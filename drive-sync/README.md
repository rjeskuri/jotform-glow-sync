# drive-sync: the photo mover

Jotform's Google Drive integration writes only into the connected account's My Drive, and the
integration runs on Ryan's company account. This standalone Apps Script project, owned by that
same account, moves each submission subfolder (`<Club Name> <Attendance Date>`) from
`Attendance photos - <Region>` in Ryan's My Drive into that region's folder on the company Shared
Drive, once the subfolder has not changed for 10 minutes. It runs every 15 minutes on a
time-driven trigger. Plan: [docs/plans/2026-10-21-drive-photo-mover.md](../docs/plans/2026-10-21-drive-photo-mover.md);
procedure: RUNBOOK "Photo mover". With the Script Property `RETENTION_DAYS` set, it also moves
photos on the Shared Drive to that drive's trash once they have been there that many days (90,
GLOW's CEO, 2026-10-30), and the folders they empty below the region folders: plan
[docs/plans/2026-10-30-photo-retention.md](../docs/plans/2026-10-30-photo-retention.md), epic #179.

It is **not** the sheet's Apps Script (`appsscript/`): a Drive scope there would stop the
form-submit trigger until the owner re-authorises (CLAUDE.md rule 11). This project has its own
scopes, `drive` and `script.scriptapp` (the trigger), and nothing else; the moves go through the
advanced Drive service (v3, enabled in its manifest), which uses the same `drive` scope.

What it does and never does:

- a settled subfolder moves as its files: Drive cannot move a folder from My Drive into a Shared
  Drive (#132, 2026-10-24: `teamDrivesFolderMoveInNotSupported`, whatever the role), so the mover
  makes a folder of the subfolder's name in the region folder and moves the files into it one by
  one (`Drive.Files.update` with `addParents`/`removeParents`, `supportsAllDrives`). When that
  name is already in the region folder once (a resubmission) its files move in the same way
  beside what is there, and a file whose name and size are both already there stays in My Drive
  (logged as kept). Nothing is ever replaced;
- the emptied subfolder is removed by a later run (#144): once it holds no file and no subfolder
  and has not changed for 10 minutes, the real run re-reads and re-lists it and moves it to My
  Drive's trash (restorable there for 30 days; logged `remove "<name>"`). One trash helper,
  `moveToTrash_`, does every trash and refuses a configured source or target folder and the
  Shared Drive's root whatever its caller asks. A subfolder still holding kept files, waiting,
  refused, or holding a subfolder is never removed;
- the rescue (#144): Jotform may write an edited submission's photos into a subfolder the mover
  has already trashed. Every run lists each source folder's subfolders in the trash, and a photo
  in one (in the trash through its folder only) moves like any other, out of the trash in the
  same update; a photo a person trashed is left alone. So: to discard a photo in My Drive, trash
  the photo itself, not only its subfolder;
- two or more folders of that name on the Shared Drive: refused and logged, moved by hand;
- the `Attendance photos - <Region>` folders themselves stay: Jotform writes into them;
- retention (#185, only with `RETENTION_DAYS` set, only on the real run, after the moves): every
  photo under a region folder on the Shared Drive, at any depth (directly in the region folder,
  in a club subfolder, or nested deeper), goes to the Shared Drive's trash once `RETENTION_DAYS`
  have passed since the later of its own creation and its folder's; then every folder below a
  region folder that is itself that old and has nothing left in it, children before parents. At
  most 100 photos a run, the earliest due first (`RETENTION_CAP`: the rest go on the next run).
  Each item is re-read just before its trash (still where the run read it, still due, a folder
  re-listed empty; every folder above it read once per run, before the first trash under it, and
  then untrashed in the folder the run read it in: a folder moved after that one read is not
  seen) and skipped otherwise; a folder this run merged into or made, and every folder above it,
  is kept that run (#191: Drive's search may not yet show a photo just moved in). Every trash
  goes through `moveToTrash_`. Never trashed: a region folder (`TARGET_FOLDER_<KEY>`, one
  nested inside another region's too), a source folder, the Shared Drive's root, anything not
  under a region folder, a photo before its due moment, a folder with anything left in it. To
  keep a photo longer, move it out of the region folders. The dry run (`previewMoves`) trashes
  nothing and logs what the real run would;
- it never shares, links, copies or e-mails a file, never trashes one in My Drive (only the
  emptied subfolders above), on the Shared Drive only what retention says, and never deletes
  anything for good (no permanent delete, no emptied trash). The photos show girls' faces; only
  the Shared Drive's members see them;
- the log (Executions) holds counts and folder names, never a file's name or contents; for
  retention only the names of the region folders' direct subfolders (the club subfolders), with
  everything deeper counted under them:

  | Line | Means |
  | --- | --- |
  | `retention 90 days (due once … at or before <cutoff>)` | retention on; `retention off (RETENTION_DAYS not set)` when not |
  | `<Region>: retention 90 days: would trash N file(s) and M folder(s)` | the plan, both entry points; a line `under "<club subfolder>"` per subfolder, one for the photos `directly in the region folder` |
  | `<Region>: retention 90 days: trashed N file(s) and M folder(s)` | the real run: what went to the trash, the same lines under it |
  | `not trashed "<club subfolder>": N item(s) kept by the re-check` | moved, trashed or re-dated since the read, a folder not empty, or a folder this run moved photos into or one above it: no error, the next run looks again |
  | `RETENTION_CAP: N due file(s) left for the next run` | more than 100 due |
  | `TIME_BUDGET: retention …` | out of time: the rest waits for the next run |
  | `TRASH_FAILED <Region> "<club subfolder>": <error>` | Drive refused a trash; the rest goes on, the run ends with an error |
  | `TRASH_REFUSED <Region>: …` | the plan named a region folder, the root, or something not below its region folder: nothing trashed that run, an error (a bug: stop and look) |
  | `RETENTION_FAILED <step>: <error>` | a retention read failed: nothing previewed or trashed, an error after the moves |

Files: `Plan.gs` (the planner, pure, tested by `test/drive_sync_test.js`), `Mover.gs` (the entry
points), `appsscript.json` (time zone America/New_York, the sheet's; the two scopes; the advanced
Drive service `Drive`, v3), `.clasp.json.example` (the clasp link template), `.claspignore`.

## Setup (once, Ryan)

The mover is set up first (Ryan, 2026-10-22): steps 1-6 need no form change and move nothing.
Its My Drive source folders (step 2) are the folders each form's Google Drive integration is then
pointed at (#63, RUNBOOK "Photos"); steps 7-8 follow the template's integration and a test
upload on it, and step 9 (the regional forms) comes last.

1. **The Shared Drive.** A company Shared Drive with one folder per region in use, named exactly
   `Africa`, `Asia`, `Latin America`, `Template` (and `U.S` only if that form is re-enabled):
   the mover refuses a target folder with any other name. Members: the named list only
   (the CEO and Ryan); never "anyone with the link". Ryan's company account is at least a
   **Content manager**: Ryan owns the files (Jotform uploads as his account), and Google's
   documented minimum for moving one's own files into a shared drive is Contributor. Manager is
   not needed: no role lets the API move a folder in, which is why the mover moves files
   (#132, 2026-10-24; the plan's Risks).
2. **The source folders.** In the company account's My Drive, one folder per region in use for
   Jotform's uploads, named exactly `Attendance photos - <Region>` (`Attendance photos -
   Africa`, … `Attendance photos - Template`): the mover refuses a source folder with any other
   name. Not shared with anyone.
3. **The project.** Signed in as the company account, script.google.com → New project, named
   `GLOW photo mover`. Project Settings → copy the Script ID. In the repo:
   `cp drive-sync/.clasp.json.example drive-sync/.clasp.json` and paste the id there
   (`drive-sync/.clasp.json` is gitignored; ids never go in the repo).
4. **Push** (a live write: Ryan's go). Node 18 and clasp 2.4.2 are pinned (CLAUDE.md rule 11):
   `nvm use 18`, then `cd drive-sync && npx clasp push -f`. clasp must be logged in as the
   company account (`npx clasp login`; the login is global, in `~/.clasprc.json`, so check it
   again before the next `appsscript/` push). Or paste `Plan.gs`, `Mover.gs` and the manifest
   into the editor by hand (Project Settings → show the manifest). The manifest enables the
   **advanced Drive service** (`dependencies.enabledAdvancedServices`: `Drive`, v3), which the
   moves need (#132); pasted by hand, the same is Editor → Services `+` → Drive API, version
   v3, identifier `Drive` → Add. Its scope is the `drive` scope already declared.
5. **Script Properties** (Project Settings → Script Properties). One pair per region in use; the
   id of a folder is the last part of its Drive URL, after `/folders/`:

   | Property | Folder |
   | --- | --- |
   | `SOURCE_FOLDER_AFRICA` | `Attendance photos - Africa` in Ryan's My Drive |
   | `TARGET_FOLDER_AFRICA` | the Africa folder on the Shared Drive |
   | `SOURCE_FOLDER_ASIA` / `TARGET_FOLDER_ASIA` | the same for Asia |
   | `SOURCE_FOLDER_LATIN_AMERICA` / `TARGET_FOLDER_LATIN_AMERICA` | Latin America |
   | `SOURCE_FOLDER_TEMPLATE` / `TARGET_FOLDER_TEMPLATE` | the template's test folder |
   | `SOURCE_FOLDER_US` / `TARGET_FOLDER_US` | U.S, only if that form is re-enabled |
   | `RETENTION_DAYS` | not a folder: the Shared Drive's photo retention in days, `90` (none below 90); absent or blank, retention is off. Set it only as the retention plan's Rollout says (the trigger removed first, then a `previewMoves` read by Ryan) |

   With `RETENTION_DAYS` set, every target folder must be on one Shared Drive, none in the trash
   and none that drive's root; a value that is not a whole number of at least 90 (spaces trimmed)
   is refused like a bad folder (`CONFIG refused …`). Deleting it turns retention off from the
   next run. A region with neither property is skipped. Half a pair, the same id twice, no pair at all, a
   source folder not named exactly `Attendance photos - <Region>`, or a target folder not named
   exactly the region (`Africa`, `Asia`, `Latin America`, `U.S`, `Template`): the run refuses
   (`CONFIG refused …`) before it reads a subfolder or moves anything.
6. **Dry run.** In the editor, run `previewMoves`; accept Google's authorisation (Drive, and the
   trigger scope). Executions → its log: one line per region, `would move N, would merge N (…),
   waiting N, refused N, would remove N, would rescue N`, then the folder names; on the empty
   folders every count is 0 and no `CONFIG refused`. Nothing changes.

Then #63 for the template only (Ryan, in the builder): its Google Drive integration pointed at
`Attendance photos - Template`, and a test upload on it with its read-back (RUNBOOK "Photos",
steps 1-4). No regional form yet.

7. **First real run** (Ryan's go): after 10 minutes, `previewMoves` → `would move 1` naming the
   test subfolder; then run `moveSettledPhotos` once and check the log and both drives (RUNBOOK
   "Photo mover", Verify).
8. **The trigger** (Ryan's go): run `installTrigger`. It adds one time-driven trigger,
   `moveSettledPhotos` every 15 minutes; running it again changes nothing.
9. **The regional forms** (#63, Ryan's go; RUNBOOK "Photos", step 5), only after steps 7-8:
   one form at a time, its integration pointed at `Attendance photos - <Region>`, then the next
   run's log for that region (no `CONFIG refused`, no `UNKNOWN`; its first subfolder moved)
   before the next form.

## Stopping it

Run `removeTrigger`, or delete the trigger in the editor (Triggers, the clock icon). Nothing else
runs the mover. A removed subfolder is in My Drive's trash for 30 days: Drive → Trash → the
folder → Restore puts it back in `Attendance photos - <Region>`. Undo a move by moving its files
back into the emptied subfolder there (restored first if it was removed, or a new folder of its
name) by hand. That
move out of the Shared Drive needs **Manager** on it (Google, "How file access works in shared
drives", https://support.google.com/a/users/answer/12380484: "If you have Manager access to a
shared drive, you can move files and folders out of shared drive to My Drive"; no lower role is
named), so a Manager does it, or Ryan's role is raised for it (RUNBOOK "Photo mover", Rollback).

Retention alone is turned off by deleting the Script Property `RETENTION_DAYS`; the moves go on.
What retention trashed is in the Shared Drive's trash for 30 days, then Google deletes it for
good and nothing brings it back. Within those 30 days a Content manager of the Shared Drive (Ryan)
restores it: the Shared Drive → Trash → the item → Restore. Restore a trashed folder first, then
anything from it still in the trash, and see each back in place (where a restored item goes when
its folder is in the trash too is unverified: the retention plan's Context, c, and Rollback).
