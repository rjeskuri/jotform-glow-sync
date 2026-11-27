---
title: Club-level attendance by week for photo verification - viewer filters on Attendance By Club By Date, a new Girls Present by Club and Week matrix
author: Claude (ticket #226, GLOW staff's ask relayed by Ryan on 2026-11-18)
status: done      # ticket #226; deploys 0AfRP000002kS090AE (2026-11-18) and 0AfRP000002kcdp0AA (2026-11-19)
done: 2026-11-19
created: 2026-11-19
intent: GLOW staff, 2026-11-18 - "attendance by individual club ... by week", to check against the photos mentors upload
---

# Plan: club-level attendance by week

Ticket #226. Procedures: RUNBOOK "Attendance dashboard in Salesforce".

## Context

- The attendance dashboards show partner totals. GLOW's photo verification needs each club's
  attendance per week.
- "Submissions by Club and Week" (`00ORP000009kYPk2AM`) counts submissions (batches), not girls.
- "Attendance By Club By Date" (`00ORP000007uBRN2A2`) lists girls by club and date. Ryan likes it
  and asked for an easy way to search it (2026-11-18): part 1. The ticket asked for a default of
  the last 8 weeks; the build on Ryan's go uses the last 90 days, the range the dashboard's
  club-by-date table uses (#231). A long range can pass Lightning's row display limit for a whole
  region; a viewer narrows it with the Region, Partner and Club filters (a known residual).
- Region is a filter on both reports, not a shown column (Ryan to accept this reading of the
  definition of done's "with the partner and region").
- Part 2, Ryan's choice of 2026-11-19: a new standalone matrix report, girls present per club and
  week, in the Attendance folder, not on the dashboard; "Submissions by Club and Week" is left
  unchanged.
- A matrix report takes at most two row groupings (the check-only `0AfRP000002kcab0AA` refused
  three), so the rows are partner then club and Region is an unlocked filter.
- The archive rule: neither existing report changes in part 2. Part 1 changed "Attendance By Club
  By Date"; `tools/sf_report_folders.py copy` refuses the Attendance folder by design, so its
  rollback is its `before/` (below).
- Work folders (owner only, untracked, never committed), in the ticket worktree's `data/`:
  `sf_report_filters_2026-11-18/` (part 1) and `sf_club_week_2026-11-19/` (part 2), each with
  `before/`, `build/` and `after/`.

## Rollout

Each Salesforce call with the VPN off.

1. Part 1: retrieve "Attendance By Club By Date" into `before/`; in the build, unlock Region
   (`Account$Partner_Region__c`), Partner (`Account$Parent`) and Club (`Account$Name`) filters,
   each `contains`, and set the date range to the attendance date, `INTERVAL_LAST90`.
   Check-only, Ryan's go, deploy, retrieve `after/` and compare.
2. Part 2: retrieve the two Attendance reports into `before/` (the template); build
   `reports/Attendance/Girls_Present_by_Club_and_Week.report-meta.xml` on `Attendance_Totals`:
   locked filters `Processing_Status__c` equals `Success` and `Creator__c` starts with `Jotform`;
   unlocked date filters `N_WEEKS_AGO:8` to `THIS_WEEK` and Region, Partner, Club `contains`;
   rows partner then club, columns `Session_Week__c`; Sum of `Girls_Present__c`, no record count;
   detail columns batch, session date, module, module week.
3. Check-only, deploy, retrieve `after/` and compare with the build.
4. Run the report through the Analytics API and compare every partner/club/week cell with SOQL
   summed per club and `Session_Week__c`.

## Rollback

- Part 2: delete the new report `Girls_Present_by_Club_and_Week` (`00ORP000009tUjR2AU`) in
  Lightning, or move it to Decommissioned (the archive rule prefers the move). Nothing else
  changed.
- Part 1: after a fresh retrieve of "Attendance By Club By Date" equals
  `sf_report_filters_2026-11-18/after/`, deploy that report from `before/` (DECISIONS
  2026-10-16: only the components the change made).

## Result

- Part 1, 2026-11-18: check-only `0AfRP000002kRyX0AU`, deploy `0AfRP000002kS090AE` (07:41:13
  UTC) on Ryan's go; the retrieve after equals the build.
- Part 2, 2026-11-19: check-only `0AfRP000002kccD0AQ` (1/1), deploy `0AfRP000002kcdp0AA`
  (11:50:56 UTC). The retrieve after equals the build but for one `&apos;` (normalisation).
  The report is `00ORP000009tUjR2AU`.
- Check, 2026-11-19: the report run and SOQL agree in all 698 partner/club/week cells, 10,924
  girls present in total over 10 session weeks (`2026-09 week 3` to `2026-11 week 2`); 0 cells
  differ. The largest cell, 57, matches.
