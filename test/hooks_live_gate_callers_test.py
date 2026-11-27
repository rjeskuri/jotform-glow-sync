#!/usr/bin/env python3
"""
.claude/hooks/live_gate.sh (Bash), run as Claude Code runs it (the harness, the hooks and
settings it reads, and the osascript stub: test/helpers/hooks.py): who can be asked.

Without its backup from today a live write asks Ryan in the session, and is refused - with the
reason and the backup command - where no prompt can show (bypassPermissions, dontAsk, missing or
unknown mode, a subagent). The input is read as Claude Code sends it; one the hook cannot read
never lets a command through.

The prompt itself: test/hooks_live_gate_prompt_test.py.
"""
import json
import os
import unittest
import uuid

# first: importing helpers.common (through helpers.hooks) puts the repository root and tools/ on sys.path
from helpers.hooks import ASK_MODES, NO_PROMPT_MODES, UNKNOWN_MODES, HookFixture, needs_bash


@needs_bash
class LiveGateCallers(HookFixture, unittest.TestCase):
    def test_a_session_that_cannot_show_a_prompt_is_refused(self):
        # a headless or dispatched run, or a mode that skips prompts, cannot carry Ryan's go: the
        # command is refused with a message that says where it can run (fail closed)
        for mode in ASK_MODES:
            self.assert_asks(self.SAMPLE, mode=mode)
        for mode in NO_PROMPT_MODES:
            self.assert_denies(self.SAMPLE, mode=mode, saying=("interactive", "terminal"))
        # only the four spellings above ask: anything else is unknown, and fails closed
        for mode in UNKNOWN_MODES:
            self.assert_denies(self.SAMPLE, mode=mode)
        odd = [{"permission_mode": v} for v in (None, 1, True, ["default"], {"mode": "default"})]
        for fields in odd:
            self.assert_denies(self.SAMPLE, mode=None, extra=fields)
        self.assertEqual(self.logged()["ASKED"], len(self.SAMPLE) * len(ASK_MODES))
        self.assertEqual(self.refused(), len(self.SAMPLE) * (len(NO_PROMPT_MODES) + len(UNKNOWN_MODES) + len(odd)))
        # every decision line says which mode it was taken in
        for mode in [m for m in ASK_MODES + NO_PROMPT_MODES if m]:
            before = len(self.log_lines())
            self.gate(self.SAMPLE[0], mode=mode)
            lines = self.log_lines()
            self.assertEqual(len(lines), before + 1, lines[before:])
            decision, rest = lines[-1]
            self.assertIn(decision, ("ASKED",) if mode in ASK_MODES else ("BLOCKED", "DENIED"))
            self.assertIn(mode, rest, f"the log line does not name the mode: {decision} {rest}")

    def test_a_subagent_never_gets_the_prompt(self):
        # a subagent cannot show Ryan a prompt: without a backup from today (none here) its live
        # command is refused, and the refusal says it came from a subagent (since #146 a backed
        # write is allowed to it as to the main session: test_a_backed_write_goes_through_...).
        # The input says "subagent" with agent_id (any value). agent_type alone is a main session
        # started with --agent (review of 253135b): it is no subagent, and gets the mode's decision
        runs = 0
        for mode in ASK_MODES + NO_PROMPT_MODES:
            self.assert_denies(self.SAMPLE, mode=mode, agent=True, saying=("agent",))   # a fresh id each
            runs += len(self.SAMPLE)
        self.assert_denies(self.SAMPLE, agent=True, live_ok="1", saying=("agent",))
        runs += len(self.SAMPLE)
        ids = [uuid.uuid4().hex, str(uuid.uuid4()), "agent-" + uuid.uuid4().hex[:8], "a1", "0", "Explore-2"]
        for agent_id in ids:                                            # the id alone, whatever it is
            self.assert_denies(self.SAMPLE, agent=agent_id, saying=("agent",))
        runs += len(self.SAMPLE) * len(ids)
        self.assertEqual(self.refused(), runs)
        self.assertNotIn("ASKED", self.logged())
        # the type alone: a main session (claude --agent x) - asked where a prompt can show, refused
        # where none can, never refused for being an agent
        types = ("Explore", "harness:coder", "general-purpose")
        for agent_type in types:
            for mode in ASK_MODES:
                self.assert_asks(self.SAMPLE, mode=mode, agent_type=agent_type)
            self.assert_denies(self.SAMPLE, mode="dontAsk", agent_type=agent_type, saying=("interactive", "terminal"))
        self.assertEqual(self.logged()["ASKED"], len(self.SAMPLE) * len(ASK_MODES) * len(types))
        self.assertEqual(self.refused(), runs + len(self.SAMPLE) * len(types))

    def test_without_a_backup_the_gate_never_allows_and_never_stays_silent_on_a_live_command(self):
        # no backup on record (this project has no .claude/live_backups.log and is no git
        # repository): whatever the mode, the caller and the environment, Ryan's prompt or a
        # refusal, logged - never an allow, and no notification
        cases = [(command, mode, agent, live_ok) for command in self.SAMPLE
                 for mode in ASK_MODES + NO_PROMPT_MODES + ["foo", "Default", "default\n"]
                 for agent in (None, True) for live_ok in (None, "1")]
        for case, run in zip(cases, self.all_of(lambda c: self.gate(c[0], live_ok=c[3], mode=c[1], agent=c[2]), cases)):
            with self.subTest(case=case):
                self.assertIn(self.verdict(run), ("ask", "deny"), self.show(run))
                if run.err:
                    self.assertNotIn("GLOW_LIVE_OK=1", run.err)         # no longer a way through
        self.assertEqual(sum(self.logged().values()), len(cases))
        self.assertEqual(self.logged()["ASKED"] + self.refused(), len(cases))
        self.assertEqual(self.quiet_notifications(), [], "a notification without an allow")

    def test_the_real_pretooluse_input_is_read_as_claude_code_sends_it(self):
        # the whole input of a main-session Bash call, spelt out: it asks; with the subagent
        # fields on top it denies; the description is not the command
        live = "python3 sync_attendance_form.py roster.csv --roster --region Africa --form 1 --apply"
        session = "5b3f2c1e-7d9a-4e8b-9c1d-2a3b4c5d6e7f"
        main = {"session_id": session,
                "transcript_path": os.path.expanduser(f"~/.claude/projects/-Users-someone-jotform-glow-sync/{session}.jsonl"),
                "cwd": self.tmp.name, "hook_event_name": "PreToolUse", "tool_name": "Bash",
                "tool_input": {"command": live, "description": "Apply the roster to the Africa form"},
                "tool_use_id": "toolu_01Xy7Qk2Lm9Np4Rs6Tv8Wz1B", "permission_mode": "default"}
        run = self.run_hook("live_gate.sh", {}, raw=json.dumps(main))
        self.assertEqual(self.verdict(run), "ask", self.show(run))
        self.check_reason(live, self.reason(run))
        sub = dict(main, agent_id="agent-9f8e7d6c5b4a", agent_type="harness:coder")
        run = self.run_hook("live_gate.sh", {}, raw=json.dumps(sub))
        self.assertEqual(self.verdict(run), "deny", self.show(run))
        # a main session started with --agent names its type and no agent_id: it asks
        with_agent = dict(main, agent_type="harness:coder")
        run = self.run_hook("live_gate.sh", {}, raw=json.dumps(with_agent))
        self.assertEqual(self.verdict(run), "ask", self.show(run))
        read = dict(main, tool_input={"command": "grep -n -- '--apply' docs/RUNBOOK.md",
                                      "description": "Find --apply in the runbook"})
        run = self.run_hook("live_gate.sh", {}, raw=json.dumps(read))
        self.assertEqual(self.verdict(run), "silent", self.show(run))
        self.assertEqual(self.logged()["ASKED"], 2)
        self.assertEqual(self.refused(), 1)

    def test_an_input_the_hook_cannot_read_never_lets_a_command_through(self):
        # no command: nothing to judge, so no decision (the ticket's step 1); stdin that is not the
        # hook's JSON: no decision or a refusal - never an allow, never a crash (exit 0 or 2 only)
        for tool_input in ({}, {"description": "x"}, {"command": ""}, {"command": None}):
            with self.subTest(tool_input=tool_input):
                run = self.run_hook("live_gate.sh", tool_input)
                self.assertEqual(self.verdict(run), "silent", self.show(run))
        for raw in ("", "not json", "{", "[]", "null", '{"tool_input": "--apply"}',
                    '{"tool_name": "Bash", "tool_input": {"command": "x --apply"', "\x00"):
            with self.subTest(raw=raw):
                run = self.run_hook("live_gate.sh", {}, raw=raw)
                self.assertIn(self.verdict(run), ("silent", "deny"), self.show(run))
        self.assertEqual(self.logged(), {})


if __name__ == "__main__":
    unittest.main(verbosity=1)
