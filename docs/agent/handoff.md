# Handoff — 2026-10-13

## State
- **Special Events (first type "Welcome Session") is built, reviewed, NOT merged, NOT live.**
  Plan: [2026-10-13-special-events.md](../plans/2026-10-13-special-events.md) (status
  `in-progress`; Decisions, Build notes, Review fixes, Rollout). Branch `wf22/special-events` in
  the worktree `.claude/worktrees/special-events`: `f8b612e` (the build) + `a5141bc` (the review
  fixes). `make check` in the worktree: `Ran 688 tests … OK`, `CHECK PASSED`. Two reviews (the
  second found the four fixes correct), privacy audit clean; the worktree holds no `data/` or
  `backups/` files.
- Ryan's decisions (2026-10-13): the event is a module option `Special Event - Welcome Session`
  in all three years' module dropdowns, no session dropdown; Salesforce gets `Module__c` = that
  text, `Module_Week__c` blank, `Module_Year__c` the year; no new question, no Salesforce change;
  the one-batch-per-club-and-date rule stays (a same-day event and session: the second is
  refused). Module options are translated in no language (only `sw` has 1 of 18), so the event
  gets no translations.
- What the sync now does: appends the event options to q14 / q92 / q93 (with their
  `calcValues`); one session rule per curriculum module in every year (year 1's single
  `YEAR equals 1` rule goes); a new **session bridge** calculation (q100 = the shown session
  dropdown, hidden fields ignored) placed first in section B. The bridge changes the session copy
  for EVERY submission. The runner holds a region (ATTENTION) on an event-option write and on
  "options present, rules old" (`WEEK_BRIDGE_STALE`).
- Template dry run (read-only, 2026-10-13): three `UPDATE module dropdown … 1 event option(s)
  added` lines, `REPLACE conditions (400 rules)` (394 kept, 6 new, 1 dropped), no roster change,
  plus the expected `WEEK_BRIDGE_STALE` warning before the apply.
- `main` is unchanged at `5cff6f8` (1 commit ahead of origin: the photo-sublabel Result); this
  handoff is uncommitted on `main`.

**Live now: `AUTO_SYNC_APPLY=0`** (Ryan set it himself; read back `0` at 2026-10-13 08:29 UTC).
The runner applies nothing to any region until it is `1` again: roster changes in the sheet wait.
If the rollout is not done soon, set it back to `1` (`main` still has the old code, so that is
safe until the merge).

## Next steps (each live step on Ryan's go; load `/live-systems` first)
1. `AUTO_SYNC_APPLY=0` (the live gate blocks `gh variable set` unless `GLOW_LIVE_OK=1` was
   exported before launch; Ryan can run `! gh variable set AUTO_SYNC_APPLY --body 0`). Then merge
   with `/integrate` (main checkout on `main`), delete the branch and worktree after checking it
   has no `data/` / `backups/` files.
2. Template `262352490535154`: `backup_forms.py --form` → sync dry run (`--roster --club-picker`)
   → go → `--apply` → `form_status.py … --rendered` CLEAN (bridge operands kept, bridge served
   before the session rules) → in a browser, without submitting: an event after a session leaves
   `input_100` empty; back to a module brings the session back; a year change empties it until a
   session shows → one test submission by RUNBOOK "Photos" step 3's recipe (a club + date that
   already has a `Success` batch, plain Account name): the batch is `Failed` "Duplicate" with
   `Module__c` = the event and `Module_Week__c` blank (SOQL read-back, fields only) → delete the
   test submission. If the bridge misbehaves: `restore_conditions.py --from` the snapshot and stop.
3. Africa `262382821971058`, Asia `262383129464057`, Latin America `262383455778067`, U.S
   `262382706852058` (disabled, kept matching): backup, dry run, go, apply, CLEAN. Same day: the
   runner holds each region until its apply.
4. `AUTO_SYNC_APPLY=1`; `python3 tools/auto_sync.py` dry run → every region `in-sync`.
5. Plan status → `done` with a Result section, `make docs-index`; staff tell mentors (the new
   option; one submission per club per day). Push `main` on Ryan's word.

**Work log — not updated, needs Ryan's decision.** `python3 tools/worklog.py update` exits 1
without writing: "these auto rows no longer have any work: 2026-10-09 1.25 h …" (the 10-09 row
came from the sessions started in the home folder, counted with `--transcripts`; this repo's
folder has none of that day's work). `--drop-stale` only on Ryan's word (CLAUDE.md); options:
make the 10-09 row `manual` by hand, or recount it with `--transcripts <home folder>`. Then
`update` logs 2026-10-12 and 2026-10-13 (both sessions' transcripts are in this repo's folder:
Ryan's messages are recognised). Suggested 2026-10-13 description: "Designed and built a Special
Events option for the attendance forms, starting with Welcome Sessions, so clubs can record
one-off sessions alongside the curriculum; it was reviewed and tested and is ready to go live on
approval. Confirmed the photo upload limit (10 MB, one photo) on every form."

Still open from before (see the 2026-10-09 items in git history of this file and the memory):
the Africa 38-club retirement (Partners `jotform` = `no`, then the hand apply), the Apps Script
deploy (`/deploy-appsscript`), deactivating the U.S clubs (`deactivate_clubs.py --region U.S`),
the SF_SYNC setup, BATCH-000500's date.
