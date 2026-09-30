---
title: Rosters above Submit and the club guard, merged together (wf5 integration)
author: Claude (workflow integrator, wf5/integration, 2026-09-30)
status: proposed         # Ryan accepts (with both plans below) before the merge into main; every live step needs his go
created: 2026-09-30
intent: none — integrates [plans/2026-09-29-rosters-above-submit.md](2026-09-29-rosters-above-submit.md) (BACKLOG 47) and [plans/2026-09-29-club-guard.md](2026-09-29-club-guard.md) (BACKLOG 48)
---

# Plan: the wf5 integration

Both branches fork from `0c095c0`; `wf5/integration` is today's `main`
(`41dfa07`, the time-zone work) plus `wf5/rosters-above-submit` and then
`wf5/club-guard`, each merged `--no-ff`. It merges into `main` as a fast
forward. Nothing here changes either plan's design; this page records how
they fit together and the one order of live steps for both.

## Files that change
Only where the two branches meet (everything else is each plan's own list):
- `sync_attendance_form.py` — both imports (`glow.layout` for the roster
  slot, `glow.links.order_of` + `submit_button` for the guard). Write order in
  one run: rosters (at the slot) → picker → the guard's warning (at the
  picker's order + 1) → conditions. Both refusals ("expected one Submit
  button") come before any write: the guard's whenever the guard is on, the
  layout's whenever there is a roster to create.
- `tools/form_status.py` — the report prints `layout:`, then `club guard:`
  and (with `--rendered`) `rendered picker:`; the layout problems and the
  guard's audit both join `rule_problems`.
- `glow/links.py` (docstring), `docs/ARCHITECTURE.md`, `docs/BACKLOG.md`
  (48 waits for 47's repair), `docs/DECISIONS.md` (both 2026-09-29 rows),
  `.claude/skills/jotform-api/SKILL.md` (one note on creating at a taken
  order; the order update unobserved; multi-select `calcValues` unverified).
- `test/python_test.py` — `ClubGuardFlow`'s fake form carries each
  question's `qid` (as Jotform's GET does) and its Submit below the rosters
  (the repaired layout); with two Submit buttons and no guard the sync still
  runs when there is nothing to create, and the layout refuses before any
  write when there is; a new test pins both creates in one run.
- `docs/RUNBOOK.md` — the club guard goes only on a form the repair has
  finished; the repair's `--undo` is for before the guard too (the warning's
  create shifts the rosters' orders, and `--undo` refuses once a roster's
  order changed).

## Order of work
1. Branch from `main`; merge `wf5/rosters-above-submit` (conflict:
   DECISIONS only); `make check`; commit.
2. Merge `wf5/club-guard` (conflicts: the files above); adapt the tests;
   `make check`; commit.
3. This plan; `make check`; commit.
4. Read-only proof on the live forms (below).

## Live steps (in this order; each needs Ryan's go; none is run here)
1. Accept both plans and this one, and the guard's sentence
   (`glow/sync.py GUARD_SENTENCE`).
2. Repository variable `AUTO_SYNC_APPLY=0` (the layout check makes every
   unrepaired form NOT CLEAN).
3. Merge `wf5/integration` into `main` (fast forward) and push.
4. Roster repair, the template first: `python3 tools/fix_roster_order.py
   --form 262352490535154` (dry run: 9 moves, 368-376), `--apply`, open its
   page; record in the jotform-api skill how Jotform stored the orders.
5. The four regionals: `python3 tools/fix_roster_order.py` (dry run; the
   template says nothing to do), `--apply`.
6. `python3 tools/form_status.py --roster <fresh export>`: `layout: every
   roster above …` on all five; the only problem left is the SUPER GIRLS
   rule on Africa and the template. Browser check on Africa (a roster from
   q333 up renders above Submit).
7. Either `AUTO_SYNC_APPLY=1` here and a separate window for the guard
   (recommended), or continue paused.
8. Club guard (RUNBOOK "One club per submission"), the template first:
   backup, translation audit, `--club-guard` dry run, `--apply`, the dry run
   again (nothing to do), `form_status` CLEAN, `form_status --rendered`
   (**hard stop**), `add_translations.py` dry run / `--apply` / audit,
   browser checks, one test submission.
9. U.S, Latin America, Asia, Africa, the same way (Africa's apply lands the
   SUPER GIRLS fix).
10. `AUTO_SYNC_APPLY=1`; `python3 tools/auto_sync.py` (dry run) in-sync.
11. Then 46 (Club Roster Form link) and 45 (partner list), each after the
    repair; and, before any Salesforce back-fill, the 20 fused question-5
    submissions (BACKLOG 48).

## Risks
- **Every form NOT CLEAN from the merge until its repair** — the runner is
  paused first (step 2) and the repair runs in the same sitting.
- **The warning's create moves rosters.** Created at the picker's order + 1
  (a taken order: Jotform inserts and shifts the block below, up to the first
  gap), so after the guard `fix_roster_order.py --undo` refuses. The guard
  goes only on a repaired, accepted form; its own rollback is the RUNBOOK's.
- **The template is behind** (synced by hand): its guard dry run also
  carries 23 roster creates and 12 updates. They land at the roster slot
  (above the links), but a separate plain sync apply before `--club-guard`
  keeps the guard's apply small and easier to read.
- **Order-update semantics unobserved; multi-select `calcValues` layout
  unverified; guard rules +60-69% on the largest forms** — as in the two
  plans: the template first, the probe, the `--rendered` hard stop.
- **Two Submit buttons on a guarded form** give two form_status lines (the
  layout's and the guard's), each with its own consequence — cosmetic.

## Proof
Read-only, 2026-09-30 (GETs, dry runs and one Roster export read with
`tools/sheets_client.py export`, kept in the session's scratch directory and
deleted afterwards; counts, qids and orders only).

1. `python3 tools/fix_roster_order.py` (dry run, all five): 9 moves each,
   Submit first, the seven hidden fields bottom-up, q443 last — template
   123 of 342 rosters below q443, targets 368-376; Africa 98 of 221, 247-255;
   Asia 17 of 96, 122-130; Latin America 26 of 39, 65-73; U.S 5 of 12,
   38-46 (the same as the rosters plan's proof).
2. `python3 tools/form_status.py --roster <export>`: every form has the
   `layout:` problem (first roster below: q333 template and Africa, q401
   Asia, q348 Latin America, q371 U.S); the SUPER GIRLS rule on the template
   and Africa only; `club guard: none` everywhere; 0 flagged as error and
   Salesforce yes on all five. `--rendered` on the template: 336 picker
   options, none with a `data-calcvalue` yet. Each regional form still
   reports one roster on the form but not in the Roster (q158, not from
   these branches).
3. `sync_attendance_form.py <export> --roster --form 262352490535154
   --club-guard` (dry run): `New rosters go at order 235, above
   somethingNotWorking (q443)`; 23 `CREATE roster` (each at order 235), 12
   `UPDATE roster`, `UPDATE club picker (359 clubs: calcValues, options)`,
   `CREATE club guard (below the Club picker)` at order 4 (the picker is at
   3, q5 at 4), `REPLACE conditions (378 rules + ~23 more once the new
   rosters exist)`, `conditions: 375 kept, 3 new, 1 dropped` (the two guard
   rules and the SUPER GIRLS spelling).
4. `python3 tools/auto_sync.py --roster <export>` (dry run, no
   `--synclog`): all four regions `in-sync` (Africa's one-rule spelling
   difference is not a change to the runner).
5. `git merge-tree --write-tree main wf5/integration`: clean; `main` is an
   ancestor of the branch.

`make check` (with `CSV=` pointing at the 2026-08-24 enrollment export):

```
real data (../../../data/enrollment_2026-08-24.csv): parsed 328 clubs, 6210 girls
ALL CHECKS PASSED
ALL CHECKS PASSED
ALL CHECKS PASSED
py: 34 files parse, 20 scripts answer --help
Ran 221 tests in 0.253s
OK
gs: 10 files parse
secrets: clean (134 files scanned)
docs-links: ok (51 relative links resolve, 0 absolute paths)
fixtures: up to date
CHECK PASSED
```
