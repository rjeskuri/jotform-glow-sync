---
title: The attendance forms point mentors to the Club Roster Form when a girl is missing or has left
author: Claude (workflow track wf/roster-form-link, 2026-09-28)
status: blocked          # merged 2026-09-29 (1563a34); placing the link on the forms waits for Ryan's go (BACKLOG 46)
backlog: 46
created: 2026-09-28
intent: none — finding 6 of the 2026-09-26/27 problem-report review; requested by Ryan in the 2026-09-28 workflow session
---

# Plan: a Club Roster Form link above Submit on every attendance form

## Why
7 of the 11 problem reports so far were roster changes (a girl to add or
remove), and none of them was applied; 38 of 50 partners have never used the
Club Roster Form. The attendance forms carry exactly one pointer at the bottom,
the problem-report link (text element q443, "Click here to report a problem",
`tools/add_feedback_link.py`). Nothing on the form a mentor uses every week
says where a roster change goes.

## What
One text element per form (template + the four regionals), unique name
`clubRosterFormLink`, directly **above** the problem-report link, styled like
it (the same grey box), holding one linked sentence:

> A girl missing, or no longer in your club? Tell us on the Club Roster Form.

The link is the Club Roster Form's **public** "fill in" URL
(`docs/LAUNCH.md`, the `…/forms/d/e/…/viewform` form — never an edit URL).
The sentence is translated for every language the forms offer: es, fr, th,
ur, te, vi, ne, km, sw, ar, or on all five, plus hi and fa on Asia (the tool
posts a language only to a form that offers it). The translations are ours,
marked "not native-reviewed" like the Odia, Hindi and Persian sets.

Layout today (read 2026-09-28, all five forms alike): … the rosters, q443 at
order *k*, Submit (q2) at *k*+1, the hidden bridge fields after it. After:
the new element at *k*, q443 at *k*+1, Submit at *k*+2 — three writes per
form (move Submit, move q443, add), tail first, so every intermediate state
still renders in the right order.

## Design choices
- **Extend `tools/add_feedback_link.py`** (`--link roster`) rather than a
  sibling tool: the mechanics are the same element mechanics. The element
  table (unique name, sentence, public URL, what it sits above) moves to a new
  `glow/links.py`, because `add_translations.py` and `add_language.py`
  special-case the problem link today (its `text_<qid>` translation keys) and
  must now handle both elements from the same table. `--link problem` stays
  the default, so the documented command is unchanged.
- The tool gains what its pattern promised but the 2026-09 version lacked:
  a snapshot before any write (`backup_forms.snapshot`), a re-read after
  (the element exactly once, its text as intended, not hidden, above the
  problem link and Submit, no rule mentioning it), a refusal on an edit URL
  or a URL the *other* link already uses (a swapped pair), and a refusal on an
  unexpected layout (anything but the two links and Submit between the anchor
  and Submit) instead of guessing where to insert. Re-running is a no-op when
  the text already matches; `--remove` deletes the element.
- **One sentence inside the link.** Jotform translates a text element by its
  element id (`text_<qid>`), swapping the whole inner HTML; one sentence is
  one translatable unit, exactly as the problem link does it.
- **"Club Roster Form" stays in English inside every translation.** The
  Google Form it opens is English-only and titled "Global Catalyst – Club
  Roster Form"; the mentor should recognise the page that opens.
- **Above the problem link, not below.** The specific path first: a mentor
  with a roster change meets it before the generic link. Costs one extra order
  write per form.
- **The plain viewform URL, no prefill.** Pre-selecting the Club Roster Form's
  page-1 choice ("Add or remove girls…") needs its `entry.<id>`, which breaks
  silently when that question is edited (BACKLOG 43 edits are coming). Left as
  a decision for Ryan.
- **Why the sync cannot wipe or hide it.** `sync_attendance_form.py` writes
  only roster checkboxes (create/update/prune — found by
  `type == control_checkbox`), the Club picker, q5's hidden flag and the
  conditions. A text element that no rule mentions is always visible, and
  `build_conditions` only ever mentions rosters and the structural qids. Both
  are pinned by tests (an end-to-end dry run of the sync on a fake form that
  carries both links; an invariant on `build_conditions`).
- No Apps Script change, no Google service, no Salesforce field: q5 and the
  mapping are untouched.

## Files that change
- `glow/links.py` (new) — the element table (`PROBLEM`, `ROSTER`), both public
  URLs, `element_html()` (byte-identical to the live q443 HTML for the problem
  link), `check_public_url()`, `plan_insert()` (order + tail moves, or a
  refusal), `rules_mentioning()`.
- `tools/add_feedback_link.py` — `--link {problem,roster}`, default URLs from
  `glow/links.py` (`--url` still overrides), snapshot before, verify after,
  idempotent, `--remove`.
- `tools/add_translations.py` — `plan_additions()` (pure: payload + base/en
  sources) covering every element in the table; the store is saved under
  `backups/translations/` before a POST.
- `tools/add_language.py` — the text-element keys for every element in the
  table, not only the problem link.
- `tools/translations_additions.json` — the sentence in 13 languages, with a
  `_note`.
- `test/python_test.py` — `Links` (HTML byte-identity, URL guard, insertion
  plan and its refusals, `rules_mentioning`, URLs pinned to `docs/LAUNCH.md`),
  `TranslationPlan` (both elements' `text_<qid>` / HTML / plain keys, base/en,
  hi/fa only where offered, every offered language present, the problem link's
  plan unchanged), `SyncLeavesTheLinksAlone` (the sync's dry run on a fake
  form), and a `build_conditions` invariant.
- `docs/RUNBOOK.md` ("Links above Submit"), `docs/ARCHITECTURE.md`,
  `README.md`, `docs/LAUNCH.md` (the command), `docs/DECISIONS.md`,
  `docs/BACKLOG.md`, and `appsscript/INSTALL.md` (a pointer only; `.claspignore` pushes nothing but `.gs` and `appsscript.json`).

## Order of work
1. This plan, committed.
2. `glow/links.py`, the link tool, its tests; `make check`; commit.
3. The translation tools, the additions, their tests; `make check`; commit.
4. Docs; `make check`; commit.
5. Read-only dry runs against the live forms (the link tool; `add_translations.py`,
   whose preview cannot see the new element until it exists, so also a
   read-only simulation that plans the translations for the live forms with
   the element inserted in memory) — output under **Proof**.

Live steps, each needing **Ryan's go** (none is run by this track):

    python3 backup_forms.py                                           # all forms; the tool also snapshots each form it writes
    python3 tools/add_feedback_link.py --link roster                  # dry run: ADD … above q443, move q443 and Submit
    python3 tools/add_feedback_link.py --link roster --apply          # writes, re-reads, verifies
    python3 tools/add_translations.py                                 # dry run: the new element's entries appear
    python3 tools/add_translations.py --apply                         # GET-merge-POST per form, store saved first
    python3 tools/add_translations.py --audit                         # the sentence no longer untranslated

Then open one public form in two languages (Spanish; Hindi on Asia) and see
the sentence translated, the link opening the Club Roster Form, and the box
above "Click here to report a problem". `tools/form_status.py` stays CLEAN
(the element is not a roster and no rule mentions it).

## Risks
- **Order writes on live forms.** Two existing elements (q443, Submit) move by
  one. Mitigation: tail-first sequence; the tool refuses any layout other than
  links + Submit between the anchor and Submit; the snapshot holds every old
  order; rollback is `--link roster --remove --apply` (the gap it leaves is
  harmless) and, if wanted, the two old orders re-posted from the snapshot, or
  Jotform's Revision History.
- **Equal orders.** After the move Submit shares its order with the hidden
  q103 header; equal orders render in creation order and q2 is older, so
  Submit stays first (the same situation the problem link created in 2026-09,
  since renumbered by Jotform).
- **Translations POST replaces a language.** GET-merge-POST as always; the
  store is now saved to `backups/translations/` first; new English sources go
  to base/en with `setdefault`. The Submit/Other `_note` rule (never overwrite
  Jotform's own entries) is untouched: the new sentence is ours alone.
- **Translation quality.** Written by us, not native-reviewed (BACKLOG 6a/6b
  cover a native check); a wrong word shows only until corrected and re-applied.
- **Refactor of two translation tools.** The problem link's plan must not
  change: pinned by a test on a fake form, and the live dry run must still
  report "0 new" for every form.
- **Found on the way (not fixed here):** on every form the rosters created
  since the 2026-08-24 overhaul sit *after* the Submit button (the sync
  creates new rosters at the highest order + 1): template 123 of 342, Africa
  97 of 220, Asia 14 of 93, Latin America 26 of 39, U.S 5 of 12 (orders read
  2026-09-28; the public Africa page renders them below Submit). A mentor of
  such a club sees her roster below the button and both links. Added to the
  BACKLOG as item 47, "Rosters render below the Submit button" (with 46, this
  link; 45 belongs to the parallel branch `wf/partner-box`).

## Proof
Read-only runs against the live forms, 2026-09-28 (no write was made):

`python3 tools/add_feedback_link.py --link roster` (dry run):

    DRY RUN - clubRosterFormLink: 'A girl missing, or no longer in your club? Tell us on the Club Roster Form.'
      -> https://docs.google.com/forms/d/e/1FAIpQLScPO9Dizjl9G8krMcvs1sVnqYku3k8dB7Ycv-1VahgPDssMzQ/viewform

    == Africa 262382821971058
       1. move submit2 (q2) 141 -> 142
       2. move somethingNotWorking (q443) 140 -> 141
       3. ADD clubRosterFormLink at order 140, directly above somethingNotWorking (q443)
    == Asia 262383129464057
       1. move submit2 (q2) 97 -> 98
       2. move somethingNotWorking (q443) 96 -> 97
       3. ADD clubRosterFormLink at order 96, directly above somethingNotWorking (q443)
    == Latin America 262383455778067
       1. move submit2 (q2) 31 -> 32
       2. move somethingNotWorking (q443) 30 -> 31
       3. ADD clubRosterFormLink at order 30, directly above somethingNotWorking (q443)
    == U.S 262382706852058
       1. move submit2 (q2) 25 -> 26
       2. move somethingNotWorking (q443) 24 -> 25
       3. ADD clubRosterFormLink at order 24, directly above somethingNotWorking (q443)
    == template 262352490535154
       1. move submit2 (q2) 237 -> 238
       2. move somethingNotWorking (q443) 236 -> 237
       3. ADD clubRosterFormLink at order 236, directly above somethingNotWorking (q443)

`python3 tools/add_feedback_link.py` (the problem link, default URL): every
form `somethingNotWorking (q443) already present and up to date` — the shared
HTML is byte-identical to the live element. An edit URL and the problem
form's URL given to `--link roster` were both refused.

`python3 tools/add_translations.py` (dry run, refactored): `271 entries across
11 languages (0 new)` on all five forms — identical output to the tool before
the refactor; `add_language.py` dry runs (hi on Asia, or on all) identical too.

Translation simulation (the element inserted in memory into each live form's
questions, then `plan_additions` on the live store; nothing written): the
element keyed three ways in every offered language — 11 on Africa, Latin
America, U.S and the template (33 new entries each), 13 on Asia with hi and
fa (39 new); the only new keys are the element's; base/en gain 3 sources;
no offered language left untranslated.

`make check` tail (after the docs commit):

    py: 31 files parse, 18 scripts answer --help
    Ran 80 tests
    OK
    gs: 10 files parse
    secrets: clean
    docs-links: ok
    fixtures: up to date
    CHECK PASSED

## Result
Built and tested on branch `wf/roster-form-link`; nothing deployed. The live
steps under **Order of work** wait for Ryan's go.

Code review (2026-09-28): five nits, each reproduced offline, none touching
the planned deploy (default URLs, a visible q443). Fixed, each with a test
that fails without it:
- a changed URL updated in English only: every other language keeps its copy
  of the old link, so the tool now says, in the plan and after the write, to
  re-run `tools/add_translations.py --apply` (RUNBOOK too);
- a hidden q443 crashed the roster plan with a traceback: it is now a refusal
  naming the fix (`--link problem` unhides it);
- the post-write check passed if q443 ended up below Submit (a move
  acknowledged but not applied): it now checks the anchor against Submit too,
  and so does the plan's note for an element already present;
- the pre-write snapshots and store backups were stamped to the minute, so a
  re-run within it overwrote the "before": stamped to the second, and a store
  backup never overwrites an earlier file;
- BACKLOG 45 collided with `wf/partner-box`: this branch's items are now 46
  and 47. Both branches add their rows after 44, so the merge will still stop
  on that table: keep both rows, in number order.
