#!/usr/bin/env python3
"""
Offline tests for what sync_attendance_form.py generates and reads: the rules
(ConditionBuilder), the same-name rule (SameNameRule), question 18's Contact_IDs rule
(ContactIds), the club guard's warning (ClubGuardElement), a sync that leaves the link elements
alone (SyncLeavesTheLinksAlone), and the enrollment parser on the synthetic fixture, its numbers
pinned in test/fixtures/expected.json (EnrollmentParser). Fictional names.
"""
import copy
import json
import os
import re
import sys
import unittest

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import (AutoSyncFixture, ClubGuardFixture, FakeForm, FormStatusFixture, REPO,
                            RestoreConditionsFixture, SameNameFixture, create_at, link_form, read,
                            rendered, served_rules_and_rosters)
import auto_sync
import form_status
import restore_conditions
import sync_attendance_form as sync
from glow import layout
from glow import links
from glow import sync as glow_sync


FIXTURE = os.path.join(REPO, "test", "fixtures", "enrollment_sample.csv")
EXPECTED = os.path.join(REPO, "test", "fixtures", "expected.json")


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

    def test_an_unreadable_live_rule_is_never_the_same_and_the_rules_are_rewritten(self):
        planned = self.rules(picker="500")
        wire = [dict(c, terms=json.dumps(c["terms"]), action=json.dumps(c["action"])) for c in planned]
        self.assertTrue(sync.same_conditions(wire, planned))
        for broken in ({"terms": "{broken"}, {"terms": 5}, {"terms": "[]", "action": None},
                       {"terms": [{"field": "500"}], "action": ["Show"]}):
            with self.subTest(broken=broken):
                live = wire[:-1] + [dict(wire[-1], **broken)]
                self.assertFalse(sync.same_conditions(live, planned))
                self.assertEqual(sync.rule_delta(live, planned), (0, len(planned), 0))

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
    ROSTER, QIDS, MODULES, texts = SameNameFixture.ROSTER, SameNameFixture.QIDS, SameNameFixture.MODULES, SameNameFixture.texts

    def setUp(self):
        SameNameFixture.setUp(self)

    def tearDown(self):
        SameNameFixture.tearDown(self)

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
            return ClubGuardFixture.form(ClubGuardFixture(), **kw)

    def run_sync(self, fake, *extra, roster=None):
        return SameNameFixture.run_sync(self, fake, *extra, roster=roster)

    def summary(self, fake, *extra, **kw):
        return SameNameFixture.summary(self, fake, *extra, **kw)

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
                qs, wire = SameNameFixture.form(self, picker=False)
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
        sheet = {**ClubGuardFixture.ROSTER, ("Partner One", "Alpha Club"): ["Jane Doe", "Mary Roe", "Zoe Quillfeather"]}
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
        sheet = {**ClubGuardFixture.ROSTER, **ClubGuardFixture.NEW_CLUB}
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
        return AutoSyncFixture.run_region(self, text, apply=apply, summary=summary)

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
                typed = SameNameFixture.form(self, picker=False)
                self.assertEqual(self.audit(*typed), [], combo)

    def test_each_question_18_check_fires_on_its_broken_form(self):
        qs, wire = self.form()
        sum_rule = lambda c: '"resultField": "18"' in c["action"]

        def edit(**change):
            return FormStatusFixture.edit(wire, sum_rule, **change)

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
        gated = FormStatusFixture.edit(wire, lambda c: '"field": "10"' in c["action"],
                                     terms=lambda c: json.dumps(json.loads(c["terms"]) + [
                                         {"field": "94", "operator": "equals", "value": "1"}]))
        only(gated, "1 rule(s) that show a roster test q94, which question 18's rule does not test")
        with constants(first=False):                         # without the order: as an operand
            only(gated, "test q94, which question 18's rule does not list as an operand")
            only(FormStatusFixture.edit(gated, sum_rule, action=lambda c: c["action"].replace('"500,', '"500,94,')),
                 "test q94", n=0)
        only(FormStatusFixture.edit(gated, sum_rule, terms=lambda c: json.dumps(json.loads(c["terms"]) + [
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
        code, out, puts = RestoreConditionsFixture.run_restore(self, old, qs, "--apply")
        self.assertEqual((code, len(puts)), (0, 1))
        self.assertIn("the old way", out)


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
                                   "\u200bMaya Pellucidor\nmaya pellucidor")
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
                        "": {"count": "0", "status": "ENABLED"}}[path]

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


if __name__ == "__main__":
    unittest.main(verbosity=1)
