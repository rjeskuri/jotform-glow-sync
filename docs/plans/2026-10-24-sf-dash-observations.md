---
title: GLOW Club Observations (D3) by partner and month, over the last 12 months
author: Claude (ticket #77, with Ryan's decisions of 2026-10-23 and 2026-10-24)
status: in-progress      # ticket #77; D3 + items 9-11 deployed 2026-10-25 (0AfRP000002i5hB0AQ); item 11's chart fix to deploy
created: 2026-10-24
intent: none - SOW p.5, Approach 1 (dashboards that reflect current data) and Ryan, 2026-10-21, "This data should be displayed by the Partner and Month."
---

# Plan: the GLOW Club Observations dashboard by partner and month

Ticket #77 (epic #68). The dashboard D3 of `glow/sf_keep_list.csv`, "GLOW Club Training"
(`01ZRP000006k2D32AI`, folder "GLOW Monthly Dashboards"), and its three kept reports, items 9-11,
show 2025 only (a fixed `Year__c` filter), by month name, and D3's snapshot dates from 2026-07-10
(RUNBOOK "Why the dashboards showed old data"). This change applies #74's fix steps 1-5 to them:
the last 12 months through `DHIS2__c.Period__c` (#128), grouped by the partner then the month, the
test-record rule of #70, and only items 9-11 on the dashboard. Procedure and the SOQL signals:
RUNBOOK "Monthly Report dashboards in Salesforce", `### GLOW Club Observations`.

## Context

- Ryan, 2026-10-24 on #77: the dashboard's only filter stays Partner Manager (each manager sees
  their partners); there is no Partner filter and no Month filter on any Monthly Report
  dashboard; viewers read the partner and the month from the reports' groupings. Labels stay as
  they are (#70).
- Item 16 ("Meeting with mentors to discuss program", `00ORP000004RJZ72AO`) is a D4 report on D3.
  #77 takes its component off D3 and lands first; #78 reworks item 16 and puts it on D4
  afterwards. Item 16's report itself is not changed here.
- The retrieve, 2026-10-24, is in `data/sf_dash_observations_2026-10-24/before/` (owner only,
  never committed): D3, its 4 kept reports (items 9, 10, 11, 16) in "GLOW Monthly Reports", the 5
  "DHIS2 Reports" reports D3 also uses, the report types `Dhis2` and `Monthly_Reports`, and
  `DHIS2__c`. Labels and folders equal the state #73 left. Against #74's retrieve of 2026-10-23,
  #73's move through the Analytics API dropped the `<description>` of items 9, 10, 11 and 16 and
  four unused bucket fields (on `Did_you_implement_GLOW_Club_last_month_f__c`) of items 9, 10 and
  16. The build gives items 9-11 their descriptions again, worded for the new grouping; the unused
  buckets stay out.
- #73 made copies of D3 and of items 9-11 and 16 in Decommissioned on 2026-10-24 (08:21-08:23
  UTC). This change makes its own copies, tagged #77, just before the deploy.
- The retrieved XML carries staff names (the Partner Manager filter's values, the running user):
  this plan carries counts and ids only.

## Build

`data/sf_dash_observations_2026-10-24/build/` (its own `package.xml`: the 3 reports and the
dashboard, API 67.0). `evidence/build_vs_before.diff` is the diff against `before/`.

- Items 9, 10 and 11, each:
  - the filter `Year__c equals 2025` becomes `Period__c equals LAST_N_MONTHS:12`; the standard
    date filter's column becomes `Period__c` (range All Time, `INTERVAL_CUSTOM`) in place of
    `CreatedDate`;
  - grouped down by `DHIS2__c$Account__c`, then `DHIS2__c$Period__c` by calendar month; the
    `Account__c.Owner` grouping and the `Month__c` grouping go;
  - the test-record rule: `DHIS2__c$Account__c` `notEqual` blank and `DHIS2__c$Account__c`
    `notContain` `test` (Account is not blank AND Account: Account Name does not contain "test";
    the lookup matches on the account's name, and `Account__c.Name` is not a column of `Dhis2`);
  - the filter on a non-blank answer stays; label, `params` and the other attributes as they are.
- Item 9 (`00ORP000004RJZC2A4`): Matrix, the answer `did_you_submit_your_GC_observation_form__c`
  across (Yes, No, and NA in some older months); its column is the record name (a grouping is
  never also a column). The form in use today (`dHIS2Controller`) clears this answer when no
  session was observed.
- Item 10 (`00ORP000004RJZD2A4`): Summary (no across grouping), the sum of
  `GC_sessions_did_you_observe_last_month__c`.
- Item 11 (`00ORP000005uf412AA`): Matrix, a number bucket "Observed" on
  `GC_sessions_did_you_observe_last_month__c` across: No for 0 (`to` 0), Yes for 1 or more
  (`from` 0); the sum of the field stays a column, and the report's record count stays off as
  retrieved (the param `co` 0; `build_item11/` turns it on, below). Each record is one partner's
  month, so the
  counts are partner-months; a partner with no Monthly Report for a month has no row (a missing
  response, apart from a No). An unanswered question is a No too, and the report does not tell it from 0:
  the form shows the field as 0 until a number is typed, and `dHIS2Controller.setNumber` saves a
  blank number as 0 (read in #74's retrieve of the controller and the LWC `dHIS2Forms`). So the
  field is never blank, the `!= null` filter removes nothing, and "0 blank" in the Result comes
  from the form, not from the data.
- The dashboard: 3 components, on items 9, 10 and 11, titled with the reports' labels: item 9 a
  stacked column of Yes and No by month, item 10 a column of the sum by month, item 11 a stacked
  column of Yes and No by month. The six other components go: item 16's and the five on "DHIS2
  Reports" reports. The Partner Manager filter (6 values), the running user, `dashboardType`
  `SpecifiedUser`, the title and the description are as retrieved; each component filters on
  `DHIS2__c$Account__c.Assigned_Partner_Manager__c` as before.
- Not verified before the check-only: the number bucket's `from`/`to` form (no number bucket in
  any retrieve of this org), and a component grouped by `Period__c` alone on a report grouped by
  partner then month. The check-only and the read-back settle both.
- Item 11's fix forward, 2026-10-25: `data/sf_dash_observations_2026-10-24/build_item11/` (its
  own `package.xml`: item 11's report only, API 67.0), from the fresh retrieve
  `fresh_2026-10-25b/` of D3 and items 9-11, which equals `after/`. It changes one value, the
  report param `co` from 0 to 1, which turns the report's record count on, so the report offers
  `RowCount`, the record count its component measures, beside its Sum (the Result, step 6). The
  Sum, the bucket, the groupings, the filters and the description are as deployed;
  `evidence/build_item11_vs_after.diff` is that one line. The dashboard is not in it: the
  component on item 11 stays as deployed.

## Rollout (live; each write on Ryan's go)

All with the VPN off (`route -n get default` shows `en0`), through the `sf` CLI login `glow`
(`.claude/skills/salesforce`). Each copy goes to Decommissioned before anything changes. The
copies' dry run ran on 2026-10-24 (`copy_dryrun.txt`: 4 lines, nothing written).

1. Copy the three reports into Decommissioned, on Ryan's go:
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_dash_observations_2026-10-24 --kind report --id 00ORP000004RJZC2A4 --tag "#77" --apply`,
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_dash_observations_2026-10-24 --kind report --id 00ORP000004RJZD2A4 --tag "#77" --apply` and
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_dash_observations_2026-10-24 --kind report --id 00ORP000005uf412AA --tag "#77" --apply`.
2. Copy the dashboard, on Ryan's go:
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_dash_observations_2026-10-24 --kind dashboard --id 01ZRP000006k2D32AI --tag "#77" --apply`
   (D3 runs as a specified user, so the clone is within the org's limit of 5 dynamic
   dashboards). Ryan names and describes the copy by hand in Lightning (`copy of
   01ZRP000006k2D32AI, #77`). The ledger rows are dated before the deploy.
3. On Ryan's go, check-only before the deploy: `sf project deploy start --dry-run -o glow -d force-app`,
   run within `data/sf_dash_observations_2026-10-24/build/`; its id goes in the Result.
4. On Ryan's go, the deploy: `sf project deploy start -o glow -d force-app` from the same
   folder; its deploy id goes in the Result.
5. Read back: retrieve the three reports and the dashboard into
   `data/sf_dash_observations_2026-10-24/after/` and compare it with `build/`. A difference
   beyond Salesforce's normalisation (`expandOthers`, default attributes) stops the rollout for
   Ryan.
6. Refresh the dashboard on Ryan's go:
   `PUT /services/data/v67.0/analytics/dashboards/01ZRP000006k2D32AI` (`sf api request rest
   --method PUT`), and read its refresh date back by a GET.
7. Fix item 11 forward (the refresh of step 6: item 11's component fails with 406, the Result).
   Item 11's report has its record count off (`co` 0, describe `hasRecordCount: false`), so it
   offers no `RowCount`, the record count its component measures; `build_item11/` turns the
   record count on (`co` 1, so `RowCount` beside its Sum) and changes nothing else (Build). First a fresh retrieve of D3 and items 9-11 that equals `after/`
   (2026-10-25: `fresh_2026-10-25b/`); a difference stops the step for Ryan. On Ryan's go,
   check-only, run within `data/sf_dash_observations_2026-10-24/build_item11/`:
   `sf project deploy start --dry-run -o glow -m "Report:GLOW_Monthly_Reports/Completed_Observing_Clubs_Alteast_Once_P_cn6"`.
   On Ryan's go, redeploy item 11's report only: the same command without `--dry-run`; its
   deploy id goes in the Result. Read back: retrieve item 11's report again and compare it with
   `build_item11/` (not `build/`). Then refresh the dashboard on Ryan's go (the PUT of step 6)
   and read item 11's component back by a GET: Yes and No for each month, no error. The SOQL
   check and the moves follow.
8. Check by SOQL on `DHIS2__c`, for the last complete month, that items 9-11 each equal their
   component (the RUNBOOK's query for each item) and that one partner's month equals the
   per-partner query. Then check the test-record rule on January 2026 and March 2026, the two
   months of the last 12 that hold a Monthly Report on a test account (one in each, with 0
   sessions and no item 9 answer): the item 11 component shows 33 No in January and 19 in March,
   equal to SOQL with the rule, where SOQL without the rule gives 34 and 20, and item 10's report
   counts 46 records in each of the two months, against 47 without the rule. So the test
   accounts' records are absent from every component. The counts go in the Result.
9. Move the five "DHIS2 Reports" reports D3 uses no more to Decommissioned, by the plan
   `data/sf_dash_observations_2026-10-24/move_plan.csv` (5 rows: `00ORP000005s3HN2AY`,
   `00ORP000005s3Iz2AI`, `00ORP000005s3nd2AA`, `00ORP000005s3qr2AA`, `00ORP000005uf0n2AA`): the
   dry run
   `python3 tools/sf_report_folders.py move --vpn-off --dir data/sf_dash_observations_2026-10-24 --plan data/sf_dash_observations_2026-10-24/move_plan.csv`,
   then on Ryan's go the same with `--apply --limit 1`, a SOQL check of that report, and the rest
   with
   `python3 tools/sf_report_folders.py move --vpn-off --dir data/sf_dash_observations_2026-10-24 --plan data/sf_dash_observations_2026-10-24/move_plan_rest.csv --apply`
   (`move_plan_rest.csv` is `move_plan.csv` without its first row, 4 rows: `move` moves a report
   again even when it is in its target already, so the full plan would write a sixth move row,
   Decommissioned to Decommissioned, for the first report). The ledger then holds 5 move rows. On
   2026-10-24 the dry run refused all 5 because D3 still used them (`move_dryrun.txt`); the only
   other dashboard using them is #73's copy of D3, in Decommissioned.
10. Ryan sets a weekly Subscribe on the dashboard in Lightning (the refresh is a subscription,
    not metadata), as he did for "Jotform Attendance".

## Rollback

1. First the five moved reports return to "DHIS2 Reports" by the undo of this change's ledger,
   because D3's six other components read them:
   `python3 tools/sf_report_folders.py undo --vpn-off --dir data/sf_dash_observations_2026-10-24`
   then the same with `--apply` on Ryan's go. Its dry run lists 5 lines, one per move row of
   step 9, newest first, each report back to "DHIS2 Reports"; any other line (another id or
   folder, or a count other than 5) stops the rollback for Ryan.
2. Then D3 and items 9-11 roll back together: redeploy those 4 components of this change's
   retrieve `data/sf_dash_observations_2026-10-24/before/` (check-only, Ryan's go, deploy) only
   while a fresh retrieve of the same 4 equals `after/`. The deploy names the 4 components one by
   one, within `before/`: the check-only is
   `sf project deploy start --dry-run -o glow -m "Dashboard:GLOW_Monthly_Dashboards/vbKFAhzWWcXLOmmkSckbvWkgmwtdrM" -m "Report:GLOW_Monthly_Reports/Submission_of_GC_observation_forms_M_P_iuz" -m "Report:GLOW_Monthly_Reports/Total_Number_of_Club_Observations_by_M_q3M" -m "Report:GLOW_Monthly_Reports/Completed_Observing_Clubs_Alteast_Once_P_cn6"`,
   and the deploy the same command with `--dry-run` dropped, on Ryan's go. `before/` also holds
   item 16's report, the five "DHIS2 Reports" reports, the report types `Dhis2` and
   `Monthly_Reports` and `DHIS2__c`, which this change leaves as they are: a deploy of the whole
   folder (`-d force-app` or its `package.xml`) would put those back to their state of
   2026-10-24 too, which the `after/` compare does not see, so it is never the rollback.
   Redeploying the 4 keeps every Id, so the dashboard's components read the old reports again,
   and D3 keeps its place in the FlexiPage `Monthly_Report_Dashboards`. This is the rollback that
   puts the dashboard back as it was. After Rollout step 7, item 11's report is compared with
   `build_item11/` in place of `after/`: the 4 roll back only while a fresh retrieve of D3 and
   items 9-10 equals `after/` and of item 11 equals `build_item11/`. Step 7 alone rolls back by
   redeploying item 11's report from `after/` (check-only, Ryan's go, deploy, with
   `-m "Report:GLOW_Monthly_Reports/Completed_Observing_Clubs_Alteast_Once_P_cn6"`) only while a
   fresh retrieve of it equals `build_item11/`: for that step, `after/` is item 11's before.
3. When the fresh retrieve and `after/` differ, someone has changed the dashboard or a report
   since the deploy: the rollback then starts from that fresh retrieve, by the epic's ritual.
   A rollback never deploys an older build or another change's retrieve (DECISIONS 2026-10-16).

The copies in Decommissioned (tagged #77, made before the deploy) restore D3 and its reports in
Lightning only as a set, because the dashboard copy points at the reports' original Ids, whose
content this deploy rewrites: alone, it shows its old components on the new reports. To use them:
move the three report copies and the dashboard copy back into "GLOW Monthly Reports" and "GLOW
Monthly Dashboards" (RUNBOOK "Decommissioned"), then point each of the dashboard copy's three
observation components at its report's copy (edit the component, its source report). The copies
keep their own Ids, so the FlexiPage `Monthly_Report_Dashboards` then needs the dashboard copy
in D3's place, by the ritual (check-only, Ryan's go, deploy). The copies stay in
Decommissioned otherwise, and nothing is deleted.

## Result

Read-only, 2026-10-24: the retrieve into `before/`, the build, the copies' dry run (4 lines,
nothing written), and the move dry run (refused, as expected, while D3 uses the 5 reports).

Steps 1-6 ran on 2026-10-25 in Ryan's interactive session, each write on his go, with the VPN
off. Steps 8-10 wait until item 11's chart works (Ryan, 2026-10-25: keep the deploy and fix
forward, step 7).

- Before the copies, a fresh retrieve equalled `before/` (`fresh_2026-10-25/`).
- Steps 1-2, the copies in Decommissioned, tagged #77, their ledger rows dated 2026-10-25
  04:49-04:51 UTC, before the deploy:
  - report copy `00ORP000009kM0L2AU` of item 9, `00ORP000004RJZC2A4`;
  - report copy `00ORP000009kM1x2AE` of item 10, `00ORP000004RJZD2A4`;
  - report copy `00ORP000009kM3Z2AU` of item 11, `00ORP000005uf412AA`;
  - dashboard copy `01ZRP00000BP52z2AD` of D3, `01ZRP000006k2D32AI`; its rename by hand in
    Lightning is still to do (Ryan).
- Step 3, check-only `0AfRP000002i5dx0AA`: Succeeded. Step 4, deploy `0AfRP000002i5hB0AQ`:
  Succeeded, 4 components, 0 errors.
- Step 5, the read-back into `after/`: the three reports equal `build/`; the dashboard differs
  from `build/` only in `showValues`, true -> false on the two ColumnStacked components (items 9
  and 11), which Ryan accepted as Salesforce's normalisation.
- Step 6, the refresh (PUT) at 07:28:20 UTC: the components on item 9 (`01aRP0000089gWTYAY`)
  and item 10 (`01aRP0000089gWUYAY`) refreshed. Item 11's component, `01aRP0000089gWVYAY`,
  fails with 406, "One or more of the fields selected in the component is no longer available in
  the report" (NO_DATA); the report itself runs (Analytics API, 1,022 records). The cause, by the
  Analytics describe (`GET /analytics/reports/00ORP000005uf412AA/describe`,
  `evidence/describe_00ORP000005uf412AA.json`): item 11's report has its record count off (the
  param `co` 0, describe `hasRecordCount: false`, as in `before/`), so its aggregates list only
  its Sum and no `RowCount`, while its component measures `RowCount`. Item 10's report sums the
  same column with `co` 1 and lists the Sum and `RowCount`
  (`data/sf_stale_2026-10-23/evidence/runs/00ORP000004RJZD2A4.json`); item 9's report has `co` 1
  and lists `RowCount` (`evidence/describe_00ORP000004RJZC2A4.json`). A first diagnosis on
  2026-10-25 named the wrong cause; the reviewer's check of `co` corrected it. The fix is Rollout
  step 7 (`build_item11/`), not yet run.

The baseline the components must equal after the deploy, SOQL on `DHIS2__c` for September 2026
(`Period__c = LAST_MONTH`, Account not blank, no test account), run 2026-10-24
(`evidence/soql_2026-10-24_september.txt`, `evidence/september_per_partner.csv`):

| Item | Report | September 2026 |
|---|---|---|
| 9 | Submission of GC observation forms M & P | 26 answered: 23 Yes, 3 No |
| 10 | Total Number of Club Observations M&P | sum 93 over 42 Monthly Reports |
| 11 | Completed Observing Clubs Alteast Once P | 27 partners Yes (observed 1 or more), 15 No (0), 0 blank (by the form: a blank is saved as 0) |

- 42 Monthly Reports from 42 partners; the test-record rule leaves out 0 records in September
  2026 and 2 in the last 12 months, both on a test account, one in January 2026 and one in
  March 2026 (`evidence/test_records_last12.csv`; months and values only).
- The rule's check, SOQL run 2026-10-25 (`evidence/soql_2026-10-25_test_months.txt`), with the
  rule and without it:

| Month | Item 9 (with = without) | Item 10 records, sum: with / without | Item 11 Yes; No: with / without |
|---|---|---|---|
| January 2026 | 7 Yes, 7 No, 8 NA | 46, 43 / 47, 43 | 13; 33 / 13; 34 |
| March 2026 | 21 Yes, 6 No, 1 NA | 46, 116 / 47, 116 | 27; 19 / 27; 20 |

- One partner, Abaana Community Outreach (ACO) Africa, September 2026: item 9 Yes, item 10 3
  sessions, item 11 Yes.
- A report filed or changed later moves both sides.
