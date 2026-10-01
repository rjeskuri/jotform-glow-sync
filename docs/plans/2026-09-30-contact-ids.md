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

## Build notes
Built 2026-10-01 on branch `wf8/contact-ids` (a worktree), parts 2 and 3 of "What changes" and
part 1 in its lead design. Nothing was written to any form, the sheet or Salesforce.

**The browser proof came first and passed** (2026-10-01, another part of the same workflow: local
copies of the Asia, U.S and Africa pages in headless Chrome, network to Jotform blocked, every
submit intercepted). Required rosters: one club and no tick is refused on all three forms with
Jotform's own message, 0 hidden rosters flagged, the picker not flagged, Submit still visible; one
tick goes through with question 18 equal to the ticks; refused on club A, switched to B and one
tick, it goes through (the stale error on hidden A does not block). New order: removing one of two
clubs, and clear-then-re-pick, both leave question 18 equal to the visible ticks (the old order:
other club's girls, and an empty question 18). Two clubs and Enter: no submit in any shape. Jotform's
own `requireField` on the U.S page sets exactly `validate[required]` on all 155 boxes. So the
**fallback rule (hide Submit while question 18 is empty) is not built.**

**Deviations and decisions made in the build**
- **The order and the operand apply on a form with the Club picker only**; a form without it keeps
  its rules byte for byte, in every combination of the constants (a test). Every live form has the
  picker; the typed club name is the legacy path. `form_status`'s order, operand and coverage
  checks are likewise picker-only.
- **The required flag is on every roster of every form** (a question property, not a rule). Off
  (`ROSTERS_REQUIRED = False`), the sync writes `"No"` where a roster has `"Yes"`: the rollback is
  generated both ways, and `form_status` then flags a required roster.
- **Labels.** The flag alone: `REQUIRED roster '<club>' (q<qid>: Yes)` (new `REQUIRED_RX`, plan key
  `requires`, summary-JSON `requires`). With an options update, one write and the existing label
  extended: `UPDATE roster '<club>' (q<qid>, N girls; required: Yes)` (`UPDATE_RX` takes the
  optional suffix; the runner counts it as an update). `CREATE roster` is unchanged; its payload
  gains `question[required]=Yes`. The flag-alone writes come **last** in a run, after the rules and
  the Partner-box hide: on the template they are 359 writes, and a run stopping among them must
  not leave a new roster without its rule.
- **The runner refuses more than the plan said**: any plan with the `CONTACT_IDS_STALE` warning, roster
  changes included (a `check_bands` reason, so a rules-only plan is `attention`, never `in-sync`),
  and any `REQUIRED roster` line at all, one or 220 (not a band size). After a form's rollout the
  runner still creates required rosters and applies `UPDATE … ; required: Yes`.
- **The constants are read through the module** (`glow_sync.CONTACT_IDS_FIRST`, …) by the sync,
  `form_status`, `restore_conditions` and the shared helpers `contact_ids_layout` /
  `contact_ids_stale` / `roster_required` in `glow/sync.py`: one patch, one rollback switch.
- **Coverage audit, per critique 1**: with the order on, a field a roster rule tests must be a
  *term* of question 18's rule (that puts the sum in that field's rule walk); with only the operand
  on, an operand. A form whose roster rules test the Partner box (before the same-name switch; none
  live since 2026-09-30) is therefore NOT CLEAN: flagged, not generated (the design's choice). The
  unswitched-form tests were updated to expect exactly that one line.
- With the order off, question 18 at rule 0 is not flagged (never harmful); with the operand off, the
  picker among its operands is ("includes 1 non-roster question").
- Added on the way: two rules calculating question 18 is a problem; the equation check also catches a
  literal between the fields and a field twice; `aggregate_rosters` counts rosters only (critique 2);
  `restore_conditions.py` prints a note when its snapshot calculates question 18 the old way;
  `--rendered` reads every form's page (not only picker forms) and prints the runtime build.
- **No template test submission** (critique 2): the console checks prove the same, and a delivered one
  is a real batch for a real club. The RUNBOOK's rollout drops it.
- The live-systems skill's "Never" list gains "an apply from a checkout without this code once a form
  is rolled out", and its rollback list the generated path.

**Proof, read-only (2026-10-01, from the branch).** A fresh Roster export (7,041 rows) in the
session's scratch folder, deleted afterwards. The sync's dry run on each form:

| Form | Calls | Rules | Required |
|---|---|---|---|
| U.S | 12 | `REPLACE conditions (42 rules)`: 41 kept, 1 new, 1 dropped | 11 `REQUIRED roster` |
| Latin America | 39 | 69: 68 kept, 1 new, 1 dropped | 38 |
| Asia | 96 | 126: 125 kept, 1 new, 1 dropped | 95 |
| Africa | 221 | 251: 250 kept, 1 new, 1 dropped | 220 |
| template | 366 | 393 (+~2 once its new rosters exist): 390 kept, 3 new, 3 dropped | 359, plus 3 `UPDATE roster … ; required: Yes` |

Each regional form also warned once with `question 18 (Contact_IDs) is not recalculated after the
rosters change` (rule 40 of 42, 67 of 69, 124 of 126, 249 of 251; the picker not an operand). The
template also plans its backlog: 2 `CREATE roster`, 3 roster updates, `UPDATE club picker (364 clubs:
calcValues, options)`; its 3 new rules are the sum and the guard's two (the picker gains two clubs).
`form_status --rendered` read all five NOT CLEAN, with the same six problems on each: not required,
the order, the operand, and their three rendered counterparts. Every picker's `data-calcvalue` was
aligned, and 0 roster boxes carried `validate[required]` (6,857 / 4,264 / 1,636 / 869 / 155). Runtime
builds served: template `cca53a3a639`, Africa `962dcbe2fa6`, Asia, Latin America and U.S `9e75d6f1d83`;
`jotform.forms.js` is byte-identical (md5 `841dc566a7`) in those three and in `772a1982daf`.
`auto_sync.py` as a dry run on the export (no SyncLog) put all four regions at `attention`, exit 2,
"not applied", with both reasons. `make check`: CHECK PASSED, 429 Python tests (21 new).
