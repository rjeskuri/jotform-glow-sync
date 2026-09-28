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
import json
import os
import re
import struct
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import auto_sync                      # noqa: E402
import form_status                    # noqa: E402
import rename_club                    # noqa: E402
import switcher_flags                 # noqa: E402
import update_static_fields           # noqa: E402
import sync_attendance_form as sync   # noqa: E402

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

    def test_the_partner_list_changes_only_the_partner_field(self):
        typed = self.rules(picker="500")
        listed = self.rules(picker="500", partner_field="600")
        self.assertEqual(len(listed), len(typed))           # same rule count
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
        self.assertEqual(sync.rule_delta(wire, listed), (len(typed) - 3, 3, 3))
        self.assertEqual(sync.rule_delta([], listed), (0, len(listed), 0))
        self.assertEqual(sync.rule_delta([{"terms": "{broken"}], listed), (0, len(listed), 0))


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
                                      f"REPLACE conditions ({len(wire)} rules)",
                                      "HIDE partner textbox (q331: the partner list replaces it)"])
        self.assertIn(f"conditions: {len(wire) - 3} kept, 3 new, 3 dropped", out)
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
        self.assertEqual(len(conds), len(wire))
        terms = [t for c in conds for t in json.loads(c["terms"])]
        actions = [a for c in conds for a in json.loads(c["action"])]
        self.assertFalse([t for t in terms if t["field"] == sync.PARTNER])
        self.assertFalse([a for a in actions if a.get("field") == sync.PARTNER])
        self.assertEqual(sorted(t["value"] for t in terms if t["field"] == "600"),
                         ["Partner One", "Partner Two"])
        # question 5 is still filled from the Club picker, exactly as before
        copy = [a for a in actions if a.get("resultField") == sync.CLUB_NAME]
        self.assertEqual([(a["equation"], a["operands"]) for a in copy], [("{500}", "500")])
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

    def test_refuses_before_any_write_a_partner_name_with_the_option_separator(self):
        roster = dict(self.ROSTER)
        roster[("Partner|Two", "Stars")] = roster.pop(("Partner Two", "Stars"))
        self.QIDS = {**self.QIDS, ("Partner|Two", "Stars"): "12"}
        fake = FakeForm(*self.form(roster=roster), apply=True)
        code, _ = self.run_sync(fake, "--partner-picker", "--apply", roster=roster)
        self.assertIn("option separator", str(code))
        self.assertEqual(fake.writes, [])


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
    """The two GETs a move makes; q352 is the club's roster, q444 the picker."""

    def __init__(self, gated=False):
        self.gated = gated

    def get(self, path, **params):
        if path.endswith("/questions"):
            return {"352": {"type": "control_checkbox", "text": "Sunrise Club"},
                    "444": {"type": "control_dropdown", "text": "Club Name"}}
        terms = [{"field": "444", "operator": "equals", "value": "Sunrise Club"}]
        if self.gated:
            terms.insert(0, {"field": sync.PARTNER, "operator": "equals", "value": "asoc demo"})
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
        code, out = self.run_main(self.MOVE + ["--apply"], sheet, FakeJotform(gated=True), key="test")
        self.assertIn("given Partner", str(code))
        self.assertEqual(sheet.batches, [])
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


if __name__ == "__main__":
    unittest.main(verbosity=1)
