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

   You should see the sheet's tabs with their data row counts.

Why Editor and not Viewer: the tools create and fill the Roster, Partners,
ClubRegistry, ReviewQueue and Audit tabs (and, once, the *Enrollment
Responses* import). The spreadsheet is the new **master enrollment** sheet —
the original response sheet stayed with its owner, so its data came across
as a CSV export.

## What the tools do with it

| Command | Effect |
|---|---|
| `python3 tools/sheets_client.py export "Enrollment Responses" data/enrollment_<date>.csv` | Export the imported responses tab |
| `python3 tools/sheets_client.py import "Enrollment Responses" data/enrollment_<date>.csv` | One-time import of the original form's responses |
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

## Pushing the Apps Script with clasp (instead of pasting)

`clasp` is Google's command-line tool for Apps Script. Once set up, the
whole `appsscript/` folder goes into the sheet's script project with one
command, and so does every later change. This machine runs Node 18, so the
repo pins clasp 2.4.2 (clasp 3 needs Node 20); `npm install` fetches it.

One-time, with you at the keyboard (it signs in as *your* Google account —
the forms and triggers it creates belong to you):

1. In a terminal in this folder: `npm install` then `npx clasp login`.
   A browser tab opens; pick the account that owns the master enrollment
   sheet; allow. The token lands in `~/.clasprc.json` (never in the repo).
2. Turn on the Apps Script API for your account (clasp needs it):
   <https://script.google.com/home/usersettings> → **Google Apps Script API → On**.
3. Get the script's ID: open the sheet → **Extensions → Apps Script** → ⚙
   **Project Settings** → copy **Script ID**. Put it in
   `appsscript/.clasp.json` (gitignored):

       {"scriptId": "<SCRIPT_ID>", "rootDir": "."}

4. Push: `npm run clasp:push` (that is `clasp push -f` inside `appsscript/`;
   `-f` skips the "overwrite?" prompt). Reload the sheet — the **GLOW** menu
   appears; continue with the First run steps in `appsscript/INSTALL.md`.

`appsscript/appsscript.json` is the project manifest clasp requires
(V8 runtime, time zone for the Monday digest). Edit the `.gs` files in the
repo, run tests, push — never edit in the online editor, the next push would
overwrite it.
