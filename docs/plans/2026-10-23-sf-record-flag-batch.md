---
title: Historical duplicate and obsolete Accounts and Contacts flagged by Batch Apex (RecordFlagBatch), the sheet's criteria carried by a read-only script writer
author: Claude (Ryan's decisions of 2026-10-23: 1a, 2a and the Contact workflow guard; 2026-10-24: a flag run only sets)
status: accepted      # ticket #85; nothing has run: the check-only, the deploy, the dry run and the run each still wait for Ryan's go
created: 2026-10-23
intent: none - SOW p.9 (Batch Apex over the historical records), ticket #85
---

# Plan: flag the historical duplicate and obsolete records with `RecordFlagBatch`

Ticket #85 (epic #68). The SOW (p.9) asks for Batch Apex that evaluates the existing Account and
Contact records against the agreed duplicate and obsolete criteria and sets the "Duplicate Record"
and "Obsolete Record" fields that ticket #84 created on 2026-10-22 (RUNBOOK "Duplicate and obsolete
records in Salesforce"; DECISIONS 2026-10-21 and 2026-10-22). Merging or cleaning the records is
out of scope (SOW p.10): a flag marks a record and the record keeps everything it has. Ryan's
decisions of 2026-10-23 (DECISIONS 2026-10-23, the flagging entry): 1a, a read-only Python step
carries the two criteria only the Google Sheet holds; 2a, every member of a duplicate group is
flagged; (a), the two NPSP Contact workflow rules are accepted as harmless under a guard. After the
review of PR #133, Ryan's decision of 2026-10-24, option (a): a `flag` run only sets a flag and
never unsets one, so a flag set by hand on a record outside the criteria stays; a flag comes off
only through `clear`, after the hand-set flags are counted (step 4). Nothing has run yet: the
check-only validate, the deploy, the dry run and the run each still wait for Ryan's go (Result).

## Context

- Risk is high: DML in bulk on Account and Contact, the girls' records included (about 2,000 or
  more Contacts; 455 Accounts on 2026-10-21), so scopes of 200; automation fires on update; a
  flagged record gets a new `LastModifiedDate`. A Contact flagged Duplicate is not merged here:
  `tools/sf_dupes.py` stays the merge path (RUNBOOK "Duplicate girls in Salesforce"). How the
  reports treat flagged records is #84's answer (shown, with the flags as a filter).
- The class `RecordFlagBatch` (`Database.Batchable<SObject>`, `Database.Stateful`) and its test
  class `RecordFlagBatchTest` (eleven methods, fictional records) live in
  `data/sf_record_flags_2026-10-23/build/force-app/main/default/classes/` (an SFDX project,
  `sfdx-project.json` at `build/`; never in git). Constructors `RecordFlagBatch(sobjectType, mode)`
  and `RecordFlagBatch(sobjectType, mode, deactivatedClubIds, partnerReportPartnerIds)`;
  `sobjectType` is `Account` or `Contact`, `mode` is `dryRun` (counts, writes nothing), `flag`
  (sets a flag where the criteria ask for one and never unsets one: a flag set by hand outside the
  criteria, or a flag the criteria no longer ask for, stays) or `clear` (both flags false on every
  record that has one, a flag set by hand included: `clear` alone takes a flag off). It writes
  only the two flag fields, through a fresh SObject carrying the Id and the two fields, and only
  records whose flag changes (a second run writes nothing); `Database.update` with `allOrNone`
  false, so one locked row costs one record, not the scope; `finish` fills
  `RecordFlagBatch.lastCounts` (`duplicate`, `obsolete`, `written`, `failed`) and logs those counts
  only, never a name, an id or a field's value.
- Duplicates (2a: every member, no keeper). Account: the same Name ignoring capitals and spacing
  (every run of whitespace, the no-break space included, folded to one space and trimmed, then
  `toLowerCase`), the same ParentId (blank matches blank) and the same RecordTypeId, judged in
  code over every Account once per run, as `glow.salesforce.duplicate_account_groups` judges them
  - but for the sharp s: that side casefolds, so `Straße` and `STRASSE` are one name there and
  two to the batch (RUNBOOK "Duplicate and obsolete records in Salesforce", The flagging batch).
  `Datacloud.FindDuplicates` is not used: it does not see records inserted in the same uncommitted
  transaction (DECISIONS 2026-10-22), so the Apex tests could not prove it, and it takes 50
  records a call. Contact: a member of a `DuplicateRecordSet` of the Contact rule `First_Last`
  ("First & Last & Account") that holds two or more records; a set left with one item after a
  merge is no group (`tools/sf_dupes.py cleanup` deletes such sets).
- Obsolete. Account: `Partner_Status__c` Archived; a Club (record type Club) whose id is in
  `deactivatedClubIds`; a Club created more than 6 months ago with no `Attendance_Batch__c` on it
  (`Account__c`, by `Attendance_Date__c`, any status) in the last 6 months - a Club whose
  `ParentId` is in `partnerReportPartnerIds` is judged by its partner account's `Partner report`
  batches (`Creator__c`) instead of its own. Nothing else: a young quiet Club, or a Club of an
  Archived partner, is not obsolete. Contact: `Contact_Role__c` Participant with no
  `Attendance__c` row (`Attendance_Date__c`) in the last 12 months; every other role never.
- The sheet's criteria (1a): `tools/sf_record_flags.py` (`test/sf_record_flags_test.py`), read
  only, reads the day's Roster and Partners exports and the Accounts (`SELECT Id, Name,
  RecordTypeId, ParentId FROM Account`), works out the Club account of each club deactivated in
  the Roster (no active row, by `glow.sync`'s own rule; the account named as question 5 sends the
  club, the plain name or `<club> - <partner>` when a Club account carries it, compared with
  `glow.salesforce.sf_match`; of two Club accounts of the name, the one under the club's partner,
  `glow/sf_partners.csv`) and the account of each partner marked `no` in the Partners tab's
  `jotform` column, and writes the anonymous Apex, ids only. A club with no account or with twins
  the parent does not tell apart, a marked partner missing from the map, and a Partners export
  without the `jotform` column each stop it naming what to fix. For Contact it writes the
  two-argument call, after the guard below.
- Automation on update, read 2026-10-23 06:42 UTC (VPN off, read only; the retrieve in
  `data/sf_record_flags_2026-10-23/before/`, the notes in `evidence/automation_2026-10-23.txt`;
  names and counts only). Account: the record-triggered Flow
  `Opportunity_Account_Owner_Update_remove_Access_2` runs only when `OwnerId` changes, which the
  batch never changes; 0 workflow rules: harmless. Contact: 13 active workflow rules (12 NPSP, 1
  Volunteers), 14 field updates, 2 e-mail actions, 1 task. Two rules fire on any edit of a
  Contact whose Email or Phone is blank: `npe01 Contact.Preferred_Email__c` fills Email from the
  Work, Home or Alternate e-mail field, `Preferred_Phone__c` fills Phone from the Work, Home,
  Mobile or Other phone field; the Volunteers signup rule mails for a web signup of the day; the
  other rules need a changed Email or Phone or a new record. The NPSP TDTM handlers (address,
  household, affiliation, relationship: they act when their own fields change) and MC4SF (0 async
  jobs in 30 days, so no callout) are accepted as harmless; NPSP triggers stay on (Ryan,
  2026-10-23: "a, accept").
- The guard (Ryan, 2026-10-23, option a): the two rules are accepted under a guard rather than
  deactivated for the run. The three counts - Contacts with a blank Email and a Work, Home or
  Alternate e-mail set; with a blank Phone and a Work, Home, Mobile or Other phone set; with
  `GW_Volunteers__Volunteer_Last_Web_Signup_Date__c` = TODAY - were 0, 0 and 0 on 2026-10-23;
  they are counted again right before the dry run and the Contact run, and the tool counts them
  itself before it writes any Contact script and refuses the script while any is not 0. The Apex
  test `writesOnlyTheTwoFlagFields` uses fictional Contacts shaped like today's girls (blank Email
  and Phone, no other e-mail or phone set) and proves no other field changes on them.
- Dates: a Club's six months and a girl's twelve are read on `Attendance_Date__c` (the session
  date), not on a record's `CreatedDate` (the September back-fill batches were created on
  2026-10-02 for September sessions). The created-more-than-6-months-ago condition reads the
  Account's `CreatedDate`, so the clubs created in September 2026 are not flagged before March
  2027.

## Rollout

All with the VPN off, through the `sf` CLI login `glow` (`.claude/skills/salesforce`), from the
repository root but for the deploy steps, which run from within the build. Every write of this
rollout - the check-only validate (the hook gates it too), the deploy, each anonymous Apex run -
waits for Ryan's go in the main session, never a subagent or a headless run (epic #68); his
answer to that step's prompt is the go, and nothing said earlier stands for it. The class
`RecordFlagBatch` was written offline against `RecordFlagBatchTest` and desk-checked, not
compiled: the check-only of step 1 is its first compile. `tools/sf_record_flags.py` writes each
script; `data/` is never committed, and the scripts, the logs and the saved ids live in
`data/sf_record_flags_2026-10-23/` (owner only).

1. Check-only validate of the build, from within `data/sf_record_flags_2026-10-23/build/`
   (`sfdx-project.json`; `force-app/main/default/classes/` with `RecordFlagBatch.cls`,
   `RecordFlagBatchTest.cls` and their `-meta.xml`, API 62.0), on Ryan's go:

   ```bash
   sf project deploy validate -o glow -d force-app --test-level RunSpecifiedTests --tests RecordFlagBatchTest
   ```

   Expected: 2/2 components, 0 errors, every method of the test class passed, coverage of
   `RecordFlagBatch` at least 75 % (the org's minimum; aimed well above). The result, with the
   validation id (`0Af…`), is shown to Ryan as it is. A compile error or a failed method means
   the class is fixed offline and this step runs again; nothing deploys from a failed check-only.
2. Deploy: the quick deploy (`sf project deploy quick -o glow -i <validation id>`) of that
   check-only, on Ryan's go, given after the result of step 1 is shown to him (a go given before
   it covers nothing; a headless run or a subagent cannot ask it). The validation ran
   `RecordFlagBatchTest`, so the quick deploy runs no test again. Then the read-back of the
   metadata: `sf project retrieve start -o glow -m ApexClass:RecordFlagBatch -m ApexClass:RecordFlagBatchTest -r ../after`
   into `data/sf_record_flags_2026-10-23/after/`, compared with `build/` (expected: equal). Record
   the deploy id and time (UTC) in Result.
3. The guard, right before the dry run: the three counts, read only (the read-only connector, or
   `sf data query -o glow -q "…"`), each expected 0:

   ```sql
   SELECT COUNT() FROM Contact WHERE Email = null AND (npe01__WorkEmail__c != null OR npe01__HomeEmail__c != null OR npe01__AlternateEmail__c != null)
   SELECT COUNT() FROM Contact WHERE Phone = null AND (npe01__WorkPhone__c != null OR HomePhone != null OR MobilePhone != null OR OtherPhone != null)
   SELECT COUNT() FROM Contact WHERE GW_Volunteers__Volunteer_Last_Web_Signup_Date__c = TODAY
   ```

   The first is the Contacts whose blank Email the NPSP rule `Preferred_Email__c` would fill at
   any edit, the second the Contacts whose blank Phone `Preferred_Phone__c` would fill, the third
   the Volunteers web signups of the day, whose rule sends mail. The rollout goes on only while
   each count is 0; a count above 0 stops it here and Ryan decides (option b of the ticket, the
   two rules deactivated for the run by a deploy of their own and re-activated after, is the
   fallback). `tools/sf_record_flags.py --sobject Contact` runs these three counts itself before
   it writes a Contact script (steps 5 and 8), so a count that rises in between is caught.
4. The flags set by hand, counted before any run: `clear` would take them off too, so this count
   says how many to set again by hand after a rollback (administrators alone set a flag by hand;
   the fields were created on 2026-10-22 with every flag false, so 0 is expected on each):

   ```sql
   SELECT COUNT() FROM Account WHERE Duplicate_Record__c = true
   SELECT COUNT() FROM Account WHERE Obsolete_Record__c = true
   SELECT COUNT() FROM Contact WHERE Duplicate_Record__c = true
   SELECT COUNT() FROM Contact WHERE Obsolete_Record__c = true
   SELECT Id FROM Account WHERE Duplicate_Record__c = true OR Obsolete_Record__c = true
   SELECT Id FROM Contact WHERE Duplicate_Record__c = true OR Obsolete_Record__c = true
   ```

   The ids, if any, go to `data/sf_record_flags_2026-10-23/hand_set_before.csv` (ids only).
5. The dry run, on Ryan's go: today's exports of the Roster and the Partners tab, then
   `tools/sf_record_flags.py` in `dryRun` mode writes each script - ids and counts only; the
   Account script carries the deactivated clubs' Club account ids and the `jotform=no` partners'
   account ids, the Contact script is written only when the three guard counts the tool runs are
   0 - each script is pasted in full in the session, and `sf apex run` runs it:

   ```bash
   python3 tools/sheets_client.py export Roster data/roster_<date>.csv
   python3 tools/sheets_client.py export Partners data/partners_<date>.csv
   python3 tools/sf_record_flags.py --sobject Account --mode dryRun --roster data/roster_<date>.csv --partners data/partners_<date>.csv --out data/sf_record_flags_2026-10-23/scripts/account_dryRun.apex --vpn-off
   sf apex run -o glow -f data/sf_record_flags_2026-10-23/scripts/account_dryRun.apex
   sf data query -o glow -q "SELECT Id, Status, JobItemsProcessed, TotalJobItems, NumberOfErrors, CreatedDate FROM AsyncApexJob WHERE ApexClass.Name = 'RecordFlagBatch' ORDER BY CreatedDate DESC LIMIT 1"
   python3 tools/sf_record_flags.py --sobject Contact --mode dryRun --out data/sf_record_flags_2026-10-23/scripts/contact_dryRun.apex --vpn-off
   sf apex run -o glow -f data/sf_record_flags_2026-10-23/scripts/contact_dryRun.apex
   sf data query -o glow -q "SELECT Id, Status, JobItemsProcessed, TotalJobItems, NumberOfErrors, CreatedDate FROM AsyncApexJob WHERE ApexClass.Name = 'RecordFlagBatch' ORDER BY CreatedDate DESC LIMIT 1"
   ```

   Each `sf apex run` starts a batch job and prints no job id (a one-statement script prints
   nothing): the read-only `AsyncApexJob` query right after it, newest first, gives the job's id
   (`707…`, 18 characters), its `Status` and, once `Completed`, `JobItemsProcessed`,
   `TotalJobItems` and `NumberOfErrors`; the id is recorded. When the job is finished, its finish
   line in the debug log,
   `RecordFlagBatch|<object>|dryRun|duplicate=N|obsolete=N|written=0|failed=0`, gives the counts
   (a trace flag on Ryan's user for the hour; `sf apex get log -o glow -i <log id>`, or Setup,
   Debug Logs). The counts per object and flag go on the ticket and in Result. A `written` other
   than 0 in a dry run is a bug: stop, fix the class, back to step 1.
6. Ryan confirms the counts: the dry run's counts per object and flag (Account duplicate,
   Account obsolete, Contact duplicate, Contact obsolete) are put on the ticket, and Ryan confirms
   them in a comment or in the session before any `flag` run. A count he does not expect (the
   reads of 2026-10-21: 0 Account groups, 14 Contact sets of the Contact rule, every girl with
   attendance) is looked at by id first - the ids behind a count come from the dry run's criteria
   re-read by SOQL, into `data/` - and the criteria, the sheet or the class are fixed and the
   dry run (step 5) repeated.
7. The run for Account, `--mode flag` (flag mode), on Ryan's go, at a quiet hour: not during the
   automatic sync's run (11:00 UTC daily, and after a roster change: `.github/workflows/auto-sync.yml`),
   nor a form-submission peak, nor NPSP's nightly job window (20:30-21:30 UTC,
   `tools/sf_dupes.py`), with fresh exports of the day:

   ```bash
   python3 tools/sf_record_flags.py --sobject Account --mode flag --roster data/roster_<date>.csv --partners data/partners_<date>.csv --out data/sf_record_flags_2026-10-23/scripts/account_flag.apex --vpn-off
   sf apex run -o glow -f data/sf_record_flags_2026-10-23/scripts/account_flag.apex
   sf data query -o glow -q "SELECT Id, Status, JobItemsProcessed, TotalJobItems, NumberOfErrors, CreatedDate FROM AsyncApexJob WHERE ApexClass.Name = 'RecordFlagBatch' ORDER BY CreatedDate DESC LIMIT 1"
   ```

   The script is pasted in full first (ids only). Record the AsyncApexJob id (the read-only
   `AsyncApexJob` query, newest first: `sf apex run` prints none), the date and the time (UTC);
   when the job is finished, its finish line gives duplicate, obsolete, written and
   failed (expected: failed 0; duplicate and obsolete equal to the dry run's; written the records
   whose flag changed, at most duplicate plus obsolete).
8. The guard again, then the run for Contact, `--mode flag` (flag mode), on Ryan's go, right
   after the Account run at the same quiet hour. `tools/sf_record_flags.py --sobject Contact`
   runs the three counts first - the Contacts with a blank Email and another e-mail set, with a
   blank Phone and another phone set, the Volunteers signups of the day - prints them, and writes
   the script only when each is 0; a count above 0 stops the Contact run here, the refusal naming
   the count that is not 0 (then step 3's fallback):

   ```bash
   python3 tools/sf_record_flags.py --sobject Contact --mode flag --out data/sf_record_flags_2026-10-23/scripts/contact_flag.apex --vpn-off
   sf apex run -o glow -f data/sf_record_flags_2026-10-23/scripts/contact_flag.apex
   sf data query -o glow -q "SELECT Id, Status, JobItemsProcessed, TotalJobItems, NumberOfErrors, CreatedDate FROM AsyncApexJob WHERE ApexClass.Name = 'RecordFlagBatch' ORDER BY CreatedDate DESC LIMIT 1"
   ```

   The script is pasted in full first. Record the AsyncApexJob id (the read-only `AsyncApexJob`
   query, newest first), the date and the time (UTC), and the finish line's counts, as for Account.
9. The read-back: the SOQL count of each flag on each object equals the dry run's count (step 5),
   which the run's finish line repeats (steps 7 and 8), plus the flags step 4 counted on records
   outside the criteria: a `flag` run never unsets a flag set by hand, so those stay through the
   run, and the read-back equals the dry run's count alone only while step 4 counts 0 outside
   the criteria. The flagged ids are saved, ids only:

   ```sql
   SELECT COUNT() FROM Account WHERE Duplicate_Record__c = true
   SELECT COUNT() FROM Account WHERE Obsolete_Record__c = true
   SELECT COUNT() FROM Contact WHERE Duplicate_Record__c = true
   SELECT COUNT() FROM Contact WHERE Obsolete_Record__c = true
   SELECT Id FROM Account WHERE Duplicate_Record__c = true OR Obsolete_Record__c = true
   SELECT Id FROM Contact WHERE Duplicate_Record__c = true OR Obsolete_Record__c = true
   ```

   The ids go to `data/sf_record_flags_2026-10-23/flagged.csv` (object, id, which flag; never a
   name). A count that differs from the dry run's plus step 4's count outside the criteria is
   looked at by id before anything else. A `failed` above 0 in a finish line is a locked row (`UNABLE_TO_LOCK_ROW`, codes only):
   the same `flag` run again writes only what is still missing, since a record whose flag is in
   place is not written. Then: `python3 tools/auto_sync.py` as a dry run still `in-sync` for every
   region, and no `Attendance_Batch__c` created since the run is `Failed` with
   `DUPLICATES_DETECTED` (the flags are not in the processor's path, so none is expected).
10. Docs: this plan's Result (per object and flag the dry run's count and the run's count, which
    agree, step 4's count of the flags set by hand outside the criteria, 0 included, and the
    read-back's count, exactly the dry run's plus that hand-set count; each run's AsyncApexJob id
    with its date and time in UTC; then
    `status: done` with `done:`), the RUNBOOK section's run record and Status line, `make
    docs-index`; a DECISIONS bullet if a choice was made along the way.

## Rollback

The rollback is a `clear` run of `RecordFlagBatch` through the same script writer and
`sf apex run`, Account then Contact, on Ryan's go: it sets both flags false on every record that
has one (every flag was false when the fields were created on 2026-10-22). `clear` takes the flags
set by hand by administrators off too, so the count of step 4 says how many to set again by hand,
from `hand_set_before.csv`. `clear` is the only mode that takes a flag off: a `flag` run only sets
a flag and never unsets one (Ryan, 2026-10-24, option a), so a stale flag - an obsolete flag on a
club that reports again - stays until a `clear` run and a `flag` run, each on Ryan's go. The
Contact `clear` script is written only while the guard's three counts are 0, like any Contact
script.

```bash
python3 tools/sf_record_flags.py --sobject Account --mode clear --roster data/roster_<date>.csv --partners data/partners_<date>.csv --out data/sf_record_flags_2026-10-23/scripts/account_clear.apex --vpn-off
sf apex run -o glow -f data/sf_record_flags_2026-10-23/scripts/account_clear.apex
python3 tools/sf_record_flags.py --sobject Contact --mode clear --out data/sf_record_flags_2026-10-23/scripts/contact_clear.apex --vpn-off
sf apex run -o glow -f data/sf_record_flags_2026-10-23/scripts/contact_clear.apex
```

Finer, for one run alone: the ids that run flagged are in `data/sf_record_flags_2026-10-23/flagged.csv`
(the read-back of step 9), so each listed record's flags are set back to false by id, through the
write connector one record at a time, read back after. The class itself leaves the org only by a
destructive deploy of its own (`destructiveChanges.xml` naming `RecordFlagBatch` and
`RecordFlagBatchTest`), and only once the flags are not to be run again; the four fields stay
(ticket #84).

## Risks

- **DML on the girls' records.** Scopes of 200, the two flag fields only, only records whose flag
  changes, `allOrNone` false. Mitigation: the dry run's counts confirmed by Ryan before the run,
  the quiet hour, the read-back by SOQL, and `clear` as the way back.
- **The Contact workflow rules.** `Preferred_Email__c` and `Preferred_Phone__c` would rewrite a
  blank Email or Phone from another field on any edit. Mitigation: the guard's three counts right
  before the dry run and the Contact run, by hand and by the tool; option b (the two rules
  deactivated for the run) as the fallback. The Volunteers rule's mail is guarded the same way.
- **The first compile is the check-only.** The class was desk-checked against every test method,
  not compiled: a compile error or a failed method costs a round of fixes offline and a second
  check-only, never a deploy.
- **Governor limits.** Account groups are computed once per run from one query over every Account
  (455 today) and kept by `Database.Stateful`; per scope of 200 at most two aggregate queries and
  one DML for Account, three queries and one DML for Contact. The test
  `batchOf200StaysWithinGovernorLimits` runs one scope of 200 Contacts and 200 duplicate Clubs.
- **A one-item set.** A Contact in a `DuplicateRecordSet` left with one item (after a merge) is
  not flagged: the batch counts a set's items and flags only the members of a set of two or more.
- **The sheet's criteria go stale.** The Account script carries the day's Roster and Partners
  exports; a club deactivated after the run, or a partner marked later, is picked up by the next
  run (a `flag` run is idempotent, and it only adds). The other way round, a flag the criteria no
  longer ask for - a club that reports again, a partner no longer Archived - is not taken off by a
  `flag` run (Ryan, 2026-10-24, option a): it stays until a `clear` run and a `flag` run, each on
  Ryan's go, with the hand-set flags counted first (step 4).
- **`DuplicateRule` in a test without `SeeAllData`.** The Contact fixtures build their
  `DuplicateRecordSet`s under the rule `First_Last`, read by SOQL on `DuplicateRule`, which
  Salesforce's documented list of setup objects visible to a test without `SeeAllData` does not
  name; the test's `contactRuleId()` asserts the read and names the rule when it fails. If the
  check-only fails there, the fix is never `SeeAllData=true` (it would open the live girls'
  records to the tests): the batch is given the rule id instead - a constructor argument the
  script writer reads, read only, and the tests read the same way - and step 1 runs again.
- **GLOW changes a definition.** The obsolete criteria live in the class and the docs: a change
  is a new check-only and deploy by this plan's steps 1 and 2; the duplicate criteria for
  Accounts are the rules' (#84) and the class's alike.

## Proof

- `scripts/harness_tests.sh test/sf_record_flags_test.py test/sf_data_quality_test.py`: the
  tool's tests and the docs tests (`RecordFlagBatchDocs`), `make check` → `CHECK PASSED` - but for
  `test_the_runbook_records_the_flagging_run`, which stays red by design until the RUNBOOK records
  a run that happened and this plan's Result agrees with it.
- Read only, 2026-10-24, through the read-only connector after the review of PR #133 (schema and
  aggregate counts, no record's fields; the notes in
  `data/sf_record_flags_2026-10-23/evidence/review_reads_2026-10-24.txt`): the Contact rule's
  `DeveloperName` is `First_Last` ("First & Last & Account"), active - the class's `CONTACT_RULE`
  and the test's; the org's two other Contact rules, `NPSP_Contact_Personal_Email_Match` and
  `Standard_Rule_for_Contacts_with_Duplicate_Leads`, are inactive. The fixtures' fields and
  values exist and are in use: `Attendance__c.Present__c` (a checkbox); `Account.Partner_Status__c`
  `Active, In good standing` (51 Accounts) and `Archived` (21); `Contact.Contact_Role__c`
  `Participant` (4,172), `Partnership Coordinator` (79), `Lead Mentor` (14) and `staff` (3, and 2
  more with a trailing space); `Attendance_Batch__c.Creator__c` is free text (`Jotform` 773,
  `Partner report` 3, one `Jotform back-fill …` value per back-filled batch).
- Live: the check-only validate with `RecordFlagBatchTest` (step 1), the dry run (step 5), the
  read-back (step 9).

## Result

Nothing has run yet (2026-10-24): the class and its tests are written and desk-checked, not
compiled; the check-only validate, the deploy, the dry run and the run each still wait for Ryan's
go. When they have happened, this section carries, in order and with counts and ids only: the
check-only's id and result; the deploy id and time (UTC); the guard's three counts; the hand-set
flags' counts; per object and flag the dry run's count and the run's count, which agree, a clause
per object of step 4's count of each flag set by hand outside the criteria (0 included), and the
read-back's count, exactly the dry run's plus that hand-set count (a `flag` run never unsets a
flag); each run's AsyncApexJob id with its date and time (UTC); and the plan goes `status: done`
with its `done:` date.
