---
title: GLOW Club Training (D4, "Mentors") by partner and month, over the last 12 months
author: Claude (ticket #78, with Ryan's decisions of 2026-10-23 and 2026-10-24)
status: in-progress      # ticket #78; built 2026-10-25, nothing deployed, the live steps await Ryan's go
created: 2026-10-25
intent: none - SOW p.5, Approach 1 (dashboards that reflect current data) and Ryan, 2026-10-21, "This data should be displayed by the Partner and Month."
---

# Plan: the GLOW Club Training dashboard by partner and month

Ticket #78 (epic #68). The dashboard D4 of `glow/sf_keep_list.csv`, labelled "Mentors" in the
org (`01ZRP000006quAj2AI`, folder "GLOW Monthly Dashboards"), and its kept reports, items 13-16,
show 2025 only (a fixed `Year__c` filter), with the month name as a column, and D4's snapshot
dates from 2026-08-13 (RUNBOOK "Why the dashboards showed old data"). This change applies #74's
fix steps 1-5 to them: the last 12 months through `DHIS2__c.Period__c` (#128), grouped by the
partner then the month, the test-record rule of #70, and items 13-15 on the dashboard now, item 16
once #77 has landed. Procedure and the SOQL signals: RUNBOOK "Monthly Report dashboards in
Salesforce", `### GLOW Club Training`.

## Context

- Ryan, 2026-10-24 (for all five dashboards #75-#79): the dashboard's only filter stays Partner
  Manager (each manager sees their partners); no Partner or Month filter (Ryan, 2026-10-24) on any
  Monthly Report dashboard; viewers read the partner and the month from the reports' groupings.
  Labels stay as they are (#70); the kept items live in "GLOW Monthly Reports" and "GLOW Monthly
  Dashboards" (#73).
- Ryan, 2026-10-24, item 16 ("Meeting with mentors to discuss program", `00ORP000004RJZ72AO`): it
  is a component of D3, the dashboard labelled "GLOW Club Training", and #77 takes it off D3 and
  lands first. #78 changes item 16 only after #77 has landed (Rollout, step 9); item 16's report is
  not in this build.
- Item 12, "New mentors recruited", has no report yet: #80 builds it and adds its component after
  this change, from a fresh retrieve. The layout leaves room for it.
- The retrieve, 2026-10-24 (VPN off), is in `data/sf_dash_training_2026-10-24/before/` (owner
  only, never committed): D4, items 13-16 in "GLOW Monthly Reports", the two "DHIS2 Reports"
  reports D4 uses, the report types `Dhis2` and `Monthly_Reports`, and the five `DHIS2__c` fields
  the items read. D4's XML equals #74's retrieve of 2026-10-23, and the labels and folders equal
  the state #73 left. #73's move through the Analytics API dropped the `<description>` of items
  13-16 and four unused bucket fields (on `Did_you_implement_GLOW_Club_last_month_f__c`); the build
  gives items 13-15 their descriptions again, worded for the new grouping, and the unused buckets
  stay out.
- D4 today: 2 components, both tables on "DHIS2 Reports" reports filtered on 2025 ("Mentors Discuss
  Program Implementation" `00ORP000005uecc2AA`, "Lead Training Session with Mentors LastM"
  `00ORP000005ufNN2AY`), none of items 13-16. Its filter "Assigned Partner Manager" has 6 values;
  its running user is active (`SpecifiedUser`) and stays as it is.
- Read-only counts, 2026-10-24 (`evidence/soql_2026-10-24.txt`): 58 partners have a Monthly Report
  in the last 12 months with the test-record rule (59 without), every one with a partner manager;
  567 Monthly Reports with the rule, 569 without; 42 partners in the last complete month.
- The retrieved XML carries staff names (the Partner Manager filter's values, the running user):
  this plan carries counts and ids only.

## Build

`data/sf_dash_training_2026-10-24/build/` (its own `package.xml`: the 3 reports and the
dashboard, API 67.0; only the files this change makes, RUNBOOK "Attendance dashboard in
Salesforce", "Changing it"). `evidence/build_vs_before.diff` is the diff against `before/`; the
build was made by a script from a copy of `before/`.

- Items 13, 14 and 15, each:
  - the filter `Year__c equals 2025` becomes `Period__c equals LAST_N_MONTHS:12`; the standard
    date filter's column becomes `Period__c` (range All Time, `INTERVAL_CUSTOM`) in place of
    `CreatedDate`;
  - grouped down by `DHIS2__c$Account__c`, then `DHIS2__c$Period__c` by calendar month; the
    `Account__c.Owner` grouping goes, and so does the `Month__c` column (a grouping is never also
    a column);
  - the test-record rule: `DHIS2__c$Account__c` `notEqual` blank and `DHIS2__c$Account__c`
    `notContain` `test` (Account is not blank AND Account: Account Name does not contain "test";
    the lookup matches on the account's name);
  - a description again; label, `params` and the other attributes as they are.
- Item 13 (`00ORP000004RJZE2A4`, "Number of mentors trained about module"): Summary, the sum of
  `Mentors_attended_the_training_sessions__c`.
- Item 14 (`00ORP000004RJZ82AO`, "Number of training sessions led"): Summary, the sum of
  `how_many_training_sessions_did_you_lead__c`.
- Item 15 (`00ORP000004RJZ62AO`, "Leading training sessions with mentors"): Matrix, the answer
  `Lead_any_training_sessions__c` across (Yes or No), its column the record name, and a filter on
  a non-blank answer. Each record is one partner's month, so the counts are partner-months; a
  partner with no Monthly Report for a month has no row (a missing response, apart from a No).
- The dashboard: 3 components, titled with the reports' labels: item 13 a column of the sum by
  month, item 14 a column of the sum by month, item 15 a stacked column of Yes and No by month.
  Items 13 and 14 fill the first row, item 15 the left half of the second; the second row's right
  half stays free for item 16 (step 9) and a third row for item 12 (#80). The two tables on "DHIS2
  Reports" reports go. The Partner Manager filter (6 values), the running user, `dashboardType`
  `SpecifiedUser` and the title are as retrieved; each component filters on
  `DHIS2__c$Account__c.Assigned_Partner_Manager__c` as before.
- Item 16's report and the two "DHIS2 Reports" reports are as retrieved and are in no deploy of
  this build.
- Not verified before the check-only: a component grouped by `Period__c` alone on a report grouped
  by partner then month (the same form as #77's build). The check-only and the read-back settle it.

## Rollout (live; each write on Ryan's go)

All with the VPN off (`route -n get default` shows `en0`), through the `sf` CLI login `glow`
(`.claude/skills/salesforce`). Each copy goes to Decommissioned before anything changes.

1. Retrieved 2026-10-24, read-only: `data/sf_dash_training_2026-10-24/before/` (Context). Just
   before step 2, a fresh retrieve of the dashboard and items 13-15 must equal `before/`; on a
   difference, stop and build again from that fresh retrieve.
2. Copy the four reports and the dashboard into Decommissioned, each on Ryan's go:
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_dash_training_2026-10-24 --kind report --id 00ORP000004RJZE2A4 --tag "#78" --apply` (item 13),
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_dash_training_2026-10-24 --kind report --id 00ORP000004RJZ82AO --tag "#78" --apply` (item 14),
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_dash_training_2026-10-24 --kind report --id 00ORP000004RJZ62AO --tag "#78" --apply` (item 15),
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_dash_training_2026-10-24 --kind report --id 00ORP000004RJZ72AO --tag "#78" --apply` (item 16) and
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_dash_training_2026-10-24 --kind dashboard --id 01ZRP000006quAj2AI --tag "#78" --apply` (D4).
   Each first runs as a dry run, the same command without its last flag, and its line is read.
   D4 runs as a specified user, so its clone is within the org's limit of 5 dynamic dashboards.
   Ryan names and describes the dashboard's copy by hand in Lightning (`copy of
   01ZRP000006quAj2AI, #78`). The ledger rows are dated before the deploy.
3. Check-only of the build: `sf project deploy start --dry-run -o glow -d force-app`, run within
   `data/sf_dash_training_2026-10-24/build/` (the three reports and the dashboard); its id goes in
   the Result.
4. On Ryan's go, the deploy: `sf project deploy start -o glow -d force-app` from the same
   `build/` folder; its deploy id goes in the Result.
5. Read back: retrieve the three reports and the dashboard into
   `data/sf_dash_training_2026-10-24/after/` and check that `after/` equals `build/` beyond
   Salesforce's normalisation (`expandOthers`, default attributes); a difference beyond it stops
   the rollout for Ryan.
6. Refresh the dashboard on Ryan's go:
   `PUT /services/data/v67.0/analytics/dashboards/01ZRP000006quAj2AI` (`sf api request rest
   --method PUT`), and read its refresh date back by a GET.
7. Check by SOQL on `DHIS2__c`, for the last complete month, that each component equals its
   item's query (RUNBOOK `### GLOW Club Training`), that one partner's cell in each report equals
   the one-partner query, and that the test accounts' records are absent from every component
   (their count for the month, by SOQL with `Account__r.Name LIKE '%test%'`, is 0). The counts go
   in the Result.
8. Move the two "DHIS2 Reports" reports D4 uses no more to Decommissioned, by the plan
   `data/sf_dash_training_2026-10-24/move_plan.csv` (2 rows: `00ORP000005uecc2AA`,
   `00ORP000005ufNN2AY`): the dry run
   `python3 tools/sf_report_folders.py move --vpn-off --dir data/sf_dash_training_2026-10-24 --plan data/sf_dash_training_2026-10-24/move_plan.csv`,
   then on Ryan's go the same with `--apply --limit 1`, a SOQL check of that report, and the rest
   with `--apply` (the same plan; the first row moves again within Decommissioned). Outside
   Decommissioned, D4 is the one dashboard using them (2026-10-24: their two other dashboards are
   in Decommissioned).
9. Item 16, once #77 has landed (Ryan, 2026-10-24): a fresh retrieve of item 16 and D4, which
   must equal item 16 in `before/` and D4 in `after/`; item 16 gets the fix of items 13-15 (a
   matrix with `Did_you_meet_with_mentors_as_a_group__c` across and its filter on a non-blank
   answer kept), and its component goes in D4's free half row. The same ritual follows: a new
   build from that retrieve, check-only, deploy on Ryan's go, read-back, and the SOQL check of
   step 7 for item 16; the counts go in the Result.
10. Ryan sets a weekly Subscribe on the dashboard in Lightning (the refresh is a subscription,
   not metadata), as he did for "Jotform Attendance".

## Rollback

- Restore the dashboard and its reports from their copies in Decommissioned, made with the tag #78
  before the deploy: open each copy, then Save As or move it back into "GLOW Monthly Reports" or
  "GLOW Monthly Dashboards" (RUNBOOK "Decommissioned"). A copy put back keeps the copy's Id, so the
  reports' and the dashboard's Ids change that way.
- Or redeploy this change's retrieve `data/sf_dash_training_2026-10-24/before/` (its D4 and items
  13-15: check-only, Ryan's go, deploy) only while a fresh retrieve equals `after/`. That keeps
  every Id.
- When the fresh retrieve and `after/` differ, someone has changed the dashboard or a report since
  the deploy: the rollback then starts from that fresh retrieve, by the epic's ritual.
- A rollback never deploys an older build, never a `build/` and never another change's retrieve
  (DECISIONS 2026-10-16).
- Before D4 goes back to its two old components, the two moved reports return to "DHIS2 Reports"
  by the undo of this change's ledger:
  `python3 tools/sf_report_folders.py undo --vpn-off --dir data/sf_dash_training_2026-10-24`
  (the dry run lists the 2 moves), then the same with `--apply` on Ryan's go.
- The copies stay in Decommissioned, and nothing is deleted.

## Result

Done so far, offline and read-only, 2026-10-24 and 2026-10-25: the retrieve into `before/`
(VPN off), the build in `build/` (3 reports and the dashboard, 4 files; the diff in
`evidence/build_vs_before.diff`) and the move plan (2 rows). Nothing is deployed, copied or moved:
steps 2-10 of the Rollout are live and await Ryan's go, and step 9 also waits for #77.

The baseline the components are checked against after the deploy, #74's SOQL on `DHIS2__c` for
September 2026, the last complete month, run 2026-10-23 (RUNBOOK "Why the dashboards showed old
data"): item 13 152, item 14 27, item 15 41 answered (19 Yes, 22 No), item 16 41 answered (37 Yes,
4 No), from 42 partners with none on a test account. A report filed or changed later moves both
sides; step 7 runs the queries again on its day.
