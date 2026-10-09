---
title: Attendance reports and dashboard visible to every internal user - the two folders shared, one permission set, "(test)" dropped
author: Claude (with Ryan's decisions of 2026-10-09)
status: blocked          # built and validated check-only 2026-10-09 (0AfRP000002gXhZ0AU, 5 of 5, 0 errors; after the review's fixes); waiting for Ryan (deploy, refresh schedule, assignment)
backlog: 60
created: 2026-10-09
intent: none - Ryan's decisions of 2026-10-09 in conversation (DECISIONS); BACKLOG 60
---

# Plan: the attendance reports and dashboard for all internal users

## Context
- **What is live**: the dashboard "Jotform Attendance (test)" (`01ZRP00000BE2TR2A1`, 19
  components) and 13 reports in the two "Attendance" folders. This is `totals1/`, deployed by
  Ryan 2026-10-07 03:59 UTC (DeployRequest `0AfRP000002gLJp0AM`). It is documented on branch
  `wf10/four-issues` (commit `63019bb`: RUNBOOK "Attendance dashboard in Salesforce" and the plan
  `2026-10-06-attendance-totals.md`), which is not merged yet. On `main` the RUNBOOK still
  describes the 12-component dashboard of 2026-10-06; `after2/` is no longer what is live.
- **Today's verification (2026-10-09, about 04:05 UTC, read only)**: the live state was
  retrieved into `data/sf_dashboard_2026-10-02/verify_2026-10-09/`.
  - Every report figure equalled SOQL: 374 comparisons, read 3 times. All 54 of 54 dashboard
    values equalled SOQL.
  - Jotform and Salesforce matched girl for girl on 612 sessions, 0 unexplained.
- **Found and fixed the same morning**: two partner-less Club accounts, "Shining Stars (Kawempe
  Youth Centre)" `001RP00000yjrLpYAI` and "Genious Girls" `001RP00000yk7aFYAQ`. Both belong to
  Kawempe Youth Center and are on the roster since 10-08. Claude set their ParentId to
  `001RP000002nJZaYAM` through the write connector at about 04:59 UTC, on Ryan's go, and read them
  back. The partner-less Club accounts are again exactly the two known ones.
- **Open**: `BATCH-000500` (Niñas Emprendedoras y Empoderadas, submitted 2026-10-04) carries the
  session date 2026-03-09, probably 3 September typed day first. It stays as it is until the club
  confirms (BACKLOG 60 (7); a guard on the forms: BACKLOG 79).
- **`SF_SYNC` cannot be switched on yet**: none of its setup exists as of 2026-10-09 (the GLOW
  Sync user, the GLOW Club Sync permission set, the External Client App, the GitHub secrets
  `SF_CLIENT_ID` / `SF_CLIENT_SECRET`). BACKLOG 27.
- **Ryan's decisions of 2026-10-09** (DECISIONS):
  1. Share both "Attendance" folders as **Viewer** with **All Internal Users**. This reverses his
     2026-10-06 "folder sharing stays as it is" (RUNBOOK "Attendance dashboard in Salesforce" →
     Access; BACKLOG 60 (1)). Girls' names inside Salesforce stay fine for anyone with Salesforce
     access (his 2026-10-06 call, unchanged).
  2. One new permission set for the 9 active users with the profile "GLOW Standard User", so a
     chart's click-through report shows them what the chart counts.
     - One of the 9 (`005RP000000qearYAA`) is **"Portal Login", a shared login account, not a
       person**. Ryan chose to include it with the set as built: View All on Account and on
       Contact, assigned to all 9. He accepted that this shared account sees every Account and
       Contact.
  3. Drop "(test)" from the two labels; every DeveloperName stays.
  4. A daily scheduled refresh of the dashboard.

## The facts this rests on (read only, 2026-10-09)
- **Folders**: report folder `00lRP000006FVpdYAG` and dashboard folder `00lRP000006FVpeYAG`, both
  `AccessType = Hidden`. The Analytics folders API (`GET /folders/{id}/shares`) returns
  `"shares": []` for both, so nobody but users with View All Data sees them today.
- **What the folders hold, so what the share opens**: besides the 13 `totals1` reports and the
  dashboard, the **March pilot**: the dashboard "Attendance" (`01ZRP000009XJjR2AW`) and 5 reports
  ("Attendance By Club By Date", "Attendance By Club By Participant", "Last 60 days New
  Participants", "Last 60 days RAW Jotform Data", "Last 60 days New Club Accounts Report"). A
  folder share covers everything in the folder, so these become visible too. They are unchanged
  by this plan. The permission set covers their fields too (after the review; Risks).
- **"All Internal Users"** is the group `AllInternalUsers` (`00G6A000000iMLWUA2`, Type
  `Organization`). The org has no portal groups and no roles. The three guest users are not
  internal, so they are never in it.
- **How Salesforce writes such a share**: two folders in this org are already shared as Viewer
  with All Internal Users (`ActivityReports`, `Activities`). Retrieved read only, both are exactly:
  ```xml
  <folderShares>
      <accessLevel>View</accessLevel>
      <sharedTo>AllInternalUsers</sharedTo>
      <sharedToType>Organization</sharedToType>
  </folderShares>
  ```
  with no `accessType` element, and their `Folder.AccessType` still reads `Hidden`. So
  `AccessType` is not the measure of sharing; the shares API is.
- **Record visibility**: Account and Contact are **Private** (internal and external).
  `Attendance__c` is controlled by its parent (master-detail `Contact__c`).
  `Attendance_Batch__c` is Public Read/Write. All 368 Club accounts are owned by System
  Administrators, and there are no sharing rules.
- **The 9 active GLOW Standard Users**:
  - The profile has Read and Edit on Account and Contact, without View All. It has no Read on
    `Attendance__c` or `Attendance_Batch__c`. It has Run Reports.
  - The 8 staff also hold `Portal_User_Login_Access`, which gives **Modify All on Account and
    Contact** (so View All on both). That was already the case before this plan; it is not a
    change. The ninth, the shared "Portal Login" account, does not hold it.
  - Checked with `UserRecordAccess`, read only: one of the 8 can read 200 of 200 sampled Club
    accounts. "Portal Login" can read 0 of 200 Club accounts and 0 of 200 club Contacts.
- **So View All on Contact alone does not reach "Portal Login".** The six per-girl reports
  (`Accounts_Contacts_Attendance`) and the three club lists (`AccountList`) start from the Account,
  and a report shows only the Accounts its viewer can read. "Portal Login" would see empty reports
  behind full charts.
  - So the permission set also gives **View All on Account**, as the 8 staff already have
    through `Portal_User_Login_Access`.
  - Claude added it to Ryan's list. **Ryan accepted it on 2026-10-09**, for the shared account
    too (Context, decision 2).
  - The narrower alternative, a sharing rule (Club accounts, Read, All Internal Users, with
    Contact access Read), was not chosen.
- **The fields the reports use**: read from the live retrieve. Every column, filter, grouping,
  time frame, cross filter, chart, custom formula and dashboard filter column of **all 18 reports
  and both dashboards** in the folders, the pilot items included, was listed. Each was checked
  against `sf sobject describe` (which fields take a field permission). The list is under "What
  changes".
- **The report types**: `Accounts_Contacts_Attendance` and `Attendance_Totals` both have
  `<deployed>true</deployed>` (retrieved read only into the backup), so non-administrators can run
  reports on them.

## What changes (four metadata files and one new one; Ryan deploys)
Built in `data/sf_dashboard_2026-10-02/public_2026-10-09/` (its own `sfdx-project.json`), from a
fresh retrieve of what is live (`before_public_2026-10-09/`). Nothing under `data/` is committed.

1. **`ReportFolder` Attendance** and **`DashboardFolder` Attendance**: the retrieved file plus the
   `folderShares` block above (View, `AllInternalUsers`, `Organization`). Nothing else changes.
2. **Report `Attendance/Jotform_Monthly_Attendance_test`**: `<name>` changes from "Jotform Monthly
   Attendance (test)" to "Jotform Monthly Attendance". The DeveloperName stays.
3. **Dashboard `Attendance/Jotform_Attendance_test`**: `<title>` changes from "Jotform Attendance
   (test)" to "Jotform Attendance". The DeveloperName stays, and so do its 19 components, filters
   and running user (Ryan: the dashboard keeps showing the whole organisation).
4. **New permission set `Attendance_Report_Viewer`** ("Attendance Report Viewer", no licence):
   - **Objects**:
     - Read on `Attendance__c` and `Attendance_Batch__c`;
     - Read and **View All** on Contact (Ryan's list);
     - Read and **View All** on Account (added by Claude, accepted by Ryan 2026-10-09; above).
     - Nothing to create, edit or delete.
   - **Field Read** (read only, never edit): 21 fields, every field the reports and dashboards in
     both folders use that takes a field permission:
     - `Attendance__c`: `Account__c` (the join of "Clubs With No Attendance Last Month"),
       `Attendance_Batch__c`, `Attendance_Date__c`, `Creator__c`, `Module__c`,
       `Module_Week__c`, `Module_Year__c`, and for the pilot report "Attendance By Club By
       Participant" `Present__c`;
     - `Attendance_Batch__c`: `Account__c` (the partner via lookup, the join of both "Clubs Not
       Submitting" reports), `Attendance_Date__c`, `Creator__c`, `Girls_Present__c`,
       `Processing_Status__c`, `Status_Message__c`, and for the pilot report "Last 60 days RAW
       Jotform Data" `Contact_IDs__c`, `Module__c`, `Module_Week__c`, `Module_Year__c`,
       `enable_fuzzy_matching__c`;
     - `Account`: `ParentId` (the Partner column, filter, grouping and dashboard filter). The
       profile already grants it; it is in the set so the set works on any profile;
     - `Contact`: `Contact_Role__c` (the pilot report "Last 60 days New Participants").
   - **Used but outside field permissions**: `describe` says `permissionable` false, so they are
     readable with the object:
     - the Name fields, Contact `FirstName` / `LastName`;
     - `Attendance__c.Contact__c` (master-detail);
     - `Attendance_Batch__c.Account_Name__c`: required (`<required>true</required>`, nillable
       false). "Blank Submissions" filters on it with filter logic, and no permission can hide
       it;
     - Id, `CreatedDate`, `CreatedById`, `LastModifiedDate`, `LastModifiedById`, `OwnerId`,
       Account `RecordTypeId` and `LastActivityDate`.
     The derivation and the describe output are kept in `public_2026-10-09/evidence/`.
   - Why every filter field matters: a viewer without a filter field's permission gets that
     filter dropped silently (no filter logic), or "Invalid Report" (with filter logic). All the
     per-girl reports filter on `Creator__c`, so without it a viewer's click-through totals would
     include the March pilot rows.
   - **Built and validated here only. Assigning it is a record write**, done later by Claude's
     main session on Ryan's go, or by Ryan (Setup → Permission Sets → Attendance Report Viewer →
     Manage Assignments), never by the build.

Unchanged:
- the other 12 reports, the report types and the pilot items;
- the processor, the forms and every record.

### The daily refresh (not deployable: Ryan's step)
**It cannot be deployed.**
- The Metadata API's `Dashboard` type has no field for a refresh schedule. The local CLI's type
  definitions (jsforce `schema.d.ts`) and Salesforce's Dashboard type description were checked.
  The nearest fields are `runningUser`, `dashboardResultRefreshedDate` and the read-only
  `numSubscriptions`.
- No other metadata type in the CLI's registry (source-deploy-retrieve 13.4) holds a dashboard
  schedule or subscription.
- A schedule is a scheduled job: `CronTrigger` / `CronJobDetail`, `JobType` 3 "Dashboard
  Refresh" (Classic) or A "Reporting Notification". These can be queried and retrieved, not
  deployed. On 2026-10-09 the org has no dashboard-refresh job and one unrelated reporting
  notification.
- In Lightning the schedule is the dashboard's **Subscribe**: Daily, Weekly or Monthly at a chosen
  hour. The e-mail to the subscriber can be switched off. The permission is "Subscribe to
  Dashboards", which the System Administrator profile has.
- In Classic it is Refresh ▾ → Schedule Refresh (needs Schedule Dashboards). On this Enterprise
  Edition org, one scheduled refresh per hour slot, run within 30 minutes of the chosen time.
- A dynamic dashboard cannot be scheduled. This one is not dynamic: it runs as a specified user.
- It runs as the dashboard's running user, Ryan. If that user is deactivated, the refresh stops.

So it is **Ryan's step after the deploy**: daily at 05:00, America/Los_Angeles. That is the org's
time zone and Ryan's, the zone in which "last month" and "this month" roll over. The subscriber
is Ryan; no other recipients unless leadership wants the e-mail.

## Does a folder deploy replace the folder's shares?
**Not documented either way.**
- Salesforce's FolderShare documentation lists the values (`accessLevel` View / EditAllContents /
  Manage; `sharedToType` ... `Organization`: "All internal users have the specified access level
  to the folder").
- It says FolderShare is **ignored during package installation**. It says nothing about whether a
  Metadata API deploy replaces a folder's shares or adds to them.
- The documented replace and add wording belongs to another API: the Analytics REST
  `/folders/{id}/shares`, where PUT replaces and POST appends.
- `sharedTo` = `AllInternalUsers` is not in the doc text either. It is what this org writes
  (above) and what Salesforce's own sample repositories use.

**Today it makes no difference.** Both folders have no shares, so after the deploy each has
exactly the one share in the file under either behaviour.

For later:
- A later deploy of these folders must start from a fresh retrieve, which carries the shares, so
  it keeps them either way.
- The rollback removes the share in the UI, which works either way.
- Do not count on deploying the share-less backup folder files to remove it.

## Order of work
1. Commit this plan (branch `wf11/reports-public`).
2. Back up what is live into `data/sf_dashboard_2026-10-02/before_public_2026-10-09/`, read only:
   the 13 reports, the report types `Attendance_Totals` and `Accounts_Contacts_Attendance`, the
   dashboard, the pilot dashboard and its 5 reports, and `ReportFolder:Attendance` /
   `DashboardFolder:Attendance`. The `totals1` items
   must equal `verify_2026-10-09/` (else stop: something was deployed since).
3. Build `public_2026-10-09/`: copy only the four changed files from the backup and edit them,
   then write the permission set.
4. **Prove the difference**: `diff -r` of each copied file against its backup shows only the two
   labels and the two `folderShares` blocks. The permission set is the only new file.
5. Check-only deploy from `public_2026-10-09/`: `sf project deploy start --dry-run -o glow -d
   force-app`, with the JSON written to a file. 0 errors, 5 components. Nothing changes in the
   org.
6. Docs on the branch: RUNBOOK (Access), BACKLOG 27 / 60 / 79, DECISIONS, this plan's Result;
   `make check`.
7. Ryan: the steps below.

## Steps for Ryan (VPN off)
1. **Before the deploy, as "Portal Login"** (`005RP000000qearYAA`, the shared account; Setup →
   Users → Login): the Attendance folders are not listed under Reports or Dashboards. This is the
   "before".
2. **Deploy**:
   ```bash
   cd ~/jotform-glow-sync/data/sf_dashboard_2026-10-02/public_2026-10-09
   sf project deploy start --dry-run -o glow -d force-app    # check only, once more
   sf project deploy start -o glow -d force-app              # the deploy: 5 components
   ```
3. **Schedule the refresh**: open "Jotform Attendance", then **Subscribe** (Lightning). Choose
   Frequency Daily, 05:00 (your time zone, America/Los_Angeles). Untick the e-mail if you do not
   want it, and add no recipients unless leadership wants the e-mail. In Classic the same is
   Refresh ▾ → Schedule Refresh. It refreshes as the running user, you.
4. **Login As a GLOW Standard User, before the permission set**. Use "Portal Login", which has
   none of `Portal_User_Login_Access`.
   - The folders and the dashboard are visible, with the dashboard's full numbers (it runs as
     Ryan).
   - A chart's report does not open ("insufficient privileges"), or shows no rows. This user has
     no Read on `Attendance__c` and sees no Club account.
5. **Assign the permission set** to the 9 GLOW Standard Users. Do it yourself, or give Claude's
   main session the go (a record write).
6. **Login As the same user, after**:
   - Click "Girls who attended last month": the report's total equals the tile.
   - Its Partner filter still works: pick one partner.
   - "Clubs With No Attendance Last Month" lists clubs.
   - "Total Attendance Last Month" shows the partner column filled.
   - Repeat the first check as one of the other 8 users.
7. Tell Claude. Claude then reads back, read only:
   - the retrieve equals `public_2026-10-09/`, apart from Salesforce's normalisation;
   - the shares API lists one share per folder;
   - the scheduled job exists (`CronTrigger`).

## Rollback
- **Labels**: deploy the two files from `before_public_2026-10-09/` (the report and the dashboard).
- **Shares**: in each folder, Share → remove "All Internal Users". Or `DELETE
  /services/data/v62.0/folders/{id}/shares/{shareId}` (the id from a GET of `/shares`). Do not
  rely on deploying the share-less folder files from the backup: whether a deploy removes a
  share is not documented.
- **Permission set**: remove its assignments, then delete it (Setup, or a `destructiveChanges.xml`
  with `PermissionSet: Attendance_Report_Viewer`).
- **The refresh schedule**: Subscribe → Unsubscribe (Classic: Schedule Refresh → Unschedule).

## Verification
- The check-only deploy succeeds: 5 components, 0 errors, no tests (no Apex).
- The diff shows only the two labels, the two `folderShares` blocks and the new permission set.
- After Ryan's deploy and assignment: the Login As checks above, then Claude's read-back.
- `make check` → `CHECK PASSED` (docs only; no code changes).

## Risks
- **The pilot items open up too**: the pilot dashboard "Attendance" and its 5 reports sit in the
  same folders, so every internal user sees them. The pilot dashboard runs as a specified user and
  shows its numbers to anyone who opens it. Its reports run as the viewer.
  - After the review, the permission set also covers the pilot reports' fields, so their columns
    show for a viewer: `Attendance__c.Present__c`, the batch's `Contact_IDs__c`, its module
    fields and `enable_fuzzy_matching__c`, and `Contact.Contact_Role__c`.
  - "Last 60 days RAW Jotform Data" shows the names lists (`Contact_IDs__c`), which is allowed
    inside Salesforce.
  - Moving the pilot items into an admin-only folder is a separate step, if Ryan wants it.
- **Wider data than the reports**: View All on Contact and on Account opens every Contact and
  Account to these 9 users: donors, households and organisations as well as clubs and girls.
  - That is in reports, list views and search, not only in the attendance reports.
  - The 8 staff already had more than that (Modify All).
  - For the shared "Portal Login" account it is new. Ryan accepted it (2026-10-09). Whoever knows
    that login sees every Account and Contact.
  - The permission set gives nothing to edit.
- **All Internal Users** includes the two integration users and the Chatter Free user. Chatter
  Free cannot open reports. Guest users are never in the group.
- **Users not on GLOW Standard User** (System Administrators) see everything already; nothing
  changes for them.
- **The dashboard shows org-wide numbers to every internal user**, also before they hold the
  permission set: it runs as Ryan. That is the intent: the permission set only makes the
  click-through agree with the tile.
- **A new staff user** sees the dashboard, but empty or refused click-throughs until assigned
  `Attendance_Report_Viewer` (RUNBOOK → Access).
- **Descriptions**: the test report's description still starts "Test report:". The labels-only
  decision keeps it as it is.

## Result (2026-10-09, build and check-only; nothing deployed, no record written)
- **Backup** (05:14 UTC, read only): `data/sf_dashboard_2026-10-02/before_public_2026-10-09/`.
  - It holds 24 files: the 13 reports, the report types `Attendance_Totals` and
    `Accounts_Contacts_Attendance` (the second retrieved after the review, 05:2x UTC; both
    `<deployed>true</deployed>`), the dashboard, the pilot dashboard and its 5 reports, and both
    folders.
  - The 15 `totals1` files are byte-identical to `verify_2026-10-09/`, so nothing was deployed
    since this morning.
  - Both folder files hold only `<name>Attendance</name>`: no shares.
- **Build**: `data/sf_dashboard_2026-10-02/public_2026-10-09/` has 5 components, and
  `diff_vs_live.txt` beside them. Against the backup:
  - each folder file gains only the 5-line `folderShares` block;
  - the report changes only line 101, `<name>`: "Jotform Monthly Attendance (test)" → "Jotform
    Monthly Attendance";
  - the dashboard changes only line 793, `<title>`: "Jotform Attendance (test)" → "Jotform
    Attendance";
  - the permission set is the only new file.
- **The field list was derived by a script** (`evidence/derive_fields.py`; its output is
  `evidence/field_derivation.txt`, and `evidence/describe_fields.txt` holds the describe):
  - It maps every token of the 18 reports and the 2 dashboards to its field: columns, filters,
    groupings, time frames, cross filters, charts, custom detail formulas and dashboard filter
    columns. The first pass covered the 13 Jotform reports only and found 14 fields. The review
    asked for the pilot items too, and this pass covers them.
  - It keeps the fields `describe` marks permissionable: 21. That is the 14 plus the review's 7,
    nothing else.
  - The permission set equals that list exactly: no field extra, none missing. 0 tokens are
    unmapped.
  - 22 used fields take no field permission (listed under "What changes").
    `Attendance_Batch__c.Account_Name__c` is one of them: its field definition, retrieved read
    only, says `<required>true</required>`.
- **First check-only deploy** `0AfRP000002gXeL0AU` (05:15:53-05:15:58 UTC): 5 of 5, 0 errors,
  with 14 fields. It is superseded by the one after the review (below).
- **Check-only deploy after the review** `0AfRP000002gXhZ0AU` (05:29:55-05:30:00 UTC), `sf project
  deploy start --dry-run -o glow -d force-app`: Succeeded, checkOnly, 5 of 5 components, 0
  errors, 0 tests.
  - ReportFolder Attendance: changed.
  - Report `Attendance/Jotform_Monthly_Attendance_test`: changed.
  - DashboardFolder Attendance: changed.
  - Dashboard `Attendance/Jotform_Attendance_test`: changed.
  - PermissionSet `Attendance_Report_Viewer`: created.
  Both JSON outputs are beside the build (`checkonly_<id>.json`).
- **Read after the check-only, nothing changed**: both folders still have `"shares": []`, the two
  labels still carry "(test)" (unchanged LastModifiedDate), and no `Attendance_Report_Viewer`
  exists.
- **Settled on the way**:
  - Schedule Refresh is not deployable (above).
  - A folder deploy's replace or add behaviour is not documented (above).
  - `AllInternalUsers` / `Organization` is how this org itself stores a Viewer share with All
    Internal Users.
- **Not verified, and only after Ryan's steps**:
  - that the deploy gives exactly one share per folder;
  - that "Portal Login" and a staff user see rows after the assignment (Login As);
  - that the refresh job appears.
