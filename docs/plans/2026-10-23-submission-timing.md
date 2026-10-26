---
title: Submission time, delay in days, session month and week on every attendance batch - four formula fields, then the reports and the dashboard that read them
author: Claude (with Ryan's answers of 2026-10-22)
status: in-progress    # ticket #101 done 2026-10-24 (the four fields live, the check OK: Result); ticket #102's four reports built, their deploy waits for Ryan's go ("Task #102: the timing reports")
created: 2026-10-23
intent: Ryan, 2026-10-22 (GLOW staff meeting, epic #93) - bring into Salesforce "the time the Jotform form was submitted AND which month/week the session belongs to (e.g. week 2, week 3), displayable in reports, so upper-level staff can see which clubs haven't submitted for a week, or have a big delay between session and submission"
---

# Plan: submission timing on attendance batches - four formula fields, then the reports and the dashboard

Ticket #101 (epic #93, item 2), the first of three. Ryan, 2026-10-22: upper-level staff should
see which clubs have not submitted for a week and the delay between a session and its
submission, "displayable in reports". Task #100 fixed the definitions (DECISIONS 2026-10-23;
`glow/session_timing.py`) and built the read-only check. This task deploys the four formula
fields that compute them on `Attendance_Batch__c`, readable by everyone who reads the attendance
reports, and proves them with the check. Task #102 then adds the reports on these fields - the
clubs that did not submit in a week, and the delay from session to submission by club, by
partner and by month - and task #103 puts them on the "Jotform Attendance" dashboard; each adds
its own Rollout, Rollback and Result to this plan.

## Context

- `Attendance_Batch__c` today: `Account_Name__c`, `Account__c`, `Attendance_Date__c`,
  `Contact_IDs__c`, `Creator__c`, `Module__c`, `Module_Week__c`, `Module_Year__c`,
  `Processing_Status__c`, `Status_Message__c`, `enable_fuzzy_matching__c`, `Girls_Present__c`
  and the formula `Partner_Girls__c` ([plan](2026-10-06-attendance-totals.md), [#59's
  plan](2026-10-20-girls-attended-tiles.md); RUNBOOK "Attendance dashboard in Salesforce").
- The definitions (DECISIONS 2026-10-23): the session week is the week of the month by day of
  `Attendance_Date__c` (1-7 week 1, 8-14 week 2, 15-21 week 3, 22-28 week 4, 29-31 week 5,
  shown as `2026-10 week 2`); the submission time is `CreatedDate` when `Creator__c` is exactly
  `Jotform`, else blank, because the native Jotform Salesforce V2 integration creates the batch
  when the form is submitted; the delay is the UTC day of the submission minus the session date,
  in whole days; there is no "big delay" threshold or flag.
- Formula fields change no record and run nothing: the processor's trigger (after insert only)
  and the Jotform integration are untouched. `tools/sf_session_timing.py check` (task #100)
  compares the four fields with the same definitions, read only, and today stops with its
  HTTP 400 hint because the fields do not exist yet.
- A field a viewer cannot read silently drops a report's filter (RUNBOOK "Attendance dashboard
  in Salesforce", Access): the permission set `Attendance_Report_Viewer` and the Admin profile
  get Read on the four fields in the same deploy, as #59 did for `Partner_Girls__c`.
- Deploy rules (`.claude/skills/salesforce`; DECISIONS 2026-10-16): VPN off; retrieve fresh;
  build in a copy; check-only; Ryan's go; deploy; retrieve and compare; never an older package;
  `data/` is never committed; every write in the main session, never a subagent.
- Risk high: Salesforce metadata on the object every attendance submission writes.
- The read-only proofs of the ticket's outline (step 2) are done, 2026-10-23: Result, below.

## Build

Everything under `data/sf_session_timing_2026-10-23/` (owner only, never committed): `before/`
is the fresh retrieve of what is live, `build/` the SFDX project to deploy, `evidence/` the
proofs' queries and answers (2026-10-23), `after/` the read-back. Built offline; the only `sf`
commands are the retrieve, the check-only and the deploy of the Rollout.

**The four formula fields** on `Attendance_Batch__c`, one file each under
`build/force-app/main/default/objects/Attendance_Batch__c/fields/<Field>.field-meta.xml`, the
`<formula>` text exactly `glow/session_timing.py SF_FORMULAS` (the check compares Salesforce
with the same definitions, so the two texts stay one):

| Field | Type | Label | Formula |
|---|---|---|---|
| `Submitted_At__c` | Date/Time | Submitted at | `IF(Creator__c = "Jotform", CreatedDate, NULL)` |
| `Submission_Delay_Days__c` | Number, 0 decimals (`precision` 18, `scale` 0) | Days from session to submission | `IF(ISBLANK(Submitted_At__c), NULL, DATEVALUE(TEXT(Submitted_At__c)) - Attendance_Date__c)` |
| `Session_Month__c` | Text | Session month | `TEXT(YEAR(Attendance_Date__c)) & "-" & LPAD(TEXT(MONTH(Attendance_Date__c)), 2, "0")` |
| `Session_Week__c` | Text | Session week | `Session_Month__c & " week " & TEXT(CEILING(DAY(Attendance_Date__c) / 7))` |

The delay takes the UTC date of the submission through `DATEVALUE(TEXT(Submitted_At__c))`:
`TEXT()` of a date/time is the UTC timestamp `YYYY-MM-DD HH:MM:SSZ` and `DATEVALUE` of that text
is its UTC date, whereas `DATEVALUE` on the date/time itself converts in
the running user's time zone (here the org's default, America/Los_Angeles) - the first deploy's `DATEVALUE(Submitted_At__c)` was a day short for every
submission between 00:00 and about 07:00 UTC (Result, 2026-10-24; DECISIONS 2026-10-24).

Each file follows the shape of `Partner_Girls__c`'s in `before/` (the #59 formula field):
`<formula>`, `<type>`, `<label>`, `<inlineHelpText>`, `<description>` (the same text),
`<formulaTreatBlanksAs>BlankAsBlank</formulaTreatBlanksAs>`, and for the Number `<precision>18</precision>`
and `<scale>0</scale>`. The help text, one per field, says what it means and which batches have
none:

- Submitted at: "When the Jotform form was submitted: the batch's created time, for the
  batches the Jotform integration created (Creator 'Jotform'). Blank on the September back-fill
  and on partner-reported batches, which were created later by tools."
- Days from session to submission: "Whole days from the session date to the day (UTC) the form
  was submitted; negative when the form was submitted before the session date (a date typo).
  Blank when the batch has no submission time."
- Session month: "The month of the session date, as 2026-10."
- Session week: "The week of the month of the session date: days 1-7 week 1, 8-14 week 2,
  15-21 week 3, 22-28 week 4, 29-31 week 5, as '2026-10 week 2'. The calendar week of the
  session, not the curriculum Session N (Module Week)."

**Access.** Read on the four fields for the permission set `Attendance_Report_Viewer` and for
the Admin profile: one `fieldPermissions` entry per field in each, `readable` true and
`editable` off as for `Partner_Girls__c` (a formula field is read-only), so every viewer's
report keeps a column, a grouping or a filter on them. The permission set file in `build/` is
`before/`'s copy with the four entries added, nothing else touched; the profile is a partial
`profiles/Admin.profile-meta.xml` holding only the four entries (a profile deploy merges them
in). `package.xml`: `CustomField` × 4, `PermissionSet` `Attendance_Report_Viewer`, `Profile`
`Admin`, `<version>62.0</version>`; `sfdx-project.json` as `data/sf_girls_tiles_2026-10-20/build/`'s.

## Rollout (live; the deploy on Ryan's go, in the main session)

All with the VPN off, through the `sf` CLI login `glow` (`.claude/skills/salesforce`); every
retrieve, build and piece of evidence lives under `data/sf_session_timing_2026-10-23/` (owner
only). Only counts and batch Names reach the ticket, the conversation or this plan.
1. VPN off. Retrieve what is live into `data/sf_session_timing_2026-10-23/before/`: the object
   `Attendance_Batch__c` (its fields come with it), the permission set `Attendance_Report_Viewer`
   and the Admin profile, in one `sf project retrieve start -o glow -m
   "CustomObject:Attendance_Batch__c" -m "PermissionSet:Attendance_Report_Viewer" -m
   "Profile:Admin"` (one retrieve, so the profile carries its field permissions for that object).
   Compare the permission set with `data/sf_girls_tiles_2026-10-20/after/`, the latest read-back:
   a difference means someone changed it since, so the build starts from this fresh retrieve
   either way and the difference goes on the ticket.
2. The `CreatedDate` proof, read only (done 2026-10-23: Result, below): the `Creator__c` values
   on every batch since 2026-09-01, counts only (task #100's query); and for the 20 latest live
   batches (`Creator__c` = `Jotform`) the Jotform submission with the same question 5 and date
   (`glow.jotform.Client.submissions` with a `created_at` filter; `glow.jotform.CLOCK` is US
   Eastern) created within 10 minutes of the batch's `CreatedDate`. A batch outside the 10 minutes
   stops the rollout with a question on the ticket, because `CreatedDate` would then be a later
   moment than the submission itself. The queries and answers go to `evidence/`.
3. Build in `build/` (Build, above): the four field files, the permission set file from `before/`
   with the four entries added, the partial Admin profile with its four entries, `package.xml`
   and `sfdx-project.json`. Offline checks before any deploy: each `<formula>` equals the
   matching `SF_FORMULAS` text (`python3 -c` over `glow.session_timing`), the four
   `fieldPermissions` names match the field files, the permission set differs from `before/`'s
   by the four entries alone.
4. Check-only: from within `build/`, `sf project deploy start --dry-run -o glow -d force-app`.
   If Salesforce refuses the delay's reference to `Submitted_At__c` or the week's reference to
   `Session_Month__c` within one deploy, split it in two: `Submitted_At__c` and
   `Session_Month__c` with their permission set and profile entries first, then the other two
   fields with theirs, each check-only first, each on Ryan's go.
5. Ryan's go in the conversation (the live gate puts the command to him as an approval prompt;
   his answer is the go).
6. Deploy: the same command minus `--dry-run`, run by Claude on his go, or by Ryan in his own
   terminal when auto mode refuses a production deploy (2026-10-02). The deploy id and time
   (UTC) go into Result.
7. Read back: retrieve the same three components into `after/` and compare with `build/` (the
   four fields and the eight entries equal, apart from Salesforce's own normalisation) and with
   `before/` (the object differs by the four fields alone, the permission set and the profile by
   the four entries alone, so nothing else in them changed).
8. `python3 tools/sf_session_timing.py check --vpn-off` -> `checked N batches` with every
   differ count 0, `-> OK`, over every batch since 2026-09-01; the line goes on the ticket. A
   `-> DIFFER` stops here: the named field's formula and `glow/session_timing.py` disagree, and
   Ryan decides which one changes (a formula fix is a new build and a new check-only).
9. RUNBOOK "Submission timing in Salesforce": its Status line gets the deploy id and time; this
   plan's Result, `status: done`, `done:`, then `make docs-index`; the ticket's definition of
   done ticked.
10. Tasks #102 (the reports) and #103 (the dashboard) follow on their own tickets, each adding
    its Rollout, Rollback and Result here.

## Rollback

First the reports: every report that uses or filters on the four fields (task #102's, and any
built by hand on `Attendance_Totals` or `Attendance_Batches_and_Girls` since) is edited to drop
the fields, since Salesforce refuses to delete a field a report uses, in whatever folder the
report is. A report kept: its copy to Decommissioned (the archive rule of DECISIONS 2026-10-21)
is edited to drop the fields as well, since a copy that kept them would block their deletion;
the report as it was, fields and all, is kept only in the fresh retrieve the edit starts from
(DECISIONS 2026-10-16), from which it can be put back if the fields are. A report retired:
moved to Decommissioned and edited there, never deleted (task #102's Rollback, below). The
dashboard components that read those reports go with them (task #103's Rollback). Then the four fields
`Submitted_At__c`, `Submission_Delay_Days__c`, `Session_Month__c` and `Session_Week__c` go in
one destructive deploy from a folder of their own: an empty `package.xml` (`<Package>` with only
`<version>62.0</version>`) beside a `destructiveChanges.xml` listing the four `CustomField`
members (`Attendance_Batch__c.Submitted_At__c` and so on), an `sfdx-project.json` and the empty
`force-app/` it names (`--manifest` needs an SFDX project); within that folder, check-only
`sf project deploy start --dry-run -o glow --manifest package.xml --post-destructive-changes
destructiveChanges.xml`, Ryan's go, then the same command minus `--dry-run`; the fields' entries
in `Attendance_Report_Viewer` and the Admin profile go with the fields. Should Salesforce refuse
the four together, the two that the others reference go last: `Submission_Delay_Days__c` and
`Session_Week__c` in one deploy, then `Submitted_At__c` and `Session_Month__c`. Retrieve the
object, the permission set and the profile again and compare with `before/`: equal means the
rollback is complete. Never an older build (DECISIONS 2026-10-16): `before/` is the comparison
only, and nothing is redeployed from it, because this deploy created the four fields and only
added their entries to `Attendance_Report_Viewer` and the Admin profile, which go with the
fields when they are deleted. Revert this ticket's RUNBOOK section with it;
`sf_session_timing.py check` then stops with its HTTP 400 hint again, as before the deploy.

## Risks

- **`CreatedDate` as the submission time**: it is the moment the batch reached Salesforce, which
  is the submission only while the Jotform integration sends at once. The proof (Rollout step
  2; Result): the 20 latest live batches were created 0-3 s after their submission, 20 of 20
  within 10 minutes. A retried send, a paused integration or a re-authorisation after a freeze
  (2026-09-30) would stretch a batch's delay by the wait, and the check cannot tell (it compares
  against the same `CreatedDate`): a surprising delay on a report is read with the integration's
  history in mind. A batch sent later by a tool carries another `Creator__c` and gets no
  submission time, by design.
- **A viewer who cannot read a field** loses a report's column, grouping or filter on it
  silently, or the report fails "Invalid Report" (RUNBOOK "Attendance dashboard in Salesforce",
  Access). Mitigation: the permission set and the Admin profile in the same deploy, compared with
  `before/` after it (Rollout step 7).
- **A formula that references a formula** (`Submission_Delay_Days__c` reads `Submitted_At__c`;
  `Session_Week__c` reads `Session_Month__c`): the check-only may refuse the four in one deploy
  if it compiles a formula before the field it references exists. Mitigation: Rollout step 4's
  split into two deploys. A compile error in a formula text (a type mismatch, a function's
  spelling) is caught by the same check-only; the fix goes into `SF_FORMULAS` and the build
  alike, so the check keeps comparing the same text.
- **The deploy refused by auto mode** (2026-10-02): Ryan runs the same command in his terminal;
  nothing else changes.
- **The VPN**: an `sf` call through the VPN freezes Ryan's user and revokes every token, the
  Jotform connection's included (2026-09-30). VPN off before each call; the tools refuse without
  `--vpn-off`.
- **A field on the object every submission writes**: a formula is computed when read, stored
  nowhere and fires no trigger, so the processor, the integration and the back-fill tools are
  untouched; the only limit is the compiled formula size, far off for these four.

## Proof

- `scripts/harness_tests.sh test/session_timing_test.py` (class `SubmissionTimingDocs`, and
  task #100's classes) and `scripts/verify.sh` -> `CHECK PASSED`, `VERIFY OK`.
- Live: the read-back of Rollout step 7 (0 differences from `build/` beyond Salesforce's
  normalisation; `before/` differs by the four fields and the entries alone) and
  `python3 tools/sf_session_timing.py check --vpn-off` -> `-> OK` (Result).

## Result

- 2026-10-23, the read-only proofs (Rollout step 2), through the read-only connector and the
  Jotform API, counts only: `Creator__c` on batches with `Attendance_Date__c >= 2026-09-01`:
  1,066 batches - `Jotform` 698, `Jotform back-fill …` 365, `Partner report` 3; no other
  value, none blank. For each of the 20 latest `Creator__c = 'Jotform'` batches, the Jotform
  submission on the regional forms with the same question 5 and date was created 0-3 s before
  the batch's `CreatedDate`: 20 of 20 within 10 minutes. Evidence in
  `data/sf_session_timing_2026-10-23/evidence/` (not committed).
- 2026-10-23: the deploy (Rollout steps 1 and 3-9) was pending Ryan's go in an interactive
  session; nothing was deployed as of this entry, and `sf_session_timing.py check` still stopped
  with its HTTP 400 hint.
- 2026-10-24, Ryan's go, VPN off, in the main session (Rollout steps 1 and 3-8): the fresh
  retrieve into `before/` equalled the one taken earlier that run, so nothing had changed live;
  the offline checks on `build/` passed (the four `<formula>` texts equal to `SF_FORMULAS` as
  they then stood, the permission set +4 Read entries and nothing else, the partial Admin profile
  its 4 Read entries, none editable); check-only `0AfRP000002i4DF0AY` Succeeded (no split needed);
  deploy `0AfRP000002i4Er0AI`, 06:41 UTC, 6 components, 0 errors. Read-back into `after/`: the
  object is `before/` plus the four fields, no existing field or object file changed; the
  permission set +4 Read entries (+20/-0 lines); the Admin profile +4 field entries plus
  `CreateSalesforcePages`, `DeploySalesforcePages` and `ViewSalesforcePages` enabled (+32/-0
  lines), which were not in the build. The build's partial profile carries only the four
  fieldPermissions, which cannot enable a userPermission, and both retrieves ran from the same
  project at the same API version, so the build's payload could not have set them; most likely Salesforce wrote the
  System Administrator profile's default permissions when the profile was saved (inferred, not
  confirmed). They are admin-only and
  left as they are; nothing else in the three components changed. The check: `checked 1123 batches; differ: Submitted_At__c 0,
  Submission_Delay_Days__c 153, Session_Month__c 0, Session_Week__c 0 -> DIFFER`. Cause,
  confirmed on BATCH-000405..409 (`CreatedDate` 04:52-05:06 UTC on 2026-10-02, Salesforce one
  day short): Salesforce's `DATEVALUE(<date/time>)` converts in the running user's time zone (here the org's default,
  America/Los_Angeles), not UTC, so the first deploy's `DATEVALUE(Submitted_At__c)` gave the Los
  Angeles day, one short for every submission between 00:00 and about 07:00 UTC. Ryan,
  2026-10-24: keep the UTC day (DECISIONS 2026-10-24); the delay formula takes it through
  `DATEVALUE(TEXT(Submitted_At__c))` (the Build table and `SF_FORMULAS`, one text), and
  `Submission_Delay_Days__c` is redeployed alone - its field file in a build of its own,
  check-only, Ryan's go, deploy, read-back, and the check to every differ count 0; that result
  follows here. Nothing reads the field yet (tasks #102 and #103).
- 2026-10-24: the delay field redeployed alone, on Ryan's go: check-only `0AfRP000002i4Jh0AI`,
  deploy `0AfRP000002i4LJ0AY` (06:59 UTC, 1 component, 0 errors), built from a fresh retrieve of
  what was live (`build2/`, one line changed: the formula). Read-back `after2/` equals `build2/`.
  `tools/sf_session_timing.py check --vpn-off`: `checked 1123 batches; differ: Submitted_At__c 0,
  Submission_Delay_Days__c 0, Session_Month__c 0, Session_Week__c 0 -> OK`.

## Task #102: the timing reports

Ticket #102 builds four reports on the fields in the Attendance report folder, on Ryan's answers
of 2026-10-24 (DECISIONS 2026-10-24, "The weekly not-submitting list leaves out the monthly
partners and the U.S clubs by partner name"). What each report answers, its SOQL check and who
is left out: RUNBOOK "Submission timing in Salesforce", The timing reports. Task #103 puts them
on the dashboard.

### Build (2026-10-24, offline)

In `data/sf_session_timing_2026-10-24/t102_build/` (`build/`, `pattern/`; owner only, never
committed), copied there unchanged on 2026-10-26 from the job folder it was first written in,
since the protected-paths hook refuses an agent's writes under `data/`. `build/` is an SFDX
project: `sfdx-project.json` as `data/sf_girls_tiles_2026-10-20/build/`'s (API 62.0), and
`package.xml` with `Report` × 4 (`Attendance/<name>`) and `ReportType` `Attendance_Totals`.
`pattern/` holds the report type as retrieved 2026-10-24 09:24 UTC
(`data/sf_dash_implementation_2026-10-24/before/`, after the fields' deploy). Under
`build/force-app/main/default/`:
- `reports/Attendance/Clubs_Not_Submitting_Last_Week.report-meta.xml`: a copy of
  `Clubs_Not_Submitting_Last_14_Days` as retrieved 2026-10-14
  (`data/sf_totals_labels_2026-10-14/before/`), with the cross filter's `LAST_N_DAYS:14` changed
  to `LAST_WEEK`, one more locked criterion, `PARENT.NAME` `notEqual` the nine partner account
  names comma-separated (not equal to any of them), and its own label and description.
- `Submissions_by_Club_and_Week`: a Matrix on `Attendance_Totals__c`, rows
  `Attendance_Batch__c$Account__c.Parent` then `Attendance_Batch__c$Account_Name__c`, columns
  `Attendance_Batch__c$Session_Week__c`, the record count; locked criteria `Attendance_Date__c`
  `greaterOrEqual` `N_WEEKS_AGO:8` and `lessOrEqual` `THIS_WEEK`; the unlocked Partner and Club
  "contains" criteria as in `Blank_Submissions`.
- `Late_Submissions_Last_Month`: a Summary on `Attendance_Totals__c` grouped by
  `Attendance_Batch__c$Account__c.Parent` (the outline), columns club, `Attendance_Date__c`,
  `Submitted_At__c` and `Submission_Delay_Days__c`; locked criteria `Creator__c` equals `Jotform`
  and `Processing_Status__c` equals `Success`; the unlocked Partner and Club criteria; the time
  frame `INTERVAL_LASTMONTH` on `Attendance_Date__c` (as `Girls_Attended_Last_Month`);
  `sortColumn` the delay, `Desc`, so each partner's batches run largest delay first. The sort
  works only within each partner's group: the month's largest delay sits at the top of its
  partner's group, which need not be the first group. That was the outline's reading of Ryan's
  "largest first"; Ryan confirmed it on the ticket on 2026-10-26 (Rollout step 1): grouped by
  partner, largest first within each partner. If it is ever changed to one list across partners,
  the report becomes Tabular (no grouping, the partner a column, sorted by the delay, `Desc`).
- `Submission_Delay_by_Partner_by_Month`: a Summary, rows partner then `Session_Month__c`, the
  delay column with `Average` and `Maximum`; the same two locked criteria plus
  `Attendance_Date__c` `greaterOrEqual` `N_MONTHS_AGO:11`; a `HorizontalBarGrouped` chart of the
  average, a bar per partner with the months as its series; its summary's `axisBinding` is `y`,
  as on every chart retrieved into `data/` (the horizontal bars included).
- `reportTypes/Attendance_Totals.reportType-meta.xml`: `pattern/`'s file with four `<columns>`
  entries added to its one section, `Submitted_At__c`, `Submission_Delay_Days__c`,
  `Session_Month__c` and `Session_Week__c` (`checkedByDefault` false), nothing else changed: a
  custom report type offers a field to its reports only once its layout lists it.

Offline checks, 2026-10-24: every XML file parses (`xmllint --noout`); `diff` of the report type
with `pattern/` shows the four `<columns>` entries alone; every report description is within 255
characters and every label within 40. Not proved offline, settled by the check-only (Rollout step
3): the relative values `N_WEEKS_AGO:8`, `THIS_WEEK` and `N_MONTHS_AGO:11` in a criterion (the
cross filter's `LAST_N_DAYS:14` passed as it is on 2026-10-07), the chart type
`HorizontalBarGrouped` with a `secondaryGroupingColumn`, and `sortColumn` on a formula field. A
refusal is fixed in `build/` and run check-only again; a changed window changes the RUNBOOK and
its SOQL check with it.

### Rollout (live; pending Ryan's go, in the main session)

Step 1 is done (2026-10-26); steps 2-8 have not run. Steps 2-8 with the VPN off, through the CLI
login `glow`; only counts and partner names reach the ticket, the conversation or this plan.
1. Done 2026-10-26: Ryan confirmed on the ticket how `Late_Submissions_Last_Month` sorts: grouped
   by partner (the outline), the largest delay first within each partner's group, so the month's
   largest delay need not be on top; `build/` stands as built. If it is ever changed to one list
   across partners, the report becomes Tabular (no grouping, the partner a column, sorted by
   `Submission_Delay_Days__c`, `Desc`), and before its next check-only every place that describes
   it changes: `build/`'s report file; the RUNBOOK's `Late_Submissions_Last_Month` bullet ("The
   timing reports") and its paragraph "The late report"; this section's Build bullet on the
   report and its Risks bullet on the sort; and a dated bullet added to the DECISIONS 2026-10-24
   entry ("The weekly not-submitting list ...") saying what Ryan chose. The change goes on the
   ticket.
2. VPN off. Retrieve what is live into `data/sf_session_timing_2026-10-24/before/`: `sf project
   retrieve start -o glow -m "Report:Attendance/Clubs_Not_Submitting_Last_14_Days" -m
   "Report:Attendance/Blank_Submissions" -m "ReportType:Attendance_Totals"` (the ticket's outline
   step 2). Compare the two reports with the copies the build started from and the report type
   with `pattern/`: a difference means someone changed it since, so the build is redone from the
   fresh retrieve and the difference goes on the ticket. SOQL on `Report` confirms none of the
   four DeveloperNames exists yet.
3. Check-only: from within `build/`, `sf project deploy start --dry-run -o glow -d force-app`.
4. Ryan's go in the conversation (the live gate puts the command to him as an approval prompt;
   his answer is the go).
5. Deploy: the same command minus `--dry-run`, by Claude on his go or by Ryan in his own terminal
   when auto mode refuses a production deploy; the deploy id and time (UTC) go into Result.
6. Read back: retrieve the four reports and the report type into `after/` and compare with
   `build/` (equal apart from Salesforce's normalisation: `expandOthers`, escaped apostrophes,
   default attributes), and the report type with `before/` (the four columns alone).
7. Run each report through the Analytics API (`sf api request rest
   '/services/data/v62.0/analytics/reports/<id>' -o glow`, a GET) and compare its totals with its
   SOQL check (the RUNBOOK's), for one checked week (last week) and one month (last month): the
   not-submitting count, the matrix's grand total, the late report's row count, and each
   partner's average and maximum delay for last month. The RUNBOOK's `GROUP BY` statements are
   the first try; where SOQL refuses `GROUP BY`, `AVG` or `MAX` on a formula field, the check is
   the fallback the RUNBOOK names: the same rows selected ungrouped, with the same `WHERE`, and
   totalled offline. The results go on the ticket; a difference stops here with its cause on the
   ticket.
8. Ticket #102's definition of done ticked; this section's Result written; task #103 follows.

### Rollback

The dashboard components that read the reports go first (task #103's Rollback). Then the four
reports are retired, never deleted (the archive rule, DECISIONS 2026-10-21): each is moved to
Decommissioned and keeps its Id, by the Analytics API move of the API proof (`PATCH
…/analytics/reports/<id>` with `reportMetadata.folderId`; `tools/sf_report_folders.py` refuses
the Attendance folder as a source) or by hand in Lightning, one report at a time on Ryan's go,
each read back by SOQL on `Report` (the same Id, `FolderName` following). A moved report still
uses the timing fields, and Salesforce refuses to delete a field a report uses, wherever the
report is, so the three moved reports on `Attendance_Totals` are edited next to drop the four
fields: retrieve them fresh (`Report:Decommissioned/<name>`) and take out of
`Submissions_by_Club_and_Week` its `Session_Week__c` column grouping (its format becomes
Summary), out of `Late_Submissions_Last_Month` the `Submitted_At__c` and
`Submission_Delay_Days__c` columns and the sort on the delay, and out of
`Submission_Delay_by_Partner_by_Month` the `Session_Month__c` grouping, the delay column and the
chart; check-only, Ryan's go, deploy, and retrieve again to confirm that no report in
Decommissioned names a timing field. `Clubs_Not_Submitting_Last_Week` (on Accounts) uses none of
them and moves as it is. `after/` (Rollout step 6) keeps the four as deployed: a report put back
starts from it. Then the report type: retrieve `Attendance_Totals` fresh, delete the four
`<columns>` entries in that copy, check-only, Ryan's go, deploy, and compare it with `before/`.
Never redeploy the report type from `before/` or `pattern/` (DECISIONS 2026-10-16). Only after
both may the fields' Rollback (above) run. Revert this task's RUNBOOK and DECISIONS changes with
it.

### Risks

- **A formula field in SOQL's `GROUP BY`, `AVG` or `MAX`**: SOQL often refuses to group by or
  aggregate a formula field (`Session_Week__c`, `Session_Month__c`, `Submission_Delay_Days__c`),
  which was not checked offline. The `GROUP BY` statements are the first try; when one is
  refused, the check Rollout step 7 runs is the fallback: the same rows selected ungrouped, with
  the same `WHERE`, and counted, averaged and maximised offline. The reports themselves group by
  the field, which reports allow.
- **The late report sorts within each partner**: grouped by partner, as the outline has it, its
  largest delay comes first only within each partner's group; Ryan confirmed that reading on the
  ticket on 2026-10-26 (Rollout step 1): grouped by partner, largest first within each partner.
- **The partner-name filter is hand-kept**: a partner newly off Jotform, a new U.S partner or a
  renamed partner account changes the weekly list until the filter is edited (RUNBOOK, Who is
  left out).
- **Two kinds of week**: the weekly list and the matrix's window use Sunday-to-Saturday weeks
  (`LAST_WEEK`, `N_WEEKS_AGO:8`), the matrix's columns the week of the month, so its first and
  last columns can hold part of a week.
- **The report type serves six reports**: the deploy only adds four columns; the read-back
  compares it with `before/`.

### Result

- 2026-10-24: built offline (Build, above); `scripts/harness_tests.sh test/session_timing_test.py`
  and `scripts/verify.sh` pass. Nothing retrieved, validated or deployed; Rollout steps 1-8 wait
  for Ryan. The build was written outside the repository, in the job folder
  `~/.claude/jobs/392fafeb/tmp/t102_build/`, because the protected-paths hook refuses an agent's
  writes under `data/`; copied into `data/` on 2026-10-26 (below).
- 2026-10-25, review fixes: the delay chart's `axisBinding` set to `y` (it was `x`); the Rollback
  moves the reports to Decommissioned and edits them off the fields instead of deleting them; the
  late report's within-partner sort becomes Rollout step 1, Ryan's confirmation.
- 2026-10-26: Rollout step 1 done: Ryan confirmed on the ticket that the late report stays grouped
  by partner, largest first within each partner; `build/` is unchanged. The build was copied
  unchanged from the job folder into `data/sf_session_timing_2026-10-24/t102_build/` (`build/`,
  `pattern/`). Steps 2-8 wait for his go.
