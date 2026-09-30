---
title: One club per attendance submission (the multi-club guard)
author: Claude (workflow track "club-guard", 2026-09-29)
status: proposed         # proposed → accepted (Ryan) → in-progress → done
created: 2026-09-29
intent: docs/intent/2026-09-01-club-picker.md (its open question: "confirm a mentor cannot pick two clubs … if two can be picked, add a guard rule")
---

# Plan: one club per submission

## Problem

The Club picker is Jotform's searchable dropdown (`multipleSelections=Yes`:
the only mode with a type-to-filter box, on phones too). Its other side: a
mentor can pick several clubs. Read-only, 2026-09-29 (GET + the public
runtime `jotform.forms.js`; counts only):

- **20 multi-club submissions since 09-01** (Africa 12: nine with 2 clubs,
  three with 3; Asia 8: seven with 2, one with 4). The picker's answer is a
  JSON list; question 5 (the Salesforce `Account_Name__c` field) received the
  names joined with **no separator** in all 20. Every picked club's roster
  showed, and the Contact_IDs sum collected ticks from all of them.
- On Salesforce's side (the other session's read-only investigation) the
  batch processor matches question 5 to `Account.Name` exactly (ignoring
  case) and **creates** a Club Account when nothing matches: a fused
  question 5 would become a junk Account. None exists yet — nothing has
  reached Salesforce since 2026-03-28 (the connection's user was deactivated
  09-17) — so the 20 fused submissions must be split or assigned before any
  back-fill.
- On a `<select multiple>` Jotform's rules evaluate only `equals`,
  `notEquals`, `isEmpty`, `isFilled`. `equals` means "this exact option is
  selected" and is **case-sensitive** on the option's value (the skill's
  "case-insensitive" holds for other fields). `contains` is silently
  skipped; there is no count operator, and a calculation cannot count a
  selection.
- **Live bug found on the way:** Africa's roster "SUPER GIRLS" (q429) can
  never appear. Its rule tests `equals "SUPER GIRLS"`, the picker offers
  "Super Girls". Same on the template. Neither roster has submissions yet.
- In 5 single-club submissions (Asia 4, Latin America 1) question 5 differs
  from the picked option by one character (an inserted space, a trailing
  "."): the stored pick holds the option's value, question 5 copies its
  visible text, which the browser's page translation altered.

## Design

Nothing changes on a form until a person runs `--club-guard --apply` on it
(the runner never passes the flag), except the spelling fix (A).

**A. The picker's own spelling (ungated).** When a form has the picker, each
roster rule and partner-reveal rule tests the club with the picker's own
spelling (`{o.lower(): o}` over the options the same run writes). Fixes
SUPER GIRLS: 1 rule changes on Africa and on the template; forms without a
picker are byte-identical.

**B. Picker `calcValues` = its own club names** (forms with the guard), kept
in the same `UPDATE club picker (N clubs: calcValues, options)` write as the
options. The q5 copy then reads `data-calcvalue`, which page translation does
not change, so question 5 is exactly one option for every single-club pick.
The layout is one constant, `PICKER_CALC_LEADING_EMPTY` (default: the leading
empty slot the five live single-select dropdowns carry — `|1|2|3`, rendered
as `data-calcvalue` 1..3 on the options after "Please Select"). Whether a
multi-select renders it the same way is **unverified**: the template's
rendered page (`form_status.py --rendered`: every option's `value` equals
its `data-calcvalue`) is a **hard stop** before any regional form.

**C. The warning element `clubGuard`:** a hidden `control_text`, found by
name like `clubPicker` / `partnerPicker`, holding one sentence in a styled
`<p>` (`glow.sync.guard_html()`, pinned byte for byte because a change
re-keys its translations). Wording (a constant, `GUARD_SENTENCE`, for Ryan to
approve): "You chose more than one club. Keep only your own club in Club
Name, and the Submit button comes back."

**D. Two generated rules** (new section D of `build_conditions`, appended
after the Contact_IDs sum, so every existing rule keeps its index):

- field rule, link All: terms `{picker isFilled}` + `q5 notEquals <option>`
  for every picker option; actions Show `clubGuard`, Hide Submit;
- require rule, link All, the same terms (fresh ids): Disable Submit
  (constant `GUARD_DISABLES_SUBMIT`; hiding alone lets desktop Enter in the
  Partner Coordinator Email box submit).

One club picked → q5 equals that option → the rules are false. Two picked →
q5 is the names run together → equals no option → warning shown, Submit
hidden and disabled; removing the extra club brings it back. Submit is found
by type (`glow.links.submit_button`: exactly one, q2 everywhere). Size: +2
rules of (options + 1) terms: template 337, Africa 217, Asia 97, Latin
America 40, U.S 13 (options + 1 as read today).

**E. Question 18 is left as it is (a separator was considered and
dropped, 2026-09-30).** Without a separator, two visible rosters fuse the
last girl of one with the first of the next (once, in a multi-club
submission). On a guarded form that cannot reach a submission: Submit is
hidden and disabled unless question 5 is exactly one option, a shared club
name is partner-gated (a single-select, so one roster), and
`ignoreHiddenFields` turns every other roster into "". The review read the
five live forms' rules, 2026-09-30: no picker option plus partner shows two
rosters. A separator in the equation, on the other hand, is written unconditionally
(the runtime's `calculate()` appends every literal): (rosters − 1) × 2
characters of ", , , …" on every guarded submission, ticks or none (Africa
about 440, the template about 680). That text would go to `Contact_IDs__c`
(its length unconfirmed), into the staff notification and the mentor's
autoresponder (both print q18), and would make q18 never empty once a club
is picked, which hides the 16 "girls ticked but empty Contact_IDs"
submissions and rules out an `isEmpty` rule on q18 (BACKLOG 35). The guard
rollout therefore leaves the q18 calculation byte-identical. If defence in
depth is ever wanted for the two theoretical gaps (two picked names that
join into a third, warned today; two same-partner clubs differing only in
case), the sync should refuse those, or each roster option carry a
calcValue with its own trailing comma — its own plan, after
`Contact_IDs__c`'s length is confirmed.

**F. `sync_attendance_form.py`.** `mk_hide`, `mk_disable`, `mk_require_rule`
next to `mk_show` / `mk_field_rule`; `build_conditions(…, picker_options=None,
guard=None, submit=None)` where `picker_options` is the exact sorted list
`main()` writes to the picker (clubs created in the same run included). New
flag `--club-guard`; refusals before any write: no Club picker; two elements
named `clubGuard`, or one that is not a text element; not exactly one Submit
button. A warning when two options joined equal a third (0 today: the guard
could not see that pair). The element is created as "CREATE club guard
(below the Club picker)", kept in shape as "UPDATE club guard (hidden,
text)"; a create answered without a qid warns and writes no guard rules this
run (as the partner list does). Write order: rosters → picker → guard element
→ conditions. `--summary-json` gains `club_guard`.

**G. `tools/form_status.py`.** Always, on a multi-select picker: every
`equals` term on it matches one option exactly (flags Africa q429 and the
template today — the next apply of either fixes it). Whenever the picker
carries `calcValues`: aligned with the options under the chosen layout. With
`clubGuard`: a picker exists; one element, a text element, hidden, the
pinned HTML, rendering directly below the picker; exactly one field rule
(Show guard + Hide Submit, link All, the full term list — missing and extra
options reported) and one require rule (Disable Submit, the same terms); no
other rule shows the guard. Report line `club guard:
q<id> (N clubs)` or `club guard: none (a mentor can pick several clubs)`
(informational: forms stay CLEAN before rollout). `--rendered`: GET the
public page (curl, like every tool here), compare each picker option's
`value` with its `data-calcvalue` in memory, and (with `calcValues`) flag a
page whose option count differs from the picker's, so a page it cannot
read never passes; counts only.

**H. `tools/auto_sync.py`.** `GUARD_RX` (CREATE|UPDATE club guard), read by
`parse_plan` and `plan_from_summary`, counted by `changes()`, named by
`plan_summary()` — like the partner list. `PICKER_RX` already accepts
`(N clubs: calcValues, options)`.

**I. Translations.** The sentence in the 13 offered languages (es, fr, th,
ur, te, vi, ne, km, sw, ar, or, hi, fa), reusing each language's "Club Name"
and Submit wording where the repo has it; written by us, not
native-reviewed. `glow.links.translated_elements()` generalises the element
list `add_translations.plan_additions` and `add_language.text_element_keys`
read, so the guard is keyed like the links: sentence, `text_<qid>`, stored
HTML.

### Deviations from the approved design (with the reason)

1. **The element is created at the picker's order + 1, not at the picker's
   order.** The live forms show that a create at a taken order *inserts*
   (the picker was posted at question 5's order 3; question 5 is now 4 on
   all five forms), so the picker's own order would put the warning above
   the picker. At order + 1 it renders directly below the picker when
   Jotform inserts, and directly after the hidden question 5 (so, visibly,
   below the picker) if it ever ties. `form_status` checks that nothing a
   mentor can see renders between the picker and the warning.
2. **`calcValues` are also kept in step whenever the picker already carries
   them**, not only with the guard. After a rollback that deletes the
   element but leaves the `calcValues`, a new club would otherwise shift
   them, and the q5 copy would send a neighbouring club's name to Salesforce
   without any error. `form_status` checks the alignment in the same case.
3. **Two elements named `clubGuard`, or one that is not a text element, are
   refused on every run** (the runner's included), not only with the flag:
   the sync cannot tell which one to show; refuse rather than guess, and the
   runner's ATTENTION names it.
4. **No q18 separator** (section E): dropped after review, 2026-09-30. The
   design's reason for it came from multi-club picks, which the guard now
   blocks; its cost fell on every guarded submission.

## Files that change
- `docs/plans/2026-09-29-club-guard.md` — this plan.
- `glow/sync.py` — `GUARD_NAME`, `GUARD_SENTENCE`, `GUARD_PROPS`,
  `guard_html()`, `club_guards()`, `GUARD_DISABLES_SUBMIT`,
  `PICKER_CALC_LEADING_EMPTY`, `picker_calc_values()`, `has_calc_values()`.
- `glow/links.py` — `translated_elements()`; the docstring's "no generated
  rule mentions any other element" narrowed to the links.
- `sync_attendance_form.py` — A, B, D, F.
- `tools/form_status.py` — G.
- `tools/auto_sync.py` — H.
- `tools/add_translations.py`, `tools/add_language.py`,
  `tools/translations_additions.json` — I.
- `test/python_test.py` — ConditionBuilder, ClubGuardFlow (fake form),
  FormStatusAudit, AutoSyncPlan, TranslationPlan additions (fictional data).
- `docs/RUNBOOK.md` ("One club per submission"; the Club picker section's
  open question), `docs/DECISIONS.md`, `docs/BACKLOG.md`,
  `docs/ARCHITECTURE.md`, `docs/intent/2026-09-01-club-picker.md`,
  `.claude/skills/jotform-api/SKILL.md` (multi-select operators and case;
  create at a taken order inserts; Hide/Disable/require rules; multi-select
  `calcValues` unverified).

## Order of work
1. Commit this plan.
2. `glow/sync.py` constants and helpers; `build_conditions` A, D with the
   ConditionBuilder tests (without the guard: identical rules, normalised;
   with it: the same rules plus the two guard rules at the end).
3. `main()`: the flag, refusals, calcValues, the element, the summary — the
   ClubGuardFlow tests on a fake form.
4. `form_status`, `auto_sync`, the translation tools, with their tests.
5. Docs. `make check` green after every step; a commit per step on
   `wf5/club-guard`.
6. Read-only proof against the live forms (below).

## Risks
- **The calcValues layout on a multi-select is unverified.** Misaligned
  values would copy a *neighbouring* club into question 5 — no warning (it
  is still one option), wrong Account in Salesforce. Mitigation: the
  template first, and `form_status.py --rendered` there is a hard stop
  (restore the template's picker with `calcValues` flipped or cleared)
  before any regional form.
- **Blocking a single-club mentor** whenever question 5 is not exactly one
  option: misaligned calcValues, two names that join into a third (warned),
  or a half-write that left a new club out of the guard's term list (the
  picker is written before the rules; the runner retries once, then its
  verify fails on "guard rule misses …" → ATTENTION). The browser check
  covers the page-translation case.
- **First Hide / Disable / require rules on these forms, and much larger
  rules.** Measured in the dry runs (the would-be conditions PUT, bytes):
  template 141,922 → 239,585 (+69%, with the 23 clubs it would create),
  Africa 98,066 → 157,115 (+60%), Asia → 76,215, Latin America 28,969 →
  40,362, U.S → 23,313 — the two guard rules repeat the full club list
  (Africa 217 terms each). A size limit on the PUT is not proven. The
  template, the largest, goes first; the builder's Conditions page must show
  no error marks. If the size bites, `GUARD_DISABLES_SUBMIT = False` halves
  the addition (and gives up the desktop Enter-key block).
- **The runner reads `main`**: merging changes no form except A on the next
  applied roster change (Africa's SUPER GIRLS rule; `form_status` flags the
  bug until then). The guard is per form, by hand, with `AUTO_SYNC_APPLY=0`
  for the window.
- **Merging with `wf5/rosters-above-submit`** (both fork from `0c095c0`):
  that branch removes `main()`'s local `order_of`, so the guard's create
  takes the picker's order from `glow.links.order_of`, imported as
  `links_order_of` as that branch does (drop the duplicate import when
  merging). Whoever merges second still adapts the ClubGuardFlow fixtures to
  the layout code: its fake questions need a `qid`, and the layout's own
  "expected one Submit button" refusal comes before the guard's.
- **The warning is English until translations are applied** (the next step
  of the per-form procedure).
- **Rollback per form**: `AUTO_SYNC_APPLY=0`; `backup_forms.py --form`;
  `restore_conditions.py --from properties-<stamp>.json` (the pre-guard
  backup); delete the `clubGuard` element (while it exists the runner
  regenerates the rules); optionally clear `calcValues` (if kept, the sync
  keeps them aligned — deviation 2); `form_status` CLEAN; `AUTO_SYNC_APPLY=1`.

## Proof
- `make check` → `CHECK PASSED` (tail below).
- Read-only against the live forms, 2026-09-30 (GETs and dry runs only; a
  fresh Roster export read with `sheets_client.py export`, kept in the
  session's scratch directory and deleted afterwards; counts only):
  - The sync's dry run, `main` vs this branch, **without the flag**: U.S,
    Latin America and Asia identical (`conditions unchanged`, nothing to
    do); Africa and the template change exactly one rule each (`1 new, 1
    dropped`: the SUPER GIRLS spelling); the template's 35 roster calls are
    the same on both (it is synced by hand and was behind).
  - **With `--club-guard`** (dry run): every form plans `UPDATE club picker
    (N clubs: calcValues)`, `CREATE club guard (below the Club picker)` and
    `REPLACE conditions` with two more rules — U.S 12 clubs, 41 → 43 rules;
    Latin America 39, 68 → 70; Asia 96, 125 → 127; Africa 216, 255 → 257;
    the template 359 (23 of them created in the same run), 376 → 378. These
    runs still had the q18 separator (section E, dropped afterwards), so
    they printed `40 kept, 3 new, 1 dropped` (Africa and the template `4
    new, 2 dropped` with the spelling fix). Without it the Contact_IDs sum
    is unchanged and each count is one lower: `41 kept, 2 new, 0 dropped`,
    the 2 new being the guard rules (`3 new, 1 dropped` on Africa and the
    template) — pinned in the ClubGuardFlow tests, not re-run live. No "two
    names join into a third" warning on any form.
    Measured in-process on the same dry runs (writes recorded, never sent):
    each guard rule has clubs + 1 terms (U.S 13, Latin America 40, Asia 97,
    Africa 217, template 360), the `calcValues` carry clubs + 1 slots, and
    the conditions PUT grows by 60-69% on the two largest forms (Risks;
    measured with the separator, which added under 700 bytes per form).
  - `form_status.py` (this branch, `--rendered`): the SUPER GIRLS rule
    flagged on Africa and the template only ("it has 'Super Girls'; a
    multi-select compares case"); `club guard: none` everywhere; errors 0,
    Salesforce yes on all five; the public page's picker found on all five
    with no `data-calcvalue` yet (template 336 options, Africa 216, Asia 96,
    Latin America 39, U.S 12). `main`'s `form_status` reports no rule
    problem on any form.
  - `auto_sync.py` dry run on this branch (the same export, `--roster`,
    `--out` in scratch; no `--synclog`): Africa, Asia and U.S `in-sync` —
    Africa's one-rule spelling difference is not a change to the runner, so
    merging does not write it. Latin America `would apply: 1 update`: the
    live form changed between the two runs (a roster write after the
    export, presumably the runner's); `main`'s dry run on the same export
    now plans the same update, and with `--club-guard` the plan is
    otherwise as above.
- The planned offline replay of the live rules without a roster was not
  needed: the dry runs above compare the generated rules with the live ones
  on every form.

`make check` (2026-09-30, with `CSV=` pointing at the 2026-08-24 enrollment
export for the real-data parity):

```
real data (…/enrollment_2026-08-24.csv): parsed 328 clubs, 6210 girls
ALL CHECKS PASSED
ALL CHECKS PASSED
ALL CHECKS PASSED
py: 32 files parse, 19 scripts answer --help
Ran 152 tests in 0.176s
OK
gs: 10 files parse
secrets: clean (128 files scanned)
docs-links: ok (46 relative links resolve, 0 absolute paths)
fixtures: up to date
CHECK PASSED
```

## Rollout (each step Ryan's go; not part of this branch)
`AUTO_SYNC_APPLY=0`. Template: backup; translation audit (before);
`--club-guard` dry run (+2 rules; +1 changed while A has not landed);
`--apply`; `form_status` CLEAN; `form_status --rendered` aligned = **hard
stop**; `add_translations.py --apply` and the audit. Browser: one club → no
warning, Submit shown; a second club → warning, Submit gone; remove it →
both back; desktop Enter with two clubs does not submit; the language switch
translates the warning; Chrome "Translate page" with one club → no warning;
the builder's Conditions page has no error marks; one test submission:
question 5 exactly the club, question 18 lists the ticked names. Then
U.S, Latin America, Asia, Africa (smallest first), `--club-guard` and
`--partner-picker` as separate commands. `AUTO_SYNC_APPLY=1`; `auto_sync.py`
dry run in-sync.
