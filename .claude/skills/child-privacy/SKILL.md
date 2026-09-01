---
name: child-privacy
description: Personal-data policy for this repository, whose data is rosters of girls (minors) — what counts as PII, what may appear in code, docs, tests, fixtures, logs, commits and conversation, and how to describe data without naming anyone. Load for any change touching data files, fixtures, tests, docs, logging, output formatting, or workflow artifacts.
---

# Child privacy

## What is personal data here
- A girl's full name (and any part of one in roster context), her id (`CLUBCODE-LASTCODE-NNN`
  — the surname is inside), mentor names and e-mail addresses, anything under `data/`,
  `backups/` (form snapshots embed rosters as checkbox options) and `credentials/`, the
  translation dictionaries' `base`/`en` entries (they list every roster option), and Jotform
  submissions.
- Club and partner-organisation names are not personal data but are operational details of
  youth groups: fine inside this private repository, not for public places.

## Rules
1. Never commit, quote, paste, print, or summarise-by-example a real girl's name or id — not in
   code, tests, docs, commit messages, workflow logs, artifacts, chat, or plans. Describe data by
   counts and structure ("club X: 14 girls, 1 duplicate name").
2. Tests and docs use fictional people only: names from `test/fixtures/make_fixture.py`
   (invented surnames), ids like `DEMOCLUB-SAMPLE-001` / `SUNRISEC-ZIBBLEWICK-001`, e-mails on
   `example.org`. Never copy a real row into a fixture.
3. Anything printed by unattended runs goes through `auto_sync.redact`; workflow artifacts hold
   conditions backups and redacted logs only, never `questions-*.json` or roster CSVs.
4. Do not open files under `data/`, `backups/` or `credentials/` unless the task needs them; when
   you must, read structure (keys, counts) not values, and say so.
5. Masked ids in output: `SUNRISEC-XXXX-001` (the tests' `mask` helper).
6. `make secrets` / the PostToolUse hook refuse girl-id patterns, e-mail addresses, keys and
   Drive ids in tracked files; `test/parity_test.js` refuses any real enrolled name in published
   text. Do not weaken either to make something pass — change the content.
7. On accidental exposure: remove it, tell Ryan, and if it reached git, rewrite history
   (precedent: 2026-08-26) before any push.
