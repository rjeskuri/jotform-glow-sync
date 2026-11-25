---
title: The six U.S partners' Monthly Reports through October 2026 count again on the six totals reports
author: Claude (ticket #267, with Ryan's request of 2026-11-24/25 and his go of 2026-11-25)
status: done      # ticket #267; deployed 2026-11-25 02:36 UTC on Ryan's go, given on the check-only 0AfRP000002kzKH0AY (rerun after the go as 0AfRP000002l1Nh0AI; deploy 0AfRP000002l1XN0AY), read back, checked against SOQL
done: 2026-11-25
created: 2026-11-25
intent: Ryan, 2026-11-24/25 - the monthly dashboards (D1-D5) line up with the interactive dashboard
---

# Plan: the U.S Monthly Reports through October 2026 on the totals reports

Ticket #267 (epic #68). Ryan, 2026-11-24/25: the monthly dashboards (D1-D5) should line up with
the interactive dashboard, so the six U.S partners' Monthly Reports count again for the months
they were active, and the Jotform-side reports keep leaving their deactivated clubs out. He took
both recommendations: the cutoff is through October 2026 (`Period__c` before 2026-11-01), and
only the totals and trends reports change. Ryan's go, "go with sums", 2026-11-25: the three D1
attendance reports and items 10, 13 and 14 (on the check-only `0AfRP000002kzKH0AY`). This amends
#209 ([plan](2026-11-05-sf-us-partners.md); DECISIONS 2026-11-05) for those six reports.
Decision: DECISIONS 2026-11-25. Procedure: RUNBOOK "Monthly Report dashboards in Salesforce".

## Context

- **The gap** (2026-11-24, counts only): between the interactive dashboard and D1-D5, January to
  October 2026, the difference is exactly the six U.S partners' `Monthly_Total__c`, month by
  month 132, 130, 111, 90, 97, 40, 0, 5, 5, 29 (639). Test accounts and reports with a blank
  account add 0, and no report has a blank Monthly Max with week counts filled in.
- **The six U.S partners** are #209's (RUNBOOK "Monthly Report dashboards in Salesforce", The
  U.S partners), their names re-read by Id on 2026-11-25: unchanged. Their Monthly Reports of
  January-October 2026: 47 (37 approved), none after October, none with a blank `Period__c`. The
  U.S form was disabled on 2026-10-06; two U.S reports exist for October.
- **Before #267** every Dhis2 report (22: the 21 on D1-D5 and item 19) carried #209's locked
  criteria item `DHIS2__c$Account__c notEqual <the six>`, and none had a `booleanFilter`.
- **What changes:** the reports that sum or chart attendance, or a count GLOW totals (Ryan's
  recommendation 2; the classification is in the Result). In each, the #209 item is ORed with a
  new locked criteria item `DHIS2__c$Period__c lessThan 11/1/2026` through `booleanFilter`.
- **Unchanged:** the 15 other Dhis2 reports on D1-D5 and item 19 (the stories table), which keep
  the full #209 exclusion; item 6, Modules Implemented by Month and Partner (report type
  `Attendance_Totals`, the Jotform attendance rows, with no #209 item: the U.S has no batches);
  the three not-submitted lists and the Jotform Attendance dashboard's Partner filter; D1-D5
  themselves; the interactive dashboard (LWC `glowDashboardShell`), which has no filters.
- Work folder (owner only, never committed): `data/sf_us_monthly_2026-11-25/`, with `before/`
  (the rollback retrieve), `fresh_0120/`, `build/` and its `make_build.py`, `after/`,
  `copies/ledger.csv` and `evidence/` (`prep_2026-11-25.md`, `check_0238/summary.md`, the
  dashboards' JSON).

## Build

- `make_build.py . --with-sums` edits a copy of `before/` into `build/` by text: in each of the
  6 reports one `booleanFilter` and one new locked criteria item `DHIS2__c$Period__c lessThan
  11/1/2026`; the OR pairs the locked #209 item with the Period item, and the other items
  (`In_Reporting_Year__c`, Account not blank, Account not containing "test", and any report's own)
  stay ANDed.
- Each report gains 8 lines; 6 members in `data/sf_us_monthly_2026-11-25/build/package.xml`.
- The filter logic, report by report:
  - Overall Attendance by Month (D1): `1 AND 2 AND (3 OR 5) AND 4`
  - Participation by Month and Partner (D1, item 3): `1 AND 2 AND (3 OR 5) AND 4`
  - GLOW Club Each Week (D1, item 4): `1 AND 2 AND 3 AND 4 AND (5 OR 7) AND 6`
  - Club Observations by Month and Partner (D3, item 10): `1 AND 2 AND 3 AND (4 OR 6) AND 5`
  - Number of mentors trained about module (D4, item 13): `1 AND 2 AND (3 OR 5) AND 4`
  - Number of training sessions led (D4, item 14): `1 AND 2 AND (3 OR 5) AND 4`

## Rollout

VPN off (ExpressVPN disconnected, the default route on en0), in the main session; each write on
Ryan's go.

1. The prep, 2026-11-25 00:50-01:15 UTC, read-only: retrieve live the 32 components (26 reports
   and 6 dashboards: D1-D5 and Jotform Attendance) into `data/sf_us_monthly_2026-11-25/before/`,
   the rollback retrieve (about 00:55 UTC); build both variants from it and run a check-only
   (`--dry-run`) of each: the default build (the 3 D1 attendance reports) `0AfRP000002kzLt0AI`,
   3/3 Succeeded, and `make_build.py . --with-sums` (the 6 reports) `0AfRP000002kzKH0AY`, 6/6
   Succeeded.
2. Ryan's go, "go with sums", 2026-11-25 (in the main session, relayed on #267), the answer to
   the question that offered "go" (the 3 D1 attendance reports, check-only `0AfRP000002kzLt0AI`)
   or "go with sums" (the 6, check-only `0AfRP000002kzKH0AY`): the 6 reports, the three D1
   attendance reports and items 10, 13 and 14, on the scope of the earlier go comment (only the
   totals and trends reports change; the reports that keep the exclusion, item 19, the three
   not-submitted lists and the Jotform Attendance Partner filter untouched).
3. After the go, a fresh retrieve of the same 32 at 01:20 UTC into `fresh_0120/`: equal to
   `before/` byte for byte.
4. Rebuild `build/` from `before/` with `make_build.py . --with-sums` (Build, above): 6 reports, 6
   members in `build/package.xml`.
5. Check-only of the rebuild (`--dry-run`): `0AfRP000002l1Nh0AI`, 6/6 Succeeded at 01:21 UTC.
6. Copies into Decommissioned (`00lRP000007iOiXYAU`) before anything changes, 02:33-02:36 UTC,
   once per report, each read back:
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_us_monthly_2026-11-25/copies --kind report --id <id> --tag "#267" --apply`
7. Deploy from `build/`: `sf project deploy start -o glow --source-dir
   data/sf_us_monthly_2026-11-25/build/force-app`, `0AfRP000002l1XN0AY`, 6/6 Succeeded, completed
   02:36:26 UTC.
8. Read back at 02:37 UTC: the 32 components retrieved into `after/`, and `after/` compared with
   `build/` for the 6 changed reports (equal byte for byte) and with `before/` for the other 26.
9. Run the 6 reports through the Analytics API beside SOQL at the same moment (02:38 UTC): each
   figure equals SOQL with `AND (Account__r.Name NOT IN (<the six>) OR Period__c < 2026-11-01)`.
10. Refresh the dashboards that hold the 6 reports (D1, D3 and D4; PUT, then GET) and read every
    component's status.

## Rollback

DECISIONS 2026-10-16, each write on Ryan's go after a check-only, VPN off.

- The 6 reports are restored by a deploy from a fresh retrieve with the `booleanFilter` and the
  Period item removed, or from #267's own `data/sf_us_monthly_2026-11-25/before/` only while a
  fresh retrieve of the 6 equals `after/`.
- The copies in Decommissioned (tagged `#267`) are the record of what the reports were, not the
  restore.
- The members are the 6 of `data/sf_us_monthly_2026-11-25/build/package.xml`. Never from an older
  build or retrieve. Nothing is deleted.

## Result

2026-11-25: the read-only prep 00:50-01:15 UTC, then Ryan's go, then the run 01:20-02:42 UTC,
each write on that go through the live gate.

- The prep: the rollback retrieve `before/` (about 00:55 UTC) and a check-only of each build,
  `0AfRP000002kzLt0AI` for the default (the 3 D1 attendance reports, 3/3 Succeeded) and
  `0AfRP000002kzKH0AY` for `--with-sums` (the 6 reports, 6/6 Succeeded).
- Ryan's go, "go with sums" (2026-11-25), answered the prep's question on the check-only
  `0AfRP000002kzKH0AY`, before the run started.
- Before: the rollback retrieve `before/` holds 6 dashboards (D1-D5 and Jotform Attendance) and
  26 reports; the fresh retrieve of 01:20 UTC, after the go, equals it byte for byte.
- Check-only `0AfRP000002l1Nh0AI` of the rebuilt `build/`: 6/6 Succeeded (01:21 UTC).
- The six copies are in Decommissioned (`00lRP000007iOiXYAU`), tagged `#267`, made 02:33-02:36
  UTC by `tools/sf_report_folders.py copy`, each read back (ledger
  `data/sf_us_monthly_2026-11-25/copies/ledger.csv`).
- Deploy `0AfRP000002l1XN0AY`: 6/6 Succeeded, completed 02:36:26 UTC.
- Read back (02:37 UTC): the 6 changed reports in `after/` equal `build/` byte for byte, and the
  other 26 components in `after/` equal `before/` byte for byte: the 15 kept Dhis2 reports on
  D1-D5, item 19, item 6 (Modules Implemented by Month and Partner), the three not-submitted
  lists, D1-D5 and the Jotform Attendance dashboard with its Partner filter of 44 options (since
  #212) and its Region filter of 4.
- Overall Attendance by Month and Participation by Month and Partner (item 3): Monthly_Total
  January-October 2026 49,337 → 49,976 (the U.S +639), equal to SOQL.
- GLOW Club Each Week (item 4): rows 374 → 410, its Monthly_Total 49,976 and Week_1-5 22,405,
  22,712, 22,437, 21,582 and 8,178 (the U.S +287, +368, +309, +334, +107), equal to SOQL.
- Club Observations by Month and Partner (item 10): sessions observed 908 → 920 (the U.S +12),
  457 rows, equal to SOQL.
- Number of mentors trained about module (item 13): 1,282 → 1,283 (the U.S +1), 468 rows, equal
  to SOQL.
- Number of training sessions led (item 14): 500 → 501 (the U.S +1), 468 rows, equal to SOQL.
- All `DHIS2__c` with `Period__c` in January-October 2026, no other filter: Monthly_Total 49,976
  (470 reports), equal to the reports' total. The ticket's 50,020 of 2026-11-24 was taken while
  October stood 44 higher (5,071 then, 5,027 at 02:38 UTC): `Monthly_Total__c` is a formula, and
  October's late reports still move it.
- Dashboards refreshed 02:39-02:40 UTC (PUT, then GET): Glow Club Attendance (D1,
  `01ZRP000006iWqL2AU`) 4/4 components DATA (49,976), Club Observation Dashboards (D3,
  `01ZRP000006k2D32AI`) 3/3 DATA (920), Mentors (D4, `01ZRP000006quAj2AI`) 5/5 DATA (1,283 and
  501). D2 and D5 hold none of the 6 reports.

Overall Attendance by Month, by month (the SOQL filter: `In_Reporting_Year__c`, Account not
blank, not "test"; before #267 the six always out, after #267 (Account not the six OR `Period__c`
before 2026-11-01); the U.S row the six with `Period__c` before 2026-11-01):

| 2026 | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Before #267 | 3277 | 4889 | 5562 | 4978 | 5336 | 5235 | 4856 | 4821 | 5385 | 4998 | 49,337 |
| The U.S partners | 132 | 130 | 111 | 90 | 97 | 40 | 0 | 5 | 5 | 29 | 639 |
| After #267, equal to SOQL | 3409 | 5019 | 5673 | 5068 | 5433 | 5275 | 4856 | 4826 | 5390 | 5027 | 49,976 |

The six reports (source → copy in Decommissioned) and the filter logic deployed:

| Source | Report | Filter logic | Copy |
|---|---|---|---|
| `00ORP000009p0FJ2AY` | Overall Attendance by Month (D1) | `1 AND 2 AND (3 OR 5) AND 4` | `00ORP000009ucdJ2AQ` |
| `00ORP000005rSbB2AU` | Participation by Month and Partner (D1, item 3) | `1 AND 2 AND (3 OR 5) AND 4` | `00ORP000009ucjl2AA` |
| `00ORP000005ufOz2AI` | GLOW Club Each Week (D1, item 4) | `1 AND 2 AND 3 AND 4 AND (5 OR 7) AND 6` | `00ORP000009uclN2AQ` |
| `00ORP000004RJZD2A4` | Club Observations by Month and Partner (D3, item 10) | `1 AND 2 AND 3 AND (4 OR 6) AND 5` | `00ORP000009ucmz2AA` |
| `00ORP000004RJZE2A4` | Number of mentors trained about module (D4, item 13) | `1 AND 2 AND (3 OR 5) AND 4` | `00ORP000009ucob2AA` |
| `00ORP000004RJZ82AO` | Number of training sessions led (D4, item 14) | `1 AND 2 AND (3 OR 5) AND 4` | `00ORP000009ucqD2AQ` |

The classification of the 23 reports in "GLOW Monthly Reports" (22 Dhis2 reports, the 21 on D1-D5
and item 19, and one `Attendance_Totals` report on D1-D5), for Ryan:

- Changed, the 6 above: they sum or chart attendance, or a count GLOW totals.
- Kept on the full #209 exclusion, 15 on D1-D5 (who reported, what is approved, on time, which
  clubs or modules): Approval Status by Month `00ORP000009p0qb2AA`, Monthly Report Approval Status
  `00ORP000006XXEf2AO`, Collection of Attendance Roster by Month `00ORP000004RJYv2AO`, Clubs
  Observed at Least Once by Month `00ORP000005uf412AA`, Club Implementation by Month and Partner
  `00ORP000005rY3t2AE`, Modules Adapted by Month and Partner `00ORP000005uehR2AQ`, Leading
  training sessions with mentors `00ORP000004RJZ62AO`, Local and Regional Summits By Month 2
  `00ORP000005uekf2AA`, Meeting with mentors to discuss program `00ORP000004RJZ72AO`, Modules
  Adapted Responses `00ORP000009p0Qb2AI`, On Time by Month `00ORP000009taVV2AY`, Partners that
  recruited new mentors `00ORP000009kXev2AE`, Reports completed on time `00ORP0000054DyH2AU`, GC
  Observation Forms by Month & Partner `00ORP000004RJZC2A4`, Summit Types Completed
  `00ORP000009p0Qc2AI`.
- Kept on the full #209 exclusion, the stories: item 19, GLOW of the Month Stories Report
  `00ORP000005p2L32AI`.
- Not a Dhis2 report, unchanged and without the #209 item: Modules Implemented by Month and
  Partner `00ORP000009kUNh2AM` (item 6, report type `Attendance_Totals`; the U.S has none of its
  rows).
- The Attendance side, unchanged: Clubs Not Submitting - Last 14 Days `00ORP000009c8iY2AQ`, Clubs
  Not Submitting - Since 1 Sept `00ORP000009c8iZ2AQ`, Clubs With No Attendance Last Month
  `00ORP000009a6Un2AI`, and the Jotform Attendance dashboard `01ZRP00000BE2TR2A1` (Partner filter
  44 options since #212, Region filter 4), read back unchanged. The interactive dashboard (LWC)
  has no filters and is untouched.
