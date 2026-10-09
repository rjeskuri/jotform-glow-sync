---
title: The group photo never reaches Salesforce; it is kept where staff can find it, under GLOW's control
author: GLOW's CEO (the decision of 2026-10-01) and Ryan (2026-10-06), captured by Claude
status: in-progress   # its plan is built and merged; the Drive set-up is Ryan's
created: 2026-10-06
---

# Intent: the group photo goes to Google Drive, not Salesforce

## Problem

Every attendance submission carries one required group photo of the girls present, faces
visible by design (DECISIONS 2026-09-12). Until 2026-10-01 the Jotform → Salesforce mapping
attached that photo to the attendance batch as a Salesforce File. On 2026-10-01 the CEO decided
that photos of the girls do not belong in Salesforce: the files there were deleted and the four
regional forms stopped sending the photo. Since then the photos exist only inside Jotform, behind
its login, named by submission id, which nobody can browse by club or date; the template still
sends the photo to Salesforce, so a test submission there would undo the decision; and the
repo's check (`tools/integration_status.py`) still expects the photo mapping and reports every
regional form as wrong. Separately, the photos are what fills Jotform's storage: 1.25 GiB of the
Silver plan's 10 GiB after five weeks, and Jotform disables the forms when the cap is reached.

## Proposed outcome

- No photo reaches Salesforce from any form, template included, and the repo's check says so.
- Each new photo is copied automatically into a Google Drive folder owned by a GLOW Workspace
  role account, one folder per form that collects attendance, one subfolder per submission
  named by club and date, so staff can find a club's photo of a given day without opening
  Jotform. Nothing else from the submission goes to Drive: no PDF, no names.
- The photo stays required on the forms.
- Jotform's storage is watched: the repo's status tools print how full it is, and the automatic
  sync raises ATTENTION before the forms can go "over quota".

## Affected users and systems

Mentors (nothing changes for them); staff (photos browsable in Drive); the CEO and Ryan (the
Drive folder's owner, sharing and retention); the staff address that receives the template's
notification e-mail (one test submission); four Jotform forms - the template, Africa, Asia and
Latin America - with an integration set in the builder, per form (the U.S form is being disabled
under the [clubs-off intent](2026-10-06-clubs-off-jotform.md) and gets none while it is);
Salesforce (one mapping row removed on the template; nothing else);
`tools/integration_status.py`, `tools/form_status.py`, `tools/auto_sync.py`; Google Drive (new).

## Constraints

- The Drive integration is a builder setting Jotform's API cannot write (proven 2026-09-30 for
  the same `integrations` property); Ryan sets it, the tools only read.
- Files only: the submission PDF carries every ticked girl's name and must never be sent; the
  subfolder name may use the club name and the date, never question 18 or a roster.
- The folders belong to a GLOW Workspace account, never a person's; the integration writes to
  that account's My Drive only (no Shared Drive).
- Photos of minors: sharing is the owner plus a short named list; a retention period is the
  CEO's decision and is recorded when taken.
- A test submission reaches Salesforce through the integration and is a real batch for a real
  club: the template's photo mapping goes first, and the test is arranged so it changes nothing
  there (see the plan).
- Jotform's "Require log-in to view uploaded files" stays on; "Auto Delete Submissions" stays
  off while the repo's back-fill and question-18 checks read the submissions.

## Open questions

- Retention: how long the photos are kept in Drive (CEO).
- Sharing: who besides the owner may open the folders (CEO / Ryan).
- Which role account owns the folders (the one that owns the enrollment sheet is suggested).
- Gold plan or a retention policy in Jotform, to be decided when the storage line passes ~50%.
