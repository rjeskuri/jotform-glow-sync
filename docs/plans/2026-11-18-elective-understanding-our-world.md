---
title: Year 2 elective "Understanding our World" on the attendance forms
author: Claude (ticket #224, on Ryan's go of 2026-11-18)
status: done      # ticket #224; the option and the rules live on the template and the three live forms 2026-11-18 UTC
done: 2026-11-18
created: 2026-11-18
intent: Staff via Ryan, 2026-11-18 - "Please can you update the elective options for Year 2 in Jotform to include “Understanding our World”?"
---

# Plan: Year 2 elective "Understanding our World"

Ticket #224. Ryan, 2026-11-18: "let's default to 8 and we shouldn't need translations right? Go
on building that". Procedures: RUNBOOK "The names dictionary and the module values".

## Context

- Year 2's module dropdown is question 92 (`glow/sync.py MODULES["2"]`). Before: 9 options, the 3
  curriculum modules (Relationships 201, Power of Girls 201, Community 201), 4 electives ("Elective - Storytelling", "- Health and Wellness", "- Healthy
  GLOW", "- Girl Boss Basics") and the two special events, the same on all five forms. Its
  `calcValues` are an empty first value (the "please select" slot) then the options.
- **Sessions:** 8, the default for a module without a `SESSION_OVERRIDES` entry: no code change.
- **Translations:** none. No elective has a translation in any of the 11 languages of the template's
  store (only its `base`/`en` source), so every language shows the English option, as for the
  other electives.
- **Year 3 already offers it.** Question 93 (Year 3) carries "Elective - Understanding our World" in
  the same spelling on all five forms, with its own session rule; that is also why `base`/`en`
  already hold the string. Year 2 now offers the same text.
- **Salesforce:** `Module__c` is a text field on `Attendance_Batch__c` and `Attendance__c`: the
  option's text arrives as it is, no picklist to change. The two years send the same
  `Module__c` text and differ in `Module_Year__c`, so a report grouped by module alone (the
  dashboard's "Club sessions last month, by module") counts Year 2 and Year 3 sessions of this
  elective together; none of the dashboard's reports filters on module values.

## Rollout

1. One write per form: q92's `options` and `calcValues` together, the new option after the last
   elective and before the special events, on the template and the Africa, Asia and Latin America
   forms (U.S is disabled and left as it is); read back.
2. The sync (`sync_attendance_form.py --roster --partners … --region … --apply`) on the three live
   forms: the rules that show the 8-session dropdown for the new option.
3. `form_status.py`: module values aligned.

## Rollback

Remove the option from **q92's** `options` and `calcValues` on each form (the 9 before are listed
above; never q93's option of the same text), then the sync on each form: it drops the generated q92
rule once the option is gone. Not `restore_conditions.py` with the 2026-11-18 backups: the runner
rewrites the rules after every roster change, so an old backup would drop roster rules added
since.

## Result

2026-11-18, on Ryan's go in the session.

- Step 1: the four forms 9 → 10 options, "Elective - Understanding our World" 8th; read back equal
  (options and `calcValues`). The form backups meant to run before it failed (a wrong path to
  `backup_forms.py`) and the write ran anyway; the backups were taken after it, before step 2.
- Step 2: REPLACE conditions on Africa (234 rules), Asia (132), Latin America (75); each gained one
  q92 rule showing the session dropdown (q15) for the new option (the other rule naming the text is
  Year 3's q93 rule, already there).
- Step 3: `form_status`: q92 aligned (10 options) on the three live forms; Asia and Latin America
  CLEAN. Africa reads not clean only for its 38 retired Jotform-only rosters, which form_status
  flags when run without the Partners export (the runner passes it); `auto_sync.py --region`
  afterwards: Africa, Asia and Latin America `in-sync`, U.S `skipped - form DISABLED`.
- The template (Ryan's go to close the ticket out): backed up, then its sync applied with the
  Partners export and `--q5-change-ok`: its usual hand catch-up (11 new rosters, 40 roster updates,
  the Club picker, #216's three Otra Cosa question-5 renames) and the rules, 378, among them the
  q92 rule for the new option. A second dry run: nothing to do.
