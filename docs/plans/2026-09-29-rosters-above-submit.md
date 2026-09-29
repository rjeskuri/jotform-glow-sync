---
title: Every roster renders above the links and the Submit button
author: Claude (workflow track wf5/rosters-above-submit, 2026-09-29)
status: proposed         # Ryan accepts before merge; every live step needs his go
created: 2026-09-29
intent: none — BACKLOG 47 (found 2026-09-28 while building the Club Roster Form link); design read-only on 2026-09-29
---

# Plan: rosters above Submit (BACKLOG 47)

## Why
The sync creates every new roster question at the form's highest order + 1,
so it lands after the Submit button and the problem-report link above it. A
mentor who picks such a club sees her girls' names under the button. Read
2026-09-29 (GET only), every roster below Submit was created after the
2026-08-24 overhaul:

| Form | Rosters | Below Submit | q443 / Submit order | Highest order |
|---|---|---|---|---|
| Africa 262382821971058 | 221 | 98 | 140 / 141 | 246 |
| Asia 262383129464057 | 96 | 17 | 96 / 97 | 121 |
| Latin America 262383455778067 | 39 | 26 | 30 / 31 | 64 |
| U.S 262382706852058 | 12 | 5 | 24 / 25 | 37 |
| template 262352490535154 | 342 | 123 | 236 / 237 | 367 |

(Asia gained a roster below Submit between the design read and this plan.)
Every form is laid out the same way: orders 1..N with no gaps, ties or page
breaks; the top fields; the rosters in two blocks with the **tail** between
them — the problem link q443, Submit q2, then seven hidden fields (q103, q18,
q98, q100, q102, q105, q109).

Evidence that it matters (picker era, 337 submissions, counts only): a
submission with no girl ticked came from a club whose roster is below Submit
20% of the time (23 of 114) against 5% above it (12 of 223). Supportive, not
proof — the newer clubs are all below, and Asia shows no effect. BACKLOG 35
(empty submissions) is re-measured two weeks after the repair.

Also learned in the read: creating a question at an order that is taken
**inserts** it there and shifts the following block down by one until the
first gap (template 2026-09-01: the Club picker created at 3, 351 questions
moved; Africa 2026-09-12 the same, the shift stopping at a gap). The
jotform-api skill says the opposite and is corrected. Moving an existing
question by posting a new `order` has never been observed.

## What
1. **New rosters go above the links and Submit** (the sync, every run).
   New `glow/layout.py`, built on `glow/links.py` (`render_key`, `order_of`,
   `elements_on`, `can_appear`, `shown_by_rules`); render order = by
   `order`, equal orders by qid.
   - `fence(questions)`: whichever of the link elements and Submit renders
     first; None when the form has neither; a refusal (exit) with two Submit
     buttons.
   - `roster_slot(questions)` → (order, fence): no fence → highest order + 1
     (today's behaviour); otherwise the order of the **last roster rendering
     above the fence**, or the fence's own order when no roster is above it.
     Right under both behaviours Jotform might show: *insert* (the new roster
     takes the slot, that roster, the fence and the tail shift down) and *tie*
     (the new roster shares the order and, being the newest, renders after
     that roster — still above the fence). Several creates in one run all use
     the same slot.
   - `sync_attendance_form.py`: the `max_order += 1` logic goes; the slot is
     computed once, only when there are rosters to create, next to the
     partner-list checks (so its refusal comes before the first write); every
     `CREATE` posts `question[order]=<slot>`. The `CREATE roster '…' (N
     girls)` label is unchanged (the runner's `CREATE_RX` and the plan hash
     read it). One plain line says where they go — `New rosters go at order
     139, above somethingNotWorking (q443)` — never starting with `!`/`?`
     (the runner counts those as warnings). No extra writes; the sync still
     never writes the links or Submit.
2. **One-time repair: `tools/fix_roster_order.py`** (by hand, gated; separate
   from the runner). Pure `plan_tail_moves(questions, conditions)` in
   `glow/layout.py`: M = the highest order; the tail = every non-roster
   question rendering at or below the fence; its fixed final sequence = the
   links in render order, then Submit, then everything else in render order;
   element *i* of it gets order M+1+*i* — every target slot is empty, so no
   roster is ever written and nothing but the tail moves. Targets: Africa
   247–255 (q443 247, q2 248, hidden 249–255), Asia 122–130, Latin America
   65–73, U.S 38–46, template 368–376. Nine writes per form (ten once the
   Club Roster Form link is on it).
   - Refuses (writes nothing to any form): not exactly one Submit; a page
     break; a field a mentor can see in the tail other than the links and
     Submit; a link below Submit; a simulation of the moves that would leave a
     roster below the fence, a link below Submit, or the sequence of what a
     mentor can see changed. No roster below the fence → "nothing to do".
   - Apply flow (as `tools/add_feedback_link.py`): every form is planned
     before any is written; per form: `backup_forms.snapshot` (stamped to the
     second), re-read + re-plan (a plan that differs from the preview → nothing
     written to that form), one `POST question[order]` per move, a re-read and
     a verify: the same qids, every question identical apart from `order`
     (compared by hash, never printed), the moved orders as planned and no
     other order changed, no roster below the fence, the links above Submit,
     the rules unchanged (`same_conditions`).
3. **form_status**: `audit_layout(questions)` in `glow/layout.py` — exactly
   one Submit; "N roster(s) render below <fence> (first q…) – run
   tools/fix_roster_order.py (dry run first)"; a link below Submit. Its lines
   join `rule_problems` in `form_report`, so CLEAN requires none and the
   runner's `verify_report` sees a relapse. Kept apart from `audit_rules`
   (whose fixtures have no Submit). `--json` gets a `layout` field; the
   printed report a `layout:` line.

## Design choices — and where this deviates from the approved design
- **Write order: Submit first, then the hidden fields bottom-up, then the
  links bottom-up** (the design had the links before the hidden fields).
  Submit first: after that one write every roster is above Submit. The first
  link — the fence — moves last, so a stop anywhere leaves either a roster
  below the fence, and a re-run (which re-plans from the form as it is) ends
  in the same layout as an uninterrupted run, or the finished layout. With the
  hidden fields last, a stop among them would leave some of them among the
  rosters while the re-run found nothing to do — invisible, but not
  identical. Bottom-up within each group keeps a moved suffix after the
  unmoved prefix, which is what makes the re-plan land on the same sequence.
  On a form with no link Submit *is* the fence and goes last. Every
  intermediate state still renders the links above Submit, in order.
- **A probe after the first write on each form** (not in the design): one
  re-read checks that the moved element took exactly its planned order and no
  other question's order changed; otherwise the tool stops — nothing more is
  written to that form or any later one — and says what Jotform stored. The
  targets assume a stored `order` is kept as sent (or inserted into an empty
  slot, which shifts nothing); if Jotform renumbered the form on an update or
  ignored the value, a later link could land below Submit. After the first
  write the form is in a safe state (Submit at the end: every roster above
  it, the links still above it). Cost: one GET per form (7 GETs + 9 POSTs).
- **The template first, and the run stops at the first form that does not
  verify** (the design's rollout, enforced by the tool): the default target
  order is template, Africa, Asia, Latin America, U.S; a systemic surprise
  shows on the first form and leaves the others untouched.
- **A warning when the last roster above the fence shares the fence's order**
  (not in the design; only a hand edit produces it): under *insert* the new
  roster still lands above the fence, under *tie* it would land below. The
  sync prints `  ! …` (a warning the runner counts, not a refusal — a missing
  roster is worse than a misplaced one) and form_status flags any roster that
  does land below.
- The repair is a separate tool, never part of the runner: 45 order writes
  on five live forms want a person watching, a snapshot, and a browser check.
- Translations (keyed by text or `text_<qid>`), the rules, the e-mails
  (custom bodies built from placeholders) and the Salesforce mapping (qids)
  do not depend on `order`; q5 stays hidden and filled by the picker
  calculation; `build_conditions` is untouched.

## Files that change
- `glow/layout.py` (new) — `fence`, `rosters_below`, `roster_slot`,
  `plan_tail_moves`, `audit_layout`.
- `glow/links.py` — docstring: the layout helpers live in `glow/layout.py`.
- `sync_attendance_form.py` — the roster slot (above), the plain line, the
  tie warning.
- `tools/fix_roster_order.py` (new) — the repair tool.
- `tools/form_status.py` — `audit_layout` into `rule_problems`, `layout` in
  the JSON, a `layout:` line.
- `test/python_test.py` — `RosterLayout` (fence, slot, both Jotform
  behaviours, the tail plan and its refusals, re-runs, the audit),
  `FixRosterOrderTool` (dry run, refusal before any write, snapshot first,
  drift, probe, verify, `--form`), `SyncLeavesTheLinksAlone` extended (the
  CREATE's order renders above the links under both behaviours),
  `PartnerPickerFlow` (no Submit: still highest + 1), form_status and
  `verify_report` wiring. Fictional clubs and girls only.
- `.claude/skills/jotform-api/SKILL.md` — inserting at a taken order shifts
  the block below; an order update is unobserved until the template repair.
- `docs/RUNBOOK.md` ("Rosters above Submit", a note in "Links above
  Submit"), `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/BACKLOG.md`
  (47), `README.md` (the tools table).

## Order of work
1. This plan, committed.
2. `glow/layout.py` + the sync's slot + tests; `make check`; commit.
3. `tools/fix_roster_order.py` + tests; `make check`; commit.
4. form_status `audit_layout` + tests; `make check`; commit.
5. Docs and the skill note; `make check`; commit.
6. Read-only proof against the live forms: the repair tool's dry run on all
   five forms; the sync's dry run where a Roster export is available;
   `form_status` layout lines (GET only). Output under **Proof**.

## Live steps (each needs Ryan's go; none is run by this track)
1. `AUTO_SYNC_APPLY=0` (the new check makes every unrepaired form NOT CLEAN,
   so a runner apply would end `applied-with-problems` until the repair).
2. Merge.
3. The template: `python3 tools/fix_roster_order.py --form 262352490535154`
   (dry run: 9 moves, 368–376), then `--apply`; open the page: every roster
   above the problem link and Submit; record in the jotform-api skill how
   Jotform stored the orders (the tool prints it).
4. The four regionals: `python3 tools/fix_roster_order.py` (dry run: the
   template says "nothing to do"), then `--apply`.
5. `python3 tools/form_status.py --roster data/roster_<date>.csv`: every form
   `layout: every roster above …` and CLEAN; browser check on Africa: a club
   whose roster qid is 333 or higher shows its names above Submit.
6. `AUTO_SYNC_APPLY=1`; `python3 tools/auto_sync.py` (dry run) in-sync.
7. Then the Club Roster Form link (46) and the partner list (45), whose
   checks assume a repaired layout.

Rollback per form: re-post the old orders from
`backups/<id>/questions-<stamp>.json` (the tool's snapshot), or Jotform's
Revision History. Nothing else changed.

## Risks
- **Order-update semantics unobserved.** Empty target slots make set and
  insert render the same; the probe after the first write stops the run on
  anything else; the template goes first; the snapshot is the rollback.
- **The runner creating a roster mid-repair.** Paused first (step 1); the
  tool re-reads and re-plans right before writing and refuses on drift; the
  verify catches a change during the writes.
- **A gateway 504 hiding a completed write.** The tool stops on any error and
  says to re-run the dry run first — the re-plan starts from what the form
  holds, and a stop anywhere ends in the same layout.
- **Jotform ignoring the order.** The probe or the verify says so; form_status
  keeps the form NOT CLEAN.
- **The new check turns every form NOT CLEAN at merge** until the repair —
  hence the paused runner and the repair straight after the merge.
- **Cosmetic:** the builder and the submissions table list fields in `order`;
  the tail's hidden fields move to the end with it.
- **Both tracks touch `sync_attendance_form.py` and `tools/form_status.py`**
  (the club-guard track too): the integration branch merges them.

## Proof
(filled in when the track is done)
