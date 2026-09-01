---
title: Python and Apps Script read the enrollment responses identically
author: Claude (found while building the fixture)
status: proposed
created: 2026-09-01
---

# Intent: close the known parity gaps

## Problem

`sync_attendance_form.py read_sheet` keeps a response row whose partner cell is empty (it only
requires a club and a roster); `appsscript/Normalize.gs readResponses_` drops it. `parseRoster_`
strips `•` and `*` bullets; `parse_roster` strips only `-`. `parse_roster` strips invisible
characters from roster lines only; `tidy_` strips them from partner and club cells too.
`read_roster_csv` matches `--region` case-insensitively; `form_status.py` matches exactly. The
synthetic fixture deliberately avoids all four so the parity test can pass; a real row that hits
one of them makes the two sides disagree silently.

## Proposed outcome

One behaviour per rule, implemented on both sides, with fixture rows that exercise each so
`test/parity_test.js` proves it. Proposal: drop partner-less rows (the Apps Script behaviour —
a nameless partner would seed a nameless Partners row), strip `-`, `•` and `*` (the Apps Script
behaviour), strip invisibles everywhere (the Apps Script behaviour), compare regions
case-insensitively everywhere (the Python behaviour).

## Affected users and systems

`sync_attendance_form.py`, `tools/form_status.py`, `tools/needs_attention.py`, `Normalize.gs`,
`test/fixtures/make_fixture.py`, `expected.json`, the parity test.

## Constraints

- A behaviour change on the Python side can change what the sync plans for a live form: run the
  GET-only before/after capture and read the diff before applying anything.

## Open questions

- Are there real rows without a partner in the historical responses tab? (`needs_attention.py`
  can count them; the answer decides how urgent this is.)
