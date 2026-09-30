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
   today. Its spelling is the live Club picker's entry (the exact one, else the one equal under
   `glow.text.key`; the picker has none: null - review, point 2). The sync's output is captured
   and not echoed (it is not redacted). A form with no submission at all gets no dry run.
4. **Ticked rosters**: a roster is a `control_checkbox` question of the form as it is today. An
   answer to a question that is no longer on the form counts when the answer itself says it was
   a checkbox and carries its text (row: `retired_club`, `no_account_name`, club = that text,
   partner and code null); an answered question that is not on the form and says nothing about
   itself is refused.
5. **Club code**: the prefix of the girl ids (`CLUBCODE-LASTCODE-NNN`, `appsscript/Ids.gs`) of
   the Roster rows, any status, whose partner and club are the ones the sync names (compared by
   `glow.text.key`). Where the sync names no partner (a plain-named roster outside the region's
   active export), the partner is the Roster's only holder of that club name, any status, any
   region (review, point 1); no such single holder, or no row: null. Two different prefixes
   for one club: the tool stops.
6. **The ledger**: per form, fetched = not active + pre-launch + in range, and in range = with
   rows + no ticks, by submission id, each once. It is checked per form and over the forms; a
   miss exits before the result is written.
7. **Privacy**: the result and the raw copies hold girls' names and mentors' contact details.
   Inside the checkout the tool writes them only under `data/` (git-ignored) and refuses any
   other place in the repository - the checkout being recognised by file identity, however its
   path is spelled (review, point 4); outside the checkout is the operator's choice. What is
   printed is counts, dates, flags, form ids and submission ids. A refusal names the submission
   id and the question id, never a value; a failed fetch never quotes a cut-off answer (review,
   point 3).

## Refusals (exit non-zero, no result written; raw copies fetched before the refusal stay)
- a checkbox answer that is not a list of strings; question 5 or 18 that is not text; a photo
  or Club-picker answer of another shape; `created_at` not `yyyy-mm-dd hh:mm:ss`; the answers
  not a table by question id;
- an answered question that is not on the form and carries no type; a ticked roster not on the
  form whose answer carries no text;
- a ticked roster that is on the form but not in the sync's plan (a club added in between);
- the sync's dry run failing, or its summary not being a dry run's;
- fewer submissions fetched than the form reports; a ledger that does not balance;
- one club with two club codes; a Roster export without `girl_id`;
- `--out` or `--raw-dir` inside the repository outside `data/`;
- a run that does not cover all four regions (`--region`) writing the default path, which is
  the loader's file.

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
- `retired_club`: the question is gone, or no partner can be named for the roster (neither by
  the sync nor as the Roster's only holder of the name), or the Roster has no active row for
  that partner and club in any region (`glow.sync.roster_pairs`). A club whose rows are active
  under another region, or none, while its question is still on this form is therefore not
  `retired_club`.
- The name flags, the module flags, `attendance_date` and `flag_vocabulary` are as the contract
  changes below say (2026-09-30); `name_not_on_roster_now` no longer exists.
- Every flag is a key of `forms.<region>.flags`, with 0 when no row has it; the numbers are rows.
- `resolver_commit` gets `-dirty` when tracked files differ from that commit.
- `sf_account_name`, `partner`, `club_code`, `q5`, `module*`, `creator`: null when there is
  none; never an empty string made up by the tool. `attendance_date` is the one exception: `""`.

## Additions beyond the contract (the loader can ignore them)
Per form, beside `form_id / submissions / pre_launch / rows / no_ticks / flags`: `fetched`,
`not_active` (by status), `with_ticks`, `flag_submissions` (each flag counted by submission),
`picked_several` and `picked_several_with_ticks` (the Club picker's answer holds more than one
club), `clubs`, `attendance_dates`, `attendance_first/last`, `created_first/last`,
`same_club_and_date` (groups and rows: kept, never collapsed), `no_ticks_but_q18`,
`partner_from_roster`, and with the contract changes `names_active_not_an_option` and
`copied_fields`.

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

## Review of 2026-09-30: eight findings, all fixed (what changes)
The branch was reviewed after the first proof; every finding was reproduced offline with
fictional data. None changed a number of the first proof. What each fix does:

1. **A club the sync does not claim keeps its partner and code** (design 5, `retired_club`).
   The sync names a partner only for a roster of the region's *active* export, or one whose
   rule names it (a long name). For a plain-named roster that is on the form but retired, or
   whose rows now carry another or no region, it says `''`. The resolver then asks the Roster
   export, any status, all regions, who has a club of that name (`glow.sync.club_partners`, the
   sync's own helper): exactly one partner - the row gets that partner and its code;
   `retired_club` only if that pair has no active row. Two or more partners - null, as before
   (no guess). No new flag: the row resolves fully, and the loader refuses a flag it does not
   know. The report prints how many rows took their partner this way.
2. **`sf_account_name` is the live Club picker's spelling** (design 3). The sync records no
   change for a respelling that is equal under `glow.text.key`, so its value could be the
   Roster's spelling (planned), not the picker entry's (sent today). The resolver now takes the
   live picker option: the exact one, else the one equal by key; when the picker has none, null
   and `no_account_name`. A form without a picker (typed) is left as the sync says.
3. **A cut-off answer is never quoted** (`glow/jotform.py`). A submissions page cut off in
   transfer is a JSON prefix that starts with a submission's id and the submitter's IP address;
   the client's error quoted its first 200 characters. It now says how many characters came and
   shows none of them; an HTML error page is still quoted, and a 401/429 still gives Jotform's
   message. Fixed in the shared client, where the quote is made, so every tool has it.
4. **The checkout is recognised by file identity** (design 7), not by how its path is spelled:
   on a case-insensitive disk another spelling of the path is the same folder. The closing line
   says `data/ is git-ignored` only when the files are under this checkout's `data/`.
5. **Two flags added for the loader** (a deviation from the brief's list of flag strings): the
   loader holds a session on `name_unknown_to_roster` and the resolver is the only tool that
   reads the Roster. Beside `name_not_on_roster_now:<n>` (unchanged) a row now carries
   `name_unknown_to_roster:<u>` - of those names, the ones the Roster has no row for under that
   partner and club, any status (`glow.sync.roster_names`, compared by `glow.text.key`: an accent
   or a letter differs, capitals and spaces do not) - and `name_left_roster:<l>` - the rest: the
   Roster knows her, she is not an option today. Each only when above zero; u + l = n. A row
   with no partner (a deleted question, a name two partners have) counts all as unknown.
6. **`--region` does not overwrite the loader's file**: a run that does not cover all four
   regions refuses to write the default path and asks for `--out`.
7. **Refusals say "no result written"**: the raw copies of the regions fetched so far are
   already overwritten when a later step refuses (they are kept on purpose: the raw copy is
   where the refused answer can be looked at), so "nothing written" was not true.
8. **A region named twice is read once** (it doubled the rows and failed the ledger).

## Contract changes of 2026-09-30 (agreed by the two sessions after the build started)
Four, each with a test that fails without it. They replace what the sections above say where
the two differ; the proofs recorded further down are left as they were run.

1. **`name_not_on_roster_now` is dropped.** Two name flags remain, and they are the only flags
   written with a count (`<flag>:<n>`). A ticked name that is an option of its roster today
   (exactly, trimmed) is never flagged: it is what the form offers and sends. For each other
   ticked name the Roster export is asked, by `glow.text.key` (capitals and spaces do not
   count, a letter or an accent does), about the row's partner and club:
   - `name_unknown_to_roster:<n>` - no Roster row of that club has the name, under any status.
     A row with no partner (a deleted question, a name two partners have) has no Roster rows to
     ask: every such name counts here. The loader holds the session.
   - `name_left_roster:<n>` - the club has a Roster row of that name and none of them is
     active: a girl who left. The loader sends her.
   - the club has an **active** row of that name (the tick is spelled unlike today's option in
     capitals or spaces only, or the form is behind the Roster): no flag - she is on the
     roster. Counted per form as `names_active_not_an_option` and printed when it is not 0,
     so the case cannot go unseen now that the wider flag is gone.
2. **`attendance_date`** is a zero-padded `yyyy-mm-dd` string, or `""` - never null - when
   question 17 is missing or is not a date; the row then carries `date_missing`.
3. **`module` is the canonical module**, not question 98.
   - *How the three hidden fields are filled* (the sync's section C, `build_conditions`; read
     on all four live forms 2026-09-30, identical): question 102 (`year_id`) is the calculation
     `{94}` - the Year dropdown, options `1|2|3` with calcValues `|1|2|3`. Question 98
     (`module_id`) has three calculation rules, `{14}`, `{92}` and `{93}`, each firing when its
     module dropdown is filled; the form shows the dropdown of the year picked
     (`glow.sync.MODULES`). Question 100 (`week_id`) has four, `{15}`, `{95}`, `{96}`, `{97}`
     (8, 10, 14 and 15 sessions, `glow.sync.WEEKS`), each dropdown with calcValues `|1|2|…`;
     the form shows the 8-session one for year 1 and, for years 2 and 3, the one of the module
     (`SESSION_OVERRIDES`, else 8).
   - *Why 98 can be wrong*: the module dropdowns have no calcValues, so the calculation copies
     the option's **visible text**, which a browser's page translation rewrites. The dropdown's
     own submitted answer is the option's value, which it does not touch.
   - *Which dropdown applies*: the one the Year answer (question 94) names. `clearFieldOnHide`
     is `disable` on the forms, so a dropdown hidden again can keep an answer; an answer in
     another module dropdown is therefore ignored. (In the 484 submissions in range exactly
     one module dropdown and one session dropdown is answered, the ones the year picks.)
   - *The rule*: `module` = the stored answer of that dropdown, when it is one of the
     dropdown's options today. `module_translated` when question 98 as submitted is not exactly
     that value (an empty 98 included). When there is no Year answer, the year names no
     dropdown of the form, that dropdown has no answer, or the answer is not one of its options
     today: `module` stays question 98 as submitted and the row carries `module_unresolved`
     (the loader holds it) - no guess from the other dropdowns.
   - `module_week` and `module_year` stay questions 100 and 102 as submitted. They are compared
     with their sources the same way - 100 with the calcValue of the answer of the session
     dropdown the form shows for that year and canonical module, 102 with the calcValue of the
     Year answer - and the per-form counts (same / differ / source not determined, by
     submission in range and of them with ticks) are printed and kept under `copied_fields`.
     No flag.
4. **`flag_vocabulary`**, top level: the sorted list of every flag name the resolver can emit
   (the two name flags without their `:<n>`). A test pins what the resolver emits to exactly
   `multi_club, q5_differs, q18_empty, q18_differs, typed_era, bare_shared_name, retired_club,
   no_account_name, date_before_2026_09, date_missing, name_left_roster, name_unknown_to_roster,
   name_has_comma, name_repeats, module_translated, module_unresolved`.

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

### Offline
`make check CSV=<the 2026-08-24 enrollment export>`: `real data …: parsed 328 clubs, 6210 girls`,
`ALL CHECKS PASSED` ×3, `py: 40 files parse, 23 scripts answer --help`, `Ran 328 tests … OK`
(27 of them `BackfillResolve`), `gs: 10 files parse`, `secrets: clean`, `docs-links: ok`,
`fixtures: up to date`, `CHECK PASSED`.

### Live, read-only (2026-09-30, fetched 12:57 UTC, at commit `11ba51c`)
A fresh Roster export (6963 rows), the result and the raw copies went to a scratch directory
outside the repository (`--out`, `--raw-dir`) and were deleted afterwards. The only calls were
GETs, and four dry runs of the sync (no `--apply`); no form was out of step with the export
(no "planned writes" note).

| | Africa | Asia | Latin America | U.S | all |
|---|---|---|---|---|---|
| fetched (all `ACTIVE`) | 144 | 230 | 113 | 0 | 487 |
| pre-launch, left out | 1 | 0 | 2 | 0 | 3 |
| **submissions in range** | 143 | 230 | 111 | 0 | **484** |
| with ticks | 115 | 212 | 93 | 0 | 420 |
| no ticks | 28 | 18 | 18 | 0 | 64 |
| **rows** | 116 | 212 | 93 | 0 | **421** |
| distinct clubs | 49 | 77 | 28 | 0 | 154 |
| distinct attendance dates | 26 | 28 | 28 | 0 | |
| attendance dates from .. to | 2026-06-09 .. 09-29 | 2026-06-09 .. 09-30 | 2026-02-09 .. 09-30 | | |
| created_at (US Eastern) from | 09-05 06:40:13 | 09-01 02:56:21 | 09-02 07:25:43 | | |
| created_at (US Eastern) to | 09-30 08:36:40 | 09-30 08:44:02 | 09-30 07:42:18 | | |
| several clubs picked (of them with ticks) | 12 (9) | 8 (8) | 0 | 0 | 20 (17) |
| one club + one date more than once: groups / rows, all kept | 6 / 12 | 15 / 31 | 10 / 21 | 0 | 31 / 64 |
| no tick but names in question 18 | 0 | 0 | 0 | 0 | 0 |

Flags, rows (submissions):

| flag | Africa | Asia | Latin America | all rows |
|---|---|---|---|---|
| `multi_club` | 2 (1) | 0 | 0 | 2 |
| `q5_differs` | 15 (14) | 17 | 10 | 42 |
| `q18_empty` | 6 | 9 | 2 | 17 |
| `q18_differs` | 10 (9) | 6 | 0 | 16 |
| `typed_era` | 19 | 10 | 40 | 69 |
| `bare_shared_name` | 2 | 0 | 0 | 2 |
| `retired_club` | 0 | 0 | 0 | 0 |
| `no_account_name` | 0 | 0 | 0 | 0 |
| `date_before_2026_09` | 1 | 3 | 5 | 9 |
| `date_missing` | 0 | 0 | 0 | 0 |
| `name_not_on_roster_now` | 1 | 4 | 0 | 5 |
| `name_has_comma` | 0 | 0 | 0 | 0 |
| `name_repeats` | 0 | 0 | 0 | 0 |

`LEDGER: 484 submissions in range = 420 with rows (421 rows) + 64 with no tick - balanced; 3
pre-launch left out`.

### Checked independently of the tool
A second script, written apart from the resolver and reading the raw copies and the live forms,
found for every form: the ids with rows and the ids with no tick are exactly the active
submissions in range, none in both; the rows are exactly the (submission, ticked checkbox)
pairs; each row's names are that checkbox's ticks in order; `created_at` and `q5` as Jotform
gave them; every `sf_account_name` is an option of that form's Club picker today (49 / 77 / 28
distinct names); every row's club is its roster question's text today; every `club_code` is the
single girl-id prefix the Roster has for that partner and club (no row without a code or a
partner); every submission lists exactly the form's questions of today (244 / 121 / 64).

### Against the numbers known beforehand
| known on 2026-09-30 | the resolver |
|---|---|
| Africa 143, Asia about 229, Latin America 113, U.S 0 submissions | 144, 230, 113, 0 fetched (one more each on Africa and Asia since) |
| about 20 submissions picked several clubs | 20 (12 Africa, 8 Asia). Only **one** of them ticked girls in two rosters, so `multi_club` is 1 submission, 2 rows; 16 ticked in one roster (one row, `q5_differs`), 3 ticked nothing |
| 17 with ticks and an empty question 18 | 17 (`q18_empty`: 6 + 9 + 2) |
| about 56 with no tick | **64**. All 64 have an empty question 18 and a photo. 8 of them are Africa submissions whose question 5 is a bare name two clubs share (Ruby 5, Super Girls 2, Shining Stars 1), which the earlier count seems to have set apart: 64 - 8 = 56 |
| 10 Africa submissions with a bare shared name | 10 by question 5 (Ruby 7, Super Girls 2, Shining Stars 1), but only **2** have ticks - both Ruby, both `bare_shared_name`. The other 8 have no tick and therefore no row |

### What the numbers say (for the loader and for Ryan)
- **64 submissions have no ticked girl** and get no row. Each still has a date, a module and a
  photo. Whether a session with nobody ticked is loaded at all is not the resolver's decision.
- **8 of those are the shared-name clubs** (Ruby, Super Girls, Shining Stars). The likely cause
  (not proven here): in those weeks such a roster showed only when the typed Partner box
  matched, so the mentor saw no roster to tick. Which girls attended is not in Jotform for these.
- **`q18_differs`, 15 submissions**: 12 differ from the ticked names only by spaces inside a
  name; 3 really differ (the one two-roster submission, and two Asia submissions whose question
  18 holds more names than are ticked).
- **`q5_differs`, 42 rows**: 18 are the several-clubs-picked ones; 21 differ only in capitals or
  spaces (16 typed, 5 picked); 3 are other single-club differences.
- **`date_before_2026_09`, 9 rows**: attendance dates as early as February and June 2026 on
  submissions created in September - likely a wrong month or year picked.
- **Pre-launch, 3**: two of 2026-08-28 (one Africa, one Latin America, each with a tick) and one
  Latin America submission of 2026-08-31 22:49:40 US Eastern, 70 minutes before the range
  starts, with no tick.
- **One club and one date more than once: 31 groups, 64 rows** - all kept.
- No retired club, no roster without an account name, no name with a comma, none twice in a row.

### Clean-up
The scratch directory with the Roster export, the result and the raw copies was deleted after
the run; nothing holding a name was written inside the repository.

## Proof after the review's fixes (2026-09-30)

### Each finding, before and after
Every one of the eight has a test that failed on the code as reviewed (`a8e1f1a`) and passes
now: the three clubs the sync names no partner for came out with partner and code null; the
respelled club with the Roster's spelling and `q5_differs`; the cut-off page's error quoted the
submission id and the IP address; the other spelling of the checkout's path was let through;
the two name flags were absent; `--region Asia` was not refused; the refusals said "nothing
written"; a region named twice failed the ledger. The first two were also run once against the
real sync (`sync_attendance_form.main()` on the test suite's fake form, fictional data, in
scratch): a plain-named club with every row inactive, with its rows under another region, and
with no region gets its partner and code (`retired_club` only in the first case); the same
name inactive under two partners stays null; a club respelled in capitals in the Roster is
reported with the live picker's spelling while the sync plans 2 writes and records no change.

### Offline
`make check`: `ALL CHECKS PASSED` ×3, `py: 40 files parse, 23 scripts answer --help`,
`Ran 335 tests … OK` (34 of them `BackfillResolve`), `gs: 10 files parse`, `secrets: clean`,
`docs-links: ok`, `fixtures: up to date`, `CHECK PASSED`.

### Live, read-only (fetched 13:30 UTC, at commit `f048412`)
A fresh Roster export (6963 rows), the result and the raw copies in a scratch directory outside
the repository, deleted afterwards. GETs and four dry runs of the sync only; no form out of
step with the export. **Every number of the first proof is unchanged**: fetched 144 / 230 /
113 / 0; in range 143 / 230 / 111 / 0 = 484; with ticks 115 / 212 / 93 = 420; no ticks 28 /
18 / 18 = 64; rows 116 / 212 / 93 = 421; pre-launch 1 / 0 / 2; clubs 49 / 77 / 28; every flag
count of the table above; the same first and last `created_at`. New:

| | Africa | Asia | Latin America | all rows |
|---|---|---|---|---|
| `name_not_on_roster_now` | 1 | 4 | 0 | 5 (7 names) |
| `name_unknown_to_roster` | 0 | 0 | 0 | **0** |
| `name_left_roster` | 1 | 4 | 0 | 5 (7 names) |
| rows whose partner came from the Roster, not the sync | 0 | 0 | 0 | 0 |

`LEDGER: 484 submissions in range = 420 with rows (421 rows) + 64 with no tick - balanced; 3
pre-launch left out`. The closing line said the files were outside the checkout's `data/`.

Checked apart from the tool, on the output and the live forms (counts only): all 421 rows have
a partner, a club code and an `sf_account_name` that is exactly an entry of that form's live
Club picker (49 of 218, 77 of 95, 28 of 38 entries in use); every row's club is its roster
question's text today; the counted name flags equal a second count made from the Roster export
read on its own (0 rows differ); the 7 names are all rows of that partner and club with
status inactive - girls who left, which the loader sends. So today nothing is held for an
unknown name.

### Open between the two tools (for the loader's session; not changed here)
- The loader as it stands in the main checkout (uncommitted `tools/sf_backfill.py`, read but
  not touched) knows `name_unknown_to_roster` and `name_left_roster` and **does not know
  `name_not_on_roster_now`**: its `check_resolved` refuses the file on the first of the 5 rows
  ("carries a flag this tool does not know"). Tried in memory: with that one flag taken off the
  rows the file is accepted, and 0 rows carry a flag it holds on. The resolver keeps the flag
  because its brief fixes that string; one of the two has to give: `name_not_on_roster_now`
  into the loader's pass list (one word), or out of the resolver (one line and its tests).
- The loader also lists `module_unresolved` and `module_translated`. The resolver's brief has
  the module, week and year "as submitted" and no such flags; it emits neither.
- A `resolved.json` written by `--region` holds fewer than four forms. The resolver no longer
  writes one to the default path; the loader does not look at `forms` and could refuse a file
  whose `forms` are not all four.

### Clean-up
The scratch directory (Roster export, result, raw copies, report, the checking scripts) was
deleted after the run; no file holding a name was written in either checkout.
