---
title: Restore the attendance processor after another team's release overwrote it on 2026-10-26
author: Claude (ticket #238, found 2026-11-19 while re-sending #153 group B)
status: done      # ticket #238; processor restored 2026-11-19 14:39 UTC; Jotform reconnected and back-filled the same day
created: 2026-11-19
done: 2026-11-19
intent: Ryan, 2026-11-19 - "That is Cyntexa. They are handling different work, so let's fix the attendance processor" (option 1, redeploy ours)
---

# Plan: restore the attendance processor

Ticket #238. Procedures: RUNBOOK "Attendance totals and partner-reported counts", "Back-fill of
attendance into Salesforce"; skill `.claude/skills/salesforce`.

## Context

- On 2026-10-26 Cyntexa (another team working in GLOW's org: a partner portal, expenses, error
  logging) released 172 components as another System Administrator user: check-only
  `0AfRP000002i8NJ0AY` and `0AfRP000002i8S90AI`, then deploy `0AfRP000002i8aD0AQ` (09:41:06 UTC,
  168 tests). It **changed `AttendanceBatchProcessor`, `AttendanceBatchProcessorTest` and
  `AttendanceBatchTriggerTest`**. `AttendanceBatchTrigger` was not in it.
- Their processor was the class as it stood before our first fix (2026-10-02): the same methods as
  `data/sf_processor_2026-10-02/before/`. Its only change was a `try/catch` around every method,
  logging to their `ErrorLogger` and returning null. This replaced our save's rethrow.
- It dropped every change since 2026-10-02:
  - one insert per batch (2026-10-02);
  - `Girls_Present__c` (2026-10-07);
  - name cleaning (BACKLOG 75, 2026-10-07);
  - merging a mentor's correction into the day's original batch (#108, 2026-10-22/24).
- Measured 2026-11-19 (counts only):
  - 0 corrections merged after the release;
  - 562 Success Jotform batches created since with a blank `Girls_Present__c` (all 239 of November);
  - 21 Failed "Duplicate" corrections that add girls (#153's group B and 9 new);
  - the ~24-girl ceiling did not come back (the largest batches since have 35, 31 and 30 rows).
- Not part of this restore: no Jotform batch has reached Salesforce since 2026-11-13 06:01 UTC
  (B on the ticket; checked separately with `tools/integration_status.py`).
- Work folder (owner only, never committed), in the ticket worktree's
  `data/sf_processor_2026-11-19/`: `before/` (today's retrieve of the three classes and the
  trigger: their version, the rollback), `build/`, `after/`, `validate*.json`.

## Rollout

Each Salesforce call with the VPN off; the deploy on Ryan's go.

1. Retrieve the live classes and trigger into `before/`.
2. Build: `AttendanceBatchProcessor` and `AttendanceBatchTriggerTest` exactly as deployed on
   2026-10-24 (`data/sf_processor_2026-10-22/deployed_2026-10-24/`, our last live version).
   Their `AttendanceBatchProcessorTest` from `before/`, with two methods adapted to our processor:
   - `testEmptyContactNamesAndNoMatchExact` expects `Failed`: a batch with no names fails, by the
     processor's rule.
   - `testCatchBlocksAndErrorLoggerExecution` becomes `testDirectCallsWithIncompleteBatches`. It
     inserts the single-word batch through the trigger and asserts that it gets a status. The
     `process(null)` and null-item calls are inputs the trigger never sends. The batch without a
     club name cannot be inserted, because `Account_Name__c` is required.
   The trigger is unchanged and not deployed.
3. Check-only with `RunSpecifiedTests` on both test classes; Ryan's go; quick deploy of that
   validation; retrieve `after/` and compare with `build/`.
4. Prove a merge live: `tools/sf_backfill.py resend --apply --vpn-off --limit 1`, then the rest.
5. `tools/sf_girls_present.py plan`, `set --apply --vpn-off`, `check`.
6. Ask Cyntexa to leave the Attendance classes out of their releases, or to retrieve from
   production first (Ryan).

## Rollback

After a fresh retrieve of the three classes equals `after/`, deploy `before/`'s three classes,
their version, with their two test classes (DECISIONS 2026-10-16: only the components this change
made). Corrections would then stop merging again and `Girls_Present__c` would stay blank. The
batches the re-send added stay: the RUNBOOK's re-send rollback, by id from
`data/backfill_2026-09/resend_ledger.csv` and `resend_added.csv`.

## Result

- Check-only runs:
  - `0AfRP000002kcVm0AI` (our test class only): 41 tests, 0 errors, 93% coverage.
  - `0AfRP000002kd5F0AQ`: failed, because their test class's two methods expect their behaviour.
  - `0AfRP000002kdLN0AY` and `0AfRP000002kdOb0AI`: failed while adapting those two methods.
  - **`0AfRP000002kdTR0AY`**: 3 components, 48 tests, 0 errors, 93% coverage.
- **Deploy `0AfRP000002kdV30AI`, 2026-11-19 14:39:11 UTC, quick deploy on Ryan's go.** The
  retrieve after equals the build for all three classes.
- Re-send, 2026-11-19, 21 copies, each verified:
  - The first, BATCH-000618 → BATCH-001854 (Swopnajyoti), merged 14 rows with 0 new contacts.
  - Then 20 more, BATCH-001855 to BATCH-001874.
  - In all, 160 rows added and 23 new contacts, in 8 clubs.
  - The morning's copy BATCH-001853, made under their processor (Failed, 0 rows), was deleted on
    Ryan's go and closed `--removed`.
- `Girls_Present__c`: 557 Success batches set and read back (8,115 rows;
  `data/sf_girls_present/ledger.csv`). `sf_girls_present.py check`: 1,683 Jotform Success
  batches, differ 0, without a value 0.
- Duplicate-girls check (`sf_dupes.py check`): 1 group, 1 extra contact in one club, created
  2026-10-30 (left for the monthly merge).

### B: Jotform delivery, stopped 2026-11-13 06:01 UTC

- Cause: Ryan's user was frozen. LoginHistory shows 'User is Frozen' for the browser until
  2026-11-15 05:27 UTC and for GLOW Sync until 17:30 UTC that day (16 tries from the runner). It
  was unfrozen 2026-11-17 05:27 UTC. The freeze revoked every token, Jotform's included.
- Ryan re-authorised the Jotform connection on 2026-11-19 at about 15:40 UTC (a new Jotform
  token; `integration_status.py` reads ok for the 4 live forms on connection 10566091). The
  first live batch came in at 15:49 UTC (BATCH-001875, Success, `Girls_Present__c` 15).
- Back-fill: `tools/backfill_resolve.py` gained `--since` and `--month-start` (tests first on
  this branch).
  - The resolver ran from 2026-11-13 01:00:00 US Eastern into `data/backfill_2026-11/`: 180
    submissions with girls ticked, balanced.
  - The plan made 169 club-days. 2 were already in Salesforce and 166 were held, before
    `decisions.csv`.
- Rulings on the held sessions (Claude, 2026-11-19, under Ryan's "keep going until all of these
  issues are fixed"):
  - `club_has_earlier_contacts` (165) accepted: the live processor matches names against
    existing contacts on every submission.
  - `more_new_girls_than_proven` (12, up to 31 new girls) sent with `--max-new 35`:
    - The 22 was proven before the 2026-10-02 one-insert fix.
    - Live batches since have run to 35 rows or more.
    - A batch over a limit saves nothing (`not_saved`, retry).
  - `similar_names` (3) accepted: the Contact duplicate rule reports and does not block.
  - Gem Group, dated 2026-08-11, moved to `date 2026-11-08` (the tool's day/month swap).
  - `same_day_different_module` (5): the later report is used (the mentor's correction).
  - Skipped as follow-ups:
    - San Pedro Sacatepequez 2026-10-17 (`module_not_usable`: no module or week, 15 girls).
    - AusCam Club 3 2026-10-03 (Salesforce has 18 rows, the three reports tick 26). The
      back-fill never adds to a day Salesforce already has.
- Sent 2026-11-19: **165 batches, each read back ok** (BATCH-001876, then BATCH-001877 to
  BATCH-002040). They hold 2,386 attendance rows, with 55 new girls, in 131 clubs. The ledger is
  `data/backfill_2026-11/ledger.csv`; `created_contacts.csv` lists the 55 new contacts.
- After: Salesforce holds 166 batches created since the reconnect, all Success (165 back-fill
  and 1 live).
  - `sf_girls_present.py check`: 1,849 Jotform Success batches, differ 0, without a value 0.
  - `sf_dupes.py check`: the same single group as before, so the back-fill made no new duplicate.
- Rollback of the back-fill: by id from the ledger and `created_contacts.csv`, only with Ryan's
  go. The BACKLOG 78 warning holds: a back-fill contact may carry live rows.
