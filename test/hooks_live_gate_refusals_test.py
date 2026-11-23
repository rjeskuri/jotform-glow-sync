#!/usr/bin/env python3
"""
.claude/hooks/live_gate.sh (Bash), run as Claude Code runs it (the harness, the hooks and
settings it reads, and the osascript stub: test/helpers/hooks.py): what no backup lets through.

Since 2026-10-26 (ticket #146) the DELETES (`--prune`, delete/remove/destructive in any case and
position, sf_dupes.py --apply) ask or are refused as before whatever the backups. A command that
approves itself (GLOW_LIVE_OK, a startup file, .claude/live_backups.log written, copied, touched or
recorded by hand in any spelling, a Salesforce plan's before/ written by hand) is refused outright,
whatever the backups; reading the records, naming them, and the retrieve that fills a before/ are
no decision. A read-only command that only mentions a live flag passes, every backup on record or
none.

The automatic go for a backed write: test/hooks_live_gate_backed_test.py.
"""
import collections
import os
import unittest

# first: importing helpers.common (through helpers.hooks) puts the repository root and tools/ on sys.path
from helpers.hooks import ASK_MODES, HookFixture, needs_bash


@needs_bash
class LiveGateRefusals(HookFixture, unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main(verbosity=1)
