---
title: Attendance dashboard in Salesforce - charts from the data already there
author: Claude (with Ryan)
status: done             # deployed 2026-10-02 03:46 UTC and fix1 2026-10-06 09:29 UTC, both by Ryan; open: BACKLOG 58-61
done: 2026-10-02
backlog: 58, 59, 60, 61
created: 2026-10-02
intent: none - Ryan's request of 2026-10-02 ("upgrade it now to use charts instead of line by line";
  then "start with basic reporting visuals ... using the info we already have")
---

# Plan: Jotform attendance dashboard (charts instead of rows), existing data only

## Context
The test report "Jotform Monthly Attendance (test)" (folder Attendance, deployed 2026-10-02) works;
Ryan checked it. It lists one row per girl per session. Leadership needs charts: one number for the
girls who attended in the month, and attendance by week and by month, with the report's filters
(partner, club, girl).

Ryan's scope (2026-10-02): **basic visuals from the information Salesforce already holds** -
no new fields, no new tool, nothing more on the forms. The "% of maximum attendance possible" line
needs an enrolled count Salesforce does not have (every `Attendance__c` row is a present girl;
4,863 rows, no absence rows, no enrolled count anywhere), so it is **not** in this round; its design
is kept under "Later".

## What Salesforce already gives (read 2026-10-02, read only)
The existing report type `Accounts_Contacts_Attendance` (Account → Contacts → Attendances, used by
the test report) carries everything needed:
- club = `Account$Name` and partner = `Account$Parent`;
- girl = `Account.Contacts$Id`, counted with a unique count, never shown;
- session = `Attendance_Batch__c`, counted the same way;
- `Module__c`, `Attendance_Date__c` and `Creator__c`.

Region is not in it: region sits on the partner Account, and the report type has no lookup to the
partner's fields. So region charts are not in this round. Partners: 49 (a dashboard filter allows
50 values); clubs: 364.

## What gets built (metadata only, folder Attendance)

### Reports
All on `Accounts_Contacts_Attendance`, with the test report's filters:
- locked: Account record type = Club; Creator = AttendanceBatchTrigger;
- unlocked: Partner contains, Club contains, Girl contains.

| Report | Time frame | Grouping | Measures |
|---|---|---|---|
| Jotform Attendance by Week | since 2026-09-01 | date by week | girls (unique), sessions (unique), clubs (unique), attendances (rows) |
| Jotform Attendance by Month | since 2026-09-01 | date by month | girls (unique), attendances |
| Jotform Attendance Last Month | last month | partner | girls, sessions, clubs (unique), attendances |
| Jotform Attendance This Month | this month | partner | girls, sessions, clubs (unique), attendances |
| Jotform Sessions by Module Last Month | last month | module | sessions (unique) |
| Clubs Without Attendance Last Month | last month | partner | clubs (row count) |

"Clubs Without Attendance Last Month" is a standard Accounts report:
- record type Club;
- cross filter "Accounts without Attendances (`Attendances__r`) where date = last month";
- unlocked Partner contains and Club contains.

**The test report itself**:
- gets a chart (attendances and girls by partner);
- its detail rows are collapsed, so it shows summary rows per partner and club instead of one line
  per girl;
- every filter stays;
- the "before" copy is `data/sf_monthly_report_2026-09-30/test_report/`.

### Dashboard "Jotform Attendance (test)" (dashboard folder Attendance)
**Row 1, four numbers:**
- girls who attended last month;
- girls who attended this month so far;
- sessions held last month;
- clubs that sent attendance last month.

**Row 2:**
- line: girls attending per week since 1 September (wide);
- column: girls and attendances by month.

**Row 3:**
- line: sessions held per week;
- line: clubs reporting per week.

**Row 4:**
- bar: girls reached by partner, last month;
- bar: sessions by module, last month.

**Row 5:**
- number and table: clubs with no attendance last month, by partner.

**Filters and running user:**
- Dashboard filter: **Partner** (49 values), on every component.
- Club and girl cannot be dashboard filters, because Salesforce allows 50 values per filter. They
  are one click away: each chart opens its report, and the Club and Girl filters there drive that
  report's chart.
- Running user: Ryan, as on the pilot "Attendance" dashboard, so viewers see the whole organisation.

Nothing existing changes except the test report. The pilot reports and the pilot dashboard, the
processor, the forms and the Jotform mapping are untouched.

## Order of work
1. Commit this plan as `docs/plans/2026-10-02-attendance-dashboard.md`.
2. Write the metadata in a scratch SFDX project (`scratchpad/glowrep`, where the current test report
   and pilot dashboard were retrieved read only).
3. Validate with `sf project deploy validate`: check only, changes nothing, no Apex so no tests run.
   Fix until it is clean.
4. **Deploy** to production. Approving this plan is Ryan's go (his "upgrade it now").
5. **Read back**, read only:
   - Run each report through the Analytics REST API.
   - Compare its numbers with SOQL. September: girls 2,165 = `COUNT_DISTINCT(Contact__c)`;
     attendances 4,712; clubs and sessions by `COUNT_DISTINCT`.
   - Read the dashboard's components through the dashboards API.
   - Ryan opens it and checks the Partner filter (screenshot if he sends one).
6. **Keep the source and update the docs:**
   - Keep the deployed source under `data/sf_dashboard_2026-10-02/` (not committed: it names
     users).
   - RUNBOOK: a short "Attendance dashboard" section (what each chart counts, where the filters
     are, rollback).
   - BACKLOG: the rate (below) and region.
   - The plan's Result, and the work log.

## Rollback
> **Superseded 2026-10-16** (Ryan: "I don't want to overwrite with an old package"): never
> redeploy a copy under `data/sf_dashboard_2026-10-02/` (`before/`, `after/`, `fix1/`, `after2/`,
> `totals1/`, ...) or a `gen.py` build; each would overwrite later changes. Every dashboard or
> report deploy starts from a fresh retrieve of what is live; the only rollback for the
> 2026-10-15 change is its three changed components (the dashboard
> `Attendance/Jotform_Attendance_test`, the reports `Attendance/Total_Attendance_Last_Month` and
> `Attendance/Total_Attendance_by_Partner_by_Month`) from `data/sf_totals2_2026-10-15/before/`
> (RUNBOOK "Attendance dashboard in Salesforce", Rollback). As planned on 2026-10-02:
- Delete the new reports and the dashboard (`destructiveChanges.xml`).
- Redeploy the test report's "before" copy.

## Limits to tell leadership
- "Girls who attended" = girls with at least one present row in the period (unique).
- "Sessions" = club sessions with at least one girl present. Duplicate or empty batches add
  nothing.
- Weeks start on Sunday (the org's locale).
- The current month fills in as attendance arrives. A partner's mentors who submit late show up
  late.
- The folders are hidden (not shared): on 2026-10-02 only the 8 active users with View All Data
  could see them, until Ryan shares the folders with leadership (his step, in Salesforce: Share on
  the folder).

## Later (not this round): the attendance rate
"% of max possible" per session = girls present / girls on the club's roster on the session date
(Ryan, 2026-10-02: from the sheet's roster with added and removed dates, only sessions held, no form
changes). It needs:
- two number fields on `Attendance_Batch__c` (present, enrolled);
- a small repo tool that fills them from the roster export;
- a sessions report type with a summary formula.

Into BACKLOG with that design.

## Verification
- `sf project deploy validate` clean, then the deploy succeeds, listing only the new reports, the
  dashboard and the test report.
- Analytics API numbers = SOQL for September, and this month = SOQL for October so far.
- The dashboard API returns every component without error.
- `make check` → `CHECK PASSED` after the docs (plan, RUNBOOK, BACKLOG; no code changes).

## Result (2026-10-02)
- **Built and validated**:
  - six reports, the test report's chart with its rows collapsed, and the dashboard (12
    components, Partner filter with 49 values);
  - check-only deploy 0AfRP000002fu8L0AQ: 8 of 8 components, 0 errors.
- **Deployed by Ryan at 03:46:53 UTC.** The session's permission guard refused a production
  deploy from Claude, so Ryan ran the command himself.
  - Reports: `00ORP000009a6Um2AI` by week, `…Ul2AI` by month, `…Uj2AI` last month, `…Uk2AI`
    this month, `…Uo2AI` sessions by module, `…Un2AI` clubs with no attendance; the test report
    `00ORP000009a5wr2AA`.
  - Dashboard `01ZRP00000BE2TR2A1`.
- **Read-back** (read only):
  - Ten checkers, a skeptic on every doubt, and a completeness critic. They used report runs
    through the Analytics API, report runs with overridden filters (nothing saved), the
    dashboard's cached results and SOQL.
  - **Every number equalled SOQL at the time it was read.**
    - Since 1 September (read about 04:00 UTC): 4,994 rows, 2,261 girls, 382 sessions, 150
      clubs.
    - Each of the five weeks, row for row and unique for unique.
    - September in the dashboard snapshot (03:56 UTC): 2,248 girls, 377 sessions, 149 clubs,
      4,932 rows.
    - Clubs with attendance plus clubs without = 149 + 213 = 362, the club accounts with a
      partner, with 0 differences across the 49 partners.
    - Every module, every partner.
    - The Partner filter, on two partners, including one with an accent.
    - The reports' Partner, Club and Girl filters.
  - **Deployed equals built.** The only difference is Salesforce normalising `expandOthers`, which
    has no visible effect. The pilot dashboard and its reports were not modified.
  - The club by the girl's Contact and the club on the attendance row never differed (0 of
    5,106 rows).
  - The figures this plan expected (4,712 rows, 2,165 girls) were stale. 220 more September rows
    arrived at 03:11-03:26 UTC, before the deploy: the last back-fill sessions and two live
    submissions. September keeps growing with late submissions.
- **Defects found, fixed in `fix1`** (check-only 0AfRP000002fuGP0AY: 2 of 2, 0 errors; deployed
  by Ryan 2026-10-06 09:29 UTC, DeployRequest 0AfRP000002gEbh0AE, 2 of 2):
  1. "This month" used `INTERVAL_CURRENT`, which is the current **fiscal quarter**: Oct-Dec, the
     fiscal year starting in January. It was right in October only by coincidence, and would have
     overcounted from 1 November. Now `INTERVAL_THISMONTH`.
  2. The "clubs with no attendance" table listed one row per club. That was 213 rows, over the
     200-row limit of a Lightning table, so the last partners' clubs could be cut off while the
     number beside it said 213. It now lists one row per partner (at most 49); the club list is
     one click away in its report.
  3. Added: a "How to read this dashboard" box (definitions, late submissions, refresh, where the
     Club and Girl filters are).
- **Passed to BACKLOG**:
  - 58: the attendance rate, with Ryan's definition.
  - 59: region.
  - 60: what to decide before leadership gets it (folder sharing, private club accounts behind
    the click-through reports, girls' names in the test report, scheduled refresh, the
    50-value filter).
  - 61: about 11 probable duplicate girls.
- **Ryan, 2026-10-06**: folder sharing stays as it is, and girls' names are fine for anyone with
  Salesforce access (BACKLOG 60: those two points closed).
- **`fix1` read back (2026-10-06, read only, three checkers and a skeptic on every doubt)**:
  - **Deployed equals built**: `fix1` and `after2` are byte-identical. Only the two components
    changed (09:29:44 UTC); the other six reports are untouched since 10-02. The differences are
    only Salesforce normalisation.
  - **"This month"** resolves to THIS_MONTH, 2026-10-01..31, with 725 girls, 67 sessions, 64
    clubs and 761 rows, all equal to SOQL, and its 18 partners each equal. In October the fiscal
    quarter gives the same rows, so the fix shows in the numbers only from 1 November. The
    resolved range is the proof.
  - **The dashboard after a refresh (09:33 UTC)**: 13 components, all with data.
    - September: 2,602 girls, 456 sessions, 168 clubs, each equal to SOQL.
    - The no-attendance table has 39 rows, one per partner, summing to 196 = the metric = SOQL.
    - The Partner filter on WESAD: every component equal to SOQL.
  - **Found**: two new WESAD clubs, "Change Makers" and "Seeds of Greatness", are on the roster
    since 2026-10-01, after the club accounts were created. When their first attendance arrived
    on 10-03, the processor created partner-less club accounts for them (BACKLOG 27). So 168 + 196
    = 364, not the 362 clubs with a partner. **Fixed 2026-10-06 on Ryan's go**: parent set to WESAD
    through the write connector, one record per call (10:53:18 and 10:53:34 UTC).
    - The first call answered "session expired" but had saved, so it was read back before the
      second.
    - Names, record type and girls (20 and 19 Contacts and attendance rows) were unchanged.
    - 364 Club accounts now have a partner; the only two without are the pilots on hold.
    - Every active roster club now has an account.
    - Before and after: `data/sf_club_parents_2026-10-06/`. Rollback: ParentId blank on both.
- **Also fixed on the way**: `tools/worklog.py` wrote the work log with Windows line endings, so
  every update rewrote every line. It now writes `\n`, with a test.
- `make check` → `CHECK PASSED` (434 tests, `OK`).

## From the RUNBOOK (moved 2026-10-09)

What `docs/RUNBOOK.md` carried for this plan until its 2026-10-09 restructure (the procedure as run, or its history), word for word (links re-pointed to this folder); the RUNBOOK keeps a stub that links here.

### "Attendance dashboard in Salesforce": what is on it and what the numbers mean

**What is on it:**
- four numbers: girls who attended last month; girls who attended this month so far; club
  sessions held last month; clubs that sent attendance last month;
- per week since 1 September: girls attending, sessions held, clubs reporting;
- girls per month;
- last month by partner (girls) and by module (sessions);
- clubs with no attendance last month: a number and a table.

Since `totals1/` (deployed 2026-10-07 03:59 UTC, [plan](2026-10-06-attendance-totals.md)
D), also: total attendance last month from every source beside the Jotform-only figures (a
header says "(Jotform only)" wherever girls are counted by name); total and Jotform attendance
per partner per month; clubs not submitting in the last 14 days and since 1 September (numbers,
and a table by partner for the 14 days); blank submissions since 1 September. Read back the
same night: the reports equal SOQL (264 of 264 totals and groups), and every new tile equals
SOQL unfiltered and under three partners' filters (the plan's Result has the numbers).

The report "Jotform Monthly Attendance" (`Jotform_Monthly_Attendance_test`; "(test)" in its
label until the same deploy) shows a chart with its rows collapsed. Its filters are unchanged.

**`fix1`** (deployed by Ryan 2026-10-06 09:29 UTC, read back the same day):
- "this month" is the calendar month. Until then it was the current fiscal quarter, which gave
  the same numbers in October only.
- The no-attendance table lists one row per partner. A Lightning table stops at 200 rows, and
  the club list is one click away in its report.
- It added the "How to read this dashboard" box.

**What the numbers mean:**
- Every `Attendance__c` row is a girl marked present. Girls are counted with a unique count of
  the Contact, so a girl who came to five sessions counts once.
- A **session** is an attendance batch with at least one girl present. "Clubs that sent
  attendance" likewise counts only clubs with at least one girl present.
- A duplicate re-submission refused by the processor adds nothing (the original counts). A
  submission with no girl ticked adds nothing either: a club whose only submissions last month
  had no girl ticked appears under "no attendance".
- The reports use the report type `Accounts_Contacts_Attendance`, so a girl's club is her
  Contact's account. "Clubs with no attendance" joins on `Attendance__c.Account__c`. The two
  agreed on every row on 2026-10-02 (0 of 5,106 differed); they would split only if a girl's
  Contact were moved to another club.
- **A club without a partner** counts in the girls, sessions and clubs numbers, but never under
  the Partner filter or in the no-attendance table. So "clubs that sent attendance" plus "clubs
  with no attendance" equals the clubs with a partner only while every reporting club has one.
  A new club whose account was not created before its first attendance gets a partner-less
  account from the processor ("Club accounts in Salesforce", BACKLOG 27); set its parent.
- Weeks run Sunday to Saturday (every user has the en_US locale). The first week shows only
  1-5 September.
- "Last month" and "this month" roll over at midnight in the running user's time zone: Ryan's,
  Los Angeles, for the dashboard; the viewer's for a report opened from it. 16 of the 18 active
  users were on Los Angeles time on 2026-10-02, and two on African time zones.
- **Late submissions**: 12 of the first 28 live sessions arrived more than a day late, and the
  latest up to 19 days late. So "last month" settles around the 20th, and the latest week and
  "this month" always start low. Compare months only after that.
- **Snapshot**: a dashboard shows its last refresh (the time at top right), not live data.
  Press Refresh, or schedule a daily refresh (Ryan's step: **Subscribe** on the dashboard in
  Lightning; Refresh ▾ → Schedule Refresh is the Classic path; Access, below).
- **Total attendance** (since `totals1/`, 2026-10-07) sums `Girls_Present__c` over `Success`
  batches - the Jotform rows plus the monthly counts partners without Jotform report
  (`Creator__c` `Partner report`; "Attendance totals and partner-reported counts"). Until a
  partner's first count arrives (BACKLOG 72) the Jotform-only figures equal the totals.
  (2026-10-15, ticket #35: the total now adds only the three partners' Salesforce-entered counts
  to the Jotform rows, and any other Salesforce entry is left out; RUNBOOK "Attendance totals and
  partner-reported counts", [plan](2026-10-15-attendance-total-three-partners.md).) "Girls who
  attended" stays Jotform only (a reported count has no names) and counts each girl once. "Did
  not submit" in the 14-day and since-1-September windows means no batch of any status dated in
  the window (a refused duplicate counts as submitted); the 14-day window is today plus the 14
  days before it, in the org's time zone (Pacific: on the evening of 2026-10-06 there, 09-22 to
  10-06); the last-month tile stays row-based. A
  **blank** is a submission with no girl ticked: `Failed` "No participants submitted", or a
  legacy `Success` with `Girls_Present__c` 0. Clubs whose partner reports a monthly count show
  as not submitting until that count arrives; the U.S clubs, which do not report attendance
  here, stay on the lists ("Clubs that do not use Jotform").
