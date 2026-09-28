# Backlog — from "launched" to "fully upgraded" by end of September 2026

Ordered by what unblocks the most. Effort is consultant days. Items marked
**needs Ryan** cannot be done by the tooling alone. Week 1 = the week of
2026-09-01 (launch day). Larger items have an intent under `docs/intent/`.

## Week 1 (right after launch)

| # | Item | Why | Effort | Who |
|---|---|---|---|---|
| 1 | **Disable the five defunct Jotforms** with a "moved" message once partners have the new links (`docs/intent/2026-09-01-disable-defunct-forms.md`) | two live forms per region = split submissions | 0.1 | needs Ryan's go, then one command |
| 1a | **Rotate the Jotform API key** (it sat in a Claude settings file); put the new one in `.env` and the GitHub secret; create a read-only key for monitoring | credential hygiene | 0.05 | needs Ryan |
| 1b | **Switch on the automatic sync** (`docs/RUNBOOK.md`, "Automatic sync": secrets, PAT, Script Properties, `clasp push`, Set up tabs, Request Jotform sync now, then `AUTO_SYNC_APPLY=1` after a dry-run day) — **done 2026-09-12** (`AUTO_SYNC_APPLY=1` after ten days of clean dry runs and the picker rollout verified in-sync) | no more manual export → sync loop | 0.2 | needs Ryan |
| 1c | **Club picker rollout** — verified on the template 2026-09-01 — **done 2026-09-12**: on all four regional forms with the training guide's wording, plus the Partner Coordinator Email / Group Photo changes (`docs/plans/2026-09-12-picker-rollout.md`); still open: the browser check that only one club can be picked | mentors pick the club instead of typing it; wrong club names become impossible | 0.2 | Ryan decides the date; then one command per form |
| 2 | **Confirm Salesforce received the test batch** from the new Africa form; note what `enable_fuzzy_matching__c = false` does to matching | the matcher is unknown (Phase 5a); this is the first evidence | 0.2 | needs Ryan (SF admin) |
| 3 | **Set `STAFF_NOTIFY_EMAIL`** in the sheet's Script Properties; put the feedback link on the four attendance forms (`tools/add_feedback_link.py`) | problem reports go nowhere until then | 0.1 | Ryan + tooling |
| 4 | **Work the P1 rows of `data/needs_attention_2026-08-26.csv`** with partners: 16 rosters with a name listed twice (7 of these are currently on the forms with one girl missing), 8 re-submitted rosters, Otra Cosa's stale combined clubs, YWOU's Shinning/Shining Stars | every one of these is a girl who either does not appear on the form or appears twice | 1–2 elapsed weeks of emails; 0.3 tooling | needs Ryan/partners |
| 5 | **Confirm Haske's region** (Partners tab says Africa on thin evidence; row is marked PLEASE CONFIRM) | wrong region = wrong form | 0.05 | needs Ryan |
| 6 | Close the old enrollment Google Form (its owner) with a note pointing to the new ones | avoids a third path into the data | 0.05 | needs the form's owner |
| 6a | **Native-speaker check of the Odia labels** (`tools/translations_or.json`, 63 strings) by a VIEWS mentor; corrections re-applied with `tools/add_language.py --code or --name Oriya --dict … --apply` | the other languages came from Jotform's machine translation; Odia was written by us | 0.1 + partner time | needs VIEWS |
| 6b | **Native-speaker check of the Hindi and Persian labels** on the Asia form (`tools/translations_hi.json`, `tools/translations_fa.json`, 52 strings each, written 2026-09-20 with a three-lens review); corrections re-applied with `tools/add_language.py --form 262383129464057 --code hi --name Hindi --dict … --apply` (Persian: `--code fa --name Persian`) | written by us, like Odia; Persian readers may be Afghan (Dari) | 0.1 + partner time | needs a Hindi and a Persian speaker |

## Weeks 2–3: Phase 2 — automatic Sheet → Jotform sync

**Built 2026-09-01 as an event-driven loop instead** (`docs/intent/2026-09-01-auto-sync.md`):
the sheet's Apps Script notifies GitHub, a workflow runs the existing Python sync within
safety bands, and the `SyncLog` tab records every run. Items 7–9 are superseded; what remains:

| # | Item | Effort |
|---|---|---|
| ~~7~~ | ~~`Jotform.gs`: UrlFetchApp wrapper~~ — superseded by the GitHub Actions runner (no Jotform key in the sheet) | — |
| ~~8~~ | ~~`Sync.gs`: port of the reconcile + `build_conditions`~~ — superseded; the Python tool is the one implementation | — |
| ~~9~~ | ~~Rollout ladder / hourly trigger~~ — superseded by `repository_dispatch` + the daily backstop | — |
| 10 | **Parity harness** between the Python dry run and the runner's plan on the same export is now `test/python_test.py`; still open: a recorded-API replay test for `sync_attendance_form.py` itself (no network) | 0.5 |
| ~~11~~ | ~~Deploy the Apps Script with `clasp`~~ — done 2026-08-27 (`npm run clasp:push`, `appsscript/INSTALL.md`) | — |
| 11a | **De-duplicate the Python tools** into a `glow/` package (`docs/intent/2026-09-01-shared-jotform-client.md`); make "nothing to do" real by skipping an unchanged conditions rewrite | 1 |
| 11b | **Duplicate-club guards** on the Club Roster Form (`docs/intent/2026-09-01-duplicate-club-guards.md`): hold and flag near-duplicate "new club" submissions instead of importing them; show the partner's clubs on the form — **handler guard built 2026-09-28** on branch `wf/duplicate-club-guard` (`docs/plans/2026-09-28-duplicate-club-guard.md`), not merged or deployed; remaining: Ryan's review, merge, `clasp push`; the form-side "Is your club one of these?" question; the duplicates already imported (Reach All ×6, Otra Cosa, YWOU) | 1 |

## Weeks 3–4: Phase 2.5 — dynamic roster picker pilot (the "backend upgrade")

Replaces "every girl is a permanent form field" with "the roster is fetched
when the form is filled". Kills Africa's 3,900-checkbox weight and the
500-field ceiling, and removes most of the sync work.

| # | Item | Effort |
|---|---|---|
| 12 | `RosterApi.gs` web app: `?club=…&partner=…&token=…` → JSON roster from the Roster tab, cached 5 min, shared-secret token in Script Properties | 0.5 |
| 13 | Jotform custom widget (~200 lines): reads the club from the form, fetches the roster, renders checkboxes, returns the ticked names via `JFCustomWidget.sendData`; explicit error state + manual-entry fallback for weak connections | 1.5 |
| 14 | Register the widget, add it to a **copy** of the Africa form, repoint the integration's `Contact_IDs__c` row (the only mapping row that changes) | 0.5 |
| 15 | Side-by-side pilot with 3–5 Africa clubs for two weeks, at least one on a weak connection; compare every `Attendance_Batch__c` record with what the static form would have produced | 1–2 elapsed weeks; 0.5 |
| 16 | **Decision gate**: pass → all four regions move to the widget form (light forms; a single worldwide form becomes possible); fail → keep the static forms, nothing else changes | — |

## Week 4+: Phase 5 — girl IDs in Salesforce (gated)

| # | Item | Effort |
|---|---|---|
| 17 | **5a Identify the matcher**: Object Manager → `Attendance_Batch__c` → triggers/flows; Apex search "Attendance"/"fuzzy"; debug log on a test submission. Deliverable: one page on how `Contact_IDs__c` names become Contacts | 0.5–1 (needs Ryan's SF access) |
| 18 | 5b `Girl_ID__c` external ID on Contact; backfill by exact normalized name within Account (script + Data Loader upsert); residue → ReviewQueue. Partial coverage is fine | 1 |
| 19 | 5c Matcher: exact `Girl_ID__c` lookup before the existing fuzzy fallback (sandbox first) | 1 (needs SF dev) |
| 20 | 5d Sync writes checkbox `calcValues` = girl IDs (verify the checkbox alignment convention on the template first); canary on one form, then the rest | 0.5 |
| 20a | **Deactivate, never delete — carried into Salesforce.** The sheet already does this (a removed girl's row stays with `status = inactive` and `removed_date`; her ID is never reused; she just leaves the attendance form). Salesforce has no equivalent signal yet: add an `Active__c` checkbox (or `Status__c` picklist + `Inactive_Date__c`) on Contact; the sync sets it from the Roster's status on every run (needs 5b's `Girl_ID__c` to find the Contact); no Contact is ever deleted or merged, so `Attendance_Batch__c` history and all historical counts stay exactly as they were. Reports and dashboards filter on `Active__c` for "current" numbers and ignore it for "all-time" ones. Until 5b lands, removed girls are visible in the Roster tab and the ReviewQueue only | 0.5 (after 5b) |

## Data-quality and small things (any time)

| # | Item |
|---|---|
| 21 | Resolve the `RENAMED_ON_FORM` clubs (Otra Cosa ×3) and the "Setidevi G.L.O.W club , Sokhel" stray-space spelling so each club has one question; then delete the orphan questions from the template and regionals |
| 22 | Decide what to do with "Queens of Baleng" (on the Africa form with 20 girls, in no enrollment) — enroll it via the New Club form or drop it |
| 23 | `tools/form_status.py`: don't flag partner-disambiguated same-name clubs as "duplicates" |
| 24 | Prefilled attendance links per club (`?clubName=…&mentorEmail=…`) in the partner handover emails |
| 25 | Spanish-language mentor confirmation email for Latin America |
| 26 | Monthly three-way reconciliation report: Roster ↔ forms ↔ Salesforce |
| 27 | Salesforce REST auto-creation of Accounts for new clubs (replaces the SF Pending section of the Monday e-mail; keep `sendSfPendingDigest`, its trigger and its ReviewQueue section) |
| 28 | Close the Python ↔ Apps Script parity gaps (partner-less rows, `•`/`*` bullets, invisible characters in partner/club cells, region case) — `docs/intent/2026-09-01-parity-partnerless-rows.md` |
| 29 | Move `backup_forms.py` / `restore_conditions.py` into `tools/` (doc references only) |
| 30 | A daily drift check with a read-only key that writes intents on a band breach; agent evals in CI — `docs/intent/2026-09-01-ci-and-evals.md` |
| 31 | Turn on plan mode by default (`defaultMode: plan` in `.claude/settings.json`) after launch week |
| 32 | `tools/form_status.py --roster` defaults to the stale offline build; default to the newest `data/roster_*.csv` or require the flag |
| 33 | `tools/needs_attention.py` `REGION_UNSURE` is vacuous once regions are derived from the live forms; decide what it should check |
| 34 | Add an `updated` timestamp column to the Roster tab so reactivations and region refreshes are visible per row (the Audit tab is the record today) |
| 35 | Decide whether the attendance forms should require at least one girl ticked (hide Submit while `Contact_IDs` is empty) — a mentor submitted with no names; with the Club picker an unknown club is impossible, a zero-girl submission still is |
| 36 | Partner → club two-step picker on the attendance forms if the single long list (Africa: 204 clubs) bothers mentors |
| 37 | Pin `oauthScopes` explicitly in `appsscript/appsscript.json` and make `scripts/check_gs.js` fail when a `.gs` uses a Google service whose scope is not listed — a scope-set change becomes a visible diff instead of a silent trigger-breaker (review finding 2026-09-01) |
| 38 | **Google Form: a REQUIRED region picker** (Africa / Asia / Latin America / U.S) on the New Club branch instead of the optional free-text "Country where this club meets"; `handleNewClub_` uses it for new partners (the Partners tab still wins where it has a value) so a new partner's clubs reach an attendance form without waiting on staff — 7 of the 8 launch-week clubs arrived region-less and sat on no form until Ryan set the regions on 2026-09-02 — **built 2026-09-02** (`docs/plans/2026-09-02-region-picker.md`); remaining: Ryan's `clasp push` + GLOW → Google Forms → "Replace the Country question with the Region picker (one-time)" |
| 39 | **Guard the rebuild after launch**: "GLOW → Rebuild roster from enrollment responses" (and the offline `build_roster_offline.js` + `upload_roster.py --replace`) re-derive from the raw responses, so they reactivate girls removed through the Club Roster Form and re-create renamed or moved clubs under their old name or partner (`docs/plans/2026-09-24-move-club-partner.md`). Retire the menu item, or make it refuse once the Roster holds post-launch changes. The replay guard (41) does not cover it: the rebuild passes no sent day |
| 40 | **Club Roster Form, Existing-club page**: its help text ("Not listed? Your organization has no enrolled clubs yet — go back and choose "Enroll a NEW club"", meant for a missing organization) also sends a partner whose club sits under another spelling into enrolling it twice (new ids, Partner-gated roster). Point them at the problem report instead, and have the duplicate-club guards (11b) hold such a submission (built: a new club whose names sit in one club on file, of any partner, is held); a cross-partner check in `needs_attention.py` (one submitter e-mail, two partners) would have caught `ion bu` |
| 41 | **Replay guard** (follow-up to `docs/plans/2026-09-27-formlog-key.md`): `planClub_` / `planModification_` must not reactivate a girl whose `removed_date` is after the submission (optional `entry.submitted`; `loadRoster_` normalises Date cells through the sheet's zone; the mentor e-mail echoes only typed names). Passing `submitted` from the rebuild also defuses 39 — **built 2026-09-28** on branch `wf/replay-guard` (`docs/plans/2026-09-28-replay-guard.md`) for the two Club Roster Form handlers; remaining: Ryan's review and merge, then `clasp push` (no new Google service, so no re-authorization). The rebuild and the offline builder still pass no sent day (39 stays open) |
| 42 | **Redo the Radiant Girls fix** undone by the 2026-09-13 replay: Club Roster Form → Existing club → Haske Humanitarian Aid Initiative → Radiant Girls → REMOVE the 20 names whose Roster `source` is `Roster Form Responses!2`; then SyncLog Africa `applied`, `form_status.py` CLEAN (q410 → 20), resolve ReviewQueue 27, check Salesforce attendance for those 20 since 09-13 — Ryan's go — **done 2026-09-28** (by a service-account write + `auto_sync.py --apply`; the plan's Result); remaining: the Salesforce attendance check |
| 43 | **Google Forms wording** (Ryan, in the Forms editor, mirrored in `Forms.gs` for fresh builds): the problem form's description points roster changes to the Club Roster Form ("Add or remove girls in a club that is already enrolled"); restore its reply-email question (hand-removed; all 11 reports came without one, so nobody can be answered); the Club Roster Form's "Something not working?" line says roster changes belong on that form |
| 44 | The Club Roster Form's free text (club, typed partner, names) reaches `setValues` unstripped: a leading `=` becomes a formula in the sheet. Strip it as `feedbackReviewItem_` does for problem reports — **built 2026-09-28** on branch `wf/duplicate-club-guard` (`sheetText_`; names word by word, `sheetName_` / `parseFormRoster_`, so `last_name` is safe too), not deployed |
| 45 | **Partner list for club names two partners share** (review finding 1, 2026-09-27: the typed Partner box needed the partner's full Roster spelling, so "HAFAI" showed the Ruby mentor no roster) — **built 2026-09-28** on `wf/partner-box` (`docs/plans/2026-09-28-partner-box.md`; `sync_attendance_form.py --partner-picker`); remaining, each on Ryan's go: accept the plan, merge, then with `AUTO_SYNC_APPLY=0` the template and then Africa: dry run, `--apply`, `form_status` CLEAN, browser check (RUNBOOK "The partner list"); then tell the Ruby / HAFAI mentor. Also check in the browser: on Asia, Latin America and U.S the typed Partner box has no rule and is not hidden, so it probably shows on every submission there (optional, ignored) — hide it with `update_static_fields.py` if so. 36 stays the answer to "the club list is too long" |

## Explicitly not planned

Consolidating the four regional forms into one (only makes sense after the
widget pilot passes); splitting Africa (only if the pilot fails and slowness
becomes a real complaint).
