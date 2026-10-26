---
title: GLOW Club Implementation (D2) by partner and month, over the last 12 months
author: Claude (ticket #76, with Ryan's decisions of 2026-10-23, 2026-10-24 and 2026-10-25)
status: done             # ticket #76; deployed 2026-10-26 02:50 UTC on Ryan's go (0AfRP000002i7Cj0AI), read back (Result)
done: 2026-10-26
created: 2026-10-24
intent: none - SOW p.5, Approach 1 (dashboards that reflect current data) and Ryan, 2026-10-21, "This data should be displayed by the Partner and Month."
---

# Plan: the GLOW Club Implementation dashboard by partner and month

Ticket #76 (epic #68). The dashboard D2 of `glow/sf_keep_list.csv`, "Implementation Dashboard"
(`01ZRP000006jU9o2AE`, folder "GLOW Monthly Dashboards"), and its kept reports, items 5-8,
showed 2025 only (a fixed `Year__c` filter), by month name (RUNBOOK "Why the dashboards showed
old data"). This change applies #74's fix to them: the last 12 months through
`DHIS2__c.Period__c` (#128), grouped by the partner then the month, the test-record rule of #70,
and only items 5-8 on the dashboard. Item 6 counts the Jotform batches' `Module__c` on
`Attendance_Batch__c` (Ryan on #74). Procedure and the SOQL signals: RUNBOOK "Monthly Report
dashboards in Salesforce", `### GLOW Club Implementation`.

## Context

- Ryan, 2026-10-24 on #76 (for all five dashboards, #75-#79): the dashboard's only filter is
  Partner Manager (each manager sees their partners); no Monthly Report dashboard has a Partner
  filter. The draft's Partner filter (A-K / L-Z) was replaced by it before the go. The reports
  stay grouped by Partner and Month, with the last-12-months period and the test-record rule.
  Labels stay as they are (#70).
- Ryan, 2026-10-25 on #76: item 6 keeps the floor `Attendance_Date__c` on or after 2026-09-01,
  so the February-August 2026 pilot batches (15) stay out; go for the rollout.
- D2 runs as the viewer (`LoggedInUser`). It is a dynamic dashboard and the org is at its limit
  of 5 dynamic dashboards, so the Analytics API refuses its copy: D2 has no copy in
  Decommissioned and its rollback is this change's retrieve `before/`.
- The retrieve, 2026-10-24 ~09:25 UTC, is in `data/sf_dash_implementation_2026-10-24/before/`
  (owner only, never committed): D2, its 4 kept reports in "GLOW Monthly Reports" (items 5, 6, 7
  and 8), the 7 "DHIS2 Reports" reports D2 also used, and the report types `Dhis2` and
  `Attendance_Totals`. Labels and folders equal the state #73 left. #73's move (the Analytics
  PATCH) cleared item 5's description; the build gives it back.
- The retrieved XML carries staff names (the Partner Manager filter's values, the running user):
  this plan carries counts and ids only.

## Build

`data/sf_dash_implementation_2026-10-24/build/` (6 components: the dashboard, 4 reports, 1
report type).

- Items 5, 7 and 8 (`DHIS2__c`, report type `Dhis2`), each:
  - the filter `Year__c equals 2025` becomes `Period__c equals LAST_N_MONTHS:12`; the standard
    date filter's column becomes `Period__c` (All Time, `INTERVAL_CUSTOM`) in place of
    `CreatedDate`;
  - grouped down by `DHIS2__c$Account__c`, then `DHIS2__c$Period__c` by calendar month, the
    answer across (Matrix); the `Account__c.Owner` grouping goes;
  - the test-record rule: `DHIS2__c$Account__c` `notEqual` blank and `notContain` `test`;
  - each keeps its filter on the answer: item 5 leaves out a blank answer and "No, we did not
    implement at all", items 7 and 8 a blank answer.
- Item 6: a new report on `Attendance_Totals` with the same label, "Glow Club Modules
  Implemented by M&P" (`Glow_Club_Modules_Implemented_Jotform`): `Processing_Status__c` equals
  `Success`, `Creator__c` starts with `Jotform`, `Attendance_Date__c` equals `LAST_N_MONTHS:12`
  and is on or after 9/1/2026 (the locale format), the club's parent not blank and not containing
  "test"; grouped by the partner (`Account__c.Parent`), then `Attendance_Date__c` by month, then
  `Module__c` across. The old item 6 report (`00ORP000005rZxd2AE`) is not changed.
- `Attendance_Totals`: one new column, `Account__c.Parent.Assigned_Partner_Manager__c` (the
  partner's manager through the club's parent), so that the Partner Manager filter reaches item 6.
  The Attendance reports on that type are unchanged.
- D2: 4 components, items 5, 6, 7 and 8, each a stacked column for each month split by answer
  or module, titled with its report's label. Item 5 is new on D2. The 7 components on "DHIS2
  Reports" reports and the old item 6 component go (10 components before). The "Assigned Partner
  Manager" filter keeps its 6 values; the running user and `LoggedInUser` are unchanged.
- The 2026-10-24 build failed its first check-only on 2026-10-26 (it had never been validated):
  `showValues` on the two stacked report charts (items 7 and 8) is refused, and item 6's date
  floor must be the locale format `9/1/2026`, not `2026-09-01`. Three lines fixed, same meaning;
  the unvalidated version is kept as `build_2026-10-24_unvalidated/`, the diff in
  `evidence/build_fix_2026-10-26.diff`.

## Rollout (live; each write on Ryan's go)

All with the VPN off (`route -n get default` shows `en0`), through the `sf` CLI login `glow`
(`.claude/skills/salesforce`). The copies' dry run ran on 2026-10-24 (`copy_dryrun.txt`: 4
lines, nothing written).

1. Retrieve D2, items 5, 7 and 8 and `Attendance_Totals` fresh into
   `data/sf_dash_implementation_2026-10-24/fresh_2026-10-26/` and compare it with the live
   retrieve of 2026-10-24, `data/sf_dash_implementation_2026-10-24/before/`; a difference stops
   the rollout for Ryan.
2. Copy each of the four reports into Decommissioned, on Ryan's go, one call per report:
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_dash_implementation_2026-10-24 --kind report --id 00ORP000005rY3t2AE --tag "#76" --apply`
   (item 5), and the same with `--id 00ORP000005rZxd2AE` (the old item 6), `--id
   00ORP000005uehR2AQ` (item 7) and `--id 00ORP000005uekf2AA` (item 8). The ledger rows
   (`data/sf_dash_implementation_2026-10-24/ledger.csv`) are dated before any metadata changes.
   D2 gets no copy (Context).
3. On Ryan's go, check-only before the deploy: `sf project deploy start --dry-run -o glow -d force-app`,
   run within `data/sf_dash_implementation_2026-10-24/build/`; its id goes in the Result.
4. On Ryan's go, the deploy: `sf project deploy start -o glow -d force-app` from the same folder;
   its id goes in the Result.
5. Read back: retrieve the same 6 components into `data/sf_dash_implementation_2026-10-24/after/`
   and compare `after/` with `build/`. A difference beyond Salesforce's normalisation
   (`expandOthers`, default attributes) stops the rollout for Ryan.
6. Refresh D2 on Ryan's go: `PUT /services/data/v67.0/analytics/dashboards/01ZRP000006jU9o2AE`
   (`sf api request rest --method PUT`), and read each component's status back by a GET.
7. Check by SOQL over the last 12 months, with the test-record rule: the dashboard's components
   for items 5, 7 and 8 each equal their SOQL count on `DHIS2__c` (the RUNBOOK's query for each
   item), column by column, and for September 2026 each partner's cells equal the per-partner
   query. Item 6 is checked
   the same way: its component equals SOQL on `Attendance_Batch__c`, module by module, and for
   September 2026 partner by partner. The counts go in the Result
   (`evidence/soql_check_2026-10-26.txt`).
8. Move the 8 reports D2 uses no more to Decommissioned by `move_plan.csv` (the 7 "DHIS2
   Reports" reports and the old item 6 report): the dry run
   `python3 tools/sf_report_folders.py move --vpn-off --dir data/sf_dash_implementation_2026-10-24 --plan data/sf_dash_implementation_2026-10-24/move_plan.csv`,
   then on Ryan's go the same with `--apply --limit 1`, a SOQL check of that report, and the
   full plan with `--apply`. Then SOQL on `DashboardComponent` shows no component on any of the 8.
9. Ryan sets a daily Subscribe on D2 in Lightning (the refresh is a subscription, not metadata),
   as he did for "Jotform Attendance".

## Rollback

1. First the 8 moved reports return to their folders by the undo of this change's ledger,
   because D2's old components read them:
   `python3 tools/sf_report_folders.py undo --vpn-off --dir data/sf_dash_implementation_2026-10-24`,
   then the same with `--apply` on Ryan's go. Its dry run lists 9 lines, newest first: the 9 move
   rows of Rollout step 8 (the first report was moved twice, the second time Decommissioned to
   Decommissioned), the 7 back to "DHIS2 Reports" and the old item 6 back to "GLOW Monthly
   Reports"; any other line stops the rollback for Ryan.
2. Then D2, items 5, 7 and 8 and `Attendance_Totals` roll back together: redeploy those 5
   components of this change's retrieve `data/sf_dash_implementation_2026-10-24/before/`
   (check-only, Ryan's go, deploy, each named with `-m` within `before/`) only while a fresh
   retrieve of the same 5 equals `after/`. `before/` also holds the old item 6 report, the 7
   "DHIS2 Reports" reports and the report type `Dhis2`, which this change leaves as they are:
   the rollback deploy is the 5 only, never the whole folder. Redeploying keeps every Id, so D2's
   components read the old reports again and D2 keeps its place in the FlexiPage
   `Monthly_Report_Dashboards`. The new item 6 report then goes to Decommissioned by `move`.
3. When the fresh retrieve and `after/` differ, someone has changed the dashboard or a report
   since the deploy: the rollback then starts from that fresh retrieve, by the epic's ritual.
   A rollback never deploys an older build or another change's retrieve (DECISIONS 2026-10-16).

The four reports also roll back from their copies in Decommissioned (tagged #76, made
2026-10-26 before the deploy): move a copy back into "GLOW Monthly Reports" (RUNBOOK
"Decommissioned") and point D2's component at it in Lightning. The copies keep their own Ids
and stay in Decommissioned otherwise; nothing is removed.

## Result

Read-only, 2026-10-24: the retrieve into `before/`, the build, the copies' dry run (4 lines,
nothing written) and the move plan. Ryan's go for the rollout: 2026-10-25 on #76. The rollout
ran on 2026-10-26 from ~02:50 UTC in Ryan's interactive session, VPN off, each write through a
live-gate prompt he answered.

- Step 1: the fresh retrieve `fresh_2026-10-26/` is byte-equal to `before/`.
- Step 2, the copies in Decommissioned, tagged #76, ledger rows 2026-10-26 02:50:14-02:50:34
  UTC, before the deploy:
  - report copy `00ORP000009kUFd2AM` of item 5, `00ORP000005rY3t2AE`;
  - report copy `00ORP000009kUHF2A2` of the old item 6, `00ORP000005rZxd2AE`;
  - report copy `00ORP000009kUIr2AM` of item 7, `00ORP000005uehR2AQ`;
  - report copy `00ORP000009kUKT2A2` of item 8, `00ORP000005uekf2AA`.
- Step 3: the first check-only, `0AfRP000002i77t0AA`, failed with 4 errors (Build: `showValues`
  on items 7 and 8, item 6's date format, and D2 because item 6 failed). After the three-line
  fix, check-only `0AfRP000002i7B70AI`: 6/6 Succeeded.
- Step 4, deploy `0AfRP000002i7Cj0AI`: Succeeded, 6 components, 0 errors. The new item 6
  report is `00ORP000009kUNh2AM`. `glow/sf_keep_list.csv` keeps the old item 6 id (#70's list of
  what GLOW kept, as it was).
- Step 5: `after/` equals `build/` beyond normalisation (escaping, `<value></value>`, default
  `legendPosition`, `showValues` and the param `co` 1; `showValues` false on the ColumnStacked
  components, as on #77 and #78).
- Step 6, refresh of D2 at 02:53 UTC: 4 of 4 components have data. "Jotform Attendance" (whose
  reports share `Attendance_Totals`) refreshed with 18 of 18 components with data.
- Step 7, the SOQL check (`evidence/soql_check_2026-10-26.txt`), the last 12 months with the
  test-record rule, report against SOQL:

| Item | Report | Last 12 months | Columns equal | September 2026, per partner equal |
|---|---|---|---|---|
| 5 | Copy of GLOW Club Implementation by M&P | 565 = 565 | 4 answers | 41 records from 41 partners |
| 6 | Glow Club Modules Implemented by M&P | 533 = 533 batches | 17 modules | 533 batches from 31 partners |
| 7 | GLOW Club Modules Adapted By Month | 543 = 543 | 2 answers | 42 records from 42 partners |
| 8 | Local and Regional Summits By Month 2 | 437 = 437 | 5 answers | 38 records from 38 partners |

- Item 6's floor leaves out the 15 pilot batches of February-August 2026; 3 batches in the
  window are on a blank or test parent and stay out by the rule.
- Step 8: 8 reports moved to Decommissioned (`--limit 1` first, 9 move rows in the ledger);
  DashboardComponent SOQL: 0 components use any of them; all 8 read back in Decommissioned.
- Step 9, the daily Subscribe: Ryan's to set in Lightning (not metadata, outside the deploy).
- A Monthly Report filed or changed later moves both sides.
