---
title: Otra Cosa's and CCCYD's club renames, Otra Cosa's three combined lists retired, obsolete clubs off the club lists
author: Claude (ticket #216, on Ryan's go of 2026-11-18)
status: done      # ticket #216; every write on 2026-11-18 UTC on Ryan's go; BATCH-000500's date (BACKLOG 60) still open
done: 2026-11-18
created: 2026-11-18
intent: Ryan, 2026-11-18 - "Go on 1. same for 2 and yes for 3 retire those 3 and make sure they don't show up in jotform as options and don't show up or impact reporting in salesforce"
---

# Plan: Otra Cosa and CCCYD renames, three lists retired

Ticket #216. Procedures: RUNBOOK "Renaming a club", "Deactivating a club", "Duplicate and
obsolete records in Salesforce".

## Context

- Otra Cosa Network confirmed its 8 lists and their names (Ryan, 2026-11-13 and the partner's
  e-mail of 2026-11-18). It has 11 on the Roster; the three combined lists "Cerrito", "Las
  Lomas" and "San Carlos" are the extra ones. Records 2026-11-18: Las Lomas never reported
  (0 Salesforce contacts); San Carlos last on 2026-09-09; Cerrito once, 2026-03-15. Their girls
  also on a kept list: San Carlos 50 of 50, Las Lomas 48 of 54, Cerrito 11 of 26 (counts on #216).
- Two CCCYD clubs carry a person's name; the partner's own enrollments name them "Hope builders
  girls club" and "AMAZING GIRL CLUB" (#215).
- Salesforce held a partner-less "Las Camelias Primaria" (`001RP00000nMZXfYAO`: 22 contacts, one
  batch of 2026-03-28, already flagged obsolete) whose name, capitals ignored, is the new name of
  Otra Cosa's "Las Camelias". Ryan chose to rename it out of the way (2026-11-18).
- Work folders (owner only, untracked): `data/sf_renames_2026-11-18/` (the nine accounts before
  and after), `data/rename_club/<stamp>/`, `data/deactivate_clubs/<stamp>/`,
  `data/sf_obsolete_filter_2026-11-18/` (`before/`, `build/`, `after/`), `backups/`.

## Rollout

1. Salesforce, one record per call (write connector): the stray renamed "Las Camelias Primaria
   (marzo 2026)"; the five club accounts renamed; "Las Lomas" and "San Carlos" flagged
   `Obsolete_Record__c` ("Cerrito" already was).
2. `tools/rename_club.py --apply` for the five clubs (Roster, ClubRegistry, SF Pending, Audit, the
   roster question on the region's form and, for the Otra Cosa clubs, the template).
3. `tools/deactivate_clubs.py --apply` for the three combined lists (the guard: none named in a
   submission since 2026-10-19).
4. The sync with `--apply --q5-change-ok` on the Latin America and Africa forms (with the Partners
   export); `form_status.py` and `tools/auto_sync.py --region` dry runs.
5. The three club-list reports of the Jotform Attendance dashboard (`Clubs_Not_Submitting_Last_14_Days`,
   `Clubs_Not_Submitting_Since_1_Sept`, `Jotform_Clubs_No_Attendance_Last_Month`) gain the filter
   `Account.Obsolete_Record__c` equals false, so a retired (obsolete) club is not listed as not
   submitting. Check-only, deploy, retrieve and compare.

## Rollback

- Accounts: the old names and flags in `data/sf_renames_2026-11-18/before.json`, one record per call.
- Sheet and forms: `tools/rename_club.py` the other way (or the saved tabs and
  `restore_conditions.py`); `tools/deactivate_clubs.py --undo data/deactivate_clubs/<stamp> --apply`;
  then the sync with `--q5-change-ok`.
- Reports: a deploy from a fresh retrieve without the filter, only while it equals `after/`.

## Result

2026-11-18, on Ryan's go in the session.

- Salesforce: the six account renames and two flags read back as written. The connector refused
  the stray's rename the first time (not yet in Ryan's go); it was written after Ryan chose it.
- `rename_club.py`: all five renamed and verified (Roster 14, 29, 18, 20, 24 cells; ClubRegistry
  1 each; SF Pending 1 each for the CCCYD clubs; forms renamed and verified).
- `deactivate_clubs.py`: Cerrito 26, Las Lomas 54, San Carlos 50 rows set inactive, removed_date
  2026-11-18. Their roster questions leave the Club picker from the next day's sync
  (`glow.sync.RETIRE_INACTIVE`).
- Sync applied: Latin America (picker 38 clubs, 74 rules), Africa (picker 197 clubs, 233 rules);
  afterwards `auto_sync.py --region`: both `in-sync`; `form_status` Latin America CLEAN.
- The template's question 5 for the three Otra Cosa renames is not yet applied: its sync also
  plans an unrelated catch-up (11 new rosters, many updates) and is left for its own run.
- Reports: check-only `0AfRP000002kRor0AE` (3/3), deploy `0AfRP000002kRqT0AU` (3/3, 07:04:45
  UTC); `after/` equals `build/`.
- Attendance already submitted keeps its account: the combined clubs' past sessions (San Carlos 2,
  Cerrito 1) still count in the attendance totals; they were real sessions.
- Still to do: the template's sync; the dropdown refresh in the sheet (GLOW → Google Forms →
  Update form dropdowns from the Roster), Ryan's; checking the next day's sync shows the three
  rosters retired; BATCH-000500's date (BACKLOG 60).
