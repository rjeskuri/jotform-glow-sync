---
title: Catch "new club" submissions that duplicate a club we already have
author: Claude (workflow track, 2026-09-28)
status: proposed         # Ryan approves before merge
created: 2026-09-28
intent: docs/intent/2026-09-01-duplicate-club-guards.md
---

# Plan: the duplicate-club guard (BACKLOG 11b) and formula-safe Club Roster Form text (BACKLOG 44)

## Context
- `handleNewClub_` (`appsscript/FormHandlers.gs`) imports every "Enroll a NEW club" response
  whose (partner, club) key is new. On 2026-09-21/22 one partner re-enrolled six clubs it
  already had, with a school name added to each club name: the girls now sit in two clubs
  each, with two ids (review finding 9). On 2026-08-31 an exact re-enrollment carried another
  club's list, and every name on it was added (the Radiant Girls case, BACKLOG 42).
- Club Roster Form free text reaches `setValues` as typed: a leading `=` becomes a formula in
  the Roster, ClubRegistry, Partners, SF Pending or ReviewQueue (BACKLOG 44).
  `feedbackReviewItem_` already strips `/^[\s=+\-@]+/` for problem reports.
- FormLog knows two kinds of result: `ERROR: …` (not done, offered again by "Process any
  missed form responses") and anything else (done). A held response is a third kind: not
  done, and not to be run until staff decide.

## Design
**1. The guard (pure, `appsscript/RosterOps.gs`).** `newClubHoldReasons_(entry, rows,
partners)` returns the reasons to hold a new-club response (empty = import as today).
`entry = {partner, club, names, typedPartner}`; `rows` = the Roster (`loadRoster_().rows`);
`partners` = the Partners tab names (roster partners are added inside). Names compare
folded (`foldKey_`: `key_` + accents removed); club and partner names compare by their
words (`matchWords_`: folded, dots dropped so `G.L.O.W` = `GLOW`, split on anything not a
letter, mark or digit, letters split from digits).
- **Exact re-enrollment** (the key is on file): held when fewer than half of the names
  sent are on the club's roster (any status) AND fewer than half of its active girls are in
  the list (`reenroll`). A re-sent list with a few new girls, or a short list, is not held
  (the short list is reported as "Girls missing" as today). No other check runs.
- **New key**, any of:
  - `names`: at least half of the names sent, and at least 2, are active in ONE existing
    club — of any partner (the intent's rule; it also catches an organization retyped under
    another name). The reason names that club and partner and the counts, never a girl.
  - `club`: the club name is close to a club of the same partner (or of a partner the typed
    organization matched): equal distinctive words (`Hillside G.L.O.W club , Northfield` =
    `Hillside GLOW Club Northfield`), one's distinctive words all inside the other's
    (`BRIGHT GIRLS (TESTVILLE SEC SCH)` ⊇ `BRIGHT GIRLS`), or a Ratcliff/Obershelp ratio
    (Python `difflib`'s, as `tools/needs_attention.py` uses) ≥ 0.8 of the distinctive words
    (`BRAVEHAERT` / `BRAVEHEART`) — each also tried with what is in parentheses left out,
    so a typo plus an added school is caught. Generic words (`glow global club girls sec
    sch primaria …`) are not distinctive; names whose numbers, section letters or school
    levels differ (`Harbor Club 1` / `Harbor Club 2`, `Orbit (A)` / `Orbit (B)`,
    `… primaria` / `… secundaria`) are never close.
  - `partner`: "My organization is not in this list" was chosen and the typed name is not a
    partner on file but is close to one: equal words (accents, punctuation), acronym
    (`TARN` / `Test Aid Relief Network`, either way round), distinctive words contained, or
    ratio ≥ 0.8.
  Thresholds in one constant `DUP_GUARD` (`NAME_SHARE 0.5`, `MIN_SHARED 2`, `SIMILAR 0.8`,
  `REENROLL_SHARE 0.5`).

**2. Holding (`handleNewClub_`).** Before anything is written: reasons → `holdNewClub_`:
one ReviewQueue item (`issue: 'New club held as a possible duplicate'`, partner and club as
sent, detail `<source> (sent <yyyy-MM-dd HH:mm:ss>): nothing imported … <reasons> … what to
do`, tag `[#Roster Form Responses!N]`), then a short e-mail to the mentor ("received; we are
checking it against the clubs already enrolled; nothing to do") that echoes only the club
and partner they typed, then Audit (source and reason kinds only), FormLog result
`HELD: possible duplicate (<kinds>) — ReviewQueue [#Roster Form Responses!N]`. No Roster,
ClubRegistry, Partners or SF Pending write, no dropdown refresh, no Jotform sync. If the
ReviewQueue write fails the handler throws: `ERROR:` as today, retried from the menu, and the
mentor is not e-mailed twice. A response released by staff skips the guard.

**3. FormLog and the menu (`FormHandlers.gs`).** `RETRY_PREFIXES` stays `['ERROR:']` (offered
again automatically); `HOLD_PREFIX = 'HELD:'` is a second "not done" result that is never
offered automatically. `indexFormLog_` records held responses by their stamp
(`which|w:<wall>`, so a later edit of the club cell does not lose it) and drops the errors
logged before the hold. `holdDecisions_(reviewRows)` (pure) reads the ReviewQueue: for each
held item's tag, the last such row's state — `open` (resolved empty), `release` (resolved
starts with the word `release`, e.g. `release 2026-10-01 by Ryan: a new club`) or `closed`
(any other text) — and its sent time. `planMissedRun_(…, holds)`:
- a held response whose item is **open**, or that has no matching item (none, or its sent
  time differs: the tab was sorted) → `waiting`: listed with the result (as the re-keyed
  "held" rows are), never run;
- **release** (sent time matches) → `released`: its own YES/NO ("run as sent, against
  today's roster"), run with the guard skipped;
- **closed** → not listed (staff dealt with it).
`runConfirmed_` re-reads the decision before running a released row; the trigger path skips
a held response (a duplicate trigger never re-holds or re-mails). "Nothing to process." now
also lists the held rows. `HELD:` results read as "held for review", not "failed again".

**4. Formula-safe text (BACKLOG 44, `Normalize.gs`).** `sheetText_(v)` = `tidy_(v)` with the
leading run of `= + - @` and spaces stripped — the rule `feedbackReviewItem_` uses, which now
calls it. `parseFormRoster_(cell)` = `parseRoster_` + `sheetText_` on every name (and the
duplicates), re-deduplicated — the enrollment import keeps `parseRoster_` unchanged (Python
parity). Applied to typed Club Roster Form text only: the typed organization, club name,
roster names, mentor name / e-mail / country (SF Pending), ADD names. Dropdown answers
(partner, existing club) are ours and stay as chosen; REMOVE names are only matched.

**5. Words the staff see.** RUNBOOK "Working the ReviewQueue": the new issue's action (compare
the response row with the Roster; same club → add only its new girls on the existing club,
resolve; a new club after all → `release …` and run the menu item; never re-submit it);
"Missed form responses": held-for-review and released rows, `HELD:` next to `ERROR:` where
the text says "does not start with". `REVIEW_ISSUES` gains the issue first (a club waiting to
be enrolled is the most urgent). INSTALL.md forms table, ARCHITECTURE.md handler line,
DECISIONS.md one row, BACKLOG 11b / 40 / 44.

## Files that change
- `appsscript/RosterOps.gs` — `DUP_GUARD`, `newClubHoldReasons_` and its word helpers, `similarity_`.
- `appsscript/Normalize.gs` — `foldKey_`, `sheetText_`, `parseFormRoster_`.
- `appsscript/FormHandlers.gs` — hold in `handleNewClub_`, `holdNewClub_`, `heldClubReviewItem_`,
  `sendHoldNotice_`, `HOLD_PREFIX`/`isHeldResult_`, `indexFormLog_`, `holdDecisions_`,
  `planMissedRun_`, `processMissedResponses`, `runConfirmed_`, `processResponseRow_`,
  `runResponse_`, `REVIEW_ISSUES`, `feedbackReviewItem_` (shared helper), sheet-safe text in
  both Club Roster Form handlers.
- `appsscript/Roster.gs` — `loadPartnerNames_` (Partners tab, column A).
- `test/forms_logic_test.js` — the guard on fictional clubs, the hold/release handler run
  with Google services stubbed, the planner and menu with held rows, the strip rule.
- `docs/RUNBOOK.md`, `appsscript/INSTALL.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`,
  `docs/BACKLOG.md`, this plan.

## Order of work
1. Commit this plan.
2. `sheetText_` / `parseFormRoster_` and their use (BACKLOG 44), tests; `make check`; commit.
3. The pure guard in RosterOps.gs, tests; `make check`; commit.
4. Hold / release in the handler, FormLog and the menu, tests; `make check`; commit.
5. Docs; read-only evaluation on the live sheet's history (counts, rows, club and partner
   names only; the export stays under `data/`); `make check`; commit.

## Risks
- **False holds** delay a real new club by up to a week (the Monday e-mail). Mitigation: the
  thresholds are one constant; the evaluation below counts how many past new-club responses
  would have been held; releasing is one word in the ReviewQueue and one menu run.
- **A missed duplicate** is imported as today — no worse than now.
- **Release runs the wrong row** after a response tab is sorted: a release applies only when
  the item's sent time equals the row's; the held state is matched by the Timestamp, not
  the row number.
- **Live deploy** (`clasp push`, Ryan's go): no new Google service (a test pins the set), so
  no re-authorization; the handler change applies to the next submission. Rollback: push the
  previous `appsscript/` (not before `7a175c4`); a `HELD:` FormLog row then reads as done to
  the old code (nothing replays it) and its ReviewQueue item stays open for staff.
- **Privacy:** reasons, detail, Audit, FormLog and the mentor e-mail carry counts, club and
  partner names only; tests use fictional names and a canary.

## Proof
- `make check` green (the three JS suites, `gs: 10 files parse`, secrets clean).
- `git diff --stat main -- appsscript/` shows only the files above.
- Read-only evaluation: every past "Enroll a NEW club" response replayed through
  `newClubHoldReasons_` against the Roster without the rows it and later responses added —
  expected: the six school-suffixed re-enrollments of 09-21/22 and the 08-31 exact
  re-enrollment held; the count of other held responses reported as the false-hold rate.
- Live (Ryan's go, after merge): push; the next new-club response gets `HELD:` or a normal
  result in FormLog; a held one shows in the menu preview under "held for review".

## Result
- 2026-09-28, branch `wf/duplicate-club-guard` (not merged, not deployed):
  - BACKLOG 44: `sheetText_` / `parseFormRoster_`; both Club Roster Form handlers write
    only sheet-safe typed text (a handler run over a stubbed spreadsheet checks every cell).
  - The guard, the hold, the release, FormLog and the menu as designed; RUNBOOK, INSTALL,
    ARCHITECTURE, DECISIONS, BACKLOG. Every guard and hold rule has a test that fails
    when the rule is removed (checked by mutating each rule in turn).
- Read-only evaluation on the live sheet (Roster, Roster Form Responses, Partners and
  FormLog exported under `data/`; the script printed rows, dates, counts, club and partner
  names only, masking a club named like a girl): of the **39** "Enroll a NEW club"
  responses so far, **7 would have been held** — row 2 (08-31, Radiant Girls, reenroll:
  0 of 20 names on file) and rows 54, 55, 56, 57, 58, 62 (09-22, Reach All: SKY, DESTINEY,
  COURADGEOUS, BRIGHT, GOLDEN and SUPER GIRLS with a school added; 13-20 of 19-20 names
  already active in the club on file, and the club name close) — and **no other**.
  The first pass missed the club-name match for the COURADGEOUS row (typo plus school; the
  names rule held it anyway) and would have read letter sections, `Global Glow` school
  clubs and primaria/secundaria as close: fixed before commit `9896624`.
- As a proxy for future false holds: of 2107 pairs of clubs of one partner on file, 17 read
  as close — 13 known duplicates (Otra Cosa's combined vs split clubs, the six Reach All
  pairs, YWOU's Shinning/Shining Stars) and 4 uncertain (two `Cerrito de la Virgen` pairs,
  `CUTE QUEENS` / `QUEENS`, `Eagles` / `Eaglets Glow Club`); of 1176 partner pairs, none.

## Out of scope (follow-ups)
The form-side question "Is your club one of these?" (intent outcome 1: a live Google Form
change); the intent's "same club name under another partner" flag and "girl active in
another club of the same partner" flag; an automatic `SAME: <club>` resolution (staff enter
the new girls on the existing club instead); the Google Form's static confirmation text
(it still says "within the hour" for a held response; BACKLOG 43 track); the replay guard
(BACKLOG 41); cleaning up the duplicates already imported (review finding 9).
