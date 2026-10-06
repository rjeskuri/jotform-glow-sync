#!/usr/bin/env python3
"""
Offline tests for tools/sf_girls_present.py (imported by test/python_test.py, so `make py` runs
them). Everything here is fictional: batch ids, names and counts are invented. The fake org holds
six batches - live Jotform ones with and without rows, a back-filled one, a Failed duplicate, a
typed partner aggregate and one the processor already counted - and answers the tool's SOQL shapes.
"""
import contextlib
import copy
import io
import os
import re
import stat
import sys
import tempfile
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import sf_girls_present as gp                              # noqa: E402
from sf_backfill_test import FakeOrg                       # noqa: E402


def batch(n, status="Success", creator="Jotform", value=None):
    return {"Id": f"a1l{n:015d}", "Name": f"BATCH-{n:06d}", "Processing_Status__c": status, "Creator__c": creator,
            "Girls_Present__c": value}


def rows(n, count):
    return [{"Id": f"a1m{n:03d}{i:012d}", "Attendance_Batch__c": f"a1l{n:015d}"} for i in range(count)]


class GirlsOrg(FakeOrg):
    """The shared fake org (sf_backfill_test), answering this tool's SOQL shapes."""

    def __init__(self):
        super().__init__([])
        self.batches = [batch(1), batch(2, creator="Jotform back-fill 001000000000000CAA 5001"), batch(3),
                        batch(4, status="Failed"), batch(5, creator="Partner report", value=25.0), batch(6, value=1.0)]
        self.rows = rows(1, 3) + rows(2, 2) + rows(6, 1)
        self.field_missing = False           # the field is not deployed yet: Salesforce refuses the read
        self.refuse_read_back = False        # once a PATCH went out, the read of one batch by id gets no answer

    def call(self, *args, **kwargs):
        raise AssertionError("a raw REST call: every read must be an explicit-field SOQL query")

    def grouped(self, batch_ids):
        counts = {}
        for r in self.rows:
            if r["Attendance_Batch__c"] in batch_ids:
                counts[r["Attendance_Batch__c"]] = counts.get(r["Attendance_Batch__c"], 0) + 1
        return [{"Attendance_Batch__c": b, "n": n} for b, n in counts.items()]

    def query(self, soql):
        self.seen.append(soql)
        if self.field_missing and gp.FIELD in soql:
            raise gp.Refused("Salesforce did not answer a read (HTTP 400)")
        if soql == gp.BATCHES:
            return copy.deepcopy(sorted(self.batches, key=lambda b: b["Name"]))
        if m := re.fullmatch(r"SELECT Attendance_Batch__c, COUNT\(Id\) n FROM Attendance__c WHERE Attendance_Batch__c IN \((.*)\) "
                             r"GROUP BY Attendance_Batch__c", soql):
            ids = [i.strip("'") for i in m.group(1).split(", ")]
            assert all(re.fullmatch(r"'\w+'", i) for i in m.group(1).split(", ")) and 0 < len(ids) <= gp.CHUNK, soql
            return self.grouped(set(ids))
        if soql == gp.JOTFORM_SUCCESS:
            return copy.deepcopy([{"Id": b["Id"], gp.FIELD: b[gp.FIELD]} for b in self.batches
                                  if b["Processing_Status__c"] == "Success" and b["Creator__c"].startswith("Jotform")])
        if m := re.fullmatch(r"SELECT Id, Processing_Status__c, Girls_Present__c FROM Attendance_Batch__c WHERE Id = '(\w+)'", soql):
            if self.refuse_read_back and self.updates:
                raise gp.Refused("Salesforce did not answer a read (HTTP 0)")
            return copy.deepcopy([b for b in self.batches if b["Id"] == m.group(1)])
        raise AssertionError(soql)

    def count(self, soql):
        self.seen.append(soql)
        if soql == gp.WITHOUT_VALUE:
            return sum(1 for b in self.batches if b["Processing_Status__c"] == "Success" and b[gp.FIELD] is None)
        raise AssertionError(soql)


class GirlsPresent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.org = GirlsOrg()

    def run_tool(self, *argv):
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                gp.main(["--dir", self.tmp.name] + list(argv), org=self.org)
        except SystemExit as stop:
            return out.getvalue(), str(stop.code)
        return out.getvalue(), None

    def ok(self, *argv):
        out, stop = self.run_tool(*argv)
        self.assertIsNone(stop, stop)
        return out

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def ledger(self):
        with open(self.path("ledger.csv"), encoding="utf-8") as fh:
            return [line.split(",") for line in fh.read().splitlines()[1:]]

    def values(self):
        return [b[gp.FIELD] for b in self.org.batches]

    def test_plan_counts_the_batches_and_writes_ids_and_counts_only(self):
        out = self.ok("plan", "--vpn-off")
        self.assertIn("batches: 6 (5 Success, 1 Failed); to set: 3 Success batches with no Girls present (2 with rows, "
                      "1 with none, 5 rows); already set: 2; Failed batches are left empty: 1", out)
        with open(self.path("plan.csv"), encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        self.assertEqual(lines[0], "batch_id,name,status,creator,rows,value")
        self.assertEqual(lines[1:], ["a1l000000000000001,BATCH-000001,Success,jotform,3,",
                                     "a1l000000000000002,BATCH-000002,Success,jotform,2,",
                                     "a1l000000000000003,BATCH-000003,Success,jotform,0,",
                                     "a1l000000000000004,BATCH-000004,Failed,jotform,0,",
                                     "a1l000000000000005,BATCH-000005,Success,other,0,25",
                                     "a1l000000000000006,BATCH-000006,Success,jotform,1,1"])
        self.assertEqual(stat.S_IMODE(os.stat(self.path("plan.csv")).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(self.tmp.name).st_mode), 0o700)
        self.assertFalse(any("Contact_IDs__c" in s or "Status_Message__c" in s for s in self.org.seen))
        self.assertEqual(self.org.updates, [])

    def test_before_the_field_is_deployed_the_refusal_names_it(self):
        self.org.field_missing = True
        self.assertIn("is Girls_Present__c deployed on Attendance_Batch__c?", self.run_tool("plan", "--vpn-off")[1])
        self.assertIn("is Girls_Present__c deployed on Attendance_Batch__c?", self.run_tool("check", "--vpn-off")[1])

    def test_set_is_a_dry_run_from_the_plan_and_writes_nothing(self):
        self.assertIn("there is no plan yet", self.run_tool("set")[1])
        self.ok("plan", "--vpn-off")
        out = self.ok("set")
        self.assertIn("to set: 3 Success batches with no Girls present", out)
        self.assertIn("  would set BATCH-000001 a1l000000000000001: Girls_Present__c = 3", out)
        self.assertIn("  would set BATCH-000003 a1l000000000000003: Girls_Present__c = 0", out)
        self.assertNotIn("BATCH-000005", out)
        self.assertIn("dry run: nothing was written (--apply writes, with Ryan's go)", out)
        self.assertEqual((self.org.updates, os.path.exists(self.path("ledger.csv"))), ([], False))

    def test_apply_sets_only_the_empty_success_batches_and_reads_each_back(self):
        self.ok("plan", "--vpn-off")
        out = self.ok("set", "--apply", "--vpn-off", "--limit", "1")
        self.assertEqual(self.org.updates, [("Attendance_Batch__c", "a1l000000000000001", {"Girls_Present__c": 3})])
        self.assertIn("  BATCH-000001 a1l000000000000001: Girls_Present__c = 3, read back equal", out)
        self.assertIn("set and read back: 1; ledger", out)
        self.assertEqual([(r[1], r[2], r[3], r[4]) for r in self.ledger()],
                         [("a1l000000000000001", "3", "", "open"), ("a1l000000000000001", "3", "3", "written")])
        self.assertEqual(stat.S_IMODE(os.stat(self.path("ledger.csv")).st_mode), 0o600)
        out = self.ok("set", "--apply", "--vpn-off")
        self.assertIn("  BATCH-000001 a1l000000000000001: has a value now - left alone", out)   # the plan is older than the write
        self.assertIn("set and read back: 2; skipped, already has a value: 1", out)
        self.assertEqual(self.values(), [3, 2, 0, None, 25.0, 1.0])     # the Failed one empty, the aggregate as typed
        self.assertEqual(len(self.org.updates), 3)
        self.ok("plan", "--vpn-off")
        self.assertIn("to set: 0 Success batches with no Girls present (0 with rows, 0 with none, 0 rows); already set: 5",
                      self.ok("set"))
        self.assertIn("check: 4 Jotform Success batches; differ: 0, without a value: 0 -> OK", self.ok("check", "--vpn-off"))

    def test_a_value_typed_after_the_plan_is_left_alone_and_a_changed_status_stops(self):
        self.ok("plan", "--vpn-off")
        self.org.batches[0][gp.FIELD] = 7.0           # somebody typed a count meanwhile
        out = self.ok("set", "--apply", "--vpn-off")
        self.assertIn("BATCH-000001 a1l000000000000001: has a value now - left alone", out)
        self.assertEqual(self.values()[0], 7.0)
        self.org = GirlsOrg()
        self.ok("plan", "--vpn-off")
        self.org.batches[2]["Processing_Status__c"] = "Failed"      # BATCH-000003 was Success when planned
        out, stop = self.run_tool("set", "--apply", "--vpn-off")
        self.assertIn("BATCH-000003 a1l000000000000003 is Failed now, Success when planned - STOPPED", stop)
        self.assertEqual(len(self.org.updates), 2)                   # the two before it were written, nothing after
        self.assertEqual(self.values(), [3, 2, None, None, 25.0, 1.0])

    def test_a_refused_or_drifting_write_closes_its_ledger_row_and_stops(self):
        self.ok("plan", "--vpn-off")
        self.org.refuse_update = True
        out, stop = self.run_tool("set", "--apply", "--vpn-off")
        self.assertIn("BATCH-000001 a1l000000000000001: Salesforce did not take the write (HTTP 400", stop)
        self.assertNotIn("refused", stop)
        self.assertEqual(([r[4] for r in self.ledger()], len(self.org.updates)), (["open", "failed_400"], 1))
        self.org.refuse_update, self.org.drift_update = False, True
        out, stop = self.run_tool("set", "--apply", "--vpn-off")
        self.assertIn("the write answered 204 but Girls_Present__c reads back as None, not 3 - STOPPED", stop)
        self.assertEqual([r[4] for r in self.ledger()], ["open", "failed_400", "open", "check"])
        self.assertEqual(self.values()[0], None)

    def test_check_names_a_count_that_differs_from_the_rows_and_exits_one(self):
        self.org.batches[5][gp.FIELD] = 4.0           # 1 row, counted 4
        out, stop = self.run_tool("check", "--vpn-off")
        self.assertEqual(stop, "1")
        self.assertIn("check: 4 Jotform Success batches; differ: 1, without a value: 3 -> NOT OK", out)
        self.assertIn("  differs: a1l000000000000006", out)
        self.org.batches[4][gp.FIELD] = 99.0          # an aggregate has no rows by design: never compared
        self.assertEqual(self.run_tool("check", "--vpn-off")[1], "1")
        self.assertIn("differ: 1,", self.run_tool("check", "--vpn-off")[0])

    def test_a_count_that_is_not_a_whole_number_is_a_refusal(self):
        self.org.batches[5][gp.FIELD] = 1.5
        self.assertIn("not a whole number", self.run_tool("plan", "--vpn-off")[1])

    def test_the_rows_are_counted_in_chunks_of_batch_ids(self):
        def grouped_reads():
            return [s for s in self.org.seen if s.startswith("SELECT Attendance_Batch__c, COUNT(Id)")]
        out = self.ok("plan", "--vpn-off")
        self.assertEqual(len(grouped_reads()), 1)                           # six batches: one GROUP BY of six ids
        self.org.seen.clear()
        with mock.patch.object(gp, "CHUNK", 4):
            self.assertEqual(self.ok("plan", "--vpn-off"), out)             # the same plan from two reads
            self.assertEqual(len(grouped_reads()), 2)
            self.org.seen.clear()
            self.assertEqual(self.run_tool("check", "--vpn-off")[1], "1")   # four Jotform Success batches: one read
            self.assertEqual(len(grouped_reads()), 1)
        self.assertTrue(all(" IN ('" in s and s.endswith(") GROUP BY Attendance_Batch__c") for s in grouped_reads()))

    def test_a_re_read_salesforce_refuses_after_a_204_closes_the_row_as_check(self):
        self.ok("plan", "--vpn-off")
        self.org.refuse_read_back = True
        out, stop = self.run_tool("set", "--apply", "--vpn-off")
        self.assertIn("BATCH-000001 a1l000000000000001: the write answered 204 but the re-read did not answer (Salesforce did "
                      "not answer a read (HTTP 0)) - STOPPED", stop)
        self.assertEqual([(r[1], r[3], r[4]) for r in self.ledger()],
                         [("a1l000000000000001", "", "open"), ("a1l000000000000001", "", "check")])
        self.assertEqual((self.values()[0], len(self.org.updates)), (3, 1))     # the PATCH took; the ledger says look

    def test_a_fresh_checkout_without_data_gets_the_default_folder_created_owner_only(self):
        with tempfile.TemporaryDirectory() as checkout, mock.patch.object(gp, "REPO", checkout):
            folder = os.path.join(checkout, "data", "sf_girls_present")
            self.assertEqual(gp.Paths(folder).plan, os.path.join(folder, "plan.csv"))
            self.assertEqual([stat.S_IMODE(os.stat(p).st_mode) for p in (os.path.join(checkout, "data"), folder)], [0o700] * 2)
            with self.assertRaises(gp.Refused):
                gp.Paths(os.path.join(checkout, "docs"))
            self.assertFalse(os.path.exists(os.path.join(checkout, "docs")))

    def test_the_live_commands_need_the_vpn_word_and_the_whole_write_flag(self):
        for argv in (("plan",), ("check",), ("set", "--apply")):
            with self.subTest(argv):
                self.assertIn("check that no VPN is on", self.run_tool(*argv)[1])
        for short in ("--app", "--a", "--appl"):
            self.assertEqual(self.run_tool("set", short, "--vpn-off")[1], "2")        # argparse: no such flag
        self.assertEqual(self.run_tool("set", "--apply", "--vpn-off", "--limit", "0")[1], "2")
        self.assertEqual((self.org.updates, self.org.seen), ([], []))
        with self.assertRaises(SystemExit) as stop, contextlib.redirect_stdout(io.StringIO()):
            gp.main(["--help"])
        self.assertEqual(stop.exception.code, 0)

    def test_a_folder_inside_the_checkout_but_outside_data_is_refused(self):
        with self.assertRaises(SystemExit) as stop, contextlib.redirect_stdout(io.StringIO()):
            gp.main(["--dir", os.path.join(REPO, "docs"), "set"], org=self.org)
        self.assertIn("must be under data/", str(stop.exception.code))


if __name__ == "__main__":
    unittest.main()
