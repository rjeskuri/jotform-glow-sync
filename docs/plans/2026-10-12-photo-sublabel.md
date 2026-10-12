---
title: The Group Photo sublabel loses its sentence about faces; one photo per submission stays
author: Claude (with Ryan)
status: accepted         # Ryan asked for it in conversation 2026-10-12; the live steps wait for his go
created: 2026-10-12
intent: none - Ryan's request of 2026-10-12
---

# Plan: "All girl faces should be visible." leaves the Group Photo field

Ryan, 2026-10-12: remove the sentence "All girl faces should be visible." from the Group Photo
field on all the attendance forms, and nothing else; one photo per submission stays the rule.

## Context (read 2026-10-12, GETs only)
- The sentence is the second half of the `subLabel` of question 19 (`photo`,
  `control_fileupload`) on the template and the four regional forms, set on 2026-09-12 by
  `tools/update_static_fields.py` (DECISIONS 2026-09-12). Nothing else writes it: the sync and
  the runner never touch question 19. The U.S form is disabled (Ryan); it is included anyway, so
  it matches the others if it is ever enabled again.
- Question 19 on all five: `subLabel` the two sentences, `fileLimit` 1, `allowMultiple` Yes,
  `required` Yes, `limitFileSize` Yes, `maxFileSize` 10240, `extensions`
  `jpg, jpeg, png, gif, heic`. `fileLimit` 1 is what keeps a submission to one photo: every
  submission carries exactly one file ([photos plan](2026-10-06-photos-to-drive.md), Context).
  The tool's dry run wanted `allowMultiple` Yes → No on every form, the point that plan noted
  "on the way".
- The two-sentence text is translated in 11 languages in `tools/translations_additions.json`
  and in Hindi and Persian in `tools/translations_hi.json` / `tools/translations_fa.json`; every
  form's store has those entries (11 of 11 languages; Asia 13 of 13).

## The change
1. `tools/update_static_fields.py` `WANTED["photo"]`: `subLabel` → "Upload one photo of everyone
   in attendance today."; `"allowMultiple": "No"` replaced by `"fileLimit": "1"` (Ryan: only one
   photo; `fileLimit` enforces it and already reads 1, so the tool's apply writes the sublabel
   and nothing else, and never writes `allowMultiple` again). A dated entry in its docstring.
2. The new sentence's translations: in every language, the first sentence of the existing
   translation - no new wording (Thai separates its sentences with a space; Urdu, Hindi, Nepali,
   Odia and Khmer end theirs with ۔ / । / ។). 11 languages in `translations_additions.json`,
   Hindi and Persian in their own files, as for every static-field string.
3. The two-sentence entries stay, with a `_note` on the `translations_additions.json` one:
   - `add_translations.py` plans only strings a form shows (`plan_additions`), so once no form
     shows the old sentence it is never posted again.
   - Deleting it from the files would not delete it from any form: every writer posts each
     language whole (the existing entries plus the new ones) and nothing prunes a store.
   - A rollback (the old sublabel written back) finds its translations in the stores and in the
     files. Precedent: the pre-2026-09-12 sublabel "Upload a photo of everyone in attendance
     today" is still in the Hindi, Persian and Odia files.
   - The tests derive each new translation from the old one, as its first sentence.
4. Tests (`test/links_layout_test.py`, `test/fix_name_translations_test.py`): `WANTED`'s photo
   props; the tool run against the live question 19 writes only `question[subLabel]` and then
   reads clean; every `WANTED` wording has its 11 + 2 translations; each new translation is the
   first sentence of the old; `plan_additions` plans the sentence a form shows and not the other;
   `add_language.py` posts the Hindi only once the form's `base` has the English.
5. DECISIONS: a dated section; the 2026-09-12 one gets a bullet pointing at it.

## Files that change
`docs/plans/2026-10-12-photo-sublabel.md` (this file), `docs/plans/README.md` (`make
docs-index`), `tools/update_static_fields.py`, `tools/translations_additions.json`,
`tools/translations_hi.json`, `tools/translations_fa.json`, `test/links_layout_test.py`,
`test/fix_name_translations_test.py`, `docs/DECISIONS.md`. No current-state document quotes the
old sentence (RUNBOOK, ARCHITECTURE, README); dated plans and decisions keep it as history.

## The live steps (Ryan's go; none of them is part of this change)
The translations cannot go first: `add_translations.py` plans an addition only when the form
shows its English, and `add_language.py` posts a string only when the form's `base` has it,
which `add_translations.py` writes. With the new entries in the files, both dry runs say
"0 new" / "+0 new" on every form today. So, per form, the sublabel and then the translations
straight after; non-English pages show the new sentence in English in between (seconds). The
template first (not mentor-facing), then the regionals. The runner needs no pause: it never
touches question 19 or the translations.

Run from a checkout that has this change (`grep -n fileLimit tools/update_static_fields.py`
finds it): an older checkout's tool would write `allowMultiple` No as well. Key from `.env`.

```bash
set -a; source .env; set +a
python3 tools/update_static_fields.py          # dry run: one "photo (q19): subLabel" line per form, nothing else
python3 tools/add_translations.py              # dry run: "(0 new)" on all five
python3 backup_forms.py --form 262352490535154
python3 backup_forms.py --form 262382821971058
python3 backup_forms.py --form 262383129464057
python3 backup_forms.py --form 262383455778067
python3 backup_forms.py --form 262382706852058
# template
python3 tools/update_static_fields.py --form 262352490535154 --apply   # "photo (q19): written and verified"
python3 tools/add_translations.py --form 262352490535154 --apply       # 11 new; "stored (...)"
# Africa, Asia (+ Hindi, Persian), Latin America, U.S
python3 tools/update_static_fields.py --form 262382821971058 --apply && python3 tools/add_translations.py --form 262382821971058 --apply
python3 tools/update_static_fields.py --form 262383129464057 --apply && python3 tools/add_translations.py --form 262383129464057 --apply
python3 tools/add_language.py --form 262383129464057 --code hi --name Hindi --dict tools/translations_hi.json --apply
python3 tools/add_language.py --form 262383129464057 --code fa --name Persian --dict tools/translations_fa.json --apply
python3 tools/update_static_fields.py --form 262383455778067 --apply && python3 tools/add_translations.py --form 262383455778067 --apply
python3 tools/update_static_fields.py --form 262382706852058 --apply && python3 tools/add_translations.py --form 262382706852058 --apply
```

Each translation POST saves the form's whole store first (`backups/translations/`). A gateway
504 on a POST can hide a completed write: re-run the dry run; "0 new" means it landed (RUNBOOK
"Translations").

**Verify** (reads):

```bash
python3 tools/update_static_fields.py          # "photo (q19): already as the guide wants it" x5, no "->" line
python3 tools/add_translations.py              # "304 entries across 11 languages (0 new)" x4; Asia "310 ... across 13 (0 new)"
python3 tools/add_language.py --form 262383129464057 --code hi --name Hindi --dict tools/translations_hi.json      # +0 new, 72 of 72
python3 tools/add_language.py --form 262383129464057 --code fa --name Persian --dict tools/translations_fa.json    # +0 new, 72 of 72
python3 tools/form_status.py --roster data/roster_<date>.csv --partners data/partners_<date>.csv   # CLEAN, as before
```

And in a browser: a regional form's public page in two other languages (Hindi on Asia) shows
the one-sentence sublabel translated.

**Rollback**: the old sublabel back on a form - in the builder (Group Photo → Sublabel; nothing
regenerates question 19, so the edit stays), Jotform's Revision History, or the tool from a
branch where only `WANTED["photo"]["subLabel"]` is the two sentences again (a `git revert` of
the whole tool change would put `allowMultiple` No back and the tool would write it). The old
sentence's translations never leave any store, so they apply again at once; the new entries need
no undoing (unused while no form shows the sentence). The questions snapshot from
`backup_forms.py` holds question 19 as it was.

## Risks
- The English window between the two writes on each form (seconds); a mentor who opens the page
  in another language then sees the new sentence in English until a reload.
- The new translations inherit the old ones' review status: written by us in 2026-09, not
  native-reviewed (the `_about` of `translations_additions.json`); nothing new to review.

## Proof
- `make check` on the branch.
- `python3 tools/update_static_fields.py` (dry run) from the branch: one drift line per form,
  `photo (q19): subLabel: 'Upload one photo of everyone in attendance today. All girl f' ->
  'Upload one photo of everyone in attendance today.'`, `mentorEmail` already right.
- With the new entries, the dry runs of `add_translations.py` (304 / Asia 310 entries, 0 new) and
  `add_language.py` hi/fa on Asia (+0 new) are unchanged; replayed in memory against the live
  stores with question 19 carrying the new sentence: 11 new entries per form plus `base`/`en`,
  then +1 Hindi and +1 Persian on Asia.
