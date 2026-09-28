---
title: The Google Forms send roster changes to the Club Roster Form, and the problem form asks for a reply address again
author: Claude (for Ryan's approval)
status: proposed         # Ryan approves before merge
created: 2026-09-28
intent: none — BACKLOG 43, from the 2026-09-26/27 problem-report review
---

# Plan: Google Forms wording, as a one-time menu migration (BACKLOG 43)

## Context
- 7 of the 11 problem reports were roster changes sent to the problem form
  ("GLOW – Something isn't working?"); nothing on that form points to the Club Roster Form.
- The live problem form lost its reply-email question (removed by hand in the Forms editor):
  all 11 reports came without one, so nobody could be answered. The Feedback tab still has the
  old column, `Your email, if you would like a reply (optional)` (column 8, the last; read
  2026-09-28, titles only). Neither response tab has a duplicate column title today.
- The Club Roster Form's description ends `Something not working? <problem-form link>` and says
  nothing about where roster changes belong.
- The new-club "Club name" help text predates the Club picker ("The name mentors will type on the
  attendance form."); one club was enrolled under the first line of its own roster. The REMOVE
  help text says "Spell names as they were enrolled", but a mentor cannot see how a name was
  enrolled; the attendance form shows exactly that spelling.
- Editing `Forms.gs` alone changes nothing live: `createGlowForms` reuses existing forms and
  `syncFormChoices` only touches the dropdowns and sections. The precedent is
  `migrateCountryToRegion` (a one-time, idempotent menu item). The handlers read answers by
  question TITLE, so no title may change.
- Saved public pages of both forms (2026-09-26) confirm that the live texts this plan replaces
  are still the generated ones.

## Design
**1. Wanted wording, in one place** (`appsscript/Forms.gs`, `WORDING` + two builders).
- Problem form description = today's text, then a new paragraph:
  `To add a girl or remove one who left, please use the Club Roster Form instead and choose
  "Add or remove girls in a club that is already enrolled" — the attendance form updates within
  the hour: <Club Roster Form link>`. The branch name is built from `Q.ACTION_MOD`, so it can
  never drift from the real choice.
- Club Roster Form description: the same first paragraph; the last line becomes
  `Something not working? To add or remove girls, choose "Add or remove girls in a club that is
  already enrolled" below; for anything else, tell us here: <problem-form link>`.
- "Club name" (new club) help: `The club's own name — not the mentor's name or a girl's name.
  Mentors will choose it from a list on the attendance form, spelled exactly as you type it
  here.`
- REMOVE help: `Leave empty if nobody is leaving. Copy each name exactly as it is spelled on the
  club's attendance form (capitals do not matter). A name spelled differently is not removed —
  our team will check it with you.`
- The problem form's reply-email question: title exactly `Q.FB_EMAIL`, short answer, optional,
  e-mail validation, placed after "Phone or computer, and which browser? (optional)".
- No question title changes anywhere.

**2. The planner (pure, tested offline).** `planFormWording_(state)` takes what the forms say now
(`readFormWording_`: both descriptions and links, the problem form's item titles and types, the
two help texts) and returns `{changes, skipped}`:
- a text equal to the wanted one → nothing;
- a text the generator wrote before (the 2026-08 wording, blank, or the wanted text with a
  different link; links compared loosely) → a change `from → to`;
- anything else was edited by hand → **skipped**, listed with the suggested text for the Forms
  editor (refuse rather than overwrite someone's wording);
- reply-email question: present under its exact title → nothing (a non-short-answer item under
  that title → skipped with a note); absent, but another question whose title mentions e-mail
  exists → skipped ("rename it to exactly …"), never a second e-mail question; absent → add.
- a missing "Club name" or REMOVE question → skipped ("not our form?").

**3. The menu item** `GLOW → Google Forms → Update the forms' wording (one-time; previews first)`
→ `migrateFormWording()`:
1. Needs the sheet UI (refuses from the script editor, like "Process any missed form responses").
   Either form missing → says to run "Create the Google Forms"; nothing written. A form whose id
   is saved but does not open (another Google account, a Forms outage) → "Could not open …;
   do NOT run Create" (Create would replace the live forms); "Create the Google Forms" itself
   refuses in that case (review 2026-09-28, F2).
2. Reads both forms and plans. Nothing to change → "Nothing to change" (+ the skipped list); no
   Audit row. Otherwise one YES/NO dialog lists every change (`now:` / `new:`, the added
   question and "the Feedback tab gets a new column with this title"), then what is left as is,
   then "No question title or answer is changed; the response tabs get no edit except the new
   reply column noted above." ("Question titles, answers and the response tabs are not changed."
   when no question is added).
3. NO → one Audit row `cancelled at the preview (would have changed …)`.
4. YES → takes the document lock (never held while a dialog is open), re-reads and re-plans; if
   anything differs from the preview → nothing written, Audit + "run it again". Also refuses if
   the preview was open more than 4 minutes (Apps Script stops a run at 6).
5. Applies each change (`setDescription`, `setHelpText`, one `addTextItem` + `moveItem`), re-reads
   and re-plans: the Audit row says `changed: <labels>; re-read: up to date` (or `STILL
   DIFFERENT: …`). Labels only — the texts are fixed wording, never form answers.
6. A failure part-way → Audit `stopped after <done> …: <error>`; every change is idempotent, so
   running it again makes only the ones still missing. A failure inside the reply question's add
   (after `addTextItem`) is recorded as `… reply-email question PARTLY added (check …)`, and the
   dialog says what to check in the Forms editor; a rerun lists an untitled short-answer question,
   or the reply question away from the device question, as left as is (never a second question).
   The handler sets Reply-To only for a typed value that looks like an address (review
   2026-09-28, F1).
- A second run: "Nothing to change". It never deletes an item, never changes a title, never
  touches responses, FormLog or the form's destination; the response tabs get nothing but the
  added question's new column, which Google makes.

**4. Fresh builds match.** `createFeedbackForm_` / `createRosterForm_` use the same `WORDING`, the
same builders and the same `addReplyEmailItem_`; `createGlowForms` sets the problem form's
description once the Club Roster Form exists (each form's description links to the other). A
test builds both forms against a stubbed FormApp and checks that the planner then finds nothing
to change.

**5. The handler reads the filled-in column** (`FormHandlers.gs` `responseFromValues_`). Re-adding
the question most likely gives the Feedback tab a second column with the same title (Google keeps
a deleted question's column and, as far as we know, does not reuse it; to be seen after the
run). Today the last same-titled column wins; if Google placed the new
column left of the old one, every reply address would read blank. Change: a blank cell never
replaces an answer already read under the same title. No title repeats in either tab today, so
no FormLog key changes (the key never uses the e-mail anyway). Leave both columns in place.

**Not changed:** the problem form's other hand edits (visible title "Global Catalyst – …", "What
were you trying to do?" required, its help text, the form list without "The enrollment
spreadsheet"), the Region help text (live differs from `REGION_HELP`), the "Existing club" page
text (BACKLOG 40), the attendance forms' "report a problem" link (finding 6). Listed for Ryan.

## Files that change
- `appsscript/Forms.gs` — `WORDING`, `feedbackDescription_`, `rosterDescription_`,
  `addReplyEmailItem_`, `readFormWording_`, `planFormWording_`, `formWordingPreviewText_`,
  `applyFormWording_`, `migrateFormWording`; the two generators and `createGlowForms` use them.
- `appsscript/Menu.gs` — the menu item.
- `appsscript/FormHandlers.gs` — `responseFromValues_` (item 5).
- `test/forms_logic_test.js` — planner cases; preview text; the menu run with FormApp, the UI, the
  lock and Audit stubbed (fake forms expose only the methods allowed, so a delete or destination
  call fails the test); fresh build → nothing to change; duplicate-column read.
- `docs/RUNBOOK.md` (new section "Google Forms wording"), `appsscript/INSTALL.md`,
  `docs/DECISIONS.md` (one row), `docs/BACKLOG.md` (43), this plan.

## Order of work
1. Commit this plan.
2. Forms.gs wording + planner + tests → `make check`.
3. Menu item + apply + the stubbed menu-run tests → `make check`.
4. `responseFromValues_` + its test → `make check`.
5. Docs → `make check`; commit per step on `wf/forms-wording`. No push, no deploy.

## Risks
- **Live write to both Google Forms** (Ryan's go): preview first, lock, re-read before and after,
  Audit. Rollback: the Forms editor — the 2026-08 texts are `WORDING.FEEDBACK_INTRO`,
  `rosterDescription2026_08_()`, `WORDING.CLUB_HELP_2026_08` and `WORDING.REMOVE_HELP_2026_08`;
  a wrongly added question is deleted in the editor (its column stays in the tab, harmless).
  Never roll `appsscript/` back before 986a325 while the Feedback tab has two reply columns (the
  two-column read goes with it).
- **Deploy**: `clasp push` of Forms.gs, Menu.gs and FormHandlers.gs. No new Google service
  (FormApp, LockService, SpreadsheetApp are already used; the services guard test pins the set),
  so no re-authorization and no trigger outage.
- **A second Feedback column** with the reply-email title: handled by item 5; tell staff not to
  delete either column.
- **Mentors mid-submission** while the form changes: text edits and an appended optional
  question do not invalidate an open form. Run at a quiet moment anyway.
- **Merge overlap** with parallel tracks editing `FormHandlers.gs`: item 5 touches only
  `responseFromValues_`.

## Proof
- `make check`: tail `ALL CHECKS PASSED` ×3, `gs: 10 files parse`, `CHECK PASSED`.
- Live (Ryan's go, a quiet moment): `make gs` → `npm run clasp:push` (no authorization prompt
  expected) → reload the sheet → GLOW → Google Forms → "Update the forms' wording" → the preview
  lists 5 changes (problem form description, reply-email question, Club Roster Form description,
  "Club name" help, REMOVE help) and nothing left as is → YES → "Done — 5 changes; re-read: up to
  date" + Audit `migrateFormWording: changed: …`. Run it again → "Nothing to change".
- Open both fill-in links (do NOT submit a test response): the descriptions, the reply-email box
  (a non-address is refused), the two help texts. Passive: the next problem report with an
  address → the staff e-mail has `Reply to:` filled and a reply-to header.

## Built (2026-09-28, branch `wf/forms-wording`; not merged, not deployed)
- Committed in three steps instead of four: the handler read (item 5) with its tests, then the
  wording + menu migration with its tests, then the docs. Each step was green on its own.
- `test/forms_logic_test.js` gained 41 checks: the wording (the 2026-08 texts pinned as the saved
  pages show them), the planner, the preview, the menu run against fake forms that have no
  delete / destination / response methods (YES, NO, a second run, forms edited during the
  preview, the lock busy, a failure part-way then the rerun, a hand-moved device question, a
  hand-edited help text, a missing form, no UI), a fresh `createGlowForms` build (nothing to
  change), and the two-column read. The two-column checks fail without the handler change.
- `make check` (also with the real export: 328 clubs / 6210 girls, no enrolled name in code,
  docs or tests):

      ALL CHECKS PASSED
      py: 30 files parse, 18 scripts answer --help
      Ran 60 tests … OK
      gs: 10 files parse
      secrets: clean (119 files scanned)
      docs-links: ok (36 relative links resolve, 0 absolute paths)
      fixtures: up to date
      CHECK PASSED

## Result
(to be filled in after the deploy)
