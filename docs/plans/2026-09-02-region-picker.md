---
title: New partners choose their region on the Club Roster Form
author: Claude (approved by Ryan)
status: in-progress
created: 2026-09-02
intent: docs/intent/2026-09-02-region-picker.md
---

# Plan: required Region picker on the Club Roster Form (backlog 38)

## Files that change

- `appsscript/Config.gs` — `Q.REGION: 'Region where this club meets'`; `Q.COUNTRY`
  marked legacy (still read from old response rows); canonical
  `const REGIONS = ['Africa', 'Asia', 'Latin America', 'U.S'];` (NOT in the
  generated, edit-blocked `Regions.gs`).
- `appsscript/RosterOps.gs` — pure helpers, Node-tested: `canonicalRegion_`
  (validate an answer against `REGIONS`, return the canonical spelling or `''`),
  `chooseRegion_(tabRegion, formAnswer, derivedRegion)` (tab verbatim > canonical
  form answer > derived > `''`), `derivedPartnerRegions_()` (key_-ed map from
  `PARTNER_REGIONS`).
- `appsscript/Roster.gs` — reader split: new `loadPartnerTabRegions_()` (tab only);
  `loadPartnerRegions_()` rebuilt on the two layers, behavior identical for its
  other callers. `seedPartners_(partnersSeen, formRegions)` — optional 2nd arg;
  blank/new Partners rows fill form > derived with note
  `'region chosen on the Club Roster Form'`; staff-typed regions never touched;
  the rebuild call site is unchanged. `refreshRosterRegions`: no change.
- `appsscript/FormHandlers.gs` — `handleNewClub_` resolves region via
  `chooseRegion_`; passes the form region into `seedPartners_`; the no-region
  ReviewQueue detail explains an ignored invalid Region answer, else the legacy
  Country line. SF Pending block unchanged.
- `appsscript/Forms.gs` — generator builds the picker instead of the Country text
  item (`REGION_HELP` help text); one-shot idempotent `migrateCountryToRegion()`
  (insert at the Country item's index via append-then-moveItem, delete Country,
  `audit_` row; refuses on an unrecognizable form; safe to run twice).
- `appsscript/Menu.gs` — Google Forms submenu: "Replace the Country question with
  the Region picker (one-time)".
- `test/forms_logic_test.js` — precedence/validation/canonicalization checks incl.
  the `U.S` spelling pin.
- `test/python_test.py` — `test_regions_match_glow_forms`: `Config.gs REGIONS` ==
  `glow.forms.REGIONS`, `Q.REGION` title present.
- `test/parity_test.js` — its `REGIONS` set now sourced from `Config.gs` via the
  loader (removes the third hand-copy of the list).
- Docs — this plan + the intent; `BACKLOG.md` row 38 status; one `DECISIONS.md`
  row; `RUNBOOK.md` blank-region bullet extended.

## Order of work

1. Intent + plan committed.
2. Config.gs + RosterOps.gs helpers + the three test files → `make check`.
3. Roster.gs + FormHandlers.gs rewiring → `make check`.
4. Forms.gs + Menu.gs → `make check`.
5. Docs rows; commit.
6. Ryan's deploy ladder (below) — the clasp push is live-gated.

## Risks

- Mentor picks the wrong region → the club syncs to the wrong regional form.
  Mitigated by the help text, the Partners-tab note flagging form-chosen regions,
  and the unchanged staff path (fix the tab → Refresh regions → auto-sync moves
  it). Strictly better than today's silent no-form-at-all.
- `seedPartners_` change touching the rebuild path → 2nd argument optional; the
  rebuild call site is byte-identical in behavior.
- Spelling drift → pinned three ways (python parity test, forms_logic check,
  parity_test sourcing from Config.gs).
- Deploy-order hazard → none: handlers look answers up by column header, so until
  the form is migrated `Q.REGION` simply isn't found and behavior is today's;
  the menu item only exists after the push, so the push comes first by
  construction. No new Google service → no OAuth scope growth.

## Proof

Offline: `make check` — healthy tail identical to the CLAUDE.md pin
(`gs: 10 files parse` unchanged); `python_test` now `Ran 30 tests … OK`;
`forms_logic_test` gains the region section and ends `ALL CHECKS PASSED`.

Deploy (Ryan-gated, quiet moment):
1. `make gs` → `npm run clasp:push`.
2. GLOW → Google Forms → "Replace the Country question with the Region picker
   (one-time)" → alert "Region picker inserted; Country question removed" +
   Audit row `migrateCountryToRegion`.
3. Run it a second time → "already migrated; picker re-asserted" (idempotence).
4. Open the fill-in URL: New club → "My organization is not in this list" →
   the "Your organization" page shows the org-name box plus a required Region
   dropdown with exactly the four choices; a known partner still jumps straight
   to "The club". **Do NOT submit a test response.**
5. Passive, on the first real new-partner submission: roster rows carry the
   region; the Partners row notes "region chosen on the Club Roster Form"; no
   "Partner has no region" ReviewQueue row; SyncLog shows the club reaching its
   regional Jotform.

Rollback: `clasp push` of the previous commit's `appsscript/` (the handler
tolerates either form state; reverting the form itself is optional and manual).
