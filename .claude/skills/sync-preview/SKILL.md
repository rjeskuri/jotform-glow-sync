---
name: sync-preview
description: Dry-run the Roster → Jotform sync for one region and summarise the planned calls (read-only; never adds --apply). Takes the region (Africa | Asia | Latin America | U.S).
disable-model-invocation: true
---

1. Confirm the key is present without printing it: `[ -n "$JOTFORM_API_KEY" ] && echo set`.
   If not set, stop and ask Ryan to load `.env` (`set -a; source .env; set +a`) — never ask for
   the key itself.
2. Find the newest exports: `ls -t data/roster_*.csv | head -1` and
   `ls -t data/partners_*.csv | head -1`; if one is missing, export it:
   `python3 tools/sheets_client.py export Roster data/roster_$(date +%F).csv`,
   `python3 tools/sheets_client.py export Partners data/partners_$(date +%F).csv`.
3. Look up the form id for `$ARGUMENTS` in `docs/RUNBOOK.md` and run
   `python3 sync_attendance_form.py <roster csv> --roster --partners <partners csv> --region
   "$ARGUMENTS" --form <id>` (without `--partners` the sync cannot tell a retired roster from a
   half-written one).
4. Report: the `Roster:` line, every `CREATE` / `UPDATE` / `DELETE` line, the `~ retired roster` /
   `~ restored roster` lines, the `REPLACE` rule count, and every `!` / `?` warning verbatim (they
   contain club names only). Say whether `tools/auto_sync.py`'s bands would allow it (≤ 5 creates,
   ≤ 20 updates, ≤ 5 rosters retired and ≤ 5 restored, no deletes, no "shares NO names", no "Club
   Name (question 5, what Salesforce reads) changes" — that one is a Salesforce Account rename and
   is only ever applied by hand). A "not added: give it a
   different name" line is a new club refused for its name: say so, it needs a human. An "its
   rule tests '…', which the Club picker does not list" line means the rules are out of step with
   the picker (that roster does not show): the runner raises ATTENTION and the rewrite is applied
   by hand. A "question 18 (Contact_IDs) is not recalculated after the rosters change" line, or
   any `REQUIRED roster '…' (q…: Yes)` line, means the form is not rolled out to the names-list
   rules yet: the runner applies nothing in that region (docs/RUNBOOK.md, "The names list sent to
   Salesforce"); count the `REQUIRED roster` lines instead of listing them.
5. Do not add `--apply`. Applying is Ryan's decision (`.claude/skills/live-systems`).
