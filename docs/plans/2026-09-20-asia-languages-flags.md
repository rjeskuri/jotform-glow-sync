---
title: Hindi and Persian on the Asia form; a switcher flag for Odia on every form
author: Claude (executed with Ryan)
status: in-progress
created: 2026-09-20
intent: none — requested by Ryan on 2026-09-20
---

# Plan: Hindi + Persian for Asia, flags for Odia (and any flagless language)

Ryan asked for Hindi, Persian, Urdu and Arabic on the Asia attendance form,
a flag for Odia on all forms, and flags for the new languages. Urdu and
Arabic are already offered on Asia (all 11 non-English languages there
cover the same mentor-visible strings; `add_translations.py --audit` shows
only the year digits and the club names untranslated, by design). So the
work is Hindi (`hi`) and Persian (`fa`) on Asia, plus the flags.

**Why Odia has no flag.** Jotform's switcher (`showStatus: flag-with-nation`)
renders one nation-flag SVG per language from its own table (Telugu → India,
Urdu → Pakistan, Swahili → Tanzania, Arabic → Saudi Arabia). Oriya is in its
language table but not in its flag table, so its row and the trigger get an
empty `.jfLangDd-flag` span. The public page applies the form's `injectCSS`,
the runtime sets `html[lang]` on every switch and copies the chosen row's
flag into the trigger — so one CSS rule per language paints both slots. The
flag used is Jotform's own India SVG (copied from the Telugu row): Odia is an
Indian language and has no flag of its own, and India is what Jotform's
convention gives it.

## Files that change
- `tools/translations_hi.json`, `tools/translations_fa.json` — the 52 strings
  (the Odia set plus the 2026-09-12 additions), written by Claude with a
  three-lens review and a refutation pass; native-speaker review pending
  like the Odia set (backlog 6a).
- `tools/switcher_flags.py` + `tools/switcher_flags/or.svg` — dry run by
  default; `--apply` snapshots the form and writes the marked CSS block into
  `injectCSS`, re-reads and compares; `--check-page` reads the public page.
- `test/python_test.py` — `SwitcherFlags`.
- `docs/RUNBOOK.md` (Translations), `docs/DECISIONS.md`, `docs/BACKLOG.md` 6a.

## Order of work
1. Tool, tests, docs, translations; `make check`; commit.
2. `add_language.py --form 262383129464057 --code hi --name Hindi --dict tools/translations_hi.json`
   dry run, then `--apply`; same for `--code fa --name Persian`. Backup: a GET
   of the translation store under `backups/translations/` first (a new
   language's POST replaces only its own, empty, dictionary).
3. `add_translations.py --audit --form 262383129464057` → hi and fa show the
   same "untranslated" set as the other languages (digits and club names).
4. `switcher_flags.py --check-page --form 262383129464057` → do Hindi and
   Persian get built-in flags? If not, add `hi.svg` / `fa.svg` to `FLAGS`.
5. `switcher_flags.py` dry run on the template + four regionals, `--apply`,
   `--check-page` on each → the block is on the public page.

## Risks
- `POST /form/{id}/translations` replaces a language's dictionary: the tool
  GETs and merges; for a new code there is nothing to lose. Big POSTs 504 at
  the gateway sometimes — the tool retries and re-reads.
- `injectCSS` is written whole: the tool preserves the theme's existing CSS
  and only replaces its own marked block; rollback is the properties
  snapshot (`backups/<id>/properties-<stamp>.json`) or deleting the block.
- Jotform caches the public page; the page check may lag a minute.
- Persian readers may be Afghan (Dari): the wording is neutral standard
  Persian; Jotform offers no separate Dari entry.

## Proof
`make check` tail; the dry-run and apply output of both tools; the audit;
`--check-page` output per form. Recorded below when done.
