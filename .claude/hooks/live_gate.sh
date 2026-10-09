#!/bin/bash
# PreToolUse hook (Bash): the live-system gate.
#
# Blocks any command that can change a LIVE system - the Jotform forms, the
# master Google Sheet, the deployed Apps Script, Salesforce, or the automatic
# sync's switches on GitHub - unless GLOW_LIVE_OK=1 was exported by the human
# BEFORE launching Claude Code. A command that sets GLOW_LIVE_OK itself is
# always blocked (no self-approval). Fast: a few greps, no network. Every
# decision on a live command is appended to .claude/live_gate.log (gitignored).
#
# A read-only command that only mentions a live flag (grep -n -- '--apply'
# docs/RUNBOOK.md) passes: its first word is grep, rg, cat, head, tail, wc or ls,
# or git log|show|diff|grep|blame|status, AND it has no ; & | ` $( <( > or line
# break, so nothing else runs (nor rg --pre / git grep -O, which run a program).
set -u
INPUT=$(cat)
if command -v jq >/dev/null 2>&1; then
  CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty')
else
  CMD=$(printf '%s' "$INPUT" | python3 -c 'import json,sys; print((json.load(sys.stdin).get("tool_input") or {}).get("command") or "")')
fi
[ -z "$CMD" ] && exit 0

# Tool flags AND the raw API shapes the tools wrap - a direct curl PUT to
# Jotform or a python snippet with apply_changes=True is just as live a write.
# Salesforce: a deploy (a check-only one too), data writes, anonymous Apex, and
# sf_dupes.py --rehearse (production DML, rolled back). GitHub: the repository
# variables and secrets (SF_SYNC, AUTO_SYNC_APPLY) and an applying workflow run.
SF='(^|[^[:alnum:]_.-])sf[[:space:]]+'
GH='(^|[^[:alnum:]_.-])gh[[:space:]]+((-R|--repo)[[:space:]=]?[^[:space:]]+[[:space:]]+)?'
APPLY_TRUE='apply["'\'']?[[:space:]]*[=:][[:space:]]*["'\'']?[Tt][Rr][Uu][Ee]'
PATTERN="(--apply|--prune|clasp[[:space:]]+push|clasp:push|sheets_client\.py[[:space:]]+import|GLOW_LIVE_OK\+?=|api\.jotform\.com|api\.github\.com/repos/[^[:space:]]*/dispatches|apply_changes[[:space:]]*=[[:space:]]*True|values\(\)\.(update|append|clear)|batchUpdate"
PATTERN+="|${SF}project[[:space:]]+deploy[[:space:]]+(start|quick|validate)|${SF}data[[:space:]]+(create|update|delete|upsert|import)|${SF}apex[[:space:]]+run|sf_dupes\.py.*--rehearse"
PATTERN+="|${GH}(variable|secret)[[:space:]]+set|${GH}workflow[[:space:]]+run.*${APPLY_TRUE}|${APPLY_TRUE}.*${GH}workflow[[:space:]]+run)"
# matched on one line: a command continued with \ (gh workflow run x \ -f apply=true) or
# spread over lines is still one command
MATCH=$(printf '%s' "$CMD" | tr '\n\r' '  ' | grep -Eo "$PATTERN" | head -1) || true
[ -z "$MATCH" ] && exit 0

# read-only and alone: a live flag it mentions is text, not an action
read_only() {
  case "$CMD" in
    *';'* | *'&'* | *'|'* | *'`'* | *'$('* | *'<('* | *'>'* | *$'\n'* | *$'\r'*) return 1 ;;
  esac
  local first second _
  read -r first second _ <<<"$CMD"
  case "$first" in
    grep | head | tail | cat | wc | ls) return 0 ;;
    rg) ! printf '%s' "$CMD" | grep -q -- '--pre' ;;              # --pre runs a program per file
    git)
      case "$second" in
        log | show | diff | blame | status) return 0 ;;
        grep) ! printf '%s' "$CMD" | grep -Eq -- '-[^[:space:]]*O|--o' ;;   # -O / --open-files-in-pager
        *) return 1 ;;
      esac ;;
    *) return 1 ;;
  esac
}
read_only && exit 0

LOG="${CLAUDE_PROJECT_DIR:-.}/.claude/live_gate.log"
if [ "${GLOW_LIVE_OK:-}" = "1" ] && ! printf '%s' "$CMD" | grep -Eq 'GLOW_LIVE_OK\+?='; then
  printf '%s ALLOWED %s\n' "$(date '+%F %T')" "$CMD" >> "$LOG"
  exit 0
fi
printf '%s BLOCKED %s\n' "$(date '+%F %T')" "$CMD" >> "$LOG"
cat >&2 <<EOF
BLOCKED by .claude/hooks/live_gate.sh - matched "$MATCH".
This command can change a LIVE system (the Jotform attendance forms, the master
enrollment Google Sheet, the deployed Apps Script, Salesforce, or the automatic
sync's switches on GitHub). They went live 2026-09-01.
To proceed: (1) show the dry-run output first, (2) back up (backup_forms.py /
sheets_client.py export-all), (3) get Ryan's explicit go in this conversation,
then EITHER Ryan runs the command himself in a terminal OR Ryan restarts Claude
Code with GLOW_LIVE_OK=1 exported in his shell. Putting GLOW_LIVE_OK= inside the
command does not count. Direct API access (curl to api.jotform.com, Sheets write
snippets, GitHub dispatches) is gated exactly like the tool flags - use the repo
tools and their dry runs. See docs/RUNBOOK.md, "Live gate".
EOF
exit 2
