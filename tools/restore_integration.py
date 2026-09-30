#!/usr/bin/env python3
"""Put the Salesforce integration back on one attendance form
(docs/plans/2026-09-30-salesforce-reconnect.md).

It copies the template's LIVE Salesforce integration - the connection Ryan authorised in the
form builder - to the form, with Account_Name__c read from question 5 (the hidden Club Name
field every form shares), never from the Club picker. It refuses any mapping but the known
one, merges into the form's `integrations` property, and re-reads after the write.

    python3 tools/restore_integration.py --form <id>            # dry run: what would be written
    python3 tools/restore_integration.py --form <id> --apply    # write, re-read, compare

Back up first (`backup_forms.py --form <id>`). The key comes from JOTFORM_API_KEY.
"""
import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow import forms                  # noqa: E402
from glow.jotform import Client         # noqa: E402
from glow.sync import CLUB_NAME         # noqa: E402

KEY = "salesforceV2"
# the one action the forms have carried since the pilot: Salesforce field -> question id
MAPPING = {"Account_Name__c": CLUB_NAME, "Attendance_Date__c": "17", "Contact_IDs__c": "18",
           "Module__c": "98", "Module_Week__c": "100", "Module_Year__c": "102",
           "Creator__c": "105", "enable_fuzzy_matching__c": "109"}
UPLOADS = ["19"]
# the questions behind it: every form must have them under these names
QUESTIONS = {CLUB_NAME: "clubName", "17": "date", "18": "contact_ids", "98": "module_id",
             "100": "week_id", "102": "year_id", "105": "creator", "109": "enableFuzzy",
             "19": "photo"}


def integrations(props):
    """The form's `integrations` property as a dict (Jotform returns [] when there is none)."""
    value = props.get("integrations") or {}
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        sys.exit(f"the form's integrations property is a {type(value).__name__} with content: "
                 "look at it in the builder before writing")
    return value


def actions(block):
    raw = block.get("actionMap")
    return json.loads(raw) if isinstance(raw, str) else raw


def mapping_of(block):
    """{Salesforce field: question id} of a salesforceV2 block's single action, or a refusal."""
    acts = actions(block)
    if not isinstance(acts, list) or len(acts) != 1:
        sys.exit("the Salesforce integration does not have exactly one action: set it up in the "
                 "builder as the plan says")
    act = acts[0]
    if (act.get("action"), act.get("upsert"), act.get("object")) != ("createRecord", "create",
                                                                     "Attendance_Batch__c"):
        sys.exit("the action is not 'create a new record' of Attendance_Batch__c")
    if any((f.get("source") or {}).get("type") != "question" for f in act.get("fieldMapping") or []):
        sys.exit("a field is not mapped from a question")
    if list(act.get("uploadFields") or []) != UPLOADS:
        sys.exit(f"the upload field is {act.get('uploadFields')}, not the Group Photo (q{UPLOADS[0]})")
    return {f["targetId"]: str(f["source"]["value"]) for f in act["fieldMapping"]}


def wanted_block(template_block):
    """The template's live block with Account_Name__c read from question 5."""
    if not template_block.get("integrationAccountID"):
        sys.exit("the template has no connected Salesforce account: reconnect it in the builder first")
    have = mapping_of(template_block)
    other = {k: v for k, v in have.items() if k != "Account_Name__c"}
    if set(have) != set(MAPPING) or other != {k: v for k, v in MAPPING.items() if k != "Account_Name__c"}:
        sys.exit(f"the template's mapping is not the known one: {have} - fix it in the builder")
    acts = actions(template_block)
    for f in acts[0]["fieldMapping"]:
        if f["targetId"] == "Account_Name__c":
            f["source"]["value"] = CLUB_NAME
    block = dict(template_block)
    block["actionMap"] = json.dumps(acts, separators=(",", ":"))
    return block, have["Account_Name__c"]


def same(block, wanted):
    """Whether a stored block is the wanted one (the action compared as data, not as text)."""
    if not isinstance(block, dict):
        return False
    rest = {k: v for k, v in block.items() if k != "actionMap"}
    return rest == {k: v for k, v in wanted.items() if k != "actionMap"} and actions(block) == actions(wanted)


def plan(client, form_id, template_id):
    if form_id in forms.DEFUNCT.values():
        sys.exit("an old form is never reconnected: it stays without the integration")
    if form_id not in forms.LIVE:
        sys.exit("not one of the five attendance forms (glow/forms.py)")
    template_block = integrations(client.get(f"/form/{template_id}/properties")).get(KEY)
    if not isinstance(template_block, dict):
        sys.exit("the template has no Salesforce integration: reconnect it in the builder first")
    wanted, template_source = wanted_block(template_block)
    questions = client.get(f"/form/{form_id}/questions")
    missing = [f"q{qid} ({name})" for qid, name in QUESTIONS.items()
               if (questions.get(qid) or {}).get("name") != name]
    if missing:
        sys.exit(f"the form lacks the mapped questions under their names: {missing}")
    props = client.get(f"/form/{form_id}/properties")
    current = integrations(props)
    unknown = sorted(k for k in current if k != KEY)
    if unknown:
        sys.exit(f"the form carries another integration ({unknown}): not overwriting it")
    return current, wanted, template_source


def main(argv=None, client=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--form", required=True, help="the form to write (the template or a regional form)")
    ap.add_argument("--template", default=forms.TEMPLATE, help="the form whose live integration is copied")
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    args = ap.parse_args(argv)
    if client is None:
        key = os.environ.get("JOTFORM_API_KEY")
        if not key:
            sys.exit("JOTFORM_API_KEY is not in the environment (RUNBOOK, Credentials)")
        client = Client(key, apply=args.apply)
    current, wanted, template_source = plan(client, args.form, args.template)
    label = forms.LIVE[args.form]
    have = current.get(KEY)
    print(f"{label}: connection {wanted['integrationAccountID']} (from the template); "
          f"Account_Name__c <- question {CLUB_NAME}"
          + (f" (the template has question {template_source})" if template_source != CLUB_NAME else ""))
    for field, qid in MAPPING.items():
        print(f"  {field:<26} <- q{qid} {QUESTIONS[qid]}")
    print(f"  file upload                <- q{UPLOADS[0]} {QUESTIONS[UPLOADS[0]]}")
    if same(have, wanted):
        print(f"{label}: nothing to do - the form has exactly this integration")
        return
    print(f"{label}: the form now has " + ("no Salesforce integration" if not have else
          f"another one (connection {have.get('integrationAccountID')}, {mapping_of(have)})"))
    if not args.apply:
        print(f"DRY RUN: would write the integration to {label} (use --apply; back up first)")
        return
    client.put_json(f"/form/{args.form}/properties", {"properties": {"integrations": {KEY: wanted}}},
                    f"PUT integrations ({label})")
    stored = integrations(client.get(f"/form/{args.form}/properties")).get(KEY)
    if not same(stored, wanted):
        print(f"{label}: the re-read differs from what was sent:")
        print("  stored:", json.dumps(stored, ensure_ascii=False)[:600])
        sys.exit(2)
    print(f"verified: {label} carries the integration, Account_Name__c read from question {CLUB_NAME}")


if __name__ == "__main__":
    main()
