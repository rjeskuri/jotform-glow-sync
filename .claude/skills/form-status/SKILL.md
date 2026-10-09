---
name: form-status
description: Read-only readiness report of every live attendance form against the newest Roster and Partners exports (rules, integration, languages, club picker, retired rosters, drift). Optional argument: a form id to limit the report.
disable-model-invocation: true
---

1. `[ -n "$JOTFORM_API_KEY" ] && echo set` — stop and ask Ryan to load `.env` if unset.
2. Newest exports: `ls -t data/roster_*.csv | head -1` and `ls -t data/partners_*.csv | head -1`;
   export what is missing or older than today's:
   `python3 tools/sheets_client.py export Roster data/roster_$(date +%F).csv` and
   `python3 tools/sheets_client.py export Partners data/partners_$(date +%F).csv`.
3. `python3 tools/form_status.py --roster <roster csv> --partners <partners csv>` (`--roster` is
   required; `--partners` tells a retired roster from a broken one); add `--form $ARGUMENTS` when
   given.
4. Report per form: `CLEAN` or the problems, `submissions`, `club picker`, `languages`, and the
   `vs Roster` line (missing from form / extra / differs). Quote club names only; never girls'.
