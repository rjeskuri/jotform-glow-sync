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
import sync_attendance_form as sync   # noqa: E402
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
                         "UPDATE club picker ({len(picker_names)} clubs: "):
            self.assertIn(fragment, joined, fragment)

    def test_picker_shape_is_the_searchable_component(self):
        self.assertEqual(sync.PICKER_PROPS["multipleSelections"], "Yes")   # Jotform's type-to-filter dropdown
        self.assertEqual(sync.PICKER_PROPS["required"], "Yes")
        self.assertNotIn("on a computer", sync.PICKER_PROPS["subLabel"])
        # the label and sublabel must have translations queued for the rollout
        additions = json.loads(read(os.path.join(REPO, "tools", "translations_additions.json")))
        self.assertIn(sync.PICKER_TEXT, additions)
        self.assertIn(sync.PICKER_SUBLABEL, additions)


class ConditionBuilder(unittest.TestCase):
    CLUBS = {"10": "Alpha Club", "11": "Stars", "12": "Stars", "13": "Beta Club"}
    PARTNERS = {"11": "Partner One", "12": "Partner Two"}
    MODULES = {"1": ["Core 1"], "2": ["Core 2", "Elective - Healthy GLOW"], "3": ["Core 3"]}

    def rules(self, picker=None):
        sync._counter[0] = 0
        return sync.build_conditions(self.CLUBS, self.PARTNERS, self.MODULES, picker=picker)

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

    def test_generated_rules_mention_only_rosters_and_structural_fields(self):
        # so no other element - the links above Submit included - is ever
        # shown, hidden or computed by the sync's rewrite
        structural = {sync.CLUB_NAME, sync.PARTNER, sync.YEAR, sync.CONTACT_IDS, sync.MODULE_ID,
                      sync.WEEK_ID, sync.YEAR_ID, *sync.MODULES.values(), *sync.WEEKS.values()}
        for picker in (None, "500"):
            mentioned = set()
            for c in self.rules(picker=picker):
                for item in c["terms"] + c["action"]:
                    mentioned |= {str(item[k]) for k in ("field", "resultField") if k in item}
                    mentioned |= {o for o in str(item.get("operands", "")).split(",") if o}
                    mentioned |= set(re.findall(r"\{(\d+)\}", str(item.get("equation", ""))))
            allowed = structural | set(self.CLUBS) | ({picker} if picker else set())
            self.assertLessEqual(mentioned, allowed, mentioned - allowed)


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
        self.assertIn("typed Partner", str(code))
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

    def run_main(self, fake, *argv):
        import contextlib
        import io
        from unittest import mock
        snaps, out = [], io.StringIO()
        with mock.patch.object(add_feedback_link, "Client", lambda key, apply=False: fake), \
                mock.patch.object(add_feedback_link, "snapshot", lambda fid, c, stamp: snaps.append(fid)), \
                mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}), \
                mock.patch.object(sys, "argv", ["add_feedback_link.py", *argv]), \
                contextlib.redirect_stdout(out):
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


class SyncLeavesTheLinksAlone(unittest.TestCase):
    """sync_attendance_form.py end to end (dry run, fake Jotform): the link
    elements are neither written nor mentioned by any generated rule."""

    def test_a_sync_run_never_touches_or_gates_the_link_elements(self):
        import contextlib
        import csv
        import io
        import tempfile
        from unittest import mock
        qs = link_form(roster=True)
        seen = {}

        class FakeForm:
            def __init__(self, api_key, form_id, apply_changes=False):
                self.calls, self.paths = [], []
                seen["form"] = self

            def get(self, path):
                return {"/questions": copy.deepcopy(qs), "/properties": {"conditions": []},
                        "": {"count": "0"}}[path]

            def post_form(self, path, data, label):
                self.calls.append(label)
                self.paths.append(path)

            def put_json(self, path, payload, label):
                self.calls.append(label)
                self.paths.append(path)
                seen["conditions"] = payload["properties"]["conditions"]

            def delete(self, path, label):
                self.calls.append(label)
                self.paths.append(path)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "roster.csv")
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["girl_id", "partner", "club", "full_name", "status", "region"])
                for i, (partner, club, name) in enumerate((
                        ("Partner A", "Sunrise Club", "Girl One"), ("Partner A", "Sunrise Club", "Girl Two"),
                        ("Partner A", "Sunrise Club", "Girl Four"), ("Partner A", "Moonrise Club", "Girl Three"),
                        ("Partner B", "Starlight Club", "Girl Five")), 1):
                    w.writerow([f"DEMOCLUB-SAMPLE-{i:03d}", partner, club, name, "active", "Africa"])
            with mock.patch.object(sync, "Jotform", FakeForm), \
                    mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}), \
                    mock.patch.object(sys, "argv", ["sync_attendance_form.py", path, "--roster",
                                                    "--region", "Africa", "--form", "999"]), \
                    contextlib.redirect_stdout(io.StringIO()):
                sync.main()
        form = seen["form"]
        self.assertTrue(any(c.startswith("CREATE roster 'Starlight Club'") for c in form.calls), form.calls)
        self.assertTrue(any(c.startswith("UPDATE roster 'Sunrise Club'") for c in form.calls), form.calls)
        self.assertTrue(any(c.startswith("REPLACE conditions") for c in form.calls), form.calls)
        for qid in ("460", "443"):
            self.assertFalse([p for p in form.paths if p.rstrip("/").endswith(f"/{qid}")], qid)
            self.assertEqual(links.rules_mentioning(seen["conditions"], qid), [], qid)


if __name__ == "__main__":
    unittest.main(verbosity=1)
