# What stops Claude from working automatically (2026-10)

Ticket #46 (epic #45), counted 2026-10-14. The question was which legacy code and guardrails
stop Claude most often, and what each stop costs Ryan by hand. The ranking is by what is
**still live in the code at `e5b04f8`**, after #30 and #36. Stops that #29/#31/#36 already removed
are listed apart. Ticket statuses, the overlaps and the counts of `test/runbook_test.py` and
`docs/RUNBOOK.md` were brought up to date on 2026-10-15 at `c0592fc` (main merged in: #31 and #33
landed; #31, #33, #36 and #48 are closed, #34 and #37 open).

Counts come from scripts that print counts only (in this session's scratch directory, not
committed). No command text was copied, because command text can carry a girl's name. Every
number names its source. Anything marked **estimate** says what it is based on.

## Ranked stops (still live)

Hand work is per stop. Classes: **(a)** protects against something real, keep it;
**(b)** now covered by PR review and tests, a candidate to remove; **(c)** a false positive of
the mechanism, a candidate to narrow.

| # | Stop (code) | Count (source) | Hand work per stop | Class | Smallest change | Size / risk |
|---|---|---|---|---|---|---|
| 1 | `live_gate.sh`: a live flag that sits only in **text**: a heredoc body (`cat > doc <<EOF`, `git commit -F -`), a commit message, a `harness-board` question | gate log: 199 of 429 entries are text and 94 more are no-network python heredocs that edit files. Transcripts: 21 heredoc bodies, 1 commit message, 1 board question among 81 blocks [E1, E5] | main session: today, one approval prompt for Ryan (estimate 15–30 s each: read the reason, answer). Subagent or dispatched run: **denied**, so 1–3 extra tool calls to rephrase, or the stage stalls | (c) | No hook change ("prompt, don't parse" stands). Text goes through files: `git commit -F <file>`, `gh pr/issue --body-file`, docs through Write/Edit, never `cat > file <<EOF`. One line in CLAUDE.md rule 1 and in the live-systems skill's "The gate" (ticket 1: the workflow doc's item 2) | S / low |
| 2 | `live_gate.sh`: a **read-only pipeline** that mentions a flag (`grep -n -- --apply X \| head`, `sed -n`, `echo`) | transcripts: grep 10, git grep 1, sed 3, echo 3 of 81 blocks. Gate log: grep 48, echo 5 [E1, E5] | as #1. The exemption covers a read-only command only when it stands alone, so one pipe makes it ask, or deny in a subagent | (c) | Keep `read_only()` and its place exactly as today (`read_only && exit 0` above `if has "$SELF"`), so the standalone mentions that pass now still pass and `test_a_read_only_command_that_only_mentions_a_live_flag_passes` (`test/hooks_test.py`) stays green. Add a separate pipeline branch after it: accept `\|` between segments when every segment starts with a word that cannot write a file: `grep head tail cat wc ls cut`. Not `sort` (`sort -o F`), `uniq` (`uniq IN OUT`), `rg` (`--pre` runs a program) or `sed` (`w`, `-i`). Every other operator (`;`, `&`, a backtick, `$(`, `<(`, `>`, a newline) still asks, and so does any word not on the list. The branch needs no `SELF` check: `SELF` matches the variable's assignment text, a write to a startup file (`>`, `tee`, `sed -i`, `perl -i`) and `launchctl setenv`; with `>` rejected and those words off the list, no passing pipeline can write a file or set the environment (a segment cannot start with an assignment or `export` either), so the variable's text in one is a mention, like the standalone `grep` of it that passes today, and since #36 the variable grants nothing. `sed`, `echo` and `git` are not on it, so their 7 transcript stops (sed 3, echo 3, git grep 1) remain; the change covers at most the 10 grep ones. `git grep` stays out: it could join only without `-O`/`--open-files-in-pager`, which runs a program, and that is 1 stop | S / high (gate, protected file) |
| 3 | `live_gate.sh` **subagent rule**: any match in a subagent is denied, mentions included | transcripts, harness era (2026-10-13/14, 2 days): 33 of 46 blocks came from subagents. 31 of the 33 are still denied by today's hook (re-run on the same commands; 2 now pass); none was a real write [E5] | the subagent rewrites or gives up. The orchestrator or Ryan picks it up | (a) for real writes; the mentions are #1 and #2 | Nothing on its own: #1 and #2 take away the mentions. Keep the rule: a live write never comes from a subagent | — |
| 4 | `.claude/settings.json` deny rule `Read(./.env)`: a Bash command that names `.env` (to see whether the key file exists, or to read or source it) is denied in every mode, main sessions too | transcripts: 39 "Permission to use Bash … denied", 32 of them in subagents. **36 of the 39 name `.env` itself** (first words of the denied part: head 20, ls 7, grep 2, others 7); 1 names a path outside the project; 2 have no cause found. Not a missing allow rule: `Bash(ls:*)` and `Bash(wc:*)` are allowed, and all 7 `ls` and the 1 `wc` denials name `.env` [E6] | 1–2 extra tool calls (estimate); the agent drops the check or asks | (a): it keeps the API key out of transcripts (CLAUDE.md rule 2) | Keep the rule. One sentence in CLAUDE.md rule 2 (ticket 10), which every session and subagent reads: the tools load the key themselves and refuse without it (`glow/cli.py`), so nothing needs to name `.env`. Do **not** add `Bash(cat:*)`/`Bash(head:*)` either: they would read `data/` silently, past the `Read(./data/**)` ask. The dead rules are ticket 9 (the "Settings rules that never match" row below the top 10) | S / low |
| 5 | `protected_paths.sh` on `.claude/hooks/*` and `.claude/settings*.json`: Ryan applies every guardrail change by hand | 2 tickets since 2026-10-13 (#3 "Ryan's edit", #36 "Ryan applied the hook and settings", git log bodies of `459451d`, `e5b04f8`). #36: 1 needs-input; 11 assistant messages in one session asked Ryan to apply a guardrail patch (**estimate**, a regex) [E2]. Git: 12 commits to `.claude/hooks` and `.claude/settings.json` in all [E3]. Transcripts: 0 blocks on hooks or settings [E6] | high: Ryan reviews the diff, copies the files and re-runs verify, every review round (estimate 10–20 min per round, from #36: needs-input 03:20Z, PR 03:42Z) | (a) | Keep the block. Iterate on a draft, apply once (ticket 5: the workflow doc's item 9, adopted here by Ryan on 2026-10-15): the hook tests take the script under test from `HOOK_UNDER_TEST` (default `.claude/hooks/<name>`); a guardrail ticket's coder edits `test/hooks_draft/<name>` and every review round runs against it; at the end Ryan copies the reviewed draft over the real hook once (one `cp`, one `git diff` to read), and a test checks that the draft and the real hook are identical before the PR is ready. A `settings.json` change stays a patch Ryan applies | M / high (how the gate itself is tested) |
| 6 | `protected_paths.sh` on `data/`: new work files (a Salesforce metadata package, a helper script) under `data/<dated>/` | transcripts: 10 blocks in 4 sessions (6 transcript files, 2 main and 4 subagent; 8 of the 10 in subagents), 2026-09-28 … 2026-10-14 [E6] | 1–3 tool calls: the file is generated by a script instead (estimate). No Ryan time | (a) for existing exports; (c) for new work files | No hook change (`data/` holds minors' names). The `/sf-metadata` skill the workflow doc proposes (item 12, a proposed ticket there) says builds are generated by a script or kept in the scratchpad | M / low (item 12's ticket) |
| 7 | Plan document for every change with a live rollout (CLAUDE.md conventions, `docs/templates/plan.md`, `docs_index.py --check`) | 44 plans, all added since 2026-09-01: `git log --diff-filter=A --name-only --format= -- docs/plans`, README left out, unique paths: 44, all still on disk; `docs_index.py --check`: "ok (44 plans, 11 intents)". (`--since=2026-09-01` gives 42: it drops the 2 plans added on 2026-09-01 itself in `4eee550`.) 0 check failures found in transcripts [E6] | authoring, not a stop: about one plan per working day (estimate, from the count) | (b) for a generated form change whose rollout is now the merge (#30); (a) for hand rollouts | A plan only when hand steps remain (the template, a disabled form, Salesforce, Apps Script). A generated change carries `Live:` in its PR. One line in CLAUDE.md and the template | S / low |
| 8 | Prose-pinning tests: `test/runbook_test.py` (40 tests in 9 classes at `c0592fc`, 32 in 7 at `e5b04f8`; a `.md` file named on 87 lines), `special_events_test.py` `RunbookQuotes`/`IdgDocs`, `doc_refs_test.py` | `runbook_test.py` has changed in 11 commits since it was created on 2026-10-09 (9 at `e5b04f8`). The breaker "cheat passed" twice on doc tests only (#30 Resolution); #31 breaker fail ×2 (`harness-work` attempts) [E2, E3]. Transcripts: 1 failing result named a runbook class [E6] | each doc ticket rewrites or adds pins: #31 (landed, `0fbd63c`) added `RolloutProcedures` (5 tests) and updated the `ContactIdsRunbook` pins; #33 added `FixHintsRunbook` (3 tests) [E3]. Breaker rounds cost tokens, not Ryan's time | (b) for sentence quotes of historical plans; (a) for pinned commands, form ids and headings | Keep the pins on commands, ids and headings (`doc_refs` already guards headings). Drop sentence-level quotes of plans that ran (`RosterRepairRunbook`, `SameNameRunbook`) | M / low |
| 9 | `sync_attendance_form.py` refusal flags: `--q5-change-ok`, `--same-name-switch`, `--disabled-ok`, `--prune` on a form with submissions; `auto_sync.py --min-active` | transcripts, failed commands that name the flag: q5 2, same-name 3, disabled 2, prune 3; min-active/floor 9 (**estimate**, a loose marker) [E6]. Gate log, real applies that carried a flag: `--same-name-switch` 4, `--disabled-ok` 1 [E1] | one re-run with the flag after reading why (a minute, estimate). On Ryan's go | (a) | Keep them all. One question: does the disabled U.S form still need every form change by hand (`--disabled-ok`, RUNBOOK "Special events", **Add a type** step 4, from #31)? If not, that hand step goes | S / low (a question first) |
| 10 | `--vpn-off` (`glow/salesforce.py require_vpn_off`) | transcripts: 5 failed commands with the VPN marker (**estimate**, the marker also matches other text); gate log: 13 real applies carried `--vpn-off` [E1, E6] | one re-run, after Ryan confirms the VPN is off | (a) | Keep. Salesforce freezes the user (CLAUDE.md rule 12) | — |

Below the top 10, still live but rarely or never stopping work:

| Stop | Count (source) | Class | Change |
|---|---|---|---|
| `live_gate.sh` self-approval rule: the `GLOW_LIVE_OK=` text (and startup-file writes) | 17 gate-log entries, **all mentions**: none sets the variable [E1]. 15 transcript blocks are mentions too [E5]. Denied in every mode | (c), and (b) for the variable: since #36 `GLOW_LIVE_OK` grants nothing, so setting it opens nothing | Ryan kept the self-approval blocks in #36. Proposal: drop the `GLOW_LIVE_OK=` alternative; keep the startup-file writes and `launchctl setenv` (a). His decision |
| `auto_sync.py check_bands`: the bands that remain | **0** of 210 runs held on a remaining band. All 7 region holds (2 runs, 2026-10-02 and 2026-10-14) were the two rollout holds #30 removed [E4] | (a) | none |
| Runner dry runs while `AUTO_SYNC_APPLY=0` | 40 of 210 runs (2026-09-02 … 09-12 at launch, 24 runs; 2026-09-30 … 10-01, 16 runs). Roster changes waited for a later run [E4] | (b) | #31 (landed, `0fbd63c`) stopped the toggling; the switch stays for emergencies |
| Branch guard (harness `branch_guard.py`) | 4 refusals on main, 2026-10-14, 2 sessions [E6] | (a) | none |
| Monthly work-log chore (#15) | 1 ticket a month, kept out of dispatch (`needs-local`), #15 comment 2026-10-13 [E2] | (a) (invoicing) | none |
| Settings rules that never match: the four dead `:*` allow rules in `.claude/settings.json` (`Bash(node test/:*)`, `Bash(python3 scripts/check_:*)`, `Bash(.venv/bin/python3 scripts/check_:*)`, `Bash(harness-*:*)`), found by the workflow doc's item 5 from the permission docs and the installed matcher, not against a live session | **0** stops counted: no `node` call was denied or rejected in the transcripts [E6]; the board calls ran in `auto` mode, whose classifier approved them anyway (item 5) | (c): `Bash(harness-*:*)` would stall a `default` or `dontAsk` venue | ticket 9 |

## Already removed by #29 / #31 / #36 (historical counts)

- **Hard blocks until a relaunch.** 69 `BLOCKED` gate-log entries under the hook before #36
  (2026-09-03 … 10-14; the 3 later `BLOCKED` entries are today's subagent denials, E1). 13
  assistant messages in 4 sessions asked Ryan to relaunch with the variable set [E1, E6]. Today
  the same 69 commands get 54 prompts and 15 denials (the self-approval mentions) in a main
  session [E1].
- **The cost moved, it did not vanish.** 356 gate-log entries were `ALLOWED` because the session
  had the variable set (2026-09-12 … 10-07). Today the hook asks on 355 of them [E1]. Only 89 of
  the 429 entries are real live writes (sync, translations, static-fields and Salesforce tools'
  `--apply`, 3 `clasp:push`). At today's rate, about 7 of every 10 prompts would be for text
  (**estimate**, from the historical mix). Rows 1 and 2 are what makes per-command prompts cheap.
- **Runner rollout holds.** The 7 holds (question-18 rules, special-event options) are gone with
  #30 [E4].
- **`AUTO_SYNC_APPLY` toggling.** Gone with #31 (landed, `0fbd63c`): no rollout step sets it; it
  stays the emergency off switch.

## Gaps: under-gating, not friction

Each was probed by feeding the command to today's hook as JSON (never run; probe script in
scratch). Mode `default`:

| Command shape | Today | Proposed change | Size / risk |
|---|---|---|---|
| `gh variable -b 1 set X`, `gh secret -b x set X` (a flag with a value before the verb) | **passes** (`gh variable set X -b 1` asks) | words-anywhere rule: a `gh` word, then `variable\|secret` and `set\|delete\|remove` later in the same command, in any order with flags between. Text only, fails closed | S / high |
| `gh workflow -f apply=true run auto-sync.yml` | **passes** (`gh workflow run … -f apply=true` asks) | the same rule for `workflow` + `run\|enable\|disable` and `run rerun` | (same ticket) |
| `sf project deploy resume` | **passes** the hook. Only the settings rule `Bash(sf project deploy resume:*)` asks, and a prefix rule misses `cd x && sf …` | add `resume` to the hook's `project deploy (start\|quick\|validate)` | (same ticket) |
| `gh pr merge 41 --squash` | **passes** (allowed by `Bash(gh pr:*)`) | ask on `gh pr merge`. Since #30 a merge to `main` is a rollout on the runner's next run. `/harness:land` runs in Ryan's session, so the prompt is his go; a dispatched run is denied | (same ticket) |
| `gh api -X PUT repos/o/r/pulls/41/merge`; `gh api -X PUT repos/o/r/contents/glow/sync.py -f branch=main …` (any path); `gh api -X PATCH repos/o/r/git/refs/heads/main …`; `gh api -X POST repos/o/r/merges …` | **all pass** (the `gh api` rule looks only for `actions/`, `dispatches`, `graphql`) | ask on a gh api **write** to any path that changes a branch: `contents/`, `git/` (refs, commits, trees, tags), `merges`, `pulls/N/merge`. A write is a method other than GET or HEAD (`-X`, `--method`) or a field or input (`-f`, `-F`, `--field`, `--raw-field`, `--input`, which make gh send a POST), matched as text like the rest of the gate. Every path, not only `.github/workflows`: since #30 any change on `main` is a rollout on the runner's next run. **Not every non-GET call**, which #36's DoD first asked: issue, comment, label and sub-issue writes change no branch and no live system, and agents make them in dispatched runs (the sub-issue `gh api -X POST` line `harness-board` prints for a hand fix is one); asking would deny those runs for nothing. Reads of these paths change nothing, so they stay ungated (unlike `actions/`, where #36 chose "whatever the method") | (same ticket) |
| `gh api repos/o/r/actions/runs` (a read) | asks: a false positive, accepted in #36 ("whatever the method") | none: Ryan's decision | — |

## Evidence by source

- **[E1] `.claude/live_gate.log`.** Every gate log present at the cut-off, **2026-10-14 22:37
  JST (13:37 UTC**; the log stamps the Mac's local time): the main checkout (417 entries) and the
  worktrees `t-31-…` (6), `t-34-…` (2), `t-37-…` (2) and `t-38-…` (2): 429 entries,
  2026-09-03 15:28 … 2026-10-14 22:13 JST. **Excluded:** the `t-46-…` log, 3 `BLOCKED` entries
  made by this ticket's own subagents while counting (22:15 … 22:34 JST). The logs of worktrees
  that have landed were deleted with them, so they are not counted. Decisions: 356 `ALLOWED`,
  72 `BLOCKED`, 1 `ASKED`. 425 entries are in the format of the hook before #36 (no `mode=`): 356
  `ALLOWED`, 69 `BLOCKED`. The 4 after #36's hook (`e5b04f8`, committed 22:04 JST) are the first
  `ASKED` (a main session, t-37, 22:13) and 3 subagent denials (t-37 1, a self-approval mention;
  t-38 2). By match: `--apply` 359, self-approval 17, `clasp push` 21, `--prune` 6, Sheets write
  API 8, `api.jotform.com` 6, gh switches 5, gh api 6, sf data 1. By kind (a classifier over each
  entry's shell words; heredoc bodies are read as text unless fed to python or a shell):
  - real tool invocations 89;
  - text 199 (heads: `cat` heredoc 120, grep 48, git commit 18, echo 5, harness-board 2, other 6);
  - python heredocs 110 (94 only write files, 12 call the network or a subprocess, 2 test-like, 2 other);
  - self-approval mentions 17;
  - unclassified 13;
  - an API read 1.

  Re-run through today's hook: interactive 412 ask and 17 deny; `bypassPermissions` 429 deny.
- **[E2] The board.** `gh api repos/…/issues/comments` returned 108 comments, 104 of them with
  `<!-- harness -->`. 5 needs-input:
  - #30 ×3: a blocker not yet landed, ultrareview could not see the private repo, the Fable
    limit;
  - #36 ×1: apply the protected guardrail patch;
  - #34 ×1: the Fable limit.

  `harness-work attempt` records (`~/.claude/harness/repos/561908a82410/tickets/*.json`): tests
  25/0, breaker 11 pass/9 fail, code 24/3 (2 were Fable 429s on #30), review 21/5 (#36 ×3, the
  gh api parser; #34 ×2), ci 15/0. 17 dispatched runs (7 headless, 10 bg) in
  `~/.claude/harness/runs/`.
- **[E3] Git.** Counted at `c0592fc` (main merged in), with `e5b04f8`'s count in brackets where
  it differs. Merge commits are left out (`--no-merges`): a merge of main into a ticket branch
  repeats changes its parents already carry.
  - `git log --no-merges --format=%h c0592fc -- .claude/hooks .claude/settings.json | wc -l`:
    12 (the same with merges, and at `e5b04f8`). Since the harness, 2 were applied by Ryan by
    hand (bodies of `459451d`, `e5b04f8`).
  - `git log --no-merges --format=%h --since='2026-09-01 00:00' c0592fc -- docs/RUNBOOK.md`:
    118 commits [116]; 136 with merges [134]. The file's first commit is `916bd1a`
    (2026-09-01 11:49 +0200), so the boundary drops nothing: without `--since` the count is the
    same. Of the 118, 74 [72] also touch `test/` (each commit's `git show --name-only --format=`
    has a line starting `test/`).
  - `git log --format=%h c0592fc -- test/runbook_test.py`: 11 commits [9], 5 [3] of them also
    touching `docs/RUNBOOK.md`; created in `d708da8` (2026-10-09). The two since `e5b04f8`:
    `18532ea` (#33) and `0fbd63c` (#31).
  - `test/runbook_test.py` at `c0592fc`: 40 tests (`grep -c '^    def test_'`) in 9 classes
    (`grep -c '^class '`); a `.md` file is named on 87 lines (`grep -c '\.md'`). At `e5b04f8`:
    32, 7 and 76. Row 8's earlier "52 doc references" could not be reproduced and is replaced
    by the `.md` count.
- **[E4] GitHub Actions.** `gh run list --workflow auto-sync.yml` and `gh run view --log` for all
  210 runs (2026-09-02 … 10-14; 126 repository_dispatch, 41 schedule, 42 workflow_dispatch, 1 push).
  - Region results: 626 in-sync, 122 applied, 1 applied-with-problems, 60 dry-run,
    12 skipped (form DISABLED), 7 attention.
  - ATTENTION printed in 3 runs (8 items).
  - SyncLog was not read: it lives in the live sheet, and no offline copy is in the repository.
- **[E5] Transcripts, live-gate blocks.** The cut-off is E1's, **2026-10-14 13:37 UTC** (the
  transcripts stamp UTC), and this ticket's own sessions (the `t-46-…` project folder) are
  excluded. 1,009 transcript files with a record before the cut-off (32 main sessions, 977
  subagents) under `~/.claude/projects/<this repo>*`. 81 results carry
  `BLOCKED by .claude/hooks/live_gate.sh`; each was joined to its own tool call and
  classified:
  - real 3 (all in main sessions);
  - text 41;
  - no-network scripts 14;
  - network scripts 4;
  - self-approval mentions 15;
  - unclassified 4.

  Harness era (2026-10-13/14): 46 blocks, 33 of them in subagents.
- **[E6] Transcripts, other stops** (error tool results by fixed message text; E5's cut-off,
  2026-10-14 13:37 UTC, and E5's exclusion of this ticket's sessions):
  - in the repository's code:
    - protected_paths 10, all on `data/`, 0 on hooks or settings (results that start with the
      hook's message, the rule the Bash denials below use). 2 more results, in subagents, quote
      the hook's source line (the literal `$REL`) inside a command's output and are not blocks;
    - "Permission to use Bash … denied" 39: 36 name `.env` (the `Read(./.env)` deny rule),
      1 a path outside the project, 2 no cause found (row 4). 2 more results, in subagents,
      quote the message inside a Bash command's output (transcript counting) and are not
      denials;
    - harness branch guard on main 4;
  - Ryan's own answers and fixed rules: Ryan rejected 12, a settings deny rule 4, a built-in
    denial 4;
  - outside the repository's code, so not ranked:
    - the Claude Code auto-mode classifier: no verdict 100 (2026-09-14 … 09-30), denied 25;
    - Claude Code worktree isolation 84;
    - harness role and read-only guards 81, mostly "python opens a file for writing" in
      subagents (2026-10-12 … 14; the harness plugin's, see the workflow doc's draft harness
      issues);
    - connector session expired 35.

  Assistant messages asking Ryan for a hand step (regex over main-session text,
  **estimate**): his go on a live write 102 (14 sessions), run it in his terminal 23 (10),
  relaunch with the variable 13 (4), apply a guardrail patch 11 (1), VPN off 1.

**Not counted:**
- approved permission prompts: Claude Code records only refusals in transcripts;
- `AUTO_SYNC_APPLY` toggles Ryan made in his own terminal: not logged anywhere offline, so only
  their effect is counted (E4's dry runs);
- SyncLog rows: in the live sheet;
- gate-log entries and transcript records after the cut-off (2026-10-14 22:37 JST, 13:37 UTC),
  and this ticket's own `t-46-…` gate log and sessions.

## Proposed tickets

1. **Route message and doc text through files so the live gate sees no flags.** Covers rows 1 and
   3. Already proposed once, so not again here: the workflow doc's item 2
   (`docs/agent/2026-10-workflow.md`, on main from #48) and its proposed ticket "Text that names
   a live command goes through a file" (S, low, no-tests: one paragraph in the live-systems skill
   and RUNBOOK "Live gate (Claude Code)", folded into #37 while #37 is open), with the harness
   side as its draft H2 (`needs-input --question-file`, `epic|task create --title-file`). File
   it once, from there. Rows 1 and 3 are its evidence from the gate log; the one line in
   CLAUDE.md rule 1 (row 1) can go into the same ticket.
2. **Live gate: the gaps from PR #41's review.** Words-anywhere for `gh variable|secret|workflow`,
   `sf project deploy resume`, `gh pr merge`, and a `gh api` write (a method other than GET or
   HEAD, or a field or input) to `contents/`, `git/`, `merges` or `pulls/N/merge`, on any path;
   other `gh api` writes (issues, comments, labels, sub-issues) stay ungated, for the reason in
   the Gaps table. `test/hooks_test.py` first, run against the draft copy
   (`test/hooks_draft/live_gate.sh`, ticket 5: the workflow doc's item 9); Ryan applies it with
   one `cp`. S, high. After ticket 5. It follows #36's (landed) "prompt, don't parse" decision.
   #37's RUNBOOK "Live gate (Claude Code)" would need one more sentence.
3. **Live gate: let read-only pipelines through.** Row 2: `read_only()` accepts `|` between
   segments that each start with `grep head tail cat wc ls cut` (no `sort`, `uniq`, `rg` or
   `sed`), as a separate branch after the single-command exemption, which keeps its words and
   its place above the self-approval check; the new branch needs no self-approval check (row 2
   says why). Tests in `test/hooks_test.py` first: the existing
   `test_a_read_only_command_that_only_mentions_a_live_flag_passes` and
   `test_a_read_only_word_is_no_cover_for_a_second_command` stay green unchanged; new: a
   pipeline of listed words that mentions a flag (`grep -n -- --apply X | head`) passes silently
   in every mode and in a subagent; a pipeline with a word off the list (`sort -o`, `tee`, `sed`,
   `sh`) or with `>` is gated as today: it asks in an interactive session and is denied in a
   subagent. Developed on the same draft copy as ticket 2 (ticket 5: the workflow doc's item 9).
   S, high. After ticket 5; it can share a PR with ticket 2 (same file, one `cp`). Builds on
   #36 (landed).
4. **Self-approval: drop the `GLOW_LIVE_OK=` text rule.** Below the top 10. Keep the
   startup-file and `launchctl` rules. S, high. **Needs Ryan's decision**: #36 kept the block on
   purpose.
5. **Hook tests run against a draft copy; Ryan applies once.** Row 5. The workflow doc's item 9
   and its proposed ticket of the same name, which left the choice to this ticket ("Overlaps
   #46: decide there"): decided here, Ryan 2026-10-15, in place of the apply script and staging
   folder this doc proposed before. `test/hooks_test.py` takes the script under test from
   `HOOK_UNDER_TEST` (default `.claude/hooks/<name>`); a guardrail ticket's coder edits
   `test/hooks_draft/<name>` and every review round runs against it; Ryan copies the reviewed
   draft over the real hook once (one `cp`, one `git diff`); a test checks that the draft and the
   real hook are identical before the PR is ready. Tickets 2 and 3 use it, so it goes first. Not
   checked here: whether the harness role guard counts a file under `test/` as a test the coder
   may not edit; check that before the ticket starts. M, high (it changes how the gate itself is
   tested), needs-local.
6. **Plans only for hand rollouts.** Row 7: CLAUDE.md conventions and `docs/templates/plan.md`.
   S, low. Unblocked: #31 landed (`0fbd63c`) and the template's Rollout now lists hand steps only;
   this ticket builds on it (when a plan is needed at all: CLAUDE.md and the template's header).
7. **Prose pins: keep commands, ids and headings, drop sentence quotes of plans that ran.**
   Row 8. M, low. Unblocked: #31 landed (`0fbd63c`) with `RosterRepairRunbook` and
   `SameNameRunbook` unchanged; the file now has 40 tests in 9 classes [E3].
8. **Question for Ryan: does the disabled U.S form follow every form change?** Row 9. If not,
   the `--disabled-ok` hand step leaves "Add a type". S, low. Unblocked: #31 landed; the step is
   RUNBOOK "Special events", **Add a type** step 4.
9. **settings: replace the four dead `:*` allow rules.** The "Settings rules that never match"
   row (below the top 10). Adopted from the workflow doc's item 5, which left it to this ticket
   ("#46 already lists dead settings rules"). In `.claude/settings.json`:
   - `Bash(node test/:*)` → `Bash(node test/*)`;
   - `Bash(python3 scripts/check_:*)` → `Bash(python3 scripts/check_*)`;
   - `Bash(.venv/bin/python3 scripts/check_:*)` → `Bash(.venv/bin/python3 scripts/check_*)`;
   - `Bash(harness-*:*)` → `Bash(harness-board *)`, `Bash(harness-work *)`, `Bash(harness-pr *)`,
     `Bash(harness-red *)`, `Bash(harness-worklog *)`.

   A patch Ryan applies (`protected_paths.sh` guards the file), then `make check`. S, low,
   no-tests, needs-local: allow rules only, each replacement allows what its dead rule was
   written for, and none reaches `data/` or `.env`. Item 5's finding is from the permission docs
   and the installed matcher, not a live session: check one `harness-board` call in a `default`
   session after the apply.
10. **The `.env` line.** Row 4: `Read(./.env)` stays; one sentence in CLAUDE.md rule 2: the tools
    load the key themselves and refuse without it (`glow/cli.py`), so no command names `.env`.
    Still no `cat`/`head` allows, for the `data/` reason. S, low, no-tests.

Open tickets on 2026-10-15: #34 and #37 (#31, #33, #36 and #48 are closed). Ticket 1 folds into
#37 while it is open (the workflow doc's item 2); ticket 2 adds a sentence to #37's RUNBOOK
section. No proposal touches #33 (landed) or #34. Their changes (form_status hints, the rendered
verify) remove none of the stops counted here.
