# Handoff — 2026-10-13 (later)

## State
- **Special Events ("Special Event - Welcome Session") is LIVE on all five forms** (template,
  Africa, Asia, Latin America, U.S disabled), applied by Ryan 2026-10-13; `form_status --rendered`
  CLEAN on every form. Plan `done`, with its Result:
  [2026-10-13-special-events.md](../plans/2026-10-13-special-events.md). Backups of 2026-10-13:
  template `173626`, regionals `175210`-`175213` (`backups/`).
- Ryan checked the stale-session case in a browser on the template (passes); the regional forms
  serve the same runtime script. He declined a test submission.
- `tools/auto_sync.py` dry run with the merged code: Africa, Asia, Latin America `in-sync`, U.S
  `skipped - form DISABLED`.
- **`AUTO_SYNC_APPLY=0` since 08:29 UTC**: roster changes in the sheet reach no form until it is
  `1` again.
- `main` is ahead of `origin/main` (the photo-sublabel Result, the handoffs, the branch, the merge,
  the Result commit): **not pushed**.

## Next steps (Ryan's go for each)
1. **Push `main` first, then `AUTO_SYNC_APPLY=1`** — never the other way round: the runner runs
   `origin/main`, and the old code would put the old rules back on a region at its next roster
   change (the session bridge gone, a session dropdown for the event). Ryan runs
   `! gh variable set AUTO_SYNC_APPLY --body 1` (the live gate blocks it from Claude).
2. Watch the first real Welcome Session batch in Salesforce (read-only SOQL on
   `Attendance_Batch__c` where `Module__c = 'Special Event - Welcome Session'`): `Success`,
   `Module_Week__c` null, rows created. A blank number through the Jotform integration is
   unproven (no test submission). If a Jotform submission with the event has no batch, the
   integration refused the blank: back-fill it and decide the fix with Ryan.
3. Staff tell mentors: the new option; one submission per club per day (a Welcome Session on a
   curriculum day is refused as a duplicate, whichever arrives second).

**Work log — not updated, needs Ryan's decision.** `python3 tools/worklog.py update` exits 1
without writing: the 2026-10-09 auto row has no work in this repo's transcripts (it came from the
home-folder sessions, counted with `--transcripts`). `--drop-stale` only on Ryan's word; or make
the row `manual` by hand, or recount it with `--transcripts <home folder>`. Then `update` logs
2026-10-12 and 2026-10-13. Suggested 2026-10-13 description: "Designed, built and released a
Special Events option on all the attendance forms, starting with Welcome Sessions, so clubs can
record one-off sessions alongside the curriculum; reviewed, tested and checked on every form.
Confirmed the photo upload limit (10 MB, one photo) on every form."

Still open from before: the Africa 38-club retirement (Partners `jotform` = `no`, then the hand
apply), the Apps Script deploy (`/deploy-appsscript`), deactivating the U.S clubs
(`deactivate_clubs.py --region U.S`), the SF_SYNC setup, BATCH-000500's date.
