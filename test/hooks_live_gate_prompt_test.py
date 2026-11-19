#!/usr/bin/env python3
"""
.claude/hooks/live_gate.sh (Bash), run as Claude Code runs it (the harness, the hooks and
settings it reads, and the osascript stub: test/helpers/hooks.py): the prompt for a live command.

Without its backup from today a live write asks Ryan in the session, and is refused - with the
reason and the backup command - where no prompt can show. A command that approves itself
(GLOW_LIVE_OK, a startup file) is refused outright. A read-only command that only mentions a live
flag passes, a chained one does not.

How a command is matched ("prompt, don't parse"): test/hooks_live_gate_matching_test.py; the modes,
the subagents and the input: test/hooks_live_gate_callers_test.py; the backed writes (#146):
test/hooks_live_gate_backed_test.py.
"""
import unittest

# first: importing helpers.common (through helpers.hooks) puts the repository root and tools/ on sys.path
from helpers.hooks import ASK_MODES, NO_PROMPT_MODES, HookFixture, needs_bash


@needs_bash
class LiveGatePrompt(HookFixture, unittest.TestCase):
    def test_every_live_command_asks_ryan_and_is_logged(self):
        for mode in ASK_MODES:
            self.assert_asks(self.LIVE, mode=mode)
        self.assertEqual(self.logged(), {"ASKED": len(self.LIVE) * len(ASK_MODES)})

    def test_glow_live_ok_no_longer_skips_the_prompt(self):
        # 2026-10-14: a session-wide pre-approval was open for 10 days (BACKLOG 83), and a
        # dispatched run inherits the environment; the prompt is the only approval
        self.assert_asks(self.LIVE, live_ok="1")
        self.assertEqual(self.logged(), {"ASKED": len(self.LIVE)})
        self.assert_asks(["python3 sync_attendance_form.py x --apply"], live_ok="yes")
        self.assert_denies(self.SAMPLE, live_ok="1", mode="bypassPermissions")
        self.assert_denies(self.SAMPLE, live_ok="1", agent=True)

    def test_a_command_that_approves_itself_is_blocked_outright(self):
        commands = self.SELF_APPROVING + self.STARTUP_WRITES
        runs = 0
        for live_ok in (None, "1"):
            for mode in ASK_MODES + NO_PROMPT_MODES:
                for command, run in self.runs(commands, live_ok=live_ok, mode=mode):
                    with self.subTest(command=command, live_ok=live_ok, mode=mode):
                        self.assertEqual(self.verdict(run), "deny", self.show(run))
                        # the old way out is gone: nothing tells Claude to relaunch with the flag
                        self.assertNotIn("restart", (run.err + self.reason(run)).lower())
                runs += len(commands)
        self.assertEqual(self.refused(), runs)
        self.assertNotIn("ASKED", self.logged())

    def test_reads_and_dry_runs_pass(self):
        for mode in ("default", "bypassPermissions", None, "foo"):
            self.assert_silent(self.READS, mode=mode)
        self.assert_silent(self.READS, agent=True)
        self.assert_silent(self.READS, live_ok="1")
        self.assertEqual(self.logged(), {})

    def test_a_read_only_command_that_only_mentions_a_live_flag_passes(self):
        mentions = self.MENTIONS
        for mode in ("default", "bypassPermissions", None):
            self.assert_silent(mentions, mode=mode)
        self.assert_silent(mentions, agent=True)
        self.assertEqual(self.logged(), {})                    # nothing live: nothing to log

    def test_a_read_only_word_is_no_cover_for_a_second_command(self):
        chained = [
            "grep x; python3 tools/auto_sync.py --apply-salesforce",
            "grep x && python3 sync_attendance_form.py x --apply",
            "grep x || python3 sync_attendance_form.py x --apply",
            "grep x & python3 sync_attendance_form.py x --apply",
            "cat notes --apply | sh",
            "grep x $(python3 tools/auto_sync.py --apply-salesforce)",
            "grep x `python3 sync_attendance_form.py x --apply`",
            "grep x <(python3 sync_attendance_form.py x --apply)",
            "grep -- --apply docs/RUNBOOK.md > run.sh",
            "grep x docs\npython3 sync_attendance_form.py x --apply",
            "rg --pre 'python3 tools/auto_sync.py --apply-salesforce' x docs",
            "git grep --open-files-in-pager='python3 sync_attendance_form.py x --apply' x",
            "git grep -Opython3 --apply x", "git grep -nOpython3 --apply x",
            "rg '--pre' 'python3 sync_attendance_form.py x --apply' docs", "git grep '-Opython3' --apply x",
            # first words that are not read-only
            "echo --apply", "git commit -m 'docs: --apply in the runbook'", "sed -n '/--apply/p' docs/RUNBOOK.md",
            "git -C . log --grep=--apply", "GREP=1 grep -- --apply docs",
            # the characters count even quoted: a regex alternation is not read-only enough
            "grep -nE -- '--apply|--prune' docs/RUNBOOK.md",
        ]
        self.assert_asks(chained)                                       # Ryan decides, in the session
        self.assertEqual(self.logged(), {"ASKED": len(chained)})
        self.assert_denies(chained, mode="bypassPermissions")           # ... and only there


if __name__ == "__main__":
    unittest.main(verbosity=1)
