---
title: Question 331 (Partner) filled with the picked club's partner on the forms with the Club picker
author: Claude (ticket #236)
status: accepted      # ticket #236; the code lands offline, every live step waits on Ryan's go
created: 2026-11-23
intent: ticket #236, the prerequisite of #225 - the photo subfolders are named `{Partner} | {Club Name} | {Date} | {Week}`, and q331 is blank on every form with the Club picker
---

# Plan: The Partner fill (q331)

Ticket #236, the prerequisite of #225 (the Google Drive photo folders by partner and month; its
plan, `docs/plans/2026-11-19-photo-folders-partner-month.md`, is on the #225 branch). Procedures:
RUNBOOK "Club names two partners share" (the typed Partner box) and "Backup and restore
(Jotform)".

## Context

- Jotform's Google Drive integration names each photo subfolder from the submission's fields,
  `{Partner} | {Club Name} | {Date} | {Week}`. On a form with the Club picker question 331
  (`glow/sync.py PARTNER`) is hidden since 2026-09-30 and nothing fills it: the folder's partner,
  and the staff notification e-mail's "Partner" row, are blank.
- The change: `build_conditions` gains section E. On a form with the fill, one calculation per
  partner: its clubs' picker entries (`picker equals <entry>`, any of them) -> the partner's name,
  as text, into q331. Appended after every other rule and minted last, so no rule of today moves.
  The partner is the data's - the Roster's for a club in the export, else the one the form's rules
  name (as the summary's `sf_names`) - never split out of an entry at " - ". No fill for a retired
  roster, a roster whose partner nobody knows, or rosters the typed box still tells apart; a
  partner whose name holds `{`, `}`, `[` or `]` gets no rule and a `!` line.
- The switch: `--partner-fill`, by hand, once per form. Afterwards the form's own rules (a
  calculation into q331) keep it on, so the runner, which never passes the flag, keeps it and adds
  each new club to its partner's rule in the run that creates it. A form not rolled out never gets
  it from the runner: no flag, nothing in its rules.
- Refused before any write, dry run or apply: `--partner-fill` on a form without the Club picker,
  and on a form where a rule still shows q331 (run `--same-name-switch` first, or in the same run).
  A form whose rules hold the fill but whose rosters are told apart by the box again: no fill rules,
  a `!` line naming q331, the run goes on.
- q331 stays hidden; the HIDE of the box is unchanged. q5 is untouched: the fill writes only q331.
- Two runtime readings, unproven until the template's test below: a calculation whose condition
  turns false does not blank q331 (a mentor who picks one club, then another partner's club), and
  a literal-text equation (no `{field}` in it) is written as is.
- A partner renamed with no roster change is a rules-only difference: the runner reads the form
  as `in-sync` and does not apply it until the next roster change on that form (or a hand apply).

## Rollout (live)

Every step on Ryan's go, one form at a time, after the PR has landed. The runner keeps running:
it never adds the fill, and on a form that has it, it keeps it.

1. **Template** `262352490535154`: today's exports (`tools/sheets_client.py export Roster` and
   `Partners`), then `python3 backup_forms.py --form 262352490535154`.
2. Dry run: `python3 sync_attendance_form.py data/roster_<date>.csv --roster --partners
   data/partners_<date>.csv --form 262352490535154 --partner-fill`. Expected: `Partner fill: q331
   (Partner) is filled from the Club picker - N rule(s), one per partner` (N = the partners with a
   club on the form), `conditions: K kept, N new, 0 dropped`, and the only call `REPLACE conditions
   (K+N rules)`; no question-5 line, no `HIDE`.
3. The same command with `--apply`, then `python3 tools/form_status.py --form 262352490535154
   --roster data/roster_<date>.csv --partners data/partners_<date>.csv`: rules CLEAN, and a second
   dry run without the flag says `(conditions unchanged - skipping the rewrite)`.
4. One test submission on the template, arranged to change nothing in Salesforce (the recipe in
   RUNBOOK "Photos", step 3): pick a club, then, before submitting, switch to a club of a partner
   in the middle of the fill's order - not the alphabetically first, whose rule runs last in
   Jotform's walk (index 0 runs last) and would pass by luck. Check that the submission's q331 holds the second club's partner (proves the
   false-turned condition does not blank q331, and that the literal text is written as is), that
   q5 is the second club's entry as before the fill, and that the staff e-mail's "Partner" row
   shows the partner. Then delete the test submission.
5. Each regional form in turn (Latin America `262383455778067`, Asia `262383129464057`, Africa
   `262382821971058`; U.S `262382706852058` is disabled, `--disabled-ok`): steps 1-3 with
   `--region '<region>'` and its form id. No test submission on a regional form: the read-back is
   the first real submission's staff e-mail, its "Partner" row filled.
6. `python3 tools/auto_sync.py` (dry run): every region `in-sync`.

## Rollback

Per form, in one sitting:

1. `python3 restore_conditions.py --form <id> --from conditions-<stamp>.json` from step 1's
   backup, dry run then `--apply`: the rules as they were before the fill. It refuses a snapshot
   that tests a club the picker no longer offers (renamed or retired since step 1); then add
   `--force` - step 2 rebuilds those rules.
2. At once, the sync by hand without `--partner-fill` (step 2's command on today's exports, dry
   run then `--apply`): with no calculation into q331 left the fill stays off, and every picker
   entry gets its rules back. Not optional: a club added since step 1 passes the restore without
   its show rule, its question 18 operand and its club-guard term, and the runner reads that
   rules-only difference as `in-sync` - its roster would never show and, on a guarded form, its
   mentors could not submit.
3. `python3 tools/form_status.py` (step 3's command): rules CLEAN.

A revert of the code alone does not remove the fill from a form that has it until that form's next
rewrite: roll the forms back first.

## Risks

- A calculation into q331 that Jotform's runtime blanks when its condition turns false: q331
  blank or wrong for a mentor who changed club. Step 4 tests exactly that on the template before
  any regional form; if it fails, roll the template back and stop.
- A partner name a calculation misreads (`{`, `}`, `[`, `]`): no rule, a `!` line; its clubs'
  q331 stays blank, as today.
- A form where the typed box tells rosters apart: refused with the flag, no fill without it.
- The runner: never passes `--partner-fill` (a test pins it); on a filled form a new club joins
  its partner's rule in the same run.

## Proof

Offline (2026-11-23): `scripts/harness_tests.sh test/partner_fill_test.py` - 14 tests OK; the
neighbouring suites (`sync_conditions_test`, `same_name_test`, `form_status_test`,
`auto_sync_test`, `runbook_test`, `doc_refs_test`) OK; `ruff check .` clean.

## Result

Pending the live rollout (Ryan's go, one form at a time).
