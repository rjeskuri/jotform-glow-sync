#!/usr/bin/env python3
"""
The club and form tools on in-memory sheets and fake forms: tools/rename_club.py (RenameClub),
deactivate_clubs.py (DeactivateClubs), disable_form.py (DisableForm), upload_roster.py's
partners merge (UploadRosterPartners) and switcher_flags.py (SwitcherFlags). Fictional names.
"""
import copy
import json
import os
import re
import sys
import unittest

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import REPO
import deactivate_clubs
import disable_form
import rename_club
import sheets_client
import switcher_flags
import sync_attendance_form as sync
import upload_roster
from glow import forms as glow_forms
from glow import text as glow_text


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
    gated: its rule tests the typed Partner box (q331)."""

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
        # the sheet-cell helpers live in tools/sheets_client.py (rename_club and
        # deactivate_clubs import them)
        sc = sheets_client
        self.assertEqual([sc.col_letter(i) for i in (0, 2, 25, 26, 27)],
                         ["A", "C", "Z", "AA", "AB"])
        self.assertEqual(sc.describe_rows([]), "no rows")
        self.assertEqual(sc.describe_rows([7]), "row 7")
        self.assertEqual(sc.describe_rows([3, 4, 5]), "rows 3-5")
        self.assertEqual(sc.describe_rows([3, 5]), "rows 3, 5")
        self.assertEqual(sc.a1("SF Pending", "C4"), "'SF Pending'!C4")
        self.assertEqual(sc.a1("Club's Tab"), "'Club''s Tab'")             # a whole tab, the quote doubled
        self.assertEqual((sc.cell(["a", "b"], 1), sc.cell(["a"], 3), sc.cell(["a"], None)), ("b", "", ""))
        self.assertEqual(sc.trimmed(["a", "", "b", "", ""]), ["a", "", "b"])
        self.assertIs(rename_club.describe_rows, sc.describe_rows)

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
        t = glow_text          # tidy / cell_key / nfc_key live in glow/text.py beside key
        self.assertEqual(t.cell_key(" Asoc\u200b  Demo\ufeff "), "asoc demo")
        self.assertEqual(t.tidy("a\u2060b  c "), "ab c")
        # key_ folds neither accents nor Unicode form; nfc_key only fixes the form
        self.assertNotEqual(t.cell_key("Asociación"), t.cell_key("Asociacion"))
        self.assertNotEqual(t.cell_key("Asociación"), t.cell_key("Asociacio\u0301n"))
        self.assertEqual(t.nfc_key("Asociación"), t.nfc_key("Asociacio\u0301n"))
        # ...and glow.text.key keeps the invisible characters (BACKLOG 28)
        self.assertNotEqual(t.key(" Asoc\u200b  Demo "), t.cell_key(" Asoc\u200b  Demo "))

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
        # a term on any other field is no Partner term (the retired partner list's q600 included)
        listed = dict(gated, id="5", terms=[dict(gated["terms"][0], field="600"), gated["terms"][1]])
        self.assertEqual(rename_club.partner_gated([plain, listed], {"352"}), [])

    def test_form_questions_finds_the_rosters_by_name(self):
        class Client:
            def __init__(self, qs):
                self.qs = qs

            def get(self, path, **params):
                return self.qs
        qs = {"352": {"type": "control_checkbox", "text": "Sunrise Club", "options": "A Girl|B  Girl"},
              "353": {"type": "control_checkbox", "text": "New Name"}}
        self.assertEqual(rename_club.form_questions(Client(qs), "1", "sunrise club", "New Name"),
                         (["352"], ["353"], {"352": {"a girl", "b girl"}}))
        self.assertEqual(rename_club.form_questions(Client(qs), "1", "Sunrise Club", "x"),
                         (["352"], [], {"352": {"a girl", "b girl"}}))

    # --- renaming a club the sync did not add (its name was another partner's club's) ---
    def stars_sheet(self):
        """Partner One's Stars is on the forms (q352, its two girls); Partner Three's new
        Stars is in the Roster and the registry, and on no form: the sync refused it."""
        return FakeSheet({
            "Roster": [self.HDR,
                       ["DEMOCLUB-SAMPLE-001", "Partner One", "Stars", "Africa", "Ann Poe", "active"],
                       ["DEMOCLUB-SAMPLE-002", "Partner One", "Stars", "Africa", "Kay Loe", "active"],
                       ["DEMOCLUB-SAMPLE-003", "Partner One", "Stars", "Africa", "Sue Moe", "inactive"],
                       ["SUNRISEC-SAMPLE-001", "Partner Three", "Stars", "Africa", "Uma Umberlash", "active"],
                       ["SUNRISEC-SAMPLE-002", "Partner Three", "Stars", "Africa", "Ann Poe", "active"]],
            "ClubRegistry": [["club_code", "partner", "club", "created"],
                             ["STARS", "Partner One", "Stars", "2026-08-26"],
                             ["STARS2", "Partner Three", "Stars", "2026-09-30"]],
            "SF Pending": [["added", "partner", "club", "region"],
                           ["2026-09-30", "Partner Three", "Stars", "Africa"]],
            "Audit": [["when", "action", "detail"]],
        })

    class StarsForms:
        """Both forms hold one roster question named Stars: Partner One's."""

        def __init__(self, options="Ann Poe|Kay Loe|Sue Moe"):
            self.options, self.gets, self.posts = options, [], []

        def get(self, path, **params):
            self.gets.append(path)
            return {"352": {"type": "control_checkbox", "text": "Stars", "options": self.options},
                    "444": {"type": "control_dropdown", "text": "Club Name"}}

        def post_form(self, path, data, label):
            self.posts.append((path, data))

    def test_a_club_the_sync_did_not_add_is_renamed_in_the_sheet_only(self):
        # the documented way out of "new club … not added": rename it. The tool finds a
        # club's question by its text, and the only question named Stars is Partner One's:
        # it used to plan (and, applied, write) "q352: 'Stars' -> 'Stars Juniors'" on the
        # region's form and the template - the other partner's roster relabelled
        rename = ["--partner", "Partner Three", "--old", "Stars", "--new", "Stars Juniors"]
        for extra in ([], ["--apply"]):
            sheet, forms = self.stars_sheet(), self.StarsForms()
            code, out = self.run_main(rename + extra, sheet, forms, key="test")
            self.assertIn("q352 is named 'Stars' but holds another club's girls", str(code), out)
            self.assertIn("--sheet-only", str(code))
            self.assertIn("'Partner One'", str(code))
            self.assertNotIn("Ann Poe", str(code) + out)                 # counts, never names
            self.assertEqual((sheet.batches, forms.posts, self.written), ([], [], []), extra)
            self.assertEqual(len(sheet.tabs["Audit"]), 1)
        # --sheet-only: the sheet cells and the Audit row, no Jotform call, and next steps that
        # fit a club the next sync CREATES (no Account to rename, no --q5-change-ok)
        sheet = self.stars_sheet()
        code, out = self.run_main(rename + ["--sheet-only", "--apply"], sheet)
        self.assertEqual(code, 0, out)
        self.assertEqual([r[2] for r in sheet.tabs["Roster"][1:]],
                         ["Stars", "Stars", "Stars", "Stars Juniors", "Stars Juniors"])
        self.assertEqual([r[:3] for r in sheet.tabs["ClubRegistry"][1:]],
                         [["STARS", "Partner One", "Stars"], ["STARS2", "Partner Three", "Stars Juniors"]])
        self.assertEqual(sheet.tabs["SF Pending"][1][2], "Stars Juniors")
        self.assertEqual(sheet.tabs["Audit"][-1][1], "renameClub")
        self.assertNotIn("--apply --q5-change-ok", out)
        self.assertNotIn("rename the club's Account to the new name FIRST", out)
        self.assertIn("no roster question was renamed", out)
        self.assertIn("CREATE roster 'Stars Juniors'", out)
        self.assertIn("hourly", out.lower())                 # ticket #228: the rename's own hint
        self.assertIn("Update form dropdowns", out)
        # the owner of the question renames its own club as ever, namesake or not: the
        # question's girls are its Roster rows' (any status)
        sheet, forms = self.stars_sheet(), self.StarsForms()
        code, out = self.run_main(["--partner", "Partner One", "--old", "Stars", "--new", "North Stars"],
                                  sheet, forms, key="test")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("q352: text 'Stars' -> 'North Stars'"), 2)   # the region's form, the template
        self.assertIn("DRY RUN", out)

    def test_two_questions_of_the_old_name_say_how_to_rename_a_club_that_is_on_no_form(self):
        class Two(self.StarsForms):
            def get(self, path, **params):
                qs = super().get(path, **params)
                return {**qs, "353": dict(qs["352"], options="Eve Hoe|Ida Toe")}
        sheet, forms = self.stars_sheet(), Two()
        code, _ = self.run_main(["--partner", "Partner Three", "--old", "Stars", "--new", "Stars Juniors"],
                                sheet, forms, key="test")
        self.assertIn("2 questions named 'Stars' (q352, q353)", str(code))
        self.assertIn("--sheet-only", str(code))
        self.assertEqual(sheet.batches, [])

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
                         {ord(c) for c in glow_text.INVISIBLE.pattern.strip("[]")})

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

    def run_main(self, argv, sheet, client=None, key=None, clock=None, zone=None):
        """(exit code, stdout). `clock` stands in for datetime (its now(tz=None)); `zone` for
        sc.time_zone (default: a sheet on America/New_York). self.written: what the run left
        in OUT (the backup folder), listed before the temp dir goes."""
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
                mock.patch.object(rename_club.sc, "time_zone", zone or (lambda svc: "America/New_York")), \
                mock.patch.object(rename_club, "datetime", clock or rename_club.datetime), \
                mock.patch.object(rename_club, "Client", lambda api_key, apply=False: client), \
                mock.patch.dict(os.environ, env), \
                mock.patch.object(sys, "argv", ["rename_club.py"] + argv), \
                contextlib.redirect_stdout(out):
            try:
                rename_club.main()
                code = 0
            except SystemExit as e:
                code = e.code
            finally:
                self.written = sorted(os.listdir(d))
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
        # ticket #228: an hourly trigger refreshes the dropdowns; the menu is the way to do it at once
        self.assertIn("hourly", out.lower())
        self.assertIn("Update form dropdowns", out)
        self.assertNotIn("In the sheet, now:", out)

    def test_move_dates_the_audit_and_the_note_in_the_sheets_zone(self):
        # 03:30 UTC on 09-30 is still 09-29 in New York (the patched sheet zone), whatever
        # zone this process is on; the backup folder's stamp stays the process's own clock
        import datetime as dt
        instant = dt.datetime(2026, 9, 30, 3, 30, 0, tzinfo=dt.timezone.utc)

        class Clock:
            @staticmethod
            def now(tz=None):
                return instant.astimezone(tz) if tz else instant.astimezone().replace(tzinfo=None)
        sheet = self.move_sheet()
        code, out = self.run_main(self.MOVE + ["--apply"], sheet, FakeJotform(), key="test",
                                  clock=Clock)
        self.assertEqual(code, 0, out)
        self.assertEqual(sheet.tabs["Audit"][-1][0], "2026-09-29 23:30:00")
        self.assertIn("moved to 'Asociación Demo' on 2026-09-29 (tools/rename_club.py)",
                      sheet.tabs["Partners"][2][2])
        local = instant.astimezone().strftime("%Y-%m-%dT%H%M%S")
        self.assertIn(local, out)

    def test_move_reads_the_sheets_zone_before_any_write(self):
        # the zone read failing (RuntimeError stands in for an HttpError) or answering a zone
        # that is no IANA name stops the run before the backup folder, the batch, the Audit row
        def broken(svc):
            raise RuntimeError("the zone read failed")
        audit = copy.deepcopy(self.move_sheet().tabs["Audit"])
        sheet = self.move_sheet()
        with self.assertRaises(RuntimeError):
            self.run_main(self.MOVE + ["--apply"], sheet, FakeJotform(), key="test", zone=broken)
        self.assertEqual((sheet.batches, sheet.tabs["Audit"], self.written), ([], audit, []))
        sheet = self.move_sheet()
        code, out = self.run_main(self.MOVE + ["--apply"], sheet, FakeJotform(), key="test",
                                  zone=lambda svc: "Mars/Base")
        self.assertIn("the sheet's time zone 'Mars/Base' is not an IANA zone name", str(code))
        self.assertEqual((sheet.batches, sheet.tabs["Audit"], self.written), ([], audit, []))
        sheet = self.move_sheet()                        # the control: a named zone writes all three
        code, out = self.run_main(self.MOVE + ["--apply"], sheet, FakeJotform(), key="test")
        self.assertEqual(code, 0, out)
        self.assertEqual((len(sheet.batches), len(sheet.tabs["Audit"]), len(self.written)), (1, 2, 1))

    def test_move_refuses_a_partner_gated_rule_and_sheet_only_apply(self):
        sheet = self.move_sheet()
        code, out = self.run_main(self.MOVE + ["--apply"], sheet, FakeJotform(gated=True), key="test")
        self.assertIn("given Partner (the typed Partner box)", str(code))
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


class GuardForms:
    """The GETs tools/deactivate_clubs.py's guard makes: the filtered submissions page(s)
    of each form, its questions (q444 is the Club picker) and, for a region whose every
    club is chosen, the form itself (its status: ENABLED unless the id is in `disabled`).
    subs: {form id: [submission]}."""

    def __init__(self, subs=None, picker="444", disabled=()):
        self.subs, self.picker, self.gets = subs or {}, picker, []
        self.disabled = set(disabled)

    def get(self, path, **params):
        self.gets.append((path, params))
        if path.endswith("/questions"):
            return {self.picker: {"type": "control_dropdown", "name": sync.PICKER_NAME},
                    "5": {"type": "control_textbox"}}
        if re.fullmatch(r"/form/\d+", path):
            form_id = path.rsplit("/", 1)[1]
            return {"id": form_id, "status": "DISABLED" if form_id in self.disabled else "ENABLED"}
        page = self.subs.get(path.split("/")[2], [])
        offset, limit = int(params.get("offset", 0)), int(params.get("limit", 1000))
        return page[offset:offset + limit]


def submission(sid, created, q5, picks):
    """One attendance submission as the API lists it, the two answers the guard reads."""
    return {"id": sid, "created_at": created,
            "answers": {"5": {"answer": q5}, "444": {"answer": picks}, "18": {"answer": "x"}}}


class DeactivateClubs(unittest.TestCase):
    """tools/deactivate_clubs.py on an in-memory sheet and a fake form: the plan, the guard
    and its match rule, the write, the re-read, the Audit row, --undo."""

    def test_the_submissions_filter_reaches_jotform_encoded_once(self):
        import subprocess
        import urllib.parse
        from unittest import mock

        from glow import jotform
        urls = []

        def curl(argv, **kw):
            urls.append(next(a for a in argv if a.startswith(jotform.API_BASE)))
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({"responseCode": 200, "content": []}),
                                               stderr="")
        with mock.patch.object(jotform.subprocess, "run", curl):
            self.assertEqual(deactivate_clubs.fetch_since(jotform.Client("KEY"), "123", "2026-09-01 00:00:00"), [])
        self.assertIn("&filter=%7B%22created_at%3Agt%22%3A%20%222026-09-01%2000%3A00%3A00%22%7D", urls[0])
        self.assertEqual(json.loads(urllib.parse.parse_qs(urllib.parse.urlsplit(urls[0]).query)["filter"][0]),
                         {"created_at:gt": "2026-09-01 00:00:00"})

    HDR = ["girl_id", "partner", "club", "region", "full_name", "last_name", "status",
           "added_date", "removed_date", "source"]
    AFRICA, US = glow_forms.REGIONALS["Africa"], glow_forms.REGIONALS["U.S"]

    def roster(self):
        g = lambda n, p, c, r, name, status, removed="": \
            [f"T{n}", p, c, r, name, name.split()[-1], status, "2026-08-26", removed, "T!2"]
        return [self.HDR,
                g(1, "Partner One", "QUEENS", "Africa", "Ann Poe", "active"),              # row 2
                g(2, "Partner One", " queens ", "Africa", "Kay Loe", "active"),            # 3: the same club
                g(3, "Partner One", "QUEENS", "Africa", "Sue Moe", "inactive", "2026-09-01"),   # 4: left already
                g(4, "Partner Two", "Queens of Quest", "Africa", "Uma Roe", "active"),     # 5: 'QUEENS' is its prefix
                g(5, "Partner Three", "Sunrise Club", "U.S", "Eve Hoe", "active"),         # 6
                g(6, "Partner Three", "Sunrise Club", "U.S", "Ida Toe", " Active "),       # 7: the status as typed
                g(7, "Partner Four", "Moon Club", "U.S", "Dee Koe", "active"),             # 8
                g(8, "Partner One", "Stars", "Africa", "Fay Low", "active")]               # 9

    def sheet(self, before_read=None, rows=None):
        return FakeSheet({"Roster": rows or self.roster(), "Audit": [["when", "action", "detail"]]},
                         before_read)

    class Clock:
        """datetime stand-in: 2026-10-07 14:00 UTC (10:00 in New York, the sheet's zone)."""
        import datetime as _dt
        instant = _dt.datetime(2026, 10, 7, 14, 0, 0, tzinfo=_dt.timezone.utc)

        @classmethod
        def now(cls, tz=None):
            return cls.instant.astimezone(tz) if tz else cls.instant.astimezone().replace(tzinfo=None)

    def run_main(self, argv, sheet, client=None, key="test", clock=None, out=None):
        """(exit code, stdout). client: the guard's Jotform (GuardForms; by default one whose U.S
        form is DISABLED, the order the RUNBOOK has - a test of the ENABLED refusal passes its
        own); key=None removes the API key from the environment; out: where the backup folders
        go (a temp dir otherwise)."""
        import contextlib
        import io
        import tempfile
        from unittest import mock
        env = dict(os.environ)
        env.pop("JOTFORM_API_KEY", None)
        if key:
            env["JOTFORM_API_KEY"] = key
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(deactivate_clubs, "OUT", out or d), \
                mock.patch.object(deactivate_clubs.sc, "service", lambda: sheet), \
                mock.patch.object(deactivate_clubs.sc, "read_tab", sheet.read_tab), \
                mock.patch.object(deactivate_clubs.sc, "append_rows", sheet.append_rows), \
                mock.patch.object(deactivate_clubs.sc, "spreadsheet_id", lambda: "SHEET"), \
                mock.patch.object(deactivate_clubs.sc, "sa_email", lambda: "robot"), \
                mock.patch.object(deactivate_clubs.sc, "time_zone", lambda svc: "America/New_York"), \
                mock.patch.object(deactivate_clubs, "datetime", clock or self.Clock), \
                mock.patch.object(deactivate_clubs, "Client",
                                  lambda api_key, apply=False: client or GuardForms(disabled={self.US})), \
                mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(sys, "argv", ["deactivate_clubs.py"] + argv), \
                contextlib.redirect_stdout(buf):
            try:
                deactivate_clubs.main()
                code = 0
            except SystemExit as e:
                code = e.code
            finally:
                self.written = sorted(os.listdir(out or d))
        return code, buf.getvalue()

    def test_matches_is_exact_or_the_long_name_never_a_prefix(self):
        m = deactivate_clubs.matches
        self.assertTrue(m("QUEENS", "Queens", "Partner One"))
        self.assertTrue(m(" queens ", "QUEENS", "Partner One"))
        self.assertTrue(m("QUEENS - Partner One", "QUEENS", "Partner One"))      # "<club> - <its partner>"
        self.assertTrue(m("queens -  partner one", "QUEENS", "Partner One"))     # by key, both halves
        self.assertEqual(m(sync.sf_club_name("QUEENS", "Partner One", True), "QUEENS", "Partner One"), True)
        self.assertFalse(m("Queens of Quest", "QUEENS", "Partner One"))          # the pinned pair (plan, B)
        self.assertFalse(m("QUEENS", "Queens of Quest", "Partner Two"))
        self.assertFalse(m("QUEENSX", "QUEENS", "Partner One"))
        self.assertFalse(m("QUEENS -Partner One", "QUEENS", "Partner One"))      # not the separator
        self.assertFalse(m("Ruby - Partner Two", "Ruby", "Partner One"))         # a namesake's long name
        self.assertFalse(m("Ruby - Partner One - Partner Two", "Ruby", "Partner One"))
        self.assertFalse(m("QUEENS - Partner One", "QUEENS", ""))                # no partner, no long form
        self.assertFalse(m("", "QUEENS", "Partner One"))
        self.assertFalse(m("QUEENS", "", "Partner One"))

    def test_selectors(self):
        sheet = self.sheet()
        code, out = self.run_main(["--region", "u.s", "--reason", "x"], sheet)
        self.assertEqual(code, 0, out)
        self.assertIn("Sunrise Club", out)
        self.assertIn("2 active row(s)   rows 6-7", out)             # ' Active ' counts; row order
        self.assertIn("Moon Club", out)
        self.assertIn("Roster             3 row(s) -> status inactive, removed_date 2026-10-07 (6 cells)", out)
        self.assertIn("Audit              1 row appended", out)
        self.assertIn("--undo", out)
        self.assertIn("DRY RUN", out)
        self.assertNotIn("QUEENS", out)
        self.assertEqual(sheet.batches, [])
        code, out = self.run_main(["--partner", "partner one"], sheet)
        self.assertEqual(code, 0, out)
        self.assertIn("QUEENS", out)
        self.assertIn("2 active row(s)   rows 2-3", out)             # the inactive row 4 is not planned
        self.assertIn("Stars", out)
        self.assertNotIn("Queens of Quest", out)
        code, out = self.run_main(["--partner", "Partner One", "--club", "queens"], sheet)
        self.assertEqual(code, 0, out)
        self.assertIn("Roster             2 row(s) -> status inactive", out)      # QUEENS alone, rows 2-3
        self.assertNotIn("Stars", out)
        # names, never: the plan lists rows, counts, partners and clubs
        for name in ("Ann Poe", "Kay Loe", "Eve Hoe"):
            self.assertNotIn(name, out)

    def test_refusals_before_anything_is_read(self):
        sheet = self.sheet()
        for argv, text in ([[], "choose the clubs"],
                           [["--club", "QUEENS"], "exactly one --partner"],
                           [["--region", "U.S", "--check-only", "--apply"], "drop --apply"],
                           [["--region", "U.S", "--apply"], "--apply needs --reason"],
                           [["--undo", "x", "--region", "U.S"], "--undo takes no selector"],
                           [["--undo", "x", "--form-enabled-ok"], "--undo takes no selector and no guard flag"],
                           [["--region", "U.S", "--recent-days", "-1"], "0 or more"]):
            code, _ = self.run_main(argv, sheet)
            self.assertIn(text, str(code), argv)
            self.assertEqual(sheet.reads, {}, argv)
        for argv, text in ([["--region", "Mars"], "--region 'Mars' matches no active Roster row"],
                           [["--partner", "Nobody"], "--partner 'Nobody' matches no active Roster row"],
                           [["--partner", "Partner One", "--club", "Moon Club"], "--club 'Moon Club' matches"],
                           [["--partner", "Partner One", "--partner", "Nobody"], "--partner 'Nobody' matches"]):
            code, _ = self.run_main(argv, sheet)
            self.assertIn(text, str(code), argv)
            self.assertIn("Africa / Asia / Latin America / U.S", str(code))
        self.assertEqual(sheet.batches, [])
        code, _ = self.run_main(["--region", "U.S"], sheet, key=None)
        self.assertIn("Set JOTFORM_API_KEY", str(code))
        self.assertIn("before any club is deactivated", str(code))
        rows = self.roster() + [["T9", "Partner Five", "Comet Club", "", "Bea Goe", "Goe", "active", "2026-08-26", "", "T!2"]]
        code, _ = self.run_main(["--partner", "Partner Five"], self.sheet(rows=rows))
        self.assertIn("region ''", str(code))
        self.assertIn("no attendance form's", str(code))

    def africa_forms(self):
        """Africa: one plain submission for Queens of Quest, and one that picked QUEENS together
        with Queens of Quest (the 2026-09-25 shape); U.S: nothing."""
        return GuardForms({self.AFRICA: [
            submission("1", "2026-10-01 09:00:00", "Queens of Quest", ["Queens of Quest"]),
            submission("2", "2026-09-25 11:26:00", "QUEENSQueens of Quest", ["QUEENS", "Queens of Quest"]),
        ]})

    def test_check_only_prints_the_counts_and_plans_nothing(self):
        sheet, forms = self.sheet(), self.africa_forms()
        code, out = self.run_main(["--partner", "Partner One", "--check-only"], sheet, forms)
        self.assertEqual(code, 0, out)
        self.assertIn(f"Africa form {self.AFRICA}: 2 submissions since 2026-09-01 read", out)
        self.assertRegex(out, r"Partner One\s+2 club\(s\)\s+1 submission\(s\)  \(last 2026-09-25; 1 picked together with another club\)")
        self.assertIn("'QUEENS': 1 submission(s), 2026-09-25", out)
        self.assertNotIn("'Stars':", out)
        self.assertIn("--check-only: 3 active row(s) of 2 club(s) would be deactivated; nothing planned", out)
        self.assertNotIn("DRY RUN", out)
        self.assertNotIn("Roster  ", out)
        self.assertEqual((sheet.batches, len(sheet.tabs["Audit"])), ([], 1))
        # the submissions GET is filtered since launch and paged with Jotform's maximum
        subs_gets = [(p, q) for p, q in forms.gets if p.endswith("/submissions")]
        self.assertEqual(len(subs_gets), 1)
        self.assertEqual(json.loads(subs_gets[0][1]["filter"]), {"created_at:gt": deactivate_clubs.SINCE})   # Client.url encodes it
        self.assertEqual((subs_gets[0][1]["limit"], subs_gets[0][1]["offset"]), (1000, 0))
        # the exact rule in the flow: Queens of Quest's two submissions are its own
        code, out = self.run_main(["--partner", "Partner Two", "--check-only"], sheet, forms)
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"Partner Two\s+1 club\(s\)\s+2 submission\(s\)")
        self.assertIn("'Queens of Quest': 2 submission(s), 2026-09-25, 2026-10-01", out)
        code, out = self.run_main(["--region", "U.S", "--check-only"], sheet, forms)
        self.assertEqual(code, 0, out)
        self.assertIn(f"U.S form {self.US}: 0 submissions since 2026-09-01 read", out)
        self.assertRegex(out, r"Partner Three\s+1 club\(s\)\s+0 submission\(s\)\n")

    def test_a_recent_submission_stops_the_run_unless_anyway(self):
        sheet, forms = self.sheet(), self.africa_forms()
        code, out = self.run_main(["--partner", "Partner One", "--reason", "x"], sheet, forms)
        self.assertEqual(str(code), "'QUEENS' (Partner One) sent attendance on 2026-09-25 - deactivating a club "
                                    "that reports needs --deactivate-anyway (1 of the 2 club(s) named in a "
                                    "submission since 2026-09-07)")
        self.assertNotIn("DRY RUN", out)
        code, out = self.run_main(["--partner", "Partner One", "--reason", "x", "--deactivate-anyway"], sheet, forms)
        self.assertEqual(code, 0, out)
        self.assertIn("going on: --deactivate-anyway", out)
        self.assertIn("DRY RUN", out)
        code, out = self.run_main(["--partner", "Partner One", "--reason", "x", "--recent-days", "5"], sheet, forms)
        self.assertEqual(code, 0, out)
        self.assertIn("no chosen club was named in a submission since 2026-10-02", out)
        # the prefix pair: Queens of Quest's submissions never stop a run for 'QUEENS'
        forms = GuardForms({self.AFRICA: [submission("1", "2026-10-06 09:00:00", "Queens of Quest", ["Queens of Quest"])]})
        code, out = self.run_main(["--partner", "Partner One", "--club", "QUEENS", "--reason", "x"], sheet, forms)
        self.assertEqual(code, 0, out)
        self.assertIn("no chosen club was named", out)
        self.assertEqual(sheet.batches, [])

    def test_a_whole_region_needs_its_form_off_first(self):
        # every active U.S club chosen while the U.S form is ENABLED: the dry run says so, --apply
        # refuses without --form-enabled-ok (deactivated first, the runner fails on the empty region)
        sheet, forms = self.sheet(), GuardForms()
        code, out = self.run_main(["--region", "U.S", "--reason", "x"], sheet, forms)
        self.assertEqual(code, 0, out)
        self.assertIn(f"! U.S form {self.US} is ENABLED and these are all of its active clubs - disable it first "
                      "(tools/disable_form.py), or pass --form-enabled-ok", out)
        self.assertIn("DRY RUN", out)
        self.assertIn(f"/form/{self.US}", [p for p, _ in forms.gets])                  # one status GET
        code, out = self.run_main(["--region", "U.S", "--reason", "x", "--apply"], sheet, forms)
        self.assertIn(f"U.S form {self.US} is ENABLED and the chosen clubs are all of its active clubs", str(code))
        self.assertIn("disable the form first (tools/disable_form.py", str(code))
        self.assertIn("--form-enabled-ok", str(code))
        self.assertEqual((sheet.batches, len(self.written)), ([], 0))                  # before the backup folder
        code, out = self.run_main(["--region", "U.S", "--reason", "x", "--apply", "--form-enabled-ok"], sheet, forms)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(sheet.batches), 1)
        # the same clubs through their partners is the same whole region; one partner's is not
        sheet, forms = self.sheet(), GuardForms()
        code, out = self.run_main(["--partner", "Partner Three", "--partner", "Partner Four", "--reason", "x"], sheet, forms)
        self.assertEqual(code, 0, out)
        self.assertIn("these are all of its active clubs", out)
        n = len(forms.gets)
        code, out = self.run_main(["--partner", "Partner Three", "--reason", "x", "--apply"], sheet, forms)
        self.assertEqual(code, 0, out)
        self.assertNotIn("all of its active clubs", out)
        self.assertNotIn(f"/form/{self.US}", [p for p, _ in forms.gets[n:]])           # no status GET needed
        # a DISABLED form (the RUNBOOK's order): nothing to say
        sheet = self.sheet()
        code, out = self.run_main(["--region", "U.S", "--reason", "x", "--apply"], sheet, GuardForms(disabled={self.US}))
        self.assertEqual(code, 0, out)
        self.assertNotIn("disable it first", out)
        # a status this tool cannot read is not DISABLED either

        class Odd(GuardForms):
            def get(self, path, **params):
                out = super().get(path, **params)
                return {"id": out["id"]} if re.fullmatch(r"/form/\d+", path) else out
        code, _ = self.run_main(["--region", "U.S", "--reason", "x", "--apply"], self.sheet(), Odd())
        self.assertIn("is of no readable status and the chosen clubs", str(code))

    def test_apply_writes_the_two_cells_re_reads_and_audits(self):
        sheet = self.sheet()
        code, out = self.run_main(["--region", "U.S", "--reason", "no reports (test)", "--apply"], sheet)
        self.assertEqual(code, 0, out)
        roster = sheet.tabs["Roster"]
        self.assertEqual([(r[6], r[8]) for r in roster[6 - 1:8]],
                         [("inactive", "2026-10-07")] * 3)
        self.assertEqual([r[6] for r in roster[1:5]], ["active", "active", "inactive", "active"])   # untouched
        self.assertEqual(roster[4 - 1][8], "2026-09-01")
        self.assertEqual([r[4] for r in roster[1:]], [r[4] for r in self.roster()[1:]])          # names as they were
        self.assertEqual(len(sheet.batches), 1)
        self.assertEqual(len(sheet.batches[0]), 6)
        self.assertIn("Roster: 6 cell(s) written and verified", out)
        audit = sheet.tabs["Audit"][-1]
        self.assertEqual(audit[0], "2026-10-07 10:00:00")                                       # the sheet's zone
        self.assertEqual(audit[1], "deactivateRows")
        self.assertEqual(audit[2], "2 club(s) of 2 partner(s) in U.S: 3 row(s) set inactive, removed_date "
                                   "2026-10-07 - tools/deactivate_clubs.py (no reports (test))")
        self.assertEqual(len(self.written), 1)
        self.assertIn("Next (docs/RUNBOOK.md, \"Deactivating a club\")", out)
        self.assertIn("hourly", out.lower())                 # ticket #228
        self.assertIn("Update form dropdowns from the Roster", out)
        self.assertNotIn("In the sheet, now:", out)
        self.assertIn("--undo", out)
        for name in ("Eve Hoe", "Ida Toe", "Dee Koe"):
            self.assertNotIn(name, out)

    def test_the_backup_folder_holds_the_tab_and_the_rows_written(self):
        import tempfile
        sheet = self.sheet()
        with tempfile.TemporaryDirectory() as out:
            code, _ = self.run_main(["--partner", "Partner One", "--club", "QUEENS", "--reason", "r", "--apply"],
                                    sheet, out=out)
            self.assertEqual(code, 0)
            folder = os.path.join(out, self.written[0])
            self.assertEqual(sorted(os.listdir(folder)), ["Roster.csv", "written.json"])
            import csv
            with open(os.path.join(folder, "Roster.csv"), newline="", encoding="utf-8") as f:
                self.assertEqual(list(csv.reader(f)), self.roster())             # as it was, before
            with open(os.path.join(folder, "written.json"), encoding="utf-8") as f:
                rec = json.load(f)
        self.assertEqual(rec["set"], {"status": "inactive", "removed_date": "2026-10-07"})
        self.assertEqual((rec["status_col"], rec["removed_col"], rec["reason"]), (6, 8, "r"))
        self.assertEqual(rec["clubs"], [["Partner One", "QUEENS", 2, "Africa"]])
        self.assertEqual(rec["rows"], [{"row": 2, "partner": "Partner One", "club": "QUEENS", "status": "active",
                                        "removed_date": ""},
                                       {"row": 3, "partner": "Partner One", "club": "QUEENS", "status": "active",
                                        "removed_date": ""}])
        self.assertNotIn("Ann Poe", json.dumps(rec))

    def test_removed_date_and_the_audit_when_are_the_sheets_day(self):
        # 03:30 UTC on 10-07 is still 10-06 in New York, whatever zone this process is on
        import datetime as dt

        class Late(self.Clock):
            instant = dt.datetime(2026, 10, 7, 3, 30, 0, tzinfo=dt.timezone.utc)
        sheet = self.sheet()
        code, out = self.run_main(["--region", "U.S", "--reason", "x", "--apply"], sheet, clock=Late)
        self.assertEqual(code, 0, out)
        self.assertEqual(sheet.tabs["Roster"][6 - 1][8], "2026-10-06")
        self.assertEqual(sheet.tabs["Audit"][-1][0], "2026-10-06 23:30:00")
        self.assertIn("removed_date 2026-10-06", out)

    def test_apply_stops_when_a_planned_row_changed_or_the_club_gained_a_row(self):
        def flip(sheet, tab, n):
            if tab == "Roster" and n == 2:                   # the re-read just before the write
                sheet.tabs["Roster"][6 - 1][6] = "inactive"
        sheet = self.sheet(flip)
        code, _ = self.run_main(["--region", "U.S", "--reason", "x", "--apply"], sheet)
        self.assertIn("Roster: row 6 changed since the plan was read", str(code))
        self.assertIn("nothing written", str(code))
        self.assertEqual((sheet.batches, len(sheet.tabs["Audit"])), ([], 1))
        self.assertEqual(len(self.written), 1)             # the backup is taken before the re-read

        def enroll(sheet, tab, n):
            if tab == "Roster" and n == 2:
                sheet.tabs["Roster"].append(["T9", "Partner Four", "moon club", "U.S", "Gia Mow", "Mow",
                                             "active", "2026-10-07", "", "T!9"])
        sheet = self.sheet(enroll)
        code, _ = self.run_main(["--region", "U.S", "--reason", "x", "--apply"], sheet)
        self.assertIn("row 10 came in for the chosen clubs", str(code))
        self.assertEqual(sheet.batches, [])

    def test_a_row_arriving_during_the_write_is_reported_not_written(self):
        def enroll(sheet, tab, n):
            if tab == "Roster" and n == 3:                   # the verify re-read, after the batch
                sheet.tabs["Roster"].append(["T9", "Partner Four", "Moon Club", "U.S", "Gia Mow", "Mow",
                                             "active", "2026-10-07", "", "T!9"])
        sheet = self.sheet(enroll)
        code, out = self.run_main(["--region", "U.S", "--reason", "x", "--apply"], sheet)
        self.assertIn("1 row(s) of the chosen clubs arrived during the run and are still active", str(code))
        self.assertIn("! Roster row 10: active row(s) of the chosen clubs arrived during the run", out)
        self.assertEqual(len(sheet.batches), 1)                                   # no second batch
        self.assertEqual(sheet.tabs["Roster"][10 - 1][6], "active")
        self.assertEqual(sheet.tabs["Audit"][-1][1], "deactivateRows")             # what was written is audited
        self.assertNotIn("Gia Mow", out + str(code))

    def test_undo_puts_the_rows_back_and_refuses_a_changed_row(self):
        import tempfile
        with tempfile.TemporaryDirectory() as out:
            sheet = self.sheet()
            code, _ = self.run_main(["--region", "U.S", "--reason", "x", "--apply"], sheet, out=out)
            self.assertEqual(code, 0)
            folder = os.path.join(out, self.written[0])
            code, text = self.run_main(["--undo", folder], sheet, key=None)      # no key: no guard
            self.assertEqual(code, 0, text)
            self.assertIn("3 row(s) -> status and removed_date as before the run of", text)
            self.assertIn("DRY RUN", text)
            self.assertEqual(len(sheet.batches), 1)
            code, text = self.run_main(["--undo", folder, "--apply"], sheet, key=None)
            self.assertEqual(code, 0, text)
            self.assertEqual([(r[6], r[8]) for r in sheet.tabs["Roster"][6 - 1:8]],
                             [("active", ""), (" Active ", ""), ("active", "")])  # exactly as they were
            self.assertEqual(len(sheet.batches), 2)
            audit = sheet.tabs["Audit"][-1]
            self.assertEqual(audit[1], "reactivateRows")
            self.assertIn("3 row(s) of 2 club(s) of 2 partner(s) in U.S set back as before", audit[2])
            self.assertIn("tools/deactivate_clubs.py --undo", audit[2])
            self.assertTrue(any(d.startswith("undo-") for d in os.listdir(folder)), os.listdir(folder))
            self.assertIn("Update form dropdowns", text)
            self.assertIn("hourly", text.lower())            # ticket #228
            # run again: the rows are active now, so every one of them "changed"
            code, _ = self.run_main(["--undo", folder, "--apply"], sheet, key=None)
            self.assertIn("rows 6-8 changed since the run of", str(code))
            self.assertEqual(len(sheet.batches), 2)
            # a deactivation, then one girl put back by hand: the undo names her row and her club
            # and writes nothing - before the plan, so the dry run refuses too and saves no folder
            sheet = self.sheet()
            self.run_main(["--region", "U.S", "--reason", "x", "--apply"], sheet, out=out)
            folder = os.path.join(out, sorted(os.listdir(out))[-1])     # the fixed clock: the same stamp as above
            saved = sorted(os.listdir(folder))
            sheet.tabs["Roster"][7 - 1][6], sheet.tabs["Roster"][7 - 1][8] = "active", ""
            for argv in (["--undo", folder], ["--undo", folder, "--apply"]):
                code, text = self.run_main(argv, sheet, key=None)
                self.assertIn("Roster: row 7 changed since the run of", str(code))
                self.assertIn("nothing written. Look at those rows first. If the other clubs should still go back, "
                              "take this club out of written.json - the rows and the line under \"clubs\" - and "
                              "run again: 'Sunrise Club' (Partner Three); its own rows are then put back by hand "
                              "from ", str(code))
                self.assertIn("/Roster.csv or through the Club Roster Form", str(code))
                self.assertNotIn("DRY RUN", text)
                self.assertNotIn("Ida Toe", str(code) + text)
            self.assertEqual(len(sheet.batches), 1)
            self.assertEqual(sorted(os.listdir(folder)), saved)                         # no new undo- folder
            # the remedy the message names, done: Sunrise Club out of written.json, the rest go back
            with open(os.path.join(folder, "written.json"), encoding="utf-8") as f:
                rec = json.load(f)
            rec["rows"] = [r for r in rec["rows"] if r["club"] != "Sunrise Club"]
            rec["clubs"] = [c for c in rec["clubs"] if c[1] != "Sunrise Club"]
            with open(os.path.join(folder, "written.json"), "w", encoding="utf-8") as f:
                json.dump(rec, f)
            code, text = self.run_main(["--undo", folder, "--apply"], sheet, key=None)
            self.assertEqual(code, 0, text)
            self.assertEqual([(r[6], r[8]) for r in sheet.tabs["Roster"][6 - 1:8]],
                             [("inactive", "2026-10-07"), ("active", ""), ("active", "")])   # 6 stays, 7 by hand, 8 back
            self.assertEqual(len(sheet.batches), 2)
            self.assertIn("1 row(s) of 1 club(s) of 1 partner(s) in U.S set back", sheet.tabs["Audit"][-1][2])
            code, _ = self.run_main(["--undo", out], sheet, key=None)
            self.assertIn("no written.json", str(code))

    def test_undo_refuses_a_club_with_an_active_row_it_does_not_name_before_the_plan(self):
        import tempfile
        with tempfile.TemporaryDirectory() as out:
            sheet = self.sheet()
            self.run_main(["--region", "U.S", "--reason", "x", "--apply"], sheet, out=out)
            folder = os.path.join(out, self.written[0])
            # a girl enrolled to Moon Club since (a Club Roster Form submission): her row is nobody's to undo
            sheet.tabs["Roster"].append(["T9", "Partner Four", "moon club", "U.S", "Gia Mow", "Mow",
                                         "active", "2026-10-08", "", "T!9"])
            code, text = self.run_main(["--undo", folder], sheet, key=None)
            self.assertEqual(str(code), "Roster: row 10 of 'Moon Club' (Partner Four) is active and not in written.json "
                                        "(enrolled since?) - nothing written. Look at those rows first. If the other "
                                        "clubs should still go back, take this club out of written.json - the rows "
                                        "and the line under \"clubs\" - and run again: 'Moon Club' (Partner Four); "
                                        "its own rows are then put back by hand from "
                                        f"{os.path.relpath(folder, deactivate_clubs.REPO)}/Roster.csv or through "
                                        "the Club Roster Form")
            self.assertNotIn("DRY RUN", text)
            self.assertEqual(len(sheet.batches), 1)
            self.assertNotIn("Gia Mow", str(code) + text)
            # both at once: a changed row of one club and a new row of another, every club named once
            sheet.tabs["Roster"][7 - 1][6], sheet.tabs["Roster"][7 - 1][8] = "active", ""
            code, _ = self.run_main(["--undo", folder, "--apply"], sheet, key=None)
            self.assertIn("row 7 changed since the run of", str(code))
            self.assertIn("; row 10 of 'Moon Club' (Partner Four) is active and not in written.json", str(code))
            self.assertIn("take these clubs out of written.json - the rows and the line under \"clubs\" - and run "
                          "again: 'Moon Club' (Partner Four), 'Sunrise Club' (Partner Three); their own rows", str(code))
            self.assertEqual(len(sheet.batches), 1)
            # half an edit (a club's rows kept, its "clubs" line dropped) is refused by name
            with open(os.path.join(folder, "written.json"), encoding="utf-8") as f:
                rec = json.load(f)
            rec["clubs"] = [c for c in rec["clubs"] if c[1] != "Moon Club"]
            with open(os.path.join(folder, "written.json"), "w", encoding="utf-8") as f:
                json.dump(rec, f)
            code, _ = self.run_main(["--undo", folder], sheet, key=None)
            self.assertEqual(str(code), "written.json: row 8 is 'Moon Club' (Partner Four), which has no line under "
                                        "\"clubs\" - a club leaves written.json with its rows AND its line under "
                                        "\"clubs\", or not at all")

    def test_undo_stops_when_a_row_moves_under_it(self):
        import tempfile
        with tempfile.TemporaryDirectory() as out:
            sheet = self.sheet()
            self.run_main(["--partner", "Partner Four", "--reason", "x", "--apply"], sheet, out=out)
            folder = os.path.join(out, self.written[0])

            def reactivate(sheet, tab, n):
                if tab == "Roster" and n == 2:               # between the undo's plan and its write
                    sheet.tabs["Roster"][8 - 1][6] = "active"
            sheet.before_read, sheet.reads = reactivate, {}
            code, _ = self.run_main(["--undo", folder, "--apply"], sheet, key=None)
            self.assertIn("row 8 changed", str(code))
            self.assertIn("look at those rows first (the dry run names them with their clubs)", str(code))
            self.assertEqual(len(sheet.batches), 1)
            sheet.tabs["Roster"][8 - 1][6] = "inactive"

            def enroll(sheet, tab, n):
                if tab == "Roster" and n == 2:               # a new Moon Club row in the same window
                    sheet.tabs["Roster"].append(["T9", "Partner Four", "Moon Club", "U.S", "Gia Mow", "Mow",
                                                 "active", "2026-10-08", "", "T!9"])
            sheet.before_read, sheet.reads = enroll, {}
            code, _ = self.run_main(["--undo", folder, "--apply"], sheet, key=None)
            self.assertIn("row 10 of the chosen clubs active again since the plan was read", str(code))
            self.assertNotIn("run the tool again", str(code))
            self.assertEqual(len(sheet.batches), 1)


class FormApi:
    """The Jotform calls tools/disable_form.py makes: GET /form/{id}, GET .../properties, and
    the properties POST, which flips the status (and the message) unless flips=False - the
    unverified case: Jotform answers 200 and changes nothing."""

    def __init__(self, status="ENABLED", count=0, last="", message=disable_form.DEFAULT_MESSAGE,
                 flips=True, title="U.S Attendance Form"):
        self.status, self.count, self.last, self.message = status, count, last, message
        self.flips, self.title, self.calls = flips, title, []

    def get(self, path, **params):
        self.calls.append(("GET", path))
        if path.endswith("/properties"):
            return {"status": self.status, "messageOfLimitedForm": self.message, "conditions": [], "emails": []}
        if path.endswith("/questions"):
            return {"5": {"type": "control_textbox"}}
        return {"id": path.rsplit("/", 1)[1], "title": self.title, "status": self.status,
                "count": str(self.count), "last_submission": self.last}

    def post_form(self, path, data, label):
        self.calls.append(("POST", path, dict(data)))
        if self.flips:
            self.status = data.get("properties[status]", self.status)
            self.message = data.get("properties[messageOfLimitedForm]", self.message)


class DisableForm(unittest.TestCase):
    """tools/disable_form.py: the dry run, the refusals, the backup before the write, the
    re-read that decides."""

    US = glow_forms.REGIONALS["U.S"]

    def run_main(self, argv, api, key="test", today="2026-10-07 14:00:00"):
        import contextlib
        import datetime as dt
        import io
        from unittest import mock
        instant = dt.datetime.strptime(today, "%Y-%m-%d %H:%M:%S")

        class Clock:
            @staticmethod
            def now(tz=None):
                return instant

        def snapshot(form_id, client, stamp):
            api.calls.append(("BACKUP", form_id, stamp))
            return {"questions": 7, "conditions": 3, "emails": 1, "salesforce": "yes"}
        env = dict(os.environ)
        env.pop("JOTFORM_API_KEY", None)
        if key:
            env["JOTFORM_API_KEY"] = key
        buf = io.StringIO()
        with mock.patch.object(disable_form, "Client", lambda api_key, apply=False: api), \
                mock.patch.object(disable_form.backup, "snapshot", snapshot), \
                mock.patch.object(disable_form, "datetime", Clock), \
                mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(sys, "argv", ["disable_form.py"] + argv), \
                contextlib.redirect_stdout(buf):
            try:
                disable_form.main()
                code = 0
            except SystemExit as e:
                code = e.code
        return code, buf.getvalue()

    def test_dry_run_reads_and_says_what_it_would_do(self):
        api = FormApi()
        code, out = self.run_main(["--form", self.US], api)
        self.assertEqual(code, 0, out)
        self.assertIn(f"U.S Attendance Form {self.US}: status ENABLED, 0 submissions (last none)", out)
        self.assertIn("messageOfLimitedForm: 'This form is currently unavailable!'", out)
        self.assertIn("DRY RUN - re-run with --apply to back up the form, then set status DISABLED (then re-read)", out)
        self.assertEqual([c[0] for c in api.calls], ["GET", "GET"])
        code, out = self.run_main(["--form", self.US, "--message", "Paused."], api)
        self.assertEqual(code, 0, out)
        self.assertIn("message -> 'Paused.'", out)
        self.assertNotIn("POST", str(api.calls))

    def test_refusals(self):
        api = FormApi()
        code, _ = self.run_main(["--form", glow_forms.TEMPLATE], api)
        self.assertIn("the template is never disabled", str(code))
        code, _ = self.run_main(["--form", glow_forms.DEFUNCT["U.S"]], api)
        self.assertIn("not one of the live regional forms", str(code))
        code, _ = self.run_main(["--form", self.US, "--enable", "--message", "x"], api)
        self.assertIn("--enable takes no --message", str(code))
        self.assertEqual(api.calls, [])                                   # nothing read for a refused form
        code, _ = self.run_main(["--form", self.US], api, key=None)
        self.assertIn("Set JOTFORM_API_KEY", str(code))
        api = FormApi(count=3, last="2026-10-01 10:00:00")
        code, _ = self.run_main(["--form", self.US], api)
        self.assertIn(f"form {self.US} took a submission on 2026-10-01 (in the last 30 days)", str(code))
        self.assertIn("--disable-anyway", str(code))
        code, out = self.run_main(["--form", self.US, "--disable-anyway"], api)
        self.assertEqual(code, 0, out)
        self.assertIn("DRY RUN", out)
        code, out = self.run_main(["--form", self.US], FormApi(count=3, last="2026-08-30 10:00:00"))
        self.assertEqual(code, 0, out)                                    # older than 30 days: no guard
        api = FormApi(status="FUNNY")
        code, _ = self.run_main(["--form", self.US], api)
        self.assertIn("neither ENABLED nor DISABLED", str(code))

        class Split(FormApi):
            def get(self, path, **params):
                out = super().get(path, **params)
                if path.endswith("/properties"):
                    out["status"] = "DISABLED"
                return out
        code, _ = self.run_main(["--form", self.US], Split())
        self.assertIn("not the same form state; read again before anything is written", str(code))

        class SplitAfter(FormApi):
            """The two GETs agree until the POST; the re-read then disagrees."""
            def post_form(self, path, data, label):
                super().post_form(path, data, label)
                self.split = True

            def get(self, path, **params):
                out = super().get(path, **params)
                if getattr(self, "split", False) and path.endswith("/properties"):
                    out["status"] = "ENABLED"
                return out
        api = SplitAfter()
        code, _ = self.run_main(["--form", self.US, "--apply"], api)
        self.assertIn("not the same form state after the write - the properties POST was sent; run this again "
                      "without --apply until both GETs agree, then decide", str(code))
        self.assertEqual([c[0] for c in api.calls], ["GET", "GET", "BACKUP", "POST", "GET", "GET"])

    def test_apply_backs_up_then_posts_then_re_reads(self):
        api = FormApi()
        code, out = self.run_main(["--form", self.US, "--message", "The U.S attendance form is paused.", "--apply"], api)
        self.assertEqual(code, 0, out)
        kinds = [c[0] for c in api.calls]
        self.assertEqual(kinds, ["GET", "GET", "BACKUP", "POST", "GET", "GET"])     # the backup before the write
        self.assertEqual(api.calls[3][2], {"properties[status]": "DISABLED",
                                           "properties[messageOfLimitedForm]": "The U.S attendance form is paused."})
        self.assertIn("backup_forms: form", out)
        self.assertIn("status DISABLED, 0 submissions", out)
        self.assertIn(f"form {self.US} is DISABLED - the runner reads it as 'skipped'", out)
        # already off: nothing to do, no POST
        code, out = self.run_main(["--form", self.US, "--apply"], api)
        self.assertEqual(code, 0, out)
        self.assertIn("already DISABLED - nothing to do", out)
        self.assertEqual([c[0] for c in api.calls].count("POST"), 1)
        # the way back
        code, out = self.run_main(["--form", self.US, "--enable", "--apply"], api)
        self.assertEqual(code, 0, out)
        self.assertEqual(api.status, "ENABLED")
        self.assertIn(f"form {self.US} is ENABLED - one runner dry run next", out)

    def test_a_status_that_does_not_move_stops_with_the_builder_step(self):
        api = FormApi(flips=False)
        code, out = self.run_main(["--form", self.US, "--apply"], api)
        self.assertEqual(str(code), disable_form.STILL_ENABLED)
        self.assertIn("Settings -> Form Status", str(code))
        self.assertEqual([c[0] for c in api.calls], ["GET", "GET", "BACKUP", "POST", "GET", "GET"])
        self.assertIn("re-read:", out)

        class StatusOnly(FormApi):
            def post_form(self, path, data, label):
                self.calls.append(("POST", path, dict(data)))
                self.status = data.get("properties[status]", self.status)       # the message stays
        code, _ = self.run_main(["--form", self.US, "--message", "Paused.", "--apply"], StatusOnly())
        self.assertIn("messageOfLimitedForm did not change", str(code))
        self.assertIn("status DISABLED as wanted", str(code))

    def test_the_backup_stamp_is_to_the_second(self):
        # a minute stamp let a re-run within the minute write the half-changed form over the
        # true "before" (glow/backup.py stamp)
        api = FormApi()
        code, out = self.run_main(["--form", self.US, "--apply"], api, today="2026-10-07 14:00:05")
        self.assertEqual(code, 0, out)
        self.assertEqual([c for c in api.calls if c[0] == "BACKUP"], [("BACKUP", self.US, "2026-10-07T140005")])
        self.assertIn(f"backups/{self.US}/*-2026-10-07T140005.json", out)


class UploadRosterPartners(unittest.TestCase):
    """tools/upload_roster.py merge_partners keeps the live header's width (the jotform column)."""

    def test_merge_keeps_every_live_cell_and_the_width(self):
        live = [["partner", "region", "notes", "jotform"], ["P1", "Africa", "", "no"], ["P2", "", "", ""],
                ["P3", "Asia", "x"]]
        local = [["partner", "region", "notes", "jotform"], ["P2", "Asia", "derived", ""], ["P4", "U.S", "", ""]]
        out, added, filled = upload_roster.merge_partners(live, local)
        self.assertEqual(out, [["partner", "region", "notes", "jotform"], ["P1", "Africa", "", "no"],
                               ["P2", "Asia", "derived", ""], ["P3", "Asia", "x", ""], ["P4", "U.S", "", ""]])
        self.assertEqual((added, filled), (1, 1))
        # a live tab still three columns wide: its width wins, a local fourth cell is not added
        out, _, _ = upload_roster.merge_partners([["partner", "region", "notes"], ["P1", "Africa", ""]], local)
        self.assertEqual({len(r) for r in out}, {3})
        self.assertEqual(out[-1], ["P4", "U.S", ""])


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


if __name__ == "__main__":
    unittest.main(verbosity=1)
