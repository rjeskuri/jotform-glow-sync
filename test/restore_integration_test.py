#!/usr/bin/env python3
"""
Offline tests for tools/restore_integration.py (imported by test/python_test.py). A fake
client stands in for Jotform; nothing here is a real connection id.
"""
import contextlib
import copy
import io
import json
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import restore_integration as ri      # noqa: E402
from glow import forms as glow_forms  # noqa: E402

US = glow_forms.REGIONALS["U.S"]
TEMPLATE = glow_forms.TEMPLATE


def block(club_source="444", account="1234567"):
    fields = dict(ri.MAPPING, Account_Name__c=club_source)
    action = {"id": "1", "order": "1", "action": "createRecord", "upsert": "create",
              "object": "Attendance_Batch__c", "uploadFields": ["19"],
              "fieldMapping": [{"matchId": str(n), "targetId": t, "metadata": {},
                                "source": {"type": "question", "value": q}}
                               for n, (t, q) in enumerate(fields.items())]}
    return {"actionMap": json.dumps([action]), "editBehavior": "update", "integrationAccountID": account}


class FakeJotform:
    def __init__(self, template_block, target=None, apply=True, store=True):
        self.props = {TEMPLATE: {"integrations": {"salesforceV2": template_block} if template_block else []},
                      US: {"integrations": target if target is not None else []}}
        self.apply, self.store, self.puts = apply, store, []

    def get(self, path):
        _, _, form_id, part = path.split("/")
        if part == "questions":
            return {qid: {"name": name} for qid, name in ri.QUESTIONS.items()}
        return copy.deepcopy(self.props[form_id])

    def put_json(self, path, payload, label):
        self.puts.append(payload)
        if self.apply and self.store:
            self.props[path.split("/")[2]]["integrations"] = copy.deepcopy(payload["properties"]["integrations"])


def run(client, *argv):
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            ri.main(list(argv), client=client)
    except SystemExit as stop:
        return out.getvalue(), str(stop.code)
    return out.getvalue(), None


class RestoreIntegration(unittest.TestCase):
    def test_a_dry_run_writes_nothing_and_says_what_it_would_write(self):
        client = FakeJotform(block())
        out, stop = run(client, "--form", US)
        self.assertIsNone(stop)
        self.assertEqual(client.puts, [])
        self.assertIn("Account_Name__c <- question 5 (the template has question 444)", out)
        self.assertIn("DRY RUN: would write the integration to U.S", out)

    def test_apply_writes_the_template_block_with_question_5_and_re_reads(self):
        client = FakeJotform(block())
        out, stop = run(client, "--form", US, "--apply")
        self.assertIsNone(stop)
        sent = client.puts[0]["properties"]["integrations"]["salesforceV2"]
        self.assertEqual(ri.mapping_of(sent), ri.MAPPING)
        self.assertEqual((sent["integrationAccountID"], sent["editBehavior"]), ("1234567", "update"))
        self.assertIn("verified: U.S carries the integration", out)
        out, stop = run(client, "--form", US, "--apply")                 # a second run has nothing to do
        self.assertIn("nothing to do", out)
        self.assertEqual(len(client.puts), 1)

    def test_the_template_itself_is_corrected_from_the_picker_to_question_5(self):
        client = FakeJotform(block())
        client.props[US] = client.props[TEMPLATE]                        # not used; the template is the target
        out, stop = run(client, "--form", TEMPLATE, "--apply")
        self.assertIsNone(stop)
        self.assertEqual(ri.mapping_of(client.props[TEMPLATE]["integrations"]["salesforceV2"])["Account_Name__c"], "5")

    def test_a_write_that_is_not_stored_as_sent_fails(self):
        out, stop = run(FakeJotform(block(), store=False), "--form", US, "--apply")
        self.assertEqual(stop, "2")
        self.assertIn("the re-read differs", out)

    def test_refusals(self):
        other_field = json.loads(block()["actionMap"])
        other_field[0]["fieldMapping"][1]["source"]["value"] = "99"
        cases = {
            "an old form is never reconnected": (FakeJotform(block()), glow_forms.DEFUNCT["Africa"]),
            "not one of the five attendance forms": (FakeJotform(block()), "123"),
            "the template has no Salesforce integration": (FakeJotform(None), US),
            "not the known one": (FakeJotform(dict(block(), actionMap=json.dumps(other_field))), US),
            "no connected Salesforce account": (FakeJotform(block(account="")), US),
            "carries another integration": (FakeJotform(block(), target={"slack": {"a": 1}}), US),
        }
        for message, (client, form_id) in cases.items():
            with self.subTest(message):
                out, stop = run(client, "--form", form_id, "--apply")
                self.assertIn(message, stop)
                self.assertEqual(client.puts, [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
