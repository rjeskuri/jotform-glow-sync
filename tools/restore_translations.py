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
import json
import os
import subprocess
import sys

API_BASE = "https://api.jotform.com"
TEMPLATE = "262352490535154"
ENGLISH_KEYS = {"en", "base"}


def call(args, label, api_key):
    out = subprocess.run(["curl", "-sS"] + args, capture_output=True, text=True)
    try:
        resp = json.loads(out.stdout)
    except json.JSONDecodeError:
        sys.exit(f"{label}: non-JSON response (gateway error?): {out.stdout[:120]!r}")
    if resp.get("responseCode") != 200:
        sys.exit(f"{label}: {resp.get('responseCode')} {resp.get('message')}")
    return resp["content"]


def language_of(form_id, api_key):
    props = call([f"{API_BASE}/form/{form_id}/properties?apiKey={api_key}"],
                 f"{form_id} properties", api_key)
    lang = props.get("language")
    return lang[0] if isinstance(lang, list) and lang else (lang or {})


def translations_of(form_id, api_key):
    t = call([f"{API_BASE}/form/{form_id}/translations?apiKey={api_key}"],
             f"{form_id} translations", api_key)
    return t if isinstance(t, dict) else {}


def describe(form_id, api_key):
    lang = language_of(form_id, api_key)
    tr = translations_of(form_id, api_key)
    langs = {k: len(v) for k, v in tr.items() if k not in ENGLISH_KEYS}
    return lang.get("options", ""), langs


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--form", required=True, help="target form ID (a clone)")
    ap.add_argument("--source", default=TEMPLATE, help="form to copy from (default: template)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true", help="only report the target's state")
    args = ap.parse_args()
    api_key = os.environ.get("JOTFORM_API_KEY") or sys.exit("Set JOTFORM_API_KEY")

    options, langs = describe(args.form, api_key)
    print(f"target {args.form}: languages offered: {options or '(none)'}")
    print(f"   translated strings: {langs or 'none'}")
    if args.check:
        return

    src_lang = language_of(args.source, api_key)
    src_tr = translations_of(args.source, api_key)
    have = translations_of(args.form, api_key)
    payload = {k: v for k, v in src_tr.items()
               if k not in ENGLISH_KEYS and len(have.get(k, {})) < len(v)}
    print(f"source {args.source}: languages offered: {src_lang.get('options')}")
    print(f"   language property: {'same already' if options == src_lang.get('options') else 'will be copied'}")
    print(f"   translated strings to post: {({k: len(v) for k, v in payload.items()}) or 'none (target already has them)'}")

    if not args.apply:
        print("\nDRY RUN - re-run with --apply to write")
        return

    if options != src_lang.get("options"):
        call(["-X", "PUT", f"{API_BASE}/form/{args.form}/properties?apiKey={api_key}",
              "-H", "Content-Type: application/json",
              "--data-binary", json.dumps({"properties": {"language": [src_lang]}})],
             "set language property", api_key)
    if payload:
        call(["-X", "POST", f"{API_BASE}/form/{args.form}/translations?apiKey={api_key}",
              "-H", "Content-Type: application/json",
              "--data-binary", json.dumps(payload, ensure_ascii=False)],
             "post translations", api_key)

    options, langs = describe(args.form, api_key)
    ok = options == src_lang.get("options") and all(
        langs.get(k, 0) >= len(v) for k, v in src_tr.items() if k not in ENGLISH_KEYS)
    print(f"\nafter: languages offered: {options}")
    print(f"   translated strings: {langs}")
    print("RESTORED" if ok else "MISMATCH - compare with the source in the builder")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
