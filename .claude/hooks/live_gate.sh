#!/bin/bash
# PreToolUse hook (Bash): the live-system gate.
#
# Blocks any command that can change a LIVE system - the Jotform forms, the
# master Google Sheet, or the deployed Apps Script - unless GLOW_LIVE_OK=1 was
# exported by the human BEFORE launching Claude Code. A command that sets
# GLOW_LIVE_OK itself is always blocked (no self-approval). Fast: one grep,
# no network. Every decision is appended to .claude/live_gate.log (gitignored).
set -u
INPUT=$(cat)
if command -v jq >/dev/null 2>&1; then
  CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty')
else
  CMD=$(printf '%s' "$INPUT" | python3 -c 'import json,sys; print((json.load(sys.stdin).get("tool_input") or {}).get("command") or "")')
fi
[ -z "$CMD" ] && exit 0

PATTERN='(--apply|--prune|clasp[[:space:]]+push|clasp:push|sheets_client\.py[[:space:]]+import|GLOW_LIVE_OK=)'
MATCH=$(printf '%s' "$CMD" | grep -Eo "$PATTERN" | head -1) || true
[ -z "$MATCH" ] && exit 0

LOG="${CLAUDE_PROJECT_DIR:-.}/.claude/live_gate.log"
if [ "${GLOW_LIVE_OK:-}" = "1" ] && ! printf '%s' "$CMD" | grep -q 'GLOW_LIVE_OK='; then
  printf '%s ALLOWED %s\n' "$(date '+%F %T')" "$CMD" >> "$LOG"
  exit 0
fi
printf '%s BLOCKED %s\n' "$(date '+%F %T')" "$CMD" >> "$LOG"
cat >&2 <<EOF
BLOCKED by .claude/hooks/live_gate.sh - matched "$MATCH".
This command can change a LIVE system (the Jotform attendance forms, the master
enrollment Google Sheet, or the deployed Apps Script). They went live 2026-09-01.
To proceed: (1) show the dry-run output first, (2) back up (backup_forms.py /
sheets_client.py export-all), (3) get Ryan's explicit go in this conversation,
then EITHER Ryan runs the command himself in a terminal OR Ryan restarts Claude
Code with GLOW_LIVE_OK=1 exported in his shell. Putting GLOW_LIVE_OK= inside the
command does not count. See docs/RUNBOOK.md, "Live gate".
EOF
exit 2
