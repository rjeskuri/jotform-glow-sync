---
name: form-status
description: Read-only readiness report of every live attendance form against the newest Roster export (rules, integration, languages, club picker, drift). Optional argument: a form id to limit the report.
disable-model-invocation: true
---

1. `[ -n "$JOTFORM_API_KEY" ] && echo set` — stop and ask Ryan to load `.env` if unset.
2. Newest export: `ls -t data/roster_*.csv | head -1` (export one with
   `python3 tools/sheets_client.py export Roster data/roster_$(date +%F).csv` if missing).
3. `python3 tools/form_status.py --roster <csv>` (add `--form $ARGUMENTS` when given).
4. Report per form: `CLEAN` or the problems, `submissions`, `club picker`, `languages`, and the
   `vs Roster` line (missing from form / extra / differs). Quote club names only; never girls'.
