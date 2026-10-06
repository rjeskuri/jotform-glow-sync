#!/usr/bin/env python3
"""
Offline Python tests (standard library unittest; run by `make py`):

  - the auto-sync runner's decisions (plan parsing, safety bands, the
    blank-region guard, verification, redaction), on fabricated output;
  - the enrollment parser on the synthetic fixture (numbers pinned in
    test/fixtures/expected.json) and its edge cases;
  - the constants that exist in BOTH Python and appsscript/Config.gs /
    Roster.gs - form ids, qids, SESSION_OVERRIDES, SF_NAME_SEP, SyncLog
    columns - so a change on one side fails here until the other side
    follows; and the same-name rule itself, run on both sides over one
    fictional Roster (the Apps Script side in Node, through test/load_gs.js).

    python3 test/python_test.py
"""
import copy
import json
import os
import re
import struct
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import add_feedback_link              # noqa: E402
import add_language                   # noqa: E402
import add_translations               # noqa: E402
import auto_sync                      # noqa: E402
import fix_name_translations          # noqa: E402
import fix_roster_order               # noqa: E402
import form_status                    # noqa: E402
import rename_club                    # noqa: E402
import restore_conditions             # noqa: E402
import switcher_flags                 # noqa: E402
import update_static_fields           # noqa: E402
import worklog                        # noqa: E402
import sync_attendance_form as sync   # noqa: E402
from glow import forms as glow_forms  # noqa: E402
from glow import layout               # noqa: E402
from glow import links                # noqa: E402
from glow import sync as glow_sync    # noqa: E402
from glow import translation_lookup as tl   # noqa: E402
from glow import usage                # noqa: E402
from glow.text import md5             # noqa: E402
from sf_club_accounts_test import SalesforceClubAccounts  # noqa: E402,F401  (its own file; run here)
from integration_status_test import IntegrationStatus     # noqa: E402,F401  (its own file; run here)
from sf_backfill_test import SalesforceBackfill, SalesforceBackfillEdges   # noqa: E402,F401  (its own file; run here)
from backfill_resolve_test import BackfillResolve, BackfillResolverAndLoaderAgree   # noqa: E402,F401  (its own file; run here)

FIXTURE = os.path.join(REPO, "test", "fixtures", "enrollment_sample.csv")
EXPECTED = os.path.join(REPO, "test", "fixtures", "expected.json")
CONFIG_GS = os.path.join(REPO, "appsscript", "Config.gs")
ROSTER_GS = os.path.join(REPO, "appsscript", "Roster.gs")

DRY_RUN = """Roster: 12 active clubs in Asia (176 girls); 332 clubs overall
  ! 'Old Name Club' (q120): proposed roster shares NO names with the current one - verify it is the same club before applying
  ? 'Left Behind' (q133) is on the form but not in the sheet export - keeping its current roster

DRY RUN (use --apply to write):
  - CREATE roster 'Brand New Club' (9 girls)
  - UPDATE roster 'Old Name Club' (q120, 14 girls)
  - UPDATE roster 'Sunrise Club, Eastside "B"' (q121, 3 girls)
  - DELETE roster 'Elsewhere' (q140, belongs to Africa)
  - UPDATE club picker (13 clubs: options, subLabel)
  - REPLACE conditions (57 rules + ~1 more once the new rosters exist)
"""


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def gs_block(src, name):
    """Body of `const NAME = {...};` or `const NAME = [...];` in a .gs file."""
    m = re.search(r"const %s = [\{\[](.*?)\n?[\}\]];" % re.escape(name), src, re.S)
    assert m, name
    return m.group(1)


def apps_script_same_name(rows, pairs=(), probes=()):
    """What appsscript/ makes of a Roster, run in Node exactly as the JS tests run
    it (test/load_gs.js; no Google API): {"sep": Config.gs SF_NAME_SEP, "shared":
    the sorted names of RosterOps.gs sharedClubNames_(rows), "names":
    [sfClubName_(club, partner, shared) for each (partner, club) of `pairs`],
    "held": [True when newClubHoldReasons_ holds a new club (partner, club) of
    `probes` for its name (kind samename)]}. rows: dicts with partner, club,
    full_name, status, region - Roster rows as loadRoster_ hands them over. The
    probe's girls are on nobody's roster, so no other hold reason can fire.
    None when Node is not installed (make check runs the JS tests first, so
    there it always is)."""
    import shutil
    import subprocess
    if not shutil.which("node"):
        return None
    script = """
const gs = require(process.argv[1])(['SF_NAME_SEP', 'sharedClubNames_', 'sfClubName_', 'newClubHoldReasons_']);
const inp = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const shared = gs.sharedClubNames_(inp.rows);
process.stdout.write(JSON.stringify({
  sep: gs.SF_NAME_SEP,
  shared: Object.keys(shared).sort(),
  names: inp.pairs.map(p => gs.sfClubName_(p[1], p[0], shared)),
  held: inp.probes.map(p => gs.newClubHoldReasons_(
      { partner: p[0], club: p[1], names: ['Probe Girlone', 'Probe Girltwo'], typedPartner: false },
      inp.rows, []).some(r => r.kind === 'samename')),
}));"""
    done = subprocess.run(["node", "-e", script, os.path.join(REPO, "test", "load_gs.js")],
                          input=json.dumps({"rows": rows, "pairs": list(pairs), "probes": list(probes)}),
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


class AutoSyncPlan(unittest.TestCase):
    def test_parse_plan_reads_every_line_kind(self):
        plan = auto_sync.parse_plan(DRY_RUN)
        self.assertEqual([c["club"] for c in plan["creates"]], ["Brand New Club"])
        self.assertEqual(plan["creates"][0]["girls"], 9)
        self.assertEqual([(u["qid"], u["club"], u["girls"]) for u in plan["updates"]],
                         [("120", "Old Name Club", 14), ("121", 'Sunrise Club, Eastside "B"', 3)])
        self.assertEqual(plan["deletes"], [{"qid": "140", "club": "Elsewhere", "region": "Africa"}])
        self.assertEqual(plan["rules"], 57)
        self.assertEqual((plan["roster_clubs"], plan["roster_girls"]), (12, 176))
        self.assertEqual(len(plan["warnings"]), 2)
        self.assertEqual(plan["picker"], [{"op": "UPDATE", "clubs": 13}])
        self.assertEqual(auto_sync.changes(plan), 5)

    def test_in_sync_when_only_the_conditions_rewrite_is_planned(self):
        plan = auto_sync.parse_plan("Roster: 3 active clubs in U.S (40 girls); 300 clubs overall\n"
                                    "\nDRY RUN (use --apply to write):\n"
                                    "  - REPLACE conditions (40 rules)\n")
        self.assertEqual(auto_sync.changes(plan), 0)
        self.assertEqual(plan["rules"], 40)
        self.assertEqual(auto_sync.check_bands(plan), [])
        self.assertEqual(auto_sync.plan_summary(plan), "0 create(s), 0 update(s), 0 delete(s), 0 warning(s)")

    def test_summary_json_gives_the_same_shape(self):
        summary = {"creates": [{"club": "A", "partner": "P", "girls": 2}],
                   "updates": [{"qid": "7", "club": "B", "girls": 5}],
                   "deletes": [], "rules": 9, "warnings": ["  ? 'B' (q7) is on the form"],
                   "calls": ["CREATE roster 'A' (2 girls)", "UPDATE roster 'B' (q7, 5 girls)",
                             "UPDATE club picker (2 clubs)", "REPLACE conditions (9 rules)"],
                   "roster_clubs": 2, "roster_girls": 7}
        plan = auto_sync.plan_from_summary(summary)
        self.assertEqual(set(plan), set(auto_sync.parse_plan("")))
        self.assertEqual(plan["picker"], [{"op": "UPDATE", "clubs": 2}])
        self.assertEqual(auto_sync.changes(plan), 3)
        self.assertEqual(plan["warnings"], ["? 'B' (q7) is on the form"])
        self.assertEqual(auto_sync.plan_summary(plan),
                         "1 create(s), 1 update(s), 0 delete(s), 1 warning(s), update club picker")

    def test_bands_refuse_deletes_big_waves_and_replaced_rosters(self):
        plan = auto_sync.parse_plan(DRY_RUN)
        reasons = auto_sync.check_bands(plan)
        self.assertTrue(any("delete" in r for r in reasons))
        self.assertTrue(any("shares no names" in r for r in reasons))
        self.assertEqual(len(reasons), 2)
        big = {"creates": [{"club": f"C{i}", "girls": 1} for i in range(6)], "updates": [],
               "deletes": [], "rules": 1, "warnings": [], "roster_clubs": 50, "roster_girls": 1}
        self.assertEqual(len(auto_sync.check_bands(big)), 1)
        self.assertEqual(auto_sync.check_bands(big, max_creates=6), [])
        many = dict(big, creates=[], updates=[{"qid": str(i), "club": "c", "girls": 1} for i in range(21)])
        self.assertIn("update", auto_sync.check_bands(many)[0])

    def test_bands_catch_a_truncated_export(self):
        warnings = [f"? 'Club {i}' (q{i}) {auto_sync.NOT_IN_EXPORT} - keeping its current roster"
                    for i in range(12)]
        plan = {"creates": [], "updates": [{"qid": "1", "club": "x", "girls": 2}], "deletes": [],
                "rules": 5, "warnings": warnings, "roster_clubs": 30, "roster_girls": 100}
        self.assertTrue(any("truncated" in r for r in auto_sync.check_bands(plan)))
        plan["roster_clubs"] = 200      # 12 of 200 is normal drift, not truncation
        self.assertEqual(auto_sync.check_bands(plan), [])

    def test_blank_region_rows(self):
        rows = [{"partner": "P", "club": "A", "status": "active", "region": ""},
                {"partner": "P", "club": "A", "status": "ACTIVE ", "region": "  "},
                {"partner": "P", "club": "A", "status": "inactive", "region": ""},
                {"partner": "Q", "club": "B", "status": "active", "region": "Asia"},
                {"partner": " Q ", "club": "C", "status": "active", "region": ""}]
        self.assertEqual(auto_sync.blank_region_rows(rows), [("P", "A", 2), ("Q", "C", 1)])

    def test_verify_report(self):
        clean = {"error_conditions": 0, "salesforce": True, "rule_problems": [],
                 "languages": ["a"] * 12, "duplicate_club_questions": [],
                 "region_check": {"missing_from_form": [], "not_in_roster": ["Extra"],
                                  "rosters_out_of_date": []}}
        problems, notes = auto_sync.verify_report(clean)
        self.assertEqual(problems, [])
        self.assertEqual(len(notes), 1)
        bad = dict(clean, error_conditions=2, salesforce=False, languages=["en"],
                   region_check={"missing_from_form": ["M"], "not_in_roster": [],
                                 "rosters_out_of_date": [["S", 1, 0]]})
        problems, _ = auto_sync.verify_report(bad)
        self.assertEqual(len(problems), 5)
        self.assertIn("no region check", auto_sync.verify_report(dict(clean, region_check=None))[0][0])

    def test_redact_masks_names_longest_first_and_case_insensitively(self):
        text = "UPDATE roster 'X' - Ana Fennwhistle Long and ana fennwhistle, plus Bo Vexmoorish."
        out = auto_sync.redact(text, ["Ana Fennwhistle", "Ana Fennwhistle Long", "Bo Vexmoorish", ""])
        self.assertEqual(out, "UPDATE roster 'X' - [girl] and [girl], plus [girl].")
        self.assertEqual(auto_sync.redact("nothing", []), "nothing")
        # one-word roster entries must not garble ordinary words or region names
        self.assertEqual(auto_sync.redact("== Asia  form 262383129464057", ["Asia"]),
                         "== Asia  form 262383129464057")
        # whole words only: a name inside another word stays
        self.assertEqual(auto_sync.redact("Milan Ostrivane's club", ["Lan Ostrivane"]),
                         "Milan Ostrivane's club")

    def test_plan_line_formats_still_exist_in_the_sync_tool(self):
        src = read(os.path.join(REPO, "sync_attendance_form.py"))
        # string literals in the source may be split across lines: join them before looking
        joined = re.sub(r'"\s*\n\s*"', "", src)
        for fragment in ("CREATE roster '{club}' (", "UPDATE roster '{club}' (q{qid}, ",
                         "DELETE roster '{club}' (q{qid}, belongs to {reg})",
                         "REPLACE conditions ({len(conds)} rules", auto_sync.NOT_IN_EXPORT,
                         auto_sync.NO_SHARED_NAMES, "--summary-json",
                         "CREATE club picker ({len(picker_names)} clubs)",
                         "UPDATE club picker ({len(picker_names)} clubs: ",
                         "CREATE club guard (below the Club picker)",
                         "UPDATE club guard ({', '.join(sorted(drift))})",
                         # the three same-name warnings the runner acts on
                         f'Q5_CHANGES = "{auto_sync.SF_NAME_CHANGE}"',
                         f'NOT_ADDED = "{auto_sync.SAME_NAME_REFUSED}"',
                         f'RULES_OLDER = "{auto_sync.RULES_OLDER}"',
                         "{Q5_CHANGES} from '{c['old']}' to '{c['new']}'", "- {NOT_ADDED}",
                         "its rule tests '{value}', {RULES_OLDER} ",
                         # question 18 the old way, and the required flag (docs/plans/2026-09-30-contact-ids.md)
                         f'CONTACT_IDS_STALE = "{auto_sync.CONTACT_IDS_STALE}"', "{CONTACT_IDS_STALE}: ",
                         "UPDATE roster '{club}' (q{qid}, {options.count('|')+1} girls{also})",
                         'also = f"; required: {want_required}"',
                         "REQUIRED roster '{club}' (q{qid}: {want_required})"):
            self.assertIn(fragment, joined, fragment)
        for line, rx in (("UPDATE roster 'A' (q1, 2 girls)", auto_sync.UPDATE_RX),
                         ("UPDATE roster 'A' (q1, 2 girls; required: Yes)", auto_sync.UPDATE_RX),
                         ("UPDATE roster 'A' (q1, 2 girls; required: No)", auto_sync.UPDATE_RX),
                         ("REQUIRED roster 'A' (q1: Yes)", auto_sync.REQUIRED_RX),
                         ("REQUIRED roster 'Club (B)' (q1: No)", auto_sync.REQUIRED_RX)):
            self.assertTrue(rx.match("  - " + line), line)
        self.assertFalse(auto_sync.UPDATE_RX.match("  - UPDATE roster 'A' (q1, 2 girls; required: Maybe)"))
        self.assertFalse(auto_sync.REQUIRED_RX.match("  - UPDATE roster 'A' (q1, 2 girls; required: Yes)"))
        # the partner list is retired: the sync writes no such line any more (the runner's
        # pattern for it stays until the dead code is cleaned up, docs/BACKLOG.md)
        self.assertNotIn("partner picker (", joined)

    SAME_NAME_DRY_RUN = (
        "Roster: 3 active clubs in Africa (40 girls); 300 clubs overall\n"
        "  ! new club 'Stars' (Partner Three) has the name of Partner One's club - not added: "
        "give it a different name\n"
        "  ! 'Beta Club 2' (q13): Club Name (question 5, what Salesforce reads) changes from "
        "'Beta Club' to 'Beta Club 2' - rename its Salesforce account first; an --apply needs "
        "--q5-change-ok\n"
        "\nDRY RUN (use --apply to write):\n"
        "  - REPLACE conditions (25 rules)\n")

    def run_region(self, text, apply=False, summary=None, region_check=None):
        """auto_sync.Run.region("Africa") over a fabricated dry run; with apply, every
        later step (backup, apply, verify) answers ok and a clean form_status report -
        or one whose region check says `region_check`."""
        import tempfile
        import types
        from unittest import mock
        clean = {"error_conditions": 0, "salesforce": True, "rule_problems": [], "languages": ["a"] * 12,
                 "region_check": {"missing_from_form": [], "not_in_roster": [], "rosters_out_of_date": [],
                                  **(region_check or {})}}
        with tempfile.TemporaryDirectory() as out:
            args = types.SimpleNamespace(apply=apply, out=out, max_creates=5, max_updates=20,
                                         trigger="test", run_url="")
            run = auto_sync.Run(args)
            run.synced = []

            def sync_(csv_path, region, form, apply, summary_path=None):
                run.synced.append(apply)
                if summary is not None and summary_path:
                    with open(summary_path, "w", encoding="utf-8") as f:
                        json.dump(summary, f)
                return types.SimpleNamespace(returncode=0, stdout=text, stderr="")

            with mock.patch.object(run, "sync", sync_), \
                    mock.patch.object(run, "cmd", lambda *a, **k: types.SimpleNamespace(
                        returncode=0, stdout=json.dumps([clean]), stderr="")), \
                    mock.patch.object(run, "save_conditions", lambda form: None), \
                    mock.patch("builtins.print"):
                run.region("Africa", os.path.join(out, "roster.csv"))
        return run

    def test_a_question_5_change_is_never_in_sync_and_never_applied(self):
        # a rules-only plan (no roster, picker or guard write) used to read "in-sync"; one that
        # changes what an existing club sends to Salesforce must stop the region instead
        text = "\n".join(l for l in self.SAME_NAME_DRY_RUN.splitlines() if "new club" not in l) + "\n"
        plan = auto_sync.parse_plan(text)
        self.assertEqual((auto_sync.changes(plan), len(auto_sync.q5_changes(plan))), (0, 1))
        reasons = auto_sync.check_bands(plan)
        self.assertEqual(len(reasons), 1)
        self.assertIn("question 5 (what Salesforce reads) would change for 1 existing club(s)", reasons[0])
        self.assertIn("--q5-change-ok", reasons[0])
        for apply in (False, True):
            run = self.run_region(text, apply=apply)
            self.assertEqual([r[7] for r in run.results], ["attention"], apply)
            self.assertEqual(run.synced, [False])                     # the dry run only, never an apply
            (title, detail), = run.attention
            self.assertIn("Africa: not applied", title)
            self.assertIn("changes from 'Beta Club' to 'Beta Club 2'", detail)
        # with other changes planned too: still nothing is applied for the region
        busy = text.replace("  - REPLACE", "  - CREATE roster 'Gamma Club' (2 girls)\n  - REPLACE")
        run = self.run_region(busy, apply=True)
        self.assertEqual(([r[7] for r in run.results], run.synced), (["attention"], [False]))

    def test_a_refused_new_club_raises_attention_and_the_rest_goes_on(self):
        text = "\n".join(l for l in self.SAME_NAME_DRY_RUN.splitlines() if "Beta Club 2" not in l) + "\n"
        plan = auto_sync.parse_plan(text)
        self.assertEqual(len(auto_sync.refused_clubs(plan)), 1)
        self.assertEqual(auto_sync.check_bands(plan), [])              # not a band: nothing is held back
        # nothing else planned: in-sync, and ATTENTION all the same (exit 2 in main)
        run = self.run_region(text)
        self.assertEqual([r[7:9] for r in run.results],
                         [["in-sync", "1 new club(s) not added (name in use)"]])
        (title, detail), = run.attention
        self.assertIn("Africa: 1 new club(s) NOT added to the form", title)
        self.assertIn("new club 'Stars' (Partner Three) has the name of Partner One's club", detail)
        # the way out it names is the one that works for a club with no question of its own:
        # without --sheet-only the rename would relabel the OTHER partner's roster question
        self.assertIn("tools/rename_club.py --partner … --old … --new … --sheet-only", detail)
        # with a roster change in the same plan: that change is applied, the refusal reported.
        # form_status's region check goes by club name, so after the apply it counts the
        # refused club against its namesake on the form ("differ"; "missing" when the
        # namesake is on another region's form): applied-with-problems, until the rename
        busy = text.replace("  - REPLACE", "  - CREATE roster 'Gamma Club' (2 girls)\n  - REPLACE")
        for check, line in (({"rosters_out_of_date": [["Stars", 2, 0]]},
                             "- 1 roster(s) still differ from the sheet: Stars"),
                            ({"missing_from_form": ["Stars"]},
                             "- 1 club(s) still missing from the form: Stars")):
            run = self.run_region(busy, apply=True, region_check=check)
            self.assertEqual(run.synced, [False, True])
            self.assertEqual([r[7] for r in run.results], ["applied-with-problems"])
            self.assertIn("1 new club(s) not added (name in use)", run.results[0][8])
            (refusal, _), (title, detail) = run.attention
            self.assertIn("1 new club(s) NOT added to the form", refusal)
            self.assertIn("Africa: applied, but the form still has problems", title)
            self.assertIn(line, detail)
            self.assertIn("naming a club listed above as NOT added is expected until that club is renamed",
                          detail)
        # (a refused club whose girls all sit on its namesake's roster would verify clean)
        run = self.run_region(busy, apply=True)
        self.assertEqual(([r[7] for r in run.results], len(run.attention)), (["applied"], 1))
        # and without a refused club the verify problems carry no such note
        plain = "\n".join(l for l in busy.splitlines() if "new club" not in l) + "\n"
        run = self.run_region(plain, apply=True, region_check={"missing_from_form": ["Stars"]})
        (title, detail), = run.attention
        self.assertNotIn("NOT added", detail)
        # the summary file gives the same warnings
        summary = {"creates": [], "updates": [], "deletes": [], "rules": 25, "calls": [],
                   "warnings": [l for l in text.splitlines() if l.startswith("  ! ")]}
        self.assertEqual(len(auto_sync.refused_clubs(auto_sync.plan_from_summary(summary))), 1)

    STALE_RULES_DRY_RUN = (
        "Roster: 3 active clubs in Africa (40 girls); 300 clubs overall\n"
        "  ! 'Stars' (q11): its rule tests 'Stars', which the Club picker does not list (it lists "
        "'Stars - Partner One') - the rules and the picker are out of step (a restored backup, an "
        "apply that stopped half-way?): until an --apply rewrites the rules this roster does not show\n"
        "  conditions: 18 kept, 2 new, 3 dropped\n"
        "\nDRY RUN (use --apply to write):\n"
        "  - REPLACE conditions (20 rules)\n")

    def test_rules_older_than_the_picker_are_never_in_sync(self):
        # a conditions backup from before the same-name switch restored over the switched
        # picker, or a hand apply that stopped after the picker write: the sync plans only
        # REPLACE conditions (no question-5 change: the picker says what the club sends), which
        # is no change to the runner - it read "in-sync" on every run while those clubs'
        # rosters never showed and the club guard blocked their mentors
        plan = auto_sync.parse_plan(self.STALE_RULES_DRY_RUN)
        self.assertEqual((auto_sync.changes(plan), auto_sync.q5_changes(plan), len(auto_sync.stale_rules(plan))),
                         (0, [], 1))
        self.assertEqual(auto_sync.check_bands(plan), [])      # no band: see the last case
        for apply in (False, True):
            run = self.run_region(self.STALE_RULES_DRY_RUN, apply=apply)
            self.assertEqual([r[7] for r in run.results], ["attention"], apply)
            self.assertIn("1 roster rule(s) test a name the Club picker does not list", run.results[0][8])
            self.assertEqual(run.synced, [False])              # a rules-only write is never unattended
            (title, detail), = run.attention
            self.assertIn("Africa: 1 roster rule(s) test a name the Club picker does not list", title)
            self.assertIn("- ! 'Stars' (q11): its rule tests 'Stars'", detail)
            self.assertIn("--apply", detail)
            self.assertIn(auto_sync.REGIONAL_FORMS["Africa"], detail)
        # the summary file gives the same
        summary = {"creates": [], "updates": [], "deletes": [], "rules": 20,
                   "calls": ["REPLACE conditions (20 rules)"],
                   "warnings": [l for l in self.STALE_RULES_DRY_RUN.splitlines() if l.startswith("  ! ")]}
        run = self.run_region(self.STALE_RULES_DRY_RUN, summary=summary)
        self.assertEqual([r[7] for r in run.results], ["attention"])
        # a rules-only plan with no such line stays in-sync, as ever
        quiet = "\n".join(l for l in self.STALE_RULES_DRY_RUN.splitlines() if "its rule tests" not in l) + "\n"
        run = self.run_region(quiet)
        self.assertEqual(([r[7] for r in run.results], run.attention), (["in-sync"], []))
        # with a roster change in the same plan the ordinary apply rewrites the rules - the
        # repair that already existed - so this is no band and holds nothing back
        busy = self.STALE_RULES_DRY_RUN.replace("  - REPLACE", "  - CREATE roster 'Gamma Club' (2 girls)\n  - REPLACE")
        run = self.run_region(busy, apply=True)
        self.assertEqual((run.synced, [r[7] for r in run.results], run.attention), ([False, True], ["applied"], []))

    def test_main_checks_the_names_across_the_regions_and_exits_2(self):
        # each region alone is in-sync; the two send one Salesforce name between them. Only
        # main() sees both: it must make the cross-region check, write ATTENTION.md and exit 2
        import tempfile
        import types
        from unittest import mock
        sent = {"Africa": {"qid": "11", "partner": "Partner One", "club": "Stars", "value": "Stars"},
                "Asia": {"qid": "20", "partner": "Partner Three", "club": "Stars", "value": "STARS"}}

        def sync_(run, csv_path, region, form, apply, summary_path=None):
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump({"creates": [], "updates": [], "deletes": [], "rules": 25, "warnings": [],
                           "calls": [], "sf_names": [sent[region]]}, f)
            return types.SimpleNamespace(returncode=0, stderr="", stdout=(
                f"Roster: 1 active clubs in {region} (1 girls); 2 clubs overall\n\nDRY RUN (use --apply "
                "to write):\n  nothing to do - form already matches the sheet\n"))

        def run_main(regions):
            with tempfile.TemporaryDirectory() as tmp:
                roster = os.path.join(tmp, "roster.csv")
                with open(roster, "w", encoding="utf-8") as f:
                    f.write("girl_id,partner,club,full_name,status,region\n"
                            "DEMOCLUB-SAMPLE-001,Partner One,Stars,Ann Poe,active,Africa\n"
                            "DEMOCLUB-SAMPLE-002,Partner Three,Stars,Sue Moe,active,Asia\n")
                argv = ["auto_sync.py", "--roster", roster, "--out", tmp, "--min-active", "1"]
                for region in regions:
                    argv += ["--region", region]
                code = 0
                with mock.patch.object(sys, "argv", argv), \
                        mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}), \
                        mock.patch.object(auto_sync.Run, "sync", sync_), mock.patch("builtins.print"):
                    try:
                        auto_sync.main()
                    except SystemExit as e:
                        code = e.code
                path = os.path.join(tmp, "ATTENTION.md")
                return code, read(path) if os.path.exists(path) else ""

        code, attention = run_main(["Africa", "Asia"])
        self.assertEqual(code, 2)
        self.assertIn("## 1 Salesforce name(s) are sent by more than one club", attention)
        self.assertIn("- 'Stars': Stars (Partner One, Africa); Stars (Partner Three, Asia)", attention)
        self.assertNotIn("Ann Poe", attention)
        # one region alone has nothing to clash with: exit 0, no ATTENTION file
        self.assertEqual(run_main(["Africa"]), (0, ""))

    def test_no_two_clubs_of_any_region_may_send_one_salesforce_name(self):
        africa = [{"qid": "11", "partner": "Partner One", "club": "Stars", "value": "Stars - Partner One"},
                  {"qid": "12", "partner": "Partner Two", "club": "Stars", "value": "Stars - Partner Two"},
                  {"qid": "10", "partner": "Partner One", "club": "Alpha Club", "value": "Alpha Club"},
                  {"qid": None, "partner": "Partner One", "club": "Gamma Club", "value": "Gamma Club"}]
        asia = [{"qid": "20", "partner": "Partner Three", "club": "Stars", "value": "Stars - Partner Three"},
                {"qid": "21", "partner": "Partner Three", "club": "Beta Club", "value": "Beta Club"}]
        self.assertEqual(auto_sync.name_clashes({"Africa": africa, "Asia": asia}), [])
        self.assertEqual(auto_sync.name_clashes({"Africa": africa, "Asia": None}), [])   # no summary file
        # before the switch: three clubs send "Stars", in two regions; case is ignored
        plain = [dict(e, value=e["club"]) for e in africa]
        asia[0]["value"] = "STARS"
        self.assertEqual(auto_sync.name_clashes({"Africa": plain, "Asia": asia}),
                         [("Stars", ["Stars (Partner One, Africa)", "Stars (Partner Two, Africa)",
                                     "Stars (Partner Three, Asia)"])])
        # a leftover question for the same club is told apart by its qid when the form names no partner
        twice = [{"qid": "30", "partner": "", "club": "Moon", "value": "Moon"},
                 {"qid": "31", "partner": "", "club": "Moon", "value": "Moon"}]
        self.assertEqual(auto_sync.name_clashes({"U.S": twice}),
                         [("Moon", ["Moon (q30, U.S)", "Moon (q31, U.S)"])])
        # the runner reports it once for the whole run, after the regions
        text = ("Roster: 3 active clubs in Africa (40 girls); 300 clubs overall\n"
                "\nDRY RUN (use --apply to write):\n  nothing to do - form already matches the sheet\n")
        run = self.run_region(text, summary={"creates": [], "updates": [], "deletes": [], "rules": 25,
                                             "warnings": [], "calls": [], "sf_names": plain})
        self.assertEqual(([r[7] for r in run.results], run.attention), (["in-sync"], []))
        from unittest import mock
        with mock.patch("builtins.print"):
            run.check_names()
        (title, detail), = run.attention
        self.assertIn("1 Salesforce name(s) are sent by more than one club", title)
        self.assertIn("- 'Stars': Stars (Partner One, Africa); Stars (Partner Two, Africa)", detail)
        self.assertIn("--same-name-switch", detail)

    def test_check_storage_judges_each_limit_on_its_own(self):
        """docs/plans/2026-10-06-photos-to-drive.md: once per run, the storage line in the log;
        an ATTENTION per limit at alarm naming it (upload space, or the submissions cycle); at
        warn the line alone; a reader that raises is a log line, never a failed run."""
        import types
        from unittest import mock

        def run_with(answer):
            run = auto_sync.Run(types.SimpleNamespace(apply=False, out="", max_creates=5, max_updates=20,
                                                      trigger="test", run_url=""))

            def read():
                if isinstance(answer, Exception):
                    raise answer
                return dict(answer)
            with mock.patch("builtins.print"):
                run.check_storage(read)
            return run
        base = {"plan": "SILVER", "uploads": 1340458410, "uploads_cap": 10738466816,
                "submissions": 474, "submissions_cap": 2500, "reset": "2026-10-21"}
        run = run_with(base)
        self.assertEqual((run.attention, run.failed), ([], False))
        self.assertEqual(run.lines[-1].strip(), "storage: upload space 1.25 GiB of 10.00 GiB (12.5%) -> ok; "
                         "submissions this cycle 474 of 2,500 (19.0%, resets 2026-10-21) -> ok; plan SILVER")
        run = run_with(dict(base, uploads=base["uploads_cap"] // 2))          # warn: the line alone
        self.assertEqual(run.attention, [])
        self.assertIn("(50.0%) -> warn;", run.lines[-1])
        run = run_with(dict(base, uploads=base["uploads_cap"] * 9 // 10))     # alarm on upload space
        (title, detail), = run.attention
        self.assertEqual(title, "Jotform upload space at 90% - the forms stop at 100%")
        for fragment in ("SILVER plan allows 10.00 GiB", "9.00 GiB are used", "Gold versus retention",
                         "Auto Delete Submissions", "frees nothing"):
            self.assertIn(fragment, detail)
        self.assertNotIn("submissions this cycle", title)
        self.assertEqual(run.lines[-1], "  ! " + title)
        run = run_with(dict(base, submissions=2100))                          # alarm on the cycle only
        (title, detail), = run.attention
        self.assertEqual(title, "Jotform submissions this cycle at 84% - the forms stop at 100%")
        for fragment in ("2,500 submissions a month", "2,100 have arrived", "resets on 2026-10-21",
                         "busy month, not storage", "Gold versus retention"):
            self.assertIn(fragment, detail)
        self.assertNotIn("upload space", title)
        run = run_with(dict(base, uploads=base["uploads_cap"], submissions=2500))   # both: one each
        self.assertEqual([t.split(" at ")[0] for t, _ in run.attention],
                         ["Jotform upload space", "Jotform submissions this cycle"])
        run = run_with(RuntimeError("nope"))                                  # a failed read
        self.assertEqual((run.attention, run.failed), ([], False))
        self.assertEqual(run.lines[-1].strip(), "storage: could not be read (RuntimeError)")
        self.assertNotIn("nope", "\n".join(run.lines))
        # main() reads it after the regions, through the one client, with the key from the environment
        src = read(os.path.join(REPO, "tools", "auto_sync.py"))
        self.assertIn('run.check_names()\n    run.check_storage(lambda: usage.read_usage(Client(os.environ["JOTFORM_API_KEY"], max_time=60)))',
                      src)                      # bounded: a stalled GET must not hold the run

    def test_a_club_guard_update_is_a_change_and_parses_from_both_shapes(self):
        text = ("Roster: 3 active clubs in Asia (40 girls); 300 clubs overall\n"
                "\nDRY RUN (use --apply to write):\n"
                "  - UPDATE club picker (96 clubs: calcValues)\n"
                "  - UPDATE club guard (hidden, text)\n"
                "  - REPLACE conditions (127 rules)\n")
        plan = auto_sync.parse_plan(text)
        self.assertEqual(plan["club_guard"], [{"op": "UPDATE"}])
        self.assertEqual(plan["picker"], [{"op": "UPDATE", "clubs": 96}])
        self.assertEqual(auto_sync.changes(plan), 2)
        self.assertEqual(auto_sync.check_bands(plan), [])
        self.assertEqual(auto_sync.plan_summary(plan), "0 create(s), 0 update(s), 0 delete(s), "
                                                       "0 warning(s), update club picker, update club guard")
        summary = {"creates": [], "updates": [], "deletes": [], "rules": 127, "warnings": [],
                   "calls": ["CREATE club guard (below the Club picker)", "REPLACE conditions (127 rules)"]}
        plan = auto_sync.plan_from_summary(summary)
        self.assertEqual(plan["club_guard"], [{"op": "CREATE"}])
        self.assertEqual(auto_sync.changes(plan), 1)
        for label in ("CREATE club guard (below the Club picker)", "UPDATE club guard (text)",
                      "UPDATE club guard (hidden, text)"):
            self.assertTrue(auto_sync.GUARD_RX.match("  - " + label), label)
        self.assertFalse(auto_sync.GUARD_RX.match("  - UPDATE club picker (3 clubs: calcValues)"))
        self.assertFalse(auto_sync.PICKER_RX.match("  - UPDATE club guard (text)"))

    def test_a_partner_list_update_is_a_change_and_parses_from_both_shapes(self):
        text = ("Roster: 3 active clubs in Africa (40 girls); 300 clubs overall\n"
                "\nDRY RUN (use --apply to write):\n"
                "  - UPDATE partner picker (8 partners: options)\n"
                "  - REPLACE conditions (254 rules)\n")
        plan = auto_sync.parse_plan(text)
        self.assertEqual(plan["partner_picker"], [{"op": "UPDATE", "partners": 8}])
        self.assertEqual(plan["picker"], [])
        self.assertEqual(auto_sync.changes(plan), 1)
        self.assertEqual(auto_sync.check_bands(plan), [])
        # applied unattended, so the SyncLog detail must say what was written (integration review F2)
        self.assertEqual(auto_sync.plan_summary(plan),
                         "0 create(s), 0 update(s), 0 delete(s), 0 warning(s), update partner list")
        # …and the runner's row uses it (a dry run here: "would apply: …")
        import tempfile
        import types
        from unittest import mock
        with tempfile.TemporaryDirectory() as out:
            args = types.SimpleNamespace(apply=False, out=out, max_creates=5, max_updates=20,
                                         trigger="test", run_url="")
            run = auto_sync.Run(args)
            with mock.patch.object(run, "sync", lambda *a, **k: types.SimpleNamespace(
                    returncode=0, stdout=text, stderr="")), mock.patch("builtins.print"):
                run.region("Africa", os.path.join(out, "roster.csv"))
        self.assertEqual([r[7:9] for r in run.results],
                         [["dry-run", "would apply: " + auto_sync.plan_summary(plan)]])
        summary = {"creates": [], "updates": [], "deletes": [], "rules": 254, "warnings": [],
                   "calls": ["CREATE partner picker (9 partners)", "REPLACE conditions (254 rules)"]}
        self.assertEqual(auto_sync.plan_from_summary(summary)["partner_picker"],
                         [{"op": "CREATE", "partners": 9}])
        # the sync's own labels match the pattern the runner reads
        for label in ("CREATE partner picker (2 partners)", "UPDATE partner picker (2 partners: options)",
                      "UPDATE partner picker (8 partners: hidden, options)"):
            self.assertTrue(auto_sync.PARTNER_PICKER_RX.match("  - " + label), label)
        self.assertFalse(auto_sync.PARTNER_PICKER_RX.match(
            "  - HIDE partner textbox (q331: the partner list replaces it)"))

    def test_a_failed_apply_says_later_runs_will_not_repair_it(self):
        # a half-write (the roster and picker written, the conditions PUT failed twice)
        # leaves only the rules stale, and a rules-only difference is not a change to
        # the runner: every later run reports in-sync while the new club's roster never
        # shows and, on a guarded form, its mentors cannot submit. ATTENTION says so.
        import tempfile
        import types
        from unittest import mock
        dry = ("Roster: 3 active clubs in Africa (40 girls); 300 clubs overall\n"
               "\nDRY RUN (use --apply to write):\n"
               "  - CREATE roster 'Gamma Club' (2 girls)\n"
               "  - REPLACE conditions (25 rules)\n")
        results = iter([types.SimpleNamespace(returncode=0, stdout=dry, stderr="")]
                       + [types.SimpleNamespace(returncode=1, stdout="", stderr="PUT /properties: 502")] * 2)
        with tempfile.TemporaryDirectory() as out:
            args = types.SimpleNamespace(apply=True, out=out, max_creates=5, max_updates=20,
                                         trigger="test", run_url="")
            run = auto_sync.Run(args)
            with mock.patch.object(run, "sync", lambda *a, **k: next(results)), \
                    mock.patch.object(run, "cmd", lambda *a, **k: types.SimpleNamespace(
                        returncode=0, stdout="", stderr="")), \
                    mock.patch.object(run, "save_conditions", lambda form: None), \
                    mock.patch("builtins.print"):
                run.region("Africa", os.path.join(out, "roster.csv"))
        self.assertTrue(run.failed)
        self.assertEqual([r[7] for r in run.results], ["failed"])
        (title, detail), = run.attention
        self.assertIn("APPLY FAILED", title)
        self.assertIn("later runs report this form in-sync", detail)
        self.assertIn("--apply", detail)
        self.assertIn("PUT /properties: 502", detail)

    def test_picker_shape_is_the_searchable_component(self):
        self.assertEqual(sync.PICKER_PROPS["multipleSelections"], "Yes")   # Jotform's type-to-filter dropdown
        self.assertEqual(sync.PICKER_PROPS["required"], "Yes")
        self.assertNotIn("on a computer", sync.PICKER_PROPS["subLabel"])
        # the label and sublabel must have translations queued for the rollout
        additions = json.loads(read(os.path.join(REPO, "tools", "translations_additions.json")))
        self.assertIn(sync.PICKER_TEXT, additions)
        self.assertIn(sync.PICKER_SUBLABEL, additions)

    def test_partner_list_shape_is_the_module_dropdowns(self):
        # pinned here, not read back from PARTNER_PICKER_PROPS: a change to it would be
        # applied to Africa unattended by the next runner apply (an UPDATE is a change)
        self.assertEqual(sync.PARTNER_PICKER_PROPS["hidden"], "Yes")     # only a shared name shows it
        self.assertEqual(sync.PARTNER_PICKER_PROPS["required"], "Yes")   # once shown, a partner is chosen
        self.assertEqual(sync.PARTNER_PICKER_PROPS["multipleSelections"], "No")   # one partner
        self.assertEqual(sync.PARTNER_PICKER_PROPS["text"], "Partner")   # already translated everywhere
        self.assertEqual(sync.PARTNER_PICKER_PROPS["emptyText"], "Please Select")
        self.assertEqual(sync.PARTNER_PICKER_PROPS["subLabel"], "")


class SheetWhen(unittest.TestCase):
    """auto_sync.sheet_when: SyncLog's `when` is the sheet's wall clock, whatever the
    process zone (the Actions runner's TZ, or the Mac's)."""

    def test_new_york_wall_time_under_any_process_zone(self):
        import datetime as dt
        import time
        utc = dt.timezone.utc
        cases = [(dt.datetime(2026, 9, 30, 10, 0, 0, tzinfo=utc), "2026-09-30 06:00:00"),    # EDT, -4
                 (dt.datetime(2026, 12, 1, 3, 30, 15, tzinfo=utc), "2026-11-30 22:30:15"),   # EST, -5
                 (dt.datetime(2026, 9, 30, 19, 0, 0, tzinfo=dt.timezone(dt.timedelta(hours=9))),
                  "2026-09-30 06:00:00")]                     # the same EDT instant, given in JST
        saved = os.environ.get("TZ")
        try:
            for tz in ("UTC", "Asia/Tokyo"):
                os.environ["TZ"] = tz
                time.tzset()
                for instant, want in cases:
                    self.assertEqual(auto_sync.sheet_when(instant, "America/New_York"), want, tz)
        finally:
            if saved is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = saved
            time.tzset()

    def test_a_naive_instant_is_refused(self):
        import datetime as dt
        with self.assertRaises(ValueError):
            auto_sync.sheet_when(dt.datetime(2026, 9, 30, 6, 0, 0), "America/New_York")

    def test_the_synclog_rows_get_the_sheets_zone(self):
        import datetime as dt
        import tempfile
        import types
        from unittest import mock
        with tempfile.TemporaryDirectory() as out:
            args = types.SimpleNamespace(apply=False, out=out, trigger="test", run_url="")
            run = auto_sync.Run(args)
        self.assertIsNotNone(run.started.utcoffset())
        run.started = dt.datetime(2026, 9, 30, 3, 30, 0, tzinfo=dt.timezone.utc)
        with mock.patch("builtins.print"):
            run.result("Asia", None, "in-sync", "")
        appended = []
        with mock.patch.object(auto_sync.sc, "time_zone", lambda svc: "America/New_York"), \
                mock.patch.object(auto_sync.sc, "_has_tab", lambda svc, t: True), \
                mock.patch.object(auto_sync.sc, "read_tab", lambda svc, t: [auto_sync.SYNC_LOG_COLS]), \
                mock.patch.object(auto_sync.sc, "append_rows",
                                  lambda svc, t, rows: appended.extend((t, list(r)) for r in rows)), \
                mock.patch("builtins.print"):
            run.append_synclog(object())
        self.assertEqual([(t, r[0], r[2]) for t, r in appended],
                         [("SyncLog", "2026-09-29 23:30:00", "Asia")])
        self.assertRegex(run.when, r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d [+-]\d{4}$")   # local, with offset


class SheetsClientGet(unittest.TestCase):
    """tools/sheets_client.py's spreadsheets.get on a fake service: a 403/404 exits with what
    to fix, for the tab list and the sheet's zone alike (SystemExit, which auto_sync's
    with_retry does not retry), and the zone must be a named IANA zone."""

    class HttpError(Exception):
        """googleapiclient.errors.HttpError's shape (err.resp.status); the real package is
        not installed where `make check` runs in CI."""

        def __init__(self, status):
            super().__init__(f"HTTP {status}")
            self.resp = type("Resp", (), {"status": status, "reason": ""})()

    class Svc:
        """spreadsheets().get(...).execute() answers `answer`, or raises it."""

        def __init__(self, answer):
            self.answer, self.fields = answer, []

        def spreadsheets(self):
            return self

        def get(self, spreadsheetId, fields):
            self.fields.append(fields)
            return self

        def execute(self):
            if isinstance(self.answer, BaseException):
                raise self.answer
            return self.answer

    def call(self, fn, svc):
        import types
        from unittest import mock
        errors = types.ModuleType("googleapiclient.errors")
        errors.HttpError = self.HttpError
        pkg = types.ModuleType("googleapiclient")
        pkg.errors = errors
        sc = auto_sync.sc
        with mock.patch.dict(sys.modules, {"googleapiclient": pkg, "googleapiclient.errors": errors}), \
                mock.patch.object(sc, "spreadsheet_id", lambda: "SHEET"), \
                mock.patch.object(sc, "sa_email", lambda: "the-robot"):
            return fn(svc)

    def test_403_and_404_exit_with_what_to_fix(self):
        sc = auto_sync.sc
        for fn in (sc.time_zone, sc._sheets_meta):
            with self.assertRaises(SystemExit) as cm:
                self.call(fn, self.Svc(self.HttpError(403)))
            self.assertIn("Share the sheet with the-robot as Editor",
                          str(cm.exception.code), fn.__name__)
            with self.assertRaises(SystemExit) as cm:
                self.call(fn, self.Svc(self.HttpError(404)))
            self.assertIn("No spreadsheet with ID SHEET (404)", str(cm.exception.code), fn.__name__)
            with self.assertRaises(self.HttpError):       # anything else stays retryable
                self.call(fn, self.Svc(self.HttpError(503)))

    def test_with_retry_does_not_retry_the_exit(self):
        import tempfile
        import types
        from unittest import mock
        with tempfile.TemporaryDirectory() as out:
            run = auto_sync.Run(types.SimpleNamespace(apply=False, out=out, trigger="test", run_url=""))
        svc = self.Svc(self.HttpError(403))
        with mock.patch.object(auto_sync.time, "sleep", side_effect=AssertionError("retried")), \
                self.assertRaises(SystemExit):
            run.with_retry(lambda: self.call(auto_sync.sc.time_zone, svc), "SyncLog")
        self.assertEqual(svc.fields, ["properties.timeZone"])     # one request, no waiting

    def test_the_zone_must_be_a_named_iana_zone(self):
        sc = auto_sync.sc
        with self.assertRaises(SystemExit) as cm:        # a custom zone the Sheets API can return
            self.call(sc.time_zone, self.Svc({"properties": {"timeZone": "GMT-07:00"}}))
        self.assertEqual(cm.exception.code,
                         "the sheet's time zone 'GMT-07:00' is not an IANA zone name - set "
                         "File > Settings > Time zone to a named zone")
        svc = self.Svc({"properties": {"timeZone": "America/New_York"}})
        self.assertEqual(self.call(sc.time_zone, svc), "America/New_York")
        self.assertEqual(svc.fields, ["properties.timeZone"])


class ConditionBuilder(unittest.TestCase):
    CLUBS = {"10": "Alpha Club", "11": "Stars", "12": "Stars", "13": "Beta Club"}
    PARTNERS = {"11": "Partner One", "12": "Partner Two"}
    MODULES = {"1": ["Core 1"], "2": ["Core 2", "Elective - Healthy GLOW"], "3": ["Core 3"]}

    def rules(self, picker=None, **kw):
        sync._counter[0] = 0
        return sync.build_conditions(self.CLUBS, self.PARTNERS, self.MODULES, picker=picker, **kw)

    def show_rules(self, conds):
        """Rules that show a club roster or the Partner box (not the curriculum cascade)."""
        targets = set(self.CLUBS) | {sync.PARTNER}
        return [c for c in conds if c["type"] == "field"
                and any(a.get("visibility") == "Show" and a.get("field") in targets
                        for a in c["action"])]

    def test_without_picker_rules_key_on_the_club_name_textbox(self):
        conds = self.rules()
        for c in self.show_rules(conds):
            fields = {t["field"] for t in c["terms"]}
            self.assertIn(sync.CLUB_NAME, fields, c)
        agg = [c for c in conds if c["type"] == "calculation"
               and c["action"][0]["resultField"] == sync.CONTACT_IDS]
        self.assertEqual(len(agg), 1)
        self.assertEqual(agg[0]["terms"][0]["field"], sync.CLUB_NAME)
        self.assertEqual(agg[0]["action"][0]["operands"], "10,11,12,13")
        self.assertFalse([c for c in conds if c["type"] == "calculation"
                          and c["action"][0]["resultField"] == sync.CLUB_NAME])

    def test_with_picker_rules_key_on_it_and_copy_into_the_textbox(self):
        conds = self.rules(picker="500")
        for c in self.show_rules(conds):
            fields = {t["field"] for t in c["terms"]}
            self.assertIn("500", fields, c)
            self.assertNotIn(sync.CLUB_NAME, fields, c)
        # same-name clubs still need the Partner term, and the Partner box is revealed
        stars = [c for c in self.show_rules(conds) if c["action"][0]["field"] in ("11", "12")]
        self.assertEqual(len(stars), 2)
        self.assertTrue(all(any(t["field"] == sync.PARTNER for t in c["terms"]) for c in stars))
        reveal = [c for c in self.show_rules(conds) if c["action"][0]["field"] == sync.PARTNER]
        self.assertEqual(len(reveal), 1)
        copy = [c for c in conds if c["type"] == "calculation"
                and c["action"][0]["resultField"] == sync.CLUB_NAME]
        self.assertEqual(len(copy), 1)
        self.assertEqual(copy[0]["terms"][0]["field"], "500")
        self.assertEqual(copy[0]["action"][0]["equation"], "{500}")
        self.assertTrue(copy[0]["action"][0]["insertAsText"])
        agg = [c for c in conds if c["type"] == "calculation"
               and c["action"][0]["resultField"] == sync.CONTACT_IDS][0]
        self.assertEqual(agg["terms"][0]["field"], "500")
        self.assertEqual(len(conds), len(self.rules()) + 1)

    def test_indexes_are_sequential(self):
        conds = self.rules(picker="500")
        self.assertEqual([c["index"] for c in conds], [str(i) for i in range(len(conds))])
        self.assertEqual([c["priority"] for c in conds], [c["index"] for c in conds])

    def test_the_default_partner_field_is_the_typed_box(self):
        # a form without the partner list keeps exactly the rules it has today
        self.assertEqual(sync._norm_rules(self.rules(picker="500")),
                         sync._norm_rules(self.rules(picker="500", partner_field=sync.PARTNER)))
        fields = {t["field"] for c in self.rules(picker="500") for t in c["terms"]}
        self.assertIn(sync.PARTNER, fields)
        # the typed box is the partner answer itself: nothing is copied into it
        self.assertFalse([c for c in self.rules(picker="500") if c["type"] == "calculation"
                          and c["action"][0]["resultField"] == sync.PARTNER])

    def test_the_partner_list_changes_the_partner_field_and_copies_it_into_q331(self):
        typed = self.rules(picker="500")
        listed = self.rules(picker="500", partner_field="600")
        # one rule more: the chosen partner is copied into the hidden typed box, which the
        # staff notification e-mail's "Partner {partner}" row reads (integration review F1)
        copies = [c for c in listed if c["type"] == "calculation"
                  and c["action"][0]["resultField"] == sync.PARTNER]
        self.assertEqual(len(copies), 1)
        self.assertEqual([(t["field"], t["operator"]) for t in copies[0]["terms"]], [("600", "isFilled")])
        self.assertEqual((copies[0]["action"][0]["operands"], copies[0]["action"][0]["equation"]),
                         ("600", "{600}"))
        self.assertTrue(copies[0]["action"][0]["insertAsText"])
        self.assertFalse(copies[0]["action"][0]["ignoreHiddenFields"])   # as the q5 copy
        self.assertEqual(len(listed), len(typed) + 1)
        listed = [c for c in listed if c is not copies[0]]
        # the gated rules and the reveal rule test / show the list; nothing tests q331
        self.assertFalse([t for c in listed for t in c["terms"] if t["field"] == sync.PARTNER])
        self.assertFalse([a for c in listed for a in c["action"] if a.get("field") == sync.PARTNER])
        stars = [c for c in listed if c["type"] == "field"
                 and c["action"][0].get("field") in ("11", "12")]
        self.assertEqual(sorted(t["value"] for c in stars for t in c["terms"] if t["field"] == "600"),
                         ["Partner One", "Partner Two"])
        self.assertTrue(all(c["link"] == "All" for c in stars))
        reveal = [c for c in listed if c["type"] == "field" and c["action"][0].get("field") == "600"]
        self.assertEqual([(t["field"], t["value"]) for t in reveal[0]["terms"]], [("500", "Stars")])
        # swap the list back for the typed box: every rule is identical, in the same order
        back = json.loads(json.dumps(listed).replace('"field": "600"', '"field": "%s"' % sync.PARTNER))
        self.assertEqual(sync._norm_rules(back), sync._norm_rules(typed))
        changed = [a for a, b in zip(sync._norm_rules(listed), sync._norm_rules(typed)) if a != b]
        self.assertEqual(len(changed), 3)                   # 2 gated rosters + 1 reveal

    def test_the_questions_carry_the_partner_list_as_a_partner_field(self):
        qs = {"331": {"type": "control_textbox"}, "444": {"type": "control_dropdown", "name": "clubPicker"}}
        self.assertEqual(sync.partner_fields(qs), {sync.PARTNER})
        self.assertIsNone(sync.partner_picker(qs))
        qs["600"] = {"type": "control_dropdown", "name": sync.PARTNER_PICKER_NAME}
        self.assertEqual(sync.partner_picker(qs), "600")
        self.assertEqual(sync.partner_fields(qs), {sync.PARTNER, "600"})
        qs["600"]["type"] = "control_textbox"                # recognised as a dropdown only
        self.assertIsNone(sync.partner_picker(qs))

    def test_partner_choices_are_the_partners_of_shared_names(self):
        clubs = {"10": "Alpha Club", "11": "Stars", "12": "STARS", "13": "Beta Club", "14": "Moon"}
        partners = {"11": "Partner Two", "12": "partner one", "10": "Partner Three"}
        self.assertEqual(sync.partner_choices(clubs, partners), ["partner one", "Partner Two"])
        # a club about to be created makes its name shared; the same partner twice is listed once
        pending = [("moon", "Partner Four"), ("Stars", " Partner  two ")]
        self.assertEqual(sync.partner_choices({"14": "Moon", **clubs}, {"14": "Partner One", **partners},
                                              pending),
                         ["Partner Four", "Partner One", "Partner Two"])
        self.assertEqual(sync.partner_choices({"10": "Alpha Club"}, {}), [])
        self.assertEqual(sync.partner_choices({"10": "A", "11": "a"}, {"10": "", "11": " "}), [])

    def test_rule_delta_counts_kept_new_and_dropped_rules(self):
        typed = self.rules(picker="500")
        wire = [dict(c, terms=json.dumps(c["terms"]), action=json.dumps(c["action"]), id="x",
                     index="99", priority="99") for c in typed]
        self.assertEqual(sync.rule_delta(wire, self.rules(picker="500")), (len(typed), 0, 0))
        listed = self.rules(picker="500", partner_field="600")
        self.assertEqual(sync.rule_delta(wire, listed), (len(typed) - 3, 4, 3))   # + the q331 copy
        self.assertEqual(sync.rule_delta([], listed), (0, len(listed), 0))
        self.assertEqual(sync.rule_delta([{"terms": "{broken"}], listed), (0, len(listed), 0))

    def test_generated_rules_mention_only_rosters_and_structural_fields(self):
        # so no other element - the links above Submit included - is ever
        # shown, hidden or computed by the sync's rewrite; with the partner
        # list (wf/partner-box) the list is the one field added, and with the
        # club guard (wf5/club-guard) the warning and Submit - only then
        structural = {sync.CLUB_NAME, sync.PARTNER, sync.YEAR, sync.CONTACT_IDS, sync.MODULE_ID,
                      sync.WEEK_ID, sync.YEAR_ID, *sync.MODULES.values(), *sync.WEEKS.values()}
        for picker in (None, "500"):
            for partner_field in (sync.PARTNER, "600"):
                for guard in (None, "700"):
                    mentioned = set()
                    for c in self.rules(picker=picker, partner_field=partner_field,
                                        picker_options=self.OPTIONS, guard=guard,
                                        submit="2" if guard else None):
                        for item in c["terms"] + c["action"]:
                            mentioned |= {str(item[k]) for k in ("field", "resultField") if k in item}
                            mentioned |= {o for o in str(item.get("operands", "")).split(",") if o}
                            mentioned |= set(re.findall(r"\{(\d+)\}", str(item.get("equation", ""))))
                    on = bool(picker and guard)
                    allowed = (structural | {partner_field} | set(self.CLUBS)
                               | ({picker} if picker else set()) | ({guard, "2"} if on else set()))
                    self.assertLessEqual(mentioned, allowed, mentioned - allowed)
                    self.assertIn(partner_field, mentioned)   # the shared names really are gated
                    self.assertEqual({guard, "2"} <= mentioned, on)

    # ---- one club per submission (docs/plans/2026-09-29-club-guard.md)
    OPTIONS = ["Alpha Club", "Beta Club", "Stars"]     # the picker's options, as main() writes them

    def guarded(self, **kw):
        return self.rules(picker="500", picker_options=self.OPTIONS, guard="700", submit="2", **kw)

    def test_without_the_guard_the_rules_are_todays(self):
        # the picker's options change nothing when their spelling is the rules' own
        today = self.rules(picker="500")
        self.assertEqual(sync._norm_rules(self.rules(picker="500", picker_options=self.OPTIONS)),
                         sync._norm_rules(today))
        # the guard needs all four: the picker, its options, the warning and Submit
        for kw in ({"picker": None, "picker_options": self.OPTIONS, "guard": "700", "submit": "2"},
                   {"picker": "500", "guard": "700", "submit": "2"},
                   {"picker": "500", "picker_options": self.OPTIONS, "submit": "2"},
                   {"picker": "500", "picker_options": self.OPTIONS, "guard": "700"}):
            conds = self.rules(**kw)
            self.assertFalse([c for c in conds if c["type"] == "require"], kw)
            self.assertFalse([a for c in conds for a in c["action"]
                              if a.get("visibility") != "Show" and "resultField" not in a], kw)
            self.assertFalse([x for c in conds for x in c["terms"] + c["action"]
                              if x.get("field") in ("2", "700")], kw)
        self.assertEqual(sync._norm_rules(self.rules(picker="500", guard="700", submit="2")),
                         sync._norm_rules(today))
        agg = [c for c in today if c["type"] == "calculation"
               and c["action"][0]["resultField"] == sync.CONTACT_IDS][0]
        self.assertEqual(agg["action"][0]["equation"], "{10}{11}{12}{13}")   # no separator today

    def test_the_guard_rules_are_two_rules_at_the_end(self):
        today = self.rules(picker="500")
        conds = self.guarded()
        self.assertEqual(len(conds), len(today) + 2)
        # every other rule is today's, at the same index, the Contact_IDs sum included
        self.assertEqual(sync._norm_rules(conds)[:-2], sync._norm_rules(today))
        show, req = conds[-2:]
        want_terms = [("500", "isFilled", "")] + [(sync.CLUB_NAME, "notEquals", o) for o in self.OPTIONS]
        for rule in (show, req):
            self.assertEqual(rule["link"], "All")
            self.assertEqual([(t["field"], t["operator"], t["value"]) for t in rule["terms"]], want_terms)
        self.assertEqual(show["type"], "field")
        self.assertEqual([(a["visibility"], a["field"]) for a in show["action"]],
                         [("Show", "700"), ("Hide", "2")])
        self.assertEqual(req["type"], "require")
        self.assertEqual([(a["visibility"], a["field"]) for a in req["action"]], [("Disable", "2")])
        ids = [t["id"] for c in conds for t in c["terms"]] + [a["id"] for c in conds for a in c["action"]]
        self.assertEqual(len(ids), len(set(ids)))                  # fresh ids, the two rules included
        self.assertEqual(len({c["id"] for c in conds}), len(conds))
        self.assertEqual([c["index"] for c in conds], [str(i) for i in range(len(conds))])
        self.assertEqual([c["priority"] for c in conds], [c["index"] for c in conds])
        # question 5 is still filled from the picker, exactly as before
        copy = [c for c in conds if c["type"] == "calculation"
                and c["action"][0]["resultField"] == sync.CLUB_NAME]
        self.assertEqual([(c["action"][0]["operands"], c["action"][0]["equation"]) for c in copy],
                         [("500", "{500}")])

    def test_the_require_rule_follows_its_constant(self):
        from unittest import mock
        with mock.patch.object(sync, "GUARD_DISABLES_SUBMIT", False):
            conds = self.guarded()
        self.assertEqual(len(conds), len(self.rules(picker="500")) + 1)
        self.assertEqual(conds[-1]["type"], "field")

    def test_the_guard_leaves_the_contact_ids_sum_as_it_is(self):
        # q18 is what Salesforce reads (Contact_IDs__c) and the e-mails print: a
        # literal between the operands would be written once per roster pair,
        # hidden rosters included, on every guarded submission. With the guard
        # only one roster is visible while Submit is, so nothing can fuse.
        def agg(conds):
            return [c["action"][0] for c in conds if c["type"] == "calculation"
                    and c["action"][0]["resultField"] == sync.CONTACT_IDS][0]
        unguarded = agg(self.rules(picker="500", picker_options=self.OPTIONS))
        self.assertEqual(agg(self.guarded()), unguarded)
        # the picker is an operand (glow.sync.CONTACT_IDS_PICKER_OPERAND), never in the equation
        self.assertEqual((unguarded["equation"], unguarded["operands"]), ("{10}{11}{12}{13}", "500,10,11,12,13"))
        self.assertTrue(unguarded["ignoreHiddenFields"])

    def test_club_terms_take_the_pickers_spelling(self):
        # two partners' "Stars" / "STARS": the picker lists the name once, and on a
        # multi-select "equals" is case-sensitive - every club term must be its option
        clubs = {"10": "Alpha Club", "11": "STARS", "12": "Stars", "13": "Beta Club"}
        sync._counter[0] = 0
        conds = sync.build_conditions(clubs, self.PARTNERS, self.MODULES, picker="500",
                                      picker_options=self.OPTIONS)
        club_terms = [t["value"] for c in conds if c["type"] == "field"
                      for t in c["terms"] if t["field"] == "500" and t["operator"] == "equals"]
        self.assertEqual(sorted(club_terms), ["Alpha Club", "Beta Club", "Stars", "Stars", "Stars"])
        self.assertLessEqual(set(club_terms), set(self.OPTIONS))
        # the typed box (no picker) keeps each roster's own spelling: "equals" ignores case there
        sync._counter[0] = 0
        typed = sync.build_conditions(clubs, self.PARTNERS, self.MODULES, picker_options=self.OPTIONS)
        values = sorted(t["value"] for c in typed if c["type"] == "field"
                        for t in c["terms"] if t["field"] == sync.CLUB_NAME)
        self.assertEqual(values, ["Alpha Club", "Beta Club", "STARS", "STARS", "Stars"])


class SameNameRule(unittest.TestCase):
    """glow.sync: which club names two partners share, and the one string such a
    club sends to question 5 (docs/plans/2026-09-30-same-name-clubs.md).
    Fictional names."""

    HEADER = "girl_id,partner,club,full_name,status,region\n"

    def pairs(self, rows):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "roster.csv")
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.HEADER)
                for n, (partner, club, status, region) in enumerate(rows):
                    name = "" if status == "blank" else f"Girl Number{n}"
                    status = "active" if status == "blank" else status
                    f.write(f'DEMOCLUB-SAMPLE-{n:03d},"{partner}","{club}",{name},{status},{region}\n')
            return glow_sync.roster_pairs(path)

    def test_the_separator_is_pinned(self):
        self.assertEqual(glow_sync.SF_NAME_SEP, " - ")       # ASCII space, hyphen-minus, space
        self.assertEqual(glow_sync.sf_club_name("Stars", "Partner One", True), "Stars - Partner One")
        self.assertEqual(glow_sync.sf_club_name("Stars", "Partner One", False), "Stars")
        # whitespace is collapsed, nothing else is touched: no case change, no accent folding
        self.assertEqual(glow_sync.sf_club_name(" STARS  Club ", "Partner   Óne (P1)", True),
                         "STARS Club - Partner Óne (P1)")
        with self.assertRaises(SystemExit) as refused:        # a long name needs its partner
            glow_sync.sf_club_name("Stars", "  ", True)
        self.assertIn("needs its partner", str(refused.exception))
        self.assertEqual(glow_sync.sf_club_name("Stars", "", False), "Stars")

    def test_roster_pairs_are_every_club_of_every_status_and_region(self):
        pairs = self.pairs([("Partner One", "Stars", "active", "Africa"),
                            ("Partner One", "Stars", "inactive", "Africa"),
                            ("Partner Two", " Stars ", "inactive", "Asia"),       # never active
                            ("Partner Two", "Beta  Club", "inactive", "Asia"),
                            ("Partner Two", "Beta Club", "active", "Asia"),       # …now active
                            ("partner two", "BETA CLUB", "active", "Asia"),       # the same club
                            ("", "Orphan", "active", "Asia"),                     # no partner: no form
                            ("Partner One", "", "active", "Africa"),
                            ("Partner Three", "Nameless", "blank", "U.S")])       # a row with no girl
        self.assertEqual(pairs, {("Partner One", "Stars"): True, ("Partner Two", "Stars"): False,
                                 ("Partner Two", "Beta Club"): True,
                                 ("Partner Three", "Nameless"): False})
        # …in read_roster_csv's own spelling for an active club (its first active row)
        self.assertIn(("Partner Two", "Beta Club"), pairs)
        with self.assertRaises(SystemExit):
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "not_a_roster.csv")
                with open(path, "w", encoding="utf-8") as f:
                    f.write("a,b\n1,2\n")
                glow_sync.roster_pairs(path)

    def test_a_name_is_shared_when_two_partners_have_it(self):
        pairs = {("Partner One", "Stars"): True, ("Partner Two", "STARS"): True,
                 ("Partner One", "Alpha Club"): True, ("partner one", "Alpha  Club"): True,
                 ("Partner Two", "Alpha Club - Juniors"): True,
                 ("Partner One", "Moon"): True, ("Partner Three", "Moon"): False}
        # compared by glow.text.key: case and spacing ignored; one partner written twice is
        # one partner; a club whose own name holds " - " is its own name
        self.assertEqual(glow_sync.shared_club_names(pairs), {"stars", "moon"})
        # the one-time switch goes by ACTIVE clubs; a NEW club is checked against every club
        self.assertEqual(glow_sync.shared_club_names(pairs, active_only=True), {"stars"})
        self.assertEqual(glow_sync.club_partners(pairs)["moon"],
                         {"partner one": "Partner One", "partner three": "Partner Three"})
        self.assertEqual(glow_sync.club_partners(pairs)["alpha club"], {"partner one": "Partner One"})
        self.assertEqual(glow_sync.shared_club_names({}), set())

    def test_the_partner_is_read_back_by_stripping_the_clubs_own_text(self):
        partners = {"partner one": "Partner One", "partner two": "Partner Two"}
        read = glow_sync.long_name_partner
        self.assertEqual(read("Stars - Partner One", "Stars", partners), "Partner One")
        self.assertEqual(read("stars  -  PARTNER two", "STARS", partners), "Partner Two")
        self.assertIsNone(read("Stars", "Stars", partners))                     # the plain name
        self.assertIsNone(read("Stars - Partner Nine", "Stars", partners))      # not the Roster's
        self.assertIsNone(read("Stars - Partner One", "Stars", None))
        # never split on the separator: "Alpha Club - Juniors" renamed to "Alpha Club" still tests
        # its old name until the sync runs, and "Juniors" is no partner
        self.assertIsNone(read("Alpha Club - Juniors", "Alpha Club", {"partner one": "Partner One"}))
        self.assertEqual(read("Alpha Club - Juniors - Partner One", "Alpha Club - Juniors", partners),
                         "Partner One")
        # nor is the partner's own " - " split: only the club's text is stripped
        self.assertEqual(read("Stars - Partner One - East", "Stars",
                              {"partner one - east": "Partner One - East"}), "Partner One - East")
        self.assertIsNone(read("Starship - Partner One", "Stars", partners))

    def test_two_clubs_sending_one_name_are_a_clash(self):
        clash = glow_sync.sf_name_clashes
        self.assertEqual(clash([("Stars", "a"), ("Alpha Club", "b"), ("Beta Club", "c")]), [])
        # compared as Salesforce matches an Account: case ignored
        self.assertEqual(clash([("Stars", ("Africa", "11")), ("STARS", ("Asia", "20")),
                                ("Alpha Club", ("Asia", "21"))]),
                         [("Stars", [("Africa", "11"), ("Asia", "20")])])
        # a club named like another club's long name; the same club seen twice is one club
        self.assertEqual(clash([("Stars - Partner One", "x"), ("stars - partner one", "y"),
                                ("Stars - Partner One", "x")]),
                         [("Stars - Partner One", ["x", "y"])])


class FakeForm:
    """sync_attendance_form.Jotform stand-in: one form held in memory. Reads
    answer from it; writes are recorded (label + payload) and, with apply, a
    question create answers `created` (the new question's id, or {}; a list
    answers one create each, in order)."""

    def __init__(self, questions, conditions, apply=False, created=None):
        self.questions, self.conditions, self.apply = questions, conditions, apply
        self.created = {"qid": 600} if created is None else created
        self.calls, self.writes = [], []

    def get(self, path):
        if path == "/questions":
            return json.loads(json.dumps(self.questions))
        if path == "/properties":
            return {"conditions": json.loads(json.dumps(self.conditions))}
        return {"count": "0"}

    def _write(self, method, path, payload, label):
        self.calls.append(label)
        self.writes.append((method, path, payload))
        if not self.apply:
            return None
        if (method, path) != ("POST", "/questions"):
            return {}
        return self.created.pop(0) if isinstance(self.created, list) else self.created

    def post_form(self, path, data, label):
        return self._write("POST", path, data, label)

    def put_json(self, path, payload, label):
        return self._write("PUT", path, payload, label)

    def delete(self, path, label):
        return self._write("DELETE", path, None, label)


class SameNameFlow(unittest.TestCase):
    """sync_attendance_form.main() on a fake Africa form where two partners each
    have a club named "Stars": before the one-time --same-name-switch (the typed
    Partner box tells the two rosters apart), during it, and after (each has its
    own Club picker entry, "Stars - <partner>", which is what question 5 sends).
    docs/plans/2026-09-30-same-name-clubs.md. Fictional names."""

    ROSTER = {("Partner One", "Alpha Club"): ["Jane Doe", "Mary Roe"],
              ("Partner One", "Stars"): ["Ann Poe", "Kay Loe"],
              ("Partner Two", "Stars"): ["Sue Moe", "Liz Noe"],
              ("Partner Two", "Beta Club"): ["Eve Hoe", "Ida Toe"]}
    QIDS = {("Partner One", "Alpha Club"): "10", ("Partner One", "Stars"): "11",
            ("Partner Two", "Stars"): "12", ("Partner Two", "Beta Club"): "13"}
    MODULES = {"1": "Core 1", "2": "Core 2|Elective - Healthy GLOW", "3": "Core 3"}
    LONG = ["Alpha Club", "Beta Club", "Stars - Partner One", "Stars - Partner Two"]
    CHANGE = "'Stars' (q{qid}): Club Name (question 5, what Salesforce reads) changes from 'Stars' to '{new}'"
    HIDE = "HIDE partner textbox (q331: no rule shows it; clubs that share a name have their own Club picker entry)"

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        del sync.WARNINGS[:]

    def tearDown(self):
        self.tmp.cleanup()
        del sync.WARNINGS[:]

    def texts(self, roster, switched=False, long=()):
        """({qid: the text its rule tests}, {qid: partner} for the rosters the
        typed Partner box still tells apart). switched: every club whose name
        another roster on the form shares has its long entry; long: the clubs
        ((partner, club)) that have it whatever the form holds."""
        from collections import Counter
        names = Counter(club.lower() for _, club in roster)
        option_of, plain = {}, Counter()
        for partner, club in roster:
            qid = self.QIDS[(partner, club)]
            if (partner, club) in long or (switched and names[club.lower()] > 1):
                option_of[qid] = f"{club} - {partner}"
            else:
                option_of[qid] = club
                plain[club.lower()] += 1
        partner_of = {self.QIDS[(p, c)]: p for p, c in roster
                      if option_of[self.QIDS[(p, c)]] == c and plain[c.lower()] > 1}
        return option_of, partner_of

    def form(self, roster=None, switched=False, long=(), rules_switched=None, picker=True,
             box_hidden=None, partner_list=None):
        """(questions, wire conditions) of a form in step with `roster`.
        switched / long: see texts(); rules_switched: the state the RULES are in
        when it differs from the picker's (a restored backup, a half apply);
        picker=False: mentors type the club name (rules on question 5);
        box_hidden: q331's hidden flag (default: hidden once no rule shows it);
        partner_list: the options of a retired partner list left on the form (q600)."""
        roster = self.ROSTER if roster is None else roster
        # the module chain as the live forms carry it: one required single-select per step
        # (form_status.audit_module_shape pins it; docs/plans/2026-10-06-module-selection.md)
        qs = {"5": {"type": "control_textbox", "text": "Club Name", "order": "4", "hidden": "Yes"},
              "331": {"type": "control_textbox", "text": "Partner", "order": "7", "name": "partner"},
              "94": {"type": "control_dropdown", "text": "GLOW Club Year", "options": "1|2|3", "order": "9",
                     "required": "Yes"}}
        for n, (year, mq) in enumerate(sync.MODULES.items()):
            # in step: the calcValues the sync writes (glow.sync.MODULE_CALC_VALUES)
            qs[mq] = {"type": "control_dropdown", "text": "Module", "options": self.MODULES[year],
                      "order": str(10 + n), "required": "Yes",
                      "calcValues": glow_sync.module_calc_values(self.MODULES[year].split("|"))}
        for n, wq in enumerate(sync.WEEKS.values()):
            qs[wq] = {"type": "control_dropdown", "text": "Session", "order": str(13 + n), "required": "Yes"}
        for q in (sync.CONTACT_IDS, sync.MODULE_ID, sync.WEEK_ID, sync.YEAR_ID):
            qs[q] = {"type": "control_textbox", "text": "bridge", "order": "30"}
        for (partner, club), names in roster.items():
            qid = self.QIDS[(partner, club)]
            # in step: the required flag the sync writes (glow.sync.ROSTERS_REQUIRED)
            qs[qid] = {"type": "control_checkbox", "text": club, "options": "|".join(names),
                       "order": str(40 + int(qid)), "hidden": "Yes", "required": glow_sync.roster_required()}
        option_of, partner_of = self.texts(roster, switched, long)
        if picker:
            qs["500"] = dict(sync.PICKER_PROPS, type="control_dropdown", name=sync.PICKER_NAME, order="3",
                             options="|".join(sorted(set(option_of.values()), key=str.lower)))
        else:
            qs["5"]["hidden"] = "No"
        if partner_list is not None:
            qs["600"] = dict(sync.PARTNER_PICKER_PROPS, type="control_dropdown",
                             name=sync.PARTNER_PICKER_NAME, order="7", options=partner_list)
        if picker and not partner_of:
            qs["331"]["hidden"] = "Yes"
        if rules_switched is not None:
            option_of, partner_of = self.texts(roster, rules_switched, long)
        modules = {y: o.split("|") for y, o in self.MODULES.items()}
        conds = sync.build_conditions(option_of, partner_of, modules, picker="500" if picker else None)
        if box_hidden is not None:
            qs["331"]["hidden"] = box_hidden
        wire = [dict(c, terms=json.dumps(c["terms"]), action=json.dumps(c["action"])) for c in conds]
        return qs, wire

    def run_sync(self, fake, *extra, roster=None, regions=None, inactive=None, region="Africa"):
        """(exit code, stdout) of main() on `fake` with a Roster export holding
        `roster` (active; region Africa unless `regions` says otherwise for a
        club) and `inactive` ({(partner, club): [names]}, rows of another status)."""
        import contextlib
        import csv
        import io
        from unittest import mock
        roster = self.ROSTER if roster is None else roster
        path = os.path.join(self.tmp.name, "roster.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["girl_id", "partner", "club", "full_name", "status", "region"])
            for status, clubs in (("active", roster), ("inactive", inactive or {})):
                for (partner, club), names in clubs.items():
                    for n, name in enumerate(names):
                        w.writerow([f"DEMOCLUB-SAMPLE-{n:03d}", partner, club, name, status,
                                    (regions or {}).get((partner, club), "Africa")])
        argv = ["sync_attendance_form.py", path, "--roster", "--region", region, "--form", "999",
                *extra]
        out = io.StringIO()
        with mock.patch.object(sync, "Jotform", lambda key, form, apply_changes: fake), \
                mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test"}), \
                mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(out):
            try:
                sync.main()
                code = 0
            except SystemExit as e:
                code = e.code
        return code, out.getvalue()

    def summary(self, fake, *extra, **kw):
        path = os.path.join(self.tmp.name, "plan.json")
        code, out = self.run_sync(fake, *extra, "--summary-json", path, **kw)
        self.assertEqual(code, 0, code)
        with open(path, encoding="utf-8") as f:
            return json.load(f), out

    @staticmethod
    def rules(payload):
        """[(rule, terms, actions)] of a conditions write."""
        return [(c, json.loads(c["terms"]), json.loads(c["action"]))
                for c in payload["properties"]["conditions"]]

    def shows(self, payload, qid):
        """The terms of the one rule that shows roster `qid`: [(field, operator, value)]."""
        found = [[(t["field"], t["operator"], t["value"]) for t in terms]
                 for _, terms, actions in self.rules(payload)
                 if any(a.get("visibility") == "Show" and a.get("field") == qid for a in actions)]
        self.assertEqual(len(found), 1, qid)
        return found[0]

    # ---- before the switch: nothing changes on its own
    def test_without_the_flag_a_form_told_apart_by_the_partner_box_is_left_as_it_is(self):
        fake = FakeForm(*self.form())
        summary, out = self.summary(fake)
        self.assertEqual(fake.calls, [])                      # no rule, option or q331 write
        self.assertIn("nothing to do", out)
        self.assertIn("(conditions unchanged - skipping the rewrite)", out)
        self.assertIn("Partner box: 2 rosters share a Club picker entry", out)
        self.assertNotIn("Same-name clubs:", out)
        self.assertEqual(sync.WARNINGS, [])
        self.assertEqual((summary["sf_name_changes"], summary["same_name_refused"]), ([], []))
        self.assertEqual([(n["qid"], n["partner"], n["club"], n["value"]) for n in summary["sf_names"]],
                         [("10", "Partner One", "Alpha Club", "Alpha Club"),
                          ("11", "Partner One", "Stars", "Stars"), ("12", "Partner Two", "Stars", "Stars"),
                          ("13", "Partner Two", "Beta Club", "Beta Club")])
        self.assertIsNone(summary["partner_picker"])

    def test_the_partner_is_read_back_from_the_rules_on_the_typed_box(self):
        # Partner Two's Stars gets an all-new roster: only the partner in the live
        # rules ties it to its question - roster overlap cannot
        sheet = {**self.ROSTER, ("Partner Two", "Stars"): ["Uma Umberlash", "Valeria Wrenfoldy"]}
        fake = FakeForm(*self.form())
        code, _ = self.run_sync(fake, roster=sheet)
        self.assertEqual(code, 0)
        self.assertEqual(fake.calls[0], "UPDATE roster 'Stars' (q12, 2 girls)")
        self.assertFalse([c for c in fake.calls if c.startswith("CREATE roster")])
        self.assertEqual(sync.WARNINGS, [])

    def test_a_form_with_no_shared_name_only_gets_the_partner_box_hidden(self):
        # Asia, Latin America and U.S today: no rule shows q331 and it is not hidden,
        # so every mentor sees an optional box that does nothing (Ryan, 2026-09-30: hide it)
        roster = {k: v for k, v in self.ROSTER.items() if k != ("Partner Two", "Stars")}
        qs, wire = self.form(roster=roster, box_hidden="No")
        fake = FakeForm(qs, wire, apply=True)
        code, out = self.run_sync(fake, "--apply", roster=roster)
        self.assertEqual((code, fake.calls), (0, [self.HIDE]))
        self.assertEqual(fake.writes, [("POST", "/question/331",
                                        {"question[hidden]": "Yes", "question[required]": "No"})])
        self.assertIn("(conditions unchanged - skipping the rewrite)", out)
        self.assertEqual(sync.WARNINGS, [])
        # the runner does not count it as a change (it rides along with the next roster change),
        # and its label is not mistaken for a partner-list write
        self.assertEqual(auto_sync.changes(auto_sync.parse_plan("\nDRY RUN:\n  - " + self.HIDE + "\n")), 0)
        self.assertFalse(auto_sync.PARTNER_PICKER_RX.match("  - " + self.HIDE))
        # already hidden: nothing at all
        fake = FakeForm(*self.form(roster=roster))
        self.assertEqual((self.run_sync(fake, roster=roster)[0], fake.calls), (0, []))

    # ---- the one-time switch
    def test_the_switch_dry_run_lists_each_change_and_plans_picker_rules_then_the_box(self):
        qs, wire = self.form()
        fake = FakeForm(qs, wire)
        summary, out = self.summary(fake, "--same-name-switch")
        self.assertEqual(fake.calls, ["UPDATE club picker (4 clubs: options)",
                                      f"REPLACE conditions ({len(wire) - 1} rules)", self.HIDE])
        self.assertEqual(fake.writes[0][2], {"question[options]": "|".join(self.LONG)})
        self.assertEqual(sync.WARNINGS,
                         ["  ! " + self.CHANGE.format(qid="11", new="Stars - Partner One"),
                          "  ! " + self.CHANGE.format(qid="12", new="Stars - Partner Two")])
        for w in sync.WARNINGS:
            self.assertIn(auto_sync.SF_NAME_CHANGE, w)
        self.assertIn("Same-name clubs: 2 roster(s) on this form send '<club> - <partner>'", out)
        self.assertNotIn("Partner box:", out)
        # each Stars rule is one term on the picker; nothing tests or shows the Partner box
        self.assertEqual(self.shows(fake.writes[1][2], "11"), [("500", "equals", "Stars - Partner One")])
        self.assertEqual(self.shows(fake.writes[1][2], "12"), [("500", "equals", "Stars - Partner Two")])
        self.assertEqual(self.shows(fake.writes[1][2], "10"), [("500", "equals", "Alpha Club")])
        for c, terms, actions in self.rules(fake.writes[1][2]):
            self.assertFalse([x for x in terms + actions if x.get("field") == sync.PARTNER], c)
        self.assertIn(f"conditions: {len(wire) - 3} kept, 2 new, 3 dropped", out)   # 2 rosters, - the reveal
        # question 5 is still the picker's copy, so it receives the long name exactly
        copies = [a for _, _, actions in self.rules(fake.writes[1][2]) for a in actions
                  if a.get("resultField") == sync.CLUB_NAME]
        self.assertEqual([(a["operands"], a["equation"]) for a in copies], [("500", "{500}")])
        self.assertEqual(summary["sf_name_changes"],
                         [{"qid": "11", "club": "Stars", "old": "Stars", "new": "Stars - Partner One",
                           "switch": True},
                          {"qid": "12", "club": "Stars", "old": "Stars", "new": "Stars - Partner Two",
                           "switch": True}])
        self.assertEqual([n["value"] for n in summary["sf_names"]],
                         ["Alpha Club", "Stars - Partner One", "Stars - Partner Two", "Beta Club"])
        # the runner's patterns still read the plan
        self.assertTrue(auto_sync.PICKER_RX.match("  - " + fake.calls[0]))
        self.assertTrue(auto_sync.REPLACE_RX.match("  - " + fake.calls[1]))

    def test_the_switch_sends_the_names_apps_script_prints_for_salesforce(self):
        # the whole path, both languages, one Roster: what the switched form sends to question 5
        # for each club (--summary-json sf_names) is the account name the Monday e-mail prints
        # for it (RosterOps.gs sharedClubNames_ / sfClubName_, run in Node)
        rows = [{"partner": partner, "club": club, "full_name": name, "status": "active", "region": "Africa"}
                for (partner, club), names in self.ROSTER.items() for name in names]
        gs = apps_script_same_name(rows, pairs=list(self.ROSTER))
        if gs is None:
            self.skipTest("node is not installed: the Apps Script side cannot run")
        summary, _ = self.summary(FakeForm(*self.form()), "--same-name-switch")
        self.assertEqual(gs["shared"], ["stars"])
        self.assertEqual({(n["partner"], n["club"]): n["value"] for n in summary["sf_names"]},
                         dict(zip(self.ROSTER, gs["names"])))
        self.assertEqual(sorted(gs["names"], key=str.lower), self.LONG)

    def test_the_switch_apply_needs_no_other_flag_and_hides_the_box_last(self):
        fake = FakeForm(*self.form(), apply=True)
        code, _ = self.run_sync(fake, "--same-name-switch", "--apply")
        self.assertEqual(code, 0)
        self.assertEqual([(m, p) for m, p, _ in fake.writes],
                         [("POST", "/question/500"), ("PUT", "/properties"), ("POST", "/question/331")])
        self.assertEqual(fake.writes[2][2], {"question[hidden]": "Yes", "question[required]": "No"})
        # …and what it wrote is the switched form: the next run, with or without the flag, is a no-op
        qs, wire = self.form(switched=True)
        self.assertEqual(sync._norm_rules(fake.writes[1][2]["properties"]["conditions"]),
                         sync._norm_rules(wire))
        self.assertEqual(fake.writes[0][2]["question[options]"], qs["500"]["options"])

    def test_the_switched_form_needs_nothing_and_stays_switched(self):
        for extra in ((), ("--same-name-switch",)):
            del sync.WARNINGS[:]
            fake = FakeForm(*self.form(switched=True))
            summary, out = self.summary(fake, *extra)
            self.assertEqual(fake.calls, [], extra)
            self.assertEqual(sync.WARNINGS, [], extra)
            self.assertIn("Same-name clubs: 2 roster(s)", out)
            self.assertEqual("nothing to switch" in out, bool(extra))
            self.assertEqual(summary["sf_name_changes"], [])
            self.assertEqual([n["partner"] for n in summary["sf_names"]],
                             ["Partner One", "Partner One", "Partner Two", "Partner Two"])

    def test_on_the_switched_form_the_partner_is_read_back_from_the_long_name(self):
        # a wholly replaced roster still updates its own question: without the read-back it
        # would fall to roster overlap, find none, and be taken for a new club
        sheet = {**self.ROSTER, ("Partner Two", "Stars"): ["Uma Umberlash", "Valeria Wrenfoldy"]}
        fake = FakeForm(*self.form(switched=True))
        code, _ = self.run_sync(fake, roster=sheet)
        self.assertEqual(code, 0)
        self.assertEqual(fake.calls, ["UPDATE roster 'Stars' (q12, 2 girls)",
                                      f"REPLACE conditions ({len(self.form(switched=True)[1])} rules)"])
        self.assertEqual(sync.WARNINGS, [])

    def test_a_namesake_in_another_region_counts(self):
        # Salesforce is one org: Partner Two's Stars lives on the Asia form, and the
        # Africa form's only Stars still gets its long name - with no partner term
        roster = dict(self.ROSTER)
        regions = {("Partner Two", "Stars"): "Asia", ("Partner Two", "Beta Club"): "Asia"}
        on_africa = {k: v for k, v in roster.items() if k not in regions}
        fake = FakeForm(*self.form(roster=on_africa))
        code, _ = self.run_sync(fake, roster=roster, regions=regions)
        self.assertEqual((code, fake.calls, sync.WARNINGS), (0, [], []))       # sticky: plain it stays
        fake = FakeForm(*self.form(roster=on_africa))
        code, _ = self.run_sync(fake, "--same-name-switch", roster=roster, regions=regions)
        self.assertEqual(code, 0)
        self.assertEqual(sync.WARNINGS, ["  ! " + self.CHANGE.format(qid="11", new="Stars - Partner One")])
        self.assertEqual(fake.writes[0][2], {"question[options]": "Alpha Club|Stars - Partner One"})
        self.assertEqual(self.shows(fake.writes[1][2], "11"), [("500", "equals", "Stars - Partner One")])
        # switched, the next run reads the partner back and needs nothing
        del sync.WARNINGS[:]
        fake = FakeForm(*self.form(roster=on_africa, long=[("Partner One", "Stars")]))
        code, _ = self.run_sync(fake, roster=roster, regions=regions)
        self.assertEqual((code, fake.calls, sync.WARNINGS), (0, [], []))

    def test_only_active_clubs_count_for_the_switch(self):
        # Partner Two's Stars was retired before the switch: Partner One's is the one Stars
        # left and keeps its plain name (the sheet's two retired duplicates, 2026-09-30)
        on_form = {k: v for k, v in self.ROSTER.items() if k != ("Partner Two", "Stars")}
        fake = FakeForm(*self.form(roster=on_form))
        code, out = self.run_sync(fake, "--same-name-switch", roster=on_form,
                                  inactive={("Partner Two", "Stars"): ["Sue Moe", "Liz Noe"]})
        self.assertEqual((code, fake.calls, sync.WARNINGS), (0, [], []))
        self.assertIn("--same-name-switch: nothing to switch", out)

    def test_the_switch_refuses_to_leave_a_retired_namesake_on_the_plain_entry(self):
        # three Stars on the form, told apart by the Partner box; Partner Three's was retired
        # and its question is still there. Switched, q11 and q12 get their long entries and
        # q20 - not in the export - would keep "Stars", now alone on it: the familiar name,
        # first in the list, showing a retired club's girls and sending plain "Stars"
        three = {**self.ROSTER, ("Partner Three", "Stars"): ["Uma Umberlash", "Valeria Wrenfoldy"]}
        self.QIDS = {**self.QIDS, ("Partner Three", "Stars"): "20"}
        gone = {("Partner Three", "Stars"): three[("Partner Three", "Stars")]}
        for extra in (("--same-name-switch",), ("--same-name-switch", "--apply")):   # the dry run too
            fake = FakeForm(*self.form(roster=three), apply="--apply" in extra)
            code, _ = self.run_sync(fake, *extra, inactive=gone)
            self.assertIn("q20 would keep the plain Club picker entry 'Stars' beside the long ones", str(code))
            self.assertIn("Delete the leftover question in the builder first", str(code))
            self.assertEqual(fake.calls, [], extra)
        # without the flag nothing is switched, so nothing is refused: the form stays as it is
        del sync.WARNINGS[:]
        fake = FakeForm(*self.form(roster=three))
        code, out = self.run_sync(fake, inactive=gone)
        self.assertEqual((code, fake.calls), (0, []))
        self.assertIn("Partner box: 3 rosters share a Club picker entry", out)
        # …also on a form that is already that way (switched by hand, the leftover on its
        # plain entry): the refusal is the switch's alone, never the unattended runner's
        del sync.WARNINGS[:]
        fake = FakeForm(*self.form(roster=three, long=[("Partner One", "Stars"), ("Partner Two", "Stars")]))
        code, _ = self.run_sync(fake, inactive=gone)
        self.assertEqual((code, fake.calls), (0, []))
        # all three active: all three go long
        del sync.WARNINGS[:]
        fake = FakeForm(*self.form(roster=three))
        summary, _ = self.summary(fake, "--same-name-switch", roster=three)
        self.assertEqual(sorted((c["qid"], c["new"], c["switch"]) for c in summary["sf_name_changes"]),
                         [("11", "Stars - Partner One", True), ("12", "Stars - Partner Two", True),
                          ("20", "Stars - Partner Three", True)])

    def test_a_refused_newcomer_does_not_make_an_existing_club_long(self):
        # Partner Three's new Alpha Club was refused (Partner One has that name) and sits,
        # active, in the Roster until someone renames it. It is on no form: a later
        # --same-name-switch must not count it and turn Partner One's one-of-a-kind Alpha
        # Club into "Alpha Club - Partner One" - an existing club's name never changes
        sheet = {**self.ROSTER, ("Partner Three", "Alpha Club"): ["Uma Umberlash", "Valeria Wrenfoldy"]}
        refused = ("  ! new club 'Alpha Club' (Partner Three) has the name of Partner One's club - "
                   "not added: give it a different name")
        fake = FakeForm(*self.form(switched=True))
        summary, out = self.summary(fake, "--same-name-switch", roster=sheet)
        self.assertEqual((fake.calls, summary["sf_name_changes"], sync.WARNINGS), ([], [], [refused]))
        self.assertIn("--same-name-switch: nothing to switch", out)
        # on a form not switched yet: the two Stars and nothing else
        del sync.WARNINGS[:]
        fake = FakeForm(*self.form())
        summary, _ = self.summary(fake, "--same-name-switch", roster=sheet)
        self.assertEqual([(c["qid"], c["new"]) for c in summary["sf_name_changes"]],
                         [("11", "Stars - Partner One"), ("12", "Stars - Partner Two")])
        self.assertEqual(fake.writes[0][2], {"question[options]": "|".join(self.LONG)})
        self.assertEqual(sync.WARNINGS[0], refused)

    # ---- after the switch: sticky
    def test_a_namesake_going_inactive_changes_nothing(self):
        gone = {("Partner Two", "Stars"): self.ROSTER[("Partner Two", "Stars")]}
        sheet = {k: v for k, v in self.ROSTER.items() if k not in gone}
        for switched in (True, False):
            del sync.WARNINGS[:]
            fake = FakeForm(*self.form(switched=switched))
            summary, _ = self.summary(fake, roster=sheet, inactive=gone)
            self.assertEqual(fake.calls, [], switched)               # both rosters keep what they send
            self.assertEqual(summary["sf_name_changes"], [], switched)
            self.assertEqual(len(sync.WARNINGS), 1, sync.WARNINGS)   # q12: on the form, not in the export
            self.assertIn("'Stars' (q12)", sync.WARNINGS[0])
            self.assertEqual([n["value"] for n in summary["sf_names"]][1:3],
                             ["Stars - Partner One", "Stars - Partner Two"] if switched else ["Stars", "Stars"])

    def test_the_picker_says_what_a_club_sends_when_the_rules_are_older(self):
        # a conditions backup from before the switch restored over the switched picker (or an
        # apply that stopped between the picker and the rules): the rules test "Stars" with
        # the Partner box, the picker lists the long names. The run rebuilds the rules on
        # the long names; it never takes the picker back to "Stars", and nothing changes
        # for Salesforce
        qs, wire = self.form(switched=True, rules_switched=False)
        fake = FakeForm(qs, wire)
        summary, out = self.summary(fake)
        self.assertEqual(fake.calls, [f"REPLACE conditions ({len(wire) - 1} rules)"])
        self.assertEqual(sync._norm_rules(fake.writes[0][2]["properties"]["conditions"]),
                         sync._norm_rules(self.form(switched=True)[1]))
        self.assertEqual(summary["sf_name_changes"], [])
        # …but it says so, per roster: until the rules are rewritten those two rosters never
        # show (and the club guard blocks their mentors), and the conditions rewrite alone is
        # no change to the runner - which must not read this form as in-sync
        self.assertEqual(sync.WARNINGS, [
            f"  ! 'Stars' (q{q}): its rule tests 'Stars', which the Club picker does not list (it "
            f"lists 'Stars - {p}') - the rules and the picker are out of step (a restored backup, "
            "an apply that stopped half-way?): until an --apply rewrites the rules this roster does "
            "not show" for q, p in (("11", "Partner One"), ("12", "Partner Two"))])
        for w in sync.WARNINGS:
            self.assertIn(auto_sync.RULES_OLDER, w)
        self.assertNotIn(auto_sync.SF_NAME_CHANGE, " ".join(sync.WARNINGS))
        plan = auto_sync.plan_from_summary(summary)
        self.assertEqual((auto_sync.changes(plan), len(auto_sync.stale_rules(plan))), (0, 2))
        # the hand apply writes the rules, and the next run has nothing to say
        fake = FakeForm(qs, wire, apply=True)
        code, _ = self.run_sync(fake, "--apply")
        self.assertEqual((code, [(m, p) for m, p, _ in fake.writes]), (0, [("PUT", "/properties")]))
        del sync.WARNINGS[:]
        fake = FakeForm(*self.form(switched=True))
        self.assertEqual((self.run_sync(fake)[0], fake.calls, sync.WARNINGS), (0, [], []))

    def test_a_roster_left_without_its_rule_by_a_failed_apply_is_finished_not_refused(self):
        # an apply that created the roster (and perhaps updated the picker) and then failed on
        # the rules write: the re-run - the runner's own retry too - must complete it. A roster
        # with no rule has nothing it "sends today", so this is no question-5 change
        sheet = {**self.ROSTER, ("Partner One", "Gamma Club"): ["Amara Pellucidor"]}
        self.QIDS = {**self.QIDS, ("Partner One", "Gamma Club"): "20"}       # 14 is a module dropdown
        for picker_written in (True, False):
            del sync.WARNINGS[:]
            qs, _ = self.form(roster=sheet, switched=True)
            _, wire = self.form(switched=True)                 # the rules from before the new club
            if not picker_written:
                qs["500"]["options"] = "|".join(self.LONG)
            fake = FakeForm(qs, wire, apply=True)
            code, _ = self.run_sync(fake, "--apply", roster=sheet)
            self.assertEqual(code, 0, code)
            self.assertEqual(sync.WARNINGS, [])
            self.assertEqual([(m, p) for m, p, _ in fake.writes],
                             ([] if picker_written else [("POST", "/question/500")]) + [("PUT", "/properties")])
            self.assertEqual(self.shows(fake.writes[-1][2], "20"), [("500", "equals", "Gamma Club")])

    def test_a_roster_created_by_an_apply_gets_its_rule_in_the_same_run(self):
        # the commonest unattended write: a new club. Its question's id is only known once
        # Jotform answers the create, and the same run must give it its picker entry, its
        # show rule, its Contact_IDs operand and its line in sf_names
        sheet = {**self.ROSTER, ("Partner Three", "Gamma Club"): ["Amara Pellucidor"]}
        for switched in (True, False):
            del sync.WARNINGS[:]
            fake = FakeForm(*self.form(switched=switched), apply=True, created={"qid": 600})
            summary, _ = self.summary(fake, "--apply", roster=sheet)
            self.assertEqual([(m, p) for m, p, _ in fake.writes],
                             [("POST", "/questions"), ("POST", "/question/500"), ("PUT", "/properties")])
            self.assertIn("Gamma Club", fake.writes[1][2]["question[options]"].split("|"))
            self.assertEqual(self.shows(fake.writes[-1][2], "600"), [("500", "equals", "Gamma Club")])
            agg, = [a for _, _, actions in self.rules(fake.writes[-1][2]) for a in actions
                    if a.get("resultField") == sync.CONTACT_IDS]
            self.assertEqual((agg["equation"], agg["operands"]), ("{10}{11}{12}{13}{600}", "500,10,11,12,13,600"))
            self.assertEqual(json.loads(fake.writes[-1][2]["properties"]["conditions"][0]["action"])[0]
                             ["resultField"], sync.CONTACT_IDS)             # rule 0, the new roster in it
            self.assertEqual(fake.writes[0][2]["question[required]"], "Yes")   # created required
            self.assertEqual(summary["sf_names"][-1], {"qid": "600", "partner": "Partner Three",
                                                       "club": "Gamma Club", "value": "Gamma Club"})

    # ---- a new club may not take a name in use
    def test_a_new_club_with_a_name_in_use_is_not_created_and_the_run_goes_on(self):
        sheet = {**self.ROSTER, ("Partner Three", "Stars"): ["Uma Umberlash"],
                 ("Partner Three", "ALPHA  club"): ["Valeria Wrenfoldy"],
                 ("Partner Three", "Gamma Club"): ["Amara Pellucidor"],
                 ("Partner One", "Alpha Club"): ["Jane Doe", "Mary Roe", "Zoe Quillfeather"]}
        for switched in (True, False):
            del sync.WARNINGS[:]
            qs, wire = self.form(switched=switched)
            fake = FakeForm(qs, wire)
            summary, _ = self.summary(fake, roster=sheet)
            # the two are refused; the unrelated new club and the roster update still go through
            self.assertEqual(fake.calls[:2], ["CREATE roster 'Gamma Club' (1 girls)",
                                              "UPDATE roster 'Alpha Club' (q10, 3 girls)"], switched)
            self.assertEqual([c for c in fake.calls if "CREATE roster" in c], fake.calls[:1])
            self.assertEqual(sync.WARNINGS, [
                "  ! new club 'ALPHA club' (Partner Three) has the name of Partner One's club - "
                "not added: give it a different name",
                "  ! new club 'Stars' (Partner Three) has the name of Partner One's club and "
                "Partner Two's club - not added: give it a different name"])
            for w in sync.WARNINGS:
                self.assertIn(auto_sync.SAME_NAME_REFUSED, w)
            self.assertEqual(summary["same_name_refused"],
                             [{"club": "ALPHA club", "partner": "Partner Three", "others": ["Partner One"]},
                              {"club": "Stars", "partner": "Partner Three",
                               "others": ["Partner One", "Partner Two"]}])
            self.assertEqual([c["club"] for c in summary["creates"]], ["Gamma Club"])
            # both existing clubs of that name are untouched: same entries, same question 5
            self.assertEqual(summary["sf_name_changes"], [])
            options = fake.writes[2][2]["question[options]"].split("|")
            self.assertEqual(options, sorted(qs["500"]["options"].split("|") + ["Gamma Club"], key=str.lower))
            self.assertEqual([n["value"] for n in summary["sf_names"]][-1], "Gamma Club")
            self.assertIsNone(summary["sf_names"][-1]["qid"])          # a dry run: not created yet

    def test_the_name_may_be_in_use_in_another_region_or_by_a_retired_club(self):
        base = {k: v for k, v in self.ROSTER.items() if k[1] != "Stars"}
        for where in ({"regions": {("Partner Two", "Stars"): "Asia"},
                       "roster": {**base, ("Partner One", "Stars"): ["Ann Poe"],
                                  ("Partner Two", "Stars"): ["Sue Moe"]}},
                      {"inactive": {("Partner Two", "Stars"): ["Sue Moe"]},
                       "roster": {**base, ("Partner One", "Stars"): ["Ann Poe"]}}):
            del sync.WARNINGS[:]
            fake = FakeForm(*self.form(roster=base))          # no Stars on this form yet
            code, _ = self.run_sync(fake, **where)
            self.assertEqual(code, 0)
            self.assertEqual(fake.calls, [], where)
            self.assertEqual(sync.WARNINGS, ["  ! new club 'Stars' (Partner One) has the name of Partner "
                                             "Two's club - not added: give it a different name"])
        # the same partner bringing its own retired club back is no clash
        fake = FakeForm(*self.form(roster=base))
        del sync.WARNINGS[:]
        code, _ = self.run_sync(fake, roster={**base, ("Partner One", "Stars"): ["Ann Poe"]},
                                inactive={("Partner One", "Stars"): ["Kay Loe"]})
        self.assertEqual((code, fake.calls[0], sync.WARNINGS), (0, "CREATE roster 'Stars' (1 girls)", []))

    def test_a_new_club_named_like_a_long_entry_is_not_created(self):
        sheet = {**self.ROSTER, ("Partner Three", "Stars - Partner One"): ["Uma Umberlash"]}
        fake = FakeForm(*self.form(switched=True))
        code, _ = self.run_sync(fake, roster=sheet)
        self.assertEqual((code, fake.calls), (0, []))
        self.assertEqual(sync.WARNINGS, ["  ! new club 'Stars - Partner One' (Partner Three) has the name of "
                                         "what q11 sends as its Club Name - not added: give it a different name"])
        # …nor on a form not switched yet, where no roster sends that text: it is the long
        # name Partner One's Stars gets at the switch
        del sync.WARNINGS[:]
        fake = FakeForm(*self.form())
        code, _ = self.run_sync(fake, roster=sheet)
        self.assertEqual((code, fake.calls), (0, []))
        self.assertEqual(sync.WARNINGS, ["  ! new club 'Stars - Partner One' (Partner Three) has the name of "
                                         "what Partner One's club 'Stars' sends as its Club Name - not added: "
                                         "give it a different name"])

    def test_a_new_club_named_like_a_question_the_roster_no_longer_explains_is_not_created(self):
        # both Stars left the Roster altogether (rows deleted, not retired) and their
        # questions, each on its long entry, are still on the form. Partner Three's new Stars
        # has no namesake in the Roster and is what no roster sends - but q11's text is "Stars"
        sheet = {k: v for k, v in self.ROSTER.items() if k[1] != "Stars"}
        sheet[("Partner Three", "Stars")] = ["Uma Umberlash"]
        fake = FakeForm(*self.form(switched=True))
        summary, _ = self.summary(fake, roster=sheet)
        self.assertEqual(fake.calls, [])
        self.assertIn("  ! new club 'Stars' (Partner Three) has the name of another club on this form "
                      "(q11) - not added: give it a different name", sync.WARNINGS)
        self.assertEqual([n["value"] for n in summary["sf_names"]][1:3],
                         ["Stars - Partner One", "Stars - Partner Two"])

    def test_a_different_partners_club_never_takes_over_a_long_roster(self):
        # the Africa form's only Stars is Partner One's (long: Partner Two's is in Asia);
        # Partner One's goes inactive and Partner Three enrols a Stars with other girls
        regions = {("Partner Two", "Stars"): "Asia", ("Partner Two", "Beta Club"): "Asia"}
        on_africa = {k: v for k, v in self.ROSTER.items() if k not in regions}
        gone = {("Partner One", "Stars"): self.ROSTER[("Partner One", "Stars")]}
        # …also when the newcomer's name merely contains the other's ("Partner One Trust"):
        # the partner in the rule is, exactly, a partner the Roster has for that club
        for newcomer in ("Partner Three", "Partner One Trust"):
            del sync.WARNINGS[:]
            sheet = {k: v for k, v in self.ROSTER.items() if k not in gone}
            sheet[(newcomer, "Stars")] = ["Uma Umberlash", "Valeria Wrenfoldy"]
            fake = FakeForm(*self.form(roster=on_africa, long=[("Partner One", "Stars")]))
            summary, _ = self.summary(fake, roster=sheet, regions=regions, inactive=gone)
            self.assertEqual(fake.calls, [], newcomer)            # q11 keeps its girls and its long name
            self.assertEqual([r["partner"] for r in summary["same_name_refused"]], [newcomer])
            self.assertEqual(summary["sf_name_changes"], [])
            self.assertEqual(summary["sf_names"][1]["value"], "Stars - Partner One")
        # Partner One's Stars, still active, was moved to Asia, and "Partner One Trust" has a
        # Stars in Africa: the question's region is its own partner's (exactly), though the
        # name also fits the other loosely
        del sync.WARNINGS[:]
        on_form = {("Partner One", "Alpha Club"): self.ROSTER[("Partner One", "Alpha Club")],
                   ("Partner One", "Stars"): self.ROSTER[("Partner One", "Stars")]}
        fake = FakeForm(*self.form(roster=on_form, long=[("Partner One", "Stars")]))
        code, _ = self.run_sync(fake, regions={("Partner One", "Stars"): "Asia"},
                                roster={**on_form, ("Partner One Trust", "Stars"): ["Uma Umberlash"]})
        self.assertEqual((code, fake.calls), (0, []))
        self.assertIn("  ! 'Stars' (q11) belongs to Asia - kept (use --prune on a fresh clone to remove it)",
                      sync.WARNINGS)
        # a partner's acronym in an old hand-made rule is still the same partner ("WESAD")
        qs, wire = self.form()
        wire = [dict(c, terms=c["terms"].replace('"Partner Two"', '"Two"')) for c in wire]
        fake = FakeForm(qs, wire)
        code, _ = self.run_sync(fake, roster={**self.ROSTER, ("Partner Two", "Stars"): ["Uma Umberlash"]})
        self.assertEqual((code, fake.calls[0]), (0, "UPDATE roster 'Stars' (q12, 1 girls)"))

    # ---- a plain roster names no partner in its rule: its owner is read from the Roster's rows
    OLD_STARS = ["Ann Poe", "Kay Loe", "Sue Moe", "Liz Noe"]
    PLAIN = {("Partner One", "Alpha Club"): ["Jane Doe", "Mary Roe"],
             ("Partner One", "Stars"): OLD_STARS,                  # q11, the only Stars: plain
             ("Partner Two", "Beta Club"): ["Eve Hoe", "Ida Toe"]}
    REFUSED = ("  ! new club 'Stars' ({0}) has the name of {1}'s club - not added: give it a "
               "different name")

    def test_a_different_partners_club_never_takes_over_a_retired_plain_roster(self):
        # Partner One's Stars is retired (its rows inactive, its question still on the form, as
        # always) and Partner Three enrols a new Stars in the same region. One sheet entry, one
        # question, no partner in the rule: the newcomer used to take q11 - its girls on
        # Partner One's question, their attendance on Partner One's Salesforce Account
        gone = {("Partner One", "Stars"): self.OLD_STARS}
        base = {k: v for k, v in self.PLAIN.items() if k not in gone}
        for newcomer in (["Ann Poe", "Uma Umberlash", "Valeria Wrenfoldy", "Amara Pellucidor"],   # one name
                         ["Uma Umberlash", "Valeria Wrenfoldy", "Amara Pellucidor"]):             # …or none
            del sync.WARNINGS[:]
            fake = FakeForm(*self.form(roster=self.PLAIN), apply=True)
            summary, _ = self.summary(fake, "--apply", roster={**base, ("Partner Three", "Stars"): newcomer},
                                      inactive=gone)
            self.assertEqual((fake.calls, fake.writes), ([], []), newcomer)     # q11 keeps its girls
            self.assertEqual([r["partner"] for r in summary["same_name_refused"]], ["Partner Three"])
            self.assertEqual(sync.WARNINGS, [
                "  ? 'Stars' (q11) is on the form but not in the sheet export - keeping its current roster",
                self.REFUSED.format("Partner Three", "Partner One")])
            # q11 still sends "Stars"; the partner read from the Roster's rows is not the
            # form's own word, so sf_names names none for it (the cross-region check tells such
            # a question apart by its id, as before)
            self.assertEqual(summary["sf_names"][1], {"qid": "11", "partner": "", "club": "Stars",
                                                      "value": "Stars"})
            # …and the runner sees a refusal, not a change it would apply
            plan = auto_sync.plan_from_summary(summary)
            self.assertEqual((auto_sync.changes(plan), len(auto_sync.refused_clubs(plan))), (0, 1))

    def test_the_owner_of_a_plain_roster_keeps_it_whatever_its_new_roster_is(self):
        # Partner One's own Stars, three of its four girls replaced (the three now inactive
        # rows): its question, with or without a namesake in the Roster
        new = ["Ann Poe", "Bea Quillon", "Cyd Rennick", "Dot Sallow"]
        left = {("Partner One", "Stars"): self.OLD_STARS[1:]}
        sheet = {**self.PLAIN, ("Partner One", "Stars"): new}
        update = "UPDATE roster 'Stars' (q11, 4 girls)"
        # a retired namesake (the two live clubs of this shape: their next cohort must go through)
        fake = FakeForm(*self.form(roster=self.PLAIN))
        summary, _ = self.summary(fake, roster=sheet,
                                  inactive={**left, ("Partner Two", "Stars"): ["Gia Hollowmere"]})
        self.assertEqual((fake.calls[0], sync.WARNINGS, summary["same_name_refused"]), (update, [], []))
        # a new namesake that was refused and sits in the Roster until someone renames it: the
        # name has two sheet entries and one question, and roster overlap alone (1 of 4) used
        # to refuse BOTH - the existing club as "new" - and leave q11 stale
        del sync.WARNINGS[:]
        fake = FakeForm(*self.form(roster=self.PLAIN))
        summary, _ = self.summary(fake, inactive=left,
                                  roster={**sheet, ("Partner Three", "Stars"): ["Uma Umberlash", "Valeria Wrenfoldy"]})
        self.assertEqual(fake.calls[0], update)
        self.assertEqual(sync.WARNINGS, [self.REFUSED.format("Partner Three", "Partner One")])
        self.assertEqual([r["partner"] for r in summary["same_name_refused"]], ["Partner Three"])
        self.assertEqual(summary["sf_names"][1], {"qid": "11", "partner": "Partner One", "club": "Stars",
                                                  "value": "Stars"})

    def test_a_duplicate_under_a_partner_that_sorts_first_does_not_take_the_question(self):
        # Beta Club is Partner Two's (q13). The same club enrolled again under Partner One,
        # which sorts first, with half the same girls: taken in sheet order it got q13, and
        # the existing club was the one reported as "new club … not added"
        sheet = {**self.ROSTER, ("Partner One", "Beta Club"): ["Eve Hoe", "Uma Umberlash"]}
        fake = FakeForm(*self.form(switched=True))
        summary, _ = self.summary(fake, roster=sheet)
        self.assertEqual(fake.calls, [])
        self.assertEqual(sync.WARNINGS, ["  ! new club 'Beta Club' (Partner One) has the name of Partner "
                                         "Two's club - not added: give it a different name"])
        self.assertEqual(summary["sf_names"][3], {"qid": "13", "partner": "Partner Two", "club": "Beta Club",
                                                  "value": "Beta Club"})

    def test_a_tie_names_no_owner_and_a_moved_club_keeps_its_question(self):
        # the club moved to another partner with the same girls (the old partner's rows
        # inactive): both partners' rows list every girl q11 holds, so the Roster names no
        # owner and the club's one entry claims its question, as it always did
        gone = {("Partner One", "Stars"): self.OLD_STARS}
        base = {k: v for k, v in self.PLAIN.items() if k not in gone}
        fake = FakeForm(*self.form(roster=self.PLAIN))
        summary, _ = self.summary(fake, inactive=gone,
                                  roster={**base, ("Partner Three", "Stars"): self.OLD_STARS + ["Uma Umberlash"]})
        self.assertEqual((fake.calls[0], sync.WARNINGS), ("UPDATE roster 'Stars' (q11, 5 girls)", []))
        self.assertEqual((summary["same_name_refused"], summary["sf_names"][1]["partner"]), ([], "Partner Three"))
        # moved with three of its four girls: the Roster's rows give q11 to Partner One, the
        # girls are mostly the same - the same club, and the line says where the owner came from
        del sync.WARNINGS[:]
        fake = FakeForm(*self.form(roster=self.PLAIN))
        moved = self.OLD_STARS[:3] + ["Uma Umberlash", "Valeria Wrenfoldy"]
        summary, _ = self.summary(fake, inactive=gone, roster={**base, ("Partner Three", "Stars"): moved})
        self.assertEqual(fake.calls[0], "UPDATE roster 'Stars' (q11, 5 girls)")
        self.assertEqual(sync.WARNINGS, ["  ! 'Stars' (q11): the Roster's earlier rows give it to the partner "
                                         "'Partner One', the sheet says 'Partner Three' - the same girls, so the "
                                         "same club (the club was moved, or the partner respelled?)"])
        self.assertEqual(summary["same_name_refused"], [])
        # the same club enrolled twice with the same girls, under two partners: nothing says
        # whose the question is, so no owner is made up from the order of the Roster's rows
        # (Partner Three's come first here) - the first partner in name order keeps it, as before
        del sync.WARNINGS[:]
        fake = FakeForm(*self.form(roster=self.PLAIN))
        summary, _ = self.summary(fake, roster={("Partner Three", "Stars"): self.OLD_STARS, **self.PLAIN})
        self.assertEqual(fake.calls, [])
        self.assertEqual(sync.WARNINGS, [self.REFUSED.format("Partner Three", "Partner One")])
        self.assertEqual(summary["sf_names"][1]["partner"], "Partner One")

    def test_less_than_half_the_girls_is_no_evidence_of_an_owner(self):
        # Partner One's Stars got a wholly new roster (its old rows respelled in place: no
        # history), and one of q11's four girls once sat in Partner Two's retired Stars. One
        # name is no owner: Partner One's club keeps its question, with the usual warning -
        # it is not refused as "a new club with the name of Partner Two's club"
        new = ["Bea Quillon", "Cyd Rennick", "Dot Sallow"]
        fake = FakeForm(*self.form(roster=self.PLAIN))
        summary, _ = self.summary(fake, roster={**self.PLAIN, ("Partner One", "Stars"): new},
                                  inactive={("Partner Two", "Stars"): ["Ann Poe", "Gia Hollowmere"]})
        self.assertEqual(fake.calls[0], "UPDATE roster 'Stars' (q11, 3 girls)")
        self.assertEqual(summary["same_name_refused"], [])
        self.assertEqual(len(sync.WARNINGS), 1)
        self.assertIn(auto_sync.NO_SHARED_NAMES, sync.WARNINGS[0])      # the runner's band holds it

    def test_without_an_owner_the_best_overlap_takes_the_question_not_the_first_partner(self):
        # Partner Two's Beta Club (q13) held four girls. Two of their rows are gone from the
        # Roster (deleted by hand: no history) and sit, with two others, in a Beta Club under
        # Partner One: each partner's rows list two of q13's girls - a tie, no owner. The club
        # whose roster is wholly on the question keeps it, not the partner that sorts first
        on_form = {("Partner One", "Alpha Club"): ["Jane Doe", "Mary Roe"],
                   ("Partner Two", "Beta Club"): ["Eve Hoe", "Ida Toe", "Sue Moe", "Liz Noe"]}
        sheet = {**on_form, ("Partner Two", "Beta Club"): ["Eve Hoe", "Ida Toe"],
                 ("Partner One", "Beta Club"): ["Sue Moe", "Liz Noe", "Bea Quillon", "Cyd Rennick"]}
        fake = FakeForm(*self.form(roster=on_form))
        summary, _ = self.summary(fake, roster=sheet)
        self.assertEqual(fake.calls[0], "UPDATE roster 'Beta Club' (q13, 2 girls)")
        self.assertEqual([r["partner"] for r in summary["same_name_refused"]], ["Partner One"])
        self.assertEqual(summary["sf_names"][1], {"qid": "13", "partner": "Partner Two", "club": "Beta Club",
                                                  "value": "Beta Club"})

    # ---- any other change of what an existing club sends is by hand
    def renamed(self):
        """Beta Club renamed to Beta Club 2 as tools/rename_club.py leaves it: the
        Roster rows and the question's label renamed, the rule still on the old name."""
        sheet = {k: v for k, v in self.ROSTER.items() if k[1] != "Beta Club"}
        sheet[("Partner Two", "Beta Club 2")] = self.ROSTER[("Partner Two", "Beta Club")]
        qs, wire = self.form(switched=True)
        qs["13"]["text"] = "Beta Club 2"
        return sheet, qs, wire

    def test_a_renamed_club_is_listed_and_refused_on_apply_without_the_ok(self):
        sheet, qs, wire = self.renamed()
        line = ("  ! 'Beta Club 2' (q13): Club Name (question 5, what Salesforce reads) changes from "
                "'Beta Club' to 'Beta Club 2' - rename its Salesforce account first; an --apply needs "
                "--q5-change-ok")
        fake = FakeForm(qs, wire)
        summary, _ = self.summary(fake, roster=sheet)
        self.assertEqual(sync.WARNINGS, [line])
        self.assertIn(auto_sync.SF_NAME_CHANGE, line)
        self.assertEqual(summary["sf_name_changes"], [{"qid": "13", "club": "Beta Club 2", "old": "Beta Club",
                                                       "new": "Beta Club 2", "switch": False}])
        self.assertEqual([c.split(" (")[0] for c in fake.calls], ["UPDATE club picker", "REPLACE conditions"])
        for extra in (("--apply",), ("--apply", "--same-name-switch")):   # the switch flag is no consent
            fake = FakeForm(qs, wire, apply=True)
            code, _ = self.run_sync(fake, *extra, roster=sheet)
            self.assertIn("Refusing: question 5 (what Salesforce reads) would change for 1 existing club",
                          str(code))
            self.assertIn("--q5-change-ok", str(code))
            self.assertEqual(fake.writes, [], extra)                       # before any write
        fake = FakeForm(qs, wire, apply=True)
        code, _ = self.run_sync(fake, "--apply", "--q5-change-ok", roster=sheet)
        self.assertEqual(code, 0)
        self.assertEqual([(m, p) for m, p, _ in fake.writes], [("POST", "/question/500"), ("PUT", "/properties")])
        self.assertEqual(self.shows(fake.writes[1][2], "13"), [("500", "equals", "Beta Club 2")])

    def test_a_respelled_partner_keeps_its_roster_and_is_a_q5_change(self):
        # Partner Two becomes "Second Partner" in the sheet (no spelling contains the other)
        sheet = {k: v for k, v in self.ROSTER.items() if k[0] != "Partner Two"}
        sheet[("Second Partner", "Stars")] = self.ROSTER[("Partner Two", "Stars")]
        sheet[("Second Partner", "Beta Club")] = self.ROSTER[("Partner Two", "Beta Club")]
        fake = FakeForm(*self.form(switched=True))
        summary, _ = self.summary(fake, roster=sheet)
        self.assertFalse([c for c in fake.calls if "roster" in c], fake.calls)     # no second roster
        self.assertEqual(summary["sf_name_changes"],
                         [{"qid": "12", "club": "Stars", "old": "Stars - Partner Two",
                           "new": "Stars - Second Partner", "switch": False}])
        self.assertEqual(summary["same_name_refused"], [])
        # long to long is not the switch's own change: --same-name-switch is no consent to it
        fake = FakeForm(*self.form(switched=True), apply=True)
        code, _ = self.run_sync(fake, "--apply", "--same-name-switch", roster=sheet)
        self.assertIn("Refusing: question 5 (what Salesforce reads) would change for 1 existing club",
                      str(code))
        self.assertEqual(fake.writes, [])
        # the same on a form where it is the only roster of that name (its namesake in Asia)
        del sync.WARNINGS[:]
        regions = {("Partner One", "Stars"): "Asia", ("Partner One", "Alpha Club"): "Asia"}
        was = {k: v for k, v in self.ROSTER.items() if k not in regions}
        fake = FakeForm(*self.form(roster=was, long=[("Partner Two", "Stars")]))
        summary, _ = self.summary(fake, roster={**sheet, **{k: self.ROSTER[k] for k in regions}},
                                  regions=regions)
        self.assertFalse([c for c in fake.calls if "roster" in c], fake.calls)
        self.assertEqual([(c["qid"], c["new"]) for c in summary["sf_name_changes"]],
                         [("12", "Stars - Second Partner")])
        # …and when the old spelling is still in the Roster (its rows inactive, the girls
        # re-entered under the new one): the rule's partner is a real one, the girls are the
        # same - the question is reused, never doubled
        del sync.WARNINGS[:]
        fake = FakeForm(*self.form(roster=was, long=[("Partner Two", "Stars")]))
        summary, _ = self.summary(fake, roster={**sheet, **{k: self.ROSTER[k] for k in regions}},
                                  regions=regions,
                                  inactive={("Partner Two", "Stars"): self.ROSTER[("Partner Two", "Stars")]})
        self.assertFalse([c for c in fake.calls if "roster" in c], fake.calls)
        self.assertEqual([(c["qid"], c["new"]) for c in summary["sf_name_changes"]],
                         [("12", "Stars - Second Partner")])
        self.assertEqual(summary["same_name_refused"], [])
        self.assertTrue(any("the same girls, so the same club" in w for w in sync.WARNINGS))

    def test_the_exact_partner_is_matched_before_the_loose_one(self):
        # "Partner One" is contained in "Partner One Trust", and both have a Stars: two
        # partners, each keeps its own question whatever its new roster is
        roster = {("Partner One", "Stars"): ["Ann Poe", "Kay Loe"],
                  ("Partner One Trust", "Stars"): ["Sue Moe", "Liz Noe"]}
        self.QIDS = {("Partner One Trust", "Stars"): "11", ("Partner One", "Stars"): "12"}
        sheet = {("Partner One", "Stars"): ["Uma Umberlash"],
                 ("Partner One Trust", "Stars"): ["Valeria Wrenfoldy", "Amara Pellucidor"]}
        updates = ["UPDATE roster 'Stars' (q11, 2 girls)", "UPDATE roster 'Stars' (q12, 1 girls)"]
        for switched in (True, False):
            del sync.WARNINGS[:]
            fake = FakeForm(*self.form(roster=roster, switched=switched))
            code, _ = self.run_sync(fake, roster=sheet)
            self.assertEqual(code, 0)
            self.assertEqual(sorted(c for c in fake.calls if "roster" in c), updates)
            self.assertEqual(sync.WARNINGS, [])
        # the order of the two passes: q11's rule names a spelling the Roster does not have
        # ("Partner One Trus", an old hand-made rule), which loosely matches BOTH entries.
        # Matched loosely first, Partner One (sorted first) would take q11, q12 would match
        # no partner and Partner One Trust's club would be refused as new
        qs, wire = self.form(roster=roster, switched=False)
        wire = [dict(c, terms=c["terms"].replace('"Partner One Trust"', '"Partner One Trus"')) for c in wire]
        self.assertEqual(sum('"Partner One Trus"' in c["terms"] for c in wire), 1)   # the rule is there
        del sync.WARNINGS[:]
        fake = FakeForm(qs, wire)
        code, _ = self.run_sync(fake, roster=sheet)
        self.assertEqual(code, 0)
        self.assertEqual(sorted(c for c in fake.calls if "roster" in c), updates)
        self.assertEqual(sync.WARNINGS, [])

    def test_a_club_renamed_out_of_a_dash_name_gets_no_made_up_partner(self):
        # "Beta Club - Juniors" renamed to "Beta Club": its rule still tests the old name, and
        # "Juniors" is no partner of Beta Club - no second roster, a plain name, one q5 change
        roster = {k: v for k, v in self.ROSTER.items() if k[1] != "Beta Club"}
        roster[("Partner Two", "Beta Club - Juniors")] = ["Eve Hoe", "Ida Toe"]
        self.QIDS = {**self.QIDS, ("Partner Two", "Beta Club - Juniors"): "13"}
        qs, wire = self.form(roster=roster, switched=True)
        qs["13"]["text"] = "Beta Club"
        fake = FakeForm(qs, wire)
        summary, _ = self.summary(fake, roster={**self.ROSTER, ("Partner Two", "Beta Club"): ["Uma Umberlash"]})
        self.assertEqual([c.split(" (")[0] for c in fake.calls],
                         ["UPDATE roster 'Beta Club'", "UPDATE club picker", "REPLACE conditions"])
        self.assertEqual([(c["old"], c["new"]) for c in summary["sf_name_changes"]],
                         [("Beta Club - Juniors", "Beta Club")])

    # ---- refusals, before any write
    def test_the_partner_list_is_retired(self):
        fake = FakeForm(*self.form(), apply=True)
        code, _ = self.run_sync(fake, "--partner-picker", "--apply")
        self.assertIn("retired 2026-09-30", str(code))
        self.assertEqual(fake.writes, [])
        fake = FakeForm(*self.form(partner_list="Partner One|Partner Two"), apply=True)
        code, _ = self.run_sync(fake, "--apply")
        self.assertIn("q600 is a partner list", str(code))
        self.assertIn("retired 2026-09-30", str(code))
        self.assertEqual(fake.writes, [])

    def test_the_switch_needs_the_picker(self):
        fake = FakeForm(*self.form(picker=False), apply=True)
        code, _ = self.run_sync(fake, "--same-name-switch", "--apply")
        self.assertIn("--same-name-switch needs the Club picker", str(code))
        self.assertEqual(fake.writes, [])

    def test_an_entry_may_not_hold_the_option_separator_or_a_field_reference(self):
        new = {("Partner Three", "Gamma Club"): ["Amara Pellucidor"]}     # an apply would create it first
        for partner, fragment in (("Partner|Two", "'Stars - Partner|Two'"),
                                  ("Partner {5} Two", "'Stars - Partner {5} Two'")):
            roster = {(partner if k == ("Partner Two", "Stars") else k[0], k[1]): v
                      for k, v in self.ROSTER.items()}
            self.QIDS = {**SameNameFlow.QIDS, (partner, "Stars"): "12"}
            fake = FakeForm(*self.form(roster=roster), apply=True)
            code, _ = self.run_sync(fake, "--same-name-switch", "--apply", roster={**roster, **new})
            self.assertIn("may not contain '|'", str(code))
            self.assertIn(fragment, str(code))
            self.assertEqual(fake.writes, [])
        # a new club's own name too
        fake = FakeForm(*self.form(), apply=True)
        code, _ = self.run_sync(fake, "--apply", roster={**self.ROSTER, ("Partner Three", "Gamma {Club}"): ["Amara Pellucidor"]})
        self.assertIn("'Gamma {Club}'", str(code))
        self.assertEqual(fake.writes, [])

    def test_two_rosters_on_one_entry_are_refused_unless_the_partner_box_tells_them_apart(self):
        new = {("Partner Three", "Gamma Club"): ["Amara Pellucidor"]}
        # today's form, with the box hidden and its rules gone: nothing tells the two Stars apart
        qs, wire = self.form()
        wire = [c for c in wire if '"field": "331"' not in c["terms"] and '"field": "331"' not in c["action"]]
        fake = FakeForm(qs, wire, apply=True)
        code, _ = self.run_sync(fake, "--apply", roster={**self.ROSTER, **new})
        self.assertIn("2 rosters (q11, q12) would share the Club picker entry 'Stars'", str(code))
        self.assertIn("--same-name-switch", str(code))
        self.assertEqual(fake.writes, [])
        code, _ = self.run_sync(FakeForm(qs, wire), "--same-name-switch")     # …which is the way out
        self.assertEqual(code, 0)

    def test_a_long_name_equal_to_another_clubs_name_is_refused(self):
        # Partner Three already has a club literally named "Stars - Partner One" (another region)
        sheet = {**self.ROSTER, ("Partner Three", "Stars - Partner One"): ["Uma Umberlash"]}
        fake = FakeForm(*self.form(), apply=True)
        code, _ = self.run_sync(fake, "--same-name-switch", "--apply", roster=sheet,
                                regions={("Partner Three", "Stars - Partner One"): "Asia"})
        self.assertIn("would send 'Stars - Partner One' to question 5, which is the name of Partner "
                      "Three's club", str(code))
        self.assertEqual(fake.writes, [])

    # ---- a form without the Club picker keeps today's rules
    def test_a_form_without_the_picker_keeps_its_rules_byte_for_byte(self):
        qs, wire = self.form(picker=False)
        self.assertTrue(any('"field": "331"' in c["terms"] for c in wire))       # told apart by the box
        fake = FakeForm(qs, wire)
        summary, out = self.summary(fake)
        self.assertEqual((fake.calls, sync.WARNINGS), ([], []))
        self.assertIn("(conditions unchanged - skipping the rewrite)", out)
        self.assertEqual([n["value"] for n in summary["sf_names"]], ["Alpha Club", "Stars", "Stars", "Beta Club"])
        # with a roster update the rewrite happens, and is the same rules
        sheet = {**self.ROSTER, ("Partner One", "Alpha Club"): ["Jane Doe"]}
        fake = FakeForm(qs, wire)
        code, _ = self.run_sync(fake, roster=sheet)
        self.assertEqual(code, 0)
        self.assertEqual(sync._norm_rules(fake.writes[1][2]["properties"]["conditions"]), sync._norm_rules(wire))
        self.assertNotIn(self.HIDE, fake.calls)               # the typed box is how they are told apart
        # …and stays visible on such a form when no name is shared and no rule shows it:
        # without the picker a mentor types the club, and may have to type the partner later
        alone = {k: v for k, v in self.ROSTER.items() if k != ("Partner Two", "Stars")}
        qs1, wire1 = self.form(roster=alone, picker=False)
        self.assertFalse(any('"331"' in c["terms"] + c["action"] for c in wire1))
        self.assertNotEqual(qs1["331"].get("hidden"), "Yes")
        fake = FakeForm(qs1, wire1, apply=True)
        self.assertEqual((self.run_sync(fake, "--apply", roster=alone)[0], fake.calls), (0, []))
        # a new club with a name in use is refused there too
        del sync.WARNINGS[:]
        fake = FakeForm(qs, wire)
        code, _ = self.run_sync(fake, roster={**self.ROSTER, ("Partner Three", "Stars"): ["Uma Umberlash"]})
        self.assertEqual((code, fake.calls, len(sync.WARNINGS)), (0, [], 1))
        # two questions of one name whose rules name no partner, one of them a retired club's:
        # still the refusal it always was - a partner read from the Roster's rows is never
        # written into a typed-Partner rule
        bare = [c for c in wire if '"field": "331"' not in c["terms"] and '"field": "331"' not in c["action"]]
        gone = {("Partner Two", "Stars"): self.ROSTER[("Partner Two", "Stars")]}
        fake = FakeForm(qs, bare, apply=True)
        code, _ = self.run_sync(fake, "--apply", inactive=gone,
                                roster={k: v for k, v in self.ROSTER.items() if k not in gone})
        self.assertIn("Cannot disambiguate 'Stars' (q12): no partner in the sheet or the form's current rules",
                      str(code))
        self.assertEqual(fake.writes, [])

    def test_without_submit_or_a_link_a_new_roster_still_goes_at_the_end(self):
        qs, wire = self.form()
        sheet = {**self.ROSTER, ("Partner Two", "Gamma Club"): ["Uma Umberlash"]}
        fake = FakeForm(qs, wire)
        code, out = self.run_sync(fake, roster=sheet)
        self.assertEqual(code, 0)
        self.assertEqual(fake.calls[0], "CREATE roster 'Gamma Club' (1 girls)")
        end = max(int(q["order"]) for q in qs.values()) + 1
        self.assertEqual(fake.writes[0][2]["question[order]"], str(end))
        self.assertIn(f"New rosters go at order {end}, the end of the form", out)


class ClubGuardFlow(unittest.TestCase):
    """sync_attendance_form.main() with --club-guard and without, on the fake
    Africa form of SameNameFlow - switched: each of the two Stars has its own
    picker entry, as on the live forms after the 2026-09-30 rollout - plus a
    Submit button (q2) below the rosters (the layout after the roster-order
    repair, glow/layout.py) and, when the form has it, the warning (q700).
    Every question carries its qid, as Jotform's GET does (the layout code
    orders by it). Fictional names."""

    ROSTER, QIDS, MODULES = SameNameFlow.ROSTER, SameNameFlow.QIDS, SameNameFlow.MODULES
    OPTIONS = SameNameFlow.LONG        # Alpha Club, Beta Club, Stars - Partner One, Stars - Partner Two
    CALC = "|" + "|".join(OPTIONS)
    NEW_CLUB = {("Partner One", "Gamma Club"): ["Amara Pellucidor", "Beatrice Marrowgate"]}
    WITH_NEW = "Alpha Club|Beta Club|Gamma Club|Stars - Partner One|Stars - Partner Two"
    texts = SameNameFlow.texts

    def setUp(self):
        SameNameFlow.setUp(self)

    def tearDown(self):
        SameNameFlow.tearDown(self)

    def run_sync(self, fake, *extra, roster=None):
        return SameNameFlow.run_sync(self, fake, *extra, roster=roster)

    def form(self, guard=True, calc=True, roster=None, switched=True):
        """(questions, wire conditions) of a form in step with `roster`; guard:
        the warning q700 and the rules it brings; calc: the picker's calcValues;
        switched=False: the form before --same-name-switch (the two Stars on one
        entry, told apart by the typed Partner box)."""
        roster = self.ROSTER if roster is None else roster
        qs, _ = SameNameFlow.form(self, roster=roster, switched=switched)
        qs["2"] = {"type": "control_button", "text": "Submit", "name": "submit2", "order": "60"}
        options = qs["500"]["options"].split("|")
        if calc:
            qs["500"]["calcValues"] = sync.picker_calc_values(options)
        if guard:
            qs["700"] = dict(sync.GUARD_PROPS, type="control_text", name=sync.GUARD_NAME, order="4")
        for q_id, q in qs.items():
            q.setdefault("qid", q_id)
        option_of, partner_of = self.texts(roster, switched)
        conds = sync.build_conditions(option_of, partner_of, {y: o.split("|") for y, o in self.MODULES.items()},
                                      picker="500", picker_options=options, guard="700" if guard else None,
                                      submit="2" if guard else None)
        return qs, [dict(c, terms=json.dumps(c["terms"]), action=json.dumps(c["action"])) for c in conds]

    @staticmethod
    def guard_rules(conds):
        return [c for c in conds if any(a.get("visibility") in ("Hide", "Disable")
                                         for a in (json.loads(c["action"]) if isinstance(c["action"], str)
                                                   else c["action"]))]

    def test_without_the_guard_nothing_changes(self):
        fake = FakeForm(*self.form(guard=False, calc=False))
        code, out = self.run_sync(fake)
        self.assertEqual((code, fake.calls), (0, []))
        self.assertNotIn("Club guard:", out)

    def test_dry_run_adds_calc_values_the_warning_and_two_rules(self):
        qs, wire = self.form(guard=False, calc=False)
        fake = FakeForm(qs, wire)
        code, out = self.run_sync(fake, "--club-guard")
        self.assertEqual(code, 0)
        self.assertEqual(fake.calls, ["UPDATE club picker (4 clubs: calcValues)",
                                      "CREATE club guard (below the Club picker)",
                                      f"REPLACE conditions ({len(wire) + 2} rules)"])
        self.assertIn(f"conditions: {len(wire)} kept, 2 new, 0 dropped", out)   # the two guard rules only
        self.assertEqual(fake.writes[0][2], {"question[calcValues]": self.CALC})
        _, path, fields = fake.writes[1]
        self.assertEqual(path, "/questions")
        self.assertEqual(fields, {"question[type]": "control_text", "question[name]": sync.GUARD_NAME,
                                  "question[order]": "4",          # the picker's order (3) + 1
                                  "question[text]": glow_sync.guard_html(), "question[hidden]": "Yes"})
        conds = fake.writes[2][2]["properties"]["conditions"]
        self.assertEqual(len(self.guard_rules(conds)), 2)
        self.assertEqual({a["field"] for c in self.guard_rules(conds) for a in json.loads(c["action"])
                          if a["visibility"] == "Show"}, {"NEW_GUARD"})
        self.assertTrue(auto_sync.GUARD_RX.match("  - " + fake.calls[1]))
        self.assertTrue(auto_sync.PICKER_RX.match("  - " + fake.calls[0]))

    def test_the_warning_is_placed_with_the_modules_order_of(self):
        # the create takes the picker's order from glow.links.order_of (what form_status
        # checks the placement with), not from main()'s local helper, which the parallel
        # branch wf5/rosters-above-submit removes: after both merge that was a NameError
        # between the picker write and the rules
        from unittest import mock
        fake = FakeForm(*self.form(guard=False, calc=False))
        with mock.patch.object(sync, "links_order_of", side_effect=links.order_of) as spy:
            code, _ = self.run_sync(fake, "--club-guard")
        self.assertEqual(code, 0)
        self.assertTrue(spy.called)
        self.assertEqual(fake.writes[1][2]["question[order]"], "4")         # the picker's 3 + 1

    def test_apply_writes_picker_then_warning_then_rules_with_its_qid(self):
        qs, wire = self.form(guard=False, calc=False)
        fake = FakeForm(qs, wire, apply=True, created={"qid": 700})
        summary = os.path.join(self.tmp.name, "plan.json")
        code, _ = self.run_sync(fake, "--club-guard", "--apply", "--summary-json", summary)
        self.assertEqual(code, 0)
        self.assertEqual([(m, p) for m, p, _ in fake.writes],
                         [("POST", "/question/500"), ("POST", "/questions"), ("PUT", "/properties")])
        conds = fake.writes[2][2]["properties"]["conditions"]
        show, req = conds[-2:]
        self.assertEqual(self.guard_rules(conds), [show, req])
        self.assertEqual([(a["visibility"], a["field"]) for a in json.loads(show["action"])],
                         [("Show", "700"), ("Hide", "2")])
        self.assertEqual((req["type"], [(a["visibility"], a["field"]) for a in json.loads(req["action"])]),
                         ("require", [("Disable", "2")]))
        for rule in (show, req):
            self.assertEqual(rule["link"], "All")
            self.assertEqual([(t["field"], t["operator"], t["value"]) for t in json.loads(rule["terms"])],
                             [("500", "isFilled", "")] + [(sync.CLUB_NAME, "notEquals", o) for o in self.OPTIONS])
        agg = [a for c in conds for a in json.loads(c["action"]) if a.get("resultField") == sync.CONTACT_IDS]
        self.assertEqual(agg[0]["equation"], "{10}{11}{12}{13}")        # q18 exactly as before
        # question 5 is still filled from the Club picker, exactly as before
        copy = [a for c in conds for a in json.loads(c["action"]) if a.get("resultField") == sync.CLUB_NAME]
        self.assertEqual([(a["equation"], a["operands"]) for a in copy], [("{500}", "500")])
        with open(summary, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["club_guard"], "700")

    def test_a_create_without_a_question_id_writes_no_guard_rules(self):
        fake = FakeForm(*self.form(guard=False, calc=False), apply=True, created={})
        code, _ = self.run_sync(fake, "--club-guard", "--apply")
        self.assertEqual(code, 0)
        # the rules stay today's (unchanged: no rewrite), the picker got its calcValues
        self.assertEqual(fake.calls, ["UPDATE club picker (4 clubs: calcValues)",
                                      "CREATE club guard (below the Club picker)"])
        self.assertTrue(any("carried no question id" in w for w in sync.WARNINGS))

    def test_a_form_with_the_guard_in_step_needs_nothing(self):
        fake = FakeForm(*self.form())
        code, out = self.run_sync(fake)
        self.assertEqual((code, fake.calls), (0, []))
        self.assertIn("Club guard: q700", out)
        code, out = self.run_sync(fake, "--club-guard")
        self.assertEqual((code, fake.calls), (0, []))
        self.assertIn("--club-guard is not needed", out)

    def test_the_warning_and_calc_values_are_kept_in_shape(self):
        qs, wire = self.form()
        qs["700"].update(hidden="No", text="<p>edited by hand</p>")
        qs["500"]["calcValues"] = self.CALC.replace("|Alpha Club|Beta Club", "|Beta Club|Alpha Club")
        fake = FakeForm(qs, wire)
        code, _ = self.run_sync(fake)
        self.assertEqual(code, 0)
        self.assertEqual(fake.calls, ["UPDATE club picker (4 clubs: calcValues)",
                                      "UPDATE club guard (hidden, text)"])
        self.assertEqual(fake.writes[1][2], {"question[hidden]": "Yes", "question[text]": glow_sync.guard_html()})
        self.assertTrue(auto_sync.GUARD_RX.match("  - " + fake.calls[1]))

    def test_a_new_club_joins_the_options_calc_values_and_the_guard_terms(self):
        sheet = {**self.ROSTER, **self.NEW_CLUB}
        fake = FakeForm(*self.form())
        code, _ = self.run_sync(fake, roster=sheet)
        self.assertEqual(code, 0)
        self.assertEqual(fake.calls[:2], ["CREATE roster 'Gamma Club' (2 girls)",
                                          "UPDATE club picker (5 clubs: calcValues, options)"])
        self.assertEqual(fake.writes[1][2], {"question[options]": self.WITH_NEW,
                                             "question[calcValues]": "|" + self.WITH_NEW})
        conds = fake.writes[2][2]["properties"]["conditions"]
        for rule in self.guard_rules(conds):
            values = [t["value"] for t in json.loads(rule["terms"]) if t["operator"] == "notEquals"]
            self.assertEqual(values, self.WITH_NEW.split("|"))

    def test_a_new_club_with_the_guard_goes_above_submit_and_the_warning_below_the_picker(self):
        # both tracks' creates in one run (integration of wf5/rosters-above-submit and
        # wf5/club-guard): the roster at the last roster's order (above Submit, glow/layout.py),
        # the warning at the picker's order + 1; both computed from the form as read
        sheet = {**self.ROSTER, **self.NEW_CLUB}
        fake = FakeForm(*self.form(guard=False, calc=False))
        code, out = self.run_sync(fake, "--club-guard", roster=sheet)
        self.assertEqual(code, 0)
        self.assertEqual([c.split(" (")[0] for c in fake.calls],
                         ["CREATE roster 'Gamma Club'", "UPDATE club picker", "CREATE club guard",
                          "REPLACE conditions"])
        last = str(max(40 + int(q) for q in self.QIDS.values()))           # 53, Submit is at 60
        self.assertEqual(fake.writes[0][2]["question[order]"], last)
        self.assertIn(f"New rosters go at order {last}, above submit2 (q2)", out)
        self.assertEqual(fake.writes[2][2]["question[order]"], "4")          # the picker's 3 + 1

    def test_calc_values_the_picker_carries_are_kept_aligned_without_the_guard(self):
        # a guard rolled back with its calcValues left: a new club must not shift them
        sheet = {**self.ROSTER, **self.NEW_CLUB}
        fake = FakeForm(*self.form(guard=False, calc=True))
        self.run_sync(fake, roster=sheet)
        self.assertIn("UPDATE club picker (5 clubs: calcValues, options)", fake.calls)
        self.assertFalse(self.guard_rules(fake.writes[-1][2]["properties"]["conditions"]))
        fake = FakeForm(*self.form(guard=False, calc=False))       # none carried: none written
        self.run_sync(fake, roster=sheet)
        self.assertIn("UPDATE club picker (5 clubs: options)", fake.calls)

    def test_refusals_come_before_any_write(self):
        sheet = {**self.ROSTER, **self.NEW_CLUB}          # an apply would create a roster first
        qs, wire = self.form(guard=False)
        del qs["500"]                                     # no Club picker
        fake = FakeForm(qs, wire, apply=True)
        code, _ = self.run_sync(fake, "--club-guard", "--apply", roster=sheet)
        self.assertIn("needs the Club picker", str(code))
        self.assertEqual(fake.writes, [])
        qs, wire = self.form()
        qs["701"] = dict(qs["700"], qid="701")            # two warnings: which one to show?
        fake = FakeForm(qs, wire, apply=True)
        code, _ = self.run_sync(fake, "--apply", roster=sheet)       # refused without the flag too
        self.assertIn("2 elements are named 'clubGuard' (q700, q701)", str(code))
        self.assertEqual(fake.writes, [])
        qs, wire = self.form()
        qs["700"]["type"] = "control_textbox"
        fake = FakeForm(qs, wire, apply=True)
        code, _ = self.run_sync(fake, "--apply", roster=sheet)
        self.assertIn("not a text element", str(code))
        self.assertEqual(fake.writes, [])
        qs, wire = self.form(guard=False)
        qs["3"] = dict(qs["2"], qid="3")                  # two Submit buttons
        fake = FakeForm(qs, wire, apply=True)
        code, _ = self.run_sync(fake, "--club-guard", "--apply", roster=sheet)
        self.assertIn("expected one Submit button, found 2", str(code))
        self.assertEqual(fake.writes, [])
        code, _ = self.run_sync(FakeForm(qs, wire))       # without the guard, nothing to create: syncs as ever
        self.assertEqual(code, 0)
        # a roster to create: the layout refuses too (where would it go? glow/layout.py), before any write
        fake = FakeForm(qs, wire, apply=True)
        code, _ = self.run_sync(fake, "--apply", roster=sheet)
        self.assertIn("expected one Submit button, found 2", str(code))
        self.assertEqual(fake.writes, [])

    def test_a_warning_on_a_form_without_the_picker_writes_no_guard_rules(self):
        qs, wire = self.form()
        del qs["500"]
        fake = FakeForm(qs, wire)
        code, _ = self.run_sync(fake)
        self.assertEqual(code, 0)
        self.assertTrue(any("needs the Club picker" in w for w in sync.WARNINGS))
        self.assertFalse(self.guard_rules(fake.writes[-1][2]["properties"]["conditions"]))

    def test_two_names_joining_into_a_third_are_warned(self):
        self.assertEqual(sync.joined_clashes(["Star", "light", "Moon", "StarLight"]),
                         [("Star", "light", "StarLight")])
        self.assertEqual(sync.joined_clashes(["Alpha Club", "Beta Club", "Stars"]), [])
        roster = {("Partner One", "Sun"): ["Amara Pellucidor"], ("Partner One", "Rise"): ["Beatrice Marrowgate"],
                  ("Partner Two", "SunRise"): ["Chiara Ostrivane"]}
        self.QIDS = {("Partner One", "Sun"): "10", ("Partner One", "Rise"): "11",
                     ("Partner Two", "SunRise"): "12"}
        for guard in (False, True):
            del sync.WARNINGS[:]
            code, _ = self.run_sync(FakeForm(*self.form(guard=guard, roster=roster)), roster=roster)
            self.assertEqual(code, 0)
            self.assertEqual(any("fills Club Name with 'SunRise'" in w for w in sync.WARNINGS), guard)

    def test_the_same_name_switch_on_a_guarded_form(self):
        # the live forms on 2026-09-30: the guard and calcValues on, the two Stars still on
        # one entry. One string everywhere: option = calcValue = roster rule = guard term
        qs, wire = self.form(switched=False)
        self.assertEqual(qs["500"]["options"], "Alpha Club|Beta Club|Stars")
        fake = FakeForm(qs, wire, apply=True)
        code, out = self.run_sync(fake, "--same-name-switch", "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(fake.calls, ["UPDATE club picker (4 clubs: calcValues, options)",
                                      f"REPLACE conditions ({len(wire) - 1} rules)", SameNameFlow.HIDE])
        self.assertEqual(fake.writes[0][2], {"question[options]": "|".join(self.OPTIONS),
                                             "question[calcValues]": self.CALC})
        conds = fake.writes[1][2]["properties"]["conditions"]
        for rule in self.guard_rules(conds):
            self.assertEqual([t["value"] for t in json.loads(rule["terms"]) if t["operator"] == "notEquals"],
                             self.OPTIONS)
        # 2 roster rules and the 2 guard rules are new; theirs and the Partner-box rule go
        self.assertIn(f"conditions: {len(wire) - 5} kept, 4 new, 5 dropped", out)
        self.assertEqual(sync._norm_rules(conds), sync._norm_rules(self.form()[1]))   # = the switched form
        agg = [a for c in conds for a in json.loads(c["action"]) if a.get("resultField") == sync.CONTACT_IDS]
        self.assertEqual(agg[0]["equation"], "{10}{11}{12}{13}")        # q18 exactly as before
        # before the switch, without the flag: nothing, the guard included
        fake = FakeForm(qs, wire)
        self.assertEqual((self.run_sync(fake)[0], fake.calls), (0, []))


def constants(first=True, operand=True, required=True):
    """glow.sync's three question-18 constants patched together (every reader takes them
    from the module at run time: build_conditions, the sync's warning and required
    writes, form_status, restore_conditions)."""
    import contextlib
    from unittest import mock
    stack = contextlib.ExitStack()
    for name, value in (("CONTACT_IDS_FIRST", first), ("CONTACT_IDS_PICKER_OPERAND", operand),
                        ("ROSTERS_REQUIRED", required)):
        stack.enter_context(mock.patch.object(glow_sync, name, value))
    return stack


class ContactIds(unittest.TestCase):
    """Question 18 (Contact_IDs, the names Salesforce stores) is recalculated after
    the rosters show or hide, and at least one girl is ticked
    (docs/plans/2026-09-30-contact-ids.md): the rule order and operand, the
    required rosters, the sync's warning and writes, the runner's refusal, the
    audits in every combination of the constants. Fictional names."""

    CLUBS, PARTNERS = ConditionBuilder.CLUBS, ConditionBuilder.PARTNERS
    OPTIONS = ConditionBuilder.OPTIONS
    ROSTERS = ["10", "11", "12", "13"]
    # SameNameFlow's fake Africa form (form(), run_sync() and summary() below use it)
    ROSTER, QIDS, MODULES, texts = SameNameFlow.ROSTER, SameNameFlow.QIDS, SameNameFlow.MODULES, SameNameFlow.texts

    def setUp(self):
        SameNameFlow.setUp(self)

    def tearDown(self):
        SameNameFlow.tearDown(self)

    def build(self, picker="500", guard=True, **kw):
        sync._counter[0] = 0
        extra = dict(picker_options=self.OPTIONS, guard="700", submit="2") if guard and picker else {}
        return sync.build_conditions(self.CLUBS, self.PARTNERS, ConditionBuilder.MODULES, picker=picker,
                                     **extra, **kw)

    @staticmethod
    def sum_at(conds):
        """(position, action) of the rule that calculates question 18."""
        (pos, action), = [(i, c["action"][0]) for i, c in enumerate(conds)
                          if c["type"] == "calculation" and c["action"][0]["resultField"] == sync.CONTACT_IDS]
        return pos, action

    # ---- build_conditions
    def test_the_sum_is_rule_0_with_its_ids_minted_first_and_the_picker_an_operand(self):
        conds = self.build()
        pos, sum_ = self.sum_at(conds)
        self.assertEqual(pos, 0)
        self.assertEqual((sum_["operands"], sum_["equation"]), ("500,10,11,12,13", "{10}{11}{12}{13}"))
        self.assertEqual((sum_["ignoreHiddenFields"], sum_["insertAsText"], sum_["readOnly"]), (True, True, False))
        self.assertEqual([(t["field"], t["operator"]) for t in conds[0]["terms"]], [("500", "isFilled")])
        # minted first: its term, action and rule carry the three lowest ids, and id order is index order
        base = sync.ID_BASE
        self.assertEqual((conds[0]["terms"][0]["id"], sum_["id"], conds[0]["id"]),
                         (f"term_{base + 1}", f"action_{base + 2}", str(base + 3)))
        ids = [int(c["id"]) for c in conds]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual([c["index"] for c in conds], [str(i) for i in range(len(conds))])
        self.assertEqual([c["priority"] for c in conds], [c["index"] for c in conds])
        # the guard's two rules are still the last two
        self.assertEqual([c["type"] for c in conds[-2:]], ["field", "require"])
        self.assertEqual([a["field"] for a in conds[-1]["action"]], ["2"])
        # every other rule is the old shape's, in the old order
        with constants(first=False, operand=False):
            old = self.build()
        old_pos, old_sum = self.sum_at(old)
        self.assertEqual(old_pos, len(old) - 3)            # before 2026-10: after the copies, before the guard
        self.assertEqual(old_sum["operands"], "10,11,12,13")
        new, before = sync._norm_rules(conds), sync._norm_rules(old)
        self.assertEqual(new[1:], before[:old_pos] + before[old_pos + 1:])
        self.assertEqual(json.loads(new[0][3])[0]["operands"], "500,10,11,12,13")
        self.assertEqual({k: v for k, v in json.loads(new[0][3])[0].items() if k != "operands"},
                         {k: v for k, v in json.loads(before[old_pos][3])[0].items() if k != "operands"})
        self.assertEqual(new[0][:3], before[old_pos][:3])  # same type, link and terms

    def test_each_constant_alone(self):
        for first, operand in ((True, False), (False, True), (False, False)):
            with constants(first=first, operand=operand):
                conds = self.build()
            pos, sum_ = self.sum_at(conds)
            self.assertEqual(pos, 0 if first else len(conds) - 3, (first, operand))
            self.assertEqual(sum_["operands"], ("500," if operand else "") + "10,11,12,13", (first, operand))
            self.assertEqual(sum_["equation"], "{10}{11}{12}{13}")      # the picker is never in it
            ids = [int(c["id"]) for c in conds]
            self.assertEqual(ids, sorted(ids), (first, operand))
        # no guard: the sum is rule 0 all the same, and last in the old shape
        self.assertEqual(self.sum_at(self.build(guard=False))[0], 0)
        with constants(first=False):
            conds = self.build(guard=False)
        self.assertEqual(self.sum_at(conds)[0], len(conds) - 1)

    def test_a_form_without_the_picker_is_unchanged_byte_for_byte(self):
        shapes = set()
        for first in (True, False):
            for operand in (True, False):
                with constants(first=first, operand=operand):
                    shapes.add(json.dumps(self.build(picker=None)))
        self.assertEqual(len(shapes), 1)                  # ids included: no constant touches it
        conds = json.loads(shapes.pop())
        pos, sum_ = self.sum_at(conds)
        self.assertEqual((pos, sum_["operands"]), (len(conds) - 1, "10,11,12,13"))

    def test_the_new_order_is_a_rewrite_of_one_rule(self):
        new = self.build()
        for first, operand, delta in ((False, False, (len(new) - 1, 1, 1)),   # moved and one operand more
                                      (True, False, (len(new) - 1, 1, 1)),    # the operand only
                                      (False, True, (len(new), 0, 0))):       # the order only
            with constants(first=first, operand=operand):
                old = self.build()
            live = [dict(c, terms=json.dumps(c["terms"]), action=json.dumps(c["action"])) for c in old]
            self.assertFalse(sync.same_conditions(live, new), (first, operand))   # order counts
            self.assertEqual(sync.rule_delta(live, new), delta, (first, operand))
        self.assertTrue(sync.same_conditions([dict(c, terms=json.dumps(c["terms"]),
                                                   action=json.dumps(c["action"])) for c in new], new))

    def test_glow_sync_reads_the_live_rules(self):
        rosters = set(self.ROSTERS)
        with constants(first=False, operand=False):
            old = self.build()
        new = self.build()
        self.assertEqual(glow_sync.contact_ids_stale(old, rosters, "500"), ["order", "operand"])
        self.assertEqual(glow_sync.contact_ids_stale(new, rosters, "500"), [])
        with constants(operand=False):
            self.assertEqual(glow_sync.contact_ids_stale(old, rosters, "500"), ["order"])
        with constants(first=False):
            self.assertEqual(glow_sync.contact_ids_stale(old, rosters, "500"), ["operand"])
        with constants(first=False, operand=False):
            self.assertEqual(glow_sync.contact_ids_stale(old, rosters, "500"), [])
        self.assertEqual(glow_sync.contact_ids_stale(old, rosters, None), [])     # no picker: nothing asked
        self.assertEqual(glow_sync.contact_ids_stale([], rosters, "500"), [])      # nothing to compare
        wire = [dict(c, terms=json.dumps(c["terms"]), action=json.dumps(c["action"])) for c in old]
        shape = glow_sync.contact_ids_layout(wire + [{"terms": "{broken"}], rosters)
        self.assertEqual((shape["position"], shape["count"], len(shape["roster_rules"])),
                         (len(old) - 3, len(old) + 1, 4))
        self.assertEqual(shape["roster_rule_fields"], {"500": 4, sync.PARTNER: 2})
        self.assertEqual(glow_sync.roster_required(), "Yes")
        with constants(required=False):
            self.assertEqual(glow_sync.roster_required(), "No")

    # ---- the sync on a fake form
    def form(self, built=(True, True, True), **kw):
        """SameNameFlow's switched form (ClubGuardFlow's with the guard), its rules and
        required flags as the sync generates them under `built` (first, operand, required)."""
        with constants(*built):
            return ClubGuardFlow.form(ClubGuardFlow(), **kw)

    def run_sync(self, fake, *extra, roster=None):
        return SameNameFlow.run_sync(self, fake, *extra, roster=roster)

    def summary(self, fake, *extra, **kw):
        return SameNameFlow.summary(self, fake, *extra, **kw)

    def test_old_rules_warn_and_plan_one_rewrite_then_nothing(self):
        for built, why in (((False, False, True), ("is rule ", "is not one of its operands")),
                           ((True, False, True), ("is not one of its operands",)),
                           ((False, True, True), ("is rule ",))):
            del sync.WARNINGS[:]
            qs, wire = self.form(built)
            fake = FakeForm(qs, wire)
            summary, out = self.summary(fake)
            self.assertEqual(fake.calls, [f"REPLACE conditions ({len(wire)} rules)"], built)
            (warning,) = sync.WARNINGS
            self.assertTrue(warning.startswith(f"  ! {sync.CONTACT_IDS_STALE}: "), warning)
            for fragment in why:
                self.assertIn(fragment, warning)
            self.assertEqual("is rule " in warning, not built[0], built)       # only what is stale
            self.assertEqual("operands" in warning, not built[1], built)
            self.assertIn('docs/RUNBOOK.md, "The names list sent to Salesforce"', warning)
            if built[1]:      # the order only: every rule is kept, one moves
                self.assertIn(f"conditions: {len(wire)} kept, 0 new, 0 dropped", out)
            else:
                self.assertIn(f"conditions: {len(wire) - 1} kept, 1 new, 1 dropped", out)
            plan = auto_sync.plan_from_summary(summary)
            self.assertEqual((auto_sync.changes(plan), len(auto_sync.contact_ids_stale(plan))), (0, 1))
        qs, wire = self.form((False, False, True))
        self.assertIn(f"is rule {len(wire) - 2} of {len(wire)}, after the rosters' rules",
                      self.run_sync(FakeForm(qs, wire))[1])
        # the hand apply writes the new rules; the next run has nothing to say
        fake = FakeForm(qs, wire, apply=True)
        self.assertEqual(self.run_sync(fake, "--apply")[0], 0)
        written = fake.writes[-1][2]["properties"]["conditions"]
        self.assertEqual(sync._norm_rules(written), sync._norm_rules(self.form()[1]))
        del sync.WARNINGS[:]
        fake = FakeForm(*self.form())
        self.assertEqual((self.run_sync(fake)[0], fake.calls, sync.WARNINGS), (0, [], []))

    def test_the_rollback_is_generated_by_the_constants(self):
        # the live form in the new shape; the constants off: the sync plans the old rules and
        # "No" on every roster, warns nothing, and the old form then needs nothing
        qs, wire = self.form()
        with constants(False, False, False):
            fake = FakeForm(qs, wire)
            summary, out = self.summary(fake)
            self.assertEqual(sync.WARNINGS, [])
            # the rules first, the flags last (a run that stops in the tail leaves no rule stale)
            self.assertEqual(fake.calls, [f"REPLACE conditions ({len(wire)} rules)"]
                             + [f"REQUIRED roster '{c}' (q{q}: No)" for q, c in
                                (("10", "Alpha Club"), ("11", "Stars"), ("12", "Stars"), ("13", "Beta Club"))])
            self.assertIn(f"conditions: {len(wire) - 1} kept, 1 new, 1 dropped", out)
            self.assertEqual(sync._norm_rules(fake.writes[0][2]["properties"]["conditions"]),
                             sync._norm_rules(self.form((False, False, False))[1]))
            self.assertEqual([r["required"] for r in summary["requires"]], ["No"] * 4)
            fake = FakeForm(*self.form((False, False, False)))
            self.assertEqual((self.run_sync(fake)[0], fake.calls), (0, []))
        # the rules alone (the required flag kept)
        with constants(False, False, True):
            fake = FakeForm(qs, wire)
            self.run_sync(fake)
            self.assertEqual(fake.calls, [f"REPLACE conditions ({len(wire)} rules)"])

    def test_a_form_without_the_picker_gets_no_warning_and_no_rewrite(self):
        for built in ((True, True, True), (False, False, True)):
            del sync.WARNINGS[:]
            with constants(*built):
                qs, wire = SameNameFlow.form(self, picker=False)
            fake = FakeForm(qs, wire)
            self.assertEqual((self.run_sync(fake)[0], fake.calls, sync.WARNINGS), (0, [], []), built)

    # ---- at least one girl: the required rosters
    def test_a_roster_without_the_flag_gets_it_alone_or_with_its_update(self):
        qs, wire = self.form()
        for q in self.ROSTERS:
            qs[q]["required"] = "No"
        del qs["13"]["required"]                         # absent reads as "No", as Jotform's default
        fake = FakeForm(qs, wire)
        summary, out = self.summary(fake)
        want = [f"REQUIRED roster '{c}' (q{q}: Yes)" for q, c in
                (("10", "Alpha Club"), ("11", "Stars"), ("12", "Stars"), ("13", "Beta Club"))]
        self.assertEqual(fake.calls, want)                # rules in step: no rewrite
        self.assertIn("(conditions unchanged - skipping the rewrite)", out)
        self.assertEqual({w[2]["question[required]"] for w in fake.writes}, {"Yes"})
        self.assertEqual([len(w[2]) for w in fake.writes], [1] * 4)        # the flag and nothing else
        for call in fake.calls:
            m = auto_sync.REQUIRED_RX.match("  - " + call)
            self.assertTrue(m, call)
            self.assertFalse(auto_sync.UPDATE_RX.match("  - " + call))
        self.assertEqual(summary["requires"], [{"qid": q, "club": c, "required": "Yes"} for q, c in
                                               (("10", "Alpha Club"), ("11", "Stars"), ("12", "Stars"),
                                                ("13", "Beta Club"))])
        plan = auto_sync.parse_plan(out)
        self.assertEqual((len(plan["requires"]), auto_sync.changes(plan)), (4, 4))
        self.assertEqual(auto_sync.plan_from_summary(summary)["requires"], plan["requires"])
        # a roster with an options update takes the flag in the same write
        sheet = {**ClubGuardFlow.ROSTER, ("Partner One", "Alpha Club"): ["Jane Doe", "Mary Roe", "Zoe Quillfeather"]}
        fake = FakeForm(qs, wire)
        summary, out = self.summary(fake, roster=sheet)
        self.assertEqual(fake.calls[0], "UPDATE roster 'Alpha Club' (q10, 3 girls; required: Yes)")
        self.assertEqual(fake.writes[0][2], {"question[options]": "Jane Doe|Mary Roe|Zoe Quillfeather",
                                             "question[required]": "Yes"})
        self.assertEqual(fake.calls[1:], [f"REPLACE conditions ({len(wire)} rules)"] + want[1:])   # flags last
        m = auto_sync.UPDATE_RX.match("  - " + fake.calls[0])
        self.assertEqual((m["club"], m["qid"], m["girls"], m["required"]), ("Alpha Club", "10", "3", "Yes"))
        self.assertEqual([r["qid"] for r in summary["requires"]], ["11", "12", "13"])
        # in step: an update writes its options only, with the line it always had
        qs, wire = self.form()
        fake = FakeForm(qs, wire)
        self.run_sync(fake, roster=sheet)
        self.assertEqual(fake.calls[0], "UPDATE roster 'Alpha Club' (q10, 3 girls)")
        self.assertEqual(fake.writes[0][2], {"question[options]": "Jane Doe|Mary Roe|Zoe Quillfeather"})
        self.assertFalse([c for c in fake.calls if c.startswith("REQUIRED")])

    def test_a_new_roster_is_created_required(self):
        sheet = {**ClubGuardFlow.ROSTER, **ClubGuardFlow.NEW_CLUB}
        for required in (True, False):
            with constants(required=required):
                fake = FakeForm(*self.form((True, True, required)))
                self.run_sync(fake, roster=sheet)
            label, (_, path, fields) = fake.calls[0], fake.writes[0]
            self.assertEqual((label, path), ("CREATE roster 'Gamma Club' (2 girls)", "/questions"))
            self.assertEqual(fields.get("question[required]"), "Yes" if required else None)
            self.assertEqual(fields["question[hidden]"], "Yes")
            self.assertEqual(set(fields) - {"question[required]"},
                             {"question[type]", "question[text]", "question[name]", "question[order]",
                              "question[hidden]", "question[options]"})       # otherwise today's payload
            self.assertFalse([c for c in fake.calls if c.startswith("REQUIRED")])

    # ---- the runner
    STALE_DRY_RUN = (
        "Roster: 4 active clubs in Africa (8 girls); 300 clubs overall\n"
        f"  ! {sync.CONTACT_IDS_STALE}: its calculation is rule 22 of 23, after the rosters' rules, so a "
        "change of club calculates it before the rosters show or hide; the Club picker (q500) is not "
        "one of its operands - the rewrite puts it right; apply this form by hand (docs/RUNBOOK.md, "
        "\"The names list sent to Salesforce\")\n"
        "  conditions: 22 kept, 1 new, 1 dropped\n"
        "\nDRY RUN (use --apply to write):\n"
        "  - REPLACE conditions (23 rules)\n")

    def run_region(self, text, apply=False, summary=None):
        return AutoSyncPlan.run_region(self, text, apply=apply, summary=summary)

    def test_the_runner_never_applies_a_region_whose_question_18_is_the_old_way(self):
        self.assertEqual(auto_sync.CONTACT_IDS_STALE, sync.CONTACT_IDS_STALE)
        plan = auto_sync.parse_plan(self.STALE_DRY_RUN)
        self.assertEqual((auto_sync.changes(plan), len(auto_sync.contact_ids_stale(plan))), (0, 1))
        (reason,) = auto_sync.check_bands(plan)
        self.assertIn("calculate question 18 (Contact_IDs, the names sent to Salesforce) the old way", reason)
        self.assertIn("by hand", reason)
        busy = self.STALE_DRY_RUN.replace("  - REPLACE", "  - CREATE roster 'Gamma Club' (2 girls)\n  - REPLACE")
        summary = {"creates": [], "updates": [], "deletes": [], "rules": 23, "calls": ["REPLACE conditions (23 rules)"],
                   "warnings": [l for l in self.STALE_DRY_RUN.splitlines() if l.startswith("  ! ")]}
        for text, apply, summ in ((self.STALE_DRY_RUN, False, None), (self.STALE_DRY_RUN, True, None),
                                  (busy, True, None), (self.STALE_DRY_RUN, True, summary)):
            run = self.run_region(text, apply=apply, summary=summ)
            self.assertEqual(run.synced, [False], text)               # never an apply: not even with a new club
            self.assertEqual([r[7] for r in run.results], ["attention"])
            self.assertIn("the old way", run.results[0][8])
            (title, detail), = run.attention
            self.assertIn("Africa: not applied", title)
            self.assertIn(sync.CONTACT_IDS_STALE, detail)
        # in step: a rules-only plan is in-sync as ever
        quiet = "\n".join(l for l in self.STALE_DRY_RUN.splitlines() if "! " not in l) + "\n"
        run = self.run_region(quiet)
        self.assertEqual(([r[7] for r in run.results], run.attention), (["in-sync"], []))

    def test_the_runner_writes_the_required_flag_only_with_a_change_it_already_makes(self):
        text = ("Roster: 4 active clubs in Africa (8 girls); 300 clubs overall\n"
                "\nDRY RUN (use --apply to write):\n"
                "  - UPDATE roster 'Alpha Club' (q10, 3 girls; required: Yes)\n"
                "  - CREATE roster 'Gamma Club' (2 girls)\n")
        plan = auto_sync.parse_plan(text)
        self.assertEqual([(u["qid"], u["girls"]) for u in plan["updates"]], [("10", 3)])
        self.assertEqual((plan["requires"], auto_sync.check_bands(plan)), ([], []))
        run = self.run_region(text, apply=True)
        self.assertEqual((run.synced, [r[7] for r in run.results]), ([False, True], ["applied"]))
        # one roster's flag on its own is never applied unattended - nor 200 of them
        for n in (1, 200):
            alone = text + "".join(f"  - REQUIRED roster 'Club {i}' (q{100 + i}: Yes)\n" for i in range(n))
            plan = auto_sync.parse_plan(alone)
            self.assertEqual(len(plan["requires"]), n)
            self.assertIn(f"required: Yes on {n} roster(s)", auto_sync.plan_summary(plan))
            (reason,) = auto_sync.check_bands(plan, max_updates=1000)
            self.assertIn(f"would write the required flag on {n} roster(s) that have no other change", reason)
            run = self.run_region(alone, apply=True)
            self.assertEqual((run.synced, [r[7] for r in run.results]), ([False], ["attention"]))
            self.assertIn(f"- REQUIRED on {n} roster(s) with no other change", run.attention[0][1])
            # …the rollback's "No" too
            plan = auto_sync.parse_plan(alone.replace(": Yes)", ": No)"))
            self.assertIn("required: No on", auto_sync.plan_summary(plan))
            self.assertEqual(len(auto_sync.check_bands(plan, max_updates=1000)), 1)
        # nothing else planned: never in-sync
        only = ("Roster: 4 active clubs in Africa (8 girls); 300 clubs overall\n\nDRY RUN (use --apply to "
                "write):\n  - REQUIRED roster 'Alpha Club' (q10: Yes)\n")
        run = self.run_region(only, apply=True)
        self.assertEqual((run.synced, [r[7] for r in run.results]), ([False], ["attention"]))

    # ---- form_status: every combination of the constants
    def audit(self, qs, wire):
        return form_status.audit_rules(qs, wire)[0]

    def test_the_audits_follow_the_constants_in_every_combination(self):
        import itertools
        expect = {  # (constant, expected value, built value) -> the problem a form shows
            (0, True): "is calculated by rule ",
            (1, True): "is not one of question 18's operands",
            (1, False): "Contact_IDs aggregate includes 1 non-roster question(s): ['500']",
            (2, True): "4 of 4 roster(s) not required (first q10)",
            (2, False): "4 of 4 roster(s) required (first q10) although glow/sync.py ROSTERS_REQUIRED is off",
        }
        for combo in itertools.product((True, False), repeat=3):
            qs, wire = self.form(combo)
            with constants(*combo):
                self.assertEqual(self.audit(qs, wire), [], combo)          # what the sync writes is clean
                for i in range(3):
                    flipped = list(combo)
                    flipped[i] = not combo[i]
                    found = self.audit(*self.form(tuple(flipped)))
                    fragment = expect.get((i, combo[i]))
                    if fragment is None:           # q18 first while the order is off: never harmful
                        self.assertEqual(found, [], (combo, i))
                        continue
                    self.assertEqual(len(found), 1, (combo, i, found))
                    self.assertIn(fragment, found[0], (combo, i))
            # the typed club name (no picker): nothing about the order or operand, ever
            with constants(*combo):
                typed = SameNameFlow.form(self, picker=False)
                self.assertEqual(self.audit(*typed), [], combo)

    def test_each_question_18_check_fires_on_its_broken_form(self):
        qs, wire = self.form()
        sum_rule = lambda c: '"resultField": "18"' in c["action"]          # noqa: E731

        def edit(**change):
            return FormStatusAudit.edit(wire, sum_rule, **change)

        def only(rules, fragment, n=1):
            found = self.audit(qs, rules)
            self.assertEqual(sum(fragment in p for p in found), n, found)
            return found

        only(edit(action=lambda c: c["action"].replace('"{10}{11}', '"{500}{10}{11}')),
             "question 18's equation is not one {qid} per roster: 5 field(s) for 4 roster(s), 1 not a roster")
        only(edit(action=lambda c: c["action"].replace('{10}{11}', '{10}, {11}')), ", text between them")
        only(edit(action=lambda c: c["action"].replace('{10}{11}', '{10}{10}{11}')), "1 twice")
        found = only(edit(action=lambda c: c["action"].replace('{10}{11}', '{11}')
                          .replace('"500,10,11', '"500,11')), "misses 1 roster(s): ['10']")
        self.assertTrue(any("3 field(s) for 4 roster(s)" in p for p in found), found)
        only(wire + [c for c in wire if sum_rule(c)], "2 rules calculate question 18 (Contact_IDs), expected 1")
        moved = wire[1:3] + wire[:1] + wire[3:]             # after two roster rules
        only(moved, "is calculated by rule 3 of")
        only(moved, "after 2 rule(s) that show a roster")
        # a roster rule on another field than the picker: question 18's rule must test it too
        gated = FormStatusAudit.edit(wire, lambda c: '"field": "10"' in c["action"],
                                     terms=lambda c: json.dumps(json.loads(c["terms"]) + [
                                         {"field": "94", "operator": "equals", "value": "1"}]))
        only(gated, "1 rule(s) that show a roster test q94, which question 18's rule does not test")
        with constants(first=False):                         # without the order: as an operand
            only(gated, "test q94, which question 18's rule does not list as an operand")
            only(FormStatusAudit.edit(gated, sum_rule, action=lambda c: c["action"].replace('"500,', '"500,94,')),
                 "test q94", n=0)
        only(FormStatusAudit.edit(gated, sum_rule, terms=lambda c: json.dumps(json.loads(c["terms"]) + [
            {"field": "94", "operator": "isFilled", "value": ""}])), "test q94", n=0)
        self.assertEqual(self.audit(qs, [c for c in wire if not sum_rule(c)]),
                         ["no Contact_IDs aggregate calculation found"])

    # ---- form_status --rendered
    def rendered(self, page, qs=None, select=True, **report):
        """form_status.rendered_problems on `page`, with the picker's <select> (its
        calcValues aligned) in front of it unless `select` is False."""
        qs = qs or self.form()[0]
        rosters = sorted((q for q, v in qs.items() if v.get("type") == "control_checkbox"), key=int)
        r = {"club_picker": "500", "picker_calc_values": True, "picker_options": 4,
             "roster_qids": rosters, **report}
        if select:
            page = ('<select name="q500_clubPicker[]" multiple="">'
                    + "".join(f'<option data-calcvalue="{o}" value="{o}">{o}</option>'
                              for o in qs["500"]["options"].split("|")) + "</select>\n" + page)
        return form_status.rendered_problems(r, page), r

    def test_the_served_page_is_read_for_the_order_the_operand_and_the_required_boxes(self):
        qs, wire = self.form()
        page = served_rules_and_rosters(qs, wire)
        problems, r = self.rendered(page, qs)
        self.assertEqual(problems, [])
        self.assertEqual(r["build"], "9e75d6f1d83")
        self.assertEqual(r["rendered_rules"], {"rules": len(wire), "position": 0, "roster_rules": 4,
                                               "first_roster_rule": 1, "operands": ["500", "10", "11", "12", "13"]})
        self.assertEqual(r["rendered_required"], {"rosters": 4, "required": 4, "boxes": 8, "boxes_required": 8})
        # the old rules served
        old_qs, old = self.form((False, False, True))
        problems, _ = self.rendered(served_rules_and_rosters(old_qs, old), qs)
        self.assertEqual(len(problems), 2, problems)
        self.assertIn(f"rendered page: question 18 is rule {len(old) - 2} of {len(old)} in JotForm.setConditions, "
                      "after the rosters' rules - the old order", problems[0])
        self.assertIn("does not list the Club picker (q500)", problems[1])
        # Jotform dropped the operand it was sent
        (problem,), _ = self.rendered(served_rules_and_rosters(qs, wire, operands="10,11,12,13"), qs)
        self.assertIn("question 18's entry in JotForm.setCalculations does not list the Club picker (q500)",
                      problem)
        # boxes without validate[required], and the other way round once the constant is off
        problems, _ = self.rendered(served_rules_and_rosters(qs, wire, required=False), qs)
        self.assertEqual(len(problems), 1)
        self.assertIn("4 of 4 rosters carry no validate[required] on their boxes", problems[0])
        with constants(required=False):
            self.assertEqual(self.rendered(served_rules_and_rosters(qs, wire, required=False), qs)[0], [])
            (problem,) = self.rendered(page, qs)[0]
            self.assertIn("4 rosters still carry validate[required] although", problem)
        # a page it cannot read is never vouched for
        problems, r = self.rendered("<html></html>", qs, select=False)
        self.assertEqual(r["build"], None)
        self.assertTrue(any("no Club picker select" in p for p in problems))
        self.assertTrue(any("no calculation of question 18 in JotForm.setConditions" in p for p in problems))
        self.assertTrue(any("shows boxes for 0 of the form's 4 rosters" in p for p in problems))
        # only the order and operand checks need the picker
        problems, _ = self.rendered(served_rules_and_rosters(old_qs, old), qs, club_picker=None)
        self.assertEqual(problems, [])
        # nothing it says carries a girl's name
        for name in ("Jane Doe", "Ann Poe", "Sue Moe", "Eve Hoe"):
            self.assertIn(name, page)
            self.assertNotIn(name, json.dumps(self.rendered(page.replace("validate[required]", ""), qs)))

    def test_the_served_page_follows_the_constants_in_every_combination(self):
        # a form rolled back (all off) or with the operand alone off (the RUNBOOK's fallback)
        # must pass the --rendered hard stop under the constants it was built with
        import itertools
        for combo in itertools.product((True, False), repeat=3):
            qs, wire = self.form(combo)
            with constants(*combo):
                self.assertEqual(self.rendered(served_rules_and_rosters(qs, wire, required=combo[2]), qs)[0],
                                 [], combo)
        # both arrays served, but no calculation of question 18 in them: never vouched for
        qs, wire = self.form()
        page = served_rules_and_rosters(qs, [c for c in wire if '"resultField": "18"' not in c["action"]])
        problems, r = self.rendered(page, qs)
        self.assertIsNone(r["rendered_rules"]["position"])
        self.assertEqual(problems, ["rendered page: no calculation of question 18 in JotForm.setConditions (page "
                                    "not served, or its layout changed) - the served order cannot be vouched for"])

    def test_the_page_helpers(self):
        self.assertEqual(form_status.page_array("x JotForm.setConditions(  [1, {\"a\": 2}]);", "setConditions"),
                         [1, {"a": 2}])
        self.assertIsNone(form_status.page_array("JotForm.setConditions({});", "setConditions"))
        self.assertIsNone(form_status.page_array("JotForm.setConditions([1,", "setConditions"))
        self.assertIsNone(form_status.page_array(None, "setConditions"))
        self.assertEqual(form_status.runtime_build('<script src="https://cdn.jotfor.ms/s/static/772a1982daf/js/x.js">'),
                         "772a1982daf")
        self.assertIsNone(form_status.runtime_build(""))
        # a box's attributes in any order; boxes of other questions are not counted
        page = ('<input required="" value="Ann Poe" class="form-checkbox validate[required]" id="input_10_0" '
                'type="checkbox"><input type="checkbox" class="form-checkbox" id="input_10_1">'
                '<input type="checkbox" class="form-checkbox validate[required]" id="input_99_0">'
                '<input type="text" class="validate[required]" id="input_11_0">')
        self.assertEqual(form_status.rendered_required(page, ["10", "11"]),
                         {"rosters": 1, "required": 1, "boxes": 2, "boxes_required": 1})
        # several validations in one class (the runtime's own join), and none that is "required"
        page = ('<input type="checkbox" class="form-checkbox validate[required,minSelection]" id="input_10_0">'
                '<input type="checkbox" class="form-checkbox validate[minSelection]" id="input_11_0">')
        self.assertEqual(form_status.rendered_required(page, ["10", "11"]),
                         {"rosters": 2, "required": 1, "boxes": 2, "boxes_required": 1})

    # ---- restore_conditions: the second rollback path says what follows
    def test_restoring_an_old_snapshot_says_the_form_will_read_not_clean(self):
        qs, wire = self.form()
        old = self.form((False, False, True))[1]
        note = restore_conditions.contact_ids_note(old, qs)
        self.assertIn("calculates question 18 (Contact_IDs) the old way (after the rosters' rules and without "
                      "the Club picker as an operand)", note)
        self.assertIn("the runner does not apply its region", note)
        self.assertIsNone(restore_conditions.contact_ids_note(wire, qs))
        with constants(first=False, operand=False):
            self.assertIsNone(restore_conditions.contact_ids_note(old, qs))
        code, out, puts = RestoreConditionsGuard.run_restore(self, old, qs, "--apply")
        self.assertEqual((code, len(puts)), (0, 1))
        self.assertIn("the old way", out)


def served_store(qs, extra=None):
    """A translation store as the forms hold one: an exact base/en entry (key = md5 of
    the text) for every roster option and module, a UI string translated in Spanish;
    extra: {key: (base text, en text)} added (a stale spelling, say)."""
    texts = [o for q in qs.values() if q.get("type") in ("control_checkbox", "control_dropdown")
             for o in (q.get("options") or "").split("|") if o] + ["Club Name"]
    store = {"base": {md5(t): t for t in texts}, "en": {md5(t): t for t in texts},
             "es": {md5("Club Name"): "Nombre del club"}}
    for k, (b, e) in (extra or {}).items():
        store["base"][k], store["en"][k] = b, e
    return store


def served_modules_and_store(qs, store=None, clear="disable"):
    """The module dropdowns' <select>s as Jotform serves a single-select (read from the U.S
    page 2026-10-02: a "Please Select" placeholder, then each option with a data-calcvalue
    when the question carries calcValues, the leading slot being the placeholder's), the
    runtime's clearFieldOnHide (JotForm.clearFieldOnHide="…", the template page 2026-10-06;
    None: no such line) and the store the page embeds (window.allTranslations,
    FormTranslation.init)."""
    import html as html_mod
    parts = [] if clear is None else [f'<script>JotForm.clearFieldOnHide="{clear}";</script>']
    for year, q in sync.MODULES.items():
        if q not in qs:
            continue
        options = [o for o in (qs[q].get("options") or "").split("|") if o]
        calc = (qs[q].get("calcValues") or "").split("|")
        parts.append(f'<select class="form-dropdown validate[required]" id="input_{q}" name="q{q}_module{year}" '
                     'data-component="dropdown"><option value="">Please Select</option>')
        for i, o in enumerate(options):
            cv = calc[i + 1] if i + 1 < len(calc) and calc[i + 1] else None
            attr = f' data-calcvalue="{html_mod.escape(cv)}"' if cv else ""
            parts.append(f'<option{attr} value="{html_mod.escape(o)}">{html_mod.escape(o)}</option>')
        parts.append("</select>")
    store = served_store(qs) if store is None else store
    parts.append('<script>window.allTranslations = {"acceptLanguage":null,"languages":{"English (US)":"en",'
                 '"Español":"es"},"translations":' + json.dumps(store) + "};\n"
                 'FormTranslation.init({"options":"English (US)|Español","primaryLanguage":"en","version":"2"});'
                 "</script>")
    return "\n".join(parts)


def served_rules_and_rosters(qs, wire, required=True, build="9e75d6f1d83", operands=None, store=None):
    """The parts of a public page that form_status --rendered reads besides the
    picker's <select>, shaped as Jotform serves them (read from the U.S page
    2026-10-01): the runtime script, every roster's boxes (validate[required]
    and required="" on each when `required`), JotForm.setConditions with the
    rules parsed, JotForm.setCalculations with each calculation's action and its
    conditionId; and (2026-10-02) the module dropdowns and the embedded store
    (served_modules_and_store; store: the one the page embeds, default a clean
    served_store). operands: replace question 18's operands as served (Jotform
    dropping one). Fictional names, as the fixtures'."""
    import html as html_mod
    parts = [f'<script src="https://cdn.jotfor.ms/s/static/{build}/static/jotform.forms.js"></script>',
             served_modules_and_store(qs, store)]
    for qid, q in sorted(qs.items(), key=lambda kv: int(kv[0])):
        if q.get("type") != "control_checkbox":
            continue
        cls = "form-checkbox validate[required]" if required else "form-checkbox"
        attr = ' required=""' if required else ""
        for i, name in enumerate(o for o in q.get("options", "").split("|") if o):
            parts.append(f'<input type="checkbox" class="{cls}" id="input_{qid}_{i}" name="q{qid}_club[]" '
                         f'value="{html_mod.escape(name)}"{attr} />')
    rules = [dict(c, terms=json.loads(c["terms"]) if isinstance(c["terms"], str) else c["terms"],
                  action=json.loads(c["action"]) if isinstance(c["action"], str) else c["action"])
             for c in wire]
    calcs = [dict(a, conditionId=c["id"], conditionTrue=False) for c in rules if c["type"] == "calculation"
             for a in c["action"]]
    if operands is not None:
        calcs = [dict(a, operands=operands) if a["resultField"] == sync.CONTACT_IDS else a for a in calcs]
    parts.append("<script>JotForm.setCalculations(" + json.dumps(calcs) + ");")
    parts.append("JotForm.setConditions(" + json.dumps(rules) + ");</script>")
    return "\n".join(parts)


class FormStatusAudit(unittest.TestCase):
    """tools/form_status.py audit_rules on forms built by the sync's own rules."""

    PARTNERS = {"stars": {"partner one": "Partner One", "partner two": "Partner Two"},
                "alpha club": {"partner one": "Partner One"},
                "beta club": {"partner two": "Partner Two"}}       # the Roster's, as load_partners gives

    def form(self, **kw):
        return SameNameFlow.form(SameNameFlow(), **kw)

    COVERAGE = ("2 rule(s) that show a roster test q331, which question 18's rule does not test: when "
                "q331 shows or hides a roster, question 18 is not recalculated")

    def test_the_typed_box_form_is_clean(self):
        # before --same-name-switch: two rosters test "Stars", told apart by the Partner box. Every
        # same-name rule passed - only question 18's rule does not test the box, so typing the
        # partner re-shows a roster without re-running it (none of the live forms is in this
        # state since 2026-09-30; flagged, not generated: docs/plans/2026-09-30-contact-ids.md)
        for partners in (None, self.PARTNERS):
            problems, summary = form_status.audit_rules(*self.form(), partners)
            self.assertEqual(len(problems), 1, problems)
            self.assertIn(self.COVERAGE, problems[0])
            self.assertEqual((summary["clubs"], summary["long_names"]), (4, 0))
        # in the shape before 2026-10 (both constants off) nothing is expected of question 18
        from unittest import mock
        with mock.patch.object(glow_sync, "CONTACT_IDS_FIRST", False), \
                mock.patch.object(glow_sync, "CONTACT_IDS_PICKER_OPERAND", False):
            self.assertEqual(form_status.audit_rules(*self.form())[0], [])

    SUMMARY = {"clubs": 4, "show_rules": 4, "aggregate_rosters": 4, "long_names": 2,
               "contact_ids_rule": 1, "contact_ids_picker_operand": True, "required_rosters": 4}

    def test_the_switched_form_is_clean(self):
        # each Stars tests its own long name: one roster per tested text, no Partner term
        qs, wire = self.form(switched=True)
        for partners in (None, self.PARTNERS):
            self.assertEqual(form_status.audit_rules(qs, wire, partners),
                             ([], dict(self.SUMMARY, rules=len(wire))))
        self.assertEqual(form_status.tested_values(qs, wire),
                         {"10": "Alpha Club", "11": "Stars - Partner One", "12": "Stars - Partner Two",
                          "13": "Beta Club"})

    def test_a_tested_text_must_be_the_rosters_own_or_its_long_name(self):
        def retest(wire, qid, old, new):
            return [dict(c, terms=c["terms"].replace(f'"{old}"', f'"{new}"'))
                    if f'"field": "{qid}"' in c["action"] else c for c in wire]

        # a long name whose partner the Roster does not have for that club
        qs, wire = self.form(switched=True)
        qs["500"]["options"] = qs["500"]["options"].replace("Stars - Partner Two", "Stars - Partner Nine")
        wire = retest(wire, "12", "Stars - Partner Two", "Stars - Partner Nine")
        self.assertEqual(form_status.audit_rules(qs, wire)[0], [])           # no Roster given: any partner
        problems = form_status.audit_rules(qs, wire, self.PARTNERS)[0]
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("'Stars' (q12): its rule tests 'Stars - Partner Nine', but the Roster has no "
                      "partner of that name with a club 'Stars'", problems[0])
        # another club's text, or the separator with nothing after it, is never a roster's own
        for value in ("Alpha Club", "Beta Club - ", "Beta Clubs - Partner Two"):
            qs, wire = self.form(switched=True)
            found = form_status.audit_rules(qs, retest(wire, "13", "Beta Club", value), self.PARTNERS)[0]
            self.assertTrue(any("'Beta Club' (q13): show-rule does not test the club field (q500) == its "
                                "text or its text + ' - ' + its partner" in p for p in found), (value, found))
        # without the picker the club name is typed: a long name is not accepted there
        qs, wire = self.form(picker=False)
        found = form_status.audit_rules(qs, retest(wire, "13", "Beta Club", "Beta Club - Partner Two"))[0]
        self.assertEqual(found, ["'Beta Club' (q13): show-rule does not test the club field (q5) == its text"])

    def test_rosters_are_grouped_by_the_text_they_test(self):
        # two rosters on one text with no Partner term: only one could ever show
        qs, wire = self.form(switched=True)
        same = [dict(c, terms=c["terms"].replace("Stars - Partner Two", "Stars - Partner One")) for c in wire]
        problems = form_status.audit_rules(qs, same)[0]
        self.assertEqual(sum("tests the same text as another roster ('Stars - Partner One') but its rule "
                             "has no Partner term" in p for p in problems), 2, problems)
        # a roster alone on its text must not ask for a partner
        qs, wire = self.form(switched=True)
        wire = [dict(c) for c in wire]
        for c in wire:
            if '"field": "10"' in c["action"]:
                c["terms"] = json.dumps([{"field": "331", "operator": "equals", "value": "Partner One"},
                                         {"field": "500", "operator": "equals", "value": "Alpha Club"}])
        problems = form_status.audit_rules(qs, wire)[0]
        self.assertEqual(problems[0], "'Alpha Club' (q10) is unique but its rule needs a Partner")
        self.assertEqual(len(problems), 2, problems)          # …and question 18 does not test q331
        self.assertIn(self.COVERAGE.replace("2 rule(s)", "1 rule(s)"), problems[1])

    def test_a_partner_list_left_on_a_form_is_a_problem(self):
        qs, wire = self.form(partner_list="Partner One|Partner Two", switched=True)
        problems = form_status.audit_rules(qs, wire)[0]
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("partner list (q600) on the form: the partner list was retired 2026-09-30", problems[0])

    def report(self, qs, wire, partners=None):
        class Fake:
            def get(self, path, **params):
                if path.endswith("/questions"):
                    return copy.deepcopy(qs)
                if path.endswith("/properties"):
                    return {"conditions": wire, "language": [{"options": "English (US)|Español"}],
                            "clearFieldOnHide": "disable"}
                return {"title": "t", "status": "ENABLED", "count": "0"}
        for q_id, q in qs.items():
            q.setdefault("qid", q_id)
        return form_status.form_report(glow_forms.TEMPLATE, Fake(), {}, partners)

    def picker_problems(self, rep):
        return [p for p in rep["rule_problems"] if p.startswith("club picker")]

    def test_the_pickers_options_are_the_texts_the_rules_test(self):
        for switched in (True, False):
            rep = self.report(*self.form(switched=switched), self.PARTNERS)
            self.assertEqual(self.picker_problems(rep), [], switched)
            self.assertEqual(rep["same_name_rosters"], 2 if switched else 0)
            # two questions named "Stars" are duplicates only while they share one picker entry
            self.assertEqual(rep["duplicate_club_questions"], [] if switched else ["Stars"])
        # the switched rules with the old options: both Stars are missing, "Stars" shows nothing
        qs, wire = self.form(switched=True)
        qs["500"]["options"] = "Alpha Club|Beta Club|Stars"
        self.assertEqual(self.picker_problems(self.report(qs, wire)),
                         ["club picker misses 1 club(s): ['Stars']",
                          "club picker lists 1 name(s) with no roster: ['Stars']"])
        # …and the other way round (a conditions backup restored over the switched picker)
        qs, wire = self.form(switched=True, rules_switched=False)
        self.assertEqual(self.picker_problems(self.report(qs, wire)),
                         ["club picker misses 1 club(s): ['Stars']",
                          "club picker lists 2 name(s) with no roster: ['Stars - Partner One', "
                          "'Stars - Partner Two']"])

    def test_the_report_says_how_many_long_names_and_what_the_partner_box_does(self):
        def lines(rep):
            return (rep["same_name_rosters"], form_status.partner_box_line(rep["partner_box"], rep["club_picker"]))

        self.assertEqual(lines(self.report(*self.form())),
                         (0, "q331 shown by 1 rule(s): rosters that share a text are told apart by the "
                             "typed partner"))
        self.assertEqual(lines(self.report(*self.form(switched=True))),
                         (2, "q331 hidden, no rule shows it"))
        self.assertEqual(lines(self.report(*self.form(switched=True, box_hidden="No"))),
                         (2, "q331 VISIBLE to every mentor, and no rule uses it - the next sync apply "
                             "hides it"))

    # ---- the Club picker's spelling and calcValues; the club guard
    def guard_form(self, **kw):
        return ClubGuardFlow.form(ClubGuardFlow(), **kw)

    @staticmethod
    def edit(wire, pred, **change):
        """wire with change(rule) applied to the rules pred(rule) selects."""
        return [dict(c, **{k: f(c) for k, f in change.items()}) if pred(c) else c for c in wire]

    def test_the_guard_form_is_clean(self):
        qs, wire = self.guard_form()
        self.assertEqual(form_status.audit_rules(qs, wire, self.PARTNERS),
                         ([], dict(self.SUMMARY, rules=len(wire))))
        qs, wire = self.guard_form(switched=False)                   # before the same-name switch
        problems = form_status.audit_rules(qs, wire, self.PARTNERS)[0]
        self.assertEqual(len(problems), 1, problems)                 # only the Partner box's rules
        self.assertIn(self.COVERAGE, problems[0])
        qs, wire = self.guard_form(guard=False, calc=False)          # before the guard's rollout: clean too
        self.assertEqual(form_status.audit_rules(qs, wire)[0], [])

    def test_a_picker_term_spelled_unlike_its_option_never_fires(self):
        # Africa's SUPER GIRLS (read 2026-09-29): the rule tests "SUPER GIRLS", the picker offers
        # "Super Girls", and a multi-select's equals is case-sensitive - a long name too
        for switched, old, new in ((False, "Stars", "STARS"),
                                   (True, "Stars - Partner One", "Stars - PARTNER ONE")):
            qs, wire = self.guard_form(guard=False, calc=False, switched=switched)
            wire = self.edit(wire, lambda c: '"field": "11"' in c["action"],
                             terms=lambda c: c["terms"].replace(f'"{old}"', f'"{new}"'))
            # (before the switch question 18's rule does not test the Partner box: one more line)
            problems = [p for p in form_status.audit_rules(qs, wire, self.PARTNERS)[0] if self.COVERAGE not in p]
            self.assertEqual(len(problems), 1, problems)
            self.assertIn(f"equals '{new}', which is not one of its options (it has '{old}'", problems[0])
            qs["500"]["multipleSelections"] = "No"      # a single-select compares without case
            self.assertEqual([p for p in form_status.audit_rules(qs, wire, self.PARTNERS)[0]
                              if self.COVERAGE not in p], [])

    def test_calc_values_must_be_the_options_in_order(self):
        for guard in (True, False):                  # checked whenever the picker carries them
            qs, wire = self.guard_form(guard=guard)
            qs["500"]["calcValues"] = ClubGuardFlow.CALC.replace("|Alpha Club|Beta Club", "|Beta Club|Alpha Club")
            problems = form_status.audit_rules(qs, wire)[0]
            self.assertEqual(len(problems), 1, problems)
            self.assertIn("calcValues are not its 4 options in order", problems[0])
        qs, wire = self.guard_form()
        del qs["500"]["calcValues"]                  # the guard needs them
        self.assertTrue(any("calcValues" in p for p in form_status.audit_rules(qs, wire)[0]))

    def test_each_guard_check_fires_on_its_broken_form(self):
        def problems(qs, wire):
            return form_status.audit_rules(qs, wire)[0]

        def only(qs, wire, fragment, n=1):
            found = problems(qs, wire)
            self.assertEqual(sum(fragment in p for p in found), n, found)
            return found

        shows_guard = lambda c: '"Show", "isError": false, "field": "700"' in c["action"]   # noqa: E731
        requires = lambda c: c["type"] == "require"                                        # noqa: E731
        qs, wire = self.guard_form()
        qs["700"]["hidden"] = "No"
        only(qs, wire, "is not hidden: every mentor sees the warning")
        qs, wire = self.guard_form()
        qs["700"]["text"] = "<p>edited by hand</p>"
        only(qs, wire, "text is not glow.sync.guard_html()")
        qs, wire = self.guard_form()
        qs["700"]["type"] = "control_textbox"
        only(qs, wire, "is a control_textbox, not a text element")
        qs, wire = self.guard_form()
        qs["701"] = dict(qs["700"])
        only(qs, wire, "2 elements are named 'clubGuard' (q700, q701)")
        qs, wire = self.guard_form()
        del qs["500"]
        self.assertIn("club guard (q700) but no Club picker: nothing can show it", problems(qs, wire))
        qs, wire = self.guard_form()
        qs["700"]["order"] = "2"                     # above the picker (order 3)
        only(qs, wire, "renders above the Club picker (q500)")
        qs, wire = self.guard_form()
        qs["700"]["order"] = "20"                    # below the year and module dropdowns
        only(qs, wire, "is not directly below the Club picker (q500)")
        qs, wire = self.guard_form()
        qs["3"] = dict(qs["2"])
        only(qs, wire, "2 Submit buttons, expected 1")
        # the rules: one missing, one doubled, the wrong link, a club left out, a stray value
        qs, wire = self.guard_form()
        only(qs, [c for c in wire if not shows_guard(c)], "0 rule(s) show the club guard, expected 1")
        only(qs, [c for c in wire if not requires(c)], "0 rule(s) disable Submit, expected 1")
        only(qs, wire + [c for c in wire if requires(c)], "2 rule(s) disable Submit, expected 1")
        only(qs, self.edit(wire, shows_guard, link=lambda c: "Any"), "linking its terms with Any")
        only(qs, self.edit(wire, shows_guard, action=lambda c: c["action"].replace('"Hide"', '"Show"')),
             "its actions are not Hide q2 + Show q700")
        drop = lambda c: json.dumps([t for t in json.loads(c["terms"]) if t["value"] != "Beta Club"])  # noqa: E731
        only(qs, self.edit(wire, lambda c: shows_guard(c) or requires(c), terms=drop),
             "misses 1 club(s) - their mentors cannot submit: ['Beta Club']", n=2)
        add = lambda c: json.dumps(json.loads(c["terms"]) + [{"field": "5", "operator": "notEquals",  # noqa: E731
                                                               "value": "Old Club"}])
        only(qs, self.edit(wire, requires, terms=add), "tests 1 value(s) that are not the picker's options")
        filled = lambda c: json.dumps([t for t in json.loads(c["terms"]) if t["operator"] != "isFilled"])  # noqa: E731
        only(qs, self.edit(wire, requires, terms=filled), "does not test that the Club picker is filled")

    def test_rendered_calc_values_are_counted_never_printed(self):
        page = ('<select id="input_500" name="q500_clubPicker[]" multiple="">'
                '<option data-calcvalue="Alpha Club" value="Alpha Club">Alpha Club</option>'
                '<option value="Beta &amp; Co" data-calcvalue="Beta &amp; Co">Beta &amp; Co</option>'
                '<option data-calcvalue="Alpha Club" value="Stars">Stars</option>'
                '<option value="Moon">Moon</option></select>'
                '<select name="q15_week8"><option value="">Please Select</option>'
                '<option data-calcvalue="1" value="Session 1">Session 1</option></select>')
        self.assertEqual(form_status.rendered_calc_values(page, "500"),
                         {"options": 4, "aligned": 2, "differ": 1, "missing": 1})
        placeholder = page.replace('multiple="">', 'multiple=""><option value="">Please Select</option>')
        self.assertEqual(form_status.rendered_calc_values(placeholder, "500")["options"], 4)
        self.assertIsNone(form_status.rendered_calc_values(page, "444"))
        self.assertIsNone(form_status.rendered_calc_values("", "500"))

    def test_the_report_names_the_guard_and_the_rendered_check(self):
        import contextlib
        import io
        import tempfile
        from unittest import mock
        from glow import forms as glow_forms
        qs, wire = self.guard_form()
        for q_id, q in qs.items():
            q.setdefault("qid", q_id)

        storage = {"/user/usage": {"uploads": "1340458410", "submissions": "474", "total_submissions": "690",
                                   "monthly_usage_reset_date": "2026-10-21 00:00:00", "form_count": "5"},
                   "/user": {"account_type": "https://api.jotform.com/system/plan/SILVER"},
                   "/system/plan/SILVER": {"name": "SILVER", "limits": {"uploads": 10738466816, "submissions": 2500}}}

        class Fake:
            def get(self, path, **params):
                if path.endswith("/questions"):
                    return copy.deepcopy(qs)
                if path.endswith("/properties"):
                    return {"conditions": wire, "language": [{"options": "English (US)|Español"}],
                            "clearFieldOnHide": "disable"}
                if path in storage:
                    return copy.deepcopy(storage[path])
                return {"title": "t", "status": "ENABLED", "count": "0"}

        select = ('<select name="q500_clubPicker[]" multiple="">'
                  + "".join(f'<option data-calcvalue="{o}" value="{o}">{o}</option>'
                            for o in ClubGuardFlow.OPTIONS) + "</select>")
        aligned = select + "\n<!--rest-->"
        shifted = aligned.replace('data-calcvalue="Beta Club"', 'data-calcvalue="Alpha Club"')

        def report(roster, *extra, page=None):
            # the rules and rosters the page serves follow the form as it is at the call
            served = None if page is None else page.replace("<!--rest-->", served_rules_and_rosters(qs, wire))
            out = io.StringIO()
            with mock.patch.object(form_status, "Client", lambda key: Fake()), \
                    mock.patch.object(form_status, "public_page", lambda fid: served), \
                    mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}), \
                    mock.patch.object(sys, "argv", ["form_status.py", "--form", glow_forms.TEMPLATE,
                                                    "--roster", roster, *extra]), \
                    contextlib.redirect_stdout(out):
                form_status.main()
            return out.getvalue()

        with tempfile.TemporaryDirectory() as tmp:
            roster = os.path.join(tmp, "roster.csv")
            with open(roster, "w", encoding="utf-8") as f:
                f.write("partner,club,full_name,status,region\n")
                for (partner, club), names in ClubGuardFlow.ROSTER.items():
                    f.write(f"{partner},{club},{names[0]},active,Africa\n")
            good, bad = report(roster, "--rendered", page=aligned), report(roster, "--rendered", page=shifted)
            self.assertIn("club guard: q700 (4 clubs)", good)
            self.assertIn("rendered picker: 4 options, 4 with data-calcvalue = value, 0 different, "
                          "0 without", good)
            self.assertIn("same-name clubs: 2 rosters send '<club> - <partner>'", good)
            self.assertIn("partner box: q331 hidden, no rule shows it", good)
            self.assertIn(f"question 18: rule 1 of {len(wire)}, the Club picker an operand: yes   "
                          "rosters required: 4 of 4", good)
            self.assertIn("runtime build: 9e75d6f1d83", good)
            self.assertIn(f"rendered rules: question 18 is rule 1 of {len(wire)}, the first roster rule 2; "
                          "its operands list the picker: yes", good)
            self.assertIn("rendered rosters: 4 with boxes, 4 with validate[required] (8 of 8 boxes)", good)
            self.assertIn("rendered shape: clearFieldOnHide disable, module selects served multiple: none", good)
            self.assertIn("module shape: year q94 single-select required; modules q14/q92/q93 single-select "
                          "required; sessions q15/q95/q96/q97 single-select required; clearFieldOnHide disable", good)
            self.assertIn("→ CLEAN", good)
            for name in ("Jane Doe", "Ann Poe", "Sue Moe"):         # counts only, never a girl
                self.assertNotIn(name, good)
            # the storage line right after the Roster line (never a form problem), and in --json
            self.assertIn("clubs per region\nstorage: upload space 1.25 GiB of 10.00 GiB (12.5%) -> ok; submissions "
                          "this cycle 474 of 2,500 (19.0%, resets 2026-10-21) -> ok; plan SILVER\n", good)
            (rep,) = json.loads(report(roster, "--json"))
            self.assertEqual(rep["storage"]["levels"], {"uploads": "ok", "submissions": "ok"})
            self.assertEqual((rep["storage"]["plan"], rep["storage"]["reset"]), ("SILVER", "2026-10-21"))
            self.assertEqual(rep["rule_problems"], [])                    # not one of them
            storage["/user/usage"]["uploads"] = str(10738466816 * 9 // 10)
            out = report(roster)
            self.assertIn("\n!! storage: upload space 9.00 GiB of 10.00 GiB (90.0%) -> alarm;", out)
            self.assertIn("→ CLEAN", out)                                 # account-wide: no form turns NOT CLEAN
            del storage["/user"]["account_type"]
            out = report(roster)
            self.assertIn("\nstorage: could not be read (GET /user: no account_type", out)
            self.assertIn("→ CLEAN", out)
            self.assertIn("error", json.loads(report(roster, "--json"))[0]["storage"])
            storage["/user"]["account_type"] = "https://api.jotform.com/system/plan/SILVER"
            self.assertIn("rendered picker: 4 options, 3 with data-calcvalue = value, 1 different", bad)
            self.assertIn("would send another club's name", bad)
            self.assertNotIn("CLEAN", bad)
            self.assertNotIn("rendered picker", report(roster))          # only with --rendered
            # the hard stop never passes on a page it could not read in full: no
            # options, only a placeholder, attributes it does not parse, a subset
            empty = '<select name="q500_clubPicker[]" multiple=""></select>'
            unread = {"empty": empty,
                      "placeholder": empty.replace('""></select>', '""><option value="">…</option></select>'),
                      "single quotes": aligned.replace('"', "'").replace("name='q500_clubPicker[]'",
                                                                         'name="q500_clubPicker[]"'),
                      "one of four": empty.replace("</select>", '<option data-calcvalue="Alpha Club" '
                                                                'value="Alpha Club">Alpha Club</option></select>')}
            for what, page in unread.items():
                out = report(roster, "--rendered", page=page)
                n = 1 if what == "one of four" else 0
                self.assertIn(f"rendered page lists {n} of the picker's 4 options", out, what)
                self.assertNotIn("CLEAN", out, what)
            # a long name is checked against the Roster given: without Partner Two's Stars in it,
            # "Stars - Partner Two" is not a name the sync would write
            other = os.path.join(tmp, "other.csv")
            with open(other, "w", encoding="utf-8") as f:
                f.write("partner,club,full_name,status,region\nPartner One,Stars,Ann Poe,inactive,Asia\n")
            out = report(other)
            self.assertIn("its rule tests 'Stars - Partner Two', but the Roster has no partner of that name",
                          out)
            self.assertNotIn("'Stars - Partner One'", out)          # any status, any region counts
            self.assertNotIn("CLEAN", out)
            del qs["700"]
            wire[:] = self.guard_form(guard=False)[1]
            self.assertIn("club guard: none (a mentor can pick several clubs)", report(roster))
            # before the rollout (no calcValues on the picker) the count is only printed
            del qs["500"]["calcValues"]
            out = report(roster, "--rendered", page=empty + "\n<!--rest-->")
            self.assertIn("rendered picker: 0 options", out)
            self.assertIn("→ CLEAN", out)


class RestoreConditionsGuard(unittest.TestCase):
    """restore_conditions.py: a snapshot whose rules test clubs the Club picker no
    longer offers is refused - restored, those clubs' rosters never show and the
    club guard blocks their mentors (every backup from before a form's
    --same-name-switch is one)."""

    def test_stale_club_terms(self):
        stale = restore_conditions.stale_club_terms
        before, after = ClubGuardFlow.form(ClubGuardFlow(), switched=False), ClubGuardFlow.form(ClubGuardFlow())
        self.assertEqual(stale(after[1], after[0]), [])
        self.assertEqual(stale(before[1], before[0]), [])
        # the pre-switch rules on the switched form: "Stars" in two roster rules, the Partner-box
        # rule and both guard rules - named once
        self.assertEqual(stale(before[1], after[0]), ["Stars"])
        # …and the other way round (the switched rules over a picker taken back by hand)
        self.assertEqual(stale(after[1], before[0]), ["Stars - Partner One", "Stars - Partner Two"])
        # the guard's list alone is enough (the roster rules dropped)
        guard_only = [c for c in before[1] if c["type"] == "require"]
        self.assertEqual(stale(guard_only, after[0]), ["Stars"])
        # …and so are the roster rules alone: a snapshot from before the guard existed (and
        # before the switch) has no guard list, only "Club picker equals Stars"
        unguarded = SameNameFlow.form(SameNameFlow(), switched=False)[1]
        self.assertFalse([c for c in unguarded if c["type"] == "require"])
        self.assertEqual(stale(unguarded, after[0]), ["Stars"])
        # a multi-select compares case: another spelling is not the option
        respelt = [dict(c, terms=c["terms"].replace('"Alpha Club"', '"ALPHA CLUB"')) for c in after[1]]
        self.assertEqual(stale(respelt, after[0]), ["ALPHA CLUB"])
        # a snapshot taken before a club was ADDED still fits; parsed or wire terms alike
        older = ClubGuardFlow.form(ClubGuardFlow(), roster={k: v for k, v in ClubGuardFlow.ROSTER.items()
                                                            if k[1] != "Beta Club"})
        self.assertEqual(stale(older[1], after[0]), [])
        self.assertEqual(stale([dict(c, terms=json.loads(c["terms"])) for c in before[1]], after[0]), ["Stars"])
        # without the Club picker nothing is checked (mentors type the club name)
        typed = SameNameFlow.form(SameNameFlow(), picker=False)
        self.assertEqual(stale(before[1], typed[0]), [])

    def run_restore(self, snapshot, questions, *extra):
        import contextlib
        import io
        import tempfile
        from unittest import mock
        puts = []

        class Fake:
            def __init__(self, key, apply=False):
                pass

            def get(self, path):
                if path.endswith("/questions"):
                    return copy.deepcopy(questions)
                return {"conditions": puts[-1] if puts else [{"id": "live"}]}

            def put_json(self, path, payload, label):
                puts.append(payload["properties"]["conditions"])

        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "backups", "999"))
            with open(os.path.join(tmp, "backups", "999", "properties-latest.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"conditions": snapshot}, f)
            with mock.patch.object(restore_conditions, "REPO", tmp), \
                    mock.patch.object(restore_conditions, "Client", Fake), \
                    mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}), \
                    mock.patch.object(sys, "argv", ["restore_conditions.py", "--form", "999", *extra]), \
                    contextlib.redirect_stdout(out):
                try:
                    restore_conditions.main()
                    code = 0
                except SystemExit as e:
                    code = e.code
        return code, out.getvalue(), puts

    def test_a_snapshot_from_before_the_switch_is_refused_unless_forced(self):
        before, after = ClubGuardFlow.form(ClubGuardFlow(), switched=False), ClubGuardFlow.form(ClubGuardFlow())
        for extra in ((), ("--apply",)):                       # the dry run says so too
            code, _, puts = self.run_restore(before[1], after[0], *extra)
            self.assertIn("Refusing: the snapshot's rules test 1 club name(s) the Club picker does not "
                          "offer today ('Stars')", str(code))
            self.assertIn("--force", str(code))
            self.assertEqual(puts, [])
        code, out, puts = self.run_restore(before[1], after[0], "--apply", "--force")
        self.assertEqual((code, puts), (0, [before[1]]))
        self.assertIn("! --force:", out)
        self.assertIn("Run the sync (dry run, then --apply) straight after", out)
        # a snapshot that fits is restored as ever
        code, out, puts = self.run_restore(after[1], after[0], "--apply")
        self.assertEqual((code, puts), (0, [after[1]]))
        self.assertIn("matches snapshot", out)
        code, out, puts = self.run_restore(after[1], after[0])
        self.assertEqual((code, puts), (0, []))
        self.assertIn("DRY RUN", out)


class FormStatusLayout(unittest.TestCase):
    """tools/form_status.py: the layout audit joins rule_problems (CLEAN needs
    none, and the runner's verify_report sees a relapse)."""

    class Client:
        def __init__(self, qs):
            self.qs = qs

        def get(self, path, **params):
            if path.endswith("/properties"):
                return {"conditions": [], "language": [{"options": "English|Español"}],
                        "integrations": {"salesforceV2": {"on": 1}}, "clearFieldOnHide": "disable"}
            if path.endswith("/questions"):
                return copy.deepcopy(self.qs)
            return {"title": "Attendance Form (Template)", "status": "ENABLED", "count": "0"}

    def report(self, qs):
        return form_status.form_report(glow_forms.TEMPLATE, self.Client(qs), {})

    def layout_problems(self, rep):
        return [p for p in rep["rule_problems"] if "fix_roster_order" in p or "Submit" in p]

    def test_a_roster_below_the_links_is_a_problem_until_the_repair(self):
        rep = self.report(link_form())
        self.assertEqual(self.layout_problems(rep), layout.audit_layout(link_form()))
        self.assertEqual(len(self.layout_problems(rep)), 1)
        self.assertEqual(rep["layout"]["rosters_below"], 1)
        self.assertEqual(form_status.layout_line(rep["layout"]),
                         "1 of 2 rosters render below somethingNotWorking (q443) (first q400) - "
                         "run tools/fix_roster_order.py (dry run first)")
        clean = dict(rep, rule_problems=self.layout_problems(rep), languages=["a"] * 12,
                     region_check={"missing_from_form": [], "not_in_roster": [], "rosters_out_of_date": []})
        problems, _ = auto_sync.verify_report(clean)
        self.assertEqual(len(problems), 1)
        self.assertIn("fix_roster_order", problems[0])
        repaired = move_all(link_form(), layout.plan_tail_moves(link_form()))
        rep = self.report(repaired)
        self.assertEqual(self.layout_problems(rep), [])
        self.assertEqual(form_status.layout_line(rep["layout"]),
                         "every roster above somethingNotWorking (q443)")
        self.assertEqual(auto_sync.verify_report(dict(clean, rule_problems=[]))[0], [])

    def test_the_rule_audit_is_unchanged(self):
        # audit_rules still knows nothing of the layout (its fixtures have no Submit)
        qs, wire = SameNameFlow.form(SameNameFlow(), switched=True)
        self.assertEqual(form_status.audit_rules(qs, wire)[0], [])
        self.assertEqual(layout.audit_layout(qs), ["0 Submit buttons, expected 1"])
        self.assertEqual(form_status.layout_line(layout.summary(qs)), "0 Submit button(s), no link")

    def test_two_submit_buttons_are_not_reported_as_no_link(self):
        qs = link_form(roster=True)                   # two links on it
        qs["471"] = {"qid": "471", "type": "control_button", "name": "b2", "order": "30"}
        rep = self.report(qs)
        self.assertIn("2 Submit buttons, expected 1", rep["rule_problems"])
        line = form_status.layout_line(rep["layout"])
        self.assertNotIn("no link", line)
        self.assertEqual(line, "2 Submit buttons, expected 1 - rosters not checked")


class TranslationAudit(unittest.TestCase):
    """tools/add_translations.py: what counts as a string a mentor sees."""

    def test_partner_names_are_not_strings_to_translate(self):
        import add_translations
        qs, _ = SameNameFlow.form(SameNameFlow(), partner_list="Partner One|Partner Two")
        strings = add_translations.visible_strings(qs)
        # the list's label is (already translated everywhere); its options stay English,
        # so adding the list does not grow the audit's "untranslated" count
        self.assertEqual(strings["Partner"], {"q331.text", "q600.text"})
        self.assertNotIn("Partner One", strings)
        self.assertNotIn("Partner Two", strings)
        # other dropdowns' options are still counted (the module names are translated)
        self.assertEqual(strings["Core 1"], {f"q{sync.MODULES['1']}.option"})

class GlowClient(unittest.TestCase):
    """The dry-run gate and call shapes of glow.jotform.Client (no network)."""

    def setUp(self):
        import glow.jotform as gj
        self.gj = gj
        self.spawned = []
        self.bodies = []

    def fake(self, outputs):
        """subprocess.run replacement yielding the given stdout strings in order."""
        import subprocess as sp

        def runner(argv, capture_output=True, text=True, **kw):
            self.spawned.append(argv)
            self.bodies.append(kw.get("input"))
            out = outputs[min(len(self.spawned) - 1, len(outputs) - 1)]
            return sp.CompletedProcess(argv, 0, stdout=out, stderr="")
        return runner

    def ok(self, content=None):
        return json.dumps({"responseCode": 200, "content": content if content is not None else {"x": 1}})

    def test_writes_are_recorded_and_skipped_without_apply(self):
        from unittest import mock
        c = self.gj.Client("KEY")
        with mock.patch.object(self.gj.subprocess, "run", self.fake([self.ok()])):
            self.assertIsNone(c.post_form("/form/1/questions", {"a": "b"}, "CREATE x"))
            self.assertIsNone(c.put_json("/form/1/properties", {}, "REPLACE y"))
            self.assertIsNone(c.delete("/form/1/question/2", "DELETE z"))
            self.assertEqual(c.get("/form/1/questions"), {"x": 1})
        self.assertEqual(c.calls, ["CREATE x", "REPLACE y", "DELETE z"])
        self.assertEqual(len(self.spawned), 1)          # only the GET ran

    def test_apply_runs_writes_and_still_records_them(self):
        from unittest import mock
        c = self.gj.Client("KEY", apply=True)
        with mock.patch.object(self.gj.subprocess, "run", self.fake([self.ok()])):
            self.assertEqual(c.post_form("/form/1/questions", {"a": "b"}, "CREATE x"), {"x": 1})
        self.assertEqual(c.calls, ["CREATE x"])
        argv = self.spawned[0]
        self.assertEqual(argv[:2], ["curl", "-sS"])
        self.assertIn("--data-urlencode", argv)
        self.assertIn("a=b", argv)
        self.assertEqual(argv.count("https://api.jotform.com/form/1/questions?apiKey=KEY"), 1)

    def test_url_params_and_max_time(self):
        from unittest import mock
        c = self.gj.Client("KEY", max_time=150)
        self.assertEqual(c.url("/form/1/questions", limit=1000),
                         "https://api.jotform.com/form/1/questions?apiKey=KEY&limit=1000")
        with mock.patch.object(self.gj.subprocess, "run", self.fake([self.ok()])):
            c.get("/form/1/questions", limit=1000)
        self.assertIn("--max-time", self.spawned[0])

    def test_retry_then_success_then_give_up(self):
        from unittest import mock
        naps = []
        c = self.gj.Client("KEY", retries=3, backoff=1, sleep=naps.append)
        with mock.patch.object(self.gj.subprocess, "run",
                               self.fake(["<html>504</html>", "<html>504</html>", self.ok()])):
            self.assertEqual(c.get("/x"), {"x": 1})
        self.assertEqual((len(self.spawned), naps), (3, [1, 1]))
        self.spawned.clear()
        c1 = self.gj.Client("KEY")                       # default: one attempt
        with mock.patch.object(self.gj.subprocess, "run", self.fake(["nope"])):
            with self.assertRaises(self.gj.JotformError):
                c1.get("/x")
            self.assertIsNone(c1.call([c1.url("/x")], "GET /x", allow_fail=True))

    def test_a_json_body_goes_on_standard_input_never_as_an_argument(self):
        # Linux refuses one argument over 131,072 bytes; Africa's rules are about 153 KB
        from unittest import mock
        rules = [{"id": str(i), "terms": "x" * 900} for i in range(250)]       # > 200 KB as JSON
        payload = {"properties": {"conditions": rules}}
        self.assertGreater(len(json.dumps(payload)), 200_000)
        c = self.gj.Client("KEY", apply=True)
        with mock.patch.object(self.gj.subprocess, "run", self.fake([self.ok()])):
            self.assertEqual(c.put_json("/form/1/properties", payload, "REPLACE conditions"), {"x": 1})
            self.assertEqual(c.post_json("/form/1/translations", payload, "POST translations"), {"x": 1})
            c.get("/form/1/questions")
        for argv, body in zip(self.spawned[:2], self.bodies[:2]):
            self.assertEqual(argv[argv.index("--data-binary") + 1], "@-")
            self.assertEqual(json.loads(body), payload)
            self.assertLess(max(len(a.encode()) for a in argv), 131_072)
            self.assertTrue(self.gj.is_write(argv[2:]))
        self.assertIsNone(self.bodies[2])                        # a GET sends nothing
        self.assertEqual(c.calls, ["REPLACE conditions", "POST translations"])

    def test_a_retry_sends_the_body_again(self):
        from unittest import mock
        c = self.gj.Client("KEY", apply=True, retries=3, backoff=0, sleep=lambda s: None)
        with mock.patch.object(self.gj.subprocess, "run",
                               self.fake(["<html>504</html>", "<html>504</html>", self.ok()])):
            self.assertEqual(c.put_json("/form/1/properties", {"a": "é"}, "REPLACE y"), {"x": 1})
        self.assertEqual(self.bodies, [json.dumps({"a": "é"})] * 3)

    def test_an_argument_too_large_for_a_command_line_is_refused_not_tried(self):
        from unittest import mock
        c = self.gj.Client("KEY", apply=True)
        with mock.patch.object(self.gj.subprocess, "run", self.fake([self.ok()])):
            with self.assertRaises(self.gj.JotformError) as e:
                c.post_form("/form/1/question/5", {"question[options]": "n" * 130_000}, "UPDATE q5")
            self.assertIn("cannot go on a command line", str(e.exception))
            self.assertNotIn("nnnn", str(e.exception))
            self.assertEqual(self.spawned, [])                   # curl was never started
            dry = self.gj.Client("KEY")                          # a dry run refuses it as well
            with self.assertRaises(self.gj.JotformError):
                dry.post_form("/form/1/question/5", {"question[options]": "n" * 130_000}, "UPDATE q5")
            self.assertEqual((dry.calls, self.spawned), ([], []))
            self.assertEqual(c.post_form("/form/1/question/5", {"question[options]": "n" * 90_000},
                                         "UPDATE q5"), {"x": 1})

    def test_a_curl_that_cannot_start_is_a_clean_error(self):
        from unittest import mock

        def boom(argv, **kw):
            raise OSError(7, "Argument list too long")
        c = self.gj.Client("KEY")
        with mock.patch.object(self.gj.subprocess, "run", boom):
            with self.assertRaises(self.gj.JotformError) as e:
                c.get("/x")
        self.assertIn("curl could not be started", str(e.exception))

    def test_is_write_catches_every_shape(self):
        w = self.gj.is_write
        self.assertTrue(w(["-X", "POST", "u"]))
        self.assertTrue(w(["-X", "DELETE", "u"]))
        self.assertTrue(w(["u", "--data-binary", "{}"]))
        self.assertTrue(w(["--data-urlencode", "a=b", "u"]))
        self.assertFalse(w(["u"]))
        self.assertFalse(w(["-H", "Accept: x", "u"]))


class GlowText(unittest.TestCase):
    """glow.text must be byte-equal to the per-script copies it replaced."""

    CORPUS = [None, "", "  ", 7, "Ana  Maria\tLopez ", "ÑANDÚ vex", "Zoë", "İstanbul",
              "café", "​Grace", "a b", "MiXeD CaSe", "ümit-öz"]

    @staticmethod
    def old_key(s):                                     # tools/form_status.py (pre-refactor)
        return " ".join(str(s or "").split()).lower()

    @staticmethod
    def old_name_key(s):
        import unicodedata
        s = unicodedata.normalize("NFKD", str(s or ""))
        s = "".join(c for c in s if not unicodedata.combining(c))
        return " ".join(s.split()).lower()

    def test_byte_equal_to_the_old_implementations(self):
        from glow import text
        import hashlib
        for s in self.CORPUS:
            self.assertEqual(text.key(s), self.old_key(s), repr(s))
            self.assertEqual(text.name_key(s), self.old_name_key(s), repr(s))
        for s in ("Session 4", "Mentor Email", "日本語", ""):
            self.assertEqual(text.md5(s), hashlib.md5(s.encode("utf-8")).hexdigest())


class GlowForms(unittest.TestCase):
    def test_shape(self):
        from glow import forms
        self.assertEqual(set(forms.REGIONALS), set(forms.REGIONS))
        self.assertEqual(len(forms.LABELS), 10)
        self.assertEqual(forms.region_of(forms.REGIONALS["Asia"]), "Asia")
        self.assertIsNone(forms.region_of(forms.TEMPLATE))
        self.assertIsNone(forms.region_of(forms.DEFUNCT["Africa"]))
        ids = {forms.TEMPLATE, *forms.REGIONALS.values(), *forms.DEFUNCT.values()}
        self.assertEqual(len(ids), 10)


class EnrollmentParser(unittest.TestCase):
    def test_fixture_matches_expected_json(self):
        expected = json.loads(read(EXPECTED))
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            sheet, dups = sync.read_sheet(FIXTURE)
        self.assertEqual(len(sheet), expected["clubs"])
        self.assertEqual(sum(len(v) for v in sheet.values()), expected["girls"])
        self.assertEqual(len({p for p, _ in sheet}), expected["partners"])
        self.assertEqual(sum(1 for d in dups.values() if d), expected["duplicate_name_clubs"])
        self.assertEqual(sorted(f"{p.lower()}||{c.lower()}" for p, c in sheet), expected["py_clubs"])
        # the case-only re-submission won, with the later spelling and the extra girl
        glow = [k for k in sheet if k[1].lower() == "glow club"]
        self.assertEqual(len(glow), 1)
        self.assertEqual(glow[0][1], "GLOW Club")
        self.assertEqual(len(sheet[glow[0]]), 6)

    def test_parse_roster_edge_cases(self):
        from glow.sync import parse_roster   # its home since the de-dup refactor
        names, dups = parse_roster("1. Dalia Yexleyton\n12) Esther Grimboltz\n- Farah Halverquist\n"
                                   "3 Gloria Ixworthing\nHana Jubbleton,\nInes Lorrimane.\n\n"
                                   "  Joy   Nimbleford  \n\tKavya Quillstrand\t\n"
                                   "​Maya Pellucidor\nmaya pellucidor")
        self.assertEqual(names, ["Dalia Yexleyton", "Esther Grimboltz", "Farah Halverquist",
                                 "Gloria Ixworthing", "Hana Jubbleton", "Ines Lorrimane",
                                 "Joy Nimbleford", "Kavya Quillstrand", "Maya Pellucidor"])
        self.assertEqual(dups, ["maya pellucidor"])

    def test_read_roster_csv_filters_active_and_region(self):
        import tempfile
        rows = ("girl_id,partner,club,region,full_name,last_name,status,added_date,removed_date,source\n"
                "A-B-001,P,Club One,Asia,Ana Fennwhistle,Fennwhistle,active,2026-01-01,,x\n"
                "A-B-002,P,Club One,Asia,Bea Fennwhistle,Fennwhistle,inactive,2026-01-01,2026-02-01,x\n"
                "A-C-001,P,Club Two,,Cy Marrowgate,Marrowgate,active,2026-01-01,,x\n"
                "A-D-001,Q,Club Three,africa,Di Ostrivane,Ostrivane,active,2026-01-01,,x\n")
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(rows)
        try:
            want, all_clubs, region_of = sync.read_roster_csv(f.name, "Asia")
            self.assertEqual(list(want), [("P", "Club One")])
            self.assertEqual(want[("P", "Club One")], ["Ana Fennwhistle"])
            self.assertEqual(len(all_clubs), 3)
            self.assertEqual(region_of[("P", "Club Two")], "")     # blank region: silently not in any region
            self.assertEqual(list(sync.read_roster_csv(f.name, "AFRICA")[0]), [("Q", "Club Three")])
        finally:
            os.remove(f.name)


class PythonAppsScriptParity(unittest.TestCase):
    def setUp(self):
        self.config = read(CONFIG_GS)

    def test_form_ids(self):
        forms = dict(re.findall(r"^\s+([A-Z_]+): '(\d+)',", gs_block(self.config, "FORMS"), re.M))
        self.assertEqual({"Africa": forms["AFRICA"], "Asia": forms["ASIA"],
                          "Latin America": forms["LATIN_AMERICA"], "U.S": forms["US"]},
                         auto_sync.REGIONAL_FORMS)
        template = [fid for fid, (label, _) in form_status.FORMS.items() if label == "template"]
        self.assertEqual(template, [forms["TEMPLATE"]])
        self.assertEqual({fid for fid, (_, region) in form_status.FORMS.items() if region},
                         set(auto_sync.REGIONAL_FORMS.values()))
        self.assertTrue(all(re.fullmatch(r"\d{15}", f) for f in auto_sync.REGIONAL_FORMS.values()))
        # every other Python copy of the table (docs promise this test catches drift)
        import add_feedback_link
        import add_language
        import add_translations
        import backup_forms
        import clone_regional
        import restore_translations
        live = set(auto_sync.REGIONAL_FORMS.values()) | {forms["TEMPLATE"]}
        defunct = set(form_status.DEFUNCT)
        self.assertEqual(set(backup_forms.FORMS), live | defunct)
        self.assertEqual(set(add_translations.FORMS), live)
        self.assertEqual(set(add_language.FORMS), live)
        self.assertEqual(set(add_feedback_link.FORMS), live)
        self.assertEqual(clone_regional.WORKING_COPY, forms["TEMPLATE"])
        self.assertEqual(restore_translations.TEMPLATE, forms["TEMPLATE"])
        self.assertEqual(set(clone_regional.TITLES), set(auto_sync.REGIONAL_FORMS))

    def test_picker_name_is_shared(self):
        self.assertEqual(form_status.PICKER_NAME, sync.PICKER_NAME)

    def test_qids(self):
        block = gs_block(self.config, "QID")
        simple = dict(re.findall(r"^\s+([A-Z_]+): '(\d+)',", block, re.M))
        self.assertEqual(simple["CLUB_NAME"], sync.CLUB_NAME)
        self.assertEqual(simple["PARTNER"], sync.PARTNER)
        self.assertEqual(simple["YEAR"], sync.YEAR)
        self.assertEqual((simple["CONTACT_IDS"], simple["MODULE_ID"], simple["WEEK_ID"], simple["YEAR_ID"]),
                         (sync.CONTACT_IDS, sync.MODULE_ID, sync.WEEK_ID, sync.YEAR_ID))
        self.assertEqual(simple["ENABLE_FUZZY"], form_status.ENABLE_FUZZY_QID)
        self.assertEqual((simple["CLUB_NAME"], simple["PARTNER"], simple["CONTACT_IDS"]),
                         (form_status.CLUB_NAME_QID, form_status.PARTNER_QID, form_status.CONTACT_IDS_QID))
        modules = dict(re.findall(r"'(\d)': '(\d+)'", re.search(r"MODULE: \{([^}]*)\}", block).group(1)))
        self.assertEqual(modules, sync.MODULES)
        sessions = {int(k): v for k, v in
                    re.findall(r"(\d+): '(\d+)'", re.search(r"SESSIONS: \{([^}]*)\}", block).group(1))}
        self.assertEqual(sessions, sync.WEEKS)

    def test_session_overrides(self):
        # tolerant of a missing trailing comma and of double-quoted keys, so a
        # GS-side addition can never be invisible to this test
        block = gs_block(self.config, "SESSION_OVERRIDES")
        pairs = {k or k2: int(v) for k, k2, v in
                 re.findall(r"(?:'([^']+)'|\"([^\"]+)\")\s*:\s*(\d+)\s*,?", block)}
        self.assertEqual(pairs, sync.SESSION_OVERRIDES)
        self.assertEqual(len(pairs), block.count(":"))   # every entry was parsed

    def test_the_same_name_separator(self):
        # "<club> - <partner>" is one string on both sides: the forms' Club picker entry and
        # question 5 (Python), the Monday e-mail's Salesforce account name and the intake
        # check (Apps Script). CLAUDE.md rule 7: change both
        found = re.findall(r"^const SF_NAME_SEP = '([^'\n]*)';", self.config, re.M)
        self.assertEqual(found, [glow_sync.SF_NAME_SEP])
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

    def test_synclog_columns(self):
        m = re.search(r"const SYNC_LOG_COLS = \[(.*?)\];", read(ROSTER_GS), re.S)
        self.assertEqual(re.findall(r"'([a-z0-9_]+)'", m.group(1)), auto_sync.SYNC_LOG_COLS)
        self.assertEqual(m.group(1).count("'") // 2, len(auto_sync.SYNC_LOG_COLS))
        self.assertIn("SYNC_LOG: 'SyncLog'", self.config)
        self.assertEqual(auto_sync.SYNC_LOG_TAB, "SyncLog")

    def test_roster_columns_python_side_is_a_subset(self):
        cols = re.findall(r"'([a-z_]+)'", gs_block(self.config, "ROSTER_COLS"))
        self.assertTrue({"partner", "club", "full_name", "status", "region"} <= set(cols))
        self.assertEqual(cols[0], "girl_id")

    def test_regions_match_glow_forms(self):
        # the Club Roster Form's region picker (Config.gs REGIONS) must offer
        # exactly the regions the Python sync routes on — spelling included
        from glow import forms as glow_forms
        regions = re.findall(r"'([^']+)'", gs_block(self.config, "REGIONS"))
        self.assertEqual(tuple(regions), glow_forms.REGIONS)
        self.assertIn("U.S", regions)                     # one dot, no trailing dot
        self.assertIn("REGION: 'Region where this club meets'", self.config)

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
        for constant in ("Live form ids", "Structural question ids", "SESSION_OVERRIDES",
                         "`SF_NAME_SEP`", "Roster tab columns", "SyncLog columns"):
            self.assertEqual(sum(constant in f for f in firsts), 1, constant)


class FakeSheet:
    """An in-memory spreadsheet for rename_club.main(): read_tab, the values
    batchUpdate and append_rows. before_read(sheet, tab, nth read of that tab)
    can change a tab mid-run, the way a form submission would."""

    def __init__(self, tabs, before_read=None):
        self.tabs = {t: [list(r) for r in rows] for t, rows in tabs.items()}
        self.batches, self.reads, self.before_read, self.last = [], {}, before_read, 0

    def read_tab(self, svc, tab):
        self.reads[tab] = self.reads.get(tab, 0) + 1
        if self.before_read:
            self.before_read(self, tab, self.reads[tab])
        return [list(r) for r in self.tabs.get(tab, [])]

    def append_rows(self, svc, tab, rows):
        self.tabs.setdefault(tab, []).extend(list(r) for r in rows)

    def spreadsheets(self):
        return self

    def values(self):
        return self

    def batchUpdate(self, spreadsheetId, body):
        self.batches.append(body["data"])
        for d in body["data"]:
            m = re.match(r"'((?:[^']|'')+)'!([A-Z]+)(\d+)$", d["range"])
            col = 0
            for ch in m.group(2):
                col = col * 26 + ord(ch) - 64
            row = self.tabs[m.group(1).replace("''", "'")][int(m.group(3)) - 1]
            row += [""] * (col - len(row))
            row[col - 1] = d["values"][0][0]
        self.last = len(body["data"])
        return self

    def execute(self):
        return {"totalUpdatedCells": self.last}


class FakeJotform:
    """The two GETs a move makes; q352 is the club's roster, q444 the picker.
    gated: True = its rule tests the typed Partner box (q331); "list" = the form
    has the partner list (q600) and the rule tests that instead."""

    def __init__(self, gated=False):
        self.gated = gated

    def get(self, path, **params):
        if path.endswith("/questions"):
            qs = {"352": {"type": "control_checkbox", "text": "Sunrise Club"},
                  "444": {"type": "control_dropdown", "text": "Club Name"}}
            if self.gated == "list":
                qs["600"] = {"type": "control_dropdown", "name": sync.PARTNER_PICKER_NAME}
            return qs
        terms = [{"field": "444", "operator": "equals", "value": "Sunrise Club"}]
        if self.gated:
            field = "600" if self.gated == "list" else sync.PARTNER
            terms.insert(0, {"field": field, "operator": "equals", "value": "asoc demo"})
        return {"conditions": [{"id": "1", "type": "field", "terms": json.dumps(terms),
                                "action": json.dumps([{"visibility": "Show", "field": "352"}])}]}


class RenameClub(unittest.TestCase):
    """tools/rename_club.py: the pure planning helpers, on fabricated tabs."""

    HDR = ["girl_id", "partner", "club", "region", "full_name", "status"]

    def rows(self):
        return [self.HDR,
                ["DEMOCLUB-SAMPLE-001", "Demo Partner", "Old Club", "Asia", "A", "active"],
                ["DEMOCLUB-SAMPLE-002", "Demo Partner", " old  club ", "Asia", "B", "removed"],
                ["OTHER-X-001", "Other Partner", "Old Club", "Africa", "C", "active"],
                ["DEMOCLUB-Y-001", "Demo Partner", "Sunrise", "Asia", "D", "active"]]

    def test_find_cells_matches_partner_and_club_case_insensitively(self):
        i_c, hits, clashes, regions = rename_club.find_cells(
            self.rows(), "demo partner", "OLD CLUB", "New Club")
        self.assertEqual(i_c, 2)
        self.assertEqual(hits, [2, 3])          # any status; not the other partner's club
        self.assertEqual(clashes, [])
        self.assertEqual(regions, {"Asia"})

    def test_find_cells_reports_a_clash_with_the_new_name(self):
        _, hits, clashes, _ = rename_club.find_cells(
            self.rows(), "Demo Partner", "Old Club", "sunrise")
        self.assertEqual(hits, [2, 3])
        self.assertEqual(clashes, [5])

    def test_find_cells_without_a_region_column(self):
        rows = [["club_code", "partner", "club", "created"],
                ["OLDCLUB", "Demo Partner", "Old Club", "2026-08-26"]]
        i_c, hits, clashes, regions = rename_club.find_cells(rows, "Demo Partner", "Old Club", "New")
        self.assertEqual((i_c, hits, clashes, regions), (2, [2], [], set()))

    def test_find_cells_refuses_a_tab_without_the_columns(self):
        with self.assertRaises(SystemExit):
            rename_club.find_cells([["when", "action", "detail"]], "p", "a", "b")

    def test_col_letter_and_row_descriptions(self):
        self.assertEqual([rename_club.col_letter(i) for i in (0, 2, 25, 26, 27)],
                         ["A", "C", "Z", "AA", "AB"])
        self.assertEqual(rename_club.describe_rows([]), "no rows")
        self.assertEqual(rename_club.describe_rows([7]), "row 7")
        self.assertEqual(rename_club.describe_rows([3, 4, 5]), "rows 3-5")
        self.assertEqual(rename_club.describe_rows([3, 5]), "rows 3, 5")
        self.assertEqual(rename_club.a1("SF Pending", "C4"), "'SF Pending'!C4")

    # --- --new-partner: moving a club filed under a mistyped partner ---------------
    PARTNERS = [["partner", "region", "notes"],
                ["Asociación Demo", "Latin America", "derived"],
                ["asoc demo", "Latin America", "derived"],
                ["Demo Partner", "Asia", ""]]

    def move_rows(self):
        return [self.HDR,
                ["SUNRISEC-SAMPLE-001", "asoc demo", "Sunrise Club", "Latin America", "A", "active"],
                ["SUNRISEC-SAMPLE-002", "asoc\u200b demo ", "sunrise  club", "Latin America", "B", "inactive"],
                ["DEMOCLUB-SAMPLE-001", "Asociación Demo", "Demo Club", "Latin America", "C", "active"]]

    def test_cell_key_is_the_apps_script_key(self):
        self.assertEqual(rename_club.cell_key(" Asoc\u200b  Demo\ufeff "), "asoc demo")
        self.assertEqual(rename_club.tidy("a\u2060b  c "), "ab c")
        # key_ folds neither accents nor Unicode form; nfc_key only fixes the form
        self.assertNotEqual(rename_club.cell_key("Asociación"), rename_club.cell_key("Asociacion"))
        self.assertNotEqual(rename_club.cell_key("Asociación"), rename_club.cell_key("Asociacio\u0301n"))
        self.assertEqual(rename_club.nfc_key("Asociación"), rename_club.nfc_key("Asociacio\u0301n"))

    def test_find_cells_for_a_move_matches_the_old_partner_any_status(self):
        i_c, hits, clashes, regions = rename_club.find_cells(
            self.move_rows(), "asoc demo", "Sunrise Club", "Sunrise Club", "Asociación Demo")
        self.assertEqual((i_c, hits, clashes, regions), (2, [2, 3], [], {"Latin America"}))

    def test_find_cells_for_a_move_refuses_a_target_that_has_the_club(self):
        rows = self.move_rows() + [["X-1", "Asociación Demo", "Sunrise Club", "Latin America", "D", "active"]]
        _, hits, clashes, _ = rename_club.find_cells(
            rows, "asoc demo", "Sunrise Club", "Sunrise Club", "Asociación Demo")
        self.assertEqual((hits, clashes), ([2, 3], [5]))

    def test_partner_count_and_sharing_partners(self):
        rows = self.move_rows()
        self.assertEqual(rename_club.partner_count(rows, "ASOC DEMO"), 2)
        self.assertEqual(rename_club.partner_count(rows, "Asociación Demo"), 1)
        self.assertEqual(rename_club.sharing_partners(rows, ("asoc demo", "Asociación Demo"),
                                                      {"Sunrise Club"}), [])
        rows.append(["Y-1", "Demo Partner", "SUNRISE CLUB", "Asia", "E", "active"])
        rows.append(["Z-1", "", "Sunrise Club", "", "F", "active"])      # partner-less: not a group
        self.assertEqual(rename_club.sharing_partners(rows, ("asoc demo", "Asociación Demo"),
                                                      {"Sunrise Club"}), ["Demo Partner"])

    def test_partner_rows_and_the_accent_suggestion(self):
        found = rename_club.partner_rows(self.PARTNERS, "asociacio\u0301n  demo")   # NFD, spaced
        self.assertEqual(found, [(2, "Asociación Demo", "Latin America", "derived")])
        self.assertEqual(rename_club.partner_rows(self.PARTNERS, "Asociacion Demo"), [])
        self.assertEqual(rename_club.near_partners(self.PARTNERS, "Asociacion Demo"), ["Asociación Demo"])
        self.assertEqual(rename_club.partner_rows(self.PARTNERS, ""), [])

    def test_partner_gated_finds_only_rules_that_test_the_partner_box(self):
        plain = {"id": "1", "terms": json.dumps([{"field": "444", "operator": "equals", "value": "Sunrise Club"}]),
                 "action": json.dumps([{"visibility": "Show", "field": "352"}])}
        gated = {"id": "2", "terms": [{"field": sync.PARTNER, "operator": "equals", "value": "asoc demo"},
                                      {"field": "444", "operator": "equals", "value": "Sunrise Club"}],
                 "action": {"visibility": "Show", "field": "352"}}
        other = {"id": "3", "terms": gated["terms"], "action": [{"visibility": "Show", "field": "353"}]}
        broken = {"id": "4", "terms": "{not json", "action": "[]"}
        self.assertEqual(rename_club.partner_gated([plain, other, broken], {"352"}), [])
        self.assertEqual(rename_club.partner_gated([plain, gated, other], {"352"}), ["2"])
        # on a form with the partner list the rule tests the list instead
        listed = dict(gated, id="5", terms=[dict(gated["terms"][0], field="600"), gated["terms"][1]])
        self.assertEqual(rename_club.partner_gated([plain, listed], {"352"}), [])
        self.assertEqual(rename_club.partner_gated([plain, listed], {"352"}, {sync.PARTNER, "600"}), ["5"])

    def test_form_questions_names_the_partner_fields(self):
        class Client:
            def __init__(self, qs):
                self.qs = qs

            def get(self, path, **params):
                return self.qs
        qs = {"352": {"type": "control_checkbox", "text": "Sunrise Club", "options": "A Girl|B  Girl"},
              "353": {"type": "control_checkbox", "text": "New Name"}}
        self.assertEqual(rename_club.form_questions(Client(qs), "1", "sunrise club", "New Name"),
                         (["352"], ["353"], {sync.PARTNER}, {"352": {"a girl", "b girl"}}))
        qs["600"] = {"type": "control_dropdown", "name": sync.PARTNER_PICKER_NAME}
        self.assertEqual(rename_club.form_questions(Client(qs), "1", "Sunrise Club", "x")[2],
                         {sync.PARTNER, "600"})

    # --- renaming a club the sync did not add (its name was another partner's club's) ---
    def stars_sheet(self):
        """Partner One's Stars is on the forms (q352, its two girls); Partner Three's new
        Stars is in the Roster and the registry, and on no form: the sync refused it."""
        return FakeSheet({
            "Roster": [self.HDR,
                       ["DEMOCLUB-SAMPLE-001", "Partner One", "Stars", "Africa", "Ann Poe", "active"],
                       ["DEMOCLUB-SAMPLE-002", "Partner One", "Stars", "Africa", "Kay Loe", "active"],
                       ["DEMOCLUB-SAMPLE-003", "Partner One", "Stars", "Africa", "Sue Moe", "inactive"],
                       ["SUNRISEC-SAMPLE-001", "Partner Three", "Stars", "Africa", "Uma Umberlash", "active"],
                       ["SUNRISEC-SAMPLE-002", "Partner Three", "Stars", "Africa", "Ann Poe", "active"]],
            "ClubRegistry": [["club_code", "partner", "club", "created"],
                             ["STARS", "Partner One", "Stars", "2026-08-26"],
                             ["STARS2", "Partner Three", "Stars", "2026-09-30"]],
            "SF Pending": [["added", "partner", "club", "region"],
                           ["2026-09-30", "Partner Three", "Stars", "Africa"]],
            "Audit": [["when", "action", "detail"]],
        })

    class StarsForms:
        """Both forms hold one roster question named Stars: Partner One's."""

        def __init__(self, options="Ann Poe|Kay Loe|Sue Moe"):
            self.options, self.gets, self.posts = options, [], []

        def get(self, path, **params):
            self.gets.append(path)
            return {"352": {"type": "control_checkbox", "text": "Stars", "options": self.options},
                    "444": {"type": "control_dropdown", "text": "Club Name"}}

        def post_form(self, path, data, label):
            self.posts.append((path, data))

    def test_a_club_the_sync_did_not_add_is_renamed_in_the_sheet_only(self):
        # the documented way out of "new club … not added": rename it. The tool finds a
        # club's question by its text, and the only question named Stars is Partner One's:
        # it used to plan (and, applied, write) "q352: 'Stars' -> 'Stars Juniors'" on the
        # region's form and the template - the other partner's roster relabelled
        rename = ["--partner", "Partner Three", "--old", "Stars", "--new", "Stars Juniors"]
        for extra in ([], ["--apply"]):
            sheet, forms = self.stars_sheet(), self.StarsForms()
            code, out = self.run_main(rename + extra, sheet, forms, key="test")
            self.assertIn("q352 is named 'Stars' but holds another club's girls", str(code), out)
            self.assertIn("--sheet-only", str(code))
            self.assertIn("'Partner One'", str(code))
            self.assertNotIn("Ann Poe", str(code) + out)                 # counts, never names
            self.assertEqual((sheet.batches, forms.posts, self.written), ([], [], []), extra)
            self.assertEqual(len(sheet.tabs["Audit"]), 1)
        # --sheet-only: the sheet cells and the Audit row, no Jotform call, and next steps that
        # fit a club the next sync CREATES (no Account to rename, no --q5-change-ok)
        sheet = self.stars_sheet()
        code, out = self.run_main(rename + ["--sheet-only", "--apply"], sheet)
        self.assertEqual(code, 0, out)
        self.assertEqual([r[2] for r in sheet.tabs["Roster"][1:]],
                         ["Stars", "Stars", "Stars", "Stars Juniors", "Stars Juniors"])
        self.assertEqual([r[:3] for r in sheet.tabs["ClubRegistry"][1:]],
                         [["STARS", "Partner One", "Stars"], ["STARS2", "Partner Three", "Stars Juniors"]])
        self.assertEqual(sheet.tabs["SF Pending"][1][2], "Stars Juniors")
        self.assertEqual(sheet.tabs["Audit"][-1][1], "renameClub")
        self.assertNotIn("--apply --q5-change-ok", out)
        self.assertNotIn("rename the club's Account to the new name FIRST", out)
        self.assertIn("no roster question was renamed", out)
        self.assertIn("CREATE roster 'Stars Juniors'", out)
        # the owner of the question renames its own club as ever, namesake or not: the
        # question's girls are its Roster rows' (any status)
        sheet, forms = self.stars_sheet(), self.StarsForms()
        code, out = self.run_main(["--partner", "Partner One", "--old", "Stars", "--new", "North Stars"],
                                  sheet, forms, key="test")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("q352: text 'Stars' -> 'North Stars'"), 2)   # the region's form, the template
        self.assertIn("DRY RUN", out)

    def test_two_questions_of_the_old_name_say_how_to_rename_a_club_that_is_on_no_form(self):
        class Two(self.StarsForms):
            def get(self, path, **params):
                qs = super().get(path, **params)
                return {**qs, "353": dict(qs["352"], options="Eve Hoe|Ida Toe")}
        sheet, forms = self.stars_sheet(), Two()
        code, _ = self.run_main(["--partner", "Partner Three", "--old", "Stars", "--new", "Stars Juniors"],
                                sheet, forms, key="test")
        self.assertIn("2 questions named 'Stars' (q352, q353)", str(code))
        self.assertIn("--sheet-only", str(code))
        self.assertEqual(sheet.batches, [])

    def test_late_rows_finds_the_club_appended_after_the_read(self):
        rows = self.move_rows()
        self.assertEqual(rename_club.late_rows(rows, len(rows), "asoc demo", "Sunrise Club"), [])
        rows += [["SUNRISEC-SAMPLE-003", "ASOC DEMO", "sunrise club", "Latin America", "G", "active"],
                 ["DEMOCLUB-SAMPLE-002", "Asociación Demo", "Demo Club", "Latin America", "H", "active"]]
        self.assertEqual(rename_club.late_rows(rows, 4, "asoc demo", "Sunrise Club"), [5])
        self.assertEqual(rename_club.late_rows([], 0, "asoc demo", "Sunrise Club"), [])

    def test_invisible_characters_are_normalize_gs_own(self):
        with open(os.path.join(REPO, "appsscript", "Normalize.gs"), encoding="utf-8") as f:
            src = f.read()
        gs_class = re.search(r"const INVISIBLE = /\[(.*?)\]/g;", src).group(1)
        self.assertEqual({int(h, 16) for h in re.findall(r"\\u([0-9A-Fa-f]{4})", gs_class)},
                         {ord(c) for c in rename_club.INVISIBLE.pattern.strip("[]")})

    # --- main() on an in-memory sheet (no network, fictional rows) ---------------
    MOVE = ["--partner", "asoc demo", "--club", "Sunrise Club",
            "--new-partner", "asociacio\u0301n demo"]          # NFD on purpose

    def move_sheet(self, before_read=None):
        return FakeSheet({
            "Roster": self.move_rows(),
            "ClubRegistry": [["club_code", "partner", "club", "created"],
                             ["SUNRISEC", "asoc demo", "Sunrise Club", "2026-08-26"],
                             ["DEMOCLUB", "Asociación Demo", "Demo Club", "2026-08-26"]],
            "SF Pending": [["added", "partner", "club", "region"]],
            "Partners": self.PARTNERS,
            "Audit": [["when", "action", "detail"]],
        }, before_read)

    def run_main(self, argv, sheet, client=None, key=None, clock=None, zone=None):
        """(exit code, stdout). `clock` stands in for datetime (its now(tz=None)); `zone` for
        sc.time_zone (default: a sheet on America/New_York). self.written: what the run left
        in OUT (the backup folder), listed before the temp dir goes."""
        import contextlib
        import io
        import tempfile
        from unittest import mock
        out, env = io.StringIO(), {"JOTFORM_API_KEY": key} if key else {}
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(rename_club, "OUT", d), \
                mock.patch.object(rename_club.sc, "service", lambda: sheet), \
                mock.patch.object(rename_club.sc, "read_tab", sheet.read_tab), \
                mock.patch.object(rename_club.sc, "append_rows", sheet.append_rows), \
                mock.patch.object(rename_club.sc, "spreadsheet_id", lambda: "SHEET"), \
                mock.patch.object(rename_club.sc, "sa_email", lambda: "robot"), \
                mock.patch.object(rename_club.sc, "time_zone", zone or (lambda svc: "America/New_York")), \
                mock.patch.object(rename_club, "datetime", clock or rename_club.datetime), \
                mock.patch.object(rename_club, "Client", lambda api_key, apply=False: client), \
                mock.patch.dict(os.environ, env), \
                mock.patch.object(sys, "argv", ["rename_club.py"] + argv), \
                contextlib.redirect_stdout(out):
            try:
                rename_club.main()
                code = 0
            except SystemExit as e:
                code = e.code
            finally:
                self.written = sorted(os.listdir(d))
        return code, out.getvalue()

    def test_move_dry_run_writes_nothing_and_says_what_it_would_do(self):
        sheet = self.move_sheet()
        code, out = self.run_main(self.MOVE + ["--sheet-only"], sheet)
        self.assertEqual(code, 0, out)
        self.assertIn("partner 'asoc demo' -> 'Asociación Demo'", out)
        self.assertIn("rows 2-3", out)                      # both statuses, the invisible char too
        self.assertIn("('asoc demo' blanked, note added)", out)
        self.assertIn("forms          not checked (--sheet-only)", out)
        self.assertIn("DRY RUN", out)
        self.assertEqual(sheet.batches, [])

    def test_move_apply_moves_every_row_and_retires_the_typo(self):
        sheet = self.move_sheet()
        code, out = self.run_main(self.MOVE + ["--apply"], sheet, FakeJotform(), key="test")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(sheet.batches), 1)
        roster, reg, partners = sheet.tabs["Roster"], sheet.tabs["ClubRegistry"], sheet.tabs["Partners"]
        self.assertEqual([r[1] for r in roster[1:3]], ["Asociación Demo"] * 2)
        self.assertEqual([r[4] for r in roster[1:]], ["A", "B", "C"])          # nothing else touched
        self.assertEqual(reg[1][:3], ["SUNRISEC", "Asociación Demo", "Sunrise Club"])
        self.assertEqual(partners[2][:2], ["", "Latin America"])
        self.assertTrue(partners[2][2].startswith(
            "was 'asoc demo': its club 'Sunrise Club' moved to 'Asociación Demo' on "), partners[2])
        self.assertTrue(partners[2][2].endswith("; earlier note: derived"))
        self.assertEqual(partners[1][0], "Asociación Demo")
        audit = sheet.tabs["Audit"][-1]
        self.assertEqual(audit[1], "moveClub")
        self.assertIn("2 Roster rows, ClubRegistry SUNRISEC kept", audit[2])
        self.assertIn("GLOW -> Google Forms -> Update form dropdowns", out)

    def test_move_dates_the_audit_and_the_note_in_the_sheets_zone(self):
        # 03:30 UTC on 09-30 is still 09-29 in New York (the patched sheet zone), whatever
        # zone this process is on; the backup folder's stamp stays the process's own clock
        import datetime as dt
        instant = dt.datetime(2026, 9, 30, 3, 30, 0, tzinfo=dt.timezone.utc)

        class Clock:
            @staticmethod
            def now(tz=None):
                return instant.astimezone(tz) if tz else instant.astimezone().replace(tzinfo=None)
        sheet = self.move_sheet()
        code, out = self.run_main(self.MOVE + ["--apply"], sheet, FakeJotform(), key="test",
                                  clock=Clock)
        self.assertEqual(code, 0, out)
        self.assertEqual(sheet.tabs["Audit"][-1][0], "2026-09-29 23:30:00")
        self.assertIn("moved to 'Asociación Demo' on 2026-09-29 (tools/rename_club.py)",
                      sheet.tabs["Partners"][2][2])
        local = instant.astimezone().strftime("%Y-%m-%dT%H%M%S")
        self.assertIn(local, out)

    def test_move_reads_the_sheets_zone_before_any_write(self):
        # the zone read failing (RuntimeError stands in for an HttpError) or answering a zone
        # that is no IANA name stops the run before the backup folder, the batch, the Audit row
        def broken(svc):
            raise RuntimeError("the zone read failed")
        audit = copy.deepcopy(self.move_sheet().tabs["Audit"])
        sheet = self.move_sheet()
        with self.assertRaises(RuntimeError):
            self.run_main(self.MOVE + ["--apply"], sheet, FakeJotform(), key="test", zone=broken)
        self.assertEqual((sheet.batches, sheet.tabs["Audit"], self.written), ([], audit, []))
        sheet = self.move_sheet()
        code, out = self.run_main(self.MOVE + ["--apply"], sheet, FakeJotform(), key="test",
                                  zone=lambda svc: "Mars/Base")
        self.assertIn("the sheet's time zone 'Mars/Base' is not an IANA zone name", str(code))
        self.assertEqual((sheet.batches, sheet.tabs["Audit"], self.written), ([], audit, []))
        sheet = self.move_sheet()                        # the control: a named zone writes all three
        code, out = self.run_main(self.MOVE + ["--apply"], sheet, FakeJotform(), key="test")
        self.assertEqual(code, 0, out)
        self.assertEqual((len(sheet.batches), len(sheet.tabs["Audit"]), len(self.written)), (1, 2, 1))

    def test_move_refuses_a_partner_gated_rule_and_sheet_only_apply(self):
        sheet = self.move_sheet()
        for gated in (True, "list"):   # the typed box, or the partner list (main() passes its fields)
            code, out = self.run_main(self.MOVE + ["--apply"], sheet, FakeJotform(gated), key="test")
            self.assertIn("given Partner", str(code), gated)
            self.assertEqual(sheet.batches, [], gated)
        code, _ = self.run_main(self.MOVE + ["--sheet-only", "--apply"], sheet)
        self.assertIn("drop --sheet-only", str(code))
        self.assertEqual(sheet.batches, [])

    def test_move_stops_when_the_club_grows_before_the_write(self):
        def add_row(sheet, tab, n):
            if tab == "Roster" and n == 2:            # the re-read just before the write
                sheet.tabs["Roster"].append(["SUNRISEC-SAMPLE-003", "asoc demo", "Sunrise Club",
                                             "Latin America", "G", "active"])
        sheet = self.move_sheet(add_row)
        code, out = self.run_main(self.MOVE + ["--apply"], sheet, FakeJotform(), key="test")
        self.assertIn("nothing written", str(code))
        self.assertEqual(sheet.batches, [])

    def test_move_writes_a_row_that_arrives_during_the_write(self):
        def add_row(sheet, tab, n):
            if tab == "Roster" and n == 3:            # the verify re-read, after the batch
                sheet.tabs["Roster"].append(["SUNRISEC-SAMPLE-003", "asoc demo", "Sunrise Club",
                                             "Latin America", "G", "active"])
        sheet = self.move_sheet(add_row)
        code, out = self.run_main(self.MOVE + ["--apply"], sheet, FakeJotform(), key="test")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(sheet.batches), 2)
        self.assertEqual({r[1] for r in sheet.tabs["Roster"][1:] if r[2] == "Sunrise Club"},
                         {"Asociación Demo"})
        self.assertIn("Roster: 1 late row(s) written and verified", out)
        self.assertIn("3 Roster rows", sheet.tabs["Audit"][-1][2])

    def test_move_stops_for_a_row_edited_in_or_another_club_under_the_typo(self):
        def edit_in(sheet, tab, n):
            if tab == "Roster" and n == 2:
                sheet.tabs["Roster"][-1][2] = "Sunrise Club"         # 'Moon Club' becomes the club
        sheet = self.move_sheet(edit_in)
        sheet.tabs["Roster"].append(["DEMOCLUB-SAMPLE-009", "asoc demo", "Moon Club", "Latin America", "G", "active"])
        code, _ = self.run_main(self.MOVE + ["--apply"], sheet, FakeJotform(), key="test")
        self.assertIn("row 5 changed since the plan was read", str(code))
        self.assertEqual(sheet.batches, [])

        def enroll(sheet, tab, n):
            if tab == "Roster" and n == 2:                           # the typo is not retired now
                sheet.tabs["Roster"].append(["DEMOCLUB-SAMPLE-009", "asoc demo", "Moon Club",
                                             "Latin America", "G", "active"])
        sheet = self.move_sheet(enroll)
        code, _ = self.run_main(self.MOVE + ["--apply"], sheet, FakeJotform(), key="test")
        self.assertIn("row must stay - nothing written", str(code))
        self.assertEqual(sheet.batches, [])

    def test_move_ignores_handler_edits_during_the_write(self):
        def handlers(sheet, tab, n):
            if n == 3 and tab == "Roster":                          # setRowsStatus_ on a moved girl
                sheet.tabs["Roster"][1][5] = "inactive"
            if n == 3 and tab == "Partners":                        # seedPartners_ on another partner
                sheet.tabs["Partners"][3] = ["Demo Partner", "Asia", "region chosen on the form"]
        sheet = self.move_sheet(handlers)
        code, out = self.run_main(self.MOVE + ["--apply"], sheet, FakeJotform(), key="test")
        self.assertEqual(code, 0, out)
        self.assertEqual(sheet.tabs["Audit"][-1][1], "moveClub")


class SwitcherFlags(unittest.TestCase):
    """tools/switcher_flags.py: the CSS block builder and the injectCSS merge."""

    def test_data_uri_is_base64_and_round_trips(self):
        # base64 on purpose: Jotform rewrites "http:" inside injectCSS when serving the page
        import base64
        import xml.etree.ElementTree as ET
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 24">\n  <path fill="#FF9933" d="M0 0h32v8H0z"/>\n</svg>'
        uri = switcher_flags.data_uri(svg)
        self.assertTrue(uri.startswith("data:image/svg+xml;base64,"))
        self.assertNotIn("http:", uri)
        self.assertRegex(uri.split(",", 1)[1], r"^[A-Za-z0-9+/=]+$")
        root = ET.fromstring(base64.b64decode(uri.split(",", 1)[1]))
        self.assertEqual(root[0].get("fill"), "#FF9933")
        self.assertEqual(root.get("xmlns", root.tag.split("}")[0].strip("{")), "http://www.w3.org/2000/svg")

    def test_block_and_merge_are_idempotent(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "xx.svg"), "w") as f:
                f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 24"><path fill="#123" d="M0 0h32v24H0z"/></svg>')
            block = switcher_flags.css_block({"xx": "xx.svg"}, d)
        self.assertTrue(block.startswith(switcher_flags.START) and block.endswith(switcher_flags.END))
        self.assertIn('#langList li[data-lang="xx"] .jfLangDd-flag', block)
        self.assertIn('html[lang="xx"] #langDd .jfLangDd-current:not(.lang-emp) .jfLangDd-flag', block)
        theme = ".form-all { font-family: Inter; }"
        once = switcher_flags.merge(theme, block)
        self.assertTrue(once.startswith(theme))
        self.assertEqual(once.count(switcher_flags.START), 1)
        self.assertEqual(switcher_flags.merge(once, block), once)          # replace, not append
        self.assertEqual(switcher_flags.merge("", block), block + "\n")
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "xx.svg"), "w") as f:
                f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 24"><path fill="#456" d="M0 0h32v24H0z"/></svg>')
            newer = switcher_flags.css_block({"xx": "xx.svg"}, d)
        self.assertNotEqual(newer, block)
        self.assertNotIn(block, switcher_flags.merge(once, newer))
        older = once.replace(switcher_flags.START, "/* GLOW switcher flags v1 */")   # an earlier version's block
        upgraded = switcher_flags.merge(older, block)
        self.assertEqual(upgraded, once)
        self.assertEqual(upgraded.count("GLOW switcher flags v"), 1)

    def test_real_flag_files_parse(self):
        import base64
        import xml.etree.ElementTree as ET
        for code, filename in switcher_flags.FLAGS.items():
            with open(os.path.join(switcher_flags.SVG_DIR, filename), encoding="utf-8") as f:
                uri = switcher_flags.data_uri(f.read())
            root = ET.fromstring(base64.b64decode(uri.split(",", 1)[1]))
            self.assertTrue(root.tag.endswith("svg"), code)


class HeaderImage(unittest.TestCase):
    """tools/update_static_fields.py: the header-logo field and its URL guard."""

    @staticmethod
    def png(width, height):
        return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
                + struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))

    def fetch(self, status="200", content_type="image/png", head=None):
        return lambda url: (status, content_type, self.png(410, 206) if head is None else head)

    def test_png_size_reads_the_ihdr_and_rejects_other_bytes(self):
        self.assertEqual(update_static_fields.png_size(self.png(410, 206)), (410, 206))
        self.assertIsNone(update_static_fields.png_size(b"GIF89a" + b"\0" * 40))
        self.assertIsNone(update_static_fields.png_size(b""))

    def test_the_image_field_is_left_alone_without_a_url(self):
        fields = update_static_fields.wanted_fields()
        self.assertEqual(set(fields), {"mentorEmail", "photo"})
        self.assertEqual(fields, update_static_fields.WANTED)
        fields["photo"] = {}                       # a copy, not the constant
        self.assertNotEqual(update_static_fields.WANTED["photo"], {})

    def test_the_image_field_carries_the_url_size_and_derived_name(self):
        url = "https://www.jotform.com/uploads/Someone/form_files/logo-2x.png?v=3"
        image = update_static_fields.wanted_fields(url)[update_static_fields.IMAGE_FIELD]
        self.assertEqual(image["src"], url)
        self.assertEqual(image["text"], "logo-2x")          # basename, no extension, no query
        self.assertEqual((image["width"], image["height"]), ("205", "103"))
        self.assertEqual(image["align"], "Center")
        # 205x103 keeps the replaced banner's height and the new logo's own shape
        self.assertEqual(int(image["height"]), 103)
        self.assertAlmostEqual(int(image["width"]) / int(image["height"]), 1.99, places=1)

    def test_check_src_accepts_a_2x_png_and_describes_it(self):
        line = update_static_fields.check_src("https://x.test/logo.png", self.fetch())
        self.assertIn("410x206", line)
        self.assertIn("205x103", line)
        self.assertIn("2x", line)

    def test_check_src_refuses_what_a_browser_could_not_load(self):
        for url, fetch in (
            ("http://x.test/logo.png", self.fetch()),                       # not https
            ("https://x.test/logo.png", self.fetch(status="404")),          # missing
            ("https://x.test/logo.png", self.fetch(content_type="text/html")),
            ("https://x.test/logo.png", self.fetch(head=self.png(100, 50))),  # too small
        ):
            with self.assertRaises(SystemExit):
                update_static_fields.check_src(url, fetch)

    def test_check_src_passes_a_non_png_image_through(self):
        line = update_static_fields.check_src(
            "https://x.test/logo.svg", self.fetch(content_type="image/svg+xml", head=b"<svg/>"))
        self.assertIn("image/svg+xml", line)

    def test_the_committed_header_asset_is_big_enough_to_display(self):
        path = os.path.join(REPO, "assets", "global-catalyst-header.png")
        self.assertTrue(os.path.exists(path), path)
        with open(path, "rb") as f:
            size = update_static_fields.png_size(f.read(64))
        self.assertIsNotNone(size, "the header asset must be a PNG")
        props = update_static_fields.IMAGE_PROPS
        self.assertEqual(size, (int(props["width"]) * 2, int(props["height"]) * 2))


# ------------------------------------------------ the links above Submit
def link_form(problem=True, roster=False, stray=None):
    """A fake attendance form laid out like the live ones (read 2026-09-28): the
    top fields, a roster, the link elements, Submit, the hidden bridge fields,
    and a roster the sync created after Submit. Fictional clubs and girls."""
    rows = [("1", "control_head", "heading", {}),
            ("444", "control_dropdown", sync.PICKER_NAME,
             {**sync.PICKER_PROPS, "options": "Moonrise Club|Sunrise Club"}),
            (sync.CLUB_NAME, "control_textbox", "clubName", {"hidden": "Yes"}),
            (sync.PARTNER, "control_textbox", "partner", {"text": "Partner"}),
            (sync.YEAR, "control_dropdown", "module94", {"options": "1|2|3"}),
            ("14", "control_dropdown", "module1", {"options": "Core 1"}),
            ("92", "control_dropdown", "module2", {"hidden": "Yes", "options": "Core 2"}),
            ("93", "control_dropdown", "module3", {"hidden": "Yes", "options": "Core 3"}),
            ("350", "control_checkbox", "SunriseClub",
             {"hidden": "Yes", "text": "Sunrise Club", "options": "Girl One|Girl Two"})]
    if roster:
        rows.append(("460", "control_text", links.ROSTER.name,
                     {"text": links.element_html(links.ROSTER.sentence, links.ROSTER_FORM_URL)}))
    if problem:
        rows.append(("443", "control_text", links.PROBLEM.name,
                     {"text": links.element_html(links.PROBLEM.sentence, links.PROBLEM_FORM_URL)}))
    if stray:
        rows.append(stray)
    rows += [("2", "control_button", "submit2", {"text": "Submit"}),
             ("103", "control_head", "belowAre", {"hidden": "Yes"}),
             (sync.CONTACT_IDS, "control_textarea", "contact_ids", {"hidden": "Yes"}),
             ("400", "control_checkbox", "MoonriseClub",
              {"hidden": "Yes", "text": "Moonrise Club", "options": "Girl Three"})]
    return {qid: {"qid": qid, "type": t, "name": n, "order": str(i), **extra}
            for i, (qid, t, n, extra) in enumerate(rows, 1)}


def apply_steps(questions, steps):
    """What add_feedback_link's steps do to a form, the way the API does it."""
    qs = copy.deepcopy(questions)
    for s in steps:
        if s["op"] == "delete":
            del qs[str(s["qid"])]
        elif s["op"] == "add":
            qid = str(max(int(k) for k in qs) + 1)
            qs[qid] = {"qid": qid, **s["fields"]}
        else:
            qs[str(s["qid"])].update(s["fields"])
    return qs


def rendered(questions):
    """Names in render order: by order, equal orders in creation (qid) order."""
    return [q["name"] for q in sorted(questions.values(),
                                      key=lambda q: (links.order_of(q), int(q["qid"])))]


def create_at(questions, fields, behaviour):
    """(form, new qid) after POST /questions with question[order], under one of
    the two behaviours Jotform might show: "insert" - the question takes the
    order and the block from there down to the first gap moves down one (seen
    on the template 2026-09-01 and Africa 2026-09-12) - or "tie" - it just
    takes the order (equal orders render in creation order, the newest last)."""
    qs = copy.deepcopy(questions)
    order = int(fields["order"])
    if behaviour == "insert":
        used, end = {links.order_of(q) for q in qs.values()}, order
        while end in used:
            end += 1
        for q in qs.values():
            if order <= links.order_of(q) < end:
                q["order"] = str(links.order_of(q) + 1)
    qid = str(max(int(k) for k in qs) + 1)
    qs[qid] = {"qid": qid, **fields}
    return qs, qid


def move_all(questions, moves):
    """What fix_roster_order's writes (one question[order] each) do to a form."""
    qs = copy.deepcopy(questions)
    for qid, order in moves:
        qs[qid]["order"] = str(order)
    return qs


class FakeFormClient:
    """Jotform for add_feedback_link.main(): GETs serve the in-memory forms and
    writes change them as the API would."""

    def __init__(self, forms):
        self.forms, self.writes = forms, []

    def get(self, path, **params):
        fid, part = re.fullmatch(r"/form/(\d+)/(questions|properties)", path).groups()
        return copy.deepcopy(self.forms[fid]) if part == "questions" else {"conditions": []}

    def post_form(self, path, data, label):
        self.writes.append(label)
        fields = {re.fullmatch(r"question\[(\w+)\]", k).group(1): v for k, v in data.items()}
        m = re.fullmatch(r"/form/(\d+)/questions", path)
        if m:
            qs = self.forms[m.group(1)]
            qid = str(max(int(k) for k in qs) + 1)
            qs[qid] = {"qid": qid, **fields}
            return {"qid": qid}
        fid, qid = re.fullmatch(r"/form/(\d+)/question/(\d+)", path).groups()
        self.forms[fid][qid].update(fields)
        return {}

    def delete(self, path, label):
        self.writes.append(label)
        fid, qid = re.fullmatch(r"/form/(\d+)/question/(\d+)", path).groups()
        del self.forms[fid][qid]


class Links(unittest.TestCase):
    """glow/links.py: the element table, its HTML, the URL guard, rule lookup."""

    def test_the_problem_link_html_is_byte_identical_to_the_live_element(self):
        # q443 as read from all five live forms on 2026-09-28: a change here would
        # re-key its translations (md5 of the HTML) and rewrite a live element
        live = ('<p style="margin:12px 0;padding:10px 12px;border:1px solid #ddd;'
                'border-radius:6px;background:#f7f7f7;font-size:14px"><a href="'
                'https://docs.google.com/forms/d/e/1FAIpQLSeYx286-Bre0aSOWnhEDgC4_6FjGyPssldLA3J5WzIeK8cKCA'
                '/viewform" target="_blank" rel="noopener">Click here to report a problem</a></p>')
        self.assertEqual(links.element_html(links.PROBLEM.sentence, links.PROBLEM.url), live)
        self.assertEqual(links.href_of(live), links.PROBLEM_FORM_URL)

    def test_the_urls_are_the_public_links_in_launch_md(self):
        rows = dict(re.findall(r"^\| (.+?) \| (https://\S+) \|$",
                               read(os.path.join(REPO, "docs", "LAUNCH.md")), re.M))
        roster = [u for label, u in rows.items() if label.startswith("Club Roster Form")]
        problem = [u for label, u in rows.items() if label.startswith("Something")]
        self.assertEqual(roster, [links.ROSTER_FORM_URL])
        self.assertEqual(problem, [links.PROBLEM_FORM_URL])
        self.assertEqual(links.ROSTER.url, links.ROSTER_FORM_URL)
        self.assertNotEqual(links.ROSTER_FORM_URL, links.PROBLEM_FORM_URL)

    def test_the_table(self):
        self.assertEqual(set(links.LINKS), {"problem", "roster"})
        self.assertEqual(links.ROSTER.above, links.PROBLEM.name)   # the specific path first
        self.assertEqual(links.PROBLEM.above, links.SUBMIT)
        self.assertEqual(len(links.BY_NAME), len(links.LINKS))
        for link in links.LINKS.values():
            self.assertEqual(link.sentence, link.sentence.strip())
            self.assertFalse(set("&<>\"") & set(link.sentence), link.sentence)

    def test_only_a_public_form_link_is_accepted(self):
        for url in (links.ROSTER_FORM_URL, links.PROBLEM_FORM_URL,
                    links.ROSTER_FORM_URL + "?usp=sf_link", "https://forms.gle/AbCdEf123"):
            self.assertEqual(links.check_public_url(url), url)
        for url in (links.ROSTER_FORM_URL.replace("/viewform", "/edit"),       # owner's edit link
                    "https://docs.google.com/forms/d/" + "1" + "x" * 43 + "/edit",
                    links.ROSTER_FORM_URL.replace("https://", "http://"),
                    "https://example.org/forms/d/e/" + "x" * 30 + "/viewform",
                    links.ROSTER_FORM_URL + '"><b>', links.ROSTER_FORM_URL + " ", "", None):
            with self.assertRaises(SystemExit, msg=url):
                links.check_public_url(url)

    def test_rules_mentioning(self):
        conds = [{"id": "1", "terms": json.dumps([{"field": "443", "operator": "isFilled"}]),
                  "action": json.dumps([{"visibility": "Show", "field": "350"}])},
                 {"id": "2", "terms": [], "action": [{"resultField": "18", "operands": "350,460",
                                                      "equation": "{350}{460}"}]},
                 {"id": "3", "terms": [{"field": "4430"}], "action": [{"field": "44"}]}]
        self.assertEqual(links.rules_mentioning(conds, "443"), ["1"])
        self.assertEqual(links.rules_mentioning(conds, "460"), ["2"])
        self.assertEqual(links.rules_mentioning(conds, 350), ["1", "2"])
        self.assertEqual(links.rules_mentioning(conds, "44"), ["3"])
        self.assertEqual(links.rules_mentioning(conds, "4"), [])
        self.assertEqual(links.rules_mentioning(None, "4"), [])


class ClubGuardElement(unittest.TestCase):
    """glow/sync.py: the club guard's warning, its constants and helpers."""

    def test_the_warning_html_is_pinned(self):
        # a change re-keys its translations (md5 of the stored HTML) and rewrites the
        # element on every guarded form at the next runner apply
        self.assertEqual(glow_sync.guard_html(),
                         '<p style="margin:8px 0;padding:10px 12px;border:1px solid #e0a800;'
                         'border-radius:6px;background:#fff8e1;font-size:14px">You chose more than '
                         'one club. Keep only your own club in Club Name, and the Submit button comes '
                         'back.</p>')
        self.assertEqual(glow_sync.GUARD_PROPS, {"text": glow_sync.guard_html(), "hidden": "Yes"})
        self.assertFalse(set("&<>\"") & set(glow_sync.GUARD_SENTENCE))
        self.assertEqual(glow_sync.GUARD_SENTENCE, glow_sync.GUARD_SENTENCE.strip())
        self.assertTrue(glow_sync.guard_html("a < b").endswith(">a &lt; b</p>"))
        self.assertIn(sync.PICKER_TEXT, glow_sync.GUARD_SENTENCE)        # it names the picker's label

    def test_the_constants_and_helpers(self):
        from unittest import mock
        self.assertEqual(glow_sync.GUARD_NAME, "clubGuard")
        self.assertTrue(glow_sync.GUARD_DISABLES_SUBMIT)
        self.assertTrue(glow_sync.PICKER_CALC_LEADING_EMPTY)    # the single-selects' layout, until proven
        self.assertEqual(glow_sync.picker_calc_values(["A", "B c"]), "|A|B c")
        with mock.patch.object(glow_sync, "PICKER_CALC_LEADING_EMPTY", False):
            self.assertEqual(glow_sync.picker_calc_values(["A", "B c"]), "A|B c")
        for q, has in (({}, False), ({"calcValues": ""}, False), ({"calcValues": "|||"}, False),
                       ({"calcValues": "| "}, False), ({"calcValues": "|A|B"}, True)):
            self.assertEqual(glow_sync.has_calc_values(q), has, q)
        qs = {"12": {"name": "clubGuard", "type": "control_text"}, "9": {"name": "clubGuard"},
              "3": {"name": "clubPicker"}}
        self.assertEqual(glow_sync.club_guards(qs), ["9", "12"])
        self.assertEqual(glow_sync.club_guards({}), [])


class LinkTool(unittest.TestCase):
    """tools/add_feedback_link.py: placement, idempotence, removal, refusals."""

    R, P = links.ROSTER, links.PROBLEM

    def plan(self, qs, link, url=None, conditions=(), remove=False):
        return add_feedback_link.plan_form(qs, list(conditions), link, url or link.url, remove)

    def test_the_roster_link_goes_directly_above_the_problem_link(self):
        qs = link_form()
        steps, _ = self.plan(qs, self.R)
        self.assertEqual([(s["op"], s["qid"]) for s in steps],
                         [("move", "2"), ("move", "443"), ("add", None)])   # tail first
        self.assertEqual(steps[2]["fields"]["order"], qs["443"]["order"])
        self.assertEqual(steps[2]["fields"]["type"], "control_text")
        self.assertNotIn("hidden", steps[2]["fields"])
        after = apply_steps(qs, steps)
        names = rendered(after)
        i = names.index(self.R.name)
        self.assertEqual(names[i:i + 3], [self.R.name, self.P.name, "submit2"])
        self.assertEqual([n for n in names if n != self.R.name], rendered(qs))  # nothing else moves
        self.assertEqual(add_feedback_link.verify(after, [], self.R, self.R.url), [])
        self.assertEqual(add_feedback_link.verify(after, [], self.P, self.P.url), [])
        for n in range(1, len(steps)):   # every intermediate state still renders in order
            part = rendered(apply_steps(qs, steps[:n]))
            self.assertLess(part.index(self.P.name), part.index("submit2"))
        again, notes = self.plan(after, self.R)
        self.assertEqual(again, [])                                     # a re-run is a no-op
        self.assertIn("already present", notes[-1])

    def test_without_the_problem_link_it_sits_above_submit_and_the_problem_link_goes_between(self):
        qs = link_form(problem=False)
        steps, _ = self.plan(qs, self.R)
        self.assertEqual([s["op"] for s in steps], ["move", "add"])
        after = apply_steps(qs, steps)
        steps, _ = self.plan(after, self.P)
        after = apply_steps(after, steps)
        seen = [q["name"] for q in sorted(after.values(), key=links.render_key)
                if links.can_appear(q, set())]      # the hidden q103 header may sit between
        i = seen.index(self.R.name)
        self.assertEqual(seen[i:i + 3], [self.R.name, self.P.name, "submit2"])
        self.assertEqual(add_feedback_link.verify(after, [], self.R, self.R.url), [])
        self.assertEqual(add_feedback_link.verify(after, [], self.P, self.P.url), [])

    def test_remove_deletes_only_its_own_element(self):
        qs = link_form(roster=True)
        steps, _ = self.plan(qs, self.R, remove=True)
        self.assertEqual([(s["op"], s["qid"]) for s in steps], [("delete", "460")])
        after = apply_steps(qs, steps)
        self.assertEqual(add_feedback_link.verify(after, [], self.R, self.R.url, removed=True), [])
        self.assertEqual(add_feedback_link.verify(after, [], self.P, self.P.url), [])
        steps, notes = self.plan(after, self.R, remove=True)
        self.assertEqual(steps, [])
        self.assertIn("nothing to remove", notes[0])

    def test_a_changed_or_hidden_element_is_updated_in_place(self):
        qs = link_form(roster=True)
        qs["460"]["text"] = links.element_html(self.R.sentence, self.R.url + "?usp=old")
        qs["460"]["hidden"] = "Yes"
        steps, _ = self.plan(qs, self.R)
        self.assertEqual([(s["op"], s["qid"]) for s in steps], [("update", "460")])
        self.assertEqual(steps[0]["fields"], {"text": links.element_html(self.R.sentence, self.R.url),
                                              "hidden": "No"})
        self.assertEqual(add_feedback_link.verify(apply_steps(qs, steps), [], self.R, self.R.url), [])

    def test_it_refuses_rather_than_guessing(self):
        stray = link_form(stray=("470", "control_textbox", "somethingElse", {}))
        two_buttons = link_form()
        two_buttons["471"] = {"qid": "471", "type": "control_button", "name": "b2", "order": "30"}
        twice = link_form(roster=True)
        twice["472"] = dict(twice["460"], qid="472", order="31")
        below = link_form()
        below["443"]["order"] = "99"
        shown = link_form(stray=("470", "control_dropdown", "extra", {"hidden": "Yes"}))
        rule = [{"id": "7", "terms": [], "action": [{"visibility": "Show", "field": "470"}]}]
        tied = link_form()   # a roster sharing Submit's order renders after it, until Submit moves
        tied["480"] = {"qid": "480", "type": "control_checkbox", "name": "TiedClub",
                       "hidden": "Yes", "order": tied["2"]["order"]}
        for qs, link, url, conds in ((stray, self.R, None, ()), (two_buttons, self.R, None, ()),
                                     (twice, self.R, None, ()), (below, self.R, None, ()),
                                     (link_form(), self.R, self.P.url, ()),   # the other link's form
                                     (shown, self.R, None, rule),             # hidden, but a rule shows it
                                     (tied, self.R, None, ())):               # would land between the links
            with self.assertRaises(SystemExit):
                self.plan(qs, link, url, conditions=conds)
        # a hidden field no rule shows may sit in the run: it moves along
        quiet = link_form(stray=("470", "control_textbox", "bridge", {"hidden": "Yes"}))
        steps, _ = self.plan(quiet, self.R)
        self.assertEqual([s["qid"] for s in steps], ["2", "470", "443", None])

    def test_a_submit_tied_with_a_hidden_field_does_not_block_the_next_insert(self):
        # after an insert, Submit shares its order with the hidden q103 header
        # (Submit, the older, renders first): a later insert still plans cleanly
        qs = link_form(problem=False)
        after = apply_steps(qs, self.plan(qs, self.R)[0])
        self.assertEqual(after["2"]["order"], after["103"]["order"])
        after = apply_steps(after, self.plan(after, self.P)[0])
        visible = [n for n in rendered(after) if n in (self.R.name, self.P.name, "submit2")]
        self.assertEqual(visible, [self.R.name, self.P.name, "submit2"])

    def test_verify_catches_what_would_hide_or_misplace_it(self):
        qs = link_form(roster=True)
        self.assertEqual(add_feedback_link.verify(qs, [], self.R, self.R.url), [])
        rule = [{"id": "9", "terms": [{"field": sync.YEAR, "operator": "equals", "value": "1"}],
                 "action": [{"visibility": "Show", "field": "460"}]}]
        self.assertTrue(any("rule(s) 9" in p for p in add_feedback_link.verify(qs, rule, self.R, self.R.url)))
        _, notes = self.plan(qs, self.R, conditions=rule)
        self.assertTrue(any("rule 9" in n for n in notes))
        hidden = copy.deepcopy(qs)
        hidden["460"]["hidden"] = "Yes"
        self.assertIn("it is hidden", add_feedback_link.verify(hidden, [], self.R, self.R.url))
        low = copy.deepcopy(qs)
        low["460"]["order"] = "99"
        self.assertTrue(any("not above" in p for p in add_feedback_link.verify(low, [], self.R, self.R.url)))

    def run_main(self, fake, *argv, clock=None):
        """(snapshotted form ids, stdout); the stamps the snapshots were given
        land in self.stamps. `clock` stands in for datetime (its now())."""
        import contextlib
        import io
        from unittest import mock
        snaps, out, self.stamps = [], io.StringIO(), []

        def snapshot(fid, client, stamp):
            snaps.append(fid)
            self.stamps.append(stamp)
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(add_feedback_link, "Client",
                                                  lambda key, apply=False: fake))
            stack.enter_context(mock.patch.object(add_feedback_link, "snapshot", snapshot))
            stack.enter_context(mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}))
            stack.enter_context(mock.patch.object(sys, "argv", ["add_feedback_link.py", *argv]))
            if clock:
                stack.enter_context(mock.patch.object(add_feedback_link, "datetime", clock))
            stack.enter_context(contextlib.redirect_stdout(out))
            add_feedback_link.main()
        return snaps, out.getvalue()

    def test_apply_snapshots_first_writes_tail_first_and_verifies(self):
        from glow import forms as glow_forms
        fid = glow_forms.TEMPLATE
        fake = FakeFormClient({fid: link_form()})
        snaps, out = self.run_main(fake, "--link", "roster", "--form", fid)   # dry run
        self.assertEqual((snaps, fake.writes), ([], []))
        self.assertIn("3. ADD clubRosterFormLink", out)
        snaps, out = self.run_main(fake, "--link", "roster", "--form", fid, "--apply")
        self.assertEqual(snaps, [fid])
        self.assertEqual([w.split(" ", 2)[1] for w in fake.writes], ["move", "move", "ADD"])
        self.assertIn("re-read: verified", out)
        fake.writes.clear()
        snaps, out = self.run_main(fake, "--link", "roster", "--form", fid, "--apply")
        self.assertEqual((snaps, fake.writes), ([], []))                   # idempotent
        self.assertIn("already present", out)

    def test_a_changed_url_says_the_translations_must_be_re_applied(self):
        # every other language shows its copy of the element (keyed text_<qid>),
        # and that copy keeps the old link until add_translations.py runs again
        from glow import forms as glow_forms
        fid, new = glow_forms.TEMPLATE, "https://forms.gle/NewRosterForm1"
        fake = FakeFormClient({fid: link_form(roster=True)})
        _, notes = self.plan(fake.forms[fid], self.R, new)
        self.assertTrue(any("tools/add_translations.py --apply" in n for n in notes), notes)
        _, out = self.run_main(fake, "--link", "roster", "--url", new, "--form", fid, "--apply")
        self.assertEqual([w.split(" ", 2)[1] for w in fake.writes], ["UPDATE"])
        after = out.split("re-read: verified", 1)[1]
        self.assertIn("tools/add_translations.py --apply", after)
        self.assertIn("old link", after)
        _, out = self.run_main(fake, "--link", "roster", "--url", new, "--form", fid, "--apply")
        self.assertNotIn("add_translations", out)                          # nothing written, nothing to redo
        fresh = FakeFormClient({fid: link_form()})                         # a new element: English only until then
        _, out = self.run_main(fresh, "--link", "roster", "--form", fid, "--apply")
        self.assertIn("tools/add_translations.py --apply", out.split("re-read: verified", 1)[1])

    def test_a_hidden_anchor_or_submit_is_refused_not_a_traceback(self):
        hidden = link_form()
        hidden["443"]["hidden"] = "Yes"
        with self.assertRaises(SystemExit) as cm:
            self.plan(hidden, self.R)
        self.assertIn("hidden", str(cm.exception.code))
        self.assertIn("--link problem", str(cm.exception.code))
        rule = [{"id": "5", "terms": [], "action": [{"visibility": "Show", "field": "443"}]}]
        steps, _ = self.plan(hidden, self.R, conditions=rule)             # a rule shows it: fine
        self.assertEqual([s["op"] for s in steps], ["move", "move", "add"])
        no_button = link_form(problem=False)
        no_button["2"]["hidden"] = "Yes"
        with self.assertRaises(SystemExit) as cm:
            self.plan(no_button, self.R)
        self.assertIn("submit2 (q2)", str(cm.exception.code))

    def test_verify_and_the_plan_catch_the_anchor_below_submit(self):
        # the tail-first moves put Submit below the anchor first; a Submit move
        # acknowledged but not applied leaves the problem link under the button
        qs = link_form()
        steps, _ = self.plan(qs, self.R)
        self.assertEqual((steps[0]["op"], steps[0]["qid"]), ("move", "2"))
        partial = apply_steps(qs, steps[1:])
        self.assertEqual([n for n in rendered(partial) if n in (self.R.name, self.P.name, "submit2")],
                         [self.R.name, "submit2", self.P.name])
        problems = add_feedback_link.verify(partial, [], self.R, self.R.url)
        self.assertTrue(any(self.P.name in p and "submit2" in p for p in problems), problems)
        self.assertEqual(add_feedback_link.verify(apply_steps(qs, steps), [], self.R, self.R.url), [])
        below = link_form(roster=True)
        below["443"]["order"] = "99"
        steps, notes = self.plan(below, self.R)                            # present: flagged, not moved
        self.assertEqual(steps, [])
        self.assertTrue(any(self.P.name in n and "submit2" in n for n in notes), notes)

    def test_a_retry_in_the_same_minute_keeps_the_first_snapshot(self):
        # the pre-write snapshot is the rollback path: a re-run seconds after a
        # failed one must not write the half-changed form over it
        from datetime import datetime as real
        from glow import forms as glow_forms
        ticks = iter([real(2026, 9, 28, 10, 0, 5), real(2026, 9, 28, 10, 0, 40)])

        class Clock:
            @staticmethod
            def now():
                return next(ticks)
        fid, stamps = glow_forms.TEMPLATE, []
        for _ in range(2):
            self.run_main(FakeFormClient({fid: link_form()}), "--link", "roster", "--form", fid,
                          "--apply", clock=Clock)
            stamps += self.stamps
        self.assertEqual(len(stamps), 2)
        self.assertNotEqual(stamps[0], stamps[1])


class TranslationPlan(unittest.TestCase):
    """tools/add_translations.py plan_additions/merge and add_language's text-element keys."""

    OFFERED = {"es", "fr", "th", "ur", "te", "vi", "ne", "km", "sw", "ar", "or", "hi", "fa"}

    def setUp(self):
        self.additions = add_translations.load_additions()

    @staticmethod
    def store(*langs):
        return {**{lang: {} for lang in langs}, "base": {}, "en": {}}

    def test_the_roster_sentence_is_translated_for_every_offered_language(self):
        raw = json.loads(read(os.path.join(REPO, "tools", "translations_additions.json")))
        entry = raw[links.ROSTER.sentence]
        self.assertEqual(set(entry) - {"_note"}, self.OFFERED)
        self.assertIn("not native-reviewed", entry["_note"].lower())
        for lang in self.OFFERED:
            text = entry[lang]
            self.assertIn("Club Roster Form", text, lang)     # the form's own (English) name
            self.assertNotEqual(text, links.ROSTER.sentence, lang)
            self.assertFalse(set("&<>") & set(text), lang)
        self.assertIn(links.PROBLEM.sentence, raw)

    def test_both_link_elements_are_keyed_by_sentence_element_id_and_html(self):
        qs = link_form(roster=True)
        payload, sources = add_translations.plan_additions(qs, self.store("es", "hi"), self.additions)
        self.assertEqual(set(payload), {"es", "hi"})               # only what the form offers
        for qid, link in (("460", links.ROSTER), ("443", links.PROBLEM)):
            stored, text_id = qs[qid]["text"], f"text_{qid}"
            for lang in payload:
                if lang not in self.additions[link.sentence]:
                    continue
                want = self.additions[link.sentence][lang]
                html_t = payload[lang][md5(text_id)]
                self.assertEqual(payload[lang][md5(stored)], html_t)
                self.assertEqual(payload[lang][md5(link.sentence)], want)
                self.assertIn(want, html_t)
                self.assertNotIn(link.sentence, html_t)
                self.assertEqual(links.href_of(html_t), link.url)   # the link is untouched
            self.assertEqual(sources[md5(link.sentence)], link.sentence)
            self.assertEqual(sources[md5(text_id)], text_id)
            self.assertEqual(sources[md5(stored)], stored)
        self.assertIn(md5("text_460"), payload["hi"])              # Hindi reaches the new link
        self.assertNotIn(md5("text_443"), payload["hi"])           # its problem-link Hindi is add_language's

    def test_a_form_without_the_element_gets_none_of_its_keys(self):
        qs = link_form()
        payload, sources = add_translations.plan_additions(qs, self.store(*self.OFFERED), self.additions)
        keys = {k for d in payload.values() for k in d} | set(sources)
        self.assertNotIn(md5(links.ROSTER.sentence), keys)
        self.assertIn(md5(links.PROBLEM.sentence), keys)
        payload, _ = add_translations.plan_additions(link_form(roster=True), self.store("es", "fr"),
                                                     self.additions)
        self.assertFalse({"hi", "fa", "or"} & set(payload))       # a language the form lacks is never posted

    def test_merge_keeps_every_existing_entry_and_never_overwrites_a_source(self):
        qs = link_form(roster=True)
        store = self.store("es", "fr")
        store["es"]["k-existing"] = "ya estaba"
        store["fr"]["k-existing"] = "déjà là"
        store["base"][md5(links.ROSTER.sentence)] = "an older source text"
        store["base"]["k-roster-option"] = "Girl One"
        payload, sources = add_translations.plan_additions(qs, store, self.additions)
        merged = add_translations.merge(store, payload, sources)
        self.assertEqual(merged["es"]["k-existing"], "ya estaba")
        self.assertEqual(merged["fr"]["k-existing"], "déjà là")
        self.assertEqual(merged["base"]["k-roster-option"], "Girl One")
        self.assertEqual(merged["base"][md5(links.ROSTER.sentence)], "an older source text")
        self.assertEqual(merged["en"][md5(links.ROSTER.sentence)], links.ROSTER.sentence)
        self.assertEqual(merged["en"][md5("text_460")], "text_460")
        for lang in ("es", "fr"):
            self.assertLessEqual(set(store[lang]), set(merged[lang]))

    def test_add_language_keys_both_elements(self):
        qs = link_form(roster=True)
        base = {md5("text_460"): "text_460", md5(qs["460"]["text"]): qs["460"]["text"],
                md5("text_443"): "text_443", "k-roster-option": "Girl One"}
        words = {links.ROSTER.sentence: "RR", links.PROBLEM.sentence: "PP"}
        out = add_language.text_element_keys(qs, base, words)
        self.assertEqual(set(out), {md5("text_460"), md5(qs["460"]["text"]), md5("text_443")})
        self.assertEqual(out[md5("text_460")], qs["460"]["text"].replace(links.ROSTER.sentence, "RR"))
        self.assertEqual(out[md5("text_443")], qs["443"]["text"].replace(links.PROBLEM.sentence, "PP"))
        self.assertEqual(add_language.text_element_keys(qs, base, {links.PROBLEM.sentence: "PP"}),
                         {md5("text_443"): qs["443"]["text"].replace(links.PROBLEM.sentence, "PP")})

    def test_re_applying_after_a_url_change_replaces_every_languages_copy(self):
        # the remedy add_feedback_link.py names after it changes a link
        qs = link_form(roster=True)
        store = add_translations.merge(self.store("es", "fr"), *add_translations.plan_additions(
            qs, self.store("es", "fr"), self.additions))
        new = "https://forms.gle/NewRosterForm1"
        qs["460"]["text"] = links.element_html(links.ROSTER.sentence, new)
        store = add_translations.merge(store, *add_translations.plan_additions(qs, store, self.additions))
        for lang in ("es", "fr"):
            self.assertEqual(links.href_of(store[lang][md5("text_460")]), new, lang)
            self.assertEqual(links.href_of(store[lang][md5(qs["460"]["text"])]), new, lang)

    @staticmethod
    def guard_form():
        qs = link_form(roster=True)
        qs["700"] = {"qid": "700", "type": "control_text", "name": glow_sync.GUARD_NAME, "order": "3",
                     **glow_sync.GUARD_PROPS}
        return qs

    def test_the_guard_sentence_is_translated_for_every_offered_language(self):
        raw = json.loads(read(os.path.join(REPO, "tools", "translations_additions.json")))
        entry = raw[glow_sync.GUARD_SENTENCE]
        self.assertEqual(set(entry) - {"_note"}, self.OFFERED)
        self.assertIn("not native-reviewed", entry["_note"].lower())
        # it names the picker by its label in that language, as the mentor sees it
        label = dict(raw["Club Name"])
        for lang in ("or", "hi", "fa"):
            label[lang] = json.loads(read(os.path.join(REPO, "tools", f"translations_{lang}.json")))["Club Name"]
        for lang in self.OFFERED:
            text = entry[lang]
            self.assertIn(label[lang], text, lang)
            self.assertNotEqual(text, glow_sync.GUARD_SENTENCE, lang)
            self.assertFalse(set("&<>") & set(text), lang)

    def test_the_guard_is_keyed_by_sentence_element_id_and_html(self):
        qs = self.guard_form()
        payload, sources = add_translations.plan_additions(qs, self.store("es", "fa"), self.additions)
        stored, sentence = qs["700"]["text"], glow_sync.GUARD_SENTENCE
        for lang in ("es", "fa"):
            want = self.additions[sentence][lang]
            html_t = payload[lang][md5("text_700")]
            self.assertEqual(payload[lang][md5(stored)], html_t)
            self.assertEqual(payload[lang][md5(sentence)], want)
            self.assertEqual(html_t, glow_sync.guard_html(want))       # the same box, translated
        self.assertEqual((sources[md5(sentence)], sources[md5("text_700")], sources[md5(stored)]),
                         (sentence, "text_700", stored))
        # the links keep their keys
        self.assertIn(md5("text_460"), payload["es"])
        # a form without the warning gets none of its keys
        payload, sources = add_translations.plan_additions(link_form(roster=True), self.store("es"),
                                                           self.additions)
        self.assertNotIn(md5(sentence), set(payload["es"]) | set(sources))
        # add_language keys it too, beside the links
        base = {md5("text_700"): "text_700", md5(stored): stored, md5("text_460"): "text_460"}
        out = add_language.text_element_keys(qs, base, {sentence: "GG", links.ROSTER.sentence: "RR"})
        self.assertEqual(set(out), {md5("text_700"), md5(stored), md5("text_460")})
        self.assertEqual(out[md5("text_700")], glow_sync.guard_html("GG"))
        self.assertEqual(out[md5(stored)], glow_sync.guard_html("GG"))

    def test_only_a_text_element_named_club_guard_is_translated(self):
        qs = self.guard_form()
        qs["700"]["type"] = "control_textbox"
        self.assertEqual([s for _, s in links.translated_elements(qs)],
                         [links.ROSTER.sentence, links.PROBLEM.sentence])

    def test_the_store_backup_is_never_overwritten(self):
        # a same-stamp re-run after a failed POST must keep the true 'before'
        import tempfile
        from unittest import mock
        self.assertIn("<form>-<stamp>-before.json", add_translations.__doc__)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(add_translations, "REPO", tmp):
            first = add_translations.save_store("123", {"es": {"k": "before"}}, "2026-09-28T100005")
            again = add_translations.save_store("123", {"es": {"k": "half-written"}}, "2026-09-28T100005")
            self.assertNotEqual(first, again)
            self.assertTrue(first.endswith(os.path.join("translations", "123-2026-09-28T100005-before.json")))
            with open(first, encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"es": {"k": "before"}})
            with open(again, encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"es": {"k": "half-written"}})


class SyncLeavesTheLinksAlone(unittest.TestCase):
    """sync_attendance_form.py end to end (dry run, fake Jotform): the link
    elements are neither written nor mentioned by any generated rule, and a
    new roster is created above them and the Submit button."""

    ROWS = (("Partner A", "Sunrise Club", "Girl One"), ("Partner A", "Sunrise Club", "Girl Two"),
            ("Partner A", "Sunrise Club", "Girl Four"), ("Partner A", "Moonrise Club", "Girl Three"),
            ("Partner B", "Starlight Club", "Girl Five"))

    def run_sync(self, qs, rows=ROWS):
        """(fake form, stdout) of a dry run on the form `qs` with Roster `rows`."""
        import contextlib
        import csv
        import io
        import tempfile
        from unittest import mock
        seen = {}

        class FakeForm:
            def __init__(self, api_key, form_id, apply_changes=False):
                self.calls, self.paths, self.data = [], [], []
                seen["form"] = self

            def get(self, path):
                return {"/questions": copy.deepcopy(qs), "/properties": {"conditions": []},
                        "": {"count": "0"}}[path]

            def post_form(self, path, data, label):
                self.calls.append(label)
                self.paths.append(path)
                self.data.append(data)

            def put_json(self, path, payload, label):
                self.calls.append(label)
                self.paths.append(path)
                self.data.append(payload)
                seen["conditions"] = payload["properties"]["conditions"]

            def delete(self, path, label):
                self.calls.append(label)
                self.paths.append(path)
                self.data.append(None)

        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "roster.csv")
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["girl_id", "partner", "club", "full_name", "status", "region"])
                for i, (partner, club, name) in enumerate(rows, 1):
                    w.writerow([f"DEMOCLUB-SAMPLE-{i:03d}", partner, club, name, "active", "Africa"])
            with mock.patch.object(sync, "Jotform", FakeForm), \
                    mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}), \
                    mock.patch.object(sys, "argv", ["sync_attendance_form.py", path, "--roster",
                                                    "--region", "Africa", "--form", "999"]), \
                    contextlib.redirect_stdout(out):
                sync.main()
        form = seen["form"]
        form.conditions = seen.get("conditions")
        return form, out.getvalue()

    def setUp(self):
        del sync.WARNINGS[:]

    def tearDown(self):
        del sync.WARNINGS[:]

    def test_a_sync_run_never_touches_or_gates_the_link_elements(self):
        form, _ = self.run_sync(link_form(roster=True))
        self.assertTrue(any(c.startswith("CREATE roster 'Starlight Club'") for c in form.calls), form.calls)
        self.assertTrue(any(c.startswith("UPDATE roster 'Sunrise Club'") for c in form.calls), form.calls)
        self.assertTrue(any(c.startswith("REPLACE conditions") for c in form.calls), form.calls)
        for qid in ("460", "443", "2"):
            self.assertFalse([p for p in form.paths if p.rstrip("/").endswith(f"/{qid}")], qid)
            self.assertEqual(links.rules_mentioning(form.conditions, qid), [], qid)

    def created(self, form):
        return [(c, d) for c, d in zip(form.calls, form.data) if c.startswith("CREATE roster")]

    def test_a_new_roster_goes_above_the_links_and_submit_under_both_behaviours(self):
        for roster_link in (False, True):
            qs = link_form(roster=roster_link)
            form, out = self.run_sync(qs)
            (label, data), = self.created(form)
            self.assertEqual(label, "CREATE roster 'Starlight Club' (1 girls)")
            self.assertTrue(auto_sync.CREATE_RX.match("  - " + label))    # the runner still reads it
            self.assertEqual(data["question[order]"], qs["350"]["order"])  # the last roster above the links
            fence = "clubRosterFormLink (q460)" if roster_link else "somethingNotWorking (q443)"
            self.assertIn(f"New rosters go at order {qs['350']['order']}, above {fence}", out)
            plan = auto_sync.parse_plan(out)
            self.assertEqual((len(plan["creates"]), plan["warnings"]), (1, []))   # not a warning
            fields = {k[len("question["):-1]: v for k, v in data.items()}
            for behaviour in ("insert", "tie"):
                after, _ = create_at(qs, fields, behaviour)
                names = rendered(after)
                for anchor in ([links.ROSTER.name] if roster_link else []) + [links.PROBLEM.name, "submit2"]:
                    self.assertLess(names.index(fields["name"]), names.index(anchor), (behaviour, anchor))
                self.assertEqual([n for n in names if n != fields["name"]], rendered(qs))   # nothing else moves
                self.assertEqual([q["qid"] for q in layout.rosters_below(after)], ["400"], behaviour)

    def test_several_new_rosters_share_the_slot_and_all_land_above(self):
        rows = self.ROWS + (("Partner B", "Comet Club", "Girl Six"), ("Partner C", "Aurora Club", "Girl Seven"))
        qs = link_form(roster=True)
        form, _ = self.run_sync(qs, rows)
        creates = self.created(form)
        self.assertEqual(len(creates), 3)
        self.assertEqual({d["question[order]"] for _, d in creates}, {qs["350"]["order"]})
        for behaviour in ("insert", "tie"):
            after, new = qs, []
            for _, data in creates:
                after, qid = create_at(after, {k[len("question["):-1]: v for k, v in data.items()},
                                       behaviour)
                new.append(qid)
            names = rendered(after)
            for qid in new:
                self.assertLess(names.index(after[qid]["name"]), names.index(links.ROSTER.name), behaviour)
            self.assertEqual([q["qid"] for q in layout.rosters_below(after)], ["400"], behaviour)

    def test_without_a_roster_above_the_links_it_takes_the_fence_order_and_says_so(self):
        qs = link_form()
        qs["350"]["order"] = "99"                    # every roster below Submit
        form, out = self.run_sync(qs)
        (_, data), = self.created(form)
        self.assertEqual(data["question[order]"], qs["443"]["order"])
        self.assertTrue(any("new rosters take the order of somethingNotWorking (q443)" in w
                            for w in sync.WARNINGS), sync.WARNINGS)
        after, qid = create_at(qs, {k[len("question["):-1]: v for k, v in data.items()}, "insert")
        self.assertLess(rendered(after).index(after[qid]["name"]), rendered(after).index(links.PROBLEM.name))

    def test_two_submit_buttons_are_refused_before_any_write(self):
        qs = link_form()
        qs["471"] = {"qid": "471", "type": "control_button", "name": "b2", "order": "30"}
        with self.assertRaises(SystemExit) as cm:
            self.run_sync(qs)
        self.assertIn("expected one Submit button, found 2", str(cm.exception.code))

    def test_nothing_to_create_prints_no_slot(self):
        rows = [r for r in self.ROWS if r[1] != "Starlight Club"]
        form, out = self.run_sync(link_form(), rows)
        self.assertEqual(self.created(form), [])
        self.assertNotIn("New rosters go", out)


class RosterLayout(unittest.TestCase):
    """glow/layout.py: the fence, the new-roster slot, the one-time tail
    repair and the audit, on the fake form laid out like the live ones."""

    def test_the_fence_is_the_first_of_the_links_and_submit(self):
        self.assertEqual(layout.fence(link_form())["qid"], "443")
        self.assertEqual(layout.fence(link_form(roster=True))["qid"], "460")
        self.assertEqual(layout.fence(link_form(problem=False))["qid"], "2")
        low = link_form()
        low["443"]["order"] = "50"                   # a link below Submit: Submit is the fence
        self.assertEqual(layout.fence(low)["qid"], "2")
        bare = {k: v for k, v in link_form().items() if k not in ("443", "2")}
        self.assertIsNone(layout.fence(bare))
        self.assertEqual(layout.rosters_below(bare), [])
        two = link_form()
        two["471"] = {"qid": "471", "type": "control_button", "name": "b2", "order": "30"}
        with self.assertRaises(SystemExit):
            layout.fence(two)

    def test_rosters_below_and_the_slot(self):
        qs = link_form()
        self.assertEqual([q["qid"] for q in layout.rosters_below(qs)], ["400"])
        slot, fence = layout.roster_slot(qs)
        self.assertEqual((slot, fence["qid"]), (links.order_of(qs["350"]), "443"))
        # no Submit and no link (the SameNameFlow form): the end of the form, as before
        pp, _ = SameNameFlow.form(SameNameFlow())
        self.assertEqual(layout.roster_slot(pp), (max(links.order_of(q) for q in pp.values()) + 1, None))
        # no roster above the fence: the fence's own order
        qs["350"]["order"] = "99"
        slot, fence = layout.roster_slot(qs)
        self.assertEqual((slot, fence["qid"]), (links.order_of(qs["443"]), "443"))

    def test_one_and_two_new_rosters_render_above_the_fence_under_both_behaviours(self):
        for base in (link_form(), link_form(roster=True), link_form(problem=False)):
            fence = layout.fence(base)["qid"]
            for behaviour in ("insert", "tie"):
                for n in (1, 2):
                    qs, new = base, []
                    for i in range(n):
                        slot, _ = layout.roster_slot(base)          # computed once per run
                        qs, qid = create_at(qs, {"type": "control_checkbox", "name": f"New{i}",
                                                 "hidden": "Yes", "order": str(slot)}, behaviour)
                        new.append(qid)
                    order = [str(q["qid"]) for q in layout.in_render_order(qs)]
                    for qid in new:
                        self.assertLess(order.index(qid), order.index(fence), (behaviour, n))
                    self.assertEqual([q["qid"] for q in layout.rosters_below(qs)], ["400"])
                    # where among the rosters (RUNBOOK "Rosters above Submit"): inserted,
                    # just above the last roster above the fence, newest first; tied,
                    # just after it, in creation order
                    i = order.index("350")
                    if behaviour == "insert":
                        self.assertEqual(order[i - n:i], new[::-1], n)
                    else:
                        self.assertEqual(order[i + 1:i + 1 + n], new, n)

    def test_the_tail_plan(self):
        qs = link_form()
        top = max(links.order_of(q) for q in qs.values())
        moves = layout.plan_tail_moves(qs)
        # Submit first, then the hidden fields bottom-up, the link (the fence) last
        self.assertEqual(moves, [("2", top + 2), ("18", top + 4), ("103", top + 3), ("443", top + 1)])
        self.assertFalse({qid for qid, _ in moves} & {"350", "400"})    # no roster is ever written
        after = move_all(qs, moves)
        self.assertEqual(layout.rosters_below(after), [])
        self.assertEqual(rendered(after)[-4:], [links.PROBLEM.name, "submit2", "belowAre", "contact_ids"])
        seen = [n for n in rendered(qs) if n not in ("MoonriseClub", "SunriseClub")]
        self.assertEqual([n for n in rendered(after) if n not in ("MoonriseClub", "SunriseClub")], seen)
        self.assertEqual(layout.plan_tail_moves(after), [])            # a second run plans nothing
        self.assertEqual(layout.audit_layout(after), [])

    def test_with_both_links_they_move_bottom_up_and_stay_above_submit_at_every_step(self):
        qs = link_form(roster=True)
        top = max(links.order_of(q) for q in qs.values())
        moves = layout.plan_tail_moves(qs)
        self.assertEqual([qid for qid, _ in moves], ["2", "18", "103", "443", "460"])
        self.assertEqual(dict(moves), {"460": top + 1, "443": top + 2, "2": top + 3,
                                       "103": top + 4, "18": top + 5})
        for n in range(len(moves) + 1):
            part = rendered(move_all(qs, moves[:n]))
            self.assertEqual([x for x in part if x in (links.ROSTER.name, links.PROBLEM.name, "submit2")],
                             [links.ROSTER.name, links.PROBLEM.name, "submit2"], n)
            if n:                                     # after the first write every roster is above Submit
                self.assertGreater(part.index("submit2"), part.index("MoonriseClub"), n)
        self.assertEqual(layout.rosters_below(move_all(qs, moves)), [])

    def test_a_re_run_after_a_half_finished_apply_ends_identical(self):
        for qs in (link_form(), link_form(roster=True), link_form(problem=False)):
            moves = layout.plan_tail_moves(qs)
            whole = rendered(move_all(qs, moves))
            for n in range(1, len(moves)):
                half = move_all(qs, moves[:n])
                again = layout.plan_tail_moves(half)
                self.assertTrue(again, n)             # the fence moves last: a stop leaves work to do
                self.assertEqual(rendered(move_all(half, again)), whole, n)

    def test_without_a_link_submit_is_the_fence_and_moves_last(self):
        qs = link_form(problem=False)
        moves = layout.plan_tail_moves(qs)
        self.assertEqual([qid for qid, _ in moves], ["18", "103", "2"])
        self.assertEqual(layout.rosters_below(move_all(qs, moves)), [])

    def test_it_refuses_rather_than_guessing(self):
        pagebreak = link_form()
        pagebreak["480"] = {"qid": "480", "type": "control_pagebreak", "name": "page2", "order": "8"}
        visible = link_form()
        visible["481"] = {"qid": "481", "type": "control_textbox", "name": "extra", "order": "13"}
        shown = link_form()
        shown["482"] = {"qid": "482", "type": "control_textbox", "name": "extra", "order": "13",
                        "hidden": "Yes"}
        rule = [{"id": "7", "terms": [], "action": [{"visibility": "Show", "field": "482"}]}]
        below = link_form(roster=True)
        below["460"]["order"] = "12"                  # a link below Submit
        none = link_form()
        del none["2"]
        two = link_form()
        two["471"] = {"qid": "471", "type": "control_button", "name": "b2", "order": "30"}
        for name, qs, conds in (("page break", pagebreak, ()), ("visible field", visible, ()),
                                ("shown by a rule", shown, rule), ("link below Submit", below, ()),
                                ("no Submit", none, ()), ("two Submits", two, ())):
            with self.assertRaises(SystemExit, msg=name):
                layout.plan_tail_moves(qs, conds)
        quiet = copy.deepcopy(shown)                  # hidden and no rule shows it: it moves along
        moves = layout.plan_tail_moves(quiet)
        self.assertIn("482", [qid for qid, _ in moves])

    def test_the_restore_plan_puts_every_order_back_with_the_links_above_submit(self):
        for saved in (link_form(), link_form(roster=True), link_form(problem=False)):
            moves = layout.plan_tail_moves(saved)
            for n in range(1, len(moves) + 1):           # after a whole or a stopped repair
                now = move_all(saved, moves[:n])
                back = layout.plan_restore(now, saved)
                self.assertEqual(sorted(q for q, _ in back), sorted(q for q, _ in moves[:n]), n)
                for i in range(len(back) + 1):
                    part = rendered(move_all(now, back[:i]))
                    seen = [x for x in part if x in (links.ROSTER.name, links.PROBLEM.name, "submit2")]
                    self.assertEqual(seen, [x for x in rendered(saved) if x in seen], (n, i))
                self.assertEqual(move_all(now, back), saved, n)
            self.assertEqual(layout.plan_restore(saved, saved), [])
        qs = link_form()
        repaired = move_all(qs, layout.plan_tail_moves(qs))
        grown = copy.deepcopy(repaired)
        grown["490"] = {"qid": "490", "type": "control_checkbox", "name": "LateClub", "order": "9"}
        shifted = copy.deepcopy(repaired)
        shifted["400"]["order"] = "99"
        for name, now in (("a new question", grown), ("a roster moved", shifted)):
            with self.assertRaises(SystemExit, msg=name):
                layout.plan_restore(now, qs)

    def test_the_restore_plan_refuses_a_snapshot_with_a_tie_and_says_why(self):
        # the Club Roster Form link placed before the repair: plan_insert moves
        # q443 and Submit one down, so Submit shares the next hidden field's order
        qs = link_form()
        order, moves = links.plan_insert(qs, links.ROSTER)
        linked = move_all(qs, moves)
        linked["460"] = {"qid": "460", "type": "control_text", "name": links.ROSTER.name,
                         "order": str(order)}
        self.assertEqual(links.order_of(linked["2"]), links.order_of(linked["103"]))
        repaired = move_all(linked, layout.plan_tail_moves(linked))
        self.assertEqual(layout.audit_layout(repaired), [])           # the repair itself is fine
        with self.assertRaises(SystemExit) as cm:                      # its undo refuses, and says why
            layout.plan_restore(repaired, linked)
        self.assertIn(f"the snapshot holds more than one question at order {links.order_of(linked['2'])}",
                      str(cm.exception.code))
        self.assertIn("Revision History", str(cm.exception.code))

    def test_the_audit(self):
        qs = link_form()
        problems = layout.audit_layout(qs)
        self.assertEqual(problems, ["1 roster(s) render below somethingNotWorking (q443) (first q400) - "
                                    "run tools/fix_roster_order.py (dry run first)"])
        self.assertEqual(layout.audit_layout(move_all(qs, layout.plan_tail_moves(qs))), [])
        below = link_form(roster=True)
        below["460"]["order"] = "12"
        self.assertTrue(any("clubRosterFormLink (q460) renders below Submit" in p
                            for p in layout.audit_layout(below)))
        two = link_form()
        two["471"] = {"qid": "471", "type": "control_button", "name": "b2", "order": "30"}
        self.assertEqual(layout.audit_layout(two), ["2 Submit buttons, expected 1"])
        self.assertEqual(layout.summary(qs), {"submit_buttons": 1, "fence": "somethingNotWorking (q443)",
                                              "rosters": 2, "rosters_below": 1, "first_below": "400"})


class FixRosterOrderTool(unittest.TestCase):
    """tools/fix_roster_order.py main() on fake forms (FakeFormClient keeps an
    order as sent): planning, refusals, snapshot, drift, probe, verify."""

    FIDS = [glow_forms.TEMPLATE, *glow_forms.REGIONALS.values()]

    def run_main(self, fake, *argv):
        """(exit code or 0, stdout, events): events = 'snap <fid>' / 'write <label>' in order."""
        import contextlib
        import io
        from unittest import mock
        events, out = [], io.StringIO()
        post = fake.post_form

        def post_form(path, data, label):
            events.append("write " + label)
            return post(path, data, label)
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(fix_roster_order, "Client",
                                                  lambda key, apply=False: fake))
            stack.enter_context(mock.patch.object(
                fix_roster_order, "snapshot", lambda fid, client, stamp: events.append("snap " + fid)))
            stack.enter_context(mock.patch.object(fake, "post_form", post_form))
            stack.enter_context(mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}))
            stack.enter_context(mock.patch.object(sys, "argv", ["fix_roster_order.py", *argv]))
            stack.enter_context(contextlib.redirect_stdout(out))
            try:
                fix_roster_order.main()
                code = 0
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), events

    def forms(self, **overrides):
        return {fid: overrides.get(fid) or link_form() for fid in self.FIDS}

    def test_the_template_is_planned_and_written_first(self):
        self.assertEqual(list(fix_roster_order.FORMS), self.FIDS)

    def test_dry_run_plans_every_form_and_writes_nothing(self):
        fake = FakeFormClient(self.forms())
        code, out, events = self.run_main(fake)
        self.assertEqual((code, events), (0, []))
        self.assertEqual(out.count("1 of 2 rosters render below somethingNotWorking (q443)"), 5)
        self.assertIn("1. move submit2 (q2) 11 -> 16", out)
        self.assertIn("4. move somethingNotWorking (q443) 10 -> 15", out)
        self.assertNotIn("Girl", out)                 # girls' names never printed

    def test_apply_snapshots_first_probes_then_verifies_and_a_re_run_is_a_no_op(self):
        fid = glow_forms.TEMPLATE
        fake = FakeFormClient({fid: link_form(roster=True)})
        code, out, events = self.run_main(fake, "--form", fid, "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(events[0], "snap " + fid)
        self.assertEqual([e.split(" ")[3] for e in events[1:]], ["submit2", "contact_ids", "belowAre",
                                                                 "somethingNotWorking", "clubRosterFormLink"])
        self.assertIn("probe: q2 holds order", out)
        self.assertIn("re-read: verified - every roster above clubRosterFormLink (q460)", out)
        self.assertEqual(layout.rosters_below(fake.forms[fid]), [])
        self.assertEqual(layout.audit_layout(fake.forms[fid]), [])
        code, out, events = self.run_main(fake, "--form", fid, "--apply")
        self.assertEqual((code, events), (0, []))
        self.assertIn("nothing to do", out)

    def test_form_limits_what_is_read_and_written(self):
        fake = FakeFormClient({self.FIDS[1]: link_form()})     # only Africa exists in the fake
        code, _, events = self.run_main(fake, "--form", self.FIDS[1], "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(events[0], "snap " + self.FIDS[1])
        self.assertTrue(all(self.FIDS[1] in e for e in events))

    def test_a_refusal_on_the_last_form_writes_no_form(self):
        two = link_form()
        two["471"] = {"qid": "471", "type": "control_button", "name": "b2", "order": "30"}
        fake = FakeFormClient(self.forms(**{self.FIDS[-1]: two}))
        code, _, events = self.run_main(fake, "--apply")
        self.assertIn("expected one Submit button, found 2", str(code))
        self.assertEqual(events, [])

    def test_a_form_changed_since_the_preview_is_not_written(self):
        fid = glow_forms.TEMPLATE
        fake = FakeFormClient({fid: link_form()})
        gets = fake.get

        def get(path, **params):
            if path.endswith("/questions") and not hasattr(fake, "seen"):
                fake.seen = True
                return gets(path, **params)
            fake.forms[fid]["490"] = {"qid": "490", "type": "control_checkbox", "name": "LateClub",
                                      "hidden": "Yes", "order": "40"}   # the runner, mid-run
            return gets(path, **params)
        fake.get = get
        code, _, events = self.run_main(fake, "--form", fid, "--apply")
        self.assertIn("changed since the preview - nothing written", str(code))
        self.assertEqual(events, ["snap " + fid])

    def test_the_probe_stops_the_run_when_jotform_renumbers(self):
        # a Jotform that renumbers the form 1..N after an order update: the second
        # target would no longer be an empty slot - stop after the first write
        class Renumbering(FakeFormClient):
            def post_form(self, path, data, label):
                out = super().post_form(path, data, label)
                fid = re.fullmatch(r"/form/(\d+)/.*", path).group(1)
                for n, q in enumerate(sorted(self.forms[fid].values(), key=links.render_key), 1):
                    q["order"] = str(n)
                return out
        fake = Renumbering(self.forms())
        code, out, events = self.run_main(fake, "--apply")
        self.assertIn("after the first write", str(code))
        self.assertIn("does not keep an order update as sent", str(code))
        self.assertEqual([e.split(" ")[0] for e in events], ["snap", "write"])   # the template only
        tpl = fake.forms[glow_forms.TEMPLATE]
        names = rendered(tpl)                          # safe: every roster above Submit, the link too
        self.assertLess(names.index(links.PROBLEM.name), names.index("submit2"))
        self.assertLess(names.index("MoonriseClub"), names.index("submit2"))
        for fid in self.FIDS[1:]:
            self.assertEqual(fake.forms[fid], link_form(), fid)
        # the message says what the re-read shows, and no longer that only one
        # element moved - with a roster renumbered, --undo refuses (it says so)
        self.assertIn("other question(s) changed order", str(code))
        self.assertNotIn("only that element moved", str(code))
        self.assertIn("the re-read shows every roster above Submit", str(code))
        self.assertIn("--undo (below) refuses: a roster's order changed too (q400)", str(code))
        self.assertIn("Revision History", str(code))
        with self.assertRaises(SystemExit) as cm:
            layout.plan_restore(tpl, link_form())
        self.assertIn("roster(s) changed order since the snapshot", str(cm.exception.code))

    def test_a_probe_that_finds_only_the_written_order_off_says_undo_puts_it_back(self):
        # a Jotform that ignores the order sent: nothing else moved - and the
        # re-read is measured, not assumed safe (the roster is still below Submit)
        class Ignoring(FakeFormClient):
            def post_form(self, path, data, label):
                self.writes.append(label)
                return {}
        fid = glow_forms.TEMPLATE
        fake = Ignoring({fid: link_form()})
        code, _, events = self.run_main(fake, "--form", fid, "--apply")
        self.assertEqual([e.split(" ")[0] for e in events], ["snap", "write"])
        self.assertIn("q2 holds 11, sent 16", str(code))
        self.assertNotIn("other question(s) changed order", str(code))
        self.assertIn("no other order changed, so --undo (below) puts that element back", str(code))
        self.assertIn("the re-read shows 1 roster(s) below Submit", str(code))
        self.assertRegex(str(code), rf"--form {fid} --undo \d{{4}}-\d\d-\d\dT\d{{6}}")

        class Nudging(FakeFormClient):              # another (non-roster) order moves as well
            def post_form(self, path, data, label):
                self.forms[fid]["103"]["order"] = "112"
                return super().post_form(path, data, label)
        fake = Nudging({fid: link_form()})
        code, _, _ = self.run_main(fake, "--form", fid, "--apply")
        self.assertIn("1 other question(s) changed order, e.g. q103 12 -> 112", str(code))
        self.assertIn("the --undo dry run (below) plans the way back or refuses", str(code))
        self.assertEqual(move_all(fake.forms[fid], layout.plan_restore(fake.forms[fid], link_form())),
                         link_form())                # here it plans it

    def test_a_write_that_changes_anything_else_fails_the_verify_and_stops(self):
        class Meddling(FakeFormClient):
            def post_form(self, path, data, label):
                out = super().post_form(path, data, label)
                if "somethingNotWorking" in label:                # the last write
                    fid = re.fullmatch(r"/form/(\d+)/.*", path).group(1)
                    self.forms[fid]["350"]["options"] = "Girl One|Girl Two|Girl Nine"
                return out
        fake = Meddling(self.forms())
        code, out, _ = self.run_main(fake, "--apply")
        self.assertIn("MISMATCH after the writes", str(code))
        self.assertIn("1 question(s) changed apart from their order: q350", str(code))
        self.assertNotIn("Girl", str(code) + out)       # compared by hash, never printed
        for fid in self.FIDS[1:]:
            self.assertEqual(fake.forms[fid], link_form(), fid)

    def test_a_failed_write_says_to_re_run_the_dry_run(self):
        class Failing(FakeFormClient):
            def post_form(self, path, data, label):
                if "belowAre" in label:
                    raise fix_roster_order.JotformError(label + ": non-JSON response: '<html>504'")
                return super().post_form(path, data, label)
        fake = Failing(self.forms())
        code, _, _ = self.run_main(fake, "--apply")
        self.assertIn("2 of 4 moves were confirmed", str(code))
        self.assertIn("Re-run the dry run", str(code))
        half = fake.forms[glow_forms.TEMPLATE]           # the re-run finishes it identically
        again = layout.plan_tail_moves(half)
        self.assertEqual(rendered(move_all(half, again)),
                         rendered(move_all(link_form(), layout.plan_tail_moves(link_form()))))

    def test_after_a_stop_the_stopped_runs_stamp_stays_the_rollback(self):
        # run 1 stops part-way; its stop repeats its stamp, and the re-run's
        # plan says the form is part-way, so the re-run's snapshot (of the
        # part-way form) is not taken for the form before the repair
        fid = glow_forms.TEMPLATE

        class Failing(FakeFormClient):
            def post_form(self, path, data, label):
                if "belowAre" in label:
                    raise fix_roster_order.JotformError(label + ": non-JSON response: '<html>504'")
                return super().post_form(path, data, label)
        fake = Failing({fid: link_form()})
        code, out, _ = self.run_main(fake, "--form", fid, "--apply")
        stamp = re.search(r"--undo (\S+)\)", out).group(1)
        self.assertIn(f"the rollback to this form as this run found it: --form {fid} --undo {stamp}",
                      str(code))
        code, out, events = self.run_main(FakeFormClient(fake.forms), "--form", fid)   # the dry run
        self.assertEqual((code, events), (0, []))
        self.assertIn("part-way: 2 element(s) already render after the last roster", out)
        self.assertIn("the --undo stamp that run printed", out)
        _, fresh, _ = self.run_main(FakeFormClient({fid: link_form()}), "--form", fid)
        self.assertNotIn("part-way", fresh)
        # nothing written (a changed form, or an error before the first POST): no rollback line
        for fail in ("drift", "read"):
            class Reading(FakeFormClient):
                gets = 0

                def get(self, path, **params):
                    if path.endswith("/questions"):
                        self.gets += 1
                        if self.gets == 2 and fail == "read":
                            raise fix_roster_order.JotformError(path + ": non-JSON response: '<html>504'")
                        if self.gets == 2:
                            self.forms[fid]["490"] = {"qid": "490", "type": "control_checkbox",
                                                      "name": "LateClub", "hidden": "Yes", "order": "40"}
                    return super().get(path, **params)
            code, _, events = self.run_main(Reading({fid: link_form()}), "--form", fid, "--apply")
            self.assertEqual(events, ["snap " + fid], fail)
            self.assertNotIn("--undo", str(code), fail)
        self.assertIn("nothing was written to it", str(code))

    def test_a_failed_re_read_stops_with_the_count_and_what_was_not_verified(self):
        # a 504 on the probe's GET or on the verify's: stop() with the count, not
        # a bare API error - after the last write the dry run says "nothing to do"
        fid = glow_forms.TEMPLATE
        for writes, confirmed in ((1, "1 of 4"), (4, "4 of 4")):
            class Failing(FakeFormClient):
                failed = False

                def get(self, path, **params):
                    if path.endswith("/questions") and len(self.writes) == writes and not self.failed:
                        self.failed = True
                        raise fix_roster_order.JotformError(path + ": non-JSON response: '<html>504'")
                    return super().get(path, **params)
            fake = Failing({fid: link_form()})
            code, _, events = self.run_main(fake, "--form", fid, "--apply")
            self.assertEqual(len(events), 1 + writes, writes)             # the snapshot, then the writes
            self.assertIn(f"{confirmed} moves were confirmed; the re-read that verifies the form "
                          "did not run", str(code))
            self.assertNotIn("can hide a completed write", str(code))    # every POST answered
            self.assertIn(f"tools/form_status.py --form {fid}", str(code))
            self.assertIn("Re-run the dry run", str(code))
            self.assertRegex(str(code), rf"--form {fid} --undo \S+")

    def test_undo_puts_the_snapshot_orders_back_by_the_same_path(self):
        from unittest import mock
        fid = glow_forms.TEMPLATE
        before = link_form(roster=True)
        fake = FakeFormClient({fid: copy.deepcopy(before)})
        self.assertEqual(self.run_main(fake, "--form", fid, "--apply")[0], 0)
        code, _, _ = self.run_main(fake, "--undo", "2026-09-29T100000")
        self.assertIn("--undo needs --form", str(code))
        with mock.patch.object(fix_roster_order, "load_snapshot", lambda f, stamp: copy.deepcopy(before)):
            code, out, events = self.run_main(fake, "--form", fid, "--undo", "2026-09-29T100000")
            self.assertEqual((code, events), (0, []))                         # a dry run
            self.assertIn("5 element(s) go back to the snapshot's orders", out)
            code, out, events = self.run_main(fake, "--form", fid, "--undo", "2026-09-29T100000", "--apply")
            self.assertEqual(code, 0, out)
            self.assertEqual(events[0], "snap " + fid)
            self.assertEqual([e.split(" ")[3] for e in events[1:]], ["clubRosterFormLink", "somethingNotWorking",
                                                                     "belowAre", "contact_ids", "submit2"])
            self.assertIn("the 2026-09-29T100000 orders are back", out)
            self.assertEqual(fake.forms[fid], before)
            code, out, events = self.run_main(fake, "--form", fid, "--undo", "2026-09-29T100000", "--apply")
            self.assertEqual((code, events), (0, []))
            self.assertIn("nothing to do", out)

    def test_undo_reads_the_snapshot_the_tool_names(self):
        import tempfile
        from unittest import mock
        fid = glow_forms.TEMPLATE
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(fix_roster_order, "REPO", tmp):
            with self.assertRaises(SystemExit) as cm:
                fix_roster_order.load_snapshot(fid, "2026-09-29T100000")
            self.assertIn(f"no snapshot backups/{fid}/questions-2026-09-29T100000.json", str(cm.exception.code))
            os.makedirs(os.path.join(tmp, "backups", fid))
            with open(os.path.join(tmp, "backups", fid, "questions-2026-09-29T100000.json"), "w") as f:
                json.dump(link_form(), f)
            self.assertEqual(fix_roster_order.load_snapshot(fid, "2026-09-29T100000"), link_form())

    def test_verify_catches_a_roster_left_below_and_changed_rules(self):
        qs = link_form()
        moves = layout.plan_tail_moves(qs)
        after = move_all(qs, moves)
        self.assertEqual(fix_roster_order.verify(qs, after, [], [], moves), [])
        rule = [{"id": "1", "type": "field", "link": "Any", "terms": json.dumps([]),
                 "action": json.dumps([{"visibility": "Show", "field": "350"}])}]
        self.assertIn("the rules changed", fix_roster_order.verify(qs, after, rule, [], moves))
        partial = move_all(qs, moves[:1])
        problems = fix_roster_order.verify(qs, partial, [], [], moves)
        self.assertTrue(any("hold another order than sent" in p for p in problems), problems)
        self.assertTrue(any("render below somethingNotWorking" in p for p in problems), problems)


class RosterRepairRunbook(unittest.TestCase):
    """docs/RUNBOOK.md "Rosters above Submit": the runner is paused before the
    merge (the form_status check ships with it), and the procedures whose
    checks expect CLEAN come after the repair."""

    def section(self):
        doc = read(os.path.join(REPO, "docs", "RUNBOOK.md"))
        return doc.split("## Rosters above Submit", 1)[1].split("\n## ", 1)[0]

    def test_the_runner_is_paused_before_the_merge(self):
        text = self.section()
        self.assertNotIn("Before the first `--apply`", text)
        self.assertRegex(text, r"AUTO_SYNC_APPLY=0`?,? (set )?before (merging|the merge)")
        self.assertIn("then back to `1`", text)

    def test_what_expects_clean_waits_for_the_repair(self):
        backlog = {l.split("|")[1].strip(): l for l in read(os.path.join(REPO, "docs", "BACKLOG.md"))
                   .splitlines() if re.match(r"\| (~~45~~|46) \|", l)}
        self.assertIn("after 47's repair", backlog["46"])
        # the partner list (45) was retired before it was deployed; what took its place
        # (the same-name switch, RUNBOOK "Club names two partners share") expects CLEAN too
        self.assertIn("superseded 2026-09-30", backlog["~~45~~"])
        self.assertIn("the same-name switch", " ".join(self.section().split()))


class SameNameRunbook(unittest.TestCase):
    """docs/RUNBOOK.md "Club names two partners share": the one-time switch is
    backed up, previewed and verified, the runner paused around it; the rollback
    is for before the Salesforce reconnect; the quoted warnings are the code's."""

    def section(self):
        doc = read(os.path.join(REPO, "docs", "RUNBOOK.md"))
        self.assertNotIn("## The partner list", doc)           # replaced by this section
        return doc.split("## Club names two partners share", 1)[1].split("\n## ", 1)[0]

    def test_the_switch_is_backed_up_previewed_applied_and_verified_in_that_order(self):
        switch = self.section().split("### The one-time switch", 1)[1].split("\n### ", 1)[0]
        block = switch.split("```bash", 1)[1].split("```", 1)[0]
        lines = [l for l in block.splitlines() if l.strip()]

        def at(fragment, after=-1):
            return next(i for i, l in enumerate(lines) if i > after and fragment in l)

        backup = at("backup_forms.py --form")
        dry = at("--same-name-switch ")
        self.assertNotIn("--apply", lines[dry])
        apply = at("--same-name-switch --apply")
        again = at("sync_attendance_form.py", after=apply)
        self.assertNotIn("--apply", lines[again])
        self.assertNotIn("--same-name-switch", lines[again])     # the form stays switched without it
        status, rendered = at("tools/form_status.py", after=apply), at("--rendered", after=apply)
        self.assertEqual(sorted([backup, dry, apply, again, status, rendered]),
                         [backup, dry, apply, again, status, rendered])
        # the runner is paused for the window, merged code first, and switched back on at the end
        text = " ".join(switch.split())
        self.assertIn("**merge first**", text)
        self.assertLess(text.index("AUTO_SYNC_APPLY=0"), text.index("```bash"))
        self.assertGreater(text.index("AUTO_SYNC_APPLY=1"), text.index("```bash"))
        self.assertNotIn("--q5-change-ok --apply", text)         # the switch needs no second flag

    def test_the_rollback_is_all_forms_with_the_runner_paused_and_only_before_the_reconnect(self):
        text = " ".join(self.section().split("### Rollback", 1)[1].split())
        self.assertIn("only before the Salesforce reconnect", text)
        self.assertLess(text.index("AUTO_SYNC_APPLY=0"), text.index("Revert the merge"))
        self.assertLess(text.index("Revert the merge"), text.index("AUTO_SYNC_APPLY=1"))
        self.assertIn("`restore_conditions.py` is not a rollback here", text)

    def test_the_quoted_warnings_and_flags_are_the_tools_own(self):
        text = " ".join(self.section().split())
        self.assertIn(auto_sync.SF_NAME_CHANGE, text)
        self.assertIn(auto_sync.SAME_NAME_REFUSED, text)
        self.assertIn(glow_sync.SF_NAME_SEP.join(("`<club>", "<partner>`")), text)
        src = read(os.path.join(REPO, "sync_attendance_form.py"))
        for flag in ("--same-name-switch", "--q5-change-ok", "--partner-picker"):
            self.assertIn(flag, text)
            self.assertIn(f'"{flag}"', src)
        self.assertIn("HIDE partner textbox (q331: no rule shows it;", text)
        self.assertIn("HIDE partner textbox (q{PARTNER}: no rule shows it;", src)
        # CLAUDE.md rule 5 and the rename procedure carry the Salesforce step
        self.assertIn("--q5-change-ok", read(os.path.join(REPO, "CLAUDE.md")))
        doc = read(os.path.join(REPO, "docs", "RUNBOOK.md"))
        rename = " ".join(doc.split("## Renaming a club", 1)[1].split("\n## ", 1)[0].split())
        self.assertIn("rename the club's Account to the new text first", rename)
        self.assertIn("--apply --q5-change-ok", rename)

    def test_what_the_runbook_says_the_runner_and_the_tools_do_is_what_they_do(self):
        doc = read(os.path.join(REPO, "docs", "RUNBOOK.md"))
        text = " ".join(self.section().split())
        src = read(os.path.join(REPO, "sync_attendance_form.py"))
        # rules older than the picker: the sync's own line, and ATTENTION - not a repair the
        # runner makes ("the next sync run then rebuilds the rules" read as if it did)
        runner = " ".join(doc.split("## Automatic sync", 1)[1].split("\n## ", 1)[0].split())
        for where in (text, runner):
            self.assertIn(auto_sync.RULES_OLDER, where)
        self.assertNotIn("the next sync run then rebuilds", text)
        self.assertIn("The runner does not apply a rules-only difference: it raises ATTENTION", text)
        # a refused new club: the rename that works, and what the verify step then says
        self.assertIn("tools/rename_club.py --partner … --old … --new … --sheet-only", text)
        rename = " ".join(doc.split("## Renaming a club", 1)[1].split("\n## ", 1)[0].split())
        self.assertIn("--sheet-only --apply", rename)
        self.assertIn("applied-with-problems", runner)
        self.assertIn("counts the club that was not added", runner)
        # the switch: its refusal is the tool's, and the count is checked before applying
        self.assertIn("would keep the plain Club picker entry", text)
        self.assertIn("would keep the plain Club picker entry", src)
        self.assertIn("**one more means stop**", text)
        # the Partner-box hide rides along and is not in SyncLog's detail
        self.assertIn("neither counted nor named in `detail`", runner)
        # the retired design is gone from the prose: no roster is Partner-gated for a part move
        self.assertNotIn("Partner-gates both roster questions", doc)
        self.assertNotIn("same-name clubs additionally require the Partner box",
                         " ".join(read(os.path.join(REPO, "README.md")).split()))


class ContactIdsRunbook(unittest.TestCase):
    """docs/RUNBOOK.md "The names list sent to Salesforce": what it quotes is the
    code's own, the rollout is backed up, previewed, applied and verified in that
    order with the runner paused, the console check prints counts only, and the
    rollback is the constants."""

    def section(self):
        doc = read(os.path.join(REPO, "docs", "RUNBOOK.md"))
        return doc.split("## The names list sent to Salesforce", 1)[1].split("\n## ", 1)[0]

    def test_the_quoted_lines_are_the_tools_own(self):
        text = " ".join(self.section().split())
        self.assertIn(sync.CONTACT_IDS_STALE, text)
        self.assertIn("REQUIRED roster '<club>' (q…: Yes)", text)
        self.assertIn("UPDATE roster '<club>' (q…, N girls; required: Yes)", text)
        for name in ("CONTACT_IDS_FIRST", "CONTACT_IDS_PICKER_OPERAND", "ROSTERS_REQUIRED"):
            self.assertIn(name, text)
            self.assertTrue(hasattr(glow_sync, name), name)
        self.assertIn("question 18: rule 1 of N, the Club picker an operand: yes", text)
        runner = " ".join(read(os.path.join(REPO, "docs", "RUNBOOK.md"))
                          .split("## Automatic sync", 1)[1].split("\n## ", 1)[0].split())
        self.assertIn(auto_sync.CONTACT_IDS_STALE, runner)
        self.assertIn("`REQUIRED roster` line", runner)

    def test_the_rollout_is_backed_up_previewed_applied_and_verified(self):
        text = self.section()
        block = text.split("```bash", 1)[1].split("```", 1)[0]
        lines = [l for l in block.splitlines() if l.strip()]

        def at(fragment, after=-1):
            return next(i for i, l in enumerate(lines) if i > after and fragment in l)

        backup = at("backup_forms.py --form")
        dry = at("sync_attendance_form.py")
        apply = at("--apply")
        again = at("sync_attendance_form.py", after=apply)
        status = at("tools/form_status.py", after=apply)
        rendered = at("--rendered", after=apply)
        self.assertEqual(sorted([backup, dry, apply, again, status, rendered]),
                         [backup, dry, apply, again, status, rendered])
        self.assertNotIn("--apply", lines[dry] + lines[again])
        flat = " ".join(text.split())
        self.assertLess(flat.index("AUTO_SYNC_APPLY=0"), flat.index("```bash"))
        self.assertGreater(flat.rindex("`AUTO_SYNC_APPLY=1`"), flat.index("```bash"))   # back on at the end
        self.assertIn("**hard stop**", flat)

    def test_the_rollout_merges_right_after_the_template(self):
        # the runner syncs from main, and older code puts a rolled-out form back in the old
        # order with its next roster change and reads CLEAN: the merge is a step of its own,
        # between the template and the first regional form, before the runner is switched on
        flat = " ".join(self.section().split())
        m = flat.index("**merge and push**")
        self.assertLess(flat.index("The template goes first"), m)
        self.assertLess(m, flat.index("Then U.S, Latin America, Asia and Africa"))
        self.assertLess(m, flat.index("```bash"))
        self.assertLess(m, flat.rindex("`AUTO_SYNC_APPLY=1`"))
        self.assertIn("nobody applies the template from another checkout", flat)
        # proven with the runner's own refusal, which older code never gives
        plan = auto_sync.parse_plan("DRY RUN (use --apply to write):\n  - REPLACE conditions (40 rules)\n"
                                    f"  ! {auto_sync.CONTACT_IDS_STALE}: rule 39 of 40\n")
        (reason,) = auto_sync.check_bands(plan)
        quoted = flat.split("with the reason \"", 1)[1].split("\"", 1)[0]
        for part in quoted.split(" … "):
            self.assertIn(part, reason)
        skill = " ".join(read(os.path.join(REPO, ".claude", "skills", "live-systems", "SKILL.md")).split())
        self.assertIn("so merge right after the template's rollout", skill)

    def test_the_required_message_is_english_on_four_forms(self):
        # only U.S's translation store holds the `base` entry of Jotform's required text
        # (read 2026-10-01): the rollout's Español check must not read English as a failure
        flat = " ".join(self.section().split())
        self.assertNotIn("in the form's language", flat)
        self.assertNotIn("in the form's language", " ".join(read(os.path.join(REPO, "glow", "sync.py")).split()))
        step7 = flat.split(" 7. ", 1)[1].split("`equal: false`", 1)[0]
        self.assertIn("Spanish on U.S only", step7)
        self.assertIn("template, Africa, Asia and Latin America it stays English", step7)
        self.assertIn("not a failure", step7)
        backlog = read(os.path.join(REPO, "docs", "BACKLOG.md"))
        item = next(l for l in backlog.splitlines() if l.startswith("| 57 |"))
        self.assertIn(f"`{md5('This field is required.')[:8]}…`", item)      # the key, cut (check_secrets)
        self.assertIn("`base`", item)

    def test_the_back_step_cannot_pass_from_the_browsers_memory(self):
        # a default Chrome restores the page from its back-forward cache, where the old rules
        # pass too: the step makes Chrome load it again and reads Jotform's own flag
        flat = " ".join(self.section().split())
        step6 = flat.split(" 6. ", 1)[1].split(" 7. ", 1)[0]
        self.assertIn("addEventListener('unload', () => {})", step6)
        self.assertIn("`bf: false`", step6)
        self.assertIn("--disable-features=BackForwardCache", step6)
        self.assertLess(step6.index("addEventListener"), step6.index("Back"))

    def test_the_language_switcher_residual_says_what_the_required_flag_does(self):
        flat = " ".join(self.section().split())
        residual = flat.split("**Two clubs picked, then the form's own language switcher**", 1)[1]
        for fragment in ("higher in the picker's list", "every shown roster has a tick",
                         "Ticks in one roster only are refused", "Ticks in both still go through",
                         "clears the picker and picks her club again"):
            self.assertIn(fragment, residual)
        backlog = read(os.path.join(REPO, "docs", "BACKLOG.md"))
        item = next(l for l in backlog.splitlines() if l.startswith("| 56 |"))
        self.assertIn("ticks in one roster only are refused", item)
        self.assertIn("higher in the list", item)

    def test_the_console_check_prints_counts_only(self):
        js = self.section().split("```js", 1)[1].split("```", 1)[0].strip()
        returned = js.split("return {", 1)[1].split("};", 1)[0]
        self.assertEqual(re.findall(r"(\w+):", returned), ["shown", "ticked", "q18", "equal", "flagged", "bf"])
        self.assertNotIn("console.log", js)
        self.assertIn("input_18", js)
        self.assertIn("JotForm.fromBFCache", js)

    def test_the_rollback_is_generated(self):
        rollback = " ".join(self.section().split("**Rollback**", 1)[1].split())
        self.assertIn("`False`", rollback)
        self.assertIn("REQUIRED roster '<club>' (q…: No)", rollback)
        self.assertIn("restore_conditions.py", rollback)
        self.assertLess(rollback.index("`False`"), rollback.index("restore_conditions.py"))   # the second path
        # the runner runs main's constants: merged only once every form is rolled back
        self.assertIn("Once every form is rolled back, merge the constants-off commit to `main`, and only then "
                      "set `AUTO_SYNC_APPLY=1`", rollback)
        self.assertIn("Never merge a constants-off commit while any form is still rolled out", rollback)
        skill = " ".join(read(os.path.join(REPO, ".claude", "skills", "live-systems", "SKILL.md")).split())
        self.assertIn("merge the constants-off commit only once every form is rolled back", skill)


import datetime as dt                 # noqa: E402  (the work-log tests below)
import time                           # noqa: E402


def name_store(entries, others=None, pad=0):
    """A translation store as Jotform holds one: [(base text, en text or None)] keyed by
    the md5 of the base text, other languages as {lang: {base text: translation}}, and
    `pad` UI strings ("Label 0001", ...) exact in base and en. Fictional names only."""
    store = {"base": {}, "en": {}}
    for i in range(pad):
        text = f"Label {i:04d}"
        store["base"][md5(text)] = store["en"][md5(text)] = text
    for b, e in entries:
        store["base"][md5(b)] = b
        if e is not None:
            store["en"][md5(b)] = e
    for lang, d in (others or {}).items():
        store[lang] = {md5(b): t for b, t in d.items()}
    return store


class TranslationLookup(unittest.TestCase):
    """glow/translation_lookup.py: the runtime's names dictionary (formTranslation.v2.js:
    setDictionary, trimMultiSpaces, sanitizeKeys, translate's fall-back) and the removal
    plan, on fictional names (docs/plans/2026-10-02-names-and-modules.md)."""

    NAME = "Amara Fennwhistle"

    def test_javascripts_whitespace_simplify_and_key_order(self):
        self.assertEqual(tl.js_trim("﻿　 Amara  "), "Amara")
        self.assertEqual(tl.js_trim("\x85Amara\x1c"), "\x85Amara\x1c")      # whitespace to Python only
        self.assertEqual("\x85Amara\x1c".strip(), "Amara")
        self.assertEqual(tl.simplify(" Amara &amp; Grace<br>Fennwhistle\t\t &gt; "), "Amara & Grace Fennwhistle >")
        # the ideographic space is replaced AFTER the double spaces: one double space survives
        self.assertEqual(tl.simplify("Amara　 Fennwhistle"), "Amara  Fennwhistle")
        self.assertEqual(tl.replace_nbsp("Amara Grace Fennwhistle"), "Amara Grace Fennwhistle")
        self.assertEqual(tl.js_order({"b": 1, "10": 2, "a": 3, "2": 4, "01": 5}), ["2", "10", "b", "a", "01"])

    def test_a_stale_spelling_in_base_and_en_alters_the_exact_name(self):
        for variant in ("Amara  Fennwhistle", "Amara\tFennwhistle", "Amara Fennwhistle",
                        "Amara   Fennwhistle", "Amara\nFennwhistle",
                        "Amara\u202fFennwhistle"):
            store = name_store([(self.NAME, self.NAME), (variant, variant)])
            for skip in tl.BUILDS:
                lookup = tl.Lookup(store, skip_missing=skip)
                result, hits = lookup.trace(self.NAME, "en")
                self.assertEqual(result, variant, repr(variant))
                self.assertEqual(lookup.sources(hits), {md5(variant)}, repr(variant))
            self.assertEqual(tl.altered(store, {self.NAME}), {self.NAME: ["en"]})
            self.assertEqual(tl.removal(store, {self.NAME}), ({md5(variant)}, None))      # only that entry
            self.assertEqual(tl.altered(tl.without(store, {md5(variant)}), {self.NAME}), {})

    def test_an_invisible_mark_is_no_whitespace(self):
        lrm = "Amara‎ Fennwhistle"
        # in base and en alike, its key keeps the mark: the exact name never lands on it
        store = name_store([(self.NAME, self.NAME), (lrm, lrm)])
        self.assertEqual(tl.altered(store, {self.NAME}), {})
        self.assertEqual(tl.removal(store, {self.NAME}), (set(), None))         # nothing that alters no name
        # the exact name in base, the mark in en: sent with the mark
        store = name_store([(self.NAME, lrm)])
        self.assertEqual(tl.altered(store, {self.NAME}), {self.NAME: ["en"]})
        self.assertEqual(tl.removal(store, {self.NAME}), ({md5(self.NAME)}, None))

    def test_the_stale_spelling_wins_in_either_order_and_two_take_two_rounds(self):
        double, tab = "Amara  Fennwhistle", "Amara\tFennwhistle"
        for entries in ([(self.NAME, self.NAME), (double, double)], [(double, double), (self.NAME, self.NAME)]):
            self.assertEqual(tl.Lookup(name_store(entries)).translate(self.NAME, "en"), double)
        store = name_store([(self.NAME, self.NAME), (double, double), (tab, tab)])
        self.assertEqual(tl.Lookup(store).translate(self.NAME, "en"), tab)           # the later one
        self.assertEqual(tl.removal(store, {self.NAME}), ({md5(double), md5(tab)}, None))

    def test_an_exact_entry_or_none_leaves_a_name_alone(self):
        store = name_store([(self.NAME, self.NAME), ("Grace Marrowgate  ", "Grace Marrowgate  ")], pad=3)
        self.assertEqual(tl.altered(store, {self.NAME, "Grace Marrowgate", "Priya Ostrivane"}), {})
        self.assertEqual(tl.removal(store, {self.NAME, "Grace Marrowgate"}), (set(), None))
        # no `en` at all: the runtime builds no dictionary
        self.assertEqual(tl.Lookup({"base": {md5(self.NAME): "Amara  Fennwhistle"}}).dictionary, {})

    def test_a_ui_string_is_never_picked(self):
        store = name_store([(self.NAME, self.NAME), ("Please  Select", "Please  Select"), ("Club Name", "Club Name")],
                           {"es": {"Club Name": "Nombre del club", "Please  Select": "Seleccione"}})
        self.assertEqual(tl.removal(store, {self.NAME}), (set(), None))
        self.assertEqual(tl.Lookup(store).translate("Please Select", "es"), "Seleccione")    # the runtime's own business

    def test_another_languages_entry_is_never_removed(self):
        double = "Amara  Fennwhistle"
        # the stale key translated in Spanish: removing it would orphan the translation
        store = name_store([(self.NAME, self.NAME), (double, double)], {"es": {double: "Amara Fennwhistle (es)"}})
        keys, why = tl.removal(store, {self.NAME})
        self.assertIsNone(keys)
        self.assertIn("another language's entries (es: ", why)
        # a name translated in a language: base/en removal cannot fix it
        store = name_store([(self.NAME, self.NAME)], {"fr": {self.NAME: "Amara Fennwhistle-fr"}})
        self.assertEqual(tl.altered(store, {self.NAME}), {self.NAME: ["fr"]})
        self.assertIn("(fr: ", tl.removal(store, {self.NAME})[1])
        # the fall-back: a Spanish text equal to the name returns its English source
        store = name_store([("Welcome", "Welcome")], {"es": {"Welcome": self.NAME}})
        result, hits = tl.Lookup(store).trace(self.NAME, "en")
        self.assertEqual((result, [h[:2] for h in hits]), ("Welcome", [("match", "es"), ("value", "en")]))
        self.assertIsNone(tl.removal(store, {self.NAME})[0])
        self.assertEqual(tl.target_languages(store), ["en", "es"])                # never base
        # removing base/en entries leaves every other language as it was
        cut = tl.without(store, {md5("Welcome")})
        self.assertEqual((cut["es"], cut["base"], cut["en"]), (store["es"], {}, {}))

    def test_the_two_runtime_builds_differ_on_an_entry_missing_in_en_or_base(self):
        store = name_store([(self.NAME, self.NAME), ("Only In Base", None)], {"es": {"Not In Base": "No en la base"}})
        new, old = tl.Lookup(store, skip_missing=True), tl.Lookup(store, skip_missing=False)
        self.assertNotIn("undefined", new.dictionary["base"])
        self.assertEqual(old.dictionary["base"]["undefined"], "Only In Base")
        self.assertNotIn("undefined", new.dictionary["es"])
        self.assertEqual(old.dictionary["es"]["undefined"], "No en la base")
        # the audits run both builds
        self.assertEqual(tl.altered(store, {"undefined"}, builds=(True,)), {})
        self.assertEqual(tl.altered(store, {"undefined"}), {"undefined": ["es"]})

    def test_what_cannot_be_emulated_or_removed_is_refused(self):
        self.assertIn("not a translation store", tl.check_store({"base": "x"}))
        self.assertIn("no 'base'", tl.check_store({"en": {}}))
        self.assertIn("1 entry is not text", tl.check_store({"base": {"k": 1}, "en": {}}))
        self.assertIsNone(tl.check_store(name_store([(self.NAME, self.NAME)])))
        with self.assertRaises(ValueError):
            tl.Lookup({"en": {}})
        # a no-break space in the option itself: no entry to remove makes it exact
        keys, why = tl.removal(name_store([(self.NAME, self.NAME)]), {"Amara Fennwhistle"})
        self.assertIsNone(keys)
        self.assertIn("no dictionary entry", why)

    def test_each_step_of_the_runtime_is_pinned(self):
        # trimMultiSpaces, THEN sanitizeKeys: the double space moves first, the <br> spelling over it
        br, double = "Amara<br>Fennwhistle", "Amara  Fennwhistle"
        store = name_store([(br, br), (self.NAME, self.NAME), (double, double)])
        self.assertEqual(tl.Lookup(store).translate(self.NAME, "en"), br)
        self.assertEqual(tl.removal(store, {self.NAME}), ({md5(br), md5(double)}, None))
        # the fall-back never walks the language shown: en's own text equal to the name is no match
        store = name_store([("Amara Fenwhistle", double)])
        self.assertEqual(tl.altered(store, {self.NAME}), {})
        self.assertEqual(tl.removal(store, {self.NAME}), (set(), None))
        # another language is keyed by the base text trimmed (the fall-back reads it there)
        store = name_store([(" Welcome ", " Welcome ")], {"es": {" Welcome ": self.NAME}})
        self.assertEqual(tl.altered(store, {self.NAME}), {self.NAME: ["en"]})
        # ... or by the element id when the en text is one
        store = name_store([("Hello", "text_7")], {"es": {"Hello": "Hola"}})
        self.assertEqual(list(tl.Lookup(store).dictionary["es"]), ["text_7"])
        # a fall-back match is traced to the entry it was when the texts were simplified, and to
        # the one now under its key
        store = name_store([("Club Name", "Club Name"), ("Club  Name", "Club  Name")],
                           {"es": {"Club Name": self.NAME, "Club  Name": "Nombre del club"}})
        lookup = tl.Lookup(store)
        result, hits = lookup.trace(self.NAME, "en")
        self.assertEqual(result, "Club  Name")
        self.assertEqual(lookup.sources(hits), {md5("Club Name"), md5("Club  Name")})

    def test_an_option_that_simplifies_to_nothing_is_sent_empty(self):
        # the checkbox reader pushes translate(value) as it is: '' for a value simplifyfWord
        # empties, never the value (that only on a page without FormTranslation)
        store = name_store([(self.NAME, self.NAME)], {"es": {self.NAME: self.NAME}})
        for option in (" ", "&nbsp;", "\ufeff", "\u00a0"):
            self.assertEqual(tl.Lookup(store).translate(option, "en"), "", repr(option))
            self.assertTrue(tl.is_altered(option, ""), repr(option))
            self.assertEqual(tl.altered(store, {option}), {option: ["en", "es"]}, repr(option))
            keys, why = tl.removal(store, {option})
            self.assertIsNone(keys, repr(option))
            self.assertIn("no dictionary entry", why)
        self.assertFalse(tl.is_altered(self.NAME, self.NAME))


class FakeStoreClient:
    """glow.jotform.Client stand-in for tools/fix_name_translations.py: the five forms'
    questions, translation stores and properties in memory. A POST /translations
    replaces each posted language, as Jotform's does. mode "lose": written, the answer
    lost; "nothing": not written, an error; "partial": one removed entry comes back;
    "clobber": written, and Spanish emptied (another language changed by the POST);
    "notstore": written, and the store re-read after it is no store.
    before_post(): called at the POST (what was on disk by then)."""

    def __init__(self, questions, stores, mode=None, before_post=None, primary="en"):
        self.questions, self.stores, self.mode, self.before_post = questions, stores, mode, before_post
        self.props = {fid: {"pagetitle": f"{glow_forms.LIVE[fid]} title",
                            "language": [{"primaryLanguage": primary, "options": "English (US)|Español"}]}
                      for fid in questions}
        self.writes = []

    def get(self, path, **params):
        fid, what = path.split("/")[2], path.rsplit("/", 1)[1]
        if self.mode == "notstore" and self.writes and what == "translations":
            return []
        return copy.deepcopy({"questions": self.questions, "translations": self.stores,
                              "properties": self.props}[what][fid])

    def post_json(self, path, payload, label):
        from glow.jotform import JotformError
        fid = path.split("/")[2]
        if self.before_post:
            self.before_post()
        self.writes.append((path, copy.deepcopy(payload), label))
        if self.mode == "nothing":
            raise JotformError(f"{label}: non-JSON response")
        before = copy.deepcopy(self.stores[fid])
        for lang, d in payload.items():
            self.stores[fid][lang] = copy.deepcopy(d)
        if self.mode == "partial":
            gone = next(k for k in before["en"] if k not in payload["en"])
            self.stores[fid]["en"][gone] = before["en"][gone]
        if self.mode == "clobber":
            self.stores[fid]["es"] = {}
        if self.mode == "lose":
            raise JotformError(f"{label}: non-JSON response")
        return {}

    def post_form(self, path, data, label):
        self.writes.append((path, dict(data), label))
        return {}


def served_page(store):
    """The part of a public page tools/fix_name_translations.py reads: the embedded store."""
    return ('<script>window.allTranslations = {"acceptLanguage":null,"translations":'
            + json.dumps(store) + '};\nFormTranslation.init({"primaryLanguage":"en"});</script>')


class FixNameTranslations(unittest.TestCase):
    """tools/fix_name_translations.py on five fake forms whose stores (cloned, as the live
    ones) hold one stale spelling of an Africa girl's name: what the dry run says, every
    refusal, the write (store saved first, base and en only, re-read, audited, the page
    read and re-rendered), a lost answer, and the rollback. Fictional names; none of them
    may be printed."""

    NAME, DOUBLE = "Amara Fennwhistle", "Amara  Fennwhistle"
    CLUBS = {"Africa": ("Sunrise Club", ["Amara Fennwhistle", "Beatrice Wrenfoldy"]),
             "Asia": ("Lotus Club", ["Grace Marrowgate"]),
             "Latin America": ("Andes Club", ["Priya Ostrivane"]),
             "U.S": ("Liberty Club", ["Hope Thornquibble"])}
    AFRICA = glow_forms.REGIONALS["Africa"]
    GIRLS = [g for _, girls in CLUBS.values() for g in girls]

    def setUp(self):
        import tempfile
        from unittest import mock
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = mock.patch.object(add_translations, "REPO", self.tmp.name)
        self.repo.start()

    def tearDown(self):
        self.repo.stop()
        self.tmp.cleanup()

    def questions(self):
        out = {}
        for fid in fix_name_translations.ORDER:
            region = glow_forms.LIVE[fid]
            clubs = list(self.CLUBS.values()) if region == "template" else [self.CLUBS[region]]
            out[fid] = {str(10 + i): {"type": "control_checkbox", "text": club, "options": "|".join(girls)}
                        for i, (club, girls) in enumerate(clubs)}
            out[fid]["2"] = {"type": "control_button", "text": "Submit"}
        return out

    def store(self, extra=()):
        return name_store([(g, g) for g in self.GIRLS] + [("Club Name", "Club Name"), (self.DOUBLE, self.DOUBLE)]
                          + list(extra), {"es": {"Club Name": "Nombre del club"}},
                          pad=fix_name_translations.STORE_FLOOR)

    def fake(self, **kw):
        return FakeStoreClient(self.questions(), {fid: self.store() for fid in fix_name_translations.ORDER}, **kw)

    def run_main(self, fake, *argv, page=None):
        """(exit code or message, stdout) of main() on `fake`; page(fid): the public page."""
        import contextlib
        import io
        from unittest import mock
        out = io.StringIO()
        page = page or (lambda fid: served_page(fake.stores[fid]))
        with mock.patch.object(fix_name_translations, "Client", lambda key, apply=False: fake), \
                mock.patch.object(fix_name_translations, "public_page", page), \
                mock.patch.object(fix_name_translations.time, "sleep", lambda s: None), \
                mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}), \
                mock.patch.object(sys, "argv", ["fix_name_translations.py", *argv]), \
                contextlib.redirect_stdout(out):
            try:
                fix_name_translations.main()
                code = 0
            except SystemExit as e:
                code = e.code
        for name in self.GIRLS + [self.DOUBLE]:          # counts and club names only, ever
            self.assertNotIn(name, out.getvalue() + str(code))
        return code, out.getvalue()

    def saved(self):
        folder = os.path.join(self.tmp.name, "backups", "translations")
        return sorted(os.path.join(folder, f) for f in os.listdir(folder)) if os.path.isdir(folder) else []

    def test_the_dry_run_counts_and_names_clubs_never_girls(self):
        fake = self.fake()
        code, out = self.run_main(fake)
        self.assertEqual((code, fake.writes), (0, []))
        self.assertIn("Roster options read from all five forms: template 5, U.S 1, Latin America 1, Asia 1, "
                      "Africa 2 (5 distinct texts)", out)
        africa = out.split(f"== Africa {self.AFRICA}", 1)[1]
        self.assertIn("altered today: 1 of this form's 2 roster options, in 1 club(s); its dictionary alters 1 "
                      "option text(s) of the five forms (en 1; on template 1, U.S 0, Latin America 0, Asia 0, "
                      "Africa 1)", africa)
        self.assertIn("clubs: Sunrise Club", africa)
        self.assertEqual(out.count("keys to remove: 1 (base 1, en 1)"), 5)      # every form: all five count
        self.assertEqual(out.count("both runtime builds): 0 option(s) altered"), 5)
        us = out.split("== U.S", 1)[1].split("==", 1)[0]
        self.assertIn("altered today: 0 of this form's 1 roster options;", us)
        self.assertIn("properties[pagetitle] = 'Africa title'", africa)
        self.assertIn("DRY RUN", out)
        # the other forms' options are what make the U.S store's entry go
        options = {fid: opts for fid, opts in fix_name_translations.read_options(fake).items()
                   if glow_forms.LIVE[fid] == "U.S"}
        self.assertEqual(fix_name_translations.plan_form(self.store(), options)["keys"], set())

    def test_every_refusal_writes_nothing(self):
        from unittest import mock
        options = fix_name_translations.read_options(self.fake())

        def refusals(store):
            return " | ".join(fix_name_translations.plan_form(store, options)["refusals"])

        good = self.store()
        self.assertEqual(refusals(good), "")
        self.assertIn("no 'en' dictionary", refusals({k: v for k, v in good.items() if k != "en"}))
        self.assertIn("no 'base' dictionary", refusals({k: v for k, v in good.items() if k != "base"}))
        self.assertIn("below 1000 (a truncated read?)", refusals(name_store([(self.DOUBLE, self.DOUBLE)])))
        bad = copy.deepcopy(good)
        bad["es"]["x"] = 7
        self.assertIn("1 entry is not text", refusals(bad))
        translated = copy.deepcopy(good)
        translated["es"][md5(self.DOUBLE)] = "Amara (es)"
        self.assertIn("another language's entries", refusals(translated))
        with mock.patch.object(fix_name_translations, "MAX_KEYS", 0):
            self.assertIn("1 keys to remove, more than 0", refusals(good))
        with mock.patch.object(fix_name_translations.tl, "removal", lambda *a, **k: (set(), None)):
            self.assertIn("1 option(s) would still be altered after the removal", refusals(good))
        # through main: refused forms are named, nothing is written, --apply included
        fake = self.fake()
        fake.stores[self.AFRICA]["es"][md5(self.DOUBLE)] = "Amara (es)"
        for argv in ((), ("--form", self.AFRICA, "--apply")):
            code, out = self.run_main(fake, *argv)
            self.assertIn("Refused, nothing written: ", str(code))
            self.assertIn("REFUSED: ", out)
            self.assertEqual(fake.writes, [])
        for argv, says in (((("--apply",)), "exactly one --form"),
                           (("--form", self.AFRICA, "--form", glow_forms.TEMPLATE, "--apply"), "exactly one --form"),
                           (("--restore", "x.json"), "exactly one --form"),
                           (("--form", "123"), "Not one of the five forms: 123")):
            code, _ = self.run_main(self.fake(), *argv)
            self.assertIn(says, str(code), argv)
        code, _ = self.run_main(self.fake(primary="es"), "--form", self.AFRICA)
        self.assertIn("primaryLanguage is 'es'", str(code))

    def test_the_write_saves_the_store_first_posts_base_and_en_only_and_verifies(self):
        on_disk = []
        fake = self.fake(before_post=lambda: on_disk.append(self.saved()))
        before = copy.deepcopy(fake.stores[self.AFRICA])
        code, out = self.run_main(fake, "--form", self.AFRICA, "--apply")
        self.assertEqual(code, 0, out)
        (path, payload, label), = fake.writes
        self.assertEqual(path, f"/form/{self.AFRICA}/translations")
        self.assertEqual(set(payload), {"base", "en"})                       # no other language posted
        for lang in ("base", "en"):
            self.assertEqual(payload[lang], {k: v for k, v in before[lang].items() if k != md5(self.DOUBLE)})
        self.assertEqual(fake.stores[self.AFRICA]["es"], before["es"])
        # saved before the POST, whole, readable by its owner only
        self.assertEqual(len(on_disk[0]), 1)
        with open(on_disk[0][0], encoding="utf-8") as f:
            self.assertEqual(json.load(f), before)
        self.assertEqual(os.stat(on_disk[0][0]).st_mode & 0o777, 0o600)
        self.assertTrue(os.path.basename(on_disk[0][0]).startswith(f"{self.AFRICA}-"))
        for line in ("re-read: APPLIED", "audit of the re-read store: 0 of this form's roster options altered",
                     "public page: 0 removed keys still served"):
            self.assertIn(line, out)
        # the other forms are untouched; a second run has nothing to remove on this one
        self.assertEqual(fake.stores[glow_forms.TEMPLATE], self.store())
        code, out = self.run_main(fake, "--form", self.AFRICA)
        self.assertIn("nothing to remove", out)

    def test_a_lost_or_failed_answer_is_re_read_never_guessed(self):
        code, out = self.run_main(self.fake(mode="lose"), "--form", self.AFRICA, "--apply")
        self.assertEqual(code, 0)
        self.assertIn("answer to the POST was lost or not JSON - re-reading", out)
        self.assertIn("re-read: APPLIED - despite the lost answer", out)
        fake = self.fake(mode="nothing")
        code, out = self.run_main(fake, "--form", self.AFRICA, "--apply")
        self.assertIn("re-read: UNCHANGED", out)
        self.assertIn("the store reads unchanged after the POST. Nothing was written; run again.", str(code))
        self.assertEqual(fake.stores[self.AFRICA], self.store())
        code, out = self.run_main(self.fake(mode="partial"), "--form", self.AFRICA, "--apply")
        self.assertIn("re-read: PARTIAL (en: 0 entr(ies) missing, 1 that should be gone, 0 changed)", out)
        self.assertIn(f"--form {self.AFRICA} --restore backups/translations/{self.AFRICA}-", str(code))
        from glow.jotform import JotformError
        # the re-read itself fails: it never says "nothing written", and it names the saved store
        fake = self.fake()
        real_get = fake.get

        def get_after_post(path, **params):
            if fake.writes and path.endswith("/translations"):
                raise JotformError("GET: a cut-off JSON answer, 900 characters, not shown")
            return real_get(path, **params)
        fake.get = get_after_post
        code, _ = self.run_main(fake, "--form", self.AFRICA, "--apply")
        self.assertIn("the write may or may not have happened", str(code))
        self.assertIn(f"the store before the POST is backups/translations/{self.AFRICA}-", str(code))
        self.assertNotIn("nothing written", str(code))

        class Failing:
            def get(self, path, **params):
                raise JotformError("GET: a cut-off JSON answer")
        with self.assertRaises(SystemExit) as cm:
            fix_name_translations.get(Failing(), "/form/1/translations", "the store")
        self.assertEqual(str(cm.exception.code), "Could not read the store (an error or a non-JSON answer from "
                                                 "Jotform) - nothing written; run again")

    def test_a_page_still_serving_a_removed_key_is_re_rendered_once(self):
        fake = self.fake()
        old = copy.deepcopy(fake.stores[self.AFRICA])
        reads = []

        def page(fid):          # Jotform's cache: the old store for PAGE_TRIES reads
            reads.append(fid)
            return served_page(old if len(reads) <= fix_name_translations.PAGE_TRIES else fake.stores[fid])

        code, out = self.run_main(fake, "--form", self.AFRICA, "--apply", page=page)
        self.assertEqual(code, 0, out)
        self.assertEqual([w[0] for w in fake.writes], [f"/form/{self.AFRICA}/translations",
                                                       f"/form/{self.AFRICA}/properties"])
        self.assertEqual(fake.writes[1][1], {"properties[pagetitle]": "Africa title"})
        for line in ("public page: 1 removed keys still served - re-rendering it", "pagetitle re-read: unchanged",
                     "public page: 0 removed keys still served"):
            self.assertIn(line, out)
        # a page that never follows, or cannot be read: the write stands, the run says to check
        for page, says in ((lambda fid: served_page(old), "public page: 1 removed keys still served"),
                           (lambda fid: "<html></html>", "could not read its embedded store")):
            code, out = self.run_main(self.fake(), "--form", self.AFRICA, "--apply", page=page)
            self.assertIn("could not be shown to serve it", str(code))
            self.assertIn(says, out)

    def test_a_re_read_with_another_language_changed_or_no_store_is_partial(self):
        # CLAUDE.md rule 9: a POST that changed a language it was not sent is never "applied"
        fake = self.fake(mode="clobber")
        code, out = self.run_main(fake, "--form", self.AFRICA, "--apply")
        self.assertIn("re-read: PARTIAL (other languages changed: es)", out)
        self.assertIn(f"Stopped: the store reads partial after the POST. Put it back: --form {self.AFRICA} "
                      f"--restore backups/translations/{self.AFRICA}-", str(code))
        self.assertNotIn("audit of the re-read store", out)
        code, out = self.run_main(self.fake(mode="notstore"), "--form", self.AFRICA, "--apply")
        self.assertIn("re-read: PARTIAL (the re-read store is not a translation store)", out)
        self.assertIn("Stopped: the store reads partial after the POST", str(code))
        # the restore's POST too
        fake, earlier = self.fake(), set(self.saved())
        self.assertEqual(self.run_main(fake, "--form", self.AFRICA, "--apply")[0], 0)
        (saved,) = set(self.saved()) - earlier
        fake.mode = "clobber"
        code, out = self.run_main(fake, "--form", self.AFRICA, "--restore", saved, "--apply")
        self.assertIn("re-read: PARTIAL (other languages changed: es)", out)
        self.assertIn("Stopped: the store reads partial after the restore POST - compare it with "
                      f"backups/translations/{self.AFRICA}-", str(code))
        self.assertNotIn("public page:", out)

    def test_the_audit_of_the_re_read_store_stops_the_run(self):
        import contextlib
        import io
        # a plan that missed a stale spelling (the tab one): the POST lands as planned, the
        # audit of the re-read store still finds the name altered and stops before the page
        tab = "Amara\tFennwhistle"
        fake = self.fake()
        store = self.store(extra=[(tab, tab)])
        fake.stores[self.AFRICA] = copy.deepcopy(store)
        plan = {"keys": {md5(self.DOUBLE)}, "refusals": []}
        out, pages = io.StringIO(), []
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as cm:
            fix_name_translations.apply_form(fake, self.AFRICA, store, plan, fix_name_translations.read_options(fake),
                                             "s", page_of=lambda fid: pages.append(fid) or "", sleep=lambda s: None)
        self.assertIn("Stopped: the re-read store still alters roster options", str(cm.exception.code))
        self.assertIn("re-read: APPLIED", out.getvalue())
        self.assertIn("audit of the re-read store: 1 of this form's roster options altered, 1 option text(s) "
                      "of the five forms", out.getvalue())
        self.assertEqual(pages, [])
        for name in self.GIRLS + [self.DOUBLE, tab]:
            self.assertNotIn(name, out.getvalue() + str(cm.exception.code))

    def test_a_restore_with_nothing_to_put_back_or_no_store_writes_nothing(self):
        fake = self.fake()
        same = os.path.join(self.tmp.name, "backups", "translations", f"{self.AFRICA}-same-before.json")
        os.makedirs(os.path.dirname(same))
        with open(same, "w", encoding="utf-8") as f:
            json.dump(fake.stores[self.AFRICA], f)
        code, out = self.run_main(fake, "--form", self.AFRICA, "--restore", same, "--apply")
        self.assertEqual((code, fake.writes), (0, []))
        self.assertIn("base: 0 entr(ies) put back", out)
        self.assertIn("nothing to restore", out)
        fake.stores[self.AFRICA] = ["not", "a", "store"]
        code, out = self.run_main(fake, "--form", self.AFRICA, "--restore", same, "--apply")
        self.assertIn("Refused, nothing written: the form's store: not a translation store", str(code))
        self.assertEqual(fake.writes, [])

    def test_the_re_render_failing_after_the_post_never_says_nothing_written(self):
        from glow.jotform import JotformError
        stale_page = None

        def failing(fake, step):
            """fake with the re-render's `step` failing once the store POST has landed:
            "props" the first properties read, "post" the pagetitle POST, "again" its re-read."""
            real_get, real_post = fake.get, fake.post_form
            reads = []

            def get(path, **params):
                if fake.writes and path.endswith("/properties"):
                    reads.append(path)
                    if step == "props" or (step == "again" and len(reads) == 2):
                        raise JotformError("GET: a cut-off JSON answer, 900 characters, not shown")
                return real_get(path, **params)

            def post_form(path, data, label):
                real_post(path, data, label)
                if step == "post":
                    raise JotformError(f"{label}: non-JSON response")
            fake.get, fake.post_form = get, post_form
            return fake

        for step in ("props", "post", "again"):
            fake = self.fake()
            stale_page = served_page(copy.deepcopy(fake.stores[self.AFRICA]))     # the page never follows
            code, out = self.run_main(failing(fake, step), "--form", self.AFRICA, "--apply",
                                      page=lambda fid: stale_page)
            self.assertIn("re-read: APPLIED", out, step)
            self.assertNotIn(md5(self.DOUBLE), fake.stores[self.AFRICA]["en"])       # the store is written
            self.assertIn("The store is fixed but the public page could not be shown to serve it", str(code), step)
            self.assertNotIn("nothing written", str(code) + out, step)
            self.assertIn("the re-render could not be done or confirmed", out, step)
            self.assertNotIn("cut-off", out + str(code))                             # Jotform's answer never echoed
        # the restore: the same accurate exit after its POST
        fake, earlier = self.fake(), set(self.saved())
        self.assertEqual(self.run_main(fake, "--form", self.AFRICA, "--apply")[0], 0)
        (saved,) = set(self.saved()) - earlier
        stale_page = served_page(copy.deepcopy(fake.stores[self.AFRICA]))           # without the restored key
        fake.writes.clear()
        code, out = self.run_main(failing(fake, "props"), "--form", self.AFRICA, "--restore", saved, "--apply",
                                  page=lambda fid: stale_page)
        self.assertIn("re-read: APPLIED", out)
        self.assertIn(md5(self.DOUBLE), fake.stores[self.AFRICA]["en"])
        self.assertIn("Restored, but the public page could not be shown to serve it", str(code))
        self.assertNotIn("nothing written", str(code) + out)

    def test_the_restore_puts_back_what_was_removed_in_the_saved_order(self):
        fake = self.fake()
        original = copy.deepcopy(fake.stores[self.AFRICA])
        self.assertEqual(self.run_main(fake, "--form", self.AFRICA, "--apply")[0], 0)
        (saved,) = self.saved()
        fake.stores[self.AFRICA]["en"]["k-new"] = "Added Since"            # kept by the restore
        fake.stores[self.AFRICA]["en"][md5("Label 0000")] = "Label zero"   # changed since: kept too
        fake.writes.clear()
        code, out = self.run_main(fake, "--form", self.AFRICA, "--restore", saved)
        self.assertEqual((code, fake.writes), (0, []))
        self.assertIn("base: 1 entr(ies) put back; 0 changed since and 0 added since", out)
        self.assertIn("en: 1 entr(ies) put back; 1 changed since and 1 added since", out)
        self.assertIn("after the restore: 1 of this form's roster options altered again, in 1 club(s)", out)
        code, out = self.run_main(fake, "--form", self.AFRICA, "--restore", saved, "--apply")
        self.assertEqual(code, 0, out)
        (_, payload, _), = fake.writes
        self.assertEqual(set(payload), {"base", "en"})
        self.assertEqual(list(payload["base"]), list(original["base"]))
        self.assertEqual(list(payload["en"]), list(original["en"]) + ["k-new"])
        self.assertEqual(payload["en"][md5("Label 0000")], "Label zero")     # not the saved text
        self.assertEqual(payload["base"][md5("Label 0000")], "Label 0000")
        self.assertIn("public page: 0 restored keys not yet served", out)
        self.assertEqual(len(self.saved()), 2)                               # the store before the restore too
        # refusals: another form's file, a truncated one
        other = os.path.join(os.path.dirname(saved), f"{glow_forms.TEMPLATE}-x-before.json")
        with open(other, "w", encoding="utf-8") as f:
            json.dump(original, f)
        code, _ = self.run_main(self.fake(), "--form", self.AFRICA, "--restore", other, "--apply")
        self.assertIn("is not a saved store of form", str(code))
        short = os.path.join(os.path.dirname(saved), f"{self.AFRICA}-short-before.json")
        with open(short, "w", encoding="utf-8") as f:
            json.dump(name_store([(self.DOUBLE, self.DOUBLE)]), f)
        code, _ = self.run_main(self.fake(), "--form", self.AFRICA, "--restore", short, "--apply")
        self.assertIn("below 1000", str(code))


class ModuleValues(unittest.TestCase):
    """The module dropdowns' calcValues (glow/sync.py MODULE_CALC_VALUES): their own options
    after a single-select's empty slot, written and kept in step by the sync, cleared by
    the generated rollback, never applied by the runner unattended; on SameNameFlow's
    fake Africa form."""

    ROSTER, QIDS, MODULES, texts = SameNameFlow.ROSTER, SameNameFlow.QIDS, SameNameFlow.MODULES, SameNameFlow.texts
    LINES = ["UPDATE module dropdown (q14, year 1: calcValues = its 1 options)",
             "UPDATE module dropdown (q92, year 2: calcValues = its 2 options)",
             "UPDATE module dropdown (q93, year 3: calcValues = its 1 options)"]

    def setUp(self):
        SameNameFlow.setUp(self)

    def tearDown(self):
        SameNameFlow.tearDown(self)

    def run_sync(self, fake, *extra, roster=None):
        return SameNameFlow.run_sync(self, fake, *extra, roster=roster)

    def summary(self, fake, *extra, **kw):
        return SameNameFlow.summary(self, fake, *extra, **kw)

    def form(self, calc=True):
        qs, wire = SameNameFlow.form(self, switched=True)
        if not calc:
            for q in sync.MODULES.values():
                del qs[q]["calcValues"]
        return qs, wire

    def test_the_layout_is_the_year_dropdowns(self):
        self.assertEqual(glow_sync.module_calc_values(["Core 2", "Elective - Healthy GLOW"]),
                         "|Core 2|Elective - Healthy GLOW")
        self.assertEqual(glow_sync.module_calc_values(["Core 1"]).split("|"), ["", "Core 1"])   # the |1|2|3 shape
        self.assertEqual(glow_sync.aligned_calc_values([]), "")
        self.assertEqual(glow_sync.dropdown_options({"options": "A||B|"}), ["A", "B"])
        from unittest import mock
        with mock.patch.object(glow_sync, "MODULE_CALC_VALUES", False):
            self.assertEqual(glow_sync.module_calc_values(["Core 1"]), "")

    def test_a_form_without_them_gets_one_write_per_dropdown_then_nothing(self):
        qs, wire = self.form(calc=False)
        fake = FakeForm(qs, wire)
        summary, out = self.summary(fake)
        self.assertEqual(fake.calls, self.LINES)
        self.assertIn("(conditions unchanged - skipping the rewrite)", out)
        self.assertEqual([w[1:] for w in fake.writes],
                         [("/question/14", {"question[calcValues]": "|Core 1"}),
                          ("/question/92", {"question[calcValues]": "|Core 2|Elective - Healthy GLOW"}),
                          ("/question/93", {"question[calcValues]": "|Core 3"})])
        want = [{"qid": "14", "year": "1", "modules": 1}, {"qid": "92", "year": "2", "modules": 2},
                {"qid": "93", "year": "3", "modules": 1}]
        self.assertEqual(summary["module_values"], want)
        plan = auto_sync.parse_plan(out)
        self.assertEqual((plan["modules"], auto_sync.plan_from_summary(summary)["modules"]), (want, want))
        self.assertEqual(auto_sync.changes(plan), 3)
        # applied, the form is in step: nothing more
        fake = FakeForm(qs, wire, apply=True)
        self.assertEqual(self.run_sync(fake, "--apply")[0], 0)
        fake = FakeForm(*self.form())
        self.assertEqual((self.run_sync(fake)[0], fake.calls), (0, []))

    def test_a_dropdown_edited_in_the_builder_is_realigned(self):
        for calc in ("|Elective - Healthy GLOW|Core 2", "|Core 2", "|||", ""):
            qs, wire = self.form()
            qs["92"]["calcValues"] = calc
            fake = FakeForm(qs, wire)
            self.run_sync(fake)
            self.assertEqual(fake.calls, [self.LINES[1]], calc)
        qs, wire = self.form()
        qs["92"]["options"] += "|Elective - STEM"                         # a module added in the builder
        fake = FakeForm(qs, wire)
        self.run_sync(fake)
        self.assertIn("UPDATE module dropdown (q92, year 2: calcValues = its 3 options)", fake.calls)
        self.assertEqual(fake.writes[0][2], {"question[calcValues]": "|Core 2|Elective - Healthy GLOW|Elective - STEM"})

    def test_the_rollback_clears_them(self):
        from unittest import mock
        carrying = self.form()                                             # built with the constant on
        with mock.patch.object(glow_sync, "MODULE_CALC_VALUES", False):
            fake = FakeForm(*carrying)
            summary, out = self.summary(fake)
            self.assertEqual(fake.calls, [l.split(": calcValues")[0] + ": calcValues cleared)" for l in self.LINES])
            self.assertEqual({w[2]["question[calcValues]"] for w in fake.writes}, {""})
            self.assertEqual([m["modules"] for m in auto_sync.parse_plan(out)["modules"]], [0, 0, 0])
            fake = FakeForm(*self.form(calc=False))
            self.assertEqual((self.run_sync(fake)[0], fake.calls), (0, []))

    def test_the_runner_never_applies_them(self):
        text = ("Roster: 4 active clubs in Africa (8 girls); 300 clubs overall\n\nDRY RUN (use --apply to write):\n"
                + "".join(f"  - {l}\n" for l in self.LINES))
        plan = auto_sync.parse_plan(text)
        self.assertIn(", module values on 3 dropdown(s)", auto_sync.plan_summary(plan))
        (reason,) = auto_sync.check_bands(plan)
        self.assertIn("would write the calcValues of 3 module dropdown(s) (q14, q92, q93) - never unattended", reason)
        busy = text + "  - CREATE roster 'Gamma Club' (2 girls)\n"
        for t in (text, busy):
            run = AutoSyncPlan.run_region(self, t, apply=True)
            self.assertEqual((run.synced, [r[7] for r in run.results]), ([False], ["attention"]))
            self.assertIn("- MODULE values q92 (year 2: 2 modules)", run.attention[0][1])
        cleared = text.replace("= its 1 options)", "cleared)")
        self.assertIn("- MODULE values q14 (year 1: cleared)", AutoSyncPlan.run_region(self, cleared, apply=True)
                      .attention[0][1])
        self.assertFalse(auto_sync.MODULE_RX.match("  - UPDATE module dropdown (q14, year 1: calcValues)"))
        # the line is the sync's own
        joined = re.sub(r'"\s*\n\s*"', "", read(os.path.join(REPO, "sync_attendance_form.py")))
        for fragment in ('f"UPDATE module dropdown (q{mqid}, year {year}: calcValues "',
                         '(f"= its {len(options)} options)" if want else "cleared)")'):
            self.assertIn(fragment, joined)


class ModuleAndNamesAudit(unittest.TestCase):
    """tools/form_status.py: the module dropdowns' calcValues (as MODULE_CALC_VALUES says)
    and the form's names dictionary (emulated), through the API and on the served page;
    the runner's verify step reads both. Fictional names; counts and club names only."""

    def form(self):
        return SameNameFlow.form(SameNameFlow(), switched=True)

    def test_the_module_audit_follows_the_constant(self):
        from unittest import mock
        qs, _ = self.form()
        problems, summary = form_status.audit_module_values(qs)
        self.assertEqual(problems, [])
        self.assertEqual(summary, {"14": {"options": 1, "aligned": True}, "92": {"options": 2, "aligned": True},
                                   "93": {"options": 1, "aligned": True}})
        bare = copy.deepcopy(qs)
        for q in sync.MODULES.values():
            bare[q]["calcValues"] = ""
        shifted = copy.deepcopy(qs)
        shifted["92"]["calcValues"] = "|Elective - Healthy GLOW|Core 2"
        problems = form_status.audit_module_values(bare)[0]
        self.assertEqual(len(problems), 3)
        self.assertIn("module dropdown q14 (year 1): no calcValues - question 98 (module_id, what Salesforce "
                      "stores) copies the visible text", problems[0])
        (problem,) = form_status.audit_module_values(shifted)[0]
        self.assertIn("q92 (year 2): calcValues out of line with its 2 options (3 values) - question 98 would "
                      "send another module", problem)
        gone = copy.deepcopy(qs)
        del gone["93"]
        self.assertEqual(form_status.audit_module_values(gone)[0], ["module dropdown q93 (year 3) is not on the form"])
        with mock.patch.object(glow_sync, "MODULE_CALC_VALUES", False):
            self.assertEqual((form_status.audit_module_values(bare)[0], form_status.audit_module_values(qs)[0]),
                             ([], []))
            (problem,) = form_status.audit_module_values(shifted)[0]
            self.assertIn("a sync apply by hand clears them", problem)
        self.assertEqual(form_status.module_values_line(summary),
                         "q14 aligned (1 options), q92 aligned (2 options), q93 aligned (1 options)")

    def test_the_names_audit_counts_and_names_clubs_never_girls(self):
        qs, _ = self.form()
        options = form_status.roster_options(qs)
        self.assertEqual(len(options), 8)
        clean = served_store(qs)
        self.assertEqual(form_status.audit_names("999", options, clean)[0], [])
        stale = served_store(qs, {md5("Jane  Doe"): ("Jane  Doe", "Jane  Doe")})
        (problem,), summary = form_status.audit_names("999", options, stale)
        self.assertIn("names dictionary: 1 roster option(s) in 1 club(s) are altered by the form's own "
                      "translation dictionary (en 1)", problem)
        self.assertIn("tools/fix_name_translations.py --form 999", problem)
        self.assertEqual((summary["altered"], summary["clubs"], summary["by_language"]), (1, ["Alpha Club"], {"en": 1}))
        self.assertNotIn("Jane", problem + json.dumps(summary))
        self.assertEqual(form_status.names_line(summary),
                         "1 of 8 roster options altered (2 language(s) checked) in 1 club(s): Alpha Club")
        problems, summary = form_status.audit_names("999", options, "the store could not be read")
        self.assertEqual((problems, summary), ([], {"checked": False, "why": "the store could not be read"}))
        self.assertEqual(form_status.names_line(summary), "not checked (the store could not be read)")

    def test_the_report_and_the_runners_verify_read_both(self):
        qs, wire = self.form()
        for q_id, q in qs.items():
            q.setdefault("qid", q_id)
        stale = served_store(qs, {md5("Jane  Doe"): ("Jane  Doe", "Jane  Doe")})

        def report(store, questions=qs):
            class Fake:
                def get(self, path, **params):
                    if path.endswith("/questions"):
                        return copy.deepcopy(questions)
                    if path.endswith("/properties"):
                        return {"conditions": wire, "language": [{"options": "English (US)|Español",
                                                                   "primaryLanguage": "en"}],
                                "clearFieldOnHide": "disable"}
                    if path.endswith("/translations"):
                        if isinstance(store, Exception):
                            raise store
                        return copy.deepcopy(store)
                    return {"title": "t", "status": "ENABLED", "count": "0"}
            return form_status.form_report(glow_forms.TEMPLATE, Fake(), {})

        clean = {"error_conditions": 0, "salesforce": True, "languages": ["a"] * 12,
                 "region_check": {"missing_from_form": [], "not_in_roster": [], "rosters_out_of_date": []}}
        rep = report(stale)
        self.assertEqual(rep["names_dictionary"]["altered"], 1)
        self.assertEqual([p for p in rep["rule_problems"] if p.startswith("names dictionary")],
                         [p for p in rep["rule_problems"] if "fix_name_translations" in p])
        problems, notes = auto_sync.verify_report(dict(clean, **{k: rep[k] for k in ("rule_problems", "names_dictionary")}))
        self.assertTrue(any("names dictionary: 1 roster option(s)" in p for p in problems))
        rep = report(served_store(qs))
        self.assertEqual((rep["names_dictionary"]["altered"], [p for p in rep["rule_problems"] if "names" in p]), (0, []))
        from glow.jotform import JotformError
        rep = report(JotformError("GET: a cut-off JSON answer, 900 characters, not shown"))
        self.assertFalse(rep["names_dictionary"]["checked"])
        problems, notes = auto_sync.verify_report(dict(clean, rule_problems=[], names_dictionary=rep["names_dictionary"]))
        self.assertEqual(problems, [])                                # a note, never applied-unverified
        self.assertIn("names dictionary not checked (the store could not be read", notes[0])
        self.assertNotIn("cut-off", json.dumps(rep["names_dictionary"]))
        # the module half: a dropdown without calcValues is a rule problem, so the verify step fails
        rep = report(served_store(qs))
        self.assertEqual(rep["module_values"]["14"], {"options": 1, "aligned": True})
        self.assertFalse([p for p in rep["rule_problems"] if p.startswith("module dropdown")])
        bare = copy.deepcopy(qs)
        bare["14"]["calcValues"] = ""
        rep = report(served_store(qs), bare)
        self.assertFalse(rep["module_values"]["14"]["aligned"])
        self.assertTrue(any(p.startswith("module dropdown q14 (year 1): no calcValues") for p in rep["rule_problems"]))
        problems, _ = auto_sync.verify_report(dict(clean, **{k: rep[k] for k in ("rule_problems", "names_dictionary")}))
        self.assertTrue(any("module dropdown q14" in p for p in problems))

    def test_the_served_page_is_read_for_the_module_values_and_the_names(self):
        from unittest import mock
        qs, _ = self.form()
        rosters = sorted((q for q, v in qs.items() if v.get("type") == "control_checkbox"), key=int)
        summary = form_status.audit_module_values(qs)[1]

        def rendered(page, qs_=qs):
            r = {"id": "999", "roster_qids": rosters, "module_values": form_status.audit_module_values(qs_)[1]}
            boxes = "".join(f'<input type="checkbox" id="input_{q}_{i}" value="{o}">'
                            for q in rosters for i, o in enumerate(qs[q]["options"].split("|")))
            return form_status.rendered_module_problems(r, page) + form_status.rendered_names_problems(r, boxes + page), r

        problems, r = rendered(served_modules_and_store(qs))
        self.assertEqual(problems, [])
        self.assertEqual(r["rendered_modules"]["92"], {"options": 2, "aligned": 2, "differ": 0, "missing": 0})
        self.assertEqual(r["rendered_names"], {"checked": True, "options": 8, "altered": 0, "languages": 2,
                                               "by_language": {}})
        bare = copy.deepcopy(qs)
        for q in sync.MODULES.values():
            bare[q]["calcValues"] = ""
        problems, _ = rendered(served_modules_and_store(bare))
        self.assertEqual(len(problems), 3)
        self.assertIn("rendered page: module dropdown q14: 1 of 1 options carry no data-calcvalue", problems[0])
        with mock.patch.object(glow_sync, "MODULE_CALC_VALUES", False):
            self.assertEqual(rendered(served_modules_and_store(bare), bare)[0], [])
        more = copy.deepcopy(qs)
        more["92"]["options"] += "|Elective - STEM"
        more["92"]["calcValues"] += "|Elective - STEM"
        (problem,), _ = rendered(served_modules_and_store(qs), more)
        self.assertIn("rendered page lists 2 of module dropdown q92's 3 options", problem)
        # the embedded dictionary, not the API's: a page from before the fix is caught
        stale = served_store(qs, {md5("Jane  Doe"): ("Jane  Doe", "Jane  Doe")})
        (problem,), r = rendered(served_modules_and_store(qs, stale))
        self.assertIn("rendered page: the embedded dictionary alters 1 of the 8 roster options it serves (1 "
                      "roster(s))", problem)
        self.assertNotIn("Jane", problem + json.dumps(r))
        # a value served html-escaped is looked up as the option it is; a box outside the rosters is no option
        page = ('<input type="checkbox" id="input_7_0" value="Amara O&#x27;Fennwhistle &amp; Grace">'
                '<input type="checkbox" id="input_8_0" value="Not a roster">')
        self.assertEqual(form_status.rendered_options(page, ["7"]), [("7", "q7", "Amara O'Fennwhistle & Grace")])
        problems, r = rendered("<html></html>")
        self.assertEqual(len(problems), 5)                # never vouched for: three selects, clearFieldOnHide, the store
        self.assertIn("no select for module dropdown q14", problems[0])
        self.assertIn("no JotForm.clearFieldOnHide on the public page", problems[3])
        self.assertIn("no embedded translation store", problems[4])
        self.assertFalse(r["rendered_names"]["checked"])
        self.assertEqual(r["rendered_shape"], {"clearFieldOnHide": None, "multi_select": []})
        self.assertEqual(summary["14"]["options"], 1)

    def test_the_module_shape_is_pinned(self):
        """docs/plans/2026-10-06-module-selection.md (a): one required single-select per step of
        the chain, the year visible, and the form-level clearFieldOnHide as glow/sync.py says;
        an unknown value is reported as not read, never as "cleared"."""
        qs, _ = self.form()
        props = {"clearFieldOnHide": glow_sync.CLEAR_FIELD_ON_HIDE}
        self.assertEqual(glow_sync.CLEAR_FIELD_ON_HIDE, "disable")
        problems, summary = form_status.audit_module_shape(qs, props)
        self.assertEqual(problems, [])
        self.assertEqual(form_status.module_shape_line(summary),
                         "year q94 single-select required; modules q14/q92/q93 single-select required; "
                         "sessions q15/q95/q96/q97 single-select required; clearFieldOnHide disable")
        self.assertEqual(summary["module"]["92"], {"single": True, "required": True, "dropdown": True})
        self.assertEqual(summary["year"]["94"]["visible"], True)
        self.assertEqual(sorted(summary["session"]), sorted(sync.WEEKS.values()))

        def only(change, *fragments):
            changed = copy.deepcopy(qs)
            change(changed)
            found, s = form_status.audit_module_shape(changed, props)
            self.assertEqual(len(found), 1, found)
            for fragment in fragments:
                self.assertIn(fragment, found[0])
            self.assertIn("never a sync apply - the sync does not write it", found[0])
            return s
        s = only(lambda q: q["92"].__setitem__("multipleSelections", "Yes"),
                 "module dropdown q92 (year 2) is a multi-select: a mentor could send two modules; question 98 "
                 "would run them together")
        self.assertIn("modules q14/q92/q93: q92 multi-select;", form_status.module_shape_line(s))
        only(lambda q: q["94"].__setitem__("required", "No"), "year dropdown q94 is not required: a blank year")
        only(lambda q: q["15"].__setitem__("required", "No"),
             "session dropdown q15 (8 sessions) is not required: a blank session reaches Salesforce")
        only(lambda q: q["97"].__setitem__("multipleSelections", "Yes"),
             "session dropdown q97 (15 sessions) is a multi-select: a mentor could send two sessions; question 100")
        only(lambda q: q["94"].__setitem__("hidden", "Yes"), "year dropdown q94 is hidden: the chain starts visible")
        s = only(lambda q: q.pop("96"), "session dropdown q96 (14 sessions) is not on the form")
        self.assertIn("sessions q15/q95/q96/q97: q96 missing;", form_status.module_shape_line(s))
        only(lambda q: q["14"].__setitem__("type", "control_radio"),
             "module dropdown q14 (year 1) is a control_radio, not a dropdown")
        # clearFieldOnHide: each value its own line; a value nobody has read is never "cleared"
        for value, fragment in (("dontClear", "a module dropdown hidden by the Year rule would keep its answer at submit"),
                                ("enable", "rejected 2026-09-30: the loop limit drops to 3 (DECISIONS)"),
                                (None, "a value whose runtime behaviour has not been read - do not treat hidden "
                                       "answers as cleared"),
                                ("Disable", "a value whose runtime behaviour has not been read")):
            (problem,), s = form_status.audit_module_shape(qs, {} if value is None else {"clearFieldOnHide": value})
            self.assertIn(f"clearFieldOnHide is {value!r}, not 'disable': {fragment}", problem)
            self.assertEqual(s["clearFieldOnHide"], value)
        self.assertTrue(form_status.module_shape_line(form_status.audit_module_shape(qs, {})[1])
                        .endswith("; clearFieldOnHide unset"))
        # the shape audit flags shape only: a dropdown without calcValues is the values audit's
        bare = copy.deepcopy(qs)
        bare["14"]["calcValues"] = ""
        self.assertEqual(form_status.audit_module_shape(bare, props)[0], [])

    def test_the_report_and_the_runners_verify_read_the_shape(self):
        qs, wire = self.form()
        qs["2"] = {"type": "control_button", "text": "Submit", "name": "submit2", "order": "60"}
        for q_id, q in qs.items():
            q.setdefault("qid", q_id)

        def report(props_extra, questions=qs):
            class Fake:
                def get(self, path, **params):
                    if path.endswith("/questions"):
                        return copy.deepcopy(questions)
                    if path.endswith("/properties"):
                        return {"conditions": wire, "language": [{"options": "English (US)|Español",
                                                                   "primaryLanguage": "en"}], **props_extra}
                    if path.endswith("/translations"):
                        return served_store(qs)
                    return {"title": "t", "status": "ENABLED", "count": "0"}
            return form_status.form_report(glow_forms.TEMPLATE, Fake(), {})

        clean = {"error_conditions": 0, "salesforce": True, "languages": ["a"] * 12,
                 "region_check": {"missing_from_form": [], "not_in_roster": [], "rosters_out_of_date": []}}
        rep = report({"clearFieldOnHide": "disable"})
        self.assertEqual(rep["module_shape"]["clearFieldOnHide"], "disable")
        self.assertEqual([p for p in rep["rule_problems"] if "clearFieldOnHide" in p or "dropdown q" in p], [])
        self.assertEqual(auto_sync.verify_report(dict(clean, **{k: rep[k] for k in ("rule_problems", "names_dictionary")}))[0], [])
        rep = report({"clearFieldOnHide": "dontClear"})
        self.assertTrue(any(p.startswith("clearFieldOnHide is 'dontClear', not 'disable'") for p in rep["rule_problems"]))
        problems, _ = auto_sync.verify_report(dict(clean, **{k: rep[k] for k in ("rule_problems", "names_dictionary")}))
        self.assertTrue(any("clearFieldOnHide is 'dontClear'" in p for p in problems))   # the verify step fails
        rep = report({})                                                                  # unset: not read, a problem
        self.assertIsNone(rep["module_shape"]["clearFieldOnHide"])
        self.assertTrue(any("do not treat hidden answers as cleared" in p for p in rep["rule_problems"]))
        multi = copy.deepcopy(qs)
        multi["93"]["multipleSelections"] = "Yes"
        rep = report({"clearFieldOnHide": "disable"}, multi)
        self.assertFalse(rep["module_shape"]["module"]["93"]["single"])
        self.assertTrue(any("module dropdown q93 (year 3) is a multi-select" in p for p in rep["rule_problems"]))

    def test_the_served_page_is_read_for_the_shape(self):
        qs, _ = self.form()

        def rendered(page):
            r = {"id": "999", "module_values": form_status.audit_module_values(qs)[1]}
            return form_status.rendered_module_problems(r, page), r

        problems, r = rendered(served_modules_and_store(qs))
        self.assertEqual((problems, r["rendered_shape"]), ([], {"clearFieldOnHide": "disable", "multi_select": []}))
        (problem,), r = rendered(served_modules_and_store(qs, clear="dontClear"))
        self.assertIn("rendered page: JotForm.clearFieldOnHide is 'dontClear', not 'disable'", problem)
        self.assertIn("never a sync apply", problem)
        self.assertEqual(r["rendered_shape"]["clearFieldOnHide"], "dontClear")
        (problem,), r = rendered(served_modules_and_store(qs, clear=None))
        self.assertIn("no JotForm.clearFieldOnHide on the public page", problem)
        page = served_modules_and_store(qs).replace('name="q92_module2"', 'multiple="" name="q92_module2"')
        (problem,), r = rendered(page)
        self.assertIn("rendered page: module dropdown q92 is served as a multi-select (<select multiple>)", problem)
        self.assertEqual(r["rendered_shape"]["multi_select"], ["92"])
        self.assertIn('multiple=""', form_status.rendered_select_attrs(page, "92"))
        self.assertNotIn("multiple", form_status.rendered_select_attrs(page, "14"))
        self.assertIsNone(form_status.rendered_select_attrs(page, "500"))
        # the whole-page read: the shape line printed, counts only
        self.assertEqual(form_status.rendered_clear_field_on_hide('x JotForm.clearFieldOnHide = "enable"; y'), "enable")
        self.assertIsNone(form_status.rendered_clear_field_on_hide(""))


class NamesAndModulesRunbook(unittest.TestCase):
    """docs/RUNBOOK.md "The names dictionary and the module values": the commands and
    lines it quotes are the tools' own, the rollout is template first with the runner
    paused, and both rollbacks are there."""

    def section(self):
        doc = read(os.path.join(REPO, "docs", "RUNBOOK.md"))
        return " ".join(doc.split("## The names dictionary and the module values", 1)[1].split("\n## ", 1)[0].split())

    def test_the_quoted_lines_and_flags_are_the_tools_own(self):
        text = self.section()
        tool = read(os.path.join(REPO, "tools", "fix_name_translations.py"))
        for fragment in ("keys to remove:", "after the removal", "re-read: APPLIED", "public page: 0 removed keys",
                         "nothing to remove"):
            self.assertIn(fragment, text)
            self.assertIn(fragment.split(":")[0], tool)
        self.assertIn("UPDATE module dropdown (q14, year 1: calcValues = its 5 options)", text)
        self.assertTrue(auto_sync.MODULE_RX.match("  - UPDATE module dropdown (q14, year 1: calcValues = its 5 options)"))
        for flag in ("--restore", "--apply", "--form"):
            self.assertIn(flag, text)
        self.assertIn("MODULE_CALC_VALUES", text)
        self.assertIn("AUTO_SYNC_APPLY=0", text)
        self.assertIn(f"fix_name_translations.py --form {glow_forms.TEMPLATE} --apply", text)
        # template first, merged, then the regional forms; the runner back on last
        order = [text.index(s) for s in ("1. The template", "2. **Merge and push**",
                                         "3. U.S, Latin America, Asia, Africa, smallest first",
                                         "then `AUTO_SYNC_APPLY=1`")]
        self.assertEqual(order, sorted(order))
        self.assertIn("never unattended", text)
        self.assertIn("--restore backups/translations/<id>-<stamp>-before.json", text)
        # the module chain's shape (docs/plans/2026-10-06-module-selection.md): the line is the tool's own
        qs, _ = SameNameFlow.form(SameNameFlow(), switched=True)
        line = form_status.module_shape_line(form_status.audit_module_shape(qs, {"clearFieldOnHide": "disable"})[1])
        self.assertIn(f"module shape: {line}", text)
        for fragment in ("dontClear", "`enable`", "never a sync apply", "JotForm.clearFieldOnHide"):
            self.assertIn(fragment, text)


class JotformUsage(unittest.TestCase):
    """glow/usage.py: Jotform's two limits against the account's usage, each judged on its own
    (docs/plans/2026-10-06-photos-to-drive.md); a fake client with the answers' shapes as read
    2026-10-06 (counts as strings, the plan's URL, numeric limits)."""

    CAP_UP, CAP_SUB = 10738466816, 2500

    class Fake:
        def __init__(self, **change):
            self.calls = []
            self.answers = {
                "/user/usage": {"uploads": "1340458410", "submissions": "474", "total_submissions": "690",
                                "monthly_usage_reset_date": "2026-10-21 00:00:00", "form_count": "5"},
                "/user": {"account_type": "https://api.jotform.com/system/plan/SILVER", "loginToViewUploadedFiles": "1"},
                "/system/plan/SILVER": {"name": "SILVER", "limits": {"uploads": 10738466816, "submissions": 2500,
                                                                     "totalSubmissions": 25000, "formCount": 50}}}
            self.answers.update(change)

        def get(self, path, **params):
            from glow.jotform import JotformError
            self.calls.append(path)
            if path not in self.answers:
                raise JotformError(f"GET {path}: 404 Not Found")
            return copy.deepcopy(self.answers[path])

    BASE = {"plan": "SILVER", "uploads": 1340458410, "uploads_cap": CAP_UP, "submissions": 474,
            "submissions_cap": CAP_SUB, "reset": "2026-10-21"}

    def test_the_three_reads_and_the_line(self):
        fake = self.Fake()
        u = usage.read_usage(fake)
        self.assertEqual(fake.calls, ["/user/usage", "/user", "/system/plan/SILVER"])
        self.assertEqual(u, self.BASE)                                 # the reset date trimmed to the day
        self.assertEqual(usage.levels(u), {"uploads": "ok", "submissions": "ok"})
        self.assertEqual(usage.worst(usage.levels(u)), "ok")
        self.assertEqual(usage.storage_line(u), "storage: upload space 1.25 GiB of 10.00 GiB (12.5%) -> ok; "
                         "submissions this cycle 474 of 2,500 (19.0%, resets 2026-10-21) -> ok; plan SILVER")
        # the plan's name from its URL, whatever the case or a trailing slash; other date shapes kept as they are
        self.assertEqual(usage.plan_name({"account_type": "https://api.jotform.com/system/plan/gold/"}), "GOLD")
        self.assertEqual(usage.read_usage(self.Fake(**{"/user": {"account_type": ".../system/plan/Gold"},
                                                       "/system/plan/GOLD": {"limits": {"uploads": 107374182400,
                                                                                        "submissions": 10000}}}))["plan"],
                         "GOLD")
        self.assertEqual([usage.reset_day(v) for v in ("2026-10-21 00:00:00", "2026-10-21", "soon", None)],
                         ["2026-10-21", "2026-10-21", "soon", ""])
        self.assertIn("resets ?)", usage.storage_line(dict(self.BASE, reset="")))
        self.assertEqual((usage.WARN_AT, usage.ALARM_AT), (0.5, 0.8))

    def test_levels_per_limit_at_the_boundaries(self):
        for limit, cap in (("uploads", self.CAP_UP), ("submissions", self.CAP_SUB)):
            other = "submissions" if limit == "uploads" else "uploads"
            # 49.9 / 50 / 79.9 / 80 % of that limit (integer arithmetic: the 50 and 80 % values rounded up)
            for used, want in ((cap * 499 // 1000, "ok"), (-(-cap * 5 // 10), "warn"),
                               (cap * 799 // 1000, "warn"), (-(-cap * 8 // 10), "alarm"), (cap, "alarm"),
                               (cap + 1, "alarm"), (0, "ok")):
                u = dict(self.BASE, uploads=0, submissions=0)
                u[limit] = used
                lv = usage.levels(u)
                self.assertEqual((lv[limit], lv[other]), (want, "ok"), (limit, used))   # never the other one
                self.assertEqual(usage.worst(lv), want)
                self.assertIn(f"-> {want}", usage.storage_line(u).split(usage.NAMES[limit])[1])
        self.assertEqual(usage.worst({"uploads": "warn", "submissions": "alarm"}), "alarm")
        self.assertEqual(usage.worst({"uploads": "warn", "submissions": "ok"}), "warn")
        self.assertEqual(usage.share(dict(self.BASE, submissions=1250), "submissions"), 0.5)

    def test_an_answer_of_another_shape_is_refused_never_guessed(self):
        from glow.jotform import JotformError
        cases = {
            "no account_type": {"/user": {"name": "x"}},
            "not the shape read on 2026-10-06 (KeyError": {"/user/usage": {"submissions": "474"}},
            "not the shape read on 2026-10-06 (ValueError": {"/user/usage": {"uploads": "lots", "submissions": "474"}},
            "GET /system/plan/SILVER limits: not the object": {"/system/plan/SILVER": {"limits": []}},
            "cannot be judged": {"/system/plan/SILVER": {"limits": {"uploads": 0, "submissions": 2500}}},
            "GET /user/usage: not the object": {"/user/usage": []},
        }
        for message, change in cases.items():
            with self.subTest(message):
                with self.assertRaises(ValueError) as caught:
                    usage.read_usage(self.Fake(**change))
                self.assertIn(message, str(caught.exception))
        with self.assertRaises(JotformError):                          # the client's own error passes through
            usage.read_usage(self.Fake(**{"/user": {"account_type": ".../system/plan/BRONZE"}}))
        # form_status: a failed read is reported, never a form problem; the line says so
        fake = self.Fake(**{"/user": {"account_type": ".../system/plan/BRONZE"}})
        store = form_status.read_storage(fake)
        self.assertEqual(list(store), ["error"])
        self.assertIn("GET /system/plan/BRONZE", store["error"])
        self.assertTrue(form_status.storage_status_line(store).startswith("storage: could not be read (GET /system/plan/BRONZE"))
        store = form_status.read_storage(self.Fake())
        self.assertEqual(store["levels"], {"uploads": "ok", "submissions": "ok"})
        self.assertFalse(form_status.storage_status_line(store).startswith("!!"))
        store = form_status.read_storage(self.Fake(**{"/user/usage": {"uploads": str(self.CAP_UP), "submissions": "1"}}))
        self.assertTrue(form_status.storage_status_line(store).startswith("!! storage: upload space 10.00 GiB of 10.00 GiB (100.0%) -> alarm;"))


class WorkLog(unittest.TestCase):
    """tools/worklog.py: hours from session transcripts on the zone timeline, the log, the invoice
    (synthetic data)."""
    TZ = dt.timezone(dt.timedelta(hours=8))
    UTC = dt.timezone.utc

    def at(self, hhmm, day="2026-09-26", tz=None):
        return dt.datetime.fromisoformat(f"{day}T{hhmm}:00").replace(tzinfo=tz or self.TZ)

    def utc(self, text):
        return dt.datetime.fromisoformat(text).replace(tzinfo=self.UTC)

    def zones(self, *rows):
        """rows: (since 'yyyy-mm-ddThh:mm' UTC, zone text) -> the timeline read_zones returns."""
        return [(self.utc(s), worklog.parse_zone(z), z, "") for s, z in rows]

    def plus8(self):
        return self.zones(("2026-01-01T00:00", "+08:00"))

    def entry(self, kind, when_utc, content="x", **extra):
        e = {"type": kind, "timestamp": when_utc, "message": {"content": content}}
        e.update(extra)
        return e

    def test_ryans_messages_only(self):
        ryan = worklog.is_ryans_message
        self.assertTrue(ryan(self.entry("user", "t", [{"type": "text", "text": "Pick this back up"}])))
        self.assertTrue(ryan(self.entry("user", "t", "Go ahead")))
        self.assertFalse(ryan(self.entry("user", "t", [{"type": "tool_result", "content": "ok"}])))
        self.assertFalse(ryan(self.entry("user", "t", "<task-notification><task-id>x</task-id>")))
        self.assertFalse(ryan(self.entry("user", "t", [{"type": "text", "text": "Base dir"}], isMeta=True)))
        self.assertFalse(ryan(self.entry("user", "t", "This session is being continued", isCompactSummary=True)))
        self.assertFalse(ryan(self.entry("assistant", "t", [{"type": "text", "text": "Done."}])))

    def test_blocks_gaps_and_the_ryan_rule(self):
        at = self.at
        evts = [(at("09:00"), True), (at("09:20"), False), (at("09:45"), False),    # block 1: 45 min
                (at("11:00"), False), (at("11:20"), False),                        # agent alone: not billed
                (at("14:00"), True), (at("14:10"), False)]                         # block 3: 10 min
        blocks = worklog.day_blocks(evts, self.plus8())
        day = at("09:00").date()
        self.assertEqual(worklog.blocks_text(blocks[day]), "09:00-09:45, 14:00-14:10")
        self.assertEqual(worklog.zones_text(blocks[day]), "+08:00")
        self.assertEqual(worklog.day_hours(blocks[day]), 1.0)          # 55 min -> 1.00
        # stricter gap: 09:20 is 20 min on, so the 09:00 block is that message alone, and the
        # 09:20-09:45 stretch has no message of Ryan's: not billed
        self.assertEqual(worklog.day_blocks(evts, self.plus8(), gap_minutes=15)[day][0], (at("09:00"), at("09:00")))

    def test_concurrent_sessions_count_once_and_a_session_past_midnight_stays_on_its_first_day(self):
        at = self.at
        one = [(at("10:00"), True), (at("10:40"), False)]
        two = [(at("10:05"), True), (at("10:30"), False)]                   # a second open session
        blocks = worklog.day_blocks(sorted(one + two), self.plus8())
        self.assertEqual(worklog.day_hours(blocks[at("10:00").date()]), 0.75)   # 40 min, not 65
        late = [(at("23:50"), True), (at("00:20", "2026-09-27"), False), (at("01:05", "2026-09-27"), True)]
        days = worklog.day_blocks(late, self.plus8())
        self.assertEqual(sorted(d.isoformat() for d in days), ["2026-09-26", "2026-09-27"])
        self.assertEqual(worklog.blocks_text(days[at("23:50").date()]), "23:50-00:20")   # one block, its start day
        self.assertEqual(worklog.day_hours(days[at("23:50").date()]), 0.5)
        self.assertEqual(worklog.blocks_text(days[at("01:05", "2026-09-27").date()]), "01:05-01:05")

    def test_rounding(self):
        at = self.at
        self.assertEqual(worklog.day_hours([(at("09:00"), at("09:07"))]), 0.25)    # a day with work: at least 0.25
        self.assertEqual(worklog.day_hours([(at("09:00"), at("09:52"))]), 0.75)    # 52 -> 0.75
        self.assertEqual(worklog.day_hours([(at("09:00"), at("09:53"))]), 1.0)     # 53 -> 1.00 (half up)

    def transcript(self, folder, stamps):
        """A transcript file of (UTC stamp, Ryan's?) entries."""
        path = os.path.join(folder, "s.jsonl")
        with open(path, "w") as fh:
            for stamp, ryans in stamps:
                fh.write(json.dumps(self.entry("user" if ryans else "assistant", stamp, "Go")) + "\n")
            fh.write(json.dumps({"type": "summary"}) + "\n")
            fh.write("not json\n")
        return path

    def test_events_are_utc(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            evts = worklog.events([self.transcript(d, [("2026-09-26T01:00:00.000Z", True),
                                                       ("2026-09-26T01:30:00.000Z", False)])])
        self.assertEqual(len(evts), 2)
        self.assertTrue(evts[0][1] and not evts[1][1])
        self.assertEqual(evts[0][0], self.utc("2026-09-26T01:00"))
        self.assertEqual(evts[0][0].utcoffset(), dt.timedelta(0))

    def test_the_same_rows_under_any_process_time_zone(self):
        """The regression that billed September on the wrong days: the Mac's zone at run time must not matter."""
        import tempfile
        stamps = [("2026-09-02T20:45:00.000Z", True), ("2026-09-02T21:12:00.000Z", False),   # 22:45 at +02
                  ("2026-09-12T17:00:00.000Z", True), ("2026-09-12T17:25:00.000Z", False),   # 20:00 at +03
                  ("2026-09-12T17:50:00.000Z", False), ("2026-09-12T18:15:00.000Z", False),
                  ("2026-09-12T18:30:00.000Z", False)]
        zones = self.zones(("2026-08-28T00:00", "+02:00"), ("2026-09-03T00:00", "+03:00"),
                           ("2026-09-17T00:00", "+08:00"))
        saved = os.environ.get("TZ")
        results = []
        with tempfile.TemporaryDirectory() as d:
            path = self.transcript(d, stamps)
            try:
                for tz in ("UTC", "Asia/Tokyo", "Pacific/Pago_Pago"):
                    os.environ["TZ"] = tz
                    time.tzset()
                    days = worklog.day_blocks(worklog.events([path]), zones)
                    results.append({k.isoformat(): (worklog.day_hours(b), worklog.blocks_text(b)) for k, b in days.items()})
            finally:
                if saved is None:
                    os.environ.pop("TZ", None)
                else:
                    os.environ["TZ"] = saved
                time.tzset()
        self.assertEqual(results[0], {"2026-09-02": (0.5, "22:45-23:12"), "2026-09-12": (1.5, "20:00-21:30")})
        self.assertTrue(results[0] == results[1] == results[2])

    def test_zone_parsing_and_zone_at(self):
        self.assertEqual(worklog.parse_zone("+09:00").utcoffset(None), dt.timedelta(hours=9))
        self.assertEqual(worklog.parse_zone("-03:30").utcoffset(None), -dt.timedelta(hours=3, minutes=30))
        self.assertEqual(str(worklog.parse_zone("Asia/Tokyo")), "Asia/Tokyo")
        for bad in ("+15:00", "+09:60", "9", "", "Mars/Base", "+9:00"):
            with self.assertRaises(ValueError, msg=bad):
                worklog.parse_zone(bad)
        self.assertEqual(worklog.parse_instant("2026-09-29T12:37:00Z"), self.utc("2026-09-29T12:37"))
        with self.assertRaises(ValueError):
            worklog.parse_instant("2026-09-29T12:37:00")                       # no offset
        zones = self.zones(("2026-09-17T00:00", "+08:00"), ("2026-09-29T12:37", "Asia/Tokyo"))
        at = worklog.zone_at
        self.assertIsNone(at(zones, self.utc("2026-09-16T23:59")))              # before the timeline
        self.assertEqual(at(zones, self.utc("2026-09-29T12:36")), zones[0][1])
        self.assertEqual(at(zones, self.utc("2026-09-29T12:37")), zones[1][1])  # since <= t: the switch itself is new

    def test_an_iana_zone_follows_daylight_saving(self):
        zones = self.zones(("2026-10-01T00:00", "Europe/London"))
        evts = [(self.utc("2026-10-24T12:00"), True), (self.utc("2026-10-26T12:00"), True)]
        days = worklog.day_blocks(evts, zones)
        self.assertEqual(worklog.blocks_text(days[dt.date(2026, 10, 24)]), "13:00-13:00")   # BST
        self.assertEqual(worklog.blocks_text(days[dt.date(2026, 10, 26)]), "12:00-12:00")   # GMT
        self.assertEqual(worklog.zones_text(days[dt.date(2026, 10, 24)]), "+01:00")

    def test_a_block_across_a_zone_switch_and_a_travel_day(self):
        zones = self.zones(("2026-09-17T00:00", "+08:00"), ("2026-09-29T12:37", "Asia/Tokyo"))
        across = [(self.utc("2026-09-29T12:20"), True), (self.utc("2026-09-29T12:50"), False)]
        day = worklog.day_blocks(across, zones)[dt.date(2026, 9, 29)]
        self.assertEqual(worklog.blocks_text(day), "20:20-20:50")      # the end on the start's clock
        travel = [(self.utc("2026-09-29T03:00"), True), (self.utc("2026-09-29T14:00"), True)]
        day = worklog.day_blocks(travel, zones)[dt.date(2026, 9, 29)]
        self.assertEqual(worklog.zones_text(day), "+08:00/+09:00")
        self.assertEqual(worklog.blocks_text(day), "11:00-11:00 (+08:00), 23:00-23:00 (+09:00)")

    def test_blocks_before_the_timeline_are_left_out(self):
        zones = self.zones(("2026-09-01T00:00", "+02:00"))
        evts = [(self.utc("2026-08-20T10:00"), True), (self.utc("2026-09-01T10:00"), True)]
        self.assertEqual(sorted(worklog.day_blocks(evts, zones)), [dt.date(2026, 9, 1)])

    def test_read_zones_refuses_a_bad_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "tz.csv")
            for body, why in [("since,zone,evidence\n", "no rows"),
                              ("since,zone,evidence\n2026-09-02T00:00:00+00:00,+02:00,\n"
                               "2026-09-01T00:00:00+00:00,+03:00,\n", "time order"),
                              ("since,zone,evidence\n2026-09-01T00:00:00+00:00,Mars/Base,\n", "line 2"),
                              ("since,zone,evidence\n2026-09-01T00:00:00,+02:00,\n", "line 2")]:
                with open(path, "w") as fh:
                    fh.write(body)
                with self.assertRaises(ValueError, msg=why) as cm:
                    worklog.read_zones(path)
                self.assertIn(why, str(cm.exception))
            with open(path, "w") as fh:
                fh.write("since,zone,evidence\n2026-09-01T00:00:00Z,+02:00,commits\n"
                         "2026-09-29T12:37:00+00:00,Asia/Tokyo,clock\n")
            zones = worklog.read_zones(path)
            self.assertEqual([z[2] for z in zones], ["+02:00", "Asia/Tokyo"])
            with self.assertRaises(ValueError):
                worklog.read_zones(os.path.join(d, "missing.csv"))

    def test_the_mac_must_be_on_the_timelines_zone(self):
        from zoneinfo import ZoneInfo
        zones = self.zones(("2026-09-17T00:00", "+08:00"))
        now = self.utc("2026-09-30T02:00")
        evts = [(self.utc("2026-09-28T14:00"), True), (self.utc("2026-09-28T15:55"), False),
                (self.utc("2026-09-29T13:15"), True), (self.utc("2026-09-30T01:50"), True)]
        self.assertIsNone(worklog.mac_zone_problem(zones, dt.timezone(dt.timedelta(hours=8)), None, now, evts))
        tokyo = ZoneInfo("Asia/Tokyo")
        commits = [self.commit("2026-09-28T14:43", 8)]                          # the last one on the old clock
        msg = worklog.mac_zone_problem(zones, tokyo, "Asia/Tokyo", now, evts, commits=commits)
        self.assertIn("--zone Asia/Tokyo", msg)
        # no clock-change time: the middle of the first idle stretch of 6 h+ after that commit, to the
        # hour - not the later stretch after a session that was already on the new clock
        self.assertIn("--since 2026-09-29T02:00+00:00", msg)
        self.assertIn("abc1234", msg)
        # the clock-change time, when nobody was working near it
        msg = worklog.mac_zone_problem(zones, tokyo, "Asia/Tokyo", now, evts, changed=self.utc("2026-09-29T12:37"),
                                       commits=commits)
        self.assertIn("--since 2026-09-29T12:37+00:00", msg)
        # ...but not when it falls inside a session
        msg = worklog.mac_zone_problem(zones, tokyo, "Asia/Tokyo", now, evts, changed=self.utc("2026-09-29T13:20"),
                                       commits=commits)
        self.assertIn("--since 2026-09-29T02:00+00:00", msg)
        # the same offset under another name is no change
        zones = self.zones(("2026-09-29T12:37", "Asia/Tokyo"))
        self.assertIsNone(worklog.mac_zone_problem(zones, dt.timezone(dt.timedelta(hours=9)), None, now, evts))

    def commit(self, when, offset_hours, sha="abc1234", committer="Ryan"):
        return (self.utc(when), dt.timedelta(hours=offset_hours), sha, "A commit", committer)

    def test_commit_offsets_must_agree_with_the_timeline(self):
        zones = self.zones(("2026-09-03T00:00", "+03:00"), ("2026-09-17T00:00", "+08:00"))
        start = self.utc("2026-09-01T00:00")
        ok = [self.commit("2026-09-12T17:23", 3), self.commit("2026-09-20T05:52", 8)]
        self.assertEqual(worklog.commit_problems(ok, zones, start), [])
        missed_trip = ok + [self.commit("2026-09-24T06:00", 9, "def5678")]      # the timeline says +08
        bad = worklog.commit_problems(missed_trip, zones, start)
        self.assertEqual(len(bad), 1)
        self.assertTrue(bad[0].startswith("def5678") and "+09:00" in bad[0] and "+08:00" in bad[0])
        self.assertEqual(worklog.commit_problems(missed_trip, zones, start, ignore=["def5678"]), [])
        github = ok + [self.commit("2026-09-24T06:00", 0, "fff0000", committer="GitHub")]
        self.assertEqual(worklog.commit_problems(github, zones, start), [])
        old = [self.commit("2026-08-20T10:00", 5)]                               # before the window / timeline
        self.assertEqual(worklog.commit_problems(old, zones, start), [])

    def in_zones(self, fn, zones=("UTC", "Asia/Tokyo", "Pacific/Pago_Pago")):
        """fn() under each process TZ (restored afterwards) -> the list of results."""
        saved, out = os.environ.get("TZ"), []
        try:
            for tz in zones:
                os.environ["TZ"] = tz
                time.tzset()
                out.append(fn())
        finally:
            if saved is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = saved
            time.tzset()
        return out

    def test_commit_subjects_are_dated_by_the_timeline(self):
        zones = self.zones(("2026-09-03T00:00", "+03:00"), ("2026-09-17T00:00", "+08:00"))
        commits = [(self.utc("2026-09-12T17:23"), dt.timedelta(hours=3), "a", "Evening rollout", "Ryan"),
                   (self.utc("2026-09-12T22:30"), dt.timedelta(hours=3), "b", "After midnight", "Ryan"),
                   # recorded at +09 but the timeline says +08: the timeline wins (23:30 on 09-20, not 00:30 on 09-21)
                   (self.utc("2026-09-20T15:30"), dt.timedelta(hours=9), "c", "Late", "Ryan"),
                   (self.utc("2026-08-01T10:00"), dt.timedelta(hours=1), "d", "Before the timeline", "Ryan")]
        want = {"2026-09-12": ["Evening rollout"], "2026-09-13": ["After midnight"], "2026-09-20": ["Late"]}
        for got in self.in_zones(lambda: worklog.subjects_by_day(commits, zones)):
            self.assertEqual(got, want)

    def test_a_commit_goes_to_the_day_its_block_started(self):
        zones = self.zones(("2026-09-29T00:00", "+09:00"))
        evts = [(self.utc("2026-09-29T13:15"), True), (self.utc("2026-09-29T15:36"), False)]   # 22:15-00:36 JST
        for step in range(15, 141, 15):                                                         # one long session
            evts.append((self.utc("2026-09-29T13:15") + dt.timedelta(minutes=step), False))
        days = worklog.day_blocks(sorted(evts), zones)
        commit = (self.utc("2026-09-29T15:40"), dt.timedelta(hours=9), "e", "Past midnight", "Ryan")   # 00:40 on 09-30
        self.assertEqual(worklog.subjects_by_day([commit], zones, days), {"2026-09-29": ["Past midnight"]})
        self.assertEqual(worklog.subjects_by_day([commit], zones), {"2026-09-30": ["Past midnight"]})

    def test_events_stay_utc_under_any_process_time_zone(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = self.transcript(d, [("2026-09-26T01:00:00.000Z", True), ("2026-09-26T20:00:00.000Z", True)])
            runs = self.in_zones(lambda: worklog.events([path]))
            after, end = self.utc("2026-09-26T00:00"), self.utc("2026-09-27T12:00")
            picks = self.in_zones(lambda: worklog.suggest_since(worklog.events([path]), after, end))
        for evts in runs:
            self.assertTrue(all(t.utcoffset() == dt.timedelta(0) for t, _ in evts))
            self.assertIs(evts[0][0].tzinfo, dt.timezone.utc)
        self.assertTrue(picks[0] == picks[1] == picks[2])

    def test_system_zone_reads_etc_localtime_not_the_shell(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            link = os.path.join(d, "localtime")
            os.symlink("/var/db/timezone/zoneinfo/Europe/London", link)       # need not exist
            stamp = 1790000000
            os.utime(link, (stamp, stamp), follow_symlinks=False)
            plain = os.path.join(d, "plain")
            open(plain, "w").close()
            odd = os.path.join(d, "odd")
            os.symlink("/nowhere/Asia/Tokyo", odd)
            saved = worklog.LOCALTIME
            try:
                worklog.LOCALTIME = link
                tz, name, changed = self.in_zones(worklog.system_zone, ("Asia/Tokyo",))[0]
                self.assertEqual((str(tz), name), ("Europe/London", "Europe/London"))
                self.assertEqual(changed, dt.datetime.fromtimestamp(stamp, dt.timezone.utc))
                for fallback in (plain, odd):
                    worklog.LOCALTIME = fallback
                    _, name, changed = worklog.system_zone()
                    self.assertEqual((name, changed), (None, None))
            finally:
                worklog.LOCALTIME = saved

    def test_where_a_zone_change_may_be_recorded(self):
        from zoneinfo import ZoneInfo
        tokyo = ZoneInfo("Asia/Tokyo")
        zones = self.zones(("2026-09-17T00:00", "+08:00"))
        now = self.utc("2026-09-30T02:00")
        evts = [(self.utc("2026-09-28T15:55"), True), (self.utc("2026-09-29T13:15"), True)]
        commits = [self.commit("2026-09-28T14:43", 8), self.commit("2026-09-29T14:00", 9, "fff1111")]
        check = worklog.since_problems
        self.assertEqual(check(self.utc("2026-09-29T02:00"), tokyo, zones, evts, commits, now), [])
        old = check(self.utc("2026-09-28T12:00"), tokyo, zones, evts, commits, now)
        self.assertTrue(any("old clock" in p for p in old))                          # 14:43 was still +08
        new = check(self.utc("2026-09-29T14:30"), tokyo, zones, evts, commits, now)
        self.assertTrue(any("new clock" in p and "fff1111" in p for p in new))       # 14:00 was already +09
        # inside a session with no commits around it: refused
        quiet = [self.commit("2026-09-20T01:00", 8)]
        inside = check(self.utc("2026-09-29T13:30"), tokyo, zones, evts, quiet, now)
        self.assertTrue(any("inside a session" in p for p in inside))
        # ...but a clock change during a session, between its old- and new-clock commits, is fine
        busy = [(self.utc("2026-10-05T10:00"), True)] + [
            (self.utc("2026-10-05T10:00") + dt.timedelta(minutes=m), False) for m in range(10, 121, 10)]
        mid = [self.commit("2026-10-05T10:30", 8), self.commit("2026-10-05T11:30", 9, "fff2222")]
        self.assertEqual(check(self.utc("2026-10-05T11:00"), tokyo, zones, busy, mid, self.utc("2026-10-06T00:00")), [])
        self.assertTrue(any("future" in p for p in check(self.utc("2026-10-02T00:00"), tokyo, zones, evts, commits, now)))
        self.assertTrue(any("not after the last row" in p for p in
                            check(self.utc("2026-09-10T00:00"), tokyo, zones, evts, commits, now)))

    def test_the_suggested_switch_is_one_zone_accepts_and_update_then_passes(self):
        from zoneinfo import ZoneInfo
        tokyo = ZoneInfo("Asia/Tokyo")
        zones = self.zones(("2026-09-17T00:00", "+08:00"))
        u = self.utc

        def session(start, minutes, ryan=True):
            t0 = u(start)
            return [(t0, ryan)] + [(t0 + dt.timedelta(minutes=m), False) for m in range(10, minutes + 1, 10)]

        def accepted(evts, commits, now, changed=None):
            msg = worklog.mac_zone_problem(zones, tokyo, "Asia/Tokyo", now, evts, changed, commits=commits)
            m = re.search(r"--since (\S+)\+00:00", msg)
            self.assertIsNotNone(m, msg)
            since = u(m.group(1))
            self.assertEqual(worklog.since_problems(since, tokyo, zones, evts, commits, now), [], msg)
            timeline = zones + [(since, tokyo, "Asia/Tokyo", "")]
            self.assertEqual(worklog.commit_problems(commits, timeline, zones[0][0]), [])
            return since

        # the clock changed 5 min before an arrival session that commits on the new clock (a short hop)
        evts = session("2026-10-05T08:00", 120) + session("2026-10-05T15:00", 120)
        commits = [self.commit("2026-10-05T10:00", 8), self.commit("2026-10-05T16:30", 9, "fff3333")]
        since = accepted(evts, commits, u("2026-10-05T18:00"), changed=u("2026-10-05T14:55"))
        self.assertTrue(u("2026-10-05T10:00") < since < u("2026-10-05T15:00"))
        # the clock changed 10 min before a session; a session with no commits sat before the flight:
        # the switch is after that session, not the night before it
        evts = session("2026-10-05T08:00", 120) + session("2026-10-06T00:00", 115) + session("2026-10-06T16:10", 60)
        commits = [self.commit("2026-10-05T10:00", 8)]
        since = accepted(evts, commits, u("2026-10-06T17:30"), changed=u("2026-10-06T16:00"))
        self.assertEqual(since, u("2026-10-06T09:00"))
        # no clock-change time: the longest idle stretch, never "now"
        since = accepted(evts, commits, u("2026-10-06T17:30"))
        self.assertTrue(u("2026-10-06T01:55") < since < u("2026-10-06T16:10"))
        # the clock changed during a session with commits on both clocks: no idle moment, no command
        evts = session("2026-10-05T10:00", 120)
        commits = [self.commit("2026-10-05T10:30", 8), self.commit("2026-10-05T11:30", 9, "fff4444")]
        msg = worklog.mac_zone_problem(zones, tokyo, "Asia/Tokyo", u("2026-10-05T12:00"), evts, commits=commits)
        self.assertIn("pick one by hand", msg)
        self.assertNotRegex(msg, r"--since \d")

    def test_a_switch_date_means_midnight_on_the_new_clock(self):
        switch = worklog.parse_switch
        self.assertEqual(switch("2026-10-02", "Europe/London")[0], self.utc("2026-10-01T23:00"))   # BST
        self.assertEqual(switch("2026-10-02", "+09:00")[0], self.utc("2026-10-01T15:00"))
        self.assertEqual(switch("2026-10-02", "-03:00")[0], self.utc("2026-10-02T03:00"))
        self.assertEqual(switch("2026-10-02T12:37:00Z", "Asia/Tokyo")[0], self.utc("2026-10-02T12:37"))
        for bad in [("2026-10-02T12:37", "Asia/Tokyo"), ("2026-10-02", "Mars/Base"), ("", "+09:00")]:
            with self.assertRaises(ValueError, msg=bad):
                switch(*bad)
        plus8, tokyo = worklog.parse_zone("+08:00"), worklog.parse_zone("Asia/Tokyo")
        self.assertEqual(worklog.first_day(self.utc("2026-09-29T15:30"), plus8, tokyo), dt.date(2026, 9, 29))
        self.assertEqual(worklog.first_day(self.utc("2026-09-29T16:30"), plus8, tokyo), dt.date(2026, 9, 30))

    def test_append_zone_keeps_rows_apart(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "tz.csv")
            with open(path, "w") as fh:
                fh.write("since,zone,evidence\n2026-09-17T00:00:00+00:00,+08:00,commits")      # no final newline
            worklog.append_zone(self.utc("2026-09-29T12:37"), "Asia/Tokyo", "clock", path)
            zones = worklog.read_zones(path)
            self.assertEqual([z[2] for z in zones], ["+08:00", "Asia/Tokyo"])
            with open(path, "rb") as fh:
                self.assertNotIn(b"\r", fh.read())
            with open(path, "w") as fh:
                fh.write("since,zone,evidence\n2026-09-17T00:00:00+00:00,+08:00,commits2026-09-29T12:37:00+00:00,"
                         "Asia/Tokyo,clock\n")                                              # two rows run together
            with self.assertRaises(ValueError) as cm:
                worklog.read_zones(path)
            self.assertIn("more than 3 columns", str(cm.exception))

    def recount(self, rows, evts, today, since, **kw):
        return worklog.update_rows(rows, evts, [], self.plus8(), since, today, **kw)

    def test_update_refuses_or_drops_a_stale_row_only_as_asked(self):
        evts = [(self.at("09:00", "2026-09-26"), True), (self.at("09:30", "2026-09-26"), False)]
        rows = [{"date": "2026-09-25", "hours": "0.75", "blocks": "10:00-10:45", "description": "Moved", "source": "auto"},
                {"date": "2026-09-25", "hours": "1.00", "blocks": "", "description": "Call", "source": "manual"}]
        today, since = dt.date(2026, 9, 30), dt.date(2026, 9, 20)
        with self.assertRaises(SystemExit) as cm:
            self.recount(rows, evts, today, since)
        self.assertIn("--drop-stale", str(cm.exception.code))
        new, computed, dropped, kept, held = self.recount(rows, evts, today, since, drop_stale=True)
        self.assertEqual(dropped, ["2026-09-25"])
        self.assertEqual([(r["date"], r["source"]) for r in new], [("2026-09-25", "manual"), ("2026-09-26", "auto")])
        # 40 days on, the row may just have lost its transcripts: kept, whatever the flag
        old_evts = [(self.at("09:00", "2026-11-05"), True)]
        new, *_, kept, held = self.recount(rows, old_evts, dt.date(2026, 11, 5), since, drop_stale=True)
        self.assertEqual(kept, ["2026-09-25"])
        self.assertIn(("2026-09-25", "auto"), [(r["date"], r["source"]) for r in new])
        # another transcript folder never drops a row
        new, _, dropped, kept, _ = self.recount(rows, evts, today, since, drop_stale=True, custom_folder=True)
        self.assertEqual((dropped, kept), ([], ["2026-09-25"]))

    def test_update_refuses_work_before_the_timeline(self):
        zones = self.zones(("2026-09-26T00:00", "+08:00"))
        evts = [(self.utc("2026-09-25T20:00"), True)]                      # 2026-09-26 04:00 at +08
        with self.assertRaises(SystemExit) as cm:
            worklog.update_rows([], evts, [], zones, dt.date(2026, 9, 26), dt.date(2026, 9, 30))
        self.assertIn("predates", str(cm.exception.code))

    def test_an_old_or_partial_recount_never_lowers_a_logged_row(self):
        evts = [(self.at("09:00", "2026-09-01"), True), (self.at("09:30", "2026-09-01"), False)]
        rows = [{"date": "2026-09-01", "hours": "2.75", "blocks": "08:00-10:45", "description": "Kept", "source": "auto"}]
        since = dt.date(2026, 9, 1)
        # a month later a session of that day may have expired: the row stays, reported as held
        new, computed, _, _, held = self.recount(rows, evts, dt.date(2026, 10, 31), since)
        self.assertEqual((held, new[0]["hours"]), (["2026-09-01"], "2.75"))
        # another folder: held too
        new, _, _, _, held = self.recount(rows, evts, dt.date(2026, 9, 10), since, custom_folder=True)
        self.assertEqual((held, new[0]["hours"]), (["2026-09-01"], "2.75"))
        # a recent day recounts; --rewrite-old lets a deliberate correction of an old one through
        new, *_, held = self.recount(rows, evts, dt.date(2026, 9, 10), since)
        self.assertEqual((held, new[0]["hours"]), ([], "0.50"))
        new, *_, held = self.recount(rows, evts, dt.date(2026, 10, 31), since, rewrite_old=True)
        self.assertEqual((held, new[0]["hours"]), ([], "0.50"))

    def test_days_before_the_window_must_not_change_and_a_missed_day_is_found(self):
        rows = [{"date": "2026-10-01", "hours": "1.00", "blocks": "10:00-11:00", "source": "auto"},
                {"date": "2026-10-03", "hours": "1.00", "blocks": "10:00-11:00", "source": "auto"}]
        computed = {"2026-10-01": (1.0, "10:00-11:00", "+09:00"), "2026-10-03": (1.0, "10:00-11:00", "+09:00"),
                    "2026-10-04": (2.0, "10:00-12:00", "+09:00"), "2026-10-20": (1.0, "10:00-11:00", "+09:00")}
        today = dt.date(2026, 10, 20)
        # the default window reaches back to the last logged day when the log is behind
        self.assertEqual(worklog.default_since(rows, today), dt.date(2026, 10, 3))
        self.assertEqual(worklog.default_since(rows, dt.date(2026, 10, 10)), dt.date(2026, 9, 26))  # not behind
        self.assertEqual(worklog.default_since(rows, dt.date(2026, 11, 30)), dt.date(2026, 11, 1))  # never past 29 days
        self.assertIsNone(worklog.window_problems(rows, computed, dt.date(2026, 10, 3), today))
        # an explicit --since past a never-logged day refuses and names it
        msg = worklog.window_problems(rows, computed, dt.date(2026, 10, 6), today)
        self.assertIn("2026-10-04: no row -> 2.00 h", msg)
        self.assertIn("--since 2026-10-04", msg)
        # a logged day whose work vanished (recent) refuses; the log's own start and expired days do not
        self.assertIn("no work", worklog.window_problems(rows, {}, dt.date(2026, 10, 2), today))
        self.assertIsNone(worklog.window_problems(rows, {}, dt.date(2026, 10, 2), dt.date(2026, 12, 1)))
        self.assertIsNone(worklog.window_problems(rows, {"2026-09-30": (1.0, "x", "+09:00")}, dt.date(2026, 10, 1), today))
        self.assertIsNone(worklog.window_problems(rows, {}, dt.date(2026, 10, 2), today, earliest=dt.date(2026, 10, 2)))

    def test_stale_rows_go_only_when_recent_and_from_this_repos_transcripts(self):
        rows = [{"date": "2026-09-05", "hours": "0.75", "source": "auto"},
                {"date": "2026-09-05", "hours": "1.00", "source": "manual"},
                {"date": "2026-09-04", "hours": "0.75", "source": "auto"}]
        computed = {"2026-09-04": (0.75, "20:32-21:15", "+03:00")}
        since = dt.date(2026, 9, 1)
        self.assertEqual(worklog.stale_days(rows, computed, since, dt.date(2026, 9, 30), False), (["2026-09-05"], []))
        # a month later its transcripts may have expired: kept, never dropped
        self.assertEqual(worklog.stale_days(rows, computed, since, dt.date(2026, 10, 20), False), ([], ["2026-09-05"]))
        # another transcript folder never drops anything
        self.assertEqual(worklog.stale_days(rows, computed, since, dt.date(2026, 9, 30), True), ([], ["2026-09-05"]))

    def test_merge_keeps_manual_rows_and_written_descriptions(self):
        rows = [{"date": "2026-09-25", "hours": "2.00", "blocks": "x", "description": "Curated text", "source": "auto"},
                {"date": "2026-09-25", "hours": "1.00", "blocks": "", "description": "Call", "source": "manual"},
                {"date": "2026-09-05", "hours": "0.75", "blocks": "z", "description": "Moved", "source": "auto"},
                {"date": "2026-08-30", "hours": "3.00", "blocks": "y", "description": "Old", "source": "auto"}]
        computed = {"2026-09-25": (2.5, "09:00-11:30", "+08:00"), "2026-09-26": (1.0, "10:00-11:00", "+08:00")}
        subjects = {"2026-09-26": ["Second commit", "First commit"]}
        out = worklog.merge(rows, computed, subjects, drop=["2026-09-05"])
        by = {(r["date"], r["source"]): r for r in out}
        self.assertEqual(by[("2026-09-25", "auto")]["hours"], "2.50")
        self.assertEqual(by[("2026-09-25", "auto")]["zone"], "+08:00")
        self.assertEqual(by[("2026-09-25", "auto")]["description"], "Curated text")
        self.assertEqual(by[("2026-09-25", "manual")]["hours"], "1.00")
        self.assertEqual(by[("2026-09-26", "auto")]["description"], "First commit; Second commit")
        self.assertNotIn(("2026-09-05", "auto"), by)     # dropped as asked
        self.assertIn(("2026-08-30", "auto"), by)        # an expired day is never dropped
        self.assertEqual([r["date"] for r in out], sorted(r["date"] for r in out))

    def test_invoice_rows(self):
        rows = [{"date": "2026-09-25", "hours": "2.50", "description": "Fix", "source": "auto"},
                {"date": "2026-09-25", "hours": "1.00", "description": "Call", "source": "manual"},
                {"date": "2026-09-26", "hours": "1.25", "description": "", "source": "auto"},
                {"date": "2026-10-01", "hours": "4.00", "description": "Next month", "source": "auto"}]
        out = worklog.invoice_rows(rows, "2026-09", rate=60)
        self.assertEqual(out[0], ["Date", "Hours", "Description", "Amount"])
        self.assertEqual(out[1], ["2026-09-25", "3.50", "Fix / Call", "210.00"])
        self.assertEqual(out[-1], ["Total", "4.75", "", "285.00"])
        self.assertEqual(len(worklog.invoice_rows(rows, "2026-09")[0]), 3)   # no rate, no Amount

    def test_log_round_trip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "w", "log.csv")
            rows = [{"date": "2026-09-25", "hours": "1.00", "blocks": "09:00-10:00",
                     "description": 'Commas, "quotes"\nand a newline', "source": "auto", "zone": "+08:00"}]
            worklog.write_log(rows, path)
            self.assertEqual(worklog.read_log(path), rows)
            with open(path, "rb") as fh:
                self.assertNotIn(b"\r", fh.read())     # LF only: an update must not rewrite every line

    def test_transcripts_dir(self):
        repo = os.sep + os.path.join("srv", "jotform-glow-sync")          # built, not a literal path
        self.assertTrue(worklog.transcripts_dir(repo).endswith(
            os.path.join(".claude", "projects", "-srv-jotform-glow-sync")))


if __name__ == "__main__":
    unittest.main(verbosity=1)
