# Backlog — from "launched" to "fully upgraded" by end of September 2026

Ordered by what unblocks the most. Effort is consultant days. Items marked
**needs Ryan** cannot be done by the tooling alone.

## Week 1 (right after launch)

| # | Item | Why | Effort | Who |
|---|---|---|---|---|
| 1 | **Disable the five defunct Jotforms** with a "moved" message once partners have the new links | two live forms per region = split submissions | 0.1 | needs Ryan's go, then one command |
| 2 | **Confirm Salesforce received the test batch** from the new Africa form; note what `enable_fuzzy_matching__c = false` does to matching | the matcher is unknown (Phase 5a); this is the first evidence | 0.2 | needs Ryan (SF admin) |
| 3 | **Set `STAFF_NOTIFY_EMAIL`** in the sheet's Script Properties; put the feedback link on the four attendance forms (`tools/add_feedback_link.py`) | problem reports go nowhere until then | 0.1 | Ryan + tooling |
| 4 | **Work the P1 rows of `data/needs_attention_2026-08-26.csv`** with partners: 16 rosters with a name listed twice (7 of these are currently on the forms with one girl missing), 8 re-submitted rosters, Otra Cosa's stale combined clubs, YWOU's Shinning/Shining Stars | every one of these is a girl who either does not appear on the form or appears twice | 1–2 elapsed weeks of emails; 0.3 tooling | needs Ryan/partners |
| 5 | **Confirm Haske's region** (Partners tab says Africa on thin evidence; row is marked PLEASE CONFIRM) | wrong region = wrong form | 0.05 | needs Ryan |
| 6 | Close the old enrollment Google Form (its owner) with a note pointing to the new ones | avoids a third path into the data | 0.05 | needs the form's owner |

## Weeks 2–3: Phase 2 — automatic Sheet → Jotform sync

The manual loop today is `export Roster → sync per region`. Phase 2 moves it
into the sheet so a New Club / Roster Modification submission reaches the
attendance form within the hour with nobody at a keyboard.

| # | Item | Effort |
|---|---|---|
| 7 | `Jotform.gs`: UrlFetchApp wrapper with the verified call shapes (form-urlencoded question POST merges; conditions PUT wholesale as JSON-encoded strings; 13-digit ids; sequential index/priority) — the API key lives in Script Properties | 0.5 |
| 8 | `Sync.gs`: port of the reconcile + `build_conditions` from `sync_attendance_form.py`, reading the Roster tab with a region filter; targets = the four regional form ids in `Config.gs` | 1.5 |
| 9 | Rollout ladder: dry-run → Audit tab; "Sync now" menu item; then the form handlers set a dirty flag and an hourly time trigger syncs if dirty, under LockService | 0.5 |
| 10 | **Parity harness**: same Roster export → Python dry-run and Apps Script dry-run → diff the planned calls; run before every risky change | 0.5 |
| 11 | Deploy the Apps Script with `clasp` instead of pasting (`tools/README-sheets.md`) so updates are one command | 0.2 |

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

## Data-quality and small things (any time)

| # | Item |
|---|---|
| 21 | Resolve the `RENAMED_ON_FORM` clubs (Otra Cosa ×3) and the "Setidevi G.L.O.W club , Sokhel" stray-space spelling so each club has one question; then delete the orphan questions from the template and regionals |
| 22 | Decide what to do with "Queens of Baleng" (on the Africa form with 20 girls, in no enrollment) — enroll it via the New Club form or drop it |
| 23 | `tools/form_status.py`: don't flag partner-disambiguated same-name clubs as "duplicates" |
| 24 | Prefilled attendance links per club (`?clubName=…&mentorEmail=…`) in the partner handover emails |
| 25 | Spanish-language mentor confirmation email for Latin America |
| 26 | Monthly three-way reconciliation report: Roster ↔ forms ↔ Salesforce |
| 27 | Salesforce REST auto-creation of Accounts for new clubs (replaces the SF Pending digest) |

## Explicitly not planned

Consolidating the four regional forms into one (only makes sense after the
widget pilot passes); splitting Africa (only if the pilot fails and slowness
becomes a real complaint).
