# credentials/

Two files live here, both gitignored, read-denied to Claude Code
(`.claude/settings.json`) and closed to its edits (`.claude/hooks/protected_paths.sh`,
in every checkout; this README and `config.example.json` excepted):

- `service-account.json` — the Google service-account key that lets the
  tooling read and write the master enrollment sheet. Created in the Cloud
  console; the sheet is shared with the robot's email as Editor. The
  `GLOW_SA_KEY` environment variable points the tools at another path.
- `config.json` — `{"spreadsheet_id": "..."}`; copy `config.example.json`.
  The `GLOW_SHEET_ID` environment variable overrides it.

Setup walkthrough: `docs/SHEETS-ACCESS.md`. In GitHub Actions the same two
values arrive as the secrets `GLOW_SA_JSON` and `GLOW_SHEET_ID`.
