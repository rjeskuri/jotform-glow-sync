# Harness v2 adoption — what this repo keeps, removes, replaces

Prepared 2026-10-13 on `prep/harness-v2`, against the harness source at
`~/portfolio_projects/harness/plugins/harness` (plugin `0.2.0`). **The installed plugin is still
`0.1.0`**: until v2 is installed, nothing in its column is active here, so merge this branch after
installing v2, never before (it removes `/check` and `/integrate`).

Rule applied: domain rules (Jotform, the sheet, Apps Script, Salesforce, live-write gates, minors'
data, invoicing) stay; only process rules the harness duplicates go.

## Hooks, settings, scripts

| Item | Harness v2 counterpart | Decision | Reasoning |
|---|---|---|---|
| `.claude/hooks/live_gate.sh` (PreToolUse Bash) | none (`branch_guard` judges git and main only) | keep | Gates writes to the live forms, sheet, Apps Script, Salesforce and the runner's GitHub switches; the harness knows none of these commands. |
| `.claude/hooks/protected_paths.sh` (PreToolUse Edit\|Write\|MultiEdit) | `branch_guard` | keep | Blocks `data/`, `backups/`, `credentials/`, `.env`, generated `Regions.gs` and the guardrails on every branch; `branch_guard` explicitly *allows* gitignored paths, which are exactly these. |
| `.claude/hooks/secret_scan.sh` (PostToolUse Edit\|Write\|MultiEdit) | `after_edit.py` secret scan | keep | Ours also catches personal data, sheet/script ids and service-account fields (the rules `make secrets`, pre-commit and CI use); the harness scan knows provider key formats only. Both run; the overlap is harmless. |
| `scripts/check_secrets.py` (called by the hook above) | — | keep | Shared with `make secrets`, `.githooks/pre-commit`, CI and `privacy-auditor`. |
| `.claude/settings.json` permissions | template `settings.json` | keep | The deny rules (`.env`, credentials, `settings.local.json`) and the asks (`Read(data/**)`, clasp, `git commit`/`push`) are this project's; see "Before you adopt" 5. |
| `.claude/settings.local.json` | — | keep | Per machine, gitignored, a permission allow-list only (no hooks); not on the branch. Read for key names and rule counts only. |
| `.claude/live_gate.log` | — | keep | Gitignored log of `live_gate.sh`. |
| Stop hook | `verify_on_stop.py` | none here | The project has no Stop hook, so the harness's runs; it does nothing until `CLAUDE_VERIFY_CMD` is set ("Before you adopt" 2). |
| SessionStart hook | `session_brief.py` | none here | The project has no SessionStart hook, so the harness brief runs; it already reads `docs/agent/handoff.md`. |
| Notification hook | `notify.py` | none here | Harness notifications run unchanged. |
| `.claude/rules/`, `.claude/commands/` | — | none here | Neither exists. |

## Skills and agents

| Item | Harness v2 counterpart | Decision | Reasoning |
|---|---|---|---|
| `.claude/skills/check` | verify on stop + CI (`check.yml`) + the global "show the evidence" and "never loosen a test" | **removed** (replace) | Its only job was "run `make check` before done"; its `CSV=` advice was stale (nothing reads `CSV`). |
| `.claude/skills/integrate` | `/harness:land` (squash merge, worktree and branch removed, main fast-forwarded) | **replaced** by `land-checks` | A local `git merge` on main is refused by `branch_guard`; the domain steps (doc-conflict rules, generated files, worklog rows, privacy audit, the runner's next run, the worktree's `data/`/`backups/`) moved verbatim to `.claude/skills/land-checks`. |
| `.claude/skills/child-privacy` | — | keep | Minors' data policy. |
| `.claude/skills/deploy-appsscript` | — | keep | Apps Script deploys, OAuth scopes, rollback floors. |
| `.claude/skills/form-status` | — | keep | Read-only live form report. |
| `.claude/skills/jotform-api` (+ 4 references) | — | keep | Verified Jotform semantics. |
| `.claude/skills/live-systems` | — | keep | Every live writer, its backup and rollback. |
| `.claude/skills/salesforce` | — | keep | Salesforce read/write paths and gates. |
| `.claude/skills/sync-preview` | — | keep | Dry-run summary per region. |
| `.claude/agents/privacy-auditor` | `harness:reviewer` (general review) | keep | Scans for minors' names, mentor e-mails and ids, which the reviewer does not; its line 7 still names `/integrate` (left as is: a keep item). |
| `.githooks/pre-commit`, `.gitmessage` (`make hooks`) | — | keep | Git-level scan of added lines and the commit template. |
| `REVIEW.md` | `harness:reviewer` | keep | The domain review passes (live-system safety, privacy, parity); the reviewer sees them only through `CLAUDE.md`'s pointer, which stays. |

## CLAUDE.md process instructions

| Instruction | Harness v2 counterpart | Decision | Reasoning |
|---|---|---|---|
| "Commands (run before saying done; paste the tail; fix the code, not the check)" and `make check`'s healthy-tail list | verify on stop; global "show the evidence", "never loosen a test" | **replaced** | Header shortened; the tail list condensed to "ends `CHECK PASSED`" (the hook judges the exit status). |
| Once per clone `make venv`, `make hooks`; `make docs-index` | — | keep | Project setup and tooling. |
| Dry run by default, back up, verify after | — | keep | The live-write ritual. |
| `print()`, argparse, standard library | — | keep | Code convention. |
| Fictional names; girls' names never in logs | — | keep | Privacy. |
| "Beyond a one-line fix: a plan in `docs/plans/` first; an intent is optional" | `/harness:plan` (request, outline, definition of done, tests) | **replaced** | New work is a ticket; a live rollout still keeps a `docs/plans/` file, since Rollout, Rollback and Result have no place in the ticket. |
| A decision: a dated section in `docs/DECISIONS.md` | — | keep | Domain record; the board has none. |
| BACKLOG: a new item takes the next free number | the board | **replaced** | New work is a ticket; existing items keep their numbers (283 references checked by `doc-refs`). |
| Review against `REVIEW.md` | `harness:reviewer` | keep | See `REVIEW.md` above. |
| Commits: ≤ 72 characters, `area:`, body, `Plan:`/`Backlog:`/`Live:` trailers | — | keep | `Live:` is the record of live writes; see "Before you adopt" 6. |
| Branches: `wf<N>/<slug>` worktrees, primary on main, `/integrate`, delete branch and worktree | `branch_guard`, `harness-work start` (`t/<issue>-<slug>` in `.claude/worktrees/`), `/harness:land` | **replaced** | Only the `data/`/`backups/` rescue is domain: one line pointing at `/land-checks`. |
| Work log: `/harness:worklog` every session, 1-3 client-facing sentences, never edit `auto` hours | global CLAUDE.md, `/harness:worklog` skill | **removed** | Both say the same. Kept: `--drop-stale`/`--rewrite-old` only on Ryan's word, the home-folder `--transcripts` lesson, the RUNBOOK pointer. |
| Things Claude gets wrong 1–12 | — | keep | All domain. Rule 2 (no key on a command line) overlaps the global rule but stays: it records the leak, and the list is cited by number (rules 1, 3, 5, 9, 10, 11 in RUNBOOK, BACKLOG, skills, `RosterOps.gs`), so removing it would renumber the rest. |

There are no tests-first, session-brief or notification instructions in `CLAUDE.md` to remove.

## Before you adopt (found, not changed here)

1. **Install v2 first** (above). The installed cache is `0.1.0`: no `branch_guard`, `tests_first`,
   read-only guard, `/harness:plan|work|land`.
2. **`CLAUDE_VERIFY_CMD`**: add `"env": { "CLAUDE_VERIFY_CMD": "make check" }` to
   `.claude/settings.json`. The file is guarded by `protected_paths.sh`, so this is your edit.
   `make check` took 17 s in a fresh worktree with no `.venv` (system ruff), well inside the 300 s
   default.
3. **`HARNESS_TEST_CMD`**: `harness-red`'s detected `python3 -m unittest test/x_test.py` fails here
   (`ModuleNotFoundError: No module named 'test.x_test'`, the stdlib `test` package wins; `test/`
   has no `__init__.py`), and `npm test -- <file>` runs `make test`. Every red proof would be an
   import error. This command ran `special_events_test.py` (19 tests OK) and `dispatch_test.js`
   (ALL CHECKS PASSED) here, not yet through `harness-red`:
   `for f in {files}; do case "$f" in *.py) python3 -m unittest discover -s test -p "$(basename "$f")" ;; *.js) node "$f" ;; esac || exit 1; done`
   Also `settings.json` `env`: your edit.
4. **The worklog on main**: `branch_guard` refuses `git commit` on main, and on a ticket branch
   `tests_first` treats `worklog/worklog.csv` as source (`*.csv` is not exempt). Today's update
   and commit on main stops working, and so does committing `docs/agent/handoff.md` there (the edit
   is allowed, the commit is not). Decide where those commits go (a chore branch per month, or
   `worklog/**` in `HARNESS_SOURCE_EXEMPT`).
5. **`ask` on `git commit`/`git push`** in `settings.json`: the coder and headless dispatched
   sessions commit and push `t/*` branches; an ask stops a headless run. Your call, your edit.
6. **Squash merges** take the PR title as the subject: put `Plan:`/`Backlog:`/`Live:` in the PR
   description so they reach `main`.
7. **Two worklog tools**: `/harness:worklog` runs `harness-worklog`; the RUNBOOK documents
   `tools/worklog.py`. Same CSV and, by their docstrings, the same rules; not compared on this
   repo's file. Compare one `update` before relying on it.
8. **CLAUDE.md is 84 lines**, not about 60. What is left is domain. Reaching 60 means moving keep
   content (the three read-only tool commands into `form-status`/`sync-preview`, rules 9 and 11
   into `jotform-api`/`deploy-appsscript`); the numbered rules are cited elsewhere, so a move has
   to keep the numbers. Not done: your call.
9. Once you accept this, record the adoption as a dated section in `docs/DECISIONS.md`.
