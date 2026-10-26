#!/usr/bin/env python3
"""
Clubs that do not report through Jotform (docs/plans/2026-10-06-clubs-off-jotform.md): the
sync retires their rosters (RetiredRosters) and tools/form_status.py audits them
(RetiredRostersAudit). Fictional names.
"""
import copy
import json
import os
import sys
import unittest
from unittest import mock

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import (AutoSyncFixture, FakeForm, REPO, SameNameFixture, read,
                            served_rules_and_rosters)
import auto_sync
import form_status
import sync_attendance_form as sync
from glow import forms as glow_forms
from glow import layout
from glow import sync as glow_sync


class RetiredRosters(unittest.TestCase):
    """Clubs that do not report through Jotform leave the forms
    (docs/plans/2026-10-06-clubs-off-jotform.md), on SameNameFlow's fake Africa
    form: a partner marked jotform=no in the Partners export has its rosters
    RETIRED - kept on the form, hidden and frozen, off the Club picker, no show
    rule, still in question 18's sum - and so is a club with no active girl
    since before today (glow.sync.RETIRE_INACTIVE); a retired roster comes back
    when the Roster says so; a hand run without the export refuses to restore;
    what the runner makes of the plan. Fictional names."""

    ROSTER, QIDS, MODULES, LONG = SameNameFixture.ROSTER, SameNameFixture.QIDS, SameNameFixture.MODULES, SameNameFixture.LONG
    form, run_sync, summary = SameNameFixture.form, SameNameFixture.run_sync, SameNameFixture.summary
    partners_csv, texts, shows = SameNameFixture.partners_csv, SameNameFixture.texts, SameNameFixture.shows
    rules = staticmethod(SameNameFixture.rules)
    NO = {"Partner Two": "no"}
    RETIRED = {"12": "  ~ retired roster 'Stars' (q12): not on Jotform (Partner Two, Partners tab jotform=no)",
               "13": "  ~ retired roster 'Beta Club' (q13): not on Jotform (Partner Two, Partners tab jotform=no)"}
    DRY = ("Roster: 3 active clubs in Africa (40 girls); 300 clubs overall\n\nDRY RUN (use --apply to write):\n"
           "  - CREATE roster 'Gamma Club' (2 girls)\n")

    def setUp(self):
        SameNameFixture.setUp(self)

    def tearDown(self):
        SameNameFixture.tearDown(self)

    def retired_form(self, gone=("12", "13")):
        """(questions, wire) of the switched form as the sync leaves it once the rosters
        `gone` are retired: no show rule for them, their entries off the picker."""
        qs, _ = self.form(switched=True)
        option_of, partner_of = self.texts(self.ROSTER, True)
        keep = {q: o for q, o in option_of.items() if q not in gone}
        qs["500"]["options"] = "|".join(sorted(set(keep.values()), key=str.lower))
        modules = {y: o.split("|") for y, o in self.MODULES.items()}
        conds = sync.build_conditions(keep, partner_of, modules, picker="500", retired=gone)
        return qs, [dict(c, terms=json.dumps(c["terms"]), action=json.dumps(c["action"])) for c in conds]

    # ---- glow.sync
    def test_the_partners_tab_is_read_by_header_and_any_other_value_is_yes(self):
        import contextlib
        import csv
        import io
        path = os.path.join(self.tmp.name, "p.csv")

        def write(header, rows):
            with open(path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows([header] + rows)
            return path
        write(["Partner", "Region", "Notes", "Jotform "],         # capitals and spacing ignored
              [["Partner One", "Africa", "", ""], ["Partner Two", "Africa", "", " No "],
               ["Partner  Three", "Asia", "", "YES"], ["Partner Four", "Asia", "", "maybe"],
               ["", "", "", "no"], ["Partner Two", "Africa", "", ""]])   # a blank row; a second row of a marked partner
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(glow_sync.read_partners_csv(path),
                             {"partner one": "yes", "partner two": "no", "partner three": "yes", "partner four": "yes"})
        self.assertEqual(out.getvalue(), "".join(w + "\n" for w in glow_sync.WARNINGS))    # printed as it is kept
        self.assertEqual(glow_sync.WARNINGS, ["  ! Partners tab: 'Partner Four' has jotform='maybe' - only yes, no "
                                              "or blank are understood; treated as yes"])
        self.assertIn(auto_sync.JOTFORM_VALUE, glow_sync.WARNINGS[0])
        self.assertTrue(glow_sync.partners_marker_present(path))
        del glow_sync.WARNINGS[:]
        # the tab before the column marks nobody - and says so (a renamed header would otherwise
        # read as every mark lifted); one without a partner column is refused
        write(["partner", "region", "notes"], [["Partner One", "Africa", ""]])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(glow_sync.read_partners_csv(path), {"partner one": "yes"})
        self.assertEqual(out.getvalue(), "".join(w + "\n" for w in glow_sync.WARNINGS))
        self.assertFalse(glow_sync.partners_marker_present(path))
        self.assertEqual(glow_sync.WARNINGS, ["  ! Partners tab: the export has no 'jotform' column, so no partner is "
                                              "marked - a retired roster of an active club would be restored; check "
                                              "the header (Partners!D1) before applying (docs/RUNBOOK.md, \"Clubs "
                                              "that do not use Jotform\")"])
        self.assertIn(auto_sync.JOTFORM_COLUMN, glow_sync.WARNINGS[0])
        self.assertNotIn(auto_sync.JOTFORM_VALUE, glow_sync.WARNINGS[0])
        del glow_sync.WARNINGS[:]
        write(["name", "region"], [["Partner One", "Africa"]])
        for reader in (glow_sync.read_partners_csv, glow_sync.partners_marker_present):
            with self.assertRaises(SystemExit) as e:
                reader(path)
            self.assertIn("Not a Partners export: expected a 'partner' column", str(e.exception))
        self.assertEqual(glow_sync.WARNINGS, [])
        # the constants the Apps Script side mirrors (appsscript/Roster.gs PARTNER_COLS)
        self.assertEqual(glow_sync.PARTNER_COLS, ("partner", "region", "notes", "jotform"))
        self.assertIn(glow_sync.JOTFORM_COL, glow_sync.PARTNER_COLS)
        self.assertEqual(glow_sync.JOTFORM_COL, glow_sync.PARTNER_COLS[-1])

    def test_the_inactive_rule_is_a_date_before_today_and_the_constant_is_on(self):
        import datetime as dt
        from unittest import mock
        today = dt.date(2026, 10, 7)
        self.assertTrue(glow_sync.RETIRE_INACTIVE)            # Ryan, 2026-10-06: on
        self.assertTrue(glow_sync.inactive_retires("2026-10-06", today))
        self.assertTrue(glow_sync.inactive_retires(" 2026-09-28 ", today))
        self.assertFalse(glow_sync.inactive_retires("2026-10-07", today))     # the same day: kept
        self.assertFalse(glow_sync.inactive_retires("2026-10-08", today))
        self.assertFalse(glow_sync.inactive_retires("", today))              # no date: the safe side
        self.assertFalse(glow_sync.inactive_retires(None, today))
        self.assertFalse(glow_sync.inactive_retires("yesterday", today))
        with mock.patch.object(glow_sync, "RETIRE_INACTIVE", False):
            self.assertFalse(glow_sync.inactive_retires("2026-10-06", today))
        # `today` is the day in the SHEET's zone - the one Roster.gs today_() stamps removed_date
        # in (getSpreadsheetTimeZone(): America/New_York since 2026-09-02, DECISIONS 2026-09-30),
        # not appsscript.json's timeZone (the script project's, America/Chicago) and not UTC: a
        # club emptied at 21:30 New York is dated today there while the UTC date is tomorrow,
        # so a UTC "today" would retire it at the very next dispatch (review finding)
        self.assertEqual(glow_sync.SHEET_ZONE, "America/New_York")
        with open(os.path.join(REPO, "appsscript", "appsscript.json"), encoding="utf-8") as f:
            self.assertNotEqual(json.load(f)["timeZone"], glow_sync.SHEET_ZONE)     # the two are not one thing
        utc = dt.timezone.utc
        self.assertEqual(glow_sync.sheet_today(dt.datetime(2026, 10, 7, 1, 30, tzinfo=utc)), dt.date(2026, 10, 6))
        self.assertEqual(glow_sync.sheet_today(dt.datetime(2026, 10, 7, 3, 59, tzinfo=utc)), dt.date(2026, 10, 6))
        self.assertEqual(glow_sync.sheet_today(dt.datetime(2026, 10, 7, 4, 0, tzinfo=utc)), dt.date(2026, 10, 7))
        self.assertEqual(glow_sync.sheet_today(dt.datetime(2026, 10, 7, 11, 0, tzinfo=utc)), dt.date(2026, 10, 7))  # the daily run
        self.assertEqual(glow_sync.sheet_today(dt.datetime(2026, 1, 15, 4, 30, tzinfo=utc)), dt.date(2026, 1, 14))   # winter: UTC-5
        self.assertEqual(glow_sync.sheet_today(dt.datetime(2026, 1, 15, 5, 0, tzinfo=utc)), dt.date(2026, 1, 15))
        self.assertIsInstance(glow_sync.sheet_today(), dt.date)                                              # the clock
        # the evening case end to end: emptied "today" in New York, the run minutes later (UTC tomorrow)
        evening = dt.datetime(2026, 10, 7, 1, 35, tzinfo=utc)
        self.assertFalse(glow_sync.inactive_retires("2026-10-06", glow_sync.sheet_today(evening)))      # kept
        self.assertTrue(glow_sync.inactive_retires("2026-10-06", glow_sync.sheet_today(evening + dt.timedelta(hours=9))))
        with mock.patch.object(glow_sync, "SHEET_ZONE", "Nowhere/Nothing"):
            with self.assertRaises(SystemExit) as e:
                glow_sync.sheet_today()
            self.assertIn("The time zone database has no 'Nowhere/Nothing'", str(e.exception))
        # the sync and the audit take today from it, the runner checks the constant against the sheet
        self.assertIn("today = sheet_today()", read(os.path.join(REPO, "sync_attendance_form.py")))
        self.assertIn("today = today or sheet_today()", read(os.path.join(REPO, "tools", "form_status.py")))
        self.assertIn("run.check_sheet_zone(sc.time_zone(svc))", read(os.path.join(REPO, "tools", "auto_sync.py")))
        # the latest removed_date per club, from the Roster's rows of any status
        gone = {("Partner Two", "Stars"): self.ROSTER[("Partner Two", "Stars")]}
        self.run_sync(FakeForm(*self.form(switched=True)), inactive=gone,
                      removed={("Partner Two", "Stars"): "2026-10-01"})
        path = os.path.join(self.tmp.name, "roster.csv")
        self.assertEqual(glow_sync.roster_removed(path), {("partner two", "stars"): "2026-10-01"})
        with open(path, encoding="utf-8") as f:
            rows = f.read().splitlines()
        rows.append("DEMOCLUB-SAMPLE-009,Partner Two,Stars,Zoe Quillfeather,inactive,Africa,2026-10-03")
        rows.append("DEMOCLUB-SAMPLE-010,Partner Two,Stars,Yan Quillfeather,inactive,Africa,3 Oct")   # not a date here
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(rows) + "\n")
        self.assertEqual(glow_sync.roster_removed(path), {("partner two", "stars"): "2026-10-03"})
        with open(path, "w", encoding="utf-8") as f:
            f.write("partner,club,full_name,status,region\nPartner One,Stars,Ann Poe,inactive,Africa\n")
        self.assertEqual(glow_sync.roster_removed(path), {})                 # an export without the column

    # ---- the sync
    def test_a_marked_partners_rosters_are_retired_and_nothing_is_written_to_them(self):
        qs, wire = self.form(switched=True)
        fake = FakeForm(qs, wire)
        summary, out = self.summary(fake, partners=self.NO)
        self.assertIn("Form: 999 status ENABLED\nRoster: 2 active clubs in Africa (4 girls); 4 clubs overall; 2 "
                      "club(s) of 1 partner(s) not on Jotform (Partners tab jotform=no) left off this form\n", out)
        for line in self.RETIRED.values():
            self.assertIn(line, out)
        self.assertEqual(fake.calls, ["UPDATE club picker (2 clubs: options)",
                                      f"REPLACE conditions ({len(wire) - 2} rules)"])
        self.assertEqual(fake.writes[0][2], {"question[options]": "Alpha Club|Stars - Partner One"})
        self.assertEqual(sync.WARNINGS, [])
        # no show rule for the two; every roster still in question 18's sum; nothing to q12 / q13
        shown = {a["field"] for _, _, actions in self.rules(fake.writes[1][2]) for a in actions
                 if a.get("visibility") == "Show"} & set(self.QIDS.values())
        self.assertEqual(shown, {"10", "11"})
        (calc,) = [a for _, _, actions in self.rules(fake.writes[1][2]) for a in actions
                   if a.get("resultField") == sync.CONTACT_IDS]
        self.assertEqual((calc["operands"], calc["equation"]), ("500,10,11,12,13", "{10}{11}{12}{13}"))
        self.assertFalse([p for _, p, _ in fake.writes if p in ("/question/12", "/question/13")])
        self.assertEqual(summary["retired"], [
            {"qid": "12", "club": "Stars", "partner": "Partner Two",
             "reason": "not on Jotform (Partner Two, Partners tab jotform=no)"},
            {"qid": "13", "club": "Beta Club", "partner": "Partner Two",
             "reason": "not on Jotform (Partner Two, Partners tab jotform=no)"}])
        self.assertEqual((summary["restored"], summary["retired_before"]), ([], 0))
        self.assertTrue(summary["partners"].endswith("partners.csv"))
        self.assertEqual([n["qid"] for n in summary["sf_names"]], ["10", "11"])    # a retired club sends nothing
        self.assertEqual(summary["sf_name_changes"], [])
        # the runner reads both shapes: the picker update is the counted change, 2 is within the band
        for plan in (auto_sync.parse_plan(out), auto_sync.plan_from_summary(summary)):
            self.assertEqual([(r["qid"], r["club"]) for r in plan["retired"]], [("12", "Stars"), ("13", "Beta Club")])
            self.assertEqual((auto_sync.changes(plan), auto_sync.check_bands(plan), plan["warnings"]), (1, [], []))
            self.assertIn(", 2 retired, update club picker", auto_sync.plan_summary(plan))
        # applied, the form holds them retired: the next run has nothing to do and no ~ line
        fake = FakeForm(qs, wire, apply=True)
        code, _ = self.run_sync(fake, "--apply", partners=self.NO)
        self.assertEqual((code, [(m, p) for m, p, _ in fake.writes]), (0, [("POST", "/question/500"), ("PUT", "/properties")]))
        qs["500"]["options"] = fake.writes[0][2]["question[options]"]
        after = FakeForm(qs, fake.writes[1][2]["properties"]["conditions"])
        del sync.WARNINGS[:]
        summary, out = self.summary(after, partners=self.NO)
        self.assertEqual((after.calls, sync.WARNINGS), ([], []))
        self.assertNotIn("~ retired", out)
        self.assertIn("Retired rosters: 2 already off the Club picker (hidden, no show rule; still in question "
                      "18's sum)", out)
        self.assertIn("(conditions unchanged - skipping the rewrite)", out)
        self.assertIn("nothing to do", out)
        self.assertEqual((summary["retired"], summary["retired_before"]), ([], 2))
        self.assertEqual(auto_sync.changes(auto_sync.parse_plan(out)), 0)      # in-sync to the runner
        # what the sync wrote is the retired state the audit's tests build
        rq, rw = self.retired_form()
        self.assertEqual(sync._norm_rules(fake.writes[1][2]["properties"]["conditions"]), sync._norm_rules(rw))
        self.assertEqual(qs["500"]["options"], rq["500"]["options"])

    def test_the_same_name_branch_retires_the_marked_partners_roster(self):
        # before the switch the two Stars test one text and are told apart by the Partner box:
        # Partner Two's goes, q11 is alone on "Stars", its rule loses the Partner term, the box hides
        qs, wire = self.form()
        fake = FakeForm(qs, wire)
        code, out = self.run_sync(fake, partners=self.NO)
        self.assertEqual(code, 0)
        self.assertIn(self.RETIRED["12"], out)
        self.assertIn(self.RETIRED["13"], out)
        self.assertEqual(fake.calls, ["UPDATE club picker (2 clubs: options)",
                                      f"REPLACE conditions ({len(wire) - 3} rules)", SameNameFixture.HIDE])
        self.assertEqual(fake.writes[0][2], {"question[options]": "Alpha Club|Stars"})
        self.assertEqual(self.shows(fake.writes[1][2], "11"), [("500", "equals", "Stars")])
        self.assertFalse([a for _, _, actions in self.rules(fake.writes[1][2]) for a in actions
                          if a.get("visibility") == "Show" and a["field"] in ("12", "13", sync.PARTNER)])
        self.assertNotIn("Partner box:", out)
        self.assertEqual(sync.WARNINGS, [])
        # ...and the roster whose owner the rule names is the one that goes: Partner One marked instead
        del sync.WARNINGS[:]
        fake = FakeForm(*self.form())
        code, out = self.run_sync(fake, partners={"Partner One": "no"})
        self.assertEqual(code, 0)
        self.assertIn("  ~ retired roster 'Stars' (q11): not on Jotform (Partner One, Partners tab jotform=no)", out)
        self.assertIn("  ~ retired roster 'Alpha Club' (q10): not on Jotform (Partner One, Partners tab jotform=no)", out)
        self.assertEqual(self.shows(fake.writes[1][2], "12"), [("500", "equals", "Stars")])
        self.assertEqual(sync.WARNINGS, [])

    def test_a_club_with_no_active_girl_retires_the_day_after_its_last_removal(self):
        import datetime as dt
        from unittest import mock
        today = glow_sync.sheet_today()          # the sheet's day, as the sync reads it (not UTC's)
        yesterday = str(today - dt.timedelta(days=1))
        gone = {("Partner Two", "Stars"): self.ROSTER[("Partner Two", "Stars")]}
        sheet = {k: v for k, v in self.ROSTER.items() if k not in gone}
        # today's treatment of a same-name leftover (test_a_namesake_going_inactive_changes_nothing)
        kept = "  ! 'Stars' (q12) matched no partner in the sheet - keeping it, but check it in the builder"
        cases = [(yesterday, True, True),        # the day after: retired
                 (str(today), True, False),      # the same day: a two-step roster replacement may be under way
                 ("", True, False),              # no date to go by: the safe side
                 (yesterday, False, False)]      # the constant off: today's treatment
        for when, on, retires in cases:
            for partners in (None, {}):          # the Partners export is not what this trigger needs
                del sync.WARNINGS[:]
                fake = FakeForm(*self.form(switched=True))
                with mock.patch.object(glow_sync, "RETIRE_INACTIVE", on):
                    summary, out = self.summary(fake, roster=sheet, inactive=gone, partners=partners,
                                                removed={("Partner Two", "Stars"): when})
                if retires:
                    self.assertIn("  ~ retired roster 'Stars' (q12): no active girl in the Roster", out, (when, on))
                    self.assertEqual(fake.calls[0], "UPDATE club picker (3 clubs: options)")
                    self.assertEqual(fake.writes[0][2], {"question[options]": "Alpha Club|Beta Club|Stars - Partner One"})
                    self.assertEqual(sync.WARNINGS, [])
                    self.assertEqual([(r["qid"], r["reason"]) for r in summary["retired"]],
                                     [("12", "no active girl in the Roster")])
                    self.assertNotIn("Roster: 3 active clubs in Africa (6 girls); 3 clubs overall;", out)  # no tail
                else:
                    self.assertNotIn("~ retired", out, (when, on))
                    self.assertEqual((fake.calls, sync.WARNINGS), ([], [kept]), (when, on))
        # a later ADD puts it back: active again, its roster is restored (the ~ line, within the bands)
        del sync.WARNINGS[:]
        qs, wire = self.retired_form(gone=("12",))
        fake = FakeForm(qs, wire)
        summary, out = self.summary(fake, partners={})
        self.assertIn("  ~ restored roster 'Stars' (q12): back on the Club picker", out)
        self.assertEqual(auto_sync.check_bands(auto_sync.plan_from_summary(summary)),
                         ["question 5 (what Salesforce reads) would change for 1 existing club(s) - rename each "
                          "Salesforce account named in the warnings first, then apply this region by hand with "
                          "--q5-change-ok (docs/RUNBOOK.md, \"Club names two partners share\")"])   # a shared name

    def test_a_question_the_roster_does_not_know_keeps_todays_treatment(self):
        # a roster whose club is in no Roster row (an incomplete export looks like that): the
        # `?` line and its entry, as ever - never retired on a guess
        three = {**self.ROSTER, ("Partner Three", "Comet Club"): ["Uma Umberlash", "Valeria Wrenfoldy"]}
        self.QIDS = {**self.QIDS, ("Partner Three", "Comet Club"): "20"}
        fake = FakeForm(*self.form(roster=three, switched=True))
        summary, out = self.summary(fake, partners=self.NO)
        self.assertNotIn("Comet Club' (q20)", "".join(self.RETIRED.values()))
        self.assertIn(self.RETIRED["12"], out)
        self.assertNotIn("~ retired roster 'Comet Club'", out)
        self.assertEqual(sync.WARNINGS, ["  ? 'Comet Club' (q20) is on the form but not in the sheet export - "
                                         "keeping its current roster"])
        self.assertEqual(fake.writes[0][2], {"question[options]": "Alpha Club|Comet Club|Stars - Partner One"})
        self.assertEqual(self.shows(fake.writes[1][2], "20"), [("500", "equals", "Comet Club")])
        self.assertEqual(summary["retired_before"], 0)
        # ...and a name with several holders and no word on the owner: today's treatment too (the
        # two Stars on one plain entry with the Partner box, Partner Two marked, the rules gone)
        del sync.WARNINGS[:]
        qs, wire = self.form()
        wire = [c for c in wire if '"field": "12"' not in c["action"] and '"field": "11"' not in c["action"]]
        qs["11"]["options"] = qs["12"]["options"] = "Nobody Known|Nobody Else"       # no owner read-back either
        fake = FakeForm(qs, wire)
        code, out = self.run_sync(fake, partners=self.NO)
        self.assertNotIn("~ retired roster 'Stars'", out)
        self.assertIn(self.RETIRED["13"], out)

    def test_a_retired_roster_comes_back_plain_or_long(self):
        # Beta Club - a name one partner has: restored plain, nothing to warn
        qs, wire = self.retired_form(gone=("13",))
        fake = FakeForm(qs, wire)
        summary, out = self.summary(fake, partners={})
        self.assertIn("  ~ restored roster 'Beta Club' (q13): back on the Club picker", out)
        self.assertEqual(fake.calls, ["UPDATE club picker (4 clubs: options)",
                                      f"REPLACE conditions ({len(wire) + 1} rules)"])
        self.assertEqual(fake.writes[0][2], {"question[options]": "|".join(self.LONG)})
        self.assertEqual(self.shows(fake.writes[1][2], "13"), [("500", "equals", "Beta Club")])
        self.assertEqual((sync.WARNINGS, summary["sf_name_changes"]), ([], []))
        self.assertEqual(summary["restored"], [{"qid": "13", "club": "Beta Club", "partner": "Partner Two",
                                                "reason": "back on the Club picker"}])
        self.assertEqual([n["value"] for n in summary["sf_names"]],
                         ["Alpha Club", "Stars - Partner One", "Stars - Partner Two", "Beta Club"])
        for plan in (auto_sync.parse_plan(out), auto_sync.plan_from_summary(summary)):
            self.assertEqual(([r["qid"] for r in plan["restored"]], auto_sync.check_bands(plan)), (["13"], []))
            self.assertIn(", 1 restored, update club picker", auto_sync.plan_summary(plan))
        # Partner Two's Stars - a name two partners have had: long, as a question-5 change by hand
        # (its namesake's long entry on the picker is not its own)
        del sync.WARNINGS[:]
        qs, wire = self.retired_form(gone=("12",))
        fake = FakeForm(qs, wire)
        summary, out = self.summary(fake, partners={})
        self.assertIn("  ~ restored roster 'Stars' (q12): back on the Club picker", out)
        self.assertEqual(fake.writes[0][2], {"question[options]": "|".join(self.LONG)})
        self.assertEqual(self.shows(fake.writes[1][2], "12"), [("500", "equals", "Stars - Partner Two")])
        self.assertEqual(summary["sf_name_changes"], [{"qid": "12", "club": "Stars", "old": sync.RETIRED_OLD,
                                                       "new": "Stars - Partner Two", "switch": False}])
        self.assertEqual(sync.WARNINGS, ["  ! 'Stars' (q12): Club Name (question 5, what Salesforce reads) changes "
                                         "from '(retired: no rule to read)' to 'Stars - Partner Two' - rename its "
                                         "Salesforce account first; an --apply needs --q5-change-ok"])
        fake = FakeForm(qs, wire, apply=True)
        code, _ = self.run_sync(fake, "--apply", partners={})
        self.assertIn("Refusing: question 5 (what Salesforce reads) would change for 1 existing club(s)", str(code))
        self.assertEqual(fake.writes, [])
        fake = FakeForm(qs, wire, apply=True)
        code, _ = self.run_sync(fake, "--apply", "--q5-change-ok", partners={})
        self.assertEqual((code, [(m, p) for m, p, _ in fake.writes]), (0, [("POST", "/question/500"), ("PUT", "/properties")]))
        # the runner's question-5 band holds it for the hand apply
        plan = auto_sync.plan_from_summary(summary)
        self.assertEqual(len(auto_sync.q5_changes(plan)), 1)
        self.assertTrue(any("question 5 (what Salesforce reads) would change" in r for r in auto_sync.check_bands(plan)))
        # a retired roster whose partner is still marked is not restored by the same run
        del sync.WARNINGS[:]
        fake = FakeForm(*self.retired_form())
        summary, out = self.summary(fake, partners=self.NO)
        self.assertEqual((fake.calls, summary["restored"], summary["retired_before"]), ([], [], 2))

    def test_without_a_partners_export_a_restore_is_warned_and_refused(self):
        qs, wire = self.retired_form(gone=("13",))
        fake = FakeForm(qs, wire)
        summary, out = self.summary(fake)
        self.assertNotIn("~ restored", out)
        self.assertEqual(sync.WARNINGS, [
            "  ! 'Beta Club' (q13) has no Club picker entry and no show rule although its club is active in the "
            "Roster - a retired roster, or a new roster of an apply that stopped half-way: pass --partners "
            "<Partners export> (the runner always does) and the run restores it or keeps it retired"])
        self.assertEqual(fake.calls[0], "UPDATE club picker (4 clubs: options)")     # the dry run still shows the plan
        self.assertEqual((summary["restored"][0]["qid"], summary["partners"]), ("13", None))
        fake = FakeForm(qs, wire, apply=True)
        code, _ = self.run_sync(fake, "--apply")
        self.assertIn("Refusing: 1 roster(s) would be restored without a Partners export (the '!' lines above) - "
                      "nothing written", str(code))
        self.assertEqual(fake.writes, [])
        # the flag needs the Roster
        import contextlib
        import io
        from unittest import mock
        argv = ["sync_attendance_form.py", "x.csv", "--form", "999", "--partners", "p.csv"]
        with mock.patch.object(sys, "argv", argv), mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test"}), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as e:
            sync.main()
        self.assertIn("--partners needs --roster", str(e.exception))

    def test_a_partners_export_missing_a_partner_with_active_clubs_is_refused(self):
        fake = FakeForm(*self.form(switched=True))
        code, out = self.run_sync(fake, "--partners", self.partners_csv({"Partner One": ""}))
        self.assertIn("Partners export lists 1 of 2 partners with active clubs - missing: Partner Two - a truncated "
                      "export, or rows deleted from the Partners tab? nothing done", str(code))
        self.assertEqual(fake.calls, [])
        self.assertIn("Form: 999 status ENABLED", out)
        # a partner with inactive rows only is not required (nothing of it is on the picker's side)
        gone = {("Partner Two", "Stars"): self.ROSTER[("Partner Two", "Stars")],
                ("Partner Two", "Beta Club"): self.ROSTER[("Partner Two", "Beta Club")]}
        sheet = {k: v for k, v in self.ROSTER.items() if k not in gone}
        fake = FakeForm(*self.form(roster=sheet, switched=True))
        code, _ = self.run_sync(fake, "--partners", self.partners_csv({"Partner One": ""}), roster=sheet, inactive=gone)
        self.assertEqual(code, 0)
        # every club of the region marked: the form is not synced down to an empty picker
        fake = FakeForm(*self.form(switched=True))
        code, _ = self.run_sync(fake, partners={"Partner One": "no", "Partner Two": "no"})
        self.assertIn("Every active club in Africa belongs to a partner marked jotform=no", str(code))
        self.assertIn("empty Club picker", str(code))
        self.assertEqual(fake.calls, [])

    def test_a_partners_export_without_the_jotform_column_warns_and_never_restores_unattended(self):
        import csv
        # the header lost its column (renamed, moved, one inserted before it): nobody is marked,
        # so a retired roster of an active club reads as one to restore - said, never applied
        path = os.path.join(self.tmp.name, "partners_old.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["partner", "region", "notes"])
            for p in ("Partner One", "Partner Two"):
                w.writerow([p, "Africa", ""])
        column = ("  ! Partners tab: the export has no 'jotform' column, so no partner is marked - a retired roster of "
                  "an active club would be restored; check the header (Partners!D1) before applying (docs/RUNBOOK.md, "
                  "\"Clubs that do not use Jotform\")")
        qs, wire = self.retired_form(gone=("13",))
        fake = FakeForm(qs, wire)
        summary, out = self.summary(fake, "--partners", path)
        self.assertIn("  ~ restored roster 'Beta Club' (q13): back on the Club picker", out)   # the dry run says so
        self.assertEqual(sync.WARNINGS, [column])
        self.assertEqual(fake.calls, ["UPDATE club picker (4 clubs: options)", f"REPLACE conditions ({len(wire) + 1} rules)"])
        fake = FakeForm(qs, wire, apply=True)
        code, _ = self.run_sync(fake, "--apply", "--partners", path)
        self.assertIn("Refusing: 1 roster(s) would be restored from a Partners export that has no 'jotform' column "
                      "(nobody can be marked in it) - nothing written", str(code))
        self.assertIn("Partners!D1 = jotform", str(code))
        self.assertEqual(fake.writes, [])
        # the runner: ATTENTION for the export, and a plan that restores from it is outside the bands
        plan = auto_sync.plan_from_summary(summary)
        self.assertEqual(auto_sync.no_jotform_column(plan), [column.strip()])     # the summary strips them
        (reason,) = auto_sync.check_bands(plan)
        self.assertIn("would put 1 club(s) back on the Club picker from a Partners export that has no jotform column", reason)
        run = AutoSyncFixture.run_region(self, out, apply=True)
        self.assertEqual((run.synced, [r[7] for r in run.results]), ([False], ["attention"]))
        self.assertIn("no jotform column", run.results[0][8])
        self.assertEqual([t for t, _ in run.attention][0], "Africa: the Partners export has no jotform column")
        self.assertIn("Partners!D1 = jotform", run.attention[0][1])
        self.assertTrue(run.attention[1][0].startswith("Africa: not applied - "))
        self.assertIn("- RESTORE Beta Club (q13): back on the Club picker", run.attention[1][1])
        # with nothing to restore the warning alone: in-sync, the ATTENTION still raised
        del sync.WARNINGS[:]
        fake = FakeForm(*self.form(switched=True))
        summary, out = self.summary(fake, "--partners", path)
        self.assertEqual((fake.calls, sync.WARNINGS), ([], [column]))
        self.assertEqual(auto_sync.check_bands(auto_sync.plan_from_summary(summary)), [])
        run = AutoSyncFixture.run_region(self, out)
        self.assertEqual([r[7:9] for r in run.results], [["in-sync", "Partners export without a jotform column"]])
        self.assertEqual([t for t, _ in run.attention], ["Africa: the Partners export has no jotform column"])
        # a roster the Roster says is retired stays so: the export marks nobody, but the inactive rule still holds
        del sync.WARNINGS[:]
        gone = {("Partner Two", "Stars"): self.ROSTER[("Partner Two", "Stars")]}
        sheet = {k: v for k, v in self.ROSTER.items() if k not in gone}
        fake = FakeForm(*self.retired_form(gone=("12",)))
        summary, out = self.summary(fake, "--partners", path, roster=sheet, inactive=gone,
                                    removed={("Partner Two", "Stars"): "2020-01-01"})
        self.assertEqual((fake.calls, summary["restored"], summary["retired_before"]), ([], [], 1))

    def test_an_odd_jotform_value_is_yes_plus_a_warning_the_runner_reports(self):
        fake = FakeForm(*self.form(switched=True))
        summary, out = self.summary(fake, partners={"Partner Two": "maybe"})
        self.assertEqual(fake.calls, [])
        self.assertNotIn("~ retired", out)
        self.assertEqual(sync.WARNINGS, ["  ! Partners tab: 'Partner Two' has jotform='maybe' - only yes, no or "
                                         "blank are understood; treated as yes"])
        plan = auto_sync.plan_from_summary(summary)
        self.assertEqual((len(auto_sync.odd_jotform_values(plan)), auto_sync.check_bands(plan)), (1, []))
        run = AutoSyncFixture.run_region(self, out)
        self.assertEqual([r[7:9] for r in run.results], [["in-sync", "1 jotform value(s) not understood"]])
        (title, detail), = run.attention
        self.assertEqual(title, "Africa: 1 Partners-tab jotform value(s) not understood")
        self.assertIn("- ! Partners tab: 'Partner Two' has jotform='maybe'", detail)
        self.assertIn("Clubs that do not use Jotform", detail)
        # with a roster change in the same plan the change is applied and the warning reported
        busy = out.replace("  nothing to do - form already matches the sheet", "  - CREATE roster 'Gamma Club' (2 girls)")
        run = AutoSyncFixture.run_region(self, busy, apply=True)
        self.assertEqual((run.synced, [r[7] for r in run.results], len(run.attention)), ([False, True], ["applied"], 1))
        self.assertIn("1 jotform value(s) not understood", run.results[0][8])

    def test_the_form_status_line_and_disabled_ok(self):
        qs, wire = self.form(switched=True)
        fake = FakeForm(qs, wire, status="DISABLED")
        code, out = self.run_sync(fake)
        self.assertEqual((code, fake.calls), (0, []))                       # a dry run reads it
        self.assertIn("Form: 999 status DISABLED\nRoster: ", out)
        fake = FakeForm(qs, wire, apply=True, status="DISABLED")
        code, _ = self.run_sync(fake, "--apply")
        self.assertIn("Refusing: form 999 is DISABLED, not ENABLED - a write nobody can see", str(code))
        self.assertIn("--disabled-ok", str(code))
        self.assertEqual(fake.writes, [])
        fake = FakeForm(qs, wire, apply=True, status="DISABLED")
        self.assertEqual(self.run_sync(fake, "--apply", "--disabled-ok")[0], 0)
        fake = FakeForm(qs, wire, apply=True, status="")
        code, _ = self.run_sync(fake, "--apply")
        self.assertIn("form 999 is of unknown status, not ENABLED", str(code))   # refused, never guessed
        code, out = self.run_sync(FakeForm(qs, wire, status=""))
        self.assertIn("Form: 999 status not reported", out)

    def test_the_roster_lines_tail_is_free_text_to_the_runner(self):
        line = ("Roster: 182 active clubs in Africa (3518 girls); 364 clubs overall; 38 club(s) of 3 partner(s) not "
                "on Jotform (Partners tab jotform=no) left off this form")
        m = auto_sync.ROSTER_RX.match(line)
        self.assertEqual((m["clubs"], m["girls"], m["all"]), ("182", "3518", "364"))
        plan = auto_sync.parse_plan(line + "\n\nDRY RUN (use --apply to write):\n  - REPLACE conditions (213 rules)\n")
        self.assertEqual((plan["roster_clubs"], plan["roster_girls"], plan["rules"]), (182, 3518, 213))

    # ---- the runner
    def test_the_runner_bands_the_retirements_and_the_restores(self):
        def text(kind, n):
            why = ("not on Jotform (Partner Nine, Partners tab jotform=no)" if kind == "retired"
                   else "back on the Club picker")
            return ("Roster: 20 active clubs in Africa (200 girls); 300 clubs overall\n"
                    + "".join(f"  ~ {kind} roster 'Club {i}' (q{100 + i}): {why}\n" for i in range(n))
                    + "\nDRY RUN (use --apply to write):\n  - UPDATE club picker (20 clubs: options)\n"
                    "  - REPLACE conditions (50 rules)\n")
        for kind, band, phrase in (("retired", "max_retires", "would take 6 clubs off the Club picker at once (band: 5)"),
                                   ("restored", "max_restores", "would put 6 clubs back on the Club picker at once (band: 5)")):
            plan = auto_sync.parse_plan(text(kind, 6))
            self.assertEqual(len(plan[kind]), 6)
            self.assertEqual(plan[kind][0], {"qid": "100", "club": "Club 0", "reason": plan[kind][0]["reason"]})
            self.assertEqual(plan["warnings"], [])                 # a ~ line is no warning
            (reason,) = auto_sync.check_bands(plan)
            self.assertIn(phrase, reason)
            self.assertIn("apply by hand after checking", reason)
            self.assertEqual(auto_sync.check_bands(plan, **{band: 6}), [])
            self.assertIn(f", 6 {kind}, update club picker", auto_sync.plan_summary(plan))
            run = AutoSyncFixture.run_region(self, text(kind, 6), apply=True)
            self.assertEqual((run.synced, [r[7] for r in run.results]), ([False], ["attention"]))
            self.assertIn(phrase, run.results[0][8])
            self.assertIn(f"- {'RETIRE' if kind == 'retired' else 'RESTORE'} Club 0 (q100): ", run.attention[0][1])
            run = AutoSyncFixture.run_region(self, text(kind, 6), apply=True, **{band: 6})
            self.assertEqual((run.synced, [r[7] for r in run.results]), ([False, True], ["applied"]))
            run = AutoSyncFixture.run_region(self, text(kind, 5), apply=True)
            self.assertEqual([r[7] for r in run.results], ["applied"])
            self.assertIn(f", 5 {kind}, update club picker; verified clean", run.results[0][8])
        # the summary file gives the same
        summary = {"creates": [], "updates": [], "deletes": [], "rules": 50, "warnings": [],
                   "calls": ["UPDATE club picker (20 clubs: options)"],
                   "retired": [{"qid": str(100 + i), "club": f"Club {i}", "partner": "Partner Nine",
                                "reason": "not on Jotform (Partner Nine, Partners tab jotform=no)"} for i in range(6)],
                   "restored": [{"qid": "200", "club": "Comet Club", "partner": "Partner Nine", "reason": "back on the Club picker"}]}
        plan = auto_sync.plan_from_summary(summary)
        self.assertEqual((len(plan["retired"]), len(plan["restored"]), len(auto_sync.check_bands(plan))), (6, 1, 1))
        self.assertEqual(set(plan), set(auto_sync.parse_plan("")))
        # the patterns tell the two lines apart, and the defaults are the runner's flags
        self.assertTrue(auto_sync.RETIRED_RX.match("  ~ retired roster 'Club (B)' (q12): no active girl in the Roster"))
        self.assertFalse(auto_sync.RETIRED_RX.match("  ~ restored roster 'Club (B)' (q12): back on the Club picker"))
        self.assertFalse(auto_sync.RESTORED_RX.match("  ~ retired roster 'A' (q1): x"))
        src = read(os.path.join(REPO, "tools", "auto_sync.py"))
        self.assertIn('ap.add_argument("--max-retires", type=int, default=5,', src)
        self.assertIn('ap.add_argument("--max-restores", type=int, default=5,', src)

    def test_the_runner_checks_the_sheets_zone_against_the_constant(self):
        # the sheet stamps removed_date in its own zone; the sync takes "today" in SHEET_ZONE; the
        # runner, which reads the sheet's setting anyway, says when the two differ (the rule is
        # then off by the difference) - a log line when they agree, never a failed run
        import tempfile
        import types
        from unittest import mock
        with tempfile.TemporaryDirectory() as out:
            args = types.SimpleNamespace(apply=False, out=out, max_creates=5, max_updates=20, trigger="test", run_url="")
            run = auto_sync.Run(args)
            with mock.patch("builtins.print"):
                run.check_sheet_zone(glow_sync.SHEET_ZONE)
                self.assertEqual((run.attention, run.lines[-1]), ([], "Sheet zone: America/New_York (as glow/sync.py SHEET_ZONE)"))
                run.check_sheet_zone("America/Chicago")
        (title, detail), = run.attention
        self.assertEqual(title, "The sheet's time zone is America/Chicago, the tools expect America/New_York")
        self.assertIn("glow/sync.py SHEET_ZONE says America/New_York", detail)
        self.assertIn("Clubs that do not use Jotform", detail)
        self.assertEqual(run.lines[-1], "  ! sheet zone America/Chicago differs from glow/sync.py SHEET_ZONE America/New_York")
        self.assertFalse(run.failed)
        # read where the tabs are exported (a --roster run reads no sheet, and gets no check)
        src = read(os.path.join(REPO, "tools", "auto_sync.py"))
        self.assertIn("run.partners = run.export_partners(svc)\n        run.check_sheet_zone(sc.time_zone(svc))", src)

    def test_a_disabled_form_is_skipped_and_an_unread_status_is_failed(self):
        run = AutoSyncFixture.run_region(self, self.DRY, apply=True, status="DISABLED")
        self.assertEqual((run.synced, run.failed, run.attention), ([], False, []))
        self.assertEqual([r[7:9] for r in run.results], [["skipped", "form DISABLED"]])
        self.assertIn(f"  form {auto_sync.REGIONAL_FORMS['Africa']} is DISABLED - not synced", run.lines)
        run = AutoSyncFixture.run_region(self, self.DRY, apply=True, status="")
        self.assertEqual([r[7:9] for r in run.results], [["skipped", "form status not reported"]])
        run = AutoSyncFixture.run_region(self, self.DRY, apply=True, status=RuntimeError("boom"))
        self.assertEqual((run.synced, run.failed), ([], True))
        self.assertEqual(run.results[0][7:9], ["failed", "could not read form status: RuntimeError: boom"])
        # read_status itself: GET /form/{id} through the run's client, under the retries
        import types
        from unittest import mock
        run = auto_sync.Run(types.SimpleNamespace(apply=False, out="", max_creates=5, max_updates=20,
                                                  trigger="test", run_url=""))
        calls = []

        class Client_:
            def get(self, path):
                calls.append(path)
                if len(calls) < 3:
                    raise RuntimeError("nope")
                return {"status": "ENABLED", "count": "0"}
        run.client = Client_()
        with mock.patch.object(auto_sync.time, "sleep", lambda s: None), mock.patch("builtins.print"):
            self.assertEqual(run.read_status("262382821971058"), "ENABLED")
        self.assertEqual(calls, ["/form/262382821971058"] * 3)
        run.client = types.SimpleNamespace(get=lambda path: {"count": "0"})
        self.assertEqual(run.read_status("1"), "")
        # the SyncLog's result list, as the RUNBOOK writes it
        doc = read(os.path.join(REPO, "docs", "RUNBOOK.md"))
        self.assertIn("`attention`, `skipped`, `failed`", doc)

    def test_the_partners_export_travels_with_every_sync_and_verify_call(self):
        import tempfile
        import types
        from unittest import mock
        clean = {"error_conditions": 0, "salesforce": True, "rule_problems": [], "languages": ["a"] * 12,
                 "region_check": {"missing_from_form": [], "not_in_roster": [], "rosters_out_of_date": []}}
        with tempfile.TemporaryDirectory() as out:
            run = auto_sync.Run(types.SimpleNamespace(apply=True, out=out, max_creates=5, max_updates=20,
                                                      trigger="test", run_url=""))
            run.partners = os.path.join(out, "partners.csv")
            seen = []

            def cmd(argv, label):
                seen.append((label, argv))
                if label.startswith("sync"):
                    return types.SimpleNamespace(returncode=0, stdout=self.DRY, stderr="")
                if label == "verify":
                    return types.SimpleNamespace(returncode=0, stdout=json.dumps([clean]), stderr="")
                return types.SimpleNamespace(returncode=0, stdout="", stderr="")
            with mock.patch.object(run, "cmd", cmd), mock.patch.object(run, "read_status", lambda form: "ENABLED"), \
                    mock.patch.object(run, "save_conditions", lambda form: None), mock.patch("builtins.print"):
                run.region("Africa", os.path.join(out, "roster.csv"))
            self.assertEqual([r[7] for r in run.results], ["applied"])
            self.assertEqual([label for label, _ in seen], ["sync Africa", "backup", "sync Africa --apply", "verify"])
            for label, argv in seen:
                if label == "backup":
                    self.assertNotIn("--partners", argv)
                    continue
                self.assertIn("--partners", argv, label)
                self.assertEqual(argv[argv.index("--partners") + 1], run.partners, label)
            self.assertIn("--apply", seen[2][1])
            self.assertNotIn("--apply", seen[0][1])
            # (never in main(): --roster needs --partners) without one nothing is added
            run.partners = None
            seen.clear()
            with mock.patch.object(run, "cmd", cmd):
                run.sync("r.csv", "Africa", "1", apply=False)
            self.assertNotIn("--partners", seen[0][1])
            # the exported Partners tab is written beside the Roster export
            run.args.out = out
            svc = object()
            with mock.patch.object(auto_sync.sc, "read_tab", lambda s, tab: [["partner", "region", "notes", "jotform"],
                                                                              ["Partner One", "Africa", "", "no"]]), \
                    mock.patch("builtins.print"):
                path = run.export_partners(svc)
            self.assertEqual(os.path.basename(path), f"partners_{run.stamp}.csv")
            self.assertEqual(glow_sync.read_partners_csv(path), {"partner one": "no"})
            self.assertIn(f"Partners: exported 1 rows -> {os.path.relpath(path, auto_sync.REPO)}", run.lines)

    def test_the_verify_step_notes_a_skipped_check_and_counts_rosters_awaiting_retirement(self):
        clean = {"error_conditions": 0, "salesforce": True, "rule_problems": [], "languages": ["a"] * 12,
                 "duplicate_club_questions": []}
        self.assertEqual(auto_sync.verify_report(dict(clean, region_check={"skipped": "DISABLED"})),
                         ([], ["region check skipped (form DISABLED)"]))
        rc = {"missing_from_form": [], "not_in_roster": [], "rosters_out_of_date": [],
              "retired": ["Stars", "Beta Club"], "awaiting_retirement": []}
        self.assertEqual(auto_sync.verify_report(dict(clean, region_check=rc)), ([], []))
        rc["awaiting_retirement"] = ["Beta Club"]
        problems, notes = auto_sync.verify_report(dict(clean, region_check=rc))
        self.assertEqual((problems, notes), (["1 roster(s) still await retirement: Beta Club"], []))
        # the runner's apply reads applied-with-problems on it
        run = AutoSyncFixture.run_region(self, self.DRY, apply=True, region_check={"awaiting_retirement": ["Beta Club"]})
        self.assertEqual([r[7] for r in run.results], ["applied-with-problems"])
        self.assertIn("1 roster(s) still await retirement: Beta Club", run.results[0][8])


# SameNameFixture's form predates the session-notes field (live on every form since task #105,
# which set glow.layout.NOTES_EXPECTED): its absence is pinned in test/session_notes_test.py.
@mock.patch.object(layout, "NOTES_EXPECTED", False)
class RetiredRostersAudit(unittest.TestCase):
    """tools/form_status.py and the retired rosters (docs/plans/2026-10-06-clubs-off-
    jotform.md): with --partners a roster the Roster says is retired is clean off the
    picker without a rule, awaits the next sync apply while it still has one, and a
    roster off the picker whose club is active is a problem - as every such roster is
    without --partners; a disabled form's region check and served page are skipped;
    the served page's always-hidden count. Fictional names."""

    ROSTER, QIDS, LONG = SameNameFixture.ROSTER, SameNameFixture.QIDS, SameNameFixture.LONG
    AFRICA = glow_forms.REGIONALS["Africa"]
    NO = {"partner two": "no"}

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.roster = self.roster_csv()

    def tearDown(self):
        self.tmp.cleanup()

    def roster_csv(self, roster=None, inactive=None, removed=None, name="roster.csv"):
        """A Roster export: `roster` active in Africa, `inactive` rows of another status
        with the removed_date `removed` gives their club."""
        import csv
        roster = self.ROSTER if roster is None else roster
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["girl_id", "partner", "club", "full_name", "status", "region", "removed_date"])
            for status, clubs in (("active", roster), ("inactive", inactive or {})):
                for (partner, club), names in clubs.items():
                    for n, name_ in enumerate(names):
                        w.writerow([f"DEMOCLUB-SAMPLE-{n:03d}", partner, club, name_, status, "Africa",
                                    (removed or {}).get((partner, club), "") if status != "active" else ""])
        return path

    def form(self, retired=(), **kw):
        """SameNameFlow's switched form, every question carrying its qid, with the rosters
        `retired` as the sync leaves them (no show rule, off the picker)."""
        qs, wire = SameNameFixture.form(SameNameFixture(), switched=True, **kw)
        qs["2"] = {"type": "control_button", "text": "Submit", "name": "submit2", "order": "60"}
        if retired:
            option_of, partner_of = SameNameFixture.texts(SameNameFixture(), self.ROSTER, True)
            keep = {q: o for q, o in option_of.items() if q not in retired}
            qs["500"]["options"] = "|".join(sorted(set(keep.values()), key=str.lower))
            modules = {y: o.split("|") for y, o in SameNameFixture.MODULES.items()}
            conds = sync.build_conditions(keep, partner_of, modules, picker="500", retired=retired)
            wire = [dict(c, terms=json.dumps(c["terms"]), action=json.dumps(c["action"])) for c in conds]
        for q_id, q in qs.items():
            q.setdefault("qid", q_id)
        return qs, wire

    @staticmethod
    def verified(rep):
        """auto_sync.verify_report over the report, the fakes' own gaps filled (no integration, two
        languages, no translation store: none of them this plan's)."""
        return auto_sync.verify_report(dict(rep, languages=["a"] * 12, salesforce=True, names_dictionary={"checked": True}))

    def report(self, qs, wire, marks=None, roster=None, status="ENABLED", form=None):
        """form_report as main() calls it: the Roster's regions, holders and facts from
        `roster` (the export), the Partners marks (None: no --partners)."""
        roster = roster or self.roster

        class Fake:
            def get(self, path, **params):
                if path.endswith("/questions"):
                    return copy.deepcopy(qs)
                if path.endswith("/properties"):
                    return {"conditions": wire, "language": [{"options": "English (US)|Español"}],
                            "clearFieldOnHide": "disable"}
                return {"title": "t", "status": status, "count": "0"}
        facts = form_status.roster_facts(roster, marks)
        partners_of = facts["holders"] or None
        facts = facts if partners_of else None
        return form_status.form_report(form or self.AFRICA, Fake(), form_status.load_roster(roster), partners_of, facts)

    def printed(self, qs, wire, *extra, partners=None, status="ENABLED", page=None):
        """main()'s printed report for the Africa form (never the public page: `page`, if
        given, stands in for it)."""
        import contextlib
        import csv
        import io
        from unittest import mock

        class Fake:
            def get(self, path, **params):
                if path.endswith("/questions"):
                    return copy.deepcopy(qs)
                if path.endswith("/properties"):
                    return {"conditions": wire, "language": [{"options": "English (US)|Español"}],
                            "clearFieldOnHide": "disable"}
                return {"title": "t", "status": status, "count": "0"}
        argv = ["form_status.py", "--form", self.AFRICA, "--roster", self.roster, *extra]
        if partners is not None:
            path = os.path.join(self.tmp.name, "partners.csv")
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(glow_sync.PARTNER_COLS)
                for p in ("Partner One", "Partner Two"):
                    w.writerow([p, "Africa", "", partners.get(p, "")])
            argv += ["--partners", path]
        fetched = []

        def public_page(fid):
            fetched.append(fid)
            return page or ""
        out = io.StringIO()
        with mock.patch.object(form_status, "Client", lambda key: Fake()), \
                mock.patch.object(form_status, "public_page", public_page), \
                mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}), \
                mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(out):
            form_status.main()
        return out.getvalue(), fetched

    def test_a_retired_roster_is_clean_with_the_partners_export(self):
        qs, wire = self.form(retired=("12", "13"))
        rep = self.report(qs, wire, marks=self.NO)
        self.assertEqual(rep["rule_problems"], [])
        self.assertEqual(rep["retired_rosters"], {"total": 2, "not_on_jotform": 2, "no_active_girl": 0})
        self.assertEqual((rep["retired_qids"], rep["awaiting_retirement"]), (["12", "13"], 0))
        self.assertEqual((rep["rule_summary"]["clubs"], rep["rule_summary"]["live_rosters"],
                          rep["rule_summary"]["show_rules"], rep["rule_summary"]["aggregate_rosters"]), (4, 2, 2, 4))
        # the region check: Partner Two's share of "Stars" leaves the union compare, Beta Club leaves want
        self.assertEqual(rep["region_check"], {
            "roster_clubs": 2, "missing_from_form": [], "not_in_roster": [], "rosters_out_of_date": [],
            "retired": ["Stars", "Beta Club"], "awaiting_retirement": []})
        out, _ = self.printed(qs, wire, partners={"Partner Two": "no"})
        self.assertIn("Roster (active girls): {'Africa': 2} clubs per region; not on Jotform: Africa 2\n", out)
        self.assertIn("   retired rosters: 2 (not on Jotform 2, no active girl 0)\n", out)
        self.assertIn("   rules: 2 show-rules for 2 live rosters (4 on the form), Contact_IDs aggregate covers 4  → CLEAN", out)
        self.assertIn("   vs Roster (2 clubs in region): 0 missing from form, 0 on form but not in roster, 0 rosters "
                      "differ, 2 retired\n", out)
        for name in ("Sue Moe", "Liz Noe", "Eve Hoe"):          # counts and club names only
            self.assertNotIn(name, out)
        # the verify step reads it clean
        self.assertEqual(self.verified(rep), ([], []))
        # a retired roster whose girls differ from the Roster's is no "differs": its options are frozen
        qs["13"]["options"] = "Nobody Known"
        self.assertEqual(self.report(qs, wire, marks=self.NO)["region_check"]["rosters_out_of_date"], [])

    def test_a_marked_roster_still_on_the_form_awaits_the_next_apply(self):
        qs, wire = self.form()
        rep = self.report(qs, wire, marks=self.NO)
        self.assertEqual(rep["rule_problems"], [])
        self.assertEqual(rep["retired_rosters"], {"total": 0, "not_on_jotform": 0, "no_active_girl": 0})
        self.assertEqual(rep["awaiting_retirement"], 2)
        self.assertEqual((rep["region_check"]["retired"], rep["region_check"]["awaiting_retirement"]),
                         ([], ["Stars", "Beta Club"]))
        self.assertEqual((rep["region_check"]["roster_clubs"], rep["region_check"]["not_in_roster"]), (2, []))
        out, _ = self.printed(qs, wire, partners={"Partner Two": "no"})
        self.assertIn("rules: 4 show-rules for 4 rosters, Contact_IDs aggregate covers 4  → CLEAN", out)
        self.assertIn("0 rosters differ, 2 await retirement (the next sync apply)\n", out)
        # a note to the audit, a problem to the verify step (an apply leaves nothing awaiting)
        problems, _ = self.verified(rep)
        self.assertEqual(problems, ["2 roster(s) still await retirement: Stars, Beta Club"])
        # without the marks the same form is simply in step
        rep = self.report(qs, wire)
        self.assertEqual((rep["rule_problems"], rep["awaiting_retirement"], rep["region_check"]["roster_clubs"]), ([], 0, 3))

    def test_without_the_partners_export_a_retired_roster_of_an_active_club_is_a_problem(self):
        qs, wire = self.form(retired=("12", "13"))
        rep = self.report(qs, wire)
        self.assertEqual(rep["rule_problems"], [
            "'Stars' (q12) is off the Club picker but its club is active in the Roster - pass --partners if its "
            "partner is not on Jotform, else the next sync apply restores it",
            "'Beta Club' (q13) is off the Club picker but its club is active in the Roster - pass --partners if its "
            "partner is not on Jotform, else the next sync apply restores it"])
        self.assertEqual(rep["retired_rosters"]["total"], 0)
        out, _ = self.printed(qs, wire)
        self.assertIn("2 PROBLEM(S)", out)
        self.assertNotIn("show-rules, expected 1", out)
        self.assertNotIn("club picker misses", out)
        # the same with the export when the partner is not marked: the next apply restores it
        self.assertEqual(len(self.report(qs, wire, marks={})["rule_problems"]), 2)
        # and the Roster's own shape of the problem: a roster without its rule on a form the
        # audit is given no Roster for keeps today's lines
        rep = form_status.form_report(self.AFRICA, type("F", (), {"get": lambda self, path, **k: (
            copy.deepcopy(qs) if path.endswith("/questions") else
            {"conditions": wire, "clearFieldOnHide": "disable"} if path.endswith("/properties") else
            {"title": "t", "status": "ENABLED", "count": "0"})})(), {})
        self.assertIn("'Stars' (q12) has 0 show-rules, expected 1", rep["rule_problems"])

    def test_a_club_with_no_active_girl_is_retired_the_day_after_and_a_namesakes_entry_is_not_its_own(self):
        import datetime as dt
        from unittest import mock
        today = glow_sync.sheet_today()          # the sheet's day, as the audit reads it (not UTC's)
        gone = {("Partner Two", "Stars"): self.ROSTER[("Partner Two", "Stars")]}
        sheet = {k: v for k, v in self.ROSTER.items() if k not in gone}
        qs, wire = self.form(retired=("12",))          # q11's "Stars - Partner One" stays on the picker
        for when, reason in ((str(today - dt.timedelta(days=1)), "no active girl"), (str(today), None)):
            roster = self.roster_csv(sheet, gone, {("Partner Two", "Stars"): when}, name=f"r{when}.csv")
            rep = self.report(qs, wire, marks={}, roster=roster)
            if reason:
                self.assertEqual(rep["rule_problems"], [])
                self.assertEqual(rep["retired_rosters"], {"total": 1, "not_on_jotform": 0, "no_active_girl": 1})
                self.assertEqual(rep["region_check"]["retired"], ["Stars"])
                self.assertEqual(rep["region_check"]["rosters_out_of_date"], [])  # q11 alone against Partner One's girls
            else:
                # the same day: not retired, not stray (its club is not active) - today's lines, the
                # inactive namesake's girls counted against the name included
                self.assertEqual(rep["rule_problems"], ["'Stars' (q12) has 0 show-rules, expected 1",
                                                        "club picker misses 1 club(s): ['Stars']"])
                self.assertEqual(rep["region_check"]["rosters_out_of_date"], [("Stars", 0, 2)])
        roster = self.roster_csv(sheet, gone, {("Partner Two", "Stars"): str(today - dt.timedelta(days=1))}, name="r3.csv")
        with mock.patch.object(glow_sync, "RETIRE_INACTIVE", False):
            self.assertEqual(self.report(qs, wire, marks={}, roster=roster)["retired_rosters"]["total"], 0)
        # off_picker: a roster's own entries are its text and "<text> - <its partner>"
        self.assertEqual(form_status.off_picker(qs, wire, {"12": "Partner Two"}), {"12"})
        self.assertEqual(form_status.off_picker(qs, wire), set())           # owner unknown: any long name of its text
        self.assertEqual(form_status.off_picker(*self.form(retired=("13",))), {"13"})

    def test_a_disabled_forms_region_check_and_served_page_are_skipped(self):
        qs, wire = self.form()
        rep = self.report(qs, wire, marks=self.NO, status="DISABLED")
        self.assertEqual(rep["region_check"], {"skipped": "DISABLED"})
        self.assertEqual(rep["status"], "DISABLED")
        self.assertEqual(self.verified(rep),
                         ([], ["region check skipped (form DISABLED)"]))
        out, fetched = self.printed(qs, wire, "--rendered", partners={"Partner Two": "no"}, status="DISABLED")
        self.assertEqual(fetched, [])                                        # the public page is never read
        self.assertIn('[DISABLED]', out)
        self.assertIn("   rendered: skipped (form DISABLED)\n", out)
        self.assertIn("   vs Roster: skipped (form DISABLED)\n", out)
        self.assertNotIn("rendered picker", out)
        self.assertIn("→ CLEAN", out)
        # an enabled form's page is read, as ever
        _, fetched = self.printed(qs, wire, "--rendered", page="<html></html>")
        self.assertEqual(fetched, [self.AFRICA])

    def test_a_form_whose_status_is_not_reported_is_skipped_like_a_disabled_one(self):
        # GET /form/{id} without a status: the region check and the served page are skipped and
        # named as such (a falsy marker once sent main() looking for the clubs count: KeyError)
        qs, wire = self.form()
        rep = self.report(qs, wire, marks=self.NO, status=None)
        self.assertEqual(rep["region_check"], {"skipped": "status not reported"})
        self.assertIsNone(rep["status"])
        self.assertEqual(self.verified(rep), ([], ["region check skipped (form status not reported)"]))
        out, fetched = self.printed(qs, wire, "--rendered", partners={"Partner Two": "no"}, status=None)
        self.assertEqual(fetched, [])
        self.assertIn("[status not reported]", out)
        self.assertIn("   rendered: skipped (form status not reported)\n", out)
        self.assertIn("   vs Roster: skipped (form status not reported)\n", out)
        self.assertIn("→ CLEAN", out)

    def test_the_served_page_is_counted_for_the_retired_rosters_always_hidden(self):
        page = ('<li class="form-line always-hidden" data-type="control_checkbox" id="id_12">'
                '<input type="checkbox" class="form-checkbox validate[required]" id="input_12_0" value="x"></li>'
                '<li id="id_13" class="form-line form-field-hidden" data-type="control_checkbox"></li>'
                '<li class="form-line" id="id_10"></li>')
        self.assertEqual(form_status.rendered_retired(page, ["12", "13"]), {"retired": 2, "always_hidden": 1})
        self.assertEqual(form_status.rendered_retired(page, ["12"]), {"retired": 1, "always_hidden": 1})
        self.assertEqual(form_status.rendered_retired(page, ["14"]), {"retired": 0, "always_hidden": 0})
        self.assertEqual(form_status.rendered_retired("", ["12"]), {"retired": 0, "always_hidden": 0})

        def problems(page, retired):
            r = {"club_picker": None, "roster_qids": [], "retired_qids": retired, "id": self.AFRICA}
            found = form_status.rendered_problems(r, page)
            return [p for p in found if "retired rosters" in p], r.get("rendered_retired")
        found, counts = problems(page, ["12", "13"])
        self.assertEqual(counts, {"retired": 2, "always_hidden": 1})
        self.assertEqual(len(found), 1)
        self.assertIn("rendered page: 1 of the 2 retired rosters are served always-hidden (2 found)", found[0])
        self.assertIn("no mentor could send the form", found[0])
        self.assertEqual(problems(page, ["12"]), ([], {"retired": 1, "always_hidden": 1}))
        found, counts = problems(page, ["12", "14"])                      # one not served at all
        self.assertEqual((len(found), counts), (1, {"retired": 1, "always_hidden": 1}))
        self.assertEqual(problems(page, [])[1], None)                      # no retired roster: nothing counted
        # the printed line, on the retired form with its page
        qs, wire = self.form(retired=("12", "13"))
        served = ('<li class="form-line always-hidden" id="id_12"></li><li class="form-line always-hidden" id="id_13"></li>'
                  + served_rules_and_rosters(qs, wire))
        out, _ = self.printed(qs, wire, "--rendered", partners={"Partner Two": "no"}, page=served)
        self.assertIn("   rendered retired: 2 retired rosters, 2 always-hidden\n", out)
        self.assertNotIn("retired rosters are served always-hidden", out)


if __name__ == "__main__":
    unittest.main(verbosity=1)
