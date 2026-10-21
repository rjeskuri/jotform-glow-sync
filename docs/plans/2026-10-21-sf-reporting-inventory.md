---
title: Inventory of the Monthly Report (DHIS2) reports, dashboards and interactive dashboard; the two hidden Decommissioned folders; the copy-and-move API proof
author: Claude (with Ryan's request of 2026-10-21)
status: in-progress      # ticket #69; inventory done 2026-10-21; folders passed the check-only, the deploy waits for Ryan's go; API proof not yet run
created: 2026-10-21
intent: none - Ryan's request of 2026-10-21 (ticket #69)
---

# Plan: take stock of the Monthly Report reporting; add the Decommissioned folders

Ticket #69, the first task of epic #68 (clean up and fix GLOW's Salesforce reports and
dashboards). Ryan, 2026-10-21: "removing old Salesforce reports, looking at updates for the
current reports, and trying to fix the interactive dashboard", and "Create a decommissioned
folder to put any old copies in in case we need to revert any changes." Before anything changes:
an inventory of what is there (read-only), the hidden report folder and dashboard folder
"Decommissioned", and a proof that the Analytics API copies and moves a report or dashboard
while its Id stays the same. The rule this sets: DECISIONS 2026-10-21; procedure: RUNBOOK
"Monthly Report dashboards in Salesforce" and "Interactive dashboard in Salesforce".

## Context

- The Monthly Report is `DHIS2__c`: one record per partner per month, `Account__c` the partner
  account, `YearMonth__c` like `202609`, record type `Monthly_reports_new` (DECISIONS 2026-10-19).
- `data/sf_reporting_2026-10-21/` (owner only, never committed; copied to the main checkout
  before landing): `before/` the read-only retrieve, `evidence/` the SOQL, Tooling and shares
  reads and `inventory.csv`, `scan/` the wider retrieve that found the FlexiPage, the tabs and the
  app, `folders/` the build of the two new folders. The retrieved XML carries staff names
  (shares, running users, filter values); this plan carries counts, ids and metadata names only.
- Must not change: any existing report, dashboard or folder, and the "Jotform Attendance"
  dashboard with its two Attendance folders. The two proof clones are the only new reports or
  dashboards.

## Rollout (live; each write on Ryan's go)

All with the VPN off, through the `sf` CLI login `glow` (`.claude/skills/salesforce`).

1. Inventory (reads only, done 2026-10-21): the retrieve into `data/sf_reporting_2026-10-21/before/`,
   the SOQL and Tooling reads, the shares API on the three DHIS2 folders (Inventory, below).
2. The two folders. The build is `data/sf_reporting_2026-10-21/folders/`: the `ReportFolder`
   `Decommissioned` and the `DashboardFolder` `Decommissioned_Dashboards`, both labelled
   "Decommissioned", with no `folderShares`.
   - Check-only first, then the deploy: `sf project deploy start --dry-run -o glow -d force-app`
     within the build folder. The check-only passed 2026-10-21 (validation `0AfRP000002hisf0AA`).
   - Ryan's go, then the same command without `--dry-run`.
   - Read back: retrieve both folders into `data/sf_reporting_2026-10-21/after/` and compare
     with the build; SOQL on `Folder` (`Type` `Report` and `Dashboard`, DeveloperName
     `Decommissioned` and `Decommissioned_Dashboards`) shows both.
   - The shares API (`GET /services/data/v67.0/folders/<id>/shares`) shows no share on either
     folder beyond one Manage share for the deploying administrator (an internal System
     Administrator), which enhanced folder sharing may add to a new folder by itself: that one is
     accepted and recorded in the Result. Any other share (a group, a role, guest, portal,
     community or partner users, All Internal Users) is a failure, removed before anything is
     moved in. If the administrator's Manage entry appears, the definition of done's "no share"
     is knowingly read as "no share beyond that entry", and the Result records it.
3. The API proof, each non-GET call on Ryan's go: clone one DHIS2 report into Decommissioned,
   move the clone to "DHIS2 Reports" and back, and the same with one dashboard; SOQL shows the
   same Id after each move, with `FolderName` following; the two clones stay in Decommissioned,
   labelled as the proof. Each request: API proof, below.

## Rollback

- This ticket changes no existing report, dashboard or folder; it adds two folders and two proof
  clones, and its rollback removes those four things only.
- The proof clones (one report, one dashboard, both made by this ticket) are deleted on Ryan's go,
  in Lightning or with `DELETE /services/data/v67.0/analytics/reports/<clone id>` and
  `DELETE /services/data/v67.0/analytics/dashboards/<clone id>`.
- The two folders go with a destructive deploy listing the `ReportFolder` `Decommissioned` and
  the `DashboardFolder` `Decommissioned_Dashboards` (check-only, Ryan's go, deploy); Salesforce
  refuses to delete a folder that holds anything.
- From #72 on, Decommissioned holds what the epic retired, and the folders stay.
- The inventory and the retrieve are reads: they leave nothing in the org to undo.

## Result

- 2026-10-21: steps 1-3 of the ticket done read-only (Inventory, below). The retrieve succeeded
  with 0 failures: 66 reports, 15 dashboards, 3 folders, 2 report types, 21 LWC, 4 Apex classes,
  1 static resource (`chartjs_v280`), 1 FlexiPage, 2 tabs, 1 app.
- 2026-10-21: the two folders built in `data/sf_reporting_2026-10-21/folders/`; check-only passed
  (validation `0AfRP000002hisf0AA`). Pending: the deploy on Ryan's go, the read-back and the
  shares API on both. If the shares API shows the deploying administrator's Manage entry, it is
  recorded here, and the definition of done's "no share" is knowingly read as "no share beyond
  that entry".
- Pending: the API proof (status: not yet run).

## Inventory

**Counts by folder** (2026-10-21):

| Folder | Kind | DeveloperName | Count | Shares (shares API) |
|---|---|---|---|---|
| "DHIS2 Reports" | report folder | `DHIS2Reports` | 63 reports | 6 |
| "DHIS2 Dashboards" | dashboard folder | `DHIS2Dashboards` | 9 dashboards | 6 |
| "Dhis2 Dashbords" (sic) | dashboard folder | `Dhis2Dashbords` | 6 dashboards | 2 |

- The shares are all to internal users or one Regular group: no guest, portal, community or
  partner share.
- Correction to the ticket's definition of done: `SELECT FolderName, COUNT(Id) FROM Report GROUP BY
  FolderName` is refused by Salesforce ("FolderName can not be grouped"). The counts come from
  `SELECT OwnerId, COUNT(Id) FROM Report GROUP BY OwnerId` (a report's `OwnerId` is its folder)
  and `SELECT FolderId, COUNT(Id) FROM Dashboard GROUP BY FolderId`; they equal the retrieve and
  `evidence/inventory.csv`.

**What the dashboards use** (`DashboardComponent` by `DashboardId`, reading `CustomReportId`):
- The 15 dashboards have 64 components on 55 reports: 52 in "DHIS2 Reports" and 3 in "Public
  Reports" (`unfiled$public`, retrieved with them).
- 11 of the 63 reports in "DHIS2 Reports" are used by no dashboard.
- Report types: `Dhis2` (65 reports) and `Monthly_Reports` (1), both on `DHIS2__c`.
- 11 of the 15 dashboards filter on `DHIS2__c$Account__c.Assigned_Partner_Manager__c`.
- 10 of the 15 dashboards are embedded in the FlexiPage `Monthly_Report_Dashboards`, on the tab
  `Monthly_Report_Dashbords` (sic) of the app "Monthly Report Dashboards".
- `evidence/inventory.csv`: one row per report and dashboard of the three folders and the three
  outside reports - kind, id, DeveloperName, label, folder, report type, format, created, last
  modified (date and user id), last run, last viewed, the dashboards and components that use
  it; for a dashboard its type, running user id, component count, reports used and FlexiPage.

**The interactive dashboard** (LWC `glowDashboardShell`), from the retrieve; code facts only:
- Hosted on the CustomTab `Glow_Interactive_Dashboard` (`lwcComponent` `glowDashboardShell`); no
  app lists the tab; the LWC's `isExposed` is `false`, and no FlexiPage embeds it.
- Its parts: `glowFilterBar`, seven tiles (`glowTileActivity`, `glowTileSummits`,
  `glowTileWeeklyAttendance`, `glowTileMentorOrientation`, `glowTileMentorGroup`,
  `glowTileSessionsObserved`, `glowTileMentorTraining`), `glowRangeBadge`, and shared chart
  modules on the static resource `chartjs_v280`.
- Last modified in the org: the Apex classes 2026-01-04; the LWC bundles 2026-01-13
  (`glowTileWeeklyAttendance` 2026-01-22). None of it is in git.
- Both classes are `public with sharing`; every method is `public static`,
  `@AuraEnabled(cacheable=true)`, and has no DML (reads only). Coverage
  (`ApexCodeCoverageAggregate`): `GlowDemoController` 92.4% (122 of 132 lines),
  `GlowTilesController` 93.4%; the test classes `GlowDemoControllerTest` and
  `GlowTilesControllerTest` contain no assertions.
- Every tile method takes `(Id managerId, Id partnerId, Integer year, String month, Integer
  startYM, Integer endYM, Boolean showAll)` and reads `DHIS2__c` only. The WHERE is the same in
  each: the manager field (`Account__r.Assigned_Partner_Manager__c`, chosen by `getMgrField()`
  ahead of `Account__r.Partner_Manager__c` and `Account__r.OwnerId`), `Account__c`, and
  `YearMonth__c` between `startYM` and `endYM` (else `Year__c`, `Month__c`); `showAll` drops the
  manager and partner conditions, the dates always apply.

| Class | Method | Returns | Called by | Reads on `DHIS2__c` (besides the WHERE) |
|---|---|---|---|---|
| `GlowDemoController` | `getFilterOptions(Id managerId, Id partnerId, Boolean showAll)` | `FiltersResponse` | `glowDashboardShell` | distinct `Account__r.Assigned_Partner_Manager__c` and `Account__c` (with the names), years, months |
| `GlowDemoController` | `getDependentOptions(Id managerId, Id partnerId, Integer year, Boolean showAll)` | `FiltersResponse` | `glowDashboardShell` | the same, narrowed by manager and year |
| `GlowDemoController` | `getMetrics(Id managerId, Id partnerId, Integer year, String month, Boolean showAll)` | `MetricsResponse` | unused | `Complete_at_least_four_sessions_weeks__c`, `girls_attended_GLOW_Club_last_month__c` |
| `GlowTilesController` | `getActivityKpi(...)` | `ActivityKpi` | `glowTileActivity` | `COUNT()` with `Any_Activity_Calc__c = TRUE`, and `COUNT()` of all rows |
| `GlowTilesController` | `getSummitsBreakdown(...)` | `List<CategoryCount>` | `glowTileSummits` | `Select_summits_completed_last_month__c` |
| `GlowTilesController` | `getWeeklyAttendanceTotals(...)` | `List<BarDatum>` | `glowTileWeeklyAttendance` | `Week_1__c` to `Week_5__c` |
| `GlowTilesController` | `getMonthlyAttendanceTotals(...)` | `List<BarDatum>` | `glowTileWeeklyAttendance` | `Monthly_Total__c` |
| `GlowTilesController` | `getMentorOrientationBreakdown(...)` | `List<CategoryCount>` | `glowTileMentorOrientation` | `GLOW_Club_orientation_training__c` |
| `GlowTilesController` | `getMentorGroupBreakdown(...)` | `List<CategoryCount>` | `glowTileMentorGroup` | `Did_you_meet_with_mentors_as_a_group__c` |
| `GlowTilesController` | `getObservedSessionsMonthlyTotals(...)` | `List<BarDatum>` | `glowTileSessionsObserved` | `GC_sessions_did_you_observe_last_month__c` |
| `GlowTilesController` | `getLedTrainingSessionsMonthlyTotals(...)` | `List<BarDatum>` | `glowTileMentorTraining` | `how_many_training_sessions_did_you_lead__c` |
| `GlowTilesController` | `getGirlsAttendanceByPartner(...)` | `List<BarDatum>` | unused | `girls_attended_GLOW_Club_last_month__c` |
| `GlowTilesController` | `getObservedSessionsByPartner(...)` | `List<BarDatum>` | unused | `GC_sessions_did_you_observe_last_month__c` |
| `GlowTilesController` | `getLedTrainingSessionsBreakdown(...)` | `List<CategoryCount>` | commented out (`GlowTilesController.cls:735-780`) | `how_many_training_sessions_did_you_lead__c` |

Where the epic's interactive-dashboard tasks (#81-#83) start:
- **The Partner-Month count** is `COUNT()` of `DHIS2__c` rows (`GlowTilesController.cls:156-163`,
  `getActivityKpi`): rows, not distinct partners.
- **The majority across months**: there is no such logic. The badge is one ratio over the whole
  range, `pct >= 50` (`glowTileActivity.js:26`).
- **The Partner Manager and Partner options** are distinct values over every `DHIS2__c` row of any
  date, with no active or current filter (`GlowDemoController.cls:149-219`).
- **The Partner -> Partner Manager mapping** is the account's current
  `Account__r.Assigned_Partner_Manager__c`, applied to every month.

## API proof

status: not yet run. Each non-GET call waits for Ryan's go; the request forms below are the ones
to run, with each one's HTTP status to be recorded here (no record data).

The sources (from `evidence/inventory.csv`):
- Report: `00ORP000005rVCT2A2` (`Freq_of_Glow_Club_Meet_by_Mon_and_Reg_Fq6`, matrix, in "DHIS2
  Reports", used by no dashboard).
- Dashboard: `01ZRP000006quAj2AI` (DeveloperName `fgMcyANlcTvERilgPVySaXCChURVlO`, in "DHIS2
  Dashboards", 2 components), type `SpecifiedUser`. 4 of the 15 dashboards are dynamic
  (`LoggedInUser`) and dynamic dashboards count against an org limit, so the proof clones a
  `SpecifiedUser` one.

The clones' labels: a report or dashboard name is at most 40 characters, so each label is
`proof #69 <short>` within 40 characters (e.g. `proof #69 Club meet freq`); the source Id and
the ticket go in `description`. Every label the proof sets keeps the `proof #69` marker.

Report:
1. Clone into Decommissioned: `POST /services/data/v67.0/analytics/reports?cloneId=00ORP000005rVCT2A2`, body `{"reportMetadata": {"name": "proof #69 Club meet freq", "folderId": "<Decommissioned report folder id>"}}`. Status: not yet run.
2. Where the clone landed: `SELECT Id, FolderName FROM Report WHERE Id = '<clone id>'`. If it is in the source folder ("DHIS2 Reports": the clone ignored `folderId`), the proof records that, and the first move is into Decommissioned (step 4 before step 3).
3. Move to "DHIS2 Reports": `PATCH /services/data/v67.0/analytics/reports/<clone id>`, body `{"reportMetadata": {"folderId": "<DHIS2 Reports folder id>"}}`. Status: not yet run.
4. Move back: `PATCH /services/data/v67.0/analytics/reports/<clone id>`, body `{"reportMetadata": {"folderId": "<Decommissioned report folder id>"}}`. Status: not yet run.
5. Label and description: `PATCH /services/data/v67.0/analytics/reports/<clone id>`, body `{"reportMetadata": {"name": "proof #69 Club meet freq (moved)", "description": "copy of 00ORP000005rVCT2A2, #69"}}`. Status: not yet run.
6. After each move: `SELECT Id, FolderName FROM Report WHERE Id = '<clone id>'` - the same Id, `FolderName` following.

Dashboard:
1. Clone into Decommissioned: `POST /services/data/v67.0/analytics/dashboards?cloneId=01ZRP000006quAj2AI`, body `{"folderId": "<Decommissioned dashboard folder id>"}`. Status: not yet run.
2. Where the clone landed: `SELECT Id, FolderName FROM Dashboard WHERE Id = '<clone id>'`. If it is in the source folder ("DHIS2 Dashboards", a shared folder: the clone ignored `folderId`), the proof records that; step 3 renames it first, then step 5 moves it into Decommissioned, and steps 4 and 5 follow as written.
3. Label and description, right after the clone and its folder check, before any move: `PATCH /services/data/v67.0/analytics/dashboards/<clone id>`, body `{"dashboardMetadata": {"name": "proof #69 DHIS2 dashboard", "description": "copy of 01ZRP000006quAj2AI, #69"}}`. Status: not yet run.
4. Move to "DHIS2 Dashboards": `PATCH /services/data/v67.0/analytics/dashboards/<clone id>`, body `{"dashboardMetadata": {"folderId": "<DHIS2 Dashboards folder id>"}}`. Status: not yet run.
5. Move back: `PATCH /services/data/v67.0/analytics/dashboards/<clone id>`, body `{"dashboardMetadata": {"folderId": "<Decommissioned dashboard folder id>"}}`. Status: not yet run.
6. After each move: `SELECT Id, FolderName FROM Dashboard WHERE Id = '<clone id>'` - the same Id, `FolderName` following.

If an API refuses a call, that is recorded here with its status, and the fallback is Lightning's
Move, done by hand by Ryan (the report's or dashboard's Move action in Lightning), checked with
the same SOQL.
