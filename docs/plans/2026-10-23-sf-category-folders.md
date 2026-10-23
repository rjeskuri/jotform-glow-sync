---
title: The kept Monthly Report reports and dashboards into one report folder and one dashboard folder
author: Claude (with Ryan's decisions of 2026-10-21 and 2026-10-23)
status: in-progress      # ticket #73; reads, build and dry runs done 2026-10-23; the deploy, copies and moves await Ryan's go
created: 2026-10-23
intent: none - the SOW item (p.5, "reorganize reports under their correct dashboards") and GLOW's keep list, ticket #73
---

# Plan: the kept reports and dashboards into "GLOW Monthly Reports" and "GLOW Monthly Dashboards"

Ticket #73 (epic #68). GLOW's keep list (`glow/sf_keep_list.csv`, #70) names 19 items: 18 reports
in five dashboards and one table. Ryan, 2026-10-21: one report folder and one dashboard folder,
not a folder per category; the five groups stay as the dashboards' categories. Ryan, 2026-10-23:
labels do not change, this ticket is folders only, and every kept item is copied to
Decommissioned before it moves. The folder names, "GLOW Monthly Reports" (`ReportFolder`
`GLOW_Monthly_Reports`) and "GLOW Monthly Dashboards" (`DashboardFolder`
`GLOW_Monthly_Dashboards`), go to Ryan with the dry run before anything is deployed. The rule:
DECISIONS 2026-10-23 (the keep list, its dated bullet); procedure: RUNBOOK "Monthly Report
dashboards in Salesforce", "The five dashboards and their folders".

## Context

- What moves: the 18 kept reports in the org today (17 of the five dashboards and item 19; item 12
  is `new`, built by #80) and the five dashboards D1 to D5. Item 17 is in "Public Reports", the
  other 17 reports in "DHIS2 Reports"; the dashboards are in "DHIS2 Dashboards" and "Dhis2
  Dashbords".
- `data/sf_folders_2026-10-23/` (owner only, never committed; copied to the main checkout before
  landing): `before/` the retrieve of the three DHIS2 folders, `build/` the two new folders,
  `copies.txt` the 23 ids to copy, `move_plan.csv` the report moves, `dashboards_by_hand.csv` the
  dashboard moves. The retrieved XML carries staff names (shares); this plan carries counts, ids
  and folder, report and dashboard names only.
- Shares: a dashboard's viewers need its reports' folder, so both new folders get the same
  shares, the union of the three DHIS2 folders' shares: 7 entries (4 internal users View, 2
  internal users Manage, 1 group Manage), internal only, never a guest, portal, community or
  partner share.
- Must not change: any label, the "Jotform Attendance" dashboard and the two Attendance folders,
  and the three DHIS2 folders themselves (#72 moves what is left in them to Decommissioned).

## Rollout (live; each write on Ryan's go)

All with the VPN off, through the `sf` CLI login `glow` (`.claude/skills/salesforce`).

1. Read-only, done 2026-10-23: `tools/sf_report_folders.py list --vpn-off` of "DHIS2 Reports",
   "DHIS2 Dashboards" and "Dhis2 Dashbords", compared with `glow/sf_keep_list.csv`. All 22 ids
   are present with their file labels except item 19, whose file label read "…Report_2025": the
   org's label is "GLOW of the Month Stories Report" (SOQL, unchanged since 2026-10-21), and this
   ticket fixes the file. Item 17 was read by SOQL in "Public Reports". Item 12 is `new` (#80).
2. Retrieve, done 2026-10-23: the three DHIS2 folders into `data/sf_folders_2026-10-23/before/`.
   Build, done 2026-10-23: `data/sf_folders_2026-10-23/build/` holds the `ReportFolder`
   `GLOW_Monthly_Reports` ("GLOW Monthly Reports") and the `DashboardFolder`
   `GLOW_Monthly_Dashboards` ("GLOW Monthly Dashboards"), each carrying the same 7 shares, the
   union of the three DHIS2 folders' shares.
3. Check-only first, then the deploy: `sf project deploy start --dry-run -o glow -d force-app`
   within the build folder. Then Ryan's go, and the deploy (the same command, `--dry-run`
   dropped), its deploy id recorded in the Result.
4. Read back: retrieve both folders into `data/sf_folders_2026-10-23/after/` and compare with the
   build; SOQL on `Folder` shows both with their labels and DeveloperNames; the shares API
   (`GET /services/data/v67.0/folders/<id>/shares`) on each new folder shows the 7 entries,
   internal users and the one group only. An entry of any other kind is removed before step 5.
5. Copies, on Ryan's go: each of the 18 reports and 5 dashboards is copied into Decommissioned
   before any move, with
   `python3 tools/sf_report_folders.py copy --vpn-off --kind report|dashboard --id <id> --tag "#73" --apply`
   for each id in `data/sf_folders_2026-10-23/copies.txt` (23 copies). The dry run of each copy
   was run 2026-10-23: 23 lines, nothing written.
6. Report moves: the plan `data/sf_folders_2026-10-23/move_plan.csv` has 18 rows, `to_folder`
   "GLOW Monthly Reports" and a blank `new_label` (each label kept).
   - Dry run: `python3 tools/sf_report_folders.py move --vpn-off --plan data/sf_folders_2026-10-23/move_plan.csv`.
     On 2026-10-23, before the folder existed, the tool refused it ("0 report folders are named
     exactly"); it is run again after step 4.
   - On Ryan's go, the same with `--apply --limit 1`; check that report by SOQL (same Id, folder
     "GLOW Monthly Reports", label as before).
   - On Ryan's go, the rest:
     `python3 tools/sf_report_folders.py move --vpn-off --plan data/sf_folders_2026-10-23/move_plan.csv --apply`,
     each move to "GLOW Monthly Reports".
7. Dashboards: Ryan moves the five by hand in Lightning into "GLOW Monthly Dashboards" (the API refuses a dashboard `PATCH`), Ids unchanged, as listed in `data/sf_folders_2026-10-23/dashboards_by_hand.csv`.
8. Verify by SOQL after the moves: each kept Id is in its folder with its label unchanged ("GLOW
   Monthly Reports" for the 18 reports, "GLOW Monthly Dashboards" for the five dashboards). The
   same SOQL checks that the three DHIS2 folders hold no kept item. They stay in place; #72 moves
   the rest of them to Decommissioned.

## Rollback

- The reports go back by `undo` from the ledger `data/sf_report_folders/ledger.csv`, bounded to
  #73's 18 moves:
  `python3 tools/sf_report_folders.py undo --vpn-off --ledger data/sf_report_folders/ledger.csv --limit 18`.
  Its dry run lists exactly the 18 ids of `data/sf_folders_2026-10-23/move_plan.csv`; then, on
  Ryan's go, the same with `--apply`: each to its old folder and label, last first.
- The ledger is shared: `undo` reverses the pending moves in it last first, whatever their tag. A
  dry run that lists any other id (a move of #72 or another ticket made after #73's) stops the
  rollback there: those moves are not this ticket's to undo, and Ryan decides.
- The five dashboards go back by hand in Lightning (Ryan), each to the DHIS2 folder it came from,
  checked with SOQL on `Dashboard`.
- The copies stay in Decommissioned.
- The two new folders are left in place, with their shares unchanged.

## Result

- 2026-10-23: step 1 done read-only. All 22 ids are present; item 19's file label was wrong
  ("…Report_2025") and is fixed in `glow/sf_keep_list.csv` to the org's "GLOW of the Month
  Stories Report".
- 2026-10-23: step 2 done. The retrieve into `before/` and the build in `build/`: the two folders,
  each with the same 7 shares (4 internal users View, 2 internal users Manage, 1 group Manage).
- 2026-10-23: the dry run of the 23 copies (step 5): 23 lines, nothing written. The dry run of the
  report moves (step 6) was refused before the folder existed, as expected.
- Awaiting Ryan's go: the folder names, then steps 3 to 8.
