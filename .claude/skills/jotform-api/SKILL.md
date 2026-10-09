---
name: jotform-api
description: Verified Jotform API and runtime semantics for this project's forms - conditions, questions, translations, calculations, properties, integrations and account limits, with the traps that have cost data before. Load before writing or reviewing code that calls api.jotform.com, or before reasoning about how the forms behave at runtime.
---

# Jotform API — what is verified (2026-08-24 → 2026-10-06)

Confirmed against the live API and the runtime (`jotform.forms.js`); when Jotform's docs and
these files disagree, these files won. The client is `glow/jotform.py` (`Client`;
`sync_attendance_form.py`'s `Jotform` class is a form-scoped view of it): `curl -sS`, a JSON
answer with `responseCode`; every write is recorded and skipped unless `--apply`.

## The rules that bite most
- **Conditions** are read from `GET /form/{id}/properties` (the `conditions` key;
  `/properties/conditions` 404s) and written with JSON `PUT /form/{id}/properties`
  `{"properties": {"conditions": [...]}}`, each condition's `terms` and `action` a
  **JSON-encoded string** (`glow.sync.rule_parts` decodes them). The write **replaces the whole
  array**: the sync regenerates every rule (CLAUDE.md rule 3).
- **`POST /form/{id}/translations` replaces each posted language's whole dictionary.** GET the
  store, save it, merge, POST, re-read (`glow/translations.py`; 135 strings per language were
  lost once). A new English string needs its `base` and `en` entries (md5 → English) too.
  `PUT` answers an HTML 504.
- **`POST /form/{id}/question/{qid}`** (form-encoded `question[key]=value`) **merges**
  properties. Adding a question at a taken order inserts it and pushes the block below down to
  the first gap; moving one to an empty order moves nothing else.
- **A clone resets the `language` property** (the offered languages) to English (US) and leaves
  `pagetitle` "Clone of …": `tools/restore_translations.py`, then `properties[pagetitle]`.
- **The rule walk**: the runtime reverses the rules, so **index 0 runs last**; showing or hiding a
  field never re-runs a calculation and **nothing recalculates at submit**. A calculation over
  fields that rules show or hide comes first (the Contact_IDs sum is rule 0: `CONTACT_IDS_FIRST`).
- **`clearFieldOnHide` at submit**: unless it is `dontClear` (the live value is `disable`), every
  input inside a `.form-field-hidden` element is emptied before sending; `always-hidden` fields are
  not touched.
- **Runtime `equals`** is case-insensitive and trimmed on a text box or single-select; on the
  multi-select Club picker only `equals` (exact, case-sensitive), `notEquals`, `isEmpty` and
  `isFilled` are evaluated, the rest silently skipped.
- **Dropdown `calcValues` has a leading empty slot**: `len(calcValues.split('|')) ==
  len(options.split('|')) + 1` (the placeholder); the picker keeps it too
  (`PICKER_CALC_LEADING_EMPTY`).
- **The `integrations` property is read-only** through the API: a PUT or POST answers 200 and
  changes nothing; the Salesforce and Google Drive integrations are set up in the builder.
  Removing a connected account removes the integration from every form.
- **A 504 can hide a completed write**, a clone included (check `/user/forms`): re-GET before
  retrying.
- **A request body goes on standard input** (`--data-binary @-`), never on curl's command line:
  Linux refuses an argument over 131,072 bytes and a form's rules pass that.
- The `emails` property write replaces the whole array (resend the others verbatim); hidden fields
  are still submitted and skip `required`.

## Checking a form
`python3 tools/form_status.py --roster data/roster_<date>.csv --partners data/partners_<date>.csv
[--form <id>] [--rendered]` (read-only; `--roster` is required). Every `form_status --rendered`
in the references means this command with `--rendered`.

## References (everything else, verbatim)
| File | Holds |
|---|---|
| [references/conditions.md](references/conditions.md) | Conditions: read/write, runtime operators, rule types, the rule walk, `clearFieldOnHide`, the loop limit, calculations, the checkbox reader, the dictionary lookup |
| [references/questions.md](references/questions.md) | Questions: merge, insert at an order, moves, the body size, `calcValues`, multi-select dropdowns, hidden and required fields; images |
| [references/translations.md](references/translations.md) | Translations (store shape, replace semantics, `base`/`en`, runtime texts, text elements); clones |
| [references/forms-and-account.md](references/forms-and-account.md) | E-mails, properties (`injectCSS`, form status), integrations (Salesforce, Google Drive, uploads behind the login), account usage and plan limits, rate and failure modes |
