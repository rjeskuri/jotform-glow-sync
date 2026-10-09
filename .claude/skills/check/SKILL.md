---
name: check
description: Run the offline feedback loop (make check) and report the result verbatim. Use after any code, test, config or doc change and before saying a task is done.
---

Run `make check` from the repository root (use `CSV=<path to enrollment_2026-08-24.csv>` when the
real export lives outside this checkout, e.g. in a worktree). New files count only once staged:
the checkers read `git ls-files`. Paste the tail. Healthy, in order: `lint: ok`,
`ALL CHECKS PASSED` four times (one per JS test file), `py: N files parse, N scripts answer
--help`, `Ran N tests … OK`, `gs: 10 files parse, 8 services, 0 unknown calls (…)`,
`secrets: clean (…)`, `docs-links: ok (…)`, `doc-refs: ok (…)`, `docs-index: ok (…)`,
`conflicts: none`, `fixtures: up to date` (after the fixture's deliberate
`! 1 non-empty CSV row(s) had too few columns` line), `CHECK PASSED`.

If it fails: fix the code, the doc, or the data — not the check — unless the plan says the check
itself must change (then say so). A stale `docs-index` is fixed by `make docs-index`; a ruff
finding by the code (`make lint` shows it). Re-run until green, then report.
