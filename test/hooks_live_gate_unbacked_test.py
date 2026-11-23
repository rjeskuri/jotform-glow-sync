#!/usr/bin/env python3
"""
.claude/hooks/live_gate.sh (Bash), run as Claude Code runs it (the harness, the hooks and
settings it reads, and the osascript stub: test/helpers/hooks.py): a write without its backup, and
the modes that never get the automatic go.

Since 2026-10-26 (ticket #146) a live write whose backup from today is on record goes through with
no prompt (test/hooks_live_gate_backed_test.py). Without one the write asks Ryan in the session,
and is refused - with the reason and the backup command - where no prompt can show
(bypassPermissions, dontAsk, missing or unknown mode, a subagent). Never automatic: plan mode, an
unknown mode; a chained command, a launcher and a tool no pinned list names:
test/hooks_live_gate_never_automatic_test.py.
"""
import collections
import datetime
import os
import unittest

# first: importing helpers.common (through helpers.hooks) puts the repository root and tools/ on sys.path
from helpers.hooks import ASK_MODES, UNKNOWN_MODES, HookFixture, needs_bash


@needs_bash
class LiveGateUnbacked(HookFixture, unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main(verbosity=1)
