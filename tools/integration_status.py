#!/usr/bin/env python3
"""Is the Salesforce integration on the attendance forms what it must be? Read-only
(docs/plans/2026-09-30-salesforce-reconnect.md).

The integration is set up per form in Jotform's form builder - the API cannot write it (a PUT
or POST of the `integrations` property answers 200 and changes nothing; verified 2026-09-30).
This tool reads each form and says whether it carries the one known action: create a record of
Attendance_Batch__c, the eight fields from their questions, the Group Photo as upload - with
Account_Name__c read from question 5 (the hidden Club Name field every form shares), never
from the Club picker, and all live forms on one connection.

    python3 tools/integration_status.py              # the five live forms and the old ones
    python3 tools/integration_status.py --form <id>  # one form

Exit 1 when a live form asked for is not right. The key comes from JOTFORM_API_KEY.
"""
import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow import forms                  # noqa: E402
from glow.jotform import Client         # noqa: E402
from glow.sync import CLUB_NAME, PICKER_NAME   # noqa: E402

KEY = "salesforceV2"
# the one action the forms have carried since the pilot: Salesforce field -> question id
MAPPING = {"Account_Name__c": CLUB_NAME, "Attendance_Date__c": "17", "Contact_IDs__c": "18",
           "Module__c": "98", "Module_Week__c": "100", "Module_Year__c": "102",
           "Creator__c": "105", "enable_fuzzy_matching__c": "109"}
UPLOADS = ["19"]
# the questions behind it, by their field names
QUESTIONS = {CLUB_NAME: "clubName", "17": "date", "18": "contact_ids", "98": "module_id",
             "100": "week_id", "102": "year_id", "105": "creator", "109": "enableFuzzy",
             "19": "photo"}


def block_of(props):
    """The form's salesforceV2 block, or None (Jotform returns [] when there is no integration)."""
    value = props.get("integrations") or {}
    if isinstance(value, str):
        value = json.loads(value)
    block = value.get(KEY) if isinstance(value, dict) else None
    return block if isinstance(block, dict) else None


def problems(block, questions):
    """What is wrong with a form's Salesforce integration ([] = right)."""
    raw = block.get("actionMap")
    acts = json.loads(raw) if isinstance(raw, str) else raw
    if not block.get("integrationAccountID"):
        return ["no connected Salesforce account"]
    if not isinstance(acts, list) or len(acts) != 1:
        return [f"{len(acts) if isinstance(acts, list) else 0} actions (want exactly one)"]
    act, out = acts[0], []
    if (act.get("action"), act.get("upsert"), act.get("object")) != ("createRecord", "create",
                                                                     "Attendance_Batch__c"):
        out.append(f"the action is {act.get('action')}/{act.get('upsert')} on {act.get('object')}, "
                   "not 'create a new record' of Attendance_Batch__c")
    have = {f.get("targetId"): str((f.get("source") or {}).get("value"))
            for f in act.get("fieldMapping") or [] if (f.get("source") or {}).get("type") == "question"}
    names = {qid: (q.get("name"), q.get("text")) for qid, q in questions.items()}
    for field, qid in MAPPING.items():
        got = have.get(field)
        if got == qid:
            continue
        what = "is not mapped from a question" if got is None else f"reads q{got}"
        if got is not None and names.get(got, (None,))[0] == PICKER_NAME:
            what += " (the Club picker)"
        out.append(f"{field} {what}; it must read q{qid} ({QUESTIONS[qid]})")
    out += [f"{f} is mapped too (leave it unmapped)" for f in sorted(set(have) - set(MAPPING))]
    if len(act.get("fieldMapping") or []) != len(have):
        out.append("a field is mapped from something that is not a question")
    if list(act.get("uploadFields") or []) != UPLOADS:
        out.append(f"the upload field is {act.get('uploadFields')}, not the Group Photo (q{UPLOADS[0]})")
    out += [f"the form has no q{qid} named {name}" for qid, name in QUESTIONS.items()
            if names.get(qid, (None,))[0] != name]
    return out


def main(argv=None, client=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--form", help="one form id (default: every attendance form, old ones included)")
    args = ap.parse_args(argv)
    if client is None:
        key = os.environ.get("JOTFORM_API_KEY")
        if not key:
            sys.exit("JOTFORM_API_KEY is not in the environment (RUNBOOK, Credentials)")
        client = Client(key)
    old = {fid: f"old {name}" for name, fid in forms.DEFUNCT.items()}
    known = {**forms.LIVE, **old}
    if args.form and args.form not in known:
        sys.exit("not one of the attendance forms (glow/forms.py)")
    wanted = [args.form] if args.form else list(known)
    bad, connections = 0, set()
    for form_id in wanted:
        label = known[form_id]
        block = block_of(client.get(f"/form/{form_id}/properties"))
        if form_id in old:
            print(f"{label}: " + ("STILL CONNECTED to Salesforce - it takes a typed club name; remove "
                                  "the integration or disable the form" if block else
                                  "no Salesforce integration (as wanted)"))
            continue
        if block is None:
            print(f"{label}: NO Salesforce integration - set it up in the form builder (RUNBOOK)")
            bad += 1
            continue
        found = problems(block, client.get(f"/form/{form_id}/questions"))
        connections.add(str(block.get("integrationAccountID")))
        if found:
            bad += 1
            print(f"{label}: connection {block.get('integrationAccountID')} - NOT RIGHT:")
            for line in found:
                print(f"  - {line}")
        else:
            print(f"{label}: connection {block.get('integrationAccountID')} - ok (one action, 8 fields, "
                  f"Account_Name__c from q{CLUB_NAME}, photo q{UPLOADS[0]})")
    if len(connections) > 1:
        bad += 1
        print(f"the live forms use {len(connections)} different connections: {sorted(connections)}")
    if bad:
        sys.exit(1)
    print("integration: ok")


if __name__ == "__main__":
    main()
