---
name: land-checks
description: This repository's checks before /harness:land merges a pull request - the doc and generated-file conflict rules, the privacy audit, what the unattended runner will do once main moves, and the worktree's data/ and backups/, which land deletes. Takes the PR's branch (t/<issue>-<slug>).
disable-model-invocation: true
---

# Before `/harness:land` (`/land-checks <branch>`)

`/harness:land` squash-merges the pull request, moves `main`, removes the worktree and deletes the
branch. Here `main` moving is a live change (the runner runs `main`'s code), and a worktree can hold
the only copy of a personal-data file. `B=$ARGUMENTS`; the worktree is `git worktree list`'s line
for `$B`.

## 1. Conflicts with main (in the worktree, on `$B`, never on main)
`git fetch origin && git merge origin/main` when GitHub reports a conflict (GitHub judges against
`origin/main`; local `main` moves only when `harness-pr land` fast-forwards it), then resolve:
- **`docs/BACKLOG.md`**: keep both sides' items and dated bullets; never renumber an item. Two new
  items with one number: the branch's takes the next free number, and every citation of it on
  the branch's side changes with it (`git grep -n "BACKLOG <n>"`).
- **`docs/DECISIONS.md`**: keep both sides' sections, in date order.
- **`docs/RUNBOOK.md`, `.claude/skills/*`**: keep both procedures; where they disagree, the newer
  dated decision wins (DECISIONS, the plans' dates) and the older text goes or points to it. Never
  rename a heading: tools and docs quote them (`make doc-refs`).
- **Generated files** are regenerated, never hand-merged: `docs/plans/README.md` (`make
  docs-index`), `test/fixtures/enrollment_sample.csv` and `expected.json` (`make fixtures`).
- **`worklog/worklog.csv`**: take main's rows (`git checkout main -- worklog/worklog.csv`); hours
  are recomputed in the primary checkout (its transcripts are the project's), never hand-merged.

## 2. Privacy
The `privacy-auditor` agent on `origin/main...$B`.

## 3. What the unattended runner does once `main` moves
The auto-sync workflow runs `main`'s code only and, with `AUTO_SYNC_APPLY=1`, applies within its
bands. Read `git diff origin/main...$B -- glow/ tools/auto_sync.py tools/sf_new_clubs.py
sync_attendance_form.py .github/workflows/` for: a switch in `glow/sync.py` (`CONTACT_IDS_FIRST`,
`ROSTERS_REQUIRED`, `MODULE_CALC_VALUES`, `RETIRE_INACTIVE`, …), what a sync plans that it did not
before, the bands (`--max-*`), the Salesforce path (`SF_SYNC`). Tell Ryan in plain words what the
next run will do differently; a change that must not reach a form unattended waits with
`AUTO_SYNC_APPLY=0` (RUNBOOK "Automatic sync", Switches; RUNBOOK "The names list sent to
Salesforce": the runner runs `main`'s constants). An `appsscript/` change is not live until
`/deploy-appsscript`.

## 4. The worktree's `data/` and `backups/`
Land runs `git worktree remove`, which **deletes gitignored files without asking**, and on
2026-10-09 one worktree held the only copies of 11 files. List what exists nowhere else, by name
only (never open them):
`cd <worktree> && find data backups -type f 2>/dev/null | while read -r f; do cmp -s "$f" "<primary checkout>/$f" || echo "$f"; done`.
Anything listed: ask Ryan, and move it to the same path in the primary checkout (`mv -n`) on his
word.

## Report
The three answers (conflicts resolved and how, the audit, what the runner will do), any file moved,
and whether `AUTO_SYNC_APPLY` must be `0` first. Ryan lands with `/harness:land`.
