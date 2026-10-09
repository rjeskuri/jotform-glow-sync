#!/usr/bin/env python3
"""
Restore a form's conditional logic from a snapshot taken by backup_forms.py.

This is the rollback path when a sync or manual edit breaks a form's logic.
It only touches the `conditions` property; questions, emails, and the
Salesforce integration are left exactly as they are.

Because the questions stay, a snapshot must still fit them. It is refused
when its rules test a club on the Club picker - or list one in the club guard
- that the picker does not offer today: those clubs' rosters would never
show, and on a guarded form their mentors could not submit. That is every
snapshot taken before a form's --same-name-switch (its rules say "Ruby", the
picker says "Ruby - <partner>"), and any taken before a club was renamed. Run
the sync instead; --force overrides (then run the sync dry run and --apply
straight away: it rebuilds the rules on what the picker lists).

A snapshot from before question 18's rules were rebuilt (Contact_IDs first,
the picker an operand: docs/plans/2026-09-30-contact-ids.md) restores with a
note: the form then reads NOT CLEAN and the runner stops its region until the
sync is applied by hand or glow/sync.py's constants are turned off.

Usage:
    export JOTFORM_API_KEY=...
    python3 restore_conditions.py --form 262352490535154                    # dry run
    python3 restore_conditions.py --form 262352490535154 --apply
    python3 restore_conditions.py --form <ID> --from conditions-2026-08-24T1730.json
"""
import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
from glow.cli import api_key, run          # noqa: E402
from glow.jotform import Client   # noqa: E402
from glow import sync as glow_sync             # noqa: E402
from glow.sync import CLUB_NAME, PICKER_NAME   # noqa: E402


def contact_ids_note(conditions, questions):
    """A line for a snapshot whose rules calculate question 18 the way glow/sync.py's
    constants no longer generate (before docs/plans/2026-09-30-contact-ids.md): it
    restores, but form_status reports the form NOT CLEAN and the runner stops its
    region until the sync is applied by hand - or the constants are turned off, the
    generated rollback. None when the snapshot is in the current shape."""
    picker = next((str(qid) for qid, q in questions.items()
                   if q.get("type") == "control_dropdown" and q.get("name") == PICKER_NAME), None)
    rosters = {str(qid) for qid, q in questions.items() if q.get("type") == "control_checkbox"}
    stale = glow_sync.contact_ids_stale(conditions, rosters, picker)
    if not stale:
        return None
    return ("  ! the snapshot calculates question 18 (Contact_IDs) the old way ("
            + " and ".join({"order": "after the rosters' rules",
                            "operand": "without the Club picker as an operand"}[s] for s in stale)
            + "): restored, form_status reports this form NOT CLEAN and the runner does not apply its "
              "region until the sync is applied by hand, or glow/sync.py's CONTACT_IDS_* constants "
              "are off (the generated rollback, docs/RUNBOOK.md \"The names list sent to Salesforce\")")


def stale_club_terms(conditions, questions):
    """The club texts a snapshot's rules test that the form's Club picker does
    not offer (exactly, as a multi-select compares): values of `equals` terms
    on the picker - roster rules - and of `notEquals` terms on question 5 - the
    club guard's list. Sorted, each once. [] on a form without the picker."""
    picker = next((str(qid) for qid, q in questions.items()
                   if q.get("type") == "control_dropdown" and q.get("name") == PICKER_NAME), None)
    if picker is None:
        return []
    options = {o for o in (questions[picker].get("options") or "").split("|") if o}
    stale = set()
    for c in conditions:
        try:
            terms = json.loads(c["terms"]) if isinstance(c.get("terms"), str) else c.get("terms")
        except ValueError:
            continue
        for t in terms or []:
            field, op, value = str(t.get("field")), t.get("operator"), str(t.get("value") or "")
            if value and value not in options and \
                    ((field == picker and op == "equals") or (field == CLUB_NAME and op == "notEquals")):
                stale.add(value)
    return sorted(stale)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--form", required=True)
    ap.add_argument("--from", dest="src",
                    help="snapshot filename in backups/<form>/ "
                         "(default: properties-latest.json)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="restore even when the snapshot's rules test clubs the Club picker does "
                         "not offer today (their rosters will not show until the sync runs)")
    args = ap.parse_args()

    client = Client(api_key(), apply=args.apply)

    path = os.path.join(REPO, "backups", args.form,
                        args.src or "properties-latest.json")
    if not os.path.exists(path):
        sys.exit(f"No snapshot at {path} - run backup_forms.py first")
    with open(path, encoding="utf-8") as f:
        saved = json.load(f)
    conditions = saved["conditions"] if isinstance(saved, dict) else saved
    if not conditions:
        sys.exit(f"{path} holds no conditions - refusing to wipe the form")

    live = client.get(f"/form/{args.form}/properties")
    print(f"form {args.form}: live has {len(live.get('conditions', []))} "
          f"conditions; snapshot has {len(conditions)}")
    print(f"snapshot: {os.path.relpath(path, REPO)}")

    questions = client.get(f"/form/{args.form}/questions")
    note = contact_ids_note(conditions, questions)
    if note:
        print(note)
    stale = stale_club_terms(conditions, questions)
    if stale:
        msg = (f"the snapshot's rules test {len(stale)} club name(s) the Club picker does not offer "
               f"today ({', '.join(repr(s) for s in stale[:5])}{', …' if len(stale) > 5 else ''}): "
               "those clubs' rosters would never show, and with the club guard their mentors could "
               "not submit. The snapshot predates a change of the picker's entries (the same-name "
               "switch, a renamed or retired club)")
        if not args.force:
            sys.exit(f"Refusing: {msg}. Run the sync instead (dry run, then --apply); or, to restore "
                     "anyway, --force - and run the sync straight after")
        print(f"  ! --force: {msg}. Run the sync (dry run, then --apply) straight after")

    if not args.apply:
        print("\nDRY RUN - re-run with --apply to restore")
        return

    client.put_json(f"/form/{args.form}/properties",
                    {"properties": {"conditions": conditions}}, "PUT conditions")

    after = client.get(f"/form/{args.form}/properties")
    n = len(after.get("conditions", []))
    ok = n == len(conditions)
    print(f"RESTORED: {n} conditions on the server "
          f"({'matches snapshot' if ok else 'MISMATCH - investigate'})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    run(main)
