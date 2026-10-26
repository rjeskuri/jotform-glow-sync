---
title: GLOW Club Reporting (the dashboard "Reporting", items 17 and 18) and the GLOW of the Month table (item 19) by Partner and Month
author: Claude (ticket #79, with Ryan's decisions of 2026-10-23, 2026-10-24 and 2026-10-25)
status: done   # ticket #79; built 2026-10-24, Ryan's go 2026-10-25, deployed 2026-10-26 and checked against SOQL
created: 2026-10-24
intent: Ryan, 2026-10-21 - "This data should be displayed by the Partner and Month."
---

# Plan: GLOW Club Reporting and the GLOW of the Month table

Ticket #79 (epic #68). The dashboard "Reporting" (`01ZRP000006oxSr2AI`, D5) and its items 17
("Approved Approvals monthly report", `00ORP000006XXEf2AO`) and 18 ("Reports completed on time",
`00ORP0000054DyH2AU`), and the table, item 19 ("GLOW of the Month Stories Report",
`00ORP000005p2L32AI`), get the fix #74 recorded (RUNBOOK "Monthly Report dashboards in
Salesforce", "Why the dashboards showed old data"): the last 12 months through `Period__c`,
grouped by the partner then the month, the test-record rule, and items 17 and 18 on the
dashboard. What each one counts, the filters and the SOQL signals: RUNBOOK "GLOW Club Reporting".

Ryan's decisions (2026-10-23 and 2026-10-24, on #74 and #79): the period is the last 12 months
through `DHIS2__c.Period__c`; the test-record rule of #70 on every kept report; labels stay; a copy
of each report goes to Decommissioned before it changes, and the dashboard, dynamic, has the
retrieve `before/` as its rollback (the API refuses its copy at the org's 5 dynamic dashboards);
the dashboards keep the Partner Manager filter as their only filter, with no Partner or Month
filter (2026-10-24, all five dashboards; DECISIONS 2026-10-24). Ryan, 2026-10-25: go for this
Rollout, run in an interactive session; add the missing active manager to the filter; item 19
from summary to tabular confirmed.

## Build

Everything under `data/sf_dash_reporting_2026-10-24/` (owner only, never committed).

- `before/`: the retrieve of 2026-10-24 (VPN off): the dashboard, the three reports, the report
  "Partner Report Submission On Time" (`00ORP000005u1WP2AY`, the dashboard's one component today),
  the two folders and the report type `Dhis2`. Labels and folders are the state #73 left: the
  three reports in "GLOW Monthly Reports", the dashboard in "GLOW Monthly Dashboards", each label
  as in `glow/sf_keep_list.csv`. Since the #74 retrieve of 2026-10-23, the dashboard's running
  user changed (the hand move of #73; it runs as the viewer, so the setting is the fallback only)
  and item 19 lost its description; items 17 and 18 are unchanged.
- `build/`: the three reports and the dashboard, made from `before/` by `build79.py` beside it
  (text edits; the four files parse as XML); `evidence/diff_summary.txt` and
  `evidence/before_build.diff` list every change:
  - item 17: groupings `Account_Owner_Check__c`, `Approved__c`, `Month__c` replaced by
    `Account__c`, then `Period__c` by month; the `Account__c` column removed (a grouping now);
    filters kept (Account not blank, `Approved__c` = 1) plus `Period__c equals
    LAST_N_MONTHS:12` and Account does not contain "test"; its chart groups by `Period__c`;
  - item 18: groupings `Account__c.Owner`, `Month__c` replaced by `Account__c`, then `Period__c`
    by month; the `Account__c` column removed; the period and the test-record rule as its filters;
  - item 19: summary (grouped by `Month__c`) made tabular, no grouping, the column `Period__c`
    added beside `Account__c`; `Year__c equals 2026` replaced by the period; the period and Account
    filters unlocked for the viewer, the "test" condition locked;
  - each: standard date column `Period__c`, All Time, in place of `CreatedDate`;
  - the dashboard: its one component gives way to two tables, items 17 and 18, titled with the
    reports' labels, a row per partner and month; the Partner Manager filter, the only filter, with
    7 managers: the 6 it offered plus the active manager it lacked (Ryan, 2026-10-25), the name in
    the build only; the inactive eighth (one partner) left out by a Ruling made in the build, not
    by Ryan, open for him to reverse and no rule for #75-#78 until he confirms it; running user
    and "run as the viewer" unchanged.
- The table columns' names for the `Period__c` grouping (`DHIS2__c.Period__c`): proven in this
  org by the check-only `0AfRP000002i6N70AI` and the deploy `0AfRP000002i7330AA`, both
  succeeded, and the read-back `after/` equals `build/` (Result, steps 3 to 5).
- Items 17 and 18 are also components of two retired dashboards in Decommissioned ("Approval
  Status Monthly Reports", "Reporting Rate Dashboards"); those components follow the new groupings.

## Rollout

On Ryan's go, VPN off, in the main session (never a subagent), with `--vpn-off` on every tool.

1. Retrieve the dashboard, the three reports and their folders fresh into
   `data/sf_dash_reporting_<date>/before/` and compare it with
   `data/sf_dash_reporting_2026-10-24/before/`; on a difference, stop and rebuild `build/` from the
   fresh retrieve.
2. Copy each report into Decommissioned, every one of items 17-19, the dry run first:
   `python3 tools/sf_report_folders.py copy --vpn-off --kind report --id 00ORP000006XXEf2AO --tag "#79"`,
   `python3 tools/sf_report_folders.py copy --vpn-off --kind report --id 00ORP0000054DyH2AU --tag "#79"`,
   `python3 tools/sf_report_folders.py copy --vpn-off --kind report --id 00ORP000005p2L32AI --tag "#79"`.
   Then, on Ryan's go, the same with `--apply`:
   `python3 tools/sf_report_folders.py copy --vpn-off --kind report --id 00ORP000006XXEf2AO --tag "#79" --apply`,
   `python3 tools/sf_report_folders.py copy --vpn-off --kind report --id 00ORP0000054DyH2AU --tag "#79" --apply`,
   `python3 tools/sf_report_folders.py copy --vpn-off --kind report --id 00ORP000005p2L32AI --tag "#79" --apply`.
   Each ledger row in `data/sf_report_folders/ledger.csv` is `ok` and dated before the change.
   The dashboard has its retrieve in `before/` as its rollback (its API copy is refused).
3. The check-only from `data/sf_dash_reporting_2026-10-24/build/`:
   `sf project deploy start --dry-run -o glow -d force-app`, on Ryan's go (the live gate asks).
4. On Ryan's go, deploy from `data/sf_dash_reporting_2026-10-24/build/`:
   `sf project deploy start -o glow -d force-app`.
5. Retrieve the same components into `data/sf_dash_reporting_2026-10-24/after/` and compare it
   with `build/`: they differ only by Salesforce's normalisation (default attributes, `expandOthers`).
6. Refresh the dashboard (`PUT /services/data/v67.0/analytics/dashboards/01ZRP000006oxSr2AI`, Ryan's
   go), then check each component against SOQL on `DHIS2__c` for the last complete month, by the
   signals of the RUNBOOK's "GLOW Club Reporting": each component's total and one partner's number
   equal SOQL, and item 19's row count too.
7. Check that the test accounts' records are absent: SOQL `SELECT COUNT(Id) FROM DHIS2__c WHERE
   Period__c = LAST_N_MONTHS:12 AND (Account__c = null OR Account__r.Name LIKE '%test%')` gives
   the records the rule leaves out, and the components show none of them.
8. Move "Partner Report Submission On Time" (`00ORP000005u1WP2AY`), which the dashboard no longer
   uses, to Decommissioned with `tools/sf_report_folders.py move --dir data/sf_dash_reporting_2026-10-24`
   (a plan of one row, the dry run, then `--apply --limit 1` on Ryan's go), its Id kept. The move
   goes in this change's own ledger, `data/sf_dash_reporting_2026-10-24/ledger.csv`, so its undo
   touches no other ticket's move.
9. Record the counts in Result, set `status: done`, and update the RUNBOOK's status line.

## Rollback

- The reports, items 17-19, are restored from their copies in Decommissioned, made by step 2 of
  the Rollout, as RUNBOOK "Decommissioned" says (open the copy, Save As into "GLOW Monthly
  Reports").
- The report "Partner Report Submission On Time" (`00ORP000005u1WP2AY`), which step 8 moved to
  Decommissioned, comes back first, before the dashboard: the dashboard of `before/` has its one
  component on that report. It is one move, in this change's own ledger: the dry run
  `python3 tools/sf_report_folders.py undo --vpn-off --dir data/sf_dash_reporting_2026-10-24 --limit 1`
  lists that report alone, back to "DHIS2 Reports", and then the same with `--apply` on Ryan's go.
  If the dry run lists any other move, stop and ask Ryan; he moves the report back to "DHIS2
  Reports" by hand in Lightning, and SOQL on `Report` shows the same Id there.
- The dashboard "Reporting" (D5) has no copy: the API refuses it at the org's limit of 5 dynamic
  dashboards (Ryan, 2026-10-24). The dashboard is restored by redeploying it from
  `data/sf_dash_reporting_2026-10-24/before/`, only while a fresh retrieve of it equals `after/`.
- Only the dashboard is deployed from `before/`, run in that folder: the check-only
  `sf project deploy start --dry-run -o glow -m "Dashboard:GLOW_Monthly_Dashboards/DGdiHNHQWRoBNviGBlNWJPnSYqTlMR"`,
  then the same deploy without `--dry-run` on Ryan's go. Never the report type `Dhis2`, the two
  folders or the "DHIS2 Reports" report that `before/` also holds; the three reports come back from
  their copies (above).
- If a fresh retrieve differs from `after/`, stop and ask Ryan. A rollback never deploys an older
  build or an earlier retrieve (DECISIONS 2026-10-16). Nothing is deleted.

## Result

Done 2026-10-26, on Ryan's go of 2026-10-25 in the interactive session, VPN off
(`evidence/rollout_2026-10-26.txt`, counts only):
- Step 1: the fresh retrieve of 2026-10-25 (`data/sf_dash_reporting_2026-10-25/before/`, 8
  components) equals `data/sf_dash_reporting_2026-10-24/before/`: no difference, `build/` stands.
- Step 2: the three copies in Decommissioned, read back, ledger rows `ok` dated 2026-10-25, before
  the deploy: item 17 as `00ORP000009kP7t2AE`, item 18 as `00ORP000009kPHZ2A2`, item 19 as
  `00ORP000009kPJB2A2`.
- Steps 3 and 4: the check-only `0AfRP000002i6N70AI` (2026-10-25) and the deploy
  `0AfRP000002i7330AA` (2026-10-26) both succeeded, 4/4 components. A first deploy call, on
  2026-10-25, was cut off when the session ended and never reached the org: the four components'
  `LastModifiedDate` was still 2026-10-24.
- Step 5: `after/` equals `build/` exactly (`diff -r` empty, 4 files).
- Step 6: the refresh needs a body (`-X PUT -b '{}'`, as in RUNBOOK "Attendance dashboard in
  Salesforce"); without it nothing refreshed. Refreshed 2026-10-26 02:44 UTC. For September
  2026, each component equals SOQL on `DHIS2__c`:
  - Item 17: 16 approved from 16 partners (SOQL 16); 437 in the last 12 months (SOQL 437).
  - Item 18: 42 filed from 42 partners (SOQL 42); 567 in the last 12 months (SOQL 567).
  - One partner, Development Consortium: 1 in item 17 and 1 in item 18 (SOQL 1 and 1).
  - Item 19, now tabular with the columns Partner and Period: 42 rows for September (SOQL 42) and
    567 in the window (SOQL 567).
- Step 7: the test-record rule leaves out 2 Monthly Reports of the window (SOQL). No component
  has a blank-Account group or a partner whose name contains "test"; item 18 has 58 partners, as
  SOQL gives for the window.
- The Partner Manager filter, the only filter, offers 7 managers. A refresh filtered to one
  manager through the Analytics API (`PUT` with `{"filters":[<option id>]}`) returned a status
  URL, but the filtered results stayed empty through the API, so one manager's view is not proven
  here: Ryan checks it in Lightning.
- Step 8: "Partner Report Submission On Time" (`00ORP000005u1WP2AY`), on no dashboard after the
  deploy, moved to Decommissioned 2026-10-26, read back, `ok` in this change's own ledger.
- Still to do by Ryan: the daily refresh (a Subscribe on the dashboard, Outline step 6) and the
  one-click check of the Partner Manager filter.

The baseline, 2026-10-24, before the change (September 2026, `Period__c =
LAST_MONTH`, with the test-record rule; `evidence/soql_2026-10-24_baseline.txt`):
- Item 17: 16 Monthly Reports approved (437 in the last 12 months).
- Item 18: 42 Monthly Reports filed, from 42 partners (567 in the last 12 months).
- Item 19: 42 rows.
- One partner, Development Consortium: 1 filed and 1 approved in September 2026.
- The test-record rule leaves out 2 of the 569 Monthly Reports of the last 12 months (11 of all
  time, on 2 test accounts or a blank Account), none of September 2026.
- 58 partners and 8 partner managers have Monthly Reports in the last 12 months; the Partner
  Manager filter offered 6 of the 8; the build offers 7 (the eighth, inactive, left out by a
  Ruling of the build, not Ryan's decision).
