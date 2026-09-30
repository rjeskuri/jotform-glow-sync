---
title: Monthly Report in Salesforce - the "attendance submitted electronically" checkbox
author: Claude (with Ryan)
status: done (deployed to production 2026-09-30 13:26 UTC; open: which other profiles see the field)
created: 2026-09-30
intent: none - Ryan's request of 2026-09-30, wording confirmed by GLOW leadership
---

# Plan: Monthly Report - the electronic-attendance checkbox

## Context
Jotform is now the main source of attendance. Partners still file a Monthly Report in Salesforce,
and its second section asks for weekly attendance counts by hand. GLOW leadership confirmed the
change on 2026-09-30:

- At the top of section 2, one checkbox, not required, worded exactly:
  "Click here if you have confirmed all mentors submitted attendance electronically for this month.
  This does not apply to EEFY, TLM, and Ng’aa Maskani."
- Below it a warning: "Do not fill this out unless you are part of EEFY, TLM, or Ng’aa Maskani".
- The checkbox and the other attendance questions of section 2 are optional.

EEFY, TLM and Ng'aa Maskani are the three partners without Jotform access; they keep counting by hand.

## What the form is (read 2026-09-30, nothing changed)
- Visualforce page `Dhis2Vf` on the public site, Aura app `DHIS2App`, Lightning web component
  `dHIS2Forms`, Apex `dHIS2Controller` (`getContactRecord`, `getDhisRecord`,
  `saveOrUpdateDhisRecord`), object `DHIS2__c`, record type `Monthly_reports_new`. The Apex was last
  deployed on 2026-09-23 by another administrator, so somebody else is actively working on it.
- The component's source cannot be read through the connector. Its layout, labels and styles were
  read from the compiled component the public site serves to any visitor; the Apex through the
  read-only connector.
- Sections, by their ribbons: General Information; Curriculum Completion & Content (section 1);
  **Girls' Reach (section 2)**; Implementation Monitoring (section 3); GLOW of the Month (section 4).
- Section 2 today: "How many girls attended GLOW Club EACH WEEK according to the attendance
  rosters?" with five week panels of seven count + date pairs (`Week_N__c`, `Week_N_attended_*`,
  `Week_N_date_*`), then `Why__c`, `Girls_in_programming_participate__c` and
  `Additional_Information_Section_2__c`.
- **Nothing in section 2 is required today**: no input carries `required`, the save has no check,
  the Apex has none, and every field is nillable. "Optional" is already true; the change adds no
  rule. One side effect to know: a week count left empty is **saved as 0**, not as blank (the
  component sends `0`, and `putNumber` turns blank into 0).

## The change
1. **Field** on `DHIS2__c`: checkbox `Attendance_submitted_electronically__c`, label
   "Attendance submitted electronically", default unchecked; visible to the internal profiles and
   on the Monthly Report layout.
2. **Component** `dHIS2Forms`, first thing inside the Girls' Reach card: the checkbox with the
   exact wording, then the warning as a red-edged note directly above the weekly question (so
   "this" reads as the weekly counts, not the checkbox). Both apostrophes typographic, as the
   form's own "Girls’ Reach". Loaded from and saved to the new field. No input becomes required.
3. **Apex** `dHIS2Controller`: the field in `getDhisRecord`'s SELECT; set in
   `saveOrUpdateDhisRecord` (`'true'` → checked, anything else unchecked). The class runs without
   sharing and without field checks, so the site's guest profile needs no new permission.
4. **Tests**: `dHIS2ControllerTest` / `dHIS2Controller_Test` get one case each way; production
   deploys run them.

Preview (a mock-up built from the live layout, sent to Ryan 2026-09-30): the scratch file
`monthly-report-section2-preview.png`. It is not a screenshot of the live form.

## Order of work
1. Ryan's user is unfrozen and his network no longer triggers the freeze
   ([back-fill plan](2026-09-30-september-backfill.md), "The freeze").
2. Ryan tells the administrator who deployed on 09-23: one change is coming, no parallel deploy.
3. Retrieve the component, the two Apex classes and the object with the Salesforce CLI; keep the
   retrieved originals as the rollback.
4. Edit the four parts above.
5. If Ryan has a login to the `dev` sandbox (it exists: its site answers), deploy there first and
   take the real screenshot there. Otherwise `sf project deploy validate` against production
   (runs the tests, changes nothing).
6. With Ryan's go, at a quiet moment: deploy to production. Then open the form as a partner, take
   the screenshot, save one report on a test account, read the field back, remove the test record.

## Risks
- **Two people deploying one component.** The other administrator's next deploy from their own
  copy would silently remove the checkbox. Step 2 is the only guard.
- **Production deploy without a sandbox run** if Ryan has no sandbox login: the validate step and
  the tests are the safety net; rollback is redeploying the retrieved originals (the field can stay).
- **The CLI login froze Ryan's user once** (2026-09-30). Not repeated until the cause is removed.
- **Reports that read the weekly counts** will show 0 for partners who tick the box and skip the
  weeks. Whether empty should be stored as blank instead is Ryan's decision (not in this change).

## Found on the way (not part of this change)
- The production component sends a visitor who is not logged in to the **sandbox** login page
  (`globalglow--dev.sandbox.my.salesforce-sites.com/LoginPageevf`) instead of production's
  (checked in a browser 2026-09-30). A partner who logs in there is in the sandbox. One line in
  the same component; fix it in the same deploy only if Ryan says so.
- `dHIS2Controller.getContactRecord` returns any Contact by id to a guest (known; told Ryan
  2026-09-30).

## Proof
- The form shows the checkbox and the warning at the top of Girls' Reach (screenshot).
- A saved report has `Attendance_submitted_electronically__c` = true; an untouched one false.
- The Apex tests pass in the deploy; a report saved without any weekly count still saves.

## Result (2026-09-30)
Ryan's decisions: straight to production; leave the sandbox-login redirect; no coordination with the
other administrator. His user was unfrozen at 12:50 UTC and the command-line login made with the VPN
off (13:14 UTC).

- Retrieved from production: the component `dHIS2Forms`, `dHIS2Controller` and its three test
  classes. Copies as they were and as deployed: `data/sf_monthly_report_2026-09-30/before` and
  `after` (not committed; the rollback is redeploying `before`).
- Deployed 13:26:31 UTC (validation 0AfRP000002fgtN0AQ, then quick deploy 0AfRP000002fgwb0AA), five
  components: the field `DHIS2__c.Attendance_submitted_electronically__c` (checkbox, default
  unticked), the component (checkbox and warning at the top of Girls' Reach; loaded and saved), the
  controller (field in the read, set on save from `'true'`/`'false'`, left alone when the form does
  not send it), one new test in `dHIS2ControllerTest`, and the field's read/edit permission on the
  System Administrator profile only.
- The deploy ran the three test classes: 12 tests, 0 failures, controller coverage 99%.
- Found while testing: the controller reads three fields back after the save
  (`Did_you_implement_GLOW_Club_last_month_f__c`, `Adapted_to_the_local_culture_or_context__c`,
  `GC_sessions_did_you_observe_last_month__c`); on an existing report a save that does not send
  them fails. The form always sends them, so partners are not affected; the new test sends them too.
- Proof: the live form, opened with the test account's link, shows both additions
  (`data/sf_monthly_report_2026-09-30/monthly-report-girls-reach-LIVE.png`, sent to Ryan). Not done:
  a save through the live form itself (the automated test covers save, read-back and untick).
- Open: other profiles that should see the field; whether an empty week should be stored as blank
  instead of 0.
