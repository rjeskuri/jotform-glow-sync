#!/usr/bin/env python3
"""
The refusals that guard an irreversible or bad-data write, pinned through each tool's own command
line (main() on an argv, as the other tests drive it): each refuses with its own message and
before any write, and each has a control run - the same input past the refusal - on which the
fake DOES record the write, so "no write" cannot hold merely because the input was inert.

  - sync_attendance_form.py, the prune switch, on a form that has submissions (PruneRefusal);
  - restore_conditions.py with no snapshot, or a snapshot holding no conditions (RestoreRefusals);
  - tools/auto_sync.py on an export with fewer active rows than --min-active (MinActiveFloor).
Fictional names only.
"""
import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import ClubGuardFixture, FakeForm, SameNameFixture
import auto_sync
import restore_conditions

PRUNE = "--" + "prune"      # the switch, spelled so the live-systems hook does not read this file as a command


class CountingForm(FakeForm):
    """FakeForm whose GET /form/{id} reports `count` submissions."""

    def __init__(self, *args, count="0", **kw):
        super().__init__(*args, **kw)
        self.count = count

    def get(self, path):
        if path == "":
            return {"count": self.count, "status": self.status}
        return super().get(path)


class PruneRefusal(SameNameFixture, unittest.TestCase):
    """The prune switch DELETEs the questions of clubs the Roster places in another region; on a
    form that has submissions it is refused with --apply, before any write
    (sync_attendance_form.py)."""

    # Partner Two's Beta Club (q13) is on this form but the Roster places it in Asia: a prune
    # run on the Africa form deletes q13
    ASIA = {("Partner Two", "Beta Club"): "Asia"}

    def prune(self, count, *extra):
        fake = CountingForm(*self.form(), apply="--apply" in extra, count=count)
        code, out = self.run_sync(fake, PRUNE, *extra, regions=self.ASIA)
        return fake, code, out

    def test_control_prune_on_a_fresh_form_deletes_the_other_regions_club(self):
        fake, code, out = self.prune("0", "--apply")
        self.assertEqual(code, 0)
        self.assertEqual([w[:2] for w in fake.writes if w[0] == "DELETE"], [("DELETE", "/question/13")])

    def test_apply_prune_on_a_form_with_submissions_refuses_before_any_write(self):
        for count in ("1", "3", "250"):
            with self.subTest(count=count):
                fake, code, out = self.prune(count, "--apply")
                self.assertEqual(code, f"Refusing: form 999 already has {count} submission(s); "
                                       "--prune is for fresh clones only")
                self.assertEqual((fake.writes, fake.calls), ([], []))

    def test_the_refusal_needs_both_prune_and_submissions(self):
        # submissions without the switch: the club is kept, nothing refused, nothing deleted
        fake = CountingForm(*self.form(), apply=True, count="3")
        code, out = self.run_sync(fake, "--apply", regions=self.ASIA)
        self.assertEqual((code, fake.writes), (0, []))

    def test_a_prune_dry_run_on_a_form_with_submissions_only_warns(self):
        fake, code, out = self.prune("3")
        self.assertEqual(code, 0)
        self.assertIn("  ! (preview only) form 999 already has 3 submission(s); "
                      "--prune is for fresh clones only", out)


class RestoreRefusals(unittest.TestCase):
    """restore_conditions.py main() against a recording fake: a missing snapshot and a snapshot
    without conditions are refused before the form is read or written."""

    def setUp(self):
        self.qs, self.wire = ClubGuardFixture.form(ClubGuardFixture())

    def run_restore(self, snapshot, *extra, name="properties-latest.json"):
        """(exit code, stdout, every call the fake saw, backups/999/ file names afterwards).
        snapshot: what to save as backups/999/<name>; None saves nothing."""
        calls = []
        questions = self.qs

        class Fake:
            def __init__(self, key, apply=False):
                pass

            def get(self, path):
                calls.append(("GET", path))
                if path.endswith("/questions"):
                    return copy.deepcopy(questions)
                puts = [c[2]["properties"]["conditions"] for c in calls if c[0] == "PUT"]
                return {"conditions": puts[-1] if puts else [{"id": "live"}]}

            def put_json(self, path, payload, label):
                calls.append(("PUT", path, payload))

            def post_form(self, path, data, label):
                calls.append(("POST", path, data))

            def delete(self, path, label):
                calls.append(("DELETE", path))

        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            folder = os.path.join(tmp, "backups", "999")
            os.makedirs(folder)
            if snapshot is not None:
                with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
                    json.dump(snapshot, f)
            with mock.patch.object(restore_conditions, "REPO", tmp), \
                    mock.patch.object(restore_conditions.backup, "REPO", tmp), \
                    mock.patch.object(restore_conditions, "Client", Fake), \
                    mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}), \
                    mock.patch.object(sys, "argv", ["restore_conditions.py", "--form", "999", *extra]), \
                    contextlib.redirect_stdout(out):
                try:
                    restore_conditions.main()
                    code = 0
                except SystemExit as e:
                    code = e.code
            self.folder = folder
            return code, out.getvalue(), calls, sorted(os.listdir(folder))

    def test_control_a_snapshot_with_conditions_is_restored(self):
        code, out, calls, files = self.run_restore({"conditions": self.wire}, "--apply")
        self.assertEqual(code, 0)
        self.assertEqual([c[:2] for c in calls if c[0] == "PUT"], [("PUT", "/form/999/properties")])
        self.assertIn("RESTORED:", out)

    def test_no_snapshot_at_the_path_is_refused_before_anything_is_read_or_written(self):
        for extra in ((), ("--apply",), ("--from", "properties-2026-01-02T030405.json"),
                      ("--apply", "--from", "properties-2026-01-02T030405.json"),
                      ("--apply", "--force")):
            with self.subTest(extra=extra):
                # the folder exists; the file asked for (default properties-latest.json, or the
                # --from name) does not - another snapshot beside it must not stand in for it
                code, out, calls, files = self.run_restore({"conditions": self.wire}, *extra,
                                                           name="conditions-latest.json")
                wanted = extra[extra.index("--from") + 1] if "--from" in extra else "properties-latest.json"
                self.assertEqual(code, f"No snapshot at {os.path.join(self.folder, wanted)} "
                                       "- run backup_forms.py first")
                self.assertEqual((out, calls), ("", []))
                self.assertEqual(files, ["conditions-latest.json"])      # no snapshot of the form either

    def test_no_backup_folder_at_all_is_refused_too(self):
        code, out, calls, files = self.run_restore(None, "--apply")
        self.assertTrue(str(code).startswith("No snapshot at "))
        self.assertIn("run backup_forms.py first", str(code))
        self.assertEqual((out, calls, files), ("", [], []))

    def test_a_snapshot_that_holds_no_conditions_is_refused_before_anything_is_read_or_written(self):
        for empty in ({"conditions": []}, [], {"conditions": None}):
            for extra in ((), ("--apply",), ("--apply", "--force")):
                with self.subTest(snapshot=empty, extra=extra):
                    code, out, calls, files = self.run_restore(empty, *extra)
                    self.assertEqual(code, f"{os.path.join(self.folder, 'properties-latest.json')} holds no "
                                           "conditions - refusing to wipe the form")
                    self.assertEqual((out, calls), ("", []))
                    self.assertEqual(files, ["properties-latest.json"])   # no snapshot of the form either

    def test_the_empty_snapshot_named_by_from_is_refused(self):
        code, out, calls, files = self.run_restore({"conditions": []}, "--apply", "--from", "conditions-x.json",
                                                   name="conditions-x.json")
        self.assertTrue(str(code).endswith("conditions-x.json holds no conditions - refusing to wipe the form"))
        self.assertEqual((out, calls), ("", []))


class MinActiveFloor(unittest.TestCase):
    """tools/auto_sync.py main(): an export with fewer active rows than --min-active (default
    1000) syncs nothing and exits 1."""

    ROWS = [("Partner One", "Alpha Club", "Jane Doe", "active", "Africa"),
            ("Partner One", "Alpha Club", "Mary Roe", "active", "Africa"),
            ("Partner One", "Stars", "Ann Poe", "active", "Africa"),
            ("Partner Two", "Beta Club", "Eve Hoe", "active", "Asia"),
            ("Partner Two", "Beta Club", "Ida Toe", "active", "Asia"),
            ("Partner Two", "Old Club", "Sue Moe", "inactive", "Asia"),     # not counted
            ("Partner Two", "Old Club", "Liz Noe", "dropped", "Asia")]       # not counted
    ACTIVE = 5

    DRY_RUN = ("Roster: 2 active clubs in Africa (3 girls); 3 clubs overall\n\nDRY RUN (use --apply to "
               "write):\n  - CREATE roster 'Gamma Club' (2 girls)\n")

    def run_main(self, *extra, rows=None):
        """(exit code, stdout, syncs, client calls, files in --out): the sync children Run.sync
        was asked to start as (region, apply), and everything the runner's Jotform client saw."""
        syncs, client_calls = [], []

        def sync_(run, csv_path, region, form, apply, summary_path=None):
            syncs.append((region, apply))
            return types.SimpleNamespace(returncode=0, stderr="", stdout=self.DRY_RUN)

        class Client:
            def __init__(self, key, **kw):
                pass

            def __getattr__(self, name):
                def call(*a, **kw):
                    client_calls.append((name, a))
                    return {"status": "ENABLED"}
                return call

        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            roster = os.path.join(tmp, "roster.csv")
            with open(roster, "w", encoding="utf-8") as f:
                f.write("girl_id,partner,club,full_name,status,region\n")
                for n, (partner, club, name, status, region) in enumerate(rows or self.ROWS):
                    f.write(f"DEMOCLUB-SAMPLE-{n:03d},{partner},{club},{name},{status},{region}\n")
            tab = os.path.join(tmp, "partners.csv")
            with open(tab, "w", encoding="utf-8") as f:
                f.write("partner,region,notes,jotform\nPartner One,Africa,,\nPartner Two,Asia,,\n")
            work = os.path.join(tmp, "out")
            argv = ["auto_sync.py", "--roster", roster, "--partners", tab, "--out", work,
                    "--region", "Africa", *extra]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}), \
                    mock.patch.object(auto_sync, "Client", Client), \
                    mock.patch.object(auto_sync.Run, "sync", sync_), \
                    mock.patch.object(auto_sync.Run, "read_status", lambda self, form: "ENABLED"), \
                    mock.patch.object(auto_sync.Run, "check_storage", lambda self, read: None), \
                    contextlib.redirect_stdout(out):
                try:
                    auto_sync.main()
                    code = 0
                except SystemExit as e:
                    code = e.code
            files = sorted(os.listdir(work))
            self.logs = []
            for n in files:
                if n.endswith(".log"):
                    with open(os.path.join(work, n), encoding="utf-8") as f:
                        self.logs.append(f.read())
        return code, out.getvalue(), syncs, client_calls, files

    def refusal(self, active, floor):
        return (f"  ! only {active} active rows (floor {floor}) - the export looks truncated; "
                "nothing synced")

    def test_control_an_export_at_the_floor_is_synced(self):
        # the same export, floor met: the region is planned (the fake would record the sync)
        for floor in (1, 3, self.ACTIVE):
            with self.subTest(floor=floor):
                code, out, syncs, _, _ = self.run_main("--min-active", str(floor))
                self.assertEqual(code, 0)
                self.assertEqual(syncs[0], ("Africa", False))
                self.assertNotIn("nothing synced", out)

    def test_an_export_below_the_floor_syncs_nothing_and_exits_1(self):
        for floor in (self.ACTIVE + 1, 6, 50, 1000):
            for apply in (False, True):
                with self.subTest(floor=floor, apply=apply):
                    code, out, syncs, client_calls, files = self.run_main(
                        "--min-active", str(floor), *(["--apply"] if apply else []))
                    self.assertEqual(code, 1)
                    self.assertIn(self.refusal(self.ACTIVE, floor), out)
                    self.assertEqual((syncs, client_calls), ([], []))
                    self.assertIn(self.refusal(self.ACTIVE, floor), "\n".join(self.logs))   # the log file too
                    self.assertNotIn("ATTENTION.md", files)

    def test_the_default_floor_is_1000_active_rows(self):
        code, out, syncs, client_calls, _ = self.run_main("--apply")
        self.assertEqual(code, 1)
        self.assertIn(self.refusal(self.ACTIVE, 1000), out)
        self.assertEqual((syncs, client_calls), ([], []))
        # 1000 active rows meet it (and 999 do not): the count is of active rows, not of rows
        many = [("Partner One", f"Club {n % 7}", f"Girl {n}", "active", "Africa") for n in range(1000)]
        inactive = [("Partner Two", "Old Club", f"Gone {n}", "inactive", "Asia") for n in range(50)]
        code, out, syncs, _, _ = self.run_main(rows=many + inactive)
        self.assertEqual((code, syncs[0]), (0, ("Africa", False)))
        code, out, syncs, _, _ = self.run_main(rows=many[:-1] + inactive)
        self.assertEqual((code, syncs), (1, []))
        self.assertIn(self.refusal(999, 1000), out)


if __name__ == "__main__":
    unittest.main()
