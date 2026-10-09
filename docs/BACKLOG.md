# Backlog

What is left to do, one section per item: open items first, by theme; finished and
dropped ones under [Done](#done) at the end. Until 2026-10-09 this was one table per
launch week, ordered by what unblocked the most; "Effort" is in consultant days, and
**needs Ryan** marks what the tooling cannot do alone.

- **A new item** goes at the end of its theme with the next free number - one more than
  the highest here (`grep -oE '^### [0-9]+' docs/BACKLOG.md | cut -c5- | sort -n | tail -1`).
  Never reuse, letter or renumber an item: code and docs cite them by number
  ("BACKLOG 50"), and `make check` fails on a cited number that does not exist.
- **An update** is a dated bullet at the end of the item (`- YYYY-MM-DD: …`) and, when it
  changes, the `Status:` line; earlier bullets stay as they are.
- **Status** is one of `open`, `in-progress`, `blocked-on-ryan`, `done YYYY-MM-DD` or
  `dropped`. A done or dropped item moves to "Done", number and text unchanged.
- A larger item has an intent under `docs/intent/` or a plan under `docs/plans/`.

## Launch follow-ups

### 1a. Rotate the Jotform API key

Status: blocked-on-ryan

- **Rotate the Jotform API key** (it sat in a Claude settings file); put the new one in `.env` and the GitHub secret; create a read-only key for monitoring
- Why: credential hygiene
- Effort: 0.05
- Who: needs Ryan

### 2. Confirm Salesforce received the test batch

Status: blocked-on-ryan

- **Confirm Salesforce received the test batch** from the new Africa form; note what `enable_fuzzy_matching__c = false` does to matching
- Why: the matcher is unknown (Phase 5a); this is the first evidence
- Effort: 0.2
- Who: needs Ryan (SF admin)

### 4. Work the P1 rows of the 2026-08-26 data-quality report

Status: blocked-on-ryan

- **Work the P1 rows of `data/needs_attention_2026-08-26.csv`** with partners: 16 rosters with a name listed twice (7 of these are currently on the forms with one girl missing), 8 re-submitted rosters, Otra Cosa's stale combined clubs, YWOU's Shinning/Shining Stars
- Why: every one of these is a girl who either does not appear on the form or appears twice
- Effort: 1–2 elapsed weeks of emails; 0.3 tooling
- Who: needs Ryan/partners

### 5. Confirm Haske's region

Status: blocked-on-ryan

- **Confirm Haske's region** (Partners tab says Africa on thin evidence; row is marked PLEASE CONFIRM)
- Why: wrong region = wrong form
- Effort: 0.05
- Who: needs Ryan

### 6. Close the old enrollment Google Form

Status: blocked-on-ryan

- Close the old enrollment Google Form (its owner) with a note pointing to the new ones
- Why: avoids a third path into the data
- Effort: 0.05
- Who: needs the form's owner

### 6a. Native-speaker check of the Odia labels

Status: blocked-on-ryan

- **Native-speaker check of the Odia labels** (`tools/translations_or.json`, 63 strings) by a VIEWS mentor; corrections re-applied with `tools/add_language.py --code or --name Oriya --dict … --apply`
- Why: the other languages came from Jotform's machine translation; Odia was written by us
- Effort: 0.1 + partner time
- Who: needs VIEWS

### 6b. Native-speaker check of the Hindi and Persian labels

Status: blocked-on-ryan

- **Native-speaker check of the Hindi and Persian labels** on the Asia form (`tools/translations_hi.json`, `tools/translations_fa.json`, 52 strings each, written 2026-09-20 with a three-lens review); corrections re-applied with `tools/add_language.py --form 262383129464057 --code hi --name Hindi --dict … --apply` (Persian: `--code fa --name Persian`)
- Why: written by us, like Odia; Persian readers may be Afghan (Dari)
- Effort: 0.1 + partner time
- Who: needs a Hindi and a Persian speaker

## The automatic sync

**Built 2026-09-01 as an event-driven loop instead** (`docs/intent/2026-09-01-auto-sync.md`):
the sheet's Apps Script notifies GitHub, a workflow runs the existing Python sync within
safety bands, and the `SyncLog` tab records every run. Items 7–9 are superseded; what remains:

### 10. Parity harness

Status: open

- **Parity harness** between the Python dry run and the runner's plan on the same export is now `test/python_test.py`; still open: a recorded-API replay test for `sync_attendance_form.py` itself (no network)
- Effort: 0.5
- 2026-10-09: `test/python_test.py` was split by subject (d708da8); the Python ↔ Apps Script parity tests are `test/gs_parity_test.py`.

### 11b. Duplicate-club guards

Status: in-progress

- **Duplicate-club guards** on the Club Roster Form (`docs/intent/2026-09-01-duplicate-club-guards.md`): hold and flag near-duplicate "new club" submissions instead of importing them; show the partner's clubs on the form
- **handler guard built 2026-09-28** on branch `wf/duplicate-club-guard` (`docs/plans/2026-09-28-duplicate-club-guard.md`), merged 2026-09-29, **deployed 2026-09-30 (the same-name push; RUNBOOK "Apps Script deploy")**
- remaining: the form-side "Is your club one of these?" question; the duplicates already imported (Reach All ×6, Otra Cosa, YWOU)
- Effort: 1

## Dynamic roster picker pilot (the "backend upgrade")

Replaces "every girl is a permanent form field" with "the roster is fetched
when the form is filled". Kills Africa's 3,900-checkbox weight and the
500-field ceiling, and removes most of the sync work.

### 12. `RosterApi.gs` web app

Status: open

- `RosterApi.gs` web app: `?club=…&partner=…&token=…` → JSON roster from the Roster tab, cached 5 min, shared-secret token in Script Properties
- Effort: 0.5

### 13. Jotform custom widget

Status: open

- Jotform custom widget (~200 lines): reads the club from the form, fetches the roster, renders checkboxes, returns the ticked names via `JFCustomWidget.sendData`; explicit error state + manual-entry fallback for weak connections
- Effort: 1.5

### 14. Register the widget on a copy of the Africa form

Status: open

- Register the widget, add it to a **copy** of the Africa form, repoint the integration's `Contact_IDs__c` row (the only mapping row that changes)
- Effort: 0.5

### 15. Side-by-side pilot with 3–5 Africa clubs

Status: open

- Side-by-side pilot with 3–5 Africa clubs for two weeks, at least one on a weak connection; compare every `Attendance_Batch__c` record with what the static form would have produced
- Effort: 1–2 elapsed weeks; 0.5

### 16. Decision gate

Status: open

- **Decision gate**: pass → all four regions move to the widget form (light forms; a single worldwide form becomes possible); fail → keep the static forms, nothing else changes
- Effort: —

## Girl IDs in Salesforce (gated)

### 17. 5a Identify the matcher

Status: open

- **5a Identify the matcher**: Object Manager → `Attendance_Batch__c` → triggers/flows; Apex search "Attendance"/"fuzzy"; debug log on a test submission. Deliverable: one page on how `Contact_IDs__c` names become Contacts
- Effort: 0.5–1 (needs Ryan's SF access)

### 18. 5b `Girl_ID__c` external ID on Contact

Status: open

- 5b `Girl_ID__c` external ID on Contact; backfill by exact normalized name within Account (script + Data Loader upsert); residue → ReviewQueue. Partial coverage is fine
- Effort: 1

### 19. 5c Matcher: exact `Girl_ID__c` lookup

Status: open

- 5c Matcher: exact `Girl_ID__c` lookup before the existing fuzzy fallback (sandbox first)
- Effort: 1 (needs SF dev)

### 20. 5d Sync writes checkbox `calcValues` = girl IDs

Status: open

- 5d Sync writes checkbox `calcValues` = girl IDs (verify the checkbox alignment convention on the template first); canary on one form, then the rest
- Effort: 0.5

### 20a. Deactivate, never delete — carried into Salesforce

Status: open

- **Deactivate, never delete — carried into Salesforce.** The sheet already does this (a removed girl's row stays with `status = inactive` and `removed_date`; her ID is never reused; she just leaves the attendance form). Salesforce has no equivalent signal yet: add an `Active__c` checkbox (or `Status__c` picklist + `Inactive_Date__c`) on Contact; the sync sets it from the Roster's status on every run (needs 5b's `Girl_ID__c` to find the Contact); no Contact is ever deleted or merged, so `Attendance_Batch__c` history and all historical counts stay exactly as they were. Reports and dashboards filter on `Active__c` for "current" numbers and ignore it for "all-time" ones.
- Until 5b lands, removed girls are visible in the Roster tab and the ReviewQueue only
- Effort: 0.5 (after 5b)

## Data quality and small things (any time)

### 21. Resolve the `RENAMED_ON_FORM` clubs

Status: in-progress

- Resolve the `RENAMED_ON_FORM` clubs (Otra Cosa ×3) and the "Setidevi G.L.O.W club , Sokhel" stray-space spelling so each club has one question; then delete the orphan questions from the template and regionals
- **Setidevi done 2026-09-30**: the orphan q158 (old spelling, 0 answers) deleted from all five forms, the picker entry gone (DECISIONS 2026-09-30); Otra Cosa's three remain

### 22. Decide what to do with "Queens of Baleng"

Status: blocked-on-ryan

- Decide what to do with "Queens of Baleng" (on the Africa form with 20 girls, in no enrollment) — enroll it via the New Club form or drop it

### 24. Prefilled attendance links per club

Status: open

- Prefilled attendance links per club (`?clubName=…&mentorEmail=…`) in the partner handover emails — a club whose name another partner's club shares is prefilled with its long picker entry (`<club> - <partner>`, the sync's `sf_names`), never the plain name

### 25. Spanish-language mentor confirmation email for Latin America

Status: open

- Spanish-language mentor confirmation email for Latin America

### 26. Monthly three-way reconciliation report

Status: open

- Monthly three-way reconciliation report: Roster ↔ forms ↔ Salesforce — a club's Salesforce Account name is what its roster sends to question 5 (the sync's `--summary-json` `sf_names`; `glow.sync.sf_club_name`), not always its plain name

### 27. Salesforce accounts for new clubs, automatically

Status: blocked-on-ryan

- Salesforce REST auto-creation of Accounts for new clubs (replaces the SF Pending section of the Monday e-mail; keep `sendSfPendingDigest`, its trigger and its ReviewQueue section).
- **Since 2026-09-30 every active club has its account** ([plan](plans/2026-09-30-salesforce-clubs.md), RUNBOOK "Club accounts in Salesforce"): this item is now only about clubs added or renamed afterwards - the account must be named as the picker sends it and linked to the partner; name each Account with the club's question-5 text (the sync's `--summary-json` `sf_names`), and never create one for a club the sync refused for its name.
- **Built 2026-10-06** ([plan](plans/2026-10-06-sf-new-club-accounts.md), RUNBOOK "New clubs' accounts, automatically"): v1 creates only; adopting a processor-made account, a rename and a partner move stay manual by decision, and the Monday e-mail keeps its SF Pending section for what still needs a person. Live once Ryan has done the setup and set `SF_SYNC`.
- **First real case 2026-10-03**: "Change Makers" and "Seeds of Greatness" (WESAD, on the roster since 10-01) had no account when their first attendance arrived, so the processor created partner-less club accounts (the attendance itself is fine). They are invisible to the dashboard's Partner filter and no-attendance table until their parent is set (found by the dashboard read-back of 2026-10-06; parent set to WESAD the same day on Ryan's go).
- Until `SF_SYNC` is `apply`, check after every new club: "Club accounts without a parent" in RUNBOOK "Club accounts in Salesforce" must be exactly the two pilots.
- **Cadence until then** (2026-10-06, [plan](plans/2026-10-06-attendance-totals.md) E, DECISIONS): the Monday e-mail's SF Pending list is worked each Monday, Ryan with Claude, as a round of the 2026-09-30 procedure, so a new club's account exists before its first attendance; a partner-less account the processor created meanwhile is re-parented, never re-created. Clubs the sync never puts on a form (a partner marked `jotform=no`) stay a hand create either way: BACKLOG 74.
- **Setup not done as of 2026-10-09**: none of the GLOW Sync user, the GLOW Club Sync permission set, the External Client App and the GitHub secrets `SF_CLIENT_ID` / `SF_CLIENT_SECRET` exists, so `SF_SYNC` cannot be switched on yet (read 2026-10-09; [plan 2026-10-09](plans/2026-10-09-attendance-reports-public.md), Context).
- Meanwhile two more partner-less club accounts came from the processor (Kawempe Youth Center's two new clubs, on the roster since 10-08); their parent was set on Ryan's go on 2026-10-09, 04:59 UTC

### 28. Close the Python ↔ Apps Script parity gaps

Status: open

- Close the Python ↔ Apps Script parity gaps (partner-less rows, `•`/`*` bullets, invisible characters in partner/club cells, region case) — `docs/intent/2026-09-01-parity-partnerless-rows.md`

### 30. A daily drift check; agent evals in CI

Status: open

- A daily drift check with a read-only key that writes intents on a band breach; agent evals in CI — `docs/intent/2026-09-01-ci-and-evals.md`

### 31. Plan mode by default

Status: open

- Turn on plan mode by default (`defaultMode: plan` in `.claude/settings.json`) after launch week

### 32. `form_status.py --roster` defaults to the stale offline build

Status: open

- `tools/form_status.py --roster` defaults to the stale offline build; default to the newest `data/roster_*.csv` or require the flag

### 33. `needs_attention.py` `REGION_UNSURE` is vacuous

Status: open

- `tools/needs_attention.py` `REGION_UNSURE` is vacuous once regions are derived from the live forms; decide what it should check

### 34. An `updated` timestamp column on the Roster tab

Status: open

- Add an `updated` timestamp column to the Roster tab so reactivations and region refreshes are visible per row (the Audit tab is the record today)

### 36. Partner → club two-step picker

Status: open

- Partner → club two-step picker on the attendance forms if the single long list (Africa: 204 clubs) bothers mentors

### 37. Pin `oauthScopes` in `appsscript.json`

Status: in-progress

- Pin `oauthScopes` explicitly in `appsscript/appsscript.json` and make `scripts/check_gs.js` fail when a `.gs` uses a Google service whose scope is not listed — a scope-set change becomes a visible diff instead of a silent trigger-breaker (review finding 2026-09-01)
- 2026-10-09: `scripts/check_gs.js` pins the 8 Google services in use and fails on a 9th (38dbc13, `make check`); `oauthScopes` in `appsscript/appsscript.json` is still not pinned.

### 38. Google Form: a REQUIRED region picker

Status: blocked-on-ryan

- **Google Form: a REQUIRED region picker** (Africa / Asia / Latin America / U.S) on the New Club branch instead of the optional free-text "Country where this club meets"; `handleNewClub_` uses it for new partners (the Partners tab still wins where it has a value) so a new partner's clubs reach an attendance form without waiting on staff — 7 of the 8 launch-week clubs arrived region-less and sat on no form until Ryan set the regions on 2026-09-02
- **built 2026-09-02** (`docs/plans/2026-09-02-region-picker.md`)
- remaining: Ryan's `clasp push` + GLOW → Google Forms → "Replace the Country question with the Region picker (one-time)"

### 39. Guard the rebuild after launch

Status: open

- **Guard the rebuild after launch**: "GLOW → Rebuild roster from enrollment responses" (and the offline `build_roster_offline.js` + `upload_roster.py --replace`) re-derive from the raw responses, so they reactivate girls removed through the Club Roster Form and re-create renamed or moved clubs under their old name or partner (`docs/plans/2026-09-24-move-club-partner.md`). Retire the menu item, or make it refuse once the Roster holds post-launch changes. The replay guard (41) does not cover it: the rebuild passes no sent day

### 40. Club Roster Form, Existing-club page

Status: in-progress

- **Club Roster Form, Existing-club page**: its help text ("Not listed? Your organization has no enrolled clubs yet — go back and choose "Enroll a NEW club"", meant for a missing organization) also sends a partner whose club sits under another spelling into enrolling it twice (new ids, and the second club reaches no attendance form: its name is in use). Point them at the problem report instead, and have the duplicate-club guards (11b) hold such a submission (built: a new club whose names sit in one club on file, of any partner, is held); a cross-partner check in `needs_attention.py` (one submitter e-mail, two partners) would have caught `ion bu`

### 42. Redo the Radiant Girls fix

Status: in-progress

- **Redo the Radiant Girls fix** undone by the 2026-09-13 replay: Club Roster Form → Existing club → Haske Humanitarian Aid Initiative → Radiant Girls → REMOVE the 20 names whose Roster `source` is `Roster Form Responses!2`; then SyncLog Africa `applied`, `form_status.py` CLEAN (q410 → 20), resolve ReviewQueue 27, check Salesforce attendance for those 20 since 09-13 — Ryan's go
- **done 2026-09-28** (by a service-account write + `auto_sync.py --apply`; the plan's Result)
- remaining: the Salesforce attendance check

### 43. Google Forms wording

Status: blocked-on-ryan

- **Google Forms wording**: the problem form's description points roster changes to the Club Roster Form ("Add or remove girls in a club that is already enrolled"); restore its reply-email question (hand-removed; all 11 reports came without one, so nobody can be answered); the Club Roster Form's "Something not working?" line says roster changes belong on that form; the new-club "Club name" help asks for the club's own name, and the REMOVE help says to copy the spelling from the club's attendance form
- **built 2026-09-28** as a one-time, previewing GLOW menu migration instead of hand edits; fresh builds match (`docs/plans/2026-09-28-forms-wording.md`); the menu item is **deployed 2026-09-30 (the same-name push; RUNBOOK "Apps Script deploy")**
- remaining: Ryan clicks GLOW → Google Forms → "Update the forms' wording (one-time; shows the changes first)"

### 46. Club Roster Form link on the attendance forms

Status: blocked-on-ryan

- **Club Roster Form link on the attendance forms** ("A girl missing, or no longer in your club? Tell us on the Club Roster Form.", above the problem-report link, translated)
- built 2026-09-28 on branch `wf/roster-form-link` ([plan](plans/2026-09-28-roster-form-link.md)); deploy (after 47's repair) = `tools/add_feedback_link.py --link roster --apply`, then `tools/add_translations.py --apply` — Ryan's go

### 47. Rosters render below the Submit button

Status: in-progress

- **Rosters render below the Submit button**: the sync creates a new roster at the form's highest order + 1, i.e. after Submit and the links above it.
- Read 2026-09-28: Africa 97 of 220 rosters, Asia 14 of 93, Latin America 26 of 39, U.S 5 of 12 (template 123 of 342) — every roster created since the 2026-08-24 overhaul; the public Africa page renders them after the button. A mentor of such a club sees her names below Submit (perhaps behind 35's empty submission).
- Fix: the sync creates new rosters above the first link element, plus a one-time move of the links, Submit and the hidden bridge fields below the last roster (no roster touched)
- **built 2026-09-29** on branch `wf5/rosters-above-submit` ([plan](plans/2026-09-29-rosters-above-submit.md)): the sync creates each new roster at the order of the last roster above the first link (`glow/layout.py`), instead of moving the tail on every create (rejected, DECISIONS 2026-09-29), `tools/fix_roster_order.py` is the one-time repair (9 order writes per form, dry run read-only on all five 2026-09-30), and `form_status` makes a roster below the links NOT CLEAN
- **done 2026-09-30** with Ryan's go: merged (`3ed68b2`), all five forms repaired and verified (every roster above the links and Submit, on the API and the public pages), the template's 23 new rosters created above Submit by the sync, `form_status` CLEAN everywhere ([Result](plans/2026-09-29-rosters-above-submit.md)). 45 and 46 can now go live.
- Remaining: re-count 35's empty submissions for two weeks (to 2026-10-14)

### 48. One club per attendance submission

Status: in-progress

- **One club per attendance submission** (the Club picker is a multi-select: 20 submissions since 09-01 picked 2-4 clubs, and question 5, the Salesforce field, got their names run together)
- **built 2026-09-29** on `wf5/club-guard` ([plan](plans/2026-09-29-club-guard.md); `sync_attendance_form.py --club-guard`: a warning below the picker, Submit hidden and disabled while question 5 is not exactly one club, the picker's `calcValues`; RUNBOOK "One club per submission").
- Ungated on the way: rules use the picker's own spelling (Africa's SUPER GIRLS roster could never show).
- **Done 2026-09-30** with Ryan's go: live on all five forms (template q482, U.S q445, Latin America q453, Asia q456, Africa q462), every `--rendered` check aligned, the warning translated, Ryan's browser checks passed ([Result](plans/2026-09-29-club-guard.md)).
- Separately: split or assign the 20 fused question-5 submissions **before** any Salesforce back-fill (nothing has reached Salesforce since 2026-03-28, so no junk Account exists yet); the 16 submissions with girls ticked but an empty Contact_IDs (mostly single-club) need their own investigation (**explained 2026-09-30**: 17 by then, the rule order - Jotform calculated question 18 before it showed the roster; fixed by 35's build).
- Follow-up (its own plan, it changes the runner): an apply that stops after the roster and picker writes leaves only the rules stale, and the runner then reports `in-sync` on every run (on `main` too: the new roster never shows; with the guard its mentors cannot submit). A check in the sync for live rules that miss a roster (show rule, Contact_IDs operand) or a picker option (guard terms), counted by the runner as a change, would let the next run repair it
- The back-fill must also map by hand the 10 Africa submissions since 09-01 whose question 5 is a bare shared name (Ruby 7, Super Girls 2, Shining Stars 1; 2 by the roster ticked, 8 carry no attendance): replayed as they are, "Ruby" would make Salesforce create a plain Account next to the two long-named ones (49)

### 50. Delete the dead partner-list code

Status: open

- **Delete the dead partner-list code** (retired by 49): `PARTNER_PICKER_PROPS`, `partner_choices` and `build_conditions`' `partner_field` in `sync_attendance_form.py`, `partner_picker` / `partner_fields` / `PARTNER_PICKER_NAME` in `glow/sync.py` (keep the refusal of a form carrying one), `PARTNER_PICKER_RX` and the `partner_picker` plan key in `tools/auto_sync.py`, the partner-list branches of `tools/rename_club.py` and `tools/add_translations.py`, and their tests (the plan `docs/plans/2026-09-28-partner-box.md` is marked superseded)

### 51. `tools/rename_club.py` cannot rename one of the seven same-name clubs

Status: open

- **`tools/rename_club.py` cannot rename one of the seven same-name clubs**: it finds a club's question by its text and refuses a form with two questions of the old name (Africa and the template hold two or three). Find the question by its text plus the partner in its long picker entry. A rename also needs the Salesforce Account renamed first (49, `--q5-change-ok`). The other side of finding a question by its text: a new club the sync did not add (its name was in use) has no question, and the one of that name is the other partner's — the tool refuses a question that holds another club's girls, and such a club is renamed with `--sheet-only` (built 2026-09-30, review fix). Related: a form built from scratch would refuse to create those seven rosters (a new roster whose name another partner's club has is never created) — a rebuilt form must be cloned from the template

### 52. Watch: a pick with an empty question 5 is blocked by the club guard

Status: open

- **Watch: a pick with an empty question 5 is blocked by the club guard.** One Latin America submission before the guard had a club picked but question 5 empty (the copy never ran); with the guard that mentor sees "You chose more than one club" and no Submit. Count submissions whose question 5 is not exactly one current picker entry (read-only), and look at the public page if a mentor reports it

### 53. The live gate does not know Salesforce

Status: in-progress

- **The live gate does not know Salesforce.** `.claude/hooks/live_gate.sh` catches `sf_backfill.py send --apply`, but not a direct `sf data …`, `sf apex run`, `sf api request rest` or a curl to `*.salesforce.com`, nor `sf org auth show-access-token` (which prints the token), now that a CLI login for production exists.
- Proposed pattern, tested on a scratch copy of the hook by the 2026-09-30 review: add `(^|[^[:alnum:]_./-])sf(dx)?[[:space:]]` and `salesforce\.com/services`, and deny reading `~/.sfdx` / `~/.sf` in `.claude/settings.json`. Ryan's file: his decision (it would also stop Claude's own read-only `sf` calls unless he exports `GLOW_LIVE_OK=1`)
- Since 2026-10-06 also `gh variable set` / `gh secret set` and `gh workflow run` (they switch the automatic sync's Salesforce writes, `SF_SYNC`): proposed, tested by the code review of 2026-10-06 on a scratch copy of the hook (blocks every write form including reruns and `-R`, passes `gh run list/view`, `gh workflow list`, `gh variable list`): `|gh[[:space:]]+(-R[[:space:]]+[^[:space:]]+[[:space:]]+|--repo[[:space:]=][^[:space:]]+[[:space:]]+)?(workflow[[:space:]]+(run|enable)|run[[:space:]]+rerun|(variable|secret)[[:space:]]+set)|repos/[^[:space:]]*/(dispatches|rerun[^[:space:]]*)|actions/variables`; and in `settings.local.json` move `Bash(gh workflow *)`, `Bash(gh variable *)`, `Bash(gh api *)` from allow to ask.
- Once the sheet's token is switched, drop the `repository_dispatch` trigger from the workflow. The sync's own write flag is `--apply-salesforce`, which the existing `--apply` pattern already catches
- 2026-10-09: `.claude/hooks/live_gate.sh` now gates `sf`/`sfdx` writes and deploys, the REST API, `--rehearse`, `gh variable|secret set|delete`, `gh workflow run` that applies, `gh run rerun` and `gh api` writes (8a04c16, cc43d1b, d9c7053; RUNBOOK "Live gate (Claude Code)"). Not done: denying `~/.sfdx` / `~/.sf` in `.claude/settings.json`, the `settings.local.json` moves, dropping the workflow's `repository_dispatch` trigger.

### 55. Monthly Report leftovers

Status: blocked-on-ryan

- **Monthly Report leftovers** (`docs/plans/2026-09-30-monthly-report-checkbox.md`): the new field is visible to System Administrator only (which other profiles?); an empty week is stored as 0, not blank; the production form sends a logged-out visitor to the **sandbox** login page (Ryan: leave it for now); the controller fails on an existing report when a save does not send three fields it reads back (the form always sends them).
- Also: on 2026-09-30 12:42 UTC another administrator re-activated the former staff administrator's user - Ryan to ask whether that was intended

### 56. Two clubs picked, then the form's own language switcher, lifts the club guard

Status: open

- **Two clubs picked, then the form's own language switcher, lifts the club guard** (found by the runtime review of `docs/plans/2026-09-30-contact-ids.md`, reproduced in headless Chrome on Asia and U.S copies; residual of 35's build, the old rule order and the new alike). The switcher (`formTranslation.v2.js`) saves each select's `selectedIndex`, writes it back after translating and recalculates. On a `<select multiple>` that keeps only one picked club (the one higher in the list, not the one picked first) and fires no event: question 5 becomes one club, the guard lifts and Submit comes back, while both rosters stay shown with their ticks and question 18 holds both. With required rosters (35's build) Submit then goes through only if every shown roster has a tick: ticks in one roster only are refused, the required message on the other roster (which may be the club she meant: she clears the picker and picks her club again, never ticks a girl of the other club; RUNBOOK "The names list sent to Salesforce"), and ticks in both still go through, all under the club kept (reproduced 2026-10-01 on a U.S copy).
- Adding "question 5 is filled" to every roster rule closed it in a prototype but tripled the checks per picker change and broke under fast arrow keys on Asia: not adopted.
- The structural answer is a **single-select Club picker** (the multi-select is what makes two clubs possible at all; Jotform's classic layout has no searchable single-select, so it means a plain list or another component).
- Until then the daily comparison of question 18 with the stored ticks (35's rollout) is the alarm: ticks stored in two rosters, or question 18 names outside the picked club

### 57. Jotform's required message is English on the template, Africa, Asia and Latin America

Status: open

- **Jotform's required message is English on the template, Africa, Asia and Latin America** (found by the runtime review of `docs/plans/2026-09-30-contact-ids.md`, read 2026-10-01). Every form's translation store holds key `9303c9bd…` (the md5 of "This field is required.") in 11 languages (Odia none, and Asia's Hindi and Farsi none), but only U.S has it in `base`, and the runtime finds a translation through `base` only. So `JotForm.texts.required` stays English in every language there: the Club picker's message today, and with 35's required rosters the roster's too (the no-tick case, 64 of September's 484 submissions).
- Fix: add the `base` (and `en`) source of that one text by GET, merge, POST (CLAUDE.md rule 9), on Ryan's go, and Odia, Hindi and Farsi translations of it. `tools/add_translations.py` cannot do it as it stands: it posts an addition only when the English is a question's visible text, and this text is Jotform's own, so it needs a small change for Jotform's runtime texts first. Independent of 35's rollout, which expects English there (RUNBOOK, browser step 7)

### 58. Attendance rate on the dashboard

Status: open

- **Attendance rate on the dashboard ("% of the maximum attendance possible")** - the line chart Ryan asked for on 2026-10-02, left out because Salesforce has no enrolled count (`docs/plans/2026-10-02-attendance-dashboard.md`, "Later"). Ryan's definition: a session's maximum is the girls active on that club's roster in the sheet **on the session date** (the Roster's `added_date` / `removed_date`; removed girls drop out from their removal date), only for sessions held; **nothing more on the forms**.
- Needs: two number fields on `Attendance_Batch__c` (girls present = its attendance rows; girls enrolled), a small repo tool that fills them from the roster export (club code → account id from `data/sf_prep_2026-09-30/created_accounts*.csv`, dry run, then `--apply` on Ryan's go, idempotent), a sessions report type with the summary formula SUM(present) / SUM(enrolled), then a line by week and a number for last month. Keeping it current without a hand run needs Salesforce access from GitHub Actions or a nightly Salesforce flow

### 59. Region on the attendance dashboard

Status: open

- **Region on the attendance dashboard.** Region is on the partner account (`Parent.Region__c`: Africa, Asia, North America, South America), not on clubs, and the report type `Accounts_Contacts_Attendance` cannot reach the partner's fields.
- Either a new report type (base `Attendance__c` with lookups to the club, its partner and the partner's region), or a region on every Club account kept by the club tooling; then a Region dashboard filter (4 values) and charts by region

### 60. Attendance dashboard leftovers

Status: blocked-on-ryan

- **Attendance dashboard leftovers** (RUNBOOK "Attendance dashboard in Salesforce").
- **Decided 2026-10-09 (Ryan), reversing 2026-10-06 on (1)**: (1), (2), (4) and (5) are addressed by [plan 2026-10-09](plans/2026-10-09-attendance-reports-public.md) - both folders shared Viewer with All Internal Users, the permission set `Attendance_Report_Viewer` (Read on the attendance objects and the 21 fields the folders' reports use, View All on Contact and Account) for the 9 GLOW Standard Users, the shared "Portal Login" account included by Ryan's choice, "(test)" dropped from the two labels, the daily refresh as Ryan's Subscribe; built and validated check-only 2026-10-09, done once Ryan has deployed, scheduled the refresh and the set is assigned.
- Still open: (6) and (7).
- **Decided 2026-10-06 (Ryan)**: folder sharing stays as it is (hidden; administrators only), and girls' names are fine for anyone with Salesforce access, so (1) and (3) below are closed.
- (1) share the two Attendance folders, with whom - closed 2026-10-06 with no change, reopened and decided 2026-10-09 (above); (2) record sharing, only if the folders are ever shared beyond administrators: the dashboard runs as Ryan, but a chart opens its report as the viewer, and club accounts are private (administrator-owned, no sharing rules), so a standard user sees few or no rows there; options: give leadership View All Data, or add a sharing rule on Club accounts (and check that the Contacts and `Attendance__c` rows follow it: the report type reads all three); (3) the test report's detail rows carry girls' names - closed, allowed inside Salesforce; (4) a daily scheduled refresh (Refresh > Schedule Refresh); (5) drop "(test)" from the names once it is the real one; (6) the Partner filter holds 49 of its 50 values by hand: a new or renamed partner needs an edit; (7) `BATCH-000500` (Niñas Emprendedoras y Empoderadas, submitted 2026-10-04) carries the session date 2026-03-09, probably 3 September typed day first (found by the verification of 2026-10-09): it stays open until the club confirms the date; a guard on the forms is 79

### 62. The names-dictionary audit runs only after an apply

Status: open

- **The names-dictionary audit runs only after an apply** (found by the live-safety review of `docs/plans/2026-10-02-names-and-modules.md`). `form_status.py` flags a roster option the form's own translation dictionary alters, and the runner's verify step runs it after every apply; a region with nothing to apply (U.S, Latin America on a quiet week) is not audited until someone runs `form_status.py` by hand. A stale entry typed in the builder's Translations page would then reach Salesforce for days. Add the names check (one GET per form, counts only) to the runner's in-sync path, raising ATTENTION, or run `form_status.py` daily in the workflow (about 0.2 days)

### 63. Other regions' girls' names on each public page

Status: blocked-on-ryan

- **Other regions' girls' names on each public page**: every form's `base`/`en` store was cloned from the template and is embedded in its public page (window.allTranslations): Africa's holds about 1,660 entries that are roster names of other forms, Asia's 2,790, Latin America's 3,720, U.S's 5,190 (read 2026-09-30), about 500 KB per page.
- Pruning them is a larger decision than the stale-spelling fix (fix 1 of `docs/plans/2026-10-02-names-and-modules.md` removed only the 55 entries that alter a name); `tools/fix_name_translations.py` (save, POST `base`+`en`, re-read, page check, `--restore`) is where it would be built.
- Mind that all five forms' options count for a girl who moves region. Needs Ryan's decision

### 64. Watch: Jotform's translation runtime changes without notice

Status: open

- **Watch: Jotform's translation runtime changes without notice.** `glow/translation_lookup.py` emulates `formTranslation.v2.js` as read 2026-10-02 (builds `62a8b57dd95` regional, `fc726a121d4` template, byte-identical; the older `9e75d6f1d83` differs only in entries missing in `en`/`base`, and the audits run both). When `form_status.py --rendered` prints a new runtime build, re-read `setDictionary`, `trimMultiSpaces`, `sanitizeKeys`, `simplifyfWord` and `translateUncached` against the module (a diff of those five functions is enough; a byte-identical `formTranslation.v2.js` needs no more).
- Seen 2026-10-06: `7a7e75787df` (Asia), `9083adfcdff` then `2bdb1ec3fa8` (Africa), whose `formTranslation.v2.js` is byte-identical to the 2026-10-02 builds' (`2bdb1ec3fa8`'s `jotform.forms.js` adds a payment total to a calculation's operand state and reshapes the autofill restore: no change to the checkbox reader, the rules or `data-calcvalue`); later that day (the module-shape proof, `--rendered`): template `bc6c80d556a`, Africa / Asia / Latin America `8705c008453`, U.S `18bdf84aedc` - their `formTranslation.v2.js` and the submit handler's `clearFieldOnHide` branch (67) not yet re-read

### 65. Residual: a resend restored after a submit can carry ticks with an empty question 18

Status: open

- **Residual: a resend restored after a submit can carry ticks with an empty question 18.** The required rosters stop a submission with no tick, and the Contact_IDs rule order keeps question 18 equal to the ticks under every club change; but a page the browser restores after a submit fires no change event, so question 18 can arrive empty with girls ticked. Seen once since the guard (2026-10-02 to 10-06): STRIKER GLOW CLUB 2026-10-03, a resend 20 minutes after a complete submission — Salesforce refused it as a duplicate (BATCH-000471; BATCH-000470 holds the 17 girls).
- Ryan decided 2026-10-06: **no extra form rule**; the Salesforce backstop is **deployed since 2026-10-07 03:22 UTC** (`docs/plans/2026-10-06-attendance-totals.md`, B): a batch with no names and no count is now `Failed` "No participants submitted" instead of Success - no rows, and it no longer blocks the club's day. It makes such a submission visible as a blank; it cannot bring back the ticked names, which stay in Jotform only.
- Keep watching with the back-fill resolver's `q18_empty` flag on new submissions

### 68. Gold versus retention

Status: open

- **Gold versus retention** (Jotform's upload space). Silver caps uploaded files at 10 GiB in all - the group photos, about 1.9 MB each; 1.25 GiB = 12.5 % on 2026-10-06. At the current pace (about 950 submissions and 1.8 GB a month) the account passes 50 % around mid-December 2026, 80 % around February 2027 and the cap around mid-March 2027; at September's pace 50 % in mid-February 2027 and the cap around August 2027 - arithmetic, not a fact. At about 50 % (the `storage:` line of `form_status.py` reads `warn`) Ryan decides: **Gold** (100 GiB and 10,000 submissions a month; the API's plan record says $594 a year at the nonprofit rate against Silver's $234, the pricing page $99 a month billed yearly - read the bill Jotform would actually charge on the day) or a **retention policy** (deleting and purging old submissions in Jotform, which also starves `tools/backfill_resolve.py` and the question-18 comparison for the purged period: the CEO's decision, with Drive holding the photos from the integration's start).
- Open: whether GLOW's bill is already at the nonprofit rate (billing was not read; Jotform's nonprofit pricing page, approval in 2-3 days). From 80 % `auto_sync.py` raises an ATTENTION every morning naming the limit. Never switch on Auto Delete Submissions before this is decided ([plan](plans/2026-10-06-photos-to-drive.md), RUNBOOK "Photos" step 7)

### 69. The 677 photos taken before the Drive integration

Status: open

- **The 677 photos taken before the Drive integration** (every submission up to 2026-10-06) stay in Jotform, behind its login. Leave them (recommended), or export them by hand into the same Drive folders: about half a day of clicking and a second copy of minors' photos to govern. Only if staff ask; Ryan decides ([plan](plans/2026-10-06-photos-to-drive.md))

### 70. Watch: the Google Drive token can lapse silently

Status: open

- **Watch: the Google Drive token can lapse silently.** Jotform raises no alarm when the Drive integration's Google token expires or is revoked (a password change, a session revocation): the copies stop and nothing says so. Nothing in the repo can see it either (`integration_status.py` can at most say the block exists, once its key is known).
- The check is by eye once a month: the newest subfolder's date in each `Attendance photos - <Region>` folder against the form's newest submission; a week's gap with newer submissions means remove and re-add the integration on that form (RUNBOOK "Photos" step 6).
- A repo check would need Drive access from the Mac or the runner (a role-account credential): not built

### 71. The retired rosters' option lists stay on the forms

Status: open

- **The retired rosters' option lists stay on the forms** (751 names on the Africa form, 155 on the U.S form once its clubs are deactivated): a retired roster is hidden, off the Club picker and never written to ([plan](plans/2026-10-06-clubs-off-jotform.md); RUNBOOK "Clubs that do not use Jotform"), so the names stay in its options and in the form's `base`/`en` translation store exactly as today - nothing new is written anywhere.
- Blanking them would be the first write of an empty option list to a checkbox question (untested; the disabled U.S form is unreachable) and would have to clear the store's entries too (63).
- Ryan's default 2026-10-06: leave them; a later, tested step with his go if staff ask

### 72. The intake for partner-reported attendance counts is not decided

Status: blocked-on-ryan

- **The intake for partner-reported attendance counts is not decided** (`docs/plans/2026-10-06-attendance-totals.md`, F; Ryan is gathering information). Three partners' clubs leave the Jotform forms and report a monthly total per club instead, as an `Attendance_Batch__c` with `Girls_Present__c` typed, `Creator__c` `Partner report`, no names and the last day of the month as its date (the contract: RUNBOOK "Attendance totals and partner-reported counts").
- Options: a small Jotform "aggregate attendance" form with its own Salesforce mapping; a screen flow or the plain record form in Salesforce for the coordinator; a sheet tab the partners fill and a dry-run repo tool (`tools/sf_aggregate_send.py`, built like `sf_backfill.py`) sends monthly.
- Whichever: the club name must be the account's exactly, or the processor creates a partner-less account.
- Its own plan once Ryan decides; the first aggregates land only after the three partners' clubs are off the Africa picker (plan 3)

### 73. The three legacy blank `Success` batches

Status: open

- **The three legacy blank `Success` batches** (one club each, dated 2026-09-30, 2026-09-30 and 2026-10-01; plus one February pilot batch): stored before the processor's backstop, no rows, no names. After `tools/sf_girls_present.py set` they carry `Girls_Present__c` 0, which is how the blank-submissions report finds them; each still blocks its club's day for a late re-submission (`Duplicate`).
- Ryan's default 2026-10-06: leave them; if he wants those days open, three record deletes with his go (no rows to remove; nothing to roll back)

### 74. Club accounts for clubs on no form

Status: blocked-on-ryan

- **Club accounts for clubs on no form** (from the photos/clubs-off-Jotform plans, 2026-10-06): the automatic sync creates accounts only for clubs it puts on a form, so a new club of a partner that does not use Jotform (jotform=no) gets none and stays in SF Pending for a hand create. A second trigger, "an active Roster club on no form with no account", would close it: Ryan's decision

### 76. Days where Salesforce holds fewer rows than ticks

Status: blocked-on-ryan

- **Days where Salesforce holds fewer rows than ticks** (same plan): Maridians 2026-09-17, 09-24 and 09-30 have 11-12 rows against 19-20 ticks - the fuller re-submissions were refused as same-day duplicates - and 11 back-fill sessions are held as `salesforce_has_different_count`. Needs a way to add the missing girls to a day that already has a batch (the processor keeps only the first per club and day): Ryan's decision on each

### 77. 11 girls with contacts in both "Las Camelias" and "Las Camelias Primaria"

Status: blocked-on-ryan

- **11 girls with contacts in both "Las Camelias" and "Las Camelias Primaria"** (same plan; `sf_dupes.py check --roster` reports them under (d)): two club accounts for what may be one club or two. A club decision first (one club or two, which account), then, if one, a move of the account's contacts and rows - not a merge of girls across clubs, which the tool never does

### 78. A guard in `tools/sf_backfill.py` against deleting back-fill contacts that carry live rows

Status: open

- **A guard in `tools/sf_backfill.py` against deleting back-fill contacts that carry live rows** (same plan): since 2026-10-02 live ticks attach to back-fill contacts, and the duplicate merge keeps the back-fill's contact; deleting one cascades to its live attendance rows (RUNBOOK "Back-fill of attendance into Salesforce", Rollback, WARNING). `status` (and any rollback helper) should count, per listed contact, the rows whose batch is not in the ledger and refuse to name such a contact for deletion

### 79. A session-date guard on the attendance forms

Status: blocked-on-ryan

- **A session-date guard on the attendance forms** (from the verification of 2026-10-09, BACKLOG 60 (7)): `BATCH-000500` reached Salesforce dated 2026-03-09, probably 3 September typed day first.
- Proposal: the session date must lie within the season (on or after 2026-09-01) and not in the future, else a hidden warning shows and Submit is held, as the club guard does it (48). The rule is generated by the sync from a `glow/sync.py` constant (the season's first day), never added by hand (CLAUDE.md rule 3); the date widget's own min/max limits are the alternative to compare; check the form's date question format and how "today" behaves across the mentors' time zones; Spanish, French and the other languages need the warning text (translations). Ryan's decision on the rule and the season's first day

## Done

### 1. Disable the five defunct Jotforms

Status: done 2026-09-30

- **Disable the five defunct Jotforms** with a "moved" message once partners have the new links (`docs/intent/2026-09-01-disable-defunct-forms.md`)
- **done 2026-09-30** (read 2026-10-06: all five `status: DISABLED` with the default "This form is currently unavailable!" page; how they were switched off is not in the repo — the builder, presumably; RUNBOOK "The forms")
- Why: two live forms per region = split submissions
- Effort: 0.1
- Who: done

### 1b. Switch on the automatic sync

Status: done 2026-09-12

- **Switch on the automatic sync** (`docs/RUNBOOK.md`, "Automatic sync": secrets, PAT, Script Properties, `clasp push`, Set up tabs, Request Jotform sync now, then `AUTO_SYNC_APPLY=1` after a dry-run day)
- **done 2026-09-12** (`AUTO_SYNC_APPLY=1` after ten days of clean dry runs and the picker rollout verified in-sync)
- Why: no more manual export → sync loop
- Effort: 0.2
- Who: needs Ryan

### 1c. Club picker rollout

Status: done 2026-09-12

- **Club picker rollout** — verified on the template 2026-09-01
- **done 2026-09-12**: on all four regional forms with the training guide's wording, plus the Partner Coordinator Email / Group Photo changes (`docs/plans/2026-09-12-picker-rollout.md`); the browser check that only one club can be picked found the opposite (20 multi-club submissions by 09-29): the guard is 48
- Why: mentors pick the club instead of typing it; wrong club names become impossible
- Effort: 0.2
- Who: Ryan decides the date; then one command per form

### 3. Set `STAFF_NOTIFY_EMAIL`; the feedback link on the attendance forms

Status: done 2026-09-28

- **Set `STAFF_NOTIFY_EMAIL`** in the sheet's Script Properties; put the feedback link on the four attendance forms (`tools/add_feedback_link.py`)
- Why: problem reports go nowhere until then
- Effort: 0.1
- Who: Ryan + tooling
- 2026-10-09: status from evidence elsewhere: the problem-report link (q443) was read on all five live forms on 2026-09-28 (`test/links_layout_test.py`), and the Monday e-mail goes to `STAFF_NOTIFY_EMAIL` (RUNBOOK "Working the ReviewQueue"); the day each was done is not recorded.

### 7. `Jotform.gs`: UrlFetchApp wrapper

Status: dropped

- ~~`Jotform.gs`: UrlFetchApp wrapper~~ — superseded by the GitHub Actions runner (no Jotform key in the sheet)
- Effort: —

### 8. `Sync.gs`: port of the reconcile + `build_conditions`

Status: dropped

- ~~`Sync.gs`: port of the reconcile + `build_conditions`~~ — superseded; the Python tool is the one implementation
- Effort: —

### 9. Rollout ladder / hourly trigger

Status: dropped

- ~~Rollout ladder / hourly trigger~~ — superseded by `repository_dispatch` + the daily backstop
- Effort: —

### 11. Deploy the Apps Script with `clasp`

Status: done 2026-08-27

- ~~Deploy the Apps Script with `clasp`~~ — done 2026-08-27 (`npm run clasp:push`, `appsscript/INSTALL.md`)
- Effort: —

### 11a. De-duplicate the Python tools

Status: done 2026-09-02

- **De-duplicate the Python tools** into a `glow/` package (`docs/intent/2026-09-01-shared-jotform-client.md`); make "nothing to do" real by skipping an unchanged conditions rewrite
- Effort: 1
- 2026-10-09: status from evidence elsewhere: step 6 of `docs/plans/2026-09-01-ai-native-sdlc-adoption.md` shipped 2026-09-02 (`cec1c6c`): the `glow/` package, twelve scripts migrated, the conditions-equality skip (`docs/intent/2026-09-01-shared-jotform-client.md`: done). The next consolidation is Phase 3 of `docs/plans/2026-10-09-repo-cleanup.md`.

### 23. `form_status.py`: same-name clubs are not duplicates

Status: done 2026-09-30

- `tools/form_status.py`: don't flag partner-disambiguated same-name clubs as "duplicates"
- **done 2026-09-30** for clubs that have their own picker entry (`<club> - <partner>`): two questions of one text count as duplicates only while they test the same text; rosters the typed Partner box still tells apart (a form not switched yet) are still listed

### 29. Move `backup_forms.py` / `restore_conditions.py` into `tools/`

Status: dropped

- Move `backup_forms.py` / `restore_conditions.py` into `tools/` (doc references only)
- 2026-10-09: decided against: the rollback pair stays at the root (CLAUDE.md conventions), `backup_forms.py` stays the thin CLI there and `tools/` stays flat (`docs/plans/2026-10-09-repo-cleanup.md`, Phase 3, accepted by Ryan 2026-10-09).

### 35. At least one girl ticked per submission

Status: done 2026-10-02

- Decide whether the attendance forms should require at least one girl ticked (hide Submit while `Contact_IDs` is empty) — a mentor submitted with no names; with the Club picker an unknown club is impossible, a zero-girl submission still is
- **decided 2026-09-30 and built 2026-10-01** on `wf8/contact-ids` ([plan](plans/2026-09-30-contact-ids.md); RUNBOOK "The names list sent to Salesforce"): every roster carries Jotform's `required` flag (only the shown roster is checked, one tick satisfies it; 64 of September's 484 submissions had no tick), and question 18 is recalculated after the rosters change (the Contact_IDs sum is rule 0 with the picker as an operand).
- **Live on all five forms 2026-10-02** (template 2026-10-01 16:37 UTC, U.S 01:44, Latin America 02:01, Asia 02:02, Africa 02:04; [Result](plans/2026-09-30-contact-ids.md))

### 41. Replay guard

Status: done 2026-09-30

- **Replay guard** (follow-up to `docs/plans/2026-09-27-formlog-key.md`): `planClub_` / `planModification_` must not reactivate a girl whose `removed_date` is after the submission (optional `entry.submitted`; `loadRoster_` normalises Date cells through the sheet's zone; the mentor e-mail echoes only typed names). Passing `submitted` from the rebuild also defuses 39
- **built 2026-09-28** on branch `wf/replay-guard` (`docs/plans/2026-09-28-replay-guard.md`) for the two Club Roster Form handlers, merged 2026-09-29, **deployed 2026-09-30 (the same-name push; RUNBOOK "Apps Script deploy")**. The rebuild and the offline builder still pass no sent day (39 stays open)

### 44. The Club Roster Form's free text reaches `setValues` unstripped

Status: done 2026-09-30

- The Club Roster Form's free text (club, typed partner, names) reaches `setValues` unstripped: a leading `=` becomes a formula in the sheet. Strip it as `feedbackReviewItem_` does for problem reports
- **built 2026-09-28** on branch `wf/duplicate-club-guard` (`sheetText_` / `parseFormRoster_`; a name keeps its inner words so it still matches the Roster, and `newRosterRow_` strips `last_name`), **deployed 2026-09-30 (the same-name push; RUNBOOK "Apps Script deploy")**

### 45. Partner list for club names two partners share

Status: dropped

- ~~Partner list for club names two partners share~~ (built 2026-09-28 on `wf/partner-box`, `docs/plans/2026-09-28-partner-box.md`)
- **superseded 2026-09-30, never deployed**: each such club has its own Club picker entry instead (49; `docs/plans/2026-09-30-same-name-clubs.md`), `--partner-picker` is refused, and the typed Partner box is hidden on every form by the sync. 36 stays the answer to "the club list is too long"

### 49. Clubs that share a name send `<club> - <partner>` to Salesforce

Status: done 2026-09-30

- **Clubs that share a name send `<club> - <partner>` to Salesforce** (`docs/plans/2026-09-30-same-name-clubs.md`; RUNBOOK "Club names two partners share")
- Part 1 (the forms) **built 2026-09-30** on `wf6/same-name-forms`: each roster keeps the form it has, `--same-name-switch` by hand, a new club with a name in use is not created, any other question-5 change needs `--q5-change-ok`, q331 hidden, `restore_conditions.py` refuses a pre-switch snapshot.
- **Forms done 2026-09-30** with Ryan's go: merged (`d238b43`), the template, Asia and Africa switched (7 / 1 / 6 long names), q331 hidden on all five, every form CLEAN and `--rendered` aligned, the runner in-sync with no ATTENTION ([Result](plans/2026-09-30-same-name-clubs.md)).
- **Apps Script pushed 2026-09-30** (Part 2: the Club Roster Form hold and the Monday e-mail's Account names) and the seven Salesforce Accounts created from the live picker strings the same day ([plan](plans/2026-09-30-salesforce-clubs.md)). Remaining before the Salesforce reconnect: one template test submission with a long name

### 54. The Contact duplicate rule alerts, and an alert refuses a girl created by code

Status: done 2026-10-01

- **The Contact duplicate rule alerts, and an alert refuses a girl created by code.** "First & Last & Account" is Allow + Alert + Report on create (read 2026-09-30). When a club has two girls with the same last name and similar first names (about 16 rosters), the attendance processor fails mid-batch: a Failed batch, part of the girls saved, the club's day blocked. It hit the live flow and the back-fill alike.
- **Done 2026-10-01 11:26 UTC** on Ryan's go: Report only (deploy 0AfRP000002foFp0AI, read back, proven with two fictional test contacts that were deleted); the back-fill plans with `--dup-rule-ok`.
- Left: the duplicate reports it now fills are worth a look once a month

### 61. Possible duplicate girls in Salesforce

Status: done 2026-10-07

- **Possible duplicate girls in Salesforce** (found by the dashboard verification, 2026-10-02): 14 pairs of Contacts have the same name at the same club, 11 of which never attend the same session, so they are probably one girl created twice (by the old name matching, e.g. a difference in capitals, accents or spacing). About 0.5% of the girls counted; read-only listing by club first, then a merge with Ryan's go (merging moves attendance rows).
- **Taken up 2026-10-07** ([plan](plans/2026-10-07-sf-duplicate-girls.md)): the census found 15 girls with 19 extra contacts in 5 clubs, made by the altered names; `tools/sf_dupes.py` built the same day (`check` / `plan` / `merge` / `rename` / `cleanup`; RUNBOOK "Duplicate girls in Salesforce"); its `check` is the monthly look.
- Left out of that plan: 75 to 78

### 66. Batches with a Spanish `Module__c`

Status: done 2026-10-07

- **Batches with a Spanish `Module__c`** (6 batches, 43 rows as of 2026-10-06, all Latin America's, created 2026-10-01..05 by the live flow after the September back-fill; none more since the module `calcValues` went live there, 2026-10-06 11:17 UTC): corrected in place by `tools/fix_module_values.py` ([plan](plans/2026-10-06-module-selection.md), (b); RUNBOOK "The names dictionary and the module values") - the dry run first (it pairs each batch with its one submission and lists the rest `UNMATCHED`), then `--apply` with Ryan's go, batch and rows, each read back, with a ledger for `--undo`.
- Until then the dashboard's "Jotform Sessions by Module Last Month" (built on `Attendance__c` rows of the last calendar month, `gen.py` `Jotform_Sessions_by_Module_Last_Month`) shows a Spanish bar beside the English one for each module concerned: in October's view the two September-dated batches (Autodefensa, Toma de decisiones), in November's the three October-dated ones - which is why the rows are corrected, not only the batches. Closed when the dry run after the apply says `nothing to correct`
- **done 2026-10-07** (Ryan's go, VPN off): 0 validation rules on either object (Tooling API); the dry run paired all 6 batches (5 Success, 1 Failed; 43 rows; the newest created 2026-10-05) with exactly one Latin America submission each, 0 `UNMATCHED`; `--apply --limit 1` (one batch and its 8 rows), then the other 5 (35 rows): 49 records, every one `written` in the ledger (`data/module_fix_2026-10/`); the dry run again → `nothing to correct: 0 of 595 batches`; `GROUP BY Module__c` since 09-01 on both objects = 17 canonical English values (the module chart reads the `Attendance__c` ones; its session told)

### 67. `form_status` pins the module chain's shape

Status: done 2026-10-06

- **`form_status` pins the module chain's shape** (single-select, required, form-level `clearFieldOnHide=disable`; `module shape:` line, `--rendered` reads the served `JotForm.clearFieldOnHide` and refuses a module select served `multiple`) - **built 2026-10-06** ([plan](plans/2026-10-06-module-selection.md), RUNBOOK "The names dictionary and the module values"): a builder change becomes NOT CLEAN, not a silent change of what Salesforce receives. The audit's premise is Jotform's runtime (build `fc726a121d4`; 64 lists the builds seen since, not yet re-read): when `--rendered` prints a new build, re-read the submit handler's `clearFieldOnHide` branch (64's pattern)

### 75. The attendance processor's name match

Status: done 2026-10-07

- **The attendance processor's name match** (from `docs/plans/2026-10-07-sf-duplicate-girls.md`, "Not in this plan"): it compares a ticked name with the club's contacts exactly (capitals ignored), so any spacing difference makes a new contact, and it reads the club's contacts without `ORDER BY`, so with two copies of a girl the row goes to whichever comes first.
- Fix: `normalizeSpace()` on both sides of the comparison and `ORDER BY CreatedDate` on the contacts. Vendor code (`AttendanceBatchProcessor`): its own plan, a check-only deploy, Ryan's go
- **Done 2026-10-07** ([plan](plans/2026-10-07-processor-name-spacing.md)): names cleaned when parsed (format characters removed, any whitespace run one space), both sides compared clean, new girls stored clean, the club's contacts read oldest first; validated 33/33, deployed 04:38 UTC, proven rolled back

## Explicitly not planned

Consolidating the four regional forms into one (only makes sense after the
widget pilot passes); splitting Africa (only if the pilot fails and slowness
becomes a real complaint).
