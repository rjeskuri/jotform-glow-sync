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
- Least sure (BUILD.md): the summary formula's token
  `Attendance__c.Contact__c:UNIQUE + Attendance_Batch__c.Partner_Girls__c:SUM`, about 75%; the
  alternatives to try if the check-only refuses it are listed there.

## Rollout (live; each step on Ryan's go)

All with the VPN off, through the `sf` CLI login `glow` (`.claude/skills/salesforce`).
1. Retrieve fresh the components `build/package.xml` lists that exist today (the dashboard, the
   permission set) into a dated folder and compare with `data/sf_girls_tiles_2026-10-20/before/`.
   Equal: go on. Different: someone changed them since - stop and rebuild from that retrieve.
2. Check-only deploy of `build/`: from within `data/sf_girls_tiles_2026-10-20/build/`, `sf project
   deploy start --dry-run -o glow -d force-app`. A refused summary formula: the alternatives in
   `BUILD.md`, then check-only again.
3. Ryan's go in the conversation; then the same command without `--dry-run` deploys.
4. Read back: retrieve the eight components into `data/sf_girls_tiles_2026-10-20/after/` and
   compare with `build/` (expected: only Salesforce's own defaults, RUNBOOK "Attendance dashboard
   in Salesforce", Changing it).
5. SOQL per tile. Last month's tile must equal `COUNT_DISTINCT(Contact__c)` over the month's
   Jotform `Attendance__c` rows (batch `Creator__c` starting with `Jotform`, batch `Success`) +
   `SUM(Girls_Present__c)` over the three partners' `Partner report` batches (September 2026:
   the Jotform figure + 745). This is also the blank `Contact__c` check: each row-less batch gives the report one row
   with a blank `Contact__c`; equal means the unique count ignores it, one more means the blank
   counts as a girl - stop and ask Ryan (subtract it in the formula, or roll back). This month's
   tile: the same with `THIS_MONTH`, partner part 0.
6. Assign nothing: the permission set's assignments are unchanged. Refresh the dashboard (Ryan's
   go, RUNBOOK "Attendance dashboard in Salesforce", Refreshing through the API) and record the
   numbers in Result.

## Rollback

`data/sf_girls_tiles_2026-10-20/before/` is the fresh retrieve of what was live right before
the change; it is a rollback only for this change, while a retrieve still equals `build/` (or
`after/`) - DECISIONS 2026-10-16.
1. VPN off. Retrieve the dashboard and the permission set fresh and compare with `after/` (or
   `build/`); if either differs, stop and build the rollback from that fresh retrieve instead.
2. Equal: Ryan's go. From `data/sf_girls_tiles_2026-10-20/before/`, redeploy only the dashboard
   `Attendance/Jotform_Attendance_test` and the permission set `Attendance_Report_Viewer`: copy the
   two files into a new folder with `sfdx-project.json`, check-only, then deploy. The rest of
   `before/` is never deployed from it.
3. Then delete the five new components with a `destructiveChanges.xml`, in this order: the
   reports `Girls_Attended_Last_Month`, `Girls_Attended_This_Month` and `Girls_Attended_by_Month`,
   then the report type `Attendance_Batches_and_Girls`, then the field
   `Attendance_Batch__c.Partner_Girls__c` (its Admin profile entry goes with it).
4. Retrieve again and compare with `before/`; revert #59's docs change with it.

## Risks

- **The summary formula's token** may be refused by the check-only deploy (BUILD.md, about 75%).
  Mitigation: the listed alternatives, or build the formula once in the report builder and
  retrieve it.
- **A blank `Contact__c` counted as one girl** would make each tile one too high. Mitigation: the
  SOQL check of Rollout step 5 before anyone reads the tiles.
- **The Partner filter** set to one of the three partners shows only its Jotform girls (0 since
  2026-10-16): its batch sits on the partner account, whose parent is blank. Stated in the RUNBOOK.
- **A renamed partner account** drops out of filter 4 (it matches the names). Mitigation: rename
  the filter values with the account.

## Proof

- `scripts/harness_tests.sh test/runbook_test.py` (class `GirlsAttendedTilesRunbook`) and
  `scripts/verify.sh` → `VERIFY OK`.
- Live: the read-back (0 differences beyond Salesforce's defaults) and each tile against SOQL
  (Rollout step 5).

## Result

Not deployed yet: built 2026-10-20 in `data/sf_girls_tiles_2026-10-20/build/`, checked offline
only (BUILD.md); the check-only deploy and the deploy wait for Ryan's go.
