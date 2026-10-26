# Handoff — 2026-10-26, ticket #103 (paused on Ryan's word via session -53)

- **Ticket and branch:** #103, `t/103-show-submission-timing-on-the`, worktree
  `.claude/worktrees/t-103-show-submission-timing-on-the`. Status left `in-progress`.
- **Stage reached:** code (step 4 of `/harness:work`). Tests are done: the test-author's tests at
  `764404b` (`test/session_timing_test.py`, class `DashboardTimingDocs`). Ryan chose (b) on the
  ticket: keep them and go to code. The breaker stage is closed by that answer.
- **Done:** red run recorded (`harness-red status`: assertion, exit 1, 2026-10-26T22:38:47+09:00,
  `scripts/harness_tests.sh test/session_timing_test.py`, current: yes). The fresh retrieve
  `data/sf_session_timing_2026-10-26/dashboard_before/` (worktree only, not committed) was taken
  ~12:45 UTC, after #157 deployed #102's four reports (12:34 UTC, PR #158 still open).
- **Not done:** the coder (Opus xhigh) was stopped before it wrote anything. There is no commit,
  no build, and no `harness-work attempt` recorded for the code stage.
- **Next step:** `/harness:work 103` re-runs the coder. Brief it with Ryan's 2026-10-26 answers
  (the average-delay tile, the 2026-09-01 floor on `Submission_Delay_by_Partner_by_Month`,
  `build/` vs `build_sibling/`). The live report sources are #157's read-back in that
  worktree's `data/sf_session_timing_2026-10-24/after/`. The build goes in the job folder (the
  hook blocks writes under `data/`) and is then copied into
  `data/sf_session_timing_2026-10-26/`. The steps after that: review, PR, then the live rollout
  on Ryan's go.

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
- `main` pushed `8b6a93f..ebffdf4` at 09:03 UTC (CI `Check` success); then `AUTO_SYNC_APPLY=1`
  again (Ryan, read back 09:06 UTC; it was `0` from 08:29). The runner runs the new code: a form
  missing the event option, or with the options but the old rules, is held (ATTENTION), never
  rewritten. **Rollout complete.**

## Next steps
1. Read the first runner run's SyncLog rows after 09:06 UTC: every region `in-sync` (or applied
   roster changes), U.S `skipped`.
2. Watch the first real Welcome Session batch in Salesforce (read-only SOQL on
   `Attendance_Batch__c` where `Module__c = 'Special Event - Welcome Session'`): `Success`,
   `Module_Week__c` null, rows created. A blank number through the Jotform integration is
   unproven (no test submission). If a Jotform submission with the event has no batch, the
   integration refused the blank: back-fill it and decide the fix with Ryan.
3. Staff tell mentors (Ryan): the new option; one submission per club per day (a Welcome Session on a
   curriculum day is refused as a duplicate, whichever arrives second).

**Work log — unblocked 2026-10-13 (Ryan: option 1).** The 2026-10-09 row is `manual`, 2.00 h
(12:47-13:15, 13:57-15:23: the three home-folder GLOW sessions; the other home-folder sessions
of 10-08..10-12 were other projects and are not billed). `update` now runs: 10-07 recounted to
4.50 h (its afternoon was never counted), 10-12 1.50 h, 10-13 logged with written descriptions.
Run `python3 tools/worklog.py update` once more at the end of the session (today's hours grow).

Still open from before: the Africa 38-club retirement (Partners `jotform` = `no`, then the hand
apply), the Apps Script deploy (`/deploy-appsscript`), deactivating the U.S clubs
(`deactivate_clubs.py --region U.S`), the SF_SYNC setup, BATCH-000500's date.
