#!/bin/bash
# PreToolUse hook (Bash): the live-system gate.
#
# A command that can change a LIVE system - the Jotform forms, the master Google
# Sheet, the deployed Apps Script, Salesforce, or the automatic sync's switches
# on GitHub - gets one of three answers (since 2026-10-26, ticket #146):
#   - "allow", with no prompt, for a backed WRITE: one simple command whose tool or
#     raw shape is on the lists below and whose backup from today is on record - in
#     the modes default, acceptEdits, auto, dontAsk, bypassPermissions or a missing
#     one, from a subagent too. Logged ALLOWED (mode, target, backup) in
#     .claude/live_gate.log, and a macOS notification (osascript, run detached, the
#     command only ever an argument) tells Ryan what went through;
#   - "ask" (Ryan's prompt in the session; his answer is the go) for everything else
#     live, in default, acceptEdits, auto and plan: a DELETE (--prune, the words
#     delete, remove or destructive in any case and position, sf_dupes.py --apply;
#     and by what a file holds: the Apex file of sf apex run --file holding a word
#     starting delete, undelete, merge or emptyRecycleBin, a deploy naming a folder
#     with a destructiveChanges*.xml below it), a write without its backup from today
#     (the reason names the backup command), a chained or prefixed command, a tool
#     no list names, plan mode;
#   - "deny" where nobody can answer that prompt: a subagent (agent_id in the input;
#     agent_type alone is the main thread of a session started with --agent), and
#     the modes dontAsk, bypassPermissions, a missing or an unknown value (a
#     headless or dispatched run: the reason is its needs-input). And a command
#     that approves itself is refused whatever the mode and the caller: one that
#     sets GLOW_LIVE_OK, writes a file the next launch reads its environment from
#     (~/.zshrc and the other shell startup files, a direnv .envrc, the repository's
#     .env: a redirect, tee, sed -i or perl -i into one, a cp, mv, ln, install,
#     rsync or ditto onto one, or launchctl setenv), writes the .curlrc every curl
#     reads (~/, $CURL_HOME/, $XDG_CONFIG_HOME/; the same ways), or
#     forges a backup - writes, copies, touches or records .claude/live_backups.log
#     by hand (a redirect whose target is the records: after the first > they, a $,
#     a backtick or a glob appear), imports its writer glow/live_backups.py, or
#     writes a Salesforce plan's before/ (touch under it, cp|mv|rsync|ditto|ln|install
#     onto it, > or tee into it - unless a query, export or retrieve alone saves its
#     output there). A read of the records whose output goes elsewhere is no forgery.
# And since ticket #204 (Ryan, 2026-11-04: no prompt unless it is destructive), "allow"
# with no prompt and no backup - in the modes a backed write is allowed in, from a subagent
# too; plan and an unknown mode as before - for what changes no record and no metadata,
# logged PASSED (no notification):
#   - a dashboard refresh: sf|sfdx api request rest /services/data/vNN.N/analytics/
#     dashboards/<01Z id> with PUT (-X, --method) and no body or an empty {} one; a GET of
#     the dashboard or of its /status;
#   - a check-only deploy: sf|sfdx project deploy start --dry-run, or project deploy
#     validate, with -d/--source-dir, -x/--manifest or -m/--metadata, and only -o, -l, -t,
#     -w, --api-version, --json, --concise, --verbose beside them;
#   - a SOQL query: sf|sfdx data query with -q/--query or -f/--file, and only -o, -r, -t,
#     -w, -b, --all-rows, --async, --api-version, --json and --output-file inside data/.
#   Each only as one plain command read as the shell reads it: unquoted letters, digits and
#   _ . / : @ , + = % - (or an empty {}), whole quoted strings ('...', or "..." with no $ `
#   \ or !), nothing the shell would expand, redirect, chain or run, every flag known, and
#   no --apply, --rehearse or --prune anywhere. The self-approvals, the deletes and a deploy
#   of a folder with a destructiveChanges*.xml are judged first, as above. Anything else -
#   another body, method, path or flag, a curl, a quick deploy, --metadata-dir, a request
#   from a file - is judged as before. sf apex run stays as above: a dry run (a savepoint
#   rolled back) cannot be told from its file.
#
# The automatic go needs ALL of:
#   - one simple command: none of ; & | ` $( <( > # or a line break (a
#     backslash-newline too), and a first word that is python3 (or any path ending
#     /python3), node, npm, npx, sf, sfdx, gh, curl or clasp - never env, sudo,
#     nohup, time, exec, a shell's -c or a VAR=value;
#   - a recognised write, each target with its backup: a record in
#     .claude/live_backups.log - `<YYYY-MM-DD HH:MM:SS>\t<target>\t<id>\t<path>`,
#     written by glow/live_backups.py - whose first field is from today (the local
#     date) and whose path is relative, never climbs (..) and still exists here:
#       jotform <form id>|all  the form tools' --apply or --rehearse (FORM_TOOLS
#                              below, by exact path), api.jotform.com,
#                              apply_changes=True; a form id is one after --form
#                              (--form=<id>) or in an API path /form/<id>; a
#                              command naming none, or an odd --form, needs `all`
#                              (backup_forms.py and every tool's own snapshot);
#       sheet <Tab>|all        sheets_client.py import <Tab> (the tab matched
#                              whole); values().update|append|clear, batchUpdate
#                              and rename_club.py: `all` (sheets_client.py export);
#       github all             gh variable|secret set, gh workflow enable|disable,
#                              gh api or api.github.com on actions/
#                              (tools/github_switches.py backup);
#       jotform all            gh workflow run ... apply=true, gh run rerun: they
#                              run the sync, which writes the forms;
#     and with no record:
#       appsscript             clasp push: appsscript/ tracked, nothing uncommitted
#                              or untracked under it (the version before is in git),
#                              and pushed from the folder whose project it is - the
#                              input's cwd, resolved: npx clasp push | clasp push in
#                              <checkout>/appsscript, npm run clasp:push in the
#                              checkout - bare or with -f/--force only;
#       salesforce, raw        sf|sfdx deploys, data writes, apex run, sf api
#                              request writes, .salesforce.com/services/: the
#                              command names a path inside data/sf_<topic>/ and
#                              data/sf_<topic>/before/ holds a file modified today
#                              (the plan's before/ retrieve); apex run only with a
#                              --file the gate reads - a regular file, no link,
#                              inside the checkout - that deletes nothing; a REST
#                              request only with all of it on the command line;
#       salesforce, tools      SF_TOOLS below: each writes its own rollback record
#                              (a ledger row, merge_rollback.json) before every write.
#   Never automatic: gh api or api.github.com on dispatches or graphql; auto_sync.py
#   with --apply-salesforce (Salesforce accounts, no rollback record); a metadata
#   (mdapi) deploy (--metadata-dir, force:mdapi:deploy) and force:apex:execute; a
#   source-tracked one, which deploys local deletions too (Ryan, 2026-11-06):
#   force:source:push, and a project deploy start or deploy metadata with no
#   -d/--source-dir, -m/--metadata or -x/--manifest; what
#   takes its method, URL, headers, body or flags from a file or standard input (review
#   2 of PR #154: a request file or a composite body can hold a DELETE) - sf's
#   --flags-dir, sf api request graphql (its --body names a file whenever one exists),
#   sf api request rest with -f/--file or a --body @file or -, every curl with
#   -K/--config (live whatever host it names or none: Ryan, 2026-11-06), and to .salesforce.com/services/ an @, a < or a lone - anywhere (-d
#   @file, -H @file, -F f=<file), -T/--upload-file, or a python3 -c snippet; any other tool (the
#   Drive photo mover, upload_roster.py, deactivate_clubs.py, ...).
#
# Fast: a few greps, awk, find and git, no network, well inside the 5 s timeout.
# Every decision on a live command is appended to .claude/live_gate.log
# (gitignored), with the mode it was taken in.
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
# apart from a missing, numeric or oddly spelt value), whether it comes from a subagent
# (an agent_id), then the command. Unreadable input gives no fields, hence no command and
# no decision.
if command -v jq >/dev/null 2>&1; then
  FIELDS=$(printf '%s' "$INPUT" | jq -r '[(.permission_mode | @json), (has("agent_id") | tostring), (.tool_input.command | if type == "string" then . else "" end)] | join("\n")')
else
  FIELDS=$(printf '%s' "$INPUT" | python3 -c '
import json, sys
d = json.load(sys.stdin)
mode = json.dumps(d.get("permission_mode"))
agent = "true" if "agent_id" in d else "false"
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
# Salesforce, through sf or the older sfdx: a deploy (a check-only one too: #204's
# pass below lets the plain ones through) or a delete of metadata, data writes,
# anonymous Apex, the REST API itself, and --rehearse (sf_dupes.py's production DML,
# rolled back).
SF='(^|[^[:alnum:]_.-])sf(dx)?[[:space:]]+'
PATTERN="(--apply|--prune|--rehearse|clasp[[:space:]]+push|clasp:push|sheets_client\.py[[:space:]]+import|api\.jotform\.com|api\.github\.com/[^[:space:]]*(actions/|dispatches|graphql)|apply_changes[[:space:]]*=[[:space:]]*True|values\(\)\.(update|append|clear)|batchUpdate"
PATTERN+="|${SF}project[[:space:]]+deploy[[:space:]]+(start|quick|validate)|${SF}deploy[[:space:]]+metadata|${SF}project[[:space:]]+delete[[:space:]]+source"
PATTERN+="|${SF}data[[:space:]]+(create|update|delete|upsert|import)|${SF}apex[[:space:]]+run"
PATTERN+="|${SF}force:(apex:execute|source:(deploy|delete|push)|mdapi:deploy|data:(record|bulk|tree):)|\.salesforce\.com/services/"
# GitHub: the sync's switches (repository variables and secrets: SF_SYNC, AUTO_SYNC_APPLY),
# the workflow itself, a run that applies (apply given true, from a file, by expansion, or
# inputs as JSON) and a rerun (it repeats the recorded inputs); gh api is below. A -R x,
# --repo x or --repo=x may stand before or between the words (gh variable -R o/r set).
# The GitHub API by its URL (curl, a script) is live on the paths the gh api rule below
# names: the Actions API, a dispatch and GraphQL, whatever the method.
REPO='((-R|--repo)[[:space:]=]?[^[:space:]]+[[:space:]]+)?'
GH="(^|[^[:alnum:]_.-])gh[[:space:]]+${REPO}"
APPLY_ON='apply["'\'']?[[:space:]]*[=:][[:space:]]*["'\'']?([Tt][Rr][Uu][Ee]|1|[$@`])'
PATTERN+="|${GH}(variable|secret)[[:space:]]+${REPO}(set|delete|remove)|${GH}workflow[[:space:]]+${REPO}(enable|disable)|${GH}run[[:space:]]+${REPO}rerun"
PATTERN+="|${GH}workflow[[:space:]]+${REPO}run.*(${APPLY_ON}|--json|=@)|${APPLY_ON}.*${GH}workflow[[:space:]]+${REPO}run"
# self-approval: the flag in the command, or written where the next launch picks it up - and
# .curlrc (~/, $CURL_HOME/, $XDG_CONFIG_HOME/), which every curl reads its options from: a
# `request = "DELETE"` there turns a backed curl into a delete (Ryan, 2026-11-06). Written by
# a redirect, tee, sed -i or perl -i into one, or a cp, mv, ln, install, rsync or ditto onto
# one (its name the last word, or the last before a ; & | or ) - a copy FROM one is no write)
NAMES='(\.zshrc|\.zprofile|\.zshenv|\.zlogin|\.bashrc|\.bash_profile|\.bash_login|\.profile|\.envrc|\.env|\.curlrc)'
STARTUP="${NAMES}([^[:alnum:]_.-]|\$)"
WRITES='(>|tee[[:space:]]|sed[[:space:]][^;&|]*(-[[:alnum:]]*i|--in-place)|perl[[:space:]][^;&|]*-[[:alnum:]]*i)[^;&|]*'
COPIES="(^|[^[:alnum:]_.-])(cp|mv|ln|install|rsync|ditto)[[:space:]][^;&|]*[[:space:]/]${NAMES}[[:space:]]*(\$|[;&|)])"
SELF="GLOW_LIVE_OK\\+?=|${WRITES}${STARTUP}|${COPIES}|launchctl[[:space:]]+setenv"
PATTERN+="|${SELF})"
# Prompt, don't parse (Ryan, 2026-10-14): the command is matched as text, never read as
# shell words - a reader fails open on every gap between it and the shell, a text pattern
# fails closed. Every pattern is tried, in any case, on the command on one line (a command
# continued with \ or spread over lines is still one command), on the same with each
# backslash-newline (LF or CRLF) removed, as the shell removes it inside a word (--ap\<LF>ply
# is --apply), and on both with the quote and backslash characters removed (gh 'workflow'
# run, g""h, var\iable, --ap""ply).
JOIN=$'\\\n' JOIN_CRLF=$'\\\r\n'
JOINED=${CMD//"$JOIN_CRLF"/}
JOINED=${JOINED//"$JOIN"/}
FLAT=$(printf '%s' "$CMD" | tr '\n\r' '  ')
JOINED=$(printf '%s' "$JOINED" | tr '\n\r' '  ')
bare() { printf '%s' "$1" | tr -d '\\"'"'"; }
BARE=$(bare "$JOINED")
TEXTS=$FLAT$'\n'$(bare "$FLAT")$'\n'$JOINED$'\n'$BARE
has() { printf '%s\n' "$TEXTS" | grep -Eiq -e "$1"; }
first() { printf '%s\n' "$TEXTS" | grep -Eio -e "$1" | head -1; }
MATCH=$(first "$PATTERN") || true
# gh api: a gh word (any case, a path ending in /gh, =gh) and the word api, with actions/,
# dispatches or graphql anywhere in the command: the Actions API (the sync's variables,
# secrets, workflows and runs), a repository dispatch, GraphQL (a mutation can hide in
# -F query=@file). Live whatever the method - a read of them asks too. Every other gh api
# call (issues, comments, labels, the harness's resume reads) is ungated, as before 2026-10-14,
# and so is a message that mentions gh api without those words.
GH_API=
if has '(^|[^[:alnum:]_.-])gh([^[:alnum:]_.-]|$)' && has '(^|[^[:alnum:]_])api([^[:alnum:]_]|$)'; then
  ON=$(first 'actions/|dispatches|graphql' | tr '[:upper:]' '[:lower:]')
  [ -n "$ON" ] && GH_API="gh api on $ON"
fi
[ -z "$MATCH" ] && MATCH=$GH_API
# sf api request: any GraphQL call (a mutation writes), and a REST call that writes - a method
# other than GET (the CLI offers GET POST PUT PATCH HEAD DELETE OPTIONS TRACE), a body (-b,
# --body), a request file (-f, --file: it carries its own method and body) or --flags-dir (a
# file per flag: the method too). A relative path (/services/data/...) does not name the host,
# so the URL pattern above does not see it.
SF_API=
if has "${SF}api[[:space:]]+request[[:space:]]+graphql"; then
  SF_API="sf api request graphql"
elif has "${SF}api[[:space:]]+request[[:space:]]+rest" \
    && has '(^|[[:space:]])((-X|--method)[[:space:]=]*["'\'']?(POST|PUT|PATCH|DELETE|HEAD|OPTIONS|TRACE)|-[bf]|--body|--file|--flags-dir)'; then
  SF_API="sf api request rest that writes"
fi
[ -z "$MATCH" ] && MATCH=$SF_API
# curl with a config file (Ryan, 2026-11-06): it sets the method, the URL and the data, so every
# curl -K is live, whatever host it names or none - a -K (alone, joined to its file, or last in
# a cluster of short options like -sSK, not inside -X's value) or --config (or a prefix curl
# takes for it, --conf) after a curl word. Matched case-sensitively: -k is --insecure
CURL_K='^-[^-X]*K' CURL_T='^-[^-X]*T'   # a short option in a cluster, not inside -X's value
curl_config() {
  local w seen=
  while IFS= read -r w; do
    case "$w" in [Cc][Uu][Rr][Ll] | */[Cc][Uu][Rr][Ll]) seen=1; continue ;; esac
    [ -n "$seen" ] || continue
    case "$w" in
      --conf*) ;;
      --*) continue ;;
      -*) [[ $w =~ $CURL_K ]] || continue ;;
      *) continue ;;
    esac
    printf '%s' "$w"
    return 0
  done <<EOF
$(set -f; printf '%s\n' $BARE)
EOF
  return 1
}
CURL_CONF=$(curl_config) || CURL_CONF=
[ -z "$MATCH" ] && MATCH=$CURL_CONF
# A forged backup is a self-approval too (#146): the records the automatic go trusts
# (.claude/live_backups.log, any spelling of its path) named together with a write verb, or
# as a redirect's target - anywhere after the command's first > it names them, a $, a
# backtick or a glob (a target the gate cannot read: a variable, a substitution); their
# writer (glow/live_backups.py) imported or called by hand; a Salesforce plan's before/
# written by hand. Reading them (its output or errors redirected elsewhere: > out.txt,
# 2>/dev/null), copying FROM a before/, the retrieve into one, a query or an export saved
# into one - alone: sf|sfdx data query|export or project retrieve start, no ; & | ` $( <( or
# line break -, their tests and a commit message that names them are no forgery (F5 of PR #154's
# review).
VERB='(^|[^[:alnum:]_.-])(tee|cp|mv|dd|ln|install|rsync|ditto|touch|truncate)([^[:alnum:]_.-]|$)'
# each spelling of the command from its first > on: every redirect's target is in it
after_redirect() {
  local t
  while IFS= read -r t; do
    case "$t" in *'>'*) printf '%s\n' "${t#*>}" ;; esac
  done <<EOF
$TEXTS
EOF
}
FORGED= FORGED_KIND=
if has 'live_backups\.log' \
    && { has "${VERB}|sed[[:space:]][^;&|]*(-[[:alnum:]]*i|--in-place)|perl[[:space:]][^;&|]*-[[:alnum:]]*i|open\(|write_text|write_bytes" \
         || after_redirect | grep -Eiq 'live_backup|[$*?`]|\['; }; then
  FORGED=$(first 'live_backups\.log') FORGED_KIND=records
elif has 'live_backups' && has 'import|live_backups\.record'; then
  FORGED=$(first 'live_backups') FORGED_KIND=writer
else
  TRIMMED=${BARE%"${BARE##*[![:space:]]}"}
  LAST=${TRIMMED##*[[:space:]]}
  case "$LAST" in before | before/* | */before | */before/*) LAST_BEFORE=1 ;; *) LAST_BEFORE= ;; esac
  SAVED=      # a query, an export or a retrieve alone: what it saves into a before/ is the backup
  case "$CMD" in
    *';'* | *'&'* | *'|'* | *'`'* | *'$('* | *'<('* | *$'\n'* | *$'\r'*) ;;
    *) read -r S1 S2 S3 S4 _ <<<"$CMD"
       case "$S1" in sf | sfdx | */sf | */sfdx)
         case "$S2 $S3" in 'data query' | 'data export') SAVED=1 ;; esac
         [ "$S2 $S3 ${S4:-}" = 'project retrieve start' ] && SAVED=1 ;;
       esac ;;
  esac
  if { has '(^|[^[:alnum:]_.-])touch([^[:alnum:]_.-]|$)' && has '(^|[[:space:]/=])before/'; } \
      || { [ -n "$LAST_BEFORE" ] && has '(^|[^[:alnum:]_.-])(cp|mv|rsync|ditto|ln|install)([^[:alnum:]_.-]|$)'; } \
      || { [ -z "$SAVED" ] && has '(>|(^|[^[:alnum:]_.-])tee[[:space:]])[^;&|]*(^|[[:space:]/=])before/'; }; then
    FORGED="before/" FORGED_KIND=before
  fi
fi
[ -z "$MATCH" ] && MATCH=$FORGED

# ---- #204: what changes no record and no metadata passes with no prompt and no backup - a
# dashboard refresh and its read, a check-only deploy, a SOQL query (the header lists each
# shape). The command is read as the shell reads it only where that reading is plain: SW gets
# its words when every one is made of unquoted letters, digits and _ . / : @ , + = % - (an
# empty {} too: no brace expansion), and whole quoted strings - '...', or "..." with no $ `
# \ or ! -, split by spaces and tabs (the shell's blanks); anything else (a line break, ; & |
# < > ( ) # ~ * ? [ ], a $, a backslash, a quote left open) is no plain command, and no pass
PLAIN_PIECE='^([A-Za-z0-9_./:@,+=%-]+|\{\}|'"'[^']*'"'|"[^"$`\\!]*")'
BLANK=$' \t'
SW=()
plain_words() {
  local rest=$CMD word piece started
  case "$rest" in *$'\n'* | *$'\r'*) return 1 ;; esac
  while :; do
    rest=${rest#"${rest%%[!$BLANK]*}"}
    [ -z "$rest" ] && break
    word= started=
    while [[ $rest =~ $PLAIN_PIECE ]]; do
      piece=${BASH_REMATCH[1]}
      rest=${rest:${#piece}}
      case "$piece" in \'*\' | \"*\") piece=${piece:1:$((${#piece} - 2))} ;; esac
      word=$word$piece
      started=1
    done
    [ -n "$started" ] || return 1
    case "$rest" in '' | ["$BLANK"]*) ;; *) return 1 ;; esac
    SW[${#SW[@]}]=$word
  done
  [ ${#SW[@]} -gt 0 ]
}
ALIAS_RE='^[A-Za-z0-9_][A-Za-z0-9_.@+-]*$'                 # -o/--target-org: an alias or a username
VERSION_RE='^[0-9]+\.[0-9]+$'
PATH_RE='^[A-Za-z0-9_./][A-Za-z0-9_./@+-]*$'              # a source folder, a manifest, a SOQL file
METADATA_RE='^[A-Za-z][A-Za-z0-9_]*(:[A-Za-z0-9_.*/-]+)?$'  # Type or Type:Name (Report:Folder/Name)
TEST_RE='^[A-Za-z0-9_.]+$'
DASHBOARD_RE='^/services/data/v[0-9]+\.[0-9]+/analytics/dashboards/01Z[A-Za-z0-9]{12}([A-Za-z0-9]{3})?(/status)?$'
# a query's --output-file: a file inside data/ (from the checkout), never climbing out
output_in_data() {
  local p=${1#./}
  case "$p" in data/?*) ;; *) return 1 ;; esac
  case "/$p/" in */../* | */./*) return 1 ;; esac
  [[ $p =~ $PATH_RE ]]
}
# sf|sfdx api request rest: a dashboard refresh (PUT, no body or {}) or a GET of it or its /status
pass_rest() {
  local i=4 n=${#SW[@]} w name val url= method= body= bodies=0 orgs=0
  while [ "$i" -lt "$n" ]; do
    w=${SW[$i]}; i=$((i + 1))
    case "$w" in
      -i | --include) continue ;;
      --*=*) name=${w%%=*}; val=${w#*=} ;;
      -X?*) name=-X; val=${w#-X} ;;
      -*) name=$w; [ "$i" -lt "$n" ] || return 1; val=${SW[$i]}; i=$((i + 1)) ;;
      *) [ -z "$url" ] || return 1; url=$w; continue ;;
    esac
    case "$name" in
      -X | --method) [ -z "$method" ] || return 1; method=$val ;;
      -b | --body) bodies=$((bodies + 1)); body=$val ;;
      -o | --target-org) orgs=$((orgs + 1)); [[ $val =~ $ALIAS_RE ]] || return 1 ;;
      --api-version) [[ $val =~ $VERSION_RE ]] || return 1 ;;
      *) return 1 ;;
    esac
  done
  [[ $url =~ $DASHBOARD_RE ]] || return 1
  [ "$bodies" -le 1 ] && [ "$orgs" -le 1 ] || return 1
  case "$method" in
    PUT)
      case "$url" in */status) return 1 ;; esac
      case "$body" in '' | '{}') ;; *) return 1 ;; esac
      PASS="a dashboard refresh" ;;
    '' | GET)
      [ "$bodies" -eq 0 ] || return 1
      PASS="a read of a dashboard" ;;
    *) return 1 ;;
  esac
}
# sf|sfdx project deploy start --dry-run | validate, with an explicit source
pass_deploy() {
  local verb=${SW[3]} i=4 n=${#SW[@]} w name val dry= src=
  while [ "$i" -lt "$n" ]; do
    w=${SW[$i]}; i=$((i + 1))
    case "$w" in
      --dry-run) [ "$verb" = start ] || return 1; dry=1; continue ;;
      --json | --concise | --verbose) continue ;;
      --*=*) name=${w%%=*}; val=${w#*=} ;;
      -?*) name=$w; [ "$i" -lt "$n" ] || return 1; val=${SW[$i]}; i=$((i + 1)) ;;
      *) return 1 ;;
    esac
    case "$name" in
      -d | --source-dir | -x | --manifest) [[ $val =~ $PATH_RE ]] || return 1; src=1 ;;
      -m | --metadata) [[ $val =~ $METADATA_RE ]] || return 1; src=1 ;;
      -o | --target-org) [[ $val =~ $ALIAS_RE ]] || return 1 ;;
      -l | --test-level)
        case "$val" in NoTestRun | RunSpecifiedTests | RunLocalTests | RunAllTestsInOrg | RunRelevantTests) ;; *) return 1 ;; esac ;;
      -t | --tests) [[ $val =~ $TEST_RE ]] || return 1 ;;
      -w | --wait) [[ $val =~ ^[0-9]+$ ]] || return 1 ;;
      --api-version) [[ $val =~ $VERSION_RE ]] || return 1 ;;
      *) return 1 ;;
    esac
  done
  [ -n "$src" ] || return 1
  [ "$verb" = validate ] || [ -n "$dry" ] || return 1
  PASS="a check-only deploy"
}
# sf|sfdx data query: one SOQL (-q, or -f from a file), read-only flags, a result file in data/
pass_query() {
  local i=3 n=${#SW[@]} w name val queries=0
  while [ "$i" -lt "$n" ]; do
    w=${SW[$i]}; i=$((i + 1))
    case "$w" in
      --json | -t | --use-tooling-api | --all-rows | -b | --bulk | --async) continue ;;
      --*=*) name=${w%%=*}; val=${w#*=} ;;
      -?*) name=$w; [ "$i" -lt "$n" ] || return 1; val=${SW[$i]}; i=$((i + 1)) ;;
      *) return 1 ;;
    esac
    case "$name" in
      -q | --query) queries=$((queries + 1)) ;;
      -f | --file) [[ $val =~ $PATH_RE ]] || return 1; queries=$((queries + 1)) ;;
      -r | --result-format) case "$val" in human | csv | json) ;; *) return 1 ;; esac ;;
      -o | --target-org) [[ $val =~ $ALIAS_RE ]] || return 1 ;;
      -w | --wait) [[ $val =~ ^[0-9]+$ ]] || return 1 ;;
      --output-file) output_in_data "$val" || return 1 ;;
      --api-version) [[ $val =~ $VERSION_RE ]] || return 1 ;;
      *) return 1 ;;
    esac
  done
  [ "$queries" -eq 1 ] || return 1
  PASS="a SOQL query"
}
PASS=
case "$CMD" in
  sf["$BLANK"]* | sfdx["$BLANK"]*)
    if ! has '--apply|--rehearse|--prune' && plain_words; then
      case "${SW[1]:-} ${SW[2]:-} ${SW[3]:-}" in
        'api request rest') pass_rest ;;
        'project deploy start' | 'project deploy validate') pass_deploy ;;
        'data query '*) pass_query ;;
      esac
    fi ;;
esac
[ -z "$MATCH" ] && [ -z "$PASS" ] && exit 0

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

# A live command: one decision, logged with the mode and the caller.
PROJECT=${CLAUDE_PROJECT_DIR:-}
LOG="${PROJECT:-.}/.claude/live_gate.log"
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
# Ryan's prompt in the session, with why the command is not automatic
ask() {
  REASON="LIVE command - matched \"$MATCH\" in: $SHOWN
$1
It can change a live system: the Jotform attendance forms, the master enrollment Google
Sheet, the deployed Apps Script, Salesforce, or the automatic sync's switches on GitHub
(live since 2026-09-01). Ryan's answer here is the go. Yes only after the dry run was read
and the backup exists. The gate matches text: a message that only names a live command
asks too.
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
}
# not automatic: Ryan is asked where a prompt can show, refused where none can
not_automatic() {
  if [ "$AGENT" = "true" ]; then
    refuse "$1
A subagent cannot show Ryan the prompt (the input carries an agent_id): from one, only a
backed write goes through, and this one is not. The main session asks Ryan, and his
answer is the go; a headless run takes it to needs-input."
  fi
  case "$MODE" in
    '"default"' | '"acceptEdits"' | '"auto"' | '"plan"') ask "$1" ;;
  esac
  refuse "$1
This session cannot show Ryan the approval prompt (permission_mode $MODE; only
default, acceptEdits, auto and plan can): needs-input. Run it in an interactive session,
or Ryan runs it in his terminal."
}
# #204's pass: allowed in the modes a backed write is allowed in, from a subagent too, and
# logged PASSED - no notification, nothing changes. In plan or an unknown mode it returns, and
# the command is judged as before
pass_through() {
  case "$MODE" in
    '"default"' | '"acceptEdits"' | '"auto"' | '"dontAsk"' | '"bypassPermissions"' | null) ;;
    *) return 0 ;;
  esac
  local out
  out=$(decide allow "PASSED by .claude/hooks/live_gate.sh - $PASS: it changes no record and no metadata, so it needs no prompt and no backup (ticket #204).
$RUNBOOK") || out=
  [ -n "$out" ] || return 0
  { log PASSED; } 2>/dev/null
  printf '%s\n' "$out"
  exit 0
}
# a query or a dashboard read with nothing live in its text: allowed, or no decision as before
if [ -z "$MATCH" ]; then
  pass_through
  exit 0
fi

if has "$SELF" || [ -n "$FORGED" ]; then
  case "$FORGED_KIND" in
    records) HOW="It forges a backup record: it writes .claude/live_backups.log by hand (a redirect
into it, a copy, move or link onto it, tee, touch, truncate or an edit in place). Only a
backup tool writes a record, once its backup is on disk. To read the records, run the read
alone without redirecting into them: cat, tail or grep .claude/live_backups.log (its output
or errors may go elsewhere, > out.txt or 2>/dev/null)." ;;
    writer) HOW="It forges a backup record: it imports or calls the records' writer
(glow/live_backups.py) by hand. Only a backup tool calls it, once its backup is on disk." ;;
    before) HOW="It forges a Salesforce plan's before/ retrieve: it writes a before/ folder by hand
(touch, a copy, move, sync or link onto it, a redirect or tee into it from anything but a
query). Take the before/ with sf project retrieve start ... --target-dir
data/sf_<topic>/before, or save a query there, alone: sf data query ... >
data/sf_<topic>/before/<name>.csv (or sf data export ... --output-dir it)." ;;
    *) HOW="It sets GLOW_LIVE_OK, or writes a file the next launch reads its environment from (a
shell startup file, .envrc, .env: a redirect, tee or edit in place into it, or a copy, move or
link onto it), or the .curlrc every curl reads its options from, or runs launchctl setenv." ;;
  esac
  refuse "The command approves itself. $HOW
Nothing pre-approves a live command: a backup tool's own record, or Ryan's answer to the
session's prompt, is the go. GLOW_LIVE_OK grants nothing since 2026-10-14."
fi

# every curl with a config file (Ryan, 2026-11-06): before the delete words, so the reason names
# the config file even when its name holds one
[ -n "$CURL_CONF" ] && not_automatic "curl with a config file ($CURL_CONF) is never automatic, whatever host it names or none: its
method, URL and data come from a file the gate does not read (Ryan, 2026-11-06)."

# DELETES ask whatever the backups (Ryan, 2026-10-26): --prune (and the words argparse
# takes for it or --remove: --pr, --re, ...), delete, remove or destructive in any case and
# position (sf data delete, sf project delete source, destructiveChanges, gh variable|secret
# delete|remove, an HTTP DELETE however spelt), and sf_dupes.py --apply (a merge deletes the
# losing record).
if has '--prune|delete|remove|destructive|(^|[[:space:]])--(p|pr|pru|prun|r|re|rem|remo|remov)([[:space:]=]|$)' \
    || { has 'sf_dupes' && has '--apply'; }; then
  not_automatic "A delete or --prune: it asks whatever the backups (ticket #146)."
fi

# the command's words, quotes and backslashes removed (for the flags and paths read below)
set -f
WORDS=($BARE)
set +f
words() { [ ${#WORDS[@]} -gt 0 ] && printf '%s\n' "${WORDS[@]}"; }
# the checkout and the Bash tool's working folder (the input's cwd, where a relative path in
# the command starts and clasp looks for its project), each resolved - links and .. followed;
# empty when missing, relative, not a folder, or unreadable input
input_cwd() {
  local c
  if command -v jq >/dev/null 2>&1; then
    c=$(printf '%s' "$INPUT" | jq -j '.cwd | if type == "string" then . else "" end' 2>/dev/null; printf x)
  else
    c=$(printf '%s' "$INPUT" | python3 -c '
import json, sys
c = json.load(sys.stdin).get("cwd")
print(c if isinstance(c, str) else "", end="")' 2>/dev/null; printf x)
  fi
  printf '%s' "${c%x}"
}
resolved() { (cd -P -- "$1" 2>/dev/null && pwd -P); }
PROJECT_REAL=
[ -n "$PROJECT" ] && case "$PROJECT" in /*) PROJECT_REAL=$(resolved "$PROJECT") ;; esac
CWD_IN=$(input_cwd)
WD=
case "$CWD_IN" in
  *$'\n'* | *$'\r'*) ;;
  /*) WD=$(resolved "$CWD_IN") ;;
esac

# ... and the deletes that only a file shows (F1 of PR #154's review): anonymous Apex whose
# file holds delete, merge (a merge deletes the losing record), undelete or emptyRecycleBin -
# a word starting so, in any case: DML or a Database. call (a field like IsDeleted is no
# such word) -, and a deploy naming a folder with a destructiveChanges*.xml anywhere below it
# (it deletes what that file lists).
# the files `sf|sfdx apex run` runs: each -f, --file, --file=, -f=, -f<name> value, as "f:<name>"
apex_files() {
  local w expecting=
  while IFS= read -r w; do
    if [ -n "$expecting" ]; then
      expecting=
      printf 'f:%s\n' "$w"
      continue
    fi
    case "$w" in
      -f | --file) expecting=1 ;;
      --file=*) printf 'f:%s\n' "${w#--file=}" ;;
      -f=*) printf 'f:%s\n' "${w#-f=}" ;;
      -f?*) printf 'f:%s\n' "${w#-f}" ;;
    esac
  done <<EOF
$(words)
EOF
  [ -n "$expecting" ] && printf 'f:\n'
  return 0
}
# a file the gate can read for what the org will run: a regular file, no link, readable, its
# folder (links followed) inside the checkout; a relative name from the working folder
apex_path() {
  local f=$1 dir
  [ -n "$f" ] && [ -n "$PROJECT_REAL" ] || return 1
  case "$f" in /*) ;; *) [ -n "$WD" ] || return 1; f="$WD/$f" ;; esac
  [ -f "$f" ] && [ ! -L "$f" ] && [ -r "$f" ] || return 1
  dir=$(resolved "$(dirname -- "$f")") || return 1
  case "$dir/" in "$PROJECT_REAL"/*) ;; *) return 1 ;; esac
  printf '%s' "$f"
}
APEX=           # sf apex run: none (no --file), unread (a file it cannot read here), deletes, ok
if has "${SF}apex[[:space:]]+run"; then
  APEX_FILES=$(apex_files)
  if [ -z "$APEX_FILES" ]; then
    APEX=none
  else
    APEX=ok
    while IFS= read -r line; do
      if p=$(apex_path "${line#f:}"); then
        grep -Eiq '(^|[^[:alnum:]_])(delete|undelete|merge|emptyrecyclebin)' "$p"
        case $? in
          0) APEX=deletes; break ;;
          1) ;;
          *) APEX=unread ;;
        esac
      else
        APEX=unread
      fi
    done <<EOF
$APEX_FILES
EOF
  fi
fi
[ "$APEX" = deletes ] && not_automatic "Anonymous Apex that deletes: the file sf apex run runs holds delete, merge (a merge
deletes the losing record), undelete or emptyRecycleBin. A delete asks whatever the backups
(ticket #146)."
# the first folder a deploy names (from the working folder or the checkout) with a
# destructiveChanges*.xml anywhere below it
destructive_below() {
  local w c base d
  while IFS= read -r w; do
    for c in "$w" "${w#--*=}" "${w#-?=}" "${w#@}" "${w#-?}"; do
      [ -n "$c" ] || continue
      for base in "$WD" "$PROJECT"; do
        case "$c" in /*) d=$c ;; *) [ -n "$base" ] || continue; d="$base/$c" ;; esac
        [ -d "$d" ] || continue
        if [ -n "$(find -L "$d" -iname 'destructiveChanges*.xml' 2>/dev/null | head -1)" ]; then
          printf '%s' "$c"
          return 0
        fi
      done
    done
  done <<EOF
$(words)
EOF
  return 1
}
DEPLOY="${SF}(project[[:space:]]+deploy|deploy[[:space:]]+metadata|force:(source:(deploy|push)|mdapi:deploy))"
if has "$DEPLOY" && DESTRUCTIVE=$(destructive_below); then
  not_automatic "A deploy of $DESTRUCTIVE, which holds a destructiveChanges*.xml: destructive changes delete
what they list. A delete asks whatever the backups (ticket #146)."
fi

# #204: a dashboard refresh or a check-only deploy, once no self-approval and no delete is in it
[ -n "$PASS" ] && pass_through

# ---- a WRITE: automatic when it is one simple command, recognised, and backed up today
TODAY=$(date +%F)
BACKUPS="$PROJECT/.claude/live_backups.log"
WHY=        # why not automatic (the first reason found)
NEEDS=      # what must be backed up: "<target>\t<id>" lines
HINTS=      # the backup commands that are missing
TARGETS=    # what goes through, for the log and the notification
USED=       # the backups used
nope() { [ -z "$WHY" ] && WHY=$1; }
need() { case $'\n'"$NEEDS" in *$'\n'"$1"$'\t'"$2"$'\n'*) ;; *) NEEDS="$NEEDS$1"$'\t'"$2"$'\n' ;; esac; }
add_target() {   # target id
  case " $TARGETS " in *" $1 "*) ;; *) TARGETS="${TARGETS:+$TARGETS }$1" ;; esac
  IDS="${IDS:+$IDS, }$1 $2"
}
add_used() { case ", $USED, " in *", $1, "*) ;; *) USED="${USED:+$USED, }$1" ;; esac; }
IDS=

case "$CMD" in
  *';'* | *'&'* | *'|'* | *'`'* | *'$('* | *'<('* | *'>'* | *'#'* | *$'\n'* | *$'\r'*)
    nope "it is no single simple command (a ; & | \` \$( <( > # or line break in it)." ;;
esac
read -r W1 W2 W3 _ <<<"$CMD"
case "$W1" in *=*) nope "it starts with a variable assignment ($W1)." ;; esac
LAUNCHER=
case "$W1" in
  python3 | */python3) LAUNCHER=python ;;
  node | npm | npx | clasp | sf | sfdx | gh | curl) LAUNCHER=$W1 ;;
  *) nope "its first word ($W1) is no launcher the automatic go knows (python3, node, npm, npx, sf, sfdx, gh, curl, clasp)." ;;
esac
[ -z "$PROJECT" ] || [ ! -d "$PROJECT" ] && nope "CLAUDE_PROJECT_DIR is not set."

# the tool a python3 command runs, by its path from the checkout (./ and the checkout's
# own path allowed before it)
SCRIPT=${W2:-}
SCRIPT=${SCRIPT#./}
[ -n "$PROJECT" ] && SCRIPT=${SCRIPT#"$PROJECT"/}
FORM_TOOLS=" sync_attendance_form.py restore_conditions.py tools/add_feedback_link.py tools/add_language.py tools/add_session_notes.py tools/add_translations.py tools/auto_sync.py tools/disable_form.py tools/fix_name_translations.py tools/fix_roster_order.py tools/rename_club.py tools/restore_translations.py tools/switcher_flags.py tools/update_static_fields.py "
SF_TOOLS=" tools/sf_backfill.py tools/sf_dupes.py tools/sf_girls_present.py tools/sf_partner_monthly.py tools/sf_report_folders.py "
TOOL=
if [ "$LAUNCHER" = python ]; then
  case "$FORM_TOOLS" in *" $SCRIPT "*) TOOL=form ;; esac
  case "$SF_TOOLS" in *" $SCRIPT "*) TOOL=sf ;; esac
  [ "$SCRIPT" = tools/sheets_client.py ] && TOOL=sheets
  [ "$SCRIPT" = -c ] && TOOL=snippet
  [ -z "$TOOL" ] && nope "${SCRIPT:-python3} is on no list of tools whose write is automatic."
fi
[ "$LAUNCHER" = node ] && nope "no node tool's write is automatic."

# a word argparse would take for FLAG: FLAG itself or a prefix of it at least MIN long
abbrev_of() {   # FLAG MIN
  local w
  while IFS= read -r w; do
    [ ${#w} -ge "$2" ] && case "$1" in "$w"*) return 0 ;; esac
  done <<EOF
$(words)
EOF
  return 1
}
# the form ids a command writes: each after --form (or a prefix argparse takes for it) and
# in an API path /form/<id>; a value that is no 15-digit id makes it "all"
jotform_needs() {
  local w expecting= ids= all= v
  while IFS= read -r w; do
    if [ -n "$expecting" ]; then
      expecting=
      case "$w" in [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]) ids="$ids $w" ;; *) all=1 ;; esac
      continue
    fi
    case "$w" in
      --f | --fo | --for | --form) expecting=1 ;;
      --f=* | --fo=* | --for=* | --form=*)
        v=${w#*=}
        case "$v" in [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]) ids="$ids $v" ;; *) all=1 ;; esac ;;
    esac
  done <<EOF
$(words)
EOF
  [ -n "$expecting" ] && all=1
  while IFS= read -r v; do
    [ -z "$v" ] && continue
    v=${v#/[Ff][Oo][Rr][Mm]/}
    case "$v" in [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]) ids="$ids $v" ;; *) all=1 ;; esac
  done <<EOF
$(printf '%s\n' "$BARE" | grep -Eio '/form/[^/?&[:space:]]*')
EOF
  if [ -n "$all" ] || [ -z "$ids" ]; then
    need jotform all
  else
    for v in $ids; do need jotform "$v"; done
  fi
}
# the tab of `sheets_client.py import <Tab>`, as the shell hands it over: a quoted name whole,
# an unquoted one its first word; anything it cannot read for sure needs `sheet all`
sheet_tab() {
  local rest tab= after= i
  [ "$W3" = import ] || return 0
  rest=$CMD
  for i in 1 2 3; do
    rest=${rest#"${rest%%[![:space:]]*}"}
    rest=${rest#"${rest%%[[:space:]]*}"}
  done
  rest=${rest#"${rest%%[![:space:]]*}"}
  case "$rest" in
    \"*) tab=${rest#\"}
         case "$tab" in *\"*) after=${tab#*\"}; tab=${tab%%\"*} ;; *) tab= ;; esac
         case "$tab" in *[\$\`\\]*) tab= ;; esac ;;
    \'*) tab=${rest#\'}
         case "$tab" in *\'*) after=${tab#*\'}; tab=${tab%%\'*} ;; *) tab= ;; esac ;;
    *) tab=${rest%%[[:space:]]*}; after=${rest#"$tab"}
       case "$tab" in *[\"\'\$\`\\]*) tab= ;; esac ;;
  esac
  case "$after" in '' | [[:space:]]*) ;; *) tab= ;; esac
  printf '%s' "$tab"
}

# the families of live text in the command; each must be one its launcher writes through
FAMILIES=
has '--apply|--rehearse' && FAMILIES="$FAMILIES toolflag"
has 'clasp[[:space:]]+push|clasp:push' && FAMILIES="$FAMILIES clasp"
has 'sheets_client\.py[[:space:]]+import' && FAMILIES="$FAMILIES sheetimport"
has 'api\.jotform\.com|apply_changes[[:space:]]*=[[:space:]]*True' && FAMILIES="$FAMILIES jotform"
has 'values\(\)\.(update|append|clear)|batchUpdate' && FAMILIES="$FAMILIES sheetapi"
has 'api\.github\.com/[^[:space:]]*(actions/|dispatches|graphql)' && FAMILIES="$FAMILIES ghurl"
has '\.salesforce\.com/services/' && FAMILIES="$FAMILIES sfurl"
has "${SF}project[[:space:]]+deploy[[:space:]]+(start|quick|validate)|${SF}deploy[[:space:]]+metadata|${SF}data[[:space:]]+(create|update|upsert|import)|${SF}apex[[:space:]]+run|${SF}force:(apex:execute|source:(deploy|push)|mdapi:deploy|data:(record|bulk|tree):)" \
  && FAMILIES="$FAMILIES sfraw"
[ -n "$SF_API" ] && FAMILIES="$FAMILIES sfraw"
has "${GH}(variable|secret)[[:space:]]+${REPO}set|${GH}workflow[[:space:]]+${REPO}(enable|disable)" && FAMILIES="$FAMILIES ghswitch"
has "${GH}run[[:space:]]+${REPO}rerun|${GH}workflow[[:space:]]+${REPO}run.*(${APPLY_ON}|--json|=@)|${APPLY_ON}.*${GH}workflow[[:space:]]+${REPO}run" \
  && FAMILIES="$FAMILIES ghrun"
[ -n "$GH_API" ] && FAMILIES="$FAMILIES ghapi"
[ -z "$FAMILIES" ] && nope "no write the automatic go knows."
case "$LAUNCHER:$TOOL" in
  python:form | python:sf) OK_FAMILIES=" toolflag " ;;
  python:sheets) OK_FAMILIES=" sheetimport " ;;
  python:snippet) OK_FAMILIES=" jotform sheetapi ghurl sfurl " ;;
  curl:) OK_FAMILIES=" jotform ghurl sfurl " ;;
  sf: | sfdx:) OK_FAMILIES=" sfraw sfurl " ;;
  gh:) OK_FAMILIES=" ghswitch ghrun ghapi ghurl " ;;
  npm: | npx: | clasp:) OK_FAMILIES=" clasp " ;;
  *) OK_FAMILIES=" " ;;
esac
for f in $FAMILIES; do
  case "$OK_FAMILIES" in *" $f "*) ;; *) nope "it is no write the automatic go knows ($f text under $W1${TOOL:+ $SCRIPT})." ;; esac
done

# Review 2 of PR #154: what the gate decides on - the method above all, a DELETE or not - must be
# in the command's text (a curl config file: never automatic, above). A Salesforce REST request - sf api request rest, or the URL - whose method, URL, headers
# or body come from a file or standard input (a request file carries its own method, a composite
# body can hold DELETE sub-requests): a < redirect, an @ anywhere (sf's --body @file; curl's -d,
# --data*, --json, -H, -F, --variable or --url-query with @file or @-), a lone - (sf's --body -,
# --body=-, -b-), sf's -f/--file, curl's -T/--upload-file (or --up, a prefix curl takes for it).
# Prints the word that shows it
sf_request_file() {
  local w
  [ "$SF_API" = "sf api request rest that writes" ] || has '\.salesforce\.com/services/' || return 1
  case "$CMD" in *'<'*) printf '<'; return 0 ;; esac
  while IFS= read -r w; do
    case "$LAUNCHER:$w" in
      *:*@* | *:- | *:*=- | *:-b- | sf:-f* | sfdx:-f* | sf:--f* | sfdx:--f* | curl:--up*) ;;
      curl:-[!-]*) [[ $w =~ $CURL_T ]] || continue ;;
      *) continue ;;
    esac
    printf '%s' "$w"
    return 0
  done <<EOF
$(words)
EOF
  return 1
}

# a deploy's explicit source: -d/--source-dir, -m/--metadata, -x/--manifest, each also joined to
# its value (-d<path>, --source-dir=<path>); --results-dir and --metadata-dir are none
explicit_source() {
  local w
  while IFS= read -r w; do
    case "$w" in
      --source-dir | --source-dir=?* | --metadata | --metadata=?* | --manifest | --manifest=?*) return 0 ;;
      --*) ;;
      -[dmx]*) return 0 ;;
    esac
  done <<EOF
$(words)
EOF
  return 1
}

# what each family writes, and so must be backed up
if [ -z "$WHY" ]; then
  for f in $FAMILIES; do
    case "$f" in
      toolflag)
        if [ "$TOOL" = sf ]; then
          need salesforce "${SCRIPT#tools/}"
        else
          jotform_needs
          [ "$SCRIPT" = tools/rename_club.py ] && need sheet all
          if [ "$SCRIPT" = tools/auto_sync.py ]; then
            abbrev_of --apply-salesforce 8 && nope "auto_sync.py --apply-salesforce creates Salesforce accounts with no rollback record."
            abbrev_of --synclog 3 && need sheet all
          fi
        fi ;;
      clasp)
        # clasp pushes the .clasp.json project of its working folder (F2 of PR #154's review):
        # npx clasp push or clasp push from appsscript/, npm run clasp:push (it goes there
        # itself) from the checkout - the folder is checked with the backup below -, bare or
        # with -f/--force only: -P, --project, --rootDir or any other flag can push another one
        CLASP_IN=
        case "$LAUNCHER" in
          npm) [ "${WORDS[1]:-}" = run ] && [ "${WORDS[2]:-}" = clasp:push ] && CLASP_IN=. ;;
          npx) [ "${WORDS[1]:-}" = clasp ] && [ "${WORDS[2]:-}" = push ] && CLASP_IN=appsscript ;;
          clasp) [ "${WORDS[1]:-}" = push ] && CLASP_IN=appsscript ;;
        esac
        if [ -z "$CLASP_IN" ]; then
          nope "the automatic Apps Script push is npx clasp push or clasp push run in appsscript/, or npm run clasp:push run in the checkout."
        else
          case "$LAUNCHER" in clasp) i=2 ;; *) i=3 ;; esac
          while [ "$i" -lt ${#WORDS[@]} ]; do
            case "${WORDS[$i]}" in
              -f | --force) ;;
              --) [ "$LAUNCHER" = npm ] && [ "$i" -eq 3 ] \
                    || nope "clasp push goes through bare or with -f (--force) only, not with ${WORDS[$i]}." ;;
              *) nope "clasp push goes through bare or with -f (--force) only, not with ${WORDS[$i]}: -P, --project, --rootDir and the other flags can push another project." ;;
            esac
            i=$((i + 1))
          done
          need appsscript "$CLASP_IN"
        fi ;;
      sheetimport) TAB=$(sheet_tab); need sheet "${TAB:-all}" ;;
      jotform) jotform_needs ;;
      sheetapi) need sheet all ;;
      ghurl | ghapi)
        if has 'dispatches|graphql'; then
          nope "a repository dispatch or GraphQL call is never automatic."
        else
          need github all
        fi ;;
      sfurl | sfraw)
        # F1 of PR #154's review: what a metadata folder or force:apex:execute changes is not
        # read here; anonymous Apex only from a file the gate read above
        if has '--metadata-dir|force:mdapi:'; then
          nope "a deploy of a metadata (mdapi) folder (--metadata-dir, force:mdapi:deploy) is never automatic: deploy a source folder (--source-dir)."
        # a source-tracked push or deploy deploys local deletions too, which the gate does not
        # see (Ryan, 2026-11-06)
        elif has 'force:source:push'; then
          nope "sfdx force:source:push is never automatic: it pushes the project's tracked changes, local deletions too. Deploy an explicit source: sf project deploy start --source-dir, --manifest or --metadata."
        elif has "${SF}(project[[:space:]]+deploy[[:space:]]+start|deploy[[:space:]]+metadata)" && ! explicit_source; then
          nope "a deploy with no explicit source deploys the project's tracked changes, local deletions too: it goes through only with -d/--source-dir, -x/--manifest or -m/--metadata."
        elif has 'force:apex:execute'; then
          nope "force:apex:execute is never automatic: sf apex run --file <a file in the checkout> is, when that file deletes nothing."
        elif [ "$APEX" = none ]; then
          nope "anonymous Apex goes through only from a --file in the checkout that the gate reads; this one has none (its Apex comes from standard input)."
        elif [ "$APEX" = unread ]; then
          nope "anonymous Apex goes through only from a --file in the checkout that the gate reads; this file is not there, cannot be read, is a link, or lies outside the checkout."
        # review 2 of PR #154: the method, URL, headers, body or flags from a file the gate does
        # not read
        elif has '--flags-dir'; then
          nope "sf --flags-dir is never automatic: each flag's value comes from a file in that folder, which the gate does not read (a method, a destructive-changes file)."
        elif [ "$SF_API" = "sf api request graphql" ]; then
          nope "sf api request graphql is never automatic: its --body is read from a file whenever one by that name exists, and a mutation can delete."
        elif [ "$TOOL" = snippet ] && has '\.salesforce\.com/services/'; then
          nope "a python3 -c snippet to .salesforce.com/services/ is never automatic: what it sends can come from a file the gate does not read."
        elif FROM=$(sf_request_file); then
          nope "a Salesforce request whose method, URL, headers or body come from a file or standard input ($FROM) is never automatic: the gate does not read it, and a request file or a composite body can hold a DELETE. Put the request on the command line (-X and an inline --body)."
        fi
        need salesforce-plan - ;;
      ghswitch) need github all ;;
      ghrun) need jotform all ;;
    esac
  done
fi

# a backup record of today that still holds: the path of the last one for target and id
record() {   # target id
  [ -f "$BACKUPS" ] || return 1
  local p found=
  while IFS= read -r p; do
    case "$p" in '' | . | /* | .. | ../* | */.. | */../*) continue ;; esac
    [ -e "$PROJECT/$p" ] && found=$p
  done <<EOF
$(T=$1 I=$2 D=$TODAY awk -F'\t' 'NF == 4 && $2 == ENVIRON["T"] && $3 == ENVIRON["I"] && substr($1, 1, 11) == ENVIRON["D"] " " && $1 ~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]$/ { print $4 }' "$BACKUPS" 2>/dev/null)
EOF
  [ -n "$found" ] || return 1
  printf '%s' "$found"
}
# the Salesforce plan folders a raw write names (data/sf_<topic>/...): each needs a file in
# its before/ modified today
sf_topics() {
  local w
  while IFS= read -r w; do
    w=${w#--*=}
    case "$w" in -?data/*) w=${w#-?} ;; esac   # a short flag joined to its folder: -ddata/sf_x
    w=${w#@}
    w=${w#./}
    case "$w" in data/sf_*/?*) ;; *) continue ;; esac
    case "/$w/" in */../*) continue ;; esac
    w=${w#data/}
    printf '%s\n' "data/${w%%/*}"
  done <<EOF
$(words)
EOF
}
before_today() {   # data/sf_<topic>
  [ -d "$PROJECT/$1/before" ] || return 1
  [ -n "$(find "$PROJECT/$1/before" -type f -newermt "$TODAY" ! -newermt "$TODAY 23:59:59" 2>/dev/null | head -1)" ]
}
# appsscript/ tracked, with nothing uncommitted or untracked under it: the short HEAD
appsscript_head() (
  unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR GIT_CEILING_DIRECTORIES
  [ -d "$PROJECT/appsscript" ] || exit 1
  command -v git >/dev/null 2>&1 || exit 1
  [ -n "$(git -C "$PROJECT" ls-files -- appsscript 2>/dev/null | head -1)" ] || exit 1
  STATUS=$(git -C "$PROJECT" status --porcelain --untracked-files=all -- appsscript 2>/dev/null) || exit 1
  [ -z "$STATUS" ] || exit 1
  SHA=$(git -C "$PROJECT" rev-parse HEAD 2>/dev/null) || exit 1
  [ -n "$SHA" ] || exit 1
  printf '%s' "${SHA:0:7}"
)
sf_tool_record() {   # tool file name: its own rollback record, written before each write
  case "$1" in
    sf_backfill.py) echo "ledger.csv in its --dir (default data/backfill_2026-09)" ;;
    sf_dupes.py) echo "merge_rollback.json in the plan's folder" ;;
    sf_girls_present.py) echo "ledger.csv in its --dir (default data/sf_girls_present)" ;;
    sf_partner_monthly.py) echo "ledger.csv in its --dir (default data/sf_partner_monthly)" ;;
    sf_report_folders.py) echo "ledger.csv in its --dir (default data/sf_report_folders)" ;;
  esac
}

if [ -z "$WHY" ]; then
  while IFS=$'\t' read -r target ident; do
    [ -z "$target" ] && continue
    case "$target" in
      jotform)
        if [ "$ident" != all ] && p=$(record jotform "$ident"); then
          add_used "$p"; add_target jotform "$ident"
        elif p=$(record jotform all); then
          add_used "$p"; add_target jotform "$ident"
        elif [ "$ident" = all ]; then
          HINTS="$HINTS
- no backup from today of every form (jotform all): run python3 backup_forms.py first."
        else
          HINTS="$HINTS
- no backup from today of form $ident: run python3 backup_forms.py --form $ident first."
        fi ;;
      sheet)
        if [ "$ident" != all ] && p=$(record sheet "$ident"); then
          add_used "$p"; add_target sheet "$ident"
        elif p=$(record sheet all); then
          add_used "$p"; add_target sheet "$ident"
        elif [ "$ident" = all ]; then
          HINTS="$HINTS
- no backup from today of the Sheet (sheet all): run python3 tools/sheets_client.py export-all data/sheet_$TODAY first."
        else
          HINTS="$HINTS
- no backup from today of the Sheet's $ident tab: run python3 tools/sheets_client.py export \"$ident\" data/sheet_$TODAY/$ident.csv (or export-all) first."
        fi ;;
      github)
        if p=$(record github all); then
          add_used "$p"; add_target github all
        else
          HINTS="$HINTS
- no backup from today of the sync's GitHub switches (github all): run python3 tools/github_switches.py backup first."
        fi ;;
      appsscript)   # ident: the folder the push must run in, from the checkout (. or appsscript)
        if sha=$(appsscript_head); then
          WANT=$PROJECT_REAL
          [ "$ident" = . ] || WANT="$PROJECT_REAL/$ident"
          if [ -n "$PROJECT_REAL" ] && [ -n "$WD" ] && [ "$WD" = "$WANT" ]; then
            add_used "appsscript/ at HEAD $sha"; add_target appsscript "$sha"
          else
            case "$ident" in .) WHERE="the checkout" ;; *) WHERE="$ident/" ;; esac
            nope "Not automatic: clasp pushes the project of the folder it runs in, and this push runs in ${CWD_IN:-a folder the input does not name}, not $WHERE (npx clasp push in appsscript/, npm run clasp:push in the checkout)."
          fi
        else
          HINTS="$HINTS
- appsscript/ is not clean and committed (a change, an untracked file, or no git): commit it first, so the version before the push is in git."
        fi ;;
      salesforce)
        add_used "$(sf_tool_record "$ident")"; add_target salesforce "$ident" ;;
      salesforce-plan)
        TOPICS=$(sf_topics | sort -u)
        if [ -z "$TOPICS" ]; then
          HINTS="$HINTS
- no backup from today: the command names no plan folder data/sf_<topic>/ whose before/ retrieve is from today (sf project retrieve start ... --target-dir data/sf_<topic>/before first)."
        fi
        while IFS= read -r topic; do
          [ -z "$topic" ] && continue
          if before_today "$topic"; then
            add_used "$topic/before"; add_target salesforce "${topic#data/}"
          else
            HINTS="$HINTS
- no backup from today of $topic/: retrieve what it changes into $topic/before/ first (sf project retrieve start ... --target-dir $topic/before)."
          fi
        done <<EOF
$TOPICS
EOF
        ;;
    esac
  done <<EOF
$NEEDS
EOF
  [ -n "$HINTS" ] && nope "Not automatic - a backup is missing:$HINTS"
  [ -z "$USED" ] && nope "no backup on record."
else
  WHY="Not automatic: $WHY"
fi

if [ -z "$WHY" ]; then
  case "$MODE" in
    '"default"' | '"acceptEdits"' | '"auto"' | '"dontAsk"' | '"bypassPermissions"' | null) ;;
    '"plan"') WHY="Not automatic in plan mode (a hook's allow has no effect there); its backup from today is on record: $USED." ;;
    *) WHY="Not automatic in this mode; its backup from today is on record: $USED." ;;
  esac
fi
[ -n "$WHY" ] && not_automatic "$WHY"

# ALLOWED: the answer, then the log line, then the notification (detached: the hook never
# waits on it; the command only ever an argument, never AppleScript text)
TARGET=${TARGETS// /+}
REASON="AUTO-APPROVED by .claude/hooks/live_gate.sh - a live write to $IDS, backed up today: $USED.
Logged in .claude/live_gate.log; Ryan is notified. $RUNBOOK"
OUT=$(decide allow "$REASON") || OUT=
if [ -z "$OUT" ]; then
  log BLOCKED
  printf '%s\n' "BLOCKED by .claude/hooks/live_gate.sh - the allow decision could not be built for: $SHOWN" >&2
  exit 2
fi
printf '%s ALLOWED mode=%s%s target=%s backup=%s %s\n' "$(date '+%F %T')" "$MODE" "$CALLER" "$TARGET" "$USED" "$CMD" >> "$LOG"
if command -v osascript >/dev/null 2>&1; then
  (osascript -e 'on run argv' -e 'display notification (item 2 of argv) with title (item 1 of argv)' -e 'end run' \
    "GLOW live write auto-approved" "$IDS: ${CMD:0:120}" </dev/null >/dev/null 2>&1 &)
fi
printf '%s\n' "$OUT"
exit 0
