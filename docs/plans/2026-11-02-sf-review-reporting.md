---
title: GLOW Club Reporting (D5) - 2026 only, a Month filter, item 17 renamed, an approval overview chart
author: Claude (ticket #200, with Ryan's decisions of 2026-11-02)
status: done      # ticket #200; deployed 2026-11-04 09:03 UTC on Ryan's go (0AfRP000002j9lx0AA, 5/5), read back, checked against SOQL
done: 2026-11-04
created: 2026-11-02
intent: GLOW's review of 2026-11-02 (epic #194) - "Monthly Report Approval Status", "an overview chart showing the number of partner reports approved versus not yet approved by month", the stories table 2026 only, a filter by month
---

# Plan: D5 "Reporting" after GLOW's review

Ticket #200 (epic #194), after #195 ([plan](2026-11-02-sf-reporting-year.md)) added
`DHIS2__c.In_Reporting_Year__c` and the month names. D5 is the dashboard "Reporting"
(`01ZRP000006oxSr2AI`, folder "GLOW Monthly Dashboards"); its components show items 17 and 18 of
`glow/sf_keep_list.csv`, and item 19 is the table on no dashboard, reports in "GLOW Monthly
Reports". RUNBOOK `### GLOW Club Reporting` holds the state and the rollback; #79's
[plan](2026-10-24-sf-dash-reporting.md) the change before this one.

## Context

- GLOW, 2026-11-02, on item 17, "Approved Approvals monthly report": rename it, "Perhaps,
  'Monthly Report Approval Status'", and "include an overview chart showing the number of
  partner reports approved versus not yet approved by month".
- On item 19, "GLOW of the Month Stories Report": "Let's only include 2026 data".
- On every dashboard: 2026 only, the former PO (user `005RP000001RERJYA4`) off the Partner Manager
  filter, a filter by month.
- Item 17 lists approved reports only (`Approved__c equals 1`), so the overview is a new report
  without that filter; item 17's own table keeps it.
- D5 runs as the viewer (`LoggedInUser`). It is dynamic and the org is at its limit of 5 dynamic
  dashboards, so the API refuses its copy: its rollback is this change's `before/`.
- The on-time chart GLOW also asked for is #119, not this change.

## Build

`data/sf_glow_review_2026-11/reporting/build/` (in the ticket worktree, never committed), made by
`make_build.py` from a copy of the retrieve `before/`, text edits each with an assert:

- Items 17 (`00ORP000006XXEf2AO`), 18 (`00ORP0000054DyH2AU`) and 19 (`00ORP000005p2L32AI`): the
  filter `Period__c equals LAST_N_MONTHS:12` becomes `In_Reporting_Year__c equals true`. Item 19
  stays tabular (it is on no dashboard).
- Item 17 relabelled "Monthly Report Approval Status" (`Approved_Approvals_monthly_report_ecK`,
  the Id unchanged); its D5 table component is titled the same.
- A new report "Approval Status by Month" (`Approval_Status_by_Month`, "GLOW Monthly Reports"): a
  summary report with item 17's filters without `Approved__c equals 1` (the reporting year, the
  account not blank, the account name not containing "test"), grouped by `Period__c` by month,
  then by `Approved__c`, the record count.
- D5, a new ColumnStacked component on that report, "Monthly Report Approval Status: Approved vs
  Not Yet Approved by Month": full width below the two tables (row 10, 12 columns, 8 rows).
- D5, the Assigned Partner Manager filter: the former PO's option goes (7 options to 6).
- D5, a second dashboard filter "Month": 12 `equals` options, January to December, on
  `DHIS2__c$Month__c`, mapped on all three components.
- Items 17 and 18's tables keep their totals: GLOW asked nothing about them.

The new report gets no row in `glow/sf_keep_list.csv`: the file is GLOW's keep list, one row per
item 1-19 and D1-D5, and `test/sf_keep_list_test.py` holds it to exactly those rows. The RUNBOOK
names the report and its Id instead. The keep list's `label_target` of item 17 becomes GLOW's
name; its `label_today` stays the label #70 recorded.

## Rollout (live; each write on Ryan's go)

VPN off (`route -n get default` shows `en0`), in the main session, through the `sf` CLI login
`glow`. Ryan gave his go in chat on 2026-11-04; each live command also passed the live-gate
prompt.

1. Retrieve live into `data/sf_glow_review_2026-11/reporting/before/`: D5 (`01ZRP000006oxSr2AI`,
   file `DGdiHNHQWRoBNviGBlNWJPnSYqTlMR`) and the reports of items 17 (`00ORP000006XXEf2AO`), 18
   (`00ORP0000054DyH2AU`) and 19 (`00ORP000005p2L32AI`). Compare it with #79's `after/`; a
   difference stops for Ryan.
2. Copies into Decommissioned (`00lRP000007iOiXYAU`) before anything changes, one per report,
   each on Ryan's go after its dry run:
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_glow_review_2026-11/reporting/copies --kind report --id 00ORP000006XXEf2AO --tag "#200" --apply`,
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_glow_review_2026-11/reporting/copies --kind report --id 00ORP0000054DyH2AU --tag "#200" --apply` and
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_glow_review_2026-11/reporting/copies --kind report --id 00ORP000005p2L32AI --tag "#200" --apply`.
   The dry runs are the same commands without `--apply`. Each copy is read back and its row in
   `copies/ledger.csv` says `ok`. D5 is dynamic and the API refuses its copy (the org is at its
   limit of 5 dynamic dashboards), so its rollback is `before/`.
3. Make `build/` from a copy of `before/` with `make_build.py` (Build, above): items 17-19, D5
   and the new report "Approval Status by Month".
4. Check-only from `build/`: `sf project deploy start --dry-run -o glow -d force-app`, on Ryan's
   go.
5. On Ryan's go, deploy: `sf project deploy start -o glow -d force-app` from `build/`.
6. Read back: retrieve D5 and the four reports into `after/` and compare `after/` with `build/`:
   no differences beyond Salesforce's normalisation.
7. Refresh D5:
   `sf api request rest '/services/data/v67.0/analytics/dashboards/01ZRP000006oxSr2AI' -o glow -X PUT -b '{}'`;
   every component returns data.
8. Check against SOQL (Result): the overview equals, month by month, the approved and not yet
   approved Monthly Reports of
   `SELECT CALENDAR_MONTH(Period__c), Approved__c, COUNT(Id) FROM DHIS2__c WHERE In_Reporting_Year__c = true AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') GROUP BY CALENDAR_MONTH(Period__c), Approved__c`
   (September on 2026-11-02: 27 approved, 18 not yet approved); item 19's rows equal the SOQL
   count of 2026 Monthly Reports,
   `SELECT COUNT() FROM DHIS2__c WHERE In_Reporting_Year__c = true AND Account__c != null AND (NOT Account__r.Name LIKE '%test%')`;
   no component shows a 2025 month; the Partner Manager filter has no option for the former PO.

## Rollback

DECISIONS 2026-10-16, each write on Ryan's go after a check-only, VPN off.

- The reports of items 17, 18 and 19 are restored by a deploy, and their copies in Decommissioned
  (`00ORP000009p0wr2AA`, `00ORP000009p0yT2AQ`, `00ORP000009p1052AA`, tagged `#200`) are the record
  of what they were. A copy saved back into "GLOW Monthly Reports" would be a separate report:
  D5's components point at the reports themselves, so D5 would still show the reports as #200
  left them.
- Each report's deploy is one of two, after a check-only: a fresh retrieve of it, edited back
  where #200 changed it; or its file in `data/sf_glow_review_2026-11/reporting/before/`, only
  while a fresh retrieve of it equals `after/` (DECISIONS 2026-10-16).
- D5 is dynamic and the API refuses its copy, so the dashboard is restored the same way: by
  deploying only its own file in `data/sf_glow_review_2026-11/reporting/before/`, only while a
  fresh retrieve of D5 equals `after/` (nothing has changed it since this deploy), or a fresh
  retrieve of it edited back. D5 and the three reports go in one deploy, so D5's old components
  meet the reports as they were.
- Never from an older build or retrieve (DECISIONS 2026-10-16): never #79's
  `data/sf_dash_reporting_2026-10-24/` (its `before/` or `build/`).
- The new report "Approval Status by Month" (`00ORP000009p0qb2AA`) is not in `before/`: D5's
  redeploy takes it off the dashboard first, as D5 in `before/` has no component on it, and then
  it moves to Decommissioned. Nothing is deleted.

## Result

All on 2026-11-04 UTC, VPN off, on Ryan's go.

- Step 1: D5 and the reports of items 17, 18 and 19 equal #79's `after/`.
- Step 2: item 17 to `00ORP000009p0wr2AA` (09:01:01Z), item 18 to `00ORP000009p0yT2AQ`
  (09:01:10Z), item 19 to `00ORP000009p1052AA` (09:01:18Z), each read back, every ledger row
  `ok`, all before the deploy. D5 has no copy (dynamic).
- Step 4: check-only `0AfRP000002j9kL0AQ` Succeeded, 5 of 5 components.
- Step 5: deploy `0AfRP000002j9lx0AA` Succeeded, 5 of 5, 0 errors, 09:03:34Z. The new report's
  Id: "Approval Status by Month" `00ORP000009p0qb2AA`.
- Step 6: the four reports in `after/` are byte-identical to `build/`. D5 differs from `build/` in
  two lines: Salesforce stored the stacked chart's `showValues` as false (the build asked true; a
  stacked column keeps no values printed on its bars, as on D2's stacked charts), and it added the
  default `sortLegendValues` false.
- Step 7: D5 refreshed at 09:04:30Z, all 3 components return data.
- Step 8:
  - The overview equals the SOQL in every month, approved / not yet approved: January 39/7,
    February 43/4, March 40/8, April 45/2, May 41/7, June 39/9, July 36/13, August 38/8,
    September 33/12, October 1/2.
  - September was 27 approved and 18 not yet approved on 2026-11-02 (the ticket) and 33 and 12 on
    2026-11-04: six September reports were approved between the two days, 45 reports on both.
  - Item 19's table has 427 rows, the SOQL count of 2026 Monthly Reports with its filters.
  - No grouping label in any component contains 2025 (0 of 910).
  - The live Partner Manager filter has 6 options, none the former PO's; the Month filter 12.
- Item 19's long stories: the "Formatted Report" export cuts every story at 255 characters
  (tested 2026-11-04 by #201 through the Reports API's Excel export, lengths only); the "Details
  Only" export is #201's to prove.

`data/sf_glow_review_2026-11/reporting/` (before/, copies/, build/, after/) is in the ticket
worktree, untracked: move it to the main checkout before land.
