---
title: One attendance total for leadership that includes the partners who report counts, with the per-girl figures labelled Jotform only, and the clubs that did not submit or sent a blank in plain view
author: Claude (with Ryan's decisions of 2026-10-06)
status: done             # F (the intake) open: BACKLOG 72; accepted by Ryan 2026-10-06 (in conversation), with the defaults of the "Open decisions" unless noted in the plan; A + B deployed 2026-10-07 03:22 UTC, C done 2026-10-07, D deployed 2026-10-07 03:59 UTC (Result); F was planned as its own plan from the start (Order of work, step 7)
done: 2026-10-07
backlog: 72, 73
created: 2026-10-06
intent: docs/intent/2026-10-06-attendance-totals.md
---

# Plan: attendance totals that include the three partners, "did not submit" and "blank" views, and a blank is never a success

## Context

Ryan's decisions of 2026-10-06 (in conversation), as they bear on this plan:

- **Report** (decision 2): "did not submit" for three windows - rolling 14 days, never since
  1 September, last calendar month (exists) - plus a "submitted a blank" report. A `Failed`
  duplicate counts as submitted. **No new Jotform rule** for blanks; instead an **Apex
  backstop**: a batch with no names is marked `Failed` "No participants" instead of `Success`,
  exempting aggregate batches (`Girls_Present__c` > 0). Non-reporting clubs are excluded at the
  source, not with a **Salesforce-side** marker: the sheet-side `jotform=no` marker of the
  [clubs-off plan](2026-10-06-clubs-off-jotform.md) takes them off the forms (decision 5), and
  their monthly aggregates (decision 4) are what makes them "submitting" here; nothing on the
  Account says which source a club uses. (The stored message in this
  plan is the fixed literal "No participants submitted" - Ryan's words plus one; see B.)
- **Aggregates** (decision 4): per **club** per **month**, as `Attendance_Batch__c` records with
  a new number field `Girls_Present__c` - set by Apex for Jotform batches (= the rows created),
  typed for aggregates; `Creator__c` says where a batch came from (e.g. `Partner report`). One
  custom report type on batches gives total attendance and "Jotform only" (a `Creator__c`
  filter); the distinct-girl tiles are labelled Jotform only. **The intake method is not
  decided** (section F); the Salesforce side is built so any intake works.
- **Hygiene** (decision 5, last sentence): the two stray WESAD accounts were re-parented on
  Ryan's go at 10:53 UTC the same day, before this plan was written (main `00ee471`); E below
  records it and leaves only BACKLOG 27's cadence.

What Salesforce holds today (read 2026-10-06 through the read-only connector, after the
re-parent; the 10-06 read-only investigation is the source for anything not re-read here). File and line
numbers in this plan are **main's after `00ee471` and the wf9 merge `3ea1cab`** (RUNBOOK's
Salesforce sections sit 192 lines lower there than in this branch's base `50126b3`; the
`python_test.py` import block two lines lower), since main is merged before the plan is
committed (Order of work, step 1). `main` has since moved to `9d58ce4` (-54's Result: docs only -
BACKLOG 65, one RUNBOOK line, its plan - so the code lines hold; BACKLOG 65 is that residual's row,
which B closes):

- `Attendance_Batch__c`: 565 batches = 538 `Success` + 27 `Failed`. 554 since 1 September =
  361 back-fill + 193 live "Jotform" (166 Success, 27 Failed, all 27 "Duplicate:"); the 11
  February pilot batches (all `Creator__c` "Jotform", all Success) make the 565. 534 batches
  have attendance rows; **4 `Success` batches have
  none** (one February pilot, and Maejan / Friends of Thai Daughters 2026-09-30, Girls Shine
  Forever Glow Club / See Them Grow Foundation 2026-10-01, United Girls / Feminature Uganda
  Limited 2026-09-30 - the three blanks since launch). The object has **no count field**: its
  custom fields are `Account_Name__c` (required text), `Account__c`, `Attendance_Date__c`,
  `Contact_IDs__c`, `Creator__c`, `Module__c`, `Module_Week__c`, `Module_Year__c`,
  `Processing_Status__c` (Pending / Success / Failed), `Status_Message__c` (255),
  `enable_fuzzy_matching__c`. `Attendance__c` → batch is a lookup (relationship
  `Attendances__r`), so there is no roll-up summary.
- 7,041 `Attendance__c` rows in all, 6,177 dated September. Clubs with a partner: **364**; with
  no batch of any status since 1 September: **182**; with none dated in the last 14 days: **202**;
  with none dated last month: **194** (the live row-based tile says 196: the two clubs whose
  only September submissions were blanks). All four re-read after the re-parent.
- Club accounts without a parent: **2**, the two pilot accounts on hold (the RUNBOOK's expected
  value, `:1683`). `Change Makers` (001RP00000yQZcJYAW, 20 rows) and `Seeds of Greatness`
  (001RP00000yQbB3YAK, 19 rows), created partner-less by the processor on 2026-10-03, carry
  `ParentId` = 001RP000002nR7mYAE ("World Economy Skills and Agro Development (WESAD)") since
  2026-10-06 10:53 UTC; WESAD has **30** clubs.
- The live Jotform integration creates batches as a user on the **System Administrator**
  profile (all 204 "Jotform" batches, pilots included); the 7 active users with View All Data
  are all System Administrators (plus one system integration user).

The processor (the repo's copy of what Ryan deployed on 2026-10-02:
`data/sf_processor_2026-10-02/after/force-app/main/default/classes/AttendanceBatchProcessor.cls`;
the deployed class itself cannot be read through the connector, so step 2 retrieves it again
first):

- `process` → `processBatch` per batch (:59-65, :82-96): `resolveClubAccount` (:102-109; a
  name no account carries creates a partner-less Club account, :186-196), then
  `isDuplicateBatch` (:116-122; "Duplicate: A successful batch already exists for this account
  and date." - the check looks at `Success` batches only, :221-233), then `processParticipants`
  → `markBatchSuccess` (:462-465, "Processed successfully.").
- `processParticipants` (:240-291): rows already on that club and day → `Failed` "Attendance
  already exists for this club on …" (:241-247); `parseParticipantNames` returns an **empty list
  for a blank `Contact_IDs__c`** (:314-317), the loops then do nothing and the method returns
  `true` (:290): **a blank is a `Success` with no rows**, and it blocks the club's day.
- Every distinct name becomes exactly one `Attendance__c` row (:254-288); the status record is
  `ctx.statusUpdate` (:37-40), written in `saveRecords` (:482-503) after the rows (:488, :494).
- The trigger runs **after insert only** (`AttendanceBatchTrigger.trigger:1-3`), so an update of
  a batch (the back-fill in C) runs none of this.

Repo code that depends on today's rule:

- `tools/sf_backfill.py:5-9` (docstring: "stores a batch without names as a Success that blocks
  the real one"), `:603-615` (the `salesforce_has_empty_or_failed_batch` hold and its detail text
  "the day is blocked until that is removed", `:614`), `:756-765` (the plan's list of batches
  without attendance: "each blocks that day for a later batch", `:762-763`), `:825-836`
  (`outcome_of`, the kinds of status message), `:853-896` (`verify`), `:911-916` (`send_one`
  refuses a club and day that has any batch or any row).
- `test/sf_backfill_test.py:5-8` and the fake org's `insert` (:117-158: blank names → a
  `Success` without rows), `test_what_salesforce_already_has_for_a_club_day` (:398-421; `:419-421`
  assert the listing's text and its `BATCH-000001 Success` line) and
  `test_send_proves_each_batch_against_salesforce_first` (:562-566).

The dashboard generator (`data/sf_dashboard_2026-10-02/gen.py`, session -51's; `after2/` +
`fix1/` = live): column constants `:20-25`, `criteria` `:32-35`, `ROW_FILTER` `:38-44`,
`row_report` `:63-76`, the six reports `:80-109` (`INTERVAL_THISMONTH` at `:102` is `fix1`), the
no-attendance report `CLUBS_WITHOUT` `:111-138` (cross filter `:113-120`: `without`
`Attendance__c` joined on `Account__c`, `Attendance_Date__c equals LAST_MONTH`, `Creator__c
equals AttendanceBatchTrigger`), `component` `:157-183` (`dashboardFilterColumns` `:164`, default
`Account$Parent`), the tiles `:186-225` (the no-attendance metric and the one-row-per-partner
table at `:213-225` use `PARENT.NAME` as their filter column - `fix1`), the How-to box `:233-249`
(`fix1`), the 49-value Partner filter `:251-254`.

Related: [dashboard plan](2026-10-02-attendance-dashboard.md) (read-back method `:160-181`,
`fix1` `:182-192`, the strays and their re-parent `:214-224`, written by `00ee471`);
[processor plan](2026-10-02-attendance-processor-one-insert.md)
(how the class was validated and deployed: 21 of 21 tests with `TestContactTriggerHandler`,
coverage 92%, `:78-79`; the rolled-back anonymous proof run, `:59-60`); [September back-fill](2026-09-30-september-backfill.md) (the hold table
`:94-106`); [Monthly Report checkbox](2026-09-30-monthly-report-checkbox.md) (field permission
on the System Administrator profile only, `:107-108`; "which other profiles" open, `:117`);
[Club accounts](2026-09-30-salesforce-clubs.md); RUNBOOK "Club accounts in Salesforce"
(`:1669-1699`), "Back-fill of attendance into Salesforce" (`:1763-1825`), "Attendance dashboard
in Salesforce" (`:1827-1947`); BACKLOG 27 (`:73`, its last sentence written by `00ee471`), 35
(`:81`), 48 (`:94`), 55 (`:101`), 58-61 (`:104-107`); main's 62-64 are the wf9 rows and 65 the
question-18-empty resend residual (`9d58ce4`: "a Salesforce backstop … is planned in another
session" - this plan's B); the sibling plans of this day take 66-67 (module), 68-70 (photos) and
71 (clubs-off: the retired rosters' options).

## A. Salesforce schema

**`Attendance_Batch__c.Girls_Present__c`** - Number(18, 0), label "Girls present", not required,
no default. Description (in the field): "Girls counted present for this batch. Set by the
attendance processor when a Jotform batch succeeds (= its attendance rows). Typed for a partner-
reported total (Creator 'Partner report'), which carries no names and creates no rows. Empty on
Failed batches, and on batches from before 2026-10 until the one-off back-fill." Metadata:
`force-app/main/default/objects/Attendance_Batch__c/fields/Girls_Present__c.field-meta.xml`
(`<type>Number</type>`, `<precision>18</precision>`, `<scale>0</scale>`, `<required>false</required>`,
`<externalId>false</externalId>`, `<trackTrending>false</trackTrending>`).

**`Attendance_Batch__c.Girls_Enrolled__c`** (BACKLOG 58) - **recommended: create it now, empty, no
behaviour.** Same type, label "Girls enrolled", description "Girls active on the club's roster on
the session date, from the enrollment sheet (BACKLOG 58). Not filled yet." Why now: it rides on
the same field deploy and the same permission pass, the report type (D) lists it once instead of
being redeployed later, and the back-fill tool in C is the tool 58 will extend. Why not: an empty
column exists until 58 is built; it is kept off every report and tile until then, so nobody reads
a zero. If Ryan prefers not to carry an empty field, strike it here and in D; nothing else
changes.

**The partner on a batch report: the lookup path first, a formula field only as the fallback**
(amended 2026-10-06 on session -51's advice, from its two deploys). The batch reports in D group
and filter by partner, and the dashboard's Partner filter needs a column on each component's
report whose values are the partner names. The custom report type carries the club's parent
**"via lookup"** - `Account__c` → Parent (Name) added to the report type's fields, the column then
of the shape `Attendance_Batch__c$Account__c.Parent` (the exact token is read from the deployed
type's describe, `GET /services/data/vXX.X/analytics/reportTypes/<type>`); this org's own DHIS2
dashboard already filters on such a via-lookup column (`DHIS2__c$Account__c.Assigned_Partner_Manager__c`),
so the pattern is proven here, and it needs no new field, no field-level security and no extra
deploy. Only if the check-only validate refuses the two-hop path does the plan fall back to
**`Attendance_Batch__c.Partner__c`** - formula (Text) `Account__r.Parent.Name`, label "Partner",
read permission on the Admin profile - whose use as a dashboard **filter column** is itself
unverified (D.3, Risks). Either way the value is blank for a partner-less club (today only the two
pilots on hold). **Settled 2026-10-07**: the via-lookup path works - Analytics token
`Attendance_Batch__c.Account__c.Parent.Name`, metadata `Account__c.Parent` in the type and
`Attendance_Batch__c$Account__c.Parent` on the reports and as the filter column; the `Partner__c`
formula was not created (Result).

**Field-level security.** The 2026-09-30 deploy gave its new field read/edit on the System
Administrator profile only ([plan](2026-09-30-monthly-report-checkbox.md) `:107-108`), and
"which other profiles" is still open (BACKLOG 55). Here that is enough for everything this plan
does: the live integration user, the dashboard's running user (Ryan) and the 7 users who can
open the hidden Attendance folders are all System Administrators (read 2026-10-06). Apex sets the
field in a trigger, where field permissions are not checked. So: `profiles/Admin.profile-meta.xml`
with `<fieldPermissions>` read + edit for `Girls_Present__c` and `Girls_Enrolled__c`, read for
`Partner__c` only if the fallback formula is created (a formula is read-only), in the same deploy. If the intake (F) ends up with a user
on another profile typing the counts, that profile needs edit on `Girls_Present__c` then - with
that plan.

## B. Apex backstop: a blank is never a success

**The change**, in `processParticipants`, right after `parseParticipantNames`
(`AttendanceBatchProcessor.cls:250`):

- **blank `Contact_IDs__c` and (`Girls_Present__c` null or 0)** →
  `markBatchFailed(ctx.statusUpdate, 'No participants submitted')`, `return false`, no rows.
  The message is a fixed string (nothing of the submission in it, so it can never quote a name)
  and the exact value the reports filter on with "equals": **one literal in the Apex constant,
  the Apex tests, the report criterion and this plan.** Ryan said `Failed` "No participants";
  the plan extends it by one word so the message reads as a sentence next to "Processed
  successfully." - listed under "Decisions to record" for his confirmation; if he prefers his
  exact words, the literal changes everywhere at once (`outcome_of` below matches the prefix
  either way).
- **blank `Contact_IDs__c` and `Girls_Present__c` > 0** → an **aggregate batch**: `return true`
  with no rows; `markBatchSuccess` then runs as today and `Girls_Present__c` stays as typed.
- **non-blank** → exactly as today (:254-288), then one line before `return true` (:290):
  `ctx.statusUpdate.Girls_Present__c = matches.size();` - the number of `addAttendanceRecord`
  calls (:283-288), one per distinct name, which is the number of rows `saveRecords` inserts
  (:488; a failing insert throws and rolls the whole batch back, :501, so the count can never
  disagree with the rows). A batch that carries names **and** a typed count gets the rows'
  count: names win.

What does **not** change: `resolveClubAccount` (a mistyped `Account_Name__c` still creates a
partner-less account - the intake contract in F guards against it), `isDuplicateBatch` and
`hasAttendanceForClubOnDate` (an aggregate `Success` for a club and date blocks a Jotform batch
for that date with "Duplicate: …", and rows on that date block an aggregate with "Attendance
already exists …" - both stated here on purpose; aggregates are therefore **dated the last day of
the month** they report, a day the three partners' clubs never send a Jotform batch for, and
those 38 clubs leave the Africa form anyway under decision 5), the statuses and their texts,
the 255-character cut in `markBatchFailed` (:472-477), the one-insert design of 2026-10-02.

A `Failed` "No participants submitted" batch blocks nothing: `hasDuplicateSuccessfulBatch`
looks at `Success` only (:230), and the blank created no rows. So the club's real submission for
that day goes through afterwards - the point of the change. The Jotform integration never sees
the status (it inserts the record; the trigger sets the status after), so a blank still
"succeeds" on the Jotform side and nothing retries.

**Tests** (`AttendanceBatchTriggerTest`, 18 methods today; the 10-02 validation ran 21 with
`TestContactTriggerHandler`):

- `testEmptyParticipantList` (:549-573) flips: `Failed`, `Status_Message__c` equals
  "No participants submitted", 0 rows.
- new `testAggregateBatchWithoutNamesSucceeds`: blank names, `Girls_Present__c = 25` →
  `Success`, "Processed successfully.", 0 rows, `Girls_Present__c` still 25, `Account__c` set.
- new `testAggregateWithZeroCountIsNoParticipants`: blank names, `Girls_Present__c = 0` →
  `Failed` "No participants submitted".
- new `testGirlsPresentEqualsRowsCreated`: three names, one of them twice → `Girls_Present__c`
  = 2 = rows (extends the 2026-10-02 repeated-name case, :644-664).
- new `testBlankDoesNotBlockTheDay`: a blank batch, then a batch with names for the same club
  and date → the second is `Success` with its rows (the behaviour change this plan buys).
- new `testAggregateBlocksJotformBatchSameDay`: an aggregate `Success`, then a names batch for
  the same club and date → `Failed` "Duplicate: …" (the collision, pinned so nobody is surprised).
- Fictional names only, as the class already does; the repo never quotes them.

**Deploy** (one package: the three fields, the profile permissions, the class, the test class):
retrieve the live class, trigger, test class and object first into `data/sf_totals_2026-10/before/`
(the rollback; the 10-02 `after/` copy is not trusted as "live" without a re-read), edit in
`data/sf_totals_2026-10/after/`, then
`sf project deploy validate -o glow -d force-app -l RunSpecifiedTests -t AttendanceBatchTriggerTest -t TestContactTriggerHandler`
(check-only; the tests run in the org; nothing changes). Expected: every test passes (18 + 5 =
23 in the class, 26 with the other class), the class's coverage ≥ 75% (92% before). Ryan then
runs `sf project deploy quick -o glow -i <validation id>` at a quiet moment (a submission at that
second runs the old or the new code, both complete). Proof after: retrieve and compare with
`after/`; one **rolled-back anonymous Apex run** in production (as on 2026-10-02, [processor
plan](2026-10-02-attendance-processor-one-insert.md) `:59-60`: a savepoint, a blank batch and an
aggregate batch inserted for a made-up club name, the three outcomes asserted,
`Database.rollback`) - nothing left behind. **This run is a Salesforce write path** (`sf apex run`
inserts a batch, a Club account and Contacts in production for the length of the transaction;
`.claude/hooks/live_gate.sh` matches no `sf` command): it is made **on Ryan's go in the
conversation, or run by Ryan**, and the script is pasted in full first. An uncaught exception
before `Database.rollback` also rolls the anonymous transaction back (anonymous Apex is one
transaction; nothing it inserted survives an exception), so the only way it leaves a record is a
script that reaches its end without the rollback call - which the pasted script makes visible.
The live-systems skill lists it as a write path (Files that change).

**Effect on `tools/sf_backfill.py` and its tests** (repo work, same branch):

- The docstring `:5-9` ("stores a batch without names as a Success that blocks the real one")
  becomes "stores a batch without names as Failed 'No participants submitted', which blocks
  nothing (before 2026-10: a Success with no rows that blocked the day)". In the RUNBOOK the
  change lands by line, not by a phrase: the back-fill contract at `:1788-1789` ("no batch
  without names" - still the tool's rule, with one clause on why: the processor now refuses one)
  and the `CHECK` paragraph at `:1816` ("its rows block that club and day" - still true, since a
  `CHECK` batch has rows; one sentence added: a `Failed` batch without rows blocks nothing);
  the September history at `:811` ("stored as an empty *Success* batch that blocks the club's
  real batch") gets "(until 2026-10; since then Failed 'No participants submitted')".
- The hold `salesforce_has_empty_or_failed_batch` (`:613-614`) **stays**: the tool never adds to a
  club and day that has any batch (`send_one` refuses on any batch or any row, `:911-916`,
  and that is its contract, RUNBOOK `:1788-1789`). Its detail text changes from "the day is
  blocked until that is removed" to "this tool never adds to a day Salesforce has a batch for;
  a Failed batch no longer blocks the processor itself", because the first half is no longer
  true for a `Failed` one.
- The `plan` command's listing (`:762-763`, "Salesforce holds N batch(es) … without any
  attendance for their club and day - each blocks that day for a later batch") says the same
  thing and becomes just as untrue for a `Failed` one: it changes to "… - a Success among them
  blocks that day for a later batch; this tool never adds to a day with any batch". The test
  that asserts the line (`test/sf_backfill_test.py:419`) follows.
- `outcome_of` (`:825-836`) learns the new kind: a message starting "No participants" →
  `no_participants` (the tool prints kinds, never the text).
- `verify` (`:853-896`) adds `Girls_Present__c` to its SELECT (`:855-856`) and one more equality:
  `Girls_Present__c == counts["n"]`, so a back-filled batch whose count disagrees with its rows
  is `CHECK`.
- `test/sf_backfill_test.py`: the fake org's `insert` (`:117-158`) follows the processor - blank
  names → `Failed` "No participants submitted" unless the body carries `Girls_Present__c` > 0;
  a success sets `Girls_Present__c` = rows. The docstring `:5-8` says so.
  `test_what_salesforce_already_has_for_a_club_day` keeps its two holds (`:415`) but the listing
  text asserted at `:419` carries the new wording and the line at `:420` reads
  `BATCH-000001 Failed …`; `test_send_proves_each_batch_against_salesforce_first`
  (`:562-566`) keeps its refusal (any batch on the day), its comment changes. One new test: a
  verify whose `Girls_Present__c` differs from the rows is `CHECK`. The suite stays offline.
- `test/python_test.py:49` imports these tests already; nothing to add there.

**The three legacy blank `Success` batches** (and the February one): **left as they are** - they
predate the rule, hold no rows and no names, and after the back-fill in C they carry
`Girls_Present__c = 0`, which is exactly how the blank report (D) finds them. Each still blocks
its club's day (Maejan 09-30, Girls Shine Forever 10-01, United Girls 09-30) for a late
re-submission; if Ryan wants those days open, the three are deleted with his go (three record
deletes, no rows to remove; rollback = none needed), and the plan notes it. Default: leave.

## C. One-off back-fill of `Girls_Present__c`: `tools/sf_girls_present.py`

A standard-library argparse tool, `print()` only, built like `tools/sf_backfill.py` and reusing
its `Org` (`:168-238`: the CLI's token read into memory and handed to curl on stdin, never on a
command line), `Refused`, `quoted` and `API`:

```bash
python3 tools/sf_girls_present.py plan --vpn-off          # live, read-only -> data/sf_girls_present/plan.csv
python3 tools/sf_girls_present.py set                     # dry run: what the plan would write
python3 tools/sf_girls_present.py set --apply --vpn-off --limit 1   # Ryan's go: one batch, read back
python3 tools/sf_girls_present.py set --apply --vpn-off   # the rest, one PATCH per batch, each read back
python3 tools/sf_girls_present.py check --vpn-off         # read-only: Jotform batches whose count differs from their rows
```

- `plan`: `SELECT Id, Name, Processing_Status__c, Creator__c, Girls_Present__c FROM Attendance_Batch__c`
  and `SELECT Attendance_Batch__c, COUNT(Id) n FROM Attendance__c GROUP BY Attendance_Batch__c`
  (ids, counts and statuses only - never `Contact_IDs__c`, never a Contact). Writes
  `data/sf_girls_present/plan.csv` (batch id, name, status, creator kind, rows, current value)
  and prints: `batches: 565 (538 Success, 27 Failed); to set: 538 Success batches with no Girls
  present (534 with rows, 4 with none, 7,041 rows); Failed batches are left empty: 27`.
- `set`: **`Success` batches whose `Girls_Present__c` is empty only** → `Girls_Present__c` = rows
  (0 for the four blanks). `Failed` batches stay empty (the Apex leaves them empty too, so the
  field means one thing: the count behind a success). A batch that already has a value is never
  touched - that protects any aggregate typed before the run and makes a second run find
  `to set: 0`. Each write is `PATCH /services/data/v67.0/sobjects/Attendance_Batch__c/<id>`
  with `{"Girls_Present__c": n}` (HTTP 204), then a re-read of that batch's `Girls_Present__c`
  and a ledger line (`data/sf_girls_present/ledger.csv`: when, id, rows, value read back,
  outcome). The PATCH is **`Org.update`, the method the [module plan](2026-10-06-module-selection.md)
  adds to `tools/sf_backfill.py`** (built once, by whichever tool lands first; `FakeOrg.update` with
  it) - the two tools write different fields of the same object and share the writer, the
  `--vpn-off` rule, the `--limit 1` first write and the ledger-per-record shape. The first thing not
  as planned stops the run (`Refused`). The trigger is after-insert only, so an update runs no
  processing (`AttendanceBatchTrigger.trigger:1`).
- `check`: `Success` batches with `Creator__c` starting `Jotform` whose `Girls_Present__c` ≠
  their rows, and `Success` batches with no value → both `0` when healthy. A RUNBOOK signal from
  then on; aggregate batches (`Creator__c` other than `Jotform…`) are not compared (they have no
  rows by design).
- Gates: `--apply` is caught by `.claude/hooks/live_gate.sh` (its pattern matches `--apply`);
  the two live commands refuse without `--vpn-off`, like the back-fill (`sf_backfill.py:1117-1119`).
  `plan` and `check` are reads, but through the CLI login (`sf org auth show-access-token`, which the
  hook does not see: BACKLOG 53) while this workflow's sessions reach Salesforce through the read
  connector only - so, as the module plan says of its dry run, the first `plan --vpn-off` runs with
  Ryan present or in his terminal until BACKLOG 53 is decided.
  The folder is under `data/` (never committed), although it holds ids and counts only.
- Tests `test/sf_girls_present_test.py` (offline, a fake org: the plan's counts; `set` writes only
  where the value is empty; a typed aggregate is left alone; the dry run writes nothing; a PATCH
  that does not answer 204 stops with a ledger line; `--apply` without `--vpn-off` is refused;
  the help smoke), imported in `test/python_test.py` beside the back-fill tests (`:49`; the
  module plan adds its `fix_module_values_test` import to the same block - one merged block).

Equalities after the run (read-only): `SELECT COUNT(Id) FROM Attendance_Batch__c WHERE
Processing_Status__c = 'Success' AND Girls_Present__c = null` → 0;
`SELECT SUM(Girls_Present__c) FROM Attendance_Batch__c WHERE Processing_Status__c = 'Success'` →
7,041 = `SELECT COUNT(Id) FROM Attendance__c` (both re-read at the time: live submissions keep
arriving, and after B's deploy new batches carry their own count). Run C **right after B is
deployed and before D's reports go up**, otherwise the total-attendance tiles under-count
every batch from before the deploy.

## D. Reporting metadata (generated by `gen.py` - session -51's file; told to -51 first, built after `fix1`, which is live)

**1. Custom report type `Attendance_Totals`** (developer name and label "Attendance Totals" -
not `Attendance_Batches` / "Attendance Batches", which the org's vendor report type already
carries and which is left untouched; Build notes, dashboard generator) -
`force-app/main/default/reportTypes/Attendance_Totals.reportType-meta.xml`: `baseObject
Attendance_Batch__c`, category `other`, deployed, label "Attendance Totals", one section with
`Name`, `Account__c`, `Account_Name__c`, the club's parent via lookup (`Account__c` → Parent Name;
`Partner__c` instead only if the fallback formula is created), `Attendance_Date__c`, `CreatedDate`,
`Creator__c`, `Processing_Status__c`, `Status_Message__c`, `Module__c`, `Module_Week__c`,
`Module_Year__c`, `Girls_Present__c`, `Girls_Enrolled__c`. **`Contact_IDs__c` is left out on
purpose**: it is the names list, and no report built on this type can show it.
`Status_Message__c` stays in (the blank report filters on it) although a processor "Error: …"
message can quote the value Salesforce choked on, which can be a girl's name (class `:92`;
`sf_backfill.py:826-828` says the same) - acceptable inside Salesforce per Ryan's 2026-10-06
decision (`ae97969`), but the column goes on **no dashboard component** and no read-back the
tool or the conversation prints selects it (as `sf_backfill.py` never prints it). **This is a
`gen.py` change** (session -51's): today it writes `reports/Attendance` and `dashboards/Attendance`
only (`:272-278`); it gains a `reportTypes/` output folder, the report type's text, and a flag
that leaves `Girls_Enrolled__c` out of the type when Ryan strikes it from A.
Reports on it use `<reportType>Attendance_Totals__c</reportType>` and columns of the shape
`Attendance_Batch__c$Girls_Present__c` (the spelling the check-only validate and the first
retrieve settle - the pattern is `Accounts_Contacts_Attendance__c` and `Account$Parent` in
`gen.py:74,24`).

**2. Reports** (folder Attendance; every filter below locked unless said; unlocked "contains"
filters on `Partner__c` and `Account_Name__c` as the existing reports have on partner and club):

| Report (developer name) | Type | Filters | Grouping / measure | Window |
|---|---|---|---|---|
| Total Attendance by Partner by Month (`Total_Attendance_by_Partner_by_Month`) | batches | `Processing_Status__c = Success` | `Partner__c`, then `Attendance_Date__c` by month; **Sum `Girls_Present__c`**; column chart by month | `Attendance_Date__c` since 2026-09-01 |
| Jotform Attendance by Partner by Month (`Jotform_Attendance_by_Partner_by_Month`) | batches | as above + `Creator__c` starts with `Jotform` (covers `Jotform` and `Jotform back-fill …`) | same | same |
| Total Attendance Last Month (`Total_Attendance_Last_Month`) | batches | `Processing_Status__c = Success` | `Partner__c`; Sum `Girls_Present__c`; bar chart | `INTERVAL_LASTMONTH` |
| Clubs Not Submitting - Last 14 Days (`Clubs_Not_Submitting_Last_14_Days`) | Accounts (`AccountList`, as `CLUBS_WITHOUT`) | record type Club; `PARENT.NAME` not blank; cross filter **without `Attendance_Batch__c`** (join `Account__c`) where `Attendance_Date__c equals LAST_N_DAYS:14` - **no status or creator criterion**: any batch is a submission | `PARENT.NAME`; row count | the cross filter is the window |
| Clubs Not Submitting - Since 1 Sept (`Clubs_Not_Submitting_Since_1_Sept`) | Accounts | same, cross filter `Attendance_Date__c greaterOrEqual 2026-09-01` | same | same |
| Clubs With No Attendance Last Month (`Jotform_Clubs_No_Attendance_Last_Month`, exists) | Accounts | today: without `Attendance__c` rows, Creator `AttendanceBatchTrigger` | `PARENT.NAME` | `LAST_MONTH` |
| Blank Submissions (`Blank_Submissions`) | batches | `Status_Message__c = No participants submitted` **or** (`Processing_Status__c = Success` and `Girls_Present__c = 0`), filter logic `1 OR (2 AND 3)` | `Partner__c`; columns `Account_Name__c`, `Attendance_Date__c`, `CreatedDate`, `Processing_Status__c`; row count | `Attendance_Date__c` since 2026-09-01 |

Notes on the table:

- The windows test the **session date** (`Attendance_Date__c`), as the existing tile does, not
  the day the submission arrived: "no session dated in the last 14 days" is the alarm Ryan wants
  (a club that stopped meeting, or is three weeks late, both deserve a look), and the existing
  report's cross-filter shape is proven metadata (`gen.py:113-120`). If Ryan means the act of
  submitting, the criterion becomes the batch's created date - one word in `gen.py`, and a
  spelling for a standard field in a cross filter the validate has to confirm.
- `LAST_N_DAYS:14` means the 14 days before today plus today. Its spelling inside a cross-filter
  `<value>` was **not verified** (the existing one carries `LAST_MONTH`, `gen.py:115`); the
  check-only validate settles it, the alternative being `LAST_N_DAYS:14` on a `timeFrameFilter`
  of a batch-based report. **Settled 2026-10-07**: `LAST_N_DAYS:14` is accepted in a cross
  filter as it stands. The since-1-Sept cross filter's date is not: a cross filter's date value
  must be the report's locale format, `9/1/2026` (ISO `2026-09-01`, and `greaterThan 2026-08-31`,
  were refused with "There are errors with your subfilters"; Build notes, dashboard generator).
- A duplicate (`Failed` "Duplicate: …") counts as submitted, per Ryan: no status criterion.
- **The existing last-month tile** counts attendance rows (Jotform only), so a club whose only
  September batch was a blank or a duplicate is "without attendance" there but "submitting" on
  the two new tiles (today 196 against 194). **Ryan, 2026-10-06: it stays row-based** ("no
  Jotform attendance rows last month"); the two new tiles are batch-based ("no submission of any
  kind"), and the How-to box names the difference in one sentence ("Clubs with no attendance last
  month counts Jotform rows; clubs not submitting counts submissions of any kind, blanks and
  duplicates included"). The proposed switch (cross filter `without Attendance_Batch__c` of any
  status) is recorded here as rejected, so the complement with the "clubs that sent attendance"
  metric (unique Account over `Attendance__c` rows) holds.
- "Blank" before B lands would be an Accounts report `with Attendance_Batch__c (Success, in the
  window)` and `without Attendance__c (in the window)`; since B is deployed first in the order of
  work, the batch report above is built directly and the Accounts variant is the fallback only.
- The by-module report (`Jotform_Sessions_by_Module_Last_Month`) counts rows, so aggregate
  batches (no module, no rows) never appear in it; no blank bucket.
- `Girls_Enrolled__c` is on no report until BACKLOG 58 fills it.

**3. Dashboard** ("Jotform Attendance (test)", `01ZRP00000BE2TR2A1`; 13 components today, the
Lightning limit is 20):

- **Labels**: "(Jotform only)" appended to the headers of the two "Girls who attended" metrics
  (`gen.py:188-191`), "Girls attending per week" (`:197`), "Girls attending per month" (`:199`)
  and "Girls who attended last month, by partner" (`:207`). The How-to box (`:233-244`) gains:
  "Total attendance = girls present summed over sessions: the Jotform rows plus the counts
  partners without Jotform report (source 'Partner report'). Girls who attended counts each girl
  once and is Jotform only: a reported count has no names." and "Clubs not submitting = no
  submission of any kind dated in the window; a club that reports late shows here until its
  session dates arrive. Blank = a submission with no girl ticked."
- **New tiles** (6 → 19 components): Metric "Total attendance / last month" (Sum
  `Girls_Present__c`, report Total Attendance Last Month); Column "Total attendance per month,
  all sources" (Total Attendance by Partner by Month, grouped by month); Metric "Clubs not
  submitting / last 14 days"; Metric "Clubs not submitting / since 1 Sept"; Metric "Blank
  submissions / since 1 Sept" (row count); FlexTable "Clubs not submitting in the last 14 days,
  by partner" - **one row per partner** (≤ 49; a Lightning table stops at 200 rows, which is why
  `fix1` made the last-month table per partner, `gen.py:215-216`; the club list is one click away
  in the report). The last-month metric and table stay.
- **Partner filter mapping per component** (`dashboardFilterColumns`, `gen.py:164`): batch
  reports → the via-lookup parent column (`Attendance_Batch__c$Account__c.Parent` or as the deployed
  type's describe spells it; `Attendance_Batch__c$Partner__c` only with the fallback formula);
  Accounts reports → `PARENT.NAME` (as `:214`); the
  existing Contacts reports → `Account$Parent`. The 49 values are the same partner names on
  every column, so one filter drives all 19 components. No new filter value is needed (`Partner
  report` is a creator, not a partner); the filter stays at 49 of 50 (BACKLOG 60.6). **A formula
  field as a dashboard filter column is not verified**: `gen.py` filters on `Account$Parent` and
  `PARENT.NAME` only (`:24, :164, :214`), both standard. The check-only validate settles it;
  the fallback is the report type's own lookup fields (`Account__c`'s parent through "fields
  related via lookup", the second hop A leaves unverified), and the last resort is grouping by
  `Partner__c` with no Partner filter on the batch tiles (said so in their headers). **Settled
  2026-10-07**: the via-lookup column `Attendance_Batch__c$Account__c.Parent` is the batch
  components' filter column and the one Partner filter drives every new tile (equal to SOQL under
  WESAD, Fundación Kaleidos and Ng'aa Maskani); no formula field was needed (Result).
- **`fix1` pieces kept**: `INTERVAL_THISMONTH` (`:102`), the per-partner no-attendance table
  (`:217-225`), the How-to box (`:233-249`).

**4. Read-back = SOQL for every number** (as on 2026-10-02 and 10-06, read-only; the numbers
below are today's, re-read on the day):

| Tile / report | SOQL | 2026-10-06 |
|---|---|---|
| Total attendance, last month (all sources) | `SELECT SUM(Girls_Present__c) FROM Attendance_Batch__c WHERE Processing_Status__c = 'Success' AND Attendance_Date__c = LAST_MONTH` | 6,177 after C (no aggregates yet) |
| Jotform only, last month | same + `AND Creator__c LIKE 'Jotform%'`; must equal `SELECT COUNT(Id) FROM Attendance__c WHERE Attendance_Date__c = LAST_MONTH` | 6,177 = 6,177 |
| Total by partner by month | `SELECT Account__r.Parent.Name, CALENDAR_MONTH(Attendance_Date__c), SUM(Girls_Present__c) … GROUP BY …` | one row per partner-month |
| Clubs not submitting, last 14 days | `SELECT COUNT(Id) FROM Account WHERE RecordType.DeveloperName = 'Club' AND ParentId != null AND Id NOT IN (SELECT Account__c FROM Attendance_Batch__c WHERE Attendance_Date__c = LAST_N_DAYS:14)` | 202 |
| since 1 Sept | same with `Attendance_Date__c >= 2026-09-01` | 182 |
| last month (batches of any status) | same with `= LAST_MONTH` | 194 (row-based, Jotform only: 196) |
| Blank submissions since 1 Sept | `SELECT COUNT(Id) FROM Attendance_Batch__c WHERE Attendance_Date__c >= 2026-09-01 AND (Status_Message__c = 'No participants submitted' OR (Processing_Status__c = 'Success' AND Girls_Present__c = 0))` | 3 after C |
| Partner filter on WESAD | each tile with `AND Account__r.ParentId = '001RP000002nR7mYAE'` (or `Parent.Name`) | today: 30 clubs (since the re-parent of 10:53 UTC) |

Deploys: check-only by Claude (`sf project deploy start --dry-run -o glow -d force-app` from the
build folder, RUNBOOK `:1925`), **Ryan deploys**, then retrieve and compare with the build; the
copies go beside `before/`, `after/`, `fix1/`, `after2/` as `totals1/` (RUNBOOK `:1912-1916`).

## E. Hygiene: the two stray WESAD accounts (done), and BACKLOG 27

- **Done before this plan, nothing to write**: `Change Makers` (001RP00000yQZcJYAW) and
  `Seeds of Greatness` (001RP00000yQbB3YAK), created partner-less by the processor on 2026-10-03
  (20 and 19 attendance rows; the roster lists both as WESAD clubs added 2026-10-01), were
  re-parented to 001RP000002nR7mYAE ("World Economy Skills and Agro Development (WESAD)") on
  Ryan's go at 2026-10-06 10:53:18 and 10:53:34 UTC through the write connector, one record per
  call, read back - main `00ee471`, recorded in the [dashboard plan](2026-10-02-attendance-dashboard.md)
  `:214-224` (before/after copies in `data/sf_club_parents_2026-10-06/`; rollback there: `ParentId`
  blank on both) and in BACKLOG 27's last sentence. Re-read for this plan: both carry WESAD's
  id; Club accounts without a parent → **2** (the RUNBOOK's signal, `:1683-1684`); WESAD's clubs
  → **30**; clubs with a partner → 364. Re-parenting rather than re-creating was right: their
  names already equal the picker's text, and the RUNBOOK forbids deleting an account with
  Contacts or attendance (`:1698-1699`). This plan's BACKLOG 27 edit **merges onto `00ee471`'s
  sentence** ("check after every new club … exactly the two pilots"), which it keeps.
- **Handed over by the [clubs-off plan](2026-10-06-clubs-off-jotform.md)**: the twelfth U.S Club
  account (FemXFem's) has no Roster rows and no batch; it pads the "did not submit" lists like
  the other eleven. Nothing is written here; whether it is kept, re-typed or deactivated in
  Salesforce is Ryan's (Open decisions).
- **BACKLOG 27 scheduled**: until an account is created automatically before a club's first
  attendance, a round of the 2026-09-30 procedure (`tools/sf_club_accounts.py`, [plan](2026-09-30-salesforce-clubs.md))
  for the clubs in the Monday e-mail's SF Pending list, each Monday, by Ryan with Claude; the
  BACKLOG line gets that cadence and this plan's date. Not built here.
- **BACKLOG 27 built on `main` meanwhile** (session -51, 2026-10-06, merged here 2026-10-07:
  [plan](2026-10-06-sf-new-club-accounts.md); `tools/sf_new_clubs.py`, `SF_SYNC` off/plan/apply):
  the automatic sync creates a new club's account right before the region's form puts it on the
  Club picker - **only for the clubs it puts on a form** (the plan's `CREATE roster` lines). A new
  club of a partner marked `jotform=no` ([clubs-off plan](2026-10-06-clubs-off-jotform.md)) never
  reaches a form, so it gets no account from the sync: it stays on SF Pending and in the Monday
  e-mail for a hand create, and that account must exist before the club's first aggregate batch
  (F, the contract) or the processor creates a partner-less one from the typed name. The second
  trigger that would close this - "an active Roster club on no form with no account" - is
  BACKLOG 74, Ryan's decision. The weekly round above stays the cadence while `SF_SYNC` is not
  `apply`, and for those clubs after.

## F. Intake for the aggregates - OPEN DECISION (Ryan is gathering information)

The plan proceeds through A-E without it; the Salesforce side accepts any of the three. **The
contract every intake must meet**, whatever the method:

| Field | Value |
|---|---|
| `Account_Name__c` | the club's Salesforce Account name **exactly** as the Club picker sends it (CLAUDE.md rule 5): the plain club name, or `<club> - <partner>` for a club whose name another partner's club shares; the strings are the sync's `--summary-json` `sf_names`. A mistyped name creates a partner-less account (processor `:102-109`, proven twice on 2026-10-03). Whether any of the 38 clubs shares a name is **not verified** (read `sf_names` for the three partners first). |
| `Attendance_Date__c` | the **last day of the month** reported (one batch per club per month; a partner that can give per-session counts dates them the session day instead) |
| `Girls_Present__c` | the count, > 0 (0 or empty with no names is `Failed` "No participants submitted", B) |
| `Contact_IDs__c` | **empty** - no names, ever |
| `Creator__c` | `Partner report` (the label the reports and the How-to box use; any other non-`Jotform…` value also stays out of the Jotform-only view) |
| `Module__c`, `Module_Week__c`, `Module_Year__c` | optional; empty keeps them out of nothing (the module report counts rows) |
| `enable_fuzzy_matching__c` | false |

**The account comes first, whatever the intake.** The club's Club account must exist before its
first aggregate batch, or the processor creates a partner-less account from the typed name (the
2026-10-03 case). The 38 clubs have theirs (2026-09-30). A **new** club of one of the three
partners gets none from the automatic sync: session -51's new-club account step
([plan](2026-10-06-sf-new-club-accounts.md), on `main`, merged 2026-10-07) creates accounts only
for the clubs the sync puts on a form, and a `jotform=no` partner's club never reaches one - it
stays on SF Pending and in the Monday e-mail for a hand create (RUNBOOK "Club accounts in
Salesforce"), before the month's aggregate is sent. The second trigger that would close this
("an active Roster club on no form with no account") is BACKLOG 74, Ryan's decision.

What each option needs:

1. **A small Jotform "aggregate attendance" form** with its own Salesforce V2 mapping: a Club
   dropdown holding the 38 clubs' Salesforce names (kept in step by hand or by a small tool - the
   sync does not manage this form), a month picker, a required number "Girls present" (minimum 1),
   a hidden textbox with the constant `Partner report` mapped to `Creator__c`, a calculated
   last-day-of-month date mapped to `Attendance_Date__c`. The mapping is builder-only (proven
   2026-09-30: the API cannot write integrations) and set by Ryan; `tools/integration_status.py`
   learns the sixth form; `tools/backup_forms.py --form` backs it up. Partners type their own
   numbers; another form and mapping to govern.
2. **The coordinator in Salesforce**: a screen flow "Report a club's monthly attendance" (pick the
   Club account - record type Club, parent among the three - the month, the count; the flow
   writes `Account_Name__c` = the account's `Name`, the last-day date, `Creator__c`) so the name is
   never typed; or a plain "New Attendance Batch" with the fields on the layout, which leaves the
   typo risk. 38 entries a month, about 20 minutes. A flow is metadata Ryan deploys.
3. **A sheet import**: the three partners fill a simple tab (club, month, girls present) that a
   dry-run repo tool (`tools/sf_aggregate_send.py`, built like `sf_backfill.py`: snapshot, plan
   with the club names resolved against `sf_names`, `send` one batch per request on `--apply
   --vpn-off`, read back, ledger) turns into batches once a month. Exact names for free, the repo's
   discipline, no new Salesforce metadata; a monthly hand run and a new tab to design.

Not chosen (for the record): summing the Monthly Report's weekly counts (`DHIS2__c`). Its grain
is partner-month with week slots that look like session days, not clubs; a partner that ticks
"submitted electronically" and still types counts (one did on 2026-10-05) would be counted
twice. The Monthly Report is never added to attendance totals.

## Files that change

- `docs/intent/2026-10-06-attendance-totals.md` - new (this plan's intent).
- `docs/plans/2026-10-06-attendance-totals.md` - this plan.
- `tools/sf_girls_present.py` - new (C): `plan`, `set` (dry run; `--apply --vpn-off` writes), `check`.
- `test/sf_girls_present_test.py` - new; `test/python_test.py` - one import line in the block at
  `:46-49` (**shared with the module plan**, which adds `fix_module_values_test` there: one merged
  block).
- `tools/sf_backfill.py` - docstring `:5-9`, the hold's detail text `:613-614`, the `plan` listing's
  text `:762-763`, `outcome_of` `:825-836` (`no_participants`), `verify` `:855-856, :873-874`
  (`Girls_Present__c` equals the rows). (The module plan adds `Org.update` to the same file;
  different lines.)
- `test/sf_backfill_test.py` - docstring `:5-8`, `FakeOrg.insert` `:117-158` (the new processor rule;
  the module plan adds `FakeOrg.update` beside it), `test_what_salesforce_already_has_for_a_club_day`
  `:419-420`, the comment at `:565`, one new test.
- `docs/RUNBOOK.md` - "Club accounts in Salesforce" (BACKLOG 27's weekly cadence; the re-parent
  is already recorded by `00ee471` in the dashboard plan and BACKLOG 27); "Back-fill of attendance
  into Salesforce" (`:1788-1789`, `:1816`: a blank is Failed and blocks nothing; `check`); the
  September history at `:811`; "Attendance dashboard in Salesforce" (what the new tiles count,
  Jotform only vs total, the three windows, `totals1/`, rollback); a new "Attendance totals and
  partner-reported counts" section (the field, the contract in F, the one-off tool, the signals).
- `docs/BACKLOG.md` - 27 (cadence, merged onto `00ee471`'s sentence), 55 (profiles: answered for
  these fields), 58 (the fields exist; what remains is the enrolled count and the rate), 60 (the
  How-to box and labels), **65** (the residual's row: the backstop is this plan's B - closed when B
  is deployed, the `q18_empty` watch kept), a new item for the intake decision (F) and one for the
  legacy blanks if Ryan leaves them - at the next free numbers after the sibling plans' 66-71
  (72, 73 as of `main` 9d58ce4; re-checked at commit time).
- `docs/DECISIONS.md` - the rows under "Decisions to record".
- `.claude/skills/live-systems/SKILL.md` - the "Salesforce (production) is written in two ways
  only" paragraph (`:21-30` on main): `tools/sf_girls_present.py set --apply` is the **second
  `--apply` tool that writes Salesforce** beside `sf_backfill.py send --apply` (the module plan's
  `tools/fix_module_values.py --apply` is the other new one: **one merged paragraph for both
  plans**, with the orchestrator); a batch `PATCH` runs no processing (the trigger is after-insert
  only); and a **rolled-back anonymous Apex run** (`sf apex run`, B's proof) is a write path
  the hook does not see - Ryan's go or Ryan's hands, script pasted first, savepoint and
  `Database.rollback` in it.
- **Not in the repo** (under `data/`, never committed): `data/sf_totals_2026-10/{before,after}/`
  (fields, profile, class, tests), `data/sf_dashboard_2026-10-02/gen.py` (session -51's; a
  `reportTypes/` output folder and the report type's text with the `Girls_Enrolled__c` flag, the
  reports, tiles, labels and How-to lines), `data/sf_dashboard_2026-10-02/totals1/`
  (what is deployed), `data/sf_girls_present/` (plan, ledger).
- **Untouched**: every Jotform form, `sync_attendance_form.py`, `glow/`, `appsscript/`, the sheet,
  the Salesforce V2 mapping, `tools/form_status.py` (session -54's window).

## Order of work (the repo stays green after each step; live steps marked)

1. Merge main (`00ee471`, the wf9 merge `3ea1cab`) into this branch, then commit the intent and
   this plan (its line numbers are main's); tell session -51 what D adds to `gen.py` (a
   `reportTypes/` folder, the type, the `Girls_Enrolled__c` flag, the reports and tiles) and
   session -54 that nothing here touches a form. E is already done on main: nothing to write.
2. **A + B - schema and Apex**, in `data/sf_totals_2026-10/`: retrieve the live class, trigger,
   test class and object → `before/`; write the three fields, the profile permissions, the class
   change and the five tests → `after/`; independent adversarial review of the diff (as on
   2026-10-02); `sf project deploy validate … -t AttendanceBatchTriggerTest -t TestContactTriggerHandler`
   → paste the result; **Ryan deploys** (`sf project deploy quick -i <id>`) at a quiet moment;
   retrieve and compare; the rolled-back anonymous Apex proof (**Ryan's go, or run by Ryan**:
   it writes inside a transaction it rolls back; the script is pasted first).
3. **Repo follow-through for B**: `sf_backfill.py` and its tests as listed; `make check` green;
   RUNBOOK and DECISIONS lines.
4. **C - the one-off back-fill**: build `tools/sf_girls_present.py` and its tests; `plan --vpn-off`
   → the counts above; `set` (dry run); **Ryan's go** → `set --apply --vpn-off --limit 1`, read that
   batch in Salesforce; `set --apply --vpn-off` for the rest; the two equalities; `check` → 0 and 0.
5. **D - reporting**, with session -51 in `gen.py` after `fix1`: the report type, the six new
   reports (and the last-month switch if Ryan says so), the labels, the How-to lines, the six
   tiles; `python3 gen.py`; copy the changed files to `totals1/`; check-only validate (it also
   settles the formula-as-filter-column question; the fallback in D.3 if it fails); **Ryan
   deploys**; retrieve and compare; the read-back table, every number against SOQL, the Partner
   filter on WESAD and on one accented partner (as on 10-02).
6. Docs: RUNBOOK sections, BACKLOG 27/55/58/60 and the new items, DECISIONS; `make check`; the
   work log.
7. **F**: Ryan's intake decision → its own plan; the first aggregate batches then prove the
   `Creator__c` split on the live tiles (total ≠ Jotform only for the first time).

Steps 2 and 4 are ordered on purpose: the field must exist before the tool fills it, and the
fill must be done before D's totals are read, or every batch from before the deploy counts zero.

## Risks

- **The vendor's Apex class, in production, again** (Studio Infinite Lives; no sandbox login in
  use). Mitigation as on 2026-10-02: retrieve first, check-only validate with the org's tests,
  an independent review of the diff, Ryan's quick deploy at a quiet moment, read back, a
  rolled-back proof; rollback = redeploy `before/` (the fields can stay). A deploy swaps the class
  between transactions; a submission at that second completes on either version.
- **A live blank changes outcome**: from a `Success` that blocked the day to a `Failed` that
  blocks nothing. Intended; the Jotform side is unaffected (the insert succeeds either way). The
  daily question-18-vs-ticks check (BACKLOG 35's rollout alarm) keeps running to ~10-09.
- **Double counting** if anyone also sums the Monthly Report's weekly counts, or enters an
  aggregate for a club that also submits on Jotform. The How-to box names the one source per
  partner; the three partners' clubs leave the Africa form (decision 5); the processor's
  club-and-day lock stops a same-day collision (`Duplicate`), and the month-end date convention
  keeps aggregates off real session days.
- **Mixed definitions on one page**: attendances (sum) next to distinct girls (unique). Every
  distinct-girl tile says "(Jotform only)" and the How-to box defines both; the by-month column
  for totals sits beside the by-month girls column with its own header.
- **The 50-value Partner filter**: 49 of 50 used, no new value needed here; a new partner still
  needs a hand edit (BACKLOG 60.6). The filter column differs per component on purpose; a tile
  given the wrong column shows unfiltered numbers - the WESAD read-back catches it.
- **Late submissions**: the 14-day tile names clubs that report late (12 of the first 28 live
  sessions arrived more than a day late, RUNBOOK `:1873-1875`); the box says "not yet received",
  and the window tests session dates, so a late batch clears the club as soon as it lands.
- **Padding of the "did not submit" lists**: the 38 clubs of the three partners and the 12 U.S.
  clubs (50 of today's 182) cannot submit on Jotform and have no marker in Salesforce (Ryan's
  choice: exclusion at the source). The 38 count as submitting once their monthly aggregate
  lands, and are flagged on the 14-day tile between a month-end and the next aggregate; the 12
  stay listed until their accounts carry a status. Stated in the How-to box; the exclusion
  options are an open decision below.
- **Access and private records**: the dashboard runs as Ryan; a report opened from it runs as
  the viewer, and club accounts are private (RUNBOOK `:1900-1903`). New fields add nothing to
  that: the readers are the 7 System Administrators. If the folders are ever shared wider,
  `Girls_Present__c` needs read permission on those profiles too (BACKLOG 55 / 60.2).
- **Session -51's generator**: all report and dashboard metadata goes through `gen.py` after
  `fix1`, not beside it; `after2/` stays the live reference until `totals1/` is deployed. Session
  -54's form rollout is untouched: this plan writes to no form and does not change
  `tools/form_status.py`.
- **Unverified metadata spellings** (settled by the check-only validate, which changes nothing):
  the batch report column prefix (`Attendance_Batch__c$…`), `LAST_N_DAYS:14` and `greaterOrEqual
  2026-09-01` inside a cross filter, **`Attendance_Batch__c$Partner__c` (a formula field) as a
  component's `dashboardFilterColumns` entry** (fallback in D.3: the report type's lookup fields
  for the club's parent, or batch tiles grouped by `Partner__c` without the Partner filter), a
  `Number` field update through `PATCH` on a batch with a validation rule or flow nobody has read
  (the `--limit 1` run proves it before the rest), and whether a report type can carry the
  parent's parent via lookup (needed only if the formula column fails as a filter). **Settled
  2026-10-07** (Result): the prefix `Attendance_Batch__c$…` holds; the partner via lookup works
  (`Attendance_Batch__c$Account__c.Parent`, report and filter column), so the formula column and
  the parent's parent are moot; `LAST_N_DAYS:14` is accepted in a cross filter; the since-1-Sept
  date must be the locale's `9/1/2026`, not ISO; 0 validation rules on either object (Tooling
  API) and the `--limit 1` PATCH went through.
- **A mistyped aggregate name** creates a partner-less account, as today; the intake contract
  (F) and the parent-less signal (RUNBOOK `:1683`) are the guards until the intake is designed.
- **Privacy**: no names enter the repo, the tool's files (ids and counts) or this plan; the
  report type leaves the names list out, and its `Status_Message__c` (which an "Error: …" can
  fill with a name) is on no dashboard component and in no read-back that is printed; the Apex
  message is a fixed string; test names are the vendor's fictional ones and are not quoted here.

## Build notes (C, built 2026-10-06 offline on the workflow's branch; nothing run against Salesforce)
- `set --apply` re-reads each batch (`Id, Processing_Status__c, Girls_Present__c`) **before** the
  PATCH as well as after: a value typed between `plan` and `set` is left alone and counted
  (`skipped, already has a value`), a status that changed since the plan stops the run. That is the
  "never touched" rule enforced at write time, not only in the plan.
- The ledger has an `open` row and a closing row per batch (`written` / `failed_<status>` /
  `check`), the shape the module tool uses, with the plan's columns (when, id, rows, value read
  back, outcome).
- `check` exits 1 when either count is not 0, so a script can read it; aggregate batches
  (`Creator__c` not starting `Jotform`) are not compared, as planned.
- `plan` and `check` before the field is deployed stop with "is `Girls_Present__c` deployed?" (the
  read comes back HTTP 400); the field does not exist in the org yet, and the RUNBOOK section says
  "after the field is deployed". The `plan --vpn-off`, `set` and `check` runs were **not** made:
  they need the CLI login (BACKLOG 53; with Ryan). The fake-org tests are the proof of this step.
- Step 3 (the `sf_backfill.py` hold wording, docstring, `outcome_of`, `verify`, the fake org's
  `insert`) is untouched: it is held until the class is deployed (Order across the four plans, B.5).
- **Review fixes (2026-10-06).** The rows query deviates from the SOQL above: one `GROUP BY` per
  200 batch ids (`WHERE Attendance_Batch__c IN (...)`, the ids `plan` and `check` already hold)
  instead of one over every batch. Salesforce gives an aggregate query a single page and no next
  page (documented at 2,000 groups; not tried against this org), and at the live rate the batches
  pass that within a year - `check`, a standing signal, would then stop with an HTTP 400 that the
  "is the field deployed?" hint mis-explains. The result is the same (a batch with no rows is
  absent either way). `check` also covers a re-read Salesforce did not answer after a 204: the
  closing row is written (outcome `check`, no value read back) and the stop names the batch. `data/`
  is created (owner-only) when the folder lies under it and a fresh checkout has none yet, since
  `sf_backfill.within` needs it to exist. `quoted` is imported at the top with the rest of
  `sf_backfill`.

## Build notes (Apex and fields, 2026-10-07)

A + B, prepared offline 2026-10-06 and corrected after the review on 2026-10-07; no `sf` command
was run, nothing was written to Salesforce, Jotform, the sheet or GitHub. The full diff and its
reading are in `DIFF.md` beside the files; the commands in `COMMANDS.md`.

- **Built in the session's scratchpad, not in `data/sf_totals_2026-10/`**: the hook
  `.claude/hooks/protected_paths.sh` blocks the Write and Edit tools under `data/`, and nothing
  was routed around it. Placing the folder is `COMMANDS.md` step 0 (one `cp -R`, then `diff -r`),
  with Ryan's go.
- Against the 10-02 copy (`data/sf_processor_2026-10-02/after/`; `COMMANDS.md` step 1 confirms it
  is still what is live): four hunks, 20 lines added, none removed - the `NO_PARTICIPANTS_MESSAGE`
  constant; the blank / aggregate branch at the top of `processParticipants` (after
  `resolveClubAccount` and `isDuplicateBatch`, so `Account__c` is set on a blank and a `Failed`
  blank never blocks a day); `Girls_Present__c = matches.size()` (the rows step 3 queues, one per
  distinct name, so count and rows cannot disagree); and `markBatchFailed`. The trigger and the
  three `-meta.xml` files are byte-identical to 10-02.
- **`markBatchFailed` clears `Girls_Present__c` to null on every Failed path** (Duplicate,
  "Attendance already exists", "No participants submitted", the `catch` in `processBatch`) - one
  line B did not list: A's field description "Empty on Failed batches" is the spec and C relies
  on it, while B set the field on success only, which left a typed count on a batch that ends
  Failed. Two tests pin it (a typed 0 with no names; a typed 7 on a Duplicate).
- **A negative `Girls_Present__c` with no names counts as 0** (Failed, the literal): the plan's
  "> 0 is an aggregate" read literally.
- **`Girls_Enrolled__c.field-meta.xml` is in the package** (A's recommended default; the profile
  already named it, so without the file the validate would have refused the profile entry). The
  first draft left it out.
- `profiles/Admin.profile-meta.xml` carries only the two `fieldPermissions` (read + edit on both
  fields), so the deploy merges them into the live System Administrator profile and touches
  nothing else of it (the 09-30 shape). No `Partner__c` entry: the formula is a fallback
  (`fallback/`, not under `force-app/`).
- **No `Attendance_Batch__c.object-meta.xml`**: a lone field under `fields/` deploys as a change
  to the existing object, and an object file would carry object-level properties nobody asked to
  change. Add an empty one only if the validate asks for the parent.
- **`sourceApiVersion` 65.0** in `sfdx-project.json`: the version the class, test and trigger meta
  files carry, unchanged from 10-02 (the first draft copied the dashboard project's 62.0).
- **Two fictional e-mail literals removed from the vendor's test setup** (`setupTestData`): the
  repo's secret scan refuses any e-mail address in a file this session writes, and nothing reads
  `Email`. Not in the plan.
- Tests: `testEmptyParticipantList` flipped (`Failed`, the literal, `Account__c` set, count null,
  0 rows); five new methods (an aggregate succeeds with no rows and keeps its count; a typed 0
  with no names is "No participants" and the 0 is cleared; present = rows created, a repeated
  name once; a blank does not block the day; an aggregate blocks a Jotform batch the same day,
  whose typed 7 is cleared). 23 `@isTest` methods, fictional names from the class's existing
  vocabulary. `proof_anonymous_apex.apex`: one transaction - a pre-check that the made-up club
  exists nowhere, a savepoint, three inserts, the outcomes as `System.debug`, `Database.rollback`
  in a `finally`, then an exception so the run ends Failed on purpose and nothing can commit.

## Build notes (dashboard generator, 2026-10-07)

D, built 2026-10-06 and revised 2026-10-07 after two adversarial reviews. `gen.py` is session
-51's file and -51 cleared the edit; `after2/` stays the live reference until `totals1/` is
deployed. No `sf` command was run.

- **Built in the scratchpad** (the `data/` hook, as above), with `NOTES.md` beside it; installed
  into `data/sf_dashboard_2026-10-02/` with Ryan's go: first `cp gen.py gen.py.after2` there
  (the previous generator, what built `after2/`, kept beside the new one), then `gen.py` and
  `NOTES.md` in, then `python3 gen.py` → `13 reports, 1 report type, 1 dashboard, 19 components,
  49 partner filter values`. The seven existing reports build byte-identical to `after2/`
  (`diff -r` after each build lists only the six new files).
- **The report type is `Attendance_Totals`, label "Attendance Totals"**, not `Attendance_Batches`
  / "Attendance Batches" as D.1 first said: the org already holds a vendor report type of that
  developer name and label (retrieved 2026-10-02: category accounts, with `Contact_IDs__c` and
  six other columns the plan's type leaves out). Deploying under that name would overwrite the
  vendor's and could break the pilot dashboard's batches report (whose type was not retrieved);
  a second type with the same label would be two "Attendance Batches" in the report builder's
  type picker. The one section inside the type keeps "Attendance Batches" as its heading. **The
  vendor's `Attendance_Batches` type is left untouched.** Re-check in the sitting: `sf org list
  metadata -m ReportType -o glow` (the new name must be free). D.1, Decisions row 4 and
  `docs/DECISIONS.md` say `Attendance_Totals` since 2026-10-07.
- **`running_user()`** reads the dashboard's running user from the deployed copies beside
  `gen.py` (`after/`, `fix1/`, `after2/`, later `totals1/`: the `<runningUser>` they all carry);
  copies that disagree stop the build, and `sf org display` (the CLI login) is read only while
  no copy exists - a missing CLI or a failed login is a `sys.exit` that says what to restore. It
  runs from `main()` after the arguments are parsed, so `--help` touches neither. A redeploy
  must never switch the running user to whoever is logged in.
- **`described(text)`** stops the build on a `<description>` over 255 characters (Salesforce's
  limit for a report, a type and a dashboard; the first build's Blank Submissions was 263 and
  would have failed the whole package - now 246).
- **How-to box**: the plan's two sentences are split across two bullets so "each girl counted
  once" is not said twice; the first bullet and the dashboard's description name both sources;
  one more bullet states the padding of the "did not submit" lists, which the Risks said the box
  states and the first build left out: "Clubs whose partner reports a monthly count instead of
  using Jotform show as not submitting until that count arrives; the U.S. clubs, which do not
  report attendance here, stay on the lists." Eleven bullets; the box takes 9 rows.
- **Weekly header**: "Girls attending per week (Jotform only, since 1 Sept)" rather than two
  parentheses in a row.
- **Layout**: 19 components (limit 20) - the nine metrics in three rows of three (4 columns
  each) instead of a row of four; the weekly girls line full width; the two per-partner tables
  (one row per partner: `PARENT.NAME` + `RowCount`, never per club) side by side; no component
  removed. Every batch component filters on `Attendance_Batch__c$Account__c.Parent`.
- **Unverified until the first check-only validate and the type's describe** (`NOTES.md` has the
  full table): the two-hop lookup `Account__c.Parent` as a type field and
  `Attendance_Batch__c$Account__c.Parent` as a report column and filter column (the one-hop shape
  is this org's; the fallback is D.3's `Partner__c` formula); `LAST_N_DAYS:14` and
  `greaterOrEqual 2026-09-01` as cross-filter values (the deployed one carries `LAST_MONTH`
  only); the filter logic `(1 OR (2 AND 3)) AND 4 AND 5`; a column chart grouped by the report's
  second grouping (swap `BY_PARTNER_BY_MONTH` if refused); `Girls_Present__c` and
  `Girls_Enrolled__c` existing (A deploys them first; the validate fails until then);
  `Attendance_Totals` free as a developer name. Proven, out of the table: the column prefix
  `Attendance_Batch__c$<field>` (the pilot dashboard groups on it). **Settled 2026-10-07** by the
  check-only runs and the deploy (8 of 8): the partner via lookup (Analytics token
  `Attendance_Batch__c.Account__c.Parent.Name`; metadata `Account__c.Parent` /
  `Attendance_Batch__c$Account__c.Parent`, report column and filter column alike - the `Partner__c`
  formula was not needed); `LAST_N_DAYS:14` in a cross filter; the since-1-Sept date in the
  locale's format (first fix below); the column chart on the second grouping; the filter logic;
  the two fields and the free developer name.

**Fixes from the first check-only run (2026-10-07).** The first dry run of `totals1/` failed 4 of
its 8 components, for two causes; after both fixes the dry run passed 8 of 8 with 0 errors and the
seven existing reports still built byte-identical to `after2/`.

- **The cross filter's date is the report's locale format.** The since-1-Sept cross filter
  (`Clubs_Not_Submitting_Since_1_Sept`) was refused with "There are errors with your subfilters"
  for ISO `2026-09-01`, and for `greaterThan 2026-08-31`; `9/1/2026` and `LAST_N_DAYS:400` were
  accepted. `gen.py` gained the constant `SINCE_CROSS = "9/1/2026"`. The dashboard (the fourth
  failure) failed only because of this one.
- **A grouping is never also a column.** The two by-month reports
  (`Total_Attendance_by_Partner_by_Month`, `Jotform_Attendance_by_Partner_by_Month`) listed the
  session date both as the month grouping and as a column ("You can't include groupings in the
  selected columns list"). `gen.py` gained `MONTH_COLUMNS` = every column but the date.

## Decisions to record (proposed rows for `docs/DECISIONS.md`, dated 2026-10-06)

1. **A batch with no names and no count is never a success.** The attendance processor marks it
   `Failed` "No participants submitted" (no rows, blocks nothing); a batch with no names and
   `Girls_Present__c` > 0 is an **aggregate** and succeeds with no rows. Why: three blank
   submissions since 1 September were stored as successes that blocked their club's day, and
   one submission with ticks and an empty names list still arrived on 2026-10-03 after the
   required-roster guard. Consequences: no new Jotform rule for blanks (Ryan, 2026-10-06); the
   back-fill tool's fake org and hold wording follow; the three legacy blanks are left as they are
   (or deleted on Ryan's go).
2. **`Girls_Present__c` on `Attendance_Batch__c` is the one attendance count.** Apex sets it on
   success to the rows created; a partner-reported total is typed into it, with `Creator__c`
   `Partner report`, per club per month, dated the last day of the month. **Total attendance =
   SUM over `Success` batches; "Jotform only" = the same with `Creator__c` starting `Jotform`.
   Distinct-girl figures are Jotform only and say so.** (2026-10-15, ticket #35: the total now
   counts only the Jotform batches and the three partners' clubs;
   [plan](2026-10-15-attendance-total-three-partners.md).) Why: one object, one report type, one
   filter for the label; aggregates have no names, so no distinct count can include them.
   Consequences: a one-off back-fill of the 538 existing successes (C); the Monthly Report's
   weekly counts are never summed into attendance; `Girls_Enrolled__c` is created empty for
   BACKLOG 58 (if Ryan agrees).
3. **"Did not submit" = no `Attendance_Batch__c` of any status dated in the window** (a `Failed`
   duplicate counts as submitted), for three windows: last 14 days, since 1 September, last
   calendar month. **"Blank" = `Failed` "No participants submitted", or a legacy `Success` with
   `Girls_Present__c` 0.** The existing last-month tile stays row-based (Ryan, 2026-10-06: "no
   Jotform attendance rows"), beside the two batch-based windows, the difference named in the
   How-to box. Non-reporting clubs are excluded at the
   source, not with a Salesforce-side marker (Ryan, 2026-10-06; the sheet's `jotform=no` is the
   clubs-off plan's), so the lists carry the 50 clubs that cannot submit until their counts arrive.
4. **The batch report type carries the club's parent via lookup** (`Account__c` → Parent Name),
   so batch reports group by partner and the dashboard's one Partner filter drives every tile with
   no new field; a `Partner__c` formula (`Account__r.Parent.Name`) is created only if the validate
   refuses the two-hop path. The custom report type `Attendance_Totals` leaves `Contact_IDs__c` out;
   the vendor's `Attendance_Batches` type is left untouched.
5. **A stray club account the processor created is re-parented, never re-created** (its
   Contacts and rows stay) - done for the two WESAD clubs on 2026-10-06 10:53 UTC (Ryan's go, main
   `00ee471`; `00ee471` wrote BACKLOG 27 and the dashboard plan, not this file); until BACKLOG 27
   is automated, a new club's account is created before its first attendance by a weekly round of
   the 2026-09-30 procedure.
6. **Field permissions for the new fields are on the System Administrator profile** (the live
   integration user, the dashboard's running user and every reader are on it; Apex writes in a
   trigger need none); any other profile that types counts gets edit with the intake plan.
7. **The blank batch's message is the literal "No participants submitted"** - Ryan's `Failed`
   "No participants" plus one word, one value for the Apex constant, its tests, the report
   criterion and `outcome_of`'s prefix (confirmed by Ryan, 2026-10-06).

## Open decisions (for Ryan)

- **Intake** (F): Jotform aggregate form, coordinator in Salesforce (flow), or sheet import.
- `Girls_Enrolled__c` now, empty (recommended), or with BACKLOG 58.
- ~~Switch the existing last-month tile to batches of any status, or keep it row-based~~ -
  **decided 2026-10-06: kept row-based.**
- The 14-day and since-launch windows test the **session date** (recommended) or the day the
  submission arrived.
- The 50 clubs that cannot submit on Jotform in the "did not submit" lists: accept the padding
  (default), or a hand-typed `PARENT.NAME not equal to` filter for those ten partners (brittle),
  or a later status on the account.
- The three legacy blank `Success` batches: leave (default) or delete with Ryan's go.
- The twelfth U.S Club account (FemXFem's: no Roster rows, no batch): leave (default) or retire it
  in Salesforce (a write, Ryan's go) so the U.S padding is eleven, matching the Roster.
- The blank batch's stored message: "No participants submitted" (as planned) or his exact "No
  participants".
- Delivery: tiles only, or also a weekly report subscription to Ryan ("record count > 0") set in
  the Salesforce UI - not metadata, not in this plan.

## Proof

- Repo: `make check` → `CHECK PASSED` (the new test file `test/sf_girls_present_test.py` and the
  back-fill suite's new test counted in `OK`; `docs-links: ok`; `secrets: clean`), run by the
  orchestrator at the end.
- B, check-only: `sf project deploy validate -o glow -d force-app -l RunSpecifiedTests -t AttendanceBatchTriggerTest -t TestContactTriggerHandler`
  → `Status: Succeeded`, every test passing and 0 failing (23 in `AttendanceBatchTriggerTest`, 26
  with `TestContactTriggerHandler`'s 3), `AttendanceBatchProcessor` coverage ≥ 75% (92% before). After Ryan's deploy: `sf project retrieve start` of the class, test and object →
  identical to `after/`; the rolled-back anonymous run (**Ryan's go, or run by Ryan**; script
  pasted first) prints `blank: Failed No participants submitted / aggregate: Success 0 rows 25 /
  names: Success 2 rows 2` and leaves nothing behind (`SELECT COUNT(Id) FROM Attendance_Batch__c
  WHERE Account_Name__c = '<the made-up name>'` → 0 and the same on `Account`).
- C: `plan --vpn-off` → `to set: 538 … 7,041 rows`; `set` → `dry run: nothing was written
  (--apply writes, with Ryan's go)`; after `set --apply --vpn-off` → `set and read back: 538`; then
  `SELECT COUNT(Id) FROM Attendance_Batch__c WHERE Processing_Status__c = 'Success' AND
  Girls_Present__c = null` → 0 and `SUM(Girls_Present__c)` over `Success` = `COUNT(Id)` of
  `Attendance__c` (7,041 at the time of writing; re-read); `check --vpn-off` → `differ: 0,
  without a value: 0`. A second `set` → `to set: 0`.
- D, check-only: `sf project deploy start --dry-run -o glow -d force-app` from `totals1/` →
  `Status: Succeeded`, N of N components, 0 errors. After Ryan's deploy: every row of the
  read-back table equals its SOQL; the dashboard's 19 components all return data through the
  dashboards API; the Partner filter on WESAD shows 30 clubs and every tile equal to SOQL with
  `Account__r.ParentId = '001RP000002nR7mYAE'`; the retrieve differs from the build only in
  Salesforce's normalisation (`expandOthers`, default attributes), as before.
- E (already true, re-read 2026-10-06 after the re-parent): `SELECT COUNT(Id) FROM Account WHERE
  RecordType.DeveloperName = 'Club' AND ParentId = null` → 2; `SELECT COUNT(Id) FROM Account WHERE
  ParentId = '001RP000002nR7mYAE'` → 30. Re-read once more before D's WESAD read-back.
- Nothing written to Jotform, the sheet or GitHub by any step; every Salesforce write this plan
  makes (the 538 field updates; the anonymous proof run, which commits nothing) is on Ryan's go,
  read back, and - for the updates - reversible by id.

## Order across the four plans (cross-plan review, 2026-10-06)

The four plans of this day - [module](2026-10-06-module-selection.md) (1),
this plan (2), [clubs-off](2026-10-06-clubs-off-jotform.md) (3) and
[photos](2026-10-06-photos-to-drive.md) (4) - share one branch, three files
(`tools/form_status.py`, `tools/auto_sync.py`, `tools/sf_backfill.py`), three docs
(DECISIONS, BACKLOG, RUNBOOK, plus the two skills and CLAUDE.md) and Ryan's time. This section
is the one sequence; each plan's own "Order of work" holds inside its slot.

**Preconditions as they stand.** Session -54's rollout is recorded complete on `main` `9d58ce4`
(every form CLEAN, `AUTO_SYNC_APPLY=1` at 11:23 UTC, Latin America's module values live 11:17 UTC):
every "after -54's window closes" in the four plans is met: -54 confirmed to this session,
in so many words, that its window closed at 11:23 UTC on 2026-10-06 and that live form work may
resume on top of `main`. Session -51's `fix1` is live
(09:29 UTC), so plan 2 D has its base. BACKLOG numbers: `main` holds 65 (`9d58ce4`); plan 1 takes
66-67, plan 4 68-70, plan 3 71, plan 2 72-73 (re-checked when each is committed). `main` is
**merged** into the branch (never rebased: four plans and the orchestrator hold its commits).

**A. One merge, then the plans committed** (offline). Merge `main` (`9d58ce4`); commit the four
plans and three intents (plan 1 keeps the 2026-09-01 club-picker intent); `make check` by the
orchestrator. Tell -54 (nothing here writes a form until it confirms; plan 1 (a), plan 3 steps
7-10 and plan 4's builder steps wait on that) and -51 (plan 2 D's `gen.py` additions, plan 4's one
Access bullet, plan 1 step 4's module-chart change in the data).

**B. Offline code, serial on the shared files** (no live dependency; each commit green on
`python3 test/python_test.py`). Smallest edits to `form_status.py` / `auto_sync.py` first, so the
large one merges onto them:
1. Plan 4 part 1: `tools/integration_status.py` `UPLOADS = []`, its test, the `other
   integrations:` line; docs rows.
2. Plan 1 (a) `audit_module_shape` + `CLEAR_FIELD_ON_HIDE`, and plan 4's `glow/usage.py` +
   `storage:` line + `check_storage` - the two `form_status.py main()` additions in one commit or
   two adjacent ones (plan 4 asked for exactly this), after -54's confirmation (B.2 is the one
   offline step that edits the file -54 verified with).
3. Plan 1 (b) `tools/fix_module_values.py` + **`Org.update`** (+ `FakeOrg.update`), then plan 2 C
   `tools/sf_girls_present.py` on the same `Org.update`; the shared `test/python_test.py` import
   block and the shared live-systems paragraph ("written in two ways only" → the two `--apply`
   tools and the anonymous Apex run) written once.
4. Plan 3 code: `glow/sync.py` (`PARTNER_COLS`, `read_partners_csv`, `RETIRE_INACTIVE`), the sync,
   the runner (`--partners`, `skipped`, the bands), `form_status.py` (`--partners`, the `DISABLED`
   skips), the two tools, the Apps Script sources, parity tests. Plan 3's step 4 rehearsal (scratch
   Partners export, dry runs, `form_status --partners`) closes this block - reads only.
5. Plan 2 step 3 (`sf_backfill.py` hold wording, fake org) is held until C's deploy below: the
   docstring describes the live processor.
Docs touched by several plans land per block, serially: `jotform-api` SKILL.md (plan 1's
`clearFieldOnHide` bullet; plan 4's "Integrations" rename and usage fields; plan 3's `status` and
`always-hidden` facts), CLAUDE.md (plan 3's `--partners` on the two command lines and rules 6-7;
plan 4's `storage:` in the healthy tail - the same command line, one edit), RUNBOOK "Automatic
sync" (plan 3's `skipped`, plan 4's storage ATTENTION). The RUNBOOK dashboard section is edited
in this branch by plan 2 (D's tiles) with plan 4's Access bullet riding in the same edit, after
-51 is told; -51 owns `gen.py`, not the RUNBOOK text about its output.

**C. Salesforce, one CLI sitting with Ryan** (VPN off; the hook sees none of `sf …`, BACKLOG 53,
so every step is Ryan's go in the conversation or his hands):
1. Plan 2 A + B: retrieve → `before/`; the fields, profile, class, tests → `after/`; review;
   `sf project deploy validate` (check-only) → **Ryan's quick deploy** at a quiet moment; retrieve
   and compare; the rolled-back anonymous proof (Ryan's go, script pasted first).
2. Plan 2 step 3 (repo follow-through: `sf_backfill.py`, its tests, RUNBOOK/DECISIONS lines).
3. Plan 2 C: `plan --vpn-off` → `set` (dry) → Ryan's go → `set --apply --vpn-off --limit 1` → the
   rest → the two equalities → `check` 0/0.
4. Plan 1 (b), same sitting, independent field: `fix_module_values.py --vpn-off` (dry: 6 batches,
   43 rows, 0 UNMATCHED, **and no batch created after 11:17 UTC with a non-canonical module** - 0
   Latin America batches of any module since 11:30 UTC when this was written; re-read on the day,
   and Ryan's Tooling-API query for validation rules on `Module__c` first) → Ryan's go →
   `--apply --vpn-off --limit 1` → the rest → `nothing to correct`; tell -51 (its module chart).
   C.3 and C.4 touch different fields and re-read only the field they wrote, so their order is
   free; both before D so the first totals and the module chart read clean.
5. Plan 2 D with -51 in `gen.py` after `fix1`: report type, reports, labels, tiles → `totals1/` →
   check-only validate (it settles the formula-as-filter-column and `LAST_N_DAYS:14` spellings) →
   **Ryan deploys** → read-back table against SOQL, the WESAD filter (30 clubs).
6. Plan 2 F is Ryan's intake decision → its own plan; the first aggregate batches are dated the
   last day of a month and land only after plan 3's Africa apply (D below) - the 38 clubs must be
   off the picker before a club of theirs can hold a `Success` batch, or a stray mentor
   submission that day is `Failed` "Duplicate" (plan 2 B, pinned by a test).

**D. Jotform and the sheet, Ryan's goes, in this order** (after -54's confirmation; `main`
merged and pushed before Africa):
1. Plan 4 builder steps 3-5 on the **template** (unmap q19 with every form backed up first, the
   Drive block, the arranged test submission, the test batch deleted on Ryan's go). No runner pause
   needed (integrations are not conditions; rule 3 does not bite) - a quiet moment and
   `form_status.py` CLEAN after each save. Before plan 3's template apply, so the template's one
   test submission and its CLEAN read are not confounded with the retirement rewrite.
2. Plan 3 steps 5-6: the Partners tab cells (Ryan, UI), the real Partners export, the sync's dry
   run from it; `deactivate_clubs.py --check-only` on the three partners (0 / 0 / 1 accidental
   pick, 2026-09-25) and on U.S (0).
3. Plan 3 steps 7-10 in **one sitting** with `AUTO_SYNC_APPLY=0`: template apply (Ryan's go) →
   `form_status --partners --rendered` CLEAN with 38 retired / 38 `always-hidden` and the
   headless-Chrome check → merge to `main` and push → one runner dry run from `main` (Africa
   `attention`, the rest `in-sync`) → Africa apply (Ryan's go) → CLEAN → U.S form disabled
   (`disable_form.py --apply`, or the builder if the API does not take the write) → U.S rows
   deactivated (`deactivate_clubs.py --region U.S --apply`) → `Update form dropdowns from the
   Roster` → `AUTO_SYNC_APPLY=1` → one manual run: Africa / Asia / Latin America `in-sync`, U.S
   `skipped`. Until the Africa apply every runner run exits 2 and holds Africa's roster changes:
   the sitting is short, and Ryan hears that before it starts.
4. Plan 4 step 7 on the three regionals (Latin America, Asia, Africa: backup, the Drive block,
   diff, CLEAN), after D.3 so Africa is read CLEAN once, with its retirements in; the read-back
   is each form's first real photo in Drive. Then plan 4 step 8 (`DRIVE_WANTED = True`: the U.S
   form reads `DISABLED` after D.3). Plan 1's `form_status --rendered` on all five accepts
   `rendered: skipped (form DISABLED)` on U.S from here on.
5. Plan 3 step 11, any later quiet moment: `clasp push` of `Roster.gs` / `FormHandlers.gs` (no new
   scope, no rule-11 window).

**E. Results and the log.** Each plan's Result, DECISIONS (plan 1: 1 row; plan 2: 7; plan 3: 5;
plan 4: 3 - no two rows decide the same thing; plan 2 row 3 and plan 3 row 1 are one decision seen
from Salesforce and from the sheet, worded to agree), BACKLOG (27, 55, 58, 60, 65 updated; 66-73
new), RUNBOOK, the work log.

Interactions checked and where they are settled: the Apex backstop against aggregate batches -
`Girls_Present__c > 0` exempts them (plan 2 B, tested); aggregates against the processor's
club-and-day lock - month-end dates and the 38 clubs off the Africa picker (plan 2 B, plan 3 A;
C.6 above orders the first aggregate after the Africa apply); the 50 non-Jotform clubs in the
"did not submit" lists - accepted padding, no Salesforce marker (plan 2 Risks and Open decisions;
plan 3 E says the same); the disabled U.S form - `skipped` by the runner (plan 3 D), `drive: not
wanted` (plan 4), `rendered: skipped` for plan 1's audit; two tools writing `Attendance_Batch__c`
- one `Org.update`, one auth and VPN rule, one ledger shape, different fields (B.3, C.3-4); three
plans editing `form_status.py` and two editing `auto_sync.py` - serial commits in B.2 → B.4 after
-54's confirmation.

## Result

All Salesforce steps on 2026-10-07 in one CLI sitting, each write on Ryan's go, VPN off.

**A + B, the fields and the processor - live in production since 2026-10-07 03:22 UTC.**

- Check-only validation `0AfRP000002gKnZ0AU` (`RunSpecifiedTests`: `AttendanceBatchTriggerTest`
  and `TestContactTriggerHandler`): 26 of 26 tests passed (23 + 3), `AttendanceBatchProcessor`
  coverage 93% (92% before).
- Quick deploy `0AfRP000002gKqn0AE` at 2026-10-07 03:22 UTC, on Ryan's go. Retrieved back
  afterwards: what is live equals what was built (`data/sf_totals_2026-10/after/`; the rollback is
  `before/`, redeployed - the fields can stay).
- Fields: `Attendance_Batch__c.Girls_Present__c` and `Girls_Enrolled__c`, both Number(18, 0), read
  and edit on the System Administrator profile (`Admin`) only. `Girls_Enrolled__c` is empty and on
  no report (BACKLOG 58).
- The rolled-back anonymous Apex proof ran once and printed `blank: Failed No participants
  submitted / aggregate: Success 0 rows 25 / names: Success 2 rows 2`; 0 records were left
  behind.
- Tooling API: 0 validation rules on `Attendance_Batch__c` and on `Attendance__c` (the Risks'
  "a `PATCH` on a batch with a validation rule nobody has read" for C, and plan 1's `Module__c`
  correction).
- What the processor does now: blank `Contact_IDs__c` and no count → `Failed` "No participants
  submitted", no rows, blocks nothing; blank and `Girls_Present__c` > 0 → `Success` with no rows
  (an aggregate, its count kept); names → as before, plus `Girls_Present__c` = the rows created;
  every `Failed` path clears `Girls_Present__c` to empty.

**Step 3, the repo follow-through - done (2026-10-07, offline).** `tools/sf_backfill.py`: the
docstring; the `salesforce_has_empty_or_failed_batch` hold's text (it says "a batch or rows", since
`send_one` refuses on either); the `plan` listing's text; `outcome_of` → `no_participants`;
`verify` reads `Girls_Present__c` and, on a `Success`, a count other than the rows (or no count) is
`CHECK` (a `Failed` batch is `CHECK` already by its status, and the processor clears the count on
it). `test/sf_backfill_test.py`: the docstring, `FakeOrg.insert` as the new processor, the
listing and `BATCH-000001 Failed` assertions, the refusal test's comment, one new test (a
`Success` whose `Girls_Present__c` is 2 or empty for 3 rows is `CHECK`; 3.0 as Salesforce gives
it is `ok`) and one assertion added to the status-kind test (`no_participants`). The refusal hint
of `tools/sf_girls_present.py` now also names the profile; RUNBOOK ("The names list sent to
Salesforce", "Back-fill of attendance into Salesforce", "Attendance totals and partner-reported
counts"), DECISIONS (the four A/B rows; the two D rows stay pending) and BACKLOG 65 say it is
deployed.

**C, the one-off back-fill of `Girls_Present__c` - done (2026-10-07).**

- `plan --vpn-off` (fresh): 606 batches, 575 `Success` and 31 `Failed`; 2 of the successes
  already carried a count from the new processor (Queens of Quest's two released batches), so
  573 to set.
- `set --apply --vpn-off --limit 1`: BATCH-000000 set to 2 = its 2 rows, read back by the tool and
  re-read independently; then `set --apply --vpn-off` for the remaining 572. Ledger: 573 `open` →
  573 `written`, no failure (`data/sf_girls_present/`, never committed).
- `check --vpn-off` → `575 Jotform Success batches; differ: 0, without a value: 0 -> OK`.
- SOQL afterwards: 0 `Success` batches with an empty `Girls_Present__c`; `SUM(Girls_Present__c)`
  over `Success` = **7,540** = `COUNT(Id)` of `Attendance__c` 7,540.
- Session -54's contact merges (19 duplicates, done 03:57 UTC) moved rows between Contacts and
  changed no row count.

**D, the reporting - deployed 2026-10-07 03:59:58 UTC (deploy `0AfRP000002gLJp0AM`, 8 of 8).**

- The first check-only run of `totals1/` failed 4 of 8; the two `gen.py` fixes (the locale date in
  the cross filter, `MONTH_COLUMNS`) are in the Build notes above. After them: 8 of 8, 0 errors;
  the seven existing reports byte-identical to `after2/`.
- Backup of what was live, taken first: `data/sf_dashboard_2026-10-02/live_2026-10-07/` (the
  dashboard and the 7 reports).
- Retrieve after the deploy: what is deployed = what was built, apart from Salesforce's
  normalisation (`expandOthers` → true, `useReportChart` dropped, `showPicturesOnCharts` and the
  owner added, apostrophes escaped).
- Report ids: `Total_Attendance_by_Partner_by_Month` 00ORP000009c8ic2AA,
  `Jotform_Attendance_by_Partner_by_Month` 00ORP000009c8ia2AA, `Total_Attendance_Last_Month`
  00ORP000009c8ib2AA, `Clubs_Not_Submitting_Last_14_Days` 00ORP000009c8iY2AQ,
  `Clubs_Not_Submitting_Since_1_Sept` 00ORP000009c8iZ2AQ, `Blank_Submissions` 00ORP000009c8iX2AQ.
- **Partner via lookup works**: Analytics token `Attendance_Batch__c.Account__c.Parent.Name`
  (metadata `Account__c.Parent` / `Attendance_Batch__c$Account__c.Parent`); the `Partner__c`
  formula fallback was not needed and does not exist.
- **Read-back** (read only, 04:02-04:13 UTC; the org's time zone is America/Los_Angeles, so
  `LAST_MONTH` = September): **264 of 264 report/SOQL pairs equal**, every grand total and every
  group.

| Tile / report | Report = SOQL |
|---|---|
| Total attendance, last month | 6,618 (490 `Success` batches) |
| Total attendance since 1 Sept | 7,437 (September 6,618, October 819) |
| Jotform only | = total everywhere (no partner-reported batch exists yet), and = `COUNT(Attendance__c)` for each window |
| Clubs not submitting, last 14 days | 195 (window 09-22..10-06 Pacific: today plus the 14 days before it) |
| Clubs not submitting since 1 Sept | 175 |
| Blank submissions since 1 Sept | 3 (the three legacy blanks; no "No participants submitted" batch yet) |
| Clubs with no attendance last month (the existing, row-based tile) | 189 = SOQL with its cross filter (187 on batches of any status: two clubs sent only blank or failed batches) |

- **Dashboard**: 5 refreshes (unfiltered, WESAD, Fundación Kaleidos, Ng'aa Maskani, unfiltered
  last), all 18 report components `DATA` with no error each time; every new tile = SOQL under
  each filter (WESAD 405 attendance last month and 18 clubs not submitting; Fundación Kaleidos
  126; Ng'aa Maskani 16 not submitting, 0 attendance). Left unfiltered. The seven earlier reports
  run and equal SOQL.
- **Not testable yet**: total ≠ Jotform only (needs a first partner-reported batch, F) and the
  "No participants submitted" branch of Blank Submissions (needs a first live blank).

**Still open**: F, the intake for partner-reported counts (Ryan's decision, BACKLOG 72; its own
plan). The first aggregate batch is also the first live proof that total and Jotform only part.

## From the RUNBOOK (moved 2026-10-09)

What `docs/RUNBOOK.md` carried for this plan until its 2026-10-09 restructure (the procedure as run, or its history), word for word (links re-pointed to this folder); the RUNBOOK keeps a stub that links here.

### "Attendance totals and partner-reported counts": status

 The field and the processor change (plan sections A and B) are
**deployed since 2026-10-07 03:22 UTC** (Ryan's quick deploy `0AfRP000002gKqn0AE` of validation
`0AfRP000002gKnZ0AU`; rollback: redeploy `data/sf_totals_2026-10/before/`, the fields can stay).
The one-off back-fill below (plan C) is done and the dashboard's totals (plan D) are deployed,
both on 2026-10-07 ("Attendance dashboard in Salesforce"). Open: how the partners' counts come
in (BACKLOG 72).

### "Attendance totals and partner-reported counts": the one-off back-fill

**The one-off back-fill** (`tools/sf_girls_present.py`) - **done 2026-10-07**, on Ryan's go, VPN
off. The batches from before the deploy had the field empty, so the totals would have
under-counted every one of them. `plan` read 606 batches (575 `Success`, 31 `Failed`; 2
successes already counted by the new processor), `set --apply --limit 1` wrote BATCH-000000
(2 = its 2 rows, read back and re-read independently), then the remaining 572: ledger
(`data/sf_girls_present/ledger.csv`) 573 `open` → 573 `written`, no failure. `check` → `575
Jotform Success batches; differ: 0, without a value: 0 -> OK`; SOQL: 0 `Success` batches without
a value, and `SUM(Girls_Present__c)` over `Success` = 7,540 = `COUNT(Id)` of `Attendance__c`.
Since then the processor sets the count on every new batch, and **`check` is the signal**
(Signals, below). The commands, for the record and for a re-run (a second `set` finds `to set:
0`; the CLI login, VPN off; the hook sees `--apply` only):

```bash
python3 tools/sf_girls_present.py plan --vpn-off            # read-only -> data/sf_girls_present/plan.csv (ids and counts)
python3 tools/sf_girls_present.py set                       # dry run from the plan: "to set: N Success batches with no Girls present"
python3 tools/sf_girls_present.py set --apply --vpn-off --limit 1   # Ryan's go: one batch, read back
python3 tools/sf_girls_present.py set --apply --vpn-off     # the rest, one PATCH per batch, each re-read before and after
python3 tools/sf_girls_present.py check --vpn-off           # "differ: 0, without a value: 0 -> OK"
```

It writes only a `Success` batch whose value is still empty, = its attendance rows (0 for the
legacy blanks, BACKLOG 73); a `Failed` batch stays empty, as the processor leaves it, so the field
means one thing; a batch with a value - a typed aggregate, or a count the processor set - is
never touched, so a second `set` finds `to set: 0`. The ledger (`data/sf_girls_present/ledger.csv`,
owner only: when, id, rows, value read back, outcome `open` then `written` / `failed_<status>` /
`check` - 204 answered but the value not confirmed: look at the batch) says what was written; the
run stops at the first thing not as planned. The rows are counted one GROUP BY per 200 batch ids
(an aggregate query has a single page), so the check keeps working as the batches grow. A read
Salesforce refuses for the field (HTTP 400: an org without it, or a login not on the System
Administrator profile, the only one that can read it) stops `plan` and `check` with "is
`Girls_Present__c` deployed?" and names the profile. An update runs none of the
processor (after-insert trigger). After the run, read-only: `SELECT COUNT(Id) FROM
Attendance_Batch__c WHERE Processing_Status__c = 'Success' AND Girls_Present__c = null` → 0, and
`SELECT SUM(Girls_Present__c) FROM Attendance_Batch__c WHERE Processing_Status__c = 'Success'` =
`SELECT COUNT(Id) FROM Attendance__c` (both re-read at the time; live submissions keep arriving).
