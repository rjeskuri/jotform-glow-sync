# credentials/

Two files live here, both gitignored and read-denied to Claude Code
(`.claude/settings.json`):

- `service-account.json` — the Google service-account key that lets the
  tooling read and write the master enrollment sheet. Created in the Cloud
  console; the sheet is shared with the robot's email as Editor.
- `config.json` — `{"spreadsheet_id": "..."}`; copy `config.example.json`.
  The `GLOW_SHEET_ID` environment variable overrides it.

Setup walkthrough: `docs/SHEETS-ACCESS.md`. In GitHub Actions the same two
values arrive as the secrets `GLOW_SA_JSON` and `GLOW_SHEET_ID`.
