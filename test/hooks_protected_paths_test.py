#!/usr/bin/env python3
"""
.claude/hooks/protected_paths.sh (Edit|Write|MultiEdit), run as Claude Code runs it (the harness
and the hooks it reads: test/helpers/hooks.py): data/, backups/, credentials/, .env, the generated
Regions.gs, the backup records and the guardrails themselves are refused in every copy of the
repository (main checkout, worktree, sibling checkout) and for a relative path.
"""
import os
import shutil
import tempfile
import unittest

# first: importing helpers.common (through helpers.hooks) puts the repository root and tools/ on sys.path
from helpers.hooks import HookFixture, needs_bash


@needs_bash
class ProtectedPaths(HookFixture, unittest.TestCase):
    def assert_edit(self, paths, code):
        for path, got in zip(paths, self.all_of(self.edit, paths)):
            with self.subTest(path=path):
                self.assertEqual(got, code, path)

    # ---- protected_paths.sh
    def edit(self, path, project=None):
        return self.run_hook("protected_paths.sh", {"file_path": path, "content": "x"}, tool="Write",
                             project=project).code

    def test_protected_paths_are_refused_wherever_the_checkout_lives(self):
        root = self.tmp.name                         # CLAUDE_PROJECT_DIR
        homes = [root, os.path.join(root, ".claude", "worktrees", "wf99-x"),
                 os.path.dirname(root) + os.sep + "jotform-glow-sync-wf20"]
        protected = ["data/enrollment_2026-08-24.csv", "data/auto_sync/run.log", "backups/262382821971058/q.json",
                     "credentials/service-account.json", "credentials/config.json", "appsscript/Regions.gs",
                     ".claude/settings.json", ".claude/settings.local.json", ".claude/live_gate.log",
                     ".claude/hooks/live_gate.sh", ".claude/hooks/new_hook.sh", ".env", ".env.local"]
        self.assert_edit([os.path.join(home, rel) for home in homes for rel in protected], 2)
        self.assert_edit(["data/x.csv", "./data/x.csv", "../data/x.csv", "./backups/1/q.json", ".env",
                          "credentials/config.json", "./.claude/settings.json", "appsscript/Regions.gs",
                          root + "//data///x.csv", root + "/./data/x.csv", root + "/tools/../data/x.csv",
                          root + "/Data/x.csv", root + "/APPSSCRIPT/regions.gs",         # the Mac ignores case
                          root + "/data/credentials/README.md", root + "/backups/.env.example"], 2)
        why = self.run_hook("protected_paths.sh", {"file_path": root + "/data/x.csv"}, tool="Edit").err
        self.assertIn("BLOCKED by .claude/hooks/protected_paths.sh: 'data/x.csv'", why)

    def test_the_exceptions_and_ordinary_files_are_editable(self):
        root = self.tmp.name
        worktree = os.path.join(root, ".claude", "worktrees", "wf99-x")
        ordinary = ["credentials/README.md", "credentials/config.example.json", ".env.example",
                    "tools/auto_sync.py", "docs/RUNBOOK.md", "appsscript/Roster.gs", "test/hooks_test.py",
                    ".claude/skills/check/SKILL.md", ".claude/agents/verifier.md", "glow/sf_partners.csv",
                    "test/fixtures/enrollment_sample.csv", "tools/database.py", "metadata/x.json"]
        self.assert_edit([os.path.join(home, rel) for home in (root, worktree) for rel in ordinary]
                         + ["docs/plans/x.md", "./tools/auto_sync.py"], 0)
        self.assertEqual(self.run_hook("protected_paths.sh", {}).code, 0)        # no path: nothing to judge

    def test_a_checkout_that_lives_under_a_data_folder_stays_editable(self):
        # inside the project only the part below it is read (review of 2026-10-09: every edit of
        # /Volumes/data/jotform-glow-sync/... was refused); outside it, the whole path
        project = os.path.join(self.tmp.name, "Volumes", "data", "jotform-glow-sync")
        worktree = os.path.join(project, ".claude", "worktrees", "wf99-x")
        for path, code in [(os.path.join(project, "tools", "x.py"), 0), (os.path.join(project, "docs", "a.md"), 0),
                           (os.path.join(worktree, "tools", "x.py"), 0), (project + "//tools/./x.py", 0),
                           ("tools/x.py", 0),
                           (os.path.join(project, "data", "x.csv"), 2), (os.path.join(project, "credentials", "a.json"), 2),
                           (os.path.join(worktree, "data", "x.csv"), 2), (os.path.join(worktree, ".env"), 2),
                           (os.path.join(project, ".claude", "settings.json"), 2), ("data/x.csv", 2),
                           (project + "-wf20/data/x.csv", 2),
                           (project + "-wf20/tools/x.py", 2)]:         # a sibling outside: its whole path
            with self.subTest(path=path):
                self.assertEqual(self.edit(path, project=project), code, path)

    def test_a_symbolic_link_into_a_protected_folder_is_followed(self):
        # review of 2026-10-09: <a temp folder>/alias-to-data/x.csv was allowed though it points into data/
        root = self.tmp.name
        for d in ("data", "credentials", "tools", os.path.join(".claude", "hooks")):
            os.makedirs(os.path.join(root, d), exist_ok=True)
        with open(os.path.join(root, "credentials", "config.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        outside = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, outside, True)
        os.symlink(os.path.join(root, "data"), os.path.join(outside, "alias-to-data"))
        os.symlink(os.path.join(root, "data"), os.path.join(root, "tools", "shortcut"))
        os.symlink(os.path.join(root, "credentials", "config.json"), os.path.join(root, "notes.json"))
        os.symlink(os.path.join(root, ".claude", "hooks"), os.path.join(outside, "gates"))
        os.symlink(os.path.join(root, "tools"), os.path.join(outside, "alias-to-tools"))
        self.assert_edit([os.path.join(outside, "alias-to-data", "x.csv"),            # a file not yet written
                          os.path.join(outside, "alias-to-data", "new", "y.csv"),
                          os.path.join(root, "tools", "shortcut", "x.csv"), "tools/shortcut/x.csv",
                          os.path.join(root, "notes.json"), "notes.json",
                          os.path.join(outside, "gates", "live_gate.sh")], 2)
        self.assert_edit([os.path.join(outside, "alias-to-tools", "x.py"), os.path.join(root, "tools", "x.py")], 0)

    def test_the_user_level_claude_settings_and_hooks_are_protected_too(self):
        # they could switch the project's hooks off (kept on purpose, review of 2026-10-09)
        home = os.path.join(os.sep, "Users", "someone")
        self.assert_edit([os.path.join(home, ".claude", "settings.json"),
                          os.path.join(home, ".claude", "settings.local.json"),
                          os.path.join(home, ".claude", "hooks", "gate.sh")], 2)
        self.assert_edit([os.path.join(home, ".claude", "CLAUDE.md"), os.path.join(home, "notes", "todo.md")], 0)

    def test_the_backup_records_are_protected(self):
        # .claude/live_backups.log is what the live gate trusts for an automatic go (#146): an Edit
        # or Write of it is a forged record, refused in every copy of the repository
        root = self.tmp.name
        homes = [root, os.path.join(root, ".claude", "worktrees", "t-99-x"),
                 os.path.dirname(root) + os.sep + "jotform-glow-sync-wf20"]
        self.assert_edit([os.path.join(home, ".claude", "live_backups.log") for home in homes]
                         + [".claude/live_backups.log", "./.claude/live_backups.log", root + "//.claude/./live_backups.log",
                            root + "/.claude/LIVE_BACKUPS.log"], 2)
        why = self.run_hook("protected_paths.sh", {"file_path": root + "/.claude/live_backups.log"}, tool="Edit").err
        self.assertIn("BLOCKED by .claude/hooks/protected_paths.sh: '.claude/live_backups.log'", why)


if __name__ == "__main__":
    unittest.main(verbosity=1)
