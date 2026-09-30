---
title: Mentors pick their club from a list instead of typing its name
author: Ryan Eskuri (captured by Claude)
status: in-progress
created: 2026-09-01
---

# Intent: club picker on the attendance forms

## Problem

On the attendance forms the girls' names only appear once the club name is
typed exactly as it is on the form (the roster visibility rules compare the
Club Name textbox with each club's name). Mentors misspell, add or drop
words, or use a different casing convention, see no names, and either give
up or type again. Support requests come in as "the form is broken".

## Proposed outcome

As the mentor starts choosing their club, a list of club names appears and
they pick one; the roster shows at once. No typing of club names. The
change is tried on the template form first, verified by Ryan, then rolled
out to the four regional forms.

## Affected users and systems

- Mentors filling in the four regional Jotform attendance forms.
- `sync_attendance_form.py` (must generate and maintain the picker and the
  rules that key on it — the sync regenerates every condition on every run,
  so nothing added by hand survives).
- `tools/form_status.py` (rule audit must accept rules keyed on the picker).
- The Salesforce mapping, which reads the club name from question id 5 and
  must keep doing so.
- Translations: one new label and sublabel in twelve languages before the
  regional rollout.

## Constraints

- Question id 5 stays the field Salesforce reads (`Account_Name__c`); its
  value must remain the plain club name.
- Conditions must compare exactly (`equals`), never `contains`: several club
  names are substrings of others.
- No free text: a value that is not one of the form's clubs must be
  impossible.
- Works on weak mobile connections and inside the language switcher; no
  iframe widgets.
- Same-name clubs under two partners keep working (the Partner box).

## Open questions

- Jotform's plain dropdown only jumps to the first letter (Ryan's test);
  the Autocomplete widget allows free text and its conditions are
  `contains`-based. Decision: the native dropdown in its searchable mode
  (`multipleSelections=Yes` renders Jotform's own filter-as-you-type
  component; exact matching, no free text, translatable, no iframe) —
  Ryan verified it on the template 2026-09-01 and likes it.
- Where should the picker sit — same position as the textbox. Decided.
- Rollout: **template only for now**; the regional forms get it in a later
  mass update with other features (Ryan). Before that: apply the queued
  translations, and confirm a mentor cannot pick two clubs (Jotform ignores
  `maxSelection` on dropdowns; if two can be picked, add a guard rule).
  **Answered 2026-09-29:** two can be picked — 20 submissions since 09-01
  sent question 5 several club names run together. The guard rule is
  `--club-guard` ([plan](../plans/2026-09-29-club-guard.md); RUNBOOK "One
  club per submission"), proposed, not deployed.
