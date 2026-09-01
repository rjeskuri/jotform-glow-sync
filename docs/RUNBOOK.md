# Runbook

Every operational procedure, in one place, each with its dry-run and its
apply form. Everything here talks to LIVE systems (the four regional Jotform
attendance forms, the master enrollment Google Sheet, the Apps Script bound to
it, and through the forms, Salesforce). The forms and the sheet went live on
2026-09-01.

## The forms

| Region | Form id | Mentor link |
|---|---|---|
| Africa | `262382821971058` | https://form.jotform.com/262382821971058 |
| Asia | `262383129464057` | https://form.jotform.com/262383129464057 |
| Latin America | `262383455778067` | https://form.jotform.com/262383455778067 |
| U.S | `262382706852058` | https://form.jotform.com/262382706852058 |
| Template (every logic change lands here first) | `262352490535154` | not for mentors |

The five pre-launch forms are retitled "(defunct)" and still enabled until
they are switched off (backlog item 1). The same table lives in
`tools/auto_sync.py` (`REGIONAL_FORMS`), `tools/form_status.py`,
`backup_forms.py` and `appsscript/Config.gs`; `test/python_test.py` fails if
they drift apart.

## Credentials

- **Jotform API key** — `JOTFORM_API_KEY` in the environment. Put it in `.env`
  (`cp .env.example .env`, `chmod 600 .env`) and load with
  `set -a; source .env; set +a`. Never type it on a command line inside Claude
  Code: command lines end up in `.claude/settings.local.json` and in
  transcripts (that happened once; the key was rotated). A read-only key is
  enough for `form_status.py`, `backup_forms.py` and every dry run.
- **Google Sheet** — service account key at `credentials/service-account.json`
  (or `GLOW_SA_KEY`), sheet id in `credentials/config.json` (or
  `GLOW_SHEET_ID`). Setup: [SHEETS-ACCESS.md](SHEETS-ACCESS.md).
- **Apps Script** — Script Properties (File → Project Settings): `FORM_ROSTER_ID`,
  `FORM_FEEDBACK_ID`, `STAFF_NOTIFY_EMAIL`, and for the automatic sync
  `SYNC_DISPATCH_REPO`, `SYNC_DISPATCH_TOKEN`.
- **GitHub Actions** (automatic sync) — repository secrets `JOTFORM_API_KEY`,
  `GLOW_SA_JSON` (the whole service-account file), `GLOW_SHEET_ID`; repository
  variable `AUTO_SYNC_APPLY` (`0` = dry runs only, `1` = writes).

## The live gate (Claude Code)

`.claude/hooks/live_gate.sh` blocks any command Claude runs that contains
`--apply`, `--prune`, `clasp push`, `clasp:push` or `sheets_client.py import`,
unless `GLOW_LIVE_OK=1` was exported in the shell **before** Claude Code was
started. A command that sets `GLOW_LIVE_OK` itself is always blocked. Every
decision is logged to `.claude/live_gate.log`. To let Claude write to a live
system: read the dry run, check the backup exists, then either run the command
yourself or restart Claude Code with the variable exported. Running commands
yourself in a terminal is never affected.

## Keeping the forms in step with the Roster (the manual loop)

The automatic sync (below) does this on every roster change and every
morning. By hand, per region:

```bash
python3 tools/sheets_client.py export Roster data/roster_<date>.csv        # 1. export
python3 tools/form_status.py --roster data/roster_<date>.csv               # 2. what differs? (read-only)
python3 backup_forms.py --form 262382821971058                             # 3. snapshot the form
python3 sync_attendance_form.py data/roster_<date>.csv --roster \
        --region Africa --form 262382821971058                             # 4. dry run
python3 sync_attendance_form.py data/roster_<date>.csv --roster \
        --region Africa --form 262382821971058 --apply                     # 5. apply
python3 tools/form_status.py --form 262382821971058 --roster data/roster_<date>.csv   # 6. verify: CLEAN
```

Or all four regions in one go, with the same guards the workflow uses:

```bash
python3 tools/auto_sync.py --no-synclog            # dry run, every region
python3 tools/auto_sync.py --no-synclog --apply    # apply within the bands
```

What to know:

- `form_status.py` without `--roster` compares against the stale offline
  build `data/roster_build/Roster.csv` — always pass the fresh export.
- The sync rewrites every condition on every run (`REPLACE conditions` is
  always in the plan); "changed" means a `CREATE`, `UPDATE` or `DELETE` line.
- Never `--prune` a live form. It deletes questions and is for fresh clones
  only; the sync refuses it on any form with submissions.
- Active roster rows with a **blank region** reach no form and no tool warns
  except `auto_sync.py` (ATTENTION) and the sheet's ReviewQueue. Fill in the
  Partners tab, then **GLOW → Refresh regions from the Partners tab**.
- Region spelling must be exactly `Africa`, `Asia`, `Latin America`, `U.S`.

## Automatic sync

**Path:** a roster change in the sheet (New Club / Roster Modification form,
a rebuild, or a region refresh) → `appsscript/Dispatch.gs` sends a
`repository_dispatch` event to GitHub → `.github/workflows/auto-sync.yml` →
`tools/auto_sync.py` exports the Roster tab and, per region, dry-runs the
sync, checks the safety bands, backs up, applies, verifies with
`form_status.py`, and appends a row to the sheet's **SyncLog** tab. The
workflow also runs every morning (06:00 Chicago) as a backstop for missed
events and manual sheet edits, and can be started by hand from the Actions
tab ("Run workflow", optional region).

**Safety bands** (per region, per run; `--max-creates`, `--max-updates`):
at most 5 new clubs and 20 roster updates; never a delete; not when a roster
would be replaced by one sharing no names with the current one; not when the
export looks truncated (fewer than 1,000 active rows, or many clubs on the
form missing from the export). Outside the bands nothing is written, the
region is logged as `attention`, and `data/auto_sync/ATTENTION.md` (kept as
a workflow artifact) says what to do. The workflow fails visibly (GitHub
emails the repository owner) on `attention` (exit 2) and on any failure
(exit 1).

**SyncLog columns:** `when, trigger, region, mode, creates, updates, rules,
result, detail, run_url`. `mode` is `dry-run` or `apply`; `result` is one of
`in-sync`, `dry-run` (would apply), `applied`, `applied-with-problems`,
`applied-unverified`, `attention`, `failed`. The Audit tab additionally gets
a `syncRequested … → HTTP 204` row every time the sheet sends the event.

**Switches:**

- Repository variable `AUTO_SYNC_APPLY`: `0` = every run is a dry run (start
  here; read a day of SyncLog rows), `1` = runs apply within the bands.
- Script Properties `SYNC_DISPATCH_REPO` / `SYNC_DISPATCH_TOKEN` unset = the
  sheet sends nothing (the daily run still happens).
- Manual runs from the Actions tab apply only when both `AUTO_SYNC_APPLY=1`
  and the "apply" input is ticked.

**First-time setup** (once, by the sheet's owner):

1. Rotate the Jotform key; add the three secrets and the variable to the
   private GitHub repo (Settings → Secrets and variables → Actions).
2. Create a fine-grained personal access token limited to this repository
   with *Contents: read and write*; set `SYNC_DISPATCH_REPO=<owner>/<repo>`
   and `SYNC_DISPATCH_TOKEN=<token>` in the sheet's Script Properties.
3. `npm run clasp:push`, then in the sheet **GLOW → Set up tabs** (creates
   `SyncLog`) and **GLOW → Google Forms → Request Jotform sync now**. The
   first call asks you to authorize the new "connect to an external service"
   scope; until then the notification fails softly into the Audit tab.
4. Watch the Actions run (dry run) and the SyncLog row; after a clean day set
   `AUTO_SYNC_APPLY=1`.

**Rollback:** the workflow keeps `backups/<form>/properties-<stamp>.json`
(conditions only, no names) as an artifact for 30 days;
`python3 restore_conditions.py --form <id> --from <file> --apply` puts the
conditions back. Questions are never deleted by the runner. To stop the
automation: `AUTO_SYNC_APPLY=0` (or clear the two Script Properties).

## The Club picker (mentors choose their club instead of typing it)

Intent: [intent/2026-09-01-club-picker.md](intent/2026-09-01-club-picker.md).
A required **Club** dropdown listing every club on the form; the roster
rules key on it, and a calculation copies the pick into the (now hidden)
Club Name textbox, question 5, which is what the Salesforce mapping reads —
so `Account_Name__c` still receives the plain club name. Added once per
form; from then on every sync run keeps its option list equal to the form's
clubs (`UPDATE club picker (N clubs)` in the plan).

```bash
python3 backup_forms.py --form 262352490535154
python3 sync_attendance_form.py data/roster_<date>.csv --roster --form 262352490535154 --club-picker            # dry run
python3 sync_attendance_form.py data/roster_<date>.csv --roster --form 262352490535154 --club-picker --apply    # add it
python3 tools/form_status.py --form 262352490535154 --roster data/roster_<date>.csv     # "club picker: q<id>", rules CLEAN
```

(The template takes no `--region`; a regional form takes its `--region`.)
Verify in the browser: pick a club → its names appear; pick another → they
swap; submit a test → the submission and Salesforce show the club name in
the Club Name field. Rollback: `restore_conditions.py` for the rules, and in
the builder delete the Club dropdown and un-hide Club Name (or
`question[hidden]=No`, `question[required]=Yes` on q5 via the API).

Before the regional rollout add the label and sublabel ("Club", "Choose
your club from the list…") to `tools/translations_additions.json` and run
`tools/add_translations.py --apply` on each form, or the picker shows in
English in every language.

## Backup and restore (Jotform)

```bash
python3 backup_forms.py                       # every known form -> backups/<id>/{questions,properties}-<stamp>.json
python3 backup_forms.py --form <id>           # one form (2 API calls)
python3 restore_conditions.py --form <id>              # preview restoring the latest snapshot's conditions
python3 restore_conditions.py --form <id> --apply      # restore
```

Restores touch only the conditions; questions, emails and the Salesforce
integration are left alone. Jotform's own Revision History is the second
rollback path. `backups/` holds rosters and never enters git.

## Translations

```bash
python3 tools/add_translations.py --audit                 # which labels lack translations
python3 tools/add_translations.py                         # preview (uses tools/translations_additions.json)
python3 tools/add_translations.py --apply
python3 tools/add_language.py --code or --name Oriya --dict tools/translations_or.json          # preview
python3 tools/add_language.py --code or --name Oriya --dict tools/translations_or.json --apply
python3 tools/restore_translations.py --form <clone id> --check   # after a clone: is the switcher intact?
```

Jotform's `POST /form/{id}/translations` replaces a language's whole
dictionary — the tools always GET, merge, then POST. A new English string
must also be written to `base` and `en` or its translations never apply
(details: `.claude/skills/jotform-api/SKILL.md`).

## Apps Script deploy

```bash
make gs                 # every .gs file parses (a broken file breaks every form handler)
npm run clasp:push      # gated: GLOW_LIVE_OK=1 for Claude, or run it yourself
```

Setup and the manual-paste fallback: [../appsscript/INSTALL.md](../appsscript/INSTALL.md).
Adding a Google service to a `.gs` file (UrlFetchApp, MailApp…) adds an
OAuth scope — the next menu action asks for re-authorization once. Rollback
is a push of the previous commit's `appsscript/`.

## Roster rebuild and upload (offline path)

Used when the Roster tab has to be rebuilt from the raw enrollment responses
outside the sheet:

```bash
python3 tools/sheets_client.py export-all data/live_<date>
node tools/build_roster_offline.js data/enrollment_<date>.csv --existing data/live_<date>
python3 tools/upload_roster.py                      # preview
python3 tools/upload_roster.py --apply --replace    # write; previous tabs saved under data/roster_build/previous/
```

## Data-quality report

```bash
python3 tools/needs_attention.py data/enrollment_<date>.csv     # -> data/needs_attention_<date>.csv
```

## Building a new regional form (not maintenance)

`tools/clone_regional.py <region> <roster.csv> [--apply]` clones the
template, restores the languages, syncs one region with `--prune` and prints
the status. Only for a fresh form; never against a live one.

## Checks

```bash
make check      # everything offline: JS parity + logic tests, Python tests, .gs parse, secrets, links, fixture
make help       # the individual targets
```

Real-data parity runs automatically when `data/enrollment_2026-08-24.csv`
exists (`CSV=<path>` to point elsewhere, `PARITY_REAL=0` to skip).
