---
title: A standalone Apps Script moves Jotform's photo subfolders from Ryan's My Drive to the company Shared Drive
author: Claude (ticket #89, with Ryan's decision of 2026-10-21)
status: accepted         # built offline 2026-10-21 (drive-sync/); set up before #63 (Ryan, 2026-10-22); every live step below waits for Ryan's go
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
- **The move.** `DriveApp` `Folder.moveTo` / `File.moveTo`: the `drive` scope only. Drive API v3
  `files.update` with `addParents`/`removeParents` and `supportsAllDrives` needs the same scope
  plus an enabled advanced service, so `DriveApp` is the smaller of the two.
- **What moves** (`planMoves_` in `drive-sync/Plan.gs`, pure, tested offline by
  `test/drive_sync_test.js`):
  - only folders named exactly `Attendance photos - <Region>`, region one of Africa, Asia,
    Latin America, U.S, Template, with a target configured; any other `Attendance photos - …`
    folder is reported unknown and left alone; any other folder is ignored;
  - a subfolder whose newest file changed less than **10 minutes** ago waits (still uploading);
    an empty one is left alone;
  - a settled subfolder whose name is not in the region folder on the Shared Drive **moves
    whole**;
  - its name already there **once** (a resubmission): **merged** file by file, each file moved
    in beside what is there; a file with the same name **and** size already there stays in My
    Drive (`kept`); nothing on the Shared Drive is replaced (a move never overwrites);
  - its name there **twice or more**: **refused**, the mover does not pick one (moved by hand);
  - two settled subfolders of one name in one region: one moves or merges files, the other waits
    for the next run (never two same-name folders created by one run); a merge whose files are
    all kept moves nothing, so it never holds up the other copy and never waits itself.
- **The run** (`drive-sync/Mover.gs`): the folder ids come from Script Properties
  (`SOURCE_FOLDER_<KEY>`, `TARGET_FOLDER_<KEY>`, KEY = AFRICA, ASIA, LATIN_AMERICA, US,
  TEMPLATE; never in the repo). A region with neither is skipped; half a pair, an id used twice,
  no pair at all, a source folder whose name is not `Attendance photos - <Region>`, or a target
  folder whose name is not exactly `<Region>`, is refused before any subfolder is read. One run
  at a time (`LockService`); a run stops reading new subfolders after half its 4.5-minute budget
  and starting new moves after 4.5 minutes (Apps Script's limit is 6), and leaves the rest to the
  next. Each source subfolder is read together with the target's subfolders of its name, so a
  subfolder in the plan always has its target side read. Every failure is logged
  by code (`MOVE_FAILED`, `MERGE_FAILED`, `CONFIG refused`, `LOCKED`, `TIME_BUDGET`) and a run
  with a failure ends in an error, so the execution shows as failed.
- **The log**: per region `move N, merge N (F file(s) in, K kept), waiting N, refused N`, then one
  line per subfolder by name (club names and dates, as in the folder names). Never a file name,
  never contents.
- **Never** a share, a link, a copy, a trash or an e-mail (the test forbids the calls). Who sees
  the photos is the Shared Drive's membership: the named list (the CEO and Ryan), never "anyone
  with the link".
- **Entry points**: `previewMoves` (the dry run: reads, plans, logs, changes nothing),
  `moveSettledPhotos` (the real run; the trigger's handler), `installTrigger` (every 15 minutes,
  once), `removeTrigger` (stops it).

### Not chosen

- **Copy, then trash the original**: a second copy of minors' photos sits in Ryan's trash for 30
  days, and the copy has a new owner and date. A move keeps one copy.
- **A GitHub Actions job with a service account**: Ryan's My Drive shared to a robot account,
  its key as a repository secret, the photos readable from the runner. More secrets, more
  places that can see the photos.
- **Moving the code into `appsscript/`**: the Drive scope makes the form-submit trigger fail
  until re-authorised (rule 11).

## Rollout (live; each step on Ryan's go)

The order (Ryan, 2026-10-22): the mover is set up first, with the My Drive source folders it
reads; #63 then points each form's Google Drive integration at its region's source folder.

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
3. **#63** (Ryan, in the builder; RUNBOOK "Photos", steps 1-2 and 5): each form's Google Drive
   integration pointed at its region's source folder, `Attendance photos - <Region>` in Ryan's
   My Drive, template first.
4. **Template test, then the trigger**: the photos plan's test submission on the template
   (RUNBOOK "Photos", step 3: a neutral image with nobody in it). After 10 minutes,
   `previewMoves` → `would move 1` naming `<club> <date>`; then `moveSettledPhotos` by hand,
   once → `done: 1 folder(s) moved, 0 file(s) merged, 0 failure(s)`; the subfolder is in the
   Template folder on the Shared Drive and gone from `Attendance photos - Template`, which
   stays. Then `installTrigger`; the next executions (every 15 minutes) log `move 0 … waiting 0`
   or the folders they moved. Each regional form is verified by its first real submission's
   subfolder arriving on the Shared Drive within half an hour.

## Rollback

- Stop: `removeTrigger`, or delete the trigger in the editor (Triggers). Nothing else runs it.
- Undo a move: move the subfolder (or the merged files) back into `Attendance photos - <Region>`
  by hand; the mover changes nothing else. A merged file is told apart by its date; the log names
  the subfolder it went into.
- Remove entirely: delete the trigger, then the standalone project. Jotform's integration keeps
  writing into Ryan's My Drive as before; `appsscript/` and the forms are untouched by any of it.

## Risks

- **Moving a folder into a Shared Drive may need Manager, not Content manager** (Google lets
  content managers move files; folders may need the Manager role or a domain setting:
  unverified). The dry run cannot show it; the template test's first real move does
  (`MOVE_FAILED`). Mitigation: Ryan's role on the drive raised to Manager, then the test again.
- **A late file.** A file Jotform adds after the subfolder moved: the settle time (10 minutes
  since the newest file) makes it unlikely; if Jotform makes a new subfolder of the same name, it
  is merged on a later run; if it writes into the moved folder, it is already on the Shared
  Drive.
- **Leftovers in My Drive.** A merge leaves the files it kept (same name and size already on
  the Shared Drive) in their subfolder, logged as kept every run. Ryan deletes such a subfolder
  by hand after a look; the mover never trashes.
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

Not rolled out yet: built offline on 2026-10-21 (ticket #89). Filled in after the rollout.
