---
title: Club picker on every attendance form, with the training guide's wording
author: Claude (executed with Ryan; leadership approval 2026-09-12)
status: done
created: 2026-09-12
intent: docs/intent/2026-09-01-club-picker.md
---

# Plan: club picker rollout + 2026-09-12 wording (executed 2026-09-12)

Leadership approved the club selector for all forms and sent exact wording from
the updated training guide. This is the record of what was done, in order, so a
future reader can see the state each form was left in.

## What changed, per form (template + Africa, Asia, Latin America, U.S)

1. Static fields (`tools/update_static_fields.py --apply`, verified by re-read):
   `mentorEmail` label → **Partner Coordinator Email** (sublabel unchanged);
   `photo` sublabel → "Upload one photo of everyone in attendance today. All
   girl faces should be visible.", `maxFileSize` 3000 → 10240 KB, extensions
   + `heic`, `allowMultiple` → No.
2. Sync with `--club-picker --apply`: the picker (searchable dropdown, label
   **Club Name**, sublabel "Select your Club Name to see your roster." from
   `PICKER_PROPS`), question 5 hidden and calc-filled (Salesforce keeps reading
   it), conditions regenerated — and the roster changes that had been waiting
   since 09-09 while `AUTO_SYNC_APPLY` was 0.
3. `tools/add_translations.py --form <id> --apply` — 33 new entries per form
   across 11 languages (ten plus Odia for the new strings). Two POSTs returned
   a gateway 504 (U.S, Asia); a dry-run re-read showed "0 new" both times, i.e.
   the writes had landed.
4. `tools/form_status.py --form <id> --roster <csv>` → CLEAN on every form.

## Order and results

| Form | Applied | Rules | Picker | Status |
|---|---|---|---|---|
| template 262352490535154 | 13 creates, 17 updates, picker wording | 376 | q444 | CLEAN |
| U.S 262382706852058 | picker | 41 | q444 | CLEAN |
| Latin America 262383455778067 | 2 creates, 2 updates, picker | 68 | q452 | CLEAN |
| Asia 262383129464057 | 2 creates, 7 updates, picker | 117 | q447 | CLEAN |
| Africa 262382821971058 | 1 create, picker | 240 | q446 | CLEAN |

Then `tools/auto_sync.py` (dry run) reported every region **in-sync** with the
picker recognised, and `AUTO_SYNC_APPLY` went back to 1.

## Safety measures used

- `AUTO_SYNC_APPLY=0` for the whole window (no unattended run could interleave).
- `backup_forms.py --form <id>` for all five forms first
  (`backups/<id>/*2026-09-12T2005*` / `*T2006*`); rollback per form is
  `restore_conditions.py --form <id> --from conditions-<stamp>.json --apply`,
  deleting the Club dropdown in the builder, and `question[hidden]=No`,
  `question[required]=Yes` on q5.
- Template first as the dress rehearsal, then regionals smallest first, each
  verified CLEAN before the next.
- The picker wording was committed to `main` (af43d64) before any apply, because
  the runner reads `PICKER_PROPS` from `main` and maintains the picker on every run.

## Left open

- Browser check (Ryan): pick a club → roster appears; language switch shows the
  translated picker; and whether two clubs can be selected at once (Jotform drops
  `maxSelection` on dropdowns) — if so, a guard rule is the next change.
- Salesforce: confirm the first submission through a picker form carries the
  plain club name in `Account_Name__c`.
- Native-speaker review of the new translations (VIEWS for Odia).
- Backlog 21: the 'Setidevi G.L.O.W club, Sokhel' orphan still sits on every form
  (one extra picker option); a sheet-side naming decision resolves it.
