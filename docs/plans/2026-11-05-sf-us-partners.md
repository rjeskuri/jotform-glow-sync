---
title: The six U.S partners off every dashboard and report; the not-submitted lists without the monthly partners
author: Claude (ticket #209, with Ryan's request and added scope of 2026-11-05)
status: done      # ticket #209; deployed 2026-11-05/06 UTC on Ryan's go (round 1 0AfRP000002jNNV0A2, round 2 0AfRP000002jNQj0AM, round 3 0AfRP000002jNiT0AU), read back, checked against SOQL
done: 2026-11-06
created: 2026-11-05
intent: Ryan, 2026-11-05 - the U.S partners are inactive and distort the totals; their girls and clubs should not count as not submitted
---

# Plan: the U.S partners off the dashboards

Ticket #209 (epic #194). Ryan, 2026-11-05: "remove all US partners from all dashboards and reports
as they are inactive and distorting the total numbers. These girls and clubs should not count as
not submitted for example." Decision: DECISIONS 2026-11-05. Procedures: RUNBOOK "Monthly Report
dashboards in Salesforce" and "Attendance dashboard in Salesforce".

## Context

- **The six U.S partners** (region U.S in `appsscript/Regions.gs` and `glow/sf_partners.csv`;
  names re-read by Id on 2026-11-05, each unique in the org): Angelo Patri School
  (`001RP000002nJZUYA2`), Detroit Public Schools (`001RP000002nJZNYA2`), Ewa Makai Middle School
  (`001RP00000SL2ebYAD`), Farmington Municipal School District (`001RP00000F1DPBYA3`), HOLA
  (`001RP000002nJZXYA2`) and Holbrook Unified School District (`001RP00000VxX9PYAV`).
- They have 11 Club accounts, 0 `Attendance_Batch__c`, 0 `Attendance__c` and 0 Contacts, and 46
  Monthly Reports (`DHIS2__c`) in 2026, 36 of them approved, Monthly_Total 605.
- **Round 1** (the request): every Monthly report on D1-D5 and item 19 (the stories table) filters
  `DHIS2__c$Account__c notEqual` the six; the three not-submitted lists (Clubs Not Submitting -
  Last 14 Days `00ORP000009c8iY2AQ`, Clubs Not Submitting - Since 1 Sept `00ORP000009c8iZ2AQ`,
  Clubs With No Attendance Last Month `00ORP000009a6Un2AI`) filter `PARENT.NAME notEqual` the six;
  the Jotform Attendance dashboard (`01ZRP00000BE2TR2A1`) loses the six options of its Partner
  filter.
- **Round 2** (Ryan's added scope, 2026-11-05, on the ticket): the three not-submitted lists also
  leave out the 38 clubs of the three monthly partners (Education and English for You, Tumaini La
  Maisha, Ng'aa Maskani), one `PARENT.NAME notEqual` holding the nine partners, the value of Clubs
  Not Submitting - Last Week (`00ORP000009kYPh2AM`, DECISIONS 2026-10-24). Coordinators use the
  lists to chase Jotform submissions; those partners report through Salesforce. Their Monthly
  Reports stay on D1-D5, and the Girls Attended tiles keep their `Partner report` batches.
- **Round 3** (a review finding on #209): the Jotform Attendance dashboard's "How to read this
  dashboard" box said the monthly partners' clubs "show as not submitting until that count
  arrives" and the U.S clubs "stay on the lists"; that one sentence is replaced so the box says
  the lists leave those clubs out.
- **Unchanged:** D1-D5 themselves; item 6 and the attendance-row reports (the U.S has no batches,
  and its form is disabled, DECISIONS 2026-10-06); the interactive dashboard (on hold, #81-#83).
- This ticket lifts, for these changes only and on Ryan's request, the epic's rule that the
  Jotform Attendance dashboard and the Attendance folders stay untouched.
- Work folder (owner only, never committed): `data/sf_us_partners_2026-11-05/`, with `before/`,
  `build/`, `after/`, `copies/ledger.csv`, `item11_copy/`, `evidence/` and `make_build.py`;
  round 2 in its own `round2/` beside them.

## Build

- `make_build.py` edits a copy of `before/` into `build/` by text: in each of the 21 Dhis2 reports
  (the 20 on D1-D5 and item 19) one locked criteria item `DHIS2__c$Account__c notEqual <the six
  names>` beside the test rule, any `booleanFilter` extended; in the three not-submitted lists
  `PARENT.NAME notEqual <the six names>`, in the form of Clubs Not Submitting - Last Week's; the
  Jotform Attendance dashboard's Partner filter 49 → 43 options.
- 24 reports gain 7 lines each and the dashboard loses 24 lines; 25 members in
  `data/sf_us_partners_2026-11-05/build/package.xml`.

## Rollout

VPN off, in the main session; each write on Ryan's go.

1. Retrieve live into `data/sf_us_partners_2026-11-05/before/`: D1-D5 and every report on them,
   item 6 (unchanged, for the record), item 19, the Jotform Attendance dashboard and its three
   not-submitted lists.
2. Copies into Decommissioned before anything changes, each on Ryan's go after its dry run:
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_us_partners_2026-11-05/copies --kind report --id <id> --tag "#209" --apply`,
   once per Monthly report the build changes. D1, D2 and D5 are dynamic (no Decommissioned
   copy), so their rollback is `before/`; #209 changes none of D1-D5, so no dashboard is copied.
   The Attendance reports and the Jotform
   Attendance dashboard are not copied (the tool never takes the Attendance folders), so their
   rollback is `before/`.
3. Item 11 (`00ORP000005uf412AA`, a bucket field): the Analytics API refused its copy (HTTP 400),
   so it is copied into Decommissioned by metadata from `item11_copy/`, its own check-only
   first, then on Ryan's go its own deploy.
4. Check-only of the build from `build/`:
   `sf project deploy start --dry-run -o glow -d force-app`.
5. On Ryan's go, deploy: `sf project deploy start -o glow -d force-app` from `build/`.
6. Read back: retrieve the 25 members into `after/` and compare `after/` with `build/`, equal
   beyond Salesforce's normalisation.
7. Refresh each dashboard (D1-D5 and Jotform Attendance) and read every component's status.
8. Run the changed reports through the Analytics API: each before/after figure equals SOQL
   without the six (`AND Account__r.Name NOT IN (<the six>)`), D5's not-yet-approved count drops
   by the U.S reports', and each not-submitted list drops by the 11 U.S clubs.
9. Round 2 in `data/sf_us_partners_2026-11-05/round2/`: a fresh retrieve of the three lists into
   `round2/before/`, compared with round 1's `after/`; `round2/build/` sets each list's
   `PARENT.NAME notEqual` to the nine partners; check-only, Ryan's go, deploy; `round2/after/`
   compared with `round2/build/`; the three lists run again and each count equals SOQL.
10. Round 3 in `data/sf_us_partners_2026-11-05/round3/` (a review finding: the dashboard's "How to
    read this dashboard" box still said the monthly partners' clubs show as not submitting and the
    U.S clubs stay on the lists): a fresh retrieve of the Jotform Attendance dashboard into
    `round3/before/`, compared with round 1's `after/`; `round3/build/` replaces that one sentence
    of the box's rich text; check-only, Ryan's go, deploy; `round3/after/` compared with
    `round3/build/`.

## Rollback

DECISIONS 2026-10-16, each write on Ryan's go after a check-only, VPN off.

- Round 3 is undone first, then round 2, then round 1.
- Round 3: the How-to box is restored by a deploy from a fresh retrieve with its sentence put
  back, or by a deploy of the dashboard in `data/sf_us_partners_2026-11-05/round3/before/` only
  while a fresh retrieve equals `round3/after/`.
- Round 2: the three not-submitted lists are restored by a deploy from a fresh retrieve with the
  three monthly partners taken out of their `PARENT.NAME` value, or by a deploy of their files in
  `data/sf_us_partners_2026-11-05/round2/before/` only while a fresh retrieve equals
  `round2/after/`.
- Round 1, the Monthly reports: the 21 reports are restored by a deploy from a fresh retrieve
  with the U.S criteria items removed, or from #209's own `data/sf_us_partners_2026-11-05/before/`
  only while a fresh retrieve equals `after/`. The copies in Decommissioned are the record of what
  the reports were; item 11's metadata copy stays there.
- Round 1, the Attendance reports and the Jotform Attendance dashboard: the three lists and the
  dashboard are restored by a deploy of their files in `data/sf_us_partners_2026-11-05/before/`,
  only while a fresh retrieve equals `after/`; otherwise from a fresh retrieve with the six U.S
  partners taken out of the lists' value and the six Partner options restored to the dashboard.
- The members are the 25 of `data/sf_us_partners_2026-11-05/build/package.xml`. Never from an
  older build or retrieve. Nothing is deleted.

## Result

2026-11-05 23:29 UTC to 2026-11-06 00:39 UTC, each write on Ryan's go through the live gate.

- Before: the 09:48 UTC retrieve took 6 dashboards (D1-D5 and Jotform Attendance
  `Attendance/Jotform_Attendance_test`) and 25 reports: the 20 Dhis2 reports on D1-D5, item 6
  (`Attendance_Totals`, unchanged), item 19 and the three not-submitted lists.
- The copies are in Decommissioned, tagged `#209`, made 23:29-23:32 UTC by
  `tools/sf_report_folders.py copy` for 20 of the 21 Monthly reports (ledger
  `data/sf_us_partners_2026-11-05/copies/ledger.csv`).
- Item 11 (`00ORP000005uf412AA`): its Analytics API copy was refused (HTTP 400), so it was copied
  by metadata into Decommissioned as `Completed_Observing_Clubs_Alteast_Once_P_209`
  `00ORP000009q7GL2AY` (check-only `0AfRP000002jNFR0A2`, deploy `0AfRP000002jNH30AM`, 23:40 UTC).
- Round 1: check-only `0AfRP000002jNIf0AM` (25/25), deploy `0AfRP000002jNNV0A2` (25/25, completed
  23:48:55 UTC). `after/` equals `build/` byte for byte, 25 of 25.
- Refresh: D1-D5 returned DATA on every component, with 0 grouping labels of a U.S partner and no
  U.S option in any filter. Jotform Attendance returned DATA on its 17 report components
  (component 17 is an embedded dashboard component, with no data status), and its Partner filter
  has 43 options, none of them U.S.
- Approval Status by Month 430 → 384, equal to SOQL (319 approved + 65 not yet approved).
- Monthly Report Approval Status (item 17) 355 → 319, equal to SOQL.
- Overall Attendance by Month 45,118 → 44,513, equal to SOQL (Monthly_Total 38,766 + 5,747).
- Round 2: check-only `0AfRP000002jNP70AM` (3/3), deploy `0AfRP000002jNQj0AM` (3/3, completed
  23:57:04 UTC). `round2/before/` equalled round 1's `after/`, and `round2/after/` equals
  `round2/build/`, 3 of 3. Clubs Not Submitting - Last Week (`00ORP000009kYPh2AM`) was retrieved
  for its value and is unchanged.
- Clubs Not Submitting - Last 14 Days 187 → 176 → 138, each equal to SOQL (round 1 the 11 U.S
  clubs, round 2 the 38 clubs of the three monthly partners).
- Clubs Not Submitting - Since 1 Sept 124 → 113 → 75, each equal to SOQL (−11, then −38).
- Clubs With No Attendance Last Month 139 → 128 → 90, each equal to SOQL (−11, then −38).
- Round 3: check-only `0AfRP000002jNgr0AE` (1/1), deploy `0AfRP000002jNiT0AU` (1/1, completed
  2026-11-06 00:38:38 UTC). `round3/before/` equalled round 1's `after/`, and `round3/after/`
  equals `round3/build/`. The box's sentence now reads: "The not-submitting lists leave out the
  clubs of the three partners that report a monthly count instead of using Jotform, and the U.S.
  clubs: they are for following up Jotform submissions."

The 20 copies by the tool (source → copy in Decommissioned):

| Source | Copy |
|---|---|
| `00ORP000009p0qb2AA` | `00ORP000009q6lh2AA` |
| `00ORP000006XXEf2AO` | `00ORP000009q6nJ2AQ` |
| `00ORP000004RJYv2AO` | `00ORP000009q6ov2AA` |
| `00ORP000005rY3t2AE` | `00ORP000009q6qX2AQ` |
| `00ORP000005ufOz2AI` | `00ORP000009q6s92AA` |
| `00ORP000005uehR2AQ` | `00ORP000009q6tl2AA` |
| `00ORP000005p2L32AI` | `00ORP000009q6vN2AQ` |
| `00ORP000004RJZ62AO` | `00ORP000009q6wz2AA` |
| `00ORP000005uekf2AA` | `00ORP000009q6CE2AY` |
| `00ORP000004RJZ72AO` | `00ORP000009q6yb2AA` |
| `00ORP000009p0Qb2AI` | `00ORP000009q70D2AQ` |
| `00ORP000004RJZE2A4` | `00ORP000009q71p2AA` |
| `00ORP000004RJZ82AO` | `00ORP000009q73R2AQ` |
| `00ORP000009p0FJ2AY` | `00ORP000009q7532AA` |
| `00ORP000005rSbB2AU` | `00ORP000009q76f2AA` |
| `00ORP000009kXev2AE` | `00ORP000009q78H2AQ` |
| `00ORP0000054DyH2AU` | `00ORP000009q79t2AA` |
| `00ORP000004RJZC2A4` | `00ORP000009q6FS2AY` |
| `00ORP000009p0Qc2AI` | `00ORP000009q76g2AA` |
| `00ORP000004RJZD2A4` | `00ORP000009q7BV2AY` |
