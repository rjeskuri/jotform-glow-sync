---
title: The three Salesforce-reporting partners' Monthly Max copied into attendance, one Partner report batch per partner per month
author: Claude (with Ryan's decision of 2026-10-19)
status: accepted         # ticket #60; the tool and the docs built 2026-10-19; the first live run (September 2026) waits for Ryan's go
backlog: 72
created: 2026-10-19
intent: none - Ryan's request of 2026-10-19 (ticket #60)
---

# Plan: the three partners' Monthly Max as one Partner report batch a month

Ticket #60 (blocks #59, the dashboard that reads these batches). Ryan, 2026-10-19: no separate
intake for Education and English for You, Tumaini La Maisha and Ng'aa Maskani. Their number is the
one their Monthly Report already carries, "Monthly Max" (`DHIS2__c.Monthly_Total__c`, roughly the
month's unique girls), copied once a month into the attendance data so the dashboard can show one
combined number: Jotform girls plus the three partners' Monthly Max.

## Context

- The Monthly Report: one `DHIS2__c` per partner per month, `Account__c` = the partner account,
  `Month__c` / `Year__c` / `YearMonth__c`, `Monthly_Total__c` ("Monthly Max"); filed between the
  5th and the 12th of the next month.
- The processor matches `Account_Name__c` against every Account, any record type: a batch named
  for the partner account attaches to it and creates none. A batch with no names and
  `Girls_Present__c` above 0 succeeds with no rows. The club-and-day lock is per Account and date;
  a partner account has no Jotform batches.
- This replaces BACKLOG 72's per-club intake contract (RUNBOOK "Attendance totals and
  partner-reported counts", before 2026-10-19) and, for these three partners only, the rule that
  the Monthly Report is never added to attendance (DECISIONS 2026-10-19).
- The dashboard's total (filter 3: the club's parent is one of the three partners) does not take
  a batch on the partner account itself; #59 changes the dashboard to read these batches.

## Build

`tools/sf_partner_monthly.py` (`test/sf_partner_monthly_test.py`, offline, a fake Salesforce):
- `--month YYYY-MM` (default: last month; the current month or a later one is refused before
  Salesforce is asked). Reads the three partners' Accounts by name, their `DHIS2__c` for the month
  (`Monthly_Total__c` only) and their `Success` `Partner report` batches on the month's last day.
- Plans, per partner in the fixed order Education and English for You, Tumaini La Maisha, Ng'aa
  Maskani: insert one `Attendance_Batch__c` (`Account_Name__c` = the partner's Account name,
  `Attendance_Date__c` = the last day of the month, `Girls_Present__c` = Monthly Max, `Creator__c`
  `Partner report`, `Contact_IDs__c` empty, `enable_fuzzy_matching__c` false); skip one already
  in place with the same count; update `Girls_Present__c` alone (old → new) on one with another
  count; refuse a partner with no Monthly Report or more than one, a Monthly Max blank, 0,
  negative or not whole, or two `Success` `Partner report` batches on its day. A refused partner
  gets no write; the others are planned and written; the run ends non-zero.
- Dry run by default (still needs `--vpn-off`: it reads Salesforce); `--apply --vpn-off` writes
  one insert or update per request, reads each back (`Success`, `Account__c` = the partner
  account, the count) and keeps `data/sf_partner_monthly/ledger.csv` (owner only, never
  committed): every write's batch id, partner, month, date, old and new count, read-back. `--limit
  N` counts writes only.
- It never selects `Contact_IDs__c`, a status message or a girl's name; it prints partner names
  and counts, no record ids.

## Rollout (live; each step on Ryan's go)

All with the VPN off, through the `sf` CLI login `glow` (`.claude/skills/salesforce`).
1. Dry run: `python3 tools/sf_partner_monthly.py --month 2026-09 --vpn-off`. Expected (read
   2026-10-19): Education and English for You 110, Tumaini La Maisha 320, Ng'aa Maskani 315, each
   an insert dated 2026-09-30; 745 in all.
2. Ryan's go: `python3 tools/sf_partner_monthly.py --month 2026-09 --apply --vpn-off --limit 1`
   (Education and English for You), read back by the tool: `Success`, on the partner account, 110.
3. Ryan's go: the same without `--limit` (the other two; the first is skipped as in place).
4. Read back: `SELECT Account__r.Name, Girls_Present__c, Processing_Status__c FROM
   Attendance_Batch__c WHERE Creator__c = 'Partner report' AND Attendance_Date__c = 2026-09-30` -
   three `Success` rows, sum 745 = `SELECT SUM(Monthly_Total__c) FROM DHIS2__c` over the three
   partner accounts' September 2026 reports (`YearMonth__c` 202609). A second dry run says
   every partner unchanged, skipped. No new Account (club accounts without a parent: still the two
   pilot accounts).
5. Every month after, about the 12th, once the three reports are filed: a dry run, then `--apply
   --vpn-off` on Ryan's go (RUNBOOK "Attendance totals and partner-reported counts").

## Rollback

From `data/sf_partner_monthly/ledger.csv` (each batch's last row is its state):
- An inserted batch (`action` `insert`): delete it by its `batch_id`, one record per call, on
  Ryan's go (VPN off; a batch with no rows has nothing else to remove). It goes to the Recycle Bin.
- An updated batch (`action` `update`): set `Girls_Present__c` back to the row's `old` count by
  its `batch_id` (one PATCH).
- Then a dry run plans the month again as before the run. Revert this ticket's docs with it if the
  approach is dropped.

## Risks

- **A partner account renamed**: the batch's `Account_Name__c` would no longer find it, and the
  processor would make a stray Club account. Mitigation: the tool reads the Account by the exact
  name first and refuses a partner whose name no single Account carries; the read-back checks
  `Account__c`.
- **A Monthly Report corrected after the copy**: the next run sees another count and plans an
  update, old → new; the ledger keeps the old count.
- **The dashboard does not show the batches yet** (filter 3 is about the club's parent): #59.

## Proof

- `scripts/harness_tests.sh test/sf_partner_monthly_test.py` (23 tests) and `scripts/verify.sh`.
- Live: the read-back of Rollout step 4 (three `Success` batches, 745).

## Result

Not run yet.
