# What stops Claude from working automatically (2026-10)

Ticket #46 (epic #45), counted 2026-10-14. The question was which legacy code and guardrails
stop Claude most often, and what each stop costs Ryan by hand. The ranking is by what is
**still live in the code at `e5b04f8`**, after #30 and #36. Stops that #29/#36 already removed are
listed apart.

Counts come from scripts that print counts only (in this session's scratch directory, not
committed). No command text was copied, because command text can carry a girl's name. Every
number names its source. Anything marked **estimate** says what it is based on.

## Ranked stops (still live)

Hand work is per stop. Classes: **(a)** protects against something real, keep it;
**(b)** now covered by PR review and tests, a candidate to remove; **(c)** a false positive of
the mechanism, a candidate to narrow.

| # | Stop (code) | Count (source) | Hand work per stop | Class | Smallest change | Size / risk |
|---|---|---|---|---|---|---|
| 1 | `live_gate.sh`: a live flag that sits only in **text**: a heredoc body (`cat > doc <<EOF`, `git commit -F -`), a commit message, a `harness-board` question | gate log: 199 of 429 entries are text and 94 more are no-network python heredocs that edit files. Transcripts: 21 heredoc bodies, 1 commit message, 1 board question among 83 blocks [E1, E5] | main session: today, one approval prompt for Ryan (estimate 15–30 s each: read the reason, answer). Subagent or dispatched run: **denied**, so 1–3 extra tool calls to rephrase, or the stage stalls | (c) | No hook change ("prompt, don't parse" stands). Text goes through files: `git commit -F <file>`, `gh pr/issue --body-file`, docs through Write/Edit, never `cat > file <<EOF`. One line in CLAUDE.md rule 1 and in the live-systems skill's "The gate" | S / low |
| 2 | `live_gate.sh`: a **read-only pipeline** that mentions a flag (`grep -n -- --apply X \| head`, `sed -n`, `echo`) | transcripts: grep 10, git grep 1, sed 3, echo 3 of 83 blocks. Gate log: grep 48, echo 5 [E1, E5] | as #1. The exemption covers a read-only command only when it stands alone, so one pipe makes it ask, or deny in a subagent | (c) | In `read_only()`, accept `\|` between segments when every segment starts with a word that cannot write a file: `grep head tail cat wc ls cut`. Not `sort` (`sort -o F`), `uniq` (`uniq IN OUT`), `rg` (`--pre` runs a program) or `sed` (`w`, `-i`). Move the self-approval check ahead of the exemption: today `read_only` exits before the `SELF` refusal (`live_gate.sh`, `read_only && exit 0` sits above `if has "$SELF"`), so a passing pipeline must not skip it. Every other operator still asks, and so does any word not on the list. `sed` and `echo` are not on it, so their 6 transcript stops (sed 3, echo 3) remain; the change covers at most the 11 grep ones | S / high (gate, protected file) |
| 3 | `live_gate.sh` **subagent rule**: any match in a subagent is denied, mentions included | transcripts, harness era (2026-10-13/14, 2 days): 35 of 48 blocks came from subagents. 32 of the 35 are still denied by today's hook (re-run on the same commands; 3 now pass); none was a real write [E5] | the subagent rewrites or gives up. The orchestrator or Ryan picks it up | (a) for real writes; the mentions are #1 and #2 | Nothing on its own: #1 and #2 take away the mentions. Keep the rule: a live write never comes from a subagent | — |
| 4 | `.claude/settings.json` deny rule `Read(./.env)`: a Bash command that names `.env` (to see whether the key file exists, or to read or source it) is denied in every mode, main sessions too | transcripts: 39 "Permission to use Bash … denied", 32 of them in subagents. **36 of the 39 name `.env` itself** (first words of the denied part: head 20, ls 7, grep 2, others 7); 1 names a path outside the project; 2 have no cause found. Not a missing allow rule: `Bash(ls:*)` and `Bash(wc:*)` are allowed, and all 7 `ls` and the 1 `wc` denials name `.env` [E6] | 1–2 extra tool calls (estimate); the agent drops the check or asks | (a): it keeps the API key out of transcripts (CLAUDE.md rule 2) | Keep the rule. One line in the agent prompts (#48): the tools load the key themselves and refuse without it (`glow/cli.py`), so nothing needs to name `.env`. Do **not** add `Bash(cat:*)`/`Bash(head:*)` either: they would read `data/` silently, past the `Read(./data/**)` ask. Remove the dead rules (the "Settings rules that never match" row below the top 10) | S / low |
| 5 | `protected_paths.sh` on `.claude/hooks/*` and `.claude/settings*.json`: Ryan applies every guardrail change by hand | 2 tickets since 2026-10-13 (#3 "Ryan's edit", #36 "Ryan applied the hook and settings", git log bodies of `459451d`, `e5b04f8`). #36: 1 needs-input; 11 assistant messages in one session asked Ryan to apply a guardrail patch (**estimate**, a regex) [E2, E6]. Transcripts: 2 blocks on hooks [E6] | high: Ryan reviews the diff, copies the files and re-runs verify, every review round (estimate 10–20 min per round, from #36: needs-input 03:20Z, PR 03:42Z) | (a) | Keep the block. Make the hand step one command: `scripts/apply_guardrails.sh <worktree>`. Ryan runs it; it prints the diff of `.guardrails/` against `.claude/`, asks y/n, copies, removes `.guardrails/` and runs `test/hooks_test.py`. `protected_paths.sh` protects the script's own path too: `scripts/` is not protected today, so an agent could edit the script Ryan runs (and the diff it shows him) and get around the block this row keeps. That makes it a hook change, applied by hand once | S / high (adds a protected path) |
| 6 | `protected_paths.sh` on `data/`: new work files (a Salesforce metadata package, a helper script) under `data/<dated>/` | transcripts: 10 blocks in 8 sessions, 2026-09-28 … 2026-10-14 [E6] | 1–3 tool calls: the file is generated by a script instead (estimate). No Ryan time | (a) for existing exports; (c) for new work files | No hook change (`data/` holds minors' names). The Salesforce metadata skill #48 proposes says builds are generated by a script or kept in the scratchpad | S / low |
| 7 | Plan document for every change with a live rollout (CLAUDE.md conventions, `docs/templates/plan.md`, `docs_index.py --check`) | 44 plans, all added since 2026-09-01: `git log --diff-filter=A --name-only --format= -- docs/plans`, README left out, unique paths: 44, all still on disk; `docs_index.py --check`: "ok (44 plans, 11 intents)". (`--since=2026-09-01` gives 42: it drops the 2 plans added on 2026-09-01 itself in `4eee550`.) 0 check failures found in transcripts [E6] | authoring, not a stop: about one plan per working day (estimate, from the count) | (b) for a generated form change whose rollout is now the merge (#30); (a) for hand rollouts | A plan only when hand steps remain (the template, a disabled form, Salesforce, Apps Script). A generated change carries `Live:` in its PR. One line in CLAUDE.md and the template | S / low |
| 8 | Prose-pinning tests: `test/runbook_test.py` (32 tests in 7 classes; 52 doc references), `special_events_test.py` `RunbookQuotes`/`IdgDocs`, `doc_refs_test.py` | `runbook_test.py` has changed in 9 commits since it was created on 2026-10-09. The breaker "cheat passed" twice on doc tests only (#30 Resolution); #31 breaker fail ×2 (`harness-work` attempts) [E2, E3]. Transcripts: 1 failing result named a runbook class [E6] | each doc ticket rewrites pinned quotes (#31 updates 3, and must keep 4 classes "unchanged"). Breaker rounds cost tokens, not Ryan's time | (b) for sentence quotes of historical plans; (a) for pinned commands, form ids and headings | Keep the pins on commands, ids and headings (`doc_refs` already guards headings). Drop sentence-level quotes of plans that ran (`RosterRepairRunbook`, `SameNameRunbook`) | M / low |
| 9 | `sync_attendance_form.py` refusal flags: `--q5-change-ok`, `--same-name-switch`, `--disabled-ok`, `--prune` on a form with submissions; `auto_sync.py --min-active` | transcripts, failed commands that name the flag: q5 2, same-name 3, disabled 2, prune 3; min-active/floor 8 (**estimate**, a loose marker) [E6]. Gate log, real applies that carried a flag: `--same-name-switch` 4, `--disabled-ok` 1 [E1] | one re-run with the flag after reading why (a minute, estimate). On Ryan's go | (a) | Keep them all. One question: does the disabled U.S form still need every form change by hand (`--disabled-ok`, #31's "Add a type" step 4)? If not, that hand step goes | S / low (a question first) |
| 10 | `--vpn-off` (`glow/salesforce.py require_vpn_off`) | transcripts: 5 failed commands with the VPN marker (**estimate**, the marker also matches other text); gate log: 13 real applies carried `--vpn-off` [E1, E6] | one re-run, after Ryan confirms the VPN is off | (a) | Keep. Salesforce freezes the user (CLAUDE.md rule 12) | — |

Below the top 10, still live but rarely or never stopping work:

| Stop | Count (source) | Class | Change |
|---|---|---|---|
| `live_gate.sh` self-approval rule: the `GLOW_LIVE_OK=` text (and startup-file writes) | 17 gate-log entries, **all mentions**: none sets the variable [E1]. 16 transcript blocks are mentions too (one is this investigation's own script) [E5]. Denied in every mode | (c), and (b) for the variable: since #36 `GLOW_LIVE_OK` grants nothing, so setting it opens nothing | Ryan kept the self-approval blocks in #36. Proposal: drop the `GLOW_LIVE_OK=` alternative; keep the startup-file writes and `launchctl setenv` (a). His decision |
| `auto_sync.py check_bands`: the bands that remain | **0** of 210 runs held on a remaining band. All 7 region holds (2 runs, 2026-10-02 and 2026-10-14) were the two rollout holds #30 removed [E4] | (a) | none |
| Runner dry runs while `AUTO_SYNC_APPLY=0` | 40 of 210 runs (2026-09-02 … 09-12 at launch, 24 runs; 2026-09-30 … 10-01, 16 runs). Roster changes waited for a later run [E4] | (b) | #31 (in review) stops the toggling; the switch stays for emergencies |
| Branch guard (harness `branch_guard.py`) | 4 refusals on main, 2026-10-14, 2 sessions [E6] | (a) | none |
| Monthly work-log chore (#15) | 1 ticket a month, kept out of dispatch (`needs-local`), #15 comment 2026-10-13 [E2] | (a) (invoicing) | none |
| Settings rules that never match (`Bash(node test/:*)`, the old `:*` forms) | **0** stops: no `node` call was denied or rejected in the transcripts [E6]. Not tested here whether they match | (c), cleanup only | in #48 ("dead `:*` rules") |

## Already removed by #29 / #36 (historical counts)

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
- **`AUTO_SYNC_APPLY` toggling.** It goes with #31 (in review).

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
- **[E3] Git.** `git log -- .claude/hooks .claude/settings.json`: 12 commits. Since the
  harness, 2 were applied by Ryan by hand (bodies of `459451d`, `e5b04f8`). `docs/RUNBOOK.md`:
  131 commits since 2026-09-01, 64 of them touching a test. `test/runbook_test.py`: 9 commits,
  3 of them with the RUNBOOK.
- **[E4] GitHub Actions.** `gh run list --workflow auto-sync.yml` and `gh run view --log` for all
  210 runs (2026-09-02 … 10-14; 126 repository_dispatch, 41 schedule, 42 workflow_dispatch, 1 push).
  - Region results: 626 in-sync, 122 applied, 1 applied-with-problems, 60 dry-run,
    12 skipped (form DISABLED), 7 attention.
  - ATTENTION printed in 3 runs (8 items).
  - SyncLog was not read: it lives in the live sheet, and no offline copy is in the repository.
- **[E5] Transcripts, live-gate blocks.** 1,064 jsonl files (33 main sessions, 1,031 subagents)
  under `~/.claude/projects/<this repo>*`. 83 results carry
  `BLOCKED by .claude/hooks/live_gate.sh`; each was joined to its own tool call and
  classified:
  - real 3 (all in main sessions);
  - text 41;
  - no-network scripts 14;
  - network scripts 4;
  - self-approval mentions 16;
  - unclassified 5.

  Harness era (2026-10-13/14): 48 blocks, 35 of them in subagents.
- **[E6] Transcripts, other stops** (error tool results by fixed message text):
  - in the repository's code:
    - protected_paths 12 (`data/` 10, hooks 2);
    - "Permission to use Bash … denied" 39: 36 name `.env` (the `Read(./.env)` deny rule),
      1 a path outside the project, 2 no cause found (row 4);
    - harness branch guard on main 4;
  - Ryan's own answers and fixed rules: Ryan rejected 12, a settings deny rule 4, a built-in
    denial 4;
  - outside the repository's code, so not ranked:
    - the Claude Code auto-mode classifier: no verdict 100 (2026-09-14 … 09-30), denied 23;
    - Claude Code worktree isolation 84;
    - harness role and read-only guards 80, mostly "python opens a file for writing" in
      subagents (2026-10-12 … 14; #48's harness side);
    - connector session expired 35.

  Assistant messages asking Ryan for a hand step (regex over main-session text,
  **estimate**): his go on a live write 102 (14 sessions), run it in his terminal 23 (10),
  relaunch with the variable 13 (4), apply a guardrail patch 11 (1), VPN off 1.

**Not counted:**
- approved permission prompts: Claude Code records only refusals in transcripts;
- `AUTO_SYNC_APPLY` toggles Ryan made in his own terminal: not logged anywhere offline, so only
  their effect is counted (E4's dry runs);
- SyncLog rows: in the live sheet;
- gate-log entries after the E1 cut-off (2026-10-14 22:37 JST), and the `t-46-…` log (this
  ticket's own agents).

## Proposed tickets

1. **Route message and doc text through files so the live gate sees no flags.** Covers rows 1 and
   3. Commits use `-F`, PR and issue text `--body-file`, board comments
   `harness-board comment --body-file`, docs Write/Edit. A board question cannot go through a
   file today: `harness-board needs-input` takes only `--question TEXT` (plus
   `--evidence-file`). So the question stays short and flag-free and any flag text goes into the
   evidence file; a `--question-file` would be a harness-plugin change (an item for #48). Add
   CLAUDE.md rule 1 (one line), the live-systems skill "The gate", and the harness agents'
   prompts. S, low. Overlaps #37: it edits "The gate" in the same skill, so do this after #37
   lands or fold it in. Also #48 (agent prompts).
2. **Live gate: the gaps from PR #41's review.** Words-anywhere for `gh variable|secret|workflow`,
   `sf project deploy resume`, `gh pr merge`, and a `gh api` write (a method other than GET or
   HEAD, or a field or input) to `contents/`, `git/`, `merges` or `pulls/N/merge`, on any path;
   other `gh api` writes (issues, comments, labels, sub-issues) stay ungated, for the reason in
   the Gaps table. `test/hooks_test.py` first; staged in `.guardrails/`, applied by
   Ryan. S, high. Overlaps #36: it follows that ticket's "prompt, don't parse" decision. #37's
   RUNBOOK "Live gate (Claude Code)" would need one more sentence.
3. **Live gate: let read-only pipelines through.** Row 2: `read_only()` accepts `|` between
   segments that each start with `grep head tail cat wc ls cut` (no `sort`, `uniq`, `rg` or
   `sed`), and the self-approval check moves ahead of the exemption; everything else unchanged. S, high. It can share a PR with ticket 2 (same
   file, same hand apply). Overlaps #36.
4. **Self-approval: drop the `GLOW_LIVE_OK=` text rule.** Below the top 10. Keep the
   startup-file and `launchctl` rules. S, high. **Needs Ryan's decision**: #36 kept the block on
   purpose.
5. **One command to apply staged guardrail changes.** Row 5: `scripts/apply_guardrails.sh`, run
   by Ryan, with its own path added to `protected_paths.sh` so no agent can change what he runs.
   S, high (a protected-path change, staged in `.guardrails/` and applied by hand once). Overlaps #48 ("hand steps for protected files").
6. **Plans only for hand rollouts.** Row 7: CLAUDE.md conventions and `docs/templates/plan.md`.
   S, low. Overlaps #31, which rewrites the template's Rollout guidance: do it after #31 lands.
7. **Prose pins: keep commands, ids and headings, drop sentence quotes of plans that ran.**
   Row 8. M, low. Overlaps #31, which updates the same pinned quotes and keeps
   `RosterRepairRunbook` and `SameNameRunbook` unchanged: do it after #31 lands.
8. **Question for Ryan: does the disabled U.S form follow every form change?** Row 9. If not,
   the `--disabled-ok` hand step leaves "Add a type". S, low. Overlaps #31 (its step 4).
9. **Settings cleanup and the `.env` line.** The "Settings rules that never match" row (below
   the top 10): dead rules out. Row 4: `Read(./.env)` stays; agent prompts say the tools load the
   key themselves, so nothing names `.env`; still no `cat`/`head` allows, for the `data/` reason.
   S, low. Overlaps #48 ("Settings: dead `:*` rules, ask and allow lists"): fold it in
   there.

No proposal touches #33 or #34. Their changes (form_status hints, the rendered verify) remove
none of the stops counted here.
