# Jotform conditions, the rule walk and calculations

Part of the `jotform-api` skill ([SKILL.md](../SKILL.md): the rules that bite most). Confirmed
against the live API and the runtime (`jotform.forms.js`); when Jotform's docs and this file
disagree, this file won.

## Conditions
- Read: `GET /form/{id}/properties` (the `conditions` key). `GET /form/{id}/properties/conditions` 404s.
- Write: `PUT /form/{id}/properties` with JSON `{"properties": {"conditions": [...]}}`. Each
  condition's `terms` and `action` must be **JSON-encoded strings**. Writing the key replaces the
  whole array; other property keys are untouched. Ids: unique 13-digit numeric strings; keep
  `index` and `priority` sequential and equal (`build_conditions` does).
- Runtime `equals` is case-insensitive and trims outer whitespace (`JotForm.checkValueByOperator`)
  — on a text box or single-select. **A multi-select dropdown** (the Club picker,
  `<select multiple>`) is different (read 2026-09-29 in the runtime, build ef085979a40): only
  `equals` ("this exact option is selected", exact and **case-sensitive** on the option's value),
  `notEquals`, `isEmpty`, `isFilled` are evaluated; `contains`, `lessThan` and the rest are
  silently skipped; there is no count-selected operator. A rule spelling a club unlike its
  option never fires (Africa's "SUPER GIRLS" vs "Super Girls"), so the sync writes every
  picker term in the picker's own spelling and `form_status` flags any other.
- Rule types: `field` rules Show/Hide (Hide works on the Submit button, `control_button`;
  several Hide rules on one field combine — Show does not re-show it while another Hide is
  true); `require` rules Require/Unrequire/Enable/Disable (Disable greys `<button>`). No custom
  error action. Hiding Submit alone does not stop desktop Enter in a text box from submitting —
  the club guard also disables it (runtime reading; first used by `--club-guard`, verified in
  the browser on the template before any regional form).
- **The rule walk** (read 2026-09-30 in `jotform.forms.js`, md5 `841dc566a7`, byte-identical in
  builds `9e75d6f1d83`, `772a1982daf`, `962dcbe2fa6`, `cca53a3a639` and `2dd4239c231`, the five
  the forms were served on by 2026-10-01): `setConditions` reverses the rules array, and each field's listener
  walks the rules that test it in that reversed order, so **the rule at index 0 runs last**.
  Showing or hiding a field never re-runs a calculation (only a section or multi-field action
  with `clearFieldOnHide=enable` does), and **nothing recalculates at submit**. A calculation over
  fields that rules show or hide must therefore come before those rules and test the fields they
  test: the Contact_IDs sum is rule 0 on a picker form (`glow/sync.py` `CONTACT_IDS_FIRST`; with it
  after the roster rules, a change of club calculated question 18 over the previous club's
  rosters). 1.5 s after init, `prePopulations` runs `runAllConditions()` with an event that does
  not bubble: on a page the browser restores (Back) that is the only thing that re-shows the
  roster, so only the rule order covers it, not an operand listener.
- **`clearFieldOnHide`** is a form-level property (`GET /form/{id}/properties`; live value
  `disable` on all five forms - template, Africa, Asia, Latin America, U.S 262382706852058 -
  read 2026-10-06) with three runtime values (`jotform.forms.js`, build `fc726a121d4`): `enable`
  (clear a field the moment a rule hides it and run every calculation - the mode rejected
  2026-09-30, loop limit 3), `disable` (the live mode: a rule-hidden field keeps its answer *in the
  page*) and `dontClear`. At submit, unless the value is `dontClear`, every
  `input`/`select`/`textarea` inside a `.form-field-hidden` element is emptied before the form is
  sent; `always-hidden` fields (q98/q100/q102) are not touched and nothing recalculates. So a module
  dropdown hidden by the Year rule can keep a pick in the page but never in the submission (0 of
  674 since launch) - the back-fill resolver's "a dropdown hidden again can keep an answer" is true
  of the page only. `form_status` pins the value (`glow/sync.py` `CLEAR_FIELD_ON_HIDE`, the
  `module shape:` line; `--rendered` reads the served `JotForm.clearFieldOnHide="…"`; plan
  `docs/plans/2026-10-06-module-selection.md`); the builder labels of the three values are
  unverified.
- **Loop limit**: a rule checked more than `19 * (rules / 100 + 1)` times in one half-second (at
  most 100; 3 with `clearFieldOnHide=enable`) is skipped: today U.S 27, Asia 43, Africa 66, the
  template 94. Calculation rules are exempt unless an operand (or `baseField`) is a time, date,
  text or "mixed" field; the picker is a dropdown and the rosters are checkboxes.
- Calculations: text concatenates at top level, `[brackets]` = math; `ignoreHiddenFields: true`
  makes hidden fields contribute "" in text context (that is how one aggregate over every roster
  yields only the visible club's ticks; "hidden" is the `form-field-hidden` class on the field's
  `<li>` or section, tested at each run). `operands` must list every `{qid}` in the equation or
  changes do not re-trigger: each operand gets a `change` listener on its `<li>`, which fires by
  bubbling after the field's rules ran. An operand need not be in the equation (the Club picker
  on the Contact_IDs sum, `CONTACT_IDS_PICKER_OPERAND`); whether Jotform keeps such an operand
  is proven on the template by the second dry run and `form_status --rendered`.
  `insertAsText` / `newCalculationType` are builder-side flags.
- **A checkbox operand is read box by box**: for each ticked box, its `data-calcvalue`, else
  `FormTranslation.translate(value)` as it is (even `""`: `translateUncached` returns `""` when
  `simplifyfWord` empties the value), or `value` only when `FormTranslation` is not defined;
  never the label. One checkbox's ticks are joined with `", "`; operands are joined with nothing
  (two visible rosters fuse one token).
- **The dictionary lookup in a calculation** (`formTranslation.v2.js`, read 2026-10-02 in builds
  `62a8b57dd95` and `fc726a121d4`, byte-identical; emulated by `glow/translation_lookup.py`,
  which `tools/fix_name_translations.py` and `form_status.py` run). `setDictionary`: the original
  language is `base`; `dictionary.base` maps each entry's `en` text to its `base` text, and every
  other language L maps the `base` text, trimmed, to L's text, trimmed (an entry missing in
  `en`/`base` is skipped; the older build `9e75d6f1d83` files it under "undefined"). Then
  `trimMultiSpaces` and `sanitizeKeys` move every key whose whitespace runs collapse (JavaScript's
  `\s`: tab, newline, U+00A0 and the other Unicode spaces, U+FEFF; not U+200E) onto the
  collapsed key, **overwriting** the entry there: a stale `Amara  Fennwhistle` beats the exact
  `Amara Fennwhistle` in either order. `translate(word)` simplifies the word (`&amp;`, `<br>`,
  tabs, double spaces…), returns `dictionary[to][word]` when truthy, else retries with no-break
  spaces replaced, else walks the other languages in the runtime's own order for an entry whose
  simplified text equals the word and returns `to`'s entry for that key, else the word. `to` is
  the language the form shows (the primary `en`, or the mentor's browser language: the forms
  detect it). So a stale `base`/`en` spelling of a girl's name replaces her exact name in
  question 18: 55 options on 2026-10-02 (Africa 49, Asia 5, Latin America 1), removed by the tool.
  The page embeds the same store (`window.allTranslations.translations`, equal to the API's,
  key order included); `form_status --rendered` audits that copy.
- A field filled by a calculation can be the source of another rule (the Club picker → q5 copy);
  a calculation writing a text box fires keyup, so a rule testing q5 re-evaluates after each copy.
- The calculation reader, in text context, joins a multi-select's selected options with **no
  separator**, taking each option's `data-calcvalue` if it has one, else its visible text (which
  the browser's page translation can alter). So two clubs picked reach q5 run together, and a
  calculation cannot count a selection (only math/date functions exist).
