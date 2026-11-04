---
title: Club Observation Dashboards (D3) - GLOW's names, 2026 only, a Month filter, the former PO off the filter
author: Claude (ticket #198, with Ryan's decisions of 2026-11-02)
status: done      # ticket #198; deployed 2026-11-04 08:56 UTC on Ryan's go (0AfRP000002j9ij0AA, 4/4), read back, checked against SOQL
done: 2026-11-04
created: 2026-11-02
intent: GLOW's review of 2026-11-02 (epic #194) - the dashboard "GLOW Club Training" is about club observations, not training; full wording for the component titles; the typo "Alteast"; 2026 only; a filter by month
---

# Plan: D3 after GLOW's review

Ticket #198 (epic #194), after #195 ([plan](2026-11-02-sf-reporting-year.md)) added
`DHIS2__c.In_Reporting_Year__c`. D3 is the dashboard `01ZRP000006k2D32AI` in "GLOW Monthly
Dashboards", with items 9-11 of `glow/sf_keep_list.csv`, reports in "GLOW Monthly Reports".
RUNBOOK `### GLOW Club Observations` holds the state and the rollback.

## Context

- GLOW, 2026-11-02: the dashboard named "GLOW Club Training" shows club observations, not
  training, so it is titled "Club Observation Dashboards" (the Id stays).
- The component titles in GLOW's full wording: "Submission of GC observation forms by month and
  partner", "Total Number of Club Observations by Month and Partner" (GLOW's note reads "Cub", a
  typo) and "Completed Observing Clubs At least Once by Month and Partner" ("Alteast" fixed).
- General: 2026 only, the former PO (user `005RP000001RERJYA4`) off the Partner Manager filter,
  and a filter by month.
- GLOW's "I think we have removed this question from the form?" is about the count question
  `many_clubs_do_you_still_need_to_observe__c`, which has no answers in 2026. Item 11 does not use
  it: it derives Observed Yes/No from `GC_sessions_did_you_observe_last_month__c` (Yes for 1 or
  more, No for 0), answered in every month of 2026. The report stays; the reply to GLOW (#201)
  says so.
- A report's name is limited to 40 characters, so the three reports get shorter names than the
  component titles, in `glow/sf_keep_list.csv`'s `label_target` (`label_today` stays the label
  #70 recorded).

## Build

`data/sf_glow_review_2026-11/observations/build/` (in the ticket worktree, never committed), made
by `make_build.py` from a copy of the retrieve `before/`, text edits each with an assert:

- Items 9 (`00ORP000004RJZC2A4`), 10 (`00ORP000004RJZD2A4`) and 11 (`00ORP000005uf412AA`): the
  filter `DHIS2__c$Period__c equals LAST_N_MONTHS:12` becomes `DHIS2__c$In_Reporting_Year__c
  equals 1` (true).
- Report labels: item 9 "GC Observation Forms by Month & Partner", item 10 "Club Observations by
  Month and Partner", item 11 "Clubs Observed at Least Once by Month".
- D3, the three component titles as above, and the dashboard title "Club Observation Dashboards".
- D3, the Assigned Partner Manager filter: the former PO's option goes (6 options to 5).
- D3, a second dashboard filter "Month" on `DHIS2__c$Month__c`: 12 `equals` options, January to
  December, mapped on all 3 components.
- Item 11's developer name, `Completed_Observing_Clubs_Alteast_Once_P_cn6`, keeps "Alteast": an
  API name is fixed with the report's Id, and no label or title has it.

## Rollout (live; each write on Ryan's go)

VPN off (`route -n get default` shows `en0`), in the main session, through the `sf` CLI login
`glow`. Ryan gave his go in chat on 2026-11-04; each live command also passed the live-gate
prompt.

1. Retrieve live into `data/sf_glow_review_2026-11/observations/before/`: D3, and items 9, 10 and
   11. Compare it with `data/sf_dash_observations_2026-10-24/fresh_2026-10-26/`; a difference
   stops for Ryan.
2. Copies into Decommissioned before anything changes, each on Ryan's go after its dry run:
   `python3 tools/sf_report_folders.py copy --kind <dashboard|report> --id <id> --tag "#198" --vpn-off --dir data/sf_glow_review_2026-11/observations/copies --apply`
   for D3 and items 9 and 10. Each copy is read back and its row in `copies/ledger.csv` says
   `ok`. D3 runs as a specified user, so its copy works; the copy's rename and description in
   Lightning are by hand, as the tool says, and the deploy carries the new title.
3. Item 11's copy: the Analytics API refused it (HTTP 400; item 11 is the only one of the four
   with a bucket field, `BucketField_Observed`, the likely cause), and its ledger row says
   `failed`. The fallback is a copy by metadata: item 11's `before/` XML as
   `Decommissioned/Completed_Observing_Clubs_Alteast_Once_P_198` with the description "copy of
   00ORP000005uf412AA, #198" (folder `Decommissioned`, `00lRP000007iOiXYAU`), check-only, then
   deploy, then read back from Decommissioned.
4. Make `build/` from a copy of `before/` with `make_build.py` (Build, above).
5. Check-only from `build/`: `sf project deploy start --dry-run -o glow -d force-app`, on Ryan's
   go.
6. On Ryan's go, deploy: `sf project deploy start -o glow -d force-app` from `build/`.
7. Read back: retrieve D3 and the three reports into `after/` and compare `after/` with `build/`.
8. Refresh D3:
   `sf api request rest '/services/data/v67.0/analytics/dashboards/01ZRP000006k2D32AI' -o glow -X PUT -b '{}'`;
   every component returns data.
9. Check against SOQL on `DHIS2__c` for September 2026, the last complete month (Result).

## Rollback

DECISIONS 2026-10-16, each write on Ryan's go after a check-only, VPN off.

- The dashboard and the reports of items 9-11 are restored by a deploy, and their copies in
  Decommissioned (the dashboard `01ZRP00000BV0bh2AD`, items 9 and 10 `00ORP000009p0dV2AQ` and
  `00ORP000009p0f72AA`, item 11 `00ORP000009p0jx2AA`, tagged `#198`) are the record of what they
  were. A report copy saved back into "GLOW Monthly Reports" would be a separate report: D3's
  components point at the reports themselves, so D3 would still show the new reports.
- The deploy is one of two, after a check-only: a fresh retrieve of the four, edited back where
  #198 changed them; or their files in `data/sf_glow_review_2026-11/observations/before/`, only
  while a fresh retrieve of the same four equals `after/` (nothing has changed them since this
  deploy). It names each with `-m`, as #77's rollback does (RUNBOOK).
- Never from an older build or retrieve (DECISIONS 2026-10-16): #77's
  `data/sf_dash_observations_2026-10-24/` is no rollback for this change. #77's own rollback runs
  only after this one, because a fresh retrieve no longer equals its `after/`.
- Nothing is deleted: the copies stay in Decommissioned.

## Result

All on 2026-11-04 UTC, VPN off, on Ryan's go.

- Step 1: D3 (`01ZRP000006k2D32AI`, file `vbKFAhzWWcXLOmmkSckbvWkgmwtdrM`, runs as a specified
  user) and items 9 (`00ORP000004RJZC2A4`), 10 (`00ORP000004RJZD2A4`) and 11
  (`00ORP000005uf412AA`): D3, 9 and 10 are identical to `fresh_2026-10-26/`; item 11 differs from
  it but equals `build_item11/` (its 2026-10-26 redeploy, record count on). No drift.
- Step 2: D3 to `01ZRP00000BV0bh2AD` (folder Decommissioned_Dashboards `00lRP000007iOiYYAU`,
  08:12:29Z), item 9 to `00ORP000009p0dV2AQ` (08:12:36Z), item 10 to `00ORP000009p0f72AA`
  (08:12:42Z), each dry run first, all before the deploy.
- Step 3: item 11's copy by the API was refused (HTTP 400, ledger row `failed`). The metadata
  copy: check-only `0AfRP000002j94Q0AQ`, deploy `0AfRP000002j9af0AA` at 08:47:22Z, giving
  `00ORP000009p0jx2AA`, read back in Decommissioned with the description "copy of
  00ORP000005uf412AA, #198" (files in `item11_copy/`). The RUNBOOK's Decommissioned part now
  says a report with a bucket field is copied by metadata.
- Step 5: check-only `0AfRP000002j9h70AA` Succeeded, 4 of 4.
- Step 6: deploy `0AfRP000002j9ij0AA` Succeeded, 4 of 4, 0 errors, 08:56:08Z.
- Step 7: the four files in `after/` are byte-identical to `build/`.
- Step 8: D3 refreshed at 08:56:51Z, 3 components DATA. The dashboard Id is `01ZRP000006k2D32AI`
  and its title "Club Observation Dashboards"; the three component titles and report labels are
  as in Build.
- Step 9, September 2026:
  - September 2026 (the last complete month), SOQL with the same filters (`In_Reporting_Year__c
    = true`, `Month__c = 'September'`, the account not blank, its name not containing "test"):
    item 9 shows 29 Monthly Reports, equal to the SOQL's 29 (`did_you_submit_your_GC_observation_form__c`
    Yes 24, No 4, NA 1); item 10 shows 95 sessions observed, equal to the SOQL sum of
    `GC_sessions_did_you_observe_last_month__c` over 45 Monthly Reports; item 11 shows 45 Monthly
    Reports, equal to the SOQL's 45, of which 29 with at least one session observed (Observed
    Yes). The RUNBOOK's queries carry `Year__c = 2026` as well, which the one-month rule of its
    tests asks for; it changes nothing under the reporting year, and the three queries returned the
    same 24/4/1, 45/95 and 29 when run again with it.
  - The RUNBOOK's earlier September figures, from the check of 2026-10-24 (item 9: 23 Yes and 3
    No; item 10: 93 sessions over 42 Monthly Reports; item 11: 27 partners who observed and 15
    with 0), are older. The deploy does not touch records, so the difference (item 9 26 Monthly
    Reports to 29, with a first NA; item 10 42 to 45; item 11 27 to 29 who observed) is Monthly
    Reports for September filed or corrected after 2026-10-24 (not checked); it is not a
    before-figure of this change.
  - No grouping label in any component reads 2025 (0 of 78 labels).
  - The live Partner Manager filter has 5 options, none of them the former PO's (6 before); the
    Month filter has 12.
- GLOW's question: the count question `many_clubs_do_you_still_need_to_observe__c` has no answers in 2026
  and item 11 does not use it (Context); the report stays and the reply to GLOW (#201) says so.

`data/sf_glow_review_2026-11/observations/` (before/, copies/, build/, after/, item11_copy/) is in
the ticket worktree, untracked: move it to the main checkout before land.
