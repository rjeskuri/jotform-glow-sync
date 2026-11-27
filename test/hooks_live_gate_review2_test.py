#!/usr/bin/env python3
"""
.claude/hooks/live_gate.sh (Bash), run as Claude Code runs it (the harness, the hooks and
settings it reads, and the osascript stub: test/helpers/hooks.py): the backed writes review 2 of
PR #154 (ticket #146) narrowed, and its three questions.

After review 2: a Salesforce request whose request, body, headers or flags come from a file or
standard input (sf api request rest --file, --body @file or -, --flags-dir, graphql --body <file>,
curl -d @file, -H @file, -T, < file, a python3 -c snippet) is never automatic, nor is any curl with
a config file (-K, --config), whatever the host.
Ryan, 2026-11-06 (PR #154's questions): a write to ~/.curlrc or $CURL_HOME/.curlrc is a
self-approval, refused in every mode; every curl -K/--config is live - asked, or refused where
no prompt can show - even naming no live host; sfdx force:source:push is never automatic, and
sf project deploy start only with an explicit -d/--source-dir, -m/--metadata or -x/--manifest.

Review 1's fixes: test/hooks_live_gate_review_test.py.
"""
import collections
import os
import unittest

# first: importing helpers.common (through helpers.hooks) puts the repository root and tools/ on sys.path
from helpers.hooks import HookFixture, needs_bash


@needs_bash
class LiveGateReview2(HookFixture, unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main(verbosity=1)
