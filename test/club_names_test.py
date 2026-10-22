#!/usr/bin/env python3
"""
Offline tests for tools/club_names.py (ticket #94): `similar` lists the clubs whose names are near
identical across partners and regions (capitals, spacing, punctuation, accents, small edits).

Everything is fictional: the clubs are the ticket's own invented names ("Sunrise Club" /
"Sunrize Club" ...), the partners are make_fixture.py's PARTNERS, and every girl's name is built
from make_fixture.py's FIRST and LAST word pools. The tool reads files only; every test writes a
Roster export and a Partners export into a temporary directory and runs club_names.main().
"""
import contextlib
import csv
import difflib
import io
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.join(REPO, "test", "fixtures"))
import club_names                                        # noqa: E402
from make_fixture import FIRST, LAST, PARTNERS           # noqa: E402

ALPHA, BETA, GAMMA, DELTA = PARTNERS
ROSTER_COLS = ["girl_id", "partner", "club", "region", "full_name", "last_name", "status",
               "added_date", "removed_date", "source"]
CSV_COLUMNS = ["group", "match", "club", "partner", "region", "form", "country", "sf_name",
               "status", "active_girls", "same_partner"]
COUNTS = re.compile(r"^groups: (\d+) \(same (\d+), folded (\d+), close (\d+)\); clubs in them: (\d+)$")

# the main fixture: (partner, club, region cell, active girls, inactive girls)
MAIN = [
    (ALPHA, "Sunrise Club", "Africa", 3, 1),           # close to Sunrize Club (0.917)
    (BETA, "Sunrize Club", "Asia", 5, 0),
    (GAMMA, "Niñas Unidas", " latin  america ", 2, 0),  # folded: accent and hyphen
    (DELTA, "Ninas-Unidas", "U.S", 4, 0),
    (ALPHA, "Golden Wings", "Africa", 1, 0),           # same (key equal): two partners share it
    (GAMMA, "GOLDEN WINGS", "Asia", 6, 0),
    (DELTA, "Bright Girls", "Africa", 3, 0),           # close (0.87), one partner's own lookalikes
    (DELTA, "Brite Girls", "Africa", 2, 0),
    (ALPHA, "Harbor Club 1", "Africa", 2, 0),          # 0.923, but the digits differ: no group
    (ALPHA, "Harbor Club 2", "Africa", 2, 0),
    (BETA, "Morning Star", "Asia", 3, 0),              # 0.75: no group
    (GAMMA, "Evening Star", "Latin America", 3, 0),
    (BETA, "River Roots", "Asia", 4, 0),               # nothing like it
]
MAIN_GROUPS = [["Sunrise Club", "Sunrize Club"], ["Niñas Unidas", "Ninas-Unidas"],
               ["Golden Wings", "GOLDEN WINGS"], ["Bright Girls", "Brite Girls"]]
LONERS = ["Harbor Club 1", "Harbor Club 2", "Morning Star", "Evening Star", "River Roots"]


class Workspace:
    """A temporary directory with the files club_names reads; every girl gets a distinct
    fictional name from make_fixture's pools, and the names written are kept in self.girls."""

    def __init__(self, tmp):
        self.tmp, self.girls, self._n = tmp, [], 0

    def path(self, name):
        return os.path.join(self.tmp, name)

    def next_girl(self):
        first = FIRST[self._n % len(FIRST)]
        last = LAST[(self._n // len(FIRST) + self._n) % len(LAST)]
        self._n += 1
        name = f"{first} {last}"
        self.girls.append(name)
        return name

    def roster(self, clubs, name="roster.csv"):
        """clubs: (partner, club, region cell, active girls, inactive girls)."""
        path = self.path(name)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(ROSTER_COLS)
            for partner, club, region, active, inactive in clubs:
                for status, count in (("active", active), ("inactive", inactive)):
                    for _ in range(count):
                        girl = self.next_girl()
                        w.writerow([f"DEMOCLUB-SAMPLE-{self._n:03d}", partner, club, region, girl,
                                    girl.split()[-1], status, "2026-09-01",
                                    "2026-10-01" if status != "active" else "", "test"])
        return path

    def partners(self, marked_no=(), name="partners.csv"):
        path = self.path(name)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["partner", "region", "notes", "jotform"])
            for p in PARTNERS:
                w.writerow([p, "Africa", "", "no" if p in marked_no else ""])
        return path

    def countries(self, rows, name="countries.csv"):
        path = self.path(name)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["partner", "country"])
            w.writerows(rows)
        return path

    def summary(self, region, entries, name):
        """The sync's --summary-json shape (only the keys around sf_names)."""
        path = self.path(name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"form": "262382821971058", "region": region, "apply": False, "roster_clubs": 3,
                       "warnings": [], "calls": [], "sf_names": entries}, f, indent=1)
        return path


def run_main(argv):
    """club_names.main(argv) with no network and no subprocess: (exit code, stdout + stderr)."""
    out, err = io.StringIO(), io.StringIO()
    env = {k: v for k, v in os.environ.items() if k != "JOTFORM_API_KEY"}

    def refuse(*a, **k):
        raise AssertionError("club_names must read files only (a network or subprocess call was made)")

    with unittest.mock.patch.dict(os.environ, env, clear=True), \
            unittest.mock.patch.object(socket.socket, "connect", refuse), \
            unittest.mock.patch.object(socket, "create_connection", refuse), \
            unittest.mock.patch.object(subprocess, "Popen", refuse), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = club_names.main(argv)
        except SystemExit as e:
            code = e.code
    return code, out.getvalue() + err.getvalue()


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def counts_line(test, text):
    """The one counts line, as ints (groups, same, folded, close, clubs), and its line index."""
    lines = text.splitlines()
    found = [(i, COUNTS.match(line.strip())) for i, line in enumerate(lines)]
    found = [(i, m) for i, m in found if m]
    test.assertEqual(len(found), 1, f"expected one counts line in:\n{text}")
    i, m = found[0]
    return tuple(int(g) for g in m.groups()), i


class SimilarClubNames(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    # ------------------------------------------------------------- the command, broad
    def test_similar_lists_lookalike_clubs_of_different_partners_in_one_group(self):
        roster, partners = self.ws.roster(MAIN), self.ws.partners()
        code, out = run_main(["similar", "--roster", roster, "--partners", partners])
        self.assertIn(code, (0, None), out)
        counts, at = counts_line(self, out)
        self.assertEqual(counts, (4, 1, 1, 2, 8), out)
        lines = out.splitlines()

        def line_of(club, partner):
            hits = [i for i, line in enumerate(lines) if club in line and partner in line]
            self.assertTrue(hits, f"no line names {club!r} with its partner {partner!r}:\n{out}")
            return hits[0]

        sunrise, sunrize = line_of("Sunrise Club", ALPHA), line_of("Sunrize Club", BETA)
        self.assertIn("Africa Attendance Form", lines[sunrise])
        self.assertIn("Asia Attendance Form", lines[sunrize])
        self.assertTrue(at < min(sunrise, sunrize), "the counts line comes before the groups")
        # one group: no club of another group is printed between the two
        others = [c for g in MAIN_GROUPS[1:] for c in g]
        for line in lines[min(sunrise, sunrize) + 1:max(sunrise, sunrize)]:
            for club in others:
                self.assertNotIn(club, line, f"{club!r} printed inside the Sunrise group:\n{out}")
        # every grouped club is printed with its partner, the others not at all
        for partner, club, *_ in MAIN:
            if club in LONERS:
                self.assertNotIn(club, out)
            else:
                line_of(club, partner)
        self.assertIn("Latin America Attendance Form", lines[line_of("Niñas Unidas", GAMMA)])
        self.assertIn("U.S Attendance Form", lines[line_of("Ninas-Unidas", DELTA)])

    def test_the_csv_has_one_row_per_club_with_country_form_and_sf_name(self):
        roster, partners = self.ws.roster(MAIN), self.ws.partners()
        countries = self.ws.countries([["  fixture partner ALPHA ", "Kenya"], [BETA, "Nepal"],
                                       [GAMMA, "Peru"]])            # Delta: none
        africa = self.ws.summary("Africa", [
            {"qid": "10", "club": "Sunrise Club", "partner": ALPHA, "value": "Sunrise Club"},
            {"qid": "11", "club": "Golden Wings", "partner": ALPHA, "value": f"Golden Wings - {ALPHA}"},
            {"qid": None, "club": "Bright Girls", "partner": DELTA, "value": "Bright Girls"},
        ], "plan_africa.json")
        asia = self.ws.summary("Asia", [
            {"qid": "20", "club": "Sunrize Club", "partner": BETA, "value": "Sunrize Club"},
            {"qid": "21", "club": "GOLDEN WINGS", "partner": GAMMA, "value": f"GOLDEN WINGS - {GAMMA}"},
            {"qid": "22", "club": "River Roots", "partner": BETA, "value": "River Roots"},
        ], "plan_asia.json")
        out_csv = self.ws.path("similar.csv")
        code, out = run_main(["similar", "--roster", roster, "--partners", partners,
                              "--countries", countries, "--sf-names", africa, "--sf-names", asia,
                              "--csv", out_csv])
        self.assertIn(code, (0, None), out)
        header, rows = read_csv(out_csv)
        self.assertEqual(header, CSV_COLUMNS)
        by_club = {r["club"]: r for r in rows}
        self.assertEqual(len(rows), 8, rows)
        self.assertEqual(sorted(by_club), sorted(c for g in MAIN_GROUPS for c in g))
        want = {   # club: (match, partner, region, form, country, sf_name, active_girls, same_partner)
            "Sunrise Club": ("close", ALPHA, "Africa", "Africa Attendance Form", "Kenya", "Sunrise Club", "3", "no"),
            "Sunrize Club": ("close", BETA, "Asia", "Asia Attendance Form", "Nepal", "Sunrize Club", "5", "no"),
            "Niñas Unidas": ("folded", GAMMA, "Latin America", "Latin America Attendance Form", "Peru", "", "2", "no"),
            "Ninas-Unidas": ("folded", DELTA, "U.S", "U.S Attendance Form", "", "", "4", "no"),
            "Golden Wings": ("same", ALPHA, "Africa", "Africa Attendance Form", "Kenya",
                             f"Golden Wings - {ALPHA}", "1", "no"),
            "GOLDEN WINGS": ("same", GAMMA, "Asia", "Asia Attendance Form", "Peru",
                             f"GOLDEN WINGS - {GAMMA}", "6", "no"),
            "Bright Girls": ("close", DELTA, "Africa", "Africa Attendance Form", "", "Bright Girls", "3", "yes"),
            "Brite Girls": ("close", DELTA, "Africa", "Africa Attendance Form", "", "", "2", "yes"),
        }
        cols = ["match", "partner", "region", "form", "country", "sf_name", "active_girls", "same_partner"]
        for club, values in want.items():
            with self.subTest(club=club):
                self.assertEqual(tuple(by_club[club][c] for c in cols), values)
                self.assertEqual(by_club[club]["status"], "active")
        # one group id per group, a different one for every group
        ids = [{by_club[c]["group"] for c in g} for g in MAIN_GROUPS]
        for g, got in zip(MAIN_GROUPS, ids):
            self.assertEqual(len(got), 1, f"{g} split over groups {got}")
        self.assertEqual(len({next(iter(s)) for s in ids}), len(MAIN_GROUPS))
        self.assertTrue(all(r["group"].strip() for r in rows))

    def test_without_countries_or_sf_names_those_columns_are_blank(self):
        roster, partners = self.ws.roster(MAIN), self.ws.partners()
        out_csv = self.ws.path("plain.csv")
        code, out = run_main(["similar", "--roster", roster, "--partners", partners, "--csv", out_csv])
        self.assertIn(code, (0, None), out)
        header, rows = read_csv(out_csv)
        self.assertEqual(header, CSV_COLUMNS)
        self.assertEqual(len(rows), 8)
        self.assertEqual({(r["country"], r["sf_name"]) for r in rows}, {("", "")})

    # ------------------------------------------------------------- fold / match_kind
    def test_fold_drops_case_accents_spacing_and_punctuation(self):
        cases = [
            ("  Niñas  Emprendedoras ", "ninas emprendedoras"),     # the ticket's examples
            ("G.L.O.W. Club", "glow club"),
            ("Bishop’s Girls", "bishops girls"),
            ("Sun-Rise Club", "sun rise club"),
            ("O'Brien Club", "obrien club"),                         # ' removed, not a space
            ("Bishop`s  Club", "bishops club"),                      # backtick removed
            ("Ångström_Girls", "angstrom girls"),                    # accents; _ is a space
            ("Club #3 (B)", "club 3 b"),                             # digits kept, the rest spaces
            ("Café/Club", "cafe club"),
            ("ÉTOILES\tdu  Sud", "etoiles du sud"),
            ("Sunrise Club", "sunrise club"),
            ("", ""),
        ]
        for name, want in cases:
            with self.subTest(name=name):
                self.assertEqual(club_names.fold(name), want)

    def test_match_kind_same_folded_close_or_none(self):
        cases = [
            # the ticket's examples
            ("Sunrise Club", "SUNRISE  CLUB", "same"),
            ("Niñas Unidas", "Ninas-Unidas", "folded"),
            ("Sunrise Club", "Sunrize Club", "close"),               # 0.917
            ("Bright Girls", "Brite Girls", "close"),                # 0.870
            ("Harbor Club 1", "Harbor Club 2", None),                # digits differ, though 0.923
            ("Morning Star", "Evening Star", None),                  # 0.75
            # more of each
            ("Golden Wings", " golden wings", "same"),
            ("G.L.O.W. Club", "Glow Club", "folded"),
            ("Bishop’s Girls", "Bishops Girls", "folded"),
            ("Harbor Club 1", "Harbour Club 1", "close"),            # same digits, 0.963
            ("Harbor Club 12", "Harbor Club 21", None),              # same digits, other order
            ("Harbor Club", "Harbor Club 1", None),                  # one has a digit, 0.917
            ("Sunrise Club", "Sunrize Klub", None),                  # 0.833
            ("River Roots", "Ocean Voices", None),
        ]
        for a, b, want in cases:
            with self.subTest(a=a, b=b):
                self.assertEqual(club_names.match_kind(a, b), want)
                self.assertEqual(club_names.match_kind(b, a), want)

    def test_match_kind_threshold_is_a_lower_bound_on_the_ratio(self):
        bright = difflib.SequenceMatcher(None, "bright girls", "brite girls").ratio()   # 20/23
        cases = [
            ("Sunrise Club", "Sunrize Club", 0.95, None),
            ("Sunrise Club", "Sunrize Club", 0.9, "close"),
            ("Morning Star", "Evening Star", 0.7, "close"),
            ("Morning Star", "Evening Star", 0.76, None),
            ("Bright Girls", "Brite Girls", bright, "close"),        # equal to the threshold
            ("Bright Girls", "Brite Girls", bright + 1e-9, None),
            ("Harbor Club 1", "Harbor Club 2", 0.5, None),           # digits rule at any threshold
            ("Niñas Unidas", "Ninas Unidas", 1.0, "folded"),         # not a ratio question
        ]
        for a, b, threshold, want in cases:
            with self.subTest(a=a, b=b, threshold=threshold):
                self.assertEqual(club_names.match_kind(a, b, threshold=threshold), want)

    def test_threshold_option_changes_the_groups(self):
        roster, partners = self.ws.roster(MAIN), self.ws.partners()
        for threshold, want in (("0.95", (2, 1, 1, 0, 4)), ("0.7", (5, 1, 1, 3, 10))):
            with self.subTest(threshold=threshold):
                code, out = run_main(["similar", "--roster", roster, "--partners", partners,
                                      "--threshold", threshold])
                self.assertIn(code, (0, None), out)
                self.assertEqual(counts_line(self, out)[0], want, out)

    # ------------------------------------------------------------- groups
    def test_three_names_chained_by_close_pairs_form_one_group(self):
        # Sunrise ~ Sunrize (0.917), Sunrize ~ Sunrize Klub (0.917), Sunrise !~ Sunrize Klub (0.833)
        self.assertIsNone(club_names.match_kind("Sunrise Club", "Sunrize Klub"))
        roster = self.ws.roster([
            (ALPHA, "Sunrise Club", "Africa", 2, 0),
            (BETA, "Sunrize Club", "Asia", 3, 0),
            (GAMMA, "Sunrize Klub", "Latin America", 4, 0),
            (DELTA, "Ocean Voices", "Africa", 2, 0),
        ])
        out_csv = self.ws.path("chain.csv")
        code, out = run_main(["similar", "--roster", roster, "--partners", self.ws.partners(),
                              "--csv", out_csv])
        self.assertIn(code, (0, None), out)
        counts, _ = counts_line(self, out)
        self.assertEqual((counts[0], counts[4]), (1, 3), out)
        _, rows = read_csv(out_csv)
        self.assertEqual(sorted(r["club"] for r in rows), ["Sunrise Club", "Sunrize Club", "Sunrize Klub"])
        self.assertEqual(len({r["group"] for r in rows}), 1, rows)
        self.assertEqual({r["match"] for r in rows}, {"close"})
        self.assertEqual({r["same_partner"] for r in rows}, {"no"})

    def test_match_column_is_the_strongest_kind_joining_the_club(self):
        roster = self.ws.roster([
            (ALPHA, "Valley Stars", "Africa", 2, 0),
            (BETA, "VALLEY STARS", "Asia", 2, 0),        # same as Valley Stars
            (GAMMA, "Valley Starz", "Asia", 2, 0),       # only close to both
            (DELTA, "Northern Lights", "Africa", 2, 0),
        ])
        out_csv = self.ws.path("strong.csv")
        code, out = run_main(["similar", "--roster", roster, "--partners", self.ws.partners(),
                              "--csv", out_csv])
        self.assertIn(code, (0, None), out)
        _, rows = read_csv(out_csv)
        self.assertEqual({r["club"]: r["match"] for r in rows},
                         {"Valley Stars": "same", "VALLEY STARS": "same", "Valley Starz": "close"})
        self.assertEqual(len({r["group"] for r in rows}), 1)

    # ------------------------------------------------------------- form and status
    def test_form_column_for_retired_inactive_and_regionless_clubs(self):
        roster = self.ws.roster([
            (ALPHA, "Silver Lights", "Africa", 3, 0),     # on the Africa form
            (DELTA, "Silver Light", "Africa", 2, 0),      # Delta is jotform=no
            (BETA, "Silver-Lights", "Asia", 0, 4),        # nobody active
            (GAMMA, "Silver Lights!", "", 2, 0),          # blank region
            (ALPHA, "Silverlights", "Europe", 5, 0),      # not a region of a form
            (DELTA, "Mountain Flames", "Africa", 2, 0),
        ])
        partners = self.ws.partners(marked_no=(DELTA,))
        out_csv = self.ws.path("forms.csv")
        code, out = run_main(["similar", "--roster", roster, "--partners", partners, "--csv", out_csv])
        self.assertIn(code, (0, None), out)
        _, rows = read_csv(out_csv)
        got = {r["club"]: (r["form"], r["status"], r["active_girls"]) for r in rows}
        self.assertEqual(got, {
            "Silver Lights": ("Africa Attendance Form", "active", "3"),
            "Silver Light": ("retired (jotform=no)", "active", "2"),
            "Silver-Lights": ("none (no active girl)", "inactive", "0"),
            "Silver Lights!": ("none (no region)", "active", "2"),
            "Silverlights": ("none (no region)", "active", "5"),
        })
        by_club = {r["club"]: r for r in rows}
        self.assertEqual(by_club["Silver-Lights"]["region"], "Asia")
        self.assertEqual(by_club["Silver Lights!"]["region"], "")
        self.assertEqual(by_club["Silver Light"]["partner"], DELTA)
        self.assertEqual(len({r["group"] for r in rows}), 1)
        counts, _ = counts_line(self, out)
        self.assertEqual((counts[0], counts[4]), (1, 5), out)

    # ------------------------------------------------------------- privacy, files only
    def test_no_girls_name_is_printed(self):
        roster, partners = self.ws.roster(MAIN), self.ws.partners()
        countries = self.ws.countries([[ALPHA, "Kenya"], [BETA, "Nepal"]])
        summary = self.ws.summary("Africa", [
            {"qid": "10", "club": "Sunrise Club", "partner": ALPHA, "value": "Sunrise Club"}], "plan.json")
        out_csv = self.ws.path("names.csv")
        code, out = run_main(["similar", "--roster", roster, "--partners", partners,
                              "--countries", countries, "--sf-names", summary, "--csv", out_csv])
        self.assertIn(code, (0, None), out)
        with open(out_csv, encoding="utf-8") as f:
            written = f.read()
        self.assertTrue(written.strip() and out.strip())
        surnames = {g.split()[-1] for g in self.ws.girls}
        for name in self.ws.girls:
            self.assertNotIn(name, out)
            self.assertNotIn(name, written)
        for word in surnames:
            self.assertNotIn(word, out)
            self.assertNotIn(word, written)

    def test_the_command_line_runs_offline_and_answers_help(self):
        roster, partners = self.ws.roster(MAIN), self.ws.partners()
        env = {k: v for k, v in os.environ.items() if k != "JOTFORM_API_KEY"}
        tool = os.path.join(REPO, "tools", "club_names.py")
        for argv in (["--help"], ["similar", "--help"]):
            r = subprocess.run([sys.executable, tool, *argv], capture_output=True, text=True, env=env, cwd=REPO)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("usage", r.stdout.lower())
        r = subprocess.run([sys.executable, tool, "similar", "--roster", roster, "--partners", partners],
                           capture_output=True, text=True, env=env, cwd=REPO)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(counts_line(self, r.stdout)[0], (4, 1, 1, 2, 8), r.stdout)


if __name__ == "__main__":
    unittest.main()
