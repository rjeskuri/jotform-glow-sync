#!/usr/bin/env python3
"""
Give a cloned attendance form its languages back.

Jotform's API clone (POST /form/{id}/clone) copies a form's translated
strings but resets its `language` property - the list of languages the
switcher offers - to English only. So a fresh regional clone LOOKS
English-only even though the ten translations are sitting in it. This copies
the `language` property from a source form (the template by default) onto a
target, and, only where a language's strings are actually missing on the
target, the strings too (via the undocumented but working
GET/POST /form/{id}/translations endpoint).

Only translated languages are ever posted (es, fr, th, …), never the English
"en"/"base" entries: those are just the source texts and on the template they
include every roster name in the world.

Translations are keyed by a hash of the English text, so they apply to the
target's questions automatically wherever the English wording is the same.
New wording (e.g. the problem-report link) simply stays English until someone
translates it in the builder.

Usage:
    export JOTFORM_API_KEY=...
    python3 tools/restore_translations.py --form <TARGET_ID>                 # dry run
    python3 tools/restore_translations.py --form <TARGET_ID> --apply
    python3 tools/restore_translations.py --form <ID> --source <FORM> --apply # from another form
    python3 tools/restore_translations.py --form <ID> --check                # just report
"""
import argparse
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow.cli import api_key, run               # noqa: E402
from glow.forms import TEMPLATE        # noqa: E402
from glow.jotform import Client        # noqa: E402

ENGLISH_KEYS = {"en", "base"}


def language_of(form_id, client):
    props = client.get(f"/form/{form_id}/properties")
    lang = props.get("language")
    return lang[0] if isinstance(lang, list) and lang else (lang or {})


def translations_of(form_id, client):
    t = client.get(f"/form/{form_id}/translations")
    return t if isinstance(t, dict) else {}


def describe(form_id, client):
    lang = language_of(form_id, client)
    tr = translations_of(form_id, client)
    langs = {k: len(v) for k, v in tr.items() if k not in ENGLISH_KEYS}
    return lang.get("options", ""), langs


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--form", required=True, help="target form ID (a clone)")
    ap.add_argument("--source", default=TEMPLATE, help="form to copy from (default: template)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true", help="only report the target's state")
    args = ap.parse_args()
    client = Client(api_key(), apply=args.apply)

    options, langs = describe(args.form, client)
    print(f"target {args.form}: languages offered: {options or '(none)'}")
    print(f"   translated strings: {langs or 'none'}")
    if args.check:
        return

    src_lang = language_of(args.source, client)
    src_tr = translations_of(args.source, client)
    have = translations_of(args.form, client)
    payload = {k: v for k, v in src_tr.items()
               if k not in ENGLISH_KEYS and len(have.get(k, {})) < len(v)}
    print(f"source {args.source}: languages offered: {src_lang.get('options')}")
    print(f"   language property: {'same already' if options == src_lang.get('options') else 'will be copied'}")
    print(f"   translated strings to post: {({k: len(v) for k, v in payload.items()}) or 'none (target already has them)'}")

    if not args.apply:
        print("\nDRY RUN - re-run with --apply to write")
        return

    if options != src_lang.get("options"):
        client.put_json(f"/form/{args.form}/properties",
                        {"properties": {"language": [src_lang]}}, "set language property")
    if payload:
        # POST replaces each language's dictionary: send existing + source strings
        merged = {}
        for lang, d in payload.items():
            merged[lang] = dict(d)
            merged[lang].update(have.get(lang, {}))
        client.post_json(f"/form/{args.form}/translations", merged, "post translations")

    options, langs = describe(args.form, client)
    ok = options == src_lang.get("options") and all(
        langs.get(k, 0) >= len(v) for k, v in src_tr.items() if k not in ENGLISH_KEYS)
    print(f"\nafter: languages offered: {options}")
    print(f"   translated strings: {langs}")
    print("RESTORED" if ok else "MISMATCH - compare with the source in the builder")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    run(main)
