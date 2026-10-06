#!/usr/bin/env python3
"""
Offline tests for tools/fix_module_values.py (imported by test/python_test.py, so `make py` runs
them). Everything here is fictional: clubs, submission and Salesforce ids are invented; the module
names are the curriculum's (not personal data). A fake org holds two batches with their rows and
answers the tool's SOQL shapes; a fake Jotform serves the template's module dropdowns and the
submissions of one regional form, filtered as the API filters.
"""
import contextlib
import copy
import io
import json
import os
import re
import stat
import sys
import tempfile
import unittest
import urllib.parse

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import fix_module_values as fmv                            # noqa: E402
from glow import forms                                     # noqa: E402
from glow.sync import MODULES, YEAR                        # noqa: E402
from sf_backfill_test import FakeOrg                       # noqa: E402

LATAM, AFRICA = forms.REGIONALS["Latin America"], forms.REGIONALS["Africa"]
SUNRISE, RIVER = "001000000000000CAA", "001000000000000CBB"
BATCH_A, BATCH_B = "a1l000000000000AAA", "a1l000000000000BBB"
OPTIONS = {"1": ["Self Advocacy", "Power of Girls 101", "Decision Making"],
           "2": ["Community 201", "Elective - Academic Engagement", "Decision Making"],   # one shared with year 1
           "3": ["Elective - Academic Engagement", "Leadership 301"]}
# the batch is created in UTC; the submission a minute earlier on Jotform's clock (US Eastern, -4 h in September)
CREATED_UTC, CREATED_EASTERN = "2026-09-24T15:03:00.000+0000", "2026-09-24 11:02:30"


def dropdown(options, calc=False):
    return {"type": "control_dropdown", "options": "|".join(options), "calcValues": "|" + "|".join(options) if calc else ""}


def questions(calc=False):
    out = {YEAR: dropdown(["1", "2", "3"], calc=True), "5": {"type": "control_textbox"}, "17": {"type": "control_datetime"}}
    out.update({MODULES[year]: dropdown(options, calc) for year, options in OPTIONS.items()})
    return out


def submission(sid, created=CREATED_EASTERN, club="Sunrise Club", date=("2026", "09", "24"), year="1",
               module="Decision Making", q98="Toma de decisiones", week="8", form=LATAM):
    answers = {"5": {"answer": club}, "17": {"answer": {"year": date[0], "month": date[1], "day": date[2]}},
               YEAR: {"answer": year}, MODULES[year]: {"answer": module}, "98": {"answer": q98}, "100": {"answer": week},
               "102": {"answer": year}}
    return {"id": sid, "form_id": form, "created_at": created, "status": "ACTIVE", "answers": answers}


def batch(bid, created=CREATED_UTC, club="Sunrise Club", account=SUNRISE, date="2026-09-24", module="Toma de decisiones",
          year=1.0, week=8.0, status="Success", region="South America"):
    return {"Id": bid, "Account_Name__c": club, "Account__c": account, "Account__r": {"Parent": {"Region__c": region}},
            "Attendance_Date__c": date, "Module__c": module, "Module_Week__c": week, "Module_Year__c": year,
            "Processing_Status__c": status, "Creator__c": "Jotform", "CreatedDate": created}


def rows_of(bid, n, module="Toma de decisiones"):
    return [{"Id": f"a1m{bid[-3:]}{i:012d}", "Attendance_Batch__c": bid, "Module__c": module} for i in range(n)]


class ModuleOrg(FakeOrg):
    """The shared fake org (sf_backfill_test), answering this tool's three SOQL shapes."""

    def __init__(self, batches, rows):
        super().__init__([])
        self.batches, self.rows = batches, rows

    def call(self, *args, **kwargs):
        raise AssertionError("a raw REST call: every read must be an explicit-field SOQL query")

    def query(self, soql):
        self.seen.append(soql)
        if m := re.fullmatch(r"SELECT (.*) FROM Attendance_Batch__c WHERE CreatedDate >= (\S+) ORDER BY CreatedDate", soql):
            assert m.group(1) == fmv.BATCH_FIELDS, soql
            return copy.deepcopy([b for b in self.batches if b["CreatedDate"] >= m.group(2)])
        if m := re.fullmatch(r"SELECT Id, Module__c FROM Attendance__c WHERE Attendance_Batch__c = '(\w+)'", soql):
            return [{"Id": r["Id"], "Module__c": r["Module__c"]} for r in self.rows if r["Attendance_Batch__c"] == m.group(1)]
        if m := re.fullmatch(r"SELECT Id, Module__c FROM (\w+) WHERE Id = '(\w+)'", soql):
            records = self.batches if m.group(1) == "Attendance_Batch__c" else self.rows
            return [{"Id": r["Id"], "Module__c": r["Module__c"]} for r in records if r["Id"] == m.group(2)]
        raise AssertionError(soql)


class FakeJotform:
    """Reads only. The template and the regional forms share one questions table here."""

    def __init__(self, submissions, qs=None):
        self.submissions, self.qs, self.asked = submissions, qs or questions(), []     # form id -> [submission]

    def get(self, path, **params):
        self.asked.append((path, params))
        parts = path.strip("/").split("/")
        if parts[2:] == ["questions"]:
            return copy.deepcopy(self.qs)
        subs = self.submissions.get(parts[1], [])
        if parts[2:] == ["submissions"]:
            if "filter" in params:
                assert "{" not in params["filter"] and '"' not in params["filter"], "the filter must be URL-encoded"
                window = json.loads(urllib.parse.unquote(params["filter"]))
                subs = [s for s in subs if window["created_at:gt"] < s["created_at"] < window["created_at:lt"]]
            return copy.deepcopy(subs[params["offset"]:params["offset"] + params["limit"]])
        return {"id": parts[1], "count": str(len(subs))}


class FixModuleValues(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.org = ModuleOrg([batch(BATCH_A), batch(BATCH_B, created="2026-09-17T15:03:00.000+0000", date="2026-09-17",
                                                  status="Failed", week=7.0)],
                             rows_of(BATCH_A, 2))
        self.jotform = FakeJotform({LATAM: [submission("9001"),
                                            submission("9002", created="2026-09-17 11:02:30", date=("2026", "09", "17"), week="7")]})

    def run_tool(self, *argv, org=None, client=None):
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                fmv.main(["--dir", self.tmp.name] + list(argv), org=org or self.org, client=client or self.jotform)
        except SystemExit as stop:
            return out.getvalue(), str(stop.code)
        return out.getvalue(), None

    def dry(self, *argv):
        out, stop = self.run_tool("--vpn-off", *argv)
        self.assertIsNone(stop, stop)
        return out

    def apply(self, *argv):
        return self.run_tool("--vpn-off", "--apply", *argv)

    def ledger(self):
        return fmv.read_ledger(os.path.join(self.tmp.name, "ledger.csv"))

    def outcomes(self):
        return [r["outcome"] for r in self.ledger()]

    # ---- the pairing
    def test_the_region_map_names_the_four_live_forms(self):
        self.assertEqual(sorted(fmv.SF_REGION_FORM), ["Africa", "Asia", "North America", "South America"])
        self.assertEqual(sorted(fmv.SF_REGION_FORM.values()), sorted(forms.REGIONALS.values()))

    def test_a_dry_run_pairs_each_batch_with_its_one_submission_and_writes_nothing(self):
        out = self.dry()
        self.assertIn(f"canonical modules: 6 (template {forms.TEMPLATE}: q14 3, q92 3, q93 2 options)", out)
        self.assertIn("batches since 2026-09-01: 2; module not a canonical option: 2 (1 Failed, 1 Success); rows under them: 2", out)
        self.assertIn(f"  {BATCH_A}  Sunrise Club  2026-09-24  Success  'Toma de decisiones' -> 'Decision Making'  "
                      f"(Latin America {LATAM}, submission 1 candidate(s), year 1, session 8; 2 rows; "
                      "created 2026-09-24T15:03:00 UTC)", out)
        self.assertIn(f"  {BATCH_B}  Sunrise Club  2026-09-17  Failed  'Toma de decisiones' -> 'Decision Making'  "
                      f"(Latin America {LATAM}, submission 1 candidate(s), year 1, session 7; 0 rows", out)
        self.assertIn("would write: 2 batches, 2 rows   (dry run - nothing written; --apply --vpn-off after Ryan's go)", out)
        self.assertEqual((self.org.updates, os.path.exists(os.path.join(self.tmp.name, "ledger.csv"))), ([], False))
        # one Jotform read per batch, on the region's form only, inside a URL-encoded 6-hour window around CreatedDate
        fetched = [(p, q) for p, q in self.jotform.asked if p.endswith("/submissions")]
        self.assertEqual([p for p, _ in fetched], [f"/form/{LATAM}/submissions"] * 2)
        window = json.loads(urllib.parse.unquote(fetched[0][1]["filter"]))
        self.assertEqual(window, {"created_at:gt": "2026-09-24 08:03:00", "created_at:lt": "2026-09-24 14:03:00"})
        self.assertNotIn(AFRICA, "".join(p for p, _ in self.jotform.asked))
        # every Salesforce read is an explicit-field SOQL query, never the names list or the status message
        self.assertTrue(self.org.seen)
        self.assertFalse(any("Contact_IDs__c" in s or "Status_Message__c" in s or "SELECT *" in s for s in self.org.seen))

    def test_a_year_or_session_is_compared_as_a_whole_number(self):
        self.assertEqual([fmv.as_int(v) for v in (1.0, "1", 8, " 8 ", 8.5, "8.0", "", None, True, "x")],
                         [1, 1, 8, 8, None, None, None, None, None, None])
        self.org.batches[0]["Module_Week__c"] = 8          # an integer instead of Salesforce's double
        self.assertIn("-> 'Decision Making'", self.dry())

    def test_every_unmatched_reason_is_listed_and_nothing_is_written_for_it(self):
        self.org.batches = [
            batch("a1l00000000000NONE", date="2026-09-25"),                            # no submission of that date
            batch("a1l00000000000TWO0", created="2026-09-30T15:03:00.000+0000", date="2026-09-30"),
            batch("a1l00000000000YEAR", created="2026-10-01T15:03:00.000+0000", date="2026-10-01"),  # the form says year 2
            batch("a1l00000000000HALF", week=8.5),
            batch("a1l00000000000WHER", region="Europe"),
            batch("a1l00000000000GONE", created="2026-10-02T15:03:00.000+0000", date="2026-10-02"),  # option left the form
            batch(BATCH_A)]
        self.jotform.submissions[LATAM] += [
            submission("9003", created="2026-09-30 11:02:00", date=("2026", "09", "30")),
            submission("9004", created="2026-09-30 11:04:00", date=("2026", "09", "30")),
            submission("9005", created="2026-10-01 11:02:00", date=("2026", "10", "01"), year="2", module="Community 201"),
            submission("9006", created="2026-10-02 11:02:00", date=("2026", "10", "02"), module="Retired Module")]
        out = self.dry()
        self.assertIn("a1l00000000000NONE  Sunrise Club  2026-09-25  Success  'Toma de decisiones'  UNMATCHED (0 candidates)", out)
        self.assertIn("a1l00000000000TWO0  Sunrise Club  2026-09-30  Success  'Toma de decisiones'  UNMATCHED (2 candidates)", out)
        self.assertIn("a1l00000000000YEAR  Sunrise Club  2026-10-01  Success  'Toma de decisiones'  UNMATCHED (0 candidates)", out)
        self.assertIn("a1l00000000000HALF  Sunrise Club  2026-09-24  Success  'Toma de decisiones'  UNMATCHED (year or session "
                      "is not a whole number)", out)
        self.assertIn("a1l00000000000WHER  Sunrise Club  2026-09-24  Success  'Toma de decisiones'  UNMATCHED (region 'Europe' "
                      "names no form)", out)
        self.assertIn("a1l00000000000GONE  Sunrise Club  2026-10-02  Success  'Toma de decisiones'  UNMATCHED (the submission's "
                      "module dropdown holds no option of the form today)", out)
        self.assertIn(f"{BATCH_A}  Sunrise Club  2026-09-24  Success  'Toma de decisiones' -> 'Decision Making'", out)
        self.assertIn("would write: 1 batches, 2 rows; UNMATCHED, left alone: 6", out)
        out, stop = self.apply()
        self.assertIsNone(stop, stop)
        self.assertEqual({r for _, r, _ in self.org.updates}, {BATCH_A} | {r["Id"] for r in rows_of(BATCH_A, 2)})

    def test_all_forms_reads_the_four_forms_whole_and_serves_a_region_the_map_does_not_know(self):
        self.org.batches = [batch(BATCH_A, region="Europe")]
        self.jotform.submissions[AFRICA] = [submission("9007", created="2026-09-24 11:02:30", form=AFRICA, club="River Club")]
        self.assertIn("UNMATCHED (region 'Europe' names no form)", self.dry())
        self.jotform.asked.clear()
        out = self.dry("--all-forms")
        self.assertIn(f"-> 'Decision Making'  (Latin America {LATAM}, submission 1 candidate(s)", out)
        fetched = [(p, q) for p, q in self.jotform.asked if p.endswith("/submissions")]
        self.assertEqual(sorted(p for p, _ in fetched), sorted(f"/form/{fid}/submissions" for fid in forms.REGIONALS.values()))
        self.assertFalse(any("filter" in q for _, q in fetched))

    def test_a_clean_org_says_so_without_reading_a_submission(self):
        for b in self.org.batches:
            b["Module__c"] = "Decision Making"
        out = self.dry()
        self.assertIn("nothing to correct: 0 of 2 batches since 2026-09-01 carry a module outside the 6 canonical options", out)
        self.assertEqual([p for p, _ in self.jotform.asked], [f"/form/{forms.TEMPLATE}/questions"])

    def test_the_template_without_module_options_is_a_refusal(self):
        self.jotform.qs[MODULES["2"]] = {"type": "control_dropdown", "options": ""}
        self.assertIn("module dropdown q92 (year 2) is not a dropdown with options", self.run_tool("--vpn-off")[1])

    # ---- the writes
    def test_apply_writes_the_batch_then_its_rows_each_with_an_open_and_a_closing_ledger_row(self):
        out, stop = self.apply("--limit", "1")
        self.assertIsNone(stop, stop)
        self.assertEqual([(s, r, b) for s, r, b in self.org.updates],
                         [("Attendance_Batch__c", BATCH_A, {"Module__c": "Decision Making"})]
                         + [("Attendance__c", r["Id"], {"Module__c": "Decision Making"}) for r in rows_of(BATCH_A, 2)])
        self.assertEqual(self.outcomes(), ["open", "written"] * 3)
        self.assertEqual([(r["batch_id"], r["sobject"], r["old"], r["new"]) for r in self.ledger()][::2],
                         [(BATCH_A, "Attendance_Batch__c", "Toma de decisiones", "Decision Making")]
                         + [(BATCH_A, "Attendance__c", "Toma de decisiones", "Decision Making")] * 2)
        self.assertIn(f"  {BATCH_A}  Sunrise Club  2026-09-24  Success  'Toma de decisiones' -> 'Decision Making': batch "
                      "written and read back equal; 2 rows written and read back equal; rows 2 before, 2 after", out)
        self.assertIn("written and read back: 1 batches, 2 rows; ledger", out)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.tmp.name, "ledger.csv")).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(self.tmp.name).st_mode), 0o700)
        self.assertEqual(self.org.batches[1]["Module__c"], "Toma de decisiones")       # --limit 1: the second waits
        out, stop = self.apply()
        self.assertIsNone(stop, stop)
        self.assertEqual(self.outcomes(), ["open", "written"] * 4)
        self.assertEqual({b["Module__c"] for b in self.org.batches} | {r["Module__c"] for r in self.org.rows}, {"Decision Making"})
        self.assertIn("nothing to correct", self.dry())

    def test_a_refused_write_closes_its_ledger_row_and_stops_the_run(self):
        self.org.refuse_update = True
        out, stop = self.apply()
        self.assertIn(f"{BATCH_A} (Attendance_Batch__c, batch {BATCH_A}): Salesforce did not take the write (HTTP 400", stop)
        self.assertIn("STOPPED, nothing more written", stop)
        self.assertNotIn("refused", stop)                # the answer's text is never repeated, only its status
        self.assertEqual((self.outcomes(), len(self.org.updates)), (["open", "failed_400"], 1))

    def test_a_write_whose_read_back_differs_is_check_and_stops_the_run(self):
        self.org.drift_update = True
        out, stop = self.apply()
        self.assertIn("answered 204 but the value read back differs", stop)
        self.assertEqual((self.outcomes(), len(self.org.updates)), (["open", "check"], 1))

    def test_a_row_count_or_module_that_changed_since_the_plan_stops_before_the_write(self):
        self.org.rows[0]["Module__c"] = "Self Advocacy"
        out, stop = self.apply()
        self.assertIn("a row under it carries another module than the batch - STOPPED before writing", stop)
        self.assertEqual((self.org.updates, self.ledger()), ([], []))

    def test_undo_puts_back_the_written_and_check_records_only(self):
        self.assertIsNone(self.apply("--limit", "1")[1])
        self.org.refuse_update = True
        self.assertIsNotNone(self.apply()[1])            # the second batch: open, failed_400
        self.org.refuse_update = False
        ledger = os.path.join(self.tmp.name, "ledger.csv")
        out, stop = self.run_tool("--undo", ledger)      # a dry run of the undo reads the ledger only: no --vpn-off needed
        self.assertIsNone(stop, stop)
        self.assertIn(f"nothing to undo: {BATCH_B} (Attendance_Batch__c) is failed_400", out)
        self.assertIn(f"would put back {BATCH_A} (Attendance_Batch__c, batch {BATCH_A}): 'Decision Making' -> 'Toma de decisiones'", out)
        self.assertIn("would put back: 3 records   (dry run - nothing written", out)
        self.assertEqual(len(self.org.updates), 4)
        self.assertIn("check that no VPN is on", self.run_tool("--undo", ledger, "--apply")[1])
        out, stop = self.run_tool("--undo", ledger, "--vpn-off", "--apply")
        self.assertIsNone(stop, stop)
        self.assertIn("put back and read back: 3 records", out)
        self.assertEqual({b["Module__c"] for b in self.org.batches} | {r["Module__c"] for r in self.org.rows}, {"Toma de decisiones"})
        self.assertEqual(self.outcomes(), ["open", "written"] * 3 + ["open", "failed_400"] + ["undo_open", "undo_written"] * 3)
        out, stop = self.run_tool("--undo", ledger, "--vpn-off", "--apply")
        self.assertIsNone(stop, stop)
        self.assertEqual(out.count("nothing to undo:"), 4)
        self.assertIn("nothing to undo\n", out)
        self.assertEqual(len(self.org.updates), 7)
        self.assertIn("'Toma de decisiones' -> 'Decision Making'", self.dry())    # the correction is due again

    def test_an_undone_check_record_stops_the_undo_too(self):
        self.assertIsNone(self.apply("--limit", "1")[1])
        self.org.drift_update = True
        out, stop = self.run_tool("--undo", os.path.join(self.tmp.name, "ledger.csv"), "--vpn-off", "--apply")
        self.assertIn("answered 204 but the value read back differs", stop)
        self.assertEqual(self.outcomes()[-2:], ["undo_open", "undo_check"])

    def test_the_salesforce_commands_need_the_vpn_word_and_the_whole_write_flag(self):
        self.assertIn("check that no VPN is on", self.run_tool()[1])
        self.assertIn("check that no VPN is on", self.run_tool("--apply")[1])
        for short in ("--app", "--a", "--vpn"):
            self.assertEqual(self.run_tool(short, "--vpn-off")[1], "2")          # argparse: no such flag
        self.assertEqual(self.run_tool("--vpn-off", "--apply", "--limit", "0")[1], "2")
        self.assertIn("a date like 2026-09-01", self.run_tool("--vpn-off", "--since", "2026-9-1")[1])
        self.assertEqual((self.org.updates, self.org.seen), ([], []))
        with self.assertRaises(SystemExit) as stop, contextlib.redirect_stdout(io.StringIO()):
            fmv.main(["--help"])
        self.assertEqual(stop.exception.code, 0)

    def test_a_ledger_inside_the_checkout_but_outside_data_is_refused(self):
        out, stop = self.run_tool("--vpn-off", "--apply", "--dir", os.path.join(REPO, "docs"))
        self.assertIn("must be under data/", stop)
        self.assertEqual(self.org.updates, [])


if __name__ == "__main__":
    unittest.main()
