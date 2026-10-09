#!/usr/bin/env python3
"""
The constants that exist in BOTH Python and appsscript/ - SF_NAME_SEP, the regions, the Roster,
Partners and SyncLog columns and tabs, the response-tab header fragments - so a change on one
side fails here until the other side follows (CLAUDE.md rule 7); and logic both sides run: the
same-name rule over one fictional Roster, similarity_ against difflib, foldKey_ against
glow.text.name_key. The Apps Script side runs in Node, through test/load_gs.js (gs_eval).
"""
import csv
import difflib
import json
import os
import re
import shutil
import subprocess
import unittest

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import REPO, apps_script_same_name, read
import auto_sync
import form_status
import sync_attendance_form as sync
from glow import sync as glow_sync
from glow.text import name_key


GS_DIR = os.path.join(REPO, "appsscript")
ROSTER_GS = os.path.join(GS_DIR, "Roster.gs")
FIXTURE_CSV = os.path.join(REPO, "test", "fixtures", "enrollment_sample.csv")

_GS_EVAL = """
const inp = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const gs = require(process.argv[1])(inp.names, inp.files, { strict: true });
const out = inp.expr === null ? gs : new Function('gs', 'data', 'return (' + inp.expr + ');')(gs, inp.data);
process.stdout.write(JSON.stringify(out));
"""


def gs_eval(names=None, expr=None, data=None):
    """Every .gs file loaded in Node as the JS tests load them (test/load_gs.js, strict: no
    Google API, no implicit global), as JSON: the top-level `names` (all of them when None)
    as {name: value} - functions drop out - or, with `expr`, the value of that JavaScript
    expression, in which `gs` holds the names and `data` is `data` (JSON). Skips the test
    when node is missing (make check runs the JS tests first, so there it never is)."""
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed: the Apps Script side cannot run")
    files = sorted(f for f in os.listdir(GS_DIR) if f.endswith(".gs"))
    done = subprocess.run(["node", "-e", _GS_EVAL, os.path.join(REPO, "test", "load_gs.js")],
                          input=json.dumps({"names": names, "files": files, "expr": expr, "data": data}),
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


class PythonAppsScriptParity(unittest.TestCase):
    def test_picker_name_is_shared(self):
        # the sync and form_status find the Club picker with one function, by one name
        self.assertIs(form_status.club_picker, glow_sync.club_picker)
        self.assertIs(sync.club_picker, glow_sync.club_picker)
        self.assertEqual(sync.PICKER_NAME, glow_sync.PICKER_NAME)

    def test_the_same_name_separator(self):
        # "<club> - <partner>" is one string on both sides: the forms' Club picker entry and
        # question 5 (Python), the Monday e-mail's Salesforce account name and the intake
        # check (Apps Script). CLAUDE.md rule 7: change both
        self.assertEqual(gs_eval(["SF_NAME_SEP"]), {"SF_NAME_SEP": glow_sync.SF_NAME_SEP})
        self.assertEqual([ord(c) for c in glow_sync.SF_NAME_SEP], [0x20, 0x2D, 0x20])   # no long dash
        # one definition per side, used by name everywhere else
        self.assertIs(sync.SF_NAME_SEP, glow_sync.SF_NAME_SEP)
        self.assertIs(form_status.SF_NAME_SEP, glow_sync.SF_NAME_SEP)
        for name in sorted(os.listdir(os.path.join(REPO, "appsscript"))):
            if name.endswith(".gs") and name != "Config.gs":
                self.assertNotRegex(read(os.path.join(REPO, "appsscript", name)),
                                    r"(?:const|let|var)\s+SF_NAME_SEP\b", name)

    # One fictional Roster for both sides: (partner, club, full_name, status, region)
    SAME_NAME_ROSTER = [
        ("Partner One", "Stars", "Ann Poe", "active", "Africa"),
        ("Partner One", "Stars", "Kay Loe", "inactive", "Africa"),
        ("Partner Two", "Stars", "Sue Moe", "active", "Asia"),            # another region: one Salesforce org
        ("Partner Four", "STARS", "Liz Noe", " Active ", "U.S"),          # capitals; the status as typed
        ("Partner One", "Alpha Club", "Jane Doe", "active", "Africa"),
        ("partner  one", "Alpha  Club", "Mary Roe", "active", "Africa"),  # one partner written twice
        ("Partner Two", "Beta Club", "Eve Hoe", "active", "Asia"),
        ("Partner Three", "Beta Club", "Ida Toe", "inactive", "U.S"),     # a retired namesake
        ("Partner One", "Comet Club", "Uma Roe", "active", "Africa"),
        ("Partner Two", "Comet Club", "", "active", "Asia"),              # a row with no girl
        ("Partner Two", "Alpha Club - Juniors", "Amy Foe", "active", "Asia"),   # its own " - "
        ("Partner Two", "Étoiles", "Bea Goe", "active", "Asia"),
        ("Fundación Demo", "étoiles", "Cy Joe", "active", "Latin America"),     # accents kept, case not
        ("Partner Three", "Moon", "Dee Koe", "inactive", "U.S"),          # nobody's active club
        ("", "Stars", "Fay Low", "active", "Africa"),                     # no partner: reaches no form
        ("Partner Three", "", "Gia Mow", "active", "U.S"),                # no club
    ]

    def same_name_sides(self, probes=()):
        """(Python's roster_pairs of SAME_NAME_ROSTER, its active clubs, what Apps
        Script makes of the same rows)."""
        import csv
        import tempfile
        cols = ["partner", "club", "full_name", "status", "region"]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "roster.csv")
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["girl_id"] + cols)
                for n, row in enumerate(self.SAME_NAME_ROSTER):
                    w.writerow([f"DEMOCLUB-SAMPLE-{n:03d}", *row])
            pairs = glow_sync.roster_pairs(path)
        active = sorted(pc for pc, is_active in pairs.items() if is_active)
        gs = apps_script_same_name([dict(zip(cols, row)) for row in self.SAME_NAME_ROSTER],
                                   pairs=active, probes=probes)
        if gs is None:
            self.skipTest("node is not installed: the Apps Script side cannot run")
        return pairs, active, gs

    def test_the_switch_rule_agrees_with_apps_script(self):
        # which clubs are "<club> - <partner>": Python decides it for the forms
        # (sync_attendance_form.py --same-name-switch goes by shared_club_names(active_only=True)),
        # Apps Script for the Monday e-mail's Salesforce account names (sharedClubNames_ /
        # sfClubName_). Both run here, on the same rows
        from glow.text import key
        pairs, active, gs = self.same_name_sides()
        shared = glow_sync.shared_club_names(pairs, active_only=True)
        self.assertEqual(gs["sep"], glow_sync.SF_NAME_SEP)
        self.assertEqual(gs["shared"], sorted(shared))
        self.assertEqual(sorted(shared), ["stars", "étoiles"])     # pinned: neither side is empty
        names = [glow_sync.sf_club_name(club, partner, key(club) in shared) for partner, club in active]
        self.assertEqual(gs["names"], names)
        self.assertEqual(dict(zip(active, names)), {
            ("Fundación Demo", "étoiles"): "étoiles - Fundación Demo",
            ("Partner Four", "STARS"): "STARS - Partner Four",             # its own spelling kept
            ("Partner One", "Alpha Club"): "Alpha Club",                   # one partner, written twice
            ("Partner One", "Comet Club"): "Comet Club",                   # its namesake has no girl
            ("Partner One", "Stars"): "Stars - Partner One",
            ("Partner Two", "Alpha Club - Juniors"): "Alpha Club - Juniors",
            ("Partner Two", "Beta Club"): "Beta Club",                     # its namesake is retired
            ("Partner Two", "Stars"): "Stars - Partner Two",
            ("Partner Two", "Étoiles"): "Étoiles - Partner Two"})
        # no two clubs end up with one Salesforce name, on either side
        self.assertEqual(glow_sync.sf_name_clashes(zip(gs["names"], active)), [])

    def test_a_name_in_use_is_the_same_on_both_sides(self):
        # Ryan's decision 2: a NEW club may not take a name another partner's club has - any
        # status, any region, a girl on the row or not. The sync refuses to create it
        # (sync_attendance_form.py: glow.sync.club_partners over roster_pairs); the Club Roster
        # Form handler holds it before it reaches the Roster (newClubHoldReasons_, kind samename)
        from glow.text import key
        clubs = ["Stars", "stars", "Beta Club", "Comet Club", "Moon", "Alpha Club", "Étoiles",
                 "Alpha Club - Juniors", "Brand New Club", "Star"]
        probes = [(partner, club) for club in clubs
                  for partner in ("Partner Nine", "Partner One", "Partner Three")]
        pairs, _, gs = self.same_name_sides(probes)
        holders = glow_sync.club_partners(pairs)
        active = {(key(p), key(c)) for (p, c), is_active in pairs.items() if is_active}
        held = dict(zip(probes, gs["held"]))

        def on_file(partner, club):
            return key(partner) in holders.get(key(club), {})

        def taken(partner, club):
            return any(k != key(partner) for k in holders.get(key(club), {}))

        new = [p for p in probes if not on_file(*p)]
        self.assertEqual(len(new), 24)
        self.assertEqual({p: held[p] for p in new}, {p: taken(*p) for p in new})
        self.assertTrue(held[("Partner Nine", "Stars")])
        self.assertTrue(held[("Partner Nine", "stars")])                # capitals do not make a new name
        self.assertTrue(held[("Partner Nine", "Moon")])                 # a retired club's name is in use
        self.assertTrue(held[("Partner Three", "Comet Club")])          # ...and one a row with no girl holds
        self.assertTrue(held[("Partner One", "Alpha Club - Juniors")])  # a club's own " - " is its name
        self.assertFalse(held[("Partner Nine", "Brand New Club")])
        self.assertFalse(held[("Partner Nine", "Star")])                # a different name
        # a club the partner has on file with an active girl is no new club on either side:
        # the sync matches it to its roster, the handler runs it as that club
        own = [p for p in probes if (key(p[0]), key(p[1])) in active]
        self.assertEqual(sorted(own), [("Partner One", "Alpha Club"), ("Partner One", "Comet Club"),
                                       ("Partner One", "Stars"), ("Partner One", "stars")])
        self.assertEqual([held[p] for p in own], [False] * 4)
        # the documented divergence (docs/ARCHITECTURE.md, Known divergences): a club on file
        # with NO active girl whose name another partner's club has is held at intake; the
        # sync refuses it only when its roster question is gone and it would be created
        self.assertTrue(held[("Partner Three", "Beta Club")])
        self.assertFalse(held[("Partner Three", "Moon")])               # retired, and nobody else's name

    def test_synclog_columns_and_the_runner_tabs(self):
        gs = gs_eval(["SYNC_LOG_COLS", "TAB"])
        self.assertEqual(gs["SYNC_LOG_COLS"], auto_sync.SYNC_LOG_COLS)
        # the tabs tools/auto_sync.py reads and writes are the ones the sheet's code names
        self.assertEqual((gs["TAB"]["ROSTER"], gs["TAB"]["PARTNERS"], gs["TAB"]["SYNC_LOG"]),
                         (auto_sync.ROSTER_TAB, auto_sync.PARTNERS_TAB, auto_sync.SYNC_LOG_TAB))
        self.assertEqual(auto_sync.SYNC_LOG_TAB, "SyncLog")

    def test_roster_columns_python_side_is_a_subset(self):
        cols = gs_eval(["ROSTER_COLS"])["ROSTER_COLS"]
        self.assertTrue({"partner", "club", "full_name", "status", "region"} <= set(cols))
        self.assertEqual(cols[0], "girl_id")

    def test_response_columns(self):
        # the header fragments both sides find the enrollment export's columns by:
        # readResponses_ (Normalize.gs) and read_sheet (glow.sync)
        self.assertEqual(gs_eval(["RESPONSE_COLS"])["RESPONSE_COLS"],
                         {"partner": glow_sync.COL_PARTNER, "club": glow_sync.COL_CLUB,
                          "roster": glow_sync.COL_ROSTER})

    def test_partner_columns(self):
        # the Partners tab's columns: Roster.gs writes them (setUpTabs, seedPartners_) and reads the
        # jotform cell for the mentor e-mails (loadPartnerJotform_), the offline builder keeps its own
        # copy, Python reads the cell for the forms (glow.sync). CLAUDE.md rule 7: change all three
        self.assertEqual(tuple(gs_eval(["PARTNER_COLS"])["PARTNER_COLS"]), glow_sync.PARTNER_COLS)
        offline = os.path.join(REPO, "tools", "build_roster_offline.js")   # a script: read, not run
        m = re.search(r"const PARTNER_COLS = \[(.*?)\];", read(offline), re.S)
        self.assertIsNotNone(m, offline)
        self.assertEqual(tuple(re.findall(r"'([a-z_]+)'", m.group(1))), glow_sync.PARTNER_COLS)
        self.assertEqual(m.group(1).count("'") // 2, len(glow_sync.PARTNER_COLS))
        self.assertIn(glow_sync.JOTFORM_COL, glow_sync.PARTNER_COLS)
        self.assertEqual(glow_sync.PARTNER_COLS[:3], ("partner", "region", "notes"))   # the live tab's header
        # the Apps Script finds the column by the tab's own header row (key_), as Python's
        # read_partners_csv reads the export by header - never by the constant's position
        reader = re.search(r"function loadPartnerJotform_\(\) \{(.*?)\n\}", read(ROSTER_GS), re.S).group(1)
        self.assertIn("getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0].map(key_)", reader)
        self.assertIn(f"header.indexOf('{glow_sync.JOTFORM_COL}')", reader)
        self.assertNotIn("PARTNER_COLS", reader)

    def test_regions_match_glow_forms(self):
        # the Club Roster Form's region picker (Config.gs REGIONS) must offer
        # exactly the regions the Python sync routes on — spelling included
        from glow import forms as glow_forms
        gs = gs_eval(["REGIONS", "Q"])
        self.assertEqual(tuple(gs["REGIONS"]), glow_forms.REGIONS)
        self.assertIn("U.S", gs["REGIONS"])               # one dot, no trailing dot
        self.assertEqual(gs["Q"]["REGION"], "Region where this club meets")

    # Fictional pairs, club- and partner-name-like. Each side counts characters its own way
    # (JavaScript UTF-16 units, Python code points), so none here is outside the BMP; and
    # difflib's autojunk only starts at 200 characters, which no name reaches.
    SIMILARITY_PAIRS = [
        ("bravehaert", "braveheart"), ("shining stars", "shinning stars"), ("vision", "rise"),
        ("abcd", "bcde"), ("chacarita", "traslasierra"), ("empowerment kenya", "empowerment uganda"),
        ("aaab", "abaa"), ("xyz", ""), ("", ""), ("ab", "ba"), ("aaaa", "aa"),
        ("glow club", "glow clubs"), ("sunrise", "sunset"), ("lucia zorblewick", "lucía zörblewick"),
        ("kibera hope", "kibera hope 2"), ("harbor club 1", "harbor club (2)"), ("orbit a", "orbit b"),
        ("las lomitas primaria", "las lomitas secundaria"), ("test aid relief network", "tarn"),
        ("fundacion demo", "fundación demo"), ("abcabcabc", "cbacbacba"),
        ("the quick brown fox", "the quack brown box"), ("bright girls testville", "brite girls testvile"),
        ("evening stars", "morning stars"),
    ]

    def test_similarity_is_difflibs_ratio(self):
        # RosterOps.gs similarity_ (the duplicate-club guard's "close names") is meant to be
        # difflib.SequenceMatcher(None, a, b).ratio(): Ratcliff/Obershelp, ties broken
        # earliest in a, then in b
        got = gs_eval(["similarity_"], "data.map(p => gs.similarity_(p[0], p[1]))",
                      [list(p) for p in self.SIMILARITY_PAIRS])
        want = [difflib.SequenceMatcher(None, a, b).ratio() for a, b in self.SIMILARITY_PAIRS]
        self.assertEqual(len(got), len(want))
        for (a, b), g, w in zip(self.SIMILARITY_PAIRS, got, want):
            self.assertAlmostEqual(g, w, places=12, msg=f"{a!r} / {b!r}")
        self.assertTrue(all(len(a) < 200 and len(b) < 200 for a, b in self.SIMILARITY_PAIRS))
        self.assertTrue(all(ord(c) < 0x10000 for a, b in self.SIMILARITY_PAIRS for c in a + b))
        self.assertGreater(len({round(w, 6) for w in want}), 15)    # the pairs are not all alike

    def test_fold_key_and_name_key_differ_only_by_invisible_characters(self):
        # Normalize.gs foldKey_ (the near-duplicate checks: matchWords_, the problem-report
        # patterns) and glow.text.name_key fold case and accents alike. They differ where a
        # text holds an invisible character (Normalize.gs INVISIBLE): key_ drops it,
        # glow.text keeps it - the documented divergence (CLAUDE.md rule 10, BACKLOG 28,
        # docs/ARCHITECTURE.md "Known divergences"), so it is asserted here, not equality.
        # Not exercised by these Latin-script names: a combining mark outside U+0300-U+036F
        # (name_key drops every combining mark, foldKey_ only those).
        with open(FIXTURE_CSV, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))[1:]
        texts = set()
        for row in rows:
            for i in (2, 3):                                  # partner, club
                if len(row) > i:
                    texts.add(row[i])
            if len(row) > 5:
                lines = row[5].split("\n")                    # the roster cell, line by line, as typed
                texts.update(lines)
                texts.update(glow_sync.parse_roster(row[5])[0])
        texts = sorted(texts)
        gs = gs_eval(["foldKey_", "INVISIBLE"],
                     "{ invisible: gs.INVISIBLE.source, folded: data.map(gs.foldKey_) }", texts)
        invisible = re.compile(gs["invisible"])
        self.assertEqual(invisible.pattern.count("\\u"), 7)    # \u200B ... \uFEFF
        hidden = [t for t in texts if invisible.search(t)]
        self.assertGreaterEqual(len(hidden), 4)                 # the fixture's "Hidden Chars" club
        self.assertTrue(any(name_key(t) != t.lower() for t in texts))   # accents are exercised
        for text, folded in zip(texts, gs["folded"]):
            self.assertEqual(folded, name_key(invisible.sub("", text)), repr(text))
            if invisible.search(text):
                self.assertNotEqual(folded, name_key(text), repr(text))
            else:
                self.assertEqual(folded, name_key(text), repr(text))

    def test_the_architecture_table_lists_every_mirrored_constant(self):
        # docs/ARCHITECTURE.md's "change both" table is the human copy of CLAUDE.md
        # rule 7: one three-cell row per constant (a row with more cells than the
        # header renders without its extra cells, and that constant disappears)
        doc = read(os.path.join(REPO, "docs", "ARCHITECTURE.md"))
        section = doc.split("## Constants that exist on both sides", 1)[1].split("\n## ", 1)[0]
        rows = [ln for ln in section.splitlines() if ln.startswith("|")][2:]   # past header + rule
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row.count("|"), 4, row)
        firsts = [row.split("|")[1] for row in rows]
        for constant in ("`SF_NAME_SEP`", "Roster tab columns", "Partners tab columns",
                         "Response-tab header fragments", "SyncLog columns"):
            self.assertEqual(sum(constant in f for f in firsts), 1, constant)


if __name__ == "__main__":
    unittest.main(verbosity=1)
