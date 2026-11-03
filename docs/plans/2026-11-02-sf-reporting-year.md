---
title: A reporting-year flag and a month name for the Monthly Report dashboards (2026 only, a Month filter)
author: Claude (ticket #195, with Ryan's decisions of 2026-11-02)
status: in-progress      # ticket #195; check-only 0AfRP000002iyVZ0AY succeeded 2026-11-03; the deploy waits for Ryan's go
created: 2026-11-02
intent: GLOW's review of 2026-11-02 (epic #194) - "Please exclude 2025 data from all the dashboards" and "Can a filter be added by month"
---

# Plan: In_Reporting_Year__c and Month_Name__c

Ticket #195 (epic #194), the shared change the dashboard tasks #196 to #200 need before they
replace `Period__c equals LAST_N_MONTHS:12` (#74, #128) and add a Month filter.

## Context

- GLOW, 2026-11-02: no 2025 data on any dashboard, because 2025 and 2026 have different numbers of
  partners, and a filter by month.
- Ryan, 2026-11-02: the year rolls over by itself in mid-February. A fixed `Year__c` filter is what
  left the dashboards on 2025 data until October 2026 (RUNBOOK "Why the dashboards showed old
  data"). Plain `THIS_YEAR` would drop December's report on 1 January, while it is still being
  filed (reports come in between the 5th and about the 15th of the next month), and leave the
  dashboards empty until February.
- One dashboard filter has to reach both report types D2 uses: `Dhis2` (`DHIS2__c.Month__c`, a
  picklist of month names) and `Attendance_Totals` (item 6, `Attendance_Batch__c`, which has a
  date but no month name).

## Build

`data/sf_glow_review_2026-11/fields/build/` (in the ticket worktree), made by `make_build.py` from
the retrieve `before/` (2026-11-03, VPN off): 10 files.

- `DHIS2__c.In_Reporting_Year__c`, a checkbox formula:
  `IF(ISBLANK(Period__c), FALSE, YEAR(Period__c) = YEAR(TODAY() - 45))`. It is true for the
  reporting year: the calendar year of today less 45 days, so it changes on 15 February.
- `Attendance_Batch__c.In_Reporting_Year__c`, the same on `Attendance_Date__c`.
- `Attendance_Batch__c.Month_Name__c`, a text formula: the month of `Attendance_Date__c` as
  "January" ... "December", the values of `DHIS2__c.Month__c`.
- The report type `Dhis2` gets the one column next to `Period__c`; `Attendance_Totals` gets the two
  next to `Attendance_Date__c`. No column is checked by default.
- Read access (never edit) as the date each is computed from has it: the profiles Admin and GLOW
  Standard User (both read `Period__c` and `Attendance_Date__c`) and the permission set
  `Attendance_Report_Viewer` (reads `Attendance_Date__c`). A field a viewer cannot read is dropped
  from a report silently (RUNBOOK "Attendance dashboard in Salesforce", Access).
- The first check-only, `0AfRP000002ixWH0AY`, failed: a formula field cannot carry a
  `defaultValue`. The line was taken out of both checkboxes; nothing else changed.

## Rollout

VPN off (`route -n get default` shows `en0`), in the main session, the `sf` login `glow`.

1. Retrieved live into `data/sf_glow_review_2026-11/fields/before/` (2026-11-03): the two objects'
   date fields, the two report types, the two profiles, the permission set.
2. Check-only from `build/`: `sf project deploy start --dry-run -o glow -d force-app`;
   `0AfRP000002iyVZ0AY` succeeded 2026-11-03, 8 of 8 components.
3. On Ryan's go: `sf project deploy quick -o glow -i 0AfRP000002iyVZ0AY` (or the same `start`
   without `--dry-run` if the validation has expired).
4. Retrieve again into `after/` by `before/package.xml` plus the three new fields; `diff -r` with
   `before/` shows only the three fields, the three columns and the read permissions.
5. Check (counts into the Result):
   - `SELECT COUNT(Id) FROM DHIS2__c WHERE In_Reporting_Year__c = true` equals the count with
     `Period__c >= 2026-01-01` (both include October 2026's early reports);
   - the same on `Attendance_Batch__c` with `Attendance_Date__c >= 2026-01-01`;
   - `Month_Name__c` by month equals `CALENDAR_MONTH(Attendance_Date__c)` for 2026;
   - an unsaved report (Analytics API `reports/query`, saves nothing) offers all three fields.

## Rollback

Only while no report or dashboard filters on the three fields (tasks #196 to #200 will): a
destructive change of the fields and of their report-type columns and permissions, each from a
fresh retrieve, on Ryan's go (DECISIONS 2026-10-16). Until then they are formula fields nobody
reads, and leaving them is harmless.

## Result

Open: the deploy waits for Ryan's go.
