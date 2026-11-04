---
title: GLOW Club Attendance (D1) - 2026 only, a Month filter, no double-counting totals, an overall chart
author: Claude (ticket #196, with Ryan's decisions of 2026-11-02)
status: done      # ticket #196; deployed 2026-11-04 07:15 UTC on Ryan's go (0AfRP000002j8mf0AA, 5/5), read back, checked against SOQL
done: 2026-11-04
created: 2026-11-02
intent: GLOW's review of 2026-11-02 (epic #194) - "only 2026 data is shown", "remove the grand total row, as adding the weekly counts across months is double-counting girls", "the overall attendance total by month", a filter by month
---

# Plan: D1 "Glow Club Attendance" after GLOW's review

Ticket #196 (epic #194), after #195 ([plan](2026-11-02-sf-reporting-year.md)) added
`DHIS2__c.In_Reporting_Year__c`. D1 is the dashboard "Glow Club Attendance"
(`01ZRP000006iWqL2AU`, folder "GLOW Monthly Dashboards"); its components show items 1, 3 and 4 of
`glow/sf_keep_list.csv`, reports in "GLOW Monthly Reports". RUNBOOK `### GLOW Club Attendance`
holds the state and the rollback.

## Context

- GLOW, 2026-11-02, on D1's weekly table (item 4, "GLOW Club Each Week"): only 2026 data; the
  Partner Manager filter without the former PO; "remove the grand total row, as adding the weekly
  counts across months is double-counting girls who attend multiple sessions. The same for the Sum
  Monthly Max totals."
- On item 3, "Participation by Month and Partner": 2026 only, the same filter, and the total of
  57,873 hidden, as it is not the number of unique girls served.
- A chart of the overall attendance total by month beside the partner-level breakdown, and a
  filter by month on the dashboard.
- GLOW's "the months start from Oct 2025" was #74's last-12-months rule; the reply to GLOW (#201)
  answers it.
- The former PO (user `005RP000001RERJYA4`) has no 2026 partner: its two partners last reported
  in 2025.

## Build

`data/sf_glow_review_2026-11/attendance/build/` (in the ticket worktree, never committed), made
by `make_build.py` from a copy of the retrieve `before/`, text edits each with an assert:

- Items 1 (`00ORP000004RJYv2AO`), 3 (`00ORP000005rSbB2AU`) and 4 (`00ORP000005ufOz2AI`): the
  filter `DHIS2__c$Period__c equals LAST_N_MONTHS:12` becomes `DHIS2__c$In_Reporting_Year__c
  equals 1` (true).
- Item 3: `showGrandTotal` false.
- D1, the weekly FlexTable on item 4: `showTotal` false on all 8 columns, Sum Monthly Max
  (`Monthly_Total__c`) included, and no subtotals.
- D1, the Assigned Partner Manager filter: the former PO's option goes (7 options to 6).
- D1, a second dashboard filter "Month" on `DHIS2__c$Month__c`: 12 `equals` options, January to
  December, mapped on every component.
- A new report "Overall Attendance by Month" (`Overall_Attendance_by_Month`, in "GLOW Monthly
  Reports"): a summary report grouped by `Period__c` by calendar month, the sum of
  `Monthly_Total__c`, with item 3's filters (the reporting year, the account not blank, the
  account name not containing "test").
- D1, a new column chart "Overall Attendance by Month" on it: row 0, full width (12 columns), 8
  rows high, values shown, no total; the other three components move down 8 rows.

The new report gets no row in `glow/sf_keep_list.csv`: the file is GLOW's keep list, one row per
item 1-19 and D1-D5 (24 ids), and `test/sf_keep_list_test.py` holds it to exactly those rows, so
an unnumbered row would break it. The RUNBOOK names the report and its Id instead.

## Rollout (live; each write on Ryan's go)

VPN off (`route -n get default` shows `en0`), in the main session, through the `sf` CLI login
`glow`. Ryan gave his go in chat on 2026-11-04; each live command also passed the live-gate
prompt.

1. Retrieve live into `data/sf_glow_review_2026-11/attendance/before/`: D1 (`01ZRP000006iWqL2AU`),
   the reports of items 1 (`00ORP000004RJYv2AO`), 3 (`00ORP000005rSbB2AU`) and 4
   (`00ORP000005ufOz2AI`), and the report type `Dhis2`. Compare it with
   `data/sf_dash_attendance_2026-10-24/after/`; a difference stops for Ryan.
2. Copies into Decommissioned (`00lRP000007iOiXYAU`) before anything changes, one per report, each
   on Ryan's go after its dry run:
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_glow_review_2026-11/attendance/copies --kind report --id 00ORP000004RJYv2AO --tag "#196" --apply`,
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_glow_review_2026-11/attendance/copies --kind report --id 00ORP000005rSbB2AU --tag "#196" --apply` and
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_glow_review_2026-11/attendance/copies --kind report --id 00ORP000005ufOz2AI --tag "#196" --apply`.
   The dry runs are the same commands without `--apply`. Each copy is read back and its row in
   `copies/ledger.csv` says `ok`. D1 is dynamic and the API refuses its copy (the org is at its
   limit of 5 dynamic dashboards), so its rollback is `before/`.
3. Make `build/` from a copy of `before/` with `make_build.py` (Build, above).
4. Check-only from `build/`: `sf project deploy start --dry-run -o glow -d force-app`, on Ryan's
   go.
5. On Ryan's go, deploy: `sf project deploy start -o glow -d force-app` from `build/`.
6. Read back: retrieve D1 and the four reports into `after/` and compare `after/` with `build/`:
   no differences beyond Salesforce's normalisation.
7. Refresh D1:
   `sf api request rest '/services/data/v67.0/analytics/dashboards/01ZRP000006iWqL2AU' -o glow -X PUT -b '{}'`;
   every component returns data. A filtered view needs its own refresh, the same PUT with
   `?filter2=<option id>`, before a GET returns its data.
8. Check against SOQL on `DHIS2__c` (Result): the overall chart equals
   `SELECT CALENDAR_MONTH(Period__c), SUM(Monthly_Total__c) FROM DHIS2__c WHERE In_Reporting_Year__c = true AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') GROUP BY CALENDAR_MONTH(Period__c)`
   month by month; no component shows a 2025 month; the Month filter narrows every component to
   its month; the Partner Manager filter has no option for the former PO; the weekly table shows
   no total row.

## Rollback

DECISIONS 2026-10-16, each write on Ryan's go after a check-only, VPN off.

- The reports of items 1, 3 and 4 are restored from their copies in Decommissioned
  (`00ORP000009p02P2AQ`, `00ORP000009p0412AA`, `00ORP000009p05d2AA`, tagged `#196`): a Salesforce
  user opens the copy, then Save As or moves it into "GLOW Monthly Reports" (RUNBOOK, the archive
  rule). A report's metadata rollback is a fresh retrieve of it, edited back where #196 changed
  it, then a check-only and a deploy.
- D1 is dynamic and the API refuses its copy, so the dashboard is restored by deploying only its
  own file in `data/sf_glow_review_2026-11/attendance/before/`, and only while a fresh retrieve of
  D1 equals `after/` (nothing has changed it since this deploy).
- Never from an older build or retrieve (DECISIONS 2026-10-16): #75's
  `data/sf_dash_attendance_2026-10-24/` is no rollback for this change.
- The new report "Overall Attendance by Month" (`00ORP000009p0FJ2AY`) is not in `before/`, and D1
  as `before/` has it shows no component on it. The report may stay, harmless, or move to
  Decommissioned once D1 no longer uses it. Nothing is deleted.

## Result

All on 2026-11-04 UTC, VPN off, on Ryan's go.

- Step 1: D1 and the three reports equal `data/sf_dash_attendance_2026-10-24/after/`; `Dhis2`
  differs only by #195's column (equal to #195's `after/`).
- Step 2: item 1 to `00ORP000009p02P2AQ` (07:11:03Z), item 3 to `00ORP000009p0412AA` (07:11:10Z),
  item 4 to `00ORP000009p05d2AA` (07:11:17Z), each read back, every ledger row `ok`, all before
  the deploy. D1 has no copy (dynamic).
- Step 4: check-only `0AfRP000002j8l30AA` Succeeded, 5 of 5 components.
- Step 5: deploy `0AfRP000002j8mf0AA` Succeeded, 5 of 5, 0 errors, 07:15:06Z. The new report's
  Id is `00ORP000009p0FJ2AY`.
- Step 6: the three reports in `after/` equal `build/`. D1 differs only by one default element
  Salesforce adds (`sortLegendValues` false on the new component), the new report only by
  `&apos;` in its description: normalisation.
- Step 7: D1 refreshed at 07:16:25Z, all 4 components return data.
- Step 8:
  - The overall chart equals the SOQL in every month of 2026: January 3,409, February 5,019,
    March 5,673, April 5,068, May 5,433, June 5,275, July 4,856, August 4,826, September 5,385
    (unchanged by #196) and October 0 (3 early reports, no figure yet).
  - No grouping label in any component contains 2025 (0 of 949).
  - With the Month filter on September, every component shows September 2026 only, all with data.
  - The live Partner Manager filter has 6 options, none the former PO's.
  - Unfiltered, item 1's roster chart shows one month: it counts only rosters submitted
    electronically.

`data/sf_glow_review_2026-11/attendance/` (before/, copies/, build/, after/) is in the ticket
worktree, untracked: move it to the main checkout before land.
