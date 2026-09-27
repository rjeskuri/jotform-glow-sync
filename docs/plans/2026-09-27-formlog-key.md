---
title: Time-zone-proof form-response keys and a safe "Process any missed form responses"
author: Claude (with Ryan)
status: accepted
created: 2026-09-27
intent: none — the 2026-09-13 incident found in the 2026-09-26/27 problem-report review
---

# Plan: time-zone-proof form-response keys + a safe "Process any missed form responses"

## Context
- FormLog records each processed Google-Form response under
  `which|timestamp.getTime()|partner|club` (`appsscript/FormHandlers.gs` `responseKey_` /
  `formLogHas_`). A Date read from a sheet cell is interpreted in the **spreadsheet's** time
  zone, which changed UTC → UTC-4 on 2026-09-02: every older key moved by exactly 4 h while the
  cell text stayed the same (FormLog rows 2 and 33: same milliseconds, +4 h). The comment on
  `responseKey_` claims the opposite.
- On 2026-09-13 at about 11:45, "Process any missed form responses" therefore re-ran Roster
  Form Responses rows 2-12. Row 2 (sent 08-31) **reactivated the 20 Radiant Girls rows**
  deactivated on 09-12 (Audit 82 → 84; Africa q410 back to 40; ReviewQueue 27). The run held
  the document lock throughout, died at the 6-minute limit in row 13 (no partial write: no
  12th Audit row), and never reached the 2 failed Feedback rows it was clicked for.
- Still armed: rows 13-16 carry old-offset keys. An offline simulation on the 2026-09-27
  export: the current code would re-run 6 responses today (Roster 13-16 + Feedback 2-3); the
  new key selects exactly Feedback 2-3, and nothing more after simulated later zone changes to
  −12, −5, 0, +5:30, +13 and +14 (a ±14 h window would have re-selected 62 rows at +13, so the
  window is 26 h).
- RUNBOOK, INSTALL.md and CLAUDE.md rule 11 make the click routine after scope-adding pushes.
  **Until this ships, nobody clicks that menu item.**

## Design
**1. Response identity** — pure helpers in `FormHandlers.gs` (no new `.gs` file; nothing in
Python reads FormLog, so no parity mirror; `FORM_LOG_COLS` unchanged).
- New key `which|w:<wall>|partner|club`, where `wall = Utilities.formatDate(ts,
  getSpreadsheetTimeZone(), 'yyyy-MM-dd HH:mm:ss.SSS')` — the cell's own wall-clock text,
  unchanged by zone changes and DST. Never the script time zone (test-pinned). Non-Date
  timestamps keep today's `tidy_` text key, matched exactly.
- **Done** = a FormLog row whose result does not start with `ERROR:` and whose key is either
  (a) a new key with the same `which|w:<wall>` (the stamp only, so a later partner/club cell
  edit cannot re-open it), or (b) a legacy millisecond key with the same `which` and
  partner|club tail whose milliseconds differ from today's `getTime()` by a whole multiple of
  15 minutes, at most 26 hours (every UTC offset is whole quarter-hours, spread −12…+14).
  Legacy keys parse as `which` | digits | rest (club names may contain `|`). No FormLog
  migration.
- The pure helpers never receive a Date: the caller passes `{wall, ms}` or `{text}`.
- The trigger (`onAnyFormSubmit` → `processResponseRow_`) and the menu share the same
  done-check. The trigger never holds anything back (a hold there would silently drop a real
  submission).

**2. The menu run (`processMissedResponses`)**
- Read FormLog and both response tabs once, **without the lock**. Each row that is not done is
  `retry` (only ERROR logged for it) or `new`, or one of two kinds that do **not** run on a
  plain YES:
  - `held` — FormLog already has a *successful* row for the same form and sheet row under a
    different key: something re-keyed it (the 09-13 class, whatever the cause). Listed, never
    run by the menu; releasing one is a deliberate FormLog edit (RUNBOOK).
  - `old` — a Club Roster Form row never logged and sent more than 7 days ago: runs only after
    a second, explicit YES whose text warns that it replays an old submission into today's
    roster. Feedback rows are never `old` (they only e-mail staff).
- Dialogs (`ui.alert` YES/NO), Feedback first, then the Club Roster Form: a count and one line
  per row — sheet row · sent <date> · new club / change / problem report · club (partner) ·
  `retry after ERROR: …` (e-mail-like text redacted); at most 15 lines plus "… and N more";
  held rows in an information section. Never girls' names or e-mail addresses. Nothing
  pending → "Nothing to process." No spreadsheet window (script editor, trigger) → refuse.
- Run: per row, `tryLock` (30 s; busy → stop, "run it again"), re-read FormLog, run only rows
  that were confirmed and are still pending, release, pause briefly so a waiting form-submit
  trigger gets in. Budget: stop starting rows 240 s after the **function** started (dialog
  time counts toward the 6-minute limit). No lock while a dialog is open.
- Audit (sources and counts only): `cancelled at the preview (would have run …)`,
  `started: …` (before the first row, so a killed run stays visible), `finished: …; N left`.
- Only services the project already uses (SpreadsheetApp including getUi, LockService,
  Utilities): no new OAuth scope, so no trigger outage (CLAUDE.md rule 11).

## Files that change
- `appsscript/FormHandlers.gs` — the above; the header comment (handlers are not safe to
  *replay* into a changed roster; the menu previews and holds) and the wrong `responseKey_`
  comment.
- `test/forms_logic_test.js` — a new section loading `Config.gs`, `Normalize.gs` and
  `FormHandlers.gs` (as `dispatch_test.js` loads its files); header widened.
  `test/load_gs.js` — comment only. The check counts stay (`ALL CHECKS PASSED` ×3,
  `gs: 10 files parse`).
- `docs/RUNBOOK.md` — a new "Missed form responses" section (what runs, held, old; the budget;
  never sort the response tabs — use a filter view; releasing a held row; roll back only to
  commit A); "Apps Script deploy" and "Automatic sync" step 3 point to it.
- `appsscript/INSTALL.md` and `CLAUDE.md` rule 11 — "…then run it and read its preview: it
  should list only what arrived since the push".
- `docs/DECISIONS.md` — one row. `docs/BACKLOG.md` — the follow-ups below.

## Order of work (the repo stays green after each)
1. Commit this plan. Stage only these files: the working tree also holds another session's
   uncommitted `tools/translations_additions.json` edit.
2. **Commit A — menu safety on the old key**: preview and confirm, holds, the old-row
   confirmation, per-row lock, budget, Audit rows, tests. With A alone, rows 13-16 show as
   `held`, so A would have stopped 09-13. A is the rollback target.
3. **Commit B — the new key**: stamp plus legacy match, shared by trigger and menu; tests;
   docs; DECISIONS; BACKLOG. `make check` green; independent review against REVIEW.md;
   privacy audit of the diff.
4. **Deploy — Ryan's go**: at a quiet moment, Ryan runs `npm run clasp:push` (or relaunches
   with `GLOW_LIVE_OK=1` exported and Claude runs it). Live proof below; then fill in Result.

## Out of scope — named follow-ups
- **Replay guard** (next plan): `planClub_` / `planModification_` never reactivate a girl whose
  `removed_date` is after the submission (optional `entry.submitted`; the rebuild and the
  offline builder unchanged; `loadRoster_` normalises Date cells through the sheet's zone; the
  mentor e-mail echoes typed names only). It also defuses the rebuild hazard (BACKLOG 39) if
  the rebuild passes `submitted`.
- **Radiant Girls repair** — independent of this code; it can happen now with Ryan's go. Staff
  submit Club Roster Form → Existing club → Haske Humanitarian Aid Initiative → Radiant Girls →
  REMOVE, listing the 20 names whose Roster `source` is `Roster Form Responses!2` (the audited
  handler stamps removed_date and dispatches the Africa sync; Sparkle Girls is untouched,
  because removal is per partner and club). Verify by counts: Audit `… 20 removed` with no
  "did not match"; SyncLog Africa `applied`; `form_status.py` CLEAN (q410 → 20 options);
  resolve ReviewQueue 27; check Salesforce attendance for those 20 since 09-13.
- Dropped: auto-resolving ReviewQueue rows on a successful retry; a FormLog `via` column;
  deferring the dropdown refresh during menu runs.

## Risks
- A bug in the legacy rule → rows show as `held` (the same sheet row is logged) or in the
  preview → answer NO and roll forward. Loud, never silent.
- A DST spring-forward gap after a future zone change → that one row shows as held.
- A rollback to code older than commit A → a mass replay with no preview → the RUNBOOK says
  roll back to A only.
- A dialog left open → no lock is held; the run dies at 6 minutes having done nothing.
- Response rows sorted or deleted → the affected rows show as held or old instead of running.

## Proof
Offline: `make check` — the healthy tail is unchanged (`ALL CHECKS PASSED` ×3, `py: …`, `OK`,
`gs: 10 files parse`, `secrets: clean`, `docs-links: ok`, `fixtures: up to date`,
`CHECK PASSED`). New tests, fictional 'Test Partner Org' / 'Sunrise Club' only:
- the key format; the same key read at offsets 0 and −240 (milliseconds differ by 14,400,000);
- tail parity with the old key (new club, change-form section, Feedback, blanks, invisible
  characters); ERROR never counts and a later success does; a partner/club edit does not
  re-open a row;
- legacy matches at 0, +4 h, −5 h, +5:30, +13 h, +14 h and −12 h; none at +4 h + 1 ms, at
  26 h 15 min, for another club or for the other form; text stamps match exactly only;
- **the 09-02 regression**: the old logic selects the stale rows; the new logic selects only
  the ERROR Feedback rows, also after later +13 h and −12 h switches; a brand-new submission
  is still selected;
- the planner: a successful row for the same sheet row under another key → `held`; a
  never-logged Roster row older than 7 days → `old`; Feedback never `old`; Feedback before
  Roster; the preview never contains a roster name or e-mail from the answers and caps at 15
  lines;
- a source guard: the spreadsheet's time zone, never the script's.

Service set unchanged: `git grep -ohE '\b(\w+App|\w+Service|Session|Utilities)\b' <base> --
'appsscript/*.gs' | sort -u` equals the same at HEAD.

Live (Ryan's go):
1. `python3 tools/sheets_client.py tabs` — note the FormLog and response-tab counts.
2. `npm run clasp:push` → `Pushed 11 files.`; the GLOW menu opens with no authorization prompt.
3. GLOW → Google Forms → Process any missed form responses → the Feedback preview lists
   exactly rows 2 and 3 (`retry after ERROR: STAFF_NOTIFY_EMAIL …`); the Club Roster Form has
   nothing to run, 0 held, 0 old. Answer NO → Audit `cancelled at the preview (would have run
   Feedback!2, Feedback!3)`. (A later YES sends the two stale reports to staff — Ryan's
   choice; or resolve ReviewQueue 21-22 by hand.)
4. The next real submission → a FormLog `ROSTER|w:…` row that is not ERROR; Executions shows
   onAnyFormSubmit Completed; `python3 tools/auto_sync.py` → every region in-sync.

Rollback: `git checkout <commit A> -- appsscript && npm run clasp:push`.

## Result
(filled in after the deploy)
