---
title: The photo mover trashes Shared Drive photos 90 days after they arrive, at every level under each region folder, never the region folders
author: Claude (ticket #180, epic #179, with Ryan's answers of 2026-10-30)
status: accepted         # Ryan's answers of 2026-10-30 on #179
created: 2026-10-30
intent: Ryan, 2026-10-30 - "Photo mover: trash photos on the Shared Drive 90 days after they arrive." GLOW's CEO approved the retention on 2026-10-30 (per Ryan). "Trash only, never permanently delete."
---

# Plan: 90-day photo retention on the Shared Drive

<!-- Kept beside epic #179: #180 records it, #181/#182/#185 build it offline, #183 rolls it out
     (Ryan), #184 proves it in January 2027. When it is done: the Result, the status and `done:`,
     then `make docs-index`. -->

## Context

**The decision.** The group photos (one per submission, of girls - minors) reach Google Drive
through Jotform's own integration ([photos plan](2026-10-06-photos-to-drive.md)), land in Ryan's
company My Drive and are moved by the photo mover (`drive-sync/`,
[mover plan](2026-10-21-drive-photo-mover.md)) into the region folders on the company Shared
Drive. The photos plan left retention open as the CEO's decision: until it was taken, nothing
was deleted from Drive. On 2026-10-30 GLOW's CEO approved 90 days (per Ryan): photos on the
Shared Drive go to its trash once they have been there 90 days. Trash only, never a permanent
delete (DECISIONS 2026-10-30).

**Jotform's subfolder name.** Since 2026-10-30 the Google Drive integration's subfolder name is
`{Club Name} {Date}` on the Template, Africa, Asia and Latin America forms (the U.S form is
disabled), e.g. `Sunrise Club 10-30-2026`. Question 17 on every active form (read 2026-10-30):
label "Date", name `date`, `control_datetime`, mmddyyyy, separator `-`, no time; question 5 is
"Club Name", hidden. Before 2026-10-30 the setting was the club name only, not the
`<Club Name> <Attendance Date>` the photos plan describes, so a folder made before then can hold
photos of many dates. Ryan changed the setting himself in the builder. Which "Club Name" field
it uses (the hidden question 5 or the Club picker) is #63's Result, not this plan's.

**What Google says** (primary sources; #180's researcher, quoted on the ticket):

- **a. The Shared Drive's trash.** "Files and folders in Trash are deleted forever after 30
  days" and "Members with Manager access can permanently delete files before 30 days"
  (https://support.google.com/a/users/answer/7212025, #144's research of 2026-10-30). Roles
  (https://support.google.com/a/users/answer/12380484): a Content manager "Can move files and
  folders to the Trash" and can restore from it within the 30 days, but cannot delete for good;
  a Manager "Can permanently delete files in the Trash". Ryan is a Content manager on the Shared
  Drive ([mover plan](2026-10-21-drive-photo-mover.md), Design; RUNBOOK "Photo mover"). The
  Drive API's `files.delete` on a shared-drive item needs `organizer` (Manager), which the mover
  never calls. `trashed`: "Whether the file has been trashed, either explicitly or from a trashed
  parent folder." (the files resource).
- **b. `createdTime` on a move: UNVERIFIED.** The files resource
  (https://developers.google.com/workspace/drive/api/reference/rest/v3/files) says only that
  `createdTime` is "The time at which the file was created"; neither it, `files.update`, nor
  Google's pages on moving content to shared drives say a move keeps it or changes it (what they
  say changes is ownership, to the organization, and inherited permissions). Nothing found
  contradicts it surviving. The mover moves files one by one (`files.update` with `addParents`
  and `removeParents`), never folders: "you can't move a folder from My Drive into a shared drive
  by updating the `addParents` parameter"
  (https://developers.google.com/workspace/drive/api/guides/folder), so every folder below a
  region folder was made on the Shared Drive, by the mover or a person. A folder's `createdTime`
  as the time it was made: partly (the folder guide: "a folder is a type of file"; no page says
  it for folders). Rollout step 6 checks it by eye.
- **c. Restoring an item whose folder is in the trash: UNVERIFIED.** No page settles where a
  restored item goes, whether its trashed folder has to be restored first, or what happens when
  the folder was trashed after its files (support.google.com/drive/answer/2405957, the shared
  drive help 7212025, and the API's delete guide, which "doesn't cover this scenario"). What is
  settled: the API restores with `files.update` and `trashed` false, and "To untrash a shared
  drive file, you also must set the boolean supportsAllDrives query parameter to true"
  (https://developers.google.com/workspace/drive/api/guides/delete); `explicitlyTrashed`:
  "Whether the file has been explicitly trashed, as opposed to recursively trashed from a parent
  folder."; `trashedTime`: "Only populated for items in shared drives." (the files resource).
- **d. The search terms: confirmed**
  (https://developers.google.com/workspace/drive/api/guides/ref-search-terms):
  - `createdTime`: operators `<=, <, =, !=, >, >=`; "Use RFC 3339 format, default time zone is
    UTC, such as 2012-06-04T12:00:00-08:00." (v3 only);
  - `parents`: operator `in` only; "Only checks direct parent folders; doesn't match indirect
    ancestor folders." The search guide
    (https://developers.google.com/workspace/drive/api/guides/search-files): "The `parents`
    query term only returns direct child files and folders located within the specified
    folder." (also #144's research);
  - `trashed`: `=` and `!=`, true or false; `mimeType`: `contains`, `=` and `!=`, quoted with `'`
    (the search guide's example: `mimeType != 'application/vnd.google-apps.folder'`);
  - `corpora=drive`: "Queries all items in the specified shared drive. The `driveId` must be
    specified in the request."; `includeItemsFromAllDrives`: "If not present or set to false,
    then shared drive items are not returned."
    (https://developers.google.com/workspace/drive/api/guides/enable-shareddrives); and
    `supportsAllDrives=true` with it (the search guide: "you must also set
    `supportsAllDrives=true` and `includeItemsFromAllDrives=true` on the request").

**No new scope.** The mover's manifest (`drive-sync/appsscript.json`) already declares
`https://www.googleapis.com/auth/drive`, which covers the trash; `Drive.Files.update` with
`{trashed: true}` is the same call #144 adds for My Drive.

## Design

**The rules** (Ryan's answers of 2026-10-30 on epic #179):

- **What is trashed.** Every file under a region folder, at any depth - directly in a region
  folder, in its subfolders, and in folders nested deeper, whoever put it there - once it is
  due; and every folder strictly below a region folder once nothing is left in it.
- **The clock.** A file is due once `now - max(its createdTime, its parent folder's createdTime)`
  is at least `RETENTION_DAYS` × 24 h. The file's own `createdTime` is Jotform's upload into
  Ryan's My Drive (expected to survive the move, unverified: Context, b); the parent is the folder it sits in on
  the Shared Drive, whose creation stands in for the time the file entered it (Drive records no
  such time).
- **Never trashed:** the region folders (`Africa`, `Asia`, `Latin America`, `Template`, and
  `U.S` if configured: the `TARGET_FOLDER_<KEY>` Script Properties), the Shared Drive's root, and
  anything outside the region folders. To keep a photo past 90 days, someone moves it out of the
  region folder.
- **Trash only.** Never `files.delete`, never `emptyTrash`, nothing that needs Manager. The undo
  is a Content manager's restore within 30 days.
- **The switch.** On only while the live project's Script Property `RETENTION_DAYS` is set; a
  value below 90 is refused. At most 100 files per run (9,600 a day); no refusal by share.

**Rulings** (reversible; from epic #179, as revised 2026-10-30):

- **R1. Coverage: every level under each configured region folder.** Files directly in a region
  folder, and anything below it at any depth, are covered. Never trashed: a region folder
  itself, the Shared Drive's root, or anything whose walk up its parents reaches no configured
  region folder (the root first, a missing or second parent, or a loop). An item counts for the
  first region folder met on the walk up; a region folder nested inside another region's folder
  is still never trashed. Guarded in the planner, in the re-checks, and in the trash helper
  itself (Ryan: "make sure the region folders do not get trashed somehow").
- **R2. The clock.** Due once `now - max(file createdTime, its parent folder's createdTime)` is
  at least `RETENTION_DAYS` × 24 h; milliseconds, no time zone, due at exactly 90 days. What the
  edge cases get (Ryan accepted these on 2026-10-30):
  - a photo the mover moves on time: 90 days from the folder the mover made, minutes after the
    upload;
  - a photo held up in My Drive and then moved into a new folder: 90 days from that folder, so
    the full 90 days on the Shared Drive;
  - a held-up photo merged into an existing folder: the later of its own and that folder's
    creation, so it can be due on arrival when both are past 90 days;
  - an old file dragged by hand into a new folder: 90 days from that folder;
  - an old file dragged by hand into an existing folder older than 90 days: both past 90 days,
    so it is trashed by the next run, within 15 minutes;
  - files in the club-only folders made before 2026-10-30: each goes by its own upload once that
    is later than the folder's creation.
- **R3. Emptied folders, at any depth, bottom-up.** A folder strictly below a region folder is
  trashed when its listing was complete, it has no untrashed child left after this run's
  trashes, it is itself at least `RETENTION_DAYS` old, and it is re-listed empty just before the
  trash. Children go before parents. The age rule protects the empty folder a move cut short
  leaves behind, which the next run merges into.
- **R4. `RETENTION_DAYS`.** Absent or blank: off. A whole number of 90 or more (spaces trimmed):
  on. Anything else: CONFIG refused for the whole run. Deleting it is the off switch.
- **R5. One Shared Drive.** With retention on, every target folder must be on a Shared Drive,
  all on the same one (read with `Drive.Files.get` `driveId`); otherwise CONFIG refused. Ryan
  confirmed that all the target region folders, Template's included, are on the one company
  Shared Drive.
- **R6. A cap of 100 files per run, oldest due moment first; no share refusal.** The rest wait
  for the next run (`RETENTION_CAP`); at four runs an hour that is 9,600 files a day. Folders
  follow their files and are not counted against the cap. Ryan: "No there are hundreds of clubs
  in a region, it may need to trash many at once."
- **R7. Inside the existing runs, after the moves, on what is left of the 4.5-minute budget.** No
  new trigger, no new entry point, and a failed move does not skip it. The reads, all with
  `corpora: 'drive'` on that drive: every untrashed folder on the drive in one paged search (every
  walk up resolves offline, no call per item); one paged search for files with `createdTime` at
  or before the cutoff (a pre-filter: a file can only be due if its own time is past the
  cutoff); a full file listing of each folder from `retentionFolders_` (the old folders strictly
  below a region folder). If the folder list is not complete within the budget, retention is
  skipped for that run (a missing child folder would make its parent look empty). The cost grows
  with the folders and the old files on the whole drive: one page per 1,000, plus one listing
  per old folder under a region.
- **R8. The only trash call is #144's helper:** `Drive.Files.update({trashed: true}, id, null,
  {supportsAllDrives: true})`. It refuses any configured folder id and the drive's id. Never
  `files.delete`, `emptyTrash` or DriveApp's `setTrashed`, and no new OAuth scope.
- **R9. Re-checks just before each trash.** The file: untrashed, not a folder, its one parent as
  planned, and the R2 moment still due. Every folder from its parent up to the region folder,
  once per run: untrashed, with its one parent as read, until a configured region folder is
  reached. A folder: re-listed empty, with its parent as planned. Never a configured id, never
  the drive's id. A failed re-check skips the item, counted, without an error; a Drive error is
  `TRASH_FAILED`, and the run ends in an error.
- **R10. The January proof is its own ticket (#184),** on hold until 2027-01-19.
- **R11. Rollout order.** The trigger is removed while `RETENTION_DAYS` is first set;
  `installTrigger` runs only after Ryan reads the would-trash count.
- **R12. The fake understands a fixed set of Drive calls** (#182's Context), so the tests can be
  written first.
- **R13. Splitting the mover work.** #182 reads and previews, #185 trashes. Each leaves the suite
  green, and nothing is pasted live until both land.
- **R14. What the logs name.** Only the names of a region folder's direct subfolders appear
  (Jotform's and the mover's `{Club Name} {Date}`). Anything deeper is counted under that
  subfolder and never named, because a person may have typed anything into a nested folder's
  name. Files directly in a region folder are counted under the region. File names never appear.

**Where it is built.** `planTrash_` and `retentionFolders_` in `drive-sync/Plan.gs` (#181, pure,
tested offline in `test/drive_sync_test.js`); the reads, the one-Shared-Drive check and the
`would trash` log in `drive-sync/Mover.gs` (#182); the trash on apply (#185). Jotform keeps its
own copy of every photo: Auto Delete Submissions stays off (BACKLOG 68; proposed ticket #177).

## Rollout (live; each step on Ryan's go)

Ryan does every step, as the company account, in the `GLOW photo mover` editor: no agent can
(clasp is logged in as another account, and no agent writes to Drive). First the docs of #183
(RUNBOOK "Photo mover", the mover plan's dated notes) land on its branch.

1. `removeTrigger`.
2. Replace the editor's `Plan.gs` and `Mover.gs` with the repo's, whole files; the manifest is
   unchanged (RUNBOOK "Photo mover", "Updating the live project"). Google may ask to authorise
   again.
3. `previewMoves` with `RETENTION_DAYS` unset → `retention off`, moves as before, no
   `CONFIG refused`.
4. Script Properties: `RETENTION_DAYS` = `90`; then `previewMoves` → per region
   `would trash 0 file(s) …`, no `CONFIG refused`. A count above 0 means something under the
   region folders is already past its due moment (a file sitting directly in a region folder,
   for example): Ryan looks at it in Drive before going on. Anything unexpected: delete
   `RETENTION_DAYS` and stop.
5. `installTrigger`. The next execution's log (within 15 minutes) shows the retention line and
   the moves as usual, with no failure.
6. By eye: the details pane of one moved photo shows "Created" = its upload date, not the move
   date (Context, b). Recorded yes or no only; a no sends #183 to `needs-input` before step 5.
7. The Result below: the steps with dates (UTC) and counts, `Live: <what, when UTC, Ryan's go>`,
   status `in-progress  # live <date>; first trashes due ~2027-01-19 to 01-22 (#184)`, then
   `make docs-index`.

Then, on or after 2027-01-19 (#184, on hold until then):

8. Ryan reads, as the company account: the Executions log of the runs since (per region
   `trashed N file(s) and M folder(s)` by region subfolder, any `RETENTION_CAP`, no
   `TRASH_FAILED`, no `TRASH_REFUSED`); the Shared Drive's trash (counts by region and their
   dates only); the region folders (`Africa`, `Asia`, `Latin America` and `Template` present and
   untrashed, every photo not yet due still in place, nothing outside the region folders
   trashed).
9. Optional, on Ryan's go: restore one Template test photo (a neutral image with nobody in it)
   from the trash, see it back in its folder, and see the next run trash it again (it is still
   due).
10. If anything is off - a region folder, an item not yet due, or anything outside the region
    folders in the trash, or a `TRASH_FAILED`/`TRASH_REFUSED` - stop: Ryan deletes
    `RETENTION_DAYS`, the items are restored within 30 days, and #184 goes to `needs-input`.
11. The read-back goes into the Result (UTC dates, counts only); status `done` with `done:`;
    `make docs-index`; RUNBOOK "Photo mover"'s Status line.

## Rollback

- **Off:** delete the Script Property `RETENTION_DAYS`; retention is off from the next run, and
  the moves go on as before. `removeTrigger` stops the whole mover.
- **Undo a trash:** a Content manager (Ryan) restores the items from the Shared Drive's trash
  within 30 days of their trash; after that Google deletes them and nothing brings them back.
  Where a restored item goes when its folder is in the trash too is unverified (Context, c), so
  restore the folder first, then anything from it still in the trash, and see each back in place.
- **The code:** paste the previous `Plan.gs` and `Mover.gs` back (the repo's last commit before
  #182); with `RETENTION_DAYS` deleted the new code trashes nothing in any case.
- Jotform's own copy of every photo stays (Auto Delete Submissions off), behind its login.

## Risks

- **A region folder, the root or something outside trashed.** Guarded three times (R1): the
  planner never plans one, the re-check before each trash walks up to a configured region
  folder (R9), and the trash helper refuses any configured id and the drive's id (R8); tested
  in `test/drive_sync_test.js` even with a wrong planner. If it happens anyway: delete
  `RETENTION_DAYS` and restore within 30 days.
- **A young photo trashed early.** The clock takes the later of the two times (R2), so a merge
  or an old club-only folder cannot shorten a photo's own 90 days; a file dragged into an old
  folder by hand can be due on arrival (accepted by Ryan). The 30 days in the trash are the undo.
- **`createdTime` not surviving the move** (Context, b): every moved photo would read as new,
  so it would be kept longer, never trashed early. Step 6 checks it by eye.
- **A folder looking empty because a listing was cut short.** R3 trashes only on a complete
  listing and a re-list just before; R7 skips retention for a run whose folder list is
  incomplete.
- **Many items at once** (a whole region's old folders): the cap of 100 per run (R6) spreads it
  over runs; there is no share refusal (Ryan).
- **Purge after 30 days.** A wrong trash noticed after 30 days cannot be undone. #184 reads the
  first trashes within days of 2027-01-19.
- **Names in logs.** Only region subfolder names, counts otherwise (R14); the plan, tickets and
  PRs carry counts and region subfolder names only.

## Proof

- Offline: `node test/drive_sync_test.js` → `ALL CHECKS PASSED` with the retention cases (#181,
  #182, #185); `make check` → `CHECK PASSED`.
- Live (Ryan): the `previewMoves` log at rollout (`retention off`, then `would trash 0 file(s)`
  per region, no `CONFIG refused`); from about 2027-01-19, the Executions log's retention lines
  and the Shared Drive's trash, counted by region.

## Result

