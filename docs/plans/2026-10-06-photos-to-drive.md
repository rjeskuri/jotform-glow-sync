---
title: The group photo never reaches Salesforce; it is kept where staff can find it, under GLOW's control
author: Claude (with Ryan's decisions of 2026-10-06)
status: in-progress      # parts 1 and 2 built 2026-10-06 (Build notes), merged into main 2026-10-09 (79208cd); the Drive set-up in the builder is Ryan's. Ryan 2026-10-06 (in conversation), with the defaults of the "Open decisions" unless noted in the plan
backlog: 68, 69, 70
created: 2026-10-06
intent: docs/intent/2026-10-06-photos-to-drive.md
---

# Plan: the group photo goes to Google Drive, not Salesforce

## Context

**The decision.** On 2026-10-01 GLOW's CEO decided that the attendance photos (one required
group photo per submission, faces visible: DECISIONS 2026-09-12) do not belong in Salesforce.
That day the photo files in Salesforce were deleted (27 files, per the conversation; the read
connector cannot see the recycle bin, so the count is unverified) and the four regional forms
stopped sending the photo. Read on 2026-10-06, read-only:

- Salesforce holds no photo from the attendance flow: 0 files are linked to any batch created
  since 2026-09-01, and the whole org created one `ContentDocument` in 2026 (February). The
  batch object has no photo field (`Attendance_Batch__c` custom fields: Account_Name__c,
  Account__c, Attendance_Date__c, Contact_IDs__c, Creator__c, Module__c, Module_Week__c,
  Module_Year__c, Processing_Status__c, Status_Message__c, enable_fuzzy_matching__c).
- The four regional forms' Salesforce action has `uploadFields: []`; **the template still has
  `uploadFields: ['19']`** (GET `/form/{id}/properties`, `integrations.salesforceV2.actionMap`,
  all five live forms, 2026-10-06). Every form's `integrations` property has exactly one key,
  `salesforceV2`.
- `tools/integration_status.py` hard-codes the photo as the wanted upload
  (`UPLOADS = ["19"]`, tools/integration_status.py:33, checked at :76-77), so today it reports
  the template `ok` and every regional form `NOT RIGHT: the upload field is [], not the Group
  Photo (q19)`, exit 1. A real mapping fault on a regional form would sit under the same red
  line until the tool's expectation is updated.
- Question 19 ("Group Photo", `control_fileupload`) is required on the template and Africa:
  one file, 10 MB, jpg/jpeg/png/gif/heic (GET `/form/262352490535154/question/19`;
  tools/update_static_fields.py:49-56 is the wanted shape). Every submission on the three
  active regional forms carries exactly one photo (Africa 212 of 212, Asia 321 of 321, Latin
  America 144 of 144; U.S 0 submissions).

**What Ryan asked: the cost.** Jotform's Google Drive integration costs **$0**. Jotform includes
every integration on every plan, the Free plan included (Jotform support, 2023-01-25:
https://www.jotform.com/answers/4807305-integration-of-dropbox-or-google-drive-for-free-users ;
the integration page calls it a free integration: https://www.jotform.com/integrations/google-drive ;
https://www.jotform.com/pricing). There is no "integration package" to buy. The same holds for
Dropbox, Box and OneDrive.

**The real cost item is Jotform's own storage cap.** GLOW's account is on the **Silver** plan
(GET `/user`: `account_type` ends in `SILVER`; GET `/system/plan/SILVER`: `limits.uploads`
10,738,466,816 bytes = 10 GiB cumulative, `limits.submissions` 2,500 a month,
`limits.totalSubmissions` 25,000, `limits.formCount` 50). GET `/user/usage` on 2026-10-06:
`uploads` 1,340,458,410 bytes = **1.25 GiB, 12.5 % of the cap**; `submissions` 474 in the cycle
that resets 2026-10-21 (`monthly_usage_reset_date`); `total_submissions` 690; `form_count` 5.
About 1.9 MB per photo (1.34 GB over 690 stored submissions). Upload space is cumulative and
account-wide; reaching it, or any monthly limit, makes Jotform disable the forms on a scheduled
date ("Form over quota"), and attendance collection stops
(https://www.jotform.com/help/408-Understanding-Your-Account-Usage-and-Limits). Copying files to
Drive frees nothing in Jotform; only deleting *and purging* submissions does, and Jotform cannot
delete just the file.

Projection (arithmetic, not a fact): at the current pace (474 submissions in the 15 days since
2026-09-21, about 950 a month, about 1.8 GB of photos a month) the account passes **50 % around
mid-December 2026, 80 % around February 2027 and the cap around mid-March 2027**; at September's
pace (484 submissions, about 0.94 GB a month) 50 % in mid-February 2027, 80 % in late May 2027,
the cap around August 2027. The submissions limit is not the problem (474 of 2,500 in the cycle).

Prices, from the API's plan records only (GET `/system/plan/SILVER` and `/GOLD`, `prices` and
`onSale.nonProfit`, read 2026-10-06):

| Plan | Upload space | Submissions / month | List | Nonprofit (50 % off) |
|---|---|---|---|---|
| Silver (current) | 10 GiB | 2,500 | $49 / month; $468 / year | $24.50 / month; $234 / year |
| Gold | 100 GiB | 10,000 | $129 / month; $774 / year | $64.50 / month; $594 / year |

The pricing page (https://www.jotform.com/pricing/ , the same day) shows Gold at "$99 / month
billed yearly" = $1,188 a year, not the API record's $774: the two sources disagree and the API's
figure may be a sale price; the bill Jotform would actually charge is read at the time of the
decision. So Gold is **+$360 a year or +$40 a month at nonprofit rates** ($594 against $234; $64.50
against $24.50), +$306 a year or +$80 a month at the API's list prices. Whether GLOW already pays
the nonprofit rate is **unverified** (billing was not read); if not, applying at
https://www.jotform.com/nonprofit/pricing/ halves the current bill too (approval in 2-3 days per
https://www.jotform.com/answers/2753099-jotform-pricing-and-non-profit-discount ). Ryan's
decision of 2026-10-06: Gold or a retention policy is decided when usage passes about 50 %;
nothing is bought now.

**What the Google Drive integration does** (help guide 192, "How to Integrate Your Form with
Google Drive", updated 2024-12-19, https://www.jotform.com/help/192/ - the guide's full slug
is refused by the repo's secrets scanner as a Drive-id lookalike; subfolder
fields: https://www.jotform.com/answers/4166365-google-drive-integration-choose-specific-folder-for-the-integration ;
nested folders not supported: https://www.jotform.com/answers/2547853-how-to-use-sub-folder-in-the-google-drive-integration ):

- set per form in the builder: Settings → Integrations → Google Drive → Authorize (a Google
  account logs in); the API cannot create it (the `integrations` property answers 200 and changes
  nothing on PUT or POST, proven 2026-09-30 on the same property for Salesforce,
  [plan](2026-09-30-salesforce-reconnect.md), "What the API cannot do");
- one **Folder Name** per form, created in the connected account's **My Drive** (Shared Drives
  are not supported; a 2026-07-15 support workaround was contradicted by another agent the same
  day: https://www.jotform.com/answers/39923771-google-drive-integration-saving-pdfs-directly-to-shared-drive — unverified, do not rely on it);
- optional **Create Subfolders for Submissions**, with a subfolder name built from Form Fields;
- two independent toggles: **Send Submission PDFs** (the PDF renders every answer, so every
  ticked girl's name and question 18) and **Send Uploaded Files**; files-only is possible;
- new submissions only; the existing 677 photos are not copied;
- the Google token can expire or be revoked (password change, session revocation) and Jotform
  raises no alarm; the remedy is to remove and re-add the integration on each affected form
  (https://www.jotform.com/answers/290275-Google-Drive-and-Spreadsheet-Integration-Error-refreshing-the-OAuth2-token ,
  https://www.jotform.com/answers/5415057-access-token-from-google-has-expired-when-integrating-google-sheets ).

Uploaded files need a Jotform login to view (GET `/user`: `loginToViewUploadedFiles` = "1"; an
upload URL answers HTTP 200 with `text/html`, the login page, with or without the APIKEY header;
https://www.jotform.com/answers/1727402-can-we-use-api-key-to-download-individual-files-without-removing-the-require-log-in-authentication ).
That rules out a repo script or Apps Script fetching the photos (it would need that setting off,
making every photo URL public, and a Drive scope in the deployed script is a rule-11 outage).
Zapier or Make would cost money at this volume and put a third processor in the path of every
submission, names included. The native integration is the only route this plan considers.

## Decisions to record (docs/DECISIONS.md, one row each)

1. **2026-10-01 (CEO): no photo in Salesforce.** The files there were deleted and the mapping's
   upload row removed on the four regional forms; the template follows in this plan;
   `tools/integration_status.py` expects **no** upload field and flags a mapped one as NOT RIGHT.
   Consequence: a photo is never re-mapped without the CEO's word; `backfill_resolve.py` still
   reads the photo URLs from Jotform (tools/backfill_resolve.py:54, :251), unaffected.
2. **2026-10-06 (Ryan): the photos go to Google Drive through Jotform's own integration**, set
   in the builder per form, template first. Policy:
   - the folders are owned by a **GLOW Workspace role account** (never a staff member's own
     account); which one is open (the account that owns the enrollment sheet and the Apps Script
     is suggested, so one departure plan covers everything);
   - **uploaded files only; the "Send Submission PDFs" toggle stays OFF** because the PDF carries
     the girls' names. Nothing in the repo can see that toggle, so this row and the RUNBOOK's
     read-back after every builder edit are the only guard;
   - **one Drive folder per form** (`Attendance photos - Africa`, `… - Asia`,
     `… - Latin America`, `… - Template`; the U.S form is being disabled under Ryan's decision 5
     of 2026-10-06 and gets no folder unless it is re-enabled);
   - **one subfolder per submission named `<Club Name> <Attendance Date>`**, from the Form
     Fields picker: the hidden question 5 (the club's Salesforce Account name, unique per club,
     `<club> - <partner>` for the seven same-name clubs) if the picker offers it, otherwise the
     Club picker (the template's q444; a different id per form: Africa q446, Asia q447, Latin
     America q452); the date is question 17. **Never question 18, never a roster**;
   - the photo stays **required** on every form (DECISIONS 2026-09-12 stands);
   - **sharing = the owner plus a short named list** (who: open, CEO / Ryan);
   - **retention: open, the CEO's decision**; until it is taken nothing is deleted from Drive;
   - the existing 677 photos stay in Jotform (no manual export unless staff ask: BACKLOG 69);
   - Jotform's "Require log-in to view uploaded files" stays on; "Auto Delete Submissions" stays
     off: `tools/backfill_resolve.py` and the daily question-18-versus-ticks comparison
     (BACKLOG 35/56) read the submissions.
3. **2026-10-06 (Ryan): Jotform's storage is watched by the repo**, not bought ahead: a
   `storage:` line in `form_status.py` and a once-per-run check in `auto_sync.py`, each of the
   two limits (cumulative upload space; submissions in the monthly cycle) judged on its own and
   named (warn at 50 %, ATTENTION at 80 % of that limit); Gold or a retention policy is decided
   when upload space passes about 50 % (BACKLOG 68).

## Files that change

- `tools/integration_status.py`: `UPLOADS = []` (:33); the message at :76-77 becomes
  `the upload field is ['19'], not [] (no photo goes to Salesforce since 2026-10-01)`; the `ok`
  line at :118-119 says `no upload` instead of `photo q19` (both f-strings index `UPLOADS[0]`
  today and would raise on an empty list, so they are rewritten, not just re-worded); the
  docstring (:7-10) says the photo is **not** mapped. `QUESTIONS` keeps `"19": "photo"`
  (:35-37): the question must still exist, it is required. New: a line per live form listing the other keys of `integrations`
  (`other integrations: none` today; after Ryan's template setup it prints the Drive block's
  key, which is how we learn it - **unverified** until then whether the block is visible in the
  property at all). Second step, once the key is known: constant `DRIVE_KEY`, a `drive: yes` /
  `drive: NO - set it up in the builder (RUNBOOK "Photos")` line, and constant
  `DRIVE_WANTED` (False during the rollout, True after: a live form without the block is then
  NOT RIGHT, exit 1). The `drive:` check is **skipped for a form whose `status` is `DISABLED`**
  (the key is in the same `/properties` answer, read 2026-10-06; the line reads
  `drive: not wanted (form DISABLED)`): the U.S form stays in `glow.forms.LIVE` when the
  [clubs-off plan](2026-10-06-clubs-off-jotform.md) disables it (step 9 there; it is not moved
  to `DEFUNCT`) and gets no Drive folder, so without the skip `DRIVE_WANTED = True` would make
  it NOT RIGHT, exit 1, for good. `DRIVE_WANTED` is set True only after the U.S form reads
  `DISABLED`.
- `test/integration_status_test.py`: `block()`'s default `uploads=("19",)` (:24) becomes
  `uploads=()`; the `test_every_other_difference_is_named` case `"the upload field is []"` (:76)
  becomes `"the upload field is ['19']": block(uploads=("19",))`; the `ok` assertion (:62)
  follows the new line; new cases for `other integrations:` and, in the second step, `drive:`
  (wanted and present; wanted and missing → NOT RIGHT; a `DISABLED` form without the block →
  `not wanted`, not a problem).
- `glow/usage.py` (new, standard library): `read_usage(client)` - GET `/user/usage`, GET
  `/user` for `account_type`, GET `/system/plan/<NAME>` for `limits` - returns a dict
  `{plan, uploads, uploads_cap, submissions, submissions_cap, reset}` (`reset` is the date only:
  the API returns `2026-10-21 00:00:00`, read 2026-10-06); `levels(u)` returns one level per
  limit, `{"uploads": …, "submissions": …}`, each `ok` / `warn` / `alarm` against
  `WARN_AT = 0.5` and `ALARM_AT = 0.8` **of that limit** (the two are not merged: upload space
  is cumulative and is what Gold or retention answers; the submissions count resets every cycle,
  and a busy month at 1,250 submissions would otherwise print "storage warn" with the storage
  unchanged); `worst(levels)` for the `!!` prefix and the exit; `storage_line(u)` renders
  `storage: upload space 1.25 GiB of 10.00 GiB (12.5%) -> ok; submissions this cycle 474 of 2,500 (19.0%, resets 2026-10-21) -> ok; plan SILVER`.
- `tools/form_status.py`: `main()` reads the usage once after building the client (:718 as of
  50126b3) and prints the storage line right after the `Roster (active girls)` line (:730),
  prefixed `!! ` when the worst level is `alarm`; every report dict gains `"storage": u` with
  `"levels"` so `--json` (:726-728, a list the runner reads as `[0]`) carries it. It is **not**
  added to `rule_problems`: the cap is account-wide, not a form problem, so no form turns NOT
  CLEAN for it. Built after session -54's `form_status.py` changes merge, after `main` is merged
  into the branch (see Order of work 6), and after (or in the same commit as) the module-shape audit
  of the sibling [module-selection plan](2026-10-06-module-selection.md), which edits the same
  `main()`.
- `tools/auto_sync.py`: `Run.check_storage(read)` next to `check_names` (:575-590 as of
  50126b3): once per run, after the regions (:693-695), `read()` wrapped so a Jotform error only
  logs `storage: could not be read` and never fails the run; logs the storage line; for each
  limit at `alarm` appends an ATTENTION naming it - `Jotform upload space at NN% - the forms
  stop at 100%` or `Jotform submissions this cycle at NN% - the forms stop at 100%` - with the
  Gold / retention choice in its detail, referred to by its BACKLOG title ("Gold versus
  retention") rather than its number (exit 2, so GitHub e-mails Ryan: RUNBOOK "Automatic sync",
  docs/RUNBOOK.md:289-290). At `warn` only the log line (a daily e-mail for months would bury
  real ATTENTIONs). `verify_report` (:292-320) is unchanged. `main()` passes
  `lambda: usage.read_usage(Client(os.environ["JOTFORM_API_KEY"]))` (the key is already
  required at :656-657), which needs two imports the file does not have today (:52-54 import
  `sheets_client`, `glow.forms` and `glow.sync.sf_name_clashes` only): `from glow.jotform import
  Client` and `from glow import usage`, both standard library, like the file's own note at :54.
  Built after session -54's `auto_sync.py` changes merge, with `main` merged into the branch.
- `test/python_test.py`: `glow.usage` with a fake client (the three GETs; the trimmed `reset`;
  `levels` at 49.9 / 50 / 79.9 / 80 % on each limit with the other at 0, so a submissions `warn`
  never shows as an uploads one; the line's wording); `AutoSyncPlan`: `check_storage` with an
  injected dict at `ok`, `warn` and `alarm` on uploads (log line only, log line only, one
  ATTENTION naming upload space), `alarm` on submissions only (one ATTENTION naming the cycle),
  and with a reader that raises (one log line, no ATTENTION, `run.failed` still False), in the
  shape of the `check_names` test (test/python_test.py:467-479); `form_status` main is not
  unit-tested today, so the storage key is covered through `glow.usage` and a `--json` smoke by
  hand.
- `docs/RUNBOOK.md`: new section **"Photos"** (below "Attendance dashboard in Salesforce"), the
  text in "The RUNBOOK section" below; one bullet in the dashboard's **Access** list
  (docs/RUNBOOK.md:1701-1711, a section session -51 owns: the one line is sent to -51 first, and
  lands in its own RUNBOOK edit if it prefers): "Photos: none in Salesforce since 2026-10-01;
  they are in Google Drive - "Photos"."; the `form_status.py` healthy lines in CLAUDE.md's
  Commands gain the storage line.
- `docs/DECISIONS.md`: the three rows above.
- `docs/BACKLOG.md`: three rows at the next free numbers, **68, 69, 70** - `main` already holds
  62-64 from session -54's merge (`3ea1cab`: the names-dictionary audit, other regions' names on
  each page, the translation-runtime watch; this worktree's base `50126b3` ends at 61) **and 65
  from -54's Result commit `9d58ce4`** (the question-18-empty resend residual), and the sibling
  module-selection plan takes 66 and 67. So `main` is **merged into the branch before
  `docs/BACKLOG.md` is edited**, and the numbers are re-checked then (renumber if another plan of
  this workflow took them). 68 Gold versus retention at ~50 % of upload space (with the
  projected dates and the nonprofit-rate question); 69 the 677 existing photos (leave, or a
  one-off manual export); 70 the Drive token watch (no alarm exists; the check is the newest
  subfolder's date).
- `.claude/skills/jotform-api/SKILL.md`, the "Salesforce" section (:167-190 as of 50126b3;
  session -54 edits this skill too, so these land after its merge), renamed "Integrations": the
  first bullet's mapping summary `(5, 17, 18, 98, 100, 102, 105, 109 + photo 19)` (:168-169)
  drops `+ photo 19` and says the upload row has been empty since 2026-10-01 (regionals; the
  template after RUNBOOK step 1); the `integrations` property is read-only for Google Drive too
  (builder only); the Drive block's key as learned (or "not visible through the API" if that is
  the finding); uploaded files need a login (`loginToViewUploadedFiles` = "1": the file URL
  answers 200 `text/html` with or without the APIKEY header); `GET /user/usage` fields
  (`uploads` bytes as a string, `submissions` in the cycle, `total_submissions`,
  `monthly_usage_reset_date` as `yyyy-mm-dd 00:00:00`, `form_count`), `GET /user`
  `account_type` = the plan URL, `GET /system/plan/<NAME>` `limits.uploads` /
  `limits.submissions` / `limits.totalSubmissions`, `prices`, `onSale.nonProfit`; `status`
  (`ENABLED` / `DISABLED`) is in `/properties`.
- `docs/ARCHITECTURE.md`: in the flow (docs/ARCHITECTURE.md:29-35) one line "the photo (q19)
  is not in the mapping since 2026-10-01; Jotform's Google Drive integration copies it to Drive
  (RUNBOOK "Photos")"; a Components row for `tools/integration_status.py` (it has none today).
- `CLAUDE.md`: no new rule; the `form_status.py` healthy tail gains `storage: … -> ok`.

Nothing in `sync_attendance_form.py`, `glow/sync.py`, `appsscript/` or Salesforce metadata
changes: the sync writes only `conditions` (sync_attendance_form.py:1194) and never touches
integrations; no qid, form id or `ROSTER_COLS` changes, so rule 7 is not engaged.

## The RUNBOOK section (what "Photos" will say)

**Photos.** Since 2026-10-01 no attendance photo goes to Salesforce (the CEO's decision). Since
<date> the photos are copied by Jotform's Google Drive integration into the My Drive of
<role account>, folder `Attendance photos - <Region>`, one subfolder per submission named
`<Club Name> <Attendance Date>`, uploaded files only, no PDF. The photo stays required on the
forms. The photos before <date> (677 by 2026-10-06) are in Jotform only, behind its login.
Sharing: the owner and <named list>. Retention: <CEO's decision, or "not yet decided: nothing is
deleted">.

*Setting it up (Ryan, in the builder; the API cannot; template first). Every builder save is a
live write to a form, so each one follows the ritual: a quiet moment with no other rollout on
the forms (for this plan's first run: **after session -54 has declared its window closed**, the
template included - it verifies the template with `form_status.py` while it rolls out), a backup
before, a re-read and compare after. The `/properties` snapshot `backup_forms.py` writes holds
`integrations`, `emails` and `conditions`, so the compare is a plain `diff` of the snapshot
before and the one after.*

1. **Template, Salesforce first**. Before: `python3 backup_forms.py` (**all** forms, not just the
   template: a change to the connected account propagates to every form, see below; note the
   stamp it prints). Then Settings → Integrations → Salesforce → the existing action (create
   `Attendance_Batch`) → remove the file upload (Group Photo) → save. **Edit the action; never
   remove the connected Salesforce account - that detaches the integration from all ten forms
   (2026-09-30).** After: `python3 backup_forms.py --form 262352490535154` and
   `diff backups/262352490535154/properties-<before>.json backups/262352490535154/properties-<after>.json`
   → the only hunks are inside `integrations` (the upload row gone); `emails`, `conditions`,
   `clearFieldOnHide` byte-identical; `python3 backup_forms.py` again for the other four and
   the same diff on each → empty. Then `python3 tools/integration_status.py` → every live form
   `ok (one action, 8 fields, Account_Name__c from q5, no upload)`, `integration: ok`. Until
   this step the template reads `NOT RIGHT: the upload field is ['19'], not []`.
2. **Template, Google Drive**. Before: `python3 backup_forms.py --form 262352490535154`. Then
   Settings → Integrations → Google Drive → Authorize → log in as the role account (never your
   own) → Folder Name `Attendance photos - Template` → Create Subfolders for Submissions ON,
   name = the "Club Name" field that is **question 5** (the hidden text field; the builder shows
   the Club picker under the same label - prefer the hidden one; if only the picker is offered,
   use it and say so in the plan's Result), a space, then "Attendance Date" → Send Uploaded Files
   ON → **Send Submission PDFs OFF** → Save. After: `backup_forms.py --form 262352490535154`
   and the diff → hunks inside `integrations` only (a block added, or nothing visible: see the
   next line), nothing else changed. Then
   `python3 tools/integration_status.py --form 262352490535154` → the `other integrations:`
   line names the Drive block, or says none (then the API cannot see it; the Drive check below
   is by eye).
3. **One test submission on the template, arranged to change nothing in Salesforce.** A
   template submission goes through the Salesforce integration like any other and is a real
   batch for a real club ([contact-ids plan](2026-09-30-contact-ids.md), build notes: "a
   delivered one is a real batch for a real club"). The processor refuses a second batch for a
   club and date that already has a Success batch, *before* it reads any name
   (`processBatch` → `resolveClubAccount` → `isDuplicateBatch` → return,
   `AttendanceBatchProcessor.cls` lines 82-96 and 116-122, the deployed copy under
   `data/sf_processor_2026-10-02/after/`): such a batch is Failed `Duplicate: …` with no
   attendance row and no Contact created. `resolveClubAccount` runs first, though, and
   **creates a partner-less Club account when question 5 matches no Account name** (:102-108,
   the BACKLOG 27 path, seen twice on 2026-10-03) - so the club must be one whose Account name
   is plain, never one of the seven `<club> - <partner>` names. Mentors submit late (19 of the
   27 duplicates since 10-01 were September dates re-sent in October) and a Success batch dated
   today is the exception (0 on the afternoon of 2026-10-06; 38 in the last three days), so the
   query is a window, not a day - read-only SOQL:
   `SELECT Account_Name__c, Attendance_Date__c FROM Attendance_Batch__c WHERE
   Processing_Status__c = 'Success' AND Attendance_Date__c = LAST_N_DAYS:3 ORDER BY
   Attendance_Date__c DESC LIMIT 5`; take the newest club + date pair whose name has no
   ` - <partner>` suffix; **never a free date**. Also read, before the submission,
   `SELECT COUNT() FROM Account WHERE RecordType.DeveloperName = 'Club' AND ParentId = null`
   (2 on 2026-10-06: the two pilots). On the template pick that club and that date, tick one
   girl (the roster is required), type your own address as the Partner Coordinator Email, and
   upload a **neutral image with nobody in it**. Open the mentor link
   (`https://form.jotform.com/262352490535154`), not the builder's preview (whether a preview
   submission runs the integrations is unverified). **Two e-mails go out with it**: the
   template's staff notification ("Notification 1", to one fixed address set in the form's
   Emails tab - it is not in the repo - with the ticked girl's name and the photo link) and the
   mentor confirmation to the address you typed. Tell the notification's recipient beforehand,
   or pause that e-mail for the test and switch it back on afterwards (whether a paused e-mail
   stays in the `emails` list is unverified; the diff of step 4 shows whatever changed and that
   it came back).
4. **Read back, within a few minutes:**
   - Drive (as the role account): folder `Attendance photos - Template` → one subfolder named
     exactly `<that club> <that date>` → one image file, **no PDF**.
   - Salesforce (read-only SOQL): exactly one new batch for that club and date,
     `Processing_Status__c = 'Failed'`, `Status_Message__c LIKE 'Duplicate:%'`, 0 `Attendance__c`
     rows (`SELECT COUNT() FROM Attendance__c WHERE Attendance_Batch__c = '<id>'`), no new
     Contact (`SELECT COUNT() FROM Contact WHERE CreatedDate = TODAY AND AccountId = '<club
     id>'` unchanged from before the test), and the partner-less Club account count unchanged
     (the query of step 3; 2 today). Then delete that one batch - Ryan's go, one write (the
     write connector or Ryan in the Salesforce UI) - and read it back as gone.
   - Jotform: `python3 tools/form_status.py --form 262352490535154 --roster <csv>` →
     `submissions 2`, CLEAN, `salesforce yes`; `backup_forms.py --form 262352490535154` and the
     diff against step 2's "after" snapshot → nothing but `count` (the submission) and, if you
     paused the notification, `emails` back to the original. Delete the test submission in
     Jotform Tables (Ryan; it frees no space for 30 days), or leave it: it holds one girl's tick
     and a test photo.
   - If the subfolder shows a name other than the club's (the picker's text, or empty): fix the
     Form Fields choice before any regional form.
5. **The regional forms**, at a quiet moment after session -54's window, smallest first: Latin
   America `262383455778067`, Asia `262383129464057`, Africa `262382821971058` (U.S skipped: it
   is being disabled). Per form: `python3 backup_forms.py --form <id>` before; the same
   settings, folder `Attendance photos - <Region>`, the "Club Name" field that is question 5 on
   that form; `backup_forms.py --form <id>` after and the diff → hunks inside `integrations`
   only; `python3 tools/form_status.py --form <id> --roster <csv>` → CLEAN. **No test
   submission on a regional form**: Asia and Africa submit many times a day, Latin America a
   few; the read-back is the first real submission's photo appearing in the form's Drive folder
   (within a day), and `python3 tools/integration_status.py --form <id>` → `drive: yes` (once
   the key is known and coded). After the last form, and once the U.S form reads `DISABLED`
   (the clubs-off plan): `DRIVE_WANTED = True` in the tool, `integration_status.py` → the
   template and three regionals `drive: yes`, U.S `drive: not wanted (form DISABLED)`,
   `integration: ok`; `form_status.py` → every form CLEAN, `salesforce yes`.
6. **When copies stop** (a subfolder dated more than a week ago is the newest while the form has
   newer submissions; or Jotform e-mails a token error): the Google token has lapsed. In the
   builder, on each affected form: Settings → Integrations → Google Drive → remove → add again
   with the same settings (step 2, backup and diff included); read back with the next real
   submission. Nothing in the repo raises an alarm for this (BACKLOG 70); look at the folders
   once a month.
7. **Storage**: `python3 tools/form_status.py --roster <csv>` prints
   `storage: upload space N GiB of 10.00 GiB (P%) -> ok; submissions this cycle N of 2,500 (P%,
   resets <date>) -> ok; plan SILVER` on its first lines. Each limit is judged on its own: `warn`
   from 50 % of it, and from 80 % the automatic sync raises an ATTENTION naming the limit every
   morning until acted on. **Upload space** is the one Gold or retention answers: at about 50 %
   of it, decide Gold (100 GiB, nonprofit $594 a year against Silver's $234) or a retention
   policy (BACKLOG 68). A **submissions** `warn` is a busy month (1,250 submissions in the
   cycle) and resets on the date printed; it means Gold's 10,000 a month, not retention. Never
   switch on Jotform's Auto Delete Submissions without reading BACKLOG 68 first.

*Rollback.* Removing the Google Drive integration from a form in the builder stops the copies;
the photos stay in Jotform and nothing else on the form changes (the before/after diff of that
save says so). The template's Salesforce upload row is re-added only on the CEO's word, with
`UPLOADS = ["19"]` put back in the tool. What is already in Drive is the owner's to delete (the
CEO's retention decision).

## Order of work

1. Commit this plan and the intent (`docs/intent/2026-10-06-photos-to-drive.md`).
2. **Repo, part 1** (no live dependency, offline): `tools/integration_status.py` `UPLOADS = []`,
   the messages, the `other integrations:` line; its test; DECISIONS rows 1 and 2; the RUNBOOK
   "Photos" section (steps 1-6, the storage step marked "after part 2"); the ARCHITECTURE line
   and row. The Access bullet goes to session -51 first (one line); it lands here or in -51's
   own RUNBOOK edit, as it prefers. `docs/BACKLOG.md` (68-70) is edited only after `main` is
   merged into the branch (62-65 are taken there) and the numbers re-checked. `make check`. Then,
   read-only against the live forms: `python3 tools/integration_status.py` → the template
   `NOT RIGHT: the upload field is ['19'], not []`, the four regionals `ok … no upload`, every
   form `other integrations: none`, exit 1: the red line now points at the one remaining builder
   step.
3. **Ryan, builder, template - after session -54 has declared its window closed** (its Result on
   `main` `9d58ce4` records every form CLEAN and `AUTO_SYNC_APPLY=1` at 11:23 UTC, so the
   condition is its confirmation, not a wait; while it rolled out on the template a builder save or a
   test submission in the middle would have changed what it verified): RUNBOOK step 1 (backup of all
   forms, unmap the photo, diff). `integration_status.py` → `integration: ok`, exit 0.
   `form_status.py --form 262352490535154` → CLEAN, `salesforce yes`.
4. **Ryan, builder, template** (same window condition as 3): RUNBOOK step 2 (backup, Google
   Drive, diff). `integration_status.py --form 262352490535154` → the `other integrations:`
   line: the key, or none.
5. **Controlled test on the template** (same window condition; RUNBOOK steps 3-4): the two
   SOQL reads first (the newest Success club + date pair with a plain Account name; the
   partner-less account count), the notification's recipient told, Ryan's submission, the
   Drive read-back (file, no PDF, the subfolder's name), the Salesforce read-back (one Failed
   `Duplicate:` batch, 0 rows, no new Contact, the partner-less count unchanged), the deletion
   of that batch on Ryan's go, the Jotform submission's fate on Ryan's go, the diff of the
   form's properties (nothing but `count`). If the subfolder name came from the wrong field, fix
   it and repeat the test the same way.
6. **Repo, part 2** (after session -54 says its window is closed and its branch is merged):
   first **merge `main` into `wf10/four-issues`** (a merge, as the sibling plans do: the branch is shared by the four plans of this day), which already carries -54's merge of
   `form_status.py`, `auto_sync.py` and SKILL.md, and re-check the BACKLOG numbers; the
   `storage:` line in `form_status.py` lands after, or in the same commit as, the
   module-selection plan's `audit_module_shape` (the same `main()`). Then `DRIVE_KEY` and the
   `drive:` line in `integration_status.py` (skipped if the block is not visible: the RUNBOOK
   then says the check is by eye); `glow/usage.py`; the `storage:` line; `check_storage` in
   `auto_sync.py`; tests; the SKILL.md notes; DECISIONS row 3; CLAUDE.md's healthy line.
   `make check`. Read-only proofs: `form_status.py` prints the storage line; `auto_sync.py` as
   a dry run logs it, every region `in-sync`, no ATTENTION (12.5 % and 19.0 % are `ok`).
7. **Ryan, builder, the three regional forms** (RUNBOOK step 5), at a quiet moment after -54's
   window: Latin America, Asia, Africa, each with its backup and diff. After each, the next
   real submission's photo in Drive and `integration_status.py --form <id>` → `drive: yes`. No
   test submission on these forms.
8. **After the U.S form reads `DISABLED`** (the clubs-off plan's step 9, Ryan's go there):
   `DRIVE_WANTED = True`, `make check`, `integration_status.py` → `drive: yes` on the template
   and three regionals, `drive: not wanted (form DISABLED)` on U.S, `integration: ok`. Fill in
   the RUNBOOK's `<date>`, `<role account>` (its role, never a password), sharing and retention
   as decided; this plan's Result; the work log.

The repo stays green after every step; nothing is written to a form, the sheet or Salesforce by
the tooling in this plan. The only writes are Ryan's builder saves (steps 3, 4, 7, each backed up
before and diffed after), his test submission (step 5) and the deletion of the one test batch
(step 5, his go).

## Open decisions (Ryan / the CEO)

1. **Which GLOW Workspace role account** owns the folders (suggested: the account that owns
   the enrollment sheet and the Apps Script).
2. **Sharing**: the named list beside the owner.
3. **Retention** in Drive: the CEO's; recorded in DECISIONS and the RUNBOOK when taken.
4. **The test submission's leftovers**: delete the Failed `Duplicate:` batch (recommended) and
   the Jotform submission (recommended; it frees no space for 30 days).
5. **Thresholds**: warn at 50 %, ATTENTION at 80 %, of each limit on its own (proposed);
   whether the daily ATTENTION from 80 % is wanted, or a weekly one (a Monday-only reminder is
   a one-line change).
6. **The U.S form**: no Drive folder while it is being disabled (proposed); the tool skips the
   `drive:` expectation on a `DISABLED` form, so re-enabling it would make the missing folder
   NOT RIGHT, which is wanted.
7. **The nonprofit rate**: is GLOW's Jotform bill already at 50 % off? (Billing was not read.)
8. **The 677 existing photos**: leave them in Jotform (recommended) or export them by hand into
   the same Drive folders (half a day of clicking and a second copy of minors' photos to govern).
9. **Gold or a retention policy**, at ~50 % of upload space (BACKLOG 68): not now.
10. **The test submission's two e-mails**: tell the staff notification's recipient and let them
    go, or pause the notification for the test (proposed: tell them; fewer builder changes to
    diff).

## Risks

- **Names reaching Drive.** The PDF toggle and the subfolder's Form Fields are hand settings the
  repo cannot see; a PDF, or a subfolder named from question 18 or a roster, would put girls'
  names in Drive. Mitigation: the DECISIONS row, the RUNBOOK's read-back after every builder
  save (step 4: no PDF, the subfolder name is the club and the date), and the template test
  before any regional form.
- **The template test reaches Salesforce.** Mitigation: the photo is unmapped first (step 3);
  the test uses the newest club + date pair that already has a Success batch (a three-day
  window, never a free date), so the processor refuses it before reading a name (verified in
  the deployed class); the club's Account name is plain, so `resolveClubAccount` (which runs
  before the duplicate check) matches it and creates no stray account; the one Failed batch and
  the partner-less account count are read back, the batch deleted on Ryan's go. If
  `isDuplicateBatch` changes under plan 2 (the Apex backstop), re-read the class before the
  test; plan 2 changes `processParticipants`, not the duplicate check.
- **The template test sends e-mails.** The staff notification (one fixed address, with the
  ticked girl's name and the photo link) and the mentor confirmation go out like for any
  submission. Mitigation: the recipient is told beforehand, or the notification paused and
  restored (RUNBOOK step 3, open decision 10).
- **A builder save changes more than it should.** The 2026-09-30 reconnect showed that removing
  the connected Salesforce account detaches the integration from all ten forms, something only
  a read of the other forms shows. Mitigation: `backup_forms.py` before every save (all forms
  before the template's Salesforce edit), the `diff` of `/properties` after (hunks inside
  `integrations` only), `form_status.py` CLEAN; the RUNBOOK says in bold never to remove the
  account.
- **A silent token lapse.** Copies stop and nothing in Jotform or the repo says so. Mitigation:
  the RUNBOOK's monthly look at the newest subfolder's date (step 6) and BACKLOG 70; the
  `drive:` line can only say the block exists, not that the token works.
- **Account ownership.** Photos of minors in a person's My Drive follow that person; Shared
  Drives are not supported. Mitigation: the role account (open decision 1), authorised by Ryan
  logged in as that account, written into the RUNBOOK.
- **The cap.** Drive solves nothing about Jotform's 10 GiB; at the current pace the forms would
  go "over quota" around March 2027 and attendance collection would stop. Mitigation: the
  storage line, the ATTENTION at 80 % of upload space, the ~50 % decision date in BACKLOG 68
  (December 2026 - February 2027 by the projection). Never Auto Delete Submissions without that
  decision: it starves `backfill_resolve.py` and the question-18 alarm.
- **The Drive block may be invisible to the API.** Then `integration_status.py` cannot report
  `drive:`; the plan's part 2 drops that line and the check stays by eye (RUNBOOK step 6).
- **Concurrent builder work.** Session -54 rolled out dropdown and translation changes on
  the same forms, the template first and then the regionals, and read each with
  `form_status.py` as it went (complete per `main` `9d58ce4`, 11:23 UTC; its confirmation that
  the window is closed is still asked for); every builder save and the test submission in this plan - the
  template's (steps 3-5) as much as the regionals' (step 7) - wait for it to declare its
  window closed, and `form_status.py` is read CLEAN after each save. The `form_status.py` /
  `auto_sync.py` / SKILL.md edits of part 2 land after `main` is merged into the branch, which carries
  -54's merge, and are sequenced with the sibling module-selection plan's `form_status.py`
  audit (Order of work 6). The Access bullet is -51's section and goes through it.
- **The hidden question 5 may not be in the Form Fields picker.** Then the subfolder uses the
  Club picker's text (the same string for all but the seven same-name clubs, whose picker entry
  is also the long name); recorded in the Result either way.
- **The storage GETs add three calls per `form_status.py` run - including each verify the
  runner performs after an apply (tools/auto_sync.py:539-544, one per applied region) - and
  three per runner run for `check_storage`.** All reads; a failure only logs a line.
- **The BACKLOG numbers move.** 68-70 are the next free numbers after `main`'s 62-65 and the
  module-selection plan's 66-67 on 2026-10-06; another plan of this workflow could take them
  first. Mitigation: the rows are written after the merge of `main`; the ATTENTION text refers to the
  item by title, not number.
- **Noticed on the way, not this plan's business**: the template's question 19 reads
  `allowMultiple: Yes` while `tools/update_static_fields.py` wants `No` (`fileLimit` is 1 and
  every submission carries exactly one file, so the effect is nil). A dry run of that tool would
  say whether the key is unapplied or ignored by Jotform.

## Proof

Before part 1 (today, read-only):

```
python3 tools/integration_status.py
template: connection 10566091 - ok (one action, 8 fields, Account_Name__c from q5, photo q19)
Africa: connection 10566091 - NOT RIGHT:
  - the upload field is [], not the Group Photo (q19)
…   (Asia, Latin America, U.S the same)
exit 1
```

After part 1 (step 2), before Ryan's template step:

```
python3 tools/integration_status.py
template: connection 10566091 - NOT RIGHT:
  - the upload field is ['19'], not [] (no photo goes to Salesforce since 2026-10-01)
  other integrations: none
Africa: connection 10566091 - ok (one action, 8 fields, Account_Name__c from q5, no upload)
  other integrations: none
…
exit 1
```

After step 3 (the template unmapped): the before/after `diff` of the template's `/properties`
snapshot shows hunks inside `integrations` only, the other four forms' diffs are empty; every live
form `ok … no upload`, `old <region>: no Salesforce integration (as wanted)` ×5,
`integration: ok`, exit 0.

After step 4: the template's `other integrations:` line names the Drive block (or `none`); its
diff again `integrations` only.

After step 5: Drive holds one subfolder `<club> <date>` with one image and no PDF; Salesforce
one Failed `Duplicate:` batch (then gone), 0 rows, Contacts and partner-less Club accounts (2)
unchanged; the template `submissions 2`, CLEAN, its diff nothing but `count`.

After part 2 (step 6):

```
python3 tools/form_status.py --roster data/roster_<date>.csv
Roster (active girls): {...} clubs per region
storage: upload space 1.25 GiB of 10.00 GiB (12.5%) -> ok; submissions this cycle 474 of 2,500 (19.0%, resets 2026-10-21) -> ok; plan SILVER
== template …  → CLEAN   (every form; salesforce yes; 0 flagged as error)

python3 tools/auto_sync.py            # dry run
…  storage: upload space 1.25 GiB of 10.00 GiB (12.5%) -> ok; submissions this cycle … -> ok; plan SILVER
  => Africa: in-sync … (every region), exit 0, no ATTENTION
```

After step 8: `integration_status.py` → every live form `… no upload`; `drive: yes` on the
template, Africa, Asia and Latin America; `drive: not wanted (form DISABLED)` on U.S;
`integration: ok`, exit 0.

`make check` → `ALL CHECKS PASSED` ×3, `py: … scripts answer --help`, `OK`, `gs: 10 files
parse`, `secrets: clean`, `docs-links: ok`, `fixtures: up to date`, `CHECK PASSED` (pasted when
done).

## Build notes (2026-10-06, parts 1 and 2 built together on the branch, offline)

- **`DRIVE_KEY`, the `drive:` line and `DRIVE_WANTED` are not built.** The Drive block's key is
  unknown until Ryan's template setup (step 4); `tools/integration_status.py` carries a marked
  TODO with the whole second step (the `DISABLED` skip included), and RUNBOOK "Photos" step 5
  says a `drive: yes` line follows once the key is known and coded.
- The `other integrations:` line prints for every live form, including one with no Salesforce
  block (the plan said "per live form"; a form that lost its Salesforce block may still carry
  the Drive one, which is worth seeing); old forms get no line.
- The upload-field message keeps its "since 2026-10-01" parenthesis only while `UPLOADS` is
  empty, so the rollback (`UPLOADS = ["19"]`) does not print a false reason.
- `glow/usage.py` refuses an answer of another shape than the one read 2026-10-06 (counts as
  strings, the plan's URL, numeric limits, a limit of 0) with a `ValueError`; `form_status.py`
  prints `storage: could not be read (…)` and puts `{"error": …}` under the report's `storage`
  key, so the runner's verify step never fails on a storage read (the plan's Risks: "a failure
  only logs a line"); `auto_sync.py` catches any exception from the reader and logs the error's
  class only.
- The storage line in `form_status.py` is read once per run, before the forms, and every report
  dict carries the same `storage` object; the printed line follows the `Roster (active girls)`
  line, which lost its trailing blank line to the storage line (the blank line now follows it).
- The DECISIONS rows (1-3), BACKLOG 68-70 and CLAUDE.md's healthy line are written. BACKLOG 65
  (session -54's Result commit) sits below the "Explicitly not planned" paragraph, outside the
  table; the build moved it into the table and the review moved it back: the attendance-totals
  plan edits that row in place, and two branches touching one line in two places is a merge
  conflict - where it sits is that track's to settle. The DECISIONS rows are filed by date (the
  2026-10-01 row before the 2026-10-02 rows), not grouped by plan. *Settled at the round-1 merge
  (2026-10-07): 65 is in the "Data-quality and small things" table, the two tracks' 66 rows are
  one (the attendance-totals wording, which knows fix 4 is live), 71 holds a reserved row for the
  clubs-off plan so 65-73 read consecutively, and the DECISIONS rows of 2026-10-06 stand in the
  order module, photos, storage, then the seven attendance-totals rows.*
- The dashboard's Access bullet was added in this branch's RUNBOOK edit (session -51 had cleared
  it before the build), and the "Automatic sync" section gained the storage paragraph.
- RUNBOOK "Photos" step 7 (storage) is written as live, not "after part 2": both parts landed in
  one branch. The `<date>`, `<role account>`, sharing and retention placeholders stay for step 8.
- Read-only proofs, 2026-10-06 afternoon: `integration_status.py` exactly as the "After part 1"
  block above (template `NOT RIGHT: the upload field is ['19'], not []`, the four regionals `ok …
  no upload`, `other integrations: none` ×5, exit 1); `form_status.py --rendered` on the five
  live forms prints the storage line (`storage: upload space 1.30 GiB of 10.00 GiB (13.0%) -> ok;
  submissions this cycle 510 of 2,500 (20.4%, resets 2026-10-21) -> ok; plan SILVER` by the
  afternoon) and every form CLEAN (the pages on new runtime builds, noted in the
  module-selection plan's Build notes). The `auto_sync.py` dry run was not run from the build worktree (it needs the sheet
  export or a Roster CSV outside the worktree and spawns four sync dry runs); `check_storage` is
  unit-tested at ok / warn / alarm per limit and with a failing reader. The runner's client for
  the three usage GETs is built with `max_time=60` (review finding: the read runs in the runner's
  own process after any apply and before the log, ATTENTION and SyncLog are written, so a stalled
  connection must become `storage: could not be read (JotformError)` within minutes, not hold the
  run to the job's 30-minute timeout).
