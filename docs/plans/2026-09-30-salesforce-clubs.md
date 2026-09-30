---
title: Club accounts in Salesforce, linked to their partners
author: Claude (with Ryan)
status: proposed
created: 2026-09-30
intent: none - Ryan's request of 2026-09-29/30 ("assign the clubs to a partner", then "create all clubs")
---

# Plan: Club accounts in Salesforce, linked to their partners

## Context
Salesforce (production org "Global G.L.O.W") holds only the ten pilot Club accounts from
February-March 2026, none of them linked to a partner. The attendance forms send the club's name in
question 5; the Apex `AttendanceBatchProcessor` compares it with **every** Account name (trimmed,
case-insensitive, nothing else folded; first match wins) and, when nothing matches, creates a Club
account with a name and nothing else. So unless the clubs exist before attendance flows again,
every first submission creates a partner-less account, and a spelling that differs from the form by
one character creates a second one.

Ryan's decision (2026-09-30): create every active club as a Club account named exactly as its form
sends it, linked to its partner account through `ParentId`. The approved list is
`data/sf_prep_2026-09-30/clubs_to_create.csv` (364 rows, never committed):

| action | rows | what happens |
|---|---|---|
| `create` | 345 | new Account |
| `link existing (set Parent Account)` | 8 | `ParentId` set on the pilot account, nothing else |
| `create (name incl. partner: same-name club)` | 11 | **held**: not written in this plan |

The 345 + 8 hang on 49 partner accounts. 44 partners match by exact name; five by a confirmed
alias or spelling (21 create rows): Angelo Patri School, Girls Leader Forum and Holbrook Unified
School District were confirmed by Ryan on 2026-09-30, and Development Consortium and Fundacion
Bibliotec differ from the sheet in capitals or an accent only.

Read on 2026-09-30, before anything was written (a read-only review by seven independent checks,
each finding challenged by a second reader):
- Account has one required field (`Name`) and no duplicate rule; validation rules cannot be read
  through the connector. Record types: Club (`012RP000002uklNYAQ`), Household Account (every
  partner account), Organization (unused). 92 accounts: 10 Club, 82 Household Account. No account
  has a parent today, so these are the org's first child accounts.
- No Account carries any of the 345 names, under any record type; the only accounts that answer to
  a write-set name are the eight link targets (Club, no parent). All 49 parents exist, are partner
  accounts, have no parent themselves and carry the name the CSV says.
- Automation on Account: the NPSP trigger `TDTM_Account` (insert, update, delete), the Mailchimp
  package trigger `MC4SF.Account` (before insert, before and after update), and one active
  record-triggered flow, on **update** only ("Opportunity Account Owner Update / remove Access 2",
  activated 2026-09-14). Its eleven elements only read the account's Opportunities and rewrite
  their sharing; Club accounts have no Opportunities. Nothing found creates, renames, e-mails or
  sends anything out for a Club account. Its entry criteria could not be read, which is why the
  first link is written alone.
- The nightly NPSP rollup (21:00 UTC, run by another administrator) sets the rollup fields of each
  new account from empty to 0 on its first night. "Last modified" on the new accounts then shows
  that administrator. Expected.
- The write tools act as Ryan's System Administrator user, so the new accounts are owned by him
  (the pilot accounts are owned by a former staff administrator). Ownership does not affect the
  processor's match. Administrators and eight staff users see the clubs; one staff user does not.
- All 353 names of the write set are options of their region's live Club picker, character for
  character, and every picker's `calcValues` equal its options (`sf_club_accounts.py pickers`).
- The Jotform connection is not running: 11 attendance batches ever, the last on 2026-03-28, and
  its two access tokens belong to a deactivated user.

## What is written
For each `create` row, one Account with exactly four fields:

| field | value |
|---|---|
| `Name` | `sf_account_name`, unchanged (capitals, spacing and spelling as the form sends them) |
| `RecordTypeId` | Club |
| `ParentId` | `sf_partner_account_id` |
| `Description` | `GLOW club code <club_code>; created from the club registry 2026-09-30` (the day the registry was exported, whatever day the write happens) |

For each `link existing` row: `ParentId` = `sf_partner_account_id` on the account in
`already_in_sf`. The name is not touched, although four of the eight differ from the form in
capitals only - the processor's match ignores case.

Nothing else is written: no Contact, no attendance, no field, layout, Apex or flow.

## How these writes are gated
The repository's live gate (`live_gate.sh`, `GLOW_LIVE_OK`) covers Jotform, the sheet and Apps
Script, not the Salesforce connector. The gate here is Ryan's explicit go in the conversation and
the connector's own permission prompt. Only the create and update tools are used; the delete and
"related record" tools are never called under this plan (a rollback needs its own go). The writes
are made by the main session, never by a subagent or a workflow, and the write tools are not added
to any allow list.

## Files that change
- `docs/plans/2026-09-30-salesforce-clubs.md` - this plan, then its Result.
- `tools/sf_club_accounts.py` - new. It never calls Salesforce; it validates the CSV, cuts the
  batches, prints the queries and request bodies, checks the saved reads, and keeps the run log and
  the rollback file. `test/sf_club_accounts_test.py` (fictional data) and one import line in
  `test/python_test.py`.
- When the work is done: `docs/RUNBOOK.md` (a "Club accounts in Salesforce" section),
  `docs/DECISIONS.md`, `docs/BACKLOG.md` (item 27), the live-systems skill (Salesforce as a writer).
- Generated in `data/sf_prep_2026-09-30/`, never committed: `write_set.json`, `run_log.csv`,
  `link_targets_before.json`, `created_accounts.csv`. Saved reads (they carry club names and an
  owner id) stay in that folder or the session scratchpad.

## Order of work
1. **Preflight, read-only.** The write tools are present; the user is Ryan's administrator; the org
   is production; the other sessions have confirmed the main checkout is free. Baseline, to be
   repeated right after the go and at the end - any difference means stop:
   - attendance batches by status (one row: Success, 11, latest 2026-03-28);
   - the Jotform access tokens (two, both of an inactive user, last used 2026-03-28);
   - accounts by record type (Club 10, Household Account 82).
2. **Build the write set**: `python3 tools/sf_club_accounts.py build`. It refuses on a blank or
   duplicated name (case-insensitive, across all 364 rows and the plain names of the held clubs),
   edge, double or invisible whitespace, a name that differs from the sheet's club name, a region
   that is no form region, a malformed Account id, one partner with two ids, or an on-hold account
   as a parent or a link target. 18 batches: three single records (a create with an apostrophe
   under an exact-match partner; a link on the pilot account with the least history; a create with
   an accented letter), then the other 343 creates in batches of 25 or fewer (by region, then
   partner), then the other seven links. The CSV's checksum is stored; a changed CSV or a rebuild
   that would move the batches after the run started is refused.
3. **Compare with the live forms**: `python3 tools/sf_club_accounts.py pickers` (GET only). Every
   name must be an option of its region's Club picker, `calcValues` must be the options in order,
   and the picker may offer nothing this list does not know. Repeated right before the first write
   and at the end (the runner may add or rename a club meanwhile).
4. **Compare with Salesforce, read-only.**
   - `soql --all` → `precheck --all`: for all 353 names, exactly the eight link targets exist, each
     a Club with no parent.
   - `soql --parents` → `parents`: the 49 parents exist, are partner accounts, carry the name the
     CSV says, have no parent, are not on hold.
   - The two on-hold accounts are read and left alone.
5. **Show Ryan** the counts and ten sample rows, and the two decisions below; wait for his go.
   Status becomes `accepted`. The plan and the tool are committed before the first write, as soon
   as the other session's window in the main checkout is closed.
   - The public partner sign-up page lists every Account (Risks): Ryan looks at its organisation
     field once, submitting nothing, and accepts the club names in it or has the list filtered first.
   - Nobody re-authorises the Jotform connection until the Result is written.
6. **One create** (batch 0). Re-read it by the id the connector returned and by name: Name
   character for character (the apostrophe), RecordType Club, ParentId set, Description as sent.
   Count what else appeared: Contacts and child accounts on it (0), NPSP error records (16 before,
   16 after). Anything unexpected, or an error from the call: stop, do not retry.
7. **One link** (batch 1). Read just before: the account, its sharing rows (one, the owner), its
   Contact count, Opportunity sharing rows by cause (126 manual, 228 owner), NPSP error records
   (16). Write `ParentId`. Read again: `ParentId` set; Name, owner and record type as before; the
   other four reads unchanged. A changed owner is a hard stop (the pilot accounts' owner is an
   inactive user and could probably not be set back). An error from the call means nothing was
   saved: stop, do not retry.
8. **One accented create** (batch 2), re-read by returned id and by name, character for character.
9. **The rest, batch by batch.** For every batch:
   - read it (`soql --batch N`: its names and its parents) and run `precheck`, which opens the batch
     in `run_log.csv`. It refuses an empty, cut, foreign or stale read, a batch already written, a
     batch out of order, an existing name, a changed parent;
   - write its records, pasting each body from `bodies --batch N` unchanged, and keep the returned ids;
   - read the batch again and the number of Club accounts (`soql --count`), and run
     `verify --ids … --club-count …`. It demands exactly one Account per name, the Name character
     for character, RecordType, ParentId and Description as sent, the returned ids to be the ones
     found by name, and the Club count to be 10 plus what the run has recorded - so an account
     stored under another name, a double write or a stranger's account stops the run. It records
     the ids in `created_accounts.csv` and closes the batch.
   - Not between 20:50 and 21:10 UTC (the nightly rollup).
10. **Totals, read-only**: `soql --totals` → `totals` (all Club accounts against the write set, the
    rollback file and the link targets' before-images: by region and by partner, no two Club
    accounts with one name, the two on-hold accounts present and without a parent, 355 in all);
    the step-1 baseline again; `pickers` again; and four counts that must be 0 now and stay 0:
    Contacts on Club accounts that are not girls (role other than Participant), Contacts on Club
    accounts marked as portal sign-ups, Monthly Reports on Club accounts, programme-income records
    on Club accounts.
11. **The morning after** (first session after 21:00 UTC): all 345 new accounts show the rollup
    fields at 0, NPSP error records still 16, `totals` again on a fresh read.
12. **Record**: Result below, RUNBOOK section, decisions, backlog, memory, work log; commit; push
    only with Ryan's go. The 36 clubs of this list that are "pending" in the sheet's SF Pending tab
    are set to "done" by Ryan in the sheet (or with a separate go) before the Monday e-mail of
    2026-10-05 - only those whose account is in `created_accounts.csv`.

A call whose outcome is unknown (an error, a timeout, no id returned) is **never repeated blind**.
The batch is read again and `verify` run: it records what exists. A name it reports missing is
written again, record by record, only after a fresh read of that one name shows nothing **and** the
Club count equals 10 plus the recorded accounts. If the session dies between a write and `verify`,
the same read and `verify --no-ids` recover the ids.

## Verification
- Per record: the connector returns the new id; `verify` compares a fresh read with what was sent.
- Per batch: `verify` exits non-zero on any difference and the batch stays open, so the next batch
  cannot start.
- At the end: `totals ok`; Club accounts = 10 pilot + 345 new = 355; Household Account still 82;
  353 Club accounts have a parent, the two on-hold accounts have none; `created_accounts.csv` has
  353 rows (345 create, 8 link); the baseline is unchanged; the four signal counts are 0.
- Nothing in Jotform, the sheet or Apps Script is written by this plan.

## Rollback
`data/sf_prep_2026-09-30/created_accounts.csv` lists every account this plan made or changed, and
`link_targets_before.json` holds the eight pilot accounts as they were.
- A **created** account is deleted by id, and only if a fresh read shows it is this plan's: its
  Description is still the one written, it was created by Ryan's user on or after the run's start,
  and it has no Contacts, attendance, attendance batches, Monthly Reports, programme-income records
  or child accounts. Anything else is listed for Ryan, not deleted. A deleted account stays in the
  Recycle Bin for 15 days and comes back with the same id.
- Once attendance has arrived for a club, its account is no longer deleted: deleting a club
  account takes its girls' Contacts and their attendance with it.
- A **linked** pilot account gets the `ParentId` it had before (`previous_parent_id`; all eight
  had none).
- Only with Ryan's go, and never the two on-hold accounts.

## Risks
- **A name the form does not send.** The processor would create a second, partner-less Club
  account on the first submission. Mitigation: the picker comparison before and after, exact-name
  verification after every batch. Afterwards, a Club account without a parent that is not one of
  the two on-hold accounts is the signal that a form sent an unknown name.
- **Club names are never edited in Salesforce.** Staff do rename accounts there; a tidied club
  name breaks the match and the next submission creates a second account. A rename starts in the
  sheet. Many names are deliberately kept as the forms send them (capitals only, no capitals, old
  misspellings, a space before a comma).
- **The public partner sign-up page.** The Apex behind it (`signupController`, open to the site's
  guest user) returns every Account, unfiltered: 92 today including the ten pilot clubs, 437 after
  this plan. A partner who chose a club there would be filed under the Club account, and their
  Monthly Reports would be saved against the club. Whether the page shows the list as a choice
  list could not be read; Ryan looks once (step 5). The lasting fix is an Apex change outside this
  plan: leave Club accounts out of that list and out of the sign-up lookup. The same clubs would
  join the list anyway on their first submission. The Monthly Report page itself lists no accounts.
- **Two daily QuickBooks imports** book a payment on any Account whose name equals the payee. No
  club name equals a partner or payee account today; the programme-income count on Club accounts
  (step 10) is the signal.
- **The held same-name clubs are not created here.** Until their names are settled and the forms
  send them, two clubs of one name resolve to one account: on the same date the second submission
  is rejected, on different dates the two rosters mix. The forms' side settled the scheme on
  2026-09-30 ([its own plan](2026-09-30-same-name-clubs.md)):
  - two duplicates were retired that day (their rosters deactivated and removed from the forms)
    and get no account;
  - the two clubs that shared a name with them are ordinary clubs now, under their plain names
    ("Shinning Stars" of Ready for Reading, "Super Girls" of Feminature Uganda Limited): two more
    creates, added to this run with Ryan's go once the 345 are verified;
  - seven clubs will send "<club> - <partner>". Their accounts are created from the live pickers
    when the forms are switched, not before.
- **Drift after today.** A club renamed or added in the sheet reaches the forms automatically but
  not Salesforce (BACKLOG 27). Until then the SF Pending tab and the Monday e-mail are how a new
  club is noticed.
- **The update flow and the triggers.** Steps 6-8 write one record each and read everything back.
- **The run assumes a dead connection and a quiet picker.** Both are read before, right after the
  go and at the end; the Club count in every `verify` would show an account made by a submission.
- **A partial batch.** `verify` reports the missing ones; the rule above says how they are written.
- **Salesforce API limits.** About 350 writes and 80 reads, far below the org's daily limit.
- **Privacy.** No Contact is read or written; queries select Account fields and counts of children.
  One Africa club's name also appears as a line of its own roster (club code ASPIRING, a roster
  artefact for the sheet's ReviewQueue): the account is a club.

## Before the Jotform connection is switched back on (its own plan)
Found by this plan's review and carried over:
- the held same-name clubs settled on the forms and in Salesforce (the orphan roster question with
  the old Setidevi spelling, a picker option no club answered to, was deleted from all five forms
  on 2026-09-30);
- the five old forms disabled or disconnected: they are still enabled, take a typed club name and
  carry the same Salesforce mapping;
- fuzzy matching stays off (137 names have a near neighbour in the list);
- the first live submission comes from a club of 40 or more girls and its batch is read before the
  rest follow: the processor creates one Contact per girl in one transaction, the pilot proved 22,
  and 37 clubs are larger;
- the Contact duplicate rule's action is read;
- two guest-facing portal methods are hardened by whoever maintains the partner portal (details
  given to Ryan on 2026-09-30, not repeated here), before girls' Contacts arrive in volume.

## Not in this plan (on hold)
- The two pilot accounts `001RP00000nMZXfYAO` and `001RP00000mgVVMYA2` (Ryan is checking them).
- The held same-name clubs (see Risks).
- The Monthly Report checkbox, any Apex, metadata or field change, the 435 missed submissions.
- The Jotform → Salesforce reconnect: its own steps once Ryan has re-authorised the connection.

## Follow-up once everything above and the reconnect are done and verified
Ryan, 2026-09-30: build a simple Salesforce report called **"Jotform Monthly Attendance (test)"**
showing the attendance from the past month's Jotform submissions. Overall attendance for the whole
organisation is the default view; it must also slice or filter by foundation, partner and girl, to
show that those links work. It needs attendance to be flowing first (and the partner link this plan
creates), so it is its own step with its own go: how the report is created (the connector writes
records, not reports), which object it sits on, and what "foundation" maps to are settled then.

## Proof
- `python3 tools/sf_club_accounts.py build` → `write set: 345 create + 8 link = 353 writes in 18 batches; 11 same-name rows held`
- `python3 tools/sf_club_accounts.py pickers` → per region `not on the picker 0`, `options this list does not know 0`, Africa `also a roster line 1 ['ASPIRING']`, then `pickers ok`
- `precheck --all` → `precheck of all names ok`; `parents` → `parents ok: 49 partner accounts`
- after the last batch: `python3 tools/sf_club_accounts.py totals --result <saved read>` → `totals ok`
- `make check` → `CHECK PASSED`
