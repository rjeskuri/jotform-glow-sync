---
name: salesforce
description: Salesforce for this project - what lives there (attendance batches and the Apex processor, club and partner accounts, reports and dashboards), the read and write paths (connectors, the sf CLI with the VPN off, the plan/apply tools, metadata deploys), and every writer's gate and rollback. Load before any Salesforce query, record write, sf command, deploy, report or dashboard change, or code that talks to Salesforce.
---

# Salesforce (production)

## What lives there
- **Attendance.** Each Jotform submission goes through the forms' native Salesforce V2
  integration (question 5 = the club's Account name, question 18 = the names list) and becomes one
  `Attendance_Batch__c`. The Apex attendance processor (after-insert trigger only, so a batch
  `PATCH` runs none of it) matches the club Account by name (capitals ignored; no match creates a
  partner-less Club account), finds or creates one Contact per ticked girl and writes the
  `Attendance__c` rows (master-detail on the Contact). A second batch for a club and date that
  already has a `Success` one (a mentor's corrected re-submission; since 2026-10-22, #108) is
  merged into the oldest `Success` batch of that club and date when its `Module__c` is the same:
  only the girls not yet on that date get an `Attendance__c` row, as rows of that original batch,
  whose `Girls_Present__c` moves to its row count; the correction is `Success` with
  `Status_Message__c` `merged into <original batch id>`, no count and no rows of its own. A
  different module, or a correction that adds nobody, is `Failed` "Duplicate" as before (never a
  row removed, never a girl twice). `Girls_Present__c` on the batch is the one attendance count:
  set by the processor on `Success`, moved on a merge, typed in for partner-reported aggregates
  (RUNBOOK "Attendance totals and partner-reported counts").
- **Accounts.** Every active club has a Club account (record type Club) named exactly as question
  5 sends it, parented to its partner's account (`glow/sf_partners.csv`). Never rename a club in
  Salesforce first: a rename starts in the sheet (RUNBOOK "Renaming a club").
- **Duplicate and obsolete flags.** `Duplicate_Record__c` and `Obsolete_Record__c` ("Duplicate
  Record", "Obsolete Record") on Account and Contact, set by hand by administrators alone and by
  rule by the flagging batch (#85): `RecordFlagBatch`, run as anonymous Apex on a script
  `tools/sf_record_flags.py` writes (ids only; the Contact script only while the guard's three
  counts are 0; `clear` mode is the rollback; RUNBOOK "Duplicate and obsolete records in
  Salesforce", The flagging batch). The Matching Rule `Account.Name_Parent` (same name ignoring
  capitals and spacing, same parent) and one Duplicate Rule per record type, Club and Household
  (`Account.Name_Parent_Club_Report`, `Account.Name_Parent_Household_Report`, the condition Record
  Type equals that type), are Allow with Report only, no Alert and no Block, because an alert
  refuses a record created by code (BACKLOG 54: the processor's partner-less Club accounts,
  `tools/sf_new_clubs.py`). Flagged records are shown in the reports, the flags a filter (RUNBOOK
  "Duplicate and obsolete records in Salesforce").
- **Reports and dashboards**: the "Jotform Attendance" dashboard and its reports, the
  `Attendance_Totals` report type, the `Attendance_Report_Viewer` permission set (RUNBOOK
  "Attendance dashboard in Salesforce"); the Monthly Report (`DHIS2__c`) reports and dashboards
  and the two hidden Decommissioned folders (RUNBOOK "Monthly Report dashboards in Salesforce");
  the interactive dashboard, LWC `glowDashboardShell` (RUNBOOK
  "Interactive dashboard in Salesforce"). The archive rule (DECISIONS 2026-10-21): a retired report or dashboard is moved
  to Decommissioned and keeps its Id, never deleted; before a report or dashboard changes, a copy
  of it as it was goes to Decommissioned, carrying its source Id and the ticket.
- **The SF Pending tab** in the sheet lists new clubs still without an account; the Monday e-mail
  sends it to staff; the automatic sync marks a row `done (auto <date>)` when it creates one.
- `glow/salesforce.py` holds the org's record-type ids, `sf_match` (the processor's name
  comparison), `error_codes`, the partner map and `--vpn-off`; private files and ledgers:
  `glow/private_files.py`.

## Access
- **VPN off before any `sf` command or any tool that talks to Salesforce from the Mac.**
  Salesforce freezes a user whose connection comes through an anonymising VPN and revokes all their
  tokens, the Jotform connection's included (2026-09-30); only another administrator can unfreeze,
  then Jotform is re-authorised on the five forms (`tools/integration_status.py`). Check with
  `scripts/vpn_check.sh`, run as its own call (allowed alone, no prompt): `vpn: off` (exit 0), or
  `vpn: on <iface>` (exit 1: a tunnel carries the default route or holds an IPv4 address), and it
  fails closed when it cannot tell. Never probe inline (`route -n get default | grep interface && sf
  ...`, an `ifconfig` loop). The tools refuse without `--vpn-off`, the word that you checked, and run
  the same check before they call: a tunnel that is up refuses even with `--vpn-off` (#251).
- **One live command per call** (#251): each `sf` command or live tool alone in its Bash call, with
  nothing in front - no `cd`, no VPN probe, no `.env` sourcing (`set -a; . .env; set +a; ...`), no
  variable assignments (`F=...;`) - from the checkout, with `-o glow` and the tools' own paths and
  flags (`--source-dir data/sf_<topic>/after`, `--dir`, `--plan`). The live gate sees through three
  wrappers only, judging what they wrap as it would alone: a leading `cd <a folder inside the
  checkout> &&`, a leading `scripts/vpn_check.sh &&`, and a trailing `| jq <filter>` or
  `| python3 -c '<snippet>'` that reads standard input only (jq: `-r -c -e -j -S -M -s -a` and one
  filter, no `$`/`env`/`import`; python3: imports from json, sys, csv, collections, re, math,
  statistics, datetime, itertools, and nothing that opens a file, runs a program or reads the
  environment). Anything else chained or in front asks Ryan, as before.
- **Reads**: the read-only connector `Global_Glow_SF` (`soqlQuery`, `getObjectSchema`, …); or
  Ryan's CLI login, alias `glow` (`sf data query -q "..." -o glow --json`, `sf org display
  --target-org glow`). A plain `sf data query` passes the live gate with no prompt (#204; an
  `--output-file` only inside `data/`), alone or piped into a read-only jq or `python3 -c` as above.
  An ad-hoc read is one of these, never Python from standard input (`python3 -`) or a scratchpad
  script; a one-off live script is a file under its plan folder (`data/sf_<topic>/`), where the
  gate (an Apex `--file`) and Ryan can read it.
  Never `sf org auth show-access-token`, `show-sfdx-auth-url`, `show-user-password` or
  `SF_TEMP_SHOW_SECRETS`: they print the token.
- **Record writes**: the write connector `Global_Glow_Full_Access`, one record per call, by the
  main session only (never a subagent), on Ryan's go in the conversation, read back after. No hook
  sees connector calls. Bulk changes go through the plan/apply tools below, which keep ledgers.
- **Metadata** (Apex, fields, reports, dashboards, permission sets, folders): retrieve what is
  live into a dated `before/` folder → check-only (`sf project deploy validate -o glow …` with the
  tests an Apex change needs, or `sf project deploy start --dry-run`) → the go (below) → quick deploy
  of the validation (`sf project deploy quick -o glow -i <validation id>`) or the same `start` without
  `--dry-run` → retrieve again and compare with the build. Since #204 the check-only run passes the
  hook with no prompt and no backup when it is one plain command: `validate` or `start --dry-run`
  with `-d`/`--source-dir`, `-x`/`--manifest` or `-m`/`--metadata`, and only `-o`, `-l`, `-t`,
  `-w`, `--api-version`, `--json`, `--concise`, `--verbose` beside them (destructive changes, a
  `--metadata-dir` or another flag: judged as a deploy). The deploy itself (since 2026-10-26, #146)
  goes through automatically when it names the plan folder `data/sf_<topic>/` and its `before/`
  holds a file from today; a `quick` deploy by its id names no folder and asks Ryan. A `start` needs an explicit source too (`--source-dir`,
  `--manifest` or `--metadata`), and `sfdx force:source:push` always asks: a source-tracked
  deploy carries local deletions the hook does not see (Ryan, 2026-11-06). Claude Code's auto mode may refuse a production deploy
  (2026-10-02): then Ryan runs it.
  **Never redeploy an older build** (Ryan, 2026-10-16): every deploy, a rollback included, edits a
  fresh retrieve of what is live; a `before/` is a rollback only for its own change, only for the
  components that change made, and only while a fresh retrieve of them still equals that change's
  `after/` (DECISIONS 2026-10-16).
- **Names never reach the conversation, a log or the repo.** SOQL selects explicit fields: counts,
  ids, dates, statuses, club names. Never select a Contact's name, `Contact_IDs__c` or
  `Status_Message__c` (filter on them, do not print them), never `GET /sobjects/<type>/<id>`.
  An error is reported by its codes only (`glow.salesforce.error_codes`: `DUPLICATES_DETECTED`,
  `UNABLE_TO_LOCK_ROW`), never its words or a response body: a message can quote a girl's name.

## Writers (one per row; the Gate column says which the live gate lets through automatically and which ask Ryan)
| Writer | What it changes | Gate | Rollback |
|---|---|---|---|
| Write connector `Global_Glow_Full_Access` | One record per call (a Club account by hand, a `ParentId`, a permission-set assignment) | Ryan's go only; no hook sees it | The record's values read before the write; a created account is deleted only while it has no Contacts and no attendance |
| `tools/sf_backfill.py send --apply` | New attendance batches (the processor makes the contacts and rows) | Hook: automatic on its own `ledger.csv` row (#146), `--vpn-off`, `--limit 1` first | By id from `ledger.csv` and `created_contacts.csv`, never a time window; never delete a back-fill contact that carries live rows (BACKLOG 78) |
| `tools/sf_backfill.py resend --apply` | A copy of each Failed "Duplicate" correction since 2026-09-07; the processor merges its missing girls into the day's original batch (rows, new contacts, the original's `Girls_Present__c`) | Hook: automatic on its own `resend_ledger.csv` row (#146), `--vpn-off` (dry run too), `--limit 1` first | By id from `resend_ledger.csv` and `resend_added.csv`: the added rows, the contacts only while they carry no other rows, the copies; each original's `Girls_Present__c` back to its own rows |
| `tools/fix_module_values.py --apply` | `Module__c` on batches and their rows | Hook: asks (not on the gate's list), `--vpn-off` | `--undo <ledger> --vpn-off --apply` |
| `tools/sf_partner_monthly.py --apply` | One `Partner report` batch per partner a month (the three partners' Monthly Max), or its `Girls_Present__c` when the report changed | Hook: automatic on its own `ledger.csv` row, `--vpn-off`, `--limit 1` first | By id from `data/sf_partner_monthly/ledger.csv`: delete an inserted batch, set an updated one back to its `old` count |
| `tools/sf_report_folders.py copy`, `move`, `undo` with `--apply` | `copy`: a clone of a report or dashboard in Decommissioned; `move`: a report's folder and label (its Id kept); `undo`: those moves put back. Never a dashboard's folder or name (by hand in Lightning) and never the Attendance folders | Hook: automatic on its own `ledger.csv` row, `--vpn-off`, `move --limit 1` first | `undo --ledger data/sf_report_folders/ledger.csv --vpn-off --apply`, last first; a copy stays in Decommissioned |
| `tools/sf_girls_present.py set --apply` | `Girls_Present__c` on `Success` batches that had none | Hook: automatic on its own `ledger.csv` row, `--vpn-off` | The ledger (`data/sf_girls_present/`) lists every batch written; no undo command |
| `tools/sf_dupes.py merge --rehearse` | The merges' DML in production, then thrown and rolled back (records locked, triggers run) | Hook: automatic on its own `merge_rollback.json`, `--vpn-off`, the same quiet moment as `--apply` | Nothing left; should one keep a change, `merge_rollback.json` |
| `tools/sf_dupes.py merge --apply` | Duplicate contacts of one girl merged (anonymous Apex, one all-or-nothing run per club) | Hook: asks (a merge deletes a record), `--vpn-off`; after the dry run and `--rehearse` | `merge_rollback.json`: undelete within 15 days, rows inserted again |
| `tools/sf_dupes.py rename --apply` | A stored name's whitespace | Hook: asks (every `sf_dupes.py --apply`), `--vpn-off` | The `renames` old values |
| `tools/sf_dupes.py cleanup --apply` | Extra affiliations and duplicate-rule sets deleted | Hook: asks (a delete), `--vpn-off` | Each deleted record is saved in the rollback file first |
| `tools/auto_sync.py --apply-salesforce` (GitHub Actions, as Ryan's own user through the External Client App GLOW Sync (client credentials), through `tools/sf_new_clubs.py`) | Creates new clubs' Club accounts (at most 5 per region per run) and marks their SF Pending rows | `SF_SYNC=apply` and `AUTO_SYNC_APPLY=1`, repository variables that only Ryan changes | `SF_SYNC=off`; a created account (Description `created by the automatic sync <date>`; `CreatedById` is Ryan's, not the sync's) is deleted only while it has no Contacts and no attendance. A freeze of Ryan's user also revokes the Jotform connection (RUNBOOK "New clubs' accounts, automatically", The risks of running as Ryan) |
| `sf project deploy validate`, `start`, `quick` | Metadata | Hook: a plain check-only run (`validate`, `start --dry-run`, with an explicit source) passes with no prompt and no backup (#204); otherwise automatic when the command names `data/sf_<topic>/` and its `before/` holds a file from today (a `start` only with `--source-dir`, `--manifest` or `--metadata`), else asks; destructive changes ask (a `destructiveChanges*.xml` in a folder it deploys too); a `--metadata-dir` deploy always asks, and so does one with `--flags-dir` (each flag's value from a file the hook does not read, a `--post-destructive-changes` too) | Redeploy only the components that change made, from its `before/`, after a fresh retrieve of them equals its `after/`, never an older build (2026-10-15: RUNBOOK "Attendance dashboard in Salesforce", Rollback); a `destructiveChanges.xml` for new components |
| `sf apex run` (the rolled-back proof of a processor change) | Inserts inside a transaction that ends in `Database.rollback` | Hook: automatic as for a deploy, only with `--file` naming a file in the checkout the hook reads (`data/sf_<topic>/…`), else asks; a file with `delete`, `merge`, `undelete` or `emptyRecycleBin` asks; the script pasted in full first | Nothing left, unless the script misses its rollback call |
| `sf apex run -o glow -f <script>` of `RecordFlagBatch` in `flag` or `clear` mode (the script from `tools/sf_record_flags.py`, ticket #85) | `Duplicate_Record__c` and `Obsolete_Record__c` on every Account or Contact whose flag changes, in scopes of 200 | Hook: as for `sf apex run` above (automatic only with the script in its `data/sf_record_flags_<date>/` folder and a `before/` there from today, else asks); `dryRun` first and its counts confirmed by Ryan; the Contact script only while the guard's three counts are 0; a quiet hour; the script pasted in full first | `clear` mode (the hand-set flags come off too: counted first), or the saved ids `data/sf_record_flags_<date>/flagged.csv` record by record |
| `sf data create`, `update`, `delete`, `upsert`, `import` | Records | Hook: automatic as for a deploy, else asks; `delete` always asks | Prefer the write connector (one record) or a tool with a ledger |
| `sf api request rest` with a method other than GET, a body (`-b`/`--body`), a request file (`-f`/`--file`) or `--flags-dir`; `sf api request graphql` | Anything | Hook: automatic as for a deploy only with the whole request on the command line (`-X`, an inline `--body '{…}'`; the response may go to `-S <file>`), else asks; a request file (`-f`), a body from a file or standard input (`--body @file`, `--body -`, a `<`), `--flags-dir` and every `sf api request graphql` always ask (review 2 of PR #154: what the hook does not read can hold a DELETE); a DELETE always asks (a GET without a body or file passes: a read); a dashboard refresh (`PUT` on `/services/data/vNN.N/analytics/dashboards/<id>` with no body or `-b '{}'`, beside only `-o`, `-i` or `--api-version`) and a GET of it or its `/status` pass with no prompt and no backup (#204), and a `filters` body or a `?filter1=` path is judged as a write | As for the record or metadata it changed |

`SF_SYNC` is `off` (or unset: no login), `plan` (reads, checks, and turns every account it would
create into an ATTENTION item with the exact body) or `apply`. `gh variable set SF_SYNC …` and
`gh variable set AUTO_SYNC_APPLY …` are Ryan's to decide; the hook lets one through without a
prompt only on a `github all` backup from today (`tools/github_switches.py backup`), and asks
him otherwise (RUNBOOK "New clubs' accounts, automatically"; "Live gate (Claude Code)").

## Where the files go
Salesforce metadata and Apex are not in git. Every retrieve, build and piece of evidence lives
under `data/` (never committed, owner-only): `data/sf_<topic>_<date>/` with `before/` (the
retrieve that is the rollback), `after/` or a named build folder (what was deployed, with
`sfdx-project.json`), and `evidence/` (the queries behind a decision), e.g.
`data/sf_dashboard_2026-10-02/`, `data/sf_totals_2026-10/`. The tools keep their ledgers and
rollback files there too (`data/backfill_2026-09/`, `data/sf_dupes_<date>/`,
`data/sf_girls_present/`, `data/module_fix_2026-10/`). Only counts go into a plan or a message.

## The procedures (RUNBOOK)
RUNBOOK "Club accounts in Salesforce" (by hand, the Signals), "New clubs' accounts,
automatically" (`SF_SYNC`, the GLOW Sync app, its risks and rollback, the ATTENTION table), "Duplicate girls in
Salesforce" (the monthly check, the merge, the rollback per part), "Attendance totals and
partner-reported counts" (the intake contract), "Attendance dashboard in Salesforce" (the steps,
Access, rollback), "Back-fill of attendance into Salesforce", "Credentials" (the CLI login) and
"Live gate (Claude Code)". Live writes outside Salesforce: `.claude/skills/live-systems`.
