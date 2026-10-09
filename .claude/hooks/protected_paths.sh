#!/bin/bash
# PreToolUse hook (Edit|Write|MultiEdit): paths Claude must not write.
#
# data/, backups/ and credentials/ hold minors' names or secrets and are never
# edited by hand; appsscript/Regions.gs is generated; the per-machine Claude
# settings and the live-gate log are not source. Exit 2 blocks the edit and
# shows the reason.
#
# The match is on path components, not on a prefix of $CLAUDE_PROJECT_DIR, so the
# same set is protected in every copy of the repository (the main checkout, a
# worktree under .claude/worktrees/, a sibling checkout) and for a relative path
# (data/x, ./data/x, ../data/x): any `data`, `backups` or `credentials` directory
# in the path, any `.env` file. Case-insensitive, as the Mac's file system is.
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

# "/" + the path with every // and /./ collapsed: each component reads "/name/"
# (the patterns are variables: bash 3.2 keeps a backslash-escaped / in a replacement)
P="/$FP" S="/" SS="//" SDS="/./"
while :; do
  case "$P" in
    *//*) P="${P//$SS/$S}" ;;
    */./*) P="${P//$SDS/$S}" ;;
    *) break ;;
  esac
done
NAME="${P##*/}"

shopt -s nocasematch
BLOCKED=
case "$P" in
  */data/*|*/backups/*) BLOCKED=1 ;;
  */credentials/README.md|*/credentials/config.example.json) ;;
  */credentials/*) BLOCKED=1 ;;
  */appsscript/Regions.gs|*/.claude/settings.json|*/.claude/settings.local.json|*/.claude/live_gate.log|*/.claude/hooks/*)
    BLOCKED=1 ;;
esac
case "$NAME" in
  .env.example) ;;
  .env|.env.*) BLOCKED=1 ;;
esac
[ -z "$BLOCKED" ] && exit 0
echo "BLOCKED by .claude/hooks/protected_paths.sh: '$REL' holds personal data or secrets, is generated (Regions.gs comes from tools/derive_partner_regions.py --write), or is part of the Claude Code guardrails themselves - the gate must not be editable by the thing it gates. Change the generator, or ask Ryan to make guardrail changes himself (or with his explicit go outside this hook)." >&2
exit 2
