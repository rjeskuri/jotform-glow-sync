---
name: check
description: Run the offline feedback loop (make check) and report the result verbatim. Use after any code, test, config or doc change and before saying a task is done.
---

Run `make check` from the repository root (use `CSV=<path to enrollment_2026-08-24.csv>` when the
real export lives outside this checkout, e.g. in a worktree). Paste the last 15 lines. Healthy:
`ALL CHECKS PASSED` three times, `OK` from the Python tests, `gs: … files parse`,
`secrets: clean`, `docs-links: ok`, `fixtures: up to date`, `CHECK PASSED`.

If it fails: fix the code, the doc, or the data — not the check — unless the plan says the check
itself must change (then say so). Re-run until green, then report.
