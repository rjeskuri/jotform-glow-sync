---
title: Attendance processor - a corrected re-submission adds its missing girls to the day's original batch
author: Claude (with Ryan's decisions of 2026-10-22)
status: in-progress      # ticket #108; deployed 2026-10-24 06:48 UTC, step 7 (the read-back) pending (Result)
created: 2026-10-22
intent: none - Ryan's request of 2026-10-22 (staff meeting, "names not being added"; ticket #108)
---

# Plan: a corrected re-submission merges into the day's original batch (ticket #108)

## Context
- The 2026-10-22 trace of every girl added through the Club Roster Form since 2026-09-07 found
  12 girls with no Participant Contact although a mentor ticked them: each was ticked only in a
  corrected re-submission for a session date that already had a `Success` batch, and the
  processor failed such a batch whole as "Duplicate" before reading a name. All 83 Failed
  batches since 2026-09-07 are this rule, and they arrive daily (ticket #108).
- The rule (Ryan, 2026-10-22, on the ticket): a re-submission for a club and date that already
  has a `Success` batch, with the same `Module__c`, adds `Attendance__c` rows only for the girls
  ticked now and absent from that club and date's rows - never a row removed, never a girl
  counted twice - as rows of the original batch; the original's `Girls_Present__c` moves to the
  new total; the correction's own batch is `Success` with `Status_Message__c` exactly
  `merged into <original batch id>` (no new picklist value), no count and no rows of its own. A
  different module stays `Failed` "Duplicate" (one session per club per day, DECISIONS
  2026-10-13); a re-submission that adds nobody stays `Failed` "Duplicate" exactly as now.
- The live processor, its test class, the trigger and `TestContactTriggerHandler` were retrieved
  fresh on 2026-10-22 into `data/sf_processor_2026-10-22/before/` (never an older build,
  DECISIONS 2026-10-16); the build is `after/` beside it, with its `sfdx-project.json`.

## The change (one class, its test class)
`AttendanceBatchProcessor` only; the trigger and `TestContactTriggerHandler` stay as retrieved.
1. `findOriginalBatch` replaces the yes/no duplicate check: the oldest `Success` batch for the
   account and date (`ORDER BY CreatedDate, Id LIMIT 1`, the current batch excluded) with its
   date, module, week, year and `Creator__c`. A merged correction is a `Success` too, but never
   the oldest, so a second correction merges into the original as well.
2. `mergeIntoOriginal`, when there is an original: refused (`Failed` "Duplicate", the message
   unchanged) when the module differs, when the original is a `Partner report` or has no rows of
   its own, when the correction names nobody, or when every girl it names already has a row for
   that club and date. Else the girls are matched and created exactly as a submission's are
   (`resolveParticipants`: the part of `processParticipants` both share - clean names, a name
   twice counts once, exact or fuzzy match, the new girls in ONE insert), one row of the original
   batch is queued for each girl without a row on that club and date (whatever created the rows),
   the original's `Girls_Present__c` is set to its own rows after the merge, and the correction's
   status update is `Success`, `merged into <original id>`, `Girls_Present__c` null.
3. `saveRecords` updates the batches' own statuses and the originals' counts in one DML (a map,
   one update per original: two corrections of one day in one run share it). Two corrections of
   one day in ONE trigger run (a bulk insert) read each other through the run's own state, not
   the database, where the first one's rows arrive only in `saveRecords`: per original, the girls
   this run has queued for it (`girlsQueuedByOriginal`) and its one status update with the
   running count (the original's rows in the database plus every girl queued). The second
   correction gets no second row for a girl the first one added, counts her once, and stays
   `Failed` "Duplicate" when it brings nothing new (2026-10-23, the review of PR #126; no method
   of the fixed test class inserts two corrections in one DML - the proof of Rollout step 6 does).
4. Three choices Ryan's answers leave open, built as the defaults below - **Ryan to confirm
   before the deploy** (Rollout step 3; DECISIONS 2026-10-22 lists the same three):
   - (1) a merged row carries the ORIGINAL batch's `Module_Week__c`, `Module_Year__c`, module and
     date (it belongs to that session), not the correction's;
   - (2) the original's `Girls_Present__c` = the count of the original batch's own `Attendance__c`
     rows after the merge - the field's definition since 2026-10-07 and what
     `tools/sf_girls_present.py check` compares; Ryan's answer 2, "the count of that date's rows
     after the merge", is read as the batch's own rows, so a hand-made row (on no batch) for a
     girl on that date blocks a second row for her but is not counted on the batch;
   - (3) nothing is merged into a batch with no rows of its own (a typed aggregate, one of the
     three legacy blanks of BACKLOG 73, a merged correction) or whose `Creator__c` is
     `Partner report`: such a correction stays `Failed` "Duplicate" as today.
5. Module equality is Apex's string equality (`==`: case-insensitive, null-safe), as the club and
   name matching ignores case; the form sends the dropdown's exact text, so this only matters if
   a form's option ever changes case.

Unchanged: the club lookup (question 5, a partner-less account created when nothing matches),
"Attendance already exists" for rows without a `Success` batch, the blank-names backstop and the
typed aggregates, the statuses' texts, name cleaning and matching, one insert for new girls.

Tests (`AttendanceBatchTriggerTest`, fictional names only): 11 new methods and one changed -
a correction adding one girl (rows, fields, count 1 -> 2); one adding nobody (refused, nothing
changed); the whole roster again with one new girl, ticked twice (one contact, one row, 2 -> 3);
another day (a batch of its own); another module (refused, no contact created); names matched
and stored as a submission's (capitals, spacing, invisible marks); a fuzzy correction; a second
correction merging into the OLDEST `Success` batch; earlier Failed batches passed over; a blank
on a day with a `Success` batch; a girl with a hand-made row gets no second row; the old
duplicate test now ticks a girl already on that day.

The repository side (this ticket, no live step): `tools/sf_girls_present.py` leaves merged
corrections out of `plan`, `set` and `check` by a condition on `Status_Message__c` in the WHERE
only (never selected or printed); `tools/sf_backfill.py` knows the outcome `merged`; RUNBOOK
"Attendance totals and partner-reported counts" (A mentor's correction), the template-test
recipe in "Photos", "Special events"; the salesforce skill; DECISIONS 2026-10-22.

## Rollout (live; each step on Ryan's go)
1. `data/sf_processor_2026-10-22/`: `before/` is the fresh retrieve of 2026-10-22, `after/` the
   build (the processor changed, the test class with the new methods, the trigger and
   `TestContactTriggerHandler` as retrieved). Before anything runs, retrieve the four components
   again and compare with `before/`: any difference means someone changed them since - stop and
   rebuild from that retrieve.
2. Check-only validate in production with the two test classes, nothing changed in the org,
   VPN off, from `data/sf_processor_2026-10-22/after/`:

   ```sh
   sf project deploy validate -o glow --source-dir force-app --test-level RunSpecifiedTests --tests AttendanceBatchTriggerTest --tests TestContactTriggerHandler
   ```

   Expected: every test passes (the 33 of 2026-10-07 plus the 11 new ones), the processor's
   coverage at least 75%; note the validation id. A failing test: fix the processor (never the
   test), validate again.
3. Ryan's go, in the conversation, on the validation's result AND his confirmation of the three
   defaults of "The change" 4 as built: (1) a merged row carries the original batch's session
   fields, (2) the original's `Girls_Present__c` is the count of its own rows, (3) nothing is
   merged into a row-less or `Partner report` batch. A different answer on any of them changes
   the build: rebuild `after/` to it and validate again (step 2) before any deploy.
4. Quick deploy of that validation: `sf project deploy quick -o glow -i <validation id>`; note
   the deploy id and the time (UTC).
5. Retrieve the four components again (`sf project retrieve start -o glow -m
   ApexClass:AttendanceBatchProcessor -m ApexClass:AttendanceBatchTriggerTest -m
   ApexClass:TestContactTriggerHandler -m ApexTrigger:AttendanceBatchTrigger`, into a new folder
   under `data/sf_processor_2026-10-22/`) and compare with `after/`: equal, apart from a missing
   final newline on a class (Salesforce stores it without one).
6. Proof in production, rolled back, with fictional names (`sf apex run` of a script pasted in
   full in the conversation first, ending in `Database.rollback`): a test club with two made-up
   girls, a submission of one of them (`Success`, 1 row, `Girls_Present__c` 1), then the same
   club, date and module with both girls -> the correction `Success` with `Status_Message__c`
   `merged into <the first batch's id>`, no count, no rows of its own; the first batch 2
   `Attendance__c` rows, `Girls_Present__c` 2; a third batch naming the same two girls ->
   `Failed` "Duplicate", nothing changed; a fourth with another module -> `Failed` "Duplicate";
   then two corrections inserted in ONE DML (one trigger run: the bulk case of "The change" 3),
   the first naming a third made-up girl and the second naming only her -> the first `Success`
   merged, the second `Failed` "Duplicate" (she was queued by the first, not yet in the
   database), the first batch 3 rows, `Girls_Present__c` 3, one row for her.
   Everything rolled back: the club, the contacts, the batches and the rows gone (a count of
   each = 0 after the run). Counts only in the conversation, never a name.
7. Read-back of the live flow, the next day: `SELECT COUNT() FROM Attendance_Batch__c WHERE
   Processing_Status__c = 'Success' AND Status_Message__c LIKE 'merged into %' AND CreatedDate
   = TODAY` (a condition, never the message selected) - the day's corrections, if any; for one
   of them, the original's rows and `Girls_Present__c` equal; `python3
   tools/sf_girls_present.py check --vpn-off` -> `differ: 0, without a value: 0 -> OK`; the
   dashboard's tiles unchanged for sessions with one batch. Then the Result below, the plan
   `done`, `make docs-index`.

## Rollback
Redeploy only the two classes this change deploys, `AttendanceBatchProcessor` and
`AttendanceBatchTriggerTest`, from `data/sf_processor_2026-10-22/before/`, and only after a fresh
retrieve of the two classes and the trigger equals this change's `after/` (ignoring a missing
final newline on a class); any other difference means something was deployed since -
stop and build the rollback from that retrieve, never from an older build or copy (DECISIONS
2026-10-16). The trigger `AttendanceBatchTrigger` and `TestContactTriggerHandler` are not
redeployed: they stay as retrieved. Rows a correction added before the rollback stay (they are
real attendance); a merged correction's batch keeps its `merged into` message, which the tools
read as its own kind.

## Risks
- **A real second session on one day** (two curriculum sessions of one module on one date) would
  merge into one: the forms allow one module per submission, and staff tell mentors one
  submission per club per day (DECISIONS 2026-10-13), so a second batch with the same module is
  a correction.
- **A correction with fuzzy matching on** could attach a typo to the wrong girl, as a submission
  can; fuzzy matching is off by default and the forms never set it.
- **Live flow during the deploy**: the class is swapped between transactions; a submission runs
  the old or the new code, both complete.
- **The 12 girls of the Request** are not back-filled by this change: their corrections are
  already `Failed` and are never re-processed (the trigger runs on insert only). The next ticket
  re-sends or adds them.
- **The template-test recipe** (RUNBOOK "Photos", step 3) relied on the refusal; it now ticks
  only girls already on that date's batch and still expects `Failed` "Duplicate".
- The class is the vendor's (Studio Infinite Lives); Ryan decided not to coordinate with the other
  administrator for these changes (2026-10-02).

## Proof
- Offline: `make check` -> `CHECK PASSED` (the doc tests of `test/correction_merge_test.py`, the
  tool tests `test/sf_backfill_test.py` and `test/sf_girls_present_test.py`).
- In the org: the validate of Rollout step 2 (every test passes), the compare of step 5 (equal),
  the rolled-back proof of step 6 (counts as expected, nothing left), the read-back of step 7.

## Result (2026-10-24)
Deployed 2026-10-24 06:48 UTC, each step on Ryan's go in the conversation (counts only, never a
name); the read-back of Rollout step 7 is the remaining step, due the next day (2026-10-25).
- Step 1: a fresh retrieve of the four components (`data/sf_processor_2026-10-22/check_2026-10-24/`)
  equalled `before/`: nothing had changed in the org since 2026-10-22.
- Step 2: check-only validate 0AfRP000002i4GT0AY: 44 of 44 tests passed
  (`AttendanceBatchTriggerTest` and `TestContactTriggerHandler`: the 33 of 2026-10-07 plus the 11
  new ones), 0 failing; the validate run's coverage 94.05% of lines (269/286); the processor and
  its test class Changed, the trigger and `TestContactTriggerHandler` Unchanged.
- Step 3: Ryan confirmed the three defaults of "The change" 4 as built - (1) a merged row carries
  the original batch's session fields, (2) the original's `Girls_Present__c` is the count of its
  own rows, (3) nothing is merged into a row-less or `Partner report` batch - and gave the go.
  The last low finding of the review (the template-test remedy keyed by `CreatedDate`) stays as
  it is, his choice.
- Step 4: quick deploy 0AfRP000002i4I50AI of that validation, done 06:48:43 UTC.
- Step 5: the retrieve after the deploy (`data/sf_processor_2026-10-22/deployed_2026-10-24/`)
  equals `after/`, apart from the missing final newline on `AttendanceBatchProcessor.cls`
  (Salesforce stores it without one; on 2026-10-07 it was the test class, hence "a class" in the
  steps above).
- Step 6: the rolled-back proof (`data/sf_processor_2026-10-22/proof_2026-10-24.apex`, fictional
  names, session day 2026-01-15) gave exactly the expected outcome: the original `Success`, 1 row,
  `Girls_Present__c` 1; the correction `Success` with `Status_Message__c` exactly
  `merged into <the original's id>`, no count, no rows of its own, the original 2 rows and
  `Girls_Present__c` 2; the same girls again `Failed` "Duplicate", the original unchanged; another
  module `Failed` "Duplicate", no rows, no contact made; two corrections in one insert: the first
  merged, the second `Failed` "Duplicate", the original 3 rows and `Girls_Present__c` 3, one row
  for the third girl. After the rollback 0 accounts, 0 batches, 0 contacts, confirmed by separate
  read-only counts afterwards (0 / 0 / 0).
- Step 7, the read-back of the live flow, is due 2026-10-25: the day's merged corrections counted,
  one original's rows and `Girls_Present__c` equal, `sf_girls_present.py check` OK, the dashboard's
  tiles unchanged for sessions with one batch; then the plan `done`, `make docs-index`.
- Rollback, if needed: as in Rollback above - the two classes from `before/`, after a fresh
  retrieve equals `after/` (the read-back of step 5 did, ignoring the processor's missing final
  newline).
