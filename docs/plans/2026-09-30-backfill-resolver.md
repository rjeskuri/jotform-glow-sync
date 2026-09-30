---
title: September back-fill - the resolver (every attendance submission as clean rows)
author: Claude (workflow builder, wf7/backfill-resolve, 2026-09-30)
status: accepted         # Ryan asked for the back-fill directly on 2026-09-30; this is its read-only first step
created: 2026-09-30
intent: none - Ryan's request of 2026-09-30 (back-fill September's attendance into Salesforce); the plan for the whole back-fill is the loader session's `2026-09-30-september-backfill.md`
---

# Plan: the back-fill resolver

`tools/backfill_resolve.py` is the read-only half of the September back-fill. It reads every
active submission of the four regional attendance forms and writes one row per
(submission, ticked roster) to `data/backfill_2026-09/resolved.json`. The Salesforce loader
(another session's tool) reads that file; the file's shape is the contract between the two and
was fixed before either was written.

## Why the ticked roster and not question 5
Question 5 is what Salesforce reads, and in September it was unreliable: typed by hand until the
Club picker (about 09-01 to 09-12), the names of 2-4 picked clubs run together, a bare name two
clubs shared, or altered by a browser's page translation. The roster a mentor ticked girls in is
the one thing that says whose attendance it was, so the club of a row is that roster. Question 5
is only compared (`q5_differs`).

## Files that change
- `tools/backfill_resolve.py` - new. GET only (`glow.jotform.Client.get`), no `--apply`.
- `test/backfill_resolve_test.py` - new; one import line in `test/python_test.py`.
- `README.md`, `docs/ARCHITECTURE.md` - one line each in the tool tables.
- `docs/RUNBOOK.md` - "September back-fill: the resolver".
- this file.

## Design
1. **The forms** come from `glow/forms.py REGIONALS`; no form id is written in the tool (a test
   reads the source for them).
2. **Fetch**: `GET /form/{id}/submissions` with `limit`/`offset`, 100 at a time, until a short
   page. Jotform lists the newest first, so a submission arriving meanwhile repeats one on the
   next page (dropped by id) and hides none. Afterwards the form's own `count` is read: fewer
   fetched than it reports is an error ("run it again"). The raw answer, any status, goes to
   `raw/<region>.json` beside the result, overwritten, with `fetched_at_utc`.
3. **What each roster is** - club, partner, the Club Name it sends today - is the sync's own
   word: the tool runs `sync_attendance_form.py <roster> --roster --region <r> --form <id>
   --summary-json <tmp>` as a subprocess, never with `--apply`, and reads `sf_names`. Nothing is
   matched a second time. `sf_names` is what each roster sends *after* the plan; where the plan
   would change it (`sf_name_changes`) the row takes the change's `old`, which is what it sends
   today. The sync's output is captured and not echoed (it is not redacted). A form with no
   submission at all gets no dry run.
4. **Ticked rosters**: a roster is a `control_checkbox` question of the form as it is today. An
   answer to a question that is no longer on the form counts when the answer itself says it was
   a checkbox and carries its text (row: `retired_club`, `no_account_name`, club = that text,
   partner and code null); an answered question that is not on the form and says nothing about
   itself is refused.
5. **Club code**: the prefix of the girl ids (`CLUBCODE-LASTCODE-NNN`, `appsscript/Ids.gs`) of
   the Roster rows, any status, whose partner and club are the ones the sync names (compared by
   `glow.text.key`). No row, or no partner named by the sync: null. Two different prefixes for one
   club: the tool stops.
6. **The ledger**: per form, fetched = not active + pre-launch + in range, and in range = with
   rows + no ticks, by submission id, each once. It is checked per form and over the forms; a
   miss exits before the result is written.
7. **Privacy**: the result and the raw copies hold girls' names and mentors' contact details.
   Inside the checkout the tool writes them only under `data/` (git-ignored) and refuses any
   other place in the repository; outside the checkout is the operator's choice. What is
   printed is counts, dates, flags, form ids and submission ids. A refusal names the submission
   id and the question id, never a value.

## Refusals (exit non-zero, no result written)
- a checkbox answer that is not a list of strings; question 5 or 18 that is not text; a photo
  or Club-picker answer of another shape; `created_at` not `yyyy-mm-dd hh:mm:ss`; the answers
  not a table by question id;
- an answered question that is not on the form and carries no type; a ticked roster not on the
  form whose answer carries no text;
- a ticked roster that is on the form but not in the sync's plan (a club added in between);
- the sync's dry run failing, or its summary not being a dry run's;
- fewer submissions fetched than the form reports; a ledger that does not balance;
- one club with two club codes; a Roster export without `girl_id`;
- `--out` or `--raw-dir` inside the repository outside `data/`.

## Readings of the contract (where its words left a choice)
- `q18_differs` is set only when question 18 is not empty: an empty one is `q18_empty` alone, so
  the two counts do not overlap. The comparison ignores order (the pieces, split on commas and
  trimmed, against the ticked names of all the submission's rosters, both sorted) and nothing
  else: case and spaces inside a name count.
- `q5_differs` is literal: question 5 as submitted is not the string the roster sends today. A
  roster with no account name therefore carries it too.
- `bare_shared_name`: question 5 equals the roster's own plain club name (compared by
  `glow.text.key`) and the roster sends `<club> - <something>` today. The "more than one club has
  or had it" part is implied by the long name and is not looked up again.
- `retired_club`: the question is gone, or the sync names no partner for the roster, or the
  Roster has no active row for that partner and club (`glow.sync.roster_pairs`).
- `name_not_on_roster_now:<count>` compares each ticked name, trimmed, with the roster's options
  today exactly. In the per-form `flags` table its key is `name_not_on_roster_now`.
- Every flag is a key of `forms.<region>.flags`, with 0 when no row has it; the numbers are rows.
- `resolver_commit` gets `-dirty` when tracked files differ from that commit.
- `sf_account_name`, `partner`, `club_code`, `attendance_date`, `q5`, `module*`, `creator`: null
  when there is none; never an empty string made up by the tool.

## Additions beyond the contract (the loader can ignore them)
Per form, beside `form_id / submissions / pre_launch / rows / no_ticks / flags`: `fetched`,
`not_active` (by status), `with_ticks`, `flag_submissions` (each flag counted by submission),
`picked_several` and `picked_several_with_ticks` (the Club picker's answer holds more than one
club), `clubs`, `attendance_dates`, `attendance_first/last`, `created_first/last`,
`same_club_and_date` (groups and rows: kept, never collapsed) and `no_ticks_but_q18`.

`no_ticks_but_q18` lists submissions with no tick whose question 18 still holds names. They get
no row, as the contract says, and stay in `no_ticks`; they are printed with a `!` because there
are two ways to get there and the tool cannot tell them apart: the mentor took the ticks back,
or the ticks sat in a roster question deleted since (see the first finding below).

## What the live answers look like (read 2026-09-30, in memory, all submissions of the four forms)
- A submission's `answers` is rebuilt from the form **as it is today**: every question of the
  form is listed with its `name`, `order`, `text` and `type` (244 entries per Africa submission),
  including rosters created after the submission; `answer` is present only where there was one.
  No answer of any submission names a question that is not on the form, and every checkbox
  answer's text equals the question's text today. So an answer to a question deleted since is,
  as far as can be seen, **not served at all** - it cannot be observed (q158, q422 and q429,
  deleted 2026-09-30, held no answers, so there is no counter-example either way). The code
  still handles both shapes it could take (design 4), and the `no_ticks_but_q18` list is the
  net under the case it cannot see.
- A ticked roster: `answer` is a list of strings, with a `prettyFormat` string beside it. An
  unticked one has no `answer` key.
- Question 17: `answer` is `{year, month, day, datetime}`, all submissions filled.
- Question 19: a list of one link on every submission.
- The Club picker: a list of strings (it is a multi-select), or no `answer` (typed era).
- Questions 5 and 18: a string, or no `answer`.
- `status` is `ACTIVE` on every submission; `created_at` is `yyyy-mm-dd hh:mm:ss`, US Eastern;
  `updated_at` is null throughout. `orderby` / `direction` did not give an ascending list, so
  the paging relies on the default order and the count check (design 2).

## Order of work
1. This plan. 2. The tool and its tests (`make check`). 3. The docs. 4. The read-only proof on
the live forms, recorded below.

## Risks
- **Names in the wrong place.** The output is refused anywhere in the repository but `data/`;
  the tests assert that neither stdout nor any refusal carries a fixture name.
- **A write by accident.** The tool has no write call; the sync is started without `--apply`,
  and a summary that says `apply` is refused. A test pins the argument list.
- **The sync's dry run is slow on Africa** (its questions GET): one run takes a few minutes.
- **The form changes between the dry run and the fetch** (the automatic sync adds a club): a
  ticked roster unknown to the plan is refused with "run it again".
- **A roster deleted with answers in it** would make its submissions look like "no tick"
  (first finding). None exists today; `no_ticks_but_q18` would show it.

## Proof
Recorded after the live run (below).
