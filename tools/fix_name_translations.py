#!/usr/bin/env python3
"""
Take out of each form's translation dictionary the stale entries that alter girls' names.

Each attendance form carries a translation store (base/en and one dictionary per
offered language) cloned from the template. Jotform's runtime builds a lookup
from it in the browser, collapsing whitespace in every key, and the calculation
that fills question 18 (the girls Salesforce stores as present) passes each
ticked name through that lookup. Stale entries that spell a girl's name with a
double space, a tab or a non-breaking space therefore replace her exact name in
question 18: a second Contact in Salesforce (docs/plans/2026-10-02-names-and-
modules.md). This tool finds, by emulating the runtime exactly
(glow/translation_lookup.py), the `base`/`en` entries whose lookup alters a
roster option of ANY of the five forms (a girl who moves region, or a namesake,
must not revive one) - and only those - and removes them. Removal, not
correction: a name with no entry is the normal state and comes out exact.

Dry run by default: per form, the roster options the dictionary alters today
(counts and club names, never a girl's name), the keys it would remove, and
what is altered after (emulated, every language the store holds, both runtime
builds: 0). --apply (one --form at a time, template first) saves the whole
store to backups/translations/<form>-<stamp>-before.json (mode 600), POSTs
`base` and `en` without those keys (GET, merge, POST: no other language is
posted, CLAUDE.md rule 9), re-reads the store and compares every entry, audits
the re-read store (0 altered), then reads the public page and counts the
removed keys it still embeds: if any after a wait, ONE more write - the form's
`pagetitle` posted back unchanged, which makes Jotform re-render the page -
and it reads the page again. A lost or non-JSON answer to the POST is re-read
and reported as unchanged, applied or partial, never guessed.

Refuses, writing nothing: a store without `base` or `en`, below STORE_FLOOR
entries in either (a truncated read), or with an entry that is not text; a key
to remove that another language translates, or an alteration another
language's entry makes; more than MAX_KEYS keys; anything still altered after
the removal; --apply on more or fewer than one form.

Rollback: --restore <saved store> --form <id> (a dry run; --apply writes) puts
back every `base`/`en` entry of the saved store that the form no longer has, in
the saved order; entries changed or added since are kept as they are.

Usage:
    export JOTFORM_API_KEY=...
    python3 tools/fix_name_translations.py                                       # dry run, all five forms
    python3 tools/fix_name_translations.py --form 262352490535154                # dry run, the template
    python3 tools/fix_name_translations.py --form 262352490535154 --apply        # write that form
    python3 tools/fix_name_translations.py --form <id> --restore backups/translations/<id>-<stamp>-before.json
    python3 tools/fix_name_translations.py --form <id> --restore <that file> --apply
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, REPO)
import add_translations                                     # noqa: E402  (save_store: mode 600, never over a file)
from form_status import embedded_store, public_page, roster_options   # noqa: E402
from glow import forms as glow_forms                        # noqa: E402
from glow import translation_lookup as tl                   # noqa: E402
from glow.cli import run                                    # noqa: E402
from glow.jotform import Client, JotformError               # noqa: E402

# template first, then the regional forms smallest first (the rollout's order)
ORDER = [glow_forms.TEMPLATE] + [glow_forms.REGIONALS[r] for r in ("U.S", "Latin America", "Asia", "Africa")]
LABEL = {fid: glow_forms.LIVE[fid] for fid in ORDER}
SOURCES = (tl.SOURCE, tl.PRIMARY)       # the only dictionaries ever posted
MAX_KEYS = 300                          # 55 on every form, read 2026-10-02
STORE_FLOOR = 1000                      # entries in base and in en; 4,416 to 6,079 read 2026-10-02
PAGE_WAIT, PAGE_TRIES = 20, 3           # seconds between reads of the public page, and how many


def shown(path):
    """A saved store's path as the RUNBOOK writes it (backups/translations/...)."""
    return os.path.relpath(path, add_translations.REPO)


class Refused(Exception):
    """A form this tool will not write (the reason says what to fix)."""


def get(client, path, what):
    """A read whose failure is reported in our words: Jotform's answer is never echoed
    (a translation store holds every girl's name)."""
    try:
        return client.get(path)
    except JotformError:
        sys.exit(f"Could not read {what} (an error or a non-JSON answer from Jotform) - nothing "
                 "written; run again")


def read_options(client):
    """{form id: roster_options()} for all five forms: every roster option counts, whichever
    form is written."""
    return {fid: roster_options(get(client, f"/form/{fid}/questions", f"{LABEL[fid]}'s questions"))
            for fid in ORDER}


def store_problems(store):
    """Why a store must not be written from (or restored from), or []."""
    floor = STORE_FLOOR
    why = tl.check_store(store)
    if why:
        return [why]
    out = [f"the store has no {lang!r} dictionary" for lang in SOURCES if lang not in store]
    out += [f"the store's {lang!r} dictionary has {len(store[lang])} entries, below {floor} "
            "(a truncated read?)" for lang in SOURCES if lang in store and len(store[lang]) < floor]
    return out


def plan_form(store, options, primary=tl.PRIMARY):
    """What to remove from one store. options: read_options(). Returns {"keys", "base",
    "en", "altered" (option texts the lookup changes today, any form), "after" (the same
    once the keys are out), "refusals"}; never a girl's name in what it prints."""
    plan = {"keys": set(), "base": 0, "en": 0, "altered": {}, "after": {}, "refusals": store_problems(store)}
    if plan["refusals"]:
        return plan
    texts = {o for opts in options.values() for _, _, o in opts}
    plan["altered"] = tl.altered(store, texts, primary)
    keys, why = tl.removal(store, texts, primary)
    if why:
        plan["refusals"].append(why)
        return plan
    translated = sorted(tl.js_trim(lang) for lang, d in store.items()
                        if tl.js_trim(lang) not in SOURCES and keys & set(d))
    if translated:
        plan["refusals"].append(f"a key to remove is translated in {', '.join(translated)}")
    if len(keys) > MAX_KEYS:
        plan["refusals"].append(f"{len(keys)} keys to remove, more than {MAX_KEYS} - not stale spellings "
                                "of a few names: read the store before anything is written")
    plan["after"] = tl.altered(tl.without(store, keys, SOURCES), texts, primary)
    if plan["after"]:
        plan["refusals"].append(f"{len(plan['after'])} option(s) would still be altered after the removal")
    plan.update(keys=keys, base=len(keys & set(store[tl.SOURCE])), en=len(keys & set(store[tl.PRIMARY])))
    return plan


def own(options, fid, altered):
    """(roster options of form `fid` that `altered` holds, their clubs sorted)."""
    found = [(club, o) for _, club, o in options[fid] if o in altered]
    return found, sorted({club for club, _ in found}, key=str.lower)


def describe(fid, store, plan, options, title):
    found, clubs = own(options, fid, plan["altered"])
    langs = {}
    for ls in plan["altered"].values():
        for lang in ls:
            langs[lang] = langs.get(lang, 0) + 1
    print(f"\n== {LABEL[fid]} {fid}")
    if tl.check_store(store) is None:
        print(f"   store: base {len(store.get(tl.SOURCE, {}))}, en {len(store.get(tl.PRIMARY, {}))}, "
              f"{len(tl.target_languages(store)) - 1} other language(s)")
    if plan["altered"] or not plan["refusals"]:
        on = {LABEL[f]: len(own(options, f, plan["altered"])[0]) for f in ORDER}
        print(f"   altered today: {len(found)} of this form's {len(options[fid])} roster options"
              + (f", in {len(clubs)} club(s)" if found else "")
              + f"; its dictionary alters {len(plan['altered'])} option text(s) of the five forms ("
              + ", ".join(f"{lang} {n}" for lang, n in sorted(langs.items())) + "; on "
              + ", ".join(f"{label} {n}" for label, n in on.items()) + ")")
        if clubs:
            print("   clubs: " + "; ".join(clubs))
    if plan["refusals"]:
        for why in plan["refusals"]:
            print(f"   REFUSED: {why}")
        return
    if not plan["keys"]:
        print("   nothing to remove: the dictionary alters no roster option of the five forms")
        return
    print(f"   keys to remove: {len(plan['keys'])} (base {plan['base']}, en {plan['en']}) - only the entries "
          "behind those alterations")
    print(f"   after the removal (emulated, {len(tl.target_languages(store))} language(s), both runtime "
          f"builds): {len(plan['after'])} option(s) altered")
    print("   --apply: save the whole store (mode 600); POST base and en without those keys (no other "
          "language); re-read and compare every entry; audit the re-read store; read the public page")
    print(f"   ...and if the page still serves a removed key after {PAGE_WAIT}s, ONE more write: POST "
          f"/form/{fid}/properties properties[pagetitle] = {title!r} (its current value: Jotform "
          "re-renders the page), re-read it, read the page again")


def outcome(before, after, want):
    """How the re-read store compares: ("applied" | "unchanged" | "partial", detail counts)."""
    if not isinstance(after, dict) or tl.check_store(after):
        return "partial", "the re-read store is not a translation store"
    others = [lang for lang in set(before) | set(after) if lang not in SOURCES]
    moved = [lang for lang in others if before.get(lang) != after.get(lang)]
    if all(after.get(lang) == want[lang] for lang in SOURCES) and not moved:
        return "applied", ""
    if all(after.get(lang) == before.get(lang) for lang in SOURCES) and not moved:
        return "unchanged", ""
    detail = []
    for lang in SOURCES:
        a, w = after.get(lang, {}), want[lang]
        missing = sum(1 for k in w if k not in a)
        extra = sum(1 for k in a if k not in w)
        changed = sum(1 for k in w if k in a and a[k] != w[k])
        if missing or extra or changed:
            detail.append(f"{lang}: {missing} entr(ies) missing, {extra} that should be gone, {changed} changed")
    if moved:
        detail.append(f"other languages changed: {', '.join(sorted(moved))}")
    return "partial", "; ".join(detail)


def post_sources(client, fid, before, want, label):
    """POST base and en (want), then re-read and compare. Returns (outcome, detail, after)."""
    lost = False
    try:
        client.post_json(f"/form/{fid}/translations", {lang: want[lang] for lang in SOURCES}, label)
    except JotformError:
        lost = True              # never echoed; the re-read says what happened
        print("   ! Jotform's answer to the POST was lost or not JSON - re-reading the store")
    after = get(client, f"/form/{fid}/translations", "the store after the POST (the write may or may not "
                "have happened: compare by hand with the saved store")
    state, detail = outcome(before, after, want)
    print(f"   re-read: {state.upper()}" + (f" ({detail})" if detail else "")
          + (" - despite the lost answer" if lost and state == "applied" else ""))
    return state, detail, after


def page_count(fid, keys, present, page_of):
    """How many of `keys` the public page's embedded store holds in base/en (present=True) or
    lacks (present=False); None when the page could not be read."""
    store, _ = embedded_store(page_of(fid))
    if store is None:
        return None
    held = {k for lang in SOURCES for k in store.get(lang, {})}
    return sum(1 for k in keys if (k in held) == present)


def check_page(client, fid, keys, present, page_of, sleep):
    """Read the public page until it serves the change (or PAGE_TRIES reads), re-rendering
    it once with the unchanged pagetitle if needed. Returns True when it does."""
    def waiting():
        n = None
        for attempt in range(PAGE_TRIES):
            n = page_count(fid, keys, present, page_of)
            if n == 0:
                return 0
            if attempt < PAGE_TRIES - 1:
                sleep(PAGE_WAIT)
        return n

    what = "removed keys still served" if present else "restored keys not yet served"
    n = waiting()
    if n == 0:
        print(f"   public page: 0 {what}")
        return True
    if n is None:
        print("   public page: could not read its embedded store - check with tools/form_status.py "
              f"--form {fid} --rendered in a few minutes")
        return False
    print(f"   public page: {n} {what} - re-rendering it (pagetitle posted back unchanged)")
    props = get(client, f"/form/{fid}/properties", "the form's properties")
    title = props.get("pagetitle")
    if not title:
        print("   ! the form has no pagetitle to post back - re-save the form in the builder, then "
              f"tools/form_status.py --form {fid} --rendered")
        return False
    client.post_form(f"/form/{fid}/properties", {"properties[pagetitle]": title},
                     f"{fid} re-render (pagetitle unchanged)")
    again = get(client, f"/form/{fid}/properties", "the form's properties after the re-render")
    print(f"   pagetitle re-read: {'unchanged' if again.get('pagetitle') == title else 'CHANGED - set it back'}")
    sleep(PAGE_WAIT)
    n = waiting()
    print(f"   public page: {n if n is not None else 'unreadable,'} {what}")
    return n == 0


def apply_form(client, fid, store, plan, options, stamp, page_of=public_page, sleep=time.sleep,
               primary=tl.PRIMARY):
    """The write for one form (the plan must have no refusal). Exits non-zero on anything
    but a clean, verified write."""
    keys = plan["keys"]
    if plan["refusals"]:
        raise Refused("; ".join(plan["refusals"]))
    if not keys:
        print("   nothing written")
        return
    path = add_translations.save_store(fid, store, stamp)
    print(f"   store saved: {shown(path)} (mode 600; the rollback: --restore)")
    want = {lang: {k: v for k, v in store[lang].items() if k not in keys} for lang in SOURCES}
    state, _, after = post_sources(client, fid, store, want,
                                   f"{fid} POST base and en without {len(keys)} key(s)")
    if state != "applied":
        sys.exit(f"Stopped: the store reads {state} after the POST. "
                 + ("Nothing was written; run again." if state == "unchanged" else
                    f"Put it back: --form {fid} --restore {shown(path)} --apply"))
    texts = {o for opts in options.values() for _, _, o in opts}
    left = tl.altered(after, texts, primary)
    found, clubs = own(options, fid, left)
    print(f"   audit of the re-read store: {len(found)} of this form's roster options altered, "
          f"{len(left)} option text(s) of the five forms")
    if left:
        sys.exit("Stopped: the re-read store still alters roster options - compare it with the saved store")
    if not check_page(client, fid, keys, True, page_of, sleep):
        sys.exit("The store is fixed but the public page could not be shown to serve it - "
                 f"tools/form_status.py --form {fid} --rendered before going on")


def merged_restore(saved, current):
    """base/en with every entry of `saved` the form no longer has put back, in the saved
    order; entries changed or added since are kept as they are. Returns (want, counts)."""
    want, counts = {}, {}
    for lang in SOURCES:
        s, c = saved[lang], current.get(lang, {})
        out = {k: (c[k] if k in c else v) for k, v in s.items()}
        out.update({k: v for k, v in c.items() if k not in s})
        want[lang] = out
        counts[lang] = {"back": sum(1 for k in s if k not in c),
                        "changed": sum(1 for k in s if k in c and c[k] != s[k]),
                        "newer": sum(1 for k in c if k not in s)}
    return want, counts


def restore(client, fid, path, apply, options, stamp, page_of=public_page, sleep=time.sleep,
            primary=tl.PRIMARY):
    if not os.path.basename(path).startswith(f"{fid}-"):
        raise Refused(f"{os.path.basename(path)} is not a saved store of form {fid} (its name starts "
                      "with the form id)")
    try:
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, ValueError) as err:
        raise Refused(f"cannot read {path}: {err.__class__.__name__}")
    problems = store_problems(saved)
    if problems:
        raise Refused(f"{path}: " + "; ".join(problems))
    current = get(client, f"/form/{fid}/translations", f"{LABEL.get(fid, fid)}'s store")
    if tl.check_store(current):
        raise Refused(f"the form's store: {tl.check_store(current)}")
    want, counts = merged_restore(saved, current)
    back = {k for lang in SOURCES for k in saved[lang] if k not in current.get(lang, {})}
    texts = {o for opts in options.values() for _, _, o in opts}
    found, clubs = own(options, fid, tl.altered({**current, **want}, texts, primary))
    print(f"\n== {LABEL.get(fid, fid)} {fid}: restore from {shown(path)}")
    for lang in SOURCES:
        c = counts[lang]
        print(f"   {lang}: {c['back']} entr(ies) put back; {c['changed']} changed since and {c['newer']} added "
              "since, kept as they are")
    print(f"   after the restore: {len(found)} of this form's roster options altered again"
          + (f", in {len(clubs)} club(s)" if found else ""))
    if not back:
        print("   nothing to restore")
        return
    if not apply:
        print("   --apply: save the current store (mode 600); POST base and en with those entries back "
              "(no other language); re-read and compare; read the public page")
        return
    saved_now = add_translations.save_store(fid, current, stamp)
    print(f"   current store saved: {shown(saved_now)} (mode 600)")
    state, _, _ = post_sources(client, fid, current, want, f"{fid} POST base and en with {len(back)} key(s) back")
    if state != "applied":
        sys.exit(f"Stopped: the store reads {state} after the restore POST - compare it with "
                 f"{shown(saved_now)}")
    if not check_page(client, fid, back, False, page_of, sleep):
        sys.exit(f"Restored, but the public page could not be shown to serve it - tools/form_status.py "
                 f"--form {fid} --rendered")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    ap.add_argument("--form", action="append", help="form id (repeatable; default: all five, dry run)")
    ap.add_argument("--apply", action="store_true", help="write (exactly one --form; template first)")
    ap.add_argument("--restore", metavar="FILE",
                    help="put back the base/en entries of this saved store that the form no longer has "
                         "(a dry run; --apply writes)")
    args = ap.parse_args()
    forms = args.form or ORDER
    unknown = [f for f in forms if f not in LABEL]
    if unknown:
        sys.exit(f"Not one of the five forms: {', '.join(unknown)} (template {glow_forms.TEMPLATE}; the "
                 "regional ids in docs/RUNBOOK.md)")
    if (args.apply or args.restore) and len(args.form or []) != 1:
        sys.exit("--apply and --restore take exactly one --form: the rollout is one form at a time, "
                 "template first (docs/RUNBOOK.md, \"The names dictionary and the module values\")")
    api_key = os.environ.get("JOTFORM_API_KEY") or sys.exit("Set JOTFORM_API_KEY in the environment")
    client = Client(api_key, apply=args.apply)
    stamp = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    options = read_options(client)
    print("Roster options read from all five forms: "
          + ", ".join(f"{LABEL[f]} {len(options[f])}" for f in ORDER)
          + f" ({len({o for opts in options.values() for _, _, o in opts})} distinct texts)")
    if args.restore:
        try:
            restore(client, forms[0], args.restore, args.apply, options, stamp, public_page, time.sleep)
        except Refused as why:
            sys.exit(f"Refused, nothing written: {why}")
        return
    plans, refused = {}, []
    for fid in [f for f in ORDER if f in forms]:
        props = get(client, f"/form/{fid}/properties", f"{LABEL[fid]}'s properties")
        lang = props.get("language")
        lang = lang[0] if isinstance(lang, list) and lang else (lang or {})
        primary = lang.get("primaryLanguage") or tl.PRIMARY
        if primary != tl.PRIMARY:
            sys.exit(f"{LABEL[fid]}: primaryLanguage is {primary!r}, not {tl.PRIMARY!r} - this tool posts "
                     "base and en only; refusing rather than guessing")
        store = get(client, f"/form/{fid}/translations", f"{LABEL[fid]}'s store")
        plan = plan_form(store, options)
        describe(fid, store, plan, options, props.get("pagetitle"))
        plans[fid] = (store, plan)
        if plan["refusals"]:
            refused.append(LABEL[fid])
    if refused:
        sys.exit(f"\nRefused, nothing written: {', '.join(refused)} (the REFUSED lines above)")
    if not args.apply:
        print("\nDRY RUN - re-run with --form <id> --apply to write (template first)")
        return
    fid = forms[0]
    store, plan = plans[fid]
    print(f"\nAPPLY {LABEL[fid]} {fid}")
    try:
        apply_form(client, fid, store, plan, options, stamp, public_page, time.sleep)
    except Refused as why:
        sys.exit(f"Refused, nothing written: {why}")


if __name__ == "__main__":
    run(main)
