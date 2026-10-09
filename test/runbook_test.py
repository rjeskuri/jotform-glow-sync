#!/usr/bin/env python3
"""
docs/RUNBOOK.md against the code: its procedures quote the tools' own commands and lines, in a
safe order (RosterRepairRunbook, SameNameRunbook, ContactIdsRunbook, NamesAndModulesRunbook);
and restore_conditions.py refuses a snapshot whose rules test clubs the Club picker no longer
offers (RestoreConditionsGuard).
"""
import json
import os
import re
import unittest

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import (ClubGuardFixture, REPO, RestoreConditionsFixture, SameNameFixture, read)
import auto_sync
import form_status
import restore_conditions
import sync_attendance_form as sync
from glow import forms as glow_forms
from glow import sync as glow_sync
from glow.text import md5


class RestoreConditionsGuard(RestoreConditionsFixture, unittest.TestCase):
    """restore_conditions.py: a snapshot whose rules test clubs the Club picker no
    longer offers is refused - restored, those clubs' rosters never show and the
    club guard blocks their mentors (every backup from before a form's
    --same-name-switch is one)."""

    def test_stale_club_terms(self):
        stale = restore_conditions.stale_club_terms
        before, after = ClubGuardFixture.form(ClubGuardFixture(), switched=False), ClubGuardFixture.form(ClubGuardFixture())
        self.assertEqual(stale(after[1], after[0]), [])
        self.assertEqual(stale(before[1], before[0]), [])
        # the pre-switch rules on the switched form: "Stars" in two roster rules, the Partner-box
        # rule and both guard rules - named once
        self.assertEqual(stale(before[1], after[0]), ["Stars"])
        # …and the other way round (the switched rules over a picker taken back by hand)
        self.assertEqual(stale(after[1], before[0]), ["Stars - Partner One", "Stars - Partner Two"])
        # the guard's list alone is enough (the roster rules dropped)
        guard_only = [c for c in before[1] if c["type"] == "require"]
        self.assertEqual(stale(guard_only, after[0]), ["Stars"])
        # …and so are the roster rules alone: a snapshot from before the guard existed (and
        # before the switch) has no guard list, only "Club picker equals Stars"
        unguarded = SameNameFixture.form(SameNameFixture(), switched=False)[1]
        self.assertFalse([c for c in unguarded if c["type"] == "require"])
        self.assertEqual(stale(unguarded, after[0]), ["Stars"])
        # a multi-select compares case: another spelling is not the option
        respelt = [dict(c, terms=c["terms"].replace('"Alpha Club"', '"ALPHA CLUB"')) for c in after[1]]
        self.assertEqual(stale(respelt, after[0]), ["ALPHA CLUB"])
        # a snapshot taken before a club was ADDED still fits; parsed or wire terms alike
        older = ClubGuardFixture.form(ClubGuardFixture(), roster={k: v for k, v in ClubGuardFixture.ROSTER.items()
                                                            if k[1] != "Beta Club"})
        self.assertEqual(stale(older[1], after[0]), [])
        self.assertEqual(stale([dict(c, terms=json.loads(c["terms"])) for c in before[1]], after[0]), ["Stars"])
        # without the Club picker nothing is checked (mentors type the club name)
        typed = SameNameFixture.form(SameNameFixture(), picker=False)
        self.assertEqual(stale(before[1], typed[0]), [])

    def test_a_snapshot_whose_rules_do_not_parse_is_refused_before_anything_is_read(self):
        qs, wire = ClubGuardFixture.form(ClubGuardFixture())
        for broken in ({"terms": 5}, {"terms": {"field": "500"}}, {"terms": "{broken"},
                       {"action": json.dumps(["Show"])}):
            snapshot = wire[:2] + [dict(wire[2], id="77", **broken)] + wire[3:]
            self.assertEqual(restore_conditions.unreadable_rules(snapshot), ["77"])
            restore_conditions.stale_club_terms(snapshot, qs)                  # no traceback either
            for extra in ((), ("--apply",), ("--apply", "--force")):
                with self.subTest(broken=broken, extra=extra):
                    code, out, puts = self.run_restore(snapshot, qs, *extra)
                    self.assertIn("Refusing: 1 rule(s) of ", str(code))
                    self.assertIn("have terms or an action that do not parse (rule 77) - not a snapshot "
                                  "to restore", str(code))
                    self.assertEqual((out, puts), ("", []))                  # not even the live form is read
        self.assertEqual(restore_conditions.unreadable_rules(wire), [])

    def test_a_snapshot_from_before_the_switch_is_refused_unless_forced(self):
        before, after = ClubGuardFixture.form(ClubGuardFixture(), switched=False), ClubGuardFixture.form(ClubGuardFixture())
        for extra in ((), ("--apply",)):                       # the dry run says so too
            code, _, puts = self.run_restore(before[1], after[0], *extra)
            self.assertIn("Refusing: the snapshot's rules test 1 club name(s) the Club picker does not "
                          "offer today ('Stars')", str(code))
            self.assertIn("--force", str(code))
            self.assertEqual(puts, [])
        code, out, puts = self.run_restore(before[1], after[0], "--apply", "--force")
        self.assertEqual((code, puts), (0, [before[1]]))
        self.assertIn("! --force:", out)
        self.assertIn("Run the sync (dry run, then --apply) straight after", out)
        # a snapshot that fits is restored as ever
        code, out, puts = self.run_restore(after[1], after[0], "--apply")
        self.assertEqual((code, puts), (0, [after[1]]))
        self.assertIn("matches snapshot", out)
        code, out, puts = self.run_restore(after[1], after[0])
        self.assertEqual((code, puts), (0, []))
        self.assertIn("DRY RUN", out)


class RosterRepairRunbook(unittest.TestCase):
    """docs/RUNBOOK.md "Rosters above Submit": the runner is paused before the
    merge (the form_status check ships with it), and the procedures whose
    checks expect CLEAN come after the repair."""

    def section(self):
        doc = read(os.path.join(REPO, "docs", "RUNBOOK.md"))
        return doc.split("## Rosters above Submit", 1)[1].split("\n## ", 1)[0]

    def test_the_runner_is_paused_before_the_merge(self):
        text = self.section()
        self.assertNotIn("Before the first `--apply`", text)
        self.assertRegex(text, r"AUTO_SYNC_APPLY=0`?,? (set )?before (merging|the merge)")
        self.assertIn("then back to `1`", text)

    def test_what_expects_clean_waits_for_the_repair(self):
        backlog = {l.split("|")[1].strip(): l for l in read(os.path.join(REPO, "docs", "BACKLOG.md"))
                   .splitlines() if re.match(r"\| (~~45~~|46) \|", l)}
        self.assertIn("after 47's repair", backlog["46"])
        # the partner list (45) was retired before it was deployed; what took its place
        # (the same-name switch, RUNBOOK "Club names two partners share") expects CLEAN too
        self.assertIn("superseded 2026-09-30", backlog["~~45~~"])
        self.assertIn("the same-name switch", " ".join(self.section().split()))


class SameNameRunbook(unittest.TestCase):
    """docs/RUNBOOK.md "Club names two partners share": the one-time switch is
    backed up, previewed and verified, the runner paused around it; the rollback
    is for before the Salesforce reconnect; the quoted warnings are the code's."""

    def section(self):
        doc = read(os.path.join(REPO, "docs", "RUNBOOK.md"))
        self.assertNotIn("## The partner list", doc)           # replaced by this section
        return doc.split("## Club names two partners share", 1)[1].split("\n## ", 1)[0]

    def test_the_switch_is_backed_up_previewed_applied_and_verified_in_that_order(self):
        switch = self.section().split("### The one-time switch", 1)[1].split("\n### ", 1)[0]
        block = switch.split("```bash", 1)[1].split("```", 1)[0]
        lines = [l for l in block.splitlines() if l.strip()]

        def at(fragment, after=-1):
            return next(i for i, l in enumerate(lines) if i > after and fragment in l)

        backup = at("backup_forms.py --form")
        dry = at("--same-name-switch ")
        self.assertNotIn("--apply", lines[dry])
        apply = at("--same-name-switch --apply")
        again = at("sync_attendance_form.py", after=apply)
        self.assertNotIn("--apply", lines[again])
        self.assertNotIn("--same-name-switch", lines[again])     # the form stays switched without it
        status, rendered = at("tools/form_status.py", after=apply), at("--rendered", after=apply)
        self.assertEqual(sorted([backup, dry, apply, again, status, rendered]),
                         [backup, dry, apply, again, status, rendered])
        # the runner is paused for the window, merged code first, and switched back on at the end
        text = " ".join(switch.split())
        self.assertIn("**merge first**", text)
        self.assertLess(text.index("AUTO_SYNC_APPLY=0"), text.index("```bash"))
        self.assertGreater(text.index("AUTO_SYNC_APPLY=1"), text.index("```bash"))
        self.assertNotIn("--q5-change-ok --apply", text)         # the switch needs no second flag

    def test_the_rollback_is_all_forms_with_the_runner_paused_and_only_before_the_reconnect(self):
        text = " ".join(self.section().split("### Rollback", 1)[1].split())
        self.assertIn("only before the Salesforce reconnect", text)
        self.assertLess(text.index("AUTO_SYNC_APPLY=0"), text.index("Revert the merge"))
        self.assertLess(text.index("Revert the merge"), text.index("AUTO_SYNC_APPLY=1"))
        self.assertIn("`restore_conditions.py` is not a rollback here", text)

    def test_the_quoted_warnings_and_flags_are_the_tools_own(self):
        text = " ".join(self.section().split())
        self.assertIn(auto_sync.SF_NAME_CHANGE, text)
        self.assertIn(auto_sync.SAME_NAME_REFUSED, text)
        self.assertIn(glow_sync.SF_NAME_SEP.join(("`<club>", "<partner>`")), text)
        src = read(os.path.join(REPO, "sync_attendance_form.py"))
        for flag in ("--same-name-switch", "--q5-change-ok", "--partner-picker"):
            self.assertIn(flag, text)
            self.assertIn(f'"{flag}"', src)
        self.assertIn("HIDE partner textbox (q331: no rule shows it;", text)
        self.assertIn("HIDE partner textbox (q{PARTNER}: no rule shows it;", src)
        # CLAUDE.md rule 5 and the rename procedure carry the Salesforce step
        self.assertIn("--q5-change-ok", read(os.path.join(REPO, "CLAUDE.md")))
        doc = read(os.path.join(REPO, "docs", "RUNBOOK.md"))
        rename = " ".join(doc.split("## Renaming a club", 1)[1].split("\n## ", 1)[0].split())
        self.assertIn("rename the club's Account to the new text first", rename)
        self.assertIn("--apply --q5-change-ok", rename)

    def test_what_the_runbook_says_the_runner_and_the_tools_do_is_what_they_do(self):
        doc = read(os.path.join(REPO, "docs", "RUNBOOK.md"))
        text = " ".join(self.section().split())
        src = read(os.path.join(REPO, "sync_attendance_form.py"))
        # rules older than the picker: the sync's own line, and ATTENTION - not a repair the
        # runner makes ("the next sync run then rebuilds the rules" read as if it did)
        runner = " ".join(doc.split("## Automatic sync", 1)[1].split("\n## ", 1)[0].split())
        for where in (text, runner):
            self.assertIn(auto_sync.RULES_OLDER, where)
        self.assertNotIn("the next sync run then rebuilds", text)
        self.assertIn("The runner does not apply a rules-only difference: it raises ATTENTION", text)
        # a refused new club: the rename that works, and what the verify step then says
        self.assertIn("tools/rename_club.py --partner … --old … --new … --sheet-only", text)
        rename = " ".join(doc.split("## Renaming a club", 1)[1].split("\n## ", 1)[0].split())
        self.assertIn("--sheet-only --apply", rename)
        self.assertIn("applied-with-problems", runner)
        self.assertIn("counts the club that was not added", runner)
        # the switch: its refusal is the tool's, and the count is checked before applying
        self.assertIn("would keep the plain Club picker entry", text)
        self.assertIn("would keep the plain Club picker entry", src)
        self.assertIn("**one more means stop**", text)
        # the Partner-box hide rides along and is not in SyncLog's detail
        self.assertIn("neither counted nor named in `detail`", runner)
        # the retired design is gone from the prose: no roster is Partner-gated for a part move
        self.assertNotIn("Partner-gates both roster questions", doc)
        self.assertNotIn("same-name clubs additionally require the Partner box",
                         " ".join(read(os.path.join(REPO, "README.md")).split()))


class ContactIdsRunbook(unittest.TestCase):
    """docs/RUNBOOK.md "The names list sent to Salesforce": what it quotes is the
    code's own, the rollout is backed up, previewed, applied and verified in that
    order with the runner paused, the console check prints counts only, and the
    rollback is the constants."""

    def section(self):
        doc = read(os.path.join(REPO, "docs", "RUNBOOK.md"))
        return doc.split("## The names list sent to Salesforce", 1)[1].split("\n## ", 1)[0]

    def test_the_quoted_lines_are_the_tools_own(self):
        text = " ".join(self.section().split())
        self.assertIn(sync.CONTACT_IDS_STALE, text)
        self.assertIn("REQUIRED roster '<club>' (q…: Yes)", text)
        self.assertIn("UPDATE roster '<club>' (q…, N girls; required: Yes)", text)
        for name in ("CONTACT_IDS_FIRST", "CONTACT_IDS_PICKER_OPERAND", "ROSTERS_REQUIRED"):
            self.assertIn(name, text)
            self.assertTrue(hasattr(glow_sync, name), name)
        self.assertIn("question 18: rule 1 of N, the Club picker an operand: yes", text)
        runner = " ".join(read(os.path.join(REPO, "docs", "RUNBOOK.md"))
                          .split("## Automatic sync", 1)[1].split("\n## ", 1)[0].split())
        self.assertIn(auto_sync.CONTACT_IDS_STALE, runner)
        self.assertIn("`REQUIRED roster` line", runner)

    def test_the_rollout_is_backed_up_previewed_applied_and_verified(self):
        text = self.section()
        block = text.split("```bash", 1)[1].split("```", 1)[0]
        lines = [l for l in block.splitlines() if l.strip()]

        def at(fragment, after=-1):
            return next(i for i, l in enumerate(lines) if i > after and fragment in l)

        backup = at("backup_forms.py --form")
        dry = at("sync_attendance_form.py")
        apply = at("--apply")
        again = at("sync_attendance_form.py", after=apply)
        status = at("tools/form_status.py", after=apply)
        rendered = at("--rendered", after=apply)
        self.assertEqual(sorted([backup, dry, apply, again, status, rendered]),
                         [backup, dry, apply, again, status, rendered])
        self.assertNotIn("--apply", lines[dry] + lines[again])
        flat = " ".join(text.split())
        self.assertLess(flat.index("AUTO_SYNC_APPLY=0"), flat.index("```bash"))
        self.assertGreater(flat.rindex("`AUTO_SYNC_APPLY=1`"), flat.index("```bash"))   # back on at the end
        self.assertIn("**hard stop**", flat)

    def test_the_rollout_merges_right_after_the_template(self):
        # the runner syncs from main, and older code puts a rolled-out form back in the old
        # order with its next roster change and reads CLEAN: the merge is a step of its own,
        # between the template and the first regional form, before the runner is switched on
        flat = " ".join(self.section().split())
        m = flat.index("**merge and push**")
        self.assertLess(flat.index("The template goes first"), m)
        self.assertLess(m, flat.index("Then U.S, Latin America, Asia and Africa"))
        self.assertLess(m, flat.index("```bash"))
        self.assertLess(m, flat.rindex("`AUTO_SYNC_APPLY=1`"))
        self.assertIn("nobody applies the template from another checkout", flat)
        # proven with the runner's own refusal, which older code never gives
        plan = auto_sync.parse_plan("DRY RUN (use --apply to write):\n  - REPLACE conditions (40 rules)\n"
                                    f"  ! {auto_sync.CONTACT_IDS_STALE}: rule 39 of 40\n")
        (reason,) = auto_sync.check_bands(plan)
        quoted = flat.split("with the reason \"", 1)[1].split("\"", 1)[0]
        for part in quoted.split(" … "):
            self.assertIn(part, reason)
        skill = " ".join(read(os.path.join(REPO, ".claude", "skills", "live-systems", "SKILL.md")).split())
        self.assertIn("so merge right after the template's rollout", skill)

    def test_the_required_message_is_english_on_four_forms(self):
        # only U.S's translation store holds the `base` entry of Jotform's required text
        # (read 2026-10-01): the rollout's Español check must not read English as a failure
        flat = " ".join(self.section().split())
        self.assertNotIn("in the form's language", flat)
        self.assertNotIn("in the form's language", " ".join(read(os.path.join(REPO, "glow", "sync.py")).split()))
        step7 = flat.split(" 7. ", 1)[1].split("`equal: false`", 1)[0]
        self.assertIn("Spanish on U.S only", step7)
        self.assertIn("template, Africa, Asia and Latin America it stays English", step7)
        self.assertIn("not a failure", step7)
        backlog = read(os.path.join(REPO, "docs", "BACKLOG.md"))
        item = next(l for l in backlog.splitlines() if l.startswith("| 57 |"))
        self.assertIn(f"`{md5('This field is required.')[:8]}…`", item)      # the key, cut (check_secrets)
        self.assertIn("`base`", item)

    def test_the_back_step_cannot_pass_from_the_browsers_memory(self):
        # a default Chrome restores the page from its back-forward cache, where the old rules
        # pass too: the step makes Chrome load it again and reads Jotform's own flag
        flat = " ".join(self.section().split())
        step6 = flat.split(" 6. ", 1)[1].split(" 7. ", 1)[0]
        self.assertIn("addEventListener('unload', () => {})", step6)
        self.assertIn("`bf: false`", step6)
        self.assertIn("--disable-features=BackForwardCache", step6)
        self.assertLess(step6.index("addEventListener"), step6.index("Back"))

    def test_the_language_switcher_residual_says_what_the_required_flag_does(self):
        flat = " ".join(self.section().split())
        residual = flat.split("**Two clubs picked, then the form's own language switcher**", 1)[1]
        for fragment in ("higher in the picker's list", "every shown roster has a tick",
                         "Ticks in one roster only are refused", "Ticks in both still go through",
                         "clears the picker and picks her club again"):
            self.assertIn(fragment, residual)
        backlog = read(os.path.join(REPO, "docs", "BACKLOG.md"))
        item = next(l for l in backlog.splitlines() if l.startswith("| 56 |"))
        self.assertIn("ticks in one roster only are refused", item)
        self.assertIn("higher in the list", item)

    def test_the_console_check_prints_counts_only(self):
        js = self.section().split("```js", 1)[1].split("```", 1)[0].strip()
        returned = js.split("return {", 1)[1].split("};", 1)[0]
        self.assertEqual(re.findall(r"(\w+):", returned), ["shown", "ticked", "q18", "equal", "flagged", "bf"])
        self.assertNotIn("console.log", js)
        self.assertIn("input_18", js)
        self.assertIn("JotForm.fromBFCache", js)

    def test_the_rollback_is_generated(self):
        rollback = " ".join(self.section().split("**Rollback**", 1)[1].split())
        self.assertIn("`False`", rollback)
        self.assertIn("REQUIRED roster '<club>' (q…: No)", rollback)
        self.assertIn("restore_conditions.py", rollback)
        self.assertLess(rollback.index("`False`"), rollback.index("restore_conditions.py"))   # the second path
        # the runner runs main's constants: merged only once every form is rolled back
        self.assertIn("Once every form is rolled back, merge the constants-off commit to `main`, and only then "
                      "set `AUTO_SYNC_APPLY=1`", rollback)
        self.assertIn("Never merge a constants-off commit while any form is still rolled out", rollback)
        skill = " ".join(read(os.path.join(REPO, ".claude", "skills", "live-systems", "SKILL.md")).split())
        self.assertIn("merge the constants-off commit only once every form is rolled back", skill)


class NamesAndModulesRunbook(unittest.TestCase):
    """docs/RUNBOOK.md "The names dictionary and the module values": the commands and
    lines it quotes are the tools' own, the rollout is template first with the runner
    paused, and both rollbacks are there."""

    def section(self):
        doc = read(os.path.join(REPO, "docs", "RUNBOOK.md"))
        return " ".join(doc.split("## The names dictionary and the module values", 1)[1].split("\n## ", 1)[0].split())

    def test_the_quoted_lines_and_flags_are_the_tools_own(self):
        text = self.section()
        tool = read(os.path.join(REPO, "tools", "fix_name_translations.py"))
        for fragment in ("keys to remove:", "after the removal", "re-read: APPLIED", "public page: 0 removed keys",
                         "nothing to remove"):
            self.assertIn(fragment, text)
            self.assertIn(fragment.split(":")[0], tool)
        self.assertIn("UPDATE module dropdown (q14, year 1: calcValues = its 5 options)", text)
        self.assertTrue(auto_sync.MODULE_RX.match("  - UPDATE module dropdown (q14, year 1: calcValues = its 5 options)"))
        for flag in ("--restore", "--apply", "--form"):
            self.assertIn(flag, text)
        self.assertIn("MODULE_CALC_VALUES", text)
        self.assertIn("AUTO_SYNC_APPLY=0", text)
        self.assertIn(f"fix_name_translations.py --form {glow_forms.TEMPLATE} --apply", text)
        # template first, merged, then the regional forms; the runner back on last
        order = [text.index(s) for s in ("1. The template", "2. **Merge and push**",
                                         "3. U.S, Latin America, Asia, Africa, smallest first",
                                         "then `AUTO_SYNC_APPLY=1`")]
        self.assertEqual(order, sorted(order))
        self.assertIn("never unattended", text)
        self.assertIn("--restore backups/translations/<id>-<stamp>-before.json", text)
        # the module chain's shape (docs/plans/2026-10-06-module-selection.md): the line is the tool's own
        qs, _ = SameNameFixture.form(SameNameFixture(), switched=True)
        line = form_status.module_shape_line(form_status.audit_module_shape(qs, {"clearFieldOnHide": "disable"})[1])
        self.assertIn(f"module shape: {line}", text)
        for fragment in ("dontClear", "`enable`", "never a sync apply", "JotForm.clearFieldOnHide"):
            self.assertIn(fragment, text)


if __name__ == "__main__":
    unittest.main(verbosity=1)
