#!/usr/bin/env python3
"""
Offline tests for glow/session_timing.py and tools/sf_session_timing.py check (ticket #100; found by
`make py`'s unittest discovery). Ryan's answers (2026-10-22): the session week is the week of the
month by day (1-7 week 1 ... 29-31 week 5, `2026-10 week 2`), the submission day is the UTC day, and
there is no "big delay" threshold or flag. Everything here is fictional: batch ids, batch Names
(`AB-0001`), account ids and dates are invented. A stub org answers the check's one SOQL query with
Salesforce's REST shapes (CreatedDate `2026-10-06T01:30:00.000+0000`, a Date `2026-10-05`, a Number
as a float) and the formula values Salesforce would compute, written out by hand below.

Ticket #101 deploys the four fields; its repo side is documentation, checked by SubmissionTimingDocs:
the RUNBOOK section "Submission timing in Salesforce" and the plan in docs/plans/ that carries the
live change (found by its ticket reference, never by a date).
"""
import contextlib
import copy
import glob
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
from helpers.common import flat, md_part, read, sentences  # noqa: E402

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


def prose(body):
    """`body` (flattened) with the dots inside code spans turned into middle dots, so a `[^.]{0,N}`
    window and a sentence split read across a quoted path or command (`sf_session_timing.py`,
    `destructiveChanges.xml`) and stop at a sentence end only."""
    return re.sub(r"`[^`]*`", lambda m: m.group(0).replace(".", "·"), body)


def near(first, second, window=250):
    """A regex: `first` then `second`, or `second` then `first`, within `window` characters of one
    sentence (no sentence end between)."""
    return re.compile(rf"(?i)(?:{first})[^.]{{0,{window}}}?(?:{second})|(?:{second})[^.]{{0,{window}}}?(?:{first})")


# A statement is affirmed only when the clause that carries it has no negation: "days 1-7 are not week
# 1", "the submission day is never the UTC day", "no --dry-run is needed", "Ryan's go is not required",
# "do not compare", "skip the check", "unrelated to" say the opposite of what the ticket asks. A clause
# ends at a sentence end, a comma, a semicolon, a colon, a parenthesis or a spaced dash, so "the same
# command without `--dry-run`" and "compare (no difference expected)" still count. The week rule and
# the time-zone rule are scanned over their whole sentence: a contrast ("not the mentor's local day")
# goes in a sentence of its own.
NEGATION = re.compile(r"(?i)\b(?:not|never|no|none|nor|isn't|aren't|wasn't|don't|doesn't|cannot|can't|won't|"
                      r"skip\w*|omit\w*|optional|unnecessary|needless|rather than|instead of|"
                      r"wrong\w*|false\w*|incorrect\w*|opposite|unrelated|irrelevant)\b")
CLAUSE_END = re.compile(r"[.,;:()]|\s[-–—]\s")
LIST_ITEM = re.compile(r"(?:\d+[.)]|[-*•])\s+")


def clause_of(text, at):
    """The clause of `text` around offset `at`: from the clause end before it to the one after."""
    start = max((m.end() for m in CLAUSE_END.finditer(text, 0, at)), default=0)
    end = CLAUSE_END.search(text, at)
    return text[start:end.start() if end else len(text)]


def clauses(sentence):
    """The non-empty clauses of a sentence, in order."""
    return [c for c in CLAUSE_END.split(sentence) if c and c.strip()]


def negated(text, m):
    """A match whose clause at its start or at its end carries a negation (a window that spans clauses
    is judged by its two anchors: "(no difference expected)" between them is not a negation of either)."""
    return bool(NEGATION.search(clause_of(text, m.start())) or NEGATION.search(clause_of(text, max(m.end() - 1, m.start()))))


def affirmed(text, pattern, start=0):
    """The first match of `pattern` in `text` at or after `start` that is not negated; None when every
    match is."""
    for m in pattern.finditer(text, start):
        if not negated(text, m):
            return m
    return None


def denied(text, pattern):
    """The first negated match of `pattern` in `text`, else None: a step the text argues against."""
    for m in pattern.finditer(text):
        if negated(text, m):
            return m
    return None


def sentence_at(text, at):
    """The sentence of `text` (flattened, prose()) around offset `at`."""
    start = max((m.end() for m in re.finditer(r"[.;]\s", text[:at])), default=0)
    end = re.search(r"[.;](?:\s|$)", text[at:])
    return text[start:at + end.start() if end else len(text)]


def list_items(part):
    """The numbered or bulleted items of a Markdown part, in order, each flattened: an item starts at an
    unindented marker line and runs over its indented lines and lazy continuations; a blank line, a
    paragraph after one or a heading ends it. Text outside the items (an intro, a trailing line) is
    not an item."""
    items, current, open_ = [], [], False
    for line in part.splitlines():
        if LIST_ITEM.match(line):
            current = [line[LIST_ITEM.match(line).end():]]
            items.append(current)
            open_ = True
        elif not line.strip() or line.startswith("#"):
            open_ = False
        elif open_ and (line[:1].isspace() or line.lstrip()[:1] not in "-*•"):
            current.append(line)
        else:
            open_ = False
    return [flat(" ".join(item)) for item in items]


class SubmissionTimingDocs(unittest.TestCase):
    """Ticket #101: the four formula fields are deployed on Ryan's go; what the repo keeps is the
    documentation. docs/RUNBOOK.md "Submission timing in Salesforce" (that section alone, to the
    next `## `) names the four formula fields of `Attendance_Batch__c` by API name, each in its own
    sentence that says what it is, the week rule (days 1-7 week 1, 8-14 week 2, 15-21 week 3, 22-28
    week 4, 29-31 week 5, shown as `2026-10 week 2`), the time zone (the submission day is the UTC
    day), which batches have no submission time (only `Creator__c` exactly `Jotform` has one - the
    September back-fill and the `Partner report` batches have none), the check command and the
    rollback (a destructive deploy of the fields, or the plan's path). A plan in docs/plans/ naming
    #101 in its head (frontmatter, title or the paragraphs before the first section) carries the
    live change, for tasks #101-#103: its Rollout's numbered steps have, in this order, the retrieve
    into `before/`, the `CreatedDate` proof, the check-only deploy (`--dry-run`), Ryan's go, the
    deploy, the read-back (retrieve into `after/`, compared with the build) and the check, and no
    step is argued against anywhere in the Rollout; its Rollback deletes the four fields by a
    destructive deploy (`destructiveChanges`) after the reports that use them, the reports' step
    first. Meaning, not sentences: tolerant matching on the names and the key commands, but a
    negated statement does not count, and the steps are found in sequence."""

    RUNBOOK = os.path.join(REPO, "docs", "RUNBOOK.md")
    HEADING = "## Submission timing in Salesforce"
    CHECK = re.compile(r"\bsf_session_timing[.·]py check\b")
    LADDER = ((1, 7, 1), (8, 14, 2), (15, 21, 3), (22, 28, 4), (29, 31, 5))
    NONE = r"\b(?:no|none|not|never|blank|empty|null|without)\b"
    ONLY = r"\b(?:only|exactly|alone|just|nothing else)\b"
    SUBMISSION = re.compile(r"(?i)submission time|submitted at|Submitted_At__c|CreatedDate")
    A_FIELD = r"\bfields?\b|" + "|".join(FIELDS)
    # what each field is, said within ~60 characters of its name, in a sentence that names it alone
    MEANINGS = {
        "Submitted_At__c": (r"CreatedDate", "the batch's `CreatedDate`"),
        "Submission_Delay_Days__c": (r"\bdays?\b", "days, from the session date"),
        "Session_Month__c": (r"\b\d{4}-(?:0[1-9]|1[0-2])\b", "a `YYYY-MM` month"),
        "Session_Week__c": (r"\bweek\b", "the week of the month"),
    }
    READS = r"\bread\w*|\baccess\w*|\bvisib\w*|\bFLS\b|field-?level"
    ROLLOUT_STEPS = (
        ("retrieve what is live into `before/`, first", near(r"\bretriev\w*", r"before/")),
        ("the proof that `CreatedDate` is the submission time (the Jotform submission created within 10 minutes of "
         "it), after the retrieve", near(r"CreatedDate", r"\bproo?f\w*|\bprove[sdn]?\b|within \d+ minutes")),
        ("the check-only deploy (`sf project deploy start --dry-run`), after the proof",
         near(r"--dry-run", r"check-only|\bvalidat\w*|sf project deploy start", 120)),
        ("Ryan's go, after the check-only deploy", near(r"\bRyan'?s?\b", r"\bgo\b", 40)),
        ("the deploy, after the go", re.compile(r"(?i)\bdeploy\w*")),
        ("the read-back after the deploy: retrieve into `after/`", near(r"\bretriev\w*", r"after/")),
        ("the read-back compares `after/` with the build", near(r"after/", r"\bcompar\w*")),
        ("the check `sf_session_timing.py check`, after the read-back", CHECK),
    )

    def section(self):
        """The section's text, flattened; a missing heading fails here (md_part)."""
        return flat(md_part(self.RUNBOOK, self.HEADING))

    def test_the_runbook_defines_the_four_fields_and_the_check(self):
        raw = self.section()
        text = prose(raw)
        where = f"RUNBOOK section {self.HEADING[3:]!r}"
        said = sentences(text, ".;")
        self.assertIn("Attendance_Batch__c", raw, f"{where}: the fields are on `Attendance_Batch__c`")
        self.assertRegex(raw, r"(?i)\bformula", f"{where}: say they are formula fields (they change no record)")
        # the four fields, by API name, each in its own sentence that says what it is
        for field, (meaning, hint) in self.MEANINGS.items():
            with self.subTest(field=field):
                self.assertIn(field, raw, f"{where}: name the field `{field}`")
                own = [s for s in said if field in s and sum(f in s for f in FIELDS) == 1]
                self.assertTrue([s for s in own if affirmed(s, near(field, meaning, 60))],
                                f"{where}: say what `{field}` is ({hint}) within about 60 characters of its name, in a "
                                "sentence that names no other field; a negation in that clause does not count")
        self.assertTrue([s for s in said if "Submission_Delay_Days__c" in s and sum(f in s for f in FIELDS) == 1
                         and affirmed(s, near("Submission_Delay_Days__c", r"Attendance_Date__c|\bsession\b", 60))],
                        f"{where}: the delay counts from the session date (`Attendance_Date__c`), said of "
                        "`Submission_Delay_Days__c`")
        # the week rule: the week of the month by day, the whole ladder in a sentence that argues against
        # nothing, shown as `2026-10 week 2`
        for lo, hi, week in self.LADDER:
            with self.subTest(days=f"{lo}-{hi}"):
                rung = near(rf"\b{lo}\s*(?:-|–|to)\s*{hi}\b", rf"\bweek {week}\b", 60)
                self.assertTrue([s for s in said if rung.search(s) and not NEGATION.search(s)],
                                f"{where}: say days {lo}-{hi} are week {week} (the rule by day of the month) in a "
                                "sentence with no negation at all")
        self.assertRegex(raw, r"\b\d{4}-(?:0[1-9]|1[0-2]) week [1-5]\b",
                         f"{where}: show the shape of a session week, `2026-10 week 2`")
        # the time zone: the day a batch was submitted (what the delay counts to) is the UTC day, in a
        # sentence that argues against nothing
        utc = near(r"\bUTC\b", r"\bday\b", 60)
        self.assertTrue([s for s in said if re.search(r"(?i)submi|delay", s) and utc.search(s) and not NEGATION.search(s)],
                        f"{where}: say the submission day (the delay's end) is the UTC day, in a sentence with no "
                        "negation at all (a contrast goes in its own sentence)")
        # which batches have a submission time: only `Creator__c` exactly `Jotform`, said of the submission
        # time in the same or the next clause; the back-fill and the partners' `Partner report` batches have none
        self.assertIn("Creator__c", raw, f"{where}: name `Creator__c`, which decides whether a batch has a submission time")
        self.assertTrue([s for s in said if re.search(f"(?i){self.ONLY}", s) and self.creator_jotform_has_submission_time(s)],
                        f"{where}: say only a batch whose `Creator__c` is exactly `Jotform` has a submission time "
                        "(`Submitted_At__c`), the submission time in the same or an adjacent clause, neither negated")
        for kind, pattern in (("back-fill", r"(?i)back-?fill"), ("Partner report", r"Partner report")):
            with self.subTest(batches=kind):
                self.assertTrue([s for s in said if re.search(pattern, s) and re.search(f"(?i){self.NONE}", s)
                                 and re.search(r"(?i)submi|Submitted_At__c|delay", s)],
                                f"{where}: say the {kind} batches have no submission time (and so no delay)")
        # the check, with the VPN off like every sf call, and the rollback: the destructive deploy of the
        # fields, or the plan's path
        self.assertRegex(raw, r"\bsf_session_timing\.py check\b",
                         f"{where}: quote the check `python3 tools/sf_session_timing.py check --vpn-off`")
        self.assertIn("--vpn-off", raw, f"{where}: the check runs with `--vpn-off` (VPN off before any sf call)")
        self.assertTrue([s for s in said if re.search(r"(?i)\broll ?back", s)
                         and (("destructiveChanges" in s and re.search(f"(?i){self.A_FIELD}", s))
                              or re.search(r"plans/[\w-]+[.·]md", s))],
                        f"{where}: say how the fields are rolled back - a destructive deploy (`destructiveChanges`) of "
                        "the fields, or the plan's path for its Rollback - in one sentence")

    @classmethod
    def creator_jotform_has_submission_time(cls, sentence):
        """`Creator__c` and `Jotform` in one clause, the submission time in that clause or the one before or
        after, none of them negated."""
        parts = clauses(sentence)
        for i, clause in enumerate(parts):
            if "Creator__c" in clause and re.search(r"\bJotform\b", clause) and not NEGATION.search(clause):
                for j in (i - 1, i, i + 1):
                    if 0 <= j < len(parts) and cls.SUBMISSION.search(parts[j]) and not NEGATION.search(parts[j]):
                        return True
        return False

    def plans_naming(self, ticket):
        """The plans whose head (frontmatter, title or the paragraphs before the first section) names the ticket."""
        return [p for p in sorted(glob.glob(os.path.join(REPO, "docs", "plans", "*.md")))
                if os.path.basename(p) != "README.md"
                and re.search(rf"(?<![\w#])#{ticket}\b", read(p).split("\n## ", 1)[0])]

    def test_a_plan_carries_the_check_only_go_deploy_and_read_back(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        plans = self.plans_naming(101)
        self.assertTrue(plans, "docs/plans/: no plan names ticket #101 in its frontmatter, title or opening paragraph "
                               "(the four formula fields are a live Salesforce change: CLAUDE.md conventions)")
        for path in plans:
            name = os.path.relpath(path, REPO)
            text = read(path)
            keys, _ = docs_index.frontmatter(text)
            self.assertIn("status", keys, f"{name}: frontmatter `status:`")
            _, problem = docs_index.status_of(keys["status"])
            self.assertIsNone(problem, f"{name}: {problem}")
            whole = prose(flat(text))
            for ticket in ("#102", "#103"):
                self.assertRegex(whole, rf"(?<![\w#]){ticket}\b", f"{name}: the plan covers tasks #101-#103 ({ticket})")
            # the viewers' permission set and the Admin profile read the fields (a field a viewer cannot
            # read silently drops a report filter)
            for who, pattern in (("the permission set `Attendance_Report_Viewer`", r"Attendance_Report_Viewer"),
                                 ("the Admin profile", r"\bAdmin\b[^.]{0,40}?\bprofile\b|\bprofile\b[^.]{0,40}?\bAdmin\b")):
                self.assertTrue(affirmed(whole, near(pattern, self.READS, 200)),
                                f"{name}: {who} reads the fields (say so, not just that it exists)")
                self.assertTrue(affirmed(whole, near(pattern, self.A_FIELD, 200)),
                                f"{name}: {who} reads the fields: name the fields (or `fields`) near it")
            bodies, parts = {}, {}
            for heading, least in (("## Rollout", 60), ("## Rollback", 30), ("## Risks", 15), ("## Result", 0)):
                part = md_part(path, heading)
                parts[heading] = part.split("\n", 1)[1] if "\n" in part else ""
                body = flat(parts[heading])
                self.assertNotRegex(body, r"(?i)\b(TBD|TODO|TBA|FIXME)\b", f"{name}: `{heading}` is a placeholder")
                self.assertGreaterEqual(len(re.findall(r"\w+", body)), least,
                                        f"{name}: `{heading}` says too little (at least {least} words): the steps")
                bodies[heading] = body
            self.rollout_is_retrieve_proof_check_only_go_deploy_read_back_check(name, parts["## Rollout"])
            self.rollback_deletes_the_fields_after_the_reports(name, bodies["## Rollback"])
            self.risks_name_a_real_risk(name, bodies["## Risks"])

    def rollout_is_retrieve_proof_check_only_go_deploy_read_back_check(self, name, part):
        """The steps in this order over the Rollout's list items (an intro or a trailing line is not a
        step), each found at or after the one before it and affirmed; and no step argued against anywhere
        in the Rollout."""
        where, text = f"{name}: Rollout", prose(flat(part))
        self.assertIn("sf project deploy start", text, f"{where}: the deploy command `sf project deploy start`")
        for what, pattern in self.ROLLOUT_STEPS:
            if pattern.pattern != r"(?i)\bdeploy\w*":        # "never deploy an older package" is a rule, not a step
                m = denied(text, pattern)
                self.assertIsNone(m, f"{where}: argues against a step - {what}: {clause_of(text, m.start()).strip()!r}"
                                     if m else None)
        items = list_items(part)
        self.assertGreaterEqual(len(items), 3, f"{where}: the steps as a numbered (or bulleted) list, in order")
        walk = " . ".join(prose(item) for item in items)
        at = 0
        for what, pattern in self.ROLLOUT_STEPS:
            m = affirmed(walk, pattern, at)
            self.assertTrue(m, f"{where}: {what} (the steps in that order, in the list's items; a negated statement "
                               "does not count)")
            at = m.start()
        self.assertTrue(affirmed(walk, near(r"after/", r"\bbuild\b")),
                        f"{where}: the read-back is compared with the build (`build/`), in a step")

    def rollback_deletes_the_fields_after_the_reports(self, name, rollback):
        where, text = f"{name}: Rollback", prose(rollback)
        self.assertIn("destructiveChanges", rollback,
                      f"{where}: the four fields go by a destructive deploy (`destructiveChanges.xml`)")
        for field in FIELDS:
            self.assertIn(field, rollback, f"{where}: name the field `{field}` it deletes")
        deletion = near(r"\breports?\b", r"\b(?:delet\w*|remov\w*|drop\w*|destructive|edit\w*|first)\b")
        # the reports' step: the reports that use (filter on) the fields are deleted or edited
        uses = re.compile(r"(?i)\b(?:use[sd]?|using|filter\w*|read\w*|depend\w*|built on|based on|need\w*)\b")
        steps = [m for m in deletion.finditer(text) if not negated(text, m)
                 and uses.search(sentence_at(text, m.start())) and re.search(f"(?i){self.A_FIELD}", sentence_at(text, m.start()))]
        self.assertTrue(steps, f"{where}: delete (or edit) the reports that use the fields, said in one sentence - a field "
                               "a report filters on cannot be deleted")
        # the fields' destructive deploy: the first `destructiveChanges` whose sentence names a field, else the first
        mentions = [m.start() for m in re.finditer(r"destructiveChanges", text)]
        fields_deploy = next((p for p in mentions if re.search(f"(?i){self.A_FIELD}", sentence_at(text, p))), mentions[0])
        self.assertLess(steps[0].start(), fields_deploy,
                        f"{where}: the reports' step comes before the fields' destructive deploy (order matters: a field "
                        "a report uses cannot be deleted)")
        late = affirmed(text, deletion, fields_deploy)
        self.assertIsNone(late, f"{where}: a report deletion after the fields' destructive deploy: "
                                f"{sentence_at(text, late.start()).strip()!r} - the reports go first" if late else None)

    def risks_name_a_real_risk(self, name, risks):
        where = f"{name}: Risks"
        self.assertNotRegex(risks, r"(?i)^\W*(?:none|no risks?|n/?a|nothing|hardly|few|little|minimal|negligible|harmless)\b",
                            f"{where}: name at least one real risk (no dismissive opening)")
        self.assertRegex(risks, r"(?i)CreatedDate|permission|filter|formula|deploy|\bfields?\b|\breports?\b",
                         f"{where}: a risk of this change (the `CreatedDate` assumption, a viewer who cannot read a "
                         "field, the deploy)")


if __name__ == "__main__":
    unittest.main()
