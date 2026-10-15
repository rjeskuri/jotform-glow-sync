# Maintainability risks going forward (2026-10)

Ticket #47, epic #45 (steady state). Written 2026-10-15 on `t/47-identify-the-maintainability-r`,
offline: no Jotform, Salesforce or Google call, nothing under `data/`, `backups/` or
`credentials/` read (what lives there is taken from what the tracked docs and code say).
A proposal only: nothing here changes code, docs or a live system. Siblings: #46 (legacy code
and guardrails that stop Claude working automatically: `docs/agent/2026-10-friction.md`) and
#48 (skills, agents, settings, harness: `docs/agent/2026-10-workflow.md`). Where an item
touches their scope it says so and leaves it to them.

## Summary

**Top 5 risks** (the next six months, to 2027-04-15):

1. **Jotform's upload space runs out.** The Group Photo is required. At October's pace the
   account passes 50 % of Silver's 10 GiB around mid-December 2026 and reaches the cap around
   mid-March 2027 (BACKLOG 68). Nobody has decided Gold or a retention policy yet.
2. **The live Apps Script is not the code in `appsscript/`.** The 15 commits of 2026-10-09
   wait for a push (`docs/RUNBOOK.md:2071`). No `appsscript-deployed-*` tag exists, locally or
   on `origin`, so the deployed commit is unknown to git. The rollback in the deploy skill
   starts from that tag.
3. **Jotform's runtime changes weekly, and our emulation of it is pinned.** Six builds have
   been compared (`glow/translation_lookup.py:68-71`). At least three builds served since
   2026-10-06 have not (BACKLOG 64).
4. **An integration can lapse without an alarm.** The Jotform → Salesforce connection, the
   Drive token, the sheet's dispatch token and the CLI login can each stop working silently.
   No automated check compares Jotform submissions with Salesforce batches.
5. **The Salesforce source lives only in gitignored `data/` on one Mac.** This covers the
   processor's Apex, the dashboard generator and the permission sets (BACKLOG 82). #35 needs
   to change that dashboard now.

**Top 3 actions:**

1. **Book the storage decision before the 50 % line.** Ryan and the CEO choose Gold or a
   retention policy by 2026-12-01 (T1).
2. **Deploy and tag the Apps Script.** Ryan's push, the tag, and a `/land-checks` line that
   says when `appsscript/` is ahead of the last tag (T2).
3. **Put the Salesforce metadata in git, metadata only.** Do it before #35's dashboard change
   lands (T4).

The next three are cheap: compare the uncompared runtime builds (T3), sweep the stale RUNBOOK
status lines (T6), and retire `tools/fix_module_values.py` after 2026-11-01 (T8).

## How the items are scored

- **Likelihood (L)**: will it break or bite within six months? 1 = unlikely, 2 = plausible,
  3 = expected or already happening.
- **Cost (C)**: what happens when it does? 1 = an hour of fixing. 2 = a day, or a wrong
  output someone must notice. 3 = attendance stops reaching Salesforce, minors' data is at
  risk, or a live system cannot be rolled back.
- **Effort (E)**: what does the fix take? 1 = under half a day, or one decision by Ryan.
  2 = a ticket of size S or M. 3 = size L, or several tickets.
- **Rank**: L × C, highest first. Ties go to the lower effort first, then the higher cost.

## Ranked list

| # | Item | L | C | E | L×C | Proposal |
|---|---|---|---|---|---|---|
| 1 | A. Jotform upload space reaches the cap | 3 | 3 | 1 | 9 | T1 |
| 2 | B. Live Apps Script ≠ `appsscript/`; deploy not recorded | 3 | 2 | 1 | 6 | T2 |
| 3 | C. Jotform runtime builds not compared | 3 | 2 | 1 | 6 | T3 |
| 4 | D. An integration lapses silently | 2 | 3 | 2 | 6 | T5 |
| 5 | E. Salesforce metadata only in `data/` | 2 | 3 | 2 | 6 | T4 |
| 6 | F. RUNBOOK size and stale Status lines | 3 | 2 | 2 | 6 | T6, T7 |
| 7 | G. Salesforce CLI unpinned; tools read its JSON | 2 | 2 | 1 | 4 | T11 |
| 8 | H. Harness plugin unpinned; the invoice runs on it | 2 | 2 | 1 | 4 | T11 (#48) |
| 9 | I. Python 3.10 EOL, unpinned Google libraries on the live runner | 2 | 2 | 2 | 4 | T10 |
| 10 | J. Python ↔ Apps Script duplicated rules | 2 | 2 | 3 | 4 | T9 shrinks it |
| 11 | K. `data/` and `backups/` exist on one Mac only | 1 | 3 | 1 | 3 | T13 |
| 12 | L. OAuth scopes not pinned in the manifest | 1 | 3 | 1 | 3 | none (guarded) |
| 13 | M. `hooks_test.py` is most of the verify run | 3 | 1 | 1 | 3 | T12 |
| 14 | N. Legacy enrollment path and the Rebuild menu item | 1 | 3 | 2 | 3 | T9 |
| 15 | O. Tests that pin prose | 3 | 1 | 2 | 3 | T7 (#46) |
| 16 | P. Two backlogs: BACKLOG.md and the board | 3 | 1 | 2 | 3 | T14 |
| 17 | Q. One-off tools and one-time menu items | 2 | 1 | 1 | 2 | T8 |
| 18 | R. Plan and intent statuses drift | 2 | 1 | 1 | 2 | T6 |
| 19 | S. Node 18 + clasp 2.4.2 | 1 | 2 | 2 | 2 | watch |
| 20 | T. Dashboard Partner filter at 49 of 50; two partner lists | 1 | 2 | 2 | 2 | watch |
| 21 | V. DECISIONS.md growth | 1 | 1 | 1 | 1 | none |
| 22 | U. `FormHandlers.gs` at 1,353 lines | 1 | 1 | 2 | 1 | none (BACKLOG 86) |

## The items, with evidence

### A. Jotform upload space reaches the cap (L3 C3 E1)

- **Usage.** 1.25 GiB of 10 GiB (12.5 %) on 2026-10-06. Uploads grow about 1.8 GB a month
  (BACKLOG 68).
- **Projection.** 50 % around mid-December 2026, 80 % around February 2027 and the cap around
  mid-March 2027. At September's pace the cap moves to about August 2027. BACKLOG 68 calls
  this arithmetic, not a fact.
- **The question is required.** The Group Photo is "required" (`glow/sync.py:44`). At the cap
  a mentor probably cannot submit. Jotform's behaviour at the cap is not verified.
- **Warnings exist.** `glow/usage.py:20-21` warns at 50 % (`form_status.py`'s `storage:`
  line). The runner raises an ATTENTION at 80 %.
- **No decision yet.** Gold, or a retention policy (the CEO's call), is open. Whether GLOW
  already pays the nonprofit rate is unknown (BACKLOG 68).
- **Fix.** One decision, made before the warning gets urgent. Retention would also starve
  `tools/backfill_resolve.py` and the question-18 comparison for the purged months.

### B. Live Apps Script ≠ `appsscript/`; deploy not recorded (L3 C2 E1)

- **Undeployed changes.** RUNBOOK "Apps Script deploy" `Status` (`docs/RUNBOOK.md:2071`): the
  2026-10-09 cleanup's changes are in the repository but not deployed. Among them are the
  handlers' write order and the Rebuild menu item's YES/NO (`docs/RUNBOOK.md:1831-1833`).
  `git log --since=2026-09-30 -- appsscript` lists 15 commits dated 2026-10-09.
- **No deploy tags.** `git tag -l 'appsscript-deployed-*'` prints nothing, and neither does
  `git ls-remote --tags origin`. The deploy skill bases its diff and its rollback on that tag
  (`.claude/skills/deploy-appsscript/SKILL.md:16-17`, `:47`).
- **Cost.** The tests prove the repository's `.gs`, not what runs. Every later Apps Script fix
  ships on top of the 15 untested-in-production commits. A rollback target is "the commit Ryan
  knows was live".
- **Fix.** One push on Ryan's go, then the tag. Optionally, `/land-checks` prints "appsscript/
  is N commits ahead of the last deploy tag".

### C. Jotform runtime builds not compared (L3 C2 E1)

- **What is compared.** `glow/translation_lookup.py` emulates `formTranslation.v2.js`.
  `READ_BUILDS` holds 6 builds (`:68-71`).
- **What is not.** BACKLOG 64 (bullet of 2026-10-06) lists builds served that day that are not
  in `READ_BUILDS`: template `bc6c80d556a`, Africa, Asia and Latin America `8705c008453`, and
  U.S `18bdf84aedc`. Eight distinct builds were seen between 2026-10-02 and 2026-10-06.
- **How it shows.** Since #13, `form_status.py --rendered` names an uncompared build as a note,
  never a problem (BACKLOG 64, bullet of 2026-10-14).
- **Cost.** If the dictionary lookup changes, the names audit vouches for a form whose
  dictionary alters a girl's name, and the wrong name reaches Salesforce. The submit
  handler's `clearFieldOnHide` branch (item 67) is in the same unread files.
- **Fix.** Per build: a diff of five functions. The risk is that nobody does it.

### D. An integration lapses silently (L2 C3 E2)

Each of these can stop working without an alarm:

| Connection | Evidence | Who would notice |
|---|---|---|
| Jotform → Salesforce (the native V2 integration) | It was revoked once: the VPN freeze of 2026-09-30 (`docs/RUNBOOK.md:2744-2748`). Before launch nothing reached Salesforce from 2026-03-28 (BACKLOG 48). `tools/integration_status.py` reads the configuration, not delivery. | A person looking at the dashboard's "not submitting" table |
| Jotform → Google Drive (photos) | Jotform raises no alarm when the token lapses; the check is a monthly look by eye (BACKLOG 70) | Ryan, monthly |
| Sheet → GitHub (`SYNC_DISPATCH_TOKEN`, a fine-grained token, `appsscript/Dispatch.gs:17`) | HTTP errors are muted by design (`test/dispatch_test.js`, "HTTP errors are muted"). Its expiry is recorded nowhere: `git grep -i expir` finds no mention. | Nobody. The 11:00 UTC cron (`.github/workflows/auto-sync.yml:19`) still runs, so the cost is up to a day's delay. |
| Mac → Salesforce (CLI login `glow`) | `glow/salesforce.py:105-119` refuses with a re-login message | The next person who runs a Salesforce tool |

- **What is missing.** Nothing in `tools/auto_sync.py` or `glow/` queries `Attendance_Batch__c`
  for delivery (`git grep`). The runner could compare each day's submissions per form with the
  batches Salesforce holds, counts only.
- **The blocker.** The runner has no Salesforce credentials until the `SF_SYNC` setup is done
  (BACKLOG 27: none of the user, permission set, app or secrets existed on 2026-10-09).
  Until then the check would run from the Mac.

### E. Salesforce metadata only in `data/` (L2 C3 E2)

- **What is outside git.** The processor's Apex (class, trigger, tests) as deployed and its
  "before" copies: `data/sf_processor_2026-10-02/{before,after}` and
  `data/sf_totals_2026-10/{before,after}`. The dashboard, its 13 reports, the report types and
  the generator `gen.py`: `data/sf_dashboard_2026-10-02/` (`docs/RUNBOOK.md:2629`). The
  permission set and folder shares: `public_2026-10-09/`. The Monthly Report change:
  `data/sf_monthly_report_2026-09-30/`. The `sfdx-project.json` (`sourceApiVersion` 65.0,
  `docs/plans/2026-10-06-attendance-totals.md:762`).
- **Rollbacks point at it.** Rollback = redeploy `data/sf_processor_2026-10-02/before`
  (DECISIONS 2026-10-02, `docs/DECISIONS.md:317`) or `data/sf_totals_2026-10/before/`
  (`docs/RUNBOOK.md:2491`).
- **It has been lost before.** `/harness:land` deletes a worktree's `data/`. On 2026-10-09 one
  worktree held the only copies of 11 files (`CLAUDE.md:34`).
- **Likely changes within six months.** #35 (relabel the dashboard tiles, in progress),
  BACKLOG 72 (the partners' count intake), 76 (adding girls to a day that has a batch) and 58
  (attendance rate). Each one is a metadata change made without versioned source.
- **Fix.** BACKLOG 82 as written: a `salesforce/` sfdx project in git, metadata only (no record
  data, no names), deployed check-only from there.

### F. RUNBOOK size and stale Status lines (L3 C2 E2)

- **Size.** `docs/RUNBOOK.md` is 2,978 lines: 37 `##` procedures, 100 lines inside code
  fences, and 180 lines that carry a `2026-` date. The largest sections are "Club accounts in
  Salesforce" (182 lines), "Automatic sync" (179), "The names dictionary and the module
  values" (170) and "Attendance dashboard in Salesforce" (160).
- **Stale today** (every one of these can be checked against the repository, except the
  first):
  - The dashboard's Access change: the `Status` line (`:2548`) and the Access bullet
    (`:2584-2587`) say it waits for Ryan's deploy. Ryan says it is live (ticket #47's
    Context). The plan's frontmatter still says `blocked`. This could not be verified
    offline.
  - The table of contents (`:19-62`) has no entry for "Special events" (`:815`).
  - The "Clubs that do not use Jotform" `Status` (`:1615`) says "the runner runs it once
    `main` is pushed". `main` was pushed 2026-10-13 (`docs/agent/handoff.md:13`).
  - The "Disabling a regional form" `Status` (`:1228`) says the first run (the U.S form) is not
    recorded. The U.S form is `DISABLED` (`docs/agent/handoff.md:5`, `:12`).
  - The "Live gate (Claude Code)" section and the clasp comment (`:2080`, `:2810`, `:2829`)
    describe `GLOW_LIVE_OK`, which no longer opens the gate (DECISIONS 2026-10-14). #37 fixes
    this.
  - `docs/agent/handoff.md:33` runs the retired `tools/worklog.py`. Lines `:15-16` describe the
    runner hold that DECISIONS 2026-10-14 removed.
- **Waiting on Ryan.** 10 of the 31 `Status` lines say a step waits for Ryan, or that the
  step is "not recorded" (`:967`, `:1055`, `:1091`, `:1228`, `:1615`, `:2002`, `:2071`,
  `:2238`, `:2548`, `:818`). A Status line that waits on a person goes stale the day the person
  acts. The board, which has `needs-input`, does not.
- **Cost.** Claude reads the RUNBOOK as the truth. A stale status sends a session to redo a
  live step, or to skip one.

### G. Salesforce CLI unpinned; tools read its JSON (L2 C2 E1)

- **What the tools assume.** `glow/salesforce.py:108` reads `sf org display --json` and
  `sf org auth show-access-token --json` (`result.instanceUrl`, `result.accessToken`).
  `tools/sf_dupes.py:662` reads `sf apex run --json`.
- **No version recorded.** No file names a CLI version: `git grep '@salesforce/cli'` finds
  nothing. The Mac has 2.151.7 (read with `sf --version`, local, no org call). The REST
  version is `v67.0` (`glow/salesforce.py:32`), and the RUNBOOK's examples use `v62.0`
  (`:2592`, `:2680`).
- **Releases.** Salesforce's next release (Spring '27) falls inside the window. The org runs
  the processor's Apex tests on any deploy, and their source is item E.
- **Cost.** The Mac's Salesforce tools stop (the monthly `sf_dupes.py check`, any back-fill).
  The runner is unaffected: it uses client credentials, not the CLI.
- **Fix.** Record the CLI version in RUNBOOK "Credentials". Add one offline test over a
  recorded `--json` answer of each shape.

### H. Harness plugin unpinned; the invoice runs on it (L2 C2 E1)

- **How it is installed.** The plugin comes from a directory marketplace,
  `~/portfolio_projects/harness` (`~/.claude/plugins/known_marketplaces.json`). Its install
  record still says `0.1.0` at `0061302`, installed 2026-10-06. Yet DECISIONS 2026-10-14
  relies on harness behaviour of commits `07a4835` and `e372870`.
- **What depends on it.** The work log behind the monthly invoice (`harness-worklog`; its
  fixes "go to the harness repository", DECISIONS 2026-10-14), the verify and land flow, and
  `HARNESS_*` in `.claude/settings.json:3-5`.
- **Cost.** A harness change alters the invoice tool or the land flow under this repository,
  with nothing here to say which commit last worked.
- **Overlap.** #48 inventories the harness plugin. This item only asks that the working
  commit be recorded (T11).

### I. Python 3.10 EOL, unpinned Google libraries on the live runner (L2 C2 E2)

- **Python itself.** 3.10 reached its end of life on 2026-10-04 (BACKLOG 80). The runner and CI
  pin `"3.10"` (`.github/workflows/auto-sync.yml:64`, `check.yml:18`), and ruff's target is
  `py310` (`ruff.toml:6`).
- **Google's libraries.** `google.api_core` 2.34.0 in the venv (3.10.4) warns on import:
  "You are using a non-supported Python version (3.10.4). Google will not post any further
  updates to google.api_core supporting this Python version" (FutureWarning, read with
  `python3 -W default`).
- **Ranges, no lock.** `requirements.txt` holds ranges (`>=2.100,<3`, `>=2.23,<3`) and
  `auto-sync.yml:65` installs them fresh on every run. An upstream release changes what the
  live sync runs, without a commit (BACKLOG 81). pip honours `Requires-Python`, so an outright
  install failure is less likely than a silent behaviour change.
- **Code to change.** `datetime.utcnow()` is deprecated in 3.12, at `tools/sf_backfill.py:139`
  and `:802`.
- **Not verified offline.** Whether `actions/checkout@v4`, `setup-python@v5`,
  `upload-artifact@v4` and `setup-node@v4` face a runtime deprecation in the window. The run
  annotations on GitHub would say.

### J. Python ↔ Apps Script duplicated rules (L2 C2 E3)

- **The size of it.**
  - 8 constants exist on both sides (ARCHITECTURE "Constants that exist on both sides",
    `docs/ARCHITECTURE.md:118-136`).
  - 6 parity bridges (`:138-171`).
  - 11 known-divergence bullets (`:173-229`), 8 of them Python versus Apps Script.
  - The tests that hold it together: `test/gs_parity_test.py` (314 lines, 12 tests),
    `test/parity_test.js` (195 lines) and `test/forms_logic_test.js` (2,971 lines).
  - CLAUDE.md rules 7 and 10; BACKLOG 28 (three gaps still open).
- **`appsscript/Regions.gs`.** Hand-kept since 2026-10-09, last touched 2026-08-26
  (`git log`). Line 3 still says "GENERATED by tools/derive_partner_regions.py", a retired
  tool. The edit hook keeps it Ryan's (ARCHITECTURE "Generated and hand-kept files").
- **Cost.** In steady state, few changes cross the boundary (Roster columns, the shared-name
  rule, the Partners marker). When one does, it costs two implementations and a parity test.
- **What shrinks it.** Retiring the legacy enrollment path (item N) removes parity bridges 1
  and 2, the response-tab constants row and four of the eight divergences (`read_sheet`'s
  partner-less rows, bullets, invisible characters in `parse_roster`, and `splitlines`).
  `parseRoster_` stays: the Club Roster Form's REMOVE uses it (`appsscript/FormHandlers.gs:867`).

### K. `data/` and `backups/` exist on one Mac only (L1 C3 E1)

- **Rollback and undo files that exist only there.** They are named by the docs, not read here:
  - `data/backfill_2026-09/` (`ledger.csv`, `created_contacts.csv`: the back-fill's only
    rollback, `docs/RUNBOOK.md:2750-2760`);
  - `data/module_fix_2026-10/ledger.csv` (the `--undo`, `:810`);
  - `data/sf_dupes_<date>/` (merge rollback);
  - `data/sf_prep_2026-09-30/created_accounts*.csv` (the 345 accounts' rollback, `:2230`; also
    BACKLOG 58's club → account map);
  - `data/deactivate_clubs/<stamp>/` (`--undo`);
  - `backups/` (form snapshots, translation stores). The runner uploads conditions backups
    only.
- **No backup recorded.** No document names an off-Mac copy (`git grep -i "time machine"`
  finds none).
- **Fix.** A decision by Ryan, not code. The files hold minors' names, so any copy is
  governed like the original (encrypted, owner only; the `child-privacy` skill). This item
  only asks that the answer be written into RUNBOOK "Credentials" or the privacy section.

### L. OAuth scopes not pinned in the manifest (L1 C3 E1)

- **The risk.** BACKLOG 37 is in progress: `appsscript/appsscript.json` has no
  `oauthScopes` list. A new Google service makes the form-submit trigger fail hard until the
  owner re-authorises (CLAUDE.md rule 11).
- **Already guarded.** `scripts/check_gs.js` pins the 8 services and fails on a ninth
  (`make gs`: "8 services, 0 unknown calls"). Likelihood is low in steady state. No new
  ticket.

### M. `hooks_test.py` is most of the verify run (L3 C1 E1)

- **Measured 2026-10-15.** `scripts/verify.sh` took 87.9 s wall. The Python suite ran 738
  tests in 82.4 s. `test/hooks_test.py` alone took 75.9 s for 29 tests. The next slowest
  module took 2.5 s (`fix_name_translations_test`).
- **Cost.** The verify command runs on every stop hook, every red check and every review
  round.
- **Overlap.** #48 (the stop hook in a red worktree) and #46.

### N. Legacy enrollment path and the Rebuild menu item (L1 C3 E2)

- **Only the legacy path uses it.** `sync_attendance_form.py:528` calls `read_sheet()` only
  without `--roster`. No doc, skill or tool runs the sync without `--roster` (`git grep`). The
  runner passes it (`tools/auto_sync.py:526`).
- **It is pre-launch only.** RUNBOOK "Roster rebuild and upload (offline path)" says
  "pre-launch only, never after 2026-09-01" (`docs/RUNBOOK.md:1820`). A rebuild "reactivates
  every girl removed through the Club Roster Form … re-creates any enrolled club that was
  renamed or moved".
- **The menu item is still live.** "Rebuild roster from enrollment responses" is in the GLOW
  menu (`appsscript/Menu.gs:8-9`). Its YES/NO is undeployed (item B). BACKLOG 39 is open.
- **What it keeps alive.** `glow/sync.py` `parse_roster` / `read_sheet` (`:730-777`), the
  `COL_*` constants, `Normalize.gs readResponses_` and `Roster.gs rebuildRosterLocked_`,
  `tools/build_roster_offline.js` (273 lines) and `tools/upload_roster.py` (186), and
  `test/fixtures/make_fixture.py`. It also keeps `make fixtures-check`, and the real-CSV
  branch of `test/forms_logic_test.js:2939`, which reads `data/enrollment_2026-08-24.csv`
  when present. That branch makes the suite differ between Ryan's Mac and CI.

### O. Tests that pin prose (L3 C1 E2)

- **How many.** At least 58 test methods in 16 files read a tracked `.md` file (method-level
  `git grep` of `"docs"`, `.md"` and the section helpers). In `test/runbook_test.py` (887
  lines) that is 28 of 32 tests. In `test/special_events_test.py` it is `IdgDocs` (5) and
  `RunbookQuotes` (1).
- **What they pin.**
  - `RunnerRunbook` (`test/runbook_test.py:422-470`) keeps 9 `HOLDS` phrases, 20
    `OTHER_WORDS` and a regex out of four RUNBOOK sections and the skills.
  - `WorkLogRunbook` wants `## Work log and invoices` "word for word".
  - Two tests read the whole RUNBOOK: the public-URL table (`test/links_layout_test.py:274-278`)
    and "`attention`, `skipped`, `failed`" (`test/retired_rosters_test.py:619-621`). They
    break if that text moves to another file.
  - `doc-refs` keeps 241 RUNBOOK section references, 98 anchors and 289 BACKLOG references
    alive (the run of 2026-10-15).
- **Cost.** Each one protects a real contract: a tool's quoted line, or a decision's wording.
  But they make any doc consolidation a test change, and the board's test-first rule then
  makes a docs ticket a tests ticket.
- **Overlap.** #46 ranks them as friction. Here they only constrain the consolidation below.

### P. Two backlogs: BACKLOG.md and the board (L3 C1 E2)

- **Size.** `docs/BACKLOG.md` runs to 758 lines and has 94 item sections: 42 `open`, 8 `in-progress`, 20
  `blocked-on-ryan`, 18 `done` and 6 `dropped`. New work is a ticket (DECISIONS 2026-10-14),
  so 70 live items sit outside the board.
- **Overtaken already.**
  - Item 47 ends "re-count 35's empty submissions for two weeks (to 2026-10-14)": the window
    closed and no result was recorded.
  - Item 31 ("plan mode by default after launch week") predates the harness.
  - Item 53 is in progress, but #36 gated `sf` and `gh api` writes.
  - Item 83 closes with #37.
  - Item 1a (key rotation) has been `blocked-on-ryan` since launch.
- **Cost.** Nothing breaks. What is planned is split across two places, and a session has to
  read both.

### Q. One-off tools and one-time menu items (L2 C1 E1)

Each one-off has to keep passing `make check` against today's `glow/` (DECISIONS 2026-10-09,
"Finished one-offs are deleted, not archived"). The candidates, with their dates, are in
[Retirement candidates](#retirement-candidates). Together:

- `tools/fix_module_values.py`, `sf_girls_present.py`, `sf_backfill.py`,
  `backfill_resolve.py`, `fix_roster_order.py` and `fix_name_translations.py` are 2,871 lines.
- Their tests are another 3,443 lines (435 + 264 + 1,090 + 1,059 + 595, plus the share of
  `links_layout_test.py`, not counted).
- 4 one-time or pre-launch GLOW menu items (`appsscript/Menu.gs:8-9`, `:18-21`, `:26`).

### R. Plan and intent statuses drift (L2 C1 E1)

- **Size.** 44 plans (12,576 lines) and 11 intents (662 lines): 36 `done`, 10 `in-progress`,
  5 `blocked`, 2 `proposed`, 1 `accepted`, 1 `superseded`.
- **Drift.** `docs_index.py --check` enforces the vocabulary, not the truth.
  `2026-10-09-attendance-reports-public.md` is `blocked`, but its change is live per Ryan
  (item F). This is the same drift that DECISIONS 2026-10-09 ("A plan is required…") found
  and fixed once.

### S. Node 18 + clasp 2.4.2 (L1 C2 E2)

- **The pin.** clasp 2.4.2 on Node 18 (DECISIONS 2026-08-27: "clasp 3 needs Node 20"). The
  `clasp:push` script refuses any other Node (`package.json`), and CI's JS checks run on
  Node 18 (`.github/workflows/check.yml:15`).
- **Node 18 is past its end of life** (April 2025). The Mac's default Node is v26.10.0, so a
  push needs `nvm use 18` (`.claude/skills/deploy-appsscript/SKILL.md:32`).
- **Cost.** The deploy path fails until a clasp 3 migration, which means a new login and new
  flags. The fallback is pasting 10 files into the editor.
- **Plan.** Watch. Upgrade when clasp 2.4.2 or Node 18 stops installing, or with the next
  Apps Script change after item B is done.

### T. Dashboard Partner filter at 49 of 50; two partner lists (L1 C2 E2)

- **The filter is nearly full.** It holds 49 typed partner names, and Salesforce allows 50
  (`docs/RUNBOOK.md:2567-2575`; BACKLOG 60, part 6). A 51st partner needs another layout.
- **Two lists.** A new or renamed partner must be added by hand to both the dashboard's
  `partners.json` (in `data/`, item E) and `glow/sf_partners.csv`.
- **Low likelihood.** Steady state means few new partners.

### V. DECISIONS.md growth (L1 C1 E1)

615 lines, 84 decisions, append-only by its own rule (`docs/DECISIONS.md:1-9`). Long but
well-formed. Nothing to do.

### U. `FormHandlers.gs` at 1,353 lines (L1 C1 E2)

BACKLOG 86 ("if it keeps growing"). In steady state it should not grow. Nothing to do.

## Knowledge outside git

These come from what the tracked docs and code say lives elsewhere. Nothing under `data/` was
read.

| What | Where it lives | Risk item |
|---|---|---|
| Processor Apex, its tests, the dashboard and reports, `gen.py`, permission sets, `partners.json` | `data/sf_*` on one Mac | E, T |
| Back-fill, module-fix, girls-present and merge ledgers; account and deactivation rollback files | `data/` on one Mac | K |
| Form snapshots and translation stores | `backups/` on one Mac; the runner keeps conditions backups as artifacts | K |
| Jotform's Salesforce V2 mapping, the Drive integration, the header logo upload | Jotform's builder. Only the mapping is read back (`tools/integration_status.py`); the Drive setup and the logo are Ryan's steps (`docs/RUNBOOK.md:1055`, `:1091`) | D |
| The `SF_SYNC` setup (integration user, permission set, External Client App, two secrets) | Not done as of 2026-10-09 (BACKLOG 27) | D |
| The dispatch token's expiry; whether GLOW pays the nonprofit rate | Nowhere | D, A |
| Which Apps Script commit is deployed | Ryan's memory (no tag) | B |
| The harness commit that works with this repository | `~/portfolio_projects/harness`, unrecorded | H |
| What is stuck on Ryan | 20 `blocked-on-ryan` BACKLOG items and 10 RUNBOOK Status lines | F, P |

## Retirement candidates

How a tool retires (ARCHITECTURE [Retired tools](../ARCHITECTURE.md#retired-tools)): delete
the tool and its tests. Add a row (Path, What it did, Retired in, and Restore with
`git show <commit>^:<path> > <path>`), then run `make check`. Prior rows name the deleting
commit (`7c24ac7`, `608bcd2`, `0dc0d4c`, `648947e`) or a ticket and commit (#10, `459451d`).
A `.gs` restore is also an Apps Script push, so it needs Ryan's go (CLAUDE.md rule 1).

| Tool or code | Why it exists | Retire after | Restore path |
|---|---|---|---|
| `tools/fix_module_values.py`, `test/fix_module_values_test.py` | The one-off `Module__c` correction of 2026-10-07 and its `--undo` | **2026-11-01**: the undo window closes at the end of October (BACKLOG 84). Keep the one-line SOQL audit in RUNBOOK "The names dictionary and the module values". The ledger stays in `data/`. | `git show <commit>^:tools/fix_module_values.py`, the test likewise |
| `tools/sf_girls_present.py`, its test | The one-off `Girls_Present__c` back-fill, done 2026-10-07 (573 written). It has no undo command (`.claude/skills/salesforce/SKILL.md:61`). Its `check` is a health check (`docs/RUNBOOK.md:2534`). | When its two `check` counts move into RUNBOOK "Attendance totals and partner-reported counts" as SOQL, or into the monthly `sf_dupes.py check`. Earliest 2026-11-01, after one clean monthly look. | `git show <commit>^:tools/sf_girls_present.py` |
| `tools/sf_backfill.py`, `tools/backfill_resolve.py`, their tests | The September back-fill (done 2026-10-02). The RUNBOOK keeps them as the incident procedure (`:2736-2742`), but the window is hard-coded (`backfill_resolve.py:54-57`). Rolling back by contact is now dangerous (`:2750-2760`). | When BACKLOG items 76 (11 held sessions) and 78 (the guard) are settled, and Ryan chooses between generalising the window (flags, not constants) and retiring both. BACKLOG 65's `q18_empty` watch uses the resolver: move it first. | `git show <commit>^:tools/sf_backfill.py`, `…:tools/backfill_resolve.py`. `glow/submissions.py` stays: `fix_module_values.py` imports it. |
| `tools/fix_roster_order.py` | The one-time repair of 2026-09-30 (BACKLOG 47) | **Not yet.** It is still the fix `form_status.py` prints (`glow/layout.py:30` `FIX`). It can go once that hint names a sync apply instead, and no form has needed it for six months (2027-04-01). | `git show <commit>^:tools/fix_roster_order.py` |
| `tools/fix_name_translations.py` | Removed 55 stale dictionary entries (2026-10-06). It has `--restore`, and is where BACKLOG 63's pruning would be built. | When BACKLOG 63 is dropped or done | `git show <commit>^:tools/fix_name_translations.py` |
| GLOW menu: `migrateCountryToRegion`, `retireOldEnrollmentForm` (`appsscript/Forms.gs`) | One-time migrations (BACKLOG items 38 and 6) | When the live Audit tab shows each has run, or its item is settled another way (BACKLOG 85) | `git show <commit>^:appsscript/Forms.gs` plus `Menu.gs`, then a push |
| GLOW menu: `migrateFormWording` | The one-time wording run (BACKLOG 43, not yet run) | After Ryan's run is recorded | As above |
| The legacy enrollment path: the sync without `--roster` (`read_sheet`, `parse_roster`, `COL_*`); `readResponses_` and the Rebuild menu item; `tools/build_roster_offline.js`, `tools/upload_roster.py`; `test/fixtures/make_fixture.py` and its two outputs; parity bridges 1 and 2 | Pre-launch import and rebuild (item N) | When Ryan confirms that a rebuild from the raw responses is never wanted (BACKLOG 39), and names the recovery path for a damaged Roster tab instead (the sheet's version history). | `git show <commit>^:<path>` for each; the archive keeps the commands (`docs/archive/runbook-roster-rebuild.md`) |
| `appsscript/Regions.gs` | Prefills a region where the Partners tab has none | When the Region picker is live (BACKLOG 38) and every Partners row has a region (Ryan reads the count). The edit is Ryan's: the hook protects the file. | `git show <commit>^:appsscript/Regions.gs`, then a push |

## What to upgrade, and when

| What | Now | When | Note |
|---|---|---|---|
| Python | 3.10 (EOL 2026-10-04) | **Before 2026-12-31** (T10) | 3.12 in CI, the runner, the venv and `ruff.toml`. Fix the two `utcnow()` calls. One dry run on 3.12, then one watched applying run (BACKLOG 80). |
| Runner dependencies | Ranges, installed fresh | With Python (T10) | A `requirements.lock` from `pip freeze`, refreshed on purpose (BACKLOG 81) |
| Salesforce CLI | 2.151.7 on the Mac, recorded nowhere | Record it now (T11). Update on purpose, then run one read-only tool | |
| Salesforce API | REST `v67.0`; the project at 65.0 | No change. After each Salesforce release (next: Spring '27), run a check-only deploy of the processor from git (needs T4) | |
| Node + clasp | 18 + 2.4.2 | Only when it breaks, or after item B | clasp 3 needs Node 20 and a new login |
| GitHub Actions | checkout@v4, setup-python@v5, upload-artifact@v4, setup-node@v4 | When the run annotations warn | Not verified offline |
| Harness plugin | A directory marketplace, unrecorded | Record the working commit now (T11; #48 owns the rest) | |

## Doc consolidation

**The constraint.** DECISIONS 2026-10-09, "The docs stay one file each…", rejected splitting
the RUNBOOK into `docs/runbook/`, because 241 section references and the whole-file tests
would break. This proposal keeps that decision. `docs/RUNBOOK.md` stays the one operations
guide at the same path, with every quoted heading. History leaves it by the pattern the
2026-10-09 cleanup used: a finished procedure's text moves to the end of its plan under
`## From the RUNBOOK (moved …)`, and the RUNBOOK keeps a stub. Wanting `docs/runbook/`
anyway would amend that decision. This document does not recommend it.

### What moves

To each plan, or to `docs/archive/` when no plan fits:

- **"Rosters above Submit"** (`:1029`, 23 lines): the one-time repair is done. Keep a stub.
- **"Club names two partners share"**: `### The one-time switch` (`:1574-1583`). The plan
  already holds the full text. Keep `### Afterwards`.
- **"Club accounts in Salesforce"**: the 2026-09-30 rounds' history (the retired tool, the
  rollback-file bullet) moves to `plans/2026-09-30-salesforce-clubs.md`.
- **"The names dictionary and the module values"**: the `fix_module_values.py` paragraph and
  commands (`:802-813`) move with T8. Keep the SOQL audit line.
- **"Attendance totals and partner-reported counts"**: the one-off back-fill paragraph
  (`:2527-2535`) moves when `sf_girls_present.py` retires. #35 edits this section first.
- **Rollout narratives** in "Automatic sync", "One club per submission (the club guard)",
  "The names list sent to Salesforce" and "Special events" (the UTC times and the per-form
  qids of each go-live) move to their plans' Results.
- **"Work log and invoices"** (111 lines): what `harness-worklog` documents itself. Keep the
  monthly chore, the time zones and the `--transcripts` lesson.

### What is deleted

- **"Data-quality report"** (`:2162`, 14 lines, a retired tool; no file quotes it), and its
  table-of-contents line.
- **Every Status-line narrative of a pending step.** A Status line says "live since …" or
  "not live: #N". The pending step itself becomes a `needs-input` ticket, so it cannot go
  stale in the RUNBOOK.

### What is fixed

- The table of contents gains "Special events".
- The stale lines of item F are corrected.
- The handoff is rewritten by the next `/harness:handoff`.

### What stays

Every procedure: When, Status, Dry run, Apply, Verify, Rollback.

### Expected size

An estimate, not measured: 350-500 lines fewer (12-17 %), to about 2,500. The large
procedures ("Automatic sync", "Missed form responses", "Photos", "Club accounts in
Salesforce") are mostly procedure.

### Headings that must stay

A move must not rename any of these. Counts are the tracked files that quote each heading
(`scripts/check_doc_refs.py`'s patterns, run 2026-10-15). An asterisk marks headings that code
or tests quote, which is a test or tool change, not only a doc change.

- **Jotform forms**
  - "The forms" (3)\*
  - "Automatic sync" (11)\*
  - "The Club picker (mentors choose their club instead of typing it)" (1)
  - "One club per submission (the club guard)" (5)
  - "The names list sent to Salesforce" (12)\*
  - "The names dictionary and the module values" (6)\*
  - "Special events" (8)\*
  - "Translations" (2)
  - "Links above Submit (problem report, Club Roster Form)" (2)
  - "Rosters above Submit" (3)\*
  - "Header logo" (3)\*
  - "Photos" (7)\*
  - "Disabling a regional form" (4)\*
  - "Building a new regional form (not maintenance)" (1)
- **Clubs**
  - "Renaming a club" (4)\*
  - "Moving a club to another partner (a mistyped partner)" (5)\*
  - "Club names two partners share" (11)\*
  - "Clubs that do not use Jotform" (11)\*
  - "Deactivating a club" (3)\*
  - "Roster rebuild and upload (offline path)" (3)\*
- **Sheet and Apps Script**
  - "Working the ReviewQueue" (10)\*, with its table's issue names: `FormHandlers.gs` points
    staff at an issue by name, for example "Form response could not be processed"
  - "Missed form responses" (6)\*
  - "Google Forms wording" (3)\*
  - "Apps Script deploy" (4)
  - "Rolling back `appsscript/`" (4)
- **Salesforce**
  - "Club accounts in Salesforce" (6)\*
  - "New clubs' accounts, automatically" (3)
  - "Duplicate girls in Salesforce" (2)
  - "Attendance totals and partner-reported counts" (2)
  - "Attendance dashboard in Salesforce" (5)
  - "September back-fill: the resolver" (2)\*
  - "Back-fill of attendance into Salesforce" (5)
- **Admin and offline checks**
  - "Credentials" (3)\*
  - "Live gate (Claude Code)" (4)\*
  - "Work log and invoices" (7)\*
  - "Checks" (1)

Unquoted, and free to change: "Keeping the forms in step with the Roster (the manual loop)",
"Backup and restore (Jotform)" and "Data-quality report".

### Test changes a move needs

Name these in the ticket that moves text:

- **`test/runbook_test.py`**
  - `SameNameRunbook` splits on `## Club names two partners share`, `## Renaming a club` and
    `## Automatic sync`.
  - `ContactIdsRunbook` reads "The names list sent to Salesforce": steps ` 6. ` and ` 7. `,
    `**Rollback**`, and the language-switcher residual paragraph.
  - `NamesAndModulesRunbook` reads its section.
  - `RunnerRunbook.SECTIONS` needs the APPLIES and BY_HAND phrases in four sections.
  - `WorkLogRunbook` needs its heading, and ARCHITECTURE's `## Retired tools` and
    `## Components`.
  - `moved()` reads only `## From the RUNBOOK (moved 2026-10-09)`, so a new move needs a new
    heading and its own helper.
- **`test/special_events_test.py`**
  - `IdgDocs`: `\n## Special events\n` exactly once, and its Status line names both types and
    links the IDG plan.
  - `RunbookQuotes`: the quoted MODULE line, the warning and `{15}{95}{96}{97}`.
- **Tests that read the whole RUNBOOK**, so their text must stay in that file:
  - `test/links_layout_test.py:274-278` (the public-URL table);
  - `test/retired_rosters_test.py:619-621`.
- **Others.** `test/hooks_test.py:211` (the gate's reason names "Live gate (Claude Code)").
  `test/gs_parity_test.py:302` (ARCHITECTURE "Constants that exist on both sides").

### The other docs

- **BACKLOG.md**: freeze it. Its rules, `doc-refs` and the 289 references stay. Triage the 70
  live items once (T14). Each one becomes a ticket (wanted within six months), `dropped`, or
  stays `open` as a parked idea with a dated bullet. Its header gains one line: nothing new
  gets planned here.
- **Plans and intents**: leave them in place, since RUNBOOK links and `moved()` read them.
  Correct the drifted statuses in the status sweep (T6).
- **DECISIONS.md**: no change.
- **`docs/agent/`**: this file, the two sibling findings and `harness-prep.md` are dated
  inventories. When their tickets close, they can move to `docs/archive/`.

## Proposed tickets

Nothing is filed. Ryan picks (epic #45). Size and risk use the board's labels. Value is what
the risk ranking says the ticket removes.

| # | Title | Size | Risk | Value | Overlap with open tickets |
|---|---|---|---|---|---|
| T1 | Decide Jotform storage: Gold or retention, before the 50 % warning (BACKLOG 68) | S (a decision; `needs-input`) | low | high (A) | none |
| T2 | Deploy and tag the 2026-10-09 Apps Script; `/land-checks` reports `appsscript/` ahead of the last tag | S | medium (live intake; Ryan's push) | high (B; also lands the Rebuild YES/NO, N) | #48 (land flow) for the `/land-checks` line only |
| T3 | Compare the uncompared Jotform runtime builds and add them to `READ_BUILDS` (BACKLOG 64) | S | low (offline after one GET of each page) | medium-high (C) | #34 (the runner reads `--rendered` after a rules change: it could carry the build note) |
| T4 | Salesforce metadata into git as a `salesforce/` sfdx project, metadata only; check-only deploy from there (BACKLOG 82) | M | low (no deploy) | high (E; makes #35's dashboard change reviewable) | #35 (do T4 first, or let #35 start the project); #48 (a "Salesforce metadata change" skill) |
| T5 | A read-only delivery check: each form's submissions against `Attendance_Batch__c` per day, counts only. Record token expiries in RUNBOOK "Credentials". | M | low (read only) | high (D) | BACKLOG 27 (the runner's Salesforce credentials; until then it runs on the Mac); BACKLOG 62 (the in-sync path) |
| T6 | RUNBOOK and plans status sweep: the table of contents, the stale lines of item F, the drifted plan statuses; pending steps become `needs-input` tickets | S | low | medium (F, R) | #37 (Live gate section), #35 (Attendance totals section): skip their sections or land after them |
| T7 | RUNBOOK trim: history and finished one-time text to their plans, every quoted heading kept, the named tests adjusted | M | low | medium (F, O) | #46 (prose-pinning tests: its classification decides how far the tests follow) |
| T8 | Retire `tools/fix_module_values.py` (after 2026-11-01) and `tools/sf_girls_present.py` (its check moved), with their ARCHITECTURE rows | S | low | low-medium (Q) | none (BACKLOG 84) |
| T9 | Retire the legacy enrollment path and the Rebuild menu item, after Ryan confirms (BACKLOG 39, 28). Split: (a) Python, fixtures and `upload_roster.py` (M); (b) Apps Script with the next push (S). | M + S | medium (sync argument parsing; a push) | medium (N; shrinks J by two bridges and four divergences) | #46 (legacy code that stops automation) |
| T10 | Python 3.12 and a runner lockfile (BACKLOG 80, 81) | M | medium (CI runs the live sync: a dry run, then one watched apply) | medium (I) | none |
| T11 | Record the Salesforce CLI version and the working harness commit; an offline test over a recorded `--json` answer of each CLI shape the tools read | S | low | medium (G, H) | #48 (the harness plugin inventory) |
| T12 | Make `test/hooks_test.py` fast (76 s of an 88 s verify) | S-M | low (tests only; the hooks unchanged) | medium (M) | #48 (stop hook, session hygiene), #46 |
| T13 | Write down the off-Mac copy of `data/` and `backups/`, or its absence (a decision; `child-privacy` rules) | S | medium (minors' data) | medium (K) | none |
| T14 | BACKLOG triage: 70 live items become tickets, `dropped`, or parked; the header says it is frozen | S-M | low | low-medium (P) | #37 (closes item 83) |

## Could not verify (offline)

- **That the dashboard's 2026-10-09 Access change is live.** Taken from the ticket's Context
  (Ryan, 2026-10-14). The repository says it is not.
- **Which runtime builds the forms serve today.** BACKLOG 64 lists those of 2026-10-06.
- **Jotform's behaviour at the upload cap, and GLOW's billing rate.**
- **The expiry of `SYNC_DISPATCH_TOKEN`**, and whether the Jotform → Salesforce connection is
  healthy now.
- **Whether GitHub's runner images or the action majors in use face a deprecation inside the
  window.**
- **The Salesforce CLI version.** It was read on this Mac with `sf --version`, which is local
  and makes no org call. Nothing pins it.
