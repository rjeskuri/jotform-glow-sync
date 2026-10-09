#!/bin/bash
# PreToolUse hook (Bash): the live-system gate.
#
# Blocks any command that can change a LIVE system - the Jotform forms, the
# master Google Sheet, the deployed Apps Script, Salesforce, or the automatic
# sync's switches on GitHub - unless GLOW_LIVE_OK=1 was exported by the human
# BEFORE launching Claude Code. A command that sets GLOW_LIVE_OK itself is
# always blocked (no self-approval), and so is one that writes a file the next
# launch reads its environment from - ~/.zshrc and the other shell startup files,
# a direnv .envrc, the repository's .env (sourced with set -a): a redirect, tee,
# sed -i or perl -i into one, or launchctl setenv. Fast: a few greps, no network.
# Every decision on a live command is appended to .claude/live_gate.log (gitignored).
#
# Limits: the gate reads the command's text. A write through another program (cp,
# an editor, a script), or a flag assembled at run time, is not seen: it guards
# against mistakes, not against intent.
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
# Salesforce, through sf or the older sfdx: a deploy (a check-only one too) or a
# delete of metadata, data writes, anonymous Apex, the REST API itself, and
# --rehearse (sf_dupes.py's production DML, rolled back).
SF='(^|[^[:alnum:]_.-])sf(dx)?[[:space:]]+'
PATTERN="(--apply|--prune|--rehearse|clasp[[:space:]]+push|clasp:push|sheets_client\.py[[:space:]]+import|api\.jotform\.com|api\.github\.com/repos/[^[:space:]]*/dispatches|apply_changes[[:space:]]*=[[:space:]]*True|values\(\)\.(update|append|clear)|batchUpdate"
PATTERN+="|${SF}project[[:space:]]+deploy[[:space:]]+(start|quick|validate)|${SF}deploy[[:space:]]+metadata|${SF}project[[:space:]]+delete[[:space:]]+source"
PATTERN+="|${SF}data[[:space:]]+(create|update|delete|upsert|import)|${SF}apex[[:space:]]+run"
PATTERN+="|${SF}force:(apex:execute|source:(deploy|delete|push)|mdapi:deploy|data:(record|bulk|tree):)|\.salesforce\.com/services/"
# GitHub: the sync's switches (repository variables and secrets: SF_SYNC, AUTO_SYNC_APPLY),
# the workflow itself, a run that applies (apply given true, from a file, by expansion, or
# inputs as JSON) and a rerun (it repeats the recorded inputs); gh api writes are below.
GH='(^|[^[:alnum:]_.-])gh[[:space:]]+((-R|--repo)[[:space:]=]?[^[:space:]]+[[:space:]]+)?'
APPLY_ON='apply["'\'']?[[:space:]]*[=:][[:space:]]*["'\'']?([Tt][Rr][Uu][Ee]|1|[$@`])'
PATTERN+="|${GH}(variable|secret)[[:space:]]+(set|delete|remove)|${GH}workflow[[:space:]]+(enable|disable)|${GH}run[[:space:]]+rerun"
PATTERN+="|${GH}workflow[[:space:]]+run.*(${APPLY_ON}|--json|=@)|${APPLY_ON}.*${GH}workflow[[:space:]]+run"
# self-approval: the flag in the command, or written where the next launch picks it up
STARTUP='(\.zshrc|\.zprofile|\.zshenv|\.zlogin|\.bashrc|\.bash_profile|\.bash_login|\.profile|\.envrc|\.env)([^[:alnum:]_.-]|$)'
WRITES='(>|tee[[:space:]]|sed[[:space:]][^;&|]*(-[[:alnum:]]*i|--in-place)|perl[[:space:]][^;&|]*-[[:alnum:]]*i)[^;&|]*'
SELF="GLOW_LIVE_OK\\+?=|${WRITES}${STARTUP}|launchctl[[:space:]]+setenv"
PATTERN+="|${SELF})"
# matched on one line: a command continued with \ (gh workflow run x \ -f apply=true) or
# spread over lines is still one command
FLAT=$(printf '%s' "$CMD" | tr '\n\r' '  ')
MATCH=$(printf '%s' "$FLAT" | grep -Eo "$PATTERN" | head -1) || true
# gh api: a write - a method other than GET, or fields / --input, which make it a POST - on
# the Actions API (variables, secrets, workflows, runs) or to a repository dispatch
if [ -z "$MATCH" ] && printf '%s' "$FLAT" | grep -Eq "${GH}api[[:space:]]" \
    && printf '%s' "$FLAT" | grep -Eq '(actions/|/dispatches)' \
    && printf '%s' "$FLAT" | grep -Eiq '(^|[[:space:]])((-X|--method)[[:space:]=]*["'\'']?(POST|PUT|PATCH|DELETE)|-[fF]|--field|--raw-field|--input)'; then
  MATCH="gh api write under actions/ or to dispatches"
fi
# sf api request: any GraphQL call (a mutation writes), and a REST call that writes - a method
# other than GET (the CLI offers GET POST PUT PATCH HEAD DELETE OPTIONS TRACE), a body (-b,
# --body) or a request file (-f, --file: it carries its own method and body). A relative path
# (/services/data/...) does not name the host, so the URL pattern above does not see it.
if [ -z "$MATCH" ] && printf '%s' "$FLAT" | grep -Eq "${SF}api[[:space:]]+request[[:space:]]+graphql"; then
  MATCH="sf api request graphql"
fi
if [ -z "$MATCH" ] && printf '%s' "$FLAT" | grep -Eq "${SF}api[[:space:]]+request[[:space:]]+rest" \
    && printf '%s' "$FLAT" | grep -Eiq '(^|[[:space:]])((-X|--method)[[:space:]=]*["'\'']?(POST|PUT|PATCH|DELETE|HEAD|OPTIONS|TRACE)|-[bf]|--body|--file)'; then
  MATCH="sf api request rest that writes"
fi
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
if [ "${GLOW_LIVE_OK:-}" = "1" ] && ! printf '%s' "$FLAT" | grep -Eq "$SELF"; then
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
