---
title: The Club Roster Form's dropdowns refresh hourly, by an Apps Script trigger
author: Claude (ticket #228, PR #234)
status: accepted      # ticket #228; the push and the install wait on Ryan's go
created: 2026-11-19
intent: ticket #228 - a roster change made by a tool reaches the Club Roster Form without someone running the menu item
---

# Plan: Hourly Club Roster Form dropdown refresh

Ticket #228. Decision: DECISIONS 2026-11-19. Procedures: RUNBOOK "Apps Script deploy", "Rolling
back `appsscript/`"; the push itself follows `.claude/skills/deploy-appsscript/SKILL.md`, which is
not repeated here.

## Context

- A club renamed, deactivated or moved by a tool changes the Roster only; the Club Roster Form kept
  offering the old list until someone ran GLOW → Google Forms → Update form dropdowns from the
  Roster.
- The change: `installTriggers` also installs a time-driven trigger for `syncFormChoicesHourly`
  (every hour). It runs `syncFormChoices(true)` under the document lock, skips quietly when the
  lock is busy, and writes an Audit row only when a dropdown changed. No new Google service, so no
  new OAuth scope; the handler is a new name, not a renamed one.
- Until the push and the install, nothing changes: the menu item is the only way.

## Rollout (live)

On Ryan's go, after the PR has landed and `appsscript/` is committed and clean.

1. Offline: `make check` ends `CHECK PASSED`, its `gs:` line `8 services, 0 unknown calls`.
2. Backup, per the skill: a clean, committed `appsscript/` is the gate's backup for the push; the
   rollback target is the newest `appsscript-deployed-*` tag (`git tag -l
   'appsscript-deployed-*'`), so note it before the push.
3. Push (Node 18, a quiet moment, Ryan's word): `nvm use 18`, then `npm run clasp:push` in the
   checkout's root. The push alone adds no trigger and changes no handler the live project calls.
4. Ryan runs **GLOW → Google Forms → Install triggers** once. He is the owner and accepts Google's
   authorization prompt if one appears. `installTriggers` deletes and recreates the form-submit
   router, the Monday e-mail and `syncFormChoicesHourly`, and writes an Audit row "installTriggers".
5. Check the Triggers panel (Apps Script editor, clock icon): three triggers, `onAnyFormSubmit`
   (from spreadsheet, on form submit), `sendSfPendingDigest` (week timer, Monday, 8 AM) and the
   new `syncFormChoicesHourly` (time-driven, hour timer, every hour), each once.
6. The next hour (and the one after): the Executions list shows `syncFormChoicesHourly` with status
   Completed. A run that changes nothing writes no Audit row, so the Executions list is the proof
   of life, not the Audit tab.
7. The proof that it does its work: after the next real Roster change (a club rename, a
   deactivation or a move), the next hourly run writes an Audit row "syncFormChoices: N
   dropdown(s) updated", and a Preview of the Club Roster Form (never a submit) shows the change.
   The menu item still does it at once.
8. Tag (ask Ryan first): `git tag appsscript-deployed-YYYY-MM-DD <commit pushed>`.

## Rollback

- Fastest, no new push: in the Triggers panel delete the `syncFormChoicesHourly` trigger. The
  form-submit router and the Monday e-mail are untouched and the menu item keeps working.
- Code back: the skill's Rollback (check out `appsscript/` from the previous
  `appsscript-deployed-*` tag, push it with Node 18 in a quiet moment, never below the floors, then
  `git checkout HEAD -- appsscript`). The older `installTriggers` does not know
  `syncFormChoicesHourly` and does not delete it, so after that push delete the hourly trigger by
  hand in the Triggers panel (a trigger whose function no longer exists fails every hour), and run
  Install triggers again only if the other two are missing.

## Risks

- The hourly run takes the document lock for a moment; a form response or problem report arriving
  then waits (the router waits up to 120 s). Mitigation: the run waits at most 30 s and skips when
  the lock is busy, so it never blocks the router; the next hour catches up.
- An hour's delay remains: the Club Roster Form can offer a retired club until the next run. The
  menu item closes it at once (the RUNBOOK's club procedures say so).
- A new Google service would add an OAuth scope and fail the submit trigger hard: none is added
  (`make gs` fails on a 9th).

## Proof

- `harness-red run` for the ticket (`hourly_roster_refresh`, `load_gs`, `club_tools`, `runbook`),
  `make gs`, `test/gs_parity_test.py`; the live read-back is Rollout steps 5 to 7.

## Result

Pending: not pushed, not installed. To be filled in with the push commit, Ryan's go, the install
time (UTC), the Triggers panel read-back and the first Executions entries.
