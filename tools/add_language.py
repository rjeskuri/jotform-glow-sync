#!/usr/bin/env python3
"""
Offer another language on the attendance forms.

Two things make a language work on a Jotform form: its display name in the
form's `language.options` list (the switcher), and a dictionary of
translations keyed by md5 of the English text (see tools/add_translations.py
for the mechanics: base/en must hold the English source; text elements are
keyed by their element id). This tool does both:

    --name    the display name exactly as Jotform's own language table spells
              it (e.g. "Oriya" for Odia; Arabic's key carries two invisible
              direction-control characters, which --name arabic handles)
    --code    the two-letter code the store uses (or, ar, ...)
    --dict    optional JSON of English -> translation (tools/translations_or.json);
              omit when the form already has the strings (Arabic)

Usage:
    export JOTFORM_API_KEY=...
    python3 tools/add_language.py --code ar --name arabic                       # dry run
    python3 tools/add_language.py --code or --name Oriya --dict tools/translations_or.json --apply
"""
import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow import forms as glow_forms   # noqa: E402
from glow.cli import run               # noqa: E402
from glow.jotform import Client        # noqa: E402
from glow.text import md5              # noqa: E402

FORMS = {**{fid: glow_forms.TITLES[region] for region, fid in glow_forms.REGIONALS.items()},
         glow_forms.TEMPLATE: glow_forms.TEMPLATE_TITLE}
SPECIAL_NAMES = {"arabic": "Arabic‬‎"}   # as in Jotform's table
LINK_SENTENCE = "Click here to report a problem"
LINK_ELEMENT_NAME = "somethingNotWorking"


def load_dict(path):
    data = json.load(open(path, encoding="utf-8"))
    out = {}
    for english, text in data.items():
        if english.startswith("_"):
            continue
        if "{n}" in english:
            for n in range(1, 16):
                out[english.replace("{n}", str(n))] = text.replace("{n}", str(n))
        else:
            out[english] = text
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--code", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--dict", help="JSON: English -> translation")
    ap.add_argument("--form", action="append")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    api_key = os.environ.get("JOTFORM_API_KEY") or sys.exit("Set JOTFORM_API_KEY")
    # the big translation POSTs 504 at the gateway now and then: retry hard
    client = Client(api_key, apply=args.apply, retries=5, backoff=8, max_time=150)
    name = SPECIAL_NAMES.get(args.name.lower(), args.name)
    words = load_dict(args.dict) if args.dict else {}
    targets = {f: FORMS.get(f, f) for f in args.form} if args.form else FORMS

    for form_id, title in targets.items():
        props = client.get(f"/form/{form_id}/properties")
        lang = props.get("language")
        lang = lang[0] if isinstance(lang, list) and lang else (lang or {})
        options = [o for o in str(lang.get("options", "")).split("|") if o]
        store = client.get(f"/form/{form_id}/translations")
        have = store.get(args.code, {})
        base = store.get("base", {})

        # translations to post: only strings whose English source is on this form
        new = {}
        if words:
            for english, text in words.items():
                if md5(english) in base:
                    new[md5(english)] = text
            questions = client.get(f"/form/{form_id}/questions")
            link = next((q for q in questions.values() if q.get("name") == LINK_ELEMENT_NAME), None)
            if link and LINK_SENTENCE in words:
                text_id = f"text_{link['qid']}"
                for k, english in base.items():
                    if english == text_id or (LINK_SENTENCE in english and english.startswith("<")):
                        new[k] = english.replace(LINK_SENTENCE, words[LINK_SENTENCE]) if english.startswith("<") \
                            else link["text"].replace(LINK_SENTENCE, words[LINK_SENTENCE])
        covered = sum(1 for k in (dict(have, **new)) if k in base)
        print(f"== {title}: switcher {'already has' if name in options else 'will get'} {name!r}; "
              f"{args.code} strings now {len(have)}, +{sum(1 for k in new if k not in have)} new, "
              f"{covered} of {sum(1 for k in store.get('es', {}) if k in base)} form strings covered")
        if not args.apply:
            continue

        if name not in options:
            lang["options"] = "|".join(options + [name])
            client.put_json(f"/form/{form_id}/properties",
                            {"properties": {"language": [lang]}}, f"{form_id} set options")
        if new:
            merged = dict(have)
            merged.update(new)
            client.post_json(f"/form/{form_id}/translations", {args.code: merged},
                             f"{form_id} post {args.code}")
        # re-render the cached page
        client.post_form(f"/form/{form_id}/properties",
                         {"properties[pagetitle]": title}, f"{form_id} nudge")
        after = client.get(f"/form/{form_id}/translations")
        props = client.get(f"/form/{form_id}/properties")
        opts = props["language"][0]["options"] if isinstance(props.get("language"), list) else ""
        ok = name in opts and all(after.get(args.code, {}).get(k) == v for k, v in new.items())
        print(f"   {'OK' if ok else 'PROBLEM'}: switcher = {opts}")

    if not args.apply:
        print("\nDRY RUN - re-run with --apply to write")


if __name__ == "__main__":
    run(main)
