#!/usr/bin/env python3
"""
tools/form_status.py's audits: the rules (FormStatusAudit), the layout (FormStatusLayout), the
module values and the names dictionary (ModuleAndNamesAudit) and Jotform's usage limits
(JotformUsage); and what tools/add_translations.py counts as a string a mentor sees
(TranslationAudit). Fictional names.
"""
import copy
import json
import os
import sys
import unittest

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import (ClubGuardFixture, FormStatusFixture, SameNameFixture, link_form,
                            move_all, served_modules_and_store, served_rules_and_rosters,
                            served_store)
import auto_sync
import form_status
import sync_attendance_form as sync
from glow import forms as glow_forms
from glow import layout
from glow import sync as glow_sync
from glow import usage
from glow.text import md5


class FormStatusAudit(FormStatusFixture, unittest.TestCase):
    """tools/form_status.py audit_rules on forms built by the sync's own rules."""

    PARTNERS = {"stars": {"partner one": "Partner One", "partner two": "Partner Two"},
                "alpha club": {"partner one": "Partner One"},
                "beta club": {"partner two": "Partner Two"}}       # the Roster's, as load_partners gives

    def form(self, **kw):
        return SameNameFixture.form(SameNameFixture(), **kw)

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

    SUMMARY = {"clubs": 4, "show_rules": 4, "live_rosters": 4, "aggregate_rosters": 4, "long_names": 2,
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
        return ClubGuardFixture.form(ClubGuardFixture(), **kw)

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
            qs["500"]["calcValues"] = ClubGuardFixture.CALC.replace("|Alpha Club|Beta Club", "|Beta Club|Alpha Club")
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
                            for o in ClubGuardFixture.OPTIONS) + "</select>")
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
                for (partner, club), names in ClubGuardFixture.ROSTER.items():
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
        qs, wire = SameNameFixture.form(SameNameFixture(), switched=True)
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
        qs, _ = SameNameFixture.form(SameNameFixture(), partner_list="Partner One|Partner Two")
        strings = add_translations.visible_strings(qs)
        # the list's label is (already translated everywhere); its options stay English,
        # so adding the list does not grow the audit's "untranslated" count
        self.assertEqual(strings["Partner"], {"q331.text", "q600.text"})
        self.assertNotIn("Partner One", strings)
        self.assertNotIn("Partner Two", strings)
        # other dropdowns' options are still counted (the module names are translated)
        self.assertEqual(strings["Core 1"], {f"q{sync.MODULES['1']}.option"})


class ModuleAndNamesAudit(unittest.TestCase):
    """tools/form_status.py: the module dropdowns' calcValues (as MODULE_CALC_VALUES says)
    and the form's names dictionary (emulated), through the API and on the served page;
    the runner's verify step reads both. Fictional names; counts and club names only."""

    def form(self):
        return SameNameFixture.form(SameNameFixture(), switched=True)

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


if __name__ == "__main__":
    unittest.main(verbosity=1)
