---
title: One Jotform client, one form table, one set of text helpers
author: Claude (scope approved by Ryan)
status: done          # 2026-09-02, commit cec1c6c; proof in the commit message
done: 2026-09-02
created: 2026-09-01
---

# Intent: de-duplicate the Python tools

## Problem

The curl-based Jotform wrapper exists eight times (`backup_forms.py`, `restore_conditions.py`,
`tools/form_status.py`, `add_translations.py`, `restore_translations.py`, `add_feedback_link.py`,
`clone_regional.py`, `add_language.py`) plus the `Jotform` class in `sync_attendance_form.py` —
the only one with a dry-run gate. The form-id table exists in six files, `key`/`name_key`/`md5`
in four/three/two, and two tools load `sync_attendance_form.py` through `importlib`. Every fix
has to be made several times and the constants can drift from `appsscript/Config.gs`.

## Proposed outcome

A `glow/` package: `jotform.py` (one `Client` whose single `call` primitive treats any
POST/PUT/DELETE as a write, records it and skips it unless `apply=True`; retries and
`allow_fail` preserved for the callers that had them), `forms.py` (template, regionals, defunct,
titles, labels), `text.py`, `sync.py` (pure moves of the parsers and constants), `cli.py`. Every
script imports from it; behaviour is byte-identical except a clean exit message instead of a
traceback, and — the one deliberate improvement — the sync skips the conditions rewrite when the
regenerated rules equal the current ones, making "nothing to do" real.

## Affected users and systems

Nobody outside the repo; every Python tool; `tools/derive_partner_regions.py` also gets
`--forms live|defunct` (default live, `--write` refused for live: circular).

## Constraints

- Migrate one script at a time with `make check` green after each; `git tag pre-refactor`.
- Byte-equal tests for the helpers against the old code; parity pins on the real export; a
  GET-only before/after capture (`form_status --json` minus volatile keys, an Africa dry run, a
  template backup, `add_translations --audit`) must be identical.
- Root rollback pair stays at the root for now.

## Open questions

- Whether to fold `tools/auto_sync.py`'s `REGIONAL_FORMS` into `glow.forms` in the same change
  (yes, with the Config.gs parity test moving with it).
