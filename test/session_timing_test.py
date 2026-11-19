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

Ticket #102 builds the four timing reports on those fields (Salesforce metadata, deployed on Ryan's
go); its repo side is the same RUNBOOK section, checked by TimingReportsDocs: the four reports by
DeveloperName, each with the SOQL check that reproduces it beside its name, and Ryan's answers of
2026-10-24 on who is left out of the weekly not-submitting list and what "not submitting" means.

Ticket #103 puts three of those reports on the "Jotform Attendance" dashboard (four components and
the timing in its "How to read this dashboard" box; deployed on Ryan's go); its repo side is the
RUNBOOK section "Attendance dashboard in Salesforce" and the plan's "Task #103" section, checked by
DashboardTimingDocs. The build in `data/` is never committed and never read here.

Live finding (2026-10-24, after the first deploy): Salesforce's DATEVALUE(<date/time>) converts in the
org's time zone (America/Los_Angeles), not UTC, so `DATEVALUE(Submitted_At__c)` gave a delay one day
short for every submission between 00:00 and about 07:00 UTC (153 of 1,123 batches). Ryan kept the UTC
day (DECISIONS 2026-10-23) and the delay formula takes it through `DATEVALUE(TEXT(Submitted_At__c))`:
TEXT() of a date/time is the UTC timestamp 'YYYY-MM-DD HH:MM:SSZ', and DATEVALUE of that text is its
UTC date. FORMULAS below is the deployed text; Definitions.test_delay_formula_takes_the_utc_date_through_text
records why.
"""
import contextlib
import copy
import csv
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
    "Submission_Delay_Days__c": "IF(ISBLANK(Submitted_At__c), NULL, DATEVALUE(TEXT(Submitted_At__c)) - Attendance_Date__c)",
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

    def test_delay_formula_takes_the_utc_date_through_text(self):
        """Why the delay formula is `DATEVALUE(TEXT(Submitted_At__c))` and never `DATEVALUE(Submitted_At__c)`:
        Salesforce's DATEVALUE on a date/time converts in the org's zone (America/Los_Angeles), so a form
        submitted 2026-10-02T04:52Z for a session on 2026-09-17 came out as 14 days (its Los Angeles day is
        10-01), one short of the UTC rule's 15 (live, 2026-10-24: 153 of 1,123 batches). TEXT() of a date/time
        is the UTC timestamp 'YYYY-MM-DD HH:MM:SSZ' and DATEVALUE of that text is its UTC date, which is what
        glow/session_timing.py counts and what the check expects."""
        st = timing()
        self.assertEqual(st.delay_days(datetime(2026, 10, 2, 4, 52, tzinfo=UTC), date(2026, 9, 17)), 15)
        delay = st.SF_FORMULAS["Submission_Delay_Days__c"]
        self.assertIn("DATEVALUE(TEXT(Submitted_At__c))", delay)
        for name, formula in st.SF_FORMULAS.items():
            with self.subTest(field=name):
                self.assertNotRegex(formula, r"DATEVALUE\(\s*(?:Submitted_At__c|CreatedDate)\s*\)",
                                    f"{name}: DATEVALUE on a date/time field uses the org's zone, not UTC; "
                                    "take the UTC date with DATEVALUE(TEXT(<date/time>))")

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


def clause_span(text, at):
    """The [start, end) of the clause of `text` around offset `at`: from the clause end before it to the
    one after."""
    start = max((m.end() for m in CLAUSE_END.finditer(text, 0, at)), default=0)
    end = CLAUSE_END.search(text, at)
    return start, (end.start() if end else len(text))


def clause_of(text, at):
    """The clause of `text` around offset `at`."""
    start, end = clause_span(text, at)
    return text[start:end]


def clauses(sentence):
    """The non-empty clauses of a sentence, in order."""
    return [c for c in CLAUSE_END.split(sentence) if c and c.strip()]


# "is not", "is never", "not required", "optional": a denial wherever it stands in the clause
PREDICATE_NEGATION = re.compile(r"(?i)\b(?:is|are|was|were|be)\s+(?:not|never|no)\b|\bnot\s+(?:required|needed|necessary)\b|"
                                r"\b(?:optional|unnecessary|needless|skipped|omitted)\b")


def negated(text, m):
    """A match denied by the clause at its start or the clause at its end: a negation word in that clause
    before the match's end ("do not retrieve into `before/`", "`CreatedDate` needs no proof", "`after/`
    and do not compare"), or a predicate negation anywhere in it ("Ryan's go is not required"). A
    negation after the match in its clause ("`sf project deploy start -o glow` (no `--dry-run`)" is
    read from the deploy command on) and one between the anchors of a window that spans clauses ("(no
    difference expected)") deny nothing."""
    for at in (m.start(), max(m.end() - 1, m.start())):
        start, end = clause_span(text, at)
        if NEGATION.search(text, start, min(end, m.end())) or PREDICATE_NEGATION.search(text, start, end):
            return True
    return False


def matches(text, pattern, start=0):
    """The non-overlapping matches of `pattern` in `text` from `start`, each tightened to the latest start
    that keeps its end: "a fresh retrieve: retrieve what is live into `before/`" is judged from the
    second retrieve, in its own clause."""
    pos = start
    while True:
        m = pattern.search(text, pos)
        if not m:
            return
        while True:
            tighter = pattern.search(text, m.start() + 1)
            if tighter and tighter.end() == m.end():
                m = tighter
            else:
                break
        yield m
        pos = max(m.end(), m.start() + 1)


def affirmed(text, pattern, start=0):
    """The first match of `pattern` in `text` at or after `start` that is not negated; None when every
    match is."""
    for m in matches(text, pattern, start):
        if not negated(text, m):
            return m
    return None


def denied(text, pattern):
    """The first negated match of `pattern` in `text`, else None: a step the text argues against."""
    for m in matches(text, pattern):
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
        # `--dry-run` said of a check-only or validation, or inside the deploy command itself: "`sf project
        # deploy start -o glow` (no `--dry-run`)" is the real deploy, not this step
        ("the check-only deploy (`sf project deploy start --dry-run`), after the proof",
         re.compile(r"(?i)(?:check-only|\bvalidat\w*)[^.]{0,120}?--dry-run|--dry-run[^.]{0,120}?(?:check-only|\bvalidat\w*)|"
                    r"sf project deploy start[^.(]{0,80}?--dry-run")),
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

    def test_the_plan_quotes_the_four_formulas_verbatim(self):
        """The plan's Build table is what goes into `build/` and is read back from Salesforce: each of the
        four formula texts stands in the plan exactly as FORMULAS has it (the delay one through
        `DATEVALUE(TEXT(...))`, the 2026-10-24 finding), and no plan still carries the first deploy's
        `DATEVALUE(Submitted_At__c)` as a formula to build."""
        plans = self.plans_naming(101)
        self.assertTrue(plans, "docs/plans/: no plan names ticket #101 in its head")
        for path in plans:
            name, text = os.path.relpath(path, REPO), read(path)
            for field, formula in FORMULAS.items():
                with self.subTest(plan=name, field=field):
                    self.assertTrue(formula in text, f"{name}: quote `{field}`'s formula verbatim: {formula}")
            self.assertFalse("`IF(ISBLANK(Submitted_At__c), NULL, DATEVALUE(Submitted_At__c) - Attendance_Date__c)`" in text,
                             f"{name}: the first deploy's formula (DATEVALUE on the date/time: the org's zone, a day "
                             "short before ~07:00 UTC) is still quoted as a formula to build")

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
        steps = [m for m in matches(text, deletion) if not negated(text, m)
                 and uses.search(sentence_at(text, m.start())) and re.search(f"(?i){self.A_FIELD}", sentence_at(text, m.start()))]
        self.assertTrue(steps, f"{where}: delete (or edit) the reports that use the fields, said in one sentence - a field "
                               "a report filters on cannot be deleted")
        # the fields' destructive deploy: the first `destructiveChanges` whose sentence names a field, else the first
        mentions = [m.start() for m in re.finditer(r"destructiveChanges", text)]
        fields_deploy = next((p for p in mentions if re.search(f"(?i){self.A_FIELD}", sentence_at(text, p))), mentions[0])
        self.assertLess(steps[0].start(), fields_deploy,
                        f"{where}: the reports' step comes before the fields' destructive deploy (order matters: a field "
                        "a report uses cannot be deleted)")
        # a reports' step after the fields' deploy: a deletion verb and a uses-verb in its sentence ("leaves every
        # other report untouched" is not one)
        late_deletion = near(r"\breports?\b", r"\b(?:delet\w*|remov\w*|drop\w*|edit\w*)\b")
        late = next((m for m in matches(text, late_deletion, fields_deploy)
                     if not negated(text, m) and uses.search(sentence_at(text, m.start()))), None)
        self.assertIsNone(late, f"{where}: a report deletion after the fields' destructive deploy: "
                                f"{sentence_at(text, late.start()).strip()!r} - the reports go first" if late else None)

    def risks_name_a_real_risk(self, name, risks):
        where = f"{name}: Risks"
        self.assertNotRegex(risks, r"(?i)^\W*(?:none|no risks?|n/?a|nothing|hardly|few|little|minimal|negligible|harmless)\b",
                            f"{where}: name at least one real risk (no dismissive opening)")
        self.assertRegex(risks, r"(?i)CreatedDate|permission|filter|formula|deploy|\bfields?\b|\breports?\b",
                         f"{where}: a risk of this change (the `CreatedDate` assumption, a viewer who cannot read a "
                         "field, the deploy)")


# Ticket #102: the four timing reports, by DeveloperName (the outline's names)
REPORTS = ("Clubs_Not_Submitting_Last_Week", "Submissions_by_Club_and_Week",
           "Late_Submissions_Last_Month", "Submission_Delay_by_Partner_by_Month")
# The three partners whose clubs report monthly through Salesforce, off the forms since 2026-10-16
# (RUNBOOK "Clubs that do not use Jotform", DECISIONS 2026-10-06/-15/-19); spelled as their Salesforce
# accounts are (glow/sf_partners.csv). Partner names, never girls' names.
MONTHLY_PARTNERS = ("Education and English for You", "Tumaini La Maisha", "Ng'aa Maskani")
# A SOQL statement in a code span: a `SELECT` that is not a subquery's (not right after an opening
# parenthesis), to the end of its code span (the next backtick, inline or a fence's)
STATEMENT = re.compile(r"(?<!\()(?<!\(\s)\bSELECT\b[^`]*")
# A negation within two words before a phrase, inside its clause: "does not leave out", "never left
# out", "is not needed", "not descending", "rather than left out". "The clubs that do not report
# through Jotform are left out" has four words between and affirms.
NEG_BEFORE = (r"(?:\bnot|\bnever|\bno|\bno longer|\bnothing|\bnor|\bneither|\bwithout|\brather than|\binstead of|n't)"
              r"\s+(?:[\w'`]+\s+){0,2}$")
# A run-in label ("**Who is left out** (Ryan, 2026-10-24):") at a sentence's start is not a statement
LABEL = r"^\*\*[^*]{1,80}\*\*\s*(?:\([^)]*\)\s*)?:?\s*"


def partner(name):
    """A regex for a partner's account name in prose or in SOQL: the apostrophe straight, typographic
    or SOQL-escaped (`Ng\\'aa Maskani`)."""
    return re.escape(name).replace("'", r"\\?['’]")


def us_partner_accounts():
    """The Salesforce account names of the partners whose clubs are in the U.S: `appsscript/Regions.gs`
    PARTNER_REGIONS (region `U.S`; the clubs-off plan: 11 clubs of 6 partners) mapped through
    `glow/sf_partners.csv` (partner -> account name; a partner without an account has no club
    accounts to leave out). The repo's own data, not the RUNBOOK: the weekly list's filter on partner
    account names must name them, or the U.S clubs pad it."""
    regions = read(os.path.join(REPO, "appsscript", "Regions.gs")).split("PARTNER_REGIONS = {", 1)[1].split("};", 1)[0]
    us = {p.replace("\\'", "'") for p in re.findall(r"^\s*'((?:[^'\\]|\\.)*)':\s*'U\.S'", regions, re.M)}
    with open(os.path.join(REPO, "glow", "sf_partners.csv"), encoding="utf-8", newline="") as f:
        return [row["sf_account_name"] for row in csv.DictReader(f) if row["partner"] in us]


def affirms(sentence, pattern, denied=None, flags=re.I):
    """The first match of `pattern` in `sentence` (case-insensitive unless `flags` says otherwise) that its
    clause does not deny: no negation within two words before it (NEG_BEFORE) and no `denied` phrase
    in its clause."""
    for m in re.finditer(pattern, sentence, flags):
        start, end = clause_span(sentence, m.start())
        if re.search(f"(?i){NEG_BEFORE}", sentence[start:m.start()]):
            continue
        if denied and re.search(f"(?i){denied}", sentence[start:end]):
            continue
        return m
    return None


def without_subqueries(statement):
    """The SOQL statement with every `(SELECT ...)` subquery, and whatever it nests, taken out."""
    out, depth, i = [], 0, 0
    while i < len(statement):
        if depth == 0 and re.match(r"\(\s*SELECT\b", statement[i:]):
            depth, i = 1, i + 1
            continue
        if depth:
            depth += {"(": 1, ")": -1}.get(statement[i], 0)
        else:
            out.append(statement[i])
        i += 1
    return "".join(out)


def duplicate_equals(statement):
    """The fields with more than one `=` predicate in the statement's own WHERE (subqueries taken out):
    `Attendance_Date__c = LAST_MONTH AND Attendance_Date__c = 2026-09-01` reads two windows at once."""
    m = re.search(r"\bWHERE\b(.*?)(?:\bGROUP\s+BY\b|\bORDER\s+BY\b|\bLIMIT\b|\bHAVING\b|$)", without_subqueries(statement), re.S)
    if not m:
        return []
    fields = re.findall(r"\b([A-Za-z_][\w.]*)\s*=(?!=)", m.group(1))
    return sorted({f for f in fields if fields.count(f) > 1})


def blocks(part):
    """The blocks of a Markdown part, each flattened: a paragraph (to a blank line or a heading), a
    top-level list item with its indented lines, nested items and lazy continuations (as list_items),
    or a table row. The unit a report's name and its SOQL check must share."""
    out, current = [], []

    def close():
        if current:
            out.append(flat(" ".join(current)))
            del current[:]

    for line in part.splitlines():
        if not line.strip() or line.startswith("#"):
            close()
        elif line.lstrip().startswith("|"):
            close()
            out.append(flat(line))
        elif LIST_ITEM.match(line):
            close()
            current.append(line[LIST_ITEM.match(line).end():])
        else:
            current.append(line)
    close()
    return out


def soql_checks(part):
    """{report: [statement, ...]}: every SOQL statement of a Markdown part, tied to the report it
    checks - the last of the four report names before it in the same block (a paragraph, a top-level
    list item with its nested lines, a table row), else the first named after it in that block. A
    statement in a block that names no report is nobody's check: a list of names and, elsewhere, a
    list of queries ties nothing."""
    checks = {report: [] for report in REPORTS}
    for block in blocks(part):
        named = sorted((m.start(), report) for report in REPORTS for m in re.finditer(rf"\b{report}\b", block))
        for m in STATEMENT.finditer(block):
            before = [report for at, report in named if at < m.start()]
            after = [report for at, report in named if at >= m.end()]
            if before:
                checks[before[-1]].append(m.group(0).strip())
            elif after:
                checks[after[0]].append(m.group(0).strip())
    return checks


class TimingReportsDocs(unittest.TestCase):
    """Ticket #102: the four timing reports are Salesforce metadata in the Attendance folder, deployed on
    Ryan's go; what the repo keeps is docs/RUNBOOK.md "Submission timing in Salesforce" (that section
    alone, to the next `## `). It names the four reports by DeveloperName and their folder, and beside
    each name - in the same bullet, paragraph or table row, the name first - the SOQL check that
    reproduces the report's total (DoD: "each report's totals equal its SOQL check"): Accounts of
    record type Club with a parent and no `Attendance_Batch__c` dated `LAST_WEEK`; batches counted by
    club and `Session_Week__c`; live Jotform `Success` batches of `LAST_MONTH` with their
    `Submission_Delay_Days__c`; `AVG` and `MAX` of the delay by partner and `Session_Month__c`. Four
    distinct statements: one query cannot stand for two reports.

    And it records Ryan's answers of 2026-10-24 (ticket #102, comments): the clubs of the three
    monthly-reporting partners (Education and English for You, Tumaini La Maisha, Ng'aa Maskani) and
    the U.S clubs are left out of the weekly not-submitting list by a filter on their partner account
    names, hand-kept, so a new partner of that kind needs a report edit; `Submissions_by_Club_and_Week`
    is unaffected; "not submitting last week" is no batch of any status whose session date
    (`Attendance_Date__c`) is in last week, Sunday to Saturday (`LAST_WEEK`), with no new field; the
    late report has no cut-off and lists largest delay first. The U.S clubs' partner accounts come from
    `appsscript/Regions.gs` (region `U.S`) through `glow/sf_partners.csv`, and the weekly list's SOQL
    must exclude them by `Parent.Name` with the three partners. Meaning, not sentences: tolerant
    matching on the names and the key words; a statement with a negation right before it ("does not
    leave out", "not the Attendance folder", "not descending") or denied in its own clause ("changes
    nothing") does not count, and a never-true predicate (`= null`, `LIMIT 0`) disqualifies a SOQL."""

    RUNBOOK = SubmissionTimingDocs.RUNBOOK
    HEADING = SubmissionTimingDocs.HEADING
    FOLDER = r"\bAttendance\b(?: reports?)? folder\b|\bfolder\b[ \"“']*Attendance\b"
    BATCHES = ("batches (`FROM Attendance_Batch__c`)", r"\bFROM\s+Attendance_Batch__c\b")
    JOTFORM = ("live Jotform batches (`Creator__c = 'Jotform'`)",
               r"\bCreator__c\s*=\s*'Jotform'|\bSubmitted_At__c\s*(?:!=|<>)\s*null\b")
    SUCCESS = ("processed batches (`Processing_Status__c = 'Success'`)", r"\bProcessing_Status__c\s*=\s*'Success'")
    # what each report's SOQL check must read, as (what, regex) over the statement's text
    SOQL = {
        "Clubs_Not_Submitting_Last_Week": (
            ("Accounts (`FROM Account`)", r"\bFROM\s+Account\b(?!_)"),
            ("of record type Club (`RecordType.DeveloperName = 'Club'`)", r"\bRecordType\.(?:DeveloperName|Name)\s*=\s*'Club'"),
            ("with a parent (`ParentId != null`)", r"\b(?:ParentId|Parent\.Id|Parent\.Name)\s*(?:!=|<>)\s*(?:null|'')"),
            ("without a batch dated last week, Sunday to Saturday - `Id NOT IN (SELECT Account__c FROM Attendance_Batch__c "
             "WHERE Attendance_Date__c = LAST_WEEK)`, the date inside the subquery (outside it, every club with a batch "
             "ever is counted as submitting)",
             r"\bNOT\s+IN\s*\(\s*SELECT\s+Account__c\s+FROM\s+Attendance_Batch__c\s+WHERE\b[^()]*"
             r"\bAttendance_Date__c\s*=\s*LAST_WEEK\b[^()]*\)"),
        ),
        "Submissions_by_Club_and_Week": (
            BATCHES,
            ("a record count (`COUNT(Id)`)", r"\bCOUNT\s*\("),
            ("grouped by partner, then club, and session week (`GROUP BY Account__r.Parent.Name, Account__r.Name, "
             "Session_Week__c`: rows partner then club)",
             r"\bGROUP\s+BY\b(?=.*\bParent\.Name\b.*\b(?:Account__r\.Name|Account_Name__c|Account__c)\b)(?=.*\bSession_Week__c\b)"),
        ),
        "Late_Submissions_Last_Month": (
            BATCHES, JOTFORM, SUCCESS,
            ("with a session date last month (`Attendance_Date__c = LAST_MONTH`)", r"\bAttendance_Date__c\s*=\s*LAST_MONTH\b"),
            ("the delay among the selected fields (`SELECT ... Submission_Delay_Days__c ... FROM`)",
             r"\bSELECT\b(?:(?!\bFROM\b).)*\bSubmission_Delay_Days__c\b"),
            ("the largest delay first (`ORDER BY Submission_Delay_Days__c DESC`)", r"\bORDER\s+BY\s+Submission_Delay_Days__c\s+DESC\b"),
        ),
        "Submission_Delay_by_Partner_by_Month": (
            BATCHES, JOTFORM, SUCCESS,
            ("the average delay (`AVG(Submission_Delay_Days__c)`)", r"\bAVG\s*\(\s*Submission_Delay_Days__c\s*\)"),
            ("the maximum delay (`MAX(Submission_Delay_Days__c)`)", r"\bMAX\s*\(\s*Submission_Delay_Days__c\s*\)"),
            ("grouped by partner and session month (`GROUP BY Account__r.Parent.Name, Session_Month__c`)",
             r"\bGROUP\s+BY\b(?=.*\bParent\.Name\b|.*\bPartner__c\b)(?=.*\bSession_Month__c\b)"),
        ),
    }
    # what no tied statement may carry: a predicate that is never true, an OR, a LIMIT or HAVING
    FORBIDDEN_ALL = (
        ("no predicate that is never true (`= null`, `= ''`): the statement would return nothing", r"(?<![!<>])=\s*(?:null\b|'')"),
        ("no `OR` (one window, one filter)", r"\bOR\b"),
        ("no `LIMIT`", r"\bLIMIT\b"),
        ("no `HAVING`", r"\bHAVING\b"),
    )
    NO_LITERAL_PERIOD = ("no literal month, week or date (`Session_Month__c = '2026-09'`, `Attendance_Date__c = 2026-09-01`): the "
                         "report's window is relative",
                         r"\bSession_(?:Month|Week)__c\s*(?:=|!=|<>|LIKE\b|IN\b|NOT\s+IN\b)|\bAttendance_Date__c\s*(?:=|>=?|<=?)\s*\d{4}-\d{2}")
    # the delay report alone may carry its floor, exactly `Attendance_Date__c >= 2026-09-01` (Ryan 2026-10-26 on #103:
    # session dates from 2026-09-01; #103's Rollout adds it to the check once deployed); any other literal date or
    # period, on it or on another report, is still refused
    FLOOR = r"\bAttendance_Date__c\s*>=\s*2026-09-01\b(?![T:])"
    NO_LITERAL_PERIOD_BUT_FLOOR = (
        "no literal month, week or date (`Session_Month__c = '2026-09'`, `Attendance_Date__c <= 2026-10-31`) but the floor "
        "`Attendance_Date__c >= 2026-09-01`: the report's window is relative",
        r"\bSession_(?:Month|Week)__c\s*(?:=|!=|<>|LIKE\b|IN\b|NOT\s+IN\b)|"
        r"\bAttendance_Date__c\s*(?!>=\s*2026-09-01\b(?![T:]))(?:=|>=?|<=?)\s*\d{4}-\d{2}")
    FORBIDDEN = {
        "Clubs_Not_Submitting_Last_Week": (
            ("no `Processing_Status__c` or `Creator__c` in the subquery (a batch of any status, by anyone, counts as submitted)",
             r"\(\s*SELECT\b[^()]*\b(?:Processing_Status__c|Creator__c)\b"),
        ),
        "Submissions_by_Club_and_Week": (
            ("no `Creator__c` or `Processing_Status__c` (every batch is a submission)", r"\b(?:Creator__c|Processing_Status__c)\b"),
            NO_LITERAL_PERIOD,
        ),
        "Late_Submissions_Last_Month": (NO_LITERAL_PERIOD,),
        "Submission_Delay_by_Partner_by_Month": (
            NO_LITERAL_PERIOD_BUT_FLOOR,
            ("the floor once (`Attendance_Date__c >= 2026-09-01` at most one time)", rf"(?:{FLOOR}).*(?:{FLOOR})"),
        ),
    }
    # the Parent.Name exclusion's names: inside `Parent.Name NOT IN (...)`, or each `Parent.Name != '...'`
    EXCLUSION = re.compile(r"\bParent\.Name\s+NOT\s+IN\s*\(([^)]*)\)|\bParent\.Name\s*(?:!=|<>)\s*('(?:[^'\\]|\\.)*')")
    # a report said to be in another folder: "in the Decommissioned folder", "under folder Private Reports" (case matters:
    # "in the report folder Attendance" is the Attendance folder)
    REPORT_REF = "|".join(REPORTS) + r"|\b(?:late|weekly|not-submitting|matrix) (?:list|report)s?\b|\bthe (?:four |new )?reports\b|\bmatrix\b"
    OTHER_FOLDER = (r"\b(?:in|inside|under|within)\s+(?:the\s+|its\s+|a\s+)?(?!Attendance\b)[A-Z][\w-]*(?: [A-Z][\w-]*)? folder\b|"
                    r"\b(?:in|inside|under|within)\s+(?:the\s+)?folder\s+[\"“']?(?!Attendance\b)[A-Z][\w-]*")
    # a Monday-start week affirmed anywhere in the section (a contrast carries "not" or "rather than")
    MON_SUN = r"\bMonday\b[^.;]{0,20}\bSunday\b|\bMonday[- ]start\w*|\bstarts? on (?:a )?Monday\b|\bfrom Monday\b"
    # every sentence about the late report, its delay, the list or its sort order
    ABOUT_LATE = r"\blate\b|\bdelay|\blist\b|\bsort\w*|Late_Submissions_Last_Month"
    # Ryan's answers, as the words that carry them (case-insensitive over prose() text)
    LIST = r"Clubs_Not_Submitting_Last_Week|\bweekly\b|\bnot[- ]submitting\b|\bdid not submit\b|\bnot submitted\b|\bno submission\b"
    OUT = (r"\bleft out\b|\bleaves? out\b|\bleaving out\b|\bexclud\w*|\bfilter\w* out\b|\bomit\w*|\bdrop\w*|\bremoved\b|"
           r"\btaken out\b|\bkept (?:off|out)\b|\bstays? (?:off|out)\b|\bnot (?:listed|shown|included|counted|in it|in the list|"
           r"on the list)\b|\bnever (?:show|appear|list)\w*|\bdo(?:es)? not (?:show|appear|list)\w*|\bout of\b")
    THREE = r"\bthree partners\b|\bmonthly\b|\b38 clubs\b|" + "|".join(partner(n) for n in MONTHLY_PARTNERS)
    US = r"\bU\.S\b|\bUS\b|\bUnited States\b"
    NAMES = (r"\b(?:partner|parent|account)s?'?s?\s+(?:account'?s?\s+)?names?\b|\bParent[.·]Name\b|"
             r"\bnames? of (?:the |their |its )?(?:partner|parent|account)")
    NEW_PARTNER = (r"\bnew partner\b|\banother partner\b|\bfourth partner\b|\bnext partner\b|\bpartner (?:that|who|which) "
                   r"(?:later|stops|leaves|moves|joins|starts|switches)\b|\bpartner of (?:that|this|the same) kind\b")
    EDIT = r"\bedit\w*|\bchang\w*|\bupdat\w*|\badd\w*|\bby hand\b|\bhand-kept\b|\bmaintain\w*|\bamend\w*|\badjust\w*|\bextend\w*"
    TARGET = r"\breports?\b|\bfilter\w*|Clubs_Not_Submitting_Last_Week|\blist\b"
    # in the edit's own clause: "changes nothing", "nothing to edit", "needs no change", "added automatically"
    EDIT_DENIED = (r"\bnothing\b|\bneeds? no\b|\bnot need\w*|\bno (?:report |filter |hand )?(?:edit|change|update|work)\w*|"
                   r"\bwithout (?:a |any )?(?:report |filter )?(?:edit|change)\w*|\bunchanged\b|\bautomatically\b")
    UNAFFECTED = (r"\bunaffected(?: by (?:the |that |this |its |any )?(?:partner[- ]name |partner |name )?(?:filter|it))?\b|"
                  r"\bnot affected(?: by (?:the |that |this |its |any )?(?:partner[- ]name |partner |name )?(?:filter|it))?\b|"
                  r"\bno (?:such |partner[- ]name |partner |name |this )?filter\b|"
                  r"\bwithout (?:the|that|this|a|any|such a) (?:partner[- ]name |partner |name )?filter\b|\bnot filtered\b|"
                  r"\buntouched\b|\bunchanged\b|\bno (?:such )?padding\b|\bonly (?:the )?clubs (?:with|that)\b|"
                  r"\bclubs with a batch\b|\bnothing (?:is )?left out\b|\bleaves? (?:nothing|no club|no one) out\b|"
                  r"\bevery club\b|\ball clubs\b|\bas (?:it|they) (?:is|are|stands?)\b")
    # said of the matrix once UNAFFECTED is taken out: it has / shares / also carries the filter, clubs are missing
    MATRIX_FILTERED = (r"\b(?:carr\w+|has|have|had|with|share\w*|same|also|too)\b[^,;]{0,30}\bfilter|"
                       r"\bfilter\w*[^,;]{0,30}\b(?:too|as well|also)\b|\bmissing\b|\bexclud\w*|\bleft out of it\b|"
                       r"\bleaves? out\b|\bdropped\b|\bomit\w*|\bremoved\b")
    STATUS = r"\bany status\b|\bwhatever (?:its|the|their) status\b|\bevery status\b|\bregardless of (?:its |the |their )?status\b|\bof any kind\b"
    NO_BATCH = (r"\b(?:no|without(?: a| an| any)?|not (?:a single|one|any)|zero|never a|lacks?(?: a| any)?|has no|had no|sent no)\s+"
                r"`?(?:\w+\s+){0,2}`?(?:batch|Attendance_Batch__c|submission)")
    DATED = r"\bAttendance_Date__c\b|\bsession date\b|\bdated\b|\bsession'?s? day\b|\bdate of the session\b|\bsession (?:falls|is|was|held)\b"
    LAST_WEEK = r"\blast week\b|\bLAST_WEEK\b|\bthe week\b|\bthat week\b"
    SUN_SAT = r"\bSunday\b[^.;]{0,20}\bSaturday\b"
    # the negation governs the field's being needed or added, in the same clause
    NO_FIELD = (r"\b(?:no|without(?: a| any)?|needs? no|never need\w*(?: a| any)?|not need\w*(?: a| any)?|not require\w*(?: a| any)?)\s+"
                r"(?:new |extra |additional |further |another |second )?(?:formula |checkbox |date )?fields?\b|"
                r"\bfields?\b[^.;,]{0,40}\b(?:is|was|were|are)\s+(?:not|never)\s+(?:needed|required|necessary|added|deployed|created|built)\b|"
                r"In_Last_Week__c[^.;,]{0,60}\b(?:not|never|un)\s*(?:needed|required|necessary|added|deployed|created|built)\b|"
                r"\b(?:no|not|never|without)\b[^.;,]{0,30}\bIn_Last_Week__c\b")
    LATE = r"Late_Submissions_Last_Month|\blate (?:report|list|submissions?)\b"
    NO_CUTOFF = (r"\b(?:no|without(?: a| any)?|not)\s+(?:a\s+)?(?:cut-?off|threshold|minimum|floor|filter on the delay)\b|"
                 r"\bevery (?:live )?(?:Jotform )?batch\b|\ball (?:live )?(?:Jotform )?batches\b|\bwhatever (?:its|the) delay\b|"
                 r"\bany delay\b|\bno matter (?:how|the)\b")
    # a number of days stated as the late report's cut-off ("3 or more days late", "over 7 days", "only batches ...")
    DAY_THRESHOLD = (r"\b\d+\s*(?:or more |or fewer |\+ ?)?days?\s+(?:late|or more|and more|or longer|behind|of delay|late[rn])\b|"
                     r"\b(?:above|over|more than|at least|beyond|exceed\w*|greater than|longer than|later than|under|below|less than)"
                     r"\s+\d+\s*days?\b|\bthreshold of\b|\bcut-?off (?:of|at)\b|\bonly (?:the )?(?:batches|those|rows|submissions)\b")
    LARGEST = (r"\b(?:largest|biggest|longest|highest|greatest|most delayed|latest|slowest)\s+(?:delays? )?first\b|\bdescending\b|"
               r"\bORDER BY Submission_Delay_Days__c DESC\b|\bfrom the (?:largest|longest|biggest|highest)\b|"
               r"\b(?:longest|largest|biggest) (?:delays? )?(?:at the top|on top)\b")
    SMALLEST = r"\b(?:smallest|shortest|lowest|least|earliest|quickest)\s+(?:delays? )?first\b|\bascending\b|\bASC\b|\bnot descending\b"
    THRESHOLD = r"\bSubmission_Delay_Days__c\s*(?:>=?|<=?)\s*-?\d"

    def section(self):
        """The section's raw Markdown; a missing heading fails here (md_part)."""
        return md_part(self.RUNBOOK, self.HEADING)

    @classmethod
    def missing(cls, report, statement):
        """What the statement lacks to be `report`'s check: the features it has not, what it must not carry
        (FORBIDDEN_ALL, the report's FORBIDDEN), and a field with two `=` predicates in its WHERE."""
        lacks = [what for what, pattern in cls.SOQL[report] if not re.search(pattern, statement)]
        lacks += [what for what, pattern in cls.FORBIDDEN_ALL + cls.FORBIDDEN.get(report, ()) if re.search(pattern, statement)]
        twice = duplicate_equals(statement)
        if twice:
            lacks.append(f"one `=` predicate per field in its WHERE (twice: {', '.join(twice)})")
        return lacks

    @classmethod
    def excluded_set(cls, statement):
        """The account names the statement's `Parent.Name` exclusion(s) carry: inside `NOT IN (...)`, or each
        `!= '...'`; SOQL's `\\'` unescaped."""
        inside = " ".join(a or b for a, b in cls.EXCLUSION.findall(statement))
        return {n.replace("\\'", "'") for n in re.findall(r"'((?:[^'\\]|\\.)*)'", inside)}

    @staticmethod
    def saying(said, *patterns):
        """The sentences that match every pattern (case-insensitive)."""
        return [s for s in said if all(re.search(f"(?i){p}", s) for p in patterns)]

    @staticmethod
    def clause_and_next(sentence, at):
        """The clause of `sentence` around offset `at` and the one after it: where what is said of a subject
        ("a new partner of that kind ...") must stand."""
        start, end = clause_span(sentence, at)
        nxt = CLAUSE_END.search(sentence, min(end + 1, len(sentence)))
        return sentence[start:nxt.start() if nxt else len(sentence)]

    def test_the_runbook_lists_the_timing_reports_and_their_soql(self):
        part = self.section()
        raw = flat(part)
        where = f"RUNBOOK section {self.HEADING[3:]!r}"
        # the four reports by DeveloperName, in the Attendance folder (affirmed: "not the Attendance folder" is not it)
        for report in REPORTS:
            with self.subTest(report=report):
                self.assertIn(report, raw, f"{where}: name the report `{report}` (its DeveloperName)")
        said = sentences(prose(raw), ".;")
        self.assertTrue([s for s in said if re.search(r"\breports?\b|" + "|".join(REPORTS), s) and affirms(s, self.FOLDER)],
                        f"{where}: say the reports are in the Attendance folder, in a sentence about the reports with no "
                        "negation right before it")
        elsewhere = [s for s in said if re.search(f"(?i){self.REPORT_REF}", s) and affirms(s, self.OTHER_FOLDER, flags=0)]
        self.assertFalse(elsewhere, f"{where}: a sentence puts a report in another folder than Attendance: "
                                    f"{elsewhere[0] if elsewhere else ''!r}")
        # a SOQL check beside each name: the statement in the report's own bullet, paragraph or table row
        checks = soql_checks(part)
        self.assertTrue(any(checks.values()),
                        f"{where}: a SOQL check (`SELECT ... FROM ...`, in a code span) beside each of the four report "
                        "names, in the same bullet, paragraph or table row as the name")
        passing = {}
        for report in self.SOQL:
            with self.subTest(report=report):
                found = checks[report]
                self.assertTrue(found, f"{where}: `{report}` has no SOQL check beside its name: a `SELECT ... FROM ...` in a "
                                       "code span, in the same bullet, paragraph or table row as the name and after it")
                missing = min((self.missing(report, stmt) for stmt in found), key=len)
                self.assertFalse(missing, f"{where}: the SOQL check beside `{report}` is not that report's check; it lacks: "
                                          + "; ".join(missing))
                passing[report] = next(stmt for stmt in found if not self.missing(report, stmt))
        self.assertEqual(len(set(passing.values())), len(passing),
                         f"{where}: one SOQL check per report - the same statement stands beside two reports")

    def test_the_runbook_says_who_is_left_out_of_the_weekly_lists(self):
        part = self.section()
        raw = flat(part)
        text = prose(raw).replace("U.S.", "U.S")
        said = [re.sub(LABEL, "", s) for s in sentences(text, ".;")]
        where = f"RUNBOOK section {self.HEADING[3:]!r}"
        us_accounts = us_partner_accounts()
        self.assertTrue(us_accounts, "appsscript/Regions.gs + glow/sf_partners.csv: no U.S partner with a Salesforce "
                                     "account (the test's own data; the clubs-off plan counted 6)")
        # who: the three partners by their account names, and the U.S clubs
        for name in MONTHLY_PARTNERS:
            with self.subTest(partner=name):
                self.assertRegex(raw, partner(name), f"{where}: name the monthly-reporting partner {name} (as its Salesforce "
                                                     "account is spelled: the filter is on the names)")
        self.assertRegex(text, self.US, f"{where}: name the U.S clubs (their form is disabled)")
        # left out of the weekly not-submitting list, said of the three partners' clubs and of the U.S clubs, and
        # not denied right before ("does not leave out", "never left out", "rather than excluded")
        self.assertTrue([s for s in self.saying(said, self.LIST, self.THREE) if affirms(s, self.OUT)],
                        f"{where}: say the three monthly-reporting partners' clubs are left out of the weekly not-submitting "
                        "list (`Clubs_Not_Submitting_Last_Week`), in one sentence that names the list and the partners, "
                        "with no negation right before the leaving out")
        self.assertTrue([s for s in self.saying(said, self.US) if affirms(s, self.OUT)],
                        f"{where}: say the U.S clubs are left out too, in a sentence")
        # how: a filter on their partner account names - the names of the ones left out (the three partners or the
        # U.S clubs named in the sentence), not of the clubs that do report
        self.assertTrue([s for s in self.saying(said, self.NAMES, f"{self.THREE}|{self.US}") if affirms(s, r"\bfilter\w*")],
                        f"{where}: say they are left out by a filter on their partner account names (`Parent.Name`), in a "
                        "sentence that names the three partners (or `monthly`) or the U.S clubs")
        # hand-kept: a new partner of that kind needs a report edit - the edit affirmed in the new partner's own
        # clause or the one after it ("hand-kept" said of the filter elsewhere in the sentence is not it)
        self.assertTrue([s for s in self.saying(said, self.TARGET)
                         if any(affirms(self.clause_and_next(s, m.start()), self.EDIT, self.EDIT_DENIED)
                                for m in re.finditer(f"(?i){self.NEW_PARTNER}", s))],
                        f"{where}: say a new partner of that kind (monthly through Salesforce, or off Jotform) needs the "
                        "report's filter edited by hand, in a sentence, the edit said of the new partner (\"changes "
                        "nothing\", \"nothing to edit\", \"no edit\" say the opposite)")
        # Submissions_by_Club_and_Week is unaffected, and no sentence about it (by name or as "the matrix") gives it
        # the filter or loses clubs from it
        matrix = self.saying(said, r"Submissions_by_Club_and_Week|\bmatrix\b")
        self.assertTrue([s for s in matrix if re.search(f"(?i){self.UNAFFECTED}", s)],
                        f"{where}: say `Submissions_by_Club_and_Week` is unaffected (it shows only clubs with a batch), in the "
                        "sentence that names it")
        filtered = [s for s in matrix if re.search(f"(?i){self.MATRIX_FILTERED}", re.sub(f"(?i){self.UNAFFECTED}", " ", s))]
        self.assertFalse(filtered, f"{where}: a sentence about `Submissions_by_Club_and_Week` (the matrix) gives it the filter or "
                                   f"says clubs are missing from it: {filtered[0] if filtered else ''!r}")
        # the SOQL check of the weekly list leaves them out the same way: a Parent.Name exclusion whose names are
        # exactly the three partners and the U.S clubs' partner accounts (Regions.gs region U.S, as sf_partners.csv
        # spells them) - a live Jotform partner in it would hide real non-submitters
        checks = soql_checks(part)
        expected = set(MONTHLY_PARTNERS) | set(us_accounts)
        tied = checks["Clubs_Not_Submitting_Last_Week"]
        self.assertTrue(tied, f"{where}: no SOQL check beside `Clubs_Not_Submitting_Last_Week` (the first test says where)")
        names = min((self.excluded_set(stmt) for stmt in tied), key=lambda got: len(got ^ expected))
        self.assertEqual(names, expected,
                         f"{where}: the SOQL check beside `Clubs_Not_Submitting_Last_Week` leaves out exactly the partners the "
                         "report does - `Parent.Name NOT IN (...)` with the three monthly partners and the U.S clubs' partner "
                         "accounts, nobody else (SOQL escapes the apostrophe: Ng\\'aa Maskani); "
                         f"missing: {sorted(expected - names)}, extra: {sorted(names - expected)}")
        # what "not submitting last week" means: NO batch of any status whose session date (Attendance_Date__c) is
        # in last week; the week Sunday to Saturday (LAST_WEEK), affirmed and with no Monday in the sentence (a
        # contrast goes in a sentence of its own); no new field for it, the negation on the field itself
        self.assertTrue(self.saying(said, self.NO_BATCH, self.STATUS, self.DATED, self.LAST_WEEK),
                        f"{where}: define \"not submitting last week\": NO batch (none, `without a batch`) of any status whose "
                        "session date (`Attendance_Date__c`) is in last week, in one sentence")
        self.assertTrue([s for s in self.saying(said, r"\bweek\b|LAST_WEEK") if affirms(s, self.SUN_SAT)
                         and not re.search(r"(?i)\bMonday\b", s)],
                        f"{where}: say the week runs Sunday to Saturday (Salesforce's `LAST_WEEK`), in a sentence with no "
                        "negation right before it and no Monday in it")
        monday = [s for s in said if affirms(s, self.MON_SUN)]
        self.assertFalse(monday, f"{where}: a sentence affirms a Monday-start week (a contrast carries `not` or `rather than`): "
                                 f"{monday[0] if monday else ''!r}")
        self.assertIn("LAST_WEEK", raw, f"{where}: name the date literal `LAST_WEEK` the report and its check use")
        self.assertTrue(self.saying(said, self.NO_FIELD, r"\bweek\b|LAST_WEEK|Sunday|Saturday|In_Last_Week__c"),
                        f"{where}: say no new field (no `In_Last_Week__c` formula) was needed for last week, in a sentence, the "
                        "negation on the field being needed or added")
        # the late report: no cut-off, and no sentence about late batches, a delay, the list or its order states a
        # number of days as one; the largest delay first, and no such sentence says smallest first or ascending
        self.assertTrue([s for s in self.saying(said, self.LATE) if affirms(s, self.NO_CUTOFF)],
                        f"{where}: say `Late_Submissions_Last_Month` has no cut-off or threshold - every live Jotform batch of "
                        "last month with its delay - in a sentence")
        about = self.saying(said, self.ABOUT_LATE)
        cut = [s for s in about if re.search(f"(?i){self.DAY_THRESHOLD}", s)]
        self.assertFalse(cut, f"{where}: a sentence about late batches or the delay states a cut-off in days (Ryan 2026-10-24: "
                              f"none): {cut[0] if cut else ''!r}")
        self.assertTrue([s for s in self.saying(said, self.LATE + r"|\bdelay") if affirms(s, self.LARGEST)],
                        f"{where}: say the late report lists the largest delay first (descending), in a sentence")
        asc = [s for s in about if re.search(f"(?i){self.SMALLEST}", s)]
        self.assertFalse(asc, f"{where}: a sentence about late batches, the delay or the list says smallest first or ascending: "
                              f"{asc[0] if asc else ''!r}")
        for stmt in checks["Late_Submissions_Last_Month"]:
            self.assertNotRegex(stmt, self.THRESHOLD,
                                f"{where}: the late report has no threshold (Ryan 2026-10-24), but its SOQL check compares "
                                f"`Submission_Delay_Days__c` with a number: {stmt[:120]!r}")


# Ticket #103: the three reports the new dashboard components read (`Submissions_by_Club_and_Week` stays
# off the dashboard), the folder of the build (`data/sf_session_timing_2026-11-19/`: `dashboard_before/`
# is the fresh retrieve, `after/` the read-back; never committed, so only what the docs say of it is
# tested) and the dashboard's DeveloperName. The dashboard changed on 2026-11-18 (#222, #231), so the
# build was redone from a fresh retrieve of 2026-11-19; the 2026-10-26 retrieve is superseded (DECISIONS
# 2026-10-16: never an older build) and counts as another change's folder (OTHER_CHANGE).
DASH_REPORTS = ("Clubs_Not_Submitting_Last_Week", "Late_Submissions_Last_Month", "Submission_Delay_by_Partner_by_Month")
DASH_FOLDER = "sf_session_timing_2026-11-19"
# a folder said to be superseded, older or never used (the docs may name the 2026-10-26 retrieve so)
SUPERSEDED = (r"(?i)\bsupersed\w*|\bpredat\w*|\bnever used\b|\bnot used\b|\bunused\b|\bolder\b|\bearlier\b|\bstale\b|"
              r"\bobsolete\b|\bdiscarded\b|\breplaced\b|\bout of date\b")


def names_job_folder(text):
    """The sentences of `text` (flattened, prose()) that name `data/{DASH_FOLDER}/` as #103's own folder: the
    name not negated in its clause, and the sentence not calling it superseded, older or never used."""
    pattern = re.compile(re.escape(DASH_FOLDER) + r"(?![\w-])")
    return [s for s in sentences(text, ".;") if affirmed(s, pattern) and not re.search(SUPERSEDED, s)]
DASHBOARD = "Jotform_Attendance_test"
# `--dry-run` said of a check-only or validation, or inside the deploy command itself
CHECK_ONLY = re.compile(r"(?i)(?:check-only|\bvalidat\w*)[^.]{0,120}?--dry-run|--dry-run[^.]{0,120}?(?:check-only|\bvalidat\w*)|"
                        r"sf project deploy start[^.(]{0,80}?--dry-run")
RYANS_GO = near(r"\bRyan'?s?\b", r"\bgo\b", 40)
# what the not-submitting list is called ("Clubs not submitting last week", "no batch dated last week") names it;
# it denies nothing
NOT_SUBMITTING = re.compile(r"(?i)\b(?:not|never|no)\s+(?=(?:\w+\s+){0,2}?(?:submit\w*|submission\w*|batch\w*)\b)")


def names_unnegated(text):
    """`text` with the not-submitting list's name taken out of the negation scan: "not submitting" reads
    "non-submitting", "no batch" "non-batch"."""
    return NOT_SUBMITTING.sub("non-", text)


def top_items(part):
    """The top-level list items of a Markdown part, each flattened with everything it holds: its indented
    lines, nested lists, lazy continuations and the indented paragraphs after a blank line inside it. A
    heading, an unindented paragraph after a blank line or the next top-level marker ends it."""
    items, current, blank = [], None, False
    for line in part.splitlines():
        if LIST_ITEM.match(line):
            current = [line[LIST_ITEM.match(line).end():]]
            items.append(current)
        elif line.startswith("#"):
            current = None
        elif not line.strip():
            blank = True
            continue
        elif current is not None and (line[:1].isspace() or not blank):
            current.append(line)
        else:
            current = None
        blank = False
    return [flat(" ".join(item)) for item in items]


def md_sub(text, heading):
    """The part of Markdown `text` under the first heading line that starts with `heading`, that line
    included, to the next heading of its level or higher; None when there is no such heading."""
    m = re.search(r"^" + re.escape(heading) + r"(?!\w).*$", text, re.M)
    if not m:
        return None
    level = len(heading) - len(heading.lstrip("#"))
    rest = text[m.start():]
    nxt = re.search(r"\n#{1,%d} " % level, rest)
    return rest[:nxt.start()] if nxt else rest


def typed_blocks(part):
    """blocks(part), each as (kind, text): "item" (a top-level list item with everything it holds), "row" (a
    table row) or "para" (a paragraph)."""
    out, current, kind = [], [], "para"

    def close():
        if current:
            out.append((kind, flat(" ".join(current))))
            del current[:]

    for line in part.splitlines():
        if not line.strip() or line.startswith("#"):
            close()
        elif line.lstrip().startswith("|"):
            close()
            out.append(("row", flat(line)))
        elif LIST_ITEM.match(line):
            close()
            kind = "item"
            current.append(line[LIST_ITEM.match(line).end():])
        else:
            if not current:
                kind = "para"
            current.append(line)
    close()
    return out


class Span:
    """A [start, end) with a match's start() and end(), for negated() on a span that no one regex matched."""

    def __init__(self, start, end):
        self._start, self._end = start, end

    def start(self):
        return self._start

    def end(self):
        return self._end


class DashboardTimingDocs(unittest.TestCase):
    """Ticket #103: four components on the "Jotform Attendance" dashboard (`Attendance/Jotform_Attendance_test`,
    or a sibling dashboard "Attendance Submissions" if the check-only refuses the component count), deployed
    on Ryan's go; the repo keeps docs/RUNBOOK.md "Attendance dashboard in Salesforce" (that section alone, to
    the next `## `) and the plan's "## Task #103" section.

    The section names each new component beside the report it reads: a metric of the clubs not submitting
    last week and a table of them by partner (`Clubs_Not_Submitting_Last_Week`), a metric of last month's
    submissions (`Late_Submissions_Last_Month`) and a bar chart of the average days from session to
    submission by partner (`Submission_Delay_by_Partner_by_Month`). A component's kind (metric or tile,
    table, chart or bar) is paired with the report named right after it, else right before it, with no
    other kind or report between; a pairing the dashboard does not have ("the bar chart reads
    `Clubs_Not_Submitting_Last_Week`", any component on `Submissions_by_Club_and_Week`) fails unless negated.
    Each follows the dashboard's Partner filter. The bullet or paragraph that names the "How to read this
    dashboard" box (with the list items right after it when it introduces them) carries the box's timing:
    last week is Sunday to Saturday (`LAST_WEEK`), "submitted at" is the batch's `CreatedDate`
    (`Submitted_At__c`), the September back-fill and the three partners' monthly batches have none (no
    submission time, no delay: "never a blank delay" says they have one), and there is no late threshold.
    Nowhere in the section: a Monday-start week (Monday to Sunday, begins on Monday, an ISO week),
    "submitted at" tied to `LastModifiedDate` or another modification stamp, those batches said to have or
    show a submission time, a threshold (Ryan 2026-10-22, DECISIONS 2026-10-23: "tasks #102 and #103 drop
    any threshold"; Ruling of 2026-10-26: the outline's "Late submissions last month (over N days)" becomes
    a threshold-free metric headed so that nobody reads it as a count of late ones) as a number of days or
    weeks, in digits or words ("over seven days", "more than a week"), a metric that counts the late ones,
    or a header "Late ..." (quoted, in backticks, bold, or after "titled", "headed", "called").

    Its Rollback for #103 redeploys only the dashboard, from `data/sf_session_timing_2026-11-19/dashboard_before/`
    (the job folder, named as #103's own and not as superseded), check-only first and on Ryan's go, and only
    after a fresh retrieve equals #103's own read-back
    (`data/sf_session_timing_2026-11-19/after/`, or `after/` in a sentence that names no other change) - a
    difference stops it (no "anyway", "proceed", "ignore the difference"), and the rollback is built from
    the fresh retrieve; never an older package (DECISIONS 2026-10-16), so another change's folder
    (`sf_girls_tiles_2026-10-20`, the superseded retrieve `sf_session_timing_2026-10-26`, #59, #35) appears only where it is denied or named as the older package
    never used; no deploy sentence also redeploys a report, a field, a permission set or a folder other
    than `dashboard_before/`; #102's reports stay (the archive rule: nothing deleted), and a sibling
    dashboard, when there is one, is retired with it. The plan's "## Task #103" carries Build (what `build/`
    holds - the dashboard, the three reports, the box - and that it is made from `dashboard_before/`),
    Rollout, Rollback, Risks (one of #103's own: the component limit, the sibling, the Partner filter, the
    week, a change since the retrieve, the live leadership dashboard ...) and Result (what was built or
    deployed); its Rollout's items run, in order, the fresh retrieve of `Jotform_Attendance_test` compared
    with `dashboard_before/` (a difference: rebuild, stop or say so), the check-only (`build/`, and
    `build_sibling/` on a component-count refusal), Ryan's go, the deploy, the read-back into `after/`
    compared with `build/`, the refresh (the PUT, `analytics/dashboards`), and each component against its
    report and its SOQL under All and under one partner. Meaning, not sentences: tolerant matching on names
    and key words; a negated statement does not count."""

    RUNBOOK = SubmissionTimingDocs.RUNBOOK
    HEADING = "## Attendance dashboard in Salesforce"
    # the components' kinds, which of #102's reports each kind of new component reads (a metric the weekly list or
    # the late report, the table the weekly list, the bar chart the delay report; `Submissions_by_Club_and_Week` is
    # on none), and each component as (what, report, kind, [(what it must say, regex), ...]): the extras are words
    # beyond the report's name (`\b` does not match inside `Clubs_Not_Submitting_Last_Week`)
    KINDS = (("metric", r"\bmetrics?\b|\btiles?\b"), ("table", r"\b(?:flex ?)?tables?\b|FlexTable"),
             ("chart", r"\bbar charts?\b|\bbars?\b|\bcharts?\b|HorizontalBar\w*"))
    READS_REPORT = {"metric": ("Clubs_Not_Submitting_Last_Week", "Late_Submissions_Last_Month"),
                    "table": ("Clubs_Not_Submitting_Last_Week",), "chart": ("Submission_Delay_by_Partner_by_Month",)}
    COMPONENTS = (
        ("the metric \"Clubs not submitting last week\"", "Clubs_Not_Submitting_Last_Week", "metric",
         (("that it counts the clubs not submitting", r"\bnot submitting\b|\bdid not submit\b|\bno submission\b|\bnot submitted\b|"
                                                      r"\bwithout a (?:batch|submission)\b"),
          ("last week", r"\blast week\b|\bLAST_WEEK\b"))),
        ("the table of those clubs by partner", "Clubs_Not_Submitting_Last_Week", "table",
         (("by partner", r"\bpartners?\b"),)),
        ("the metric of last month's submissions", "Late_Submissions_Last_Month", "metric",
         (("the submissions it counts", r"\bsubmissions?\b|\bbatch(?:es)?\b"), ("last month", r"\blast month\b|\bLAST_MONTH\b"))),
        ("the bar chart of the average days from session to submission, by partner", "Submission_Delay_by_Partner_by_Month",
         "chart", (("the average", r"\baverage\b|\bAVG\b|\bmean\b"), ("by partner", r"\bpartners?\b"),
                   ("the delay in days", r"\bdays?\b|\bdelay\b"))),
    )
    # the late metric counts every submission of last month, whatever its delay (affirmed), or says no threshold
    ALL_SUBMISSIONS = (r"\b(?:every|all|each)\b[^.;]{0,40}\b(?:submissions?|batch(?:es)?|forms?)\b|\bwhatever (?:its|the|their) delay\b|"
                       r"\bany delay\b|(?<![Ll]ate )\bsubmissions (?:of|in|from|dated) last month\b")
    NO_THRESHOLD = (r"(?i)\b(?:no|without(?: a| any)?|never a)\s+(?:(?:late|delay|big[- ]delay|[\"“']big delay[\"”'])\s+)?"
                    r"(?:threshold|cut-?off|flag)s?\b|\bnothing is flagged\b|\b(?:never|not) flagged\b|\bthreshold\b\W{0,4}none\b")
    # the Partner filter followed, said in a block about the timing components
    PARTNER_FILTER = r"\bPartner\b[*`\"”'’]*\s+filters?\b|\bfilters?\s+(?:on|by|for)\s+(?:the\s+)?partners?\b"
    FOLLOWS = (r"\bfollow\w*|\bcover\w*|\bappl(?:y|ies|ied)\b|\bfiltered\b|\bnarrow\w*|\bobey\w*|\brespect\w*|\bhonou?r\w*|"
               r"\bwired\b|\bconnected\b|\blinked\b|\brespond\w*|\bdriven\b|\bsame\b|\bshare\w*|\bcarr\w*")
    TIMING = "|".join(DASH_REPORTS) + r"|\btiming\b|(?<![\w#])#103\b|Attendance_Submissions|\bAttendance Submissions\b"
    EACH = r"(?i)\b(?:each|every|all|four|three|both|they|these|them)\b"
    # the new components named as such in the sentence itself ("each new component", "all four")
    NEW_ONES = (r"(?i)\b(?:four|new|timing|#103's?)\b[^.;]{0,30}\bcomponents?\b|\b(?:each|all|every one) of the (?:four|new)\b|"
                r"\ball four\b|\bthe four\b")
    # the How-to box, documented with the timing
    BOX = r"(?i)How to read this dashboard|\bhow-to\b|\bbox\b"
    BOX_TIMING = (r"(?i)\bweek\b|\bLAST_WEEK\b|\bsubmitted at\b|Submitted_At__c|\bsubmission time\b|\bthreshold\b|\bdelay\b|"
                  r"\btiming\b|(?<![\w#])#103\b|\bsubmi\w*|Attendance_Submissions|\bAttendance Submissions\b")
    # "submitted at": the batch's CreatedDate (when the Jotform integration created it), never a modification stamp
    SUBMITTED = (r"\bsubmitted at\b|Submitted_At__c|\bsubmission time\b|\btime (?:of|it was|the form was) submi\w*|"
                 r"\bwhen (?:the|a|its) form was submitted\b")
    CREATED = r"CreatedDate"
    WRONG_STAMP = (r"LastModifiedDate|SystemModstamp|LastReferencedDate|LastViewedDate|\blast[- ]modified\b|"
                   r"\blast (?:edit|chang|updat|modif)\w*|\bmodifi\w* (?:date|time|stamp)\b")
    # the batches with no submission time: the September back-fill and the three partners' monthly batches; "no
    # submission time", "no delay", "the delay is blank", "have none" - and never "a blank delay" (a delay)
    BACKFILL = r"(?i)back-?fill"
    MONTHLY = r"(?i)Partner report|\bmonthly\b|\bthree partners\b"
    NOT_A_TIME = r"(?!(?:no|not|none|never|blank|empty|null|missing|without)\b)"
    TIME = r"(?:submission (?:times?|dates?)|submitted at|Submitted_At__c|delays?)"
    HAS_NONE = (rf"(?i)\b(?:no|without(?: a| any)?|never (?:a|any)|lacks?(?: a| any)?|not (?:a|any)|none of (?:a|the))\s+"
                rf"(?:{NOT_A_TIME}[`\"“]?[\w'’]+[`\"”]?\s+){{0,2}}?[`\"“]?{TIME}\b|"
                rf"{TIME}\W{{0,3}}[^.;]{{0,40}}?\b(?:is|are|stays?|left|shows?|reads?)\s+(?:blank|empty|null|none)\b|\b(?:has|have)\s+none\b")
    HAS_TIME = (rf"\b(?:have|has|show\w*|carr\w*|gets?|got|keeps?|holds?|gives?|with)\s+(?:(?:a|an|the|their|its|one)\s+)?"
                rf"(?:{NOT_A_TIME}[\w`'’]+\s+)?[`\"“]?{TIME}\b")
    # a clause about the batches that do have a time ("only a live Jotform batch has a submission time")
    OTHER_BATCHES = (r"(?i)\bonly\b|\bevery\b|\beach\b|\ball\b|\bunlike\b|\bwhile\b|\bwhereas\b|\blive\b|"
                     r"\bJotform (?:batch(?:es)?|submissions?|forms?)\b")
    # a Monday-start week: Monday to Sunday, begins on Monday, an ISO week (a contrast carries "not" in its clause)
    MONDAY_WEEK = (r"\b(?:start|begin|open|commenc)\w*\b[^.;,]{0,40}?\bMon(?:day)?\b|\bMon(?:day)?\b[^.;]{0,60}?\bSun(?:day)?\b|"
                   r"\bMonday[- ]start\w*|\bfrom Monday\b|\bISO[- ]?weeks?\b|\bweeks? of Monday\b|"
                   r"\bMonday (?:is|as) (?:the )?first\b|\bfirst day\b[^.;,]{0,30}\bMonday\b")
    CONTRAST = r"\bnot\b|\bnever\b|\bnor\b|\brather than\b|\binstead of\b|\bunlike\b|\bisn't\b|\bwrong\w*"
    # sentences that may state a threshold, and the threshold they must not state, in digits or words ("over N days",
    # "over seven days", "more than a week", "7+ days")
    ABOUT_DELAY = r"(?i)\blate\b|\bdelay|\bthreshold|\bcut-?off|Late_Submissions_Last_Month|\bsubmi\w*|\bmetric|\btile"
    NUM = (r"(?:\d+|N|X|an?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|twenty|"
           r"thirty|a few|several)")
    UNIT = r"(?:days?|weeks?|fortnights?)"
    DAY_THRESHOLD = (rf"\b{NUM}\s*(?:or more|or fewer|or longer|and (?:up|over|more|above)|\+|plus)\s*{UNIT}\b|"
                     rf"\b{NUM}[\s-]*{UNIT}\s+(?:late|or more|and more|or longer|or later|behind|of delay|late[rn]|overdue|plus)\b|"
                     r"\b(?:above|over|more than|at least|beyond|exceed\w*|greater than|longer than|later than|under|below|less than|"
                     rf"past)\s+{NUM}\s*{UNIT}\b|"
                     r"\bthreshold of\b|\bcut-?off (?:of|at)\b|\b(?:threshold|cut-?off)\s*(?:of|is|=|:)?\s*\d+\b")
    # a header "Late ...": after a naming word, quoted, in backticks or bold near a component's kind, a table cell, or
    # any quoted "Late submissions" (the report's own label, "the report "Late Submissions - Last Month"", is no header)
    QUOTE = r"[\"“”'‘’`*_]"
    LATE_HEADER = (rf"\b(?:called|named|titled|headed|labell?ed|header|heading|title|label)\b\s*(?:is\s+|reads\s+|:\s*)?{QUOTE}*\s*Late\b|"
                   rf"\b(?:metric|tile|component|chart|table)s?\b[^.;]{{0,30}}?{QUOTE}+\s*Late\b|"
                   rf"\|\s*(?:\w+\s+){{0,2}}{QUOTE}+\s*Late\b|{QUOTE}+\s*Late\s+submissions?\b")
    REPORT_LABEL = r"(?i)\breports?\b\W{0,4}(?:(?:label|title|name)\w*\W{0,4})?(?:is\s+)?" + QUOTE + r"*\s*$"
    NOT_SAID = r"\bnot\b|\bnever\b|\bnobody\b|\bno one\b|\brather than\b|\binstead of\b"
    # the late metric said to count the late ones only
    COUNTS_LATE = (r"\bcount\w*\b[^.;,]{0,40}?\b(?:the |only (?:the )?)?late (?:ones|submissions?|batch(?:es)?|forms?)\b|"
                   r"\bcount\w*\b[^.;,]{0,40}?\b(?:submitted|sent|filed|arriv\w*|came in)\s+(?:over|more than|after|later than|"
                   r"beyond|at least|late)\b|\bonly (?:the )?late (?:ones|submissions?|batch(?:es)?)\b")
    # the rollback
    FRESH = r"\bretriev\w*|\bfresh\b"
    COMPARE = r"\bcompar\w*|\bequal\w*|\bidentical\b|\bmatch\w*|\bsame as\b|\bdiff\b"
    # the read-back the fresh retrieve is compared with: #103's own `after/` (beside `dashboard_before/`)
    READ_BACK = rf"{DASH_FOLDER}/after/|`after/"
    # another change's folder or ticket: #59's and #35's read-backs predate the timing components
    OTHER_CHANGE = rf"\bsf_(?!{DASH_FOLDER[3:]}\b)\w*?\d{{4}}-\d\d-\d\d\b|(?<![\w#])#(?:35|59)\b"
    DIFFER = r"(?i)\bdiffer\w*|\bdifferences?\b|\bnot equal\b|\bunequal\b|\bmismatch\w*|\bchanged\b|\bnot the same\b"
    # stop (not "stop worrying"), or build from the fresh retrieve
    STOP = (r"\bstop(?:s|ped)?\b(?!\s+(?!deploying\b|rolling\b)\w+ing\b)|\bhalt\w*|\babort\w*|"
            r"\bbuild\w*\b[^.;]{0,60}\bfrom (?:that|the|this|a) fresh\b|\bfrom (?:that|the|this) fresh retrieve\b")
    # pressing on past a difference, in the sentence that says what a difference means
    PRESS_ON = (r"\banyway\b|\bregardless\b|\bnevertheless\b|\bnonetheless\b|\bproceed\w*|\bcontinu\w*|\bcarry on\b|"
                r"\bgo ahead\b|\bignor\w*|\bstill (?:re)?deploy\w*|\ball the same\b")
    # a difference overridden, anywhere in the rollback
    OVERRIDE = (r"(?i)\beven (?:if|when|though) (?:they|it|the \w+|`[^`]*`) (?:differ|do not match|don't match|changed)\w*|"
                r"\bignor\w* (?:the|any|a) (?:difference|diff\w*|compar\w*|mismatch\w*)|"
                r"\bregardless of (?:the |any )?(?:difference|diff\w*|compar\w*|change\w*|mismatch\w*)|"
                r"\bwhether or not (?:they|it) (?:differ|match|equal)\w*")
    ONLY = r"\bonly\b|\balone\b|\bnothing else\b|\bthe one (?:file|component)\b|\bjust\b|\bsingle\b"
    DEPLOY_VERB = re.compile(r"(?i)\b(?:re)?deploy\w*")
    # what the rollback redeploys besides the dashboard: nothing - no report, field, permission set, profile or package
    OTHER_METADATA = (r"(?i)\breports?\b(?! ?types?\b)|" + "|".join(REPORTS) + r"|\breport ?types?\b|\bpermission ?sets?\b|"
                      r"\bprofiles?\b|\bfields?\b|\bpackages?\b(?![·.]xml)|Attendance_Totals|Attendance_Report_Viewer")
    FOLDER = r"`[^`\s]*/`"
    OLDER = (r"(?i)\b(?:never|not|no|nor)\b[^.;]{0,80}?\b(?:older|old|earlier|previous|superseded|stale)\b[^.;]{0,40}?"
             r"(?:\bpackages?\b|\bcop(?:y|ies)\b|\bretrieves?\b|\bfolders?\b|\bbuilds?\b|before/|after/)|"
             r"\bnever\b[^.;]{0,80}?sf_girls_tiles_2026-10-20")
    REPORT_WORD = r"\breports?\b|" + "|".join(REPORTS)
    WHOSE = r"(?i)(?<![\w#])#102\b|\bfour\b|\btiming\b|" + "|".join(REPORTS)
    STAY = (r"\bstay\w*|\bremain\w*|\bkept\b|\bkeeps?\b|\buntouched\b|\bin place\b|\bunchanged\b|\bleft (?:as|alone|in place|untouched)\b|"
            r"\bleaves?\b[^.;]{0,60}\b(?:in place|as they are|alone|untouched)\b|\bnot (?:deleted|moved|touched|changed|retired)\b|"
            r"\bnever (?:deleted|touched|moved)\b")
    DELETE = r"\bdelet\w*|\bdestructive\w*"
    SIBLING_NAME = r"Attendance_Submissions|\bAttendance Submissions\b"
    SIBLING = SIBLING_NAME + r"|\bsibling\b"
    RETIRE = r"\bDecommissioned\b|\bretir\w*|\bmov\w*|\bdelet\w*|\bremov\w*|\bdestructive\w*"
    # the plan's Rollout: its list items in this order, each affirmed
    BUILT = r"(?<!\w)build(?:_sibling)?/"
    ROLLOUT = (
        (f"a fresh retrieve of the dashboard (`Dashboard:Attendance/{DASHBOARD}`), first", near(FRESH, DASHBOARD, 200)),
        ("the fresh retrieve compared with `dashboard_before/` (a difference: someone changed it since)",
         near(r"\bcompar\w*|\bequal\w*|\bdiffer\w*|\bdiff\b|\bidentical\b|\bsame as\b", r"dashboard_before\b")),
        ("the check-only deploy (`sf project deploy start --dry-run`), after the compare", CHECK_ONLY),
        ("Ryan's go, after the check-only deploy", RYANS_GO),
        ("the deploy, after the go", re.compile(r"(?i)\bdeploy\w*")),
        ("the read-back after the deploy: retrieve into `after/`", near(r"\bretriev\w*|\bread[- ]?back\b", r"after/")),
        ("the read-back compared with the build, `build/` by name", near(r"after/", BUILT)),
        ("the refresh, the PUT of RUNBOOK \"Attendance dashboard in Salesforce\" (`analytics/dashboards`), after the "
         "read-back", re.compile(r"(?i:\brefresh\w*)[^.]{0,200}?(?:\bPUT\b|analytics/dashboards|(?i:Refreshing through the API))|"
                                 r"(?:\bPUT\b|analytics/dashboards)[^.]{0,200}?(?i:\brefresh\w*)")),
        ("each new component against its report's total and its SOQL, after the refresh",
         near(r"\bSOQL\b", r"\breports?\b|\btotals?\b|\bcomponents?\b")),
    )
    # what a difference at the Rollout's first compare means: rebuild from the fresh retrieve, stop, say so on the ticket
    ON_DIFFERENCE = (r"(?i)\b(?:re)?build\w*|\bstop\w*|\bhalt\w*|\bsay so\b|\bon the ticket\b|\bstart over\b|\bredo\b|"
                     r"\bfrom the fresh retrieve\b|\binstead\b")
    # the Build says what `build/` is made from
    MADE_FROM = r"\bfrom\b|\bcop(?:y|ied|ies)\b|\bedit\w*|\bbased on\b|\bmade\b|\bbuilt\b|\bstarts?\b|\bderived\b"
    # a risk of #103's own
    RISK_103 = (r"(?i)\bcomponent (?:limit|count)\b|\b(?:20|25|twenty)\b[^.]{0,40}\bcomponents?\b|\btoo many components\b|"
                r"\bsibling\b|Attendance Submissions|\bPartner filter\b|\bfilter (?:column|value)s?\b|\bweeks?\b|\bLAST_WEEK\b|"
                r"\bchanged (?:it |the dashboard )?since\b|\bsince the (?:fresh )?retrieve\b|\brefresh\w*|\bthreshold\b|"
                r"\bread (?:it )?as\b|\bmisread\w*|\brunning user\b|\bviewers?\b|Attendance_Report_Viewer|\bHow to read\b|"
                r"\bbox\b|\bblank[- ]partner\b|\bpilot\b|\bleadership\b")
    # the Result says what was built or deployed
    RESULT_CONTENT = r"(?i)\bbuil[dt]\w*|\bdeploy\w*|\bcheck-only\b|\bread[- ]?back\b|\bretriev\w*|\b0Af\w{12,15}\b"
    ROLLOUT_DENIABLE = (("comparing the fresh retrieve with `dashboard_before/`", near(r"\bcompar\w*", r"dashboard_before\b")),
                        ("comparing `after/` with the build", near(r"after/", r"\bcompar\w*")))
    UNFILTERED = r"\bAll\b|(?i:\bunfiltered\b|\bno filter\b|\bwithout (?:a |any )?filter\b)"
    ONE_PARTNER = r"(?i)filter1|\bone partner|\ba partner\b|\bsingle partner|\bone of the partners\b|\beach partner"

    def section(self):
        """The section's raw Markdown; a missing heading fails here (md_part)."""
        return md_part(self.RUNBOOK, self.HEADING)

    def rollback_parts(self):
        """Every Rollback part of the section: from a run-in `**Rollback...**` paragraph at the start of a line,
        or a heading that names Rollback, to the next such paragraph or heading."""
        part = self.section()
        out = []
        for m in re.finditer(r"(?m)^(?:\*\*[^*\n]*\bRollback\b[^*\n]*\*\*|#{3,6} [^\n]*\bRollback\b)[^\n]*", part):
            rest = part[m.end():]
            nxt = re.search(r"(?m)^(?:\*\*[^*\n]+\*\*|#{1,6} )", rest)
            out.append(rest[:nxt.start()] if nxt else rest)
        return out

    @classmethod
    def deletes_reports(cls, sentence):
        """A report deletion the sentence affirms: a deletion verb beside a report, neither negated nor
        "nothing is deleted" / "none of them" in its clause."""
        for m in matches(sentence, near(cls.DELETE, cls.REPORT_WORD, 60)):
            if negated(sentence, m):
                continue
            if any(re.search(r"(?i)\bnothing\b|\bnone\b", clause_of(sentence, at)) for at in (m.start(), max(m.end() - 1, m.start()))):
                continue
            return m
        return None

    # a contrast between a component and a report ("unlike the metric, `X` averages ...") pairs nothing
    CONTRAST_SPAN = r"(?i)\bunlike\b|\bwhereas\b|\bwhile\b|\bapart from\b|\bexcept\b|\bbesides\b|\bbut\b|\brather than\b|\binstead of\b"

    @classmethod
    def pairings(cls, sentence, loose=False):
        """[(kind, report, Span)] for each component kind word of `sentence` beside one of #102's reports. Strict (what
        a component must not read): the report named next after the kind ("the bar chart reads `X`, the table reads
        `Y`" pairs chart-X and table-Y), no contrast between; else the report right before it in the same clause
        ("`X` feeds the bar chart"). Loose (what a component must read): the next report after it or, failing that,
        the last one before it, other kind words between allowed ("`X` feeds two components: a tile ... and a
        table ..."). The span runs from one to the other."""
        tokens = sorted([(m.start(), m.end(), kind, None) for kind, p in cls.KINDS for m in re.finditer(f"(?i){p}", sentence)]
                        + [(m.start(), m.end(), None, r) for r in REPORTS for m in re.finditer(re.escape(r), sentence)])
        out = []
        for i, (start, end, kind, _) in enumerate(tokens):
            if not kind:
                continue
            rest = tokens[i + 1:] if loose else tokens[i + 1:i + 2]
            after = next((t for t in rest if t[3]), None) if loose else (rest[0] if rest and rest[0][3] else None)
            if after and (loose or not re.search(cls.CONTRAST_SPAN, sentence[end:after[0]])):
                out.append((kind, after[3], Span(start, after[1])))
                continue
            if after:
                continue
            if loose:
                before = next((t for t in reversed(tokens[:i]) if t[3]), None)
            else:
                before = tokens[i - 1] if i and tokens[i - 1][3] and not CLAUSE_END.search(sentence, tokens[i - 1][1], start) else None
            if before:
                out.append((kind, before[3], Span(before[0], end)))
        return out

    @classmethod
    def paired(cls, unit, loose=False):
        """[(kind, report, sentence)] for every pairing in the block `unit` that its clause does not deny."""
        out = []
        for s in sentences(unit, ".;"):
            s = names_unnegated(s)
            out += [(kind, report, s) for kind, report, span in cls.pairings(s, loose) if not negated(s, span)]
        return out

    def box_regions(self, part):
        """The text (prose()) of each bullet, paragraph or table row that names the How-to box, with the list items or
        table rows right after it when it is a paragraph or ends in a colon (the box's bullets), when it speaks of
        the timing."""
        typed = typed_blocks(part)
        out = []
        for i, (kind, text) in enumerate(typed):
            if re.search(self.BOX, text):
                region = [text]
                if kind == "para" or text.rstrip().endswith(":"):
                    for k, t in typed[i + 1:]:
                        if k == "para":
                            break
                        region.append(t)
                if re.search(self.BOX_TIMING, " ".join(region)):
                    out.append(prose(" ".join(region)))
        return out

    @classmethod
    def monday_start(cls, sentence):
        """The first Monday-start week the sentence affirms: no negation within two words before it, and no contrast
        in its clause or in the 30 characters before it ("Sunday to Saturday, not Monday to Sunday", "not an ISO
        (Monday to Sunday) week")."""
        for m in re.finditer(cls.MONDAY_WEEK, sentence, re.I):
            start, end = clause_span(sentence, m.start())
            if (re.search(f"(?i){NEG_BEFORE}", sentence[start:m.start()]) or re.search(f"(?i){cls.CONTRAST}", sentence[start:end])
                    or re.search(f"(?i){cls.CONTRAST}", sentence[max(0, m.start() - 30):m.start()])):
                continue
            return m
        return None

    @classmethod
    def late_header(cls, sentence):
        """The first "Late ..." header the sentence affirms (neither a negation before it nor NOT_SAID in its clause),
        the report's own label after "report" aside."""
        for m in re.finditer(cls.LATE_HEADER, sentence, re.I):
            start, end = clause_span(sentence, m.start())
            if re.search(f"(?i){NEG_BEFORE}", sentence[start:m.start()]) or re.search(f"(?i){cls.NOT_SAID}", sentence[start:end]):
                continue
            late = m.start() + [w.start() for w in re.finditer(r"(?i)\bLate\b", m.group(0))][-1]
            if re.search(cls.REPORT_LABEL, sentence[max(0, late - 40):late]):
                continue
            return m
        return None

    @classmethod
    def has_time(cls, sentence):
        """A clause of a sentence about the back-fill or the monthly batches that gives them a submission time or a
        delay ("show a submission time"), not negated; a clause about the other batches ("only a live Jotform batch
        has one") aside."""
        for m in re.finditer(cls.HAS_TIME, sentence, re.I):
            start, end = clause_span(sentence, m.start())
            clause = sentence[start:end]
            if re.search(f"(?i){NEG_BEFORE}", sentence[start:m.start()]) or NEGATION.search(clause):
                continue
            about = re.search(cls.BACKFILL, clause) or re.search(cls.MONTHLY, clause)
            if not about and re.search(cls.OTHER_BATCHES, clause):
                continue
            return m
        return None

    def test_the_runbook_lists_the_dashboard_timing_components(self):
        part = self.section()
        raw = flat(part)
        text = prose(raw)
        said = sentences(text, ".;")
        units = [prose(b) for b in blocks(part)]
        where = f"RUNBOOK section {self.HEADING[3:]!r}"
        # the four components, each beside the report it reads: its kind and the report's DeveloperName paired in one
        # sentence (the report right after the kind, else right before it), not negated, and the block (bullet,
        # paragraph, table row) saying what it shows
        for what, report, kind, extras in self.COMPONENTS:
            with self.subTest(component=what):
                found = [u for u in units if (kind, report) in [(k, r) for k, r, _ in self.paired(u, loose=True)]]
                self.assertTrue(found, f"{where}: name {what} beside the report it reads, `{report}` - the component's kind "
                                       "and the report's DeveloperName in one sentence, with no other component or report "
                                       "between them (a negation does not count)")
                lacks = min(([label for label, p in extras if not re.search(f"(?i){p}", u)] for u in found), key=len)
                self.assertFalse(lacks, f"{where}: {what} on `{report}`: say {' and '.join(lacks)} where it is named (the "
                                        "same bullet, paragraph or table row)")
        # no component paired with a report it does not read: the swapped "the bar chart reads the weekly list"
        wrong = [(k, r, s) for u in units for k, r, s in self.paired(u) if r not in self.READS_REPORT[k]]
        self.assertFalse(wrong, f"{where}: a {wrong[0][0] if wrong else ''} is said to read `{wrong[0][1] if wrong else ''}`, "
                                "which no such component reads (a metric reads `Clubs_Not_Submitting_Last_Week` or "
                                "`Late_Submissions_Last_Month`, the table `Clubs_Not_Submitting_Last_Week`, the bar chart "
                                f"`Submission_Delay_by_Partner_by_Month`): {wrong[0][2] if wrong else ''!r}")
        # the submissions metric counts every submission of last month, whatever its delay - not late ones
        late = [u for u in units if ("metric", "Late_Submissions_Last_Month") in [(k, r) for k, r, _ in self.paired(u, loose=True)]]
        self.assertTrue([u for u in late if affirms(u, self.ALL_SUBMISSIONS) or re.search(self.NO_THRESHOLD, u)],
                        f"{where}: the metric on `Late_Submissions_Last_Month` counts every Jotform submission of last month, "
                        "whatever its delay (no threshold: DECISIONS 2026-10-23) - say so where it is named")
        counts = [s for s in said if affirms(s, self.COUNTS_LATE, denied=self.NOT_SAID)]
        self.assertFalse(counts, f"{where}: the submissions metric counts every submission of last month, not the late ones "
                                 f"(no threshold: DECISIONS 2026-10-23): {counts[0] if counts else ''!r}")
        # each follows the dashboard's Partner filter: said in a block about the timing components, or in a sentence
        # that names them as the new (four, timing) components
        follow = near(self.PARTNER_FILTER, self.FOLLOWS, 120)
        timing = [s for u in units if re.search(self.TIMING, u) for s in sentences(u, ".;")
                  if re.search(self.EACH, s) or all(r in s for r in DASH_REPORTS)]
        self.assertTrue([s for s in timing + [s for s in said if re.search(self.NEW_ONES, s)] if affirmed(names_unnegated(s), follow)],
                        f"{where}: say each new component follows the dashboard's Partner filter, in a sentence that names "
                        "them (\"each new component\", \"the four\") or in the bullet or paragraph about them (\"The "
                        "dashboard's Partner filter covers every component\" says it of the old ones); a negation does not count")
        # the How-to box, documented with the timing it now defines: the definitions stand in the bullet or paragraph
        # that names the box (or the list right after it), each in a sentence
        box = self.box_regions(part)
        self.assertTrue(box, f"{where}: say what the \"How to read this dashboard\" box adds for the timing (the week, the "
                             "submission time, which batches have none, no threshold), in a bullet or paragraph that names the box")
        told = [s for region in box for s in sentences(region, ".;")]
        in_box = "in the bullet or paragraph that names the \"How to read this dashboard\" box (or the list right after it)"
        self.assertIn("LAST_WEEK", raw, f"{where}: name `LAST_WEEK`, the report's week (DECISIONS 2026-10-24)")
        self.assertTrue([s for s in told if re.search(r"(?i)\bweeks?\b|\bLAST_WEEK\b", s) and affirms(s, TimingReportsDocs.SUN_SAT)
                         and not self.monday_start(s)],
                        f"{where}: the box: last week runs Sunday to Saturday (`LAST_WEEK`), {in_box}, in a sentence with no "
                        "negation right before it and no Monday-start week affirmed in it")
        self.assertTrue([s for s in told if affirmed(s, near(self.SUBMITTED, self.CREATED, 150))],
                        f"{where}: the box: what \"submitted at\" (`Submitted_At__c`, the submission time) is - the batch's "
                        f"`CreatedDate`, by name - {in_box}, in a sentence (a negation does not count)")
        for kind, pattern in (("the September back-fill batches", self.BACKFILL),
                              ("the three partners' monthly batches (`Partner report`)", self.MONTHLY)):
            with self.subTest(batches=kind):
                self.assertTrue([s for s in told if re.search(pattern, s) and re.search(self.HAS_NONE, s)],
                                f"{where}: the box: {kind} have no submission time (and so no delay) - \"no submission "
                                f"time\", \"no delay\", \"have none\" - {in_box}")
        self.assertTrue([s for s in told if re.search(self.NO_THRESHOLD, s)],
                        f"{where}: the box: there is no late threshold - the delay in days is shown and staff judge it "
                        f"(DECISIONS 2026-10-23) - {in_box}")
        # nowhere a Monday-start week, "submitted at" as a modification stamp, those batches with a submission time
        monday = [s for s in said if self.monday_start(s)]
        self.assertFalse(monday, f"{where}: a sentence affirms a Monday-start week (last week is Sunday to Saturday, "
                                 f"`LAST_WEEK`; a contrast carries \"not\" in its clause): {monday[0] if monday else ''!r}")
        stamp = [s for s in said if affirmed(s, near(self.SUBMITTED, self.WRONG_STAMP, 60))]
        self.assertFalse(stamp, f"{where}: \"submitted at\" is the batch's `CreatedDate`, never its `LastModifiedDate` or "
                                f"another modification stamp: {stamp[0] if stamp else ''!r}")
        timed = [s for s in said if (re.search(self.BACKFILL, s) or re.search(self.MONTHLY, s)) and self.has_time(s)]
        self.assertFalse(timed, f"{where}: the September back-fill and the three partners' monthly batches have no "
                                f"submission time and no delay: {timed[0] if timed else ''!r}")
        # no threshold anywhere: never stated as a number of days or weeks (digits or words) or a "Late ..." header
        cut = [s for s in said if re.search(self.ABOUT_DELAY, s) and affirms(s, self.DAY_THRESHOLD)]
        self.assertFalse(cut, f"{where}: a sentence about late submissions, the delay or a metric states a cut-off in days "
                              f"(none: DECISIONS 2026-10-23; quote no threshold, not even the outline's): {cut[0] if cut else ''!r}")
        headed = [s for s in said if self.late_header(s)]
        self.assertFalse(headed, f"{where}: a metric headed \"Late ...\" reads as a count of late submissions (Ruling: the "
                                 f"submissions metric is headed so nobody reads it so): {headed[0] if headed else ''!r}")

    def dashboard_rollback(self, where, text, sibling):
        """#103's rollback in `text` (flattened, prose()): `sibling` says the sibling dashboard is named beside it."""
        said = sentences(text, ".;")
        self.assertIn(DASH_FOLDER, text, f"{where}: name the folder `data/{DASH_FOLDER}/` the rollback deploys from")
        self.assertTrue(names_job_folder(text), f"{where}: name `data/{DASH_FOLDER}/` as #103's own folder, in a sentence "
                                                "that does not call it superseded, older or never used")
        self.assertIn(DASHBOARD, text, f"{where}: name the dashboard `Attendance/{DASHBOARD}`")
        self.assertTrue(affirmed(text, near(r"\b(?:re)?deploy\w*", r"dashboard_before\b")),
                        f"{where}: the dashboard is redeployed from `data/{DASH_FOLDER}/dashboard_before/` (said of the "
                        "deploy, not negated)")
        self.assertTrue([s for s in said if re.search(r"(?i)\b(?:re)?deploy\w*", s)
                         and affirmed(s, near(self.ONLY, rf"{DASHBOARD}|\bdashboard\b", 60))],
                        f"{where}: redeploy ONLY the dashboard (`{DASHBOARD}`), said in the deploy's sentence")
        # ... and no deploy sentence redeploys anything else: a report, a field, a permission set, a package, or a folder
        # other than `dashboard_before/` as the deploy's source (a negated clause, or "the reports stay", aside)
        for s in said:
            if not any(not negated(s, m) for m in matches(s, self.DEPLOY_VERB)):
                continue
            for m in re.finditer(self.OTHER_METADATA, s):
                clause = clause_of(s, m.start())
                self.assertTrue(NEGATION.search(clause) or re.search(f"(?i){self.STAY}", clause),
                                f"{where}: the rollback redeploys only the dashboard - this deploy sentence also deploys "
                                f"{m.group(0)!r}: {s!r}")
            for m in re.finditer(self.FOLDER, s):
                path, (start, end) = m.group(0), clause_span(s, m.start())
                if re.search(r"dashboard_before/`$|force-app", path) or NEGATION.search(s, start, end):
                    continue
                if re.search(r"(?i)\b(?:into|with|to|against|beside|than)\s+(?:the\s+)?$", s[max(0, m.start() - 20):m.start()]):
                    continue                                    # a retrieve's target or a compare's other side
                source = (re.search(r"(?i)\bfrom\s+(?:within\s+|inside\s+|in\s+)?(?:the\s+)?$", s[max(0, m.start() - 30):m.start()])
                          or any(not negated(s[start:end], d) for d in matches(s[start:end], self.DEPLOY_VERB)))
                self.assertFalse(source, f"{where}: the rollback deploys only from `data/{DASH_FOLDER}/dashboard_before/` - "
                                         f"this deploy sentence deploys {path}: {s!r}")
        # the gate: a fresh retrieve compared with #103's own read-back, in a sentence that names no other change
        self.assertTrue([s for s in said if re.search(self.READ_BACK, s) and affirmed(s, near(self.FRESH, self.COMPARE))
                         and not re.search(self.OTHER_CHANGE, s)],
                        f"{where}: first a fresh retrieve of the dashboard, compared with #103's read-back (`data/{DASH_FOLDER}/"
                        "after/`, or `after/` beside `dashboard_before/`), in one sentence that names no other change's "
                        "folder (#59's `sf_girls_tiles_2026-10-20/after/` predates the timing); a negation does not count")
        # another change's folder or ticket only where it is denied, or named as the older package never deployed
        for m in re.finditer(self.OTHER_CHANGE, text):
            s = sentence_at(text, m.start())
            ok = negated(text, m) or (re.search(self.OLDER, s) and not affirmed(
                s, re.compile(r"(?i)\b(?:re)?deploy\w*|\bcompar\w*|\bequal\w*|\bmatch\w*|\bdiff\b|\bfrom (?:within )?`")))
            self.assertTrue(ok, f"{where}: {m.group(0)} is another change - #103's rollback compares with its own `after/` "
                                f"and deploys only `dashboard_before/`; name another change's folder only as the older "
                                f"package never used: {s.strip()!r}")
        self.assertTrue([s for s in said if re.search(self.DIFFER, s) and affirms(s, self.STOP)],
                        f"{where}: when the fresh retrieve differs from `after/`, someone changed it since - stop and build "
                        "the rollback from the fresh retrieve - in a sentence")
        pressed = [s for s in said if (re.search(self.DIFFER, s) and affirms(s, self.PRESS_ON)) or affirmed(s, re.compile(self.OVERRIDE))]
        self.assertFalse(pressed, f"{where}: a difference stops the rollback - nothing goes ahead anyway: "
                                  f"{pressed[0] if pressed else ''!r}")
        self.assertTrue(affirmed(text, CHECK_ONLY), f"{where}: check-only first (`sf project deploy start --dry-run`)")
        self.assertTrue(affirmed(text, RYANS_GO), f"{where}: the redeploy on Ryan's go")
        self.assertRegex(text, self.OLDER, f"{where}: never an older package (DECISIONS 2026-10-16) - e.g. #59's "
                                           "`data/sf_girls_tiles_2026-10-20/before/` - said for this rollback")
        reports = [s for s in said if re.search(f"(?i){self.REPORT_WORD}", s)]
        deleting = [s for s in reports if self.deletes_reports(s)]
        self.assertFalse(deleting, f"{where}: deletes reports - #102's reports are never deleted (DECISIONS 2026-10-21; "
                                   f"Task #102's Rollback retires them): {deleting[0] if deleting else ''!r}")
        retired = [s for s in said if re.search(self.SIBLING, s) and affirms(s, self.RETIRE)]
        if sibling:
            self.assertTrue(retired, f"{where}: the sibling dashboard \"Attendance Submissions\" is named: retire it with the "
                                     "rollback (to Decommissioned), not leave it behind")
        else:
            self.assertTrue([s for s in reports if re.search(self.WHOSE, s) and affirms(s, self.STAY)],
                            f"{where}: say #102's four reports stay (the rollback changes only the dashboard), in a sentence")

    def test_the_dashboard_rollback_redeploys_only_the_changed_dashboard(self):
        where = f"RUNBOOK section {self.HEADING[3:]!r}, Rollback"
        parts = self.rollback_parts()
        self.assertTrue(parts, f"{where}: no Rollback part (`**Rollback:**`)")
        items = [i for p in parts for i in top_items(p) if re.search(r"dashboard_before\b", i)]
        self.assertTrue(items, f"{where}: no item for #103's rollback - redeploy only the dashboard `Attendance/{DASHBOARD}` "
                               f"from `data/{DASH_FOLDER}/dashboard_before/`, after a fresh retrieve equals `after/`")
        # #103's own item when its first sentence says so (another change's item may point at it: "roll #103 back first")
        own = [i for i in items if re.search(r"(?<![\w#])#103\b|\btiming\b", sentences(i, ".;")[0])]
        items = own or items
        sibling = bool(re.search(self.SIBLING_NAME, flat(self.section())))
        self.dashboard_rollback(where + " (#103)", prose(" ".join(items)), sibling)

    def dashboard_rollout(self, where, part):
        """The steps in this order over the Rollout's list items, each affirmed at or after the one before it; no
        compare argued against anywhere in the Rollout; a check of each component under All and under one
        partner; `build_sibling/` on a component-count refusal."""
        text = prose(flat(part))
        self.assertIn("sf project deploy start", text, f"{where}: the deploy command `sf project deploy start`")
        for what, pattern in self.ROLLOUT_DENIABLE:
            m = denied(text, pattern)
            self.assertIsNone(m, f"{where}: argues against {what}: {clause_of(text, m.start()).strip()!r}" if m else None)
        items = list_items(part)
        self.assertGreaterEqual(len(items), 5, f"{where}: the steps as a numbered (or bulleted) list, in order")
        walk = " . ".join(prose(item) for item in items)
        at = 0
        for what, pattern in self.ROLLOUT:
            m = affirmed(walk, pattern, at)
            self.assertTrue(m, f"{where}: {what} (the steps in that order, in the list's items; a negated statement does "
                               "not count)")
            at = m.start()
        self.assertTrue([i for i in items if re.search(r"\bSOQL\b", i) and re.search(self.UNFILTERED, i)
                         and re.search(self.ONE_PARTNER, i)],
                        f"{where}: a step checks each new component against its report and its SOQL under All (unfiltered) "
                        "and under one partner's filter (`?filter1=<option id>`)")
        # the first compare: with `dashboard_before/`, what a difference means said in the same step, and no other
        # change's read-back in it
        compare =near(r"\bcompar\w*|\bequal\w*|\bdiff\w*|\bidentical\b|\bsame as\b", r"dashboard_before\b")
        steps = [prose(i) for i in items if affirmed(prose(i), compare)]
        self.assertTrue([i for i in steps if re.search(self.DIFFER, i) and re.search(self.ON_DIFFERENCE, i)],
                        f"{where}: the step that compares the fresh retrieve with `dashboard_before/` says what a difference "
                        "means - someone changed it since: rebuild from the fresh retrieve and say so on the ticket")
        other = [i for i in steps if any(not negated(i, m) for m in matches(i, re.compile(self.OTHER_CHANGE)))]
        self.assertFalse(other, f"{where}: the fresh retrieve is compared with #103's `dashboard_before/`, not another "
                                f"change's folder: {other[0] if other else ''!r}")
        self.assertTrue(affirmed(text, near(r"--dry-run|check-only|\bvalidat\w*", r"(?<!\w)build/")),
                        f"{where}: the check-only of `build/` (the four components on `{DASHBOARD}`)")
        self.assertRegex(text, near(r"build_sibling/", r"\brefus\w*|\breject\w*|\blimit\w*|\btoo many\b|\bcomponent count\b|\bfails?\b", 200),
                         f"{where}: `build_sibling/` (the dashboard \"Attendance Submissions\") when the check-only refuses "
                         "`build/`'s component count")

    def test_the_plan_carries_the_dashboard_rollout(self):
        plans = SubmissionTimingDocs.plans_naming(self, 103)
        self.assertTrue(plans, "docs/plans/: no plan names ticket #103 in its head (the dashboard change is live: CLAUDE.md "
                               "conventions)")
        tasks = [(p, md_sub(read(p), "## Task #103")) for p in plans]
        tasks = [(p, t) for p, t in tasks if t]
        self.assertTrue(tasks, f"{', '.join(os.path.relpath(p, REPO) for p in plans)}: no section `## Task #103: ...` (the "
                               "dashboard's Build, Rollout, Rollback, Risks and Result, after Task #102's)")
        for path, task in tasks:
            name = os.path.relpath(path, REPO)
            parts = {}
            for heading, least in (("### Build", 30), ("### Rollout", 60), ("### Rollback", 30), ("### Risks", 15),
                                   ("### Result", 15)):
                sub = md_sub(task, heading)
                self.assertIsNotNone(sub, f"{name}: `## Task #103` has no `{heading}`")
                body = sub.split("\n", 1)[1] if "\n" in sub else ""
                self.assertNotRegex(flat(body), r"(?i)\b(TBD|TODO|TBA|FIXME)\b", f"{name}: Task #103 `{heading}` is a placeholder")
                self.assertGreaterEqual(len(re.findall(r"\w+", body)), least,
                                        f"{name}: Task #103 `{heading}` says too little (at least {least} words)")
                parts[heading] = body
            # the Build: what `build/` holds (the dashboard, the three reports its components read, the box) and that it
            # is made from the fresh retrieve `dashboard_before/`, said in a sentence
            self.assertIn(DASH_FOLDER, task, f"{name}: Task #103: name the folder `data/{DASH_FOLDER}/` that holds "
                                             "`dashboard_before/`, `build/` and `after/`")
            build = prose(flat(parts["### Build"]))
            # ... as the Build's own folder: a mention that calls it superseded, older or never used (as the 2026-10-26
            # retrieve is) does not count
            self.assertTrue(names_job_folder(build),
                            f"{name}: Task #103 Build: say the build is in `data/{DASH_FOLDER}/` (the fresh retrieve of "
                            "2026-11-19), in a sentence that does not call that folder superseded, older or never used")
            for what, pattern in (("`build/`", r"(?<!\w)build/"), ("the fresh retrieve `dashboard_before/`", r"dashboard_before\b"),
                                  (f"the dashboard `{DASHBOARD}`", DASHBOARD),
                                  *((f"the report `{r}` (a component reads it)", re.escape(r)) for r in DASH_REPORTS),
                                  ("the \"How to read this dashboard\" box", self.BOX)):
                self.assertRegex(build, pattern, f"{name}: Task #103 Build: say what `build/` holds - name {what}")
            self.assertTrue([s for s in sentences(build, ".;") if re.search(r"(?<!\w)build/", s) and re.search(r"dashboard_before\b", s)
                             and affirms(s, self.MADE_FROM)],
                            f"{name}: Task #103 Build: `build/` is made from `dashboard_before/` (a copy of it, edited), "
                            "said in one sentence")
            self.dashboard_rollout(f"{name}: Task #103 Rollout", parts["### Rollout"])
            sibling = bool(re.search(self.SIBLING_NAME, flat(task)))
            self.dashboard_rollback(f"{name}: Task #103 Rollback", prose(flat(parts["### Rollback"])), sibling)
            # the Risks: no dismissive opening (as #101's), and a risk of #103's own (#101's keywords - `CreatedDate`, a
            # field, a permission - are another change's)
            self.assertNotRegex(flat(parts["### Risks"]),
                                r"(?i)^\W*(?:none|no risks?|n/?a|nothing|hardly|few|little|minimal|negligible|harmless)\b",
                                f"{name}: Task #103 Risks: name at least one real risk (no dismissive opening)")
            self.assertRegex(flat(parts["### Risks"]), self.RISK_103,
                             f"{name}: Task #103 Risks: a risk of this change - the component limit (the sibling dashboard), "
                             "a component the Partner filter does not reach, the week read as Monday to Sunday, a change "
                             "since the retrieve, the live leadership dashboard")
            self.assertRegex(parts["### Result"], r"\b20\d\d-\d\d-\d\d\b", f"{name}: Task #103 Result: dated entries")
            self.assertRegex(flat(parts["### Result"]), self.RESULT_CONTENT,
                             f"{name}: Task #103 Result: say what was built, check-only'd, deployed or read back")


if __name__ == "__main__":
    unittest.main()
