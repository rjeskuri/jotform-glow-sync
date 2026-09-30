#!/usr/bin/env python3
"""
Offline tests for tools/backfill_resolve.py (imported by test/python_test.py). A fake
client stands in for Jotform and a canned plan for the sync's dry run; every girl, mentor,
club and partner here is fictional (first names and invented surnames from
test/fixtures/make_fixture.py).
"""
import contextlib
import csv
import io
import json
import os
import sys
import tempfile
import unittest
import subprocess
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import backfill_resolve as br         # noqa: E402
from glow import forms as glow_forms  # noqa: E402
from glow import jotform as glow_jotform   # noqa: E402
from glow.sync import MODULES, PICKER_NAME, SESSION_OVERRIDES, WEEKS, YEAR   # noqa: E402

AFRICA, ASIA = glow_forms.REGIONALS["Africa"], glow_forms.REGIONALS["Asia"]
PICKER = "500"
AMARA, BEA, CHIARA = "Amara Fennwhistle", "Beatrice Marrowgate", "Chiara Ostrivane"
DALIA, ESTHER, FATIMA = "Dalia Pellucidor", "Esther Thornquibble", "Fatima Umberlash"
GRACE, HANA, INES = "Grace Wrenfoldy", "Hana Yexleyton", "Ines Grimboltz"
KAVYA, LEILA, MAYA = "Kavya Ixworthing", "Leila Jubbleton", "Maya Kestrelby"
NADIA, OLIVIA, PRIYA = "Nadia Nimbleford", "Olivia Quillstrand", "Priya Vexmoorish"
STRANGER, STRANGER2 = "Joy Halverquist", "Keza Lorrimane"      # ticked, and in no Roster row
MENTOR = "mentor1@example.org"
# the curriculum cascade as the sync builds it: a module dropdown per year (no calcValues: the
# calculation into question 98 copies the option's visible text) and a session dropdown per
# number of sessions (calcValues: the calculation into question 100 copies the number)
MODULE_OPTIONS = {"1": ["Relationships 101", "Decision Making"],
                  "2": ["Relationships 201", "Elective - Healthy GLOW", "Elective - Girl Boss Basics"],
                  "3": ["Power of Girls 301", "Elective - Girl Boss Pro"]}
TRANSLATED = "Toma de decisiones"          # "Decision Making" as a browser's page translation shows it
PHOTO = "https://www.example.org/uploads/group-photo.jpg"
IP = "192.0.2.1"
# qid -> (club, the partner the sync names - '' = none -, what the sync says it sends, its girls today)
ROSTERS = {
    "10": ("Alpha Club", "Partner One", "Alpha Club", [AMARA, BEA, CHIARA]),
    "11": ("Stars", "Partner One", "Stars - Partner One", [DALIA, ESTHER]),
    "12": ("Stars", "Partner Two", "Stars - Partner Two", [FATIMA, GRACE]),
    "13": ("Old Club", "Partner Two", "Old Club", [HANA]),       # on the form; its Roster rows inactive
    "24": ("Lost Club", "", "Lost Club", [INES]),                # on the form; no partner named, no Roster row
    # plain-named rosters the region's active export does not hold: the sync names no partner
    # (14 and 15 are the first module and session dropdowns; 17, 18 and 19 the date, the
    # Contact IDs and the photo)
    "20": ("Quiet Club", "", "Quiet Club", [KAVYA]),             # Roster: one partner's, every row inactive
    "21": ("Far Club", "", "Far Club", [LEILA]),                 # Roster: one partner's, active, another region
    "22": ("Adrift Club", "", "Adrift Club", [MAYA]),            # Roster: one partner's, active, no region
    "23": ("Twin Club", "", "Twin Club", [OLIVIA]),              # Roster: two partners have had one
}
# the Roster export: (club code, partner, club, region, status, girls)
SHEET = [
    ("ALPHACLU", "Partner One", "Alpha Club", "Africa", "active", [AMARA, BEA, CHIARA]),
    ("ALPHACLU", "Partner One", "Alpha Club", "Africa", "inactive", [NADIA]),     # she left the club
    ("ALPHACLU", "Partner One", "Alpha Club", "Africa", "inactive", [BEA]),       # left, and came back: two rows
    ("STARS", "Partner One", "Stars", "Africa", "active", [DALIA, ESTHER]),
    ("STARS2", "Partner Two", "Stars", "Africa", "active", [FATIMA, GRACE]),
    ("OLDCLUB", "Partner Two", "Old Club", "Africa", "inactive", [HANA]),
    ("QUIETCLU", "Partner Two", "Quiet Club", "Africa", "inactive", [KAVYA]),
    ("FARCLUB", "Partner One", "Far Club", "Asia", "active", [LEILA]),
    ("ADRIFTCL", "Partner Two", "Adrift Club", "", "active", [MAYA]),
    ("TWINCLUB", "Partner One", "Twin Club", "Africa", "inactive", [OLIVIA]),
    ("TWINCLU2", "Partner Two", "Twin Club", "Africa", "inactive", [PRIYA]),
]
SHEET_ROWS = sum(len(girls) for *_, girls in SHEET)
EVERY_NAME = [AMARA, BEA, CHIARA, DALIA, ESTHER, FATIMA, GRACE, HANA, INES, KAVYA, LEILA, MAYA,
              NADIA, OLIVIA, PRIYA, STRANGER, STRANGER2]


def questions():
    """The form today, as GET /form/{id}/questions gives it."""
    qs = {"5": {"type": "control_textbox", "name": "clubName", "text": "Club Name"},
          "17": {"type": "control_datetime", "name": "date", "text": "Date"},
          "18": {"type": "control_textarea", "name": "contact_ids", "text": "Contact IDs"},
          "19": {"type": "control_fileupload", "name": "photo", "text": "Group Photo"},
          YEAR: {"type": "control_dropdown", "name": "module94", "text": "GLOW Club Year",
                 "options": "1|2|3", "calcValues": "|1|2|3"},
          "98": {"type": "control_textbox", "name": "module_id", "text": "module"},
          "100": {"type": "control_number", "name": "week_id", "text": "week"},
          "102": {"type": "control_number", "name": "year_id", "text": "year"},
          "105": {"type": "control_textbox", "name": "creator", "text": "creator"},
          PICKER: {"type": "control_dropdown", "name": PICKER_NAME, "text": "Club Name",
                   "options": "|".join(sorted({sends for _, _, sends, _ in ROSTERS.values()}))}}
    for year, qid in MODULES.items():
        qs[qid] = {"type": "control_dropdown", "name": "module" + year, "text": "Module",
                   "options": "|".join(MODULE_OPTIONS[year]), "calcValues": ""}
    for sessions, qid in WEEKS.items():
        qs[qid] = {"type": "control_dropdown", "name": f"week{sessions}", "text": "Session",
                   "options": "|".join(f"Session {n}" for n in range(1, sessions + 1)),
                   "calcValues": "|" + "|".join(str(n) for n in range(1, sessions + 1))}
    for qid, (club, _, _, girls) in ROSTERS.items():
        qs[qid] = {"type": "control_checkbox", "name": "roster" + qid, "text": club,
                   "options": "|".join(girls)}
    return qs


def plan(**change):
    """The sync's dry-run summary (--summary-json), the part the resolver reads."""
    names = [{"qid": qid, "club": club, "value": sends, "partner": partner}
             for qid, (club, partner, sends, _) in ROSTERS.items()]
    names.append({"qid": None, "club": "New Club", "value": "New Club", "partner": "Partner Two"})
    return dict({"apply": False, "sf_names": names, "sf_name_changes": [], "calls": []}, **change)


AUTO = object()


def submission(sid, ticks, created="2026-09-10 08:00:00", q5="Alpha Club", q18=AUTO,
               date=("2026", "09", "09"), picks=("Alpha Club",), status="ACTIVE", form=AFRICA,
               photo=(PHOTO,), extra=None, year="1", module="Decision Making", week="Session 3",
               q98=AUTO, q100=AUTO, q102=AUTO):
    """One submission in Jotform's shape: every question of today's form is listed with
    its name/text/type, and carries `answer` only when it was answered. ticks: {qid:
    [names]}; q18 defaults to what the form's calculation writes; extra: raw answers added.
    year / module / week are picked in the dropdowns the form shows for them (the module
    dropdown of that year, the session dropdown of that module); q98 / q100 / q102 default to
    what the form's calculations copy from them (the module's text, the session's number, the
    year)."""
    answers = {qid: {"name": q["name"], "order": "1", "text": q["text"], "type": q["type"]}
               for qid, q in questions().items()}

    def put(qid, value):
        if qid in answers and value not in (None, "", [], ()):
            answers[qid]["answer"] = value

    for qid, names in ticks.items():     # a list of names; anything else is passed through as it is
        put(qid, names)
    if q18 is AUTO:
        q18 = ", ".join(n for qid in sorted(ticks, key=int) for n in ticks[qid])
    put("5", q5)
    put("18", q18)
    put("19", list(photo))
    put("17", dict(zip(("year", "month", "day"), date), datetime="x") if date else None)
    put(YEAR, year)
    put(MODULES.get(year), module)
    put(WEEKS[8 if year == "1" else SESSION_OVERRIDES.get(module, 8)], week)
    put("98", module if q98 is AUTO else q98)
    put("100", (week or "").split(" ")[-1] if q100 is AUTO else q100)
    put("102", year if q102 is AUTO else q102)
    put("105", MENTOR)
    put(PICKER, list(picks))
    answers.update(extra or {})
    return {"id": sid, "form_id": form, "ip": IP, "created_at": created, "status": status,
            "new": "1", "flag": "0", "notes": "", "updated_at": None, "answers": answers}


class FakeJotform:
    """Reads only: there is no write method to call."""

    def __init__(self, submissions=None, count=None, qs=None):
        self.submissions = submissions or {}            # form id -> [submission, ...]
        self.count, self.qs, self.asked = count, qs, []

    def get(self, path, **params):
        self.asked.append((path, params))
        parts = path.strip("/").split("/")
        subs = self.submissions.get(parts[1], [])
        if parts[2:] == ["submissions"]:
            return json.loads(json.dumps(subs[params["offset"]:params["offset"] + params["limit"]]))
        if parts[2:] == ["questions"]:
            return questions() if self.qs is None else self.qs
        return {"id": parts[1], "count": str(len(subs) if self.count is None else self.count)}


class BackfillResolve(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.roster_csv = os.path.join(cls.tmp.name, "roster.csv")
        with open(cls.roster_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["girl_id", "partner", "club", "region", "full_name", "last_name", "status"])
            for code, partner, club, region, status, girls in SHEET:
                for n, girl in enumerate(girls, 1):      # ids are built here, never written out
                    w.writerow([f"{code}-{girl.split()[-1].upper()[:12]}-{n:03d}", partner, club,
                                region, girl, girl.split()[-1], status])
        cls.roster = br.read_roster(cls.roster_csv)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def resolve(self, subs, qs=None, the_plan=None):
        return br.resolve("Africa", AFRICA, subs, questions() if qs is None else qs,
                          br.rosters_today(the_plan or plan()), self.roster)

    def one(self, ticks, **kw):
        """The rows of one submission."""
        rows, _, _ = self.resolve([submission("9001", ticks, **kw)])
        return rows

    def refused(self, fn, *fragments):
        with self.assertRaises(SystemExit) as stop:
            fn()
        for fragment in fragments:
            self.assertIn(fragment, str(stop.exception.code))
        for name in EVERY_NAME + [MENTOR]:              # a refusal names no one either
            self.assertNotIn(name, str(stop.exception.code))

    def run_main(self, client, *argv, the_plan=None, roster=None):
        """(stdout, exit code or None, the result file's content or None)."""
        out_path = os.path.join(self.out_dir.name, "resolved.json")
        argv = ["--roster", roster or self.roster_csv, "--out", out_path, *argv]
        out, code = io.StringIO(), None
        try:
            with contextlib.redirect_stdout(out):
                br.main(argv, client=client, plan_of=lambda *a: the_plan or plan())
        except SystemExit as stop:
            code = stop.code
        result = None
        if os.path.exists(out_path):
            with open(out_path, encoding="utf-8") as f:
                result = json.load(f)
        return out.getvalue(), code, result

    def setUp(self):
        self.out_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.out_dir.cleanup()

    # ---- the row
    def test_one_row_per_ticked_roster_with_every_field(self):
        rows = self.one({"10": [AMARA, CHIARA]})
        self.assertEqual(rows, [{
            "region": "Africa", "form_id": AFRICA, "submission_id": "9001",
            "created_at": "2026-09-10 08:00:00", "roster_qid": "10", "club_code": "ALPHACLU",
            "club": "Alpha Club", "partner": "Partner One", "sf_account_name": "Alpha Club",
            "attendance_date": "2026-09-09", "names": [AMARA, CHIARA], "module": "Decision Making",
            "module_week": "3", "module_year": "1", "creator": MENTOR, "photo_urls": [PHOTO],
            "q5": "Alpha Club", "flags": []}])

    def test_several_ticked_rosters_are_split_into_one_row_each(self):
        # two clubs picked: question 5 holds their names run together, question 18 the two
        # rosters' names with no separator between the rosters - neither is used for the club
        rows = self.one({"11": [DALIA, ESTHER], "10": [BEA]}, q5="Alpha ClubStars - Partner One",
                        picks=("Alpha Club", "Stars - Partner One"), q18=f"{BEA}{DALIA}, {ESTHER}")
        self.assertEqual([(r["roster_qid"], r["club"], r["partner"], r["sf_account_name"], r["names"])
                          for r in rows],
                         [("10", "Alpha Club", "Partner One", "Alpha Club", [BEA]),
                          ("11", "Stars", "Partner One", "Stars - Partner One", [DALIA, ESTHER])])
        self.assertEqual({r["submission_id"] for r in rows}, {"9001"})
        for r in rows:
            self.assertEqual(r["flags"], ["multi_club", "q5_differs", "q18_differs"])

    def test_names_are_a_list_trimmed_in_the_order_ticked(self):
        row, = self.one({"10": [f"  {CHIARA} ", f"{AMARA}\t", "  "]}, q18=f"{CHIARA}, {AMARA}")
        self.assertEqual(row["names"], [CHIARA, AMARA])
        self.assertIsInstance(row["names"], list)
        self.assertEqual(row["flags"], [])

    def test_same_club_and_date_twice_stays_two_rows(self):
        rows, _, counts = self.resolve([submission("9001", {"10": [AMARA]}),
                                        submission("9002", {"10": [AMARA]})])
        self.assertEqual([r["submission_id"] for r in rows], ["9001", "9002"])
        self.assertEqual(counts["same_club_and_date"], {"groups": 1, "rows": 2})

    # ---- the flags, one by one
    def test_q5_is_only_cross_checked(self):
        for q5, flagged in (("Alpha Club", False), ("alpha club", True), ("Alpha Club ", True),
                            ("Alpha Clab", True), (None, True)):
            with self.subTest(q5=q5):
                row, = self.one({"10": [AMARA]}, q5=q5)
                self.assertEqual((row["club"], row["q5"]), ("Alpha Club", q5))
                self.assertEqual(row["flags"], ["q5_differs"] if flagged else [])

    def test_q18_empty_and_q18_differs(self):
        ticks = {"10": [AMARA, BEA]}
        cases = {"": ["q18_empty"], "   ": ["q18_empty"],
                 f"{AMARA},{BEA}": [], f" {BEA} ,  {AMARA} ": [],          # commas only, pieces trimmed, any order
                 AMARA: ["q18_differs"], f"{AMARA}, {BEA}, {CHIARA}": ["q18_differs"],
                 f"{AMARA}, {BEA.upper()}": ["q18_differs"], f"{AMARA}, {BEA}, ": ["q18_differs"]}
        for q18, flags in cases.items():
            with self.subTest(q18=len(q18)):
                row, = self.one(ticks, q18=q18)
                self.assertEqual(row["flags"], flags)

    def test_typed_era_is_a_submission_without_a_picker_answer(self):
        row, = self.one({"10": [AMARA]}, picks=())
        self.assertEqual(row["flags"], ["typed_era"])
        no_picker = {q: v for q, v in questions().items() if q != PICKER}     # a form without the picker
        rows, _, _ = self.resolve([submission("9001", {"10": [AMARA]})], qs=no_picker)
        self.assertEqual(rows[0]["flags"], ["typed_era"])

    def test_bare_shared_name(self):
        # 'Stars' was typed or picked when two partners' clubs shared the entry: the ticked
        # roster says whose club it was, and that roster sends the long name today
        row, = self.one({"12": [FATIMA]}, q5="stars", picks=())
        self.assertEqual((row["partner"], row["sf_account_name"], row["club_code"]),
                         ("Partner Two", "Stars - Partner Two", "STARS2"))
        self.assertEqual(row["flags"], ["q5_differs", "typed_era", "bare_shared_name"])
        row, = self.one({"11": [DALIA]}, q5="Stars - Partner One", picks=("Stars - Partner One",))
        self.assertEqual(row["flags"], [])
        row, = self.one({"10": [AMARA]}, q5="Stars")          # a plain-named roster: just q5_differs
        self.assertEqual(row["flags"], ["q5_differs"])

    def test_retired_club(self):
        # on the form, its Roster rows all inactive: the code is still the club's
        row, = self.one({"13": [HANA]}, q5="Old Club", picks=("Old Club",))
        self.assertEqual((row["club"], row["partner"], row["club_code"], row["sf_account_name"]),
                         ("Old Club", "Partner Two", "OLDCLUB", "Old Club"))
        self.assertEqual(row["flags"], ["retired_club"])
        # on the form, the sync names no partner for it and the Roster has no club of that name
        row, = self.one({"24": [INES]}, q5="Lost Club", picks=("Lost Club",))
        self.assertEqual((row["club"], row["partner"], row["club_code"], row["sf_account_name"]),
                         ("Lost Club", None, None, "Lost Club"))
        self.assertEqual(row["flags"], ["retired_club"])

    def test_a_club_the_sync_names_no_partner_for_takes_the_roster_s_only_holder(self):
        # the sync names a partner only for a roster of the region's ACTIVE export (or a
        # long-named one): for a plain-named club that retired, or whose rows carry another
        # region or none, it says ''. The Roster export still holds the club: one partner
        # has (or had) a club of that name -> that partner and its code
        cases = {"20": ("Quiet Club", "Partner Two", "QUIETCLU", ["retired_club"]),   # every row inactive
                 "21": ("Far Club", "Partner One", "FARCLUB", []),                    # active, region Asia
                 "22": ("Adrift Club", "Partner Two", "ADRIFTCL", [])}                # active, no region
        for qid, (club, partner, code, flags) in cases.items():
            with self.subTest(club=club):
                self.assertEqual(br.rosters_today(plan())[qid], (club, None, club))   # the sync's word
                rows, _, counts = self.resolve([submission("9001", {qid: ROSTERS[qid][3]}, q5=club,
                                                           picks=(club,))])
                row, = rows
                self.assertEqual((row["club"], row["partner"], row["club_code"], row["sf_account_name"]),
                                 (club, partner, code, club))
                self.assertEqual(row["flags"], flags)
                self.assertEqual(counts["partner_from_roster"], 1)
        # two partners have had a club of that name: whose it is cannot be told - no guess
        rows, _, counts = self.resolve([submission("9001", {"23": [OLIVIA]}, q5="Twin Club",
                                                   picks=("Twin Club",))])
        row, = rows
        self.assertEqual((row["partner"], row["club_code"], row["sf_account_name"]), (None, None, "Twin Club"))
        self.assertEqual(row["flags"], ["retired_club"])
        self.assertEqual(counts["partner_from_roster"], 0)
        # a partner the sync does name is never replaced
        rows, _, counts = self.resolve([submission("9001", {"10": [AMARA]})])
        self.assertEqual((rows[0]["partner"], counts["partner_from_roster"]), ("Partner One", 0))

    def test_the_club_name_is_the_live_picker_s_spelling(self):
        # the Roster respells a club by capitals only: the sync records no change for that
        # (equal under glow.text.key), so its value is the Roster's spelling - what the roster
        # SENDS today is the live Club picker's entry
        respelled = plan()
        respelled["sf_names"][0]["value"] = "ALPHA  CLUB"
        rows, _, _ = self.resolve([submission("9001", {"10": [AMARA]})], the_plan=respelled)
        self.assertEqual((rows[0]["sf_account_name"], rows[0]["flags"]), ("Alpha Club", []))
        # the picker has no entry for what the sync says the roster sends: it sends nothing today
        absent = plan()
        absent["sf_names"][0]["value"] = "Alpha Club - Partner One"
        rows, _, _ = self.resolve([submission("9001", {"10": [AMARA]})], the_plan=absent)
        self.assertEqual((rows[0]["sf_account_name"], rows[0]["club"], rows[0]["partner"]),
                         (None, "Alpha Club", "Partner One"))
        self.assertEqual(rows[0]["flags"], ["q5_differs", "no_account_name"])
        # a form without the Club picker (the name is typed): the sync's word is kept
        no_picker = {q: v for q, v in questions().items() if q != PICKER}
        rows, _, _ = self.resolve([submission("9001", {"10": [AMARA]})], qs=no_picker, the_plan=respelled)
        self.assertEqual(rows[0]["sf_account_name"], "ALPHA  CLUB")

    def test_an_answer_to_a_deleted_roster_question_that_still_says_what_it_was(self):
        gone = {"158": {"name": "roster158", "order": "9", "text": " Gone  Club ",
                        "type": "control_checkbox", "answer": [AMARA, BEA]}}
        rows = self.one({}, q5="Gone Club", picks=("Gone Club",), q18=f"{AMARA}, {BEA}", extra=gone)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["roster_qid"], row["club"], row["partner"], row["club_code"],
                          row["sf_account_name"], row["names"]),
                         ("158", "Gone Club", None, None, None, [AMARA, BEA]))
        # no partner, so no Roster rows to look the names up in: all count as unknown (held)
        self.assertEqual(row["flags"], ["q5_differs", "retired_club", "no_account_name",
                                        "name_unknown_to_roster:2"])

    def test_date_flags(self):
        # attendance_date is always text: zero-padded yyyy-mm-dd, or "" (never null) with
        # date_missing when question 17 is missing or is not a date
        for date, iso, flags in ((("2026", "09", "01"), "2026-09-01", []),
                                 (("2026", "08", "31"), "2026-08-31", ["date_before_2026_09"]),
                                 (("2026", "2", "9"), "2026-02-09", ["date_before_2026_09"]),
                                 (("2026", "10", "2"), "2026-10-02", []),
                                 (("2026", "13", "01"), "", ["date_missing"]),
                                 (("2026", "02", "30"), "", ["date_missing"]),
                                 (("2026", "09", "x"), "", ["date_missing"]),
                                 (("", "", ""), "", ["date_missing"]),
                                 (None, "", ["date_missing"])):
            with self.subTest(date=date):
                row, = self.one({"10": [AMARA]}, date=date)
                self.assertEqual((row["attendance_date"], row["flags"]), (iso, flags))
                self.assertIsInstance(row["attendance_date"], str)
        # question 17 answered with something that is not {year, month, day}
        for odd in ("2026-09-09", ["2026", "09", "09"], {"year": "2026", "month": "09"}):
            with self.subTest(odd=type(odd).__name__):
                sub = submission("9001", {"10": [AMARA]})
                sub["answers"]["17"]["answer"] = odd
                rows, _, counts = self.resolve([sub])
                self.assertEqual((rows[0]["attendance_date"], rows[0]["flags"]), ("", ["date_missing"]))
                # a missing date is no attendance date of the form's summary
                self.assertEqual((counts["attendance_dates"], counts["attendance_first"]), (0, None))

    # ---- the module: the dropdown the submission used, not the copy in question 98
    def test_the_module_is_the_answer_of_the_module_dropdown_the_year_names(self):
        # question 98 is a calculation's copy of the option's VISIBLE text (the module dropdowns
        # have no calcValues), which a browser's page translation rewrites; the dropdown's own
        # answer is the option's value
        def module(**kw):
            row, = self.one({"10": [AMARA]}, **kw)
            return row["module"], row["flags"]
        self.assertEqual(module(), ("Decision Making", []))
        self.assertEqual(module(q98=TRANSLATED), ("Decision Making", ["module_translated"]))
        # each year has its own dropdown
        self.assertEqual(module(year="2", module="Relationships 201"), ("Relationships 201", []))
        self.assertEqual(module(year="3", module="Elective - Girl Boss Pro", q98="Optativa - Girl Boss Pro"),
                         ("Elective - Girl Boss Pro", ["module_translated"]))
        # any difference counts, an empty copy too - the row still gets the dropdown's answer
        self.assertEqual(module(q98=None), ("Decision Making", ["module_translated"]))
        self.assertEqual(module(q98="decision making"), ("Decision Making", ["module_translated"]))
        # a dropdown hidden again keeps its answer (the forms do not clear hidden fields): the
        # year says which one the mentor saw - here year 2, with year 1's answer still there
        # and last copied into question 98
        stale = {"14": {"name": "module1", "order": "1", "text": "Module", "type": "control_dropdown",
                        "answer": "Decision Making"}}
        self.assertEqual(module(year="2", module="Relationships 201", q98="Decision Making", extra=stale),
                         ("Relationships 201", ["module_translated"]))
        # the week and the year stay what questions 100 and 102 hold, whatever their sources say
        row, = self.one({"10": [AMARA]}, q98=TRANSLATED, q100="7", q102="3")
        self.assertEqual((row["module"], row["module_week"], row["module_year"], row["flags"]),
                         ("Decision Making", "7", "3", ["module_translated"]))
        # every row of a submission carries it, after the name flags
        rows = self.one({"10": [AMARA, AMARA], "11": [DALIA]}, q98=TRANSLATED, q5="Alpha ClubStars - Partner One",
                        picks=("Alpha Club", "Stars - Partner One"))
        self.assertEqual([r["flags"] for r in rows],
                         [["multi_club", "q5_differs", "name_repeats", "module_translated"],
                          ["multi_club", "q5_differs", "module_translated"]])
        self.assertEqual({r["module"] for r in rows}, {"Decision Making"})

    def test_a_module_that_cannot_be_told_stays_question_98_and_is_flagged(self):
        # no guess: the row keeps question 98 as submitted and carries module_unresolved (the
        # loader holds it)
        def answer(qid, value):
            return {qid: dict(questions()[qid], order="1", answer=value)}
        cases = {
            "no year picked": dict(year=None, extra=answer("14", "Decision Making")),
            "the year names no dropdown": dict(extra=answer(YEAR, "4")),
            "that year's dropdown has no answer": dict(year="2", module=None, extra=answer("14", "Decision Making")),
            "the answer is no option of the dropdown today": dict(module="Retired Module"),
            "the answer is another year's module": dict(module="Relationships 201"),
            "the answer is not text": dict(extra=answer("14", ["Decision Making"])),
            "the answer is the translated text": dict(module=TRANSLATED),
        }
        for what, kw in cases.items():
            with self.subTest(what):
                row, = self.one({"10": [AMARA]}, **dict({"q98": TRANSLATED}, **kw))
                self.assertEqual((row["module"], row["flags"]), (TRANSLATED, ["module_unresolved"]))
        # nothing in question 98 either: null, never a made-up text
        row, = self.one({"10": [AMARA]}, year=None, module=None, q98=None)
        self.assertEqual((row["module"], row["flags"]), (None, ["module_unresolved"]))
        # a form without that module dropdown
        gone = {q: v for q, v in questions().items() if q != "14"}
        rows, _, _ = self.resolve([submission("9001", {"10": [AMARA]})], qs=gone)
        self.assertEqual((rows[0]["module"], rows[0]["flags"]), ("Decision Making", ["module_unresolved"]))

    def test_week_and_year_are_compared_with_their_dropdowns_and_only_counted(self):
        # questions 100 and 102 are copies too (of the session dropdown's and the year
        # dropdown's calcValue): compared the same way, reported per form, never flagged
        def verdicts(**kw):
            rows, _, counts = self.resolve([submission("9001", {"10": [AMARA]}, **kw)])
            self.assertEqual(rows[0]["flags"], [f for f in ("module_translated", "module_unresolved")
                                                if f in rows[0]["flags"]])          # no flag of their own
            got = {f: [v for v, n in c.items() if n] for f, c in counts["copied_fields"].items()}
            self.assertEqual(counts["copied_fields"], counts["copied_fields_with_ticks"])
            return got["module"], got["week"], got["year"], rows[0]["module_week"], rows[0]["module_year"]
        self.assertEqual(verdicts(), (["same"], ["same"], ["same"], "3", "1"))
        self.assertEqual(verdicts(q100="4", q102="2"), (["same"], ["differ"], ["differ"], "4", "2"))
        self.assertEqual(verdicts(q100="Session 3"), (["same"], ["differ"], ["same"], "Session 3", "1"))
        self.assertEqual(verdicts(q100=None, q102=None), (["same"], ["differ"], ["differ"], None, None))
        self.assertEqual(verdicts(q98=TRANSLATED)[:3], (["differ"], ["same"], ["same"]))
        # the session dropdown is the one the form shows for the year and the module
        for year, module, qid in (("1", "Relationships 101", "15"), ("2", "Relationships 201", "15"),
                                  ("2", "Elective - Healthy GLOW", "96"), ("2", "Elective - Girl Boss Basics", "95"),
                                  ("3", "Elective - Girl Boss Pro", "97"), ("3", "Power of Girls 301", "15")):
            with self.subTest(module=module):
                self.assertEqual(br.session_dropdown(year, module), qid)
                self.assertEqual(verdicts(year=year, module=module, week="Session 8")[:3], (["same"],) * 3)
                self.assertEqual(verdicts(year=year, module=module, week="Session 8", q100="2")[1], ["differ"])
        # no source to compare with: counted apart
        stray = {"95": dict(questions()["95"], order="1", answer="Session 9")}
        self.assertEqual(verdicts(week=None, q100="9", extra=stray)[:3], (["same"], ["undetermined"], ["same"]))
        self.assertEqual(verdicts(week="Session 99")[1], ["undetermined"])
        self.assertEqual(verdicts(year=None, module=None)[:3], (["undetermined"],) * 3)
        self.assertEqual(verdicts(year="2", module=None)[:3], (["undetermined"], ["undetermined"], ["same"]))
        self.assertEqual(verdicts(year="1", module=None)[:3], (["undetermined"], ["same"], ["same"]))
        # counted over every submission in range, and apart for the ones with ticks
        rows, _, counts = self.resolve([submission("9001", {"10": [AMARA]}, q98=TRANSLATED),
                                        submission("9002", {}, q98=TRANSLATED, q100="5"),
                                        submission("9003", {"10": [BEA]}, q102="3"),
                                        submission("9004", {"10": [BEA]}, created="2026-08-30 10:00:00", q102="3")])
        self.assertEqual(counts["copied_fields"], {
            "module": {"same": 1, "differ": 2, "undetermined": 0},
            "week": {"same": 2, "differ": 1, "undetermined": 0},
            "year": {"same": 2, "differ": 1, "undetermined": 0}})
        self.assertEqual(counts["copied_fields_with_ticks"], {
            "module": {"same": 1, "differ": 1, "undetermined": 0},
            "week": {"same": 2, "differ": 0, "undetermined": 0},
            "year": {"same": 1, "differ": 1, "undetermined": 0}})
        self.assertEqual((counts["flags"]["module_translated"], counts["flags"]["module_unresolved"]), (1, 0))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            br.report("Africa", counts)
        self.assertRegex(out.getvalue(), r"module \(question 98\) +same +1 \(1\) +differ +2 \(1\) +source not determined +0 \(0\)\n")
        self.assertRegex(out.getvalue(), r"session \(question 100\) +same +2 \(2\) +differ +1 \(0\) +source not determined +0 \(0\)\n")
        self.assertRegex(out.getvalue(), r"year \(question 102\) +same +2 \(1\) +differ +1 \(1\) +source not determined +0 \(0\)\n")
        self.assertNotIn(TRANSLATED, out.getvalue())

    def test_name_flags(self):
        comma = "Marrowgate, Beatrice"
        row, = self.one({"10": [AMARA, STRANGER, STRANGER2]})
        self.assertEqual(row["flags"], ["name_unknown_to_roster:2"])
        self.assertEqual(row["names"], [AMARA, STRANGER, STRANGER2])       # still listed
        row, = self.one({"10": [AMARA, comma]}, q18=f"{AMARA}, {comma}")
        self.assertEqual(row["flags"], ["q18_differs", "name_unknown_to_roster:1", "name_has_comma"])
        row, = self.one({"10": [AMARA, BEA, AMARA]})
        self.assertEqual(row["flags"], ["name_repeats"])

    def test_a_name_that_is_no_option_today_is_unknown_to_the_roster_or_left_it(self):
        # the loader holds a session on name_unknown_to_roster (Salesforce would create a new
        # Contact for a mistyped or renamed girl) and sends a girl who left the club. These two
        # are the only name flags, and the only flags written with a count
        def flags(*names, qid="10", **kw):
            rows, _, counts = self.resolve([submission("9001", {qid: list(names)}, **kw)])
            return rows[0]["flags"], counts["names_active_not_an_option"]
        # an option of the roster today is never flagged
        self.assertEqual(flags(AMARA, BEA, CHIARA), ([], 0))
        # she left: the club's only Roster row of that name is inactive
        self.assertEqual(flags(AMARA, NADIA), (["name_left_roster:1"], 0))
        # the Roster never had that name for this club
        self.assertEqual(flags(AMARA, STRANGER), (["name_unknown_to_roster:1"], 0))
        # both in one row, each with its own count, 'left' first
        self.assertEqual(flags(NADIA, STRANGER, AMARA, STRANGER2),
                         (["name_left_roster:1", "name_unknown_to_roster:2"], 0))
        # an option is compared exactly, the Roster by capitals and spaces only. A tick spelled
        # unlike today's option that way is an ACTIVE girl of the club: no flag, but counted
        self.assertEqual(flags(AMARA.upper()), ([], 1))
        self.assertEqual(flags(NADIA.upper().replace(" ", "   ")), (["name_left_roster:1"], 0))
        # a letter differs: unknown
        self.assertEqual(flags(AMARA.replace("whistle", "whistel")), (["name_unknown_to_roster:1"], 0))
        # she left and came back (an inactive row and an active one): she has not left
        self.assertEqual(flags(BEA.lower(), NADIA), (["name_left_roster:1"], 1))
        # a girl of ANOTHER club is unknown to this one
        self.assertEqual(flags(DALIA), (["name_unknown_to_roster:1"], 0))
        # a club with no active row at all: a name that is no option today left with the rest
        self.assertEqual(flags(HANA.upper(), qid="13", q5="Old Club", picks=("Old Club",)),
                         (["retired_club", "name_left_roster:1"], 0))
        # a roster whose partner cannot be told (two partners have the name): no Roster rows
        # to ask, so a name that is no option today is unknown
        self.assertEqual(flags(OLIVIA, PRIYA, qid="23", q5="Twin Club", picks=("Twin Club",)),
                         (["retired_club", "name_unknown_to_roster:1"], 0))
        # counted per form by the bare name, like every flag; the old wider flag is gone
        rows, _, counts = self.resolve([submission("9001", {"10": [NADIA, STRANGER]}),
                                        submission("9002", {"10": [NADIA]})])
        self.assertEqual([counts["flags"][f] for f in ("name_left_roster", "name_unknown_to_roster")], [2, 1])
        self.assertNotIn("name_not_on_roster_now", counts["flags"])
        self.assertNotIn("name_not_on_roster_now", json.dumps(rows))
        self.assertNotIn("name_not_on_roster_now", br.FLAGS)
        # the unflagged case is printed, as a count, only when there is one
        def said(subs):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                br.report("Africa", self.resolve(subs)[2])
            return out.getvalue()
        line = "ticked name(s) are not an option of their roster today but an ACTIVE girl"
        self.assertIn("   2 " + line, said([submission("9001", {"10": [AMARA.upper(), BEA.lower()]})]))
        self.assertNotIn(line, said([submission("9001", {"10": [AMARA, NADIA]})]))

    def test_the_flag_list_is_the_contract(self):
        self.assertEqual(br.FLAGS, [
            "multi_club", "q5_differs", "q18_empty", "q18_differs", "typed_era", "bare_shared_name",
            "retired_club", "no_account_name", "date_before_2026_09", "date_missing",
            "name_left_roster", "name_unknown_to_roster",          # the only two written with ":<n>"
            "name_has_comma", "name_repeats", "module_translated", "module_unresolved"])

    # ---- no ticks, the range, the ledger
    def test_no_tick_means_no_row_and_the_id_is_listed(self):
        subs = [submission("9001", {"10": [AMARA]}), submission("9002", {}),
                submission("9003", {"10": ["  "]}), submission("9004", {}, q18=AMARA)]
        rows, no_ticks, counts = self.resolve(subs)
        self.assertEqual([r["submission_id"] for r in rows], ["9001"])
        self.assertEqual(no_ticks, ["9002", "9003", "9004"])
        self.assertEqual((counts["submissions"], counts["with_ticks"], counts["no_ticks"], counts["rows"]),
                         (4, 1, 3, 1))
        self.assertEqual(counts["no_ticks_but_q18"], ["9004"])    # names in question 18, no tick to be seen

    def test_the_range_starts_2026_09_01_us_eastern_and_has_no_end(self):
        subs = [submission("9001", {"10": [AMARA]}, created="2026-08-31 23:59:59"),
                submission("9002", {"10": [AMARA]}, created="2026-09-01 00:00:00"),
                submission("9003", {"10": [AMARA]}, created="2026-11-05 10:00:00"),
                submission("9004", {}, created="2026-08-28 01:00:00")]
        rows, no_ticks, counts = self.resolve(subs)
        self.assertEqual([(r["submission_id"], r["created_at"]) for r in rows],
                         [("9002", "2026-09-01 00:00:00"), ("9003", "2026-11-05 10:00:00")])
        self.assertEqual((counts["pre_launch"], counts["submissions"], no_ticks), (2, 2, []))
        self.assertEqual((counts["created_first"], counts["created_last"]),
                         ("2026-09-01 00:00:00", "2026-11-05 10:00:00"))

    def test_only_active_submissions(self):
        subs = [submission("9001", {"10": [AMARA]}), submission("9002", {"10": [BEA]}, status="DELETED")]
        rows, _, counts = self.resolve(subs)
        self.assertEqual([r["submission_id"] for r in rows], ["9001"])
        self.assertEqual((counts["fetched"], counts["not_active"], counts["submissions"]),
                         (2, {"DELETED": 1}, 1))

    def test_a_ledger_that_does_not_balance_stops_the_run(self):
        twice = [submission("9001", {"10": [AMARA]}), submission("9001", {"10": [AMARA]})]
        self.refused(lambda: self.resolve(twice), "the ledger does not balance", "No result written")
        twice = [submission("9001", {}), submission("9001", {})]
        self.refused(lambda: self.resolve(twice), "the ledger does not balance")

    # ---- what each roster is comes from the sync
    def test_the_club_name_a_roster_sends_today_not_after_the_plan(self):
        changing = plan(sf_name_changes=[{"qid": "10", "club": "Alpha Club", "old": "Alpha Club",
                                          "new": "Alpha Club - Partner One", "switch": False}])
        changing["sf_names"][0]["value"] = "Alpha Club - Partner One"
        today = br.rosters_today(changing)
        self.assertEqual(today["10"], ("Alpha Club", "Partner One", "Alpha Club"))
        self.assertEqual(today["24"], ("Lost Club", None, "Lost Club"))
        self.assertEqual(sorted(today, key=int), sorted(ROSTERS, key=int))          # no club still to create

    def test_the_sync_is_run_as_a_dry_run_and_its_output_is_not_echoed(self):
        seen = {}

        def runner(argv, **kw):
            seen["argv"], seen["kw"] = argv, kw
            with open(argv[argv.index("--summary-json") + 1], "w", encoding="utf-8") as f:
                json.dump(plan(), f)
            return mock.Mock(returncode=0, stdout=f"  ! {AMARA} appears twice", stderr="")

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            got = br.sync_plan("roster.csv", "Latin America", "123", runner=runner)
        self.assertEqual(got["sf_names"], plan()["sf_names"])
        self.assertEqual(out.getvalue(), "")
        argv = seen["argv"]
        self.assertTrue(argv[1].endswith("sync_attendance_form.py"))
        self.assertEqual(argv[2:9], ["roster.csv", "--roster", "--region", "Latin America",
                                     "--form", "123", "--summary-json"])
        self.assertEqual(len(argv), 10)
        self.assertNotIn("--apply", argv)
        self.assertNotIn("--prune", argv)
        self.assertTrue(seen["kw"]["capture_output"])

    def test_a_failed_dry_run_or_an_applied_plan_is_refused(self):
        failed = lambda argv, **kw: mock.Mock(returncode=1, stdout=AMARA, stderr=AMARA)   # noqa: E731
        self.refused(lambda: br.sync_plan("roster.csv", "Asia", "123", runner=failed),
                     "Asia: the sync's dry run exited 1", "--region 'Asia' --form 123")

        def applied(argv, **kw):
            with open(argv[argv.index("--summary-json") + 1], "w", encoding="utf-8") as f:
                json.dump(plan(apply=True), f)
            return mock.Mock(returncode=0, stdout="", stderr="")
        self.refused(lambda: br.sync_plan("roster.csv", "Asia", "123", runner=applied),
                     "not a dry run's plan")

    def test_club_codes_come_from_the_girl_ids(self):
        rows, active, codes, holders, known, on = self.roster
        self.assertEqual(rows, SHEET_ROWS)
        self.assertEqual(codes[("partner one", "stars")], ["STARS"])
        self.assertEqual(codes[("partner two", "old club")], ["OLDCLUB"])
        self.assertIn(("partner two", "stars"), active)
        self.assertNotIn(("partner two", "old club"), active)
        # who has, or had, a club of each name (any status, any region) and every girl it held
        self.assertEqual(holders["quiet club"], {"partner two": "Partner Two"})
        self.assertEqual(sorted(holders["twin club"]), ["partner one", "partner two"])
        self.assertEqual(len(known[("partner one", "alpha club")]), 4)
        # ... and the ones with an active row: she who left is not one, she who came back is
        self.assertEqual(len(on[("partner one", "alpha club")]), 3)
        self.assertNotIn(("partner two", "old club"), on)
        two = self.roster._replace(codes={**codes, ("partner one", "alpha club"): ["ALPHA2", "ALPHACLU"]})
        self.refused(lambda: br.resolve("Africa", AFRICA, [submission("9001", {"10": [AMARA]})],
                                        questions(), br.rosters_today(plan()), two),
                     "'Alpha Club' (Partner One)", "2 different club codes (ALPHA2, ALPHACLU)")
        path = os.path.join(self.out_dir.name, "no_ids.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows([["partner", "club", "region", "full_name", "status"],
                                     ["Partner One", "Alpha Club", "Africa", AMARA, "active"]])
        self.refused(lambda: br.read_roster(path), "no girl_id column")

    # ---- refusals: an answer it cannot resolve honestly
    def test_answer_shapes_it_does_not_know_are_refused(self):
        nameless = {"158": {"answer": [AMARA]}}                                  # no type, no text
        textless = {"158": {"type": "control_checkbox", "answer": [AMARA]}}
        cases = [
            (submission("9001", {}, extra=nameless),
             ("submission 9001", "q158 is answered but is not on the form any more")),
            (submission("9001", {}, extra=textless),
             ("ticked roster q158 is not on the form any more", "cannot be identified")),
            (submission("9001", {"10": {"0": AMARA}}, q18=""), ("roster q10 is answered with a dict",)),
            (submission("9001", {"10": AMARA}, q18=""), ("roster q10 is answered with a str",)),
            (submission("9001", {"10": [AMARA]}, q5=["Alpha Club"]), ("q5 is answered with a list",)),
            (submission("9001", {"10": [AMARA]}, photo=({"url": PHOTO},)), ("the photo (q19)",)),
            (submission("9001", {"10": [AMARA]}, picks=({"club": "Alpha Club"},)), ("the Club picker (q500)",)),
            (submission("9001", {"10": [AMARA]}, created="10/09/2026 08:00"), ("its created_at is not",)),
        ]
        for sub, fragments in cases:
            with self.subTest(fragments[0]):
                self.refused(lambda: self.resolve([sub]), *fragments)
        # an unanswered leftover of a deleted question is nothing to refuse
        rows, _, _ = self.resolve([submission("9001", {"10": [AMARA]}, extra={"158": {"answer": ""}})])
        self.assertEqual(len(rows), 1)

    def test_a_roster_on_the_form_that_the_plan_does_not_know_is_refused(self):
        short = plan()
        short["sf_names"] = [n for n in short["sf_names"] if n["qid"] != "12"]
        self.refused(lambda: self.resolve([submission("9001", {"12": [FATIMA]})], the_plan=short),
                     "roster q12 is on the form but not in the sync's plan")

    # ---- the whole tool
    def test_main_writes_the_contract_and_prints_counts_only(self):
        africa = [submission("9001", {"10": [AMARA, BEA]}),
                  submission("9002", {"10": [CHIARA], "11": [DALIA]}, q5="Alpha ClubStars - Partner One",
                             picks=("Alpha Club", "Stars - Partner One")),
                  submission("9003", {}, q5="Stars", picks=()),
                  submission("9004", {"12": [FATIMA, GRACE]}, q5="Stars", picks=(), q18=""),
                  submission("9005", {"10": [AMARA]}, created="2026-08-28 09:00:00"),
                  submission("9006", {"13": [HANA]}, q5="Old Club", picks=("Old Club",),
                             date=("2026", "08", "20"), created="2026-09-20 10:00:00")]
        asia = [submission("9101", {"10": [BEA]}, form=ASIA)]
        client = FakeJotform({AFRICA: list(reversed(africa)), ASIA: asia})
        with mock.patch.object(br, "PAGE", 2):
            out, code, result = self.run_main(client)
        self.assertIsNone(code, out)
        # reads only, page by page, newest first as Jotform serves them
        pages = [p for path, p in client.asked if path == f"/form/{AFRICA}/submissions"]
        self.assertEqual(pages, [{"limit": 2, "offset": n} for n in (0, 2, 4, 6)])
        self.assertFalse([a for a in dir(client) if a.startswith(("post", "put", "delete"))])

        self.assertEqual(list(result), ["fetched_at_utc", "resolver_commit", "roster_export", "forms",
                                        "no_ticks", "rows"])
        self.assertRegex(result["fetched_at_utc"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertRegex(result["resolver_commit"], r"^([0-9a-f]{7,}(-dirty)?|unknown)$")
        self.assertEqual(result["roster_export"]["rows"], SHEET_ROWS)
        self.assertEqual(list(result["forms"]), list(glow_forms.REGIONALS))
        a = result["forms"]["Africa"]
        self.assertEqual({k: a[k] for k in ("form_id", "submissions", "pre_launch", "rows", "no_ticks")},
                         {"form_id": AFRICA, "submissions": 5, "pre_launch": 1, "rows": 5, "no_ticks": 1})
        self.assertEqual(a["flags"], dict.fromkeys(br.FLAGS, 0) | {
            "multi_club": 2, "q5_differs": 3, "q18_empty": 1, "q18_differs": 0, "typed_era": 1,
            "bare_shared_name": 1, "retired_club": 1, "date_before_2026_09": 1})
        self.assertEqual(a["flag_submissions"]["multi_club"], 1)
        self.assertEqual((a["picked_several"], a["clubs"], a["attendance_dates"]), (1, 4, 2))
        self.assertEqual(result["no_ticks"], {"Africa": ["9003"], "Asia": [], "Latin America": [], "U.S": []})
        self.assertEqual([(r["submission_id"], r["roster_qid"]) for r in result["rows"]],
                         [("9001", "10"), ("9002", "10"), ("9002", "11"), ("9004", "12"), ("9006", "13"),
                          ("9101", "10")])
        self.assertEqual(result["rows"][-1]["region"], "Asia")
        self.assertEqual(set(result["rows"][0]), {
            "region", "form_id", "submission_id", "created_at", "roster_qid", "club_code", "club",
            "partner", "sf_account_name", "attendance_date", "names", "module", "module_week",
            "module_year", "creator", "photo_urls", "q5", "flags"})
        # the raw copies: as fetched (the pre-launch one too), stamped, one per region
        raw_dir = os.path.join(self.out_dir.name, "raw")
        self.assertEqual(sorted(os.listdir(raw_dir)), sorted(f"{r}.json" for r in glow_forms.REGIONALS))
        with open(os.path.join(raw_dir, "Africa.json"), encoding="utf-8") as f:
            raw = json.load(f)
        self.assertEqual((raw["fetched_at_utc"], raw["form_id"], len(raw["submissions"])),
                         (result["fetched_at_utc"], AFRICA, 6))

        # what is printed: counts, never a name
        for private in EVERY_NAME + [MENTOR, PHOTO] + [n.split()[-1] for n in EVERY_NAME]:
            self.assertNotIn(private, out)
        self.assertIn("== Africa  form " + AFRICA, out)
        self.assertIn("fetched 6   not active, left out 0   pre-launch, left out 1", out)
        self.assertIn("submissions in range 5   with ticks 4   no ticks 1   rows 5", out)
        self.assertIn("distinct clubs 4   distinct attendance dates 2 (2026-08-20 .. 2026-09-09)", out)
        self.assertIn("created_at (US Eastern) 2026-09-10 08:00:00 .. 2026-09-20 10:00:00", out)
        self.assertIn("several clubs picked in the Club picker: 1 submissions (1 of them with ticks)", out)
        self.assertRegex(out, r"multi_club +2 +1\n")
        self.assertRegex(out, r"name_unknown_to_roster +0 +0\n")
        self.assertNotIn("name_not_on_roster_now", out + json.dumps(result))
        self.assertIn("ledger: 4 with rows + 1 no ticks = 5 in range - balanced", out)
        self.assertIn("LEDGER: 6 submissions in range = 5 with rows (6 rows) + 1 with no tick - balanced; "
                      "1 pre-launch left out", out)
        self.assertIn("== U.S  form " + glow_forms.REGIONALS["U.S"], out)
        # the files went outside this checkout: the closing line does not call the place git-ignored
        self.assertIn("they hold girls' names", out)
        self.assertIn("outside this checkout's data/", out)
        self.assertNotIn("git-ignored", out)

    def test_main_refusals_write_no_result(self):
        subs = {AFRICA: [submission("9001", {"10": [AMARA]}), submission("9002", {"10": {"0": BEA}})]}
        out, code, result = self.run_main(FakeJotform(subs))
        self.assertIn("submission 9002", code)
        self.assertIsNone(result)
        for private in EVERY_NAME:
            self.assertNotIn(private, out + code)
        # what it says is what happened: no result, but this region's raw copy is the new fetch
        self.assertIn("no result written (the raw copies fetched so far are overwritten", code)
        self.assertNotIn("nothing written", code.lower())
        self.assertEqual(os.listdir(os.path.join(self.out_dir.name, "raw")), ["Africa.json"])
        # fewer submissions fetched than the form itself reports
        out, code, result = self.run_main(FakeJotform({AFRICA: subs[AFRICA][:1]}, count=3))
        self.assertIn("Africa: fetched 1 submissions but the form reports 3", code)
        self.assertIsNone(result)
        # the same submission on two pages (one arrived meanwhile) is counted once
        client = FakeJotform({AFRICA: [subs[AFRICA][0], subs[AFRICA][0], submission("9003", {})]}, count=2)
        with mock.patch.object(br, "PAGE", 2):
            out, code, result = self.run_main(client, "--region", "Africa")
        self.assertIsNone(code, out)
        self.assertEqual(result["forms"]["Africa"]["fetched"], 2)
        self.assertIn("1 of 4 regions", out)

    def test_a_region_named_twice_is_read_once(self):
        subs = {AFRICA: [submission("9001", {"10": [AMARA]})], ASIA: [submission("9101", {"10": [BEA]}, form=ASIA)]}
        client = FakeJotform(subs)
        out, code, result = self.run_main(client, "--region", "Asia", "--region", "Africa", "--region", "Asia")
        self.assertIsNone(code, out)                       # it doubled Asia's rows and failed the ledger
        self.assertEqual(list(result["forms"]), ["Asia", "Africa"])
        self.assertEqual([r["submission_id"] for r in result["rows"]], ["9101", "9001"])
        self.assertEqual([path for path, _ in client.asked if path.endswith("/submissions")],
                         [f"/form/{ASIA}/submissions", f"/form/{AFRICA}/submissions"])
        self.assertEqual(out.count("== Asia"), 1)

    def test_a_run_of_some_regions_never_lands_on_the_loader_s_file(self):
        # the default path is the file the loader reads, with all four forms: --region without
        # --out would replace it with a part (the loader would re-plan from a quarter of the data)
        default = os.path.join(self.out_dir.name, "default", "resolved.json")
        subs = {AFRICA: [submission("9001", {"10": [AMARA]})]}
        with mock.patch.object(br, "DEFAULT_OUT", default):
            for argv in (["--region", "Asia"], ["--region", "Asia", "--region", "Africa"],
                         ["--region", "Asia", "--out", default]):
                with self.subTest(argv=len(argv)):
                    client = FakeJotform(subs)
                    with self.assertRaises(SystemExit) as stop:
                        br.main(["--roster", self.roster_csv, *argv], client=client)
                    self.assertIn("--region gives a result without the other forms", str(stop.exception.code))
                    self.assertIn("--out", str(stop.exception.code))
                    self.assertEqual(client.asked, [])             # refused before anything is fetched
            self.assertFalse(os.path.exists(default))
            # all four, named or not, write the default path
            every = [a for region in glow_forms.REGIONALS for a in ("--region", region)]
            for argv in (every, []):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    br.main(["--roster", self.roster_csv, *argv], client=FakeJotform(subs),
                            plan_of=lambda *a: plan())
                with open(default, encoding="utf-8") as f:
                    self.assertEqual(list(json.load(f)["forms"]), list(glow_forms.REGIONALS))
                os.remove(default)

    # ---- a failed fetch says nothing of what it fetched
    def test_a_cut_off_submissions_page_is_never_quoted(self):
        # a page cut off in transfer is a JSON prefix that starts with a submission's id and
        # the submitter's IP address (then the answers): glow.jotform.Client quoted its start
        page = json.dumps({"responseCode": 200, "message": "success",
                           "content": [submission("9001", {"10": [AMARA, BEA]})]})
        cut = page[:page.index(BEA) + len(BEA)]
        self.assertIn(IP, cut[:200])

        def curl(stdout, stderr="", code=0):
            return lambda argv, **kw: subprocess.CompletedProcess(argv, code, stdout=stdout, stderr=stderr)

        def fetch(answer):
            client = glow_jotform.Client("KEY", retries=3, backoff=0, sleep=lambda s: None)
            out = io.StringIO()
            with mock.patch.object(glow_jotform.subprocess, "run", answer), contextlib.redirect_stdout(out):
                with self.assertRaises(glow_jotform.JotformError) as stop:
                    br.fetch_submissions(client, AFRICA, "Africa")
            return str(stop.exception) + out.getvalue()

        said = fetch(curl(cut, "curl: (18) transfer closed with outstanding read data remaining", 18))
        for private in (IP, "9001", AMARA, BEA, MENTOR, "responseCode"):
            self.assertNotIn(private, said)
        self.assertIn(f"GET /form/{AFRICA}/submissions: non-JSON response: a cut-off JSON answer, "
                      f"{len(cut)} characters, not shown", said)
        self.assertIn("curl: (18)", said)                  # curl's own word is the diagnosis
        self.assertEqual(said.count("retrying"), 2)
        # what is not API content is still quoted, and Jotform's own refusal still reads as it did
        self.assertIn("non-JSON response: '<html>504 Gateway Time-out</html>'",
                      fetch(curl("<html>504 Gateway Time-out</html>")))
        self.assertIn("401 You're not authorized",
                      fetch(curl(json.dumps({"responseCode": 401, "message": "You're not authorized"}))))

    def test_the_result_may_not_land_in_the_repository_outside_data(self):
        for argv in (["--out", os.path.join(REPO, "resolved.json")],
                     ["--out", os.path.join(REPO, "docs", "backfill", "resolved.json")],
                     ["--raw-dir", os.path.join(REPO, "test", "raw")]):
            with self.subTest(argv=argv[0]):
                with self.assertRaises(SystemExit) as stop:
                    br.main(["--roster", self.roster_csv, *argv], client=FakeJotform())
                self.assertIn("holds girls' names", str(stop.exception.code))
        self.assertFalse(os.path.exists(os.path.join(REPO, "resolved.json")))
        self.assertEqual(br.private_place(os.path.join(REPO, "data", "backfill_2026-09", "resolved.json"), "x"),
                         os.path.realpath(br.DEFAULT_OUT))
        self.assertTrue(br.under_data(os.path.realpath(br.DEFAULT_OUT)))
        self.assertFalse(br.under_data(os.path.realpath(os.path.join(self.out_dir.name, "resolved.json"))))
        self.assertFalse(br.under_data(os.path.realpath(REPO)))

    def test_the_checkout_is_known_by_what_it_is_not_by_how_its_path_is_spelled(self):
        # on a disk that ignores case (the Mac's) another spelling of the checkout's path is
        # the same folder; comparing path strings let names into a tracked directory
        other = os.path.join(os.path.dirname(REPO).swapcase(), os.path.basename(REPO))
        if other == REPO or not os.path.exists(other) or not os.path.samefile(other, REPO):
            self.skipTest("this disk tells capitals apart: there is no second spelling of the checkout")

        def refused_at(*steps):
            with self.assertRaises(SystemExit) as stop:
                br.private_place(os.path.join(*steps), "The result")
            self.assertIn("holds girls' names", str(stop.exception.code))
            self.assertIn("outside data/", str(stop.exception.code))

        refused_at(other, "docs", "x", "resolved.json")             # --out in the other spelling
        refused_at(other)                                           # --raw-dir: the checkout's root
        refused_at(other, "test", "raw")
        self.assertTrue(br.under_data(br.private_place(os.path.join(other, "data", "x", "resolved.json"), "x")))
        self.assertFalse(os.path.exists(os.path.join(REPO, "docs", "x")))
        # the tool itself started by the other spelling (REPO keeps what was typed), a plain path
        with mock.patch.object(br, "REPO", other):
            refused_at(REPO, "docs", "x", "resolved.json")
            self.assertTrue(br.under_data(br.private_place(os.path.join(REPO, "data", "x.json"), "x")))
        with self.assertRaises(SystemExit) as stop:
            br.main(["--roster", os.path.join(self.out_dir.name, "missing.csv")], client=FakeJotform())
        self.assertIn("No Roster export", str(stop.exception.code))

    def test_the_forms_are_the_repository_s_one_table(self):
        with open(os.path.join(REPO, "tools", "backfill_resolve.py"), encoding="utf-8") as f:
            source = f.read()
        for form_id in list(glow_forms.REGIONALS.values()) + [glow_forms.TEMPLATE]:
            self.assertNotIn(form_id, source)


if __name__ == "__main__":
    unittest.main(verbosity=1)
