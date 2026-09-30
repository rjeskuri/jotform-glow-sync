---
title: Jotform to Salesforce reconnected - the integration restored on the forms
author: Claude (with Ryan)
status: in-progress (Ryan's go 2026-09-30: restore through the API, the template first)
created: 2026-09-30
intent: none - Ryan's request of 2026-09-30 ("get the Jotform data flowing into Salesforce")
---

# Plan: Jotform to Salesforce reconnected

## Context
No attendance has reached Salesforce since 2026-03-28: the connection's Salesforce login was a
staff user, deactivated on 2026-09-17. On 2026-09-30 every active club got its Club account
([plan](2026-09-30-salesforce-clubs.md)), and Ryan reconnected Jotform with his own Salesforce
user for now (no spare licence he can assign; a dedicated integration user is a follow-up).

Jotform would not let him add his account beside the old one, so he removed the old connection.
That took the Salesforce integration off **all ten forms** (`integrations` is empty on each).
Nothing was flowing, so nothing was lost, and the five old forms are now disconnected, which was
wanted. The mapping itself is in the pre-apply backups of that day, identical on every form: one
action, create a record of `Attendance_Batch__c`, eight fields and the photo.

| Salesforce field | question |
|---|---|
| `Account_Name__c` | 5 (Club Name, hidden, filled from the Club picker) |
| `Attendance_Date__c` | 17 |
| `Contact_IDs__c` | 18 |
| `Module__c` / `Module_Week__c` / `Module_Year__c` | 98 / 100 / 102 |
| `Creator__c` | 105 |
| `enable_fuzzy_matching__c` | 109 |
| file upload | 19 (Group Photo) |

Ryan rebuilt the action on the template in the form builder. Read back, it equals the backup except
that `Account_Name__c` reads the Club picker (question 444) instead of question 5: both are
labelled "Club Name". Question 5 is the one every form shares and the one Salesforce must read
(CLAUDE.md, rule 5); the picker's id differs per form.

## Files that change
- `tools/restore_integration.py` - new, gated like every writer (dry run by default, `--apply`):
  it copies the template's live Salesforce integration to one form with `Account_Name__c` read
  from question 5, refuses anything but the known mapping, and re-reads after the write.
- `test/restore_integration_test.py`, one import line in `test/python_test.py`.
- `.claude/skills/live-systems/SKILL.md` (the writers' list), `docs/RUNBOOK.md`, this plan.

## Order of work
1. **Template**: `backup_forms.py --form <template>`, then
   `tools/restore_integration.py --form <template>` (dry run), then `--apply`. It rewrites the
   template's own integration with question 5 as the source of `Account_Name__c`, and proves
   whether an integration written through the API is stored as the builder stores it.
2. **Controlled test on the template** (Ryan submits in a browser; an API-made submission
   triggers no integration): a batch with status Success, its attendance rows, the photo on the
   batch, the token's use count going up. Then the test records are removed, with Ryan's go.
3. **The four regional forms**, one at a time, U.S first (no submissions yet): backup, dry run,
   `--apply`, re-read. From that moment new submissions flow by themselves.
4. **Watch** the first real submission of each form; a Club account without a parent means a
   form sent a name no account carries.
5. The five old forms stay disconnected; disabling them is a separate step with Ryan's go.

## Risks
- **A property written through the API may not be what makes the integration run.** Jotform may
  keep more than the form property. Step 2 is the proof; until it passes no regional form is
  written. If it fails, Ryan sets the action in the builder per form and the tool only verifies.
- **The write replaces the `integrations` property.** The tool merges into what is there and
  refuses a form that carries another integration it does not know.
- **Live flow starts with step 3.** A first submission from a large club creates one Contact per
  girl in one transaction (proven up to 22, the largest club has 62); a page opened before the
  same-name switch can still send a plain shared name. Both show in Salesforce (no batch, or a
  partner-less Club account) and neither loses the Jotform submission.
- **Rollback**: the backup taken in step 1 or 3 holds the form's `integrations` as it was; putting
  that value back, or removing the integration in the builder, undoes the write.

## Not in this plan
The September submissions (their own plan: they carry the girls' names), the test report, the
dedicated integration user, disabling the old forms.

## Proof
- `python3 tools/restore_integration.py --form <id>` → `would write` and the mapping table
- `python3 tools/restore_integration.py --form <id> --apply` → `verified: ... question 5`
- `python3 tools/form_status.py --form <id> --roster …` → `salesforce yes`
- `make check` → `CHECK PASSED`
