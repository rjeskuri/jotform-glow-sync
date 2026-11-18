#!/usr/bin/env python3
"""
The backup records the live gate trusts for an automatic go (ticket #146): one tab-separated line
per backup, `<YYYY-MM-DD HH:MM:SS>\\t<target>\\t<id>\\t<path>`, appended to
<checkout>/.claude/live_backups.log - the local time, the path relative to the checkout.

  - glow/live_backups.py record(target, ident, path): appends the line; refuses a path that does
    not exist, and a field holding a tab or a line break (it would forge a second record);
  - glow/backup.py snapshot(): `jotform <form id> backups/<form id>` once both parts are saved, so
    backup_forms.py --form and every tool's own snapshot record;
  - backup_forms.py with no --form: `jotform all backups` after every form's snapshot - never when
    one fails;
  - tools/sheets_client.py export <Tab> <out>: `sheet <Tab> <out>`; export-all <DIR>: `sheet all
    <DIR>` once every tab is written - never when a read fails;
  - tools/github_switches.py backup (read-only): the repository's variables with their values,
    its secrets by name and date only, and all its workflows with their state, into
    backups/github/switches-<stamp>.json, recorded `github all`.

No network anywhere: a fake Jotform client, a fake Sheets service, a gh stub first on PATH. Every
record goes to a temporary checkout - glow.live_backups.REPO, glow.backup.REPO and
CLAUDE_PROJECT_DIR point there (as glow/backup.py lets a test point REPO), or the tool runs from a
copy of glow/ and tools/ - and each test checks the real checkout's record file is untouched.
Fictional names only (test/fixtures/make_fixture.py).
"""
import contextlib
import csv
import datetime
import glob
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
import uuid
from unittest import mock

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import REPO
import backup_forms
import sheets_client
from glow import backup
from glow.jotform import JotformError

F1, F2, F3 = "261234567890123", "262345678901234", "263456789012345"     # fictional form ids
STAMP = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$")
REAL_LOG = os.path.join(REPO, ".claude", "live_backups.log")


def contents(path):
    """A file's bytes, or None when there is none."""
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def records_in(log):
    """[(stamp, target, id, path)] of a .claude/live_backups.log (complete lines only)."""
    if not os.path.exists(log):
        return []
    with open(log, encoding="utf-8") as f:
        text = f.read()
    return [tuple(line.split("\t")) for line in text.split("\n")[:-1]]


class Checkout(unittest.TestCase):
    """A temporary checkout every record of the test goes to."""

    def setUp(self):
        self.real = contents(REAL_LOG)
        self.addCleanup(self.real_log_untouched)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = os.path.realpath(tmp.name)
        os.makedirs(os.path.join(self.root, ".claude"))
        self.log = os.path.join(self.root, ".claude", "live_backups.log")
        self.started = datetime.datetime.now().replace(microsecond=0)
        patches = [mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": self.root}),
                   mock.patch.object(backup, "REPO", self.root)]
        try:
            from glow import live_backups
        except ImportError:
            live_backups = None             # before #146: nothing records, and the log assertions say so
        if live_backups is not None:
            patches.append(mock.patch.object(live_backups, "REPO", self.root))
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        cwd = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, cwd)

    def real_log_untouched(self):
        self.assertEqual(contents(REAL_LOG), self.real, "a test wrote the real checkout's .claude/live_backups.log")

    def records(self):
        """The temporary checkout's records, each checked to be four tab-separated fields."""
        got = records_in(self.log)
        for record in got:
            self.assertEqual(len(record), 4, f"not four tab-separated fields: {record!r}")
        if os.path.exists(self.log):
            with open(self.log, encoding="utf-8") as f:
                text = f.read()
            self.assertTrue(text == "" or text.endswith("\n"), "the last record has no line end")
        return got

    def assert_now(self, stamp):
        """A record's time: the local clock's when it was written, to the second."""
        self.assertRegex(stamp, STAMP)
        when = datetime.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
        self.assertGreaterEqual(when, self.started - datetime.timedelta(seconds=1))
        self.assertLessEqual(when, datetime.datetime.now() + datetime.timedelta(seconds=1))

    def make(self, rel, text="x\n"):
        full = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(text)
        return full


class Record(Checkout):
    """glow/live_backups.py record(): the one writer of the records."""

    @staticmethod
    def lb():
        from glow import live_backups
        return live_backups

    def test_each_backup_is_one_tab_separated_line_appended(self):
        lb = self.lb()
        os.makedirs(os.path.join(self.root, "backups", F1))
        self.make("data/sheet export/SF Pending.csv")
        self.make("backups/github/switches-2026-10-26T101530.json", "{}\n")
        with open(self.log, "w", encoding="utf-8") as f:
            f.write("2026-10-25 08:00:00\tjotform\tall\tbackups\n")              # an older record stays
        lb.record("jotform", F1, f"backups/{F1}")
        lb.record("sheet", "SF Pending", "data/sheet export/SF Pending.csv")
        lb.record("github", "all", "backups/github/switches-2026-10-26T101530.json")
        got = self.records()
        self.assertEqual(got[0], ("2026-10-25 08:00:00", "jotform", "all", "backups"))
        self.assertEqual([r[1:] for r in got[1:]], [("jotform", F1, f"backups/{F1}"),
                                                    ("sheet", "SF Pending", "data/sheet export/SF Pending.csv"),
                                                    ("github", "all", "backups/github/switches-2026-10-26T101530.json")])
        for record in got[1:]:
            self.assert_now(record[0])

    def test_a_path_inside_the_checkout_is_recorded_relative_to_it(self):
        lb = self.lb()
        os.makedirs(os.path.join(self.root, "backups", F2))
        lb.record("jotform", F2, os.path.join(self.root, "backups", F2))
        self.make("data/sheet/Roster.csv")
        lb.record("sheet", "Roster", os.path.join(self.root, "data", "sheet", "Roster.csv"))
        self.assertEqual([r[1:] for r in self.records()], [("jotform", F2, f"backups/{F2}"),
                                                           ("sheet", "Roster", "data/sheet/Roster.csv")])

    def test_a_backup_that_does_not_exist_is_refused_and_nothing_recorded(self):
        lb = self.lb()
        for target, ident, path in [("jotform", F3, f"backups/{F3}"), ("sheet", "Roster", "data/none.csv"),
                                    ("github", "all", os.path.join(self.root, "backups", "github", "none.json"))]:
            with self.subTest(path=path), self.assertRaises((SystemExit, ValueError, OSError)):
                lb.record(target, ident, path)
        self.assertEqual(self.records(), [])

    def test_a_tab_or_a_line_break_in_a_field_is_refused(self):
        # a second line in a field would be a second, forged record
        lb = self.lb()
        self.make("data/x.csv")
        self.make("data/odd\nname.csv")
        self.make("data/odd\rname.csv")
        self.make("data/odd\tname.csv")
        for target, ident, path in [("jotform\tall", F1, "data/x.csv"),
                                    ("sheet", "Roster\n2026-10-26 09:00:00\tjotform\tall", "data/x.csv"),
                                    ("sheet", "Ros\tter", "data/x.csv"), ("sheet", "Roster\r", "data/x.csv"),
                                    ("sheet", "Roster", "data/odd\nname.csv"), ("sheet", "Roster", "data/odd\rname.csv"),
                                    ("sheet", "Roster", "data/odd\tname.csv")]:
            with self.subTest(target=target, ident=ident, path=path), \
                    self.assertRaises((SystemExit, ValueError, OSError)):
                lb.record(target, ident, path)
        self.assertEqual(self.records(), [])


class FakeJotform:
    """The two GETs of a snapshot; `fail` is a path whose GET raises, as the client does."""

    def __init__(self, fail=None):
        self.fail, self.reads = fail, []

    def get(self, path, **params):
        self.reads.append(path)
        if path == self.fail:
            raise JotformError(f"GET {path}: HTTP 502")
        if path.endswith("/questions"):
            return {"1": {"type": "control_head"}, "5": {"type": "control_textbox"}}
        return {"conditions": [{"id": "1"}], "emails": [{}], "integrations": {"salesforceV2": {"x": 1}}}


class Snapshot(Checkout):
    """glow/backup.py snapshot() records its form once both parts are on disk."""

    def test_a_snapshot_records_its_form_once_both_parts_are_saved(self):
        fake = FakeJotform()
        # a stamp from another day: the record's time is the clock's, not the snapshot's name
        backup.snapshot(F1, fake, "2026-09-01T101530")
        backup.snapshot(F2, fake, "2026-09-01T101531", latest=False)          # restore_conditions' kind
        got = self.records()
        self.assertEqual([r[1:] for r in got], [("jotform", F1, f"backups/{F1}"), ("jotform", F2, f"backups/{F2}")])
        for record in got:
            self.assert_now(record[0])
        for form, stamp in ((F1, "2026-09-01T101530"), (F2, "2026-09-01T101531")):
            for part in backup.PARTS:
                self.assertTrue(os.path.exists(os.path.join(self.root, "backups", form, f"{part}-{stamp}.json")))

    def test_a_snapshot_that_fails_records_nothing(self):
        backup.snapshot(F1, FakeJotform(), "2026-09-01T101530")              # the control: recorded
        for fail in (f"/form/{F3}/questions", f"/form/{F3}/properties"):
            with self.subTest(fail=fail), self.assertRaises(JotformError):
                backup.snapshot(F3, FakeJotform(fail), "2026-09-01T101532")
        self.assertEqual([r[1:] for r in self.records()], [("jotform", F1, f"backups/{F1}")])


class BackupForms(Checkout):
    """backup_forms.py: every form, then `jotform all`; one form, that form."""

    def main(self, argv, fake):
        with mock.patch.object(backup_forms, "Client", lambda *a, **k: fake), \
                mock.patch.object(backup_forms, "api_key", lambda *a, **k: "fictional-key"), \
                mock.patch.object(backup_forms, "FORMS", {F1: "one", F2: "two", F3: "three"}), \
                mock.patch.object(backup_forms, "REPO", self.root), \
                mock.patch.object(sys, "argv", ["backup_forms.py", *argv]), \
                contextlib.redirect_stdout(io.StringIO()):
            backup_forms.main()

    def test_every_form_then_all(self):
        self.main([], FakeJotform())
        got = self.records()
        self.assertEqual([r[1:] for r in got],
                         [("jotform", F, f"backups/{F}") for F in (F1, F2, F3)] + [("jotform", "all", "backups")])
        for record in got:
            self.assert_now(record[0])

    def test_one_form_records_that_form_and_not_all(self):
        self.main(["--form", F2], FakeJotform())
        self.assertEqual([r[1:] for r in self.records()], [("jotform", F2, f"backups/{F2}")])

    def test_a_form_that_fails_means_no_record_of_all(self):
        with self.assertRaises((JotformError, SystemExit)):
            self.main([], FakeJotform(fail=f"/form/{F2}/properties"))
        got = [r[1:] for r in self.records()]
        self.assertIn(("jotform", F1, f"backups/{F1}"), got)                  # saved before the failure
        self.assertNotIn("all", [r[1] for r in got], got)
        self.assertNotIn(F2, [r[1] for r in got], got)


class FakeSheets:
    """spreadsheets().get (the tab list) and spreadsheets().values().get (a tab's values) of an
    in-memory spreadsheet; reading tab `fail` raises."""

    class Request:
        def __init__(self, answer):
            self.answer = answer

        def execute(self):
            if isinstance(self.answer, BaseException):
                raise self.answer
            return self.answer

    class Values:
        def __init__(self, sheet):
            self.sheet = sheet

        def get(self, spreadsheetId, range, **kw):
            title = range.split("!")[0][1:-1].replace("''", "'")
            if title == self.sheet.fail:
                return FakeSheets.Request(RuntimeError(f"HTTP 503 reading {title}"))
            return FakeSheets.Request({"values": [list(r) for r in self.sheet.tabs[title]]})

    def __init__(self, tabs, fail=None):
        self.tabs, self.fail = tabs, fail

    def spreadsheets(self):
        return self

    def values(self):
        return self.Values(self)

    def get(self, spreadsheetId, fields=None, **kw):
        return self.Request({"sheets": [{"properties": {"title": t, "sheetId": n, "sheetType": "GRID",
                                                        "gridProperties": {"rowCount": 100, "columnCount": 10}}}
                                        for n, t in enumerate(self.tabs)]})


class SheetsExport(Checkout):
    """tools/sheets_client.py export / export-all record what they saved."""

    TABS = {"Roster": [["girl_id", "name", "club"], ["G-0001", "Grace Fennwhistle", "Rising Stars"],
                       ["G-0002", "Amara Ostrivane", "Golden Wings"]],
            "Partners": [["partner", "region", "jotform"], ["Fixture Partner Alpha", "Africa", "yes"]],
            "SF Pending": [["club", "status"], ["Morning Lights", "new"]]}

    def run_main(self, argv, svc):
        errors = types.ModuleType("googleapiclient.errors")
        errors.HttpError = type("HttpError", (Exception,), {})
        pkg = types.ModuleType("googleapiclient")
        pkg.errors = errors
        with mock.patch.dict(sys.modules, {"googleapiclient": pkg, "googleapiclient.errors": errors}), \
                mock.patch.object(sheets_client, "service", lambda: svc), \
                mock.patch.object(sheets_client, "spreadsheet_id", lambda: "SHEET"), \
                mock.patch.object(sys, "argv", ["sheets_client.py", *argv]), \
                contextlib.redirect_stdout(io.StringIO()):
            sheets_client.main()

    def read_csv(self, rel):
        with open(os.path.join(self.root, rel), newline="", encoding="utf-8") as f:
            return list(csv.reader(f))

    def test_an_export_records_its_tab_and_file(self):
        svc = FakeSheets(self.TABS)
        self.run_main(["export", "Roster", "data/sheet/Roster.csv"], svc)
        self.run_main(["export", "SF Pending", os.path.join(self.root, "data", "sheet export", "SF Pending.csv")], svc)
        self.assertEqual(self.read_csv("data/sheet/Roster.csv"), self.TABS["Roster"])
        got = self.records()
        self.assertEqual([r[1:] for r in got], [("sheet", "Roster", "data/sheet/Roster.csv"),
                                                ("sheet", "SF Pending", "data/sheet export/SF Pending.csv")])
        for record in got:
            self.assert_now(record[0])

    def test_an_export_all_records_all_once_every_tab_is_written(self):
        self.run_main(["export-all", "data/sheet_all"], FakeSheets(self.TABS))
        for tab, rows in self.TABS.items():
            self.assertEqual(self.read_csv(f"data/sheet_all/{tab}.csv"), rows)
        got = [r[1:] for r in self.records()]
        self.assertEqual([r for r in got if r[1] == "all"], [("sheet", "all", "data/sheet_all")])
        self.assertEqual(got[-1], ("sheet", "all", "data/sheet_all"), "`sheet all` is recorded last")

    def test_a_read_that_fails_records_nothing_for_it(self):
        svc = FakeSheets(self.TABS, fail="Partners")
        self.run_main(["export", "Roster", "data/Roster.csv"], svc)          # the control: recorded
        with self.assertRaises((RuntimeError, SystemExit)):
            self.run_main(["export-all", "data/sheet_all"], svc)
        with self.assertRaises((RuntimeError, SystemExit)):
            self.run_main(["export", "Partners", "data/Partners.csv"], svc)
        got = [r[1:] for r in self.records()]
        self.assertEqual(got[:1], [("sheet", "Roster", "data/Roster.csv")], "the control export is not recorded")
        self.assertNotIn("all", [r[1] for r in got], got)
        self.assertNotIn("Partners", [r[1] for r in got], got)


GH_STUB = r'''
import json, os, sys
args = sys.argv[1:]
with open(os.environ["GH_CALLS"], "a", encoding="utf-8") as f:
    f.write(json.dumps(args) + "\n")
with open(os.environ["GH_DATA"], encoding="utf-8") as f:
    data = json.load(f)
if args[:2] == ["repo", "view"]:                     # which repository: a fictional one
    print("o/r" if ("-q" in args or "--jq" in args) else json.dumps({"nameWithOwner": "o/r"}))
    sys.exit(0)
kind = next((w for w in ("variable", "secret", "workflow") if w in args), None)
if kind is None or "list" not in args:
    sys.exit(0)
if os.environ.get("GH_FAIL") == kind:
    sys.stderr.write("HTTP 502: Bad Gateway\n")
    sys.exit(1)
rows = data[kind]
if kind == "workflow" and "--all" not in args and "-a" not in args:     # gh hides disabled ones
    rows = [r for r in rows if r["state"] == "active"]
fields = None
for i, a in enumerate(args):
    if a == "--json" and i + 1 < len(args):
        fields = args[i + 1].split(",")
    elif a.startswith("--json="):
        fields = a[len("--json="):].split(",")
if fields is None:                                   # a table, as gh prints one (no secret values)
    for r in rows:
        print("\t".join(str(v) for k, v in r.items() if k != "value" or kind != "secret"))
    sys.exit(0)
print(json.dumps([{k: r[k] for k in fields if k in r} for r in rows]))
'''


class GithubSwitches(unittest.TestCase):
    """tools/github_switches.py backup, run as its command line from a copy of glow/ and tools/
    (so its records and backups land in the copy), with gh a stub that answers the list commands
    from fixtures and logs every call. The stub gives a secret's value only to a caller that asks
    for a `value` field - which the real gh never has - so a tool that asks, or saves whatever it
    gets, is caught."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = os.path.realpath(tmp.name)
        ignore = shutil.ignore_patterns("__pycache__")
        shutil.copytree(os.path.join(REPO, "glow"), os.path.join(self.root, "glow"), ignore=ignore)
        shutil.copytree(os.path.join(REPO, "tools"), os.path.join(self.root, "tools"), ignore=ignore)
        os.makedirs(os.path.join(self.root, ".claude"))
        side = tempfile.TemporaryDirectory()
        self.addCleanup(side.cleanup)
        self.bin = os.path.join(side.name, "bin")
        os.makedirs(self.bin)
        stub = os.path.join(side.name, "gh_stub.py")
        with open(stub, "w", encoding="utf-8") as f:
            f.write(GH_STUB)
        with open(os.path.join(self.bin, "gh"), "w", encoding="utf-8") as f:
            f.write(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(stub)} \"$@\"\n")
        os.chmod(os.path.join(self.bin, "gh"), 0o755)
        self.calls = os.path.join(side.name, "gh.calls")
        self.secret = "never-saved-" + uuid.uuid4().hex                       # a secret's "value"
        self.value = "apply-" + uuid.uuid4().hex[:8]                          # a variable's value
        self.variables = [{"name": "AUTO_SYNC_APPLY", "value": "true", "updatedAt": "2026-10-20T08:15:00Z",
                           "visibility": "private"},
                          {"name": "SF_SYNC", "value": self.value, "updatedAt": "2026-10-22T11:00:00Z",
                           "visibility": "private"}]
        self.secrets = [{"name": "GLOW_SA_JSON", "updatedAt": "2026-10-01T00:00:00Z", "visibility": "private",
                         "value": self.secret},
                        {"name": "JOTFORM_API_KEY", "updatedAt": "2026-09-30T12:00:00Z", "visibility": "private",
                         "value": self.secret + "-2"}]
        self.workflows = [{"id": 1001, "name": "auto-sync", "state": "active", "path": ".github/workflows/auto-sync.yml"},
                          {"id": 1002, "name": "nightly-report", "state": "disabled_manually",
                           "path": ".github/workflows/nightly-report.yml"}]
        self.data = os.path.join(side.name, "gh.json")
        with open(self.data, "w", encoding="utf-8") as f:
            json.dump({"variable": self.variables, "secret": self.secrets, "workflow": self.workflows}, f)

    def run_tool(self, *args, fail=""):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("GH_", "GITHUB_"))}
        env.update(PATH=self.bin + os.pathsep + env.get("PATH", "/usr/bin:/bin"), CLAUDE_PROJECT_DIR=self.root,
                   GH_CALLS=self.calls, GH_DATA=self.data, GH_FAIL=fail)
        return subprocess.run([sys.executable, os.path.join(self.root, "tools", "github_switches.py"), *args],
                              cwd=self.root, env=env, capture_output=True, text=True, timeout=60)

    def gh_calls(self):
        if not os.path.exists(self.calls):
            return []
        with open(self.calls, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def assert_read_only(self):
        writes = {"set", "delete", "remove", "enable", "disable", "run", "rerun", "edit", "create", "api"}
        for call in self.gh_calls():
            self.assertFalse(writes & set(call), f"gh called to write: {call}")

    def test_backup_saves_the_three_lists_and_records_github_all(self):
        done = self.run_tool("backup")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        saved = glob.glob(os.path.join(self.root, "backups", "github", "*"))
        self.assertEqual(len(saved), 1, saved)
        name = os.path.basename(saved[0])
        self.assertRegex(name, r"^switches-\d{4}-\d\d-\d\dT\d{6}\.json$")      # glow.backup.stamp()
        with open(saved[0], encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn(self.secret, text, "a secret's value was saved")
        self.assertNotIn(self.secret, done.stdout + done.stderr, "a secret's value was printed")
        data = json.loads(text)
        self.assertLessEqual({"variables", "secrets", "workflows"}, set(data))
        variables = {v["name"]: v for v in data["variables"]}
        self.assertEqual(sorted(variables), ["AUTO_SYNC_APPLY", "SF_SYNC"])
        for v in self.variables:
            for key in ("value", "updatedAt"):
                self.assertEqual(variables[v["name"]].get(key), v[key], f"{v['name']} {key}")
        self.assertEqual(sorted(s["name"] for s in data["secrets"]), ["GLOW_SA_JSON", "JOTFORM_API_KEY"])
        for s in data["secrets"]:
            self.assertLessEqual(set(s), {"name", "updatedAt"}, f"a secret holds more than its name and date: {s}")
            self.assertEqual(s.get("updatedAt"), {x["name"]: x["updatedAt"] for x in self.secrets}[s["name"]])
        self.assertEqual(sorted((w.get("id"), w.get("name"), w.get("state")) for w in data["workflows"]),
                         sorted((w["id"], w["name"], w["state"]) for w in self.workflows),
                         "every workflow, a disabled one too, with its state")
        records = records_in(os.path.join(self.root, ".claude", "live_backups.log"))
        self.assertEqual([r[1:] for r in records], [("github", "all", f"backups/github/{name}")])
        self.assertRegex(records[0][0], STAMP)
        self.assertEqual(records[0][0][:10], name[len("switches-"):len("switches-") + 10], "recorded the day it saved")
        self.assertTrue(self.gh_calls(), "gh was never called")
        self.assert_read_only()

    def test_a_list_that_fails_records_nothing(self):
        for kind in ("variable", "secret", "workflow"):
            with self.subTest(failing=kind):
                before = len(self.gh_calls())
                done = self.run_tool("backup", fail=kind)
                self.assertTrue(any(kind in call and "list" in call for call in self.gh_calls()[before:]),
                                f"the tool never asked gh for the {kind} list: {done.stdout + done.stderr}")
                self.assertNotEqual(done.returncode, 0, f"gh {kind} list failed, yet the backup succeeded")
                records = records_in(os.path.join(self.root, ".claude", "live_backups.log"))
                self.assertEqual([r for r in records if r[1] == "github"], [])
        self.assert_read_only()


if __name__ == "__main__":
    unittest.main(verbosity=1)
