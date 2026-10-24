---
title: The corrections failed as "Duplicate" before 2026-10-24 re-sent, so the processor merges their missing girls
author: Claude (with Ryan's request of 2026-10-22)
status: proposed         # ticket #109; tool built and tested offline, the live run waits for Ryan's go
created: 2026-10-24
intent: none - Ryan's request of 2026-10-22 (ticket #109, epic #93): bring in the 12 girls the 2026-10-22 trace found missing, once the processor accepts a correction (#108)
---

# Plan: re-send the Failed "Duplicate" corrections (ticket #109)

## Context
- The 2026-10-22 trace found 12 girls ticked only in corrected re-submissions that the processor
  failed whole as `Duplicate` (three clubs: 7, 1 and 4 girls; ids on the ticket). Since
  2026-10-24 06:48 UTC the processor merges such a correction into the day's original batch
  ([correction merge](2026-10-22-correction-merge.md), ticket #108), but a Failed batch is never
  processed again: the trigger runs on insert only.
- The read-only check of 2026-10-24 counted 22 Failed `Duplicate` batches since 2026-09-07 on the
  three named clubs alone, often several corrections for one day; all 83 Failed batches since
  2026-09-07 are this rule (the #108 plan).
- `tools/sf_backfill.py send` refuses any club and day that already has a batch, so it cannot
  re-send these. A new subcommand, `resend`, does (RUNBOOK "Back-fill of attendance into
  Salesforce", "Re-send of the corrections failed as "Duplicate"").

## Files that change
- `tools/sf_backfill.py`: `resend` (dry run by default, `--apply`, `--limit`, `--only`, `--since`,
  `--vpn-off` in both modes); `close` and `status` read its ledger too.
- `test/sf_backfill_resend_test.py` (new, 13 tests) and `test/helpers/fake_org.py` (the merge
  rule and a generic SOQL reader), by the test author.
- `docs/RUNBOOK.md`, `docs/ARCHITECTURE.md`, `.claude/skills/salesforce/SKILL.md`, this plan.
- Nothing in Salesforce's metadata, no form, no sheet, nothing under `appsscript/`.

## Design
1. Read every `Failed` batch whose message starts `Duplicate:` created since `--since` (default
   2026-09-07), in `CreatedDate` order; the message is filtered on, never selected or printed.
2. For each, predict in memory by the processor's merge rule: the day's original (the oldest
   `Success`), refused as `no_success_original`, `original_not_mergeable` (a `Partner report` or
   no rows of its own), `module_differs`, `no_names` or `adds_nobody`; else the girls it ticked
   without a row on that club and day (names cleaned as the processor cleans them, a name twice
   once), and how many get a new contact. Corrections of one day are predicted in order, each
   after the earlier ones. A copy of this tool is `own_batch`; a failed batch in the ledger is
   `already_resent`, whatever its outcome. Names are read and compared inside the script only.
3. `--apply`: per candidate, the club and day read again (a changed prediction is refused before
   anything is sent), a `sending` ledger row, ONE insert - the failed batch's fields as they are,
   `Creator__c` `Jotform back-fill re-send <failed id>` - then the read-back: the copy `Success`
   `merged into <original id>`, no rows and no count of its own, the original's new rows (by
   `CreatedDate` >= the copy's) and the club's new contacts exactly as predicted, the original's
   `Girls_Present__c` its rows. Anything else is `CHECK` and stops the line. Every added row and
   created contact is listed by id in `resend_added.csv`, tied to its copy.
4. The original Failed batches stay as they are (history). A copy carries no `Submitted_At__c`
   (its `Creator__c` is not `Jotform`), so the timing reports of #101 do not see it.

## Rollout
Each write on Ryan's go in the conversation; VPN off; from the main checkout (the ledger lives in
`data/backfill_2026-09/`, the default `--dir`, which a worktree's land deletes).
1. Dry run: `python3 tools/sf_backfill.py resend --vpn-off`; compare its candidates with the trace's
   12 girls (three clubs: 7, 1, 4 girls to add), counts only. Any other candidate is shown to
   Ryan before the go.
2. Ryan's go.
3. `resend --apply --vpn-off --limit 1`; read back (the tool does; `status`; the original's rows
   and `Girls_Present__c` in Salesforce, counts only).
4. Then the rest: `resend --apply --vpn-off`.
5. Afterwards: the dry run shows `to re-send: 0 batches`, every candidate `already_resent`;
   `tools/sf_girls_present.py check` OK; counts in Result; the plan `done`, `make docs-index`.

## Rollback
By id, never by a time window, only with Ryan's go: the attendance rows in `resend_added.csv`,
then each listed contact only while it carries no other attendance row (deleting a contact
deletes its rows), then the copies (`batch_id` in `resend_ledger.csv`); each original's
`Girls_Present__c` set back to its own rows; `close <failed id> --removed` for each. The failed
batches were never touched.

## Risks
- **A live correction between the dry run and the send**: refused by the fresh prediction before
  each copy, and the read-back catches what lands in between.
- **The prediction and the processor disagree** (a fuzzy match, a name the processor reads
  differently): the copy is `CHECK`, the line stops, the copy's rows and contacts are listed.
- **Several corrections of one day**: sent in order; `--only` refuses one whose earlier
  correction is not re-sent yet.

## Proof
- Offline: `scripts/harness_tests.sh test/sf_backfill_resend_test.py` (13 tests) and
  `make check` -> `CHECK PASSED`.
- Live: the read-back of every copy, and Rollout step 5.

## Result
Pending: the live run (Rollout steps 1-5) waits for Ryan's go.
