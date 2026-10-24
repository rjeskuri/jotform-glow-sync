---
title: The kept Monthly Report reports and dashboards into one report folder and one dashboard folder
author: Claude (with Ryan's decisions of 2026-10-21 and 2026-10-23)
status: done      # ticket #73; on Ryan's go 2026-10-24: folders deployed, 20 copies, 18 report moves, the 5 dashboards moved by hand
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
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_folders_2026-10-23 --kind report|dashboard --id <id> --tag "#73" --apply`
   for each id in `data/sf_folders_2026-10-23/copies.txt` (23 copies). The dry run of each copy
   was run 2026-10-23: 23 lines, nothing written. On 2026-10-24 the 3 dynamic dashboards refused
   the clone (HTTP 400, the org's limit of 5 dynamic dashboards): 20 copies were made, and those 3
   take their rollback from the retrieve in `before/` (Result).
6. Report moves: the plan `data/sf_folders_2026-10-23/move_plan.csv` has 18 rows, `to_folder`
   "GLOW Monthly Reports" and a blank `new_label` (each label kept).
   - Dry run: `python3 tools/sf_report_folders.py move --vpn-off --dir data/sf_folders_2026-10-23 --plan data/sf_folders_2026-10-23/move_plan.csv`.
     On 2026-10-23, before the folder existed, the tool refused it ("0 report folders are named
     exactly"); it is run again after step 4.
   - On Ryan's go, the same with `--apply --limit 1`; check that report by SOQL (same Id, folder
     "GLOW Monthly Reports", label as before).
   - On Ryan's go, the rest:
     `python3 tools/sf_report_folders.py move --vpn-off --dir data/sf_folders_2026-10-23 --plan data/sf_folders_2026-10-23/move_plan_rest.csv --apply`,
     each move to "GLOW Monthly Reports". `move_plan_rest.csv` is `move_plan.csv` without its first row
     (00ORP000004RJYv2AO, moved by the `--limit 1` run): 17 rows. `move` moves a report again even when it
     is in its target already, so the full plan here would write a second ledger row for that report;
     #73 makes 18 move rows in all.
7. Dashboards: Ryan moves the five by hand in Lightning into "GLOW Monthly Dashboards" (the API refuses a dashboard `PATCH`), Ids unchanged, as listed in `data/sf_folders_2026-10-23/dashboards_by_hand.csv`.
8. Verify by SOQL after the moves: each kept Id is in its folder with its label unchanged ("GLOW
   Monthly Reports" for the 18 reports, "GLOW Monthly Dashboards" for the five dashboards). The
   same SOQL checks that the three DHIS2 folders hold no kept item. They stay in place; #72 moves
   the rest of them to Decommissioned.

## Rollback

- The reports go back by `undo` from #73's ledger `data/sf_folders_2026-10-23/ledger.csv` (the
  rollout ran with `--dir data/sf_folders_2026-10-23`; the tool's default ledger
  `data/sf_report_folders/ledger.csv` is not this ticket's), bounded to #73's own moves:
  `python3 tools/sf_report_folders.py undo --vpn-off --dir data/sf_folders_2026-10-23 --limit N`
  (`undo` reads and writes only the ledger in `--dir`).
  N is the number of #73's move rows in that ledger that `undo` counts as pending (`pending_moves`):
  every move row except one whose `http` starts with 4, which Salesforce refused and which moved
  nothing. A `failed` row with `http` 0 (no answer: a timeout or an unreadable body) or a 5xx, and
  a `sending` row, count. On 2026-10-24 the ledger holds 18 move rows, all `ok` 200, and no undo
  row: N is 18.
- Its dry run shows exactly N lines, each an id of `data/sf_folders_2026-10-23/move_plan.csv` going
  back to "DHIS2 Reports" ("Public Reports" for item 17, 00ORP000006XXEf2AO); then, on Ryan's go,
  the same with `--apply`: each to its old folder and label, last first.
- Any other line in that dry run (another id, another folder, or a count other than N) stops the
  rollback for Ryan: the ledger is shared, `undo` reverses its pending moves last first whatever
  their tag, and those moves are not this ticket's to undo.
- The five dashboards go back by hand in Lightning (Ryan), each to the DHIS2 folder it came from,
  checked with SOQL on `Dashboard`.
- The copies stay in Decommissioned: 18 reports and 2 dashboards. The 3 dynamic dashboards have
  no copy (the clone was refused, Result); they were moved only, Ids unchanged, and their metadata
  is in the retrieve in `data/sf_folders_2026-10-23/before/`.
- The two new folders are left in place, with their shares unchanged.

## Result

- 2026-10-23: step 1 done read-only. All 22 ids are present; item 19's file label was wrong
  ("…Report_2025") and is fixed in `glow/sf_keep_list.csv` to the org's "GLOW of the Month
  Stories Report".
- 2026-10-23: step 2 done. The retrieve into `before/` and the build in `build/`: the two folders,
  each with the same 7 shares (4 internal users View, 2 internal users Manage, 1 group Manage).
- 2026-10-23: the dry run of the 23 copies (step 5): 23 lines, nothing written. The dry run of the
  report moves (step 6) was refused before the folder existed, as expected.
- 2026-10-24: Ryan's go on the folder names, the deploy, the copies and the moves (answer on #73).
- 2026-10-24: step 3 done. Check-only 0AfRP000002i4d30AA, deploy 0AfRP000002i4ef0AA (08:17 UTC, 2
  components, 0 errors): "GLOW Monthly Reports" 00lRP000007jdFhYAI and "GLOW Monthly Dashboards"
  00lRP000007jdFiYAI. Step 4: the read-back into `after/` has the same 7 shares (who and level) as
  the build on both folders, internal users and the one group only.
- 2026-10-24: step 5, 08:20 to 08:24 UTC, ledger `data/sf_folders_2026-10-23/ledger.csv`: 18
  reports and 2 dashboards copied into Decommissioned and read back. The 3 dynamic dashboards
  (Glow Club Attendance 01ZRP000006iWqL2AU, Implementation Dashboard 01ZRP000006jU9o2AE, Reporting
  01ZRP000006oxSr2AI) refused the clone, HTTP 400 BAD_REQUEST (2 attempts each, 6 `failed` rows):
  the org is at its limit of 5 dynamic dashboards (#74's finding), so a copy would be a 6th. #73
  moved them only (Ids unchanged); #75, #76 and #79 take their rollback from the metadata
  retrieve in `before/` instead.
- 2026-10-24: step 6, 18 reports moved into "GLOW Monthly Reports": `--limit 1` first, read back,
  then the 17 of `move_plan_rest.csv`; 18 move rows, all `ok` 200. SOQL: 18 reports in the
  folder, labels unchanged.
- 2026-10-24: steps 7 and 8. Ryan moved the 5 dashboards by hand into "GLOW Monthly Dashboards".
  SOQL read-back: "GLOW Monthly Dashboards" holds the 5 (Glow Club Attendance, Implementation
  Dashboard, GLOW Club Training, Mentors, Reporting); "DHIS2 Dashboards" and "Dhis2 Dashbords"
  hold no kept item; "GLOW Monthly Reports" holds the 18 kept reports. No Salesforce write is left
  in #73.
