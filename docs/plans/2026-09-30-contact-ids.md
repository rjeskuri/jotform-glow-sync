---
title: The names list sent to Salesforce is never empty and never another club's
author: Claude (read-only investigation of Jotform's runtime and of all September submissions, a design and two adversarial reviews, 2026-09-30)
status: accepted         # Ryan 2026-09-30: "Go on all 4 fixes"; then "Guard first, then back-fill" — this plan is fixes 2 and 3; every live step needs his go
created: 2026-09-30
intent: docs/intent/2026-09-01-club-picker.md (the attendance form sends the right girls for the right club)
---

# Plan: question 18 (Contact_IDs) equals the ticked girls of the one visible roster, and at least one girl is ticked

## Context
The Jotform → Salesforce integration sends question 18 (`contact_ids`, a hidden field filled by one
calculation over every roster) as the list of girls who attended. Re-measured on all 484 September
submissions (2026-09-30, counts only):
- **No girl ticked: 64 submissions (13%).** Sent live, each is stored in Salesforce as an empty
  *Success* batch that blocks the real batch for that club and day (one arrived on 2026-09-30,
  14:19 UTC, after the reconnect).
- **Girls ticked but question 18 empty: 17 submissions (207 names never sent).**
- **Another club's girls in question 18: 2 submissions (24 extra names)**, one of them after the club
  guard went live — it is the path the guard's warning sends a mentor down (two clubs picked, girls
  ticked in both, one club removed).
- Root cause of the last two, reproduced in headless Chrome: **rule order.** On a change of the Club
  picker Jotform runs the question-18 calculation *before* it shows or hides the rosters, and never
  again. A restored page (Back) shows ticks with an empty question 18.
Ryan's order (2026-09-30): this guard first, then the September back-fill; the names-dictionary repair
and the module values follow the back-fill (their own plan).

## What changes
**1. At least one girl (lead design: required rosters).** Every roster question gets Jotform's own
`required` flag, written by the sync (on create, and as an update where it is missing). Jotform
validates at submit time, on the checkboxes themselves, only the roster that is visible (a question
hidden by a rule is not validated), and shows its own "required" message in the form's language. It
does not depend on question 18, so it also holds on a restored page. *To be proven in a browser
before it is relied on* (a local copy of the live page in headless Chrome: no club picked; a club
picked and nothing ticked; one girl ticked; two clubs picked; Back). **Fallback** if that proof
fails: a generated field rule `{picker filled, question 18 empty} → hide and disable Submit, show a
hint`, built like the club guard.

**2. Question 18 is recalculated after the rosters change (generated rules).** In
`build_conditions` the Contact_IDs rule becomes the first rule (Jotform walks a field's rules last to
first, so it then runs after every show/hide), its id minted first, and the Club picker is added to
its operands (never to its equation) so the picker's own change event re-runs it as well. Order is
the fix; the operand is a supplement (a restored page fires no bubbling event). One conditions write
per form, no question touched by this part. Constants in `glow/sync.py`
(`CONTACT_IDS_FIRST`, `CONTACT_IDS_PICKER_OPERAND`).

**3. Audits and the runner.** `tools/form_status.py`: NOT CLEAN when the Contact_IDs rule sits after
a roster rule, lacks the picker operand, holds anything but one `{qid}` per roster, when a roster
rule tests a field that is not in the Contact_IDs rule, or when a roster is not required — each
expectation derived from the constants, so a fallback does not leave every form dirty.
`sync_attendance_form.py` warns with a fixed fragment when the live rules are in the old order;
`tools/auto_sync.py` raises ATTENTION for it and **refuses to apply that region** (so a forgotten
`AUTO_SYNC_APPLY` cannot roll the change out unattended). A bulk "make every roster required" is
likewise by hand: the runner sets it only on rosters it creates or already updates.

**Not in this plan:** the names-dictionary repair (55 roster options the forms' own translation
dictionary alters) and `calcValues` on the module dropdowns — after the back-fill. The language
switcher with two clubs picked (it un-picks one silently and lifts the club guard) — recorded as a
residual, needs its own design (a single-select picker is the structural answer).

## Files
`sync_attendance_form.py` (`build_conditions` section C; the roster create/update payloads; the
warning), `glow/sync.py` (constants), `tools/form_status.py`, `tools/auto_sync.py`,
`test/python_test.py` (rule order and operands, required rosters, audits in all constant
combinations, the runner's refusal), docs (RUNBOOK "One club per submission" gains the two checks and
the browser scenarios; ARCHITECTURE; DECISIONS; BACKLOG 35 and a new item; the jotform-api skill:
the rule walk, the checkbox reader, required + hidden).

## Rollout (each step Ryan's go; `AUTO_SYNC_APPLY=0`, verified, for the window)
1. Build on a branch, three adversarial reviews (runtime in a browser; live safety; tests/docs), fixes.
2. Template: backup → dry run (exactly: `REPLACE conditions` with `1 new, 1 dropped`, and the
   roster `required` updates) → `--apply` → second dry run `nothing to do` → `form_status --rendered`
   CLEAN → browser scenarios (Ryan, console one-liner that prints counts only): one club + three
   ticks; two clubs, tick both, remove one; pick, tick, clear, re-pick; rapid switching; no tick →
   Submit refused with the required message; Español.
3. Merge and push (the runner stays paused). U.S, Latin America, Asia, Africa, smallest first, each:
   backup, dry run, apply, second dry run, `form_status --rendered`, scenarios 2 and 5.
4. `AUTO_SYNC_APPLY=1`, one manual runner apply read through. Tell the Salesforce session: the
   back-fill may go.
5. For a week, daily: question 18 against the stored ticks on new submissions (the back-fill
   resolver's `q18_differs` / `q18_empty` flags; counts and ids only).

## Rollback
Generated, not a snapshot: set the constants to `False` (and the required flag off) and apply each
form by hand; `restore_conditions.py` from the pre-apply backup is the second path. Neither touches
the picker, the guard, question 5 or the integration.

## Residual risk
No recalculation at submit exists in Jotform: after this change question 18 is right for every
sequence of club picks and ticks and for a restored page in Chrome; iOS Safari and Firefox restores
are untested, and the language switcher case above stays open. The daily comparison is the alarm.
The rule walk order is Jotform's internal behaviour, not a contract (`form_status --rendered` prints
the runtime build).
