#!/usr/bin/env python3
"""
Offline tests for tools/club_names.py (ticket #94): `similar` lists the clubs whose names are near
identical across partners and regions (capitals, spacing, punctuation, accents, small edits).
Ticket #95: `plan-renames` plans every active club's new name from a format GLOW picks
("{country} - {club}") and what its question 5 (its Salesforce Account name) becomes.

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

    def raw_roster(self, rows, name="raw_roster.csv"):
        """rows: (partner, club, region cell, status), written in this order, one girl each."""
        path = self.path(name)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(ROSTER_COLS)
            for partner, club, region, status in rows:
                girl = self.next_girl()
                w.writerow([f"DEMOCLUB-SAMPLE-{self._n:03d}", partner, club, region, girl,
                            girl.split()[-1], status, "2026-09-01",
                            "2026-10-01" if status != "active" else "", "test"])
        return path

    def partners(self, marked_no=(), name="partners.csv", extra=()):
        """PARTNERS, plus `extra` partners (plan-renames uses a fifth, retired one)."""
        path = self.path(name)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["partner", "region", "notes", "jotform"])
            for p in [*PARTNERS, *extra]:
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
            if isinstance(code, str):         # sys.exit("what to fix"): the interpreter prints it to stderr
                err.write(code + "\n")
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
            (ALPHA, "Silverlights", " Europe ", 5, 0),    # not a region of a form
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
        self.assertEqual(by_club["Silverlights"]["region"], "Europe")    # as written, whitespace collapsed
        self.assertEqual(by_club["Silver Light"]["partner"], DELTA)
        self.assertEqual(len({r["group"] for r in rows}), 1)
        counts, _ = counts_line(self, out)
        self.assertEqual((counts[0], counts[4]), (1, 5), out)

    def test_form_precedence_retired_then_no_active_girl_then_no_region(self):
        # retired (jotform=no) > none (no active girl) > none (no region) > the form's title
        roster = self.ws.roster([
            (DELTA, "Ocean Wings", "Africa", 0, 3),       # jotform=no AND nobody active
            (GAMMA, "Ocean Wing", "", 0, 2),             # blank region AND nobody active
            (BETA, "Ocean-Wings", "", 2, 0),             # blank region, active
            (ALPHA, "OCEAN WINGS", "Asia", 4, 0),        # on the Asia form
            (DELTA, "Golden Roots", "", 2, 0),           # jotform=no AND blank region
            (GAMMA, "Golden Root", "Africa", 3, 0),
        ])
        out_csv = self.ws.path("precedence.csv")
        code, out = run_main(["similar", "--roster", roster, "--partners", self.ws.partners(marked_no=(DELTA,)),
                              "--csv", out_csv])
        self.assertIn(code, (0, None), out)
        _, rows = read_csv(out_csv)
        self.assertEqual({(r["club"], r["partner"]): (r["form"], r["status"]) for r in rows}, {
            ("Ocean Wings", DELTA): ("retired (jotform=no)", "inactive"),
            ("Ocean Wing", GAMMA): ("none (no active girl)", "inactive"),
            ("Ocean-Wings", BETA): ("none (no region)", "active"),
            ("OCEAN WINGS", ALPHA): ("Asia Attendance Form", "active"),
            ("Golden Roots", DELTA): ("retired (jotform=no)", "active"),
            ("Golden Root", GAMMA): ("Africa Attendance Form", "active"),
        })

    def test_region_is_the_first_active_rows_and_blank_partner_or_club_rows_are_skipped(self):
        roster = self.ws.raw_roster([
            (ALPHA, "Rising Voices", "Asia", "inactive"),        # first row, not active
            (ALPHA, "Rising Voices", "Africa", "active"),        # first active row: its region wins
            (ALPHA, "Rising Voices", "Latin America", "active"),
            (BETA, "Rising Voice", "Latin America", "inactive"),  # nobody active: its first row
            (BETA, "Rising Voice", "Asia", "inactive"),
            ("", "Rising Voices", "Africa", "active"),           # no partner: skipped
            (GAMMA, "", "Africa", "active"),                     # no club: skipped
            (DELTA, " ", "Asia", "active"),
            ("  ", "Rising  Voicez", "Asia", "active"),          # no partner: skipped
        ])
        out_csv = self.ws.path("regions.csv")
        code, out = run_main(["similar", "--roster", roster, "--partners", self.ws.partners(), "--csv", out_csv])
        self.assertIn(code, (0, None), out)
        _, rows = read_csv(out_csv)
        self.assertEqual({(r["club"], r["partner"]): (r["region"], r["form"], r["active_girls"]) for r in rows}, {
            ("Rising Voices", ALPHA): ("Africa", "Africa Attendance Form", "2"),
            ("Rising Voice", BETA): ("Latin America", "none (no active girl)", "0"),
        })
        self.assertEqual(counts_line(self, out)[0], (1, 0, 0, 1, 2), out)
        self.assertNotIn("Rising Voicez", out)

    def test_clubs_partners_marks_countries_and_sf_names_are_matched_by_key(self):
        # one girl per row; a club is key(partner) + key(club), spelled as its first active row
        roster = self.ws.raw_roster([
            (ALPHA, "GOLDEN wings", "Asia", "inactive"),                  # first row, not active
            (ALPHA, "Golden Wings", "AFRICA", "active"),                  # first active row
            (ALPHA, "Golden Wings", "Africa", "active"),
            ("fixture  PARTNER alpha", " golden  wings", "Asia", " ACTIVE "),   # the same club
            (BETA, "Golden Wingz", " latin   AMERICA", "Active"),
            (ALPHA, "Sunrise Club", "africa", "active"),
            (DELTA, "Sunrise Club", "u.s", "active"),                     # Delta: jotform=no by key
            (GAMMA, "Sunrise-Club", " europe ", "active"),                # not a region of a form
        ])
        partners = self.ws.path("partners_keyed.csv")
        with open(partners, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows([["partner", "region", "notes", "jotform"], [ALPHA, "Africa", "", ""],
                                     [BETA, "Asia", "", "yes"], [GAMMA, "Latin America", "", ""],
                                     [" fixture partner DELTA ", "U.S", "", " No "]])
        countries = self.ws.countries([["Fixture  Partner   Alpha", "Kenya"], ["FIXTURE PARTNER BETA", "Nepal"]])
        summary = self.ws.summary("Africa", [
            {"qid": "10", "club": "sunrise  club", "partner": ALPHA.upper(), "value": f"Sunrise Club - {ALPHA}"},
            {"qid": "11", "club": "Sunrise Club", "partner": GAMMA, "value": f"Sunrise Club - {GAMMA}"},
            {"qid": "12", "club": "GOLDEN  WINGS", "partner": f" {ALPHA.lower()} ", "value": "Golden Wings"},
        ], "plan_keyed.json")
        out_csv = self.ws.path("keyed.csv")
        code, out = run_main(["similar", "--roster", roster, "--partners", partners, "--countries", countries,
                              "--sf-names", summary, "--csv", out_csv])
        self.assertIn(code, (0, None), out)
        self.assertEqual(counts_line(self, out)[0], (2, 0, 1, 1, 5), out)
        _, rows = read_csv(out_csv)
        cols = ["club", "partner", "region", "form", "country", "sf_name", "status", "active_girls"]
        self.assertEqual(sorted(tuple(r[c] for c in cols) for r in rows), sorted([
            ("Golden Wings", ALPHA, "Africa", "Africa Attendance Form", "Kenya", "Golden Wings", "active", "3"),
            ("Golden Wingz", BETA, "Latin America", "Latin America Attendance Form", "Nepal", "", "active", "1"),
            ("Sunrise Club", ALPHA, "Africa", "Africa Attendance Form", "Kenya", f"Sunrise Club - {ALPHA}",
             "active", "1"),
            ("Sunrise Club", DELTA, "U.S", "retired (jotform=no)", "", "", "active", "1"),
            ("Sunrise-Club", GAMMA, "europe", "none (no region)", "", "", "active", "1"),
        ]))
        self.assertEqual({r["match"] for r in rows if r["club"].startswith("Golden")}, {"close"})

    def test_one_club_name_under_two_partners_is_two_clubs_in_one_group(self):
        roster = self.ws.roster([
            (ALPHA, "Golden Wings", "Africa", 2, 0),
            (BETA, "Golden Wings", "Asia", 3, 0),
            (ALPHA, "Sunrise Club", "Africa", 2, 0),
            (BETA, "Sunrize Club", "Asia", 2, 0),
            (GAMMA, "River Roots", "Latin America", 2, 0),
        ])
        summary = self.ws.summary("Africa", [
            {"qid": "10", "club": "Golden Wings", "partner": ALPHA, "value": f"Golden Wings - {ALPHA}"},
            {"qid": "11", "club": "Golden Wings", "partner": BETA, "value": f"Golden Wings - {BETA}"},
            {"qid": "12", "club": "Sunrise Club", "partner": GAMMA, "value": f"Sunrise Club - {GAMMA}"},
        ], "plan.json")
        reverse = self.ws.summary("Asia", [
            {"qid": "21", "club": "Sunrize Club", "partner": GAMMA, "value": "Sunrize Club"},
        ], "plan_asia.json")
        out_csv = self.ws.path("shared.csv")
        code, out = run_main(["similar", "--roster", roster, "--partners", self.ws.partners(),
                              "--sf-names", summary, "--sf-names", reverse, "--csv", out_csv])
        self.assertIn(code, (0, None), out)
        self.assertEqual(counts_line(self, out)[0], (2, 1, 0, 1, 4), out)
        _, rows = read_csv(out_csv)
        got = {(r["club"], r["partner"]): (r["match"], r["region"], r["form"], r["sf_name"], r["active_girls"])
               for r in rows}
        self.assertEqual(got, {
            ("Golden Wings", ALPHA): ("same", "Africa", "Africa Attendance Form", f"Golden Wings - {ALPHA}", "2"),
            ("Golden Wings", BETA): ("same", "Asia", "Asia Attendance Form", f"Golden Wings - {BETA}", "3"),
            # an sf_names entry of the same club name under another partner is not this club's
            ("Sunrise Club", ALPHA): ("close", "Africa", "Africa Attendance Form", "", "2"),
            ("Sunrize Club", BETA): ("close", "Asia", "Asia Attendance Form", "", "2"),
        })
        golden = {r["group"] for r in rows if r["club"] == "Golden Wings"}
        self.assertEqual(len(golden), 1)
        self.assertNotIn(next(iter(golden)), {r["group"] for r in rows if r["club"] != "Golden Wings"})
        lines = out.splitlines()
        for partner, form in ((ALPHA, "Africa Attendance Form"), (BETA, "Asia Attendance Form")):
            hits = [line for line in lines if "Golden Wings" in line and partner in line and form in line]
            self.assertTrue(hits, f"no line for Golden Wings of {partner} with {form}:\n{out}")

    def test_a_mixed_group_counts_under_its_weakest_match_and_same_partner_is_per_group(self):
        roster = self.ws.roster([
            (ALPHA, "Valley Stars", "Africa", 2, 0),
            (ALPHA, "Valley Starz", "Africa", 2, 0),     # close to both others
            (BETA, "VALLEY STARS", "Asia", 2, 0),        # same as Valley Stars
            (BETA, "Ocean Roots", "Asia", 2, 0),         # Beta's own lookalikes: one partner
            (BETA, "Ocean Root", "Asia", 2, 0),
            (DELTA, "Northern Lights", "Africa", 2, 0),
        ])
        out_csv = self.ws.path("mixed.csv")
        code, out = run_main(["similar", "--roster", roster, "--partners", self.ws.partners(), "--csv", out_csv])
        self.assertIn(code, (0, None), out)
        self.assertEqual(counts_line(self, out)[0], (2, 0, 0, 2, 5), out)
        _, rows = read_csv(out_csv)
        self.assertEqual({(r["club"], r["partner"]): (r["match"], r["same_partner"]) for r in rows}, {
            ("Valley Stars", ALPHA): ("same", "no"),
            ("Valley Starz", ALPHA): ("close", "no"),
            ("VALLEY STARS", BETA): ("same", "no"),
            ("Ocean Roots", BETA): ("close", "yes"),
            ("Ocean Root", BETA): ("close", "yes"),
        })

    def group_kind_run(self, clubs, name):
        roster = self.ws.roster(clubs, name=f"{name}.csv")
        out_csv = self.ws.path(f"{name}_out.csv")
        code, out = run_main(["similar", "--roster", roster, "--partners", self.ws.partners(), "--csv", out_csv])
        self.assertIn(code, (0, None), out)
        return counts_line(self, out)[0], read_csv(out_csv)[1], out

    def test_a_group_counts_under_the_weakest_link_needed_to_connect_it(self):
        # two same-pairs joined only by close links: every club's strongest match is same,
        # but the group needs a close link to be one group, so it counts as close
        self.assertEqual(club_names.match_kind("Valley Stars", "Valley Starz"), "close")
        counts, rows, out = self.group_kind_run([
            (ALPHA, "Valley Stars", "Africa", 2, 0),
            (BETA, "VALLEY STARS", "Asia", 2, 0),
            (GAMMA, "Valley Starz", "Latin America", 2, 0),
            (DELTA, "valley starz", "Africa", 2, 0),
            (DELTA, "Northern Lights", "Africa", 2, 0),
        ], "close_link")
        self.assertEqual(counts, (1, 0, 0, 1, 4), out)
        self.assertEqual({(r["club"], r["partner"]): r["match"] for r in rows}, {
            ("Valley Stars", ALPHA): "same", ("VALLEY STARS", BETA): "same",
            ("Valley Starz", GAMMA): "same", ("valley starz", DELTA): "same"})
        self.assertEqual(len({r["group"] for r in rows}), 1)

    def test_two_same_pairs_joined_only_by_a_folded_link_count_as_folded(self):
        self.assertEqual(club_names.match_kind("Niñas Unidas", "Ninas-Unidas"), "folded")
        counts, rows, out = self.group_kind_run([
            (ALPHA, "Niñas Unidas", "Latin America", 2, 0),
            (BETA, "NIÑAS  UNIDAS", "Latin America", 2, 0),
            (GAMMA, "Ninas-Unidas", "U.S", 2, 0),
            (DELTA, "ninas-unidas", "Asia", 2, 0),
            (DELTA, "River Roots", "Asia", 2, 0),
        ], "folded_link")
        self.assertEqual(counts, (1, 0, 1, 0, 4), out)
        self.assertEqual({r["match"] for r in rows}, {"same"})
        self.assertEqual(len(rows), 4)
        # and a group its same-links alone connect counts as same, whatever else links it
        counts, rows, out = self.group_kind_run([
            (ALPHA, "Golden Wings", "Africa", 2, 0),
            (BETA, "GOLDEN WINGS", "Asia", 2, 0),
            (GAMMA, "golden  wings", "Asia", 2, 0),
        ], "same_link")
        self.assertEqual(counts, (1, 1, 0, 0, 3), out)

    def test_digit_runs_split_by_a_space_are_not_the_same_digits(self):
        self.assertIsNone(club_names.match_kind("Club 1 2", "Club 12"))
        self.assertIsNone(club_names.match_kind("Club 12", "Club 1 2"))

    def test_an_active_row_without_a_name_is_not_an_active_girl(self):
        roster = self.ws.path("blank_name.csv")
        with open(roster, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(ROSTER_COLS)
            w.writerow(["DEMOCLUB-SAMPLE-001", BETA, "Silver Light", "Asia", "  ", "", "active",
                        "2026-09-01", "", "test"])                    # the club's only row
            girl = self.ws.next_girl()
            w.writerow(["DEMOCLUB-SAMPLE-002", ALPHA, "Silver Lights", "Africa", girl, girl.split()[-1],
                        "active", "2026-09-01", "", "test"])
        out_csv = self.ws.path("blank_name_out.csv")
        code, out = run_main(["similar", "--roster", roster, "--partners", self.ws.partners(), "--csv", out_csv])
        self.assertIn(code, (0, None), out)
        _, rows = read_csv(out_csv)
        self.assertEqual({r["club"]: (r["status"], r["active_girls"], r["form"]) for r in rows}, {
            "Silver Light": ("inactive", "0", "none (no active girl)"),
            "Silver Lights": ("active", "1", "Africa Attendance Form"),
        })

    def test_a_chain_of_four_where_only_neighbours_match_is_one_group(self):
        chain = ["Sunrise Club", "Sunrize Club", "Sunrize Klub", "Sunrize Klab"]
        for i, a in enumerate(chain):                 # neighbours close (0.917), the rest below 0.85
            for b in chain[i + 1:]:
                ratio = difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()
                self.assertEqual(ratio >= 0.85, chain.index(b) == i + 1, (a, b, ratio))
        counts, rows, out = self.group_kind_run(
            [(PARTNERS[i], club, ("Africa", "Asia", "Latin America", "U.S")[i], 2, 0)
             for i, club in enumerate(chain)] + [(ALPHA, "Ocean Voices", "Africa", 2, 0)], "chain4")
        self.assertEqual(counts, (1, 0, 0, 1, 4), out)
        self.assertEqual(sorted(r["club"] for r in rows), sorted(chain))
        self.assertEqual(len({r["group"] for r in rows}), 1)

    def test_fold_applies_compatibility_folding(self):
        for name, want in (("ＳＵＮＲＩＳＥ Club", "sunrise club"),     # full-width letters
                           ("Ｇｌｏｗ  Ｃｌｕｂ １", "glow club 1"),        # full-width digit too
                           ("ﬁre Girls", "fire girls"),                 # the fi ligature
                           ("Oﬄine Stars", "offline stars")):          # the ffl ligature
            with self.subTest(name=name):
                self.assertEqual(club_names.fold(name), want)
        self.assertEqual(club_names.match_kind("ＳＵＮＲＩＳＥ Club", "Sunrise Club"), "folded")

    def test_no_lookalikes_prints_zero_groups_and_writes_the_header_only(self):
        roster = self.ws.roster([
            (ALPHA, "Harbor Club 1", "Africa", 2, 0),
            (ALPHA, "Harbor Club 2", "Africa", 2, 0),
            (BETA, "Morning Star", "Asia", 2, 0),
            (GAMMA, "Evening Star", "Latin America", 2, 0),
        ])
        out_csv = self.ws.path("empty.csv")
        code, out = run_main(["similar", "--roster", roster, "--partners", self.ws.partners(), "--csv", out_csv])
        self.assertIn(code, (0, None), out)
        self.assertEqual(counts_line(self, out)[0], (0, 0, 0, 0, 0), out)
        header, rows = read_csv(out_csv)
        self.assertEqual((header, rows), (CSV_COLUMNS, []))

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


# ======================================================================= plan-renames (ticket #95)
#
# Input shapes (the ticket names the options, not the files; these follow `similar`'s own inputs):
#   --countries     a partner,country CSV (header row "partner,country"), read as `similar` reads it
#   --sf-names      the sync's --summary-json files, repeatable, as `similar` reads them: their
#                   `sf_names` list ({qid, club, partner, value}) holds each club's question-5 value
#   --similar-csv   the CSV `similar --csv` writes (task #94's columns)
#   --partners      a Partners export: a partner marked jotform=no is retired, its clubs not planned
# Output: --out CSV with exactly PLAN_COLUMNS, one row per active club in scope, any order.
# Counts: one printed line holding "rename N", "unchanged N" and "refused N" (a ":" or "=" between
# the word and its number is fine), e.g. "to rename 7, unchanged 1, refused 0".
EPSILON = "Fixture Partner Epsilon"        # a fifth fictional partner, marked jotform=no (retired)
PLAN_COLUMNS = ["partner", "club", "region", "old_sf_name", "new_club", "new_sf_name", "action"]
COUNTRY = {ALPHA: "Kenya", BETA: "Kenya", GAMMA: "Peru", DELTA: "Nepal", EPSILON: "Ghana"}

# the plan fixture: (partner, club cell, region cell, active girls, inactive girls, question-5 value
# or None for no sf_names entry)
PLAN_ROSTER = [
    (ALPHA, "Sunrise Club", "Africa", 3, 1, "Sunrise Club"),             # the ticket's example
    (ALPHA, "Kenya - Lotus Club", "Africa", 2, 0, "Kenya - Lotus Club"),  # already in the format
    (ALPHA, "Shining Stars", "Africa", 2, 0, "Shining Stars"),           # plain; its namesake is retired
    (BETA, "Ruby", "Africa", 2, 0, f"Ruby - {BETA}"),                     # long-named (the ticket's example)
    (BETA, "Morning  Star", " asia ", 4, 0, "Morning Star"),             # spacing in the cells
    (GAMMA, "Ruby", " latin  america ", 2, 0, f"Ruby - {GAMMA}"),         # long-named, another country
    (GAMMA, "Niñas Unidas", "Latin America", 3, 0, "Niñas Unidas"),      # accents kept
    (DELTA, "River Roots", "Asia", 2, 0, "River Roots"),
    (DELTA, "Harbor Club 1", "Asia", 0, 3, "Harbor Club 1"),             # inactive: keeps its name
    (EPSILON, "Shining Stars", "Africa", 2, 0, None),                    # retired: keeps its name
    (EPSILON, "Ocean Voices", "Africa", 3, 0, "Ocean Voices"),           # retired: keeps its name
]
# the clubs planned: (partner, club, region) as the Roster spells them, whitespace collapsed,
# region canonical, and whether the club's question 5 is the long form
PLANNED = [
    (ALPHA, "Sunrise Club", "Africa", False),
    (ALPHA, "Kenya - Lotus Club", "Africa", False),
    (ALPHA, "Shining Stars", "Africa", False),
    (BETA, "Ruby", "Africa", True),
    (BETA, "Morning Star", "Asia", False),
    (GAMMA, "Ruby", "Latin America", True),
    (GAMMA, "Niñas Unidas", "Latin America", False),
    (DELTA, "River Roots", "Asia", False),
]
NOT_PLANNED = [(DELTA, "Harbor Club 1"), (EPSILON, "Shining Stars"), (EPSILON, "Ocean Voices")]


def fill(fmt, partner, club, region):
    """The format filled in by hand (no code under test): each placeholder replaced, whitespace
    collapsed."""
    s = fmt
    for name, value in (("country", COUNTRY[partner]), ("club", club), ("partner", partner),
                        ("region", region)):
        s = s.replace("{" + name + "}", value)
    return " ".join(s.split())


def plan_counts(test, text):
    """(rename, unchanged, refused) from the one line that prints all three."""
    found = []
    for line in text.splitlines():
        got = [re.search(rf"\b{word}\b\s*[:=]?\s*(\d+)", line) for word in ("rename", "unchanged", "refused")]
        if all(got):
            found.append(tuple(int(m.group(1)) for m in got))
    test.assertEqual(len(found), 1, f"expected one line with the counts rename N, unchanged N, refused N:\n{text}")
    return found[0]


class PlanRenames(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    # ------------------------------------------------------------- helpers
    def files(self, clubs, tag, countries=None):
        """Roster, Partners (EPSILON retired), countries and two sf-names summaries for `clubs`
        (PLAN_ROSTER's shape). Returns the argv of everything but --format/--scope/--keep-long/--out."""
        roster = self.ws.roster([c[:5] for c in clubs], name=f"{tag}_roster.csv")
        partners = self.ws.partners(marked_no=(EPSILON,), extra=(EPSILON,), name=f"{tag}_partners.csv")
        if countries is None:
            countries = [[p, c] for p, c in COUNTRY.items()]
        countries = self.ws.countries(countries, name=f"{tag}_countries.csv")
        entries = [{"qid": str(100 + i), "club": c[1], "partner": c[0], "value": c[5]}
                   for i, c in enumerate(clubs) if c[5] is not None]
        half = len(entries) // 2                         # two files: --sf-names is repeatable
        first = self.ws.summary("Africa", entries[:half], f"{tag}_sf_1.json")
        second = self.ws.summary("Asia", entries[half:], f"{tag}_sf_2.json")
        return ["--roster", roster, "--partners", partners, "--countries", countries,
                "--sf-names", first, "--sf-names", second]

    def plan(self, clubs, tag, fmt="{country} - {club}", keep_long="yes", scope=("--scope", "all"),
             countries=None, expect_ok=True):
        """Run plan-renames; returns (exit code, output, header, rows or None, out path)."""
        out_csv = self.ws.path(f"{tag}_plan.csv")
        argv = ["plan-renames", *self.files(clubs, tag, countries), "--format", fmt, *scope,
                "--keep-long", keep_long, "--out", out_csv]
        code, out = run_main(argv)
        if expect_ok:
            self.assertIn(code, (0, None), out)
            self.assertTrue(os.path.exists(out_csv), f"no --out written:\n{out}")
        if not os.path.exists(out_csv):
            return code, out, None, None, out_csv
        header, rows = read_csv(out_csv)
        return code, out, header, rows, out_csv

    def by_club(self, rows):
        got = {}
        for r in rows:
            k = (r["partner"], r["club"])
            self.assertNotIn(k, got, f"two rows for {k}")
            got[k] = (r["region"], r["old_sf_name"], r["new_club"], r["new_sf_name"], r["action"])
        return got

    def assert_refused(self, code, out, out_csv, names):
        self.assertNotIn(code, (0, None), f"the plan should be refused:\n{out}")
        self.assertFalse(os.path.exists(out_csv), "a refused plan must not write --out")
        for name in names:
            self.assertIn(name, out, f"refused club {name!r} not named:\n{out}")

    # ------------------------------------------------------------- broad: the plan
    def test_plan_renames_fills_the_format_for_every_club_in_scope(self):
        code, out, header, rows, _ = self.plan(PLAN_ROSTER, "main")
        self.assertEqual(header, PLAN_COLUMNS)
        self.assertEqual(self.by_club(rows), {
            # (partner, club): (region, old_sf_name, new_club, new_sf_name, action)
            (ALPHA, "Sunrise Club"): ("Africa", "Sunrise Club", "Kenya - Sunrise Club",
                                      "Kenya - Sunrise Club", "rename"),
            (ALPHA, "Kenya - Lotus Club"): ("Africa", "Kenya - Lotus Club", "Kenya - Lotus Club",
                                            "Kenya - Lotus Club", "unchanged"),
            (ALPHA, "Shining Stars"): ("Africa", "Shining Stars", "Kenya - Shining Stars",
                                       "Kenya - Shining Stars", "rename"),
            (BETA, "Ruby"): ("Africa", f"Ruby - {BETA}", "Kenya - Ruby", f"Kenya - Ruby - {BETA}", "rename"),
            (BETA, "Morning Star"): ("Asia", "Morning Star", "Kenya - Morning Star",
                                     "Kenya - Morning Star", "rename"),
            (GAMMA, "Ruby"): ("Latin America", f"Ruby - {GAMMA}", "Peru - Ruby", f"Peru - Ruby - {GAMMA}",
                              "rename"),
            (GAMMA, "Niñas Unidas"): ("Latin America", "Niñas Unidas", "Peru - Niñas Unidas",
                                      "Peru - Niñas Unidas", "rename"),
            (DELTA, "River Roots"): ("Asia", "River Roots", "Nepal - River Roots", "Nepal - River Roots",
                                     "rename"),
        })
        self.assertEqual(plan_counts(self, out), (7, 1, 0))
        # girls' names never printed or written
        with open(self.ws.path("main_plan.csv"), encoding="utf-8") as f:
            written = f.read()
        for name in self.ws.girls:
            self.assertNotIn(name, out)
            self.assertNotIn(name, written)
            self.assertNotIn(name.split()[-1], out)

    def test_every_placeholder_is_filled_from_the_clubs_own_partner_country_and_region(self):
        formats = ["{club} ({country})", "{region}: {country} / {club}", "{partner} - {club}",
                   "{country} {region} {partner} {club}"]
        for fmt in formats:
            with self.subTest(format=fmt):
                tag = f"fmt{formats.index(fmt)}"
                code, out, header, rows, _ = self.plan(PLAN_ROSTER, tag, fmt=fmt)
                self.assertEqual(header, PLAN_COLUMNS)
                want = {}
                for partner, club, region, long in PLANNED:
                    new = fill(fmt, partner, club, region)
                    sf = f"{new} - {partner}" if long else new
                    old = f"{club} - {partner}" if long else club
                    want[(partner, club)] = (region, old, new, sf, "rename")   # none is in these formats
                self.assertEqual(self.by_club(rows), want)
                self.assertEqual(plan_counts(self, out), (len(PLANNED), 0, 0))

    def test_only_active_clubs_are_planned_retired_and_inactive_keep_their_names(self):
        code, out, header, rows, _ = self.plan(PLAN_ROSTER, "scope")
        got = {(r["partner"], r["club"]) for r in rows}
        self.assertEqual(got, {(p, c) for p, c, _, _ in PLANNED})
        for k in NOT_PLANNED:
            self.assertNotIn(k, got)
        # a partner with no active club needs no country: nothing of it is planned
        clubs = [c for c in PLAN_ROSTER if c[0] != DELTA] + [(DELTA, "Harbor Club 1", "Asia", 0, 3, None)]
        countries = [[p, c] for p, c in COUNTRY.items() if p not in (DELTA, EPSILON)]
        code, out, header, rows, _ = self.plan(clubs, "nodelta", countries=countries)
        self.assertNotIn(DELTA, {r["partner"] for r in rows})
        self.assertNotIn(EPSILON, {r["partner"] for r in rows})
        self.assertEqual(plan_counts(self, out), (6, 1, 0))

    def test_whitespace_is_collapsed_in_the_new_name(self):
        countries = [[f"  {p.lower()} ", f"  {c.upper()}   "] for p, c in COUNTRY.items()]
        code, out, header, rows, _ = self.plan(PLAN_ROSTER, "spaces", fmt="  {country}   -\t {club}  ",
                                               countries=countries)
        got = self.by_club(rows)
        self.assertEqual(got[(ALPHA, "Sunrise Club")][2:], ("KENYA - Sunrise Club", "KENYA - Sunrise Club", "rename"))
        self.assertEqual(got[(BETA, "Morning Star")][2:], ("KENYA - Morning Star", "KENYA - Morning Star", "rename"))
        self.assertEqual(got[(GAMMA, "Ruby")][2:], ("PERU - Ruby", f"PERU - Ruby - {GAMMA}", "rename"))
        for (_, _), (_, _, new, sf, _) in got.items():
            self.assertEqual(new, " ".join(new.split()))
            self.assertEqual(sf, " ".join(sf.split()))
        # and a club already in the (collapsed) format is unchanged
        code, out, header, rows, _ = self.plan(PLAN_ROSTER, "spaces2", fmt="{country}  -   {club}")
        self.assertEqual(self.by_club(rows)[(ALPHA, "Kenya - Lotus Club")][2:],
                         ("Kenya - Lotus Club", "Kenya - Lotus Club", "unchanged"))
        self.assertEqual(plan_counts(self, out), (7, 1, 0))

    # ------------------------------------------------------------- scope similar
    def test_plan_renames_with_scope_similar_takes_only_the_listed_clubs(self):
        clubs = [
            (ALPHA, "Sunrise Club", "Africa", 3, 0, "Sunrise Club"),
            (BETA, "Sunrize Club", "Asia", 2, 0, "Sunrize Club"),
            (EPSILON, "Sunrise Club", "Africa", 2, 0, None),                    # retired
            (ALPHA, "Golden Wings", "Africa", 1, 0, f"Golden Wings - {ALPHA}"),
            (GAMMA, "GOLDEN WINGS", "Asia", 2, 0, f"GOLDEN WINGS - {GAMMA}"),
            (BETA, "Silver-Lights", "Asia", 0, 3, "Silver-Lights"),              # inactive
            (GAMMA, "River Roots", "Latin America", 2, 0, "River Roots"),
            (DELTA, "Morning Star", "Asia", 2, 0, "Morning Star"),
        ]
        # a hand-written task #94 CSV that lists some clubs, Gamma's GOLDEN WINGS not among them
        similar_csv = self.ws.path("hand_similar.csv")
        with open(similar_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            w.writeheader()
            for group, match, club, partner, region, form, status, n in [
                    (1, "close", "Sunrise Club", ALPHA, "Africa", "Africa Attendance Form", "active", 3),
                    (1, "close", "Sunrize Club", BETA, "Asia", "Asia Attendance Form", "active", 2),
                    (1, "same", "Sunrise Club", EPSILON, "Africa", "retired (jotform=no)", "active", 2),
                    (2, "same", "Golden Wings", ALPHA, "Africa", "Africa Attendance Form", "active", 1),
                    (3, "close", "Silver-Lights", BETA, "Asia", "none (no active girl)", "inactive", 0)]:
                w.writerow({"group": group, "match": match, "club": club, "partner": partner,
                            "region": region, "form": form, "country": "", "sf_name": "",
                            "status": status, "active_girls": n, "same_partner": "no"})
        code, out, header, rows, _ = self.plan(clubs, "similar_hand",
                                               scope=("--scope", "similar", "--similar-csv", similar_csv))
        self.assertEqual(header, PLAN_COLUMNS)
        self.assertEqual(self.by_club(rows), {
            (ALPHA, "Sunrise Club"): ("Africa", "Sunrise Club", "Kenya - Sunrise Club", "Kenya - Sunrise Club",
                                      "rename"),
            (BETA, "Sunrize Club"): ("Asia", "Sunrize Club", "Kenya - Sunrize Club", "Kenya - Sunrize Club",
                                     "rename"),
            (ALPHA, "Golden Wings"): ("Africa", f"Golden Wings - {ALPHA}", "Kenya - Golden Wings",
                                      f"Kenya - Golden Wings - {ALPHA}", "rename"),
        })
        self.assertEqual(plan_counts(self, out), (3, 0, 0))

        # the CSV `similar` itself writes: its groups, active clubs only
        made = self.ws.path("made_similar.csv")
        code, out = run_main(["similar", "--roster", self.ws.path("similar_hand_roster.csv"),
                              "--partners", self.ws.path("similar_hand_partners.csv"), "--csv", made])
        self.assertIn(code, (0, None), out)
        code, out, header, rows, _ = self.plan(clubs, "similar_made",
                                               scope=("--scope", "similar", "--similar-csv", made))
        self.assertEqual(sorted((r["partner"], r["club"], r["new_club"]) for r in rows), sorted([
            (ALPHA, "Sunrise Club", "Kenya - Sunrise Club"),
            (BETA, "Sunrize Club", "Kenya - Sunrize Club"),
            (ALPHA, "Golden Wings", "Kenya - Golden Wings"),
            (GAMMA, "GOLDEN WINGS", "Peru - GOLDEN WINGS"),
        ]))
        self.assertEqual(plan_counts(self, out), (4, 0, 0))

        # and --scope all takes every active club
        code, out, header, rows, _ = self.plan(clubs, "similar_all")
        self.assertEqual(sorted((r["partner"], r["club"]) for r in rows), sorted([
            (ALPHA, "Sunrise Club"), (BETA, "Sunrize Club"), (ALPHA, "Golden Wings"),
            (GAMMA, "GOLDEN WINGS"), (GAMMA, "River Roots"), (DELTA, "Morning Star")]))

    def test_scope_similar_without_the_similar_csv_is_refused(self):
        self.plan(PLAN_ROSTER, "nosim_control")                          # the same files, --scope all: fine
        code, out, header, rows, out_csv = self.plan(PLAN_ROSTER, "nosim", scope=("--scope", "similar"),
                                                     expect_ok=False)
        self.assertNotIn(code, (0, None), out)
        self.assertIn("--similar-csv", out)                              # the refusal says what is missing
        self.assertFalse(os.path.exists(out_csv))

    # ------------------------------------------------------------- long names
    def test_a_long_named_club_keeps_or_drops_the_partner_suffix(self):
        juniors, hope = "Alpha Club - Juniors", f"Hope - {DELTA}"       # plain names holding " - "
        clubs = [
            (ALPHA, "Sunrise Club", "Africa", 2, 0, "Sunrise Club"),                     # plain
            (BETA, "Ruby", "Africa", 2, 0, f"Ruby - {BETA}"),                             # long
            (GAMMA, "Ruby", "Latin America", 2, 0, f"Ruby - {GAMMA}"),                    # long
            (ALPHA, "Golden Wings", "Africa", 2, 0, f"golden  wings - {ALPHA.upper()}"),  # long, by key
            (ALPHA, juniors, "Africa", 2, 0, juniors),                                    # plain
            (DELTA, hope, "Asia", 2, 0, hope),        # plain, though its name ends " - <its partner>"
        ]
        new = {(ALPHA, "Sunrise Club"): "Kenya - Sunrise Club", (BETA, "Ruby"): "Kenya - Ruby",
               (GAMMA, "Ruby"): "Peru - Ruby", (ALPHA, "Golden Wings"): "Kenya - Golden Wings",
               (ALPHA, juniors): f"Kenya - {juniors}", (DELTA, hope): f"Nepal - {hope}"}
        long = {(BETA, "Ruby"), (GAMMA, "Ruby"), (ALPHA, "Golden Wings")}
        old = {(c[0], c[1]): " ".join(c[5].split()) for c in clubs}     # as read: spacing collapsed
        region = {(c[0], c[1]): c[2] for c in clubs}
        for keep in ("yes", "no"):
            with self.subTest(keep_long=keep):
                code, out, header, rows, _ = self.plan(clubs, f"long_{keep}", keep_long=keep)
                self.assertEqual(header, PLAN_COLUMNS)
                want = {}
                for k, new_club in new.items():
                    sf = f"{new_club} - {k[0]}" if keep == "yes" and k in long else new_club
                    want[k] = (region[k], old[k], new_club, sf, "rename")
                self.assertEqual(self.by_club(rows), want)
                self.assertEqual(plan_counts(self, out), (6, 0, 0))
        # the ticket's examples, spelled out
        _, _, _, rows_yes, _ = self.plan(clubs, "long_yes2", keep_long="yes")
        _, _, _, rows_no, _ = self.plan(clubs, "long_no2", keep_long="no")
        yes, no = self.by_club(rows_yes), self.by_club(rows_no)
        self.assertEqual(yes[(BETA, "Ruby")][3], "Kenya - Ruby - Fixture Partner Beta")
        self.assertEqual(no[(BETA, "Ruby")][3], "Kenya - Ruby")
        self.assertEqual(yes[(ALPHA, "Sunrise Club")][3], "Kenya - Sunrise Club")    # never gains it
        self.assertEqual(no[(DELTA, hope)][3], f"Nepal - Hope - {DELTA}")           # never split off

    # ------------------------------------------------------------- refusals
    def test_plan_renames_refuses_clashes_missing_countries_and_bad_characters(self):
        over = "Overlong Alpha Club " + "a" * 228          # 248 characters: "Kenya - " + it is 256
        wide = "Overlong Beta Club " + "b" * 211           # 230: new_club 238, long new_sf_name 261
        self.assertEqual((len(over), len(wide)), (248, 230))
        self.assertEqual(len(f"Kenya - {wide} - {BETA}"), 261)
        fine = (ALPHA, "Sunrise Club", "Africa", 2, 0, "Sunrise Club")
        cases = {
            # reason: (clubs, the refused clubs that must be named, more text that must appear)
            "no country": ([(DELTA, "River Roots", "Asia", 2, 0, "River Roots"),
                            (DELTA, "Valley Stars", "Africa", 3, 0, "Valley Stars"),
                            (DELTA, "Harbor Club 1", "Asia", 0, 2, None)],          # inactive: not refused
                           ["River Roots", "Valley Stars"], [DELTA]),
            "bad characters": ([(ALPHA, "Stars | Moons", "Africa", 2, 0, "Stars | Moons"),
                                (BETA, "Bright {Futures}", "Asia", 2, 0, "Bright {Futures}"),
                                (GAMMA, "Hope} Club", "Latin America", 2, 0, "Hope} Club")],
                               ["Stars | Moons", "Bright {Futures}", "Hope} Club"], []),
            # "Kenya - Lotus - Fixture Partner Alpha" (Alpha's, long) and "Kenya - lotus - fixture
            # partner alpha" (Beta's, plain): equal by key, different new_club
            "sf_name clash": ([(ALPHA, "Lotus", "Africa", 2, 0, f"Lotus - {ALPHA}"),
                               (BETA, f"lotus - {ALPHA.lower()}", "Asia", 2, 0, f"lotus - {ALPHA.lower()}")],
                              ["Lotus", f"lotus - {ALPHA.lower()}"], []),
            # Gamma's inactive club already has the name Alpha's Moon Girls would take
            "name in use": ([(GAMMA, "Kenya - Moon Girls", "Latin America", 0, 2, None),
                             (ALPHA, "Moon Girls", "Africa", 2, 0, "Moon Girls")],
                            ["Moon Girls"], []),
            "over 255": ([(ALPHA, over, "Africa", 2, 0, over),
                          (BETA, wide, "Asia", 2, 0, f"{wide} - {BETA}")],
                         [over[:22], wide[:21]], []),
        }
        countries = [[p, c] for p, c in COUNTRY.items() if p != DELTA]
        # each reason alone (beside a club that is fine) stops the plan
        for reason, (clubs, named, more) in cases.items():
            with self.subTest(reason=reason):
                tag = "ref_" + re.sub(r"\W+", "_", reason)
                code, out, _, _, out_csv = self.plan([fine, *clubs], tag, countries=countries, expect_ok=False)
                self.assert_refused(code, out, out_csv, named + more)
                self.assertEqual(plan_counts(self, out)[2], len(named), out)
        # the control: the fine club alone is planned
        self.plan([fine], "ref_control", countries=countries)
        # all at once: every refused club listed in the one run
        everything = [fine] + [c for clubs, _, _ in cases.values() for c in clubs]
        code, out, _, _, out_csv = self.plan(everything, "ref_all", countries=countries, expect_ok=False)
        named = [n for _, names, more in cases.values() for n in names + more]
        self.assert_refused(code, out, out_csv, named)
        self.assertEqual(plan_counts(self, out)[2], 10, out)
        # a placeholder the format does not know: refused, named, nothing written
        for fmt, unknown in (("{country} - {club} ({continent})", "continent"), ("{name} {club}", "name")):
            with self.subTest(format=fmt):
                code, out, _, _, out_csv = self.plan([fine], f"ref_{unknown}", fmt=fmt, countries=countries,
                                                     expect_ok=False)
                self.assert_refused(code, out, out_csv, [unknown])

    def test_a_new_sf_name_of_exactly_255_characters_is_planned(self):
        edge = "Edge Club " + "e" * 237                     # 247: "Kenya - " + it is 255
        wide = "Wide Club " + "w" * 220                     # 230: long 261, plain 238
        self.assertEqual((len(edge), len(wide)), (247, 230))
        clubs = [(ALPHA, edge, "Africa", 2, 0, edge), (BETA, wide, "Asia", 2, 0, f"{wide} - {BETA}")]
        code, out, _, rows, _ = self.plan(clubs, "edge", keep_long="no")
        got = self.by_club(rows)
        self.assertEqual(got[(ALPHA, edge)][3], f"Kenya - {edge}")
        self.assertEqual(len(got[(ALPHA, edge)][3]), 255)
        self.assertEqual(got[(BETA, wide)][3], f"Kenya - {wide}")
        # the same clubs keeping the long name: Beta's goes over 255 (new_club itself is 238)
        code, out, _, _, out_csv = self.plan(clubs, "edge_long", keep_long="yes", expect_ok=False)
        self.assert_refused(code, out, out_csv, [wide[:20]])
        self.assertEqual(plan_counts(self, out)[2], 1, out)

    def test_bad_characters_from_the_format_or_the_countries_file_are_refused(self):
        # the format brings the "|": every club in scope is refused and named
        code, out, _, _, out_csv = self.plan(PLAN_ROSTER, "badfmt", fmt="{country} | {club}", expect_ok=False)
        self.assert_refused(code, out, out_csv, sorted({c for _, c, _, _ in PLANNED}))
        self.assertEqual(plan_counts(self, out)[2], len(PLANNED), out)
        for club in ("Harbor Club 1", "Ocean Voices"):                    # inactive, retired: not refused
            self.assertNotIn(club, out)
        for n, fmt in enumerate(("{country} {{ {club}", "{club} }} {country}")):  # a brace, escaped or not
            with self.subTest(format=fmt):
                code, out, _, _, out_csv = self.plan(PLAN_ROSTER, f"badbrace{n}", fmt=fmt, expect_ok=False)
                self.assertNotIn(code, (0, None), out)
                self.assertFalse(os.path.exists(out_csv))
        # the countries file brings them: only those partners' clubs are refused
        clubs = [
            (ALPHA, "Sunrise Club", "Africa", 2, 0, "Sunrise Club"),        # Kenya|East
            (ALPHA, "Shining Stars", "Africa", 2, 0, "Shining Stars"),      # Kenya|East
            (BETA, "Morning Star", "Asia", 2, 0, "Morning Star"),           # Kenya: fine
            (GAMMA, "Niñas Unidas", "Latin America", 2, 0, "Niñas Unidas"),  # Peru {Sur}
            (DELTA, "River Roots", "Asia", 2, 0, "River Roots"),            # Nepal: fine
            (DELTA, "Harbor Club 1", "Asia", 0, 2, None),                   # inactive: not planned
        ]
        countries = [[ALPHA, "Kenya|East"], [BETA, "Kenya"], [GAMMA, "Peru {Sur}"], [DELTA, "Nepal"]]
        code, out, _, _, out_csv = self.plan(clubs, "badcountry", countries=countries, expect_ok=False)
        self.assert_refused(code, out, out_csv, ["Sunrise Club", "Shining Stars", "Niñas Unidas"])
        self.assertEqual(plan_counts(self, out)[2], 3, out)
        # the control: the same clubs with clean countries are planned
        clean = [[ALPHA, "Kenya"], [BETA, "Kenya"], [GAMMA, "Peru"], [DELTA, "Nepal"]]
        code, out, _, rows, _ = self.plan(clubs, "badcountry_control", countries=clean)
        self.assertEqual(plan_counts(self, out), (5, 0, 0))

    def write_similar_csv(self, name, clubs):
        """A task #94 CSV listing `clubs` ((partner, club, region)) as one group."""
        path = self.ws.path(name)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            w.writeheader()
            for partner, club, region in clubs:
                w.writerow({"group": 1, "match": "close", "club": club, "partner": partner, "region": region,
                            "form": f"{region} Attendance Form", "country": "", "sf_name": "",
                            "status": "active", "active_girls": 2, "same_partner": "no"})
        return path

    def test_a_new_club_another_partners_club_has_is_refused_in_any_spelling_or_status(self):
        # Alpha's plain "Moon Girls" becomes "Kenya - Moon Girls" (Alpha is in Kenya)
        moon = (ALPHA, "Moon Girls", "Africa", 2, 0, "Moon Girls")
        fine = (DELTA, "River Roots", "Asia", 2, 0, "River Roots")
        cases = {
            # the other club's name equals the new one by key only (case, spacing), inactive
            "key-equal inactive": [moon, (GAMMA, "kenya -  moon GIRLS", "Latin America", 0, 2, None)],
            # the new name itself spelled differently from the other club's
            "key-equal new name": [(ALPHA, "moon  GIRLS", "Africa", 2, 0, "moon GIRLS"),
                                   (GAMMA, "Kenya - Moon Girls", "Latin America", 0, 2, None)],
            # a retired partner's club (active girls, but never planned: it keeps its name)
            "retired partner's": [moon, (EPSILON, "Kenya - Moon Girls", "Africa", 3, 0, "Kenya - Moon Girls")],
        }
        for reason, clubs in cases.items():
            with self.subTest(reason=reason):
                tag = "inuse_" + re.sub(r"\W+", "_", reason)
                code, out, _, _, out_csv = self.plan([fine, *clubs], tag, expect_ok=False)
                self.assert_refused(code, out, out_csv, ["Moon Girls" if reason != "key-equal new name"
                                                         else "moon GIRLS"])
                self.assertEqual(plan_counts(self, out)[2], 1, out)
        # an ACTIVE club of another partner that keeps its name: out of scope ...
        clubs = [fine, moon, (BETA, "Kenya - Moon Girls", "Asia", 2, 0, "Kenya - Moon Girls")]
        listed = self.write_similar_csv("inuse_similar.csv", [(ALPHA, "Moon Girls", "Africa"),
                                                              (DELTA, "River Roots", "Asia")])
        code, out, _, _, out_csv = self.plan(clubs, "inuse_active_scope", expect_ok=False,
                                             scope=("--scope", "similar", "--similar-csv", listed))
        self.assert_refused(code, out, out_csv, ["Moon Girls"])
        self.assertEqual(plan_counts(self, out)[2], 1, out)
        # ... or in scope and already in the format (unchanged): still refused
        code, out, _, _, out_csv = self.plan(clubs, "inuse_active_all", expect_ok=False)
        self.assert_refused(code, out, out_csv, ["Moon Girls"])
        self.assertIn(plan_counts(self, out)[2], (1, 2), out)
        # the control: without Alpha's Moon Girls the same files are planned
        self.plan([c for c in clubs if c is not moon], "inuse_active_control")

    def test_the_shared_name_check_runs_on_the_names_after_the_renames(self):
        # Gamma's active "Kenya - Moon Girls" is itself renamed (to "Peru - Kenya - Moon Girls"),
        # so Alpha's Moon Girls may take "Kenya - Moon Girls"
        clubs = [(ALPHA, "Moon Girls", "Africa", 2, 0, "Moon Girls"),
                 (GAMMA, "Kenya - Moon Girls", "Latin America", 2, 0, "Kenya - Moon Girls")]
        code, out, _, rows, _ = self.plan(clubs, "after", keep_long="no")
        self.assertEqual(self.by_club(rows), {
            (ALPHA, "Moon Girls"): ("Africa", "Moon Girls", "Kenya - Moon Girls", "Kenya - Moon Girls", "rename"),
            (GAMMA, "Kenya - Moon Girls"): ("Latin America", "Kenya - Moon Girls", "Peru - Kenya - Moon Girls",
                                            "Peru - Kenya - Moon Girls", "rename"),
        })
        self.assertEqual(plan_counts(self, out), (2, 0, 0))
        # a name another partner's club keeps is allowed only in the long form "<club> - <partner>"
        clubs = [(ALPHA, "Moon Girls", "Africa", 2, 0, f"Moon Girls - {ALPHA}"),
                 (GAMMA, "Kenya - Moon Girls", "Latin America", 0, 2, None)]           # inactive: keeps it
        code, out, _, rows, _ = self.plan(clubs, "after_long", keep_long="yes")
        self.assertEqual(self.by_club(rows), {
            (ALPHA, "Moon Girls"): ("Africa", f"Moon Girls - {ALPHA}", "Kenya - Moon Girls",
                                    f"Kenya - Moon Girls - {ALPHA}", "rename")})
        code, out, _, _, out_csv = self.plan(clubs, "after_plain", keep_long="no", expect_ok=False)
        self.assert_refused(code, out, out_csv, ["Moon Girls"])
        self.assertEqual(plan_counts(self, out)[2], 1, out)

    def test_two_partners_clubs_given_one_new_name_need_the_long_form(self):
        # Alpha and Beta are both in Kenya: their "Ruby" clubs both become "Kenya - Ruby"
        fine = (GAMMA, "River Roots", "Latin America", 2, 0, "River Roots")
        plain = {ALPHA: "Ruby", BETA: "Ruby"}
        long = {ALPHA: f"Ruby - {ALPHA}", BETA: f"Ruby - {BETA}"}
        cases = [
            # (Alpha's question 5, Beta's, --keep-long, the refused partners or None when planned)
            (plain, "no", [ALPHA, BETA]),
            (plain, "yes", [ALPHA, BETA]),           # a plain club never gains the suffix
            (long, "no", [ALPHA, BETA]),
            (long, "yes", None),
            ({ALPHA: long[ALPHA], BETA: plain[BETA]}, "yes", [BETA]),
            ({ALPHA: long[ALPHA], BETA: plain[BETA]}, "no", [ALPHA, BETA]),
        ]
        for n, (sf, keep, refused) in enumerate(cases):
            with self.subTest(alpha=sf[ALPHA], beta=sf[BETA], keep_long=keep):
                clubs = [fine, (ALPHA, "Ruby", "Africa", 2, 0, sf[ALPHA]), (BETA, "Ruby", "Asia", 3, 0, sf[BETA])]
                code, out, _, rows, out_csv = self.plan(clubs, f"ruby{n}", keep_long=keep,
                                                        expect_ok=refused is None)
                if refused is None:
                    got = self.by_club(rows)
                    self.assertEqual(got[(ALPHA, "Ruby")][2:], ("Kenya - Ruby", f"Kenya - Ruby - {ALPHA}", "rename"))
                    self.assertEqual(got[(BETA, "Ruby")][2:], ("Kenya - Ruby", f"Kenya - Ruby - {BETA}", "rename"))
                    self.assertEqual(plan_counts(self, out), (3, 0, 0))
                else:
                    self.assert_refused(code, out, out_csv, ["Ruby", *refused])
                    self.assertEqual(plan_counts(self, out)[2], len(refused), out)
        # the control: in two countries the plain pair is planned
        clubs = [fine, (ALPHA, "Ruby", "Africa", 2, 0, "Ruby"), (BETA, "Ruby", "Asia", 3, 0, "Ruby")]
        countries = [[p, c] for p, c in COUNTRY.items() if p != BETA] + [[BETA, "Uganda"]]
        code, out, _, rows, _ = self.plan(clubs, "ruby_two_countries", keep_long="no", countries=countries)
        got = self.by_club(rows)
        self.assertEqual((got[(ALPHA, "Ruby")][3], got[(BETA, "Ruby")][3]), ("Kenya - Ruby", "Uganda - Ruby"))

    # ------------------------------------------------------------- a second run
    def test_plan_renames_is_idempotent(self):
        formats = ["{country} - {club}", "{club} ({country})", "{region}: {country} / {club}",
                   "{partner} - {club}"]
        for n, fmt in enumerate(formats):
            for keep in ("yes", "no"):
                with self.subTest(format=fmt, keep_long=keep):
                    tag = f"idem{n}{keep}"
                    code, out, header, rows, _ = self.plan(PLAN_ROSTER, tag, fmt=fmt, keep_long=keep)
                    first = self.by_club(rows)
                    self.assertGreater(plan_counts(self, out)[0], 0, out)
                    self.assertEqual(len(first), len(PLANNED))
                    # the Roster renamed per the plan; question 5 now sends each new_sf_name
                    renamed = []
                    for partner, club, region, active, inactive, sf in PLAN_ROSTER:
                        row = first.get((partner, " ".join(club.split())))
                        if row is None:                           # not planned: keeps its name
                            renamed.append((partner, club, region, active, inactive, sf))
                        else:
                            renamed.append((partner, row[2], region, active, inactive, row[3]))
                    code, out, header, rows, _ = self.plan(renamed, tag + "_again", fmt=fmt, keep_long=keep)
                    second = self.by_club(rows)
                    self.assertEqual(set(second), {(p, v[2]) for (p, _), v in first.items()})
                    for (partner, club), (_region, old_sf, new_club, new_sf, action) in second.items():
                        self.assertEqual((new_club, new_sf, action), (club, old_sf, "unchanged"),
                                         (partner, club))
                    self.assertEqual(plan_counts(self, out), (0, len(PLANNED), 0))

    # ------------------------------------------------------------- the command line
    def test_plan_renames_requires_its_inputs_and_answers_help(self):
        env = {k: v for k, v in os.environ.items() if k != "JOTFORM_API_KEY"}
        tool = os.path.join(REPO, "tools", "club_names.py")
        r = subprocess.run([sys.executable, tool, "plan-renames", "--help"], capture_output=True, text=True,
                           env=env, cwd=REPO)
        self.assertEqual(r.returncode, 0, r.stderr)
        for option in ("--roster", "--partners", "--countries", "--sf-names", "--format", "--scope",
                       "--similar-csv", "--keep-long", "--out"):
            self.assertIn(option, r.stdout)
        base = self.files(PLAN_ROSTER, "req")
        full = ["plan-renames", *base, "--format", "{country} - {club}", "--scope", "all",
                "--keep-long", "yes", "--out", self.ws.path("req_plan.csv")]
        for drop in ("--countries", "--sf-names", "--format"):
            argv = [a for i, a in enumerate(full) if a != drop and (i == 0 or full[i - 1] != drop)]
            with self.subTest(missing=drop):
                code, out = run_main(argv)
                self.assertNotIn(code, (0, None), out)
                self.assertIn(drop, out)                                 # names the missing option
                self.assertFalse(os.path.exists(self.ws.path("req_plan.csv")))
        r = subprocess.run([sys.executable, tool, *full], capture_output=True, text=True, env=env, cwd=REPO)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(plan_counts(self, r.stdout), (7, 1, 0))


if __name__ == "__main__":
    unittest.main()
