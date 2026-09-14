---
title: Rename a club in place (sheet + forms), first use 2026-09-14
author: Claude (executed with Ryan)
status: done
created: 2026-09-14
intent: none — an operational correction Ryan asked for on 2026-09-14
---

# Plan: rename a club without losing its code, ids or question

A partner enrolled a new club through the Club Roster Form on 2026-09-07 and
typed a person's name into "Club name" by mistake. The club (Seeds of Hope
Foundation, Asia, 14 girls) reached the sheet under that name and, through the
auto-sync of 2026-09-12, the Asia form and the template as a roster question
and a Club-picker option. Leadership wants it called **Brilliant Group**.

A club is keyed by its name in the Roster, ClubRegistry and SF Pending tabs
and by its question label on the forms. Changing the sheet alone would make
the next sync CREATE a second question under the new name and leave the old
one orphaned in the picker (backlog 21 is that situation). Renaming the
question label keeps the qid, the girls' ids (`Ids.gs`: an id never changes
when a club is renamed — the ClubRegistry keeps the code) and lets the next
sync do only what it always does: rewrite the picker options and the rules.

## Files that change
- `tools/rename_club.py` — new; dry run by default; `--apply` saves the tabs
  under `data/rename_club/<stamp>/`, snapshots each form with
  `backup_forms.snapshot`, writes the planned cells in one RAW batch, re-reads
  and compares, appends an Audit row, renames the question label per form and
  re-reads it. Refuses on: club not in the Roster, no single ClubRegistry row,
  the partner already has the new name (sheet or form), several questions with
  the old name.
- `test/python_test.py` — `RenameClub`: the pure helpers on fabricated tabs.
- `docs/RUNBOOK.md` — "Renaming a club"; `docs/ARCHITECTURE.md` — tool table;
  `docs/DECISIONS.md` — rename in place, never delete + create.

## Order of work
1. Tool + tests + docs; `make check` green; commit.
2. `tools/rename_club.py --partner … --old … --new "Brilliant Group"` dry run:
   expect 14 Roster cells, 1 ClubRegistry cell (code kept), 1 SF Pending cell,
   1 Audit row, Asia q446 and template q450.
3. `--apply`; every write verified by re-read.
4. Export the Roster; `sync_attendance_form.py … --region Asia --form
   262383129464057` dry run: no CREATE/UPDATE for this club, `UPDATE club
   picker`, `REPLACE conditions`; then `--apply`. Same for the template
   (`--form 262352490535154`, no region).
5. `form_status.py --form 262383129464057 --roster …` → CLEAN;
   `auto_sync.py` dry run → every region in-sync.
6. Ryan, in the sheet: GLOW → Google Forms → Update form dropdowns from the
   Roster (the Modification form's club list still shows the old name until
   then; it also refreshes itself on the next form submission).

## Risks
- A concurrent form submission appends Roster rows while the tool runs: cells
  are addressed by row number, so the tool re-reads after writing and compares
  every pre-existing row; new rows below are reported and left alone.
- The Jotform question `name` slug keeps the old spelling; nothing keys on it
  (the sync and `form_status` match on `text`).
- A mentor may already have submitted attendance under the old name: those
  submissions and their Salesforce rows keep it; SF Pending is corrected so
  the Salesforce Account is created under the new name.
- Rollback: sheet cells from `data/rename_club/<stamp>/`; question label by
  the same tool with `--old`/`--new` swapped; conditions with
  `restore_conditions.py --form <id> --from conditions-<stamp>.json --apply`.

## Proof
`make check` tail, the dry-run and apply output of the tool (partner and club
names only, no girls' names), the sync dry runs and `form_status … → CLEAN`,
pasted in the conversation and summarised in this file when done.

## Result (executed 2026-09-14)

- `tools/rename_club.py --apply` at 13:43 local: 14 Roster cells (rows
  6383-6396), ClubRegistry row 340 (code kept), SF Pending row 12, 1 Audit row
  (`renameClub`); Asia q446 and template q450 relabelled. Every write verified
  by re-read. Tabs before the change: `data/rename_club/2026-09-14T134346/`;
  form snapshots `backups/<id>/*-2026-09-14T134346.json`.
- Sync (`--roster --region Asia --form 262383129464057 --apply`, then the
  template with no region): each applied only `UPDATE club picker` and
  `REPLACE conditions` (117 / 376 rules). No roster question created or
  updated.
- `form_status.py` → Asia CLEAN (88 rosters, 0 flagged), template CLEAN;
  `auto_sync.py` dry run → all four regions in-sync. Both forms: no question,
  picker option or rule carries the old name; the new name is present.
- `make check` → CHECK PASSED (new `RenameClub` tests included).
- Left for Ryan: GLOW → Google Forms → Update form dropdowns from the Roster
  (or wait for the next form submission).
