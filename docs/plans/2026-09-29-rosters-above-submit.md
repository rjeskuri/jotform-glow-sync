---
title: Every roster renders above the links and the Submit button
author: Claude (workflow track wf5/rosters-above-submit, 2026-09-29)
status: done             # accepted by Ryan 2026-09-30; merged (3ed68b2) and applied to all five forms the same day (Result)
done: 2026-09-30
backlog: 47
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
  written to that form or any later one — and says what Jotform stored and
  what the re-read shows (every roster above Submit, or how many below:
  measured, not assumed). If other orders changed too (a renumber, or
  another writer) it says to open the form, and that `--undo` refuses when a
  roster's order changed; if only the written element is off, that `--undo`
  puts it back. The targets assume a stored `order` is kept as sent (or
  inserted into an empty slot, which shifts nothing); if Jotform renumbered
  the form on an update or ignored the value, a later link could land below
  Submit. When the first write lands as sent the form is in a safe state
  (Submit at the end: every roster above it, the links still above it).
  Cost: one GET per form (7 GETs + 9 POSTs).
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
- **A rollback command, `--undo <stamp>`** (not in the design, which had the
  old orders re-posted from the snapshot by hand): `plan_restore` puts back
  the orders of `backups/<id>/questions-<stamp>.json` by the same path as the
  repair — dry run first, planned before written, probed, verified — links
  first (top-down), then the hidden fields, Submit last, so the links stay
  above Submit at every step and every target is empty when written. It
  refuses once the form's questions or a roster's order differ from the
  snapshot (the sync created or moved something since), and when the
  snapshot holds two questions at an order it would write back (a tie: the
  Club Roster Form link placed before the repair leaves Submit sharing the
  next hidden field's order) — writing onto a taken order would rest on
  unobserved semantics; then the builder, or Jotform's Revision History.
  Hand-posting orders under pressure is where a link would land below
  Submit. After a stop and a re-run, the stopped run's stamp stays the
  rollback to the form before the repair: the re-run's plan says
  `part-way: …`, and every stop that follows a write repeats its own run's
  `--undo` line.
- The repair is a separate tool, never part of the runner: 45 order writes
  on five live forms want a person watching, a snapshot, and a browser check.
- Translations (keyed by text or `text_<qid>`), the rules, the e-mails
  (custom bodies built from placeholders) and the Salesforce mapping (qids)
  do not depend on `order`; q5 stays hidden and filled by the picker
  calculation; `build_conditions` is untouched.

## Files that change
- `glow/layout.py` (new) — `fence`, `rosters_below`, `roster_slot`,
  `plan_tail_moves`, `plan_restore` (the undo), `audit_layout`, `summary`
  (form_status `--json`).
- `glow/links.py` — docstring: the layout helpers live in `glow/layout.py`.
- `sync_attendance_form.py` — the roster slot (above), the plain line, the
  tie warning.
- `tools/fix_roster_order.py` (new) — the repair tool and its `--undo`.
- `tools/form_status.py` — `audit_layout` into `rule_problems`, `layout` in
  the JSON, a `layout:` line.
- `test/python_test.py` — `RosterLayout` (fence, slot, both Jotform
  behaviours, the tail plan and its refusals, re-runs, the audit),
  `FixRosterOrderTool` (dry run, refusal before any write, snapshot first,
  drift, probe and its messages, API errors on the re-reads, the part-way
  note, verify, `--form`, `--undo`), `RosterRepairRunbook` (the runner
  paused before the merge; 45 and 46 after the repair),
  `SyncLeavesTheLinksAlone` extended (the
  CREATE's order renders above the links under both behaviours),
  `PartnerPickerFlow` (no Submit: still highest + 1), form_status and
  `verify_report` wiring. Fictional clubs and girls only.
- `.claude/skills/jotform-api/SKILL.md` — inserting at a taken order shifts
  the block below; an order update is unobserved until the template repair.
  `.claude/skills/live-systems/SKILL.md` — the tool's `--apply` among the
  writers.
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

Rollback per form: `python3 tools/fix_roster_order.py --form <id> --undo
<stamp>` (dry run; `--apply` writes) with the stamp the tool printed with
its snapshot (`backups/<id>/questions-<stamp>.json`) — after a stop and a
re-run, the stopped run's stamp (the re-run's snapshot holds the part-way
form) — or Jotform's Revision History. `--undo` is for right after the
repair, before the Club Roster Form link is placed. Nothing but `order`
changed.

## Risks
- **Order-update semantics unobserved.** Empty target slots make set and
  insert render the same; the probe after the first write stops the run on
  anything else; the template goes first; the snapshot is the rollback.
- **The runner creating a roster mid-repair.** Paused first (step 1); the
  tool re-reads and re-plans right before writing and refuses on drift; the
  verify catches a change during the writes.
- **A gateway 504 hiding a completed write.** The tool stops on any API
  error — a write, the snapshot, the probe's or the verify's re-read — with
  how many moves were confirmed and, when the verify did not run, a
  `form_status --form <id>` to run after the dry run; it says to re-run the
  dry run first — the re-plan starts from what the form holds, and a stop
  anywhere ends in the same layout.
- **Jotform ignoring the order.** The probe or the verify says so; form_status
  keeps the form NOT CLEAN.
- **The new check turns every form NOT CLEAN at merge** until the repair —
  hence the paused runner and the repair straight after the merge.
- **A verify false alarm.** The verify compares every question apart from
  `order` by hash; should Jotform add or normalise a property on a question
  whose order is posted, the template stops with `MISMATCH` after its nine
  writes — the layout is then finished, the other forms untouched, and the
  tool needs a look before the regionals. The template going first is what
  makes this cheap.
- **Cosmetic:** the builder and the submissions table list fields in `order`;
  the tail's hidden fields move to the end with it.
- **Both tracks touch `sync_attendance_form.py` and `tools/form_status.py`**
  (the club-guard track too): the integration branch merges them.

## Proof
Read-only, 2026-09-30 (GET only; the key from the environment; nothing
written to any form or the sheet). Counts, qids and orders only.

| Form | Rosters | Below the fence | Fence (q443) | New-roster order now | Repair targets | New-roster order after |
|---|---|---|---|---|---|---|
| template 262352490535154 | 342 | 123 | 236 | 235 | 368–376 | 367 |
| Africa 262382821971058 | 221 | 98 | 140 | 139 | 247–255 | 246 |
| Asia 262383129464057 | 96 | 17 | 96 | 95 | 122–130 | 121 |
| Latin America 262383455778067 | 39 | 26 | 30 | 29 | 65–73 | 64 |
| U.S 262382706852058 | 12 | 5 | 24 | 23 | 38–46 | 37 |

1. `python3 tools/fix_roster_order.py` (dry run, all five forms): on each,
   `N of M rosters render below somethingNotWorking (q443); 9 element(s)
   move to orders …` and the nine moves — Submit first, the seven hidden
   fields bottom-up, q443 last (Africa: `move submit2 (q2) 141 -> 248` …
   `move somethingNotWorking (q443) 140 -> 247`). Two runs ten minutes
   apart printed the same plan.
2. `python3 tools/form_status.py --roster <a fresh Roster export>`: every
   form `layout: N of M rosters render below somethingNotWorking (q443)
   (first q…) - run tools/fix_roster_order.py (dry run first)` and `1
   PROBLEM(S)` (that line), with `0 flagged as error` and `salesforce yes`;
   first roster below: q333 (template, Africa), q401 (Asia), q348 (Latin
   America), q371 (U.S). Also, not from this track: each regional form
   reports 1 club "on form but not in roster" (q158, a roster whose label
   differs from the Roster's spelling of the club by one space).
3. The sync's dry run per region on that export
   (`tools/sheets_client.py export Roster`, a read): all four `nothing to
   do - form already matches the sheet`, so no order line (it prints only
   when there is a roster to create). On a scratch copy with one fictional
   club added per region: `New rosters go at order 139, above
   somethingNotWorking (q443)` (Africa), 95 (Asia), 29 (Latin America), 23
   (U.S); each plans `CREATE roster '…' (1 girls)` in the unchanged wording,
   an `UPDATE club picker` and `REPLACE conditions`, and no new warning.
4. An offline simulation over the same reads (a scratch script, not
   committed): on every form one and two creates at the order above land
   above q443 whether Jotform inserts or ties; the nine moves leave no
   layout problem, no roster below, the sequence a mentor sees unchanged
   and a re-plan empty; a stop after any of the first eight moves, re-run,
   ends in the same render sequence; after the repair a create lands above
   under both behaviours; the undo plan restores every order; nothing but
   `order` differs. With the Club Roster Form link (46): placed before the
   repair (then 10 moves) or after it, the form ends clean, and a partner
   list inserted at order 7 (45) plus a new roster afterwards still leave
   every roster above. Placed before the repair, `plan_insert` leaves Submit
   sharing the next hidden field's order, so `--undo` refuses that snapshot
   (the tie) and the rollback is Revision History; placed after it (the
   order of the live steps), `--undo` works until the link is placed.

`make check` (with the real export via `CSV=`; after the review fixes of 2026-09-30):

```
real data (../../../data/enrollment_2026-08-24.csv): parsed 328 clubs, 6210 girls
ALL CHECKS PASSED
ALL CHECKS PASSED
ALL CHECKS PASSED
py: 34 files parse, 20 scripts answer --help
Ran 160 tests in 0.155s
OK
gs: 10 files parse
secrets: clean (130 files scanned)
docs-links: ok (46 relative links resolve, 0 absolute paths)
fixtures: up to date
CHECK PASSED
```

## Result (2026-09-30, with Ryan's go)
`AUTO_SYNC_APPLY=0`, merged into `main` as a fast forward (`3ed68b2`, pushed), then:

| Form | Rosters below q443 before | Moved to | Probe (after writing Submit) | Rollback stamp |
|---|---|---|---|---|
| template 262352490535154 | 123 of 342 | 368–376 | q2 holds 369 as sent; no other order changed | `2026-09-30T140906` |
| Africa 262382821971058 | 98 of 221 | 247–255 | q2 holds 248 as sent; no other order changed | `2026-09-30T141020` |
| Asia 262383129464057 | 17 of 96 | 122–130 | q2 holds 123 as sent; no other order changed | `2026-09-30T141020` |
| Latin America 262383455778067 | 26 of 39 | 65–73 | q2 holds 66 as sent; no other order changed | `2026-09-30T141020` |
| U.S 262382706852058 | 5 of 12 | 38–46 | q2 holds 39 as sent; no other order changed | `2026-09-30T141020` |

- Each form: `re-read: verified - every roster above somethingNotWorking (q443), 9 orders as sent,
  nothing else changed`. Jotform keeps a posted `question[order]` exactly (recorded in the
  jotform-api skill).
- The public pages (curl, parsed in memory, counts only): 0 rosters below q443 or Submit on all
  five; the newer rosters (qid ≥ 333) all above Submit (Africa 98, Asia 17, Latin America 26, U.S 5).
- The new-roster slot, live: the template's catch-up sync (23 creates, 13 updates, backup
  `backup_forms.py --form 262352490535154` first) printed `New rosters go at order 367, above
  somethingNotWorking (q443)`; the page shows all 23 (q459–q481) above Submit; a second dry run
  `nothing to do`.
- `form_status.py --roster` (fresh export): `layout: every roster above somethingNotWorking (q443)`
  and CLEAN on all five (after Africa's one-rule SUPER GIRLS apply, BACKLOG 48).
- `AUTO_SYNC_APPLY=1`; a manual runner apply (GitHub run 36672683641): Africa, Latin America,
  U.S in-sync, Asia `applied - 0 create(s), 1 update(s) … verified clean`; `auto_sync.py` dry run
  in-sync everywhere.

Next: re-count BACKLOG 35's empty submissions for two weeks (to 2026-10-14).

## From the RUNBOOK (moved 2026-10-09)

What `docs/RUNBOOK.md` carried for this plan until its 2026-10-09 restructure (the procedure as run, or its history), word for word (links re-pointed to this folder); the RUNBOOK keeps a stub that links here.

### "Rosters above Submit": the one-time repair

A mentor sees her girls' names where her club's roster renders, so every
roster must render above the links and the Submit button. Until 2026-09-29
the sync created each new roster at the form's highest order + 1 — after
Submit — and every roster created since the 2026-08-24 overhaul rendered
under the button (Africa 98 of 221 on 2026-09-29; BACKLOG 47). Two parts
(`glow/layout.py`, [plan](2026-09-29-rosters-above-submit.md)). The
repair ran on all five forms on 2026-09-30; the steps below stay for a
relapse (`form_status` names it) or a new regional form:

- **The sync** gives a new roster the order of the last roster rendering
  above the first link (or above Submit when there is no link). Jotform
  inserts a question created at a taken order there and moves the block
  below down by one, so the new roster lands just above that roster; were
  it to keep both at that order, the newer one would render just after it.
  Either way it is above the first link. Its plan says where: `New rosters
  go at order 139, above somethingNotWorking (q443)`. No extra write; the
  links and Submit are never written by the sync. A form with no Submit and
  no link (the test fixtures) still gets the highest order + 1.
- **The one-time repair**, `tools/fix_roster_order.py`, moves what renders
  at and below the first link — the links, Submit, the seven hidden bridge
  fields — to empty orders after the last one, in the same sequence. Nine
  order writes per form (ten once the Club Roster Form link is on it); no
  roster, rule, translation, e-mail or Salesforce mapping is written.

```bash
# first: AUTO_SYNC_APPLY=0, before the merge (below)
python3 tools/fix_roster_order.py                                        # dry run: the template + 4 regionals
python3 tools/fix_roster_order.py --form 262352490535154 --apply         # the template first; open its page
python3 tools/fix_roster_order.py --apply                                # then the four regionals
python3 tools/form_status.py --roster data/roster_<date>.csv             # every form: layout: every roster above …
python3 tools/fix_roster_order.py --form <id> --undo <stamp>             # the rollback (dry run; --apply writes)
```

From the merge (the check ships with it) until every form is CLEAN:
repository variable `AUTO_SYNC_APPLY=0`, set before merging — an unrepaired
form is NOT CLEAN for `form_status`, so a runner apply would end
`applied-with-problems` — then back to `1`. Run the repair in the same
sitting as the merge: until a form is repaired, `form_status` shows the
`layout` problem on it, so no other procedure's "CLEAN" can pass there (the
manual loop, renaming or moving a club, the Club picker, the same-name
switch, the club guard). That line is this section's job, not theirs.

The tool plans all five forms before it writes any and refuses — on every
form — rather than guess: two Submit buttons, a page break, a field a mentor can
see below the first link, a link below Submit, or a simulation of the moves
that would leave a roster below the links or change what a mentor sees.
With `--apply`, per form: a snapshot (`backups/<id>/questions-<stamp>.json`,
stamped to the second; the tool prints the `--undo` line), a re-read and
re-plan (a form changed since the preview is not written), Submit first
(then every roster is above it), the hidden fields, the links last. After
the first write a re-read checks that Jotform kept the order as sent and
moved nothing else. Otherwise it stops after that one write and says what
Jotform stored and what the re-read shows (whether every roster is above
Submit). If other questions shifted too, open the form; if a roster's order
changed, `--undo` refuses (then the builder, or Revision History). After the
last write a re-read verifies the whole form: the same questions, identical
apart from `order`, the orders as sent, every roster above the links and
Submit, the rules unchanged. Anything unexpected — an API error on any read
or write included — stops the run, and later forms stay untouched; the stop
says how many moves were confirmed and, once anything was written, repeats
the `--undo` line. After a
stop (or a gateway 504) run the dry run again first: it re-plans from what
the form holds, a form left part-way says `part-way: …`, and a finished
form says `nothing to do` — if the stop came before the verify, then run
`form_status --form <id>` on it. Keep the stopped run's `--undo` stamp: it
is the rollback to the form before the repair, and it works from the
finished form too; a re-run's snapshot holds the part-way form (undoing it,
then the first stamp, still gets back).

`form_status` checks the layout on every run (`layout:` line, `layout` in
`--json`): a roster rendering below the first link or Submit, a link below
Submit, or not exactly one Submit makes the form NOT CLEAN — and the
runner's verify sees it. Rollback: `--undo <stamp>` puts the snapshot's
orders back by the same path (planned, probed, verified). It is for right
after the repair, before the Club Roster Form link or the club guard is
placed (the guard's warning is created at the picker's order + 1, which
moves the rosters below it down by one, up to the first gap): it refuses
once the form's questions or a roster's order have changed since, and when
the snapshot holds two questions at one order (the link placed before the
repair leaves Submit sharing the next field's order) — then the builder, or
Jotform's Revision History. The builder and the submissions table list
fields by `order`, so the hidden fields move to the end there too
(cosmetic).
