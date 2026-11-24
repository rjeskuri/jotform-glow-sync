---
title: The photo folders already on the Shared Drive re-filed once under Region / Partner / Month
author: Claude (ticket #237, with Ryan's decisions of 2026-11-23)
status: proposed         # the code lands offline (#237); every live step waits on Ryan's go
created: 2026-11-23
intent: GLOW staff via Ryan, 2026-11-18 - the existing club folders grouped by partner and month like the new ones (#225); Ryan's decisions on ticket #237, 2026-11-23
---

# Plan: re-filing the existing photo folders by partner and month

<!-- Kept beside ticket #237. When the live steps are done: the Result, the status and `done:`,
     then `make docs-index`. -->

Since #225 ([plan](2026-11-19-photo-folders-partner-month.md)) the photo mover files each new
submission subfolder under `<Region>/<Partner>/<YYYY-MM>/` on the Shared Drive. The folders it
filed before then sit directly in the region folder, and their names carry no partner:
`<Club Name> <MM-DD-YYYY>` since 2026-10-30, the club name alone before that. Staff asked for
them to be grouped the same way. This plan moves each of them once, keeping its name and photos.

## Ryan's decisions (ticket #237, 2026-11-23)

- **Partner source: option A.** A repo tool reads the sheet's Roster and Partners tabs once and
  produces a club → partner list; the mover uses that list for this one-time re-filing only. The
  mover does not read the sheet, and no new OAuth scope is added to the mover project.
- **Folders with no date** (made before 2026-10-30, named by club only) go to
  `<Region>/<Partner>/undated/`.
- **A club whose partner is not found stays where it is** and is listed in the dry run with the
  reason.
- **Order:** #236 (question 331 filled) is live, then Ryan changes the integration naming (#225),
  then this.
- The existing folders are **moved** into their partner folder and keep their names: no renaming
  of old folders or files, and no follow-up ticket for it.
- Between the naming change of 2026-11-23 and its ` | ` fix, the integration named a few
  subfolders with spaces only, `<Partner> <Club Name> <MM-DD-YYYY> <Week>`; the re-filing
  recognises that shape too.

## What it does

Three pieces, all offline until the Rollout; `Plan.gs`, `Mover.gs` and `appsscript.json` are
unchanged (no new scope, no new service):

- **`tools/refile_list.py`** reads a Roster export and a Partners export and writes
  `RefileList.gs`, `const REFILE_LIST = [{"region", "partner", "club"}, ...]`, one row per club of
  the Roster (any status: old folders belong to clubs now inactive or retired), spelled as
  `glow.sync.roster_pairs` spells it, the partner string the Partner fill (#236) writes into
  question 331, so a re-filed folder lands in the partner folder new photos use. Its region is the
  club's Roster region (one row per region when its rows have two), else its partner's on the
  Partners tab, else blank (matched from every region). `--extra` adds rows by hand, e.g. for a
  club renamed since its folders were made. It prints counts only and refuses an `--out` inside
  the repository outside `data/`: the file holds the real club names.
- **`drive-sync/Refile.gs`**: `previewRefile` (the dry run) and `refileExisting` (the real run),
  one read and one plan (`planRefile_`, pure, tested offline) for both. It reads each region
  folder (`TARGET_FOLDER_<KEY>`) by listing, one folder per Drive call (#262, below), three
  levels deep, folder names only (no file's name is asked for), under the mover's script lock
  and time budget; a big region over several runs, its progress kept in the Script Properties.
- **The docs:** this plan, `drive-sync/README.md` ("Re-filing the existing folders"), RUNBOOK
  "Photo mover", DECISIONS 2026-11-23.

What a folder's name says (each name trimmed):

| Name | Where it goes |
| --- | --- |
| `<Partner> \| <Club> \| <MM-DD-YYYY> \| <Week>` (the layout, with its partner) | `<Partner>/<YYYY-MM>`, no lookup |
| ` \| <Club> \| <MM-DD-YYYY> \| <Week>` (the layout, partner blank) | the club's partner, `<YYYY-MM>` |
| `<Club> <MM-DD-YYYY>` (since 2026-10-30) | the club's partner, `<YYYY-MM>` |
| `<Partner> <Club> <MM-DD-YYYY> <Week>` (spaces only, 2026-11-23; the week may be blank) | the list's partner for that `<partner> <club>` pair, `<YYYY-MM>` |
| `<Club>` (before 2026-10-30) | the club's partner, `undated` |
| any of these with a date that is not a real one (`02-30-2026`) | stays: `bad-date` |

In a name without ` | ` the last date-shaped word is the date, the words before it the club
text, and every word after it is dropped (the week; also e.g. Drive's ` (1)`).

The club's partner: every list row offers its club, `<club> - <partner>` (question 5 of a club
two partners share), and both after `<partner> `, compared with case and spacing ignored; the
rows of the folder's own region first, every row when none of them has the name. One partner:
filed there. None: stays, `no-partner`. Two or more: stays, `ambiguous`, the partners named.

What holds a folder where it is (exact names: case and spaces count), each listed in the dry run
with its code and reason:

| Code | Means |
| --- | --- |
| `holds-folders` | it holds a folder: a partner folder, or not a photo folder; never moved. Also an empty folder named like a partner this run files into (one a cut-short run left): it is that partner folder, reused |
| `duplicate-name` | two or more folders of its name in the region folder: all stay |
| `partner-name` | a folder of files named like a partner this run files into: it and every folder for that partner in its region stay |
| `partner-folders` / `month-folders` | two or more partner (or month) folders of that name |
| `exists` | a folder of its name is already in that month folder |
| `no-partner` / `ambiguous` / `bad-date` | above |
| `unread` | (#262) Drive failed three times in the cycle to list it, or the partner or month folder it was planned into; the next cycle tries again |

The real run moves each folder itself, whole, by one `Drive.Files.update` within the Shared Drive
(`addParents` the month folder, `removeParents` the region folder): its id, name and photos stay
as they are. A missing partner or month folder is looked up by name first (the mover may have
made it since the read) and made by `Drive.Files.create` only when there is none, once per run.
Just before each move the folder is read by id (still a live folder of its name directly in the
region folder, or it is skipped: `moved or trashed (or renamed) since the read`, no error); after
it, read back (`REFILE_FAILED` unless it is in the month folder). The time budget is checked
before each folder, never between making its partner and month folders and its move; what it
does not reach waits for the next run (from the same plan), and a cycle after a complete one
moves nothing. Never a
configured folder, the Shared Drive's root or anything in the trash; nothing renamed, trashed,
shared, copied or deleted.

The log, per region: `<Region>: [would ]refile N, stays M (<code> n, …)`, then one line per folder
directly in the region folder by name, `[would ]refile "<name>" to <Region>/<Partner>/<YYYY-MM |
undated>` or `stays "<name>": <code>: <reason>`; after the real run `done: N folder(s) moved, M
partner or month folder(s) made, K skipped (moved or trashed since the read), F failure(s)`; per
region left for later `TIME_BUDGET: <Region>: <n> folder(s) left to read` (or `left to move`),
and `cycle complete` when nothing is left.
Folder names (club, partner, date) and counts only, never a file's name.

## The dry run refused for shared drive membership (2026-11-24, #262)

- **What happened:** with the code of #237 and `RefileList` (384 clubs) pasted and the trigger
  installed, `previewRefile` stopped in the first region with `GoogleJsonResponseException: API
  call to drive.files.list failed with error: The attempted action requires shared drive
  membership.` (`listSharedDrive_` ← `readRefileRegion_`). Nothing was read in full, planned or
  moved.
- **Why:** the account that runs the mover reaches the region folders through folder sharing and
  is not a member of the Shared Drive. Its first listing, `'<region>' in parents` (one folder),
  succeeded; the next one named up to 20 folders joined with `or`, and Drive answers a query
  that names more than one folder only to a member of the drive.
- **The fix (Ryan, 2026-11-24: read folder by folder, a slower run is fine, the account is not
  added to the drive):** every listing names one folder, `'<id>' in parents` ANDed with
  `trashed` / `mimeType` / `name` terms only, with `corpora` and `driveId` as the listing that
  succeeded sent them. That is one Drive call per folder, so a big region takes several runs: the
  re-filing keeps what a run read (and, for `refileExisting`, the plan's moves left) in the
  Script Properties (`REFILE_STATE_PREVIEW_*`, `REFILE_STATE_APPLY_*`; deleted at the end, no
  other property touched) and the next run carries on. The plan of a region read in full is the
  same as before (same targets, same stay codes); each region's plan is logged by the run that
  completes its read, and moves are made only from such a plan.

## Rollout (live; every step on Ryan's go)

Before it: #236 live, and the integration naming changed on the forms (the #225 plan, Rollout
steps 2-4: the live project's `Plan.gs` and `Mover.gs` are #225's).

1. **The exports** (read-only): `python3 tools/sheets_client.py export Roster
   data/roster_<date>.csv` and `python3 tools/sheets_client.py export Partners
   data/partners_<date>.csv`.
2. **The list:** `python3 tools/refile_list.py --roster data/roster_<date>.csv --partners
   data/partners_<date>.csv --out data/RefileList.gs`. It prints the counts (rows, clubs, the
   rows with a Roster region, with the Partners tab's, with none); open the file and look over
   the rows (club and partner names, no girl's name).
3. **The paste** (the company account, the `GLOW photo mover` project): `removeTrigger`; add two
   script files, `Refile` (the repo's `drive-sync/Refile.gs`, whole) and `RefileList`
   (`data/RefileList.gs`, whole); save; `installTrigger`. The manifest is unchanged (no new scope,
   no new service). The script lock keeps the mover's runs and the re-filing apart.
4. **The dry run:** `previewRefile`, **repeated until it reports every region read**: a run that
   has not read a region in full logs `TIME_BUDGET: <Region>: <n> folder(s) left to read, about
   <k> more run(s) at this run's pace` (n falls every run; `not read this run` for a region
   waiting its turn); the run that reads a region's last folders logs its plan, per region the
   counts, then every folder directly in the region folder with its target or its code and
   reason. Run it again until a run logs `cycle complete` and no `TIME_BUDGET` line. The plan is
   spread over those runs' logs (Executions, each run's log). Nothing changes.
5. **Ryan reviews the dry run** (the Definition of done): the targets look right, and each
   folder that stays has a reason he accepts. A club renamed since its folders were made
   (`no-partner`): a row in an `--extra` CSV (`region,partner,club`), step 2 again with `--extra`,
   and only `RefileList` replaced in the project, then step 4 again (a changed `RefileList` drops
   what the runs kept: the read starts again). `ambiguous`, `bad-date` and the holds are moved by
   hand or left, as Ryan decides. The counts (no names) go in the Result.
6. **The real run:** `refileExisting`, **repeated**: first as in step 4 (`TIME_BUDGET … left to
   read`, nothing moved); the run that completes a region's read logs its plan without `would`
   and starts its moves; the runs after it go on with them (`TIME_BUDGET: <Region>: <n>
   folder(s) left to move`) without reading that region again; each run ends `done: N folder(s)
   moved, …, 0 failure(s)`. Run it again until a run logs `cycle complete` and no `TIME_BUDGET`
   line; then go on running it (a new cycle reads again, and re-files what appeared or was
   renamed meanwhile) until such a run **moves nothing and reports no `TIME_BUDGET`**.
7. **The read-back:** `previewRefile` again, repeated as in step 4 until `cycle complete`:
   `would refile 0` in every region, the stays as reviewed. On the Shared Drive, a few re-filed
   folders opened under `<Region>/<Partner>/<YYYY-MM>` and `undated`, their photos inside.
8. **The clean-up:** delete the `RefileList` and `Refile` script files from the live project
   (Ryan); the trigger keeps running `moveSettledPhotos`. Delete `data/RefileList.gs`.
9. **The Result** below: the dates (UTC), the counts per region (re-filed, stays per code),
   `Live: <what, when UTC, Ryan's go>`; status `done` with `done:`; `make docs-index`.

## Rollback

- Nothing is deleted or renamed: each moved folder keeps its id, its name and its photos. To
  undo a move, move the folder back from `<Region>/<Partner>/<YYYY-MM>/` into the region folder
  by hand on the Shared Drive (a move within the Shared Drive: Content manager, Ryan's role). The
  partner and month folders the run made stay; empty ones can be left or trashed by hand.
- Stopping midway: do not run `refileExisting` again, and delete `Refile` and `RefileList` from
  the project (step 8). Nothing runs them on a trigger.
- Retention (#185) is unaffected: a folder's move changes neither its nor its photos' creation
  time, from which their due date is counted.

## Risks

- **A folder filed under the wrong partner:** a club name the list gives one partner, while the
  folder belongs to another partner's club of that name in the same region. The dry run shows
  every target before anything moves (step 5); a wrong one is moved back by hand (Rollback).
- **Clubs renamed since their folders were made** are `no-partner` and stay: `--extra` places
  them (step 5).
- **A large region:** one Drive call per folder (#262), so a region of thousands of folders
  takes several runs (`TIME_BUDGET … left to read`, with the runs left); a region is planned only
  once read in full, and moved only from that plan. What the runs keep is about 40 bytes per
  folder read and 60 per planned move, of the Script Properties' 500 KB (shared by a dry-run and
  a real-run cycle under way at once): some thousands of folders fit. A folder Drive will not
  list is `REFILE_FAILED` (the run ends with an error, the next tries again); at the third
  failure in a cycle it stays where it is (`unread`), and so does every folder planned into it.
- **The mover's own trigger** runs between the re-filing's runs: one script lock; both find the
  partner and month folders by name and make a missing one, so neither makes a second (a
  partner or month folder the plan found is re-read before a move into it; one the mover made
  since the read is found by name before any is made).
- **A run cut short** after making a partner folder and before its move leaves an empty partner
  folder: the next run reuses it (`holds-folders`), it never holds that partner's folders.
- **Privacy:** `RefileList.gs` holds the real club and partner names: `data/` only, never
  committed (the tool refuses an `--out` in the repository outside `data/`), deleted from the
  project and from `data/` afterwards. The log carries folder names and counts; the read never
  asks for a file's name.

## Proof

Offline, on the branch: `node test/drive_sync_refile_test.js` and `python3 -m unittest
refile_list_test` (from `test/`), `harness-red run`; `node test/drive_sync_test.js` and
`node test/drive_sync_layout_test.js` unchanged and green. Live: step 4's log (the healthy
`<Region>: would refile N, stays M (…)` lines), step 6's `done: …, 0 failure(s)`, step 7's
`would refile 0`.

## Result

<!-- To fill: each live step with its date (UTC) and counts (no names), `Live:` -->

- 2026-11-24: step 3 done (the push of #237 and `RefileList`, 384 clubs; trigger installed).
  Step 4 stopped in the first region, nothing moved: the membership error above; fixed by #262,
  then step 3's push again and step 4 repeated.
