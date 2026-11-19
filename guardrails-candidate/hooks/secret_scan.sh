#!/bin/bash
# PostToolUse hook (Edit|Write|MultiEdit): scan the file just written for
# secrets and personal data, with the same rules `make secrets` and CI use
# (scripts/check_secrets.py). Exit 2 hands the findings back to Claude so it
# removes them before going on.
set -u
INPUT=$(cat)
if command -v jq >/dev/null 2>&1; then
  FP=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty')
else
  FP=$(printf '%s' "$INPUT" | python3 -c 'import json,sys; print((json.load(sys.stdin).get("tool_input") or {}).get("file_path") or "")')
fi
[ -n "$FP" ] && [ -f "$FP" ] || exit 0
ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
PY="$ROOT/.venv/bin/python3"
[ -x "$PY" ] || PY=python3
HITS=$("$PY" "$ROOT/scripts/check_secrets.py" --file "$FP" 2>&1) && exit 0
{
  echo "SECRET or PERSONAL DATA pattern in the file you just wrote - remove it before continuing:"
  echo "$HITS"
} >&2
exit 2
