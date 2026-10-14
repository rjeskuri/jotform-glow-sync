---
title: Special event "IDG Celebrations" on every attendance form, after "Welcome Session"
author: Claude (with Ryan's decisions of 2026-10-14)
status: accepted         # Ryan accepted it in conversation on 2026-10-14
done:
backlog:
created: 2026-10-14
intent: Ryan, 2026-10-14 - "Under the new special module created yesterday we need "IDG Celebrations" added as a new option now."
---

# Plan: "Special Event - IDG Celebrations" on every attendance form

Ryan, 2026-10-14: a second type under the special-event module of 2026-10-13. The option text,
his choice, is `Special Event - IDG Celebrations`. Ticket #26, epic #25.

## Context
- The mechanism is the one built and rolled out on 2026-10-13
  ([plan](2026-10-13-special-events.md), RUNBOOK "Special events"): a special event is one more
  option of every year's module dropdown (q14, q92, q93), with no session dropdown, so Salesforce
  receives `Module__c` = the option's text, `Module_Week__c` blank and `Module_Year__c` the year.
  Adding a type is one line in `glow/sync.py` `SPECIAL_EVENTS` (the new type after Welcome
  Session: the sync appends missing options in that order and never reorders) and a rollout: the
  template by hand, the regional forms by the runner (Rollout).
- Nothing else in code changes. The tests of 2026-10-14 pin the type list, the one-option-added
  dry run on a form that already carries Welcome Session, the rules (no session rule for either
  event, the bridge still first), the `form_status` audit and the runner's apply (#27 pinned its
  refusal; #30 flips it).
- Salesforce read 2026-10-14 (read-only, counts only): no batch with `Module__c LIKE 'Special
  Event - %'`, and one regional Jotform submission since the 2026-10-13 rollout, not an event. So
  no Welcome Session batch has proven a blank `Module_Week__c` through the integration yet. Ryan
  chose to proceed anyway and to watch the first event batch (Risks).
- Translations: none, as for the modules (module options are English in every language's store,
  read 2026-10-13).

## Rollout (live; each step on Ryan's go)
Ryan's sequence (#30, 2026-10-14). Nobody applies anything by hand except Claude, on Ryan's go in
the session; the enabled regional forms are the runner's.

1. PR #40 (#30: the runner applies merged generated form changes) is ready: reviewed, CI green.
2. Ryan lands #27: `IDG Celebrations` in `SPECIAL_EVENTS` on `main` (done, c0c8f02). Until step 5
   `main`'s runner holds Africa, Asia and Latin America (Risks).
3. This branch merges `main` and flips #27's runner-hold test to the apply (done, 2b80914 and
   ddeafed).
4. **Claude applies the template** `262352490535154`, on Ryan's go in the session. That go comes
   through the live gate's in-session approval if that task (#36) has landed; otherwise Ryan
   relaunches Claude once with `GLOW_LIVE_OK=1` exported, for this one step.
   1. Backup: `python3 backup_forms.py --form 262352490535154`.
   2. The sync's dry run (the command of RUNBOOK "The Club picker", on a fresh roster export):
      `python3 sync_attendance_form.py data/roster_<date>.csv --roster --form 262352490535154 --club-picker`.
      Expect three module lines, one event option added each:
      `UPDATE module dropdown (q14, year 1: 1 event option(s) added (Special Event - IDG Celebrations); calcValues = its 7 options)`,
      and q92 with 9, q93 with 10 (Welcome Session is already there; on 2026-10-13 they had 6, 8
      and 9). The session bridge is already in place and the new event takes no rule, so the
      module lines alone change nothing in the rules (`(conditions unchanged - skipping the
      rewrite)`). The runner never syncs the template, so a fresh export normally brings its
      roster catch-up too, and `REPLACE conditions` with it: expected, and applied in the same
      run. Stop and read why only on a `!` line or a session rule for an event.
   3. Ryan's go, then the same command with `--apply`.
   4. `python3 tools/form_status.py --form 262352490535154 --roster data/roster_<date>.csv --rendered --partners data/partners_<date>.csv`
      CLEAN, `special events: 2 type(s) on 3 of 3 module dropdowns`.
   5. Browser check on the template, nothing submitted: in each year the new option is the last
      of the module dropdown (after Welcome Session) and picking it shows no session dropdown
      (RUNBOOK "Special events", Browser checks).
5. Ryan lands #40 (`/land-checks`, `/harness:land`).
6. **The runner's next run** adds the option to **Africa** `262382821971058`, **Asia**
   `262383129464057` and **Latin America** `262383455778067`: the three module lines on each
   form, with any roster change held since step 2, within the bands (SyncLog `applied`, `…
   special-event options on 3 dropdown(s); verified clean`). The next run is the next roster
   change, at the latest the morning backstop, or one started from the Actions tab on Ryan's go.
   - Claude verifies each form:
     `python3 tools/form_status.py --form <id> --roster data/roster_<date>.csv --rendered --partners data/partners_<date>.csv`
     CLEAN, `special events: 2 type(s) on 3 of 3 module dropdowns`. A region the bands hold
     (ATTENTION, nothing applied) is read and settled first.
   - The disabled **U.S** form `262382706852058` (the runner skips it) is applied by Claude the
     same way as the template, on Ryan's go: backup (`backup_forms.py --form 262382706852058`),
     the sync's dry run
     (`python3 sync_attendance_form.py data/roster_<date>.csv --roster --partners data/partners_<date>.csv --region U.S --form 262382706852058 --disabled-ok`;
     expect the three module lines, with roster lines and `REPLACE conditions` if its roster
     changed; stop only on a `!` line or a session rule for an event), `--apply`, and
     `form_status.py --rendered --partners` CLEAN.
   - Then `python3 tools/auto_sync.py`: every region `in-sync`, the U.S form `skipped - form
     DISABLED`.
7. Staff tell mentors: the new option, and one submission per club per day.

## Rollback
Remove `IDG Celebrations` from `SPECIAL_EVENTS` and merge that first (else the next apply adds
the option back). Then, per form, delete the option in the builder on q14, q92 and q93
(tooling never deletes an option); the sync's next dry run plans the realigned `calcValues`,
which the runner's next run applies (the template and the disabled U.S form: Claude, on Ryan's
go). `restore_conditions.py --from` the snapshot of the apply only if rules changed (none are
expected). Until the option is deleted the sync warns and `form_status` reports it.
Salesforce history stays: batches keep their `Module__c`.

## Risks
- **Blank `Module_Week__c` through the integration is unproven.** No event batch has arrived
  yet (Salesforce read 2026-10-14), and Ryan declined a test submission on 2026-10-13. Read the
  first `Special Event - IDG Celebrations` batch by SOQL (counts and fields only: status,
  `Module_Week__c`, `Module_Year__c`, rows created). If a Jotform submission for it never
  arrives in Salesforce, the integration refused the blank; the submission is the record:
  back-fill it and decide the fix (for example 0) with Ryan. A Welcome Session batch settles
  the same question.
- **One batch per club and date.** An IDG Celebrations session on a day the club also holds a
  curriculum session or a Welcome Session is refused as a duplicate, whichever arrives second
  (DECISIONS 2026-10-13); mentors submit one per day.
- **The regional forms are held from #27's land until #40's**: `main`'s runner holds Africa,
  Asia and Latin America (ATTENTION, `check_bands`), their roster changes with them: land #40
  soon after the template's apply. From then the runner's next run writes the option with no
  step between the land and the write; the template's apply and browser checks come first.
- **Translations: none**, so the option reads in English in every language, as the modules do.

## Proof
Healthy output after the rollout:
- Each dry run before `--apply`: three `UPDATE module dropdown … 1 event option(s) added
  (Special Event - IDG Celebrations)` lines. Roster lines and `REPLACE conditions` may come
  with them (on the template and the disabled U.S form, whose roster catch-up the runner never
  does): expected. Stop only on a `!` line or a session rule for an event.
- `python3 tools/form_status.py --form <id> --roster data/roster_<date>.csv --partners
  data/partners_<date>.csv --rendered` on each of the five forms: CLEAN, `special events: 2
  type(s) on 3 of 3 module dropdowns`.
- `python3 tools/auto_sync.py`: Africa, Asia and Latin America `in-sync`, U.S `skipped - form
  DISABLED`.
- Before landing: `scripts/verify.sh` ends `VERIFY OK`.
- After the first event: the SOQL read above.

## Result
