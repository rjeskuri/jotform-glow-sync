#!/usr/bin/env python3
"""
Offline tests for tools/refile_list.py (ticket #237, rulings G1 and G2): the one-time club -> partner list that the
photo mover's re-filing reads (drive-sync/Refile.gs REFILE_LIST; test/drive_sync_refile_test.js).

    python3 tools/refile_list.py --roster <roster.csv> --partners <partners.csv> [--extra <csv>] --out <path>.gs

writes `const REFILE_LIST = [ ... ];`, one {"region", "partner", "club"} object per row, sorted by region, partner,
club. One row per distinct (key(partner), key(club)) of EVERY Roster row with both cells, any status (old folders
belong to clubs now inactive or retired), spelled as glow.sync.roster_pairs spells it (whitespace collapsed; the
first active row's spelling, else the first row's). Region: the club's Roster region (glow.forms.canonical_region),
one row per region when its rows have two; when none of its rows has one, the Partners tab's region for its
partner; else "". --extra (header region, partner, club) adds rows; a duplicate of a list row is dropped. A girl's
name never reaches the file or the output.

The test-author's readings (reversible; the coder follows them):
  P1  The Partners fallback applies only when none of the club's rows has a region: a club with rows in Africa and
      rows with a blank region is one Africa row. The Partners tab's region is used as written there.
  P2  --extra: a row equal to a list row (region, partner and club exactly) is dropped, any other row is added (where
      in the file is not pinned); an --extra file without the region, partner and club columns is refused.
  P3  A refusal exits non-zero and writes no --out file.
  P4  The file is read the way Apps Script reads it: evaluated in node's vm, alone and appended to drive-sync/*.gs
      (test/load_gs.js, so it must not clash with a name they declare); its layout (one object per line) is left
      to the reviewer.

Everything is fictional: partners are make_fixture.py's PARTNERS plus "Fixture Partner Epsilon" and "Fixture
Partner Case <n>", clubs are invented, girls come from make_fixture.py's FIRST and LAST pools. The tool runs
in-process (runpy, network and subprocesses refused) but for one real command-line run.
"""
import contextlib
import csv
import io
import json
import os
import runpy
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "test", "fixtures"))
from make_fixture import FIRST, LAST, PARTNERS  # noqa: E402

TOOL = os.path.join(REPO, "tools", "refile_list.py")
LOAD_GS = os.path.join(REPO, "test", "load_gs.js")
DRIVE_SYNC = os.path.join(REPO, "drive-sync")
ALPHA, BETA, GAMMA, DELTA = PARTNERS
EPSILON = "Fixture Partner Epsilon"
ROSTER_COLS = ["girl_id", "partner", "club", "region", "full_name", "last_name", "status",
               "added_date", "removed_date", "source"]

# REFILE_LIST as Apps Script sees it: the file alone, and appended to drive-sync/*.gs (P4)
NODE_READ = r"""
const fs = require('fs'), path = require('path'), vm = require('vm');
const [loadGsPath, file, dir] = process.argv.slice(1);
const alone = vm.createContext({});
vm.runInContext(fs.readFileSync(file, 'utf8'), alone, { filename: 'RefileList.gs' });
const a = vm.runInContext('typeof REFILE_LIST === "undefined" ? "<undefined>" : JSON.stringify(REFILE_LIST)', alone);
const gs = fs.readdirSync(dir).filter(f => f.endsWith('.gs')).sort().map(f => path.join(dir, f));
const sb = require(loadGsPath).sandbox(gs.concat([file]), {});
const b = vm.runInContext('typeof REFILE_LIST === "undefined" ? "<undefined>" : JSON.stringify(REFILE_LIST)', sb);
process.stdout.write(JSON.stringify({ alone: a, beside: b }));
"""


class Workspace:
    """A temporary directory with the exports refile_list reads; every girl gets a distinct fictional name from
    make_fixture's pools, and the names written are kept in self.girls."""

    def __init__(self, tmp):
        self.tmp, self.girls, self._n, self._ids = tmp, [], 0, 0

    def path(self, name):
        return os.path.join(self.tmp, name)

    def next_girl(self):
        first = FIRST[self._n % len(FIRST)]
        last = LAST[(self._n // len(FIRST) + self._n) % len(LAST)]
        self._n += 1
        name = f"{first} {last}"
        self.girls.append(name)
        return name

    def roster(self, rows, name="roster.csv"):
        """rows: (partner, club, region cell, status[, named]): one girl each, in this order; named False leaves
        the girl's name blank (a row glow.sync.roster_pairs does not count as active)."""
        path = self.path(name)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(ROSTER_COLS)
            for row in rows:
                partner, club, region, status = row[:4]
                girl = self.next_girl() if (row[4] if len(row) > 4 else True) else ""
                self._ids += 1
                w.writerow([f"DEMOCLUB-SAMPLE-{self._ids:03d}", partner, club, region, girl,
                            girl.split()[-1] if girl else "", status, "2026-09-01",
                            "2026-10-01" if status != "active" else "", "test"])
        return path

    def partners(self, rows, name="partners.csv"):
        """rows: (partner, region, jotform)."""
        path = self.path(name)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["partner", "region", "notes", "jotform"])
            for partner, region, jotform in rows:
                w.writerow([partner, region, "", jotform])
        return path

    def table(self, name, header, rows):
        path = self.path(name)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)
        return path


def run_tool(test, argv):
    """tools/refile_list.py run as `python3 tools/refile_list.py <argv>`, in-process, with no network and no
    subprocess: (exit code, stdout + stderr)."""
    test.assertTrue(os.path.isfile(TOOL), "tools/refile_list.py does not exist yet (ticket #237, G1)")
    out, err = io.StringIO(), io.StringIO()
    env = {k: v for k, v in os.environ.items() if k != "JOTFORM_API_KEY"}

    def refuse(*a, **k):
        raise AssertionError("refile_list must read files only (a network or subprocess call was made)")

    with unittest.mock.patch.dict(os.environ, env, clear=True), \
            unittest.mock.patch.object(sys, "argv", [TOOL, *argv]), \
            unittest.mock.patch.object(socket.socket, "connect", refuse), \
            unittest.mock.patch.object(socket, "create_connection", refuse), \
            unittest.mock.patch.object(subprocess, "Popen", refuse), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            runpy.run_path(TOOL, run_name="__main__")
            code = 0
        except SystemExit as e:
            code = e.code
            if isinstance(code, str):         # sys.exit("what to fix"): the interpreter prints it to stderr
                err.write(code + "\n")
                code = 1
    return (0 if code is None else code), out.getvalue() + err.getvalue()


def read_list(test, path):
    """[(region, partner, club)] of the REFILE_LIST the file defines, in its order (P4)."""
    test.assertTrue(os.path.isfile(path), f"--out {path} was not written")
    if not shutil.which("node"):
        test.skipTest("node is not installed (make check runs the JS tests, so there it is)")
    done = subprocess.run(["node", "-e", NODE_READ, LOAD_GS, path, DRIVE_SYNC], capture_output=True, text=True,
                          timeout=60)
    test.assertEqual(done.returncode, 0, f"the --out file does not load as Apps Script:\n{done.stderr}")
    got = json.loads(done.stdout)
    test.assertNotEqual(got["alone"], "<undefined>", "the --out file defines no REFILE_LIST")
    test.assertEqual(got["alone"], got["beside"], "REFILE_LIST differs when loaded beside drive-sync/*.gs")
    rows = json.loads(got["alone"])
    test.assertIsInstance(rows, list)
    for row in rows:
        test.assertIsInstance(row, dict)
        test.assertEqual(sorted(row), ["club", "partner", "region"], row)
        test.assertTrue(all(isinstance(row[k], str) for k in row), row)
    return [(r["region"], r["partner"], r["club"]) for r in rows]


class RefileList(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def run_ok(self, argv):
        code, out = run_tool(self, argv)
        self.assertEqual(code, 0, out)
        return out

    def listed(self, roster, partners, extra=None):
        out_gs = self.ws.path("RefileList.gs")
        argv = ["--roster", roster, "--partners", partners, "--out", out_gs]
        if extra:
            argv += ["--extra", extra]
        self.run_ok(argv)
        return read_list(self, out_gs)

    # ------------------------------------------------------------- the list, broad
    def test_one_row_per_club_and_region_any_status_in_order(self):
        roster = self.ws.roster([
            (ALPHA, "Sunrise Club", "Africa", "active"),
            (ALPHA, "Sunrise Club", "Africa", "active"),
            (ALPHA, "Bright Stars", "Africa", "inactive"),        # no active girl: still listed
            (BETA, "Golden Wings", "Africa", "active"),           # one name, two partners: two clubs
            (DELTA, "Golden Wings", "Asia", "active"),
            (GAMMA, "River Roots", " latin  america ", "active"),  # a retired partner (jotform=no): still listed
            (GAMMA, "Ocean Lights", "asia", "active"),
            (BETA, "Morning Voices", "Asia", "active"),           # rows in two regions: a row each
            (BETA, "Morning Voices", "Africa", "inactive"),
            (DELTA, "Valley Roots", "", "active"),                # no region: its partner's on the Partners tab
            (EPSILON, "Hidden Stars", "", "active"),              # no region anywhere: blank
            (ALPHA, "", "Africa", "active"),                      # no club: no row
            ("", "Lonely Club", "Africa", "active"),              # no partner: no row
            ("fixture partner ALPHA", "evening   lights", "Africa", "inactive"),
            (" Fixture  Partner Alpha ", "Evening  Lights", "Africa", "active"),
        ])
        partners = self.ws.partners([(ALPHA, "Africa", ""), (BETA, "Africa", ""), (GAMMA, "Latin America", "no"),
                                     (DELTA, "Asia", "")])
        want = [
            ("", EPSILON, "Hidden Stars"),
            ("Africa", ALPHA, "Bright Stars"),
            ("Africa", ALPHA, "Evening Lights"),
            ("Africa", ALPHA, "Sunrise Club"),
            ("Africa", BETA, "Golden Wings"),
            ("Africa", BETA, "Morning Voices"),
            ("Asia", BETA, "Morning Voices"),
            ("Asia", DELTA, "Golden Wings"),
            ("Asia", DELTA, "Valley Roots"),
            ("Asia", GAMMA, "Ocean Lights"),
            ("Latin America", GAMMA, "River Roots"),
        ]
        rows = self.listed(roster, partners)
        self.assertEqual(rows, want)
        self.assertEqual(rows, sorted(rows), "sorted by region, partner, club")

    def test_region_from_the_roster_else_the_partners_tab_else_blank(self):
        cases = [   # (the club's region cells, its partner's region on the Partners tab or None: not there, want)
            (["Africa"], "Asia", ["Africa"]),
            ([""], "Asia", ["Asia"]),
            (["", " "], "Latin America", ["Latin America"]),
            ([""], "", [""]),
            ([""], None, [""]),
            (["africa", " Africa "], "", ["Africa"]),
            (["Africa", "Asia"], "Latin America", ["Africa", "Asia"]),
            (["Africa", ""], "Asia", ["Africa"]),                             # P1
            (["U.S", "u.s"], None, ["U.S"]),
            (["  latin america", "Asia", "LATIN AMERICA"], None, ["Asia", "Latin America"]),
        ]
        rows, tab = [], []
        for n, (cells, tab_region, _) in enumerate(cases, 1):
            partner = f"Fixture Partner Case {n}"
            for i, cell in enumerate(cells):
                rows.append((partner, "Bright Stars", cell, "active" if i % 2 == 0 else "inactive"))
            if tab_region is not None:
                tab.append((partner, tab_region, ""))
        got = self.listed(self.ws.roster(rows), self.ws.partners(tab))
        self.assertEqual(len(got), sum(len(w) for *_, w in cases), got)
        for n, (cells, tab_region, want) in enumerate(cases, 1):
            partner = f"Fixture Partner Case {n}"
            with self.subTest(cells=cells, partners_tab=tab_region):
                self.assertEqual(sorted(g for g in got if g[1] == partner),
                                 [(region, partner, "Bright Stars") for region in sorted(want)])

    def test_spelling_is_the_first_active_rows_else_the_first_rows(self):
        roster = self.ws.roster([
            ("FIXTURE PARTNER ALPHA", "bright stars", "Africa", "inactive"),
            ("Fixture Partner Alpha", "Bright  Stars", "Africa", "active"),
            (BETA, "Golden  wings", "Asia", "inactive"),
            (BETA, "Golden Wings", "Asia", "inactive"),
            (GAMMA, "River roots", "Asia", "inactive"),
            (GAMMA, "River Roots", "Asia", "active", False),        # active without a name: not an active girl
            (GAMMA, "RIVER ROOTS", "Asia", "inactive"),
            (DELTA, "ocean lights", "Africa", "inactive"),
            (DELTA, "Ocean Lights", "Asia", "active"),              # both region rows take this spelling
            (" Fixture   Partner  Epsilon", "  Valley   Roots  ", "Africa", "active"),
        ])
        partners = self.ws.partners([(p, "Africa", "") for p in PARTNERS])
        self.assertEqual(self.listed(roster, partners), [
            ("Africa", ALPHA, "Bright Stars"),
            ("Africa", DELTA, "Ocean Lights"),
            ("Africa", EPSILON, "Valley Roots"),
            ("Asia", BETA, "Golden wings"),
            ("Asia", DELTA, "Ocean Lights"),
            ("Asia", GAMMA, "River roots"),
        ])

    def test_inactive_clubs_and_retired_partners_clubs_are_listed(self):
        roster = self.ws.roster([
            (ALPHA, "Sunrise Club", "Africa", "inactive"),
            (ALPHA, "Sunrise Club", "Africa", "inactive"),
            (BETA, "Golden Wings", "Asia", "active"),
            (GAMMA, "River Roots", "Asia", "inactive"),
            (DELTA, "Ocean Lights", "Africa", "removed"),
        ])
        partners = self.ws.partners([(ALPHA, "Africa", ""), (BETA, "Asia", "no"), (GAMMA, "Asia", "no"),
                                     (DELTA, "Africa", "yes")])
        self.assertEqual(self.listed(roster, partners), [
            ("Africa", ALPHA, "Sunrise Club"),
            ("Africa", DELTA, "Ocean Lights"),
            ("Asia", BETA, "Golden Wings"),
            ("Asia", GAMMA, "River Roots"),
        ])

    # ------------------------------------------------------------- --extra
    def test_extra_rows_are_added_and_a_duplicate_of_a_list_row_dropped(self):
        roster = self.ws.roster([(ALPHA, "Sunrise Club", "Africa", "active"),
                                 (BETA, "Golden Wings", "Asia", "active")])
        partners = self.ws.partners([(ALPHA, "Africa", ""), (BETA, "Asia", "")])
        extra = self.ws.table("extra.csv", ["region", "partner", "club"], [
            ["Africa", ALPHA, "Sunrise Club"],             # already listed: dropped
            ["Asia", BETA, "Renamed Stars"],
            ["", DELTA, "Old Name Club"],
            ["Africa", ALPHA, "Sunrise Club Juniors"],
        ])
        rows = self.listed(roster, partners, extra)
        self.assertEqual(sorted(rows), sorted([
            ("Africa", ALPHA, "Sunrise Club"),
            ("Asia", BETA, "Golden Wings"),
            ("Asia", BETA, "Renamed Stars"),
            ("", DELTA, "Old Name Club"),
            ("Africa", ALPHA, "Sunrise Club Juniors"),
        ]))
        self.assertEqual(len(rows), 5, rows)

    def test_an_extra_file_without_its_columns_is_refused(self):
        roster = self.ws.roster([(ALPHA, "Sunrise Club", "Africa", "active")])
        partners = self.ws.partners([(ALPHA, "Africa", "")])
        for header in (["partner", "club"], ["region", "club"], ["name", "notes"]):
            with self.subTest(header=header):
                extra = self.ws.table("extra.csv", header, [["Asia", "Renamed Stars"]])
                out_gs = self.ws.path("refused.gs")
                code, out = run_tool(self, ["--roster", roster, "--partners", partners, "--extra", extra,
                                            "--out", out_gs])
                self.assertNotEqual(code, 0, out)
                self.assertFalse(os.path.exists(out_gs), "--out written for a refused run (P3)")

    # ------------------------------------------------------------- privacy, refusals, the command line
    def test_no_girls_name_in_the_file_or_the_output(self):
        rows = []
        for partner, club, region in ((ALPHA, "Sunrise Club", "Africa"), (BETA, "Golden Wings", "Asia"),
                                      (GAMMA, "River Roots", ""), (DELTA, "Ocean Lights", "Latin America")):
            rows += [(partner, club, region, "active")] * 6 + [(partner, club, region, "inactive")] * 3
        roster = self.ws.roster(rows)
        partners = self.ws.partners([(p, "Asia", "") for p in PARTNERS])
        out_gs = self.ws.path("RefileList.gs")
        output = self.run_ok(["--roster", roster, "--partners", partners, "--out", out_gs])
        with open(out_gs, encoding="utf-8") as f:
            written = f.read()
        self.assertEqual(len(read_list(self, out_gs)), 4)
        self.assertTrue(self.ws.girls)
        for name in self.ws.girls:
            for word in (name, name.split()[-1]):
                self.assertNotIn(word, written)
                self.assertNotIn(word, output)

    def test_a_file_that_is_not_a_roster_export_is_refused(self):
        partners = self.ws.partners([(ALPHA, "Africa", "")])
        sheet = self.ws.table("sheet.csv", ["Timestamp", "Partner Organization Name", "Club Name"],
                              [["8/20/2026 10:14:02", ALPHA, "Sunrise Club"]])
        for label, roster in (("the Partners export", partners), ("an enrollment-style sheet", sheet)):
            with self.subTest(roster=label):
                out_gs = self.ws.path("refused.gs")
                code, out = run_tool(self, ["--roster", roster, "--partners", partners, "--out", out_gs])
                self.assertNotEqual(code, 0, out)
                self.assertFalse(os.path.exists(out_gs), "--out written for a refused run (P3)")

    def test_the_command_line_runs_offline_and_answers_help(self):
        self.assertTrue(os.path.isfile(TOOL), "tools/refile_list.py does not exist yet (ticket #237, G1)")
        roster = self.ws.roster([(ALPHA, "Sunrise Club", "Africa", "active"),
                                 (BETA, "Golden Wings", "", "inactive")])
        partners = self.ws.partners([(ALPHA, "Africa", ""), (BETA, "Asia", "no")])
        env = {k: v for k, v in os.environ.items() if k != "JOTFORM_API_KEY"}
        r = subprocess.run([sys.executable, TOOL, "--help"], capture_output=True, text=True, env=env, cwd=REPO,
                           timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("usage", r.stdout.lower())
        out_gs = self.ws.path("RefileList.gs")
        r = subprocess.run([sys.executable, TOOL, "--roster", roster, "--partners", partners, "--out", out_gs],
                           capture_output=True, text=True, env=env, cwd=REPO, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(read_list(self, out_gs), [("Africa", ALPHA, "Sunrise Club"), ("Asia", BETA, "Golden Wings")])


if __name__ == "__main__":
    unittest.main()
