---
title: The names and the module the forms send are the exact roster and dropdown text
author: Claude (from the 2026-09-30 read-only investigation, design and two adversarial reviews)
status: accepted         # Ryan 2026-09-30: "Go on all 4 fixes after we get the september data into salesforce" — these are fixes 1 and 4; the back-fill was sent 2026-10-02 02:17-02:43 UTC
created: 2026-10-02
intent: docs/intent/2026-09-01-club-picker.md (the attendance form sends what Salesforce must match)
---

# Plan: girls' names without the dictionary's variants, and the module without page translation

## Context
Salesforce stores what question 18 (girls' names) and question 98 (`module_id`) say, and matches a
girl by her exact name.
- **Names (fix 1).** Each form carries a translation dictionary (`base`/`en`) cloned from the
  template, which holds 98 stale entries spelling a girl's name with a double space, a tab or an
  invisible character (U+200E). Jotform's calculation passes every ticked value through that
  dictionary, so 55 roster options (Africa 49, Asia 5, Latin America 1; 29 clubs) reach question 18
  altered — a second Contact in Salesforce (the duplicate rule now only reports it). Reproduced in a
  browser with no page translation; 58 of 58 observed names equal the emulated dictionary lookup.
- **Module (fix 4).** The module dropdowns (q14, q92, q93) have no `calcValues`, so question 98 copies
  the option's visible text, which a browser's "Translate page" rewrites: 30 of Latin America's 111
  September submissions sent a Spanish module (Salesforce keeps it as text, splitting the module in
  every report). The year and session dropdowns already carry `calcValues` and are exact.
The September back-fill sent the exact roster text and the canonical module, so after this change
the live flow and the back-filled data agree.

## Fix 1: remove the stale name entries (a tool, not the sync)
New `tools/fix_name_translations.py`, dry run by default, `--apply`, `--form`, `--restore <file>`
(which also needs `--apply`):
- Reads every form's roster options (all five forms count, so a girl who moves region or a namesake
  does not revive an entry) and the form's store (`GET /translations`).
- **What is removed:** the `base`/`en` entries whose lookup, emulated exactly as the runtime builds
  and uses the dictionary (`setDictionary`, `trimMultiSpaces`, `sanitizeKeys`, the `translate` fall-back
  through other languages), changes a roster option — and only those. Removal, not correction: a name
  with no entry is the normal state and comes out exact.
- `--apply`: saves the whole store first (mode 600 — it holds every girl's name), posts `base` and
  `en` without those keys (GET, merge, POST; no other language posted, CLAUDE.md rule 9), re-reads and
  compares every remaining entry, then reads the public page and counts the removed keys still
  embedded (0 expected; if a re-render is needed, the dry run says which extra write it makes).
- Refuses, writing nothing: a store without `base` or `en`; a key to remove that another language
  translates; more than 300 keys; a store smaller than a floor (a truncated read). A lost or
  non-JSON answer is re-read and reported as unchanged, applied or partial, never guessed.
- Prints club names and counts only.

## Fix 4: `calcValues` on the module dropdowns (generated)
The sync gives each module dropdown (q14, q92, q93, the ones `glow.sync.MODULES` names) `calcValues`
equal to its own options, with the leading empty slot of a single-select (the layout the year and
session dropdowns already use and that `form_status --rendered` proved for the picker). It keeps them
in step on every apply, like the picker's. Question 98's calculation is unchanged; it then reads the
`data-calcvalue`, which page translation does not touch.

## Audits
`tools/form_status.py`: NOT CLEAN when any roster option is altered by the form's own dictionary
(emulated lookup, `en` and every offered language), and when a module dropdown's `calcValues` are
missing or out of line with its options; `--rendered` checks the served page (embedded dictionary,
the dropdowns' `data-calcvalue`). The runner's verify picks both up after an apply. A future stale
entry (made in the builder) is flagged, not prevented.

## Rollout (Ryan's go given; runner paused for the window; template first)
1. Build on a branch, three adversarial reviews (runtime emulation vs a browser; live safety;
   tests/docs), fixes, read-only dry runs on all five forms.
2. Template: backup (`backup_forms.py`, the translation store), names tool dry run → `--apply` →
   audit 0 altered; sync dry run (only the module dropdowns' `calcValues`) → `--apply` → `nothing to
   do`; `form_status --rendered` CLEAN; a browser check on the live page (submits intercepted): a
   ticked affected girl's name is exact in question 18; with Chrome "Translate page" the module in
   question 98 stays the English option.
3. Merge and push, then U.S, Latin America, Asia, Africa the same way. Runner back on.
4. Tell the Salesforce session: Queens of Quest's held sessions and the variant-spelled duplicates
   can be handled.

## Rollback
Names: `fix_name_translations.py --form <id> --restore <saved store> --apply`. Module: set the
constant off and apply (the sync clears the `calcValues`), or restore the question from the backup.
Neither touches rosters, the rules, question 5 or the integration.
