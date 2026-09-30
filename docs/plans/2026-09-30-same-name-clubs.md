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
   names (a picker update is a change the runner applies). With it that run only rebuilds the
   rules. Test: `test_the_picker_says_what_a_club_sends_when_the_rules_are_older`.
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
  on top of the refusal's own ATTENTION until the club is renamed.
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
