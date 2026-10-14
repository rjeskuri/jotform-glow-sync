# Workflow improvements, 2026-10 (ticket #48)

Written 2026-10-14 on `t/48-workflow-improvements-to-make`, read-only: the board (#1-#48, PRs
#2-#44), the session transcripts of 2026-10-12 to 2026-10-14 (cited by the first 8 characters of
their id, which is the `.jsonl` file name under `~/.claude/projects/-Users-ryaneskuri-jotform-glow-sync*/`),
this repository's `.claude/`, and the harness plugin's source (`~/portfolio_projects/harness`,
plugin 0.2.0; GitHub `rjeskuri/Harness`, its issues to #76). Nothing was filed, applied or
changed outside this file.

**Summary.** The loop works: 12 ticket PRs landed in two days (#17-#41), and the test-breaker found real gaps on 6
tickets. Most of the time lost went to five things: the live gate tripping on *text* (47 blocks in
10 sessions), a form rollout done from memory (a wrong script path, a runner run started before
the land), the Fable limit with no fallback (two tickets stalled), the breaker probing prose
tests (5 of 13 runs found nothing but synonyms), and guardrail patches applied by hand (7 times on
#36). The steady state (small form tweaks, Ryan 2026-10-14) makes the rollout skill the best
return, followed by the cheap fixes to text and escalation.

**Ranking.** Time saved per week, against effort. Each figure is an **estimate**: minutes lost per
occurrence × occurrences seen from 10-12 to 10-14 (three unusually heavy days), scaled to a
steady-state week of one or two form tweaks and a few tickets. Rounded; read them as an order,
not a measurement.

Already covered elsewhere, so not repeated here: the RUNBOOK's stale "Live gate (Claude Code)"
text (#37); which guardrails and legacy code to keep, narrow or remove (#46, which also lists the
dead settings rules); maintainability over six months (#47); ops tickets for record updates with no
code (Harness #72). The exhausted API budget needs no change: dispatch fell back to the
subscription as Harness #50 designed (every dispatched session on 10-14 from 02:20 says so).

## Ranked improvements

| # | Improvement | Owner | Size | Risk | Saved / week (est.) | Evidence |
|---|---|---|---|---|---|---|
| 1 | A `/form-rollout` skill: the rollout of a form change in order, land before the runner | this repo | M | low | 45 min | a4973cb2 02:13, 05:58; #30/PR #40, #31/PR #44; `docs/plans/2026-10-14-idg-celebrations.md` |
| 2 | Text that names a live command goes through a file (`git commit -F`, `--body-file`), never the command line | this repo + harness plugin | S | low | 30 min | 47 live-gate blocks, 10 sessions (table in 2) |
| 3 | Escalation knows the Fable limit: fall back to Opus xhigh instead of "escalate fable" | harness plugin | S | low | 30 min | #30 (e1e437ea 04:48-04:58), #34 needs-input (be47817d 07:41), a4973cb2 04:51 |
| 4 | Breaker: one round on docs-only tests; DoD lines say what, not where | harness plugin | S | low | 30 min | prose-only on #9, #10, #26, #30, #31; position pins on PR #22, PR #40 |
| 5 | Replace the four dead `:*` allow rules | this repo (Ryan's edit) | S | low | 15 min | `.claude/settings.json`; #3/PR #4 |
| 6 | Stop hook leaves a deliberately red ticket worktree alone | harness plugin | S | low | 15 min | a4973cb2 03:17, 03:19; e1e437ea 04:53 |
| 7 | `harness-pr findings P`: the latest harness review and its inline comments | harness plugin | S | low | 15 min | a4973cb2 subagents on PR #41 (05:49, 06:05, 07:10, 12:03) |
| 8 | The work skill assumes agents run in the background | harness plugin | M | med | 15 min | 69 async Agent calls on 10-14 vs 36 synchronous on 10-13; Harness #19 |
| 9 | Guardrail tickets iterate on a draft copy of the hook; Ryan applies once | this repo | M | high | 15 min | a4973cb2: 7 `git apply` runs on #36; #36 needs-input 2026-10-14T03:20Z |
| 10 | Ultrareview: connect the GitHub app once; the harness checks access up front | this repo (Ryan, once) + harness plugin | S | low | 10 min | #30 2026-10-14T03:50Z; skipped again on PR #41 |
| 11 | The reviewer may run its narrower checks: other `make` targets, `git fetch`, scratch redirects | harness plugin | S | med | 10 min | ~20 `readonly_bash` refusals in 9cc90947, 1e3bf26b, 08393fd6, a4973cb2 |
| 12 | A `/sf-metadata` skill and a script that writes the package under `data/` | this repo | M | low | 15 min | a4973cb2 07:14-07:15 |
| 13 | `/land-checks` re-reads the open tickets a landing changes | this repo | S | low | 10 min | #37 outline vs #36's final design; #14's DoD changed in review |
| 14 | `harness-red` accepts a pin ticket with a mutation proof | harness plugin | S | low | 5 min | eae5999c 02:23, 02:27 (#32); epic #5 "no tests-only tasks" |
| 15 | zsh notes where every session reads them | harness plugin | S | low | 5 min | a4973cb2 07:14; 4348a8f6 (this session) |
| 16 | A `reconcile-count` skill: SOQL proofs, counts only | this repo | S | low | 5 min | #35; #28 |
| 17 | A review's header names the model that actually ran | harness plugin | S | low | 0 (audit accuracy) | PR #40 review 2026-10-14T05:09Z |

## 1. A `/form-rollout` skill (this repo; M, low; est. 45 min/week)

**Problem.** Since #30 (PR #40) the runner applies merged form changes, so a form tweak's rollout
is: the template and any disabled form by hand, on Ryan's go; the land; then the runner's next run;
then the re-check and the plan's Result. That sequence lived in one plan and in memory. On 10-14
(a4973cb2) the rollout block given to Ryan at 02:13 named `tools/backup_forms.py` (it is at the
root; the same slip in 9cc90947 on 10-12), and at 05:58 the runner was started from the Actions
tab before PR #40 landed: it ran `main`'s old code, held three regions, exited 2 and showed as
failed, and was re-run at 05:59 after the land. The IDG rollout (#26/PR #27, #30/PR #40, the
Result recorded under #31/PR #44) needed the same steps re-derived across three tickets.
**Fix.** The skill in "New skills" below, which `/land-checks` step 3 points to for a change that
reaches a form. **Saved (estimate):** one rollout or two a week in the steady state, ~20 min each
of re-deriving and correcting steps, plus a failed run avoided.

## 2. Text that names a live command goes through a file (this repo + harness plugin; S, low; est. 30 min/week)

**Problem.** `live_gate.sh` reads command text by design ("Prompt, don't parse", DECISIONS
2026-10-14), so a commit message, a heredoc, a grep pattern or a ticket title that *mentions* a
live flag is blocked in a subagent and asks in the main session. Blocks found in tool results:

| Session | Date | Blocks | What carried the text |
|---|---|---|---|
| 9cc90947 | 10-12 | 4 | a memory-file append; an echo probe in a review subagent; a python heredoc |
| 0a05b6ad | 10-13 | 5 | heredocs editing the handoff and an epic body (one was a real apply, which Ryan ran himself) |
| 08393fd6 | 10-13 | 1 | a breaker scratch command |
| 7fb71042 | 10-13 | 1 | a PR body piped through python |
| a4973cb2 | 10-14 | 17 | a ticket title, ticket text, grep and sed reads, hook tests (10 in subagents) |
| e1e437ea | 10-14 | 7 | a grep pattern, mutation-script heredocs, `cat >` heredocs |
| 72ebb8a8 | 10-14 | 4 | doc-edit commands, a `grep -n` of the workflows |
| eae5999c | 10-14 | 5 | mutation heredocs, a test-file heredoc, `git commit -F -` with the message on stdin |
| a0ca9613 | 10-14 | 1 | a doc heredoc |
| 5c721160 | 10-14 | 2 | a test-edit heredoc, a commit message |

The gate is right to over-ask (#36's decision). The fix is to keep prose off the command line:
write the text with the Write tool, then `git commit -F <file>`, `harness-board comment N
--body-file <file>`, `harness-pr open --notes <file>`; edit files with Edit, not heredocs. The
harness tools already take body files, except `harness-board needs-input --question TEXT` and
`--title` on `epic|task create` (`harness-board` usage lines 10-18), which put text on the
command line. **Fix.** This repo: one paragraph in `.claude/skills/live-systems` and in RUNBOOK
"Live gate (Claude Code)" (fold it into #37 while #37 is open). Harness: `--question-file` and
`--title-file` (draft H2). **Saved (estimate):** ~2 min per block, about a third of the 10-14 rate.

## 3. Escalation knows the Fable limit (harness plugin; S, low; est. 30 min/week)

**Problem.** `harness-work attempt` maps opus→fable and fable→fable (`NEXT_TIER`), and nothing
reads a 429. On #30 (e1e437ea, 04:48-04:52) two Fable coder attempts failed with "You've reached
your Fable limit", and `attempt` then answered "escalate fable", the same exhausted model; Ryan
relayed "use Opus" by hand at 04:58. On #34 (be47817d, 07:41) the review escalated to Fable, hit
the limit and the ticket went to needs-input with three options (#34, 2026-10-14T07:42Z). In
a4973cb2 two #36 agents (04:51, ~05:4x) died the same way. **Fix.** Draft H3. **Saved
(estimate):** one stalled ticket a week at the current limits, ~30 min of Ryan's attention each.

## 4. Breaker: one round on docs-only tests; DoD lines say what, not where (harness plugin; S, low; est. 30 min/week)

**Problem.** The breaker found real gaps on #13/PR #23 (a hard-coded copy of the build set), #32/PR
#39 (41 of 43 mutations killed; the Salesforce step could start before the `--min-active` exit),
#33/PR #43 (a kind-blind `.replace`), #36 (an unknown mode, a fixed agent id, `GET` in the text),
#38 (5c721160: a cheat matched the two fixed snapshots) and #34 (five untested aspects). On #9,
#10, #26, #30 and #31 it only beat prose tests with synonyms or keyword filler, used both rounds
(the cap), and handed the judgement to review (PR #19, #22, #27, #40, #44 bodies). Separately, a
DoD line "DECISIONS.md ends with the new section" produced position-pinned tests that broke the
next ticket (PR #22 inline 2026-10-13T16:52Z, PR #40 inline 2026-10-14T03:39Z). **Fix.** Draft
H4; Harness #76's audit already proposes one breaker round on S/low tickets. **Saved (estimate):**
~15 min per wasted breaker round and its review follow-up, two a week.

## 5. Replace the four dead `:*` allow rules (this repo, Ryan's edit; S, low; est. 15 min/week)

**Problem.** A `:*` rule is a word prefix: it matches the prefix alone or followed by a space
(code.claude.com/docs/en/permissions: "`Bash(ls:*)` matches the same commands as `Bash(ls *)`";
the 2.1.299 matcher checks `startsWith(prefix + " ")`). A `*` before the `:*` is not expanded, and
the binary warns that such a rule "will likely never match". Dead in `.claude/settings.json`:

| Line | Rule | Never matches | Replacement |
|---|---|---|---|
| 12 | `Bash(node test/:*)` | `node test/dispatch_test.js` | `Bash(node test/*)` |
| 14 | `Bash(python3 scripts/check_:*)` | `python3 scripts/check_secrets.py` | `Bash(python3 scripts/check_*)` |
| 14 | `Bash(.venv/bin/python3 scripts/check_:*)` | the same through the venv | `Bash(.venv/bin/python3 scripts/check_*)` |
| 25 | `Bash(harness-*:*)` | `harness-board show 48`, bare `harness-board` | `Bash(harness-board *)`, `Bash(harness-work *)`, `Bash(harness-pr *)`, `Bash(harness-red *)`, `Bash(harness-worklog *)` |

The last one is the rule #3/PR #4 added so dispatched runs could use the board tools. The sessions
ran in `auto` mode, whose classifier approved those calls anyway, so the cost so far is prompts and
classifier latency, not failures; a `dontAsk` or `default` venue would stall on it. Not run
against a live session: the finding comes from the docs and the installed matcher. **Fix.**
Ryan's edit (`protected_paths.sh` guards the file); #46 already lists dead settings rules, so this
can land as part of it. **Saved (estimate):** small but steady.

## 6. Stop hook leaves a deliberately red ticket worktree alone (harness plugin; S, low; est. 15 min/week)

**Problem.** `verify_on_stop.py` runs the verify command in the shell's working directory and blocks
twice on a failure. In a4973cb2 (03:17, 03:19) the shell sat in the #36 worktree, red on purpose
until Ryan applied the patch: two blocked stops. In e1e437ea (04:53) the #30 worktree was red while
the Fable coder was stalled. There is no skip for a red stage (`verify_on_stop.py`:309-367).
**Fix.** Draft H1. **Saved (estimate):** two blocked turns a week, a few minutes each.

## 7. `harness-pr findings P` (harness plugin; S, low; est. 15 min/week)

**Problem.** The work skill's resume step reads the latest harness review with raw `gh api`
(`skills/work/SKILL.md`:22), and `harness-pr comments` filters out the harness's own reviews
(`harness-pr`:1101-1118). In a4973cb2's subagents `harness-pr comments 41` answered "No comments
on PR #41." four times while `gh api …/pulls/41/comments` returned the findings. The logic exists
inside (`latest_harness_review`, `review_findings`, `harness-pr`:985-1018) but no subcommand
exposes it. The #36 decision keeps `Bash(gh api:*)` allowed for exactly these reads. **Fix.** Draft
H5. **Saved (estimate):** a few wrong turns per review round.

## 8. The work skill assumes agents run in the background (harness plugin; M, med; est. 15 min/week)

**Problem.** The work skill says "Run every agent in the foreground, with `run_in_background:
false`" (`skills/work/SKILL.md`:14, :41; Harness #19). On 10-13 the 36 Agent calls in the ticket
sessions ran synchronously; on 10-14 all 69 came back "Async agent launched" (e1e437ea 18, a4973cb2
17, be47817d 10, eae5999c 7, 72ebb8a8 5, 2373f639 5, 5c721160 4, a0ca9613, a876ab2d, f24eae92 1
each). The 10-14 calls passed the value as the string `"false"`; this session's Agent tool has no
such parameter at all and says subagents run in the background. Which of the two caused it is not
confirmed. Interactive sessions coped (a notification wakes the session); the rule cannot be
followed, and a one-turn headless run may again end before its agents return (#19's failure).
**Fix.** Draft H6. **Saved (estimate):** one redispatch a week avoided, more if headless runs return.

## 9. Guardrail tickets iterate on a draft copy of the hook (this repo; M, high; est. 15 min/week)

**Problem.** `protected_paths.sh` keeps `.claude/hooks/` and `settings.json` owner-only, correctly.
On #36 every change to them was a patch Ryan applied with `git apply` in the worktree: seven times
in a4973cb2 (03:26, 04:06, 04:30, 04:58, 07:08, 11:42, 12:22), one pasted into chat first, one after
"show me the git apply code"; #36's needs-input (2026-10-14T03:20Z) asked for it; PR #41's Notes:
"Ryan applied every hook and settings change by hand". **Fix.** The hook tests take the script
under test from `HOOK_UNDER_TEST` (default `.claude/hooks/<name>`); a guardrail ticket's coder edits
`test/hooks_draft/<name>` and the tests run against that, so review rounds never wait on Ryan; at the
end Ryan copies the reviewed draft over the real hook once (one `cp`, one `git diff` to read), and
a test checks the two are identical before the PR is ready. Risk high: it touches how the gate
itself is tested. Overlaps #46 (which carries PR #41's leftover gate gaps): decide there.
**Saved (estimate):** guardrail tickets are rare in the steady state (one a month?), ~60 min each.

## 10. Ultrareview access (this repo, Ryan once + harness plugin; S, low; est. 10 min/week)

**Problem.** `harness-pr ultra 40` failed: "Your connected GitHub account can't see" the repository
(#30, 2026-10-14T03:50Z, posted as needs-input); Ryan skipped it at 04:36 and said he would run
`/web-setup`; PR #41 skipped it too. Two risk:high tickets went without the deep review.
**Fix.** Ryan: if not done yet, run `/web-setup` and give the Claude GitHub app access to this
private repository (not verified here whether it was done). Harness: draft H7 (check access at
`/harness:work` start on a risk:high ticket; report a setup error with the fix, not needs-input).

## 11. The reviewer may run its narrower checks (harness plugin; S, med; est. 10 min/week)

**Problem.** `readonly_bash` already runs the verify and test commands (`scripts/verify.sh` and
`scripts/harness_tests.sh` are plain scripts; `make check`, `test` and `lint` are allowed). It
refused about 20 reviewer commands of four other kinds: `make` targets other than those three
(`make gs`, `make py`; `MAKE_TARGETS`, `readonly_bash.py`:91), output redirects (`make check > …`,
`harness-board show … > file`), `git fetch`, and `git branch --contains <rev>` and
`git check-ignore` (not reading forms) (9cc90947, 1e3bf26b, 08393fd6, a4973cb2). The reviewer then
reran the whole suite or reasoned about results it could have run. **Fix.** Draft H8. Risk medium:
a project's `make` target can write or deploy, so the allowed targets need a per-project list.
**Saved (estimate):** unchanged by the narrower scope: the ~20 refusals counted were all of these
kinds.

## 12. A `/sf-metadata` skill and a package builder (this repo; M, low; est. 15 min/week)

**Problem.** In a4973cb2 (07:14-07:15), retrieving report metadata: a loop built `M="$M -m
Report:…"` and `sf project retrieve start -o glow $M` passed every flag as one argument (zsh does
not split `$M`); the switch to a `package.xml` manifest was then refused by `protected_paths.sh`
(the Write tool may not write under `data/`). The procedure exists as one paragraph in
`.claude/skills/salesforce` ("Metadata"), with no tool that writes the build. **Fix.** The skill in
"New skills" and `tools/sf_package.py` (stdlib; writes `package.xml` and `sfdx-project.json` under
`data/sf_<topic>_<date>/`, refuses an existing folder). **Saved (estimate):** a dashboard or report
change a month, ~45 min of shell trial each.

## 13. `/land-checks` re-reads the open tickets a landing changes (this repo; S, low; est. 10 min/week)

**Problem.** #36's design changed in review ("prompt, don't parse"; `gh api` only on `actions/`,
`dispatches`, `graphql`), but #37's outline still says every `gh api` write is gated and the allow
rule is narrowed (its body, lines 11 and 49-50), and #37 started from it at 13:07. #14's outline
and DoD were stale against the harness (a DoD line dropped in review). **Fix.** A step 6 in
`/land-checks`: list open tickets whose body cites the landing ticket, its epic or a file it
changes (`gh issue list --state open --search "#N"`), say which premise changed, and ask Ryan
before editing a body.

## 14. `harness-red` accepts a pin ticket with a mutation proof (harness plugin; S, low; est. 5 min/week)

**Problem.** A ticket that pins existing behaviour cannot be red: on #32 (eae5999c 02:23, 02:27)
`harness-red` refused twice ("Tests pass before the implementation"), the red stage was waived and
the breaker's mutation run became the proof. Epic #5 decided "no tests-only tasks" for this reason.
**Fix.** Draft H9.

## 15. zsh notes where every session reads them (harness plugin; S, low; est. 5 min/week)

**Problem.** `$M` not split (a4973cb2 07:14, item 12). In this session (4348a8f6): an `echo` of a
`====` separator failed (zsh `=word` expansion: "=== not found") and an unquoted
`--include=*.md` failed ("no matches found"). The global CLAUDE.md (and the harness's
`user/CLAUDE.md`:5) says "macOS with zsh" but names none of its traps: an unquoted `$VAR` is not
word-split, a bare `=word` expands to a command's path, an unquoted glob with no match is an error.
**Fix.** Draft H10: three lines in the harness's `user/CLAUDE.md` template (arrays, not split
strings; quote globs; no bare `=word`).

## 16. A `reconcile-count` skill (this repo; S, low; est. 5 min/week)

**Problem.** "Why does this number differ" questions recur (#35 reconciles what leadership saw;
#28 checked a submitted roster against the live one) and each re-derives which SOQL is
counts-only, where the evidence goes and how to say it without names. **Fix.** The skill in "New
skills". Its runs are ops work, so it pairs with Harness #72 when that lands.

## 17. A review's header names the model that ran (harness plugin; S, low)

**Problem.** PR #40's follow-up review (2026-10-14T05:09Z) is headed "(fable)" while the PR body
says it ran on Opus after the 04:53 limit. Harmless today; wrong in an audit of where Fable went.
**Fix.** Draft H11.

## Inventory

**Skills** (`.claude/skills/`)

| Skill | Decision | Reason |
|---|---|---|
| child-privacy | keep | Minors' data policy; loaded by every doc and test change. |
| deploy-appsscript | keep | The pattern the new procedure skills copy (`disable-model-invocation`, gates, rollback floors). |
| form-status | keep | Read-only report; `/form-rollout` calls it for the re-check. |
| jotform-api | keep | Verified semantics; no friction traced to it. |
| land-checks | keep, add | Add step 6 (item 13); step 3 points to `/form-rollout` for a change that reaches a form. |
| live-systems | keep, add | One paragraph: text that names a live command goes through a file (item 2). |
| salesforce | keep, split | The "Metadata" paragraph moves to `/sf-metadata`, leaving a pointer. |
| sync-preview | keep | Not merged with form-status: one region's dry run versus every form's state, different arguments. |
| form-rollout | **add** | Item 1. |
| sf-metadata | **add** | Item 12. |
| reconcile-count | **add** | Item 16. |

**Agents.** `privacy-auditor`: keep (used by `/land-checks` step 2; the stale `/integrate` line the
harness prep noted is gone). Harness agents: keep; the test-breaker changes in item 4, the reviewer's
command access in item 11.

**Commands.** `.claude/commands/` does not exist; the four `disable-model-invocation` skills
(deploy-appsscript, form-status, land-checks, sync-preview) are the slash commands. Keep that way.

**Settings** (`.claude/settings.json`)
- Dead `:*` rules: the four in item 5. Every other `:*` rule ends on a whole word and works.
- `allow`: keep `git commit`, `git push`, `gh issue|pr|api`, `git worktree|fetch|add` (#3/PR #4; the
  #36 decision keeps `gh api` allowed for the harness's resume reads).
- `ask`: keep; it backs the live gate (DECISIONS 2026-10-14). `Bash(npm run clasp*)` is a working
  glob (no space before `*`, so `npm run clasp:push` matches).
- `deny`: keep. Reading `settings.json` with `cat` alongside `settings.local.json` is refused (four
  subagent denials: 9cc90947, 0a05b6ad, a4973cb2, 4348a8f6); read it with the Read tool.
- Default mode per venue: every session of 10-12..14 ran in `auto`. A project file cannot set `auto`
  (`permissions.defaultMode` is honoured for `auto` only in `~/.claude/settings.json`); dispatch passes
  `--permission-mode auto` (Harness #9); the live gate asks in `default|acceptEdits|auto|plan` and
  denies the rest. No change: do not add a project `defaultMode`.

**Harness plugin** (`~/portfolio_projects/harness`). The installed cache still lists `0.1.0` while the
session runs the source `0.2.0` through the directory marketplace; harmless while the marketplace is a
directory, worth a reinstall when it is not. Its handoff holds the plugin's own upgrade until the
usage reset on 2026-10-16: the drafts below wait for that too.

## New skills

### `form-rollout` (`/form-rollout <ticket>`)

```
description: Roll out a merged-or-ready form change to the live Jotform forms in order - backups, the template and disabled forms by hand on Ryan's go, the land, then the runner's next run on main's new code, the re-check and the plan's Result. Takes the ticket number. Use when a ticket's change reaches a form (glow/sync.py constants, SPECIAL_EVENTS, conditions, options).
disable-model-invocation: true
```
1. **Preconditions.** PR reviewed and CI green; the plan in `docs/plans/` with Rollout, Rollback
   and an empty Result; `scripts/verify.sh` ends `VERIFY OK` on the branch.
2. **What changes where.** From `/land-checks` step 3: which forms the runner will write, which it
   never touches (the template; a disabled form), the bands; say it in plain words.
3. **Backups.** `python3 backup_forms.py --form <id>` (the root, not `tools/`) for the template and
   each hand-applied form; name the files.
4. **Hand applies (Ryan's go each, through the live gate's prompt).** Template, then any disabled
   form: dry run, read it, the apply, `form_status --rendered`, browser check with nothing submitted.
5. **Land.** `/land-checks`, then `/harness:land`.
6. **The runner.** Confirm `origin/main` contains the merge (`git log -1 origin/main`), then wait for
   the next roster change or the morning backstop, or a run from the Actions tab on Ryan's go, and
   check that the run's head commit is the merge (`gh run list --workflow auto-sync.yml -L 1`). A run
   started before the land runs the old code (a4973cb2 05:58).
7. **Verify.** `/form-status` on every form; the SyncLog row; `tools/auto_sync.py` dry run: every
   region `in-sync`.
8. **Result.** Write the plan's Result (times in UTC, backups, the run, the re-check), set `status:
   done`, `make docs-index`.
9. **Rollback.** From the plan; a hand rollback while `main` disagrees is undone by the next run:
   pause the runner or merge the revert first (DECISIONS 2026-10-14, the runner).

### `sf-metadata` (`/sf-metadata <topic>`)

```
description: Change Salesforce metadata (Apex, fields, reports, dashboards, permission sets, folders) with the VPN off - build the package under data/ with tools/sf_package.py, retrieve the live state as the rollback, check-only deploy, Ryan's go, quick deploy, retrieve again and compare. Takes a short topic name. Use for any sf project deploy or retrieve.
disable-model-invocation: true
```
1. **Access.** VPN off; `--vpn-off` on the tools; `sf org display --target-org glow` (never the
   token commands; `.claude/skills/salesforce` "Access").
2. **Build.** `python3 tools/sf_package.py --topic <t> --member Report:<folder>/<name> …` writes
   `data/sf_<t>_<date>/{before,build}/package.xml` and `sfdx-project.json` (the Write tool cannot
   write under `data/`; flags as an array, never a split string).
3. **Retrieve `before/`.** `sf project retrieve start -o glow -x data/sf_<t>_<date>/before/package.xml`.
4. **Edit the build** by script or `sf` generators, not the Write tool.
5. **Check-only.** `sf project deploy validate` with the tests an Apex change needs (the gate asks;
   auto mode may refuse a production deploy: then Ryan runs it).
6. **Go and deploy.** Ryan's go; `sf project deploy quick -i <validation id>`.
7. **Read back.** Retrieve into `after/`, `diff -r` against the build; counts only into the plan.
8. **Rollback.** Redeploy `before/`; a `destructiveChanges.xml` for a new component.

### `reconcile-count` (model-invocable)

```
description: Reconcile a number that differs between sources - Jotform submissions, the sheet's Roster and FormLog, Salesforce batches and attendance rows, a partner's report - with counts-only SOQL and exports, evidence under data/, and a table that explains every difference without a name. Load when asked why a total, a count of girls or a club's attendance differs, or to prove a number before it is reported.
```
1. **The number.** Its exact definition (attendances or girls reached, which dates, which clubs:
   RUNBOOK "Attendance totals and partner-reported counts").
2. **Sources.** Which system holds each side; read paths only (read connector, `sf data query`,
   `form_status`, the sheet exports).
3. **Queries.** Counts, ids, dates, statuses, club names only; never a Contact's name,
   `Contact_IDs__c` or `Status_Message__c` (filter on them, never select).
4. **Evidence.** `data/reconcile_<topic>_<date>/` (queries and results); nothing of it in git.
5. **The table.** Source A, source B, the difference, each cause with its count, what is
   unexplained.
6. **Next.** A fix is a ticket (or a Harness #72 ops ticket once it exists), never done in passing.

**Rejected candidates.** A "live-gate-safe text" skill: one paragraph in `live-systems` does it
(item 2). A "guardrail patch" skill: item 9 removes the repetition instead. Merging `form-status`
and `sync-preview`: see the inventory.

## Draft issues for the harness repository

**Draft, not filed: each needs Ryan's approval.** Checked against `rjeskuri/Harness` issues #1-#76;
none duplicates an open one. They wait for the harness hold to lift (2026-10-16).

**H1. verify_on_stop: leave a deliberately red ticket worktree alone**
> ## Request
> In jotform-glow-sync on 2026-10-14 the stop hook blocked twice while the shell sat in a ticket
> worktree that was red on purpose (tests written, implementation waiting on the owner's patch), and
> once while the coder was stalled on a model limit.
> ## Outline
> 1. Skip (one line, no block) when the working directory is a ticket worktree whose newest
>    `harness-red` record is red and no source file changed since it.
> 2. Run verify in the session's project directory, not wherever the shell's `cd` left it; say
>    which directory it ran in.
> ## Tests
> A red record with no source change: no block. A source change after the record: verify runs.

**H2. harness-board: text arguments from a file**
> ## Request
> Project hooks that read command text (a live-system gate) block a `needs-input --question` or a
> task `--title` that mentions a gated command; 47 blocks in three days in one project, most of them
> text.
> ## Outline
> `needs-input --question-file F` and `epic|task create --title-file F` (`-` for stdin), like
> `--body-file`. The work skill writes ticket text and commit messages to a file and uses `-F`.

**H3. harness-work attempt: fall back when Fable is at its limit**
> ## Request
> Two tickets stalled on 2026-10-14: a coder hit "You've reached your Fable limit" (429) twice and
> `attempt` answered "escalate fable"; a review escalated into the same limit and went to
> needs-input.
> ## Outline
> 1. `harness-work budget exhaust fable --until <reset>` from the 429 text, like the api budget.
> 2. While Fable is exhausted, `tier` and `attempt` answer `opus` with `effort: xhigh` and say
>    "fable at its limit until <reset>"; `NEXT_TIER` fable→fable becomes needs-input, not a retry.
> 3. The review header and the Resolution name the model that ran.
> ## Tests
> attempt on a ticket at opus with fable exhausted: `escalate opus-xhigh`, not `escalate fable`.

**H4. test-breaker: one round on docs-only tests; planner: DoD says what, not where**
> ## Request
> Of 13 breaker runs in one project (2026-10-13/14), 6 found real gaps; 5 only beat prose tests
> with synonyms, used both rounds and handed the judgement to review. A DoD line "the file ends with
> the new section" produced position-pinned tests that broke the next ticket twice.
> ## Outline
> 1. When every new test only reads documents, the breaker runs one round and reports; no
>    re-tightening loop (Harness #76's audit proposes one round on S/low).
> 2. Planner rule: a docs DoD line names the content and its section, never its position.

**H5. harness-pr findings P**
> ## Request
> `harness-pr comments 41` answered "No comments" four times while the latest harness review had
> inline findings; the agents fell back to raw `gh api`. The work skill's resume step also reads
> them with `gh api` from Bash.
> ## Outline
> `harness-pr findings P [--json]`: the newest review carrying the harness marker, its verdict and
> its inline comments (path, line, severity, body), from `latest_harness_review` /
> `review_findings`. The work skill's resume step uses it.

**H6. work skill: agents return asynchronously**
> ## Request
> On 2026-10-14 every Agent call (69) came back "Async agent launched" although the skill requires
> foreground agents; on 10-13 the same calls ran synchronously. The current Agent tool has no
> foreground parameter.
> ## Outline
> 1. Rewrite the rule: launch, then wait for the agent's notification before the next stage; never
>    end the turn with an agent in flight.
> 2. Check a headless `claude -p` dispatch end to end (#19's failure: the process exits with
>    agents running); if it recurs, the dispatch keeps the session alive until the stage ends.

**H7. ultrareview: check access before a risk:high ticket needs it**
> ## Request
> `harness-pr ultra 40` failed: "Your connected GitHub account can't see" the private repository;
> it became a needs-input and was skipped on two risk:high PRs.
> ## Outline
> At `/harness:work` start on a risk:high ticket, check access once; on that error, report a setup
> problem with the fix (`/web-setup`, give the GitHub app the repository), not needs-input.

**H8. readonly_bash: the reviewer's narrower checks**
> ## Request
> About 20 reviewer commands were refused in one project: `make py`, `make gs`,
> `make check > file`, `git fetch`, `git branch --contains`, a board read redirected to a file.
> The verify and test commands already run (plain scripts; `make check`, `test`, `lint`).
> ## Outline
> Allow the `make` targets a project lists as read-only (beside `MAKE_TARGETS`), `git fetch`,
> `git branch --contains <rev>`, `git check-ignore`, and a redirect into the session scratchpad.

**H9. harness-red: a pin ticket**
> ## Request
> A ticket that pins behaviour that already exists cannot be red; `harness-red` refused it twice and
> the proof was a mutation run in the breaker's scratch.
> ## Outline
> `type:pin` (or `--pin`): `harness-red check` accepts green, and `tests_first` accepts the record
> only with the breaker's mutation report attached (killed / total, and every survivor answered).

**H10. user CLAUDE.md template: zsh**
> ## Request
> The template says "macOS with zsh" but not its traps. Three in one project in a day: an unquoted
> `$M` passed every flag as one argument (no word splitting); a bare `====` failed (`=word`
> expansion); an unquoted `--include=*.md` failed (no matches found).
> ## Outline
> Three lines under the macOS note: flags in an array (`args=(…); cmd "${args[@]}"`), quote every
> glob a tool should see, no bare `=word`.

**H11. review header: the model that ran**
> A review headed "(fable)" ran on Opus after the limit. Take the label from the agent's actual
> model (fold into H3 if both are taken).

## Proposed tickets for this repository

Proposals only; none created.

| Title | Size | Risk | Flags | Outline |
|---|---|---|---|---|
| Add the `/form-rollout` skill | M | low | no-tests | The skill above; `/land-checks` step 3 and RUNBOOK "Special events" point to it. |
| Text that names a live command goes through a file | S | low | no-tests | One paragraph in `live-systems` and RUNBOOK "Live gate (Claude Code)"; fold into #37 while it is open. |
| settings: replace the four dead `:*` allow rules | S | low | no-tests, needs-local | The table in item 5, as a patch Ryan applies; or part of #46. |
| Add `tools/sf_package.py` and the `/sf-metadata` skill | M | low | | Tests first for the builder (folder layout, refusal on an existing folder, members as given); the skill above; the salesforce skill's paragraph becomes a pointer. |
| `/land-checks`: re-read the open tickets a landing changes | S | low | no-tests | Step 6 (item 13). |
| Add the `reconcile-count` skill | S | low | no-tests | The skill above; after Harness #72 settles ops tickets. |
| Hook tests run against a draft copy; the owner applies once | M | high | needs-local | Item 9; decide inside #46 first. |

Not a ticket: Ryan connects the Claude GitHub app to this repository for ultrareview (item 10).
