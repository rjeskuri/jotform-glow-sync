---
title: Move the Monthly Report (DHIS2) reports and dashboards off the keep list to Decommissioned
author: Claude (ticket #72)
status: done             # ticket #72; moves on Ryan's go 2026-10-23 and 2026-10-24, read back by SOQL (Result)
done: 2026-10-24
created: 2026-10-23
intent: none - ticket #72 (epic #68, the SOW's cut to GLOW's keep list)
---

# Plan: retire the Monthly Report reports and dashboards off the keep list

Ticket #72, a task of epic #68 (clean up and fix GLOW's Salesforce reports and dashboards). The
SOW asks to cut the Monthly Report (`DHIS2__c`) reports to GLOW's keep list
(`glow/sf_keep_list.csv`, #70) and keep the 5 Monthly Report dashboards it names. Ryan,
2026-10-21: archive first, never delete in this epic; a retired report or dashboard is moved to
Decommissioned (#69) and keeps its Id. Ryan, 2026-10-23: every report and dashboard in its proper
folder today, kept minimal; the labels stay as they are (#70). Procedure: RUNBOOK "Monthly Report
dashboards in Salesforce", `### Decommissioned`.

## Context

- The tool is `tools/sf_report_folders.py` (#71): a report moves by the Analytics API and keeps
  its Id; the API refuses a dashboard move (#69's API proof), so a dashboard moves by hand in
  Lightning (Ryan).
- `data/sf_retire_2026-10-23/` (owner only, never committed; copied to the main checkout before
  landing) holds the plans, the dry runs, the reference check and the ledger `ledger.csv`.
  `data/sf_flexipage_2026-10-23/` holds the FlexiPage's `before/`, build and `after/`.
- In scope: "DHIS2 Reports", "DHIS2 Dashboards" and "Dhis2 Dashbords", plus the 2 "Public
  Reports" reports that only retiring dashboards used (Ryan, 2026-10-23). The "Jotform
  Attendance" dashboard and the two Attendance folders stay untouched.

## Rollout (live; each write on Ryan's go)

All with the VPN off, through the `sf` CLI login `glow` (`.claude/skills/salesforce`); every
report move by the tool, one PATCH per report, each read back by SOQL, one ledger row per move.

1. The list, read-only, 2026-10-23: `tools/sf_report_folders.py list` of the three folders
   against #69's inventory gave 63 reports and 15 dashboards, the same 78 ids, no item added or
   gone. Kept item 19 (`00ORP000005p2L32AI`) was relabelled in the org on 2026-10-21 by another
   org user; it is kept, and the keep list stays as it is (labels stay, Ryan, 2026-10-23).
2. The plan `data/sf_retire_2026-10-23/plan.csv`, every report of "DHIS2 Reports" whose id is
   not on the keep list (46 rows, all reports), to Decommissioned with its label kept. The 10
   retiring dashboards are not in it, because the tool refuses a dashboard row: they are listed in
   `data/sf_retire_2026-10-23/dashboards_by_hand.csv` (step 6). "DHIS2 Reports" holds 63 reports:
   17 kept reports and 46 reports retiring. The two dashboard folders hold 15 dashboards: 5 kept
   and 10 retiring. No #69 proof copy is in these folders.
3. References, read-only: #69's retrieve (Apex, LWC, Aura, tabs, apps, the FlexiPage; it holds
   no Flow) has no Apex or LWC naming a retiring id or DeveloperName. The FlexiPage
   `Monthly_Report_Dashboards` embedded 5 of the 10 retiring dashboards. On Ryan's go
   (2026-10-23) their 5 components were removed from it first, by the epic's ritual: retrieve
   `before/`, build, check-only `0AfRP000002hxy90AA`, deploy `0AfRP000002hxzl0AA` (0 errors),
   retrieve `after/`, byte-identical to the build, all in `data/sf_flexipage_2026-10-23/`.
4. The dry run of the whole plan, nothing written:
   `python3 tools/sf_report_folders.py move --vpn-off --plan data/sf_retire_2026-10-23/plan.csv --dir data/sf_retire_2026-10-23`.
   The tool refused 36 rows, each used by a dashboard outside Decommissioned: 19 are used by
   the 5 kept dashboards (`plan_3_held_on_kept_dashboards.csv`), 17 only by retiring dashboards
   (`plan_2_after_dashboards.csv`). The 10 used by no dashboard are `plan_1_unused.csv`. Ryan,
   2026-10-23: the 19 stay in "DHIS2 Reports" for #75-#79; the 2 "Public Reports" reports
   `00ORP000006XSy92AG` and `00ORP000006V09x2AC` retire in this ticket
   (`plan_4_public_reports.csv`).
5. `plan_1_unused.csv`, 2026-10-23 (07:12-07:13 UTC). Its dry run:
   `python3 tools/sf_report_folders.py move --vpn-off --plan data/sf_retire_2026-10-23/plan_1_unused.csv --dir data/sf_retire_2026-10-23`
   (10 to move). On Ryan's go, one report first with
   `python3 tools/sf_report_folders.py move --vpn-off --plan data/sf_retire_2026-10-23/plan_1_unused.csv --dir data/sf_retire_2026-10-23 --apply --limit 1`,
   read back by SOQL, then the whole plan with `--apply`: 10 reports moved. That run's first
   PATCH moved the plan's first report, already in Decommissioned, again (a no-op ledger row).
6. The dashboards: Ryan moved the 10 retiring dashboards to Decommissioned by hand in Lightning
   (each one's Move action), because the API refuses a dashboard move. They are listed with
   their old folders in `data/sf_retire_2026-10-23/dashboards_by_hand.csv`; the ledger holds
   reports only.
7. `plan_2_after_dashboards.csv`, 2026-10-23 (07:30-07:41 UTC), once the dashboards that used
   its reports were in Decommissioned: its 17 reports are used only by the 4 retiring dashboards
   `01ZRP000005STH92AO`, `01ZRP000005STH72AO`, `01ZRP000005STH82AO` and `01ZRP000006jMYn2AM`,
   and the tool refuses a report only while a dashboard outside Decommissioned uses it. Ryan
   moved the rest of the 10 by hand afterwards, the last ("Approval Status Monthly Reports",
   `01ZRP000007ivUn2AI`) by 2026-10-24 07:09 UTC (step 8). Its dry run:
   `python3 tools/sf_report_folders.py move --vpn-off --plan data/sf_retire_2026-10-23/plan_2_after_dashboards.csv --dir data/sf_retire_2026-10-23`.
   On Ryan's go, `python3 tools/sf_report_folders.py move --vpn-off --plan data/sf_retire_2026-10-23/plan_2_after_dashboards.csv --dir data/sf_retire_2026-10-23 --apply --limit 1`,
   read back, then the whole plan with `--apply`: 17 reports moved, and again a no-op row for
   the plan's first report.
8. The 2 "Public Reports" reports, 2026-10-24 (07:09 UTC), one at a time on Ryan's go, after the last
   retiring dashboard was in Decommissioned:
   `python3 tools/sf_report_folders.py move --vpn-off --plan data/sf_retire_2026-10-23/plan_4_public_reports.csv --dir data/sf_retire_2026-10-23 --apply --limit 1`,
   read back, then the second row with
   `python3 tools/sf_report_folders.py move --vpn-off --plan data/sf_retire_2026-10-23/plan_4b_rest.csv --dir data/sf_retire_2026-10-23 --apply`.
9. The check: each step was read back by SOQL by Id, `SELECT COUNT() FROM Report WHERE Id IN (…) AND FolderName = 'Decommissioned'`, and the same on `Dashboard`, with each folder's count (Result).

## Rollback

Nothing is deleted: the retired items keep their Ids in Decommissioned, and the rollback moves
them back.
- Reports: the undo's dry run lists every move of the ledger, newest first, with the folder
  each report goes back to:
  `python3 tools/sf_report_folders.py undo --vpn-off --dir data/sf_retire_2026-10-23`.
  On Ryan's go, `python3 tools/sf_report_folders.py undo --vpn-off --dir data/sf_retire_2026-10-23 --apply`
  puts each report back in its old folder ("DHIS2 Reports" or "Public Reports") with its label,
  each read back by SOQL and recorded as an undo row in the ledger.
- The 2 "Public Reports" reports: "Public Reports" has no Folder, so their ledger rows' old folder
  is the organization's id, and the undo sends a PATCH with `folderId` the organization's id. That
  PATCH is not yet proven in the org: the tool's test runs it against a fake org. Their rows are
  the newest, so the undo does them first. If Salesforce refuses the PATCH, or the read-back does
  not show the report in "Public Reports", the run stops there with a `failed` undo row and writes
  nothing more. Then Ryan moves the two back to "Public Reports" by hand in Lightning (Move), SOQL
  shows each there, and an undo row with status `ok` is added to the ledger for each of the two:
  the undo counts a move as undone only by an undo row with status `ok`, so its next run goes on
  with the moves of the other 27 reports.
- Dashboards: the 10 dashboards are in no ledger: Ryan moves each back by hand in Lightning (its
  Move action) to its old folder, "DHIS2 Dashboards" or "Dhis2 Dashbords", as
  `data/sf_retire_2026-10-23/dashboards_by_hand.csv` lists, and SOQL shows the same Id.
- The FlexiPage `Monthly_Report_Dashboards`: once its 5 dashboards are back in their folders,
  its components come back from `data/sf_flexipage_2026-10-23/before/` by the epic's ritual
  (check-only, Ryan's go, deploy, retrieve `after/` and compare).

## Result

- On 2026-10-23 and 2026-10-24, on Ryan's go, 29 reports and 10 dashboards moved to
  Decommissioned with their Ids unchanged: 27 from "DHIS2 Reports" (`plan_1_unused.csv` 10 and
  `plan_2_after_dashboards.csv` 17) and 2 from "Public Reports", and the 10 dashboards by hand in
  Lightning.
- 2026-10-23: the FlexiPage `Monthly_Report_Dashboards` lost the 5 components of retiring
  dashboards (deploy `0AfRP000002hxzl0AA`); its `after/` retrieve is identical to the build.
- 19 retiring reports stay in "DHIS2 Reports", held for #75-#79 because the 5 kept dashboards
  use them.
- SOQL read-back by Id, 2026-10-24: Decommissioned holds 30 reports (the 29 and #69's proof copy)
  and 11 dashboards (the 10 and #69's proof copy).
- SOQL read-back of the source folders, 2026-10-24: "DHIS2 Reports" holds 36 reports, the 17 kept
  and the 19 held; "DHIS2 Dashboards" holds the 5 kept dashboards; "Dhis2 Dashbords" is empty.
  Item 17 of the keep list stays in "Public Reports", as kept.
- The ledger `data/sf_retire_2026-10-23/ledger.csv` has 31 move rows for the 29 reports:
  `00ORP000005rT932AE` and `00ORP000005gxSD2AY` each have a second row, Decommissioned to
  Decommissioned, which changed nothing. Each is the first PATCH of a plan's full `--apply` run,
  which moved that plan's first report again after `--limit 1` had moved it, because the move does
  not check whether a report is already in its target folder. The undo, newest first, undoes the
  no-op row first and then the report's first row, so the report still ends back in "DHIS2
  Reports".
- 2026-10-24: the undo's dry run lists all 31 rows, after this ticket's fix to the tool (a ledger
  row moved out of "Public Reports" has the organization's id as its folder, which no Folder
  has): 27 back to "DHIS2 Reports", 2 back to "Public Reports" and the 2 no-op rows back to
  Decommissioned.
