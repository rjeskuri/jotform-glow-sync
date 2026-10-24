---
title: A Period date on the Monthly Report (DHIS2) records and in the Dhis2 report type, for the last-12-months period
author: Claude (ticket #128)
status: done             # ticket #128; deployed 2026-10-24 08:53 UTC on Ryan's go, read back (Result)
done: 2026-10-24
created: 2026-10-24
intent: Ryan, 2026-10-23 (ticket #74) - the Monthly Report dashboards' period is the last 12 months, not a fixed year
---

# Plan: DHIS2__c.Period__c, one date for the report's month

Ticket #128 (epic #68), the shared change that tasks #75 to #79 need before they replace each kept
report's fixed-year filter with the last 12 months (RUNBOOK "Monthly Report dashboards in
Salesforce", `### Why the dashboards showed old data`). `DHIS2__c` keeps the month as a picklist
of month names (`Month__c`) and the year as a number (`Year__c`); `YearMonth__c` is a number
formula (`202609`) that no report offers and no date filter can use. This task adds a date for
the month and puts it in the `Dhis2` report type. It changes no record and runs nothing.

## Build

Everything under `data/sf_period_2026-10-24/` (owner only, never committed): `before/` is the
fresh retrieve of what is live, `build/` the SFDX project to deploy, `after/` the read-back.

- **The field** `DHIS2__c.Period__c`: label "Period", type Date (a formula), `BlankAsBlank`,
  read-only for the profiles Admin (System Administrator) and GLOW Standard User (a
  `fieldPermissions` entry in each profile, nothing else in them).
- **The report type** `Dhis2`: one column, `DHIS2__c.Period__c`, in the section "DHIS2S" after
  `Year__c`.
- **The formula**, from `Year__c` and `Month__c`:

```
IF(
  OR(
    ISBLANK(Year__c),
    CASE(
      TEXT(Month__c),
      "January", 1,
      "February", 1,
      "March", 1,
      "April", 1,
      "May", 1,
      "June", 1,
      "July", 1,
      "August", 1,
      "September", 1,
      "October", 1,
      "November", 1,
      "December", 1,
      0
    ) = 0
  ),
  NULL,
  DATE(
    Year__c,
    CASE(
      TEXT(Month__c),
      "January", 1,
      "February", 2,
      "March", 3,
      "April", 4,
      "May", 5,
      "June", 6,
      "July", 7,
      "August", 8,
      "September", 9,
      "October", 10,
      "November", 11,
      "December", 12,
      1
    ),
    1
  )
)
```

Why not the outline's formula on `YearMonth__c`: the check-only `0AfRP000002i4gH0AQ` failed,
"Compiled formula is too big to execute (18,865 characters). Maximum size is 15,000", because
`YearMonth__c` is itself a large formula. `Month__c` is a restricted picklist of the 12 month
names and `Year__c` is a Number with scale 0, so the same date comes from them. It is blank when
`Year__c` is blank or the month is not a month name.

## Rollout

2026-10-24 (UTC), VPN off, in the main session.

1. Retrieved live into `data/sf_period_2026-10-24/before/`: `DHIS2__c`, the report type `Dhis2`
   and the two profiles.
2. Built in `build/`: only the field, the report type with the one column, and the two profiles
   carrying only the new field permission.
3. Check-only `0AfRP000002i4ht0AA`, succeeded 08:31 UTC (the first, `0AfRP000002i4gH0AQ`, is the
   `YearMonth__c` formula's failure above).
4. Ryan's go in the session; deploy `0AfRP000002i4l70AA`, succeeded 08:53 UTC (4 components).
5. Retrieved again into `after/`; `diff -r before after`: 15 lines added, none removed (the
   field, the two field permissions, the column). The field file equals the build except that
   Salesforce drops two default attributes (`externalId false`, `formulaTreatBlanksAs
   BlankAsBlank`); the report type equals the build.

## Rollback

Only once no report filters on `Period__c` (the dashboard tasks #75 to #79 will): a destructive
change of the field and of the report type's column, each from a fresh retrieve, Ryan's go
(DECISIONS 2026-10-16). RUNBOOK "Monthly Report dashboards in Salesforce" has the same line.

## Result

- 2026-10-24: `SELECT COUNT(Id) FROM DHIS2__c WHERE Period__c = LAST_N_MONTHS:12` = 569 and
  `... WHERE YearMonth__c >= 202510 AND YearMonth__c <= 202609` = 569 (the window 2025-10-01 to
  2026-09-30). An unsaved report (Analytics API `reports/query`, saves nothing) on `Dhis2` with
  `Period__c` as its date column and that filter returned 569 rows.
- 6 of the 1,051 Monthly Reports have no `Year__c`: `Period__c` is blank on them, so neither
  count includes them. Two of them probably belong to the window and show once an administrator
  fills in their year (not this ticket).
- RUNBOOK "Monthly Report dashboards in Salesforce"; tickets #128, #74, epic #68; tasks #75 to
  #79 apply it (DECISIONS 2026-10-24).
