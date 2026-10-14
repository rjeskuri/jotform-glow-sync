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
# gh api: a write on ANY path (since 2026-10-14; before, only under actions/ or to
# /dispatches). The settings ask on every command that starts gh api (Bash(gh api:*)); the
# hook asks on the shapes that rule misses - bash -c, sh -c, eval, gh by its full path, a
# quoted or split gh or api - and on every write. A command that holds a gh word (=gh and
# a path ending in /gh too) and the word api, once continued lines are joined and the quote
# and backslash characters removed (so g""h, g\h, 'gh' and a""pi count; a gh pr or gh issue
# body without api is never read), is read as shell words by python3: backslash-newline
# joins, $'...' and shlex (quotes, pflag shorthand bundles such as -iXDELETE or -iF name=x).
# A # is text, never a comment (Ryan, 2026-10-14: reading comments as bash does let writes
# hide behind "$(...)", backticks, ${x:- #}, heredocs and zsh =(...)). Each gh [-R x] api
# segment up to the next ; | & ( ) < > or line break is judged, and a quoted string that
# holds gh and api the same way (bash -c "gh api ...", eval) is read in turn. A write is a
# method other than GET (-X, -XPOST, -X=POST, --method, --method=, in any case), fields
# or an input file (-f, -F, --field, --raw-field, --input: they make it a POST) with no
# explicit GET (with GET they are the query string), or graphql (a mutation can hide in
# -F query=@file). A method inside a value is a value. Whatever cannot be read - an
# unbalanced quote, an escape in $'...', a short flag gh api does not have, a flag without
# its value, no python3 - counts as a write: the gate fails closed and asks.
# (the Python holds no single quote and no backtick: chr(39) and chr(96) stand in, so the
# heredoc reads the same under any shell's eye; read -d '' takes it whole, no $( ) parsing)
IFS= read -r -d '' GH_API_PY <<'PY' || true
import re, shlex, sys
VALUE_LONG = {"cache", "field", "header", "hostname", "input", "jq", "method", "preview", "raw-field", "template"}
FIELD_LONG = {"field", "raw-field", "input"}
VALUE_SHORT, BOOL_SHORT, OPS = "FHqXpft", "ih", set("();<>|&")
Q, DQ, BT = chr(39), chr(34), chr(96)
QS = "[" + DQ + Q + "]"
# the pre-filter, the same as the shell applies to the whole command
GH_BARE, API_BARE = re.compile(r"(^|[^\w.-])gh([^\w.-]|$)"), re.compile(r"(^|\W)api(\W|$)")
QUOTES_BS = re.compile(r"\$?" + QS + r"|\\")
# the gh ... api text as the command spells it (quotes, =gh, a continued line, -R x), to
# quote in the prompt: a reader sees the words of the command, the description follows
GH_RAW = re.compile("[=\\\\]?" + QS + "?gh" + QS + r"?[\s\\]+(?:(?:-R|--repo)[=\s]*\S+[\s\\]+)?"
                    + QS + "*a" + QS + "*p" + QS + "*i" + QS + "*")

def gh_and_api(text):
    """A gh word and the word api, once continued lines are joined and the quote and
    backslash characters removed (with the $ of $"..." and of ANSI-C quoting)."""
    bare = QUOTES_BS.sub("", text.replace("\\\r\n", "").replace("\\\n", ""))
    return bool(GH_BARE.search(bare) and API_BARE.search(bare))

def words_of(text):
    """Shell words and operators; a # is a word like any other (commenters is empty)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\\\n", "").replace("\n", " ; ")
    if "$" + Q in text:
        if re.search(r"\$" + Q + "[^" + Q + r"]*\\", text):
            raise ValueError("an escape in ANSI-C quoting")
        text = text.replace("$" + Q, Q)
    text = text.replace("$" + DQ, DQ)                  # $"..." reads as "..."
    lex = shlex.shlex(text, posix=True, punctuation_chars=True)
    lex.commenters = ""
    lex.whitespace_split = True
    return list(lex)

def is_op(w):
    return bool(w) and all(c in OPS for c in w)

def is_gh(w):
    w = w.lstrip(BT).lstrip("=")
    return w == "gh" or w.endswith("/gh")

def segment(words, j):
    """From the word after api to the next operator: (end, verdict)."""
    n, method, fields, graphql, positional = len(words), [], False, False, False
    while j < n and not is_op(words[j]):
        w = words[j]
        if positional or w == "-" or not w.startswith("-"):
            if w == "graphql" or w.endswith("/graphql"):
                graphql = True
        elif w == "--":
            positional = True
        elif w.startswith("--"):
            name, eq, val = w[2:].partition("=")
            if name in VALUE_LONG and not eq:
                j += 1
                if j >= n or is_op(words[j]):
                    return j, "write:with --%s and no value (a write)" % name
                val = words[j]
            if name == "method":
                method.append(val)
            elif name in FIELD_LONG:
                fields = True
        else:
            k = 1
            while k < len(w):
                c = w[k]
                if c in BOOL_SHORT:
                    k += 1
                    continue
                if c not in VALUE_SHORT:
                    return j, "write:with a short flag gh api does not have (a write)"
                rest = w[k + 1:]
                if rest.startswith("="):
                    val = rest[1:]
                elif rest:
                    val = rest
                else:
                    j += 1
                    if j >= n or is_op(words[j]):
                        return j, "write:with -%s and no value (a write)" % c
                    val = words[j]
                if c == "X":
                    method.append(val)
                elif c in "Ff":
                    fields = True
                break
        j += 1
    if graphql:
        return j, "write:graphql (a mutation writes)"
    for m in method:
        if m.upper() != "GET":
            return j, "write:with the method %s" % (m if re.fullmatch(r"[A-Za-z]+", m) else "spelt unreadably")
    if fields and not method:
        return j, "write:with fields or --input and no GET method (a POST)"
    return j, "read"

def scan(text, depth):
    words = words_of(text)
    i, n = 0, len(words)
    while i < n:
        w = words[i]
        if is_gh(w):
            j = i + 1
            while j < n and (words[j] in ("-R", "--repo") or words[j].startswith("--repo=") or (words[j].startswith("-R") and len(words[j]) > 2)):
                j += 2 if words[j] in ("-R", "--repo") else 1
            if j < n and words[j] == "api":
                j, verdict = segment(words, j + 1)
                if verdict != "read":
                    return verdict
                i = j
                continue
        elif depth < 3 and re.search(r"\s", w) and gh_and_api(w):
            verdict = scan(w, depth + 1)
            if verdict != "read":
                return verdict
        i += 1
    return "read"

raw = sys.stdin.read()
try:
    verdict = scan(raw, 0)
except Exception as e:
    verdict = "write:that could not be read as shell words (%s: a write)" % e.__class__.__name__
print(verdict)
if verdict != "read":
    found = GH_RAW.search(raw)
    print(found.group(0).replace("\r", " ").replace("\n", " ") if found else "")
PY
# the pre-filter: a gh word ("gh", 'gh', g""h, g\h, \gh, =gh, /usr/local/bin/gh, g\<newline>h)
# and the word api (a""pi, a\pi, ap$'i'), once backslash-newlines are joined and the quote and
# backslash characters removed (with the $ of $'...' and $"..."). The Python decides whether
# api is gh's subcommand.
JOIN=$'\\\n' JOIN_CRLF=$'\\\r\n' ANSI_C="\$'" LOCALE='$"'
BARE=${CMD//"$JOIN_CRLF"/}
BARE=${BARE//"$JOIN"/}
BARE=${BARE//"$ANSI_C"/}
BARE=${BARE//"$LOCALE"/}
BARE=$(printf '%s' "$BARE" | tr -d '\\"'"'" | tr '\n\r' '  ')
WHY=
if [ -z "$MATCH" ] && printf '%s' "$BARE" | grep -Eq '(^|[^[:alnum:]_.-])gh([^[:alnum:]_.-]|$)' \
    && printf '%s' "$BARE" | grep -Eq '(^|[^[:alnum:]_])api([^[:alnum:]_]|$)'; then
  VERDICT=$(printf '%s' "$CMD" | python3 -c "$GH_API_PY") || VERDICT=
  case "$VERDICT" in
    read) ;;
    write:*)   # line 1 write:<description>; line 2 the command's own gh ... api text, if found
      DESC=${VERDICT%%$'\n'*}; DESC=${DESC#write:}
      SNIPPET=${VERDICT#*$'\n'}; [ "$SNIPPET" = "$VERDICT" ] && SNIPPET=
      if [ -n "$SNIPPET" ]; then MATCH=$SNIPPET; WHY=" (gh api $DESC)"; else MATCH="gh api $DESC"; fi ;;
    *) MATCH="gh api that could not be read as shell words (no python3: a write)" ;;
  esac
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
  REASON="BLOCKED by .claude/hooks/live_gate.sh - matched \"$MATCH\"$WHY in: $SHOWN
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
if printf '%s' "$FLAT" | grep -Eq "$SELF"; then
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
REASON="LIVE command - matched \"$MATCH\"$WHY in: $SHOWN
It can change a live system: the Jotform attendance forms, the master enrollment Google
Sheet, the deployed Apps Script, Salesforce, or the automatic sync's switches on GitHub
(live since 2026-09-01). Ryan's answer here is the go; nothing pre-approves it. Yes only
after the dry run was read and the backup exists (backup_forms.py / sheets_client.py
export-all). Direct API access (curl to api.jotform.com, Sheets write snippets, GitHub
dispatches, gh api writes) is gated exactly like the tool flags.
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
