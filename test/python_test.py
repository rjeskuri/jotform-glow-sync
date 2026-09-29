#!/usr/bin/env python3
"""
Offline Python tests (standard library unittest; run by `make py`):

  - the auto-sync runner's decisions (plan parsing, safety bands, the
    blank-region guard, verification, redaction), on fabricated output;
  - the enrollment parser on the synthetic fixture (numbers pinned in
    test/fixtures/expected.json) and its edge cases;
  - the constants that exist in BOTH Python and appsscript/Config.gs /
    Roster.gs - form ids, qids, SESSION_OVERRIDES, SyncLog columns - so a
    change on one side fails here until the other side follows.

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
import form_status                    # noqa: E402
import rename_club                    # noqa: E402
import switcher_flags                 # noqa: E402
import update_static_fields           # noqa: E402
import worklog                        # noqa: E402
import sync_attendance_form as sync   # noqa: E402
from glow import layout               # noqa: E402
from glow import links                # noqa: E402
from glow.text import md5             # noqa: E402

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
                         "CREATE partner picker ({len(choices)} partners)",
                         "UPDATE partner picker ({len(choices)} partners: "):
            self.assertIn(fragment, joined, fragment)

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
        # list (wf/partner-box) the list is the one field added
        structural = {sync.CLUB_NAME, sync.PARTNER, sync.YEAR, sync.CONTACT_IDS, sync.MODULE_ID,
                      sync.WEEK_ID, sync.YEAR_ID, *sync.MODULES.values(), *sync.WEEKS.values()}
        for picker in (None, "500"):
            for partner_field in (sync.PARTNER, "600"):
                mentioned = set()
                for c in self.rules(picker=picker, partner_field=partner_field):
                    for item in c["terms"] + c["action"]:
                        mentioned |= {str(item[k]) for k in ("field", "resultField") if k in item}
                        mentioned |= {o for o in str(item.get("operands", "")).split(",") if o}
                        mentioned |= set(re.findall(r"\{(\d+)\}", str(item.get("equation", ""))))
                allowed = structural | {partner_field} | set(self.CLUBS) | ({picker} if picker else set())
                self.assertLessEqual(mentioned, allowed, mentioned - allowed)
                self.assertIn(partner_field, mentioned)   # the shared names really are gated


class FakeForm:
    """sync_attendance_form.Jotform stand-in: one form held in memory. Reads
    answer from it; writes are recorded (label + payload) and, with apply, a
    question create answers `created` (the new question's id, or {})."""

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
        return self.created if (method, path) == ("POST", "/questions") else {}

    def post_form(self, path, data, label):
        return self._write("POST", path, data, label)

    def put_json(self, path, payload, label):
        return self._write("PUT", path, payload, label)

    def delete(self, path, label):
        return self._write("DELETE", path, None, label)


class PartnerPickerFlow(unittest.TestCase):
    """sync_attendance_form.main() with --partner-picker and without, on a fake
    Africa form: two partners share the club name "Stars". Fictional names."""

    ROSTER = {("Partner One", "Alpha Club"): ["Jane Doe", "Mary Roe"],
              ("Partner One", "Stars"): ["Ann Poe", "Kay Loe"],
              ("Partner Two", "Stars"): ["Sue Moe", "Liz Noe"],
              ("Partner Two", "Beta Club"): ["Eve Hoe", "Ida Toe"]}
    QIDS = {("Partner One", "Alpha Club"): "10", ("Partner One", "Stars"): "11",
            ("Partner Two", "Stars"): "12", ("Partner Two", "Beta Club"): "13"}
    MODULES = {"1": "Core 1", "2": "Core 2|Elective - Healthy GLOW", "3": "Core 3"}

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        del sync.WARNINGS[:]

    def tearDown(self):
        self.tmp.cleanup()
        del sync.WARNINGS[:]

    def form(self, roster=None, partner_list=None, rules_on=None, box_hidden=None):
        """(questions, wire conditions) of a form in step with `roster`;
        partner_list: the list's options when the form has one (q600);
        rules_on: the field the live gated rules test (default: the list if any)."""
        roster = self.ROSTER if roster is None else roster
        qs = {"5": {"type": "control_textbox", "text": "Club Name", "order": "4", "hidden": "Yes"},
              "331": {"type": "control_textbox", "text": "Partner", "order": "7", "name": "partner"},
              "94": {"type": "control_dropdown", "text": "GLOW Club Year", "options": "1|2|3", "order": "9"}}
        for n, (year, mq) in enumerate(sync.MODULES.items()):
            qs[mq] = {"type": "control_dropdown", "text": "Module", "options": self.MODULES[year],
                      "order": str(10 + n)}
        for n, wq in enumerate(sync.WEEKS.values()):
            qs[wq] = {"type": "control_dropdown", "text": "Session", "order": str(13 + n)}
        for q in (sync.CONTACT_IDS, sync.MODULE_ID, sync.WEEK_ID, sync.YEAR_ID):
            qs[q] = {"type": "control_textbox", "text": "bridge", "order": "30"}
        clubs, partner_of = {}, {}
        for (partner, club), names in roster.items():
            qid = self.QIDS[(partner, club)]
            qs[qid] = {"type": "control_checkbox", "text": club, "options": "|".join(names),
                       "order": str(40 + int(qid))}
            clubs[qid] = club
            partner_of[qid] = partner
        qs["500"] = dict(sync.PICKER_PROPS, type="control_dropdown", name=sync.PICKER_NAME, order="3",
                         options="|".join(sorted(set(clubs.values()), key=str.lower)))
        if partner_list is not None:
            qs["600"] = dict(sync.PARTNER_PICKER_PROPS, type="control_dropdown",
                             name=sync.PARTNER_PICKER_NAME, order="7", options=partner_list)
            qs["331"]["hidden"] = "Yes"
        if box_hidden is not None:
            qs["331"]["hidden"] = box_hidden
        field = rules_on or ("600" if partner_list is not None else sync.PARTNER)
        modules = {y: o.split("|") for y, o in self.MODULES.items()}
        conds = sync.build_conditions(clubs, partner_of, modules, picker="500", partner_field=field)
        wire = [dict(c, terms=json.dumps(c["terms"]), action=json.dumps(c["action"])) for c in conds]
        return qs, wire

    def run_sync(self, fake, *extra, roster=None):
        import contextlib
        import io
        from unittest import mock
        roster = self.ROSTER if roster is None else roster
        path = os.path.join(self.tmp.name, "roster.csv")
        with open(path, "w", encoding="utf-8") as f:
            f.write("girl_id,partner,club,full_name,status,region\n")
            for (partner, club), names in roster.items():
                for n, name in enumerate(names):
                    f.write(f"DEMOCLUB-SAMPLE-{n:03d},{partner},{club},{name},active,Africa\n")
        argv = ["sync_attendance_form.py", path, "--roster", "--region", "Africa", "--form", "999",
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

    def test_without_the_list_nothing_changes_and_the_plan_says_why(self):
        fake = FakeForm(*self.form())
        code, out = self.run_sync(fake)
        self.assertEqual((code, fake.calls), (0, []))
        self.assertIn("nothing to do", out)
        self.assertIn("Partner box: 2 partners share club names", out)
        self.assertNotIn("Partner picker:", out)

    def test_dry_run_creates_the_list_rewrites_the_rules_then_hides_the_box(self):
        qs, wire = self.form()
        fake = FakeForm(qs, wire)
        code, out = self.run_sync(fake, "--partner-picker")
        self.assertEqual(code, 0)
        self.assertEqual(fake.calls, ["CREATE partner picker (2 partners)",
                                      f"REPLACE conditions ({len(wire) + 1} rules)",
                                      "HIDE partner textbox (q331: the partner list replaces it)"])
        self.assertIn(f"conditions: {len(wire) - 3} kept, 4 new, 3 dropped", out)   # + the q331 copy
        _, _, fields = fake.writes[0]
        self.assertEqual({k: fields[f"question[{k}]"] for k in ("type", "name", "order", "options")},
                         {"type": "control_dropdown", "name": sync.PARTNER_PICKER_NAME, "order": "7",
                          "options": "Partner One|Partner Two"})
        for k, v in sync.PARTNER_PICKER_PROPS.items():
            self.assertEqual(fields[f"question[{k}]"], v, k)

    def test_apply_points_the_rules_at_the_new_list_and_hides_the_box_last(self):
        qs, wire = self.form()
        fake = FakeForm(qs, wire, apply=True)
        summary = os.path.join(self.tmp.name, "plan.json")
        code, _ = self.run_sync(fake, "--partner-picker", "--apply", "--summary-json", summary)
        self.assertEqual(code, 0)
        self.assertEqual([(m, p) for m, p, _ in fake.writes],
                         [("POST", "/questions"), ("PUT", "/properties"), ("POST", "/question/331")])
        self.assertEqual(fake.writes[2][2], {"question[hidden]": "Yes", "question[required]": "No"})
        conds = fake.writes[1][2]["properties"]["conditions"]
        self.assertEqual(len(conds), len(wire) + 1)
        terms = [t for c in conds for t in json.loads(c["terms"])]
        actions = [a for c in conds for a in json.loads(c["action"])]
        self.assertFalse([t for t in terms if t["field"] == sync.PARTNER])
        self.assertFalse([a for a in actions if a.get("field") == sync.PARTNER])
        self.assertEqual(sorted(t["value"] for t in terms if t["field"] == "600" and t["operator"] == "equals"),
                         ["Partner One", "Partner Two"])
        # question 5 is still filled from the Club picker, exactly as before
        copy = [a for a in actions if a.get("resultField") == sync.CLUB_NAME]
        self.assertEqual([(a["equation"], a["operands"]) for a in copy], [("{500}", "500")])
        # and the chosen partner reaches the hidden q331, which the staff e-mail's Partner row reads
        copy = [a for a in actions if a.get("resultField") == sync.PARTNER]
        self.assertEqual([(a["equation"], a["operands"]) for a in copy], [("{600}", "600")])
        with open(summary, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["partner_picker"], "600")

    def test_a_create_without_a_question_id_keeps_this_run_on_the_typed_box(self):
        qs, wire = self.form()
        fake = FakeForm(qs, wire, apply=True, created={})
        code, out = self.run_sync(fake, "--partner-picker", "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(fake.calls, ["CREATE partner picker (2 partners)"])   # rules unchanged, box stays
        self.assertTrue(any("carried no question id" in w for w in sync.WARNINGS))

    def test_a_form_with_the_list_in_step_needs_nothing(self):
        fake = FakeForm(*self.form(partner_list="Partner One|Partner Two"))
        code, out = self.run_sync(fake)
        self.assertEqual((code, fake.calls), (0, []))
        self.assertIn("Partner picker: q600", out)
        self.assertNotIn("Partner box:", out)
        code, out = self.run_sync(fake, "--partner-picker")
        self.assertEqual((code, fake.calls), (0, []))
        self.assertIn("--partner-picker is not needed", out)

    def test_the_list_is_kept_in_shape_and_the_box_kept_hidden(self):
        fake = FakeForm(*self.form(partner_list="Old Partner|Partner One"))
        self.run_sync(fake)
        self.assertEqual(fake.calls, ["UPDATE partner picker (2 partners: options)"])
        self.assertEqual(fake.writes[0][2], {"question[options]": "Partner One|Partner Two"})
        qs, wire = self.form(partner_list="Partner One|Partner Two", box_hidden="No")
        qs["600"]["required"] = "No"
        fake = FakeForm(qs, wire)
        self.run_sync(fake)
        self.assertEqual(fake.calls, ["UPDATE partner picker (2 partners: required)",
                                      "HIDE partner textbox (q331: the partner list replaces it)"])

    def test_rules_left_on_the_typed_box_are_read_back_and_moved_to_the_list(self):
        # a run that created the list but failed before the rules write
        fake = FakeForm(*self.form(partner_list="Partner One|Partner Two", rules_on=sync.PARTNER,
                                   box_hidden="No"))
        code, out = self.run_sync(fake)
        self.assertEqual(code, 0)
        self.assertEqual([c.split(" (")[0] for c in fake.calls],
                         ["REPLACE conditions", "HIDE partner textbox"])
        self.assertIn("conditions: ", out)
        self.assertEqual(sync.WARNINGS, [])        # every roster matched its partner: no new roster

    def test_the_partner_is_read_back_from_rules_on_the_list(self):
        # Partner Two's Stars gets an all-new roster: only the partner in the live
        # rules (on the list) ties it to its question - roster overlap cannot
        sheet = {**self.ROSTER, ("Partner Two", "Stars"): ["Uma Zoe", "Val Yoe"]}
        for kw in ({"partner_list": "Partner One|Partner Two"}, {}):
            fake = FakeForm(*self.form(**kw))
            code, _ = self.run_sync(fake, roster=sheet)
            self.assertEqual(code, 0)
            self.assertEqual(fake.calls[0], "UPDATE roster 'Stars' (q12, 2 girls)", kw)
            self.assertFalse([c for c in fake.calls if c.startswith("CREATE roster")], kw)
            del sync.WARNINGS[:]

    def test_refuses_before_any_write_when_no_name_is_shared(self):
        on_form = {k: v for k, v in self.ROSTER.items() if k != ("Partner Two", "Stars")}
        fake = FakeForm(*self.form(roster=on_form), apply=True)
        # the sheet also has a new club, which an apply would otherwise create first
        sheet = {**on_form, ("Partner Two", "Gamma Club"): ["Sue Moe", "Liz Noe"]}
        code, _ = self.run_sync(fake, "--partner-picker", "--apply", roster=sheet)
        self.assertIn("nothing to choose", str(code))
        self.assertEqual(fake.writes, [])
        code, _ = self.run_sync(FakeForm(*self.form(roster=on_form)), roster=sheet)
        self.assertEqual(code, 0)                    # without the flag the same sheet syncs as ever

    def test_without_submit_or_a_link_a_new_roster_still_goes_at_the_end(self):
        qs, wire = self.form()
        sheet = {**self.ROSTER, ("Partner Two", "Gamma Club"): ["Uma Zoe"]}
        fake = FakeForm(qs, wire)
        code, out = self.run_sync(fake, roster=sheet)
        self.assertEqual(code, 0)
        self.assertEqual(fake.calls[0], "CREATE roster 'Gamma Club' (1 girls)")
        end = max(int(q["order"]) for q in qs.values()) + 1
        self.assertEqual(fake.writes[0][2]["question[order]"], str(end))
        self.assertIn(f"New rosters go at order {end}, the end of the form", out)

    def test_refuses_before_any_write_a_partner_name_with_the_option_separator(self):
        roster = dict(self.ROSTER)
        roster[("Partner|Two", "Stars")] = roster.pop(("Partner Two", "Stars"))
        self.QIDS = {**self.QIDS, ("Partner|Two", "Stars"): "12"}
        fake = FakeForm(*self.form(roster=roster), apply=True)
        code, _ = self.run_sync(fake, "--partner-picker", "--apply", roster=roster)
        self.assertIn("option separator", str(code))
        self.assertEqual(fake.writes, [])


class PartnerListRunbook(unittest.TestCase):
    """docs/RUNBOOK.md "The partner list": the rollback restores a snapshot the
    procedure itself takes, with the runner paused first."""

    def section(self):
        doc = read(os.path.join(REPO, "docs", "RUNBOOK.md"))
        section = doc.split("## The partner list", 1)[1].split("\n## ", 1)[0]
        self.assertIn("backup_forms.py --form", section)       # the procedure's backup
        return section

    def rollback(self):
        return self.section().split("Rollback, per form", 1)[1]

    def forward(self):
        return self.section().split("Rollback, per form", 1)[0]

    def test_the_forward_path_switches_the_runner_back_on_after_the_browser_check(self):
        # paused for the window; left paused, roster changes stop reaching the forms
        # (integration review, rollout-safety F3)
        text = self.forward()
        self.assertIn("AUTO_SYNC_APPLY=0", text)
        self.assertIn("AUTO_SYNC_APPLY=1", text)
        self.assertLess(text.index("5. Submit a test"), text.index("AUTO_SYNC_APPLY=1"))
        backlog = [l for l in read(os.path.join(REPO, "docs", "BACKLOG.md")).splitlines()
                   if l.startswith("| 45 |")]
        self.assertEqual(len(backlog), 1)
        self.assertIn("then `AUTO_SYNC_APPLY=1`", backlog[0])

    def test_the_translation_audit_is_read_before_and_after_the_apply(self):
        block = self.forward().split("```bash", 1)[1].split("```", 1)[0]
        lines = [l for l in block.splitlines() if l.strip()]
        audits = [i for i, l in enumerate(lines) if "add_translations.py --audit" in l]
        apply = next(i for i, l in enumerate(lines) if "--partner-picker --apply" in l)
        self.assertEqual(len(audits), 2)
        self.assertLess(audits[0], apply)
        self.assertGreater(audits[1], apply)

    def test_the_rollback_restores_a_file_backup_forms_writes(self):
        # backup_forms.py writes questions-/properties-<stamp>.json; only the
        # runner (in the Actions workspace) writes conditions-<stamp>.json
        self.assertIn('for part in ("questions", "properties")', read(os.path.join(REPO, "backup_forms.py")))
        sources = re.findall(r"restore_conditions\.py[^`]*--from ([\w.<>-]+)", self.rollback())
        self.assertTrue(sources)
        for src in sources:
            self.assertRegex(src, r"^properties-<stamp>\.json$")

    def test_the_rollback_pauses_the_runner_before_the_first_write(self):
        # a runner apply in the middle would move the rules back onto the list
        # and hide q331 again (PartnerPickerFlow, rules left on the typed box)
        text = self.rollback()
        self.assertIn("AUTO_SYNC_APPLY=0", text)
        self.assertLess(text.index("AUTO_SYNC_APPLY=0"), text.index("restore_conditions.py"))
        self.assertIn("AUTO_SYNC_APPLY=1", text)


class FormStatusAudit(unittest.TestCase):
    """tools/form_status.py audit_rules on forms built by the sync's own rules."""

    def form(self, **kw):
        return PartnerPickerFlow.form(PartnerPickerFlow(), **kw)

    def test_the_typed_box_form_is_clean(self):
        problems, summary = form_status.audit_rules(*self.form())
        self.assertEqual(problems, [])
        self.assertEqual(summary["clubs"], 4)

    def test_the_partner_list_form_is_clean(self):
        qs, wire = self.form(partner_list="Partner One|Partner Two")
        self.assertEqual(form_status.audit_rules(qs, wire), ([], {"clubs": 4, "show_rules": 4,
                                                                  "aggregate_rosters": 4}))

    def test_the_partner_list_checks(self):
        # rules still on the typed box while the list exists, and the box visible
        qs, wire = self.form(partner_list="Partner One|Partner Two", rules_on=sync.PARTNER,
                             box_hidden="No")
        problems, _ = form_status.audit_rules(qs, wire)
        self.assertEqual(sum("not the partner list (q600)" in p for p in problems), 2)
        self.assertTrue(any("typed Partner box (q331) is still visible" in p for p in problems))
        # a tested partner missing from the list, one listed that no rule tests, not required
        qs, wire = self.form(partner_list="Partner One|Someone Else")
        qs["600"]["required"] = "No"
        problems, _ = form_status.audit_rules(qs, wire)
        self.assertTrue(any("misses 1 partner(s) a rule tests: ['Partner Two']" in p for p in problems))
        self.assertTrue(any("offers 1 partner(s) no rule tests: ['Someone Else']" in p for p in problems))
        self.assertTrue(any("(q600) is not required" in p for p in problems))
        self.assertEqual(len(problems), 3)
        # an unshared name with a Partner term on the list is still flagged as before
        qs, wire = self.form(partner_list="Partner One|Partner Two")
        wire = [dict(c) for c in wire]
        for c in wire:
            if '"field": "10"' in c["action"]:
                c["terms"] = json.dumps([{"field": "600", "operator": "equals", "value": "Partner One"},
                                         {"field": "500", "operator": "equals", "value": "Alpha Club"}])
        problems, _ = form_status.audit_rules(qs, wire)
        self.assertEqual(problems, ["'Alpha Club' (q10) is unique but its rule needs a Partner"])

    @staticmethod
    def reveals(c, field):
        return any(a.get("visibility") == "Show" and str(a.get("field")) == field
                   for a in json.loads(c["action"]))

    def test_the_partner_list_is_hidden_and_shown_only_for_shared_names(self):
        # (a) the list visible to everyone: every mentor must pick a partner to submit
        qs, wire = self.form(partner_list="Partner One|Partner Two")
        qs["600"]["hidden"] = "No"
        self.assertEqual(form_status.audit_rules(qs, wire)[0],
                         ["partner list (q600) is not hidden: every mentor is asked for a partner"])
        # (b) nothing shows the list for "Stars": its two rosters can never appear
        qs, wire = self.form(partner_list="Partner One|Partner Two")
        wire = [c for c in wire if not self.reveals(c, "600")]
        self.assertEqual(form_status.audit_rules(qs, wire)[0],
                         ["'Stars' is shared, but no rule shows the partner list (q600) for it"])
        # (c) the rule shows the hidden typed box instead of the list
        qs, wire = self.form(partner_list="Partner One|Partner Two")
        wire = [dict(c, action=c["action"].replace('"600"', '"331"')) if self.reveals(c, "600") else c
                for c in wire]
        problems, _ = form_status.audit_rules(qs, wire)
        self.assertEqual(len(problems), 2, problems)
        self.assertIn("'Stars' is shared, but no rule shows the partner list (q600) for it", problems)
        self.assertTrue(any("show the typed Partner box (q331)" in p for p in problems), problems)
        # (d) the list shown for a name no two rosters share: that mentor must pick a partner
        qs, wire = self.form(partner_list="Partner One|Partner Two")
        wire = wire + [dict(c, terms=c["terms"].replace('"Stars"', '"Alpha Club"'))
                       for c in wire if self.reveals(c, "600")]
        self.assertEqual(form_status.audit_rules(qs, wire)[0],
                         ["the partner list (q600) is shown for 'Alpha Club', which no two rosters share"])
        # a form without the list is audited exactly as before, whatever shows q331
        qs, wire = self.form()
        self.assertEqual(form_status.audit_rules(qs, wire)[0], [])


class TranslationAudit(unittest.TestCase):
    """tools/add_translations.py: what counts as a string a mentor sees."""

    def test_partner_names_are_not_strings_to_translate(self):
        import add_translations
        qs, _ = PartnerPickerFlow.form(PartnerPickerFlow(), partner_list="Partner One|Partner Two")
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

    def fake(self, outputs):
        """subprocess.run replacement yielding the given stdout strings in order."""
        import subprocess as sp

        def runner(argv, capture_output=True, text=True):
            self.spawned.append(argv)
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
                         "Roster tab columns", "SyncLog columns"):
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
        qs = {"352": {"type": "control_checkbox", "text": "Sunrise Club"},
              "353": {"type": "control_checkbox", "text": "New Name"}}
        self.assertEqual(rename_club.form_questions(Client(qs), "1", "sunrise club", "New Name"),
                         (["352"], ["353"], {sync.PARTNER}))
        qs["600"] = {"type": "control_dropdown", "name": sync.PARTNER_PICKER_NAME}
        self.assertEqual(rename_club.form_questions(Client(qs), "1", "Sunrise Club", "x")[2],
                         {sync.PARTNER, "600"})

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

    def run_main(self, argv, sheet, client=None, key=None):
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
                mock.patch.object(rename_club, "Client", lambda api_key, apply=False: client), \
                mock.patch.dict(os.environ, env), \
                mock.patch.object(sys, "argv", ["rename_club.py"] + argv), \
                contextlib.redirect_stdout(out):
            try:
                rename_club.main()
                code = 0
            except SystemExit as e:
                code = e.code
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
        # no Submit and no link (the PartnerPickerFlow form): the end of the form, as before
        pp, _ = PartnerPickerFlow.form(PartnerPickerFlow())
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


class WorkLog(unittest.TestCase):
    """tools/worklog.py: hours from session transcripts, the log, the invoice (synthetic data)."""
    TZ = __import__("datetime").timezone(__import__("datetime").timedelta(hours=8))

    def at(self, hhmm, day="2026-09-26"):
        import datetime as dt
        return dt.datetime.fromisoformat(f"{day}T{hhmm}:00").replace(tzinfo=self.TZ)

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
        blocks = worklog.day_blocks(evts)
        day = at("09:00").date()
        self.assertEqual(worklog.blocks_text(blocks[day]), "09:00-09:45, 14:00-14:10")
        self.assertEqual(worklog.day_hours(blocks[day]), 1.0)          # 55 min -> 1.00
        # stricter gap: 09:20 is 20 min on, so the 09:00 block is that message alone, and the
        # 09:20-09:45 stretch has no message of Ryan's: not billed
        self.assertEqual(worklog.day_blocks(evts, gap_minutes=15)[day][0], (at("09:00"), at("09:00")))

    def test_concurrent_sessions_count_once_and_days_split(self):
        at = self.at
        one = [(at("10:00"), True), (at("10:40"), False)]
        two = [(at("10:05"), True), (at("10:30"), False)]                   # a second open session
        blocks = worklog.day_blocks(sorted(one + two))
        self.assertEqual(worklog.day_hours(blocks[at("10:00").date()]), 0.75)   # 40 min, not 65
        late = [(at("23:50"), True), (at("00:20", "2026-09-27"), False)]
        split = worklog.day_blocks(late)
        self.assertEqual(sorted(d.isoformat() for d in split), ["2026-09-26"])  # 09-27 has no message of Ryan's

    def test_rounding(self):
        at = self.at
        self.assertEqual(worklog.day_hours([(at("09:00"), at("09:07"))]), 0.25)    # a day with work: at least 0.25
        self.assertEqual(worklog.day_hours([(at("09:00"), at("09:52"))]), 0.75)    # 52 -> 0.75
        self.assertEqual(worklog.day_hours([(at("09:00"), at("09:53"))]), 1.0)     # 53 -> 1.00 (half up)

    def test_events_read_transcripts_in_local_time(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.jsonl")
            with open(path, "w") as fh:
                for e in [self.entry("user", "2026-09-26T01:00:00.000Z", "Start"),
                          self.entry("assistant", "2026-09-26T01:30:00.000Z"),
                          {"type": "summary"}]:
                    fh.write(json.dumps(e) + "\n")
                fh.write("not json\n")
            evts = worklog.events([path])
        self.assertEqual(len(evts), 2)
        self.assertTrue(evts[0][1] and not evts[1][1])
        self.assertEqual(evts[1][0] - evts[0][0], __import__("datetime").timedelta(minutes=30))

    def test_merge_keeps_manual_rows_and_written_descriptions(self):
        rows = [{"date": "2026-09-25", "hours": "2.00", "blocks": "x", "description": "Curated text", "source": "auto"},
                {"date": "2026-09-25", "hours": "1.00", "blocks": "", "description": "Call", "source": "manual"},
                {"date": "2026-08-30", "hours": "3.00", "blocks": "y", "description": "Old", "source": "auto"}]
        computed = {"2026-09-25": (2.5, "09:00-11:30"), "2026-09-26": (1.0, "10:00-11:00")}
        subjects = {"2026-09-26": ["Second commit", "First commit"]}
        out = worklog.merge(rows, computed, subjects)
        by = {(r["date"], r["source"]): r for r in out}
        self.assertEqual(by[("2026-09-25", "auto")]["hours"], "2.50")
        self.assertEqual(by[("2026-09-25", "auto")]["description"], "Curated text")
        self.assertEqual(by[("2026-09-25", "manual")]["hours"], "1.00")
        self.assertEqual(by[("2026-09-26", "auto")]["description"], "First commit; Second commit")
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
                     "description": 'Commas, "quotes"\nand a newline', "source": "auto"}]
            worklog.write_log(rows, path)
            self.assertEqual(worklog.read_log(path), rows)

    def test_transcripts_dir(self):
        repo = os.sep + os.path.join("srv", "jotform-glow-sync")          # built, not a literal path
        self.assertTrue(worklog.transcripts_dir(repo).endswith(
            os.path.join(".claude", "projects", "-srv-jotform-glow-sync")))


if __name__ == "__main__":
    unittest.main(verbosity=1)
