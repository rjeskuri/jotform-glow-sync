#!/usr/bin/env python3
"""
The Claude Code guardrail hooks, run as Claude Code runs them: the tool input as JSON on
standard input, the decision in the exit code (0 lets the command or edit through, 2 blocks it).

  - .claude/hooks/live_gate.sh (Bash): every live-system command is blocked unless the human
    exported GLOW_LIVE_OK=1 before launching, and a command that sets it itself always is; a
    read-only command that only mentions a live flag passes, a chained one does not;
  - .claude/hooks/protected_paths.sh (Edit|Write|MultiEdit): data/, backups/, credentials/,
    .env, the generated Regions.gs and the guardrails themselves are refused in every copy of the
    repository (main checkout, worktree, sibling checkout) and for a relative path.

CLAUDE_PROJECT_DIR is a temporary folder, so the gate's log never lands in the repository, and
GLOW_LIVE_OK is removed from the environment unless a test sets it.
"""
import collections
import concurrent.futures
import json
import os
import re
import subprocess
import tempfile
import unittest

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import REPO

HOOKS = os.path.join(REPO, ".claude", "hooks")
BASH = "/bin/bash"                  # the hooks' shebang


@unittest.skipUnless(os.access(BASH, os.X_OK), "no /bin/bash to run the hooks with")
class Hooks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.tmp.name, ".claude"))
        self.log = os.path.join(self.tmp.name, ".claude", "live_gate.log")

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, name, tool_input, live_ok=None, tool="Bash"):
        env = {k: v for k, v in os.environ.items() if k != "GLOW_LIVE_OK"}
        env["CLAUDE_PROJECT_DIR"] = self.tmp.name
        if live_ok is not None:
            env["GLOW_LIVE_OK"] = live_ok
        done = subprocess.run([os.path.join(HOOKS, name)], input=json.dumps(
            {"tool_name": tool, "tool_input": tool_input}), env=env, capture_output=True, text=True,
            timeout=30)
        return done.returncode, done.stderr

    def gate(self, command, live_ok=None):
        return self.run_hook("live_gate.sh", {"command": command}, live_ok)[0]

    def logged(self):
        """How many decisions of each kind the log holds (a logged command may span lines)."""
        if not os.path.exists(self.log):
            return collections.Counter()
        with open(self.log, encoding="utf-8") as f:
            return collections.Counter(re.findall(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d (ALLOWED|BLOCKED) ",
                                                  f.read(), re.M))

    @staticmethod
    def all_of(fn, items):
        """fn over items, eight hooks at a time (each is a few processes), results in order."""
        with concurrent.futures.ThreadPoolExecutor(8) as pool:
            return list(pool.map(fn, items))

    def assert_gate(self, commands, code, live_ok=None):
        for command, got in zip(commands, self.all_of(lambda c: self.gate(c, live_ok), commands)):
            with self.subTest(command=command):
                self.assertEqual(got, code, command)

    def assert_edit(self, paths, code):
        for path, got in zip(paths, self.all_of(self.edit, paths)):
            with self.subTest(path=path):
                self.assertEqual(got, code, path)

    # ---- live_gate.sh
    LIVE = [
        # the tools' write flags and the raw API shapes they wrap (gated before 2026-10-09)
        "python3 sync_attendance_form.py roster.csv --roster --region Africa --form 1 --apply",
        "python3 sync_attendance_form.py roster.csv --roster --region Africa --form 1 --prune",
        "cd appsscript && npx clasp push -f", "npm run clasp:push",
        "python3 tools/sheets_client.py import Roster roster.csv",
        "python3 tools/auto_sync.py --apply-salesforce",
        "curl -sS -X PUT 'https://api.jotform.com/form/1/properties?apiKey=x' -d @rules.json",
        "curl -X POST https://api.github.com/repos/owner/repo/dispatches -d '{}'",
        "python3 -c 'import sync_attendance_form as s; s.Jotform(k, 1, apply_changes=True)'",
        "python3 -c 'svc.spreadsheets().values().update(body=b).execute()'",
        "python3 -c 'svc.spreadsheets().batchUpdate(body=b).execute()'",
        # GitHub: the sync's switches and an applying run
        "gh variable set SF_SYNC --body apply",
        "gh -R owner/repo variable set AUTO_SYNC_APPLY --body 1",
        "gh --repo=owner/repo secret set GLOW_SA_JSON < key.json",
        "gh secret set JOTFORM_API_KEY",
        "gh workflow run auto-sync.yml -f apply=true",
        "gh workflow run auto-sync.yml --field apply=true -f region=Africa",
        "gh workflow run auto-sync.yml -F apply=true",
        "gh workflow run auto-sync.yml -f 'apply=true'",
        "gh workflow run auto-sync.yml -f apply=\"true\"",
        "gh workflow run auto-sync.yml \\\n  -f apply=true",
        "echo '{\"apply\": \"true\"}' | gh workflow run auto-sync.yml --json",
        # ... and the other spellings of the same switches (review of 2026-10-09)
        "gh workflow run auto-sync.yml -F apply=@/tmp/yes",
        "gh workflow run auto-sync.yml --json < inputs.json",
        "gh workflow run auto-sync.yml -f apply=$APPLY",
        "gh run rerun 1234", "gh run rerun 1234 --failed", "gh -R owner/repo run rerun 1234",
        "gh secret delete GLOW_SA_JSON", "gh variable delete SF_SYNC", "gh variable remove AUTO_SYNC_APPLY",
        "gh workflow disable auto-sync.yml", "gh workflow enable auto-sync.yml",
        "gh api -X PATCH repos/o/r/actions/variables/SF_SYNC -f value=apply",
        "gh api --method=PATCH repos/o/r/actions/variables/SF_SYNC --input body.json",
        "gh api -X POST repos/o/r/actions/variables -f name=SF_SYNC -f value=apply",
        "gh api -X DELETE repos/o/r/actions/variables/SF_SYNC",
        "gh api repos/o/r/actions/workflows/auto-sync.yml/dispatches -f ref=main -f 'inputs[apply]=true'",
        "gh api repos/o/r/dispatches -f event_type=roster-changed",
        "gh api -XPUT repos/o/r/actions/secrets/GLOW_SA_JSON --raw-field encrypted_value=x",
        # Salesforce: a deploy (check-only too), data writes, anonymous Apex, the rehearsal
        "sf project deploy start --source-dir force-app -o glow",
        "sf project deploy start --dry-run --source-dir force-app -o glow",
        "sf project deploy validate --source-dir force-app -o glow",
        "sf project deploy quick --job-id 0Af000000000001 -o glow",
        "sf data create record -s Account -v \"Name='Sunrise Club'\" -o glow",
        "sf data update record -s Account -i 001000000000001 -v \"Name=X\"",
        "sf data delete record -s Contact -i 003000000000001",
        "sf data upsert bulk -s Contact -f contacts.csv -i Id",
        "sf data import tree -f accounts.json",
        "sf apex run --file merge.apex -o glow",
        "/opt/homebrew/bin/sf apex run -f merge.apex",
        "python3 tools/sf_dupes.py merge --plan data/plan.json --rehearse",
        # ... and the other spellings of the same writes (review of 2026-10-09)
        "sfdx apex run -f merge.apex -o glow", "sfdx project deploy start -d force-app",
        "sf force:apex:execute -f merge.apex", "sfdx force:apex:execute -f merge.apex -u glow",
        "sfdx force:source:deploy -p force-app", "sfdx force:source:push", "sfdx force:source:delete -m ApexClass:X",
        "sfdx force:mdapi:deploy -d mdapi", "sfdx force:data:record:update -s Account -i 001x -v Name=X",
        "sfdx force:data:bulk:upsert -s Contact -f c.csv -i Id", "sfdx force:data:tree:import -f a.json",
        "sf deploy metadata -d force-app", "sf project delete source -m ApexClass:GlowSync",
        "curl -X PATCH https://example.my.salesforce.com/services/data/v60.0/sobjects/Account/001x -d @a.json",
        "curl https://login.salesforce.com/services/oauth2/token -d grant_type=client_credentials",
        "python3 -m sf_dupes merge --rehearse", "cd tools && python3 sf_dupes.py merge --rehearse",
    ]

    def test_every_live_command_is_blocked_and_logged(self):
        self.assert_gate(self.LIVE, 2)
        self.assertEqual(self.logged(), {"BLOCKED": len(self.LIVE)})

    def test_the_humans_go_lets_them_through_and_is_logged(self):
        self.assert_gate(self.LIVE, 0, live_ok="1")
        self.assertEqual(self.logged(), {"ALLOWED": len(self.LIVE)})
        self.assert_gate(["python3 sync_attendance_form.py x --apply"], 2, live_ok="yes")   # only "1"

    def test_a_command_that_approves_itself_is_blocked_even_with_the_go(self):
        for live_ok in (None, "1"):
            self.assert_gate(["GLOW_LIVE_OK=1 python3 tools/auto_sync.py --apply-salesforce",
                              "export GLOW_LIVE_OK=1",
                              "env GLOW_LIVE_OK=1 python3 sync_attendance_form.py x --apply",
                              "GLOW_LIVE_OK+=1 python3 sync_attendance_form.py x --apply",
                              "echo GLOW_LIVE_OK=1 >> ~/.zshrc"], 2, live_ok)

    def test_reads_and_dry_runs_pass(self):
        self.assert_gate(["ls", "make check", "python3 tools/auto_sync.py",
                          "python3 tools/form_status.py --roster r.csv --partners p.csv",
                          "python3 sync_attendance_form.py roster.csv --roster --region Africa --form 1",
                          "gh run list", "gh run view 123", "gh workflow list", "gh variable list",
                          "gh secret list", "gh workflow view auto-sync.yml", "gh run download 1234",
                          "gh api repos/o/r/actions/variables", "gh api -X GET repos/o/r/actions/runs --jq '.total_count'",
                          "gh api repos/o/r/actions/runs/1234/logs > run.zip",
                          "gh api -X PATCH repos/o/r/issues/1 -f title=x",       # not a switch of the sync
                          "gh workflow run auto-sync.yml", "gh workflow run auto-sync.yml -f apply=false",
                          "sf org list", "sf data query -q 'SELECT Id FROM Account' -o glow",
                          "sf project deploy report --job-id 0Af000000000001", "sfdx force:org:list",
                          "sf project retrieve start -m ApexClass:GlowSync", "sfdx force:data:soql:query -q 'SELECT Id FROM Account'",
                          "python3 tools/sf_dupes.py check",
                          "python3 tools/sf_dupes.py plan", "git status"], 0)
        self.assertEqual(self.logged(), {})

    def test_a_read_only_command_that_only_mentions_a_live_flag_passes(self):
        # 20 of the 31 blocks logged by 2026-10-09 were these: grep, git, cat on the docs
        self.assert_gate(["grep -n -- '--apply' docs/RUNBOOK.md",
                          "grep -rn 'GLOW_LIVE_OK=' docs .claude",
                          "rg -n -- '--apply-salesforce' docs tools",
                          "cat docs/plans/2026-10-06-sf-new-club-accounts.md --apply",
                          "head -50 docs/RUNBOOK.md --prune", "tail -n 5 .claude/live_gate.log --apply",
                          "wc -l --apply", "ls --apply",
                          "git log --oneline --grep=--apply", "git show HEAD -- '*--apply*'",
                          "git diff main -- docs/RUNBOOK.md --apply", "git grep -n 'sf apex run' -- docs",
                          "git blame -L 1,5 docs/RUNBOOK.md --apply", "git status --apply",
                          "  grep -c 'gh variable set SF_SYNC' CLAUDE.md"], 0)
        self.assertEqual(self.logged(), {})                    # nothing live: nothing to log

    def test_a_read_only_word_is_no_cover_for_a_second_command(self):
        self.assert_gate([
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
        ], 2)

    # ---- protected_paths.sh
    def edit(self, path):
        return self.run_hook("protected_paths.sh", {"file_path": path, "content": "x"}, tool="Write")[0]

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
        _, why = self.run_hook("protected_paths.sh", {"file_path": root + "/data/x.csv"}, tool="Edit")
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
        self.assertEqual(self.run_hook("protected_paths.sh", {})[0], 0)        # no path: nothing to judge


if __name__ == "__main__":
    unittest.main(verbosity=1)
