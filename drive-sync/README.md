# drive-sync: the photo mover

Jotform's Google Drive integration writes only into the connected account's My Drive, and the
integration runs on Ryan's company account. This standalone Apps Script project, owned by that
same account, moves each submission subfolder (`<Club Name> <Attendance Date>`) from
`Attendance photos - <Region>` in Ryan's My Drive into that region's folder on the company Shared
Drive, once the subfolder has not changed for 10 minutes. It runs every 15 minutes on a
time-driven trigger. Plan: [docs/plans/2026-10-21-drive-photo-mover.md](../docs/plans/2026-10-21-drive-photo-mover.md);
procedure: RUNBOOK "Photo mover".

It is **not** the sheet's Apps Script (`appsscript/`): a Drive scope there would stop the
form-submit trigger until the owner re-authorises (CLAUDE.md rule 11). This project has its own
scopes, `drive` and `script.scriptapp` (the trigger), and nothing else.

What it does and never does:

- a whole subfolder moves (`Folder.moveTo`); when that name is already in the region folder once
  (a resubmission) its files move in one by one beside what is there, and a file whose name and
  size are both already there stays in My Drive (logged as kept). Nothing is ever replaced;
- two or more folders of that name on the Shared Drive: refused and logged, moved by hand;
- the `Attendance photos - <Region>` folders themselves stay: Jotform writes into them;
- it never shares, links, copies, trashes or e-mails a file. The photos show girls' faces; only
  the Shared Drive's members see them;
- the log (Executions) holds counts and folder names, never a file's name or contents.

Files: `Plan.gs` (the planner, pure, tested by `test/drive_sync_test.js`), `Mover.gs` (the entry
points), `appsscript.json` (time zone America/New_York, the sheet's; the two scopes),
`.clasp.json.example` (the clasp link template), `.claspignore`.

## Setup (once, Ryan)

The mover is set up first (Ryan, 2026-10-22): steps 1-6 need no form change and move nothing.
Its My Drive source folders (step 2) are the folders each form's Google Drive integration is then
pointed at (#63, RUNBOOK "Photos"); steps 7-8 follow a test upload on the template.

1. **The Shared Drive.** A company Shared Drive with one folder per region in use, named exactly
   `Africa`, `Asia`, `Latin America`, `Template` (and `U.S` only if that form is re-enabled):
   the mover refuses a target folder with any other name. Members: the named list only
   (the CEO and Ryan); never "anyone with the link". Ryan's company account is at least a
   **Content manager** (moving items in needs it; see the plan's Risks on moving folders).
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
   into the editor by hand (Project Settings → show the manifest).
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

   A region with neither property is skipped. Half a pair, the same id twice, no pair at all, a
   source folder not named exactly `Attendance photos - <Region>`, or a target folder not named
   exactly the region (`Africa`, `Asia`, `Latin America`, `U.S`, `Template`): the run refuses
   (`CONFIG refused …`) before it reads a subfolder or moves anything.
6. **Dry run.** In the editor, run `previewMoves`; accept Google's authorisation (Drive, and the
   trigger scope). Executions → its log: one line per region, `would move N, would merge N (…),
   waiting N, refused N`, then the folder names; on the empty folders every count is 0 and no
   `CONFIG refused`. Nothing changes.

Then #63 (Ryan, in the builder): each form's Google Drive integration pointed at its region's
source folder, template first, and a test upload on the template (RUNBOOK "Photos", steps 2-3).

7. **First real run** (Ryan's go): after 10 minutes, `previewMoves` → `would move 1` naming the
   test subfolder; then run `moveSettledPhotos` once and check the log and both drives (RUNBOOK
   "Photo mover", Verify).
8. **The trigger** (Ryan's go): run `installTrigger`. It adds one time-driven trigger,
   `moveSettledPhotos` every 15 minutes; running it again changes nothing.

## Stopping it

Run `removeTrigger`, or delete the trigger in the editor (Triggers, the clock icon). Nothing else
runs the mover. Undo a move by moving the subfolder back into `Attendance photos - <Region>` by
hand (RUNBOOK "Photo mover", Rollback).
