---
title: The two club-days the November back-fill skipped - AusCam Club 3 2026-10-03 merged, San Pedro Sacatepequez 2026-10-17 sent as a special event
author: Claude (ticket #244, on Ryan's go of 2026-11-19)
status: in-progress      # ticket #244; the tool support is built 2026-11-20, the two live sends wait on Ryan's go
created: 2026-11-20
intent: ticket #244 - left over from #238's November back-fill; Ryan 2026-11-19 - "build the tool support and do AusCam Club 3 first"
---

# Plan: back-fill the two club-days #238 skipped (ticket #244)

Procedure: RUNBOOK "Back-fill of attendance into Salesforce" and its "Correction for a day Salesforce
already has (`merge`)". Counts only here; the resolved rows are in #238's back-fill folder
`data/backfill_2026-11` (never committed).

## Context
- **San Pedro Sacatepequez, 2026-10-17** (Latin America): one report, module `Special Event - IDG
  Celebrations`, week blank by design (a special event has no session week:
  [special events](2026-10-13-special-events.md), Decisions 1), year 1. `sf_backfill.py plan` held it
  `module_not_usable` because it wanted a week for every module. Ryan asks the partner to confirm the
  report's own module before it is sent.
- **AusCam Club 3, 2026-10-03** (Asia): Salesforce has the original `BATCH-000498`, `Success`, 18 rows,
  module `Elective - Understanding our World`, week 2, year 3. Three reports of that module, weeks 1, 2
  and 3, all dated 2026-10-03, 26 girls each. The week-2 report is the same session as the original.
  `plan` held the day `salesforce_has_different_count`, `send` never adds to a day Salesforce has, and
  the day was never a Failed "Duplicate" batch, so `resend` does not see it either.

## The change (ticket #244)
- `tools/sf_backfill.py`:
  - a special-event session with a blank week is queued when its year is usable and sent with
    `Module_Week__c` blank (`glow.sync.is_special_event`, never a list of event names);
  - the `decisions.csv` clause `merge` and the hold `merge_without_original`;
  - the `merge` subcommand: a dry run by default, `--apply`, `--only`, `--limit`, `--vpn-off` in both
    modes, `merge_ledger.csv` and `merge_added.csv`. It shares `resend`'s live prediction (`read_day`,
    `read_contacts`, `predict`) and its insert, read-back and settle (now one implementation for both);
  - `close` and `status` read the merge ledger too.
- Tests by the test author: `test/sf_backfill_merge_test.py` (new) and a special-event case in
  `test/sf_backfill_test.py`.
- `docs/RUNBOOK.md`, `docs/ARCHITECTURE.md`, `.claude/skills/salesforce/SKILL.md`, this plan. Nothing in
  Salesforce's metadata, no form, no sheet, nothing under `appsscript/`.

## Rollout (live, Ryan's go; VPN off)
1. **AusCam Club 3 first.** In #238's back-fill folder `data/backfill_2026-11`, change the
   `decisions.csv` line for key `001RP00000yElpvYAC|2026-10-03` from `skip` to
   `use <the week-2 report's submission id>; merge; accept club_has_earlier_contacts+more_new_girls_than_proven`
   (the week-2 report is the original's session; `plan` counts its 26 names as up to 26 new girls, more
   than the 22 proven in one batch, while the day already has 18 rows - the dry run counts the real ones).
2. `python3 tools/sf_backfill.py --dir data/backfill_2026-11 snapshot --vpn-off`, then `plan`: the key is
   a planned merge (one), nothing new held.
3. `merge --vpn-off` (dry run): one line for the key, the original `BATCH-000498`, 26 names ticked and
   the girls to add (up to 8) and new contacts it predicts; record the counts below.
4. `merge --apply --vpn-off --only '001RP00000yElpvYAC|2026-10-03'` (a key holds a `|`: quoted, and the
   live gate then asks Ryan rather than passing it on its own; with one planned merge `--limit 1` is the
   same): read back `ok`.
5. `python3 tools/sf_girls_present.py check` (differ 0) and `sf_backfill.py --dir data/backfill_2026-11 status`.
6. **San Pedro Sacatepequez**, after Ryan confirms the report's own module with the partner: change the
   `decisions.csv` line for key `001RP00000yEn04YAC|2026-10-17` from `skip` to
   `accept club_has_earlier_contacts`. Without it `plan` still holds the session: the club has 15
   participants in Salesforce, none made by this tool (#238 only showed `module_not_usable` because that
   hold comes first). With it Ryan accepts that a girl whose name is spelled differently in the report
   than on her Contact becomes a second Contact. Then `snapshot --vpn-off`, `plan` (queued: 11 names, a
   blank week, year 1, nothing else held), `send --vpn-off` (dry run),
   `send --apply --vpn-off --only '001RP00000yEn04YAC|2026-10-17'` (the fetch must be under
   `MAX_AGE_HOURS` old: run the resolver again first if it is not), then `sf_girls_present.py check`.

## Rollback (only with Ryan's go)
- AusCam: by id from `merge_added.csv` - the attendance rows the merge added to `BATCH-000498`, then each
  listed contact only while it carries no other attendance row, then the merge batch (`batch_id` in
  `merge_ledger.csv`); set `BATCH-000498`'s `Girls_Present__c` back to its own rows
  (`sf_girls_present.py check`); `close '001RP00000yElpvYAC|2026-10-03' --removed`.
- San Pedro: as any back-fill batch - by id from `ledger.csv` and `created_contacts.csv` (RUNBOOK
  "Back-fill of attendance into Salesforce", Rollback), then `close '001RP00000yEn04YAC|2026-10-17' --removed`.
- The tool change itself: revert the commit; the ledgers it wrote stay as the record.

## Result
