#!/usr/bin/env python3
"""
Offline tests for tools/integration_status.py (imported by test/python_test.py). A fake
client stands in for Jotform; nothing here is a real connection id.
"""
import contextlib
import io
import json
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import integration_status as ist      # noqa: E402
from glow import forms as glow_forms  # noqa: E402
from glow.sync import PICKER_NAME     # noqa: E402

US = glow_forms.REGIONALS["U.S"]
OLD = glow_forms.DEFUNCT["Africa"]


def block(account="1234567", uploads=("19",), **change):
    fields = dict(ist.MAPPING, **change)
    action = {"id": "1", "order": "1", "action": "createRecord", "upsert": "create",
              "object": "Attendance_Batch__c", "uploadFields": list(uploads),
              "fieldMapping": [{"matchId": str(n), "targetId": t, "metadata": {},
                                "source": {"type": "question", "value": q}}
                               for n, (t, q) in enumerate(fields.items()) if q is not None]}
    return {"actionMap": json.dumps([action]), "editBehavior": "update", "integrationAccountID": account}


class FakeJotform:
    def __init__(self, blocks):
        self.blocks = blocks

    def get(self, path):
        _, _, form_id, part = path.split("/")
        if part == "questions":
            questions = {qid: {"name": name} for qid, name in ist.QUESTIONS.items()}
            questions["444"] = {"name": PICKER_NAME}
            return questions
        found = self.blocks.get(form_id)
        return {"integrations": {"salesforceV2": found} if found else []}


def run(blocks, *argv):
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            ist.main(list(argv), client=FakeJotform(blocks))
    except SystemExit as stop:
        return out.getvalue(), stop.code
    return out.getvalue(), None


class IntegrationStatus(unittest.TestCase):
    def test_the_known_mapping_is_ok(self):
        out, stop = run({US: block()}, "--form", US)
        self.assertIsNone(stop)
        self.assertIn("U.S: connection 1234567 - ok", out)
        self.assertIn("integration: ok", out)

    def test_the_club_picker_as_the_source_of_the_account_name_is_named(self):
        out, stop = run({US: block(Account_Name__c="444")}, "--form", US)
        self.assertEqual(stop, 1)
        self.assertIn("Account_Name__c reads q444 (the Club picker); it must read q5 (clubName)", out)

    def test_every_other_difference_is_named(self):
        cases = {
            "NO Salesforce integration": None,
            "Module__c reads q99; it must read q98": block(Module__c="99"),
            "Creator__c is not mapped from a question": block(Creator__c=None),
            "Processing_Status__c is mapped too": block(Processing_Status__c="17"),
            "the upload field is []": block(uploads=()),
            "no connected Salesforce account": block(account=""),
        }
        for message, found in cases.items():
            with self.subTest(message):
                out, stop = run({US: found}, "--form", US)
                self.assertEqual(stop, 1)
                self.assertIn(message, out)

    def test_all_forms_one_connection_and_the_old_forms_stay_without(self):
        live = {fid: block() for fid in glow_forms.LIVE}
        out, stop = run(live)
        self.assertIsNone(stop)
        self.assertEqual(out.count("no Salesforce integration (as wanted)"), len(glow_forms.DEFUNCT))
        out, stop = run(dict(live, **{US: block(account="7654321")}))
        self.assertEqual(stop, 1)
        self.assertIn("2 different connections", out)
        out, stop = run(dict(live, **{OLD: block()}))
        self.assertIn("old Africa: STILL CONNECTED", out)


if __name__ == "__main__":
    unittest.main(verbosity=1)
