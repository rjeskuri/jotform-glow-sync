#!/usr/bin/env python3
"""
Special events (docs/plans/2026-10-13-special-events.md): "Special Event - <type>" as one more
option of every module dropdown, with no session dropdown and question 100 blank - the constants
(glow/sync.py), the cascade and the session bridge (build_conditions), the sync's one write per
module dropdown, the runner holding that write, form_status's audits (API and served page).
glow/submissions.py's reading of an event: test/backfill_resolve_test.py. On SameNameFixture's
fake Africa form; fictional names.
"""
import copy
import json
import os
import re
import unittest
from unittest import mock

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import (REPO, AutoSyncFixture, FakeForm, SameNameFixture, module_lists, read,
                            served_rules_and_rosters, served_store)
import auto_sync
import form_status
import sync_attendance_form as sync
from glow import forms as glow_forms
from glow import sync as glow_sync

EVENT = "Special Event - Welcome Session"
WEEK_COPIES = 4                                  # one calculation per session dropdown into question 100


def parsed(conds):
    """[(rule, terms, actions)] of generated or wire rules."""
    return [(c, *glow_sync.rule_parts(c)) for c in conds]


def session_rules(conds):
    """[(module dropdown, the module it tests, year, the session dropdown it shows)] in order."""
    out = []
    for _, terms, actions in parsed(conds):
        shows = [a["field"] for a in actions if a.get("visibility") == "Show" and a["field"] in sync.WEEKS.values()]
        if shows:
            mod = [t for t in terms if t["field"] in sync.MODULES.values()]
            year = [t["value"] for t in terms if t["field"] == sync.YEAR]
            out.append((mod[0]["field"] if mod else None, mod[0]["value"] if mod else None,
                        year[0] if year else None, shows[0]))
    return out


def before_rollout(qs, wire):
    """The form as it is live before this change: module dropdowns without the event (their
    calcValues aligned to the curriculum options), no session bridge, and the year-1 session
    dropdown shown on the year alone."""
    qs = copy.deepcopy(qs)
    for mq in sync.MODULES.values():
        options = [o for o in glow_sync.dropdown_options(qs[mq]) if o != EVENT]
        qs[mq].update(options="|".join(options), calcValues=glow_sync.module_calc_values(options))
    old = []
    for c, terms, actions in parsed(wire):
        if any(a.get("resultField") == sync.WEEK_ID and a.get("equation") == glow_sync.week_bridge_equation()
               for a in actions):
            continue
        if any(t["field"] == sync.MODULES["1"] for t in terms) and \
                any(a.get("visibility") == "Show" and a["field"] in sync.WEEKS.values() for a in actions):
            continue
        old.append(c)
        if any(a.get("visibility") == "Show" and a["field"] == sync.MODULES["3"] for a in actions):
            old.append(dict(c, id="1757999999999", link="Any",
                            terms=json.dumps([sync.mk_term(sync.YEAR, "equals", "1")]),
                            action=json.dumps([sync.mk_show(sync.WEEKS[8])])))
    return qs, old


class Constants(unittest.TestCase):
    def test_the_type_list_and_the_prefix(self):
        self.assertEqual((glow_sync.SPECIAL_EVENT_PREFIX, glow_sync.SPECIAL_EVENTS),
                         ("Special Event - ", ("Welcome Session",)))
        self.assertEqual(glow_sync.special_event_options(), [EVENT])
        for option in (EVENT, "special event -  Welcome Session", "Special Event - Retired Type"):
            self.assertTrue(glow_sync.is_special_event(option), option)
        for option in ("Elective - Healthy GLOW", "Relationships 101", "", None, "Event - Welcome Session"):
            self.assertFalse(glow_sync.is_special_event(option), option)

    def test_the_plan_of_a_dropdown(self):
        plan = glow_sync.special_event_plan
        self.assertEqual(plan(["Core 1"]), {"add": [EVENT], "unknown": [], "respelled": []})
        self.assertEqual(plan(["Core 1", EVENT]), {"add": [], "unknown": [], "respelled": []})
        self.assertEqual(plan([EVENT, "Core 1"])["add"], [])                       # anywhere: never reordered
        self.assertEqual(plan(["Core 1", "special event - welcome  session"]),
                         {"add": [], "unknown": [], "respelled": [("special event - welcome  session", EVENT)]})
        self.assertEqual(plan(["Core 1", "Special Event - Old Fair"]),
                         {"add": [EVENT], "unknown": ["Special Event - Old Fair"], "respelled": []})
        with mock.patch.object(glow_sync, "SPECIAL_EVENTS", ("Welcome Session", "Closing Ceremony")):
            self.assertEqual(plan(["Core 1", "Special Event - Closing Ceremony"])["add"], [EVENT])
            self.assertEqual(plan(["Core 1"])["add"], [EVENT, "Special Event - Closing Ceremony"])


class Cascade(unittest.TestCase):
    """build_conditions section B and the session bridge."""

    CLUBS = {"10": "Alpha Club", "11": "Beta Club"}
    MODULES = {"1": ["Core 1", "Core 1b", EVENT], "2": ["Core 2", "Elective - Healthy GLOW", EVENT],
               "3": ["Elective - Girl Boss Pro", EVENT, "Special Event - Old Fair"]}

    def build(self, picker=None):
        return sync.build_conditions(self.CLUBS, {}, self.MODULES, picker=picker,
                                     picker_options=list(self.CLUBS.values()) if picker else None)

    def test_one_rule_per_curriculum_module_of_every_year_and_none_for_an_event(self):
        self.assertEqual(session_rules(self.build()), [
            ("14", "Core 1", "1", "15"), ("14", "Core 1b", "1", "15"),
            ("92", "Core 2", "2", "15"), ("92", "Elective - Healthy GLOW", "2", "96"),
            ("93", "Elective - Girl Boss Pro", "3", "97")])
        for c, terms, _ in parsed(self.build()):
            if session_rules([c]):
                self.assertEqual(c["link"], "All")
                self.assertEqual([t["operator"] for t in terms], ["equals", "equals"])

    def test_the_bridge_heads_the_cascade_before_every_session_rule_and_copy(self):
        for picker in (None, "500"):
            with self.subTest(picker=picker):
                conds = self.build(picker)
                shape = glow_sync.week_bridge_layout(conds)
                self.assertEqual((len(shape["bridge"]), len(shape["copies"]), shape["event_rules"]),
                                 (1, WEEK_COPIES, []))
                pos = shape["position"]
                self.assertTrue(all(p > pos for p in shape["session_rules"] + shape["copies"]))
                # after section A (and question 18's rule 0 on a picker form), first of section B
                rule, terms, (action,) = parsed(conds)[pos]
                self.assertEqual(pos, (1 if picker else 0) + len(self.CLUBS))
                self.assertEqual((rule["type"], rule["link"]), ("calculation", "Any"))
                self.assertEqual([(t["field"], t["operator"]) for t in terms],
                                 [(f, "isFilled") for f in ("94", "14", "92", "93", "15", "95", "96", "97")])
                self.assertEqual((action["resultField"], action["equation"], action["operands"]),
                                 ("100", "{15}{95}{96}{97}", "94,14,92,93,15,95,96,97"))
                self.assertTrue(action["ignoreHiddenFields"])
                self.assertEqual(shape["terms"], {f: "isFilled" for f in glow_sync.WEEK_BRIDGE_FIELDS})
                # ids follow the order (minted in place), indexes are sequential
                ids = [int(c["id"]) for c in conds]
                self.assertEqual(ids, sorted(ids))
                self.assertEqual([c["index"] for c in conds], [str(i) for i in range(len(conds))])
                # the four copies are kept as they were
                copies = [parsed(conds)[p] for p in shape["copies"]]
                self.assertEqual([(t[0]["field"], a[0]["equation"]) for _, t, a in copies],
                                 [(w, "{%s}" % w) for w in sync.WEEKS.values()])

    def test_the_layout_reads_the_old_shape(self):
        qs, wire = SameNameFixture.form(SameNameFixture(), switched=True)
        _, old = before_rollout(qs, wire)
        shape = glow_sync.week_bridge_layout(old)
        self.assertEqual((shape["position"], shape["bridge"], len(shape["event_rules"])), (None, [], 1))
        rule = parsed(old)[shape["event_rules"][0]]
        self.assertEqual([t["field"] for t in rule[1]], [sync.YEAR])                # the year-1 rule
        # an event's own session rule is one too, and an unparseable rule is skipped
        bad = [{"id": "1", "terms": "not json", "action": "[]"},
               {"id": "2", "type": "field", "link": "All",
                "terms": json.dumps([sync.mk_term("14", "equals", EVENT), sync.mk_term("94", "equals", "1")]),
                "action": json.dumps([sync.mk_show("15")])}]
        self.assertEqual(glow_sync.week_bridge_layout(bad)["event_rules"], [1])


class EventSync(unittest.TestCase):
    """sync_attendance_form.main on SameNameFixture's form: the event options and the
    module calcValues in one write per dropdown, the rules from the options after it."""

    ROSTER, QIDS, MODULES, texts = SameNameFixture.ROSTER, SameNameFixture.QIDS, SameNameFixture.MODULES, SameNameFixture.texts
    LINES = ["UPDATE module dropdown (q14, year 1: 1 event option(s) added (Special Event - Welcome Session); "
             "calcValues = its 2 options)",
             "UPDATE module dropdown (q92, year 2: 1 event option(s) added (Special Event - Welcome Session); "
             "calcValues = its 3 options)",
             "UPDATE module dropdown (q93, year 3: 1 event option(s) added (Special Event - Welcome Session); "
             "calcValues = its 2 options)"]

    def setUp(self):
        SameNameFixture.setUp(self)

    def tearDown(self):
        SameNameFixture.tearDown(self)

    def run_sync(self, fake, *extra):
        return SameNameFixture.run_sync(self, fake, *extra)

    def summary(self, fake, *extra):
        return SameNameFixture.summary(self, fake, *extra)

    def in_step(self):
        return SameNameFixture.form(self, switched=True)

    def test_a_form_without_them_gets_one_write_per_dropdown_and_the_whole_result_in_the_dry_run(self):
        qs, wire = before_rollout(*self.in_step())
        fake = FakeForm(qs, wire)
        summary, out = self.summary(fake)
        self.assertEqual(fake.calls[:3], self.LINES)
        self.assertEqual(len(fake.calls), 4)
        self.assertRegex(fake.calls[3], r"^REPLACE conditions \(\d+ rules\)$")
        self.assertEqual([w[1:] for w in fake.writes[:3]], [
            ("/question/14", {"question[options]": f"Core 1|{EVENT}", "question[calcValues]": f"|Core 1|{EVENT}"}),
            ("/question/92", {"question[options]": f"Core 2|Elective - Healthy GLOW|{EVENT}",
                              "question[calcValues]": f"|Core 2|Elective - Healthy GLOW|{EVENT}"}),
            ("/question/93", {"question[options]": f"Core 3|{EVENT}", "question[calcValues]": f"|Core 3|{EVENT}"})])
        # the rules written are the in-step form's: the event shows no session, the bridge heads B
        written = fake.writes[3][2]["properties"]["conditions"]
        self.assertTrue(sync.same_conditions(written, self.in_step()[1]))
        shape = glow_sync.week_bridge_layout(written)
        self.assertEqual((len(shape["bridge"]), shape["event_rules"]), (1, []))
        self.assertNotIn(EVENT, [m for _, m, _, _ in session_rules(written)])
        self.assertIn("conditions: ", out)
        self.assertEqual(summary["module_values"],
                         [{"qid": "14", "year": "1", "modules": 2, "events": [EVENT]},
                          {"qid": "92", "year": "2", "modules": 3, "events": [EVENT]},
                          {"qid": "93", "year": "3", "modules": 2, "events": [EVENT]}])
        # the runner reads the same plan from the printed lines and from the summary, and holds it
        want = [{"qid": q, "year": y, "modules": n, "events": 1} for q, y, n in (("14", "1", 2), ("92", "2", 3),
                                                                                   ("93", "3", 2))]
        self.assertEqual((auto_sync.parse_plan(out)["modules"], auto_sync.plan_from_summary(summary)["modules"]),
                         (want, want))
        # applied, the form is in step: nothing more
        self.assertEqual(self.run_sync(FakeForm(qs, wire, apply=True), "--apply")[0], 0)
        fake = FakeForm(*self.in_step())
        self.assertEqual((self.run_sync(fake)[0], fake.calls), (0, []))

    def test_options_are_never_removed_renamed_or_reordered(self):
        qs, wire = self.in_step()
        # an event moved up by hand stays where it is; nothing to write
        qs["92"]["options"] = f"{EVENT}|Core 2|Elective - Healthy GLOW"
        qs["92"]["calcValues"] = glow_sync.module_calc_values(qs["92"]["options"].split("|"))
        fake = FakeForm(qs, wire)
        self.run_sync(fake)
        self.assertFalse([c for c in fake.calls if c.startswith("UPDATE module dropdown")])
        # a retired type is warned about and kept; the event it lacks is appended after it
        qs, wire = before_rollout(*self.in_step())
        qs["14"]["options"] += "|Special Event - Old Fair"
        fake = FakeForm(qs, wire)
        code, out = self.run_sync(fake)
        self.assertIn("  ! module dropdown q14 (year 1) lists 'Special Event - Old Fair', which is no special "
                      "event of glow/sync.py SPECIAL_EVENTS: left as it is", out)
        self.assertEqual(fake.writes[0][2]["question[options]"], f"Core 1|Special Event - Old Fair|{EVENT}")
        self.assertNotIn("Special Event - Old Fair", [m for _, m, _, _ in session_rules(
            fake.writes[-1][2]["properties"]["conditions"])])
        # one in another spelling counts as present: warned, never added twice
        qs, wire = self.in_step()
        qs["93"]["options"] = qs["93"]["options"].replace(EVENT, EVENT.upper())
        qs["93"]["calcValues"] = glow_sync.module_calc_values(qs["93"]["options"].split("|"))
        fake = FakeForm(qs, wire)
        code, out = self.run_sync(fake)
        self.assertIn(f"lists '{EVENT.upper()}', spelled unlike '{EVENT}'", out)
        self.assertFalse([w for w in fake.writes if "question[options]" in (w[2] or {})])

    def test_with_the_module_values_off_the_options_alone_are_written(self):
        qs, wire = before_rollout(*self.in_step())
        for mq in sync.MODULES.values():
            qs[mq]["calcValues"] = ""
        with mock.patch.object(glow_sync, "MODULE_CALC_VALUES", False):
            fake = FakeForm(qs, wire)
            _, out = self.run_sync(fake)
        self.assertEqual(fake.calls[0], "UPDATE module dropdown (q14, year 1: 1 event option(s) added "
                                        f"({EVENT}); calcValues none)")
        self.assertEqual(fake.writes[0][2], {"question[options]": f"Core 1|{EVENT}"})
        (entry,) = [m for m in auto_sync.parse_plan(out)["modules"] if m["qid"] == "14"]
        self.assertEqual(entry, {"qid": "14", "year": "1", "modules": 0, "events": 1})


class Runner(unittest.TestCase):
    """tools/auto_sync.py: an event-option write stops the region like the module values."""

    TEXT = ("Roster: 4 active clubs in Africa (8 girls); 300 clubs overall\n\nDRY RUN (use --apply to write):\n"
            + "".join(f"  - {line}\n" for line in EventSync.LINES) + "  - REPLACE conditions (40 rules)\n")

    def test_the_line_is_read_and_the_region_held(self):
        plan = auto_sync.parse_plan(self.TEXT)
        self.assertEqual([m["events"] for m in plan["modules"]], [1, 1, 1])
        self.assertEqual(auto_sync.changes(plan), 3)
        self.assertIn(", module values on 3 dropdown(s), special-event options on 3 dropdown(s)",
                      auto_sync.plan_summary(plan))
        (reason,) = auto_sync.check_bands(plan)
        self.assertIn("would add special-event option(s) to 3 module dropdown(s) (q14, q92, q93), with their "
                      "calcValues - never unattended", reason)
        self.assertIn("\"Special events\"", reason)
        for text in (self.TEXT, self.TEXT + "  - CREATE roster 'Gamma Club' (2 girls)\n"):
            run = AutoSyncFixture.run_region(self, text, apply=True)
            self.assertEqual((run.synced, [r[7] for r in run.results]), ([False], ["attention"]))
            self.assertIn("- MODULE values q92 (year 2: 3 modules, 1 special-event option(s) added)",
                          run.attention[0][1])
        # an event write next to a plain calcValues write: two reasons
        mixed = self.TEXT.replace(EventSync.LINES[1], "UPDATE module dropdown (q92, year 2: calcValues = its 3 options)")
        reasons = auto_sync.check_bands(auto_sync.parse_plan(mixed))
        self.assertEqual(len(reasons), 2)
        self.assertIn("(q14, q93)", reasons[0])
        self.assertIn("would write the calcValues of 1 module dropdown(s) (q92)", reasons[1])

    def test_the_format_is_the_syncs_and_nothing_else_matches(self):
        rx = auto_sync.MODULE_RX
        for line in EventSync.LINES:
            self.assertTrue(rx.match("  - " + line), line)
        self.assertEqual(rx.match("  - " + EventSync.LINES[0])["names"], EVENT)
        self.assertTrue(rx.match("  - UPDATE module dropdown (q14, year 1: 2 event option(s) added (A, B); "
                                 "calcValues none)"))
        for line in ("UPDATE module dropdown (q14, year 1: event option(s) added (A); calcValues = its 2 options)",
                     "UPDATE module dropdown (q14, year 1: 1 event option(s) added (); calcValues = its 2 options)",
                     "UPDATE module dropdown (q14, year 1: 1 event option(s) added (A); calcValues)"):
            self.assertFalse(rx.match("  - " + line), line)


class Audit(unittest.TestCase):
    """tools/form_status.py audit_special_events, the report and --rendered."""

    def in_step(self):
        return SameNameFixture.form(SameNameFixture(), switched=True)

    def test_an_in_step_form_is_clean_and_one_before_the_rollout_awaits_an_apply(self):
        qs, wire = self.in_step()
        problems, summary = form_status.audit_special_events(qs, wire)
        self.assertEqual(problems, [])
        self.assertEqual(summary["listed"], {q: {EVENT: 1} for q in sync.MODULES.values()})
        self.assertEqual((summary["session_rules"], summary["copies"], summary["event_rules"]), (4, WEEK_COPIES, 0))
        self.assertEqual(form_status.special_events_line(summary),
                         f"1 type(s) on 3 of 3 module dropdowns; session bridge rule {summary['bridge_rule']} of "
                         f"{summary['rules']}, 4 session rule(s), 0 on no curriculum module")
        old_qs, old = before_rollout(qs, wire)
        problems, summary = form_status.audit_special_events(old_qs, old)
        self.assertEqual(len(problems), 5)
        self.assertTrue(all("awaiting a sync apply by hand, template first (RUNBOOK \"Special events\")" in p
                            for p in problems))
        self.assertIn("module dropdown q14 (year 1) lacks the special event 'Special Event - Welcome Session'",
                      problems[0])
        self.assertIn("1 rule(s) show a session dropdown without testing a curriculum module", problems[3])
        self.assertIn("no session bridge (question 100", problems[4])
        self.assertIn("session bridge missing", form_status.special_events_line(summary))

    def test_each_check_fires_on_its_broken_form(self):
        qs, wire = self.in_step()

        def only(qs_=qs, wire_=wire):
            (problem,) = form_status.audit_special_events(qs_, wire_)[0]
            return problem
        twice = copy.deepcopy(qs)
        twice["92"]["options"] += "|" + EVENT
        self.assertIn("lists 'Special Event - Welcome Session' 2 times", only(twice))
        spelled = copy.deepcopy(qs)
        spelled["93"]["options"] = spelled["93"]["options"].replace(EVENT, EVENT.lower())
        self.assertIn(f"lists the special event as '{EVENT.lower()}', not '{EVENT}'", only(spelled))
        retired = copy.deepcopy(qs)
        retired["14"]["options"] += "|Special Event - Old Fair"
        self.assertIn("lists 'Special Event - Old Fair', which is no special event", only(retired))
        # the rules: the bridge after the session rules, in another shape, twice; an event's session rule
        rules = parsed(wire)
        pos = glow_sync.week_bridge_layout(wire)["position"]
        bridge = wire[pos]
        late = wire[:pos] + wire[pos + 1:] + [bridge]
        self.assertIn("after 8 rule(s) that show a session dropdown or copy one into question 100", only(wire_=late))
        action = dict(rules[pos][2][0], ignoreHiddenFields=False, operands="15,95,96,97")
        changed = dict(bridge, action=json.dumps([action]), link="All")
        self.assertIn("hidden session dropdowns not ignored; link 'All', not Any; 4 of them not among its operands",
                      only(wire_=wire[:pos] + [changed] + wire[pos + 1:]))
        terms = [t for t in rules[pos][1] if t["field"] != sync.MODULES["2"]]
        self.assertIn("its rule does not test 1 of the year, module and session dropdowns",
                      only(wire_=wire[:pos] + [dict(bridge, terms=json.dumps(terms))] + wire[pos + 1:]))
        self.assertIn("2 session bridges into question 100", only(wire_=wire[:pos + 1] + [bridge] + wire[pos + 1:]))
        event_rule = {"id": "1759999999999", "type": "field", "link": "All", "priority": "99", "index": "99",
                      "terms": json.dumps([sync.mk_term("14", "equals", EVENT), sync.mk_term("94", "equals", "1")]),
                      "action": json.dumps([sync.mk_show("15")])}
        self.assertIn("1 rule(s) show a session dropdown without testing a curriculum module", only(wire_=wire + [event_rule]))

    def test_the_report_and_the_runners_verify(self):
        qs, wire = self.in_step()
        for q_id, q in qs.items():
            q.setdefault("qid", q_id)

        def report(questions, conditions):
            class Fake:
                def get(self, path, **params):
                    if path.endswith("/questions"):
                        return copy.deepcopy(questions)
                    if path.endswith("/properties"):
                        return {"conditions": conditions, "clearFieldOnHide": "disable",
                                "language": [{"options": "English (US)|Español", "primaryLanguage": "en"}]}
                    if path.endswith("/translations"):
                        return served_store(questions)
                    return {"title": "t", "status": "ENABLED", "count": "0"}
            return form_status.form_report(glow_forms.TEMPLATE, Fake(), {})
        rep = report(qs, wire)
        self.assertEqual([p for p in rep["rule_problems"] if "event" in p or "bridge" in p], [])
        self.assertEqual(rep["special_events"]["listed"]["14"], {EVENT: 1})
        rep = report(*before_rollout(qs, wire))
        clean = {"error_conditions": 0, "salesforce": True, "languages": ["a"] * 12,
                 "region_check": {"missing_from_form": [], "not_in_roster": [], "rosters_out_of_date": []}}
        problems, _ = auto_sync.verify_report(dict(clean, rule_problems=rep["rule_problems"]))
        self.assertTrue(any("awaiting a sync apply by hand" in p for p in problems))

    def test_the_served_page_shows_the_options_and_the_bridge(self):
        qs, wire = self.in_step()
        page = served_rules_and_rosters(qs, wire)
        r = {}
        self.assertEqual(form_status.rendered_bridge_problems(r, page), [])
        self.assertEqual(r["rendered_events"], {q: {EVENT: (1, 1)} for q in sync.MODULES.values()})
        self.assertEqual((r["rendered_bridge"]["late"], r["rendered_bridge"]["ignore_hidden"]), (0, True))
        self.assertEqual(r["rendered_bridge"]["operands"], list(glow_sync.WEEK_BRIDGE_FIELDS))
        # a page from before the apply: no event option served, no bridge
        problems = form_status.rendered_bridge_problems({}, served_rules_and_rosters(*before_rollout(qs, wire)))
        self.assertEqual(len(problems), 4)
        self.assertIn("rendered page: module dropdown q14 serves 'Special Event - Welcome Session' 0 time(s)",
                      problems[0])
        self.assertIn("rendered page: no session bridge (question 100) in JotForm.setConditions", problems[3])
        # the event served without its data-calcvalue
        bare = copy.deepcopy(qs)
        bare["14"]["calcValues"] = "|Core 1"
        (problem,) = form_status.rendered_bridge_problems({}, served_rules_and_rosters(bare, wire))
        self.assertIn("q14 serves 'Special Event - Welcome Session' 1 time(s), 0 with its data-calcvalue", problem)
        # Jotform dropping the operands that are not in the equation, or the hidden-fields flag
        calcs = re.search(r"JotForm\.setCalculations\((.*?)\);", page, re.S)
        served = json.loads(calcs.group(1))
        for change, fragment in (({"operands": "15,95,96,97"}, "lacks 4 of its operands: q14, q92, q93, q94"),
                                 ({"ignoreHiddenFields": "0"}, "does not ignore hidden fields")):
            edited = [dict(c, **change) if c["resultField"] == sync.WEEK_ID and len(c["equation"]) > 6 else c
                      for c in served]
            (problem,) = form_status.rendered_bridge_problems({}, page.replace(calcs.group(1), json.dumps(edited)))
            self.assertIn(fragment, problem)
        # the served order: the bridge last
        pos = glow_sync.week_bridge_layout(wire)["position"]
        late = wire[:pos] + wire[pos + 1:] + [wire[pos]]
        (problem,) = form_status.rendered_bridge_problems({}, served_rules_and_rosters(qs, late))
        self.assertIn("after 8 rule(s) that show a session dropdown or copy one", problem)
        self.assertEqual(module_lists({"1": "Core 1"}), {"1": ["Core 1", EVENT]})


class RunbookQuotes(unittest.TestCase):
    """docs/RUNBOOK.md "Special events" quotes the tools' own lines."""

    def section(self):
        doc = read(os.path.join(REPO, "docs", "RUNBOOK.md"))
        return " ".join(doc.split("\n## Special events\n", 1)[1].split("\n## ", 1)[0].split())

    def test_the_quoted_lines_are_the_tools_own(self):
        text = self.section()
        line = ("UPDATE module dropdown (q14, year 1: 1 event option(s) added (Special Event - Welcome Session); "
                "calcValues = its 6 options)")
        self.assertIn(line, text)
        self.assertTrue(auto_sync.MODULE_RX.match("  - " + line))
        self.assertIn("would add special-event option(s) to 3 module dropdown(s) (q14, q92, q93), with their "
                      "calcValues - never unattended", text)
        reason = auto_sync.check_bands(auto_sync.parse_plan(Runner.TEXT))[0]
        self.assertIn("would add special-event option(s) to 3 module dropdown(s) (q14, q92, q93), with their "
                      "calcValues - never unattended", reason)
        warning = "which is no special event of glow/sync.py SPECIAL_EVENTS: left as it is"
        self.assertIn(warning, text)
        self.assertIn(warning, re.sub(r'"\s*\n\s*"', "", read(os.path.join(REPO, "sync_attendance_form.py"))))
        self.assertIn("awaiting " + form_status.EVENTS_FIX, text)
        self.assertIn("special events: 1 type(s) on 3 of 3 module dropdowns; session bridge rule N of M", text)
        self.assertIn("`{15}{95}{96}{97}`", text)
        self.assertEqual(glow_sync.week_bridge_equation(), "{15}{95}{96}{97}")
        self.assertIn("`restore_conditions.py --from`", text)


if __name__ == "__main__":
    unittest.main(verbosity=1)
