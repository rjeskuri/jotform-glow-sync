---
title: Move a club to its real partner (a mistyped partner), first use 2026-09-24
author: Claude (with Ryan)
status: done (applied 2026-09-28; accepted by Ryan 2026-09-24, in conversation: gated tool; blank the typo's Partners row with a note; the raw enrollment response stays as it is)
created: 2026-09-24
intent: none — an operational correction Ryan asked for on 2026-09-24
---

# Plan: move Club Glow Traslasierra from "ion bu" to Fundación Kaleidos

Fundación Kaleidos could not add a girl to Club Glow Traslasierra: the Club
Roster Form's "Club (Fundación Kaleidos)" list shows only Club Glow Chacarita.
The Latin America attendance form shows Traslasierra's roster normally.

**Cause** (read-only export of every tab, 2026-09-24). On the old Google
enrollment form (Enrollment Responses row 250, 2026-03-15) the partner of
Traslasierra was typed as `ion bu`. Six minutes later the same submitter
enrolled Chacarita as `Fundación Kaleidos`. The 2026-08-26 build therefore
filed the club under a partner of its own: 32 active Roster rows, ClubRegistry
`CLUBGLOW`, and a Partners row `ion bu` (Latin America, derived). The Google
Form's partner sections come from the Roster's partner column
(`Forms.gs` `syncFormChoices`), so the club sits in an `ion bu` section. The
Jotform attendance form keys a club by its question label only, so it never
noticed. That submitter e-mail is the only one whose clubs are split across
two partners, and none of Kaleidos's 13 Chacarita changes on 09-14 match a
Traslasierra name, so nothing was misfiled.

**What a correct move is** (mapped by three code readers, each checked by a
skeptic, plus a completeness critic):

- Jotform: nothing changes. `sync_attendance_form.py` matches roster
  questions by label, and a Partner (q331) term exists only for club names
  shared by several partners. Traslasierra's name is unique and its live show
  rule (q352, 09-20 backup) is `picker equals 'Club Glow Traslasierra'` with
  no Partner term. Salesforce receives only the club name (q5).
- The partner cell of **every** Roster row of the club (any status) and of
  its **one** ClubRegistry row must change **in one batch**. With Roster and
  ClubRegistry apart, the next Roster-change submission mints a new club code
  (`Ids.gs` looks codes up by partner + club). With only some Roster rows
  changed, the sync sees two same-named clubs, makes both questions
  Partner-gated and creates a duplicate, all within the safety bands.
- The new partner string must be byte-identical to the Partners tab's
  `Fundación Kaleidos`. `key_` folds neither accents nor Unicode form, so
  `Fundacion Kaleidos` would be a third partner.
- The `ion bu` Partners row keeps `ion bu` in both partner dropdowns. Blanking
  its partner cell (with a note) removes it: every Partners reader skips a
  blank partner (`Forms.gs` `partnerChoices_`, `Roster.gs`
  `loadPartnerTabRegions_`/`seedPartners_`, `upload_roster.merge_partners`).
  No row is deleted. The orphaned `ion bu` section stays on the Google Form,
  unreachable; nobody should remove it by hand (if someone does, remove the
  page break AND its list).
- A direct sheet write triggers nothing: afterwards someone must click
  GLOW → Google Forms → Update form dropdowns from the Roster.
- The raw Enrollment Responses row 250 stays as it is (Ryan, 2026-09-24:
  the tab is append-only). Consequence, recorded in DECISIONS and RUNBOOK:
  "Rebuild roster from enrollment responses" and the offline build +
  `upload_roster.py --replace` must not be run after launch. They would
  re-create the club under `ion bu` with new ids, and they already reactivate
  every girl removed since 2026-09-01.

## Files that change
- `tools/rename_club.py` — `--new-partner` moves the club to another partner
  (with or without `--new`; `--club` is an alias of `--old`). The target must
  be in the Partners tab, and its exact spelling there is what gets written.
  Refuses when: the target is missing (suggests the accent-folded match), the
  target's region is blank or differs from the club's rows, the target
  already has a club of that name, or the club's name is shared with another
  partner's club (Partner-gated rules). With a Jotform key, it also refuses
  when the club's show rule on a form carries a Partner term. Blanks the old
  partner's Partners row with a note when it has no rows left
  (`--keep-old-partner` skips that). Same ritual as a rename: tabs saved under
  `data/rename_club/<stamp>/`, one RAW batch, re-read and compare, one Audit
  row (`moveClub`). Cell matching strips invisible characters, as `key_` does.
  After the adversarial review (2026-09-25; 17 findings, 3 refuted), the tool
  also: re-reads just before the write and stops, with nothing written, if the
  club gained a row or a planned row changed; writes rows of the club that
  arrive during the write in a second verified batch (the review reproduced a
  split club from a submission in that window); refuses `--sheet-only
  --apply` on a move, so the Partner-rule check always runs; compares only
  the written columns on rows it did not address; treats a cell-count
  mismatch as a note and lets the re-read decide. A second round (5
  findings, 2 refuted, none important; privacy audit clean) added: the
  pre-write re-read plans again (a row edited into the club, or another club
  enrolled under the typo, which must keep its Partners row, stops the run);
  the late rows are verified whole; the cells a form handler flips in place
  (status, removed_date) and another Partners row's notes no longer fail the
  verify.
- `test/python_test.py` — `RenameClub`: move-mode helpers on fabricated tabs;
  `main()` on an in-memory sheet (dry run, apply, Partner-gated refusal,
  `--sheet-only --apply` refusal, a row arriving before and during the
  write); the invisible-character class checked against `Normalize.gs`.
- `docs/RUNBOOK.md` — "Moving a club to another partner"; the Club Roster
  Form's "Not listed? enroll a NEW club" trap; the rebuild warning.
- `docs/ARCHITECTURE.md` — tool table. `docs/DECISIONS.md` — one row.
  `docs/BACKLOG.md` — guard the rebuild menu item; reword the "Not listed?"
  help text. `appsscript/INSTALL.md`, `docs/SHEETS-ACCESS.md` — "re-running
  is always safe" is no longer true after launch.

## Order of work
1. This plan, committed.
2. Tool + tests + docs; `make check` green; commit.
3. Dry run against the live sheet (reads only):
   `python3 tools/rename_club.py --partner "ion bu" --club "Club Glow Traslasierra" --new-partner "Fundación Kaleidos" --sheet-only`
   Expect: 32 Roster cells (or more, if Kaleidos used the `ion bu`
   workaround meanwhile), 1 ClubRegistry cell (CLUBGLOW kept), 0 SF Pending,
   Partners row `ion bu` blanked, 1 Audit row.
4. Ryan's go. Then Ryan runs the same command with the Jotform key exported
   and without `--sheet-only`, plus `--apply` (or relaunches Claude Code with
   `GLOW_LIVE_OK=1` and `JOTFORM_API_KEY` exported and Claude runs it). Every
   write is verified by re-reading.
5. Ryan, in the sheet, straight away: GLOW → Google Forms → Update form
   dropdowns from the Roster. Preview the form without submitting: Existing
   club → Fundación Kaleidos lists Chacarita and Traslasierra; `ion bu` is gone.
6. Export the Roster; `tools/auto_sync.py --region "Latin America"` dry run →
   in-sync; `tools/form_status.py --form 262383455778067 --roster …` → CLEAN.
7. Tell Fundación Kaleidos to add the girl: Existing club → Fundación
   Kaleidos → Club Glow Traslasierra.

## Risks
- **Kaleidos enrolls the club again** through "Enroll a NEW club" (the
  Existing-club page's help text, "Not listed? Your organization has no
  enrolled clubs yet — go back and choose Enroll a NEW club", points there). That
  would duplicate the club with new ids and Partner-gate its roster. Mitigation:
  tell them now; until step 5 the club can be reached through Existing club →
  `ion bu`. Rows added that way are picked up by the tool, which counts at
  run time.
- A submission processed during the write: cells are addressed by row number,
  so the tool re-reads and compares every pre-existing row. Rows appended
  meanwhile are reported and left alone.
- A wrong target spelling: the tool writes the Partners tab's own spelling
  and refuses a name it cannot find.
- A future rebuild from the raw responses brings `ion bu` back: documented as
  "do not run after launch"; guarding the menu item is a backlog item.
- Salesforce: the club's Account may sit under a partner or parent named
  `ion bu`. That is outside the repo, and Ryan checks it. Attendance is
  unaffected (Salesforce reads only the club name).
- Rollback: the partner cells and the Partners row from
  `data/rename_club/<stamp>/`, or the same tool with the partners swapped once
  the `ion bu` row is restored. No form is written.

## Proof
`make check` tail; the tool's dry-run and apply output (partner and club
names and row numbers only; no girls' names or ids); the Audit row; the
dropdown refresh; `auto_sync` in-sync and `form_status` CLEAN. All pasted in
the conversation and summarised here when done.

## Result
Applied 2026-09-28 with Ryan's go, from a session launched with the live flag and the Jotform
key: dry run first, then `--apply`. Roster rows 4346-4377 (32 cells), ClubRegistry row 233
(code CLUBGLOW kept), Partners row 24 (`ion bu` blanked, note added; 2 cells), 0 SF Pending
rows, 1 Audit row — each written and re-read. The tabs before the change are in
`data/rename_club/2026-09-28T153128/`. No form writes: q352's show rule on the Latin America
form and the template has no Partner term. Afterwards `auto_sync.py --region "Latin America"`
(dry run) said in-sync, "nothing to do", and `form_status.py` on 262383455778067 said CLEAN
(68 conditions, 0 flagged, salesforce yes). Remaining: Ryan's GLOW → Google Forms → Update form
dropdowns from the Roster, a preview of the Existing-club page, and telling Fundación Kaleidos.
