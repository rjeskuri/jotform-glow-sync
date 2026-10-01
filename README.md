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
make venv                 # .venv with the Google Sheets libraries and ruff
npm install               # clasp 2.4.2 (Node 18) for the Apps Script deploy
make check                # the offline feedback loop: must print CHECK PASSED
cp .env.example .env      # then fill in the Jotform key; load with: set -a; source .env; set +a
```

Sheet access (service account) is described in [docs/SHEETS-ACCESS.md](docs/SHEETS-ACCESS.md);
every operational procedure, with its dry-run and apply forms, in
[docs/RUNBOOK.md](docs/RUNBOOK.md).

## What is where

| Path | What it does |
|---|---|
| `glow/` | The shared library every tool imports: the one Jotform client (dry-run gated), the one form-id table, the text helpers, the parsers and structural question ids |
| `sync_attendance_form.py` | The product: makes one form match the Roster export — rosters, the Club picker, and every condition. Dry run by default, `--apply` writes |
| `backup_forms.py`, `restore_conditions.py` | Snapshot a form; roll its conditions back |
| `tools/auto_sync.py` | The unattended loop run by GitHub Actions: export → plan → safety bands → backup → apply → verify → `SyncLog` |
| `tools/form_status.py` | Read-only audit of every form against the Roster (rules, integration, languages, drift) |
| `tools/sheets_client.py`, `tools/upload_roster.py`, `tools/build_roster_offline.js` | Sheet access; rebuilding and uploading the Roster tabs offline with the same `.gs` code |
| `tools/needs_attention.py`, `tools/derive_partner_regions.py` | Data-quality report; partner → region derivation (generates `appsscript/Regions.gs`) |
| `tools/add_translations.py`, `add_language.py`, `restore_translations.py`, `add_feedback_link.py`, `clone_regional.py` | Languages, the links above Submit (problem report, Club Roster Form), building a regional form |
| `tools/fix_roster_order.py` | One-time repair: every roster above the links and Submit (moves the links, Submit and the hidden fields after the last roster; `--undo` rolls back) |
| `tools/backfill_resolve.py` | September back-fill, read-only: every attendance submission as one row per ticked roster in `data/backfill_2026-09/resolved.json` (holds names; prints counts only) |
| `appsscript/` | The scripts bound to the sheet: roster ids, form handlers, generated Google Forms, the sync notification — deployed with `npm run clasp:push` ([appsscript/INSTALL.md](appsscript/INSTALL.md)) |
| `test/`, `scripts/`, `Makefile` | `make check`: parity between the Python and Apps Script parsers, roster-change logic, the runner's decisions, `.gs` parsing, secrets/PII and dead-link scans |
| `.claude/` | Claude Code guardrails: hooks that block live-system writes and PII/secret edits, skills encoding the Jotform API and privacy policy, review agents |

## Docs

[docs/README.md](docs/README.md) is the index: runbook, architecture, decisions, launch notes,
backlog, and the intent → spec → plan trail under `docs/intent`, `docs/specs`, `docs/plans`.
`CLAUDE.md` is the one-page briefing for Claude; `REVIEW.md` the review policy.

## Safety properties

- Dry run by default everywhere; `--apply` is required to write anything; Claude Code cannot
  run a write unless the human exported `GLOW_LIVE_OK=1`.
- Existing roster questions are updated, never deleted; girls are deactivated, never removed.
- Conditions are regenerated from scratch every run — no rule drift; snapshots and Jotform's
  Revision History are the rollback path.
- The tools exit with an error instead of guessing (an ambiguous club name with no partner
  information anywhere, a truncated export).
- The unattended sync applies only small, verified changes; anything else waits for a human.

## How the form logic is organized

Every sync run writes three cleanly separated groups of rules: **roster visibility** (one per
club — `IF Club equals "<club>" SHOW <roster>`; a club whose name another partner's club shares
has its own picker entry, `<club> - <partner>`, and its rule tests that entry; only rosters that
still share one entry — a form without the picker, or one not switched yet — also require the
Partner box), the **curriculum cascade** (Year → Module → Session dropdowns; sessions per elective
module come from `SESSION_OVERRIDES`), and the **Salesforce bridge** (year/module/session copies
into hidden fields, the picked club copied into the Club Name field Salesforce reads, and one
aggregate `Contact_IDs` calculation over every roster with "ignore hidden fields" on, so exactly
the visible club's ticked names come through). Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
