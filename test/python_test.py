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
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import auto_sync                      # noqa: E402
import form_status                    # noqa: E402
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


if __name__ == "__main__":
    unittest.main(verbosity=1)
