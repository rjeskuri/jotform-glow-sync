---
title: Problem reports that are roster changes reach the ReviewQueue, and Ryan works it weekly
author: Claude (with Ryan)
status: accepted
created: 2026-09-28
intent: none — the 2026-09-26/27 problem-report review
---

# Plan: problem reports that are roster changes reach the ReviewQueue, and Ryan works it weekly


## Context
- The mentors' problem form ("GLOW – Something isn't working?") only e-mails staff
  (`appsscript/FormHandlers.gs` `handleFeedback_`); nothing tracks a report to resolution.
  7 of the 11 reports were roster changes (Feedback rows 4, 5, 6, 7, 10, 11/12 — 17 add/remove
  requests at three Rukmini Foundation clubs among them); none was applied.
- The ReviewQueue grew from 22 open (09-13) to 30 with nothing resolved 09-12 → 09-28: no
  owner, nothing announces it, and the failed-removal e-mail promises mentors "our team will
  check". Several detail texts still name forms that no longer exist.
- Ryan's decisions (2026-09-28): Ryan owns the ReviewQueue; only reports that look like roster
  changes become items; back-fill the already-emailed reports; the weekly e-mail keeps going to
  `STAFF_NOTIFY_EMAIL` (it reaches Ryan).
- A four-lens critique (live safety, privacy, RUNBOOK actions, the classifier on the 11 real
  reports — booleans only) shaped everything below.

## Design
**1. Roster-change reports → ReviewQueue** (`FormHandlers.gs`)
- `looksLikeRosterChange_(a)` (pure) returns the reason — `'form'` (the "Which form were you
  using?" answer contains `roster form`), `'text'`, or `''`. Text rule, after `foldText_`
  (lower case, accents folded, the report's own club name cut out so "<X> Girls Club" is not a
  roster word): a "new girls/members/students/names" phrase, or a roster word (girls, members,
  students, names, roster, list, to/from our club … + Spanish niñas, chicas, integrantes,
  participantes, nombres, lista) together with a change word (add/added/adding,
  remove/removed/removal, join…, left, chang…, reduc…, updated, up to date + Spanish agreg…,
  añadi…, quitar…, elimin…, se fue(ron), cambi…, actualizado/a). Singular `name`, `missing`,
  `moved`, `leave`, `transfer` deliberately out (they flag page/club problems). On the 11 real
  reports: true for 4, 7, 10, 11, 12 (form) and 5, 6 (text); false for 2, 3, 8, 9.
- `feedbackReviewItem_(a, source, sentDay, reason)` (pure, shared with the back-fill):
  `issue: 'Roster change sent as a problem report'`; partner / club = the typed FB_PARTNER /
  FB_CLUB, tidied, capped at 80 chars, leading `= + - @` stripped (no formula injection);
  detail = `<source> (sent <day>; <reason>): enter it on the Club Roster Form → "Add or remove
  girls in a club that is already enrolled", removals spelled exactly as on the Roster — or ask
  the partner to. Then mark resolved.`; `dedupeKey: source`. Never the report text or e-mail.
- `handleFeedback_(a, source, responseKey)`: the STAFF_NOTIFY_EMAIL check still throws first;
  then **queue before the e-mail** through `tryReview_` (review_ skips an item already open under
  the same tag, so a retry after a failed send adds nothing; the e-mail is the step that must
  not repeat). The staff e-mail gains "Staff note: looks like a roster change; on the ReviewQueue
  as Feedback!N." or "…could NOT be added (see Audit) — add it by hand."; the FormLog result says
  `emailed staff; roster change queued` / `… NOT queued (see Audit)` (never `ERROR:`). The sent
  day comes from the key (`WALL_KEY` → `yyyy-MM-dd`), '' for legacy keys.
- `tryReview_(items, source)`: on failure one Audit row with counts, issue names and the source
  only. Also used for the existing unwrapped `review_` in `runResponse_`'s catch.

**2. The Monday e-mail lists the open ReviewQueue** (`sendSfPendingDigest`; the name stays —
the installed trigger calls it by name; a test pins that)
- Reader normalises `raised` (Date cell → `yyyy-MM-dd` in the sheet zone; text → first 10
  chars) and builds `known` partners/clubs from ClubRegistry B:C.
- `reviewDigestLines_(rows, today, known)` (pure): ReviewQueue section **first**: per issue
  (listed in `REVIEW_ISSUES`, the 8 strings; anything else under "Other (added by hand)") the
  open count, new in the last 7 days, oldest age; then up to 10 lines `row N · raised <day> ·
  <partner> / <club> · Feedback!7`. Partner/club printed only when on file in ClubRegistry, else
  "(partner not on file)" / "(not given)". A tag is printed only when it is a response-row
  reference (`Feedback!N`, `Roster Form Responses!N`, the enrollment tab) — other tags ARE
  girls' names. Never the detail column. Resolved rows left out. `DIGEST = {MAX_PER_ISSUE: 10,
  NEW_DAYS: 7}`.
- The e-mail = ReviewQueue section + the SF Pending section as today; no early returns; nothing
  to report → no e-mail, no Audit; STAFF_NOTIFY_EMAIL unset → Audit with both counts. Subject
  lists non-zero parts: `GLOW weekly: 14 open ReviewQueue item(s) · 31 club(s) pending in
  Salesforce` (the old subject changes — a mail filter on it would need updating). Audit: counts only.

**3. Words the staff see**
- `docs/RUNBOOK.md` new "Working the ReviewQueue" (after "Missed form responses"): owner Ryan;
  the Monday e-mail; close with `resolved <date> by <name>: <what was done, by reference>`
  (never a girl's name); never delete/sort rows or type after the `[#…]` tag; entering a change
  on a partner's behalf; the Monday e-mail shows no names by design — work in the sheet, never
  copy a detail cell into e-mail/chat/commits; "Closest names on file" are other girls — never
  send them to a mentor; one action line for each of the 8 issue types (from the critique).
  Also: never sort or delete Feedback rows.
- Stale detail texts: RosterOps.gs "Same name listed twice" (add the other girl on the Club
  Roster Form with a mark, not "submit again"), "Girls missing" ("Roster Modification form" →
  the Club Roster Form's add/remove branch), "Removal did not match" (source first);
  FormHandlers.gs "club not on file" ("New Club Enrollment form" → "Enroll a NEW club", look for
  a rename/move first). Text only: the identity (issue|partner|club|tag) is unchanged.
- `appsscript/INSTALL.md` step 4 (fixture name, points to the RUNBOOK, never the rebuild), the
  forms table line and the `STAFF_NOTIFY_EMAIL` bullet; the missed-responses dialog says roster
  changes also go to the ReviewQueue.
- `docs/DECISIONS.md` one row; `docs/BACKLOG.md`: the Club Roster Form's free text reaches
  `setValues` unstripped; Google Forms wording follow-ups.

**4. Back-fill** — `tools/backfill_feedback_review.py`, dry run by default, `--apply` writes
(Ryan's go). Reads Feedback / FormLog / ReviewQueue in memory; runs the `.gs`
`looksLikeRosterChange_` + `feedbackReviewItem_` through Node (`test/load_gs.js`, JSON on
stdin); refuses a row whose latest FormLog result is not a success; skips any item whose
identity matches an open ReviewQueue row (and duplicates in the batch); raised = the report's
day; detail ends `(back-filled <date>) [#Feedback!N]` (tag last). Prints only `Feedback!N  <day>
roster-change form|text|no  partner/club on-file yes|no`, totals, `would append K`; appends
RAW, re-reads by tag, one Audit row `backfillFeedbackReview: added K item(s): Feedback!4, …`.
Expected: **+7** (Feedback 4, 5, 6, 7, 10, 11, 12; 11 and 12 are one request sent twice).

## Files that change
`appsscript/FormHandlers.gs`, `appsscript/RosterOps.gs` (detail texts), `test/forms_logic_test.js`,
`tools/backfill_feedback_review.py` (new), `docs/RUNBOOK.md`, `appsscript/INSTALL.md`,
`docs/DECISIONS.md`, `docs/BACKLOG.md`, `docs/ARCHITECTURE.md` (tool table), this plan.

## Tests (fictional only: canary girl 'Hope Fennwhistle', partner 'Fixture Partner Alpha',
club 'Bright Stars', `mentor@example.org`)
- Classifier: the 22 fictional cases from the critique (form / text / '' each), incl. Spanish,
  the club-name cut-out, the accepted misses documented in a comment.
- `feedbackReviewItem_`: no report text, no e-mail, stripped `=`, cap, tag = source.
- `handleFeedback_` in the vm with the real `review_` on a fake ReviewQueue: queued before the
  send; a failed send then a retry → one e-mail, one row; a ReviewQueue failure → still e-mailed,
  "add it by hand", result NOT queued; STAFF unset → throws, nothing written; Audit never holds
  the canary, the typed club or example.org.
- `reviewDigestLines_` / `sendSfPendingDigest`: only-ReviewQueue open; Date and text `raised`
  both age; a row reference shown, name tags and typed off-file partner/club never; 10 per issue
  then "… and N more"; resolved rows out; "Other (added by hand)"; nothing → no e-mail; STAFF
  unset → Audit with both counts.
- Guards: every `issue: '…'` in `appsscript/*.gs` is in `REVIEW_ISSUES` and has a RUNBOOK
  action; the trigger name `sendSfPendingDigest` is both installed and defined; the Google
  services set is exactly today's (no new OAuth scope).

## Order of work
1. Commit the plan. 2. Code, tests, docs; `make check`; independent review (REVIEW.md);
commit; push. 3. Deploy — Ryan's go (this session can run the push with the live flag).
4. Back-fill — dry run shown, then Ryan's go. 5. Result in the plan.

## Proof
`make check` green (counts unchanged: tests stay in the three suites). `git diff --stat
10f9050 -- appsscript/` shows only this change. Classifier on the 11 real reports: true 4, 5,
6, 7, 10, 11, 12; false 2, 3, 8, 9 (booleans only). Live: the push (no authorization prompt);
back-fill dry run lists +7, apply, re-read; the next roster-change report gets its line and the
e-mail's staff note; Audit `sendSfPendingDigest: … open ReviewQueue …` on Monday 2026-10-05.

## Out of scope (follow-ups)
Google Forms wording (Ryan, Forms editor: problem form points roster changes to the Club
Roster Form; restore its reply-email question; the Club Roster Form's "Something not
working?" line); partner messages; the Partner-box acronym fix; replay guard; duplicate-club
guard.

## Result
(filled in after the deploy and the back-fill)
