---
title: GLOW Club Implementation (D2) - 2026 only, a Month filter, unique partners per module, summit types, adapted modules as a table
author: Claude (ticket #197, with Ryan's decisions of 2026-11-02)
status: done      # ticket #197; deployed 2026-11-04 07:34 UTC on Ryan's go (0AfRP000002j8zZ0AQ, 7/7), read back, checked against SOQL
done: 2026-11-04
created: 2026-11-02
intent: GLOW's review of 2026-11-02 (epic #194) - 2026 only, GLOW's names, "the total number of partners that implemented each module as opposed to the number of clubs", "consolidated responses" for the adapted modules and the summit types, a filter by month
---

# Plan: D2 "Implementation Dashboard" after GLOW's review

Ticket #197 (epic #194), after #195 ([plan](2026-11-02-sf-reporting-year.md)) added
`DHIS2__c.In_Reporting_Year__c`, `Attendance_Batch__c.In_Reporting_Year__c` and the month names.
D2 is the dashboard "Implementation Dashboard" (`01ZRP000006jU9o2AE`, folder "GLOW Monthly
Dashboards"); its components show items 5-8 of `glow/sf_keep_list.csv`, reports in "GLOW Monthly
Reports". RUNBOOK `### GLOW Club Implementation` holds the state and the rollback; #76's
[plan](2026-10-24-sf-dash-implementation.md) the change before this one.

## Context

- GLOW, 2026-11-02, on D2: 2026 only (no October-December 2025); GLOW's full names on the
  components; the former PO (user `005RP000001RERJYA4`) off the Partner Manager filter; a filter
  by month.
- On item 6, "Glow Club Modules Implemented by M&P": "represent the total number of partners that
  implemented each module as opposed to the number of clubs", "a horizontal bar chart", and the
  earlier 2026 months "based on the partner monthly report".
- On item 7, "GLOW Club Modules Adapted By Month": "Are we able to see consolidated responses for
  which modules were adapted?"; on item 8, "Local and Regional Summits By Month 2": "Are we able
  to see consolidated responses for the types of summits completed?"
- Ryan, 2026-11-02: the modules count from September 2026 onward, from Jotform
  (`Attendance_Batch__c.Module__c`). January-August 2026 has no module data: the Monthly Report's
  module question has no answers after September 2025 (400 rows in 2025, 0 in 2026), and the 15
  pilot batches (February-August 2026) stay out. The adapted modules are a table of responses
  (DECISIONS 2026-11-02, "The modules' data gap").
- D2 runs as the viewer (`LoggedInUser`). It is dynamic and the org is at its limit of 5 dynamic
  dashboards, so the API refuses its copy: its rollback is this change's `before/`.

## Build

`data/sf_glow_review_2026-11/implementation/build/` (in the ticket worktree, never committed),
made by `make_build.py` from a copy of the retrieve `before/`, text edits each with an assert:

- Items 5 (`00ORP000005rY3t2AE`), 7 (`00ORP000005uehR2AQ`) and 8 (`00ORP000005uekf2AA`): the
  filter `Period__c equals LAST_N_MONTHS:12` becomes `In_Reporting_Year__c equals true`.
- Item 6 (`00ORP000009kUNh2AM`, `Glow_Club_Modules_Implemented_Jotform`, #76's report): the
  filter `Attendance_Date__c equals LAST_N_MONTHS:12` becomes `Attendance_Batch__c
  In_Reporting_Year__c equals true`, the floor `Attendance_Date__c >= 9/1/2026` kept; Matrix
  becomes Summary, grouped by `Module__c` then the partner (`Account__c.Parent`), with the custom
  summary formula `FORMULA1` = `Attendance_Batch__c.Account__c.Parent.Name:UNIQUE` (label
  "Partners") at the module level, as item 18's `FORMULA1` does.
- Labels within 40 characters: item 5 "Club Implementation by Month and Partner", item 6 "Modules
  Implemented by Month and Partner", item 7 "Modules Adapted by Month and Partner"; item 8's
  unchanged.
- D2, the component titles, GLOW's names: "GLOW Club Implementation by Month and Partner", "GLOW
  Club Modules Implemented by Month and Partner", "GLOW Club Modules Adapted by Month and
  Partner"; item 8's "Local and Regional Summits By Month 2" unchanged.
- D2, item 6's component: a horizontal bar ("Bar"), one bar per module, its length the unique
  partners (`FORMULA1`), values shown, sorted by value descending.
- D2, the Assigned Partner Manager filter: the former PO's option goes (6 options to 5).
- D2, a second dashboard filter "Month": 12 `equals` options, January to December, mapped to
  `DHIS2__c$Month__c` on the `DHIS2__c` components and to `Attendance_Batch__c$Month_Name__c` on
  item 6.
- A new report "Summit Types Completed" (`Summit_Types_Completed`, "GLOW Monthly Reports"): a
  summary report grouped by `Select_summits_completed_last_month__c`, the record count, item 8's
  filters and the answer "No summit(s) were done" left out. A new report, because that filter on
  item 8 would change its monthly chart. On D2 a Bar component "Types of Summits Completed", row
  16, full width, values shown, by value descending.
- A new report "Modules Adapted Responses" (`Modules_Adapted_Responses`, "GLOW Monthly
  Reports"): tabular, the partner, `Period__c`, `If_so_please_select_which_ones__c` and
  `Please_describe_how_you_adapted_the_curr__c`, only rows with modules picked
  (`If_so_please_select_which_ones__c` not blank; the long-text description cannot be filtered
  on), the reporting year and the test-record rule, sorted by period. On D2 a Lightning table
  "GLOW Club Modules Adapted: Responses", row 24, full width, sorted by `Period__c`
  (`flexTableSortInfo`). The dashboard shows the first 255 characters of the long text; the
  report has it in full.

The two new reports get no row in `glow/sf_keep_list.csv`: the file is GLOW's keep list, one row
per item 1-19 and D1-D5, and `test/sf_keep_list_test.py` holds it to exactly those rows. The
RUNBOOK names the reports and their Ids instead. The keep list's `label_target` of items 5-7
becomes GLOW's names.

## Rollout (live; each write on Ryan's go)

VPN off (`route -n get default` shows `en0`), in the main session, through the `sf` CLI login
`glow`. Ryan gave his go in chat on 2026-11-04; each live command also passed the live-gate
prompt.

1. Retrieve live into `data/sf_glow_review_2026-11/implementation/before/`: D2
   (`01ZRP000006jU9o2AE`), the reports of items 5 (`00ORP000005rY3t2AE`), 6
   (`00ORP000009kUNh2AM`), 7 (`00ORP000005uehR2AQ`) and 8 (`00ORP000005uekf2AA`), and the report
   type `Attendance_Totals`. Compare it with `data/sf_dash_implementation_2026-10-24/after/`; a
   difference stops for Ryan.
2. Copies into Decommissioned (`00lRP000007iOiXYAU`) before anything changes, one per report,
   each on Ryan's go after its dry run:
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_glow_review_2026-11/implementation/copies --kind report --id 00ORP000005rY3t2AE --tag "#197" --apply`,
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_glow_review_2026-11/implementation/copies --kind report --id 00ORP000009kUNh2AM --tag "#197" --apply`,
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_glow_review_2026-11/implementation/copies --kind report --id 00ORP000005uehR2AQ --tag "#197" --apply` and
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_glow_review_2026-11/implementation/copies --kind report --id 00ORP000005uekf2AA --tag "#197" --apply`.
   The dry runs are the same commands without `--apply`. Each copy is read back and its row in
   `copies/ledger.csv` says `ok`. D2 is dynamic and the API refuses its copy (the org is at its
   limit of 5 dynamic dashboards), so its rollback is `before/`.
3. Make `build/` from a copy of `before/` with `make_build.py` (Build, above).
4. Check-only from `build/`: `sf project deploy start --dry-run -o glow -d force-app`, on Ryan's
   go.
5. On Ryan's go, deploy: `sf project deploy start -o glow -d force-app` from `build/`.
6. Read back: retrieve D2 and the six reports into `after/` and compare `after/` with `build/`:
   no differences beyond Salesforce's normalisation.
7. Refresh D2:
   `sf api request rest '/services/data/v67.0/analytics/dashboards/01ZRP000006jU9o2AE' -o glow -X PUT -b '{}'`;
   every component returns data. A filtered view needs its own refresh, the same PUT with
   `?filter2=<option id>` (the Month filter's option), before a GET returns its data.
8. Check against SOQL (Result): for item 6, each module's bar equals
   `SELECT Module__c, COUNT_DISTINCT(Account__r.ParentId) FROM Attendance_Batch__c WHERE Processing_Status__c = 'Success' AND Creator__c LIKE 'Jotform%' AND In_Reporting_Year__c = true AND Attendance_Date__c >= 2026-09-01 AND Account__r.ParentId != null AND (NOT Account__r.Parent.Name LIKE '%test%') GROUP BY Module__c`,
   unfiltered and with the Month filter on September (`AND Month_Name__c = 'September'`); the
   summit chart equals the picklist counts of `Select_summits_completed_last_month__c` on
   `DHIS2__c` in the reporting year; the table's rows equal the 2026 count of rows with modules
   picked; no component shows a 2025 month; the Partner Manager filter has no option for the
   former PO.

## Rollback

DECISIONS 2026-10-16, each write on Ryan's go after a check-only, VPN off.

- The reports of items 5, 6, 7 and 8 are restored from their copies in Decommissioned
  (`00ORP000009p0IX2AY`, `00ORP000009p0K92AI`, `00ORP000009p0Ll2AI`, `00ORP000009p0NN2AY`, tagged
  `#197`): a Salesforce user opens the copy, then Save As or moves it into "GLOW Monthly Reports"
  (RUNBOOK, the archive rule). A report's metadata rollback is a fresh retrieve of it, edited back
  where #197 changed it, then a check-only and a deploy.
- D2 is dynamic and the API refuses its copy, so the dashboard is restored by deploying only its
  own file in `data/sf_glow_review_2026-11/implementation/before/`, and only while a fresh
  retrieve of D2 equals `after/` (nothing has changed it since this deploy).
- Never from an older build or retrieve (DECISIONS 2026-10-16): #76's
  `data/sf_dash_implementation_2026-10-24/` is no rollback for this change.
- The two new reports, "Summit Types Completed" (`00ORP000009p0Qc2AI`) and "Modules Adapted
  Responses" (`00ORP000009p0Qb2AI`), are not in `before/`, and D2 as `before/` has it shows no
  component on them: once D2 is restored they move to Decommissioned. Nothing is deleted.

## Result

All on 2026-11-04 UTC, VPN off, on Ryan's go.

- Step 1: D2 and the four reports equal `data/sf_dash_implementation_2026-10-24/after/`;
  `Attendance_Totals` differs only by #195's new columns (equal to #195's `after/`). The keep list
  still carries the old item 6 report (`00ORP000005rZxd2AE`, in Decommissioned since #76); D2
  shows #76's `00ORP000009kUNh2AM`.
- Step 2: item 5 to `00ORP000009p0IX2AY` (07:22:56Z), item 6 to `00ORP000009p0K92AI`
  (07:23:02Z), item 7 to `00ORP000009p0Ll2AI` (07:23:07Z), item 8 to `00ORP000009p0NN2AY`
  (07:23:14Z), each read back, every ledger row `ok`, all before the deploy. D2 has no copy
  (dynamic).
- Step 4: the first check-only, `0AfRP000002j8wL0AQ`, failed: "Sort info should be always
  present" (a Lightning table on a tabular report needs `flexTableSortInfo`). With the sort added,
  check-only `0AfRP000002j8xx0AA` Succeeded, 7 of 7 components.
- Step 5: deploy `0AfRP000002j8zZ0AQ` Succeeded, 7 of 7, 0 errors, 07:34:10Z. The new reports'
  Ids: "Summit Types Completed" `00ORP000009p0Qc2AI`, "Modules Adapted Responses"
  `00ORP000009p0Qb2AI`.
- Step 6: the six reports in `after/` equal `build/`. D2 differs only by defaults Salesforce adds
  (`showPicturesOnCharts`, an empty `groupingSortProperties`, `sortLegendValues`):
  normalisation.
- Step 7: D2 refreshed at 07:35Z, all 6 components return data.
- Step 8:
  - Item 6 equals the SOQL in all 20 of 20 modules (for example Power of Girls 101: 20 partners,
    Community 101: 16, Self Advocacy: 13). With the Month filter on September (a filtered refresh,
    `?filter2=`), 17 of 17 modules equal the SOQL with `Month_Name__c = 'September'`, and all 6
    components return data.
  - The summit chart equals the SOQL by picklist value: Other 32, Local Advocacy Summit 9, Ways We
    GLOW Summit 5, IDG Summit 2 ("No summit(s) were done", 321, left out).
  - The responses table has 244 rows, the SOQL count of 2026 rows with modules picked (243 on
    2026-11-02); September 29 = 29.
  - No grouping label in any component contains 2025 (0 of 122).
  - The live Partner Manager filter has 5 options, none the former PO's; the Month filter 12.

`data/sf_glow_review_2026-11/implementation/` (before/, copies/, build/, after/) is in the ticket
worktree, untracked: move it to the main checkout before land.
