#!/bin/bash
# PreToolUse hook (Bash): the live-system gate.
#
# A command that can change a LIVE system - the Jotform forms, the master Google
# Sheet, the deployed Apps Script, Salesforce, or the automatic sync's switches
# on GitHub - is put to Ryan as an approval prompt in the session: an "ask"
# decision on stdout, and his answer to that prompt is the go. Nothing
# pre-approves it. Since 2026-10-14 GLOW_LIVE_OK grants nothing (a session-wide
# approval stayed open for 10 days, and a dispatched run inherits the
# environment), and the hook never answers "allow". It refuses outright (a "deny"
# decision), whatever the mode:
#   - a command that approves itself: one that sets GLOW_LIVE_OK, or writes a file
#     the next launch reads its environment from - ~/.zshrc and the other shell
#     startup files, a direnv .envrc, the repository's .env (sourced with set -a):
#     a redirect, tee, sed -i or perl -i into one, or launchctl setenv;
#   - a subagent (agent_id or agent_type in the input): a live write never comes
#     from one; the main session asks Ryan;
#   - a session that cannot show him the prompt: permission_mode other than
#     exactly default, acceptEdits, auto or plan - so bypassPermissions, dontAsk,
#     a missing or an unknown value (a headless or dispatched run).
# Fast: a few greps, no network. Every decision on a live command is appended to
# .claude/live_gate.log (gitignored), with the mode it was taken in.
#
# Limits: the gate reads the command's text, never its shell words. A write through
# another program (cp, an editor, a script), or a flag assembled at run time, is not
# seen: it guards against mistakes, not against intent. Text that only names a live
# command (a commit message, a PR body) asks too, unless it is read-only and alone.
#
# A read-only command that only mentions a live flag (grep -n -- '--apply'
# docs/RUNBOOK.md) passes: its first word is grep, rg, cat, head, tail, wc or ls,
# or git log|show|diff|grep|blame|status, AND it has no ; & | ` $( <( > or line
# break, so nothing else runs (nor rg --pre / git grep -O, which run a program).
set -u
INPUT=$(cat)
# three fields from the input: the permission mode as JSON text (so "default" stays
# apart from a missing, numeric or oddly spelt value), whether an agent is named, then
# the command. Unreadable input gives no fields, hence no command and no decision.
if command -v jq >/dev/null 2>&1; then
  FIELDS=$(printf '%s' "$INPUT" | jq -r '[(.permission_mode | @json), ((has("agent_id") or has("agent_type")) | tostring), (.tool_input.command | if type == "string" then . else "" end)] | join("\n")')
else
  FIELDS=$(printf '%s' "$INPUT" | python3 -c '
import json, sys
d = json.load(sys.stdin)
mode = json.dumps(d.get("permission_mode"))
agent = "true" if ("agent_id" in d or "agent_type" in d) else "false"
cmd = (d.get("tool_input") or {}).get("command")
print(mode)
print(agent)
print(cmd if isinstance(cmd, str) else "", end="")')
fi
MODE=${FIELDS%%$'\n'*}
REST=${FIELDS#*$'\n'}
case "$REST" in
  *$'\n'*) AGENT=${REST%%$'\n'*}; CMD=${REST#*$'\n'} ;;
  *) AGENT=$REST; CMD= ;;
esac
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
# inputs as JSON) and a rerun (it repeats the recorded inputs); gh api is below.
GH='(^|[^[:alnum:]_.-])gh[[:space:]]+((-R|--repo)[[:space:]=]?[^[:space:]]+[[:space:]]+)?'
APPLY_ON='apply["'\'']?[[:space:]]*[=:][[:space:]]*["'\'']?([Tt][Rr][Uu][Ee]|1|[$@`])'
PATTERN+="|${GH}(variable|secret)[[:space:]]+(set|delete|remove)|${GH}workflow[[:space:]]+(enable|disable)|${GH}run[[:space:]]+rerun"
PATTERN+="|${GH}workflow[[:space:]]+run.*(${APPLY_ON}|--json|=@)|${APPLY_ON}.*${GH}workflow[[:space:]]+run"
# self-approval: the flag in the command, or written where the next launch picks it up
STARTUP='(\.zshrc|\.zprofile|\.zshenv|\.zlogin|\.bashrc|\.bash_profile|\.bash_login|\.profile|\.envrc|\.env)([^[:alnum:]_.-]|$)'
WRITES='(>|tee[[:space:]]|sed[[:space:]][^;&|]*(-[[:alnum:]]*i|--in-place)|perl[[:space:]][^;&|]*-[[:alnum:]]*i)[^;&|]*'
SELF="GLOW_LIVE_OK\\+?=|${WRITES}${STARTUP}|launchctl[[:space:]]+setenv"
PATTERN+="|${SELF})"
# Prompt, don't parse (Ryan, 2026-10-14): the command is matched as text, never read as
# shell words - a reader fails open on every gap between it and the shell, a text pattern
# fails closed. Every pattern is tried, in any case, on the command on one line (a command
# continued with \ or spread over lines is still one command) and on a copy with the quote
# and backslash characters removed (gh 'workflow' run, g""h, var\iable, --ap""ply).
FLAT=$(printf '%s' "$CMD" | tr '\n\r' '  ')
BARE=$(printf '%s' "$FLAT" | tr -d '\\"'"'")
TEXTS=$FLAT$'\n'$BARE
has() { printf '%s\n' "$TEXTS" | grep -Eiq -e "$1"; }
first() { printf '%s\n' "$TEXTS" | grep -Eio -e "$1" | head -1; }
MATCH=$(first "$PATTERN") || true
# gh api: a gh word (any case, a path ending in /gh, =gh) and the word api, with actions/,
# dispatches or graphql anywhere in the command: the Actions API (the sync's variables,
# secrets, workflows and runs), a repository dispatch, GraphQL (a mutation can hide in
# -F query=@file). Live whatever the method - a read of them asks too. Every other gh api
# call (issues, comments, labels, the harness's resume reads) is ungated, as before 2026-10-14,
# and so is a message that mentions gh api without those words.
if [ -z "$MATCH" ] && has '(^|[^[:alnum:]_.-])gh([^[:alnum:]_.-]|$)' && has '(^|[^[:alnum:]_])api([^[:alnum:]_]|$)'; then
  ON=$(first 'actions/|dispatches|graphql' | tr '[:upper:]' '[:lower:]')
  [ -n "$ON" ] && MATCH="gh api on $ON"
fi
# sf api request: any GraphQL call (a mutation writes), and a REST call that writes - a method
# other than GET (the CLI offers GET POST PUT PATCH HEAD DELETE OPTIONS TRACE), a body (-b,
# --body) or a request file (-f, --file: it carries its own method and body). A relative path
# (/services/data/...) does not name the host, so the URL pattern above does not see it.
if [ -z "$MATCH" ] && has "${SF}api[[:space:]]+request[[:space:]]+graphql"; then
  MATCH="sf api request graphql"
fi
if [ -z "$MATCH" ] && has "${SF}api[[:space:]]+request[[:space:]]+rest" \
    && has '(^|[[:space:]])((-X|--method)[[:space:]=]*["'\'']?(POST|PUT|PATCH|DELETE|HEAD|OPTIONS|TRACE)|-[bf]|--body|--file)'; then
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

# A live command: one decision, logged with the mode and the caller, never "allow".
LOG="${CLAUDE_PROJECT_DIR:-.}/.claude/live_gate.log"
CALLER=
[ "$AGENT" = "true" ] && CALLER=" agent"
log() { printf '%s %s mode=%s%s %s\n' "$(date '+%F %T')" "$1" "$MODE" "$CALLER" "$CMD" >> "$LOG"; }
SHOWN=${FLAT:0:300}
[ ${#FLAT} -gt 300 ] && SHOWN="$SHOWN ..."
RUNBOOK='See docs/RUNBOOK.md, "Live gate (Claude Code)".'
# the decision as Claude Code reads it: JSON on stdout, built by jq or python, never
# interpolated by hand (the matched text and the command can hold quotes)
decide() {
  if command -v jq >/dev/null 2>&1; then
    jq -n --arg d "$1" --arg r "$2" '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: $d, permissionDecisionReason: $r}}'
  else
    python3 -c 'import json, sys; print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": sys.argv[1], "permissionDecisionReason": sys.argv[2]}}))' "$1" "$2"
  fi
}
# refused: a deny decision with the reason, or - should no JSON come out - exit 2 with
# the reason on stderr, which blocks just the same
refuse() {
  REASON="BLOCKED by .claude/hooks/live_gate.sh - matched \"$MATCH\" in: $SHOWN
$1
$RUNBOOK"
  OUT=$(decide deny "$REASON") || OUT=
  log BLOCKED
  if [ -n "$OUT" ]; then
    printf '%s\n' "$OUT"
    exit 0
  fi
  printf '%s\n' "$REASON" >&2
  exit 2
}
if has "$SELF"; then
  refuse "The command approves itself: it sets GLOW_LIVE_OK, or writes a file the next launch
reads its environment from. Nothing pre-approves a live command - Ryan's answer to the
session's prompt is the only go, and GLOW_LIVE_OK grants nothing since 2026-10-14."
fi
if [ "$AGENT" = "true" ]; then
  refuse "A subagent never runs a live command (the input names an agent: agent_id or
agent_type). The main session asks Ryan, and his answer to that prompt is the go."
fi
case "$MODE" in
  '"default"' | '"acceptEdits"' | '"auto"' | '"plan"') ;;
  *) refuse "This session cannot show Ryan the approval prompt (permission_mode $MODE; only
default, acceptEdits, auto and plan can). Run it in an interactive session, or Ryan runs it
in his terminal." ;;
esac
REASON="LIVE command - matched \"$MATCH\" in: $SHOWN
It can change a live system: the Jotform attendance forms, the master enrollment Google
Sheet, the deployed Apps Script, Salesforce, or the automatic sync's switches on GitHub
(live since 2026-09-01). Ryan's answer here is the go; nothing pre-approves it. Yes only
after the dry run was read and the backup exists (backup_forms.py / sheets_client.py
export-all). Direct API access (curl to api.jotform.com, Sheets write snippets, GitHub
dispatches, gh api on actions/, dispatches or graphql) is gated exactly like the tool
flags. The gate matches text: a message that only names a live command asks too.
$RUNBOOK"
OUT=$(decide ask "$REASON") || OUT=
if [ -n "$OUT" ]; then
  log ASKED
  printf '%s\n' "$OUT"
  exit 0
fi
# no ask could be built (jq and python3 both failed): refuse rather than let it through
log BLOCKED
printf '%s\n' "BLOCKED by .claude/hooks/live_gate.sh - the ask decision could not be built. $REASON" >&2
exit 2
