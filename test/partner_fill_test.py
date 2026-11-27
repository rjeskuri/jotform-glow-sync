#!/usr/bin/env python3
"""
Question 331 (Partner) filled from the Club picker (#236, the prerequisite of #225: the photo
folders are named `{Partner} | {Club Name} | {Date} | {Week}`). build_conditions' fill rules -
one calculation per partner, `picker equals <entry>` for each of its entries -> the partner's
name as text into q331, appended after every rule of today (PartnerFillRules) - and
sync_attendance_form.main() with the fill on and off, on helpers/common.py's SameNameFixture
form (PartnerFillFlow): the per-form switch --partner-fill, read back from the form's own rules
afterwards, the partner taken from the data (never split out of an entry at " - "), the refusals,
and q331 kept hidden. Fictional names.
"""
import contextlib
import io
import json
import types
import unittest
from unittest import mock

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import FakeForm, SameNameFixture
import auto_sync
import sync_attendance_form as sync

MODULES = {"1": ["Core 1"], "2": ["Core 2", "Elective - Healthy GLOW"], "3": ["Core 3"]}


def parsed(rule):
    """(terms, actions) of a rule as build_conditions returns it or as the wire carries it."""
    return tuple(json.loads(rule[k]) if isinstance(rule[k], str) else rule[k] for k in ("terms", "action"))


def writes_q331(rule):
    return any(str(a.get("resultField")) == sync.PARTNER for a in parsed(rule)[1])


def hand_fill(options, partner, picker="500", rid="9001"):
    """A calculation into q331 as a form could hold one (wire format), written out here, not by
    the sync: `options` picked on the picker -> `partner` as text."""
    terms = [{"id": f"term_90{n}", "field": picker, "operator": "equals", "value": o, "isError": False}
             for n, o in enumerate(options)]
    action = [{"id": "action_9", "resultField": sync.PARTNER, "operands": picker, "equation": partner,
               "insertAsText": True, "isError": False}]
    return {"id": rid, "type": "calculation", "link": "Any", "priority": "99", "index": "99",
            "terms": json.dumps(terms), "action": json.dumps(action)}


class FillShape:
    """fills(): the q331 rules of a rule list, their shape asserted (self is a TestCase)."""

    def fills(self, conds, picker="500"):
        """[(the partner written, [the picker entries its terms test])] of every rule that writes
        q331, in rule order. Each must be one calculation (link Any) with one action: q331 from
        the picker as text, its terms `picker equals <entry>`."""
        out = []
        for rule in conds:
            if not writes_q331(rule):
                continue
            terms, actions = parsed(rule)
            self.assertEqual((rule["type"], rule["link"]), ("calculation", "Any"), rule)
            self.assertEqual(len(actions), 1, rule)
            a = actions[0]
            self.assertEqual((str(a["resultField"]), str(a["operands"]), a["insertAsText"]),
                             (sync.PARTNER, picker, True), rule)
            self.assertEqual({(str(t["field"]), t["operator"]) for t in terms}, {(picker, "equals")}, rule)
            out.append((a["equation"], [t["value"] for t in terms]))
        return out


class PartnerFillRules(FillShape, unittest.TestCase):
    """build_conditions(..., partner_fill={qid: partner}): the fill rules' shape and place."""

    def build(self, clubs, fill="omit", partner_of=None, picker="500", options=None, guard=False,
              retired=()):
        sync._counter[0] = 0
        kw = {} if fill == "omit" else {"partner_fill": fill}
        if picker:
            kw["picker_options"] = options or sorted(set(clubs.values()), key=str.lower)
            if guard:
                kw.update(guard="700", submit="2")
        return sync.build_conditions(clubs, partner_of or {}, MODULES, picker=picker, retired=retired, **kw)

    # the three cases the ticket names, and the orders; each expectation written out by hand
    # (roster qids from 10 to 13 and from 20: 14 to 19 are the module, session and bridge fields)
    CASES = [
        ("a club with a partner",
         {"10": "Alpha Club", "11": "Beta Club", "12": "Charlie Club", "13": "Gamma Club", "20": "Kilo Club"},
         {"10": "Partner One", "11": "Partner Two", "12": "Partner One", "20": ""},   # 13, 20: no known partner
         None, (),
         [("Partner One", ["Alpha Club", "Charlie Club"]), ("Partner Two", ["Beta Club"])]),
        ("a club two partners share: each its own entry, each entry its own partner",
         {"10": "Alpha Club", "11": "Stars - Partner One", "12": "Stars - Partner Two", "13": "Beta Club"},
         {"10": "Partner One", "11": "Partner One", "12": "Partner Two", "13": "Partner Two",
          "20": "Partner Three"},                                                  # 20: a retired roster
         None, ("20",),
         [("Partner One", ["Alpha Club", "Stars - Partner One"]),
          ("Partner Two", ["Beta Club", "Stars - Partner Two"])]),
        ("a partner name containing ' - ', and a club name containing it",
         {"10": "Stars - Hope - Coast", "11": "Delta Club", "12": "Stars - Partner One",
          "13": "Alpha Club - Juniors"},
         {"10": "Hope - Coast", "11": "Hope - Coast", "12": "Partner One", "13": "Partner One"},
         None, (),
         [("Hope - Coast", ["Delta Club", "Stars - Hope - Coast"]),
          ("Partner One", ["Alpha Club - Juniors", "Stars - Partner One"])]),
        ("partners and entries sorted case-insensitively, entries in the picker's spelling",
         {"10": "bravo Club", "11": "Alpha Club", "12": "CHARLIE CLUB", "13": "Echo Club"},
         {"10": "dawn Trust", "11": "dawn Trust", "12": "dawn Trust", "13": "Partner One"},
         ["Alpha Club", "bravo Club", "Charlie Club", "Echo Club"], (),
         [("dawn Trust", ["Alpha Club", "bravo Club", "Charlie Club"]), ("Partner One", ["Echo Club"])]),
    ]

    def test_one_rule_per_partner_testing_each_of_its_picker_entries(self):
        for name, clubs, fill, options, retired, want in self.CASES:
            for guard in (False, True):
                with self.subTest(name, guard=guard):
                    conds = self.build(clubs, fill, options=options, guard=guard, retired=retired)
                    self.assertEqual(self.fills(conds), want)

    def test_every_rule_of_today_keeps_its_place_and_the_fill_comes_last(self):
        for name, clubs, fill, options, retired, want in self.CASES:
            for guard in (False, True):
                with self.subTest(name, guard=guard):
                    today = self.build(clubs, options=options, guard=guard, retired=retired)
                    conds = self.build(clubs, fill, options=options, guard=guard, retired=retired)
                    # today's rules, ids and counters included, then one fill rule per partner:
                    # the Contact_IDs sum stays rule 0, the guard's two rules stay where they were
                    self.assertEqual(conds[:len(today)], today)
                    self.assertEqual(len(conds), len(today) + len(want))
                    self.assertTrue(all(writes_q331(c) for c in conds[len(today):]))
                    self.assertFalse([c for c in today if writes_q331(c)])
                    self.assertEqual([c["index"] for c in conds], [str(i) for i in range(len(conds))])
                    self.assertEqual([c["priority"] for c in conds], [c["index"] for c in conds])
                    ids = [int(c["id"]) for c in conds]
                    self.assertEqual(ids, sorted(set(ids)))            # fresh, and in index order
                    inner = [x["id"] for c in conds for x in c["terms"] + c["action"]]
                    self.assertEqual(len(inner), len(set(inner)))

    def test_without_the_picker_or_with_the_fill_off_the_rules_are_todays_byte_for_byte(self):
        clubs, fill = self.CASES[1][1], self.CASES[1][2]
        for picker in (None, "500"):
            today = json.dumps(self.build(clubs, picker=picker))
            for off in (None, {}):
                with self.subTest(picker=picker, fill=off):
                    self.assertEqual(json.dumps(self.build(clubs, off, picker=picker)), today)
        # a form without the picker: no picker to fill from, whatever the fill holds
        none = self.build(clubs, fill, picker=None)
        self.assertEqual(json.dumps(none), json.dumps(self.build(clubs, picker=None)))
        self.assertFalse([c for c in none if writes_q331(c)])

    def test_an_entry_the_typed_box_still_tells_apart_gets_no_fill(self):
        # before --same-name-switch: two rosters on the one entry "Stars", told apart by the typed
        # Partner box. The entry cannot say whose club it is, so it fills nothing; the rest fill
        clubs = {"10": "Alpha Club", "11": "Stars", "12": "Stars", "13": "Beta Club"}
        partner_of = {"11": "Partner One", "12": "Partner Two"}
        fill = {"10": "Partner One", "11": "Partner One", "12": "Partner Two", "13": "Partner Two"}
        conds = self.build(clubs, fill, partner_of=partner_of)
        self.assertEqual(self.fills(conds), [("Partner One", ["Alpha Club"]), ("Partner Two", ["Beta Club"])])


class PartnerFillFlow(FillShape, SameNameFixture, unittest.TestCase):
    """sync_attendance_form.main() with the fill: SameNameFixture's fake Africa form (Partner One:
    Alpha Club and Stars; Partner Two: Stars and Beta Club), switched unless a test says so."""

    FILLED = [("Partner One", ["Alpha Club", "Stars - Partner One"]),
              ("Partner Two", ["Beta Club", "Stars - Partner Two"])]

    def run_sync(self, fake, *extra, **kw):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code, out = SameNameFixture.run_sync(self, fake, *extra, **kw)
        self.err = err.getvalue()
        return code, out

    def ok(self, fake, *extra, **kw):
        code, out = self.run_sync(fake, *extra, **kw)
        self.assertEqual(code, 0, self.err)
        return out

    def put(self, fake):
        """The rules the run's REPLACE conditions writes (wire format), or None without one."""
        puts = [p for m, path, p in fake.writes if (m, path) == ("PUT", "/properties")]
        self.assertLessEqual(len(puts), 1)
        return puts[0]["properties"]["conditions"] if puts else None

    # ---- the switch: --partner-fill turns it on, per form
    def test_the_flag_fills_q331_for_a_club_with_a_partner_and_a_club_two_partners_share(self):
        alone = {k: v for k, v in self.ROSTER.items() if k != ("Partner Two", "Stars")}
        for roster, want in ((self.ROSTER, self.FILLED),           # switched: Stars - <partner>
                             (alone, [("Partner One", ["Alpha Club", "Stars"]),
                                      ("Partner Two", ["Beta Club"])])):
            with self.subTest(clubs=len(roster)):
                del sync.WARNINGS[:]
                qs, wire = self.form(roster=roster, switched=True)
                fake = FakeForm(qs, wire)
                out = self.ok(fake, "--partner-fill", roster=roster)
                self.assertEqual(fake.calls, [f"REPLACE conditions ({len(wire) + len(want)} rules)"])
                conds = self.put(fake)
                self.assertEqual(self.fills(conds), want)
                # every rule the form has keeps its place (q5's copy, the q18 sum at 0, the rosters')
                self.assertEqual(sync._norm_rules(conds[:len(wire)]), sync._norm_rules(wire))
                self.assertIn(f"conditions: {len(wire)} kept, {len(want)} new, 0 dropped", out)
                self.assertEqual(sync.WARNINGS, [])
                # without the flag, on a form without the fill, it stays off: nothing at all, and
                # a rewrite for a roster change writes no rule into q331
                fake = FakeForm(qs, wire)
                self.assertEqual((self.run_sync(fake, roster=roster)[0], fake.calls), (0, []))
                changed = {**roster, ("Partner One", "Alpha Club"): ["Jane Doe"]}
                fake = FakeForm(qs, wire)
                self.ok(fake, roster=changed)
                self.assertEqual(self.fills(self.put(fake)), [])

    def test_a_partner_whose_name_holds_the_separator_comes_out_whole(self):
        roster = {("Hope - Coast", "Stars"): ["Amara Fennwhistle", "Beatrice Marrowgate"],
                  ("Hope - Coast", "Delta Club"): ["Chiara Ostrivane"],
                  ("Partner One", "Stars"): ["Dalia Pellucidor", "Esther Thornquibble"],
                  ("Partner One", "Alpha Club - Juniors"): ["Fatima Fennwhistle"],
                  ("dawn Trust", "Echo Club"): ["Grace Marrowgate"]}
        self.QIDS = {("Hope - Coast", "Stars"): "10", ("Hope - Coast", "Delta Club"): "11",
                     ("Partner One", "Stars"): "12", ("Partner One", "Alpha Club - Juniors"): "13",
                     ("dawn Trust", "Echo Club"): "20"}
        qs, wire = self.form(roster=roster, switched=True)
        fake = FakeForm(qs, wire)
        self.ok(fake, "--partner-fill", roster=roster)
        self.assertEqual(fake.calls, [f"REPLACE conditions ({len(wire) + 3} rules)"])     # the fill alone
        self.assertEqual(self.fills(self.put(fake)),
                         [("dawn Trust", ["Echo Club"]),
                          ("Hope - Coast", ["Delta Club", "Stars - Hope - Coast"]),
                          ("Partner One", ["Alpha Club - Juniors", "Stars - Partner One"])])
        self.assertEqual(sync.WARNINGS, [])

    def test_a_retired_roster_and_a_roster_with_no_known_partner_fill_nothing(self):
        # Partner Two marked jotform=no: its two rosters leave the picker, and fill nothing
        qs, wire = self.form(switched=True)
        fake = FakeForm(qs, wire)
        self.ok(fake, "--partner-fill", partners={"Partner Two": "no"})
        self.assertEqual(self.fills(self.put(fake)), [("Partner One", ["Alpha Club", "Stars - Partner One"])])
        # Beta Club on the form, not in the export: kept, its partner known to nothing - no fill
        del sync.WARNINGS[:]
        cut = {k: v for k, v in self.ROSTER.items() if k != ("Partner Two", "Beta Club")}
        fake = FakeForm(qs, wire)
        self.ok(fake, "--partner-fill", roster=cut)
        self.assertEqual(self.fills(self.put(fake)), [("Partner One", ["Alpha Club", "Stars - Partner One"]),
                                                      ("Partner Two", ["Stars - Partner Two"])])

    def test_a_partner_name_a_calculation_would_misread_fills_nothing_and_is_warned(self):
        for bad in ("Partner {Two}", "Partner [Two]", "Partner Two]", "Partner {Two"):
            with self.subTest(partner=bad):
                del sync.WARNINGS[:]
                roster = {("Partner One", "Alpha Club"): ["Jane Doe", "Mary Roe"],
                          (bad, "Beta Club"): ["Eve Hoe", "Ida Toe"],
                          ("Partner Three", "Delta Club"): ["Hana Ostrivane"]}
                self.QIDS = {("Partner One", "Alpha Club"): "10", (bad, "Beta Club"): "13",
                             ("Partner Three", "Delta Club"): "20"}
                qs, wire = self.form(roster=roster)
                fake = FakeForm(qs, wire)
                self.ok(fake, "--partner-fill", roster=roster)
                self.assertEqual(fake.calls, [f"REPLACE conditions ({len(wire) + 2} rules)"])
                self.assertEqual(self.fills(self.put(fake)), [("Partner One", ["Alpha Club"]),
                                                              ("Partner Three", ["Delta Club"])])
                self.assertTrue([w for w in sync.WARNINGS if bad in w], sync.WARNINGS)

    # ---- refusals, before any write
    def test_the_flag_needs_the_club_picker(self):
        new = {("Partner Three", "Gamma Club"): ["Amara Pellucidor"]}     # an apply would create it first
        fake = FakeForm(*self.form(picker=False), apply=True)
        code, _ = self.run_sync(fake, "--partner-fill", "--apply", roster={**self.ROSTER, **new})
        self.assertIsInstance(code, str, self.err)                        # a refusal, not argparse's 2
        self.assertIn("--partner-fill", code)
        self.assertIn("picker", code.lower())
        self.assertEqual(fake.writes, [])

    def test_rosters_still_told_apart_by_the_typed_box_stop_the_fill(self):
        new = {("Partner Three", "Gamma Club"): ["Amara Pellucidor"]}
        qs, wire = self.form()                       # before the switch: a rule shows q331
        # asked for: refused, pointing at the switch
        fake = FakeForm(qs, wire, apply=True)
        code, _ = self.run_sync(fake, "--partner-fill", "--apply", roster={**self.ROSTER, **new})
        self.assertIsInstance(code, str, self.err)
        self.assertIn("--same-name-switch", code)
        self.assertEqual(fake.writes, [])
        # with the switch in the same run no rule shows q331 any more: the fill goes on
        fake = FakeForm(qs, wire)
        self.ok(fake, "--partner-fill", "--same-name-switch")
        self.assertEqual(self.fills(self.put(fake)), self.FILLED)
        self.assertIn(self.HIDE, fake.calls)
        # recognised from the form (a calculation into q331 already there): no fill rule written,
        # the run goes on, and says so
        del sync.WARNINGS[:]
        fake = FakeForm(qs, wire + [hand_fill(["Alpha Club"], "Partner One")])
        self.ok(fake)
        conds = self.put(fake)
        self.assertIsNotNone(conds)
        self.assertEqual(self.fills(conds), [])
        self.assertTrue([w for w in sync.WARNINGS if sync.PARTNER in w], sync.WARNINGS)

    # ---- afterwards: the form's own rules keep the fill on
    def filled(self):
        """(questions, rules) of the switched form after `--partner-fill --apply`: what it wrote."""
        qs, wire = self.form(switched=True)
        fake = FakeForm(qs, wire, apply=True)
        self.ok(fake, "--partner-fill", "--apply")
        conds = self.put(fake)
        self.assertEqual(self.fills(conds), self.FILLED)
        return qs, conds

    def test_a_form_with_the_fill_keeps_it_without_the_flag_and_a_second_run_is_a_no_op(self):
        qs, conds = self.filled()
        for extra in ((), ("--partner-fill",)):
            with self.subTest(extra=extra):
                del sync.WARNINGS[:]
                fake = FakeForm(qs, conds)
                out = self.ok(fake, *extra)
                self.assertEqual(fake.calls, [])
                self.assertIn("(conditions unchanged - skipping the rewrite)", out)
                self.assertEqual(sync.WARNINGS, [])
        # a roster change rewrites the rules: the fill is in them, as it was
        fake = FakeForm(qs, conds)
        self.ok(fake, roster={**self.ROSTER, ("Partner One", "Alpha Club"): ["Jane Doe"]})
        self.assertEqual(fake.calls[0], "UPDATE roster 'Alpha Club' (q10, 1 girls)")
        self.assertEqual(sync._norm_rules(self.put(fake)), sync._norm_rules(conds))
        # a fill the form holds out of date (one entry, by hand) is put right by the next run
        qs, wire = self.form(switched=True)
        fake = FakeForm(qs, wire + [hand_fill(["Alpha Club"], "Partner One")])
        out = self.ok(fake)
        self.assertEqual(self.fills(self.put(fake)), self.FILLED)
        self.assertIn(f"conditions: {len(wire)} kept, 2 new, 1 dropped", out)

    def test_a_new_club_on_a_filled_form_joins_its_partners_rule_in_the_same_run(self):
        qs, conds = self.filled()
        sheet = {**self.ROSTER, ("Partner One", "Gamma Club"): ["Amara Pellucidor"]}
        fake = FakeForm(qs, conds, apply=True, created={"qid": 600})
        self.ok(fake, "--apply", roster=sheet)
        self.assertEqual([(m, p) for m, p, _ in fake.writes],
                         [("POST", "/questions"), ("POST", "/question/500"), ("PUT", "/properties")])
        self.assertEqual(self.fills(self.put(fake)),
                         [("Partner One", ["Alpha Club", "Gamma Club", "Stars - Partner One"]),
                          ("Partner Two", ["Beta Club", "Stars - Partner Two"])])

    # ---- q331 stays hidden
    def test_q331_stays_hidden_and_the_box_is_hidden_as_before(self):
        # a form whose box is still visible (no shared name): the fill, then the HIDE as today
        alone = {k: v for k, v in self.ROSTER.items() if k != ("Partner Two", "Stars")}
        qs, wire = self.form(roster=alone, box_hidden="No")
        fake = FakeForm(qs, wire, apply=True)
        self.ok(fake, "--partner-fill", "--apply", roster=alone)
        self.assertEqual(fake.calls, [f"REPLACE conditions ({len(wire) + 2} rules)", self.HIDE])
        self.assertEqual(fake.writes[-1], ("POST", "/question/331",
                                           {"question[hidden]": "Yes", "question[required]": "No"}))
        # a form whose box is hidden: nothing is written to q331 at all
        fake = FakeForm(*self.form(switched=True), apply=True)
        self.ok(fake, "--partner-fill", "--apply")
        self.assertEqual([p for _, p, _ in fake.writes], ["/properties"])

    # ---- the automatic runner
    def test_the_runner_never_turns_the_fill_on(self):
        # the flag is the sync's (a hand run turns the fill on)...
        fake = FakeForm(*self.form(switched=True))
        self.ok(fake, "--partner-fill")
        self.assertEqual(self.fills(self.put(fake)), self.FILLED)
        # ...and never on the runner's command line, dry run or apply
        run = auto_sync.Run(types.SimpleNamespace(apply=True, out=self.tmp.name, max_creates=5,
                                                  max_updates=20, trigger="test", run_url=""))
        run.partners = "partners.csv"
        seen = []
        with mock.patch.object(run, "cmd", lambda argv, label: seen.append(list(argv))):
            for apply in (False, True):
                run.sync("roster.csv", "Africa", "999", apply, summary_path="plan.json")
        self.assertEqual(len(seen), 2)
        self.assertEqual([a for argv in seen for a in argv if a.startswith("--partner")],
                         ["--partners", "--partners"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
