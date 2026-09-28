---
title: Replay guard — an older form response never puts back girls removed after it was sent
author: Claude (with Ryan)
status: proposed         # proposed → accepted (Ryan) → in-progress → done
created: 2026-09-28
intent: none — BACKLOG 41, the follow-up named in docs/plans/2026-09-27-formlog-key.md
---

# Plan: replay guard (BACKLOG 41)

## Context
- 2026-09-13: "Process any missed form responses" re-ran `Roster Form Responses!2` (a
  new-club response sent 08-31) and **reactivated the 20 Radiant Girls rows** removed on 09-12.
  The FormLog-key fix (`7a175c4`, `10f9050`, deployed 09-28) stops the menu from re-selecting
  processed rows and asks a second YES before running a Club Roster Form response more than
  7 days old. It does not change what a handler does once it runs.
- A handler applies a response to **today's** Roster: `planClub_` and `planModification_`
  (`appsscript/RosterOps.gs`) reactivate every inactive girl the response names, whatever her
  `removed_date`. A retried `ERROR:` row, an old row confirmed at the second YES, or a held row
  released by hand can still put back girls removed after the response was sent.
- `loadRoster_` (`appsscript/Roster.gs`) returns raw cells. `setRowsStatus_` writes
  `removed_date` as `yyyy-MM-dd` text through `setValue`, which Sheets may store as a Date
  cell; a Date read back is an instant whose day depends on the time zone it is formatted in.
  (Which of the two the live Roster holds was not checked for this plan — the code handles both.)
- The response's sent day is already known: its FormLog key carries the Timestamp cell's
  wall-clock text in the spreadsheet's zone (`which|w:<wall>|…`, `sentDayOfKey_`).

## Design
**1. The guard** — pure, in `RosterOps.gs`, so the offline builder and the tests run the same code.
- `entry.submitted` — optional, `yyyy-MM-dd`, the day the response was sent. Missing or `''`
  → today's behaviour exactly (the rebuild and `tools/build_roster_offline.js` pass nothing and
  are unchanged). Anything else that is not `yyyy-MM-dd` → throws (refuse rather than guess; the
  handlers only ever pass a day or `''`).
- `staysRemoved_(row, sentDay, today)`: an inactive girl the response names stays removed when
  her `removed_date` day is **after** `sentDay`. Same day or earlier → reactivated as today
  (`removed_date` has no time of day). `removed_date` blank or not a readable day → stays
  removed only when the response is past-dated (`sentDay < today`); a response sent today
  behaves as today.
- `planClub_` and `planModification_` (ADD) put such girls in `plan.keptRemoved` —
  `[{name: <as typed>, row: <Roster row>}]` — instead of `reactivate`. Every plan carries
  `keptRemoved` (the uniform-shape rule). In `planModification_` a held-back ADD does not count
  as "added", so the same name under REMOVE is reported "already removed", never "kept on the
  roster".
- One ReviewQueue item **per response** when anyone is held back:
  `issue: 'Removed girls not put back by an older response'`, partner, club, detail
  `<source> (sent <day>): N girl(s) it lists were removed after it was sent (or on a day the
  Roster does not record), so they stay removed — Roster rows a, b, c. If one has really
  rejoined, ADD her on the Club Roster Form ("Add or remove girls in a club that is already
  enrolled"); otherwise mark resolved.` — Roster **row numbers, never names**;
  `dedupeKey: source`, so a retry adds no second row and the Monday e-mail can show the
  response-row tag (`responseRowTag_` already allows `Roster Form Responses!N`).

**2. `loadRoster_`** — an `added_date` / `removed_date` Date cell becomes `yyyy-MM-dd` in the
**spreadsheet's** zone (never the script's); text cells are untouched. The other readers
(dropdown refresh, Roster summary) never read the date columns.

**3. The handlers** (`FormHandlers.gs`)
- `runResponse_` passes `sentDayOfKey_(responseKey)` to `handleNewClub_` and
  `handleRosterChange_`, which put it in `entry.submitted`. A Timestamp that is not a date
  gives `''` → today's behaviour (the menu already treats such a row as "old": second YES).
- The trigger path is unchanged in practice: a fresh response's sent day is today. The one
  difference: a response sent before midnight and processed after it, naming a girl whose
  `removed_date` is blank, keeps her removed (and the ReviewQueue says so).
- Summaries (Audit, FormLog result) add `, N kept removed` — a count.
- `sendChangeConfirmation_` (roster changes; the new-club branch sends no e-mail) gains a
  section listing the names **as the mentor typed them**: "Not added back — they were removed
  from the roster after you sent this form. If one of them has rejoined the club, send the form
  again to add her:" (a fresh ADD is sent today, so it reactivates).
- `REVIEW_ISSUES` gains the new issue (9) after "Removal did not match anyone"; the header
  comment and the old-row dialog say what an old response can still do (its removals and new
  names still apply; girls removed since stay removed).

**Only services the files already use** (Utilities, SpreadsheetApp): no new OAuth scope, so no
trigger outage (CLAUDE.md rule 11); the existing guard test pins the service set.

## Files that change
- `appsscript/RosterOps.gs` — `entry.submitted`, `staysRemoved_`, `dayOf_` / `submittedDay_`
  helpers, `keptRemoved`, `keptRemovedIssue_`; header comment (plan shape).
- `appsscript/Roster.gs` — `loadRoster_` normalises the two date columns.
- `appsscript/FormHandlers.gs` — `runResponse_`, `handleNewClub_`, `handleRosterChange_`,
  `sendChangeConfirmation_`, `REVIEW_ISSUES`, header comment, the old-row dialog text.
- `test/forms_logic_test.js` — pure tests of the guard; `loadRoster_` and both handlers run
  with Google services stubbed (fictional names only); the issue-count guard 8 → 9.
- `docs/RUNBOOK.md` — "Working the ReviewQueue": a row for the new issue; "Missed form
  responses" step 2: what an old response still does.
- `docs/DECISIONS.md` — one row. `docs/BACKLOG.md` — 41 built (on this branch); 39 still open.
- No Python change: nothing in Python plans roster changes; `ROSTER_COLS` unchanged.

## Order of work (the repo stays green after each)
1. Commit this plan (`status: proposed`).
2. Commit — the guard in `RosterOps.gs` + pure tests, with the new issue in `REVIEW_ISSUES`
   and its RUNBOOK row (the guard test requires both as soon as the code can raise it). No
   caller passes `submitted` yet, so nothing live would change.
3. Commit — `loadRoster_` normalisation; the handlers pass `submitted`; summaries; the mentor
   e-mail; the old-row dialog; stubbed handler tests; RUNBOOK "Missed form responses".
4. Commit — DECISIONS, BACKLOG; `make check` green; a review against REVIEW.md and a
   privacy pass over the diff.
5. **Ryan**: review, set `status: accepted`, merge. **Deploy — Ryan's go** (below).

## Out of scope — named follow-ups
- **The rebuild** (`rebuildRosterFromResponses`, `build_roster_offline.js`) passes no
  `submitted`, so BACKLOG 39 stays open: it still must not run after launch. Passing the
  Enrollment Responses Timestamp would defuse its reactivation half; it would not stop it
  re-creating renamed or moved clubs.
- **An old REMOVE replayed** after the girl was re-added deactivates her again: a reactivation
  clears `removed_date` and records no date (BACKLOG 34, an `updated` column, would allow it).
- **Same-day replays** still reactivate (`removed_date` is a day).
- The menu's second YES for old rows stays: the guard covers reactivation only.

## Risks
- **A girl really rejoined** and an old response lists her → she stays removed; the
  ReviewQueue item and (roster changes) the mentor e-mail say so; a fresh ADD puts her back.
  Loud, never silent.
- **Blank or unreadable `removed_date`** on an inactive row (typed by hand) with a past-dated
  response → she stays removed and the queue says so. Conservative by design.
- **Zone change** (as on 2026-09-02): `removed_date` was stamped in the zone of its day and
  the sent day is read in today's zone — a response within a few hours of midnight of the
  removal day can land on the other side of the comparison. Only same-day-boundary cases.
- **A thrown guard error** would log the response as `ERROR:` (retryable); the handlers only
  pass `''` or a day, and a test pins that `''` is accepted.
- **Deploy**: no new Google service → no re-authorization. Rollback: `git checkout e552f55 --
  appsscript && npm run clasp:push` (never before `7a175c4`).

## Proof
Offline: `make check` — the healthy tail unchanged (`ALL CHECKS PASSED` ×3, `py: …`, `OK`,
`gs: 10 files parse`, `secrets: clean`, `docs-links: ok`, `fixtures: up to date`,
`CHECK PASSED`). New tests, fictional names only:
- no `submitted` (missing or `''`) → exactly today's plan, whatever `removed_date` says;
- removed after the sent day → kept removed, one issue per response with the source tag and
  Roster row numbers, no names; same day and earlier → reactivated; unreadable removal day →
  kept on a past-dated response, reactivated on a same-day one; a malformed `submitted` throws;
- ADD held back + the same name under REMOVE → "already removed", not "kept";
- the Radiant Girls regression: a new-club response sent 08-31, run on 09-13 against 20 girls
  removed 09-12 → 0 reactivated, 20 kept, 1 issue;
- `loadRoster_`: Date cells → the day in the spreadsheet's zone (a UTC instant on the other
  side of midnight proves the zone), text untouched;
- both handlers with Google services stubbed: the Roster cells after the run, the ReviewQueue
  row, the FormLog result / Audit counts, the mentor e-mail's typed names; a fresh submission
  (sent today) reactivates as before;
- guards: 9 issues each with a RUNBOOK action; the service set unchanged; the rebuild and the
  offline builder pass no `submitted`.

Live (Ryan's go, at a quiet moment):
1. `npm run clasp:push` → `Pushed 11 files.`; the GLOW menu opens with no authorization prompt.
2. GLOW → Google Forms → Process any missed form responses → the preview is what it was before
   the push (answer NO if anything is listed you did not expect).
3. The next real Club Roster Form submission: FormLog result not `ERROR:`, Audit
   `rosterChangeForm` / `newClubForm` as before (`0 kept removed` is not printed);
   `python3 tools/auto_sync.py` → every region in-sync.

Rollback: `git checkout e552f55 -- appsscript && npm run clasp:push`.
