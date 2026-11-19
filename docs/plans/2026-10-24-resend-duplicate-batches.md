---
title: The corrections failed as "Duplicate" before 2026-10-24 re-sent, so the processor merges their missing girls
author: Claude (with Ryan's request of 2026-10-22)
status: done      # ticket #153: group A re-sent 2026-10-26; group B and 9 later corrections 2026-11-19
done: 2026-11-19
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
- `test/sf_backfill_resend_test.py` (new, 20 tests) and `test/helpers/fake_org.py` (the merge
  rule and a generic SOQL reader), by the test author.
- `docs/RUNBOOK.md`, `docs/ARCHITECTURE.md`, `.claude/skills/salesforce/SKILL.md`, this plan.
- Nothing in Salesforce's metadata, no form, no sheet, nothing under `appsscript/`.

## Design
1. Read every `Failed` batch whose message starts `Duplicate:` created since `--since` (default
   2026-09-07), in `CreatedDate` order; the message is filtered on, never selected or printed.
2. For each, predict in memory by the processor's merge rule: the day's original (the oldest
   `Success`), refused as `no_success_original`, `original_not_mergeable` (a `Partner report` or
   no rows of its own), `module_differs`, `no_names`, `fuzzy_matching` (`enable_fuzzy_matching__c`
   true: the processor would match by edit distance, which the exact prediction cannot follow) or
   `adds_nobody`; else the girls it ticked
   without a row on that club and day (names cleaned as the processor cleans them, a name twice
   once), and how many get a new contact. Corrections of one day are predicted in order, each
   after the earlier ones. A copy of this tool is `own_batch`; a failed batch in the ledger is
   `already_resent`, whatever its outcome. A skipped batch is counted, never sent; `--only` on it
   refuses with `skipped, <reason>`. Names are read and compared inside the script only.
3. `--apply`: per candidate, the club and day read again (a changed prediction is refused before
   anything is sent), a `sending` ledger row, ONE insert - the failed batch's fields as they are,
   `Creator__c` `Jotform back-fill re-send <failed id>` - then the read-back: the copy `Success`
   `merged into <original id>`, no rows and no count of its own, the original's new rows and the
   club's new contacts written inside the copy's window (`CreatedDate` from the copy's
   `CreatedDate` to its `LastModifiedDate`, the processor's status update and its last write:
   nothing promises one timestamp to the second for the whole transaction) exactly as
   predicted, the original's `Girls_Present__c` its rows. A later correction merged into the
   same original falls after the window and never reaches the copy's rollback list; another
   batch of the club and day created inside the window (a correction that adds nobody, or one
   merged into the same original) makes the copy `CHECK`. Anything else is `CHECK` too and stops
   the line. Every row and contact in the window is listed by id in `resend_added.csv`, tied
   to its copy (`uncertain` `yes` when another batch landed in the window).
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
   and `Girls_Present__c` in Salesforce, counts only). Read-only: the copy's `CreatedDate` and
   `LastModifiedDate`, and the `CreatedDate` of the original's rows and contacts listed in
   `resend_added.csv` - each inside that window, and the original's growth since the send equal
   to the listed rows (counts and ids only).
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
  each copy. One merged after the copy's window (before its read-back or its settling) adds its
  rows to the same original with a later `CreatedDate`: the read-back neither counts them for the
  copy nor lists them in `resend_added.csv`, so the copy's rollback never removes a mentor's rows;
  a contact it creates still shows in the club's growth, and the copy is `CHECK`. One created
  inside the copy's window cannot be told apart from the copy by time: the copy is `CHECK`, its
  window's rows and contacts are listed marked `uncertain`, and the message says the list may be
  incomplete or hold the other batch's rows - checked by hand before any removal.
- **The window misses some of the copy's rows** (a processor write stamped outside
  [`CreatedDate`, `LastModifiedDate`]): fewer rows or contacts than predicted or than the
  original and the club grew by, so the copy is `CHECK` and the message says the rollback list
  may be incomplete (and does not claim the rows are listed); the copy's rows are then found by
  hand. Rollout step 3 checks the window on the first copy.
- **The prediction and the processor disagree** (a name the processor reads differently; a
  batch with fuzzy matching on is skipped as `fuzzy_matching`, never sent): the copy is `CHECK`, the line stops, the copy's rows and contacts are listed.
- **Several corrections of one day**: sent in order; `--only` refuses one whose earlier
  correction is not re-sent yet.

## Proof
- Offline: `scripts/harness_tests.sh test/sf_backfill_resend_test.py` (20 tests) and
  `make check` -> `CHECK PASSED`.
- Live: the read-back of every copy, and Rollout step 5.

## Result
2026-10-26, interactive session, VPN off, ticket #153; every write on Ryan's go at the live-gate prompt.
- **Step 1, the dry run** wanted 31 batches (189 girls, 42 new contacts, 16 clubs), not the trace's
  12 girls in 3 clubs. A read-only analysis split them: **group A**, 19 real corrections (14 clubs);
  **group B**, 12 batches of MINISTERIOS DE AMOR and Swopnajyoti that look like separate groups
  meeting the same day. Ryan's go (06:4x UTC): send A, hold B until GLOW confirms whether those
  groups should stay separate batches.
- **Steps 3-4:** the first copy with `--only` (BATCH-000408 -> BATCH-001232) was read back, then
  the other 18, one copy per call with `--only`. The terminal closed at 07:18 UTC after 17 copies.
  The ledger had no open `sending` row, so nothing was in flight. The dry run then showed
  `already_resent: 17`, and the last 2 were sent at 07:3x UTC (BATCH-001250, BATCH-001251).
- **Totals:** 19 copies (BATCH-001232 to BATCH-001251) re-sent and verified between 06:49:50 and
  07:35:59 UTC. They added 72 attendance rows to their originals and 12 new girls' contacts, in
  14 clubs. Every id is in `resend_ledger.csv` and `resend_added.csv`.
- **Step 5:** the dry run afterwards shows `already_resent: 19`, `adds_nobody: 56`,
  `module_differs: 3`, `no_names: 1` and `original_not_mergeable: 1`. It still lists
  `to re-send: 12 batches, 117 girls to add, 30 new contacts, 2 clubs`: that is group B, held.
  `tools/sf_girls_present.py check`: 1120 Jotform Success batches, differ 0, without a value 0 -> OK.
- **Group B sent, 2026-11-19** (Ryan's ruling of 2026-11-13: "Use your judgement for 153 group
  B"):
  - The first copy, BATCH-001853, failed. A release by another team on 2026-10-26 had replaced
    the processor with one that does not merge (#238).
  - BATCH-001853 was deleted on Ryan's go and closed `--removed`. The processor was restored at
    14:39 UTC (#238).
  - Then `resend --apply --vpn-off` sent 21 copies, BATCH-001854 to BATCH-001874, each read back
    ok. That was group B's 12 (Swopnajyoti through another failed copy of the same submission)
    and 9 corrections that failed while the processor was replaced.
  - In all, 160 attendance rows were added, with 23 new contacts, in 8 clubs.
  - `sf_girls_present.py check` afterwards: differ 0.
