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
  folder (`TARGET_FOLDER_<KEY>`) by listing, three levels deep, folder names only (no file's name
  is asked for), under the mover's script lock and time budget.
- **The docs:** this plan, `drive-sync/README.md` ("Re-filing the existing folders"), RUNBOOK
  "Photo mover", DECISIONS 2026-11-23.

What a folder's name says (each name trimmed):

| Name | Where it goes |
| --- | --- |
| `<Partner> \| <Club> \| <MM-DD-YYYY> \| <Week>` (the layout, with its partner) | `<Partner>/<YYYY-MM>`, no lookup |
| ` \| <Club> \| <MM-DD-YYYY> \| <Week>` (the layout, partner blank) | the club's partner, `<YYYY-MM>` |
| `<Club> <MM-DD-YYYY>` (since 2026-10-30) | the club's partner, `<YYYY-MM>` |
| `<Partner> <Club> <MM-DD-YYYY> <Week>` (spaces only, 2026-11-23; the week may be blank) | that partner, `<YYYY-MM>` (the date: the last date-shaped word) |
| `<Club>` (before 2026-10-30) | the club's partner, `undated` |
| any of these with a date that is not a real one (`02-30-2026`) | stays: `bad-date` |

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

The real run moves each folder itself, whole, by one `Drive.Files.update` within the Shared Drive
(`addParents` the month folder, `removeParents` the region folder): its id, name and photos stay
as they are. A missing partner or month folder is made by `Drive.Files.create`, once per run.
Just before each move the folder is read by id (still a live folder of its name directly in the
region folder, or it is skipped: `moved or trashed (or renamed) since the read`, no error); after
it, read back (`REFILE_FAILED` unless it is in the month folder). The time budget is checked
before each folder, never between making its partner and month folders and its move; what it
does not reach waits for the next run, and a re-run after a complete run moves nothing. Never a
configured folder, the Shared Drive's root or anything in the trash; nothing renamed, trashed,
shared, copied or deleted.

The log, per region: `<Region>: [would ]refile N, stays M (<code> n, …)`, then one line per folder
directly in the region folder by name, `[would ]refile "<name>" to <Region>/<Partner>/<YYYY-MM |
undated>` or `stays "<name>": <code>: <reason>`; after the real run `done: N folder(s) moved, M
partner or month folder(s) made, K skipped (moved or trashed since the read), F failure(s)`.
Folder names (club, partner, date) and counts only, never a file's name.

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
4. **The dry run:** `previewRefile`. Executions → its log: per region the counts, then every
   folder directly in the region folder with its target or its code and reason. Nothing changes.
5. **Ryan reviews the dry run** (the Definition of done): the targets look right, and each
   folder that stays has a reason he accepts. A club renamed since its folders were made
   (`no-partner`): a row in an `--extra` CSV (`region,partner,club`), step 2 again with `--extra`,
   and only `RefileList` replaced in the project, then step 4 again. `ambiguous`, `bad-date` and
   the holds are moved by hand or left, as Ryan decides. The counts (no names) go in the Result.
6. **The real run:** `refileExisting`. Its log repeats the plan without `would`, then `done: …, 0
   failure(s)`. Run it again until a region line reads `refile 0` everywhere (a `TIME_BUDGET`
   line means the run stopped in time; the next one carries on).
7. **The read-back:** `previewRefile` again: `would refile 0` in every region, the stays as
   reviewed. On the Shared Drive, a few re-filed folders opened under
   `<Region>/<Partner>/<YYYY-MM>` and `undated`, their photos inside.
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
- **A large region not read in time:** past half the run's budget a region not read in full is
  not planned (`TIME_BUDGET`); the read lists folders in batches, so this is not expected. Run
  the entry point again.
- **The mover's own trigger** runs between the re-filing's runs: one script lock; both find the
  partner and month folders by name and make a missing one, so neither makes a second.
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
