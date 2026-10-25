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

The POST replaces each language it carries, so --apply first saves the
target's whole store to backups/translations/<form>-<stamp>-before.json
(mode 600 - glow/translations.py).

--from-file <saved store> is the rollback for a translations POST that read
back MISMATCH: it puts a form's translated languages back exactly as one of
those saved files holds them. The dry run prints, per language, how many keys
differ, would be added and would be removed. --apply saves the CURRENT store
first (a new file, never over the one restored from), POSTs each language that
differs with its WHOLE saved dictionary (a replace), and re-reads: RESTORED, or
MISMATCH naming the store saved before the restore (non-zero). English
base/en are never posted; a language only the live store has is left alone
(reported); a language the file holds empty is skipped (posting {} would wipe
it). Refused: a file it cannot read, not JSON, not a store, or whose name
(<form>-<stamp>-before.json) names no form or another form than --form.

Usage:
    export JOTFORM_API_KEY=...
    python3 tools/restore_translations.py --form <TARGET_ID>                 # dry run
    python3 tools/restore_translations.py --form <TARGET_ID> --apply
    python3 tools/restore_translations.py --form <ID> --source <FORM> --apply # from another form
    python3 tools/restore_translations.py --form <ID> --check                # just report
    python3 tools/restore_translations.py --form <ID> --from-file backups/translations/<ID>-<stamp>-before.json
    python3 tools/restore_translations.py --form <ID> --from-file backups/translations/<ID>-<stamp>-before.json --apply
"""
import argparse
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow import backup                # noqa: E402  (the stamp of the saved store)
from glow import translations          # noqa: E402  (read, save, POST: rule 9)
from glow.cli import api_key, run               # noqa: E402
from glow.forms import TEMPLATE, language_of   # noqa: E402
from glow.jotform import Client        # noqa: E402

ENGLISH_KEYS = set(translations.SOURCE_KEYS)


def language_property(form_id, client):
    """The form's `language` property (glow.forms.language_of): the languages it offers."""
    return language_of(client.get(f"/form/{form_id}/properties"))


def describe(form_id, client, store=None):
    """(the languages offered, {language: entries}) of a form; `store`: its translation store
    when it was just read."""
    lang = language_property(form_id, client)
    tr = translations.read_store(client, form_id) if store is None else store
    langs = {k: len(v) for k, v in tr.items() if k not in ENGLISH_KEYS}
    return lang.get("options", ""), langs


def load_saved(path, form_id):
    """The translation store saved in `path` (a save_store() file), refusing - sys.exit - a
    name that names no form or another form than `form_id`, a file it cannot read, not
    JSON, or not a store ({language: {key: text}})."""
    name = os.path.basename(path)
    m = re.match(r"(\d{6,})-", name)
    if not m:
        sys.exit(f"{name}: the name names no form - a saved store is "
                 "backups/translations/<form>-<stamp>-before.json")
    if m.group(1) != form_id:
        sys.exit(f"{name} was saved from form {m.group(1)}, not {form_id} - "
                 f"restore it with --form {m.group(1)}, or pick a file of {form_id}")
    try:
        with open(path, encoding="utf-8") as f:
            store = json.load(f)
    except FileNotFoundError:
        sys.exit(f"{name}: no such file ({path})")
    except (OSError, UnicodeDecodeError) as err:
        sys.exit(f"{name}: cannot be read ({type(err).__name__})")
    except ValueError:
        sys.exit(f"{name}: not JSON - not a saved translation store")
    if not isinstance(store, dict) or not all(
            isinstance(d, dict) and all(isinstance(t, str) for t in d.values()) for d in store.values()):
        sys.exit(f"{name}: not a translation store ({{language: {{key: text}}}})")
    return store


def counts(saved, live):
    """(differ, added, removed) of one language: keys in both with other text, keys only the
    saved dictionary has, keys only the live one has."""
    return (sum(1 for x in saved if x in live and live[x] != saved[x]),
            sum(1 for x in saved if x not in live),
            sum(1 for x in live if x not in saved))


def restore_from_file(args, client):
    """--from-file: the form's translated languages put back as the saved store holds them."""
    saved = load_saved(args.from_file, args.form)
    name = os.path.basename(args.from_file)
    wanted = {lang: d for lang, d in saved.items() if lang not in ENGLISH_KEYS}
    print(f"form {args.form}: restore from {name} (English base/en never posted)")
    if not wanted:
        print("   the file holds no translated language: nothing to restore")
        return
    live = translations.read_store(client, args.form)
    changed = {}
    for lang in sorted(wanted):
        d = wanted[lang]
        if not d:
            print(f"   {lang}: skipped - empty in the file (posting it would wipe the language)")
            continue
        have = live.get(lang, {})
        if have == d:
            print(f"   {lang}: same already")
            continue
        differ, added, removed = counts(d, have)
        print(f"   {lang}: {differ} differ, {added} added, {removed} removed - "
              f"{'replaced' if args.apply else 'to replace'} by the file's {len(d)} entries")
        changed[lang] = d
    for lang in sorted(set(live) - set(wanted) - ENGLISH_KEYS):
        print(f"   {lang}: only on the live form - left alone")

    if not changed:
        print("\nnothing differs - nothing to post")
        return
    if not args.apply:
        print("\nDRY RUN - re-run with --apply to write (the current store is saved first)")
        return

    before = translations.save_store(args.form, live, backup.stamp())
    before_rel = os.path.relpath(before, translations.REPO)
    print(f"store saved: {before_rel}")
    after = translations.replace_languages(client, args.form, changed, "restore translations", before)
    bad = sorted(lang for lang, d in wanted.items() if d and after.get(lang) != d)
    if bad:
        sys.exit(f"MISMATCH - {', '.join(bad)} not as in {name} after the POST; "
                 f"the store before this restore: {before_rel}")
    print(f"RESTORED - {', '.join(sorted(changed))} as in {name}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--form", required=True, help="target form ID (a clone)")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--source", help="form to copy from (default: template)")
    src.add_argument("--from-file", help="a saved store (backups/translations/<form>-<stamp>-before.json) "
                                         "to put the form's languages back from")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true", help="only report the target's state")
    args = ap.parse_args()
    if args.from_file:
        if args.check:
            sys.exit("--check only reports; leave it out with --from-file (its dry run reports)")
        load_saved(args.from_file, args.form)          # refuse before any call
        restore_from_file(args, Client(api_key(), apply=args.apply))
        return
    args.source = args.source or TEMPLATE
    client = Client(api_key(), apply=args.apply)

    options, langs = describe(args.form, client)
    print(f"target {args.form}: languages offered: {options or '(none)'}")
    print(f"   translated strings: {langs or 'none'}")
    if args.check:
        return

    src_lang = language_property(args.source, client)
    src_tr = translations.read_store(client, args.source)
    have = translations.read_store(client, args.form)
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
    after = None
    if payload:
        # POST replaces each language's dictionary: send existing + source strings, the
        # target's store saved first
        merged = {}
        for lang, d in payload.items():
            merged[lang] = dict(d)
            merged[lang].update(have.get(lang, {}))
        saved = translations.save_store(args.form, have, backup.stamp())
        print(f"store saved: {os.path.relpath(saved, translations.REPO)}")
        after = translations.replace_languages(client, args.form, merged, "post translations", saved)

    options, langs = describe(args.form, client, after)
    ok = options == src_lang.get("options") and all(
        langs.get(k, 0) >= len(v) for k, v in src_tr.items() if k not in ENGLISH_KEYS)
    print(f"\nafter: languages offered: {options}")
    print(f"   translated strings: {langs}")
    print("RESTORED" if ok else "MISMATCH - compare with the source in the builder")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    run(main)
