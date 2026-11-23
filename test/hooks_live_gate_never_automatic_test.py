#!/usr/bin/env python3
"""
.claude/hooks/live_gate.sh (Bash), run as Claude Code runs it (the harness, the hooks and
settings it reads, and the osascript stub: test/helpers/hooks.py): what never gets the automatic
go of a backed write, every backup on record notwithstanding.

Since 2026-10-26 (ticket #146) a live write whose backup from today is on record goes through with
no prompt (test/hooks_live_gate_backed_test.py). Never automatic: a chained command (a # too), one
whose first word is no allowed launcher (python3 by its name or any path ending /python3, node,
npm, npx, sf, sfdx, gh, curl, clasp - never env, sudo, nohup, time, exec, command, xargs, a shell's
-c or a VAR=value), a tool no pinned list names by its exact file name (FORM_TOOLS, SF_LISTED,
sheets_client.py import; auto_sync.py with --apply-salesforce); plan mode, an unknown mode and a
write without its backup: test/hooks_live_gate_unbacked_test.py; the DELETES:
test/hooks_live_gate_refusals_test.py.
"""
import collections
import os
import shlex
import unittest

# first: importing helpers.common (through helpers.hooks) puts the repository root and tools/ on sys.path
from helpers.hooks import HookFixture, needs_bash, nest

F1, F2 = HookFixture.F1, HookFixture.F2                 # the fictional form ids, for the lists below


@needs_bash
class LiveGateNeverAutomatic(HookFixture, unittest.TestCase):
    NEVER_AUTOMATIC = [
        "python3 tools/drive_photos.py --apply",                       # no backup kind of its own
        "node drive-sync/move.js --apply",
        # the Salesforce tools off SF_LISTED (read 2026-10-26): no rollback record of their own
        # before each write - sf_new_clubs.py and sf_session_timing.py have no standalone write at
        # all, the others are no tool of the repository - and fix_module_values.py, a Salesforce
        # writer whose name is no tools/sf_*.py
        "python3 tools/sf_madeup_tool.py --apply --vpn-off",
        "python3 tools/sf_rehearsal_example.py merge --plan data/plan.json --rehearse",
        "python3 tools/sf_new_clubs.py check --vpn-off --roster data/roster.csv --summary data/plan_Asia.json --apply",
        "python3 tools/sf_session_timing.py check --vpn-off --apply",
        "python3 tools/sf_backfill_v2.py send --apply --vpn-off",
        "python3 tools/sf_partner_monthly_old.py --month 2026-09 --apply --vpn-off",
        "python3 tools/fix_module_values.py --vpn-off --apply --limit 1",
        # tools whose --apply writes the Sheet, not a form (read 2026-10-26), and no sheets_client.py
        # import: no backup kind covers them
        "python3 tools/upload_roster.py --apply --replace",
        "python3 tools/deactivate_clubs.py --partner \"Demo Partner\" --club \"Sunrise Club\" --reason \"moved\" --apply",
        "gh api repos/o/r/dispatches -f event_type=roster-changed",
        "gh api repos/o/r/actions/workflows/auto-sync.yml/dispatches -f ref=main",
        "gh api graphql -F query=@m.graphql",
        "curl -X POST https://api.github.com/repos/o/r/dispatches -d @in.json",
        "curl -X POST https://api.github.com/graphql -d @query.json",
        # an allowlist, not a denylist (ruling after the breaker, round 2): a tool is automatic only
        # by its exact file name on FORM_TOOLS or SF_LISTED (or sheets_client.py import) - a made-up
        # writer, a tool whose --apply writes nothing live, and names that only resemble a listed
        # tool ask, a --form whose backup is on record notwithstanding
        "python3 tools/madeup_writer.py --apply",
        f"python3 tools/madeup_writer.py --form {F1} --apply",
        "python3 tools/club_names.py --apply",
        "python3 tools/auto_sync_v2.py --apply",
        "python3 tools/rename_club_accounts.py --apply",
        f"python3 tools/rename_club_accounts.py --form {F2} --apply",
        "python3 tools/old_update_static_fields.py --apply",
        f"python3 tools/add_translations_v2.py --form {F1} --apply",
        f"python3 sync_attendance_form_old.py data/roster.csv --roster --region Africa --form {F1} --apply",
        "python3 tools/sf_backfill_old.py send --apply --vpn-off",
        # auto_sync.py with --apply-salesforce creates Salesforce accounts with no rollback record
        # (ruling after the test-author, round 1), whatever else it holds and in either order
        "python3 tools/auto_sync.py --apply --apply-salesforce",
        "python3 tools/auto_sync.py --apply-salesforce",
        "python3 tools/auto_sync.py --apply-salesforce --apply --region Asia",
    ]

    def test_an_unrecognised_write_is_never_automatic_whatever_the_backups(self):
        p = self.fully_backed()
        self.assert_backed(p)
        self.assert_never_automatic(self.NEVER_AUTOMATIC, p)
        counts = collections.Counter(d for d, _ in self.lines_of(p))
        self.assertEqual(counts["ALLOWED"], 1, "only the control is allowed")
        self.assertEqual(counts["ASKED"], len(self.NEVER_AUTOMATIC) * 2)
        self.assertEqual(len(self.quiet_notifications()), 1, "only the control is notified")

    def chained(self):
        jot = self.jotform_write()
        return [jot + "; echo done", "echo start; " + jot, jot + " && echo done", jot + " || true",
                jot + " | tee data/out.txt", jot + " &", jot + " 2>&1", jot + " > data/out.txt", jot + " >> data/out.txt",
                jot + " $(echo --quiet)", jot + " `echo --quiet`", jot + " --roster-file <(cat data/r.csv)",
                jot + "\necho done", jot + "\r\necho done", "echo start\n" + jot,
                f"python3 sync_attendance_form.py data/roster.csv --roster \\\n  --region Africa --form {self.F1} --apply",
                f"python3 sync_attendance_form.py data/roster.csv --roster \\\r\n  --region Africa --form {self.F1} --apply",
                "LANG=C " + jot, "JOTFORM_TIMEOUT=60 " + jot, "  TZ=UTC " + jot,
                "npx clasp push -f; echo done", "gh variable set SF_SYNC --body apply && echo done",
                "TZ=UTC gh variable set SF_SYNC --body apply",
                "sf project deploy start --source-dir data/sf_x/after -o glow | tee data/deploy.txt",
                "python3 tools/sheets_client.py import Roster data/roster.csv > data/import.txt",
                "python3 tools/sf_girls_present.py set --apply --vpn-off | tee data/set.txt",
                # a # can start a comment that hides text: never automatic, quoted or not (ruling
                # after the breaker)
                jot + "  # Ryan's go", jot + "#", f"python3 tools/add_translations.py --form {self.F1} --apply --note '#146'",
                "python3 tools/sheets_client.py import Roster data/roster#2.csv",
                "python3 tools/sf_partner_monthly.py --month 2026-09 --apply --vpn-off # September",
                # a launcher before it (ruling after the breaker, round 2): the first word is python3
                # (or a path ending /python3), node, npm, npx, sf, sfdx, gh, curl or clasp, or the
                # command is never automatic
                "env LANG=C " + jot, "env " + jot, "sudo " + jot, "sudo -u someone " + jot, "nohup " + jot,
                "time " + jot, "exec " + jot, "command " + jot, "xargs " + jot, "nice " + jot,
                "caffeinate -i " + jot, nest(jot, 1), "sh -c " + shlex.quote(jot), "zsh -c " + shlex.quote(jot),
                "sudo gh variable set SF_SYNC --body apply", "nohup npx clasp push -f",
                "time sf project deploy start --source-dir data/sf_x/after -o glow",
                "env python3 tools/sheets_client.py import Roster data/roster.csv",
                "exec python3 tools/sf_partner_monthly.py --month 2026-09 --apply --vpn-off",
                nest("gh workflow run auto-sync.yml -f apply=true", 1)]

    def test_a_chained_or_prefixed_backed_write_is_never_automatic(self):
        # one simple command or nothing: a second command, a redirection, a substitution, a line
        # break (a backslash-newline too), a #, a VAR=value or a launcher before it takes it back
        # to the prompt
        p = self.fully_backed()
        self.assert_backed(p)
        # the clasp ones run in appsscript/, where clasp push alone goes through (F2 of PR #154's
        # review): what keeps them from the automatic go is the chain or the launcher
        appsscript = os.path.join(p, "appsscript")
        run = self.gate("npx clasp push -f", mode="dontAsk", project=p, cwd=appsscript, may_allow=True)
        self.assertEqual(self.verdict(run), "allow", "the control: clasp push in appsscript/ - " + self.show(run))
        commands = [(c, {"cwd": appsscript}) if "clasp" in c else c for c in self.chained()]
        self.assert_never_automatic(commands, p)
        counts = collections.Counter(d for d, _ in self.lines_of(p))
        self.assertEqual(counts["ALLOWED"], 2, "only the controls are allowed")
        self.assertEqual(len(self.quiet_notifications()), 2, "only the controls are notified")

    def test_the_interpreter_by_any_path_is_the_command_itself_and_goes_through(self):
        # the control of the launcher allowlist: python3 by its name, the venv's or any other path
        # ending /python3, and clasp by its own name, are the command itself - allowed on their
        # backups, where each launcher of chained() is not
        p = self.fully_backed()
        tail = self.jotform_write()[len("python3"):]
        commands = [python + tail for python in ("python3", ".venv/bin/python3", "/usr/bin/python3",
                                                 "/opt/homebrew/bin/python3", os.path.join(p, ".venv", "bin", "python3"))]
        commands += [".venv/bin/python3 tools/sheets_client.py import Roster data/roster.csv", "clasp push -f",
                     "/opt/homebrew/bin/python3 tools/sf_partner_monthly.py --month 2026-09 --apply --vpn-off"]
        callers = [{"mode": "dontAsk"}, {"mode": None}, {"mode": "auto", "agent": True}]
        # (clasp in appsscript/, the folder it pushes from: F2 of PR #154's review)
        cases = [(command, dict(caller, project=p, may_allow=True,
                                cwd=os.path.join(p, "appsscript") if "clasp" in command else None))
                 for command in commands for caller in callers]
        for command, kw, run in self.verdicts(cases):
            with self.subTest(command=command, mode=kw["mode"], agent=kw.get("agent")):
                self.assertEqual(self.verdict(run), "allow", self.show(run))
        counts = collections.Counter(d for d, _ in self.lines_of(p))
        self.assertEqual(counts, {"ALLOWED": len(cases)}, "one ALLOWED line per allow, nothing else")


if __name__ == "__main__":
    unittest.main(verbosity=1)
