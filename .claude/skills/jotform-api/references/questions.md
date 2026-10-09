# Jotform questions, dropdowns, required and hidden fields, images

Part of the `jotform-api` skill ([SKILL.md](../SKILL.md): the rules that bite most). Confirmed
against the live API and the runtime (`jotform.forms.js`); when Jotform's docs and this file
disagree, this file won.

## Questions
- `POST /form/{id}/question/{qid}` form-urlencoded `question[key]=value` **merges** properties.
- `POST /form/{id}/questions` adds; only `question[type]` is required; `control_email` needs
  `question[validation]=Email`. The response `content` is usually the new question (with `qid`),
  but can be a list — read defensively.
- Adding a question at an order another question holds **inserts** it there: that question and
  the block below it move down by one, up to the first gap (seen in the snapshots: the Club
  picker created at 3 on the template 2026-09-01 moved 351 questions, and q5 is now 4 on all
  five forms; Africa 2026-09-12 the same, the shift stopping at a gap). Adding at an empty order
  moves nothing. Equal orders render in creation order (qid), so code must be right under both
  (`glow/layout.py`; the club guard's warning is created at the picker's order + 1).
- Moving an existing question by posting `question[order]` to an EMPTY order keeps exactly the
  value sent and moves nothing else (verified 2026-09-30 by the roster-order repair on all five
  forms: 45 writes, each probe `q2 holds order N as sent; no other order changed`, each re-read
  verified). The public page renders by the new order at once. Posting onto a TAKEN order is
  still unobserved — `tools/fix_roster_order.py` writes only to empty orders.
- A request body never goes on curl's command line: Linux refuses one argument over 131,072
  bytes and a form's rules pass that (Africa about 153 KB, the template 244 KB since the club
  guard). `glow/jotform.py` sends JSON bodies on standard input (`--data-binary @-`); the Mac
  has no per-argument limit, so only the GitHub runner would have failed.
- Dropdown `calcValues` has a leading empty slot for the placeholder on a single-select:
  `len(calcValues.split('|')) == len(options.split('|')) + 1`; the served `<option value="">Please
  Select</option>` carries no `data-calcvalue` and every other option the next value (the year
  dropdown q94 `|1|2|3`, the session dropdowns `|1|…|8`). **The module dropdowns** (q14, q92, q93,
  single-selects) get their own options in that layout from the sync (`glow/sync.py`
  `MODULE_CALC_VALUES`, 2026-10-02): question 98's copy then reads the `data-calcvalue`, which a
  browser's "Translate page" does not rewrite (it rewrote the visible text in 30 of Latin
  America's 111 September submissions). A multi-select renders no
  placeholder but still wants the slot: with `PICKER_CALC_LEADING_EMPTY = True`
  (`glow/sync.py`) every rendered option's `data-calcvalue` equals its `value` — verified
  2026-09-30 by `form_status.py --rendered` on all five forms (359/12/39/96/216 options, 0
  different). The calculation copy into question 5 then reads the calcValue.
- Dropdown with `multipleSelections=Yes` renders Jotform's own searchable component (the
  `searchText` property is its placeholder, `visibleOptions` the rows shown). `maxSelection` /
  `minSelection` are checkbox-only and are silently dropped on dropdowns.
- Hidden fields (`hidden=Yes`) are still submitted and still reach the integrations; validation
  (`required`) is skipped while a field is hidden.
- **Required + hidden** (each question has `required` "Yes"/"No"; `POST /question/{qid}` with
  `question[required]=Yes` merges, or it goes in the create payload). Read in the runtime
  2026-09-30 and proven in headless Chrome 2026-10-01 on local copies of three forms (nothing
  submitted): `init` puts `novalidate` on the form, so the HTML `required` attribute is inert. At
  submit `validateAll` runs `validateInput` on every `[class*="validate"]` input, and that returns
  true without checking when the field's `<li>` (or its section) carries `always-hidden` or
  `form-field-hidden` (`showField` removes both): a roster a rule hides is never checked. A
  checkbox fails only when no box of its `<li>` is ticked, so one tick satisfies a required roster,
  and a change on a box re-validates, so the error goes with the first tick. Served markup of a
  required field: `<li class="form-line jf-required …">`, the label's `*`, each input
  `validate[required]` plus `required=""`. Live precedent: the module and session dropdowns are
  hidden + required and submissions arrive with them hidden, so the server takes a hidden
  required field empty. A required **checkbox** had not been rendered on these forms before
  2026-10: `form_status --rendered` counts the roster boxes carrying `validate[required]`.

## Images and other assets
- There is NO upload endpoint: `control_image`'s `src` can only point at an already-hosted file
  (verified against the docs and Jotform's own answers, 2026-09-24). The builder's uploader puts
  files at `https://www.jotform.com/uploads/<account>/form_files/<name>.png`, and that URL works
  as an `src` on any form. `/form/{id}/files` lists SUBMISSION uploads, not form assets.
- `width` / `height` / `align` on the question are the display size; `text` is the file's
  basename and is not shown to a mentor (q13 is in `add_translations.py`'s `NEVER_SHOWN`).
  Ship a 2x file and set width/height to half of it, or phones render it soft.
