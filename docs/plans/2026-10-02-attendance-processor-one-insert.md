---
title: Attendance processor - a submission's new girls created in one insert
author: Claude (with Ryan)
status: in-progress
created: 2026-10-02
intent: none - Ryan's go of 2026-10-02 ("Go ahead and make the fix")
---

# Plan: the attendance processor creates a submission's new girls in one insert

## Context
The September back-fill ([plan](2026-09-30-september-backfill.md)) had one batch refused:
Vision GLOW Club, 2026-09-07, 27 girls new to Salesforce, HTTP 400 with nothing saved. A
rolled-back reproduction in production with made-up names settled the cause (2026-10-02, nothing
left behind): 23 new girls work, 27 fail with `System.LimitException: npsp:Too many SOQL
queries: 101`. It is not a name.

The Apex class `AttendanceBatchProcessor` (run by the after-insert trigger on
`Attendance_Batch__c`) inserts each new girl with its own `insert` inside the loop over the
names. Every single Contact insert runs NPSP's Contact triggers, which spend about four of the
NPSP package's own 100 queries per transaction (94 after 23 girls). So one submission can create
about 24 girls; the 25th makes Salesforce roll back the whole submission. The live Jotform flow
meets the same ceiling: a club's first submission with more than about 24 girls not yet in
Salesforce fails, and nothing of it arrives.

## The change (one class, its test class)
`AttendanceBatchProcessor.processParticipants` in three steps instead of one loop:
1. match every submitted name against the club's Participant contacts, exactly as today
   (case-insensitive full name; Levenshtein when the batch asks for fuzzy matching), and build an
   unsaved Contact for each name that matches none - with today's fields: FirstName before the
   first space, LastName the rest (one word: LastName only), the club as Account,
   `Contact_Role__c = 'Participant'`, Description "Auto-created from Attendance Batch";
2. insert all of the batch's new Contacts with **one** `insert` - the Contact triggers, NPSP's
   among them, run once per submission instead of once per girl;
3. queue one attendance row per girl, as today.

Two faults of today's loop go with it:
- **A name submitted twice** (case-insensitively) gives one Contact and one attendance row, not
  two Contacts (new girl) or two rows (existing girl).
- **A long error message**: a failure is recorded as `'Error: ' + message` in
  `Status_Message__c`, a 255-character field; a longer message made the status update itself fail
  and the whole submission rolled back with nothing recorded. It is cut to 255 characters.

Unchanged: the club lookup and the stray-account creation, both duplicate checks, the statuses
and their texts, fuzzy matching, the attendance fields, one status update per batch. A failure
of the one Contact insert now creates no girl at all for that batch (today the girls before the
failing one stayed, with their attendance rows, and blocked a retry).

## Order of work
1. Retrieve the class, its trigger and `AttendanceBatchTriggerTest` from production; keep the
   originals (`data/sf_processor_2026-10-02/before`, the rollback).
2. Change the class; add tests: 47 new girls in one batch; a name submitted twice; a failing
   Contact insert with a long message (the batch is Failed, its message 255 characters, no girl,
   no row).
3. Independent adversarial review of the diff.
4. `sf project deploy validate` against production with the class's test class (and the other
   tests that touch attendance) - the tests run in the org, nothing is deployed.
5. With Ryan's go (given 2026-10-02): quick deploy of the validated job.
6. Proof: a rolled-back anonymous Apex run in production with 47 made-up names - Success, 47
   rows, and the NPSP query count far below 100; nothing left behind.
7. Send the six waiting back-fill sessions (`sf_backfill.py send --retry` for the refused one).

## Risks
- **Live flow during the deploy**: a deploy swaps the class between transactions; a submission
  arriving at that second runs the old or the new code, both complete.
- **Behaviour change for a repeated name**: intended (it was a fault); the Jotform rosters never
  repeat a name.
- **Rollback**: redeploy the retrieved originals (`before`).
- The class is the vendor's (Studio Infinite Lives); Ryan decided not to coordinate with the other
  administrator for these Salesforce changes.

## Proof
- The validation run: all tests pass, the class's coverage at least 75%.
- The rolled-back 47-girl run: Success, 47 rows, NPSP SOQL well under 100.
- The six waiting sessions: sent and verified by `sf_backfill.py`.
