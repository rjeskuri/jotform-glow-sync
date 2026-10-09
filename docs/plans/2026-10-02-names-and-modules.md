---
title: The names and the module the forms send are the exact roster and dropdown text
author: Claude (from the 2026-09-30 read-only investigation, design and two adversarial reviews)
status: done             # accepted by Ryan ("Go on all 4 fixes after we get the september data into salesforce"); live on all five forms 2026-10-06 (Result)
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

## Build notes

Built 2026-10-02 on `wf9/names-and-modules` (worktree), nothing written to any form, sheet or
Salesforce. `make check` passes.

**What was built.**
- `glow/translation_lookup.py`: the runtime's dictionary rebuilt and looked up exactly as
  `formTranslation.v2.js` does (`setDictionary`, `setSimplifiedDictionary`, `trimMultiSpaces`,
  `sanitizeKeys` with their snapshot semantics, `translateUncached` with the no-break-space retry
  and the fall-back through the other languages), JavaScript's whitespace and key order, both
  runtime builds (`BUILDS`), and the removal plan (`removal`: round after round, only the
  entries behind an alteration; refused when another language is involved or no entry explains
  it). It re-implements the reviewer's `emu.py` and reproduces it on the live stores: 55 / 49 /
  5 / 1 / 0 options altered (template, Africa, Asia, Latin America, U.S), identical counts.
- `tools/fix_name_translations.py`, as planned: dry run, `--form`, `--apply`, `--restore`
  (also needs `--apply`), the refusals, the store saved mode 600 before the POST, `base`+`en`
  only, re-read and compare, an audit of the re-read store, the public page read (three reads
  20 s apart) and re-rendered once with the unchanged `pagetitle` if it lags, a lost or non-JSON
  answer re-read and classed `UNCHANGED` / `APPLIED` / `PARTIAL`. Jotform's answers are never
  echoed.
- The module values: `glow/sync.py` `MODULE_CALC_VALUES`, `aligned_calc_values`,
  `module_calc_values`; the sync writes `UPDATE module dropdown (q14, year 1: calcValues = its 5
  options)` (or `… calcValues cleared)` with the constant off), and its `--summary-json` lists
  them (`module_values`).
- The runner parses the line (`MODULE_RX`), counts it as a change, names it in SyncLog's detail
  and **never applies it unattended** (`check_bands`), roster changes of that region included.
- `tools/form_status.py`: `audit_module_values` and `audit_names` in `form_report` (not in
  `audit_rules`, whose fixtures stay as they were), one GET more per form; `--rendered` reads
  the module `<select>`s and the embedded store against the roster boxes served. A store that
  cannot be read is `not checked`, a note in the runner's verify step.
- `tools/add_translations.save_store` writes every saved store mode 600.

**Decided while building (each in the RUNBOOK section and DECISIONS).**
1. *Only those*: 55 keys per form, not the 98 that look stale. Entries spelled with U+200E in
   both `base` and `en` keep the mark in their key and alter nothing, so they stay. Every form's
   store loses the same 55 keys (the stores were cloned), the U.S store included: all five
   forms' options count.
2. *Languages audited*: every language the store holds a dictionary for (a superset of the
   offered ones that can alter anything: a language without one alters nothing). Today only
   `en` alters, on every form; no other language's entry is involved, so no refusal.
3. *The fall-back order* is the runtime's own languages map (`RUNTIME_LANGUAGE_ORDER`, read
   from build `62a8b57dd95`), not the page's `allTranslations.languages` (a different map the
   runtime does not walk). It only matters when two languages' entries match one name.
4. *`--restore` puts back*, in the saved order, every `base`/`en` entry of the saved store that
   the form no longer has, and keeps entries changed or added since (a wholesale restore would
   drop a later `add_translations.py` addition). The current store is saved first.
5. *`--apply` takes exactly one `--form`*: the rollout is one form at a time, template first.
6. *Module lines are never applied by the runner*, like a `REQUIRED roster` line: the first
   rollout is by hand, template first, and afterwards a difference means a builder edit of a
   curriculum dropdown, which a human reads first. Until the rollout ends every region reads
   `attention` (the safety net if `AUTO_SYNC_APPLY` were left on).
7. *Builds*: the five forms were served `formTranslation.v2.js` builds `62a8b57dd95` (regional)
   and `fc726a121d4` (template) on 2026-10-02, byte-identical; against the runtime
   investigation's `9e75d6f1d83` only `setDictionary` differs (it now skips an entry missing in
   `en` or `base` instead of filing it under "undefined"). The audits run both; BACKLOG 64 is
   the watch for the next build.

**Read-only proof, 2026-10-02** (GETs through `glow.jotform.Client`, the public pages by curl;
no POST, PUT or DELETE):
- Names tool dry run, all five forms: 55 keys to remove on each (base 55, en 55); options
  altered today → after the removal (emulated, every language held, both builds): template 55
  → 0 (29 clubs), Africa 49 → 0 (23 clubs), Asia 5 → 0 (5 clubs), Latin America 1 → 0 (1
  club), U.S 0 → 0. No refusal. Stores: `base` 4,416 (U.S 6,079), `en` 4,424 (U.S 4,468).
- The module lines: 3 per form on all five (q14: 5 options, q92: 7, q93: 8), read with the
  sync's own comparison in a scratch script; the module dropdowns are single-selects without
  `calcValues`, the year dropdown carries `|1|2|3` (the same layout).
- `form_status.py --rendered`: NOT CLEAN on all five on the new checks only: template, Africa,
  Asia, Latin America 8 problems each (3 module + 1 names through the API, the same 4 on the
  served page, whose embedded store gives the same counts); U.S 6 (the modules). Question 18,
  the picker, the guard and the required rosters read clean as before.
- **Not run: the sync's own dry run on the five forms.** The fresh Roster export it needs was
  refused by this session's permission check (it needs the sheet's service account), so the
  roster changes that arrived since are unknown here. Run it before the rollout: it must plan
  the three module lines plus only those roster changes. (Run on 2026-10-06, below.)

**Refresh, 2026-10-06.** `main` merged in (the back-fill result, the attendance processor fix,
the Salesforce attendance dashboard, the work log). Main had taken BACKLOG 58-61 for the
dashboard, so this branch's three rows are now **62** (the names audit runs only after an
apply), **63** (other regions' girls' names on each public page) and **64** (the runtime watch);
both 2026-10-02 DECISIONS rows kept. `make check` passes (with the 2026-08-24 enrollment CSV:
328 clubs, 6,210 girls). A fresh read-only proof on the live forms (GETs through
`glow.jotform.Client`, the public pages and Jotform's scripts by curl, the Roster tab exported
by the service account; no POST, PUT or DELETE; every export and store copy deleted after):
- Names tool dry run, all five forms: unchanged since 2026-10-02. 55 keys to remove on each
  (base 55, en 55); altered today → after (emulated, both builds): template 55 → 0 (29 clubs),
  Africa 49 → 0 (23 clubs), Asia 5 → 0 (5 clubs), Latin America 1 → 0 (1 club), U.S 0 → 0. No
  refusal. Roster options: template 6,924, Africa 4,266 (4,264 on 10-02), Asia 1,636, Latin
  America 869, U.S 155. Stores as on 10-02 (`base` 4,416, U.S 6,079; `en` 4,424, U.S 4,468).
- Sync dry run with a fresh Roster export (7,186 rows, 6,926 active), each form: Africa, Asia,
  Latin America and U.S plan **exactly the three module lines** (q14: 5 options, q92: 7, q93:
  8), no roster change (the runner had kept them current), conditions unchanged. The template
  plans the same three plus **its own roster backlog: 21 roster updates** (19 Africa clubs, 2
  Asia; 6,924 → 6,926 girls; each equal in count to the club's roster on its regional form, the
  runner never syncs the template) and so a rewrite of its conditions (395 kept, 0 new, 0
  dropped). Read it before the template's apply (RUNBOOK rollout step 1).
- `tools/auto_sync.py` dry run on the same export: every region `attention`, "would write the
  calcValues of 3 module dropdown(s) (q14, q92, q93) - never unattended", nothing else.
- `form_status.py --rendered`, all five: NOT CLEAN on the new checks only, as on 10-02 (template,
  Africa, Asia, Latin America 8 problems each; U.S 6). Question 18 rule 1 with the picker an
  operand, every roster required, the picker's `data-calcvalue`s, the guard, 0 conditions in
  error, `salesforce yes` and the region comparison (0 missing, 0 differ) clean on all five.
- **New runtime builds** (BACKLOG 64's watch): Asia is now served `7a7e75787df`, Africa
  `9083adfcdff` (the template `fc726a121d4`, U.S and Latin America `62a8b57dd95` as before).
  Their `formTranslation.v2.js` is byte-identical to the 2026-10-02 builds' (one SHA-256 for
  all four), so `glow/translation_lookup.py` stands; their `jotform.forms.js` differs from
  `62a8b57dd95`'s only in the payment total's screen-reader text (no rule, calculation or
  `data-calcvalue` code).

**Review fixes, 2026-10-06** (the adversarial review of the build; each fix with a test that fails
without it):
- An option the lookup empties (a value `simplifyfWord` reduces to nothing) now counts as
  altered: the checkbox reader pushes `translate(value)` as it is, even `""`, and falls back to
  the value only when `FormTranslation` is not defined (`is_altered`; the module doc, the
  jotform-api skill and the RUNBOOK said otherwise). No live roster option is such a value.
- `fix_name_translations.py`: a failed read or write while re-rendering the page after the store
  POST (or the restore's) said "nothing written; run again", though the store was written and a
  second run cannot re-render. It now ends "The store is fixed but the public page could not be
  shown to serve it" (or "Restored, but ..."), and the RUNBOOK says what to do.
- Tests for what no test pinned (each mutation now fails the suite): the module audit's wiring
  into `form_report` and the runner's verify step, `rendered_options`' unescape and roster filter
  (3); the names tool's re-read and rollback branches - another language changed by the POST, a
  re-read that is no store, the audit of the re-read store, an entry changed since kept by the
  restore, nothing to restore (7); the emulation's steps - the order of the two renames, the
  fall-back skipping the language shown, another language's trimmed key and element id, U+202F,
  a match traced to its entry before the renames (8).

`main` merged again (the dashboard's fix1). The read-only proof re-run after the fixes (GETs
through `glow.jotform.Client`, the public pages and Jotform's scripts by curl, a fresh Roster
export by the service account; no POST, PUT or DELETE; every export deleted after):
- Names tool dry run, all five forms: as before. 55 keys to remove on each (base 55, en 55);
  altered today → after: template 55 → 0 (29 clubs), Africa 49 → 0 (23), Asia 5 → 0 (5), Latin
  America 1 → 0 (1), U.S 0 → 0; no refusal. Roster options: template 6,924, Africa 4,269, Asia
  1,636, Latin America 869, U.S 155.
- Sync dry run with the fresh export (7,191 rows, 6,929 active): Africa, Asia, Latin America and
  U.S plan exactly the three module lines, conditions unchanged. The template plans the same
  three plus its own roster backlog, now 22 roster updates (6,924 → 6,929 girls; the runner never
  syncs the template), and so a rewrite of its conditions (395 kept, 0 new, 0 dropped).
  `tools/auto_sync.py` on the same export: every region `attention` for the three module lines
  only.
- `form_status.py --rendered`, all five: NOT CLEAN on the new checks only (template, Africa,
  Asia, Latin America 8 problems each; U.S 6); 0 conditions in error, `salesforce yes`, question
  18, the picker, the guard, the required rosters and the region comparison clean. Africa is now
  served build `2bdb1ec3fa8`: its `formTranslation.v2.js` is byte-identical to the others'
  (BACKLOG 64).

**Left for the rollout (plan step 1 onwards):** the three adversarial reviews and the browser
checks on the template; repeat the dry runs on the day (a fresh export).

## Result (2026-10-06, with Ryan's go)
`AUTO_SYNC_APPLY=0` at 10:47 UTC. `main` fast-forwarded to the branch (`3ea1cab`) and the rollout run
from it; pushed after the template was proven (`00ee471` on origin, check green).

| Form | Names repair (store saved before) | Module values | After |
|---|---|---|---|
| template 262352490535154 | 10:47–10:49 UTC, 55 keys; `262352490535154-2026-10-06T194737-before.json` | 10:49 (with its 22-roster backlog) | CLEAN: 0 of 6,929 options altered (12 languages, API and served page); q14/q92/q93 aligned (API and served page) |
| U.S 262382706852058 | 11:16, 55 keys; `…-2026-10-06T201634-before.json` | 11:17 | CLEAN |
| Latin America 262383455778067 | 11:17, 55 keys | 11:17 | CLEAN, 0 of 869 altered |
| Asia 262383129464057 | 11:19, 55 keys | 11:20 | CLEAN, 0 of 1,636 altered (14 languages) |
| Africa 262382821971058 | 11:21, 55 keys | 11:22 | CLEAN, 0 of 4,269 altered |

- On U.S Jotform's answer to the store POST was lost; the tool's immediate re-read saw `PARTIAL` (en
  entries still being written). A compare with the saved store minutes later: `base` and `en` each
  exactly 55 keys fewer, nothing else gone or changed, the other 11 languages identical — the write
  had landed whole. The rollout then went one form at a time, the module step only after an
  `APPLIED` re-read.
- **Browser, live template** (build `bc6c80d556a`, every submit intercepted): every roster option
  through the runtime's own `FormTranslation.translate` unchanged in en and es (6,929); 149 girls of
  seven previously affected clubs ticked — question 18 byte-identical to the ticks in en and es and
  in the intercepted body; under a simulated Chrome page translation (text rewritten in `<font>`, 442
  options) question 98 equals the English option for all 20 modules (a control run without
  `data-calcvalue` sends the translated text); the guard and the required rosters unchanged.
- `auto_sync.py` dry run in-sync on every region; `AUTO_SYNC_APPLY=1` 11:23 UTC; GitHub run
  37456046598 in-sync.
- Follow-ups: release Queens of Quest's two held back-fill sessions in Salesforce; Spanish module
  values already stored are corrected in another session.

## From the RUNBOOK (moved 2026-10-09)

What `docs/RUNBOOK.md` carried for this plan until its 2026-10-09 restructure (the procedure as run, or its history), word for word (links re-pointed to this folder); the RUNBOOK keeps a stub that links here.

### "The names dictionary and the module values": the rollout as run

Read on 2026-10-02 (dry runs from the branch, nothing written):

| Form | Names: altered today → after | Keys to remove (base, en) | Sync: module lines | `form_status --rendered` |
|---|---|---|---|---|
| template | 55 → 0 (29 clubs) | 55 (55, 55) | 3 | NOT CLEAN: 8 problems (3 + 1 API, 3 + 1 page) |
| U.S | 0 → 0 | 55 (55, 55) | 3 | NOT CLEAN: 6 (the modules only) |
| Latin America | 1 → 0 (1 club) | 55 (55, 55) | 3 | NOT CLEAN: 8 |
| Asia | 5 → 0 (5 clubs) | 55 (55, 55) | 3 | NOT CLEAN: 8 |
| Africa | 49 → 0 (23 clubs) | 55 (55, 55) | 3 | NOT CLEAN: 8 |

Re-read 2026-10-06 with a fresh Roster export: the same counts on every form;
the sync planned only the three module lines on the four regional forms, and
on the template those plus its own roster backlog (21 rosters, which the
runner never syncs there) and with it a conditions rewrite. The plan's Build
notes have the detail.

**Rollout**, each write Ryan's go, template first. Wait for one runner run
with all four regions `in-sync`, then set `AUTO_SYNC_APPLY=0` for the whole
window and confirm it (no run in progress). Close every builder tab on these
forms. Nobody applies the sync to a form from a checkout without this code
while the window is open.

1. The template, from the branch (no `--region`: its Roster export is the
   whole tab; its own roster backlog, if any, rides along: read it first):

```bash
python3 backup_forms.py --form 262352490535154                                           # the questions as they are (calcValues "" today)
python3 tools/fix_name_translations.py --form 262352490535154                            # dry run: 55 keys, after the removal 0
python3 tools/fix_name_translations.py --form 262352490535154 --apply                    # store saved (note the file), POST, re-read: APPLIED, page: 0
python3 tools/fix_name_translations.py --form 262352490535154                            # "nothing to remove"
python3 sync_attendance_form.py data/roster_<date>.csv --roster --form 262352490535154            # dry run: the three module lines (+ its roster backlog)
python3 sync_attendance_form.py data/roster_<date>.csv --roster --form 262352490535154 --apply    # three question writes
python3 sync_attendance_form.py data/roster_<date>.csv --roster --form 262352490535154            # "nothing to do"
python3 tools/form_status.py --form 262352490535154 --roster data/roster_<date>.csv --rendered   # CLEAN: names 0 altered, module values aligned, rendered too
```

   Then in a real browser on the template's public page, without submitting
   (every submit intercepted, as for the browser steps above): pick a club the
   tool listed, tick every girl, and run the console check of "The names list
   sent to Salesforce": `equal: true` (it was `false` before the fix). Pick a
   year and a module, then Chrome's "Translate page" to Spanish: the console
   line `document.getElementById('input_98').value` still prints the English
   module. Open the builder's Translations page and close it without saving:
   the names tool's dry run still says `nothing to remove`.
2. **Merge and push**, `AUTO_SYNC_APPLY` still `0`. One runner run by hand
   (Actions, "Run workflow", apply unticked): every region reads `attention`
   with "would write the calcValues of 3 module dropdown(s)". A region without
   it means the runner runs older code: stop.
3. U.S, Latin America, Asia, Africa, smallest first, each with its `--region`
   and the same commands: backup, names tool dry run, `--apply`, dry run again;
   sync dry run (the three module lines and the roster changes since), `--apply`,
   `nothing to do`; `form_status --rendered` CLEAN; the console check on one
   affected club (Africa, Asia, Latin America) and the "Translate page" check.
4. With all five CLEAN under `--rendered`: one `auto_sync.py` dry run, every
   region `in-sync`, then `AUTO_SYNC_APPLY=1`.
5. Tell the Salesforce session: the forms send the exact names and the
   canonical module; the held sessions and the stale-spelling duplicates can
   be handled.

Stopped half-way, the runner stays at `0`: every region not rolled out reads
`attention` (the module lines), and a hand apply of its sync also rolls its
modules out; its names dictionary needs the tool run separately. A mentor with
the form already open keeps the old page until she reloads.
