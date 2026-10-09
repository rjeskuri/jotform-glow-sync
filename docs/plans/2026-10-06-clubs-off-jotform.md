---
title: Clubs that do not report through Jotform leave the forms - a Partners-tab marker for the three partners, deactivation of the U.S clubs, the U.S form disabled
author: Claude (with Ryan's decisions of 2026-10-06; code and docs read on `main` 9d58ce4 and the branch wf10/four-issues, Jotform GET, Salesforce read connector, 2026-10-06; revised after two reviews the same day)
status: accepted         # Ryan 2026-10-06 (in conversation), with the defaults of the "Open decisions" unless noted in the plan
created: 2026-10-06
intent: docs/intent/2026-10-06-clubs-off-jotform.md
---

# Plan: clubs off Jotform

## Context

**Ryan's decision (2026-10-06).** The 38 clubs of Education and English for You, Tumaini La
Maisha and Ng'aa Maskani leave the Jotform forms through a "not on Jotform" marker on the sheet's
Partners tab, which the sync and the Apps Script honour; their girls stay active and enrolled. The
U.S clubs are deactivated (Roster rows inactive with a removed date, as the Radiant Girls rows were
on 2026-09-28) and the U.S form is disabled - a write with his go, after a double-check that these
clubs have sent nothing. Salesforce: nothing now.

**Where the code is.** The branch was cut from `50126b3`; `main` is at `9d58ce4`, eleven commits
on: the wf9 merge (`3ea1cab`: `tools/form_status.py` +238 lines, `tools/auto_sync.py` +61,
`sync_attendance_form.py` +26, `glow/sync.py` +32), the WESAD re-parenting (`00ee471`) and session
-54's Result (`9d58ce4`: names dictionary and module `calcValues` live on all five forms, every
form CLEAN, `AUTO_SYNC_APPLY=1` again at 11:23 UTC, the runner in-sync on every region). So the
first step is to merge `main` into this branch; every line number below is `main`'s. The form-side
steps start when -54 confirms its window is closed (its Result says so; the confirmation is its).

**What is there today (read 2026-10-06, read only).**

- Roster export `roster_2026-10-06T1047Z.csv`: 7,191 rows, 6,929 active; 364 clubs with an active
  girl (366 partner + club pairs of any status). The three partners: 6 / 16 / 16 clubs, 114 / 320 /
  317 active girls (Education and English for You / Tumaini La Maisha / Ng'aa Maskani; 751 in all),
  all region Africa, none of the 38 club names shared with another partner. One of the 38, Ng'aa
  Maskani's 'QUEENS', is a prefix of WESAD's 'Queens of Quest' (section B). Region U.S: 11 clubs
  under 6 partners, 155 rows, all active (no inactive U.S row exists). Clubs with rows but no
  active girl anywhere: exactly 2 - the two duplicates retired on 2026-09-30, whose questions were
  deleted then. Club names two partners have ever had: 5 (3 among active clubs - e.g. the two
  'Ruby' rosters the Africa picker lists as '<club> - <partner>').
- Forms (`tools/form_status.py`, 2026-10-06): Africa 220 rosters, 251 rules, picker q446, guard q462,
  `vs Roster (217 clubs in region): 0 missing from form, 0 on form but not in roster` (217: the
  audit keys clubs by name, three Africa names have two holders); U.S 11 rosters, 42 rules, picker
  q444, guard q445, 0 submissions; template 364 rosters, 395 rules (before -54's apply of its
  22-roster backlog - read the counts again after the merge). So today **no form carries a roster
  whose club has no active girl**: the behaviour change below touches nothing until the marker is
  set or a club is deactivated.
- Salesforce (read connector): batches for the three partners' clubs, ever: Tumaini La Maisha 2
  (Success, February pilot), the other two 0. North America: 7 partner accounts, 12 Club accounts
  (the twelfth, FemXFem's, has no Roster rows), 0 batches ever. Club accounts without a parent:
  the two pilots only ('Shining Stars test', 'Las Camelias Primaria') - WESAD's 'Change Makers'
  and 'Seeds of Greatness' were re-parented with Ryan's go at 10:53 UTC (`00ee471`).
- Jotform: every live form `status: ENABLED`; the six old forms `DISABLED` with the default
  `messageOfLimitedForm` "This form is currently unavailable!" (`GET /user/forms`,
  `GET /form/{id}/properties`). `status` is a key of both `GET /form/{id}` and
  `GET /form/{id}/properties`. How the five defunct forms were disabled on 2026-09-30 is not
  recorded in the repo (docs/RUNBOOK.md:19 still says they are enabled; BACKLOG 1 still open) -
  presumably in the builder (unverified).

**What the code does with a club that leaves the active roster - and why the marker alone is not
enough.** `read_roster_csv` returns active rows only (glow/sync.py:457-495). A roster question the
export does not claim falls into "clubs on the form but not in the sheet: keep them working, just
warn" (sync_attendance_form.py:835-847): it stays in `club_questions`, so it keeps its Club-picker
entry (`option_of = dict(club_questions)`, :860; the picker's list is built from `option_of`,
:1102-1106), its show rule (`build_conditions` section A over `club_questions`, :286-305), its
club-guard term (the guard tests every picker option, :341-350) and its place in question 18's sum
(:266-277). The run prints `? '<club>' (q…) is on the form but not in the sheet export - keeping
its current roster`, and the runner counts those lines as a possible truncated export: more than
`max(5, clubs // 10)` of them is ATTENTION, nothing applied (tools/auto_sync.py:303-307). That is
why the two retired duplicates had to have their questions **deleted** on 2026-09-30
(docs/plans/2026-09-30-same-name-clubs.md:51-66, DECISIONS 2026-09-30, the one-time exception).
Deleting 38 questions is not on the table (DECISIONS 2026-08-25, CLAUDE.md rule 4), so the sync
needs a third state for a roster question: **retired** - kept on the form, hidden, off the picker,
no show rule.

**A region with no active club.** With `--region U.S` and no active U.S row, `read_roster_csv`
exits: `No active clubs have region 'U.S' in … - check the Partners tab spelling`
(glow/sync.py:491). The runner would then log U.S `failed` ("dry run exited 1") and exit 1 on
every run, including the daily one (tools/auto_sync.py:474-479, 747-748), and GitHub would e-mail
Ryan each time. So the U.S form must be **disabled before** its rows are deactivated, and the
runner must skip a disabled form.

**The existing, wrong way.** A blank region keeps a club off every form (CLAUDE.md rule 6) but
also raises "Active girls with no region" on every run (tools/auto_sync.py:724-730), a
"Partner has no region" ReviewQueue item (appsscript/Roster.gs:267-274), blanks the SF Pending
region, and would be "fixed" by the first person who sees it. A marker says the opposite:
intended.

## Design

### A. The marker: Partners tab column `jotform`

**Column.** `jotform`, fourth column of the Partners tab (today `partner, region, notes` -
appsscript/Roster.gs:17 `PARTNER_COLS`, the 2026-09-30 export's header). Values: `no` = the
partner's clubs are not on Jotform; `yes` or blank = on Jotform (the default; 46 partners' cells
stay empty). Compared with `key_` / `glow.text.key` (capitals and spacing ignored), so `No` and
` no ` count; any other text is treated as **yes** and reported (the safe side: nothing leaves a
form because of a typo), the runner raising ATTENTION for it.

Why this and not `attendance_source` (Jotform | Partner totals): Ryan said "not on Jotform"; a
yes/no column has one meaning and no vocabulary to keep in step with plan 4, whose intake method
is not decided and whose `Creator__c` values live in Salesforce. Why not a mark in `notes`: free
text staff edit. Why not the Roster tab: every Roster writer (`planClub_`, `applyRosterPlan_`,
the offline builder, `upload_roster.py`) and `ROSTER_COLS` on both sides would change for a value
that is per partner.

**How it reaches Python.** The Python side reads Roster exports only (tools/auto_sync.py:461-467
exports the Roster tab; the sync and `form_status` take `--roster`). The marker is a per-partner
cell, so the Partners tab is exported too and passed as `--partners <csv>`:

- `glow/sync.py`: `PARTNER_COLS = ("partner", "region", "notes", "jotform")` and
  `JOTFORM_COL = "jotform"` (mirrors of Roster.gs and tools/build_roster_offline.js:86, see
  parity below); `read_partners_csv(path) -> {key(partner): "yes" | "no"}` reading the columns by
  header name (like tools/rename_club.py:202-214 `partner_rows`), exiting on a file without a
  `partner` column, warning (through `warn`, so the runner sees it) on a value other than
  `yes` / `no` / blank: `! Partners tab: '<partner>' has jotform='<value>' - only yes, no or blank
  are understood; treated as yes`. (`tools/form_status.py` already has a `load_partners(path)`,
  :76-87, which reads the ROSTER for each club's holders; it is untouched, and the Partners-tab
  reader is this one, imported.)
- **A floor on the Partners export.** Every partner with an active club in the Roster export must
  be a row of the Partners export (compared by `key`), or the sync exits like the Roster's own
  floor does: `Partners export lists 46 of 49 partners with active clubs - missing: <names> - a
  truncated export, or rows deleted from the Partners tab? nothing done`. Without it an empty or
  cut export would read every partner as unmarked and restore all 38 entries unattended (one
  picker UPDATE, inside every band). `seedPartners_` (appsscript/Roster.gs:322-356) adds every
  Roster partner to the tab, so at rest none is missing; the runner logs the exit as `failed`
  (tools/auto_sync.py:474-479) and GitHub e-mails Ryan.
- `sync_attendance_form.py` gains `--partners PATH` (with `--roster`). After
  `read_roster_csv` (:473), the clubs of partners marked `no` are taken out of `sheet` (not of
  `all_clubs` / `region_of`, which stay the Roster's truth for `foreign_region`, :712-727). The
  `Roster:` line gains a tail after `clubs overall` (the runner's `ROSTER_RX`,
  tools/auto_sync.py:90-91, is anchored at the start only, so the tail is free text to it; its
  test gains the new shape): `Roster: 182 active clubs in Africa (3518 girls); 364 clubs overall;
  38 club(s) of 3 partner(s) not on Jotform (Partners tab jotform=no) left off this form`. The
  form's status is its own line, printed just before: `Form: 262382821971058 status ENABLED`.
- `tools/auto_sync.py`: `export_roster` also writes `partners_<stamp>.csv` next to the Roster
  export (`sc.read_tab(svc, "Partners")`), `--partners CSV` for local runs (like `--roster`), and
  every sync and verify call gets `--partners` (:433-440, :578-579). `--roster` without
  `--partners` exits up front (`--roster needs --partners <Partners export>: with --roster nothing
  is exported, and without the Partners tab the sync cannot tell a retired roster from a broken
  one`): the sheet service is never built on that path (:703-705), so there is nothing else to
  export from.
- `tools/form_status.py`: `--partners PATH`, read with `glow.sync.read_partners_csv`; what it
  does with it is under `form_status` below.

**`RETIRE_INACTIVE`** (glow/sync.py, beside `ROSTERS_REQUIRED` :192 and `CONTACT_IDS_FIRST`
:171). The second trigger - a club with no active girl leaves the picker in every region - is
built behind a constant - **Ryan, 2026-10-06: on** (`RETIRE_INACTIVE = True`): a club whose
rows are all inactive is retired as below, but only when the club's latest `removed_date` is at
least a day before the run's UTC date (`roster_pairs`, glow/sync.py:296, learns the latest
`removed_date` per pair) - a club emptied by "REMOVE every girl" and refilled by "ADD the new girls"
minutes later on the Club Roster Form (each submission dispatches a sync,
appsscript/FormHandlers.gs:866) must not vanish from the picker in between. With `False` a club
that loses its last active girl keeps today's `?` treatment. Tests cover both values; the decision
goes into DECISIONS. So the 11 deactivated U.S rosters leave the template's picker at its next
hand sync (`~ retired roster … no active girl in the Roster`, the day after the deactivation).

**Retired rosters in the sync** (the new state). Decided **before** the reconcile loop, so that
both of its branches see the same thing: a roster whose club's name another partner's club shares
is matched in the same-name branch (:796-833), where an unclaimed question is kept with `!
matched no partner in the sheet - keeping it` (:827-833) and never reaches the "on the form but
not in the sheet" loop (:835-847). So, after the rules are read back (:586-637) and before :765:
for every roster question the sync asks the Roster who owns it - `holders.get(key(form_text[qid]))`
(the partners with a club of that name, any status, :487) narrowed by the partner its rule names
or its owner read-back (`current_partner_of`) when the name has several holders. When the owner
is one pair in `roster_pairs` (:296) and either its partner is marked `no` or (`RETIRE_INACTIVE`)
the pair has no active girl, the roster is **retired**: its qid is taken out of `existing` (so
neither branch matches it), it is not in `club_questions` nor `option_of`, and it is listed in a
new `retired = {qid: reason}`; the run prints one line per roster, a third marker beside `!` and
`?`:

```
  ~ retired roster 'Adonai GLOW Club' (q…): not on Jotform (Tumaini La Maisha, Partners tab jotform=no)
  ~ retired roster '<club>' (q…): no active girl in the Roster
```

A question whose owner cannot be told (several holders, a plain rule, no read-back) or whose club
the Roster does not know at all keeps today's treatment and lines (an incomplete export looks like
that; the runner's truncated-export band stays as it is). `build_conditions` takes `retired=()`
and puts those qids in question 18's operands and equation (together with `club_questions`,
:266-277) but writes **no show rule** for them; the picker's options and the guard's terms follow
`option_of` and so drop the entries. Nothing is written to the roster question itself: hidden
(every roster is created `hidden=Yes`, :1067), required (unchanged), its options frozen - a
retired roster is never updated (`to_update` is built from claimed questions only). A roster
nobody can see has no ticked box to contribute to question 18, so leaving it in the sum is
harmless and keeps `form_status`'s "one {qid} per roster" audit unchanged (tools/form_status.py
`audit_contact_ids`, :660-731).

*Why the rule is dropped rather than kept as the roster's memory.* A show rule testing an entry
the picker no longer lists is the state `restore_conditions.py` refuses (its docstring :9-16,
`--force`) and that the sync's `RULES_OLDER` warning and the runner's stale-rules attention
(tools/auto_sync.py:511-530) exist to catch; 38 such rules on purpose would make every later Africa
snapshot a `--force` restore and teach the checks an exemption they cannot verify from the form
alone. The price is the memory of what the club sent to question 5, handled on the way back.

**Hidden and required, without a rule.** Jotform validates a required field only when its `<li>`
carries neither `always-hidden` nor `form-field-hidden` (.claude/skills/jotform-api/SKILL.md
"Required + hidden": the runtime read 2026-09-30, headless Chrome on local copies 2026-10-01,
nothing submitted). A property-hidden question that no rule touches renders with `always-hidden`
alone - that is how the 2026-10-06 read-only investigation's reading of the served page and runtime has q98 / q100 /
q102 (`hidden=Yes`, no visibility rule; none of them a checkbox). The live rosters a rule hides are
the `form-field-hidden` case, so the retired rosters are the first required checkboxes on these
forms that rest on `always-hidden` alone. If that reading were wrong no Africa mentor could submit,
so it is **proven on the template in step 7, before Africa**: `form_status --rendered` learns to count,
for the retired qids, `<li>` elements with `always-hidden` and their `validate[required]` boxes
(`38 retired rosters: 38 always-hidden`, a PROBLEM when fewer), and the 2026-10-01 method is
re-run on a local copy of the served template page (pick a club, tick one girl, `validateAll` true
with the 38 retired rosters present; nothing submitted). The result goes into the skill.

**The way back.** A retired roster whose club is active again and whose partner is not marked
`no` is in `sheet` and its qid stays in `existing`, so the ordinary matching claims it (:765-794):
it gets its entry and rule back and an options update if the Roster moved on. The run says so:
`~ restored roster '<club>' (q…): back on the Club picker`. What it sends to question 5 again:

- Its name is **no other partner's** (not in `shared_any`, :488): the plain name - the only text
  it can ever have sent (a roster becomes long only through `--same-name-switch`, which goes by a
  namesake's rows, and the Roster deactivates rows, never deletes them - DECISIONS 2026-08-24).
  Nothing to warn.
- Its name **two partners have had** (`shared_any`): with no rule to read, `sends_now` (:666-684)
  returns None and today's code would make it plain unwarned (`long_now` False, :890-892; no
  `sf_changes` entry, :896) - a question-5 change that CLAUDE.md rule 5 forbids without renaming
  the Account first. So the restore proposes the **long** name (what every roster of a shared name
  sends since the 2026-09-30 switch) and records it as a question-5 change with `old =
  "(retired: no rule to read)"`: the `Q5_CHANGES` warning (:1019-1026), the `--apply` refusal
  without `--q5-change-ok` (:1028) and the runner's question-5 band (tools/auto_sync.py:279-284)
  all fire, and the hand step checks the Account's name first (RUNBOOK "Club names two partners
  share"). Not today's case (none of the 38 is shared); reachable once `RETIRE_INACTIVE` is on.

Flipping the cell is the rollback of the marker; `deactivate_clubs.py --undo` (C) is the rollback
of a deactivation. No snapshot is involved (and `restore_conditions.py` would refuse the
pre-retirement conditions file anyway: its rules test entries the picker no longer lists -
docs/RUNBOOK.md "Automatic sync", its **Rollback**).

**Refusals.** Without `--partners`, a roster with no show rule and no picker entry whose club is
active in the Roster would be restored - 38 entries back on Africa by a forgotten flag. The same
shape is also an apply that stopped between the question writes and the picker and conditions
writes (the half-applied new club `sends_now` comments on, :678), which today's re-run completes.
So a dry run prints, per roster, `! '<club>' (q…) has no Club picker entry and no show rule
although its club is active in the Roster - a retired roster, or a new roster of an apply that
stopped half-way: pass --partners <Partners export> (the runner always does) and the run restores
it or keeps it retired`, and `--apply` refuses (`Refusing: … roster(s) would be restored without a
Partners export`). With `--partners` both cases are one path: the roster is restored (the `~`
line), or retired when its partner is marked `no`. A `jotform` value other than yes / no / blank is
the warning above (never a refusal: the safe reading is yes).

**`--summary-json`** gains `retired` and `restored` (qid, club, partner, reason) and `partners`
(the export's path, or null); `sf_names` lists what the clubs that stay send - a retired club sends
nothing, so it is left out (its Salesforce Account keeps its name; plan 4's aggregate batches land
on it).

**The runner.** `parse_plan` / `plan_from_summary` (tools/auto_sync.py:119, :171) read the `~`
lines (`RETIRED_RX`, `RESTORED_RX`, beside `MODULE_RX` :88; `retired` and `restored` beside
`modules` in the plan dict); `plan_summary` (:247) adds `, N retired` / `, M restored` when
non-zero (SyncLog `detail`); `check_bands` (:264-308) gains two bands, `--max-retires` and
`--max-restores` (both default 5): more in one region in one run is `attention` - "would take N
clubs off the Club picker at once (band: 5) - a partner newly marked jotform=no, or a wrong cell on
the Partners tab? apply by hand after checking" / "would put N clubs back on the Club picker at
once (band: 5) - a cell flipped back, or a Partners export missing its rows? apply by hand after
checking" (the first rollout, 38 on Africa, is by hand in any case). The picker `UPDATE` that
carries a retirement is already a counted change (:241-244 `changes`). The `jotform=<other value>`
warning is an ATTENTION that does not stop the region (like the refused-name warning, :485-502).

**`form_status`.** With `--partners` (the Partners export through `glow.sync.read_partners_csv`;
the audit's own `load_partners`, the Roster holders, stays as it is): a roster with no show rule
and no picker entry is **retired** when the Roster says so (partner marked `no`, or
`RETIRE_INACTIVE` and no active girl); then `audit_rules`'s "has 0 show-rules, expected 1"
(:613-615), the picker-coverage check inline in `form_report` ("club picker misses N club(s)",
:836-844 - not `audit_picker`, :117, which checks the picker's own properties) and the region
check's "on form but not in roster" list (`extra`, :891) leave it alone, and the report prints
`retired rosters: 38 (not on Jotform 38, no active girl 0)` and a `region_check.retired` list. A
marked partner's roster that still has its rule or its entry is **awaiting retirement**: the vs
Roster line reads `… 38 await retirement (the next sync apply)`, a `region_check.awaiting_retirement`
list, no PROBLEM (the rehearsal state of steps 4-6); `verify_report` (tools/auto_sync.py:322-356),
which runs only after an apply, counts a non-empty list as a problem (an apply leaves nothing
awaiting). A roster off the picker whose club is active and whose partner is not marked `no`
stays a PROBLEM (`'<club>' (q…) is off the Club picker but its club is active in the Roster - pass
--partners if its partner is not on Jotform, else the next sync apply restores it`). Without
`--partners` every retired roster of an active club reads that way: Africa is NOT CLEAN until the
export is passed - the tool refuses to guess. `load_roster` (:62-73) keys the region's clubs by
name, so a name leaves `want` only when every Roster holder of it in the region is retired; a
retired roster sharing its name with an active club of the region is left out of that name's
union compare (`on_form`, :897) and its girls out of `want[k]` - a test, not today's case (0 of
the 38 and 0 of the U.S 11 share a name). The `Roster (active girls):` header line lists the
retired clubs per region after the active count.

**Apps Script** (small; nothing on the form side depends on it, so it can follow):

- `appsscript/Roster.gs:17` `PARTNER_COLS` gains `'jotform'`; a reader `loadPartnerJotform_()`
  (the shape of `loadPartnerTabRegions_`, :98-109) returning `{key_(partner): true}` for cells
  that read `no`. `seedPartners_` writes `PARTNER_COLS.length` cells per new row (:337, :355): the
  rows it builds get a fourth, empty cell, or `setValues` throws on the width.
- `appsscript/FormHandlers.gs`: the mentor e-mails' closing line "The attendance form updates
  within the hour." (:903) and the hold notice's "The girls appear on the attendance form once the
  club is added." (:811) are replaced, for a partner marked `no`, by "Your organization reports
  attendance to GLOW directly, so nothing changes on the attendance form." Everything else stays:
  a new club under such a partner still gets its region from the Partners tab (:699-701), its SF
  Pending row (:736-740; the Monday e-mail asks for its Salesforce Account, which plan 4 needs)
  and dispatches a sync (:748, appsscript/Dispatch.gs:65-67) - harmless: the sync leaves the club
  off the form and the region reads `in-sync`. No ReviewQueue item: nothing is wrong.
- `tools/build_roster_offline.js:86` keeps its own `PARTNER_COLS`: same change.
  `tools/upload_roster.py:55-79` `merge_partners` cuts every Partners row to three cells (`[:3]`)
  and would drop the column on an upload: it keeps the live header's width instead. Neither has
  run since launch (docs/SHEETS-ACCESS.md:66-70).
- No new Google service, so no new OAuth scope and no rule-11 outage; the push still follows
  "Apps Script deploy".

**Parity (rule 7).** `test/python_test.py` `PythonAppsScriptParity` (:3684) gains
`test_partner_columns`: `PARTNER_COLS` in appsscript/Roster.gs and tools/build_roster_offline.js
equal `glow.sync.PARTNER_COLS`, and `JOTFORM_COL` is one of them (the shape of
`test_synclog_columns`, :3869). docs/ARCHITECTURE.md's "Constants that exist on both sides"
gains the row `Partners tab columns` (the table is itself tested, :3895).

**The Monday e-mail** is unaffected (ReviewQueue + SF Pending only). **The Club Roster Form** lists
a partner's clubs with active girls (appsscript/Forms.gs:393-408), so the three partners' clubs
stay available for roster changes (their rosters are the enrolment truth and BACKLOG 58's
"enrolled" count), and the U.S partners' sections read `(no active clubs)` (:343) after step C.

### B. Double-check before the switch (read only)

The 2026-10-06 investigation's stripped Africa submissions (ids, dates, structural answers, the picker and question 5
only) already answer it for 2026-09-01 to 2026-10-06: of 211 submissions, **0 name one of the 38
clubs as the club submitted** and **1** (2026-09-25 11:26 US Eastern, before the club guard) picked
two clubs, 'Adonai GLOW Club' (Tumaini La Maisha) and 'Love glow club', with one roster ticked and
question 18 empty - a multi-club pick by the other club's mentor, handled by the September
back-fill resolver. Salesforce agrees: 0 batches for Education and English for You and Ng'aa
Maskani, 2 February pilot batches for Tumaini La Maisha, none since.

**How a submission is matched to a club.** By `key` equality, or `key(value).startswith(key(club)
+ SF_NAME_SEP)` (glow.sync.SF_NAME_SEP, the `<club> - <partner>` form) - never a bare prefix: Ng'aa
Maskani's 'QUEENS' is a prefix of WESAD's 'Queens of Quest', which has 5 Africa submissions since
2026-09-01 (2026-09-25 x2, 2026-10-01 x3); a prefix match would credit them to 'QUEENS' and the
deactivation guard would stop a `--partner "Ng'aa Maskani"` run for the wrong reason. The exact
rule finds 0 for 'QUEENS' and still finds the Adonai pick (its picker answer lists the exact club
text). A unit test pins the pair.

On the day, the same count from the live form, through a small read-only addition to the plan's
tooling rather than a scratch script: `tools/deactivate_clubs.py --partner "<partner>" --check-only`
(below) prints, per club, the submissions of the region's form since 2026-09-01 whose question 5
or picker answer matches the club by that rule (`GET /form/262382821971058/submissions?limit=1000
&filter={"created_at:gt":"2026-09-01 00:00:00"}`, `answers['5']`, `answers['<picker qid>']`; counts
and club names only, nothing else read out). Expected:

```
Africa form 262382821971058: 2xx submissions since 2026-09-01 read
  Education and English for You   6 clubs   0 submissions
  Ng'aa Maskani                  16 clubs   0 submissions
  Tumaini La Maisha              16 clubs   1 submission  (1 picked together with another club, 2026-09-25)
U.S form 262382706852058: 0 submissions
```

Anything else stops the step until Ryan has looked at it.

### C. The U.S clubs: `tools/deactivate_clubs.py`

A standard-library argparse tool in the shape of `tools/rename_club.py` (service account through
`tools/sheets_client.py`, dry run by default, backup, stale check, one `batchUpdate`, re-read and
compare, one Audit row; :326-328, :491-507, :527-547, :552-613, :624-626).

- **Selectors:** `--region U.S` (every club with an active row in that region), `--partner P`
  (repeatable), `--club "C" --partner P`. Several may combine; the plan lists partner / club /
  active rows, and refuses a selector that matches nothing.
- **Guard:** the region form's submissions since 2026-09-01 are read (the key from the
  environment) and matched by B's rule; a club named by any submission in the last `--recent-days`
  (default 30) stops the run - `'<club>' sent attendance on <date> - deactivating a club that
  reports needs --deactivate-anyway` - and `--check-only` prints that table and exits (the check
  of B).
- **Writes (`--apply`):** `status` -> `inactive` and `removed_date` -> today in the sheet's zone
  (`sc.named_zone(sc.time_zone(svc))`, as rename_club.py:491-494; the Apps Script writes the same
  text, appsscript/Roster.gs:9-13, 292-301) on every ACTIVE row of the selected clubs - 155 rows,
  310 cells for U.S. Before writing: the Roster tab saved to `data/deactivate_clubs/<stamp>/Roster.csv`
  and the addressed row numbers with their old values to `written.json` beside it; the tab re-read
  and the run stopped if a planned row changed or the club gained a row (a Club Roster Form
  submission in between; rename_club.py:527-538). After: every addressed row re-read and compared,
  the other rows unchanged in the two columns, then one Audit row `deactivateRows` - `11 club(s)
  of 6 partner(s) in U.S: 155 row(s) set inactive, removed_date 2026-10-0X -
  tools/deactivate_clubs.py (<--reason text>)` - the action name the 2026-09-28 repair used
  (docs/plans/2026-09-27-formlog-key.md:181-187).
- **The way back, scripted:** `--undo data/deactivate_clubs/<stamp>` - the same shape (dry run,
  stale check, one `batchUpdate`, re-read and compare, Audit row `reactivateRows`) over exactly the
  rows `written.json` names: `status` back to `active`, `removed_date` back to what it was (blank).
  It refuses when one of those rows has changed since (a reactivation by the Club Roster Form, a
  move) and says which. The 2026-09-28 and 09-30 deactivations used scratch scripts with a re-read
  (docs/plans/2026-09-30-same-name-clubs.md:55-56); this plan leaves a command instead.
- **Not touched, and why:** the ClubRegistry rows (the club code is immutable and found by
  partner + club by `Ids.gs` when the club comes back; the tab has no status column and inventing
  one would touch `CLUB_COLS`, `Roster.gs`, the offline builder and the parity tests for a value no
  reader needs); SF Pending (the U.S Accounts exist); the Partners tab (the six U.S partners stay,
  their region stays `U.S`); the Jotform forms (the sync does that; here the form is disabled
  first, D). The girls' ids are kept for a reactivation (DECISIONS 2026-08-24).
- **Afterwards:** `GLOW -> Google Forms -> Update form dropdowns from the Roster` in the sheet
  (the tool's "Next" lines say so, as rename_club.py:645-684 do), so the U.S partners' sections
  read `(no active clubs)`; the U.S form itself is not synced (D). On the template the 11 rosters
  are `?`-kept until `RETIRE_INACTIVE` is on, then its next hand sync retires them (`~ retired
  roster … no active girl in the Roster`).

The U.S form is **not** synced down to zero clubs: an empty Club picker (`question[options]=`),
a guard without terms and a region the sync refuses to read are three untested shapes for a form
nobody can open. Its 11 rosters, picker and rules stay as they are, frozen, on a disabled form.

### D. Disabling the U.S form: `tools/disable_form.py`

`status` is a property of every form (`ENABLED` / `DISABLED` on `GET /form/{id}` and
`GET /form/{id}/properties`, read 2026-10-06 on the live and the defunct U.S forms); whether
`POST /form/{id}/properties` with `properties[status]=DISABLED` changes it is **unverified** (the
form-encoded POST sets scalars such as `title` and `injectCSS` - .claude/skills/jotform-api/SKILL.md
"Properties"; `integrations` answered 200 and changed nothing, so an unanswered property is a real
possibility). The jotform-api skill records no way to disable a form, and the five defunct forms'
switch-off is undocumented. So:

- `tools/disable_form.py --form <id> [--enable] [--message TEXT] [--apply]`, through
  `glow.jotform.Client`. Dry run: `GET /form/{id}` (title, status, count, last submission) and the
  properties `status`, `messageOfLimitedForm`; refuses to disable a form with a submission in the
  last 30 days unless `--disable-anyway`, and always refuses the template and any form not in
  `glow.forms.LIVE` (the defunct ones are already off). `--apply`: first `backup_forms.py --form
  <id>` (the properties snapshot records `status` and `messageOfLimitedForm`; the runner backs up
  the same way, tools/auto_sync.py:553-558), then `POST /form/{id}/properties` with
  `properties[status]` and, when given, `properties[messageOfLimitedForm]` (the disabled page's
  text - that this property is what the disabled page shows is unverified; the default is "This
  form is currently unavailable!"), then re-reads both and prints them. **If the re-read still says
  `ENABLED`, the tool says so and stops:** `the API accepted the write but the status did not
  change - disable the form in the builder (Settings -> Form Status) and run this again without
  --apply to confirm`. The U.S form, with 0 submissions, is where this is learnt; the result goes
  into the jotform-api skill either way. The way back is `--enable --apply` (or the builder); the
  snapshot is the record of what the status and message were.
- Proposed message: "The U.S attendance form is paused. Please contact your GLOW coordinator." -
  English only (the disabled page is Jotform's own; whether it translates is unverified, the
  2026-09-01 intent asked the same).

**The runner and a disabled form.** `Run.region` (tools/auto_sync.py:469-612) reads
`GET /form/{id}` first, inside `self.with_retry` (:442-451); a read that still fails records
`result = failed`, `detail = could not read form status`, sets `self.failed` and goes on to the
next region (the dry-run failure path, :474-479; a `JotformError` must not escape `main()` and lose
the run's SyncLog rows, log and ATTENTION.md, written only at :736-746). When `status` is not
`ENABLED` it logs `  form <id> is DISABLED - not synced` and records the SyncLog row
`result = skipped`, `detail = form DISABLED` (a new value in the `result` list, docs/RUNBOOK.md:306),
runs no dry run, no apply, no verify, exit code unaffected. `REGIONAL_FORMS` keeps U.S: nothing
to flip back in code when the form is enabled again, and the live form's status is the truth
read on every run. `sync_attendance_form.py` by hand prints the `Form: <id> status …` line and
refuses `--apply` on a `DISABLED` form without `--disabled-ok` (a write nobody can see).
`form_status.py` already prints `[DISABLED]` (:939, from :873); for a form whose status is not
`ENABLED` the region check is skipped (`vs Roster: skipped (form DISABLED)`, JSON
`region_check: {"skipped": "DISABLED"}`) and so are the served-page checks (`--rendered`,
:930-932: the disabled page has no picker select, no rules, no boxes, no store, so every one of
them would fail - `public_page` is not fetched and the report prints `rendered: skipped (form
DISABLED)`); `verify_report` (tools/auto_sync.py:322-356) takes the skipped region check as a note,
not a problem. The `--min-active 1000` floor is untouched (6,929 - 155 active rows).

**The way back (RUNBOOK "Disabling a regional form").** A U.S club starts: the partner sends
"Enroll a NEW club" on the Club Roster Form (its section shows no club to change); the duplicate
guard holds it (an exact re-enrollment with its names on file - DECISIONS 2026-09-28), Ryan releases
it from the Monday e-mail and `planClub_` reactivates the rows by name (sent after the removal
day, so the replay guard allows it) - or `deactivate_clubs.py --undo` for a whole club set. Then
`tools/disable_form.py --form 262382706852058 --enable --apply` (or the builder), one runner dry
run (U.S reads `in-sync` or plans the restores), `AUTO_SYNC_APPLY` unchanged.

### E. Salesforce: nothing now

Ryan: everyone at the organisation knows these clubs are not in Jotform. So: no field, no write.
Consequences to know: the 38 + 12 clubs stay in "Clubs With No Attendance Last Month" (00ORP000009a6Un2AI)
and in the "did not submit" lists of the [attendance-totals plan](2026-10-06-attendance-totals.md),
which by default accepts that padding (Ryan: no Salesforce-side marker; a hand-typed partner
exclusion is its listed alternative) - the 38 read as submitting from the month their first
aggregate batch lands, the 12 stay listed; the three
partners' aggregate batches (plan 4) land on their existing Club accounts, named as the picker
named them (plain names - none of the 38 is shared); the twelfth U.S club (FemXFem, an Account with
no Roster rows) is plan 2's hygiene, not this plan's. The parent-less Club accounts are the two
pilots again (the two WESAD strays were re-parented 2026-10-06, `00ee471`), so the RUNBOOK's
signal reads 2. BACKLOG 58's rate, when it comes, needs the same marker on its "enrolled" side
(751 girls enrolled, 0 Jotform attendance, by design).

**New clubs of a flagged partner and their accounts** (added 2026-10-07, when `main`'s new-club
account step was merged): session -51's automatic club accounts
([plan](2026-10-06-sf-new-club-accounts.md); `tools/sf_new_clubs.py`, repository variable
`SF_SYNC`) create an account **only for a club the sync puts on a form** - the step runs inside
the region's apply, over the plan's `CREATE roster` lines. A new club of a partner marked
`jotform=no` never reaches a form (Risks: "A new club under a flagged partner"), so the sync makes
no account for it: it stays on SF Pending and in the Monday e-mail for a hand create, and that
account must exist before the club's first aggregate batch (plan 2 F's contract: a typed name
with no account makes the processor create a partner-less one). The second trigger that would
close this, "an active Roster club on no form with no account", is BACKLOG 74 (Ryan's decision).

## Files that change

- `glow/sync.py` - `PARTNER_COLS`, `JOTFORM_COL`, `read_partners_csv`, `RETIRE_INACTIVE`;
  `roster_pairs` learns the latest `removed_date` per pair; `read_roster_csv` unchanged (its
  zero-club exit stays: the guard against a misspelled region).
- `sync_attendance_form.py` - `--partners`, `--disabled-ok`; the `Form:` line, the `Roster:`
  line's tail; the Partners-export floor; the retired decision before the reconcile loop and the
  restored state in it, the `~` lines; the restore's question-5 rule (long for a shared name, as an
  `sf_changes` entry); `build_conditions(..., retired=())`; the no-`--partners` warning and
  `--apply` refusal; the summary's `retired`, `restored`, `partners`; docstring.
- `tools/auto_sync.py` - the Partners export and `--partners` (and the `--roster` without
  `--partners` exit); `RETIRED_RX`, `RESTORED_RX`, `JOTFORM_VALUE` (the warning fragment);
  `plan_summary`, `check_bands` (`--max-retires`, `--max-restores`); the `GET /form/{id}` status
  read under `with_retry`, `skipped` and the `failed` on a read that fails; `verify_report`'s
  skipped region check and `awaiting_retirement`; docstring.
- `tools/form_status.py` - `--partners`; retired and awaiting rosters in `audit_rules`, the
  picker-coverage check in `form_report` and the region check; the `[DISABLED]` skip of the region
  check and of `--rendered`; `--rendered`'s `always-hidden` count for retired qids; the printed
  lines. `restore_conditions.py` unchanged (see "Why the rule is dropped").
- `tools/deactivate_clubs.py` (new, with `--check-only` and `--undo`) and `tools/disable_form.py`
  (new).
- `appsscript/Roster.gs` (`PARTNER_COLS`, `loadPartnerJotform_`, `seedPartners_`'s row width),
  `appsscript/FormHandlers.gs` (the two e-mail lines), `tools/build_roster_offline.js`
  (`PARTNER_COLS`), `tools/upload_roster.py` (`merge_partners` keeps the header's width).
- `test/python_test.py` - parity (`test_partner_columns`); the sync: a flagged partner's roster
  retires (no rule, no entry, in the sum; nothing written to the question), the same for a roster
  whose name another partner's club shares (the same-name branch), a club with no active girl
  retires only with `RETIRE_INACTIVE` and a `removed_date` before today (both values, the same-day
  case kept), an unknown club keeps the `?` line, a restored roster (plain for an unshared name; a
  shared name is restored long, listed as a question-5 change, `--apply` refused without
  `--q5-change-ok`), the `--apply` refusal without `--partners` (the message names both cases),
  the Partners-export floor, an odd `jotform` value is yes + warning, the `Form:` line and
  `--disabled-ok`, the `Roster:` tail against `ROSTER_RX`; the runner: `~` lines parsed, the two
  bands, `skipped` on a disabled form, `failed` on a status read that raises (a fake client), the
  Partners export passed through, `--roster` without `--partners`, the verify note and the awaiting
  problem; `form_status`: retired clean with `--partners`, awaiting as a note, a problem without
  `--partners`, the disabled skips, the `always-hidden` count; `deactivate_clubs` on the `FakeSheet`
  (:3906): plan, stale row refusal, the write and Audit row, the recent-submission refusal, the
  exact-or-long match ('Queens' / 'Queens of Quest'), `--undo` and its stale refusal;
  `disable_form`: the dry run, the backup before the write, the "did not change" stop.
  `test_plan_line_formats_still_exist_in_the_sync_tool` (:212) gains the `~` lines and the
  `Form:` line. `test/forms_logic_test.js` where it builds a Partners tab from `PARTNER_COLS` (:872).
- `docs/RUNBOOK.md` - new sections "Clubs that do not use Jotform", "Deactivating a club",
  "Disabling a regional form"; the manual loop and "Automatic sync" gain `--partners` and the
  `skipped` result; :19 corrected (the five defunct forms are disabled). `docs/ARCHITECTURE.md`
  (the constants row, the sync's and runner's descriptions, a known-divergence line: Python reads
  the marker, Apps Script only for the e-mail wording). `docs/DECISIONS.md` (below).
  `docs/BACKLOG.md` (item 1 closed as done 2026-09-30, how unverified; a new item for the retired
  rosters' options - 71 as of `main` 9d58ce4, after the module plan's 66-67 and the photos plan's
  68-70; re-checked at commit time). `CLAUDE.md` (the `form_status.py` and sync command lines gain `--partners`;
  rule 6 points at the marker; rule 7 lists `PARTNER_COLS`). `.claude/skills/live-systems/SKILL.md`
  (two new writers). `.claude/skills/jotform-api/SKILL.md` (`status` on `GET /form` and the
  properties; what the status write did; the `always-hidden` proof). `docs/plans/2026-10-06-clubs-off-jotform.md`
  (Result).

## Order of work

Steps 1-6 write nothing to a form (step 6 reads one). Form-side steps (7 onwards) needed
session -54's window closed: it confirmed so at 11:23 UTC on 2026-10-06 (`main`'s `9d58ce4`
records its rollout as complete and `AUTO_SYNC_APPLY=1`); they now wait only for Ryan's acceptance
of this plan and his goes.

1. **Merge `main` into this branch** (wf9 and the WESAD re-parenting have landed); read the
   template's counts again; `make check` green before anything else.
2. Commit this plan and the intent.
3. Code and tests (Files that change), `make check` green; the three `~` lines, the `Form:` line
   and the two new tools' `--help` in the smoke.
4. Read-only rehearsal on today's exports, nothing written: a Partners export with the three `no`
   cells edited into a **scratch copy** under `data/`, then the sync's dry run on Africa and the
   template with `--partners` (the lines in Proof), `form_status --partners` on the live forms
   (CLEAN, with `38 await retirement` on Africa's vs Roster line and 0 retired: the 38 still have
   their rules and entries; the scratch run proves the parser, the counts and the band), the
   runner's dry run with `--roster … --partners …` (Africa `attention`: 38 > the retire band; the
   rest `in-sync`).
5. The sheet, by Ryan in the UI: `Partners!D1` = `jotform`; `no` in column D of the three rows
   (Education and English for You, Ng'aa Maskani, Tumaini La Maisha). Then
   `python3 tools/sheets_client.py export Partners data/partners_<date>.csv` (read only) and the
   sync dry run again from the real export. Nothing on a form changes yet: the runner is on `main`
   without this code and keeps the 38 as they are (it has no `--partners` to read, and today's
   code claims active clubs).
6. B's count, from the live form (`tools/deactivate_clubs.py --partner … --check-only`, three
   runs) - expected 0 / 0 / 1-accidental as above.
7. `AUTO_SYNC_APPLY=0`, confirmed by one manual workflow run reading `dry-run`. **Template**:
   `backup_forms.py --form 262352490535154`; dry run; `--apply` with Ryan's go; second dry run;
   `form_status --partners --rendered` CLEAN including `38 retired rosters: 38 always-hidden`; the
   headless-Chrome check on a local copy of the served page (a club picked, one girl ticked,
   `validateAll` true; nothing submitted); on the public page (counts only, as the contact-ids plan
   did): the picker's option count equals the entries that stay, a search for one retired club's
   name offers nothing, a club that stays shows its roster. Not CLEAN or not 38/38: stop, restore
   the template's conditions from the backup, and nothing touches Africa.
8. **Merge and push, then Africa in the same sitting.** The merge first: `main`'s runner would
   otherwise, on an Africa applied from the branch, put the 38 back with Africa's next roster
   change (today's code claims every active club and applies a picker update unattended). One
   manual runner dry run from `main`: Africa `attention` with the retire band (38 planned, nothing
   applied), Asia, Latin America and U.S `in-sync` (-54's module values are applied on all four, so
   no module line). Then **Africa by hand**: backup, dry run, `--apply` with Ryan's go, second dry
   run, `form_status --partners --rendered` CLEAN (38 retired, 38 always-hidden), the browser
   counts as for the template. Until the Africa apply every runner run - each Dispatch and the
   daily 11:00 UTC one - reads Africa `attention` and exits 2 (a failed workflow run and its e-mail
   each time), and Africa's ordinary roster changes are held with it (`check_bands` stops the whole
   region before the apply gate, tools/auto_sync.py:534-548): keep the window to the one sitting,
   and say so to Ryan before step 8 starts.
9. **U.S form off, then its clubs:** `tools/disable_form.py --form 262382706852058` dry run ->
   `--apply` with Ryan's go (the backup, the POST; or the builder, if the API does not take it -
   the tool says which) -> re-read `DISABLED`. Then `tools/deactivate_clubs.py --region U.S` dry
   run -> `--apply` with Ryan's go -> the re-read and the Audit row -> `GLOW -> Google Forms ->
   Update form dropdowns from the Roster`. A runner dry run: U.S `skipped`, the rest `in-sync`. (The
   template's 11 U.S rosters: `?`-kept until `RETIRE_INACTIVE`; if Ryan says yes, a template dry run
   plans `11 ~ retired roster … no active girl` the day after, and an apply with his go.)
10. `AUTO_SYNC_APPLY=1`; one manual run read through (every region `in-sync` / `skipped`).
11. Apps Script (Roster.gs, FormHandlers.gs): `npm run clasp:push` at a quiet moment with the
    deploy ritual; a test e-mail is not needed (the wording change is covered by
    `test/forms_logic_test.js`). Can be a later day.
12. Docs, DECISIONS (Ryan's answer on `RETIRE_INACTIVE` included), BACKLOG, this plan's Result,
    the work log.

## Risks

- **Rule 3 - the sync rewrites every condition.** A retirement is one `UPDATE club picker` and one
  `REPLACE conditions` per form, generated; nothing hand-made survives, nothing hand-made is needed.
  Africa goes from 251 rules to 213 (38 show rules fewer), the template from 395 to 357 (then 346
  once the U.S 11 retire); the guard rules lose 38 terms each. The loop limit (`19 * (rules / 100 +
  1)`) drops from about 66 to about 59 checks per half-second on Africa - well above what one
  picker change triggers (each rule once); `--rendered` prints the runtime build as always.
- **A required roster with no rule.** Rests on `always-hidden` skipping validation (above):
  proven on the template in step 7 before Africa, and counted by `--rendered` on every later audit.
- **A wrong `no`.** The runner applies at most 5 retirements per region per run; the first 38 are
  by hand. A `no` on the wrong row takes that partner's clubs off within the hour; flipping it back
  restores them within the hour (5 or fewer; more is a hand apply), and nothing on the roster or in
  Salesforce changes in between. Any other value is yes plus ATTENTION. A header typo (`Jotform `)
  is found by header name, case and spacing ignored; a missing column means no partner is marked -
  and then the sync's "no entry and no rule although active" warning and refusal catch the rollout
  state.
- **A truncated Partners export.** Caught by the floor (every partner with an active club must be
  a row): the sync exits, the runner reads `failed`, nothing is restored. Without the floor the
  38 would come back as one picker UPDATE inside every band, and go again with ATTENTION on the
  next run.
- **A forgotten `--partners`** on a hand run: the dry run warns per roster and `--apply` refuses;
  the runner always passes it (and refuses `--roster` without it); `form_status` reads NOT CLEAN.
  Documented in the manual loop.
- **A restore that changes question 5.** Only for a club whose name two partners have had: the
  restore proposes the long name and is a hand apply with `--q5-change-ok` after the Account is
  checked. None of the 38; reachable with `RETIRE_INACTIVE`.
- **Africa applied before the merge:** `main`'s runner would restore the 38 on Africa's next
  roster change. Step 8's order (merge, then Africa) prevents it; `AUTO_SYNC_APPLY=0` from step 7
  to step 10 as for the contact-ids rollout. Between the merge and the Africa apply every runner
  run exits 2 and holds Africa's roster changes - the one-sitting rule in step 8.
- **A two-step roster replacement** (REMOVE every girl, then ADD the new ones minutes later) with
  `RETIRE_INACTIVE` on: the club's last active row goes at the first submission. The
  `removed_date`-before-today rule keeps the club on the picker that day; the next day's run
  retires it if it is still empty, and a later ADD restores it (within the hour; 1 is inside the
  bands).
- **Disabling and deactivating in the wrong order:** deactivating first makes every runner run
  fail on U.S (`read_roster_csv`'s exit) until the form is disabled. Step 9's order, and the
  runner's `skipped` lands on `main` in step 8, before either.
- **The API may not disable a form.** The tool stops and says so; Ryan uses the builder; the dry
  run then confirms `DISABLED`. Nothing else in the plan depends on which way it happened. The
  properties snapshot taken first records the status and message to put back.
- **Parity (rule 10).** Python decides from the marker what the forms carry; Apps Script reads it
  only for an e-mail line. A `no` typed with a zero-width character inside is `yes` on the Python
  side (`glow.text.key` keeps such characters) and `no` to `key_` - the e-mail would say "nothing
  changes on the attendance form" while the clubs stay on it. Named in ARCHITECTURE's divergences;
  the cell is one of three.
- **The Club Roster Form after the U.S deactivation** lists `(no active clubs)` for the six U.S
  partners once the dropdowns are refreshed (appsscript/Forms.gs:343) - the refresh is a step of
  the tool's "Next" lines, because until it runs the dropdown still offers the clubs and a roster
  change would run against the inactive rows (the rows exist, so FormHandlers.gs:834-841 does not
  skip it) and reactivate girls by name. The RUNBOOK section says to re-enroll instead.
- **Privacy.** 751 + 155 girls' names stay on two forms as hidden, frozen roster questions and in
  their translation stores (`base` / `en`), exactly as today. Nothing new is written anywhere with
  a name in it: the tools print counts, club and partner names, row numbers; the Audit rows carry
  counts; `written.json` holds row numbers and the two columns' old values (status, a date).
  Blanking the retired rosters' options is an open decision (below).
- **Late submissions for a U.S club** after the disable: the page shows the disabled message;
  nothing is lost that was not sent. For the three partners the risk is nil (0 genuine submissions
  in five weeks).
- **A new club under a flagged partner** reaches the Roster and SF Pending as today and never the
  form; its mentor e-mail says so. Plan 4's intake decides how its numbers arrive.
- **Session -54.** Its rollout is recorded complete on `main`; this branch merges `main` first
  (step 1) and starts the form-side steps when -54 confirms its window is closed;
  `tools/form_status.py` and `tools/auto_sync.py` are touched by both.

## Proof

Read-only, from the branch after the merge, before any go (the counts assume today's Roster; a
new club moves them by one):

```
# the sync, Africa, a Partners export with the three 'no' cells
python3 sync_attendance_form.py data/roster_<date>.csv --roster --partners data/partners_<date>.csv \
        --region Africa --form 262382821971058
Form: 262382821971058 status ENABLED
Roster: 182 active clubs in Africa (3518 girls); 364 clubs overall; 38 club(s) of 3 partner(s) not on Jotform (Partners tab jotform=no) left off this form
Club picker: q446 (mentors choose their club from a list)
Club guard: q462 (one club per submission)
  ~ retired roster '<club>' (q…): not on Jotform (<partner>, Partners tab jotform=no)      x 38
  conditions: 211 kept, 2 new, 40 dropped          # 38 show rules and the old guard pair go; the new guard pair comes
DRY RUN (use --apply to write):
  - UPDATE club picker (182 clubs: calcValues, options)
  - REPLACE conditions (213 rules)
```

(No `CREATE`, `UPDATE roster`, `REQUIRED`, `UPDATE module dropdown` or `!` line. The split: 251
live rules, 213 planned; the two guard rules lose 38 terms each, so they count as 2 new and 2
dropped beside the 38 show rules; the question-18 sum keeps every roster and is kept. Read the
exact numbers from the run.) The same on the template without `--region`: 38 retired,
`UPDATE club picker (326 clubs: …)`, `REPLACE conditions (357 rules)`, plus whatever backlog the
template has that day. After the U.S deactivation, with `RETIRE_INACTIVE` on, the template plans
11 more `~ retired roster '<club>' (q…): no active girl in the Roster` and `(315 clubs: …)`.

```
# the second dry run after an apply
  (conditions unchanged - skipping the rewrite)
  nothing to do - form already matches the sheet

# the audit, before the Africa apply (step 4) and after it (step 8)
python3 tools/form_status.py --roster data/roster_<date>.csv --partners data/partners_<date>.csv --rendered
Roster (active girls): {'Africa': 179, 'Asia': 95, 'Latin America': 38, 'U.S': 11} clubs per region; not on Jotform: Africa 38
== Africa  262382821971058  "Africa Attendance Form"  [ENABLED]        # step 4, before the apply
   …
   club guard: q462 (220 clubs)
   retired rosters: 0 (not on Jotform 0, no active girl 0)
   rules: 220 show-rules for 220 rosters, Contact_IDs aggregate covers 220  → CLEAN
   vs Roster (179 clubs in region): 0 missing from form, 0 on form but not in roster, 0 rosters differ, 38 await retirement (the next sync apply)
== Africa  262382821971058  "Africa Attendance Form"  [ENABLED]        # step 8, after the apply
   …
   club guard: q462 (182 clubs)
   retired rosters: 38 (not on Jotform 38, no active girl 0)
   rendered retired: 38 retired rosters, 38 always-hidden
   rules: 182 show-rules for 182 live rosters (220 on the form), Contact_IDs aggregate covers 220  → CLEAN
   vs Roster (179 clubs in region): 0 missing from form, 0 on form but not in roster, 0 rosters differ, 38 retired
== U.S  262382706852058  "U.S Attendance Form"  [DISABLED]           # after step 9
   …
   rendered: skipped (form DISABLED)
   vs Roster: skipped (form DISABLED)

# the runner
python3 tools/auto_sync.py --roster data/roster_<date>.csv --partners data/partners_<date>.csv
  => Africa: in-sync
  => Asia: in-sync
  => Latin America: in-sync
  form 262382706852058 is DISABLED - not synced
  => U.S: skipped - form DISABLED
python3 tools/auto_sync.py --roster data/roster_<date>.csv
  --roster needs --partners <Partners export>: …                       # exit 1, nothing read

# the two tools, dry runs
python3 tools/disable_form.py --form 262382706852058
U.S Attendance Form 262382706852058: status ENABLED, 0 submissions (last none)
  messageOfLimitedForm: 'This form is currently unavailable!'
DRY RUN - re-run with --apply to back up the form, then set status DISABLED (then re-read)

python3 tools/deactivate_clubs.py --region U.S --reason "U.S clubs do not report through Jotform (Ryan, 2026-10-06)"
Spreadsheet … as …@….iam.gserviceaccount.com
U.S form 262382706852058: 0 submissions since 2026-09-01 - no club sent attendance in the last 30 days
  <partner>   <club>   16 active row(s)                                   x 11
  Roster      155 row(s) -> status inactive, removed_date 2026-10-0X (310 cells)
  Audit         1 row appended
  Undo        python3 tools/deactivate_clubs.py --undo data/deactivate_clubs/<stamp>
DRY RUN - re-run with --apply to write
```

`make check`: `CHECK PASSED`, the Python test count up by the new tests; `scripts/check_docs_links`
`docs-links: ok`. Pasted here when done, with the live steps' outputs (counts only) under Result.

## Decisions to record (docs/DECISIONS.md)

1. A partner that does not report through Jotform is marked `no` in the Partners tab's `jotform`
   column; the sync keeps its clubs off every attendance form's Club picker while their girls stay
   active and enrolled; `yes` / blank is the default; any other value counts as yes and raises
   ATTENTION. Rejected: a blank region (says "fix me", loses the attribution), a mark in `notes`, a
   Roster column (every Roster writer changes), a Salesforce-only field (the 751 names would stay
   on the form).
2. A roster question whose partner is marked `no` is **retired**: kept on the form, hidden and
   frozen, off the picker and without a show rule, still in question 18's sum; it comes back when
   the mark is lifted. The runner retires or restores at most 5 per region per run. Questions are
   still never deleted. A retired roster whose club's name two partners have had is restored with
   its long name, as a question-5 change by hand. Rejected: keeping the show rule as the roster's
   memory (a rule testing an unlisted entry is what the rollback tool and the runner call broken).
3. "No active girl" as a second trigger is `glow.sync.RETIRE_INACTIVE`, **on** (Ryan,
   2026-10-06), with the `removed_date`-before-today rule.
4. The 11 U.S clubs are deactivated in the Roster (inactive, removed_date, ids kept, ClubRegistry
   untouched; `deactivate_clubs.py --undo` is the way back) and the U.S form is disabled; a
   disabled form is `skipped` by the runner, not failed, and is not synced down to an empty Club
   picker.
5. A Partners export travels with the Roster export: `--partners` on the sync, the runner and the
   audit; a hand run without it refuses to restore a retired roster; an export missing a partner
   with active clubs is refused.

## RUNBOOK sections to add

- **Clubs that do not use Jotform** - the column, who sets it, what the next run does (the `~`
  lines, the picker update, the bands), the way back and the question-5 rule for a shared name,
  the hand-run `--partners` rule, the mentor e-mail wording, what Salesforce shows meanwhile.
- **Deactivating a club** - `tools/deactivate_clubs.py` dry run / `--apply`, the backup path and
  `written.json`, the Audit row, the dropdown refresh, the template's retirements, the way back
  (`--undo`; or the Club Roster Form's hold and release).
- **Disabling a regional form** - `tools/disable_form.py` (the backup, the POST; or the builder),
  what the runner and `form_status` print, the order (disable, then deactivate), re-enabling; the
  five defunct forms' status corrected at :19.

## Open decisions (for Ryan)

- The column name and values (`jotform`: `no` / `yes` / blank) - or `attendance_source`.
- ~~`RETIRE_INACTIVE`: "no active girl = off the picker" for every region, or only the marker and
  the U.S deactivation~~ - **decided 2026-10-06: on**, with the `removed_date`-before-today rule.
- The retired rosters' option lists on the Africa form (751 names) and the U.S form (155): leave
  (recommended for now; the first blanking write to a checkbox question is untested, and the
  disabled U.S form is unreachable) or blank them in a later, tested step (a BACKLOG item).
- The disabled page's text for the U.S form (proposed above), and whether to disable through the
  API first or go straight to the builder.
- `--recent-days` for the deactivation guard (30); `--max-retires` and `--max-restores` for the
  runner (5 each).

## Not verified

- That `POST /form/{id}/properties` with `properties[status]=DISABLED` changes a form's status,
  and that `messageOfLimitedForm` is the text the disabled page shows - learnt on the U.S form
  with Ryan's go, builder as the fallback.
- How the five defunct forms were disabled on 2026-09-30 (not in the repo; builder assumed).
- That a property-hidden, required **checkbox** with no rule is skipped by `validateAll` as the
  skill's reading of the runtime says (`always-hidden`; seen on the served page for q98 / q100 /
  q102, which are not checkboxes) - material, proven on the template in step 7 before any
  regional form.
- The exact `kept / new / dropped` split of the first Africa rewrite (read from the dry run).
- Whether Jotform's disabled page translates (the 2026-09-01 intent's open question).

## Build notes (track T3a - the core, built 2026-10-07 on a branch cut from `wf10/four-issues` at `22342d5`; nothing written to Jotform, the sheet or Salesforce)

**Built as specified** (section A's Python side, `RETIRE_INACTIVE` on, "Retired rosters in the
sync", "Hidden and required, without a rule" (the `--rendered` count), "The way back", "Refusals",
`--summary-json`, "The runner", `form_status`, and section D's runner / sync / `form_status` parts):
`glow/sync.py` (`PARTNER_COLS`, `JOTFORM_COL`, `read_partners_csv`, `RETIRE_INACTIVE = True`,
`roster_removed`, `inactive_retires`), `sync_attendance_form.py` (`--partners`, the export floor, the
`Roster:` tail, the `Form:` line and `--disabled-ok`, the retired decision before the reconcile
loop, the `~` lines, the restore with the long name as an `sf_changes` entry (`RETIRED_OLD`), the
no-export warning and `--apply` refusal, `build_conditions(..., retired=())`, the summary's
`retired` / `restored` / `partners`), `tools/auto_sync.py` (the Partners export beside the Roster,
`--partners`, `--roster` without it refused, `RETIRED_RX` / `RESTORED_RX` / `JOTFORM_VALUE`,
`plan_summary`, the two bands, the status read under `with_retry` -> `skipped` / `failed`, the
odd-value ATTENTION, `verify_report`'s skipped note and awaiting problem), `tools/form_status.py`
(`--partners`, retired / awaiting / stray rosters, the `[DISABLED]` skips of the region check and
`--rendered`, `rendered_retired`), the tests (`RetiredRosters`, `RetiredRostersAudit`, the
plan-line test), CLAUDE.md, RUNBOOK ("Clubs that do not use Jotform", the manual loop, "Automatic
sync", the forms' status at :19), ARCHITECTURE, DECISIONS rows 1, 2, 3 and 5, BACKLOG 1 and 71.
Not this track's: `tools/deactivate_clubs.py`, `tools/disable_form.py`, `appsscript/`,
`tools/build_roster_offline.js`, `tools/upload_roster.py`, the parity test
(`test_partner_columns`), DECISIONS row 4, the RUNBOOK's "Deactivating a club" and "Disabling a
regional form", the two skills' entries (T3b and the live steps).

**Deviations, and why.**

- *The `~ retired roster` line names a retirement this run makes*, not every retired roster: a
  roster the form already holds retired (no rule, no entry of its own) is counted in one line
  (`Retired rosters: N already off the Club picker …`) and in the summary's `retired_before`, and
  the summary's `retired` list carries the new ones only. The plan's band counts `~` lines; printed
  on every run, 38 lines would have tripped it on every run after the Africa apply. The runner's
  dry run on an applied form reads `in-sync` (a test pins it).
- *A roster's own picker entries are its plain text and its own long name* (`<text> - <its
  partner>`) - never a namesake's long entry. Without that, Partner Two's retired "Stars" would
  have read as "on the picker" because "Stars - Partner One" is listed, and would never have been
  restored (`picker_entries` in the sync, `off_picker` with the owner in `form_status`; both tested).
- *`roster_pairs` keeps its shape* (`{(partner, club): active}` - every caller reads the value as a
  flag); the latest `removed_date` per pair is a second reader beside `roster_names`,
  `glow.sync.roster_removed`, and the day rule is `glow.sync.inactive_retires(latest, today)`, read
  at run time (so `RETIRE_INACTIVE` patched off in a test turns it off). A date that does not read
  as `YYYY-MM-DD`, or none, keeps the club as it is (the safe side).
- *`PARTNER_COLS` / `JOTFORM_COL` sit after the `COL_*` sheet-layout constants* at the top of
  `glow/sync.py`: the module has no `ROSTER_COLS` to place them after (the Roster columns live in
  `read_roster_csv`'s `needed` set and `Config.gs`). If T3b placed its two identical lines
  elsewhere, the merge shows two definitions of the same values - delete one.
- *The restore and its refusal run on picker forms with `--roster` only*: the typed-box form (none
  is live) and the enrollment path keep today's behaviour
  (`test_a_form_without_the_picker_keeps_its_rules_byte_for_byte` reaches its own "Cannot
  disambiguate" exit as before).
- *`--apply` is refused on any status other than `ENABLED`* (a status Jotform did not report
  included), not on `DISABLED` alone - refuse rather than guess; `--disabled-ok` passes it.
- *The sync refuses a region whose every active club is marked* (`Every active club in <region>
  belongs to a partner marked jotform=no …`): the form would be synced down to the empty Club
  picker section C calls untested; disable the form instead.
- *The `Roster:` tail is printed only when a club is left off* (an Asia run reads as today).
- *`form_status`*: `load_roster` keeps the names per partner too (a 4-tuple; `form_status` is its
  only reader), `roster_facts` reads the Roster once more for the holders, the active flags, the
  owner read-back (`roster_names`) and the dates; `roster_owner` is the sync's owner rule (one
  holder; else the long name's partner; else the partner whose rows list at least half, and the
  most, of the question's options); a roster off the picker whose owner cannot be told keeps
  today's "0 show-rules" line. `rule_summary` gains `live_rosters`, and the `rules:` line reads
  `N show-rules for N live rosters (M on the form)` only when they differ.
- *The runner's one `Client`* (`run.client`, `max_time=60`) serves the status reads and the storage
  read; the storage test's source assertion follows. `check_bands` reads `--max-retires` /
  `--max-restores` through `getattr` (the tests' argument namespaces predate them).
- *BACKLOG*: row 71 was reserved for this plan by the merged BACKLOG, so the retired-rosters'-options
  item is 71 (not the next free number, 74).
- *The branch* was cut from `22342d5` (the integration branch's merged head at build time, two
  tracks in), not `4ab74fc`.

**Review fixes (2026-10-07, two adversarial reviews; nothing live touched).**

- *The day rule's "today" is the sheet's day, not the UTC date* this plan wrote (section A,
  "RETIRE_INACTIVE"). The sheet stamps `removed_date` with `getSpreadsheetTimeZone()`
  (appsscript/Roster.gs `today_()`), and the spreadsheet's zone is **America/New_York** since
  2026-09-02 (DECISIONS 2026-09-30, `sheets_client.time_zone`) - not `appsscript.json`'s
  `timeZone` (America/Chicago, the script project's, which no stamp uses). Against the UTC date a
  "REMOVE every girl" after 20:00 New York read as yesterday's at the dispatch minutes later, so the
  club left the picker before the "ADD the new girls" put it back - the flicker the rule exists to
  prevent, and the plan's own purpose contradicting its letter. Now `glow/sync.py SHEET_ZONE` and
  `sheet_today()`; the sync and the audit take `today` from it; the tests take theirs from it too
  (the UTC fixture failed live while this was fixed, at 01:xx UTC = the sheet's evening). No
  parity test against `appsscript.json`: it would pin the wrong zone. Nothing offline can read the
  sheet's setting, so the runner, which reads it for SyncLog anyway, compares it with the constant
  on every export (`Run.check_sheet_zone`: a log line, or an ATTENTION that stops nothing).
  DECISIONS row 3, the RUNBOOK's section, ARCHITECTURE's constants table and CLAUDE.md rule 7 say so.
- *A Partners export without the `jotform` column* was read silently as "nobody marked", and with
  `--partners` given (the runner always) a retired roster of an active club was restored - the
  risk list's "a missing column is caught by the no-`--partners` warning and refusal" named the one
  path the runner never takes; 38 on Africa would have tripped the restore band, a region holding
  five or fewer retired rosters would not. Now `read_partners_csv` warns (a `!` line, so the
  runner's `plan['warnings']` carry it), `partners_marker_present` tells the sync, `--apply`
  refuses to restore from such an export, and the runner raises ATTENTION (`JOTFORM_COLUMN`,
  `no_jotform_column`) and holds a plan that restores anything from it (`check_bands`). A run with
  nothing to restore goes on `in-sync` with the ATTENTION. DECISIONS row 5 and the RUNBOOK's marker
  paragraph say so.
- *A form whose GET reports no status* made `form_status` fall over (`{"skipped": None}` is falsy,
  so `main()` went looking for the clubs count): the marker is now `status or "status not
  reported"`, the served-page skip and the header line the same; one test.
- *The docs' parity claim*: the RUNBOOK's mentor-e-mail sentence now says "once that change is
  pushed (the plan's step 11)". `Roster.gs PARTNER_COLS` (four entries) and `test_partner_columns`
  are track T3b's; CLAUDE.md rule 7 and ARCHITECTURE's Partners row are true once both tracks are
  merged - the orchestrator's `make check` on the merged branch is what confirms it.

**Read-only rehearsal (plan step 4), 2026-10-07 01:20 UTC, key from the environment, GET only.**
No `data/partners_*.csv` existed, so a scratch export was built from the 2026-10-06T1047Z Roster
export's partner column (49 partners, their regions, `no` on the three rows) at
`data/scratch_partners_2026-10-06.csv` (gitignored). Partner organisations and club names only;
no girl's name read out.

```
# the sync, Africa
Form: 262382821971058 status ENABLED
Roster: 182 active clubs in Africa (3518 girls); 364 clubs overall; 38 club(s) of 3 partner(s) not on Jotform (Partners tab jotform=no) left off this form
Club picker: q446 (mentors choose their club from a list)
Club guard: q462 (one club per submission)
Same-name clubs: 6 roster(s) on this form send '<club> - <partner>' to question 5 (each has its own Club picker entry)
  ~ retired roster '<club>' (q…): not on Jotform (<partner>, Partners tab jotform=no)   x 38 (6 / 16 / 16 by partner)
  conditions: 211 kept, 2 new, 40 dropped
DRY RUN (use --apply to write):
  - UPDATE roster … (q…, N girls)                             x 3 (the day's roster drift: the 10-06 export against the form on 10-07)
  - UPDATE club picker (182 clubs: calcValues, options)
  - REPLACE conditions (213 rules)
exit 0; no '!' line, no '?' line, 0 restored

# the sync, the template (no --region)
Form: 262352490535154 status ENABLED
Roster: 326 active clubs (6178 girls); 364 clubs overall; 38 club(s) of 3 partner(s) not on Jotform (Partners tab jotform=no) left off this form
Same-name clubs: 7 roster(s) …
  ~ retired roster …                                          x 38
  conditions: 355 kept, 2 new, 40 dropped
DRY RUN (use --apply to write):
  - UPDATE club picker (326 clubs: calcValues, options)
  - REPLACE conditions (357 rules)
exit 0 (no backlog: -54's 22 rosters are applied)

# the audit, --partners, the five live forms (no --rendered)
Roster (active girls): {'Africa': 179, 'Latin America': 38, 'Asia': 95, 'U.S': 11} clubs per region; not on Jotform: Africa 38
storage: … -> ok; … -> ok; plan SILVER
== template …  retired rosters: 0 (not on Jotform 0, no active girl 0)   rules: 364 show-rules for 364 rosters … → CLEAN
== Africa …    retired rosters: 0 (not on Jotform 0, no active girl 0)   rules: 220 show-rules for 220 rosters … → CLEAN
   vs Roster (179 clubs in region): 0 missing from form, 0 on form but not in roster, 3 rosters differ, 38 await retirement (the next sync apply)
== Asia / Latin America / U.S: → CLEAN, retired rosters 0, vs Roster 0 / 0 / 0, all [ENABLED]

# the runner, --roster … --partners …, --out under the scratchpad (nothing written anywhere)
Partners: using …/scratch_partners_2026-10-06.csv
== Africa:  Form: … status ENABLED … 38 ~ lines … UPDATE club picker (182 clubs …), REPLACE conditions (213 rules)
  => Africa: attention - would take 38 clubs off the Club picker at once (band: 5) - a partner newly marked jotform=no, or a wrong cell on the Partners tab? apply by hand after checking
  => Asia: in-sync
  => Latin America: in-sync
  => U.S: in-sync          (every form ENABLED today: no skipped)
storage: … -> ok
ATTENTION: 1 item(s): "Africa: not applied - 0 create(s), 3 update(s), 0 delete(s), 0 warning(s), 38 retired, update club picker", 38 "- RETIRE …" lines; exit 2
```

The counts are the Proof's (182 / 3518 / 364 / 38; 211 kept, 2 new, 40 dropped; 213 and 357
rules; 326 clubs on the template). The three roster updates on Africa are the day's drift, not this
plan's. `test/python_test.py`: 528 tests, `OK` (506 before); `scripts/check_py.py`: 49 files parse,
27 scripts answer --help; `check_secrets.py --file` clean on every changed file; `check_docs_links.py`
ok. Step 7's headless-Chrome check of the `always-hidden` reading and the live steps wait for Ryan's
goes; the session's work-log entry is the orchestrator's (not run from this worktree).
## Build notes (T3b - B, C, D and the Apps Script half of A: the two tools, Roster.gs / FormHandlers.gs, the Partners-tab mirrors; built 2026-10-07 offline on the workflow's branch, nothing written to any live system)

- `glow/sync.py` has no `ROSTER_COLS`, so `PARTNER_COLS` and `JOTFORM_COL` sit directly after the
  sheet-layout column constants (`COL_ROSTER`), as the two bare lines the track instructions
  prescribe (T3a adds the same two lines; the merge is meant to keep one copy).
- `tools/deactivate_clubs.py` imports its cell helpers (`tidy`, `cell_key`, `nfc_key`, `a1`,
  `col_letter`, `describe_rows`, `trimmed`) from `tools/rename_club.py` rather than copying them.
- The guard reads `GET /form/{id}/submissions?limit=1000&offset=…&filter={"created_at:gt":…}`
  (URL-encoded), pages until a short page, and drops a repeated id; the form's `count` is not
  compared (a filtered read has no count to compare with). The cut-off compares `created_at`'s day
  (US Eastern) with the sheet's day minus `--recent-days`: a day's fuzz on a 30-day guard.
- `--check-only` needs the sheet (the clubs come from the Roster tab) and the key (the form); it
  reads both and writes nothing. `--reason` is required with `--apply` only (the Audit row's text).
  A chosen club whose rows carry a region that is no form's (blank, misspelled) stops the run
  before the guard: there is no form to read for it.
- The backup folder (`Roster.csv`, `written.json`) is saved before the stale re-read, as
  `rename_club.py` saves its tabs; a folder left by a run that stopped there is harmless to `--undo`
  (its rows are not in the recorded state, so the undo refuses them). `written.json` records the
  columns written (indexes), the values set, the reason, the clubs with their regions and row
  counts, and per row the number, partner, club and the two old values - never a girl's cell.
- `--undo` also refuses when a chosen club has an ACTIVE row at the time of the undo that
  `written.json` does not name (one came back, or was enrolled, meanwhile): "refuse rather than
  guess" - the plan's "one of those rows has changed since" read broadly. Both checks run before
  the plan (the dry run refuses too, and saves no `undo-<stamp>` folder) and name the rows and
  their clubs; the remedy is per club - the club leaves `written.json` with its rows AND its
  `clubs` line (half an edit is refused by name), the rest go back, its own rows are a hand job -
  so it cannot loop: a row taken out alone would be "active and not in written.json" on the next
  run. `write_cells`' re-read stays as the race guard for the window between the plan and the
  write, worded for each path. A row of a chosen club that arrives during a deactivation's write is
  left active, named with `!`, audited with the rest and the tool exits 1 (no second batch: a girl
  added to a club being retired is a human's call).
- `tools/disable_form.py` reads both `GET /form/{id}` and the properties and refuses when their
  statuses disagree; "already DISABLED - nothing to do" when the status is the wanted one and no new
  `--message` is given; `--enable` takes no `--message`. The POST carries only what differs.
- `appsscript/FormHandlers.gs`: the Partners read for the closing line runs inside the two
  senders' `try`, so a failed read costs the mentor e-mail, never the handler (REVIEW pass 2).
- RUNBOOK :19 (the five defunct forms are `DISABLED` since 2026-09-30) is corrected here, with
  "Disabling a regional form"; BACKLOG 1 itself is T3a's edit. No `docs/ARCHITECTURE.md` constants
  row (T3a adds it); the tool-table rows are added here.
- **Read-only proof, 2026-10-07 (the live sheet through the service account, the live forms with
  the key; nothing written):**

  ```
  Africa form 262382821971058: 231 submissions since 2026-09-01 read
    Tumaini La Maisha                 16 club(s)    1 submission(s)  (last 2026-09-25; 1 picked together with another club)
        'Adonai GLOW Club': 1 submission(s), 2026-09-25
  --check-only: 320 active row(s) of 16 club(s) would be deactivated; nothing planned, nothing written
    Education and English for You      6 club(s)    0 submission(s)       # 114 active rows
    Ng'aa Maskani                     16 club(s)    0 submission(s)       # 317 active rows
  U.S form 262382706852058: 0 submissions since 2026-09-01 read
    6 partners, 11 club(s), 0 submission(s) each
  --check-only: 155 active row(s) of 11 club(s) would be deactivated; nothing planned, nothing written

  U.S Attendance Form 262382706852058: status ENABLED, 0 submissions (last none)
    messageOfLimitedForm: 'This form is currently unavailable!'
  DRY RUN - re-run with --apply to back up the form, then set status DISABLED (then re-read)
  ```

  As B expected: 0 / 0 / 1 (the 2026-09-25 two-club pick), U.S 0. Not run: `--apply` of either
  tool (steps 9-10, Ryan's go), `--undo` on the live sheet, the Apps Script push (step 11).

- **Review fixes (2026-10-07, two adversarial reviews; eight findings, all applied):**
  - The undo's remedy loop above (its message named an edit that `write_cells` then refused) and
    the late timing of its active-row check: both checks now before the plan, the per-club remedy.
  - B's match rule refined: `key(value) == key(club)`, or `== key(club) + SF_NAME_SEP + key(partner)`
    - the exact long form of the club's own partner (`sf_club_name`), where B wrote
    `startswith(key(club) + SF_NAME_SEP)`. The prefix rule would have credited a club with a
    same-region namesake's `<club> - <other partner>` submissions (none of today's 38 + 11 shares
    a name; three Africa names have two holders). Still never a bare prefix; the unit test pins
    `'Ruby - Partner Two'` as not Partner One's `Ruby`.
  - Beyond the plan, as defence in depth for step 9's order: when the chosen clubs are every
    active club of a region (`whole_regions`), the guard also reads `GET /form/{id}` and a status
    other than `DISABLED` is printed with `!`; `--apply` refuses without `--form-enabled-ok`
    (deactivated first, every runner run fails on the empty region). One read-only GET more; the
    tests' fake has the U.S form `DISABLED` by default, the RUNBOOK's order.
  - `appsscript/Roster.gs` `loadPartnerJotform_` finds the column by the Partners tab's header row
    (`key_`, so ` Jotform ` counts), as T3a's `read_partners_csv` reads the export by header - not
    by `PARTNER_COLS`' position, which the parity test had pinned as if it were a name lookup. A
    tab without the header marks nobody. Both sides now agree wherever the column sits, so no new
    divergence row for ARCHITECTURE; the JS test moves the column once.
  - `tools/disable_form.py`: the two-statuses-disagree exit says, on the re-read after the POST,
    that the write was sent and to re-run without `--apply` until both GETs agree (the same
    `read_form` had said "before anything is written" on both reads).
  - CLAUDE.md rule 7 lists `PARTNER_COLS` (and the offline builder's copy) - this track's, with the
    parity test; T3a's CLAUDE.md edits are the `--partners` command lines and rule 6.
  - RUNBOOK "Deactivating a club" refers to T3a's section as "the section on clubs that do not use
    Jotform" rather than by a quoted heading this branch cannot see, so a heading change cannot
    orphan it (`check_docs_links.py` checks file links only).
