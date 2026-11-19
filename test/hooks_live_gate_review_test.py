#!/usr/bin/env python3
"""
.claude/hooks/live_gate.sh (Bash), run as Claude Code runs it (the harness, the hooks and
settings it reads, and the osascript stub: test/helpers/hooks.py): the backed writes review 1 of
PR #154 (ticket #146) narrowed.

After review 1 of PR #154: `sf|sfdx apex run` is automatic only on a --file inside the checkout
that the gate reads - holding delete, merge, undelete or emptyRecycleBin it is a delete, with no
readable file it is not automatic; a --metadata-dir deploy never is, and a deploy of a folder
holding a destructiveChanges*.xml is a delete; clasp push is automatic only from the input's cwd
<project>/appsscript (npm run clasp:push from <project>), never with -P, --project or --rootDir;
a redirect writes the backup records only when they are its target, and a query or export saved
into a before/ is no forgery.

Review 2 and PR #154's three questions: test/hooks_live_gate_review2_test.py.
"""
import collections
import json
import os
import unittest

# first: importing helpers.common (through helpers.hooks) puts the repository root and tools/ on sys.path
from helpers.hooks import HookFixture, needs_bash


@needs_bash
class LiveGateReview1(HookFixture, unittest.TestCase):
    # ... and Apex that deletes, merges (a merge deletes the losing record), undeletes or empties the
    # recycle bin: DML or Database. calls, in any case (beside APEX_UPDATES, test/helpers/hooks.py)
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

    # ---- live_gate.sh: the fixes after review 1 of PR #154 (the design's "Rulings for review 1's
    # findings", F1 F2 F5; 2026-10-26; sf_plan(): test/helpers/hooks.py)

    # one text whatever the file holds: only what the file holds can tell an update from a delete
    APEX_RUNS = ["sf apex run --file data/sf_x/fix.apex -o glow", "sf apex run -f data/sf_x/fix.apex -o glow",
                 "sf apex run --file=data/sf_x/fix.apex --target-org glow", "sfdx apex run -f data/sf_x/fix.apex -o glow"]

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


if __name__ == "__main__":
    unittest.main(verbosity=1)
