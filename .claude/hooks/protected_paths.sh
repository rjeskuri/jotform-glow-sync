#!/bin/bash
# PreToolUse hook (Edit|Write|MultiEdit): paths Claude must not write.
#
# data/, backups/ and credentials/ hold minors' names or secrets and are never
# edited by hand; appsscript/Regions.gs is generated; the per-machine Claude
# settings and the live-gate log are not source. Exit 2 blocks the edit and
# shows the reason.
set -u
INPUT=$(cat)
if command -v jq >/dev/null 2>&1; then
  FP=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty')
else
  FP=$(printf '%s' "$INPUT" | python3 -c 'import json,sys; print((json.load(sys.stdin).get("tool_input") or {}).get("file_path") or "")')
fi
[ -z "$FP" ] && exit 0
ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
case "$FP" in
  "$ROOT"/*) REL="${FP#"$ROOT"/}" ;;
  *) REL="$FP" ;;
esac
case "$REL" in
  .env.example|credentials/README.md|credentials/config.example.json) exit 0 ;;
  data/*|backups/*|credentials/*|appsscript/Regions.gs|.claude/settings.local.json|.env|.env.*|.claude/live_gate.log)
    echo "BLOCKED by .claude/hooks/protected_paths.sh: '$REL' holds personal data or secrets, or is generated (Regions.gs comes from tools/derive_partner_regions.py --forms defunct --write). Change the generator or ask Ryan." >&2
    exit 2 ;;
esac
exit 0
