---
title: Mentors (D4) - 2026 only, a Month filter, the former PO off the filter
author: Claude (ticket #199, with Ryan's decisions of 2026-11-02)
status: done      # ticket #199; deployed 2026-11-05 09:41 UTC on Ryan's go (0AfRP000002jIIz0AM, 6/6), read back, checked against SOQL
done: 2026-11-05
created: 2026-11-02
intent: GLOW's review of 2026-11-02 (epic #194) - 2026 data only, a filter by month, the former PO off the filter
---

# Plan: D4 "Mentors" after GLOW's review

Ticket #199 (epic #194), after #195 ([plan](2026-11-02-sf-reporting-year.md)) and #152
([plan](2026-10-25-sf-dash-training.md)). D4 is the dashboard "Mentors" (`01ZRP000006quAj2AI`);
its components show items 12-16 of `glow/sf_keep_list.csv`. RUNBOOK `### GLOW Club Training`
holds the state and the rollback.

## Build

`data/sf_glow_review_2026-11/training/build/`, made by `make_build.py` from a copy of the
retrieve `before/`: each report's `Period__c equals LAST_N_MONTHS:12` becomes
`In_Reporting_Year__c equals true`; D4's Partner Manager filter loses the former PO's option
(6 options to 5); a Month filter on `DHIS2__c$Month__c`, 12 options, on all 5 components.

## Rollout (live; each write on Ryan's go)

VPN off (`route -n get default` shows `en0`), in the main session.

1. Retrieve live into `data/sf_glow_review_2026-11/training/before/`: D4 (`01ZRP000006quAj2AI`)
   and the reports of items 12 (`00ORP000009kXev2AE`), 13 (`00ORP000004RJZE2A4`), 14
   (`00ORP000004RJZ82AO`), 15 (`00ORP000004RJZ62AO`) and 16 (`00ORP000004RJZ72AO`). Compare it with
   #152's `after/`; a difference stops for Ryan.
2. Copies into Decommissioned before anything changes, each on Ryan's go after its dry run:
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_glow_review_2026-11/training/copies --kind dashboard --id 01ZRP000006quAj2AI --tag "#199" --apply`,
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_glow_review_2026-11/training/copies --kind report --id 00ORP000009kXev2AE --tag "#199" --apply`,
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_glow_review_2026-11/training/copies --kind report --id 00ORP000004RJZE2A4 --tag "#199" --apply`,
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_glow_review_2026-11/training/copies --kind report --id 00ORP000004RJZ82AO --tag "#199" --apply`,
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_glow_review_2026-11/training/copies --kind report --id 00ORP000004RJZ62AO --tag "#199" --apply` and
   `python3 tools/sf_report_folders.py copy --vpn-off --dir data/sf_glow_review_2026-11/training/copies --kind report --id 00ORP000004RJZ72AO --tag "#199" --apply`.
3. Make `build/` from a copy of `before/` with `make_build.py` (Build, above).
4. Check-only from `build/`: `sf project deploy start --dry-run -o glow -d force-app`, on Ryan's go.
5. On Ryan's go, deploy: `sf project deploy start -o glow -d force-app` from `build/`.
6. Read back: retrieve D4 and the five reports into `after/` and compare `after/` with `build/`:
   no differences beyond Salesforce's normalisation.
7. Check against SOQL for the last complete month: item 16's answers equal
   `SELECT Did_you_meet_with_mentors_as_a_group__c, COUNT(Id) FROM DHIS2__c WHERE In_Reporting_Year__c = true AND Period__c = LAST_MONTH AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') AND Did_you_meet_with_mentors_as_a_group__c != null GROUP BY Did_you_meet_with_mentors_as_a_group__c`.

## Rollback

DECISIONS 2026-10-16, each write on Ryan's go after a check-only, VPN off.

- D4 and the reports of items 12-16 are restored by a deploy, and their copies in Decommissioned
  are the record of what they were. A copy saved back would be a separate report: D4's
  components point at the reports themselves.
- D4's and each report's deploy is one of two, after a check-only: a fresh retrieve of it, edited back where
  #199 changed it; or their files in `data/sf_glow_review_2026-11/training/before/`, only
  while a fresh retrieve of them equals `after/` (DECISIONS 2026-10-16).
- Never from an older build or retrieve (DECISIONS 2026-10-16): never #152's or #78's folders.
  Nothing is deleted.

## Result

All on 2026-11-05 UTC, VPN off, on Ryan's go.

- Step 1: the fresh retrieve (09:2x, 6 members) equals #152's `after/` for D4 and item 16; items
  13-15 equal #152's `before/`.
- Step 2 (09:29-09:30): the copies, a record, in Decommissioned: D4 `01ZRP000006quAj2AI` to `01ZRP00000BVvq52AD`, item 12 `00ORP000009kXev2AE` to `00ORP000009pbLJ2AY`, item 13 `00ORP000004RJZE2A4` to `00ORP000009pbMv2AI`, item 14 `00ORP000004RJZ82AO` to `00ORP000009pbOX2AY`, item 15 `00ORP000004RJZ62AO` to `00ORP000009pbQ92AI`, item 16 `00ORP000004RJZ72AO` to `00ORP000009pbRl2AI`.
- Step 4: check-only `0AfRP000002jIHN0A2` Succeeded, 6 of 6.
- Step 5: deploy `0AfRP000002jIIz0AM` Succeeded, 6 of 6.
- Step 6: `after/` equals `build/` byte for byte (0 differing lines in all 6 files). D4 refreshed
  09:42 UTC: all 5 components DATA, 110 grouping labels, none with 2025; Partner Manager filter 5
  options, Month filter 12.
- Step 7: item 16 for September 2026 (the last complete month) equals SOQL, 44 answered, Yes 38
  and No 6. Every month January to October equals SOQL (October still coming in, for example
  3 Yes and 2 No); the query is the one above grouped by `CALENDAR_MONTH(Period__c)` in place of
  `Period__c = LAST_MONTH`.
