# Handoff — 2026-10-14 (overnight)

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
- **Overnight**: a dispatch loop (session `jotform-glow-sync-be`, scratchpad `dispatch_loop.sh`)
  runs `harness-work runs --sweep` and `harness-work dispatch --max 3` every 20 min; #7, #8, #9
  launched headless at 16:12 UTC. Runs: `harness-work runs`; logs `~/.claude/harness/runs/`.
- Harness-side issues filed by the harness session from this repo's findings: Harness #25
  (work log drops pasted, `!` and slash-command messages), #26 (sessions inside ticket worktrees
  are not counted), #27 (land restores main-checkout files identical to the landed content).
- The main checkout is dirty on `worklog/worklog.csv` (the 10-14 row) and this file, by design:
  both go to `main` through #15.

## Next steps
1. Morning: `harness-board board`; review and land the ready PRs (`/land-checks <branch>`, then
   `/harness:land`). Land #7 before #13 and #9 before #11 (shared files); #10 before #14 runs.
   A no-tests ticket (#8, #12) that stalled in needs-input: run it interactively, do not redispatch.
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
