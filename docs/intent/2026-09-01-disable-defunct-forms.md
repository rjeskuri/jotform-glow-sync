---
title: Switch off the five pre-launch attendance forms
author: Ryan Eskuri (backlog item 1, captured by Claude)
status: done          # the five pre-launch forms DISABLED since 2026-09-30 (BACKLOG 1)
done: 2026-09-30
created: 2026-09-01
---

# Intent: disable the defunct forms

## Problem

The five pre-launch forms (master and four regionals, retitled "(defunct)") are still ENABLED.
A mentor with an old link can submit there; those submissions reach Salesforce like any other,
split the data across two forms per region, and are not covered by the automatic sync.

## Proposed outcome

Each defunct form is DISABLED with a "this form has moved" message carrying the region's new
link (in the twelve languages, as far as Jotform's disabled-message allows), keeping its
submission history. One command per form, dry run first.

## Affected users and systems

Mentors still using old links (they see the message and the new link); the five defunct forms;
`tools/form_status.py --defunct` (shows `status DISABLED`).

## Constraints

- Only after the new links are in partners' hands (Ryan's go).
- No deletion; history stays.
- The tool goes through `glow.jotform.Client` (or the existing wrapper), dry run by default.

## Open questions

- Message wording and whether a per-language message is possible on a disabled form (Jotform
  shows one message; the link text can be multilingual).
