# Architecture

## The flow

```
partner / mentor
   │  Google Form "Global Catalyst – Club Roster Form" (new club, or add/remove girls)
   ▼
master enrollment Google Sheet ── tab "Roster Form Responses"
   │  installable on-form-submit trigger
   ▼
appsscript/FormHandlers.gs  onAnyFormSubmit → processResponseRow_ (FormLog dedupe)
   ├─ handleNewClub_      → RosterOps.gs newClubHoldReasons_ (a possible duplicate, or a club name another
   │                        partner's club has → HELD for staff) / planClub_
   └─ handleRosterChange_ → RosterOps.gs planModification_
   ▼
Roster.gs applyRosterPlan_ → tab "Roster"  (ONE ROW PER GIRL = the source of truth)
   │  ids minted by Ids.gs mintGirlId_ / clubCode_; ReviewQueue, Audit, SF Pending, mentor email
   │  Dispatch.gs tryNotifySync_ → GitHub repository_dispatch "roster-changed"
   ▼
.github/workflows/auto-sync.yml → tools/auto_sync.py
   │  sheets_client.read_tab("Roster") → per region:
   │  sync_attendance_form.py (dry run) → bands → backup_forms.py → sync --apply → form_status.py
   │  → tab "SyncLog"
   ▼
four regional Jotform attendance forms   (one hidden checkbox question per club = the roster)
   │  mentor ticks the girls present
   ▼
Jotform native Salesforce V2 integration → Attendance_Batch__c
   Account_Name__c ← qid 5 (the club's Salesforce name: its own name, or "<club> - <partner>" when
   another partner's club has that name — the club's Club-picker entry, copied by a calculation),
   Contact_IDs__c ← qid 18 (ONE aggregate calculation over every
   roster, "ignore hidden fields" on, so only the visible club's ticked names arrive; with the
   Club picker it is rule 0 - Jotform walks a field's rules last to first, so it runs after the
   rosters are shown or hidden - and lists the picker as an operand; every roster is required,
   and Jotform validates only the shown one - docs/plans/2026-09-30-contact-ids.md; each
   ticked name passes through the form's own translation dictionary, which must alter none -
   docs/plans/2026-10-02-names-and-modules.md),
   Module__c / Module_Week__c / Module_Year__c ← qids 98 / 100 / 102 (copies of the module,
   session and year dropdowns, each read through its calcValues, so page translation cannot
   change them). The cascade: the year shows its module dropdown, each curriculum module of
   every year its session dropdown (8 sessions in year 1; SESSION_OVERRIDES in years 2 and 3);
   a special event ("Special Event - <type>", every year's module option, glow/sync.py
   SPECIAL_EVENTS) shows none, and question 100 is then blank: the session bridge, one
   calculation over the session dropdowns shown, heads the cascade's rules so it runs after
   them - docs/plans/2026-10-13-special-events.md
   the Group Photo (q19) is NOT in the mapping since 2026-10-01 (the CEO: no photo in Salesforce);
   Jotform's own Google Drive integration copies it to Drive instead (RUNBOOK "Photos")
   (with the club guard: Submit is hidden and disabled unless q5 is exactly one picker option,
   so only one roster is visible when a mentor submits — docs/plans/2026-09-29-club-guard.md)
```

The legacy path still exists for the template form: a CSV export of the raw
enrollment responses → `sync_attendance_form.py read_sheet` (no `--roster`).

## Components

| Where | What | Talks to |
|---|---|---|
| `sync_attendance_form.py` | The product: makes one form match the sheet — creates/updates roster questions, regenerates every condition (visibility rules, curriculum cascade, Salesforce bridge, and — on a form with the club guard — the one-club rules), and keeps the Club picker and the club guard's warning (found by field name, `clubPicker` / `clubGuard`, added once by `--club-picker` / `--club-guard`) in shape. A club whose name another partner's club shares has its own picker entry, `<club> - <partner>` — the text question 5 sends to Salesforce (`glow/sync.py` `SF_NAME_SEP`, `sf_club_name`): each roster keeps the form its rule has (read back, never flipped), `--same-name-switch` makes the shared names long by hand, a new club with a name in use is not created, and any other change of an existing club's question 5 needs `--q5-change-ok`. A plain roster's rule names no partner, so where the Roster has another partner's club of that name its owner is read from the Roster's rows of any status (`roster_names`: whose rows list at least half, and the most, of the girls the question holds) — a retired club's question is never taken over by a newcomer. New rosters are created above the links and Submit (`glow/layout.py`). The curriculum cascade gives every curriculum module of every year its own session rule and none to a special event (`glow/sync.py` `SPECIAL_EVENTS`: the sync appends a missing event option to each module dropdown, in the same write as its calcValues, and never removes, renames or reorders one), headed by the session bridge (`WEEK_BRIDGE_FIELDS`: question 100 from the session dropdown shown, blank for an event). Question 18 (Contact_IDs) is rule 0 on a picker form, with the picker as an operand, and every roster carries Jotform's `required` flag (`glow/sync.py` `CONTACT_IDS_FIRST`, `CONTACT_IDS_PICKER_OPERAND`, `ROSTERS_REQUIRED`, read at run time: turning one off and applying is the rollback); it warns when the live rules calculate question 18 the old way, and when they let a special event show or send a session on a form that carries (or will carry) an event option (`WEEK_BRIDGE_STALE`, `glow/sync.py` `week_bridge_stale`). With `--partners` (the Partners tab) a roster whose partner is marked `jotform=no`, or whose club has had no active girl since before today (`RETIRE_INACTIVE`), is retired: kept on the form hidden and frozen, off the picker, no show rule, still in question 18's sum (`~ retired roster …`); it comes back when the Roster says so (`~ restored roster …`; a shared name long, as a question-5 change), and without the export a restore is warned and refused. It prints the form's status first and refuses `--apply` on a disabled form without `--disabled-ok`. Dry run by default, `--apply` writes, `--summary-json` for the runner (its `sf_names`: what every roster sends; `requires`: rosters whose flag alone is written; `retired` / `restored`) | Jotform API via `curl` |
| `backup_forms.py`, `restore_conditions.py` | Snapshot and rollback: `backup_forms.py` is the command line of `glow/backup.py`; the restore puts back conditions only, snapshots the form before its PUT (the `--from` that undoes it is printed; the `-latest` files are left alone) and refuses a snapshot with a rule whose terms or action do not parse (`--force` does not override that); a snapshot whose rules test clubs the Club picker no longer offers is refused; one that calculates question 18 the old way restores with a note) | Jotform API |
| `tools/form_status.py` | Read-only audit of every form vs the Roster export, rule by rule (rosters grouped by the text their rule tests; the picker's options are those texts; question 18's place, operands and equation and the rosters' required flag, the module dropdowns' `calcValues`, and the module chain's shape - year, module and session dropdowns single-select and required, the form-level `clearFieldOnHide` - each as `glow/sync.py`'s constants say; each special event listed once per module dropdown, no session rule for one and the session bridge before every session rule and copy - a form without them, or one whose required flags, question 18's order or picker operand, or module `calcValues` are off, awaits the runner's next run on an enabled regional form and a sync apply by hand on the template or a disabled form (`fixer`; other rules-only drift - question 18's equation, roster rules testing a name the picker lacks - is not the runner's); the names dictionary, emulated by `glow/translation_lookup.py`: no roster option altered in any language); `--rendered` reads the public page (counts only: picker and module `data-calcvalue`, no module select served `multiple`, `JotForm.clearFieldOnHide`, each special event served with its `data-calcvalue`, the session bridge's place and operands, question 18 in `JotForm.setConditions` / `setCalculations`, `validate[required]` boxes, the embedded translation store against the boxes served, the runtime build, and the retired rosters' `always-hidden` elements); the line after the Roster line is Jotform's storage against the plan's limits (`glow/usage.py`: upload space in all, submissions in the cycle, each on its own - account-wide, never a form problem); with `--partners` a retired roster is told from a broken one (retired: clean; still with its rule or entry: awaiting the next apply; off the picker with an active club and no mark: a problem); a form whose status is not `ENABLED` has its region check and served-page checks skipped; `--json` | Jotform API, the public page |
| `tools/integration_status.py` | Read-only: every form's Salesforce integration against the one known action (create `Attendance_Batch__c`, eight fields from their questions, `Account_Name__c` from question 5, no upload since 2026-10-01, one connection for the live forms, none on the old ones; a ninth, `Session_Notes__c` (ticket #106), read from the form's own question named `sessionNotes`, found by its name like the Club picker: right when present, required (`NOTES_MAPPING_WANTED`, True since 2026-10-26) on every live form but one whose `status` is exactly `DISABLED`) and the other integration blocks a form carries (`other integrations:`, where the Google Drive block's key will show once Ryan sets it up); the builder is the only writer | Jotform API |
| `tools/auto_sync.py` | The unattended loop (export the Roster and Partners tabs → form status → plan → bands → backup → apply → verify → SyncLog; after a `REPLACE conditions` or module-dropdown apply the verify reads the served page too, `form_status.py --rendered`; a page unreadable or with problems is read once more and the second read judged: a page problem `applied-with-problems`, a page unreadable twice a note, the first read's problems kept when the re-read cannot be read); a form that is not `ENABLED` is `skipped`, a status that cannot be read `failed`. ATTENTION also for a question-5 change of an existing club (the region is not applied), more than 5 rosters retired or restored at once (`--max-retires`, `--max-restores`), a new club refused for its name, a Partners-tab `jotform` value not understood, a Partners export without the `jotform` column (a plan restoring a roster from it is held), a name two clubs send, and roster rules that test a name the Club picker does not list (never `in-sync`; the rules-only rewrite is applied by hand). A generated rollout line — question 18 calculated the old way or rules that let a special event show or send a session on a form that carries one (each a rules-only plan, never `in-sync`, the SyncLog detail naming the rewrite), a required flag written on its own, a module dropdown's `calcValues` or special-event options (none counted against `--max-updates`) — is applied like a roster change, within the bands (DECISIONS 2026-10-14): the runner applies it to every enabled regional form on its next run; the template and a disabled form are applied by hand; once per run Jotform's storage (`glow/usage.py`): the line logged, an ATTENTION per limit at 80 %; and the sheet's time zone against `glow/sync.py SHEET_ZONE`. With the repository variable `SF_SYNC` (`plan` / `apply`) the new clubs' Salesforce accounts are made by `tools/sf_new_clubs.py` right after the region's backup and before its apply, only for a region whose form applies (a `skipped` form's region is left out of the end-of-run check too), then every club on a form is checked read-only: one SyncLog row `Salesforce` | Sheets API, Salesforce REST, the tools above |
| `tools/sheets_client.py` | Service-account access to the sheet: `whoami`, `tabs`, `export`, `export-all`; importable (`read_tab`, `append_rows`, `write_tab`, `write_cell`, and the cell helpers `a1`, `col_letter`, `cell`, `trimmed`, `describe_rows`, moved here from `rename_club.py` on 2026-10-09) | Sheets API |
| `tools/sf_new_clubs.py`, `glow/salesforce.py`, `glow/sf_partners.csv` | New clubs' Salesforce accounts (BACKLOG 27): `auto_sync` creates a new club's Club account, logged in as Ryan's own Salesforce user through the External Client App GLOW Sync (client credentials; DECISIONS 2026-10-21), right before its form puts it on the picker (`SF_SYNC` off/plan/apply, at most 5 per region, all or nothing), and checks every club on a form afterwards, read only; `check` is the same check from Ryan's CLI login. `glow/salesforce.py` is the one Salesforce client (the CLI's login for the Mac tools, client credentials for GitHub Actions); the partner map is organisation names and account ids | Salesforce REST, Sheets API (SF Pending) |
| `tools/sf_dupes.py` | One Salesforce contact per girl ([plan](plans/2026-10-07-sf-duplicate-girls.md), RUNBOOK "Duplicate girls in Salesforce"): `check` (the monthly look, read only: the same name twice in a club, stored names and batches' name lists with odd whitespace, names in two clubs the Roster does not have in both), `plan` (each group proven against the Roster, the contact that stays, merge calls of at most two -> `merge_plan.json`, ids only), `merge` (dry run, `--rehearse` or `--apply`: one anonymous-Apex `Database.merge` run per club, all or nothing, the rollback file first, read back), `rename`, `cleanup` (extra affiliations, duplicate-rule sets). Uses `glow/salesforce.py` (`query_all`, `delete`) and `sf apex run` through Ryan's CLI login; prints ids and counts, never a name | Salesforce REST and CLI, Jotform API (read only: the quiet-window check and the submission count) |
| `tools/upload_roster.py`, `tools/build_roster_offline.js` | Rebuild the Roster tabs offline with the *same* `.gs` code, upload them | local, Sheets API |
| `tools/rename_club.py` | Rename a club in place: Roster/ClubRegistry/SF Pending cells (code kept) and the question label on the region's form and the template; the sync then follows. `--new-partner` moves a club filed under a mistyped partner: the same tabs' partner cells in one batch, and the typo's Partners row blanked with a note; the forms are only read (checked for a Partner-gated rule) unless `--new` renames too. A question is found by its text, so where another partner has a club of the old name a rename refuses a question that holds that other club's girls: a club the sync did not add is renamed with `--sheet-only` | Sheets API, Jotform API |
| `tools/club_names.py` | Read-only, files only (RUNBOOK "Club names that look alike", tickets #94, #95): `similar` compares every club of a Roster export (one per `key(partner)` + `key(club)`, any status, rows read by `glow/sync.py`'s own reader) with every other - `same` (`glow.text.key` equal), `folded` (equal after `fold`: NFKD accents, case, punctuation and spacing), `close` (difflib ratio at least `--threshold`, default 0.85, with the same digit sequences) - and prints the lookalikes as connected components (union-find), each club with its partner, region (`glow.forms.canonical_region`) and form (`retired (jotform=no)` from `read_partners_csv`, `none (no active girl)`, `none (no region)`, or the form's title); the counts line counts a group under the weakest kind of link it needs to be one group (its `same` pairs alone, else with the `folded` ones, else `close`). `--csv` one row per grouped club (its folder made when missing); `--countries` (a `partner,country` CSV) and `--sf-names` (the sync's `--summary-json` files, their `sf_names`) fill the `country` and `sf_name` columns. `plan-renames` plans every active club in scope (`--scope all`, or `similar` with `--similar-csv`; partners marked `jotform=no` not planned) into `--format` (`{country}` from the required `--countries`, `{club}`, `{partner}`, `{region}`): `new_club` the format filled in, `new_sf_name` `glow.sync.sf_club_name(new_club, partner, long)` with `long` when the club's current question 5 (required `--sf-names`) is the long form (`long_name_partner`) and `--keep-long yes`; a club already in the format (by key) `unchanged`. It refuses, every club named and no `--out` written, a missing country, an unknown placeholder, `|` `{` `}`, `new_sf_name`s equal by key (`sf_name_clashes`, with the values of clubs not planned), a `new_club` another partner has after the renames (`shared_club_names`, any status) unless long, a `new_sf_name` over 255 characters, and a cycle of clubs each taking another planned club's current question 5 (no rename order). The CSV's `after` column holds, on a club whose `new_sf_name` is (by key) another planned club's current question 5, that club's `old_sf_name` - the Account renamed first - and an `order: ... first` line is printed per such pair. Club and partner names and counts, never a girl's name | local files |
| `tools/deactivate_clubs.py` | Deactivate clubs in the Roster (`--region`, `--partner`, `--partner --club`): every ACTIVE row's `status` → `inactive` and `removed_date` → today in the sheet's zone, in one batch, after a guard that reads the region's form's submissions since 2026-09-01 and credits each to a club by question 5 or the Club picker's pick - the same text or exactly `<club> - <its partner>`, never a bare prefix - and refuses a club named in the last 30 days (`--deactivate-anyway`; `--check-only` prints the counts and stops); with every active club of a region chosen it reads the form's status too and refuses `--apply` while the form is not `DISABLED` (`--form-enabled-ok`). The Roster tab and the rows' old values are saved first (`data/deactivate_clubs/<stamp>/`), the tab re-read before the write (a changed or gained row stops it) and after (row by row), one Audit row `deactivateRows`; `--undo <dir>` puts exactly those rows back the same way (`reactivateRows`) and refuses, before its plan, a row that changed since or a club with an active row it does not name - that club leaves `written.json` whole for the rest to go back. ClubRegistry, SF Pending, the Partners tab and the forms are not touched: the template's sync retires the rosters (`RETIRE_INACTIVE`) | Sheets API, Jotform API (GET) |
| `tools/disable_form.py` | A regional form's `status` (`DISABLED` / `--enable`) and the disabled page's text (`--message`) through the form-encoded properties POST - unverified: `--apply` snapshots the form first (`backup_forms.snapshot`), writes, re-reads both GETs and stops with the builder step when the status did not move. Refuses the template, a form not in `glow.forms.LIVE`, and a form with a submission in the last 30 days without `--disable-anyway`. The runner skips a `DISABLED` form (`skipped`), the audit prints `[DISABLED]`; a disabled form is never synced down to an empty Club picker | Jotform API |
| `tools/backfill_resolve.py` | September 2026 back-fill, read-only: every active submission of the four regional forms as one row per (submission, ticked roster) in `data/backfill_2026-09/resolved.json` - the club from the ticked roster, its partner and Club Name from the sync's own dry run (`--summary-json sf_names`), the module from the module dropdown the submission used (not question 98, which page translation rewrote), flags (listed in `flag_vocabulary`), a no-tick list and a ledger; prints counts only | Jotform API (GET), the sync as a dry run |
| `tools/sf_backfill.py` | The September 2026 back-fill of attendance into Salesforce ([plan](plans/2026-09-30-september-backfill.md), RUNBOOK "Back-fill of attendance into Salesforce"): the Jotform attendance that never reached Salesforce, one `Attendance_Batch__c` per club session, each proven against Salesforce before it is sent and read back after (status, rows, girls, `Girls_Present__c`). `snapshot` (live, read-only: accounts, batches, attendance and participant counts -> `sf_state.json`), `plan` (offline: `backfill_resolve.py`'s `resolved.json` + `sf_state.json` (+ `decisions.csv`) -> `plan.json`, `held.csv`, a counts-only report), `send` (the queue; dry run by default, `--apply` writes one batch per request: a `sending` ledger row first, its outcome after, and a lost outcome settled before the next send), `close` (offline: a batch the ledger has open, removed by hand or accepted), `status` (what the ledger says was sent, and what a rollback would have to remove). Its `Org` is `glow.salesforce.Org` on Ryan's CLI login (`--org`, default `glow`); `snapshot` and `send --apply` refuse without `--vpn-off`. Its files live in `data/backfill_2026-09/`, owner only; it prints counts, club names, dates, ids and statuses, never a girl's name | Salesforce REST through the CLI login |
| `tools/fix_module_values.py` | One-off correction in Salesforce (`docs/plans/2026-10-06-module-selection.md`): every `Attendance_Batch__c` since launch whose `Module__c` is not an option of the template's module dropdowns (a Spanish rendering written by page translation before the module `calcValues` were live), and the `Attendance__c` rows under it, set to the English option. The ground truth is the Jotform submission the batch came from - exactly one on the form of the batch's region (`SF_REGION_FORM`), created within 3 hours of it, with the same question 5, date, question 98, year and session (whole numbers) - and the module is `backfill_resolve.copied_fields`' stored dropdown answer; anything less is `UNMATCHED` and left alone. Dry run by default; `--apply --vpn-off` writes the batch then its rows through `glow.salesforce.Org.update`, one record per request, each with an open and a closing ledger row (`written` / `failed_<status>` / `check`, `data/module_fix_2026-10/ledger.csv`) and stops at the first thing not as planned; `--undo <ledger>` puts `old` back. Every Salesforce read is an explicit-field SOQL query - never the names list or the status message | Jotform API (GET), Salesforce through the CLI login |
| `tools/sf_partner_monthly.py` | Monthly, in Salesforce ([plan](plans/2026-10-19-partner-monthly-max.md), ticket #60): the Monthly Max (`DHIS2__c.Monthly_Total__c`) of Education and English for You, Tumaini La Maisha and Ng'aa Maskani for `--month` (default last month; the current one refused) as one `Attendance_Batch__c` per partner (`Account_Name__c` the partner's Account name, the month's last day, `Creator__c` `Partner report`, no names). Insert, skip when in place, update `Girls_Present__c` alone when changed; a partner without exactly one report, with a Monthly Max not a whole number above 0, with two `Success` `Partner report` batches on its day, or needing an insert beside another creator's `Success` batch on its account and day is refused and the others still go. Dry run by default (`--vpn-off` even so); `--apply --vpn-off` writes one record per request, reads each back, ledger `data/sf_partner_monthly/ledger.csv`; `--limit` counts writes. Partner names and counts only | Salesforce through the CLI login |
| `tools/sf_report_folders.py` | The folders of the Monthly Report reports and dashboards in Salesforce (ticket #71, epic #68; RUNBOOK "Copying and moving reports and dashboards"): `list` (read-only CSV of what named folders hold, with the dashboards that use each report), `copy` (a report or dashboard cloned into the one folder "Decommissioned" of its kind; a report's copy carries `copy of <id>, <tag>` in its description), `move` (reports moved and relabelled by a `kind,id,to_folder,new_label` plan, one PATCH each, the Id kept; a dashboard row is refused: the API refuses every dashboard PATCH, so it is moved by hand in Lightning) and `undo` (the ledger's moves put back, last first; copies stay). Never deletes; reads `Folder`, `Report`, `Dashboard` and `DashboardComponent` only. Refused before any write: the "Attendance" folders as source or target, a folder name that is not exactly one folder of the kind, a label over 40 characters, retiring a report that a dashboard outside Decommissioned uses. Dry run by default (`--vpn-off` even so); `--apply --vpn-off` writes one request at a time, each read back by SOQL, ledger `data/sf_report_folders/ledger.csv`; `--limit` counts writes. Ids, labels and folder names only | Salesforce through the CLI login |
| `tools/sf_girls_present.py` | One-off back-fill in Salesforce (`docs/plans/2026-10-06-attendance-totals.md`, C): `Girls_Present__c` on every `Success` batch from before the field existed, = its attendance rows (0 for a blank); `Failed` batches stay empty, a batch with a value is never touched (a typed partner total survives). `plan` (live, read-only: ids, statuses, creator kinds, rows, values → `data/sf_girls_present/plan.csv`), `set` (a dry run from the plan; `--apply --vpn-off` re-reads each batch, PATCHes through `Org.update`, re-reads, one open and one closing ledger row), `check` (Jotform `Success` batches whose count differs from their rows, and `Success` batches without a value: both 0 when healthy). Ids and counts only | Salesforce through the CLI login |
| `tools/sf_session_timing.py` | Read-only `check --vpn-off [--since 2026-09-01]` (ticket #100): one explicit-field SOQL over `Attendance_Batch__c` (never `Contact_IDs__c`); each batch's formula fields `Submitted_At__c`, `Submission_Delay_Days__c`, `Session_Month__c` and `Session_Week__c` (deployed by task #101) against `glow/session_timing.py`, the expected delay from the expected submission time. `-> OK`, or `-> DIFFER` with up to 10 lines of batch Name, field and both values, exit 1; an HTTP 400 says the fields are likely not deployed yet. Batch Names and counts only | Salesforce through the CLI login |
| `worklog/worklog.csv`, `worklog/timezones.csv` | The work log behind the monthly invoice, kept by the harness plugin's `harness-worklog` (`/harness:worklog`; RUNBOOK "Work log and invoices"): hours per day from the session transcripts on the Mac's clock at the time (`timezones.csv`, `zone`), descriptions, `export --month` | local files |
| `tools/add_translations.py`, `add_language.py`, `restore_translations.py`, `switcher_flags.py`, `add_feedback_link.py` | Languages (`restore_translations.py` also gives a fresh clone its language list back), switcher flags for languages Jotform has none for (`injectCSS`), the links above Submit (problem report, Club Roster Form — `glow/links.py`) | Jotform API |
| `tools/fix_name_translations.py` | Removes from each form's translation store (`base`/`en`) exactly the entries whose lookup alters a roster option of any of the five forms (stale spellings of girls' names), found by emulating Jotform's runtime (`glow/translation_lookup.py`); store saved first (mode 600), re-read, audited, the public page read and re-rendered if needed; `--restore` puts the entries back. Counts and club names only | Jotform API, the public page |
| `tools/fix_roster_order.py` | One-time repair (BACKLOG 47): the links, Submit and the hidden bridge fields move to empty orders after the last roster, so every roster renders above them; `glow/layout.py` holds the plan, the order the sync gives a new roster, and the `form_status` layout check | Jotform API |
| `tools/add_session_notes.py` | The optional session-notes field (ticket #104; built, not live — RUNBOOK "Session notes on the attendance forms"): one textarea named `sessionNotes` (`glow/layout.py` `NOTES_NAME`, `NOTES_PROPS`), placed once per form after the last roster and above the links and Submit — at an empty order, or, when none is free, after moving the first link through Submit and the hidden fields right after one down (`notes_slot`); a drifted flag or text set back in one write; snapshot first, re-read and compared after; `--remove` is the rollback. `form_status` prints `session notes:` and flags a duplicated, misplaced, hidden or required one (absent too, once `NOTES_EXPECTED`) | Jotform API |
| `tools/update_static_fields.py` | The fields the sync never touches: label wording, the Group Photo limits, and the header logo (`--image-src`, since the API cannot upload an asset). Declarative — wanted properties per field name, re-read and compared after every write | Jotform API |
| `appsscript/*.gs` | Bound to the sheet: config, normalization, ids, roster ops, form generation, submission handlers, menu, dispatch | Google services |
| `test/`, `scripts/`, `.githooks/`, `Makefile` | The offline feedback loop (`make check`): ruff; the Python tests by discovery (`python3 -m unittest discover -s test -p '*_test.py'`, one file per subject, shared fixtures as mixins in `test/helpers/common.py`, the fake Salesforce org in `test/helpers/fake_org.py`) and the JavaScript suites `test/*_test.js`; `scripts/check_gs.js` (the `.gs` files parse, use only the 8 pinned Google services, call only functions that exist); the secret, link, RUNBOOK-section and BACKLOG-number checks; `.githooks/pre-commit` for commits made outside Claude Code. Around the loop, `scripts/harness_tests.sh` (runs the test files a ticket names) and `scripts/verify.sh` (the verify command: `make check`, then `VERIFY OK`). Outside it, `scripts/capture_readonly.sh <dir>`: a GET-only capture to diff before and after a refactor (`form_status.py --json`, each live region's sync dry run and `--summary-json`, the translations audit; needs `JOTFORM_API_KEY` and a Roster export) | nothing (`capture_readonly.sh`: Jotform API, GET only) |

`appsscript/Config.gs` documents the Script Properties and the Salesforce
mapping's dependence on question ids. `Roster.gs`, `Forms.gs`,
`FormHandlers.gs`, `Menu.gs` call Google services; `Config.gs`,
`Normalize.gs`, `Ids.gs`, `Regions.gs`, `RosterOps.gs`, `Dispatch.gs` have no
top-level side effects and run in Node through `test/load_gs.js`.

### `glow/`, the shared library

Standard library only (HTTP through `curl`). On 2026-10-09 the copies the tools kept
of the same helpers moved here ([plan](plans/2026-10-09-repo-cleanup.md), Phase 3);
`glow/__init__.py` lists the modules.

| Module | What it holds |
|---|---|
| `glow/jotform.py` | `Client`, the one Jotform API client: `call()` treats any POST, PUT, DELETE or `--data*` as a write and skips it unless the client was built with `apply=True`; a JSON body goes on curl's standard input; `url()` URL-encodes the key and every parameter, once (callers pass plain values, a submissions filter as its JSON text); `submissions()` reads a form's submissions page by page and checks the count. `public_page()`: the public page as a mentor's browser gets it (no key, a browser user agent; a curl failure raises, never reads as an empty page). `CLOCK`: Jotform's clock (US Eastern) for `created_at` |
| `glow/forms.py` | The form ids, Python only: `TEMPLATE`, `REGIONALS`, `LIVE`, `DEFUNCT`, `REGIONS` (parity-tested against `Config.gs REGIONS`, the Club Roster Form's region picker), `TITLES`; `language_of()`. The tools that keep their own table (for its order or labels) are pinned to it by `test/glow_lib_test.py` |
| `glow/sync.py` | The Roster and enrollment readers (`read_roster_csv`, `_roster_rows`, `read_partners_csv`, `read_sheet`, `parse_roster`), the structural question ids (below), `club_picker()` (the one reader of the Club picker), `dropdown_options()`, `rule_parts()` (a rule's terms and action decoded, or None), the switches the sync and the audit read (`CONTACT_IDS_FIRST`, `ROSTERS_REQUIRED`, `RETIRE_INACTIVE`, …), `SESSION_OVERRIDES`, `SPECIAL_EVENTS` and `SPECIAL_EVENT_PREFIX` (the special-event module options, `special_event_plan()`), the session bridge (`WEEK_BRIDGE_FIELDS`, `week_bridge_layout()`), `SHEET_ZONE`, `SF_NAME_SEP` |
| `glow/text.py` | The keys names are compared by: `key`, `name_key`; the sheet's `tidy`, `cell_key`, `nfc_key` and `INVISIBLE` (from `rename_club.py`) |
| `glow/cli.py` | `run(main)` (a `JotformError` is a one-line exit), `api_key()` (the key from the environment; it was copied into 22 tools), `targets()` (the forms a `--form` selects) |
| `glow/backup.py` | `snapshot()` (a form's questions and properties into `backups/<form>/<part>-<stamp>.json` and `-latest.json`), `stamp()` (to the second, so a re-run within the minute never overwrites the true "before"), `path()`, `save_conditions()` |
| `glow/translations.py` | A form's translation store: `read_store()`, `save_store()` (`backups/translations/<form>-<stamp>-before.json`, mode 600, never over an earlier file), `expand_n()`, `replace_languages()` (refuses to POST without the saved store), `reads_back()` |
| `glow/submissions.py` | Reading a submission (from `tools/backfill_resolve.py`): an answer, the ticked rosters, the attendance date, the module, session and year from the dropdowns rather than their copies; an unknown answer shape is `Unreadable`, never echoed |
| `glow/links.py`, `glow/layout.py` | The link elements above Submit and their place; the session-notes field's definition and slot (`NOTES_NAME`, `NOTES_PROPS`, `NOTES_EXPECTED`, `notes_slot`); where rosters sit relative to the notes field, the links and Submit (the fence), and the layout audit `form_status` prints |
| `glow/usage.py`, `glow/translation_lookup.py` | Jotform's storage against the plan's limits; the runtime's names dictionary, emulated |
| `glow/salesforce.py`, `glow/sf_partners.csv` | The one Salesforce client (`Org`: the CLI's login on the Mac, client credentials for GitHub Actions); and what every Salesforce tool relies on, moved here from the tools: the org's record-type ids and the pilot accounts on hold, `sf_match()` (the attendance processor's trimmed, case-ignoring name match, one comparison instead of three), `duplicate_account_groups()` (the Account duplicate rule's Python side: the groups of one name, parent and record type), `has_invisible()`, `error_codes()` (codes only, never a word of the answer), the partner map (`read_partners()`), and `--vpn-off` (`add_vpn_flag()`, `require_vpn_off()`) |
| `glow/session_timing.py` | The session-timing definitions (ticket #100; DECISIONS 2026-10-23): `JOTFORM_CREATOR`, `submitted_at()` (a live Jotform batch's `CreatedDate`, else None), `delay_days()` (the submission's UTC day minus the session date; negative for a date typo), `session_month()` (`2026-10`), `session_week()` (`2026-10 week 2`: days 1-7 week 1 ... 29-31 week 5), and `SF_FORMULAS`, the four Salesforce formula texts that compute the same. No "big delay" threshold |
| `glow/private_files.py` | Files that can hold names or record ids: owner-only folders and files, inside the checkout only under `data/` (`private_folder`, `open_private`, `save_private`), and `Ledger`, the append-only CSV each Salesforce writer keeps |

The structural question ids, in `glow/sync.py` (those the Salesforce mapping reads are
frozen: DECISIONS 2026-08-24): Club Name `CLUB_NAME` 5, Partner `PARTNER` 331, year `YEAR` 94,
modules `MODULES` 14 / 92 / 93, sessions `WEEKS` 15 / 95 / 96 / 97, the date `DATE` 17,
Contact_IDs `CONTACT_IDS` 18, the Group Photo `PHOTO` 19, the bridge copies `MODULE_ID` 98,
`WEEK_ID` 100, `YEAR_ID` 102, `CREATOR` 105 and `ENABLE_FUZZY` 109. Tools import them; none
spells a qid of its own.

## Constants that exist on both sides

Change both, or `test/gs_parity_test.py` (`PythonAppsScriptParity`) fails. The
question ids, the form ids and `SESSION_OVERRIDES` are Python only since 2026-10-09
(`glow/sync.py`, `glow/forms.py`): Apps Script never talks to Jotform, and its unused
copies went. `SPECIAL_EVENTS` (2026-10-13) is Python only from the start: Apps Script never
reads modules.

| Constant | Python | Apps Script |
|---|---|---|
| `SF_NAME_SEP` (`" - "` between club and partner in the name of a club whose name two partners share: club-list entry = question 5 = Salesforce account) | `glow/sync.py` | `Config.gs` |
| Roster tab columns | `read_roster_csv` needs `partner, club, full_name, status, region`; `upload_roster.py` positional | `Config.gs ROSTER_COLS` |
| Partners tab columns (`partner, region, notes, jotform`; `jotform` = `no` keeps a partner's clubs off the attendance forms) | `glow/sync.py PARTNER_COLS`, `JOTFORM_COL`, `read_partners_csv` | `Roster.gs PARTNER_COLS`, `tools/build_roster_offline.js` |
| The sheet's time zone (`America/New_York`: the day `removed_date` is stamped in, which the no-active-girl rule compares "today" with) | `glow/sync.py SHEET_ZONE`, `sheet_today` | the spreadsheet's own setting (File → Settings), `getSpreadsheetTimeZone()` in `Roster.gs today_()` — not `appsscript.json`'s `timeZone`; no offline test can read it, so `tools/auto_sync.py` checks it on every run |
| Response-tab header fragments | `glow/sync.py COL_PARTNER`, `COL_CLUB`, `COL_ROSTER` (`read_sheet`) | `Config.gs RESPONSE_COLS` (`readResponses_`) |
| SyncLog columns | `tools/auto_sync.py SYNC_LOG_COLS` | `Roster.gs SYNC_LOG_COLS` |
| `Roster`, `Partners` and `SyncLog` tab names | `tools/auto_sync.py ROSTER_TAB, PARTNERS_TAB, SYNC_LOG_TAB` | `Config.gs TAB` |
| SF Pending columns (`test/sf_new_clubs_test.py` compares them) | `tools/sf_new_clubs.py SF_PENDING_COLS` | `FormHandlers.gs SF_PENDING_COLS` |
| Region vocabulary `Africa / Asia / Latin America / U.S` | `glow/forms.py REGIONS` (the tools' strings follow it) | `Config.gs REGIONS` (the Club Roster Form's region picker), `Regions.gs` values, Partners tab |

## Parity bridges (same logic, two languages)

1. `Normalize.gs parseRoster_` ↔ `sync_attendance_form.py parse_roster`, and
   `readResponses_` ↔ `read_sheet` — `test/parity_test.js` runs the `.gs`
   code over the synthetic fixture (always) and the real export (when
   present) and compares club sets with the Python side
   (`test/helpers/py_clubs.py`); `test/fixtures/expected.json` is written by
   the Python parser.
2. `Roster.gs rebuildRosterLocked_` ↔ `tools/build_roster_offline.js` — the
   JS mirrors the sheet rebuild by hand, sharing `RosterOps.gs`; the round
   trip (upload, then run the sheet's rebuild and expect no change) is the
   check.
3. The constants table above — `test/gs_parity_test.py` parses `Config.gs`.
4. `RosterOps.gs sharedClubNames_` / `sfClubName_` ↔ `glow/sync.py`
   `shared_club_names` / `sf_club_name` — which clubs are
   `<club> - <partner>` (a name that active clubs of two or more partners
   have, all regions). Python decides what the forms send (the one-time
   `--same-name-switch`; afterwards a form's long or plain name is sticky);
   Apps Script uses the rule for the Monday e-mail's Salesforce lines only.
   Each side is tested on its own, with fictional names
   (`test/forms_logic_test.js`; `test/sync_conditions_test.py` `SameNameRule`), and
   `PythonAppsScriptParity` runs both over one fictional Roster (the `.gs`
   side in Node, through `test/load_gs.js`): the separator, which names are
   shared, each club's name, and — for the two checkers, the sync's and the
   intake's `newClubHoldReasons_` — which new club's name is in use.
   `SameNameFlow` does the same for the switch itself: the `sf_names` the
   switched form sends are the names `sfClubName_` prints.
5. `RosterOps.gs similarity_` (the duplicate-club guard's "close names") ↔
   Python's `difflib.SequenceMatcher(None, a, b).ratio()` — `test/gs_parity_test.py`
   compares them over fictional pairs.
6. `Normalize.gs foldKey_` (the near-duplicate checks) ↔ `glow/text.py name_key`:
   the same case and accent folding, except that `foldKey_` drops the invisible
   characters (`Normalize.gs INVISIBLE`) and `name_key` keeps them — the divergence
   below; `test/gs_parity_test.py` asserts exactly that difference over the fixture.

## Known divergences (documented, not fixed — see the backlog)

- `read_sheet` keeps a row with an empty partner; `readResponses_` drops it.
- `parseRoster_` strips `•` and `*` bullets; `parse_roster` strips only `-`.
- `parse_roster` strips invisible characters from roster lines only;
  `tidy_` strips them from partner and club cells too.
- "The same club name": `sharedClubNames_` and the intake check
  (`newClubHoldReasons_`, kind `samename`) compare with `key_`, which drops
  invisible characters; Python's `shared_club_names` and the sync's own
  check compare with `glow.text.key`, which keeps them. A club cell with a
  zero-width character inside is the same name in Apps Script and a
  different one in Python (the intake errs toward holding); `foldKey_` (the
  near-duplicate checks) and `glow.text.name_key` differ the same way. Cells the form
  handlers write never hold one (likewise a girl's name cell with only
  such characters is no name in Apps Script). Also: the intake check counts
  Roster rows of any status, with a girl's name or not (as `roster_pairs`),
  the Monday e-mail's names follow today's active rows that have a girl's
  name (as `shared_club_names(active_only=True)`), and on a form the long
  or plain name is sticky once switched — so the e-mail can print a plain
  name for a club whose form entry is still `<club> - <partner>` after its
  namesake left.
- A club on file with no active girl, sent again on "Enroll a NEW club" by
  its own partner while another partner's club has its name, is held at
  intake (`newClubHoldReasons_`) whether or not its roster is still on the
  form — Apps Script cannot see the form. The sync refuses such a club only
  when it has to create the roster (a retired club whose question was
  deleted) and takes up a roster that is still there. RUNBOOK "Working the
  ReviewQueue" has the way out for that one false hold.
- A Roster row's status: the Python readers (`read_roster_csv`,
  `roster_pairs`) and `sharedClubNames_` ignore capitals and spacing
  (`Active` is active); the rest of `RosterOps.gs`, the intake check
  (`newClubHoldReasons_`) included, compares the cell exactly. The sheet's
  own code only writes `active` / `inactive`; a status typed by hand in
  another case reaches the forms and reads as not active at intake.
- The Partners tab's `jotform` marker: Python decides from it what the forms
  carry (`read_partners_csv`, compared with `glow.text.key`); Apps Script reads
  it only for the mentor e-mails' wording (`key_`, which drops invisible
  characters). A `no` typed with a zero-width character inside is `yes` to the
  sync and `no` to the e-mail — the e-mail would say the attendance form does
  not change for the partner while its clubs stay on it.
- `parse_roster` splits on every Unicode line break (`str.splitlines`:
  U+2028/U+2029, NEL, a lone CR, VT, FF); `parseRoster_` only on `\r?\n` — an
  iOS soft line break (U+2028) merges two girls into one on the Apps Script
  side while Python sees two.
- The sync rewrites all conditions every run, so its "nothing to do" line is
  unreachable; `auto_sync.py` decides "changed" from CREATE/UPDATE/DELETE.
- Reactivating a girl leaves no timestamp in the Roster row (only
  `added_date`/`removed_date` exist); the Audit tab is the change record.
- A Club Roster Form response never reactivates a girl whose `removed_date`
  is after the day it was sent (the replay guard, `RosterOps.gs`
  `staysRemoved_`); for that comparison a Club Roster Form removal's
  `removed_date` is the day it was sent, not the day it ran (the same day
  unless it ran late). The rebuild passes no sent day and is unguarded; a
  Club Roster Form response without one (a Timestamp cell that is not a
  date) is refused (FormLog `ERROR:`), never run unguarded.
  Because a reactivation records no date, an old REMOVE replayed later can
  still take off a girl re-added since.

## Generated and hand-kept files

- `appsscript/Regions.gs` — hand-kept data since 2026-10-09: the partner → region
  map derived on 2026-08-25 from the pre-launch regional forms by a script now
  retired ([Retired tools](#retired-tools)). It only prefills a region the
  Partners tab has none for: the sheet's Partners tab wins. Edit it by hand only
  for a partner the tab lacks, with its `PARTNER_REGION_NOTES` entry
  (`test/parity_test.js` wants one per partner). The edit hook
  (`.claude/hooks/protected_paths.sh`) still refuses Claude's edits, so the edit
  is Ryan's; the file's header and the hook's message still say "generated"
  until he changes them.
- `test/fixtures/enrollment_sample.csv`, `expected.json` — generated by
  `test/fixtures/make_fixture.py`; `make fixtures-check` fails when stale.

## Retired tools

Finished one-offs are deleted, not archived (DECISIONS 2026-10-09); git keeps
the last version. `git show <commit>^:<path>` prints it, and
`git show <commit>^:<path> > <path>` puts it back - then run `make check`: the
`glow/` library it imported may have moved on since.

| Path | What it did | Retired in | Restore with |
|---|---|---|---|
| `tools/needs_attention.py` | The pre-launch data-quality list: read the enrollment export (and the old regional forms' snapshots under `backups/`) and wrote `data/needs_attention_<date>.csv`, one row per thing a person had to chase - a name listed twice, a re-submitted roster, a club renamed on a form, a club on a form but not in the sheet (the 2026-08-26 list is BACKLOG 4) | `7c24ac7` (2026-10-09) | `git show 7c24ac7^:tools/needs_attention.py` |
| `tools/derive_partner_regions.py` | Worked out each partner's region from the pre-launch regional forms its clubs sat on (roster overlap first, then the club name; a majority vote per partner, a conflict left blank) and generated `appsscript/Regions.gs` (now hand-kept, above) | `7c24ac7` (2026-10-09) | `git show 7c24ac7^:tools/derive_partner_regions.py` |
| `tools/clone_regional.py` | Built a regional form: cloned the template, retitled the clone, gave it its language list back, synced one region with `--prune` and printed its status. The steps by hand: RUNBOOK "Building a new regional form (not maintenance)" | `608bcd2` (2026-10-09) | `git show 608bcd2^:tools/clone_regional.py` |
| `tools/sf_club_accounts.py` | The bookkeeping of the 2026-09-30 creation of every club's Salesforce account through the Claude session's connector ([plan](plans/2026-09-30-salesforce-clubs.md)); it never called Salesforce: it validated the write set and cut it into batches, compared it with the live Club pickers, printed the SOQL and request bodies, checked each saved answer before and after a batch, kept the rollback files, and compared the totals | `0dc0d4c` (2026-10-09) | `git show 0dc0d4c^:tools/sf_club_accounts.py` |
| `test/sf_club_accounts_test.py` | Its 29 offline tests, on fictional clubs and ids | `0dc0d4c` (2026-10-09) | `git show 0dc0d4c^:test/sf_club_accounts_test.py` |
| `tools/backfill_feedback_review.py` | One-off of 2026-09-28: put on the ReviewQueue the problem reports (Feedback rows 4-12) that asked for a roster change before the handler queued such reports itself, running the handler's own classifier through Node ([plan](plans/2026-09-28-problem-report-followup.md)) | `0dc0d4c` (2026-10-09) | `git show 0dc0d4c^:tools/backfill_feedback_review.py` |
| `tools/sheets_client.py import` (a subcommand) | Put a CSV into an empty tab, refusing a tab that held data: the one-time import of the original enrollment responses at setup. `whoami`, `tabs`, `export`, `export-all` and the library functions stay | `648947e` (2026-10-09) | `git show 648947e^:tools/sheets_client.py` (the whole file as it was) |
| `tools/worklog.py` | The work log behind the monthly invoice: hours per day from Claude Code's session transcripts on the Mac's clock at the time, descriptions, manual rows, the month's export; replaced by the harness plugin's `harness-worklog`, which reproduced every row byte for byte | #10 (2026-10-14) | `git show 459451d:tools/worklog.py` |
| `test/worklog_test.py` | Its 30 offline tests, on synthetic data: hours from session transcripts on the zone timeline, the log, the invoice | #10 (2026-10-14) | `git show 459451d:test/worklog_test.py` |

`tools/fix_module_values.py` stays until its undo window closes at the end of
October 2026 (BACKLOG 84).

## Privacy boundaries

Rosters are names of minors. `data/`, `backups/`, `credentials/` and every
`*.csv` except the synthetic fixture are gitignored; the Claude Code
settings deny reading credentials; `make secrets` and the PostToolUse hook
refuse keys, ids and girl-ID patterns in tracked files; `parity_test.js`
refuses any real girl's name in published text; `auto_sync.py` redacts names
from its logs and the workflow uploads only conditions backups and redacted
logs. A form's translation store holds every roster option in `base`/`en`:
the tools that save one (`backups/translations/`) write it mode 600, and the
names-dictionary tools (`glow/translation_lookup.py` and its callers) report
counts and club names, never a changed spelling. Club and partner names, and
the live form ids, are in the repository — it stays private.
