# Handoff — 2026-10-09

## State
- The repo cleanup ([plan and Result](../plans/2026-10-09-repo-cleanup.md#result)) is merged into `wf21/cleanup`, with its docs (`wf21/docs2`) and the CLAUDE.md, skills and agents work (`wf21/claude`); the orchestrator merges it into `main` next. Nothing is pushed and no live command was run.
- Local `main` is 37 commits ahead of `origin/main` before the cleanup (wf10, wf11 and the plan); then come the cleanup's commits (79 on `wf21/cleanup`, then the docs and CLAUDE.md branches). `make check`: 661 Python tests, 497 JS checks, `CHECK PASSED`; `make lint`: ok.
- Not live yet: the runner code (wf10's changes, the consolidated tools) goes live when `main` is pushed; the Apps Script changes (the new-club write order, the rebuild's YES/NO, the dropdown update under the lock) when it is `clasp push`ed.
- Earlier today, done: the Attendance report and dashboard folders shared View with All Internal Users, "(test)" dropped from the labels, the permission set `Attendance_Report_Viewer` assigned to the 9 GLOW Standard Users, two partner-less club accounts re-parented ([plan](../plans/2026-10-09-attendance-reports-public.md)).

## Next steps (Ryan)
1. Review and push `main` (the 37 commits plus the cleanup). Pushing makes wf10's runner changes and the consolidated tools live on the next roster change or morning run: run `python3 tools/auto_sync.py` (a dry run) first and expect every region `in-sync`.
2. `clasp push` the Apps Script change at a quiet moment, with `/deploy-appsscript` (`nvm use 18` first). No new Google service, so no re-authorization is expected; then GLOW → Google Forms → "Process any missed form responses" and read its preview.
3. `make hooks` once in the main checkout (the pre-commit hook and the commit message template).
4. Clean up the `.claude/settings.json` allowlist: the `wf21/claude` report lists the entries (one is `Bash(python3 tools/derive_partner_regions.py:*)`, a retired tool).
5. `appsscript/Regions.gs` is hand-kept data now: update its header (it still says "generated … regenerate rather than hand-edit") and the message of `.claude/hooks/protected_paths.sh` (it says Regions.gs comes from `tools/derive_partner_regions.py --write`). Both are protected files.
6. Work log: decide 2026-10-07's hours; count 2026-10-09's sessions started from the home folder (the attendance-reports work and this cleanup) with `python3 tools/worklog.py update --transcripts <folder>` - it reads that folder instead of the project's, and a logged row changes only with `--rewrite-old` (RUNBOOK "Work log and invoices"); or add a `manual` row.
7. One read-only check: `python3 tools/form_status.py --roster data/roster_<date>.csv --form 262352490535154 --rendered` - the public-page fetch now sends a browser user agent; confirm the page it gets is the same (the rendered checks read CLEAN).

Still open from before:
- The dashboard's daily refresh: Salesforce → "Jotform Attendance" → Subscribe → Daily, 05:00 America/Los_Angeles, running as Ryan (UI only).
- Login As one GLOW Standard User, open the dashboard, click through to a report, compare the totals.
- BATCH-000500's real session date with "Niñas Emprendedoras y Empoderadas" (stored 2026-03-09, probably 2026-09-03), then correct the batch and its 14 rows (BACKLOG 60 (7), BACKLOG 79).
- The SF_SYNC setup (RUNBOOK "New clubs' accounts, automatically", steps 1-6): none of it exists yet.
- Optional: delete a `JOTFORM_API_KEY` Script Property in the sheet's script project if one exists - nothing reads it any more.
