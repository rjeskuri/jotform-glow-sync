# GLOW Attendance Form Sync

Tooling for Global G.L.O.W.'s club attendance: the **master enrollment Google Sheet** (one row
per girl in its Roster tab) is the source of truth, and the four regional **Jotform attendance
forms** follow it — one hidden roster checkbox question per club, plus all the conditional
logic that shows the right roster and feeds Salesforce. Roster changes arrive through a Google
Form, the sheet's Apps Script updates the Roster, and a GitHub Actions job keeps the Jotform
forms in step. Live since 2026-09-01.

The data is rosters of minors: nothing under `data/`, `backups/` or `credentials/` is ever
committed, and tests run on a synthetic fixture with fictional names.

## Quick start

```bash
git clone <this repo> && cd jotform-glow-sync
make venv                 # .venv: the Google Sheets libraries and ruff (make check runs ruff)
make hooks                # once per clone: the pre-commit hook (secret scan of the added lines,
                          # ruff on the staged .py files) and the commit message template
npm install               # clasp 2.4.2 for the Apps Script deploy; it runs on Node 18 only (nvm use 18)
make check                # the offline feedback loop: must print CHECK PASSED
cp .env.example .env      # then fill in the Jotform key; load with: set -a; source .env; set +a
```

Python 3.10 (the venv and CI) and Node 18. Sheet access (service account) is described in
[docs/SHEETS-ACCESS.md](docs/SHEETS-ACCESS.md); every operational procedure, with its dry-run
and apply forms, in [docs/RUNBOOK.md](docs/RUNBOOK.md).

## What is where

| Path | What it does |
|---|---|
| `sync_attendance_form.py` | The product: makes one form match the Roster export — rosters, the Club picker, and every condition. Dry run by default, `--apply` writes |
| `backup_forms.py`, `restore_conditions.py` | Snapshot a form; roll its conditions back (the restore snapshots the form first) |
| `glow/` | The library every tool imports, standard library only: `jotform` (the one Jotform client, dry-run gated; the public page; submissions paged), `forms` (the one table of form ids and regions), `sync` (the Roster and enrollment parsers, the structural question ids, the Club picker, a rule's parts), `text` (the name and cell keys), `cli` (the API key, the `--form` targets, the clean exit), `backup` (snapshots and their second-precision stamp), `translations` (the translation store, saved before every POST), `links` and `layout` (the links above Submit, where rosters sit), `usage` (Jotform's storage against the plan's limits), `translation_lookup` (Jotform's names dictionary, emulated), `submissions` (reading a submission's answers), `salesforce` (the one Salesforce client, the org's ids, the processor's name match, `--vpn-off`; `sf_partners.csv` the partner map), `private_files` (owner-only files under `data/` and the append-only ledger) |
| **Tools in regular use** | |
| `tools/auto_sync.py` | The unattended loop run by GitHub Actions: export → plan → safety bands → backup → apply → verify → `SyncLog`; with `SF_SYNC`, new clubs' Salesforce accounts (`tools/sf_new_clubs.py`) |
| `tools/form_status.py`, `tools/integration_status.py` | Read-only audits: every form against the Roster export (`--roster`, required; rules, languages, drift, the module chain's shape, the names dictionary, Jotform's storage against the plan's limits; `--rendered` reads the public page); the Salesforce integration's mapping on every form and the other integration blocks a form carries |
| `tools/sheets_client.py` | Sheet access: `whoami`, `tabs`, `export`, `export-all`, and the functions the other tools import |
| `tools/rename_club.py`, `tools/deactivate_clubs.py`, `tools/disable_form.py` | A club renamed or moved to another partner; clubs taken off the forms (`--undo` puts the rows back); a regional form switched off or on |
| `tools/add_translations.py`, `add_language.py`, `restore_translations.py`, `switcher_flags.py`, `add_feedback_link.py`, `update_static_fields.py` | Languages and the switcher's flags, the links above Submit (problem report, Club Roster Form), the fields the sync never touches (labels, photo limits, header logo) |
| `tools/sf_new_clubs.py`, `tools/sf_dupes.py` | New clubs' Salesforce accounts (`check`: read only); one Salesforce contact per girl (`check` monthly; `plan`, `merge`) |
| `worklog/worklog.csv`, `worklog/timezones.csv` | The work log behind the monthly invoice, kept by the harness plugin's `harness-worklog` (`/harness:worklog`; RUNBOOK "Work log and invoices") |
| **Kept for undo or a future incident** | |
| `tools/fix_module_values.py` | The 2026-10-07 correction of Spanish module values in Salesforce; kept for its `--undo` until the end of October 2026 |
| `tools/sf_girls_present.py` | The back-fill of `Girls_Present__c` (done); its read-only `check` stays useful |
| `tools/fix_roster_order.py`, `tools/fix_name_translations.py` | One-time Jotform repairs (every roster above Submit; the stale name translations removed), each with its way back (`--undo`, `--restore`) |
| `tools/backfill_resolve.py`, `tools/sf_backfill.py` | The September 2026 back-fill of attendance into Salesforce; the procedure for a future missed-submissions incident (RUNBOOK "Back-fill of attendance into Salesforce") |
| `tools/upload_roster.py`, `tools/build_roster_offline.js` | The pre-launch offline Roster build and upload (never after launch; the builder's Partners columns are parity-tested) |
| (retired) | Finished one-offs, deleted, each with the commit that restores it: [docs/ARCHITECTURE.md, Retired tools](docs/ARCHITECTURE.md#retired-tools) |
| **Everything else** | |
| `appsscript/` | The scripts bound to the sheet: roster ids, form handlers, generated Google Forms, the sync notification — deployed with `npm run clasp:push` ([appsscript/INSTALL.md](appsscript/INSTALL.md)) |
| `test/` | Python tests found by `python3 -m unittest discover -s test -p '*_test.py'`, one file per subject (`sync_conditions_test.py`, `auto_sync_test.py`, `form_status_test.py`, `gs_parity_test.py`, `hooks_test.py`, …; shared fixtures as mixins in `test/helpers/common.py`); JavaScript suites `test/*_test.js` run the `.gs` code in Node (`test/load_gs.js`); `test/fixtures/` the synthetic enrollment with fictional names |
| `scripts/` | The checks behind `make check`: every `.py` parses and answers `--help` (`check_py.py`), `.gs` parsing, pinned Google services and resolvable calls (`check_gs.js`), secrets and personal data (`check_secrets.py`), links (`check_docs_links.py`), quoted RUNBOOK sections and BACKLOG numbers (`check_doc_refs.py`), the plans index (`docs_index.py`); outside `make check`, `harness_tests.sh` (runs the test files a ticket names: Python by basename through `unittest discover -s test`, JS with `node`), `verify.sh` (the verify command: `make check`, then `VERIFY OK`) and `capture_readonly.sh`, a GET-only capture of the audit and the sync's dry runs to diff before and after a refactor |
| `.githooks/` | `pre-commit` for commits made outside Claude Code (installed by `make hooks`) |
| `Makefile` | `make check` (lint, tests, the checks above, conflict markers, the fixture), `make lint`, `make docs-index`, `make help` |
| `.claude/` | Claude Code guardrails: hooks that block live-system writes and edits of personal data, secrets or the guardrails themselves, and scan every written file; skills for the Jotform API, the privacy policy, the live systems and Salesforce; agents |

## Docs

[docs/README.md](docs/README.md) is the index: runbook, architecture, decisions, backlog, and
the plans under `docs/plans` (kept only for changes with a live rollout, beside their ticket; an
intent under `docs/intent` is optional; the launch notes are in `docs/archive`).
`CLAUDE.md` is the one-page briefing for Claude; `REVIEW.md` the review policy.

## Safety properties

- Dry run by default everywhere; `--apply` is required to write anything. In Claude Code the
  live gate (`.claude/hooks/live_gate.sh`) blocks the write commands it recognises unless the
  human exported `GLOW_LIVE_OK=1` before starting it; Salesforce writes through the session's
  connector are not seen by it and need the human's go.
- A snapshot before every live write, stamped to the second (`backups/<form>/`): the runner
  and most writers take their own; by hand, `backup_forms.py --form` before the sync or
  `update_static_fields.py`. The translation writers save the whole store before a POST
  replaces a language (`backups/translations/`); the Mac's Salesforce writers keep a ledger or a
  rollback file under `data/` before their first write.
- Existing roster questions are updated, never deleted (`--prune` only on a fresh clone); girls
  are deactivated, never removed.
- Conditions are regenerated from scratch every run — no rule drift; snapshots and Jotform's
  Revision History are the rollback path.
- The tools exit with an error instead of guessing (an ambiguous club name with no partner
  information anywhere, a truncated export).
- The unattended sync applies only small, verified changes; anything else waits for a human.
- No key and no girl's name enters git: `make check`, the Claude hook and the pre-commit hook
  scan for keys, ids and girl-ID patterns; tests and docs use fictional names.

## How the form logic is organized

Every sync run writes three cleanly separated groups of rules: **roster visibility** (one per
club — `IF Club equals "<club>" SHOW <roster>`; a club whose name another partner's club shares
has its own picker entry, `<club> - <partner>`, and its rule tests that entry; only rosters that
still share one entry — a form without the picker, or one not switched yet — also require the
Partner box), the **curriculum cascade** (Year → Module → Session dropdowns; sessions per elective
module come from `glow/sync.py` `SESSION_OVERRIDES`), and the **Salesforce bridge** (year/module/session copies
into hidden fields, the picked club copied into the Club Name field Salesforce reads, and one
aggregate `Contact_IDs` calculation over every roster with "ignore hidden fields" on, so exactly
the visible club's ticked names come through; with the Club picker it is the first rule and lists
the picker, so it is recalculated after the rosters show or hide). Every roster is required:
Jotform refuses a submission whose shown roster has no girl ticked. Details:
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
