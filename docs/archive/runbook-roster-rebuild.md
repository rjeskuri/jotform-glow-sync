# Roster rebuild and upload (offline path)

> **Historical procedure.** Moved from `docs/RUNBOOK.md` ("Roster rebuild and upload (offline
> path)") on 2026-10-09. It rebuilt the Roster tab from the raw enrollment responses outside the
> sheet before launch. **Not after launch**: since 2026-09-01 the Roster has moved on from the raw
> responses, and a rebuild reactivates removed girls and re-creates renamed or moved clubs (the
> RUNBOOK's stub says why; [BACKLOG](../BACKLOG.md) 39). Kept for the record.

Used when the Roster tab has to be rebuilt from the raw enrollment responses
outside the sheet:

```bash
python3 tools/sheets_client.py export-all data/live_<date>
node tools/build_roster_offline.js data/enrollment_<date>.csv --tz America/New_York --existing data/live_<date>
python3 tools/upload_roster.py                      # preview
python3 tools/upload_roster.py --apply --replace    # write; previous tabs saved under data/roster_build/previous/
```
