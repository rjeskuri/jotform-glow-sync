---
title: Jotform Attendance dashboard - girls present by club and date replaces the blank-submissions tile
author: Claude (ticket #231, on Ryan's request of 2026-11-18)
status: done      # ticket #231; deploys 2026-11-18 UTC on Ryan's request
done: 2026-11-18
created: 2026-11-18
intent: Ryan, 2026-11-18 - "Let's update the dashboard to replace the blank response report with the Attendance by club by date report instead"
---

# Plan: girls present by club and date on the dashboard

Ticket #231. Procedures: RUNBOOK "Attendance dashboard in Salesforce".

## Context

- The "Blank Submissions" metric tile sat at row 8, columns 8-11, of the Jotform Attendance dashboard
  (`01ZRP00000BE2TR2A1`), a 4x4 tile in a row of three; a club-by-date list needs a table, so the
  table goes full width below the two existing tables and the row's other two tiles widen.
- "Attendance By Club By Date" (`Attendance/Attendance_By_Club_By_Week_Wdl`, report type
  `Accounts_Contacts_Attendance`) carried, since #226 earlier that day, Region, Partner and Club
  filters and a 90-day attendance-date range.
- The archive rule's copy to Decommissioned does not apply: `tools/sf_report_folders.py copy`
  refuses the Attendance folder (as for #212 and #222). The "Blank Submissions" report is kept.
- Work folder (owner only, untracked): `data/sf_dash_swap_2026-11-18/` (`before/`, `build/`,
  `after/`; the second round `before2/`, `build2/`, `after2/`, `rep_before/`; the text fix
  `before3/`, `build3/`, `after3/`).

## Rollout

1. Fresh retrieve; remove the Blank Submissions tile; widen "Clubs not submitting" (14 days and
   since 1 Sept) to 6 columns; a FlexTable from the report at row 62, 12 wide, 16 high, mapped to
   the Partner (`Account$Parent`) and Region (`Account$Partner_Region__c`) filters; the text panel
   to row 78 with its "Blank =" line replaced by the table's.
2. Check-only, deploy, retrieve and compare, refresh, read the component's data.

## Rollback

A deploy from a fresh retrieve: the table removed, the Blank Submissions tile back at row 8
(columns 8-11, its `before/` component), the two tiles back to 4 columns, the text panel's line
restored; only while that retrieve equals `after3/`. The report's grouping change (below) is
undone the same way from `rep_before/`.

## Result

2026-11-18, on Ryan's request in the session.

- Round 1: check-only `0AfRP000002kS4z0AE`, deploy `0AfRP000002kS6b0AE` (07:54 UTC). The table was
  **not** in it: the build script inserted it next to the text panel after editing that panel, so
  the anchor no longer matched and the insert silently did nothing. The dashboard went live with
  the tile removed, the two tiles widened and the text describing a table that was missing, until
  round 2 (about 15 minutes).
- Round 2: the table needed (a) a `flexTableSortInfo`, (b) a header of at most 80 characters, and
  (c) its columns named as the Analytics API names the report's groupings. The report's first
  grouping was the attendance row's club lookup with a stray `dateGranularity` Day, which no table
  column could name; the report was regrouped by `Account$Name` (the same club) and by
  `Attendance_Date__c` by day, newest first: deploy `0AfRP000002kSMj0AM` (08:07 UTC), then the
  dashboard: check-only `0AfRP000002kSTB0A2`, deploy `0AfRP000002kSUn0AM` (08:09 UTC). The
  retrieve after differs from the build only in component order.
- Refreshed: the table reads 261 clubs and 23,474 girl-attendances over the last 90 days.
- Text panel (the same day): "Not here yet … and region" and "Filter by partner above" brought up
  to date with #222's Region filter: check-only `0AfRP000002kT130AE`, deploy `0AfRP000002kT2f0AE`
  (08:50 UTC); `after3/` equals `build3/`.
