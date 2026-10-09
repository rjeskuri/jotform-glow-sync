---
title: Clubs that do not report through Jotform leave the attendance forms, without leaving the roster
author: Ryan Eskuri (decisions of 2026-10-06, captured by Claude)
status: proposed
created: 2026-10-06
---

# Intent: clubs off Jotform

## Problem

Forty-nine clubs sit on the attendance forms although nobody will ever submit for them there (a
fiftieth exists in Salesforce only):

- Three Africa partners - **Education and English for You** (6 clubs, 114 active girls),
  **Tumaini La Maisha** (16 clubs, 320) and **Ng'aa Maskani** (16 clubs, 317) - report attendance
  to GLOW directly (their Monthly Report, filed per partner per month), not through Jotform. Their
  38 clubs are entries in the Africa form's Club picker, each with a roster of the girls' names, and
  751 roster checkboxes nobody ticks. In Salesforce they have 0 attendance batches since launch
  (Tumaini La Maisha: 2 February pilot batches), so all 38 pad the "clubs without attendance" list.
- The **U.S form has 0 submissions since 2026-09-01**. Its 11 clubs (6 partners, 155 girls; a
  twelfth U.S club exists in Salesforce only) are not expected to report this way for now.

The only way the pipeline knows today to keep a club off every form is a **blank region**
(CLAUDE.md rule 6): it also blanks the club's attribution in the sheet, raises an ATTENTION on
every automatic run and a ReviewQueue item - it says "fix me", not "intended". And the sync does
not take a club off the Club picker when it leaves the active roster: a roster question that the
export no longer claims is kept with its last roster ("on the form but not in the sheet export -
keeping its current roster"), so a retired club stays pickable, showing girls who have left.

## Proposed outcome

- A partner marked **not on Jotform** on the sheet's Partners tab has no entry in any attendance
  form's Club picker; its girls stay active and enrolled in the Roster (they count as enrolled,
  they are in the Club Roster Form, they keep their ids). Flipping the mark back puts the clubs on
  the form again within the hour.
- Proposed, awaiting Ryan's answer (open question below): a club with no active girl leaves the
  Club picker the same way (its roster question stays on the form, hidden, as every question does:
  "deactivate, never delete"). Built behind a constant that ships off, so nothing beyond the
  decisions above changes until he says yes.
- The 11 U.S clubs are deactivated in the Roster (rows inactive with a removed date, the way the
  Radiant Girls rows were on 2026-09-28; a scripted undo puts the same rows back) and the U.S form
  is disabled, after a backup. The automatic sync and the audit tool treat a disabled form as "not
  synced", not as a failure. The path back (a U.S club starting) is written down.
- The audit (`form_status.py`) knows a retired roster from a broken one.

## Affected users and systems

Mentors of the three partners and of the U.S clubs (nothing to do; their coordinators are told the
form is not for them); GLOW staff (one new Partners-tab column; the Club Roster Form's dropdowns
for the U.S partners read "(no active clubs)"); the Africa form, the template and the U.S form;
`sync_attendance_form.py`, `tools/auto_sync.py`, `tools/form_status.py`, two new tools
(`tools/deactivate_clubs.py`, `tools/disable_form.py`); `appsscript/Roster.gs` (the column) and the
mentor e-mails' "attendance form" line; Salesforce only indirectly (nothing written; the 50 clubs
stay in "clubs without attendance" until plan 2's reports).

## Constraints

- Girls' names never in logs, docs or commits; the roster questions are never deleted
  (DECISIONS 2026-08-25); the three partners' girls stay **active**.
- Dry run first, backup before every live write, re-read and compare after, refuse rather than
  guess; `--apply` behind the live gate and Ryan's go; `AUTO_SYNC_APPLY=0` for the form-side window.
- Every form-side step waits for session -54's rollout window to close (it is writing the module
  dropdowns and the names dictionary on the same forms, and changing `tools/form_status.py`).
- Question 5 keeps sending the same text for every club that stays; a retired club's Salesforce
  Account keeps its name (plan 4's aggregate batches land on it); a retired club that comes back
  never changes what it sends unattended (a shared name is a hand step, as every question-5 change
  is).
- `PARTNER_COLS` exists in `appsscript/Roster.gs` and `tools/build_roster_offline.js`; the new
  column is mirrored on the Python side and parity-tested (CLAUDE.md rule 7).

## Open questions

- Name and values of the marker column (proposed: `jotform`, values `yes` / blank / `no`).
- Whether "no active girl = off the picker" should apply to every region (proposed: yes, and only
  once the club's rows have been inactive since before the day of the run, so a roster replaced in
  two steps on the Club Roster Form does not flicker off the picker; it also closes the stale-roster
  gap above).
- Whether the retired rosters' option lists (751 names on the Africa form, 155 on the U.S form) are
  later blanked (a write to a checkbox question that has never been tried) or left as they are
  (proposed: left, for now).
- How the U.S form is disabled: through the API (`status` is a form property, read 2026-10-06;
  writing it is unverified) or by Ryan in the builder.
