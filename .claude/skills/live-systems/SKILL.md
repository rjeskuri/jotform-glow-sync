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
`tools/fix_roster_order.py --apply`, `tools/auto_sync.py --apply`, `tools/upload_roster.py --apply`, `tools/sheets_client.py import`, `npm run
clasp:push` / `npx clasp push`. Anything else is read-only (GET) or writes only under `data/` and
`backups/`.

Salesforce (production) is written only through the write connector, one record per call, by the
main session, with Ryan's explicit go - the hook below does not see those calls. Procedure and
rollback files: docs/RUNBOOK.md, "Club accounts in Salesforce".

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
the plain names); writing a translation language without GET + merge first.

## Rollback
- Conditions: `restore_conditions.py --form <id> [--from <snapshot>] --apply`; Jotform Revision
  History as the second path. It refuses a snapshot whose rules test clubs the Club picker no
  longer offers (any from before a form's `--same-name-switch`, or before a rename): run the
  sync instead (docs/RUNBOOK.md, "Club names two partners share", has the switch's own rollback).
- Questions: never deleted by tooling; a wrongly created question is removed in the builder.
- Sheet tabs: `data/roster_build/previous/<stamp>/` (upload_roster saves them) or the
  `export-all` you took.
- Apps Script: `git checkout <previously deployed commit> -- appsscript && npm run clasp:push` —
  never below the floors in docs/RUNBOOK.md, "Rolling back `appsscript/`" (`7a175c4`; `986a325`
  once the Feedback tab has two reply columns), and deal with held new clubs first.
- Automatic sync: repository variable `AUTO_SYNC_APPLY=0`, or clear the Script Properties
  `SYNC_DISPATCH_REPO` / `SYNC_DISPATCH_TOKEN`.
