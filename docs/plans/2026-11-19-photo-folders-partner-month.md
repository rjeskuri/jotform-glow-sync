---
title: Photo folders filed Region / Partner / Month on the Shared Drive, the week number in the folder name
author: Claude (ticket #225, with Ryan's option A of 2026-11-18)
status: in-progress      # live mover updated 2026-11-23; #236, the naming and #237 to go
created: 2026-11-19
intent: GLOW staff via Ryan, 2026-11-18 - confirm the photo dates are session dates; the week number in the photo naming; club folders grouped by partner and month within each region
---

# Plan: photo folders by partner and month, the week in the name

<!-- Kept beside ticket #225. When the live steps are done: the Result, the status and `done:`,
     then `make docs-index`. -->

GLOW staff asked three things about the Jotform photos on the Shared Drive (relayed by Ryan,
2026-11-18): are the dates in the names session dates or upload dates; can the week number from
Jotform be in the name; can the club folders be grouped by partner and month within each region,
to find photos faster during verifications. Ryan chose **option A** (2026-11-18): the partner goes
into each form's Drive folder naming, the mover files Region / Partner / Month from that name,
and the existing folders are re-filed once, after that work.

## The staff answer on dates

**The date in a photo folder's name is the session date, not the upload date.** Since
2026-10-30 every active form's Google Drive integration names the submission subfolder
`{Club Name} {Date}` (RUNBOOK "Photos", step 2), and `{Date}` is question 17 (`glow/sync.py`
`DATE`), the attendance date the mentor picks on the form - the same field Salesforce stores as
`Attendance_Date__c`. The photo mover only moves folders and never renames them. Folders made
before 2026-10-30 carry the club name only, no date.

Evidence:

- The repo's record: the integration setting (RUNBOOK "Photos", step 2: `{Club Name} {Date}`,
  `{Date}` question 17) and the mover's code, which never renames.
- Ryan's by-eye check, 2026-11-23 (ticket #225 comment): two settled photo folders on the Shared
  Drive. In each, the date in the folder's name was a couple of days before the folder's Drive
  "Modified" date. That fits a name carrying the session date, with the photos uploaded
  afterwards; a name carrying the upload date would match.
- Caveat: "Modified" was read, not "Created", and the mover's move also updates "Modified", so it
  is an upper bound on the upload, not the upload itself.
- The Jotform API does not expose the Google Drive integration block:
  `tools/integration_status.py` shows `other integrations: none` on every form (2026-11-23). So
  the by-eye read is the live evidence.

Text Ryan can send: "The date in each photo folder's name is the session date the mentor
entered on the form, not the date the photo was uploaded. Folders from before 30 October 2026
show only the club name."

## The week number: in the name, through the integration

Two ways were weighed (ticket Outline, step 2):

- **The integration's naming** (chosen): the subfolder name carries question 100 (`WEEK_ID`,
  the session/week the mentor picked) through the integration's field tags, like the date. One
  hand edit per form, nothing new in code, and the name is right from the moment Jotform writes
  it.
- The mover renames as it moves: rejected. The mover never renames anything today; a rename
  needs the week, which the mover cannot read (it sees only Drive), and a renamed folder no
  longer matches its My Drive source by name, which the merge and the one-per-name rule rely on.

A special event has no week: question 100 is blank, so the name ends `| ` (or without the last
segment, depending on how Jotform renders a blank tag). The mover accepts both (ticket's tests).

## The folder layout

On the Shared Drive, under each region folder:

```
<Region>/
  <Partner>/
    <YYYY-MM>/
      <Partner> | <Club Name> | <MM-DD-YYYY> | <Week>/   (the submission's photos)
  <a folder named any other way>/                         (directly in the region folder, as today)
```

- The month is the session date's (question 17), `YYYY-MM`.
- The subfolder keeps the name Jotform gave it; the mover never renames.
- The partner and month folders are found by name and reused, or made by the mover when missing
  (`Drive.Files.create` on the Shared Drive). One in Drive's trash does not count. Two of the
  same name at one level: that subfolder is refused (`REFUSED … 2 folders named "<name>" …`) and
  nothing of it moves until someone merges the two by hand.
- A name that is not the new layout - every folder written before the integration edit
  (`<Club> <MM-DD-YYYY>`, or the club alone), a blank partner, a date that is not a real date -
  stays directly in the region folder, exactly as today.
- Retention (90 days, #185) walks any depth: photos under `<Partner>/<YYYY-MM>/` age out as
  before, and the emptied month and partner folders go too once they are 90 days old. Its log
  names the region folders' direct subfolders, which become the partner folders.

## The new integration naming and its prerequisite

The subfolder name in each form's Google Drive integration becomes

```
{Partner} | {Club Name} | {Date} | {Week}
```

e.g. `Sunrise Partners | Sunrise Club | 10-30-2026 | 4`. The separator ` | ` is one no club or
partner name contains (club names can contain ` - `, as in `<club> - <partner>`). `{Date}` stays
question 17 in Jotform's `mm-dd-yyyy`; `{Week}` is question 100.

**Prerequisite (not in this branch, a separate follow-up):** question 331 (Partner) is blank on
the forms with the Club picker - it is hidden and only the staff notification reads it
(`glow/sync.py` `PARTNER`). Until it is filled, `{Partner}` renders blank and every folder would
stay at the region root (the mover's rule for a blank partner). Filling it means a calculation
from the picker's choice into question 331, generated by `build_conditions` in the sync - never
made by hand in the builder, since the sync rewrites all conditions on every run (CLAUDE.md
rule 3). That follow-up is its own ticket with its own rollout.

## What this branch changes (offline, nothing live)

- `drive-sync/Plan.gs`: `photoPath_(name)` (partner and month from a layout name, `[]` for any
  other); `planMoves_` puts `path` on every move, merge, waiting and refused entry and matches a
  same-name folder on the Shared Drive by name and path.
- `drive-sync/Mover.gs`: reads the partner and month folders by name, makes the missing ones on
  the real run, refuses two of one name at a level, logs each subfolder's target path
  (`would move "<name>" to <Region>/<Partner>/<YYYY-MM>`); never a photo's file name.
- `test/drive_sync_layout_test.js` (the ticket's tests); `test/drive_sync_test.js` unchanged and
  passing (legacy names stay at the region root).
- `drive-sync/README.md`, RUNBOOK "Photos" and "Photo mover".

## Not in this plan: the one-time re-filing

The existing folders on the Shared Drive are **not** moved into the new layout here, a written
reason the Definition of done allows. Their names carry no partner (`<Club> <MM-DD-YYYY>` or the
club alone), so re-filing them needs a lookup of club → partner (the Roster or Partners tab),
a new data source or scope for the standalone mover: a design decision for Ryan. Ryan's comment
of 2026-11-18 also puts the re-filing after this work. It is a separate follow-up ticket; it
would run `previewMoves` (or its own dry run) before any real move, like every step here.

## Rollout (live; every step on Ryan's go)

1. **Question 331 filled** (the follow-up above) is rolled out and read back on every form: a
   new submission's question 331 holds its partner. Not before: the naming would carry a blank
   partner.
2. **The live mover project updated first** (it accepts both namings, so it can go before the
   integration edits): RUNBOOK "Photo mover", "Updating the live project" - `removeTrigger`,
   paste `Plan.gs` and `Mover.gs` (whole files; the manifest is unchanged: no new scope, no new
   service), `previewMoves` (a dry run: every existing subfolder still logs without a target
   path, nothing changes), `installTrigger`.
3. **The template's integration naming** edited in the builder to
   `{Partner} | {Club Name} | {Date} | {Week}` (RUNBOOK "Photos", step 2: `backup_forms.py --form`
   before and after, the diff inside `integrations` only), then one test submission on the
   template as in RUNBOOK "Photos", steps 3-4 (a neutral image, nobody in it). Before the next
   mover run takes it: `previewMoves` → `would move "<partner> | <club> | <date> | <week>" to
   Template/<partner>/<YYYY-MM>`. Then the run, and the photo is in that folder.
4. **One regional form at a time**, as #63 did (Latin America, Asia, Africa): the same edit,
   backup and diff; then the next run's `previewMoves`/log for that region shows its first
   subfolder with its target path, and the folder on the Shared Drive, before the next form.
5. The Result below: the steps with dates (UTC), counts and folder structure only (no file
   names), `Live: <what, when UTC, Ryan's go>`; status `done` with `done:`; `make docs-index`.

## Rollback

- **The naming:** edit each form's integration naming back to `{Club Name} {Date}` (backup and
  diff as in step 3). New folders then land directly in the region folder again; those already
  filed under partner and month stay where they are (nothing is moved back automatically).
- **The mover:** paste the previous `Plan.gs` and `Mover.gs` back (the repo's last commit before
  #225). The old code files every subfolder directly in the region folder, whatever its name.
  The partner and month folders it made stay; their photos can be moved by hand (within the
  Shared Drive: Content manager).
- `removeTrigger` stops the mover altogether; new photos then wait in My Drive.
- Jotform keeps its own copy of every photo (Auto Delete Submissions off).

## Risks

- A blank `{Week}` renders differently than expected: the mover accepts `… | <date> | `,
  `… | <date> |` and `… | <date>`; anything else stays at the region root (nothing lost, just
  not grouped). The template's test submission in step 3 shows the real rendering; a special
  event test is worth one too.
- `{Date}` in another format after an edit (e.g. `yyyy-mm-dd`): the folder stays at the region
  root, by the same rule. The format stays `mm-dd-yyyy` with `-` (RUNBOOK "Photos", step 2).
- A partner renamed in the sheet makes a second partner folder from then on; old photos stay
  under the old name. Merge by hand if wanted.

## Result

- **The date check: done**, 2026-11-23, Ryan, by eye: two settled folders, the name's date a
  couple of days before Drive "Modified" (an upper bound on the upload). Answer for staff: the
  dates are session dates ("The staff answer on dates", above).

- **Rollout step 2, the live mover: done**, 2026-11-23, on Ryan's go, as the company account.
  Done before step 1: the mover accepts both namings, so the order is safe.
  - `removeTrigger` by Ryan, then main's `Plan.gs` and `Mover.gs` at `ca244e7` pushed with
    clasp (a separate company-account login, not a paste) at 10:47 UTC. The manifest was unchanged.
  - Backup: the live code pulled before the push at 09:53 UTC was #144's (`8e5dabc`), so
    retention (#183) had never been live.
  - Read back by `clasp pull` after the push: `Plan.gs`, `Mover.gs` and `appsscript.json` equal
    `ca244e7`.
  - Three earlier pushes printed `Pushed 3 files.` but failed: the company account had the Apps
    Script API off (`User has not enabled the Apps Script API`). clasp 2.4.2 prints the error,
    then the success line, and exits 0. Ryan turned the API on in script.google.com's user
    settings.
  - `previewMoves`: the summary as expected (Ryan, by eye). `installTrigger` by Ryan; the next
    execution Completed.
  - `RETENTION_DAYS` is unset, so retention stays off. #183 carries the reused-folder
    `movedInto` fix, which must land before it is set.
- **Still to do:** step 1 (#236, question 331 filled), then steps 3-4 (the integration naming),
  then #237 (re-filing the existing folders: Ryan's 2026-11-23 rulings on #237).

Live: photo mover code ca244e7, 2026-11-23 10:47 UTC, Ryan's go.
