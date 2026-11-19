#!/usr/bin/env python3
"""
Offline tests for ticket #242 (incident #238): the automatic runner notices when the attendance
processor's Apex is changed in the org, or when Jotform batches stop arriving.

  - glow.salesforce.apex_fingerprint / expected_apex / apex_attention: the sha256 of each watched
    component's normalised body against glow/apex_fingerprints.json (ApexWatch, Fingerprints);
  - glow.salesforce.batch_gap_attention: no Jotform Attendance_Batch__c for 48 h on a weekday (BatchGap);
  - tools/auto_sync.py's Run.sf_watch(org, now) and its call from the Salesforce step (Wiring).

The org is faked: test/helpers/fake_org.py's FakeOrg answers the Attendance_Batch__c reads (any
explicit-field SELECT with an AND-only WHERE, ORDER BY, LIMIT); WatchOrg adds ApexClass/ApexTrigger.
Everything is fictional: bodies, ids, users.
"""
import contextlib
import datetime
import hashlib
import io
import json
import os
import re
import tempfile
import types
import unittest
from unittest import mock

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import REPO
from helpers.fake_org import FakeOrg
import auto_sync
from glow import salesforce

UTC = datetime.timezone.utc
PROC, TRIG, TEST = "AttendanceBatchProcessor", "AttendanceBatchTrigger", "AttendanceBatchTriggerTest"
KINDS = {PROC: "ApexClass", TRIG: "ApexTrigger", TEST: "ApexClass"}
# a distinctive string inside each fake body: it must never reach an ATTENTION item or the log
MARK = {PROC: "ZQX-PROC-MARKER-41", TRIG: "ZQX-TRIG-MARKER-52", TEST: "ZQX-TEST-MARKER-63"}
BODIES = {
    PROC: ("public with sharing class AttendanceBatchProcessor {\n"
           f"    // {MARK[PROC]}\n"
           "    public static void process(List<Attendance_Batch__c> batches) {\n"
           "        for (Attendance_Batch__c b : batches) { b.Processing_Status__c = 'Success'; }\n"
           "    }\n}"),
    TRIG: ("trigger AttendanceBatchTrigger on Attendance_Batch__c (after insert) {\n"
           f"    // {MARK[TRIG]}\n"
           "    AttendanceBatchProcessor.process(Trigger.new);\n}"),
    TEST: ("@isTest\nprivate class AttendanceBatchTriggerTest {\n"
           f"    // {MARK[TEST]}\n"
           "    @isTest static void processes() { System.assert(true); }\n}"),
}
# who last changed each component, and when: distinct per component, so an item that names the
# wrong component's date or user is caught
CHANGED = {PROC: ("2026-10-26T14:03:11.000+0000", "005000000000001AAA"),
           TRIG: ("2026-09-15T08:20:00.000+0000", "005000000000002BBB"),
           TEST: ("2026-08-03T22:45:59.000+0000", "005000000000003CCC")}


def sha(text):
    """The fingerprint from first principles: CRLF -> LF, trimmed, UTF-8, sha256 hex."""
    return hashlib.sha256(text.replace("\r\n", "\n").strip().encode("utf-8")).hexdigest()


def expected_for(bodies=BODIES):
    return {name: {"kind": KINDS[name], "sha256": sha(body)} for name, body in bodies.items()}


def apex_record(name, body, kind=None):
    when, who = CHANGED[name]
    kind = kind or KINDS[name]
    return {"attributes": {"type": kind}, "Id": ("01p" if kind == "ApexClass" else "01q") + "000000000" + name[:6],
            "Name": name, "Body": body, "LastModifiedDate": when, "LastModifiedById": who, "Status": "Active"}


def item_text(item):
    title, detail = item
    return f"{title}\n{detail}"


def names_in(text):
    """The watched components a text names, whole words only (AttendanceBatchTrigger is a prefix
    of AttendanceBatchTriggerTest)."""
    return {n for n in (PROC, TRIG, TEST) if re.search(r"\b" + n + r"\b", text)}


def title_names(item):
    """The watched components an item's TITLE names: each Apex item's title names its component
    (and only it), so ATTENTION.md's heading says which one."""
    return names_in(item[0])


def sf_date(when):
    """An aware instant as Salesforce writes a CreatedDate."""
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000+0000")


class WatchOrg(FakeOrg):
    """The shared fake org plus the two Apex sobjects. Apex reads answer the records of their kind
    whose Name is in the query's `Name IN (...)` (all of the kind when there is no IN); a read that
    is not a SELECT, or of another Apex sobject, is a test failure. `apex_error` makes every Apex read
    raise; `batch_error` every Attendance_Batch__c read."""

    def __init__(self, apex=None, batches=()):
        super().__init__([])
        self.apex = list(apex if apex is not None else [apex_record(n, b) for n, b in BODIES.items()])
        self.apex_soql, self.apex_error, self.batch_error = [], None, None
        for n, (creator, created) in enumerate(batches):
            self.batches.append({"Id": f"a0B000000000{n:03d}AAA", "Name": f"AB-{n:05d}", "Creator__c": creator,
                                 "CreatedDate": created, "Processing_Status__c": "Success",
                                 "Account__c": "001000000000000SUN", "Attendance_Date__c": created[:10]})

    def _apex(self, soql):
        self.apex_soql.append(soql)
        if self.apex_error:
            raise self.apex_error
        assert soql.lstrip().upper().startswith("SELECT "), soql
        m = re.search(r"\bFROM\s+(ApexClass|ApexTrigger)\b", soql)
        assert m, f"an Apex read of something else: {soql}"
        kind = m.group(1)
        found = [r for r in self.apex if r["attributes"]["type"] == kind]
        names = re.search(r"\bName\s+IN\s*\(([^)]*)\)", soql, re.I)
        if names:
            wanted = {v.strip().strip("'") for v in names.group(1).split(",")}
            found = [r for r in found if r["Name"] in wanted]
        return [dict(r) for r in found]

    def query(self, soql):
        if re.search(r"\bFROM\s+Apex", soql):
            return self._apex(soql)
        if self.batch_error and "Attendance_Batch__c" in soql:
            self.seen.append(soql)
            raise self.batch_error
        return super().query(soql)

    def query_all(self, soql):
        return self.query(soql)

    def count(self, soql):
        if self.batch_error and "Attendance_Batch__c" in soql:
            raise self.batch_error
        return super().count(soql)


# ------------------------------------------------------------------------------------- fingerprints
class Fingerprints(unittest.TestCase):
    def test_the_fingerprint_is_the_sha256_of_the_normalised_body(self):
        for body in ("", "x", "public class A {}", BODIES[PROC], BODIES[TRIG], "  trigger T on X (after insert) {}\n",
                     "class Ünïcode { String s = 'café ☕'; }", "a\r\nb\r\n\r\nc", "line1\n\n\nline2\t"):
            with self.subTest(body=body[:30]):
                got = salesforce.apex_fingerprint(body)
                self.assertEqual(got, sha(body))
                self.assertRegex(got, r"^[0-9a-f]{64}$")

    def test_crlf_and_surrounding_whitespace_do_not_change_it_and_any_other_change_does(self):
        base = BODIES[PROC]
        same = (base.replace("\n", "\r\n"), "\n\n  " + base + "  \n\t", "\r\n" + base.replace("\n", "\r\n") + "\r\n")
        for body in same:
            with self.subTest(same=repr(body[:20])):
                self.assertEqual(salesforce.apex_fingerprint(body), salesforce.apex_fingerprint(base))
        other = (base.replace("Success", "Failed"), base.replace("    // ", "   // "), base.replace("public", "Public"),
                 base + "\n// one more line", base.replace("\n", "\n\n", 1), base[:-1])
        for body in other:
            with self.subTest(other=repr(body[-25:])):
                self.assertNotEqual(salesforce.apex_fingerprint(body), salesforce.apex_fingerprint(base))

    def test_the_expected_fingerprints_file_names_the_three_components(self):
        path = os.path.join(REPO, "glow", "apex_fingerprints.json")
        self.assertTrue(os.path.isfile(path), "glow/apex_fingerprints.json is missing")
        with open(path, encoding="utf-8") as f:
            json.load(f)                                          # plain JSON
        expected = salesforce.expected_apex()
        self.assertEqual(set(expected), {PROC, TRIG, TEST})
        for name, kind in KINDS.items():
            with self.subTest(name):
                self.assertEqual(expected[name]["kind"], kind)
                self.assertRegex(expected[name]["sha256"], r"^[0-9a-f]{64}$")


# ------------------------------------------------------------------------------------------- apex
class ApexWatch(unittest.TestCase):
    def watch(self, org, expected=None, **kw):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            items = salesforce.apex_attention(org, expected=expected_for() if expected is None else expected, **kw)
        self.assertNotIn("ZQX-", out.getvalue())                  # never prints a body
        for item in items:
            self.assertEqual(len(item), 2)
            for marker in MARK.values():
                self.assertNotIn(marker, item_text(item))
            self.assertNotIn("System.assert", item_text(item))     # nor any other line of one
        return items

    def test_matching_bodies_give_no_item(self):
        self.assertEqual(self.watch(WatchOrg()), [])
        # Salesforce may hand the body back with CRLF and padding: still a match
        org = WatchOrg([apex_record(n, "\r\n " + b.replace("\n", "\r\n") + "\r\n\t") for n, b in BODIES.items()])
        self.assertEqual(self.watch(org), [])

    def test_each_changed_component_gives_one_item_naming_it_its_date_and_modifier(self):
        for changed in (PROC, TRIG, TEST):
            with self.subTest(changed=changed):
                bodies = dict(BODIES)
                bodies[changed] = bodies[changed].replace("{\n", "{\n    Integer extra = 1;\n", 1)
                org = WatchOrg([apex_record(n, b) for n, b in bodies.items()])
                items = self.watch(org)
                self.assertEqual(len(items), 1, items)
                text = item_text(items[0])
                self.assertEqual(title_names(items[0]), {changed})
                when, who = CHANGED[changed]
                self.assertIn(when[:10], text)                    # the LastModifiedDate's day
                self.assertIn(who, text)                          # the modifier's user id, never a name
                for other in (n for n in CHANGED if n != changed):
                    self.assertNotIn(CHANGED[other][1], text)

    def test_every_changed_component_gets_its_own_item(self):
        org = WatchOrg([apex_record(n, b + "\n// changed by another release") for n, b in BODIES.items()])
        items = self.watch(org)
        self.assertEqual(len(items), 3, items)
        self.assertEqual(sorted(tuple(title_names(i)) for i in items), [(PROC,), (TRIG,), (TEST,)])
        for item in items:
            (name,) = title_names(item)
            self.assertIn(CHANGED[name][1], item_text(item))
            self.assertIn(CHANGED[name][0][:10], item_text(item))

    def test_a_component_missing_from_the_org_gives_an_item_naming_it(self):
        for missing in (PROC, TRIG, TEST):
            with self.subTest(missing=missing):
                org = WatchOrg([apex_record(n, b) for n, b in BODIES.items() if n != missing])
                items = self.watch(org)
                self.assertEqual(len(items), 1, items)
                self.assertEqual(title_names(items[0]), {missing})
        items = self.watch(WatchOrg([]))                          # nothing at all
        self.assertEqual(len(items), 3, items)
        self.assertEqual(sorted(tuple(title_names(i)) for i in items), [(PROC,), (TRIG,), (TEST,)])

    def test_the_trigger_is_read_as_an_apex_trigger(self):
        # the trigger stored as a CLASS of the same name is not the trigger: it is missing
        records = [apex_record(PROC, BODIES[PROC]), apex_record(TEST, BODIES[TEST]),
                   apex_record(TRIG, BODIES[TRIG], kind="ApexClass")]
        items = self.watch(WatchOrg(records))
        self.assertEqual(len(items), 1, items)
        self.assertEqual(title_names(items[0]), {TRIG})

    def test_the_expected_side_is_what_is_passed_or_else_the_file(self):
        # a different expectation for the processor: the same org now mismatches there only
        other = expected_for()
        other[PROC] = {"kind": "ApexClass", "sha256": "0" * 64}
        items = self.watch(WatchOrg(), expected=other)
        self.assertEqual([title_names(i) for i in items], [{PROC}])
        # no expectation given: glow/apex_fingerprints.json, which records the deployed Apex - the
        # fictional bodies here match none of it
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            items = salesforce.apex_attention(WatchOrg())
        self.assertEqual(sorted(tuple(title_names(i)) for i in items), [(PROC,), (TRIG,), (TEST,)])
        self.assertNotIn("ZQX-", out.getvalue() + "".join(item_text(i) for i in items))

    def test_the_reads_are_selects_naming_the_components_and_their_fields(self):
        org = WatchOrg()
        self.watch(org)
        self.assertTrue(org.apex_soql)
        for soql in org.apex_soql:
            self.assertRegex(soql.strip(), r"(?i)^SELECT\s")
            for field in ("Name", "Body", "LastModifiedDate", "LastModifiedById"):
                self.assertRegex(soql, r"\b" + field + r"\b")
        classes = [s for s in org.apex_soql if re.search(r"\bFROM\s+ApexClass\b", s)]
        triggers = [s for s in org.apex_soql if re.search(r"\bFROM\s+ApexTrigger\b", s)]
        self.assertTrue(classes and triggers, org.apex_soql)
        self.assertTrue(all(PROC in s and TEST in s for s in classes))
        self.assertTrue(all(TRIG in s for s in triggers))
        self.assertEqual(org.inserts, [])
        self.assertEqual(org.updates, [])


# -------------------------------------------------------------------------------------- batch gap
# the week of 2026-11-16 (Monday) to 2026-11-22 (Sunday), at 10:00 UTC
WEEK = [datetime.datetime(2026, 11, 16, 10, 0, tzinfo=UTC) + datetime.timedelta(days=d) for d in range(7)]
MON, TUE, WED, THU, FRI, SAT, SUN = WEEK
H = datetime.timedelta(hours=1)


class BatchGap(unittest.TestCase):
    def gap(self, now, batches, **kw):
        org = WatchOrg(batches=[(creator, sf_date(when)) for creator, when in batches])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            items = salesforce.batch_gap_attention(org, now, **kw)
        for item in items:
            self.assertEqual(len(item), 2)
        self.assertEqual((org.inserts, org.updates), ([], []))
        return items, org

    def test_a_weekday_gap_over_48_hours_gives_one_item_and_a_weekend_none(self):
        for now in WEEK:
            for age in (49, 72, 24 * 6):
                with self.subTest(now=now.strftime("%a"), age=age):
                    items, _ = self.gap(now, [("Jotform", now - age * H)])
                    self.assertEqual(len(items), 0 if now.weekday() >= 5 else 1, items)

    def test_recent_batches_give_no_item(self):
        for now in (MON, WED, FRI):
            for age in (0.5, 1, 24, 47, 47.9):
                with self.subTest(now=now.strftime("%a"), age=age):
                    items, _ = self.gap(now, [("Jotform", now - age * H), ("Jotform", now - 300 * H)])
                    self.assertEqual(items, [])

    def test_the_item_says_since_when(self):
        for now, age in ((TUE, 50), (THU, 75), (FRI, 24 * 9)):
            with self.subTest(now=now.strftime("%a"), age=age):
                newest = now - age * H
                items, _ = self.gap(now, [("Jotform", newest - 30 * H), ("Jotform", newest)])
                self.assertEqual(len(items), 1)
                self.assertIn(newest.strftime("%Y-%m-%d"), item_text(items[0]))

    def test_the_newest_jotform_batch_is_the_one_judged(self):
        # inserted out of order: the newest is in the middle
        items, _ = self.gap(WED, [("Jotform", WED - 100 * H), ("Jotform", WED - 10 * H), ("Jotform", WED - 200 * H)])
        self.assertEqual(items, [])
        items, _ = self.gap(WED, [("Jotform", WED - 100 * H), ("Jotform", WED - 60 * H), ("Jotform", WED - 200 * H)])
        self.assertEqual(len(items), 1)
        self.assertIn((WED - 60 * H).strftime("%Y-%m-%d"), item_text(items[0]))

    def test_batches_not_made_by_jotform_do_not_count(self):
        # a partner's report or a batch made by hand (no creator) is not the Jotform flow arriving
        for creator in ("Partner report", None, "Manual entry"):
            with self.subTest(creator=creator):
                items, _ = self.gap(THU, [("Jotform", THU - 120 * H), (creator, THU - 1 * H)])
                self.assertEqual(len(items), 1, items)
                self.assertIn((THU - 120 * H).strftime("%Y-%m-%d"), item_text(items[0]))

    def test_no_jotform_batch_at_all_gives_an_item_on_a_weekday(self):
        for batches in ([], [("Partner report", TUE - 2 * H)]):
            with self.subTest(batches=len(batches)):
                items, _ = self.gap(TUE, batches)
                self.assertEqual(len(items), 1, items)

    def test_the_boundary_exactly_48_hours_is_not_yet_a_gap(self):
        # Ruling: the alert is for a newest batch OLDER than the window; exactly at it, none
        items, _ = self.gap(THU, [("Jotform", THU - 48 * H)])
        self.assertEqual(items, [])
        items, _ = self.gap(THU, [("Jotform", THU - 48 * H - datetime.timedelta(minutes=1))])
        self.assertEqual(len(items), 1)

    def test_the_window_is_the_hours_given(self):
        for hours, age, alert in ((24, 30, True), (24, 20, False), (72, 50, False), (72, 80, True), (48, 49, True)):
            with self.subTest(hours=hours, age=age):
                items, _ = self.gap(WED, [("Jotform", WED - age * H)], hours=hours)
                self.assertEqual(len(items), 1 if alert else 0, items)

    def test_the_weekday_is_the_utc_one(self):
        # Saturday 00:30 UTC is still Friday evening west of UTC: judged as Saturday (none);
        # Friday 23:30 UTC is Saturday morning east of UTC: judged as Friday (an item)
        sat_early = datetime.datetime(2026, 11, 21, 0, 30, tzinfo=UTC)
        fri_late = datetime.datetime(2026, 11, 20, 23, 30, tzinfo=UTC)
        self.assertEqual(self.gap(sat_early.astimezone(datetime.timezone(-datetime.timedelta(hours=5))),
                                  [("Jotform", sat_early - 90 * H)])[0], [])
        self.assertEqual(len(self.gap(fri_late.astimezone(datetime.timezone(datetime.timedelta(hours=3))),
                                      [("Jotform", fri_late - 90 * H)])[0]), 1)


# ----------------------------------------------------------------------------------------- wiring
class Wiring(unittest.TestCase):
    """The seam: Run.sf_watch(org, now) runs both checks and adds their items to run.attention; a
    check that raises is an ATTENTION item of its own and never an exception. The Salesforce step
    (sf_start ... sf_finish, with SF_SYNC plan or apply and the secrets set) calls it once, with the
    org it logged in with and the run's start instant (Run.started)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # the expectation the run reads is the file's; here it is the fictional bodies'
        patcher = mock.patch.object(salesforce, "expected_apex", lambda *a, **k: expected_for())
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_obj(self, **extra):
        args = types.SimpleNamespace(apply=False, out=self.tmp.name, max_creates=5, max_updates=20, trigger="test",
                                     run_url="", apply_salesforce=False, synclog=False, **extra)
        return auto_sync.Run(args)

    def watch(self, run, org, now):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            run.sf_watch(org, now)
        everything = out.getvalue() + "\n".join(run.lines) + "".join(item_text(i) for i in run.attention)
        self.assertNotIn("ZQX-", everything)                       # never a body, anywhere
        return run.attention

    def test_all_well_adds_nothing(self):
        for now in (MON, WED, SAT):
            with self.subTest(now=now.strftime("%a")):
                run = self.run_obj()
                self.assertEqual(self.watch(run, WatchOrg(batches=[("Jotform", sf_date(now - 3 * H))]), now), [])

    def test_a_changed_processor_and_a_gap_each_add_an_item(self):
        bodies = dict(BODIES, **{PROC: BODIES[PROC].replace("'Success'", "'Done'")})
        org = WatchOrg([apex_record(n, b) for n, b in bodies.items()],
                       batches=[("Jotform", sf_date(THU - 100 * H))])
        run = self.run_obj()
        run.attention.append(("an earlier item", "kept"))
        items = self.watch(run, org, THU)
        self.assertEqual(items[0], ("an earlier item", "kept"))
        new = items[1:]
        self.assertEqual(len(new), 2, new)
        apex = [i for i in new if title_names(i)]
        self.assertEqual(len(apex), 1)
        self.assertEqual(title_names(apex[0]), {PROC})
        self.assertIn(CHANGED[PROC][1], item_text(apex[0]))
        gap = [i for i in new if not title_names(i)]
        self.assertEqual(len(gap), 1)
        self.assertIn((THU - 100 * H).strftime("%Y-%m-%d"), item_text(gap[0]))
        # the same org on a Saturday: the Apex item only
        run = self.run_obj()
        self.assertEqual(len(self.watch(run, org, SAT)), 1)

    def test_a_check_that_raises_is_an_item_and_the_other_check_still_runs(self):
        # the Apex read fails; the gap check still finds its gap
        org = WatchOrg(batches=[("Jotform", sf_date(TUE - 80 * H))])
        org.apex_error = salesforce.Refused("Salesforce did not answer a read (HTTP 503)")
        run = self.run_obj()
        items = self.watch(run, org, TUE)
        self.assertEqual(len(items), 2, items)
        self.assertTrue(any((TUE - 80 * H).strftime("%Y-%m-%d") in item_text(i) for i in items))
        # the batch read fails; the Apex matches: one item, for the failure
        org = WatchOrg(batches=[("Jotform", sf_date(TUE - 1 * H))])
        org.batch_error = RuntimeError("boom")
        run = self.run_obj()
        self.assertEqual(len(self.watch(run, org, TUE)), 1)
        # both fail: two items, and still no exception
        org.apex_error = TypeError("odd answer")
        run = self.run_obj()
        self.assertEqual(len(self.watch(run, org, TUE)), 2)

    def salesforce_step(self, org, now, env=None):
        """sf_start, then sf_finish, as main() runs them, with GLOW Sync's login faked to `org` and the
        new-clubs step reduced to a stub (it is tested in sf_new_clubs_test)."""
        class Step:
            def __init__(self, mode, org_, roster_csv, **kw):
                self.mode, self.org, self.created, self.attention, self.broken, self.today = \
                    mode, org_, [], [], None, "2026-11-19"

            def prepare(self):
                pass

            def check(self, *a, **kw):
                return 0, 0

            def warn(self, title, detail=""):
                self.attention.append((title, detail))

            def close(self):
                pass
        run = self.run_obj()
        run.started = now
        env = env or {"SF_SYNC": "plan", "SF_CLIENT_ID": "demo-client-id", "SF_CLIENT_SECRET": "demo-secret"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(auto_sync, "Org", lambda *a, **k: org), \
                mock.patch.object(auto_sync, "client_credentials", lambda cid, secret, *a, **k: "demo-login"), \
                mock.patch.object(auto_sync.sfn, "Step", Step), \
                contextlib.redirect_stdout(io.StringIO()):
            run.sf_start(os.path.join(self.tmp.name, "roster.csv"))
            run.sf_finish(None)
        return run

    def test_the_salesforce_step_runs_the_watch_with_its_login_and_the_runs_clock(self):
        bodies = dict(BODIES, **{TRIG: BODIES[TRIG].replace("after insert", "after insert, after update")})
        org = WatchOrg([apex_record(n, b) for n, b in bodies.items()], batches=[("Jotform", sf_date(FRI - 60 * H))])
        run = self.salesforce_step(org, FRI)
        self.assertEqual(len(run.attention), 2, run.attention)
        self.assertEqual([title_names(i) for i in run.attention if title_names(i)], [{TRIG}])
        self.assertTrue(any((FRI - 60 * H).strftime("%Y-%m-%d") in item_text(i) for i in run.attention))
        # all well: nothing
        org = WatchOrg(batches=[("Jotform", sf_date(FRI - 2 * H))])
        self.assertEqual(self.salesforce_step(org, FRI).attention, [])
        # the gap judged on the run's clock: the same batches on a Sunday raise nothing
        org = WatchOrg(batches=[("Jotform", sf_date(SUN - 60 * H))])
        self.assertEqual(self.salesforce_step(org, SUN).attention, [])

    def test_the_step_calls_sf_watch_once_with_the_org_and_run_started(self):
        # other tests replace Run.sf_watch to keep the step offline: the step must go through it
        calls = []

        def recorder(run, org, now=None):
            calls.append((org, now))
        org = WatchOrg()
        with mock.patch.object(auto_sync.Run, "sf_watch", recorder):
            self.salesforce_step(org, WED)
        self.assertEqual(calls, [(org, WED)])


if __name__ == "__main__":
    unittest.main()
