# Giving the tooling access to the master enrollment spreadsheet

The spreadsheet holds girls' names, so it must never be shared "anyone with
the link". The tools sign in as a **service account** — a robot Google user
that you share the sheet with, exactly like sharing it with a colleague.
Nothing becomes public, you can revoke it any time by un-sharing, and the key
file stays in `credentials/` (gitignored, read-denied to Claude Code). In
GitHub Actions the same key arrives as the secret `GLOW_SA_JSON`.

One-time setup, about ten minutes:

1. Go to <https://console.cloud.google.com/> (any Google account — the
   project just hosts the robot). Create a project, e.g. `glow-sheets-tooling`
   (the existing one has a different name; the name does not matter).
2. **APIs & Services → Library** → search *Google Sheets API* → **Enable**.
   (Only the Sheets API is needed; Drive is not.)
3. **IAM & Admin → Service Accounts → Create service account**. Name it
   `glow-sync`. Skip the optional role/permission steps. Create.
4. Open the new service account → **Keys → Add key → Create new key → JSON**.
   Move the downloaded file to `credentials/service-account.json`.
5. Tell the tools which spreadsheet: `credentials/config.json` containing

       {"spreadsheet_id": "<the long token in the sheet's URL after /d/>"}

   (`credentials/config.example.json` is the template; the `GLOW_SHEET_ID`
   environment variable overrides it, and `GLOW_SA_KEY` the key path.)
6. Copy the service account's email — `python3 tools/sheets_client.py whoami`
   prints it (it ends in `iam.gserviceaccount.com`). In the spreadsheet click
   **Share**, paste it, give it **Editor**, untick "Notify", Share.
7. Test: `python3 tools/sheets_client.py tabs` lists the sheet's tabs with
   their data row counts.

Why Editor and not Viewer: the tools create and fill the Roster, Partners,
ClubRegistry, ReviewQueue, Audit and SyncLog tabs (and, once, the *Enrollment
Responses* import). The spreadsheet is the **master enrollment** sheet — the
original response sheet stayed with its owner, so its data came across as a
CSV export.

## What the tools do with it

| Command | Effect |
|---|---|
| `python3 tools/sheets_client.py export Roster data/roster_<date>.csv` | The Roster tab, the input of every sync |
| `python3 tools/sheets_client.py export "Enrollment Responses" data/enrollment_<date>.csv` | Export the imported responses tab |
| `python3 tools/sheets_client.py import "Enrollment Responses" data/enrollment_<date>.csv` | One-time import of the original form's responses (refuses to overwrite) |
| `python3 tools/sheets_client.py export-all data/live_<date>` | Every tab, for rebuilding against the live state |
| `node tools/build_roster_offline.js data/enrollment_<date>.csv [--existing data/live_<date>]` | Builds the five tabs locally in `data/roster_build/` using the *same* code that runs inside the sheet |
| `python3 tools/upload_roster.py [--apply] [--replace]` | Writes them to the spreadsheet — Roster and ClubRegistry replaced, Partners merged (staff edits win), ReviewQueue and Audit appended |
| `python3 tools/auto_sync.py` | Reads the Roster tab in-process and appends to SyncLog (see `RUNBOOK.md`) |
| `python3 tools/needs_attention.py data/enrollment_<date>.csv` | The list of clubs and names that need a human to chase down |

**First upload** (empty tabs): build, then `upload_roster.py --apply`.

**Any later upload** (the sheet already has data): export the live tabs first
and build against them, so IDs minted in the sheet are never re-minted:

    python3 tools/sheets_client.py export-all data/live_<date>
    node tools/build_roster_offline.js data/enrollment_<date>.csv --existing data/live_<date>
    python3 tools/upload_roster.py --apply --replace

`upload_roster.py` refuses to run if the sheet holds a girl ID the local build
does not — the sign that the `--existing` step was skipped.

With the Apps Script deployed (`../appsscript/INSTALL.md`), the GLOW menu
maintains those tabs going forward; re-running its rebuild after an upload
leaves Roster, ClubRegistry and Partners unchanged (ReviewQueue only gains
genuinely new questions; Audit gains one line per run), which is the check
that both paths agree. That held before launch. Since 2026-09-01, neither
path is run: both re-derive from the raw responses (`RUNBOOK.md`, "Roster
rebuild and upload").
