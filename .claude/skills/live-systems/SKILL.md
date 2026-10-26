---
name: live-systems
description: What is live (the four regional Jotform attendance forms, the template, the master enrollment sheet, the deployed Apps Script, the automatic sync), every command that writes to them with its backup and rollback, and the backup → dry-run → go → apply → verify ritual. Load before any command with --apply, --prune or --rehearse, clasp push, upload_roster.py, auto_sync.py --apply or a gh switch of the sync, and before editing appsscript/ (Salesforce writes are in the salesforce skill).
---

# Live systems

Live since 2026-09-01: the four regional attendance forms (ids in `docs/RUNBOOK.md`), the
template `262352490535154` (not mentor-facing, but every logic change lands there first), the
master enrollment Google Sheet and the Apps Script bound to it, the automatic sync (GitHub
Actions, `main`'s code: a form change the sync generates is rolled out by its merge — the runner
applies it to every enabled regional form on its next run; the template and a disabled form are
applied by hand; DECISIONS 2026-10-14), and — through the forms — Salesforce, whose writers,
gates and rollbacks are in `.claude/skills/salesforce`.

## The gate
`.claude/hooks/live_gate.sh` decides each of these: `--apply`, `--prune`, `--rehearse`, `clasp
push` / `clasp:push`; raw `api.jotform.com` calls and Sheets writes; `sf`/`sfdx` deploys
(check-only ones too), data writes, `apex run`, `sf api request` writes and the REST API by URL;
`gh variable|secret set|delete`, `gh workflow enable|disable`, a `gh workflow run` that applies,
`gh run rerun`, and any `gh api` (or `api.github.com`) call on `actions/`, `dispatches` or
`graphql`. Since 2026-10-26 (#146) a live write whose backup from today is on record goes through
automatically, logged `ALLOWED` and notified - from a subagent or a headless run too - when it is
one simple command of a tool or raw shape the hook lists. The backups: `backup_forms.py --form
<id>` (or every form: `jotform all`), `sheets_client.py export <Tab> <file>` / `export-all`,
`tools/github_switches.py backup`, a committed `appsscript/`, a plan's `before/` retrieve from
today for a raw `sf` write, a Salesforce tool's own ledger. Deletes and `--prune` still ask Ryan
in the session, and are refused where no prompt can show; so is a write without its backup, and
any other live command. It refuses outright a self-approval (setting `GLOW_LIVE_OK`, writing a
shell startup file or `.env`, `launchctl setenv`, a backup record or a `before/` made by hand). A
read-only command that only mentions a flag (`grep`, `cat`, `git log` …, alone) passes. The hook
is a seatbelt: it does not see the connectors or a write through another program, and a write it
does not see needs Ryan's explicit go in this conversation. RUNBOOK "Live gate (Claude Code)".

## Writers (one per row; every other command is read-only or writes only under `data/` and `backups/`)
| Writer | What it changes | Saved before the write | Rollback |
|---|---|---|---|
| `sync_attendance_form.py --apply` | A form's rosters, Club picker and ALL its conditions; with `--prune` it deletes questions (fresh clones only) | `backup_forms.py --form <id>` (take it) | Conditions: below |
| `restore_conditions.py --apply` | A form's conditions | A snapshot of its own | That snapshot; Jotform Revision History |
| `tools/add_feedback_link.py --apply` | The link elements above Submit | A snapshot | `--remove --apply` |
| `tools/add_translations.py --apply` | Translation strings | The whole store (`backups/translations/`) | RUNBOOK "Translations" |
| `tools/add_language.py --apply` | A language on the switcher, and its dictionary | The whole store | RUNBOOK "Translations" |
| `tools/restore_translations.py --apply` | A clone's language list and missing strings | The whole store | RUNBOOK "Translations" |
| `tools/fix_name_translations.py --apply` | `base`/`en` entries of the names dictionary | The whole store | `--restore <saved store> --apply` |
| `tools/switcher_flags.py --apply` | `injectCSS` (the switcher's flags) | A snapshot (its properties) | The snapshot's `injectCSS` |
| `tools/update_static_fields.py --apply` | Wording, the photo limits, the header logo | `backup_forms.py --form <id>` (take it) | The questions snapshot or Revision History (RUNBOOK "Header logo") |
| `tools/fix_roster_order.py --apply` | The roster questions' `order` | A snapshot | `--form <id> --undo <stamp> --apply` |
| `tools/disable_form.py --apply` | A regional form's `status` and its disabled page's text | A snapshot | `--enable --apply` |
| `tools/rename_club.py --apply` | A club's name or partner in the sheet's tabs and on its form | The tabs (`data/rename_club/<stamp>/`), a form snapshot | Those tabs and `restore_conditions.py` (RUNBOOK "Renaming a club") |
| `tools/deactivate_clubs.py --apply` | Roster rows' `status` and `removed_date`, one Audit row | The Roster tab (`data/deactivate_clubs/<stamp>/`) | `--undo <dir> --apply` |
| `tools/upload_roster.py --apply` | The sheet's roster tabs (the offline path) | The tabs it replaces (`data/roster_build/previous/<stamp>/`) | Those tabs, or the `export-all` you took |
| `tools/auto_sync.py --apply` | What the sync writes, per region, within the bands; a SyncLog row | A conditions snapshot per form (`backups/<form>/conditions-<stamp>.json`) | `restore_conditions.py --from` it; a merged form change: its revert or constants-off commit, merged (the next run rolls the forms back); an emergency stop: `AUTO_SYNC_APPLY=0`, back to `1` when `main` and the forms agree |
| `npm run clasp:push` / `npx clasp push` | The deployed Apps Script | The last deployed commit (`/deploy-appsscript`) | That commit pushed again, never below the floors (below) |
| `gh variable set AUTO_SYNC_APPLY`, `gh workflow run auto-sync.yml -f apply=true` | Whether, and when, the runner writes: `AUTO_SYNC_APPLY` is normally `1`, and a rollout never sets it | — | The emergency off switch, in a rollback or an incident only: `AUTO_SYNC_APPLY=0`, set back to `1` before it ends; or clear the Script Properties `SYNC_DISPATCH_REPO` / `SYNC_DISPATCH_TOKEN` |

## The ritual
A form change the sync generates is rolled out by its merge: the runner applies it to every
enabled regional form on its next run, and the read-back is each region's SyncLog row and
`form_status.py`. The ritual is for the template (from the ticket branch, before the land), a
disabled form, and every other writer in the table.

1. Dry run and read the plan (`CREATE` / `UPDATE` / `DELETE` / `REPLACE` lines and every `!` / `?`).
2. Back up the exact thing you will write: `backup_forms.py --form <id>`,
   `sheets_client.py export-all data/live_<date>`, `tools/github_switches.py backup` for a switch,
   or commit `appsscript/` (and note the last pushed commit) for Apps Script.
3. The go: with step 2's backup on record from today, the gate lets a listed write through
   automatically (logged, notified); otherwise - a delete, `--prune`, a tool it does not list -
   Ryan's yes to its prompt is the go, or he runs it himself.
4. Apply. Then verify with a read: `form_status.py --form <id> --roster <csv> --partners <csv>`
   (CLEAN), `sheets_client.py tabs`, or the sheet menu.
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
Salesforce"; so the template is applied from the ticket branch before the land, and a disabled
form from `main` after it);
writing a translation language without GET + merge first.

## Rollback beyond the table
- Conditions: `restore_conditions.py --form <id> [--from <snapshot>] --apply`; Jotform Revision
  History as the second path. It refuses a snapshot whose rules test clubs the Club picker no
  longer offers (any from before a form's `--same-name-switch`, or before a rename): run the
  sync instead (docs/RUNBOOK.md, "Club names two partners share", has the switch's own rollback).
- Question 18's rule order and operand and the rosters' required flag: generated, so
  `glow/sync.py`'s `CONTACT_IDS_FIRST` / `CONTACT_IDS_PICKER_OPERAND` / `ROSTERS_REQUIRED` are
  turned off on a ticket branch, and merging the constants-off commit is the rollback: the runner
  runs `main`'s constants and rolls every enabled regional form back on its next run (a
  rule-order-only difference waits for each region's next roster change; to roll a form back at
  once, apply it from `main`, no stop needed). The template and a disabled form are applied by
  hand. One form alone cannot stay rolled back while `main` disagrees (the runner rolls it
  forward): that needs the emergency switch, `AUTO_SYNC_APPLY=0`, set back to `1` when `main` and
  the forms agree. `restore_conditions.py` is the second path for the rules only
  (docs/RUNBOOK.md, "The names list sent to Salesforce").
- The module dropdowns' `calcValues` and the special-event options: generated, so `glow/sync.py`
  `MODULE_CALC_VALUES = False` (or the type's merge reverted) on a ticket branch, and merging it
  is the rollback: the runner rolls every enabled regional form back on its next run. A
  special-event option is then deleted in the builder on each form's three module dropdowns (the
  revert first, else the next apply adds it back), and the runner realigns `calcValues`. The
  template and a disabled form are applied by hand; one form alone, as with question 18, only
  under the emergency switch (docs/RUNBOOK.md, "The names dictionary and the module values",
  "Special events").
- Questions: never deleted by tooling; a wrongly created question is removed in the builder.
- Apps Script: `git checkout <previously deployed commit> -- appsscript && npm run clasp:push` —
  never below the floors in docs/RUNBOOK.md, "Rolling back `appsscript/`" (`7a175c4`; `986a325`
  once the Feedback tab has two reply columns), and deal with held new clubs first.
