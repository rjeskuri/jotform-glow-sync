---
title: The names list sent to Salesforce is never empty and never another club's
author: Claude (read-only investigation of Jotform's runtime and of all September submissions, a design and two adversarial reviews, 2026-09-30)
status: done             # Ryan 2026-09-30: "Go on all 4 fixes"; then "Guard first, then back-fill"; rolled out on all five forms 2026-10-01/02 with his go (Result)
done: 2026-10-02
backlog: 35, 56, 57
created: 2026-09-30
intent: docs/intent/2026-09-01-club-picker.md (the attendance form sends the right girls for the right club)
---

# Plan: question 18 (Contact_IDs) equals the ticked girls of the one visible roster, and at least one girl is ticked

## Context
The Jotform → Salesforce integration sends question 18 (`contact_ids`, a hidden field filled by one
calculation over every roster) as the list of girls who attended. Re-measured on all 484 September
submissions (2026-09-30, counts only):
- **No girl ticked: 64 submissions (13%).** Sent live, each is stored in Salesforce as an empty
  *Success* batch that blocks the real batch for that club and day (one arrived on 2026-09-30,
  14:19 UTC, after the reconnect).
- **Girls ticked but question 18 empty: 17 submissions (207 names never sent).**
- **Another club's girls in question 18: 2 submissions (24 extra names)**, one of them after the club
  guard went live — it is the path the guard's warning sends a mentor down (two clubs picked, girls
  ticked in both, one club removed).
- Root cause of the last two, reproduced in headless Chrome: **rule order.** On a change of the Club
  picker Jotform runs the question-18 calculation *before* it shows or hides the rosters, and never
  again. A restored page (Back) shows ticks with an empty question 18.
Ryan's order (2026-09-30): this guard first, then the September back-fill; the names-dictionary repair
and the module values follow the back-fill (their own plan).

## What changes
**1. At least one girl (lead design: required rosters).** Every roster question gets Jotform's own
`required` flag, written by the sync (on create, and as an update where it is missing). Jotform
validates at submit time, on the checkboxes themselves, only the roster that is visible (a question
hidden by a rule is not validated), and shows its own "required" message in the form's language. It
does not depend on question 18, so it also holds on a restored page. *To be proven in a browser
before it is relied on* (a local copy of the live page in headless Chrome: no club picked; a club
picked and nothing ticked; one girl ticked; two clubs picked; Back). **Fallback** if that proof
fails: a generated field rule `{picker filled, question 18 empty} → hide and disable Submit, show a
hint`, built like the club guard.

**2. Question 18 is recalculated after the rosters change (generated rules).** In
`build_conditions` the Contact_IDs rule becomes the first rule (Jotform walks a field's rules last to
first, so it then runs after every show/hide), its id minted first, and the Club picker is added to
its operands (never to its equation) so the picker's own change event re-runs it as well. Order is
the fix; the operand is a supplement (a restored page fires no bubbling event). One conditions write
per form, no question touched by this part. Constants in `glow/sync.py`
(`CONTACT_IDS_FIRST`, `CONTACT_IDS_PICKER_OPERAND`).

**3. Audits and the runner.** `tools/form_status.py`: NOT CLEAN when the Contact_IDs rule sits after
a roster rule, lacks the picker operand, holds anything but one `{qid}` per roster, when a roster
rule tests a field that is not in the Contact_IDs rule, or when a roster is not required — each
expectation derived from the constants, so a fallback does not leave every form dirty.
`sync_attendance_form.py` warns with a fixed fragment when the live rules are in the old order;
`tools/auto_sync.py` raises ATTENTION for it and **refuses to apply that region** (so a forgotten
`AUTO_SYNC_APPLY` cannot roll the change out unattended). A bulk "make every roster required" is
likewise by hand: the runner sets it only on rosters it creates or already updates.

**Not in this plan:** the names-dictionary repair (55 roster options the forms' own translation
dictionary alters) and `calcValues` on the module dropdowns — after the back-fill. The language
switcher with two clubs picked (it un-picks one silently and lifts the club guard) — recorded as a
residual, needs its own design (a single-select picker is the structural answer).

## Files
`sync_attendance_form.py` (`build_conditions` section C; the roster create/update payloads; the
warning), `glow/sync.py` (constants), `tools/form_status.py`, `tools/auto_sync.py`,
`test/python_test.py` (rule order and operands, required rosters, audits in all constant
combinations, the runner's refusal), docs (RUNBOOK "One club per submission" gains the two checks and
the browser scenarios; ARCHITECTURE; DECISIONS; BACKLOG 35 and a new item; the jotform-api skill:
the rule walk, the checkbox reader, required + hidden).

## Rollout (each step Ryan's go; `AUTO_SYNC_APPLY=0`, verified, for the window)
1. Build on a branch, three adversarial reviews (runtime in a browser; live safety; tests/docs), fixes.
2. Template: backup → dry run (exactly: `REPLACE conditions` with `1 new, 1 dropped`, and the
   roster `required` updates) → `--apply` → second dry run `nothing to do` → `form_status --rendered`
   CLEAN → browser scenarios (Ryan, console one-liner that prints counts only): one club + three
   ticks; two clubs, tick both, remove one; pick, tick, clear, re-pick; rapid switching; no tick →
   Submit refused with the required message; Español.
3. Merge and push (the runner stays paused). U.S, Latin America, Asia, Africa, smallest first, each:
   backup, dry run, apply, second dry run, `form_status --rendered`, scenarios 2 and 5.
4. `AUTO_SYNC_APPLY=1`, one manual runner apply read through. Tell the Salesforce session: the
   back-fill may go.
5. For a week, daily: question 18 against the stored ticks on new submissions (the back-fill
   resolver's `q18_differs` / `q18_empty` flags; counts and ids only).

## Rollback
Generated, not a snapshot: set the constants to `False` (and the required flag off) and apply each
form by hand; `restore_conditions.py` from the pre-apply backup is the second path. Neither touches
the picker, the guard, question 5 or the integration.

## Residual risk
No recalculation at submit exists in Jotform: after this change question 18 is right for every
sequence of club picks and ticks and for a restored page in Chrome; iOS Safari and Firefox restores
are untested, and the language switcher case above stays open. The daily comparison is the alarm.
The rule walk order is Jotform's internal behaviour, not a contract (`form_status --rendered` prints
the runtime build).

## Build notes
Built 2026-10-01 on branch `wf8/contact-ids` (a worktree), parts 2 and 3 of "What changes" and
part 1 in its lead design. Nothing was written to any form, the sheet or Salesforce.

**The browser proof came first and passed** (2026-10-01, another part of the same workflow: local
copies of the Asia, U.S and Africa pages in headless Chrome, network to Jotform blocked, every
submit intercepted). Required rosters: one club and no tick is refused on all three forms with
Jotform's own message, 0 hidden rosters flagged, the picker not flagged, Submit still visible; one
tick goes through with question 18 equal to the ticks; refused on club A, switched to B and one
tick, it goes through (the stale error on hidden A does not block). New order: removing one of two
clubs, and clear-then-re-pick, both leave question 18 equal to the visible ticks (the old order:
other club's girls, and an empty question 18). Two clubs and Enter: no submit in any shape. Jotform's
own `requireField` on the U.S page sets exactly `validate[required]` on all 155 boxes. So the
**fallback rule (hide Submit while question 18 is empty) is not built.**

**Deviations and decisions made in the build**
- **The order and the operand apply on a form with the Club picker only**; a form without it keeps
  its rules byte for byte, in every combination of the constants (a test). Every live form has the
  picker; the typed club name is the legacy path. `form_status`'s order, operand and coverage
  checks are likewise picker-only.
- **The required flag is on every roster of every form** (a question property, not a rule). Off
  (`ROSTERS_REQUIRED = False`), the sync writes `"No"` where a roster has `"Yes"`: the rollback is
  generated both ways, and `form_status` then flags a required roster.
- **Labels.** The flag alone: `REQUIRED roster '<club>' (q<qid>: Yes)` (new `REQUIRED_RX`, plan key
  `requires`, summary-JSON `requires`). With an options update, one write and the existing label
  extended: `UPDATE roster '<club>' (q<qid>, N girls; required: Yes)` (`UPDATE_RX` takes the
  optional suffix; the runner counts it as an update). `CREATE roster` is unchanged; its payload
  gains `question[required]=Yes`. The flag-alone writes come **last** in a run, after the rules and
  the Partner-box hide: on the template they are 359 writes, and a run stopping among them must
  not leave a new roster without its rule.
- **The runner refuses more than the plan said**: any plan with the `CONTACT_IDS_STALE` warning, roster
  changes included (a `check_bands` reason, so a rules-only plan is `attention`, never `in-sync`),
  and any `REQUIRED roster` line at all, one or 220 (not a band size). After a form's rollout the
  runner still creates required rosters and applies `UPDATE … ; required: Yes`.
- **The constants are read through the module** (`glow_sync.CONTACT_IDS_FIRST`, …) by the sync,
  `form_status`, `restore_conditions` and the shared helpers `contact_ids_layout` /
  `contact_ids_stale` / `roster_required` in `glow/sync.py`: one patch, one rollback switch.
- **Coverage audit, per critique 1**: with the order on, a field a roster rule tests must be a
  *term* of question 18's rule (that puts the sum in that field's rule walk); with only the operand
  on, an operand. A form whose roster rules test the Partner box (before the same-name switch; none
  live since 2026-09-30) is therefore NOT CLEAN: flagged, not generated (the design's choice). The
  unswitched-form tests were updated to expect exactly that one line.
- With the order off, question 18 at rule 0 is not flagged (never harmful); with the operand off, the
  picker among its operands is ("includes 1 non-roster question").
- Added on the way: two rules calculating question 18 is a problem; the equation check also catches a
  literal between the fields and a field twice; `aggregate_rosters` counts rosters only (critique 2);
  `restore_conditions.py` prints a note when its snapshot calculates question 18 the old way;
  `--rendered` reads every form's page (not only picker forms) and prints the runtime build.
- **No template test submission** (critique 2): the console checks prove the same, and a delivered one
  is a real batch for a real club. The RUNBOOK's rollout drops it.
- The live-systems skill's "Never" list gains "an apply from a checkout without this code once a form
  is rolled out", and its rollback list the generated path.

**Proof, read-only (2026-10-01, from the branch).** A fresh Roster export (7,041 rows) in the
session's scratch folder, deleted afterwards. The sync's dry run on each form:

| Form | Calls | Rules | Required |
|---|---|---|---|
| U.S | 12 | `REPLACE conditions (42 rules)`: 41 kept, 1 new, 1 dropped | 11 `REQUIRED roster` |
| Latin America | 39 | 69: 68 kept, 1 new, 1 dropped | 38 |
| Asia | 96 | 126: 125 kept, 1 new, 1 dropped | 95 |
| Africa | 221 | 251: 250 kept, 1 new, 1 dropped | 220 |
| template | 366 | 393 (+~2 once its new rosters exist): 390 kept, 3 new, 3 dropped | 359, plus 3 `UPDATE roster … ; required: Yes` |

Each regional form also warned once with `question 18 (Contact_IDs) is not recalculated after the
rosters change` (rule 40 of 42, 67 of 69, 124 of 126, 249 of 251; the picker not an operand). The
template also plans its backlog: 2 `CREATE roster`, 3 roster updates, `UPDATE club picker (364 clubs:
calcValues, options)`; its 3 new rules are the sum and the guard's two (the picker gains two clubs).
`form_status --rendered` read all five NOT CLEAN, with the same six problems on each: not required,
the order, the operand, and their three rendered counterparts. Every picker's `data-calcvalue` was
aligned, and 0 roster boxes carried `validate[required]` (6,857 / 4,264 / 1,636 / 869 / 155). Runtime
builds served: template `cca53a3a639`, Africa `962dcbe2fa6`, Asia, Latin America and U.S `9e75d6f1d83`;
`jotform.forms.js` is byte-identical (md5 `841dc566a7`) in those three and in `772a1982daf`.
`auto_sync.py` as a dry run on the export (no SyncLog) put all four regions at `attention`, exit 2,
"not applied", with both reasons. `make check`: CHECK PASSED, 429 Python tests (21 new).

**After the reviews (2026-10-01).** Each finding reproduced, read only (the translation stores
through the API, a local copy of the U.S page in headless Chrome with the network to Jotform
blocked; counts only), and fixed in the docs and tests; nothing in the code's behaviour changed.
- *The required message is English on four forms.* "In the form's language" (What changes, 1) and
  the Español check of rollout step 2 hold on U.S only: the translation stores of the template,
  Africa, Asia and Latin America hold "This field is required." in 11 languages but not in `base`,
  and the runtime translates through `base` only (U.S has it; Odia has no entry anywhere). The
  RUNBOOK's browser step 7 expects English on those four: not a failure. The `base` entry is
  BACKLOG 57, independent of this rollout (`add_translations.py` posts only a question's visible
  text, so it needs a small change first).
- *Merge right after the template.* Rollout step 3 was missing from the RUNBOOK, whose only safety
  net assumed it: older code on `main` puts a rolled-out form back in the old order with its next
  roster change and reads it CLEAN, and its dry run reads `in-sync`. The RUNBOOK now numbers the
  merge between the template and the first regional form and proves it with one runner dry run by
  hand (every region `attention` with the question-18 reason). The live-systems skill says so.
- *Back in a default Chrome proved nothing.* The back-forward cache restores the page from memory,
  where the old rules pass too. Browser step 6 now adds an `unload` listener first and reads
  Jotform's own `fromBFCache` (`bf` in the console check). On the U.S copy, Back then gave
  `q18: 0` with three ticks on the old rules and `q18: 3` on the new ones.
- *Two clubs, then the language switcher.* With required rosters, ticks in the kept club's roster
  only are refused with the message on the other club's roster (and the reverse); ticks in both
  still go through under the kept club, the one higher in the list. The residual, BACKLOG 56 and
  a support line say so.
- *The rollback and `main`.* The runner runs `main`'s constants: a constants-off commit is merged
  only once every form is rolled back, never while one is still rolled out.
- *`--rendered` with the constants off.* A test now serves a page built under each of the eight
  combinations and reads it clean under the same combination, plus a page without question 18's
  calculation (three mutants of `rendered_problems` that survived the suite fail it).

**Proof again after the review fixes, read-only (2026-10-01, from the branch).** A fresh Roster
export (7,045 rows) in the session's scratch folder, deleted afterwards. The sync's dry run:

| Form | Calls | Rules | Required |
|---|---|---|---|
| U.S | 12 | `REPLACE conditions (42 rules)`: 41 kept, 1 new, 1 dropped | 11 `REQUIRED roster` |
| Latin America | 39 | 69: 68 kept, 1 new, 1 dropped | 38 |
| Asia | 96 | 126: 125 kept, 1 new, 1 dropped | 95 |
| Africa | 221 | 251: 250 kept, 1 new, 1 dropped | 220 |
| template | 366 | 393 (+~2 once its new rosters exist): 390 kept, 3 new, 3 dropped | 358, plus 4 `UPDATE roster … ; required: Yes` |

The template's backlog moved with the Roster (4 roster updates now, so one roster fewer on its
own); the regional forms are as before, each with the one question-18 warning. `form_status
--rendered` read all five NOT CLEAN with the same six problems each, every picker's
`data-calcvalue` aligned and 0 roster boxes with `validate[required]`. Africa is now served on build
`2dd4239c231`: `jotform.forms.js` is the same file (md5 `841dc566a7`), and its
`formTranslation.v2.js` (the template's, which skips a missing `base` entry instead of filing it
under "undefined") also translates only through `base`, so BACKLOG 57 holds there. `auto_sync.py`
as a dry run on the export put all four regions at `attention` with the question-18 reason, the
one the RUNBOOK's merge check reads. `make check`: CHECK PASSED, 434 Python tests.

## Result (2026-10-01/02, with Ryan's go: "You have my go push things")
- `AUTO_SYNC_APPLY=0` (16:32 UTC, no run in progress). The branch had `main` merged in first
  (`1fb8cfb`, `make check` 434 tests with real data), so the template was applied from exactly the
  code that then landed on `main`.
- **Template** (backup `properties-2026-10-02T0132.json`), applied 16:33–16:37 UTC on 10-01: 364
  roster writes (2 created and 10 updated from its backlog, 352 made required), the Club picker (364
  clubs), 395 rules. Second dry run `nothing to do`; `form_status --rendered` CLEAN: question 18 rule
  1 of 395 with the picker an operand, 364 of 364 rosters required, 6,924 of 6,924 boxes carry
  `validate[required]`. **Browser, on the live page** (headless Chrome, runtime build
  `fc726a121d4`, every submit request intercepted and aborted): all ten scenarios passed — no club and
  no tick refused; one tick sends q18 = the tick; two clubs blocked by the guard (Enter included);
  two clubs then one removed, pick-clear-re-pick, 20 rapid changes, and Back each give q18 = the
  visible ticks; Español refused (the message stays English, BACKLOG 57); a same-name entry sends
  its name exactly.
- **Merge and push**: `main` = `1fb8cfb` on origin, check green; a manual runner dry run (GitHub run
  36952279243) put all four regions at `attention` with the question-18 reason — the runner was on
  the new code before any regional form was touched.
- **Regional forms** from `main`, fresh Roster export `roster_2026-10-02T0144Z`: U.S 01:44 UTC (11
  rosters required, 42 rules), Latin America 02:01 (38, 69), Asia 02:02 (95, 126), Africa 02:04 (220,
  251; with it 10 roster updates that arrived while the runner was paused). Each: backup, dry run
  (only the rule move and the required flags), `--apply`, second dry run `nothing to do`,
  `form_status --rendered` CLEAN with every box required and question 18 first (runtime build
  `62a8b57dd95`).
- `auto_sync.py` dry run: every region in-sync, exit 0. `AUTO_SYNC_APPLY=1` (02:05 UTC); GitHub run
  36953976708 on `1fb8cfb`: every region in-sync.
- **Browser, on the four live regional pages** (headless Chrome, runtime build `62a8b57dd95`,
  every submit request intercepted and aborted — a deliberate one-tick submit on U.S proved the
  interception first): on U.S, Latin America, Asia and Africa (and on Africa with the entry
  'Ruby - Binti Network') no tick is refused with only the visible roster flagged; one tick sends
  q18 = the tick and q5 = the picker entry exactly; two clubs are blocked by the guard and, with
  one removed, q18 = the remaining visible ticks; pick-clear-re-pick and Back give q18 = the
  visible ticks; Back with no tick is refused. All passed. Served rules: question 18 at index 0 on
  every form (last in the picker's walk), the picker among its operands.
- Open: BACKLOG 56 (language switcher with two clubs) and 57 (the required message's translation).

## From the RUNBOOK (moved 2026-10-09)

What `docs/RUNBOOK.md` carried for this plan until its 2026-10-09 restructure (the procedure as run, or its history), word for word (links re-pointed to this folder); the RUNBOOK keeps a stub that links here.

### "The names list sent to Salesforce": September's submissions

Of September's 484 submissions, 64 had no girl ticked
(stored as an empty *Success* batch that blocks the club's real batch for
that day - until 2026-10-07; since then Failed "No participants submitted",
which blocks nothing), 17 had girls ticked but an empty question 18 (207
names never sent), and 2 carried another club's girls.

### "The names list sent to Salesforce": the browser proof

Proven in headless Chrome on local copies of the Asia, U.S and Africa pages
(2026-10-01; nothing submitted, every submit request intercepted). With
required rosters, one club picked and no girl ticked was refused on all three
forms, and no hidden roster was ever flagged. One tick went through. Two
clubs picked was still the club guard's case. With the new order, removing
one of two clubs, or clearing and re-picking a club, left question 18 equal to
the visible ticks; with the old order it did not. Jotform's runtime file
(`jotform.forms.js`, md5 `841dc566a7`) is byte-identical in every build the
five forms were served on 2026-10-01 (`9e75d6f1d83` U.S, Latin America, Asia;
`962dcbe2fa6`, later `2dd4239c231`, Africa; `cca53a3a639` template). A required checkbox has never
been rendered by Jotform's server on these forms: the browser proof imitated
the markup. The template's `--rendered` check after its write is a **hard
stop**.

### "The names list sent to Salesforce": the rollout as run

Read on 2026-10-01 (dry runs from the branch, nothing written):

| Form | Plan |
|---|---|
| U.S | `REPLACE conditions (42 rules)`, 41 kept, 1 new, 1 dropped; 11 `REQUIRED roster` |
| Latin America | 69 rules, 68 kept, 1 new, 1 dropped; 38 `REQUIRED roster` |
| Asia | 126 rules, 125 kept, 1 new, 1 dropped; 95 `REQUIRED roster` |
| Africa | 251 rules, 250 kept, 1 new, 1 dropped; 220 `REQUIRED roster` |
| template | 393 rules (+2 once its new rosters exist), 390 kept, 3 new, 3 dropped; 359 `REQUIRED roster`; its backlog: 2 `CREATE roster`, 3 `UPDATE roster … ; required: Yes`, `UPDATE club picker` |

The guard's two rules are among the template's new rules because its picker
gains two clubs. All five then read NOT CLEAN: three API problems and three
rendered ones each.

**Rollout**, each step Ryan's go. Set `AUTO_SYNC_APPLY=0` for the whole
window and confirm it, with no run in progress. Close every builder tab on
these forms. Order matters: the runner syncs from `main`, and older code puts
the Contact_IDs sum back after the roster rules, creates rosters without the
flag and reports that CLEAN, with no warning. Its dry run reads `in-sync` on
a rolled-out form, so an `in-sync` cannot tell the old code from the new.

1. The template goes first: the commands below with its id and no
   `--region`, then the browser steps after them. Its plan carries its
   roster backlog: read it before applying. Until the merge (step 2), nobody
   applies the template from another checkout, `rename_club.py`'s template
   step included.
2. Once the template passed its hard stop and the browser steps, **merge and
   push**, with `AUTO_SYNC_APPLY` still `0`. Then prove the runner runs this
   code: one run by hand (Actions, "Run workflow", apply unticked: a dry
   run). Every region must read `attention` with the reason "the form's rules
   calculate question 18 … the old way". A region without that reason means
   the runner still runs older code: stop. From here on the runner refuses
   every region not rolled out yet, even if the switch were on; that is the
   safety net, not the plan.
3. Then U.S, Latin America, Asia and Africa, smallest first, each with its
   `--region`, the same commands (U.S below), then browser steps 2 and 5:

```bash
python3 backup_forms.py --form 262382706852058                                                  # note the stamp: the second rollback path
python3 sync_attendance_form.py data/roster_<date>.csv --roster --region U.S --form 262382706852058           # dry run: exactly the table's lines
python3 sync_attendance_form.py data/roster_<date>.csv --roster --region U.S --form 262382706852058 --apply   # one PUT + one POST per roster
python3 sync_attendance_form.py data/roster_<date>.csv --roster --region U.S --form 262382706852058           # "nothing to do", no warning (else Jotform altered what was written: stop)
python3 tools/form_status.py --form 262382706852058 --roster data/roster_<date>.csv              # CLEAN; "question 18: rule 1 of …, … operand: yes"
python3 tools/form_status.py --form 262382706852058 --roster data/roster_<date>.csv --rendered   # HARD STOP: rule 1, operands list the picker: yes, N of N rosters with validate[required]
```

The apply makes about one write per roster: 11 on U.S, 220 on Africa, 359
on the template. The `REQUIRED roster` writes come last, after the rules, so
a run that stops among them leaves no new roster without its rule. A 504 can
hide a completed write: re-run the dry run, which lists only what is still
missing, before anything else. If the second dry run
still plans `REPLACE conditions`, Jotform did not keep what was sent. That
means the order, or an operand it dropped (`--rendered` says which). The
order is the fix: if Jotform reorders the rules, stop and roll back. If it
only drops the operand, set `CONTACT_IDS_PICKER_OPERAND = False` and apply
again. On the template only, open the builder's Conditions page and close it
without saving. The dry run must still say `nothing to do`.

Then, in a real browser on the served page, without submitting. After each
step paste this in the console; it prints counts, never a name (`bf`: the
page came back from the browser's memory, below):

```js
(() => { const q = document.getElementById('input_18').value, t = [...document.querySelectorAll('li[data-type="control_checkbox"]:not(.form-field-hidden) input[type="checkbox"]:checked')].map(b => b.value); return { shown: document.querySelectorAll('li[data-type="control_checkbox"]:not(.form-field-hidden)').length, ticked: t.length, q18: q ? q.split(', ').length : 0, equal: q === t.join(', '), flagged: document.querySelectorAll('li[data-type="control_checkbox"].form-line-error').length, bf: !!(window.JotForm && JotForm.fromBFCache) }; })()
```

1. Pick a club, tick three girls: `ticked: 3, q18: 3, equal: true`.
2. Pick a second club (the guard's warning), tick girls in both, remove the
   first: `equal: true`, Submit back.
3. Pick a club, tick, clear the picker, pick the same club again, touch no box:
   `ticked` and `q18` equal and not 0.
4. Switch the club back and forth quickly four times: `equal: true`, Submit
   visible and enabled.
5. Pick a club, tick nothing, press Submit: refused, `flagged: 1`, the roster
   shows Jotform's required message. Tick one girl: the message goes.
6. Pick a club, tick three girls, then paste
   `addEventListener('unload', () => {})` in the console. Go to another page
   and come back with the browser's Back: `ticked: 3, q18: 3, equal: true`,
   `bf: false`. Without that line Chrome restores the page from memory (its
   back-forward cache), where the old rules pass too: that is `bf: true`,
   and the step proved nothing. The line makes Chrome load the page again,
   the path behind the 17 empty question-18 submissions (read 2026-10-01 on
   a local copy of the U.S page: the old rules gave `q18: 0`, the new ones
   `q18: 3`). If `bf` still reads `true`, repeat it in a Chrome started on
   its own: `open -na "Google Chrome" --args --user-data-dir="$(mktemp -d)"
   --disable-features=BackForwardCache`.
7. Español, step 5 again: refused the same way. The message is in Spanish
   on U.S only. On the template, Africa, Asia and Latin America it stays
   English (their translation stores lack its `base` entry, BACKLOG 57):
   not a failure. Switch back to English.

`equal: false` with `q18` equal to `ticked` is the names-dictionary defect
(55 roster names whose spelling the forms' own translation dictionary alters:
"The names dictionary and the module values" below), not this one. Until a
form's dictionary is fixed, pick a club it does not affect for these checks. Each form's page can be served on its own
runtime build, so steps 2 and 5 are repeated on every regional form. No test
submission: a delivered one creates a real batch for a real club, and the
console checks prove the same thing.

When all five forms are CLEAN with `--rendered`, run one `auto_sync.py` dry
run from `main` (merged in step 2): every region `in-sync`, no ATTENTION.
Then `AUTO_SYNC_APPLY=1`. Stopped
half-way, the runner stays at `0`. Every region not rolled out reads
`attention` anyway, and its roster changes wait for a hand apply, which
also rolls it out. A mentor with the form already open keeps the old page
until she reloads.

**Afterwards**, daily for a week: question 18 against the stored ticks on new
submissions (the back-fill resolver's `q18_differs` / `q18_empty` flags; counts
and ids only), and the count of submissions with no tick (0 expected).
