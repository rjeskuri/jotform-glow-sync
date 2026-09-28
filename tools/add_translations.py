#!/usr/bin/env python3
"""
Add translations for labels that were added after the forms were first
translated (the session dropdowns, the mentor email field, the problem-report
link, the Partner box).

Jotform keys a translation by the md5 of the English text; the runtime looks
the visible text up and swaps it. The strings and their translations live in
tools/translations_additions.json; this tool hashes them, posts them to each
form through the (undocumented but working) POST /form/{id}/translations
endpoint, and reports which visible labels are still untranslated per
language.

WARNING learned the hard way (2026-08-27): that POST REPLACES each language's
whole dictionary. This tool therefore always reads the form's current
strings and posts them back together with the additions. Never post a
partial dictionary; backups/translations/ holds full copies.

Also learned: a translation is only ever APPLIED if its key exists in the
`base` (and `en`) source map - the runtime resolves an element's text to a
key through `base`. So the English source of every added string is written
to base/en too (merged; base already holds every roster name, which is why
it is never rebuilt from scratch here).

Text elements (the links above Submit, glow/links.py: the problem-report
link and the Club Roster Form link) are keyed three ways: the plain sentence,
the element id `text_<qid>` (what the runtime looks up first; its value
replaces the whole inner HTML) and the stored HTML - the HTML variants carry
the link around the translated sentence. So this runs AFTER
tools/add_feedback_link.py has put an element on the form. Before a POST the
form's whole store is saved to backups/translations/<form>-<stamp>.json.

Usage:
    export JOTFORM_API_KEY=...
    python3 tools/add_translations.py --audit                 # what is untranslated, per form/language
    python3 tools/add_translations.py                         # dry run of the additions
    python3 tools/add_translations.py --apply
    python3 tools/add_translations.py --apply --form <ID>     # one form
"""
import argparse
import html as H
import json
import os
import re
import sys
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow import forms as glow_forms   # noqa: E402
from glow import links as glow_links   # noqa: E402
from glow.cli import run               # noqa: E402
from glow.jotform import Client        # noqa: E402
from glow.text import md5              # noqa: E402

FORMS = {**{fid: region for region, fid in glow_forms.REGIONALS.items()},
         glow_forms.TEMPLATE: "template"}
# hidden bridge fields, headers and images whose text never shows to a mentor
NEVER_SHOWN = {"18", "98", "100", "102", "105", "109", "103", "13"}
SOURCE_KEYS = ("base", "en")   # the English source maps, never a language to translate into


def visible_strings(questions):
    """English text -> where it appears, for everything a mentor can see
    (rosters excluded: names are not translated)."""
    out = {}
    for qid, q in questions.items():
        if q.get("type") == "control_checkbox" or qid in NEVER_SHOWN:
            continue
        for fld in ("text", "subHeader", "description", "subLabel"):
            v = q.get(fld)
            if isinstance(v, str) and v.strip():
                plain = H.unescape(re.sub(r"<[^>]+>", "", v)).strip()
                if plain:
                    out.setdefault(plain, set()).add(f"q{qid}.{fld}")
        if q.get("type") in ("control_dropdown", "control_radio") and q.get("options"):
            for o in q["options"].split("|"):
                if o.strip():
                    out.setdefault(o.strip(), set()).add(f"q{qid}.option")
    return out


def load_additions():
    with open(os.path.join(REPO, "tools", "translations_additions.json"), encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for english, langs in data.items():
        if english.startswith("_"):
            continue
        if "{n}" in english:
            for n in range(1, 16):
                out[english.replace("{n}", str(n))] = {l: t.replace("{n}", str(n)) for l, t in langs.items()}
        else:
            out[english] = dict(langs)
    return out


def plan_additions(questions, store, additions):
    """What to post for one form: (payload, sources).

    payload = {lang: {md5 key: translation}} for every addition whose English
    is visible on this form, in the languages the form's store has; sources =
    {md5 key: English} for base and en (the runtime resolves a text to its key
    through base, so a translation whose source is missing never applies).
    Each link element (glow/links.py) on the form is also keyed by its element
    id `text_<qid>` and by its stored HTML, both carrying the translated
    sentence inside the unchanged link."""
    strings = visible_strings(questions)
    payload, sources = {}, {}
    for english, per_lang in additions.items():
        if english not in strings:
            continue   # not on this form
        sources[md5(english)] = english
        for lang, text in per_lang.items():
            if lang in store and lang not in SOURCE_KEYS:
                payload.setdefault(lang, {})[md5(english)] = text
    for q, link in glow_links.elements_on(questions):
        sentence, stored = link.sentence, q.get("text", "")
        if sentence not in stored or sentence not in additions:
            continue
        text_id = f"text_{q['qid']}"
        for lang, text in additions[sentence].items():
            if lang in store and lang not in SOURCE_KEYS:
                html_t = stored.replace(sentence, H.escape(text, quote=False))
                payload.setdefault(lang, {})[md5(text_id)] = html_t
                payload.setdefault(lang, {})[md5(stored)] = html_t
        sources[md5(stored)] = stored
        sources[md5(text_id)] = text_id
    return payload, sources


def merge(store, payload, sources):
    """The dictionaries to POST: each touched language whole (existing entries
    plus the additions), and base/en with the new sources added - never
    overwriting a source already there (base holds every roster option)."""
    merged = {lang: {**store.get(lang, {}), **d} for lang, d in payload.items()}
    for key in SOURCE_KEYS:
        merged[key] = dict(store.get(key, {}))
        for k, english in sources.items():
            merged[key].setdefault(k, english)
    return merged


def save_store(form_id, store, stamp):
    """The whole translation store, before it is replaced (backups/ is never committed)."""
    folder = os.path.join(REPO, "backups", "translations")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{form_id}-{stamp}-before.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=1)
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--form", action="append")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--audit", action="store_true", help="only report untranslated labels")
    args = ap.parse_args()
    api_key = os.environ.get("JOTFORM_API_KEY") or sys.exit("Set JOTFORM_API_KEY")
    client = Client(api_key, apply=args.apply)
    additions = load_additions()
    targets = {f: FORMS.get(f, f) for f in args.form} if args.form else FORMS

    stamp = datetime.now().strftime("%Y-%m-%dT%H%M")

    for form_id, label in targets.items():
        questions = client.get(f"/form/{form_id}/questions")
        store = client.get(f"/form/{form_id}/translations")
        langs = [lg for lg in store if lg not in SOURCE_KEYS]

        if args.audit:
            strings = visible_strings(questions)
            print(f"\n== {label} {form_id}: {len(strings)} visible strings, languages {langs}")
            for lang in langs:
                missing = sorted(s for s in strings if md5(s) not in store.get(lang, {}))
                print(f"   {lang}: {len(missing)} untranslated" +
                      (": " + "; ".join(m[:40] for m in missing[:6]) + ("…" if len(missing) > 6 else "") if missing else ""))
            continue

        payload, sources = plan_additions(questions, store, additions)
        new = {lg: sum(1 for k in d if k not in store.get(lg, {})) for lg, d in payload.items()}
        print(f"== {label} {form_id}: {sum(len(d) for d in payload.values())} entries across "
              f"{len(payload)} languages ({sum(new.values())} new)")
        if not args.apply or not payload:
            continue
        backup = save_store(form_id, store, stamp)
        print(f"   store saved: {os.path.relpath(backup, REPO)}")
        # POST /translations REPLACES each language's dictionary, so always
        # send the existing strings plus the additions, never the additions alone
        merged = merge(store, payload, sources)
        client.post_json(f"/form/{form_id}/translations", merged, f"{form_id} post")
        after = client.get(f"/form/{form_id}/translations")
        ok = all(after.get(lg, {}).get(k) == v for lg, d in merged.items() for k, v in d.items())
        print("   " + (f"stored ({', '.join(f'{lg}:{len(after.get(lg, {}))}' for lg in merged)})"
                       if ok else "MISMATCH after write"))

    if not args.apply and not args.audit:
        print("\nDRY RUN - re-run with --apply to write")


if __name__ == "__main__":
    run(main)
