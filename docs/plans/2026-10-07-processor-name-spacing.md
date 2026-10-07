---
title: Attendance processor - a name with extra spaces or invisible characters finds its girl
author: Claude (with Ryan)
status: done (deployed to production 2026-10-07 04:38 UTC)
created: 2026-10-07
intent: none - Ryan's request of 2026-10-07; BACKLOG 75
---

# Plan: the attendance processor matches names regardless of spacing

## Context
- `AttendanceBatchProcessor` (the vendor's class, last changed by us 2026-10-07 03:22 UTC:
  blank-names backstop and `Girls_Present__c`) finds each ticked girl among her club's
  Participant contacts by `equalsIgnoreCase` on the full name, and creates a contact when none
  matches. Names are only trimmed at the ends.
- While the forms' names dictionary altered names (a double space; repaired 2026-10-06), every
  altered submission created another contact of the same girl: Salesforce trims the leading space
  of `LastName = " rest"`, so the stored name was the clean spelling and never equalled the
  submitted one. 19 duplicates in 5 clubs, merged 2026-10-07 (`2026-10-07-sf-duplicate-girls.md`);
  one contact kept the double space inside its name and was renamed.
- The club's contacts are queried without `ORDER BY`: when a girl has two contacts, her row lands
  on whichever comes first.

## The change (one class, its test class)
1. `parseParticipantNames`: each name has its format characters (`\p{Cf}`: U+200B..U+200F,
   U+2060, U+FEFF ...) removed and every run of whitespace or separator characters
   (`[\s\p{Z}]`: space, tab, newline, no-break space U+00A0, U+2000..U+200A, U+3000 ...) replaced by
   one space, then trimmed; a name left blank is dropped. Everything downstream - the
   repeated-name check, matching, the new contact's FirstName/LastName - uses that clean spelling,
   so a new contact is never stored with a double space again.
2. Exact match: the clean submitted name against each contact's name cleaned the same way,
   `equalsIgnoreCase` as today (a contact stored with odd spacing before this fix still matches).
   Fuzzy matching (off by default) measures the distance between the clean forms.
3. `queryClubContacts`: `ORDER BY CreatedDate, Id` - should a girl ever have two contacts again,
   every row goes to the oldest.

Unchanged: the club lookup (question 5), both duplicate checks, the statuses and their texts, the
blank-names backstop, `Girls_Present__c` (= rows, one per distinct clean name), the attendance
fields, one insert for the new girls, `Contact_IDs__c` as submitted.

Tests (made-up names only): an existing girl found when submitted with a double space, a
no-break space, a tab, a leading U+200E, other capitals - no new contact, one row each; a new girl
with odd spacing stored as `FirstName` + `LastName` with single spaces; one girl submitted twice
with different spacing gives one row; a name that is only invisible characters is dropped; with two
contacts of one name the row goes to the older one; a contact stored with a double space is
found by the clean spelling.

## Order of work
1. Retrieve the live class, test class and trigger; they must equal
   `data/sf_totals_2026-10/deployed/` (else stop: someone deployed since).
2. Build the change in a scratch SFDX project (copies kept under `data/sf_processor_2026-10-07/`:
   `before` = the rollback, `after`).
3. Independent review of the diff.
4. `sf project deploy validate` against production with `AttendanceBatchTriggerTest` and
   `TestContactTriggerHandler` - the tests run in the org, nothing is deployed. All pass;
   coverage of the class at least 75%.
5. Ryan's go: quick deploy of the validated job; retrieve and compare with `after`.
6. Proof: a rolled-back anonymous Apex run in production with made-up names (an existing girl
   sent with a double space and a no-break space; a new girl with odd spacing): Success, the
   right rows, no duplicate, the new contact's name clean; nothing left behind. Then
   `sf_dupes.py check` stays at 0 groups and 0 odd names.

## Risks
- **Two real girls whose names differ only by spacing** in one club would now be one girl. The
  Roster has none (checked on all 18 exports, 2026-10-07); `sf_dupes.py check` would show it.
- **Live flow during the deploy**: the class is swapped between transactions; a submission runs
  the old or the new code, both complete.
- **Rollback**: redeploy `before` (the 03:22 UTC version).
- The class is the vendor's (Studio Infinite Lives); Ryan decided not to coordinate with the other
  administrator for these changes (2026-10-02).

## Result (2026-10-07)
- Step 1: the live class, test class and trigger equalled `data/sf_totals_2026-10/deployed/`.
- Independent review of the diff: no critical, high or medium defect. Two low notes left as they
  are: a zero-width space used *instead of* a space joins the two words (as `sf_dupes.py`'s key
  does; no Roster name holds any format character), and the club's contact names are cleaned even
  for a batch that then turns out to have no names (harmless). Devanagari names would lose
  ZWJ/ZWNJ when stored; no roster has any (all 7,202 rows Latin script) - revisit if one arrives.
- Validation in production (check only, 0AfRP000002gLOf0AM): 33 of 33 tests
  (`AttendanceBatchTriggerTest` 30 with the 7 new ones, `TestContactTriggerHandler` 3); the
  processor's coverage 93%. `testCleanName` was the first run of `\p{Cf}` / `[\s\p{Z}]` in this org.
- Quick deploy 04:38:55 UTC (0AfRP000002gLRt0AM), the two classes only; read back identical (the
  test class without its final newline, as Salesforce stores it); the trigger unchanged.
- Proof in production, rolled back, made-up names: two new girls sent with a double space and a
  no-break space -> Success, 2 rows, 2 clean contacts; the same girls with an invisible mark, a tab
  and other capitals plus a new girl with a double space inside her last name -> Success, 3 rows,
  no twin, the new girl stored `Gamma Delta`; 3 contacts, 0 with odd spacing; nothing left behind.
- `sf_dupes.py check` after the deploy: 0 groups, 0 odd names (2,962 participants).
- Rollback: redeploy `data/sf_totals_2026-10/deployed/` (the 03:22 UTC version with the blank
  backstop and `Girls_Present__c`) - **not** `data/sf_totals_2026-10/before/`, which would undo
  both. The new build: retrieve it from the org (`sf project retrieve start -m
  ApexClass:AttendanceBatchProcessor ...`).

