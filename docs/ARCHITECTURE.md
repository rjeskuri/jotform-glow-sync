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
   change them)
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
| `sync_attendance_form.py` | The product: makes one form match the sheet — creates/updates roster questions, regenerates every condition (visibility rules, curriculum cascade, Salesforce bridge, and — on a form with the club guard — the one-club rules), and keeps the Club picker and the club guard's warning (found by field name, `clubPicker` / `clubGuard`, added once by `--club-picker` / `--club-guard`) in shape. A club whose name another partner's club shares has its own picker entry, `<club> - <partner>` — the text question 5 sends to Salesforce (`glow/sync.py` `SF_NAME_SEP`, `sf_club_name`): each roster keeps the form its rule has (read back, never flipped), `--same-name-switch` makes the shared names long by hand, a new club with a name in use is not created, and any other change of an existing club's question 5 needs `--q5-change-ok`. A plain roster's rule names no partner, so where the Roster has another partner's club of that name its owner is read from the Roster's rows of any status (`roster_names`: whose rows list at least half, and the most, of the girls the question holds) — a retired club's question is never taken over by a newcomer. New rosters are created above the links and Submit (`glow/layout.py`). Question 18 (Contact_IDs) is rule 0 on a picker form, with the picker as an operand, and every roster carries Jotform's `required` flag (`glow/sync.py` `CONTACT_IDS_FIRST`, `CONTACT_IDS_PICKER_OPERAND`, `ROSTERS_REQUIRED`, read at run time: turning one off and applying is the rollback); it warns when the live rules calculate question 18 the old way. With `--partners` (the Partners tab) a roster whose partner is marked `jotform=no`, or whose club has had no active girl since before today (`RETIRE_INACTIVE`), is retired: kept on the form hidden and frozen, off the picker, no show rule, still in question 18's sum (`~ retired roster …`); it comes back when the Roster says so (`~ restored roster …`; a shared name long, as a question-5 change), and without the export a restore is warned and refused. It prints the form's status first and refuses `--apply` on a disabled form without `--disabled-ok`. Dry run by default, `--apply` writes, `--summary-json` for the runner (its `sf_names`: what every roster sends; `requires`: rosters whose flag alone is written; `retired` / `restored`) | Jotform API via `curl` |
| `backup_forms.py`, `restore_conditions.py` | Snapshot and rollback (conditions only; a snapshot whose rules test clubs the Club picker no longer offers is refused; one that calculates question 18 the old way restores with a note) | Jotform API |
| `tools/form_status.py` | Read-only audit of every form vs the Roster export, rule by rule (rosters grouped by the text their rule tests; the picker's options are those texts; question 18's place, operands and equation and the rosters' required flag, the module dropdowns' `calcValues`, and the module chain's shape - year, module and session dropdowns single-select and required, the form-level `clearFieldOnHide` - each as `glow/sync.py`'s constants say; the names dictionary, emulated by `glow/translation_lookup.py`: no roster option altered in any language); `--rendered` reads the public page (counts only: picker and module `data-calcvalue`, no module select served `multiple`, `JotForm.clearFieldOnHide`, question 18 in `JotForm.setConditions` / `setCalculations`, `validate[required]` boxes, the embedded translation store against the boxes served, the runtime build, and the retired rosters' `always-hidden` elements); the line after the Roster line is Jotform's storage against the plan's limits (`glow/usage.py`: upload space in all, submissions in the cycle, each on its own - account-wide, never a form problem); with `--partners` a retired roster is told from a broken one (retired: clean; still with its rule or entry: awaiting the next apply; off the picker with an active club and no mark: a problem); a form whose status is not `ENABLED` has its region check and served-page checks skipped; `--json` | Jotform API, the public page |
| `tools/integration_status.py` | Read-only: every form's Salesforce integration against the one known action (create `Attendance_Batch__c`, eight fields from their questions, `Account_Name__c` from question 5, no upload since 2026-10-01, one connection for the live forms, none on the old ones) and the other integration blocks a form carries (`other integrations:`, where the Google Drive block's key will show once Ryan sets it up); the builder is the only writer | Jotform API |
| `tools/auto_sync.py` | The unattended loop (export the Roster and Partners tabs → form status → plan → bands → backup → apply → verify → SyncLog); a form that is not `ENABLED` is `skipped`, a status that cannot be read `failed`. ATTENTION also for a question-5 change of an existing club (the region is not applied), question 18 calculated the old way, a required flag written on its own or a module dropdown's `calcValues` (the region is not applied: each is rolled out by hand), more than 5 rosters retired or restored at once (`--max-retires`, `--max-restores`), a new club refused for its name, a Partners-tab `jotform` value not understood, a Partners export without the `jotform` column (a plan restoring a roster from it is held), a name two clubs send, and roster rules that test a name the Club picker does not list (never `in-sync`; the rules-only rewrite is applied by hand); once per run Jotform's storage (`glow/usage.py`): the line logged, an ATTENTION per limit at 80 %; and the sheet's time zone against `glow/sync.py SHEET_ZONE`. With the repository variable `SF_SYNC` (`plan` / `apply`) the new clubs' Salesforce accounts are made by `tools/sf_new_clubs.py` right after the region's backup and before its apply, only for a region whose form applies (a `skipped` form's region is left out of the end-of-run check too), then every club on a form is checked read-only: one SyncLog row `Salesforce` | Sheets API, Salesforce REST, the tools above |
| `tools/sheets_client.py` | Service-account access to the sheet; importable (`read_tab`, `append_rows`, `write_tab`, `write_cell`) | Sheets API |
| `tools/sf_new_clubs.py`, `glow/salesforce.py`, `glow/sf_partners.csv` | New clubs' Salesforce accounts (BACKLOG 27): `auto_sync` creates a new club's Club account as the GLOW Sync integration user right before its form puts it on the picker (`SF_SYNC` off/plan/apply, at most 5 per region, all or nothing), and checks every club on a form afterwards, read only; `check` is the same check from Ryan's CLI login. `glow/salesforce.py` is the one Salesforce client (the CLI's login for the Mac tools, client credentials for GitHub Actions); the partner map is organisation names and account ids | Salesforce REST, Sheets API (SF Pending) |
| `tools/sf_dupes.py` | One Salesforce contact per girl ([plan](plans/2026-10-07-sf-duplicate-girls.md), RUNBOOK "Duplicate girls in Salesforce"): `check` (the monthly look, read only: the same name twice in a club, stored names and batches' name lists with odd whitespace, names in two clubs the Roster does not have in both), `plan` (each group proven against the Roster, the contact that stays, merge calls of at most two -> `merge_plan.json`, ids only), `merge` (dry run, `--rehearse` or `--apply`: one anonymous-Apex `Database.merge` run per club, all or nothing, the rollback file first, read back), `rename`, `cleanup` (extra affiliations, duplicate-rule sets). Uses `glow/salesforce.py` (`query_all`, `delete`) and `sf apex run` through Ryan's CLI login; prints ids and counts, never a name | Salesforce REST and CLI, Jotform API (read only: the quiet-window check and the submission count) |
| `tools/upload_roster.py`, `tools/build_roster_offline.js` | Rebuild the Roster tabs offline with the *same* `.gs` code, upload them | local, Sheets API |
| `tools/rename_club.py` | Rename a club in place: Roster/ClubRegistry/SF Pending cells (code kept) and the question label on the region's form and the template; the sync then follows. `--new-partner` moves a club filed under a mistyped partner: the same tabs' partner cells in one batch, and the typo's Partners row blanked with a note; the forms are only read (checked for a Partner-gated rule) unless `--new` renames too. A question is found by its text, so where another partner has a club of the old name a rename refuses a question that holds that other club's girls: a club the sync did not add is renamed with `--sheet-only` | Sheets API, Jotform API |
| `tools/deactivate_clubs.py` | Deactivate clubs in the Roster (`--region`, `--partner`, `--partner --club`): every ACTIVE row's `status` → `inactive` and `removed_date` → today in the sheet's zone, in one batch, after a guard that reads the region's form's submissions since 2026-09-01 and credits each to a club by question 5 or the Club picker's pick - the same text or exactly `<club> - <its partner>`, never a bare prefix - and refuses a club named in the last 30 days (`--deactivate-anyway`; `--check-only` prints the counts and stops); with every active club of a region chosen it reads the form's status too and refuses `--apply` while the form is not `DISABLED` (`--form-enabled-ok`). The Roster tab and the rows' old values are saved first (`data/deactivate_clubs/<stamp>/`), the tab re-read before the write (a changed or gained row stops it) and after (row by row), one Audit row `deactivateRows`; `--undo <dir>` puts exactly those rows back the same way (`reactivateRows`) and refuses, before its plan, a row that changed since or a club with an active row it does not name - that club leaves `written.json` whole for the rest to go back. ClubRegistry, SF Pending, the Partners tab and the forms are not touched: the template's sync retires the rosters (`RETIRE_INACTIVE`) | Sheets API, Jotform API (GET) |
| `tools/disable_form.py` | A regional form's `status` (`DISABLED` / `--enable`) and the disabled page's text (`--message`) through the form-encoded properties POST - unverified: `--apply` snapshots the form first (`backup_forms.snapshot`), writes, re-reads both GETs and stops with the builder step when the status did not move. Refuses the template, a form not in `glow.forms.LIVE`, and a form with a submission in the last 30 days without `--disable-anyway`. The runner skips a `DISABLED` form (`skipped`), the audit prints `[DISABLED]`; a disabled form is never synced down to an empty Club picker | Jotform API |
| `tools/backfill_feedback_review.py` | One-off (2026-09-28): ReviewQueue items for problem reports that asked for a roster change before the handler queued them itself; runs the handler's own `.gs` classifier through Node | Sheets API |
| `tools/backfill_resolve.py` | September 2026 back-fill, read-only: every active submission of the four regional forms as one row per (submission, ticked roster) in `data/backfill_2026-09/resolved.json` - the club from the ticked roster, its partner and Club Name from the sync's own dry run (`--summary-json sf_names`), the module from the module dropdown the submission used (not question 98, which page translation rewrote), flags (listed in `flag_vocabulary`), a no-tick list and a ledger; prints counts only | Jotform API (GET), the sync as a dry run |
| `tools/fix_module_values.py` | One-off correction in Salesforce (`docs/plans/2026-10-06-module-selection.md`): every `Attendance_Batch__c` since launch whose `Module__c` is not an option of the template's module dropdowns (a Spanish rendering written by page translation before the module `calcValues` were live), and the `Attendance__c` rows under it, set to the English option. The ground truth is the Jotform submission the batch came from - exactly one on the form of the batch's region (`SF_REGION_FORM`), created within 3 hours of it, with the same question 5, date, question 98, year and session (whole numbers) - and the module is `backfill_resolve.copied_fields`' stored dropdown answer; anything less is `UNMATCHED` and left alone. Dry run by default; `--apply --vpn-off` writes the batch then its rows through `sf_backfill.Org.update`, one record per request, each with an open and a closing ledger row (`written` / `failed_<status>` / `check`, `data/module_fix_2026-10/ledger.csv`) and stops at the first thing not as planned; `--undo <ledger>` puts `old` back. Every Salesforce read is an explicit-field SOQL query - never the names list or the status message | Jotform API (GET), Salesforce through the CLI login |
| `tools/sf_girls_present.py` | One-off back-fill in Salesforce (`docs/plans/2026-10-06-attendance-totals.md`, C): `Girls_Present__c` on every `Success` batch from before the field existed, = its attendance rows (0 for a blank); `Failed` batches stay empty, a batch with a value is never touched (a typed partner total survives). `plan` (live, read-only: ids, statuses, creator kinds, rows, values → `data/sf_girls_present/plan.csv`), `set` (a dry run from the plan; `--apply --vpn-off` re-reads each batch, PATCHes through `Org.update`, re-reads, one open and one closing ledger row), `check` (Jotform `Success` batches whose count differs from their rows, and `Success` batches without a value: both 0 when healthy). Ids and counts only | Salesforce through the CLI login |
| `tools/worklog.py` | The work log behind the monthly invoice: hours per day from the session transcripts on the Mac's clock at the time (`worklog/timezones.csv`, `zone`), descriptions, `export --month` | local files |
| `tools/needs_attention.py`, `tools/derive_partner_regions.py` | Data-quality report; partner → region derivation (generates `appsscript/Regions.gs`) | local snapshots |
| `tools/add_translations.py`, `add_language.py`, `restore_translations.py`, `switcher_flags.py`, `add_feedback_link.py`, `clone_regional.py` | Languages, switcher flags for languages Jotform has none for (`injectCSS`), the links above Submit (problem report, Club Roster Form — `glow/links.py`), building a regional form | Jotform API |
| `tools/fix_name_translations.py` | Removes from each form's translation store (`base`/`en`) exactly the entries whose lookup alters a roster option of any of the five forms (stale spellings of girls' names), found by emulating Jotform's runtime (`glow/translation_lookup.py`); store saved first (mode 600), re-read, audited, the public page read and re-rendered if needed; `--restore` puts the entries back. Counts and club names only | Jotform API, the public page |
| `tools/fix_roster_order.py` | One-time repair (BACKLOG 47): the links, Submit and the hidden bridge fields move to empty orders after the last roster, so every roster renders above them; `glow/layout.py` holds the plan, the order the sync gives a new roster, and the `form_status` layout check | Jotform API |
| `tools/update_static_fields.py` | The fields the sync never touches: label wording, the Group Photo limits, and the header logo (`--image-src`, since the API cannot upload an asset). Declarative — wanted properties per field name, re-read and compared after every write | Jotform API |
| `appsscript/*.gs` | Bound to the sheet: config, normalization, ids, roster ops, form generation, submission handlers, menu, dispatch | Google services |
| `test/`, `scripts/`, `Makefile` | The offline feedback loop (`make check`) | nothing |

`appsscript/Config.gs` documents the Script Properties and the Salesforce
mapping's dependence on question ids. `Roster.gs`, `Forms.gs`,
`FormHandlers.gs`, `Menu.gs` call Google services; `Config.gs`,
`Normalize.gs`, `Ids.gs`, `Regions.gs`, `RosterOps.gs`, `Dispatch.gs` have no
top-level side effects and run in Node through `test/load_gs.js`.

## Constants that exist on both sides

Change both, or `test/gs_parity_test.py` (`PythonAppsScriptParity`) fails:

| Constant | Python | Apps Script |
|---|---|---|
| Live form ids | `tools/auto_sync.py REGIONAL_FORMS`, `tools/form_status.py FORMS`, `backup_forms.py FORMS`, `tools/add_*.py`, `tools/clone_regional.py` | `Config.gs FORMS` |
| Structural question ids (club name 5, partner 331, year 94, modules 14/92/93, sessions 15/95/96/97, bridge 18/98/100/102, enableFuzzy 109) | `sync_attendance_form.py` top, `tools/form_status.py` | `Config.gs QID` |
| `SESSION_OVERRIDES` (sessions per elective module) | `sync_attendance_form.py` | `Config.gs` |
| `SF_NAME_SEP` (`" - "` between club and partner in the name of a club whose name two partners share: club-list entry = question 5 = Salesforce account) | `glow/sync.py` | `Config.gs` |
| Roster tab columns | `read_roster_csv` needs `partner, club, full_name, status, region`; `upload_roster.py` positional | `Config.gs ROSTER_COLS` |
| Partners tab columns (`partner, region, notes, jotform`; `jotform` = `no` keeps a partner's clubs off the attendance forms) | `glow/sync.py PARTNER_COLS`, `JOTFORM_COL`, `read_partners_csv` | `Roster.gs PARTNER_COLS`, `tools/build_roster_offline.js` |
| The sheet's time zone (`America/New_York`: the day `removed_date` is stamped in, which the no-active-girl rule compares "today" with) | `glow/sync.py SHEET_ZONE`, `sheet_today` | the spreadsheet's own setting (File → Settings), `getSpreadsheetTimeZone()` in `Roster.gs today_()` — not `appsscript.json`'s `timeZone`; no offline test can read it, so `tools/auto_sync.py` checks it on every run |
| Response-tab header fragments | `sync_attendance_form.py COL_*` | `Config.gs RESPONSE_COLS` |
| SyncLog columns | `tools/auto_sync.py SYNC_LOG_COLS` | `Roster.gs SYNC_LOG_COLS` |
| SF Pending columns (`test/sf_new_clubs_test.py` compares them) | `tools/sf_new_clubs.py SF_PENDING_COLS` | `FormHandlers.gs SF_PENDING_COLS` |
| Region vocabulary `Africa / Asia / Latin America / U.S` | everywhere as strings | `Regions.gs` values, Partners tab |

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
  different one in Python (the intake errs toward holding). Cells the form
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
- `read_roster_csv` matches `--region` case-insensitively; `form_status.py`
  matches the region string exactly.
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

## Generated and placeholder code

- `appsscript/Regions.gs` — generated by `tools/derive_partner_regions.py --write`
  from the pre-launch regional forms; the sheet's Partners tab overrides it.
  Never hand-edit (the edit hook refuses).
- `test/fixtures/enrollment_sample.csv`, `expected.json` — generated by
  `test/fixtures/make_fixture.py`; `make fixtures-check` fails when stale.
- `Config.gs` `QID`, `FORMS`, `SESSION_OVERRIDES`, `getApiKey_` and
  `Ids.gs renameClubInRegistry_` are not referenced yet: scaffolding for a
  native Apps Script sync (superseded by the auto-sync workflow; kept for
  the constants test and the ReviewQueue rename flow).

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
