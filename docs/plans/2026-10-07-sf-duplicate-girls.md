---
title: One Salesforce contact per girl - merge the duplicates the altered names made, then release Queens of Quest
author: Claude (with Ryan)
status: accepted (Ryan, 2026-10-07: "Build tool, then go") - in-progress
created: 2026-10-07
intent: none - Ryan's request of 2026-10-06 ("You can handle all salesforce related issues")
---

# Plan: one Salesforce contact per girl

## Context
- **The cause (fixed 2026-10-06 11:22 UTC).** The forms' names dictionary altered some girls' names
  in question 18 (Contact_IDs): a double space, in 49 of 50 cases right after the first name
  (`docs/plans/2026-10-02-names-and-modules.md`). Re-read 2026-10-07 01:55 UTC: all five forms
  `CLEAN`, 0 roster options altered.
- **What it did in Salesforce.** `AttendanceBatchProcessor` matches a name exactly (ignoring case)
  among the club's contacts and creates a contact when nothing matches. It saved
  `LastName = " rest"`, which Salesforce trims, so the stored Name is the clean spelling and the
  next altered submission matched nobody again: every live submission before the repair created
  another copy of each affected girl.
- **Census (read-only, 2026-10-07 01:14 UTC; counts only here, ids in
  `data/sf_dupes_2026-10-07/`):**
  - 15 girls have 2 to 4 contacts: **19 extra contacts** in 5 clubs - Queens of Quest (Africa) 11,
    Rock Stars GLOW Club 3, Unity GLOW Club 2, Janasewa GC-3 2, Niharika G.L.O.W Club 1 (Asia).
  - Each extra holds 1 attendance row (19); **0 dates** where two copies of a girl both have a row.
  - Copies are identical in Name, FirstName, LastName, owner, role, club and Description; they
    differ only in created time and rows.
  - **1 contact (Alpha, Africa) still has the double space** in its LastName; no twin yet, but her
    next (correctly spelled) tick would create one.
  - Checked against all 18 roster exports: each group's name is exactly one active girl of that
    club, spelled as stored, and no two girls of one club differ only by spacing or case.
    Grouping stays **within a club**: 50 names are real namesakes in different clubs.
- **Queens of Quest's 2 back-fill sessions** (09-09: 12 names, 09-16: 11) are held for
  `club_has_earlier_contacts`. Released today, 21 of 23 names would each find two contacts and the
  processor (no `ORDER BY`) would attach the row to whichever comes first. After the merge each
  name finds one: 23 rows, 1 new girl, 13 contacts = the 13 active roster girls.

## Decisions
1. **Salesforce's own merge** (`Database.merge` in anonymous Apex), not re-parenting:
   `Attendance__c.Contact__c` is master-detail with reparenting off, so moving rows by update is
   blocked; a merge moves every child (rows keep their ids, batch, date, module), leaves
   `MasterRecordId` on the merged-away contact (Recycle Bin, 15 days) and returns the moved ids.
   Clicking the merges by hand is the fallback (same checks).
2. **Which contact stays:** the back-fill's contact (`created_contacts.csv`) where there is one,
   else the earliest created (ties: lowest id). The copies are otherwise identical.
3. **Alpha:** one update, `LastName` with its whitespace collapsed, only if the result equals one
   active Alpha roster girl exactly and no twin exists; if a twin has appeared, merge the twin into
   her older contact first, then rename.
4. **Same-date pairs** (none today): the run refuses and the case goes to Ryan.
5. **Order:** rehearsal → Alpha rename → Queens of Quest merges → the other four clubs → clean-up →
   final check → Queens of Quest release (`sf_backfill.py`, one session key at a time).

## What gets built: `tools/sf_dupes.py` (standard library; `glow.salesforce.Org`, CLI login `glow`)
- `check [--roster CSV]` - read-only, exit 1 on any finding, counts and ids only, never a name:
  same-name groups per club (key: invisible characters dropped, any whitespace run → one space,
  trimmed, case-folded); stored names with odd whitespace; batches since the 1st of the month whose
  name list has odd whitespace; with `--roster`, names found in two clubs that the roster does not
  have in both (reported, never merged). The monthly check (RUNBOOK).
- `plan --roster CSV` - read-only: fresh reads, the roster proof per group, the kept contact, the
  others in chunks of at most 2, each contact's rows / affiliations / duplicate-rule items, the
  renames, expected counts per club → `data/sf_dupes_<date>/merge_plan.json` (0600, ids only);
  prints a table of counts.
- `merge PLAN [--club ID] [--rehearse | --apply --vpn-off]` - dry run by default (prints what would
  run). Before any write: re-reads and refuses on any drift from the plan; refuses if a submission
  reached the Africa or Asia form in the last 10 minutes, or between 20:30 and 21:30 UTC (NPSP's
  nightly job); writes `merge_rollback.json` (0600) with every createable field of each
  merged-away contact, its rows (incl. `Account__c`), affiliations and duplicate-rule items.
  - One anonymous-Apex run per club (`sf apex run --json`, the Apex on disk 0600 with ids only):
    guards (ids as planned, same club, role Participant, exact Name/FirstName/LastName equality,
    the processor's Description and creator), row counts per date before and after (equal), kept
    contact's rows = the sum, `Limits` used; only `DIAG|` lines are printed; the full log goes to a
    0600 file (it can hold names).
  - `--rehearse` ends the run with an uncaught exception, so the whole transaction - including any
    async job NPSP queued - is discarded; then it re-reads to prove nothing changed.
  - After `--apply`: read-back (participants down by exactly the merged count, rows per date
    unchanged, moved rows on the kept contact, merged-away contacts deleted with `MasterRecordId` =
    the kept one) and a count of form submissions vs new batches in the run's window.
- `rename PLAN [--apply --vpn-off]` - the plan's renames by REST update (the value goes to curl on
  stdin), old value kept in the rollback file, read back against the roster in memory.
- `cleanup PLAN [--dup-sets] [--apply --vpn-off]` - per kept contact and club, affiliations down to
  exactly one (the earliest; never below one); with `--dup-sets`, the plan's duplicate-rule sets
  left with at most one item. Each record saved to the rollback file before its delete.
- `glow/salesforce.py` gains `Org.delete`.
- Tests: `test/sf_dupes_test.py` (fictional names), run from `test/python_test.py`: the key, the
  grouping (within a club only), the roster proof, the survivor rule, chunking, drift refusal, the
  Apex text (ids only, the rehearsal's final throw, no catch-and-continue), the DIAG filter (no name
  ever printed), the quiet-window and 21:00 refusals, the rollback file written before the first
  write, `--apply` without `--vpn-off` refused.

## The run (Ryan's go of 2026-10-07; VPN off; session -a1 told first)
1. `make check`, review, merge. 2. `plan` → counts must equal the census (15 groups, 19 extras,
0 same-date, 1 rename), else stop and ask. 3. `merge --rehearse` per club; any surprise (a row not
moved, a limit) stops everything. 4. `rename --apply`, read back. 5. `merge --apply` Queens of
Quest, read back; then the other four. 6. `cleanup --apply` (and `--dup-sets`). 7. `check` → 0.
8. Queens of Quest: fresh resolve + snapshot + the two `accept club_has_earlier_contacts` lines in
`decisions.csv` + plan + `send` dry run (exactly 2 batches, 23 rows, the other held sessions
unchanged) + `send --apply --vpn-off --only <key>` twice, each read back.

## Rollback
- A merge (15 days): undelete the merged-away contact; delete the moved rows from the kept contact
  and re-insert them on the restored one from the rollback file (new ids, created date and
  creator). After 15 days: a new contact from the saved fields.
- The rename: LastName back to the saved value. A deleted affiliation: re-insert from the file.
  Duplicate-rule sets: report data, not restored.
- The release: the back-fill's own rollback by id (RUNBOOK). **Warning added there:** back-fill
  contacts now also carry live rows (every girl ticked since 10-02, and after this merge the kept
  contacts of Janasewa and Niharika); deleting a back-fill contact cascades to its live rows.

## Not in this plan (BACKLOG)
- The processor: `normalizeSpace()` on both sides of the name match and `ORDER BY CreatedDate` on
  the club's contacts (vendor code; its own plan and Ryan's go).
- Days where Salesforce holds fewer rows than ticks (Maridians 09-17/24/30: 11-12 rows against 19-20
  ticks, the fuller re-submissions refused as same-day duplicates; 11 back-fill sessions held as
  `salesforce_has_different_count`).
- 11 girls with contacts in both "Las Camelias" and "Las Camelias Primaria" (a club decision, not a
  merge).
- A guard in `sf_backfill.py` against deleting back-fill contacts that carry live rows.

## Build notes (2026-10-07, branch `wf20/sf-dupes`; offline only, nothing run against Salesforce)
- `tools/sf_dupes.py`, `test/sf_dupes_test.py` (fictional names; a fake org with a small SOQL
  evaluator that also plays the Apex's guards), `glow/salesforce.py` gains `Org.query_all`
  (REST queryAll, deleted and merged contacts) and `Org.delete`; `query` is unchanged.
- The rehearsal's exception class is `RehearsalEndException` (Apex requires a custom exception's
  name to end in "Exception"); its message stays `SF_DUPES_REHEARSAL_END`. The tool counts a
  rehearsal as passed only with that message (bare, or after `[...].RehearsalEndException: `) and
  the `DIAG|ok|<club>` line; the CLI's exact wording for a custom exception is not yet seen live -
  any other wording fails safe (the rehearsal reports a failure, nothing is applied).
- A group whose copies are stored with odd whitespace (a twin of the Alpha contact, or two equally
  odd copies) is compared in the Apex on normalized names (format characters dropped, whitespace
  runs one space, trimmed); every other group exactly with `String.equals`. So `rename` and
  `merge` work in either order.
- An account is matched to a Roster club by its `<club> - <partner>` name first; by the plain club
  name only when exactly one active club has it and no other Club account carries that club's long
  name. `check` (d) compares with every Roster row of a club, any status (a girl who moved club is
  not reported).
- `merge --apply` checks the quiet window again before each further Apex run, and records each run
  in `merge_rollback.json` as `running` before it starts; a run whose answer was lost is `unknown`
  and the next `merge` settles it with queryAll (all merged: `done`; none: `not_applied`). The Apex
  additionally asserts the planned participant count, that the merged contacts are gone, that no
  two copies hold a row on one date, and rows per date per kept contact before = after.
- Only the three DIAG shapes the Apex writes are printed (`merged`, `limits`, `ok`; every field an
  id or a count); any other `DIAG|` line, e.g. other code's, is replaced by a placeholder.
- `cleanup --apply` also refuses in the quiet window and NPSP's hour. For `merge`, `rename` and
  `cleanup` the default folder is the plan's own folder (`check` writes nothing; `plan` writes to
  `data/sf_dupes_<UTC date>/`). Log files are `logs/<stamp>_<club>_<part>.json`.
- Not verifiable offline, so proven by the rehearsal before any `--apply`: the Apex compiles (user
  methods in an anonymous block, `Database.merge(sObject, List<Id>, Boolean)`), NPSP's merge
  triggers stay inside the limits (`DIAG|limits`; else `--per-run`), and a debug log over 20 MB
  could lose early lines (the `DIAG|ok` line is the last, so a truncated log still shows it).
