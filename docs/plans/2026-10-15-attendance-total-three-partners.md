---
title: The dashboard's total attendance counts Jotform plus the three Salesforce-reporting partners only, shown beside Jotform only
author: Claude (with Ryan's decisions of 2026-10-15)
status: done             # deployed on Ryan's go 2026-10-15 ~09:05 UTC and read back (Result); ticket #35
done: 2026-10-15
backlog: 72
created: 2026-10-15
intent: Ryan, 2026-10-15 (ticket #35) - "Just the overall total number of attendance on the forms that look at Jotform + manual SF attendance and give the numbers for both. There are 3 African partners that were specified that will give their attendance through Salesforce only. Any other clubs' attendance through Salesforce should be filtered out."
---

# Plan: total attendance = Jotform + the three partners, beside Jotform only

Ticket #35. Ryan, 2026-10-14: leadership said last month's combined attendance ("about 4
thousand") was high; make sure nothing is double counted, months are separated properly, and the
numbers can be proved. His scope change of 2026-10-15 (the intent above) replaces the ticket's
first outline: no "Girls reached (distinct)" tile, and the total takes only the three partners'
Salesforce-entered counts.

## Context

- Before this change the total (`totals1/`, 2026-10-07) summed `Girls_Present__c` over every
  `Success` batch, whatever club typed it into Salesforce
  ([plan](2026-10-06-attendance-totals.md)).
- The three partners whose clubs are to report through Salesforce only (Ryan, 2026-10-06) are
  Education and English for You, Tumaini La Maisha and Ng'aa Maskani. Their retirement from the
  forms is pending: [plan](2026-10-06-clubs-off-jotform.md) is in progress and nothing is
  applied, so the Partners tab's `jotform` column is not yet `no` for them and their 38 clubs are
  still on the Africa Club picker. Until then a Jotform batch from one of those clubs counts once,
  through the Jotform branch of the filter (2, Build). 2026-10-16: the retirement is applied (the
  three partners marked `no`, their 38 clubs off the template's and the Africa form's Club picker,
  both forms CLEAN, Ryan's go, ticket #56; [Result](2026-10-06-clubs-off-jotform.md#result)).
- Ryan's decisions of 2026-10-15:
  - Total attendance = the Jotform attendance plus the Salesforce-entered counts of the three
    partners; any other club's attendance entered in Salesforce (a `Success` batch whose
    `Creator__c` does not start with `Jotform`) is left out of the total.
  - The dashboard shows both numbers: "Total attendance (Jotform + 3 partners)" and "Attendance
    (Jotform only)".
  - No "Girls reached (distinct)" tile.
  - The Monthly Report is never added to attendance.
  - Leadership's "about 4 thousand" could not be identified: "just report what the numbers
    actually are" (the Result's reconciliation).

## Build

In a working folder `data/sf_totals2_2026-10-15/` (not committed):
- The two Total reports (`Total_Attendance_Last_Month`, `Total_Attendance_by_Partner_by_Month`)
  get the filter logic `1 AND (2 OR 3) AND 4 AND 5`: 1 `Processing_Status__c` = `Success`; 2
  `Creator__c` starts with `Jotform`; 3 `Account__c.Parent` equals one of the three partner
  names; 4 and 5 the existing unlocked Partner and Club filters.
- A new report `Jotform_Total_Attendance_Last_Month` ("Jotform Total Attendance Last Month"):
  `Success` AND `Creator__c` starts with `Jotform`, last month, the sum of `Girls_Present__c`.
- The dashboard `Jotform_Attendance_test` ("Jotform Attendance"): the top row is four 3-column
  tiles - "Total attendance (Jotform + 3 partners)", "Attendance (Jotform only)" (new, from the
  new report), and "Girls who attended (Jotform only)" last month and this month; the monthly
  chart's header is "Total attendance per month (Jotform + 3 partners)"; the "How to read this
  dashboard" bullet on the total names the three partners, says other Salesforce entries are
  left out and the Monthly Report is never added, and that Jotform only is the Jotform rows.

## Rollout (live; each step on Ryan's go)

All with the VPN off, through the `sf` CLI login `glow` (`.claude/skills/salesforce`).
1. Backup: retrieve the live dashboard `Jotform_Attendance_test`, the reports
   `Total_Attendance_Last_Month`, `Total_Attendance_by_Partner_by_Month`,
   `Jotform_Attendance_by_Partner_by_Month` and the report type `Attendance_Totals` into
   `data/sf_totals2_2026-10-15/before/` (the rollback, of the three changed components only:
   Rollback, below).
2. Build the four components (Build, above).
3. Check-only validate: `sf project deploy start --dry-run -o glow -d force-app`. The first run
   (`0AfRP000002h9YL0AY`) failed only on two descriptions over 255 characters; after shortening
   them, `0AfRP000002h9Zx0AI` succeeded, 4 of 4.
4. Ryan's go in the conversation; then the same command without `--dry-run` deploys.
5. Read back: retrieve the four components into `data/sf_totals2_2026-10-15/after/` and compare
   with the build; run both headline reports through the Analytics API and compare their totals
   with SOQL.

## Rollback

The deploy changed three components: the dashboard `Attendance/Jotform_Attendance_test` and the
reports `Attendance/Total_Attendance_Last_Month` and `Attendance/Total_Attendance_by_Partner_by_Month`
(and created `Attendance/Jotform_Total_Attendance_Last_Month`). `data/sf_totals2_2026-10-15/before/`
holds five (those three, the report `Attendance/Jotform_Attendance_by_Partner_by_Month` and the
report type `Attendance_Totals`, both unchanged by this deploy); `after/` holds the four deployed.
The rollback redeploys only the three changed components from `before/`; the other two are never
deployed from it (2026-10-16: a later change to them would be overwritten).

1. VPN off. Retrieve those three components fresh (`sf project retrieve start -o glow -m ...`, the
   three names below) and compare them with the same files in `data/sf_totals2_2026-10-15/after/`.
   If any differs, someone changed it since - stop: build the rollback from that fresh retrieve
   (edit only this change out of the copy), never from `before/`.
2. Equal: Ryan's go, then from within `data/sf_totals2_2026-10-15/before/`:
   `sf project deploy start --dry-run -o glow -m "Dashboard:Attendance/Jotform_Attendance_test"
   -m "Report:Attendance/Total_Attendance_Last_Month"
   -m "Report:Attendance/Total_Attendance_by_Partner_by_Month"`, then the same without `--dry-run`.
   Never `-d force-app` there (it would redeploy all five).
3. Retrieve the three again and compare with `before/`. The dashboard and the two Total reports
   are back on the `totals1/` filter.

This is the only rollback for this change; no older dashboard package
(`data/sf_dashboard_2026-10-02/`'s `public_2026-10-09/`, `before_public_2026-10-09/`, `totals1/`,
`gen.py`'s build) is ever redeployed. The new report `Jotform_Total_Attendance_Last_Month` can stay
(the dashboard no longer references it after step 2), or goes with a `destructiveChanges.xml` after
step 3. Revert this ticket's RUNBOOK change with it.

## Risks

- **A partner's batch typed under a club outside the three partners** is left out of the total.
  Mitigation: the intake contract (RUNBOOK "Attendance totals and partner-reported counts") names
  the club by its Salesforce Account name, whose parent is the partner.
- **A double count while the 38 clubs are still on the Africa Club picker** (added 2026-10-16): a
  typed monthly aggregate for one of those clubs (filter branch 3) plus that club's Jotform
  batches in the same month (branch 2) would both count; the processor's club-and-day lock blocks
  only the same date. Mitigation: the intake (BACKLOG 72) must not type a count for a club that
  still submits on Jotform until the retirement ([plan](2026-10-06-clubs-off-jotform.md)) is
  applied. Today: 0 batches since 1 September from the three partners' clubs (SOQL, 2026-10-16).
  2026-10-16: the retirement is applied (~00:40 / ~00:50 UTC, template and Africa): the double
  count's path through the Jotform picker is closed for these clubs.
- **A renamed partner account** drops out of filter 3 (it matches the names). Mitigation: rename
  the filter values with the account, as for the dashboard's Partner filter.
- **Leadership's number stays unexplained**: the Result reports what the numbers are, by session
  date, as Ryan asked.

## Proof

- `scripts/harness_tests.sh test/runbook_test.py` (class `AttendanceTotalsRunbook`) and
  `scripts/verify.sh` → `VERIFY OK`.
- Live: the read-back (0 differences) and Total attendance last month = Jotform only = the SOQL
  count of attendance rows (Result).

## Result

Deployed on Ryan's go (in the conversation, VPN off) 2026-10-15 ~09:05 UTC: `sf project deploy
start -o glow -d force-app`, Succeeded, `0AfRP000002h9dB0AQ`, after the check-only
`0AfRP000002h9Zx0AI` (4 of 4).

Read back: the four components retrieved into `data/sf_totals2_2026-10-15/after/`, 0 differences
from the build. Through the Analytics API, "Total Attendance Last Month" = 7,227 = "Jotform Total
Attendance Last Month" 7,227 = SOQL `SELECT COUNT(Id) FROM Attendance__c WHERE Attendance_Date__c
= LAST_MONTH` 7,227 (531 `Success` batches in September).

**Reconciliation** (read 2026-10-15 through the read connector; counts only):
- Every attendance batch since August came through Jotform (`Creator__c` starts with `Jotform`):
  no partner-reported or other Salesforce-entered batch exists yet, so today "Total attendance
  (Jotform + 3 partners)" equals "Attendance (Jotform only)".
- September 2026: 7,227 attendances (girls × sessions), 2,873 distinct girls, 531 `Success`
  batches (529 with rows), 38 `Failed`.
- October to 2026-10-15: 3,102 attendances, 2,073 distinct girls.
- Since 1 September: 10,329 attendances, 3,441 distinct girls, 209 clubs.
- Double counting: 0 Contact + date pairs appear twice since 1 September (no girl is counted twice
  on the same date); 0 attendance rows without a batch.
- Months: separated by `Attendance_Date__c`, the session date. About 4,978 September-dated rows
  were created on 2026-10-02 (the September back-fill's 4,712 plus live submissions), which a
  report by `CreatedDate` would put in
  October.
- Leadership's "about 4 thousand": no figure near 4,000 was found in these counts; Ryan,
  2026-10-15: report what the numbers actually are.
