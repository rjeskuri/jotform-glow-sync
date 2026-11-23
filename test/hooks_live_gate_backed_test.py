#!/usr/bin/env python3
"""
.claude/hooks/live_gate.sh (Bash), run as Claude Code runs it (the harness, the hooks and
settings it reads, and the osascript stub: test/helpers/hooks.py): the automatic go for a backed
write.

Since 2026-10-26 (ticket #146): a live WRITE whose backup from today is on record goes through with
no prompt - an "allow" - in default, acceptEdits, auto, dontAsk, bypassPermissions and a missing
mode, from a subagent too; it is logged ALLOWED (mode, target, backup) and notified (osascript, the
command only ever an argument, run detached). The backups: a `<date time>\t<target>\t<id>\t<path>`
line in .claude/live_backups.log (glow/live_backups.py) from today - its first field - whose path
still exists inside the project without climbing out of it - `jotform <form id>|all` (a form id is
one after --form or in an API path /form/<id>; FORM_TOOLS lists the tools that write forms),
`sheet <Tab>|all`, `github all` -, a clean committed appsscript/ for clasp push, a
data/sf_<topic>/before/ file modified today for a raw sf write naming that folder, and for the
Salesforce tools on SF_LISTED their own ledger or rollback file, written before each write.

Without one the write asks, or is refused where no prompt can show:
test/hooks_live_gate_unbacked_test.py; what never gets the automatic go:
test/hooks_live_gate_never_automatic_test.py; the deletes: test/hooks_live_gate_refusals_test.py.
"""
import collections
import datetime
import os
import time
import unittest

# first: importing helpers.common (through helpers.hooks) puts the repository root and tools/ on sys.path
from helpers.hooks import HookFixture, needs_bash


@needs_bash
class LiveGateBackedWrites(HookFixture, unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main(verbosity=1)
