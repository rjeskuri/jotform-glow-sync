---
title: Item 12, "Partners that recruited new mentors", a component on GLOW Club Training (D4)
author: Claude (ticket #80, with Ryan's answer of 2026-10-26)
status: in-progress      # ticket #80; the build is ready (2026-10-26); the Rollout runs in an interactive session with Ryan
created: 2026-10-26
intent: none - SOW p.6 (a report of new mentors recruited by month) and GLOW's keep list, item 12 on GLOW Club Training; Ryan, 2026-10-26, on #80 (option A)
---

# Plan: item 12, the partners that recruited new mentors, on GLOW Club Training

Ticket #80 (epic #68). Keep-list item 12, "New mentors recruited", had no report. Ryan's answer on
the ticket (2026-10-26, option A): a new report, "Partners that recruited new mentors", counts the
Monthly Reports (`DHIS2__c`) answering Yes and No to `Recruit_any_new_mentors_last_month__c`, by
partner (`Account__c`) and month (`Period__c`, the month the Monthly Report covers), blank answers
left out, with the test-record rule (#70) and the last 12 months, built as items 15 and 16 are
(#78). Each Yes is one partner's month, not a number of mentors. Its component goes on the
dashboard D4 of `glow/sf_keep_list.csv`, labelled "Mentors" in the org (`01ZRP000006quAj2AI`,
folder "GLOW Monthly Dashboards"), and no separate dashboard is made (Ryan, 2026-10-26). The
measure: RUNBOOK "Monthly Report dashboards in Salesforce", `### GLOW Club Training`; the
decision: DECISIONS 2026-10-26.

## Context

- The ticket's needs-input question (2026-10-26) found no Salesforce field or object that holds
  the number recruited: the Monthly Report's Yes/No question is the one source with monthly data
  by partner. The evidence, counts only, is in `data/sf_new_mentors_2026-10-26/evidence/` (owner
  only, never committed). The rejected sources and their reasons are in DECISIONS 2026-10-26; this
  plan reads `Newly_recruited__c` nowhere and no contact with a "Lead Mentor" role.
- Ryan, 2026-10-24 (for all five dashboards #75-#79): the dashboard's only filter stays Partner
  Manager, and no Partner or Month filter (Ryan, 2026-10-24) is added; viewers read the partner
  and the month from the report's grouping. The new component filters on
  `DHIS2__c$Account__c.Assigned_Partner_Manager__c`, as D4's three components do.
- The retrieve, 2026-10-26 (VPN off, read-only), is in `data/sf_new_mentors_2026-10-26/before/`:
  D4 and item 15's report, "Leading training sessions with mentors"
  (`GLOW_Monthly_Reports/Leading_training_sessions_with_ieq`), the template of the new report;
  2 files. D4 there is byte-equal to the D4 that #78 deployed and read back on 2026-10-26: items
  13-15, a third row free for item 12, and the second row's right half free for item 16 (#78's
  step 9, after #77).
- The report type `Dhis2__c`, which item 15 uses, has the column
  `DHIS2__c.Recruit_any_new_mentors_last_month__c` (a GET of the Analytics report type,
  2026-10-26), and no report in the org has the label or the developer name of the new report (a
  SOQL count on `Report`, 0).
- Read-only counts, 2026-10-26 (`evidence/soql_signal_2026-10-26.txt`), over
  `Period__c = LAST_N_MONTHS:12` with the test-record rule: 524 Monthly Reports answer the
  question, 73 Yes and 451 No; 42 partners answered Yes in at least one month. Without the rule, 1
  more answered Monthly Report is on a test account or on no account (2 Monthly Reports in all),
  so the rule changes the figure and the check of step 7 means something.
- The retrieved XML carries staff names (the Partner Manager filter's values, the running user):
  this plan carries counts and ids only.

## Build

`data/sf_new_mentors_2026-10-26/build/` (its own `sfdx-project.json` and `package.xml`, API 67.0:
the new report and the dashboard, 2 members). The script
`data/sf_new_mentors_2026-10-26/build_new_mentors.py` wrote it from `before/`, which it only reads,
and refuses to write over an existing `build/`; `evidence/build_vs_before.diff` is the diff of D4
against `before/` and of the new report against its template.

- The new report, `GLOW_Monthly_Reports/Partners_that_recruited_new_mentors`, label "Partners that
  recruited new mentors", in "GLOW Monthly Reports" (the report folder of every kept report, #73):
  item 15's report with its answer field replaced, so the same recipe:
  - Matrix, the answer `Recruit_any_new_mentors_last_month__c` across (Yes or No), its column the
    record name, and a report filter on a non-blank answer;
  - grouped down by `DHIS2__c$Account__c`, then `DHIS2__c$Period__c` by calendar month;
  - the filter `Period__c equals LAST_N_MONTHS:12`, the standard date filter's column `Period__c`
    (range All Time, `INTERVAL_CUSTOM`);
  - the test-record rule: `DHIS2__c$Account__c` `notEqual` blank and `DHIS2__c$Account__c`
    `notContain` `test`;
  - a description: by partner and month, the Monthly Report's answer Yes or No, each Yes one
    partner's month, not a number of mentors.
- D4: one component added, a stacked column (`ColumnStacked`) of the record count, grouped by
  `DHIS2__c$Period__c` then the answer, titled with the report's label, in the left half of the
  third row (row 16, column 0, 6 columns wide, 8 rows high), its other attributes those of item
  15's component (`showValues` false, the read-back value of #78). Every other part of D4 is as
  retrieved: the three components, the Partner Manager filter (6 values), the running user,
  `dashboardType` `SpecifiedUser` and the title.
- `rollback/package.xml`: D4 alone, `GLOW_Monthly_Dashboards/fgMcyANlcTvERilgPVySaXCChURVlO`, the
  manifest of the fresh retrieve and of a redeploy of `before/` (Rollback).
- Not verified before the check-only: that Salesforce takes the report's developer name and its
  matrix with the new field across, and the component on it; the read-back of step 5 shows any
  value Salesforce normalises.

## Rollout (live; each write on Ryan's go)

All with the VPN off (`route -n get default` shows `en0`), through the `sf` CLI login `glow`
(`.claude/skills/salesforce`). A copy of D4 goes to Decommissioned before anything changes; the
new report has no earlier state to copy.

Every retrieve below goes into a new folder made for it, in `data/sf_new_mentors_2026-10-26/`:
`mkdir -p <folder>/force-app`, then `cp before/sfdx-project.json <folder>/`, then within
`<folder>` `sf project retrieve start -o glow -x <manifest>`, which writes into that folder's
`force-app/`. A retrieve never runs within `before/`, `build/` or an `after/` that already holds
files: it would overwrite them, and `before/` is the redeploy's source.

1. Retrieved 2026-10-26, read-only: `data/sf_new_mentors_2026-10-26/before/` (Context). Just
   before step 2, a fresh retrieve of D4 into a new folder `fresh_<date>/` (UTC date), by
   `rollback/package.xml` (`-x ../rollback/package.xml`), must equal D4 in `before/`; on a
   difference, stop and build again from that fresh retrieve.
2. Copy the dashboard D4 into Decommissioned, on Ryan's go:
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_new_mentors_2026-10-26 --kind dashboard --id 01ZRP000006quAj2AI --tag "#80" --apply`.
   It first runs as a dry run, the same command without its last flag, and its line is read. D4
   runs as a specified user, so its clone is within the org's limit of 5 dynamic dashboards. Ryan
   names and describes the copy by hand in Lightning (`copy of 01ZRP000006quAj2AI, #80`). The
   ledger row is dated before the deploy.
3. Check-only of the build: `sf project deploy start --dry-run -o glow -d force-app`, run within
   `data/sf_new_mentors_2026-10-26/build/` (the report and the dashboard); its id goes in the
   Result.
4. On Ryan's go, the deploy: `sf project deploy start -o glow -d force-app` from the same `build/`
   folder; its deploy id goes in the Result.
5. Read back: retrieve the report and the dashboard into `data/sf_new_mentors_2026-10-26/after/`,
   a new folder made as above, by `build/package.xml` (`-x ../build/package.xml`), and check that
   `after/` equals `build/` beyond Salesforce's normalisation (default attributes); a difference
   beyond it stops the rollout for Ryan. The new report's id goes in the Result.
6. Refresh the dashboard on Ryan's go, a `PUT` with a body
   (`sf api request rest /services/data/v67.0/analytics/dashboards/01ZRP000006quAj2AI --method PUT -b '{}'`),
   and read its refresh date back by a GET.
7. Check by SOQL on `DHIS2__c` that the component equals the query for each of the last six
   complete months, Yes and No apart, month by month:
   `SELECT Period__c, Recruit_any_new_mentors_last_month__c, COUNT(Id) FROM DHIS2__c WHERE Period__c = LAST_N_MONTHS:6 AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') AND Recruit_any_new_mentors_last_month__c != null GROUP BY Period__c, Recruit_any_new_mentors_last_month__c`
   (2026-10-26, April to September 2026, Yes/No: 3/41, 4/42, 9/37, 6/36, 5/39, 3/38). The
   report's grand total equals the 12-month signal of the RUNBOOK (73 Yes and 451 No on
   2026-10-26). For one partner, named in the Result, each of the six months in the report equals
   the one-partner query:
   `SELECT Period__c, Recruit_any_new_mentors_last_month__c, COUNT(Id) FROM DHIS2__c WHERE Period__c = LAST_N_MONTHS:6 AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') AND Recruit_any_new_mentors_last_month__c != null AND Account__r.Name = '<partner>' GROUP BY Period__c, Recruit_any_new_mentors_last_month__c`.
   The test-record check is over the same 12 months, where a test record answers the question:
   `SELECT COUNT(Id) FROM DHIS2__c WHERE Period__c = LAST_N_MONTHS:12 AND (Account__c = null OR Account__r.Name LIKE '%test%') AND Recruit_any_new_mentors_last_month__c != null`
   is 1 on 2026-10-26, and the report's total equals the count with the rule, not the one
   without; a 0 there on the day means the check proves nothing, and the Result says so. The
   counts go in the Result.
8. In `glow/sf_keep_list.csv`, item 12's id becomes the new report's id, and its `label_today`
   and `label_target` become "Partners that recruited new mentors"; the keep-list test of the
   ticket (`test/sf_keep_list_test.py::test_item_12_has_its_new_report`) lands with it, and
   `make check` passes.

## Rollback

- Restore the dashboard D4 from its copy in Decommissioned, made with the tag #80 before the
  deploy: open the copy, then Save As or move it back into "GLOW Monthly Dashboards" (RUNBOOK
  "Decommissioned"). A copy put back keeps the copy's Id, so D4's Id changes that way.
- Or redeploy D4 from this change's retrieve `data/sf_new_mentors_2026-10-26/before/`, and only
  while a fresh retrieve of D4 equals `after/`. That keeps D4's Id.
- The scope is the manifest `data/sf_new_mentors_2026-10-26/rollback/package.xml`, written by
  script, with D4 as its one member, `GLOW_Monthly_Dashboards/fgMcyANlcTvERilgPVySaXCChURVlO`.
  The fresh retrieve takes the same manifest, into a new folder `fresh_<date>/` (UTC date) in
  the same work folder, made as in the Rollout; within it:
  `sf project retrieve start -o glow -x ../rollback/package.xml`. It never goes into `before/`,
  the source of this redeploy, which it would overwrite. Only while that fresh retrieve equals
  `after/`, the deploy runs within `before/` with the manifest: first the check-only
  `sf project deploy start --dry-run -o glow -x ../rollback/package.xml`, then on Ryan's go the
  same without `--dry-run`. Nothing else in `before/` goes back: item 15's report there is the
  template, untouched by this change (DECISIONS 2026-10-16: only the components the change
  touched).
- When the fresh retrieve and `after/` differ, someone has changed the dashboard since the deploy
  (#78's step 9, item 16, among them): the rollback then starts from that fresh retrieve, by the
  epic's ritual.
- Once D4 is back, the new report, "Partners that recruited new mentors", which D4 no longer
  uses, moves to Decommissioned by a one-row move plan written by script
  (`kind,id,to_folder,new_label` with `report,<its id>,Decommissioned,`): the dry run
  `python3 tools/sf_report_folders.py move --vpn-off --dir data/sf_new_mentors_2026-10-26 --plan <that plan>`,
  then on Ryan's go the same with `--apply`. Item 12's row in `glow/sf_keep_list.csv` goes back
  to `new`.
- A rollback never deploys an older build, never a `build/` and never another change's retrieve
  (DECISIONS 2026-10-16).
- The copies stay in Decommissioned, and nothing is deleted.

## Result

Offline and read-only, 2026-10-26 (a headless session, VPN off for the reads): the retrieve into
`before/`, the build in `build/` (the report and the dashboard, 2 files; the diff in
`evidence/build_vs_before.diff`), the rollback manifest `rollback/package.xml` (1 member, written
by script) and the read-only counts of step 7 (`evidence/soql_signal_2026-10-26.txt`).

The Rollout is pending: steps 1-8 run in an interactive session with Ryan, on his go. The
check-only, the deploy, the read-back, the copy's id, the report's id and the SOQL check's
counts go here then.
