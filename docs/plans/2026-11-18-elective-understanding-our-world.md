---
title: Year 2 elective "Understanding our World" on the attendance forms
author: Claude (ticket #224, on Ryan's go of 2026-11-18)
status: done      # ticket #224; the option and the rules live 2026-11-18 UTC; the template's rules wait for its catch-up sync
done: 2026-11-18
created: 2026-11-18
intent: Staff via Ryan, 2026-11-18 - "Please can you update the elective options for Year 2 in Jotform to include “Understanding our World”?"
---

# Plan: Year 2 elective "Understanding our World"

Ticket #224. Ryan, 2026-11-18: "let's default to 8 and we shouldn't need translations right? Go
on building that". Procedures: RUNBOOK "The names dictionary and the module values".

## Context

- Year 2's module dropdown is question 92 (`glow/sync.py MODULES["2"]`). Before: 9 options, 3
  curriculum modules, 4 electives ("Elective - Storytelling", "- Health and Wellness", "- Healthy
  GLOW", "- Girl Boss Basics") and the two special events, the same on all five forms. Its
  `calcValues` are an empty first value (the "please select" slot) then the options.
- **Sessions:** 8, the default for a module without a `SESSION_OVERRIDES` entry: no code change.
- **Translations:** none. No elective has a translation in any of the 11 languages of the template's
  store (only its `base`/`en` source), so every language shows the English option, as for the
  other electives.
- **Salesforce:** `Module__c` is a text field on `Attendance_Batch__c` and `Attendance__c`: the
  option's text arrives as it is, no picklist to change.

## Rollout

1. One write per form: q92's `options` and `calcValues` together, the new option after the last
   elective and before the special events, on the template and the Africa, Asia and Latin America
   forms (U.S is disabled and left as it is); read back.
2. The sync (`sync_attendance_form.py --roster --partners … --region … --apply`) on the three live
   forms: the rules that show the 8-session dropdown for the new option.
3. `form_status.py`: module values aligned.

## Rollback

Remove the option from q92's `options` and `calcValues` on each form (the 9 before are listed
above), then the sync on the live forms; `restore_conditions.py` for the rules (backups taken
2026-11-18 after step 1, before step 2).

## Result

2026-11-18, on Ryan's go in the session.

- Step 1: the four forms 9 → 10 options, "Elective - Understanding our World" 8th; read back equal
  (options and `calcValues`). The form backups meant to run before it failed (a wrong path to
  `backup_forms.py`) and the write ran anyway; the backups were taken after it, before step 2.
- Step 2: REPLACE conditions on Africa (234 rules), Asia (132), Latin America (75); each has 2 rules
  naming the new option, showing the session dropdown (q15).
- Step 3: `form_status`: q92 aligned (10 options) on the three live forms; Asia and Latin America
  CLEAN.
- Not done: the template's rules; its sync also carries an unrelated catch-up (new rosters), left
  for its own run.
