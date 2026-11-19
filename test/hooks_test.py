#!/usr/bin/env python3
"""
The Claude Code guardrail hooks, run as Claude Code runs them: the tool input as JSON on
standard input, the decision in the exit code and on standard output (0 and nothing: no
decision; 0 and an ask JSON: Ryan is asked in the session; 2, or a deny JSON: refused).

  - .claude/hooks/live_gate.sh (Bash), since 2026-10-26 (ticket #146): a live WRITE whose backup
    from today is on record goes through with no prompt - an "allow" - in default, acceptEdits,
    auto, dontAsk, bypassPermissions and a missing mode, from a subagent too; it is logged ALLOWED
    (mode, target, backup) and notified (osascript, the command only ever an argument, run
    detached). The backups: a `<date time>\t<target>\t<id>\t<path>` line in
    .claude/live_backups.log (glow/live_backups.py) from today - its first field - whose path still
    exists inside the project without climbing out of it - `jotform <form id>|all` (a form id is
    one after --form or in an API path /form/<id>; FORM_TOOLS lists the tools that write forms),
    `sheet <Tab>|all`, `github all` -, a clean committed appsscript/ for clasp push, a
    data/sf_<topic>/before/ file modified today for a raw sf write naming that folder, and for
    the Salesforce tools on SF_LISTED their own ledger or rollback file, written before each write.
    Without one the write asks Ryan in the session, and is refused - with the reason and the
    backup command - where no prompt can show (bypassPermissions, dontAsk, missing or unknown
    mode, a subagent). Never automatic: plan mode, an unknown mode, a chained command (a # too), one
    whose first word is no allowed launcher (python3 by its name or any path ending /python3, node,
    npm, npx, sf, sfdx, gh, curl, clasp - never env, sudo, nohup, time, exec, command, xargs, a
    shell's -c or a VAR=value), a tool no pinned list names by its exact file name (FORM_TOOLS,
    SF_LISTED, sheets_client.py import; auto_sync.py with --apply-salesforce), and the DELETES
    (`--prune`, delete/remove/destructive in any case and position, sf_dupes.py --apply), which ask
    or are refused as before whatever the backups. A command that approves itself (GLOW_LIVE_OK, a
    startup file, .claude/live_backups.log written, copied, touched or recorded by hand in any
    spelling, a Salesforce plan's before/ written by hand) is refused outright. A read-only command that only mentions a live
    flag passes, a chained one does not. "Prompt, don't parse" (Ryan, 2026-10-14): the command is matched as
    text - as written and with quote and backslash characters removed, in any case - never read
    as shell words. A gh api call is live when the command holds a gh word, api, and actions/,
    dispatches or graphql anywhere, whatever the method; every other gh api call is ungated.
    After review 1 of PR #154: `sf|sfdx apex run` is automatic only on a --file inside the checkout
    that the gate reads - holding delete, merge, undelete or emptyRecycleBin it is a delete, with no
    readable file it is not automatic; a --metadata-dir deploy never is, and a deploy of a folder
    holding a destructiveChanges*.xml is a delete; clasp push is automatic only from the input's cwd
    <project>/appsscript (npm run clasp:push from <project>), never with -P, --project or --rootDir;
    a redirect writes the backup records only when they are its target, and a query or export saved
    into a before/ is no forgery. After review 2: a Salesforce request whose request, body, headers
    or flags come from a file or standard input (sf api request rest --file, --body @file or -,
    --flags-dir, graphql --body <file>, curl -d @file, -H @file, -T, < file, a python3 -c snippet)
    is never automatic, nor is any curl with a config file (-K, --config), whatever the host.
    Ryan, 2026-11-06 (PR #154's questions): a write to ~/.curlrc or $CURL_HOME/.curlrc is a
    self-approval, refused in every mode; every curl -K/--config is live - asked, or refused where
    no prompt can show - even naming no live host; sfdx force:source:push is never automatic, and
    sf project deploy start only with an explicit -d/--source-dir, -m/--metadata or -x/--manifest.
    Ticket #204 (Ryan, 2026-11-04: no prompt unless it is destructive): what changes nothing live
    passes with no prompt and no backup - an "allow" in every mode a backed write is allowed in,
    from a subagent too, never in plan mode or an unknown mode (plan is not refused): a dashboard
    refresh (sf|sfdx api request rest on /services/data/vNN.N/analytics/dashboards/<id>, PUT with
    no body or an empty {} one) and a GET of the dashboard or its /status; a check-only deploy
    (sf project deploy start --dry-run, sf project deploy validate); a SOQL query (sf data query).
    Each only as one command beginning so - no chain, pipe, substitution, line break, wrapper or
    VAR=value - that writes neither the backup records nor a startup file. Anything else is judged
    as before: another body (a filter too), method, path (.., an encoded /, a ?_HttpMethod) or
    method-override header, a second body, method or URL, a request, body or flags from a file or
    standard input, a curl, a chain, a pipe, a wrapper, a quick deploy, destructive changes or a
    --metadata-dir beside --dry-run, a query that carries a live flag, a live command whose text
    only mentions one of these; anonymous Apex stays as #146 left it (the gate cannot tell a dry
    run from its file);
  - .claude/settings.json: the permission rules behind the hook (gh api allowed and never asked:
    an ask would stall the harness's resume reads; no ask rule on an automatic family or a #204
    pass - a hook's allow does not get past one -, ask rules kept on the deletes; the Read ask
    rules only on the personal-data exports in data/ and on backups/, never on a Salesforce plan's
    before/, build/ or after/ (Ryan's ruling, 2026-11-05), and HARNESS_SENSITIVE_PATHS marking the
    same; the hook entry that blocks on failure);
  - .claude/hooks/protected_paths.sh (Edit|Write|MultiEdit): data/, backups/, credentials/,
    .env, the generated Regions.gs, the backup records and the guardrails themselves are refused
    in every copy of the repository (main checkout, worktree, sibling checkout) and for a
    relative path;
  - .githooks/pre-commit, in a scratch repository: the lines a commit adds are scanned for
    secrets, and ruff checks every added, changed or renamed .py file as staged.

The hooks are read from $GLOW_HOOKS_DIR (default .claude/hooks) and the settings from
$GLOW_SETTINGS_FILE, else $GLOW_SETTINGS_JSON (default .claude/settings.json), a relative path
taken from the directory the suite starts in: no agent may edit .claude/, so a candidate staged
elsewhere is proven here before Ryan applies it by hand.
CLAUDE_PROJECT_DIR is a temporary folder, so the gate's log never lands in the repository, and
GLOW_LIVE_OK is removed from the environment unless a test sets it. An `osascript` stub stands
first on the hook's PATH, so no test posts a real notification: it appends its argv to a file.
"""
import collections
import concurrent.futures
import datetime
import fnmatch
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


@unittest.skipUnless(os.access(BASH, os.X_OK), "no /bin/bash to run the hooks with")
class Hooks(unittest.TestCase):
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
    # gh api, "prompt, don't parse" (Ryan, 2026-10-14). The read/write reader of 9794ffe..a2cf749
    # is withdrawn: four reviews found it failing open on each gap between it and the shell. A
    # gh word - any case, a path ending /gh, =gh, split by quotes or a backslash - and api, and
    # actions/, dispatches or graphql anywhere in the command: live whatever the method, GETs too
    GH_API_LIVE = [
        # the method does not count: reads of the Actions API, of dispatches and graphql ask too
        "gh api repos/o/r/actions/variables",
        "gh api -X GET repos/o/r/actions/runs --jq '.total_count'",
        "gh api repos/o/r/actions/runs/1234/logs > run.zip",
        "gh api --paginate repos/o/r/actions/secrets",
        "gh api --method GET repos/o/r/actions/variables -f per_page=100",
        "gh api graphql -f query='query { viewer { login } }'",
        "gh api repos/o/r/dispatches",
        # ... and the writes
        "gh api -X PATCH repos/o/r/actions/variables/SF_SYNC -f value=apply",
        "gh api repos/o/r/actions/workflows/auto-sync.yml/dispatches -f ref=main -f 'inputs[apply]=true'",
        "gh api repos/o/r/dispatches -f event_type=roster-changed",
        "gh api graphql -F query=@m.graphql",
        "gh -R o/r api repos/o/r/actions/variables/X -X DELETE",
        "gh api -iXDELETE repos/o/r/actions/secrets/X",
        "gh api orgs/o/actions/variables -f name=SF_SYNC -f value=x",
        # shapes the reader did not see through (reviews of PR #41): a # it took for a comment,
        # a redirection between the path and the method, a substitution before or inside the
        # command, eval, a shell, gh found at run time, four shells deep
        "gh pr comment 41 --body \"$(printf \"Closes #36\")\" && gh api repos/o/r/actions/variables/X -X PATCH -f value=true",
        "echo `echo #`; gh api -X PATCH repos/o/r/actions/variables/X -f value=true",
        "echo ${x:- #}; gh api -X PATCH repos/o/r/actions/variables/X -f value=true",
        "cat <<'EOF'\ndon't\nEOF\necho ' # '; gh api -X PATCH repos/o/r/actions/variables/X -f value=true",
        "echo `echo #`; gh api graphql -F query=@m.graphql",
        "gh api repos/o/r/actions/variables/SF_SYNC >/dev/null -X PATCH -f value=apply",
        "gh api repos/o/r/actions/variables/SF_SYNC 2>&1 -X PATCH -f value=apply",
        "$(true)gh api -X PATCH repos/o/r/actions/variables/SF_SYNC -f value=apply",
        "gh $(true) api repos/o/r/actions/variables/SF_SYNC -X PATCH -f value=apply",
        "eval 'gh api -X PATCH repos/o/r/actions/variables/SF_SYNC -f value=apply'",
        "bash -c \"gh api repos/o/r/actions/secrets/X -X DELETE\"",
        "sh -c 'gh api repos/o/r/dispatches -f event_type=x'",
        "$(which gh) api repos/o/r/actions/variables/SF_SYNC -X PATCH -f value=apply",
        nest("gh api -X PATCH repos/o/r/actions/variables/SF_SYNC -f value=apply", 4),
        # the gh word and api spelt otherwise
        "/opt/homebrew/bin/gh api repos/o/r/actions/variables",
        "=gh api graphql -f query=x",
        "GH api repos/o/r/actions/variables",
        "Gh API repos/o/r/actions/runs",
        "g\"\"h api repos/o/r/dispatches -f event_type=x",
        "g\\h api repos/o/r/actions/variables",
        "'gh' api repos/o/r/actions/runs",
        "gh 'api' graphql -f query=x",
        "gh a\"\"pi repos/o/r/actions/variables",
        "gh ap\\i repos/o/r/actions/secrets",
    ]
    # every other gh api call is ungated, as on main (Ryan, 2026-10-14): the harness's resume
    # reads, and writes to issues, comments and labels - silent in every mode and from a subagent
    GH_API_UNGATED = [
        "gh api repos/o/r/issues -f title=x",
        "gh api repos/o/r/pulls/1/reviews",
        "gh api --paginate repos/o/r/pulls/1/reviews",
        "gh api repos/o/r/pulls/1/reviews/2/comments",
        "gh api repos/o/r/issues/1/comments -f body=x",
        "gh api -X DELETE repos/o/r/labels/x",
        "gh api user", "gh api -X GET search/issues -f q=x", "gh -R o/r api repos/o/r/pulls/1/reviews",
        "gh api repos/o/r/pulls/1  # check", "# -X DELETE later\ngh api repos/o/r/pulls/1",
        "bash -c \"gh api repos/o/r/pulls/1\"", "/opt/homebrew/bin/gh api repos/o/r/pulls/1/reviews",
        "g\"\"h api repos/o/r/pulls/1/reviews", "GH api repos/o/r/issues/1",
        "echo =gh", "gh pr view 1",
    ]
    # prose that mentions gh api - a commit message, a PR or issue body (a heredoc with an odd
    # apostrophe too), a question on the board - is text, not a command: silent in every mode,
    # headless and from a subagent included (review of 014d2ab: the reader refused these)
    PROSE = [
        "git commit -m \"every gh api command asks; Ryan's go\"",
        "gh pr create --title x --body-file - <<'EOF'\nThe gate no longer reads gh api commands; it's text now.\nEOF",
        "harness-board needs-input 37 --question \"Should a gh api read ask? The hook doesn't parse it.\"",
        "gh issue comment 36 --body-file - <<'EOF'\nIt's done.\nEOF",
        "gh pr create --title x --body \"$(cat <<'EOF'\nThe Ryan's note on gh api\nEOF\n)\"",
        "gh pr comment 41 --body \"gh api reads stay ungated; it's as on main\"",
    ]
    # prose that also names actions/, dispatches or graphql: an accepted over-ask (Ryan,
    # 2026-10-14) - silent or the prompt, never refused in the session
    PROSE_OVER_ASK = ["git commit -m \"live gate: gh api under actions/ asks; Ryan's go\"",
                      "gh pr comment 41 --body \"gh api graphql calls ask now; it's greedy\""]
    # the live families with a quoted or split word, or in capitals: matched as written and with
    # quote and backslash characters removed, in any case (Ryan, 2026-10-14)
    SPELT_OTHERWISE = [
        "gh 'workflow' run auto-sync.yml -f apply=true",
        "gh \"variable\" set SF_SYNC --body apply",
        "GH variable set X --body 1",
        "SF data delete record -s Contact -i 003000000000001",
        "gh secret \"set\" JOTFORM_API_KEY",
        "Gh Workflow Disable auto-sync.yml",
        "sf \"apex\" run -f merge.apex",
        "g\"\"h run rerun 1234",
        "gh var\\iable delete SF_SYNC",
        "npx clasp \"push\" -f",
        "SFDX force:source:deploy -p force-app",
        "Sf Project Deploy Start -d force-app",
        "python3 sync_attendance_form.py x --ap\"\"ply",
        "curl -X PUT https://API.JOTFORM.COM/form/1/properties -d @rules.json",
    ]
    # a backslash-newline (LF or CRLF) inside a word: the shell removes it and joins the word
    # (review of 253135b), so the text is matched with those joined - one or more per family
    CONTINUED_WORDS = [
        "python3 sync_attendance_form.py x --ap\\\nply",
        "python3 sync_attendance_form.py x --pr\\\r\nune",
        "gh vari\\\nable set X --body 1",
        "g\\\nh variable set SF_SYNC --body apply",
        "gh secret s\\\r\net JOTFORM_API_KEY",
        "gh workflow run auto-sync.yml -f ap\\\nply=true",
        "gh run re\\\nrun 1234",
        "gh api repos/o/r/acti\\\nons/variables/X -X PATCH",
        "gh api gra\\\r\nphql -f query=x",
        "sf apex r\\\nun -f merge.apex",
        "sf data del\\\nete record -s Contact -i 003000000000001",
        "npx clasp pu\\\nsh -f",
        "curl -X PUT https://api.jot\\\nform.com/form/1/properties -d @rules.json",
        "python3 tools/sf_dupes.py merge --reh\\\r\nearse",
    ]
    # gh's -R/--repo between a family's words (gh variable -R o/r set): the family still asks
    # (review of 253135b) ...
    FLAGS_BETWEEN = [
        "gh variable -R o/r set X --body 1",
        "gh secret -R o/r set X",
        "gh workflow -R o/r disable x.yml",
        "gh run -R o/r rerun 1",
        "gh variable --repo o/r delete SF_SYNC",
        "gh secret --repo=o/r remove X",
        "gh workflow --repo o/r enable auto-sync.yml",
        "gh workflow -R o/r run auto-sync.yml -f apply=true",
    ]
    # ... and the same commands with a verb that changes nothing stay silent
    FLAGS_BETWEEN_READS = ["gh variable list", "gh run list", "gh variable -R o/r list", "gh run -R o/r list",
                           "gh secret --repo o/r list", "gh workflow -R o/r view auto-sync.yml",
                           "gh workflow -R o/r run auto-sync.yml"]
    # the GitHub API by its URL (curl, a script): api.github.com with actions/, dispatches or
    # graphql is live whatever the method, as gh api is (review of 253135b)
    GITHUB_URL_LIVE = [
        "curl -sS https://api.github.com/repos/o/r/actions/variables/AUTO_SYNC_APPLY -X PATCH -d '{\"value\": \"true\"}'",
        "curl -X POST https://api.github.com/repos/o/r/actions/workflows/auto-sync.yml/dispatches -d @in.json",
        "curl -s https://api.github.com/repos/o/r/actions/secrets",
        "curl -X POST https://api.github.com/graphql -d @query.json",
        "curl -X PATCH https://API.GITHUB.COM/repos/o/r/actions/variables/SF_SYNC -d @v.json",
        "python3 -c \"import requests; requests.patch('https://api.github.com/repos/o/r/actions/variables/SF_SYNC')\"",
    ]
    GITHUB_URL_READS = ["curl https://api.github.com/repos/o/r/pulls/1",
                        "curl -s 'https://api.github.com/repos/o/r/issues?state=open'"]

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

    def test_a_gh_api_call_on_actions_dispatches_or_graphql_asks_whatever_the_method(self):
        # "prompt, don't parse" (Ryan, 2026-10-14): the greedy text rule, so no shell construct
        # hides the call and no GET passes; refused where no prompt can be shown, and from a subagent
        for mode in ASK_MODES:
            self.assert_asks(self.GH_API_LIVE, mode=mode)
        with self.subTest("one ASKED per call"):
            self.assertEqual(self.logged(), {"ASKED": len(self.GH_API_LIVE) * len(ASK_MODES)})
        for mode in NO_PROMPT_MODES + ["foo"]:
            self.assert_denies(self.GH_API_LIVE, mode=mode)
        self.assert_denies(self.GH_API_LIVE, agent=True, saying=("agent",))

    def test_every_other_gh_api_call_is_ungated(self):
        # as on main: an issue, a comment, a label, the harness's resume reads - no prompt, and no
        # refusal in a headless run or a subagent (a refusal there would stall the harness)
        for mode in ("default", "dontAsk", "bypassPermissions", "auto", None):
            self.assert_silent(self.GH_API_UNGATED, mode=mode)
        self.assert_silent(self.GH_API_UNGATED, agent=True)
        self.assertEqual(self.logged(), {})

    def test_prose_that_mentions_gh_api_passes_in_every_mode(self):
        for mode in ASK_MODES + NO_PROMPT_MODES + ["foo"]:
            self.assert_silent(self.PROSE, mode=mode)
        self.assert_silent(self.PROSE, agent=True)
        with self.subTest("nothing logged for the prose"):
            self.assertEqual(self.logged(), {})
        # with actions/, dispatches or graphql in it too: the prompt is an accepted over-ask
        for command, run in self.runs(self.PROSE_OVER_ASK):
            with self.subTest(command=command):
                self.assertIn(self.verdict(run), ("silent", "ask"), self.show(run))

    def test_the_live_families_match_with_quoted_words_and_in_any_case(self):
        self.assert_asks(self.SPELT_OTHERWISE)
        with self.subTest("one ASKED per command"):
            self.assertEqual(self.logged(), {"ASKED": len(self.SPELT_OTHERWISE)})
        self.assert_denies(self.SPELT_OTHERWISE, mode="dontAsk", saying=("interactive", "terminal"))
        self.assert_denies(self.SPELT_OTHERWISE, agent=True, saying=("agent",))

    def test_a_word_continued_on_the_next_line_is_one_word(self):
        for mode in ASK_MODES:
            self.assert_asks(self.CONTINUED_WORDS, mode=mode)
        with self.subTest("one ASKED per command"):
            self.assertEqual(self.logged(), {"ASKED": len(self.CONTINUED_WORDS) * len(ASK_MODES)})
        for mode in NO_PROMPT_MODES:
            self.assert_denies(self.CONTINUED_WORDS, mode=mode, saying=("interactive", "terminal"))
        self.assert_denies(self.CONTINUED_WORDS, agent=True, saying=("agent",))

    def test_a_repo_flag_between_the_family_words_does_not_hide_it(self):
        self.assert_asks(self.FLAGS_BETWEEN)
        with self.subTest("one ASKED per command"):
            self.assertEqual(self.logged(), {"ASKED": len(self.FLAGS_BETWEEN)})
        self.assert_denies(self.FLAGS_BETWEEN, mode="dontAsk", saying=("interactive", "terminal"))
        self.assert_denies(self.FLAGS_BETWEEN, agent=True, saying=("agent",))
        before = self.logged()
        for mode in ("default", "dontAsk", None):
            self.assert_silent(self.FLAGS_BETWEEN_READS, mode=mode)
        self.assert_silent(self.FLAGS_BETWEEN_READS, agent=True)
        with self.subTest("nothing logged for the reads"):
            self.assertEqual(self.logged(), before)

    def test_the_github_api_by_url_asks_on_its_live_paths(self):
        for mode in ASK_MODES:
            self.assert_asks(self.GITHUB_URL_LIVE, mode=mode)
        with self.subTest("one ASKED per command"):
            self.assertEqual(self.logged(), {"ASKED": len(self.GITHUB_URL_LIVE) * len(ASK_MODES)})
        self.assert_denies(self.GITHUB_URL_LIVE, mode="dontAsk", saying=("interactive", "terminal"))
        self.assert_denies(self.GITHUB_URL_LIVE, agent=True, saying=("agent",))
        before = self.logged()
        for mode in ("default", "dontAsk", None):
            self.assert_silent(self.GITHUB_URL_READS, mode=mode)
        self.assert_silent(self.GITHUB_URL_READS, agent=True)
        with self.subTest("nothing logged for the reads"):
            self.assertEqual(self.logged(), before)

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

    # anonymous Apex that writes and deletes nothing (2026-10-26, F1 of PR #154's review: the gate
    # reads the file `sf apex run --file` names); a field named IsDeleted holds no word delete
    APEX_UPDATES = [
        "List<Contact> cs = [SELECT Id, FirstName FROM Contact WHERE Club__c = 'Sunrise Club'];\n"
        "for (Contact c : cs) { c.FirstName = c.FirstName.trim(); }\nupdate cs;\n",
        "Account a = [SELECT Id, Name FROM Account WHERE IsDeleted = false AND Name = 'Rising Stars' LIMIT 1];\n"
        "a.Name = 'Rising Stars Club';\nDatabase.update(a);\n",
    ]
    # ... and Apex that deletes, merges (a merge deletes the losing record), undeletes or empties the
    # recycle bin: DML or Database. calls, in any case
    APEX_DELETES = [
        "delete [SELECT Id FROM Contact WHERE LastName = 'Example' LIMIT 1];\n",
        "List<Account> toRemove = [SELECT Id FROM Account WHERE Name = 'Old Club'];\nDelete toRemove;\n",
        "List<Contact> dupes = [SELECT Id FROM Contact WHERE LastName = 'Example'];\nDatabase.delete(dupes, false);\n",
        "List<Id> ids = new List<Id>{'003000000000001'};\nDATABASE.DELETE(ids);\n",
        "Account keep = [SELECT Id FROM Account WHERE Name = 'Sunrise Club' LIMIT 1];\n"
        "Account dup = [SELECT Id FROM Account WHERE Name = 'Sunrise Club 2' LIMIT 1];\nmerge keep dup;\n",
        "Contact keep = [SELECT Id FROM Contact LIMIT 1];\nId dupId = '003000000000002';\nMERGE keep dupId;\n",
        "Contact keep = [SELECT Id FROM Contact LIMIT 1];\nDatabase.merge(keep, '003000000000002');\n",
        "Contact keep = [SELECT Id FROM Contact LIMIT 1];\ndatabase.Merge(keep, '003000000000003', false);\n",
        "undelete [SELECT Id FROM Contact WHERE IsDeleted = true ALL ROWS];\n",
        "List<Account> back = [SELECT Id FROM Account WHERE IsDeleted = true ALL ROWS];\nUnDelete back;\n",
        "List<Id> ids = new List<Id>{'001000000000001'};\nDatabase.emptyRecycleBin(ids);\n",
        "List<Id> ids = new List<Id>{'001000000000002'};\nDATABASE.EMPTYRECYCLEBIN(ids);\n",
    ]

    def backed_writes(self):
        """(command, project, the targets its log line may name, the backup it must name, the
        input's cwd or None): one backed write of each kind, each in a project of its own holding
        only the backup that covers it."""
        F1, F2, F3 = self.F1, self.F2, self.F3
        day = datetime.date.today().isoformat()
        cases = []

        def case(command, targets, backup, records=(), before=None, git=False, files=None, cwd=None):
            p = self.project(git=git)
            for record in records:
                self.back_up(p, *record)
            if before:
                self.salesforce_before(p, before)
            for rel, text in (files or {}).items():
                self.write(p, rel, text)
            if git:
                backup += self.head(p)[:7]
            cases.append((command, p, targets, backup, cwd and os.path.join(p, cwd)))

        # Jotform: a form tool's --apply, the raw API, each form id the command names backed by
        # its own record or by `jotform all`; a command naming no form by `jotform all`
        case(self.jotform_write(F1), ("jotform",), f"backups/{F1}", [("jotform", F1, f"backups/{F1}")])
        case(f"python3 restore_conditions.py --form {F2} --from conditions-2026-10-20T101530.json --apply",
             ("jotform",), f"backups/{F2}", [("jotform", F2, f"backups/{F2}")])
        case(f"curl -sS -X POST https://api.jotform.com/form/{F3}/properties --data-binary @data/props.json",
             ("jotform",), f"backups/{F3}", [("jotform", F3, f"backups/{F3}")])
        case("python3 tools/update_static_fields.py --apply", ("jotform",), "backups/all-forms",
             [("jotform", "all", "backups/all-forms")])
        case(f"python3 tools/add_translations.py --form {F1} --form {F2} --apply", ("jotform",), "backups/every-form",
             [("jotform", "all", "backups/every-form")])
        case(f"python3 tools/fix_roster_order.py --form {F1} --form {F3} --apply", ("jotform",), f"backups/{F3}",
             [("jotform", F1, f"backups/{F1}"), ("jotform", F3, f"backups/{F3}")])
        # a form id is one after --form or in the API path /form/<id> (ruling after the breaker):
        # the form translations are read from (--source) and an id in a file name write nothing
        case(f"python3 tools/restore_translations.py --form={F2} --source {F1} --apply", ("jotform",), f"backups/{F2}",
             [("jotform", F2, f"backups/{F2}")])
        case(f"curl -sS -X POST https://api.jotform.com/form/{F3}/questions --data-binary @data/{F1}-questions.json",
             ("jotform",), f"backups/{F3}", [("jotform", F3, f"backups/{F3}")])
        # the Sheet: an import by its tab's export (a path with a space; a quoted tab) or by
        # `sheet all`; a Sheets API write by `sheet all`
        case("python3 tools/sheets_client.py import Roster data/roster.csv", ("sheet",), "data/sheet export/Roster.csv",
             [("sheet", "Roster", "data/sheet export/Roster.csv")])
        case("python3 tools/sheets_client.py import Partners data/partners.csv", ("sheet",), "data/sheet_all",
             [("sheet", "all", "data/sheet_all")])
        case('python3 tools/sheets_client.py import "ClubRegistry" data/clubs.csv', ("sheet",), "data/ClubRegistry.csv",
             [("sheet", "ClubRegistry", "data/ClubRegistry.csv")])
        # a tab's name is matched whole, a space in it too, in either quotes (ruling after the breaker,
        # round 2)
        case('python3 tools/sheets_client.py import "SF Pending" data/p.csv', ("sheet",), "data/SF Pending.csv",
             [("sheet", "SF Pending", "data/SF Pending.csv")])
        case("python3 tools/sheets_client.py import 'Roster Archive' data/archive.csv", ("sheet",),
             "data/archive export.csv", [("sheet", "Roster Archive", "data/archive export.csv")])
        case("python3 -c 'svc.spreadsheets().values().update(body=b).execute()'", ("sheet",), "data/sheet_full",
             [("sheet", "all", "data/sheet_full")])
        # Apps Script: what is pushed is committed - npx clasp and clasp run in appsscript/, npm run
        # clasp:push in the checkout (the input's cwd: F2 of PR #154's review)
        case("npx clasp push -f", ("appsscript",), "appsscript/ at HEAD ", git=True, cwd="appsscript")
        case("npm run clasp:push", ("appsscript",), "appsscript/ at HEAD ", git=True, cwd=".")
        # Salesforce, raw: the plan folder the command names has a before/ file from today (and an
        # Apex file there that deletes nothing)
        case(f"sf project deploy start --source-dir data/sf_tiles_{day}/after -o glow", ("salesforce", "sf"),
             f"data/sf_tiles_{day}/before", before=f"data/sf_tiles_{day}/before/Attendance.dashboard-meta.xml")
        case("sf apex run --file data/sf_fix_names/fix.apex -o glow", ("salesforce", "sf"), "data/sf_fix_names/before",
             before="data/sf_fix_names/before/contacts.csv", files={"data/sf_fix_names/fix.apex": self.APEX_UPDATES[0]})
        case("sf data upsert bulk -s Contact -f data/sf_contacts/after/contacts.csv -i Id -o glow", ("salesforce", "sf"),
             "data/sf_contacts/before", before="data/sf_contacts/before/main/default/contacts.csv")
        # GitHub: a switch by `github all` (tools/github_switches.py backup); a run of the sync,
        # which writes the forms, by `jotform all`
        for n, command in enumerate(["gh variable set SF_SYNC --body apply", "gh secret set JOTFORM_API_KEY",
                                     "gh workflow disable auto-sync.yml",
                                     "gh api -X PATCH repos/o/r/actions/variables/SF_SYNC -f value=apply"]):
            path = f"backups/github/switches-{day}T09000{n}.json"
            case(command, ("github",), path, [("github", "all", path)])
        case("gh workflow run auto-sync.yml -f apply=true", ("github", "jotform"), "backups/sync-forms",
             [("jotform", "all", "backups/sync-forms")])
        case("gh run rerun 1234", ("github", "jotform"), "backups/rerun-forms", [("jotform", "all", "backups/rerun-forms")])
        return cases

    def test_a_backed_write_goes_through_in_every_mode_but_plan_logged_and_notified(self):
        # Ryan, 2026-10-26: SF, Jotform, Sheet, Apps Script and the sync's switches go through with
        # no prompt once their backup from today exists - interactive, headless and from a subagent
        cases = self.backed_writes()
        callers = ([(mode, None, None) for mode in self.ALLOW_MODES] + [(None, None, {"permission_mode": None})]
                   + [(mode, True, None) for mode in self.AGENT_MODES])
        runs = [(case, caller) for case in cases for caller in callers]
        results = self.all_of(lambda r: self.gate(r[0][0], mode=r[1][0], agent=r[1][1], extra=r[1][2],
                                                  project=r[0][1], cwd=r[0][4], may_allow=True), runs)
        for ((command, _project, targets, backup, _cwd), caller), run in zip(runs, results):
            with self.subTest(command=command, caller=caller):
                self.assertEqual(self.verdict(run), "allow", self.show(run))
                reason = self.reason(run)
                self.assertTrue(any(t in reason.lower() for t in targets), f"the reason names none of {targets}: {reason!r}")
                self.assertIn(backup, reason, "the reason does not name the backup used")
        for command, project, targets, backup, _cwd in cases:
            with self.subTest(command=command, check="log"):
                lines = self.lines_of(project)
                self.assertEqual([d for d, _ in lines], ["ALLOWED"] * len(callers), lines)    # one line per allow
                modes, agents = set(), 0
                for _, rest in lines:
                    m = self.ALLOWED.match(rest)
                    self.assertIsNotNone(m, f"not `mode=<mode>[ agent] target=<target> backup=<what> <command>`: {rest!r}")
                    self.assertIn(m.group("target"), targets, rest)
                    self.assertIn(backup, m.group("rest"), rest)
                    self.assertTrue(rest.endswith(command), f"the line does not end with the command: {rest!r}")
                    modes.add(m.group("mode").strip('"'))
                    agents += bool(m.group("agent"))
                self.assertEqual(agents, len(self.AGENT_MODES), "a subagent's line says ' agent', a main session's not")
                for mode in self.ALLOW_MODES:
                    if mode:
                        self.assertIn(mode, modes, f"no ALLOWED line names mode {mode}: {lines}")
        calls = self.notifications(len(runs))
        self.assertEqual(len(calls), len(runs), "one notification per allow")
        for command, *_ in cases:
            with self.subTest(command=command, check="notified"):
                mine = [self.split_osascript(c)[1] for c in calls if any(command[:120] in a for a in c)]
                self.assertEqual(len(mine), len(callers), "one notification per allow of this command")
                for args in mine:
                    self.assertEqual(args[0], self.TITLE, args)

    def test_the_notification_carries_the_command_only_as_an_argument(self):
        # AppleScript text built from the command could run `do shell script`: the scripts are
        # fixed, the title and the message (target, id, the command's first line cut to 120
        # characters) come only as argv items after them - a double quote arrives as it was typed
        F1 = self.F1
        p = self.project()
        self.back_up(p, "jotform", F1, f"backups/{F1}")
        commands = [f"python3 sync_attendance_form.py \"data/Grace's roster.csv\" --roster --region Africa --form {F1} --apply",
                    f"python3 sync_attendance_form.py \"data/x\\\" with title \\\"y.csv\" --roster --region Africa --form {F1} --apply",
                    f"python3 sync_attendance_form.py data/{'roster_' * 20}.csv --roster --region Africa --form {F1} --apply"]
        for command in commands:
            run = self.gate(command, mode="dontAsk", project=p, may_allow=True)
            self.assertEqual(self.verdict(run), "allow", self.show(run))
        calls = self.notifications(len(commands))
        self.assertEqual(len(calls), len(commands), calls)
        for command in commands:
            with self.subTest(command=command):
                mine = [c for c in calls if any(command[:120] in a for a in c)]
                self.assertEqual(len(mine), 1, calls)
                scripts, args = self.split_osascript(mine[0])
                self.assertEqual(scripts, self.SCRIPTS, "an -e script is not the fixed text")
                self.assertEqual(len(args), 2, f"not exactly a title and a message: {mine[0]}")
                self.assertEqual(mine[0][-2:], args, "the title and message do not come after the scripts")
                title, message = args
                self.assertEqual(title, self.TITLE)
                self.assertTrue(message.startswith(f"jotform {F1}: "), message)
                self.assertIn(command[:120], message)
                if len(command) > 120:
                    self.assertNotIn(command[:121], message, "the command is not cut to 120 characters")

    def test_the_hook_does_not_wait_for_the_notification(self):
        # its timeout is 5 s (settings.json): a hung osascript must not hold the answer
        with open(self.slow, "w", encoding="utf-8"):
            pass
        p = self.project()
        self.back_up(p, "jotform", self.F1, f"backups/{self.F1}")
        started = time.monotonic()
        run = self.gate(self.jotform_write(), mode="auto", project=p, may_allow=True)
        took = time.monotonic() - started
        self.assertEqual(self.verdict(run), "allow", self.show(run))
        self.assertLess(took, 4.0, f"the hook waited {took:.1f} s on osascript")

    # every tool whose --apply writes a Jotform form (read 2026-10-26: each writes questions,
    # properties or translations through glow.jotform's Client, or - auto_sync.py - runs
    # sync_attendance_form.py --apply per region): the command with {forms} where its --form goes,
    # and whether --form is required (None: the tool has none). Not on it, their --apply writing no
    # form: deactivate_clubs.py and upload_roster.py (the Sheet), fix_module_values.py
    # (Salesforce) - NEVER_AUTOMATIC; club_names.py, backfill_resolve.py, form_status.py,
    # integration_status.py and backup_forms.py write nothing live
    FORM_TOOLS = {
        "sync_attendance_form.py": ("python3 sync_attendance_form.py data/roster.csv --roster --region Asia {forms} --apply", True),
        "restore_conditions.py": ("python3 restore_conditions.py {forms} --from conditions-2026-10-20T101530.json --apply", True),
        "add_feedback_link.py": ("python3 tools/add_feedback_link.py --link roster {forms} --apply", False),
        "add_language.py": ("python3 tools/add_language.py --code or --name Oriya --dict tools/translations_or.json {forms} --apply",
                            False),
        "add_session_notes.py": ("python3 tools/add_session_notes.py {forms} --apply", False),
        "add_translations.py": ("python3 tools/add_translations.py {forms} --apply", False),
        "auto_sync.py": ("python3 tools/auto_sync.py --region Asia --apply", None),
        "disable_form.py": ("python3 tools/disable_form.py {forms} --apply", True),
        "fix_name_translations.py": ("python3 tools/fix_name_translations.py {forms} --apply", True),
        "fix_roster_order.py": ("python3 tools/fix_roster_order.py {forms} --apply", False),
        "rename_club.py": ('python3 tools/rename_club.py --partner "Demo Partner" --old "Old Club" --new "New Club" {forms} --apply',
                           False),
        "restore_translations.py": ("python3 tools/restore_translations.py {forms} --apply", True),
        "switcher_flags.py": ("python3 tools/switcher_flags.py {forms} --apply", False),
        "update_static_fields.py": ("python3 tools/update_static_fields.py {forms} --apply", False),
    }

    def form_tool_cases(self):
        """(tool, command, project, the backups the reason must name, allowed?) for every form tool:
        backed by `jotform all`; by the records of the forms its --form names (`--form <id>` or
        `--form=<id>`, one or two); and the same commands with another form's records only, or
        each form's but not `jotform all` - each in a project of its own. rename_club.py writes the
        Sheet too: its projects hold `sheet all` besides."""
        F1, F2, F3 = self.F1, self.F2, self.F3
        cases = []

        def case(tool, command, records, backup, allowed):
            p = self.project()
            for record in records + ([("sheet", "all", "data/sheet_all")] if tool == "rename_club.py" else []):
                self.back_up(p, *record)
            cases.append((tool, command, p, backup, allowed))

        for n, (tool, (template, required)) in enumerate(sorted(self.FORM_TOOLS.items())):
            every = f"backups/all-{n}"
            forms = f"--form {F1}" if required else ""
            command = " ".join(template.format(forms=forms).split())
            case(tool, command, [("jotform", "all", every)], [every], True)
            if required is None:
                case(tool, command, [("jotform", F, f"backups/{F}") for F in (F1, F2, F3)], [], False)
                continue
            if not required:                 # no --form: every form it writes, so `jotform all` only
                case(tool, command, [("jotform", F, f"backups/{F}") for F in (F1, F2, F3)], [], False)
            spelt = [f"--form {F2}", f"--form={F2}", f"--form {F2} --form {F3}"][n % 3]
            if required and " --form " in spelt[1:]:
                spelt = f"--form {F2}"       # (a required --form takes one id; fix_name_translations.py one only)
            command = " ".join(template.format(forms=spelt).split())
            named = [F for F in (F2, F3) if F in spelt]
            case(tool, command, [("jotform", F, f"backups/{F}") for F in named], [f"backups/{F}" for F in named], True)
            case(tool, command, [("jotform", F1, f"backups/{F1}")], [], False)
        return cases

    def test_every_form_tool_s_apply_goes_through_on_its_forms_backups_only(self):
        # Ryan, 2026-10-26: Jotform form changes go through once the form's backup from today
        # exists - for every tool that writes a form, not a sample; with another form's backup, or
        # each form's when the command picks the forms itself, it is refused where no prompt shows
        cases = self.form_tool_cases()
        self.assertEqual(len({c[0] for c in cases}), len(self.FORM_TOOLS))
        callers = [("dontAsk", None), ("auto", True)]
        runs = [(case, caller) for case in cases for caller in (callers if case[4] else callers[:1])]
        results = self.all_of(lambda r: self.gate(r[0][1], mode=r[1][0], agent=r[1][1], project=r[0][2],
                                                  may_allow=r[0][4]), runs)
        for ((tool, command, _project, backups, allowed), caller), run in zip(runs, results):
            with self.subTest(tool=tool, command=command, caller=caller):
                self.assertEqual(self.verdict(run), "allow" if allowed else "deny", self.show(run))
                message = (self.reason(run) + "\n" + run.err).lower()
                if allowed:
                    self.assertIn("jotform", message, "the reason does not name the target")
                    for backup in backups:
                        self.assertIn(backup, self.reason(run), "the reason does not name each backup used")
                else:
                    for needle in ("backup", "today", "backup_forms.py"):
                        self.assertIn(needle, message, f"the refusal does not say {needle!r}")
        for tool, command, project, backups, allowed in cases:
            with self.subTest(tool=tool, command=command, check="log"):
                lines = self.lines_of(project)
                if allowed:
                    self.assertEqual([d for d, _ in lines], ["ALLOWED"] * len(callers), lines)
                    for _, rest in lines:
                        m = self.ALLOWED.match(rest)
                        self.assertIsNotNone(m, rest)
                        self.assertIn("jotform", m.group("target"), rest)
                        for backup in backups:
                            self.assertIn(backup, m.group("rest").split(command)[0], rest)
                else:
                    self.assertNotIn("ALLOWED", [d for d, _ in lines], lines)
        allowed = sum(len(callers) for c in cases if c[4])
        self.assertEqual(len(self.notifications(allowed)), allowed, "one notification per allow")

    def unbacked_writes(self):
        """(why, command, project, what the reason must name) for a write whose backup is missing,
        stale, of another form, tab or target, gone or outside the project - each in its own
        project."""
        F1, F2, F3 = self.F1, self.F2, self.F3
        today = datetime.date.today()
        yesterday, tomorrow = today - datetime.timedelta(days=1), today + datetime.timedelta(days=1)
        try:
            last_year = today.replace(year=today.year - 1)
        except ValueError:                                              # 29 February
            last_year = today - datetime.timedelta(days=366)
        jot = self.jotform_write(F1)
        on_f1 = ("backup", "today", f"backup_forms.py --form {F1}")
        cases = []

        def case(why, command, records=(), hint=(), before=(), git=False, appsscript=True, change=None, cwd=None):
            p = self.project(git=git, appsscript=appsscript)
            for record in records:
                self.back_up(p, *record)
            for rel, day in before:
                self.salesforce_before(p, rel, day)
            if change:
                change(p)
            cases.append((why, command, p, hint, cwd and os.path.join(p, cwd)))

        case("no record at all", jot, hint=on_f1)
        case("a record from yesterday", jot, [("jotform", F1, f"backups/{F1}", yesterday)], on_f1)
        case("a record from this day last year", jot, [("jotform", F1, f"backups/{F1}", last_year)], on_f1)
        case("a record dated tomorrow", jot, [("jotform", F1, f"backups/{F1}", tomorrow)], on_f1)
        case("a record of another form", jot, [("jotform", F2, f"backups/{F2}")], on_f1)
        case("a record of another target", jot, [("sheet", F1, f"backups/{F1}")], on_f1)
        case("a record whose id only contains the form id", jot, [("jotform", "9" + F1, f"backups/9{F1}")], on_f1)
        case("a record whose backup is gone", jot, [("jotform", F1, f"backups/{F1}", None, False)], on_f1)
        case("a record whose backup is outside the project", jot, [("jotform", F1, "../elsewhere")], on_f1)
        case("a record whose backup path is absolute", jot, [("jotform", F1, os.path.join(self.side.name, "abs"))], on_f1)

        def climbs_out(p):                  # backups/../../x: inside at first, out of the project after
            os.makedirs(os.path.join(p, "backups"), exist_ok=True)
            self.write(os.path.dirname(p), "x/questions-latest.json", "{}\n")
            self.back_up(p, "jotform", F1, "backups/../../x", make=False)
        case("a record whose path climbs out partway", jot, hint=on_f1, change=climbs_out)
        case("a record whose path climbs out and back in", jot, hint=on_f1,
             change=lambda p: self.back_up(p, "jotform", F1, f"../{os.path.basename(p)}/backups/{F1}"))
        case("yesterday's record whose path holds today's date and time", jot,
             [("jotform", F1, f"backups/{today.isoformat()} 09:00:00/{F1}", yesterday)], on_f1)
        case("one of two forms not backed", f"python3 tools/add_translations.py --form {F1} --form {F2} --apply",
             [("jotform", F1, f"backups/{F1}")], ("backup", "today", f"backup_forms.py --form {F2}"))
        case("a command naming no form, each form backed but not all",
             "python3 tools/update_static_fields.py --apply",
             [("jotform", F, f"backups/{F}") for F in (F1, F2, F3)], ("backup", "today", "backup_forms.py"))
        case("the raw API without its form's record",
             f"curl -sS -X POST https://api.jotform.com/form/{F3}/properties --data-binary @data/props.json",
             [("jotform", F1, f"backups/{F1}")], ("backup", "today", f"backup_forms.py --form {F3}"))
        # a 15-digit number that is not after --form names no form: the command writes the forms it
        # picks itself, so only `jotform all` backs it - never that number's own record
        on_all = ("backup", "today", "backup_forms.py")
        case("a form id only in a file path", f"python3 tools/update_static_fields.py --apply --notes docs/{F1}-notes.md",
             [("jotform", F1, f"backups/{F1}")], on_all)
        case("a form id only after another flag", f"python3 tools/switcher_flags.py --apply --ref {F1}",
             [("jotform", F1, f"backups/{F1}")], on_all)
        case("a form id after a flag that only starts with --form", f"python3 tools/fix_roster_order.py --apply --formerly {F1}",
             [("jotform", F1, f"backups/{F1}")], on_all)
        case("the form an apply reads from backed, the one it writes not",
             f"python3 tools/restore_translations.py --form {F2} --source {F1} --apply",
             [("jotform", F1, f"backups/{F1}")], ("backup", "today", f"backup_forms.py --form {F2}"))
        on_sheet = ("backup", "today", "sheets_client.py export")
        case("an import with another tab's export", "python3 tools/sheets_client.py import Roster data/roster.csv",
             [("sheet", "Partners", "data/Partners.csv")], on_sheet)
        case("an import with yesterday's export", "python3 tools/sheets_client.py import Roster data/roster.csv",
             [("sheet", "Roster", "data/Roster.csv", yesterday)], on_sheet)
        case("an import with a form backup", "python3 tools/sheets_client.py import Roster data/roster.csv",
             [("jotform", "all", "backups")], on_sheet)
        case("a Sheets API write with one tab's export", "python3 -c 'svc.spreadsheets().values().update(body=b).execute()'",
             [("sheet", "Roster", "data/Roster.csv")], on_sheet)
        # a tab is matched whole - no prefix, no first word of a longer name (ruling after the breaker,
        # round 2); unquoted, the tab is the one word after import
        case("an import of Roster with the Roster Archive tab's export only", "python3 tools/sheets_client.py import Roster data/roster.csv",
             [("sheet", "Roster Archive", "data/Roster Archive.csv")], on_sheet)
        case("an import of a two-word tab with its first word's export only",
             'python3 tools/sheets_client.py import "SF Pending" data/p.csv', [("sheet", "SF", "data/SF.csv")], on_sheet)
        case("an import of a two-word tab with a longer tab's export only",
             "python3 tools/sheets_client.py import 'SF Pending' data/p.csv",
             [("sheet", "SF Pending Old", "data/SF Pending Old.csv")], on_sheet)
        case("an unquoted two-word tab, whose tab is its first word", "python3 tools/sheets_client.py import SF Pending data/p.csv",
             [("sheet", "SF Pending", "data/SF Pending.csv")], on_sheet)
        # a tool that writes two targets needs both backups (ruling after the test-author, round 1):
        # rename_club.py renames the club on the forms and in the Sheet - with its forms' backup and
        # no `sheet all` it asks, the reason naming the Sheet's export; with the Sheet's and no form's,
        # naming the forms' backup
        rename = 'python3 tools/rename_club.py --partner "Demo Partner" --old "Old Club" --new "New Club"'
        case("rename_club.py with jotform all and no Sheet export", rename + " --apply",
             [("jotform", "all", "backups")], on_sheet)
        case("rename_club.py with its form's backup and one tab's export", f"{rename} --form {F1} --apply",
             [("jotform", F1, f"backups/{F1}"), ("sheet", "Roster", "data/Roster.csv")], on_sheet)
        case("rename_club.py with the Sheet's export and no form backup", rename + " --apply",
             [("sheet", "all", "data/sheet_all")], ("backup", "today", "backup_forms.py"))
        on_switches = ("backup", "today", "github_switches.py backup")
        case("a switch with a form backup only", "gh variable set SF_SYNC --body apply", [("jotform", "all", "backups")],
             on_switches)
        case("a switch with yesterday's backup", "gh workflow enable auto-sync.yml",
             [("github", "all", "backups/github/switches.json", yesterday)], on_switches)
        case("an applying run with the switches' backup only", "gh workflow run auto-sync.yml -f apply=true",
             [("github", "all", "backups/github/switches.json")], ("backup", "today", "backup_forms.py"))
        on_before = ("backup", "today", "before/")
        deploy = "sf project deploy start --source-dir data/sf_tiles/after -o glow"
        case("a before/ retrieve from yesterday", deploy, before=[("data/sf_tiles/before/Attendance.xml", yesterday)],
             hint=on_before)
        case("an empty before/", deploy, change=lambda p: os.makedirs(os.path.join(p, "data", "sf_tiles", "before")),
             hint=on_before)
        case("another plan's before/", deploy, before=[("data/sf_other/before/Attendance.xml", None)], hint=on_before)
        case("a data write naming no plan folder", "sf data update record -s Account -i 001000000000001 -v \"Name='Rising Stars'\" -o glow",
             before=[("data/sf_tiles/before/Attendance.xml", None)], hint=on_before)
        case("a quick deploy by its job id", "sf project deploy quick --job-id 0Af000000000001 -o glow",
             before=[("data/sf_tiles/before/Attendance.xml", None)], hint=on_before)
        # (npx clasp run in appsscript/, npm run in the checkout: the folder each pushes from is right,
        # so what is missing is the commit - F2 of PR #154's review)
        case("a tracked Apps Script file changed", "npx clasp push -f", git=True, hint=("commit",), cwd="appsscript",
             change=lambda p: self.write(p, "appsscript/Code.gs", "function onEdit(e) { return 1; }\n"))
        case("an untracked Apps Script file", "npm run clasp:push", git=True, hint=("commit",),
             change=lambda p: self.write(p, "appsscript/Extra.gs", "function extra() {}\n"))

        def staged(p):
            self.write(p, "appsscript/Code.gs", "function onEdit(e) { return 2; }\n")
            self.git(p, "add", "appsscript/Code.gs")
        case("a staged Apps Script change", "npx clasp push -f", git=True, hint=("commit",), change=staged,
             cwd="appsscript")
        case("no git repository", "npx clasp push -f", cwd="appsscript",
             change=lambda p: self.write(p, "appsscript/Code.gs", "function onEdit(e) {}\n"))
        case("a repository without appsscript/", "npx clasp push -f", git=True, appsscript=False, cwd="appsscript")
        return cases

    def test_a_write_without_a_backup_from_today_asks_or_is_refused_saying_which(self):
        # the same writes with their backup missing, stale, of another form, tab or target, gone, or
        # outside the project: asked in a session that can show the prompt, refused (needs-input)
        # where none can - the reason says there is no backup from today and how to make one
        cases = self.unbacked_writes()
        callers = [(mode, None) for mode in ASK_MODES] + [(mode, None) for mode in self.HEADLESS] + [("auto", True)]
        runs = [(case, caller) for case in cases for caller in callers]
        results = self.all_of(lambda r: self.gate(r[0][1], mode=r[1][0], agent=r[1][1], project=r[0][2], cwd=r[0][4]),
                              runs)
        for ((why, command, _project, hint, _cwd), (mode, agent)), run in zip(runs, results):
            with self.subTest(why=why, mode=mode, agent=agent):
                expected = "ask" if mode in ASK_MODES and not agent else "deny"
                self.assertEqual(self.verdict(run), expected, self.show(run))
                if expected == "ask":
                    self.check_reason(command, self.reason(run))
                message = (self.reason(run) + "\n" + run.err).lower()
                for needle in hint:
                    self.assertIn(needle.lower(), message, f"the reason does not say {needle!r}")
        for why, _command, project, _hint, _cwd in cases:
            with self.subTest(why=why, check="log"):
                counts = collections.Counter(d for d, _ in self.lines_of(project))
                self.assertNotIn("ALLOWED", counts)
                self.assertEqual(counts["ASKED"], len(ASK_MODES))
                self.assertEqual(counts["BLOCKED"] + counts["DENIED"], len(callers) - len(ASK_MODES))
        self.assertEqual(self.quiet_notifications(), [], "a notification without an allow")

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

    def test_plan_mode_and_an_unknown_mode_never_get_the_automatic_go(self):
        # plan: a hook's allow has no effect there (Claude Code 2.1.299) - it asks; an unknown or
        # odd mode fails closed - refused. The control: each is allowed in auto in this project
        p = self.fully_backed()
        commands = [self.jotform_write(), "npx clasp push -f", "gh variable set SF_SYNC --body apply",
                    "sf project deploy start --source-dir data/sf_x/after -o glow",
                    "python3 tools/sheets_client.py import Roster data/roster.csv",
                    "gh workflow run auto-sync.yml -f apply=true"]
        # (npx clasp in appsscript/, the folder it pushes from: F2 of PR #154's review)
        where = {c: os.path.join(p, "appsscript") if "clasp" in c else None for c in commands}
        for command in commands:
            with self.subTest(command=command, mode="auto"):
                run = self.gate(command, mode="auto", project=p, cwd=where[command], may_allow=True)
                self.assertEqual(self.verdict(run), "allow", "the control - " + self.show(run))
        odd = [{"permission_mode": v} for v in (1, True, ["default"], {"mode": "auto"}, "dontask", "Auto")]
        cases = ([(c, {"mode": "plan"}) for c in commands] + [(c, {"mode": m}) for m in UNKNOWN_MODES for c in commands]
                 + [(c, {"mode": None, "extra": fields}) for fields in odd for c in commands])
        for command, kw, run in self.verdicts([(c, dict(kw, project=p, cwd=where[c])) for c, kw in cases]):
            with self.subTest(command=command, mode=kw["mode"], extra=kw.get("extra")):
                if kw["mode"] == "plan":
                    self.assertEqual(self.verdict(run), "ask", self.show(run))
                    self.check_reason(command, self.reason(run))
                else:
                    self.assertEqual(self.verdict(run), "deny", self.show(run))
        counts = collections.Counter(d for d, _ in self.lines_of(p))
        self.assertEqual(counts["ALLOWED"], len(commands), "only the controls are allowed")
        self.assertEqual(counts["ASKED"], len(commands))

    def deletes(self):
        F1 = self.F1
        return [
            "sf data delete record -s Contact -i 003000000000001 -o glow",
            "sf data delete bulk -s Contact -f data/sf_x/after/ids.csv -o glow",
            "sf project delete source -m ApexClass:GlowSync -o glow",
            "sfdx force:source:delete -m ApexClass:GlowSync",
            "sf project deploy start --source-dir data/sf_x/after --post-destructive-changes "
            "data/sf_x/after/destructiveChangesPost.xml -o glow",
            "sf project deploy start --manifest data/sf_x/after/package.xml --pre-destructive-changes "
            "data/sf_x/after/destructiveChanges.xml -o glow",
            "sf api request rest /services/data/v60.0/sobjects/Account/001x -X DELETE -o glow",
            "gh variable delete SF_SYNC", "gh secret delete GLOW_SA_JSON", "gh variable remove AUTO_SYNC_APPLY",
            "gh secret remove GLOW_SA_JSON", "gh -R o/r variable delete SF_SYNC", "gh secret --repo=o/r remove X",
            "gh api -X DELETE repos/o/r/actions/variables/SF_SYNC",
            f"curl -sS -X DELETE https://api.jotform.com/form/{F1}/question/7",
            f"curl -sS --request DELETE https://api.jotform.com/form/{F1}/question/12",
            "curl -sS -XDELETE https://api.jotform.com/submission/6123456789012345678",
            f"python3 -c \"__import__('requests').delete('https://api.jotform.com/form/{F1}/question/7')\"",
            f"python3 -c \"__import__('requests').request(method='DELETE', url='https://api.jotform.com/form/{F1}')\"",
            # the method as a positional argument, in any case (ruling after the breaker, round 2)
            f"python3 -c \"__import__('requests').request('DELETE', 'https://api.jotform.com/form/{F1}/question/7')\"",
            f"python3 -c \"__import__('requests').request('delete', 'https://api.jotform.com/form/{F1}/question/9')\"",
            f"python3 -c \"import http.client as h; c = h.HTTPSConnection('api.jotform.com'); "
            f"c.request('DELETE', '/form/{F1}/question/7')\"",
            f"python3 sync_attendance_form.py data/roster.csv --roster --region Africa --form {F1} --prune",
            f"python3 sync_attendance_form.py data/roster.csv --roster --region Africa --form {F1} --apply --prune",
            # the form tools' --remove takes their element or field off the form: a question deleted
            "python3 tools/add_feedback_link.py --link roster --remove --apply",
            f"python3 tools/add_session_notes.py --form {F1} --remove --apply",
            # a merge deletes the losing contact; the cleanup deletes affiliations (design addendum);
            # every sf_dupes.py --apply, its rename too, is one class: only its --rehearse is a write
            "python3 tools/sf_dupes.py merge data/sf_dupes/merge_plan.json --apply --vpn-off",
            "python3 tools/sf_dupes.py cleanup data/sf_dupes/merge_plan.json --apply --vpn-off",
            "python3 tools/sf_dupes.py rename data/sf_dupes/merge_plan.json --roster data/roster.csv --apply --vpn-off",
        ]

    def test_a_delete_or_prune_asks_or_is_refused_even_with_every_backup(self):
        # Ryan, 2026-10-26: deletes and --prune still ask; where no prompt can show, refused
        p = self.fully_backed()
        self.assert_backed(p)
        commands = self.deletes()
        for mode in ASK_MODES:
            self.assert_asks(commands, mode=mode, project=p)
        for mode in self.HEADLESS + ["foo"]:
            self.assert_denies(commands, mode=mode, project=p)
        self.assert_denies(commands, mode="auto", agent=True, project=p)
        counts = collections.Counter(d for d, _ in self.lines_of(p))
        self.assertEqual(counts["ALLOWED"], 1, "only the control is allowed")
        self.assertEqual(counts["ASKED"], len(commands) * len(ASK_MODES))
        self.assertEqual(counts["BLOCKED"] + counts["DENIED"], len(commands) * 5)
        self.assertEqual(len(self.quiet_notifications()), 1, "only the control is notified")

    # absolute paths in the cases below, assembled so no literal one sits in this file (make check's
    # docs-links refuses them): the records named from a home folder, files from outside the project
    HOME_RECORDS = os.path.join(os.sep, "Users", "someone", "jotform-glow-sync", ".claude", "live_backups.log")
    OUTSIDE_RECORDS = os.path.join(os.sep, "tmp", "records")
    OUTSIDE_XML = os.path.join(os.sep, "tmp", "a.xml")
    # the backup records written by hand: a forged record is a self-approval (any case: the Mac's
    # file system ignores it)
    LOG_WRITES = [
        "printf '2026-10-26 09:00:00\\tjotform\\tall\\tbackups\\n' >> .claude/live_backups.log",
        "echo x | tee -a .claude/live_backups.log",
        "echo x | tee .claude/live_backups.log",
        "sed -i '' 's/2026-10-25/2026-10-26/' .claude/live_backups.log",
        "sed --in-place 's/a/b/' ./.claude/live_backups.log",
        "perl -pi -e 's/25/26/' .claude/live_backups.log",
        "echo x > \"$CLAUDE_PROJECT_DIR/.claude/live_backups.log\"",
        "cat old.txt >>./.claude/live_backups.log",
        f"python3 tools/x.py > {HOME_RECORDS}",
        "printf 'x' >> .claude/LIVE_BACKUPS.log",
        # ... a copy, a move or a link put in its place, a file opened by a script, or the writer
        # called by hand: records nobody backed up for (ruling after the breaker)
        "cp data/forged.log .claude/live_backups.log",
        f"cp -p {OUTSIDE_RECORDS} ./.claude/live_backups.log",
        f"mv {OUTSIDE_RECORDS} .claude/live_backups.log",
        f"dd if={OUTSIDE_RECORDS} of=.claude/live_backups.log",
        f"ln -sf {OUTSIDE_RECORDS} .claude/live_backups.log",
        f"rsync -a {OUTSIDE_RECORDS} .claude/live_backups.log",
        f"install -m 600 {OUTSIDE_RECORDS} .claude/live_backups.log",
        f"ditto {OUTSIDE_RECORDS} .claude/live_backups.log",
        "python3 -c \"open('.claude/live_backups.log','a').write('2026-10-26 09:00:00\\tjotform\\tall\\tbackups\\n')\"",
        "python3 -c \"import os; open(os.path.join('.claude', 'live_backups.log'), 'a').write('x')\"",
        "python3 -c \"from glow import live_backups; live_backups.record('jotform','all','backups')\"",
        "python3 -c \"from glow.live_backups import record; record('jotform', 'all', 'backups')\"",
        "python3 -c \"import glow.live_backups as lb; lb.record('github', 'all', 'backups/github')\"",
        # ... in any spelling (ruling after the breaker, round 2): the writer imported under another
        # name or by importlib, pathlib's writers, the bare name after a cd, a ./ inside the path,
        # touch and truncate
        "python3 -c \"from glow import live_backups as lb; lb.record('jotform','all','backups')\"",
        "python3 -c \"import importlib; importlib.import_module('glow.live_backups').record('jotform', 'all', 'backups')\"",
        "python3 -c \"from pathlib import Path; Path('.claude/live_backups.log').write_text('2026-10-26 09:00:00\\tjotform\\tall\\tbackups\\n')\"",
        "python3 -c \"from pathlib import Path; Path('.claude/live_backups.log').open('a').write('x')\"",
        "python3 -c \"import pathlib; pathlib.Path('.claude', 'live_backups.log').write_bytes(b'x')\"",
        "cd .claude && printf x >> live_backups.log",
        "printf x >> .claude/./live_backups.log",
        "touch .claude/live_backups.log",
        "truncate -s 0 .claude/live_backups.log",
    ]
    # a Salesforce plan's before/ retrieve made by hand - the backup a raw sf write goes through on,
    # forged - is a self-approval too (ruling after the breaker, round 2): touch under a before/
    # folder, a copy, move, sync or link whose destination (its last word) is a before/ path, a
    # redirect or tee into one
    BEFORE_WRITES = ["touch data/sf_x_2026-10-26/before/a.xml",
                     "cp -R data/sf_x/after data/sf_x/before",
                     "cp a.xml data/sf_x/before/",
                     "rsync -a data/sf_x/after/ data/sf_x/before",
                     "echo x > data/sf_x/before/a.xml",
                     f"mv {OUTSIDE_XML} data/sf_x/before/a.xml",
                     "ditto data/sf_x/after data/sf_x/before",
                     "ln -s ../after data/sf_tiles/before",
                     "install -m 644 a.xml data/sf_x/before/a.xml",
                     "echo x | tee data/sf_tiles/before/Attendance.report-meta.xml",
                     "printf '<Report/>' >> data/sf_x/before/main/default/a.xml"]
    # ... and what reads it, copies from it, or retrieves into it (the before/ retrieve itself): no
    # decision
    BEFORE_NOT_WRITES = ["cp -R data/sf_x/before data/sf_x/after",
                         "sf project retrieve start -o glow --target-dir data/sf_x/before",
                         "sf project retrieve start -m Report:Attendance --target-dir data/sf_tiles/before -o glow",
                         "ls -la data/sf_x/before", "cat data/sf_x/before/a.xml",
                         "diff -r data/sf_x/before data/sf_x/after"]
    LOG_READS = ["cat .claude/live_backups.log", "tail -5 .claude/live_backups.log",
                 "grep -c jotform .claude/live_backups.log", "wc -l .claude/live_backups.log",
                 "ls -la .claude/live_backups.log"]
    # what names the records or their writer without writing a record (ruling after the breaker)
    LOG_NOT_WRITES = LOG_READS + [
        "scripts/harness_tests.sh test/live_backups_test.py",
        "scripts/harness_tests.sh test/hooks_test.py test/live_backups_test.py test/live_gate_docs_test.py",
        ".venv/bin/python3 -m unittest discover -s test -p live_backups_test.py",
        "git commit -m \"gate: read .claude/live_backups.log\"",
        "git add glow/live_backups.py test/live_backups_test.py",
        "grep -n 'def record' glow/live_backups.py", "head -40 glow/live_backups.py",
    ]

    def test_self_approval_is_refused_whatever_the_backups(self):
        p = self.fully_backed()
        self.assert_backed(p)
        commands = self.SELF_APPROVING + self.STARTUP_WRITES + self.LOG_WRITES + self.BEFORE_WRITES
        # every mode: without backups, above and below
        callers = [{"mode": "auto"}, {"mode": "dontAsk"}, {"mode": "auto", "agent": True}, {"mode": "dontAsk", "live_ok": "1"}]
        cases = [(command, dict(caller, project=p)) for command in commands for caller in callers]
        for command, kw, run in self.verdicts(cases):
            with self.subTest(command=command, caller=kw):
                self.assertEqual(self.verdict(run), "deny", self.show(run))
        counts = collections.Counter(d for d, _ in self.lines_of(p))
        self.assertEqual(counts["ALLOWED"], 1, "only the control is allowed")
        self.assertNotIn("ASKED", counts)
        self.assertEqual(len(self.quiet_notifications()), 1, "only the control is notified")

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

    def test_writing_the_backup_records_by_hand_is_refused_and_naming_them_is_not(self):
        # no live flag in them: refused for what they write, in a project with no backups too
        self.assert_refused_never_asked(self.LOG_WRITES)
        # the other side: reading the records, running their tests, a commit message or a git add
        # that names them - no record written, no live match: no decision, in every mode and from
        # a subagent, nothing logged (the refusal above must not over-match)
        self.assert_no_decision(self.LOG_NOT_WRITES)

    def test_a_salesforce_before_retrieve_made_by_hand_is_refused_and_copying_from_it_is_not(self):
        # the before/ a raw sf write goes through on, written by hand: refused in every mode and
        # from a subagent, in a project with no backups too; reading it, copying from it or the
        # retrieve that fills it: no decision (with every backup on record too:
        # test_a_read_still_passes_silently_with_every_backup_on_record; refused with them:
        # test_self_approval_is_refused_whatever_the_backups)
        self.assert_refused_never_asked(self.BEFORE_WRITES)
        self.assert_no_decision(self.BEFORE_NOT_WRITES)

    def test_a_read_still_passes_silently_with_every_backup_on_record(self):
        p = self.fully_backed()
        commands = self.READS + self.MENTIONS + self.LOG_NOT_WRITES + self.BEFORE_NOT_WRITES
        for mode in ("auto", None):
            self.assert_silent(commands, mode=mode, project=p)
        self.assert_silent(commands, agent=True, project=p)
        self.assertEqual(self.lines_of(p), [], "nothing live: nothing logged")
        self.assertEqual(self.quiet_notifications(), [])

    # the tools/sf_*.py whose write - --apply, sf_dupes.py's --rehearse - puts its own rollback
    # record on disk before every request (read 2026-10-26, each tool and its test): the gate keeps
    # exactly this list, and allows these with no other record, the reason and the log naming that
    # file. (command, the file it writes first, the file it does not)
    #   sf_backfill.py send       ledger.csv: a "sending" row before each insert (`status` lists what a
    #                             rollback removes, by batch id)
    #   sf_dupes.py merge         merge_rollback.json: every contact, row and affiliation of the merge,
    #     --rehearse              saved before the first Apex run (the rehearsal's own is rolled back;
    #                             every sf_dupes.py --apply is a delete: deletes())
    #   sf_girls_present.py set   ledger.csv: an "open" row before each PATCH of a batch whose value is
    #                             empty, the only kind it writes
    #   sf_partner_monthly.py     ledger.csv: a row with the old count before each insert or PATCH
    #   sf_report_folders.py      ledger.csv: a "sending" row with the old folder and label before each
    #     copy|move|undo          request (a copy's id on disk before its PATCH)
    # Off the list: sf_new_clubs.py and sf_session_timing.py (no standalone write), and any other
    # name (NEVER_AUTOMATIC)
    SF_LISTED = [
        ("python3 tools/sf_backfill.py send --apply --vpn-off", "ledger.csv", "merge_rollback.json"),
        ("python3 tools/sf_backfill.py send --apply --vpn-off --limit 1", "ledger.csv", "merge_rollback.json"),
        ("python3 tools/sf_dupes.py merge data/sf_dupes_2026-10-26/merge_plan.json --rehearse --vpn-off",
         "merge_rollback.json", "ledger.csv"),
        ("python3 tools/sf_girls_present.py set --apply --vpn-off --limit 1", "ledger.csv", "merge_rollback.json"),
        ("python3 tools/sf_partner_monthly.py --month 2026-09 --apply --vpn-off", "ledger.csv", "merge_rollback.json"),
        ("python3 tools/sf_report_folders.py move --vpn-off --plan data/sf_report_folders/plan.csv --apply",
         "ledger.csv", "merge_rollback.json"),
        ("python3 tools/sf_report_folders.py copy --vpn-off --kind report --id 00O000000000001AAA --tag ticket-72 --apply",
         "ledger.csv", "merge_rollback.json"),
        ("python3 tools/sf_report_folders.py undo --vpn-off --ledger data/sf_report_folders/ledger.csv --apply",
         "ledger.csv", "merge_rollback.json"),
    ]

    def test_a_listed_salesforce_tool_goes_through_on_its_own_rollback_record(self):
        # a project with no backup record, no git and no data/: the tool's own record is the backup.
        # Allowed in every mode but plan, from a subagent too, logged and notified like any backed
        # write; plan asks and an unknown mode is refused, as for every write
        p = self.project()
        callers = ([(mode, None, None) for mode in self.ALLOW_MODES] + [(None, None, {"permission_mode": None})]
                   + [(mode, True, None) for mode in self.AGENT_MODES])
        runs = [(case, caller) for case in self.SF_LISTED for caller in callers]
        results = self.all_of(lambda r: self.gate(r[0][0], mode=r[1][0], agent=r[1][1], extra=r[1][2], project=p,
                                                  may_allow=True), runs)
        for ((command, named, other), caller), run in zip(runs, results):
            with self.subTest(command=command, caller=caller):
                self.assertEqual(self.verdict(run), "allow", self.show(run))
                reason = self.reason(run)
                self.assertTrue(any(t in reason.lower() for t in ("salesforce", "sf")), f"no target in {reason!r}")
                self.assertIn(named, reason, "the reason does not name the tool's own rollback record")
                self.assertNotIn(other, reason, "the reason names another tool's rollback record")
        lines = self.lines_of(p)
        self.assertEqual([d for d, _ in lines], ["ALLOWED"] * len(runs), lines)
        for command, named, other in self.SF_LISTED:
            with self.subTest(command=command, check="log"):
                mine = [rest for _, rest in lines if rest.endswith(" " + command)]
                self.assertEqual(len(mine), len(callers), lines)
                for rest in mine:
                    m = self.ALLOWED.match(rest)
                    self.assertIsNotNone(m, f"not `mode=<mode>[ agent] target=<target> backup=<what> <command>`: {rest!r}")
                    self.assertIn(m.group("target"), ("salesforce", "sf"), rest)
                    backup = m.group("rest").split(command)[0]
                    self.assertIn(named, backup, "the log's backup= is not the tool's record")
                    self.assertNotIn(other, backup, "the log's backup= names another tool's record")
        self.assertEqual(len(self.notifications(len(runs))), len(runs), "one notification per allow")
        for command, *_ in self.SF_LISTED[:3]:
            self.assert_asks([command], mode="plan", project=p)
            self.assert_denies([command], mode="foo", project=p)
        self.assertEqual(collections.Counter(d for d, _ in self.lines_of(p))["ALLOWED"], len(runs),
                         "plan mode or an unknown mode was allowed")
        # (the tools off the list, with every backup there is: NEVER_AUTOMATIC; sf_dupes.py's
        # --apply: deletes())

    # ---- live_gate.sh: the fixes after review 1 of PR #154 (the design's "Rulings for review 1's
    # findings", F1 F2 F5; 2026-10-26)
    def sf_plan(self, files=None):
        """A project of its own whose plan folder data/sf_x/ holds a before/ retrieve from today, and
        `files` ({path: text})."""
        p = self.project()
        self.salesforce_before(p, "data/sf_x/before/Contact.object-meta.xml")
        for rel, text in (files or {}).items():
            self.write(p, rel, text)
        return p

    # one text whatever the file holds: only what the file holds can tell an update from a delete
    APEX_RUNS = ["sf apex run --file data/sf_x/fix.apex -o glow", "sf apex run -f data/sf_x/fix.apex -o glow",
                 "sf apex run --file=data/sf_x/fix.apex --target-org glow", "sfdx apex run -f data/sf_x/fix.apex -o glow"]

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

    def test_anonymous_apex_goes_through_only_when_its_file_deletes_nothing(self):
        # F1: `sf|sfdx apex run --file` (-f, --file=) names the Apex the org runs, and the gate reads
        # it. Holding only updates, it goes through on the plan's before/ from today, in every mode
        # but plan and from a subagent; holding delete, merge (a merge deletes the losing record),
        # undelete or emptyRecycleBin - as a word, DML or a Database. call, in any case - it is a
        # delete: asked, refused where no prompt can show, whatever the backups. The command is the
        # same text in every project
        updates = [self.sf_plan({"data/sf_x/fix.apex": text}) for text in self.APEX_UPDATES]
        callers = [{"mode": "default"}, {"mode": "dontAsk"}, {"mode": None}, {"mode": "auto", "agent": True}]
        runs = [(command, dict(caller, project=p, may_allow=True))
                for p in updates for command in self.APEX_RUNS for caller in callers]
        for command, kw, run in self.verdicts(runs):
            with self.subTest(apex=f"APEX_UPDATES[{updates.index(kw['project'])}]", command=command, mode=kw["mode"],
                              agent=kw.get("agent")):
                self.assertEqual(self.verdict(run), "allow", self.show(run))
                self.assertIn("data/sf_x/before", self.reason(run), "the reason does not name the before/ retrieve")
        deletes = [(f"APEX_DELETES[{n}]", self.APEX_RUNS[n % len(self.APEX_RUNS)],
                    self.sf_plan({"data/sf_x/fix.apex": text})) for n, text in enumerate(self.APEX_DELETES)]
        self.assert_delete_class(deletes)
        # the older spelling of the same run, on a file that deletes: never automatic
        for label, _command, p in deletes[:2]:
            for command in ("sfdx force:apex:execute -f data/sf_x/fix.apex -u glow",
                            "sf force:apex:execute --apexcodefile data/sf_x/fix.apex"):
                with self.subTest(case=label, command=command):
                    self.assertEqual(self.verdict(self.gate(command, mode="dontAsk", project=p)), "deny")
        for label, _command, p in deletes:
            with self.subTest(case=label, check="log"):
                self.assertNotIn("ALLOWED", [d for d, _ in self.lines_of(p)])
        for p in updates:
            self.assertEqual([d for d, _ in self.lines_of(p)], ["ALLOWED"] * len(self.APEX_RUNS) * len(callers))
        self.assertEqual(len(self.notifications(len(runs))), len(runs), "one notification per allow")

    def test_anonymous_apex_without_a_readable_file_in_the_checkout_is_never_automatic(self):
        # F1: no --file (the Apex on standard input), a file that is not there, one that cannot be
        # read, or a link to one outside the checkout - the gate cannot read what the org will run:
        # never automatic, the plan's before/ from today notwithstanding
        outside = self.write(self.side.name, "outside/fix.apex", self.APEX_UPDATES[0])
        p = self.sf_plan({"data/sf_x/fix.apex": self.APEX_UPDATES[0], "data/sf_x/locked.apex": self.APEX_UPDATES[1]})
        os.symlink(outside, os.path.join(p, "data", "sf_x", "linked.apex"))
        run = self.gate("sf apex run --file data/sf_x/fix.apex -o glow", mode="dontAsk", project=p, may_allow=True)
        self.assertEqual(self.verdict(run), "allow", "the control: an Apex file here that deletes nothing - " + self.show(run))
        commands = ["sf apex run --file data/sf_x/absent.apex -o glow", "sf apex run -f data/sf_x/linked.apex -o glow",
                    "sf apex run -o glow < data/sf_x/fix.apex", "sfdx apex run --target-org glow < data/sf_x/fix.apex"]
        if os.geteuid() != 0:                                           # root reads a file whatever its mode
            os.chmod(os.path.join(p, "data", "sf_x", "locked.apex"), 0)
            commands.append("sf apex run --file=data/sf_x/locked.apex -o glow")
        self.assert_never_automatic(commands, p)
        self.assertEqual(collections.Counter(d for d, _ in self.lines_of(p))["ALLOWED"], 1, "only the control is allowed")

    def test_a_metadata_dir_deploy_is_never_automatic_and_destructive_changes_are_a_delete(self):
        # F1: a deploy of a metadata (mdapi) folder - --metadata-dir in any spelling, force:mdapi:deploy
        # - is never automatic; a deploy whose folder holds a destructiveChanges*.xml anywhere below it
        # deletes what that file lists: a delete. The control: a deploy of a folder with none goes
        # through on the same before/ from today
        p = self.sf_plan({"data/sf_x/mdapi/package.xml": "<Package/>\n",
                          "data/sf_x/mdapi/reports/Glow/Attendance.report": "<Report/>\n",
                          "data/sf_x/after/main/default/reports/Attendance.report-meta.xml": "<Report/>\n"})
        control = "sf project deploy start --source-dir data/sf_x/after -o glow"
        run = self.gate(control, mode="dontAsk", project=p, may_allow=True)
        self.assertEqual(self.verdict(run), "allow", "the control: a source deploy here - " + self.show(run))
        self.assert_never_automatic(["sf project deploy start --metadata-dir data/sf_x/mdapi -o glow",
                                     "sf project deploy start --metadata-dir=data/sf_x/mdapi -o glow",
                                     "sf project deploy validate --metadata-dir data/sf_x/mdapi -o glow",
                                     "sfdx project deploy start --metadata-dir data/sf_x/mdapi --target-org glow",
                                     "sf deploy metadata --metadata-dir data/sf_x/mdapi -o glow",
                                     "sfdx force:mdapi:deploy -d data/sf_x/mdapi -u glow"], p)
        self.assertEqual(collections.Counter(d for d, _ in self.lines_of(p))["ALLOWED"], 1, "only the control is allowed")
        destructive = []
        for rel in ("destructiveChanges.xml", "main/default/destructiveChangesPost.xml", "a/b/c/destructiveChangesPre.xml"):
            q = self.sf_plan({f"data/sf_x/after/{rel}": "<Package/>\n",
                              "data/sf_x/after/main/default/reports/Attendance.report-meta.xml": "<Report/>\n",
                              "data/sf_x/other/main/default/reports/Attendance.report-meta.xml": "<Report/>\n"})
            run = self.gate("sf project deploy start --source-dir data/sf_x/other -o glow", mode="dontAsk", project=q,
                            may_allow=True)
            self.assertEqual(self.verdict(run), "allow", f"the control beside after/{rel}: a folder with none - " + self.show(run))
            destructive += [(f"after/{rel}", command, q) for command in
                            ("sf project deploy start --source-dir data/sf_x/after -o glow",
                             "sf project deploy start -d data/sf_x/after -o glow",
                             "sf project deploy start --source-dir=data/sf_x/after --target-org glow")]
        self.assert_delete_class(destructive)
        for label, _command, q in destructive:
            with self.subTest(case=label, check="log"):
                self.assertEqual(collections.Counter(d for d, _ in self.lines_of(q))["ALLOWED"], 1,
                                 "only the control is allowed")

    # ---- live_gate.sh: review 2 of PR #154 (2026-11-05): the gate tells a write from a delete by
    # the command's text, so a Salesforce request whose method, URL, headers, body or flags come
    # from a file or standard input is never automatic - a DELETE in the file or not: a request
    # file (sf api request rest --file) carries its own method, a composite body DELETE
    # sub-requests, a header file X-HTTP-Method-Override, sf's --flags-dir (a file per flag) a
    # --method or a --post-destructive-changes, a curl config file (-K) a request = "DELETE" - for
    # any host. Each file below is named by a command that the same command with the request on
    # its command line (the controls) shows would otherwise go through on the same backups; half
    # of them hold no delete at all, so reading the file is no way out
    SF_REST = "https://example.my.salesforce.com/services/data/v60.0"
    SF_REQUEST_FILES = {
        # sf api request rest --file: a request whose method is DELETE, and one whose is PATCH
        "data/sf_x/req.json": '{"url": "/services/data/v60.0/sobjects/Contact/003000000000001", "method": "DELETE"}\n',
        "data/sf_x/patch.json": ('{"url": "/services/data/v60.0/sobjects/Account/001000000000001", "method": "PATCH", '
                                 '"body": {"mode": "raw", "raw": {"Name": "Rising Stars Club"}}}\n'),
        # a composite body with a DELETE sub-request, and a record's fields
        "data/sf_x/body.json": ('{"allOrNone": true, "compositeRequest": [{"method": "DELETE", "referenceId": "gone", '
                                '"url": "/services/data/v60.0/sobjects/Contact/003000000000001"}]}\n'),
        "data/sf_x/fields.json": '{"Name": "Rising Stars Club"}\n',
        # curl header files: a method override, and an ordinary header
        "data/sf_x/headers.txt": "X-HTTP-Method-Override: DELETE\n",
        "data/sf_x/accept.txt": "Accept: application/json\n",
        # curl config files: a DELETE and a PATCH to Salesforce, a DELETE and a POST to Jotform, a
        # DELETE to GitHub's Actions API
        "data/sf_x/request.cfg": 'request = "DELETE"\n',
        "data/sf_x/patch.cfg": 'request = "PATCH"\ndata = "{\\"Name\\": \\"Rising Stars Club\\"}"\n',
        "data/jotform.cfg": 'request = "DELETE"\n',
        "data/jotform_post.cfg": 'request = "POST"\ndata = "properties[title]=Attendance"\n',
        "data/gh.cfg": 'request = "DELETE"\n',
        # GraphQL from a file (sf api request graphql --body <an existing file> reads it): a delete
        # and an update
        "data/sf_x/mutation.graphql": 'mutation { uiapi { ContactDelete(input: {Id: "003000000000001"}) { Id } } }\n',
        "data/sf_x/rename.graphql": ('mutation { uiapi { AccountUpdate(input: {Id: "001000000000001", '
                                     'Account: {Name: "Rising Stars Club"}}) { Record { Id } } } }\n'),
        # sf --flags-dir folders (each file a flag, its text the value): a request's --method DELETE,
        # a request's --method PATCH and --body, a deploy's --post-destructive-changes, a deploy's
        # --wait
        "data/sf_x/flags_rest/method": "DELETE\n",
        "data/sf_x/flags_patch/method": "PATCH\n",
        "data/sf_x/flags_patch/body": "@data/sf_x/fields.json\n",
        "data/sf_x/flags_deploy/post-destructive-changes": "data/sf_x/destructiveChangesPost.xml\n",
        "data/sf_x/destructiveChangesPost.xml": "<Package/>\n",
        "data/sf_x/flags_wait/wait": "33\n",
        # what the source deploys deploy, an earlier response (an output file that exists is no
        # input), and the body file of a Jotform write
        "data/sf_x/after/main/default/reports/Attendance.report-meta.xml": "<Report/>\n",
        "data/sf_x/after/account.json": '{"id": "001000000000001"}\n',
        "data/props.json": '{"properties": {"title": "Attendance"}}\n',
    }
    SF_REQUESTS_FROM_FILES = [
        # sf api request rest: a request file (-f, --file, --file=) ...
        "sf api request rest --file data/sf_x/req.json -o glow",
        "sf api request rest -f data/sf_x/req.json -o glow",
        "sf api request rest --file=data/sf_x/req.json --target-org glow",
        "sfdx api request rest -f data/sf_x/patch.json -o glow",
        # ... a body from a file (@file after -b, --body, --body=) or from standard input (-)
        "sf api request rest /services/data/v60.0/composite -X POST --body @data/sf_x/body.json -o glow",
        "sf api request rest /services/data/v60.0/composite --method POST -b @data/sf_x/body.json -o glow",
        "sf api request rest /services/data/v60.0/composite --method=POST --body=@data/sf_x/body.json -o glow",
        "sf api request rest /services/data/v60.0/sobjects/Account/001000000000001 -X PATCH -b @data/sf_x/fields.json -o glow",
        "sf api request rest /services/data/v60.0/composite -X POST --body - -o glow < data/sf_x/body.json",
        # ... or the flags themselves from files: sf's --flags-dir, on a request (today: no decision
        # at all) and on a deploy, whatever the folder holds
        "sf api request rest /services/data/v60.0/sobjects/Contact/003000000000001 --flags-dir data/sf_x/flags_rest -o glow",
        "sf api request rest /services/data/v60.0/sobjects/Account/001000000000001 --flags-dir data/sf_x/flags_patch -o glow",
        "sf project deploy start --source-dir data/sf_x/after --flags-dir data/sf_x/flags_deploy -o glow",
        "sf project deploy start --source-dir data/sf_x/after --flags-dir data/sf_x/flags_wait -o glow",
        # sf api request graphql: its --body is a file whenever one by that name exists
        "sf api request graphql --body data/sf_x/mutation.graphql -o glow",
        "sf api request graphql --body data/sf_x/rename.graphql -o glow",
        # curl to the REST API: a body or field from a file (-d, --data, --data-binary, --data=,
        # --json, -d@ joined, -F name=@), a header file (-H @), standard input (@- and a < redirect),
        # an upload (-T, --upload-file) or a config file (-K, -sSK, --config)
        f"curl -sS -X POST {SF_REST}/composite -d @data/sf_x/body.json",
        f"curl -sS -X POST {SF_REST}/composite --data @data/sf_x/body.json",
        f"curl -sS -X POST {SF_REST}/composite --data-binary @data/sf_x/body.json",
        f"curl -sS -X POST {SF_REST}/composite --data=@data/sf_x/body.json",
        f"curl -sS -X POST {SF_REST}/composite --json @data/sf_x/body.json",
        f"curl -sS -X POST {SF_REST}/composite -d@data/sf_x/body.json -o data/sf_x/after/out.json",
        f"curl -sS -X POST {SF_REST}/sobjects/ContentVersion -F VersionData=@data/sf_x/fields.json -o data/sf_x/after/cv.json",
        f"curl -sS -X PATCH {SF_REST}/sobjects/Account/001000000000001 -H @data/sf_x/headers.txt "
        "-d '{\"Name\": \"Rising Stars Club\"}' -o data/sf_x/after/account.json",
        f"curl -sS -X PATCH {SF_REST}/sobjects/Account/001000000000001 -H @data/sf_x/accept.txt "
        "-d '{\"Name\": \"Rising Stars Club\"}' -o data/sf_x/after/account.json",
        f"curl -sS -X POST {SF_REST}/composite -d @- -o data/sf_x/after/out.json < data/sf_x/body.json",
        f"curl -sS -X PUT -T data/sf_x/fields.json {SF_REST}/sobjects/Account/Ext_Id__c/1",
        f"curl -sS -X PUT --upload-file data/sf_x/fields.json {SF_REST}/sobjects/Account/Ext_Id__c/2",
        f"curl -sS -K data/sf_x/request.cfg {SF_REST}/sobjects/Contact/003000000000001",
        f"curl -sSK data/sf_x/request.cfg {SF_REST}/sobjects/Contact/003000000000001",
        f"curl -sS --config data/sf_x/patch.cfg {SF_REST}/sobjects/Account/001000000000001",
        # a python3 -c snippet: what it sends comes from any file it reads (open, pathlib)
        f"python3 -c \"__import__('requests').post('{SF_REST}/composite', "
        "data=open(__import__('sys').argv[1], 'rb'))\" data/sf_x/body.json",
        f"python3 -c \"__import__('requests').post('{SF_REST}/composite', "
        "data=__import__('pathlib').Path(__import__('sys').argv[1]).read_bytes())\" data/sf_x/body.json",
    ]

    def test_a_salesforce_request_or_body_from_a_file_is_never_automatic(self):
        # review 2 of PR #154: the plan's before/ from today, the form's backup and the switches'
        # backup notwithstanding, each is asked in default and auto and refused where no prompt can
        # show (dontAsk, bypassPermissions, a missing mode, a subagent), the refusal saying the
        # request comes from a file (or standard input), and logged. A curl config file (-K,
        # --config) sets the method and URL for any host: a Jotform or GitHub call with one is
        # never automatic either. The controls: the same writes with the request on the command
        # line - an existing output file (-S, -o) and a Jotform body file included - go through
        F1 = self.F1
        p = self.sf_plan(self.SF_REQUEST_FILES)
        self.back_up(p, "jotform", F1, f"backups/{F1}")
        self.back_up(p, "github", "all", "backups/github/switches.json")
        controls = [
            "sf api request rest /services/data/v60.0/sobjects/Account/001000000000001 -X PATCH "
            "--body '{\"Name\": \"Rising Stars Club\"}' -S data/sf_x/after/account.json -o glow",
            "sf api request rest /services/data/v60.0/composite -X POST --body '{\"allOrNone\": true, "
            "\"compositeRequest\": [{\"method\": \"PATCH\", \"referenceId\": \"a\", \"url\": "
            "\"/services/data/v60.0/sobjects/Account/001000000000001\", \"body\": {\"Name\": \"Rising Stars Club\"}}]}' "
            "-S data/sf_x/after/composite.json -o glow",
            f"curl -sS -X PATCH {self.SF_REST}/sobjects/Account/001000000000001 -H 'Content-Type: application/json' "
            "-d '{\"Name\": \"Rising Stars Club\"}' -o data/sf_x/after/account.json",
            "sf project deploy start --source-dir data/sf_x/after -o glow",
            f"curl -sS -X POST https://api.jotform.com/form/{F1}/properties --data-binary @data/props.json",
            "curl -sS -X PATCH https://api.github.com/repos/o/r/actions/variables/SF_SYNC "
            "-d '{\"name\": \"SF_SYNC\", \"value\": \"apply\"}'",
        ]
        for command in controls:
            with self.subTest(control=command):
                run = self.gate(command, mode="dontAsk", project=p, may_allow=True)
                self.assertEqual(self.verdict(run), "allow", "the control: the request on the command line - " + self.show(run))
        commands = self.SF_REQUESTS_FROM_FILES + [
            f"curl -sS -K data/jotform.cfg https://api.jotform.com/form/{F1}/question/7",
            f"curl -sS --config data/jotform.cfg https://api.jotform.com/form/{F1}/properties",
            f"curl -sS --config=data/jotform_post.cfg https://api.jotform.com/form/{F1}/properties",
            "curl -sS -K data/gh.cfg https://api.github.com/repos/o/r/actions/variables/SF_SYNC",
        ]
        # may_allow: an allow fails its own subtest (below), not the whole batch at the first one
        self.assert_never_automatic([(c, {"may_allow": True}) for c in commands], p,
                                    saying=("from a file", "standard input"))
        counts = collections.Counter(d for d, _ in self.lines_of(p))
        self.assertEqual(counts["ALLOWED"], len(controls), "only the controls are allowed")
        self.assertEqual(counts["ASKED"], 2 * len(commands), "each from-file request asked in default and auto, logged")
        self.assertEqual(counts["BLOCKED"] + counts["DENIED"], 4 * len(commands),
                         "each from-file request refused headless and from a subagent, logged")
        self.assertEqual(len(self.notifications(len(controls))), len(controls), "the controls are notified")
        self.assertEqual(len(self.quiet_notifications()), len(controls), "only the controls are notified")

    # ---- live_gate.sh: PR #154's three questions, answered yes by Ryan on 2026-11-06
    # 1. curl reads ~/.curlrc (or $CURL_HOME/.curlrc) on every call: a `request = "DELETE"` written
    # there turns a backed Jotform curl with no -X into a delete. A write to it - a redirect, tee,
    # sed -i, perl -i, or a copy, move, link or install onto it - is a self-approval: refused in
    # every mode, whatever the backups
    CURLRC_WRITES = [
        "echo 'request = \"DELETE\"' >> ~/.curlrc",
        "printf 'request = DELETE\\n' > $HOME/.curlrc",
        "echo x >~/.curlrc",
        "echo x | tee ~/.curlrc",
        "echo x | tee -a \"$CURL_HOME/.curlrc\"",
        "printf 'request = DELETE' >> ${CURL_HOME}/.curlrc",
        "sed -i '' 's/GET/DELETE/' ~/.curlrc",
        "sed --in-place 's/a/b/' $CURL_HOME/.curlrc",
        "perl -pi -e 's/GET/DELETE/' ~/.curlrc",
        "cp data/delete.cfg ~/.curlrc",
        "cp -p data/delete.cfg \"$CURL_HOME/.curlrc\"",
        "mv data/delete.cfg ~/.curlrc",
        "ln -sf data/delete.cfg ~/.curlrc",
        "install -m 600 data/delete.cfg ~/.curlrc",
        "rsync -a data/delete.cfg $HOME/.curlrc",
        "ditto data/delete.cfg ~/.curlrc",
        # curl also reads $XDG_CONFIG_HOME/.curlrc (orchestrator's ruling, 2026-11-06)
        "echo 'request = \"DELETE\"' >> $XDG_CONFIG_HOME/.curlrc",
        "cp data/delete.cfg \"${XDG_CONFIG_HOME}/.curlrc\"",
    ]
    # ... and what reads it, or copies it elsewhere (a file whose name only begins .curlrc is not it)
    CURLRC_NOT_WRITES = ["cat ~/.curlrc", "grep -n request ~/.curlrc", "ls -la ~/.curlrc \"$CURL_HOME/.curlrc\"",
                         "cp ~/.curlrc ~/.curlrc.bak", "cp ~/.curlrc data/curlrc-copy.txt",
                         "echo x > ~/.curlrc.bak", "diff ~/.curlrc data/delete.cfg",
                         "cat $XDG_CONFIG_HOME/.curlrc"]

    def assert_refused_with_every_backup(self, commands):
        """Each command refused - never asked - in a project with every backup from today, in
        acceptEdits, bypassPermissions, dontAsk with GLOW_LIVE_OK=1 and from a subagent; each
        refusal logged, only the project's control allowed."""
        p = self.fully_backed()
        self.assert_backed(p)
        callers = [{"mode": "acceptEdits"}, {"mode": "bypassPermissions"}, {"mode": "dontAsk", "live_ok": "1"},
                   {"mode": "auto", "agent": True}]
        cases = [(command, dict(caller, project=p)) for command in commands for caller in callers]
        for command, kw, run in self.verdicts(cases):
            with self.subTest(command=command, caller=kw, backed=True):
                self.assertEqual(self.verdict(run), "deny", self.show(run))
        counts = collections.Counter(d for d, _ in self.lines_of(p))
        self.assertEqual(counts["ALLOWED"], 1, "only the control is allowed")
        self.assertNotIn("ASKED", counts, "a self-approval was asked, not refused")
        self.assertEqual(counts["BLOCKED"] + counts["DENIED"], len(cases), "each refusal logged")

    # the startup files the gate protects (the shells', direnv's .envrc, the repository's .env),
    # written by a copy, move, link, install, rsync or ditto onto them: a self-approval as a
    # redirect into them is (orchestrator's ruling, 2026-11-06, on the gap found with the curlrc)
    STARTUP_COPIES = [
        "cp data/snippet.sh ~/.zshrc",
        "cp -p data/snippet.sh $HOME/.zprofile",
        "mv data/snippet.sh ~/.zshenv",
        "ln -sf data/snippet.sh ~/.zlogin",
        "install -m 644 data/snippet.sh ~/.bashrc",
        "rsync -a data/snippet.sh ~/.bash_profile",
        "ditto data/snippet.sh ~/.bash_login",
        "cp data/snippet.sh \"$HOME/.profile\"",
        "mv data/zshrc.new ~/.zshrc",
        "mv data/envrc .envrc",
        "ln -s data/envrc ./.envrc",
        "ditto data/envrc .envrc",
        "cp .env.example .env",
        "cp -f data/env.txt \"$CLAUDE_PROJECT_DIR/.env\"",
        "install -m 600 data/env.txt .env",
        "rsync data/env.txt ./.env",
    ]
    # ... and copies FROM them, or onto a file whose name only begins like one (.env.bak,
    # .zshrc.bak - READS already pins cp ~/.zshrc ~/.zshrc.bak silent)
    STARTUP_COPIES_NOT_WRITES = [
        "cp .env.example .env.bak",
        "cp ~/.bashrc ~/.bashrc.bak",
        "cp .envrc .envrc.bak",
        "rsync -a ~/.zshrc data/zshrc.txt",
        "ln -s ~/.zprofile data/zprofile-link",
        "mv ~/.zshrc.bak ~/.zshrc.old",
        "cp .env.example data/env-example.txt",
    ]

    def test_copying_moving_or_linking_onto_a_startup_file_is_refused_and_copying_from_one_is_not(self):
        self.assert_refused_never_asked(self.STARTUP_COPIES)
        self.assert_refused_with_every_backup(self.STARTUP_COPIES)
        self.assert_no_decision(self.STARTUP_COPIES_NOT_WRITES)

    def test_writing_a_curlrc_is_refused_in_every_mode_and_reading_one_is_not(self):
        # with no backups: refused in default, auto, plan, dontAsk, a missing mode and from a
        # subagent, never asked, each refusal logged
        self.assert_refused_never_asked(self.CURLRC_WRITES)
        # with every backup on record, GLOW_LIVE_OK set, and in the modes that allow a backed write
        self.assert_refused_with_every_backup(self.CURLRC_WRITES)
        # the other side: reading it, or copying it elsewhere - no decision, nothing logged
        self.assert_no_decision(self.CURLRC_NOT_WRITES)

    # 2. a curl config file sets the method, the URL and the data, so a curl -K names whatever host
    # its file holds: every curl -K / --config (-K<file>, --config=<file>, -K in a cluster, -K - from
    # standard input) is live with no automatic go, the host on its command line or none
    CURL_CONFIGS = {
        "data/form_delete.cfg": 'url = "https://api.jotform.com/form/261234567890123/question/7"\nrequest = "DELETE"\n',
        "data/form_post.cfg": ('url = "https://api.jotform.com/form/261234567890123/properties"\nrequest = "POST"\n'
                               'data = "properties[title]=Attendance"\n'),
        "data/props.json": '{"properties": {"title": "Attendance"}}\n',
    }
    CURL_K_NO_HOST = [
        "curl -K data/form_delete.cfg",
        "curl -sS -K data/form_post.cfg",
        "curl -Kdata/form_delete.cfg",
        "curl -sSK data/form_post.cfg",
        "curl --config data/form_delete.cfg",
        "curl --config=data/form_post.cfg -o data/out.json",
        "curl -K data/form_delete.cfg https://example.com/status",
        "curl -sS https://example.org/ping --config data/form_post.cfg",
        "curl -K - https://example.com/status < data/form_delete.cfg",
        "/usr/bin/curl -K data/form_delete.cfg",
        "cd data && curl -K form_delete.cfg",
    ]

    def test_every_curl_with_a_config_file_is_live_even_naming_no_live_host(self):
        F1 = self.F1
        p = self.project()
        for rel, text in self.CURL_CONFIGS.items():
            self.write(p, rel, text)
        self.back_up(p, "jotform", F1, f"backups/{F1}")
        self.back_up(p, "jotform", "all", "backups/all-forms")
        self.back_up(p, "github", "all", "backups/github/switches.json")
        # the control: a curl with no config file to the backed form goes through on these backups
        control = f"curl -sS -X POST https://api.jotform.com/form/{F1}/properties --data-binary @data/props.json"
        run = self.gate(control, mode="dontAsk", project=p, may_allow=True)
        self.assertEqual(self.verdict(run), "allow", "the control: a backed Jotform curl with no -K - " + self.show(run))
        # asked in default and auto, refused in dontAsk, bypassPermissions, a missing mode and from a
        # subagent, the refusal saying a config file is why; never allowed, the form's backup from
        # today notwithstanding
        self.assert_never_automatic([(c, {"may_allow": True}) for c in self.CURL_K_NO_HOST], p, saying=("config",))
        counts = collections.Counter(d for d, _ in self.lines_of(p))
        self.assertEqual(counts["ALLOWED"], 1, "only the control is allowed")
        self.assertEqual(counts["ASKED"], 2 * len(self.CURL_K_NO_HOST), "each curl -K asked in default and auto, logged")
        self.assertEqual(counts["BLOCKED"] + counts["DENIED"], 4 * len(self.CURL_K_NO_HOST),
                         "each curl -K refused headless and from a subagent, logged")
        self.assertEqual(len(self.quiet_notifications()), 1, "only the control is notified")
        # the other side: a curl with no config file to no live host, options whose names only begin
        # like --config (--connect-timeout, --compressed), and a read that mentions curl -K stay
        # silent, headless and from a subagent too
        silent = ["curl -s https://example.com/status -o data/status.json",
                  "curl --connect-timeout 5 -sS https://example.com/status",
                  "curl --compressed -s https://example.com/status",
                  "grep -rn -- 'curl -K' docs", "grep -n -- '--config' docs/RUNBOOK.md"]
        for kw in ({"mode": "default"}, {"mode": "dontAsk"}, {"mode": None}, {"mode": "auto", "agent": True}):
            self.assert_silent(silent, project=p, **kw)
        self.assertEqual(collections.Counter(d for d, _ in self.lines_of(p))["ALLOWED"], 1, "nothing more allowed")

    # 3. a source-tracked push or deploy deploys local DELETIONS too, which the gate cannot see:
    # sfdx force:source:push is never automatic; sf project deploy start goes through only with an
    # explicit -d/--source-dir, -m/--metadata or -x/--manifest - without one it deploys the
    # project's tracked changes. Each below names the plan folder, whose before/ is from today
    SOURCE_TRACKED = [
        "sfdx force:source:push",
        "sfdx force:source:push -u glow",
        "sfdx force:source:push -f -u glow -w 33 data/sf_x/after",
        "sfdx force:source:push -u glow --json -w 33 data/sf_x/after/main",
        "sf force:source:push -o glow data/sf_x/after",
        "sfdx force:source:push -u glow -d data/sf_x/after",
        "sfdx force:source:push -u glow --source-dir data/sf_x/after",
        "sf project deploy start -o glow",
        "sf project deploy start --target-org glow --wait 30",
        "sf project deploy start -o glow --results-dir data/sf_x/after/results",
        "sf project deploy start --ignore-conflicts -o glow --junit --results-dir data/sf_x/tests",
        "sf project deploy start -o glow --coverage-formatters json --results-dir data/sf_x/after --wait 30",
        "sfdx project deploy start -o glow --results-dir data/sf_x/after",
        "sf deploy metadata -o glow --results-dir data/sf_x/after",
    ]
    # ... and with an explicit source: the automatic go on the same before/ (the deploys of the
    # first rounds keep theirs)
    EXPLICIT_SOURCE = [
        "sf project deploy start --source-dir data/sf_x/after -o glow",
        "sf project deploy start -d data/sf_x/after -o glow",
        # -d joined to its folder is the same explicit source (orchestrator's ruling, 2026-11-06)
        "sf project deploy start -ddata/sf_x/after -o glow",
        "sf project deploy start --source-dir=data/sf_x/after --target-org glow",
        "sf project deploy start -x data/sf_x/after/package.xml -o glow",
        "sf project deploy start --manifest data/sf_x/after/package.xml -o glow",
        "sf project deploy start --manifest=data/sf_x/after/package.xml -o glow",
        "sf project deploy start -m Report:Glow/Attendance -o glow --results-dir data/sf_x/after",
        "sf project deploy start --metadata Report:Glow/Attendance --results-dir data/sf_x/after/results -o glow",
        "sf project deploy start --metadata=Report:Glow/Attendance -d data/sf_x/after -o glow",
    ]

    def test_a_source_tracked_push_or_deploy_without_an_explicit_source_is_never_automatic(self):
        p = self.sf_plan({"data/sf_x/after/main/default/reports/Attendance.report-meta.xml": "<Report/>\n",
                          "data/sf_x/after/package.xml": "<Package/>\n"})
        plan = os.path.join(p, "data", "sf_x")
        # the other side first: an explicit source goes through on the before/ from today, in a main
        # session's modes and from a subagent, each logged ALLOWED and notified
        callers = [{"mode": "default"}, {"mode": "auto"}, {"mode": "dontAsk"}, {"mode": None},
                   {"mode": "auto", "agent": True}]
        cases = [(command, dict(caller, project=p, may_allow=True)) for command in self.EXPLICIT_SOURCE for caller in callers]
        for command, kw, run in self.verdicts(cases):
            with self.subTest(command=command, mode=kw["mode"], agent=kw.get("agent"), side="explicit source"):
                self.assertEqual(self.verdict(run), "allow", self.show(run))
        allowed = len(cases)
        self.assertEqual(collections.Counter(d for d, _ in self.lines_of(p))["ALLOWED"], allowed,
                         "each explicit-source deploy logged ALLOWED")
        self.assertEqual(len(self.notifications(allowed)), allowed, "each explicit-source deploy notified")
        # a push, or a deploy with no -d, -m or -x - also run from the plan folder itself: asked in
        # default and auto, refused where no prompt can show; never allowed
        commands = ([(c, {"may_allow": True}) for c in self.SOURCE_TRACKED]
                    + [("sfdx force:source:push -u glow", {"may_allow": True, "cwd": plan}),
                       ("sf project deploy start -o glow", {"may_allow": True, "cwd": plan})])
        self.assert_never_automatic(commands, p)
        counts = collections.Counter(d for d, _ in self.lines_of(p))
        self.assertEqual(counts["ALLOWED"], allowed, "a push or a deploy with no explicit source was allowed")
        self.assertEqual(counts["ASKED"], 2 * len(commands), "each asked in default and auto, logged")
        self.assertEqual(counts["BLOCKED"] + counts["DENIED"], 4 * len(commands),
                         "each refused headless and from a subagent, logged")
        self.assertEqual(len(self.quiet_notifications()), allowed, "only the explicit-source deploys are notified")

    def test_a_deploy_without_an_explicit_source_is_refused_saying_which_flag_it_needs(self):
        # headless, the refusal names what makes the deploy automatic: an explicit source
        p = self.sf_plan()
        for command in ("sf project deploy start -o glow --results-dir data/sf_x/after",
                        "sf project deploy start -o glow"):
            for kw in ({"mode": "dontAsk"}, {"mode": "auto", "agent": True}):
                with self.subTest(command=command, **kw):
                    run = self.gate(command, project=p, may_allow=True, **kw)
                    self.assertEqual(self.verdict(run), "deny", self.show(run))
                    message = (run.err + self.reason(run)).lower()
                    self.assertTrue(any(s in message for s in ("--source-dir", "--manifest", "--metadata")),
                                    f"the refusal does not name the explicit source it needs: {message!r}")

    def clasp_project(self):
        """A checkout whose appsscript/, drive-sync/ (the Drive photo mover, with its own .clasp.json)
        and appsscript-old/ are committed, every .clasp.json ignored as in the repository: all clean."""
        p = self.project(git=True)
        self.write(p, ".gitignore", ".clasp.json\n")
        for folder in ("appsscript", "drive-sync", "appsscript-old"):
            self.write(p, f"{folder}/.clasp.json", json.dumps({"scriptId": f"fictional-{folder}", "rootDir": "."}) + "\n")
        self.write(p, "drive-sync/Mover.gs", "function moveFolder() {}\n")
        self.write(p, "drive-sync/appsscript.json", '{"timeZone": "Etc/UTC"}\n')
        self.write(p, "appsscript-old/Code.gs", "function onEdit(e) {}\n")
        self.git(p, "add", "-A")
        self.git(p, "commit", "-q", "-m", "the other clasp projects")
        return p

    def test_clasp_push_goes_through_only_from_the_folder_it_pushes(self):
        # F2: clasp pushes the .clasp.json project of the Bash tool's working folder - the input's
        # cwd, which persists between calls. npx clasp push and clasp push are automatic only when
        # cwd resolves (a link, a trailing /, a .. followed) to <project>/appsscript; npm run
        # clasp:push, which goes there itself, only when it resolves to <project>. drive-sync/ (the
        # photo mover: never automatic), any other folder, a missing cwd, or a -P/--project/--rootDir
        # flag: not automatic - asked, refused where no prompt can show - appsscript/ clean and
        # committed notwithstanding
        p = self.clasp_project()
        appsscript = os.path.join(p, "appsscript")
        linked_appsscript = os.path.join(self.side.name, "aliased-appsscript")
        linked_project = os.path.join(self.side.name, "aliased-checkout")
        os.symlink(appsscript, linked_appsscript)
        os.symlink(p, linked_project)
        go = [("npx clasp push -f", appsscript), ("clasp push", appsscript), ("npx clasp push", appsscript + os.sep),
              ("npx clasp push -f", os.path.realpath(appsscript)),
              ("clasp push -f", os.path.join(p, "drive-sync", "..", "appsscript")),
              ("npx clasp push -f", linked_appsscript),
              ("npm run clasp:push", p), ("npm run clasp:push", os.path.realpath(p)), ("npm run clasp:push", linked_project),
              ("npm run clasp:push -- --force", p + os.sep)]
        callers = [{"mode": "default"}, {"mode": "dontAsk"}, {"mode": None}, {"mode": "auto", "agent": True}]
        runs = [(command, dict(caller, project=p, cwd=cwd, may_allow=True)) for command, cwd in go for caller in callers]
        head = self.head(p)[:7]
        for command, kw, run in self.verdicts(runs):
            with self.subTest(command=command, cwd=kw["cwd"], mode=kw["mode"], agent=kw.get("agent")):
                self.assertEqual(self.verdict(run), "allow", self.show(run))
                self.assertIn(f"appsscript/ at HEAD {head}", self.reason(run), "the reason does not name the commit")
        other = self.project(git=True)                  # another checkout, its appsscript/ clean and committed too
        drive = os.path.join(p, "drive-sync")
        self.assert_never_automatic([
            ("npx clasp push -f", {"cwd": drive}), ("clasp push", {"cwd": drive}),
            ("npx clasp push -f", {"cwd": p}), ("clasp push -f", {"cwd": p}),
            ("npx clasp push -f", {"cwd": os.path.join(p, "appsscript-old")}),
            ("npx clasp push -f", {"cwd": os.path.join(other, "appsscript")}),
            ("npx clasp push -f", {"cwd": os.path.join(p, "no-such-folder")}),
            ("npx clasp push -f", {"cwd": self.NO_CWD}), ("clasp push", {"cwd": self.NO_CWD}),
            ("npx clasp push -f", {"cwd": ""}), ("npx clasp push -f", {"extra": {"cwd": None}}),
            ("npm run clasp:push", {"cwd": appsscript}), ("npm run clasp:push", {"cwd": drive}),
            ("npm run clasp:push", {"cwd": other}), ("npm run clasp:push", {"cwd": self.NO_CWD}),
            ("npx clasp push -f -P ../drive-sync", {"cwd": appsscript}),
            ("clasp push --project ../drive-sync/.clasp.json", {"cwd": appsscript}),
            ("npx clasp push -f --project=../drive-sync/.clasp.json", {"cwd": appsscript}),
            ("npx clasp push --rootDir ../drive-sync", {"cwd": appsscript}),
            ("clasp push -f --rootDir=../drive-sync", {"cwd": appsscript}),
            ("npm run clasp:push -- -P drive-sync/.clasp.json", {"cwd": p}),
            ("npm run clasp:push -- --rootDir drive-sync", {"cwd": p}),
        ], p, light=True)
        counts = collections.Counter(d for d, _ in self.lines_of(p))
        self.assertEqual(counts["ALLOWED"], len(runs), "only the pushes from appsscript/ (npm run: the checkout) are allowed")

    # F5: a redirect writes the records only when its target is them (> >> &> then the path); a read
    # that sends its errors or output elsewhere is no forgery, and neither is a query or an export
    # saved into a plan's before/ - the backup itself (absolute paths assembled: make check's
    # docs-links refuses literal ones)
    TMP_X = os.path.join(os.sep, "tmp", "x.txt")
    TMP_ALL = os.path.join(os.sep, "tmp", "all_records.txt")
    TMP_CUT = os.path.join(os.sep, "tmp", "targets.txt")
    LOG_READS_REDIRECTED = ["tail -5 .claude/live_backups.log 2>/dev/null",
                            f"grep jotform .claude/live_backups.log > {TMP_X}",
                            "cat .claude/live_backups.log 2>&1",
                            "grep -c sheet .claude/live_backups.log 2> /dev/null",
                            "wc -l .claude/live_backups.log > data/count.txt",
                            f"cat .claude/live_backups.log >> {TMP_ALL}",
                            f"cut -f2 .claude/live_backups.log > {TMP_CUT} 2>&1"]
    BEFORE_SAVED = ["sf data query -q \"SELECT Id FROM Account\" -o glow > data/sf_x/before/accounts.csv",
                    "sf data query -q \"SELECT Id, Name FROM Contact\" -r csv -o glow > data/sf_y/before/contacts.csv",
                    "sfdx data query -q \"SELECT Id FROM Account\" -o glow > data/sf_x/before/accounts.csv",
                    "sf data query --file data/sf_x/q.soql --result-format csv -o glow >> data/sf_x/before/main/contacts.csv",
                    "sf data export tree -q \"SELECT Id, Name FROM Account\" --output-dir data/sf_x/before -o glow",
                    "sf data export bulk -q \"SELECT Id FROM Contact\" --output-file data/sf_x/before/contacts.csv -o glow",
                    "sf project retrieve start -m Report:Attendance --target-dir data/sf_x/before -o glow --json "
                    "> data/sf_x/before/retrieve.json"]
    # ... and still forgeries: a redirect whose target is the records, whatever 2>/dev/null or 2>&1
    # stands beside it and when the same command reads them; a before/ written by anything but a
    # query, an export or a retrieve (a write's output, a copy by redirect, a query chained to a
    # forged file)
    LOG_REDIRECTS = ["grep x a.txt > .claude/live_backups.log",
                     "cat a >> .claude/live_backups.log 2>/dev/null",
                     "echo x &> .claude/live_backups.log",
                     "echo x &>> .claude/live_backups.log",
                     "tail -5 .claude/live_backups.log > .claude/live_backups.log",
                     "cat .claude/live_backups.log 2>/dev/null >> .claude/live_backups.log",
                     "printf x 2>&1 >>.claude/live_backups.log",
                     "printf x 1> ./.claude/live_backups.log",
                     "printf x >| .claude/live_backups.log",
                     "grep x a.txt 2>/dev/null > \"$CLAUDE_PROJECT_DIR\"/.claude/live_backups.log",
                     f"grep jotform {TMP_X} > .claude/live_backups.log 2>&1",
                     "cat a 2>/dev/null >> .claude/LIVE_BACKUPS.log"]
    BEFORE_FORGED = ["cat data/sf_x/after/a.xml > data/sf_x/before/a.xml",
                     "sf data query -q \"SELECT Id FROM Account\" -o glow; echo x > data/sf_x/before/a.xml",
                     "echo sf data query > data/sf_x/before/a.xml",
                     "sf data update record -s Account -i 001000000000001 -v \"Name=X\" -o glow > data/sf_x/before/out.txt",
                     "sf data query -q \"SELECT Id FROM Account\" -o glow > data/sf_x/before/a.csv && touch data/sf_x/before/b.xml",
                     "python3 tools/x.py > data/sf_x/before/a.csv"]

    def test_a_read_of_the_records_or_a_query_saved_into_before_is_no_forgery(self):
        # F5: no decision and nothing logged - with no backups (default, dontAsk, a missing mode, a
        # subagent) and with every backup on record
        commands = self.LOG_READS_REDIRECTED + self.BEFORE_SAVED
        self.assert_no_decision(commands)
        p = self.fully_backed()
        for kw in ({"mode": "auto"}, {"mode": "dontAsk"}, {"mode": "auto", "agent": True}):
            self.assert_silent(commands, project=p, **kw)
        self.assertEqual(self.lines_of(p), [], "nothing live: nothing logged")
        self.assertEqual(self.quiet_notifications(), [])

    def test_a_redirect_into_the_records_or_a_hand_made_before_is_refused_saying_what_to_run_instead(self):
        # F5, the other side: refused in every mode and from a subagent, never asked, with no backups
        # and with every backup on record. The refusal says what to rephrase: a read without
        # redirecting into the records; a before/ taken with sf project retrieve start, or a sf data
        # query saved there
        commands = self.LOG_REDIRECTS + self.BEFORE_FORGED
        self.assert_refused_never_asked(commands)
        p = self.fully_backed()
        self.assert_denies(commands, mode="auto", project=p)
        self.assertNotIn("ALLOWED", [d for d, _ in self.lines_of(p)])
        for command, run in self.runs(self.LOG_REDIRECTS, mode="default"):
            with self.subTest(command=command, check="how to read"):
                message = (run.err + "\n" + self.reason(run)).lower()
                self.assertIn("redirect", message, "the refusal does not say how to read without redirecting into the records")
                self.assertRegex(message, r"\bread", "the refusal does not say how to read the records")
        for command, run in self.runs(self.BEFORE_FORGED + ["echo x > data/sf_x/before/a.xml"], mode="default"):
            with self.subTest(command=command, check="how to take a before/"):
                message = run.err + "\n" + self.reason(run)
                for needle in ("sf project retrieve start", "sf data query"):
                    self.assertIn(needle, message, f"the refusal does not name {needle!r} for a before/")

    # ---- live_gate.sh: ticket #204 (Ryan, 2026-11-04: "no prompt unless it is a destructive one"). What
    # changes nothing live passes with no prompt and no backup - a hook's allow - in every mode #146
    # allows a backed write in, and from a subagent: a dashboard refresh (PUT, no body or an empty {} one,
    # on /analytics/dashboards/<id>) and its read (a GET of the dashboard or of its /status), a
    # check-only deploy (--dry-run, validate) and a SOQL query. Ruling (test-author, #204): plan mode and
    # an unknown mode never get the automatic go, as for a backed write; plan mode, where a prompt can
    # show, never refuses one either. Fictional ids: a dashboard's starts 01Z, 15 or 18 characters
    D1, D2, D3, D4 = "01Z5g000000AbCdEAF", "01Z5g000000XyZw", "01Z8c00000017QrSTU", "01ZKz000000hJ2mAAE"
    REFRESHES = [
        f"sf api request rest /services/data/v60.0/analytics/dashboards/{D1} -X PUT -b '{{}}' -o glow",
        f"sf api request rest /services/data/v62.0/analytics/dashboards/{D2} --method PUT --body '{{}}' --target-org glow",
        f"sf api request rest '/services/data/v61.0/analytics/dashboards/{D3}' -X PUT",
        f"sf api request rest /services/data/v58.0/analytics/dashboards/{D4} --method=PUT --body={{}} -o glow",
        f"sf api request rest \"/services/data/v60.0/analytics/dashboards/{D2}\" -XPUT -b \"{{}}\"",
        f"sf api request rest --method PUT --body '{{}}' -o glow /services/data/v59.0/analytics/dashboards/{D3}",
        f"sfdx api request rest /services/data/v60.0/analytics/dashboards/{D4} -X PUT -b '{{}}' -o glow",
    ]
    REFRESH_READS = [
        f"sf api request rest /services/data/v60.0/analytics/dashboards/{D1}/status -o glow",
        f"sf api request rest /services/data/v62.0/analytics/dashboards/{D2} -X GET --target-org glow",
        f"sf api request rest '/services/data/v61.0/analytics/dashboards/{D3}/status' --method GET",
        f"sf api request rest /services/data/v60.0/analytics/dashboards/{D4}",
    ]
    CHECK_ONLY = [
        "sf project deploy start --dry-run --source-dir data/sf_dash_x/build/force-app -o glow",
        "sf project deploy start -d data/sf_tiles_2026-11-19/build --dry-run --target-org glow --wait 30",
        "sf project deploy start --manifest data/sf_dash_x/build/package.xml --dry-run -o glow",
        "sf project deploy start --dry-run -m Dashboard:Glow/Attendance -o glow",
        "sf project deploy start --source-dir=data/sf_tiles_2026-11-19/build --dry-run --json -o glow",
        "sfdx project deploy start --dry-run -d data/sf_dash_x/build/force-app -o glow",
        "sf project deploy validate --source-dir data/sf_dash_x/build/force-app -o glow",
        "sf project deploy validate -x data/sf_dash_x/build/package.xml --test-level RunLocalTests -o glow",
        "sf project deploy validate -m ApexClass:GlowSync --test-level RunSpecifiedTests --tests GlowSyncTest --target-org glow",
    ]
    QUERIES = [
        "sf data query -q 'SELECT Id, Title FROM Dashboard' -o glow",
        "sf data query --query \"SELECT Id FROM Account WHERE Name = 'Sunrise Club'\" --target-org glow --json",
        "sf data query -q 'SELECT COUNT() FROM Attendance_Batch__c' -r csv -o glow",
        "sfdx data query -q 'SELECT Id, Name FROM Report' -o glow",
        "sf data query --file data/sf_dash_x/q.soql -o glow",
        "sf data query -q 'SELECT Id, Name FROM ApexClass' --use-tooling-api -o glow",
        # saved into a plan's before/: the backup a later write goes through on (#146)
        "sf data query -q 'SELECT Id, Title FROM Dashboard' -r csv --output-file data/sf_dash_x/before/dashboards.csv -o glow",
    ]
    # Apex that only calls itself a dry run (a savepoint rolled back): the gate cannot tell one from its
    # file, so sf apex run stays as #146 left it (Ruling, #204) - automatic only on its plan's before/
    DRY_RUN_APEX = ("Boolean dryRun = true;\nSavepoint sp = Database.setSavepoint();\n"
                    "List<Contact> cs = [SELECT Id, FirstName FROM Contact WHERE Club__c = 'Sunrise Club'];\n"
                    "for (Contact c : cs) { c.FirstName = c.FirstName.trim(); }\nupdate cs;\n"
                    "if (dryRun) { Database.rollback(sp); }\n")

    def assert_passes(self, commands, project):
        """Each command allowed - no prompt - with no backup in `project`: in default, auto and the
        headless modes (dontAsk, bypassPermissions, a missing mode), and from a subagent; never allowed
        in plan mode or an unknown mode, and never refused in plan mode. One batch."""
        callers = [{"mode": m} for m in ["default", "auto"] + self.HEADLESS] + [{"mode": "auto", "agent": True}]
        never = [{"mode": "plan"}, {"mode": "foo"}]
        cases = [(command, dict(caller, project=project, may_allow=True)) for command in commands
                 for caller in callers + never]
        for command, kw, run in self.verdicts(cases):
            with self.subTest(command=command, mode=kw["mode"], agent=kw.get("agent")):
                if kw["mode"] in ("plan", "foo"):
                    self.assertNotEqual(self.verdict(run), "allow", "the automatic go in plan or an unknown mode - "
                                        + self.show(run))
                    if kw["mode"] == "plan":
                        self.assertNotEqual(self.verdict(run), "deny", "plan mode can show a prompt - " + self.show(run))
                else:
                    self.assertEqual(self.verdict(run), "allow", self.show(run))

    def assert_not_allowed(self, commands, project):
        """Each command never allowed - default, dontAsk, a missing mode, a subagent in auto: asked,
        refused or no decision, as before #204."""
        callers = [{"mode": "default"}, {"mode": "dontAsk"}, {"mode": None}, {"mode": "auto", "agent": True}]
        cases = [(command, dict(caller, project=project, may_allow=True)) for command in commands for caller in callers]
        for command, kw, run in self.verdicts(cases):
            with self.subTest(command=command, mode=kw["mode"], agent=kw.get("agent")):
                self.assertNotEqual(self.verdict(run), "allow", self.show(run))

    def refresh_lookalikes(self):
        """(never automatic, deletes, never allowed) beside a refresh: what #146 asks on, or refuses
        where no prompt can show; the deletes it calls deletes; reads that are no plain one."""
        D1, D2 = self.D1, self.D2
        dash = f"/services/data/v60.0/analytics/dashboards/{D1}"
        refresh = f"sf api request rest {dash} -X PUT -b '{{}}' -o glow"
        patch = ("sf api request rest /services/data/v60.0/sobjects/Account/001000000000001 -X PATCH "
                 "-b '{\"Name\": \"Rising Stars Club\"}' -o glow")
        never = [
            # a body that is not empty: a refresh with filters too
            f"sf api request rest {dash} -X PUT -b '{{\"filters\": []}}' -o glow",
            f"sf api request rest /services/data/v60.0/analytics/dashboards/{D2} --method PUT --body '{{\"Name\": \"Club Attendance\"}}'",
            # the body or the request from a file, standard input or a flags folder
            f"sf api request rest {dash} -X PUT --body @data/sf_x/refresh.json -o glow",
            f"sf api request rest {dash} -X PUT -b - -o glow < data/sf_x/refresh.json",
            f"sf api request rest {dash} -X PUT --body=- -o glow",
            f"sf api request rest {dash} --file data/sf_x/req.json -o glow",
            f"sf api request rest {dash} -X PUT -b '{{}}' --flags-dir data/sf_x/flags -o glow",
            # a second body, method or URL beside the empty PUT
            f"sf api request rest {dash} -X PUT -b '{{}}' --body '{{\"Name\": \"Club Attendance\"}}' -o glow",
            f"sf api request rest {dash} -X PUT -X PATCH -b '{{}}' -o glow",
            f"sf api request rest {dash} /services/data/v60.0/sobjects/Account/001000000000001 -X PUT -b '{{}}' -o glow",
            # another method on the dashboard: PATCH saves it, POST clones it
            f"sf api request rest {dash} -X PATCH -b '{{}}' -o glow",
            f"sf api request rest /services/data/v60.0/analytics/dashboards/{D2} --method POST -b '{{}}' -o glow",
            # another path, or the dashboard's path leading elsewhere
            "sf api request rest /services/data/v60.0/analytics/reports/00O5g000000AbCdEAF -X PUT -b '{}' -o glow",
            "sf api request rest /services/data/v60.0/sobjects/Account/001000000000001 -X PUT -b '{}' -o glow",
            "sf api request rest /services/data/v60.0/analytics/dashboards -X PUT -b '{}' -o glow",
            f"sf api request rest {dash}/status -X PUT -b '{{}}' -o glow",
            f"sf api request rest {dash}/../../sobjects/Account/001000000000001 -X PUT -b '{{}}' -o glow",
            f"sf api request rest {dash}%2F..%2F..%2Fsobjects%2FAccount%2F001000000000001 -X PUT -b '{{}}' -o glow",
            f"sf api request rest '{dash}?_HttpMethod=PATCH' -X PUT -b '{{}}' -o glow",
            f"sf api request rest {dash} -X PUT -b '{{}}' -H 'X-HTTP-Method-Override: PATCH' -o glow",
            # the same refresh by curl: no pass of its own
            f"curl -sS -X PUT https://example.my.salesforce.com{dash} -d '{{}}'",
            # chained, piped, on two lines, behind a wrapper or an assignment
            f"{refresh} && {patch}", f"{refresh}; echo done", f"{refresh} | tee data/sf_x/after/refresh.json",
            f"{refresh}\n{patch}", f"bash -c \"{refresh}\"", f"env {refresh}", f"time {refresh}", f"nohup {refresh}",
            f"SF_TARGET_ORG=glow {refresh}",
            f"sf api request rest {dash}/status -o glow && python3 tools/auto_sync.py --apply",
        ]
        deletes = [
            f"sf api request rest {dash} -X DELETE -o glow",
            f"sf api request rest {dash} -X PUT -b '{{}}' -H 'X-HTTP-Method-Override: DELETE' -o glow",
            f"sf api request rest '{dash}?_HttpMethod=DELETE' -X PUT -o glow",
            f"{refresh} && sf data delete record -s Contact -i 003000000000001 -o glow",
        ]
        reads = [
            f"sf api request rest {dash}/status -o glow | tee data/sf_x/after/status.json",
            f"bash -c 'sf api request rest {dash}/status -o glow'",
            f"env sf api request rest {dash} -o glow",
            f"sf api request rest {dash}/status -o glow\nsf api request rest {dash} -o glow",
            # the response written into the backup records or a startup file
            f"sf api request rest {dash}/status -S .claude/live_backups.log -o glow",
            f"sf api request rest {dash} --stream-to-file ~/.zshrc -o glow",
            f"sf api request rest {dash} -X PUT -b '{{}}' --stream-to-file ~/.curlrc -o glow",
        ]
        return never, deletes, reads

    def test_a_dashboard_refresh_and_its_status_pass_with_no_prompt_and_nothing_like_them_does(self):
        # DoD: a refresh PUT with an empty body passes with no prompt in auto, default and headless
        # modes, and from a subagent - in a project with no backup at all - and so does the GET that
        # follows it. A PUT with a body, another method, path or header, a request from a file, a curl,
        # a chain or a wrapper is judged by #146's rules as before: asked, or refused where no prompt
        # can show; a DELETE as a delete; a read that is no plain one is never allowed
        p = self.project()
        self.assert_passes(self.REFRESHES + self.REFRESH_READS, p)
        never, deletes, reads = self.refresh_lookalikes()
        self.assert_never_automatic([(c, {"may_allow": True}) for c in never], p, light=True)
        self.assert_delete_class([("a DELETE on or beside the dashboard", c, p) for c in deletes])
        self.assert_not_allowed(reads, p)

    def check_only_lookalikes(self):
        """(never automatic, deletes, never allowed, refused) beside a check-only deploy or a query."""
        build = "data/sf_dash_x/build/force-app"
        query = "sf data query -q 'SELECT Id FROM Account' -o glow"
        dash = f"/services/data/v60.0/analytics/dashboards/{self.D1}"
        never = [
            # a deploy (no before/ here, so it asks), and a quick deploy, which deploys the job a validate
            # left - --dry-run in its text notwithstanding
            f"sf project deploy start --source-dir {build} -o glow",
            "sf project deploy quick --job-id 0Af000000000001 -o glow",
            "sf project deploy quick --use-most-recent --dry-run -o glow",
            # --dry-run only inside another flag's value: a real deploy
            f"sf project deploy start -d {build} --test-level RunSpecifiedTests --tests \"GlowSyncTest --dry-run\" -o glow",
            # a metadata folder, or the flags from a folder, beside --dry-run or validate (#146: never automatic)
            "sf project deploy start --dry-run --metadata-dir data/sf_dash_x/mdapi -o glow",
            "sf project deploy validate --metadata-dir data/sf_dash_x/mdapi -o glow",
            f"sf project deploy start --dry-run -d {build} --flags-dir data/sf_dash_x/flags -o glow",
            # chained, piped, behind a wrapper or an assignment
            f"sf project deploy start --dry-run -d {build} -o glow && sf project deploy start -d {build} -o glow",
            f"sf project deploy validate -d {build} -o glow && sf project deploy quick --use-most-recent -o glow",
            f"sf project deploy validate -d {build} -o glow | tee data/sf_dash_x/after/validate.txt",
            f"time sf project deploy start --dry-run -d {build} -o glow",
            f"SF_TARGET_ORG=glow sf project deploy validate -d {build}",
            f"bash -c 'sf project deploy start --dry-run -d {build} -o glow'",
            # a query chained to a write, or carrying a live flag
            f"{query} && sf data update record -s Account -i 001000000000001 -v \"Name='Rising Stars Club'\" -o glow",
            f"{query} | sf data upsert bulk -s Account -f - -i Id -o glow",
            "sf data query -q \"SELECT Id FROM Account WHERE Name = 'Rising --apply'\" -o glow",
            f"{query} --rehearse",
            # a live command whose text only mentions a pass
            "python3 sync_attendance_form.py data/roster.csv --roster --region Africa --form 1 --apply --note 'sf data query'",
            "sf data update record -s Account -i 001000000000001 -v \"Description='sf data query --dry-run'\" -o glow",
            "gh variable set SF_SYNC --body 'sf project deploy validate'",
            "python3 tools/auto_sync.py --apply-salesforce --label 'sf project deploy start --dry-run'",
            # Apex that calls itself a dry run, with no before/ from today
            "sf apex run --file data/sf_dash_x/dry_run.apex -o glow",
        ]
        deletes = [
            f"sf project deploy start --dry-run -d {build} --post-destructive-changes "
            "data/sf_dash_x/build/destructiveChangesPost.xml -o glow",
            "sf project deploy validate --manifest data/sf_dash_x/build/package.xml --pre-destructive-changes "
            "data/sf_dash_x/build/destructiveChanges.xml -o glow",
            "sf project deploy start --dry-run -d data/sf_gone/build -o glow",
            "sf project deploy validate --source-dir data/sf_gone/build -o glow",
            f"{query}; sf data delete record -s Contact -i 003000000000001 -o glow",
            f"{query} --prune",
        ]
        not_allowed = [
            "sf data query -q 'SELECT Id FROM Account' -r csv --output-file .claude/live_backups.log -o glow",
            "sf data query -q 'SELECT Id FROM Account' -r csv --output-file ~/.zshrc -o glow",
            "sf data query -q \"$(cat data/sf_dash_x/q.soql)\" -o glow",
            f"{query} | tee data/sf_dash_x/after/accounts.csv",
            f"{query}\n{query}", f"env {query}", f"bash -c \"{query}\"",
        ]
        refused = [
            f"{query} > ~/.zshrc",
            f"{query} > .claude/live_backups.log",
            f"sf api request rest {dash}/status -o glow >> .claude/live_backups.log",
            f"sf project deploy start --dry-run -d {build} -o glow > data/sf_dash_x/before/a.xml",
            f"sf api request rest {dash} -X PUT -b '{{}}' -o glow | tee data/sf_dash_x/before/refresh.json",
        ]
        return never, deletes, not_allowed, refused

    def test_a_check_only_deploy_or_a_query_passes_with_no_prompt_and_nothing_like_them_does(self):
        # DoD: a check-only deploy (--dry-run, validate) and an sf data query pass with no prompt - in
        # every mode a backed write passes in, from a subagent, with no backup at all (the plan folders
        # here have no before/). A deploy, a quick deploy, --dry-run beside a metadata folder or inside a
        # value, a chain, a wrapper, a query chained to a write or carrying a live flag, and a live
        # command that only mentions a pass are judged by #146's rules: asked, or refused where no prompt
        # can show; destructive changes, a delete or --prune beside a check are deletes; a query whose
        # output is the backup records or a startup file is never allowed; a self-approval is refused
        p = self.project()
        files = {"data/sf_dash_x/build/force-app/main/default/dashboards/Glow/Attendance.dashboard-meta.xml": "<Dashboard/>\n",
                 "data/sf_dash_x/build/package.xml": "<Package/>\n",
                 "data/sf_tiles_2026-11-19/build/main/default/reports/Glow/Attendance.report-meta.xml": "<Report/>\n",
                 "data/sf_dash_x/q.soql": "SELECT Id, Title FROM Dashboard\n",
                 "data/sf_dash_x/dry_run.apex": self.DRY_RUN_APEX,
                 "data/sf_gone/build/destructiveChanges.xml": "<Package/>\n",
                 "data/sf_gone/build/main/default/reports/Old.report-meta.xml": "<Report/>\n"}
        for rel, text in files.items():
            self.write(p, rel, text)
        self.assert_passes(self.CHECK_ONLY + self.QUERIES, p)
        never, deletes, not_allowed, refused = self.check_only_lookalikes()
        self.assert_never_automatic([(c, {"may_allow": True}) for c in never], p, light=True)
        self.assert_delete_class([("destructive changes, a delete or --prune beside a check", c, p) for c in deletes])
        self.assert_not_allowed(not_allowed, p)
        self.assert_refused_never_asked(refused)

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


class GateSettings(unittest.TestCase):
    """.claude/settings.json, the second layer behind live_gate.sh: the rules read as Claude Code
    reads them (research on 2.1.299, 2026-10-14): Bash(x:*) is Bash(x *), which needs a word
    break after x - x alone or x, a space and anything (Bash(gh api repos/:*) never matched a real
    call, nor Bash(npm run clasp:*) npm run clasp:push); any other * stands for any text; a rule
    without * is the whole command. Since #146 (2026-10-26) ask rules stand only in front of the
    deletes: a hook's allow does not get past one. Since #204 the Read ask rules - gitignore patterns,
    read as node-ignore reads them - stand only on the personal data, and HARNESS_SENSITIVE_PATHS (read
    as the Harness reads it) marks the same. And the hook entries."""

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

    # the harness's resume reads: allowed and never asked - an ask rule stalls them in a dispatched
    # run (Ryan, 2026-10-14, "prompt, don't parse"); the hook asks on the live gh api calls
    LOOP_READS = ["gh api --paginate repos/o/r/pulls/36/reviews", "gh api repos/o/r/pulls/36/reviews/7/comments",
                  "gh api repos/o/r/pulls/36/reviews"]
    # whatever the call, settings neither ask nor refuse it: the hook decides
    GH_API_OTHERS = ["gh api graphql -f query='query { viewer { login } }'", "gh api user", "gh api",
                     "gh api -X DELETE repos/o/r/labels/x", "gh api repos/o/r/issues -f title=x",
                     "gh api --paginate repos/o/r/issues", "gh api repos/o/r/actions/variables",
                     "gh api -X PATCH repos/o/r/actions/variables/X -f value=true"]
    # what a session issues without a prompt: never behind an ask rule (gh pr and gh issue carry
    # the PR and issue bodies, heredocs included)
    PLAIN = ["gh pr view 36 --json state", "gh issue list", "gh run list", "gh variable list", "gh secret list",
             "gh pr create --title x --body-file -", "gh issue comment 36 --body x", "gh pr comment 41 --body x",
             "gh workflow list", "gh workflow view auto-sync.yml", "harness-board show 36 --markdown",
             "git status", "make check", "scripts/verify.sh", "python3 tools/auto_sync.py",
             "python3 sync_attendance_form.py roster.csv --roster --region Africa --form 1",
             "grep -n -- '--apply' docs/RUNBOOK.md", "sf org list",
             "sf data query -q 'SELECT Id FROM Account' -o glow", "sf project retrieve start -m ApexClass:GlowSync",
             # the deploy verbs that only read (review of 253135b: Bash(sf project deploy:*) asked on them)
             "sf project deploy report --job-id 0Af000000000001",
             "sf project deploy preview --source-dir force-app -o glow"]
    # the live families the hook may now let through on a backup from today (ticket #146): the
    # sync's switches on GitHub, the Apps Script push, the Salesforce deploys, data writes and
    # anonymous Apex. No ask rule may stand in front of them - "a matching ask rule still prompts
    # even when the hook returned allow", and in dontAsk or headless it denies - nor a deny rule;
    # the hook alone asks (or refuses) when the backup is missing
    AUTO_FAMILIES = ["gh variable set SF_SYNC --body apply", "gh secret set JOTFORM_API_KEY",
                     "gh workflow run auto-sync.yml -f apply=true", "gh workflow enable auto-sync.yml",
                     "gh workflow disable auto-sync.yml", "gh run rerun 1234",
                     "npx clasp push -f", "npx clasp push", "npm run clasp:push", "npm run clasp:push -- --force",
                     "sf project deploy start --source-dir data/sf_x/after -o glow",
                     "sf project deploy quick --job-id 0Af000000000001 -o glow",
                     "sf project deploy validate --source-dir data/sf_x/after -o glow",
                     "sf project deploy resume --job-id 0Af000000000001",
                     "sf apex run --file data/sf_x/fix.apex -o glow",
                     "sf data create record -s Account -v \"Name='Sunrise Club'\" -o glow",
                     "sf data update record -s Account -i 001000000000001 -v \"Name=X\"",
                     "sf data upsert bulk -s Contact -f data/sf_x/after/contacts.csv -i Id",
                     "sf data import tree -f data/sf_x/after/accounts.json"]
    # the deletes keep their ask rules, and get the spellings they lacked (Ryan, 2026-10-26:
    # deletes still ask). Not --prune or an HTTP DELETE: those sit anywhere in a command - the hook
    # asks on them
    DELETE_FAMILIES = ["sf data delete record -s Contact -i 003000000000001",
                       "sf data delete bulk -s Contact -f ids.csv -o glow",
                       "sf project delete source -m ApexClass:GlowSync -o glow",
                       "gh variable delete SF_SYNC", "gh secret delete GLOW_SA_JSON",
                       "gh variable remove AUTO_SYNC_APPLY", "gh secret remove GLOW_SA_JSON"]
    DELETE_RULES = ["Bash(sf data delete:*)", "Bash(gh variable delete:*)", "Bash(gh secret delete:*)",
                    "Bash(sf project delete source:*)", "Bash(gh variable remove:*)", "Bash(gh secret remove:*)"]
    # as of 2026-10-26: what the ticket leaves alone (2026-10-14's list without the clasp rules,
    # whose push is now automatic on a clean committed appsscript/). The Read rules on data/ and
    # backups/ are narrowed by #204: test_reading_a_plan_folder_asks_nothing_and_the_personal_data_still_asks
    ASK_BEFORE = ["Bash(git tag:*)", "Bash(python3 tools/derive_partner_regions.py:*)",
                  "Bash(python3 test/fixtures/make_fixture.py --write)", "Bash(make fixtures)"]
    # ticket #204: what the gate allows with no backup - a dashboard refresh and its read, a check-only
    # deploy, a query - has no ask or deny rule in front of it either: the gate is the one place a live
    # command is judged
    GATE_PASSES = ["sf api request rest /services/data/v60.0/analytics/dashboards/01Z5g000000AbCdEAF -X PUT -b '{}' -o glow",
                   "sf api request rest /services/data/v60.0/analytics/dashboards/01Z5g000000AbCdEAF/status -o glow",
                   "sf project deploy start --dry-run --source-dir data/sf_dash_x/build/force-app -o glow",
                   "sf project deploy validate --source-dir data/sf_dash_x/build/force-app -o glow",
                   "sf data query -q 'SELECT Id FROM Dashboard' -o glow"]
    # the allow list of 2026-10-26, kept whole
    ALLOW_BEFORE = ["Bash(scripts/verify.sh)", "Bash(make check)", "Bash(make test)", "Bash(make py)", "Bash(make gs)",
                    "Bash(make secrets)", "Bash(make docs-links)", "Bash(make fixtures-check)", "Bash(make lint)",
                    "Bash(make help)", "Bash(npm test)", "Bash(npm run check)", "Bash(node test/:*)",
                    "Bash(node scripts/check_gs.js)", "Bash(python3 test/python_test.py)",
                    "Bash(.venv/bin/python3 test/python_test.py)", "Bash(python3 scripts/check_:*)",
                    "Bash(.venv/bin/python3 scripts/check_:*)", "Bash(python3 test/fixtures/make_fixture.py --check)",
                    "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)",
                    "Bash(git ls-files:*)", "Bash(git check-ignore:*)", "Bash(git branch:*)", "Bash(git blame:*)",
                    "Bash(python3 tools/form_status.py:*)", "Bash(python3 backup_forms.py:*)",
                    "Bash(python3 tools/needs_attention.py:*)", "Bash(python3 tools/add_translations.py --audit:*)",
                    "Bash(python3 tools/sheets_client.py tabs)", "Bash(python3 tools/sheets_client.py whoami)",
                    "Bash(python3 tools/sheets_client.py export:*)", "Bash(ls:*)", "Bash(wc:*)", "Bash(which:*)",
                    "Bash(git commit:*)", "Bash(git push:*)", "Bash(harness-*:*)", "Bash(gh issue:*)", "Bash(gh pr:*)",
                    "Bash(gh api:*)", "Bash(git worktree:*)", "Bash(git fetch:*)", "Bash(git add:*)"]
    DENY_BEFORE = ["Read(./credentials/service-account.json)", "Read(./credentials/config.json)",
                   "Read(./.env)", "Read(./.env.local)", "Read(./.claude/settings.local.json)",
                   "Read(~/.clasprc.json)", "Read(~/.config/gcloud/**)"]
    ALLOW_KEPT = ["Bash(scripts/verify.sh)", "Bash(make check)", "Bash(make py)", "Bash(node test/:*)",
                  "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)", "Bash(python3 tools/form_status.py:*)",
                  "Bash(python3 backup_forms.py:*)", "Bash(python3 tools/sheets_client.py export:*)",
                  "Bash(harness-*:*)", "Bash(gh issue:*)", "Bash(gh pr:*)", "Bash(gh api:*)", "Bash(git worktree:*)",
                  "Bash(git fetch:*)", "Bash(git add:*)", "Bash(git commit:*)", "Bash(git push:*)"]

    def test_gh_api_is_allowed_and_no_ask_rule_names_it(self):
        # "prompt, don't parse" (Ryan, 2026-10-14): main's Bash(gh api:*) allow is back and no ask
        # rule starts Bash(gh api - one would stall the harness's resume reads in a dispatched run;
        # the hook asks on the live gh api calls (actions/, dispatches, graphql)
        allow, ask = self.permissions["allow"], self.permissions["ask"]
        self.assertIn("Bash(gh api:*)", allow)
        for rule in ask:
            self.assertFalse(rule.replace(" ", "").startswith("Bash(ghapi"), f"{rule}: an ask rule on gh api")
        for command in self.LOOP_READS + self.GH_API_OTHERS:
            with self.subTest(command=command):
                self.assertTrue(self.covering("allow", command), f"no allow rule for {command!r}")
                self.assertEqual(self.covering("ask", command), [], "an ask rule would stall a dispatched run")
        for rule in self.ALLOW_KEPT:                                    # nothing else in the list changed
            self.assertIn(rule, allow)
        for rule in self.ASK_BEFORE:
            self.assertIn(rule, ask)

    def test_no_ask_or_deny_rule_stands_in_front_of_an_automatic_family(self):
        # (until 2026-10-26 ask rules backed the hook on these; a hook's allow does not get past one)
        for command in self.AUTO_FAMILIES + self.GATE_PASSES:
            with self.subTest(command=command):
                self.assertEqual(self.covering("ask", command), [], f"an ask rule would prompt (or, headless, "
                                                                     f"deny) a backed {command!r}")
                self.assertEqual(self.covering("deny", command), [], f"a deny rule on {command!r}")

    def test_ask_rules_stay_on_the_deletes_and_nothing_else_changed(self):
        # explicit ask rules prompt in every mode, bypassPermissions included: the layer under the hook
        ask = self.permissions["ask"]
        for rule in self.DELETE_RULES:
            self.assertIn(rule, ask)
        for command in self.DELETE_FAMILIES:
            with self.subTest(command=command):
                self.assertTrue(self.covering("ask", command), f"no ask rule for {command!r}")
        for command in self.PLAIN + self.LOOP_READS:
            with self.subTest(command=command):
                self.assertEqual(self.covering("ask", command), [], "a read would prompt")
        # (the Read rules: test_reading_a_plan_folder_asks_nothing_and_the_personal_data_still_asks)
        bash_rules = [rule for rule in ask if not rule.startswith("Read(")]
        self.assertEqual(sorted(set(bash_rules)), sorted(set(self.ASK_BEFORE + self.DELETE_RULES)),
                         "the ask list is 2026-10-14's without the automatic families, with the delete spellings")
        self.assertEqual(len(ask), len(set(ask)), "a rule listed twice")
        self.assertEqual(self.permissions["deny"], self.DENY_BEFORE)
        missing = [rule for rule in self.ALLOW_BEFORE if rule not in self.permissions["allow"]]
        self.assertEqual(missing, [], "an allow rule was dropped")
        self.assertEqual(sorted(self.settings["env"]),
                         ["CLAUDE_VERIFY_CMD", "HARNESS_SENSITIVE_PATHS", "HARNESS_TEST_CMD", "HARNESS_ULTRAREVIEW",
                          "HARNESS_WORKTREE_SETUP"])
        self.assertEqual(self.settings["env"]["HARNESS_ULTRAREVIEW"], "off")   # no ultrareview: it bills usage credits (2026-10-26)
        # personal-data folders marked sensitive for the Harness backup store (Ryan, 2026-11-05): a later edit
        # must not drop one - narrowed with the Read rules by #204: test_the_harness_sensitive_paths_agree_...

    # F6 of PR #154's review: in dontAsk (a headless run) only allow-listed commands run, so the
    # backups the automatic go needs - besides backup_forms.py and one tab's export, allowed already
    # - get their rules: the GitHub switches, the whole Sheet, a Salesforce plan's before/ retrieve
    BACKUP_RULES = ["Bash(python3 tools/github_switches.py backup)", "Bash(python3 tools/sheets_client.py export-all:*)",
                    "Bash(sf project retrieve start:*)"]
    BACKUPS = ["python3 tools/github_switches.py backup",
               "python3 tools/sheets_client.py export-all data/sheet_2026-10-26",
               "sf project retrieve start -m Report:Attendance --target-dir data/sf_x/before -o glow",
               "sf project retrieve start -o glow --target-dir data/sf_tiles/before",
               "python3 backup_forms.py --form 261234567890123",
               "python3 tools/sheets_client.py export Roster data/sheet_2026-10-26/Roster.csv"]

    def test_a_headless_run_may_take_every_backup_and_the_allow_list_gains_nothing_else(self):
        allow = self.permissions["allow"]
        for rule in self.BACKUP_RULES:
            self.assertIn(rule, allow)
        for command in self.BACKUPS:
            with self.subTest(command=command):
                self.assertTrue(self.covering("allow", command), f"no allow rule lets a headless run take {command!r}")
                self.assertEqual(self.covering("ask", command), [], "an ask rule would stall a headless backup")
                self.assertEqual(self.covering("deny", command), [])
        self.assertEqual(sorted(allow), sorted(self.ALLOW_BEFORE + self.BACKUP_RULES),
                         "the allow list is 2026-10-26's with the three backup rules, and nothing else")
        self.assertEqual(len(allow), len(set(allow)), "a rule listed twice")
        # no allow rule lets a live write or a delete past the hook's decision
        for command in (self.AUTO_FAMILIES + self.DELETE_FAMILIES
                        + ["python3 tools/sheets_client.py import Roster data/roster.csv",
                           "python3 tools/github_switches.py restore backups/github/switches.json",
                           "sf project deploy start --source-dir data/sf_x/before -o glow"]):
            with self.subTest(command=command, check="no allow"):
                self.assertEqual(self.covering("allow", command), [], f"an allow rule covers the live {command!r}")

    # ---- the Read rules (#204, Ryan's ruling of 2026-11-05): a Salesforce plan's before/, build/ and
    # after/ - what a session retrieves, builds and deploys - ask nothing; the personal-data exports still
    # ask: every file at the top of data/ (an export no rule names yet too), a file in any folder of data/
    # that is no plan's before/, build/ or after/ (a folder no rule names yet too), all of the folders
    # that hold personal data, and all of backups/
    PLAN_READS = [
        "data/sf_dashboard_x/build/x.dashboard-meta.xml",
        "data/sf_tiles_2026-11-19/build/force-app/main/default/dashboards/Glow/Attendance.dashboard-meta.xml",
        "data/sf_region_filter/build/package.xml",
        "data/sf_x/before/Attendance.report-meta.xml",
        "data/sf_x/before/main/default/reports/Glow/Attendance.report-meta.xml",
        "data/sf_girls_present_2026-11/before/Attendance_Batch__c.csv",
        "data/sf_x/after/package.xml",
        "data/sf_x/after/main/default/reports/Glow/Attendance.report-meta.xml",
        # the folders themselves (ls, diff -r)
        "data/sf_dashboard_x/build/", "data/sf_x/before/", "data/sf_x/after/",
    ]
    PERSONAL_READS = [
        # the top-level exports: enrollment, roster, partners, needs-attention, audit, form log, review
        # queue, feedback, club registry - and one no rule has heard of yet
        "data/enrollment_2026-08-24.csv", "data/roster.csv", "data/roster_2026-11-01.csv", "data/partners.csv",
        "data/needs_attention.json", "data/audit_2026-10-30.json", "data/formlog.csv", "data/reviewqueue.csv",
        "data/feedback_2026-10.csv", "data/clubregistry.json", "data/new_export_2026-11-19.xlsx",
        # a file in a folder of data/ that is no plan's before/, build/ or after/
        "data/new_dump/rows.csv", "data/sf_dupes_2026-10-26/merge_plan.json", "data/backfill_2026-09/ledger.csv",
        # the folders that hold personal data, at any depth
        "data/backfill_2026-09/batches/2026-09-03.json", "data/auto_sync/run.log", "data/auto_sync/2026-11-18/Africa.json",
        "data/live_2026-10-13/forms/questions.json", "data/reconcile_2026-10/matches/clubs.csv",
        "data/deactivate_clubs/plan.csv", "data/deactivate_clubs/2026-10-20/rows.csv", "data/outreach_2026-10/sent/list.csv",
        # backups/, whole
        "backups/262382821971058/questions-latest.json", "backups/github/switches-2026-10-26T090000.json",
        "backups/all-forms/2026-11-19/properties.json", "backups/notes.txt",
    ]
    # ... and what the Harness keeps secret whatever the settings say: still marked sensitive
    SECRET_READS = ["credentials/service-account.json", "credentials/config.json", ".env", ".env.local", "tools/.env"]

    @staticmethod
    def gitignore(pattern):
        """(regex, folders only) of one gitignore pattern as node-ignore reads it (Claude Code's Read and
        Edit rules follow the gitignore specification): a / at its start or inside anchors it to the
        project, else it matches at any depth; * and ? never cross a /; [...] is one character ([!...]
        one of none of them); a leading **/ any folders, a trailing /** everything inside, /**/ any
        folders between; a trailing / matches folders only."""
        folders = pattern.endswith("/")
        body = pattern.rstrip("/")
        anchored = "/" in body
        body = body.lstrip("/")
        out, i = [], 0
        while i < len(body):
            if body.startswith("**/", i):
                out.append("(?:[^/]*/)*")
                i += 3
            elif body.startswith("/**", i) and i + 3 == len(body):
                out.append("/.+")
                i += 3
            elif body.startswith("**", i):
                out.append(".*")
                i += 2
            elif body[i] == "*":
                out.append("[^/]*")
                i += 1
            elif body[i] == "?":
                out.append("[^/]")
                i += 1
            elif body[i] == "[" and "]" in body[i + 2:]:
                end = body.index("]", i + 2)
                chars = body[i + 1:end].replace("\\", "\\\\").replace("^", "\\^")
                out.append("[^/" + chars[1:] + "]" if chars.startswith("!") else "[" + chars + "]")
                i = end + 1
            else:
                out.append(re.escape(body[i]))
                i += 1
        return re.compile(("" if anchored else "(?:.*/)?") + "".join(out), re.S), folders

    def read_asks(self, path, through_folders):
        """The Read ask rules that cover `path` (from the project; a trailing / marks a folder): each
        whose pattern matches it - and, with through_folders, each that matches a folder above it, which
        node-ignore counts too (what is in an excluded folder is excluded)."""
        folder = path.endswith("/")
        path = path.rstrip("/")
        above = ["/".join(path.split("/")[:n]) for n in range(1, path.count("/") + 1)]
        found = []
        for rule in self.permissions["ask"]:
            if not (rule.startswith("Read(") and rule.endswith(")")):
                continue
            pattern = rule[len("Read("):-1]
            pattern = pattern[2:] if pattern.startswith("./") else pattern
            rx, folders_only = self.gitignore(pattern)
            if (rx.fullmatch(path) and (folder or not folders_only)) or (
                    through_folders and any(rx.fullmatch(f) for f in above)):
                found.append(rule)
        return found

    def test_reading_a_plan_folder_asks_nothing_and_the_personal_data_still_asks(self):
        # deny > ask > allow: no allow rule opens a plan folder under a broad ask, so the ask list itself
        # is narrowed. A personal-data path is matched by a rule itself (so it asks whether or not the
        # folders above count); a plan folder's path by none, nor through a folder above it
        rx = self.gitignore
        self.assertTrue(rx("data/**")[0].fullmatch("data/sf_x/build/a.xml"), "the model: data/** covers below data/")
        self.assertFalse(rx("data/*.*")[0].fullmatch("data/sf_x"), "the model: * matches within one folder")
        self.assertTrue(rx("*.csv")[0].fullmatch("data/sf_x/before/a.csv"), "the model: no / matches at any depth")
        reads = [rule for rule in self.permissions["ask"] if rule.startswith("Read(")]
        self.assertTrue(reads, "no Read ask rule left: the personal data would not ask")
        for rule in reads:
            self.assertTrue(rule.startswith(("Read(./data/", "Read(./backups/")) and rule.endswith(")"),
                            f"{rule}: a Read ask rule is on data/ or backups/, spelt ./ from the project")
        for path in self.PLAN_READS:
            with self.subTest(path=path, side="a plan's before/, build/ or after/"):
                self.assertEqual(self.read_asks(path, through_folders=True), [], f"reading {path} would ask")
        for path in self.PERSONAL_READS:
            with self.subTest(path=path, side="personal data"):
                self.assertTrue(self.read_asks(path, through_folders=False), f"reading {path} would not ask")

    @staticmethod
    def harness_match(pattern, path):
        """The Harness's glob_match (harness_lib/settings.py), which judges HARNESS_SENSITIVE_PATHS: split
        on /, ** any number of segments (none too), each other segment by fnmatchcase; a pattern with no
        / matches the base name; a folder above does not count."""
        pattern = pattern.strip()
        if not pattern:
            return False
        if "/" not in pattern:
            return fnmatch.fnmatchcase(path.rsplit("/", 1)[-1], pattern)

        def match(pats, parts):
            if not pats:
                return not parts
            if pats[0] == "**":
                return any(match(pats[1:], parts[i:]) for i in range(len(parts) + 1))
            return bool(parts) and fnmatch.fnmatchcase(parts[0], pats[0]) and match(pats[1:], parts[1:])
        return match(pattern.split("/"), path.split("/"))

    def test_the_harness_sensitive_paths_agree_with_the_read_rules(self):
        # HARNESS_SENSITIVE_PATHS (#218, #220) keeps the Harness's read-only allow off a sensitive path
        # (a plain ls or cat of it still prompts) and its snapshots of one in the project. It marks what
        # the Read rules ask on - the personal data, backups/ - and credentials/ and .env, and no plan's
        # before/, build/ or after/, nor a file in one
        pats = [p.strip() for p in self.settings["env"]["HARNESS_SENSITIVE_PATHS"].split(",") if p.strip()]
        self.assertTrue(self.harness_match("data/**", "data/sf_x/build/a.xml"), "the model: ** spans folders")
        self.assertFalse(self.harness_match("data/*.*", "data/sf_x/build/a.xml"), "the model: * is one segment")
        for path in self.PERSONAL_READS + self.SECRET_READS:
            with self.subTest(path=path, side="sensitive"):
                self.assertTrue(any(self.harness_match(p, path) for p in pats), f"{path} is not marked sensitive")
        for path in self.PLAN_READS:
            with self.subTest(path=path, side="a plan's before/, build/ or after/"):
                self.assertEqual([p for p in pats if self.harness_match(p, path.rstrip("/"))], [],
                                 f"{path} is marked sensitive: the read-only allow withholds itself on it")

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
