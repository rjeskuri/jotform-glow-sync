# Automating the routine asks: the tickets and their order (2026-10)

Written 2026-10-28 on `claude/wonderful-planck-nv9syw` for epic #159, from a read-only survey of
this repository (the skills, hooks, settings, workflows, `docs/RUNBOOK.md`, `docs/BACKLOG.md`,
the two October analyses `2026-10-workflow.md` and `2026-10-maintainability.md`, the plans and
the work log) and the open board on 2026-10-28. Nothing under `data/`, `backups/` or
`credentials/` was opened. Nothing was applied: the tickets were created as `status:proposed`
and this document was committed; Ryan promotes.

**Summary.** The two October analyses had already found most of the repetitive work and
proposed the fixes; almost none of the proposals had been filed. Epic #159 files them as 19
tickets in three groups: scripts that replace the four command-list skills (so the mechanical
steps cost no tokens), read-only checks that move onto the GitHub Actions runner (so nobody runs
a session to find out whether anything is wrong), and less text for every session to read. Two
decisions that are not tooling ride along because they carry dates. Everything is free: the
standard library, Make, the existing Actions minutes, Claude Code skills and hooks.

**The order in one line.** Finish the live work in flight first (#146, #153, #157), then the two
cheapest clean-ups (#173, the handoff refresh through #15), then the scripts in dependency order
(#160, #161, #162, #165, #167, #168), then the runner checks (#169, #170, #171, #172), then the
decisions (#163, #177) and what follows them (#164, #166), and the document trims last (#175,
#174), after the dashboard work has stopped changing the RUNBOOK. #176 waits for #146; #178 is
its own rollout and goes wherever a quiet week is.

## The board on 2026-10-28

Open before this epic, from `gh issue list --state open` through the GitHub API:

| # | Title (short) | Status | What it means for the order |
|---|---|---|---|
| 157 | Deploy #102's four timing reports live | in-review | A live Salesforce rollout; lands first. |
| 153 | Re-send the 12 girls' Duplicate batches live | in-progress | A live Salesforce write; lands first. |
| 146 | Live gate: auto-approve backed-up writes; deletes still ask | in-progress, priority | Changes `live_gate.sh` (PR #154). #176 and the backup check in #166 build on it. |
| 103 | Submission timing on the Jotform Attendance dashboard | in-progress | Keeps changing the RUNBOOK's dashboard sections: #174 waits for it. |
| 152 | Item 16 on the GLOW Club Training dashboard | ready | Small; unrelated. |
| 148 | Session notes in both e-mails on all five forms | proposed | Ryan in the builder; unrelated. |
| 144 | Photo mover: remove the emptied subfolders | blocked | Related to the storage decision #177 only. |
| 119, 107 | On-time definition; report e-mails to stakeholders | blocked | Wait on the #68 epic; unrelated. |
| 99, 98, 97, 96 | Club renames in GLOW's format | blocked | A large hand rollout; #166 (form rollout) would carry its form side if it lands first. |
| 93, 68, 6 | Epics: staff-meeting upgrades; Salesforce reports; harness v2 | ready | #159 is a sibling of #6, not a child: it is this repository's tooling, not the harness's. |
| 83, 82, 81 | Interactive dashboard fixes | blocked | Unrelated. |
| 15 | Commit the work log and handoff, 2026-10 | blocked | The month's chore; #167 makes its refreshes one command. Land it at month end as the RUNBOOK says. |

## The new tickets

All under epic #159, all `status:proposed`. "After" is the dependency; GitHub's blocked-by links
could not be set from the cloud session, so Ryan adds them with
`gh issue edit N --add-blocked-by M` (or `harness-board` on the next edit) if the board should
enforce them; the bodies name them.

| # | Title (short) | Type, size, risk | After | Group |
|---|---|---|---|---|
| 160 | `tools/ops.py`: exports, status, preview | task M, low | nothing | scripts |
| 161 | runner state: last runs, ATTENTION, SyncLog | task S, low | 160 | scripts |
| 162 | `make sf-monthly`: the monthly Salesforce checks | task M, low, needs-local | nothing | scripts |
| 163 | Decide: Salesforce metadata in git or under `data/` | chore S, no-tests, needs-local | nothing (a question to Ryan) | decision |
| 164 | `tools/sf_package.py` and `/sf-metadata` | task M, low | 163 | scripts |
| 165 | `scripts/land_checks.sh` | task S, low | nothing | scripts |
| 166 | `tools/form_rollout.py` and `/form-rollout` | task M, high, needs-local | 160, 161; #146 for the backup rule | scripts |
| 167 | Work log: Stop hook and chore refresh script | task S, low, needs-local | nothing; pairs with #15 | scripts |
| 168 | `scripts/appsscript_diff.sh` and the deploy tag | task S, low, needs-local | nothing; the tag waits for Ryan's push | scripts |
| 169 | Runner: names-dictionary audit every run | task S, low | nothing | runner |
| 170 | Runner: daily delivery check | task M, low | nothing | runner |
| 171 | Runner: runtime build watch | task S, low | nothing | runner |
| 172 | Workflow: monthly checks on the 1st | task S, low | 162 | runner |
| 173 | settings: dead rules out | chore S, no-tests, needs-local | nothing; Ryan applies | reading |
| 174 | RUNBOOK: history to plans, Routine index | chore M, no-tests | 175; after #103 and the #68 children | reading |
| 175 | Tests: drop the sentence pins | chore S, low | nothing | reading |
| 176 | Live gate: pipelines pass, text through files | task S, high, needs-local | #146 | reading |
| 177 | Decide Jotform storage before the 50 % line | chore S, high, no-tests | nothing; by 2026-12-01 | decision |
| 178 | Runner: Python 3.12 and a lockfile | task M, high | nothing; a quiet week | runner |

## The order, and why

The ranking is by tokens or minutes saved per week against effort and risk, with two
constraints: nothing touches a file a live ticket is changing, and nothing moves a document that
open work is still rewriting.

### Phase 0: land what is in flight (this week)

#157, #153 and #146 are live rollouts or a guardrail change; they land before anything here
starts. #146 in particular: #166 relies on its backup rule, #176 edits the same hook, and
starting either beside it means a merge of `live_gate.sh` by hand.

### Phase 1: the cheap clean-ups (same week; an hour)

1. **#173** (settings). Three rules name files that no longer exist and four never match. Each is
   a prompt or a denial in every session. Ryan applies the patch; nothing depends on it.
2. **#15 with #167's first half**: refresh `docs/agent/handoff.md`, which still carries the
   2026-10-13 next steps that the harness brief loads into every session, and commit the work
   log, which stops at 2026-10-13 in git. The Stop hook of #167 is a settings line Ryan applies at
   the same time; the refresh script can follow in the same ticket or the next chore.

### Phase 2: the scripts, in dependency order (weeks 1 to 3)

3. **#160** `tools/ops.py`. The common root: #161 and #166 call it, and `form-status` and
   `sync-preview` shrink to one line each. Read-only, no live risk, the largest per-session
   saving.
4. **#162** `make sf-monthly`. Independent of #160; replaces re-reading seven RUNBOOK sections
   every month. Needs the Mac for the CLI; the tests are offline.
5. **#161** runner state, once #160 is in.
6. **#165** `scripts/land_checks.sh`. Runs on every ticket from then on, so the sooner the more
   it saves; independent.
7. **#168** the Apps Script diff script; the tag half waits for Ryan's next `clasp push` (the
   2026-10-09 changes were still undeployed on 2026-10-15).
8. **#167**'s second half, the chore refresh script, if it did not ride with #15.

### Phase 3: the runner checks (weeks 2 to 4; each is one `auto_sync.py` change)

9. **#169** the names-dictionary audit on every run (BACKLOG 62 and 30). Smallest; the land is
   the rollout.
10. **#171** the runtime build watch (BACKLOG 64). Small; the same shape as #169, so the same
    ticket worktree can do both in sequence, never in one PR.
11. **#170** the daily delivery check. The one alarm for a silent integration lapse, risk 2 of
    the maintainability ranking; medium because it joins two systems.
12. **#172** the monthly checks on a schedule, once #162 is in. Decides whether the CLI-only
    check moves to the client-credentials path.

### Phase 4: the decisions and what they unblock (ask now, build when answered)

13. **#163** where the Salesforce metadata lives. A question to Ryan; ask it in week 1 so the
    answer is in before #164 is reached. The maintainability doc recommends git.
14. **#177** Jotform storage. A question to Ryan and the CEO with a date: 2026-12-01, before the
    50 % line in mid-December. Not tooling; filed for the deadline.
15. **#164** the package builder and `/sf-metadata`, after #163. The dominant work of the last
    two weeks was this chain by hand; once the Salesforce epic #68 picks up again it pays back
    on every report change.
16. **#166** the form rollout, after #160, #161 and #146. Risk high because its stages write to
    the template and the disabled form; keep it for a week with a real form change to roll out,
    and write that change's plan as the first use.

### Phase 5: the trims (after #103 and the #68 children stop rewriting the RUNBOOK)

17. **#175** drop the sentence pins first, so the trim does not fight the tests.
18. **#174** the RUNBOOK trim and the Routine index. Last on purpose: the dashboard sections are
    the ones still changing, and the index lists the commands the earlier tickets add.

### Any quiet week

- **#176** live-gate pipelines and the text rule, after #146 has landed and its hook tests are
  green. Protected path; Ryan lands it.
- **#178** Python 3.12 and the lockfile. Its own rollout plan with a watched morning run; pick a
  week with no other change to the runner.
  One known blocker, found while checking this document: on Python 3.13 the suite has 18 errors
  in `test/sf_record_flags_test.py` (a regex with an inline flag not at the start of the
  pattern, an error since 3.11 and a warning on the 3.10 CI runs). #178 fixes it first.

## What was deliberately not filed

- A ticket for the stale handoff: #15 is that ticket.
- `reconcile-count` (workflow item 16) and `/land-checks` re-reading open tickets (item 13): the
  first is a skill of prose with no mechanical step to script; the second is one line in #165.
- BACKLOG 26 (the monthly three-way reconciliation): #170 is its daily two-way half; the Roster
  side can be a later ticket once #170 has run for a month.
- A RUNBOOK "Routine" section on its own (maintainability T7): folded into #174.
- Anything in the harness plugin (workflow items 3, 4, 6, 7, 8, 11, 14, 15, 17): those are
  `rjeskuri/Harness` tickets, not this repository's.

## Result

_To be written when the epic closes: the order actually followed, what each ticket saved, and
what was dropped._
