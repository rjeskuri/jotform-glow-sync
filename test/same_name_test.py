#!/usr/bin/env python3
"""
sync_attendance_form.main() end to end on a fake Africa form where two partners each have a
club named "Stars" (SameNameFlow: before, during and after the --same-name-switch), and with the
club guard (ClubGuardFlow). The form itself is helpers/common.py's SameNameFixture. Fictional
names.
"""
import json
import os
import unittest

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import ClubGuardFixture, FakeForm, SameNameFixture, apps_script_same_name
import auto_sync
import sync_attendance_form as sync
from glow import links
from glow import sync as glow_sync


class SameNameFlow(SameNameFixture, unittest.TestCase):
    """sync_attendance_form.main() on a fake Africa form where two partners each
    have a club named "Stars": before the one-time --same-name-switch (the typed
    Partner box tells the two rosters apart), during it, and after (each has its
    own Club picker entry, "Stars - <partner>", which is what question 5 sends).
    docs/plans/2026-09-30-same-name-clubs.md. Fictional names."""

    CHANGE = "'Stars' (q{qid}): Club Name (question 5, what Salesforce reads) changes from 'Stars' to '{new}'"

    # ---- before the switch: nothing changes on its own
    def test_a_live_rule_that_does_not_parse_is_refused_not_a_traceback(self):
        qs, wire = self.form()
        at = next(n for n, c in enumerate(wire) if c["type"] == "field")      # the rules the sync reads back
        for broken in ({"terms": "{broken"}, {"action": json.dumps({"visibility": 5}) + "x"}, {"terms": 5}):
            with self.subTest(broken=broken):
                fake = FakeForm(qs, wire[:at] + [dict(wire[at], id="88", **broken)] + wire[at + 1:])
                code, _ = self.run_sync(fake)
                self.assertIn("Refusing: the form's rule 88 has terms or an action that do not parse", str(code))
                self.assertEqual(fake.calls, [])

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
        # with no rule has nothing it "sends today", so this is no question-5 change. Without
        # its picker entry as well it has the shape of a retired roster (docs/plans/2026-10-06-
        # clubs-off-jotform.md): the run finishes it with the Partners export, which the runner
        # always passes; a hand run without one is told so and refuses to --apply
        sheet = {**self.ROSTER, ("Partner One", "Gamma Club"): ["Amara Pellucidor"]}
        self.QIDS = {**self.QIDS, ("Partner One", "Gamma Club"): "20"}       # 14 is a module dropdown
        for picker_written in (True, False):
            del sync.WARNINGS[:]
            qs, _ = self.form(roster=sheet, switched=True)
            _, wire = self.form(switched=True)                 # the rules from before the new club
            if not picker_written:
                qs["500"]["options"] = "|".join(self.LONG)
            fake = FakeForm(qs, wire, apply=True)
            code, out = self.run_sync(fake, "--apply", roster=sheet, partners={})
            self.assertEqual(code, 0, code)
            self.assertEqual(sync.WARNINGS, [])
            self.assertEqual([(m, p) for m, p, _ in fake.writes],
                             ([] if picker_written else [("POST", "/question/500")]) + [("PUT", "/properties")])
            self.assertEqual(self.shows(fake.writes[-1][2], "20"), [("500", "equals", "Gamma Club")])
            # with its entry written the picker says what it sends (no restore); without, restored
            self.assertEqual("  ~ restored roster 'Gamma Club' (q20): back on the Club picker" in out,
                             not picker_written)
        # without a Partners export the entry-less roster could be a retired one: the dry run says
        # so, --apply refuses, and with the entry written there is nothing to tell apart
        for picker_written in (True, False):
            del sync.WARNINGS[:]
            qs, _ = self.form(roster=sheet, switched=True)
            _, wire = self.form(switched=True)
            if not picker_written:
                qs["500"]["options"] = "|".join(self.LONG)
            fake = FakeForm(qs, wire, apply=True)
            code, out = self.run_sync(fake, "--apply", roster=sheet)
            if picker_written:
                self.assertEqual((code, sync.WARNINGS), (0, []))
                continue
            self.assertIn("Refusing: 1 roster(s) would be restored without a Partners export", str(code))
            self.assertEqual(fake.writes, [])
            self.assertEqual(sync.WARNINGS, [
                "  ! 'Gamma Club' (q20) has no Club picker entry and no show rule although its club is "
                "active in the Roster - a retired roster, or a new roster of an apply that stopped "
                "half-way: pass --partners <Partners export> (the runner always does) and the run "
                "restores it or keeps it retired"])
            self.assertNotIn("~ restored", out)
            code, _ = self.run_sync(FakeForm(qs, wire), roster=sheet)         # the dry run only warns
            self.assertEqual(code, 0)

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
            self.QIDS = {**SameNameFixture.QIDS, (partner, "Stars"): "12"}
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


class ClubGuardFlow(ClubGuardFixture, unittest.TestCase):
    """sync_attendance_form.main() with --club-guard and without, on the fake
    Africa form of SameNameFlow - switched: each of the two Stars has its own
    picker entry, as on the live forms after the 2026-09-30 rollout - plus a
    Submit button (q2) below the rosters (the layout after the roster-order
    repair, glow/layout.py) and, when the form has it, the warning (q700).
    Every question carries its qid, as Jotform's GET does (the layout code
    orders by it). Fictional names."""

    WITH_NEW = "Alpha Club|Beta Club|Gamma Club|Stars - Partner One|Stars - Partner Two"

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
                                      f"REPLACE conditions ({len(wire) - 1} rules)", SameNameFixture.HIDE])
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


if __name__ == "__main__":
    unittest.main(verbosity=1)
