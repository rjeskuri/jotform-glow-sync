---
title: Catch "new club" submissions that duplicate a club we already have
author: Ryan Eskuri (captured by Claude)
status: proposed
created: 2026-09-01
---

# Intent: duplicate-club guards on the Club Roster Form

## Problem

Partners misunderstand the form and submit a **new club** for a club that is already enrolled —
a different spelling, a different casing convention, or their organisation retyped under "my
organization is not in this list". Today an exact (partner, club) match is treated as a
re-enrollment (safe), but a near-duplicate creates a second club: new girl ids for the same
girls, a second roster question on the attendance form, and two Salesforce accounts.

## Proposed outcome

1. **In the form:** on the "Enroll a NEW club" branch, after the partner is chosen, the
   partner's enrolled clubs are shown and a required question asks "Is your club one of these?"
   — *yes* picks it and the submission is treated as a roster update; *no* continues to the
   new-club fields. (`Forms.gs` already builds per-partner sections and `syncFormChoices` keeps
   the lists current.)
2. **In the handler (the guarantee):** a new-club submission is **held, not imported** — FormLog
   `HELD: possible duplicate of '<club>'`, a ReviewQueue row with the candidates and what to do,
   the response row untouched, no Jotform sync triggered — when any of these fire:
   (a) the club name fuzzy-matches an existing club of the same partner (normalised similarity
   ≥ 0.8, containment, or a shared distinctive token: catches "Setidevi G.L.O.W club , Sokhel"
   vs "Setidevi GLOW Club Sokhel");
   (b) ≥ 50 % of the submitted names already sit in one existing club's active roster, any
   partner (catches a retyped organisation name);
   (c) a typed "other" organisation fuzzy-matches a known partner;
   (d) the exact same club name under a *different* partner — imported (legitimate cases exist)
   but flagged for review.
   Staff resolve in the ReviewQueue `resolved` column with `SAME: <club>` or `NEW`, and "Process
   any missed form responses" re-processes held rows accordingly (the pattern `ERROR:` rows use).
3. Extra checks at the same time: a girl already active in another club of the same partner
   (flag); a submitted roster much shorter than the existing one (already reported as
   "vanished", never removed).

## Affected users and systems

Partners (one more question on the form); staff (ReviewQueue resolutions); `Forms.gs`,
`FormHandlers.gs`, `RosterOps.gs` (pure matching logic, unit-tested in
`test/forms_logic_test.js` including the known real cases), the ReviewQueue and FormLog tabs.

## Constraints

- Held responses are kept for record keeping; nothing is imported until resolved.
- The form change alters the live Google Form (a menu action, idempotent) — after launch
  settles; the handler change ships first (a `clasp push`).
- Never merge two clubs automatically; only staff decide "same".

## Open questions

- Similarity thresholds: start at 0.8 and tune on the ReviewQueue.
- Whether holding should also apply to the roster-modification branch when the chosen club has a
  near-duplicate sibling (probably: report, do not hold).
