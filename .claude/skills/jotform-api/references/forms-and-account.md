# Jotform e-mails, properties, integrations, account limits, failure modes

Part of the `jotform-api` skill ([SKILL.md](../SKILL.md): the rules that bite most). Confirmed
against the live API and the runtime (`jotform.forms.js`); when Jotform's docs and this file
disagree, this file won.

## Emails
- Managed through the `emails` property (no endpoint); autoresponder type `"autorespond"`,
  recipient `to: "{fieldUniqueName}"`. Writing replaces the whole array — resend the existing
  notifications verbatim. Bodies cap at 65,535 chars (long default templates are truncated
  mid-HTML); the server regenerates default notification bodies when questions change.
  API-created submissions do not trigger emails.

## Properties
- Form-urlencoded `POST /form/{id}/properties` with `properties[key]=value` sets scalars (title,
  pagetitle, injectCSS); JSON `PUT` for structured ones (language, conditions).
- `injectCSS` is stored verbatim (GET returns what was sent) but the public page serves it with
  every `http:` rewritten to `//` (protocol-relative) — inside a percent-encoded SVG data URI that
  turned `xmlns='http://www.w3.org/2000/svg'` into `//www.w3.org/2000/svg` and the image never
  painted (2026-09-20). Use base64 data URIs (`tools/switcher_flags.py`). The page is served
  inside `<style id="form-designer-style">` in `<head>`, BEFORE the switcher stylesheet linked
  in `<body>`, so equal-specificity rules lose: use id-based selectors.
- **Form status.** `status` (`ENABLED` / `DISABLED`) is a key of both `GET /form/{id}` and
  `GET /form/{id}/properties` (read 2026-10-06: the five live forms `ENABLED`, the six old forms
  `DISABLED`). A disabled form's public page is Jotform's own "unavailable" page; the properties
  carry `messageOfLimitedForm`, on every form the default "This form is currently unavailable!"
  - that this property is the text the disabled page shows is unverified, and whether that page
  translates is unverified. **Writing it is UNVERIFIED until tried:** whether the form-encoded
  `POST /form/{id}/properties` with `properties[status]=DISABLED` (and
  `properties[messageOfLimitedForm]`) changes anything is not known (`integrations` answered 200
  and changed nothing; how the five defunct forms were disabled on 2026-09-30 is not recorded).
  `tools/disable_form.py --apply` takes a `backup_forms` snapshot, POSTs, re-reads both GETs and
  stops with the builder step (Settings -> Form Status) when the status did not move; record the
  result here after the first run (the U.S form, docs/plans/2026-10-06-clubs-off-jotform.md, D).

## Integrations
- Native Salesforce V2 integration, 8 mapping rows keyed to question ids
  (5, 17, 18, 98, 100, 102, 105, 109), byte-identical across the forms; it survives a clone. Its
  upload row (`uploadFields`) has been **empty since 2026-10-01** on the four regional forms (the
  CEO: no photo in Salesforce; the template follows at RUNBOOK "Photos" step 1, until then it still
  reads `['19']`); `tools/integration_status.py` expects `[]`. The club name is read from q5 and matching happens inside Salesforce. q5 is the picked
  option's text, so an option IS the Account name: a club's own name, or `<club> - <partner>`
  for a name two partners share (2026-09-30; never split it on " - ", club names contain it).
  The typed Partner box (q331) is not in the mapping (the live `salesforceV2` action map, read
  for the 2026-09-30 same-name design); only the staff notification e-mail's `{partner}` row and
  the submissions table read it.
- A question with `hidden` unset that no rule targets is shown to every mentor: q331 on Asia,
  Latin America and U.S had neither on 2026-09-30 (API read; the same design's review saw the
  box on Asia's public page). On the template and Africa the rules that Show it for a shared name
  are what kept it out of sight; with those rules gone it would appear, so the sync sets
  `hidden=Yes` once no generated rule shows it, after the conditions write.

- The `integrations` property is READ-ONLY through the API (verified 2026-09-30 on the template):
  a JSON `PUT /form/{id}/properties` of `{"properties": {"integrations": {...}}}` and a
  form-encoded `POST` of `properties[integrations][salesforceV2][...]` both answer 200 with
  `{"formID": ...}` and change nothing. The integration is set up per form in the builder;
  `tools/integration_status.py` checks the result. Removing a connected account in Jotform
  removes the integration from EVERY form that used it (all ten, 2026-09-30).
- In the builder's field list the Club picker and question 5 are both called "Club Name":
  `Account_Name__c` must read question 5 (the hidden text field), and the picker's id differs
  per form.
- **Google Drive** (docs/plans/2026-10-06-photos-to-drive.md): every integration is included on
  every Jotform plan ($0). The `integrations` property is read-only for it too: builder only
  (Settings → Integrations → Google Drive; one folder in the connected account's My Drive, Shared
  Drives unsupported; optional subfolder per submission named from Form Fields; two toggles, Send
  Submission PDFs and Send Uploaded Files - the forms want files only). Every live form's
  `integrations` had exactly one key, `salesforceV2`, on 2026-10-06; **the Drive block's key is
  not read yet** - `tools/integration_status.py` prints the other keys (`other integrations:`),
  and whether the block shows in the property at all is unverified until Ryan's template setup.
- **Uploaded files need a login**: `GET /user` `loginToViewUploadedFiles` = `"1"`; an upload URL
  answers HTTP 200 `text/html` (the login page) with or without the APIKEY header. No script can
  fetch a photo without switching that off (which would make every photo URL public).
- **Account usage and limits** (`glow/usage.py`, read 2026-10-06): `GET /user/usage` returns the
  counts **as strings** - `uploads` (bytes, cumulative), `submissions` (this cycle),
  `total_submissions`, `form_count`, `monthly_usage_reset_date` as `yyyy-mm-dd 00:00:00`;
  `GET /user` `account_type` is the plan's URL (`…/system/plan/SILVER`); `GET /system/plan/<NAME>`
  has `limits` as numbers (`uploads` 10,738,466,816 = 10 GiB, `submissions` 2,500,
  `totalSubmissions` 25,000, `formCount` 50 on Silver), `prices` and `onSale.nonProfit`. A form's
  `status` (`ENABLED` / `DISABLED`) is in `GET /form/{id}/properties` (and `GET /form/{id}`).

## Rate and failure modes
- Big forms (Africa: ~3,900 checkbox options) make `questions` GETs slow; back up only the form
  you are about to write. Gateway 504s can hide a completed write — re-GET before retrying.
