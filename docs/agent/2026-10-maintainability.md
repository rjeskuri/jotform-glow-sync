# Maintainability risks going forward (2026-10)

Ticket #47, epic #45 (steady state). Written 2026-10-15 on `t/47-identify-the-maintainability-r`.
Its numbers were refreshed after the rebase onto `main` at `0fbd63c`, which includes #31, #33,
#38 and #48. The work was offline: no Jotform, Salesforce or Google call, and nothing under
`data/`, `backups/` or `credentials/` was read. What lives there is taken from what the tracked
docs and code say.

This is a proposal only: nothing here changes code, docs or a live system. Two related docs
cover neighbouring ground:
- #46 (open): legacy code and guardrails that stop Claude working automatically,
  `docs/agent/2026-10-friction.md`.
- #48 (closed): the workflow proposals, landed as `docs/agent/2026-10-workflow.md` (`2decf25`),
  cited below as "the workflow doc, item N".

Where an item touches their scope, it says so.

## Summary

**Top 5 risks** (the next six months, to 2027-04-15):

1. **Jotform's upload space runs out.** The Group Photo is required. At October's pace, uploads
   pass 50 % of Silver's 10 GiB around mid-December 2026 and reach the cap around mid-March
   2027 (BACKLOG 68). Nobody has decided between Gold and a retention policy.
2. **The live Apps Script is not the code in `appsscript/`.** The 15 commits of 2026-10-09
   wait for a push (`docs/RUNBOOK.md:2095`). No `appsscript-deployed-*` tag exists locally or on
   `origin`, so git cannot say which commit is deployed. The deploy skill's rollback starts from
   that tag.
3. **Jotform's runtime changes weekly, and our emulation of it is pinned.** Six builds have
   been compared (`glow/translation_lookup.py:68-71`). At least three builds served since
   2026-10-06 have not (BACKLOG 64).
4. **An integration can lapse without an alarm.** Any of these can stop working silently: the
   Jotform → Salesforce connection, the Drive token, the sheet's dispatch token and the CLI
   login. No automated check compares Jotform submissions with Salesforce batches.
5. **The Salesforce source lives only in gitignored `data/` on one Mac.** That covers the
   processor's Apex, the dashboard generator and the permission sets (BACKLOG 82). #35 needs to
   change that dashboard now. The workflow doc's item 12 would keep building packages under
   `data/`. T4 reconciles the two.

**Top 3 actions:**

1. **Book the storage decision before the 50 % line.** Ryan and the CEO choose Gold or a
   retention policy by 2026-12-01 (T1).
2. **Deploy and tag the Apps Script.** Ryan pushes it and adds the tag. `/land-checks` then
   reports when `appsscript/` is ahead of the last tag (T2).
3. **Put the Salesforce metadata in git, metadata only, before #35's dashboard change.** Point
   the workflow doc's `/sf-metadata` skill at that project instead of at `data/` (T4).

Three more are cheap:
- Compare the uncompared runtime builds (T3).
- Sweep the stale RUNBOOK status lines (T6).
- Retire `tools/fix_module_values.py` after 2026-11-01 (T8).

**On the RUNBOOK.** A trim is not worth a ticket. The 2026-10-09 cleanup already moved its
history into the plans. What is left is mostly procedure, so a further trim saves only about 25
lines now, and about 100 once the retirements land. The cost is stale Status lines, not length;
see item F and "Doc consolidation".

## How the items are scored

**Likelihood (L).** Will it break or bite within six months?

| Score | Meaning |
|---|---|
| 1 | unlikely |
| 2 | plausible |
| 3 | expected, or already happening |

**Cost (C).** What happens when it does?

| Score | Meaning |
|---|---|
| 1 | an hour of fixing |
| 2 | a day of fixing, or a wrong output someone must notice |
| 3 | attendance stops reaching Salesforce, minors' data is at risk, or a live system cannot be rolled back |

**Effort (E).** What does the fix take?

| Score | Meaning |
|---|---|
| 1 | under half a day, or one decision by Ryan |
| 2 | a ticket of size S or M |
| 3 | a ticket of size L, or several tickets |

**Rank.** Sort by L × C, highest first. Ties go to the lower effort first, then to the higher
cost.

## Ranked list

| # | Item | L | C | E | L×C | Proposal |
|---|---|---|---|---|---|---|
| 1 | A. Jotform upload space reaches the cap | 3 | 3 | 1 | 9 | T1 |
| 2 | B. Live Apps Script ≠ `appsscript/`; deploy not recorded | 3 | 2 | 1 | 6 | T2 |
| 3 | C. Jotform runtime builds not compared | 3 | 2 | 1 | 6 | T3 |
| 4 | D. An integration lapses silently | 2 | 3 | 2 | 6 | T5 |
| 5 | E. Salesforce metadata only in `data/` | 2 | 3 | 2 | 6 | T4 |
| 6 | F. Stale RUNBOOK Status lines; its size | 3 | 2 | 2 | 6 | T6, T7 |
| 7 | G. Salesforce CLI unpinned; tools read its JSON | 2 | 2 | 1 | 4 | T11 |
| 8 | H. The harness commit that works is recorded nowhere; the invoice runs on it | 2 | 2 | 1 | 4 | T11 |
| 9 | I. Python 3.10 EOL, unpinned Google libraries on the live runner | 2 | 2 | 2 | 4 | T10 |
| 10 | J. Python ↔ Apps Script duplicated rules | 2 | 2 | 3 | 4 | T9 shrinks it |
| 11 | K. `data/` and `backups/` exist on one Mac only | 1 | 3 | 1 | 3 | T13 |
| 12 | L. OAuth scopes not pinned in the manifest | 1 | 3 | 1 | 3 | none (guarded) |
| 13 | M. `hooks_test.py` is most of the verify run | 3 | 1 | 1 | 3 | T12 |
| 14 | N. Legacy enrollment path and the Rebuild menu item | 1 | 3 | 2 | 3 | T9 |
| 15 | O. Tests that pin prose | 3 | 1 | 2 | 3 | none here (#46) |
| 16 | P. Two backlogs: BACKLOG.md and the board | 3 | 1 | 2 | 3 | T14 |
| 17 | Q. One-off tools and one-time menu items | 2 | 1 | 1 | 2 | T8 |
| 18 | R. Plan and intent statuses drift | 2 | 1 | 1 | 2 | T6 |
| 19 | S. Node 18 + clasp 2.4.2 | 1 | 2 | 2 | 2 | watch |
| 20 | T. Dashboard Partner filter at 49 of 50; two partner lists | 1 | 2 | 2 | 2 | watch |
| 21 | V. DECISIONS.md growth | 1 | 1 | 1 | 1 | none |
| 22 | U. `FormHandlers.gs` at 1,353 lines | 1 | 1 | 2 | 1 | none (BACKLOG 86) |

## The items, with evidence

### A. Jotform upload space reaches the cap (L3 C3 E1)

- **Usage.** 1.25 GiB of 10 GiB (12.5 %) on 2026-10-06, growing about 1.8 GB a month
  (BACKLOG 68).
- **Projection.** 50 % around mid-December 2026, 80 % around February 2027, the cap around
  mid-March 2027. At September's pace the cap comes around August 2027. BACKLOG 68 calls these
  projections arithmetic, not facts.
- **The Group Photo is required** (`glow/sync.py:44`). At the cap a mentor probably cannot
  submit. Jotform's behaviour at the cap is not verified.
- **The warnings exist.** `glow/usage.py:20-21` warns at 50 % (`form_status.py`'s `storage:`
  line), and the runner raises ATTENTION at 80 %.
- **The decision is open.** Gold, or a retention policy (the CEO's call). It is also unknown
  whether GLOW already pays the nonprofit rate (BACKLOG 68).
- **Fix.** One decision, made before the warning. A retention policy would also starve
  `tools/backfill_resolve.py` and the question-18 comparison for the purged months.

### B. Live Apps Script ≠ `appsscript/`; deploy not recorded (L3 C2 E1)

- **Undeployed code.** The `Status` of RUNBOOK "Apps Script deploy" (`docs/RUNBOOK.md:2095`)
  says the 2026-10-09 cleanup's changes are in the repository and not deployed. They include
  the handlers' write order and the Rebuild menu item's YES/NO (`docs/RUNBOOK.md:1854-1856`).
  `git log --since=2026-09-30 -- appsscript` lists 15 commits dated 2026-10-09.
- **No deploy tag.** `git tag -l 'appsscript-deployed-*'` and `git ls-remote --tags origin`
  both print nothing. The deploy skill bases its diff and its rollback on that tag
  (`.claude/skills/deploy-appsscript/SKILL.md:16-17`, `:47`).
- **Cost.**
  - The tests prove the repository's `.gs` files, not what runs.
  - Every later Apps Script fix ships on top of the 15 commits that have never run in
    production.
  - The rollback target is "the commit Ryan knows was live".
- **Fix.** One push on Ryan's go, then the tag. Optionally, `/land-checks` prints "appsscript/
  is N commits ahead of the last deploy tag". That would sit beside the workflow doc's item 13,
  which adds a step to `/land-checks` too.

### C. Jotform runtime builds not compared (L3 C2 E1)

- **What we emulate.** `glow/translation_lookup.py` emulates `formTranslation.v2.js`.
  `READ_BUILDS` holds 6 builds (`:68-71`).
- **What is uncompared.** BACKLOG 64 (its 2026-10-06 bullet) lists builds served that day that
  are not in `READ_BUILDS`:
  - template: `bc6c80d556a`;
  - Africa, Asia and Latin America: `8705c008453`;
  - U.S: `18bdf84aedc`.

  Eight distinct builds were seen between 2026-10-02 and 2026-10-06.
- **How it shows today.** Since #13, `form_status.py --rendered` names an uncompared build as a
  note, never as a problem (BACKLOG 64, its 2026-10-14 bullet).
- **Cost.** If the dictionary lookup changes, the names audit vouches for a form whose
  dictionary alters a girl's name, and the wrong name reaches Salesforce. The submit handler's
  `clearFieldOnHide` branch (item 67) sits in the same unread files.
- **Fix.** A diff of five functions per build. The risk is that nobody does it.

### D. An integration lapses silently (L2 C3 E2)

| Connection | Evidence | Who would notice |
|---|---|---|
| Jotform → Salesforce (the native V2 integration) | Revoked once, by the VPN freeze of 2026-09-30 (`docs/RUNBOOK.md:2768-2772`). Before launch nothing reached Salesforce from 2026-03-28 (BACKLOG 48). `tools/integration_status.py` reads the configuration, not delivery. | Someone reading the dashboard's "not submitting" table |
| Jotform → Google Drive (photos) | Jotform raises no alarm when the token lapses; the check is a monthly look by eye (BACKLOG 70) | Ryan, monthly |
| Sheet → GitHub (`SYNC_DISPATCH_TOKEN`, a fine-grained token, `appsscript/Dispatch.gs:17`) | HTTP errors are muted (`test/dispatch_test.js`, "HTTP errors are muted"). The expiry is recorded nowhere: `git grep -i expir` finds none. | Nobody. The 11:00 UTC cron (`.github/workflows/auto-sync.yml:19`) still runs, so the cost is up to a day's delay. |
| Mac → Salesforce (CLI login `glow`) | `glow/salesforce.py:105-119` refuses with a re-login message | The next run of a Salesforce tool |

- **Nothing checks delivery.** `tools/auto_sync.py` and `glow/` never query
  `Attendance_Batch__c` (`git grep`). The runner could compare each day's submissions per form
  with the batches in Salesforce, counts only.
- **The runner has no Salesforce credentials yet.** The `SF_SYNC` setup is not done
  (BACKLOG 27: none of the user, permission set, app or secrets existed on 2026-10-09). Until it
  is, the check would run from the Mac.

### E. Salesforce metadata only in `data/` (L2 C3 E2)

- **What lives only in `data/`:**
  - The processor's Apex (class, trigger, tests), as deployed and before:
    `data/sf_processor_2026-10-02/{before,after}` and `data/sf_totals_2026-10/{before,after}`.
  - The dashboard, its 13 reports, the report types and the generator `gen.py`:
    `data/sf_dashboard_2026-10-02/` (`docs/RUNBOOK.md:2653`).
  - The permission set and folder shares: `public_2026-10-09/`.
  - The Monthly Report change: `data/sf_monthly_report_2026-09-30/`.
  - `sfdx-project.json` (`sourceApiVersion` 65.0,
    `docs/plans/2026-10-06-attendance-totals.md:762`).
- **Rollbacks point there.** Redeploy `data/sf_processor_2026-10-02/before`
  (`docs/DECISIONS.md:317`) or `data/sf_totals_2026-10/before/` (`docs/RUNBOOK.md:2515`).
- **It has been lost before.** `/harness:land` deletes a worktree's `data/`. On 2026-10-09 one
  worktree held the only copies of 11 files (`CLAUDE.md:34`).
- **Changes are coming.** Within six months: #35 (relabel the dashboard tiles, in progress),
  BACKLOG 72 (the partners' count intake), 76 (adding girls to a day that has a batch) and 58
  (attendance rate). Each one is a metadata change without versioned source.
- **The workflow doc pulls the other way.** Its item 12 proposes a `/sf-metadata` skill and
  `tools/sf_package.py`, which write `package.xml` and `sfdx-project.json` under
  `data/sf_<topic>_<date>/`. That fixes how metadata is built and retrieved, but keeps the
  source in `data/`.
- **Fix (T4).** BACKLOG 82 as written: a `salesforce/` sfdx project in git, metadata only (no
  record data, no names), deployed check-only from there. How T4 and item 12 fit together is
  under "Proposed tickets".

### F. Stale RUNBOOK Status lines; its size (L3 C2 E2)

- **Size.** `docs/RUNBOOK.md` is 3,002 lines on the rebased branch.
  - It has 37 `##` sections, 31 `Status` lines, 100 lines inside code fences, and 179 lines
    that carry a `2026-` date.
  - The largest `##` sections: "Club accounts in Salesforce" (182 lines with its `###`
    parts), "Automatic sync" (181), "The names dictionary and the module values" (173),
    "Attendance dashboard in Salesforce" (160) and "Club names two partners share" (149).
- **Stale today.** All of these can be checked against the repository except the first:
  - **The dashboard's Access change.** Its `Status` (`:2572`) and the Access bullet
    (`:2608-2611`) say it waits for Ryan's deploy. Ryan says it is live (ticket #47's Context),
    but the plan's frontmatter still says `blocked`. Not verifiable offline.
  - **The table of contents** (`:19-62`) has no entry for "Special events" (`:828`).
  - **"Clubs that do not use Jotform"** (`:1639`) says "the runner runs it once `main` is
    pushed". `main` was pushed on 2026-10-13 (`docs/agent/handoff.md:13`).
  - **"Disabling a regional form"** (`:1252`) says the first run (the U.S form) is not recorded.
    The U.S form is `DISABLED` (`docs/agent/handoff.md:5`, `:12`).
  - **`GLOW_LIVE_OK`** still appears in the "Live gate (Claude Code)" section and in the clasp
    comment (`:2104`, `:2834`, `:2853`), but it no longer opens the gate (DECISIONS
    2026-10-14). #37 fixes this.
  - **The handoff.** `docs/agent/handoff.md:33` runs the retired `tools/worklog.py`, and
    `:15-16` describe the runner hold that DECISIONS 2026-10-14 removed. The handoff reaches
    `main` only through the monthly chore (#15). The next `/harness:handoff` rewrites it.
- **Waiting on Ryan.** 9 of the 31 `Status` lines say a step waits for Ryan or is "not
  recorded": `:991`, `:1079`, `:1115`, `:1252`, `:1639`, `:2026`, `:2095`, `:2262` and `:2572`.
  A Status line that waits on a person goes stale the day the person acts. A `needs-input`
  ticket on the board does not.
- **Fixed since the first draft.** #31 updated the "Special events" Status: IDG Celebrations
  has been live since 2026-10-14, and its plan is `done`.
- **Cost.** Claude reads the RUNBOOK as the truth. A stale status sends a session to redo a live
  step, or to skip one.

### G. Salesforce CLI unpinned; tools read its JSON (L2 C2 E1)

- **What the tools depend on.**
  - `glow/salesforce.py:108` reads the JSON of `sf org display` and
    `sf org auth show-access-token` (`result.instanceUrl`, `result.accessToken`).
  - `tools/sf_dupes.py:662` reads the JSON of `sf apex run`.
- **No version is recorded.** No file names a CLI version (`git grep '@salesforce/cli'` finds
  none). The first draft read 2.151.7 on this Mac with `sf --version`, a local command with no
  org call; this revision ran no `sf`.
- **API versions in use.** REST `v67.0` (`glow/salesforce.py:32`). The RUNBOOK's examples use
  `v62.0` (`:2616`, `:2704`).
- **Releases.** Salesforce's next release, Spring '27, falls inside the window. The processor's
  Apex tests run on any deploy, and their source is item E.
- **Cost.** The Mac's Salesforce tools stop: the monthly `sf_dupes.py check` and any back-fill.
  The runner uses client credentials, not the CLI, so it is unaffected.

### H. The harness commit that works is recorded nowhere; the invoice runs on it (L2 C2 E1)

- **What the workflow doc found** (its "Inventory", Harness plugin):
  - The plugin comes from a directory marketplace, `~/portfolio_projects/harness`.
  - The cache still lists `0.1.0` while sessions run the source `0.2.0`, which is "harmless
    while the marketplace is a directory".
  - The plugin's own upgrade is held until the usage reset on 2026-10-16.
- **What this item adds: the source moves under this repository.** DECISIONS 2026-10-14 relies
  on harness commits `07a4835` and `e372870`. The harness carries the invoice (`harness-worklog`,
  whose fixes "go to the harness repository"), the verify and land flow, and `HARNESS_*` in
  `.claude/settings.json:3-5`. Nothing here records which harness commit last worked.
- **Fix.** Record that commit (T11). Everything else about the plugin is the workflow doc's
  scope.

### I. Python 3.10 EOL, unpinned Google libraries on the live runner (L2 C2 E2)

- **Python 3.10 reached its end of life on 2026-10-04** (BACKLOG 80). The runner and CI pin
  `"3.10"` (`.github/workflows/auto-sync.yml:64`, `check.yml:18`), and ruff targets `py310`
  (`ruff.toml:6`).
- **Google has stopped supporting it.** `google.api_core` 2.34.0 in the venv (Python 3.10.4)
  warns on import (a FutureWarning, read with `python3 -W default`): "You are using a
  non-supported Python version (3.10.4). Google will not post any further updates to
  google.api_core supporting this Python version".
- **The runner's dependencies float.**
  - `requirements.txt` holds ranges (`>=2.100,<3`, `>=2.23,<3`), and `auto-sync.yml:65`
    installs them fresh on every run. An upstream release changes what the live sync runs,
    without a commit (BACKLOG 81).
  - pip honours `Requires-Python`, so a silent change in behaviour is more likely than a
    failed install.
- **Code to change:** `datetime.utcnow()`, deprecated in 3.12, at `tools/sf_backfill.py:139`
  and `:802`.
- **Not verified offline:** whether the actions in use face a runtime deprecation within the
  window (`actions/checkout@v4`, `setup-python@v5`, `upload-artifact@v4`, `setup-node@v4`).

### J. Python ↔ Apps Script duplicated rules (L2 C2 E3)

- **9 constants exist on both sides** (ARCHITECTURE "Constants that exist on both sides",
  `docs/ARCHITECTURE.md:128-136`, one table row each):
  1. `SF_NAME_SEP`;
  2. the Roster tab columns;
  3. the Partners tab columns;
  4. the sheet's time zone (the spreadsheet's own setting on the Apps Script side, checked by
     the runner);
  5. the response-tab header fragments;
  6. the SyncLog columns;
  7. the `Roster`, `Partners` and `SyncLog` tab names;
  8. the SF Pending columns;
  9. the region vocabulary.
- **The rest of the duplication:**
  - 6 parity bridges (`:138-171`).
  - 11 known-divergence bullets (`:173-229`), 8 of them Python versus Apps Script.
  - The tests: `test/gs_parity_test.py` (314 lines, 12 tests), `test/parity_test.js` (195
    lines) and `test/forms_logic_test.js` (2,971 lines). The last one also reads the
    divergence list and the constants table (`:1293-1297`).
  - CLAUDE.md rules 7 and 10, and BACKLOG 28 (three gaps open).
- **`appsscript/Regions.gs`.** Hand-kept since 2026-10-09 and last touched 2026-08-26
  (`git log`). Line 3 still says "GENERATED by tools/derive_partner_regions.py", a retired tool.
  The edit hook leaves it to Ryan (ARCHITECTURE "Generated and hand-kept files").
- **Cost.** In steady state few changes cross the line: the Roster columns, the shared-name
  rule, the Partners marker. When one does, it costs two implementations and a parity test.
- **What shrinks it: retiring the legacy enrollment path (item N).** That removes:
  - parity bridges 1 and 2;
  - constant 5, the response-tab header fragments;
  - four of the eight divergences: `read_sheet`'s partner-less rows, bullets, invisible
    characters in `parse_roster`, and `splitlines`.

  `parseRoster_` stays, because the Club Roster Form's REMOVE uses it
  (`appsscript/FormHandlers.gs:867`).

### K. `data/` and `backups/` exist on one Mac only (L1 C3 E1)

- **Rollback and undo files that exist only there.** These are named by the docs; none was read
  here.
  - `data/backfill_2026-09/` (`ledger.csv`, `created_contacts.csv`): the back-fill's only
    rollback (`docs/RUNBOOK.md:2774-2785`).
  - `data/module_fix_2026-10/ledger.csv`: the `--undo` (`:823`).
  - `data/sf_dupes_<date>/`: the merge's rollback.
  - `data/sf_prep_2026-09-30/created_accounts*.csv`: the 345 accounts' rollback (`:2254`), and
    BACKLOG 58's club → account map.
  - `data/deactivate_clubs/<stamp>/`: `--undo`.
  - `backups/`: form snapshots and translation stores. The runner uploads conditions backups
    only.
- **No off-Mac copy is documented** (`git grep -i "time machine"` finds none).
- **Fix: a decision by Ryan, not code.** The files hold minors' names, so any copy is governed
  like the original: encrypted and owner only (the `child-privacy` skill). This item only asks
  that the answer be written down.

### L. OAuth scopes not pinned in the manifest (L1 C3 E1)

- **The gap.** BACKLOG 37 is in progress: `appsscript/appsscript.json` has no `oauthScopes`
  list. A new Google service makes the form-submit trigger fail hard until the owner
  re-authorises (CLAUDE.md rule 11).
- **Already guarded.** `scripts/check_gs.js` pins the 8 services and fails on a ninth (`make
  gs`). The likelihood is low in steady state, so no new ticket.

### M. `hooks_test.py` is most of the verify run (L3 C1 E1)

- **Measured on 2026-10-15, before the rebase.** `scripts/verify.sh` took 87.9 s wall, and the
  Python suite ran 738 tests in 82.4 s. `test/hooks_test.py` alone took 75.9 s for 29 tests.
  The next slowest module took 2.5 s.
- **The rebased branch.** The suite ran 758 tests in 58.0 s, and `hooks_test.py` alone took 50.9 s
  for its 29 tests. It is still most of the run, though the run time varies between runs.
- **Cost.** The verify command runs on every stop hook, every red check and every review round.
- **Overlap.** The workflow doc's item 6 (the stop hook in a red worktree, a harness-plugin
  fix) and #46.

### N. Legacy enrollment path and the Rebuild menu item (L1 C3 E2)

- **No one calls the path.** `sync_attendance_form.py:528` calls `read_sheet()` only without
  `--roster`. No doc, skill or tool runs the sync without `--roster` (`git grep`), and the
  runner passes it (`tools/auto_sync.py:526`).
- **The rebuild is pre-launch only.** RUNBOOK "Roster rebuild and upload (offline path)"
  (`docs/RUNBOOK.md:1841-1861`) says so: "pre-launch only, never after 2026-09-01". A rebuild
  "reactivates every girl removed through the Club Roster Form … re-creates any enrolled club
  that was renamed or moved".
- **The menu item is still live.** "Rebuild roster from enrollment responses" is in the GLOW
  menu (`appsscript/Menu.gs:8-9`). Its YES/NO is undeployed (item B), and BACKLOG 39 is open.
- **What the path keeps alive:**
  - `glow/sync.py` `parse_roster` and `read_sheet` (`:730-777`), and the `COL_*` constants;
  - `Normalize.gs readResponses_` and `Roster.gs rebuildRosterLocked_`;
  - `tools/build_roster_offline.js` (273 lines) and `tools/upload_roster.py` (186);
  - `test/fixtures/make_fixture.py` and `make fixtures-check`;
  - the real-CSV branch of `test/forms_logic_test.js:2939`, which reads
    `data/enrollment_2026-08-24.csv` when present. That branch makes the suite differ between
    Ryan's Mac and CI.

### O. Tests that pin prose (L3 C1 E2)

- **How many read the docs.**
  - At least 64 Python test methods read a tracked `.md` file (a method-level `git grep` for
    `"docs"`, `.md"` and the section helpers).
  - `test/runbook_test.py` (1,360 lines) holds 40 tests. 36 of them sit in doc-reading
    classes, `RolloutProcedures` (5) and `FixHintsRunbook` (3) among them, both new with #31
    and #33.
  - In `test/special_events_test.py`: `IdgDocs` (5) and `RunbookQuotes` (1).
  - In `test/forms_logic_test.js`: 8 checks read the RUNBOOK or ARCHITECTURE.
- **What they pin.**
  - `RunnerRunbook` (`test/runbook_test.py:550`) keeps 9 `HOLDS` phrases (`:581`), 20
    `OTHER_WORDS` (`:589`) and a regex (`:595`) out of the live docs.
  - `RolloutProcedures` keeps `AUTO_SYNC_APPLY` toggles out of every rollout paragraph.
  - `WorkLogRunbook` wants its heading "word for word" and three bold paragraphs.
  - The whole-file reads are listed under "Doc consolidation".
- **Value and cost.** Each one protects a real contract: a tool's quoted line, or a decision's
  wording. But together they turn any doc move into a test change.
- **Overlap.** #46 ranks these tests as friction, and the workflow doc's item 4 covers the
  breaker probing them. This document only uses them to constrain the consolidation.

### P. Two backlogs: BACKLOG.md and the board (L3 C1 E2)

- **`docs/BACKLOG.md`** runs to 758 lines and has 94 item sections: 42 `open`, 8
  `in-progress`, 20 `blocked-on-ryan`, 18 `done` and 6 `dropped`. New work is a ticket
  (DECISIONS 2026-10-14), so 70 live items sit outside the board.
- **Items already overtaken:**
  - Item 47 ends "re-count 35's empty submissions for two weeks (to 2026-10-14)". The window
    has closed and no result is recorded.
  - Item 31, plan mode by default after launch week, predates the harness.
  - Item 53 is `in-progress`, but #36 gated `sf` and `gh api` writes.
  - Item 83 closes with #37.
  - Item 1a, the key rotation, has been `blocked-on-ryan` since launch.
- **Cost.** Nothing breaks. The plan is split across two places, so a session has to read both.

### Q. One-off tools and one-time menu items (L2 C1 E1)

- **Why they cost.** Each one-off must keep passing `make check` against today's `glow/`
  (DECISIONS 2026-10-09, "Finished one-offs are deleted, not archived").
- **What they add up to:**
  - `tools/fix_module_values.py`, `sf_girls_present.py`, `sf_backfill.py`, `backfill_resolve.py`,
    `fix_roster_order.py` and `fix_name_translations.py`: 2,871 lines, plus
    `glow/submissions.py` (147 lines).
  - Their tests: another 3,443 lines (435 + 264 + 1,090 + 1,059 + 595), plus their share of
    `links_layout_test.py`, which is not counted.
  - 4 one-time or pre-launch GLOW menu items (`appsscript/Menu.gs:8-9`, `:18-21`, `:26`).
- **The candidates with their dates** are under [Retirement candidates](#retirement-candidates).

### R. Plan and intent statuses drift (L2 C1 E1)

- **The count.** 44 plans (12,593 lines) and 11 intents: 37 `done`, 10 `in-progress`, 5
  `blocked`, 2 `proposed`, 1 `superseded`.
- **The check.** `docs_index.py --check` enforces the vocabulary, not the truth.
- **A drifted status.** `2026-10-09-attendance-reports-public.md` is `blocked`, but its change
  is live per Ryan (item F).
- **It has happened before.** DECISIONS 2026-10-09 ("A plan is required…") found the same drift
  and fixed it once.

### S. Node 18 + clasp 2.4.2 (L1 C2 E2)

- **The pin.** clasp 2.4.2 runs on Node 18 (DECISIONS 2026-08-27: "clasp 3 needs Node 20").
  The `clasp:push` script refuses any other Node (`package.json`), and CI's JS checks run on
  Node 18 (`.github/workflows/check.yml:15`).
- **Node 18 is past its end of life** (April 2025). The Mac's default Node is v26.10.0, so a
  push needs `nvm use 18` (`.claude/skills/deploy-appsscript/SKILL.md:32`).
- **Cost.** The deploy path fails until someone migrates to clasp 3 (a new login and new flags).
  The fallback is pasting 10 files into the editor.
- **Plan.** Watch. Upgrade when clasp 2.4.2 or Node 18 stops installing, or with the next Apps
  Script change after item B.

### T. Dashboard Partner filter at 49 of 50; two partner lists (L1 C2 E2)

- **The filter.** It holds 49 typed partner names, and Salesforce allows 50
  (`docs/RUNBOOK.md:2590-2598`; BACKLOG 60, part 6). A 51st partner needs another layout.
- **Two lists.** A new or renamed partner must be added by hand to both the dashboard's
  `partners.json` (in `data/`, item E) and `glow/sf_partners.csv`.
- **Likelihood.** Steady state means few new partners.

### V. DECISIONS.md growth (L1 C1 E1)

615 lines and 84 decisions, append-only by its own rule (`docs/DECISIONS.md:1-9`). Long but
well-formed. Nothing to do.

### U. `FormHandlers.gs` at 1,353 lines (L1 C1 E2)

BACKLOG 86 applies "if it keeps growing", and in steady state it should not. Nothing to do.

## Knowledge outside git

Taken from what the tracked docs and code say lives elsewhere; nothing under `data/` was read.

| What | Where it lives | Risk item |
|---|---|---|
| Processor Apex, its tests, the dashboard and reports, `gen.py`, permission sets, `partners.json` | `data/sf_*` on one Mac | E, T |
| Back-fill, module-fix, girls-present and merge ledgers; account and deactivation rollback files | `data/` on one Mac | K |
| Form snapshots and translation stores | `backups/` on one Mac (the runner keeps conditions backups as artifacts) | K |
| Jotform's Salesforce V2 mapping, the Drive integration, the header logo upload | Jotform's builder. Only the mapping is read back (`tools/integration_status.py`). The Drive set-up and the logo are Ryan's steps (`docs/RUNBOOK.md:1079`, `:1115`). | D |
| The `SF_SYNC` setup (integration user, permission set, External Client App, two secrets) | Not done as of 2026-10-09 (BACKLOG 27) | D |
| The dispatch token's expiry; whether GLOW pays the nonprofit rate | Nowhere | D, A |
| Which Apps Script commit is deployed | Ryan's memory (no tag) | B |
| The harness commit that works with this repository | `~/portfolio_projects/harness`, unrecorded | H |
| What is stuck on Ryan | 20 `blocked-on-ryan` BACKLOG items and 9 RUNBOOK Status lines | F, P |

## Retirement candidates

**How a retirement is done.** ARCHITECTURE [Retired tools](../ARCHITECTURE.md#retired-tools)
sets the steps:

1. Delete the tool and its tests.
2. Add a row: Path, What it did, Retired in, and Restore with `git show <commit>^:<path> >
   <path>`.
3. Run `make check`.

Earlier rows name the deleting commit (`7c24ac7`, `608bcd2`, `0dc0d4c`, `648947e`) or the
ticket and commit (#10, `459451d`). Restoring a `.gs` file also means an Apps Script push, so
it needs Ryan's go (CLAUDE.md rule 1).

| Tool or code | Why it exists | Retire after | Restore path |
|---|---|---|---|
| `tools/fix_module_values.py`, `test/fix_module_values_test.py` | The one-off `Module__c` correction of 2026-10-07 and its `--undo` | **2026-11-01**, when the undo window closes at the end of October (BACKLOG 84). RUNBOOK "The names dictionary and the module values" keeps a one-line SOQL audit in place of its paragraph (`:815-826`). The ledger stays in `data/`. | `git show <commit>^:tools/fix_module_values.py`; the test likewise |
| `tools/sf_girls_present.py`, its test | The one-off `Girls_Present__c` back-fill (done 2026-10-07, 573 written). It has no undo command (`.claude/skills/salesforce/SKILL.md:61`). Its `check` is a health check (`docs/RUNBOOK.md:2558`). | When its two `check` counts move into RUNBOOK "Attendance totals and partner-reported counts" as SOQL, or into the monthly `sf_dupes.py check`. Earliest 2026-11-01, after one clean monthly look. | `git show <commit>^:tools/sf_girls_present.py` |
| `tools/sf_backfill.py`, `tools/backfill_resolve.py`, `glow/submissions.py` (147 lines), their tests (`test/sf_backfill_test.py`, `test/backfill_resolve_test.py`, which also tests `glow/submissions.py`) | The September back-fill, done 2026-10-02. The RUNBOOK keeps both tools as the incident procedure (`:2758-2766`), but the window is hard-coded (`backfill_resolve.py:54-57`), and rollback by contact is now dangerous (`:2778-2785`). `glow/submissions.py` is used only by `backfill_resolve.py` and `fix_module_values.py` (`git grep`). | When BACKLOG items 76 (11 held sessions) and 78 (the guard) are settled, T8 has retired `fix_module_values.py`, and Ryan chooses between generalising the window (flags, not constants) and retiring both. BACKLOG 65's `q18_empty` watch uses the resolver, so move it first. With the tools gone, `glow/submissions.py` goes too, with its line in `glow/__init__.py` and its ARCHITECTURE row. | `git show <commit>^:tools/sf_backfill.py`, `…:tools/backfill_resolve.py`, `…:glow/submissions.py` (all from the one deleting commit) |
| `tools/fix_roster_order.py` (and `FixRosterOrderTool` in `test/links_layout_test.py`) | The one-time repair of 2026-09-30 (BACKLOG 47). RUNBOOK "Rosters above Submit" (`:1053-1075`) keeps its relapse and new-form procedure. | **Not yet.** It is still the fix `form_status.py` prints (`glow/layout.py:30` `FIX`, pinned by `test/links_layout_test.py:913`). It can go once that hint names a sync apply instead, which is one of epic #29's follow-ups ("form_status's 'sync apply by hand' hints"), and no form has needed it for six months (2027-04-01). | `git show <commit>^:tools/fix_roster_order.py` |
| `tools/fix_name_translations.py` | Removed 55 stale dictionary entries (2026-10-06). It has `--restore`, and BACKLOG 63's pruning would be built here. | When BACKLOG 63 is dropped or done. `NamesAndModulesRunbook` (`test/runbook_test.py:509`) pins its commands in the RUNBOOK and changes with it. | `git show <commit>^:tools/fix_name_translations.py` |
| GLOW menu: `migrateCountryToRegion`, `retireOldEnrollmentForm` (`appsscript/Forms.gs`) | One-time migrations (BACKLOG items 38 and 6) | When the live Audit tab shows each has run, or its item is settled another way (BACKLOG 85) | `git show <commit>^:appsscript/Forms.gs` and `Menu.gs`, then a push |
| GLOW menu: `migrateFormWording` | The one-time wording run (BACKLOG 43, not yet run) | After Ryan's run is recorded | As above |
| The legacy enrollment path: the sync without `--roster` (`read_sheet`, `parse_roster`, `COL_*`); `readResponses_` and the Rebuild menu item; `tools/build_roster_offline.js` and `tools/upload_roster.py`; `test/fixtures/make_fixture.py` and its two outputs; parity bridges 1 and 2 | The pre-launch import and rebuild (item N) | When Ryan confirms that a rebuild from the raw responses is never wanted (BACKLOG 39) and names the recovery path for a damaged Roster tab (the sheet's version history) | `git show <commit>^:<path>` for each. The archive keeps the commands (`docs/archive/runbook-roster-rebuild.md`). |
| `appsscript/Regions.gs` | Prefills a region where the Partners tab has none | When the Region picker is live (BACKLOG 38) and every Partners row has a region (Ryan reads the count). The edit is Ryan's, because the hook protects the file. | `git show <commit>^:appsscript/Regions.gs`, then a push |

## What to upgrade, and when

| What | Now | When | Note |
|---|---|---|---|
| Python | 3.10 (EOL 2026-10-04) | **Before 2026-12-31** (T10) | Move CI, the runner, the venv and `ruff.toml` to 3.12, and fix the two `utcnow()`. One dry run on 3.12, then one watched applying run (BACKLOG 80). |
| Runner dependencies | Ranges, installed fresh on every run | With Python (T10) | A `requirements.lock` from `pip freeze`, refreshed on purpose (BACKLOG 81) |
| Salesforce CLI | Recorded nowhere | Record it now (T11); update on purpose, then run one read-only tool | |
| Salesforce API | REST `v67.0`; the project at 65.0 | No change. After each Salesforce release (next: Spring '27), run a check-only deploy of the processor from git (needs T4). | |
| Node + clasp | 18 + 2.4.2 | When it breaks, or after item B | clasp 3 needs Node 20 and a new login |
| GitHub Actions | checkout@v4, setup-python@v5, upload-artifact@v4, setup-node@v4 | When the run annotations warn | Not verified offline |
| Harness plugin | Directory marketplace; the working commit unrecorded | Record the commit now (T11). The plugin upgrade itself waits for the usage reset (workflow doc, "Inventory"). | |

## Doc consolidation

**A decision constrains this section.** DECISIONS 2026-10-09 ("The docs stay one file each…")
rejected splitting the RUNBOOK into `docs/runbook/`. The reason: the section references and the
tests that read the whole file would break. This proposal keeps that decision, and does not
recommend amending it.

**The finding.** The 2026-10-09 cleanup already did the "operations guide plus archived
history" split:
- finished procedures moved to their plans, under `## From the RUNBOOK (moved 2026-10-09)`;
- the original plan and the offline rebuild went to `docs/archive/`;
- the RUNBOOK kept a stub with a link.

Re-checked against the rebased branch, what remains is mostly live procedure:
- **"Rosters above Submit"** (`:1053-1075`) holds the relapse and new-form steps of
  `fix_roster_order.py`, the fix `glow/layout.py:30` prints.
- **`### The one-time switch`** (`:1598-1607`) is what a new regional clone still needs.
- **The rollout paragraphs** in "One club per submission (the club guard)", "The names list sent
  to Salesforce" and "Special events" already link to their plans' moved text.
- **"Work log and invoices"** is the monthly chore, pinned by `WorkLogRunbook`.

So the RUNBOOK's length is procedure. The proposal is a short routine page at the top, a status
sweep, and retirements that take their paragraphs with them.

### What moves or shrinks (each only with its condition)

- **`fix_module_values.py`'s paragraph** (`:815-826`, 12 lines) becomes one SOQL audit line.
  Condition: T8, after 2026-11-01.
- **`sf_girls_present.py`'s one-off paragraph** (`:2551-2555`) moves to its plan, and its
  `check` signal becomes SOQL. Condition: T8.
- **"Roster rebuild and upload (offline path)"** (`:1841-1861`, 21 lines) becomes a retired stub
  of about 5 lines. Condition: T9. The heading stays, because `Roster.gs` and `INSTALL.md` quote
  it.
- **"September back-fill: the resolver" and "Back-fill of attendance into Salesforce"**
  (`:2729-2786`, 58 lines) become stubs. Condition: the back-fill tools retire. Both headings
  stay, because their tools and the salesforce skill quote them.
- **"Club accounts in Salesforce"**: two sentences about the retired `sf_club_accounts.py`
  move to `plans/2026-09-30-salesforce-clubs.md`. About 4 lines; no condition.
- **The 9 Status lines that wait on Ryan** become "live since …" or "not live: #N", and the
  waiting itself becomes a `needs-input` ticket (T6). About 9 lines.

### What is deleted

- **"Data-quality report"** (`:2186-2195`, 10 lines) and its contents line (`:49`). It is a
  retired tool's stub, and no file quotes it; ARCHITECTURE "Retired tools" already holds the
  restore.

### What is added

- **A short "Routine" list** at the top of the RUNBOOK, about 30 lines (T7). It names what
  recurs and links each section:
  - daily: the runner's SyncLog, "Automatic sync";
  - Monday: the e-mail's SF Pending list, "Club accounts in Salesforce";
  - monthly:
    - the `sf_dupes.py check`, "Duplicate girls in Salesforce";
    - the Drive folder look, "Photos";
    - `form_status.py --rendered` and the runtime-build note, item C;
  - month end: the work-log chore, "Work log and invoices".

  This is the short operations guide; the procedures stay where they are.
- **The contents gain "Special events".**

### What stays

Every other procedure, with its When, Status, Dry run, Apply, Verify and Rollback, including
"Rosters above Submit", `### The one-time switch` and "Work log and invoices".

### Expected saving

Re-estimated against the rebased branch:
- about 25 lines now (the deleted section, the Club accounts sentences, the Status lines);
- about 55 after T8 and T9;
- about 100 if the back-fill tools retire too.

Against that, the Routine list adds about 30. The net is within ±3 % of 3,002 lines, so the
RUNBOOK's length is not a risk to buy down; its Status lines are.

### Headings that must stay

A move must not rename any of these. **Refs** counts the tracked files whose text quotes the
heading in `scripts/check_doc_refs.py`'s patterns (run on the rebased branch). **Read by tests,
scripts and tools** comes from a re-audit: every file in `test/` and `scripts/` that opens a doc
by name (`git grep` for `RUNBOOK.md`, `ARCHITECTURE.md`, `BACKLOG.md`, `DECISIONS.md`), and
every tool or `.gs` file that prints the heading. Substring matches of short headings
("Translations", "Photos", "The forms") that are not about the RUNBOOK were dropped. A heading
read by a test needs a test change to rename; one printed by a tool needs a code change.

| Heading | Refs | Read by tests, scripts and tools |
|---|---|---|
| The forms | 3 | `glow/links.py` (message) |
| Keeping the forms in step with the Roster (the manual loop) | 0 | none |
| Automatic sync | 11 | `test/runbook_test.py` (`SameNameRunbook`, `ContactIdsRunbook`, `RunnerRunbook`, `RolloutProcedures` "**Switches:**"); `test/special_events_test.py` (`RunbookQuotes`); `.github/workflows/auto-sync.yml`, `appsscript/Dispatch.gs` (messages) |
| Backup and restore (Jotform) | 0 | none |
| The Club picker (mentors choose their club instead of typing it) | 1 | none |
| One club per submission (the club guard) | 5 | `test/runbook_test.py` (`RolloutProcedures.ROLLBACKS`) |
| The names list sent to Salesforce | 11 | `test/runbook_test.py` (`ContactIdsRunbook`, `RunnerRunbook`, `RolloutProcedures`); `test/sync_conditions_test.py`, `test/auto_sync_test.py` (quoted messages); `sync_attendance_form.py`, `restore_conditions.py`, `tools/auto_sync.py`, `tools/form_status.py` |
| The names dictionary and the module values | 7 | `test/runbook_test.py` (`NamesAndModulesRunbook`, `RunnerRunbook`, `RolloutProcedures`); `tools/auto_sync.py`, `tools/form_status.py`, `tools/fix_name_translations.py` |
| Special events | 10 | `test/runbook_test.py` (`RunnerRunbook`, `RolloutProcedures` "**Add a type**" / "**Retire a type**", `FixHintsRunbook`); `test/special_events_test.py` (`RunbookQuotes`, `IdgDocs`: the heading exactly once, its Status line names both types; `EventHintsByFormKind`: the tool's hint); `test/auto_sync_test.py`; `glow/sync.py`, `sync_attendance_form.py`, `tools/auto_sync.py`, `tools/form_status.py` |
| Translations | 2 | none |
| Links above Submit (problem report, Club Roster Form) | 2 | none |
| Rosters above Submit | 3 | none (`RosterRepairRunbook` reads the plan's moved copy) |
| Header logo | 3 | `tools/update_static_fields.py` |
| Photos | 7 | `tools/auto_sync.py`, `tools/integration_status.py` |
| Disabling a regional form | 4 | `tools/deactivate_clubs.py`, `tools/disable_form.py` |
| Building a new regional form (not maintenance) | 1 | none |
| Renaming a club | 4 | `test/runbook_test.py` (`SameNameRunbook` splits on it); `tools/rename_club.py`, `tools/sf_new_clubs.py` |
| Moving a club to another partner (a mistyped partner) | 5 | `test/forms_logic_test.js` (`:2280-2286`: the ReviewQueue's same-name row must name it); `tools/rename_club.py` |
| Club names two partners share | 11 | `test/runbook_test.py` (`SameNameRunbook`); `test/retired_rosters_test.py`, `test/forms_logic_test.js` (quoted messages); `sync_attendance_form.py`, `tools/auto_sync.py`, `tools/rename_club.py` |
| `### The one-time switch` | 0 | none in the RUNBOOK (`SameNameRunbook` reads the plan's copy) |
| Clubs that do not use Jotform | 11 | `test/retired_rosters_test.py`, `test/auto_sync_test.py` (quoted messages); `glow/sync.py`, `sync_attendance_form.py`, `tools/auto_sync.py` |
| Deactivating a club | 3 | `test/club_tools_test.py` (the tool's output); `tools/deactivate_clubs.py` |
| Roster rebuild and upload (offline path) | 4 | `appsscript/Roster.gs` (message) |
| Working the ReviewQueue | 10 | `test/forms_logic_test.js` (`:2276-2286`: a bold row per `REVIEW_ISSUES`, the same-name row's wording); `scripts/check_doc_refs.py` (the table's issue names); `appsscript/FormHandlers.gs` |
| Missed form responses | 6 | `test/forms_logic_test.js` (`:2287-2289`); `appsscript/FormHandlers.gs`; `scripts/check_gs.js` (comment) |
| Google Forms wording | 3 | `test/forms_logic_test.js` (`:2434-2440`: its Rollback bullet); `appsscript/FormHandlers.gs`, `appsscript/Forms.gs` |
| Apps Script deploy | 5 | `test/forms_logic_test.js` (`:2024-2027`: the rollback names `986a325` and the held new clubs) |
| `### Rolling back appsscript/` | 4 | the deploy and live-systems skills |
| Data-quality report | 0 | none |
| Club accounts in Salesforce | 6 | `tools/auto_sync.py`, `tools/sf_new_clubs.py` |
| `### New clubs' accounts, automatically` | 3 | `tools/sf_new_clubs.py` |
| Duplicate girls in Salesforce | 2 | `tools/sf_dupes.py` |
| Attendance totals and partner-reported counts | 4 | the salesforce skill |
| Attendance dashboard in Salesforce | 5 | the salesforce skill |
| September back-fill: the resolver | 2 | `tools/backfill_resolve.py` |
| Back-fill of attendance into Salesforce | 5 | `tools/sf_backfill.py`, `glow/salesforce.py` (message) |
| Credentials | 4 | `tools/backfill_resolve.py`, `tools/fix_module_values.py`, `tools/integration_status.py`, `tools/sheets_client.py` |
| Live gate (Claude Code) | 5 | `test/hooks_test.py:211` (the gate's reason); `.claude/hooks/live_gate.sh` |
| Work log and invoices | 7 | `test/runbook_test.py` (`WorkLogRunbook`: the heading word for word, and the bold "Time zones.", "Which sessions count." and "What `update` will not do without being asked." paragraphs) |
| Checks | 1 | none |

### Tests that read more than a heading

Name these in any ticket that moves text.

**Tests that read the whole RUNBOOK** (a text they read must stay somewhere in that file):

- `test/forms_logic_test.js`:
  - `:2015-2023`: the paragraphs that start `**Held new clubs and a rollback` and
    `**Same-name holds and a rollback`.
- `test/links_layout_test.py:274-278`: the public-URL table.
- `test/retired_rosters_test.py:619-621`: "`attention`, `skipped`, `failed`".
- `test/special_events_test.py` `IdgDocs`: no "special events: 1 type(s)" anywhere.
- `test/runbook_test.py`:
  - `RunnerRunbook`: the `HOLDS` and `OTHER_WORDS` phrases, across the RUNBOOK, ARCHITECTURE,
    README, the skills and three code files.
  - `RolloutProcedures`: every rollout paragraph, and no `AUTO_SYNC_APPLY` toggle.
  - `FixHintsRunbook`: no "wording predates", in the RUNBOOK and ARCHITECTURE.

**Tests that read inside one section:**

- `test/runbook_test.py`:
  - `ContactIdsRunbook`: steps ` 6. ` and ` 7. `, `**Rollback**`, and the language-switcher
    paragraph of "The names list sent to Salesforce".
  - `RolloutProcedures`: the Apply and Rollback lines of four sections.
  - `FixHintsRunbook`: the hint sentences in "Special events".
- `test/forms_logic_test.js`: the four RUNBOOK sections above.

**The other docs:**

- ARCHITECTURE:
  - `test/gs_parity_test.py:302`: "Constants that exist on both sides".
  - `test/forms_logic_test.js:1293-1297`: "Known divergences", and `SF_NAME_SEP` among the
    constants.
  - `test/runbook_test.py`: "Retired tools", "Components" and the `tools/form_status.py`
    row.
- DECISIONS: `test/runbook_test.py`, for the decisions `RunnerRunbook.AMENDED` names and the
  work-log decision's Why, Rejected and Consequences.
- BACKLOG: `test/runbook_test.py` (`backlog_item`), `scripts/check_doc_refs.py`,
  `scripts/docs_index.py`.
- Plans:
  - `test/runbook_test.py` `moved()` reads only `## From the RUNBOOK (moved 2026-10-09)`. A new
    move needs a new heading and its own reader.
  - `test/special_events_test.py` `IdgDocs` reads the IDG plan.
  - `scripts/docs_index.py` reads every plan's frontmatter.

### The other docs

- **BACKLOG.md: freeze it.** Its rules, `doc-refs` and the references stay. Triage the 70 live
  items once (T14). Each becomes:
  - a ticket, if it is wanted within six months;
  - `dropped`;
  - or stays `open` as a parked idea, with a dated bullet.

  Its header gains one line: nothing new is planned here.
- **Plans and intents** stay where they are, because RUNBOOK links and `moved()` read them.
  Their drifted statuses are fixed in T6.
- **DECISIONS.md:** no change.
- **`docs/agent/`:** this file, the two sibling findings and `harness-prep.md` are dated
  inventories. They can move to `docs/archive/` when their tickets close.

## Proposed tickets

Nothing is filed; Ryan picks (epic #45). Size and risk use the board's labels. Value is what the
risk ranking says the ticket removes. The overlaps were re-checked with
`gh issue list --state open --limit 100` on 2026-10-15. Open now: #6, #15, #29, #34, #35, #37,
#45, #46, #47. #31, #33, #38 and #48 are closed. In the table, "WF" means
`docs/agent/2026-10-workflow.md` (#48, landed).

| # | Title | Size | Risk | Value | Overlap |
|---|---|---|---|---|---|
| T1 | Decide Jotform storage, Gold or retention, before the 50 % warning (BACKLOG 68) | S (a decision; `needs-input`) | low | high (A) | none |
| T2 | Deploy and tag the 2026-10-09 Apps Script; `/land-checks` reports `appsscript/` ahead of the last tag | S | medium (the live intake; Ryan's push) | high (B; also lands the Rebuild YES/NO, N) | WF item 13 also adds a `/land-checks` step: one edit of that skill. |
| T3 | Compare the uncompared Jotform runtime builds; add them to `READ_BUILDS` (BACKLOG 64) | S | low (offline after one GET per page) | medium-high (C) | #34 (the runner reads `--rendered` after a rules change, and could carry the build note) |
| T4 | Salesforce metadata into git as a `salesforce/` sfdx project, metadata only, deployed check-only from there (BACKLOG 82). Reconcile with WF item 12 (below the table). | M | low (no deploy) | high (E; makes #35's dashboard change reviewable) | #35 (do T4 first, or let #35 start the project); WF item 12 and its proposed ticket "Add `tools/sf_package.py` and the `/sf-metadata` skill" |
| T5 | A read-only delivery check: each form's submissions against `Attendance_Batch__c` per day, counts only; record token expiries in RUNBOOK "Credentials" | M | low (read only) | high (D) | #34 (the same verify step in `tools/auto_sync.py`); BACKLOG 27 (the runner's Salesforce credentials; until then from the Mac); BACKLOG 62 |
| T6 | Status sweep: the RUNBOOK contents, the stale Status lines of item F, the drifted plan statuses; waiting steps become `needs-input` tickets | S | low | medium (F, R) | #37 (in review: the Live gate section and `GLOW_LIVE_OK`); #35 (the Attendance totals section); #15 (the handoff's stale lines land through the monthly chore, not here) |
| T7 | A "Routine" list at the top of the RUNBOOK, linking the sections | S | low | medium (F) | WF item 1 (a `/form-rollout` skill) is the per-change procedure; this is the recurring one |
| T8 | Retire `tools/fix_module_values.py` (after 2026-11-01) and `tools/sf_girls_present.py` (its check moved), with their ARCHITECTURE rows and RUNBOOK paragraphs | S | low | low-medium (Q) | none (BACKLOG 84) |
| T9 | Retire the legacy enrollment path and the Rebuild menu item after Ryan confirms (BACKLOG 39, 28), in two parts: (a) Python, fixtures and `upload_roster.py` (M); (b) Apps Script with the next push (S) | M + S | medium (sync argument parsing; a push) | medium (N; shrinks J by two bridges, a constant and four divergences) | #46 (legacy code); T2 (part (b) rides on the next push) |
| T10 | Python 3.12 and a runner lockfile (BACKLOG 80, 81) | M | medium (CI runs the live sync: a dry run, then one watched apply) | medium (I) | none |
| T11 | Record the Salesforce CLI version and the working harness commit; an offline test over a recorded `--json` answer of each CLI shape the tools read | S | low | medium (G, H) | WF "Inventory" (the plugin's cache label; its upgrade waits for 2026-10-16); #6 (the harness v2 adoption epic) |
| T12 | Make `test/hooks_test.py` fast (51-76 s of a 58-82 s Python suite) | S-M | low (tests only; the hooks unchanged) | medium (M) | WF item 6 (the stop hook in a red worktree) and item 9 (hook tests on a draft copy); #46 |
| T13 | Write down the off-Mac copy of `data/` and `backups/`, or its absence (a decision under the `child-privacy` rules) | S | medium (minors' data) | medium (K) | none |
| T14 | BACKLOG triage: the 70 live items become tickets, `dropped` or parked; the header says the file is frozen | S-M | low | low-medium (P) | #37 (closes item 83) |

**T4 and the workflow doc's item 12.** They point in opposite directions. Item 12 builds and
retrieves packages under `data/sf_<topic>_<date>/`, because the Write tool may not write
there; T4 moves the metadata into git. One direction should win:

- **T4 first (recommended).**
  - `salesforce/` in git holds the source and `package.xml`. It is metadata only: report and
    filter definitions name partners and clubs, which the repository already holds, and never
    girls.
  - `/sf-metadata` (item 12) runs against that project: build in git, check-only, Ryan's go,
    quick deploy, then retrieve and compare.
  - Only the live "before" retrieve, the rollback copy, stays under `data/`, and that retrieve is
    committed after the deploy.
  - `tools/sf_package.py` is then a small helper for the retrieve, and the `protected_paths`
    obstacle in item 12 disappears for the build itself.
- **Item 12 as landed.** The source stays in `data/`, item E keeps its score, and K's loss risk
  covers the Apex too.

Ryan picks one before either ticket is planned.

## Could not verify (offline)

- **The dashboard's 2026-10-09 Access change.** The ticket's Context (Ryan, 2026-10-14) says it
  is live; the repository says it is not.
- **Which runtime builds the forms serve today.** BACKLOG 64 lists those of 2026-10-06.
- **Jotform's behaviour at the upload cap, and GLOW's billing rate.**
- **The expiry of `SYNC_DISPATCH_TOKEN`**, and whether the Jotform → Salesforce connection is
  healthy now.
- **Whether GitHub's runner images or the action majors in use face a deprecation inside the
  window.**
- **The Salesforce CLI version.** It was read once in the first draft (`sf --version`, local).
  Nothing pins it, and this revision ran no `sf`.
- **The savings estimates** in "Doc consolidation". They come from the section line counts on
  the rebased branch; nothing was moved to measure them.
