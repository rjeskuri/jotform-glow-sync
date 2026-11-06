---
title: OMID Foundation as an Asia partner - Partners tab, the Jotform Attendance dashboard's Partner filter, the partner map
author: Claude (ticket #212, on Ryan's request of 2026-11-06)
status: done      # ticket #212; Partners!52 and deploy 0AfRP000002jOD70AM on 2026-11-06 UTC on Ryan's request; the Club Roster Form dropdowns are Ryan's step (pending)
done: 2026-11-06
created: 2026-11-06
intent: Ryan, 2026-11-06 - "Can you create OMID Foundation and make it available in the Asian form? Please make sure the Salesforce links to it properly."
---

# Plan: OMID Foundation as a partner

Ticket #212 (epic #68). Ryan, 2026-11-06: "Can you create OMID Foundation and make it available
in the Asian form? Please make sure the Salesforce links to it properly." Procedures: RUNBOOK
"Attendance dashboard in Salesforce" and "New clubs' accounts, automatically".

## Context

- OMID Foundation's coordinator said five clubs registered on 2026-10-13 never reached Jotform.
- Every sheet tab, the whole Jotform account (2026-10-11 to 2026-10-19: 275 submissions, all
  attendance forms) and Salesforce held no OMID Foundation submission.
- OMID Foundation was never a Jotform partner: no Partners row, no clubs. Its Salesforce
  Household account `001RP000002nJZiYAM` (OMID Foundation) has a Monthly Report every month.
- Three places name a partner, each changed here: the sheet's Partners tab (its region, which
  puts its clubs on the Asia form and the Club Roster Form's dropdowns), the Jotform Attendance
  dashboard's Partner filter (`01ZRP00000BE2TR2A1`), and `glow/sf_partners.csv` (the partner map
  the automatic club accounts read, so a new OMID club gets `001RP000002nJZiYAM` as its parent).
- **Unchanged:** the not-submitted lists (OMID Foundation uses Jotform, so its clubs belong on
  them); the interactive dashboard's `partners.json` (#81-#83 on hold); `appsscript/Regions.gs`
  (the Partners tab wins over it, CLAUDE.md rule 8).
- Work folder (owner only, untracked, never committed; its contents are never quoted):
  `data/sf_omid_partner_2026-11-06/`, with `partners_before.csv`, `before/`, `build/` and
  `after/`.

## Rollout

Each live write on Ryan's request in the session; Salesforce with the VPN off.

1. Back up the Partners tab into `data/sf_omid_partner_2026-11-06/partners_before.csv`, then
   append the row `OMID Foundation | Asia` to the Partners tab.
2. `python3 tools/auto_sync.py` (dry run): every enabled region in-sync, the Partners export
   holding the new row.
3. Ryan: GLOW → Google Forms → Update form dropdowns from the Roster, so the Club Roster Form
   offers OMID Foundation.
4. Retrieve the Jotform Attendance dashboard into `before/` and compare it with #209's round-3
   `after/`; build one more Partner filter option, OMID Foundation, in its sorted place, into
   `build/`.
5. Check-only of `build/`, then the deploy; retrieve into `after/` and compare it with `build/`.
6. Refresh the dashboard and read every component's status and the Partner filter's options.
7. This pull request: `glow/sf_partners.csv` gains `OMID Foundation,001RP000002nJZiYAM,OMID
   Foundation`. Once it lands, `SF_SYNC=apply` creates each new OMID club's account under that
   parent on the runner's next run.

## Rollback

- The Partners row: clear row 52 of the Partners tab by hand (OMID Foundation has no clubs yet,
  so nothing else follows it).
- The dashboard: a deploy from a fresh retrieve with the OMID Foundation option removed, check-only
  first, VPN off, on Ryan's go, and only while that fresh retrieve equals
  `data/sf_omid_partner_2026-11-06/after/` (DECISIONS 2026-10-16). Never a deploy of an older
  build or retrieve.
- The partner map: revert the `glow/sf_partners.csv` line; a club account already created under
  `001RP000002nJZiYAM` stays (RUNBOOK "New clubs' accounts, automatically").

## Result

2026-11-06, every step on Ryan's request in the session.

- Partners tab: the row `OMID Foundation | Asia` appended at Partners!52, about 06:13 UTC, after
  the tab's backup in `data/sf_omid_partner_2026-11-06/partners_before.csv`. The
  `auto_sync.py` dry run afterwards: Africa, Asia and Latin America in-sync, U.S skipped (form
  disabled); its Partners export holds the row.
- Club Roster Form dropdowns: **pending Ryan** - GLOW → Google Forms → Update form dropdowns from
  the Roster, not yet confirmed when this was written.
- Salesforce, the Jotform Attendance dashboard `01ZRP00000BE2TR2A1`: a fresh retrieve at API 67.0
  equals #209's round-3 `after/` (no change since). The build adds one Partner filter option,
  OMID Foundation, in its sorted place: 43 → 44 options. Check-only `0AfRP000002jOBV0A2` (1/1),
  deploy `0AfRP000002jOD70AM` (1/1), 2026-11-06 06:19:14-06:19:28 UTC. `after/` is byte-identical
  to `build/`. Refresh: the 17 report components DATA, plus the embedded dashboard component (no
  data status); the Partner filter has 44 options, OMID Foundation among them.
- `glow/sf_partners.csv` (this pull request, #212): 50 partners. Until it lands on main, an OMID
  club gets the runner's ATTENTION "partner not in glow/sf_partners.csv"; `SF_SYNC=apply` creates
  the Club account on the first run after the land. Keep-list check: "OMID Foundation" does not
  contain "test".
