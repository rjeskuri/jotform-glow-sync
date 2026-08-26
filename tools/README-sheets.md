# Giving the tooling access to the enrollment spreadsheet

The spreadsheet holds girls' names, so it must never be shared "anyone with
the link". Instead the tools sign in as a **service account** — a robot Google
user that you share the sheet with, exactly like sharing it with a colleague.
Nothing becomes public, you can revoke it any time by un-sharing, and the key
file stays on this laptop (`credentials/` is gitignored — commit `.gitignore`
before anything else if you ever clone this repo fresh).

One-time setup, about ten minutes:

1. Go to <https://console.cloud.google.com/> (sign in with the Google account
   that owns the sheet, or any account — the project just hosts the robot).
   Create a project, e.g. `glow-sheets-tooling`.
2. **APIs & Services → Library** → search *Google Sheets API* → **Enable**.
3. **IAM & Admin → Service Accounts → Create service account**. Name it
   `glow-sync`. Skip the optional role/permission steps. Create.
4. Open the new service account → **Keys → Add key → Create new key → JSON**.
   A file downloads. Move it to:

       ~/jotform-glow-sync/credentials/service-account.json

5. Tell the tools which spreadsheet: create
   `~/jotform-glow-sync/credentials/config.json` containing

       {"spreadsheet_id": "<the long token in the sheet's URL after /d/>"}

6. Copy the service account's email (looks like
   `glow-sync@glow-sheets-tooling.iam.gserviceaccount.com`; also printed by
   `python3 tools/sheets_client.py whoami`). In the spreadsheet click
   **Share**, paste that email, give it **Editor**, untick "Notify", Share.
7. Test:

       python3 tools/sheets_client.py tabs

   You should see `Form Responses 1` with its number of data rows (around 350).

Why Editor and not Viewer: the tools create and fill the Roster, Partners,
ClubRegistry, ReviewQueue and Audit tabs. They never write to
`Form Responses 1`.

## What the tools do with it

| Command | Effect |
|---|---|
| `python3 tools/sheets_client.py export "Form Responses 1" data/enrollment_<date>.csv` | Fresh export without the manual download |
| `python3 tools/sheets_client.py export-all data/live_<date>` | Every tab, for rebuilding against the live state |
| `node tools/build_roster_offline.js data/enrollment_<date>.csv [--existing data/live_<date>]` | Builds the five tabs locally in `data/roster_build/` using the *same* code that runs inside the sheet |
| `python3 tools/upload_roster.py [--apply] [--replace]` | Writes them to the spreadsheet — Roster and ClubRegistry replaced, Partners merged (staff edits win), ReviewQueue and Audit appended |
| `python3 tools/needs_attention.py data/enrollment_<date>.csv` | The list of clubs and names that need a human to chase down |

**First upload** (empty tabs): build, then `upload_roster.py --apply`.

**Any later upload** (the sheet already has data): export the live tabs first
and build against them, so IDs minted in the sheet are never re-minted:

    python3 tools/sheets_client.py export-all data/live_2026-09-01
    node tools/build_roster_offline.js data/enrollment_2026-09-01.csv --existing data/live_2026-09-01
    python3 tools/upload_roster.py --apply --replace

`upload_roster.py` refuses to run if the sheet holds a girl ID the local build
does not — that is the sign the `--existing` step was skipped.

Once the Apps Script from `appsscript/` is installed in the sheet, the GLOW
menu maintains those tabs going forward; re-running its rebuild after an
upload leaves Roster, ClubRegistry and Partners unchanged (ReviewQueue only
gains genuinely new questions; Audit gains one line per run), which is the
check that both paths agree.

## Optional: pushing the Apps Script from here

Pasting six files into the Apps Script editor works, but `clasp` (Google's
CLI) can push them directly:

    npm install -g @google/clasp
    clasp login                       # browser sign-in, once
    # in the sheet: Extensions → Apps Script → Project Settings → copy Script ID
    cd appsscript && clasp clone <SCRIPT_ID> && clasp push

`clasp login` uses your own Google account, so this needs you at the keyboard
the first time.
