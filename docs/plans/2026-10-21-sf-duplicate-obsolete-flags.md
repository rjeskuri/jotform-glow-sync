---
title: Duplicate and obsolete flags on Account and Contact, and Account duplicate rules that report only
author: Claude (with Ryan's working answers of 2026-10-21)
status: in-progress      # ticket #84; deployed 2026-10-22 on Ryan's go; step 8, the next day's batch check, pending
created: 2026-10-21
intent: none - the SOW item (p.9) and GLOW's questions on it, ticket #84
---

# Plan: "Duplicate Record" and "Obsolete Record" flags, one Account matching rule, report-only duplicate rules

Ticket #84 (epic #68). The SOW (p.9) asks for Duplicate Record and Obsolete Record checkbox
fields on Account and Contact and for one Matching Rule and one Duplicate Rule on Account.
Ryan, 2026-10-21: "move forward with this" - his working answers (on the ticket) hold until GLOW
defines the terms, and GLOW can still change any of them (a change to the duplicate criteria
means a new deploy of the rules; the obsolete criteria live in the docs and the batch only).
Deployed 2026-10-22 12:33 UTC on Ryan's go (Result); step 8, the next day's batch check, is
pending. The definitions are in the RUNBOOK ("Duplicate and obsolete records in Salesforce") and
in DECISIONS 2026-10-21, with the review's two design changes of 2026-10-21 (the obsolete Club
exception for the three Salesforce-reporting partners; one Duplicate Rule per record type in
place of a RecordTypeId matching item) and Ryan's two decisions of 2026-10-22 (the proof is a
no-DML diagnostic; cross-type pairs are accepted, DECISIONS 2026-10-22); the batch that sets the
flags by them is ticket #85.

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
- Read on 2026-10-21, before the deploy (counts only): 455 Accounts (372 clubs, 83 partners),
  0 groups of Accounts with one name under one parent and record type; 7 clubs of different
  partners share 3 names and are named `<club> - <partner>` on purpose (RUNBOOK "Club names two
  partners share"); 14 possible-duplicate sets on the Contact rule; and the Account object had
  no duplicate rule then (it has the two below since the deploy of 2026-10-22).
- The matching design (review, 2026-10-21): Salesforce does not allow Record Type as a
  matching-rule field, so the Matching Rule matches Name (Exact, case-insensitive) and ParentId
  (blank matches blank), and "same record type" comes, for the record saved, from one report-only
  Duplicate Rule per record type, Club and Household, each with the condition Record Type equals
  that type. That condition picks only which rule runs for the record being saved and does not
  limit the candidates (the records the Matching Rule finds, whatever their record type), so
  Salesforce may report a Household account and a Club of one name and parent as a pair: the
  diagnostic showed it on 2026-10-22, and Ryan accepted it the same day, documented here and in
  the RUNBOOK, with no code or metadata change (DECISIONS 2026-10-22).
- The Python side of the rules is `glow.salesforce.duplicate_account_groups` (the same name
  ignoring capitals and spacing, the same parent, the same record type; an accent is a different
  name): what the read-back and the monthly check compare with the rules' `DuplicateRecordSet`s,
  since Salesforce's Exact method ignores case and its handling of spacing is not documented with
  certainty (the diagnostic did not probe spacing, so the two lists are compared instead).
- Duplicates of girls are handled by `tools/sf_dupes.py` by its own key (RUNBOOK "Duplicate
  girls in Salesforce"); that path is unchanged.

## Rollout

All with the VPN off, through the `sf` CLI login `glow` (`.claude/skills/salesforce`). Every
write of this rollout (the deploy of step 5, the proof of step 6) waited for Ryan's go in the main
session, never a subagent (epic #68), and the Rollback waits for it the same way. `data/` is
never committed; the build is written there by script or `cp`.
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
   equals that type for the record saved, on create and on edit, Allow
   with Report only, no Alert and no Block (`actionOnInsert` and `actionOnUpdate` `Allow`,
   `operationsOnInsert` and `operationsOnUpdate` `Report`, no `alertText`, `isActive` true);
   Edit on the four fields for administrators, as entries in the partial Admin profile retrieved
   with the fields, and Read on them for the users who read the reports, in the
   `Attendance_Report_Viewer` permission set. RecordTypeId is not a matching item, since
   Salesforce does not allow Record Type as a matching-rule field (review, 2026-10-21). Each
   rule's condition is a `duplicateRuleFilter` whose `duplicateRuleFilterItems` test
   `Account.RecordTypeId` equals the record type's Name - "Club" and "Household Account" (not
   "Household") - for the record saved only; the candidates are whatever the Matching Rule finds.
   Each Duplicate Rule has its own `sortOrder` (Club 1, Household 2): the first check-only failed
   with "SortOrder must be in sequential order from 1" when both carried 1 (Result). Each rule's
   `securityOption` is `BypassSharingRules`. All three rules go in one deploy (a Duplicate Rule
   needs its Matching Rule in the same package or already active).
3. Check-only: from within `build/`, `sf project deploy start --dry-run -o glow -x package.xml`;
   its result (the components, 0 errors, 0 tests run) is shown to Ryan as it is.
4. Ryan's go: his answer in the main session, given after the check-only's result of step 3 is
   shown to him. A go given before that result covers nothing here; a headless run or a
   subagent cannot ask it.
5. Deploy: from within `build/`, `sf project deploy start -o glow -x package.xml`, the check-only
   command of step 3 with its dry-run flag taken off; record the deploy id and time (UTC).
6. The proof, at once, with the rules live, `sf apex run -o glow -f diag.apex` on Ryan's go: the
   script (below, "The diagnostic's script") is pasted in full first in the conversation. It is
   a no-DML diagnostic: `Datacloud.FindDuplicates.findDuplicates` runs the active rules over
   three unsaved copies of existing accounts, read by SOQL, inserts nothing and prints only
   `DIAG|` lines with each rule's name and its match count (never a record's name or id). Probe
   A is an upper-cased copy of a Club that has a parent: expected, the Club rule runs and reports
   1 match, the original. Probe B is a copy of a Household account: expected, the Household rule,
   1 match. Probe C is a Household account with a club's name and ParentId: the Household rule
   runs (the record saved is a Household account) and reports 1 match, the Club, since the
   record-type condition does not limit the candidates (cross-type, see Context). A probe with 0
   matches would mean a rule does not match what it should: the Rollback. The rolled-back insert
   proof of this plan's first version was dropped on 2026-10-22: Salesforce's duplicate matching
   does not see records inserted earlier in the same uncommitted transaction (Result).
7. Read-back: retrieve the same components into `data/sf_dupflags_2026-10-21/after/` and compare
   with `build/` (expected: Salesforce's normalisation only) and with `before/`. SOQL: `SELECT
   DeveloperName, IsActive, SobjectType FROM DuplicateRule` and the same on `MatchingRule` show
   all three rules active and the Contact rule "First & Last & Account" unchanged (its row and its
   metadata file equal to `before/`); the four fields are in `describe` of each object;
   `glow.salesforce.duplicate_account_groups` over `SELECT Id, Name, ParentId, RecordTypeId FROM
   Account` is compared by Account id with the rules' `DuplicateRecordSet`s and their
   `DuplicateRecordItems` (expected today: 0 groups and 0 sets, the two lists equal; a set
   without a group may be a cross-type pair, looked at by hand). Then the docs: this plan's
   Result, the RUNBOOK's Status line.
8. The next day (on or after 2026-10-23, UTC): SOQL on `Attendance_Batch__c` created since the
   deploy, none `Failed` with `DUPLICATES_DETECTED` among its `Status_Message__c` codes
   (`glow.salesforce.error_codes`, codes only); `python3 tools/auto_sync.py` as a dry run, its
   Salesforce plan unchanged (every region `in-sync`, 0 `SF:` ATTENTION items);
   `python3 tools/sf_new_clubs.py check --vpn-off …` exits 0. Record the counts in Result.

## The diagnostic's script (step 6)

`data/sf_dupflags_2026-10-21/proof/diag.apex`, quoted in full as it ran on 2026-10-22 (`data/` is
never committed). No DML: it reads one Club with a parent and one Household account by SOQL,
builds three unsaved probes from them and runs `Datacloud.FindDuplicates.findDuplicates` on each,
printing only `DIAG|` lines with the rule names and the match counts. The record type ids are the
org's (`glow.salesforce`).

```apex
// Ticket #84 diagnostic: no DML. Unsaved copies of existing accounts; rule names and match counts only.
Account club = [SELECT Name, ParentId FROM Account WHERE RecordType.DeveloperName = 'Club' AND ParentId != null LIMIT 1];
Account hh = [SELECT Name, ParentId FROM Account WHERE RecordType.DeveloperName = 'HH_Account' LIMIT 1];
Id clubType = '012RP000002uklNYAQ', hhType = '0126A000000cdYFQAY';
Map<String, Account> probes = new Map<String, Account>{
    'A_club_copy' => new Account(Name = club.Name.toUpperCase(), ParentId = club.ParentId, RecordTypeId = clubType),
    'B_household_copy' => new Account(Name = hh.Name, ParentId = hh.ParentId, RecordTypeId = hhType),
    'C_household_named_like_club' => new Account(Name = club.Name, ParentId = club.ParentId, RecordTypeId = hhType)};
for (String k : probes.keySet()) {
    List<Datacloud.FindDuplicatesResult> res = Datacloud.FindDuplicates.findDuplicates(new List<Account>{ probes.get(k) });
    System.debug('DIAG|' + k + '|rules_run|' + res[0].getDuplicateResults().size());
    for (Datacloud.DuplicateResult d : res[0].getDuplicateResults()) {
        Integer n = 0;
        for (Datacloud.MatchResult m : d.getMatchResults()) { n += m.getSize(); }
        System.debug('DIAG|' + k + '|' + d.getDuplicateRule() + '|matches|' + n);
    }
}
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
  touched), the no-DML diagnostic with the rules live right after the deploy, and the next day's
  batch check, which is the live check of the rules' action: a batch `Failed` with
  `DUPLICATES_DETECTED` means the Rollback.
- **Record Type as a Duplicate Rule condition.** A record whose type is neither Club nor
  Household meets no rule; the org uses only these two on Account (read 2026-10-21). A third type
  would need a third rule.
- **Cross-type pairs.** Salesforce may report a Household account and a Club of one name and
  parent as a pair, since a Duplicate Rule's record-type condition picks only the rule that runs
  for the record saved; `duplicate_account_groups` never groups them, so the monthly check sees
  a set without a group: looked at by hand, by id (Ryan, 2026-10-22).
- **Salesforce's Exact method and spacing.** The rules may report fewer twins than the Python
  side (a double space). Mitigation: the read-back and the monthly check compare the two lists,
  and a difference is looked at by hand, by id; the diagnostic did not probe spacing.
- **GLOW changes a definition.** Only the docs and the batch (#85) carry the obsolete criteria,
  so a change of them costs no deploy; the rules carry the duplicate criteria, so a change of
  those is a new deploy by this plan's steps.

## Proof

- `scripts/harness_tests.sh test/sf_data_quality_test.py` (classes `DuplicateRuleDocs` and
  `DuplicateAccountGroups`) and `make check` → `CHECK PASSED`.
- Live: the no-DML `Datacloud.FindDuplicates` diagnostic (step 6), the read-back (step 7) and
  the next day's batches (step 8).

## Result

Deployed 2026-10-22 on Ryan's go; step 8 pending. In order, counts and ids only:

- 2026-10-21, from 13:46 UTC: the fresh retrieve into `data/sf_dupflags_2026-10-21/before/`
  (step 1) and the build (step 2). The first check-only, `0AfRP000002hlP70AI`, failed:
  "SortOrder must be in sequential order from 1", because both Duplicate Rules carried
  `sortOrder` 1; the Household rule was set to `sortOrder` 2, so each Duplicate Rule has its own
  (Club 1, Household 2), and the check-only `0AfRP000002hlVZ0AY` succeeded, 9/9 components,
  0 errors. Its result was shown to Ryan; his go came on 2026-10-22.
- 2026-10-22 12:33 UTC: deploy `0AfRP000002htOH0AY`, 9/9 components, on Ryan's go. SOQL:
  `Name_Parent_Club_Report` and `Name_Parent_Household_Report` active, the Matching Rule
  `Name_Parent` Active, and the Contact rule "First & Last & Account" unchanged, its metadata
  equal to `before/`. Each Duplicate Rule's `securityOption` is `BypassSharingRules`.
- The read-back into `data/sf_dupflags_2026-10-21/after/` equals `build/` but for Salesforce's
  normalisation (`externalId` omitted, `trackFeedHistory` added, the permission set re-sorted);
  the 4 field permissions are present (Read in `Attendance_Report_Viewer`, Edit on the Admin
  profile).
- 12:35 UTC: the rolled-back insert proof of this plan's first version ran and could not work:
  all 7 inserts were saved and the rollback left 0 records, but 0 DuplicateRecordSets appeared,
  because Salesforce's duplicate matching does not see records inserted earlier in the same
  uncommitted transaction. Ryan, 2026-10-22: the no-DML `Datacloud.FindDuplicates` diagnostic
  replaces it as the proof (DECISIONS 2026-10-22).
- The diagnostic, the same day, over three unsaved copies of existing accounts (`DIAG|` lines,
  rule names and match counts only): probe A, an upper-cased copy of a Club that has a parent,
  ran the Club rule, 1 match; probe B, a copy of a Household account, ran the Household rule,
  1 match; probe C, a Household account with a club's name and ParentId, ran the Household rule,
  1 match, the Club. The log's lines, as printed (Salesforce writes `&#124;` for `|`):

  ```text
  DIAG&#124;A_club_copy&#124;rules_run&#124;1
  DIAG&#124;A_club_copy&#124;Name_Parent_Club_Report&#124;matches&#124;1
  DIAG&#124;B_household_copy&#124;rules_run&#124;1
  DIAG&#124;B_household_copy&#124;Name_Parent_Household_Report&#124;matches&#124;1
  DIAG&#124;C_household_named_like_club&#124;rules_run&#124;1
  DIAG&#124;C_household_named_like_club&#124;Name_Parent_Household_Report&#124;matches&#124;1
  ```

- Probe C is the cross-type pair: a Duplicate Rule's record-type condition picks only which rule
  runs for the record being saved and does not limit the candidates, so Salesforce may report a
  Household account and a Club of one name and parent as a pair. Ryan, 2026-10-22: accepted and
  documented, no code or metadata change; `duplicate_account_groups` keeps its own definition,
  and the monthly check reviews any such pair by hand.
- Counts on 2026-10-22: 0 same-name-and-parent groups (`duplicate_account_groups`), 0 cross-type
  pairs, 0 Account DuplicateRecordSets - the same after a Club account was created by hand that
  day (ticket #66).
- Step 8, the next day's batch check, is pending: due on or after 2026-10-23 (UTC), not yet run;
  its counts are written here when it has.
