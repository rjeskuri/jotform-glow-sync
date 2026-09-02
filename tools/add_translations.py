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

Text elements (the report link) are matched two ways, because Jotform may
hash either the plain sentence or the element's whole HTML: both keys are
posted, the HTML variant carrying the link around the translated sentence.

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

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow import forms as glow_forms   # noqa: E402
from glow.cli import run               # noqa: E402
from glow.jotform import Client        # noqa: E402
from glow.text import md5              # noqa: E402

FORMS = {**{fid: region for region, fid in glow_forms.REGIONALS.items()},
         glow_forms.TEMPLATE: "template"}
# hidden bridge fields, headers and images whose text never shows to a mentor
NEVER_SHOWN = {"18", "98", "100", "102", "105", "109", "103", "13"}
LINK_ELEMENT_NAME = "somethingNotWorking"


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
    data = json.load(open(os.path.join(REPO, "tools", "translations_additions.json"), encoding="utf-8"))
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

    for form_id, label in targets.items():
        questions = client.get(f"/form/{form_id}/questions")
        store = client.get(f"/form/{form_id}/translations")
        langs = [l for l in store if l not in ("en", "base")]
        strings = visible_strings(questions)
        link = next((q for q in questions.values() if q.get("name") == LINK_ELEMENT_NAME), None)

        if args.audit:
            print(f"\n== {label} {form_id}: {len(strings)} visible strings, languages {langs}")
            for lang in langs:
                missing = sorted(s for s in strings if md5(s) not in store.get(lang, {}))
                print(f"   {lang}: {len(missing)} untranslated" +
                      (": " + "; ".join(m[:40] for m in missing[:6]) + ("…" if len(missing) > 6 else "") if missing else ""))
            continue

        payload = {}
        for english, per_lang in additions.items():
            if english not in strings and not (link and english in H.unescape(re.sub(r"<[^>]+>", "", link["text"]))):
                continue   # not on this form
            for lang, text in per_lang.items():
                if lang not in store:
                    continue
                payload.setdefault(lang, {})[md5(english)] = text
        # Text elements are special: the runtime first translates the element's
        # ID ("text_<qid>") as a word and, if a translation exists, replaces the
        # whole inner HTML with it. That is how the builder stores them. Key the
        # translated HTML by the id (and, as a fallback, by the stored HTML).
        if link:
            sentence = "Click here to report a problem"
            if sentence in link["text"] and sentence in additions:
                text_id = f"text_{link['qid']}"
                for lang, text in additions[sentence].items():
                    if lang in store:
                        html_t = link["text"].replace(sentence, text)
                        payload.setdefault(lang, {})[md5(text_id)] = html_t
                        payload.setdefault(lang, {})[md5(link["text"])] = html_t
        new = {l: sum(1 for k in d if k not in store.get(l, {})) for l, d in payload.items()}
        print(f"== {label} {form_id}: {sum(len(d) for d in payload.values())} entries across "
              f"{len(payload)} languages ({sum(new.values())} new)")
        if not args.apply or not payload:
            continue
        # POST /translations REPLACES each language's dictionary, so always
        # send the existing strings plus the additions, never the additions alone
        merged = {}
        for lang, d in payload.items():
            merged[lang] = dict(store.get(lang, {}))
            merged[lang].update(d)
        # The runtime finds an element's key by looking its English text up in
        # `base` (and the server builds the text-keyed dictionaries from it),
        # so every added key also needs its English source in base and en.
        for src_key in ("base", "en"):
            merged[src_key] = dict(store.get(src_key, {}))
            for english in additions:
                if english in strings or (link and english in link["text"]):
                    merged[src_key].setdefault(md5(english), english)
            if link:
                merged[src_key].setdefault(md5(link["text"]), link["text"])
                merged[src_key].setdefault(md5(f"text_{link['qid']}"), f"text_{link['qid']}")
        client.post_json(f"/form/{form_id}/translations", merged, f"{form_id} post")
        after = client.get(f"/form/{form_id}/translations")
        ok = all(after.get(l, {}).get(k) == v for l, d in merged.items() for k, v in d.items())
        print("   " + (f"stored ({', '.join(f'{l}:{len(after.get(l, {}))}' for l in merged)})"
                       if ok else "MISMATCH after write"))

    if not args.apply and not args.audit:
        print("\nDRY RUN - re-run with --apply to write")


if __name__ == "__main__":
    run(main)
