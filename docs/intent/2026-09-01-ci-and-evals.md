---
title: The loop closes by itself — CI, a daily drift check that writes intents, evals for the agent setup
author: Claude (playbook stages 4 and 6)
status: proposed
created: 2026-09-01
---

# Intent: CI, control-band monitoring, evals

## Problem

`make check` runs only where someone runs it; nothing watches the live forms for drift (a rule
flagged as error, a language list reset by a clone, a club missing from a form, an unusual
submission volume) until a person looks; and changes to `CLAUDE.md`, the skills or the hooks are
not tested against real tasks.

## Proposed outcome

1. **CI** (done in this change): `make check` on every push and pull request, no secrets.
2. **Daily drift check** (stage 6, "control bands"): a scheduled job runs `form_status.py --json`
   with a **read-only** Jotform key and compares each form's metrics against `bands.yaml`
   (`error_conditions ≤ 0`, `languages ≥ 12`, `missing_from_form = 0`, `rosters_out_of_date = 0`,
   `salesforce = true`, submissions per day within a range per region). A breach writes
   `docs/intent/<date>-auto-<form>-<metric>.md` from the intent template (`status: draft`,
   `author: daily-check`, the observed value, the band, the last seven values) and opens a pull
   request; no breach appends one line to `docs/evals/daily.csv`. Ryan triages the queue: fix,
   schedule, or dismiss (dismissals tune the bands).
3. **Evals**: twenty real tasks from this repository's history (a roster change dry run, a
   translation addition, a hook decision, a privacy question) written as prompt + acceptance
   checks and run non-interactively on changes to `CLAUDE.md`, `.claude/**` and `REVIEW.md`.

## Affected users and systems

Ryan (a triage queue instead of a routine); the repository (scheduled workflows, secrets); the
forms (read-only).

## Constraints

- A read-only Jotform key as the secret for the daily job, never the full-access one.
- The check writes intents, never fixes forms; every automatic write still goes through the
  auto-sync bands or a pull request.

## Open questions

- Which metric first: rule errors and languages are cheap and unambiguous; submission volume
  needs a baseline (a few weeks of data).
