---
title: A Region filter on the Jotform Attendance dashboard, through Account.Partner_Region__c
author: Claude (ticket #222, on Ryan's request of 2026-11-13)
status: done      # ticket #222; deploy 0AfRP000002kRk10AE on 2026-11-18 UTC on Ryan's go
done: 2026-11-18
created: 2026-11-18
backlog: 59
intent: Ryan, 2026-11-13 - "go ahead and add a region filter to the dashboard" (pick Asia, every component shows Asia only)
---

# Plan: Region filter on the Jotform Attendance dashboard

Ticket #222, BACKLOG 59. Procedures: RUNBOOK "Attendance dashboard in Salesforce".

## Context

- Region is a picklist on the partner account (`Account.Region__c`: Africa, Asia, North America,
  South America). Every Club account's own `Region__c` is blank (381 clubs on 2026-11-18).
- The dashboard `01ZRP00000BE2TR2A1` has 17 report components on 11 reports of four report
  types: `Accounts_Contacts_Attendance` (base Account), `Attendance_Batches_and_Girls` and
  `Attendance_Totals` (base `Attendance_Batch__c`), and the standard `AccountList` (the three
  clubs-not-submitting / no-attendance reports).
- The standard `AccountList` offers only `PARENT.NAME` and `PARENT_ID` of the parent (its
  describe, read 2026-11-18), so no path through `Parent.Region__c` reaches those three reports:
  BACKLOG 59's "cannot reach the partner's fields" holds for that type.
- **The choice:** one cross-object formula field on Account, `Partner_Region__c` (text,
  `IF(ISBLANK(ParentId), TEXT(Region__c), TEXT(Parent.Region__c))`). Every report type reaches
  it (the standard one as an Account custom field), and it needs no upkeep: a new club, or a
  club moved to another partner, follows its parent. Rejected: writing `Region__c` on 381 clubs
  (the club tooling would have to keep it; a moved partner leaves stale values); a new report type
  (the three `AccountList` reports would have to be rebuilt).
- **The archive rule:** `tools/sf_report_folders.py copy` refuses the Attendance folder by design,
  as for #212; the rollback is a deploy from a fresh retrieve (below).
- Work folder (owner only, untracked, never committed): `data/sf_region_filter_2026-11-18/`
  with `before/`, `build/`, `after/` and the deploy results.

## Rollout

Each Salesforce call with the VPN off; the deploy on Ryan's go.

1. Retrieve into `before/`: the dashboard, the three custom report types, the permission set
   `Attendance_Report_Viewer` and the 11 reports.
2. Build `build/`: the field; its column in the three custom report types (`Account` table;
   `Account__c.Partner_Region__c` on the two batch types); read access in
   `Attendance_Report_Viewer` and the System Administrator profile (the dashboard's running user;
   a one-entry profile file); a second dashboard filter, Region (4 values), mapped on each
   component to its report type's column (`Account.Partner_Region__c`,
   `Account$Partner_Region__c`, `Attendance_Batch__c$Account__c.Partner_Region__c`). The reports do
   not change: a dashboard filter needs the field in the report type only.
3. Check-only (`sf project deploy start --dry-run`), Ryan's go, the deploy; retrieve into `after/`
   and compare with `build/`.
4. SOQL: per region, clubs and batches by `Partner_Region__c` against `Parent.Region__c`.

## Rollback

- A deploy from a fresh retrieve with the Region filter and its 17 filter columns removed, and the
  three report-type columns removed, check-only first, on Ryan's go, only while that retrieve equals
  `after/` (DECISIONS 2026-10-16), never an older build. Then the field by `destructiveChanges.xml`
  (the permission-set and profile entries go with it).

## Result

2026-11-18, on Ryan's go in the session.

- Check-only `0AfRP000002kRiP0AU` (7/7, 0 errors); deploy `0AfRP000002kRk10AE` (7/7, 0 errors),
  completed 06:44:33 UTC.
- `after/` equals `build/` for the dashboard and the three report types; the permission set
  differs only in Salesforce's sort order of the entries, the field only in escaped apostrophes and
  the default `trackHistory`.
- The live dashboard's describe: filters Partner (44) and Region (Africa, Asia, North America,
  South America).
- SOQL, clubs by the field / by `Parent.Region__c`: Africa 235/235, Asia 95/95, North America
  12/12, South America 37/37; 2 clubs have no region (their partners have none). Batches: Asia
  624/624, North America 19/19, South America 257/257, Africa 935/932: the 3 more are batches on
  partner accounts without a parent (partner-reported counts), which the field gives their own
  region, as intended.
- One region checked end to end (2026-11-18, ~08:20 UTC): "Attendance By Club By Date" run
  through the Analytics API with `Account.Partner_Region__c` equals Asia, the column the
  dashboard's Region filter uses on that report type, gave 89 clubs and 8,546 attendance rows
  over the last 90 days; SOQL on `Attendance__c` (`Account__r.Partner_Region__c = 'Asia'`,
  `LAST_N_DAYS:90`) gave the same 89 clubs and 8,546 rows. A filtered dashboard refresh through
  the API returned no data (its filter ids changed with #231's redeploy), so the click in
  Lightning is Ryan's to see.
