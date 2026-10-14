#!/usr/bin/env python3
"""
Special events (docs/plans/2026-10-13-special-events.md): "Special Event - <type>" as one more
option of every module dropdown, with no session dropdown and question 100 blank - the constants
(glow/sync.py), the cascade and the session bridge (build_conditions), the sync's one write per
module dropdown, the runner applying that write on its next run (docs/DECISIONS.md, 2026-10-14),
form_status's audits (API and served page).
glow/submissions.py's reading of an event: test/backfill_resolve_test.py. On SameNameFixture's
fake Africa form; fictional names.
"""
import copy
import json
import os
import re
import sys
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
WELCOME = EVENT
IDG = "Special Event - IDG Celebrations"        # the second type (ticket #26): after Welcome Session
WEEK_COPIES = 4                                  # one calculation per session dropdown into question 100

# The mechanism classes below were written when Welcome Session was the only type: their literals
# (one option added, "its 2 options", the form "before the rollout") describe a one-type world.
# They stay meaningful by pinning the constant to that world; the live two-type list is pinned by
# Constants, IdgSync, IdgRules, IdgAudit and IdgDocs.
ONE_TYPE = mock.patch.object(glow_sync, "SPECIAL_EVENTS", ("Welcome Session",))


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
                         ("Special Event - ", ("Welcome Session", "IDG Celebrations")))
        self.assertEqual(glow_sync.special_event_options(), [WELCOME, IDG])     # Welcome first: never reordered
        for option in (WELCOME, IDG, "special event -  Welcome Session", "special EVENT - idg   celebrations",
                       "Special Event - Retired Type"):
            self.assertTrue(glow_sync.is_special_event(option), option)
        for option in ("Elective - Healthy GLOW", "Relationships 101", "", None, "Event - Welcome Session"):
            self.assertFalse(glow_sync.is_special_event(option), option)

    def test_the_live_plan_of_a_dropdown_appends_what_is_missing_in_type_order(self):
        plan = glow_sync.special_event_plan
        # the live state: Welcome Session there, IDG Celebrations to come, after it
        self.assertEqual(plan(["Core 1", WELCOME]), {"add": [IDG], "unknown": [], "respelled": []})
        self.assertEqual(plan(["Core 1"])["add"], [WELCOME, IDG])
        self.assertEqual(plan(["Core 1", IDG])["add"], [WELCOME])
        # both there, in either order, anywhere: nothing to add
        for options in (["Core 1", WELCOME, IDG], ["Core 1", IDG, WELCOME], [IDG, "Core 1", WELCOME]):
            self.assertEqual(plan(options), {"add": [], "unknown": [], "respelled": []}, options)
        self.assertEqual(plan(["Core 1", WELCOME, "special event - idg  celebrations"]),
                         {"add": [], "unknown": [], "respelled": [("special event - idg  celebrations", IDG)]})
        self.assertEqual(plan(["Core 1", WELCOME, "Special Event - Old Fair"]),
                         {"add": [IDG], "unknown": ["Special Event - Old Fair"], "respelled": []})

    @ONE_TYPE
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


@ONE_TYPE
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
                         [{"qid": "14", "year": "1", "modules": 2, "events": [EVENT], "calc": "set"},
                          {"qid": "92", "year": "2", "modules": 3, "events": [EVENT], "calc": "set"},
                          {"qid": "93", "year": "3", "modules": 2, "events": [EVENT], "calc": "set"}])
        # the runner reads the same plan from the printed lines and from the summary, and holds it
        want = [{"qid": q, "year": y, "modules": n, "events": 1, "calc": "set"}
                for q, y, n in (("14", "1", 2), ("92", "2", 3), ("93", "3", 2))]
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
        self.assertEqual(entry, {"qid": "14", "year": "1", "modules": 0, "events": 1, "calc": "none"})


class Runner(unittest.TestCase):
    """tools/auto_sync.py: an event-option write is applied on the runner's next run like the
    module values, within the bands (docs/DECISIONS.md, 2026-10-14)."""

    HEAD = "Roster: 4 active clubs in Africa (8 girls); 300 clubs overall\n\nDRY RUN (use --apply to write):\n"
    TEXT = HEAD + "".join(f"  - {line}\n" for line in EventSync.LINES) + "  - REPLACE conditions (40 rules)\n"
    DETAIL = ("0 create(s), 0 update(s), 0 delete(s), 0 warning(s), module values on 3 dropdown(s), "
              "special-event options on 3 dropdown(s)")

    def test_the_line_is_read_and_the_region_applied(self):
        plan = auto_sync.parse_plan(self.TEXT)
        self.assertEqual([m["events"] for m in plan["modules"]], [1, 1, 1])
        self.assertEqual(auto_sync.changes(plan), 3)
        self.assertEqual(auto_sync.plan_summary(plan), self.DETAIL)
        self.assertEqual(auto_sync.check_bands(plan), [])
        self.assertEqual(auto_sync.check_bands(plan, max_updates=0), [])   # a module line is no roster update
        for text, want in ((self.TEXT, self.DETAIL),
                           (self.TEXT + "  - CREATE roster 'Gamma Club' (2 girls)\n",
                            self.DETAIL.replace("0 create(s)", "1 create(s)"))):
            run = AutoSyncFixture.run_region(self, text, apply=True)
            self.assertEqual((run.synced, [r[7:9] for r in run.results], run.attention),
                             ([False, True], [["applied", want + "; verified clean"]], []), text)
            run = AutoSyncFixture.run_region(self, text)
            self.assertEqual((run.synced, [r[7:9] for r in run.results], run.attention),
                             ([False], [["dry-run", "would apply: " + want]], []), text)
        # an event write next to a plain calcValues write: applied all the same
        mixed = self.TEXT.replace(EventSync.LINES[1], "UPDATE module dropdown (q92, year 2: calcValues = its 3 options)")
        plan = auto_sync.parse_plan(mixed)
        self.assertEqual(auto_sync.check_bands(plan), [])
        self.assertEqual(auto_sync.plan_summary(plan), self.DETAIL.replace("options on 3", "options on 2"))
        run = AutoSyncFixture.run_region(self, mixed, apply=True)
        self.assertEqual((run.synced, [r[7] for r in run.results]), ([False, True], ["applied"]))
        # held by a band (a delete), the ATTENTION list still names each dropdown's write
        run = AutoSyncFixture.run_region(self, self.TEXT + "  - DELETE roster 'Elsewhere' (q140, belongs to Asia)\n",
                                         apply=True)
        self.assertEqual((run.synced, [r[7] for r in run.results]), ([False], ["attention"]))
        self.assertTrue(run.results[0][8].startswith("would delete 1 roster question(s)"), run.results[0][8])
        self.assertIn("- MODULE values q92 (year 2: 3 modules, 1 special-event option(s) added)", run.attention[0][1])

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


@ONE_TYPE
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
        self.assertIn("correct it in the builder", only(spelled))
        # the exact option AND one in another case: still reported (a mentor may pick the other)
        both = copy.deepcopy(qs)
        both["92"]["options"] += "|" + EVENT.upper()
        self.assertIn(f"lists the special event as '{EVENT.upper()}', not '{EVENT}' - Salesforce receives the "
                      "form's spelling; remove it in the builder (the exact option is listed too)", only(both))
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
        self.assertEqual(r["rendered_events"], {q: {EVENT: (1, 1, 0)} for q in sync.MODULES.values()})
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
        # MODULE_CALC_VALUES off (the generated rollback): no data-calcvalue is asked for, as for
        # every module option; one other than the value still is a problem
        with mock.patch.object(glow_sync, "MODULE_CALC_VALUES", False):
            bare = copy.deepcopy(qs)
            for q in sync.MODULES.values():
                bare[q]["calcValues"] = ""
            r = {}
            self.assertEqual(form_status.rendered_bridge_problems(r, served_rules_and_rosters(bare, wire)), [])
            self.assertEqual(r["rendered_events"]["14"], {EVENT: (1, 0, 0)})
            other = copy.deepcopy(qs)
            other["14"]["calcValues"] = "|Core 1|Special Event - Something Else"
            (problem,) = form_status.rendered_bridge_problems({}, served_rules_and_rosters(other, wire))
            self.assertIn("q14 serves 'Special Event - Welcome Session' 1 time(s), 0 with its data-calcvalue, "
                          "1 with another", problem)
            self.assertFalse(form_status.event_served_ok((0, 0, 0)))
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


@ONE_TYPE
class StaleRules(unittest.TestCase):
    """A form that carries the event option but whose live rules are the old way (an apply that
    stopped after the module writes, or the option added in the builder): the dry run plans a
    rules-only REPLACE, which the runner never reads as in-sync and applies on its next run
    (docs/DECISIONS.md, 2026-10-14)."""

    # the warning's ending since 2026-10-14; the runner matches on the constant before the colon
    RUNNER_APPLIES = ("the rewrite puts it right; the runner applies it on its next run (the template and a "
                      "disabled form by hand: docs/RUNBOOK.md, \"Special events\")")

    ROSTER, QIDS, MODULES, texts = SameNameFixture.ROSTER, SameNameFixture.QIDS, SameNameFixture.MODULES, SameNameFixture.texts

    def setUp(self):
        SameNameFixture.setUp(self)

    def tearDown(self):
        SameNameFixture.tearDown(self)

    def run_sync(self, fake, *extra):
        return SameNameFixture.run_sync(self, fake, *extra)

    def summary(self, fake, *extra):
        return SameNameFixture.summary(self, fake, *extra)

    def options_in_step_rules_old(self):
        qs, wire = SameNameFixture.form(self, switched=True)
        return qs, before_rollout(qs, wire)[1]

    def test_the_layout_says_what_is_stale(self):
        qs, wire = SameNameFixture.form(self, switched=True)
        self.assertEqual(glow_sync.week_bridge_stale(wire), [])
        self.assertEqual(glow_sync.week_bridge_stale([]), [])                     # nothing to compare
        old = before_rollout(qs, wire)[1]
        self.assertEqual(glow_sync.week_bridge_stale(old), [
            "1 rule(s) show a session dropdown without testing a curriculum module (first: rule 9)",
            "no session bridge, so question 100 keeps a session picked before the event"])
        pos = glow_sync.week_bridge_layout(wire)["position"]
        late = wire[:pos] + wire[pos + 1:] + [wire[pos]]
        (why,) = glow_sync.week_bridge_stale(late)
        self.assertRegex(why, r"^the session bridge is rule \d+ of \d+, after 8 session rule\(s\) or copies$")
        terms, (action,) = glow_sync.rule_parts(wire[pos])
        shaped = wire[:pos] + [dict(wire[pos], action=json.dumps([dict(action, ignoreHiddenFields=False)]))] \
            + wire[pos + 1:]
        self.assertEqual(glow_sync.week_bridge_stale(shaped), ["the session bridge: hidden session dropdowns not ignored"])
        doubled = wire[:pos + 1] + [wire[pos]] + wire[pos + 1:]
        self.assertEqual(glow_sync.week_bridge_stale(doubled), ["2 session bridges into question 100"])

    def test_options_in_step_with_old_rules_is_applied_never_in_sync(self):
        self.assertEqual(auto_sync.WEEK_BRIDGE_STALE, sync.WEEK_BRIDGE_STALE)
        fake = FakeForm(*self.options_in_step_rules_old())
        summary, out = self.summary(fake)
        self.assertEqual(len(fake.calls), 1)
        self.assertRegex(fake.calls[0], r"^REPLACE conditions \(\d+ rules\)$")      # rules only
        (warning,) = summary["warnings"]
        self.assertTrue(warning.startswith(f"  ! {sync.WEEK_BRIDGE_STALE}: 1 rule(s) show a session dropdown"))
        self.assertTrue(warning.endswith(" - " + self.RUNNER_APPLIES), warning)
        self.assertNotIn("apply this form by hand", warning)
        detail = "0 create(s), 0 update(s), 0 delete(s), 1 warning(s), special-event rules rewritten"
        for plan in (auto_sync.parse_plan(out), auto_sync.plan_from_summary(summary)):
            self.assertEqual((auto_sync.changes(plan), len(auto_sync.week_bridge_stale(plan))), (0, 1))
            self.assertEqual(auto_sync.check_bands(plan), [])
            self.assertEqual(auto_sync.plan_summary(plan), detail)
        busy = out.replace("  - REPLACE", "  - CREATE roster 'Gamma Club' (2 girls)\n  - REPLACE")
        for text, summ, want in ((out, None, detail), (busy, None, detail.replace("0 create(s)", "1 create(s)")),
                                 (out, summary, detail)):
            run = AutoSyncFixture.run_region(self, text, apply=True, summary=summ)
            self.assertEqual(run.synced, [False, True], text)                # the dry run, then the apply
            self.assertEqual(run.steps, ["sync", "backup", "save conditions", "sync --apply", "verify"], text)
            self.assertEqual([r[7:9] for r in run.results], [["applied", want + "; verified clean"]], text)
            self.assertEqual(run.attention, [], text)
            run = AutoSyncFixture.run_region(self, text, apply=False, summary=summ)
            self.assertEqual((run.synced, run.steps), ([False], ["sync"]), text)
            self.assertEqual([r[7:9] for r in run.results], [["dry-run", "would apply: " + want]], text)
            self.assertEqual(run.attention, [], text)

    def test_new_rules_read_in_sync_and_a_form_without_events_is_not_asked(self):
        qs, wire = SameNameFixture.form(self, switched=True)
        # a rules-only difference that leaves the special events' rules in shape (a copy rule
        # deleted in the builder): in-sync, as every rules-only plan
        gone = [c for c in wire if not any(a.get("resultField") == sync.YEAR_ID for a in glow_sync.rule_parts(c)[1])]
        fake = FakeForm(qs, gone)
        _, out = self.run_sync(fake)
        self.assertEqual(len(fake.calls), 1)
        self.assertNotIn(sync.WEEK_BRIDGE_STALE, out)
        run = AutoSyncFixture.run_region(self, out, apply=True)
        self.assertEqual(([r[7] for r in run.results], run.attention), (["in-sync"], []))
        # the form in step: nothing at all
        fake = FakeForm(qs, wire)
        self.assertEqual((self.run_sync(fake)[0], fake.calls), (0, []))
        # no event anywhere (no type listed, none on the form): old rules are nobody's business here
        bare_qs, old = before_rollout(qs, wire)
        with mock.patch.object(glow_sync, "SPECIAL_EVENTS", ()):
            _, out = self.run_sync(FakeForm(bare_qs, old))
        self.assertNotIn(sync.WEEK_BRIDGE_STALE, out)

    def test_a_write_of_the_options_alone_says_so_and_is_applied(self):
        qs, wire = SameNameFixture.form(self, switched=True)
        # the option deleted in the builder, its calcValues left aligned to the full list
        qs["14"]["options"] = "Core 1"
        fake = FakeForm(qs, wire)
        _, out = self.run_sync(fake)
        line = (f"UPDATE module dropdown (q14, year 1: 1 event option(s) added ({EVENT}); calcValues unchanged)")
        self.assertEqual(fake.calls[0], line)
        self.assertEqual(fake.writes[0][2], {"question[options]": f"Core 1|{EVENT}"})
        plan = auto_sync.parse_plan(out)
        self.assertEqual(plan["modules"], [{"qid": "14", "year": "1", "modules": 0, "events": 1, "calc": "unchanged"}])
        self.assertEqual(auto_sync.check_bands(plan), [])
        detail = ("0 create(s), 0 update(s), 0 delete(s), 0 warning(s), module values on 1 dropdown(s), "
                  "special-event options on 1 dropdown(s)")
        run = AutoSyncFixture.run_region(self, out, apply=True)
        self.assertEqual((run.synced, [r[7:9] for r in run.results], run.attention),
                         ([False, True], [["applied", detail + "; verified clean"]], []))
        run = AutoSyncFixture.run_region(self, out)
        self.assertEqual((run.synced, [r[7:9] for r in run.results]), ([False], [["dry-run", "would apply: " + detail]]))
        # every shape of the line is applied; held by a band (a delete), the ATTENTION list tells
        # "calcValues unchanged" from "no calcValues" (options alone, values off) and "cleared"
        delete = "  - DELETE roster 'Elsewhere' (q140, belongs to Asia)\n"
        for words, attention in (("calcValues unchanged", "calcValues unchanged"), ("calcValues none", "no calcValues"),
                                 ("calcValues cleared", "cleared")):
            text = (Runner.HEAD
                    + f"  - UPDATE module dropdown (q14, year 1: 1 event option(s) added ({EVENT}); {words})\n")
            self.assertEqual(auto_sync.check_bands(auto_sync.parse_plan(text)), [], words)
            run = AutoSyncFixture.run_region(self, text, apply=True)
            self.assertEqual((run.synced, [r[7] for r in run.results], run.attention),
                             ([False, True], ["applied"], []), words)
            run = AutoSyncFixture.run_region(self, text + delete, apply=True)
            self.assertEqual((run.synced, [r[7] for r in run.results]), ([False], ["attention"]), words)
            self.assertTrue(run.results[0][8].startswith("would delete 1 roster question(s)"), run.results[0][8])
            self.assertIn(f"- MODULE values q14 (year 1: {attention}, 1 special-event option(s) added)",
                          run.attention[0][1])


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
        # the runner's hold is gone (docs/DECISIONS.md, 2026-10-14): no reason of its to quote
        self.assertNotIn("never unattended", text)
        self.assertEqual(auto_sync.check_bands(auto_sync.parse_plan(Runner.TEXT)), [])
        warning = "which is no special event of glow/sync.py SPECIAL_EVENTS: left as it is"
        self.assertIn(warning, text)
        self.assertIn(warning, re.sub(r'"\s*\n\s*"', "", read(os.path.join(REPO, "sync_attendance_form.py"))))
        self.assertIn("awaiting " + form_status.EVENTS_FIX, text)
        self.assertIn("special events: 2 type(s) on 3 of 3 module dropdowns; session bridge rule N of M", text)
        self.assertIn("`{15}{95}{96}{97}`", text)
        self.assertEqual(glow_sync.week_bridge_equation(), "{15}{95}{96}{97}")
        self.assertIn("`restore_conditions.py --from`", text)
        # the stale-rules warning, here and in "Automatic sync"
        self.assertIn(f"`! {sync.WEEK_BRIDGE_STALE}: …`", text)
        self.assertIn("`calcValues unchanged)`", text)
        runner = " ".join(read(os.path.join(REPO, "docs", "RUNBOOK.md"))
                          .split("## Automatic sync", 1)[1].split("\n## ", 1)[0].split())
        self.assertIn(sync.WEEK_BRIDGE_STALE, runner)
        self.assertIn(f'WEEK_BRIDGE_STALE = "{auto_sync.WEEK_BRIDGE_STALE}"', read(os.path.join(REPO, "tools", "auto_sync.py")))
        self.assertIn("{WEEK_BRIDGE_STALE}: ", read(os.path.join(REPO, "sync_attendance_form.py")))


# ---------------------------------------------------------------------------------------------
# The second type, "IDG Celebrations" (ticket #26), on the live list of two types. Literal options
# and calcValues throughout: nothing here asks the code under test what the answer is. The live
# state is a form that already carries Welcome Session on q14, q92 and q93 (rollout 2026-10-13).

CURRICULUM = {"14": ["Core 1"], "92": ["Core 2", "Elective - Healthy GLOW"], "93": ["Core 3"]}


def shaped(**by_qid):
    """(questions, wire conditions) of SameNameFixture's in-step Africa form with the module
    dropdowns set to literal option lists (default: the curriculum, Welcome Session, IDG
    Celebrations) and calcValues aligned to them (an empty slot, then each option). The rules are
    the in-step ones: an event has no session rule, so they do not depend on the event options.
    shaped(q14=[...]) sets q14's options."""
    qs, wire = SameNameFixture.form(SameNameFixture(), switched=True)
    for qid, curriculum in CURRICULUM.items():
        options = by_qid.get("q" + qid, curriculum + [WELCOME, IDG])
        qs[qid]["options"] = "|".join(options)
        qs[qid]["calcValues"] = "|" + "|".join(options)
    return qs, wire


def live_state():
    """The forms as they are live: Welcome Session on q14, q92 and q93, nothing after it."""
    return shaped(**{"q" + q: c + [WELCOME] for q, c in CURRICULUM.items()})


def after_writes(qs, writes):
    """The questions once the sync's module writes have been applied (payload keys as Jotform's API)."""
    qs = copy.deepcopy(qs)
    for _method, path, payload in writes:
        if path.startswith("/question/") and payload and "question[options]" in payload:
            qs[path.rsplit("/", 1)[1]]["options"] = payload["question[options]"]
            if "question[calcValues]" in payload:
                qs[path.rsplit("/", 1)[1]]["calcValues"] = payload["question[calcValues]"]
    return qs


class IdgSync(unittest.TestCase):
    """sync_attendance_form.main (a dry run, then --apply on the fake form) with the live list of
    two types, and what the runner makes of the dry run's own output."""

    ROSTER, QIDS, MODULES, texts = SameNameFixture.ROSTER, SameNameFixture.QIDS, SameNameFixture.MODULES, SameNameFixture.texts
    LIVE_LINES = [f"UPDATE module dropdown (q14, year 1: 1 event option(s) added ({IDG}); calcValues = its 3 options)",
                  f"UPDATE module dropdown (q92, year 2: 1 event option(s) added ({IDG}); calcValues = its 4 options)",
                  f"UPDATE module dropdown (q93, year 3: 1 event option(s) added ({IDG}); calcValues = its 3 options)"]

    def setUp(self):
        SameNameFixture.setUp(self)

    def tearDown(self):
        SameNameFixture.tearDown(self)

    def run_sync(self, fake, *extra):
        return SameNameFixture.run_sync(self, fake, *extra)

    def summary(self, fake, *extra):
        return SameNameFixture.summary(self, fake, *extra)

    def test_a_form_with_welcome_session_gets_exactly_one_option_added_per_dropdown(self):
        qs, wire = live_state()
        fake = FakeForm(qs, wire)
        summary, out = self.summary(fake)
        self.assertEqual(fake.calls, self.LIVE_LINES)                # no rules rewrite: the rules are in step
        self.assertIn("(conditions unchanged - skipping the rewrite)", out)
        # the new option goes after Welcome Session, which stays where it is; calcValues cover every option
        self.assertEqual([w[1:] for w in fake.writes], [
            ("/question/14", {"question[options]": f"Core 1|{WELCOME}|{IDG}",
                              "question[calcValues]": f"|Core 1|{WELCOME}|{IDG}"}),
            ("/question/92", {"question[options]": f"Core 2|Elective - Healthy GLOW|{WELCOME}|{IDG}",
                              "question[calcValues]": f"|Core 2|Elective - Healthy GLOW|{WELCOME}|{IDG}"}),
            ("/question/93", {"question[options]": f"Core 3|{WELCOME}|{IDG}",
                              "question[calcValues]": f"|Core 3|{WELCOME}|{IDG}"})])
        self.assertEqual(summary["module_values"],
                         [{"qid": "14", "year": "1", "modules": 3, "events": [IDG], "calc": "set"},
                          {"qid": "92", "year": "2", "modules": 4, "events": [IDG], "calc": "set"},
                          {"qid": "93", "year": "3", "modules": 3, "events": [IDG], "calc": "set"}])

    def test_every_write_only_appends_and_its_calcvalues_line_up_with_its_options(self):
        # nothing removed, renamed or reordered: the form's options are a prefix of the written ones
        # and the one appended is the new type; calcValues = the empty slot, then each option
        for label, (qs, wire), added in (("live", live_state(), [IDG]),
                                         ("hand-ordered", shaped(q14=[WELCOME, "Core 1"], q92=[
                                             "Core 2", WELCOME, "Elective - Healthy GLOW"], q93=["Core 3"]),
                                          None)):
            with self.subTest(label):
                fake = FakeForm(qs, wire)
                self.run_sync(fake)
                self.assertTrue(fake.writes)
                for _m, path, payload in fake.writes:
                    qid = path.rsplit("/", 1)[1]
                    before = qs[qid]["options"].split("|")
                    written = payload["question[options]"].split("|")
                    self.assertEqual(written[:len(before)], before, qid)
                    self.assertEqual(written[len(before):], added if added else
                                     [e for e in (WELCOME, IDG) if e not in before], qid)
                    self.assertEqual(payload["question[calcValues]"].split("|"), [""] + written, qid)
                    if WELCOME in before:                            # where it was, it stays
                        self.assertEqual(written.index(WELCOME), before.index(WELCOME), qid)

    def test_after_the_apply_the_form_is_in_step_and_a_second_run_writes_nothing(self):
        qs, wire = live_state()
        fake = FakeForm(qs, wire, apply=True)
        self.assertEqual(self.run_sync(fake, "--apply")[0], 0)
        self.assertEqual(len(fake.writes), 3)
        applied = after_writes(qs, fake.writes)
        self.assertEqual({q: applied[q]["options"] for q in CURRICULUM},
                         {"14": f"Core 1|{WELCOME}|{IDG}",
                          "92": f"Core 2|Elective - Healthy GLOW|{WELCOME}|{IDG}",
                          "93": f"Core 3|{WELCOME}|{IDG}"})
        again = FakeForm(applied, wire)
        self.assertEqual((self.run_sync(again)[0], again.calls), (0, []))
        self.assertEqual(form_status.audit_special_events(applied, wire)[0], [])
        self.assertEqual(form_status.audit_module_values(applied)[0], [])

    def test_the_options_missing_in_other_states_are_appended_in_type_order_and_nothing_else_moves(self):
        cases = (
            # (label, the dropdowns' options, the options written: {qid: options}; {} = no write)
            ("neither type yet", dict(q14=["Core 1"], q92=["Core 2", "Elective - Healthy GLOW"], q93=["Core 3"]),
             {"14": f"Core 1|{WELCOME}|{IDG}", "92": f"Core 2|Elective - Healthy GLOW|{WELCOME}|{IDG}",
              "93": f"Core 3|{WELCOME}|{IDG}"}),
            ("the new type added by hand ahead of the first", dict(q92=["Core 2", "Elective - Healthy GLOW", IDG]),
             {"92": f"Core 2|Elective - Healthy GLOW|{IDG}|{WELCOME}"}),
            ("Welcome Session moved to the top by hand", dict(q14=[WELCOME, "Core 1"]),
             {"14": f"{WELCOME}|Core 1|{IDG}"}),
            ("both there, the new one first", dict(q93=["Core 3", IDG, WELCOME]), {}),
            ("a retired type kept", dict(q14=["Core 1", WELCOME, "Special Event - Old Fair"]),
             {"14": f"Core 1|{WELCOME}|Special Event - Old Fair|{IDG}"}),
        )
        for label, options, want in cases:
            with self.subTest(label):
                # a dropdown not named keeps the full list; "neither" starts all three bare
                start = shaped(**options)
                fake = FakeForm(*start)
                self.run_sync(fake)
                got = {w[1].rsplit("/", 1)[1]: w[2]["question[options]"] for w in fake.writes
                       if "question[options]" in (w[2] or {})}
                self.assertEqual(got, want)
                self.assertEqual(len(fake.writes), len(want))        # nothing but those writes: rules in step
        # both spelled differently in the case of the new one: counted as present, warned, never added twice
        qs, wire = shaped(q93=["Core 3", WELCOME, IDG.upper()])
        fake = FakeForm(qs, wire)
        code, out = self.run_sync(fake)
        self.assertIn(f"lists '{IDG.upper()}', spelled unlike '{IDG}'", out)
        self.assertFalse([w for w in fake.writes if "question[options]" in (w[2] or {})])

    def test_neither_type_yet_is_one_write_per_dropdown_naming_both_and_the_rules_get_no_event_rule(self):
        # the form from before 2026-10-13: no options, the old rules (a year-1 rule on the year alone,
        # no bridge) - the first apply of both types at once
        bare = dict(q14=["Core 1"], q92=["Core 2", "Elective - Healthy GLOW"], q93=["Core 3"])
        qs, wire = shaped(**bare)
        old = before_rollout(qs, wire)[1]
        fake = FakeForm(qs, old)
        self.run_sync(fake)
        self.assertEqual(fake.calls[:3], [
            f"UPDATE module dropdown (q14, year 1: 2 event option(s) added ({WELCOME}, {IDG}); "
            "calcValues = its 3 options)",
            f"UPDATE module dropdown (q92, year 2: 2 event option(s) added ({WELCOME}, {IDG}); "
            "calcValues = its 4 options)",
            f"UPDATE module dropdown (q93, year 3: 2 event option(s) added ({WELCOME}, {IDG}); "
            "calcValues = its 3 options)"])
        self.assertRegex(fake.calls[3], r"^REPLACE conditions \(\d+ rules\)$")
        written = fake.writes[3][2]["properties"]["conditions"]
        self.assertTrue(sync.same_conditions(written, shaped()[1]))
        shape = glow_sync.week_bridge_layout(written)
        self.assertEqual((len(shape["bridge"]), shape["event_rules"]), (1, []))
        self.assertFalse([m for _, m, _, _ in session_rules(written) if m in (WELCOME, IDG)])
        self.assertTrue(session_rules(written))                      # the curriculum modules keep theirs

    # --- the runner: the dry run's own output is read and held ---------------------------------

    def test_the_runner_never_applies_the_new_option_unattended(self):
        qs, wire = live_state()
        summary, out = self.summary(FakeForm(qs, wire))
        want = [{"qid": q, "year": y, "modules": n, "events": 1, "calc": "set"}
                for q, y, n in (("14", "1", 3), ("92", "2", 4), ("93", "3", 3))]
        plan = auto_sync.parse_plan(out)
        self.assertEqual((plan["modules"], auto_sync.plan_from_summary(summary)["modules"]), (want, want))
        self.assertEqual(auto_sync.changes(plan), 3)
        (reason,) = auto_sync.check_bands(plan)
        self.assertIn("would add special-event option(s) to 3 module dropdown(s) (q14, q92, q93), with their "
                      "calcValues - never unattended", reason)
        for text in (out, out + "  - CREATE roster 'Gamma Club' (2 girls)\n"):
            for sm in (None, summary):
                run = AutoSyncFixture.run_region(self, text, apply=True, summary=sm)
                self.assertEqual((run.synced, [r[7] for r in run.results]), ([False], ["attention"]))
                self.assertIn("- MODULE values q92 (year 2: 4 modules, 1 special-event option(s) added)",
                              run.attention[0][1])
        # a form lacking both types: two options a dropdown, still one reason, still held
        qs, wire = shaped(q14=["Core 1"], q92=["Core 2", "Elective - Healthy GLOW"], q93=["Core 3"])
        summary, out = self.summary(FakeForm(qs, wire))
        plan = auto_sync.parse_plan(out)
        self.assertEqual([m["events"] for m in plan["modules"]], [2, 2, 2])
        self.assertEqual(len(auto_sync.check_bands(plan)), 1)
        run = AutoSyncFixture.run_region(self, out, apply=True, summary=summary)
        self.assertEqual((run.synced, [r[7] for r in run.results]), ([False], ["attention"]))
        self.assertIn("2 special-event option(s) added", run.attention[0][1])


class IdgRules(unittest.TestCase):
    """build_conditions with both types among the module options."""

    CLUBS = {"10": "Alpha Club", "11": "Beta Club"}

    def build(self, modules, picker=None):
        return sync.build_conditions(self.CLUBS, {}, modules, picker=picker,
                                     picker_options=list(self.CLUBS.values()) if picker else None)

    def test_neither_event_gets_a_session_rule_and_the_bridge_still_heads_the_cascade(self):
        self.assertEqual(glow_sync.special_event_options(), [WELCOME, IDG])
        modules = {"1": ["Core 1", "Core 1b", WELCOME, IDG],
                   "2": ["Core 2", "Elective - Healthy GLOW", IDG, WELCOME],
                   "3": ["Elective - Girl Boss Pro", WELCOME, "Special Event - Old Fair", IDG]}
        for picker in (None, "500"):
            with self.subTest(picker=picker):
                conds = self.build(modules, picker)
                # exactly the curriculum's rules, none for either event
                self.assertEqual(session_rules(conds), [
                    ("14", "Core 1", "1", "15"), ("14", "Core 1b", "1", "15"),
                    ("92", "Core 2", "2", "15"), ("92", "Elective - Healthy GLOW", "2", "96"),
                    ("93", "Elective - Girl Boss Pro", "3", "97")])
                for _, terms, _actions in parsed(conds):
                    self.assertFalse([t for t in terms if t.get("value") in (WELCOME, IDG)], terms)
                shape = glow_sync.week_bridge_layout(conds)
                self.assertEqual((len(shape["bridge"]), len(shape["copies"]), shape["event_rules"]),
                                 (1, WEEK_COPIES, []))
                pos = shape["position"]
                self.assertEqual(pos, (1 if picker else 0) + len(self.CLUBS))   # first of section B
                self.assertTrue(all(p > pos for p in shape["session_rules"] + shape["copies"]))
                self.assertEqual(glow_sync.week_bridge_stale(conds), [])
        # the events add nothing: the same rules as for the curriculum alone
        bare = {y: [o for o in opts if not glow_sync.is_special_event(o)] for y, opts in modules.items()}
        self.assertTrue(sync.same_conditions(self.build(modules, "500"), self.build(bare, "500")))


class IdgAudit(unittest.TestCase):
    """tools/form_status.py with the live list of two types: a form lacking the new one is NOT CLEAN."""

    FIX = 'awaiting a sync apply by hand, template first (RUNBOOK "Special events")'

    def report(self, qs, wire):
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
                return {"title": "t", "status": "ENABLED", "count": "0"}
        return form_status.form_report(glow_forms.TEMPLATE, Fake(), {})

    def test_a_form_with_both_types_is_clean(self):
        qs, wire = shaped()
        problems, summary = form_status.audit_special_events(qs, wire)
        self.assertEqual(problems, [])
        self.assertEqual(summary["listed"], {q: {WELCOME: 1, IDG: 1} for q in ("14", "92", "93")})
        self.assertTrue(form_status.special_events_line(summary).startswith(
            "2 type(s) on 3 of 3 module dropdowns; session bridge rule "))
        rep = self.report(qs, wire)
        self.assertEqual([p for p in rep["rule_problems"] if "event" in p or "bridge" in p], [])

    def test_the_live_form_lacking_the_new_type_is_not_clean_until_the_apply(self):
        qs, wire = live_state()
        problems, summary = form_status.audit_special_events(qs, wire)
        self.assertEqual(len(problems), 3)
        for qid, year, problem in zip(("14", "92", "93"), ("1", "2", "3"), problems):
            self.assertTrue(problem.startswith(f"module dropdown q{qid} (year {year}) lacks the special event "
                                               f"'{IDG}'"), problem)
            self.assertIn(self.FIX, problem)
        self.assertEqual(summary["listed"], {q: {WELCOME: 1, IDG: 0} for q in ("14", "92", "93")})
        self.assertIn("2 type(s) on 0 of 3 module dropdowns", form_status.special_events_line(summary))
        # the report: NOT CLEAN (rule problems), and the runner's verify step reads it as a problem
        rep = self.report(qs, wire)
        self.assertEqual(len([p for p in rep["rule_problems"] if IDG in p]), 3)
        clean = {"error_conditions": 0, "salesforce": True, "languages": ["a"] * 12,
                 "region_check": {"missing_from_form": [], "not_in_roster": [], "rosters_out_of_date": []}}
        verdict, _ = auto_sync.verify_report(dict(clean, rule_problems=rep["rule_problems"]))
        self.assertTrue(any("awaiting a sync apply by hand" in p for p in verdict))
        # applied (the option on every dropdown): clean again
        applied_qs, applied_wire = shaped()
        self.assertEqual([p for p in self.report(applied_qs, applied_wire)["rule_problems"]
                          if "event" in p or "bridge" in p], [])

    def test_each_dropdown_and_each_type_is_audited_on_its_own(self):
        # one dropdown lacking it: one problem, naming that dropdown
        qs, wire = shaped(q93=["Core 3", WELCOME])
        (problem,) = form_status.audit_special_events(qs, wire)[0]
        self.assertTrue(problem.startswith("module dropdown q93 (year 3) lacks the special event " + f"'{IDG}'"))
        # one lacking Welcome Session instead: that is the one named
        qs, wire = shaped(q14=["Core 1", IDG])
        (problem,) = form_status.audit_special_events(qs, wire)[0]
        self.assertTrue(problem.startswith(f"module dropdown q14 (year 1) lacks the special event '{WELCOME}'"))
        # neither type anywhere: one problem per type per dropdown
        qs, wire = shaped(q14=["Core 1"], q92=["Core 2", "Elective - Healthy GLOW"], q93=["Core 3"])
        problems = form_status.audit_special_events(qs, wire)[0]
        self.assertEqual(len(problems), 6)
        self.assertEqual(len([p for p in problems if f"'{IDG}'" in p]), 3)
        self.assertEqual(len([p for p in problems if f"'{WELCOME}'" in p]), 3)
        # the new type twice, or in another spelling, is reported like Welcome Session is
        qs, wire = shaped(q92=["Core 2", "Elective - Healthy GLOW", WELCOME, IDG, IDG])
        (problem,) = form_status.audit_special_events(qs, wire)[0]
        self.assertIn(f"lists '{IDG}' 2 times", problem)
        qs, wire = shaped(q93=["Core 3", WELCOME, IDG.lower()])
        (problem,) = form_status.audit_special_events(qs, wire)[0]
        self.assertIn(f"lists the special event as '{IDG.lower()}', not '{IDG}'", problem)

    def test_the_served_page_must_serve_the_new_option_too(self):
        qs, wire = shaped()
        r = {}
        self.assertEqual(form_status.rendered_bridge_problems(r, served_rules_and_rosters(qs, wire)), [])
        self.assertEqual(r["rendered_events"], {q: {WELCOME: (1, 1, 0), IDG: (1, 1, 0)} for q in ("14", "92", "93")})
        # a page from before the apply: Welcome Session served, the new one not
        problems = form_status.rendered_bridge_problems({}, served_rules_and_rosters(*live_state()))
        self.assertEqual(len(problems), 3)
        for qid, problem in zip(("14", "92", "93"), problems):
            self.assertIn(f"rendered page: module dropdown q{qid} serves '{IDG}' 0 time(s)", problem)


class IdgDocs(unittest.TestCase):
    """The plan beside the ticket, and the RUNBOOK's "Special events" naming both types."""

    PLAN = os.path.join(REPO, "docs", "plans", "2026-10-14-idg-celebrations.md")

    def runbook_section(self):
        doc = read(os.path.join(REPO, "docs", "RUNBOOK.md"))
        self.assertEqual(doc.count("\n## Special events\n"), 1)         # the heading is unchanged
        return doc.split("\n## Special events\n", 1)[1].split("\n## ", 1)[0]

    def test_the_runbook_status_line_names_both_types(self):
        section = self.runbook_section()
        (status,) = [l for l in section.split("\n") if l.startswith("- **Status:**")]
        for name in ("Welcome Session", "IDG Celebrations"):
            self.assertIn(name, status)
        self.assertLess(status.index("Welcome Session"), status.index("IDG Celebrations"))
        # it links this ticket's plan, and no sentence of the section still calls Welcome Session the
        # first or only type (Status line and body alike)
        self.assertIn("plans/2026-10-14-idg-celebrations.md", status)
        flat = " ".join(section.split())
        for stale in ("the first type is", "first type", "only type", "only special event"):
            self.assertNotIn(stale, flat.lower())
        # the report line it quotes is the tool's, for two types
        text = " ".join(self.runbook_section().split())
        self.assertIn("special events: 2 type(s) on 3 of 3 module dropdowns; session bridge rule N of M", text)
        self.assertNotIn("special events: 1 type(s)", " ".join(read(os.path.join(REPO, "docs", "RUNBOOK.md")).split()))

    def sections(self):
        """{heading word: body} of the plan's `## ` sections (comments removed), the plan's text."""
        text = re.sub(r"<!--.*?-->", "", read(self.PLAN), flags=re.S)          # missing file: the red state
        parts = re.split(r"^## ", text, flags=re.M)[1:]
        return {p.split("\n", 1)[0].split()[0].strip(":"): p.split("\n", 1)[1] if "\n" in p else ""
                for p in parts}, text

    def test_the_plan_carries_a_plans_frontmatter_and_says_what_it_is_about(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        sections, text = self.sections()
        keys, h1 = docs_index.frontmatter(read(self.PLAN))
        template, _ = docs_index.frontmatter(read(os.path.join(REPO, "docs", "templates", "plan.md")))
        self.assertEqual(set(template), {"title", "author", "status", "done", "backlog", "created", "intent"})
        self.assertLessEqual(set(keys), set(template))                  # no key a plan does not carry
        for key_ in ("title", "author", "status", "created", "intent"):
            self.assertTrue(keys.get(key_, "").partition("#")[0].strip(), key_)
        self.assertIn("IDG Celebrations", keys["title"])
        self.assertEqual(docs_index.status_of(keys["status"])[0], "accepted")
        self.assertRegex(keys["created"], r"^2026-10-14$")
        self.assertEqual(keys.get("backlog", "").partition("#")[0].strip(), "")      # none
        self.assertEqual(keys.get("done", "").partition("#")[0].strip(), "")         # not done until the rollout
        self.assertIn("IDG Celebrations", h1)
        self.assertIn("IDG Celebrations", " ".join(sections.values()))     # the body says it too
        self.assertIn("SPECIAL_EVENTS", text)

    def test_the_plan_has_a_real_rollout_rollback_risks_proof_and_an_empty_result(self):
        sections, text = self.sections()
        headings = [h for h in re.findall(r"^## (.+)$", text, re.M)]
        names = ("Rollout", "Rollback", "Risks", "Proof", "Result")
        for name in names:
            self.assertEqual(len([h for h in headings if h.startswith(name)]), 1, name)
        order = [next(i for i, h in enumerate(headings) if h.startswith(n)) for n in names]
        self.assertEqual(order, sorted(order))
        for name in names[:4]:                                            # real content, not one token
            self.assertGreaterEqual(len(sections[name].split()), 20, name)
        rollout, rollback = sections["Rollout"], sections["Rollback"]
        self.assertIn("AUTO_SYNC_APPLY", rollout)
        self.assertRegex(rollout, r"(?i)template")
        self.assertRegex(rollout, r"(?i)template.{0,200}first|first.{0,200}template")
        self.assertRegex(rollout, r"(?i)ryan.s go")
        self.assertIn("--apply", rollout)
        self.assertIn("form_status", rollout)
        self.assertIn("restore_conditions.py", rollback)
        self.assertRegex(rollback, r"(?i)builder")
        self.assertIn("SPECIAL_EVENTS", rollback)
        self.assertIn("Module_Week__c", sections["Risks"])
        self.assertEqual(sections["Result"].strip(), "")                  # nothing to report yet

    def test_the_plans_index_is_the_generated_one(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        plans, p1 = docs_index.entries("plans")
        intents, p2 = docs_index.entries("intent")
        self.assertEqual((p1, p2), ([], []))
        self.assertIn("2026-10-14-idg-celebrations.md", [p["name"] for p in plans])    # missing plan: red
        self.assertEqual(read(os.path.join(REPO, "docs", "plans", "README.md")), docs_index.render(plans, intents))


if __name__ == "__main__":
    unittest.main(verbosity=1)
