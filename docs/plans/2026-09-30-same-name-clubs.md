---
title: Clubs that share a name send "<club> - <partner>" to Salesforce
author: Claude (design workflow + two adversarial reviews, 2026-09-30)
status: accepted         # by Ryan 2026-09-30 (plan approval); every live step needs his go
created: 2026-09-30
intent: docs/intent/2026-09-01-club-picker.md (its constraint "question 5 stays the plain club name" is amended by Ryan's decision of 2026-09-30)
---

# Plan: clubs that share a name send "<club> - <partner>" to Salesforce

## Context
Salesforce matches an attendance submission to a club by question 5 (Club Name), exactly, ignoring
case, and creates a new account when nothing matches. Several clubs of different partners have the
same name, so Salesforce could not tell them apart. Ryan decided (2026-09-30): those clubs are named
"<club> - <partner>" in Salesforce and the form sends that same text. Nothing reaches Salesforce
today (connection off since 09-17); this must be live before the reconnect.

A read-only design and two adversarial reviews were done on 2026-09-30 (read-only: GETs, the Roster export, the repo at `e4b1670`). This plan is that design, changed
by Ryan's decisions below.

## Ryan's decisions (2026-09-30)
1. **One list.** Each same-name club is its own entry in the club list, e.g. `Ruby - Binti Network`.
   No Partner question: the typed Partner box is hidden on all five forms, and the unbuilt partner
   list (BACKLOG 45) is retired. (Side effect: the "Partner" line in the staff notification e-mail
   is blank from then on.)
2. **An existing club's name never changes; a new club may not take a name already in use.** A
   checker refuses a new club whose name another partner's club already has (below).
3. **Remove the two duplicates now**: YWOU "Shinning Stars" (15 girls, all also in YWOU "Shining
   Stars") and Reach All's old "SUPER GIRLS" (08-26; "SUPER GIRLS (MUTAKWA PRI SCH)" of 09-22 is the
   up-to-date roster). Claude does it, including deleting their emptied roster questions and the
   stale q158 through the API — a one-time exception to "tools never delete questions", for exactly
   9 questions that hold 0 attendance answers (checked).
4. Spelling always follows the sheet.

## The 7 Salesforce names (after the removals)
| Salesforce account = what the form sends | Form |
|---|---|
| `Angels Club - Abaana Community Outreach (ACO) Africa` | Africa |
| `Angels Club - Ready for Reading` | Africa |
| `Ruby - Binti Network` | Africa |
| `Ruby - Health Aid For All Initiative` | Africa |
| `Shining Stars - Seeds of Hope Foundation` | Asia |
| `Shining Stars - World Economy Skills and Agro Development (WESAD)` | Africa |
| `Shining Stars - Youth and Women Opportunities Uganda (YWOU)` | Africa |

Stay plain: `Shinning Stars` (Ready for Reading), `Super Girls` (Feminature Uganda Limited),
`SUPER GIRLS (MUTAKWA PRI SCH)` (Reach All), `Shining Star` (Rift Valley Reading Association) and
every other club. No Salesforce account for the two retired clubs. I pass this to the Salesforce
session (its list has 11 composites today).

## Step 0 — remove the two duplicates (first, right after approval; runner paused)
Prepared on 09-28 in `data/outreach_2026-09-28/pack/` (sets `YW-SHINING`, `RA-SUPER`).
1. `AUTO_SYNC_APPLY=0`. `pack/support/plan_retire.py YW-SHINING` and `RA-SUPER` (read-only pre-check:
   the exact Roster rows; stop on drift).
2. Sheet: `sheets_client.py export-all data/live_2026-09-30` (backup), then a scratch script as for
   Radiant Girls on 09-28: set those 35 rows `inactive` with `removed_date` 2026-09-30, re-read and
   compare, add the Audit row. No names printed.
3. Forms: `backup_forms.py` for all five, then `DELETE /form/{id}/question/{qid}` for q422 and q429 on
   Africa and the template and q158 on all five (9 deletes), re-read to confirm.
4. Sync by hand, template then each region (dry run → `--apply`): the rules for the deleted rosters
   go, the pickers lose the duplicate/stale entries, calcValues and guard terms follow, and the
   Partner-box gate ends for "Shinning Stars" and "Super Girls" (each now one club).
   `form_status` CLEAN + `--rendered` on each form; `auto_sync.py` dry run in-sync;
   `AUTO_SYNC_APPLY=1`.
5. Record it: DECISIONS (the delete exception), BACKLOG (duplicate sets done), close the matching
   ReviewQueue/pack items later with Ryan.

## What gets built — Part 1 (Python; the forms)
One string everywhere: picker option = calculation value = roster rule = club-guard term = question 5
= Salesforce account name. Question text (the roster's heading) stays the plain club name.
- **`glow/sync.py`** (new pure functions next to `read_roster_csv`): `SF_NAME_SEP = " - "`,
  `roster_pairs(csv)` (every partner+club, with status, all regions), `shared_club_names(pairs)`
  (names held by two or more partners; compared with the existing `glow.text.key`),
  `sf_club_name(club, partner, long)`, `sf_name_clashes(...)`.
- **`sync_attendance_form.py` `main()`**:
  - Read back, per existing roster, what its rule tests today: plain, or "<its text> - <a partner
    the Roster has for that club>". That form is **sticky**: the sync never flips an existing
    roster between plain and long on its own (so a namesake going inactive changes nothing).
  - `--same-name-switch` (by hand, once per form; the runner never passes it): existing rosters
    whose name is shared by two or more partners' **active** clubs (all regions — Asia's Shining
    Stars shares with Africa's) become long. The dry run lists each change: `! '<club>' (q…): Club
    Name (question 5, what Salesforce reads) changes from 'X' to 'Y'`.
  - **The checker, form side:** a club to be CREATED whose name another partner's club already has
    (any status, all regions) is **not created**; `! new club '<club>' (<partner>) has the name of
    <other partner>'s club - not added: give it a different name` and the rest of the run goes on.
  - Any other change of an existing club's question 5 (a rename, a partner respelling) is refused
    on `--apply` unless `--q5-change-ok` is given.
  - `build_conditions` is called with each roster's option text: a long-named roster gets a
    one-term rule (no Partner-box term); the "show Partner box" rules disappear; guard terms and
    calcValues follow the options as today. Refuse `|` or `{…}` in an option, two rosters on one
    option, and an option equal to another club's name.
  - Hide q331 (`question[hidden]=Yes`, after the conditions write) on every picker form once no
    rule shows it. `--partner-picker` exits with "retired 2026-09-30".
  - From the reviews: a read-back partner counts only if the Roster has that pair; exact partner
    match before the loose one; a partner mismatch with roster overlap ≥ 0.5 reuses the question
    instead of creating a sibling.
  - `--summary-json` gains `sf_names` (`[{qid, partner, club, value}]`), `sf_name_changes`,
    `same_name_refused`.
- **`tools/form_status.py`**: rosters grouped by tested value (not text); a tested value must be the
  roster's text or text + " - " + a partner the Roster has for that club; picker options = tested
  values; prints `same-name clubs: N rosters send '<club> - <partner>'`. `audit_picker`,
  `audit_club_guard`, `--rendered` unchanged.
- **`tools/auto_sync.py`**: the refused-new-club warning and the q5-change warning raise ATTENTION
  (evaluated before the "in-sync" return; only the q5-change one stops the region); a cross-region
  check that no two clubs send the same Salesforce name (from each region's `sf_names`).
- **`restore_conditions.py`**: refuses (unless `--force`) a snapshot whose picker/guard terms are
  not all current picker options (a pre-switch backup would block the same-name clubs).
- Tests in `test/python_test.py` (fictional names only): `SameNameRule`, `SameNameFlow` (replaces
  `PartnerPickerFlow`), updates to `ClubGuardFlow`, `FormStatusAudit`, `AutoSyncPlan`; a form
  without a picker keeps today's rules byte for byte.
- Docs: `docs/plans/2026-09-30-same-name-clubs.md` (committed first), DECISIONS (the rule; partner
  list superseded), RUNBOOK ("Club names two partners share" replaces "The partner list"; renaming a
  club or partner = rename the Salesforce account first; rollback is all forms together, fix-forward
  after the reconnect), ARCHITECTURE, BACKLOG (45 superseded; 48: the 10 bare-name Africa submissions
  are mapped by hand in a back-fill; new: delete the dead partner-list code, `rename_club.py` cannot
  rename the 7, a pick with an empty question 5 is blocked by the guard — watch), the 2026-09-01
  club-picker intent (amendment), CLAUDE.md rule 5 (one clause).

## Part 2 (Apps Script; its own push at a quiet moment, before the reconnect)
- **The checker, intake side** (`FormHandlers.gs`, next to the duplicate-club hold of 09-28,
  `newClubHoldReasons_` / `HOLD_PREFIX`): a new-club response whose club name (by `key_`) another
  partner's club already has — any status — is **held, not imported**, with a ReviewQueue item
  "Club name already used by <partner>'s club — ask for a different name" (RUNBOOK "Working the
  ReviewQueue" gets the issue; the Monday e-mail lists it).
- `Config.gs` `SF_NAME_SEP`, `RosterOps.gs` `sharedClubNames_` / `sfClubName_` (active rows, as the
  switch), parity-tested against Python; the Monday e-mail's "waiting to be created in Salesforce"
  lines print the exact account name.
- No new Google service, so no re-authorisation. Tests in `test/forms_logic_test.js`.

## How it gets built
A workflow in git worktrees off `main`: plan-doc commit → Part 1 and Part 2 as two parallel tracks
(different files) → `make check` → three adversarial reviewers per track (runtime correctness;
Salesforce/operations; tests and docs) → verify → fix → one integration branch → read-only proof
against the live forms (after Step 0). No live writes, no merge into `main` without Ryan's go.

## Rollout (each step Ryan's go; one `AUTO_SYNC_APPLY=0` window at a quiet hour)
1. Merge + push (GitHub check green).
2. Template: backup → dry run with `--same-name-switch` (7 name changes, options +4, Partner box
   hidden) → `--apply` → second dry run "nothing to do" → `form_status` CLEAN → `--rendered` →
   browser: type "Ruby" (two entries), pick one (its roster, no Partner question), two clubs (the
   guard), Chrome "Translate page", one test submission with a long name (question 5 exact).
3. Asia (1 change), Africa (6), then U.S and Latin America (Partner-box hide only); a phone-width
   look at the long "Shining Stars" entries.
4. `auto_sync.py` dry run in-sync → `AUTO_SYNC_APPLY=1`.
5. Apps Script push (Part 2).
6. The Salesforce session creates the 7 accounts from the live picker strings (`sf_names`); a
   read-only compare of account names with the form strings before the reconnect.

## Verification
- `make check` green (`CHECK PASSED`, real-data line) on the integration branch.
- Read-only proof before any write: dry runs match the expected changes (template 7, Africa 6,
  Asia 1, Latin America and U.S 0); `form_status` CLEAN before and after; `auto_sync.py` dry run;
  a fictional new "Ruby" under a third partner is refused by both checkers and leaves both existing
  Rubys untouched.
- After rollout: every form CLEAN, `--rendered` aligned, the 7 strings equal the Salesforce account
  names character for character, runner in-sync.
