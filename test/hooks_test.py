#!/usr/bin/env python3
"""
The Claude Code guardrail hooks, run as Claude Code runs them: the tool input as JSON on
standard input, the decision in the exit code and on standard output (0 and nothing: no
decision; 0 and an ask JSON: Ryan is asked in the session; 2, or a deny JSON: refused). The harness,
the hooks and settings it reads ($GLOW_HOOKS_DIR, $GLOW_SETTINGS_FILE) and the osascript stub:
test/helpers/hooks.py. This file holds what changes nothing live and the settings behind the gate;
the rest of the gate, protected_paths.sh and the pre-commit hook: test/hooks_*_test.py.

  - .claude/hooks/live_gate.sh (Bash), ticket #204 (Ryan, 2026-11-04: no prompt unless it is
    destructive): what changes nothing live passes with no prompt and no backup - an "allow" in
    every mode a backed write is allowed in, from a subagent too, never in plan mode or an unknown
    mode (plan is not refused): a dashboard refresh (sf|sfdx api request rest on
    /services/data/vNN.N/analytics/dashboards/<id>, PUT with no body or an empty {} one) and a GET
    of the dashboard or its /status; a check-only deploy (sf project deploy start --dry-run, sf
    project deploy validate); a SOQL query (sf data query). Each only as one command beginning so -
    no chain, pipe, substitution, line break, wrapper or VAR=value - that writes neither the backup
    records nor a startup file. Anything else is judged as before: another body (a filter too),
    method, path (.., an encoded /, a ?_HttpMethod) or method-override header, a second body,
    method or URL, a request, body or flags from a file or standard input, a curl, a chain, a pipe,
    a wrapper, a quick deploy, destructive changes or a --metadata-dir beside --dry-run, a query
    that carries a live flag, a live command whose text only mentions one of these; anonymous Apex
    stays as #146 left it (the gate cannot tell a dry run from its file);
  - live_gate.sh, ticket #251 (Ryan, 2026-11-20: fewer prompts from how a command is written): three
    wrappers are transparent - a leading `cd <a folder inside the checkout> &&`, a leading
    `scripts/vpn_check.sh &&`, a trailing pipe into a read-only jq or a python3 -c snippet that reads
    standard input only - and what they wrap is judged as it is alone (a cd's command from the folder
    the cd names); any other wrapper is judged as before (LiveGateWrappers);
  - .claude/settings.json: the permission rules behind the hook (gh api allowed and never asked:
    an ask would stall the harness's resume reads; no ask rule on an automatic family or a #204
    pass - a hook's allow does not get past one -, ask rules kept on the deletes; the Read ask
    rules only on the personal-data exports in data/ and on backups/, never on a Salesforce plan's
    before/, build/ or after/ (Ryan's ruling, 2026-11-05), and HARNESS_SENSITIVE_PATHS marking the
    same; the hook entry that blocks on failure; since #251 the VPN check allowed alone).
"""
import fnmatch
import json
import os
import re
import unittest

# first: importing helpers.common (through helpers.hooks) puts the repository root and tools/ on sys.path
from helpers.hooks import SETTINGS, HookFixture, needs_bash


@needs_bash
class LiveGatePasses(HookFixture, unittest.TestCase):
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


@needs_bash
class LiveGateWrappers(HookFixture, unittest.TestCase):
    # ---- live_gate.sh: ticket #251 (Ryan, 2026-11-20: cut the prompts that come from how a session writes
    # a command, not from what it does). Three wrappers are transparent: a leading `cd <a folder inside
    # the checkout> &&` - relative from the input's cwd, or absolute: the checkout itself, a worktree under
    # .claude/worktrees/ -, a leading `scripts/vpn_check.sh &&` (it exits 1 while a tunnel is up, so &&
    # runs nothing then), and a trailing pipe into a read-only jq (a filter on standard input) or a
    # python3 -c snippet that reads standard input only. What they wrap gets the answer it gets alone: a
    # #204 pass is allowed (PASSED), a backed write gets the automatic go (AUTO-APPROVED), a write without
    # its backup and a delete ask. Ruling (test-author, #251): `cd X && C` from the cwd W is C from W/X -
    # its relative paths and clasp's project are that folder's -, so a cd cannot move clasp to another
    # project's folder behind the gate's back. Any other wrapper is none, judged as before: a cd out of
    # the checkout (a temporary folder, ~, a sibling whose path starts with the checkout's, .. climbing
    # out) or to a path the gate cannot read ($( ), a variable - Ruling: never expanded), ; or || for &&,
    # a look-alike of the check or an assignment before it, a variable assignment, .env sourced, an inline
    # VPN probe; a pipe into python3 -, a script, sh or tee, a jq that writes or reads a file, a python3
    # -c snippet that writes, reads a file or runs what it reads. One mode, default: #146's and #204's
    # tests walk the modes and callers
    QUERY = 'sf data query -q "SELECT Id FROM Account LIMIT 1" -o glow --json'
    DASHBOARD = "sf api request rest /services/data/v60.0/analytics/dashboards/01Z5g000000AbCdEAF/status -o glow"
    BACKED = "sf project deploy start --source-dir data/sf_x/after -o glow"           # data/sf_x/before/ is from today
    UNBACKED = "sf project deploy start --source-dir data/sf_y/after -o glow"         # data/sf_y/ has no before/
    LISTED = "python3 tools/sf_partner_monthly.py --month 2026-09 --apply --vpn-off"  # its own ledger row (#146)
    DELETE = "sf data delete record -s Contact -i 003000000000001 -o glow"
    CLASP = "npx clasp push -f"
    CHECK = "scripts/vpn_check.sh"
    JQ = "jq '.result.totalSize'"
    PY = "python3 -c 'import json, sys; print(json.load(sys.stdin)[\"result\"][\"totalSize\"])'"

    def wrapper_project(self, destructive=False):
        """A clean committed checkout (appsscript/; drive-sync/ beside it, another clasp project), form
        F1's backup from today, the plan data/sf_x/ with its before/ from today and data/sf_y/ with none,
        a worktree folder under .claude/worktrees/, and a sibling folder <checkout>-elsewhere. With
        destructive: a destructiveChanges.xml in a past plan's folder (data/sf_old/del/) that no deploy
        here names, and the plan data/sf_z/ - its before/ from today - whose after/ holds one."""
        p = self.project(git=True)
        self.back_up(p, "jotform", self.F1, f"backups/{self.F1}")
        self.salesforce_before(p, "data/sf_x/before/Contact.object-meta.xml")
        for plan in ("sf_x", "sf_y"):
            self.write(p, f"data/{plan}/after/main/default/reports/Attendance.report-meta.xml", "<Report/>\n")
        self.write(p, "drive-sync/.clasp.json", '{"scriptId": "fictional-drive-sync", "rootDir": "."}\n')
        self.write(p, ".claude/worktrees/t-9-fictional/README.md", "A fictional worktree.\n")
        os.makedirs(p + "-elsewhere")
        if destructive:
            self.write(p, "data/sf_old/del/destructiveChanges.xml", "<Package/>\n")
            self.salesforce_before(p, "data/sf_z/before/Contact.object-meta.xml")
            self.write(p, "data/sf_z/after/main/default/reports/Attendance.report-meta.xml", "<Report/>\n")
            self.write(p, "data/sf_z/after/destructiveChanges.xml", "<Package/>\n")
        return p

    def transparent(self, p):
        """(wrapped, its cwd, the command alone, the cwd it runs in alone, the verdict, the reason's first
        word) - cwds from the checkout, or absolute."""
        wt = os.path.join(p, ".claude", "worktrees", "t-9-fictional")
        q, b, d = self.QUERY, self.BACKED, self.DELETE
        return [
            # a #204 pass: allowed with no prompt and no backup, as alone
            (f"cd data/sf_x && {q}", ".", q, "data/sf_x", "allow", "PASSED"),
            (f"cd {p} && {q}", "data", q, ".", "allow", "PASSED"),
            (f"cd {wt} && {self.DASHBOARD}", ".", self.DASHBOARD, wt, "allow", "PASSED"),
            (f"{self.CHECK} && {q}", ".", q, ".", "allow", "PASSED"),
            (f"{q} | {self.JQ}", ".", q, ".", "allow", "PASSED"),
            (f"{q} | {self.PY}", ".", q, ".", "allow", "PASSED"),
            (f"cd data/sf_x && {self.CHECK} && {q} | jq -r .result.records", ".", q, "data/sf_x", "allow", "PASSED"),
            # a backed write: the automatic go, as alone
            (f"cd {p} && {b}", "data", b, ".", "allow", "AUTO-APPROVED"),
            (f"cd {p} && {self.jotform_write()}", ".", self.jotform_write(), ".", "allow", "AUTO-APPROVED"),
            (f"{self.CHECK} && {self.LISTED}", ".", self.LISTED, ".", "allow", "AUTO-APPROVED"),
            (f"{b} --json | jq -r .result.status", ".", f"{b} --json", ".", "allow", "AUTO-APPROVED"),
            # ... judged from the folder the cd names: clasp pushes that folder's project
            (f"cd appsscript && {self.CLASP}", ".", self.CLASP, "appsscript", "allow", "AUTO-APPROVED"),
            (f"cd ../drive-sync && {self.CLASP}", "appsscript", self.CLASP, "drive-sync", "ask", "LIVE"),
            # a write without its backup, a delete: asked, as alone
            (f"cd {p} && {self.UNBACKED}", ".", self.UNBACKED, ".", "ask", "LIVE"),
            (f"{self.CHECK} && {self.UNBACKED}", ".", self.UNBACKED, ".", "ask", "LIVE"),
            (f"cd {p} && {d}", ".", d, ".", "ask", "LIVE"),
            (f"{self.CHECK} && {d}", ".", d, ".", "ask", "LIVE"),
            (f"{d} --json | {self.JQ}", ".", f"{d} --json", ".", "ask", "LIVE"),
        ]

    def opaque(self, p):
        """(command, its cwd, the verdict): "ask" for a backed write (alone: the automatic go) behind a
        wrapper that is none; "not allow" for a query (alone: allowed) piped into what is no read-only
        filter on standard input."""
        b, q = self.BACKED, self.QUERY
        return [
            (f"cd {self.side.name} && {b}", ".", "ask"),                  # a folder outside the checkout
            (f"cd {p}-elsewhere && {b}", ".", "ask"),                    # its path starts with the checkout's
            (f"cd ~ && {b}", ".", "ask"),
            (f"cd data/../.. && {b}", ".", "ask"),                       # .. climbing out
            (f'cd "$(git rev-parse --show-toplevel)" && {b}', ".", "ask"),
            (f"cd $CLAUDE_PROJECT_DIR && {b}", ".", "ask"),
            (f"cd {p}; {b}", ".", "ask"),
            (f"{self.CHECK}; {b}", ".", "ask"),                          # the write runs with the VPN on too
            (f"{self.CHECK} || {b}", ".", "ask"),                        # ... and only then
            (f"scripts/vpn_check_old.sh && {b}", ".", "ask"),
            (f"TZ=UTC {self.CHECK} && {b}", ".", "ask"),
            ("F=data/sf_x/after; sf project deploy start --source-dir $F -o glow", ".", "ask"),
            (f"set -a; . .env; set +a; {b}", ".", "ask"),
            (f"route -n get default | grep interface && {b}", ".", "ask"),
            (f"{b} --json | python3 -", ".", "ask"),
            (f"{q} | python3 -", ".", "not allow"),                      # standard input is the program
            (f"{q} | python3 data/sf_x/summarize.py", ".", "not allow"),
            (f"{q} | sh", ".", "not allow"),
            (f"{q} | tee data/sf_x/accounts.json", ".", "not allow"),
            (f"{q} | jq . > data/sf_x/accounts.json", ".", "not allow"),
            (f"{q} | jq . data/sf_x/other.json", ".", "not allow"),
            (f"{q} | jq -f data/sf_x/prog.jq", ".", "not allow"),
            (f"{q} | python3 -c 'import sys; open(\"data/sf_x/out.json\", \"w\").write(sys.stdin.read())'", ".", "not allow"),
            (f"{q} | python3 -c 'print(open(\"data/sf_x/q.soql\").read())'", ".", "not allow"),
            (f"{q} | python3 -c 'import os, sys; os.system(sys.stdin.read())'", ".", "not allow"),
        ]

    def first_word(self, run):
        """The reason's first word: PASSED (#204), AUTO-APPROVED (#146), LIVE (the prompt), BLOCKED."""
        return (self.reason(run).split() or [""])[0]

    def as_alone(self, p, rows):
        """The gate's cases for transparent rows (transparent's shape) in `p`: each wrapped, then alone."""
        where = lambda rel: os.path.normpath(os.path.join(p, rel))
        cases = []
        for wrapped, cwd, alone, alone_cwd, _verdict, _kind in rows:
            cases += [(wrapped, dict(project=p, cwd=where(cwd), may_allow=True)),
                      (alone, dict(project=p, cwd=where(alone_cwd), may_allow=True))]
        return cases

    def check_as_alone(self, rows, runs):
        """Each row's run wrapped and alone (the control), from as_alone's cases: both get the verdict
        named, the wrapped one the same kind of reason; the runs it read."""
        for n, (wrapped, _cwd, alone, alone_cwd, verdict, kind) in enumerate(rows):
            (_, _, run), (_, _, control) = runs[2 * n], runs[2 * n + 1]
            with self.subTest(command=wrapped):
                self.assertEqual(self.verdict(control), verdict, f"the control - {alone!r} alone from {alone_cwd}: "
                                 + self.show(control))
                self.assertEqual(self.verdict(run), verdict, f"not judged as {alone!r} alone - " + self.show(run))
                self.assertEqual(self.first_word(run), kind, "not the answer the command alone gets - " + self.show(run))
                if verdict == "ask":
                    self.check_reason(wrapped, self.reason(run))
        return runs[2 * len(rows):]

    def test_a_safe_wrapper_is_judged_as_the_command_it_wraps_and_any_other_is_not(self):
        # DoD: a leading in-repo cd, a leading scripts/vpn_check.sh and a read-only trailing jq or python3
        # -c are transparent, the wrapped command judged as it would be alone; a cd outside the
        # repository, a wrapper around a delete and any other prefix still ask. Each transparent row is run
        # wrapped and alone (the control): both get the verdict named, with the same kind of reason
        p = self.wrapper_project()
        where = lambda rel: os.path.normpath(os.path.join(p, rel))
        rows, others = self.transparent(p), self.opaque(p)
        cases = self.as_alone(p, rows)
        cases += [(command, dict(project=p, cwd=where(cwd), may_allow=True)) for command, cwd, _ in others]
        cases.append((self.CHECK, dict(project=p, cwd=p, may_allow=True)))
        rest = self.check_as_alone(rows, self.verdicts(cases))
        for (command, _cwd, verdict), (_, _, run) in zip(others, rest):
            with self.subTest(command=command):
                if verdict == "ask":
                    self.assertEqual(self.verdict(run), "ask", "a wrapper that is none - " + self.show(run))
                    self.check_reason(command, self.reason(run))
                else:
                    self.assertNotEqual(self.verdict(run), "allow", "a pipe that is no read-only filter - " + self.show(run))
        with self.subTest(command=self.CHECK):
            self.assertEqual(self.verdict(rest[-1][2]), "silent", "the VPN check alone: no decision (the settings "
                                                                  "allow it) - " + self.show(rest[-1][2]))

    def test_a_wrapper_s_own_words_name_no_deploy_folder(self):
        # DoD (the wrapped command judged as it would be alone; PR #254's review, medium): the folders a
        # deploy names, searched for a destructiveChanges*.xml, are the wrapped command's - not the cd's
        # destination nor a jq filter (.) read as a folder - so a destructiveChanges.xml elsewhere in the
        # checkout (data/sf_old/del/) changes nothing; one in the folder the wrapped deploy names still
        # makes it a delete that asks, where without it the plan's before/ from today is the automatic go
        p = self.wrapper_project(destructive=True)
        dry = "sf project deploy start --dry-run -d data/sf_y/after -o glow --json"
        own = "sf project deploy start --source-dir data/sf_z/after -o glow"   # data/sf_z/after/destructiveChanges.xml
        rows = [
            (f"cd {p} && {self.BACKED}", "data", self.BACKED, ".", "allow", "AUTO-APPROVED"),
            (f"{dry} | jq .", ".", dry, ".", "allow", "PASSED"),
            ("cd data && sf project deploy start --dry-run -d sf_y/after -o glow", ".",
             "sf project deploy start --dry-run -d sf_y/after -o glow", "data", "allow", "PASSED"),
            # the safety side: its own folder's destructiveChanges.xml asks, wrapped as alone
            (f"cd {p} && {own}", "data", own, ".", "ask", "LIVE"),
        ]
        runs = self.verdicts(self.as_alone(p, rows))
        self.check_as_alone(rows, runs)
        with self.subTest(command=rows[-1][0]):
            self.assertIn("delet", self.reason(runs[-2][2]).lower(), "the ask does not call it a delete - "
                          + self.show(runs[-2][2]))


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
        self.assertEqual(sorted(allow), sorted(self.ALLOW_BEFORE + self.BACKUP_RULES + [self.VPN_CHECK_RULE]),
                         "the allow list is 2026-10-26's with the three backup rules and the VPN check (#251), "
                         "and nothing else")
        self.assertEqual(len(allow), len(set(allow)), "a rule listed twice")
        # no allow rule lets a live write or a delete past the hook's decision
        for command in (self.AUTO_FAMILIES + self.DELETE_FAMILIES
                        + ["python3 tools/sheets_client.py import Roster data/roster.csv",
                           "python3 tools/github_switches.py restore backups/github/switches.json",
                           "sf project deploy start --source-dir data/sf_x/before -o glow"]):
            with self.subTest(command=command, check="no allow"):
                self.assertEqual(self.covering("allow", command), [], f"an allow rule covers the live {command!r}")

    # ticket #251: the VPN check a session runs as its own call before an sf command (read-only: route and
    # ifconfig) - allowed alone, so it never prompts, in a headless run neither; the rule is the whole
    # command, so nothing chained to it, no flag and no look-alike rides on it
    VPN_CHECK_RULE = "Bash(scripts/vpn_check.sh)"

    def test_the_vpn_check_runs_without_a_prompt_and_nothing_rides_on_its_rule(self):
        self.assertIn(self.VPN_CHECK_RULE, self.permissions["allow"])
        self.assertTrue(self.covering("allow", "scripts/vpn_check.sh"), "no allow rule for scripts/vpn_check.sh")
        self.assertEqual(self.covering("ask", "scripts/vpn_check.sh"), [], "an ask rule would prompt the VPN check")
        self.assertEqual(self.covering("deny", "scripts/vpn_check.sh"), [])
        for command in ("scripts/vpn_check.sh && sf data delete record -s Contact -i 003000000000001 -o glow",
                        "scripts/vpn_check.sh; python3 -", "scripts/vpn_check.sh > .claude/live_backups.log",
                        "scripts/vpn_check.sh --anything", "scripts/vpn_check_old.sh", "scripts/vpn_check.sh.bak"):
            with self.subTest(command=command):
                self.assertEqual([r for r in self.covering("allow", command) if "vpn_check" in r], [],
                                 f"the VPN check's rule covers {command!r}")

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


if __name__ == "__main__":
    unittest.main(verbosity=1)
