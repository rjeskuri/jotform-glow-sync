#!/usr/bin/env python3
"""
Offline tests for glow/session_timing.py and tools/sf_session_timing.py check (ticket #100; found by
`make py`'s unittest discovery). Ryan's answers (2026-10-22): the session week is the week of the
month by day (1-7 week 1 ... 29-31 week 5, `2026-10 week 2`), the submission day is the UTC day, and
there is no "big delay" threshold or flag. Everything here is fictional: batch ids, batch Names
(`AB-0001`), account ids and dates are invented. A stub org answers the check's one SOQL query with
Salesforce's REST shapes (CreatedDate `2026-10-06T01:30:00.000+0000`, a Date `2026-10-05`, a Number
as a float) and the formula values Salesforce would compute, written out by hand below.
"""
import contextlib
import copy
import importlib
import io
import os
import re
import sys
import unittest
from unittest import mock
from datetime import date, datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
from glow.salesforce import Refused  # noqa: E402

UTC = timezone.utc
FIELDS = ["Submitted_At__c", "Submission_Delay_Days__c", "Session_Month__c", "Session_Week__c"]
SELECTED = {"Id", "Name", "Creator__c", "CreatedDate", "Attendance_Date__c", *FIELDS}
FORMULAS = {
    "Submitted_At__c": 'IF(Creator__c = "Jotform", CreatedDate, NULL)',
    "Submission_Delay_Days__c": "IF(ISBLANK(Submitted_At__c), NULL, DATEVALUE(Submitted_At__c) - Attendance_Date__c)",
    "Session_Month__c": 'TEXT(YEAR(Attendance_Date__c)) & "-" & LPAD(TEXT(MONTH(Attendance_Date__c)), 2, "0")',
    "Session_Week__c": 'Session_Month__c & " week " & TEXT(CEILING(DAY(Attendance_Date__c) / 7))',
}
BACKFILL = "Jotform back-fill 001AA0000000000ZZZ 5001"


def timing():
    return importlib.import_module("glow.session_timing")


def tool():
    return importlib.import_module("sf_session_timing")


def batch(n, creator, created, day, submitted, delay, month, week):
    """One Attendance_Batch__c as REST gives it, with the formula values Salesforce computes."""
    return {"attributes": {"type": "Attendance_Batch__c", "url": f"/services/data/v61.0/sobjects/Attendance_Batch__c/a1l{n:015d}"},
            "Id": f"a1l{n:015d}", "Name": f"AB-{n:04d}", "Creator__c": creator, "CreatedDate": created,
            "Attendance_Date__c": day, "Submitted_At__c": submitted, "Submission_Delay_Days__c": delay,
            "Session_Month__c": month, "Session_Week__c": week}


def agreeing_batches():
    """Salesforce's values, computed by hand from the definitions (UTC day; week of the month by day)."""
    return [
        # live Jotform: submitted the next UTC day
        batch(1, "Jotform", "2026-10-06T01:30:00.000+0000", "2026-10-05", "2026-10-06T01:30:00.000+0000", 1.0,
              "2026-10", "2026-10 week 1"),
        # live Jotform: same UTC day, day 15 is week 3; a Number Salesforce may give as an int
        batch(2, "Jotform", "2026-10-15T23:59:00.000+0000", "2026-10-15", "2026-10-15T23:59:00.000+0000", 0,
              "2026-10", "2026-10 week 3"),
        # September back-fill: no submission time, so no delay
        batch(3, BACKFILL, "2026-10-02T08:00:00.000+0000", "2026-09-30", None, None, "2026-09", "2026-09 week 5"),
        # a partner's monthly batch: no submission time
        batch(4, "Partner report", "2026-10-03T10:00:00.000+0000", "2026-09-01", None, None, "2026-09", "2026-09 week 1"),
        # live Jotform: submitted before the session day (a date typo) - negative
        batch(5, "Jotform", "2026-09-20T12:00:00.000+0000", "2026-09-22", "2026-09-20T12:00:00.000+0000", -2.0,
              "2026-09", "2026-09 week 4"),
        # live Jotform: a long delay, day 14 is still week 2
        batch(6, "Jotform", "2026-10-29T08:00:00.000+0000", "2026-10-14", "2026-10-29T08:00:00.000+0000", 15.0,
              "2026-10", "2026-10 week 2"),
        # live Jotform: day 29 is week 5; submitted in the next month
        batch(7, "Jotform", "2026-11-01T00:00:00.000+0000", "2026-10-29", "2026-11-01T00:00:00.000+0000", 3.0,
              "2026-10", "2026-10 week 5"),
        # before the default --since (2026-09-01): the query leaves it out
        batch(8, "Jotform", "2026-09-02T09:00:00.000+0000", "2026-08-31", "2026-09-02T09:00:00.000+0000", 2.0,
              "2026-08", "2026-08 week 5"),
    ]


ORDER_TERM = r"\w+(?:\s+(?:ASC|DESC))?"
CHECK_SOQL = re.compile(r"\s*SELECT\s+(?P<fields>.+?)\s+FROM\s+Attendance_Batch__c\s+"
                        r"WHERE\s+Attendance_Date__c\s*>=\s*(?P<since>\d{4}-\d{2}-\d{2})"
                        rf"(?:\s+ORDER\s+BY\s+{ORDER_TERM}(?:\s*,\s*{ORDER_TERM})*)?\s*", re.S)


class StubOrg:
    """Salesforce as the check sees it: one read-only SOQL query over Attendance_Batch__c of exactly
    the shape `SELECT <the nine fields> FROM Attendance_Batch__c WHERE Attendance_Date__c >= <day>`,
    optionally followed by ORDER BY - no other filter, no LIMIT. It honours the day, as Salesforce
    would; any other query, or anything else that talks to Salesforce, is a test failure."""

    def __init__(self, batches, refusal=None):
        self.batches, self.refusal, self.seen = batches, refusal, []

    def query(self, soql):
        self.seen.append(soql)
        if self.refusal:
            raise Refused(self.refusal)
        m = CHECK_SOQL.fullmatch(soql)
        if not m:
            raise AssertionError(f"not the check's one query (no other filter, no LIMIT): {soql}")
        if sorted(f.strip() for f in m.group("fields").split(",")) != sorted(SELECTED):
            raise AssertionError(f"not the nine explicit fields: {soql}")
        return [b for b in copy.deepcopy(self.batches) if b["Attendance_Date__c"] >= m.group("since")]

    query_all = query

    def count(self, soql):
        raise AssertionError("a count: the check is one SOQL query")

    def call(self, *args, **kwargs):
        raise AssertionError("a raw REST call: the check is one explicit-field SOQL query")

    def insert(self, *args, **kwargs):
        raise AssertionError("a write: the check is read-only")

    update = delete = insert


def run(argv, org):
    """(exit code, stdout + stderr): 0 for a plain return or None; SystemExit's code otherwise."""
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = tool().main(argv, org=org)
    except SystemExit as stop:
        code = stop.code
    return (0 if code is None else code), out.getvalue()


def selected_fields(soql):
    m = re.match(r"\s*SELECT\s+(.*?)\s+FROM\s+Attendance_Batch__c\b", soql, re.I | re.S)
    if not m:
        raise AssertionError(f"not a SELECT over Attendance_Batch__c: {soql}")
    return [f.strip() for f in m.group(1).split(",")]


def summary(counts, verdict):
    a, b, c, d = counts
    return (f"differ: Submitted_At__c {a}, Submission_Delay_Days__c {b}, Session_Month__c {c}, "
            f"Session_Week__c {d} -> {verdict}")


class CheckAgainstSalesforce(unittest.TestCase):
    """tools/sf_session_timing.py check, through main(argv, org=stub)."""

    def test_check_reports_ok_when_salesforce_agrees(self):
        org = StubOrg(agreeing_batches())
        code, out = run(["check", "--vpn-off"], org)
        self.assertEqual(code, 0, out)
        self.assertIn("checked 7 batches; " + summary((0, 0, 0, 0), "OK"), out)
        self.assertNotIn("DIFFER", out)
        self.assertEqual(len(org.seen), 1, org.seen)

    def test_check_ok_counts_follow_since(self):
        org = StubOrg(agreeing_batches())
        code, out = run(["check", "--vpn-off", "--since", "2026-10-01"], org)
        self.assertEqual(code, 0, out)
        self.assertIn("checked 4 batches; " + summary((0, 0, 0, 0), "OK"), out)
        self.assertRegex(org.seen[0], r"\bAttendance_Date__c\s*>=\s*2026-10-01\b")

    def test_check_names_the_batches_that_differ(self):
        batches = agreeing_batches()
        by_name = {b["Name"]: b for b in batches}
        by_name["AB-0001"]["Submitted_At__c"] = "2026-10-06T02:30:00.000+0000"   # not its CreatedDate
        by_name["AB-0005"]["Submission_Delay_Days__c"] = 9.0                      # expected -2
        by_name["AB-0006"]["Submission_Delay_Days__c"] = 14.0                     # expected 15
        by_name["AB-0002"]["Session_Week__c"] = "2026-10 week 2"                  # day 15: week 3
        by_name["AB-0004"]["Session_Week__c"] = "2026-09 week 0"                  # day 1: week 1
        by_name["AB-0007"]["Session_Week__c"] = "2026-10 week 4"                  # day 29: week 5
        code, out = run(["check", "--vpn-off"], StubOrg(batches))
        self.assertEqual(code, 1, out)
        self.assertIn("checked 7 batches; " + summary((1, 2, 0, 3), "DIFFER"), out)
        lines = out.splitlines()

        def line_for(name, field):
            found = [ln for ln in lines if name in ln and field in ln]
            self.assertEqual(len(found), 1, f"{name} {field}: {out}")
            return found[0]

        self.assertIn("2026-10 week 2", line_for("AB-0002", "Session_Week__c"))
        self.assertIn("2026-10 week 3", line_for("AB-0002", "Session_Week__c"))
        self.assertIn("2026-10 week 4", line_for("AB-0007", "Session_Week__c"))
        self.assertIn("2026-10 week 5", line_for("AB-0007", "Session_Week__c"))
        self.assertIn("2026-09 week 0", line_for("AB-0004", "Session_Week__c"))
        self.assertIn("2026-09 week 1", line_for("AB-0004", "Session_Week__c"))
        delay = line_for("AB-0005", "Submission_Delay_Days__c")
        self.assertRegex(delay, r"(?<![-\d])9(\.0)?(?!\d)")
        self.assertRegex(delay, r"-2(?!\d)")
        delay = line_for("AB-0006", "Submission_Delay_Days__c")
        self.assertRegex(delay, r"(?<!\d)14(\.0)?(?!\d)")
        self.assertRegex(delay, r"(?<!\d)15(?!\d)")
        self.assertIn("02:30", line_for("AB-0001", "Submitted_At__c"))
        self.assertIn("01:30", line_for("AB-0001", "Submitted_At__c"))
        for name in ("AB-0003", "AB-0008"):
            self.assertNotIn(name, out)

    def test_check_finds_a_submission_time_on_a_batch_that_should_have_none(self):
        batches = agreeing_batches()
        batches[2]["Submitted_At__c"] = batches[2]["CreatedDate"]   # the back-fill: none expected
        batches[2]["Submission_Delay_Days__c"] = 2.0
        batches[3]["Session_Month__c"] = "2026-10"                   # the partner batch's day is 2026-09-01
        code, out = run(["check", "--vpn-off"], StubOrg(batches))
        self.assertEqual(code, 1, out)
        self.assertIn("checked 7 batches; " + summary((1, 1, 1, 0), "DIFFER"), out)
        self.assertTrue(any("AB-0003" in ln and "Submitted_At__c" in ln for ln in out.splitlines()), out)
        self.assertTrue(any("AB-0004" in ln and "Session_Month__c" in ln and "2026-09" in ln and "2026-10" in ln
                            for ln in out.splitlines()), out)

    def test_check_shows_at_most_ten_differences_but_counts_them_all(self):
        batches = []
        for n in range(1, 16):
            day = date(2026, 10, n)
            week = f"2026-10 week {(n - 1) // 7 + 1}"
            batches.append(batch(n, "Partner report", "2026-10-20T10:00:00.000+0000", day.isoformat(), None, None,
                                 "2026-10", week + "9"))         # every week wrong
        code, out = run(["check", "--vpn-off"], StubOrg(batches))
        self.assertEqual(code, 1, out)
        self.assertIn("checked 15 batches; " + summary((0, 0, 0, 15), "DIFFER"), out)
        detail = [ln for ln in out.splitlines() if re.search(r"AB-\d{4}", ln)]
        self.assertEqual(len(detail), 10, out)

    def test_check_parses_rest_shapes(self):
        """CreatedDate with milliseconds and +0000, a Date as text, the delay as a float or an int, null
        formula values for batches that are not live Jotform ones: all agree with the definitions."""
        rows = [
            batch(1, "Jotform", "2026-10-06T01:30:00.000+0000", "2026-10-05", "2026-10-06T01:30:00.000+0000", 1.0,
                  "2026-10", "2026-10 week 1"),
            batch(2, "Jotform", "2026-10-06T01:30:00.000+0000", "2026-10-05", "2026-10-06T01:30:00.000+0000", 1,
                  "2026-10", "2026-10 week 1"),
            batch(3, "Partner report", "2026-12-02T10:00:00.000+0000", "2026-12-01", None, None, "2026-12", "2026-12 week 1"),
            batch(4, BACKFILL, "2026-10-02T08:00:00.000+0000", "2026-09-09", None, None, "2026-09", "2026-09 week 2"),
        ]
        code, out = run(["check", "--vpn-off"], StubOrg(rows))
        self.assertEqual(code, 0, out)
        self.assertIn("checked 4 batches; " + summary((0, 0, 0, 0), "OK"), out)

    def test_check_reads_timestamps_in_any_spelling(self):
        """Submitted_At__c the same instant as CreatedDate, spelt another way (Z, no milliseconds, a
        non-zero offset), agrees; a CreatedDate with an offset counts its UTC day for the delay."""
        rows = [
            batch(1, "Jotform", "2026-10-06T01:30:00.000+0000", "2026-10-05", "2026-10-06T01:30:00Z", 1.0,
                  "2026-10", "2026-10 week 1"),
            batch(2, "Jotform", "2026-10-06T01:30:00.000+0000", "2026-10-05", "2026-10-05T20:30:00.000-0500", 1.0,
                  "2026-10", "2026-10 week 1"),
            batch(3, "Jotform", "2026-10-05T20:30:00.000-0500", "2026-10-05", "2026-10-06T01:30:00.000+0000", 1.0,
                  "2026-10", "2026-10 week 1"),
            batch(4, "Jotform", "2026-10-21T04:15:00.000+0530", "2026-10-20", "2026-10-20T22:45:00.000+0000", 0.0,
                  "2026-10", "2026-10 week 3"),
        ]
        code, out = run(["check", "--vpn-off"], StubOrg(rows))
        self.assertEqual(code, 0, out)
        self.assertIn("checked 4 batches; " + summary((0, 0, 0, 0), "OK"), out)
        # one minute apart in another spelling is a difference
        rows[1]["Submitted_At__c"] = "2026-10-05T20:31:00.000-0500"
        code, out = run(["check", "--vpn-off"], StubOrg(rows))
        self.assertEqual(code, 1, out)
        self.assertIn("checked 4 batches; " + summary((1, 0, 0, 0), "DIFFER"), out)

    def check_with_patched(self, name, fake):
        """The check over the agreeing batches with glow/session_timing.<name> replaced by `fake`
        (wherever the tool holds it), so a tool that does not use the module's definitions shows."""
        st, cli = timing(), tool()
        original = getattr(st, name)
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(st, name, fake))
            for attr, value in list(vars(cli).items()):
                if value is original:
                    stack.enter_context(mock.patch.object(cli, attr, fake))
            return run(["check", "--vpn-off"], StubOrg(agreeing_batches()))

    def test_check_uses_the_definitions_in_glow_session_timing(self):
        code, out = self.check_with_patched("session_week", lambda day: "SENTINEL week 9")
        self.assertEqual(code, 1, out)
        self.assertRegex(out, r"Session_Week__c 7 -> DIFFER")
        self.assertIn("SENTINEL week 9", out)

        code, out = self.check_with_patched("session_month", lambda day: "1999-99")
        self.assertEqual(code, 1, out)
        self.assertRegex(out, r"Session_Month__c 7\b")

        code, out = self.check_with_patched("delay_days", lambda submitted, day: None if submitted is None else 999)
        self.assertEqual(code, 1, out)
        self.assertRegex(out, r"Submission_Delay_Days__c 5\b")       # the five live Jotform batches since 2026-09-01
        self.assertIn("999", out)

        code, out = self.check_with_patched("submitted_at", lambda creator, created: None)
        self.assertEqual(code, 1, out)
        self.assertRegex(out, r"Submitted_At__c 5\b")
        self.assertRegex(out, r"Submission_Delay_Days__c 5\b")     # the delay follows the expected submission time

    def test_check_expects_the_delay_from_the_expected_submission_time(self):
        """The expected delay comes from submitted_at(Creator__c, CreatedDate), never from Salesforce's own
        Submitted_At__c: a wrong Submitted_At__c with a delay that matches it is two differences."""
        rows = [
            batch(1, "Jotform", "2026-10-06T01:30:00.000+0000", "2026-10-05", "2026-10-07T01:30:00.000+0000", 2.0,
                  "2026-10", "2026-10 week 1"),
            batch(2, "Jotform", "2026-10-12T09:00:00.000+0000", "2026-10-10", "2026-10-12T09:00:00.000+0000", 2.0,
                  "2026-10", "2026-10 week 2"),
            batch(3, "Partner report", "2026-10-12T09:00:00.000+0000", "2026-10-03", None, None, "2026-10", "2026-10 week 1"),
        ]
        code, out = run(["check", "--vpn-off"], StubOrg(rows))
        self.assertEqual(code, 1, out)
        self.assertIn("checked 3 batches; " + summary((1, 1, 0, 0), "DIFFER"), out)
        found = [ln for ln in out.splitlines() if "AB-0001" in ln and "Submission_Delay_Days__c" in ln]
        self.assertEqual(len(found), 1, out)
        self.assertRegex(found[0], r"(?<![-\d])2(\.0)?(?!\d)")
        self.assertRegex(found[0], r"(?<![-\d.])1(?![\d.])")
        self.assertTrue(any("AB-0001" in ln and "Submitted_At__c" in ln for ln in out.splitlines()), out)
        self.assertNotIn("AB-0002", out)

    def test_check_prints_batch_names_and_counts_only(self):
        batches = agreeing_batches()
        for b in batches:
            b["Session_Week__c"] = "wrong"
        code, out = run(["check", "--vpn-off"], StubOrg(batches))
        self.assertEqual(code, 1, out)
        self.assertIn("AB-0001", out)
        for b in batches:
            self.assertNotIn(b["Id"], out)
        self.assertNotIn("001AA0000000000ZZZ", out)


class SafeRead(unittest.TestCase):
    """The check reads explicit fields only (never Contact_IDs__c, the girls' names) and needs --vpn-off."""

    def test_the_check_reads_no_names_and_needs_vpn_off(self):
        org = StubOrg(agreeing_batches())
        code, out = run(["check", "--vpn-off"], org)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(org.seen), 1, org.seen)
        soql = org.seen[0]
        fields = selected_fields(soql)
        self.assertEqual(sorted(fields), sorted(SELECTED), soql)
        self.assertEqual(len(fields), len(set(fields)), soql)
        self.assertNotIn("Contact_IDs__c", soql)
        self.assertNotIn("*", soql)
        self.assertNotRegex(soql.upper(), r"FIELDS\s*\(")
        self.assertRegex(soql, r"\bAttendance_Date__c\s*>=\s*2026-09-01\b")

        refused = StubOrg(agreeing_batches())
        code, out = run(["check"], refused)
        self.assertNotEqual(code, 0, out)
        self.assertEqual(refused.seen, [])
        self.assertNotIn("checked", out)

    def test_since_must_be_a_date(self):
        for since in ("2026-13-01", "yesterday", "2026-10-01' OR Name != '"):
            with self.subTest(since=since):
                org = StubOrg(agreeing_batches())
                code, out = run(["check", "--vpn-off", "--since", since], org)
                self.assertNotEqual(code, 0, out)
                self.assertEqual(org.seen, [])

    def test_fields_not_deployed_yet(self):
        """Salesforce refuses a query that names a field the org does not have (HTTP 400, INVALID_FIELD):
        the check says the fields are not deployed yet (task #101) and stops."""
        for refusal in ("Salesforce did not answer a read (HTTP 400)",
                        "Salesforce did not answer a read (HTTP 400 INVALID_FIELD)"):
            with self.subTest(refusal=refusal):
                code, out = run(["check", "--vpn-off"], StubOrg(agreeing_batches(), refusal=refusal))
                self.assertNotEqual(code, 0, out)
                said = f"{code} {out}"
                self.assertIn("#101", said)
                self.assertRegex(said.lower(), r"not deployed")
                self.assertNotIn("-> OK", out)

    def test_another_refusal_is_not_called_undeployed(self):
        code, out = run(["check", "--vpn-off"], StubOrg(agreeing_batches(), refusal="Salesforce did not answer a read (HTTP 503)"))
        self.assertNotEqual(code, 0, out)
        said = f"{code} {out}"
        self.assertIn("HTTP 503", said)
        self.assertNotIn("#101", said)
        self.assertNotIn("-> OK", out)


class Definitions(unittest.TestCase):
    """glow/session_timing.py: Ryan's answers of 2026-10-22."""

    def test_session_week_and_month_examples(self):
        st = timing()
        self.assertEqual(st.session_month(date(2026, 9, 30)), "2026-09")
        self.assertEqual(st.session_week(date(2026, 10, 7)), "2026-10 week 1")
        self.assertEqual(st.session_week(date(2026, 10, 8)), "2026-10 week 2")
        self.assertEqual(st.session_week(date(2026, 10, 31)), "2026-10 week 5")
        for day, week in ((1, 1), (14, 2), (15, 3), (21, 3), (22, 4), (28, 4), (29, 5), (30, 5)):
            with self.subTest(day=day):
                self.assertEqual(st.session_week(date(2026, 9, day)), f"2026-09 week {week}")
        self.assertEqual(st.session_month(date(2026, 1, 5)), "2026-01")
        self.assertEqual(st.session_month(date(2025, 12, 31)), "2025-12")
        self.assertEqual(st.session_week(date(2025, 12, 31)), "2025-12 week 5")
        self.assertEqual(st.session_week(date(2027, 2, 28)), "2027-02 week 4")
        self.assertEqual(st.session_week(date(2028, 2, 29)), "2028-02 week 5")

    def test_session_week_every_day_of_a_year(self):
        st = timing()
        day = date(2026, 1, 1)
        while day.year == 2026:
            week = 1 + (day.day - 1) // 7          # 1-7 -> 1, 8-14 -> 2, ... 29-31 -> 5
            month = f"{day.year:04d}-{day.month:02d}"
            with self.subTest(day=day):
                self.assertEqual(st.session_month(day), month)
                self.assertEqual(st.session_week(day), f"{month} week {week}")
            day += timedelta(days=1)

    def test_delay_days_examples(self):
        st = timing()
        session = date(2026, 10, 5)
        self.assertEqual(st.delay_days(datetime(2026, 10, 6, 1, 30, tzinfo=UTC), session), 1)
        self.assertEqual(st.delay_days(datetime(2026, 10, 5, 23, 59, tzinfo=UTC), session), 0)
        self.assertEqual(st.delay_days(datetime(2026, 10, 4, 12, 0, tzinfo=UTC), session), -1)
        self.assertIsNone(st.delay_days(None, session))
        # the UTC day: an evening in the Americas is the next UTC day, a morning in India the day before
        self.assertEqual(st.delay_days(datetime(2026, 10, 5, 20, 0, tzinfo=timezone(timedelta(hours=-5))), session), 1)
        self.assertEqual(st.delay_days(datetime(2026, 10, 6, 3, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))), session), 0)
        self.assertEqual(st.delay_days(datetime(2026, 11, 1, 0, 0, tzinfo=UTC), date(2026, 10, 29)), 3)
        self.assertEqual(st.delay_days(datetime(2026, 12, 1, 6, 0, tzinfo=UTC), date(2026, 9, 1)), 91)
        self.assertEqual(st.delay_days(datetime(2027, 1, 2, 0, 0, tzinfo=UTC), date(2026, 12, 31)), 2)
        result = st.delay_days(datetime(2026, 10, 9, 0, 0, tzinfo=UTC), session)
        self.assertIsInstance(result, int)
        self.assertEqual(result, 4)

    def test_only_live_jotform_batches_have_a_submission_time(self):
        st = timing()
        self.assertEqual(st.JOTFORM_CREATOR, "Jotform")
        for dt in (datetime(2026, 10, 6, 1, 30, tzinfo=UTC), datetime(2026, 9, 14, 17, 5, 9, tzinfo=UTC)):
            with self.subTest(dt=dt):
                self.assertEqual(st.submitted_at("Jotform", dt), dt)
                for creator in ("Jotform back-fill 001AA 123", "Jotform back-fill 2026-09", BACKFILL,
                                "Partner report", "", None):
                    self.assertIsNone(st.submitted_at(creator, dt), creator)
        self.assertIsNone(st.submitted_at("Jotform", None))

    def test_sf_formulas_are_the_four_deployed_texts(self):
        st = timing()
        self.assertEqual(st.SF_FORMULAS, FORMULAS)

    def test_no_late_threshold_or_flag(self):
        """Ryan 2026-10-22: no "big delay" threshold and no flag; staff read the delay themselves."""
        st = timing()
        self.assertFalse(hasattr(st, "LATE_DAYS"))
        self.assertFalse(hasattr(st, "is_late"))


if __name__ == "__main__":
    unittest.main()
