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
- **`docs/BACKLOG.md`**: keep both sides' dated bullets and the newer `Status:` line; never
  renumber or add an item (new work is a ticket). `make doc-refs` checks the result.
- **`docs/DECISIONS.md`**: keep both sides' sections, in date order.
- **`docs/RUNBOOK.md`, `.claude/skills/*`**: keep both procedures; where they disagree, the newer
  dated decision wins (DECISIONS, the plans' dates) and the older text goes or points to it. Never
  rename a heading: tools and docs quote them (`make doc-refs`).
- **Generated files** are regenerated, never hand-merged: `docs/plans/README.md` (`make
  docs-index`), `test/fixtures/enrollment_sample.csv` and `expected.json` (`make fixtures`).
- **`worklog/worklog.csv`, `docs/agent/handoff.md`**: only the month's work-log chore changes them
  (RUNBOOK "Work log and invoices"). A branch that changes either (a `/harness:handoff` run
  or a hand edit inside its worktree) is reported to Ryan; on his word the branch's copy
  moves to the main checkout and the branch takes `origin/main`'s copy back
  (`git checkout origin/main -- <path>`).

## 2. Privacy
The `privacy-auditor` agent on `origin/main...$B`.

## 3. What the unattended runner does once `main` moves
The land is the rollout. The auto-sync workflow runs `main`'s code only and applies within its
bands, so a form change the sync generates reaches every enabled regional form on the runner's
next run: the next roster change, the morning backstop, or a run from the Actions tab (RUNBOOK
"Automatic sync"; DECISIONS 2026-10-14). If the emergency stop is on (`AUTO_SYNC_APPLY` at `0`,
during a rollback), the next run is a dry run: the land rolls nothing out until the rollback
switches it back to `1`. Read `git diff origin/main...$B -- glow/
tools/auto_sync.py tools/sf_new_clubs.py sync_attendance_form.py .github/workflows/` for: a
switch in `glow/sync.py` (`CONTACT_IDS_FIRST`, `ROSTERS_REQUIRED`, `MODULE_CALC_VALUES`,
`RETIRE_INACTIVE`, …), what a sync plans that it did not before, the bands (`--max-*`), the
Salesforce path (`SF_SYNC`). Tell Ryan in plain words what the next run will apply, on which
forms, and what each region's SyncLog row will say. A change that is not ready for every enabled
regional form does not land yet: it stays on its branch until it is. The runner never syncs the
template or a disabled form: name the steps they take by hand (the template from the ticket
branch before the land, a disabled form from `main` after it). An `appsscript/` change is not
live until `/deploy-appsscript`.

## 4. The worktree's `data/` and `backups/`
Land runs `git worktree remove`, which **deletes gitignored files without asking**, and on
2026-10-09 one worktree held the only copies of 11 files. List what exists nowhere else, by name
only (never open them):
`cd <worktree> && find data backups -type f 2>/dev/null | while read -r f; do cmp -s "$f" "<primary checkout>/$f" || echo "$f"; done`.
Anything listed: ask Ryan, and move it to the same path in the primary checkout (`mv -n`) on his
word.

## 5. The month's work-log chore PR
After the month's last `/harness:worklog` and a final refresh of the PR:
`cmp "<primary checkout>/$f" "<worktree>/$f"` prints nothing for `f` = `worklog/worklog.csv` and
`docs/agent/handoff.md` (anything printed: refresh the PR first). Then `/harness:land`: it restores
the primary checkout's byte-identical copies before the fast-forward, and a copy that differs
blocks the pull ("main not pulled") instead of being lost (RUNBOOK "Work log and invoices").

## Report
The three answers (conflicts resolved and how, the audit, what the next run will apply and on
which forms), any file moved, and the template's or a disabled form's steps still to take. Ryan
lands with `/harness:land`.
