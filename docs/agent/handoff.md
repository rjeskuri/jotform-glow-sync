# Handoff — 2026-10-14 (overnight; landing ~09:30 JST)

## State
- **Harness v2 adopted**: PR #2 (`1e2f769`, the prep inventory `docs/agent/harness-prep.md`, the
  scaffold, `scripts/verify.sh`, `scripts/harness_tests.sh`) and PR #4 (`459451d`, `git commit` /
  `git push` and the board tools allowed). `main` is pushed; the board is this repo's issues.
- **Ryan's decisions, 2026-10-14 ~00:40 JST**: adoption follow-ups on the board; `harness-worklog`
  is the canonical work-log tool (it reproduced every row of `worklog/worklog.csv` byte for byte);
  the work log and this handoff reach `main` through a monthly chore ticket; commit/push allowed
  (done in #4). Then, relayed by the harness session: work the offline tickets overnight, pull
  requests left ready for him to land in the morning.
- **Board**: epic #5 "Offline sweep" (tasks #7 form_status regions, #8 docs describe the ticket
  loop, #9 plans index and templates, #11 doc-refs checks BACKLOG's rules, #12 CLAUDE.md moves to
  ~72 lines, #13 form_status names an uncompared runtime build); epic #6 "Finish the harness v2
  adoption" (#10 retire `tools/worklog.py`, #14 document the monthly chore, blocked by #10; #15
  October chore, `status:blocked` on purpose so dispatch skips it).
- **Overnight (done 17:53 UTC)**: every headless run ended ok; #7–#13 are in review as ready PRs
  #18, #17, #19, #22, #20, #21, #23, CI green, each with a Fable review whose findings were fixed
  and a clean re-review. Pre-land check in a scratch clone: squash-landing all seven in the order
  below is conflict-free and the result ends `VERIFY OK`; no worktree holds `data/` or `backups/`
  files; every branch is pushed and clean; the privacy audit of the combined diff found nothing
  (the home-folder paths in five PR bodies' tracebacks were trimmed; one nit: #18's test rosters
  use surnames like Sample/Mock instead of `make_fixture.py`'s list, precedent on main). Runner: `glow/forms.py` gains `canonical_region` and
  `glow/translation_lookup.py` `READ_BUILDS`, both used only by `tools/form_status.py`; nothing
  `auto_sync.py` runs changes. #14 waits for #10 to close; nothing else is dispatchable.
- Harness-side issues filed by the harness session from this repo's findings: Harness #25
  (work log drops pasted, `!` and slash-command messages), #26 (sessions inside ticket worktrees
  are not counted), #27 (land restores main-checkout files identical to the landed content).
- **Landed 2026-10-14 morning (Ryan's go)**: #17, #18, #23, #19, #20, #21, #22 in that order,
  after the land checks (privacy audit clean, no worktree data, runner unchanged: `--json` output
  is unchanged and the new `! Roster:` line prints in text mode only). #21 got one commit first:
  rule 12 keeps "one record per call". Epic #5 closed; epic #6 1 of 3 (#10 done). `main` at
  `2e031b4`. `tools/worklog.py` is gone: `harness-worklog` only.
- The main checkout is dirty on `worklog/worklog.csv` (the 10-14 row) and this file, by design:
  both go to `main` through #15.

## Next steps
1. #14 (document the monthly chore) is dispatchable now that #10 is closed.
2. Ryan's questions: #12 stops at ~72 lines; go to ~60 by shortening rules 3, 4, 6, 7, 9, 10, 11
   to one line plus a skill pointer? Should `make doc-refs` refuse a new BACKLOG number (> 86)?
   Drop `.env` and `credentials/` from `.worktreeinclude` for dispatched runs (no ticket needs
   them)? Later months' chore tickets under a standing epic? `/harness:handoff` from the main
   checkout only?
3. Daytime BACKLOG candidates (risk or a decision; not dispatched): 48's follow-up (runner),
   62 (runner), 81 (runner's installs), 80 (Python 3.12, needs Homebrew), 78 (`sf_backfill`
   guard), 51, 57, 40 (wording listed for Ryan), and an `auto_sync` ATTENTION for active rows whose
   region matches no form. Close candidates: 2 and 17 (answered), 31 (obsolete), 10 (no red test).
4. #15 at month end: refresh the copy, `cmp` both paths, Ryan restores
   `worklog/worklog.csv docs/agent/handoff.md` in the main checkout by hand, then land.
5. `prep/harness-v2` and its worktree: merged in PR #2 (squash, so `git branch -d` refuses); no
   `data/` or `backups/` files in it. Remove on Ryan's word.
6. Still open from before: the first real Welcome Session batch in Salesforce (`Module_Week__c`
   null, `Success`); the runner's SyncLog rows since 10-13 09:06 UTC; the Africa 38-club
   retirement; the Apps Script deploy; deactivating the U.S clubs; SF_SYNC; BATCH-000500's date.
