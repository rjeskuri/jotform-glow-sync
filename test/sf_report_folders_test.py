#!/usr/bin/env python3
"""
Offline tests for tools/sf_report_folders.py (ticket #71, epic #68; found by `make py`'s unittest
discovery).

The tool copies a report or a dashboard into the "Decommissioned" folder of its kind, moves (and,
for free, relabels) reports keeping their Ids, lists what a folder holds, and undoes its own moves
from its ledger. It never deletes. Everything here is fictional: the ids are new random ones per
fake org, so a tool that hard-codes one cannot pass.

The fake org (ReportOrg) is Salesforce as far as this tool may see it, after the API proof of #69
(docs/plans/2026-10-21-sf-reporting-inventory.md, "API proof"):

- query(soql) / query_all(soql): plain SOQL (SELECT fields FROM object [WHERE ...] with
  AND/OR/NOT/parentheses, =, !=, <, >, IN, NOT IN, LIKE; ORDER BY and LIMIT accepted and ignored)
  over Folder (Id, Name, DeveloperName, Type), Report (Id, DeveloperName, Name, OwnerId - its
  folder's id - FolderName, LastRunDate), Dashboard (Id, DeveloperName, Title, FolderId,
  FolderName, Type) and DashboardComponent (Id, DashboardId, CustomReportId, and the relationship
  Dashboard.*). Any other object is an AssertionError (recorded first).
- call(method, path, body) -> (status, answer), paths under /services/data/v67.0:
  * POST analytics/reports?cloneId=<id>, body {"reportMetadata": {"name", "folderId",
    ["description"]}} -> 200, {"reportMetadata": {"id": <new id>, "name", "folderId"}, ...};
    the clone lands in folderId with that name (or the source's) and description. A name is
    stored with its surrounding whitespace stripped (clone and PATCH), as Salesforce stores it.
  * POST analytics/dashboards?cloneId=<id>, body {"folderId": ...} -> 200, {"id": <new id>,
    "dashboardMetadata": {"id": <new id>, ...}, ...}; any other key in the body is refused
    400 JSON_PARSER_ERROR, as the API refused a dashboard's name and description.
  * PATCH analytics/reports/<id>, body {"reportMetadata": {...}}: folderId, name, description
    change; 200 with the report's metadata. drift[id] = "folder" | "name" makes the PATCH answer
    200 while that field stays as it was (a failed read-back); drift[id] = "echo" answers 200 with
    the values asked for while nothing is stored (only a SOQL read-back sees it); refuse_patch
    makes it 400. misplace = True: a clone answers 200 with the folder asked for, but lands in its
    source's folder (only a SOQL read-back sees it).
  * PATCH analytics/dashboards/<id>: always 400 JSON_PARSER_ERROR (the proof, steps 3-5).
  * GET .../describe answers a small describe; any other GET (a report run returns its rows) and
    any other method is an AssertionError (recorded first).
  Every answer carries a fictional staff name (CANARY): the tool must never print an answer.

The plan CSV has columns kind,id,to_folder,new_label; the ledger CSV has the columns LEDGER_COLS.
Options go after the subcommand: `move --plan FILE --vpn-off [--apply] [--limit N] --dir DIR`.
A run succeeds when main() returns 0/None; a refusal is SystemExit with a non-zero code (or a
non-zero return) and sends no write.
"""
import contextlib
import copy
import csv
import io
import os
import random
import re
import stat
import string
import subprocess
import sys
import tempfile
import unittest

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import REPO, md_part, read
sys.path.insert(0, os.path.join(REPO, "test", "fixtures"))
import make_fixture                                        # the invented name pools
import sf_report_folders as srf

API_ROOT = "/services/data/v67.0/"
TOOL = os.path.join(REPO, "tools", "sf_report_folders.py")
LEDGER_COLS = ["when", "action", "kind", "id", "from_folder_id", "to_folder_id", "old_label", "new_label",
               "copy_id", "tag", "status", "http"]
LIST_COLS = ["kind", "id", "developer_name", "label", "folder", "last_run", "used_by"]
ALLOWED_OBJECTS = {"folder", "report", "dashboard", "dashboardcomponent"}
# a fictional staff member's name, in every API answer: the tool prints no response body
CANARY = f"{make_fixture.FIRST[3]} {make_fixture.LAST[4]}"
ALNUM = string.ascii_letters + string.digits

L40 = "Mentor trainings by partner and by month"
L41 = L40 + "s"
L60 = "Mentor trainings recorded by every partner, by region, month"
LONG = "Implementation by country and partner month"       # 43: a clone's name is cut to 40
assert (len(L40), len(L41), len(L60), len(LONG)) == (40, 41, 60, 43)


def fresh_id(prefix):
    """A new 18-character id each time."""
    return prefix + "".join(random.choice(ALNUM) for _ in range(18 - len(prefix)))


# ---- a minimal SOQL evaluator ---------------------------------------------------------------------
TOKEN = re.compile(r"\s*(?:('(?:[^'\\]|\\.)*')|(!=|<=|>=|=|<|>)|(\()|(\))|(,)|([^\s(),=<>!']+))")


def tokens(text):
    out, pos, text = [], 0, text.strip()
    while pos < len(text):
        m = TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise AssertionError(f"the fake cannot read this WHERE clause: {text!r}")
        pos = m.end()
        s, op, lp, rp, comma, word = m.groups()
        if s is not None:
            out.append(("str", re.sub(r"\\(.)", r"\1", s[1:-1])))
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
    return value


def field_of(record, path):
    value = record
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = next((v for k, v in value.items() if k.lower() == part.lower()), None)
    return value


def compare(a, op, b):
    if op in ("=", "!="):
        same = (None if a is None else str(a).casefold()) == (None if b is None else str(b).casefold())
        return same if op == "=" else not same
    if a is None or b is None:
        return False
    return {"<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[op]


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
        return any(compare(field_of(record, node[1]), "=", v) for v in node[2]) != node[3]
    if kind == "like":
        pattern = "".join(".*" if c == "%" else "." if c == "_" else re.escape(c) for c in node[2])
        value = field_of(record, node[1])
        found = value is not None and re.fullmatch(pattern, str(value), re.IGNORECASE | re.DOTALL) is not None
        return found != node[3]
    return compare(field_of(record, node[1]), node[2], node[3])


SOQL = re.compile(r"^\s*SELECT\s+(.+?)\s+FROM\s+(\w+)(?:\s+WHERE\s+(.+?))?(?:\s+ORDER\s+BY\s+.+?)?"
                  r"(?:\s+LIMIT\s+\d+)?\s*$", re.IGNORECASE | re.DOTALL)


def project(record, fields):
    out = {}
    for f in fields:
        parts, spot = f.split("."), out
        for part in parts[:-1]:
            spot = spot.setdefault(part, {})
        spot[parts[-1]] = copy.deepcopy(field_of(record, f))
    return out


def soql_objects(soql):
    """Every object a SOQL names after FROM (subqueries too), lower case."""
    return {m.lower() for m in re.findall(r"\bFROM\s+(\w+)", soql, re.IGNORECASE)}


# ---- the fake org ---------------------------------------------------------------------------------
FOLDERS = [   # key, name, type
    ("r_dhis2", "DHIS2 Reports", "Report"), ("r_public", "Public Reports", "Report"),
    ("r_cat", "GLOW Club Reports", "Report"), ("r_shared", "Shared Name", "Report"),
    ("r_old1", "Old Exports", "Report"), ("r_old2", "Old Exports", "Report"),
    ("r_att", "Attendance", "Report"), ("r_attarch", "Attendance Archive", "Report"),
    ("d_dhis2", "DHIS2 Dashboards", "Dashboard"), ("d_dhis2b", "Dhis2 Dashbords", "Dashboard"),
    ("d_cat", "GLOW Club Dashboards", "Dashboard"), ("d_shared", "Shared Name", "Dashboard"),
    ("d_att", "Attendance", "Dashboard"),
]
REPORTS = [   # key, label, folder key, last run
    ("meet", "Club meet freq by month and region", "r_dhis2", "2026-09-14T08:00:00.000+0000"),
    ("girls", "Girls attended by partner", "r_dhis2", "2026-10-02T11:30:00.000+0000"),
    ("mentors", "Mentors trained per month", "r_dhis2", "2026-08-30T07:15:00.000+0000"),
    ("observed", "Sessions observed by partner", "r_dhis2", "2026-07-01T09:00:00.000+0000"),
    ("stories", "GLOW of the Month Stories", "r_dhis2", None),
    ("long", LONG, "r_dhis2", "2026-06-11T10:00:00.000+0000"),
    ("mixed", "Training sessions led", "r_dhis2", "2026-10-05T16:45:00.000+0000"),
    ("public", "Public club totals", "r_public", "2026-10-01T12:00:00.000+0000"),
    ("att", "Jotform attendance by club", "r_att", "2026-10-20T06:00:00.000+0000"),
    ("archived", "Old attendance export", "r_attarch", "2026-05-02T09:30:00.000+0000"),
]
DASHBOARDS = [   # key, title, folder key, report keys of its components (None: a text component)
    ("attendance", "GLOW Club Attendance", "d_dhis2", ["meet", "girls", None]),
    ("training_old", "Old training view", "d_dhis2b", ["girls", "mixed"]),
    ("reporting", "GLOW Club Reporting", "d_dhis2b", ["public"]),
    ("retired", "Retired observations", "d_decom", ["observed", "mixed"]),
    ("jotform", "Jotform Attendance", "d_att", ["att"]),
]


def dev_name(text):
    return re.sub(r"\W+", "_", text).strip("_")


class ReportOrg:
    """Salesforce as far as tools/sf_report_folders.py may see it (see the module docstring)."""
    alias = "fake"

    def __init__(self, decom_reports=1, decom_dashboards=1):
        self.calls, self.seen = [], []
        self.drift, self.refuse_patch, self.misplace = {}, set(), False
        self.folders, self.fid = [], {}
        for key, name, kind in FOLDERS:
            self.add_folder(key, name, kind)
        for n in range(decom_reports):
            self.add_folder("r_decom" if n == 0 else f"r_decom{n}", "Decommissioned", "Report")
        for n in range(decom_dashboards):
            self.add_folder("d_decom" if n == 0 else f"d_decom{n}", "Decommissioned", "Dashboard")
        self.reports, self.rid = [], {}
        for key, label, folder, last_run in REPORTS:
            rid = fresh_id("00O")
            self.rid[key] = rid
            self.reports.append({"Id": rid, "DeveloperName": dev_name(label), "Name": label,
                                 "OwnerId": self.fid[folder], "LastRunDate": last_run, "Description": ""})
        self.dashboards, self.did, self.components = [], {}, []
        for key, title, folder, uses in DASHBOARDS:
            did = fresh_id("01Z")
            self.did[key] = did
            folder = folder if folder in self.fid else "d_dhis2b"     # no Decommissioned: it stays outside
            self.dashboards.append({"Id": did, "DeveloperName": dev_name(title), "Title": title,
                                    "FolderId": self.fid[folder], "Type": "SpecifiedUser", "Description": ""})
            for rkey in uses:
                self.components.append({"Id": fresh_id("01a"), "DashboardId": did,
                                        "CustomReportId": self.rid[rkey] if rkey else None})

    def add_folder(self, key, name, kind):
        fid = fresh_id("00l")
        self.fid[key] = fid
        self.folders.append({"Id": fid, "Name": name, "DeveloperName": dev_name(name) + "_" + key, "Type": kind})

    # -- what the tests read
    def folder_name(self, fid):
        return next((f["Name"] for f in self.folders if f["Id"] == fid), None)

    def report(self, rid):
        found = [r for r in self.reports if r["Id"] == rid]
        assert len(found) <= 1
        return found[0] if found else None

    def dashboard(self, did):
        return next((d for d in self.dashboards if d["Id"] == did), None)

    def state(self):
        """{report id: (folder id, label)} and {dashboard id: (folder id, title)}."""
        return ({r["Id"]: (r["OwnerId"], r["Name"]) for r in self.reports},
                {d["Id"]: (d["FolderId"], d["Title"]) for d in self.dashboards})

    def writes(self):
        return [c for c in self.calls if c[0] != "GET"]

    def patches(self):
        return [c for c in self.calls if c[0] == "PATCH"]

    def posts(self):
        return [c for c in self.calls if c[0] == "POST"]

    # -- SOQL
    def table(self, sobject):
        name = sobject.lower()
        if name == "folder":
            return [dict(f) for f in self.folders]
        if name == "report":
            return [dict(r, FolderName=self.folder_name(r["OwnerId"])) for r in self.reports]
        if name == "dashboard":
            return [dict(d, FolderName=self.folder_name(d["FolderId"])) for d in self.dashboards]
        if name == "dashboardcomponent":
            dashes = {d["Id"]: d for d in self.table("Dashboard")}
            return [dict(c, Dashboard=dashes.get(c["DashboardId"])) for c in self.components]
        raise AssertionError(f"the tool read an object it has no reason to read: {sobject}")

    def query(self, soql):
        self.seen.append(soql)
        m = SOQL.match(soql)
        if not m:
            raise AssertionError(f"the fake cannot read this SOQL: {soql}")
        fields, sobject, where = m.groups()
        names = [f.strip() for f in fields.split(",")]
        if any("(" in f for f in names):
            raise AssertionError(f"the fake answers plain field lists only: {soql}")
        records = self.table(sobject)
        if where:
            tree = Where(where).parse()
            records = [r for r in records if holds(tree, r)]
        return [project(r, names) for r in records]

    query_all = query

    def count(self, soql):
        raise AssertionError("the fake answers no COUNT(): count the records a query returns")

    # -- REST
    def call(self, method, path, body=None):
        self.calls.append((method, path, copy.deepcopy(body)))
        if method not in ("GET", "POST", "PATCH"):
            raise AssertionError(f"the tool sent {method} {path}")
        assert path.startswith(API_ROOT), f"not under {API_ROOT}: {path}"
        rest = path[len(API_ROOT):]
        m = re.fullmatch(r"analytics/(reports|dashboards)\?cloneId=(\w+)", rest)
        if method == "POST" and m:
            return self.clone(m.group(1), m.group(2), body)
        m = re.fullmatch(r"analytics/(reports|dashboards)/(\w+)", rest)
        if method == "PATCH" and m:
            if m.group(1) == "dashboards":
                return 400, [{"errorCode": "JSON_PARSER_ERROR", "message": f"Cannot deserialize ({CANARY})"}]
            return self.patch_report(m.group(2), body)
        m = re.fullmatch(r"analytics/(reports|dashboards)/(\w+)/describe", rest)
        if method == "GET" and m:
            if m.group(1) == "reports" and self.report(m.group(2)):
                r = self.report(m.group(2))
                return 200, {"reportMetadata": {"id": r["Id"], "name": r["Name"], "folderId": r["OwnerId"]},
                             "runningUser": {"name": CANARY}}
            if m.group(1) == "dashboards" and self.dashboard(m.group(2)):
                d = self.dashboard(m.group(2))
                return 200, {"id": d["Id"], "name": d["Title"], "folderId": d["FolderId"],
                             "runningUser": {"name": CANARY}}
            return 404, [{"errorCode": "NOT_FOUND", "message": "no such item"}]
        raise AssertionError(f"the fake does not answer {method} {path} (a GET on a report runs it: record data)")

    def clone(self, kind, source, body):
        if kind == "reports":
            src = self.report(source)
            meta = (body or {}).get("reportMetadata") if isinstance(body, dict) else None
            if src is None:
                return 404, [{"errorCode": "NOT_FOUND", "message": "no such report"}]
            if not isinstance(meta, dict):
                return 400, [{"errorCode": "JSON_PARSER_ERROR", "message": f"no reportMetadata ({CANARY})"}]
            name = meta.get("name", src["Name"]).strip()      # Salesforce keeps a name trimmed
            if len(name) > 40:
                return 400, [{"errorCode": "FIELD_INTEGRITY_EXCEPTION", "message": "name too long"}]
            asked = meta.get("folderId", src["OwnerId"])
            new = dict(src, Id=fresh_id("00O"), Name=name, OwnerId=src["OwnerId"] if self.misplace else asked,
                       DeveloperName=src["DeveloperName"] + "_copy", Description=meta.get("description", ""),
                       LastRunDate=None)
            self.reports.append(new)
            return 200, {"reportMetadata": {"id": new["Id"], "name": new["Name"], "folderId": asked},
                         "runningUser": {"name": CANARY}}
        src = self.dashboard(source)
        if src is None:
            return 404, [{"errorCode": "NOT_FOUND", "message": "no such dashboard"}]
        if not isinstance(body, dict) or set(body) - {"folderId"}:
            return 400, [{"errorCode": "JSON_PARSER_ERROR", "message": f"Cannot deserialize ({CANARY})"}]
        asked = body.get("folderId", src["FolderId"])
        new = dict(src, Id=fresh_id("01Z"), FolderId=src["FolderId"] if self.misplace else asked,
                   DeveloperName=src["DeveloperName"] + "_copy")
        self.dashboards.append(new)
        for c in [c for c in self.components if c["DashboardId"] == source]:
            self.components.append(dict(c, Id=fresh_id("01a"), DashboardId=new["Id"]))
        return 200, {"id": new["Id"], "name": new["Title"], "folderId": asked,
                     "dashboardMetadata": {"id": new["Id"], "name": new["Title"], "folderId": asked},
                     "runningUser": {"name": CANARY}}

    def patch_report(self, rid, body):
        r = self.report(rid)
        if r is None:
            return 404, [{"errorCode": "NOT_FOUND", "message": "no such report"}]
        if rid in self.refuse_patch:
            return 400, [{"errorCode": "INVALID_FIELD", "message": f"refused ({CANARY})"}]
        meta = body.get("reportMetadata") if isinstance(body, dict) else None
        if not isinstance(meta, dict):
            return 400, [{"errorCode": "JSON_PARSER_ERROR", "message": f"no reportMetadata ({CANARY})"}]
        if "name" in meta and len(meta["name"]) > 40:
            return 400, [{"errorCode": "FIELD_INTEGRITY_EXCEPTION", "message": "name too long"}]
        drift = self.drift.get(rid)
        if drift == "echo":        # the answer says what was asked; Salesforce kept nothing
            echoed = {"id": r["Id"], "name": r["Name"], "folderId": r["OwnerId"]}
            echoed.update({k: v for k, v in meta.items() if k in ("name", "folderId")})
            return 200, {"reportMetadata": echoed, "runningUser": {"name": CANARY}}
        if "folderId" in meta and drift != "folder":
            r["OwnerId"] = meta["folderId"]
        if "name" in meta and drift != "name":
            r["Name"] = meta["name"].strip()
        if "description" in meta:
            r["Description"] = meta["description"]
        return 200, {"reportMetadata": {"id": r["Id"], "name": r["Name"], "folderId": r["OwnerId"]},
                     "runningUser": {"name": CANARY}}


def rows_on_disk(path):
    """The ledger's rows as they are on disk now ([] when there is no file yet)."""
    if not path or not os.path.exists(path) or os.path.getsize(path) == 0:
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


class Crash(BaseException):
    """The process dies (power, kill, lost laptop) after Salesforce took a write, before the tool
    hears back: nothing in the tool runs after it."""


class WatchedOrg(ReportOrg):
    """ReportOrg that, when each write (POST or PATCH) arrives, records what ledger.csv on disk holds
    at that moment (on_disk: [(method, path, rows)]); crash_at = N makes the Nth write land in
    Salesforce and then raise Crash."""

    def __init__(self, ledger_path, **kw):
        super().__init__(**kw)
        self.ledger_path, self.on_disk, self.crash_at = ledger_path, [], None

    def call(self, method, path, body=None):
        if method != "GET":
            self.on_disk.append((method, path, rows_on_disk(self.ledger_path)))
        answer = super().call(method, path, body)
        if method != "GET" and self.crash_at == len(self.writes()):
            raise Crash(f"died after {method} {path}")
        return answer


# ---- the harness ----------------------------------------------------------------------------------
class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fresh()

    def fresh(self, **kw):
        self.org = ReportOrg(**kw)
        self.dir = tempfile.mkdtemp(dir=self.tmp.name)
        self.ledger_path = os.path.join(self.dir, "ledger.csv")
        return self.org

    def run_tool(self, *argv, dir_=True):
        """(stdout + stderr + the exit message, the exit code: None or 0 when it ended normally).
        self.out keeps stdout alone. Checks that no API answer reached the output."""
        out, err = io.StringIO(), io.StringIO()
        code = None
        args = list(argv) + (["--dir", self.dir] if dir_ else [])
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = srf.main(args, org=self.org)
        except SystemExit as stop:
            code = stop.code
        self.out = out.getvalue()
        said = out.getvalue() + err.getvalue() + ("" if code in (None, 0) else str(code))
        self.assertNotIn(CANARY, said, "the tool printed an API answer")
        return said, code

    def ok(self, *argv):
        said, code = self.run_tool(*argv)
        self.assertIn(code, (None, 0), f"the run should succeed; it said:\n{said}")
        return said

    def refused(self, *argv):
        said, code = self.run_tool(*argv)
        self.assertNotIn(code, (None, 0), f"the run should be refused; it said:\n{said}")
        return said

    def plan(self, rows):
        """A plan CSV of (kind, id, to_folder, new_label) rows; its path."""
        fd, path = tempfile.mkstemp(suffix=".csv", dir=self.tmp.name)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["kind", "id", "to_folder", "new_label"])
            w.writerows(rows)
        return path

    def ledger(self):
        self.assertTrue(os.path.exists(self.ledger_path), "no ledger.csv after a write")
        self.assertEqual(stat.S_IMODE(os.stat(self.ledger_path).st_mode), 0o600)
        with open(self.ledger_path, encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            self.assertEqual(reader.fieldnames, LEDGER_COLS)
            return list(reader)

    def assert_nothing_written(self, before=None):
        self.assertEqual(self.org.writes(), [], "a write was sent")
        self.assertFalse(os.path.exists(self.ledger_path) and os.path.getsize(self.ledger_path) > 0,
                         "a ledger row was written")
        if before is not None:
            self.assertEqual(self.org.state(), before)

    def lines_with(self, said, text):
        return [line for line in said.splitlines() if text in line]

    def move_plan(self):
        """Three report rows: a relabel into a category folder, a retirement with the label kept, a
        relabel into the report folder that shares its name with a dashboard folder."""
        o = self.org
        return [
            ("report", o.rid["meet"], "GLOW Club Reports", "Club meeting frequency"),
            ("report", o.rid["mentors"], "Decommissioned", ""),
            ("report", o.rid["stories"], "Shared Name", "GLOW of the Month table"),
        ]

    def target(self, name):
        return {"GLOW Club Reports": "r_cat", "Decommissioned": "r_decom", "Shared Name": "r_shared",
                "Public Reports": "r_public", "DHIS2 Reports": "r_dhis2", "Attendance Archive": "r_attarch"}[name]

    def write_ledger(self, rows):
        """A ledger written by hand (an earlier run's), at the --dir ledger; its path."""
        with open(self.ledger_path, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=LEDGER_COLS, lineterminator="\n")
            w.writeheader()
            for n, row in enumerate(rows):
                w.writerow(dict({"when": f"2026-10-23T10:0{n}:00Z"}, **row))
        os.chmod(self.ledger_path, 0o600)
        return self.ledger_path

    def apply_moves(self, plans):
        """Each plan (a list of rows) moved with --apply, in order; the ledger's move rows."""
        for rows in plans:
            self.ok("move", "--plan", self.plan(rows), "--vpn-off", "--apply")
        return [x for x in self.ledger() if x["action"] == "move"]

    def writes_since(self, n):
        return [x for x in self.org.calls[n:] if x[0] != "GET"]


# ---- the broad behaviour --------------------------------------------------------------------------
class List(Harness):
    def parse_csv(self):
        lines = [line for line in self.out.splitlines() if line.strip()]
        self.assertTrue(lines, "list printed nothing to stdout")
        rows = list(csv.reader(lines))
        self.assertEqual(rows[0], LIST_COLS, "stdout must be the CSV alone, header first")
        return [dict(zip(LIST_COLS, r)) for r in rows[1:]]

    def expected_used_by(self, rid):
        return {c["DashboardId"] for c in self.org.components if c["CustomReportId"] == rid}

    def test_list_prints_csv_of_the_folders_items_with_the_dashboards_that_use_them(self):
        o = self.org
        before = o.state()
        self.ok("list", "--vpn-off", "--folder", "DHIS2 Reports")
        rows = self.parse_csv()
        want = [r for r in o.reports if r["OwnerId"] == o.fid["r_dhis2"]]
        self.assertEqual(sorted(r["id"] for r in rows), sorted(r["Id"] for r in want))
        for r in want:
            row = next(x for x in rows if x["id"] == r["Id"])
            self.assertEqual(row["kind"], "report")
            self.assertEqual(row["developer_name"], r["DeveloperName"])
            self.assertEqual(row["label"], r["Name"])
            self.assertEqual(row["folder"], "DHIS2 Reports")
            if r["LastRunDate"]:
                self.assertEqual(row["last_run"][:10], r["LastRunDate"][:10])
            else:
                self.assertEqual(row["last_run"], "")
            used = {u for u in row["used_by"].split(";") if u}
            self.assertEqual(used, self.expected_used_by(r["Id"]), f"used_by of {r['Name']}")
        # the spread: two dashboards, one, none
        by_id = {x["id"]: x for x in rows}
        self.assertEqual(len(by_id[o.rid["girls"]]["used_by"].split(";")), 2)
        self.assertEqual(by_id[o.rid["mentors"]]["used_by"], "")
        self.assert_nothing_written(before)

        # two folders of both kinds, and --kind
        self.ok("list", "--vpn-off", "--folder", "Dhis2 Dashbords", "--folder", "Public Reports")
        rows = self.parse_csv()
        self.assertEqual(sorted((x["kind"], x["id"]) for x in rows),
                         sorted([("dashboard", o.did["training_old"]), ("dashboard", o.did["reporting"]),
                                 ("report", o.rid["public"])]))
        dash = next(x for x in rows if x["id"] == o.did["reporting"])
        self.assertEqual((dash["label"], dash["folder"]), ("GLOW Club Reporting", "Dhis2 Dashbords"))
        self.assertEqual(next(x for x in rows if x["id"] == o.rid["public"])["used_by"], o.did["reporting"])

        self.ok("list", "--vpn-off", "--folder", "Decommissioned", "--kind", "dashboard")
        rows = self.parse_csv()
        self.assertEqual([(x["kind"], x["id"]) for x in rows], [("dashboard", o.did["retired"])])
        self.ok("list", "--vpn-off", "--folder", "Decommissioned", "--kind", "report")
        self.assertEqual(self.parse_csv(), [])
        self.assert_nothing_written(before)


class Move(Harness):
    def test_move_dry_run_writes_nothing_and_prints_each_change(self):
        for n in (1, 3):
            o = self.fresh()
            rows = self.move_plan()[:n]
            before = o.state()
            said = self.ok("move", "--plan", self.plan(rows), "--vpn-off")
            self.assert_nothing_written(before)
            for _kind, rid, to, label in rows:
                lines = self.lines_with(said, rid)
                self.assertEqual(len(lines), 1, f"one line per plan row for {rid}:\n{said}")
                self.assertIn(to, lines[0])
                if label:
                    self.assertIn(label, lines[0])
                # what only the read of the item gives: its current label and folder
                self.assertIn(o.report(rid)["Name"], lines[0], f"the current label, read from Salesforce:\n{said}")
                self.assertIn(o.folder_name(o.report(rid)["OwnerId"]), lines[0], "the current folder")
            others = [r["Id"] for r in o.reports if r["Id"] not in {x[1] for x in rows}]
            for rid in others:
                self.assertNotIn(rid, said)

    def test_move_apply_moves_and_relabels_and_reads_back_the_same_id(self):
        o = self.org
        rows = self.move_plan()
        old = {rid: (o.report(rid)["OwnerId"], o.report(rid)["Name"]) for _, rid, _, _ in rows}
        count = len(o.reports)
        said = self.ok("move", "--plan", self.plan(rows), "--vpn-off", "--apply")
        self.assertEqual(o.posts(), [], "a move is a PATCH, never a clone")
        patches = o.patches()
        self.assertEqual(len(patches), len(rows))
        for (_, rid, to, label) in rows:
            folder_id = o.fid[self.target(to)]
            sent = [p for p in patches if p[1] == f"{API_ROOT}analytics/reports/{rid}"]
            self.assertEqual(len(sent), 1, f"one PATCH for {rid}")
            want = {"folderId": folder_id}
            if label:
                want["name"] = label
            self.assertEqual(sent[0][2], {"reportMetadata": want})
            r = o.report(rid)
            self.assertIsNotNone(r, "the same Id after the move")
            self.assertEqual(r["OwnerId"], folder_id)
            self.assertEqual(r["Name"], label or old[rid][1])
            self.assertIn(rid, said)
        self.assertEqual(len(o.reports), count, "no new report: the Ids are kept")

        ledger = self.ledger()
        self.assertEqual([x["id"] for x in ledger], [rid for _, rid, _, _ in rows])
        for x, (_, rid, to, label) in zip(ledger, rows):
            self.assertEqual((x["action"], x["kind"], x["status"], x["http"]), ("move", "report", "ok", "200"))
            self.assertEqual(x["from_folder_id"], old[rid][0])
            self.assertEqual(x["to_folder_id"], o.fid[self.target(to)])
            self.assertEqual(x["old_label"], old[rid][1])
            if label:
                self.assertEqual(x["new_label"], label)
            self.assertTrue(x["when"])

    def test_limit_stops_after_n_writes(self):
        for n in (1, 2, 3):
            o = self.fresh()
            rows = self.move_plan() + [("report", o.rid["long"], "Decommissioned", "")]
            before = {rid: o.report(rid)["OwnerId"] for _, rid, _, _ in rows}
            said = self.ok("move", "--plan", self.plan(rows), "--vpn-off", "--apply", "--limit", str(n))
            self.assertEqual(len(o.writes()), n, said)
            self.assertEqual([x["id"] for x in self.ledger()], [rid for _, rid, _, _ in rows[:n]])
            for i, (_, rid, to, _) in enumerate(rows):
                want = o.fid[self.target(to)] if i < n else before[rid]
                self.assertEqual(o.report(rid)["OwnerId"], want, f"row {i} with --limit {n}")

    def test_a_failed_read_back_stops_the_run(self):
        # "echo": the PATCH answer says it worked; only a SOQL read-back shows nothing changed
        for bad, drift in ((0, "folder"), (1, "folder"), (2, "name"), (0, "echo"), (1, "echo")):
            o = self.fresh()
            rows = self.move_plan()
            o.drift[rows[bad][1]] = drift
            untouched = {rid: (o.report(rid)["OwnerId"], o.report(rid)["Name"]) for _, rid, _, _ in rows[bad + 1:]}
            said = self.refused("move", "--plan", self.plan(rows), "--vpn-off", "--apply")
            self.assertEqual(len(o.writes()), bad + 1, f"no write after the failed read-back:\n{said}")
            ledger = self.ledger()
            self.assertEqual([x["id"] for x in ledger], [rid for _, rid, _, _ in rows[:bad + 1]])
            self.assertEqual([x["status"] for x in ledger], ["ok"] * bad + ["failed"])
            for rid, was in untouched.items():
                self.assertEqual((o.report(rid)["OwnerId"], o.report(rid)["Name"]), was)
            self.assertIn(rows[bad][1], said)

        # a refused PATCH stops the run too, and says its HTTP code
        o = self.fresh()
        rows = self.move_plan()
        o.refuse_patch.add(rows[0][1])
        said = self.refused("move", "--plan", self.plan(rows), "--vpn-off", "--apply")
        self.assertEqual(len(o.writes()), 1)
        self.assertIn("400", said)


class Copy(Harness):
    def test_copy_clones_into_decommissioned_with_its_source_and_tag(self):
        o = self.org
        # the dry run sends nothing
        before = o.state()
        said = self.ok("copy", "--kind", "report", "--id", o.rid["meet"], "--tag", "#72", "--vpn-off")
        self.assert_nothing_written(before)
        self.assertIn(o.rid["meet"], said)

        cases = [("report", o.rid["meet"], "#72"), ("report", o.rid["long"], "keep-list 2026-10-23"),
                 ("dashboard", o.did["attendance"], "#72"), ("dashboard", o.did["reporting"], "before #75")]
        for n, (kind, source, tag) in enumerate(cases, 1):
            was = copy.deepcopy(o.report(source) if kind == "report" else o.dashboard(source))
            sent_before = len(o.posts())
            self.ok("copy", "--kind", kind, "--id", source, "--tag", tag, "--vpn-off", "--apply")
            posts = o.posts()[sent_before:]
            self.assertEqual(len(posts), 1, f"one clone for {kind} {source}")
            method, path, body = posts[0]
            row = self.ledger()[-1]
            self.assertEqual(len(self.ledger()), n, "one ledger row per copy")
            self.assertEqual((row["action"], row["kind"], row["id"], row["tag"], row["status"]),
                             ("copy", kind, source, tag, "ok"))
            new_id = row["copy_id"]
            self.assertNotEqual(new_id, source)
            if kind == "report":
                decom = o.fid["r_decom"]
                self.assertEqual(path, f"{API_ROOT}analytics/reports?cloneId={source}")
                self.assertEqual(body["reportMetadata"]["folderId"], decom)
                self.assertEqual(body["reportMetadata"]["name"], was["Name"][:40])
                new = o.report(new_id)
                self.assertIsNotNone(new, "the ledger's copy_id is the clone's id")
                self.assertEqual((new["OwnerId"], new["Name"]), (decom, was["Name"][:40]))
                self.assertIn(source, new["Description"])
                self.assertIn(tag, new["Description"])
                self.assertEqual(o.report(source), was, "the source is untouched")
            else:
                decom = o.fid["d_decom"]
                self.assertEqual(path, f"{API_ROOT}analytics/dashboards?cloneId={source}")
                self.assertEqual(body, {"folderId": decom}, "the API takes no name or description for a dashboard")
                new = o.dashboard(new_id)
                self.assertIsNotNone(new, "the ledger's copy_id is the clone's id")
                self.assertEqual(new["FolderId"], decom)
                self.assertEqual(o.dashboard(source), was, "the source is untouched")
        self.assertFalse([p for p in o.patches() if "/dashboards/" in p[1]], "a dashboard PATCH is refused by the API")

    def test_a_copy_is_read_back_and_a_misplaced_clone_stops_the_run(self):
        for kind in ("report", "dashboard"):
            o = self.fresh()
            o.misplace = True        # the clone answers 200 with the folder asked for, but lands in its source's
            source = o.rid["meet"] if kind == "report" else o.did["attendance"]
            said = self.refused("copy", "--kind", kind, "--id", source, "--tag", "#72", "--vpn-off", "--apply")
            self.assertEqual(len(o.writes()), 1, f"no write after the failed read-back:\n{said}")
            new_id = (o.reports if kind == "report" else o.dashboards)[-1]["Id"]
            ledger = self.ledger()
            self.assertEqual(len(ledger), 1)
            self.assertEqual((ledger[0]["action"], ledger[0]["id"], ledger[0]["copy_id"], ledger[0]["status"]),
                             ("copy", source, new_id, "failed"))

    def add_report(self, label, folder="r_dhis2"):
        """A new report in the fake org (fictional label); its id."""
        o = self.org
        rid = fresh_id("00O")
        o.reports.append({"Id": rid, "DeveloperName": dev_name(label), "Name": label, "OwnerId": o.fid[folder],
                          "LastRunDate": None, "Description": ""})
        return rid

    def test_report_clone_body_is_the_proofs_and_the_description_follows_by_patch(self):
        """#69's API proof, Report steps 1 and 5: the clone POST carries reportMetadata name and
        folderId and nothing else; the source id and tag go on by a PATCH of the copy."""
        for key, tag in (("meet", "#72"), ("long", "keep-list 2026-10-23"), ("girls", "before #75")):
            o = self.fresh()
            source = o.rid[key]
            was = copy.deepcopy(o.report(source))
            label = was["Name"][:40]
            decom = o.fid["r_decom"]
            sent = len(o.calls)
            self.ok("copy", "--kind", "report", "--id", source, "--tag", tag, "--vpn-off", "--apply")
            writes = self.writes_since(sent)
            method, path, body = writes[0]
            self.assertEqual((method, path), ("POST", f"{API_ROOT}analytics/reports?cloneId={source}"))
            self.assertEqual(body, {"reportMetadata": {"name": label, "folderId": decom}},
                             f"{key}: the clone body is the proof's, name and folderId only")
            self.assertEqual([w[0] for w in writes], ["POST", "PATCH"], f"{key}: the clone, then its description")
            ledger = self.ledger()
            self.assertEqual(len(ledger), 1, "one ledger row per copy")
            row = ledger[0]
            copy_id = row["copy_id"]
            self.assertEqual((row["action"], row["kind"], row["id"], row["tag"], row["status"]),
                             ("copy", "report", source, tag, "ok"))
            self.assertIsNotNone(o.report(copy_id), "the ledger's copy_id is the clone's id")
            self.assertNotEqual(copy_id, source)
            _, path, body = writes[1]
            self.assertEqual(path, f"{API_ROOT}analytics/reports/{copy_id}", "the description PATCH is on the copy")
            self.assertEqual(set(body), {"reportMetadata"})
            meta = body["reportMetadata"]
            self.assertLessEqual(set(meta), {"name", "description"}, f"the proof's step 5 keys only: {meta}")
            self.assertEqual(meta.get("description"), f"copy of {source}, {tag}")
            if "name" in meta:
                self.assertEqual(meta["name"], label, "a name in the PATCH is the copy's own label")
            new = o.report(copy_id)
            self.assertEqual((new["OwnerId"], new["Name"], new["Description"]),
                             (decom, label, f"copy of {source}, {tag}"))
            self.assertEqual(o.report(source), was, "the source is untouched")

    def test_a_refused_description_patch_keeps_the_copy_id_and_stops(self):
        class NoDescribe(ReportOrg):
            def patch_report(self, rid, body):
                if rid not in self.rid.values():         # the clone's description PATCH is refused
                    return 400, [{"errorCode": "INVALID_FIELD", "message": f"refused ({CANARY})"}]
                return super().patch_report(rid, body)
        self.org = o = NoDescribe()
        source = o.rid["mentors"]
        said = self.refused("copy", "--kind", "report", "--id", source, "--tag", "#72", "--vpn-off", "--apply")
        self.assertEqual([w[0] for w in o.writes()], ["POST", "PATCH"])
        new_id = o.reports[-1]["Id"]
        self.assertNotEqual(new_id, source)
        ledger = self.ledger()
        self.assertEqual(len(ledger), 1)
        self.assertEqual((ledger[0]["action"], ledger[0]["id"], ledger[0]["copy_id"], ledger[0]["status"]),
                         ("copy", source, new_id, "failed"))
        self.assertIn(new_id, said, "the refusal names the copy that has no description")
        self.assertIn("400", said)

    def test_a_cut_label_drops_the_space_it_ends_on(self):
        """The 40-character cut can end on a space; Salesforce stores the name trimmed, so the tool
        sends it trimmed and its read-back passes."""
        ends_on_space = "Mentor sessions recorded by partner and month, all"
        cut_before_space = L40 + " of the year"
        cases = ((ends_on_space, "Mentor sessions recorded by partner and"), (cut_before_space, L40))
        self.assertEqual((len(ends_on_space), ends_on_space[39], cut_before_space[40]), (50, " ", " "))
        self.assertEqual([len(want) for _, want in cases], [39, 40])
        for label, want in cases:
            o = self.fresh()
            source = self.add_report(label)
            sent = len(o.calls)
            self.ok("copy", "--kind", "report", "--id", source, "--tag", "#72", "--vpn-off", "--apply")
            writes = self.writes_since(sent)
            self.assertEqual(writes[0][0], "POST")
            self.assertEqual(writes[0][2]["reportMetadata"]["name"], want, f"the clone's name for {label!r}")
            for _, _, body in writes[1:]:
                if "name" in body.get("reportMetadata", {}):
                    self.assertEqual(body["reportMetadata"]["name"], want)
            row = self.ledger()[-1]
            self.assertEqual((row["action"], row["status"]), ("copy", "ok"), f"read back for {label!r}")
            self.assertEqual(row["new_label"], want)
            self.assertEqual((o.report(row["copy_id"])["Name"], o.report(row["copy_id"])["OwnerId"]),
                             (want, o.fid["r_decom"]))


class Undo(Harness):
    def test_undo_puts_every_ledger_row_back_last_first(self):
        o = self.org
        original = o.state()[0]
        b, c = o.rid["mentors"], o.rid["stories"]
        self.ok("copy", "--kind", "report", "--id", c, "--tag", "#72", "--vpn-off", "--apply")
        copy_id = self.ledger()[-1]["copy_id"]
        self.ok("move", "--plan", self.plan([("report", b, "Decommissioned", ""),
                                             ("report", c, "GLOW Club Reports", "Monthly stories")]),
                "--vpn-off", "--apply")
        self.ok("move", "--plan", self.plan([("report", c, "Decommissioned", "Stories, retired")]),
                "--vpn-off", "--apply")
        moves = [x for x in self.ledger() if x["action"] == "move"]
        self.assertEqual([x["id"] for x in moves], [b, c, c])
        rows_before = len(self.ledger())

        # the dry run
        state = o.state()
        sent = len(o.calls)
        said = self.ok("undo", "--ledger", self.ledger_path, "--vpn-off")
        self.assertEqual([x for x in o.calls[sent:] if x[0] != "GET"], [])
        self.assertEqual(o.state(), state)
        self.assertEqual(len(self.ledger()), rows_before, "a dry run writes no ledger row")
        self.assertTrue(self.lines_with(said, b) and self.lines_with(said, c), said)

        # the undo
        sent = len(o.calls)
        self.ok("undo", "--ledger", self.ledger_path, "--vpn-off", "--apply")
        undo_patches = [x for x in o.calls[sent:] if x[0] != "GET"]
        self.assertTrue(all(x[0] == "PATCH" for x in undo_patches), undo_patches)
        self.assertEqual([x[1] for x in undo_patches],
                         [f"{API_ROOT}analytics/reports/{x['id']}" for x in reversed(moves)], "last first")
        for (_, _, body), row in zip(undo_patches, reversed(moves)):
            self.assertEqual(body["reportMetadata"]["folderId"], row["from_folder_id"])
            if row["new_label"] and row["new_label"] != row["old_label"]:
                self.assertEqual(body["reportMetadata"]["name"], row["old_label"])
        now = o.state()[0]
        for rid, was in original.items():
            self.assertEqual(now[rid], was, f"{rid} is back where and as it was")
        self.assertEqual(now[copy_id], (o.fid["r_decom"], original[c][1]), "the copy stays")
        self.assertNotIn("DELETE", {x[0] for x in o.calls})
        added = self.ledger()[rows_before:]
        self.assertEqual(len(added), len(moves), "one ledger row per undone move")
        self.assertTrue(all(x["action"] not in ("move", "copy") for x in added), added)
        self.assertEqual([x["id"] for x in added], [x["id"] for x in reversed(moves)])

        # a second undo finds nothing left to undo
        sent = len(o.calls)
        self.ok("undo", "--ledger", self.ledger_path, "--vpn-off", "--apply")
        self.assertEqual(self.writes_since(sent), [], "every move was undone already")
        self.assertEqual(o.state()[0], now)

        # a later move is undone alone
        x = o.rid["observed"]
        self.apply_moves([[("report", x, "GLOW Club Reports", "Observations by partner")]])
        sent = len(o.calls)
        self.ok("undo", "--ledger", self.ledger_path, "--vpn-off", "--apply")
        self.assertEqual([w[1] for w in self.writes_since(sent)], [f"{API_ROOT}analytics/reports/{x}"])
        self.assertEqual(o.state()[0], now)

    def test_undo_acts_on_every_sent_move_and_skips_a_refused_one(self):
        """A move row whose PATCH answered 200 is undone, ok or failed; one answered 400 never moved."""
        o = self.org
        original = o.state()[0]
        meet, mentors, stories = o.rid["meet"], o.rid["mentors"], o.rid["stories"]
        o.report(meet).update(OwnerId=o.fid["r_cat"], Name="Club meeting frequency")
        o.report(mentors).update(OwnerId=o.fid["r_cat"])        # its read-back failed, the move landed later
        common = {"action": "move", "kind": "report", "from_folder_id": o.fid["r_dhis2"], "to_folder_id": o.fid["r_cat"]}
        ledger = self.write_ledger([
            dict(common, id=meet, old_label=original[meet][1], new_label="Club meeting frequency",
                 status="ok", http="200"),
            dict(common, id=mentors, old_label=original[mentors][1], new_label="", status="failed", http="200"),
            dict(common, id=stories, old_label=original[stories][1], new_label="Stories", status="failed",
                 http="400"),
            {"action": "copy", "kind": "report", "id": stories, "to_folder_id": o.fid["r_decom"],
             "copy_id": fresh_id("00O"), "tag": "#72", "status": "ok", "http": "200"},
        ])
        sent = len(o.calls)
        self.ok("undo", "--ledger", ledger, "--vpn-off", "--apply")
        self.assertEqual([w[1] for w in self.writes_since(sent)],
                         [f"{API_ROOT}analytics/reports/{rid}" for rid in (mentors, meet)], "last first; no 400 row")
        self.assertEqual(o.state()[0], original)

    def test_undo_stops_on_a_failed_read_back(self):
        for mode in ("echo", "folder", "refuse"):
            o = self.fresh()
            a, b, c = o.rid["mentors"], o.rid["stories"], o.rid["observed"]     # labels within 40: undo can put them back
            moves = self.apply_moves([[("report", a, "Decommissioned", ""), ("report", b, "GLOW Club Reports", "Stories")],
                                      [("report", c, "Shared Name", "Implementation by month")]])
            moved = o.state()[0]
            rows_before = len(self.ledger())
            if mode == "refuse":
                o.refuse_patch.add(c)
            else:
                o.drift[c] = mode
            sent = len(o.calls)
            said = self.refused("undo", "--ledger", self.ledger_path, "--vpn-off", "--apply")
            self.assertEqual([w[1] for w in self.writes_since(sent)], [f"{API_ROOT}analytics/reports/{c}"],
                             f"{mode}: no write after the failed undo:\n{said}")
            added = self.ledger()[rows_before:]
            self.assertEqual([(x["id"], x["status"]) for x in added], [(c, "failed")], mode)
            self.assertNotIn(added[0]["action"], ("move", "copy"))
            for rid in (a, b):
                self.assertEqual(o.state()[0][rid], moved[rid], f"{mode}: {rid} stays moved")
            self.assertEqual(len(moves), 3)

    def test_undo_limit_undoes_the_last_n_and_the_rest_later(self):
        o = self.org
        original = o.state()[0]
        a, b, c = o.rid["mentors"], o.rid["stories"], o.rid["observed"]     # labels within 40: undo can put them back
        self.apply_moves([[("report", a, "Decommissioned", ""), ("report", b, "GLOW Club Reports", "Stories"),
                           ("report", c, "Shared Name", "Implementation by month")]])
        moved = o.state()[0]
        sent = len(o.calls)
        self.ok("undo", "--ledger", self.ledger_path, "--vpn-off", "--apply", "--limit", "1")
        self.assertEqual([w[1] for w in self.writes_since(sent)], [f"{API_ROOT}analytics/reports/{c}"])
        self.assertEqual(o.state()[0][c], original[c])
        self.assertEqual((o.state()[0][a], o.state()[0][b]), (moved[a], moved[b]))
        sent = len(o.calls)
        self.ok("undo", "--ledger", self.ledger_path, "--vpn-off", "--apply")
        self.assertEqual([w[1] for w in self.writes_since(sent)],
                         [f"{API_ROOT}analytics/reports/{rid}" for rid in (b, a)])
        self.assertEqual(o.state()[0], original)


class PublicReportsOrg(ReportOrg):
    """ReportOrg as the real org has "Public Reports": no Folder record; a report there has the
    organization's id (an `00D…` id) as its OwnerId and "Public Reports" as its FolderName. A second
    report stays there (in the org, the keep list's item 17 did)."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.org_id = fresh_id("00D")
        public = self.fid["r_public"]
        self.folders = [f for f in self.folders if f["Id"] != public]
        for r in self.reports:
            if r["OwnerId"] == public:
                r["OwnerId"] = self.org_id
        self.fid["r_public"] = self.org_id
        rid = fresh_id("00O")
        self.rid["public_kept"] = rid
        self.reports.append({"Id": rid, "DeveloperName": "Public_partner_count", "Name": "Public partner count",
                             "OwnerId": self.org_id, "LastRunDate": None, "Description": ""})

    def folder_name(self, fid):
        return "Public Reports" if fid == self.org_id else super().folder_name(fid)


class UndoFromPublicReports(Harness):
    """Ticket #72, live 2026-10-24: two reports moved out of "Public Reports", whose ledger rows'
    from_folder_id is the organization's id (no Folder has it), and two reports have a repeated
    Decommissioned-to-Decommissioned row, a no-op: the full `--apply` run's first PATCH moved its plan's
    first row, already moved by `--limit 1`, again. The undo's dry run must
    list every row and name "Public Reports" as the destination of the org-id ones, not refuse; the
    undo puts each report back, last first, a Public Reports one with folderId the org id."""

    def fresh(self, **kw):
        super().fresh(**kw)
        self.org = PublicReportsOrg(**kw)
        return self.org

    def retired_ledger(self, public_from=None):
        """The org after the retirement and its ledger: meet moved DHIS2 Reports -> Decommissioned, the
        public report moved Public Reports (the org id, or `public_from`) -> Decommissioned, then meet's
        repeated row Decommissioned -> Decommissioned. (original state, [meet, public])."""
        o = self.org
        original = o.state()[0]
        meet, pub = o.rid["meet"], o.rid["public"]
        o.report(meet).update(OwnerId=o.fid["r_decom"])
        o.report(pub).update(OwnerId=o.fid["r_decom"])
        common = {"action": "move", "kind": "report", "new_label": "", "status": "ok", "http": "200"}
        self.write_ledger([
            dict(common, id=meet, from_folder_id=o.fid["r_dhis2"], to_folder_id=o.fid["r_decom"],
                 old_label=original[meet][1]),
            dict(common, id=pub, from_folder_id=public_from or o.org_id, to_folder_id=o.fid["r_decom"],
                 old_label=original[pub][1]),
            dict(common, id=meet, from_folder_id=o.fid["r_decom"], to_folder_id=o.fid["r_decom"],
                 old_label=original[meet][1]),
        ])
        return original, [meet, pub]

    def test_undo_dry_run_lists_every_row_and_names_public_reports(self):
        o = self.org
        _, (meet, pub) = self.retired_ledger()
        state, on_disk = o.state(), read(self.ledger_path)
        sent = len(o.calls)
        said = self.ok("undo", "--ledger", self.ledger_path, "--vpn-off")
        self.assertEqual(self.writes_since(sent), [], "a dry run sends no write")
        self.assertEqual(o.state(), state)
        self.assertEqual(read(self.ledger_path), on_disk, "a dry run writes no ledger row")
        rows = [line for line in said.splitlines() if meet in line or pub in line]
        self.assertEqual([pub if pub in line else meet for line in rows], [meet, pub, meet],
                         f"one line per ledger move, newest first (the no-op row included):\n{said}")
        self.assertIn("Public Reports", rows[1], f"the org-id row goes back to \"Public Reports\":\n{said}")
        self.assertIn("DHIS2 Reports", rows[2], f"the first row goes back to \"DHIS2 Reports\":\n{said}")
        self.assertNotIn("DHIS2 Reports", rows[0], f"the repeated row goes back to Decommissioned only:\n{said}")
        self.assertNotIn("Public Reports", rows[0] + rows[2], said)

        # a folder id that is neither a Folder nor the org's id is still refused, with nothing written
        self.fresh()
        self.retired_ledger(public_from=fresh_id("00l"))
        state = self.org.state()
        said = self.refused("undo", "--ledger", self.ledger_path, "--vpn-off")
        self.assertEqual(self.org.writes(), [], said)
        self.assertEqual(self.org.state(), state)

    def test_undo_apply_puts_a_public_report_back_with_the_org_id(self):
        o = self.org
        original, (meet, pub) = self.retired_ledger()
        rows_before = len(self.ledger())
        sent = len(o.calls)
        self.ok("undo", "--ledger", self.ledger_path, "--vpn-off", "--apply")
        patches = self.writes_since(sent)
        self.assertTrue(all(p[0] == "PATCH" for p in patches), patches)
        self.assertEqual([p[1] for p in patches], [f"{API_ROOT}analytics/reports/{rid}" for rid in (meet, pub, meet)],
                         "last first, every row")
        self.assertEqual([p[2]["reportMetadata"]["folderId"] for p in patches],
                         [o.fid["r_decom"], o.org_id, o.fid["r_dhis2"]])
        now = o.state()[0]
        self.assertEqual(now[meet], original[meet], "meet is back in DHIS2 Reports as it was")
        self.assertEqual(now[pub], (o.org_id, original[pub][1]), "the public report is back in Public Reports")
        self.assertEqual(now[o.rid["public_kept"]], original[o.rid["public_kept"]], "the kept one is untouched")
        added = self.ledger()[rows_before:]
        self.assertEqual([(x["action"], x["id"], x["to_folder_id"], x["status"]) for x in added],
                         [("undo", meet, o.fid["r_decom"], "ok"), ("undo", pub, o.org_id, "ok"),
                          ("undo", meet, o.fid["r_dhis2"], "ok")])
        sent = len(o.calls)
        self.ok("undo", "--ledger", self.ledger_path, "--vpn-off", "--apply")
        self.assertEqual(self.writes_since(sent), [], "every move was undone already")


class LedgerDurability(Harness):
    """A write's ledger row is on disk (status "sending", as tools/sf_backfill.py's) BEFORE its
    request goes out, and finished (ok or failed, in place: the finished ledger keeps one row per
    write) before the next write. A row a crash leaves "sending" has an unknown outcome: undo puts
    that move back, as it does any move Salesforce may have taken."""

    def watched(self, **kw):
        self.org = WatchedOrg(self.ledger_path, **kw)
        return self.org

    def die(self, *argv):
        """Run the tool until the fake's Crash (or an exit); what it printed is discarded."""
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                srf.main(list(argv) + ["--dir", self.dir], org=self.org)
            except (Crash, SystemExit):
                pass
            else:
                self.fail("the fake's Crash should have stopped the run")

    def assert_in_flight(self, seen, rid, where, **fields):
        rows = [x for x in seen if x["id"] == rid and x["status"] == "sending"]
        self.assertEqual(len(rows), 1, f"{where}: a 'sending' row for {rid} on disk before its request:\n{seen}")
        for k, v in fields.items():
            self.assertEqual(rows[0][k], v, f"{where}: the in-flight row's {k}")
        return rows[0]

    def test_move_rows_are_on_disk_before_each_patch_and_finished_before_the_next(self):
        o = self.watched()
        rows = self.move_plan()
        old = {rid: (o.report(rid)["OwnerId"], o.report(rid)["Name"]) for _, rid, _, _ in rows}
        self.ok("move", "--plan", self.plan(rows), "--vpn-off", "--apply")
        self.assertEqual([(m, p) for m, p, _ in o.on_disk],
                         [("PATCH", f"{API_ROOT}analytics/reports/{rid}") for _, rid, _, _ in rows])
        for k, (_, _, seen) in enumerate(o.on_disk):
            _, rid, to, label = rows[k]
            self.assert_in_flight(seen, rid, f"PATCH {k + 1}", action="move", kind="report",
                                  from_folder_id=old[rid][0], to_folder_id=o.fid[self.target(to)],
                                  old_label=old[rid][1], new_label=label)
            for _, earlier, _, _ in rows[:k]:
                done = [x for x in seen if x["id"] == earlier and x["status"] == "ok"]
                self.assertEqual(len(done), 1, f"PATCH {k + 1}: {earlier}'s finished row is on disk first:\n{seen}")
        final = self.ledger()
        self.assertEqual([(x["action"], x["id"], x["status"], x["http"]) for x in final],
                         [("move", rid, "ok", "200") for _, rid, _, _ in rows], "one finished row per write")

        # a failed read-back: its row is on disk before the PATCH, finished as failed after it
        o = self.fresh()
        o = self.watched()
        rows = self.move_plan()
        o.drift[rows[1][1]] = "folder"
        self.refused("move", "--plan", self.plan(rows), "--vpn-off", "--apply")
        self.assertEqual(len(o.on_disk), 2)
        self.assert_in_flight(o.on_disk[1][2], rows[1][1], "the failing PATCH", action="move")
        self.assertEqual([(x["id"], x["status"]) for x in self.ledger()], [(rows[0][1], "ok"), (rows[1][1], "failed")])

    def test_copy_row_is_on_disk_before_the_clone_and_holds_the_copy_id_before_the_next_write(self):
        o = self.watched()
        source = o.rid["mentors"]
        self.ok("copy", "--kind", "report", "--id", source, "--tag", "#72", "--vpn-off", "--apply")
        self.assertEqual(o.on_disk[0][0], "POST")
        self.assert_in_flight(o.on_disk[0][2], source, "the clone POST", action="copy", kind="report", tag="#72")
        self.assertEqual([m for m, _, _ in o.on_disk], ["POST", "PATCH"])
        final = self.ledger()
        self.assertEqual(len(final), 1)
        copy_id = final[0]["copy_id"]
        self.assertIsNotNone(o.report(copy_id))
        held = [x for x in o.on_disk[1][2] if x["action"] == "copy" and x["id"] == source]
        self.assertEqual([x["copy_id"] for x in held], [copy_id],
                         "the clone's id is on disk before the description PATCH is sent")
        self.assertEqual(final[0]["status"], "ok")

        o = self.fresh()
        o = self.watched()
        source = o.did["reporting"]
        self.ok("copy", "--kind", "dashboard", "--id", source, "--tag", "before #75", "--vpn-off", "--apply")
        self.assertEqual([m for m, _, _ in o.on_disk], ["POST"])
        self.assert_in_flight(o.on_disk[0][2], source, "the dashboard clone POST", action="copy", kind="dashboard",
                              tag="before #75")
        self.assertEqual([(x["action"], x["id"], x["status"]) for x in self.ledger()], [("copy", source, "ok")])

    def test_undo_rows_are_on_disk_before_each_patch(self):
        o = self.watched()
        a, b, c = o.rid["mentors"], o.rid["stories"], o.rid["observed"]
        moves = self.apply_moves([[("report", a, "Decommissioned", ""), ("report", b, "GLOW Club Reports", "Stories"),
                                   ("report", c, "Shared Name", "Implementation by month")]])
        rows_before = len(self.ledger())
        o.on_disk = []
        self.ok("undo", "--ledger", self.ledger_path, "--vpn-off", "--apply")
        order = [m["id"] for m in reversed(moves)]
        self.assertEqual([p for _, p, _ in o.on_disk], [f"{API_ROOT}analytics/reports/{rid}" for rid in order])
        for k, (_, _, seen) in enumerate(o.on_disk):
            row = self.assert_in_flight(seen, order[k], f"undo PATCH {k + 1}")
            self.assertNotIn(row["action"], ("move", "copy"))
            for earlier in order[:k]:
                done = [x for x in seen[rows_before:] if x["id"] == earlier and x["status"] == "ok"]
                self.assertEqual(len(done), 1, f"undo PATCH {k + 1}: {earlier}'s finished row is on disk first")
        added = self.ledger()[rows_before:]
        self.assertEqual([(x["id"], x["status"]) for x in added], [(rid, "ok") for rid in order])

    def test_a_crash_mid_write_leaves_a_row_that_undo_puts_back(self):
        for crash_at in (1, 2):
            o = self.fresh()
            o = self.watched()
            original = o.state()[0]
            mentors, stories = o.rid["mentors"], o.rid["stories"]
            rows = [("report", mentors, "Decommissioned", ""), ("report", stories, "GLOW Club Reports", "Monthly stories")]
            o.crash_at = crash_at
            self.die("move", "--plan", self.plan(rows), "--vpn-off", "--apply")
            crashed = rows[crash_at - 1][1]
            self.assertNotEqual(o.state()[0][crashed], original[crashed], "the crashed PATCH landed")
            left = rows_on_disk(self.ledger_path)
            mine = [x for x in left if x["id"] == crashed and x["action"] == "move"]
            self.assertEqual(len(mine), 1, f"crash at write {crash_at}: the ledger knows the write was sent:\n{left}")
            self.assertNotEqual(mine[0]["status"], "ok", "it was never read back")
            o.crash_at = None
            sent = len(o.calls)
            self.ok("undo", "--ledger", self.ledger_path, "--vpn-off", "--apply")
            self.assertEqual([w[1] for w in self.writes_since(sent)],
                             [f"{API_ROOT}analytics/reports/{r[1]}" for r in reversed(rows[:crash_at])], "last first")
            self.assertEqual(o.state()[0], original, f"crash at write {crash_at}: undo puts everything back")

        # a crash during the clone: the copy row is on disk; undo leaves copies alone
        o = self.fresh()
        o = self.watched()
        o.crash_at = 1
        source = o.rid["girls"]
        self.die("copy", "--kind", "report", "--id", source, "--tag", "#72", "--vpn-off", "--apply")
        self.assertEqual([x["id"] for x in rows_on_disk(self.ledger_path) if x["action"] == "copy"], [source])
        o.crash_at = None
        sent = len(o.calls)
        self.ok("undo", "--ledger", self.ledger_path, "--vpn-off", "--apply")
        self.assertEqual(self.writes_since(sent), [], "a copy is never undone")

        # a ledger a crash left: two 'sending' moves, one that landed and one that never did; both
        # outcomes are unknown to the tool, so undo puts both back
        o = self.fresh()
        original = o.state()[0]
        meet, observed = o.rid["meet"], o.rid["observed"]
        o.report(meet).update(OwnerId=o.fid["r_cat"], Name="Club meeting frequency")
        common = {"action": "move", "kind": "report", "from_folder_id": o.fid["r_dhis2"], "to_folder_id": o.fid["r_cat"],
                  "status": "sending", "http": ""}
        self.write_ledger([dict(common, id=observed, old_label=original[observed][1], new_label="Observations"),
                           dict(common, id=meet, old_label=original[meet][1], new_label="Club meeting frequency")])
        sent = len(o.calls)
        self.ok("undo", "--ledger", self.ledger_path, "--vpn-off", "--apply")
        self.assertEqual([w[1] for w in self.writes_since(sent)],
                         [f"{API_ROOT}analytics/reports/{rid}" for rid in (meet, observed)])
        self.assertEqual(o.state()[0], original)


# ---- the refusals ---------------------------------------------------------------------------------
class Refusals(Harness):
    def assert_move_refused(self, bad_row, *words):
        """A plan of a valid row, then `bad_row`: refused whole, before any write, in the dry run
        and with --apply alike."""
        o = self.org
        before = o.state()
        rows = [("report", o.rid["public"], "GLOW Club Reports", "Public club totals, all"), bad_row]
        plan = self.plan(rows)
        for extra in ([], ["--apply"]):
            said = self.refused("move", "--plan", plan, "--vpn-off", *extra)
            self.assert_nothing_written(before)
            for w in words:
                self.assertIn(w, said, f"move {extra}")
        return said

    def assert_copy_refused(self, kind, item, *words):
        before = self.org.state()
        for extra in ([], ["--apply"]):
            said = self.refused("copy", "--kind", kind, "--id", item, "--tag", "#72", "--vpn-off", *extra)
            self.assert_nothing_written(before)
            for w in words:
                self.assertIn(w, said, f"copy {extra}")
        return said

    def test_refuses_a_folder_name_that_is_not_exactly_one_folder_of_the_kind(self):
        # none; two; only a dashboard folder; a folder's name in another case (SOQL's = ignores case:
        # the name is compared exactly, in Python)
        for name in ("Nowhere Folder", "Old Exports", "GLOW Club Dashboards", "glow club reports", "DECOMMISSIONED"):
            o = self.fresh()
            self.assert_move_refused(("report", o.rid["mentors"], name, ""), name)
        # the control: a name one report folder and one dashboard folder share is one of the kind
        o = self.fresh()
        self.ok("move", "--plan", self.plan([("report", o.rid["mentors"], "Shared Name", "")]), "--vpn-off", "--apply")
        self.assertEqual(o.report(o.rid["mentors"])["OwnerId"], o.fid["r_shared"])

    def test_refuses_to_touch_the_attendance_folders(self):
        o = self.fresh()
        self.assert_move_refused(("report", o.rid["att"], "GLOW Club Reports", ""), "Attendance")
        o = self.fresh()
        self.assert_move_refused(("report", o.rid["mentors"], "Attendance", ""), "Attendance")
        for kind, key in (("report", "att"), ("dashboard", "jotform")):
            o = self.fresh()
            self.assert_copy_refused(kind, o.rid[key] if kind == "report" else o.did[key], "Attendance")
        # the control: only a folder named exactly "Attendance" is protected, not "Attendance Archive"
        o = self.fresh()
        self.ok("move", "--plan", self.plan([("report", o.rid["mentors"], "Attendance Archive", ""),
                                             ("report", o.rid["archived"], "GLOW Club Reports", "")]),
                "--vpn-off", "--apply")
        self.assertEqual(o.report(o.rid["mentors"])["OwnerId"], o.fid["r_attarch"])
        self.assertEqual(o.report(o.rid["archived"])["OwnerId"], o.fid["r_cat"])
        self.ok("copy", "--kind", "report", "--id", o.rid["archived"], "--tag", "#72", "--vpn-off", "--apply")
        self.assertEqual(len(o.posts()), 1)

    def test_refuses_to_retire_a_report_a_remaining_dashboard_uses(self):
        # used by one dashboard outside Decommissioned; by two outside; by one inside and one outside
        for key, dash in (("meet", "attendance"), ("girls", "training_old"), ("mixed", "training_old")):
            o = self.fresh()
            said = self.assert_move_refused(("report", o.rid[key], "Decommissioned", ""))
            self.assertTrue(o.did[dash] in said or dict((k, t) for k, t, _, _ in DASHBOARDS)[dash] in said,
                            f"the refusal names the dashboard that uses it:\n{said}")
        # the controls: used only by a dashboard already in Decommissioned; a used report moved elsewhere
        o = self.fresh()
        self.ok("move", "--plan", self.plan([("report", o.rid["observed"], "Decommissioned", ""),
                                             ("report", o.rid["girls"], "GLOW Club Reports", "")]),
                "--vpn-off", "--apply")
        self.assertEqual(o.report(o.rid["observed"])["OwnerId"], o.fid["r_decom"])
        self.assertEqual(o.report(o.rid["girls"])["OwnerId"], o.fid["r_cat"])

    def test_refuses_a_label_over_the_limit(self):
        for label in (L41, L60):
            o = self.fresh()
            self.assert_move_refused(("report", o.rid["mentors"], "GLOW Club Reports", label), "40")
        o = self.fresh()
        self.ok("move", "--plan", self.plan([("report", o.rid["mentors"], "GLOW Club Reports", L40)]),
                "--vpn-off", "--apply")
        self.assertEqual(o.report(o.rid["mentors"])["Name"], L40)
        # a report whose CURRENT label is over 40 is not relabelled: undo could not put that label back
        for label in ("Implementation by month", L40):
            o = self.fresh()
            self.assert_move_refused(("report", o.rid["long"], "GLOW Club Reports", label), "40")
        # the control: moved with its label kept
        o = self.fresh()
        self.ok("move", "--plan", self.plan([("report", o.rid["long"], "GLOW Club Reports", "")]),
                "--vpn-off", "--apply")
        self.assertEqual((o.report(o.rid["long"])["OwnerId"], o.report(o.rid["long"])["Name"]), (o.fid["r_cat"], LONG))
        # a dashboard is moved and renamed by hand in Lightning: the API refuses every dashboard PATCH
        for to, label in (("GLOW Club Dashboards", ""), ("Decommissioned", "Old training")):
            o = self.fresh()
            self.assert_move_refused(("dashboard", o.did["training_old"], to, label), "Lightning")

    def test_copy_refuses_without_exactly_one_decommissioned_folder(self):
        for kind, counts in (("report", dict(decom_reports=0)), ("report", dict(decom_reports=2)),
                             ("dashboard", dict(decom_dashboards=0)), ("dashboard", dict(decom_dashboards=2))):
            o = self.fresh(**counts)
            self.assert_copy_refused(kind, o.rid["meet"] if kind == "report" else o.did["attendance"],
                                     "Decommissioned")
        # the other kind's Decommissioned folder does not count
        o = self.fresh(decom_reports=0)
        self.ok("copy", "--kind", "dashboard", "--id", o.did["attendance"], "--tag", "#72", "--vpn-off", "--apply")
        self.assertEqual(len(o.posts()), 1)

    def test_never_sends_delete_and_never_reads_records(self):
        o = self.org
        self.ok("list", "--vpn-off", "--folder", "DHIS2 Reports", "--folder", "DHIS2 Dashboards")
        self.ok("copy", "--kind", "report", "--id", o.rid["mentors"], "--tag", "#72", "--vpn-off", "--apply")
        self.ok("copy", "--kind", "dashboard", "--id", o.did["reporting"], "--tag", "#72", "--vpn-off", "--apply")
        self.ok("move", "--plan", self.plan(self.move_plan()), "--vpn-off", "--apply")
        self.ok("undo", "--ledger", self.ledger_path, "--vpn-off", "--apply")
        self.assertTrue(o.calls and o.seen)
        self.assertLessEqual({c[0] for c in o.calls}, {"GET", "POST", "PATCH"})
        for soql in o.seen:
            self.assertLessEqual(soql_objects(soql), ALLOWED_OBJECTS, soql)
            self.assertNotIn("fields(", soql.lower(), soql)
        for _method, path, _ in o.calls:
            self.assertRegex(path, r"^/services/data/v67\.0/analytics/(reports|dashboards)\b", path)
        source = read(TOOL)
        self.assertNotRegex(source, r"""['"]DELETE['"]""", "a DELETE in the tool")
        self.assertNotRegex(source, r"\.delete\(", "a delete call in the tool")

    def test_every_subcommand_refuses_without_vpn_off(self):
        o = self.org
        plan = self.plan(self.move_plan())
        ledger = os.path.join(self.tmp.name, "old_ledger.csv")
        with open(ledger, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=LEDGER_COLS, lineterminator="\n")
            w.writeheader()
            w.writerow({"when": "2026-10-23T10:00:00Z", "action": "move", "kind": "report", "id": o.rid["meet"],
                        "from_folder_id": o.fid["r_dhis2"], "to_folder_id": o.fid["r_cat"],
                        "old_label": "Club meet freq by month and region", "new_label": "Club meeting frequency",
                        "status": "ok", "http": "200"})
        commands = [
            ["list", "--folder", "DHIS2 Reports"],
            ["copy", "--kind", "report", "--id", o.rid["meet"], "--tag", "#72"],
            ["copy", "--kind", "dashboard", "--id", o.did["attendance"], "--tag", "#72", "--apply"],
            ["move", "--plan", plan],
            ["move", "--plan", plan, "--apply"],
            ["undo", "--ledger", ledger],
            ["undo", "--ledger", ledger, "--apply"],
        ]
        for argv in commands:
            said = self.refused(*argv)
            self.assertIn("--vpn-off", said, argv)
            self.assertEqual((o.calls, o.seen), ([], []), f"Salesforce was asked: {argv}")
            self.assertFalse(os.path.exists(self.ledger_path), argv)


class Docs(unittest.TestCase):
    ARCH = os.path.join(REPO, "docs", "ARCHITECTURE.md")
    RUNBOOK = os.path.join(REPO, "docs", "RUNBOOK.md")
    SKILL = os.path.join(REPO, ".claude", "skills", "salesforce", "SKILL.md")
    MONTHLY = "## Monthly Report dashboards in Salesforce"
    SUB = "### Copying and moving reports and dashboards"

    def row(self, text, where):
        rows = [line for line in text.splitlines() if line.startswith("| `tools/sf_report_folders.py")]
        self.assertEqual(len(rows), 1, f"{where}: one table row for tools/sf_report_folders.py")
        return rows[0]

    def test_the_docs_name_the_tool_its_gate_and_its_undo(self):
        arch = self.row(read(self.ARCH), "docs/ARCHITECTURE.md")
        for word in ("--apply", "--vpn-off", "undo", "Decommissioned"):
            self.assertIn(word, arch, f"docs/ARCHITECTURE.md's row names {word}")

        monthly = md_part(self.RUNBOOK, self.MONTHLY)
        self.assertIn(self.SUB, monthly, f"the subsection sits under {self.MONTHLY}")
        part = md_part(self.RUNBOOK, self.SUB)
        for word in ("tools/sf_report_folders.py", "--apply", "--vpn-off", "--limit 1", "undo", "ledger"):
            self.assertIn(word, part, f"RUNBOOK {self.SUB} names {word}")
        for sub in ("list", "copy", "move", "undo"):
            self.assertRegex(part, rf"sf_report_folders\.py\s+{sub}\b", f"RUNBOOK gives the {sub} command")

        writer = self.row(md_part(self.SKILL, "## Writers"), ".claude/skills/salesforce/SKILL.md Writers")
        for word in ("--apply", "--vpn-off", "undo"):
            self.assertIn(word, writer, f"the skill's Writers row names {word}")

    def test_help_answers(self):
        for argv in (["--help"], ["move", "--help"], ["undo", "--help"]):
            done = subprocess.run([sys.executable, TOOL] + argv, capture_output=True, text=True, cwd=REPO,
                                  timeout=60)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("usage", done.stdout.lower())


if __name__ == "__main__":
    unittest.main()
