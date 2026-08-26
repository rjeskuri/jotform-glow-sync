# GLOW Enrollment → Attendance → Salesforce Workflow Automation

## Context

The 2026-08-24 overhaul made the Jotform attendance side maintainable: the
enrollment Google Sheet is the source of truth and
[sync_attendance_form.py](/Users/ryaneskuri/jotform-glow-sync/sync_attendance_form.py)
regenerates rosters + all conditional logic from a CSV export. Still manual or
fragile: (1) every new enrollment response requires a manual CSV download + a
sync run; (2) new-club enrollment and roster changes share one free-text
Google Form, causing the duplicate/rename mess; (3) girls reach Salesforce as
fuzzy-matched NAMES, so same-name girls collide and history is fragile.

Ryan (part-time consultant) wants: automatic flow-through, two purpose-built
Google Forms (new club / roster modification, changes never delete Salesforce
history), and an immutable unique girl ID (club+lastname+digits) — without
changing the stack (Google Forms/Sheets, Jotform, Salesforce; Apps Script is
in-stack).

## Verified findings (Jotform API, read-only)

- All six forms (master `260555608160556`, 4 regionals, working copy
  `262352490535154`) carry a **byte-identical native Salesforce V2
  integration**: insert-only creates of `Attendance_Batch__c`
  (clubName→`Account_Name__c`, contact_ids→`Contact_IDs__c` 32KB textarea,
  module/week/year, photo). No webhooks or middleware anywhere. Region is not
  captured in the mapping at all.
- Girl→Contact matching happens **inside Salesforce** (unknown Apex/Flow) by
  fuzzy name matching; `contact_ids` carries plain comma-separated names today.
- **The ID hook already exists**: every club checkbox has empty `calcValues`;
  filling it makes attendance submit IDs with zero integration-mapping changes.
- **enableFuzzy bug**: qid 109 is hidden+required with nothing selected →
  `enable_fuzzy_matching__c` receives blank on every submission.
- Limits (Silver plan): 500 fields/form (working copy ~352), 2,500
  submissions/month (~330 clubs weekly ≈ 1,300/mo), 50k API calls/day.
- Master still has the old 465-rule architecture (3 error-flagged rules);
  regionals drifted independently (50–428 conditions).
- **Africa form anatomy** (the "extra slots" question): 222 live questions —
  200 of them club roster checkboxes holding 3,923 girl options. The scary
  427 lastQuestionID is churn, not live weight: 205 question IDs were consumed
  by questions created and later deleted during manual upkeep. So Africa is at
  222/500 fields, not 427/500. It also carries **10 duplicate club questions**
  (the five CCCYD clubs that re-submitted enrollment each got a SECOND
  question instead of an update, plus Ruby/Super Girls/Shinning Stars/Joy
  Club/Angels Club pairs) and 6 error-flagged rules. **Slowness cause**:
  ~3,900 checkbox inputs in the DOM plus 428 old-style conditions with 208
  separate calculation bindings re-evaluated as users interact. The new
  architecture halves the condition load; the DOM load only drops by putting
  fewer clubs on each form (Phase 4 split) or by not putting rosters in the
  form at all (Phase 2.5 widget).
- **Cloning preserves the Salesforce integration**: the working copy is itself
  a clone of master and inherited the identical integration config — evidence
  that clone-based migration keeps SF wiring intact (verify with one test
  submission per clone).
- ⚠️ **The pre-upgrade backup form `262352734718057` is DELETED** (status
  verified via API; not deleted by this session). The original pre-upgrade
  state survives ONLY as local JSON snapshots in the session scratchpad —
  making Phase 0's snapshot preservation urgent. The report artifact's
  rollback row should be corrected when convenient.

## The Salesforce mapping (why clone/widget risk is bounded)

The whole integration is 8 mapping rows keyed to **question numbers**, not
rosters (verified byte-identical, 1,721 chars, on both the working copy and
Africa):

| Salesforce field | ← qid | |
|---|---|---|
| `Account_Name__c` (required) | 5 | clubName |
| `Attendance_Date__c` | 17 | date |
| **`Contact_IDs__c`** (32KB textarea) | **18** | contact_ids |
| `Module__c` | 98 | module_id |
| `Module_Week__c` | 100 | week_id |
| `Module_Year__c` | 102 | year_id |
| `Creator__c` | 105 | creator |
| `enable_fuzzy_matching__c` | 109 | enableFuzzy |
| (attachment) | 19 | photo |

The 329 roster questions appear nowhere in the mapping — they only feed qid 18
via calculation. Consequences: **cloning inherits the mapping perfectly**
(zero mapping work per regional), and the **widget changes exactly one row**
(qid 18's source), leaving the other seven untouched. Both are verified by a
single test submission landing correctly in `Attendance_Batch__c`.

## User decisions

- Salesforce: native integration confirmed; Ryan **has SF admin access**; the
  matching automation is unknown → ID rollout is phase-gated so fuzzy name
  matching keeps working until the matcher is identified. **No hybrid
  "Name [ID]" strings in contact_ids ever** (they'd poison fuzzy matching).
- Both new Google Forms generated via Apps Script; the Roster Modification
  form uses **partner-branched pages** (47 partner sections, each with only
  its own 5–30 clubs) rather than one 330-item dropdown — searchable-feeling
  for non-technical mentors while staying entirely in Google Forms.
- **Keep the 4 regional attendance forms** (no consolidation); the automation
  manages them with per-region club filters. No region column exists today →
  a Partners→region mapping tab is required. Ryan has no region list to type
  in, so the mapping is **derived** from the regional forms themselves (roster
  overlap + club-name match per club, majority vote per partner) — see
  `tools/derive_partner_regions.py`.
- Regionals are rebuilt by **cloning the upgraded working copy and relabeling**,
  not by editing the drifted live forms.
- **Prototype the dynamic roster widget FIRST** (new Phase 2.5), before
  regional cloning — Ryan chose the bigger long-term payoff over the fastest
  relief. If the pilot succeeds, regionals are cloned from the widget-based
  form and stay permanently light (and the Africa split may become
  unnecessary); if it fails, fall back to static clones + the Africa split.

## Girl ID design (used from Phase 1 onward)

`{CLUBCODE}-{LASTCODE}-{NNN}`, e.g. `DEMOCLUB-SAMPLE-001`.

- **CLUBCODE** minted once per club in a **ClubRegistry** tab (NFKD → strip
  diacritics → uppercase alphanumerics → truncate to 8; digit suffix on
  collision). The registry is authoritative — renames and primaria/secundaria
  splits never change existing IDs; a stale club code inside an ID is expected
  and documented (the ID is opaque).
- **LASTCODE**: last token of the normalized name, same transliteration
  (~107 non-ASCII surnames in real data), truncated to 12; one-token names
  (10 exist) use that token.
- **NNN**: per (CLUBCODE, LASTCODE) sequence from a registry high-water mark;
  never reused, even after removal. Same-name girls get -001/-002 after the
  sheet disambiguation the sync already enforces by freezing.
- **Write-once**: the script never regenerates an ID. Re-enrollment matches
  normalized full name within club → reactivates the existing row, same ID.

## Phases (each independently shippable; stop anywhere and be better off)

### Phase 0 — Guardrails & quick fixes (half day)
- **First**: copy the session-scratchpad snapshots into the durable repo
  `~/jotform-glow-sync/backups/` — original pre-upgrade state
  (`properties.json`, `questions.json`, `emails_verbatim.json` from
  `/private/tmp/claude-501/-Users-ryaneskuri/286ab1f0-b277-4137-8062-be2677d79d45/scratchpad/jotform/`),
  current post-sync state (`properties_final.json`, `questions_final.json`),
  and `enrollment_full.csv`. Then snapshot questions/properties/emails for
  master + all 4 regionals via GET. (The scratchpad is session-ephemeral and
  the backup form is gone — this is the rollback foundation.)
- **Rehearse a restore once**: PUT the saved working-copy conditions back onto
  the working copy and verify round-trip, so the rollback path is proven.
- Fix **enableFuzzy** on all 6 forms: `POST /form/{id}/question/109` — make it
  not-required with a selected default (`false` unless the SF matcher review
  says otherwise), so `enable_fuzzy_matching__c` stops receiving blank.
- Check master for live submissions; fix its 3 error-flagged rules only if
  still actively used (it's retired in Phase 4).
- Record a per-form qid map (verify structural qids 5/17/18/19/94–105/109 by
  name via GET — don't assume clone equality).

Verify: test submission on working copy → `Attendance_Batch__c` shows
enable_fuzzy populated. Rollback: snapshots + builder Revision History.

### Phase 1 — Canonical Roster tab + ID backfill (1–2 days, Sheet-only)
- New tabs in the existing spreadsheet: **Roster** (girl_id, partner, club,
  region, first/last, status active|inactive, added/removed dates, source),
  **Partners** (47 rows; region **prefilled from `Regions.gs`** — derived
  2026-08-24 by `tools/derive_partner_regions.py` from which regional form each
  partner's clubs sit on: 47/47 resolved, 0 conflicts, 1 thin (Haske, one
  matched club); the tab overrides the derived map), **ClubRegistry**,
  **ReviewQueue**, **Audit**.
- `Normalize.gs` (bound Apps Script): direct port of `parse_roster` /
  `read_sheet` from the Python tool — invisible-Unicode stripping, numbering
  removal, case-insensitive last-submission-wins, dup-name freezing routed to
  ReviewQueue.
- One-time backfill: 353 raw rows → ~328 clubs / ~6,210 girls with minted IDs.
  Jotform API key lives in Script Properties, never in code.
- ReviewQueue seeded with known messes: 16 dup-name rosters, the
  17-single-girl-rows club, the 32-token paste-error line, stale combined
  clubs from partner splits.

Verify: counts and per-club rosters match a Python-tool dry-run on the same
export (this parity check anchors everything later). A club whose partner has
no region **queues, never silently drops**.

### Phase 2 — Automated Sheet → Jotform sync, working copy only (2–3 days)
- `Jotform.gs`: UrlFetchApp wrapper mirroring the Python `Jotform` class —
  identical verified semantics (conditions PUT wholesale as JSON-encoded
  strings, 13-digit unique ids, sequential index/priority; form-urlencoded
  question POSTs merge; new qids return as ints → stringify).
- `Sync.gs`: port of reconcile + `build_conditions` (rule categories A/B/C),
  reading the **Roster tab**.
- Rollout ladder: dry-run→Audit tab → manual "Sync now" menu → installable
  onFormSubmit trigger setting a dirty flag + hourly time-trigger syncing if
  dirty, with LockService against overlap. Incremental runs are a handful of
  API calls — Apps Script's 6-min limit is a non-issue (the heavy 329-question
  build is already done).
- **Parity harness**: export Roster → run Python dry-run and Apps Script
  dry-run → diff planned calls. Run before every risky change, forever.

Verify: test enrollment row → club appears on working copy with correct
visibility rule; cascade intact; contact_ids aggregate still emits names.
Rollback: delete the trigger (kill switch); PUT snapshot conditions.

### Phase 2.5 — Dynamic roster widget pilot (2–4 days, working copy only)
Replaces "every girl is a permanent form field" with "the roster is fetched at
fill time". Kills the DOM weight (Africa's ~3,900 checkboxes), the 500-field
ceiling, and most of the sync work in one move.

**What it is**: a Jotform *custom widget* — a small web page embedded in the
form as one field. Ours reads the club from the form, looks that club up in
the Roster tab, renders just those ~20 girls as checkboxes, and writes the
ticked girls (names now, IDs after Phase 5) as its field value.

**Build**:
- Apps Script **web app** (`RosterApi.gs`, `doGet`) deployed as a URL:
  `?club=X&partner=Y&token=…` → JSON roster from the Roster tab. Shared-secret
  token in Script Properties; deployed "execute as me / anyone with link".
  Cache with `CacheService` (5 min) so fill-time latency stays low.
- Widget page (~200 lines HTML/JS): fetches the roster, renders checkboxes,
  calls Jotform's widget API (`JFCustomWidget.subscribeToSendData` /
  `sendData`) to hand back a comma-separated value. Must handle: club not
  found, network failure (show a clear error + a manual-entry fallback so a
  mentor is never blocked), and slow connections (partners are in low-bandwidth
  regions — this is the pilot's key question).
- Register in Jotform (My Widgets → custom widget URL), add to a **copy** of
  the working copy, and re-point the integration's `Contact_IDs__c` row from
  qid 18 to the widget field. The other seven mappings are untouched.

**Verify**: side-by-side pilot — the widget form and the current static form
both live; run a handful of real clubs through the widget form for 1–2 weeks
(including at least one low-bandwidth partner) and confirm every
`Attendance_Batch__c` record matches what the static form would have produced.

**Decision gate**: if fill-time reliability holds → regionals clone from the
widget form (Phase 4 shrinks dramatically; Africa split likely unnecessary; a
single worldwide form becomes viable). If not → discard, revert to the static
clone plan + Africa split. **Nothing else in the plan depends on this
succeeding.**

### Phase 3 — Two generated Google Forms (1–2 days)
- `FormsSetup.gs` one-time generator + bound handlers:
  - **Form 1 "New Club Enrollment"**: partner dropdown (from Partners tab),
    club name, roster paragraph, mentor/language fields. Handler normalizes →
    Roster, mints IDs.
  - **Form 2 "Roster Modification"**: **partner-branched** — page 1 is a
    47-item partner dropdown with `setGoToPage` branching to that partner's
    own section, which lists only their 5–30 clubs. All 47 sections and the
    branching are generated and kept current by the script (`setChoiceValues`
    + `setGoToPage` on each sync), so no mentor ever scrolls 330 options.
    Adds → new Roster rows (after reactivation check against inactive rows).
    Removes → matched case-insensitively against the active roster; matches
    become status=inactive + removed_date (**nothing is ever deleted**;
    Jotform option disappears next sync; historical Jotform submissions and
    Salesforce records untouched); non-matches → ReviewQueue.
- New club → Salesforce Account: **"SF Pending" tab + weekly email digest** to
  the admin who runs Data Import Wizard. No Connected App/REST integration now
  — over-engineering at this volume (backlogged).
- Close the old enrollment form with a redirect message to the new ones.

Verify end-to-end: Form 1 club reaches the working copy within the hour;
Form 2 removal drops the option while history stays.

### Phase 4 — Regional forms via CLONE-and-replace (2–3 days, one region at a time)
Per Ryan: don't operate on the drifted live regionals — clone the upgraded
working copy and relabel. This is safer AND fixes Africa's duplicate-club and
churn mess for free. **Clone from whichever form the Phase 2.5 gate blesses**
(widget-based if the pilot succeeded — in which case the region filter and the
Africa split below are likely moot, since a light form can carry every club —
otherwise the static one).
- Extend sync with a target list `{formId, qidMap, regionFilter}` and a
  `--prune` mode that DELETEs club questions outside the region filter —
  **safe only on fresh clones with zero submissions** (the sync must refuse to
  prune a form that has any submissions).
- Per region: `POST /form/262352490535154/clone` (may gateway-504 but still
  clone — check /user/forms; delete accidental extras) → retitle ("Africa
  Attendance Form") → region-filtered sync with prune (clone starts with all
  329 clubs; Africa keeps ~200, U.S. ~10, etc.) → structural qids are
  inherited from the working copy so the SF integration mapping carries over —
  **verify with one real test submission reaching `Attendance_Batch__c`**
  before go-live.
- Swap-over: disable each old regional with a "this form has moved" thank-you
  message; distribute new links (mentor links change — coordinate with
  partners; prefilled links can carry clubName + mentorEmail).
  Old regionals keep their submission history as archives.
- **Master**: retire (disable/redirect), keep archived. **Working copy**
  becomes the template/staging form: every future sync-logic change lands
  there first, and future regional rebuilds re-clone from it.
- **Africa split (fallback only)**: if the widget pilot failed, Africa becomes
  TWO static clones (split by partner/country in the Partners tab, ~100 clubs
  each) to halve DOM weight. Both carry the same SF mapping, so reporting is
  unaffected. If the widget succeeded, skip this entirely.

Verify per region: form club list == Roster filtered by region; cascade
intact; test submission → correct `Attendance_Batch__c`. Rollback: trivial —
old form still exists untouched; just don't swap links (or re-enable it).

### Phase 5 — Salesforce IDs (2–4 working days, longer elapsed; strictly gated)
- **5a Identify the matcher** (gates the rest): Setup → Object Manager →
  `Attendance_Batch__c` → Triggers; Flows filtered by object; Apex search
  "Attendance"/"fuzzy"; if opaque, debug log on the integration user + test
  submission. Deliverable: short doc of how `Contact_IDs__c` names become
  Contacts.
- **5b `Girl_ID__c`** external ID (unique) on Contact; backfill via export +
  exact-normalized-name-within-Account matching script → Data Loader upsert;
  residue → ReviewQueue. Partial coverage is acceptable — don't block on 100%.
- **5c Update the matcher**: exact `Girl_ID__c` lookup branch BEFORE the
  existing fuzzy fallback (sandbox first if available). Fallback stays, so
  unmatched legacy girls keep working.
- **5d Flip calcValues**: sync writes checkbox `calcValues` = girl IDs.
  Checkboxes should align calcValues 1:1 with options (dropdowns have a
  leading placeholder slot; **verify the checkbox convention empirically on
  the working copy before regionals** — encode the distinction in one shared
  helper). Canary on working copy → verify a test batch resolves IDs → then
  regionals one at a time. Until 5d, names keep flowing unchanged.

### Phase 6 — Backlog (explicitly not now)
SF REST auto-Account creation; monthly three-way reconciliation report;
regional consolidation; Spanish-language mentor confirmation email.

## Sharpest risks

1. **Unknown SF matcher** — `Attendance_Batch__c` is insert-only with no
   error surfaced to mentors; flipping calcValues early would break attendance
   **silently**. Mitigated by the hard 5a→5d gate, external-ID interim, canary
   form, retained fuzzy fallback.
2. **Widget fill-time dependency** (new with Phase 2.5) — a static form always
   renders; a widget-based form needs the Apps Script endpoint to respond
   while the mentor is filling it, in low-bandwidth regions. Mitigated by
   caching, an explicit error state with manual-entry fallback, a side-by-side
   pilot including a low-bandwidth partner, and a discard gate that costs
   nothing else in the plan.
3. **6,210-girl Contact backfill residue** — legacy Contacts were created by
   fuzzy matching, so exact-name backfill will leave a real remainder; it's
   deliberately decoupled (every phase ships without it) and fuzzy fallback
   covers the gap.
4. **Wholesale conditions PUT / clone swap-over** — a bad payload nukes a
   form's logic, and swapping regionals changes mentors' links mid-season.
   Mitigated by pre-write snapshots, the *rehearsed* restore, cloning instead
   of editing live forms (old form survives untouched as instant rollback),
   one region at a time, and the parity harness before each apply.

## Reuse & references

- Porting source: [sync_attendance_form.py](/Users/ryaneskuri/jotform-glow-sync/sync_attendance_form.py)
  (`parse_roster`, `read_sheet`, reconcile, `build_conditions`, `Jotform`
  API-call shapes) and [README.md](/Users/ryaneskuri/jotform-glow-sync/README.md).
- Verified API semantics: memory note `jotform-api-quirks.md`.
- Current-state templates: scratchpad `questions_final.json` /
  `properties_final.json` (copy to repo in Phase 0); original pre-upgrade
  state: `properties.json` / `questions.json` / `emails_verbatim.json`.
- Backfill input: scratchpad `enrollment_full.csv` (original in
  `~/Downloads/Global G.L.O.W. - Girl Enrollment Submission (Responses) - Form Responses 1.csv`).

## Sizing

~13–18 consultant days over 8–12 weeks elapsed (the widget pilot adds 2–4 days
plus 1–2 weeks of side-by-side observation; Salesforce coordination dominates
the tail). **Phases 0–2 alone (~4–6 days) eliminate the manual CSV workflow** —
everything after that is optional improvement, and each phase is independently
shippable.
