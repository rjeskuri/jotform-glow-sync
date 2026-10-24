#!/usr/bin/env python3
"""
Offline tests for `tools/sf_backfill.py resend` (ticket #109; found by `make py`'s unittest discovery):
the corrected re-submissions the processor failed whole as "Duplicate" before 2026-10-24 are re-sent
as new batches, so the processor as deployed since merges each into its day's original batch.
Everything here is fictional: clubs, girls and ids are invented. The shared fake org
(test/helpers/fake_org.py) builds the history with its merge rule OFF - the processor that failed
them - and answers the re-sends with it ON.

The contract these tests pin:
- `resend` needs --vpn-off in both modes (it reads Salesforce either way); `--apply` writes, one
  candidate per request, in order; `--since`, `--only <failed batch id>` and `--limit N` narrow it.
- the dry run prints ONE line per candidate holding the Failed batch's Name and Id, the original's
  Name and Id, the club's name, the date, and the counts names ticked / girls to add / new contacts
  expected; a totals line `to re-send: N batches, A girls to add, C new contacts, K clubs`; a line
  per club with its girls to add; and `skipped, <reason>: N` per skip reason, the reasons being
  no_success_original, module_differs, original_not_mergeable (a Partner report or no rows of its own),
  no_names, adds_nobody, own_batch (a batch carrying this tool's marker), already_resent (per ledger,
  whatever the outcome; it wins over the prediction's reasons). A skipped batch is counted, not listed:
  its id is not printed. The dry run is a live read: an open CHECK does not block it, only `--apply`.
- `--only X` refuses, sending nothing, when an earlier candidate of X's club and day is not re-sent
  yet (the queue under `--limit` keeps that order); in the dry run `--only X` shows X's prediction with
  the earlier same-day candidates simulated. `--only` naming a skipped batch, one already re-sent, or
  anything that is not a Failed "Duplicate" batch read (another Failed, a Success, an unknown id) is
  refused in BOTH modes, the message naming the skip reason or saying "not a candidate".
- the ledger is <dir>/resend_ledger.csv (owner-only) with at least the columns RESEND_COLS; a
  candidate's rows go `sending` then `ok` / `CHECK` / `unknown` (a lost read-back: settled by the
  marker before the next `--apply` sends anything); the added rows and created contacts are recorded
  by id in the folder, each on a line that also names its re-send (the new batch's id or the failed
  batch's), and nothing of what was there before - the originals' own rows, the club's earlier
  contacts - is ever recorded; `status` reports the re-sends and what a rollback would remove.
- the fake gives a merged correction's rows the SAME CreatedDate as the correction's batch (Salesforce
  writes them in the same second): the rows added "after" the new batch are read with >=, as the
  existing read-back reads the contacts a batch made.
- never a girl's name and never the text of a status message, printed or written.
"""
import csv
import os
import re
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
from glow.salesforce import PARTNER_RECORD_TYPE            # noqa: E402
from helpers.fake_org import DUPLICATE, FakeOrg as BareOrg   # noqa: E402
from sf_backfill_test import PARTNER, FakeOrg, Harness, account   # noqa: E402

ASPEN, BIRCH, CEDAR = "001000000000000CAA", "001000000000000CBB", "001000000000000CCC"
CLUBS = {ASPEN: "Aspen Club", BIRCH: "Birch Club", CEDAR: "Cedar Club"}      # name order = id order
AMARA, BEATRICE, CHIARA = "Amara Zibblewick", "Beatrice Quornstead", "Chiara Vexholm"
DALIA, ESTHER, FIONA = "Dalia Fennimore", "Esther Wrenlock", "Fiona Thistlebury"
GRETA, HANA, INES = "Greta Morrowind", "Hana Pellingbrook", "Ines Quibblestone"
JANA, KIRA, LENA, MIRA = "Jana Fernsby", "Kira Wobblecastle", "Lena Pumpernick", "Mira Oakhollow"
SURNAMES = [n.split()[1] for n in (AMARA, BEATRICE, CHIARA, DALIA, ESTHER, FIONA, GRETA, HANA, INES, JANA, KIRA,
                                   LENA, MIRA)]
RESEND_LEDGER = "resend_ledger.csv"
RESEND_COLS = {"when_utc", "done_utc", "failed_id", "original_id", "account_id", "account_name", "attendance_date",
               "names", "adds_expected", "contacts_expected", "batch_id", "batch_name", "status", "outcome",
               "rows_added", "contacts_created", "note"}
BODY_FIELDS = {"Account_Name__c", "Attendance_Date__c", "Contact_IDs__c", "Module__c", "Module_Week__c",
               "Module_Year__c", "Creator__c", "enable_fuzzy_matching__c"}
MODULE = "Self Advocacy"


class ResendHarness(Harness):
    def setUp(self):
        super().setUp()
        self.fresh()

    def fresh(self):
        """A fake org of three clubs, an empty back-fill folder, the processor BEFORE the merge rule."""
        self.org = FakeOrg([account(PARTNER, "Example Partner", PARTNER_RECORD_TYPE, None)]
                           + [account(acc_id, name) for acc_id, name in CLUBS.items()])
        self.org.merge_corrections = False
        for name in os.listdir(self.dir):
            os.remove(self.path(name))

    def batch(self, club, date, names, module=MODULE, week=3, year=1, creator="Jotform", **extra):
        """One batch through the fake's processor, as a form submission or a partner's; its record.
        `names`: a list, or the exact text of Contact_IDs__c."""
        body = {"Account_Name__c": CLUBS[club], "Attendance_Date__c": date, "Module__c": module, "Module_Week__c": week,
                "Module_Year__c": year, "Creator__c": creator, "enable_fuzzy_matching__c": False,
                "Contact_IDs__c": names if isinstance(names, str) else ", ".join(names), **extra}
        self.org.insert("Attendance_Batch__c", body)
        self.org.inserts.pop()               # history, not something the tool sent
        return self.org.batches[-1]

    def history(self):
        """The Failed "Duplicate" corrections the old processor left, per club and day (in CreatedDate
        order, which is also the clubs' name and id order and the days' order), and their originals.
        Candidates, in order: C1 (Aspen 09-05: 4 ticked, adds 2, 2 new contacts), C2 (Aspen 09-12: 2 ticked,
        adds 1, a girl with a contact: 0 new), C11 (Cedar 09-05: 2 ticked, adds 1, 1 new), C13 (Cedar 09-05,
        after C11 and C12: 4 ticked, adds 3, 3 new). Skipped: C3 and C12 add nobody, C4 another module,
        C5 a Partner report original, C6 an original without rows, C7 no Success original, C8 no names.
        Not read at all: C9 (Failed, but "Attendance already exists"), C10 (before --since's default)."""
        h = {}
        h["O0"] = self.batch(ASPEN, "2026-09-02", [AMARA])
        h["C10"] = self.batch(ASPEN, "2026-09-02", [AMARA, JANA])
        h["C10"]["CreatedDate"] = "2026-09-03T10:00:00.000+0000"
        h["O1"] = self.batch(ASPEN, "2026-09-05", [AMARA, BEATRICE])
        h["C1"] = self.batch(ASPEN, "2026-09-05", f"{AMARA},{BEATRICE} , {CHIARA},  {KIRA}")     # verbatim text
        h["O2"] = self.batch(ASPEN, "2026-09-12", [AMARA], week=4)
        h["C2"] = self.batch(ASPEN, "2026-09-12", [AMARA, BEATRICE], week=4)
        h["O8"] = self.batch(ASPEN, "2026-09-19", [AMARA], week=5)
        h["C8"] = self.batch(ASPEN, "2026-09-19", "", week=5)
        h["O3"] = self.batch(BIRCH, "2026-09-05", [DALIA])
        h["C3"] = self.batch(BIRCH, "2026-09-05", [DALIA])
        h["O4"] = self.batch(BIRCH, "2026-09-12", [DALIA], week=4)
        h["C4"] = self.batch(BIRCH, "2026-09-12", [DALIA, ESTHER], module="Leadership", week=4)
        h["O7"] = self.batch(BIRCH, "2026-09-19", [DALIA], week=5)
        h["C7"] = self.batch(BIRCH, "2026-09-19", [DALIA, HANA], week=5)
        self.org.batches.remove(h["O7"])     # the original is gone since: rows without a Success batch
        h["O9"] = self.batch(BIRCH, "2026-09-26", [DALIA], week=6)
        self.org.batches.remove(h["O9"])
        h["C9"] = self.batch(BIRCH, "2026-09-26", [DALIA, INES], week=6)       # Failed, not a Duplicate
        h["O11"] = self.batch(CEDAR, "2026-09-05", [FIONA])
        h["C11"] = self.batch(CEDAR, "2026-09-05", [FIONA, GRETA])
        h["C12"] = self.batch(CEDAR, "2026-09-05", [GRETA])
        h["C13"] = self.batch(CEDAR, "2026-09-05", [GRETA, HANA, LENA, MIRA])
        h["O5"] = self.batch(CEDAR, "2026-09-19", [FIONA], week=5, creator="Partner report")
        h["C5"] = self.batch(CEDAR, "2026-09-19", [FIONA, GRETA], week=5)
        h["O6"] = self.batch(CEDAR, "2026-09-26", "", week=6, Girls_Present__c=10)   # a typed aggregate: no rows
        h["C6"] = self.batch(CEDAR, "2026-09-26", [GRETA], week=6)
        for label, record in h.items():      # the fake left the history as this test means it
            status, message = record["Processing_Status__c"], record["Status_Message__c"]
            if label.startswith("O"):
                assert status == "Success", (label, status)
            elif label == "C9":
                assert (status, message[:20]) == ("Failed", "Attendance already e"), (label, status, message)
            else:
                assert (status, message) == ("Failed", DUPLICATE), (label, status, message)
        self.org.merge_corrections = True    # the processor since 2026-10-24 takes the re-sends
        return h

    def hook(self, before=None, after=None):
        """Something that happens around the tool's next inserts (every one of them)."""
        real = self.org.insert

        def insert(sobject, body):
            if before:
                before()
            answer = real(sobject, body)
            if after:
                after()
            return answer
        self.org.insert = insert

    def resend(self, *argv):
        return self.run_tool("resend", "--vpn-off", *argv)

    def apply(self, *argv):
        return self.run_tool("resend", "--apply", "--vpn-off", *argv)

    def ledger(self):
        path = self.path(RESEND_LEDGER)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))

    def states(self):
        return [r["status"] for r in self.ledger()]

    def folder_text(self):
        text = ""
        for name in sorted(os.listdir(self.dir)):
            with open(self.path(name), encoding="utf-8", errors="replace") as fh:
                text += fh.read()
        return text

    def assert_private(self, *texts):
        """Nothing printed and nothing in the folder names a girl or quotes a status message."""
        text = "".join(t or "" for t in texts) + self.folder_text()
        for surname in SURNAMES:
            self.assertNotIn(surname.lower(), text.lower())
        self.assertNotIn(DUPLICATE[:20], text)
        self.assertNotIn("Processed successfully", text)
        for record in self.org.batches:
            self.assertNotIn(f"merged into {record['Id']}", text)

    def line_of(self, out, failed):
        lines = [line for line in out.splitlines() if failed["Name"] in line and failed["Id"] in line]
        self.assertEqual(len(lines), 1, f"{failed['Name']}: one candidate line with its Name and Id expected:\n{out}")
        return lines[0]

    def counts_in(self, line, *remove):
        """The whole numbers on a line once the ids, batch names, dates and `remove` are taken out."""
        for word in remove:
            line = line.replace(word, " ")
        line = re.sub(r"\d{4}-\d{2}-\d{2}T?[\d:Z]*|BATCH-\d+|\b[A-Za-z0-9]{18}\b|\b[A-Za-z0-9]{15}\b", " ", line)
        return {int(t) for t in re.findall(r"\b\d+\b", line)}

    def assert_candidate(self, out, failed, original, club, date, ticked, adds, new):
        line = self.line_of(out, failed)
        for piece in (original["Name"], original["Id"], CLUBS[club], date):
            self.assertIn(piece, line)
        self.assertTrue({ticked, adds, new} <= self.counts_in(line, CLUBS[club]), (line, ticked, adds, new))

    def skip_counts(self, out):
        return {m.group(1): int(m.group(2)) for m in re.finditer(r"skipped, (\w+): (\d+)", out) if int(m.group(2))}

    def rows_of(self, batch):
        return [r for r in self.org.rows if r["Attendance_Batch__c"] == batch["Id"]]


class ResendDryRun(ResendHarness, unittest.TestCase):
    def test_the_dry_run_lists_the_corrections_that_would_add_girls_counts_the_rest_and_sends_nothing(self):
        h = self.history()
        self.org.merge_corrections = False   # a Success whose message starts "Duplicate" is no correction: the
        ox = self.batch(BIRCH, "2026-10-03", [DALIA], week=7)              # Failed condition matters, not the text
        odd = self.batch(BIRCH, "2026-10-03", [DALIA, ESTHER], week=7)
        odd["Processing_Status__c"] = "Success"
        self.org.merge_corrections = True
        out, stop = self.resend()
        self.assertIsNone(stop, stop)
        self.assertNotIn(odd["Id"], out)
        self.assertNotIn(ox["Id"], out)
        self.assert_candidate(out, h["C1"], h["O1"], ASPEN, "2026-09-05", ticked=4, adds=2, new=2)
        self.assert_candidate(out, h["C2"], h["O2"], ASPEN, "2026-09-12", ticked=2, adds=1, new=0)
        self.assert_candidate(out, h["C11"], h["O11"], CEDAR, "2026-09-05", ticked=2, adds=1, new=1)
        self.assert_candidate(out, h["C13"], h["O11"], CEDAR, "2026-09-05", ticked=4, adds=3, new=3)
        for label in ("C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10", "C12"):
            self.assertNotIn(h[label]["Id"], out, label)
        self.assertIn("to re-send: 4 batches, 7 girls to add, 6 new contacts, 2 clubs", out)
        self.assertEqual(self.skip_counts(out), {"adds_nobody": 2, "module_differs": 1, "original_not_mergeable": 2,
                                                 "no_success_original": 1, "no_names": 1})
        for club, total in ((ASPEN, 3), (CEDAR, 4)):
            lines = [line for line in out.splitlines() if CLUBS[club] in line and "BATCH-" not in line]
            self.assertTrue(any(total in self.counts_in(line, CLUBS[club]) for line in lines), (CLUBS[club], total, out))
        self.assertEqual(self.org.inserts, [])
        self.assertFalse(os.path.exists(self.path(RESEND_LEDGER)))
        self.assert_private(out)
        # the Failed batches are found by a condition on the message in SOQL; the message is never selected
        asked = [q for q in self.org.seen if re.search(r"LIKE\s+'Duplicate", q, re.I)]
        self.assertTrue(asked, self.org.seen)
        for q in asked:
            self.assertNotIn("Status_Message__c", q.split(" FROM ")[0], q)
        # --since reaches further back; --only narrows to one failed batch
        out, stop = self.resend("--since", "2026-09-01")
        self.assertIsNone(stop, stop)
        self.assert_candidate(out, h["C10"], h["O0"], ASPEN, "2026-09-02", ticked=2, adds=1, new=1)
        self.assertIn("to re-send: 5 batches, 8 girls to add, 7 new contacts, 2 clubs", out)
        out, stop = self.resend("--only", h["C2"]["Id"])
        self.assertIsNone(stop, stop)
        self.assert_candidate(out, h["C2"], h["O2"], ASPEN, "2026-09-12", ticked=2, adds=1, new=0)
        self.assertNotIn(h["C1"]["Id"], out)
        self.assertEqual(self.org.inserts, [])

    def test_each_skip_reason_turns_on_its_cause_alone(self):
        def pair(reason, skipped):
            """Birch 2026-09-05: an original with one girl, then one correction; `skipped` makes the cause."""
            self.fresh()
            if reason == "no rows of its own":
                original = self.batch(BIRCH, "2026-09-05", "" if skipped else [DALIA], Girls_Present__c=10 if skipped else None)
            else:
                original = self.batch(BIRCH, "2026-09-05", [DALIA], creator="Partner report" if reason == "Partner report"
                                      and skipped else "Jotform")
            names, module = [DALIA, ESTHER], MODULE
            if reason == "module_differs":
                module = "Leadership" if skipped else "SELF ADVOCACY"       # Apex's ==: case ignored
            elif reason == "no_names":
                names = " , ," if skipped else [ESTHER]
            elif reason == "adds_nobody":
                names = [DALIA, "dalia  fennimore"] if skipped else [DALIA, ESTHER]
            correction = self.batch(BIRCH, "2026-09-05", names, module=module)
            if reason == "no_success_original" and skipped:
                self.org.batches.remove(original)
            self.org.merge_corrections = True
            return original, correction

        cases = {"no_success_original": "no_success_original", "module_differs": "module_differs",
                 "Partner report": "original_not_mergeable", "no rows of its own": "original_not_mergeable",
                 "no_names": "no_names", "adds_nobody": "adds_nobody"}
        for reason, printed in cases.items():
            with self.subTest(reason):
                original, correction = pair(reason, skipped=True)
                out, stop = self.resend()
                self.assertIsNone(stop, stop)
                self.assertEqual(self.skip_counts(out), {printed: 1})
                self.assertIn("to re-send: 0 batches, 0 girls to add, 0 new contacts, 0 clubs", out)
                self.assertNotIn(correction["Id"], out)
                self.assertIsNone(self.apply()[1])
                self.assertEqual(self.org.inserts, [])
            with self.subTest(reason + " removed"):
                original, correction = pair(reason, skipped=False)
                out, stop = self.resend()
                self.assertIsNone(stop, stop)
                self.assertEqual(self.skip_counts(out), {})
                self.assert_candidate(out, correction, original, BIRCH, "2026-09-05", ticked=len(correction["Contact_IDs__c"].split(",")),
                                      adds=1, new=1)
                out, stop = self.apply()
                self.assertIsNone(stop, stop)
                self.assertEqual((len(self.org.inserts), self.states()), (1, ["sending", "ok"]))
                self.assertEqual((len(self.rows_of(original)), original["Girls_Present__c"]), (2, 2))
                self.assert_private(out)

    def test_resend_needs_the_vpn_word_in_both_modes_and_only_sends_what_it_is_told(self):
        h = self.history()
        self.org.seen.clear()
        self.assertIn("check that no VPN is on", self.run_tool("resend")[1] or "")
        self.assertIn("check that no VPN is on", self.run_tool("resend", "--apply")[1] or "")
        self.assertEqual((self.org.seen, self.org.inserts), ([], []))
        self.assertEqual(self.run_tool("resend", "--apply", "--vpn-off", "--limit", "0")[1], "2")   # argparse
        self.assertEqual(self.org.inserts, [])
        out, stop = self.apply("--only", h["C2"]["Id"])
        self.assertIsNone(stop, stop)
        self.assertEqual(len(self.org.inserts), 1)
        self.assertIn(h["C2"]["Id"], self.org.inserts[0]["Creator__c"])
        done = self.ledger()[-1]
        self.assertEqual((done["status"], done["failed_id"], done["rows_added"], done["contacts_created"]),
                         ("ok", h["C2"]["Id"], "1", "0"))         # a girl with a contact and no row that day
        self.assertEqual((len(self.rows_of(h["O2"])), h["O2"]["Girls_Present__c"]), (2, 2))
        self.assert_private(out)


class ResendApply(ResendHarness, unittest.TestCase):
    def test_apply_re_sends_a_copy_of_each_candidate_in_order_verifies_it_and_is_safe_to_repeat(self):
        h = self.history()
        before = {acc: len(mine) for acc, mine in self.org.contacts.items()}
        rows_before, batches_before = len(self.org.rows), len(self.org.batches)
        out, stop = self.apply("--limit", "1")
        self.assertIsNone(stop, stop)
        self.assertEqual(len(self.org.inserts), 1)
        copy = self.org.inserts[0]
        self.assertEqual(set(copy), BODY_FIELDS)
        self.assertEqual({k: copy[k] for k in BODY_FIELDS - {"Creator__c"}}, {
            "Account_Name__c": "Aspen Club", "Attendance_Date__c": "2026-09-05",
            "Contact_IDs__c": f"{AMARA},{BEATRICE} , {CHIARA},  {KIRA}", "Module__c": MODULE,
            "Module_Week__c": 3, "Module_Year__c": 1, "enable_fuzzy_matching__c": False})
        self.assertIn(h["C1"]["Id"], copy["Creator__c"])
        self.assertNotEqual(copy["Creator__c"], h["C1"]["Creator__c"])
        new = self.org.batches[-1]
        self.assertEqual((new["Processing_Status__c"], new["Status_Message__c"]), ("Success", f"merged into {h['O1']['Id']}"))
        self.assertEqual((len(self.rows_of(h["O1"])), h["O1"]["Girls_Present__c"]), (4, 4))
        rows = self.ledger()
        self.assertTrue(set(rows[0]) >= RESEND_COLS, set(rows[0]))
        self.assertEqual(self.states(), ["sending", "ok"])
        done = rows[-1]
        self.assertEqual({k: done[k] for k in ("failed_id", "original_id", "account_id", "account_name", "attendance_date",
                                               "names", "adds_expected", "contacts_expected", "batch_id", "batch_name",
                                               "outcome", "rows_added", "contacts_created")},
                         {"failed_id": h["C1"]["Id"], "original_id": h["O1"]["Id"], "account_id": ASPEN,
                          "account_name": "Aspen Club", "attendance_date": "2026-09-05", "names": "4", "adds_expected": "2",
                          "contacts_expected": "2", "batch_id": new["Id"], "batch_name": new["Name"], "outcome": "merged",
                          "rows_added": "2", "contacts_created": "2"})
        self.assertTrue(rows[0]["when_utc"] and done["done_utc"])
        self.assertEqual(self.mode(RESEND_LEDGER), 0o600)
        self.assert_private(out)
        # the rest, in order; one request each
        out, stop = self.apply()
        self.assertIsNone(stop, stop)
        self.assertEqual([next(l for l in ("C1", "C2", "C11", "C13") if h[l]["Id"] in b["Creator__c"]) for b in self.org.inserts],
                         ["C1", "C2", "C11", "C13"])
        self.assertEqual(len({b["Creator__c"] for b in self.org.inserts}), 4)
        self.assertEqual(self.states(), ["sending", "ok"] * 4)
        self.assertEqual([(r["adds_expected"], r["contacts_expected"], r["rows_added"], r["contacts_created"])
                          for r in self.ledger() if r["status"] == "ok"],
                         [("2", "2", "2", "2"), ("1", "0", "1", "0"), ("1", "1", "1", "1"), ("3", "3", "3", "3")])
        # Salesforce afterwards: the originals grew by the adds, the copies hold nothing of their own
        self.assertEqual({acc: len(mine) - before[acc] for acc, mine in self.org.contacts.items()},
                         {PARTNER: 0, ASPEN: 2, BIRCH: 0, CEDAR: 4})
        self.assertEqual(len(self.org.rows) - rows_before, 7)
        self.assertEqual([(len(self.rows_of(h[o])), h[o]["Girls_Present__c"]) for o in ("O1", "O2", "O11")],
                         [(4, 4), (2, 2), (5, 5)])
        copies = self.org.batches[batches_before:]
        self.assertEqual(len(copies), 4)
        for record in copies:
            self.assertEqual((record["Processing_Status__c"], record["Girls_Present__c"], self.rows_of(record)),
                             ("Success", None, []))
        # recorded for a rollback by id: every row added and every contact created
        text = self.folder_text()
        for r in self.org.rows[rows_before:]:
            self.assertIn(r["Id"], text)
        for acc in (ASPEN, CEDAR):
            for cid, _ in list(self.org.contacts[acc].values())[before[acc]:]:
                self.assertIn(cid, text)
        # a second run sends nothing more; the dry run counts them as re-sent
        out, stop = self.apply()
        self.assertIsNone(stop, stop)
        self.assertEqual(len(self.org.inserts), 4)
        out, stop = self.resend()
        self.assertIsNone(stop, stop)
        self.assertIn("to re-send: 0 batches, 0 girls to add, 0 new contacts, 0 clubs", out)
        self.assertEqual(self.skip_counts(out).get("already_resent"), 4)
        # status reports the resend ledger and what a rollback would remove
        out, stop = self.run_tool("status")
        self.assertIsNone(stop, stop)
        lines = [line for line in out.splitlines() if re.search(r"re-?sen[dt]", line, re.I)]
        self.assertTrue(any({4, 7, 6} <= self.counts_in(line) for line in lines), out)
        self.assert_private(out)

    def test_a_name_ticked_twice_with_odd_spacing_or_other_capitals_is_one_girl(self):
        o1 = self.batch(CEDAR, "2026-09-05", [FIONA])
        self.batch(CEDAR, "2026-09-12", [GRETA], week=4)        # Greta has a contact, and no row on 09-05
        ticked = (f"{FIONA}, {FIONA.lower()},{FIONA.upper().replace(' ', '   ')} , GRETA MORROWIND, Greta{chr(0x200B)} Morrowind,"
                  f"{HANA}, {HANA}")
        correction = self.batch(CEDAR, "2026-09-05", ticked)
        self.org.merge_corrections = True
        out, stop = self.resend()
        self.assertIsNone(stop, stop)
        self.assertIn("to re-send: 1 batches, 2 girls to add, 1 new contacts, 1 clubs", out)   # Greta and Hana; Hana new
        self.assertTrue({2, 1} <= self.counts_in(self.line_of(out, correction), "Cedar Club"))
        contacts = len(self.org.contacts[CEDAR])
        out, stop = self.apply()
        self.assertIsNone(stop, stop)
        self.assertEqual(self.org.inserts[0]["Contact_IDs__c"], ticked)        # verbatim: the processor cleans it
        self.assertEqual((len(self.org.contacts[CEDAR]) - contacts, len(self.rows_of(o1)), o1["Girls_Present__c"]), (1, 3, 3))
        self.assertEqual([(r["adds_expected"], r["contacts_expected"], r["rows_added"], r["contacts_created"])
                          for r in self.ledger() if r["status"] == "ok"], [("2", "1", "2", "1")])
        self.assert_private(out)

    def test_a_re_send_that_is_not_as_predicted_is_check_and_stops_the_line(self):
        def stranger():
            self.org.contacts[ASPEN]["somebody new"] = ("003STRANGER00001", self.org.clock())

        def failed():
            self.org.merge_corrections = False

        cases = {
            "comes back Failed": ("before", failed),
            "merged into another batch": ("after", lambda: self.org.batches[-1].__setitem__(
                "Status_Message__c", f"merged into {self.h['O2']['Id']}")),
            "added fewer rows": ("after", lambda: self.org.rows.pop()),
            "added more rows": ("after", lambda: self.org.rows.append(dict(
                self.org.rows[-1], Id="a1mEXTRA00000000001", Contact__c="003STRANGER00001"))),
            "a row of its own": ("after", lambda: self.org.rows.append(dict(
                self.org.rows[-1], Id="a1mOWN0000000000001", Attendance_Batch__c=self.org.batches[-1]["Id"]))),
            "a count of its own": ("after", lambda: self.org.batches[-1].__setitem__("Girls_Present__c", 2.0)),
            "the original's count is not its rows": ("after", lambda: self.h["O1"].__setitem__("Girls_Present__c", 1.0)),
            "the club grew by more": ("after", stranger),
            "the club grew by fewer": ("after", lambda: self.org.contacts[ASPEN].popitem()),
            "landed on another account": ("after", lambda: self.org.batches[-1].__setitem__("Account__c", BIRCH)),
        }
        for name, (when, change) in cases.items():
            with self.subTest(name):
                self.fresh()
                self.h = self.history()
                self.hook(**{when: change})
                out, stop = self.apply()
                self.assertIsNotNone(stop, name)
                self.assertEqual((len(self.org.inserts), self.states()), (1, ["sending", "CHECK"]))
                self.assertEqual(self.ledger()[-1]["failed_id"], self.h["C1"]["Id"])
                self.assert_private(out, stop)
                out, stop = self.apply()      # nothing more until it is dealt with
                self.assertIsNotNone(stop, name)
                self.assertEqual(len(self.org.inserts), 1)
                self.assert_private(out, stop)
                if name == "comes back Failed":   # the Failed copy carries this tool's marker: counted, never re-sent
                    out, stop = self.resend()
                    self.assertIsNone(stop, stop)
                    self.assertEqual((self.skip_counts(out).get("own_batch"), self.skip_counts(out).get("already_resent")), (1, 1))
                    self.assertIn("to re-send: 3 batches, 5 girls to add, 4 new contacts, 2 clubs", out)
                    self.assert_private(out)

    def test_the_live_re_prediction_before_each_send_refuses_when_the_day_changed(self):
        def a_live_correction_got_there_first():
            beatrice = self.org.contacts[ASPEN][BEATRICE.casefold()]
            self.org.rows.append({"Id": "a1mLIVE00000000001", "Attendance_Batch__c": self.h["O2"]["Id"], "Account__c": ASPEN,
                                  "Attendance_Date__c": "2026-09-12", "Contact__c": beatrice[0], "contact_created": beatrice[1],
                                  "CreatedDate": self.org.clock()})
            self.h["O2"]["Girls_Present__c"] = 2

        cases = {"the prediction now adds nobody": a_live_correction_got_there_first,
                 "the original is now a Partner report": lambda: self.h["O2"].__setitem__("Creator__c", "Partner report"),
                 "the original is gone": lambda: self.org.batches.remove(self.h["O2"])}
        for name, change in cases.items():
            with self.subTest(name):
                self.fresh()
                self.h = self.history()
                once = []

                def after(change=change, once=once):
                    if not once:              # after the FIRST re-send only: the second candidate's day changes
                        once.append(1)
                        change()
                self.hook(after=after)
                out, stop = self.apply()
                self.assertIsNotNone(stop, name)
                self.assertEqual(len(self.org.inserts), 1)
                self.assertIn(self.h["C1"]["Id"], self.org.inserts[0]["Creator__c"])
                self.assertEqual(self.states(), ["sending", "ok"])      # the first went; nothing of the second was sent
                self.assert_private(out, stop)

    def test_a_lost_answer_is_settled_by_the_copy_s_own_marker(self):
        h = self.history()
        self.org.lose_answer = True
        out, stop = self.apply("--limit", "1")
        self.assertIsNone(stop, stop)
        self.assertEqual((len(self.org.inserts), self.states()), (1, ["sending", "ok"]))
        self.assertEqual(self.ledger()[-1]["batch_id"], self.org.batches[-1]["Id"])
        self.assertEqual((len(self.rows_of(h["O1"])), h["O1"]["Girls_Present__c"]), (4, 4))
        self.assert_private(out)

    def test_a_read_that_fails_after_the_insert_is_unknown_and_settled_before_the_next_run_sends(self):
        h = self.history()
        real = self.org.insert

        def insert_then_die(sobject, body):
            answer = real(sobject, body)
            self.org.die_after_insert = 1    # the first read-back gets no answer
            return answer
        self.org.insert = insert_then_die
        out, stop = self.apply()
        self.assertIsNotNone(stop)
        self.assertEqual((len(self.org.inserts), self.states()), (1, ["sending", "unknown"]))
        self.assertEqual((self.ledger()[-1]["failed_id"], self.ledger()[-1]["batch_id"]), (h["C1"]["Id"], self.org.batches[-1]["Id"]))
        self.assert_private(out, stop)
        self.org.insert = real
        out, stop = self.apply()             # settled by its marker first, then the rest
        self.assertIsNone(stop, stop)
        self.assertEqual(self.states(), ["sending", "unknown", "ok"] + ["sending", "ok"] * 3)
        settled = self.ledger()[2]
        self.assertEqual((settled["failed_id"], settled["outcome"], settled["rows_added"], settled["contacts_created"]),
                         (h["C1"]["Id"], "merged", "2", "2"))
        self.assertEqual(len(self.org.inserts), 4)
        self.assertEqual([(len(self.rows_of(h[o])), h[o]["Girls_Present__c"]) for o in ("O1", "O2", "O11")],
                         [(4, 4), (2, 2), (5, 5)])
        self.assert_private(out)

    def test_the_rollback_record_holds_only_what_each_re_send_added_tied_to_it(self):
        h = self.history()
        rows_before = [r["Id"] for r in self.org.rows]
        contacts_before = [cid for mine in self.org.contacts.values() for cid, _ in mine.values()]
        batches_before = len(self.org.batches)
        out, stop = self.apply()
        self.assertIsNone(stop, stop)
        text = self.folder_text()
        lines = text.splitlines()
        copies = {b["CreatedDate"]: b for b in self.org.batches[batches_before:]}     # a re-send's rows and contacts
        self.assertEqual(len(copies), 4)                                               # carry its CreatedDate

        def tied(record_id, made):
            """The line recording `record_id` names its re-send: the new batch or the failed one it copies."""
            copy = copies[made]
            failed = next(h[l]["Id"] for l in ("C1", "C2", "C11", "C13") if h[l]["Id"] in copy["Creator__c"])
            return any(record_id in line and (copy["Id"] in line or failed in line) for line in lines)
        added = [r for r in self.org.rows if r["Id"] not in set(rows_before)]
        created = [(cid, made) for mine in self.org.contacts.values() for cid, made in mine.values()
                   if cid not in set(contacts_before)]
        self.assertEqual((len(added), len(created)), (7, 6))
        for r in added:
            self.assertTrue(tied(r["Id"], r["CreatedDate"]), (r["Id"], text))
        for cid, made in created:
            self.assertTrue(tied(cid, made), (cid, text))
        for record_id in rows_before + contacts_before:   # never the originals' own attendance, never the girls there before
            self.assertNotIn(record_id, text)
        self.assert_private(out)

    def test_only_and_limit_keep_a_day_s_corrections_in_order(self):
        h = self.history()
        out, stop = self.resend("--only", h["C13"]["Id"])    # the dry run: C11 and C12 simulated before it
        self.assertIsNone(stop, stop)
        self.assert_candidate(out, h["C13"], h["O11"], CEDAR, "2026-09-05", ticked=4, adds=3, new=3)
        self.assertIn("to re-send: 1 batches, 3 girls to add, 3 new contacts, 1 clubs", out)
        out, stop = self.apply("--only", h["C13"]["Id"])     # C11 of the same club and day is not re-sent yet
        self.assertIsNotNone(stop)
        self.assertEqual((self.org.inserts, self.ledger()), ([], []))
        self.assert_private(out, stop)
        out, stop = self.apply("--limit", "3")               # the queue keeps the order: C13 waits behind C11
        self.assertIsNone(stop, stop)
        self.assertEqual([next(l for l in ("C1", "C2", "C11", "C13") if h[l]["Id"] in b["Creator__c"]) for b in self.org.inserts],
                         ["C1", "C2", "C11"])
        out, stop = self.apply("--only", h["C13"]["Id"])
        self.assertIsNone(stop, stop)
        self.assertEqual((len(self.org.inserts), self.states()), (4, ["sending", "ok"] * 4))
        done = self.ledger()[-1]
        self.assertEqual((done["failed_id"], done["adds_expected"], done["contacts_expected"], done["rows_added"], done["contacts_created"]),
                         (h["C13"]["Id"], "3", "3", "3", "3"))
        self.assertEqual((len(self.rows_of(h["O11"])), h["O11"]["Girls_Present__c"]), (5, 5))
        self.assert_private(out)

    def test_only_names_what_it_cannot_re_send_and_sends_nothing(self):
        h = self.history()
        self.assertIsNone(self.apply("--only", h["C1"]["Id"])[1])
        cases = {h["C4"]["Id"]: "module_differs", h["C3"]["Id"]: "adds_nobody", h["C5"]["Id"]: "original_not_mergeable",
                 h["C6"]["Id"]: "original_not_mergeable", h["C7"]["Id"]: "no_success_original", h["C8"]["Id"]: "no_names",
                 h["C1"]["Id"]: "already_resent", h["C9"]["Id"]: "not a candidate", h["O1"]["Id"]: "not a candidate",
                 "a1l000000000000999": "not a candidate"}
        for only, why in cases.items():
            for run in (self.apply, self.resend):
                with self.subTest((why, run.__name__)):
                    out, stop = run("--only", only)
                    self.assertIsNotNone(stop)
                    self.assertIn(why, stop)
                    self.assert_private(out, stop)
        self.assertEqual((len(self.org.inserts), self.states()), (1, ["sending", "ok"]))


class MergeRuleOfTheFake(unittest.TestCase):
    """The fake's merge rule, as docs/plans/2026-10-22-correction-merge.md states the processor's (the
    tests above rely on it; green by design, it pins the test double, not the tool)."""

    def test_a_correction_merges_into_the_oldest_success_and_the_refusals_stay_duplicate(self):
        org = BareOrg([account(ASPEN, "Aspen Club")])
        body = {"Account_Name__c": "Aspen Club", "Attendance_Date__c": "2026-09-05", "Module__c": MODULE, "Creator__c": "Jotform"}
        org.insert("Attendance_Batch__c", dict(body, Contact_IDs__c=AMARA))
        original = org.batches[0]
        org.insert("Attendance_Batch__c", dict(body, Contact_IDs__c=f"{AMARA}, {BEATRICE},beatrice  quornstead, BEATRICE QUORNSTEAD"))
        merged = org.batches[-1]
        self.assertEqual((merged["Processing_Status__c"], merged["Status_Message__c"], merged["Girls_Present__c"]),
                         ("Success", f"merged into {original['Id']}", None))
        self.assertEqual(([r["Attendance_Batch__c"] for r in org.rows], original["Girls_Present__c"], len(org.contacts[ASPEN])),
                         ([original["Id"]] * 2, 2, 2))
        self.assertEqual(org.rows[-1]["CreatedDate"], merged["CreatedDate"])
        for text, why in ((f"{AMARA}, {BEATRICE}", "adds nobody"), ("", "names nobody"), (" , ", "names nobody")):
            org.insert("Attendance_Batch__c", dict(body, Contact_IDs__c=text))
            self.assertEqual((org.batches[-1]["Processing_Status__c"], org.batches[-1]["Status_Message__c"]),
                             ("Failed", DUPLICATE), why)
        org.insert("Attendance_Batch__c", dict(body, Contact_IDs__c=CHIARA, Module__c="Leadership"))
        self.assertEqual(org.batches[-1]["Status_Message__c"], DUPLICATE)
        org.insert("Attendance_Batch__c", dict(body, Contact_IDs__c=CHIARA, Module__c="self advocacy"))   # a second correction
        self.assertEqual((org.batches[-1]["Status_Message__c"], original["Girls_Present__c"]), (f"merged into {original['Id']}", 3))
        self.assertEqual(len(org.rows), 3)
        original["Creator__c"] = "Partner report"
        org.insert("Attendance_Batch__c", dict(body, Contact_IDs__c=DALIA))
        self.assertEqual(org.batches[-1]["Status_Message__c"], DUPLICATE)
        org.merge_corrections = False
        original["Creator__c"] = "Jotform"
        org.insert("Attendance_Batch__c", dict(body, Contact_IDs__c=DALIA))
        self.assertEqual((org.batches[-1]["Status_Message__c"], len(org.rows)), (DUPLICATE, 3))
        # the generic read answers an explicit-field SOQL as Salesforce would
        found = org.query("SELECT Id, Name FROM Attendance_Batch__c WHERE Processing_Status__c = 'Failed' "
                          "AND Status_Message__c LIKE 'Duplicate%' AND CreatedDate >= 2026-09-07T00:00:00Z ORDER BY CreatedDate, Id")
        self.assertEqual([sorted(r) for r in found][:1], [["Id", "Name"]])
        self.assertEqual(len(found), 6)
        self.assertEqual(org.query(f"SELECT Id, Name FROM Contact WHERE AccountId = '{ASPEN}' AND Contact_Role__c = 'Participant' "
                                   "ORDER BY CreatedDate, Id")[0]["Name"], AMARA.casefold())
        self.assertEqual(org.count(f"SELECT COUNT() FROM Attendance__c WHERE Attendance_Batch__c = '{original['Id']}' "
                                   f"AND CreatedDate >= {merged['CreatedDate'][:19]}Z"), 2)
        with self.assertRaises(AssertionError):
            org.query("SELECT Id, Email FROM Contact")
        with self.assertRaises(AssertionError):
            org.query("SELECT Id FROM Contact WHERE Id = 'x' OR Name = 'y'")


if __name__ == "__main__":
    unittest.main(verbosity=1)
