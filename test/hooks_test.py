#!/usr/bin/env python3
"""
The Claude Code guardrail hooks, run as Claude Code runs them: the tool input as JSON on
standard input, the decision in the exit code and on standard output (0 and nothing: no
decision; 0 and an ask JSON: Ryan is asked in the session; 2, or a deny JSON: refused).

  - .claude/hooks/live_gate.sh (Bash): every live-system command asks Ryan in the session
    (since 2026-10-14 GLOW_LIVE_OK pre-approves nothing), and is refused outright when the
    session cannot show him the prompt (permission_mode bypassPermissions, dontAsk, missing or
    unknown), from a subagent, and when the command approves itself; a read-only command that
    only mentions a live flag passes, a chained one does not; every gh api write is live. A #
    is text, never a comment (Ryan, 2026-10-14: reading comments as bash does let writes hide),
    and the gh api reader runs only when the command holds a gh word and the text api once
    quote and backslash characters are removed (a PR or issue body is not read);
  - .claude/settings.json: the permission rules behind the hook (every gh api command asks and
    none is allowed, since 2026-10-14; ask rules for the live families; the hook entry that
    blocks on failure);
  - .claude/hooks/protected_paths.sh (Edit|Write|MultiEdit): data/, backups/, credentials/,
    .env, the generated Regions.gs and the guardrails themselves are refused in every copy of the
    repository (main checkout, worktree, sibling checkout) and for a relative path;
  - .githooks/pre-commit, in a scratch repository: the lines a commit adds are scanned for
    secrets, and ruff checks every added, changed or renamed .py file as staged.

The hooks are read from $GLOW_HOOKS_DIR (default .claude/hooks) and the settings from
$GLOW_SETTINGS_FILE, else $GLOW_SETTINGS_JSON (default .claude/settings.json): no agent may edit
.claude/, so a candidate staged elsewhere is proven here before Ryan applies it by hand.
CLAUDE_PROJECT_DIR is a temporary folder, so the gate's log never lands in the repository, and
GLOW_LIVE_OK is removed from the environment unless a test sets it.
"""
import collections
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import REPO

HOOKS = os.environ.get("GLOW_HOOKS_DIR") or os.path.join(REPO, ".claude", "hooks")
SETTINGS = (os.environ.get("GLOW_SETTINGS_FILE") or os.environ.get("GLOW_SETTINGS_JSON")
            or os.path.join(REPO, ".claude", "settings.json"))
BASH = "/bin/bash"                  # the hooks' shebang

# the permission modes Claude Code puts in the hook's input: in exactly these four, spelt exactly
# so, a prompt can reach Ryan; in the other two, with the field missing (None), and with any
# other spelling (Manual arrives as "default", never "manual") nobody can answer one
ASK_MODES = ["default", "acceptEdits", "auto", "plan"]
NO_PROMPT_MODES = ["bypassPermissions", "dontAsk", None]
UNKNOWN_MODES = ["yolo", "foo", "", "Default", "DEFAULT", "acceptEdits ", "default\n", " plan", "auto\t",
                 "default auto", "bypasspermissions", "manual", "ask"]

Run = collections.namedtuple("Run", "code out err")


@unittest.skipUnless(os.access(BASH, os.X_OK), "no /bin/bash to run the hooks with")
class Hooks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.tmp.name, ".claude"))
        self.log = os.path.join(self.tmp.name, ".claude", "live_gate.log")

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, name, tool_input, live_ok=None, tool="Bash", project=None, mode="default", agent=None,
                 agent_type=None, extra=None, raw=None):
        """The hook on one tool call: exit code, stdout, stderr. `mode` is the input's
        permission_mode (None leaves it out); `agent` an agent_id (True: a fresh one, with an
        agent_type), `agent_type` that field alone; `extra` fields are set last (a null, a
        number); `raw` replaces the whole of stdin."""
        env = {k: v for k, v in os.environ.items() if k != "GLOW_LIVE_OK"}
        env["CLAUDE_PROJECT_DIR"] = project or self.tmp.name
        if live_ok is not None:
            env["GLOW_LIVE_OK"] = live_ok
        data = self.pretooluse(tool, tool_input, env["CLAUDE_PROJECT_DIR"], mode)
        if agent is True:
            data["agent_id"] = "agent-" + uuid.uuid4().hex
            data["agent_type"] = agent_type or "harness:coder"
        elif agent is not None:
            data["agent_id"] = agent
        if agent_type is not None:
            data["agent_type"] = agent_type
        data.update(extra or {})
        done = subprocess.run([os.path.join(HOOKS, name)], input=json.dumps(data) if raw is None else raw, env=env,
                              capture_output=True, text=True, timeout=30,
                              cwd=env["CLAUDE_PROJECT_DIR"] if os.path.isdir(env["CLAUDE_PROJECT_DIR"]) else None)
        return Run(done.returncode, done.stdout, done.stderr)

    @staticmethod
    def pretooluse(tool, tool_input, cwd, mode):
        """The input as Claude Code sends it to a PreToolUse hook, for a fictional session:
        session_id, transcript_path, cwd, hook_event_name, tool_name, tool_input, tool_use_id and
        permission_mode (left out when `mode` is None)."""
        session = str(uuid.uuid4())
        data = {"session_id": session,
                "transcript_path": os.path.join(os.path.expanduser("~"), ".claude", "projects",
                                                "-Users-someone-jotform-glow-sync", session + ".jsonl"),
                "cwd": cwd, "hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": dict(tool_input),
                "tool_use_id": "toolu_01" + uuid.uuid4().hex[:22].upper()}
        if mode is not None:
            data["permission_mode"] = mode
        return data

    def gate(self, command, live_ok=None, mode="default", **kw):
        run = self.run_hook("live_gate.sh", {"command": command, "description": "Run one command for the test"},
                            live_ok, mode=mode, **kw)
        # the one answer no input may ever get: Claude Code would skip Ryan's prompt
        self.assertNotEqual(self.verdict(run), "allow", f"{command!r} (mode {mode!r}, {kw}, "
                                                        f"GLOW_LIVE_OK {live_ok}) was ALLOWED: {run.out}")
        return run

    @staticmethod
    def verdict(run):
        """What Claude Code does with the hook's answer: "silent" (no decision: the normal
        permission flow), "ask" (Ryan's prompt), "deny" (an exit 2, or a deny decision), "allow",
        or a description of an answer it could not read."""
        text = run.out.strip()
        if run.code == 2:
            return "deny" if '"ask"' not in text else "exit 2 but an ask on stdout: " + text
        if run.code != 0:
            return f"exit {run.code}: {run.err}"
        if not text:
            return "silent"
        try:
            out = json.loads(text)["hookSpecificOutput"]
            if out["hookEventName"] != "PreToolUse":
                return "wrong hookEventName: " + text
            return out["permissionDecision"]
        except (ValueError, KeyError, TypeError):
            return "unreadable stdout: " + text

    @staticmethod
    def reason(run):
        try:
            return json.loads(run.out)["hookSpecificOutput"].get("permissionDecisionReason") or ""
        except (ValueError, KeyError, TypeError, AttributeError):
            return ""

    @staticmethod
    def show(run):
        return f"exit {run.code}; stdout {run.out!r}; stderr {run.err[:400]!r}"

    LINE = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d (ASKED|ALLOWED|BLOCKED|DENIED) (.*)$", re.M)

    def log_lines(self):
        """[(decision, the rest of the line)] of the gate's log (a logged command may span lines)."""
        if not os.path.exists(self.log):
            return []
        with open(self.log, encoding="utf-8") as f:
            return self.LINE.findall(f.read())

    def logged(self):
        """How many decisions of each kind the log holds."""
        return collections.Counter(decision for decision, _ in self.log_lines())

    def refused(self):
        """The refusals logged, under either word for one."""
        counts = self.logged()
        self.assertNotIn("ALLOWED", counts, "the gate logged an ALLOWED: nothing is pre-approved")
        return counts["BLOCKED"] + counts["DENIED"]

    @staticmethod
    def all_of(fn, items):
        """fn over items, eight hooks at a time (each is a few processes), results in order."""
        with concurrent.futures.ThreadPoolExecutor(8) as pool:
            return list(pool.map(fn, items))

    def runs(self, commands, **kw):
        return list(zip(commands, self.all_of(lambda c: self.gate(c, **kw), commands)))

    def check_reason(self, command, reason):
        """The prompt's text: the matched text, the command, why, and where to read more."""
        flat = command.replace("\r", " ").replace("\n", " ")
        shown = reason.replace("\r", " ").replace("\n", " ")
        matched = re.search(r'matched "(.+?)"', reason)
        self.assertIsNotNone(matched, f"no matched \"...\" in the reason: {reason!r}")
        # the matched text is the command's own, except for the gh/sf api writes, whose match
        # is a description - and only when the command is one, read as the shell reads it too
        # (continued lines joined, quotes and backslashes removed: g""h a\pi is gh api)
        cli = r"""(^|[^\w.-])["']?(gh|sf|sfdx)["']?\s[^;&|]*\bapi\b"""
        bare = re.sub(r"""["'\\]""", "", command.replace("\\\r\n", "").replace("\\\n", ""))
        api_cli = re.search(cli, flat) or re.search(cli, bare.replace("\r", " ").replace("\n", " "))
        self.assertTrue(matched.group(1) in flat or (api_cli and matched.group(1).startswith(("gh api", "sf api"))),
                        f"the matched text {matched.group(1)!r} is not in the command {flat!r}")
        if command in self.TRIGGERS:
            self.assertIn(self.TRIGGERS[command], reason, f"the reason does not name the family's trigger: {reason!r}")
        self.assertIn(flat[:20], shown, f"the reason does not name the command: {reason!r}")
        self.assertIn("live", reason.lower(), f"the reason does not say why: {reason!r}")
        self.assertIn("RUNBOOK", reason, reason)
        self.assertIn("Live gate (Claude Code)", reason, reason)          # the RUNBOOK section

    def assert_asks(self, commands, **kw):
        for command, run in self.runs(commands, **kw):
            with self.subTest(command=command, **kw):
                self.assertEqual(self.verdict(run), "ask", self.show(run))
                self.check_reason(command, self.reason(run))

    def assert_denies(self, commands, saying=(), **kw):
        """Refused: exit 2 (and no ask on stdout), or a deny decision; the message, on stderr or
        in the deny's reason, holds one of `saying`."""
        for command, run in self.runs(commands, **kw):
            with self.subTest(command=command, **kw):
                self.assertEqual(self.verdict(run), "deny", self.show(run))
                message = run.err + self.reason(run)
                if saying:
                    self.assertTrue(any(s in message.lower() for s in saying),
                                    f"none of {saying} in the message: {message!r}")

    def assert_silent(self, commands, **kw):
        for command, run in self.runs(commands, **kw):
            with self.subTest(command=command, **kw):
                self.assertEqual(self.verdict(run), "silent", self.show(run))

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
        "gh workflow run auto-sync.yml -F apply=@yes.txt",
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
        # the REST and GraphQL API through the CLI, a relative path (found 2026-10-09)
        "sf api request rest '/services/data/v60.0/sobjects/Account/001x' -X PATCH --body '{}'",
        "sf api request rest /services/data/v60.0/sobjects/Account --method POST --body @account.json",
        "sf api request rest /services/data/v60.0/sobjects/Account/001x -XDELETE -o glow",
        "sf api request rest /services/data/v60.0/sobjects/Account/001x --method=delete",
        "sf api request rest /services/data/v60.0/sobjects/Account -b '{\"Name\": \"X\"}'",
        "sf api request rest --file request.json -o glow", "sf api request rest -f request.json",
        "sfdx api request rest /services/data/v60.0/sobjects/Account/001x -X PUT -b @a.json",
        "sf api request graphql --body '{\"query\": \"mutation { x }\"}'", "sf api request graphql --body @query.txt",
    ]
    # one of each family, for the tests that walk the modes
    SAMPLE = [LIVE[0], "cd appsscript && npx clasp push -f", "python3 tools/sheets_client.py import Roster roster.csv",
              "curl -sS -X PUT 'https://api.jotform.com/form/1/properties?apiKey=x' -d @rules.json",
              "gh variable set SF_SYNC --body apply", "gh workflow run auto-sync.yml -f apply=true",
              "gh api repos/o/r/issues -f title=x", "sf project deploy start --source-dir force-app -o glow",
              "python3 tools/sf_dupes.py merge --plan data/plan.json --rehearse"]
    # what the prompt must name for one command of each family: its own trigger
    TRIGGERS = {
        LIVE[0]: "--apply", LIVE[1]: "--prune",
        "cd appsscript && npx clasp push -f": "clasp push", "npm run clasp:push": "clasp:push",
        "python3 tools/sheets_client.py import Roster roster.csv": "sheets_client.py import",
        "python3 tools/auto_sync.py --apply-salesforce": "--apply",
        "curl -sS -X PUT 'https://api.jotform.com/form/1/properties?apiKey=x' -d @rules.json": "api.jotform.com",
        "curl -X POST https://api.github.com/repos/owner/repo/dispatches -d '{}'": "api.github.com/repos/owner/repo/dispatches",
        "python3 -c 'import sync_attendance_form as s; s.Jotform(k, 1, apply_changes=True)'": "apply_changes=True",
        "python3 -c 'svc.spreadsheets().values().update(body=b).execute()'": "values().update",
        "python3 -c 'svc.spreadsheets().batchUpdate(body=b).execute()'": "batchUpdate",
        "gh variable set SF_SYNC --body apply": "gh variable set", "gh secret set JOTFORM_API_KEY": "gh secret set",
        "gh workflow run auto-sync.yml -f apply=true": "gh workflow run", "gh run rerun 1234": "gh run rerun",
        "gh workflow disable auto-sync.yml": "gh workflow disable", "gh variable delete SF_SYNC": "gh variable delete",
        "gh api -X PATCH repos/o/r/actions/variables/SF_SYNC -f value=apply": "gh api",
        "sf project deploy start --source-dir force-app -o glow": "sf project deploy start",
        "sf data create record -s Account -v \"Name='Sunrise Club'\" -o glow": "sf data create",
        "sf apex run --file merge.apex -o glow": "sf apex run",
        "python3 tools/sf_dupes.py merge --plan data/plan.json --rehearse": "--rehearse",
        "sfdx force:source:deploy -p force-app": "force:source:deploy",
        "sf deploy metadata -d force-app": "sf deploy metadata",
        "curl -X PATCH https://example.my.salesforce.com/services/data/v60.0/sobjects/Account/001x -d @a.json":
            ".salesforce.com/services/",
        "sf api request rest '/services/data/v60.0/sobjects/Account/001x' -X PATCH --body '{}'": "sf api request rest",
        "sf api request graphql --body '{\"query\": \"mutation { x }\"}'": "sf api request graphql",
    }
    # a command that approves itself: the flag in the command, or written where the next launch
    # reads its environment (review of 2026-10-09)
    SELF_APPROVING = ["GLOW_LIVE_OK=1 python3 tools/auto_sync.py --apply-salesforce",
                      "export GLOW_LIVE_OK=1",
                      "env GLOW_LIVE_OK=1 python3 sync_attendance_form.py x --apply",
                      "GLOW_LIVE_OK+=1 python3 sync_attendance_form.py x --apply",
                      "echo GLOW_LIVE_OK=1 >> ~/.zshrc"]
    STARTUP_WRITES = ["printf 'export GLOW_LIVE_OK\\x3d1' >> ~/.zshrc",
                      "printf 'export X\\x3d1\\n' > $HOME/.zprofile", "echo x | tee -a ~/.zshenv",
                      "echo x | tee ~/.bashrc", "cat snippet >> ~/.bash_profile", "echo x >>~/.profile",
                      "echo x > ~/.zlogin", "sed -i '' 's/a/b/' ~/.zshrc", "sed -e 's/a/b/' -i ~/.bash_login",
                      "sed --in-place 's/a/b/' ~/.bashrc", "perl -pi -e 's/a/b/' ~/.zshrc",
                      "echo 'export A=1' > .envrc", "printf 'A\\x3d1' >> .env",
                      "launchctl setenv GLOW_LIVE_OK 1"]
    READS = ["ls", "make check", "python3 tools/auto_sync.py",
             "python3 tools/form_status.py --roster r.csv --partners p.csv",
             "python3 sync_attendance_form.py roster.csv --roster --region Africa --form 1",
             "gh run list", "gh run view 123", "gh workflow list", "gh variable list",
             "gh secret list", "gh workflow view auto-sync.yml", "gh run download 1234",
             "gh api repos/o/r/actions/variables", "gh api -X GET repos/o/r/actions/runs --jq '.total_count'",
             "gh api repos/o/r/actions/runs/1234/logs > run.zip",
             "gh workflow run auto-sync.yml", "gh workflow run auto-sync.yml -f apply=false",
             "sf org list", "sf data query -q 'SELECT Id FROM Account' -o glow",
             "sf project deploy report --job-id 0Af000000000001", "sfdx force:org:list",
             "sf project retrieve start -m ApexClass:GlowSync", "sfdx force:data:soql:query -q 'SELECT Id FROM Account'",
             "sf api request rest '/services/data/v60.0/query?q=SELECT+Id+FROM+Account' -o glow",
             "sf api request rest /services/data/v60.0/limits", "sf api request rest /services/data/v60.0/ -X GET",
             "sf api request rest /services/data/v60.0/ --stream-to-file out.txt --include",
             "python3 tools/sf_dupes.py check",
             # the startup files read, or a copy of one written
             "cat ~/.zshrc", "grep -n PATH ~/.zshrc", "tail -5 ~/.bash_profile", "ls -la ~/.zshrc",
             "wc -l .envrc", "cp ~/.zshrc ~/.zshrc.bak", "echo x > ~/.zshrc.bak", "source .env",
             "python3 tools/sf_dupes.py plan", "git status"]
    # gh api: a write is a method other than GET, or fields / --input (which make it a POST)
    # without an explicit GET, or any graphql call - on any path, not only actions/ or /dispatches
    GH_API_WRITES = [
        "gh api -X PATCH repos/o/r/issues/1 -f title=x",
        "gh api repos/o/r/issues -f title=x",
        "gh api repos/o/r/issues/1/comments --raw-field body=x",
        "gh api --method DELETE repos/o/r/git/refs/heads/x",
        "gh api -XPUT repos/o/r/pulls/1/merge",
        "gh api repos/o/r/contents/a.md --input body.json",
        "gh api graphql -f query='query { viewer { login } }'",
        "gh api graphql -F query=@m.graphql",
        "gh -R o/r api repos/o/r/labels -f name=x",
        # the same writes spelt otherwise
        "gh api -X post repos/o/r/issues -f title=x",                    # the method in any case
        "gh api --method=patch repos/o/r/issues/1 -f state=closed",
        "gh api -F name=x repos/o/r/labels",                             # the field before the path
        "gh api --field body=x repos/o/r/issues/1/comments",
        "gh api repos/o/r/pulls/1/reviews -f event=APPROVE",           # the loop's path, written to
        "gh api repos/o/r/issues/36/comments -f body='done'",
        "gh api user/repos -f name=scratch",                             # not under repos/
        "gh api orgs/o/actions/variables -f name=SF_SYNC -f value=x",
        "gh --repo o/r api repos/o/r/labels -F name=x",
        "gh api graphql -f query='mutation { x }'",
        "gh api -X DELETE repos/o/r/labels/x",
        "gh api repos/o/r/git/refs -f ref=refs/heads/x -f sha=abc",
        # GET as a value or inside a word is no method
        "gh api -X POST repos/o/r/issues -f title=GET",
        "gh api -X DELETE repos/o/r/labels/BUDGET",
        "gh api -X PATCH repos/o/r/contents/TARGET.md -f message=x",
        "gh api repos/o/r/issues -f title=GETTING_STARTED",
        "gh api repos/o/r/issues/1/comments -f body=target",
        "gh api --method PUT repos/o/r/pulls/1/merge -f merge_method=GET",
        # the method or field flag in a combined shorthand (pflag: -iX DELETE is -i -X DELETE,
        # -iXPOST is -i -X POST, -if body=x is -i -f body=x) or quoted the shell's other ways
        # (review of PR #41)
        "gh api -iX DELETE repos/o/r/labels/x",
        "gh api -iXPOST repos/o/r/issues -f title=x",
        "gh api -iXDELETE repos/o/r/labels/x",
        "gh api -iF name=x repos/o/r/labels",
        "gh api -if body=x repos/o/r/issues/1/comments",
        "gh api -X$'POST' repos/o/r/issues -f title=x",
        "gh api --method=$'DELETE' repos/o/r/labels/x",
        "gh api -X \"PUT\" repos/o/r/pulls/1/merge",
        "gh api -i --method DELETE repos/o/r/labels/x",
        # a GET inside a field's value is a value, not the method: the fields make it a POST
        "gh api repos/o/r/issues/36/comments -f body='use curl -X GET first'",
        "gh api repos/o/r/issues -f body=\"--method GET\"",
        "gh api repos/o/r/issues -f title='--method=get'",
        "gh api repos/o/r/issues -f note='-X GET' -f title=x",
        "gh api repos/o/r/issues/1/comments --raw-field body='gh api -X GET repos/o/r/issues'",
        # a # is text wherever it stands, never a comment (Ryan, 2026-10-14; before, a # at the
        # start of a word was read as bash reads a comment, and the reader dropped what followed)
        "# add the label\ngh api repos/o/r/labels -f name=x",
        "gh api repos/o/r/issues/1 # read the state\ngh api -X DELETE repos/o/r/issues/1/labels/x",
        "gh api repos/o/r/issues#x -XPOST",
        "gh api -X GET repos/o/r/issues -f q=bug#12; gh api -X DELETE repos/o/r/labels/x",
        "gh api repos/o/r/pulls/1 --jq .state # then\ngh api -XPUT repos/o/r/pulls/1/merge",
        "gh api repos/o/r/issues -f body='#1 done'",                     # a quoted # is data
        "gh api repos/o/r/issues -f title=\"#12 again\"",
        # ... so a write method after a # on the gh api line is a flag of that command (it asks
        # since 2026-10-14; before, it was a comment and passed)
        "gh api repos/o/r/pulls/1 # then -X DELETE it",
        # gh or api quoted, or split over a continued line, is still gh api
        "gh \"api\" -X POST repos/o/r/issues",
        "\"gh\" api -X POST repos/o/r/issues",
        "gh \\\n  api -X POST repos/o/r/issues",
        "gh 'api' -X POST repos/o/r/issues",
        "'gh' api -XPOST repos/o/r/issues",
        # a # glued to the ) of $(...), $((...)), <(...) or >(...) is text, and the ; still splits
        "echo $(echo x)#t; gh api -X POST repos/o/r/issues",
        "$((1+1))#n; gh api -X DELETE repos/o/r/labels/x",
        "cat <(echo x)#t; gh api -X PUT repos/o/r/pulls/1/merge",
        "echo x > >(cat)#t; gh api -XPATCH repos/o/r/issues/1 -f state=closed",
        "(true)#c\ngh api -X POST repos/o/r/issues",
        # zsh expands =gh to gh's path; a split or quoted api is still api
        "=gh api -X POST repos/o/r/issues",
        "gh a\"\"pi -X POST repos/o/r/issues",
        "gh 'a'pi -XPOST repos/o/r/issues",
        # what the settings' ask rule Bash(gh api:*) misses (research on 2.1.299, 2026-10-14), so
        # the hook is the only layer: a shell or eval running the text, gh by its full path, and
        # a quoted or split subcommand word
        "bash -c \"gh api -X POST repos/o/r/issues\"",
        "sh -c 'gh api repos/o/r/labels -f name=x'",
        "zsh -c \"gh api -XDELETE repos/o/r/labels/x\"",
        "eval \"gh api --method PATCH repos/o/r/issues/1 -f state=closed\"",
        "/opt/homebrew/bin/gh api -X POST repos/o/r/issues",
        "/usr/local/bin/gh api graphql -f query=x",
        "gh ap\"\"i -X POST repos/o/r/issues",
        "gh 'api' repos/o/r/labels -f name=x",
    ]
    # a # is text (2026-10-14): each of these hid its write from the reader at 014d2ab, which
    # took the # for a comment's start and dropped the rest of the line (review of PR #41 at
    # 014d2ab): inside "$(...)" quotes, in backticks, in ${x:- #}, after a heredoc body whose
    # apostrophe the reader took for a quote, after zsh's =(...), after a case pattern's ) in $(...)
    HASH_IS_TEXT = [
        "gh pr comment 41 --body \"$(printf \"Closes #36\")\" && gh api repos/o/r/actions/variables/X -X PATCH -f value=true",
        "echo `echo #`; gh api -X PATCH repos/o/r/actions/variables/X -f value=true",
        "echo ${x:- #}; gh api -X PATCH repos/o/r/actions/variables/X -f value=true",
        "cat <<'EOF'\ndon't\nEOF\necho ' # '; gh api -X PATCH repos/o/r/actions/variables/X -f value=true",
        "cat =(echo x)#t; gh api -X POST repos/o/r/issues",
        "echo $(case a in a) echo y;; esac)#t; gh api -X POST repos/o/r/issues",
        # the same hiding places in front of the other kinds of write: fields, graphql, --input,
        # --raw-field, a bundled method, --method
        "gh issue comment 36 --body \"$(printf \"see #36\")\"; gh api repos/o/r/labels -f name=x",
        "echo `echo #`; gh api graphql -F query=@m.graphql",
        "echo ${x:- #}; gh api repos/o/r/contents/a.md --input body.json",
        "gh issue comment 36 --body-file - <<'EOF'\nIt's done\nEOF\necho ' # '; gh api -XDELETE repos/o/r/labels/x",
        "cat =(true)#t; gh api repos/o/r/issues/1/comments --raw-field body=x",
        "x=$(case $1 in -h) echo h;; esac)#c; gh api --method DELETE repos/o/r/git/refs/heads/x",
    ]
    # the gh api reader runs when the command holds a gh word and the text api once the quote and
    # backslash characters are removed (2026-10-14): a gh split by quotes or a backslash is gh
    SPLIT_GH_WRITES = [
        "g\"\"h api -X POST repos/o/r/issues",
        "g\\h api -X POST repos/o/r/issues",
        "g''h api -XPOST repos/o/r/issues -f title=x",
        "g\"h\" api repos/o/r/labels -f name=x",
        "\"g\"h api repos/o/r/contents/a.md --input body.json",
        "g\"\"h a\\pi graphql -f query=x",
        "echo ok; g\"\"h api -XPATCH repos/o/r/issues/1 -f state=closed",
        "\\gh api --method DELETE repos/o/r/labels/x",
        "gh a\"\"pi -X POST repos/o/r/issues",
        "'gh' api -X POST repos/o/r/issues",
        "=gh api -X POST repos/o/r/issues",
    ]
    # ... and a split gh that only reads is read like any other: no prompt
    SPLIT_GH_READS = ["g\"\"h api repos/o/r/pulls/1/reviews", "g\\h api --paginate repos/o/r/pulls/1/reviews",
                      "'gh' api repos/o/r/pulls/1", "gh ap\"\"i repos/o/r/pulls/1"]
    # a gh command with no api in it is never read as shell words, so a PR or issue body's odd
    # apostrophe (a heredoc is not shell syntax) cannot refuse it in a dispatched run (review of
    # 014d2ab); with api in its text but no gh api command, the reader runs and finds none
    GH_TEXT_SILENT = [
        "gh issue comment 36 --body-file - <<'EOF'\nIt's done.\nEOF",
        "gh pr create --title x --body \"$(cat <<'EOF'\nThe Ryan's note\nEOF\n)\"",
        "gh pr comment 41 --body-file - <<'EOF'\nRyan's go is on the ticket.\nEOF",
        "gh pr comment 41 --body-file - <<'EOF'\nDon't merge yet; it's #36.\nEOF",
        "gh pr comment 41 --body \"Closes #36\"",
        "gh pr create --title \"api docs\" --body \"Closes #36\"",
        "gh issue create --title x --body-file - <<'EOF'\nSee the api notes in #36.\nEOF",
    ]
    # a read with a comment that holds no write of its own command: the gate may pass it or ask
    # (a # is text); it never refuses it in the session and never allows it. The -X DELETE on
    # the line before gh is not a flag of gh api (orchestrator, 2026-10-14: silent or ask)
    GH_API_COMMENTED_READS = ["gh api repos/o/r/pulls/1  # check",
                              "gh api repos/o/r/pulls/1 # check\ngh api repos/o/r/pulls/2",
                              "# -X DELETE later\ngh api repos/o/r/pulls/1"]
    GH_API_READS = [
        "gh api repos/o/r/pulls/1/reviews",                              # the harness loop's reads
        "gh api --paginate repos/o/r/pulls/1/reviews",
        "gh api repos/o/r/pulls/1/reviews/2/comments",
        "gh api -X GET repos/o/r/issues -f state=open",                  # with GET the fields are the query
        "gh api --method GET search/issues -f q=x",
        "gh api repos/o/r/actions/variables",
        "gh api -X GET repos/o/r/actions/variables -f per_page=100",
        "gh api user", "gh api repos/o/r/pulls/1 --jq .state",
        "gh api -H 'Accept: application/vnd.github+json' repos/o/r/pulls/1",
        "gh api --paginate 'repos/o/r/issues?state=open'",
        "gh api -XGET repos/o/r/issues -F per_page=100",
        "gh api --method=GET repos/o/r/issues -f state=open",
        "gh -R o/r api repos/o/r/pulls/1/reviews",
        "gh api -i repos/o/r/pulls/1",
        # the method in any case, and after the fields
        "gh api -X get repos/o/r/issues -f state=open",
        "gh api --method=get repos/o/r/issues -f state=open",
        "gh api repos/o/r/issues -f state=open -X GET",
        "gh api repos/o/r/issues -F per_page=100 --method GET",
        # a real GET in a combined shorthand or quoted; a method inside a value is a value
        "gh api -iX GET repos/o/r/issues -f per_page=100",
        "gh api -iXGET repos/o/r/issues -f per_page=100",
        "gh api -X $'GET' repos/o/r/issues -f per_page=100",
        "gh api -X GET repos/o/r/issues -f q='see -X POST'",
        "gh api --method GET search/issues -f q='--method DELETE'",
        # (the comment cases moved, 2026-10-14: a # is text; see GH_API_COMMENTED_READS, and the
        # one whose gh api line holds -X DELETE after the # now asks, in GH_API_WRITES)
        # a read run by a shell, by eval or by gh's full path is still a read
        "bash -c \"gh api repos/o/r/pulls/1\"", "eval \"gh api --paginate repos/o/r/pulls/1/reviews\"",
        "/opt/homebrew/bin/gh api repos/o/r/pulls/1/reviews",
        # =gh is a word of its own only as a command; gh without api is not gh api
        "echo =gh", "gh pr view 1",
    ]

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
        # 20 of the 31 blocks logged by 2026-10-09 were these: grep, git, cat on the docs
        mentions = ["grep -n -- '--apply' docs/RUNBOOK.md",
                    "grep -rn 'GLOW_LIVE_OK=' docs .claude",
                    "rg -n -- '--apply-salesforce' docs tools",
                    "cat docs/plans/2026-10-06-sf-new-club-accounts.md --apply",
                    "head -50 docs/RUNBOOK.md --prune", "tail -n 5 .claude/live_gate.log --apply",
                    "wc -l --apply", "ls --apply",
                    "git log --oneline --grep=--apply", "git show HEAD -- '*--apply*'",
                    "git diff main -- docs/RUNBOOK.md --apply", "git grep -n 'sf apex run' -- docs",
                    "git blame -L 1,5 docs/RUNBOOK.md --apply", "git status --apply",
                    "  grep -c 'gh variable set SF_SYNC' CLAUDE.md"]
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

    def test_every_gh_api_write_asks_not_only_under_actions(self):
        for mode in ("default", "bypassPermissions", None):
            self.assert_silent(self.GH_API_READS, mode=mode)
        self.assert_silent(self.GH_API_READS, agent=True)
        with self.subTest("nothing logged for the reads"):
            self.assertEqual(self.logged(), {})
        before = self.logged()
        for command, run in self.runs(self.GH_API_WRITES):
            with self.subTest(command=command):
                self.assertEqual(self.verdict(run), "ask", self.show(run))
                self.check_reason(command, self.reason(run))
                self.assertIn("gh api", self.reason(run))               # the prompt says what it is
        with self.subTest("one ASKED per write"):
            self.assertEqual(self.logged()["ASKED"] - before["ASKED"], len(self.GH_API_WRITES))
        self.assert_denies(self.GH_API_WRITES, mode="dontAsk")
        self.assert_denies(self.GH_API_WRITES, agent=True)
        # a read with a harmless comment: passes or asks, never refused in the session
        before = self.logged()
        asked = 0
        for command, run in self.runs(self.GH_API_COMMENTED_READS):
            with self.subTest(command=command):
                self.assertIn(self.verdict(run), ("silent", "ask"), self.show(run))
                asked += self.verdict(run) == "ask"
        with self.subTest("only the asks are logged"):
            self.assertEqual(self.logged() - before, collections.Counter({"ASKED": asked}) if asked else collections.Counter())

    def test_a_hash_is_text_so_nothing_after_it_hides_a_write(self):
        # Ryan, 2026-10-14, after the review of 014d2ab: reading comments as bash does failed open
        # (no decision, and the old allow rule Bash(gh api repos/:*) then ran the PATCH); a # is
        # text everywhere, so the write after it is seen
        for command, run in self.runs(self.HASH_IS_TEXT):
            with self.subTest(command=command):
                self.assertEqual(self.verdict(run), "ask", self.show(run))
                self.check_reason(command, self.reason(run))
                self.assertIn("gh api", self.reason(run))
        with self.subTest("one ASKED per write"):
            self.assertEqual(self.logged(), {"ASKED": len(self.HASH_IS_TEXT)})
        for mode in ("dontAsk", "bypassPermissions", None):            # a dispatched run: refused
            self.assert_denies(self.HASH_IS_TEXT, mode=mode, saying=("interactive", "terminal"))
        self.assert_denies(self.HASH_IS_TEXT, agent=True, saying=("agent",))

    def test_the_gh_api_reader_runs_when_gh_and_api_survive_quote_removal(self):
        # the pre-filter (2026-10-14): a gh word AND the text api once quote and backslash
        # characters are removed. g""h, g\h, 'gh', =gh and a""pi are gh api and are read ...
        for command, run in self.runs(self.SPLIT_GH_WRITES):
            with self.subTest(command=command):
                self.assertEqual(self.verdict(run), "ask", self.show(run))
                self.check_reason(command, self.reason(run))
                self.assertIn("gh api", self.reason(run))
        with self.subTest("one ASKED per write"):
            self.assertEqual(self.logged(), {"ASKED": len(self.SPLIT_GH_WRITES)})
        self.assert_denies(self.SPLIT_GH_WRITES, mode="dontAsk", saying=("interactive", "terminal"))
        self.assert_denies(self.SPLIT_GH_WRITES, agent=True, saying=("agent",))
        # ... a split gh that only reads passes, and a gh command with no api in its text is never
        # read: a heredoc body's apostrophe asks nothing, here or in a dispatched run
        before = self.logged()
        for mode in ("default", "dontAsk", "bypassPermissions", "auto", None):
            self.assert_silent(self.SPLIT_GH_READS + self.GH_TEXT_SILENT, mode=mode)
        self.assert_silent(self.SPLIT_GH_READS + self.GH_TEXT_SILENT, agent=True)
        with self.subTest("nothing logged for the reads and the PR texts"):
            self.assertEqual(self.logged(), before)

    def test_a_gh_word_split_by_a_continued_line_is_still_gh(self):
        # g\<newline>h is the word gh to the shell (a backslash-newline is removed), as gh \<newline>
        # api already is; Bash(gh api:*) cannot see it, so the gate is the only layer
        commands = ["g\\\nh api -X POST repos/o/r/issues -f title=x",
                    "gh a\\\npi repos/o/r/labels -f name=x",
                    "g\\\nh \\\n  api -XDELETE repos/o/r/labels/x"]
        for command, run in self.runs(commands):
            with self.subTest(command=command):
                self.assertEqual(self.verdict(run), "ask", self.show(run))
                self.check_reason(command, self.reason(run))
        with self.subTest("one ASKED per write"):
            self.assertEqual(self.logged(), {"ASKED": len(commands)})
        self.assert_silent(["g\\\nh api repos/o/r/pulls/1/reviews"], mode="dontAsk")

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
        # CLAUDE.md: live writes never from a subagent; the main session asks Ryan. The input
        # says "subagent" with agent_id (any value) or agent_type (any name): either is enough
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
        for agent_type in ("Explore", "harness:coder", "general-purpose"):     # the type alone
            self.assert_denies(self.SAMPLE, agent_type=agent_type, saying=("agent",))
        runs += len(self.SAMPLE) * 3
        self.assertEqual(self.refused(), runs)
        self.assertNotIn("ASKED", self.logged())

    def test_the_gate_never_allows_and_never_stays_silent_on_a_live_command(self):
        # whatever the mode, the caller and the environment: Ryan's prompt or a refusal, logged
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
        read = dict(main, tool_input={"command": "grep -n -- '--apply' docs/RUNBOOK.md",
                                      "description": "Find --apply in the runbook"})
        run = self.run_hook("live_gate.sh", {}, raw=json.dumps(read))
        self.assertEqual(self.verdict(run), "silent", self.show(run))
        self.assertEqual(self.logged()["ASKED"], 1)
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


class GateSettings(unittest.TestCase):
    """.claude/settings.json, the second layer behind live_gate.sh: the rules read as Claude Code
    reads them (research on 2.1.299, 2026-10-14): Bash(x:*) is Bash(x *), which needs a word
    break after x - x alone or x, a space and anything (Bash(gh api repos/:*) never matched a real
    call, nor Bash(npm run clasp:*) npm run clasp:push); any other * stands for any text; a rule
    without * is the whole command. And the hook entries."""

    @classmethod
    def setUpClass(cls):
        with open(SETTINGS, encoding="utf-8") as f:
            cls.settings = json.load(f)
        cls.permissions = cls.settings["permissions"]

    @staticmethod
    def matches(rule, command):
        if not (rule.startswith("Bash(") and rule.endswith(")")):
            return rule == "Bash"
        body = rule[5:-1]
        if body.endswith(":*"):                                        # the legacy spelling of " *"
            body = body[:-2] + " *"
        if "*" not in body:
            return command == body
        if body.endswith(" *") and body.count("*") == 1 and command == body[:-2]:
            return True
        return re.fullmatch(".*".join(re.escape(part) for part in body.split("*")), command, re.S) is not None

    def covering(self, kind, command):
        return [rule for rule in self.permissions.get(kind, []) if self.matches(rule, command)]

    # the reads the harness loop once ran through gh api: it no longer runs gh api from Bash
    # (Ryan, 2026-10-14), so they ask like every other gh api command
    LOOP_READS = ["gh api --paginate repos/o/r/pulls/36/reviews", "gh api repos/o/r/pulls/36/reviews/7/comments",
                  "gh api repos/o/r/pulls/36/reviews"]
    GH_API_OTHERS = ["gh api graphql -f query='query { viewer { login } }'", "gh api user", "gh api",
                     "gh api -X DELETE repos/o/r/git/refs/heads/x", "gh api --method DELETE repos/o/r/labels/x",
                     "gh api -XPUT repos/o/r/pulls/1/merge", "gh api orgs/o/actions/variables -f name=x",
                     "gh api user/repos -f name=scratch", "gh api --paginate repos/o/r/issues",
                     "gh api -X PATCH repos/o/r/actions/variables/X -f value=true",
                     "gh api repos/o/r/actions/variables"]
    # what a session issues without a prompt: never behind an ask rule (gh pr and gh issue carry
    # the PR and issue bodies, heredocs included)
    PLAIN = ["gh pr view 36 --json state", "gh issue list", "gh run list", "gh variable list", "gh secret list",
             "gh pr create --title x --body-file -", "gh issue comment 36 --body x", "gh pr comment 41 --body x",
             "gh workflow list", "gh workflow view auto-sync.yml", "harness-board show 36 --markdown",
             "git status", "make check", "scripts/verify.sh", "python3 tools/auto_sync.py",
             "python3 sync_attendance_form.py roster.csv --roster --region Africa --form 1",
             "grep -n -- '--apply' docs/RUNBOOK.md", "sf org list",
             "sf data query -q 'SELECT Id FROM Account' -o glow", "sf project retrieve start -m ApexClass:GlowSync"]
    # the live families a prefix rule can name: the sync's switches on GitHub, the Apps Script
    # push, the Salesforce deploys, data writes and anonymous Apex. Not --apply, --prune,
    # --rehearse, api.jotform.com or apply=true: those sit anywhere in a command, and a rule like
    # Bash(*--apply*) would prompt on every grep of the docs (20 of 31 blocks by 2026-10-09)
    ASKED_FAMILIES = ["gh variable set SF_SYNC --body apply", "gh variable delete SF_SYNC",
                      "gh secret set JOTFORM_API_KEY", "gh secret delete GLOW_SA_JSON",
                      "gh workflow run auto-sync.yml -f apply=true", "gh workflow enable auto-sync.yml",
                      "gh workflow disable auto-sync.yml", "gh run rerun 1234",
                      "npx clasp push -f", "npm run clasp:push",
                      "sf project deploy start --source-dir force-app -o glow",
                      "sf apex run --file merge.apex -o glow",
                      "sf data create record -s Account -v \"Name='Sunrise Club'\" -o glow",
                      "sf data update record -s Account -i 001000000000001 -v \"Name=X\"",
                      "sf data delete record -s Contact -i 003000000000001",
                      "sf data upsert bulk -s Contact -f contacts.csv -i Id",
                      "sf data import tree -f accounts.json"]
    CLASP_PUSH = ["npm run clasp:push", "npm run clasp:push -- --force", "npx clasp push", "npx clasp push -f"]
    # as of 2026-10-14: what the ticket leaves alone (Bash(npm run clasp:*) may be replaced: it
    # never covered npm run clasp:push, see CLASP_PUSH)
    ASK_BEFORE = ["Read(./data/**)", "Read(./backups/**)", "Bash(git tag:*)",
                  "Bash(npx clasp:*)", "Bash(python3 tools/derive_partner_regions.py:*)",
                  "Bash(python3 test/fixtures/make_fixture.py --write)", "Bash(make fixtures)"]
    DENY_BEFORE = ["Read(./credentials/service-account.json)", "Read(./credentials/config.json)",
                   "Read(./.env)", "Read(./.env.local)", "Read(./.claude/settings.local.json)",
                   "Read(~/.clasprc.json)", "Read(~/.config/gcloud/**)"]
    ALLOW_KEPT = ["Bash(scripts/verify.sh)", "Bash(make check)", "Bash(make py)", "Bash(node test/:*)",
                  "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)", "Bash(python3 tools/form_status.py:*)",
                  "Bash(python3 backup_forms.py:*)", "Bash(python3 tools/sheets_client.py export:*)",
                  "Bash(harness-*:*)", "Bash(gh issue:*)", "Bash(gh pr:*)", "Bash(git worktree:*)",
                  "Bash(git fetch:*)", "Bash(git add:*)", "Bash(git commit:*)", "Bash(git push:*)"]

    def test_every_gh_api_command_asks_and_none_is_allowed(self):
        # Ryan, 2026-10-14 (reverses the ticket's first requirement, "no ask rule starts
        # Bash(gh api"): the harness no longer runs gh api from Bash, so every gh api command asks
        # through settings, the loop's reads included, and no allow rule names gh api. The rule
        # needs the space before the wildcard (Bash(gh api repos/:*) never matched a real call,
        # research on 2.1.299): Bash(gh api:*) or Bash(gh api *). It is denied in every
        # headless mode; the hook still asks on the shapes it misses (bash -c, eval, a full path,
        # a quoted subcommand word).
        allow, ask = self.permissions["allow"], self.permissions["ask"]
        self.assertTrue({"Bash(gh api:*)", "Bash(gh api *)"} & set(ask), f"no Bash(gh api:*) ask rule: {ask}")
        for rule in allow:
            self.assertFalse(rule.replace(" ", "").startswith("Bash(ghapi"), f"{rule}: an allow rule on gh api")
        for command in self.LOOP_READS + self.GH_API_OTHERS:
            with self.subTest(command=command):
                self.assertTrue(self.covering("ask", command), f"no ask rule for {command!r}")
                self.assertEqual(self.covering("allow", command), [], "allowed without a prompt")
        for command in ["gh -R o/r api repos/o/r/labels -f name=x", "gh --repo o/r api repos/o/r/pulls/1"]:
            with self.subTest(command=command):                         # nor does any rule allow it with -R
                self.assertEqual(self.covering("allow", command), [], "allowed without a prompt")
        for rule in self.ALLOW_KEPT:                                    # nothing else in the list changed
            self.assertIn(rule, allow)
        for rule in self.ASK_BEFORE:
            self.assertIn(rule, ask)

    def test_ask_rules_back_the_hook_for_the_live_families(self):
        # explicit ask rules prompt in every mode, bypassPermissions included: the layer under the hook
        for command in self.ASKED_FAMILIES + self.LOOP_READS:
            with self.subTest(command=command):
                self.assertTrue(self.covering("ask", command), f"no ask rule for {command!r}")
        # the Apps Script push, both ways it is spelt: Bash(npm run clasp:*) is "npm run clasp" and a
        # word break, so it never covered npm run clasp:push (orchestrator, 2026-10-14: fix it here)
        for command in self.CLASP_PUSH:
            with self.subTest(command=command):
                self.assertTrue(self.covering("ask", command), f"no ask rule for {command!r} (a word break "
                                                               f"is needed after a :* rule's prefix)")
        for command in self.PLAIN:
            with self.subTest(command=command):
                self.assertEqual(self.covering("ask", command), [], "a read would prompt")
        for rule in self.ASK_BEFORE:
            self.assertIn(rule, self.permissions["ask"])
        self.assertEqual(self.permissions["deny"], self.DENY_BEFORE)
        self.assertEqual(sorted(self.settings["env"]), ["CLAUDE_VERIFY_CMD", "HARNESS_TEST_CMD", "HARNESS_WORKTREE_SETUP"])

    def test_the_live_gate_still_runs_on_every_bash_command(self):
        pre = self.settings["hooks"]["PreToolUse"]
        gates = [h for entry in pre if entry.get("matcher") == "Bash" for h in entry["hooks"]
                 if h.get("type") == "command" and h.get("command", "").endswith("/.claude/hooks/live_gate.sh")]
        self.assertEqual(len(gates), 1, pre)
        self.assertEqual(gates[0].get("onFailure"), "block")            # a timed-out hook must not let a write through
        timeout = gates[0].get("timeout")
        self.assertIsInstance(timeout, int)
        self.assertNotIsInstance(timeout, bool)
        self.assertGreaterEqual(timeout, 1)
        edits = [h for entry in pre if entry.get("matcher") == "Edit|Write|MultiEdit" for h in entry["hooks"]]
        self.assertTrue(any(h.get("command", "").endswith("/.claude/hooks/protected_paths.sh") for h in edits), pre)
        post = [h for entry in self.settings["hooks"]["PostToolUse"] for h in entry["hooks"]]
        self.assertTrue(any(h.get("command", "").endswith("/.claude/hooks/secret_scan.sh") for h in post), post)


RUFF = shutil.which("ruff") or (os.path.join(REPO, ".venv", "bin", "ruff")
                                if os.access(os.path.join(REPO, ".venv", "bin", "ruff"), os.X_OK) else None)


@unittest.skipUnless(shutil.which("git") and RUFF and os.access(BASH, os.X_OK), "needs git, ruff and /bin/bash")
class PreCommit(unittest.TestCase):
    """.githooks/pre-commit run on a scratch repository's staged changes (it is installed per clone
    by `make hooks`; here it is called directly, as git would)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = self.tmp.name
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env["PATH"] = os.pathsep.join([os.path.dirname(RUFF), os.path.dirname(sys.executable),
                                            self.env.get("PATH", "")])
        os.makedirs(os.path.join(self.repo, "scripts"))
        shutil.copy(os.path.join(REPO, "scripts", "check_secrets.py"), os.path.join(self.repo, "scripts"))
        shutil.copy(os.path.join(REPO, "ruff.toml"), self.repo)
        self.write("tools/club.py", "def club(name):\n    return name.strip()\n")
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", "start")

    def git(self, *args):
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.org",
                        "-c", "core.hooksPath=/dev/null", *args], cwd=self.repo, env=self.env, check=True,
                       capture_output=True)

    def write(self, rel, text):
        os.makedirs(os.path.dirname(os.path.join(self.repo, rel)) or self.repo, exist_ok=True)
        with open(os.path.join(self.repo, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def hook(self):
        done = subprocess.run([os.path.join(REPO, ".githooks", "pre-commit")], cwd=self.repo, env=self.env,
                              capture_output=True, text=True, timeout=60)
        return done.returncode, done.stdout + done.stderr

    def test_a_renamed_and_edited_py_file_is_linted(self):
        # review of 2026-10-09: --diff-filter=AM dropped a renamed file (status R)
        self.git("mv", "tools/club.py", "tools/clubs.py")
        self.assertEqual(self.hook()[0], 0)                               # a plain rename
        self.write("tools/clubs.py", "import os\n\n\ndef club(name):\n    return name.strip()\n")
        self.git("add", "tools/clubs.py")
        code, out = self.hook()
        self.assertEqual(code, 1, out)
        self.assertIn("F401", out)

    def test_added_lines_are_scanned_and_lint_errors_refused(self):
        self.write("notes.md", "a clean line\n")
        self.git("add", "notes.md")
        self.assertEqual(self.hook()[0], 0)
        self.write("tools/new.py", "import sys\n")
        self.git("add", "tools/new.py")
        self.assertEqual(self.hook()[0], 1)
        self.git("rm", "-q", "--cached", "tools/new.py")
        fake = "ab" * 16                                                  # a 32-hex token, built here
        self.write("cfg.txt", f"token = {fake}\n")
        self.git("add", "cfg.txt")
        code, out = self.hook()
        self.assertEqual(code, 1, out)
        self.assertIn("32-hex token", out)
        self.git("commit", "-q", "--no-verify", "-m", "slipped in")
        self.git("rm", "-q", "cfg.txt")
        self.assertEqual(self.hook()[0], 0)                              # removing it is fine

    def test_a_column_0_decorator_is_not_read_as_an_e_mail_address(self):
        # review of 2026-10-09: the diff's "+" marker went into the scan, and with it a decorator at
        # column 0 matched the e-mail rule (whose local part takes "+"), refusing a clean commit
        self.write("tools/cached.py", "\n".join(["import functools", "", "",
                                                 "@functools.lru_cache(maxsize=64)",
                                                 "def club(name):", "    return name.strip()", ""]))
        self.git("add", "tools/cached.py")
        code, out = self.hook()
        self.assertEqual(code, 0, out)
        address = "mentor" + "@" + "school.test"                         # built here, as above
        self.write("notes.md", f"{address}\n")                           # still caught at column 0
        self.git("add", "notes.md")
        code, out = self.hook()
        self.assertEqual(code, 1, out)
        self.assertIn("e-mail address", out)


if __name__ == "__main__":
    unittest.main(verbosity=1)
