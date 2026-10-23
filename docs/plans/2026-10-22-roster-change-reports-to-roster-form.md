---
title: Roster changes sent as problem reports point their sender to the Club Roster Form, and girls "not on the form" count as one
author: Claude (ticket #110)
status: proposed         # ticket #110; the deploy waits for Ryan's go at a quiet moment
created: 2026-10-22
intent: none - ticket #110 (a 2026-10 report of girls who attended but were "not on the form" was missed)
---

# Plan: roster-change reports point their sender to the Club Roster Form

Ticket #110. A problem report of 2026-10 said girls who attended were "not on the form": a
roster change with no change word, so `looksLikeRosterChange_` (`appsscript/FormHandlers.gs`)
missed it and nothing reached the ReviewQueue. And a report that is recognised still leaves the
sender waiting on staff. Two changes, both in the deployed Apps Script, nothing on the forms or
in the sheet's data:

- The classifier also takes girls "not on the form / list / roster", "not in the portal",
  "missing from the form / list" (Spanish "no aparece(n) / no está(n) en la lista, el
  formulario, el portal") when they are said of people — a people word, or a girl's name (two
  capitalised words), in the clause before the phrase, or in the clause before that when it is
  only a pronoun ("two girls came but they are not on the form"); a thing word in that clause
  ("Golden Wings Girls Club", "the number of girls") and any subject with neither sign ("today's
  attendance", "our mentor", "my name") stay bug reports (the PR #117 review: the first cut took
  anything not on its thing list as people). The accepted misses and false alarms are in the
  comment above `RC_ABSENT` and in `docs/DECISIONS.md` (2026-10-23).
- `handleFeedback_` e-mails the sender of a roster-change report, when the reply box holds an
  address, a short note naming the Club Roster Form with its published link
  (`existingForm_(PROP.ROSTER_FORM).getPublishedUrl()`; FormApp is already a pinned service, so
  no new OAuth scope). It is sent after the staff e-mail (the step that throws and is retried),
  so a retry never sends it twice; it never echoes the report, the typed club or partner; a
  failure is one Audit row `sendRosterFormPointer_: could not e-mail the mentor about Feedback!N`
  (addresses masked) and the handler still returns `emailed staff; roster change queued`. No
  roster form saved, or one that does not open: the note goes without a link. The note also
  says a misspelled name is fixed there by removing the wrong spelling and adding the right one
  (Ryan, 2026-10-22). The ReviewQueue item, the staff e-mail and its Audit row are as before;
  the FormLog result gains `; sender pointed to the Club Roster Form` or `; sender NOT e-mailed
  (see Audit)`. A report that chose the Club Roster Form gets the note only when its "what
  happened" itself asks for the change ("please remove X from the roster"): a mentor whose
  Club Roster Form broke ("the partner dropdown is empty") is not told to use it (the PR #117
  review); her report is queued and e-mailed to staff as before.

Staff still own the item (RUNBOOK "Working the ReviewQueue"): enter the change or confirm the
partner sent it, then resolve.

## Rollout (live; each step on Ryan's go)
1. After the land: `/deploy-appsscript` from `main` at a quiet moment (`.claude/skills/deploy-appsscript/SKILL.md`:
   `make gs` and `make check` first, then `npm run clasp:push`, Node 18; no new Google service,
   so no re-authorization and no trigger outage).
2. One problem report on a test club, sent from the problem form with a reply address Ryan
   owns, worded as a roster change ("Two girls are not on the form"), the test club typed as
   the club. Read back: the Audit row `feedbackForm: emailed … ; ReviewQueue [#Feedback!N]`,
   the FormLog result ending `sender pointed to the Club Roster Form`, the ReviewQueue row
   (tagged `[#Feedback!N]`, no report text), the staff e-mail with its "Staff note" line, and
   the reply address's e-mail naming the Club Roster Form with the live form's link.
3. Resolve that ReviewQueue row (`resolved <date> by Ryan: test of #110`); never delete it.

## Rollback
The previous deployed commit pushed again (`git checkout <previous appsscript-deployed-* tag> --
appsscript && npm run clasp:push`, then `git checkout HEAD -- appsscript`; the skill's Rollback,
RUNBOOK "Rolling back `appsscript/`"): never below the floors `7a175c4` / `986a325`, and held
new clubs dealt with first. Nothing else to undo: no sheet column, no form change, no Script
Property. An e-mail already sent to a mentor is not recalled; the ReviewQueue rows stay.

## Risks
- A false alarm now also e-mails the sender (a thing the classifier does not list, "the date is
  not on the form"): the note says "if your report was about something else, there is nothing
  more to do"; staff resolve the item "not a roster change" as before.
- The mentor and staff both enter the change: the Club Roster Form reports the second as
  "already on the roster" / "already removed" — no double rows.
- A report naming girls is never echoed: the e-mail carries the form's name and link only, and
  Audit masks addresses (`previewError_`).
- The Forms service slow or down at submit time: `rosterFormUrl_` catches it and the note goes
  without the link; the handler never fails for it.

## Proof
Offline: `scripts/harness_tests.sh test/forms_logic_test.js` (the "which reports are roster
changes" table, 178 wordings with the PR #117 review's 68, and the block "a roster-change report
points its sender to the Club Roster Form (#110)") green; `make gs` (services unchanged); `scripts/verify.sh` ends
`CHECK PASSED`. Live: step 2's read-back.

## Result
Pending: the deploy waits for Ryan's go.
