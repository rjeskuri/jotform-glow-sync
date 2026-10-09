---
name: integrate
description: Merge a worktree branch into main - what both sides changed, the doc conflict rules, make check, the privacy audit, what the unattended runner will do once main is pushed, then the worktree and branch removed. Argument: the branch (wf<N>/<slug> or fix/<slug>).
disable-model-invocation: true
---

# Integrate a branch into main (`/integrate <branch>`)

From the primary checkout, on `main`, with `git status --short` empty. `B=$ARGUMENTS`.

## 1. Scope
- `BASE=$(git merge-base main $B)`; `git log --oneline main..$B` (what it brings) and
  `git log --oneline $BASE..main` (what main gained meanwhile).
- Files both sides changed, where conflicts come from:
  `comm -12 <(git diff --name-only $BASE main | sort) <(git diff --name-only $BASE $B | sort)`.
- The plan it implements (`Plan:` trailers, `docs/plans/`) and its Proof.

## 2. Merge (never rebase shared history)
`git merge --no-ff --no-commit $B`, then resolve:
- **`docs/BACKLOG.md`**: keep both sides' items and dated bullets; never renumber an item. Two new
  items with one number: the branch's takes the next free number, and every citation of it on
  the branch's side changes with it (`git grep -n "BACKLOG <n>"`).
- **`docs/DECISIONS.md`**: keep both sides' sections, in date order.
- **`docs/RUNBOOK.md`, `.claude/skills/*`**: keep both procedures; where they disagree, the newer
  dated decision wins (DECISIONS, the plans' dates) and the older text goes or points to it. Never
  rename a heading: tools and docs quote them (`make doc-refs`).
- **Generated files** are regenerated, never hand-merged: `docs/plans/README.md` (`make
  docs-index`), `test/fixtures/enrollment_sample.csv` and `expected.json` (`make fixtures`).
- **`worklog/worklog.csv`**: take main's rows, conflicted or not (`git checkout HEAD -- worklog/worklog.csv`), then
  recompute here, in the primary checkout (its transcripts are the project's):
  `python3 tools/worklog.py update`. Never hand-merge hours.
- Code: understand both sides; both sides' tests must pass.

## 3. Check
- `make check` (it fails on a leftover conflict marker: the `conflicts:` line) and `make lint`;
  paste the tail.
- The `privacy-auditor` agent on `main...$B`.
- **What the unattended runner does once `main` is pushed.** The auto-sync workflow runs `main`'s
  code only and, with `AUTO_SYNC_APPLY=1`, applies within its bands. Read
  `git diff $BASE $B -- glow/ tools/auto_sync.py tools/sf_new_clubs.py sync_attendance_form.py
  .github/workflows/` for: a switch in `glow/sync.py` (`CONTACT_IDS_FIRST`, `ROSTERS_REQUIRED`,
  `MODULE_CALC_VALUES`, `RETIRE_INACTIVE`, …), what a sync plans that it did not before, the
  bands (`--max-*`), the Salesforce path (`SF_SYNC`). Tell Ryan in plain words what the next run
  will do differently; a change that must not reach a form unattended waits with
  `AUTO_SYNC_APPLY=0` (RUNBOOK "Automatic sync", Switches; RUNBOOK "The names list sent to
  Salesforce": the runner runs `main`'s constants). An `appsscript/` change is not live until
  `/deploy-appsscript`.

## 4. Commit
`git commit` with a short subject (`Merge <branch>: <what it brings>`, ≤ 72 characters), a body
(what changed for the runner, conflicts resolved and how) and the trailers (`Plan:`, `Backlog:`,
`Live: none`).

## 5. Clean up
- The worktree: `git worktree list` gives its path. **`git worktree remove` deletes its gitignored
  files without asking** (`data/`, `backups/`), and on 2026-10-09 one worktree held the only copies
  of 11 files. First list what exists nowhere else, by name only (never open them):
  `cd <worktree> && find data backups -type f 2>/dev/null | while read -r f; do cmp -s "$f" "<primary checkout>/$f" || echo "$f"; done`.
  Anything listed: ask Ryan, and move it to the same path in the primary checkout (`mv -n`) on his
  word. Then `git worktree remove <path>` and `git worktree prune`.
- `git branch -d $B` (it refuses an unmerged branch: never `-D` without Ryan's word).
- `git branch --merged main`: list the other merged branches for Ryan; delete on his word.

## Never
Push without Ryan's go: pushing `main` makes the runner run the new code. Rebase or force anything
that is shared. Remove a worktree before the step-5 check.
