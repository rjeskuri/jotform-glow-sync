---
title: The GLOW Club Attendance dashboard (D1) and its reports by Partner and Month, last 12 months
author: Claude (ticket #75, with Ryan's decisions of 2026-10-23 and 2026-10-24)
status: done             # ticket #75; deployed 2026-10-26 on Ryan's go (0AfRP000002i7HZ0AY), read back, checked against SOQL, moves done
done: 2026-10-26
created: 2026-10-24
intent: Ryan, 2026-10-21 - "This data should be displayed by the Partner and Month."; SOW p.5, Approach 1
---

# Plan: D1 "Glow Club Attendance" by Partner and Month

Ticket #75 (epic #68). D1 is the dashboard "Glow Club Attendance" (`01ZRP000006iWqL2AU`, folder
"GLOW Monthly Dashboards") with items 1-4 of `glow/sf_keep_list.csv` (folder "GLOW Monthly
Reports"). #74 found why it showed old data (RUNBOOK "Monthly Report dashboards in Salesforce",
`### Why the dashboards showed old data`); #128 added `DHIS2__c.Period__c`. This plan fixes D1
and items 1, 3 and 4 by Ryan's decisions, and retires item 2 from D1. What each component counts,
its SOQL signal and the rollback: RUNBOOK `### GLOW Club Attendance`.

## Context

- Ryan's decisions (on #74 and #75): the period is the last 12 months on `Period__c`; every
  report groups by the partner (`Account__c`), then the month; the test-record filter `Account is
  not blank AND Account: Account Name does not contain "test"` on every report (#70); item 1
  counts `Attendance_submitted_electronically__c`; item 2 is retired from D1, its report to
  Decommissioned; labels stay; component titles are the reports' labels.
- Ryan, 2026-10-24 on #75, for all five dashboards: the one dashboard filter is Assigned Partner
  Manager (`DHIS2__c$Account__c.Assigned_Partner_Manager__c`), so each manager sees the partners
  assigned to them. There is no Partner filter and no Month filter; the reports keep the partner
  and the month as their groupings.
- `data/sf_dash_attendance_2026-10-24/` (owner only, never committed): `before/` the live
  retrieve, `build/` the change, `make_build.py` the script that made it from a copy of
  `before/`, `copy_dryrun.txt` and `move_dryrun.txt` the dry runs, `move_plan.csv` the moves
  after the deploy, `evidence/` the SOQL counts. The retrieved XML carries staff names and an
  address (the running user, the owner, the filter's values): never quoted.
- What must not change: the "Jotform Attendance" dashboard and the two Attendance folders,
  `tools/sf_partner_monthly.py`, every label, D1's running user and its type (`LoggedInUser`).

## Build

`build/` holds only what changes: the dashboard and the reports of items 1, 3 and 4. Item 2's
report and the report type `Monthly_Reports` are unchanged and left out. The report type `Dhis2`
joined the build on 2026-10-26 (Ryan's decision, after the first check-only refused item 1, step
3): `Dhis2.reportType-meta.xml` is the fresh retrieve of 2026-10-26 plus the one column
`DHIS2__c$Attendance_submitted_electronically__c` (not checked by default), which item 1 needs.

- Every report: `Year__c equals <year>` becomes `Period__c equals LAST_N_MONTHS:12`; the standard
  date filter's column becomes `Period__c` (All Time) in place of `CreatedDate`; two filter lines
  on `Account__c` (not equal to blank, does not contain `test`) carry the test-record rule; the
  groupings become the partner (`Account__c`), then `Period__c` by calendar month, and the
  `Account__c.Owner`, `Account_Owner_Check__c` and `Month__c` groupings go.
- Item 1 "Collection of Attendance Roster by Month" (`00ORP000004RJYv2AO`, matrix): its column
  `collect_last_month_s_attendance__c` becomes `Attendance_submitted_electronically__c`, with the
  filter that checkbox equals true; the measure is the record count.
- Item 3 "Participation by Month and Partner" (`00ORP000005rSbB2AU`, matrix): the sum of
  `Monthly_Total__c`, as before.
- Item 4 "GLOW Club Each Week" (`00ORP000005ufOz2AI`, summary): its two filters on
  `Monthly_Total__c` (not blank, not 0) and `Account__c` not blank stay; `Week_1__c` and
  `Week_2__c` get the Sum that weeks 3 to 5 have.
- The dashboard: three components in place of six, titled with the reports' labels: items 1 and
  3 as bar charts on the partner, then the month; item 4 as a Lightning table (the partner, the
  month, the sums of weeks 1 to 5 and of `Monthly_Total__c`). The components on item 2 and on the
  four reports held for D1 (`00ORP000004RJZ92AO`, `00ORP000005rTk92AE`, `00ORP000005rTNZ2A2`,
  `00ORP000005rTQn2AM`) go. The filter Assigned Partner Manager stays on every component, with 7
  values: today's 6 and the one active manager with partners in the window who had none.
- The build's own risk: the table's Sum columns are written `s!DHIS2__c.Week_1__c` (and so on),
  a form no retrieve in this org shows yet; the check-only proves it or refuses it, and a refusal
  stops the rollout for Ryan.

Counts for the build (SOQL, 2026-10-24, the test-record rule applied): 58 partners have Monthly
Reports in the last 12 months, under 8 managers, every partner with one; 7 of the managers are
active. The filter's 7 values are within Salesforce's 50 per filter.

## Rollout (live; each write on Ryan's go)

All with the VPN off, through the `sf` CLI login `glow`, in the interactive session.

1. Retrieve, done 2026-10-24: D1 (`01ZRP000006iWqL2AU`), the reports of items 1-4 and the report
   types `Dhis2` and `Monthly_Reports` into `data/sf_dash_attendance_2026-10-24/before/`. Labels
   and folders equal what #73 left; the build is made from a copy of it.
2. Copies into Decommissioned, before anything changes, one per report:
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_dash_attendance_2026-10-24 --kind report --id 00ORP000004RJYv2AO --tag "#75" --apply`,
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_dash_attendance_2026-10-24 --kind report --id 00ORP000005rTiX2AU --tag "#75" --apply`,
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_dash_attendance_2026-10-24 --kind report --id 00ORP000005rSbB2AU --tag "#75" --apply` and
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_dash_attendance_2026-10-24 --kind report --id 00ORP000005ufOz2AI --tag "#75" --apply`.
   Each copy's `--apply` runs on Ryan's go. The dry runs (the same commands without `--apply`)
   ran 2026-10-24: 4 lines, nothing written (`copy_dryrun.txt`). The dashboard is dynamic and the
   API refuses its copy (the org is at its limit of 5 dynamic dashboards, #73), so its rollback is
   the retrieve in `before/`.
3. Check-only: `sf project deploy start --dry-run -o glow -d force-app` within
   `data/sf_dash_attendance_2026-10-24/build/`, on Ryan's go (a check-only is a write in this
   epic), after the copies read back in Decommissioned. On 2026-10-26 the first check-only was
   refused because the report type `Dhis2` lacked item 1's column; the column was added to
   `build/` (Build, above) and the check-only run again.
4. On Ryan's go, deploy: `sf project deploy start -o glow -d force-app` within `build/`, its id
   recorded in the Result.
5. Read back: retrieve the dashboard and the three reports into
   `data/sf_dash_attendance_2026-10-24/after/` and compare `after/` with `build/`: no differences
   beyond Salesforce's normalisation (default attributes, `expandOthers`).
6. Refresh D1 (a PUT, Ryan's go), then check each component's total and one partner's month for
   September 2026 against SOQL on `DHIS2__c`, the queries in RUNBOOK `### GLOW Club Attendance`:
   item 1 = 21, item 3 = 4,861 over 42 Monthly Reports, item 4 = 4,861 over 36 with weeks 2,428,
   1,676, 1,492, 1,314 and 518; the partner "Mahila Margadarshi" = 1 record, 220, weeks 60, 61,
   60, 25 and 0, ticked 1. With the manager `005RP000000qlipYAA` selected in the filter, D1 shows
   that manager's 12 partners, and for September 2026 9 partners, 1,300 and 7 ticked. A test
   account's records are absent from every component (2 Monthly Reports of test accounts in the
   window, none of them shown).
7. Moves, after the deploy: item 2's report (`00ORP000005rTiX2AU`) and the four reports held for
   D1 alone move to Decommissioned by
   `python3 tools/sf_report_folders.py move --vpn-off --dir data/sf_dash_attendance_2026-10-24 --plan data/sf_dash_attendance_2026-10-24/move_plan.csv`
   (the dry run first, then `--apply --limit 1` on Ryan's go, then the rest). The dry run of
   2026-10-24 refused all 5 rows, as it must while D1 still uses them (`move_dryrun.txt`).
8. Ryan decides whether D1 gets a dashboard subscription (outline step 6); D1 runs as the viewer.

## Rollback

- The dashboard is dynamic and the API refuses to copy it (the org is at its limit of 5 dynamic
  dashboards), so it has no Decommissioned copy: its rollback is this change's retrieve
  `data/sf_dash_attendance_2026-10-24/before/`.
- The order, step 7's moves undone before anything is deployed: the dashboard in `before/` names
  its six reports by folder path, and step 7 moves five of them (item 2's report from "GLOW
  Monthly Reports", the four held reports from "DHIS2 Reports") to Decommissioned, so after step 7
  a check-only of `before/` is refused (those reports are no longer at their paths) until the moves
  are put back. They
  are put back by
  `python3 tools/sf_report_folders.py undo --vpn-off --dir data/sf_dash_attendance_2026-10-24`
  (its dry run first, then `--apply` on Ryan's go), last first. Before step 7 there is nothing to
  undo.
- Then the dashboard and its three reports are restored by deploying their files in `before/`
  only while a fresh retrieve of them equals `after/` (nothing has changed them since this
  change's deploy), never from an older build or retrieve (DECISIONS 2026-10-16), on Ryan's go
  after a check-only.
- The column `Attendance_submitted_electronically__c` added to the report type `Dhis2` is
  additive and harmless, so it may stay. To take it out as well, after the reports are back,
  retrieve `Dhis2` fresh, take that one column (`DHIS2__c$Attendance_submitted_electronically__c`)
  out of the retrieved file, then check-only and deploy that file on Ryan's go, never an older
  build or retrieve of `Dhis2` (DECISIONS 2026-10-16: `Dhis2` is shared with #76-#79, which may
  add columns later); the item 1 report in `before/` does not use the column. While the fresh
  retrieve still equals `after/`'s `Dhis2.reportType-meta.xml`, the result is byte-for-byte
  `data/sf_dash_attendance_2026-10-24/fresh_2026-10-26/`'s file, the comparison, not a source to
  deploy.
- A Salesforce user restores a report from its copy in Decommissioned (step 2, tagged `#75`):
  open the copy, then Save As or move it into "GLOW Monthly Reports" (RUNBOOK, the archive rule).
- Nothing is deleted: the copies stay in Decommissioned.

## Result

- 2026-10-24: step 1 done, read-only. The retrieve's labels and folders equal #73's state. Two
  other differences from #74's retrieve of 2026-10-23: the reports of items 2 and 4 lost their
  descriptions (every kept report has none since #73's moves), and D1's running user is Ryan's
  user since his hand move; both left as they are in the build.
- 2026-10-24: the dry runs of the 4 copies (4 lines, nothing written) and of the moves (refused,
  as expected); the build made and the SOQL numbers of step 6 counted.
- 2026-10-25 07:45-07:47 UTC, step 2 on Ryan's go (his answer on #75, 2026-10-25): the 4 copies
  into Decommissioned, tagged `#75`, 4 ledger rows `ok`: item 1 `00ORP000009kMtB2AU`, item 2
  `00ORP000009kMun2AE`, item 3 `00ORP000009kMwP2AU`, item 4 `00ORP000009kMy12AE`.
- 2026-10-26, before the check-only: a fresh retrieve of D1 and the reports of items 1, 3 and 4
  into `data/sf_dash_attendance_2026-10-24/fresh_2026-10-26/` is byte-equal to `before/`; the
  report type `Dhis2` is unchanged since 2026-10-24.
- 2026-10-26, step 3: the first check-only (`0AfRP000002i7EL0AY`) failed: item 1's column
  `DHIS2__c$Attendance_submitted_electronically__c` is not in the report type `Dhis2`. Ryan,
  2026-10-26: add the column in the same deploy. `build/` then also held
  `Dhis2.reportType-meta.xml`, the fresh retrieve plus that one column (not checked by default);
  its rollback takes that column out of a fresh retrieve (Rollback). The second check-only
  (`0AfRP000002i7Fx0AI`) passed, 5/5 components.
- 2026-10-26, step 4, on Ryan's go: deploy `0AfRP000002i7HZ0AY`, 5/5 components, Succeeded.
- 2026-10-26, step 5: `after/` equals `build/`, apart from CR line endings in one formula of
  item 4.
- 2026-10-26, step 6: D1 refreshed 03:01 UTC, 3/3 components with data. The reports against SOQL
  for September 2026 (`evidence/soql_check_2026-10-26.txt`), every number equal to the expected
  one in step 6: item 1 = 21; item 3 = 4,861 over 42 Monthly Reports; item 4 = 4,861 over 36,
  weeks 2,428, 1,676, 1,492, 1,314 and 518; "Mahila Margadarshi" = 1 record, 220, weeks 60, 61,
  60, 25 and 0, ticked 1; the manager `005RP000000qlipYAA`: 12 partners over the 12 months, and
  for September 2026 9 partners, 1,300 and 7 ticked (SOQL). The 2 Monthly Reports of test
  accounts in the window are absent from the reports' totals.
- 2026-10-26 03:03-03:04 UTC, step 7 on Ryan's go: the 5 reports (item 2's and the four held for
  D1) moved to Decommissioned, `--limit 1` first, then the rest; 6 ledger rows, the second a
  Decommissioned-to-Decommissioned row for item 2's report (the full run moving `--limit 1`'s
  report again, which changed nothing; the undo, last first, still ends with it in its old
  folder). The only component that uses any of the 5 is on a dashboard in Decommissioned; all 5
  read back in Decommissioned.
- Step 8: no dashboard subscription on D1 (Ryan, 2026-10-25).
- 2026-10-26 ~03:50 UTC, the Partner Manager filter view, read-only: D1 refreshed with
  `?filter1=` set to the manager `005RP000000qlipYAA`'s filter option `0ICRP000000D5l74AC` (a
  filtered PUT), then a filtered GET: item 1 September 7 (ticked); item 3 September 1,300 over 9
  partners with a value, 12 partners listed; item 4 September 1,300, 9 records, weeks 851, 499,
  361, 235 and 43. Equal to the SOQL of step 6 (12 partners; September 9, 1,300, 7 ticked).
- Not verified: the filter view was not opened in Lightning.
