---
status: in-progress      # Ryan 2026-10-09: merge wf10+wf11 first, all four phases; one-offs deleted, not archived (the recommended default; Ryan left that question open). Phases 1-4 on wf21/*
backlog: 32, 50, 53
date: 2026-10-09
---
# Repo cleanup: organize, consolidate, lint (no rewrite)

Source: six read-only reviews of the merged tree main + wf10/four-issues + wf11/reports-public
(glow core, Jotform/Sheets tools, Salesforce tools, tests/CI, Apps Script/JS, docs/.claude).
Baseline on that merge: `make check` passes (633 Python tests, 407 JS checks, 8.5 s); `ruff` (repo
config) 2 errors, both from wf10. Nothing in this plan writes to Jotform, the sheet, Salesforce or
GitHub; the Apps Script changes wait for Ryan's `clasp push`.

## Phase 0 - Integrate first (prerequisite)
wf10 (29 commits, ~10k lines) and wf11 are unmerged; a cleanup on either alone conflicts with the
other. In a worktree off `main`:
1. Merge `wf10/four-issues`; fix its two F-errors (`tools/auto_sync.py:79` duplicate import,
   `tools/form_status.py:66` unused `JOTFORM_COL`).
2. Merge `wf11/reports-public`. Conflicts (docs only): BACKLOG 27 = concatenate both sentences;
   RUNBOOK "Attendance dashboard in Salesforce" = 2026-10-09 Access block supersedes 2026-10-06, keep wf10's
   totals1 paragraph, "Total attendance" bullet and Photos bullet; live-systems skill = union of
   both writer lists; worklog.csv = take main's rows, re-run `worklog.py update`.
3. `make check`; fast-forward local `main`. Not pushed (pushing makes wf10's runner code live).
4. Hygiene: delete the 34 branches merged into main + wf10's 4 feeder branches; remove worktrees
   `sdlc-adoption`, `wf11-sf-new-clubs`, `wf10-four-issues`, `~/jotform-glow-sync-wf20`;
   `git worktree prune`; primary checkout back on `main`.

## Phase 1 - Safety fixes (real bugs, small)
Hooks
- `protected_paths.sh` blocks only `$CLAUDE_PROJECT_DIR/data/...`: an edit to `data/`,
  `credentials/`, `.claude/settings.json` from any worktree (or a `./` path) passes (exit 0,
  reproduced). Match path components (`*/data/*`, ...), keep the README/example exceptions.
- `live_gate.sh`: add `gh variable set|secret set`, `gh workflow run ... apply=true`,
  `sf project deploy start|quick`, `sf_dupes.py ... --rehearse` (BACKLOG 53 has the tested
  patterns). Cut false positives (20 of 31 logged blocks were `grep`/`git`/`echo` on docs): exempt a
  command whose first word is read-only ONLY when it has no `;`, `&&`, `||`, `|`, `$(` or backtick.
- `test/hooks_test.sh` (stdin JSON cases for both hooks) wired into `make check`.

Python
- `form_status.py --roster` defaults to the pre-launch `data/roster_build/Roster.csv` (wrong
  counts, or a traceback): make it required (BACKLOG 32).
- Snapshots minted at minute precision (`backup_forms.py`, `disable_form.py`, `switcher_flags.py`,
  `upload_roster.py`) can overwrite the true "before" on a re-run within the minute: one
  second-precision stamp for all (glow/backup.py, Phase 3).
- `add_language.py`, `restore_translations.py` POST a whole language (REPLACES it) without saving
  the store first; the other two writers do. Save first everywhere.
- `restore_conditions.py` is the only writer with no snapshot of its own: take one before the PUT.
- `glow.jotform.Client.url()` does not URL-encode params (two callers pre-encode by hand): encode in
  `url()`, drop the two workarounds in the same commit.
- `switcher_flags.page_flags` ignores curl's exit code (a network failure reads as "0 languages").
- `sf_dupes` `use_folder` refuses `data/...` on a fresh checkout (`within()` with a missing root).
- `sf_new_clubs.py:341` `assert` in a live writer -> refusal; its error-code regex repeats any
  all-caps word into ATTENTION -> the underscore rule `sf_dupes` uses.
- `integration_status.py` is the only tool not under `glow.cli.run` (traceback on a 504).

Apps Script (code + tests now; live only after Ryan's push)
- A1 trigger path: after the Roster write, `review_` and the SF Pending append run unwrapped in
  `handleNewClub_`/`handleRosterChange_` (FormHandlers.gs:711-748, :852-868). If `review_` throws,
  the retry sees no change: the new club's SF Pending row is never written, no Jotform sync request
  is sent, and the mentor is told "already on the roster". Use `tryReview_`; append SF Pending and
  notify before the ReviewQueue write. Test with `sheetWorld`'s `opts.down`.
- Menu `syncFormChoices` without the document lock (can insert a section twice); failure path writes
  the mentor's address into Audit (`sendChangeConfirmation_`); `rebuildRosterFromResponses` one click
  from a post-launch footgun -> YES/NO prompt stating what it does.

## Phase 2 - Check harness and lint
- Tests by discovery: `python3 -m unittest discover -s test -p '*_test.py'` (same 633 tests;
  delete the hand-import block in python_test.py, which every branch edits). JS: loop over
  `test/*_test.js` in Makefile/package.json.
- Split `test/python_test.py` (9.4k lines, 80 commits, edited by every branch) by subject into
  ~11 files + `test/helpers/common.py` (map in the tests review). `forms_logic_test.js` stays one
  file; share its `check()` helper.
- `ruff` in `make check` and CI. Select `E,F,W,B,UP,SIM,PLE,RUF100`; ignore `E501,E731,E741,B905`
  (~83 findings today, 34 auto-fixable; deliberate invisible-character test data written as escapes).
  Not adopted, with reasons recorded in DECISIONS: `ruff format` (42,773-line diff, flattens the
  aligned comments), isort (961 lines; breaks the `# noqa: E402` lines), pyproject/editable install
  (the worktrees share one `.venv` symlink: an editable `glow` would point at one checkout).
- `make check` also fails on merge-conflict markers (it passed with 21 of them in the merge).
- `check_gs.js`: pin the 8 Google services in use (a 9th = new OAuth scope = trigger fails hard,
  rule 11) and fail on a call to an undefined top-level function (dependency-free; ESLint skipped).
- CI: `permissions: contents: read`, install `ruff==0.16.5`. Silence the 7 stderr lines tests leak
  into the healthy tail. `check_py.py` walks `git ls-files` like the other checkers.
- `.githooks/pre-commit` (added-lines secret scan + ruff on staged .py) and `make hooks`; covers
  VS Code / terminal commits the Claude hooks never see. No pre-commit framework.
- clasp scripts refuse to run unless Node 18 (local Node is 26; rule 11 is memory, not a check).

## Phase 3 - Consolidate into glow/ (behavior unchanged)
- `glow/cli.py`: `api_key()` (22 copies, 6 message variants) and `targets(args.form)` (6 copies).
- `glow/sync.py`: public `rule_parts` (9 decoders, 3 exception sets), `club_picker` (7 copies),
  `dropdown_options` used everywhere, one `_roster_rows` reader, qid constants for 17/105/109/19.
  `tools/form_status.py`'s own qid literals and per-tool form tables -> `glow.sync`/`glow.forms`.
- `glow/backup.py`: `snapshot()`, `stamp()`, backup paths (5 tools import them from a root CLI
  today); `backup_forms.py` stays the thin CLI at the root.
- `glow/translations.py`: read/save store, `{n}` expansion, GET-merge-POST-verify (4 copies).
- `glow/jotform.py`: `public_page()` (3 curls), `submissions()` paging (3 copies), `CLOCK`.
- Salesforce: record-type ids and `odd()` out of the finished `sf_club_accounts.py` (the live
  `auto_sync -> sf_new_clubs` path imports a one-off for them); `apex_trim/sf_match` (one name
  comparison, not three), the `--vpn-off` flag/refusal (4 copies), `error_codes()`, the partners
  CSV reader -> `glow/salesforce.py`. Private-file/ledger helpers (3 copies) -> `glow/private_files.py`.
  `sf_backfill.py` stops being an import hub (its dead re-export goes). Generic submission readers
  out of `backfill_resolve.py` -> `glow/submissions.py`. Sheet-cell helpers out of `rename_club.py`
  -> `sheets_client.py`/`glow/text.py`. `auto_sync.key` -> `glow.text.key`.
- Dead code: BACKLOG 50 (retired partner list remnants; keep the refusal), `glow.REPO`,
  `sheets_client.py import` subcommand, Apps Script `FORMS`/`QID`/`SESSION_OVERRIDES`/`getApiKey_`
  /`renameClubInRegistry_`/`DISPATCH_EVENT` (unexecuted; their parity tests go too).
- Apps Script small consolidations: `clubKey_` (11 copies), `reviewTag_` (3), `withDocumentLock_`
  (3), `spreadsheetZone_` reuse, `foldText_` alias. Parity tests for the pairs nothing checks today
  (RESPONSE_COLS, tab names, `similarity_` vs difflib, `foldKey_` vs `name_key`).
- Retire finished one-offs: `needs_attention.py`, `derive_partner_regions.py` (Regions.gs becomes
  hand-kept data), `clone_regional.py` (stale), `sf_club_accounts.py` (+ its test),
  `backfill_feedback_review.py`. `fix_module_values.py` stays until its undo window closes (end of
  October). `tools/` stays flat (moving tools breaks ~300 documented paths for little gain).

## Phase 4 - Docs and skills
- RUNBOOK (3,045 lines, 36 sections, ~600 lines of finished one-time procedures) -> `docs/runbook/`
  by system (index, jotform-forms, clubs, sheet-and-apps-script, salesforce, admin). Every procedure
  gets When / Status / Dry run / Apply / Verify / Rollback; history moves to the plans' Result.
  Fix the stale "live gate" and "Credentials" (no SF rows) sections.
- `docs/plans/README.md` generated from frontmatter (`make docs-index`, checked); status vocabulary
  pinned; 9+ stale statuses fixed. `docs/specs/` retired; intents optional. LAUNCH.md archived.
- BACKLOG: one file per item `docs/backlog/NNN-slug.md` + generated index (rows are 585 chars on
  average and conflicted three times). DECISIONS: two sentences per cell; rejected options in plans.
- CLAUDE.md: add a Salesforce rule (VPN off, connector vs CLI, check-only then quick deploy) and a
  branches/commits rule; move detail into skills. Commits: subject <= 72 chars, body, trailers
  (`Plan:`, `Backlog:`, `Live:`); `.gitmessage` (subjects today average 212 chars, max 1,461).
- Skills: new `salesforce` (model-invocable; absorbs the live-systems SF half), `deploy-appsscript`
  (user-only; scope diff, quiet-moment push, re-auth, missed responses, rollback floors as git tags),
  `integrate` (user-only; merge a worktree branch with the doc-conflict rules, check, prune).
  `jotform-api` (267 lines) -> short SKILL.md + references/. `form-status`/`sync-preview` pass
  `--partners`. `live-systems` writers as a table. Delete the `verifier` agent (= `check` skill +
  harness:reviewer). Worklog/handoff stay with the harness plugin.

## Not in scope (BACKLOG)
Python 3.10 went EOL 2026-10-04 (move to 3.12 is its own change: CI runs the live sync);
`requirements.lock` for the unattended job; Salesforce metadata/Apex into git (`salesforce/`, today
only in gitignored `data/` on one Mac); scoped `GLOW_LIVE_OK` (the gate was open on 10 days);
splitting FormHandlers.gs; `migrateCountryToRegion`/`retireOldEnrollmentForm` removal (needs the
live Audit tab read first).

## Execution
Worktree branch `wf21/cleanup` off the integrated `main`; one commit per phase step; harness:coder
implements, harness:reviewer reviews each phase's diff, `make check` before/after (test count must
stay 633 until tests are added). Nothing pushed, no live command. Ryan afterwards: push `main`,
`clasp push` the Apps Script change at a quiet moment (no new service, so no re-authorization).
