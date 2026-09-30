---
name: jotform-api
description: Verified Jotform API semantics for this project — conditions as JSON-string terms/action via PUT properties, question POST merges, translations POST replaces a language, clone resets the language list, dropdown/multi-select properties, 504-but-created. Load before writing or reviewing any code that calls api.jotform.com or reasons about how the forms behave at runtime.
---

# Jotform API — what is verified (2026-08-24 → 2026-09-01)

Everything below was confirmed against the live API and the runtime
(`jotform.forms.js`); when the docs and this file disagree, this file won.
The client conventions are in `sync_attendance_form.py` (`Jotform` class):
`curl -sS`, JSON response with `responseCode`; writes are recorded and skipped
unless `--apply`.

## Conditions
- Read: `GET /form/{id}/properties` (the `conditions` key). `GET /form/{id}/properties/conditions` 404s.
- Write: `PUT /form/{id}/properties` with JSON `{"properties": {"conditions": [...]}}`. Each
  condition's `terms` and `action` must be **JSON-encoded strings**. Writing the key replaces the
  whole array; other property keys are untouched. Ids: unique 13-digit numeric strings; keep
  `index` and `priority` sequential and equal (`build_conditions` does).
- Runtime `equals` is case-insensitive and trims outer whitespace (`JotForm.checkValueByOperator`).
- Calculations: text concatenates at top level, `[brackets]` = math; `ignoreHiddenFields: true`
  makes hidden fields contribute "" in text context (that is how one aggregate over every roster
  yields only the visible club's ticks). `operands` must list every `{qid}` in the equation or
  changes do not re-trigger. `insertAsText` / `newCalculationType` are builder-side flags.
- A field filled by a calculation can be the source of another rule (the Club picker → q5 copy).

## Questions
- `POST /form/{id}/question/{qid}` form-urlencoded `question[key]=value` **merges** properties.
- `POST /form/{id}/questions` adds; only `question[type]` is required; `control_email` needs
  `question[validation]=Email`. The response `content` is usually the new question (with `qid`),
  but can be a list — read defensively.
- Adding a question at an order another question holds **inserts** it there: that question and
  the block below it move down by one, up to the first gap (seen in the snapshots: the Club
  picker created at 3 on the template 2026-09-01 moved 351 questions; Africa 2026-09-12 the
  same, the shift stopping at a gap). Adding at an empty order moves nothing. Equal orders
  render in creation order (qid), so code must be right under both (`glow/layout.py`).
- Moving an existing question by posting `question[order]` is unobserved until the roster-order
  repair (`tools/fix_roster_order.py` writes only to empty orders and probes after its first
  write); record here what the template repair shows.
- Dropdown `calcValues` has a leading empty slot for the placeholder:
  `len(calcValues.split('|')) == len(options.split('|')) + 1`.
- Dropdown with `multipleSelections=Yes` renders Jotform's own searchable component (the
  `searchText` property is its placeholder, `visibleOptions` the rows shown). `maxSelection` /
  `minSelection` are checkbox-only and are silently dropped on dropdowns.
- Hidden fields (`hidden=Yes`) are still submitted and still reach the integrations; validation
  (`required`) is skipped while a field is hidden.

## Images and other assets
- There is NO upload endpoint: `control_image`'s `src` can only point at an already-hosted file
  (verified against the docs and Jotform's own answers, 2026-09-24). The builder's uploader puts
  files at `https://www.jotform.com/uploads/<account>/form_files/<name>.png`, and that URL works
  as an `src` on any form. `/form/{id}/files` lists SUBMISSION uploads, not form assets.
- `width` / `height` / `align` on the question are the display size; `text` is the file's
  basename and is not shown to a mentor (q13 is in `add_translations.py`'s `NEVER_SHOWN`).
  Ship a 2x file and set width/height to half of it, or phones render it soft.

## Emails
- Managed through the `emails` property (no endpoint); autoresponder type `"autorespond"`,
  recipient `to: "{fieldUniqueName}"`. Writing replaces the whole array — resend the existing
  notifications verbatim. Bodies cap at 65,535 chars (long default templates are truncated
  mid-HTML); the server regenerates default notification bodies when questions change.
  API-created submissions do not trigger emails.

## Clone
- `POST /form/{id}/clone` may 504 at the gateway on big forms but still creates the clone (check
  `/user/forms`; one clone per attempt). The clone copies translated strings but **resets** the
  `language` property (the offered-languages list) to English (US) and leaves `pagetitle` as
  "Clone of …" — `tools/restore_translations.py`, then `properties[pagetitle]`.

## Translations (undocumented, working)
- `GET /form/{id}/translations` → `{lang: {md5(englishText): translated}}`; the `en` and `base`
  entries hold the source texts (including every checkbox option — i.e. every girl's name).
- `POST /form/{id}/translations` with the same shape **replaces each posted language's whole
  dictionary** — always GET, union, then POST (135 strings per language were lost once). PUT
  returns an HTML 504 page.
- Keys are the md5 of the plain English text; the runtime resolves element text → key through
  `base`, so a new string must be added to `base` and `en` (md5 → English) as well, or its
  translations never apply. Re-POST `properties[pagetitle]` to force a re-render.
- Text elements (`control_text`) are translated by element id: key `text_<qid>`, value = the
  translated inner HTML.

## Properties
- Form-urlencoded `POST /form/{id}/properties` with `properties[key]=value` sets scalars (title,
  pagetitle, injectCSS); JSON `PUT` for structured ones (language, conditions).
- `injectCSS` is stored verbatim (GET returns what was sent) but the public page serves it with
  every `http:` rewritten to `//` (protocol-relative) — inside a percent-encoded SVG data URI that
  turned `xmlns='http://www.w3.org/2000/svg'` into `//www.w3.org/2000/svg` and the image never
  painted (2026-09-20). Use base64 data URIs (`tools/switcher_flags.py`). The page is served
  inside `<style id="form-designer-style">` in `<head>`, BEFORE the switcher stylesheet linked
  in `<body>`, so equal-specificity rules lose: use id-based selectors.

## Salesforce
- Native Salesforce V2 integration, 8 mapping rows keyed to question ids
  (5, 17, 18, 98, 100, 102, 105, 109 + photo 19), byte-identical across the forms; it survives a
  clone. The club name is read from q5 and matching happens inside Salesforce.

## Rate and failure modes
- Big forms (Africa: ~3,900 checkbox options) make `questions` GETs slow; back up only the form
  you are about to write. Gateway 504s can hide a completed write — re-GET before retrying.
