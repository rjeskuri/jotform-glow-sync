#!/usr/bin/env python3
"""
Offline tests for tools/sf_dupes.py (found by `make py`'s unittest discovery; glow/salesforce.py's
query_all / delete: test/salesforce_test.py). Everything here is fictional: clubs, partners, girls
(names from test/fixtures/make_fixture.py's invented pools) and Salesforce ids are invented.

A fake org answers the tool's SOQL with a small evaluator (WHERE ... AND ..., =, >=, IN, GROUP BY)
and runs `sf apex run` the way Salesforce would for the Apex this tool writes: it checks the
counts the Apex asserts, merges (rows, affiliations and duplicate-rule items follow the kept
contact; the merged one is deleted with its MasterRecordId) unless the run is a rehearsal, and
returns a debug log that also holds names in lines the tool must never print.
"""
import collections
import contextlib
import csv
import datetime
import io
import json
import os
import re
import stat
import sys
import tempfile
import types
import unittest
import unittest.mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import sf_dupes as sd                  # noqa: E402
import helpers                         # noqa: E402,F401  the VPN check's stand-in (#251)
from glow import forms                 # noqa: E402
from glow.jotform import Client, JotformError   # noqa: E402
from glow import salesforce            # noqa: E402

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 10, 7, 12, 0, tzinfo=UTC)          # 08:00 US Eastern
RT = "012000000000000CLB"
SUN, RIV = "001000000000000SUN", "001000000000000RIV"
USER, OTHER_USER = "005000000000000PRC", "005000000000000OTH"
DESCRIPTION = "Auto-created from Attendance Batch"
BATCH = "a1l000000000000001"
ROSTER_COLS = ["girl_id", "partner", "club", "region", "full_name", "last_name", "status",
               "added_date", "removed_date", "source"]
# every word of every fictional girl's name used below: none may ever reach the tool's output
NAME_WORDS = ["Amara", "Fennwhistle", "Beatrice", "Marrowgate", "Chiara", "Ostrivane", "Pellucidor",
              "Dalia", "Thornquibble", "Esther", "Umberlash", "Zara", "Zibblewick"]


def cid(n):
    return f"003{n:015d}"


def row_id(n):
    return f"a1m{n:015d}"


def aff_id(n):
    return f"a0x{n:015d}"


def item_id(n):
    return f"0GL{n:015d}"


def set_id(n):
    return f"0GK{n:015d}"


def created(day, hour=10):
    return f"{day}T{hour:02d}:00:00.000+0000"


def literal_time(text):
    return datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def as_salesforce_logs(lines):
    """A debug log as `sf apex run --json` returns it: a USER_DEBUG message's | is written as &#124;
    (seen 2026-10-07)."""
    out = []
    for line in lines:
        parts = line.split("|", 4)
        out.append("|".join(parts[:4] + [parts[4].replace("|", "&#124;")])
                   if len(parts) == 5 and parts[1] == "USER_DEBUG" else line)
    return "\n".join(out)


def cli_answer(success, outcome):
    """The CLI's answer: the outcome under "result" when the Apex finished, under "data" (an error
    answer) when it threw or did not compile (seen 2026-10-07)."""
    if success:
        return {"status": 0, "result": outcome}
    return {"status": 1, "name": "executeRuntimeFailure" if outcome.get("compiled") else "executeCompileFailure",
            "message": "the Apex threw", "exitCode": 1, "data": outcome}


class FakeSF:
    """Salesforce as far as tools/sf_dupes.py can see it."""
    alias = "fake"
    CREATEABLE = {"Contact": ["FirstName", "LastName", "AccountId", "Description", "Contact_Role__c", "Email",
                              "npsp__Primary_Affiliation__c"],
                  "Attendance__c": ["Contact__c", "Account__c", "Attendance_Date__c", "Attendance_Batch__c", "Module__c"],
                  "npe5__Affiliation__c": ["npe5__Contact__c", "npe5__Organization__c", "npe5__Status__c",
                                           "npe5__Primary__c"],
                  "DuplicateRecordSet": ["DuplicateRuleId"]}

    def __init__(self):
        self.accounts = {SUN: {"Id": SUN, "Name": "Sunrise Club", "RecordTypeId": RT},
                         RIV: {"Id": RIV, "Name": "River Club", "RecordTypeId": RT}}
        self.contacts, self.rows, self.affs, self.items, self.sets = {}, {}, {}, {}, {}
        self.batches, self.events, self.queries = [], [], []
        self.apex_mode, self.on_write = "ok", None
        self.blank_on_delete, self.delete_answer = False, None

    # ---- the world
    def contact(self, n, first, last, acc=SUN, when="2026-10-01", hour=10, by=USER, description=DESCRIPTION,
                affiliation=True, primary=False):
        self.contacts[cid(n)] = {"Id": cid(n), "FirstName": first, "LastName": last,
                                 "Name": f"{first} {last}" if first else last, "AccountId": acc,
                                 "CreatedDate": created(when, hour), "CreatedById": by, "Description": description,
                                 "Contact_Role__c": "Participant", "Email": None, "IsDeleted": False,
                                 "MasterRecordId": None, "npsp__Primary_Affiliation__c": acc if primary else None}
        if affiliation:
            self.aff(n, n, acc, when, hour, primary)

    def row(self, n, contact_n, day, acc=None):
        self.rows[row_id(n)] = {"Id": row_id(n), "Contact__c": cid(contact_n),
                                "Account__c": acc or self.contacts[cid(contact_n)]["AccountId"],
                                "Attendance_Date__c": day, "Attendance_Batch__c": BATCH, "Module__c": "Self Advocacy"}

    def aff(self, n, contact_n, acc, when="2026-10-01", hour=10, primary=False):
        self.affs[aff_id(n)] = {"Id": aff_id(n), "npe5__Contact__c": cid(contact_n), "npe5__Organization__c": acc,
                                "CreatedDate": created(when, hour), "npe5__Status__c": "Current",
                                "npe5__Primary__c": primary}

    def dup_set(self, n, *contact_ns):
        self.sets[set_id(n)] = {"Id": set_id(n), "DuplicateRuleId": "0Bm000000000000DUP"}
        for k, c in enumerate(contact_ns):
            self.items[item_id(n * 10 + k)] = {"Id": item_id(n * 10 + k), "RecordId": cid(c),
                                               "DuplicateRecordSetId": set_id(n)}

    def participants(self, acc):
        return [c for c in self.contacts.values() if not c["IsDeleted"] and c["AccountId"] == acc]

    # ---- reads
    def table(self, obj, deleted=False):
        return {"Contact": [c for c in self.contacts.values() if deleted or not c["IsDeleted"]],
                "Account": list(self.accounts.values()), "Attendance__c": list(self.rows.values()),
                "npe5__Affiliation__c": list(self.affs.values()), "DuplicateRecordItem": list(self.items.values()),
                "DuplicateRecordSet": list(self.sets.values()), "Attendance_Batch__c": self.batches}[obj]

    def get(self, rec, field):
        if field.startswith("Account."):
            return self.accounts.get(rec.get("AccountId"), {}).get(field.split(".", 1)[1])
        return rec.get(field)

    def matches(self, rec, where):
        for cond in (where.split(" AND ") if where else []):
            m = re.fullmatch(r"([\w.]+) (=|>=|IN) (.+)", cond)
            assert m, cond
            field, op, text = m.groups()
            have = self.get(rec, field)
            if text.startswith("("):
                value = [re.sub(r"\\(.)", r"\1", v) for v in re.findall(r"'((?:[^'\\]|\\.)*)'", text)]
            elif text.startswith("'"):
                value = re.sub(r"\\(.)", r"\1", text[1:-1])
            elif text in ("true", "false"):
                value = text == "true"
            else:
                value = literal_time(text)
            if op == "=" and have != value or op == "IN" and have not in value:
                return False
            if op == ">=" and sd.sf_time(have) < value:
                return False
        return True

    def select(self, soql, deleted=False):
        self.queries.append(soql)
        if soql.startswith("SELECT Id FROM RecordType"):
            return [{"Id": RT, "attributes": {"type": "RecordType"}}]
        m = re.fullmatch(r"SELECT (.+?) FROM (\w+)(?: WHERE (.+?))?(?: GROUP BY ([\w, ]+))?(?: ORDER BY ([\w, .]+))?",
                         soql)
        assert m, soql
        fields, obj, where, group, _ = m.groups()
        recs = [r for r in self.table(obj, deleted) if self.matches(r, where)]
        if group:
            names = [g.strip() for g in group.split(",")]
            counted = collections.Counter(tuple(self.get(r, f) for f in names) for r in recs)
            return [dict(zip(names, k), n=v, attributes={"type": "AggregateResult"}) for k, v in counted.items()]
        out = []
        for r in sorted(recs, key=lambda r: r["Id"]):
            got = {"attributes": {"type": obj}}
            for f in (x.strip() for x in fields.split(",")):
                if "." in f:
                    got.setdefault(f.split(".")[0], {})[f.split(".")[1]] = self.get(r, f)
                else:
                    assert f in r, (obj, f)
                    got[f] = r[f]
            out.append(got)
        return out

    def query(self, soql):
        return self.select(soql)

    def query_all(self, soql):
        return self.select(soql, deleted=True)

    def count(self, soql):
        self.queries.append(soql)
        m = re.fullmatch(r"SELECT COUNT\(\) FROM (\w+)(?: WHERE (.+))?", soql)
        assert m, soql
        return sum(1 for r in self.table(m.group(1)) if self.matches(r, m.group(2)))

    def describe(self, sobject):
        return {"fields": [{"name": "Id", "createable": False}, {"name": "Name", "createable": False}]
                + [{"name": f, "createable": True} for f in self.CREATEABLE[sobject]]}

    # ---- writes
    def update(self, sobject, record_id, body):
        assert sobject == "Contact"
        self.events.append(("update", record_id, self.on_write(self) if self.on_write else None))
        c = self.contacts[record_id]
        c.update(body)
        c["Name"] = f"{c['FirstName']} {c['LastName']}" if c["FirstName"] else c["LastName"]
        return 204, None

    def delete(self, sobject, record_id):
        self.events.append(("delete", record_id, self.on_write(self) if self.on_write else None))
        if self.delete_answer:
            return self.delete_answer
        if sobject == "npe5__Affiliation__c":
            gone = self.affs.pop(record_id)
            contact = self.contacts[gone["npe5__Contact__c"]]
            # NPSP's AfterDelete: a Primary affiliation gone blanks the contact's Primary Affiliation
            if (gone["npe5__Primary__c"] and contact["npsp__Primary_Affiliation__c"] == gone["npe5__Organization__c"]) \
                    or self.blank_on_delete:
                contact["npsp__Primary_Affiliation__c"] = None
        else:
            assert sobject == "DuplicateRecordSet"
            del self.sets[record_id]
            for k in [k for k, i in self.items.items() if i["DuplicateRecordSetId"] == record_id]:
                del self.items[k]
        return 204, None

    def run(self, argv, input=None, **_):
        assert argv[:3] == ["sf", "apex", "run"] and argv[-1] == "--json" and "--target-org" in argv, argv
        path = argv[argv.index("--file") + 1]
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.events.append(("apex", os.path.basename(path), self.on_write(self) if self.on_write else None))
        acc = re.search(r"Id acc = '(\w+)';", text).group(1)
        calls = [(k, re.findall(r"'(\w+)'", ids)) for k, ids in
                 re.findall(r"Database\.merge\(new Contact\(Id = '(\w+)'\), new List<Id>\{([^}]*)\}, true\)", text)]
        everyone = {k for k, _ in calls} | {x for _, xs in calls for x in xs}
        want_people = int(re.search(r"System\.assertEquals\((\d+), participantsBefore", text).group(1))
        want_rows = int(re.search(r"System\.assertEquals\((\d+), rowsBefore", text).group(1))
        rehearse = "RehearsalEndException" in text
        logs = ["67.0 APEX_CODE,FINEST;APEX_PROFILING,INFO",
                "10:00:00.1 (100)|VARIABLE_ASSIGNMENT|[20]|c|{\"Name\":\"Amara Fennwhistle\",\"Id\":\"" + cid(1) + "\"}",
                "10:00:00.2 (200)|USER_DEBUG|[1]|DEBUG|Zara Zibblewick was processed",
                "10:00:00.3 (300)|USER_DEBUG|[2]|ERROR|DIAG|Beatrice Marrowgate sneaked in"]

        def answer(success, message="", compiled=True):
            return types.SimpleNamespace(returncode=0 if success else 1, stdout=json.dumps(cli_answer(success, {
                "success": success, "compiled": compiled, "compileProblem": "", "exceptionMessage": message,
                "exceptionStackTrace": "AnonymousBlock: line 9" if message else "", "line": -1, "column": -1,
                "logs": as_salesforce_logs(logs)})))
        if self.apex_mode == "unreadable":
            return types.SimpleNamespace(returncode=1, stdout="Error: socket hang up for Amara Fennwhistle")
        have_people = len(self.participants(acc))
        if have_people != want_people:
            return answer(False, f"System.AssertException: Assertion Failed: DIAG|fail|participants before|{acc}: "
                                 f"Expected: {want_people}, Actual: {have_people}")
        have_rows = sum(1 for r in self.rows.values() if r["Contact__c"] in everyone)
        if have_rows != want_rows:
            return answer(False, f"System.AssertException: Assertion Failed: DIAG|fail|rows before|{acc}")
        normalized = set(re.findall(r"'(\w+)'", re.search(r"Set<Id> normalized = new Set<Id>\{([^}]*)\}", text).group(1)))
        for kept, ids in calls:                    # the Apex's name guard: exact, or norm()ed for these groups
            same = (lambda a, b: sd.norm(a) == sd.norm(b)) if kept in normalized else (lambda a, b: a == b)
            for x in ids:
                if not all(same(self.contacts[x][f], self.contacts[kept][f]) for f in sd.NAME_FIELDS):
                    return answer(False, f"System.AssertException: Assertion Failed: DIAG|fail|name|{x}")
        if self.apex_mode == "other":
            logs.append("10:00:01.0 (900)|FATAL_ERROR|System.DmlException: Merge failed. DUPLICATES_DETECTED, "
                        "AMARA FENNWHISTLE")
            return answer(False, "System.DmlException: Merge failed. First exception on row 0; first error: "
                                 "DUPLICATES_DETECTED, AMARA FENNWHISTLE looks like Amara Fennwhistle: []")
        for kept, ids in calls:
            moved = sorted(r["Id"] for r in self.rows.values() if r["Contact__c"] in ids)
            logs.append(f"10:00:00.5 (500)|USER_DEBUG|[40]|ERROR|DIAG|merged|{kept}|{','.join(ids)}|{','.join(moved)}")
            if not rehearse or self.apex_mode == "leaky":       # leaky: a rehearsal that kept its changes
                for x in ids:
                    for r in self.rows.values():
                        if r["Contact__c"] == x:
                            r["Contact__c"] = kept
                    for a in self.affs.values():
                        if a["npe5__Contact__c"] == x:
                            a["npe5__Contact__c"] = kept
                    for k in [k for k, i in self.items.items() if i["RecordId"] == x]:
                        del self.items[k]
                    self.contacts[x].update(IsDeleted=True, MasterRecordId=kept)
        logs += ["10:00:00.8 (800)|USER_DEBUG|[90]|ERROR|DIAG|limits|queries=9/100|dml=2/150|cpu=420/10000",
                 f"10:00:00.9 (900)|USER_DEBUG|[91]|ERROR|DIAG|ok|{acc}"]
        if rehearse:
            return answer(False, f"RehearsalEndException: {sd.MARKER}")
        return answer(True)


class FakeJotform:
    """The regional forms' submissions (Jotform's clock: US Eastern), newest first as Jotform's default
    order is (`oldest_first` plays an order the tool must not trust), paged by the client's own reader."""
    submissions = Client.submissions

    def __init__(self):
        self.latest = {fid: "2026-10-07 07:00:00" for fid in forms.REGIONALS.values()}   # 11:00 UTC
        self.subs = {fid: [] for fid in forms.REGIONALS.values()}
        self.calls, self.oldest_first = [], False

    def get(self, path, **params):
        self.calls.append((path, params))
        assert "orderby" not in params and "direction" not in params, params    # the default order only
        form_id = path.split("/")[2]
        if path.endswith("/submissions"):
            subs = sorted(self.subs[form_id] + [self.latest[form_id]], reverse=not self.oldest_first)
            offset = params.get("offset", 0)
            return [{"id": f"{form_id}-{c}", "created_at": c, "status": "ACTIVE"}
                    for c in subs][offset:offset + params["limit"]]
        return {"id": form_id, "last_submission": self.latest[form_id]}


def flat(n, first, last, acc=SUN, when="2026-10-01", hour=10, by=USER, account_name=None):
    return {"Id": cid(n), "Name": f"{first} {last}" if first else last, "FirstName": first, "LastName": last,
            "AccountId": acc, "AccountName": account_name or {SUN: "Sunrise Club", RIV: "River Club"}[acc],
            "CreatedDate": created(when, hour), "CreatedById": by, "Description": DESCRIPTION,
            "Contact_Role__c": "Participant"}


class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = os.path.join(self.tmp.name, "sf_dupes")
        self.roster = os.path.join(self.tmp.name, "roster.csv")
        self.backfill = os.path.join(self.tmp.name, "created_contacts.csv")
        self.sf, self.jf, self.now = FakeSF(), FakeJotform(), NOW
        self.write_roster()
        self.write_backfill(1)
        self.printed = []

    def write_roster(self, extra=(), sunrise=("Amara Fennwhistle", "Beatrice Marrowgate", "Chiara Ostrivane Pellucidor",
                                              "Dalia Thornquibble"), river=("Amara Fennwhistle",)):
        with open(self.roster, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(ROSTER_COLS)
            rows = [("Example Partner", "Sunrise Club", n, "active") for n in sunrise] \
                + [("Second Partner", "River Club", n, "active") for n in river] + list(extra)
            for partner, club, name, status in rows:
                w.writerow(["", partner, club, "Africa", name, name.split()[-1], status, "2026-09-01", "", "test"])

    def write_backfill(self, *contact_ns):
        with open(self.backfill, "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh, lineterminator="\n").writerows([BATCH, cid(n)] for n in contact_ns)

    def world(self):
        """Sunrise: one girl three times (the first from the back-fill), one twice, one stored with a
        double space, one alone; River: a namesake of the first (another girl, another club)."""
        sf = self.sf
        sf.contact(1, "Amara", "Fennwhistle", SUN, "2026-09-02")
        sf.contact(2, "Amara", "Fennwhistle", SUN, "2026-10-03")
        sf.contact(3, "Amara", "Fennwhistle", SUN, "2026-10-04")
        sf.contact(4, "Beatrice", "Marrowgate", SUN, "2026-10-01")
        sf.contact(5, "Beatrice", "Marrowgate", SUN, "2026-10-02")
        sf.contact(6, "Chiara", "Ostrivane  Pellucidor", SUN, "2026-09-20")
        sf.contact(7, "Dalia", "Thornquibble", SUN, "2026-09-03")
        sf.contact(8, "Amara", "Fennwhistle", RIV, "2026-09-04")
        for n, c, day in ((1, 1, "2026-09-09"), (2, 2, "2026-10-03"), (3, 3, "2026-10-04"), (4, 4, "2026-10-01"),
                          (5, 5, "2026-10-02"), (6, 7, "2026-10-01"), (7, 8, "2026-10-01")):
            sf.row(n, c, day)
        sf.dup_set(1, 4, 5)

    def run_tool(self, *argv, vpn=True):
        out, err = io.StringIO(), io.StringIO()
        code = 0
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                sd.main(["--dir", self.dir] + list(argv) + (["--vpn-off"] if vpn else []), org=self.sf,
                        jotform=self.jf, clock=lambda: self.now)
        except SystemExit as stop:
            code = stop.code
        text = out.getvalue() + err.getvalue() + (code if isinstance(code, str) else "")
        self.printed.append(text)
        return text, code

    def plan_path(self):
        return os.path.join(self.dir, "merge_plan.json")

    def make_plan(self, expect=0):
        out, code = self.run_tool("plan", "--roster", self.roster, "--backfill-contacts", self.backfill)
        self.assertEqual(code, expect, out)
        return out

    def rollback(self):
        with open(os.path.join(self.dir, "merge_rollback.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def assert_no_names(self, text):
        for word in NAME_WORDS:
            self.assertNotIn(word.lower(), text.lower())


# ---- the pure parts --------------------------------------------------------------------------------
class SfDupesNames(Harness):
    def test_the_key_ignores_spacing_invisible_characters_and_case(self):
        base = sd.spelling_key("Amara Fennwhistle")
        for variant in ("Amara  Fennwhistle", "Amara\xa0Fennwhistle", "Amara\tFennwhistle", "\u200eAmara Fennwhistle",
                        "Amara\u200b Fennwhistle", " AMARA fennwhistle ", "Amara\ufeff Fennwhistle"):
            with self.subTest(repr(variant)):
                self.assertEqual(sd.spelling_key(variant), base)
        for oddity in ("Amara  Fennwhistle", "Amara\xa0Fennwhistle", "Amara\tFennwhistle", "\u200eAmara Fennwhistle",
                       " Amara Fennwhistle"):
            self.assertTrue(sd.odd_spacing(oddity), repr(oddity))
        self.assertFalse(sd.odd_spacing("Amara Fennwhistle"))
        self.assertNotEqual(sd.spelling_key("Amara Fennwhistle"), sd.spelling_key("Amara Fennwhistl"))
        self.assertEqual(sd.norm("amara  Fennwhistle\u200e"), "amara Fennwhistle")      # case kept
        self.assertTrue(sd.odd_list("Amara  Fennwhistle, Dalia Thornquibble"))
        self.assertTrue(sd.odd_list("Amara\xa0Fennwhistle"))
        self.assertTrue(sd.odd_list("Amara Fennwhistle,\u200bDalia Thornquibble"))
        self.assertFalse(sd.odd_list("Amara Fennwhistle, Dalia Thornquibble"))

    def test_groups_form_within_one_account_only(self):
        contacts = [flat(1, "Amara", "Fennwhistle", SUN), flat(2, "Amara", "Fennwhistle", RIV),
                    flat(3, "Beatrice", "Marrowgate", SUN), flat(4, "beatrice", "Marrowgate  ", SUN)]
        found = sd.group_by_key(contacts)
        self.assertEqual([[c["Id"] for c in g] for g in found.values()], [[cid(3), cid(4)]])

    def decide(self, contacts, rows=None, backfill=()):
        roster = sd.Roster(self.roster)
        return sd.decide(contacts, rows or {}, roster, ["Sunrise Club", "River Club"], set(backfill))

    def test_the_roster_proves_each_group(self):
        pair = [flat(1, "Amara", "Fennwhistle", when="2026-10-01"), flat(2, "Amara", "Fennwhistle", when="2026-10-02")]
        groups, _, needs = self.decide(pair)
        self.assertEqual((len(groups), needs), (1, []))
        cases = {"two roster girls of that name": (dict(sunrise=("Amara Fennwhistle", "Amara  fennwhistle")),
                                                    "not_one_roster_girl"),
                 "not on the roster": (dict(sunrise=("Dalia Thornquibble",)), "not_one_roster_girl"),
                 "on the roster but not active": (dict(sunrise=("Dalia Thornquibble",),
                                                       extra=[("Example Partner", "Sunrise Club", "Amara Fennwhistle",
                                                               "removed")]), "not_one_roster_girl"),
                 "spelled otherwise on the roster": (dict(sunrise=("Amara FennWhistle",)), "name_differs_from_roster"),
                 "the club is not on the roster": (dict(sunrise=(), river=("Amara Fennwhistle",)), "club_not_on_roster")}
        for what, (roster, reason) in cases.items():
            with self.subTest(what):
                self.write_roster(**roster)
                groups, renames, needs = self.decide(pair)
                self.assertEqual(groups, [])
                self.assertEqual([n["reasons"] for n in needs], [[reason]])
                self.assertEqual(needs[0]["contact_ids"], [cid(1), cid(2)])

    def test_a_club_two_partners_share_is_found_by_its_long_name_only(self):
        self.write_roster(sunrise=("Amara Fennwhistle",),
                          extra=[("Second Partner", "Sunrise Club", "Esther Umberlash", "active")])
        pair = [flat(1, "Amara", "Fennwhistle", when="2026-10-01"), flat(2, "Amara", "Fennwhistle", when="2026-10-02")]
        _, _, needs = self.decide(pair)
        self.assertEqual(needs[0]["reasons"], ["club_ambiguous"])        # 'Sunrise Club' is two partners' club
        long = [dict(c, AccountName="Sunrise Club - Example Partner") for c in pair]
        groups, _, needs = self.decide(long)
        self.assertEqual((len(groups), needs), (1, []))

    def test_the_contact_that_stays(self):
        three = [flat(1, "Amara", "Fennwhistle", when="2026-10-03"), flat(2, "Amara", "Fennwhistle", when="2026-10-01"),
                 flat(3, "Amara", "Fennwhistle", when="2026-10-02")]
        groups, _, _ = self.decide(three, backfill={cid(1)})
        self.assertEqual((groups[0]["kept"], groups[0]["why_kept"]), (cid(1), "the back-fill's contact"))
        self.assertEqual(groups[0]["merged"], [cid(2), cid(3)])
        groups, _, _ = self.decide(three)
        self.assertEqual((groups[0]["kept"], groups[0]["why_kept"]), (cid(2), "the earliest created"))
        tie = [flat(9, "Amara", "Fennwhistle", when="2026-10-01"), flat(5, "Amara", "Fennwhistle", when="2026-10-01")]
        groups, _, _ = self.decide(tie)
        self.assertEqual(groups[0]["kept"], cid(5))                     # same time: the lowest id
        groups, _, needs = self.decide(three, backfill={cid(1), cid(3)})
        self.assertEqual((groups, needs[0]["reasons"]), ([], ["two_backfill_contacts"]))

    def test_merges_go_in_calls_of_at_most_two(self):
        four = [flat(n, "Amara", "Fennwhistle", when=f"2026-10-0{n}") for n in (1, 2, 3, 4)]
        groups, _, _ = self.decide(four)
        self.assertEqual(groups[0]["chunks"], [[cid(2), cid(3)], [cid(4)]])

    def test_two_copies_with_a_row_on_one_date_go_to_a_person(self):
        pair = [flat(1, "Amara", "Fennwhistle", when="2026-10-01"), flat(2, "Amara", "Fennwhistle", when="2026-10-02")]
        rows = {cid(1): [[row_id(1), "2026-10-05"]], cid(2): [[row_id(2), "2026-10-05"]]}
        groups, _, needs = self.decide(pair, rows)
        self.assertEqual((groups, needs[0]["reasons"]), ([], ["same_date"]))
        rows[cid(2)] = [[row_id(2), "2026-10-06"]]
        groups, _, needs = self.decide(pair, rows)
        self.assertEqual((len(groups), needs), (1, []))

    def test_copies_that_differ_in_more_than_whitespace_go_to_a_person(self):
        pair = [flat(1, "Amara", "Fennwhistle", when="2026-10-01"), flat(2, "amara", "Fennwhistle", when="2026-10-02")]
        _, _, needs = self.decide(pair)
        self.assertIn("names_differ", needs[0]["reasons"])
        pair = [flat(1, "Amara", "Fennwhistle", when="2026-10-01"),
                flat(2, "Amara", "Fennwhistle", when="2026-10-02", by=OTHER_USER)]
        _, _, needs = self.decide(pair)
        self.assertEqual(needs[0]["reasons"], ["fields_differ"])

    def test_renames(self):
        lone = [flat(6, "Chiara", "Ostrivane  Pellucidor")]
        _, renames, needs = self.decide(lone)
        self.assertEqual(needs, [])
        self.assertEqual(renames, [{"contact_id": cid(6), "account_id": SUN, "fields": ["LastName"], "in_group": False,
                                    "new_name_sha256": sd.name_hash("Chiara Ostrivane Pellucidor")}])
        self.write_roster(sunrise=("Dalia Thornquibble",))
        _, renames, needs = self.decide(lone)
        self.assertEqual((renames, needs[0]["reasons"]), ([], ["not_one_roster_girl"]))
        # a twin appeared: merged into the older (odd) contact, which is then renamed
        self.write_roster()
        twin = lone + [flat(9, "Chiara", "Ostrivane Pellucidor", when="2026-10-05")]
        groups, renames, needs = self.decide(twin)
        self.assertEqual(needs, [])
        self.assertEqual((groups[0]["kept"], groups[0]["kind"], groups[0]["merged"]), (cid(6), "normalized", [cid(9)]))
        self.assertEqual([(r["contact_id"], r["in_group"]) for r in renames], [(cid(6), True)])
        # the newer twin is the odd one: merged away, nothing to rename
        twin = [flat(6, "Chiara", "Ostrivane Pellucidor", when="2026-09-01"),
                flat(9, "Chiara", "Ostrivane  Pellucidor", when="2026-10-05")]
        groups, renames, _ = self.decide(twin)
        self.assertEqual((groups[0]["kept"], renames), (cid(6), []))
        # both copies stored with the same odd spelling: compared normalized, the kept one renamed
        both = [flat(6, "Chiara", "Ostrivane  Pellucidor", when="2026-09-01"),
                flat(9, "Chiara", "Ostrivane  Pellucidor", when="2026-10-05")]
        groups, renames, needs = self.decide(both)
        self.assertEqual((groups[0]["kind"], [r["contact_id"] for r in renames], needs), ("normalized", [cid(6)], []))
        plain = [flat(1, "Amara", "Fennwhistle", when="2026-10-01"), flat(2, "Amara", "Fennwhistle", when="2026-10-02")]
        self.assertEqual(self.decide(plain)[0][0]["kind"], "identical")


# ---- the Apex and what is printed of a run ------------------------------------------------------------
class SfDupesApex(Harness):
    def test_the_apex_holds_ids_only_and_never_catches(self):
        self.world()
        self.make_plan()
        plan = sd.load_plan(self.plan_path())
        calls = sd.parts_of(plan, SUN, None, set())[0]
        self.assertEqual(calls, [(cid(1), [cid(2), cid(3)]), (cid(4), [cid(5)])])
        for rehearse in (False, True):
            text = sd.apex_text(plan, SUN, calls, set(), rehearse, 1, 1, "2026-10-07T12:00:00Z")
            with self.subTest(rehearse=rehearse):
                self.assert_no_names(text)
                self.assertNotIn("catch", text.lower())
                self.assertNotRegex(text, r"\btry\b")
                self.assertIn("same(c.Name, k.Name)", text)
                self.assertIn("a.equals(b)", text)                   # String.equals: case-sensitive
                self.assertNotRegex(text, r"\.Name == ")
                self.assertIn(f"Database.merge(new Contact(Id = '{cid(1)}'), new List<Id>{{(Id) '{cid(2)}', "
                              f"(Id) '{cid(3)}'}}, true)", text)
                self.assertIn("System.assertEquals(7, participantsBefore", text)
                self.assertIn("System.assertEquals(5, rowsBefore", text)
                self.assertIn("'DIAG|ok|' + acc", text)
                self.assertIn("LoggingLevel.ERROR, 'DIAG|limits|queries=", text)
                for m in re.finditer(r"new List<Id>\{([^}]*)\}", text):
                    self.assertLessEqual(len(re.findall(r"'(\w+)'", m.group(1))), 2)
                ids = set(re.findall(r"'([A-Za-z0-9]{18})'", text))
                self.assertEqual(ids, {SUN, cid(1), cid(2), cid(3), cid(4), cid(5)})
                if rehearse:
                    self.assertTrue(text.rstrip().endswith(f"throw new RehearsalEndException('{sd.MARKER}');"))
                    self.assertIn("class RehearsalEndException extends Exception {}", text)
                else:
                    self.assertNotIn("RehearsalEnd", text)
                    self.assertNotIn("throw", text)

    def test_the_cli_answer_is_read_from_a_file_not_a_pipe(self):
        # through a pipe the CLI cut an 11-merge answer at 65,536 bytes (2026-10-07): it now writes a file
        big = json.dumps(cli_answer(False, {"success": False, "compiled": True, "line": 1, "column": 1,
                                            "exceptionMessage": f"RehearsalEndException: {sd.MARKER}",
                                            "logs": as_salesforce_logs([f"1 (1)|USER_DEBUG|[9]|ERROR|DIAG|ok|{SUN}"]
                                                                       + ["1 (1)|LIMIT_USAGE|x" * 10] * 4000)}))
        self.assertGreater(len(big), 70000)
        seen = {}

        def cli(argv, stdout=None, **kwargs):
            seen.update(kwargs, pipe=stdout is None or kwargs.get("capture_output"))
            stdout.write(big)
            return types.SimpleNamespace(returncode=1, stdout=None)
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "answer.json")
            org = types.SimpleNamespace(alias="glow", run=cli)
            answer, raw = sd.run_apex(org, os.path.join(tmp, "x.apex"), out)
            self.assertFalse(seen["pipe"])
            self.assertEqual(os.stat(out).st_mode & 0o777, 0o600)
            self.assertEqual(sd.judge(answer, SUN, True)[0], True)

            def cut(argv, stdout=None, **_):
                stdout.write(big[:65536])
                return types.SimpleNamespace(returncode=1, stdout=None)
            org.run = cut
            self.assertIsNone(sd.run_apex(org, os.path.join(tmp, "x.apex"), out)[0])     # unreadable: never a success

    def test_only_diag_lines_of_user_debug_entries_are_shown(self):
        log = "\n".join(["67.0 APEX_CODE,FINEST",
                         "10:00:00.1 (1)|VARIABLE_ASSIGNMENT|[3]|c|{\"Name\":\"Amara Fennwhistle\"}",
                         "10:00:00.1 (1)|VARIABLE_ASSIGNMENT|[3]|s|\"DIAG|ok|Amara Fennwhistle\"",
                         "10:00:00.2 (2)|USER_DEBUG|[4]|DEBUG|Esther Umberlash",
                         "10:00:00.3 (3)|USER_DEBUG|[5]|ERROR|DIAG|merged|" + cid(1) + "|" + cid(2) + "|" + row_id(2),
                         "10:00:00.4 (4)|USER_DEBUG|[6]|ERROR|DIAG|Esther Umberlash's row",
                         "10:00:00.5 (5)|USER_DEBUG|[7]|ERROR|DIAG|ok|" + SUN,
                         "10:00:00.6 (6)|FATAL_ERROR|System.AssertException: Amara Fennwhistle"])
        lines = sd.diag_lines(log)
        hidden = "DIAG|(a line not shown: not one this tool writes)"
        self.assertEqual(lines, [f"DIAG|merged|{cid(1)}|{cid(2)}|{row_id(2)}", hidden, f"DIAG|ok|{SUN}"])
        self.assertEqual(sd.diag_lines(as_salesforce_logs(log.split("\n"))), lines)     # | written as &#124;
        for sneaky in ("DIAG|ok|Thornquibbleford", "DIAG|ok|Amara Fennwhistle", "DIAG|merged|Fennwhistlewickam|x|y",
                       f"DIAG|merged|{cid(1)}|Fennwhistlewickam|", "DIAG|limits|queries=Amara",
                       f"DIAG|ok|{SUN}|Amara", "DIAG|Esther Umberlash"):
            with self.subTest(sneaky):
                self.assertEqual(sd.diag_lines(f"1 (1)|USER_DEBUG|[1]|ERROR|{sneaky}"), [hidden])
        self.assertEqual(sd.diag_lines(f"1 (1)|USER_DEBUG|[1]|ERROR|DIAG|merged|{cid(1)}|{cid(2)},{cid(3)}|"),
                         [f"DIAG|merged|{cid(1)}|{cid(2)},{cid(3)}|"])
        self.assertEqual(sd.diag_lines("1 (1)|USER_DEBUG|[1]|ERROR|DIAG|limits|queries=9/100|dml=2/150|cpu=4/10000"),
                         ["DIAG|limits|queries=9/100|dml=2/150|cpu=4/10000"])

    def test_the_outcome_of_a_run(self):
        ok_log = f"1 (1)|USER_DEBUG|[9]|ERROR|DIAG|ok|{SUN}"

        def answer(success, message="", logs=ok_log, compiled=True):
            return {"status": 0, "result": {"success": success, "compiled": compiled, "exceptionMessage": message,
                                            "logs": logs, "line": 3, "column": 1}}

        def as_cli(success, message="", logs=ok_log, compiled=True):      # what the CLI really answers
            return cli_answer(success, {"success": success, "compiled": compiled, "exceptionMessage": message,
                                        "logs": as_salesforce_logs(logs.split("\n")), "line": 3, "column": 1})
        marker = f"RehearsalEndException: {sd.MARKER}"
        for good, rehearse, ans in (
                (True, True, answer(False, marker)),
                (True, True, answer(False, f"AnonymousBlock.RehearsalEndException: {sd.MARKER}")),
                (False, True, answer(False, marker, logs="")),                               # no DIAG|ok
                (False, True, answer(False, "RehearsalEndException: something else")),
                (False, True, answer(False, "System.LimitException: Too many SOQL queries: 101")),
                (False, True, answer(True)),                                                 # it did not throw
                (True, False, answer(True)),
                (False, False, answer(True, logs="")),
                (False, False, answer(False, marker)),
                (False, False, answer(False, "System.DmlException: DUPLICATES_DETECTED, Amara Fennwhistle")),
                # a name written in capitals, as some rosters hold them, is quoted by the error text
                (False, False, answer(False, "System.DmlException: Merge failed. first error: DUPLICATES_DETECTED, "
                                             "AMARA FENNWHISTLE looks like ZARA ZIBBLEWICK: []")),
                (False, False, answer(False, "FENNWHISTLE: UNABLE_TO_LOCK_ROW, AMARA")),
                (False, True, answer(False, marker, compiled=False)),
                (False, True, {"status": 1, "message": "no result"}),
                (True, True, as_cli(False, marker)),
                (False, True, as_cli(False, marker, logs="")),
                (False, True, as_cli(False, "System.AssertException: Assertion Failed: DIAG|fail|rows before|" + SUN)),
                (False, True, as_cli(False, marker, compiled=False)),
                (True, False, as_cli(True)),
                (False, False, as_cli(False, marker)),
                (False, True, {"status": 1, "name": "executeRuntimeFailure", "data": {"message": "no outcome"}})):
            good_said = sd.judge(ans, SUN, rehearse)
            with self.subTest(ans=str(ans)[:120], rehearse=rehearse):
                self.assertEqual(good_said[0], good)
                self.assert_no_names(good_said[1])
        said = sd.judge(answer(False, "System.AssertException: Assertion Failed: DIAG|fail|participants before|"
                                      f"{SUN}: Expected: 7, Actual: 8"), SUN, True)[1]
        self.assertIn(f"DIAG|fail|participants before|{SUN}", said)
        self.assertIn("expected 7, actual 8", said)
        self.assertIn("DUPLICATES_DETECTED", sd.judge(answer(False, "System.DmlException: DUPLICATES_DETECTED, "
                                                                    "Amara Fennwhistle"), SUN, False)[1])
        said = sd.judge(answer(False, "System.DmlException: Merge failed. first error: DUPLICATES_DETECTED, AMARA "
                                      "FENNWHISTLE; UNABLE_TO_LOCK_ROW"), SUN, False)[1]
        self.assertEqual(said, "System.DmlException; DUPLICATES_DETECTED; UNABLE_TO_LOCK_ROW")
        self.assertEqual(sd.judge(answer(False, "FENNWHISTLE: UNABLE_TO_LOCK_ROW, AMARA"), SUN, False)[1],
                         "an exception; UNABLE_TO_LOCK_ROW")


# ---- the commands on the fake org ---------------------------------------------------------------------
class SfDupesFlow(Harness):
    def test_every_command_needs_vpn_off(self):
        self.world()
        for argv in (["check"], ["plan", "--roster", self.roster], ["merge", self.plan_path(), "--apply"],
                     ["merge", self.plan_path(), "--rehearse"], ["rename", self.plan_path(), "--apply"],
                     ["cleanup", self.plan_path(), "--apply"]):
            with self.subTest(argv[0]):
                out, code = self.run_tool(*argv, vpn=False)
                self.assertIn("--vpn-off", str(code))
        self.assertEqual((self.sf.queries, self.sf.events, self.jf.calls), ([], [], []))

    def test_rehearse_and_apply_exclude_each_other(self):
        out, code = self.run_tool("merge", self.plan_path(), "--rehearse", "--apply")
        self.assertEqual(code, 2)
        self.assertIn("not allowed with argument", out)

    def test_a_fresh_checkout_without_data_gets_the_folder_made_owner_only(self):
        # the guard asked within() about a data/ that did not exist yet and refused every folder under it
        with tempfile.TemporaryDirectory() as checkout, unittest.mock.patch.object(sd, "REPO", checkout):
            ctx = sd.Ctx(types.SimpleNamespace(org="glow"), self.sf, self.jf, lambda: self.now)
            folder = os.path.join(checkout, "data", "sf_dupes_2026-10-07")
            ctx.use_folder(folder)
            self.assertEqual(ctx.folder, folder)
            self.assertEqual([stat.S_IMODE(os.stat(p).st_mode) for p in (os.path.join(checkout, "data"), folder)],
                             [0o700] * 2)
            with self.assertRaises(salesforce.Refused) as stop:
                ctx.use_folder(os.path.join(checkout, "docs"))
            self.assertIn("must be under data/", str(stop.exception))
            self.assertFalse(os.path.exists(os.path.join(checkout, "docs")))

    def test_the_plan(self):
        self.world()
        out = self.make_plan()
        self.assertIn("groups 2, extras 3, same-date 0, renames 1, needs-a-person 0", out)
        self.assertIn(f"{SUN}", out)
        self.assertEqual(stat.S_IMODE(os.stat(self.dir).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(self.plan_path()).st_mode), 0o600)
        with open(self.plan_path(), encoding="utf-8") as fh:
            text = fh.read()
        self.assert_no_names(text)
        plan = json.loads(text)
        self.assertEqual(plan["clubs"][SUN]["participants_before"], 7)
        self.assertEqual(plan["clubs"][SUN]["participants_after"], 4)
        self.assertEqual(plan["clubs"][SUN]["rows_per_date"],
                         {"2026-09-09": 1, "2026-10-01": 2, "2026-10-02": 1, "2026-10-03": 1, "2026-10-04": 1})
        self.assertNotIn(RIV, plan["clubs"])                            # a namesake in another club is no group
        g = {g["kept"]: g for g in plan["groups"]}
        self.assertEqual(g[cid(1)]["chunks"], [[cid(2), cid(3)]])
        self.assertEqual(g[cid(4)]["contacts"][cid(5)]["dup_items"], [[item_id(11), set_id(1)]])
        self.assertEqual(g[cid(1)]["contacts"][cid(2)]["affiliations"], [aff_id(2)])
        self.assertEqual(plan["renames"][0]["contact_id"], cid(6))

    def test_a_group_left_to_a_person_makes_the_plan_exit_1(self):
        self.world()
        self.sf.row(9, 2, "2026-09-09")                                 # contacts 1 and 2 on one date
        out = self.make_plan(expect=1)
        self.assertIn("same-date 1", out)
        self.assertIn(f"needs a person: group in {SUN}: {cid(1)}+{cid(2)}+{cid(3)} - same_date", out)
        self.assert_no_names(out)

    def test_the_whole_run_prints_no_name_and_leaves_one_contact_per_girl(self):
        self.world()
        self.make_plan()
        out, code = self.run_tool("merge", self.plan_path())
        self.assertEqual(code, 0, out)
        self.assertIn(f"keep {cid(1)} <- {cid(2)} + {cid(3)}", out)
        self.assertIn("merge (dry run): 1 club(s), 2 merge call(s) in 1 Apex run(s)", out)
        self.assertEqual(self.sf.events, [])                            # a dry run runs nothing
        out, code = self.run_tool("merge", self.plan_path(), "--rehearse")
        self.assertEqual(code, 0, out)
        self.assertIn(f"DIAG|ok|{SUN}", out)
        self.assertIn("rehearsal ok", out)
        self.assertIn("exactly as before the rehearsal", out)
        self.assertNotIn("DIAG|Beatrice", out)
        self.assertIn("DIAG|(a line not shown: not one this tool writes)", out)
        saved = self.rollback()                         # a rehearsal saves the rollback data too, and no merge
        self.assertEqual((sorted(saved["contacts"]), saved["merges"]), ([cid(2), cid(3), cid(5)], []))
        self.assertTrue(all(not self.sf.contacts[cid(n)]["IsDeleted"] for n in (2, 3, 5)))
        out, code = self.run_tool("rename", self.plan_path())
        self.assertEqual(code, 0, out)
        self.assertIn(f"would rename {cid(6)} ({SUN}): LastName", out)
        out, code = self.run_tool("rename", self.plan_path(), "--apply", "--roster", self.roster)
        self.assertEqual(code, 0, out)
        self.assertIn(f"{cid(6)}: OK", out)
        self.assertEqual(self.sf.contacts[cid(6)]["Name"], "Chiara Ostrivane Pellucidor")
        self.assertEqual(self.rollback()["renames"][cid(6)]["old"], {"LastName": "Ostrivane  Pellucidor"})
        out, code = self.run_tool("merge", self.plan_path(), "--apply")
        self.assertEqual(code, 0, out)
        self.assertIn("read back", out)
        for n, kept in ((2, 1), (3, 1), (5, 4)):
            self.assertEqual((self.sf.contacts[cid(n)]["IsDeleted"], self.sf.contacts[cid(n)]["MasterRecordId"]),
                             (True, cid(kept)))
        self.assertEqual(sorted(r["Id"] for r in self.sf.rows.values() if r["Contact__c"] == cid(1)),
                         [row_id(1), row_id(2), row_id(3)])
        self.assertEqual(len(self.sf.participants(SUN)), 4)
        merges = self.rollback()["merges"]
        self.assertEqual([(m["status"], m["merged"]) for m in merges], [("done", [cid(2), cid(3), cid(5)])])
        self.assertEqual(len(merges[0]["results"]), 2)
        out, code = self.run_tool("merge", self.plan_path(), "--apply")
        self.assertEqual(code, 0, out)
        self.assertIn("nothing left to merge", out)
        out, code = self.run_tool("cleanup", self.plan_path(), "--dup-sets")
        self.assertEqual(code, 0, out)
        self.assertIn(f"would delete npe5__Affiliation__c {aff_id(2)}", out)
        self.assertEqual(len(self.sf.affs), 8)
        out, code = self.run_tool("cleanup", self.plan_path(), "--dup-sets", "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(sorted(a["Id"] for a in self.sf.affs.values() if a["npe5__Organization__c"] == SUN),
                         [aff_id(1), aff_id(4), aff_id(6), aff_id(7)])
        self.assertEqual(self.sf.sets, {})
        deleted = self.rollback()["deleted"]
        self.assertEqual(sorted(d["id"] for d in deleted), sorted([aff_id(2), aff_id(3), aff_id(5), set_id(1)]))
        self.assertTrue(all(d["status"] == "deleted" and d["record"] for d in deleted))
        out, code = self.run_tool("check")
        self.assertEqual(code, 0, out)
        self.assertIn("check: 0 finding(s) - clean", out)
        for name in os.listdir(self.dir):
            path = os.path.join(self.dir, name)
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o700 if os.path.isdir(path) else 0o600, name)
            for inner in (os.listdir(path) if os.path.isdir(path) else []):
                self.assertEqual(stat.S_IMODE(os.stat(os.path.join(path, inner)).st_mode), 0o600, inner)
        for apex in os.listdir(os.path.join(self.dir, "apex")):
            with open(os.path.join(self.dir, "apex", apex), encoding="utf-8") as fh:
                self.assert_no_names(fh.read())
        self.assert_no_names("\n".join(self.printed))

    def test_a_twin_of_an_odd_name_is_merged_after_or_before_the_rename(self):
        for rename_first in (True, False):
            with self.subTest(rename_first=rename_first):
                self.sf = FakeSF()
                self.world()
                self.sf.contact(9, "Chiara", "Ostrivane Pellucidor", SUN, "2026-10-05")    # her next tick made a twin
                self.sf.row(9, 9, "2026-10-05")
                out = self.make_plan()
                self.assertIn("groups 3, extras 4, same-date 0, renames 1, needs-a-person 0", out)
                self.assertIn(f"rename {cid(6)} ({SUN}): LastName - the kept contact of a group", out)
                steps = [("rename", self.plan_path(), "--apply", "--roster", self.roster),
                         ("merge", self.plan_path(), "--apply")]
                for argv in (steps if rename_first else steps[::-1]):
                    out, code = self.run_tool(*argv)
                    self.assertEqual(code, 0, out)
                self.assertEqual(self.sf.contacts[cid(9)]["MasterRecordId"], cid(6))
                self.assertEqual(self.sf.contacts[cid(6)]["Name"], "Chiara Ostrivane Pellucidor")
                self.assertEqual(self.rows_of(6), [row_id(9)])
                out, code = self.run_tool("check")
                self.assertEqual(code, 0, out)
                os.remove(os.path.join(self.dir, "merge_rollback.json"))

    def rows_of(self, n):
        return sorted(r["Id"] for r in self.sf.rows.values() if r["Contact__c"] == cid(n))

    def test_a_name_changed_since_the_plan_fails_the_apex_and_nothing_changes(self):
        self.world()
        self.make_plan()
        self.sf.contacts[cid(5)].update(FirstName="BEATRICE", Name="BEATRICE Marrowgate")   # same key: no drift
        out, code = self.run_tool("merge", self.plan_path(), "--apply")
        self.assertIn(f"DIAG|fail|name|{cid(5)}", out)
        self.assertIn("Salesforce rolled it back", str(code))
        self.assertFalse(any(c["IsDeleted"] for c in self.sf.contacts.values()))
        self.assert_no_names(out)

    def test_a_club_in_several_runs(self):
        self.world()
        self.make_plan()
        out, code = self.run_tool("merge", self.plan_path(), "--per-run", "1", "--rehearse")
        self.assertEqual(code, 0, out)
        self.assertEqual([e[1] for e in self.sf.events], [f"{SUN}_1.apex", f"{SUN}_2.apex"])
        self.sf.events = []
        out, code = self.run_tool("merge", self.plan_path(), "--per-run", "1", "--apply", "--club", SUN)
        self.assertEqual(code, 0, out)
        self.assertEqual([e[1] for e in self.sf.events], [f"{SUN}_1.apex", f"{SUN}_2.apex"])
        self.assertEqual([m["status"] for m in self.rollback()["merges"]], ["done", "done"])
        self.assertEqual((self.rows_of(1), self.rows_of(4)), ([row_id(1), row_id(2), row_id(3)], [row_id(4), row_id(5)]))
        self.assertEqual(len(self.sf.participants(SUN)), 4)
        out, code = self.run_tool("merge", self.plan_path(), "--club", RIV)
        self.assertIn("the plan has no merge for that account", str(code))

    def test_the_rollback_file_is_written_before_the_first_write(self):
        self.world()
        self.make_plan()
        seen = []

        def look(sf):
            data = self.rollback()
            seen.append(data)
            return sorted(data["contacts"])
        self.sf.on_write = look
        out, code = self.run_tool("merge", self.plan_path(), "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.sf.events[0][:2], ("apex", f"{SUN}_1.apex"))
        self.assertEqual(self.sf.events[0][2], [cid(2), cid(3), cid(5)])
        saved = seen[0]["contacts"]
        self.assertEqual(saved[cid(2)]["kept"], cid(1))
        self.assertEqual(saved[cid(5)]["why_kept"], "the earliest created")
        self.assertEqual(saved[cid(2)]["fields"]["LastName"], "Fennwhistle")
        self.assertEqual(set(saved[cid(2)]["fields"]), {"AccountId", "Contact_Role__c", "Description", "Email",
                                                         "FirstName", "LastName", "npsp__Primary_Affiliation__c"})
        self.assertEqual([r["Id"] for r in saved[cid(2)]["rows"]], [row_id(2)])
        self.assertEqual(set(saved[cid(2)]["rows"][0]), {"Id", "Contact__c", "Account__c", "Attendance_Date__c",
                                                          "Attendance_Batch__c", "Module__c"})
        self.assertEqual([a["Id"] for a in saved[cid(3)]["affiliations"]], [aff_id(3)])
        self.assertEqual(saved[cid(5)]["dup_items"], [{"Id": item_id(11), "RecordId": cid(5),
                                                       "DuplicateRecordSetId": set_id(1)}])
        self.assertEqual(seen[0]["merges"][0]["status"], "running")

    def test_a_change_since_the_plan_stops_the_merge(self):
        for what, change in (("a new member", lambda sf: sf.contact(9, "Amara", "Fennwhistle", SUN, "2026-10-06")),
                             ("a new row", lambda sf: sf.row(9, 2, "2026-10-06")),
                             ("a moved contact", lambda sf: sf.contacts[cid(3)].update(AccountId=RIV)),
                             ("a new girl in the club", lambda sf: sf.contact(9, "Esther", "Umberlash", SUN))):
            with self.subTest(what):
                self.sf = FakeSF()
                self.world()
                self.make_plan()
                change(self.sf)
                for mode in ("--apply", "--rehearse"):
                    out, code = self.run_tool("merge", self.plan_path(), mode)
                    self.assertIn("no longer as planned", str(code))
                    self.assert_no_names(out)
                self.assertEqual(self.sf.events, [])
                self.assertFalse(os.path.exists(os.path.join(self.dir, "merge_rollback.json")))

    def test_no_write_while_a_submission_may_be_in_flight_or_npsp_runs(self):
        self.world()
        self.make_plan()
        self.jf.latest[forms.REGIONALS["Asia"]] = "2026-10-07 07:55:00"       # 11:55 UTC, 5 minutes ago
        for argv in (["merge", self.plan_path(), "--apply"], ["merge", self.plan_path(), "--rehearse"],
                     ["rename", self.plan_path(), "--apply", "--roster", self.roster],
                     ["cleanup", self.plan_path(), "--apply"]):
            out, code = self.run_tool(*argv)
            if argv[0] == "cleanup":
                self.assertEqual(code, 0, out)                          # nothing to delete before the merges
                continue
            self.assertIn("Asia form 5 minute(s) ago", str(code))
        self.assertEqual(self.sf.events, [])
        self.jf.latest[forms.REGIONALS["Asia"]] = "2026-10-07 07:49:00"       # 11 minutes ago: quiet
        for hour, minute, refused in ((20, 30, True), (20, 45, True), (21, 29, True), (20, 29, False), (21, 30, False)):
            with self.subTest(f"{hour}:{minute}"):
                self.now = datetime.datetime(2026, 10, 7, hour, minute, tzinfo=UTC)
                self.jf.latest = {k: "2026-10-07 07:00:00" for k in self.jf.latest}
                out, code = self.run_tool("rename", self.plan_path(), "--apply", "--roster", self.roster)
                self.assertEqual("20:30 and 21:30" in str(code), refused, (out, code))
        self.now, self.sf.events = datetime.datetime(2026, 10, 7, 20, 40, tzinfo=UTC), []
        out, code = self.run_tool("merge", self.plan_path(), "--rehearse")      # its DML locks and runs triggers too
        self.assertIn("20:30 and 21:30", str(code))
        self.assertEqual(self.sf.events, [])
        self.now = NOW
        self.jf.latest = {k: "2026-10-07 07:49:00" for k in self.jf.latest}
        out, code = self.run_tool("merge", self.plan_path(), "--rehearse")
        self.assertEqual(code, 0, out)
        self.assertIn("0 submission(s) on the regional forms, 0 new batch(es)", out)      # counted after it too

    def test_a_failed_run_stops_everything_and_prints_no_name(self):
        self.world()
        self.sf.contact(9, "Amara", "Fennwhistle", RIV, "2026-10-05")
        self.make_plan()
        plan = sd.load_plan(self.plan_path())
        self.assertEqual(sorted(plan["clubs"]), [RIV, SUN])
        for mode in ("other", "unreadable"):
            with self.subTest(mode):
                self.sf.apex_mode, self.sf.events = mode, []
                out, code = self.run_tool("merge", self.plan_path(), "--apply")
                self.assertEqual(len(self.sf.events), 1)                # the next club is never run
                self.assertEqual(self.sf.events[0][1], f"{RIV}_1.apex")
                self.assert_no_names(out)
                if mode == "other":
                    self.assertIn("Salesforce rolled it back", str(code))
                    self.assertIn("DUPLICATES_DETECTED", out)
                    self.assertEqual(self.rollback()["merges"][-1]["status"], "not_applied")
                else:
                    self.assertIn("THE OUTCOME IS UNKNOWN", str(code))
                    self.assertEqual(self.rollback()["merges"][-1]["status"], "unknown")
        self.sf.apex_mode = "ok"
        out, code = self.run_tool("merge", self.plan_path(), "--apply")           # settles the unknown run first
        self.assertEqual(code, 0, out)
        self.assertIn("settled an earlier run", out)
        self.assertEqual([m["status"] for m in self.rollback()["merges"]], ["not_applied", "not_applied", "done", "done"])
        self.assertTrue(self.sf.contacts[cid(9)]["IsDeleted"])

    def test_a_failed_rehearsal_and_a_rehearsal_check_that_fails(self):
        self.world()
        self.make_plan()
        self.sf.apex_mode = "other"
        out, code = self.run_tool("merge", self.plan_path(), "--rehearse")
        self.assertIn("the rehearsal failed", str(code))
        self.assert_no_names(out + str(code))
        self.sf.apex_mode = "leaky"
        out, code = self.run_tool("merge", self.plan_path(), "--rehearse")
        self.assertIn("not as before the rehearsal - LOOK AT IT NOW", str(code))
        self.sf = FakeSF()
        self.world()
        self.sf.contacts[cid(7)]["IsDeleted"] = True                    # a girl gone since the plan: drift
        out, code = self.run_tool("merge", self.plan_path(), "--rehearse")
        self.assertIn("no longer as planned", str(code))

    def test_more_submissions_than_batches_is_attention(self):
        self.world()
        self.make_plan()
        africa = forms.REGIONALS["Africa"]
        self.sf.on_write = lambda sf: self.jf.subs[africa].append("2026-10-07 08:00:30")
        out, code = self.run_tool("merge", self.plan_path(), "--apply")
        self.assertEqual(code, 2, out)
        self.assertIn("1 submission(s) on the regional forms, 0 new batch(es)", out)
        self.assertIn("ATTENTION", out)
        self.sf.batches.append({"Id": "a1l000000000000009", "Name": "BATCH-000009", "Contact_IDs__c": "x",
                                "CreatedDate": created("2026-10-07", 12)})
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sd.window_count(types.SimpleNamespace(jotform=lambda: self.jf), self.sf, NOW), 0)

    def test_the_submission_count_checks_the_order_and_counts_every_form(self):
        ctx = types.SimpleNamespace(jotform=lambda: self.jf)
        # a Latin America submission with its batch cannot hide a missing Africa one
        self.jf.subs[forms.REGIONALS["Latin America"]].append("2026-10-07 08:00:20")
        self.jf.subs[forms.REGIONALS["Africa"]].append("2026-10-07 08:00:30")
        self.sf.batches.append({"Id": "a1l000000000000009", "Name": "BATCH-000009", "Contact_IDs__c": "x",
                                "CreatedDate": created("2026-10-07", 12)})
        with contextlib.redirect_stdout(io.StringIO()) as shown:
            self.assertEqual(sd.window_count(ctx, self.sf, NOW), 2)
        self.assertIn("2 submission(s) on the regional forms, 1 new batch(es)", shown.getvalue())
        self.assertEqual(sorted({p.split("/")[2] for p, _ in self.jf.calls}), sorted(forms.REGIONALS.values()))
        # a list that is not newest first would end the count on its first page: refused, never 0
        self.jf.oldest_first = True
        with self.assertRaises(salesforce.Refused) as stop:
            sd.submissions_since(self.jf, "Africa", NOW - datetime.timedelta(minutes=1))
        self.assertIn("did not come newest first", str(stop.exception))
        self.world()
        self.make_plan()
        out, code = self.run_tool("merge", self.plan_path(), "--apply")
        self.assertEqual(code, 2, out)
        self.assertIn("could not be made", out)
        self.assertIn("compare them by hand", out)

        class Pages:                                # a submission arrived between the two page reads
            submissions = Client.submissions

            def __init__(self, pages):
                self.pages = pages

            def get(self, path, **params):
                assert "orderby" not in params
                return self.pages[params["offset"] // params["limit"]]
        page1 = [{"id": "s4", "created_at": "2026-10-07 08:04:00", "status": "ACTIVE"},
                 {"id": "s3", "created_at": "2026-10-07 08:03:00", "status": "DELETED"}]
        page2 = [{"id": "s3", "created_at": "2026-10-07 08:03:00", "status": "DELETED"},
                 {"id": "s2", "created_at": "2026-10-07 08:02:00", "status": "ACTIVE"}]
        page3 = [{"id": "s1", "created_at": "2026-10-07 07:00:00", "status": "ACTIVE"}]
        with unittest.mock.patch.object(sd, "SUBMISSION_PAGE", 2):
            self.assertEqual(sd.submissions_since(Pages([page1, page2, page3]), "Africa", NOW), 2)
        # every page newer than the run's start, up to the cap: refused, never a short count
        newer = [[{"id": f"s{n}", "created_at": f"2026-10-07 08:{59 - n:02d}:00", "status": "ACTIVE"}] for n in range(3)]
        with unittest.mock.patch.object(sd, "SUBMISSION_PAGE", 1), unittest.mock.patch.object(sd, "SUBMISSION_PAGES", 2), \
                self.assertRaises(salesforce.Refused) as stop:
            sd.submissions_since(Pages(newer), "Africa", NOW)
        self.assertIn("more than 2 submissions on the Africa form", str(stop.exception))
        with unittest.mock.patch.object(sd, "SUBMISSION_PAGE", 1), unittest.mock.patch.object(sd, "SUBMISSION_PAGES", 4):
            self.assertEqual(sd.submissions_since(Pages(newer + [[]]), "Africa", NOW), 3)
        # an answer without ids is Jotform's, not a count
        with self.assertRaises(JotformError) as stop:
            sd.submissions_since(Pages([[{"created_at": "2026-10-07 08:04:00"}]]), "Africa", NOW)
        self.assertIn("the Africa form: the submissions answer is not a list of submissions with ids", str(stop.exception))

    def test_an_unknown_run_is_settled_only_on_what_salesforce_shows(self):
        os.makedirs(self.dir)
        self.sf.contact(1, "Esther", "Umberlash")
        self.sf.contact(98, "Esther", "Umberlash")

        def settle(missing=False, **state):
            rb = sd.Rollback(self.dir)
            merged = [cid(98)] + ([cid(97)] if missing else [])
            rb.data["merges"] = [{"club": SUN, "part": 1, "calls": [[cid(1), merged]], "merged": merged,
                                  "status": "unknown"}]
            self.sf.contacts[cid(98)].update(state)
            with contextlib.redirect_stdout(io.StringIO()):
                sd.settle(self.sf, rb)
            return rb.data["merges"][0]["status"]
        self.assertEqual(settle(), "not_applied")
        self.assertEqual(settle(IsDeleted=True, MasterRecordId=cid(1)), "done")
        for what, kwargs, said in (
                ("purged from the Recycle Bin", dict(missing=True), "cannot tell whether that run merged"),
                ("deleted, but not by this merge", dict(IsDeleted=True, MasterRecordId=None), "not merged into")):
            with self.subTest(what):
                with self.assertRaises(salesforce.Refused) as stop:
                    settle(**kwargs)
                self.assertIn(said, str(stop.exception))

    def test_rename_and_cleanup_save_each_record_before_its_write(self):
        self.world()
        self.make_plan()
        self.sf.on_write = lambda sf: (self.rollback()["renames"].get(cid(6)) or {}).get("old")
        out, code = self.run_tool("rename", self.plan_path(), "--apply", "--roster", self.roster)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.sf.events, [("update", cid(6), {"LastName": "Ostrivane  Pellucidor"})])
        self.sf.on_write, self.sf.events = None, []
        out, code = self.run_tool("merge", self.plan_path(), "--apply")
        self.assertEqual(code, 0, out)
        self.sf.on_write, self.sf.events = lambda sf: {d["id"]: (d["status"], bool(d["record"]))
                                                       for d in self.rollback()["deleted"]}, []
        out, code = self.run_tool("cleanup", self.plan_path(), "--dup-sets", "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual([e[1] for e in self.sf.events], [aff_id(2), aff_id(3), aff_id(5), set_id(1)])
        for _, rid, saved in self.sf.events:
            self.assertEqual(saved.get(rid), ("saved", True), rid)

    def test_cleanup_keeps_a_primary_affiliation_and_watches_her_primary_affiliation(self):
        sf = self.sf
        sf.contact(1, "Amara", "Fennwhistle", SUN, "2026-09-02", primary=True)
        sf.contact(2, "Amara", "Fennwhistle", SUN, "2026-10-03", primary=True)   # NPSP flagged it Primary too
        sf.contact(3, "Amara", "Fennwhistle", SUN, "2026-10-04")
        sf.contact(4, "Beatrice", "Marrowgate", SUN, "2026-10-01")
        sf.contact(5, "Beatrice", "Marrowgate", SUN, "2026-10-02", primary=True)
        self.make_plan()
        out, code = self.run_tool("merge", self.plan_path(), "--apply")
        self.assertEqual(code, 0, out)
        out, code = self.run_tool("cleanup", self.plan_path())
        self.assertEqual(code, 0, out)
        self.assertIn(f"leave npe5__Affiliation__c {aff_id(2)} (kept contact {cid(1)}: a further Primary", out)
        self.assertIn(f"would delete npe5__Affiliation__c {aff_id(3)} (kept contact {cid(1)} keeps {aff_id(1)})", out)
        self.assertIn(f"would delete npe5__Affiliation__c {aff_id(4)} (kept contact {cid(4)} keeps {aff_id(5)})", out)
        out, code = self.run_tool("cleanup", self.plan_path(), "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(sorted(sf.affs), [aff_id(1), aff_id(2), aff_id(5)])
        self.assertEqual((sf.contacts[cid(1)]["npsp__Primary_Affiliation__c"],
                          sf.contacts[cid(4)]["npsp__Primary_Affiliation__c"]), (SUN, None))
        deleted = {d["id"]: d for d in self.rollback()["deleted"]}
        self.assertEqual(deleted[aff_id(3)]["contact_primary_before"],
                         {"contact": cid(1), "npsp__Primary_Affiliation__c": SUN})
        # should NPSP blank it on another delete as well, the cleanup stops right there
        self.sf, self.printed = FakeSF(), []
        self.world()
        self.sf.contacts[cid(1)]["npsp__Primary_Affiliation__c"] = SUN
        self.sf.blank_on_delete = True
        os.remove(os.path.join(self.dir, "merge_rollback.json"))
        self.make_plan()
        out, code = self.run_tool("merge", self.plan_path(), "--apply")
        self.assertEqual(code, 0, out)
        out, code = self.run_tool("cleanup", self.plan_path(), "--apply")
        self.assertIn(f"kept contact {cid(1)}: its Primary Affiliation changed", str(code))
        self.assertIn(f"it was {SUN}, it is blank", str(code))
        self.assertEqual([e[1] for e in self.sf.events if e[0] == "delete"], [aff_id(2)])
        entry = self.rollback()["deleted"][-1]
        self.assertEqual((entry["id"], entry["status"], entry["contact_primary_after"]), (aff_id(2), "CHECK", None))

    def test_a_failed_delete_shows_error_codes_only(self):
        self.world()
        self.make_plan()
        out, code = self.run_tool("merge", self.plan_path(), "--apply")
        self.assertEqual(code, 0, out)
        self.sf.delete_answer = (400, [{"errorCode": "DELETE_FAILED",
                                        "message": "AMARA FENNWHISTLE is still linked to DALIA THORNQUIBBLE"}])
        out, code = self.run_tool("cleanup", self.plan_path(), "--apply")
        self.assertIn(f"npe5__Affiliation__c {aff_id(2)}: not deleted as planned (HTTP 400 DELETE_FAILED)", str(code))
        self.assertEqual(self.rollback()["deleted"][-1]["status"], "CHECK")
        self.assert_no_names(out)

    def test_the_renames_are_checked_again_before_writing(self):
        self.world()
        self.make_plan()
        self.sf.contacts[cid(6)].update(LastName="Ostrivane   Pellucidorr", Name="Chiara Ostrivane   Pellucidorr")
        out, code = self.run_tool("rename", self.plan_path(), "--apply", "--roster", self.roster)
        self.assertIn("no longer as planned", str(code))
        self.assertEqual(self.sf.events, [])
        out, code = self.run_tool("rename", self.plan_path(), "--apply")
        self.assertIn("--roster", str(code))

    def test_cleanup_refuses_an_affiliation_the_plan_does_not_know(self):
        self.world()
        self.make_plan()
        out, code = self.run_tool("merge", self.plan_path(), "--apply")
        self.assertEqual(code, 0, out)
        self.sf.aff(99, 1, SUN, "2026-10-06")
        self.sf.events = []
        out, code = self.run_tool("cleanup", self.plan_path(), "--apply")
        self.assertIn(f"affiliation {aff_id(99)} is not one the plan recorded", str(code))
        self.assertEqual(self.sf.events, [])

    def test_the_check_reports_every_kind_of_finding_by_id(self):
        self.world()
        self.sf.contact(10, "Esther", "Umberlash", SUN, "2026-09-05")
        self.sf.contact(11, "Esther", "Umberlash", RIV, "2026-09-05")
        self.write_roster(extra=[("Second Partner", "River Club", "Esther Umberlash", "active")])
        self.sf.batches += [{"Id": "a1l000000000000002", "Name": "BATCH-000002", "CreatedDate": created("2026-10-03"),
                             "Contact_IDs__c": "Amara  Fennwhistle, Dalia Thornquibble"},
                            {"Id": "a1l000000000000003", "Name": "BATCH-000003", "CreatedDate": created("2026-10-04"),
                             "Contact_IDs__c": "Amara Fennwhistle, Dalia Thornquibble"},
                            {"Id": "a1l000000000000004", "Name": "BATCH-000004", "CreatedDate": created("2026-09-28"),
                             "Contact_IDs__c": "Amara\xa0Fennwhistle"}]
        out, code = self.run_tool("check", "--roster", self.roster)
        self.assertEqual(code, 1, out)
        self.assertIn("(a) same name twice in one club: 2 group(s), 3 extra contact(s) in 1 club(s)", out)
        self.assertIn(f"{SUN}: 2 group(s), 3 extra - {cid(1)}+{cid(2)}+{cid(3)}; {cid(4)}+{cid(5)}", out)
        self.assertIn(f"(b) stored names with odd whitespace or invisible characters: 1\n  {SUN}: {cid(6)} (Name, LastName)",
                      out)
        self.assertIn("(c) batches since 2026-10-01 whose name list has odd whitespace: 1 of 2 - BATCH-000002", out)
        self.assertIn("(d) names in two or more clubs that the Roster does not have in each: 1", out)
        self.assertIn(f"{cid(11)} ({RIV}), {cid(10)} ({SUN}) - not on the Roster in {SUN}", out)
        self.assert_no_names(out)
        out, code = self.run_tool("check", "--since", "2026-09-01")
        self.assertIn("whose name list has odd whitespace: 2 of 3", out)
        self.assertIn("(d) names in two or more clubs: not checked (needs --roster)", out)


if __name__ == "__main__":
    unittest.main()
