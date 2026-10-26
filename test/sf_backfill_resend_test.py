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
  no_names, adds_nobody, fuzzy_matching (Enable_Fuzzy_Matching__c true: the processor would match the
  names by edit distance, which the exact-match prediction cannot follow), own_batch (a batch carrying
  this tool's marker), already_resent (per ledger, whatever the outcome; it wins over the prediction's
  reasons). A skipped batch is counted, not listed: its id is not printed, and it is never sent. The dry
  run is a live read: an open CHECK does not block it, only `--apply`.
- `--only X` refuses, sending nothing, when an earlier candidate of X's club and day is not re-sent
  yet (the queue under `--limit` keeps that order); in the dry run `--only X` shows X's prediction with
  the earlier same-day candidates simulated. `--only` naming a skipped batch, one already re-sent, or
  anything that is not a Failed "Duplicate" batch read (another Failed, a Success, an unknown id) is
  refused in BOTH modes: a skipped one with `skipped, <its reason>` (and no other reason), anything else
  with `not a Failed "Duplicate" batch created since <since>` (and no skip reason).
- the ledger is <dir>/resend_ledger.csv (owner-only) with at least the columns RESEND_COLS; a
  candidate's rows go `sending` then `ok` / `CHECK` / `unknown` (a lost read-back: settled by the
  marker before the next `--apply` sends anything); the added rows and created contacts are recorded
  by id in the folder, each on a line that also names its re-send (the new batch's id or the failed
  batch's), and nothing of what was there before - the originals' own rows, the club's earlier
  contacts - is ever recorded; `status` reports the re-sends and what a rollback would remove.
- the fake gives a merged correction's rows the SAME CreatedDate as the correction's batch (Salesforce
  writes them in the same transaction): a copy's rows are the original's rows of the copy's own
  transaction. Rows a LATER correction (a live mentor's, merged after the copy and before its read-back
  or its settling) adds to the same original carry a later CreatedDate: never counted for the copy,
  never recorded for its rollback.
- nothing promises that every write of the processor's transaction carries the copy's CreatedDate to the
  second (review of PR #136): with the fake's `processor_lag` the copy's rows and contacts land after its
  CreatedDate, and the copy's LastModifiedDate (the processor's status update, its last write) after its
  rows. The copy's own are what it added to the original inside [its CreatedDate, its LastModifiedDate]:
  such a copy is `ok` with every row and contact it made in resend_added.csv. When another batch of the
  copy's club and day was created inside that window, rows in it could be that batch's: the copy is CHECK
  and the run stops. A CHECK whose rollback list holds fewer rows than the original grew by (or none)
  says the list may be incomplete (MAY_BE_INCOMPLETE) and does not claim the rows are listed; a CHECK whose
  list is complete keeps `close <failed id> --removed` and does not say so.
- never a girl's name and never the text of a status message, printed or written.
"""
import csv
import datetime
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
sys.path.insert(0, os.path.join(REPO, "test", "fixtures"))
import make_fixture                                          # noqa: E402  the invented name pools

ASPEN, BIRCH, CEDAR = "001000000000000CAA", "001000000000000CBB", "001000000000000CCC"
CLUBS = {ASPEN: "Aspen Club", BIRCH: "Birch Club", CEDAR: "Cedar Club"}      # name order = id order
# girls: invented, from the fixture's pools (CLAUDE.md); 14 distinct, first names in order, initials A to N
(AMARA, BEATRICE, CHIARA, DALIA, ESTHER, FIONA, GRETA, HANA, INES, JANA, KIRA, LENA, MIRA,
 NORA) = [f"{make_fixture.FIRST[i]} {make_fixture.LAST[i]}" for i in range(14)]
SURNAMES = [n.split()[1] for n in (AMARA, BEATRICE, CHIARA, DALIA, ESTHER, FIONA, GRETA, HANA, INES, JANA, KIRA,
                                   LENA, MIRA, NORA)]
REASONS = ("no_success_original", "module_differs", "original_not_mergeable", "no_names", "adds_nobody",
           "fuzzy_matching", "own_batch", "already_resent")
NOT_READ = 'not a Failed "Duplicate" batch created since'
RESEND_LEDGER = "resend_ledger.csv"
RESEND_COLS = {"when_utc", "done_utc", "failed_id", "original_id", "account_id", "account_name", "attendance_date",
               "names", "adds_expected", "contacts_expected", "batch_id", "batch_name", "status", "outcome",
               "rows_added", "contacts_created", "note"}
BODY_FIELDS = {"Account_Name__c", "Attendance_Date__c", "Contact_IDs__c", "Module__c", "Module_Week__c",
               "Module_Year__c", "Creator__c", "enable_fuzzy_matching__c"}
MODULE = "Self Advocacy"
RESEND_ADDED = "resend_added.csv"
MAY_BE_INCOMPLETE = "may be incomplete"      # in a CHECK's message, case ignored, when the rollback list is short
CLAIMS_COMPLETE = "are listed by id in"      # the wording that tells the operator the list is complete


def later(stamp, seconds):
    """A Salesforce datetime `seconds` after `stamp`, in the fake's format."""
    when = datetime.datetime.fromisoformat(stamp[:19]) + datetime.timedelta(seconds=seconds)
    return when.strftime("%Y-%m-%dT%H:%M:%S.000+0000")


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
        assert len({record["Id"] for record in h.values()}) == len(h), "two batches of the history share an id"
        self.org.merge_corrections = True    # the processor since 2026-10-24 takes the re-sends
        return h

    def live_correction(self, club, date, names, week=3):
        """A mentor's correction the processor takes while the tool runs (not something the tool sent):
        straight into the fake, past any hook on its insert."""
        body = {"Account_Name__c": CLUBS[club], "Attendance_Date__c": date, "Module__c": MODULE, "Module_Week__c": week,
                "Module_Year__c": 1, "Creator__c": "Jotform", "enable_fuzzy_matching__c": False,
                "Contact_IDs__c": ", ".join(names)}
        type(self.org).insert(self.org, "Attendance_Batch__c", body)
        self.org.inserts.pop()
        return self.org.batches[-1]

    def assert_refusal(self, stop, why):
        """An `--only` refusal that gives the reason it should: `skipped, <reason>` alone, or NOT_READ."""
        self.assertIsNotNone(stop)
        if why == NOT_READ:
            self.assertIn(NOT_READ, stop)
            self.assertNotIn("skipped,", stop)
            for reason in REASONS:
                self.assertNotIn(reason, stop)
        else:
            self.assertIn(f"skipped, {why}", stop)
            self.assertNotIn(NOT_READ, stop)
            for reason in REASONS:
                if reason != why:
                    self.assertNotIn(reason, stop)

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
                names = [DALIA, DALIA.lower().replace(" ", "  ")] if skipped else [DALIA, ESTHER]
            fuzzy = reason == "fuzzy_matching" and skipped       # the processor would match names by edit distance
            correction = self.batch(BIRCH, "2026-09-05", names, module=module, enable_fuzzy_matching__c=fuzzy)
            if reason == "no_success_original" and skipped:
                self.org.batches.remove(original)
            self.org.merge_corrections = True
            return original, correction

        cases = {"no_success_original": "no_success_original", "module_differs": "module_differs",
                 "Partner report": "original_not_mergeable", "no rows of its own": "original_not_mergeable",
                 "no_names": "no_names", "adds_nobody": "adds_nobody", "fuzzy_matching": "fuzzy_matching"}
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
                for run in (self.resend, self.apply):       # --only on it names this reason, in both modes
                    self.assert_refusal(run("--only", correction["Id"])[1], printed)
                self.assertEqual((self.org.inserts, self.ledger()), ([], []))
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

    def test_a_correction_the_processor_would_match_fuzzily_is_counted_and_never_sent(self):
        h = self.history()
        self.org.merge_corrections = False   # Birch and Cedar on 10-03: each correction would add a girl by exact names
        fuzzy = []
        for club, original, names in ((BIRCH, [DALIA], [DALIA, ESTHER]), (CEDAR, [FIONA], [FIONA, INES, JANA])):
            self.batch(club, "2026-10-03", original, week=7)
            fuzzy.append(self.batch(club, "2026-10-03", names, week=7, enable_fuzzy_matching__c=True))
        self.org.merge_corrections = True
        out, stop = self.resend()
        self.assertIsNone(stop, stop)
        for record in fuzzy:
            self.assertNotIn(record["Id"], out)
        self.assertIn("to re-send: 4 batches, 7 girls to add, 6 new contacts, 2 clubs", out)     # the history's four
        self.assertEqual(self.skip_counts(out), {"adds_nobody": 2, "module_differs": 1, "original_not_mergeable": 2,
                                                 "no_success_original": 1, "no_names": 1, "fuzzy_matching": 2})
        out, stop = self.apply()
        self.assertIsNone(stop, stop)
        self.assertEqual([next((l for l in ("C1", "C2", "C11", "C13") if h[l]["Id"] in b["Creator__c"]), b["Creator__c"])
                          for b in self.org.inserts], ["C1", "C2", "C11", "C13"])
        self.assertFalse({r["failed_id"] for r in self.ledger()} & {record["Id"] for record in fuzzy})
        out, stop = self.resend()            # still counted afterwards, still not a candidate
        self.assertIsNone(stop, stop)
        self.assertEqual((self.skip_counts(out).get("fuzzy_matching"), self.skip_counts(out).get("already_resent")), (2, 4))
        self.assertIn("to re-send: 0 batches, 0 girls to add, 0 new contacts, 0 clubs", out)
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
        self.batch(CEDAR, "2026-09-12", [GRETA], week=4)        # GRETA has a contact, and no row on 09-05
        ticked = (f"{FIONA}, {FIONA.lower()},{FIONA.upper().replace(' ', '   ')} , {GRETA.upper()}, "
                  f"{GRETA.replace(' ', chr(0x200B) + ' ')},"
                  f"{HANA}, {HANA}")
        correction = self.batch(CEDAR, "2026-09-05", ticked)
        self.org.merge_corrections = True
        out, stop = self.resend()
        self.assertIsNone(stop, stop)
        self.assertIn("to re-send: 1 batches, 2 girls to add, 1 new contacts, 1 clubs", out)   # GRETA and HANA; HANA new
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

    def test_rows_a_later_correction_merges_into_the_original_are_not_the_copy_s(self):
        """A live mentor's correction of the copy's club and day, merged by the processor after the copy and
        before its read-back (or its settling by the next run): its row lands on the same original, later.
        It is neither counted for the copy nor recorded for the copy's rollback; the copy is as predicted."""
        def run_with_live_correction(path):
            if path == "read back at once":
                once = []

                def after():
                    if not once:
                        once.append(self.live_correction(ASPEN, "2026-09-05", [NORA]))
                self.hook(after=after)
                out, stop = self.apply("--limit", "1")
                self.assertIsNone(stop, stop)
                self.assertEqual(self.states(), ["sending", "ok"])
                return once[0], out
            real = self.org.insert

            def insert_then_die(sobject, body):
                answer = real(sobject, body)
                self.org.die_after_insert = 1    # the read-back gets no answer: settled by the next run
                return answer
            self.org.insert = insert_then_die
            out, stop = self.apply("--limit", "1")
            self.assertIsNotNone(stop)
            self.assertEqual(self.states(), ["sending", "unknown"])
            self.org.insert = real
            live = self.live_correction(ASPEN, "2026-09-05", [NORA])
            more, stop = self.apply()
            self.assertIsNone(stop, stop)
            self.assertEqual(self.states(), ["sending", "unknown", "ok"] + ["sending", "ok"] * 3)
            return live, out + more

        for path in ("read back at once", "settled by the next run"):
            with self.subTest(path):
                self.fresh()
                h = self.history()
                # a girl the club knows, without a row on 09-05: the live correction adds her, no new contact
                self.org.contacts[ASPEN][NORA.casefold()] = ("003LATE00000000001", "2026-03-01T00:00:00.000+0000")
                live, out = run_with_live_correction(path)
                copy = next(b for b in self.org.batches if h["C1"]["Id"] in str(b["Creator__c"]))
                self.assertEqual(live["Status_Message__c"], f"merged into {h['O1']['Id']}")      # the fake did merge it
                self.assertGreater(live["CreatedDate"], copy["CreatedDate"])
                theirs = [r for r in self.rows_of(h["O1"]) if r["CreatedDate"] == live["CreatedDate"]]
                mine = [r for r in self.rows_of(h["O1"]) if r["CreatedDate"] == copy["CreatedDate"]]
                self.assertEqual((len(theirs), len(mine), len(self.rows_of(h["O1"])), h["O1"]["Girls_Present__c"]),
                                 (1, 2, 5, 5))
                done = [r for r in self.ledger() if r["failed_id"] == h["C1"]["Id"]][-1]
                self.assertEqual((done["status"], done["batch_id"], done["rows_added"], done["contacts_created"]),
                                 ("ok", copy["Id"], "2", "2"))
                text = self.folder_text()
                self.assertNotIn(theirs[0]["Id"], text)                   # never removed by the copy's rollback
                self.assertNotIn(theirs[0]["Contact__c"], text)
                for r in mine:
                    self.assertTrue(any(r["Id"] in line and (copy["Id"] in line or h["C1"]["Id"] in line)
                                        for line in text.splitlines()), (r["Id"], text))
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
        self.org.merge_corrections = False   # a correction that would add a girl, but the processor would match fuzzily
        self.batch(ASPEN, "2026-10-03", [AMARA], week=7)
        fuzzy = self.batch(ASPEN, "2026-10-03", [AMARA, BEATRICE], week=7, enable_fuzzy_matching__c=True)
        self.org.merge_corrections = True
        self.assertIsNone(self.apply("--only", h["C1"]["Id"])[1])
        cases = [("C4", h["C4"]["Id"], "module_differs"), ("C3", h["C3"]["Id"], "adds_nobody"),
                 ("C5", h["C5"]["Id"], "original_not_mergeable"), ("C6", h["C6"]["Id"], "original_not_mergeable"),
                 ("C7", h["C7"]["Id"], "no_success_original"), ("C8", h["C8"]["Id"], "no_names"),
                 ("C1", h["C1"]["Id"], "already_resent"), ("C9", h["C9"]["Id"], NOT_READ),
                 ("O1", h["O1"]["Id"], NOT_READ), ("unknown", "a1l000000000000999", NOT_READ),
                 ("fuzzy", fuzzy["Id"], "fuzzy_matching")]
        self.assertEqual(len({only for _, only, _ in cases}), len(cases))      # each case its own batch
        for label, only, why in cases:
            for run in (self.apply, self.resend):
                with self.subTest((label, why, run.__name__)):
                    out, stop = run("--only", only)
                    self.assert_refusal(stop, why)
                    self.assert_private(out, stop)
        self.assertEqual((len(self.org.inserts), self.states()), (1, ["sending", "ok"]))


class ResendWindow(ResendHarness, unittest.TestCase):
    """A copy's own rows and contacts are those it added inside [its CreatedDate, its LastModifiedDate]."""

    def contact_ids(self):
        return {cid for mine in self.org.contacts.values() for cid, _ in mine.values()}

    def watch(self, after_first=None, die_first=False):
        """Wrap the org's insert: per insert the batch it made and the rows and contacts written during it
        (self.made); `after_first(made)` runs after the first insert, `die_first` loses its read-back."""
        real, self.made = self.org.insert, []

        def insert(sobject, body):
            rows, contacts = {r["Id"] for r in self.org.rows}, self.contact_ids()
            answer = real(sobject, body)
            self.made.append({"batch": self.org.batches[-1], "rows": [r for r in self.org.rows if r["Id"] not in rows],
                              "contacts": self.contact_ids() - contacts})
            if len(self.made) == 1:
                if after_first:
                    after_first(self.made[0])
                if die_first:
                    self.org.die_after_insert = 1
            return answer
        self.org.insert = insert

    def added(self):
        path = self.path(RESEND_ADDED)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))

    def listed_for(self, made, failed_id):
        """(kind, record id) of each resend_added.csv line that names this re-send."""
        return {(r["kind"], r["record_id"]) for r in self.added()
                if r.get("batch_id") == made["batch"]["Id"] or r.get("failed_id") == failed_id}

    def expected(self, made):
        return {("attendance", r["Id"]) for r in made["rows"]} | {("contact", c) for c in made["contacts"]}

    def move(self, rows, made_contacts, at):
        """Stamp `rows` (and the contacts among `made_contacts` they point at) with `at`."""
        for r in rows:
            r["CreatedDate"] = at
            if r["Contact__c"] in made_contacts:
                r["contact_created"] = at
                for mine in self.org.contacts.values():
                    for key, (cid, _) in list(mine.items()):
                        if cid == r["Contact__c"]:
                            mine[key] = (cid, at)

    def other_batch(self, club, date, names, at=None):
        """A batch the processor takes while the tool runs (not something the tool sent); with `at`, it
        and everything written for it carry that moment, as if it ran beside the copy's transaction."""
        rows, contacts = {r["Id"] for r in self.org.rows}, self.contact_ids()
        other = self.live_correction(club, date, names)
        if at:
            other["CreatedDate"] = other["LastModifiedDate"] = at
            self.move([r for r in self.org.rows if r["Id"] not in rows], self.contact_ids() - contacts, at)
        return other

    def assert_check_stops(self, stop):
        self.assertIsNotNone(stop)
        self.assertEqual((len(self.org.inserts), self.states()), (1, ["sending", "CHECK"]))
        again, refused = self.apply()                 # nothing more until it is dealt with
        self.assertIsNotNone(refused)
        self.assertEqual(len(self.org.inserts), 1)
        return again, refused

    def test_a_copy_whose_rows_land_after_its_created_date_is_ok_with_all_its_rows_and_contacts_listed(self):
        labels = ("C1", "C2", "C11", "C13")
        for lag in (1, 3):
            for path in ("read back at once", "settled by the next run"):
                with self.subTest(lag=lag, path=path):
                    self.fresh()
                    h = self.history()
                    self.org.processor_lag = lag
                    self.watch(die_first=path != "read back at once")
                    out, stop = self.apply()
                    if path == "read back at once":
                        self.assertIsNone(stop, stop)
                        self.assertEqual(self.states(), ["sending", "ok"] * 4)
                    else:
                        self.assertIsNotNone(stop)
                        self.assertEqual(self.states(), ["sending", "unknown"])
                        more, stop = self.apply()
                        self.assertIsNone(stop, stop)
                        self.assertEqual(self.states(), ["sending", "unknown", "ok"] + ["sending", "ok"] * 3)
                        out += more
                    self.assertEqual([(len(m["rows"]), len(m["contacts"])) for m in self.made],
                                     [(2, 2), (1, 0), (1, 1), (3, 3)])
                    for label, made in zip(labels, self.made):
                        copy = made["batch"]
                        self.assertIn(h[label]["Id"], copy["Creator__c"])
                        for r in made["rows"]:      # the fake did lag: rows after the copy, its last write after them
                            self.assertTrue(copy["CreatedDate"] < r["CreatedDate"] < copy["LastModifiedDate"],
                                            (copy["CreatedDate"], r["CreatedDate"], copy["LastModifiedDate"]))
                        self.assertEqual(self.listed_for(made, h[label]["Id"]), self.expected(made), label)
                    self.assertEqual({(r["kind"], r["record_id"]) for r in self.added()},
                                     set().union(*(self.expected(m) for m in self.made)))
                    self.assertEqual([(r["failed_id"], r["rows_added"], r["contacts_created"])
                                      for r in self.ledger() if r["status"] == "ok"],
                                     [(h[label]["Id"], str(len(m["rows"])), str(len(m["contacts"])))
                                      for label, m in zip(labels, self.made)])
                    self.assertEqual([(len(self.rows_of(h[o])), h[o]["Girls_Present__c"]) for o in ("O1", "O2", "O11")],
                                     [(4, 4), (2, 2), (5, 5)])
                    self.assert_private(out)

    def test_another_batch_of_the_club_and_day_inside_the_copy_s_window_is_check_and_the_list_may_be_incomplete(self):
        """C1's copy (Aspen 2026-09-05) with the processor lagging 2 ticks: its window is [t, t+4], its rows at
        t+2 and t+3. A batch of the same club and day created at t+1 makes the copy CHECK, whether it merged
        a girl into the same original or added nobody (Failed "Duplicate"); a batch of another club, or of the
        club on another day, inside the window, or one of the same day after the window, does not."""
        cases = {   # name: (club, date, names, inside the window, CHECK)
            "a correction of the day that adds nobody": (ASPEN, "2026-09-05", [AMARA], True, True),
            "a correction of the day merged into the same original": (ASPEN, "2026-09-05", [NORA], True, True),
            "another club's batch": (BIRCH, "2026-10-10", [DALIA], True, False),
            "the club's batch of another day": (ASPEN, "2026-10-10", [AMARA], True, False),
            "a correction of the day after the window": (ASPEN, "2026-09-05", [NORA], False, False),
        }
        for name, (club, date, names, inside, check) in cases.items():
            with self.subTest(name):
                self.fresh()
                h = self.history()
                # a girl the club knows, without a row on 09-05: a correction adds her, no new contact
                self.org.contacts[ASPEN][NORA.casefold()] = ("003LATE00000000001", "2026-03-01T00:00:00.000+0000")
                self.org.processor_lag = 2
                others = []
                self.watch(after_first=lambda made, others=others, club=club, date=date, names=names, inside=inside:
                           others.append(self.other_batch(
                               club, date, names, at=later(made["batch"]["CreatedDate"], 1) if inside else None)))
                out, stop = self.apply("--limit", "1")
                made, other = self.made[0], others[0]
                copy = made["batch"]
                self.assertIn(h["C1"]["Id"], copy["Creator__c"])
                if inside:                          # the test placed it as it says
                    self.assertTrue(copy["CreatedDate"] < other["CreatedDate"] < copy["LastModifiedDate"])
                else:
                    self.assertGreater(other["CreatedDate"], copy["LastModifiedDate"])
                self.assertEqual(other["Status_Message__c"], DUPLICATE if names == [AMARA] and date == "2026-09-05"
                                 else f"merged into {h['O1']['Id']}" if date == "2026-09-05" else "Processed successfully.")
                if check:
                    again, refused = self.assert_check_stops(stop)
                    self.assertIn(MAY_BE_INCOMPLETE, stop.lower())
                    self.assertNotIn(CLAIMS_COMPLETE, stop)
                    self.assert_private(out, stop, again, refused)
                else:
                    self.assertIsNone(stop, stop)
                    self.assertEqual(self.states(), ["sending", "ok"])
                    done = self.ledger()[-1]
                    self.assertEqual((done["rows_added"], done["contacts_created"]), ("2", "2"))
                    self.assertEqual({(r["kind"], r["record_id"]) for r in self.added()}, self.expected(made))
                    self.assert_private(out)

    def test_a_check_whose_rollback_list_is_short_of_the_original_s_growth_says_it_may_be_incomplete(self):
        """C1's copy adds 2 rows (2 new contacts) to O1. Rows stamped after the copy's last write fall outside
        its window: the list holds fewer than the original grew by, and the CHECK says it may be incomplete."""
        def every_row_late(made):
            for i, r in enumerate(made["rows"]):
                self.move([r], made["contacts"], later(made["batch"]["LastModifiedDate"], 5 + i))

        def last_row_late(made):
            self.move(made["rows"][-1:], made["contacts"], later(made["batch"]["LastModifiedDate"], 5))

        for lag in (0, 1):
            for name, change, inside in (("every row after its last write", every_row_late, 0),
                                         ("its last row after its last write", last_row_late, 1)):
                with self.subTest(lag=lag, case=name):
                    self.fresh()
                    h = self.history()
                    self.org.processor_lag = lag
                    self.watch(after_first=change)
                    out, stop = self.apply()
                    made = self.made[0]
                    self.assertEqual((len(made["rows"]), len(self.rows_of(h["O1"])), h["O1"]["Girls_Present__c"]), (2, 4, 4))
                    self.assertEqual(sum(1 for r in made["rows"] if r["CreatedDate"] <= made["batch"]["LastModifiedDate"]),
                                     inside)
                    again, refused = self.assert_check_stops(stop)
                    self.assertIn(MAY_BE_INCOMPLETE, stop.lower())
                    self.assertNotIn(CLAIMS_COMPLETE, stop)
                    self.assertIn(h["C1"]["Id"], stop)
                    self.assertTrue({("attendance", r["Id"]) for r in made["rows"][:inside]}
                                    <= self.listed_for(made, h["C1"]["Id"]))
                    self.assert_private(out, stop, again, refused)

    def test_a_check_whose_rollback_list_is_complete_keeps_close_removed_and_does_not_say_incomplete(self):
        cases = {"a count of its own": lambda made: made["batch"].__setitem__("Girls_Present__c", 2.0),
                 "the original's count is not its rows": lambda made: self.h["O1"].__setitem__("Girls_Present__c", 1.0)}
        for lag in (0, 2):
            for name, change in cases.items():
                with self.subTest(lag=lag, case=name):
                    self.fresh()
                    self.h = self.history()
                    self.org.processor_lag = lag
                    self.watch(after_first=change)
                    out, stop = self.apply()
                    again, refused = self.assert_check_stops(stop)
                    made, fid = self.made[0], self.h["C1"]["Id"]
                    self.assertEqual((len(made["rows"]), len(made["contacts"])), (2, 2))
                    self.assertEqual(self.listed_for(made, fid), self.expected(made))
                    self.assertNotIn(MAY_BE_INCOMPLETE, stop.lower())
                    self.assertIn(f"close {fid} --removed", stop)
                    self.assert_private(out, stop, again, refused)


class MergeRuleOfTheFake(unittest.TestCase):
    """The fake's merge rule, as docs/plans/2026-10-22-correction-merge.md states the processor's (the
    tests above rely on it; green by design, it pins the test double, not the tool)."""

    def test_a_correction_merges_into_the_oldest_success_and_the_refusals_stay_duplicate(self):
        org = BareOrg([account(ASPEN, "Aspen Club")])
        body = {"Account_Name__c": "Aspen Club", "Attendance_Date__c": "2026-09-05", "Module__c": MODULE, "Creator__c": "Jotform"}
        org.insert("Attendance_Batch__c", dict(body, Contact_IDs__c=AMARA))
        original = org.batches[0]
        org.insert("Attendance_Batch__c", dict(body, Contact_IDs__c=f"{AMARA}, {BEATRICE},{BEATRICE.lower().replace(' ', '  ')}, {BEATRICE.upper()}"))
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

    def test_with_a_processor_lag_rows_and_contacts_land_inside_the_batch_s_window(self):
        org = BareOrg([account(ASPEN, "Aspen Club")])
        body = {"Account_Name__c": "Aspen Club", "Attendance_Date__c": "2026-09-05", "Module__c": MODULE, "Creator__c": "Jotform"}
        org.insert("Attendance_Batch__c", dict(body, Contact_IDs__c=AMARA))
        first = org.batches[0]
        self.assertEqual(first["LastModifiedDate"], first["CreatedDate"])        # no lag: one moment
        org.processor_lag = 2
        org.insert("Attendance_Batch__c", dict(body, Contact_IDs__c=f"{AMARA}, {BEATRICE}, {CHIARA}"))
        merged = org.batches[-1]
        late = org.rows[1:]
        self.assertEqual([r["Attendance_Batch__c"] for r in late], [first["Id"]] * 2)
        self.assertEqual([r["CreatedDate"] for r in late], [later(merged["CreatedDate"], 2), later(merged["CreatedDate"], 3)])
        self.assertEqual([r["contact_created"] for r in late], [r["CreatedDate"] for r in late])
        self.assertEqual(merged["LastModifiedDate"], later(merged["CreatedDate"], 4))
        self.assertEqual(first["LastModifiedDate"], merged["LastModifiedDate"])
        found = org.query(f"SELECT Id FROM Attendance__c WHERE Attendance_Batch__c = '{first['Id']}' AND CreatedDate >= "
                          f"{merged['CreatedDate'][:19]}Z AND CreatedDate <= {merged['LastModifiedDate'][:19]}Z")
        self.assertEqual([r["Id"] for r in found], [r["Id"] for r in late])
        self.assertEqual(org.query(f"SELECT LastModifiedDate FROM Attendance_Batch__c WHERE Id = '{merged['Id']}'")[0]
                         ["LastModifiedDate"], merged["LastModifiedDate"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
