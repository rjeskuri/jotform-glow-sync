"""
What the guardrail hook tests share (test/hooks_test.py and test/hooks_*_test.py, one file per part
of the hooks, each under the 180 s a module may take alone): the Claude Code guardrail hooks, run as
Claude Code runs them: the tool input as JSON on standard input, the decision in the exit code and
on standard output (0 and nothing: no decision; 0 and an ask JSON: Ryan is asked in the session; 2,
or a deny JSON: refused).

The hooks are read from $GLOW_HOOKS_DIR (default .claude/hooks) and the settings from
$GLOW_SETTINGS_FILE, else $GLOW_SETTINGS_JSON (default .claude/settings.json), a relative path
taken from the directory the suite starts in: no agent may edit .claude/, so a candidate staged
elsewhere is proven here before Ryan applies it by hand. HOOKS and SETTINGS below are the one place
the tests read them.
CLAUDE_PROJECT_DIR is a temporary folder, so the gate's log never lands in the repository, and
GLOW_LIVE_OK is removed from the environment unless a test sets it. An `osascript` stub stands
first on the hook's PATH, so no test posts a real notification: it appends its argv to a file.

  - HookFixture, the mixin a hook test borrows (class X(HookFixture, unittest.TestCase)): a
    temporary project and the osascript stub per test, run_hook() and gate(), what Claude Code
    makes of an answer (verdict, reason, the prompt's text), the gate's log, the batch runner
    (sixteen hooks at a time) and the assertions every part uses; the live commands, reads and
    self-approvals more than one part walks; and since #146 the backups - fictional form ids,
    projects with backup records, a Salesforce plan's before/, the notifications;
  - needs_bash: the skip of a test class when there is no /bin/bash to run the hooks with.
"""
import collections
import concurrent.futures
import datetime
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import REPO

# absolute, from the directory the suite starts in: each hook runs with the temporary project as its
# working directory, where a relative GLOW_HOOKS_DIR (.guardrails/hooks) would name nothing
HOOKS = os.path.abspath(os.environ.get("GLOW_HOOKS_DIR") or os.path.join(REPO, ".claude", "hooks"))
SETTINGS = os.path.abspath(os.environ.get("GLOW_SETTINGS_FILE") or os.environ.get("GLOW_SETTINGS_JSON")
                           or os.path.join(REPO, ".claude", "settings.json"))
BASH = "/bin/bash"                  # the hooks' shebang
needs_bash = unittest.skipUnless(os.access(BASH, os.X_OK), "no /bin/bash to run the hooks with")

# the permission modes Claude Code puts in the hook's input: in exactly these four, spelt exactly
# so, a prompt can reach Ryan; in the other two, with the field missing (None), and with any
# other spelling (Manual arrives as "default", never "manual") nobody can answer one
ASK_MODES = ["default", "acceptEdits", "auto", "plan"]
NO_PROMPT_MODES = ["bypassPermissions", "dontAsk", None]
UNKNOWN_MODES = ["yolo", "foo", "", "Default", "DEFAULT", "acceptEdits ", "default\n", " plan", "auto\t",
                 "default auto", "bypasspermissions", "manual", "ask"]

Run = collections.namedtuple("Run", "code out err")


def nest(command, depth):
    """The command run through `bash -c` depth times, each level quoted as the shell needs it."""
    for _ in range(depth):
        command = "bash -c " + shlex.quote(command)
    return command


class HookFixture:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.tmp.name, ".claude"))
        self.log = os.path.join(self.tmp.name, ".claude", "live_gate.log")
        # the notification's stand-in: first on the hook's PATH, it appends its argv (JSON, one
        # line per call) to self.calls; with self.slow present it first sleeps 8 s (a hung osascript)
        self.side = tempfile.TemporaryDirectory()
        self.bin = os.path.join(self.side.name, "bin")
        os.makedirs(self.bin)
        self.calls = os.path.join(self.side.name, "osascript.calls")
        self.slow = os.path.join(self.side.name, "slow")
        record = 'import json, sys\nwith open(sys.argv[1], "a", encoding="utf-8") as f:\n    f.write(json.dumps(sys.argv[2:]) + "\\n")\n'
        with open(os.path.join(self.bin, "osascript"), "w", encoding="utf-8") as f:
            f.write(f"#!/bin/sh\n[ -f {shlex.quote(self.slow)} ] && sleep 8\n"
                    f"exec {shlex.quote(sys.executable)} -c {shlex.quote(record)} {shlex.quote(self.calls)} \"$@\"\n")
        os.chmod(os.path.join(self.bin, "osascript"), 0o755)

    def tearDown(self):
        self.tmp.cleanup()
        self.side.cleanup()

    # run_hook's cwd that leaves the input's cwd field out
    NO_CWD = object()

    def run_hook(self, name, tool_input, live_ok=None, tool="Bash", project=None, mode="default", agent=None,
                 agent_type=None, extra=None, raw=None, cwd=None):
        """The hook on one tool call: exit code, stdout, stderr. `mode` is the input's
        permission_mode (None leaves it out); `agent` an agent_id (True: a fresh one, with an
        agent_type), `agent_type` that field alone; `cwd` the input's cwd - the Bash tool's working
        folder (default: the project; NO_CWD leaves the field out) - while the hook itself always
        runs in the project; `extra` fields are set last (a null, a number); `raw` replaces the
        whole of stdin."""
        env = {k: v for k, v in os.environ.items() if k != "GLOW_LIVE_OK" and not k.startswith("GIT_")}
        env["PATH"] = self.bin + os.pathsep + env.get("PATH", "/usr/bin:/bin")
        env["CLAUDE_PROJECT_DIR"] = project or self.tmp.name
        if live_ok is not None:
            env["GLOW_LIVE_OK"] = live_ok
        data = self.pretooluse(tool, tool_input, cwd if isinstance(cwd, str) else env["CLAUDE_PROJECT_DIR"], mode)
        if cwd is self.NO_CWD:
            del data["cwd"]
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

    def gate(self, command, live_ok=None, mode="default", may_allow=False, **kw):
        run = self.run_hook("live_gate.sh", {"command": command, "description": "Run one command for the test"},
                            live_ok, mode=mode, **kw)
        # the answer Claude Code runs a live command on without Ryan's prompt: only a backed write
        # may get it (may_allow). Without a backup from today, for a delete or --prune, a chained
        # command, a self-approval, in plan mode or an unknown one, never
        if not may_allow:
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
        self.assertNotIn("ALLOWED", counts, "the gate logged an ALLOWED with no backup on record")
        return counts["BLOCKED"] + counts["DENIED"]

    @staticmethod
    def all_of(fn, items):
        """fn over items, sixteen hooks at a time (each is a few short processes, mostly waiting on
        process start-up), results in order."""
        with concurrent.futures.ThreadPoolExecutor(16) as pool:
            return list(pool.map(fn, items))

    def runs(self, commands, **kw):
        return list(zip(commands, self.all_of(lambda c: self.gate(c, **kw), commands)))

    def verdicts(self, cases):
        """[(command, kw, run)] of the gate on each (command, kw) - every case in one batch, so a
        test that walks commands, modes and callers waits once, not once per mode."""
        return [(command, kw, run) for (command, kw), run
                in zip(cases, self.all_of(lambda case: self.gate(case[0], **case[1]), cases))]

    def assert_never_automatic(self, commands, project, saying=(), light=False):
        """Each command, in `project`: asked in a main session that can show the prompt (default,
        auto - the reason as check_reason reads it), refused where none can (dontAsk,
        bypassPermissions, a missing mode, a subagent in auto) - never allowed, in one batch. A
        command may come as (command, {more of gate's keywords}): its cwd, an extra field. light:
        default, dontAsk and a subagent only."""
        callers = ([{"mode": "default"}, {"mode": "auto"}] + [{"mode": m} for m in self.HEADLESS]
                   + [{"mode": "auto", "agent": True}])
        if light:
            callers = [{"mode": "default"}, {"mode": "dontAsk"}, {"mode": "auto", "agent": True}]
        cases = [(command, dict(caller, project=project, **more))
                 for command, more in ((c, {}) if isinstance(c, str) else c for c in commands) for caller in callers]
        for command, kw, run in self.verdicts(cases):
            with self.subTest(command=command, mode=kw["mode"], agent=kw.get("agent"),
                              cwd=kw.get("cwd"), extra=kw.get("extra")):
                if kw["mode"] in self.HEADLESS or kw.get("agent"):
                    self.assertEqual(self.verdict(run), "deny", self.show(run))
                    message = (run.err + self.reason(run)).lower()
                    if saying:
                        self.assertTrue(any(s in message for s in saying), f"none of {saying} in the message: {message!r}")
                else:
                    self.assertEqual(self.verdict(run), "ask", self.show(run))
                    self.check_reason(command, self.reason(run))

    def check_reason(self, command, reason):
        """The prompt's text: the matched text, the command, why, and where to read more."""
        flat = command.replace("\r", " ").replace("\n", " ")
        shown = reason.replace("\r", " ").replace("\n", " ")
        matched = re.search(r'matched "(.+?)"', reason)
        self.assertIsNotNone(matched, f"no matched \"...\" in the reason: {reason!r}")
        # the matched text is the command's own - as written or with its quote and backslash
        # characters removed, in any case (gh "variable" set, GH variable set) - except for the
        # gh/sf api rules, whose match may be a description, and only when the command holds a
        # gh or sf word and api
        # (and with a backslash-newline joined, as the shell joins it: --ap\<newline>ply is --apply)
        joined = command.replace("\\\r\n", "").replace("\\\n", "").replace("\r", " ").replace("\n", " ")
        bare = re.sub(r"""["'\\]""", "", flat)
        joined_bare = re.sub(r"""["'\\]""", "", joined)
        texts = [t.lower() for t in (flat, bare, joined, joined_bare)]
        found = matched.group(1).lower()
        api_cli = (re.search(r"(^|[^\w.-])(gh|sf|sfdx)([^\w.-]|$)", joined_bare, re.I) and "api" in joined_bare.lower())
        self.assertTrue(any(found in t for t in texts) or (api_cli and found.startswith(("gh api", "sf api"))),
                        f"the matched text {matched.group(1)!r} is not in the command {flat!r}")
        if command in self.TRIGGERS:
            self.assertIn(self.TRIGGERS[command], reason, f"the reason does not name the family's trigger: {reason!r}")
        self.assertTrue(flat[:20] in shown or joined[:20] in shown, f"the reason does not name the command: {reason!r}")
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
        # Salesforce: a deploy, data writes, anonymous Apex, the rehearsal (a check-only deploy - --dry-run,
        # validate - passes since #204: test_a_check_only_deploy_or_a_query_passes_...; a quick deploy of
        # a validated job is a deploy)
        "sf project deploy start --source-dir force-app -o glow",
        "sf project deploy quick --job-id 0Af000000000001 -o glow",
        "sf data create record -s Account -v \"Name='Sunrise Club'\" -o glow",
        "sf data update record -s Account -i 001000000000001 -v \"Name=X\"",
        "sf data delete record -s Contact -i 003000000000001",
        "sf data upsert bulk -s Contact -f contacts.csv -i Id",
        "sf data import tree -f accounts.json",
        "sf apex run --file merge.apex -o glow",
        "/opt/homebrew/bin/sf apex run -f merge.apex",
        # (2026-10-26, #146: the tools/sf_*.py on SF_LISTED write their own rollback record before
        # each write and are automatic - test_a_listed_salesforce_tool_goes_through_on_its_own_...
        # - so the --rehearse family is sampled here on a tool no list names, and sf_dupes.py by its
        # --apply, a delete: its merge deletes the losing contact)
        "python3 tools/sf_rehearsal_example.py merge --plan data/plan.json --rehearse",
        "python3 tools/sf_dupes.py merge --plan data/plan.json --apply",
        # ... and the other spellings of the same writes (review of 2026-10-09)
        "sfdx apex run -f merge.apex -o glow", "sfdx project deploy start -d force-app",
        "sf force:apex:execute -f merge.apex", "sfdx force:apex:execute -f merge.apex -u glow",
        "sfdx force:source:deploy -p force-app", "sfdx force:source:push", "sfdx force:source:delete -m ApexClass:X",
        "sfdx force:mdapi:deploy -d mdapi", "sfdx force:data:record:update -s Account -i 001x -v Name=X",
        "sfdx force:data:bulk:upsert -s Contact -f c.csv -i Id", "sfdx force:data:tree:import -f a.json",
        "sf deploy metadata -d force-app", "sf project delete source -m ApexClass:GlowSync",
        "curl -X PATCH https://example.my.salesforce.com/services/data/v60.0/sobjects/Account/001x -d @a.json",
        "curl https://login.salesforce.com/services/oauth2/token -d grant_type=client_credentials",
        "python3 -m sf_dupes merge --apply", "cd tools && python3 sf_dupes.py merge --rehearse",
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
              "gh api -X PATCH repos/o/r/actions/variables/SF_SYNC -f value=apply",
              "sf project deploy start --source-dir force-app -o glow",
              "python3 tools/sf_rehearsal_example.py merge --plan data/plan.json --rehearse"]
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
        "python3 tools/sf_rehearsal_example.py merge --plan data/plan.json --rehearse": "--rehearse",
        "python3 tools/sf_dupes.py merge --plan data/plan.json --apply": "--apply",
        "sfdx force:source:deploy -p force-app": "force:source:deploy",
        "sf deploy metadata -d force-app": "sf deploy metadata",
        "curl -X PATCH https://example.my.salesforce.com/services/data/v60.0/sobjects/Account/001x -d @a.json":
            ".salesforce.com/services/",
        "sf api request rest '/services/data/v60.0/sobjects/Account/001x' -X PATCH --body '{}'": "sf api request rest",
        "sf api request graphql --body '{\"query\": \"mutation { x }\"}'": "sf api request graphql",
        # matched with quotes removed, in any case
        "gh 'workflow' run auto-sync.yml -f apply=true": "workflow run",
        "gh \"variable\" set SF_SYNC --body apply": "variable set", "GH variable set X --body 1": "variable set",
        "SF data delete record -s Contact -i 003000000000001": "data delete",
        "python3 sync_attendance_form.py x --ap\"\"ply": "--apply",
        # matched with a backslash-newline joined
        "python3 sync_attendance_form.py x --ap\\\nply": "--apply", "gh vari\\\nable set X --body 1": "variable set",
        "sf apex r\\\nun -f merge.apex": "apex run",
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
             # (gh api reads of actions/ moved to GH_API_LIVE, 2026-10-14: they ask, whatever the method)
             # the gh api rule needs all three: a gh word, api, and actions/, dispatches or graphql
             "ls .github/actions/ && make check", "curl -s https://example.com/api/graphql -o out.json",
             "gh run list --json name,url | grep actions/", "gh pr list --search graphql",
             "gh workflow run auto-sync.yml", "gh workflow run auto-sync.yml -f apply=false",
             # (sf data query: no decision until #204, an allow since - test_a_check_only_deploy_or_a_query_...)
             "sf org list",
             "sf project deploy report --job-id 0Af000000000001", "sfdx force:org:list",
             "sf project deploy preview --source-dir force-app -o glow",
             "sf project retrieve start -m ApexClass:GlowSync", "sfdx force:data:soql:query -q 'SELECT Id FROM Account'",
             "sf api request rest '/services/data/v60.0/query?q=SELECT+Id+FROM+Account' -o glow",
             "sf api request rest /services/data/v60.0/limits", "sf api request rest /services/data/v60.0/ -X GET",
             "sf api request rest /services/data/v60.0/ --stream-to-file out.txt --include",
             "python3 tools/sf_dupes.py check",
             # the startup files read, or a copy of one written
             "cat ~/.zshrc", "grep -n PATH ~/.zshrc", "tail -5 ~/.bash_profile", "ls -la ~/.zshrc",
             "wc -l .envrc", "cp ~/.zshrc ~/.zshrc.bak", "echo x > ~/.zshrc.bak", "source .env",
             "python3 tools/sf_dupes.py plan", "git status"]
    # 20 of the 31 blocks logged by 2026-10-09 were these: grep, git, cat on the docs
    MENTIONS = ["grep -n -- '--apply' docs/RUNBOOK.md",
                "grep -rn 'GLOW_LIVE_OK=' docs .claude",
                "rg -n -- '--apply-salesforce' docs tools",
                "cat docs/plans/2026-10-06-sf-new-club-accounts.md --apply",
                "head -50 docs/RUNBOOK.md --prune", "tail -n 5 .claude/live_gate.log --apply",
                "wc -l --apply", "ls --apply",
                "git log --oneline --grep=--apply", "git show HEAD -- '*--apply*'",
                "git diff main -- docs/RUNBOOK.md --apply", "git grep -n 'sf apex run' -- docs",
                "git blame -L 1,5 docs/RUNBOOK.md --apply", "git status --apply",
                "  grep -c 'gh variable set SF_SYNC' CLAUDE.md",
                "grep -n \"gh api repos/o/r/actions/variables\" docs/RUNBOOK.md"]

    # ---- live_gate.sh: the automatic go for a backed write (ticket #146, Ryan 2026-10-26)
    F1, F2, F3 = "261234567890123", "262345678901234", "263456789012345"     # fictional form ids
    # a backed write is allowed to a main session in these modes (None: the field missing) ...
    ALLOW_MODES = ["default", "acceptEdits", "auto", "dontAsk", "bypassPermissions", None]
    # ... and to a subagent, in its session's mode
    AGENT_MODES = ["auto", "dontAsk", None]
    HEADLESS = ["dontAsk", "bypassPermissions", None]
    TITLE = "GLOW live write auto-approved"
    # the notification's AppleScript: fixed text, the title and message only ever its argv
    SCRIPTS = ["on run argv", "display notification (item 2 of argv) with title (item 1 of argv)", "end run"]
    ALLOWED = re.compile(r"^mode=(?P<mode>\S*)(?P<agent> agent)? target=(?P<target>\S+) backup=(?P<rest>.*)$", re.S)

    def jotform_write(self, form_id=None):
        return ("python3 sync_attendance_form.py data/roster.csv --roster --region Africa "
                f"--form {form_id or self.F1} --apply")

    @staticmethod
    def write(folder, rel, text):
        full = os.path.join(folder, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(text)
        return full

    @staticmethod
    def git(project, *args):
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        return subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.org",
                               "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *args],
                              cwd=project, env=env, check=True, capture_output=True, text=True).stdout

    def project(self, git=False, appsscript=True):
        """A fresh CLAUDE_PROJECT_DIR with .claude/ and no backup. With git: a repository whose
        README and (unless appsscript is False) appsscript/ are committed - a clean Apps Script."""
        path = tempfile.mkdtemp(dir=self.tmp.name)
        os.makedirs(os.path.join(path, ".claude"))
        if git:
            if not shutil.which("git"):
                self.skipTest("needs git")
            if appsscript:
                self.write(path, "appsscript/Code.gs", "function onEdit(e) {}\n")
                self.write(path, "appsscript/appsscript.json", '{"timeZone": "Etc/UTC"}\n')
            self.write(path, "README.md", "A fictional checkout.\n")
            self.git(path, "init", "-q")
            self.git(path, "add", "-A")
            self.git(path, "commit", "-q", "-m", "start")
        return path

    def head(self, project):
        return self.git(project, "rev-parse", "HEAD").strip()

    def back_up(self, project, target, ident, path, day=None, make=True):
        """A backup record as glow/live_backups.py writes it - `<date time>\\t<target>\\t<id>\\t<path>`
        appended to <project>/.claude/live_backups.log - and, with make, the backup it names (a
        file when the path has an extension, else a folder with a file in it). `day` dates the
        record (default: now); a past day gets its last second, a future one its first: the
        nearest a record can be to today without being from today."""
        if day is None:
            when = datetime.datetime.now()
        elif day < datetime.date.today():
            when = datetime.datetime.combine(day, datetime.time(23, 59, 59))
        else:
            when = datetime.datetime.combine(day, datetime.time(0, 0, 0))
        with open(os.path.join(project, ".claude", "live_backups.log"), "a", encoding="utf-8") as f:
            f.write(f"{when:%Y-%m-%d %H:%M:%S}\t{target}\t{ident}\t{path}\n")
        if make:
            if os.path.splitext(path)[1]:
                self.write(project, path, "{}\n")
            else:
                self.write(os.path.join(project, path), "questions-latest.json", "{}\n")

    def salesforce_before(self, project, rel, day=None):
        """A file of a plan's before/ retrieve (data/sf_<topic>/before/...): modified now, or at noon
        of `day`. Its folders stay modified now - only a file's own date counts."""
        full = self.write(project, rel, "<Report/>\n")
        if day is not None:
            t = datetime.datetime.combine(day, datetime.time(12, 0)).timestamp()
            os.utime(full, (t, t))
        return full

    def fully_backed(self):
        """A project with every backup there is, from today: jotform all and each fictional form,
        sheet all and the Roster tab, github all, data/sf_x/before/ (beside data/sf_x/after/), and a
        clean committed appsscript/."""
        p = self.project(git=True)
        for target, ident, path in [("jotform", "all", "backups"), ("jotform", self.F1, f"backups/{self.F1}"),
                                    ("jotform", self.F2, f"backups/{self.F2}"), ("jotform", self.F3, f"backups/{self.F3}"),
                                    ("sheet", "all", "data/sheet"), ("sheet", "Roster", "data/sheet/Roster.csv"),
                                    ("github", "all", "backups/github/switches-2026-10-26T090000.json")]:
            self.back_up(p, target, ident, path)
        self.salesforce_before(p, "data/sf_x/before/Attendance.report-meta.xml")
        self.write(p, "data/sf_x/after/Attendance.report-meta.xml", "<Report/>\n")
        return p

    def lines_of(self, project):
        """[(decision, the rest of the line)] of a project's .claude/live_gate.log."""
        path = os.path.join(project, ".claude", "live_gate.log")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            return self.LINE.findall(f.read())

    def osascript_calls(self):
        """Each osascript call's argv, in the order they ended (complete lines only)."""
        if not os.path.exists(self.calls):
            return []
        with open(self.calls, encoding="utf-8") as f:
            return [json.loads(line) for line in f.read().split("\n")[:-1] if line.strip()]

    def notifications(self, expect, wait=15.0):
        """The osascript calls, once `expect` have arrived or `wait` s have passed: the gate runs it
        detached, so a call may land after the hook has answered."""
        deadline = time.monotonic() + wait
        while True:
            calls = self.osascript_calls()
            if len(calls) >= expect or time.monotonic() > deadline:
                return calls
            time.sleep(0.05)

    def quiet_notifications(self):
        """The osascript calls after a second's wait, for a test that expects none (or no more)."""
        time.sleep(1.0)
        return self.osascript_calls()

    @staticmethod
    def split_osascript(argv):
        """(the -e scripts, the other arguments in order) of one osascript call."""
        scripts, args, items = [], [], iter(argv)
        for item in items:
            if item == "-e":
                scripts.append(next(items, None))
            else:
                args.append(item)
        return scripts, args

    def assert_backed(self, project):
        """The control of a test whose point needs real backups: a write they cover is allowed
        here (one ALLOWED line, one notification)."""
        run = self.gate(self.jotform_write(), mode="dontAsk", project=project, may_allow=True)
        self.assertEqual(self.verdict(run), "allow", "the control: this project's backups back no write - " + self.show(run))

    def sf_plan(self, files=None):
        """A project of its own whose plan folder data/sf_x/ holds a before/ retrieve from today, and
        `files` ({path: text})."""
        p = self.project()
        self.salesforce_before(p, "data/sf_x/before/Contact.object-meta.xml")
        for rel, text in (files or {}).items():
            self.write(p, rel, text)
        return p

    # anonymous Apex that writes and deletes nothing (2026-10-26, F1 of PR #154's review: the gate
    # reads the file `sf apex run --file` names); a field named IsDeleted holds no word delete
    APEX_UPDATES = [
        "List<Contact> cs = [SELECT Id, FirstName FROM Contact WHERE Club__c = 'Sunrise Club'];\n"
        "for (Contact c : cs) { c.FirstName = c.FirstName.trim(); }\nupdate cs;\n",
        "Account a = [SELECT Id, Name FROM Account WHERE IsDeleted = false AND Name = 'Rising Stars' LIMIT 1];\n"
        "a.Name = 'Rising Stars Club';\nDatabase.update(a);\n",
    ]

    def assert_refused_never_asked(self, commands):
        """Each command refused in a project with no backups - in default, auto, plan, dontAsk, a
        missing mode and from a subagent - never asked; one refusal logged per call."""
        callers = [{"mode": m} for m in ("default", "auto", "plan", "dontAsk", None)] + [{"mode": "auto", "agent": True}]
        cases = [(command, dict(caller)) for command in commands for caller in callers]
        before = self.logged()
        for command, kw, run in self.verdicts(cases):
            with self.subTest(command=command, mode=kw["mode"], agent=kw.get("agent")):
                self.assertEqual(self.verdict(run), "deny", self.show(run))
        after = self.logged()
        self.assertEqual(after["ASKED"], before["ASKED"], "a self-approval was asked")
        self.assertEqual(self.refused(), before["BLOCKED"] + before["DENIED"] + len(cases))

    def assert_no_decision(self, commands):
        """Each command passes with no decision - default, dontAsk, a missing mode, a subagent - and
        nothing is logged."""
        callers = [{"mode": "default"}, {"mode": "dontAsk"}, {"mode": None}, {"mode": "auto", "agent": True}]
        cases = [(command, dict(caller)) for command in commands for caller in callers]
        before = self.logged()
        for command, kw, run in self.verdicts(cases):
            with self.subTest(command=command, mode=kw["mode"], agent=kw.get("agent")):
                self.assertEqual(self.verdict(run), "silent", self.show(run))
        self.assertEqual(self.logged(), before, "nothing live: nothing logged")

    def assert_delete_class(self, cases):
        """Each (label, command, project): asked in default and auto, refused in dontAsk,
        bypassPermissions, a missing mode and from a subagent - never allowed, the plan's before/
        from today notwithstanding - and the message calls it a delete."""
        callers = ([{"mode": "default"}, {"mode": "auto"}] + [{"mode": m} for m in self.HEADLESS]
                   + [{"mode": "auto", "agent": True}])
        labels = {}
        runs = []
        for label, command, p in cases:
            labels[p] = label
            runs += [(command, dict(caller, project=p)) for caller in callers]
        for command, kw, run in self.verdicts(runs):
            with self.subTest(case=labels[kw["project"]], command=command, mode=kw["mode"], agent=kw.get("agent")):
                expected = "deny" if kw["mode"] in self.HEADLESS or kw.get("agent") else "ask"
                self.assertEqual(self.verdict(run), expected, self.show(run))
                if expected == "ask":
                    self.check_reason(command, self.reason(run))
                self.assertIn("delet", (run.err + self.reason(run)).lower(), "the message does not call it a delete")
