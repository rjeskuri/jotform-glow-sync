---
name: live-systems
description: What is live (the four regional Jotform attendance forms, the template, the master enrollment sheet, the deployed Apps Script, the Salesforce integration), which commands write to them, the backup → dry-run → go → apply → verify ritual, and the rollback path per system. Load before any command with --apply, --prune, clasp push, upload_roster.py, sheets_client.py import, or auto_sync.py --apply, and before editing appsscript/.
---

# Live systems

Live since 2026-09-01: the four regional attendance forms (ids in `docs/RUNBOOK.md`), the
template `262352490535154` (not mentor-facing, but every logic change lands there first), the
master enrollment Google Sheet and the Apps Script bound to it, and — through the forms — the
Salesforce V2 integration.

## Writers
`sync_attendance_form.py --apply`, `restore_conditions.py --apply`, `tools/add_*.py --apply`,
`tools/restore_translations.py --apply`, `tools/clone_regional.py --apply`,
`tools/fix_roster_order.py --apply`, `tools/fix_name_translations.py --apply` (also with `--restore`),
`tools/auto_sync.py --apply`, `tools/upload_roster.py --apply`, `tools/sheets_client.py import`, `npm run
clasp:push` / `npx clasp push`; in Salesforce `tools/sf_backfill.py send --apply` and
`tools/sf_dupes.py merge|rename|cleanup --apply` (below). Anything else is read-only (GET) or writes
only under `data/` and `backups/` - except `tools/sf_dupes.py merge --rehearse`, which runs the
merges' DML in Salesforce for real and then throws so that Salesforce rolls it back: it leaves
nothing behind, but it is not read-only (triggers run, records are locked meanwhile).

Salesforce (production) is written in two ways only, both with Ryan's explicit go: through the
write connector, one record per call, by the main session (the hook below does not see those
calls; docs/RUNBOOK.md, "Club accounts in Salesforce"), and by `tools/sf_backfill.py send --apply`
(attendance batches, which carry girls' names and so never pass through the conversation; the
hook catches it; docs/RUNBOOK.md, "Back-fill of attendance into Salesforce"). No Salesforce
CLI or API call from the Mac while a VPN is on: Salesforce freezes the user (2026-09-30).
A fourth: **the automatic sync** creates a new club's Club account as the GLOW Sync integration user
when the repository variable `SF_SYNC` is `apply` (`--apply-salesforce`; create only, at most 5 per
region; docs/RUNBOOK.md, "New clubs' accounts, automatically"). Changing `SF_SYNC` is Ryan's go.
A third way: **metadata deploys** (`sf project deploy start`: the Monthly Report checkbox, the
attendance processor, the attendance dashboard). Check-only first (`--dry-run`), then Ryan's go;
the hook does not see `sf` commands. Claude Code's auto-mode guard may refuse a production deploy
(it did on 2026-10-02); then Ryan runs it himself (docs/RUNBOOK.md, "Attendance dashboard in
Salesforce").
A fifth: **`tools/sf_dupes.py merge|rename|cleanup --apply`** (2026-10-07): duplicate contacts of
one girl merged by anonymous Apex (`sf apex run`, one all-or-nothing run per club), a stored name's
whitespace fixed, extra affiliations and duplicate-rule sets deleted; each with Ryan's go, after a
dry run and `merge --rehearse`, `merge_rollback.json` written before the first write
(docs/RUNBOOK.md, "Duplicate girls in Salesforce"). The hook catches `--apply`, not `--rehearse`.

## The ritual
1. Dry run and read the plan (`CREATE` / `UPDATE` / `DELETE` / `REPLACE` lines and every `!` / `?`).
2. Back up the exact thing you will write: `backup_forms.py --form <id>`,
   `sheets_client.py export-all data/live_<date>`, or note the last pushed commit for Apps Script.
3. Get Ryan's explicit go in this conversation. The hook `.claude/hooks/live_gate.sh` blocks the
   write unless he exported `GLOW_LIVE_OK=1` before launching Claude Code or runs it himself.
4. Apply. Then verify with a read: `form_status.py --form <id> --roster <csv>` (CLEAN),
   `sheets_client.py tabs`, or the sheet menu.
5. Say what was written, where the backup is, and how to roll back.

## Never
`--prune` on a form with submissions (it refuses anyway); deleting questions or rows (deactivate
instead); hand-made conditions (the sync regenerates all of them); re-pointing the Salesforce
mapping off question 5; changing what an existing club sends to question 5 (its Salesforce
Account name: a rename, a respelled partner of a `<club> - <partner>` club) without renaming the
Account first — the sync refuses it without `--q5-change-ok`; `sync_attendance_form.py --apply`
from a checkout without the same-name code once a form is switched (older code puts it back on
the plain names), or without the question-18 code once a form is rolled out (older code puts
the Contact_IDs sum back after the roster rules: docs/RUNBOOK.md, "The names list sent to
Salesforce"; so merge right after the template's rollout, before the first regional form);
writing a translation language without GET + merge first.

## Rollback
- Conditions: `restore_conditions.py --form <id> [--from <snapshot>] --apply`; Jotform Revision
  History as the second path. It refuses a snapshot whose rules test clubs the Club picker no
  longer offers (any from before a form's `--same-name-switch`, or before a rename): run the
  sync instead (docs/RUNBOOK.md, "Club names two partners share", has the switch's own rollback).
- Question 18's rule order and operand and the rosters' required flag: generated, so the rollback
  is `glow/sync.py`'s `CONTACT_IDS_FIRST` / `CONTACT_IDS_PICKER_OPERAND` / `ROSTERS_REQUIRED`
  turned off on a branch and the sync applied by hand per form (docs/RUNBOOK.md, "The names list
  sent to Salesforce"); `restore_conditions.py` is the second path for the rules only. The runner
  runs `main`'s constants: merge the constants-off commit only once every form is rolled back, then
  `AUTO_SYNC_APPLY=1`; never while any form is still rolled out (the runner would put the old rule
  order back on it with its next roster change).
- The names dictionary (`base`/`en` of a form's translation store): `tools/fix_name_translations.py
  --form <id> --restore backups/translations/<id>-<stamp>-before.json`, a dry run, then `--apply`
  (puts back the entries the form no longer has). The module dropdowns' `calcValues`: generated,
  so `glow/sync.py` `MODULE_CALC_VALUES = False` on a branch and the sync applied by hand per form;
  the runner never applies those lines (docs/RUNBOOK.md, "The names dictionary and the module
  values").
- Questions: never deleted by tooling; a wrongly created question is removed in the builder.
- Sheet tabs: `data/roster_build/previous/<stamp>/` (upload_roster saves them) or the
  `export-all` you took.
- Apps Script: `git checkout <previously deployed commit> -- appsscript && npm run clasp:push` —
  never below the floors in docs/RUNBOOK.md, "Rolling back `appsscript/`" (`7a175c4`; `986a325`
  once the Feedback tab has two reply columns), and deal with held new clubs first.
- Automatic sync: repository variable `AUTO_SYNC_APPLY=0`, or clear the Script Properties
  `SYNC_DISPATCH_REPO` / `SYNC_DISPATCH_TOKEN`.
- Salesforce duplicate merges, renames, deleted affiliations: from `data/sf_dupes_<date>/merge_rollback.json`
  (a merge: undelete within 15 days, then the saved rows inserted again on the restored contact;
  docs/RUNBOOK.md, "Duplicate girls in Salesforce", Rollback). Never delete a back-fill contact
  to undo anything: it may carry live rows (RUNBOOK, "Back-fill of attendance into Salesforce").
