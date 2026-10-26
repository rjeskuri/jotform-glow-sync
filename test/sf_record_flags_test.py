#!/usr/bin/env python3
"""
Offline tests for tools/sf_record_flags.py (ticket #85): the read-only step that works out, from the
Google Sheet and Salesforce, what Batch Apex cannot read, and writes the anonymous Apex that runs
RecordFlagBatch (Ryan, 2026-10-23: decision 1a; the Contact workflow guard, option a). Written
before the tool exists: this file is its contract.

  - deactivated_club_ids(roster_csv, accounts, partners): the Account ids of the clubs deactivated in
    a Roster export, each matched to its Club account. A club is deactivated when none of its Roster
    rows is active, by the sync's own rule (glow.sync: a row is active when its status, spacing
    collapsed and capitals ignored, is `active`; Inactive, removed and blank are not; removed_date
    says nothing). Only the deactivated clubs are matched. The club's account is the Club account
    (RecordTypeId glow.salesforce.CLUB_RECORD_TYPE; a Household or other-type account of the name is
    neither the club's nor its twin) named as question 5 sends the club: `<club> - <partner>`
    (glow.sync.SF_NAME_SEP) when a Club account carries that name, else the plain name (RUNBOOK
    "Club names two partners share"; tools/sf_dupes.py club_for), compared as the processor compares
    question 5 (glow.salesforce.sf_match: Java's equalsIgnoreCase after a trim of the Roster's name;
    the Account's name untrimmed, so a double or trailing space is another name). Of two Club
    accounts of the name, the club's is the one under its partner's account (`partners`:
    glow/sf_partners.csv as glow.salesforce.read_partners gives it). A deactivated club with no
    account, or with twins the parent does not tell apart, is refused (glow.salesforce.Refused, or
    sys.exit from the command line) naming the club and what to fix - never guessed. `accounts` are
    plain Account records (Id, Name, RecordTypeId, ParentId). The result has no repeats.
  - partner_report_partner_ids(partners_csv, partners): the account ids (glow/sf_partners.csv as
    glow.salesforce.read_partners gives it) of the partners marked `no` in a Partners-tab export's
    `jotform` column, read as glow.sync.read_partners_csv reads it (columns by header name, capitals
    and spacing ignored, in any order, a byte-order mark ignored; `no` ignoring capitals and spacing;
    yes, blank or anything else is yes; a partner listed twice is `no` when any row says so). A
    marked partner missing from the map is refused; so is an export without the column (it would
    judge the three Salesforce-reporting partners' 38 clubs by batches they never have).
  - apex_script(sobject, mode, deactivated_ids=(), partner_ids=()): the anonymous Apex, one
    statement (comments allowed): for Account
      Database.executeBatch(new RecordFlagBatch('Account', '<mode>', new Set<Id>{'001…', …},
                            new Set<Id>{'001…', …}), 200);
    (the deactivated clubs' ids first, the jotform=no partners' ids second, each quoted; an empty
    set as `new Set<Id>{}` or `new Set<Id>()`) and for Contact the two-argument
      Database.executeBatch(new RecordFlagBatch('Contact', '<mode>'), 200);
    sobject is exactly Account or Contact and mode exactly dryRun, flag or clear: anything else is
    refused. Ids only: no club, partner or person's name reaches the script.
  - guard_counts(org): {"email": n, "phone": n, "volunteer": n} - the Contacts with a blank Email and
    a Work, Home or Alternate e-mail set (npe01__WorkEmail__c, npe01__HomeEmail__c,
    npe01__AlternateEmail__c); with a blank Phone and a Work, Home, Mobile or Other phone set
    (npe01__WorkPhone__c, HomePhone, MobilePhone, OtherPhone); and with
    GW_Volunteers__Volunteer_Last_Web_Signup_Date__c = TODAY. Each is one SOQL count (Org.count,
    `SELECT COUNT() FROM Contact WHERE …`): a Contact is counted once however many of the fields it
    has, and no record is read. (The NPSP rules Preferred_Email__c and Preferred_Phone__c rewrite
    Email or Phone on any edit of such a Contact, and the Volunteers rule mails:
    data/sf_record_flags_2026-10-23/before/.../Contact.workflow-meta.xml.)
  - main(argv, org=None, partners_path=glow.salesforce.PARTNERS): the command line
      --sobject Account --mode dryRun|flag|clear --roster <Roster export> --partners <Partners-tab
      export> --out <file> --vpn-off [--alias glow]
      --sobject Contact --mode dryRun|flag|clear --out <file> --vpn-off [--alias glow]
    Account reads the two exports and Salesforce and writes the four-argument script; --roster and
    --partners are its inputs: an Account run without either, and a Contact run given either, is
    refused naming the flag before anything is read; a Partners export without the `jotform`
    column, or a marked partner missing from the map, stops the Account run the same way. Contact
    runs the guard first and refuses to write anything while any count is not 0: the refusal names
    each count that is not 0 by its kind, with its number, and no kind whose count is 0 (the three
    counts may be printed before it). The output carries counts and
    record ids only: never a girl's name, and on the success path no club's or partner's name either
    (ids only, as Ryan decided for the script; a refusal names the club or partner to fix).
    --vpn-off is required before anything is read (glow.salesforce.add_vpn_flag / require_vpn_off,
    like the other sf tools).
    The household-naming guard (Ryan, 2026-10-26): NPSP's Automatic Household Naming would rename the
    partners' household Accounts on any Account update, so before every Account script - dryRun, flag
    and clear alike, each runs an update or precedes one - the tool runs one read-only SOQL count,
      SELECT COUNT() FROM npo02__Households_Settings__c WHERE npo02__Advanced_Household_Naming__c = true
    (Org.count; a hierarchy custom setting: the org default and any profile's or user's row) and
    prints it on a line that names household naming. It writes the script only when the count is 0;
    above 0 it refuses (sys.exit) naming the household-naming guard, and writes no script. A Contact
    run never reads the household settings and is not stopped by them.

Everything here is fictional: clubs, partners, girls (test/fixtures/make_fixture.py's pools) and
Salesforce ids are invented. A fake org answers the tool's SOQL with a small evaluator (SELECT …
FROM … WHERE … with AND, OR, NOT, parentheses, =, !=, <, >, <=, >=, IN, LIKE, null, true, false,
TODAY, quoted strings, numbers and dates); any other SOQL is a test failure that quotes the query.
The fake's records are reachable through SOQL alone.
"""
import contextlib
import csv
import datetime
import io
import os
import re
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import sf_record_flags as sfr            # noqa: E402  (red until tools/sf_record_flags.py exists)
from glow import salesforce              # noqa: E402
from glow.sync import PARTNER_COLS       # noqa: E402  (the Partners tab's columns: partner, region, notes, jotform)

CLUB, HOUSE, OTHER = salesforce.CLUB_RECORD_TYPE, salesforce.PARTNER_RECORD_TYPE, "012000000000000OTH"
P1, P2, P3, P4 = "001000000000000PAA", "001000000000000PBB", "001000000000000PCC", "001000000000000PDD"
SUN, SUN2, RIV, DAWN = "001000000000000SUN", "001000000000000SU2", "001000000000000RIV", "001000000000000DAW"
STA1, STA2, NIG = "001000000000000ST1", "001000000000000ST2", "001000000000000NIG"
HH1, OT1, CL1, CL3, STP = ("001000000000000HH1", "001000000000000OT1", "001000000000000CL1", "001000000000000CL3",
                           "001000000000000STP")
PARTNER_MAP = [("Example Partner", P1, "Example Partner Org"), ("Second Partner", P2, "Second Partner"),
               ("Third Partner", P3, "Third Partner Org"), ("Fourth Partner", P4, "Fourth Partner")]
MODES = ("dryRun", "flag", "clear")
ROSTER_COLS = ["girl_id", "partner", "club", "region", "full_name", "last_name", "status",
               "added_date", "removed_date", "source"]
# fictional girls (make_fixture.py's pools); no word of a name may ever reach the tool's output
GIRLS = [("Amara", "Fennwhistle"), ("Beatrice", "Marrowgate"), ("Chiara", "Ostrivane"),
         ("Dalia", "Thornquibble"), ("Esther", "Umberlash"), ("Zara", "Zibblewick")]
NAME_WORDS = sorted({w for pair in GIRLS for w in pair})
# the fixture's clubs and partners: ids only on the success path
CLUB_WORDS = ("Sunrise", "River Club", "Dawn Club", "Stars", "Night Owls", "Lost Club", "Example Partner",
              "Second Partner", "Third Partner", "Fourth Partner", "Partner Org", "Filler Org")
EMAILS = ("npe01__WorkEmail__c", "npe01__HomeEmail__c", "npe01__AlternateEmail__c")
PHONES = ("npe01__WorkPhone__c", "HomePhone", "MobilePhone", "OtherPhone")
SIGNUP = "GW_Volunteers__Volunteer_Last_Web_Signup_Date__c"
# NPSP's Households Settings (a hierarchy custom setting) and its Automatic Household Naming checkbox
HH_SETTINGS, NAMING = "npo02__Households_Settings__c", "npo02__Advanced_Household_Naming__c"
# a line or a refusal that names the household-naming guard
NAMING_GUARD = r"(?i)household[^\n]*naming|naming[^\n]*household"
# the guard's three kinds, as a refusal names them
KINDS = {"email": r"(?i)e-?mails?", "phone": r"(?i)phones?", "volunteer": r"(?i)volunteers?|sign-?ups?"}
SF_ID = re.compile(r"[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?")
SET_LITERAL = r"new\s+Set<Id>\s*(?:\{[^}]*\}|\(\s*\))"
ACCOUNT_CALL = re.compile(r"Database\.executeBatch\(\s*new\s+RecordFlagBatch\(\s*'Account'\s*,\s*'(\w+)'\s*,\s*"
                          rf"({SET_LITERAL})\s*,\s*({SET_LITERAL})\s*\)\s*,\s*200\s*\)\s*;")
CONTACT_CALL = re.compile(r"Database\.executeBatch\(\s*new\s+RecordFlagBatch\(\s*'Contact'\s*,\s*'(\w+)'\s*\)\s*,"
                          r"\s*200\s*\)\s*;")


def gid(code, n):
    """A fictional girl id, built here so no literal one sits in the file."""
    return "-".join((code, "ZQ", f"{n:03d}"))


def cid(n):
    return f"003{n:015d}"


def today():
    return datetime.date.today()


def ids_in(set_literal):
    return re.findall(r"'([A-Za-z0-9]{15,18})'", set_literal)


def without_comments(apex):
    return re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", apex, flags=re.S))


def names_field(soql, field):
    """The field named in the SOQL as a word of its own (`Email` is not the one inside `npe01__HomeEmail__c`)."""
    return re.search(rf"(?<!\w){re.escape(field)}(?!\w)", soql) is not None


def acct(i, name, rt=CLUB, parent=None):
    return {"Id": i, "Name": name, "RecordTypeId": rt, "ParentId": parent, "Description": None}


def fillers(n=410):
    return [acct(f"001F{i:014d}", f"Filler Org {i}", OTHER) for i in range(n)]


def base_accounts():
    return fillers() + [acct(P1, "Example Partner Org", HOUSE), acct(P2, "Second Partner", HOUSE),
                        acct(P3, "Third Partner Org", HOUSE), acct(P4, "Fourth Partner", HOUSE),
                        acct(SUN, "Sunrise Club", CLUB, P1), acct(RIV, "River Club", CLUB, P2),
                        acct(DAWN, "Dawn Club", CLUB, P1), acct(STA1, "Stars - Example Partner", CLUB, P1),
                        acct(STA2, "Stars - Second Partner", CLUB, P2), acct(NIG, "Night Owls", CLUB, P2)]


def but(accounts, account_id, **changes):
    """The accounts with one of them changed (its Name, say)."""
    return [dict(a, **changes) if a["Id"] == account_id else a for a in accounts]


def contact(n, **fields):
    """A Contact as today's girls are stored: blank Email and Phone, no other e-mail or phone, no signup."""
    first, last = GIRLS[n % len(GIRLS)]
    base = {"Id": cid(n), "FirstName": first, "LastName": last, "Name": f"{first} {last}",
            "Contact_Role__c": "Participant", "AccountId": SUN, "Email": None, "Phone": None, SIGNUP: None}
    base.update({f: None for f in EMAILS + PHONES})
    base.update(fields)
    return base


def naming_setting(n, on):
    """A Households Settings record (the org default's, or a profile's or a user's: a hierarchy custom setting
    has one row per level) with Automatic Household Naming on or off."""
    return {"Id": f"a0H{n:015d}", "SetupOwnerId": f"00D{n:015d}", NAMING: on}


def says_naming_count(text, n):
    """A line of `text` names household naming and carries the number n as a word of its own."""
    return any(re.search(NAMING_GUARD, line) and re.search(rf"\b{n}\b", line) for line in text.splitlines())


# ---- a fake Salesforce: the tool's SOQL evaluated over fixture records ---------------------------
TOKEN = re.compile(r"\s*(?:('(?:[^'\\]|\\.)*')|([(),])|(!=|<>|<=|>=|=|<|>)|"
                   r"(\d{4}-\d\d-\d\d(?:T[\d:.]+(?:Z|[+-]\d\d:?\d\d))?)|(-?\d+(?:\.\d+)?)|([A-Za-z_][\w.:]*))")
HEAD = re.compile(r"SELECT\s+(.+?)\s+FROM\s+(\w+)(?:\s+WHERE\s+(.+?))?(?:\s+ORDER\s+BY\s+(.+?))?"
                  r"(?:\s+LIMIT\s+(\d+))?\s*$", re.S | re.I)
COUNT = re.compile(r"SELECT\s+COUNT\(\)\s+FROM\s+(\w+)(?:\s+WHERE\s+(.+?))?\s*$", re.S | re.I)


def tokens(text):
    out, pos, text = [], 0, text.strip()
    while pos < len(text):
        m = TOKEN.match(text, pos)
        assert m and m.end() > pos, f"unreadable SOQL near {text[pos:pos + 40]!r}"
        pos = m.end()
        s, punct, op, date, num, word = m.groups()
        if s is not None:
            out.append(("str", re.sub(r"\\(.)", r"\1", s[1:-1])))
        elif punct:
            out.append(("p", punct))
        elif op:
            out.append(("op", op))
        elif date:
            out.append(("lit", date))
        elif num:
            out.append(("lit", float(num) if "." in num else int(num)))
        else:
            out.append(("w", word))
    return out


class Where:
    """WHERE … parsed into (and|or|not|cmp|in|like, …) nodes."""

    def __init__(self, text):
        self.t, self.i = tokens(text), 0
        self.tree = self.expr()
        assert self.i == len(self.t), f"unsupported SOQL after {self.t[self.i:]!r} in {text!r}"

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def word_is(self, *words):
        k, v = self.peek()
        return k == "w" and v.upper() in words

    def take(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def expr(self):
        left = self.term()
        while self.word_is("OR"):
            self.take()
            left = ("or", left, self.term())
        return left

    def term(self):
        left = self.factor()
        while self.word_is("AND"):
            self.take()
            left = ("and", left, self.factor())
        return left

    def factor(self):
        if self.word_is("NOT"):
            self.take()
            return ("not", self.factor())
        k, v = self.take()
        if (k, v) == ("p", "("):
            inner = self.expr()
            assert self.take() == ("p", ")"), "a bracket is not closed"
            return inner
        assert k == "w", f"a field name expected, got {v!r}"
        negate = False
        if self.word_is("NOT"):
            self.take()
            negate = True
        if self.word_is("IN"):
            self.take()
            node = ("in", v, self.values())
        elif self.word_is("LIKE"):
            self.take()
            k2, pattern = self.take()
            assert k2 == "str", "LIKE takes a quoted pattern"
            node = ("like", v, pattern)
        else:
            assert not negate, "NOT before an operator"
            k2, op = self.take()
            assert k2 == "op", f"an operator expected after {v}, got {op!r}"
            node = ("cmp", v, op, self.value())
        return ("not", node) if negate else node

    def values(self):
        assert self.take() == ("p", "("), "IN takes a bracketed list"
        out = []
        while True:
            out.append(self.value())
            k, v = self.take()
            if v == ")":
                return out
            assert v == ",", f"a comma expected in an IN list, got {v!r}"

    def value(self):
        k, v = self.take()
        if k in ("str", "lit"):
            return v
        assert k == "w", f"a literal expected, got {v!r}"
        named = {"NULL": None, "TRUE": True, "FALSE": False, "TODAY": today().isoformat(),
                 "YESTERDAY": (today() - datetime.timedelta(days=1)).isoformat(),
                 "TOMORROW": (today() + datetime.timedelta(days=1)).isoformat()}
        assert v.upper() in named, f"unsupported SOQL literal {v!r}"
        return named[v.upper()]


def field_value(rec, path):
    cur = rec
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def same(have, want):
    if have is None or want is None:
        return have is None and want is None
    if isinstance(have, str) and isinstance(want, str):
        if len(want) == 10 and len(have) > 10:       # a date literal against a datetime value
            have = have[:10]
        return have.casefold() == want.casefold()
    return have == want


def holds(node, rec):
    kind = node[0]
    if kind == "and":
        return holds(node[1], rec) and holds(node[2], rec)
    if kind == "or":
        return holds(node[1], rec) or holds(node[2], rec)
    if kind == "not":
        return not holds(node[1], rec)
    have = field_value(rec, node[1])
    if have == "":
        have = None                                    # Salesforce stores a blank as null, and '' means null
    if kind == "in":
        return any(same(have, None if v == "" else v) for v in node[2])
    if kind == "like":
        rx = "".join(".*" if c == "%" else "." if c == "_" else re.escape(c) for c in node[2])
        return have is not None and re.fullmatch(rx, str(have), re.I) is not None
    _, _, op, want = node
    if want == "":
        want = None
    if op in ("=", "!=", "<>"):
        return same(have, want) if op == "=" else not same(have, want)
    if have is None or want is None:
        return False
    return {"<": have < want, ">": have > want, "<=": have <= want, ">=": have >= want}[op]


class FakeOrg:
    """Salesforce as far as the tool can read it: Accounts, Contacts and NPSP's Households Settings, reachable
    through SOQL alone (the records live in a closure: no attribute of the org holds them). Read-only: a write
    fails. `settings` defaults to production's own (2026-10-26): the org default alone, naming off."""
    alias = "fake"

    def __init__(self, accounts=(), contacts=(), settings=None):
        settings = [naming_setting(0, False)] if settings is None else settings
        tables = {"Account": [dict(a) for a in accounts], "Contact": [dict(c) for c in contacts],
                  HH_SETTINGS: [dict(s) for s in settings]}
        self.queries, self.token, self.revoked = [], "t", False

        def rows(obj, where):
            table = tables.get(obj)
            assert table is not None, f"the tool queried {obj}, which the fake org does not hold"
            tree = Where(where).tree if where else None
            return [r for r in table if tree is None or holds(tree, r)]

        def query(soql):
            self.queries.append(soql)
            m = HEAD.fullmatch(soql.strip())
            assert m, f"unsupported SOQL: {soql!r}"
            fields, obj, where, _order, limit = m.groups()
            names = [f.strip() for f in fields.split(",")]
            if names == ["COUNT()"]:
                return []                              # as the REST API answers: records [], totalSize apart
            assert all(re.fullmatch(r"[A-Za-z_][\w.]*", f) for f in names), f"unsupported SOQL fields: {soql!r}"
            out = []
            for r in rows(obj, where)[:int(limit) if limit else None]:
                got = {"attributes": {"type": obj}}
                for f in names:
                    if "." in f:
                        head, tail = f.split(".", 1)
                        got.setdefault(head, {})[tail] = field_value(r, f)
                    else:
                        got[f] = r.get(f)
                out.append(got)
            return out

        def count(soql):
            self.queries.append(soql)
            m = COUNT.fullmatch(soql.strip())
            assert m, f"unsupported count SOQL: {soql!r}"
            return len(rows(m.group(1), m.group(2)))

        self.query = self.query_all = query
        self.count = count

    def describe(self, sobject):
        return {"fields": [{"name": n} for n in ("Id", "Name", "Email", "Phone", SIGNUP) + EMAILS + PHONES]}

    def insert(self, *a, **k):
        raise AssertionError("the tool is read-only: it must never write")

    update = delete = insert

    def revoke(self):
        self.revoked, self.token = True, None


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.partner_map = os.path.join(self.tmp.name, "sf_partners.csv")
        with open(self.partner_map, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(salesforce.PARTNER_COLS)
            w.writerows(PARTNER_MAP)
        self.map = salesforce.read_partners(self.partner_map)
        self.roster = os.path.join(self.tmp.name, "roster.csv")
        self.partners = os.path.join(self.tmp.name, "partners.csv")
        self.out = os.path.join(self.tmp.name, "flag.apex")
        self.write_roster(self.THREE_DEACTIVATED)
        self.write_partners(self.TWO_MARKED)

    # a club: (code, partner, club, the status of each girl row); no active row = deactivated
    THREE_DEACTIVATED = [("SUNRISEC", "Example Partner", "Sunrise Club", ["inactive", "inactive"]),
                         ("RIVERCLU", "Second Partner", "River Club", ["active", "inactive"]),
                         ("DAWNCLUB", "Example Partner", "Dawn Club", ["active", "active"]),
                         ("STARSEXA", "Example Partner", "Stars", ["inactive"]),
                         ("STARSSEC", "Second Partner", "Stars", ["active", "active"]),
                         ("NIGHTOWL", "Second Partner", "Night Owls", ["inactive", "inactive", "inactive"])]
    ONE_DEACTIVATED = [("SUNRISEC", "Example Partner", "Sunrise Club", ["active", "active"]),
                       ("NIGHTOWL", "Second Partner", "Night Owls", ["inactive"])]
    NONE_DEACTIVATED = [("SUNRISEC", "Example Partner", "Sunrise Club", ["active"]),
                        ("NIGHTOWL", "Second Partner", "Night Owls", ["active", "inactive"])]
    SECOND_STARS = [("STARSEXA", "Example Partner", "Stars", ["active"]),
                    ("STARSSEC", "Second Partner", "Stars", ["inactive", "inactive"])]
    BOTH_STARS = [("STARSEXA", "Example Partner", "Stars", ["inactive"]),
                  ("STARSSEC", "Second Partner", "Stars", ["inactive", "inactive"])]
    # the Partners tab: (partner, region, notes, jotform)
    TWO_MARKED = [("Example Partner", "Africa", "", "yes"), ("Second Partner", "Asia", "", "no"),
                  ("Third Partner", "U.S", "", ""), ("Fourth Partner", "Asia", "", "No ")]
    FIRST_MARKED = [("Example Partner", "Africa", "", "no"), ("Second Partner", "Asia", "", "yes"),
                    ("Third Partner", "U.S", "", "maybe")]      # `maybe`: glow.sync warns, naming the cell to fix
    ONE_MARKED = [("Example Partner", "Africa", "", "no"), ("Second Partner", "Asia", "", "yes"),
                  ("Third Partner", "U.S", "", "")]
    NONE_MARKED = [("Example Partner", "Africa", "", ""), ("Second Partner", "Asia", "", "yes")]
    TWICE_LISTED = [("Second Partner", "Asia", "", ""), ("Second Partner", "Africa", "", "no"),
                    ("Third Partner", "U.S", "", "NO")]

    def write_roster(self, clubs):
        """The Roster export: a removed_date only on a row that says `inactive` as the Club Roster Form writes
        it; a row of any other status has none (the status decides, never the date)."""
        with open(self.roster, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(ROSTER_COLS)
            n = 0
            for code, partner, club, statuses in clubs:
                for status in statuses:
                    first, last = GIRLS[n % len(GIRLS)]
                    removed = "2026-10-01" if status == "inactive" else ""
                    w.writerow([gid(code, n), partner, club, "Africa", f"{first} {last}", last, status,
                                "2026-09-01", removed, "test"])
                    n += 1

    def write_partners(self, rows, header=PARTNER_COLS, encoding="utf-8"):
        with open(self.partners, "w", newline="", encoding=encoding) as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)

    def cli(self, argv, org):
        """(exit code or None, stdout, stderr) of the command line, exits caught."""
        out, err, code = io.StringIO(), io.StringIO(), None
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                sfr.main(argv, org=org, partners_path=self.partner_map)
            except SystemExit as stop:
                code = stop.code
        return code, out.getvalue(), err.getvalue()

    @staticmethod
    def ok(code):
        return code in (None, 0)

    @staticmethod
    def said(code, out, err):
        return out + err + (code if isinstance(code, str) else "")

    def assertNoName(self, text, where, clubs=False):
        """No girl's name in `text`; with `clubs` (the success path) no club's or partner's name either."""
        for w in NAME_WORDS:
            self.assertNotIn(w, text, f"{where} carries a girl's name ({w!r} is a fixture girl's)")
        if clubs:
            for w in CLUB_WORDS:
                self.assertNotIn(w, text, f"{where} carries a club's or partner's name ({w!r}): ids and counts only")

    def script(self):
        self.assertTrue(os.path.exists(self.out), "the script was not written")
        with open(self.out, encoding="utf-8") as fh:
            return fh.read()

    def account_argv(self, mode, vpn=True):
        return (["--sobject", "Account", "--mode", mode, "--roster", self.roster, "--partners", self.partners,
                 "--out", self.out] + (["--vpn-off"] if vpn else []))

    def contact_argv(self, mode, vpn=True):
        return ["--sobject", "Contact", "--mode", mode, "--out", self.out] + (["--vpn-off"] if vpn else [])

    def refused(self, roster_clubs, accounts, *named):
        """deactivated_club_ids refuses, naming each of `named`."""
        self.write_roster(roster_clubs)
        with self.assertRaises((salesforce.Refused, SystemExit)) as cm:
            sfr.deactivated_club_ids(self.roster, accounts, self.map)
        for word in named:
            self.assertIn(word, str(cm.exception), f"the refusal names {word!r}")
        return str(cm.exception)


# ---- the sheet-held criteria -------------------------------------------------------------------------
class DeactivatedClubs(Fixture):
    def test_the_deactivated_clubs_accounts_come_from_the_roster_and_salesforce(self):
        """A club is deactivated when none of its Roster rows is active; its account is the Club account named as
        question 5 sends the club (the plain name, or `<club> - <partner>` for a name two partners share),
        compared as the processor compares (capitals ignored)."""
        for label, clubs, expected in (("three deactivated", self.THREE_DEACTIVATED, [SUN, STA1, NIG]),
                                       ("one deactivated", self.ONE_DEACTIVATED, [NIG]),
                                       ("none deactivated", self.NONE_DEACTIVATED, []),
                                       ("the second partner's Stars", self.SECOND_STARS, [STA2]),
                                       ("both partners' Stars", self.BOTH_STARS, [STA1, STA2])):
            with self.subTest(label):
                self.write_roster(clubs)
                got = sfr.deactivated_club_ids(self.roster, base_accounts(), self.map)
                self.assertEqual(sorted(got), sorted(expected))
                self.assertEqual(len(got), len(set(got)), "no id twice")

    def test_a_club_is_deactivated_by_the_syncs_status_rule(self):
        """glow.sync's rule, the one that retires a roster question (glow.sync.roster_pairs: glow.text.key of the
        status is `active`): a row is active when its status, surrounding and repeated spacing collapsed and
        capitals ignored, is `active`; Inactive, removed, a typo, a blank and an interior space (`act ive`: key()
        collapses runs of whitespace, it never removes a space) are not. The removed_date says nothing
        (write_roster gives one to `inactive` rows only)."""
        cases = ((["Inactive"], True), (["removed", ""], True), (["INACTIVE", "Removed", " inactive "], True),
                 ([""], True), (["", ""], True), (["act ive"], True), (["Act ive", "inactive"], True),
                 (["act ive", "active"], False), ([" active ", "inactive"], False), (["Active"], False),
                 (["ACTIVE "], False), (["", "active"], False), (["inactive", "removed", "Active"], False))
        for statuses, deactivated in cases:
            with self.subTest(statuses=statuses):
                self.write_roster([("NIGHTOWL", "Second Partner", "Night Owls", statuses),
                                   ("SUNRISEC", "Example Partner", "Sunrise Club", ["active"])])
                got = sfr.deactivated_club_ids(self.roster, base_accounts(), self.map)
                self.assertEqual(got, [NIG] if deactivated else [])

    def test_a_club_listed_under_two_codes_gives_its_id_once(self):
        """The Roster lists girls, not clubs: one club's rows may come under two girl-id codes (two uploads) and
        in two spellings of its name or partner (capitals: glow.sync.roster_pairs keys a club by glow.text.key of
        its partner and name). The club is one club, deactivated when none of all its rows is active, and its id
        is given once."""
        cases = ((["inactive"], ["inactive", "removed"], [NIG]), ([""], ["Inactive"], [NIG]),
                 (["inactive"], ["active"], []), (["active"], ["inactive"], []), (["inactive", "Active"], [""], []))
        spellings = (("Second Partner", "Night Owls"), ("Second Partner", "NIGHT OWLS"), ("SECOND PARTNER", "night owls"))
        for first, second, expected in cases:
            for partner, club in spellings:
                with self.subTest(first=first, second=second, spelling=club):
                    self.write_roster([("NIGHTOWL", "Second Partner", "Night Owls", first),
                                       ("NIGHTOW2", partner, club, second),
                                       ("SUNRISEC", "Example Partner", "Sunrise Club", ["inactive"])])
                    got = sfr.deactivated_club_ids(self.roster, base_accounts(), self.map)
                    self.assertEqual(sorted(got), sorted(expected + [SUN]))
                    self.assertEqual(len(got), len(set(got)), "no id twice")

    def test_the_account_is_matched_as_the_processor_matches_question_5(self):
        """glow.salesforce.sf_match, the processor's `equalsIgnoreCase` after a Java trim of question 5: capitals
        ignored one character to one (Java's: a dotted capital I is an i, where .lower(), casefold and
        glow.text.key all say no), one character never two ('Straße' is not 'STRASSE', as a casefold would have
        it), the Roster's name trimmed (what question 5 sends), the Account's name never (a double or a trailing
        space is another name), an accent another name."""
        cases = (("capitals", "Night Owls", "NIGHT OWLS", True),
                 ("lower case", "Night Owls", "night owls", True),
                 ("a dotted capital I against lower case", "İstanbul Owls", "istanbul owls", True),
                 ("a dotted capital I against capitals", "İstanbul Owls", "ISTANBUL OWLS", True),
                 ("the Account's dotted capital I", "istanbul owls", "İstanbul Owls", True),
                 ("a sharp s against SS", "Straße Owls", "STRASSE OWLS", False),
                 ("a sharp s against a sharp s", "Straße Owls", "STRAßE OWLS", True),
                 ("the Roster's spaces around the name", "  Night Owls ", "Night Owls", True),
                 ("a double space in the Account", "Night Owls", "Night  Owls", False),
                 ("a trailing space in the Account", "Night Owls", "Night Owls ", False),
                 ("an accent", "Café Owls", "Cafe Owls", False))
        for label, club, account_name, matches in cases:
            with self.subTest(label):
                accounts = but(base_accounts(), NIG, Name=account_name)
                if matches:
                    self.write_roster([("NIGHTOWL", "Second Partner", club, ["inactive"])])
                    self.assertEqual(sfr.deactivated_club_ids(self.roster, accounts, self.map), [NIG])
                else:
                    said = self.refused([("NIGHTOWL", "Second Partner", club, ["inactive"])], accounts, club.strip())
                    self.assertRegex(said, r"(?i)\baccount\b")

    def test_only_club_accounts_count_and_the_parent_tells_twins_apart(self):
        """The criterion is a Club account's ("a Club account whose club is deactivated"): an account of the name
        with another record type is neither the club's nor its twin, and of two Club accounts of the name the
        club's is the one under its partner's account (glow/sf_partners.csv, by the Roster's partner): no twin
        refusal in either case. Two Club accounts of the name with neither under the club's partner are refused."""
        household, other, under_p1 = acct(HH1, "Night Owls", HOUSE), acct(OT1, "Night Owls", OTHER, P2), \
            acct(CL1, "Night Owls", CLUB, P1)
        for label, extra in (("a Household account of the name", [household]),
                             ("an other-type account of the name under the club's partner", [other]),
                             ("a Club account of the name under another partner", [under_p1]),
                             ("all three", [household, other, under_p1])):
            with self.subTest(label):
                self.write_roster(self.ONE_DEACTIVATED)          # Night Owls, Second Partner's (P2)
                self.assertEqual(sfr.deactivated_club_ids(self.roster, base_accounts() + extra, self.map), [NIG])
        # the parent is the Roster's partner's account, whichever that is
        self.write_roster([("NIGHTOWL", "Example Partner", "Night Owls", ["inactive"])])
        self.assertEqual(sfr.deactivated_club_ids(self.roster, base_accounts() + [under_p1], self.map), [CL1])
        # a Club account of the name under a third partner does not make a partner-less twin the club's
        accounts = [a for a in base_accounts() if a["Id"] != NIG] + [under_p1, acct(CL3, "Night Owls", CLUB, P3)]
        self.refused(self.ONE_DEACTIVATED, accounts, "Night Owls")

    def test_the_long_name_wins_when_both_forms_exist(self):
        """RUNBOOK "Club names two partners share": a club whose `<club> - <partner>` name is a Club account's
        sends that one, so a plain-named account beside it is not the club's, whatever its parent
        (tools/sf_dupes.py club_for); a club with no such account sends its plain name; another partner's
        `<club> - <other partner>` is never this club's."""
        for label, plain in (("a plain Stars under the club's own partner", acct(STP, "Stars", CLUB, P1)),
                             ("a partner-less plain Stars", acct(STP, "Stars", CLUB)),
                             ("a plain Stars under the other partner", acct(STP, "Stars", CLUB, P2))):
            with self.subTest(label):
                self.write_roster([("STARSEXA", "Example Partner", "Stars", ["inactive"]),
                                   ("STARSSEC", "Second Partner", "Stars", ["active"])])
                self.assertEqual(sfr.deactivated_club_ids(self.roster, base_accounts() + [plain], self.map), [STA1])
                self.write_roster(self.BOTH_STARS)
                self.assertEqual(sorted(sfr.deactivated_club_ids(self.roster, base_accounts() + [plain], self.map)),
                                 sorted([STA1, STA2]))
        # a club with no namesake in the Roster whose account carries the long name
        self.write_roster([("NIGHTOWL", "Second Partner", "Night Owls", ["inactive"])])
        accounts = but(base_accounts(), NIG, Name="Night Owls - Second Partner")
        self.assertEqual(sfr.deactivated_club_ids(self.roster, accounts, self.map), [NIG])
        # the long name of another partner is not this club's: no account
        accounts = but(base_accounts(), NIG, Name="Night Owls - Example Partner", ParentId=P1)
        self.refused([("NIGHTOWL", "Second Partner", "Night Owls", ["inactive"])], accounts, "Night Owls")

    def test_a_deactivated_club_without_exactly_one_account_is_refused(self):
        said = self.refused([("LOSTCLUB", "Example Partner", "Lost Club", ["inactive", "inactive"])], base_accounts(),
                            "Lost Club")
        self.assertRegex(said, r"(?i)\baccount\b")
        # two Club accounts of the name under the club's own partner: twins the parent does not tell apart
        twins = base_accounts() + [acct(SUN2, "Sunrise Club", CLUB, P1)]
        self.refused([("SUNRISEC", "Example Partner", "Sunrise Club", ["inactive", "inactive"]),
                      ("NIGHTOWL", "Second Partner", "Night Owls", ["inactive"])], twins, SUN, SUN2, "Sunrise Club")
        # only the deactivated clubs are matched: the same twins of an active club stop nothing
        self.write_roster(self.ONE_DEACTIVATED)
        self.assertEqual(sfr.deactivated_club_ids(self.roster, twins, self.map), [NIG])


class PartnerReportPartners(Fixture):
    def test_the_partners_marked_no_give_their_account_ids(self):
        for label, rows, expected in (("two marked", self.TWO_MARKED, [P2, P4]),
                                      ("the first marked", self.FIRST_MARKED, [P1]),
                                      ("none marked", self.NONE_MARKED, []),
                                      ("listed twice", self.TWICE_LISTED, [P2, P3])):
            with self.subTest(label):
                self.write_partners(rows)
                got = sfr.partner_report_partner_ids(self.partners, self.map)
                self.assertEqual(sorted(got), sorted(expected))
                self.assertEqual(len(got), len(set(got)), "no id twice")

    def test_the_export_is_read_by_header_name(self):
        """As glow.sync.read_partners_csv reads it: the columns by header name, capitals and spacing ignored, in
        any order, a byte-order mark ignored; `no` ignoring capitals and spacing."""
        rows = [("Example Partner", "Africa", "", "yes"), ("Second Partner", "Asia", "", " NO"),
                ("Fourth Partner", "Asia", "", "No ")]
        moved = [("Example Partner", "Africa", "", "no"), ("Second Partner", "Asia", "", "yes"),
                 ("Fourth Partner", "Asia", "", "")]
        cases = (("capitals and a trailing space in the header", ("Partner", "Region", "Notes", "Jotform "), rows,
                  "utf-8", [P2, P4]),
                 ("an upper-case header", ("PARTNER", "REGION", "NOTES", "JOTFORM"), rows, "utf-8", [P2, P4]),
                 ("the columns in another order", ("jotform", "notes", "partner", "region"),
                  [(j, n, p, r) for p, r, n, j in rows], "utf-8", [P2, P4]),
                 ("a byte-order mark", PARTNER_COLS, rows, "utf-8-sig", [P2, P4]),
                 ("the marks moved", ("Partner", "Region", "Notes", "Jotform "), moved, "utf-8", [P1]))
        for label, header, table, encoding, expected in cases:
            with self.subTest(label):
                self.write_partners(table, header=header, encoding=encoding)
                got = sfr.partner_report_partner_ids(self.partners, self.map)
                self.assertEqual(sorted(got), sorted(expected))

    def test_a_marked_partner_missing_from_the_map_is_refused(self):
        self.write_partners(self.TWO_MARKED + [("Unknown Partner", "Asia", "", "no")])
        with self.assertRaises((salesforce.Refused, SystemExit)) as cm:
            sfr.partner_report_partner_ids(self.partners, self.map)
        self.assertIn("Unknown Partner", str(cm.exception), "the refusal names the partner to add to the map")
        self.assertIn("sf_partners.csv", str(cm.exception))

    def test_a_partners_export_without_the_jotform_column_is_refused(self):
        for header in (("partner", "region", "notes"), ("partner", "region", "notes", "jotform?"),
                       ("partner", "region", "notes", "on jotform")):
            with self.subTest(header=header):
                self.write_partners([("Example Partner", "Africa", "", "no")[:len(header)],
                                     ("Second Partner", "Asia", "", "no")[:len(header)]], header=header)
                with self.assertRaises((salesforce.Refused, SystemExit)) as cm:
                    sfr.partner_report_partner_ids(self.partners, self.map)
                self.assertIn("jotform", str(cm.exception))


# ---- the Apex the tool writes --------------------------------------------------------------------------
class ApexScript(unittest.TestCase):
    CASES = (([SUN, NIG], [P2]), ([STA1], []), ([], [P1, P2, P4]), ([], []))

    def test_the_account_script_carries_the_four_argument_call(self):
        for mode in MODES:
            for deactivated, partners in self.CASES:
                with self.subTest(mode=mode, deactivated=len(deactivated), partners=len(partners)):
                    script = sfr.apex_script("Account", mode, deactivated, partners)
                    m = ACCOUNT_CALL.search(script)
                    self.assertTrue(m, f"no four-argument call in {script!r}")
                    self.assertEqual(m.group(1), mode)
                    self.assertEqual(sorted(ids_in(m.group(2))), sorted(deactivated), "the deactivated clubs first")
                    self.assertEqual(sorted(ids_in(m.group(3))), sorted(partners), "the jotform=no partners second")
                    rest = without_comments(script).replace(m.group(0), "")
                    self.assertEqual(rest.strip(), "", f"the script is that one statement, found also {rest.strip()!r}")
                    quoted = set(re.findall(r"'([^']*)'", m.group(0)))
                    self.assertEqual(quoted, {"Account", mode} | set(deactivated) | set(partners),
                                     "ids only between the quotes")

    def test_the_contact_script_carries_the_two_argument_call(self):
        for mode in MODES:
            with self.subTest(mode):
                script = sfr.apex_script("Contact", mode)
                m = CONTACT_CALL.search(script)
                self.assertTrue(m, f"no two-argument call in {script!r}")
                self.assertEqual(m.group(1), mode)
                self.assertNotIn("Set<Id>", script)
                self.assertEqual(without_comments(script).replace(m.group(0), "").strip(), "")

    def test_the_script_never_carries_a_name(self):
        script = sfr.apex_script("Account", "flag", [SUN, STA1], [P1])
        for word in CLUB_WORDS + tuple(NAME_WORDS):
            self.assertNotIn(word, script)

    def test_an_unknown_sobject_or_mode_is_refused(self):
        for sobject, mode in (("Lead", "flag"), ("account", "flag"), ("", "flag"), ("Attendance__c", "dryRun"),
                              ("Account", "Flag"), ("Account", "delete"), ("Account", ""), ("Contact", "dry-run"),
                              ("Contact", "DryRun"), ("Contact", "clear "), ("Account", "flag; delete")):
            with self.subTest(sobject=sobject, mode=mode), self.assertRaises((salesforce.Refused, SystemExit)):
                sfr.apex_script(sobject, mode, [SUN], [P1])


# ---- the guard ----------------------------------------------------------------------------------------------
class GuardCounts(unittest.TestCase):
    def test_the_three_counts_are_read_from_salesforce(self):
        """Three SOQL counts on Contact (counts only: no record is read): a Contact with several of a group's
        fields set is counted once, so a count per field summed up is wrong."""
        yesterday = (today() - datetime.timedelta(days=1)).isoformat()
        cases = (("today's girls", [contact(1), contact(2)], (0, 0, 0)),
                 ("a home e-mail with a blank Email", [contact(1), contact(2, npe01__HomeEmail__c="g@example.org")],
                  (1, 0, 0)),
                 ("one of each", [contact(1, Email="a@example.org", npe01__WorkEmail__c="w@example.org"),   # Email set
                                  contact(2, npe01__AlternateEmail__c="alt@example.org"),                    # counted
                                  contact(3, MobilePhone="555-0101"),                                        # counted
                                  contact(4, Phone="555-0102", HomePhone="555-0103"),                        # Phone set
                                  contact(5, **{SIGNUP: today().isoformat()}),                               # counted
                                  contact(6, **{SIGNUP: yesterday})], (1, 1, 1)),
                 ("several", [contact(1, npe01__WorkEmail__c="w1@example.org"),
                              contact(2, npe01__WorkEmail__c="w2@example.org"), contact(3, OtherPhone="555-0104"),
                              contact(4, **{SIGNUP: today().isoformat()}), contact(5, **{SIGNUP: today().isoformat()}),
                              contact(6, npe01__WorkPhone__c="555-0105", Phone="555-0105")], (2, 1, 2)),
                 ("several fields on one Contact count once",
                  [contact(1, npe01__WorkEmail__c="w@example.org", npe01__HomeEmail__c="h@example.org",
                           npe01__AlternateEmail__c="a@example.org"),
                   contact(2, npe01__WorkPhone__c="555-0107", HomePhone="555-0108", MobilePhone="555-0109",
                           OtherPhone="555-0110"),
                   contact(3, npe01__HomeEmail__c="h3@example.org", MobilePhone="555-0111",
                           **{SIGNUP: today().isoformat()})], (2, 2, 1)),
                 ("an empty string is blank", [contact(1, Email="", npe01__HomeEmail__c="h@example.org"),
                                               contact(2, Phone="", npe01__WorkPhone__c="555-0106")], (1, 1, 0)))
        for label, contacts, (email, phone, volunteer) in cases:
            with self.subTest(label):
                org = FakeOrg(base_accounts(), contacts)
                self.assertEqual(sfr.guard_counts(org), {"email": email, "phone": phone, "volunteer": volunteer})
                self.assertTrue(org.queries, "Salesforce was read")
                for q in org.queries:
                    m = COUNT.fullmatch(q.strip())
                    self.assertTrue(m and m.group(1) == "Contact",
                                    f"the guard reads counts only, `SELECT COUNT() FROM Contact WHERE …`, never a "
                                    f"record: {q!r}")
                self.assertTrue(any(names_field(q, "Email") and all(names_field(q, f) for f in EMAILS)
                                    for q in org.queries),
                                "one count names Email and the three npe01 e-mail fields: " + repr(org.queries))
                self.assertTrue(any(names_field(q, "Phone") and all(names_field(q, f) for f in PHONES)
                                    for q in org.queries),
                                "one count names Phone and the four phone fields: " + repr(org.queries))
                self.assertTrue(any(names_field(q, SIGNUP) and re.search(r"(?i)\bTODAY\b", q) for q in org.queries),
                                "one count names the Volunteers signup field and TODAY: " + repr(org.queries))


# ---- the command line -----------------------------------------------------------------------------------
class CommandLine(Fixture):
    def test_the_account_script_is_written_from_the_sheet_and_salesforce(self):
        """The ids the script carries come from the exports and the Accounts read from Salesforce (with their
        record type and parent: a Household account named like a club, or a Club account of the name under
        another partner, is not the club's twin)."""
        twins = [acct(HH1, "Night Owls", HOUSE), acct(CL1, "Night Owls", CLUB, P1)]
        for label, clubs, partners, mode, extra, deactivated, marked in (
                ("three and two", self.THREE_DEACTIVATED, self.TWO_MARKED, "dryRun", [], [SUN, STA1, NIG], [P2, P4]),
                ("one and one", self.ONE_DEACTIVATED, self.ONE_MARKED, "flag", [], [NIG], [P1]),
                ("none", self.NONE_DEACTIVATED, self.NONE_MARKED, "clear", [], [], []),
                ("twins of another type or parent", self.ONE_DEACTIVATED, self.TWO_MARKED, "dryRun", twins, [NIG],
                 [P2, P4])):
            with self.subTest(label):
                self.write_roster(clubs)
                self.write_partners(partners)
                if os.path.exists(self.out):
                    os.remove(self.out)
                org = FakeOrg(base_accounts() + extra)
                code, out, err = self.cli(self.account_argv(mode), org)
                self.assertTrue(self.ok(code), self.said(code, out, err))
                script = self.script()
                m = ACCOUNT_CALL.search(script)
                self.assertTrue(m, script)
                self.assertEqual(m.group(1), mode)
                self.assertEqual(sorted(ids_in(m.group(2))), sorted(deactivated))
                self.assertEqual(sorted(ids_in(m.group(3))), sorted(marked))
                for i in deactivated + marked:
                    self.assertIn(i, out, "the output lists the ids the script carries")
                self.assertRegex(out, rf"(?im)^[^\n]*deactivat[^\n]*\b{len(deactivated)}\b")
                self.assertRegex(out, rf"(?im)^[^\n]*(?:jotform|partner report|partners?)[^\n]*\b{len(marked)}\b")
                self.assertNoName(out + err + script, "the Account run's output", clubs=True)
                self.assertTrue(org.queries, "Salesforce was read")

    def test_the_contact_script_is_written_when_every_guard_count_is_zero(self):
        for mode in MODES:
            with self.subTest(mode):
                if os.path.exists(self.out):
                    os.remove(self.out)
                org = FakeOrg(base_accounts(), [contact(1), contact(2), contact(3)])
                code, out, err = self.cli(self.contact_argv(mode), org)
                self.assertTrue(self.ok(code), self.said(code, out, err))
                script = self.script()
                m = CONTACT_CALL.search(script)
                self.assertTrue(m, script)
                self.assertEqual(m.group(1), mode)
                self.assertRegex(out, r"(?im)^[^\n]*e-?mail[^\n]*\b0\b")
                self.assertRegex(out, r"(?im)^[^\n]*phone[^\n]*\b0\b")
                self.assertRegex(out, r"(?im)^[^\n]*(?:volunteer|sign-?up)[^\n]*\b0\b")
                self.assertNoName(out + err + script, "the Contact run's output", clubs=True)
                self.assertTrue(org.queries, "Salesforce was read")

    def test_the_guard_refuses_the_contact_script_while_a_count_is_not_zero(self):
        """The refusal - what sys.exit says, or stderr when the exit code is a number - names each count that is
        not 0 by its kind (e-mail, phone, volunteer signups) with its number, and names no kind whose count is 0:
        a refusal that lists all three counts says nothing about what to fix. (The three counts may still be
        printed on stdout before it, as the success path prints them.)"""
        signup = {SIGNUP: today().isoformat()}
        cases = (("one home e-mail", {"email": 1}, [contact(1), contact(2, npe01__HomeEmail__c="h@example.org")]),
                 ("three e-mails", {"email": 3}, [contact(1, npe01__WorkEmail__c="w@example.org"),
                                                  contact(2, npe01__HomeEmail__c="h@example.org"), contact(3),
                                                  contact(4, npe01__AlternateEmail__c="a@example.org")]),
                 ("two phones", {"phone": 2}, [contact(1, MobilePhone="555-0101"), contact(2, npe01__WorkPhone__c="555-0102")]),
                 ("a signup today", {"volunteer": 1}, [contact(1, **signup), contact(2)]),
                 ("one of each", {"email": 1, "phone": 1, "volunteer": 1},
                  [contact(1, npe01__AlternateEmail__c="a@example.org"), contact(2, OtherPhone="555-0103"),
                   contact(3, **signup)]),
                 ("e-mails and signups", {"email": 2, "volunteer": 3},
                  [contact(1, npe01__HomeEmail__c="h1@example.org"), contact(2, npe01__HomeEmail__c="h2@example.org"),
                   contact(3, **signup), contact(4, **signup), contact(5, **signup), contact(6, Phone="555-0104",
                                                                                            HomePhone="555-0104")]))
        for mode in MODES:
            for label, bad, contacts in cases:
                with self.subTest(mode=mode, label=label):
                    if os.path.exists(self.out):
                        os.remove(self.out)
                    code, out, err = self.cli(self.contact_argv(mode), FakeOrg(base_accounts(), contacts))
                    self.assertFalse(self.ok(code), "the guard did not stop the run")
                    refusal = code if isinstance(code, str) else err
                    self.assertTrue(refusal.strip(), "the refusal says why: sys.exit('…'), or a line on stderr")
                    for kind, n in bad.items():
                        self.assertRegex(refusal, rf"(?:{KINDS[kind]})[^\n]*\b{n}\b|\b{n}\b[^\n]*(?:{KINDS[kind]})",
                                         f"the refusal names the {kind} count, {n}, by its kind: {refusal!r}")
                    for kind in KINDS:
                        if kind not in bad:
                            self.assertNotRegex(refusal, KINDS[kind],
                                                f"the refusal names {kind}, whose count is 0: it names what is not 0, "
                                                f"not all three counts: {refusal!r}")
                    self.assertFalse(os.path.exists(self.out), "no script while a guard count is not 0")
                    self.assertNoName(self.said(code, out, err), "the refusal")

    def test_a_club_without_its_account_stops_the_account_run(self):
        self.write_roster(self.ONE_DEACTIVATED + [("LOSTCLUB", "Example Partner", "Lost Club", ["inactive"])])
        code, out, err = self.cli(self.account_argv("dryRun"), FakeOrg(base_accounts()))
        self.assertFalse(self.ok(code), "a club without an account did not stop the run")
        self.assertIn("Lost Club", self.said(code, out, err))
        self.assertFalse(os.path.exists(self.out), "no script when a club cannot be matched")
        self.assertNoName(self.said(code, out, err), "the refusal")

    def test_a_partners_export_problem_stops_the_account_run(self):
        """Through main, in every mode: a Partners export without the `jotform` column (the run would judge the
        Salesforce-reporting partners' clubs by batches they never have) and a partner marked `no` that is
        missing from glow/sf_partners.csv each stop the Account run with a refusal naming what to fix, and no
        script is written."""
        cases = (("no jotform column", ("partner", "region", "notes"),
                  [("Example Partner", "Africa", ""), ("Second Partner", "Asia", "")], ("jotform",)),
                 ("a marked partner missing from the map", PARTNER_COLS,
                  self.TWO_MARKED + [("Unknown Partner", "Asia", "", "no")], ("Unknown Partner", "sf_partners.csv")))
        for mode in MODES:
            for label, header, rows, named in cases:
                with self.subTest(mode=mode, label=label):
                    self.write_roster(self.ONE_DEACTIVATED)
                    self.write_partners(rows, header=header)
                    if os.path.exists(self.out):
                        os.remove(self.out)
                    code, out, err = self.cli(self.account_argv(mode), FakeOrg(base_accounts()))
                    self.assertFalse(self.ok(code), f"{label}: the run was not stopped")
                    said = self.said(code, out, err)
                    for word in named:
                        self.assertIn(word, said, f"{label}: the refusal names {word!r}")
                    self.assertFalse(os.path.exists(self.out), f"{label}: no script")
                    self.assertNoName(said, "the refusal")

    def test_the_sheet_exports_belong_to_the_account_run(self):
        """--roster and --partners are the Account run's inputs: an Account run without either, and a Contact run
        given either (the guard reads Salesforce only; an export it would not read is a mistake, not noise), is
        refused naming the flag - before anything is read, and no script is written."""
        roster, partners = ["--roster", self.roster], ["--partners", self.partners]
        tail = ["--out", self.out, "--vpn-off"]
        cases = (("Account without --roster", ["--sobject", "Account", "--mode", "dryRun"] + partners + tail, "--roster"),
                 ("Account without --partners", ["--sobject", "Account", "--mode", "flag"] + roster + tail, "--partners"),
                 ("Account without either", ["--sobject", "Account", "--mode", "clear"] + tail, "--roster|--partners"),
                 ("Contact with --roster", ["--sobject", "Contact", "--mode", "dryRun"] + roster + tail, "--roster"),
                 ("Contact with --partners", ["--sobject", "Contact", "--mode", "flag"] + partners + tail, "--partners"),
                 ("Contact with both", ["--sobject", "Contact", "--mode", "clear"] + roster + partners + tail,
                  "--roster|--partners"))
        for label, argv, flag in cases:
            with self.subTest(label):
                if os.path.exists(self.out):
                    os.remove(self.out)
                org = FakeOrg(base_accounts(), [contact(1)])
                code, out, err = self.cli(argv, org)
                self.assertFalse(self.ok(code), f"{label}: ran")
                self.assertRegex(self.said(code, out, err), flag, f"{label}: the refusal names the flag")
                self.assertEqual(org.queries, [], f"{label}: nothing is read when the command line is wrong")
                self.assertFalse(os.path.exists(self.out), f"{label}: no script")
                self.assertNoName(self.said(code, out, err), "the refusal", clubs=True)

    def test_the_vpn_flag_is_required_before_anything_is_read(self):
        for argv in (self.account_argv("dryRun", vpn=False), self.contact_argv("flag", vpn=False)):
            with self.subTest(argv[1]):
                org = FakeOrg(base_accounts(), [contact(1)])
                code, out, err = self.cli(argv, org)
                self.assertFalse(self.ok(code), "ran without --vpn-off")
                self.assertIn(salesforce.VPN_REFUSAL, self.said(code, out, err))
                self.assertEqual(org.queries, [], "nothing is read without --vpn-off")
                self.assertFalse(os.path.exists(self.out))

    def test_the_tool_only_reads(self):
        """Every path through the tool, in every mode, reads: a write raises in FakeOrg and surfaces here."""
        for mode in MODES:
            for argv in (self.account_argv(mode), self.contact_argv(mode)):
                with self.subTest(mode=mode, sobject=argv[1]):
                    org = FakeOrg(base_accounts(), [contact(1)])
                    code, out, err = self.cli(argv, org)
                    self.assertTrue(self.ok(code), self.said(code, out, err))
                    self.assertTrue(org.queries, "Salesforce was read")


# ---- the household-naming guard (Ryan, 2026-10-26) -------------------------------------------------------
class HouseholdNamingGuard(Fixture):
    """NPSP's Automatic Household Naming would rename the partners' household Accounts on any Account update:
    before every Account script, in every mode, one read-only count of the Households Settings rows with it on;
    the script only when that count is 0. Contact runs never read it."""

    def fresh(self, clubs, partners):
        self.write_roster(clubs)
        self.write_partners(partners)
        if os.path.exists(self.out):
            os.remove(self.out)

    def assertNamingCountRead(self, org):
        """The household settings were read, by a count only: `SELECT COUNT() FROM npo02__Households_Settings__c
        WHERE …` naming the naming checkbox and `true`, never a record read."""
        reads = [q for q in org.queries if re.search(rf"(?i)\b{HH_SETTINGS}\b", q)]
        self.assertTrue(reads, f"the household-naming count was not read: {org.queries!r}")
        for q in reads:
            m = COUNT.fullmatch(q.strip())
            self.assertTrue(m and m.group(1) == HH_SETTINGS,
                            f"the household-naming guard reads a count only, `SELECT COUNT() FROM {HH_SETTINGS} "
                            f"WHERE …`: {q!r}")
            self.assertTrue(names_field(q, NAMING) and re.search(r"(?i)\btrue\b", q),
                            f"the count names {NAMING} = true: {q!r}")

    def test_household_naming_on_refuses_every_account_script(self):
        """A count above 0 stops the Account run in each mode (dryRun, flag and clear: each runs an update or precedes
        one), whatever the exports hold: the refusal names the household-naming guard, the count is printed on a
        line that names household naming, and no script is written. Only the rows with naming on count: a row
        with it off beside them does not."""
        cases = (("the org default on", 1, [naming_setting(1, True)], self.THREE_DEACTIVATED, self.TWO_MARKED),
                 ("a profile's row on, the org default off", 1,
                  [naming_setting(1, False), naming_setting(2, True), naming_setting(3, False)],
                  self.ONE_DEACTIVATED, self.ONE_MARKED),
                 ("two rows on, one off, nothing to flag", 2,
                  [naming_setting(1, True), naming_setting(2, False), naming_setting(3, True)],
                  self.NONE_DEACTIVATED, self.NONE_MARKED),
                 ("three rows on", 3, [naming_setting(1, True), naming_setting(2, True), naming_setting(3, True)],
                  self.THREE_DEACTIVATED, self.ONE_MARKED))
        for mode in MODES:
            for label, n, settings, clubs, partners in cases:
                with self.subTest(mode=mode, label=label):
                    self.fresh(clubs, partners)
                    org = FakeOrg(base_accounts(), [contact(1)], settings)
                    code, out, err = self.cli(self.account_argv(mode), org)
                    said = self.said(code, out, err)
                    self.assertFalse(self.ok(code), f"household naming is on ({n}) and the Account run went on: {said}")
                    refusal = code if isinstance(code, str) else err
                    self.assertTrue(refusal.strip(), "the refusal says why: sys.exit('…'), or a line on stderr")
                    self.assertRegex(refusal, NAMING_GUARD,
                                     f"the refusal names the household-naming guard: {refusal!r}")
                    self.assertTrue(says_naming_count(said, n),
                                    f"the count, {n}, is printed on a line naming household naming: {said!r}")
                    self.assertFalse(os.path.exists(self.out), "no script while household naming is on")
                    self.assertNamingCountRead(org)
                    self.assertNoName(said, "the household-naming refusal", clubs=True)

    def test_household_naming_off_writes_the_account_script_and_prints_the_count(self):
        """A count of 0 - no row with naming on, however many rows with it off, or no row at all - lets the Account
        script be written in each mode, with the ids the exports give, and the 0 is printed on a line that names
        household naming."""
        cases = (("the org default off", [naming_setting(1, False)], self.THREE_DEACTIVATED, self.TWO_MARKED,
                  [SUN, STA1, NIG], [P2, P4]),
                 ("three rows, all off", [naming_setting(1, False), naming_setting(2, False), naming_setting(3, False)],
                  self.ONE_DEACTIVATED, self.ONE_MARKED, [NIG], [P1]),
                 ("no Households Settings row", [], self.NONE_DEACTIVATED, self.NONE_MARKED, [], []))
        for mode in MODES:
            for label, settings, clubs, partners, deactivated, marked in cases:
                with self.subTest(mode=mode, label=label):
                    self.fresh(clubs, partners)
                    org = FakeOrg(base_accounts(), [contact(1)], settings)
                    code, out, err = self.cli(self.account_argv(mode), org)
                    self.assertTrue(self.ok(code), self.said(code, out, err))
                    script = self.script()
                    m = ACCOUNT_CALL.search(script)
                    self.assertTrue(m, script)
                    self.assertEqual(m.group(1), mode)
                    self.assertEqual(sorted(ids_in(m.group(2))), sorted(deactivated))
                    self.assertEqual(sorted(ids_in(m.group(3))), sorted(marked))
                    self.assertTrue(says_naming_count(out, 0),
                                    f"the count, 0, is printed on a line naming household naming: {out!r}")
                    self.assertNamingCountRead(org)
                    self.assertNoName(out + err + script, "the Account run's output", clubs=True)

    def test_the_contact_run_never_reads_the_household_settings(self):
        """The household-naming guard is the Account run's alone: a Contact run, in each mode, with naming on in
        Salesforce, reads no Households Settings and writes its script."""
        for mode in MODES:
            for settings in ([naming_setting(1, True)], [naming_setting(1, True), naming_setting(2, True)]):
                with self.subTest(mode=mode, on=len(settings)):
                    if os.path.exists(self.out):
                        os.remove(self.out)
                    org = FakeOrg(base_accounts(), [contact(1), contact(2)], settings)
                    code, out, err = self.cli(self.contact_argv(mode), org)
                    self.assertTrue(self.ok(code), self.said(code, out, err))
                    m = CONTACT_CALL.search(self.script())
                    self.assertTrue(m)
                    self.assertEqual(m.group(1), mode)
                    self.assertTrue(org.queries, "Salesforce was read")
                    self.assertEqual([q for q in org.queries if re.search(r"(?i)households?_settings", q)], [],
                                     "a Contact run reads no Households Settings")


if __name__ == "__main__":
    unittest.main(verbosity=1)
