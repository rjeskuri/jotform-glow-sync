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
   Account_Name__c ← qid 5 (club), Contact_IDs__c ← qid 18 (ONE aggregate calculation over every
   roster, "ignore hidden fields" on, so only the visible club's ticked names arrive),
   Module__c / Module_Week__c / Module_Year__c ← qids 98 / 100 / 102
   (with the club guard: Submit is hidden and disabled unless q5 is exactly one picker option,
   so only one roster is visible when a mentor submits — docs/plans/2026-09-29-club-guard.md)
```

The legacy path still exists for the template form: a CSV export of the raw
enrollment responses → `sync_attendance_form.py read_sheet` (no `--roster`).

## Components

| Where | What | Talks to |
|---|---|---|
| `sync_attendance_form.py` | The product: makes one form match the sheet — creates/updates roster questions, regenerates every condition (visibility rules, curriculum cascade, Salesforce bridge, and — on a form with the club guard — the one-club rules), and keeps the Club picker, the partner list and the club guard's warning (found by field name, `clubPicker` / `partnerPicker` / `clubGuard`, added once by `--club-picker` / `--partner-picker` / `--club-guard`) in shape. New rosters are created above the links and Submit (`glow/layout.py`). Dry run by default, `--apply` writes, `--summary-json` for the runner | Jotform API via `curl` |
| `backup_forms.py`, `restore_conditions.py` | Snapshot and rollback (conditions only) | Jotform API |
| `tools/form_status.py` | Read-only audit of every form vs the Roster export, rule by rule; `--json` | Jotform API |
| `tools/auto_sync.py` | The unattended loop (export → plan → bands → backup → apply → verify → SyncLog) | Sheets API, the tools above |
| `tools/sheets_client.py` | Service-account access to the sheet; importable (`read_tab`, `append_rows`, `write_tab`) | Sheets API |
| `tools/upload_roster.py`, `tools/build_roster_offline.js` | Rebuild the Roster tabs offline with the *same* `.gs` code, upload them | local, Sheets API |
| `tools/rename_club.py` | Rename a club in place: Roster/ClubRegistry/SF Pending cells (code kept) and the question label on the region's form and the template; the sync then follows. `--new-partner` moves a club filed under a mistyped partner: the same tabs' partner cells in one batch, and the typo's Partners row blanked with a note; the forms are only read (checked for a Partner-gated rule) unless `--new` renames too | Sheets API, Jotform API |
| `tools/backfill_feedback_review.py` | One-off (2026-09-28): ReviewQueue items for problem reports that asked for a roster change before the handler queued them itself; runs the handler's own `.gs` classifier through Node | Sheets API |
| `tools/worklog.py` | The work log behind the monthly invoice: hours per day from the session transcripts on the Mac's clock at the time (`worklog/timezones.csv`, `zone`), descriptions, `export --month` | local files |
| `tools/needs_attention.py`, `tools/derive_partner_regions.py` | Data-quality report; partner → region derivation (generates `appsscript/Regions.gs`) | local snapshots |
| `tools/add_translations.py`, `add_language.py`, `restore_translations.py`, `switcher_flags.py`, `add_feedback_link.py`, `clone_regional.py` | Languages, switcher flags for languages Jotform has none for (`injectCSS`), the links above Submit (problem report, Club Roster Form — `glow/links.py`), building a regional form | Jotform API |
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
   (`test/forms_logic_test.js`, `test/python_test.py`); there is no
   cross-language run.

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
logs. Club and partner names, and the live form ids, are in the repository —
it stays private.
