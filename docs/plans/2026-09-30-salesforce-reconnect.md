---
title: Jotform to Salesforce reconnected - the integration restored on the forms
author: Claude (with Ryan)
status: done             # Jotform reconnected 2026-09-30 12:05 UTC (2026-09-30-same-name-clubs.md, Verification after the switch); attendance flows since
done: 2026-09-30
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

## What the API cannot do (tried 2026-09-30, with Ryan's go, on the template)
The plan was to write the integration through the API. Jotform does not allow it: a JSON `PUT` of
the `integrations` property and a form-encoded `POST` of it both answer 200 and change nothing
(the template's integration was read before and after each try and was unchanged). So the
integration is set up **in the form builder, per form**, and the tool only checks the result.

## Files that change
- `tools/integration_status.py` - new, read-only: for each form, is the Salesforce integration the
  one known action, with `Account_Name__c` read from question 5 and all live forms on one
  connection? `test/integration_status_test.py`, one import line in `test/python_test.py`.
- `.claude/skills/jotform-api/SKILL.md` (the integration is read-only through the API; removing a
  connected account removes it from every form), `docs/RUNBOOK.md`, this plan.

## Order of work
1. **Template** (Ryan, in the builder): change the source of "Account Name" to the other
   "Club Name" entry - the hidden text field, not the dropdown. `integration_status.py --form
   <template>` says which one Jotform stored.
2. **Controlled test on the template** (Ryan submits in a browser; an API-made submission
   triggers no integration): a batch with status Success, its attendance rows, the photo on the
   batch, the token's use count going up. Then the test records are removed, with Ryan's go.
3. **The four regional forms** (Ryan, in the builder, U.S first - it has no submissions yet):
   Settings → Integrations → Salesforce → the existing connection → Create a New Record →
   `Attendance_Batch` → the eight fields of the table above → the Group Photo as upload. After
   each form: `integration_status.py --form <id>` → `ok`. From that moment the form's new
   submissions flow by themselves.
4. **All five**: `python3 tools/integration_status.py` → `integration: ok` (one connection, the
   old forms without), `form_status.py` → `salesforce yes`.
5. **Watch** the first real submission of each form; a Club account without a parent means a
   form sent a name no account carries.
6. The five old forms stay disconnected; disabling them is a separate step with Ryan's go.

## Risks
- **The two "Club Name" entries.** The builder's field list shows the Club picker and question 5
  under one label. The tool names which one a form uses; the wrong one is corrected in the
  builder before the form's first submission.
- **Live flow starts with step 3.** A first submission from a large club creates one Contact per
  girl in one transaction (proven up to 22, the largest club has 62); a page opened before the
  same-name switch can still send a plain shared name. Both show in Salesforce (no batch, or a
  partner-less Club account) and neither loses the Jotform submission.
- **The connection runs as Ryan's own user** for now: if that user is deactivated the flow stops
  silently, as it did on 2026-09-17. A dedicated integration user is the follow-up (the org
  shows one free full licence and four free integration licences).
- **Rollback**: removing the integration from a form in the builder stops its flow; nothing else
  on the form is touched.

## Not in this plan
The September submissions (their own plan: they carry the girls' names), the test report, the
dedicated integration user, disabling the old forms.

## Proof
- `python3 tools/integration_status.py` → `integration: ok`
- `python3 tools/form_status.py --form <id> --roster …` → `salesforce yes`
- `make check` → `CHECK PASSED`
