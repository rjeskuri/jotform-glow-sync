---
title: The dashboard's top row becomes two girls-who-attended tiles (Jotform + 3 partners); total attendance no longer tracked
author: Claude (with Ryan's decisions of 2026-10-19)
status: accepted         # ticket #59; built 2026-10-20 in data/sf_girls_tiles_2026-10-20/build/, not deployed (awaits Ryan's go)
backlog: 72
created: 2026-10-20
intent: none - Ryan's request of 2026-10-19 (ticket #59)
---

# Plan: two "Girls who attended (Jotform + 3 partners)" tiles

Ticket #59 (follows #60, which copies the three partners' Monthly Max). Ryan, 2026-10-19: total
attendance (girls × sessions) is not a number to track; the dashboard shows unique girls who
attended in a month. The top row of the dashboard "Jotform Attendance"
(`Jotform_Attendance_test`) becomes two tiles headed "Girls who attended (Jotform + 3 partners)",
last month and this month so far: the Jotform girls who attended (each girl once) plus the Monthly
Max of Education and English for You, Tumaini La Maisha and Ng'aa Maskani, added with no
de-duplication.

## Context

- The rule (RUNBOOK "Attendance totals and partner-reported counts"): each tile = unique
  `Attendance__c.Contact__c` over the month's Jotform `Success` batches + the sum of
  `Girls_Present__c` over the three partners' `Partner report` batches of the month. This month's
  partner part is 0 until the partners' Monthly Report is filed and copied (about the 12th of the
  next month).
- It replaces the top row of 2026-10-15 (ticket #35, [plan](2026-10-15-attendance-total-three-partners.md)):
  "Total attendance (Jotform + 3 partners)", "Attendance (Jotform only)" and two "Girls who
  attended (Jotform only)" tiles, and the chart "Total attendance per month (Jotform + 3
  partners)".
- The partners' batches sit on the partner accounts themselves (#60), so the 2026-10-15 filter on
  the club's parent misses them: September 2026's three batches (745) are in the data, outside
  today's dashboard.
- Salesforce limits (2026-10-19): a dashboard Metric reads one report; a joined report reaches a
  dashboard only as a chart, so both parts share one report type; a summary formula may use
  unique counts (`FIELD:UNIQUE`), at most three per report.

## Build

`data/sf_girls_tiles_2026-10-20/` (owner only, never committed): `before/` is the fresh retrieve
of 2026-10-20 (the dashboard, the permission set, the Admin profile, the object, the report type
`Attendance_Totals` and six reports; its dashboard identical to what the 2026-10-15 deploy left),
`build/` the SFDX project with `package.xml` (8 components) and `BUILD.md` (each component, the
judgement calls, the offline checks), `DIFF.md` (the dashboard and the permission set against
`before/`). Built offline, no `sf` command.
- New: the formula field `Attendance_Batch__c.Partner_Girls__c` (`Girls_Present__c` when
  `Creator__c` is `Partner report`, else 0); the report type `Attendance_Batches_and_Girls`
  (`Attendance_Batch__c` with or without `Attendance__c`); the reports
  `Attendance/Girls_Attended_Last_Month`, `Attendance/Girls_Attended_This_Month` and
  `Attendance/Girls_Attended_by_Month`, filter logic `1 AND (2 OR (3 AND 4)) AND 5 AND 6`
  (`Success`; `Creator__c` starts with `Jotform`, or `Partner report` on one of the three
  partner accounts; the unlocked Partner and Club filters), summary formula `FORMULA1` = unique
  `Attendance__c.Contact__c` + the sum of `Partner_Girls__c`.
- Changed: the dashboard (the two tiles, the chart "Girls who attended per month (Jotform + 3
  partners)", two bullets of "How to read this dashboard"); the permission set
  `Attendance_Report_Viewer` and the Admin profile (Read on the new field, one entry each).
- No longer used by the dashboard once deployed, kept until Ryan decides which to delete: the
  reports `Total_Attendance_Last_Month`, `Jotform_Total_Attendance_Last_Month`,
  `Total_Attendance_by_Partner_by_Month` and `Jotform_Attendance_This_Month` (only this dashboard
  was retrieved, so another dashboard's use of them is unchecked).
- Unverified until the check-only deploy (BUILD.md, judgement calls 1 and 2): the summary
  formula's token `Attendance__c.Contact__c:UNIQUE + Attendance_Batch__c.Partner_Girls__c:SUM`
  (about 75%) and the `FORMULA1` chartSummary with no aggregate (about 90%). If the check-only
  refuses either, fix all three reports and the dashboard the same way, in the fallback order of
  `data/sf_girls_tiles_2026-10-20/build/BUILD.md`, and check-only again.

## Rollout (live, two phases; each deploy on Ryan's go)

All with the VPN off, through the `sf` CLI login `glow` (`.claude/skills/salesforce`). The
reports are deployed and checked against SOQL before the dashboard reads them.
1. Retrieve fresh the components `build/package.xml` lists that exist today (the dashboard, the
   permission set) into a dated folder and compare with `data/sf_girls_tiles_2026-10-20/before/`.
   Equal: go on. Different: someone changed them since - stop and rebuild from that retrieve.
2. The two manifests in `data/sf_girls_tiles_2026-10-20/build/` (written from `package.xml` if
   they are not there yet): `package-phase1.xml` = the field `Attendance_Batch__c.Partner_Girls__c`,
   the partial Admin profile, the permission set `Attendance_Report_Viewer`, the report type
   `Attendance_Batches_and_Girls` and the three reports (seven components); `package-phase2.xml` =
   the dashboard `Attendance/Jotform_Attendance_test`.
3. Phase 1: from within `build/`, check-only `sf project deploy start --dry-run -o glow -x
   package-phase1.xml`; Ryan's go in the conversation; then the same command minus `--dry-run`
   deploys.
4. Check the reports before the dashboard (counts only). The ids: SOQL `SELECT Id, DeveloperName
   FROM Report WHERE DeveloperName IN ('Girls_Attended_Last_Month', 'Girls_Attended_This_Month')`.
   Each report's `FORMULA1` grand total: `sf api request rest
   '/services/data/v62.0/analytics/reports/<id>?includeDetails=false' -o glow`, a GET with no
   body. Compare with SOQL (RUNBOOK "Attendance totals and partner-reported counts", Signals):
   last month must equal `COUNT_DISTINCT(Contact__c)` over the month's Jotform `Attendance__c`
   rows + `SUM(Girls_Present__c)` over the three partners' `Partner report` batches (2026-10-20:
   2,888 + 745 = 3,633); this month the same with `THIS_MONTH` (2,893 + 0). This is the blank
   `Contact__c` check: each row-less batch gives the report one row with a blank `Contact__c`.
   Equal means the unique count ignores it. One more means the blank counts as a girl; 745 less
   means filter 5 (the Partner filter's `Parent` contains "") drops the partner batches, whose
   parent is blank. Either way: stop and ask Ryan before phase 2.
5. Phase 2: from within `build/`, check-only `sf project deploy start --dry-run -o glow -x
   package-phase2.xml`; Ryan's go; then the same command minus `--dry-run` deploys the dashboard.
6. Refresh the dashboard (Ryan's go, RUNBOOK "Attendance dashboard in Salesforce", Refreshing
   through the API). Read back, once for both phases: phase 1 is checked between the phases by
   its numbers alone (step 4, through the Analytics API), and the retrieve-and-compare runs here,
   after phase 2, over all eight components of both phases - retrieve them into
   `data/sf_girls_tiles_2026-10-20/after/` and compare with `build/` (expected: only Salesforce's
   own defaults, RUNBOOK "Attendance dashboard in Salesforce", Changing it). Then each tile against
   SOQL, as in step 4, and record the numbers in Result. The permission set's assignments are
   unchanged.

## Rollback

`data/sf_girls_tiles_2026-10-20/before/` is the fresh retrieve of what was live right before
the change; it is a rollback only for this change, while a retrieve still equals `build/` (or
`after/`) - DECISIONS 2026-10-16.
1. VPN off. Retrieve the dashboard and the permission set fresh and compare with `after/` (or
   `build/`; after phase 1 alone, the permission set and `before/`'s dashboard); if either
   differs, stop and build the rollback from that fresh retrieve instead.
2. Equal: Ryan's go. From `data/sf_girls_tiles_2026-10-20/before/`, redeploy only the dashboard
   and the permission set: copy `before/dashboards/Attendance/Jotform_Attendance_test.dashboard-meta.xml`
   to `<new folder>/force-app/main/default/dashboards/Attendance/` and
   `before/permissionsets/Attendance_Report_Viewer.permissionset-meta.xml` to
   `<new folder>/force-app/main/default/permissionsets/`, beside an `sfdx-project.json` (as
   `build/`'s), then within `<new folder>` `sf project deploy start --dry-run -o glow -d force-app`
   and the same command minus `--dry-run`. After phase 1 alone, the permission set only. The rest
   of `before/` is never deployed from it.
3. Delete the five new components in three destructive deploys, in this order, each a
   `destructiveChanges.xml` beside an empty `package.xml`, check-only first, on Ryan's go:
   - first the reports `Girls_Attended_Last_Month`, `Girls_Attended_This_Month` and
     `Girls_Attended_by_Month` (`Report` members `Attendance/Girls_Attended_Last_Month` and so on;
     they may also go as the `--pre-destructive-changes` file of the report type's deploy);
   - then the report type `Attendance_Batches_and_Girls` (`ReportType`);
   - then the field `Attendance_Batch__c.Partner_Girls__c` (`CustomField`; its Admin profile
     entry goes with it).

   Each deploy is its own folder holding an empty `package.xml` (`<Package>` with only
   `<version>62.0</version>`) and a `destructiveChanges.xml` listing that deploy's components.
   Within the folder, check-only: `sf project deploy start --dry-run -o glow --manifest
   package.xml --post-destructive-changes destructiveChanges.xml`; then Ryan's go and the same
   command minus `--dry-run`. The next deploy starts after this one succeeded.
4. Retrieve again and compare with `before/`; revert #59's docs change with it.

## Risks

- **The summary formula's token and the `FORMULA1` chartSummary** are unverified until the
  check-only deploy (BUILD.md: about 75% and 90%). Mitigation: if refused, the same fix in all
  three reports and the dashboard, in BUILD.md's fallback order, or build the formula once in
  the report builder and retrieve it.
- **A blank `Contact__c` counted as one girl** would make each tile one too high; **filter 5
  dropping the partner batches** would make last month's 745 too low. Mitigation: the reports'
  SOQL check of Rollout step 4, before the dashboard is deployed.
- **The Partner filter** set to one of the three partners shows only its Jotform girls (0 since
  2026-10-16): its batch sits on the partner account, whose parent is blank. Stated in the RUNBOOK.
- **A renamed partner account** drops out of filter 4 (it matches the names). Mitigation: rename
  the filter values with the account.

## Proof

- `scripts/harness_tests.sh test/runbook_test.py` (class `GirlsAttendedTilesRunbook`) and
  `scripts/verify.sh` → `VERIFY OK`.
- Live: the two reports against SOQL between the phases (Rollout step 4), the read-back (0
  differences beyond Salesforce's defaults) and each tile against SOQL (step 6).

## Result

Not deployed yet: built 2026-10-20 in `data/sf_girls_tiles_2026-10-20/build/`, checked offline
only (BUILD.md); both phases' check-only deploys and deploys wait for Ryan's go.
