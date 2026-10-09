---
title: New partners choose their region on the Club Roster Form
author: Ryan
status: in-progress   # built 2026-09-02 and deployed with the 2026-09-30 push; the one-time menu migration is not recorded (BACKLOG 38)
created: 2026-09-02
---

# Intent: required Region picker on the Club Roster Form

## Problem

A brand-new partner's region has no source: the New Club branch asks a free-text
"Country where this club meets" that nothing reads, so every roster row of a new
partner arrives with a blank region — and active rows with a blank region reach
NO attendance form. 7 of the 8 launch-week clubs (Fundación Bibliotec ×6,
RAWSA/Tamkeen ×1) sat on no form until staff set the regions by hand on
2026-09-02.

## Proposed outcome

The "Your organization" page (seen only by new partners) asks a REQUIRED
"Region where this club meets" picker whose choices are exactly the four
regions the sync routes on: Africa, Asia, Latin America, U.S. A new partner's
clubs land on a regional attendance form in the same automatic sync run that
creates them. Staff keep the last word: the Partners tab still wins wherever it
has a value, and a wrong pick is corrected there (then GLOW → Refresh regions).

## Affected users and systems

New partners (one extra required dropdown, replacing the Country question);
staff (fewer "Partner has no region" ReviewQueue rows); the Google Club Roster
Form; `FormHandlers.gs` / `Roster.gs` / `RosterOps.gs`; the Partners tab;
downstream, the automatic sync and the regional Jotforms. The Salesforce
mapping is untouched.

## Constraints

- Choices spelled exactly as the Jotform regions: `Africa`, `Asia`,
  `Latin America`, `U.S` (one dot, no trailing dot) — parity with
  `glow/forms.py REGIONS` is test-pinned.
- Precedence: the Partners tab beats the form answer; the form answer beats the
  frozen derived map (`Regions.gs`), which cannot know a new partner.
- The chosen region must survive **GLOW → Refresh regions**, so it is persisted
  to the Partners tab, not only to roster rows.
- The live form is changed by code only (a one-shot, idempotent menu item); no
  new Google service (no OAuth scope growth, no re-auth window); never a test
  submission on the live form.
- Must not collide with `docs/intent/2026-09-01-duplicate-club-guards.md`
  (same page, same handler): region resolution stays a pure helper that the
  future hold/resolve flow keeps calling.

## Open questions

None — precedence, wording and placement decided 2026-09-02
(`docs/DECISIONS.md`). The question title is one string in `Config.gs`
(`Q.REGION`) if the wording should ever change.
