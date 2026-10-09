# Jotform translations and clones

Part of the `jotform-api` skill ([SKILL.md](../SKILL.md): the rules that bite most). Confirmed
against the live API and the runtime (`jotform.forms.js`); when Jotform's docs and this file
disagree, this file won.

## Translations (undocumented, working)
- `GET /form/{id}/translations` → `{lang: {md5(englishText): translated}}`; the `en` and `base`
  entries hold the source texts (including every checkbox option — i.e. every girl's name).
- `POST /form/{id}/translations` with the same shape **replaces each posted language's whole
  dictionary** — always GET, union, then POST (135 strings per language were lost once). PUT
  returns an HTML 504 page.
- Keys are the md5 of the plain English text; the runtime resolves element text → key through
  `base`, so a new string must be added to `base` and `en` (md5 → English) as well, or its
  translations never apply. Re-POST `properties[pagetitle]` to force a re-render.
- The `base`/`en` entries are also what a ticked girl's name passes through on its way into
  question 18 ([conditions.md](conditions.md)): a stale spelling there is a defect in Salesforce, not a cosmetic one. A
  saved store holds every girl's name: save it mode 600 (`glow/translations.py` `save_store`).
- Jotform's own runtime texts (`JotForm.texts`, e.g. the required message "This field is
  required.") are translated the same way: `formTranslation.v2.js` builds its dictionary as
  `dictionary[lang][base[md5]]`, so without the `base` entry nothing translates, whatever the
  languages hold. Read 2026-10-01: key `9303c9bd…` is in 11 languages on every form but in `base`
  on U.S only, so the message is English on the other four (BACKLOG 57). The server never
  localises it (the served `JotForm.texts.required` is English with any `Accept-Language`).
- Text elements (`control_text`) are translated by element id: key `text_<qid>`, value = the
  translated inner HTML.

## Clone
- `POST /form/{id}/clone` may 504 at the gateway on big forms but still creates the clone (check
  `/user/forms`; one clone per attempt). The clone copies translated strings but **resets** the
  `language` property (the offered-languages list) to English (US) and leaves `pagetitle` as
  "Clone of …" — `tools/restore_translations.py`, then `properties[pagetitle]`.
