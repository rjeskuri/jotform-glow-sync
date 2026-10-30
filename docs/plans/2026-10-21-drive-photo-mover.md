---
title: A standalone Apps Script moves Jotform's photo subfolders from Ryan's My Drive to the company Shared Drive
author: Claude (ticket #89, with Ryan's decision of 2026-10-21)
status: in-progress      # set up and its trigger live 2026-10-23; every move failed (#132); the file-by-file fix pasted live 2026-10-25; #144 (the emptied subfolders trashed, the rescue) pasted live 2026-10-30, the rescue still unexercised (Result)
created: 2026-10-21
intent: Ryan, 2026-10-21 (ticket #89) - "Jotform will only use my local company gmail, but it needs to go to a company shared drive. So photos will be uploaded to me and then need to be transferred to the shared drive. Can we create a custom way to do this sync."
---

# Plan: the photo mover (My Drive → Shared Drive)

## Context

The [photos plan](2026-10-06-photos-to-drive.md) sends each submission's uploaded files (the
group photo, faces visible) to Google Drive through Jotform's own integration: one folder per
form, `Attendance photos - <Region>`, one subfolder per submission named
`<Club Name> <Attendance Date>`, uploaded files only, no PDF. That integration writes only into
the connected account's **My Drive**; Shared Drives are not supported. The plan assumed a GLOW
Workspace role account; on 2026-10-21 Ryan said the integration runs on **his company account**,
and the photos must end up on a **company Shared Drive**, not in a staff member's My Drive.

So the photos land in Ryan's My Drive and something must move them on. This plan is that
something: `drive-sync/`, a standalone Apps Script project owned by Ryan's company account.

## Design

- **Its own project.** Not `appsscript/`: a Drive scope in the sheet's script stops its
  form-submit trigger until the owner re-authorises (CLAUDE.md rule 11). `drive-sync/` has its
  own manifest (time zone America/New_York, the sheet's zone; scopes `drive` and
  `script.scriptapp`, nothing else), its own `.clasp.json` (a template in the repo, the real one
  gitignored), the same pinned Node 18 / clasp 2.4.2.
- **The move.** Planned as `DriveApp` `Folder.moveTo` / `File.moveTo` (the `drive` scope only).
  Live, every folder move failed (2026-10-23, #132): Google's API does not move a folder from My
  Drive into a shared drive at any role (`teamDrivesFolderMoveInNotSupported`). Since 2026-10-24
  the mover makes a folder of the subfolder's name in the region folder and moves its files into
  it one by one through the advanced Drive service, v3 (`Drive.Files.create`, then
  `Drive.Files.update` with `addParents`/`removeParents` and `supportsAllDrives: true`; the
  manifest enables the service, the `drive` scope covers it); a merge moves files the same way.
  The emptied subfolder stays in My Drive until a later run removes it (#144, below), and a
  move cut short by a failure or the time budget is finished by a later run as a merge.
- **What moves** (`planMoves_` in `drive-sync/Plan.gs`, pure, tested offline by
  `test/drive_sync_test.js`):
  - only folders named exactly `Attendance photos - <Region>`, region one of Africa, Asia,
    Latin America, U.S, Template, with a target configured; any other `Attendance photos - …`
    folder is reported unknown and left alone; any other folder is ignored;
  - a subfolder whose newest file changed less than **10 minutes** ago waits (still uploading);
    an empty one is left alone;
  - a settled subfolder whose name is not in the region folder on the Shared Drive **moves**: a
    folder of its name is made there and all its files (the plan's `files`) move into it;
  - its name already there **once** (a resubmission): **merged** file by file, each file moved
    in beside what is there; a file with the same name **and** size already there stays in My
    Drive (`kept`); nothing on the Shared Drive is replaced (a move never overwrites);
  - its name there **twice or more**: **refused**, the mover does not pick one (moved by hand);
  - two settled subfolders of one name in one region: one moves or merges files, the other waits
    for the next run (never two same-name folders created by one run); a merge whose files are
    all kept moves nothing, so it never holds up the other copy and never waits itself.
- **What is removed** (#144, Ryan's request of 2026-10-25; `remove` in `planMoves_`, carried
  out by the real run only). The rule, **for Ryan to confirm before the paste** (the ticket's
  definition of done): a source subfolder is "safe to remove" when
  - it is a direct subfolder of a configured `Attendance photos - <Region>` folder, not in the
    trash, holding no file and no subfolder (a file in the trash still in it counts: such a
    folder is never removed);
  - it has itself not changed for at least `SETTLE_MINUTES` (10);
  - just before the trash, the real run re-reads it (still a folder in that source folder, not in
    the trash, unchanged for 10 minutes) and re-lists it with `trashed = true or trashed = false`:
    anything in it, and it stays (`not trashed "<name>"`, no error; the next run looks again);
  - it goes to the trash (`Drive.Files.update {trashed: true}`, restorable for 30 days), never
    deleted for good, and only through `moveToTrash_`, the one trash, which refuses on its own a
    configured source or target folder and the Shared Drive's root (the drive's id) whatever its
    caller passes (#185, the Shared Drive's retention, reuses it);
  - never a subfolder that still holds a merge's `kept` files, a `waiting` or `REFUSED` one (they
    hold files), the `Attendance photos - <Region>` folder itself, anything outside the
    configured source folders, or anything on the Shared Drive.

  Which ones: every emptied, settled subfolder the run reads, whoever emptied it, so the
  leftovers of earlier runs (and of the weeks before #144) go on the first run. The subfolders a
  run empties are removed by a later run, once 10 minutes have passed: the planner sees Drive's
  state, not a history, and a folder the run just emptied has not settled.
- **The rescue** (#144, Ryan's option (b), 2026-10-30). Jotform staff say an edited submission
  re-sends its files into the folder of the same name, and no source says where that upload goes
  when the folder is in the trash (the ticket's research). So every run also lists each source
  folder's subfolders in the trash and their files, through the advanced Drive service with
  `trashed = true` stated in every query (Drive's default lists the trash too); the files of up
  to 20 such subfolders come in one query, since each trashed subfolder stays there 30 days. A
  file there that Drive reads as in the trash through its folder only (`explicitlyTrashed`
  false) is planned like any other (moved, merged with kept, waiting, refused; one per name per
  run with a live subfolder of its name) and moved by one `Drive.Files.update` carrying
  `{trashed: false}` with `addParents`/`removeParents`, then re-read (`Drive.Files.get`): still in
  the trash, or not in the folder it was sent to, is `RESCUE_FAILED`. Settled from the later of
  its `modifiedTime` and `createdTime`. A file a person trashed (`explicitlyTrashed` true) is left
  alone; a subfolder in the trash with nothing to move is in no list.
- **The run** (`drive-sync/Mover.gs`): the folder ids come from Script Properties
  (`SOURCE_FOLDER_<KEY>`, `TARGET_FOLDER_<KEY>`, KEY = AFRICA, ASIA, LATIN_AMERICA, US,
  TEMPLATE; never in the repo). A region with neither is skipped; half a pair, an id used twice,
  no pair at all, a source folder whose name is not `Attendance photos - <Region>`, or a target
  folder whose name is not exactly `<Region>`, is refused before any subfolder is read. One run
  at a time (`LockService`); a run stops reading new subfolders after half its 4.5-minute budget
  and starting new moves after 4.5 minutes (Apps Script's limit is 6), and leaves the rest to the
  next. Each source subfolder is read together with the target's subfolders of its name, so a
  subfolder in the plan always has its target side read (an emptied subfolder, no files, costs
  its one listing and nothing more). Every failure is logged
  by code (`MOVE_FAILED`, `MERGE_FAILED`, `CONFIG refused`, `LOCKED`, `TIME_BUDGET`) and a run
  with a failure ends in an error, so the execution shows as failed.
- **The log**: per region `move N, merge N (F file(s) in, K kept), waiting N, refused N, remove
  N, rescue N` (`would …` in the dry run), then one line per subfolder by name (club names and
  dates, as in the folder names; `(in the trash)` after a rescued one); the real run's `done:`
  line gives the folders actually removed. Never a file name, never contents.
- **Never** a share, a link, a copy or an e-mail; never a file trashed, a folder with anything in
  it, anything on the Shared Drive, a permanent delete or an emptied trash: the one trash is an
  emptied source subfolder's (above; the test forbids every other call, as rules a later ticket
  can extend). Who sees the photos is the Shared Drive's membership: the named list (the CEO and
  Ryan), never "anyone with the link".
- **Entry points**: `previewMoves` (the dry run: reads, plans, logs, changes nothing),
  `moveSettledPhotos` (the real run; the trigger's handler), `installTrigger` (every 15 minutes,
  once), `removeTrigger` (stops it).

### Not chosen

- **Copy, then trash the original**: a second copy of minors' photos sits in Ryan's trash for 30
  days, and the copy has a new owner and date. A move keeps one copy. (An emptied subfolder holds
  no photo, so #144's trash does not run into this; it never trashes a file.)
- **#144, the template test first** (option (a): one test submission edited after its subfolder
  was trashed, to see where the re-upload lands): Ryan skipped it on 2026-10-30, so the rescue is
  built without knowing whether it is needed. **Keep deleting by hand** (option (c)): no change.
- **#144, only the subfolders this run emptied**: such a folder has just changed, so it is not
  settled at the end of that run, and the planner would need a history of runs to tell them
  apart; the earlier runs' leftovers would stay for Ryan to delete by hand.
- **A GitHub Actions job with a service account**: Ryan's My Drive shared to a robot account,
  its key as a repository secret, the photos readable from the runner. More secrets, more
  places that can see the photos.
- **Moving the code into `appsscript/`**: the Drive scope makes the form-submit trigger fail
  until re-authorised (rule 11).

## Rollout (live; each step on Ryan's go)

The order (Ryan, 2026-10-22): the mover is set up first, with the My Drive source folders it
reads; #63 then points the template's Google Drive integration at its source folder; the
template test and the trigger come next, and only then the regional forms' integrations.

1. **Land PR #91** (code only; nothing live).
2. **Setup** (Ryan; `drive-sync/README.md`, Setup steps 1-6):
   - the Shared Drive and its region folders, named exactly `Africa`, `Asia`, `Latin America`,
     `Template` (`U.S` only if its form is re-enabled); members the named list only; Ryan's
     company account a Content manager or more;
   - one source folder per region in Ryan's company My Drive, for Jotform's uploads, named
     exactly `Attendance photos - <Region>` (the mover refuses any other name);
   - the standalone project as the company account, `.clasp.json` from `.clasp.json.example`,
     `cd drive-sync && npx clasp push -f` under Node 18, logged in as that account (or the files
     pasted into the editor);
   - Script Properties `SOURCE_FOLDER_<REGION>` / `TARGET_FOLDER_<REGION>`, one pair per region;
   - `previewMoves` on the empty folders, authorise when asked: one line per region, `would move
     0, would merge 0 (0 file(s) in, 0 kept), waiting 0, refused 0`, no `CONFIG refused`;
     nothing changes in either drive.
3. **#63, the template only** (Ryan, in the builder; RUNBOOK "Photos", steps 1-2): the
   template's Google Drive integration pointed at `Attendance photos - Template` in Ryan's My
   Drive. No regional form yet.
4. **Template test, then the trigger**: the photos plan's test submission on the template
   (RUNBOOK "Photos", steps 3-4: a neutral image with nobody in it; the read-back checks the
   subfolder's name and which folder Jotform wrote into, see Risks). After 10 minutes,
   `previewMoves` → `would move 1` naming `<club> <date>`; then `moveSettledPhotos` by hand,
   once → `done: 1 folder(s) moved (1 file(s)), 0 file(s) merged, 0 failure(s)`; a folder of the
   subfolder's name is in the Template folder on the Shared Drive with the photo, and the
   emptied subfolder is still in `Attendance photos - Template` (deleted by hand; that folder
   itself stays). Then `installTrigger`; the next executions (every 15 minutes) log `move 0 …
   waiting 0` or the folders they moved.
5. **#63, the regional forms** (Ryan, in the builder; RUNBOOK "Photos", step 5), only after
   step 4 passed, one form at a time: its integration pointed at `Attendance photos - <Region>`;
   then the next run's log for that region (no `CONFIG refused`, no `UNKNOWN`), and its first
   real submission's subfolder on the Shared Drive within half an hour, before the next form.

### #144: the emptied subfolders removed, and the rescue (Ryan's paste, on his go)

The code is in the repo; the live project is updated by hand, as for #132 (clasp is logged in as
another account). The manifest is unchanged: no new scope, no new service.

0. **Ryan confirms the "safe to remove" rule** (Design, "What is removed") on ticket #144,
   before any paste.
1. Land the pull request (code only; nothing live).
2. As the company account, open the `GLOW photo mover` project and run `removeTrigger` (log:
   `removeTrigger: 1 trigger(s) deleted; the mover is stopped`). Left on, the trigger (installed
   2026-10-23, every 15 minutes) would run the new code before step 4's preview is read, trash
   and rescue unchecked, and step 5's counts would not be the preview's. New photos wait in My
   Drive until step 6.
3. Replace the editor's `Plan.gs` and `Mover.gs` with the repo's (the whole file each). Save.
4. Run `previewMoves`. Each region's line now ends `would remove N, would rescue N`, and each
   folder it would remove is named on a `would remove "<name>"` line: they are the emptied
   subfolders in `Attendance photos - <Region>` (the leftovers of earlier runs at first), and
   none of them holds a file. Nothing changes. `would rescue` is expected to be 0 (no photo has
   been seen in a trashed subfolder yet). Above 0, stop and look before going on, the trigger
   still off: each such subfolder is in My Drive's trash, named on a `would move "<name>" (in
   the trash)` or `would merge "<name>" (in the trash)` line. If someone trashed it to discard
   its photos, the photos are trashed by themselves (the rescue leaves those alone) and
   `previewMoves` runs again; a leftover trashed by hand that Jotform wrote into since is what
   the rescue is for.
5. Run `moveSettledPhotos` once and compare its log with the preview: its region lines are the
   preview's without `would` (unless a folder settled in between); its `done:` line gives `N of
   these file(s) out of the trash`, 0 when `would rescue` was 0, and `N emptied folder(s)
   removed (to the trash)`, N the `would remove` total (fewer only with a `not trashed
   "<name>"` line). Those folders are in My Drive's trash and gone from `Attendance photos -
   <Region>`; apart from the moves its log names, the photos and the Shared Drive are as before.
6. Run `installTrigger` (`installTrigger: moveSettledPhotos every 15 minutes`). The counts go in
   the Result.

## Rollback

- Stop: `removeTrigger`, or delete the trigger in the editor (Triggers). Nothing else runs it.
- Undo a move: move the files back into the emptied subfolder in `Attendance photos - <Region>`
  (or a new folder of its name, once it was cleared) by hand; the mover changes nothing else. A
  merged file is told apart by its date; the log names the folder it went into. Moving files out
  of a shared drive needs Manager on it (Google, "How file access works in shared drives": "If
  you have Manager access to a shared drive, you can move files and folders out of shared drive
  to My Drive"; RUNBOOK "Photo mover", Rollback): a Manager does it, or Ryan's role is raised.
- Undo a removal (#144): a removed subfolder is in My Drive's trash for 30 days; Drive → Trash →
  the folder → Restore puts it back in `Attendance photos - <Region>` (the log names it on a
  `remove "<name>"` line). To stop removing: paste back the previous `Mover.gs` and `Plan.gs`
  (`git show 4e77831:drive-sync/Mover.gs`, the same for `Plan.gs`), or `removeTrigger`.
- Remove entirely: delete the trigger, then the standalone project. Jotform's integration keeps
  writing into Ryan's My Drive as before; `appsscript/` and the forms are untouched by any of it.

## Risks

- **Moving a folder into a Shared Drive may need Manager, not Content manager** (Google lets
  content managers move files; folders may need the Manager role or a domain setting:
  unverified). The dry run cannot show it; the template test's first real move does
  (`MOVE_FAILED`). Mitigation: Ryan's role on the drive raised to Manager, then the test again.
  - 2026-10-24 (#132): it failed live, and no role fixes it: Google's API does not move a folder
    from My Drive into a shared drive (`403 teamDrivesFolderMoveInNotSupported`; only the Drive
    UI, as a Manager). The mover now makes the folder on the Shared Drive and moves the files
    into it one by one through the advanced Drive service (`Drive.Files.update`,
    `supportsAllDrives`); Ryan owns the files, for which Content manager (Contributor at least)
    suffices. The emptied subfolder stays in My Drive.
- **A late file.** A file Jotform adds after the subfolder moved: the settle time (10 minutes
  since the newest file) makes it unlikely; if Jotform makes a new subfolder of the same name, it
  is merged on a later run; if it writes into the moved folder, it is already on the Shared
  Drive.
- **Leftovers in My Drive.** A merge leaves the files it kept (same name and size already on
  the Shared Drive) in their subfolder, logged as kept every run. Ryan clears such a subfolder by
  hand after a look, by trashing its files, then the folder: a file trashed by itself is left
  alone by the rescue (next), and the mover never removes a subfolder still holding a file, even
  one in the trash. Every move leaves its subfolder emptied; since #144 a later run removes it
  (Design).
- **The rescue cannot tell who trashed a folder** (#144). A subfolder a person trashed with
  photos still in it reads like one the mover trashed and Jotform wrote into: its photos are
  moved to the Shared Drive. To discard a photo in My Drive, trash the photo itself (a file
  trashed explicitly is left alone). The RUNBOOK says so.
- **The rescue is unproven live** (#144): Ryan skipped the template test on 2026-10-30, so the
  first real case is its test. Partly unverified (the ticket's research of 2026-10-30): whether
  an edited submission re-sends its photos at all, and where they land when the folder is in
  the trash; whether `'<id>' in parents` with `trashed = true` lists the children of a trashed
  folder; what `createdTime` an upload into a trashed folder gets; whether a parent change takes
  a file out of the trash (the mover does not rely on it: `{trashed: false}` goes in the same
  update, and the file is re-read). A rescue Drive accepts but does not carry out is
  `RESCUE_FAILED` (the photo may sit in the Shared Drive's trash or still in its subfolder in My
  Drive's trash: found and restored by hand, RUNBOOK "Photo mover").
- **The trash's cost** (#144): every run lists each source folder's subfolders in the trash
  (one query per region) and their files (one query per 20 of them); a removal costs one read
  and one listing more.
- **A backlog** (the first run after a pause, or a busy day): a run reads for at most about 2
  minutes (half its budget, `TIME_BUDGET` in the log) and never moves a subfolder it did not
  read; the rest waits for the next run, 15 minutes later. Same-name copies clear one per run
  (the planner is tested to settle within 10 runs and never to make a second same-name folder on
  the Shared Drive).
- **A wrong folder id.** A Script Property pointing at the wrong folder would move photos to the
  wrong place. Mitigation: the source must be named exactly `Attendance photos - <Region>` and
  the target exactly `<Region>`, or the run is refused (`CONFIG refused`) before it reads a
  subfolder; an id used twice is refused too.
- **Jotform makes its own folder.** Whether the integration writes into the existing
  `Attendance photos - <Region>` folder or creates a second one of that name is unverified. The
  template test shows it (`previewMoves` → `would move 0` while the test subfolder sits in My
  Drive); then `SOURCE_FOLDER_<REGION>` is pointed at the folder Jotform writes into, and the
  empty one is deleted by hand.
- **Authorisation lapses** (a password change, a revoked session): the trigger's runs fail and
  Google sends the owner its failure summary; re-run any entry point in the editor and accept.
- **Ryan's account.** The integration and the mover run on it; the photos do not stay in it.
  If the account goes, the Shared Drive keeps the photos; the integration and the mover are set
  up again on another account (the photos plan, the README).
- **Names.** Folder names carry the club and the date only (the photos plan's subfolder rule);
  the mover logs them and nothing more.

## Proof

- `node test/drive_sync_test.js` → `ALL CHECKS PASSED`.
- `make check` → `CHECK PASSED`; `make gs` unchanged (`appsscript/` and its scopes untouched).

## Result

- 2026-10-23: set up as planned (the Shared Drive's region folders, the source folders, the
  project, its Script Properties, `previewMoves` clean) and the trigger installed; the forms'
  integrations write into the source folders. Every real move failed: `cannot use this
  operation on a shared drive item` - Google's API does not move a folder from My Drive into a
  shared drive (`teamDrivesFolderMoveInNotSupported`), whatever the role.
- 2026-10-24 (#132): fixed in the repo - the folder is made on the Shared Drive and the files
  move into it one by one through the advanced Drive service (Design, "The move"; Risks). The
  live project awaits Ryan's paste of `Plan.gs`, `Mover.gs` and the manifest, then one
  `moveSettledPhotos` and its log (RUNBOOK "Photo mover", the update steps).
- 2026-10-25: Ryan pasted the #132 fix; `previewMoves` and `moveSettledPhotos` worked. Every move
  left its emptied subfolder in My Drive, deleted by hand (ticket #144's request).
- 2026-10-30 (#144): built offline - the emptied, settled subfolders go to the trash, and the
  rescue (Design); `test/drive_sync_test.js` passes. Not live: it waits for Ryan's confirmation
  of the "safe to remove" rule and his paste (Rollout, #144). The rescue is unproven live (Ryan
  skipped the template test, 2026-10-30) and rests on Drive semantics the research could only
  partly confirm (Risks). The counts of the first `previewMoves` and `moveSettledPhotos` go here.
- 2026-10-30 (#144, live; Ryan's paste in the US Eastern evening, about 01:00 UTC on
  2026-10-31): Rollout #144 steps 2 to 6. `removeTrigger`; `Plan.gs` and `Mover.gs` pasted from
  main 8e5dabc. `previewMoves` (20:57 Eastern, 00:57 UTC): would move 1 (Africa), would merge 4
  (0 files in, 4 kept: Africa), would remove 162 (Africa 91, Asia 47, Latin America 24,
  Template 0), would rescue 0 in every region. `moveSettledPhotos` (21:05 Eastern, 01:05 UTC):
  1 folder moved (1 file), 0 files merged, 0 out of the trash, 162 emptied folders removed (to
  the trash), 0 failures - equal to the preview. Then `installTrigger`. The rescue is still
  unexercised live (nothing to rescue). The 4 Africa subfolders whose files were kept (already
  on the Shared Drive) stay until Ryan trashes those files, then the folders.
