#!/usr/bin/env python3
"""
Offline tests for the automatic sync's runner, tools/auto_sync.py, on fabricated output: the
plan parsing, the safety bands, the blank-region guard, verification and redaction
(AutoSyncPlan); SyncLog's `when` (SheetWhen); tools/sheets_client.py's spreadsheets.get
(SheetsClientGet); and the module dropdowns' calcValues, which the runner never applies
unattended (ModuleValues).
"""
import json
import os
import re
import sys
import unittest

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import AutoSyncFixture, FakeForm, REPO, SameNameFixture, read
import auto_sync
import sync_attendance_form as sync
from glow import sync as glow_sync


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


class AutoSyncPlan(AutoSyncFixture, unittest.TestCase):
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
                         "REQUIRED roster '{club}' (q{qid}: {want_required})",
                         # the retired rosters (docs/plans/2026-10-06-clubs-off-jotform.md): the two ~ lines,
                         # the Form: line and the Partners-tab warning the runner reports
                         "~ retired roster '{text}' (q{qid}): {reason}",
                         "~ restored roster '{text}' (q{qid}): {RESTORED_WHY}",
                         'RESTORED_WHY = "back on the Club picker"',
                         "Form: {args.form} status {status or 'not reported'}"):
            self.assertIn(fragment, joined, fragment)
        self.assertIn(auto_sync.JOTFORM_VALUE, read(os.path.join(REPO, "glow", "sync.py")))
        self.assertIn(auto_sync.JOTFORM_COLUMN, read(os.path.join(REPO, "glow", "sync.py")))
        for line, rx in (("UPDATE roster 'A' (q1, 2 girls)", auto_sync.UPDATE_RX),
                         ("UPDATE roster 'A' (q1, 2 girls; required: Yes)", auto_sync.UPDATE_RX),
                         ("UPDATE roster 'A' (q1, 2 girls; required: No)", auto_sync.UPDATE_RX),
                         ("REQUIRED roster 'A' (q1: Yes)", auto_sync.REQUIRED_RX),
                         ("REQUIRED roster 'Club (B)' (q1: No)", auto_sync.REQUIRED_RX)):
            self.assertTrue(rx.match("  - " + line), line)
        for line, rx in (("retired roster 'Club (B)' (q12): not on Jotform (Partner Two, Partners tab jotform=no)",
                          auto_sync.RETIRED_RX),
                         ("retired roster 'A' (q1): no active girl in the Roster", auto_sync.RETIRED_RX),
                         ("restored roster 'A' (q1): back on the Club picker", auto_sync.RESTORED_RX)):
            self.assertTrue(rx.match("  ~ " + line), line)
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

        def run_main(regions, partners=True):
            with tempfile.TemporaryDirectory() as tmp:
                roster = os.path.join(tmp, "roster.csv")
                with open(roster, "w", encoding="utf-8") as f:
                    f.write("girl_id,partner,club,full_name,status,region\n"
                            "DEMOCLUB-SAMPLE-001,Partner One,Stars,Ann Poe,active,Africa\n"
                            "DEMOCLUB-SAMPLE-002,Partner Three,Stars,Sue Moe,active,Asia\n")
                tab = os.path.join(tmp, "partners.csv")
                with open(tab, "w", encoding="utf-8") as f:
                    f.write("partner,region,notes,jotform\nPartner One,Africa,,\nPartner Three,Asia,,\n")
                argv = ["auto_sync.py", "--roster", roster, "--out", tmp, "--min-active", "1"]
                if partners:
                    argv += ["--partners", tab]
                for region in regions:
                    argv += ["--region", region]
                code = 0
                with mock.patch.object(sys, "argv", argv), \
                        mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}), \
                        mock.patch.object(auto_sync.Run, "sync", sync_), \
                        mock.patch.object(auto_sync.Run, "read_status", lambda self, form: "ENABLED"), \
                        mock.patch.object(auto_sync.Run, "check_storage", lambda self, read: None), \
                        mock.patch("builtins.print"):
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
        # --roster without --partners: nothing read, exit 1 with what to pass
        code, attention = run_main(["Africa"], partners=False)
        self.assertIn("--roster needs --partners <Partners export>", str(code))
        self.assertEqual(attention, "")

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
        # main() reads it after the regions, through the run's one client (the form-status reads use
        # it too), built with the key from the environment and bounded: a stalled GET must not hold the run
        src = read(os.path.join(REPO, "tools", "auto_sync.py"))
        self.assertIn('run.client = Client(os.environ["JOTFORM_API_KEY"], max_time=60)', src)
        self.assertIn('run.check_names()\n    run.check_storage(lambda: usage.read_usage(run.client))', src)

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
                    returncode=0, stdout=text, stderr="")), \
                    mock.patch.object(run, "read_status", lambda form: "ENABLED"), mock.patch("builtins.print"):
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
                    mock.patch.object(run, "read_status", lambda form: "ENABLED"), \
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


class ModuleValues(unittest.TestCase):
    """The module dropdowns' calcValues (glow/sync.py MODULE_CALC_VALUES): their own options
    after a single-select's empty slot, written and kept in step by the sync, cleared by
    the generated rollback, never applied by the runner unattended; on SameNameFlow's
    fake Africa form."""

    ROSTER, QIDS, MODULES, texts = SameNameFixture.ROSTER, SameNameFixture.QIDS, SameNameFixture.MODULES, SameNameFixture.texts
    LINES = ["UPDATE module dropdown (q14, year 1: calcValues = its 1 options)",
             "UPDATE module dropdown (q92, year 2: calcValues = its 2 options)",
             "UPDATE module dropdown (q93, year 3: calcValues = its 1 options)"]

    def setUp(self):
        SameNameFixture.setUp(self)

    def tearDown(self):
        SameNameFixture.tearDown(self)

    def run_sync(self, fake, *extra, roster=None):
        return SameNameFixture.run_sync(self, fake, *extra, roster=roster)

    def summary(self, fake, *extra, **kw):
        return SameNameFixture.summary(self, fake, *extra, **kw)

    def form(self, calc=True):
        qs, wire = SameNameFixture.form(self, switched=True)
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
            run = AutoSyncFixture.run_region(self, t, apply=True)
            self.assertEqual((run.synced, [r[7] for r in run.results]), ([False], ["attention"]))
            self.assertIn("- MODULE values q92 (year 2: 2 modules)", run.attention[0][1])
        cleared = text.replace("= its 1 options)", "cleared)")
        self.assertIn("- MODULE values q14 (year 1: cleared)", AutoSyncFixture.run_region(self, cleared, apply=True)
                      .attention[0][1])
        self.assertFalse(auto_sync.MODULE_RX.match("  - UPDATE module dropdown (q14, year 1: calcValues)"))
        # the line is the sync's own
        joined = re.sub(r'"\s*\n\s*"', "", read(os.path.join(REPO, "sync_attendance_form.py")))
        for fragment in ('f"UPDATE module dropdown (q{mqid}, year {year}: calcValues "',
                         '(f"= its {len(options)} options)" if want else "cleared)")'):
            self.assertIn(fragment, joined)


if __name__ == "__main__":
    unittest.main(verbosity=1)
