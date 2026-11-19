---
title: Restore the attendance processor after another team's release overwrote it on 2026-10-26
author: Claude (ticket #238, found 2026-11-19 while re-sending #153 group B)
status: in-progress      # ticket #238; processor restored 2026-11-19 14:39 UTC on Ryan's go; Jotform delivery (B) open
created: 2026-11-19
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
- `Girls_Present__c`: 557 Success batches to set (8,115 rows), per the plan of 2026-11-19.
  Outcome below.
