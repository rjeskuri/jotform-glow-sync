#!/usr/bin/env python3
"""
tools/form_status.py's audits: the rules (FormStatusAudit), the layout (FormStatusLayout), the
module values and the names dictionary (ModuleAndNamesAudit) and Jotform's usage limits
(JotformUsage). Fictional names.
"""
import copy
import json
import os
import sys
import unittest
from unittest import mock

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
                "beta club": {"partner two": "Partner Two"}}       # the Roster's, as roster_facts' holders give

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
                             terms=lambda c, old=old, new=new: c["terms"].replace(f'"{old}"', f'"{new}"'))
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

        shows_guard = lambda c: '"Show", "isError": false, "field": "700"' in c["action"]
        requires = lambda c: c["type"] == "require"
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
        drop = lambda c: json.dumps([t for t in json.loads(c["terms"]) if t["value"] != "Beta Club"])
        only(qs, self.edit(wire, lambda c: shows_guard(c) or requires(c), terms=drop),
             "misses 1 club(s) - their mentors cannot submit: ['Beta Club']", n=2)
        add = lambda c: json.dumps(json.loads(c["terms"]) + [{"field": "5", "operator": "notEquals",
                                                               "value": "Old Club"}])
        only(qs, self.edit(wire, requires, terms=add), "tests 1 value(s) that are not the picker's options")
        filled = lambda c: json.dumps([t for t in json.loads(c["terms"]) if t["operator"] != "isFilled"])
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

    COMPARED = ("62a8b57dd95", "fc726a121d4", "9e75d6f1d83", "7a7e75787df", "9083adfcdff", "2bdb1ec3fa8")
    NOTE = " (not compared with glow/translation_lookup.py yet: BACKLOG 64)"

    def test_the_build_line_names_a_build_not_yet_compared(self):
        for build in self.COMPARED:                                   # compared: the id alone
            self.assertEqual(form_status.build_line(build), build)
        for build in ("8705c008453", "bc6c80d556a", "18bdf84aedc",   # later builds, then made-up ones
                      "0123456789a", "deadbeef", "62a8b57dd96", "9e75d6f1d8"):
            self.assertEqual(form_status.build_line(build), build + self.NOTE, build)
        self.assertEqual(form_status.build_line(None), "not found on the public page")
        # the line follows the READ_BUILDS set, not a list kept in the tool
        from unittest import mock
        from glow import translation_lookup as tl
        for build in tl.READ_BUILDS:
            self.assertEqual(form_status.build_line(build), build)
        # ... read at call time from the module attribute: a patched set decides, in both directions
        with mock.patch.object(tl, "READ_BUILDS", frozenset({"0123456789a"})):
            self.assertEqual(form_status.build_line("0123456789a"), "0123456789a")
            self.assertEqual(form_status.build_line("62a8b57dd95"), "62a8b57dd95" + self.NOTE)
            self.assertEqual(form_status.build_line("9e75d6f1d83"), "9e75d6f1d83" + self.NOTE)
            self.assertEqual(form_status.build_line(None), "not found on the public page")
        with mock.patch.object(tl, "READ_BUILDS", frozenset()):
            self.assertEqual(form_status.build_line("9e75d6f1d83"), "9e75d6f1d83" + self.NOTE)
        self.assertEqual(form_status.build_line("62a8b57dd95"), "62a8b57dd95")      # restored

    def test_rendered_problems_sets_build_read_true_false_or_none(self):
        from unittest import mock
        from glow import translation_lookup as tl

        def page(build):
            return (f'<script src="https://cdn.jotfor.ms/s/static/{build}/static/jotform.forms.js"></script>'
                    if build else "<p>no runtime here</p>")

        def run(build):
            r = {"club_picker": None, "roster_qids": []}
            form_status.rendered_problems(r, page(build))
            return r

        for build in self.COMPARED:
            r = run(build)
            self.assertEqual((r["build"], r["build_read"]), (build, True), build)
        for build in ("8705c008453", "bc6c80d556a", "18bdf84aedc", "0123456789a"):
            r = run(build)
            self.assertEqual((r["build"], r["build_read"]), (build, False), build)
        r = run(None)
        self.assertIsNone(r["build"])
        self.assertIn("build_read", r)
        self.assertIsNone(r["build_read"])
        # follows the module's set at call time
        with mock.patch.object(tl, "READ_BUILDS", frozenset({"0123456789a"})):
            self.assertIs(run("0123456789a")["build_read"], True)
            self.assertIs(run("9e75d6f1d83")["build_read"], False)
            self.assertIsNone(run(None)["build_read"])

    def test_an_uncompared_build_is_named_and_the_form_stays_clean(self):
        import contextlib
        import io
        import re
        import tempfile
        from unittest import mock
        qs, wire = self.guard_form()
        for q_id, q in qs.items():
            q.setdefault("qid", q_id)

        class Fake:
            def get(self, path, **params):
                if path.endswith("/questions"):
                    return copy.deepcopy(qs)
                if path.endswith("/properties"):
                    return {"conditions": wire, "language": [{"options": "English (US)|Español"}],
                            "clearFieldOnHide": "disable"}
                if path == "/user/usage":
                    return {"uploads": "1340458410", "submissions": "474", "total_submissions": "690",
                            "monthly_usage_reset_date": "2026-10-21 00:00:00", "form_count": "5"}
                if path == "/user":
                    return {"account_type": "https://api.jotform.com/system/plan/SILVER"}
                if path == "/system/plan/SILVER":
                    return {"name": "SILVER", "limits": {"uploads": 10738466816, "submissions": 2500}}
                return {"title": "t", "status": "ENABLED", "count": "0"}

        select = ('<select name="q500_clubPicker[]" multiple="">'
                  + "".join(f'<option data-calcvalue="{o}" value="{o}">{o}</option>'
                            for o in ClubGuardFixture.OPTIONS) + "</select>\n<!--rest-->")

        shifted = select.replace('data-calcvalue="Beta Club"', 'data-calcvalue="Alpha Club"')

        def report(roster, *extra, strip_build=False, picker=select, **served_kw):
            rest = served_rules_and_rosters(qs, wire, **served_kw)
            if strip_build:                                   # a page whose runtime script is gone
                rest = re.sub(r'<script src="https://cdn\.jotfor\.ms/s/static/[^>]*></script>', "", rest)
            served = picker.replace("<!--rest-->", rest)
            out = io.StringIO()
            with mock.patch.object(form_status, "Client", lambda key: Fake()), \
                    mock.patch.object(form_status, "public_page", lambda fid: served), \
                    mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}), \
                    mock.patch.object(sys, "argv", ["form_status.py", "--form", glow_forms.TEMPLATE,
                                                    "--roster", roster, "--rendered", *extra]), \
                    contextlib.redirect_stdout(out):
                form_status.main()
            return out.getvalue()

        def build_lines(out):
            return [ln.strip() for ln in out.splitlines() if ln.strip().startswith("runtime build:")]

        with tempfile.TemporaryDirectory() as tmp:
            roster = os.path.join(tmp, "roster.csv")
            with open(roster, "w", encoding="utf-8") as f:
                f.write("partner,club,full_name,status,region\n")
                for (partner, club), names in ClubGuardFixture.ROSTER.items():
                    f.write(f"{partner},{club},{names[0]},active,Africa\n")
            # an uncompared build: the note, and the form stays CLEAN
            for build in ("8705c008453", "bc6c80d556a", "0123456789a"):
                out = report(roster, build=build)
                self.assertEqual(build_lines(out), [f"runtime build: {build}{self.NOTE}"], build)
                self.assertIn(f"runtime build: {build} (not compared", out)
                self.assertIn("→ CLEAN", out, build)
                (rep,) = json.loads(report(roster, "--json", build=build))
                self.assertIs(rep["build_read"], False, build)
                self.assertEqual(rep["build"], build)
                self.assertEqual(rep["rule_problems"], [])
            # the default build and other compared ones: the line is exactly the id, nothing after it
            out = report(roster)
            self.assertEqual(build_lines(out), ["runtime build: 9e75d6f1d83"])
            self.assertIn("→ CLEAN", out)
            (rep,) = json.loads(report(roster, "--json"))
            self.assertIs(rep["build_read"], True)
            for build in ("62a8b57dd95", "2bdb1ec3fa8"):
                self.assertEqual(build_lines(report(roster, build=build)), [f"runtime build: {build}"], build)
                (rep,) = json.loads(report(roster, "--json", build=build))
                self.assertIs(rep["build_read"], True, build)
            # a page with no build: the line says so, and build_read is None (not False)
            out = report(roster, strip_build=True)
            self.assertEqual(build_lines(out), ["runtime build: not found on the public page"])
            (rep,) = json.loads(report(roster, "--json", strip_build=True))
            self.assertIsNone(rep["build"])
            self.assertIn("build_read", rep)
            self.assertIsNone(rep["build_read"])
            # the report follows glow.translation_lookup.READ_BUILDS at call time
            from glow import translation_lookup as tl
            with mock.patch.object(tl, "READ_BUILDS", frozenset({"0123456789a"})):
                out = report(roster, build="0123456789a")
                self.assertEqual(build_lines(out), ["runtime build: 0123456789a"])
                self.assertIn("→ CLEAN", out)
                (rep,) = json.loads(report(roster, "--json", build="0123456789a"))
                self.assertIs(rep["build_read"], True)
                out = report(roster)                              # 9e75d6f1d83 is no longer compared
                self.assertEqual(build_lines(out), [f"runtime build: 9e75d6f1d83{self.NOTE}"])
                self.assertIn("→ CLEAN", out)
                (rep,) = json.loads(report(roster, "--json"))
                self.assertIs(rep["build_read"], False)
            # an uncompared build does not skip the audit: a real problem is still flagged
            for build in ("8705c008453", "9e75d6f1d83"):
                out = report(roster, picker=shifted, build=build)
                self.assertIn("would send another club's name", out, build)
                self.assertNotIn("→ CLEAN", out, build)
                self.assertEqual(len(build_lines(out)), 1, build)
            out = report(roster, picker=shifted, build="8705c008453")
            self.assertIn(f"runtime build: 8705c008453{self.NOTE}", out)
            self.assertIn("would send another club's name", out)
            self.assertNotIn("→ CLEAN", out)


class FormStatusRoster(unittest.TestCase):
    """tools/form_status.py --roster: required (the old default was the pre-launch offline
    build, BACKLOG 32), and an export with a byte-order mark reads like any other."""

    def test_without_roster_it_refuses_and_names_the_export(self):
        import contextlib
        import io
        from unittest import mock
        built = []
        env = {k: v for k, v in os.environ.items() if k != "JOTFORM_API_KEY"}
        with mock.patch.object(form_status, "Client", lambda key: built.append(key)), \
                mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(sys, "argv", ["form_status.py", "--form", glow_forms.TEMPLATE]), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as cm:
            form_status.main()
        self.assertIn("--roster is required", str(cm.exception.code))
        self.assertIn("python3 tools/sheets_client.py export Roster data/roster_<date>.csv",
                      str(cm.exception.code))
        self.assertEqual(built, [])                       # refused before the key or a read

    def test_a_roster_export_with_a_byte_order_mark_is_read(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "roster.csv")
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                f.write("partner,club,full_name,status,region\r\n"
                        "Partner One,Alpha Club,Ana Example,active,Africa\r\n")
            roster = form_status.load_roster(path)
        self.assertEqual(list(roster), ["Africa"])
        club, names, partner, _ = roster["Africa"]["alpha club"]
        self.assertEqual((club, partner, len(names)), ("Alpha Club", "Partner One", 1))

    # ---- regions read the way the sync reads them (ticket #7) ----

    @staticmethod
    def write_roster(folder, rows, name="roster.csv"):
        """A Roster export (partner, club, full_name, status, region) of fictional rows."""
        import csv
        path = os.path.join(folder, name)
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["partner", "club", "full_name", "status", "region"])
            w.writerows(rows)
        return path

    def test_each_club_is_under_the_region_whose_sync_takes_it(self):
        import tempfile
        from glow.text import key, name_key
        # one club per spelling, a different number of girls each, one region per club
        spellings = ["Africa", "africa", " AFRICA ", "Latin  America", "latin america", "u.s", "U.S", "Asia"]
        clubs = ["Alpha Club", "Beta Club", "Gamma Club", "Delta Club", "Epsilon Club", "Zeta Club",
                 "Eta Club", "Theta Club"]
        rows = []
        for i, (club, region) in enumerate(zip(clubs, spellings)):
            for g in range(i % 3 + 1):
                rows.append([f"Partner {'One' if i % 2 else 'Two'}", club, f"Girl{i}{g} Example", "active", region])
        rows.append(["Partner One", "Iota Club", "Ina Inactive", "inactive", "africa"])   # not active: no entry
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_roster(tmp, rows)
            roster = form_status.load_roster(path)
            self.assertEqual(set(roster), set(glow_forms.REGIONS))     # no 'africa', no 'Latin  America'
            for region in glow_forms.REGIONS:
                want, _, _ = glow_sync.read_roster_csv(path, region)   # the writer is the oracle
                self.assertEqual(set(roster[region]), {key(club) for (_, club) in want}, region)
                for (_, club), names in want.items():
                    self.assertEqual(roster[region][key(club)][1], {name_key(n) for n in names}, club)
        # the spread the table makes: 3 clubs on Africa, 2 on Latin America, 2 on U.S, 1 on Asia
        self.assertEqual({r: len(c) for r, c in roster.items()},
                         {"Africa": 3, "Latin America": 2, "U.S": 2, "Asia": 1})

    def test_a_club_whose_rows_spell_its_region_two_ways_is_one_entry(self):
        import tempfile
        from glow.text import name_key
        rows = [["Partner One", "Alpha Club", "Ana Example", "active", "africa "],   # lower case first
                ["Partner One", "Alpha Club", "Bea Sample", "active", "Africa"],
                ["Partner Two", "Beta Club", "Cora Test", "active", "Africa"],       # capitalized first
                ["Partner Two", "Beta Club", "Dina Mock", "active", " AFRICA"],
                ["Partner Two", "Beta Club", "Eva Dummy", "active", "africa"]]
        with tempfile.TemporaryDirectory() as tmp:
            roster = form_status.load_roster(self.write_roster(tmp, rows))
        self.assertEqual(list(roster), ["Africa"])
        self.assertEqual(set(roster["Africa"]), {"alpha club", "beta club"})
        club, names, partner, by_partner = roster["Africa"]["alpha club"]
        self.assertEqual((club, partner), ("Alpha Club", "Partner One"))
        self.assertEqual(names, {name_key("Ana Example"), name_key("Bea Sample")})
        self.assertEqual(by_partner, {"partner one": names})
        club, names, partner, by_partner = roster["Africa"]["beta club"]
        self.assertEqual(names, {name_key(n) for n in ("Cora Test", "Dina Mock", "Eva Dummy")})
        self.assertEqual(by_partner, {"partner two": names})

    # rows with regions no form has: '(no region)' 1 club / 1 girl, 'Afrika' 2 clubs / 4 girls,
    # 'U.S.' 1 club / 2 girls; Africa (spelled 'africa') and Asia are forms' regions
    NO_FORM_ROWS = [
        ["Partner One", "Alpha Club", "Ana Example", "active", "U.S."],
        ["Partner One", "Alpha Club", "Bea Sample", "active", "  U.S. "],
        ["Partner Two", "Beta Club", "Cora Test", "active", "Afrika"],
        ["Partner Two", "Gamma Club", "Dina Mock", "active", " Afrika"],
        ["Partner Two", "Gamma Club", "Eva Dummy", "active", "Afrika"],
        ["Partner Two", "Gamma Club", "Fay Fiction", "active", "Afrika  "],
        ["Partner Three", "Delta Club", "Gia Pretend", "active", ""],
        ["Partner One", "Epsilon Club", "Hana Invent", "active", "africa"],
        ["Partner One", "Zeta Club", "Ida Imagine", "active", "Asia"],
        ["Partner One", "Zeta Club", "Jo Madeup", "active", "Asia"],
        ["Partner Three", "Eta Club", "Kim Unreal", "inactive", "Narnia"],     # not active: not counted
    ]

    def test_a_region_no_form_has_is_kept_as_typed_and_counted(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            roster = form_status.load_roster(self.write_roster(tmp, self.NO_FORM_ROWS))
            self.assertEqual(set(roster), {"Africa", "Asia", "U.S.", "Afrika", "(no region)"})
            self.assertEqual(set(roster["U.S."]), {"alpha club"})
            self.assertEqual(set(roster["Afrika"]), {"beta club", "gamma club"})
            self.assertEqual(set(roster["(no region)"]), {"delta club"})
            self.assertEqual(form_status.regions_without_form(roster),
                             [("(no region)", 1, 1), ("Afrika", 2, 4), ("U.S.", 1, 2)])
            # only blank regions: one entry, its own counts
            blank = form_status.load_roster(self.write_roster(tmp, [
                ["Partner One", "Alpha Club", "Ana Example", "active", ""],
                ["Partner One", "Alpha Club", "Bea Sample", "active", "  "],
                ["Partner Two", "Beta Club", "Cora Test", "active", ""],
                ["Partner Two", "Gamma Club", "Dina Mock", "active", ""],
                ["Partner Two", "Gamma Club", "Eva Dummy", "active", ""]], "blank.csv"))
            self.assertEqual(form_status.regions_without_form(blank), [("(no region)", 3, 5)])
            # every region a form's, however spelled: nothing listed, never a canonical region
            clean = form_status.load_roster(self.write_roster(tmp, [
                ["Partner One", "Alpha Club", "Ana Example", "active", " latin  AMERICA "],
                ["Partner One", "Beta Club", "Bea Sample", "active", "u.s"],
                ["Partner Two", "Gamma Club", "Cora Test", "active", "ASIA"],
                ["Partner Two", "Delta Club", "Dina Mock", "active", "Africa"]], "clean.csv"))
            self.assertEqual(form_status.regions_without_form(clean), [])
        # a by_region built by hand: canonical regions are skipped, every other key counted
        made = {"Africa": {"a": ("A", {"x", "y"}, "P", {})},
                "Latin America": {"b": ("B", {"x"}, "P", {})},
                "Oceania": {"c": ("C", {"x", "y", "z"}, "P", {}), "d": ("D", {"w"}, "P", {})},
                "Europe": {"e": ("E", set(), "P", {})}}
        self.assertEqual(form_status.regions_without_form(made), [("Europe", 1, 0), ("Oceania", 2, 4)])

    def test_the_report_names_such_regions_in_counts_never_a_name(self):
        import contextlib
        import io
        import tempfile
        from unittest import mock

        def report(path, *extra):
            out = io.StringIO()
            with mock.patch.object(form_status, "Client", lambda key: object()), \
                    mock.patch.object(form_status, "read_storage", lambda client: {}), \
                    mock.patch.object(form_status, "storage_status_line", lambda store: "storage: test"), \
                    mock.patch.dict(form_status.FORMS, {}, clear=True), \
                    mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}), \
                    mock.patch.object(sys, "argv", ["form_status.py", "--roster", path, *extra]), \
                    contextlib.redirect_stdout(out):
                form_status.main()
            return out.getvalue()

        with tempfile.TemporaryDirectory() as tmp:
            bad = self.write_roster(tmp, self.NO_FORM_ROWS)
            out = report(bad)
            lines = out.splitlines()
            at = next(i for i, line in enumerate(lines) if line.startswith("Roster (active girls):"))
            self.assertEqual(lines[at + 1],
                             "! Roster: 7 active girl(s) in 4 club(s) carry a region no form has - they reach "
                             "NO attendance form: '(no region)' 1 club(s), 'Afrika' 2 club(s), "
                             "'U.S.' 1 club(s); fix the Partners tab, then GLOW -> Refresh regions from the "
                             "Partners tab")
            self.assertEqual(sum(1 for line in lines if line.startswith("! Roster:")), 1)
            for _, club, girl, _, _ in self.NO_FORM_ROWS:            # counts and regions, never a name
                self.assertNotIn(club, out)
                self.assertNotIn(girl, out)
            # --json keeps its shape: the JSON alone, no Roster line
            self.assertEqual(json.loads(report(bad, "--json")), [])

            # a different spread: the counts follow the export
            other = self.write_roster(tmp, [
                ["Partner One", "Alpha Club", "Ana Example", "active", "Oceania"],
                ["Partner One", "Alpha Club", "Bea Sample", "active", "Oceania "],
                ["Partner One", "Beta Club", "Cora Test", "active", " Oceania"],
                ["Partner Two", "Gamma Club", "Dina Mock", "active", "Asia"]], "other.csv")
            lines = report(other).splitlines()
            self.assertIn("! Roster: 3 active girl(s) in 2 club(s) carry a region no form has - they reach "
                          "NO attendance form: 'Oceania' 2 club(s); fix the Partners "
                          "tab, then GLOW -> Refresh regions from the Partners tab", lines)

            # every region a form's, however spelled: no ! Roster: line
            clean = self.write_roster(tmp, [
                ["Partner One", "Alpha Club", "Ana Example", "active", "africa"],
                ["Partner One", "Beta Club", "Bea Sample", "active", " Latin  America"],
                ["Partner Two", "Gamma Club", "Cora Test", "active", "u.s"],
                ["Partner Two", "Delta Club", "Dina Mock", "active", "ASIA"]], "clean.csv")
            out = report(clean)
            self.assertIn("Roster (active girls):", out)
            self.assertNotIn("! Roster", out)
            self.assertNotIn("'africa'", out)                     # under its form's region


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


# Written when Welcome Session was the only special event: pinned to that world, so the module
# audit it tests does not move with the live type list. The two-type state is
# test/special_events_test.py (IdgAudit).
@mock.patch.object(glow_sync, "SPECIAL_EVENTS", ("Welcome Session",))
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
        # each dropdown carries its curriculum options and the special event (glow.sync.SPECIAL_EVENTS)
        self.assertEqual(summary, {"14": {"options": 2, "aligned": True}, "92": {"options": 3, "aligned": True},
                                   "93": {"options": 2, "aligned": True}})
        bare = copy.deepcopy(qs)
        for q in sync.MODULES.values():
            bare[q]["calcValues"] = ""
        shifted = copy.deepcopy(qs)
        shifted["92"]["calcValues"] = "|Elective - Healthy GLOW|Core 2|Special Event - Welcome Session"
        problems = form_status.audit_module_values(bare)[0]
        self.assertEqual(len(problems), 3)
        self.assertIn("module dropdown q14 (year 1): no calcValues - question 98 (module_id, what Salesforce "
                      "stores) copies the visible text", problems[0])
        (problem,) = form_status.audit_module_values(shifted)[0]
        self.assertIn("q92 (year 2): calcValues out of line with its 3 options (4 values) - question 98 would "
                      "send another module", problem)
        gone = copy.deepcopy(qs)
        del gone["93"]
        self.assertEqual(form_status.audit_module_values(gone)[0], ["module dropdown q93 (year 3) is not on the form"])
        with mock.patch.object(glow_sync, "MODULE_CALC_VALUES", False):
            self.assertEqual((form_status.audit_module_values(bare)[0], form_status.audit_module_values(qs)[0]),
                             ([], []))
            # who clears them depends on the form kind (FixHintsByFormKind): the audit alone
            # does not know it, so only the part both kinds share is pinned here
            (problem,) = form_status.audit_module_values(shifted)[0]
            self.assertIn(" clears them (glow/sync.py MODULE_CALC_VALUES is off)", problem)
        self.assertEqual(form_status.module_values_line(summary),
                         "q14 aligned (2 options), q92 aligned (3 options), q93 aligned (2 options)")

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
        self.assertEqual(rep["module_values"]["14"], {"options": 2, "aligned": True})
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
        self.assertEqual(r["rendered_modules"]["92"], {"options": 3, "aligned": 3, "differ": 0, "missing": 0})
        self.assertEqual(r["rendered_names"], {"checked": True, "options": 8, "altered": 0, "languages": 2,
                                               "by_language": {}})
        bare = copy.deepcopy(qs)
        for q in sync.MODULES.values():
            bare[q]["calcValues"] = ""
        problems, _ = rendered(served_modules_and_store(bare))
        self.assertEqual(len(problems), 3)
        self.assertIn("rendered page: module dropdown q14: 2 of 2 options carry no data-calcvalue", problems[0])
        with mock.patch.object(glow_sync, "MODULE_CALC_VALUES", False):
            self.assertEqual(rendered(served_modules_and_store(bare), bare)[0], [])
        more = copy.deepcopy(qs)
        more["92"]["options"] += "|Elective - STEM"
        more["92"]["calcValues"] += "|Elective - STEM"
        (problem,), _ = rendered(served_modules_and_store(qs), more)
        self.assertIn("rendered page lists 3 of module dropdown q92's 4 options", problem)
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
        self.assertEqual(summary["14"]["options"], 2)

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


# ---- ticket #33: each fix hint names who repairs the drift, by form kind

RUNNER = "the runner's next run (or the sync's apply by hand now)"     # an enabled regional form
HAND = "a sync apply by hand"                                           # the template, a disabled form
# (form id, Jotform status, label): the kinds a report can be for
REGIONAL_KINDS = tuple((fid, "ENABLED", f"{region} enabled") for region, fid in glow_forms.REGIONALS.items())
HAND_KINDS = ((glow_forms.TEMPLATE, "ENABLED", "template"),
              (glow_forms.TEMPLATE, "DISABLED", "template, status disabled"),
              # a regional form whose status is anything but ENABLED is not the runner's: disabled,
              # deleted, or a status Jotform did not report (None)
              *((fid, status, f"{region} {status or 'no status'}")
                for region, fid in glow_forms.REGIONALS.items() for status in ("DISABLED", "DELETED", None)),
              # an enabled form that is none of the four regionals: a retired (defunct) form, an unknown id
              *((fid, "ENABLED", f"defunct {fid} enabled") for fid in form_status.DEFUNCT),
              ("999", "ENABLED", "unknown id enabled"))
# --rendered reads enabled forms only and takes the kind from r["id"]: the four regionals, then the
# ids that get the hand wording (the template, a retired form, an unknown id, no id at all)
RENDERED_REGIONAL = tuple(glow_forms.REGIONALS.values())
RENDERED_HAND = (glow_forms.TEMPLATE, *form_status.DEFUNCT, "999", None)


def rendered_r(form_id, **rest):
    """The report dict --rendered is handed for `form_id` (None: a dict with no id)."""
    return dict(rest, **({} if form_id is None else {"id": form_id}))


def hint_report(qs, wire, form_id, status):
    """form_report for `form_id` as Jotform reports `status`, over a fake form with these
    questions and rules (nothing else in the form is under test)."""
    qs = copy.deepcopy(qs)
    for q_id, q in qs.items():
        q.setdefault("qid", q_id)

    class Fake:
        def get(self, path, **params):
            if path.endswith("/questions"):
                return copy.deepcopy(qs)
            if path.endswith("/properties"):
                return {"conditions": wire, "clearFieldOnHide": "disable",
                        "language": [{"options": "English (US)|Español", "primaryLanguage": "en"}]}
            if path.endswith("/translations"):
                return served_store(qs)
            return {"title": "t", "count": "0", **({} if status is None else {"status": status})}
    return form_status.form_report(form_id, Fake(), {})


def built_with(first=True, operand=True, required=True):
    """The guard form as the sync generates it with question 18's three constants so set."""
    import contextlib
    with contextlib.ExitStack() as stack:
        for name, value in (("CONTACT_IDS_FIRST", first), ("CONTACT_IDS_PICKER_OPERAND", operand),
                            ("ROSTERS_REQUIRED", required)):
            stack.enter_context(mock.patch.object(glow_sync, name, value))
        return ClubGuardFixture.form(ClubGuardFixture())


class FixHintsByFormKind(unittest.TestCase):
    """The fix hints of form_status's problems name who repairs the drift: on an enabled regional
    form the runner's next run (or the sync's apply by hand now), on the template and on a disabled
    form (the runner syncs neither) a sync apply by hand. Read through form_report, for every kind
    of form and for each hint's own drift; docs/DECISIONS.md, 2026-10-14."""

    def check_kinds(self, qs, wire, fragment, tail, count=1):
        """For every form kind, the `count` problems containing `fragment` carry RUNNER + tail on
        an enabled regional form, HAND + tail on any other, and never the other kind's words."""
        for form_id, status, label in REGIONAL_KINDS + HAND_KINDS:
            with self.subTest(label):
                problems = hint_report(qs, wire, form_id, status)["rule_problems"]
                found = [p for p in problems if fragment in p]
                self.assertEqual(len(found), count, (fragment, problems))
                for p in found:
                    if (form_id, status, label) in REGIONAL_KINDS:
                        self.assertIn(RUNNER + tail, p)
                        self.assertNotIn(HAND, p)
                    else:
                        self.assertIn(HAND + tail, p)
                        self.assertNotIn("runner", p.lower())
                        self.assertNotIn("sync's apply", p)

    def test_the_module_values_hint_when_calcvalues_are_missing(self):
        qs, wire = SameNameFixture.form(SameNameFixture(), switched=True)
        qs = copy.deepcopy(qs)
        for q in glow_sync.MODULES.values():
            qs[q]["calcValues"] = ""
        # the three module dropdowns, one problem each: question 98 copies the visible text
        self.check_kinds(qs, wire, "no calcValues - question 98 (module_id", " writes them", count=3)

    def test_the_module_values_hint_when_calcvalues_are_out_of_line(self):
        qs, wire = SameNameFixture.form(SameNameFixture(), switched=True)
        qs = copy.deepcopy(qs)
        qs["92"]["calcValues"] = "|Elective - Healthy GLOW|Core 2|Special Event - Welcome Session"
        self.check_kinds(qs, wire, "q92 (year 2): calcValues out of line", " writes them")

    def test_the_module_values_hint_when_the_constant_is_off(self):
        qs, wire = SameNameFixture.form(SameNameFixture(), switched=True)
        qs = copy.deepcopy(qs)
        qs["92"]["calcValues"] = "|Elective - Healthy GLOW|Core 2|Special Event - Welcome Session"
        with mock.patch.object(glow_sync, "MODULE_CALC_VALUES", False):
            self.check_kinds(qs, wire, "calcValues out of line", " clears them (glow/sync.py MODULE_CALC_VALUES is off)")

    def test_the_required_flag_hints(self):
        # ROSTERS_REQUIRED on, the rosters built without the flag
        qs, wire = built_with(required=False)
        self.check_kinds(qs, wire, "roster(s) not required", " sets the flag")
        # ROSTERS_REQUIRED off (the generated rollback), the rosters still required
        qs, wire = built_with(required=True)
        with mock.patch.object(glow_sync, "ROSTERS_REQUIRED", False):
            self.check_kinds(qs, wire, "although glow/sync.py ROSTERS_REQUIRED is off", " clears the flag")

    def test_the_question_18_hints(self):
        # Contact_IDs calculated after the rosters (CONTACT_IDS_FIRST on, the form built with it off)
        qs, wire = built_with(first=False)
        self.check_kinds(qs, wire, "is calculated by rule", " puts it first")
        # the Club picker an operand of question 18 (on, the form built without it)
        qs, wire = built_with(operand=False)
        self.check_kinds(qs, wire, "is not one of question 18's operands", " adds it")

    def test_a_clean_form_says_nothing_of_either(self):
        qs, wire = built_with()
        for form_id, status, label in REGIONAL_KINDS + HAND_KINDS:
            problems = hint_report(qs, wire, form_id, status)["rule_problems"]
            self.assertEqual([p for p in problems if RUNNER in p or HAND in p], [], label)

    def test_the_builder_only_hint_is_left_alone(self):
        # a problem only a builder edit repairs never offers a sync apply (SHAPE_FIX), on any kind
        qs, wire = SameNameFixture.form(SameNameFixture(), switched=True)
        qs = copy.deepcopy(qs)
        qs["93"]["multipleSelections"] = "Yes"
        for form_id, status, label in REGIONAL_KINDS + HAND_KINDS:
            found = [p for p in hint_report(qs, wire, form_id, status)["rule_problems"]
                     if "module dropdown q93 (year 3) is a multi-select" in p]
            self.assertEqual(len(found), 1, label)
            self.assertIn("never a sync apply", found[0])
            self.assertNotIn("runner", found[0].lower())

    def test_the_served_page_hint_names_the_runner_on_a_regional_form_only(self):
        # --rendered reads enabled forms only and tells the kind by r["id"]: only the four regionals
        # are the runner's; the template, a retired form, an unknown id and no id get the hand wording
        qs, _ = SameNameFixture.form(SameNameFixture(), switched=True)
        bare = copy.deepcopy(qs)
        for q in glow_sync.MODULES.values():
            bare[q]["calcValues"] = ""
        summary = form_status.audit_module_values(qs)[1]
        page = served_modules_and_store(bare)
        for form_id in RENDERED_REGIONAL + RENDERED_HAND:
            with self.subTest(form_id=form_id):
                problems = form_status.rendered_module_problems(rendered_r(form_id, module_values=summary), page)
                self.assertEqual(len(problems), 3)
                for p in problems:
                    self.assertIn("carry no data-calcvalue", p)
                    if form_id in RENDERED_REGIONAL:
                        self.assertIn(RUNNER + " writes them", p)
                        self.assertNotIn(HAND, p)
                    else:
                        self.assertIn(HAND + " writes them", p)
                        self.assertNotIn("runner", p.lower())


if __name__ == "__main__":
    unittest.main(verbosity=1)
