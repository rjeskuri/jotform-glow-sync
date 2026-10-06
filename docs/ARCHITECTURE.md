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
| `sync_attendance_form.py` | The product: makes one form match the sheet — creates/updates roster questions, regenerates every condition (visibility rules, curriculum cascade, Salesforce bridge, and — on a form with the club guard — the one-club rules), and keeps the Club picker and the club guard's warning (found by field name, `clubPicker` / `clubGuard`, added once by `--club-picker` / `--club-guard`) in shape. A club whose name another partner's club shares has its own picker entry, `<club> - <partner>` — the text question 5 sends to Salesforce (`glow/sync.py` `SF_NAME_SEP`, `sf_club_name`): each roster keeps the form its rule has (read back, never flipped), `--same-name-switch` makes the shared names long by hand, a new club with a name in use is not created, and any other change of an existing club's question 5 needs `--q5-change-ok`. A plain roster's rule names no partner, so where the Roster has another partner's club of that name its owner is read from the Roster's rows of any status (`roster_names`: whose rows list at least half, and the most, of the girls the question holds) — a retired club's question is never taken over by a newcomer. New rosters are created above the links and Submit (`glow/layout.py`). Question 18 (Contact_IDs) is rule 0 on a picker form, with the picker as an operand, and every roster carries Jotform's `required` flag (`glow/sync.py` `CONTACT_IDS_FIRST`, `CONTACT_IDS_PICKER_OPERAND`, `ROSTERS_REQUIRED`, read at run time: turning one off and applying is the rollback); it warns when the live rules calculate question 18 the old way. Dry run by default, `--apply` writes, `--summary-json` for the runner (its `sf_names`: what every roster sends; `requires`: rosters whose flag alone is written) | Jotform API via `curl` |
| `backup_forms.py`, `restore_conditions.py` | Snapshot and rollback (conditions only; a snapshot whose rules test clubs the Club picker no longer offers is refused; one that calculates question 18 the old way restores with a note) | Jotform API |
| `tools/form_status.py` | Read-only audit of every form vs the Roster export, rule by rule (rosters grouped by the text their rule tests; the picker's options are those texts; question 18's place, operands and equation and the rosters' required flag, the module dropdowns' `calcValues`, and the module chain's shape - year, module and session dropdowns single-select and required, the form-level `clearFieldOnHide` - each as `glow/sync.py`'s constants say; the names dictionary, emulated by `glow/translation_lookup.py`: no roster option altered in any language); `--rendered` reads the public page (counts only: picker and module `data-calcvalue`, no module select served `multiple`, `JotForm.clearFieldOnHide`, question 18 in `JotForm.setConditions` / `setCalculations`, `validate[required]` boxes, the embedded translation store against the boxes served, the runtime build); `--json` | Jotform API, the public page |
| `tools/integration_status.py` | Read-only: every form's Salesforce integration against the one known action (create `Attendance_Batch__c`, eight fields from their questions, `Account_Name__c` from question 5, no upload since 2026-10-01, one connection for the live forms, none on the old ones) and the other integration blocks a form carries (`other integrations:`, where the Google Drive block's key will show once Ryan sets it up); the builder is the only writer | Jotform API |
| `tools/auto_sync.py` | The unattended loop (export → plan → bands → backup → apply → verify → SyncLog). ATTENTION also for a question-5 change of an existing club (the region is not applied), question 18 calculated the old way, a required flag written on its own or a module dropdown's `calcValues` (the region is not applied: each is rolled out by hand), a new club refused for its name, a name two clubs send, and roster rules that test a name the Club picker does not list (never `in-sync`; the rules-only rewrite is applied by hand) | Sheets API, the tools above |
| `tools/sheets_client.py` | Service-account access to the sheet; importable (`read_tab`, `append_rows`, `write_tab`) | Sheets API |
| `tools/upload_roster.py`, `tools/build_roster_offline.js` | Rebuild the Roster tabs offline with the *same* `.gs` code, upload them | local, Sheets API |
| `tools/rename_club.py` | Rename a club in place: Roster/ClubRegistry/SF Pending cells (code kept) and the question label on the region's form and the template; the sync then follows. `--new-partner` moves a club filed under a mistyped partner: the same tabs' partner cells in one batch, and the typo's Partners row blanked with a note; the forms are only read (checked for a Partner-gated rule) unless `--new` renames too. A question is found by its text, so where another partner has a club of the old name a rename refuses a question that holds that other club's girls: a club the sync did not add is renamed with `--sheet-only` | Sheets API, Jotform API |
| `tools/backfill_feedback_review.py` | One-off (2026-09-28): ReviewQueue items for problem reports that asked for a roster change before the handler queued them itself; runs the handler's own `.gs` classifier through Node | Sheets API |
| `tools/backfill_resolve.py` | September 2026 back-fill, read-only: every active submission of the four regional forms as one row per (submission, ticked roster) in `data/backfill_2026-09/resolved.json` - the club from the ticked roster, its partner and Club Name from the sync's own dry run (`--summary-json sf_names`), the module from the module dropdown the submission used (not question 98, which page translation rewrote), flags (listed in `flag_vocabulary`), a no-tick list and a ledger; prints counts only | Jotform API (GET), the sync as a dry run |
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

Change both, or `test/python_test.py` (`PythonAppsScriptParity`) fails:

| Constant | Python | Apps Script |
|---|---|---|
| Live form ids | `tools/auto_sync.py REGIONAL_FORMS`, `tools/form_status.py FORMS`, `backup_forms.py FORMS`, `tools/add_*.py`, `tools/clone_regional.py` | `Config.gs FORMS` |
| Structural question ids (club name 5, partner 331, year 94, modules 14/92/93, sessions 15/95/96/97, bridge 18/98/100/102, enableFuzzy 109) | `sync_attendance_form.py` top, `tools/form_status.py` | `Config.gs QID` |
| `SESSION_OVERRIDES` (sessions per elective module) | `sync_attendance_form.py` | `Config.gs` |
| `SF_NAME_SEP` (`" - "` between club and partner in the name of a club whose name two partners share: club-list entry = question 5 = Salesforce account) | `glow/sync.py` | `Config.gs` |
| Roster tab columns | `read_roster_csv` needs `partner, club, full_name, status, region`; `upload_roster.py` positional | `Config.gs ROSTER_COLS` |
| Response-tab header fragments | `sync_attendance_form.py COL_*` | `Config.gs RESPONSE_COLS` |
| SyncLog columns | `tools/auto_sync.py SYNC_LOG_COLS` | `Roster.gs SYNC_LOG_COLS` |
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
3. The constants table above — `test/python_test.py` parses `Config.gs`.
4. `RosterOps.gs sharedClubNames_` / `sfClubName_` ↔ `glow/sync.py`
   `shared_club_names` / `sf_club_name` — which clubs are
   `<club> - <partner>` (a name that active clubs of two or more partners
   have, all regions). Python decides what the forms send (the one-time
   `--same-name-switch`; afterwards a form's long or plain name is sticky);
   Apps Script uses the rule for the Monday e-mail's Salesforce lines only.
   Each side is tested on its own, with fictional names
   (`test/forms_logic_test.js`, `test/python_test.py`), and
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
