# Decisions

One section per decision that shaped the system, in date order; the reasoning lives in the
linked plan or intent. Add one when a choice is made that a future reader would otherwise
re-litigate: at the end of the file, headed `### YYYY-MM-DD — <the decision in a few words>`,
the decision in one to three bullets, then **Why**, **Rejected** (the options not taken, or a
link to the plan that lists them) and **Consequences**. A decision that amends or reverses
an earlier one says so, and the earlier one gets a dated bullet pointing at it. (Until
2026-10-09 this was one table, a row per decision.)

### 2026-08-24 — Jotform's native Salesforce integration, no custom client

- Keep Jotform's native Salesforce V2 integration; no custom SF client
- **Why:** mapping is 8 rows keyed to question ids and identical on every form; the matcher lives in Salesforce
- **Consequences:** question ids 5/17/18/19/98/100/102/105/109 are frozen; changing them breaks the integration

### 2026-08-24 — Immutable girl IDs, numbers never reused

- Girl IDs `CLUBCODE-LASTCODE-NNN`, immutable, numbers never reused
- **Why:** historical Salesforce records must never point at the wrong person
- **Consequences:** reactivation reuses the same id; a renamed club keeps its code via the ClubRegistry

### 2026-08-24 — The sheet's Roster tab is the source of truth

- The sheet's Roster tab (one row per girl) is the source of truth; forms follow
- **Why:** the raw form responses are append-only and inconsistent
- **Consequences:** every tool reads the Roster export; nobody edits the forms by hand

### 2026-08-25 — Deactivate, never delete

- Deactivate, never delete (girls, clubs, questions)
- **Why:** history and Salesforce counts stay intact
- **Consequences:** `--prune` exists only for fresh clones and refuses on forms with submissions

### 2026-08-26 — Partner regions derived from the old forms

- Partner → region derived from which regional form each partner's clubs were on, Partners tab overrides
- **Why:** nobody had typed regions; the old forms encoded them
- **Consequences:** `Regions.gs` is generated and frozen at that derivation; the Partners tab is authoritative
- 2026-10-09: the deriving script is retired and `Regions.gs` is hand-kept data (2026-10-09 — Finished one-offs are deleted, not archived)

### 2026-08-26 — Git history rewritten once for privacy

- Git history rewritten once to remove a real girl's id used as an example
- **Why:** privacy
- **Consequences:** examples are `DEMOCLUB-SAMPLE-001` and fictional surnames only

### 2026-08-27 — Four regional forms cloned from the template

- Four regional forms cloned from the upgraded template and relabelled, old forms kept as "(defunct)"
- **Why:** clone keeps the Salesforce mapping byte-identical; Africa stays one form
- **Consequences:** languages must be restored after a clone (`restore_translations.py`)

### 2026-08-27 — One Club Roster Form with a page-1 choice

- One Google "Club Roster Form" with a page-1 choice instead of two forms
- **Why:** partners kept picking the wrong form
- **Consequences:** handlers route by the linked form url, never by tab name

### 2026-08-27 — Apps Script deployed with clasp 2.4.2 on Node 18

- Deploy Apps Script with clasp 2.4.2 on Node 18
- **Why:** one command instead of pasting nine files; clasp 3 needs Node 20
- **Consequences:** `.nvmrc`, `engines`, `.claspignore`

### 2026-09-01 — The AI-native SDLC playbook adopted

- Adopt the AI-native SDLC playbook: intent → spec → plan under `docs/`, CLAUDE.md, REVIEW.md, skills, hooks, `make check`
- **Why:** see `docs/plans/2026-09-01-ai-native-sdlc-adoption.md`
- **Consequences:** plan mode for non-trivial changes; committed plans are the audit trail
- 2026-10-09: the spec stage is retired and an intent is optional (the 2026-10-09 decision on plans and intents).

### 2026-09-01 — `make` and `scripts/` as the check interface

- `Makefile` + `scripts/*.py` as the check interface (not npm scripts, not a lone shell script)
- **Why:** named sub-targets, no dependencies, portable regex (BSD grep has no `\b`), make 3.81 on macOS
- **Consequences:** `make check` is the definition of done

### 2026-09-01 — A synthetic fixture, generated in Python

- Synthetic fixture generated in Python with a fixed seed; `expected.json` written by the Python parser
- **Why:** the real export is PII and never leaves `data/`; Python is the parity oracle
- **Consequences:** `make fixtures-check` catches parser drift; tests are green on a fresh clone and in CI

### 2026-09-01 — The live gate: a hook keyed on a variable set outside the agent

- Live-system gate is a PreToolUse hook keyed on an environment variable set outside the agent
- **Why:** the playbook's "deterministic control layer"; a command cannot approve itself
- **Consequences:** `GLOW_LIVE_OK=1` exported before launching Claude Code, or Ryan runs the command
- 2026-10-14: the variable opens nothing any more; the hook asks Ryan in the session instead (2026-10-14 — The live gate asks Ryan in the session; GLOW_LIVE_OK no longer opens it)

### 2026-09-01 — The leaked Jotform key rotated; settings.local holds no rules

- The Jotform key found in `.claude/settings.local.json` is rotated; settings.local is gitignored by the repo and holds no rules
- **Why:** the file was protected only by a machine-local global ignore
- **Consequences:** keys live in `.env`; never on a command line in a Claude session

### 2026-09-01 — The automatic sync is event-driven

- Automatic sync is event-driven: `Dispatch.gs` → GitHub Actions → the existing Python sync, with a daily backstop
- **Why:** runs when the Mac is off; reuses the proven tools; a native Apps Script port (old Phase 2) would duplicate `sync_attendance_form.py`
- **Consequences:** credentials as GitHub secrets in a private repo; `AUTO_SYNC_APPLY` variable as the kill switch; dry runs first

### 2026-09-01 — Safety bands for the unattended sync

- Safety bands: ≤5 creates, ≤20 updates, no deletes, no "shares no names" replacements, no truncated exports
- **Why:** an unattended writer must have a blast radius a human can review
- **Consequences:** bigger changes are applied by hand after reading `ATTENTION.md`

### 2026-09-01 — A SyncLog tab records every run

- `SyncLog` tab in the sheet records every run; the Audit tab records every request
- **Why:** Ryan asked for a timestamped record in the sheet; the Roster's date columns cannot show reactivations
- **Consequences:** `SYNC_LOG_COLS` duplicated in `Roster.gs` and `auto_sync.py`, parity-tested

### 2026-09-01 — The original plan archived, not rewritten

- `docs/PLAN.md` archived, not rewritten
- **Why:** it is the best record of *why*; current state lives in LAUNCH/BACKLOG/ARCHITECTURE
- **Consequences:** `docs/archive/2026-08-24-original-plan.md`
- 2026-10-09: the launch notes followed (`docs/archive/2026-09-01-launch.md`); their links are in the RUNBOOK, "The forms".

### 2026-09-01 — The rollback pair stays at the repo root

- `backup_forms.py` and `restore_conditions.py` stay at the repo root for now
- **Why:** the launch-day rollback pair; muscle memory and every doc reference
- **Consequences:** moving them into `tools/` is a backlog item
- 2026-10-09: and stays there: BACKLOG 29 is dropped (`docs/plans/2026-10-09-repo-cleanup.md` keeps the rollback pair at the root and `tools/` flat).

### 2026-09-01 — Plan mode not the default in launch week

- Plan mode is not made the default (`defaultMode`) during launch week
- **Why:** quick fixes may be needed on launch day
- **Consequences:** revisit after the first week

### 2026-09-01 — The Club picker: Jotform's searchable dropdown

- Club picker = a native Jotform dropdown in its searchable mode (`multipleSelections=Yes`), maintained by the sync, not the Autocomplete widget
- **Why:** the plain single-select is a browser `<select>` (first-letter jump only); the searchable component filters as you type, cannot take free text, its conditions compare exactly, it translates and needs no iframe; the widget allows any text and its conditions are `contains`-based
- **Consequences:** question 5 stays the Salesforce field, hidden and filled by a calculation; single-pick enforcement to confirm before the mass update; template only until then (Ryan)

### 2026-09-02 — Review-driven hardening of the runner and the guardrails

- Review-driven hardening: an unattended write whose verification cannot run raises ATTENTION (exit 2); the workflow artifact carries conditions-only rollback files, never full properties snapshots; runner output is redacted before it reaches the Actions job log; the secrets scanner's allowlists apply to the matched text only; the live gate also matches raw API shapes (`api.jotform.com`, dispatches, `apply_changes=True`, Sheets writes) and the guardrail files protect themselves from edits; SyncLog writes are opt-in (`--synclog`, the workflow passes it)
- **Why:** a five-pass adversarial review (REVIEW.md) confirmed each gap; the Bash-side residual (a determined edit via shell) is accepted for a solo repo — the hooks are a control layer, not a security boundary
- **Consequences:** plan status log 2026-09-02

### 2026-09-02 — New partners choose their region on the Club Roster Form

- New partners choose their region on the Club Roster Form: a required picker with the canonical `REGIONS` list (Config.gs); precedence Partners tab > form answer > derived map; the choice is persisted to the Partners tab
- **Why:** 7 of 8 launch-week clubs arrived region-less and reached no attendance form until staff intervened; the frozen derived map cannot know a new partner
- **Consequences:** `Q.COUNTRY` stays as a legacy read; `REGIONS` spelling parity with `glow/forms.py` is test-pinned; a wrong pick is corrected on the tab + Refresh regions

### 2026-09-12 — The Club picker rolled out with the training guide's wording

- Club picker rolled out to all four regional forms with the training guide's wording ("Club Name" / "Select your Club Name to see your roster."); mentor email field renamed "Partner Coordinator Email"; Group Photo = one photo, faces visible, 10 MB, HEIC; club names stay English in every language while the surrounding text is translated (Odia included)
- **Why:** leadership approval 2026-09-12 after consistent partner feedback — typed club names kept rosters from populating, and phone photos exceeded the 3 MB cap
- **Consequences:** picker wording is generated (`PICKER_PROPS`) and the sync reverts hand edits; static-field wording goes through `tools/update_static_fields.py`; translations are applied only after a form has the picker; translations were written by us, native review pending
- **2026-10-12:** the Group Photo sublabel no longer says "All girl faces should be visible." (2026-10-12 below); one photo stays.

### 2026-09-14 — A club is renamed in place

- A club is renamed in place (`tools/rename_club.py`: sheet cells + the roster question's label), never by deleting and re-creating
- **Why:** the sheet alone would make the sync create a duplicate question and orphan the old one in the picker; the club code, the girls' ids and any submitted attendance stay attached to the same club
- **Consequences:** the question's `name` slug keeps the old spelling (harmless, nothing keys on it); the Google Form dropdown follows at the next `syncFormChoices`

### 2026-09-20 — Hindi and Persian on the Asia form; a flag for Odia

- Hindi and Persian offered on the Asia form only (Urdu and Arabic were already there); the switcher flag for Odia is Jotform's own India SVG painted through `injectCSS` (`tools/switcher_flags.py`), the same nation Jotform gives Telugu
- **Why:** Jotform's flag table has no entry for Oriya and no per-language flag setting; Odia has no flag of its own; the public page applies `injectCSS` and the runtime stamps `html[lang]` on every switch
- **Consequences:** the SVG travels as a base64 data URI because the served page rewrites `http:` inside injected CSS (a percent-encoded SVG lost its xmlns and never painted); translations written by Claude with a three-lens review, native review pending (backlog 6a); the block is marked and idempotent, rollback = properties snapshot; other forms get the languages with the same commands minus `--form`

### 2026-09-24 — The Global Catalyst logo replaces the header banner

- The Global Girls GLOW header banner is replaced by the Global Catalyst logo on the template and the four regionals, displayed 205x103
- **Why:** rebrand; 103 is the height of the banner it replaces, so the header band does not move, and the width follows the new logo's own 1.99:1 proportions instead of the banner's 3.94:1, which would have squashed it
- **Consequences:** the logo's own mark is bigger than the old one's (the old 406x103 file was 65% whitespace around a 142x52 mark); the asset is hosted by Jotform because the API cannot upload one, so a rebrand means one builder upload plus `update_static_fields.py --image-src`; `assets/` keeps the supplied original and the 2x header derived from it

### 2026-09-24 — A club under a mistyped partner is moved in place

- A club filed under a mistyped partner is moved in place (`tools/rename_club.py --new-partner`: the partner cells of Roster, ClubRegistry and SF Pending in one batch, written as the Partners tab spells the target); the typo's Partners row is blanked with a note, never deleted; the raw Enrollment Responses stay append-only
- **Why:** Fundación Kaleidos could not find Club Glow Traslasierra on the Club Roster Form because the 2026-03 enrollment typed its partner as `ion bu`; `Ids.gs` keys codes by partner + club and the sync splits a part-moved club, so the cells must move together; `key_` folds no accents, so the spelling is copied, never typed; Ryan chose to keep the raw tab untouched
- **Consequences:** no Jotform write (forms key clubs by label); the typo's section stays on the Google Form, unreachable; a rebuild from the raw responses (in-sheet or offline) would bring the typo back, and already reactivates girls removed since 2026-09-01, so it is not run after launch ([plan](plans/2026-09-24-move-club-partner.md))

### 2026-09-27 — FormLog knows a response by its Timestamp text

- FormLog knows a form response by the text of its Timestamp cell in the spreadsheet's zone, to the millisecond (`which|w:<wall>|partner|club`), not by `getTime()`; keys from before still count when their milliseconds differ by whole quarter-hours, at most 26 h.
- "Process any missed form responses" previews and asks per group, never runs a row FormLog has as processed under another key, asks separately before running Club Roster Form responses more than 7 days old, locks per row, and starts no row after 4 minutes
- **Why:** `getTime()` moved 4 h when the sheet's zone changed on 2026-09-02, and the 2026-09-13 menu run replayed 11 old responses (the 20 Radiant Girls reactivated) and hit the 6-minute limit
- **Consequences:** no FormLog migration; roll `appsscript/` back no further than `7a175c4`; [plan](plans/2026-09-27-formlog-key.md)

### 2026-09-28 — Ryan owns the ReviewQueue, worked from the Monday e-mail

- Ryan owns the ReviewQueue and works it from the Monday e-mail (`sendSfPendingDigest`, name kept for the installed trigger), which now lists the open items by issue with their ReviewQueue row — never the detail column, never a dedupe tag other than a response row, and a partner or club only when it is on file in ClubRegistry.
- A problem report that looks like a roster change (the Club Roster Form chosen, or roster words with change words) also becomes a ReviewQueue item, "Roster change sent as a problem report" tagged `[#Feedback!N]`, written before the staff e-mail; other reports stay e-mail only.
- The reports e-mailed before (Feedback rows 4-12) went through the same code once (`tools/backfill_feedback_review.py`)
- **Why:** 7 of 11 problem reports were roster requests and none was applied; the queue grew from 22 to 30 open with nothing resolved 09-12 → 09-28, because nobody owned it and nothing announced it
- **Consequences:** any text in `resolved` closes an item, rows are never deleted; the classifier is a keyword heuristic — a missed report still reaches staff by e-mail (add it by hand), a false alarm is resolved "not a roster change"; [plan](plans/2026-09-28-problem-report-followup.md)

### 2026-09-28 — A partner list for shared club names (superseded)

- **Superseded 2026-09-30, never deployed** (the 2026-09-30 row on same-name clubs; `--partner-picker` is refused).
- It was: a club name that two partners share is told apart by a sync-generated **Partner** dropdown (`--partner-picker`, field `partnerPicker`: the partners concerned on that form, hidden until such a name is picked, required when shown), not by the typed Partner box (q331), which is hidden.
- **Why:** the typed box had to equal the partner's full Roster spelling, so a mentor who typed "HAFAI" saw no roster (Feedback 9); a list removes the typing and adds one rule per form (Africa 255, template 377: the chosen partner copied into the hidden q331, which the staff notification e-mail's Partner row reads)
- **Rejected:** the options in the [plan](plans/2026-09-28-partner-box.md#options)
- **Consequences:** created once per form by the flag, then maintained on every run and audited by `form_status`; the runner never creates it; `main` must carry the code before any apply, or the next unattended run points the rules back at the hidden box; question 5 and the Salesforce mapping are untouched ([plan](plans/2026-09-28-partner-box.md))

### 2026-09-28 — The replay guard

- A Club Roster Form response never puts back a girl removed after the day it was sent (the replay guard): the handlers pass the response's sent day (its Timestamp's wall-clock day, from the FormLog key) and `planClub_` / `planModification_` keep her removed when her `removed_date` is a later day, or unreadable (or after today) on a response sent before today; one ReviewQueue item per response ("Removed girls not put back by an older response": Roster row numbers, tagged with the response row) and, for a roster change, the mentor e-mail lists the names as typed under "Not added back".
- The same day still reactivates; no sent day (the rebuild, the offline builder) keeps today's behaviour, and a Club Roster Form response without one (a Timestamp that is not a date) is refused as `ERROR:`, never run unguarded (review finding: the menu's warning for old rows, where such a row lands, promises girls removed since stay removed); `loadRoster_` reads Date cells in the spreadsheet's zone; a Club Roster Form removal is dated the day it was sent (never after today), so both sides of the comparison are sent days (review finding: dated the day it ran, a REMOVE and a later-sent ADD both run late kept the girl removed)
- **Why:** the 2026-09-13 replay put back 20 girls removed the day before; the FormLog-key fix stops the menu re-selecting processed rows, but a retried or late-confirmed response still applied itself to today's roster
- **Consequences:** a girl who really rejoined needs a fresh ADD (the queue item and the e-mail say so); an old REMOVE still takes off a girl re-added since (a reactivation records no date, BACKLOG 34); the rebuild stays unguarded (BACKLOG 39); [plan](plans/2026-09-28-replay-guard.md)

### 2026-09-28 — A possible duplicate new club is held

- A new-club response that may duplicate a club on file is **held**, not imported (proposed; Ryan approves before merge): ≥ half (and ≥ 2) of its names active in one club of any partner; a club name close to one of the same partner (equal words, containment, or Python-difflib similarity ≥ 0.8 of the distinctive words, also without parentheses; different numbers, section letters or school levels never close); a typed organization close to a partner on file (accents, acronym, containment, similarity); or an exact re-enrollment where under half of the names are on file AND under half of its girls are in the list.
- Held = one ReviewQueue item tagged with the response row and its sent time, FormLog `HELD: …`, a neutral e-mail to the mentor, nothing else. `HELD:` is a second "not done" result beside `ERROR:`: never offered by "Process any missed form responses" until the item's `resolved` starts with the word `release`, then asked on its own and run as sent with the check skipped — except an organization typed close to a partner on file, refused until the response's `Partner organization` cell names that partner or the Partners tab has the new organization (a release as typed would re-create the `ion bu` duplicate partner); any other resolution closes it (never run; the menu preview still names its row, so a release typed another way shows).
- Club Roster Form free text passes `sheetText_` (no leading `= + - @`), a girl's name only at its start, so it still matches her Roster spelling (her last word, filed on its own as `last_name`, is stripped where the row is built)
- **Why:** 7 of 39 new-club responses so far would have been held — exactly the 08-31 exact re-enrollment with another club's list and the six 09-22 re-enrollments with a school added — and no other; importing them created second ids for the same girls. A leading `=` from a public form became a formula in the sheet
- **Consequences:** a false hold waits up to a week for the Monday e-mail; thresholds are one constant (`DUP_GUARD`); "same club" is never automated (staff enter the new girls on the club on file); the form-side "Is your club one of these?" question is not built; [plan](plans/2026-09-28-duplicate-club-guard.md)
- 2026-10-09: merged 2026-09-29 and deployed 2026-09-30 with the same-name push (BACKLOG 11b).

### 2026-09-28 — The Google Forms' wording comes from `Forms.gs`

- The Google Forms' descriptions and help texts live in `Forms.gs` `WORDING` and reach the live forms through a one-time, previewing GLOW menu migration (`migrateFormWording`), not hand edits mirrored in code.
- It replaces only a text the generator wrote (the 2026-08 wording, an empty text, or the wanted text with another form link) and lists anything edited by hand with the suggested text; it re-adds the problem form's reply-email question under exactly `Q.FB_EMAIL` and never adds a second e-mail question.
- A handler reading a response now takes the filled-in cell when two columns share a title
- **Why:** 7 of 11 problem reports were roster changes, and none could be answered: the reply question had been removed by hand; `createGlowForms` reuses existing forms, so editing `Forms.gs` alone changed nothing live, and wording kept by hand in two places drifts
- **Consequences:** a fresh build and a migrated form say the same thing (tested); the Feedback tab keeps two reply columns with one title: leave both; the live problem form's other hand edits (its visible title, a required "What were you trying to do?", its help text, its form list) and the live Region help text are not mirrored in the generator; [plan](plans/2026-09-28-forms-wording.md)

### 2026-09-28 — A Club Roster Form link on every attendance form

- *(proposed, pending Ryan's go)* Every attendance form carries a Club Roster Form link directly above the problem-report link — "A girl missing, or no longer in your club? Tell us on the Club Roster Form.", one text element placed by `tools/add_feedback_link.py --link roster`, translated for every offered language with "Club Roster Form" kept in English; the links above Submit live in one table (`glow/links.py`) read by the placing tool and both translation tools
- **Why:** 7 of 11 problem reports were roster changes and 38 of 50 partners never used the Club Roster Form; the attendance form is the page mentors open every week
- **Consequences:** q443 and Submit each move down one order; the sync never writes or gates the element (not a roster, no generated rule mentions it — test-pinned); its translations are a second step keyed by its qid; the plain `viewform` URL, no page-1 prefill; [plan](plans/2026-09-28-roster-form-link.md)
- 2026-10-09: merged 2026-09-29; placing it on the forms still waits for Ryan's go (BACKLOG 46).

### 2026-09-29 — Every roster renders above the links and Submit

- *(accepted by Ryan 2026-09-30; live on all five forms the same day)* Every roster renders above the links and the Submit button: the sync creates a new roster at the order of the last roster rendering above the first link (or Submit), and a one-time tool (`tools/fix_roster_order.py`) moves the links, Submit and the hidden bridge fields to empty orders after the last one; `form_status` makes a roster below them NOT CLEAN.
- **Why:** 98 of Africa's 221 rosters (every one created since the 2026-08-24 overhaul) rendered under Submit; a submission with no girl ticked came 20% of the time from a club below Submit against 5% above
- **Rejected:** moving the tail down on every create (`plan_insert`-style, about 10 extra writes per new club, every unattended run) and moving the rosters instead of the tail (98 writes on Africa alone)
- **Consequences:** the create order is right whether Jotform inserts at a taken order (seen 2026-09) or keeps both; the repair writes only `order`, to empty slots, never a roster, Submit first and the first link last, probed after its first write and verified after its last, rollback `--undo <stamp>`; the hidden fields move to the end of the builder and submissions table; `AUTO_SYNC_APPLY=0` from the merge to the last repaired form; [plan](plans/2026-09-29-rosters-above-submit.md)

### 2026-09-29 — One club per attendance submission

- *(accepted by Ryan 2026-09-30; live on all five forms the same day)* One club per attendance submission is enforced on the form by two sync-generated rules, added per form with `--club-guard`.
- Whenever question 5 (the picker's copy) is not exactly one of the picker's options, a hidden warning below the picker shows and Submit is hidden (a field rule) and disabled (a require rule, which closes desktop Enter).
- The picker's `calcValues` = its own options, so the copy survives the browser's page translation. The q18 (Contact_IDs) calculation is unchanged. Ungated: every picker term uses the picker's own spelling.
- **Why:** 20 multi-club submissions since 09-01 sent question 5 the names run together, which Salesforce's processor would turn into a junk Club Account; a multi-select's rules have no count operator, only exact, case-sensitive `equals` / `notEquals` / `isEmpty` / `isFilled` (`plans/2026-09-29-club-guard.md`)
- **Rejected:** a single-select picker (Jotform's classic layout offers no searchable single-select), a widget (iframe, weak connections, free text), a server-side clean-up only (the fused name would still reach Salesforce), a ", " between the rosters in q18 (with Submit shown only one roster is visible, and the literal would be written on every submission: Africa about 440 characters of commas in `Contact_IDs__c` and in both e-mails, and q18 never empty)
- **Consequences:** two new rules per guarded form of (clubs + 1) terms each (Africa 217); a new club reaches the guard in the same run as the picker; the `calcValues` layout on a multi-select is verified on the template's rendered page before any regional form; the warning is English until `add_translations.py --apply`; `main` must carry the code before any `--club-guard --apply`, and the merge is not reverted while a picker carries `calcValues` (older code leaves them stale, and a new club then shifts question 5 by one with no warning)

### 2026-09-30 — Work-log days on the clock the Mac showed

- The work log counts each block of work on the day it **started**, on the clock the Mac showed then; that clock is a committed timeline (`worklog/timezones.csv`, seeded from git commit offsets), not the Mac's zone at run time
- **Why:** a zone change rewrote billed history, and the September back-fill had counted Sep 1-14 at +08:00 although the Mac was on +02:00/+03:00 (20.25 h → 20.50 h, six days re-cut); Ryan chose start-day over splitting at midnight
- **Consequences:** `update` refuses after travel until `zone` records the switch, and when a commit's offset disagrees; rows are dropped only with `--drop-stale` and only for the last 29 days

### 2026-09-30 — Sheet timestamps in the sheet's own zone

- Timestamps our tools write into the sheet use the sheet's own zone (SyncLog `when`, `rename_club.py`'s Audit row and Partners note, `build_roster_offline.js --tz`)
- **Why:** the runner's and the Mac's clocks differed from the sheet's (America/Chicago on GitHub, JST on the Mac, against the sheet's America/New_York), so SyncLog and Audit rows next to the Apps Script's disagreed by hours
- **Consequences:** the SyncLog history has a one-hour jump at the cut-over (docs/RUNBOOK.md, SyncLog columns); the Python tools read the zone from the sheet (`sheets_client.time_zone`) and refuse when it is not a named IANA zone, the offline builder refuses without `--tz`

### 2026-09-30 — Nine roster questions deleted, once

- A one-time exception to "our tools never delete questions": nine roster questions were deleted through the API on Ryan's decision — q422 'Shinning Stars' (YWOU) and q429 'SUPER GIRLS' (Reach All), the two duplicate clubs retired that day (Africa and the template), and q158, the stale 'Setidevi G.L.O.W club, Sokhel' spelling (all five forms)
- **Why:** each held 0 answers in every submission; left in place they kept a dead picker entry (q158 on every form, a Nepal club on the Africa list) and kept two names shared that are one club each — which decides what Salesforce is sent ([plan](plans/2026-09-30-same-name-clubs.md), Step 0)
- **Consequences:** the rule stands for everything else: tools never delete a question, `--prune` stays for fresh clones; backups `questions-2026-09-30T1550.json` / `properties-2026-09-30T1550.json` per form; the 35 Roster rows are inactive, not deleted (Audit `deactivateRows`)

### 2026-09-30 — Every active club is a Club account in Salesforce

- Every active club is a Club account in Salesforce, created **before** its attendance arrives, named exactly as its form sends it (the Club picker's option, spelling and capitals kept) and linked to its partner account as parent; a club's name is never edited in Salesforce
- **Why:** the attendance processor matches the submitted name against every account name (capitals ignored, nothing else) and otherwise creates a partner-less account, so a tidied or missing name splits a club's attendance
- **Consequences:** 345 created and 8 pilot accounts linked on 2026-09-30, then the two clubs released by the same-name scheme ([plan](plans/2026-09-30-salesforce-clubs.md)); the seven "<club> - <partner>" accounts follow the forms; written one record per call with a read before and after, the rollback files kept under `data/`; the public partner sign-up page returns every account name, the clubs now included - Ryan gave the go with that on the table, and leaving Club accounts out of that list is an Apex change for whoever maintains the portal

### 2026-09-30 — A shared club name sends `<club> - <partner>`

- A club whose name another partner's club also has sends `<club> - <partner>` to question 5, and its Salesforce Account carries that name.
- The one string is its Club-picker entry, `calcValue`, roster-rule and club-guard term; the roster question's text stays the plain club name. Seven clubs, after two duplicates were retired the same day. Each roster keeps the form it has (read back from its rule, never flipped by the sync); `--same-name-switch`, by hand and once per form, makes long the rosters whose name two or more partners' **active** clubs share, in any region; a **new** club whose name another partner's club has (any status, any region) is not created and raises ATTENTION; any other change of what an existing club sends (a rename, a respelled partner) is listed and needs `--q5-change-ok` by hand, never the runner.
- The typed Partner box (q331) is hidden on every form with the picker once no rule shows it, and the partner list (2026-09-28) is retired.
- **Why:** Salesforce matches an attendance submission to a club by question 5 alone, exactly apart from case, in one org for all regions, and creates an Account when nothing matches; with the typed Partner box 8 of the 10 same-name submissions since 09-01 reached no roster. Ryan's decisions of 2026-09-30: one list, an existing club's name never changes, a new club may not take a name in use, spelling follows the sheet
- **Rejected:** one "Ruby" entry with question 5 computed from a partner answer (a multi-select's `equals` is true while other clubs are picked too, so it would defeat the club guard, and 8 of 10 such submissions had no usable partner); relabelling the roster questions (breaks the match by text, `rename_club.py`, the region check); the long name for every club (about 360 long entries on phones); recomputing the set from the Roster on every run (a retired or new namesake would rename an existing club's Salesforce Account unattended)
- **Consequences:** the staff notification e-mail's Partner row is empty; the switch is applied by hand, template first, before the Salesforce reconnect, and `main` must carry this code before any form is switched: older code puts a switched form back on the plain names unattended; `restore_conditions.py` refuses a snapshot from before a form's switch; a rollback is all forms together and only before the reconnect; `rename_club.py` cannot rename the seven; a new same-name club stays off its form until it is renamed (`rename_club.py --sheet-only`: it has no question, and the one of that name is the other partner's); a plain roster's owner is read from the Roster's rows of any status, so a retired club's question (and Account) is never taken over by another partner's new club of that name and an existing club is never the one refused; rules older than the picker are ATTENTION for the runner, never `in-sync`; the Club Roster Form handler is to hold such a club at intake (Part 2) ([plan](plans/2026-09-30-same-name-clubs.md), RUNBOOK "Club names two partners share")

### 2026-09-30 — Missed attendance is back-filled by a local tool

- Attendance that missed Salesforce is back-filled by a local tool (`tools/sf_backfill.py`), not by replaying submissions and not through the conversation's connector: the club comes from the roster that holds the ticks, the names from the ticks, one batch per club and day, one request per batch, each proven before and read back after; doubtful sessions are held for Ryan's line in `decisions.csv`
- **Why:** question 5 and the stored name list are wrong on part of September (names run together, empty lists, another club's girls), and Salesforce's processor creates stray accounts, blocks a day after an empty batch, keeps only the first batch per club and day and is not bulk-safe; the batches carry girls' names, which never pass through a conversation
- **Consequences:** a second way to write to Salesforce, caught by the live gate (`--apply`); it needs the Salesforce CLI login on the Mac, which must never run over a VPN - that froze Ryan's user on 2026-09-30 ([plan](plans/2026-09-30-september-backfill.md))

### 2026-09-30 — Question 18 recalculated; at least one girl ticked

- *(accepted by Ryan 2026-09-30, "Guard first, then back-fill"; built 2026-10-01 on `wf8/contact-ids`, not live)* Question 18 (Contact_IDs, the names Salesforce stores) is recalculated after the rosters show or hide, and a submission needs at least one girl ticked.
- Both are generated by the sync, behind `glow/sync.py` constants read at run time. **Order**: on a form with the Club picker the Contact_IDs sum is rule 0, its ids minted first (Jotform walks a field's rules last to first; showing or hiding a roster never re-runs a calculation). **Operand**: the picker is one of its operands, never in its equation. Order is the fix, the operand a supplement.
- **Required rosters**: every roster carries Jotform's own `required` flag; Jotform validates only the shown roster and one tick satisfies it. The runner refuses a region whose rules are the old way, and the required flag on a roster with no other change. The rollout is by hand, per form; the rollback is generated (constants off, apply).
- **Why:** Of 484 September submissions: 64 with no girl ticked (each an empty Success batch in Salesforce that blocks the club's real batch for the day), 17 with ticks and an empty question 18 (207 names lost), 2 with another club's girls. The last two are reproduced in headless Chrome as the rule order; the club guard's own way out (remove the extra club) was one path
- **Rejected:** `clearFieldOnHide=enable` (the loop limit drops to 3: Submit stayed disabled with one valid club in a rapid sequence, and an accidental un-pick wipes ticks), a `", "` between the rosters (written between hidden ones too), one calculation per club (doubles the rules; kept as the fallback if Jotform does not keep the order), `calcValues` on every roster (the dictionary bypass, but a misaligned list sends the neighbouring girl's name, a valid one), a hide-Submit-while-q18-is-empty rule (the fallback; required rosters passed the browser proof and do not depend on question 18)
- **Consequences:** one conditions write per form and one question write per roster (Africa 220, the template 359 + its backlog); question 5, the picker, the guard and the integration untouched; `form_status` NOT CLEAN on the old shape and `--rendered` a hard stop on the template (a required checkbox's server markup was never seen); a Partner-gated roster rule (none live) is flagged, not generated; residual: the form's language switcher with two clubs picked (BACKLOG 56), restores in iOS Safari / Firefox untested, the rule walk is Jotform's internal behaviour ([plan](plans/2026-09-30-contact-ids.md))
- 2026-10-09: live on all five forms since 2026-10-02 (BACKLOG 35; the plan's Result).
- 2026-10-14: the runner no longer refuses either line: it applies the rewrite and the `REQUIRED roster` lines on its next run, like a roster change; the hand rollout per form is history ("2026-10-14 — Merged form changes roll out through the runner; review and tests are the gate", below).

### 2026-10-01 — No photo in Salesforce

- **No photo in Salesforce** (the CEO).
- The attendance photos were deleted from Salesforce that day and the upload row removed from the four regional forms' mapping; the template follows (RUNBOOK "Photos", step 1).
- `tools/integration_status.py` expects **no** upload field (`UPLOADS = []`) and flags a mapped one as NOT RIGHT
- **Why:** the photos show the girls' faces, and Salesforce is not where staff keep them; until the tool followed it reported the template `ok` and every regional form NOT RIGHT, so a real mapping fault on a regional form sat under the same red line
- **Consequences:** a photo is never re-mapped without the CEO's word (then `UPLOADS = ["19"]` goes back into the tool); `tools/backfill_resolve.py` still reads the photo URLs from Jotform, unaffected; the photo stays required on every form (2026-09-12 stands) ([plan](plans/2026-10-06-photos-to-drive.md))

### 2026-10-02 — The attendance processor creates new girls in one insert

- The attendance processor (Apex `AttendanceBatchProcessor`, the vendor's class) was changed in production: a submission's new girls are created with one insert, a name submitted twice counts once, a failure message is cut to the field's 255 characters
- **Why:** one insert per girl ran NPSP's Contact triggers per girl, and NPSP's own 100-query limit refused - and rolled back entirely - any submission with more than about 24 new girls, live or back-filled; a long failure message rolled a submission back instead of recording it
- **Consequences:** Ryan's go; validated in production with the tests, reviewed, deployed 03:25 UTC, proven with a rolled-back 47-girl run; rollback = redeploy `data/sf_processor_2026-10-02/before` ([plan](plans/2026-10-02-attendance-processor-one-insert.md))

### 2026-10-02 — Stale name translations removed; module values pinned

- *(accepted by Ryan 2026-09-30, "Go on all 4 fixes after we get the september data into salesforce"; built 2026-10-02 on `wf9/names-and-modules`, not live)* **Names**: the stale `base`/`en` entries of each form's translation store that alter a roster option are **removed** by a tool (`tools/fix_name_translations.py`), not corrected and not by the sync; what alters a name is decided by **emulating** Jotform's runtime (`glow/translation_lookup.py`: `setDictionary`, `trimMultiSpaces`, `sanitizeKeys`, `translate`'s fall-back, both runtime builds), never by matching "variant" text; the roster options of **all five forms** count.
- **Modules**: the sync gives each module dropdown (q14, q92, q93)
- `calcValues` equal to its own options after the single-select's empty slot (`glow/sync.py` `MODULE_CALC_VALUES`) and keeps them in step; the runner **never applies** a module line unattended (ATTENTION, like a `REQUIRED roster` line)
- **Why:** the calculation that fills question 18 passes each ticked name through the form's dictionary, whose key collapsing lands stale spellings (double space, tab, no-break space) on 55 exact names (Africa 49, Asia 5, Latin America 1): a second Contact per girl in Salesforce; question 98 copied the module's visible text, which "Translate page" rewrote in 30 of Latin America's 111 September submissions. Removal leaves the normal state (a name with no entry comes out exact) and keeps keys equal to their text; the sync does not own the store, so a tool's repair stays; emulation catches what a text match misses (an `en` spelling corrected in the builder) and leaves what alters nothing (55 keys removed of the 98 that look stale). Module lines unattended would roll the change out region by region with the first roster edit, past the template-first rollout
- **Consequences:** one translations POST (`base`+`en`, about 500 KB) per form, store saved first (mode 600), re-read, audited, the public page read and re-rendered once if it lags; three question writes per form; `form_status` NOT CLEAN on any altered option (every language the store holds) and on missing or misaligned module values, `--rendered` on the served page too; a stale entry made in the builder later is flagged, not prevented; until all five are rolled out the runner reads `attention` on every region; rollback: `--restore` (names), the constant off and a hand apply (modules) ([plan](plans/2026-10-02-names-and-modules.md))
- 2026-10-09: live on all five forms since 2026-10-06 (the plan's Result).
- 2026-10-14: the runner applies a module line on its next run, like a roster change; the template-first hand rollout was the first one only ("2026-10-14 — Merged form changes roll out through the runner; review and tests are the gate", below).

### 2026-10-06 — The module a submission sends stays as it is

- The module a submission sends stays as it is: one required single-select per year, hidden ones cleared at submit (form-level `clearFieldOnHide=disable`), the hidden q98 copied for Salesforce.
- No form change; no picklist or validation rule on `Module__c` in Salesforce.
- What is added: `form_status` pins the shape (NOT CLEAN on a multi-select, an optional dropdown or any `clearFieldOnHide` but `disable`), and the six batches that carry a Spanish module (and their 43 rows) are corrected once by `tools/fix_module_values.py` now that fix 4 of [names and modules](plans/2026-10-02-names-and-modules.md) is live (2026-10-06), with Ryan's go
- **Why:** 0 of 674 submissions since launch carry two modules or a blank one; the one defect (36 Latin America submissions with a page-translated q98) is fixed at its source by the module `calcValues`; a Salesforce rule would reject such a batch - the attendance then stays in Jotform and reaches Salesforce only by hand - instead of correcting it
- **Consequences:** the runtime's "cleared at submit" behaviour is Jotform's, audited not guaranteed; the correction is a Salesforce write through the CLI login (`--apply`, caught by the live gate; a new Salesforce writer in the live-systems skill) with a ledger for rollback ([plan](plans/2026-10-06-module-selection.md); applied 2026-10-07 (6 batches, 43 rows))

### 2026-10-06 — Photos go to Google Drive through Jotform's integration

- **The photos go to Google Drive through Jotform's own integration**, set in the builder per form, template first ($0: every Jotform plan includes every integration).
- Policy: the folders are owned by a **GLOW Workspace role account**, never a staff member's own (which one is open; the account that owns the enrollment sheet and the Apps Script is suggested); **uploaded files only, "Send Submission PDFs" OFF** - the PDF carries the girls' names, nothing in the repo can see the toggle, so this row and the RUNBOOK's read-back after every builder save are the only guard; one Drive folder per form (`Attendance photos - <Region>`; none for the U.S form while it is being disabled); one subfolder per submission named `<Club Name> <Attendance Date>` from the hidden question 5 if the Form Fields picker offers it, else the Club picker - **never question 18, never a roster**; the photo stays required; sharing = the owner plus a short named list (open); retention is the CEO's decision and nothing is deleted until it is taken; the 677 existing photos stay in Jotform (BACKLOG 69); "Require log-in to view uploaded files" stays on and "Auto Delete Submissions" off
- **Why:** uploaded files need a Jotform login to view (an upload URL answers the login page with or without the API key), so no repo script or Apps Script can fetch them, and a Drive scope in the deployed script is a rule-11 outage; Zapier or Make would cost money at this volume and put a third processor in the path of every submission, names included; the integration does not support Shared Drives, so the owner must be a role account
- **Consequences:** the `integrations` property is read-only, so the setup is Ryan's builder saves, each backed up before and diffed after (hunks inside `integrations` only); new submissions only; the Google token can lapse without an alarm (a monthly look at the newest subfolder's date, BACKLOG 70); copying to Drive frees nothing in Jotform - the next row ([plan](plans/2026-10-06-photos-to-drive.md))

### 2026-10-06 — Jotform's storage is watched, not bought ahead

- **Jotform's storage is watched by the repo, not bought ahead**: `tools/form_status.py` prints a `storage:` line first and `tools/auto_sync.py` reads it once per run (`glow/usage.py`: `GET /user/usage` against the plan's `limits`), each of the two limits - cumulative upload space, submissions in the monthly cycle - judged on its own and named: `warn` from 50 %, ATTENTION from 80 % (exit 2, every morning until acted on); never a form problem (no form turns NOT CLEAN for it, and a read that fails is a line, not a failed verify).
- Gold or a retention policy is decided when upload space passes about 50 % (BACKLOG "Gold versus retention")
- **Why:** the account is on Silver (10 GiB of uploads in all, 2,500 submissions a month); at 1.25 GiB and about 1.8 GB of photos a month the cap would stop attendance collection around March 2027 ("Form over quota" disables the forms); Gold is about +$360 a year at nonprofit rates and not needed yet; a busy month (1,250 submissions) must not read as a storage warning, so the two levels are never merged
- **Consequences:** three GETs per `form_status.py` run (the runner's verify included) and per runner run, all reads; never switch on Auto Delete Submissions without reading that BACKLOG item (`backfill_resolve.py` and the question-18 alarm read the submissions) ([plan](plans/2026-10-06-photos-to-drive.md))

### 2026-10-06 — A batch with no names and no count is never a success

- **A batch with no names and no count is never a success.** The attendance processor marks it `Failed` "No participants submitted" (no rows; it blocks nothing); a batch with no names and `Girls_Present__c` > 0 is an **aggregate** and succeeds with no rows
- **Why:** deployed 2026-10-07 03:22 UTC (0AfRP000002gKqn0AE) (plan 2 B). Three blank submissions since 1 September were stored as successes that blocked their club's day, and one submission with ticks and an empty names list still arrived on 2026-10-03 after the required-roster guard; a `Failed` batch is invisible to the duplicate check, so the club's real submission for that day goes through
- **Consequences:** no new Jotform rule for blanks (Ryan, 2026-10-06); `tools/sf_backfill.py`'s fake org, hold wording and read-back follow (2026-10-07); the three legacy blanks are left as they are, or deleted on Ryan's go (BACKLOG 73) ([plan](plans/2026-10-06-attendance-totals.md))

### 2026-10-06 — `Girls_Present__c` is the one attendance count

- **`Girls_Present__c` on `Attendance_Batch__c` is the one attendance count.** Apex sets it on success to the rows created; a partner-reported total is typed into it, with `Creator__c` `Partner report`, per club per month, dated the last day of the month.
- **Total attendance = SUM over `Success` batches; "Jotform only" = the same with `Creator__c` starting `Jotform`; distinct-girl figures are Jotform only and say so**
- **Why:** deployed 2026-10-07 03:22 UTC (0AfRP000002gKqn0AE): the field (plan 2 A) and the count on new batches (B); the back-fill of the older batches (C) done 2026-10-07 (573 batches set; SUM over `Success` = the attendance rows, 7,540). One object, one report type, one filter for the label; aggregates have no names, so no distinct count can include them
- **Consequences:** a one-off back-fill of the existing successes by `tools/sf_girls_present.py` (C), right after the field is deployed and before the totals go on the dashboard; the Monthly Report's weekly counts are never summed into attendance; `Girls_Enrolled__c` is created empty for BACKLOG 58 if Ryan agrees ([plan](plans/2026-10-06-attendance-totals.md))

### 2026-10-06 — "Did not submit" and "blank" defined

- **"Did not submit" = no `Attendance_Batch__c` of any status dated in the window** (a `Failed` duplicate counts as submitted), for three windows: last 14 days, since 1 September, last calendar month.
- **"Blank" = `Failed` "No participants submitted", or a legacy `Success` with `Girls_Present__c` 0.** The existing last-month tile stays row-based ("no Jotform attendance rows", Ryan 2026-10-06) beside the two batch-based windows, the difference named in the dashboard's How-to box
- **Why:** deployed 2026-10-07 03:59 UTC (0AfRP000002gLJp0AM). Non-reporting clubs are excluded at the source, not with a Salesforce-side marker (Ryan, 2026-10-06; the sheet's `jotform=no` marker is the clubs-off plan's), so the lists carry the clubs that cannot submit until their counts arrive
- **Consequences:** the windows test the session date, not the day the submission arrived; the 38 clubs of the three partners count as submitting once their monthly aggregate lands ([plan](plans/2026-10-06-attendance-totals.md))

### 2026-10-06 — Batch reports reach the partner through the lookup

- **The batch report type carries the club's parent via lookup** (`Account__c` → Parent Name), so batch reports group by partner and the dashboard's one Partner filter drives every tile with no new field; a `Partner__c` formula (`Account__r.Parent.Name`) is created only if the check-only validate refuses the two-hop path.
- The custom report type `Attendance_Totals` leaves `Contact_IDs__c` out; the vendor's `Attendance_Batches` type is left untouched (the org already holds a type of that name and label: 2026-10-07, the generator's Build notes)
- **Why:** deployed 2026-10-07 03:59 UTC (0AfRP000002gLJp0AM). Session -51's advice from its two deploys; this org's own DHIS2 dashboard already filters on such a via-lookup column, so the pattern is proven here, and a formula field as a dashboard filter column is not
- **Consequences:** `Status_Message__c` stays in the type for the blank report but goes on no dashboard component and in no printed read-back ([plan](plans/2026-10-06-attendance-totals.md))

### 2026-10-06 — A stray club account is re-parented, never re-created

- **A stray club account the processor created is re-parented, never re-created** (its Contacts and rows stay) - done for the two WESAD clubs on 2026-10-06 10:53 UTC (Ryan's go, `00ee471`); until BACKLOG 27 is automated, a new club's account is created before its first attendance by a weekly round of the 2026-09-30 procedure
- **Why:** their names already equal the picker's text, and the RUNBOOK forbids deleting an account with Contacts or attendance
- **Consequences:** the Monday e-mail's SF Pending list is worked each Monday by Ryan with Claude ([plan](plans/2026-10-06-attendance-totals.md), E)

### 2026-10-06 — Field permissions on the System Administrator profile

- **Field permissions for the new fields are on the System Administrator profile** (the live integration user, the dashboard's running user and every reader are on it; Apex writes in a trigger need none); any other profile that types counts gets edit with the intake plan
- **Why:** deployed 2026-10-07 03:22 UTC (0AfRP000002gKqn0AE) (plan 2 A). The same answer the 2026-09-30 Monthly Report field got; BACKLOG 55's "which other profiles" stays open for the rest
- **Consequences:** if the folders are ever shared wider, `Girls_Present__c` needs read on those profiles too ([plan](plans/2026-10-06-attendance-totals.md))

### 2026-10-06 — The blank batch's message: "No participants submitted"

- **The blank batch's message is the literal "No participants submitted"** - Ryan's `Failed` "No participants" plus one word (confirmed by Ryan, 2026-10-06): one value for the Apex constant, its tests, the report criterion and `sf_backfill.outcome_of`'s prefix
- **Why:** deployed 2026-10-07 03:22 UTC (0AfRP000002gKqn0AE) (plan 2 B). A fixed string carries nothing of the submission, so it can never quote a name, and it reads as a sentence next to "Processed successfully."
- **Consequences:** changing it later means changing it in all four places at once ([plan](plans/2026-10-06-attendance-totals.md))

### 2026-10-06 — A partner off Jotform is marked `no` in the Partners tab

- **A partner that does not report through Jotform is marked `no` in the Partners tab's `jotform` column** (`glow/sync.py PARTNER_COLS` / `JOTFORM_COL`, mirrored in `Roster.gs`); the sync keeps its clubs off every attendance form's Club picker while their girls stay active and enrolled; `yes` or blank is the default; any other value counts as yes and raises ATTENTION.
- **Why:** Ryan, 2026-10-06: Education and English for You, Tumaini La Maisha and Ng'aa Maskani (38 clubs, 751 girls) report attendance to GLOW directly; 0 genuine submissions in five weeks ([plan](plans/2026-10-06-clubs-off-jotform.md))
- **Rejected:** listed in the [plan](plans/2026-10-06-clubs-off-jotform.md#decisions-to-record-docsdecisionsmd), decision 1
- **Consequences:** the Partners tab is exported beside the Roster on every run (`--partners`); RUNBOOK "Clubs that do not use Jotform"

### 2026-10-06 — Such a partner's rosters are retired

- **A roster question whose partner is marked `no` is RETIRED**: kept on the form, hidden and frozen (never written to), off the Club picker and without a show rule, still in question 18's sum; it comes back when the mark is lifted (`~ restored roster`).
- The runner retires or restores at most 5 per region per run (`--max-retires`, `--max-restores`); questions are still never deleted.
- A retired roster whose club's name two partners have had is restored with its long name, as a question-5 change by hand (`--q5-change-ok`).
- **Why:** deleting 38 questions is not on the table (DECISIONS 2026-08-25); the one-time deletion of the two duplicates on 2026-09-30 stays the exception
- **Rejected:** listed in the [plan](plans/2026-10-06-clubs-off-jotform.md#decisions-to-record-docsdecisionsmd), decision 2
- **Consequences:** the first rollout (38 on Africa) is a hand apply; `form_status.py --rendered` counts the retired rosters' `always-hidden` elements, the premise that lets a required roster rest without a rule, proven on the template first ([plan](plans/2026-10-06-clubs-off-jotform.md), step 7)

### 2026-10-06 — "No active girl" retires a roster too

- **"No active girl" is a second trigger for retirement in every region**: `glow/sync.py RETIRE_INACTIVE`, **on** (Ryan, 2026-10-06), only once the club's latest `removed_date` is at least a day before the day of the run **in the sheet's own time zone** (`inactive_retires`, `sheet_today`; `SHEET_ZONE = America/New_York`, the zone `Roster.gs today_()` stamps the date in — not `appsscript.json`'s `timeZone`, the script project's America/Chicago, which no stamp uses); a club whose rows carry no date, or one the tool cannot read, is left as it is
- **Why:** a roster emptied by "REMOVE every girl" and refilled by "ADD the new girls" minutes later must not leave the picker in between — against the UTC date (the plan's first wording) a club emptied after 20:00 New York would have gone at the very next dispatch (review finding, 2026-10-07); it also closes the stale-roster gap (a club that left the active roster stayed pickable, showing girls who had left)
- **Consequences:** the 11 deactivated U.S rosters leave the template's picker at its next sync the day after; `False` is the generated rollback (today's `?` treatment); nothing offline can read the sheet's setting, so the runner compares `SHEET_ZONE` with it on every run (`sheets_client.time_zone`) and raises ATTENTION when they differ

### 2026-10-06 — The U.S clubs deactivated, the U.S form disabled

- *(accepted by Ryan 2026-10-06; the tools built 2026-10-07, not yet applied)* **The 11 U.S clubs are deactivated in the Roster and the U.S form is disabled.** Deactivation = every active row `inactive` with a `removed_date`, ids kept, ClubRegistry, SF Pending and the Partners tab untouched, by `tools/deactivate_clubs.py` - after a guard that reads the region's form for the clubs' submissions since launch (the same text or `<club> - <partner>`, never a bare prefix) and refuses a club that reported in the last 30 days; `--undo` puts the same rows back.
- The form is disabled through `tools/disable_form.py` (`POST properties[status]`, unverified: the re-read decides, the builder is the fallback) - the form first, the clubs after.
- A disabled form is `skipped` by the runner, never `failed`, and is never synced down to an empty Club picker
- **Why:** the U.S form has 0 submissions since 2026-09-01 and its clubs are not expected to report this way; a region with no active club makes `read_roster_csv` exit, so the runner would fail on every run unless the form is skipped first; an empty picker, a guard without terms and a region the sync refuses to read are three untested shapes for a form nobody can open
- **Consequences:** the U.S form's 11 rosters, picker and rules stay frozen on a disabled form; the template retires the 11 rosters at its next hand sync (`RETIRE_INACTIVE`, the day after); the way back is `--undo` (or the Club Roster Form's hold and release for one club), then `--enable` ([plan](plans/2026-10-06-clubs-off-jotform.md), C-D)

### 2026-10-06 — A Partners export travels with the Roster export

- **A Partners export travels with the Roster export**: `--partners` on the sync, the runner and the audit; a hand run without it refuses to restore a retired roster (it cannot tell one from a roster an apply left half-written); an export missing a partner with active clubs is refused (`Partners export lists N of M partners with active clubs …`); one without the `jotform` column marks nobody and says so (a warning the runner raises as ATTENTION), `--apply` refuses to restore a retired roster from it and the runner holds a plan that would
- **Why:** without the floor a cut export would read every partner as unmarked and restore every retired roster unattended, inside every band; a renamed or moved header would do the same for a region holding five or fewer retired rosters (review finding, 2026-10-07)
- **Consequences:** the runner refuses `--roster` without `--partners`; `form_status.py` without `--partners` reads NOT CLEAN on a retired roster of an active club ([plan](plans/2026-10-06-clubs-off-jotform.md))

### 2026-10-06 — The sync creates new clubs' Salesforce accounts

- *(accepted by Ryan 2026-10-06, "look at doing the salesforce clubs records automatically")* **Amends 2026-08-24 "no custom SF client"**: the automatic sync creates a new club's Salesforce Club account itself, as its own integration user (GLOW Sync, an External Client App with the client credentials flow), right before the region's form puts the club on its Club picker; everything else about club accounts is reported, never written ([plan](plans/2026-10-06-sf-new-club-accounts.md))
- **Why:** on 2026-10-03 two new clubs submitted before anyone made their accounts and the processor made partner-less ones; the account must exist before the first attendance (2026-09-30) and a weekly e-mail cannot be that fast
- **Consequences:** bounded writer: create only, at most 5 per region, for clubs being put on a form, never update/rename/delete; repository variable `SF_SYNC` off/plan/apply plus `--apply-salesforce`; the partner comes from `glow/sf_partners.csv`, a new partner is one line there; a rename or a partner move stays manual and is caught by the club code in Description; the sheet's dispatch token is narrowed to Actions: write (it could otherwise change the code that holds the Salesforce secret)

### 2026-10-07 — Duplicate contacts merged with Salesforce's own merge

- *(accepted by Ryan 2026-10-07, "Build tool, then go")* Duplicate Participant contacts of one girl in one club are merged with **Salesforce's own merge** (`Database.merge` in anonymous Apex, `tools/sf_dupes.py`), not by moving rows: the contact that stays is the **back-fill's** where the group has one, else the **earliest created** (ties: the lowest id); groups are formed **within one club only** and each must be exactly one active Roster girl of that club, spelled as stored
- **Why:** `Attendance__c.Contact__c` is master-detail with reparenting off, so rows cannot be moved by an update; a merge moves every child record, keeps the rows' ids and leaves `MasterRecordId` on the merged contact (Recycle Bin, 15 days); the copies differ only in created time and rows; 50 names are real namesakes in different clubs ([plan](plans/2026-10-07-sf-duplicate-girls.md))
- **Consequences:** one Apex run per club, all or nothing, rehearsed first (the rehearsal throws at its end so Salesforce discards it), the rollback file written before the first write, the result read back; a group the Roster does not prove, or with two copies on one date, goes to a person; the same name in two clubs is reported by `check`, never merged; the processor's exact-name match is unchanged (BACKLOG 75)

### 2026-10-09 — Both Attendance folders shared with all internal users

- *(Ryan, 2026-10-09; reverses his 2026-10-06 "folder sharing stays as it is")* Both "Attendance" folders (reports `00lRP000006FVpdYAG`, dashboards `00lRP000006FVpeYAG`) are shared as **Viewer with All Internal Users** (`folderShares` View / `AllInternalUsers` / `Organization`), never with a guest or portal group; girls' names inside Salesforce stay fine for anyone with Salesforce access (2026-10-06, unchanged)
- ([plan](plans/2026-10-09-attendance-reports-public.md))
- **Why:** leadership and staff get the attendance dashboard and its reports in Salesforce instead of administrators only
- **Consequences:** the share opens everything in the folders, the March pilot dashboard and its 5 reports included; the dashboard runs as Ryan and shows the whole organisation to every internal user; to be deployed by Ryan from `data/sf_dashboard_2026-10-02/public_2026-10-09/` (check-only `0AfRP000002gXhZ0AU`); whether a folder deploy replaces shares is not documented, so a folder is deployed only from a fresh retrieve and a share removed in the folder's Share dialog

### 2026-10-09 — One read-only permission set for the attendance reports

- *(Ryan, 2026-10-09)* One permission set, `Attendance_Report_Viewer`, read only, for the 9 active "GLOW Standard User" users: Read on `Attendance__c` and `Attendance_Batch__c`, **View All on Contact and on Account**, and Read on every field the reports and dashboards in both folders show, filter or group that takes a field permission (21, derived from the live metadata, the March pilot reports included).
- The 9th of the 9 is "Portal Login", a **shared login account, not a person**: Ryan included it with the set as built, accepting that it sees every Account and Contact.
- Built and validated by Claude; **assigning it is a record write**, done by Claude's main session or Ryan on Ryan's go, never by the build
- **Why:** a chart's click-through report runs as the viewer: without Read on the objects it is refused, and a filter on a field the viewer cannot read is dropped silently (or the report fails "Invalid Report") - every per-girl report filters on `Creator__c`, so the totals would include the March pilot rows. Account and Contact are Private and club accounts belong to administrators, and the reports start from the Account: without View All on Account the shared account, the one of the 9 without `Portal_User_Login_Access`, read 0 of 200 club accounts. Already the case before this, not a change: `Portal_User_Login_Access` gives the 8 staff Modify All on Account and Contact
- **Consequences:** a new staff user gets the set (RUNBOOK "Attendance dashboard in Salesforce" → Access); a report change that uses another field adds that field's Read to the set; View All also opens donors', households' and organisations' records to the 9, the shared account included (the 8 staff already had Modify All); the narrower alternative, a sharing rule on Club accounts, was not chosen

### 2026-10-09 — "(test)" dropped from the labels; a daily refresh

- *(Ryan, 2026-10-09)* "(test)" is dropped from the **labels** of the dashboard "Jotform Attendance (test)" and the report "Jotform Monthly Attendance (test)"; the DeveloperNames `Jotform_Attendance_test` and `Jotform_Monthly_Attendance_test` stay.
- The dashboard is **refreshed daily** by a schedule Ryan sets in the UI (Subscribe, Daily 05:00 America/Los_Angeles, as the running user)
- **Why:** the dashboard is the real one now; renaming a DeveloperName would break every reference to it (the dashboard's components, the API paths, the RUNBOOK's commands); a refresh schedule is not metadata (the `Dashboard` type has no such field; it is a scheduled job, `CronTrigger`)
- **Consequences:** labels only, so the report's description still starts "Test report:"; the refresh is a step in Ryan's list, not in the deploy, and it stops if the running user is deactivated

### 2026-10-09 — The docs stay one file each; sections instead of table rows

- `docs/RUNBOOK.md`, `docs/BACKLOG.md` and `docs/DECISIONS.md` stay single files. The RUNBOOK is
  grouped by system under a table of contents, each procedure led by the same short list (When,
  Status, Dry run, Apply, Verify, Rollback), finished one-time procedures and history moved to
  their plans; BACKLOG and DECISIONS are one section per item or decision instead of one table.
- `scripts/check_doc_refs.py` (`make check`) keeps every quoted RUNBOOK heading, `#anchor` and
  cited BACKLOG number alive.
- **Why:** the tools and tests quote `docs/RUNBOOK.md` with a section name in about 80 places
  (about 200 with the docs), in files other tracks own, so a split into `docs/runbook/` would
  break them across branches; a table row is one line, so any two edits of one item conflicted
  (BACKLOG cells averaged about 600 characters, DECISIONS about 900).
- **Rejected:** `docs/runbook/` by system and one file per BACKLOG item with a generated index
  (Phase 4 of [plans/2026-10-09-repo-cleanup.md](plans/2026-10-09-repo-cleanup.md) as first
  written), for the reason above.
- **Consequences:** headings are never renamed (add a section instead); a BACKLOG item or a
  decision is updated by a dated bullet.

### 2026-10-09 — A plan is required, an intent optional, the spec stage retired

- Anything beyond a one-line fix gets a plan under `docs/plans/`, committed before the code; an
  intent under `docs/intent/` only captures Ryan's ask before a plan exists, and the spec stage
  is gone (its one file is in `docs/archive/`, its template deleted).
- [docs/plans/README.md](plans/README.md) indexes the plans and intents from their frontmatter
  (`make docs-index`); `make check` fails when it is stale, when a status is not one of
  `proposed`, `accepted`, `in-progress`, `blocked`, `done`, `superseded` (a comment after a `#`),
  or when a `backlog:` item does not exist. A done plan carries `done: YYYY-MM-DD`.
- **Why:** in five weeks one spec was written against 41 plans; the plans' statuses had drifted
  (four plans still "proposed" had been merged on 2026-09-29 and three of them deployed the next
  day; three intents were done while marked proposed or in-progress) because nothing read them.
- **Consequences:** the 2026-10-09 restructure set every plan's and intent's status from the
  evidence (BACKLOG, the plans' Results, git); `docs/README.md` describes the flow.

### 2026-10-09 — Lint with ruff, a small rule set, no formatter

- ruff 0.16.5 (`ruff.toml`) runs in `make check`, CI and the pre-commit hook and fails on any finding: the families E, F, W, B, UP, SIM, PLE and RUF100; E501, E731, E741, B905 and UP031 ignored, each with its reason in the file ([plan](plans/2026-10-09-repo-cleanup.md), Phase 2).
- **Why:** it finds real faults (unused imports and variables, closures over a loop variable, a raise that loses its cause, invisible characters written raw) and stale `# noqa`; the merged tree had about 83 findings, 34 of them auto-fixable.
- **Rejected:** `ruff format` (a diff of about 42,800 lines that flattens the aligned trailing comments the code is read by); isort (it reorders the imports that follow a `sys.path` insert and breaks their `# noqa: E402`); a `pyproject.toml` with an editable install of `glow` (the worktrees share one `.venv` through a symlink, so an editable `glow` would point at one checkout and every other one would test that checkout's code).
- **Consequences:** `make venv` installs ruff (`requirements-dev.txt`); a new rule family is a change of its own.

### 2026-10-09 — Tests found by discovery, one file per subject

- `make check` runs `python3 -m unittest discover -s test -p '*_test.py'`; the 9.4k-line `test/python_test.py` became one file per subject, and what more than one file uses lives in `test/helpers/common.py`, a fixture other test classes borrow as a mixin. The JavaScript suites are every `test/*_test.js` ([plan](plans/2026-10-09-repo-cleanup.md), Phase 2).
- **Why:** every branch edited `python_test.py` and its hand-kept import list, so every merge conflicted there; with discovery a new test file runs without being registered.
- **Rejected:** importing one test class into another module (discovery would run it twice: hence the mixins); splitting `test/forms_logic_test.js` (it stays one file, its `check()` helper shared through `test/helpers/js/`).
- **Consequences:** the split moved test code verbatim (the same 633 test ids then); a new test module imports `helpers.common` first, which puts the repository root and `tools/` on `sys.path`.

### 2026-10-09 — The hooks match path components in every checkout

- `protected_paths.sh` matches path components, ignoring case, in any checkout (the main one, a worktree, a sibling clone): inside the project only the part below it, and the path with symbolic links resolved as well; `~/.claude/settings*.json` and `~/.claude/hooks/` are protected like the project's own.
- `live_gate.sh` lets a read-only command through (its first word `grep`, `rg`, `cat`, `head`, `tail`, `wc`, `ls` or `git log|show|diff|grep|blame|status`, with nothing else that can run in it), and treats a write to a shell startup file (`~/.zshrc` and the others, `.envrc`, `.env`) or `launchctl setenv` as self-approval, blocked even when `GLOW_LIVE_OK` is set ([plan](plans/2026-10-09-repo-cleanup.md), Phase 1; approved by Ryan).
- **Why:** the old prefix match let an edit of `data/`, `credentials/` or `.claude/settings.json` from a worktree or a `./` path through (reproduced); the user-level settings could switch the project's hooks off; 20 of 31 logged blocks were `grep`, `git` or `echo` on the docs; `printf … >> ~/.zshrc` passed.
- **Rejected:** parsing the shell properly: the gate reads text, so a write through `cp`, an editor or a script is not seen - it guards against mistakes, not intent.
- **Consequences:** `test/hooks_test.py` pins both hooks; a checkout under a folder named `data` is not refused as a whole.

### 2026-10-09 — Finished one-offs are deleted, not archived

- A finished one-time tool is deleted; its row in ARCHITECTURE [Retired tools](ARCHITECTURE.md#retired-tools) says what it did, the deleting commit and the `git show` that restores it. `tools/` stays flat; `tools/fix_module_values.py` stays until its undo window closes (BACKLOG 84); `appsscript/Regions.gs` becomes hand-kept data.
- *(the plan's recommended default; Ryan left the question open)* ([plan](plans/2026-10-09-repo-cleanup.md), Phase 3)
- **Why:** an archived script no longer runs against today's `glow/`, yet it would still have to pass `make check` and still be read and edited; git keeps every version.
- **Rejected:** a `tools/archive/` folder; subfolders in `tools/` (about 300 documented paths would break for little gain).
- **Consequences:** restoring one is a `git show` and a `make check` against today's `glow/`; the docs point at the table, not at the file.

### 2026-10-09 — A new club's SF Pending row is written before its Roster rows

- In `handleNewClub_` (`appsscript/FormHandlers.gs`) whether the club is new is decided before any write (it has no girls on file), and every write that may fail comes before the Roster write: ClubRegistry, Partners, then the SF Pending row; after the Roster write only best-effort steps (the sync request, the dropdowns, the ReviewQueue through `tryReview_`, Audit). Live after Ryan's next `clasp push` ([plan](plans/2026-10-09-repo-cleanup.md), Phase 1, A1).
- **Why:** the ReviewQueue write and the SF Pending append ran unprotected after the Roster write; a failure there made the response an ERROR whose retry saw an existing club - no SF Pending row (no account, nothing in the Monday e-mail), no sync request, and a mentor told that the girls just added were "already on the roster".
- **Rejected:** inferring "new" on the retry from the Roster rows' sources and dates (built, then wrong twice in review: when another response for the club ran in between, and when a club enrolled and closed in SF Pending was sent again with one more girl).
- **Consequences:** a failed Roster write that nobody retries leaves a pending SF Pending row for a club with no girls (the response shows ERROR in FormLog and the menu); a pending row closed by hand before the retry gets a second one. RUNBOOK "Missed form responses".

### 2026-10-09 — Private files and ledgers in `glow/private_files.py`

- The owner-only folders and files (0700 / 0600, inside the checkout only under `data/`) and `Ledger`, the append-only CSV of every Salesforce writer, live in `glow/private_files.py`; the tools import it instead of `tools/sf_backfill.py`, which stops being an import hub ([plan](plans/2026-10-09-repo-cleanup.md), Phase 3).
- **Why:** three copies of the ledger and of the folder guard had drifted: one refused a `data/` that a fresh checkout does not have yet.
- **Consequences:** the files' bytes are unchanged; a refusal is `glow.salesforce.Refused`.

### 2026-10-09 — `Client.url()` encodes the query

- `glow.jotform.Client.url()` URL-encodes the key and every parameter, once; a caller passes plain values (a submissions filter as its JSON text) ([plan](plans/2026-10-09-repo-cleanup.md), Phase 1).
- **Why:** two callers encoded the filter by hand, and any other would have sent it raw.
- **Consequences:** the URL those two send is byte-identical to before (tested); no caller pre-encodes.

### 2026-10-09 — Salesforce output repeats error codes only

- What a tool repeats from a Salesforce answer in its output (ATTENTION items, ledger outcomes) is the answer's error codes, `glow.salesforce.error_codes()` (a code has an underscore; no name has), never its words ([plan](plans/2026-10-09-repo-cleanup.md), Phase 3).
- **Why:** `sf_new_clubs.py` took every all-caps word of four letters or more from an answer, so a name Salesforce quoted in capitals could reach the runner's ATTENTION past `auto_sync.redact`, which knows full names only.
- **Consequences:** any code is named (`failed_NOT_FOUND`, no longer `failed_other`); the words of an error are read in Salesforce, not in a log.

### 2026-10-12 — The Group Photo sublabel drops "All girl faces should be visible."

- The Group Photo (question 19) sublabel on the template and the four regional forms becomes "Upload one photo of everyone in attendance today."; this replaces the "faces visible" part of 2026-09-12. One photo per submission stays the rule: `fileLimit` 1 holds it, and `tools/update_static_fields.py` now checks that instead of writing `allowMultiple` No, which reads Yes on every form ([plan](plans/2026-10-12-photo-sublabel.md)).
- The new sentence's translations are the first sentences of the existing ones; the two-sentence entries stay in the translation files, unused once the new sentence is live.
- **Why:** Ryan's request, 2026-10-12.
- **Rejected:** deleting the two-sentence translations from the files (it would delete nothing on a form and lose a rollback's source: the plan, The change 3); writing `allowMultiple` No as well (one photo per submission is the rule Ryan kept, and `fileLimit` 1 already enforces it).
- **Consequences:** live once Ryan runs the plan's steps: per form the sublabel, then the translations (they can only follow it: the tools post what a form shows); the 2026-09-12 translations stay in every store, so a rollback is the old sublabel alone.

### 2026-10-13 — Special events are module options; the same-day rule stays; all three years

- An ad-hoc session outside the curriculum is a module option named `Special Event - <type>` (as the electives are `Elective - <name>`), the first "Special Event - Welcome Session", on every year's module dropdown (q14, q92, q93), with no session dropdown: Salesforce receives `Module__c` = the option's text, `Module_Week__c` blank and `Module_Year__c` the year. The types are `glow/sync.py` `SPECIAL_EVENTS`; the sync appends a missing option and never removes, renames or reorders one; the runner never applies that write ([plan](plans/2026-10-13-special-events.md)).
- One batch per club and date stays: a special event on a day the club also holds a curriculum session is refused by Salesforce as a duplicate, whichever arrives second; mentors submit one per day.
- The option is on all three years' module dropdowns.
- **Why:** Ryan, 2026-10-13: a "Special Events" module that captures unique, ad-hoc sessions. As a module option it needs no new question, no Salesforce field, mapping or Apex change, and existing reports see it as one more module.
- **Rejected:** a "Special Events" module opening a new "Event" dropdown (a new question on five forms whose qid would differ per form, and a new Salesforce field or a combined text anyway); letting a second batch per club and day through (it would mean changing the processor's duplicate checks).
- **Consequences:** question 100 must be blank for an event even after a mentor picked a session first: one more calculation (the session bridge, question 100 from the session dropdown shown) heads the cascade, a reading of Jotform's runtime proven in the browser on the template before any regional form. Year 1 gets one session rule per module like years 2 and 3. A blank `Module_Week__c` through the integration is proven on a Duplicate batch at the rollout. The attendance rate (BACKLOG 58) must decide whether events count as sessions held; a report can exclude them by `Module__c` starting with `Special Event - `.
- 2026-10-14: the runner applies the event options and the rules rewrite on its next run; a new type is merged after the template is applied by hand from the branch ("2026-10-14 — Merged form changes roll out through the runner; review and tests are the gate", below).

### 2026-10-14 — The repo adopts harness v2: the board, ticket branches, tests first, pull requests

- Work is a GitHub issue on this repo's board (epics and task sub-issues; `status:`/`type:`/`size:`/`risk:` labels), done on a `t/<issue>-<slug>` branch in `.claude/worktrees/`, landed by squash merge through a pull request (`/harness:plan`, `/harness:work`, `/harness:land`). A hook refuses edits, commits and pushes on `main`. New tests come before the code and are proven red by `harness-red`.
- The harness runs `scripts/verify.sh` (`make check`, then `VERIFY OK`) as the verify command (`CLAUDE_VERIFY_CMD`; CI keeps running `make check` directly) and `scripts/harness_tests.sh` for the test files a ticket names (`HARNESS_TEST_CMD`): Python by basename through `unittest discover -s test`, JS as plain `node` scripts. A fresh worktree links the main checkout's `.venv`.
- Kept, as inventoried in `docs/agent/harness-prep.md`: every domain hook (`live_gate.sh`, `protected_paths.sh`, `secret_scan.sh`), the permission asks and denies, the domain skills and agents, `REVIEW.md`, the numbered rules, `docs/plans/` for live rollouts, this file. Removed or replaced: `/check`, `/integrate` (its domain steps live on as `/land-checks`), the process paragraphs of `CLAUDE.md` the harness duplicates.
- **Why:** Ryan, 2026-10-13: one process for every project, with the ticket as the context and a review of each change before it lands; the prep inventory found no domain rule the harness would weaken.
- **Rejected:** the scaffold's Python skeleton (`pyproject.toml`, `src/`, `tests/`): this repo has its own layout and `make` targets, so the scaffold ran with `--stack none` and `--no-ci` (`check.yml` stays the CI); `make py` or `make test` as the test command (neither takes file names, so a red proof would run everything and the breaker's cheat run would prove nothing); `python3 -m unittest test/x_test.py` (the standard library's `test` package shadows it).
- **Consequences:** `worklog/worklog.csv` and `docs/agent/handoff.md` can no longer be committed on `main`; where those commits go is an open decision (a chore branch, or `worklog/**` under `HARNESS_SOURCE_EXEMPT`). `git commit` and `git push` moved from `ask` to `allow` on 2026-10-14 (Ryan's edit: dispatched runs work overnight, and a headless run cannot answer an ask, verified in a scratch repo), with the board tools the runs use (`harness-*`, `gh issue|pr|api`, `git worktree|fetch|add`); safe only because the branch guard refuses commits and pushes on `main` and every force push. `git tag`, clasp, `make fixtures` and the `data/`/`backups/` reads stay asks. `BACKLOG.md` keeps its numbers for existing references; new work is a ticket.
- 2026-10-14: where the work log's and the handoff's commits go is decided: a monthly chore ticket ("2026-10-14 — The work log and the handoff reach main through a monthly chore ticket", below).

### 2026-10-14 — The work log runs on harness-worklog; tools/worklog.py retired

- The work log behind the monthly invoice (`worklog/worklog.csv`, `worklog/timezones.csv`) is kept by the harness plugin's `harness-worklog`, what `/harness:worklog` runs; it is canonical. This repository's own `tools/worklog.py` and its tests `test/worklog_test.py` are deleted (ticket #10; restore commands in `docs/ARCHITECTURE.md` "Retired tools").
- **Why:** Ryan, 2026-10-14: one work-log tool. `harness-worklog update` in the main checkout reproduced every existing row of `worklog/worklog.csv` byte for byte and only added 2026-10-14 (a one-line diff), with the same subcommands and switches plus `describe`.
- **Rejected:** keeping `tools/worklog.py` beside it (two tools writing one invoice file, and every fix made twice).
- **Consequences:** work-log fixes go to the harness repository, not this one: the description-paste bug is reported there, not fixed here. The RUNBOOK's commands ("Work log and invoices") are `harness-worklog <cmd>`, with the same switches.

### 2026-10-14 — The work log and the handoff reach main through a monthly chore ticket

- `worklog/worklog.csv` and `docs/agent/handoff.md` are written in the main checkout all month (`/harness:worklog`, `/harness:handoff`) and reach `main` through one chore ticket a month, "Commit the work log and handoff, YYYY-MM" (`--no-tests --needs-local`), whose PR copies both files from the main checkout and lands at month end, before the invoice's `export` (ticket #14; RUNBOOK "Work log and invoices"). This settles the open item in "2026-10-14 — The repo adopts harness v2" (where those commits go).
- Only that chore changes the two paths; a branch that changes either is reported at `/land-checks`.
- **Why:** Ryan, 2026-10-14. `branch_guard` refuses commits on `main`. The log lives in the main checkout (`harness-worklog` resolves a ticket worktree to it, since Harness 07a4835), and the session brief reads the handoff there. On a ticket branch the CSV counts as source (`*.csv` is not exempt from `tests_first`), hence `no-tests`.
- **Rejected:** `worklog/**` under `HARNESS_SOURCE_EXEMPT` (the other option in `docs/agent/harness-prep.md` "Before you adopt" 4).
- **Consequences:** the main checkout is dirty on the two paths all month; `/harness:land` cleans it, restoring the copies byte-identical to the landed content before the fast-forward (since Harness e372870), and a copy that differs blocks the pull instead of being lost; a ticket is created each month.

### 2026-10-14 — Merged form changes roll out through the runner; review and tests are the gate

- A form change the sync generates — the question-18 rule order and operand, the special-event session bridge, the rosters' required flag, a module dropdown's `calcValues` and the special-event options — is rolled out by merging it to `main`. `tools/auto_sync.py` `check_bands` no longer holds a region for any of the five lines; `Run.region` applies them like a roster change, within the bad-data bands: a rules-only plan that carries the question-18 or session-bridge warning is applied and never `in-sync` (the SyncLog detail says `question 18 rules rewritten` / `special-event rules rewritten`), and `REQUIRED roster` and module lines never count against `--max-updates` (they come from a constant, not the export). The sync's two warnings and the live docs say so (ticket #30, epic #29).
- **Why:** Ryan, 2026-10-14: "Update the code so that AUTO_SYNC_APPLY and other logic we added to gate certain actions is rewritten to no longer be needed. Now with the harness and test reviews, this kind of blocker slows us down."
- **Rejected:** keeping the holds (one `attention` per region until each form was applied by hand, template first, the runner paused): the harness's tests and reviews are now the gate, and the hold turned every generated change into a hand apply on five forms.
- **Consequences:**
  - a merged generated change reaches every enabled regional form on the runner's next run (the next roster change, at the latest the morning backstop, or a run from the Actions tab on Ryan's go), with no human step between the merge and the write: the PR review and the tests are that step, with the bad-data bands and the backup, verify and retry around every apply;
  - the template and a disabled form are applied by hand (the template is not in `REGIONAL_FORMS`; a disabled form is `skipped`); the template's browser checks run from the ticket branch, before the land;
  - a form rolled back by hand while `main` disagrees is rolled forward on the next run, and a constants-off commit on `main` rolls every enabled regional form back the same way: a rollback pauses the runner or merges first;
  - `AUTO_SYNC_APPLY` stays the emergency off switch, normally `1`; the rollout steps that still toggle it, and `tools/form_status.py`'s "a sync apply by hand" hints, are follow-up tickets.

### 2026-10-14 — The live gate asks Ryan in the session; GLOW_LIVE_OK no longer opens it

- `.claude/hooks/live_gate.sh` answers a live command with a PreToolUse `ask` decision: Claude Code shows Ryan the approval prompt (the matched trigger, the command, the RUNBOOK section) and his answer is the go, one command at a time. It never answers `allow`, and `GLOW_LIVE_OK` grants nothing. It denies, whatever the mode, a command that approves itself, a subagent (`agent_id` in the input; `agent_type` alone is the main thread of a session started with `--agent`, which gets its mode's decision) and a session that cannot show the prompt (`permission_mode` other than exactly `default`, `acceptEdits`, `auto` or `plan`: `bypassPermissions`, `dontAsk`, a missing or an unknown value). The log line carries the mode (ticket #36).
- "Prompt, don't parse" (Ryan, 2026-10-14): the hook matches text and never reads shell words. Its patterns are main's, tried in any case on the command on one line, on the same with each backslash-newline removed as the shell joins a word (`--ap\<newline>ply`), and on both with the quote and backslash characters removed (`gh 'workflow' run`, `GH variable set`, `g""h` match); a `-R`/`--repo` may stand between a family's words (`gh variable -R o/r set`). A `gh api` call is live when the command holds a `gh` word (any case, a path ending `/gh`, `=gh`), the word `api`, and `actions/`, `dispatches` or `graphql` anywhere, whatever the method: reads of those ask too; so is the GitHub API by its URL (`api.github.com/…` with `actions/`, `dispatches` or `graphql`). Every other `gh api` call (issues, comments, labels, the harness's resume reads) is ungated, as before; prose that mentions `gh api` without those words passes.
- `.claude/settings.json` keeps main's `Bash(gh api:*)` allow and has no ask rule on `gh api`; it backs the hook with ask rules for the live families (`gh variable|secret set|delete`, `gh workflow run|enable|disable`, `gh run rerun`, `sf project deploy start|quick|validate|resume` (not `report` or `preview`, which read), `sf apex run`, the `sf data` writes; `Bash(npm run clasp*)` now covers `npm run clasp:push`), and blocks the command when the hook fails or times out (`onFailure: "block"`).
- **Why:** Ryan, 2026-10-14: "this kind of blocker slows us down" - with the harness and the test reviews, a restart with `GLOW_LIVE_OK=1` was the only way to let Claude write, and that pre-approval was session-wide (one stayed open for 10 days, BACKLOG 83) and travels into every dispatched run (`harness-work dispatch` passes its environment on). An approval per command, where Ryan sees the command, is what rule 1 always meant. Text patterns fail closed: a quoted word or an odd case matches more, never less.
- **Rejected:** `permissions.ask` rules alone (prefix matches: they cannot see `--apply`, `api.jotform.com` or `apply=true` inside a command, nor express the read-only exception or the self-approval refusal); keeping `GLOW_LIVE_OK` as a pre-approval beside the prompt; reading `gh api` commands as shell words to ask on every write, on any path (this ticket's 9794ffe..a2cf749): four reviews found the reader failing open on each gap between it and the shell (comments, substitutions, zsh `=gh`, quoted words); a `Bash(gh api:*)` ask rule (it would stall the harness's resume reads in a dispatched run).
- **Consequences:** every live command is a prompt; a headless or dispatched run never runs one (its ask is denied); `gh api` writes on paths without `actions/`, `dispatches` or `graphql` (issues, comments, labels) stay ungated, as on main; a message (a commit, a PR body) that names a live flag, family or `gh api` path asks too, an accepted over-ask, unless the command is read-only and alone; the hook and the settings stay owner edits (`protected_paths.sh`): Ryan applies the reviewed patch by hand. The RUNBOOK, the skills, README and `.env.example` follow in #37.
