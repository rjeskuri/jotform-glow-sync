---
title: Attendance dashboard in Salesforce - charts from the data already there
author: Claude (with Ryan)
status: in-progress
created: 2026-10-02
intent: none - Ryan's request of 2026-10-02 ("upgrade it now to use charts instead of line by line";
  then "start with basic reporting visuals ... using the info we already have")
---

# Plan: Jotform attendance dashboard (charts instead of rows), existing data only

## Context
The test report "Jotform Monthly Attendance (test)" (folder Attendance, deployed 2026-10-02) works;
Ryan checked it. It lists one row per girl per session. Leadership needs charts: one number for the
girls who attended in the month, and attendance by week and by month, with the report's filters
(partner, club, girl).

Ryan's scope (2026-10-02): **basic visuals from the information Salesforce already holds** -
no new fields, no new tool, nothing more on the forms. The "% of maximum attendance possible" line
needs an enrolled count Salesforce does not have (every `Attendance__c` row is a present girl;
4,863 rows, no absence rows, no enrolled count anywhere), so it is **not** in this round; its design
is kept under "Later".

## What Salesforce already gives (read 2026-10-02, read only)
The existing report type `Accounts_Contacts_Attendance` (Account → Contacts → Attendances, used by
the test report) carries everything needed:
- club = `Account$Name` and partner = `Account$Parent`;
- girl = `Account.Contacts$Id`, counted with a unique count, never shown;
- session = `Attendance_Batch__c`, counted the same way;
- `Module__c`, `Attendance_Date__c` and `Creator__c`.

Region is not in it: region sits on the partner Account, and the report type has no lookup to the
partner's fields. So region charts are not in this round. Partners: 49 (a dashboard filter allows
50 values); clubs: 364.

## What gets built (metadata only, folder Attendance)

### Reports
All on `Accounts_Contacts_Attendance`, with the test report's filters:
- locked: Account record type = Club; Creator = AttendanceBatchTrigger;
- unlocked: Partner contains, Club contains, Girl contains.

| Report | Time frame | Grouping | Measures |
|---|---|---|---|
| Jotform Attendance by Week | since 2026-09-01 | date by week | girls (unique), sessions (unique), clubs (unique), attendances (rows) |
| Jotform Attendance by Month | since 2026-09-01 | date by month | girls (unique), attendances |
| Jotform Attendance Last Month | last month | partner | girls, sessions, clubs (unique), attendances |
| Jotform Attendance This Month | this month | partner | girls, sessions, clubs (unique), attendances |
| Jotform Sessions by Module Last Month | last month | module | sessions (unique) |
| Clubs Without Attendance Last Month | last month | partner | clubs (row count) |

"Clubs Without Attendance Last Month" is a standard Accounts report:
- record type Club;
- cross filter "Accounts without Attendances (`Attendances__r`) where date = last month";
- unlocked Partner contains and Club contains.

**The test report itself**:
- gets a chart (attendances and girls by partner);
- its detail rows are collapsed, so it shows summary rows per partner and club instead of one line
  per girl;
- every filter stays;
- the "before" copy is `data/sf_monthly_report_2026-09-30/test_report/`.

### Dashboard "Jotform Attendance (test)" (dashboard folder Attendance)
**Row 1, four numbers:**
- girls who attended last month;
- girls who attended this month so far;
- sessions held last month;
- clubs that sent attendance last month.

**Row 2:**
- line: girls attending per week since 1 September (wide);
- column: girls and attendances by month.

**Row 3:**
- line: sessions held per week;
- line: clubs reporting per week.

**Row 4:**
- bar: girls reached by partner, last month;
- bar: sessions by module, last month.

**Row 5:**
- number and table: clubs with no attendance last month, by partner.

**Filters and running user:**
- Dashboard filter: **Partner** (49 values), on every component.
- Club and girl cannot be dashboard filters, because Salesforce allows 50 values per filter. They
  are one click away: each chart opens its report, and the Club and Girl filters there drive that
  report's chart.
- Running user: Ryan, as on the pilot "Attendance" dashboard, so viewers see the whole organisation.

Nothing existing changes except the test report. The pilot reports and the pilot dashboard, the
processor, the forms and the Jotform mapping are untouched.

## Order of work
1. Commit this plan as `docs/plans/2026-10-02-attendance-dashboard.md`.
2. Write the metadata in a scratch SFDX project (`scratchpad/glowrep`, where the current test report
   and pilot dashboard were retrieved read only).
3. Validate with `sf project deploy validate`: check only, changes nothing, no Apex so no tests run.
   Fix until it is clean.
4. **Deploy** to production. Approving this plan is Ryan's go (his "upgrade it now").
5. **Read back**, read only:
   - Run each report through the Analytics REST API.
   - Compare its numbers with SOQL. September: girls 2,165 = `COUNT_DISTINCT(Contact__c)`;
     attendances 4,712; clubs and sessions by `COUNT_DISTINCT`.
   - Read the dashboard's components through the dashboards API.
   - Ryan opens it and checks the Partner filter (screenshot if he sends one).
6. **Keep the source and update the docs:**
   - Keep the deployed source under `data/sf_dashboard_2026-10-02/` (not committed: it names
     users).
   - RUNBOOK: a short "Attendance dashboard" section (what each chart counts, where the filters
     are, rollback).
   - BACKLOG: the rate (below) and region.
   - The plan's Result, and the work log.

## Rollback
- Delete the new reports and the dashboard (`destructiveChanges.xml`).
- Redeploy the test report's "before" copy.

## Limits to tell leadership
- "Girls who attended" = girls with at least one present row in the period (unique).
- "Sessions" = club sessions with at least one girl present. Duplicate or empty batches add
  nothing.
- Weeks start on Sunday (the org's locale).
- The current month fills in as attendance arrives. A partner's mentors who submit late show up
  late.
- The folders are "Hidden": only Ryan and admins see the dashboard until he shares the folders with
  leadership (his step, in Salesforce: Share on the folder).

## Later (not this round): the attendance rate
"% of max possible" per session = girls present / girls on the club's roster on the session date
(Ryan, 2026-10-02: from the sheet's roster with added and removed dates, only sessions held, no form
changes). It needs:
- two number fields on `Attendance_Batch__c` (present, enrolled);
- a small repo tool that fills them from the roster export;
- a sessions report type with a summary formula.

Into BACKLOG with that design.

## Verification
- `sf project deploy validate` clean, then the deploy succeeds, listing only the new reports, the
  dashboard and the test report.
- Analytics API numbers = SOQL for September, and this month = SOQL for October so far.
- The dashboard API returns every component without error.
- `make check` → `CHECK PASSED` after the docs (plan, RUNBOOK, BACKLOG; no code changes).
