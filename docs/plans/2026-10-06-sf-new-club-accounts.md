---
title: Salesforce club accounts created automatically for new clubs (BACKLOG 27)
author: Claude (with Ryan)
status: accepted (Ryan, 2026-10-06) - in-progress
created: 2026-10-06
intent: none - Ryan's request of 2026-10-06 ("look at doing the salesforce clubs records automatically")
---

# Plan: the automatic sync creates a new club's Salesforce account

## Context
- **New clubs reach the forms automatically.** sheet → `Dispatch.gs` → GitHub Actions →
  `tools/auto_sync.py`, 30-60 seconds after enrollment.
- **Their Salesforce Club account is made by hand.** The SF Pending tab and the Monday e-mail
  list it, and somebody creates it on Ryan's go.
- **What happened on 2026-10-03.** "Change Makers" and "Seeds of Greatness" (WESAD) first
  submitted 43 hours after enrollment, before anyone had created their accounts and before the
  Monday e-mail.
  - The attendance processor matches question 5 against every Account name. It found none, so
    it made two name-only Club accounts **without a partner**.
  - The clubs then dropped out of the dashboard's Partner filter until a hand fix on 10-06.
  - With fuzzy matching on, a club without an account can even land on a similar-named account.
    That is why the accounts exist *before* the first attendance (DECISIONS 2026-09-30).
- **Goal**: when the sync puts a new club on a form, it first creates the club's account.
  - Named exactly as question 5 will send it.
  - Club record type, with its partner as parent.
  - Every run also checks every club's account and says what needs a person. It writes nothing
    else.

## The facts this rests on (read-only, 2026-10-06; three reviews)
- **auto_sync.** In `Run.region()` the dry-run summary has `creates` and `sf_names`, the exact
  question-5 string per roster. A club refused for its name is never in `creates`. `check_bands`
  caps forms at 5 creates per region. The job runs on every roster change, daily, and by hand, in
  concurrency group `auto-sync`.
- **The processor's match** (Apex, read-only):
  - question 5 trimmed of characters ≤ U+0020, compared with `equalsIgnoreCase` against
    `SELECT Id, Name FROM Account LIMIT 5000`;
  - any record type, no order, first match wins;
  - it runs synchronously in the batch's after-insert trigger.
- **The org:**
  - 448 Accounts; 366 Club, 364 of them with a parent.
  - No Account duplicate rule. Only `Name` required. No validation rule fires on `Name`,
    `RecordTypeId`, `ParentId`, `Description`.
  - Account sharing is **Private**, with no sharing rules or roles.
  - 354 Club accounts carry "GLOW club code <code>;" in Description: one code each, none
    repeated.
  - 49 partners, each with exactly one parent today. Four differ in name from the sheet (GLF
    Rwanda, Fundación Bibliotec, Angelo Patri, HOLBROOK).
  - Every active club has exactly one account today: `ok 364`.
- **Login.**
  - Nothing unattended exists: the `glow` login is Ryan's CLI, and Jotform runs as Ryan.
  - New connected apps are disabled (Spring '26), so it must be an **External Client App** with
    the client credentials flow.
  - Free: 4 "Salesforce Integration" user licences and 5 "Salesforce API Integration" permission
    set licences. That permission set licence can grant View All on Account (Salesforce Help).
  - API use is about 2 calls a run plus 3 per create, against 114k of 116k a day free.
- **The freeze rule** (Salesforce Help 005318944). Anonymising VPNs, proxies and "high-risk IPs"
  get a user frozen; this cannot be configured or allowlisted.
  - Cloud traffic has not triggered it here. GitHub runner addresses are unclassified.
  - A dedicated user contains it: Jotform (Ryan) is unaffected, and admins get an e-mail.
- **Edit needs ownership.** With Private sharing, Edit plus View All lets a user edit only what it
  owns. Repairing a processor-made account (owned by Ryan) would need Modify All on every Account,
  so v1 does not repair; it reports.
- **The dispatch token.** The sheet's `SYNC_DISPATCH_TOKEN` (Script Properties, readable by every
  sheet editor) has Contents read/write. It could push code to `main` and dispatch a run that sees
  the Salesforce secret. Branch protection and Environments need GitHub Pro.

## Design (v1: create only, report everything else)

### Salesforce and GitHub setup (Ryan; click-by-click in the RUNBOOK)
1. **User** "GLOW Sync": Salesforce Integration licence, profile "Minimum Access - API Only
   Integrations". Assign the "Salesforce API Integration" permission set licence first.
2. **Permission set** "GLOW Club Sync":
   - Account: Read, Create, **View All**. View All is required: the step must see every name the
     processor matches against.
   - Fields: `ParentId`, `Description`.
   - Record type: Club.
   - Nothing else: no Edit, no Contact, no attendance.
3. **External Client App** "GLOW Sync":
   - OAuth client credentials flow, Run As "GLOW Sync";
   - Permitted Users "Admin approved users are pre-authorized", with the permission set in its
     policies;
   - scope `api` only, no refresh token, a short session timeout;
   - no login IP ranges (runner addresses change).
4. **Dispatch token**, closing the path above: `Dispatch.gs` calls
   `POST /repos/…/actions/workflows/auto-sync.yml/dispatches`, with a new fine-grained token that
   has **Actions: write only**. The old Contents token is revoked.
   - This is a small Apps Script change with no new Google service, so no new OAuth scope (rule
     11 does not apply). It needs a `clasp push`.
   - `workflow_dispatch` gains a `reason` input in place of the dispatch payload.
5. **GitHub**:
   - secrets `SF_CLIENT_ID` and `SF_CLIENT_SECRET`, entered by Ryan on the web page or
     `gh secret set` from stdin; never in a Claude session (rule 2);
   - repository variable **`SF_SYNC`** = `off` | `plan` | `apply` (default `off`).

### Code
**`glow/salesforce.py`**: `Org` moves here from `tools/sf_backfill.py`, which then imports it.
- It keeps the tested paging, the 401 re-login, "status 0 = outcome unknown" and error-code
  reduction.
- Login is pluggable:
  - `cli_login` for the Mac tools, as today;
  - `client_credentials_login` for CI: credentials in the POST body; an opener that **refuses
    redirects**, so Authorization is never re-sent elsewhere; exceptions carry only
    `error`/`error_description`, never a body.
- The token is revoked at the end of the run.
- The API version is one shared constant.
- **No fallback**: CI never uses the CLI login, and the Mac tools never use client credentials,
  so a local run can never write as "GLOW Sync".

**`glow/sf_partners.csv`** (committed): `partner,sf_account_id`, 49 rows taken from today's
unanimous state. The step checks every id on each run: it must be visible, Household type and
without a parent of its own. A partner not in the file gets ATTENTION: "add one line"
(BACKLOG-27 procedure in the RUNBOOK).

**`tools/sf_new_clubs.py`**: pure decisions, plus `main(argv, org=None)` for tests.
- `sf_match(a, b)`: the processor's semantics exactly.
- **Read** (paged): Id, Name, RecordTypeId, ParentId, Description, CreatedById of every Account.
  - **Completeness guard**: `done` is true; records = `totalSize` = `SELECT COUNT() FROM Account`;
    Accounts ≥ 400; Club accounts ≥ active clubs − 5; every mapped parent present. Otherwise:
    no write, ATTENTION "visibility lost?".
  - ATTENTION when Accounts > 4,500 (the processor's LIMIT 5000).
  - The read stays in memory: never written to disk or an artifact, never printed except names
    equal to a question-5 name.
- **Create**, only for this region's within-band `creates`, decided before any write
  (all-or-nothing, ≤ 5 per region). Each must pass all of these:
  - its club code (the Roster's `girl_id` prefix) is in no account's Description. If it is, that
    is a rename not yet made in Salesforce: ATTENTION "rename the account first", no create;
  - no Account of any type `sf_match`es the name. Otherwise ATTENTION before the apply;
  - the name uses only characters proven end-to-end (letters including accented, digits, space,
    `- . ( ) ' /`). Otherwise ATTENTION with the body for a hand create;
  - the partner is in `sf_partners.csv`;
  - the name is not in a `check_names` clash.
- **The write**: re-query by name just before the POST. Body: `Name` = the question-5 string
  exactly, `RecordTypeId` = Club, `ParentId`, `Description` = "GLOW club code <code>; created by
  the automatic sync <date>".
- **Read back**:
  - by Id: Name character for character, record type, parent, Description;
  - by name: exactly one Account.
  - A mismatch or an unknown outcome is ATTENTION, and that region gets no further write.
- **Writes are never retried** (`with_retry` wraps reads only).
- **Check, every run, all active clubs, read only.** Each club's question-5 name must match
  exactly one Account: a Club, under the mapped parent, carrying the club's code where one
  exists. Otherwise ATTENTION, with the one-record fix printed for a hand fix on Ryan's go:
  - no account (a club added while `SF_SYNC` was off, or a rename);
  - a partner-less Club not on hold (the processor won the race);
  - the name on a non-Club account (logged by Id);
  - two accounts;
  - another parent (a partner move);
  - a code under another name.
- **Never**: update, rename, delete, set an owner, touch a Contact or attendance, or create for a
  club not in this run's applied creates.

**`tools/auto_sync.py`**
- `plan_from_summary` keeps `partner` in creates.
- Both apply calls pass `--summary-json`, and `sf_names` is taken from the apply's summary.
- **Per region**, after `check_bands` passes and **before** backup and apply, the region's creates
  run as above.
  - The form applies whatever Salesforce answered. A club is never kept off a form because
    Salesforce is down; the end-of-run check reports it.
  - Regions in `dry-run`, `attention` or `failed` get no create.
- **After `check_names`, before `append_synclog`**, the check runs, wrapped in a catch-all so any
  error becomes ATTENTION, never a lost SyncLog.
- **`SF_SYNC` controls the step:**
  - `off`: the step is skipped, with one log line and no login;
  - missing secrets: "SF: not configured", no ATTENTION;
  - `plan`: reads only; every would-be create is ATTENTION with its body, so a person creates it
    that day;
  - `apply`: writes, with the flag **`--apply-salesforce`**, which `live_gate.sh`'s `--apply`
    pattern catches.
- **One SyncLog row**: region "Salesforce"; mode = `SF_SYNC`; creates = accounts created;
  result from the existing values. `SYNC_LOG_COLS` does not change.
- `Run.cmd` strips `SF_*` from the environment of child processes.
- **SF Pending**: with `apply` and `--synclog` only, mark `done (auto <date>)` on the rows of clubs
  the step created this run.
  - Joined by (partner, club); columns found by header; the row re-read just before the write.
  - Mentor columns are never logged.
  - A Python copy of the columns, with a parity test against `FormHandlers.gs` `SF_PENDING_COLS`,
    and a row in ARCHITECTURE's "change both" table.
  - The 38 rows pending today are closed by Ryan by hand, separately.

**`.github/workflows/auto-sync.yml`**:
- `permissions: contents: read`;
- `SF_CLIENT_ID`/`SF_CLIENT_SECRET` in the Sync step's env only;
- `--apply-salesforce` only when `vars.SF_SYNC == 'apply'`, and on a manual run only with the apply
  box ticked;
- the `reason` input (setup step 4).

**`scripts/check_secrets.py`**: rules for Salesforce access tokens (`00D…!…`), External Client App
consumer keys (`3MVG9…`) and 64-hex consumer secrets, in either case.

## Files that change
- `glow/salesforce.py`: new, `Org` moved here plus client credentials.
- `tools/sf_backfill.py`: imports `Org`; no behaviour change.
- `glow/sf_partners.csv`: new, 49 partner → account id.
- `tools/sf_new_clubs.py`: new, the decisions and the check.
- `tools/auto_sync.py`: per-region create, end-of-run check, `SF_SYNC`, summaries from the
  applies, SF Pending marking, env stripping.
- `.github/workflows/auto-sync.yml`: secrets, `SF_SYNC`, permissions, the `reason` input.
- `appsscript/Dispatch.gs`: the workflow-dispatch endpoint (clasp push).
- `scripts/check_secrets.py`: three Salesforce rules.
- `test/sf_new_clubs_test.py`: new; `test/sf_backfill_test.py` adjusted for the move;
  `test/python_test.py` imports.
- `docs/RUNBOOK.md`:
  - "Club accounts in Salesforce": setup, `SF_SYNC`, each ATTENTION and its fix, rotating the
    secret, a freeze, off-boarding;
  - "Automatic sync": the step;
  - the dashboard "Access" sentence on owners.
- `docs/DECISIONS.md`: a row amending 2026-08-24 "no custom SF client": a bounded automated
  writer, create only, ≤ 5 per region, clubs being put on a form.
- `docs/ARCHITECTURE.md`: tools table; "change both": SF Pending columns.
- `.claude/skills/live-systems/SKILL.md`: the writer and `SF_SYNC`.
- `CLAUDE.md` rule 1: `--apply-salesforce`, `gh variable set SF_SYNC`,
  `gh workflow run auto-sync.yml -f apply=true`.
- `docs/BACKLOG.md`:
  - 27: closed by v1; adopt and rename stay manual, by decision; the Monday e-mail keeps its SF
    Pending section;
  - 53: the hook patterns for `gh variable set` and `gh workflow run` (Ryan's file).

## Order of work
1. Commit this plan.
2. Move `Org`, write the new code and tests; `make check` green. Nothing is live: `SF_SYNC` is
   unset, so the step is off.
3. **Ryan**:
   - Dispatch token switch: the new token and the `clasp push` of `Dispatch.gs`, at a quiet
     moment; then a sheet edit that must trigger a run.
   - Then the Salesforce setup and the GitHub secrets.
4. **`SF_SYNC=plan`, then a manual run, read only.** It must show:
   - login ok;
   - the completeness guard passing (Accounts 448, Club 366);
   - Account describe: createable `Name`, `ParentId`, `Description`, `RecordTypeId`, and the Club
     record type available;
   - every mapped parent visible;
   - `ok 364`, `create 0`.
   - Cross-check from Ryan's `glow` login: `UserRecordAccess` for "GLOW Sync" is Read on a
     Ryan-owned Club and a partner account.
5. **Plan mode for at least 7 days**, closed by: zero login failures, and at least one "would
   create" body equal, character for character, to the account a person then created from it.
   This mode alone closes the 10-03 gap, as an ATTENTION within minutes.
6. **Ryan sets `SF_SYNC=apply`.** Until the first create is checked, each create also raises a
   one-line ATTENTION: "created, check by hand".
7. **The first real create**, checked from the `glow` login:
   - Name, record type, parent, Description, owner "GLOW Sync", Contacts 0;
   - its first attendance batch's `Account__c` is that account, and no new partner-less Club
     appears;
   - the dashboard's Partner filter shows it.

## Rollback
- **Stop**: `SF_SYNC=off` stops future runs; a run already started is cancelled in Actions.
- **Access**: turning the External Client App off, or deactivating "GLOW Sync", removes it.
- **Undo creates**: accounts made by the step are listed with
  `WHERE CreatedById = '<GLOW Sync id>'`. One is deleted only while it has no Contacts and no
  attendance, on Ryan's go.
- **Dispatch**: revert `Dispatch.gs` and restore the Contents token.

## Risks
- **"GLOW Sync" frozen** (runner IPs):
  - creates stop, and ATTENTION says so;
  - admins get Salesforce's e-mail;
  - an admin unfreezes it, or Ryan sets `SF_SYNC=off` if it repeats (repeated tries mean repeated
    containment);
  - forms and Jotform are unaffected.
- **The first create is the first time NPSP's and Mailchimp's Account triggers run as a
  minimum-access user.** This cannot be proven read-only. If a trigger refuses, the create fails
  as ATTENTION, the form still applies, and the processor makes the account as today.
- **The race with the processor**: a submission inside the seconds between the create and the
  form apply finds the account, which is fine. One before the create cannot happen, because the
  club is not on the form yet.
- **Names in two places.** A rename or a partner move stays manual: rename or re-parent the
  account first (RUNBOOK). The code check and the end-of-run check catch the drift.
- **Accepted for all club accounts on 09-30**: the public sign-up page lists every Account, and
  QuickBooks matches payees by Account name.
- **The dashboard's Partner filter** is hand-typed: a new partner still needs adding there.
- **Size**: about 700-900 lines with tests and docs.

## Proof
- `make check` → `CHECK PASSED`, with tests (fictional names, a `FakeOrg` using the processor's
  match semantics) for:
  - every create condition;
  - every check verdict;
  - the band;
  - the completeness guard;
  - a rename (code under another name);
  - an `attention` region with a question-5 change creates nothing;
  - an `applied-with-problems` region creates;
  - a write is never retried;
  - read-back mismatch;
  - login failure or freeze → ATTENTION while the forms still apply;
  - `off`/`plan`/`apply`;
  - no redirect followed;
  - the secret and the token never in any output (including the error paths);
  - the SF Pending parity test.
- Step 4's run log lines, pasted into this plan.
- Step 7's read-back, pasted into this plan.
