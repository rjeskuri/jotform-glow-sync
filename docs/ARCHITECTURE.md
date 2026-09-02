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
   ├─ handleNewClub_      → RosterOps.gs planClub_
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
```

The legacy path still exists for the template form: a CSV export of the raw
enrollment responses → `sync_attendance_form.py read_sheet` (no `--roster`).

## Components

| Where | What | Talks to |
|---|---|---|
| `sync_attendance_form.py` | The product: makes one form match the sheet — creates/updates roster questions, regenerates every condition (visibility rules, curriculum cascade, Salesforce bridge). Dry run by default, `--apply` writes, `--summary-json` for the runner | Jotform API via `curl` |
| `backup_forms.py`, `restore_conditions.py` | Snapshot and rollback (conditions only) | Jotform API |
| `tools/form_status.py` | Read-only audit of every form vs the Roster export, rule by rule; `--json` | Jotform API |
| `tools/auto_sync.py` | The unattended loop (export → plan → bands → backup → apply → verify → SyncLog) | Sheets API, the tools above |
| `tools/sheets_client.py` | Service-account access to the sheet; importable (`read_tab`, `append_rows`, `write_tab`) | Sheets API |
| `tools/upload_roster.py`, `tools/build_roster_offline.js` | Rebuild the Roster tabs offline with the *same* `.gs` code, upload them | local, Sheets API |
| `tools/needs_attention.py`, `tools/derive_partner_regions.py` | Data-quality report; partner → region derivation (generates `appsscript/Regions.gs`) | local snapshots |
| `tools/add_translations.py`, `add_language.py`, `restore_translations.py`, `add_feedback_link.py`, `clone_regional.py` | Languages, the problem-report link, building a regional form | Jotform API |
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

## Known divergences (documented, not fixed — see the backlog)

- `read_sheet` keeps a row with an empty partner; `readResponses_` drops it.
- `parseRoster_` strips `•` and `*` bullets; `parse_roster` strips only `-`.
- `parse_roster` strips invisible characters from roster lines only;
  `tidy_` strips them from partner and club cells too.
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
