#!/usr/bin/env python3
"""
Read and write the enrollment spreadsheet from this machine.

Auth is a Google service account: a robot user that the spreadsheet is shared
with, so nothing has to be made public. Its key file lives at
credentials/service-account.json and the spreadsheet's ID in
credentials/config.json (both gitignored) - see tools/README-sheets.md for
the one-time setup.

Usage (also importable):
    python3 tools/sheets_client.py whoami                   # service account email
    python3 tools/sheets_client.py tabs                     # list tabs + used rows
    python3 tools/sheets_client.py export "Enrollment Responses" out.csv
    python3 tools/sheets_client.py export-all DIR           # every tab -> DIR/<tab>.csv
    python3 tools/sheets_client.py import "Enrollment Responses" in.csv   # one-time, never overwrites
"""
import csv
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRED_DIR = os.path.join(REPO, "credentials")
KEY_FILE = os.environ.get("GLOW_SA_KEY", os.path.join(CRED_DIR, "service-account.json"))
CONFIG_FILE = os.path.join(CRED_DIR, "config.json")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def spreadsheet_id():
    sid = os.environ.get("GLOW_SHEET_ID")
    if not sid and os.path.exists(CONFIG_FILE):
        sid = json.load(open(CONFIG_FILE)).get("spreadsheet_id")
    if not sid:
        sys.exit("No spreadsheet ID: set GLOW_SHEET_ID or put "
                 '{"spreadsheet_id": "..."} in credentials/config.json '
                 "(the long token in the sheet's URL after /d/).")
    return sid


def service():
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        sys.exit("pip3 install google-api-python-client google-auth")
    if not os.path.exists(KEY_FILE):
        sys.exit(f"No service-account key at {KEY_FILE}\n"
                 "See tools/README-sheets.md for the one-time setup.")
    creds = service_account.Credentials.from_service_account_file(
        KEY_FILE, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def sa_email():
    if not os.path.exists(KEY_FILE):
        sys.exit(f"No service-account key at {KEY_FILE}")
    return json.load(open(KEY_FILE)).get("client_email", "?")


def _sheets_meta(svc):
    from googleapiclient.errors import HttpError
    try:
        return svc.spreadsheets().get(
            spreadsheetId=spreadsheet_id(),
            fields="sheets(properties(title,sheetId,sheetType,gridProperties))"
        ).execute()["sheets"]
    except HttpError as err:
        if err.resp.status == 403:
            sys.exit("Google says the robot may not open this spreadsheet (403).\n"
                     f"Share the sheet with {sa_email()} as Editor, and check that\n"
                     f"credentials/config.json holds the right ID ({spreadsheet_id()}).\n"
                     "If the message mentions the API not being enabled, enable\n"
                     "'Google Sheets API' in the Cloud project.")
        if err.resp.status == 404:
            sys.exit(f"No spreadsheet with ID {spreadsheet_id()} (404) - check "
                     "credentials/config.json against the sheet's URL.")
        raise


def list_tabs(svc):
    """[(title, used_rows_including_header, grid_rows, grid_cols)] for grid tabs."""
    out = []
    for s in _sheets_meta(svc):
        p = s["properties"]
        if p.get("sheetType", "GRID") != "GRID":
            continue
        grid = p.get("gridProperties", {})
        used = len(read_tab(svc, p["title"]))
        out.append((p["title"], used, grid.get("rowCount", 0), grid.get("columnCount", 0)))
    return out


def read_tab(svc, title):
    """All values of a tab as a list of rows (strings; ragged rows padded)."""
    resp = svc.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id(), range=_range(title),
        valueRenderOption="FORMATTED_VALUE").execute()
    rows = resp.get("values", [])
    width = max((len(r) for r in rows), default=0)
    return [r + [""] * (width - len(r)) for r in rows]


def _range(title, cell=None):
    quoted = "'" + title.replace("'", "''") + "'"
    return quoted + ("!" + cell if cell else "")


def ensure_tab(svc, title, rows_needed=0, cols_needed=0):
    """Create the tab if missing and make sure its grid is big enough.
    Returns the sheetId."""
    sheet_id, grid = None, {}
    for s in _sheets_meta(svc):
        if s["properties"]["title"] == title:
            sheet_id = s["properties"]["sheetId"]
            grid = s["properties"].get("gridProperties", {})
    requests = []
    if sheet_id is None:
        resp = svc.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id(),
            body={"requests": [{"addSheet": {"properties": {"title": title}}}]}
        ).execute()
        props = resp["replies"][0]["addSheet"]["properties"]
        sheet_id, grid = props["sheetId"], props.get("gridProperties", {})
    rows = max(grid.get("rowCount", 0), rows_needed + 1, 100)
    cols = max(grid.get("columnCount", 0), cols_needed, 10)
    if rows != grid.get("rowCount") or cols != grid.get("columnCount"):
        requests.append({"updateSheetProperties": {
            "properties": {"sheetId": sheet_id,
                           "gridProperties": {"rowCount": rows, "columnCount": cols}},
            "fields": "gridProperties(rowCount,columnCount)"}})
    if requests:
        svc.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id(),
                                       body={"requests": requests}).execute()
    return sheet_id


def write_tab(svc, title, rows):
    """Replace a tab's contents with `rows` (list of lists). Values are written
    RAW so names like '1. Ana' or '=x' are never reinterpreted by Sheets.
    Dates are plain 'yyyy-MM-dd' text on purpose (see Roster.gs)."""
    width = max((len(r) for r in rows), default=0)
    sheet_id = ensure_tab(svc, title, rows_needed=len(rows), cols_needed=width)
    svc.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id(), range=_range(title), body={}).execute()
    if rows:
        resp = svc.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id(), range=_range(title, "A1"),
            valueInputOption="RAW", body={"values": rows}).execute()
        if resp.get("updatedRows") != len(rows):
            sys.exit(f"{title}: wrote {resp.get('updatedRows')} rows, expected {len(rows)}")
    _format_header(svc, sheet_id)
    return sheet_id


def append_rows(svc, title, rows):
    """Append rows below the tab's existing data (creates the tab if needed)."""
    if not rows:
        return
    width = max(len(r) for r in rows)
    existing = len(read_tab(svc, title)) if _has_tab(svc, title) else 0
    ensure_tab(svc, title, rows_needed=existing + len(rows), cols_needed=width)
    resp = svc.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id(), range=_range(title, "A1"),
        valueInputOption="RAW", insertDataOption="INSERT_ROWS",
        body={"values": rows}).execute()
    updated = resp.get("updates", {}).get("updatedRows")
    if updated != len(rows):
        sys.exit(f"{title}: appended {updated} rows, expected {len(rows)}")


def _has_tab(svc, title):
    return any(s["properties"]["title"] == title for s in _sheets_meta(svc))


def _format_header(svc, sheet_id):
    """Bold + freeze the header row, like ensureTab_ in Roster.gs does."""
    svc.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id(), body={"requests": [
        {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                        "fields": "userEnteredFormat.textFormat.bold"}},
        {"updateSheetProperties": {"properties": {"sheetId": sheet_id,
                                                  "gridProperties": {"frozenRowCount": 1}},
                                   "fields": "gridProperties.frozenRowCount"}},
    ]}).execute()


def export_tab(svc, title, out):
    rows = read_tab(svc, title)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    return len(rows)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == "whoami":
        print(sa_email())
        return
    svc = service()
    if cmd == "tabs":
        for title, used, r, c in list_tabs(svc):
            print(f"  {title:<24} {max(0, used - 1):>6} data rows   (grid {r}x{c})")
    elif cmd == "export":
        n = export_tab(svc, sys.argv[2], sys.argv[3])
        print(f"{n} rows -> {sys.argv[3]}")
    elif cmd == "export-all":
        out_dir = sys.argv[2]
        for title, used, _, _ in list_tabs(svc):
            n = export_tab(svc, title, os.path.join(out_dir, title + ".csv"))
            print(f"  {title:<24} {n:>6} rows")
    elif cmd == "import":
        # one-time: put a CSV into a tab, refusing to overwrite existing data
        title, src = sys.argv[2], sys.argv[3]
        with open(src, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        if _has_tab(svc, title) and len(read_tab(svc, title)) > 1:
            sys.exit(f"Tab '{title}' already holds data - not overwriting.")
        write_tab(svc, title, rows)
        print(f"{len(rows) - 1} data rows -> '{title}'")
    else:
        sys.exit(f"unknown command {cmd!r}")


if __name__ == "__main__":
    main()
