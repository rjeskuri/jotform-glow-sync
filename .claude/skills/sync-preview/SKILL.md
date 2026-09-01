---
name: sync-preview
description: Dry-run the Roster → Jotform sync for one region and summarise the planned calls (read-only; never adds --apply). Argument: the region (Africa | Asia | Latin America | U.S).
disable-model-invocation: true
---

1. Confirm the key is present without printing it: `[ -n "$JOTFORM_API_KEY" ] && echo set`.
   If not set, stop and ask Ryan to load `.env` (`set -a; source .env; set +a`) — never ask for
   the key itself.
2. Find the newest Roster export: `ls -t data/roster_*.csv | head -1`; if none, export one:
   `python3 tools/sheets_client.py export Roster data/roster_$(date +%F).csv`.
3. Look up the form id for `$ARGUMENTS` in `docs/RUNBOOK.md` and run
   `python3 sync_attendance_form.py <csv> --roster --region "$ARGUMENTS" --form <id>`.
4. Report: the `Roster:` line, every `CREATE` / `UPDATE` / `DELETE` line, the `REPLACE` rule
   count, and every `!` / `?` warning verbatim (they contain club names only). Say whether
   `tools/auto_sync.py`'s bands would allow it (≤ 5 creates, ≤ 20 updates, no deletes, no
   "shares NO names").
5. Do not add `--apply`. Applying is Ryan's decision (`.claude/skills/live-systems`).
