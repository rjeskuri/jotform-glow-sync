#!/usr/bin/env python3
"""Is the Salesforce integration on the attendance forms what it must be? Read-only
(docs/plans/2026-09-30-salesforce-reconnect.md; the photo: docs/plans/2026-10-06-photos-to-drive.md).

The integration is set up per form in Jotform's form builder - the API cannot write it (a PUT
or POST of the `integrations` property answers 200 and changes nothing; verified 2026-09-30).
This tool reads each form and says whether it carries the one known action: create a record of
Attendance_Batch__c, the eight fields from their questions and NO upload (the Group Photo has
not gone to Salesforce since 2026-10-01, the CEO's decision; it is copied to Google Drive by
Jotform's own integration instead) - with Account_Name__c read from question 5 (the hidden
Club Name field every form shares), never from the Club picker, and all live forms on one
connection. For every live form it also lists the other integration blocks the form carries
(`other integrations:`; none today).

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
from glow.cli import api_key           # noqa: E402
from glow.jotform import Client         # noqa: E402
from glow.sync import CLUB_NAME, PICKER_NAME   # noqa: E402

KEY = "salesforceV2"
# the one action the forms have carried since the pilot: Salesforce field -> question id
MAPPING = {"Account_Name__c": CLUB_NAME, "Attendance_Date__c": "17", "Contact_IDs__c": "18",
           "Module__c": "98", "Module_Week__c": "100", "Module_Year__c": "102",
           "Creator__c": "105", "enable_fuzzy_matching__c": "109"}
# no upload: the Group Photo (q19) left the mapping on 2026-10-01 (the CEO: no photo in
# Salesforce, DECISIONS) and is never re-mapped without the CEO's word
UPLOADS = []
# the questions behind it, by their field names (the photo must still exist: it is required)
QUESTIONS = {CLUB_NAME: "clubName", "17": "date", "18": "contact_ids", "98": "module_id",
             "100": "week_id", "102": "year_id", "105": "creator", "109": "enableFuzzy",
             "19": "photo"}
# TODO (docs/plans/2026-10-06-photos-to-drive.md, part 2, NOT built yet): once Ryan has set up the
# Google Drive integration on the template in the builder, the `other integrations:` line below
# prints the Drive block's key - that is how it is learned (whether the block is visible in the
# property at all is unverified). Then: DRIVE_KEY = "<that key>", a `drive: yes` /
# `drive: NO - set it up in the builder (RUNBOOK "Photos")` line per live form, and DRIVE_WANTED
# (False during the rollout, True once the U.S form reads DISABLED: a live form without the block
# is then NOT RIGHT, exit 1; a form whose `status` is DISABLED reads `drive: not wanted (form
# DISABLED)` instead). Until the key is known nothing here expects the block.


def integrations_of(props):
    """The form's `integrations` property as a dict ({} when there is none: Jotform returns [])."""
    value = props.get("integrations") or {}
    if isinstance(value, str):
        value = json.loads(value)
    return value if isinstance(value, dict) else {}


def block_of(props):
    """The form's salesforceV2 block, or None."""
    block = integrations_of(props).get(KEY)
    return block if isinstance(block, dict) else None


def other_integrations(props):
    """The keys of every other integration block the form carries (the Google Drive block's,
    once it is set up in the builder: how its key is learned)."""
    return sorted(k for k in integrations_of(props) if k != KEY)


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
    uploads = list(act.get("uploadFields") or [])
    if uploads != UPLOADS:
        out.append(f"the upload field is {uploads}, not {UPLOADS}"
                   + (" (no photo goes to Salesforce since 2026-10-01)" if not UPLOADS else ""))
    out += [f"the form has no q{qid} named {name}" for qid, name in QUESTIONS.items()
            if names.get(qid, (None,))[0] != name]
    return out


def main(argv=None, client=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--form", help="one form id (default: every attendance form, old ones included)")
    args = ap.parse_args(argv)
    if client is None:
        client = Client(api_key(" - docs/RUNBOOK.md, \"Credentials\""))
    old = {fid: f"old {name}" for name, fid in forms.DEFUNCT.items()}
    known = {**forms.LIVE, **old}
    if args.form and args.form not in known:
        sys.exit("not one of the attendance forms (glow/forms.py)")
    wanted = [args.form] if args.form else list(known)
    bad, connections = 0, set()
    uploads = ", ".join(f"upload q{u}" for u in UPLOADS) or "no upload"
    for form_id in wanted:
        label = known[form_id]
        props = client.get(f"/form/{form_id}/properties")
        block = block_of(props)
        if form_id in old:
            print(f"{label}: " + ("STILL CONNECTED to Salesforce - it takes a typed club name; remove "
                                  "the integration or disable the form" if block else
                                  "no Salesforce integration (as wanted)"))
            continue
        if block is None:
            print(f"{label}: NO Salesforce integration - set it up in the form builder (RUNBOOK)")
            bad += 1
        else:
            found = problems(block, client.get(f"/form/{form_id}/questions"))
            connections.add(str(block.get("integrationAccountID")))
            if found:
                bad += 1
                print(f"{label}: connection {block.get('integrationAccountID')} - NOT RIGHT:")
                for line in found:
                    print(f"  - {line}")
            else:
                print(f"{label}: connection {block.get('integrationAccountID')} - ok (one action, 8 fields, "
                      f"Account_Name__c from q{CLUB_NAME}, {uploads})")
        print(f"  other integrations: {', '.join(other_integrations(props)) or 'none'}")
    if len(connections) > 1:
        bad += 1
        print(f"the live forms use {len(connections)} different connections: {sorted(connections)}")
    if bad:
        sys.exit(1)
    print("integration: ok")


if __name__ == "__main__":
    main()
