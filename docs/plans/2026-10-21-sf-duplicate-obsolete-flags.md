---
title: Duplicate and obsolete flags on Account and Contact, and an Account duplicate rule that reports only
author: Claude (with Ryan's working answers of 2026-10-21)
status: in-progress      # ticket #84; planned 2026-10-21, nothing deployed: the deploy waits for Ryan's go
created: 2026-10-21
intent: none - the SOW item (p.9) and GLOW's questions on it, ticket #84
---

# Plan: "Duplicate Record" and "Obsolete Record" flags, one Account duplicate rule

Ticket #84 (epic #68). The SOW (p.9) asks for Duplicate Record and Obsolete Record checkbox
fields on Account and Contact and for one Matching Rule and one Duplicate Rule on Account.
Ryan, 2026-10-21: "move forward with this" - his working answers (on the ticket) hold until GLOW
defines the terms, and GLOW can change any of them before the deploy, which waits for his go.
The definitions are in the RUNBOOK ("Duplicate and obsolete records in Salesforce") and in
DECISIONS 2026-10-21; the batch that sets the flags by them is ticket #85.

## Context

- Risk is high: the duplicate rule sits in the path of live account creation, and the fields go
  on every Contact, the girls' records included. BACKLOG 54 is the precedent: the Alert on the
  Contact rule "First & Last & Account" failed live attendance batches mid-way until 2026-10-01,
  when it became Report only. That rule is never changed here.
- What creates Accounts by code: the attendance processor (`AttendanceBatchProcessor`, a
  partner-less Club account when a submitted club name matches no Account), `tools/sf_new_clubs.py`
  (the accounts of new clubs, from the automatic sync as GLOW Sync) and the Jotform integration
  (every batch). An alert refuses such a record, and over REST would need the
  `Sforce-Duplicate-Rule-Header: allowSave=true` header on every insert.
- Read on 2026-10-21 (counts only): 455 Accounts (372 clubs, 83 partners), 0 groups of Accounts
  with one name under one parent and record type; 7 clubs of different partners share 3 names and
  are named `<club> - <partner>` on purpose (RUNBOOK "Club names two partners share"); 14
  possible-duplicate sets on the Contact rule; the Account object has no duplicate rule.
- The Python side of the Account rule is `glow.salesforce.duplicate_account_groups` (the same
  name ignoring capitals and spacing, the same parent, the same record type; an accent is a
  different name): what the read-back and the monthly check compare with the rule's
  `DuplicateRecordSet`s, since Salesforce's Exact method ignores case and its handling of spacing
  is not documented with certainty.
- Duplicates of girls are handled by `tools/sf_dupes.py` by its own key (RUNBOOK "Duplicate
  girls in Salesforce"); that path is unchanged.

## Rollout

All with the VPN off, through the `sf` CLI login `glow` (`.claude/skills/salesforce`); every
write waits for Ryan's go in the main session, never a subagent (epic #68). `data/` is never
committed; the build is written there by script or `cp`.
1. Retrieve fresh into `data/sf_dupflags_2026-10-21/before/`: the `Account` and `Contact`
   objects (their fields; none of the four exists yet), every `DuplicateRule` and `MatchingRule`
   (the Contact rule "First & Last & Account" among them), the `Attendance_Report_Viewer`
   permission set and the Admin profile, with `sf project retrieve start -o glow -x package.xml`
   from a manifest in that folder. Record the retrieve's date and time (UTC).
2. Build in a copy, `data/sf_dupflags_2026-10-21/build/` (an SFDX project with `package.xml` and
   a `BUILD.md`), offline: the four checkbox fields `Account.Duplicate_Record__c`,
   `Account.Obsolete_Record__c`, `Contact.Duplicate_Record__c` and `Contact.Obsolete_Record__c`
   ("Duplicate Record", "Obsolete Record"), default false; the Matching Rule
   `Account.Name_Parent_Record_Type` with three `MatchingRuleItems`, all required - Name with the
   Exact method (case-insensitive), ParentId (Exact, blanks matching blanks, so two partner-less
   strays match) and RecordTypeId (Exact); the Duplicate Rule `Account.Name_Parent_Record_Type_Report`
   on that Matching Rule, on create and on edit, Allow with Report only, no Alert and no Block
   (`actionOnInsert` and `actionOnUpdate` `Allow`, `operationsOnInsert` and `operationsOnUpdate`
   `Report`, no `alertText`, `isActive` true); Edit on the four fields for administrators, as
   entries in the partial Admin profile retrieved with the fields, and Read on them for the users
   who read the reports, in the `Attendance_Report_Viewer` permission set. Both rules go in one
   deploy (a Duplicate Rule needs its Matching Rule in the same package or already active).
   Should Salesforce's rule editor or the check-only refuse `RecordTypeId` as a matching item, ask
   Ryan before any deploy: the alternatives (the record type as the Duplicate Rule's condition, a
   text field mirroring it) change what the rule matches and the Python side with it.
3. Check-only: from within `build/`, `sf project deploy start --dry-run -o glow -x package.xml`;
   its result (the components, 0 errors, 0 tests run) is shown to Ryan as it is.
4. Ryan's go: his answer in the main session, given after the check-only's result of step 3 is
   shown to him. A go given before that result covers nothing here; a headless run or a
   subagent cannot ask it.
5. Deploy: from within `build/`, `sf project deploy start -o glow -x package.xml`, the check-only
   command of step 3 with its dry-run flag taken off; record the deploy id and time (UTC).
6. The rolled-back proof, at once, with the rule live, `sf apex run -o glow -f proof.apex` on
   Ryan's go: the script (below, "The proof's script") is pasted in full first in the
   conversation. It inserts two fictional Accounts that meet the criteria the way the processor
   inserts them (Apex DML, one `insert` per record, default options), after a fictional partner
   account that gives the third club another parent. Both inserts succeed, and one
   DuplicateRecordSet holding the two appears (`DIAG|set` with RecordCount 2 and two `DIAG|item`
   lines). A third Account that only shares the name with another partner's club, as the
   `<club> - <partner>` clubs do, is not matched: its parent differs. If either insert is refused
   (`DUPLICATES_DETECTED` among its error codes), the Rollback below follows at once: deactivate
   the rule. Nothing of the proof is kept: the script ends in `Database.rollback(sp);`, its last
   statement, so every record it inserted and every set is rolled back and the org is as before
   (NPSP's triggers run on the inserts meanwhile, rolled back with them). Only `DIAG|` lines, ids
   and counts, are read from the log. Should the query find no set although both inserts
   succeeded (a set written outside the transaction), the proof of the rule's action still holds,
   and the set check is the monthly check's, the first time a stray twin appears.
7. Read-back: retrieve the same components into `data/sf_dupflags_2026-10-21/after/` and compare
   with `build/` (expected: Salesforce's normalisation only) and with `before/`. SOQL: `SELECT
   DeveloperName, IsActive, SobjectType FROM DuplicateRule` and the same on `MatchingRule` show
   both rules active and the Contact rule "First & Last & Account" unchanged (its row and its
   metadata file equal to `before/`); the four fields are in `describe` of each object;
   `glow.salesforce.duplicate_account_groups` over `SELECT Id, Name, ParentId, RecordTypeId FROM
   Account` is compared with the rule's `DuplicateRecordSet`s (expected today: 0 groups and 0 sets,
   the two lists equal). Then the docs: this plan's Result, the RUNBOOK's Status line.
8. The next day: SOQL on `Attendance_Batch__c` created since the deploy, none `Failed` with
   `DUPLICATES_DETECTED` among its `Status_Message__c` codes (`glow.salesforce.error_codes`,
   codes only); `python3 tools/auto_sync.py` as a dry run, its Salesforce plan unchanged (every
   region `in-sync`, 0 `SF:` ATTENTION items); `python3 tools/sf_new_clubs.py check --vpn-off …`
   exits 0. Record the counts in Result.

## The proof's script (step 6)

Fictional names only; ids and counts in the debug lines; the last statement is the rollback.

```apex
// Ticket #84: both inserts go through with the Account duplicate rule live, and everything is rolled back.
Savepoint sp = Database.setSavepoint();
Id clubType = '012RP000002uklNYAQ';         // RecordType 'Club' on Account (glow.salesforce.CLUB_RECORD_TYPE)
Id partnerType = '0126A000000cdYFQAY';      // 'Household Account': every partner account has it
DuplicateRule rule = [SELECT Id FROM DuplicateRule
                      WHERE SobjectType = 'Account' AND DeveloperName = 'Name_Parent_Record_Type_Report'];
// a fictional partner, so that the third club has another parent
Account partner = new Account(Name = 'Zz Proof Partner 84', RecordTypeId = partnerType);
insert partner;
// two partner-less Club accounts of one name, one insert each, as the processor inserts
Account first = new Account(Name = 'Zz Proof Club 84', RecordTypeId = clubType);
insert first;
Account second = new Account(Name = 'ZZ  proof club 84', RecordTypeId = clubType);
insert second;
// a club that only shares the name, under the fictional partner
Account third = new Account(Name = 'Zz Proof Club 84', RecordTypeId = clubType, ParentId = partner.Id);
insert third;
System.debug('DIAG|inserted|' + first.Id + '|' + second.Id + '|' + third.Id);
for (DuplicateRecordSet s : [SELECT Id, RecordCount, (SELECT RecordId FROM DuplicateRecordItems)
                             FROM DuplicateRecordSet WHERE DuplicateRuleId = :rule.Id]) {
    System.debug('DIAG|set|' + s.Id + '|' + s.RecordCount);
    for (DuplicateRecordItem i : s.DuplicateRecordItems) {
        System.debug('DIAG|item|' + s.Id + '|' + i.RecordId);
    }
}
Database.rollback(sp);
```

## Rollback

Deactivate the Account Duplicate Rule in the org, on Ryan's go (VPN off):
1. Retrieve the rule fresh into `data/sf_dupflags_2026-10-21/rollback_<date>/` and compare with
   `after/`; the rollback is built from that retrieve, never from an older copy (DECISIONS
   2026-10-16).
2. Set `<isActive>false</isActive>` in
   `duplicateRules/Account.Name_Parent_Record_Type_Report.duplicateRule-meta.xml`, check-only
   with `sf project deploy start --dry-run -o glow -d force-app`, Ryan's go, then
   `sf project deploy start -o glow -d force-app`; or, when a minute matters, in Setup, Duplicate
   Rules, deactivate the rule by hand and retrieve it afterwards for the record. SOQL then shows
   `IsActive` false on it, and the Matching Rule may be deactivated the same way afterwards (an
   active Duplicate Rule holds its Matching Rule active).
3. The four fields and the flags already set stay: a flag is report data. A field goes only on a
   decision of GLOW's, by a destructive deploy of its own. The sets the rule wrote are report data
   too and are left where they are.

## Risks

- **The rule in the path of live account creation.** Mitigation: Report only (no save is touched),
  the rolled-back proof with the rule live right after the deploy, and the next day's batch check.
  If an insert is refused all the same, the Rollback.
- **`RecordTypeId` as a matching item** may be refused by the rule editor or the check-only.
  Mitigation: step 2's note - ask Ryan, since every alternative changes what the rule matches.
- **Salesforce's Exact method and spacing.** The rule may report fewer twins than the Python side
  (a double space). Mitigation: the read-back and the monthly check compare the two lists; a
  difference is looked at by hand, by id.
- **GLOW changes a definition.** Only the docs and the batch (#85) carry the criteria; the rule
  itself carries the duplicate criteria only, so a change of the obsolete criteria costs no deploy.

## Proof

- `scripts/harness_tests.sh test/sf_data_quality_test.py` (classes `DuplicateRuleDocs` and
  `DuplicateAccountGroups`) and `make check` → `CHECK PASSED`.
- Live: the rolled-back `sf apex run` (step 6), the read-back (step 7) and the next day's batches
  (step 8).

## Result

Pending (nothing deployed as of 2026-10-21): the fresh retrieve into `before/`, the check-only,
Ryan's go, the deploy, the rolled-back `sf apex run` proof, the read-back into `after/` and its
compare, and the next day's batch check. Written here with deploy ids, times (UTC) and counts
when done.
