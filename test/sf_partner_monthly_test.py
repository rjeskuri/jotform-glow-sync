#!/usr/bin/env python3
"""
Offline tests for tools/sf_partner_monthly.py (ticket #60; found by `make py`'s unittest discovery).

The tool copies the three Salesforce-reporting partners' "Monthly Max" (DHIS2__c.Monthly_Total__c of
their Monthly Report for the month) into one Attendance_Batch__c per partner (Creator__c 'Partner
report', dated the month's last day). The three partner names are real partner organisations (they
are in the repo's docs); everything else - ids, counts, other accounts, the girl's name planted in
fields the tool must never read - is fictional.

The fake org below answers any plain SOQL the tool may write (SELECT fields FROM object WHERE ...
with AND/OR/parentheses, =, !=, <, >, <=, >=, IN, NOT IN, LIKE; ORDER BY and LIMIT are accepted) over
three objects - Account, DHIS2__c and Attendance_Batch__c - and stands in for the attendance processor
on insert: the batch attaches to the Account whose name equals Account_Name__c (a stray Club account is
made when none does), a batch with no names and Girls_Present__c above 0 succeeds with no rows, a
second Success for the same account and day is Failed. A PATCH changes only the fields sent.
"""
import calendar
import contextlib
import copy
import datetime
import io
import os
import random
import re
import stat
import string
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.join(REPO, "test", "fixtures"))
import make_fixture                                        # noqa: E402  (the invented name pools)
import sf_partner_monthly as spm                           # noqa: E402

EEFY, TLM, NGAA = "Education and English for You", "Tumaini La Maisha", "Ng'aa Maskani"
PARTNERS = [EEFY, TLM, NGAA]
OTHER_PARTNER = "Northwind Girls Trust"      # a fourth partner: never read
LOOKALIKE = "Tumaini La Maisha Youth"        # a near name: never matched
CLUB = "Kestrel Hill Club"
ALNUM = string.ascii_letters + string.digits


def fresh_id(prefix):
    """A new 18-character record id each time: a tool that hard-codes an id cannot pass."""
    return prefix + "".join(random.choice(ALNUM) for _ in range(18 - len(prefix)))
# A fictional girl's name, in fields the tool must never select. Built from make_fixture's FIRST/LAST
# pools (the project's source of fictional names; LAST names are invented, so no real roster has the pair).
# Fixed indexes, not random, so a failure reproduces.
GIRL_FIRST, GIRL_LAST = make_fixture.FIRST[12], make_fixture.LAST[1]
GIRL = f"{GIRL_FIRST} {GIRL_LAST}"
REPORT = "Partner report"


def last_month(day):
    first = day.replace(day=1)
    prev = first - datetime.timedelta(days=1)
    return prev.year, prev.month


def tag(year, month):
    return f"{year:04d}-{month:02d}"


def end_of(year, month):
    return f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


# ---- a minimal SOQL evaluator ---------------------------------------------------------------------
TOKEN = re.compile(r"\s*(?:('(?:[^'\\]|\\.)*')|(!=|<=|>=|=|<|>)|(\()|(\))|(,)|([^\s(),=<>!']+))")


def tokens(text):
    out, pos = [], 0
    text = text.strip()
    while pos < len(text):
        m = TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise AssertionError(f"the fake cannot read this WHERE clause: {text!r}")
        pos = m.end()
        string, op, lp, rp, comma, word = m.groups()
        if string is not None:
            out.append(("str", re.sub(r"\\(.)", r"\1", string[1:-1])))
        elif op:
            out.append(("op", op))
        elif lp:
            out.append(("(", "("))
        elif rp:
            out.append((")", ")"))
        elif comma:
            out.append((",", ","))
        else:
            out.append(("word", word))
        while pos < len(text) and text[pos].isspace():
            pos += 1
    return out


def literal(tok):
    kind, value = tok
    if kind == "str":
        return value
    low = value.lower()
    if low == "null":
        return None
    if low in ("true", "false"):
        return low == "true"
    return value                              # a number or a date literal, as text


def norm(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if re.fullmatch(r"-?\d+\.0+", text):
        return text.split(".")[0]
    return text.casefold()


def field_of(record, path):
    value = record
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = next((v for k, v in value.items() if k.lower() == part.lower()), None)
    return value


def compare(a, op, b):
    if op in ("=", "!="):
        same = norm(a) == norm(b)
        return same if op == "=" else not same
    if a is None or b is None:
        return False
    try:
        x, y = float(a), float(b)
    except (TypeError, ValueError):
        x, y = str(a), str(b)
    return {"<": x < y, ">": x > y, "<=": x <= y, ">=": x >= y}[op]


class Where:
    def __init__(self, text):
        self.toks, self.i = tokens(text), 0

    def peek(self, word=None):
        if self.i >= len(self.toks):
            return None
        tok = self.toks[self.i]
        if word is None:
            return tok
        return tok if tok[0] == "word" and tok[1].upper() == word else None

    def take(self):
        tok = self.toks[self.i]
        self.i += 1
        return tok

    def parse(self):
        tree = self.expr()
        if self.i != len(self.toks):
            raise AssertionError(f"the fake cannot read the rest of a WHERE clause: {self.toks[self.i:]}")
        return tree

    def expr(self):
        node = self.term()
        while self.peek("OR"):
            self.take()
            node = ("or", node, self.term())
        return node

    def term(self):
        node = self.factor()
        while self.peek("AND"):
            self.take()
            node = ("and", node, self.factor())
        return node

    def factor(self):
        if self.peek("NOT"):
            self.take()
            return ("not", self.factor())
        if self.peek() and self.peek()[0] == "(":
            self.take()
            node = self.expr()
            assert self.take()[0] == ")"
            return node
        field = self.take()[1]
        negate = False
        if self.peek("NOT"):
            self.take()
            negate = True
        if self.peek("IN"):
            self.take()
            assert self.take()[0] == "("
            values = []
            while True:
                values.append(literal(self.take()))
                nxt = self.take()
                if nxt[0] == ")":
                    break
                assert nxt[0] == ",", nxt
            return ("in", field, values, negate)
        if self.peek("LIKE"):
            self.take()
            return ("like", field, literal(self.take()), negate)
        op = self.take()
        assert op[0] == "op", op
        return ("cmp", field, op[1], literal(self.take()))


def holds(node, record):
    kind = node[0]
    if kind == "and":
        return holds(node[1], record) and holds(node[2], record)
    if kind == "or":
        return holds(node[1], record) or holds(node[2], record)
    if kind == "not":
        return not holds(node[1], record)
    if kind == "in":
        found = any(compare(field_of(record, node[1]), "=", v) for v in node[2])
        return found != node[3]
    if kind == "like":
        pattern = "".join(".*" if c == "%" else "." if c == "_" else re.escape(c) for c in node[2])
        value = field_of(record, node[1])
        found = value is not None and re.fullmatch(pattern, str(value), re.IGNORECASE | re.DOTALL) is not None
        return found != node[3]
    return compare(field_of(record, node[1]), node[2], node[3])


SOQL = re.compile(r"^\s*SELECT\s+(.+?)\s+FROM\s+(\w+)(?:\s+WHERE\s+(.+?))?(?:\s+ORDER\s+BY\s+.+?)?(?:\s+LIMIT\s+\d+)?\s*$",
                  re.IGNORECASE | re.DOTALL)


def project(record, fields):
    out = {}
    for f in fields:
        value = field_of(record, f)
        parts = f.split(".")
        spot = out
        for part in parts[:-1]:
            spot = spot.setdefault(part, {})
        spot[parts[-1]] = copy.deepcopy(value)
    return out


class PartnerOrg:
    """Salesforce as far as this tool can see it (fictional apart from the three partner names)."""
    alias = "fake"

    def __init__(self):
        self.acc = {p: fresh_id("001") for p in PARTNERS}            # the partner accounts' ids, new per org
        self.other_id, self.lookalike_id, self.club_id = fresh_id("001"), fresh_id("001"), fresh_id("001")
        self.accounts = [{"Id": self.acc[p], "Name": p, "Description": f"contact {GIRL}"} for p in PARTNERS] + [
            {"Id": self.other_id, "Name": OTHER_PARTNER, "Description": ""},
            {"Id": self.lookalike_id, "Name": LOOKALIKE, "Description": ""},
            {"Id": self.club_id, "Name": CLUB, "Description": ""}]
        self.reports, self.batches = [], []
        self.seen, self.inserts, self.updates = [], [], []
        self.refuse_insert = self.refuse_update = self.drift_update = False
        self.processor = {}          # overrides for the next inserted batch: Processing_Status__c, Account__c, Girls_Present__c

    # -- fixtures
    def name_of(self, acc_id):
        return next(a["Name"] for a in self.accounts if a["Id"] == acc_id)

    def report(self, partner, year, month, total):
        acc_id = self.acc.get(partner) or {OTHER_PARTNER: self.other_id, LOOKALIKE: self.lookalike_id}[partner]
        self.reports.append({"Id": fresh_id("a0D"), "Name": f"MR-{len(self.reports) + 1:05d}",
                             "Account__c": acc_id, "Account__r": {"Name": partner},
                             "YearMonth__c": float(f"{year:04d}{month:02d}"),   # a number field: 202609.0
                             "Monthly_Total__c": None if total is None else float(total),
                             "Notes__c": f"weekly sheet kept by {GIRL}"})

    def month(self, year, month, totals):
        """One report per partner for the month (None in `totals` leaves that partner without one),
        and noise: the same partners' reports for the month before and after, the fourth partner's and
        the look-alike's for this month."""
        for partner, total in zip(PARTNERS, totals):
            if total is not None:
                self.report(partner, year, month, total)
        prev = datetime.date(year, month, 1) - datetime.timedelta(days=1)
        nxt = datetime.date(year, month, 28) + datetime.timedelta(days=5)
        for i, partner in enumerate(PARTNERS):
            self.report(partner, prev.year, prev.month, 901 + i)
            self.report(partner, nxt.year, nxt.month, 911 + i)
        self.report(OTHER_PARTNER, year, month, 977)
        self.report(LOOKALIKE, year, month, 988)

    def batch(self, acc_id, date, count, creator=REPORT, status="Success", names=""):
        b = {"Id": "a1l%015d" % (len(self.batches) + 1), "Name": "BATCH-%06d" % (len(self.batches) + 1),
             "Account__c": acc_id, "Account__r": {"Name": self.name_of(acc_id)}, "Account_Name__c": self.name_of(acc_id),
             "Attendance_Date__c": date, "Processing_Status__c": status, "Creator__c": creator,
             "Girls_Present__c": None if count is None else float(count), "Contact_IDs__c": names,
             "Status_Message__c": f"Processed successfully. ({GIRL})", "enable_fuzzy_matching__c": False}
        self.batches.append(b)
        return b

    # -- the API the tool uses
    def call(self, *args, **kwargs):
        raise AssertionError("a raw REST call (composite, bulk, describe ...): every read is a SOQL query, "
                             "every write one insert or update")

    def table(self, sobject):
        tables = {"account": self.accounts, "dhis2__c": self.reports, "attendance_batch__c": self.batches}
        if sobject.lower() not in tables:
            raise AssertionError(f"the tool read an object it has no reason to read: {sobject}")
        return tables[sobject.lower()]

    def select(self, soql):
        self.seen.append(soql)
        m = SOQL.match(soql)
        if not m:
            raise AssertionError(f"the fake cannot read this SOQL: {soql}")
        fields, sobject, where = m.groups()
        records = self.table(sobject)
        if where:
            tree = Where(where).parse()
            records = [r for r in records if holds(tree, r)]
        return fields, records

    def query(self, soql):
        fields, records = self.select(soql)
        names = [f.strip() for f in fields.split(",")]
        if any("(" in f for f in names):
            raise AssertionError(f"the fake answers plain field lists only: {soql}")
        return [project(r, names) for r in records]

    query_all = query

    def count(self, soql):
        fields, records = self.select(soql)
        assert fields.strip().upper() == "COUNT()", soql
        return len(records)

    def insert(self, sobject, body):
        assert sobject == "Attendance_Batch__c", sobject
        assert isinstance(body, dict), "one record per request"
        self.inserts.append(copy.deepcopy(body))
        if self.refuse_insert is True or self.refuse_insert == body.get("Account_Name__c"):    # all, or one partner's
            return 400, [{"errorCode": "FIELD_CUSTOM_VALIDATION_EXCEPTION", "message": "refused"}]
        wanted = str(body.get("Account_Name__c", "")).strip().casefold()
        acc = next((a for a in self.accounts if a["Name"].casefold() == wanted), None)
        if acc is None:                       # the processor creates a stray Club account
            acc = {"Id": "001STRAY%010d" % len(self.accounts), "Name": body.get("Account_Name__c", ""), "Description": ""}
            self.accounts.append(acc)
        day, typed = body.get("Attendance_Date__c"), body.get("Girls_Present__c")
        names = [n for n in str(body.get("Contact_IDs__c") or "").split(",") if n.strip()]
        b = self.batch(acc["Id"], day, typed, creator=body.get("Creator__c"), names=body.get("Contact_IDs__c") or "")
        b["Account_Name__c"] = body.get("Account_Name__c")
        if any(o is not b and o["Account__c"] == acc["Id"] and o["Attendance_Date__c"] == day
               and o["Processing_Status__c"] == "Success" for o in self.batches):
            b.update(Processing_Status__c="Failed", Girls_Present__c=None,
                     Status_Message__c="Duplicate: A successful batch already exists for this account and date.")
        elif not names and not (isinstance(typed, (int, float)) and not isinstance(typed, bool) and typed > 0):
            b.update(Processing_Status__c="Failed", Girls_Present__c=None, Status_Message__c="No participants submitted")
        b.update(self.processor)
        self.processor = {}
        return 201, {"id": b["Id"], "success": True, "errors": []}

    def update(self, sobject, record_id, body):
        self.updates.append((sobject, record_id, copy.deepcopy(body)))
        if self.refuse_update:
            return 400, [{"errorCode": "FIELD_CUSTOM_VALIDATION_EXCEPTION", "message": "refused"}]
        found = [b for b in self.batches if b["Id"] == record_id] if sobject == "Attendance_Batch__c" else []
        if len(found) != 1:
            return 404, [{"errorCode": "NOT_FOUND", "message": "no such record"}]
        if not self.drift_update:
            found[0].update(body)
        return 204, None

    def partner_batches(self, partner, date):
        return [b for b in self.batches if b["Account__c"] == self.acc[partner] and b["Attendance_Date__c"] == date]


# ---- the tests -----------------------------------------------------------------------------------
class CanaryName(unittest.TestCase):
    def test_canary_comes_from_the_fixture_name_pools(self):
        first, last = GIRL.split(" ")
        self.assertIn(first, make_fixture.FIRST)
        self.assertIn(last, make_fixture.LAST)
        self.assertEqual(GIRL, f"{first} {last}")


class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = os.path.join(self.tmp.name, "ledger_dir")
        self.org = PartnerOrg()

    def fresh(self):
        self.org = PartnerOrg()
        self.dir = tempfile.mkdtemp(dir=self.tmp.name)
        return self.org

    def run_tool(self, *argv):
        """(stdout + stderr + the exit message, the exit code: None or 0 when it ended normally)."""
        out, err = io.StringIO(), io.StringIO()
        code = None
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                spm.main(["--dir", self.dir] + list(argv), org=self.org)
        except SystemExit as stop:
            code = stop.code
        said = out.getvalue() + err.getvalue() + ("" if code in (None, 0) else str(code))
        return said, code

    def ok(self, *argv):
        said, code = self.run_tool(*argv)
        self.assertIn(code, (None, 0), said)
        return said

    def refused(self, *argv):
        said, code = self.run_tool(*argv)
        self.assertNotIn(code, (None, 0), f"the run should end non-zero; it said:\n{said}")
        return said

    def ledger_text(self):
        path = os.path.join(self.dir, "ledger.csv")
        self.assertTrue(os.path.exists(path), "no ledger.csv after a write")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        with open(path, encoding="utf-8") as fh:
            return fh.read().splitlines()

    def ledger_row(self, batch_id):
        rows = [line for line in self.ledger_text()[1:] if batch_id in line]
        self.assertTrue(rows, f"the ledger has no row for {batch_id}")
        return rows[-1]

    def assert_ledger_row(self, batch_id, partner, day, *counts):
        """The batch's last ledger row names the partner, the batch date (YYYY-MM-DD), the month
        (YYYY-MM or YYYYMM, apart from the date) and each of `counts`."""
        row = self.ledger_row(batch_id)
        self.assertIn(partner, row)
        self.assertIn(day, row)
        month, compact = day[:7], day[:4] + day[5:7]
        self.assertRegex(row, rf"(?<![\d-]){month}(?![\d-])|(?<!\d){compact}(?!\d)", f"no month column in: {row}")
        for n in counts:
            self.assertTrue(self.has_number(row, n), f"{n} missing from the ledger row: {row}")
        return row

    def line_of(self, said, partner):
        lines = [line for line in said.splitlines() if partner in line]
        self.assertTrue(lines, f"no line names {partner}:\n{said}")
        return " | ".join(lines)

    def has_number(self, text, n):
        return re.search(rf"(?<![\d.]){n}(?:\.0)?(?![\d])", text) is not None

    def assert_nothing_written(self):
        self.assertEqual((self.org.inserts, self.org.updates), ([], []))
        self.assertFalse(os.path.exists(os.path.join(self.dir, "ledger.csv")), "a dry run wrote a ledger")

    def assert_private(self, said):
        self.assertNotIn(GIRL, said)
        for soql in self.org.seen:
            for word in ("Contact_IDs__c", "Status_Message__c", "Notes__c", "Description", "FIELDS("):
                self.assertNotIn(word.lower(), soql.lower(), f"the tool selected {word}: {soql}")


class DryRun(Harness):
    def test_the_dry_run_plans_one_batch_per_partner_with_its_monthly_max_and_writes_nothing(self):
        cases = [(2026, 9, (137, 262, 389)), (2026, 8, (58, 171, 244)), (2025, 12, (306, 77, 129)), (2026, 2, (95, 418, 203))]
        for year, month, totals in cases:
            with self.subTest(month=tag(year, month)):
                self.fresh().month(year, month, totals)
                said = self.ok("--month", tag(year, month), "--vpn-off")
                for partner, total in zip(PARTNERS, totals):
                    self.assertTrue(self.has_number(self.line_of(said, partner), total),
                                    f"{partner}'s line lacks its Monthly Max {total}:\n{said}")
                for noise in (901, 902, 903, 911, 912, 913, 977, 988):
                    self.assertFalse(self.has_number(said, noise), f"{noise} is another month's or account's count:\n{said}")
                self.assertNotIn(OTHER_PARTNER, said)
                self.assertNotIn(LOOKALIKE, said)
                self.assert_nothing_written()
                self.assert_private(said)

    def test_the_dry_run_prints_partner_names_and_counts_but_no_record_ids(self):
        self.org.month(2026, 9, (137, 262, 389))
        old = self.org.batch(self.org.acc[TLM], "2026-09-30", 250)
        said = self.ok("--month", "2026-09", "--vpn-off")
        for record_id in [r["Id"] for r in self.org.reports] + list(self.org.acc.values()) + [old["Id"]]:
            self.assertNotIn(record_id, said)
        self.assert_nothing_written()

    def test_the_default_month_is_last_month(self):
        today, utc = datetime.date.today(), datetime.datetime.now(datetime.timezone.utc).date()
        candidates = {last_month(today), last_month(utc)}
        totals = {}
        for i, (year, month) in enumerate(sorted(candidates)):
            totals[(year, month)] = (141 + i, 263 + i, 352 + i)
            self.org.month(year, month, totals[(year, month)])
        this_month = (today.year, today.month)
        if this_month not in candidates:
            for partner, total in zip(PARTNERS, (931, 932, 933)):
                self.org.report(partner, *this_month, total)
        said = self.ok("--vpn-off")
        self.assertTrue(any(all(self.has_number(self.line_of(said, p), t) for p, t in zip(PARTNERS, ts))
                            for ts in totals.values()), f"not last month's Monthly Max:\n{said}")
        for noise in (931, 932, 933):
            self.assertFalse(self.has_number(said, noise), said)
        self.assert_nothing_written()

    def test_a_dry_run_without_vpn_off_refuses_before_salesforce_is_asked(self):
        self.org.month(2026, 9, (137, 262, 389))
        for argv in (("--month", "2026-09"), ()):
            with self.subTest(argv=argv):
                said = self.refused(*argv)
                self.assertIn("VPN", said)
                self.assertEqual(self.org.seen, [])
                self.assert_nothing_written()

    def test_the_current_month_or_a_later_one_is_refused_before_salesforce_is_asked(self):
        today, utc = datetime.date.today(), datetime.datetime.now(datetime.timezone.utc).date()
        year, month = max((today.year, today.month), (utc.year, utc.month))   # current for either clock
        nxt = (year + (month == 12), month % 12 + 1)
        for y, m in ((year, month), nxt, (year + 1, month), (year + 3, 1)):
            with self.subTest(month=tag(y, m)):
                self.org.month(y, m, (137, 262, 389))
                self.org.seen.clear()
                said = self.refused("--month", tag(y, m), "--vpn-off")
                self.assertEqual(self.org.seen, [], said)
                self.refused("--month", tag(y, m), "--apply", "--vpn-off")
                self.assertEqual(self.org.seen, [])
                self.assert_nothing_written()
        prev = last_month(min(today, utc))                 # last month for either clock: allowed
        self.fresh().month(*prev, (141, 263, 352))
        said = self.ok("--month", tag(*prev), "--vpn-off")
        self.assertTrue(self.has_number(self.line_of(said, TLM), 263), said)

    def test_a_month_that_is_not_yyyy_mm_is_refused_before_salesforce_is_asked(self):
        self.org.month(2026, 9, (137, 262, 389))
        for bad in ("2026-13", "2026-00", "2026-9", "202609", "09-2026", "September", "2026-09-30", ""):
            with self.subTest(month=bad):
                self.org.seen.clear()
                self.refused("--month", bad, "--vpn-off")
                self.assertEqual(self.org.seen, [])
                self.assert_nothing_written()


BAD_VALUES = {"blank": None, "zero": 0.0, "fraction": 137.5, "negative": -137.0, "negative fraction": -0.5}
KINDS = ["none", "two"] + list(BAD_VALUES)


class Refusals(Harness):
    """A partner without exactly one Monthly Report, or with a Monthly Max that is blank, 0, negative or
    not a whole number, is refused and reported; the others are planned; the run ends non-zero."""

    def setup_refusal(self, kind, refused_index):
        org = self.fresh()
        totals = [137, 262, 389]
        partner = PARTNERS[refused_index]
        if kind == "none":
            totals[refused_index] = None
        org.month(2026, 9, totals)
        if kind == "two":
            org.report(partner, 2026, 9, 455)
        if kind in BAD_VALUES:
            report = next(r for r in org.reports if r["Account__r"]["Name"] == partner and r["YearMonth__c"] == 202609.0)
            report["Monthly_Total__c"] = BAD_VALUES[kind]
        return partner, totals

    def test_each_refusal_reports_the_partner_plans_the_others_and_ends_non_zero(self):
        for kind in KINDS:
            for index in range(3):
                with self.subTest(kind=kind, partner=PARTNERS[index]):
                    partner, totals = self.setup_refusal(kind, index)
                    said = self.refused("--month", "2026-09", "--vpn-off")
                    self.assertIn(partner, said)
                    for other, total in zip(PARTNERS, totals):
                        if other != partner:
                            self.assertTrue(self.has_number(self.line_of(said, other), total), said)
                    self.assert_nothing_written()
                    self.assert_private(said)

    def test_a_refused_partner_gets_no_batch_even_with_apply(self):
        for kind in KINDS:
            for index in range(3):
                with self.subTest(kind=kind, partner=PARTNERS[index]):
                    partner, totals = self.setup_refusal(kind, index)
                    said = self.refused("--month", "2026-09", "--apply", "--vpn-off")
                    self.assertIn(partner, said)
                    self.assertEqual([b for b in self.org.inserts if b.get("Account_Name__c") == partner], [])
                    self.assertEqual(self.org.partner_batches(partner, "2026-09-30"), [])
                    self.assertEqual(self.org.updates, [])
                    # each partner is independent: the other two are written and read back
                    others = {p: t for p, t in zip(PARTNERS, totals) if p != partner}
                    self.assertEqual(sorted((b["Account_Name__c"], b["Girls_Present__c"]) for b in self.org.inserts),
                                     sorted(others.items()))
                    for other, total in others.items():
                        made = self.org.partner_batches(other, "2026-09-30")
                        self.assertEqual([(b["Processing_Status__c"], b["Girls_Present__c"]) for b in made], [("Success", total)])
                        self.assertIn(made[0]["Id"], "\n".join(self.ledger_text()))

    def test_two_existing_partner_report_batches_on_the_day_refuse_that_partner_only(self):
        for index in range(3):
            partner = PARTNERS[index]
            with self.subTest(partner=partner):
                org = self.fresh()
                totals = (137, 262, 389)
                org.month(2026, 9, totals)
                org.batch(org.acc[partner], "2026-09-30", 120 + index)
                org.batch(org.acc[partner], "2026-09-30", 140 + index)
                said = self.refused("--month", "2026-09", "--vpn-off")
                self.assertIn(partner, said)
                for other, total in zip(PARTNERS, totals):
                    if other != partner:
                        self.assertTrue(self.has_number(self.line_of(said, other), total), said)
                self.assert_nothing_written()
                said = self.refused("--month", "2026-09", "--apply", "--vpn-off")
                self.assertIn(partner, said)
                self.assertEqual(org.updates, [])
                self.assertEqual(sorted(b["Account_Name__c"] for b in org.inserts), sorted(p for p in PARTNERS if p != partner))
                self.assertEqual(len(org.partner_batches(partner, "2026-09-30")), 2)

    def assert_refused_alone(self, partner, totals=(137, 262, 389)):
        """With --apply: `partner` refused and named, nothing written for it, the other two inserted with
        their counts, the run non-zero."""
        org = self.org
        said = self.refused("--month", "2026-09", "--apply", "--vpn-off")
        self.assertIn(partner, said)
        self.assertEqual([b for b in org.inserts if str(b.get("Account_Name__c")).casefold() == partner.casefold()], [])
        self.assertEqual(org.updates, [])
        self.assertEqual(sorted((b["Account_Name__c"], b["Girls_Present__c"]) for b in org.inserts),
                         sorted((p, t) for p, t in zip(PARTNERS, totals) if p != partner))
        self.assert_private(said)
        return said

    def test_a_partner_whose_name_no_single_account_carries_exactly_is_refused(self):
        """The processor matches Account_Name__c against every Account ignoring case: the partner's
        Account missing, a second Account differing only in capitals, or the partner's Account in other
        capitals make the batch's account a guess."""
        for partner in PARTNERS:
            for case in ("missing", "a second in capitals", "stored in other capitals"):
                with self.subTest(partner=partner, case=case):
                    org = self.fresh()
                    org.month(2026, 9, (137, 262, 389))
                    mine = next(a for a in org.accounts if a["Id"] == org.acc[partner])
                    if case == "missing":
                        org.accounts.remove(mine)
                    elif case == "a second in capitals":
                        org.accounts.append({"Id": fresh_id("001"), "Name": partner.upper(), "Description": ""})
                    else:
                        mine["Name"] = partner.lower()
                    said = self.refused("--month", "2026-09", "--vpn-off")         # the dry run: the others planned
                    self.assertIn(partner, said)
                    for other, total in zip(PARTNERS, (137, 262, 389)):
                        if other != partner:
                            self.assertTrue(self.has_number(self.line_of(said, other), total), said)
                    self.assert_nothing_written()
                    self.assert_refused_alone(partner)

    def test_another_success_batch_on_the_partners_day_refuses_an_insert(self):
        """A partner that needs an insert, whose account and day already hold a Success batch of another
        creator, is refused before sending: the processor would answer Failed 'Duplicate'. A Failed one
        on the day, or a Success one on another day, does not refuse."""
        for index, partner in enumerate(PARTNERS):
            for creator in ("Jotform", "Jotform back-fill 5001", "Manual entry"):
                with self.subTest(partner=partner, creator=creator):
                    org = self.fresh()
                    org.month(2026, 9, (137, 262, 389))
                    org.batch(org.acc[partner], "2026-09-30", 17 + index, creator=creator, names=GIRL)
                    said = self.refused("--month", "2026-09", "--vpn-off")
                    self.assertIn(partner, said)
                    self.assert_nothing_written()
                    self.assert_refused_alone(partner)
        for index, partner in enumerate(PARTNERS):
            with self.subTest(partner=partner, case="Failed on the day, Success the day before"):
                org = self.fresh()
                org.month(2026, 9, (137, 262, 389))
                org.batch(org.acc[partner], "2026-09-30", None, creator="Jotform", status="Failed", names=GIRL)
                org.batch(org.acc[partner], "2026-09-29", 17 + index, creator="Jotform", names=GIRL)
                self.ok("--month", "2026-09", "--apply", "--vpn-off")
                self.assertEqual(sorted((b["Account_Name__c"], b["Girls_Present__c"]) for b in org.inserts),
                                 sorted(zip(PARTNERS, (137, 262, 389))))

    def test_two_reports_refuse_even_when_an_existing_batch_matches_one_of_them(self):
        self.org.month(2026, 9, (137, 262, 389))
        self.org.report(NGAA, 2026, 9, 455)
        self.org.batch(self.org.acc[NGAA], "2026-09-30", 389)
        said = self.refused("--month", "2026-09", "--apply", "--vpn-off")
        self.assertIn(NGAA, said)
        self.assertEqual([u for u in self.org.updates], [])
        self.assertEqual([b for b in self.org.inserts if b.get("Account_Name__c") == NGAA], [])


class ExistingBatches(Harness):
    def test_an_unchanged_count_is_skipped_and_a_different_one_is_planned_as_an_update_old_to_new(self):
        self.org.month(2026, 9, (137, 262, 389))
        self.org.batch(self.org.acc[EEFY], "2026-09-30", 137)                 # unchanged: skip
        self.org.batch(self.org.acc[TLM], "2026-09-30", 250)                  # was 250, now 262: update
        self.org.batch(self.org.acc[TLM], "2026-08-31", 262)                  # last month's: not this month's batch
        self.org.batch(self.org.club_id, "2026-09-30", 389)                   # a club's typed count on the day: not Ng'aa's
        self.org.batch(self.org.acc[NGAA], "2026-09-30", None, creator="Jotform", status="Failed", names=GIRL)  # not a Partner report
        said = self.ok("--month", "2026-09", "--vpn-off")
        self.assertRegex(self.line_of(said, EEFY).lower(), r"skip|unchanged|already|up to date|nothing to do")
        tlm = self.line_of(said, TLM)
        self.assertRegex(tlm, r"(?<![\d.])250(?:\.0)?\D+262(?![\d])", f"no old -> new on {TLM}'s line:\n{said}")
        self.assertTrue(self.has_number(self.line_of(said, NGAA), 389), said)
        self.assert_nothing_written()
        self.assert_private(said)

    def test_apply_inserts_the_new_updates_the_changed_and_leaves_the_unchanged(self):
        org = self.org
        org.month(2026, 9, (137, 262, 389))
        same = org.batch(org.acc[EEFY], "2026-09-30", 137)
        changed = org.batch(org.acc[TLM], "2026-09-30", 250)
        org.batch(org.acc[NGAA], "2026-08-31", 389)                      # last month's Partner report: not this month's
        said = self.ok("--month", "2026-09", "--apply", "--vpn-off")
        self.assertEqual(org.updates, [("Attendance_Batch__c", changed["Id"], {"Girls_Present__c": 262})])
        self.assertEqual([b["Account_Name__c"] for b in org.inserts], [NGAA])
        self.assertEqual(changed["Girls_Present__c"], 262)
        self.assertEqual(same["Girls_Present__c"], 137.0)
        new = org.partner_batches(NGAA, "2026-09-30")
        self.assertEqual(len(new), 1)
        self.assertRegex(self.assert_ledger_row(new[0]["Id"], NGAA, "2026-09-30", 389).lower(), r"insert|creat")
        self.assertRegex(self.assert_ledger_row(changed["Id"], TLM, "2026-09-30", 250, 262).lower(), r"updat")
        self.assert_private(said)

    def test_only_a_partner_report_batch_on_the_partner_and_day_is_compared(self):
        """A Jotform batch on the partner's account and day, or another account's Partner report on the
        day, sits beside the one Partner report batch: no refusal, that one is the one compared."""
        org = self.org
        org.month(2026, 9, (137, 262, 389))
        org.batch(org.acc[EEFY], "2026-09-30", 137)                                   # in place
        org.batch(org.acc[EEFY], "2026-09-30", 21, creator="Jotform", names=GIRL)     # a Jotform batch beside it
        changed = org.batch(org.acc[TLM], "2026-09-30", 250)                          # to update
        jotform = org.batch(org.acc[TLM], "2026-09-30", 33, creator="Jotform back-fill 5001", names=GIRL)
        org.batch(org.club_id, "2026-09-30", 44)                                      # a club's Partner report
        org.batch(org.acc[NGAA], "2026-09-30", None, creator="Jotform", status="Failed", names=GIRL)   # no Partner report
        said = self.ok("--month", "2026-09", "--vpn-off")
        self.assertRegex(self.line_of(said, EEFY).lower(), r"skip|unchanged|already|up to date|nothing to do")
        self.assertRegex(self.line_of(said, TLM), r"(?<![\d.])250(?:\.0)?\D+262(?![\d])", said)
        self.assertTrue(self.has_number(self.line_of(said, NGAA), 389), said)
        self.assert_nothing_written()
        said = self.ok("--month", "2026-09", "--apply", "--vpn-off")
        self.assertEqual(org.updates, [("Attendance_Batch__c", changed["Id"], {"Girls_Present__c": 262})])
        self.assertEqual(jotform["Girls_Present__c"], 33.0)
        self.assertEqual([(b["Account_Name__c"], b["Girls_Present__c"]) for b in org.inserts], [(NGAA, 389)])
        self.assert_private(said)

    def test_a_failed_partner_report_batch_is_not_an_existing_one(self):
        org = self.org
        org.month(2026, 9, (137, 262, 389))
        org.batch(org.acc[NGAA], "2026-09-30", None, status="Failed")                # a Failed one, count blank
        org.batch(org.acc[TLM], "2026-09-30", 262)                                   # in place ...
        org.batch(org.acc[TLM], "2026-09-30", None, status="Failed")                 # ... beside a Failed one: not two
        said = self.ok("--month", "2026-09", "--vpn-off")
        self.assertTrue(self.has_number(self.line_of(said, NGAA), 389), said)
        self.assertRegex(self.line_of(said, TLM).lower(), r"skip|unchanged|already|up to date|nothing to do")
        self.assert_nothing_written()
        self.ok("--month", "2026-09", "--apply", "--vpn-off")
        self.assertEqual(org.updates, [])
        self.assertEqual(sorted((b["Account_Name__c"], b["Girls_Present__c"]) for b in org.inserts),
                         sorted([(EEFY, 137), (NGAA, 389)]))
        self.assertEqual(sorted((b["Processing_Status__c"], b["Girls_Present__c"]) for b in org.partner_batches(NGAA, "2026-09-30")),
                         sorted([("Failed", None), ("Success", 389)]))

    def test_a_second_run_after_apply_finds_everything_in_place(self):
        self.org.month(2026, 9, (137, 262, 389))
        self.ok("--month", "2026-09", "--apply", "--vpn-off")
        self.assertEqual(len(self.org.inserts), 3)
        said = self.ok("--month", "2026-09", "--apply", "--vpn-off")
        self.assertEqual((len(self.org.inserts), self.org.updates), (3, []))
        for partner in PARTNERS:
            self.assertRegex(self.line_of(said, partner).lower(), r"skip|unchanged|already|up to date|nothing to do")
            self.assertEqual(len(self.org.partner_batches(partner, "2026-09-30")), 1)


class Apply(Harness):
    def test_apply_writes_one_batch_per_partner_dated_the_months_last_day(self):
        cases = [("2026-09", "2026-09-30", (137, 262, 389)), ("2026-08", "2026-08-31", (58, 171, 244)),
                 ("2026-02", "2026-02-28", (95, 418, 203)), ("2024-02", "2024-02-29", (66, 133, 199)),
                 ("2025-12", "2025-12-31", (306, 77, 129)), ("2026-01", "2026-01-31", (412, 38, 275)),
                 ("2026-04", "2026-04-30", (19, 520, 147))]
        for month, last_day, totals in cases:
            with self.subTest(month=month):
                year, mon = int(month[:4]), int(month[5:])
                self.assertEqual(end_of(year, mon), last_day)
                org = self.fresh()
                org.month(year, mon, totals)
                said = self.ok("--month", month, "--apply", "--vpn-off")
                self.assertEqual(org.updates, [])
                self.assertEqual(len(org.inserts), 3, said)
                by_name = {b.get("Account_Name__c"): b for b in org.inserts}
                self.assertEqual(sorted(by_name), sorted(PARTNERS))
                for partner, total in zip(PARTNERS, totals):
                    body = by_name[partner]
                    self.assertEqual(body["Attendance_Date__c"], last_day)
                    self.assertEqual(body["Girls_Present__c"], total)
                    self.assertNotIsInstance(body["Girls_Present__c"], bool)
                    self.assertEqual(body["Creator__c"], REPORT)
                    self.assertIn(body.get("Contact_IDs__c", ""), ("", None))
                    self.assertIs(body.get("enable_fuzzy_matching__c"), False)
                    made = org.partner_batches(partner, last_day)
                    self.assertEqual([(b["Processing_Status__c"], b["Girls_Present__c"]) for b in made], [("Success", total)])
                    row = self.assert_ledger_row(made[0]["Id"], partner, last_day, total)
                    self.assertRegex(row.lower(), r"insert|creat")
                for line in self.ledger_text()[1:]:                    # every row: a partner, the date, the month
                    self.assertTrue(any(p in line for p in PARTNERS), line)
                    self.assertIn(last_day, line)
                self.assertFalse(any(a["Id"].startswith("001STRAY") for a in org.accounts), "a stray account was made")
                self.assert_private(said)

    def test_limit_counts_writes_only_in_the_fixed_partner_order(self):
        """Partners are taken in the order Education and English for You, Tumaini La Maisha, Ng'aa
        Maskani; a partner skipped (already in place) or refused does not use up --limit."""
        def written(org):
            return [b["Account_Name__c"] for b in org.inserts] + \
                [next(b["Account_Name__c"] for b in org.batches if b["Id"] == u[1]) for u in org.updates]
        cases = [
            ("nothing in place", {}, "1", [EEFY]),
            ("the first in place", {EEFY: 137}, "1", [TLM]),
            ("the first two in place", {EEFY: 137, TLM: 262}, "1", [NGAA]),
            ("the first in place, two allowed", {EEFY: 137}, "2", [TLM, NGAA]),
            ("the first changed", {EEFY: 120}, "1", [EEFY]),
            ("the first in place, the second changed", {EEFY: 137, TLM: 250}, "1", [TLM]),
        ]
        for label, in_place, limit, expected in cases:
            with self.subTest(label):
                org = self.fresh()
                org.month(2026, 9, (137, 262, 389))
                for partner, count in in_place.items():
                    org.batch(org.acc[partner], "2026-09-30", count)
                self.ok("--month", "2026-09", "--apply", "--vpn-off", "--limit", limit)
                self.assertEqual(written(org), expected)
        org = self.fresh()                                  # a refused first partner does not use it up either
        org.month(2026, 9, (None, 262, 389))
        self.refused("--month", "2026-09", "--apply", "--vpn-off", "--limit", "1")
        self.assertEqual(written(org), [TLM])

    def test_apply_without_vpn_off_refuses_before_salesforce_is_asked(self):
        self.org.month(2026, 9, (137, 262, 389))
        said = self.refused("--month", "2026-09", "--apply")
        self.assertIn("VPN", said)
        self.assertEqual((self.org.seen, self.org.inserts, self.org.updates), ([], [], []))
        for short in ("--app", "--appl", "--a"):
            with self.subTest(flag=short):
                self.refused("--month", "2026-09", short, "--vpn-off")
                self.assertEqual((self.org.inserts, self.org.updates), ([], []))

    def test_a_read_back_that_does_not_match_is_reported_as_a_failure(self):
        mismatches = [{"Processing_Status__c": "Failed", "Girls_Present__c": None},   # the processor failed it
                      {"Account__c": "other partner"},                              # attached to another account
                      {"Girls_Present__c": 12.0}]                                    # another count
        for wrong, partner in zip(mismatches, PARTNERS):
            with self.subTest(wrong=wrong, partner=partner):
                org = self.fresh()
                org.month(2026, 9, (137, 262, 389))
                original = org.insert

                def insert(sobject, body, original=original, org=org, partner=partner, wrong=wrong):
                    if body.get("Account_Name__c") == partner:
                        org.processor = {k: org.other_id if v == "other partner" else v for k, v in wrong.items()}
                    return original(sobject, body)
                org.insert = insert
                said = self.refused("--month", "2026-09", "--apply", "--vpn-off")
                self.assertIn(partner, said)
                bad = [b for b in org.batches if b.get("Account_Name__c") == partner]
                self.assertEqual(len(bad), 1)
                self.assertTrue(os.path.exists(os.path.join(self.dir, "ledger.csv")))
                self.assertIn(bad[0]["Id"], "\n".join(self.ledger_text()))   # the rollback needs its id
                self.assert_private(said)

    def test_a_failed_write_or_a_bad_read_back_stops_the_run(self):
        """In the fixed order, the partner whose write fails (HTTP 400) or reads back wrong is the last
        one sent: no insert or update for the partners after it."""
        for index, partner in enumerate(PARTNERS):
            for fault in ("insert refused", "read back Failed", "update refused", "update drifts"):
                with self.subTest(partner=partner, fault=fault):
                    org = self.fresh()
                    org.month(2026, 9, (137, 262, 389))
                    if fault.startswith("update"):
                        for p in PARTNERS:                       # all three in place with an old count: three updates
                            org.batch(org.acc[p], "2026-09-30", 100)
                        target = org.partner_batches(partner, "2026-09-30")[0]["Id"]
                        original = org.update

                        def update(sobject, record_id, body, original=original, org=org, target=target, fault=fault):
                            if record_id == target:
                                org.refuse_update = fault == "update refused"
                                org.drift_update = fault == "update drifts"
                            return original(sobject, record_id, body)
                        org.update = update
                    elif fault == "insert refused":
                        org.refuse_insert = partner
                    else:
                        original = org.insert

                        def insert(sobject, body, original=original, org=org, partner=partner):
                            if body.get("Account_Name__c") == partner:
                                org.processor = {"Processing_Status__c": "Failed", "Girls_Present__c": None}
                            return original(sobject, body)
                        org.insert = insert
                    said = self.refused("--month", "2026-09", "--apply", "--vpn-off")
                    self.assertIn(partner, said)
                    sent = [b["Account_Name__c"] for b in org.inserts] + \
                        [next(b["Account_Name__c"] for b in org.batches if b["Id"] == u[1]) for u in org.updates]
                    self.assertEqual(sent, list(PARTNERS[:index + 1]), f"sent after the failure:\n{said}")

    def test_an_update_that_does_not_read_back_is_reported_as_a_failure(self):
        self.org.month(2026, 9, (137, 262, 389))
        changed = self.org.batch(self.org.acc[TLM], "2026-09-30", 250)
        self.org.batch(self.org.acc[EEFY], "2026-09-30", 137)
        self.org.batch(self.org.acc[NGAA], "2026-09-30", 389)
        self.org.drift_update = True
        said = self.refused("--month", "2026-09", "--apply", "--vpn-off")
        self.assertIn(TLM, said)
        self.assertEqual(self.org.updates, [("Attendance_Batch__c", changed["Id"], {"Girls_Present__c": 262})])
        self.assert_ledger_row(changed["Id"], TLM, "2026-09-30", 250, 262)

    def test_salesforce_refusing_a_write_ends_non_zero(self):
        self.org.month(2026, 9, (137, 262, 389))
        self.org.refuse_insert = True
        said = self.refused("--month", "2026-09", "--apply", "--vpn-off")
        self.assertTrue(any(p in said for p in PARTNERS), said)
        self.assertEqual(self.org.batches, [])
        self.fresh().month(2026, 9, (137, 262, 389))
        self.org.batch(self.org.acc[TLM], "2026-09-30", 250)
        self.org.batch(self.org.acc[EEFY], "2026-09-30", 137)
        self.org.batch(self.org.acc[NGAA], "2026-09-30", 389)
        self.org.refuse_update = True
        said = self.refused("--month", "2026-09", "--apply", "--vpn-off")
        self.assertIn(TLM, said)


class Folders(Harness):
    def test_the_ledger_lives_under_data_and_a_folder_elsewhere_in_the_checkout_is_refused(self):
        self.assertEqual(os.path.dirname(os.path.abspath(spm.DEFAULT_DIR)), os.path.join(REPO, "data"))
        self.org.month(2026, 9, (137, 262, 389))
        out = io.StringIO()
        with self.assertRaises(SystemExit) as stop, contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(io.StringIO()):
            spm.main(["--dir", os.path.join(REPO, "docs"), "--month", "2026-09", "--apply", "--vpn-off"], org=self.org)
        self.assertNotIn(stop.exception.code, (None, 0))
        self.assertEqual((self.org.inserts, self.org.updates), ([], []))

    def test_help_exits_zero(self):
        with self.assertRaises(SystemExit) as stop, contextlib.redirect_stdout(io.StringIO()):
            spm.main(["--help"])
        self.assertEqual(stop.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
