#!/bin/bash
# PreToolUse hook (Edit|Write|MultiEdit): paths Claude must not write.
#
# data/, backups/ and credentials/ hold minors' names or secrets and are never
# edited by hand; appsscript/Regions.gs is generated; the per-machine Claude
# settings and the live-gate log are not source; the backup records
# (.claude/live_backups.log, written only by glow/live_backups.py) are what the
# live gate trusts for an automatic go, so an edit of them is a forged record.
# Exit 2 blocks the edit and shows the reason.
#
# The match is on path components, so the same set is protected in every copy
# of the repository (the main checkout, a worktree under .claude/worktrees/, a
# sibling checkout) and for a relative path (data/x, ./data/x, ../data/x): a
# `data`, `backups` or `credentials` directory, a `.env` file. Inside the project
# ($CLAUDE_PROJECT_DIR) only the part below it is read, so a checkout that itself
# lives under such a folder (/Volumes/data/...) stays editable; outside it, the
# whole path. That includes ~/.claude/settings*.json and ~/.claude/hooks/: the
# user-level settings could switch the project's hooks off, so they are as
# protected as the project's own. Case-insensitive, as the Mac's file system is.
# The path as given and the path with its symbolic links resolved (python3's
# realpath, which resolves the part that exists of a file not yet written) are
# both read, against the project dir resolved the same way: either one blocks.
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
collapse() {
  local p="/$1" s="/" ss="//" sds="/./"
  while :; do
    case "$p" in
      *//*) p="${p//$ss/$s}" ;;
      */./*) p="${p//$sds/$s}" ;;
      *) break ;;
    esac
  done
  printf '%s' "$p"
}

# what the rules read of a path: the part below the project dir when the path is in
# it (a relative path is: the working directory is the project's), else all of it
scoped() {   # path root
  local p root
  p=$(collapse "$1")
  root=$(collapse "$2")
  root="${root%/}"
  case "$1" in
    /*) case "$p" in "$root"/*) p="/${p#"$root"/}" ;; esac ;;
  esac
  printf '%s' "$p"
}

protected() {   # a scoped path
  local p="$1" name="${1##*/}"
  shopt -s nocasematch
  case "$p" in
    */data/*|*/backups/*) return 0 ;;
    */credentials/README.md|*/credentials/config.example.json) ;;
    */credentials/*) return 0 ;;
    */appsscript/Regions.gs|*/.claude/settings.json|*/.claude/settings.local.json|*/.claude/live_gate.log|*/.claude/live_backups.log|*/.claude/hooks/*)
      return 0 ;;
  esac
  case "$name" in
    .env.example) return 1 ;;
    .env|.env.*) return 0 ;;
  esac
  return 1
}

BLOCKED=
protected "$(scoped "$FP" "$ROOT")" && BLOCKED=1
if [ -z "$BLOCKED" ] && command -v python3 >/dev/null 2>&1; then
  REAL=$(python3 -c 'import os, sys; print("\n".join(os.path.realpath(a) for a in sys.argv[1:]))' "$FP" "$ROOT")
  RFP="${REAL%$'\n'*}" RROOT="${REAL##*$'\n'}"
  protected "$(scoped "$RFP" "$RROOT")" && BLOCKED=1
fi
[ -z "$BLOCKED" ] && exit 0
echo "BLOCKED by .claude/hooks/protected_paths.sh: '$REL' holds personal data or secrets, is generated (Regions.gs comes from tools/derive_partner_regions.py --write), or is part of the Claude Code guardrails themselves - the gate must not be editable by the thing it gates. Change the generator, or ask Ryan to make guardrail changes himself (or with his explicit go outside this hook)." >&2
exit 2
