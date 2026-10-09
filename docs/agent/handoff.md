# Handoff — 2026-10-09

## Next steps
- Ryan: set the dashboard's daily refresh. Salesforce → dashboard "Jotform Attendance" → Subscribe → Daily, 05:00 America/Los_Angeles, running as Ryan. This is a UI-only step; it can't be deployed.
- Ryan: Login As one GLOW Standard User, open the dashboard, click through to a report, and check that the totals match yours.
- Confirm BATCH-000500's real session date with "Niñas Emprendedoras y Empoderadas" (stored as 2026-03-09, probably 2026-09-03), then correct the batch and its 14 rows (BACKLOG 60 (7)).
- SF_SYNC one-time setup (RUNBOOK "New clubs' accounts, automatically", steps 1-6). None of it exists yet: no GLOW Sync user, no permission set, no GitHub secrets.
- Merge `wf10/four-issues` (documents the live totals1 dashboard and the processor change), then `wf11/reports-public`. Neither is pushed.

## State (2026-10-09)
- Verified read-only: every report and dashboard figure equals SOQL. Jotform ↔ Salesforce match girl for girl on 612 sessions, 0 unexplained (counts in `data/reconcile_2026-10-09/`).
- Done: the Attendance report and dashboard folders are shared View with All Internal Users. "(test)" is dropped from the labels. Permission set `Attendance_Report_Viewer` is assigned to all 9 GLOW Standard Users, Portal Login included by Ryan's decision. Plan: `docs/plans/2026-10-09-attendance-reports-public.md` (on `wf11/reports-public`).
- Done: ParentId set to Kawempe Youth Center on "Shining Stars (Kawempe Youth Centre)" and "Genious Girls". The Club accounts without a partner are back to the two known ones.
