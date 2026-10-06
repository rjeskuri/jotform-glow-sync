---
title: The module a submission sends is one required dropdown and exact text
author: Claude (with Ryan's decisions of 2026-10-06; from the read-only module investigation of the same day)
status: accepted         # Ryan 2026-10-06 (in conversation), with the defaults of the "Open decisions" unless noted in the plan
created: 2026-10-06
intent: docs/intent/2026-09-01-club-picker.md (the attendance form sends what Salesforce must match; nothing new is built on the forms)
---

# Plan: one module per submission, pinned by an audit, and the six Spanish modules in Salesforce corrected

## Context
Ryan asked that only one module can be selected on an attendance submission, and that the module
reaching Salesforce be the real (English) option. Read on 2026-10-06, GET only, on the template,
Africa, Asia and Latin America (the read-only investigation of 2026-10-06 that preceded this plan):

- **The chain is already one required single-select per step.** Year q94 (`required` Yes,
  `multipleSelections` No, `calcValues` `|1|2|3`) shows the module dropdown of that year (q14 / q92 /
  q93: each `required` Yes, `multipleSelections` No), which shows the session dropdown of that
  module's count (q15 / q95 / q96 / q97, each required, single-select, `calcValues` set). The
  hidden q98 / q100 / q102 copy them for Salesforce. All of it is generated: `build_conditions`
  section B (`sync_attendance_form.py:303-315` at 50126b3; `307-319` on `main`) and C
  (`:325-332`; `329-336`); the qids are `glow/sync.py:32-35` (`YEAR`, `MODULES`, `WEEKS`,
  `MODULE_ID`, `WEEK_ID`, `YEAR_ID`) and `appsscript/Config.gs` mirrors them (CLAUDE.md rule 7).
  Re-read on the template twice on 2026-10-06 for this plan: before session -54's template apply,
  the same properties; after it, the same shape (each dropdown still `required` Yes,
  `multipleSelections` No) and q14 / q92 / q93 now carry `calcValues` (6 / 8 / 9 slots: the
  placeholder slot plus the options). Line numbers below are given at 50126b3 (this worktree)
  unless marked `main:`; the `main:` numbers were verified at 00ee471 (-54's merge is 3ea1cab, one
  commit earlier); `main` is now 9d58ce4 (-54's Result, docs only: the code lines are unchanged).
- **A hidden dropdown's answer never reaches the submission.** The form-level property
  `clearFieldOnHide` is `disable` on all five forms (`GET /form/{id}/properties`, 2026-10-06:
  the investigation read the template, Africa, Asia and Latin America; the U.S form
  262382706852058 was read for this plan's review). In Jotform's runtime (build
  `fc726a121d4`) the submit handler empties every input inside a `.form-field-hidden` element unless
  the value is `dontClear`; so a module dropdown hidden by the Year rule may keep its pick *in the
  page* but it is cleared *at submit*. The data is the guarantee: **0 of 674 submissions since
  2026-09-01** (Asia 321, Latin America 142, Africa 211) carry two module answers, a blank year, a
  blank module, a blank q98, or a q98 that names another option than the chosen dropdown's.
- **The one defect is page translation, and it is being fixed.** 36 Latin America submissions
  (30 in September, 6 in October) have q98 = a Spanish rendering of the module because the module
  dropdowns had no `calcValues`. Session -54's accepted plan
  ([names and modules](2026-10-02-names-and-modules.md), fix 4) gives them `calcValues`
  (`glow/sync.py` `MODULE_CALC_VALUES`, merged on `main` in 3ea1cab) and audits them
  (`tools/form_status.py` `audit_module_values`, `main:229-254`); the live rollout, template then the
  regionals, ran with `AUTO_SYNC_APPLY=0` and is recorded complete in its Result (`main` 9d58ce4:
  every form CLEAN, `AUTO_SYNC_APPLY=1` at 11:23 UTC; Latin America's module values live 11:17 UTC).
  "After -54's window closes" below is therefore -54's confirmation, not a wait. In Salesforce, `Attendance_Batch__c` since
  2026-09-01 holds 22 distinct `Module__c` values: 17 canonical and **5 Spanish on 6 batches**
  (5 Success, 1 Failed) created 2026-10-01..05 by the live flow, with **43 `Attendance__c` rows**
  under them (re-read for this plan, counts only: Autodefensa 1 batch / 8 rows, Comunidad 201
  1 / 10, El poder de las chicas 101 1 / 5, Optativa - Compromiso académico 1 / 6, Toma de
  decisiones 2 / 14). Two of the six are dated September (`Attendance_Date__c` 2026-09-30 with 8
  rows and 2026-09-24 with 14; the Failed one, 2026-09-17, has no rows), the other three October.
  The processor copies the batch's `Module__c` onto every row it creates
  (`AttendanceBatchProcessor.cls:449`), so the rows are wrong with their batch. This set grows
  until -54's `calcValues` are live on Latin America (36 of its 142 submissions carried a
  translated q98): the counts are a snapshot, not the stop condition (Risks).
- **Nothing else fires on the two objects** (read connector, 2026-10-06): `SELECT Name,
  TableEnumOrId, Status, UsageAfterInsert, UsageAfterUpdate, UsageBeforeUpdate, UsageBeforeInsert
  FROM ApexTrigger WHERE TableEnumOrId IN ('Attendance_Batch__c','Attendance__c')` → exactly one
  row, `AttendanceBatchTrigger` on `Attendance_Batch__c`, Active, `after insert` only (every
  update / before / delete flag false; nothing on `Attendance__c`). `SELECT ApiName,
  TriggerObjectOrEventId, TriggerType, RecordTriggerType FROM FlowDefinitionView WHERE IsActive =
  true AND ProcessType = 'AutoLaunchedFlow' AND TriggerType != null` → 7 flows, on Account,
  Opportunity and two other custom objects; none on `Attendance_Batch__c` (EntityDefinition
  DurableId `01IRP00000B67Js`) or `Attendance__c` (`01IRP00000B67Jt`). So a PATCH of `Module__c`
  runs no code of the org's; only validation rules stay unverified (Tooling API, Proof).

## Decision: no form change, and nothing restrictive in Salesforce
Ryan, 2026-10-06: a precaution, nothing seen. The form already enforces what was asked; the only
work is to **pin** that shape so a builder change cannot silently undo it, and to **correct** the
six batches once the fix upstream is live.

A Salesforce-side picklist or validation rule on `Module__c` is **ruled out**:
- `Module__c` is a free 255-character text on `Attendance_Batch__c` and `Attendance__c` (schema read
  2026-10-06); Jotform's Salesforce V2 integration writes it as text. A restricted picklist or a
  validation rule would make Salesforce **reject the insert of a batch whose module it does not
  know - and the attendance does not reach Salesforce** (the submission and its photo stay in
  Jotform; whether the integration retries or lets staff resend it from the builder is
  unverified: nothing in the repo documents a rejected insert). The five Spanish batches were
  accepted and processed; with a rule they would be waiting in Jotform for a hand, not corrected
  in place.
- The module list follows the curriculum (the live dropdown options and `SESSION_OVERRIDES`,
  `glow/sync.py:232-236`; `main:264-268`); a picklist would need a metadata deploy by Ryan for every
  change, in step with five forms.
- The source of non-canonical text is the form (page translation), and -54's `calcValues` remove
  it there. What remains is an audit and a one-off correction.

**DECISIONS.md row to add** (one line, the table's four columns; the two links are written to
resolve from this file - in `docs/DECISIONS.md` they take the `plans/` prefix):

> | 2026-10-06 | The module a submission sends stays as it is: one required single-select per year, hidden ones cleared at submit (form-level `clearFieldOnHide=disable`), the hidden q98 copied for Salesforce. No form change; no picklist or validation rule on `Module__c` in Salesforce. What is added: `form_status` pins the shape (NOT CLEAN on a multi-select, an optional dropdown or any `clearFieldOnHide` but `disable`), and the six batches that carry a Spanish module (and their 43 rows) are corrected once by `tools/fix_module_values.py` after fix 4 of [names and modules](2026-10-02-names-and-modules.md) is live, with Ryan's go | 0 of 674 submissions since launch carry two modules or a blank one; the one defect (36 Latin America submissions with a page-translated q98) is fixed at its source by the module `calcValues`; a Salesforce rule would reject such a batch - the attendance then stays in Jotform and reaches Salesforce only by hand - instead of correcting it | the runtime's "cleared at submit" behaviour is Jotform's, audited not guaranteed; the correction is a Salesforce write through the CLI login (`--apply`, caught by the live gate; a new Salesforce writer in the live-systems skill) with a ledger for rollback ([plan](2026-10-06-module-selection.md)) |

## Work

### (a) `tools/form_status.py`: the `module shape` line
Built on `main` as merged (00ee471 or later), **after session -54 says its rollout window is
closed** (its verify step runs `form_status.py`; no change to that file while it is in use).

- `glow/sync.py`: one constant next to `MODULE_CALC_VALUES` (`main:131`),
  `CLEAR_FIELD_ON_HIDE = "disable"`, with the runtime reading above as its comment. Audit only -
  the sync's one PUT to `/properties` carries the `conditions` key alone
  (`sync_attendance_form.py:1194`) and never touches `clearFieldOnHide`. No `Config.gs` mirror: it
  is not a qid, form id or column (rule 7 does not apply; said here so the review does not ask).
- New `audit_module_shape(questions, props)` placed directly after `audit_module_values`
  (`main:229-254`), returning `(problems, summary)`. Problems, each a NOT CLEAN line:
  - q94 (`glow_sync.YEAR`): not `control_dropdown`, `multipleSelections == "Yes"`,
    `required != "Yes"`, or `hidden == "Yes"` (the chain starts visible);
  - each of `glow_sync.MODULES` and `glow_sync.WEEKS`: not on the form, `multipleSelections ==
    "Yes"` ("a mentor could send two modules; question 98 would run them together"), or
    `required != "Yes"` ("a blank module reaches Salesforce");
  - `props.get("clearFieldOnHide") != glow_sync.CLEAR_FIELD_ON_HIDE`: `dontClear` → "a module
    dropdown hidden by the Year rule would keep its answer at submit"; `enable` → "rejected
    2026-09-30: the loop limit drops to 3 (DECISIONS)"; missing or anything else → "a value whose
    runtime behaviour has not been read: do not treat hidden answers as cleared". No guess.
  `form_report` already fetches the properties (`props`, `main:792`); the call goes right after
  `module_problems, module_summary = audit_module_values(questions)` (`main:822`), its summary into
  `rep["module_shape"]` beside `"module_values"` (`main:872`), and the printed line after
  `module values:` (`main:966`):
  `module shape: year q94 single-select required; modules q14/q92/q93 single-select required;
  sessions q15/q95/q96/q97 single-select required; clearFieldOnHide disable`.
- `--rendered`: in `rendered_module_problems` (`main:487`) read the served page's
  `JotForm.clearFieldOnHide="…"` (seen on the served template page 2026-10-06) and compare with the
  constant;
  and flag a `multiple` attribute on any module `<select name="q14_…">` (the same regex family as
  `rendered_calc_values`, `main:338-361` - `:217` at 50126b3 - and the `<select>` match of
  `rendered_options`, `main:323`). Counts and property values only; the page is never printed or
  saved.
- Tests in `test/python_test.py`, class `ModuleAndNamesAudit` (`main:6647`): the template shape
  is clean; a `multipleSelections: "Yes"` on q92 is flagged; `required: "No"` on q94 and on q15 is
  flagged; `clearFieldOnHide` `dontClear`, `enable` and missing each give their own line; a served
  page with `JotForm.clearFieldOnHide="dontClear"` fails `--rendered`. Fixtures: dropdowns and module
  names only (no roster names).
- `docs/RUNBOOK.md`, section "The names dictionary and the module values" (`main:1029`): three
  lines on the new report line and what each NOT CLEAN message means (fix: the builder's form
  settings, then re-run; never a sync apply - the sync does not write it).

### (b) `tools/fix_module_values.py`: the one-off Salesforce correction
Standard library, argparse, `print()`, dry run by default. Modelled on `tools/sf_backfill.py`
(its doc, `:1-28`; `Org`, `:168-238`) and `tools/backfill_resolve.py` (the submission readers).

- **Canonical options**: read live from the template's module dropdowns, as the sync does
  (`sync_attendance_form.py:521-523`, `main:525-527`, `module_options`:
  `questions[mqid]["options"].split("|")` for `MODULES`): 5 + 7 + 8 options, 18 distinct (two
  electives sit in both year 2 and 3). The tool never hardcodes a module name or a language.
- **Salesforce side** (through `sf_backfill.Org`, imported like `sf_club_accounts` is at
  `sf_backfill.py:45-46`; the token comes from `sf org auth show-access-token` *inside* the tool and
  goes to curl on stdin, never printed - RUNBOOK "Back-fill of attendance into Salesforce"):
  `SELECT Id, Account_Name__c, Account__c, Account__r.Parent.Region__c, Attendance_Date__c,
  Module__c, Module_Week__c, Module_Year__c, Processing_Status__c, Creator__c, CreatedDate FROM
  Attendance_Batch__c WHERE CreatedDate >= <since>` (default `2026-09-01T00:00:00Z`,
  `backfill_resolve.SINCE`'s day), keep those whose `Module__c` is not a canonical option; for
  each, `SELECT Id, Module__c FROM Attendance__c WHERE Attendance_Batch__c = <quoted id>` (one
  query per batch, `sf_backfill.quoted`; its length is the row count). **Every read of a record is
  one of these two explicit-field SOQL queries through `Org.query`** - the re-read after a write
  too (`SELECT Id, Module__c FROM Attendance_Batch__c WHERE Id = <quoted id>`, and the rows query
  again, as `sf_backfill.verify` reads back, `:853-856`); never `GET /sobjects/<type>/<id>`, which
  returns every field. **Never selected**: `Contact_IDs__c` (the girls' names, a 32k textarea),
  `Status_Message__c`, any Contact field (`sf_backfill.py` doc, `:21-22`).
- **Ground truth = the Jotform submission's dropdown**, per batch: the form of the batch's region
  - `Account__r.Parent.Region__c` holds `Africa`, `Asia`, `South America`, `North America` (read
  2026-10-06; all six batches `South America`), the forms are `glow.forms.REGIONALS` (`Latin
  America`, `U.S`), so the tool carries the four-entry map `SF_REGION_FORM` with a test, and a
  value it does not know is `UNMATCHED (region)` - and only the submissions whose `created_at`
  (Jotform's clock, US Eastern - `zoneinfo`) lies within 3 hours either side of `CreatedDate`:
  `GET /form/{id}/submissions?filter=<urlencoded {"created_at:gt": …, "created_at:lt": …}>`
  (verified 2026-10-06: both bounds narrow the list; `glow.jotform.Client.url` does not encode
  its parameters, so the tool `urllib.parse.quote`s the filter itself), paged like
  `backfill_resolve.fetch_submissions` (`:153-177`) without its whole-form count check (the window
  is not the form). `--all-forms` fetches the four forms whole, as the resolver does, for a batch
  whose region or window the narrow read cannot serve. A submission matches a batch when
  `text_of(sub, CLUB_NAME)` (q5, `:192-197`) equals `Account_Name__c`, `attendance_date(sub)`
  (q17, `:239-248`) equals `Attendance_Date__c`, `answer_of(sub, MODULE_ID)` (q98, `:186-189`)
  equals the batch's `Module__c`, and `int(answer_of(sub, YEAR)) == int(Module_Year__c)` and
  `int(answer_of(sub, WEEK_ID)) == int(Module_Week__c)` (Salesforce gives doubles, Jotform
  strings: compared as integers; a value that is not an integer on either side → `UNMATCHED`).
  Exactly one match, else the batch is listed as `UNMATCHED (n candidates)` and nothing is
  written for it: a same-day re-send of the same club, date and module inside the window gives
  its Success batch and its Failed `Duplicate` batch two candidates each, both `UNMATCHED` by
  design, corrected by hand with their ids (none of the six today: each has exactly one
  candidate, within a minute of `CreatedDate`). The English module is `copied_fields(sub,
  questions)[0]` (`:308-322`): the *stored answer* of the module dropdown the Year answer names,
  through `stored_option` (`:274-294`) - the calcValue copy that `stored_option` now also returns
  on a form with -54's `calcValues` is ignored for the module, so the ground truth is the same
  before and after -54's apply - which must be one of that dropdown's options today and one of
  the 18 canonical options.
- **Output** (club names, dates, ids and module names only; the pairs of the first dry run,
  2026-10-06, are in Risks):
  ```
  canonical modules: 18 (template 262352490535154: q14 5, q92 7, q93 8 options)
  batches since 2026-09-01: 554; module not a canonical option: 6 (5 Success, 1 Failed); rows under them: 43
    a1lRP000006KQZBYA4  <club>  2026-09-24  Success  'Toma de decisiones' -> 'Decision Making'  (Latin America 262383455778067, submission 1 candidate, year 1, session 8; 14 rows)
    a1lRP000006KQXZYA4  <club>  2026-09-17  Failed   'Toma de decisiones' -> 'Decision Making'  (…, year 1, session 7; 0 rows)
    …
  would write: 6 batches, 43 rows   (dry run - nothing written; --apply --vpn-off after Ryan's go)
  ```
  Clean state: `nothing to correct: 0 of N batches since 2026-09-01 carry a module outside the 18
  canonical options`.
- **`--apply --vpn-off`** (refused without `--vpn-off` for any Salesforce call, read or write, as
  `sf_backfill.py:1117-1119`; `--apply` is caught by the live gate): one record per request, as
  `send` does. New `Org.update(sobject, record_id, body)` = `self.call("PATCH",
  f"/services/data/{API}/sobjects/{sobject}/{record_id}", body)` (3 lines in `sf_backfill.py`;
  `FakeOrg` in `test/sf_backfill_test.py:47` gets the same). Per record (the batch first, then
  each row): append a ledger row (`data/module_fix_2026-10/ledger.csv`, owner-only like
  `sf_backfill.Paths`; columns `when_utc, batch_id, record_id, sobject, old, new, outcome` - no
  names) with `outcome=open`, PATCH `{"Module__c": "<English>"}` (HTTP 204 expected), re-read with
  the SOQL above and compare, then append the closing row for the same `record_id`: `written`
  (204, re-read equal), `failed_<status>` (any other status: nothing changed, or unknown on 0) or
  `check` (204 but the re-read differs). After the rows, the rows query once more: their count
  before and after must be equal (nothing fires on an update: Context). `--limit 1` for the first
  batch. Any `failed_*` or `check`: stop, print the id and the HTTP status (never the body), leave
  the rest; the ledger says which records were written.
- **Rollback**: `--undo data/module_fix_2026-10/ledger.csv --apply --vpn-off` reads the ledger as
  `sf_backfill.read_ledger` / `last_rows` do (`:394-406`; the last row per `record_id` wins), writes `old` back by id for
  every record whose last outcome is `written` or `check`, the same way (ledger row, PATCH,
  re-read, closing row), and prints `nothing to undo` for a record still `open` or `failed_*`.
- **When**: the dry run any time (it needs `JOTFORM_API_KEY` and the CLI login, VPN off). The apply
  only after -54's `calcValues` are live on Latin America (its `form_status` line `module values:
  q14 aligned …`) **and** the dry run shows no batch created after that apply with a non-canonical
  module (one would mean the fix did not take: tell -54, write nothing) **and** Ryan's go.
- Tests (`test/fix_module_values_test.py`, imported into `test/python_test.py` like
  `sf_backfill_test` at `:46-48`, so `make py` runs it): a fake org with two batches and their
  rows, a fake Jotform client with fictional club names and real module names; the
  match; the `UNMATCHED` reasons (no candidate, two candidates with the count printed, a
  year/session that differs, a non-integer `Module_Week__c`, a region the map does not know); the
  integer comparison (`Module_Year__c` `1.0` against q94 `"1"` matches); the fetch asks for one
  form with a URL-encoded `filter` and `--all-forms` for four; the fake org sees no `GET` to a
  `/sobjects/<type>/<id>` path and no SOQL naming `Contact_IDs__c` or `Status_Message__c`; the dry
  run writes nothing; `--apply` writes batch then rows, every record with an `open` and a closing
  ledger row, and stops on a 400 (`failed_400`, nothing further) and on an unequal re-read
  (`check`); `--undo` restores the `written` and `check` records only and says `nothing to undo`
  for the rest. `--help` must answer without the key (`scripts/check_py.py:51-53`).

### (c) `.claude/skills/jotform-api/SKILL.md`: the runtime fact
Add under "Conditions", after the rule-walk bullet (`:34-45`):

> - **`clearFieldOnHide`** is a form-level property (`GET /form/{id}/properties`; live value
>   `disable` on all five forms - template, Africa, Asia, Latin America, U.S 262382706852058 -
>   read 2026-10-06) with three runtime values (`jotform.forms.js`, build
>   `fc726a121d4`): `enable` (clear a field the moment a rule hides it and run every calculation -
>   the mode rejected 2026-09-30, loop limit 3), `disable` (the live mode: a rule-hidden field keeps
>   its answer *in the page*) and `dontClear`. At submit, unless the value is `dontClear`, every
>   `input`/`select`/`textarea` inside a `.form-field-hidden` element is emptied before the form is
>   sent; `always-hidden` fields (q98/q100/q102) are not touched and nothing recalculates. So a module
>   dropdown hidden by the Year rule can keep a pick in the page but never in the submission (0 of
>   674 since launch) - the back-fill resolver's "a dropdown hidden again can keep an answer" is true
>   of the page only. `form_status` pins the value (`module shape:` line, plan
>   `docs/plans/2026-10-06-module-selection.md`, built after session -54's rollout); the builder
>   labels of the three values are unverified.

### (d) `docs/BACKLOG.md`
Two rows at the next free numbers (66 and 67: `main` 9d58ce4 holds 65, the question-18-empty resend
residual; renumber if another plan of this workflow takes them; in `docs/BACKLOG.md` the link takes
the `plans/` prefix):
- **66 - Batches with a Spanish `Module__c`** (6 batches, 43 rows as of 2026-10-06, created
  2026-10-01..05 by the live flow after the September back-fill; more until fix 4 of
  `2026-10-02-names-and-modules.md` is live on Latin America); corrected by
  `tools/fix_module_values.py` once that fix is live, with Ryan's go
  ([plan](2026-10-06-module-selection.md)). Until then the dashboard's "Jotform Sessions by Module
  Last Month" (built on `Attendance__c` rows of the last calendar month, `gen.py`
  `Jotform_Sessions_by_Module_Last_Month`) shows a Spanish bar beside the English one for each
  module concerned: in October's view the two September-dated batches (Autodefensa, Toma de
  decisiones), in November's the three October-dated ones - which is why the rows are corrected,
  not only the batches.
- **67 - `form_status` pins the module chain's shape** (single-select, required, form-level
  `clearFieldOnHide=disable`), built after -54's rollout window; a builder change becomes NOT CLEAN,
  not a silent change of what Salesforce receives.

## Files that change
- `glow/sync.py` - `CLEAR_FIELD_ON_HIDE` constant (audit only).
- `tools/form_status.py` - `audit_module_shape`, the `module shape:` line, the `--rendered` read.
- `tools/fix_module_values.py` - new.
- `tools/sf_backfill.py` - `Org.update` (3 lines).
- `test/python_test.py` (shape audit), `test/sf_backfill_test.py` (`FakeOrg.update`),
  `test/fix_module_values_test.py` - new.
- `.claude/skills/jotform-api/SKILL.md` - the `clearFieldOnHide` bullet.
- `.claude/skills/live-systems/SKILL.md` - `tools/fix_module_values.py --apply --vpn-off` (and
  `--undo … --apply --vpn-off`) listed as a Salesforce writer the hook catches, next to
  `sf_backfill.py send --apply`; "written in two ways only" becomes three (four with the metadata
  deploys already listed).
- `README.md`, `docs/ARCHITECTURE.md` - one row each for `tools/fix_module_values.py` in the tool
  tables (as `tools/fix_name_translations.py` has, `main` README.md:39, ARCHITECTURE.md:65).
- `docs/DECISIONS.md` (the row above), `docs/BACKLOG.md` (66, 67), `docs/RUNBOOK.md` (the module
  section: the shape line and the correction tool's commands).
- Not touched: the forms, `build_conditions`, `appsscript/`, the Salesforce mapping, any Salesforce
  metadata, `data/sf_dashboard_2026-10-02/gen.py` (session -51's; the apply changes the data its
  module chart reads, so -51 is told: step 4).

## Order of work (the repo stays green after each step)
1. This plan committed. jotform-api SKILL.md bullet, live-systems SKILL.md writer, DECISIONS
   row, BACKLOG rows (docs only).
2. `tools/fix_module_values.py` + `Org.update` + tests + the README / ARCHITECTURE rows. The unit
   tests with the fake org are the proof the build session runs on its own. The dry run is a read,
   but it runs through the CLI login (`sf org auth show-access-token`, which the live gate does
   not see: BACKLOG 53) and this workflow's sessions reach Salesforce through the read connector
   only - so the first dry run (`--vpn-off`) runs with Ryan present or in his terminal until
   BACKLOG 53 is decided. Expected: every batch listed pairs by the rule in Risks (as of
   2026-10-06: 6 batches, 43 rows, the five pairs, 0 `UNMATCHED`; more batches of the same kind
   until -54's Latin America apply).
3. After -54 closes its window: `audit_module_shape` + tests + RUNBOOK; `form_status.py --rendered`
   on all five forms: every `module shape:` line as above, every form `→ CLEAN`. (Once the
   [clubs-off plan](2026-10-06-clubs-off-jotform.md) has disabled the U.S form, its served-page
   checks read `rendered: skipped (form DISABLED)`; the API-side `module shape:` line still prints.)
4. After -54's Latin America apply is live and the dry run is stable: Ryan's go →
   `--apply --vpn-off --limit 1`, read the output, then `--apply --vpn-off` for the rest; the dry run
   again → `nothing to correct`; SOQL `GROUP BY Module__c` → every value canonical. Then tell
   session -51 the date and time of the apply and the batches and rows changed (ids in the
   ledger): its module chart reads `Attendance__c.Module__c`, and its next read-back expects the
   new split; no `gen.py` change.
5. Plan Result, work log.

## Risks
- **Collision with session -54.** Its rollout writes `calcValues` on q14/q92/q93 and the names
  dictionary on live forms and runs `form_status.py` to verify. Nothing here writes to a form (rule
  3: the sync rewrites every rule anyway, and this plan adds none); `form_status.py` is edited only
  after -54's window closes; the Salesforce apply waits for its Latin America apply. If -54's
  rollout is rolled back (`MODULE_CALC_VALUES` off), the audit still holds - it pins shape, not
  `calcValues`.
- **The Salesforce write.** 49 PATCH calls to production as of 2026-10-06 (one per batch and
  row). Mitigations: dry run first with the exact pairs printed; `--apply` behind the live gate
  and Ryan's go; one record first; each re-read by explicit-field SOQL; row counts compared
  before and after (nothing fires on an update of these objects: the one trigger is `after
  insert` only and no active flow is on them, both read through the read connector - Context;
  the `--limit 1` count comparison is belt-and-braces, and the only check left to Ryan's Tooling
  API query is validation rules, Proof); the ledger with an outcome per record for `--undo`;
  `Status_Message__c` and `Contact_IDs__c` never read. The one Failed (Duplicate) batch is
  corrected too: for the "submitted" reports a duplicate counts as submitted, and its module
  should read right.
- **A wrong pairing.** The match needs q5 + date + q98 + a 3-hour window and the year/session to
  agree as integers, exactly one submission; anything else is `UNMATCHED` and left alone, and
  several candidates (a same-day re-send) stay `UNMATCHED` with their count printed, for a
  correction by hand with the id. Club accounts are never renamed (DECISIONS 2026-09-30), so
  `Account_Name__c` equals q5. **The stop is the pairing rule, not the count**: every batch's new
  value must be the stored answer of the module dropdown its Year answer names and its Spanish
  q98 must equal its `Module__c`; a pairing that breaks the rule is a stop. Batches of the same
  kind created *before* -54's Latin America apply are expected until then and simply join the
  list; one created *after* it is the other stop ((b), When). Pairs from the values read
  2026-10-06: Autodefensa → Self Advocacy (year 1), Comunidad 201 → Community 201 (year 2), El
  poder de las chicas 101 → Power of Girls 101 (year 1), Optativa - Compromiso académico →
  Elective - Academic Engagement (year 3), Toma de decisiones → Decision Making (year 1, two
  batches).
- **The audit's premise is Jotform's runtime, not a contract.** `form_status --rendered` prints the
  runtime build; a new build means re-reading the submit handler's `clearFieldOnHide` branch
  (BACKLOG 64's pattern). The hidden round trip (year 1 → module A, year 2 → module B, back to year
  1 without re-picking: q98 could hold B while q92 is cleared) is a reading of the runtime, 0
  observed, not reproduced in a browser (unverified); it is not closed by this plan and would show
  in the daily q98-vs-dropdown comparison.
- **Privacy.** The tool fetches only the submissions of one form inside a 6-hour window per batch
  (not the four forms whole, unless `--all-forms`); what it fetches (girls' names, photo links)
  stays in memory; it prints club names, dates, ids, statuses, candidate counts and module names;
  the ledger holds ids, module names and outcomes only; every Salesforce read names its fields.

## Proof
```
.venv/bin/python3 test/python_test.py                       → OK (the count rises by the shape and correction tests)
python3 tools/form_status.py --roster data/roster_<date>.csv --rendered
   module shape: year q94 single-select required; modules q14/q92/q93 single-select required; sessions q15/q95/q96/q97 single-select required; clearFieldOnHide disable
   … → CLEAN                                                 (all five forms)
python3 tools/fix_module_values.py --vpn-off                 (dry run, read-only; with Ryan: step 2)
   canonical modules: 18 (template 262352490535154: q14 5, q92 7, q93 8 options)
   batches since 2026-09-01: N; module not a canonical option: B (… Success, 1 Failed); rows under them: M
   … B lines, each pairing by the rule in Risks, 0 UNMATCHED        (N 554, B 6, M 43 as of 2026-10-06)
   would write: B batches, M rows   (dry run - nothing written; --apply --vpn-off after Ryan's go)
python3 tools/fix_module_values.py --vpn-off --apply --limit 1      (Ryan's go)
   a1lRP000006KQZBYA4  <club>  2026-09-24  Success  'Toma de decisiones' -> 'Decision Making': batch written and read back equal; 14 rows written and read back equal; rows 14 before, 14 after
python3 tools/fix_module_values.py --vpn-off --apply                (the rest)
python3 tools/fix_module_values.py --vpn-off
   nothing to correct: 0 of N batches since 2026-09-01 carry a module outside the 18 canonical options
SOQL (read connector): SELECT Module__c, COUNT(Id) FROM Attendance_Batch__c WHERE CreatedDate >= 2026-09-01T00:00:00Z GROUP BY Module__c
   → every value one of the 18 options (17 of them as of 2026-10-06); the same over Attendance__c
   → the dashboard's "Jotform Sessions by Module Last Month" (Attendance__c rows, last calendar month) has no Spanish bar: two fewer in October's view, three fewer in November's
make check                                                  → CHECK PASSED (pasted when done)
```
Salesforce-side check that nothing constrains or reacts to `Module__c` (before step 4, read-only):
the field's type is text(255) on both objects (schema read 2026-10-06); the `ApexTrigger` and
`FlowDefinitionView` queries in Context, re-run on the day, still give one `after insert` trigger
and no flow on either object; validation rules are Tooling API metadata the read connector cannot
query (`ValidationRule` → `INVALID_TYPE`, tried 2026-10-06), so Ryan runs, VPN off,
`sf data query --use-tooling-api --target-org glow -q "SELECT ValidationName, Active,
EntityDefinition.QualifiedApiName FROM ValidationRule WHERE EntityDefinition.QualifiedApiName IN
('Attendance_Batch__c','Attendance__c')"` and expects no row mentioning `Module__c` (the command's
exact shape is unverified; the five accepted Spanish batches already say no active rule rejects a
module value on insert - a rule that fires on update only would show as a 400 on the `--limit 1`
batch, with nothing written).

## Build notes (2026-10-06, part (a) built on the branch, offline, after -54's confirmation)

- `audit_module_shape` flags a missing module dropdown as the plan says, so a deleted one gives
  two lines (this audit's and `audit_module_values`'): both true, the form is badly broken then.
  The session dropdowns' messages name question 100 ("two sessions; question 100 would run them
  together", "a blank session reaches Salesforce"), the year's a blank year and the chain; a
  dropdown of another type (`control_radio`, say) is flagged too.
- The printed line is `module shape: year q94 single-select required; modules q14/q92/q93
  single-select required; sessions q15/q95/q96/q97 single-select required; clearFieldOnHide
  disable`; an odd dropdown is named in its group (`modules q14/q92/q93: q92 multi-select`), an
  unset value prints `clearFieldOnHide unset`.
- The `--rendered` read checks a `multiple` attribute on the module selects only (as the plan
  says) and the page's `JotForm.clearFieldOnHide`; a page without that line is "cannot be
  vouched for", like the other page reads. The report prints a `rendered shape:` line.
- The test fixtures (`SameNameFlow.form`, `served_modules_and_store`, the fake `/properties`
  answers) gained the live shape - `required: Yes` on the year, module and session dropdowns,
  `JotForm.clearFieldOnHide="disable"` on the served page, `clearFieldOnHide: disable` in the
  properties - so the forms the other tests build are clean under the new audit.
- Read-only proof, 2026-10-06 afternoon: `form_status.py --roster <fresh export> --rendered` on
  the five live forms, every `module shape:` line as above, every `rendered shape: clearFieldOnHide
  disable, module selects served multiple: none`, every form CLEAN. **The pages were served on
  runtime builds not read before** - template `bc6c80d556a`, Africa / Asia / Latin America
  `8705c008453`, U.S `18bdf84aedc` (the audit's premise is `fc726a121d4`; BACKLOG 64 and 67):
  the submit handler's `clearFieldOnHide` branch and the translation runtime of those builds are
  to be re-read, not done in this build.
