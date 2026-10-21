---
title: Duplicate and obsolete flags on Account and Contact, and Account duplicate rules that report only
author: Claude (with Ryan's working answers of 2026-10-21)
status: in-progress      # ticket #84; planned 2026-10-21, nothing deployed: the deploy waits for Ryan's go
created: 2026-10-21
intent: none - the SOW item (p.9) and GLOW's questions on it, ticket #84
---

# Plan: "Duplicate Record" and "Obsolete Record" flags, one Account matching rule, report-only duplicate rules

Ticket #84 (epic #68). The SOW (p.9) asks for Duplicate Record and Obsolete Record checkbox
fields on Account and Contact and for one Matching Rule and one Duplicate Rule on Account.
Ryan, 2026-10-21: "move forward with this" - his working answers (on the ticket) hold until GLOW
defines the terms, and GLOW can change any of them before the deploy, which waits for his go.
The definitions are in the RUNBOOK ("Duplicate and obsolete records in Salesforce") and in
DECISIONS 2026-10-21, with the review's two design changes of 2026-10-21 (the obsolete Club
exception for the three Salesforce-reporting partners; one Duplicate Rule per record type in
place of a RecordTypeId matching item); the batch that sets the flags by them is ticket #85.

## Context

- Risk is high: the duplicate rules sit in the path of live account creation, and the fields go
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
- The matching design (review, 2026-10-21): Salesforce does not allow Record Type as a
  matching-rule field, so the Matching Rule matches Name (Exact, case-insensitive) and ParentId
  (blank matches blank), and "same record type" comes from one report-only Duplicate Rule per
  record type, Club and Household, each with the condition Record Type equals that type.
- The Python side of the rules is `glow.salesforce.duplicate_account_groups` (the same name
  ignoring capitals and spacing, the same parent, the same record type; an accent is a different
  name): what the read-back and the monthly check compare with the rules' `DuplicateRecordSet`s,
  since Salesforce's Exact method ignores case and its handling of spacing is not documented with
  certainty (the proof probes it).
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
   ("Duplicate Record", "Obsolete Record"), default false; the Matching Rule `Account.Name_Parent`
   with two `MatchingRuleItems`, both required - Name with the Exact method (case-insensitive) and
   ParentId (Exact, blank matching blank, so two partner-less strays match); two report-only
   Duplicate Rules on that Matching Rule, one per record type, Club (`Account.Name_Parent_Club_Report`)
   and Household (`Account.Name_Parent_Household_Report`), each with the condition Record Type
   equals that type on the record saved and on the records matched, on create and on edit, Allow
   with Report only, no Alert and no Block (`actionOnInsert` and `actionOnUpdate` `Allow`,
   `operationsOnInsert` and `operationsOnUpdate` `Report`, no `alertText`, `isActive` true);
   Edit on the four fields for administrators, as entries in the partial Admin profile retrieved
   with the fields, and Read on them for the users who read the reports, in the
   `Attendance_Report_Viewer` permission set. RecordTypeId is not a matching item, since
   Salesforce does not allow Record Type as a matching-rule field (review, 2026-10-21). Each
   rule's condition is a `duplicateRuleFilter` whose `duplicateRuleFilterItems` test
   `Account.RecordTypeId` equals the record type's Name - "Club" and "Household Account" (not
   "Household") - for the record saved and for the candidates alike. All three rules go in one
   deploy (a Duplicate Rule needs its Matching Rule in the same package or already active).
3. Check-only: from within `build/`, `sf project deploy start --dry-run -o glow -x package.xml`;
   its result (the components, 0 errors, 0 tests run) is shown to Ryan as it is.
4. Ryan's go: his answer in the main session, given after the check-only's result of step 3 is
   shown to him. A go given before that result covers nothing here; a headless run or a
   subagent cannot ask it.
5. Deploy: from within `build/`, `sf project deploy start -o glow -x package.xml`, the check-only
   command of step 3 with its dry-run flag taken off; record the deploy id and time (UTC).
6. The rolled-back proof, at once, with the rules live, `sf apex run -o glow -f proof.apex` on
   Ryan's go: the script (below, "The proof's script") is pasted in full first in the
   conversation. It inserts two fictional Accounts that meet the criteria the way the processor
   inserts them (Apex DML, one `insert` per record, default options), the second differing from
   the first by case only (same spacing), then a spacing probe (the same name with a double
   space, a separate account), then a second name three times: a partner-less Club account, the
   same name under a fictional partner account (inserted before it), and the same name as a
   partner-less Household account. All seven inserts succeed, and one DuplicateRecordSet holding
   the case-only pair appears (`DIAG|set` with its RecordCount and one `DIAG|item` line per
   member); whether the spacing probe joins that set says how Salesforce's Exact method treats
   spacing, recorded in Result either way. The second name's accounts are expected outside any
   set: the Club under the fictional partner, which only shares a name with another partner's club
   (the plain-name case the deliberate `<club> - <partner>` names never meet), is not matched
   because ParentId keeps twins apart, and the Household account of that name is not matched
   because the record-type condition keeps a Club and a partner apart. Either of those two
   appearing in a set is a failure: stop and deactivate the rules (the Rollback). A missing
   DuplicateRecordSet for the case-only twin is a failure too: stop and deactivate the rules (the
   Rollback). If either insert of the pair is refused (`DUPLICATES_DETECTED` among its error
   codes), the Rollback below follows at once: deactivate the rules. Nothing of the proof is
   kept: the script ends in `Database.rollback(sp);`, its last
   statement, so every record it inserted and every set is rolled back and the org is as before
   (NPSP's triggers run on the inserts meanwhile, rolled back with them). Only `DIAG|` lines, ids
   and counts, are read from the log.
7. Read-back: retrieve the same components into `data/sf_dupflags_2026-10-21/after/` and compare
   with `build/` (expected: Salesforce's normalisation only) and with `before/`. SOQL: `SELECT
   DeveloperName, IsActive, SobjectType FROM DuplicateRule` and the same on `MatchingRule` show
   all three rules active and the Contact rule "First & Last & Account" unchanged (its row and its
   metadata file equal to `before/`); the four fields are in `describe` of each object;
   `glow.salesforce.duplicate_account_groups` over `SELECT Id, Name, ParentId, RecordTypeId FROM
   Account` is compared by Account id with the rules' `DuplicateRecordSet`s and their
   `DuplicateRecordItems` (expected today: 0 groups and 0 sets, the two lists equal). Then the
   docs: this plan's Result, the RUNBOOK's Status line.
8. The next day: SOQL on `Attendance_Batch__c` created since the deploy, none `Failed` with
   `DUPLICATES_DETECTED` among its `Status_Message__c` codes (`glow.salesforce.error_codes`,
   codes only); `python3 tools/auto_sync.py` as a dry run, its Salesforce plan unchanged (every
   region `in-sync`, 0 `SF:` ATTENTION items); `python3 tools/sf_new_clubs.py check --vpn-off …`
   exits 0. Record the counts in Result.

## The proof's script (step 6)

Fictional names only; ids and counts in the debug lines; the last statement is the rollback.

```apex
// Ticket #84: every insert goes through with the Account duplicate rules live, and everything is rolled back.
Savepoint sp = Database.setSavepoint();
Id clubType = '012RP000002uklNYAQ';         // RecordType 'Club' on Account (glow.salesforce.CLUB_RECORD_TYPE)
Id partnerType = '0126A000000cdYFQAY';      // 'Household Account': every partner account has it
Map<Id, DuplicateRule> rules = new Map<Id, DuplicateRule>([
    SELECT Id FROM DuplicateRule WHERE SobjectType = 'Account'
    AND DeveloperName IN ('Name_Parent_Club_Report', 'Name_Parent_Household_Report')]);
// (a) two partner-less Club accounts of one name, the second differing by case only, one insert each,
//     as the processor inserts: expected, ONE set holding both
Account first = new Account(Name = 'Zz Proof Club 84', RecordTypeId = clubType);
insert first;
Account second = new Account(Name = 'ZZ PROOF CLUB 84', RecordTypeId = clubType);
insert second;
// (b) the spacing probe: the same name with a double space (does the Exact method ignore spacing?)
Account spaced = new Account(Name = 'Zz  Proof Club 84', RecordTypeId = clubType);
insert spaced;
// (c) a second name three times: a partner-less Club; the same name under a fictional partner
//     (ParentId keeps twins apart); the same name as a partner-less Household account (the record-type
//     condition keeps a Club and a partner apart): expected, NO set for this name
Account partner = new Account(Name = 'Zz Proof Partner 84', RecordTypeId = partnerType);
insert partner;
Account beta = new Account(Name = 'Zz Proof Beta 84', RecordTypeId = clubType);
insert beta;
Account parented = new Account(Name = 'Zz Proof Beta 84', RecordTypeId = clubType, ParentId = partner.Id);
insert parented;
Account household = new Account(Name = 'Zz Proof Beta 84', RecordTypeId = partnerType);
insert household;
System.debug('DIAG|inserted|' + first.Id + '|' + second.Id + '|' + spaced.Id + '|' + partner.Id + '|'
             + beta.Id + '|' + parented.Id + '|' + household.Id);
for (DuplicateRecordSet s : [SELECT Id, RecordCount, DuplicateRuleId, (SELECT RecordId FROM DuplicateRecordItems)
                             FROM DuplicateRecordSet WHERE DuplicateRuleId IN :rules.keySet()]) {
    System.debug('DIAG|set|' + s.Id + '|' + s.DuplicateRuleId + '|' + s.RecordCount);
    for (DuplicateRecordItem i : s.DuplicateRecordItems) {
        System.debug('DIAG|item|' + s.Id + '|' + i.RecordId);
    }
}
Database.rollback(sp);
```

## Rollback

Deactivate the two Account Duplicate Rules in the org, each rule by the same step, on Ryan's go
(VPN off):
1. Retrieve the rules fresh into `data/sf_dupflags_2026-10-21/rollback_<date>/` and compare with
   `after/`; the rollback is built from that retrieve, never from an older copy (DECISIONS
   2026-10-16).
2. Set `<isActive>false</isActive>` in
   `duplicateRules/Account.Name_Parent_Club_Report.duplicateRule-meta.xml` and in
   `duplicateRules/Account.Name_Parent_Household_Report.duplicateRule-meta.xml`, check-only
   with `sf project deploy start --dry-run -o glow -d force-app`, Ryan's go, then
   `sf project deploy start -o glow -d force-app`; or, when a minute matters, in Setup, Duplicate
   Rules, deactivate each rule by hand and retrieve them afterwards for the record. SOQL then
   shows `IsActive` false on both, and the Matching Rule may be deactivated the same way
   afterwards (an active Duplicate Rule holds its Matching Rule active).
3. The four fields and the flags already set stay: a flag is report data. A field goes only on a
   decision of GLOW's, by a destructive deploy of its own. The sets the rules wrote are report
   data too and are left where they are.

## Risks

- **The rules in the path of live account creation.** Mitigation: Report only (no save is
  touched), the rolled-back proof with the rules live right after the deploy, and the next day's
  batch check. If an insert is refused all the same, the Rollback.
- **Record Type as a Duplicate Rule condition.** A record whose type is neither Club nor
  Household meets no rule; the org uses only these two on Account (read 2026-10-21). A third type
  would need a third rule.
- **Salesforce's Exact method and spacing.** The rules may report fewer twins than the Python
  side (a double space). Mitigation: the proof's spacing probe says which it is; the read-back and
  the monthly check compare the two lists, and a difference is looked at by hand, by id.
- **GLOW changes a definition.** Only the docs and the batch (#85) carry the criteria; the rules
  themselves carry the duplicate criteria only, so a change of the obsolete criteria costs no
  deploy.

## Proof

- `scripts/harness_tests.sh test/sf_data_quality_test.py` (classes `DuplicateRuleDocs` and
  `DuplicateAccountGroups`) and `make check` → `CHECK PASSED`.
- Live: the rolled-back `sf apex run` (step 6), the read-back (step 7) and the next day's batches
  (step 8).

## Result

Pending (nothing deployed as of 2026-10-21): the fresh retrieve into `before/`, the check-only,
Ryan's go, the deploy, the rolled-back `sf apex run` proof (with what the spacing probe showed),
the read-back into `after/` and its compare, and the next day's batch check. Written here with
deploy ids, times (UTC) and counts when done.
