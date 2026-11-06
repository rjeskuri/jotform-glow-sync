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
connection. A ninth field, Session_Notes__c (ticket #106), reads the form's own question named
sessionNotes (its qid differs per form): right when present, and required (NOTES_MAPPING_WANTED,
True since 2026-10-26) on every live form but one whose `status` property is exactly DISABLED
(the U.S form today): unmapped, that one is right and its ok line says the notes are not wanted;
a notes mapping it does carry, and everything else about it, is checked as on any form. For
every live form it also lists the other integration blocks the form carries
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
from glow.cli import api_key, run      # noqa: E402
from glow.jotform import Client         # noqa: E402
from glow.layout import NOTES_FIX, NOTES_NAME, notes_fields   # noqa: E402
from glow.sync import (                 # noqa: E402
    CLUB_NAME, CONTACT_IDS, CREATOR, DATE, ENABLE_FUZZY, MODULE_ID, PHOTO, PICKER_NAME, WEEK_ID, YEAR_ID)

KEY = "salesforceV2"
# the one action the forms have carried since the pilot: Salesforce field -> question id
MAPPING = {"Account_Name__c": CLUB_NAME, "Attendance_Date__c": DATE, "Contact_IDs__c": CONTACT_IDS,
           "Module__c": MODULE_ID, "Module_Week__c": WEEK_ID, "Module_Year__c": YEAR_ID,
           "Creator__c": CREATOR, "enable_fuzzy_matching__c": ENABLE_FUZZY}
# no upload: the Group Photo (q19) left the mapping on 2026-10-01 (the CEO: no photo in
# Salesforce, DECISIONS) and is never re-mapped without the CEO's word
UPLOADS = []
# the questions behind it, by their field names (the photo must still exist: it is required)
QUESTIONS = {CLUB_NAME: "clubName", DATE: "date", CONTACT_IDS: "contact_ids", MODULE_ID: "module_id",
             WEEK_ID: "week_id", YEAR_ID: "year_id", CREATOR: "creator", ENABLE_FUZZY: "enableFuzzy",
             PHOTO: "photo"}
# the session notes (ticket #106): Session_Notes__c from the question named NOTES_NAME, found by
# its name like the Club picker - its qid differs per form. Ryan maps it in each live form's
# builder (the API cannot). A present mapping must always read the form's own sessionNotes. The
# rollout ended 2026-10-26 (docs/plans/2026-10-26-session-notes-salesforce.md): Ryan mapped the
# template (q489), Africa (q476), Asia (q457) and Latin America (q454) in the builder; the U.S
# form is DISABLED and was left unmapped on his word ("Skip U.S: it is disabled"). So the switch
# is True: a live form without the mapping is NOT RIGHT, exit 1 - unless its `status` is exactly
# DISABLED (re-enabling U.S: map q446 first, RUNBOOK "Session notes in Salesforce"). False is the
# rollback: a present mapping is still checked, a form without one is right.
NOTES_FIELD = "Session_Notes__c"
NOTES_MAPPING_WANTED = True
# the `status` property of a switched-off form (tools/disable_form.py). Only this exact value
# excuses a live form from the notes mapping: any other (ENABLED, none, DELETED, `disabled`) is an
# enabled form's - an unknown state never excuses one
DISABLED = "DISABLED"
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


def actions_of(block):
    """The block's actions (its actionMap: a JSON string, or the list itself)."""
    raw = block.get("actionMap")
    return json.loads(raw) if isinstance(raw, str) else raw


def from_questions(act):
    """{Salesforce field: qid} of the action's fields read from a question."""
    return {f.get("targetId"): str((f.get("source") or {}).get("value"))
            for f in act.get("fieldMapping") or [] if (f.get("source") or {}).get("type") == "question"}


def problems(block, questions, disabled=False):
    """What is wrong with a form's Salesforce integration ([] = right). `disabled`: the form's
    status is DISABLED, so it needs no Session_Notes__c mapping (one it carries is checked)."""
    acts = actions_of(block)
    if not block.get("integrationAccountID"):
        return ["no connected Salesforce account"]
    if not isinstance(acts, list) or len(acts) != 1:
        return [f"{len(acts) if isinstance(acts, list) else 0} actions (want exactly one)"]
    act, out = acts[0], []
    if (act.get("action"), act.get("upsert"), act.get("object")) != ("createRecord", "create",
                                                                     "Attendance_Batch__c"):
        out.append(f"the action is {act.get('action')}/{act.get('upsert')} on {act.get('object')}, "
                   "not 'create a new record' of Attendance_Batch__c")
    have = from_questions(act)
    names = {qid: (q.get("name"), q.get("text")) for qid, q in questions.items()}
    for field, qid in MAPPING.items():
        got = have.get(field)
        if got == qid:
            continue
        what = "is not mapped from a question" if got is None else f"reads q{got}"
        if got is not None and names.get(got, (None,))[0] == PICKER_NAME:
            what += " (the Club picker)"
        out.append(f"{field} {what}; it must read q{qid} ({QUESTIONS[qid]})")
    # Session_Notes__c: checked once it is mapped or wanted (a DISABLED form's only when mapped),
    # against the form's one question named sessionNotes; two of them is then a problem, not a
    # guess (form_status flags them anyway)
    got, notes = have.get(NOTES_FIELD), [str(q["qid"]) for q in notes_fields(questions)]
    if (got is not None or (NOTES_MAPPING_WANTED and not disabled)) and notes != [got]:
        what = "is not mapped from a question" if got is None else f"reads q{got}"
        if len(notes) == 1:
            must = f"q{notes[0]} ({NOTES_NAME})"
        elif notes:
            must = (f"the one question named {NOTES_NAME}, and the form has {len(notes)} "
                    f"({', '.join('q' + n for n in notes)}) - delete the extra one in the builder")
        else:
            must = f"the question named {NOTES_NAME}, and the form has none - run {NOTES_FIX}"
        out.append(f"{NOTES_FIELD} {what}; it must read {must}")
    out += [f"{f} is mapped too (leave it unmapped)"
            for f in sorted(set(have) - set(MAPPING) - {NOTES_FIELD})]
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
            disabled = props.get("status") == DISABLED     # the exact value, by ==
            found = problems(block, client.get(f"/form/{form_id}/questions"), disabled)
            connections.add(str(block.get("integrationAccountID")))
            if found:
                bad += 1
                print(f"{label}: connection {block.get('integrationAccountID')} - NOT RIGHT:")
                for line in found:
                    print(f"  - {line}")
            else:   # right, so a notes mapping reads the form's own sessionNotes
                notes = from_questions(actions_of(block)[0]).get(NOTES_FIELD)
                if notes:
                    said = f"{NOTES_FIELD} from q{notes}, "
                elif NOTES_MAPPING_WANTED and disabled:
                    said = f"{NOTES_FIELD} not wanted (form {DISABLED}), "
                else:
                    said = ""
                print(f"{label}: connection {block.get('integrationAccountID')} - ok (one action, "
                      f"{len(MAPPING) + bool(notes)} fields, Account_Name__c from q{CLUB_NAME}, "
                      f"{said}{uploads})")
        print(f"  other integrations: {', '.join(other_integrations(props)) or 'none'}")
    if len(connections) > 1:
        bad += 1
        print(f"the live forms use {len(connections)} different connections: {sorted(connections)}")
    if bad:
        sys.exit(1)
    print("integration: ok")


if __name__ == "__main__":
    run(main)
