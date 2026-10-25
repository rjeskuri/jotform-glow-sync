#!/usr/bin/env python3
"""
Offline tests for tools/sf_girls_present.py (found by `make py`'s unittest discovery).
Everything here is fictional: batch ids, names and counts are invented. The fake org holds
six batches - live Jotform ones with and without rows, a back-filled one, a Failed duplicate, a
typed partner aggregate and one the processor already counted - and answers an explicit-field SOQL on
Attendance_Batch__c as Salesforce would: only the fields named come back, and a WHERE of the
conditions it knows (status, creator, the count, ids, Status_Message__c) joined by AND, OR and NOT.
Since 2026-10-22 (ticket #108) a mentor's merged correction is a Success batch whose Status_Message__c
is 'merged into <original id>', with no count and no rows of its own: the tool tells it apart by a
condition on that message - never by selecting it, never by its id or its place in the list.
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
from helpers.fake_org import FakeOrg                      # noqa: E402


OK_MESSAGE = "Processed successfully."
DUPLICATE_MESSAGE = "Duplicate: A successful batch already exists for this account and date."
BACKFILL = "Jotform back-fill 001000000000000CAA 5001"
FIELDS = ("Id", "Name", "Processing_Status__c", "Creator__c", "Girls_Present__c")   # what a read may name
PRIVATE = ("Status_Message__c", "Contact_IDs__c")       # never selected: a message can quote a girl's name


def batch_id(n):
    return f"a1l{n:015d}"


def batch(n, status="Success", creator="Jotform", value=None, message=None, id_=None):
    """A batch as the processor leaves it; `message` is its Status_Message__c (the processor's own
    for the status unless given: a merged correction's is 'merged into <original id>'); `id_` an id
    of its own (a live one: 18 characters, its key prefix and suffix not the fixture's zeros)."""
    return {"Id": id_ or batch_id(n), "Name": f"BATCH-{n:06d}", "Processing_Status__c": status, "Creator__c": creator,
            "Girls_Present__c": value,
            "Status_Message__c": message or (OK_MESSAGE if status == "Success" else DUPLICATE_MESSAGE)}


def rows(n, count):
    """`count` rows of batch `n` (its number, or its id when it has one of its own)."""
    who = n if isinstance(n, str) else batch_id(n)
    tag = who[-3:] if isinstance(n, str) else f"{n:03d}"
    return [{"Id": f"a1m{tag}{i:012d}", "Attendance_Batch__c": who} for i in range(count)]


# one condition of a WHERE, as SOQL writes it: `field = 'x'`, `!= 'x'`, `LIKE 'x%'`, `= null`, `!= null`,
# `IN ('a', 'b')`; `NOT` and parentheses are the logic around it (SOQL has no `NOT LIKE`)
LEAF_RX = re.compile(r"\b(?P<field>Id|Name|Processing_Status__c|Creator__c|Girls_Present__c|Status_Message__c)\s*"
                     r"(?:(?P<op>LIKE|!=|=)\s*(?:'(?P<value>[^']*)'|(?P<null>null))|IN\s*\((?P<list>[^)]*)\))", re.I)
# a condition on the message in a read: the one way the tool may know a merged correction
MESSAGE_RX = re.compile(r"Status_Message__c\s*(LIKE|!=|=|IN)\b", re.I)
# a batch id (15 or 18 characters of the Attendance_Batch__c key prefix) quoted in a condition: an enumeration of
# the originals the fake happens to hold, not the processor's message pattern (`_` is SOQL's one-character wildcard)
BATCH_ID_RX = re.compile(r"a1l\w{12}")
SELECT_RX = re.compile(r"SELECT (?P<fields>.+?) FROM Attendance_Batch__c(?: WHERE (?P<where>.+?))?"
                       r"(?: ORDER BY (?P<order>\w+)(?: (?P<dir>ASC|DESC))?)?(?: LIMIT (?P<limit>\d+))?", re.S)
ROWS_RX = re.compile(r"SELECT Attendance_Batch__c, COUNT\(Id\) n FROM Attendance__c WHERE Attendance_Batch__c IN \((.*)\) "
                     r"GROUP BY Attendance_Batch__c")


def like(pattern, text):
    """SOQL LIKE: `%` any run, `_` one character, case ignored."""
    rx = ".*".join(".".join(re.escape(piece) for piece in part.split("_")) for part in pattern.split("%"))
    return re.fullmatch(rx, text, re.I | re.S) is not None


def holds(leaf, record):
    """One LEAF_RX condition against a batch, as Salesforce compares (text case ignored; '' is null)."""
    field = next(f for f in FIELDS + ("Status_Message__c",) if f.lower() == leaf.group("field").lower())
    value = record.get(field)
    text = "" if value is None else str(value)
    if leaf.group("list") is not None:
        return text.lower() in [i.strip().strip("'").lower() for i in leaf.group("list").split(",")]
    op = leaf.group("op").upper()
    if leaf.group("null"):
        return (text == "") == (op == "=")
    if op == "LIKE":
        return like(leaf.group("value"), text)
    return (text.lower() == leaf.group("value").lower()) == (op == "=")


def where_filter(where):
    """A predicate on a batch for a WHERE clause (None: every batch passes), applied as Salesforce would:
    the conditions LEAF_RX knows, joined by AND, OR and NOT with parentheses. Anything else - a field
    this fake does not hold, a bind, a date literal - is an AssertionError, not a silent pass."""
    if where is None:
        return lambda record: True
    leaves = list(LEAF_RX.finditer(where))
    logic = LEAF_RX.sub(" _ ", where)
    if not re.fullmatch(r"(?:_|AND|OR|NOT|[\s()])*", logic, re.I) or logic.count("_") != len(leaves):
        raise AssertionError(f"a WHERE this fake org does not understand: {where}")
    pieces = re.sub(r"\b(AND|OR|NOT)\b", lambda m: m.group(1).lower(), logic, flags=re.I).split("_")

    def passes(record):
        results = [holds(leaf, record) for leaf in leaves]
        code = "".join(piece + (f" r[{i}] " if i < len(results) else "") for i, piece in enumerate(pieces))
        return bool(eval(code, {"__builtins__": {}}, {"r": results}))   # the pieces are AND/OR/NOT/parens only
    return passes


class GirlsOrg(FakeOrg):
    """The shared fake org (test/helpers/fake_org.py), answering any explicit-field SOQL on
    Attendance_Batch__c and the tool's grouped row count."""

    def __init__(self):
        super().__init__([])
        self.batches = [batch(1), batch(2, creator=BACKFILL), batch(3),
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

    def select(self, soql):
        """(the fields a SELECT on Attendance_Batch__c names, the batches it answers in its order, its WHERE);
        a field this fake does not hold, or one never to be selected, is an AssertionError."""
        m = SELECT_RX.fullmatch(soql)
        if not m:
            raise AssertionError(soql)
        fields = [f.strip() for f in m.group("fields").split(",")]
        for f in fields:
            if f in PRIVATE:
                raise AssertionError(f"{f} selected - a condition in the WHERE at most: {soql}")
            if f not in FIELDS and f != "COUNT()":
                raise AssertionError(f"{f}: not a field of this fake's batches: {soql}")
        passes = where_filter(m.group("where"))
        found = [b for b in self.batches if passes(b)]
        if m.group("order"):
            found.sort(key=lambda b: str(b[m.group("order")]), reverse=m.group("dir") == "DESC")
        if m.group("limit"):
            found = found[:int(m.group("limit"))]
        return fields, found, m.group("where")

    def query(self, soql):
        self.seen.append(soql)
        if self.field_missing and gp.FIELD in soql:
            raise gp.Refused("Salesforce did not answer a read (HTTP 400)")
        if m := ROWS_RX.fullmatch(soql):
            ids = [i.strip("'") for i in m.group(1).split(", ")]
            assert all(re.fullmatch(r"'\w+'", i) for i in m.group(1).split(", ")) and 0 < len(ids) <= gp.CHUNK, soql
            return self.grouped(set(ids))
        fields, found, where = self.select(soql)
        if fields == ["COUNT()"]:
            raise AssertionError(f"a COUNT() through query(); count() answers it: {soql}")
        if self.refuse_read_back and self.updates and where and re.fullmatch(r"Id = '\w+'", where):
            raise gp.Refused("Salesforce did not answer a read (HTTP 0)")
        return [{f: copy.deepcopy(b[f]) for f in fields} for b in found]       # only the fields named come back

    def count(self, soql):
        self.seen.append(soql)
        if self.field_missing and gp.FIELD in soql:
            raise gp.Refused("Salesforce did not answer a read (HTTP 400)")
        fields, found, _ = self.select(soql)
        if fields != ["COUNT()"]:
            raise AssertionError(f"count() answers a COUNT() query only: {soql}")
        return len(found)


# merged corrections per case: (its number, its original[, its Creator__c]); the original is a fixture batch's
# number, or the id of one the case itself adds (NEW_ORIGINAL: a live-shaped 18-character id, not in the base
# fixture, so an enumeration of the fixture's ids in a WHERE cannot pass); their ids and how many there are vary,
# so a tool that knows two ids, or skips the last batches, cannot pass either
NEW_ORIGINAL = "a1lRP00000Xk3q2YAB"
MERGED_CASES = (
    ((7, 1),),
    ((11, 2), (12, 1), (15, 6)),
    ((21, 6, BACKFILL), (23, 2)),
    ((33, 2), (35, NEW_ORIGINAL)),
)


class GirlsPresent(unittest.TestCase):
    def setUp(self):
        self.fresh()

    def fresh(self):
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

    def value_of(self, batch_id_):
        return next(b[gp.FIELD] for b in self.org.batches if b["Id"] == batch_id_)

    def add_merged(self, merged, with_rows):
        """The corrections `merged` arrive: each a Success 'merged into <original id>' with no count and no
        rows of its own; with_rows, each adds one girl to its original's day (a row of the ORIGINAL batch,
        whose count moves with it). An original given by id and not in the org yet is added first: a counted
        Jotform Success of its own (two rows, Girls_Present__c 2), numbered one below its correction.
        Returns the originals' ids, in order."""
        originals = []
        for n, original, *creator in merged:
            if isinstance(original, str):
                if not any(b["Id"] == original for b in self.org.batches):
                    self.org.batches.append(batch(n - 1, value=2.0, id_=original))
                    self.org.rows += rows(original, 2)
            else:
                original = batch_id(original)
            self.org.batches.append(batch(n, creator=creator[0] if creator else "Jotform",
                                          message=f"merged into {original}"))
            if with_rows:
                have = sum(1 for r in self.org.rows if r["Attendance_Batch__c"] == original)
                self.org.rows += rows(original, have + 1)[have:]
                for b in self.org.batches:
                    if b["Id"] == original:
                        b[gp.FIELD] = float(have + 1)
            originals.append(original)
        return originals

    def add_lookalikes(self, top):
        """After the merged ones, with higher numbers: a Failed batch whose message says 'merged into' (still a
        Failed one, left empty), a Success whose message merely contains 'merged' elsewhere (no merged
        correction: a Success without a value, to set and to flag), and a plain Success with no value and
        no rows (the same). Returns their ids."""
        self.org.batches.append(batch(top + 1, status="Failed", message=f"merged into {batch_id(1)}"))
        self.org.batches.append(batch(top + 2, message="Processed successfully. 1 name merged with an existing "
                                                        "Contact by the duplicate rule"))
        self.org.batches.append(batch(top + 3))
        return batch_id(top + 1), batch_id(top + 2), batch_id(top + 3)

    def assert_message_filtered_only(self, *printed):
        """The message decides the merged case in a WHERE: some read carries a condition on it, no read selects
        it, and neither its name nor its text reaches what the tool prints or writes. The condition is the
        processor's message PATTERN - a LIKE with a `%` wildcard on 'merged' - never an enumeration: no `IN`,
        no `=`/`!=` of a message text, no batch id quoted in it (a null test aside)."""
        self.assertTrue(any(MESSAGE_RX.search(s) for s in self.org.seen),
                        f"no read tells a merged correction apart by a condition on Status_Message__c: {self.org.seen}")
        patterns = []
        for soql in self.org.seen:
            self.assertNotIn("Status_Message__c", soql.split(" FROM ", 1)[0], soql)
            for leaf in LEAF_RX.finditer(soql.split(" WHERE ", 1)[1] if " WHERE " in soql else ""):
                if leaf.group("field").lower() != "status_message__c":
                    continue
                self.assertIsNone(leaf.group("list"), f"an IN list enumerates messages: {soql}")
                self.assertIsNone(BATCH_ID_RX.search(leaf.group(0)), f"a batch id in a message condition: {soql}")
                if leaf.group("null"):
                    continue
                self.assertEqual(leaf.group("op").upper(), "LIKE", f"a message compared whole, not by pattern: {soql}")
                self.assertIn("%", leaf.group("value"), f"a LIKE with no wildcard is an exact message: {soql}")
                patterns.append(leaf.group("value"))
        self.assertTrue([p for p in patterns if "merged" in p.lower()],
                        f"no read matches the processor's 'merged into <id>' message by its pattern: {self.org.seen}")
        for text in printed:
            self.assertNotIn("Status_Message__c", text)
            self.assertNotIn("merged into", text)

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
        # a read names ids, batch names, statuses, creators and counts: never Contact_IDs__c; Status_Message__c in a
        # WHERE at most (2026-10-22, ticket #108: a merged correction is told apart by it), never selected or printed
        self.assertFalse(any("Contact_IDs__c" in s for s in self.org.seen))
        self.assertFalse(any("Status_Message__c" in s.split(" FROM ", 1)[0] for s in self.org.seen))
        self.assertNotIn("Status_Message__c", out + "\n".join(lines))
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

    def test_check_takes_a_merged_correction_as_healthy_and_still_flags_a_success_without_a_value(self):
        # 2026-10-22 (ticket #108): a mentor's corrected re-submission for a club and day that already has a
        # Success batch adds its missing girls as rows of the ORIGINAL batch, whose count moves with them;
        # the correction itself is Success 'merged into <original id>' with no count and no rows of its own.
        # It is neither a "Success batch without a value" nor a count that differs from its rows.
        for merged in MERGED_CASES:
            with self.subTest(merged=[n for n, *_ in merged]):
                self.fresh()
                # the back-fill done: the fixture's three empty Success batches set, check OK
                self.ok("plan", "--vpn-off")
                self.ok("set", "--apply", "--vpn-off")
                self.assertIn("-> OK", self.ok("check", "--vpn-off"))
                originals = self.add_merged(merged, with_rows=True)
                self.org.seen.clear()
                out = self.ok("check", "--vpn-off")
                self.assertRegex(out, r"check: \d+ Jotform Success batches; differ: 0, without a value: 0 -> OK")
                self.assert_message_filtered_only(out)
                # a Success batch the processor did not count is still the signal, however its message reads and
                # wherever it sits in the list: the one whose message merely says 'merged' and the plain one after
                # the merged ones; the Failed 'merged into' one is a Failed batch like any other
                failed, elsewhere, plain = self.add_lookalikes(max(n for n, *_ in merged))
                out, stop = self.run_tool("check", "--vpn-off")
                self.assertEqual(stop, "1")
                self.assertIn("differ: 0, without a value: 2 -> NOT OK", out)
                # ... and so is an original whose count did not move with the rows a correction added
                for b in self.org.batches:
                    if b["Id"] == originals[-1]:
                        b[gp.FIELD] = b[gp.FIELD] - 1.0
                out, stop = self.run_tool("check", "--vpn-off")
                self.assertEqual(stop, "1")
                self.assertIn("differ: 1, without a value: 2 -> NOT OK", out)
                self.assertIn(f"  differs: {originals[-1]}", out)
                for n, *_ in merged:
                    self.assertNotIn(batch_id(n), out)
                self.assertNotIn(failed, out)
                self.assert_message_filtered_only(out)

    def test_set_never_writes_a_count_onto_a_merged_correction(self):
        # 2026-10-22 (ticket #108): a merged correction is a Success with no value and no rows - the very shape
        # set fills - but its value must stay empty: a Success with 0 is the dashboard's "blank". Whatever its id,
        # creator or place in the list, it is left out of the plan's work and never PATCHed; the look-alikes
        # (a later plain Success, one whose message merely says 'merged') are set to 0 as before, and a Failed
        # batch whose message says 'merged into' is still a Failed one: in the plan, left empty.
        for merged in MERGED_CASES:
            with self.subTest(merged=[n for n, *_ in merged]):
                self.fresh()
                originals = self.add_merged(merged, with_rows=False)
                top = max(n for n, *_ in merged)
                failed, elsewhere, plain = self.add_lookalikes(top)
                out = self.ok("plan", "--vpn-off")
                self.assertIn("to set: 5 Success batches with no Girls present (2 with rows, 3 with none, 5 rows)", out)
                self.assertIn("Failed batches are left empty: 2", out)
                with open(self.path("plan.csv"), encoding="utf-8") as fh:
                    plan = fh.read()
                self.assertIn(f"{failed},BATCH-{top + 1:06d},Failed,jotform,0,\n", plan)
                self.assert_message_filtered_only(out, plan)
                out = self.ok("set")
                self.assertIn("to set: 5 Success batches", out)
                for name, id_, count in (("BATCH-000001", batch_id(1), 3), ("BATCH-000003", batch_id(3), 0),
                                         (f"BATCH-{top + 2:06d}", elsewhere, 0), (f"BATCH-{top + 3:06d}", plain, 0)):
                    self.assertIn(f"  would set {name} {id_}: Girls_Present__c = {count}", out)
                for n, *_ in merged:
                    self.assertNotIn(batch_id(n), out)
                self.assertNotIn(failed, out)
                self.assertEqual(self.org.updates, [])
                out = self.ok("set", "--apply", "--vpn-off")
                self.assertEqual(sorted(record for _, record, _ in self.org.updates),
                                 sorted([batch_id(1), batch_id(2), batch_id(3), elsewhere, plain]))
                self.assertEqual([self.value_of(batch_id(n)) for n, *_ in merged] + [self.value_of(failed)],
                                 [None] * (len(merged) + 1))
                self.assertEqual(self.values()[:6] + [self.value_of(elsewhere), self.value_of(plain)],
                                 [3, 2, 0, None, 25.0, 1.0, 0, 0])
                for id_ in originals:                       # a counted original the case added: left as it was
                    if id_ not in [batch_id(k) for k in range(1, 7)]:
                        self.assertEqual(self.value_of(id_), 2.0)
                self.assertIn("set and read back: 5", out)
                self.assertNotIn("merged into", out)
                self.assertIn("-> OK", self.ok("check", "--vpn-off"))

    def test_a_count_that_is_not_a_whole_number_is_a_refusal(self):
        self.org.batches[5][gp.FIELD] = 1.5
        self.assertIn("not a whole number", self.run_tool("plan", "--vpn-off")[1])
        # glow.salesforce.as_int underneath: empty is None, a whole double or int its number, anything else refused
        self.assertEqual([gp.as_count(v) for v in (None, "", 3.0, 3, 0.0)], [None, None, 3, 3, 0])
        for value in (1.5, "x", True):
            with self.subTest(value=value), self.assertRaises(gp.Refused):
                gp.as_count(value)

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


class FakeOrgSoql(unittest.TestCase):
    """The fake's SOQL, so a passing merged test means the filter did the work: LIKE, null, NOT and parentheses as
    Salesforce reads them, only the selected fields in an answer, and a refusal of what it cannot apply."""

    def test_where_filter_reads_like_null_not_and_parentheses(self):
        merged, plain, failed = (batch(9, message="merged into a1l000000000000002"), batch(3),
                                 batch(4, status="Failed", message="merged into a1l000000000000001"))
        cases = {
            "Status_Message__c LIKE 'merged into %'": (True, False, True),
            "NOT Status_Message__c LIKE 'merged into %'": (False, True, False),
            "NOT (Status_Message__c LIKE 'merged into %')": (False, True, False),
            "Processing_Status__c = 'Success' AND (NOT Status_Message__c LIKE 'merged into %')": (False, True, False),
            "NOT (Processing_Status__c = 'Success' AND Status_Message__c LIKE 'merged into %')": (False, True, True),
            "Processing_Status__c != 'Success' OR NOT Status_Message__c LIKE 'merged into %'": (False, True, True),
            "Status_Message__c LIKE '%MERGED%'": (True, False, True),
            "Status_Message__c = 'Processed successfully.'": (False, True, False),
            "Girls_Present__c = null AND Creator__c LIKE 'Jotform%'": (True, True, True),
            "Id IN ('a1l000000000000009', 'a1l000000000000004')": (True, False, True),
        }
        for where, expected in cases.items():
            with self.subTest(where):
                passes = where_filter(where)
                self.assertEqual(tuple(passes(b) for b in (merged, plain, failed)), expected)
        for where in ("Status_Message__c != null AND Module__c = 'x'", "Status_Message__c LIKE :pattern",
                      "Status_Message__c NOT LIKE 'merged%'", "CreatedDate = TODAY"):
            with self.subTest(where), self.assertRaises(AssertionError):
                where_filter(where)

    def test_a_read_answers_the_fields_named_and_refuses_the_message(self):
        org = GirlsOrg()
        org.batches.append(batch(7, message="merged into a1l000000000000001"))
        found = org.query("SELECT Id, Girls_Present__c FROM Attendance_Batch__c WHERE Processing_Status__c = 'Success' "
                          "AND Creator__c LIKE 'Jotform%' AND (NOT Status_Message__c LIKE 'merged into %')")
        self.assertEqual([sorted(r) for r in found], [["Girls_Present__c", "Id"]] * 4)
        self.assertEqual([r["Id"] for r in found], [batch_id(n) for n in (1, 2, 3, 6)])
        self.assertEqual(org.count("SELECT COUNT() FROM Attendance_Batch__c WHERE Processing_Status__c = 'Success' "
                                   "AND Girls_Present__c = null AND (NOT Status_Message__c LIKE 'merged into %')"), 3)
        self.assertEqual([r["Name"] for r in org.query("SELECT Name FROM Attendance_Batch__c ORDER BY Name DESC LIMIT 2")],
                         ["BATCH-000007", "BATCH-000006"])
        self.assertEqual(len(org.query("SELECT Id FROM Attendance_Batch__c WHERE Status_Message__c != null")), 7)
        for soql in ("SELECT Id, Status_Message__c FROM Attendance_Batch__c", "SELECT Id, Contact_IDs__c FROM Attendance_Batch__c",
                     "SELECT Id FROM Attendance_Batch__c WHERE Status_Message__c LIKE :pattern",
                     "SELECT Id FROM Attendance_Batch__c WHERE Status_Message__c NOT LIKE 'merged%'"):
            with self.subTest(soql), self.assertRaises(AssertionError):
                org.query(soql)


if __name__ == "__main__":
    unittest.main()
