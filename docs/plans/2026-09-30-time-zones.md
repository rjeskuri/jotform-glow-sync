---
title: Time zones fixed - the work log (billing) and the sheet-facing timestamps
author: Claude (with Ryan)
status: done (local commits; push awaits Ryan's go)
created: 2026-09-30
intent: none - Ryan's request of 2026-09-29 ("Make sure timezone issues are fixed")
---

# Plan: time zones fixed - the work log (billing) and the sheet-facing timestamps

## Context
Ryan: "Make sure timezone issues are fixed." The Mac has moved between zones. Git commit offsets
show:

| Dates | Zone |
|---|---|
| until about 08-25 | +01:00 |
| 08-26 to 08-27 | +00:00 |
| 08-28 to 09-02 | +02:00 |
| 09-03 to 09-14 | +03:00 |
| 09-20 to 09-28 | +08:00 |
| since 09-29 | +09:00 (JST) |

`/etc/localtime` itself changed to Asia/Tokyo on 09-29 at 12:37Z. A read-only sweep ran `make check`
under five TZ values, all green: nothing in the suite would notice. It found:

- **Billing.** `tools/worklog.py` puts every past transcript event into the Mac's CURRENT zone
  (`events()`, `.astimezone()`), and `update` rewrites every auto row of the last 30 days. So a zone
  change rewrites billed history.
  - The committed September back-fill (63b50a6, run at +08:00) is itself wrong for Sep 1–14:
    20.25 h committed against **20.50 h** correct for Sep 1–28. This was independently recomputed twice.
  - 09-01: 2.25 → 2.75.
  - 09-02: 3.75 → 3.50.
  - 09-04 is missing: 0.75 h, and the roadmap work belongs there.
  - 09-05 should not exist: 0.75 h.
  - 09-12 is missing: 1.50 h, the picker-rollout evening.
  - 09-13: 2.25 → 0.75.
  - 09-03 and 09-14 have the right hours but the wrong block times.
- **Other worklog bugs:**
  - `git_subjects()` uses `--date=format-local`, so commits land on the wrong day.
  - `blocks` times carry no zone.
  - A session crossing midnight is split, and the part after midnight bills only if Ryan wrote after midnight.
- **Audit trail (low).** Tools write timestamps into the live sheet in the process's zone, but the
  sheet is America/New_York (verified).
  - `tools/auto_sync.py` SyncLog `when` is written in the Actions `TZ=America/Chicago`, one hour behind the sheet. A Mac run with `--synclog` writes JST.
  - The workflow's comment claims the times match the sheet.
  - `tools/rename_club.py` writes the Audit `when` and the Partners-note date in Mac time.
  - `tools/build_roster_offline.js` writes Roster, ClubRegistry, ReviewQueue and Audit dates in Mac time.
- **Apps Script is sound.** It writes every timestamp in the sheet's zone, and the 09-27 key fix holds.
  - The one exception is the Monday e-mail trigger's **hour**: `atHour(8)` follows the script project's zone (`appsscript.json`: America/Chicago), so the e-mail fires 09:00–10:00 in the sheet's zone (America/New_York). No timestamp is affected; docs/RUNBOOK.md says when it arrives.
  - Possible follow-up, not done here: `installTriggers` could add `.inTimezone(ss.getSpreadsheetTimeZone())` so the hour follows the sheet. That is an `appsscript/` change with its own approval and `clasp push`, and the trigger must be reinstalled.
- **Retention.** Transcripts are deleted about 30 days after a file's last activity. The earliest September deletion is 2026-10-25; Sep 1–13 lasts until at least 10-28.

**Outcome:**
- A day's hours depend only on when the work happened and where the Mac was at the time.
- September is corrected before invoicing.
- Every timestamp the tools write into the sheet is in the sheet's zone.

**Ryan's decisions (2026-09-30):**
- A session that runs past midnight belongs to the **day it started**.
- August stays out of the log, as decided on 09-28.

## A. The work log (`tools/worklog.py`)

**Zone timeline, committed: `worklog/timezones.csv`** (`since,zone,evidence`)
- `since` is a UTC instant written as `+00:00`; `fromisoformat` in 3.10 rejects `Z`.
- `zone` is `+HH:MM` or an IANA name (stdlib `zoneinfo`).
- A row means "from this instant the Mac was on this zone". `zone_at(t)` returns the latest row with `since ≤ t`.
- `.gitignore` gains `!worklog/timezones.csv`; today only `worklog.csv` is excepted from `*.csv`.
- Seed rows, each switch in a gap with no activity:

| since | zone | evidence |
|---|---|---|
| 2026-08-01T00:00:00+00:00 | +01:00 | BST reading 08-24 |
| 2026-08-26T00:00:00+00:00 | +00:00 | commits 08-26..27 |
| 2026-08-28T00:00:00+00:00 | +02:00 | commits 08-28..09-02 |
| 2026-09-03T00:00:00+00:00 | +03:00 | commits 09-03..09-14 |
| 2026-09-17T00:00:00+00:00 | +08:00 | commits 09-20..09-28 |
| 2026-09-29T00:00:00+00:00 | Asia/Tokyo | /etc/localtime changed 09-29 12:37Z |

**Days and blocks**
- Events are clustered on one continuous timeline. More than `--gap-minutes` of silence ends a block,
  whatever the clock says.
- Each block goes to the local date of its **start**, in the zone in effect then. It counts only if
  it holds a message of Ryan's.
- Day hours = the sum of the day's blocks, rounded to the quarter hour, at least 0.25 (as now).
- `blocks` text renders each block in its start's zone. On a day with mixed zones each block carries
  its offset. The new last column `zone` records the zone(s) of that day's blocks. It is output only:
  nothing reads it back, and `export` still uses date, hours and description.

**`update`: guards, refuse rather than guess**
1. **The Mac's zone must be in the timeline.**
   - It reads the system zone from `/etc/localtime`, not the process `TZ`, falling back to the process zone only if unreadable.
   - It compares UTC offsets at "now", never zone names.
   - On a mismatch it refuses and suggests `zone --since <instant> --zone <IANA name>`, using the `/etc/localtime` change time when that falls in an activity-free gap, otherwise the gap's midpoint rounded to the hour.
   - It names `TZ` in the message when it is set.
2. **Commit offsets must agree with the timeline.** Every commit in the window by the local git user must have a recorded offset equal to `zone_at(commit instant)`. Otherwise it refuses, naming the commit. This catches a missed A→B→A trip. Commits before the first row are skipped.
3. **Only relevant events need a zone.** An event in the window that predates the timeline is refused; older events are ignored.
4. **Window edge.** All days are computed. If the day before `--since` would change against the log, it refuses: "re-run with an earlier --since".
5. **Stale rows.** An auto row whose day now has no block is dropped only when all of these hold:
   - the day is on or after `max(since, today − 29)`;
   - `--transcripts` was not given;
   - `--drop-stale` was passed.

   Otherwise it refuses, listing the rows. Older stale rows are kept and reported, so expiry can never delete billed rows.
   The one-off September run passes `--drop-stale`.
6. Commit subjects come from `git log --format=%at%x09%s` and are dated with the timeline.
7. The default window is the last **14** days (was 30), safely inside the transcripts' 30-day life. The "30 days" wording in the docstring and help changes with it.

**`zone` (new subcommand)**
- With no arguments it prints the timeline, the Mac's zone and the commit-offset evidence since the last row. It needs no transcripts, so the `--help` check stays green.
- `zone --since <yyyy-mm-dd | ISO instant> --zone <+HH:MM | IANA>` appends a row. A bare date means midnight in the new zone. It refuses:
  - a `since` within `--gap-minutes` of any transcript event;
  - a `since` with a later commit in the old offset;
  - a `since` in the future, or out of order.
- It prints the `update --since …` command now needed.

**Tests (`test/python_test.py` `WorkLog`)**
- The guard gets the system zone and "now" passed in, and every `TZ`/`tzset` change is restored in `finally`. CI runs under UTC.
- New tests:
  - `zone_at` at the exact switch, before the first row, and on an IANA zone across DST;
  - a block across a +08→+09 switch;
  - a block across midnight goes to its start day;
  - identical rows under two process `TZ` values;
  - the Mac-zone refusal;
  - the commit-offset refusal;
  - `since` inside a block refused;
  - the window-edge refusal;
  - a stale row inside the window dropped only with `--drop-stale`;
  - a stale row older than today − 29 is kept;
  - with `--transcripts`, nothing is dropped;
  - subjects dated by the timeline;
  - `zone` argument parsing.
- Existing tests that change:
  - the round trip, with the `zone` column;
  - `events`/`merge` signatures (the "expired day never dropped" assertion stays);
  - the midnight test, where 23:50→00:20 is now one 0.50 h block on its start day.

**Re-compute September (local file only)**
1. The baseline is `HEAD`'s worklog.csv plus today's uncommitted 09-29 row.
2. Seed the timeline, then run `update --since 2026-09-01 --drop-stale`.
3. Show Ryan a before/after table, and re-check the ~20.50 h figure under the start-day rule.
4. Rewrite the descriptions for days whose work changed: 09-01, 09-02, 09-04 (it takes 09-05's roadmap work), 09-12, 09-13, and today. The rewrite follows the 2026-09-28 method:
   - one agent per day, given only that day's digest: Ryan's messages, Claude's summaries and commit subjects;
   - 1–3 client-facing sentences, with no names;
   - one reviewer checks all of them for accuracy, privacy and tone.

   Ryan reviews the result before invoicing.

## B. Timestamps written into the sheet use the sheet's zone
- **`tools/sheets_client.py`:** `time_zone(svc)` reads `properties.timeZone`. `tools/backfill_feedback_review.py` switches to it; it already does this inline.
  - Review fix: `time_zone` and `_sheets_meta` share `_get(svc, fields)`, so a 403 or 404 exits with what to fix (share the sheet with the robot; check the ID). `SystemExit` is not an `Exception`, so `auto_sync`'s `with_retry` fails fast instead of retrying for about 35 s.
  - Review fix: a zone that is not an IANA name (the Sheets API can return a custom `GMT-07:00`) exits via `named_zone`, asking for a named zone in File → Settings.
- **`tools/auto_sync.py`:**
  - `Run` keeps the start instant as aware UTC.
  - `append_synclog(svc)` reads the zone inside the existing retry/try (only with `--synclog`, so dry runs stay credential-free) and rewrites each row's `when` with a pure `sheet_when(instant, zone)`.
  - The first log line and the ATTENTION.md header gain `%z`.
  - `.github/workflows/auto-sync.yml` sets `TZ: America/New_York`, the sheet's zone, so the runner's local files agree, and gets a corrected comment.
- **`tools/rename_club.py`:** reads the zone once, right after the dry-run return and before backups and writes, for the Audit `when` and the Partners-note date. The backup file stamp stays local. `RenameClub.run_main` in the tests patches `sc.time_zone`.
  - Review fix: it converts with `sc.named_zone`, so an unknown zone refuses. A test pins that a failed or unknown zone read stops a move before the backup folder, the batch and the Audit row.
- **`tools/build_roster_offline.js`:**
  - Requires `--tz <IANA>`. A missing or trailing flag, or a bad zone (`RangeError`), exits with a message pointing to the sheet's File → Settings (America/New_York since 09-02).
  - Formats with `Intl.DateTimeFormat(...).formatToParts` and `hourCycle: 'h23'`. `TODAY` also feeds `planClub_`, so the Roster dates follow `--tz`.
  - Its usage lines, docs/RUNBOOK.md and docs/SHEETS-ACCESS.md (two commands) gain `--tz America/New_York`.
  - Test (forms_logic_test.js): run it as a child process with `--out <tmpdir>` on `test/fixtures/enrollment_sample.csv`, never the default `data/roster_build/`. It must refuse without `--tz`, and its dates must follow `--tz` under any process `TZ`. Review fix: the Audit time of day must also fall between the run's start and end on the `--tz` wall clock.

**Not changed (cosmetic, reported):**
- backup and log file-name stamps (`backup_forms.py`, `switcher_flags.py`, `upload_roster.py`)
- the output-file date in `needs_attention.py` and `derive_partner_regions.py`
- the `live_gate.sh` log time
- `form_status.py`'s unlabelled `last_submission` (US Eastern), which is the other session's file; I'll pass the note to them.

## Files that change
- `tools/worklog.py`, `worklog/timezones.csv` (new), `worklog/worklog.csv`, `.gitignore`
- `test/python_test.py`, `test/forms_logic_test.js`
- `tools/sheets_client.py`, `tools/auto_sync.py`, `tools/rename_club.py`, `tools/backfill_feedback_review.py`, `tools/build_roster_offline.js`
- `.github/workflows/auto-sync.yml`
- `CLAUDE.md`: the worklog Commands and Conventions lines (`zone`, the refusal, `--drop-stale`)
- `docs/RUNBOOK.md`, `docs/SHEETS-ACCESS.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` (one row)
- `docs/plans/2026-09-30-time-zones.md`

None of these is in the other session's set: `sync_attendance_form.py`, `form_status.py`,
`add_feedback_link.py`, `glow/links.py`.

## Order of work
1. Commit the plan doc.
2. Part A code and tests, then `make check`.
3. Seed the timeline; recompute September; show the table; rewrite descriptions (workflow); Ryan reviews.
4. Part B code, tests and docs, then `make check`.
5. Adversarial review of the whole diff against REVIEW.md, plus a privacy-auditor pass over the CSV descriptions; fix what they find.
6. Local commits. No push without Ryan's go.

## Verification
- `make check` is green, also under `TZ=Asia/Tokyo` and `TZ=America/Los_Angeles`.
- `TZ=UTC`, `TZ=America/Los_Angeles` and plain runs of `worklog.py update --since 2026-09-01` give identical rows. The guard reads `/etc/localtime`, so no test hook is needed.
- Each corrected block lines up with that day's commit times, and `export --month 2026-09` totals equal the sum of the rows.
- The same `update` run twice changes nothing.

## Live-system note
- Nothing here writes to Jotform, the sheet or Salesforce during the work.
- The `auto_sync.py` and workflow changes reach the live runner only when `main` is pushed. They change only how SyncLog `when` and local log names are written. They get pushed only with Ryan's go.

## As built (2026-09-30) - deviations from the plan above
- The Asia/Tokyo row starts at 2026-09-29T12:37Z (when `/etc/localtime` changed), not 00:00Z: the
  same activity-free gap, and the stronger evidence.
- The commit check covers every committer except "GitHub" (merges made on github.com), not only
  the local git user: the August evidence was committed under another name. `--ignore-commit`
  is the escape for a commit not made on this Mac.
- After the review (31 agents, 20 confirmed findings):
  - the recount moved into `update_rows()` so its refusals are tested;
  - the default window reaches back to the last logged day when the log is behind, and every
    unrecomputed day from the log's start (last 29 days) is checked, not only the day before `--since`;
  - rows older than 29 days, or read from another folder, are held unless `--rewrite-old`;
  - the switch suggestion is bounded by the last old-clock and first new-clock commits (`zone`
    refuses either side), uses the idle stretch before the session holding the clock change,
    and never falls back to "now";
  - commit subjects go to the day of the block they were made in;
  - `append_zone` never merges rows;
  - `read_zones` refuses a row with extra columns;
  - `tools/upload_roster.py`'s rebuild hint passes `--tz`.
- The September recount under the final rules equals the one above (20.50 h for Sep 1-28);
  the descriptions of 09-01, 09-02, 09-04, 09-12 and 09-13 were redrafted per day and reviewed.

## From the RUNBOOK (moved 2026-10-09)

What `docs/RUNBOOK.md` carried for this plan until its 2026-10-09 restructure (the procedure as run, or its history), word for word (links re-pointed to this folder); the RUNBOOK keeps a stub that links here.

### "Automatic sync": the SyncLog's cut-over

The cut-over:
rows written before commit d9b4f6b reached the runner on GitHub carry the
runner's America/Chicago time (one hour behind the sheet and the Audit tab;
before 2026-09-02, when the sheet was on UTC, five hours), and a Mac
`--synclog` run before then wrote the Mac's clock; the row's `run_url` gives
the true time.
