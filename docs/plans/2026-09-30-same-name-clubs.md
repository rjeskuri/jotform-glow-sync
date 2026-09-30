---
title: Clubs that share a name send "<club> - <partner>" to Salesforce
author: Claude (design workflow + two adversarial reviews, 2026-09-30)
status: in-progress      # accepted by Ryan 2026-09-30; Step 0 and the forms (Part 1) are live (Results below); open: the Apps Script push (Part 2), the seven Salesforce Accounts
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

## Result — Step 0 (2026-09-30, with Ryan's go)
- Pre-check `plan_retire.py YW-SHINING RA-SUPER`: 35 rows OK, no drift. Sheet backup
  `data/live_2026-09-30/`. Roster `G5090:G5104` and `G5164:G5183` set `inactive`, `I…` = 2026-09-30
  (70 cells written and re-read identical), two Audit `deactivateRows` rows.
- Form backups `questions-` / `properties-2026-09-30T1550.json` on all five. Nine questions deleted
  (each re-checked first: type, text, option count, the partner its rule named, 0 answers in every
  submission): q422, q429, q158 on the template and Africa; q158 on Asia, Latin America and U.S.
- Sync by hand on all five, straight after: pickers template 359 → 358, Africa 216 → 215, Asia
  96 → 95, Latin America 39 → 38, U.S 12 → 11; rules 401 → 396, 257 → 252, 127 → 126, 70 → 69,
  43 → 42. "Shinning Stars" (Ready for Reading, q421) and "Super Girls" (Feminature Uganda Limited,
  q428) are single rosters now, without the Partner-box gate. A second dry run: nothing to do.
- `form_status --rendered`: every form CLEAN, every picker option aligned, rosters = the Roster's
  clubs (362 / 218 / 95 / 38 / 11). `AUTO_SYNC_APPLY=1`; runner apply run 36680865174 in-sync.
- Left on the forms sharing a name: Angels Club ×2, Ruby ×2, Shining Stars ×2 (Africa) + ×1 (Asia)
  = the 7 of this plan.

## Build notes — Part 1

Built 2026-09-30 on branch `wf6/same-name-forms` (Python only; `appsscript/` and
`test/forms_logic_test.js` untouched — Part 2's). Nothing was written to Jotform, the sheet or
Salesforce. `make check` green; 249 Python tests.

### What is where
- `glow/sync.py`: `SF_NAME_SEP`, `roster_pairs` (`{(partner, club): active}`, any status, all
  regions), `club_partners`, `shared_club_names(pairs, active_only=False)`, `sf_club_name(club,
  partner, long)`, `long_name_partner` (the read-back of a long name's partner: the club's own text
  stripped as a prefix, never a split), `sf_name_clashes((value, who) pairs)`.
- `sync_attendance_form.py` `main()`: the read-back (`current_value`, `current_partner_of`, `gated`,
  `sends_now`), the matching (`claim`, exact partner → loose → roster overlap, each step over every
  entry), `option_of` (what each roster's rule tests), the checker, the refusals, `hide_box`,
  `--summary-json` `sf_names` / `sf_name_changes` / `same_name_refused`. `build_conditions` itself
  is unchanged apart from its docstring: it is called with `option_of`.
- `tools/form_status.py`: `tested_values`, `audit_rules(questions, conditions, partners_of=None)`,
  `load_partners`, the picker-vs-tested-texts check, the `same-name clubs:` and `partner box:` lines.
- `tools/auto_sync.py`: `SF_NAME_CHANGE`, `SAME_NAME_REFUSED`, `q5_changes`, `refused_clubs`,
  `name_clashes`, `Run.check_names`; every existing pattern (`CREATE_RX` … `GUARD_RX`) unchanged.
- `restore_conditions.py`: `stale_club_terms`, `--force`.
- Tests: `SameNameRule`, `SameNameFlow` (replaces `PartnerPickerFlow`; `PartnerListRunbook` went with
  its RUNBOOK section), `ClubGuardFlow` on the switched form, `FormStatusAudit`, `AutoSyncPlan`,
  `RestoreConditionsGuard`, `SameNameRunbook`.

### Deviations from the plan, and why
1. **The picker's entries are read back too, not only the rules** (`sends_now`). When the rules
   test a text the picker does not list, the entry the picker lists for that roster (its long
   name, else its plain one) is what the club sends today. Without it, a conditions backup
   restored over a switched picker, or a switch apply that stopped between the picker write and
   the rules write, would have made the next unattended run take the picker back to the plain
   names (a picker update is a change the runner applies). With it the sync plans only the
   rules rewrite - which the runner does not apply on its own: it raises ATTENTION (review
   fixes, below), and the rules are rebuilt by a hand `--apply`, or by the runner's next apply
   for a roster change in that region. Test:
   `test_the_picker_says_what_a_club_sends_when_the_rules_are_older`.
2. **A long name whose partner the Roster no longer has** stays long only when the club's name is
   one two partners have ever had (the partner was respelled: a question-5 change, listed);
   otherwise the roster is plain (a club renamed from "X - Y" to "X").
3. **The checker refuses three more cases than the plan names**, all "not added", the run goes on:
   a new club whose name is the text of a roster already on the form; one whose name is what a
   roster on the form sends; one whose name is the long name of any club in the Roster whose name
   is shared ("Stars - Partner One" as a club's own name). The plan's "refuse an option equal to
   another club's name" is a hard stop only for a roster that BECOMES long in the run; a roster
   that already sends its long name is never stopped by a newcomer (else one bad enrollment in
   another region would fail that region's every run).
4. **No sibling is ever created**, on any form: the old "same name, different partner → create a
   second, partner-gated roster" path is gone (the checker refuses it), on a form without the
   picker too. Such a form otherwise keeps today's rules byte for byte (tested), and
   `--same-name-switch` is refused on it.
5. **The loose partner match is also skipped** when the partner in a roster's rule is, exactly,
   another partner the Roster has for that club name ("Partner One" inside "Partner One Trust"):
   beyond the plan's "exact before loose".
6. **The partner list**: besides `--partner-picker`, a form carrying a `partnerPicker` question is
   refused (the design's line; no form has one). `main()`'s list block was unreachable after
   that and is removed; `form_status` says one thing about such a form ("retired … delete it")
   instead of auditing it. The helpers (`PARTNER_PICKER_PROPS`, `partner_choices`,
   `build_conditions`' `partner_field`, `partner_picker` / `partner_fields`, the runner's
   `PARTNER_PICKER_RX`, the branches in `rename_club.py` and `add_translations.py`) stay for
   BACKLOG 50.
7. **`sf_names` lists every roster**, not only the long ones (the cross-region check needs the
   plain names); a club not created yet (a dry run) has `qid: null`. `sf_name_changes` entries
   carry `switch: true|false`.
8. **The cross-region check also covers two clubs of one region**, so until a form is switched the
   runner reports the names its same-name rosters share on every run (exit 2): a decision for
   Ryan, below.
9. **`restore_conditions.py` refuses in its dry run too**, and the snapshot's terms are compared
   exactly (a multi-select compares case).
10. **Not in the plan's file list, changed anyway**: `tools/rename_club.py` (only its printed next
    steps: the Salesforce rename and `--q5-change-ok`), `glow/links.py` (a docstring), the
    `live-systems` and `sync-preview` skills (one paragraph each). `form_status` also prints a
    `partner box:` line and lists two questions of one text as duplicates only while they test
    the same text (BACKLOG 23).

### Known behaviour worth knowing before the rollout
- **Older code un-switches a form unattended.** Read in memory on the live data: the code at
  `2a1781b`, run on a switched form, plans `UPDATE club picker (… calcValues, options)` and
  `REPLACE conditions` back to the plain names, within the bands, no warning. So `main` must carry
  this code before any form is switched, and no checkout without it may `--apply` afterwards (the
  RUNBOOK and the `live-systems` skill say so). The same fact is the rollback.
- **The q331 hide needs no flag.** Asia, Latin America and U.S plan it on a plain dry run today.
  The runner does not count it as a change, but its next apply on such a form (any roster change)
  carries it.
- **Between the merge and the switch the runner exits 2 on every run** (the cross-region check:
  three names are sent by two or three clubs today). Merge and switch in one sitting, or expect
  GitHub's failure e-mail per run until then.
- **A refused new club after a runner apply**: the verify step then reports the club as missing
  from the form (or its name's roster as differing), so that region reads `applied-with-problems`
  on top of the refusal's own ATTENTION until the club is renamed (the RUNBOOK and both
  ATTENTION texts say so since the review fixes; the way out is `rename_club.py --sheet-only`).
- **A form built from scratch cannot create the seven rosters** (each is "a new club whose name
  another partner's club has"): build a form by cloning the template (BACKLOG 51).
- **`form_status` without `--roster`** judges long names against the stale default Roster
  (BACKLOG 32): pass the fresh export, as the runner does.
- **For Part 2**: the Python side compares names with `glow.text.key` (whitespace, case);
  `key_` in Apps Script also drops invisible characters (BACKLOG 28, a known divergence: say
  which one the mirror follows rather than fixing either side silently). The switch goes by
  ACTIVE clubs; the new-club check by every club, any status.

### The read-only proof (2026-09-30, about 16:45-17:15 JST)
A fresh Roster export each time (6,946 rows, 6,847 active; 364 clubs, 362 active; read after the
two duplicates were retired), kept in the session's scratch directory and deleted afterwards.
Jotform: GETs and the tools' dry runs only. Counts, qids, club and partner names only.

**The Roster.** Five names are held by two partners when every status counts, three when only
active clubs do: exactly the plan's seven clubs. `Shinning Stars` (Ready for Reading) and
`Super Girls` (Feminature Uganda Limited) each have one retired namesake and stay plain. No
club or partner name holds `|` or `{`.

**The sync's dry run, without the flag** — no question-5 change on any form:

| Form | Plan |
|---|---|
| Template | nothing to do (7 rosters still told apart by the Partner box) |
| Africa | nothing to do (6 such rosters) |
| Asia, Latin America, U.S | `HIDE partner textbox (q331: no rule shows it; …)` only; conditions unchanged |

**With `--same-name-switch`** — the `! '<club>' (q…): Club Name (question 5, what Salesforce
reads) changes from 'X' to 'Y'` lines:

| Form | `!` lines | Picker entries | `conditions:` | Calls |
|---|---|---|---|---|
| Template | 7 (q150, q173, q234, q334, q335, q411, q420) | 358 → 362 | 384 kept, 9 new, 12 dropped | `UPDATE club picker (362 clubs: calcValues, options)`, `REPLACE conditions (393 rules)`, `HIDE partner textbox` |
| Africa | 6 (q173, q234, q334, q335, q411, q420) | 215 → 218 | 241 kept, 8 new, 11 dropped | `UPDATE club picker (218 clubs: …)`, `REPLACE conditions (249 rules)`, `HIDE partner textbox` |
| Asia | 1 (q150) | 95 → 95 | 123 kept, 3 new, 3 dropped | `UPDATE club picker (95 clubs: …)`, `REPLACE conditions (126 rules)`, `HIDE partner textbox` |
| Latin America, U.S | 0 ("nothing to switch") | 38, 11 | unchanged | `HIDE partner textbox` only |

The seven new texts are the table in "The 7 Salesforce names" above, character for character.

**`form_status --roster <fresh>`**: all five forms CLEAN today (template 362 rosters, Africa 218,
Asia 95, Latin America 38, U.S 11; every region 0 missing, 0 differ); `same-name clubs: 0`;
`partner box:` shown by 3 rules on the template and Africa, visible with no rule on the other
three.

**`auto_sync.py` dry run** (`--roster <fresh>`, its files in the scratch directory): Africa,
Asia, Latin America, U.S all `in-sync`; one ATTENTION, the cross-region check: `Angels Club` (2
clubs), `Ruby` (2), `Shining Stars` (3, one of them on Asia) — what the switch resolves. Exit 2.

**The checker.** On a copy of the export with three fictional clubs of a fictional partner
("Partner Three (fictional)"): a new `Ruby` in Africa is refused (`! new club 'Ruby' (…) has the
name of Binti Network's club and Health Aid For All Initiative's club - not added: give it a
different name`), both existing Rubys untouched (0 question-5 changes), and the unrelated fictional
club in the same run is still created (`CREATE roster`, picker 215 → 216). A new `Shinning  stars`
in Asia is refused too (the name of an Africa club, and of a retired one; case and spacing
ignored). Through the runner: Africa `dry-run - would apply: 1 create(s) …; 1 new club(s) not
added (name in use)`, Asia `in-sync - 1 new club(s) not added (name in use)`, one ATTENTION each.

**The switch, simulated in memory.** Each live form was read once into memory and the sync's dry
run (never `--apply`) was run against a stand-in that applies the planned writes to its own copy
only. After the switch, on all five: `form_status` CLEAN (same-name rosters 7 / 6 / 1 / 0 / 0,
guard terms = picker entries, q331 hidden, 0 missing, 0 differ); the next run, with or without
the flag, plans nothing and warns of nothing; the cross-region check finds no clash; a fictional
new `Ruby` is still refused with no change to the two long-named ones; `restore_conditions.py`
would refuse each form's pre-switch conditions (`Angels Club`, `Ruby`, `Shining Stars`; on Asia
`Shining Stars`). And the rollback: the code from before this change, run the same way on the
switched template, Asia and Africa, puts the plain names and the Partner-box rules back in one
run and then plans nothing (q331 stays hidden: un-hide it by hand).

Not proved here, because it needs a browser or a write: how the long entries look and search in
the picker (phone width, typing the partner), Chrome "Translate page" on a long name, and one
test submission's question 5 — the rollout's browser checks.

## Review fixes — Part 1 (2026-09-30, after three adversarial reviews and their verification)

On the same branch, Python only. Nothing was written to Jotform, the sheet or Salesforce.
`make check` green; 264 Python tests. Every fix has a test that fails without it (checked by
removing each fix on a scratch copy: 30 single-line mutants, all caught).

### What changed, and why
1. **A plain roster's owner is read from the Roster** (a deviation: the plan has each roster's
   partner read from its rule only). A plain roster's rule names no partner, so the matching
   went by the NEW roster alone. Two things followed. A retired club's question stays on the
   form, and another partner's new club of that name — one sheet entry, one question — simply
   took it over: its girls on the retired club's question, their attendance on that club's
   Salesforce Account, no "not added" line, and with a single shared name no warning at all
   (decision 2's check only looked at clubs to be created). And while a refused namesake sat in
   the Roster, an existing club whose roster changed by more than half was itself refused as
   "new". Now, for a roster whose rule names no partner and whose name two or more partners
   have in the Roster (any status), the owner is the partner whose rows of ANY status list the
   most of the girls the question holds — at least half of them, and more than any other
   partner's (`glow.sync.roster_names`; `inferred` in `main()`). The owner's entry claims the
   question whatever its new roster is; another partner's entry goes to the same-name check
   unless it lists at least half the same girls (the same club moved: claimed, with a line that
   says where the owner came from). A tie, or no evidence, names no owner and everything goes
   on as before. The owner is never written into a rule, into `sf_names`, or into a
   typed-Partner rule on a form without the picker (that path still refuses, byte for byte).
2. **The roster-similarity step takes the best match first** over every open entry and question
   (overlap, then shared names), not the first partner in name order: a duplicate enrolment
   under a partner that sorts first no longer takes the existing club's question.
3. **Rules older than the picker are said, and are ATTENTION for the runner.** Deviation 1 made
   such a form plan only `REPLACE conditions`, which the runner does not count: it read
   `in-sync` on every run while those clubs' rosters never showed and the club guard blocked
   their mentors. The sync now prints, per roster, `! '<club>' (q…): its rule tests '<X>', which
   the Club picker does not list …` (never for a roster with no rule at all: a failed apply's
   new club is finished silently, as before), and the runner reads such a region as `attention`
   instead of `in-sync`. It still applies no rules-only write on its own, and it is no band: a
   region with a roster change is applied as usual, which rewrites the rules.
4. **`--same-name-switch` refuses to leave a retired namesake on the plain entry.** A roster not
   in the export keeps what it sends; beside two rosters going long it would be alone on the
   familiar name, showing a retired club's girls. The switch (dry run too) exits and names the
   question; the runner, which never passes the flag, is unaffected.
5. **A new club about to be refused does not count toward the switch.** It sits active in the
   Roster until it is renamed, and made an existing one-of-a-kind club long for nothing.
6. **`tools/rename_club.py` never relabels another partner's roster question.** The documented
   way out of a refusal was "rename it with `rename_club.py`" — which finds a question by its
   text and so planned to relabel the OTHER partner's question on the region's form and the
   template (before this branch the newcomer had its own, partner-gated question). Now, when
   another partner has a club of the old name, a question at least half of whose girls are not
   this club's Roster rows (any status) is refused, with `--sheet-only` named as the way; the
   printed next steps fit a club the next sync creates. The RUNBOOK and the runner's ATTENTION
   give the command with `--sheet-only`.
7. **Docs that described the retired design or promised a repair the runner does not make**:
   RUNBOOK (the part-moved club, "Restoring conditions", the refusal's `applied-with-problems`,
   the Partner-box hide not named in SyncLog, the checks before the switch), BACKLOG 40 / 50 /
   51, ARCHITECTURE, DECISIONS, README (one sentence: outside the plan's doc list), the
   partner-box plan's status (superseded), the `sync-preview` skill.
8. **Test pins the reviews asked for** (no production change): exact before loose on a rule
   whose partner the Roster does not have; a roster created by an apply gets its picker entry,
   rule, Contact_IDs operand and `sf_names` line in the same run; a partner's own " - " is
   never split; `main()` makes the cross-region check and exits 2; and five single guards
   (no hide on a picker-less form, the switch flag is no consent to a long-to-long change, the
   checker's two extra branches, a pre-guard snapshot in `restore_conditions`, the question's
   own partner's region).

### Proposed and not taken
- Refusing in the single branch whenever another partner has the name and the new roster
  overlaps by less than half: it would refuse an owner's own club at its next cohort (the two
  live plain clubs with a retired namesake).
- Counting the rules-only rewrite as a change the runner applies: its first unattended
  rules-only write, on an inference. ATTENTION instead.
- Dropping a verify line whose club name a refusal lists: the check goes by name, so it would
  also hide a real drift of the existing namesake's roster. The ATTENTION explains the line
  instead.
- Giving the switch's leftover its long name from the partner in its rule: the tool would
  pick a Salesforce name for a club that is not in the export. The refusal is complete on its
  own.
- Naming the Partner-box hide in SyncLog's `detail` (parsing code for a one-time, hand-applied
  transition): the RUNBOOK says where the line is.
- README's refusal example ("an ambiguous club name with no partner information anywhere"):
  still true of a form without the picker; left.

### Known behaviour after the fixes
- **No evidence, no owner.** When the girls a question holds are not in the Roster under any
  partner's club of that name (rows deleted, names respelled in place), the old matching
  applies: an existing club with a mostly new roster AND a namesake in the same region can
  still be refused as new, and a club whose retired namesake's rows were deleted is simply the
  only club of that name. Fewer than half the girls is no evidence either.
- **The same girls under two partners** (a full duplicate enrolment) tie: the first partner in
  name order keeps the question, as before. No form write follows from the tie; the "new club"
  line may name the wrong one of the two.
- **An owner read from the Roster is not the form's word**: `sf_names` gives no partner for a
  question that is not in the export and whose rule names none, so the cross-region check
  still tells such a question apart by its id.
- **A refused club of another region still counts toward a regional form's switch** (one run
  cannot tell it from a real namesake on another form): the RUNBOOK's check before the switch.
  On the template, and for a refused club of the form's own region, it is left out. One of the
  seven whose question were missing from a form would be left out the same way: the `!` count
  is then one short of the table, which is a stop.
- **The enrollment-CSV mode** (no `--roster`) has no history and reads no owner.

### The read-only proof of the fixes (2026-09-30, about 18:30 JST)
A fresh Roster export (6,946 rows, 6,847 active; 364 clubs, 362 active), the five forms read
once each (GETs), and every run in memory (the sync's dry run against a stand-in that holds
that read); all of it in the session's scratch directory and deleted afterwards. Counts, qids,
club and partner names only.

- **Today's data: nothing changes.** All ten plans (each form, with and without
  `--same-name-switch`) are identical to the branch before the fixes — calls, warnings,
  `sf_names`, `sf_name_changes`, `same_name_refused`: template 7 `!` lines, Africa 6, Asia 1,
  Latin America and U.S 0; without the flag nothing on the template and Africa, the
  Partner-box hide alone on the other three.
- **Fictional variants of the Africa form** (rows of a fictional partner added to a scratch
  copy of the export; `Shinning Stars`, q421, plain, with its retired namesake):
  | Variant | Before the fixes | After |
  |---|---|---|
  | its owner's rows inactive + a fictional partner's new club of that name, no shared name | `UPDATE roster … (q421, 12 girls)`, the "shares NO names" band only | no call; the new club "not added"; q421 kept |
  | the same, one shared name | `UPDATE roster … (q421, 13 girls)`, no warning: applied unattended | no call; "not added"; q421 kept |
  | a refused namesake in the Roster + 13 of the owner's 20 girls replaced (old rows inactive) | no call; BOTH clubs "not added"; q421 "matched no partner" | `UPDATE roster … (q421, 20 girls)`; only the fictional club "not added" |
  | the owner's whole roster replaced, only the retired namesake beside it | `UPDATE`, "shares NO names" | the same |
  | a fictional new club named like a one-of-a-kind Africa club, `--same-name-switch` | 7 question-5 changes on Africa, 8 on the template | 6 and 7; the new club "not added" |
- **A half-applied switch** (the picker's write applied in memory, the rules not), Africa and
  Asia: the sync plans `REPLACE conditions` (and the hide) with no question-5 change, as
  before, now with 6 and 1 `! … its rule tests …` lines; the runner read `in-sync` with no
  ATTENTION before the fixes and reads `attention` ("N roster rule(s) test a name the Club
  picker does not list") after.

## Integration — `wf6/integration` (2026-09-30)

Part 1 (`wf6/same-name-forms`) and Part 2 (`wf6/same-name-intake`, build notes:
[2026-09-30-same-name-intake.md](2026-09-30-same-name-intake.md)) merged onto `main` as it
stood after Step 0 and the Salesforce club accounts (`c8a0feb`). Not merged into `main`, not
pushed, nothing written to Jotform, the sheet, Apps Script or Salesforce.

- **Conflicts** (Part 1 against `main`'s newer doc commits; both sides kept): DECISIONS (the
  delete exception and the Salesforce club accounts, then the same-name rule), BACKLOG 26 and 27
  (every active club has its account; a new one is named by `sf_names`), this plan (Result —
  Step 0, then the build notes). Part 2 merged without a conflict. The Python files are Part 1's
  and `appsscript/` is Part 2's, byte for byte.
- **Added here**: `PythonAppsScriptParity` parses `Config.gs` for `SF_NAME_SEP` (CLAUDE.md rule 7)
  and runs both sides over one fictional Roster, the `.gs` side in Node through
  `test/load_gs.js`: which names are shared (`shared_club_names(active_only=True)` ↔
  `sharedClubNames_`), each club's name (`sf_club_name` ↔ `sfClubName_`), and which new club's
  name is in use (the sync's check ↔ `newClubHoldReasons_`, kind `samename`); `SameNameFlow`
  compares the switched form's `sf_names` with `sfClubName_`. Each fails when either side's rule
  is changed alone (checked with three mutants). `make check` green: 297 Python tests.
- **One divergence met and left** (rule 10): `newClubHoldReasons_` reads a Roster row's status
  exactly (`active`), as the rest of `RosterOps.gs`; `sharedClubNames_` and Python ignore case
  and spacing. A status typed by hand as `Active` would make the intake treat that club as
  having no active girl. The sheet's own code only ever writes `active` / `inactive`; listed in
  ARCHITECTURE "Known divergences" (and the intake notes, deviation 6).

### The read-only proof on the integrated code (about 18:50-19:00 JST)
A fresh Roster export (6,963 rows, 6,857 active; 364 clubs, 362 with an active girl), kept in
the session's scratch directory and deleted afterwards. Jotform: GETs and dry runs only.

| Form | Without any flag | With `--same-name-switch` |
|---|---|---|
| Template | no question-5 change; two ordinary roster updates (q277, q278: changes the runner already applied on their regional form) and the rules rewrite that goes with them (396 kept, 0 new, 0 dropped) | 7 `!` lines (q150, q173, q234, q334, q335, q411, q420); picker 358 → 362; 384 kept, 9 new, 12 dropped; 393 rules; the Partner-box hide |
| Africa | nothing to do | 6 (q173, q234, q334, q335, q411, q420); 215 → 218; 241 kept, 8 new, 11 dropped; 249 rules; the hide |
| Asia | the Partner-box hide only | 1 (q150); 95 → 95; 123 kept, 3 new, 3 dropped; 126 rules; the hide |
| Latin America, U.S | the Partner-box hide only | "nothing to switch"; the hide only |

- The seven new texts equal the table in "The 7 Salesforce names", character for character
  (compared by the script, not by eye), and so do the seven long names `sfClubName_` gives
  over the same export; for all 362 active clubs the two sides give the same name.
- `form_status` (plain and `--rendered`) on all five: CLEAN, 0 conditions flagged, Salesforce
  integration present, every picker option's `data-calcvalue` equal to its value (358 / 215 /
  95 / 38 / 11), regions 0 missing, 0 differ.
- `auto_sync.py` dry run: Africa, Asia, Latin America, U.S `in-sync`; exit 2 for the one
  ATTENTION the switch resolves (three names sent by more than one club).
- A fictional new `Ruby` under a fictional third partner, on a scratch copy: refused by the
  sync on the template and on Africa, with and without the flag (`not added: give it a
  different name`, both partners named), the two existing Rubys (q173, q411) untouched and the
  plan otherwise identical to the run without it; held by the intake check too (`samename`,
  both clubs named), as is a club named `Ruby - Binti Network`.
- The switch simulated in memory on each form's live data (never `--apply`): afterwards
  `form_status` CLEAN with 7 / 6 / 1 / 0 / 0 long-named rosters, guard terms = picker entries,
  q331 hidden; the next run, with or without the flag, plans nothing; the cross-region check
  finds no clash; `restore_conditions.py` would refuse each switched form's earlier conditions.

The template's dry run will show the two roster updates beside the switch's own calls until
the template is next synced: expected, and not a question-5 change.

## Result — the forms (2026-09-30, with Ryan's go)
`AUTO_SYNC_APPLY=0` → fast-forward merge of `wf6/integration` into `main` (`d238b43`, pushed, GitHub
check green; `make check` 297 tests) → a fresh Roster export → per form: backup, dry run, `--apply`, a
second dry run (`nothing to do`), `form_status --rendered`.

| Form | Backup before | Long names | Picker | Rules | After |
|---|---|---|---|---|---|
| template 262352490535154 | `properties-2026-09-30T1913.json` | 7 (q150, q173, q234, q334, q335, q411, q420) | 358 → 362 | 396 → 393 | CLEAN, 362 aligned, q331 hidden |
| Asia 262383129464057 | `properties-2026-09-30T1915.json` | 1 (q150) | 95 (one renamed) | 126 | CLEAN, 95 aligned, q331 hidden |
| Africa 262382821971058 | `properties-2026-09-30T1915.json` | 6 (q173, q234, q334, q335, q411, q420) | 215 → 218 | 252 → 249 | CLEAN, 218 aligned, q331 hidden |
| U.S 262382706852058 | taken before the hide | 0 | 11 | 42 | CLEAN, q331 hidden (the only write) |
| Latin America 262383455778067 | taken before the hide | 0 | 38 | 69 | CLEAN, q331 hidden (the only write) |

- The template's two ordinary roster updates (q277, q278) were applied by a plain sync first, so the
  switch plan carried only its own three calls. Each dry run listed exactly the expected `!` lines.
- The live pickers list the seven names exactly as in the table above ("The 7 Salesforce names"); no
  plain "Angels Club", "Ruby" or "Shining Stars" entry is left on any form; no picker has two equal
  entries. The template's translation audit rose by 4 per language (the four added entries).
- Ryan's browser check on the template: typing "Ruby" shows the two entries, picking one shows only
  that roster with no Partner question, the guard still works. Typing a partner's name in the search
  does not find the entry (the search matches from the start of an entry) — accepted.
- `auto_sync.py` dry run: every region in-sync, no ATTENTION (exit 0). `AUTO_SYNC_APPLY=1`; runner
  apply run 36701947322 in-sync. The Salesforce session has the seven strings.
- Open: the Apps Script push (Part 2); the seven Salesforce Accounts; one template test submission
  with a long name (none was sent yet); an independent read-only verification was started after the
  switch (its result is recorded with the next commit).
