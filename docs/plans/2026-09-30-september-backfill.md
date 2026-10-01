---
title: September back-fill - the Jotform attendance that never reached Salesforce
author: Claude (with Ryan)
status: in-progress (loader rewritten after review and tested offline; Ryan unfrozen, CLI login made; nothing sent)
created: 2026-09-30
intent: none - Ryan's request of 2026-09-30 ("bring in all submissions for the month of September for all forms")
---

# Plan: September back-fill

## Context
The forms went live on 2026-09-01 but the Jotform to Salesforce connection was dead until
2026-09-30 ([reconnect plan](2026-09-30-salesforce-reconnect.md)). About 480 attendance
submissions (Africa 142, Asia 229, Latin America 111, U.S 0) sit in Jotform only. Three reached
Salesforce live on 09-30 before the connection stopped again (below). Ryan wants the month in
Salesforce, then a test report on it.

Replaying a submission as Jotform would have sent it is not safe. Read from the org on 09-30
(Apex `AttendanceBatchProcessor`, trigger after insert on `Attendance_Batch__c`):

- a club name no Account carries makes it **create a stray Club account** (no partner);
- a batch without names is stored as Success and then **blocks** the real batch for that club
  and day; only the **first** batch per club and day counts, later ones are stored as Failed;
- it is not bulk-safe: several batches in one request miss each other in the duplicate checks
  and share the limits; one Contact is inserted per new girl, inside a loop (22 proven);
- a handled error mid-batch leaves the contacts and part of the rows behind, and those rows
  then block a retry for that club and day;
- names are split on commas only and matched, case-insensitively, against the club's own
  Participant contacts; the same new name twice makes two Contacts.

And question 5 / question 18, which the live integration sends, are wrong on part of the month:
20 submissions carry several club names run together, 17 have girls ticked but an empty name
list, 2 carry another club's girls, some carry a bare shared name or a typed spelling.

## The freeze (2026-09-30 12:16 UTC)
Two seconds after Ryan's first Salesforce CLI login, Salesforce's Automated Process froze his
user and revoked all his tokens, the three Jotform ones included (Setup audit trail; no flow or
Apex in the org does this). Salesforce freezes a user whose app or API connection comes from an
anonymising VPN or proxy (in force since April 2026); Ryan's logins came from three countries in
three days. Until another administrator unfreezes him **no submission reaches Salesforce**, so
the set to back-fill has no end date yet. After that: no VPN for anything that talks to
Salesforce from the Mac, Jotform re-authorised on the five forms, and only then a CLI login.

## Files that change
- `tools/sf_backfill.py` - new: `snapshot`, `plan`, `send`, `close`, `status`.
  `test/sf_backfill_test.py` (64 offline tests, a fake org that follows the processor's rules),
  one import line in `test/python_test.py`.
- `tools/backfill_resolve.py` and its tests - new, by session jotform-glow-sync-54.
- `docs/RUNBOOK.md` ("Back-fill of attendance into Salesforce"; the connector bullet under "Club
  accounts in Salesforce"), `docs/DECISIONS.md`, `.claude/skills/live-systems/SKILL.md`, this plan.
- Nothing under `appsscript/`, no form, no sheet.

## Design
Two tools, both dry by nature or by default, files under `data/backfill_2026-09/` (never
committed, owner-only; `resolved.json`, `plan.json` and `sent_names.json` hold girls' names).

1. **Form side: the resolver** - `tools/backfill_resolve.py` (session jotform-glow-sync-54).
   GET only. Every submission becomes one row per ticked roster: the club is the **roster that
   holds the ticks**, the Salesforce name is what that roster's picker entry sends today, the
   names are the ticks themselves (never question 18), the module is the stored module answer
   (not the translated copy). Submissions with nobody ticked are listed, never sent. Output
   `resolved.json`, a counts-only report.
2. **Salesforce side: the loader** - `tools/sf_backfill.py`:
   - `snapshot` (live, read-only): accounts, batches, attendance per club and day, participant
     counts. No Contact name or other personal field is ever selected: counts and ids only.
   - `plan` (offline): one session per club and day. Reports of one session with the same
     module and week are joined (a girl counts once). A session goes to `held.csv` with **every**
     reason that holds it; a line in `decisions.csv` releases only what it names (`skip`,
     `use <submission id>`, `date yyyy-mm-dd`, `accept <reason>`). What Salesforce already has
     is skipped only when the counts agree; an empty or failed batch on the day is a hold.
   - `send`: dry run by default. `--apply --vpn-off` sends **one batch per request**, a club's
     sessions in date order, small clubs first. For each one it proves the name leads to exactly
     its one Club account, that the club and day are still empty and that nobody else added
     girls; writes a `sending` line to the ledger; inserts; reads the batch back (Success, the
     right account, one row per girl, the expected number of new girls, the contacts it
     created); closes the ledger line. It stops at the first thing that is not as planned:
     a refusal that saved nothing parks that club; a lost answer stops everything until the
     next run has looked the batch up by its marker; a batch that is in Salesforce but not
     right stops everything until it is `close`d as removed or accepted.
   - New girls are counted exactly only for a club whose every participant this run created;
     any other club (the pilot clubs, a club with an accepted or removed batch) is held for an
     `accept club_has_earlier_contacts` per session and checked by bounds.
   - `status`: what was sent, and the rollback list by id (batches in `ledger.csv`, the
     contacts each batch created in `created_contacts.csv`).
   - Access: the Salesforce CLI's stored login; the token goes to curl on stdin (`-q`, no
     proxy), never onto a command line or disk. `--apply` is caught by the live gate like every
     other writer; both live commands also refuse without `--vpn-off`.
   - Each batch carries `Creator__c` "Jotform back-fill <account id> <submission ids>" (the processor never
     reads that field; live batches say "Jotform"), fuzzy matching off, no photo. A Salesforce
     status message is never printed or stored, only its kind: it can quote a girl's name.

Held, never sent without Ryan's line in `decisions.csv`:

| reason | what it is | how it is released | 09-30 count |
|---|---|---|---|
| `same_day_different_module` | one club and day reported with different module/week | `use <id>` | 16 sessions |
| `date_before_september` | attendance dated before 09-01 (some look like day and month swapped) | `date`, `accept` or `skip` | 9 |
| `several_rosters_ticked` | one submission with girls ticked in two clubs | `accept` | 1 submission |
| `more_new_girls_than_proven` | more than 22 new girls in one batch | `accept` | up to 10 |
| `similar_names` | two girls the Contact duplicate rule would take for one | `accept`, or `--dup-rule-ok` once the rule no longer alerts | about 8 clubs |
| `club_has_earlier_contacts` | the club's participants are not all this run's (pilot clubs) | `accept`, per session | 5-6 clubs |
| `name_unknown_to_roster` | a ticked name the Roster never had | `accept` | up to 7 ticks |
| `salesforce_has_different_count`, `later_report_of_sent_session`, `submission_already_sent` | Salesforce or this run already has the day, but not the same girls | `skip` (nothing can be added to a day) | - |
| `salesforce_has_empty_or_failed_batch` | a batch without attendance blocks the day | remove that batch in Salesforce | - |
| `batch_outcome_open`, `earlier_session_held` | this run has a batch for the session whose outcome is open; an earlier session of the club is held | settle, close, or decide the earlier one | - |
| account problems, bad names, a missing date or module | never expected; refused rather than guessed | fix the cause | 0 |

The Contact duplicate rule "First & Last & Account" (read 2026-09-30): on insert it **allowed**
with **Alert** and Report. An alert refuses an insert made by code, so a girl whose first name
resembles a club-mate's with the same last name made the processor fail mid-batch - in the
back-fill and in the live flow alike. On Ryan's go it was switched to **Report only** on
2026-10-01 11:26 UTC (deploy 0AfRP000002foFp0AI; read back: Allow, Report, no alert; proven with
two similar fictional test contacts on the test account: both saved, one duplicate reported, both
deleted). From then on `plan --dup-rule-ok`: two similar names are two girls, and a pair that is
really one girl spelled twice is listed in Salesforce's duplicate reports, not refused.

## Order of work
1. Ryan is unfrozen; VPN off; Jotform re-authorised; `integration_status.py` and a live
   submission arriving prove the flow.
2. Ryan's decisions (below) go into `decisions.csv`.
3. Resolver run, `snapshot`, `plan`; the report and `held.csv` go to Ryan (counts only).
4. With Ryan's go: `send --apply --vpn-off --limit 1` (the smallest club), read it in Salesforce, then
   the queue. Held sessions follow as Ryan decides them.
5. `status`, the totals against the resolver's, then the test report
   "Jotform Monthly Attendance (test)" ([clubs plan](2026-09-30-salesforce-clubs.md), Follow-up).

## Ryan's decisions (2026-09-30)
"September is test data for the org; the processes must work for October" - so: nothing is
guessed, and what is doubtful is left out rather than chased.
1. Attendance dated before September (9 sessions): left out (`skip`).
2. A club day reported twice with different weeks (16): the later report counts (`use`).
3. More than 22 new girls in one batch: sent last, one at a time, smallest first (`accept`) -
   it is also what October's live flow will meet.
4. No photos. The `Creator__c` marker stays.
5. The four form-side fixes (names dictionary, stale roster names in question 18, at least one
   tick, module values) follow after the September data is in.

## Risks
- **Anything sent is processed at once** into Contacts and attendance rows. A rollback removes,
  by id, the batches in `ledger.csv` with their rows and the contacts listed in
  `created_contacts.csv` - never by a time window (live submissions create contacts as the same
  user) - with Ryan's go, then `close <key> --removed` for each.
- **A live submission for the same club and day during the run** wins or loses by order; the
  pre-check sees it and stops.
- **The duplicate rule alerts** and so refuses a girl mid-batch: `similar_names` stays held until
  the rule is Report only.
- **Back-filled batches carry the day they were sent as created date**; the attendance date is
  the session's.
- **The tool was reviewed three times by independent reviewers** (the first review led to a
  rewrite, the second to 16 fixes and 26 more tests, the third to 6 fixes and 4 more tests, among
  them a marker that names the club as well as the reports); what it cannot rule out is met by the pre-check
  before and the read-back after every single batch, and by stopping at the first surprise.

## Proof
- `python3 tools/sf_backfill.py plan` → the counts; `send` → `dry run: nothing was sent`
- after the run: `status` → batches = the plan's, every ledger row `ok`; Salesforce counts of
  batches and attendance rows equal the ledger's
- `make check` → `CHECK PASSED` (64 offline tests of the loader, fictional data)
