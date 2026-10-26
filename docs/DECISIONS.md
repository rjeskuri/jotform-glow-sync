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
- 2026-10-23 (#110): the classifier also takes girls "not on the form", the sender of a roster-change report is e-mailed the Club Roster Form's link, and a report that the form is not working becomes a "Form not working report" item — see the 2026-10-23 entry

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
- 2026-10-23: two club names that end in the same bracket (its words as `matchWords_` folds them), each with a word that is not filler before it, are compared without that bracket (`RosterOps.gs placeSuffix_`, then the rules above): a partner's clubs at one place all end in "(<place>)", and the place's words lifted similarity_ of the whole names over `SIMILAR`, so on 2026-10-08 a genuinely new club at a place where the partner had clubs was held, then sent again under another name (#111). The place bracketed on one side only, and a name that is only the place, are compared whole as before (the place-only choice was the tests' call: such a name has nothing but the place to tell it from the clubs there, so staff decide); a shared place misspelt on one side (Centre / Center) is not the same bracket, so those names are still compared whole and still held. Live after Ryan's next `clasp push` (`.claude/skills/deploy-appsscript/SKILL.md`; rollback = the previous deployment, per that skill).

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
- 2026-10-16: that rollback is superseded - never redeploy `data/sf_processor_2026-10-02/before`: it would undo the processor's 2026-10-07 changes (the blank backstop, `Girls_Present__c`, the name cleaning); a rollback starts from a fresh retrieve (the 2026-10-16 decision below)

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
- 2026-10-15: amended - the total is Jotform plus the three partners (Education and English for You, Tumaini La Maisha, Ng'aa Maskani); any other Salesforce-entered attendance is left out (#35, see the 2026-10-15 entry)
- 2026-10-19: amended - the three partners' figure is not typed per club: it is their Monthly Report's Monthly Max, one `Partner report` batch per partner per month on the partner account (#60, see the 2026-10-19 entry)

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
- 2026-10-15: deployed 2026-10-09 ~05:35 UTC, by the metadata dates (the deploy id is not known); `public_2026-10-09/` is superseded and never redeployed: its dashboard would overwrite the 2026-10-15 one (RUNBOOK "Attendance dashboard in Salesforce", Access)

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
- 2026-10-22: amended - a second batch for the same club and date with the same module is merged into the first: its missing girls are added as rows of the original batch (#108; "2026-10-22 — A corrected re-submission adds its missing girls to the day's original batch", below); a different module stays "Duplicate", so the same-day rule itself stands.

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

### 2026-10-15 — Total attendance is Jotform plus the three Salesforce-reporting partners

- Total attendance = the Jotform attendance plus the Salesforce-entered counts of Education and English for You, Tumaini La Maisha and Ng'aa Maskani, the three partners whose clubs are to report through Salesforce only. Their retirement from the forms (the Partners tab's `jotform` = `no`) is pending ([plan](plans/2026-10-06-clubs-off-jotform.md), nothing applied); until then a Jotform batch from their clubs counts once, through the Jotform branch of the filter. Any other club's attendance entered in Salesforce is left out of the total. The dashboard shows "Total attendance (Jotform + 3 partners)" beside "Attendance (Jotform only)"; there is no distinct-girls tile; the Monthly Report is never added to attendance (ticket #35; [plan](plans/2026-10-15-attendance-total-three-partners.md); RUNBOOK "Attendance totals and partner-reported counts").
- **Why:** Ryan, 2026-10-15: "There are 3 African partners that were specified that will give their attendance through Salesforce only. Any other clubs' attendance through Salesforce should be filtered out."
- **Rejected:** the total of the 2026-10-06 decision (deployed 2026-10-07), the sum over every `Success` batch (it would count any club's Salesforce entry); a "Girls reached (distinct)" tile (the ticket's first outline).
- **Consequences:** the two Total reports carry the filter logic `1 AND (2 OR 3) AND 4 AND 5`; a fourth partner that reports through Salesforce needs its name added to filter 3 of both reports, on Ryan's go.
- 2026-10-16: the retirement is applied - the three partners are marked `no` and their 38 clubs are off the template's and the Africa form's Club picker (Ryan's go, ticket #56; [Result](plans/2026-10-06-clubs-off-jotform.md#result)); the double count's path through the Jotform picker is closed for these clubs.
- 2026-10-19: amended for the three partners only - their monthly figure is their Monthly Report's Monthly Max, copied as one `Partner report` batch per partner per month; "the Monthly Report is never added" still holds for every other partner (see the 2026-10-19 entry, #60).
- 2026-10-20: amended - total attendance (girls × sessions) is no longer tracked; the dashboard's tiles become girls who attended, Jotform girls plus the three partners' Monthly Max (see the 2026-10-20 entry, #59; deployed 2026-10-21).

### 2026-10-16 — A Salesforce dashboard or report deploy starts from a fresh retrieve; old packages are never redeployed

- Every dashboard or report deploy, a rollback included, starts from a fresh retrieve of what is live, edited only where it changes; no older package under `data/sf_dashboard_2026-10-02/` (`before/`, `build/`, `after/`, `fix1/`, `after2/`, `totals1/`, `live_2026-10-07/`, `public_2026-10-09/`, `before_public_2026-10-09/`) or `gen.py` build is redeployed, nor an older Apex copy (`data/sf_processor_2026-10-02/before`, `data/sf_totals_2026-10/before/`): a `before/` is a rollback only for its own change, while a retrieve still equals that change's `after/`
- The only rollback for the 2026-10-15 change is the three components it changed (the dashboard `Attendance/Jotform_Attendance_test` and the reports `Attendance/Total_Attendance_Last_Month` and `Attendance/Total_Attendance_by_Partner_by_Month`), redeployed from `data/sf_totals2_2026-10-15/before/` after a fresh retrieve of them shows nothing was deployed since (equal to its `after/`); never the other two components that folder holds (RUNBOOK "Attendance dashboard in Salesforce", Rollback)
- **Why:** Ryan, 2026-10-16 (ticket #35 review): "I don't want to overwrite with an old package so make sure that doesn't happen." Steps and rollbacks in older plans still read as procedure and would have overwritten the 2026-10-15 dashboard
- **Rejected:** keeping the old rollbacks with a "check first" caveat (one missed caveat overwrites live work)
- **Consequences:** the old steps in `docs/plans/2026-10-02-attendance-dashboard.md`, `2026-10-02-attendance-processor-one-insert.md`, `2026-10-06-attendance-totals.md` and `2026-10-09-attendance-reports-public.md` are marked superseded or done-never-rerun; RUNBOOK "Attendance dashboard in Salesforce" (Rollback), `.claude/skills/salesforce` and `docs/agent/2026-10-workflow.md` carry the rule

### 2026-10-19 — The three Salesforce-reporting partners' monthly figure is their Monthly Report's Monthly Max

- The monthly figure of Education and English for You, Tumaini La Maisha and Ng'aa Maskani is their Monthly Report's "Monthly Max" (`DHIS2__c.Monthly_Total__c`, roughly the month's unique girls), copied by `tools/sf_partner_monthly.py` as one `Attendance_Batch__c` per partner per month: `Account_Name__c` = the partner's Account name, dated the month's last day, `Creator__c` `Partner report`, no names (ticket #60; [plan](plans/2026-10-19-partner-monthly-max.md); RUNBOOK "Attendance totals and partner-reported counts").
- This replaces "the Monthly Report is never added to attendance" (2026-10-06, 2026-10-15) for these three partners only; every other partner's Monthly Report stays out, and its weekly counts are never summed. It also replaces the per-club intake contract (BACKLOG 72): no separate intake, no per-club counts.
- The dashboard's measure becomes girls who attended: Jotform girls plus the three partners' Monthly Max (#59, which changes the dashboard to read these batches).
- **Why:** Ryan, 2026-10-19: no separate intake; the number is the one their Monthly Report already carries. The partners file it anyway (between the 5th and the 12th of the next month), so nothing new is asked of them.
- **Rejected:** the intake options of BACKLOG 72 (a small Jotform form, a Salesforce screen flow, a sheet import - all per club); summing the Monthly Report's weekly counts ([plan](plans/2026-10-06-attendance-totals.md), "Not chosen": a partner that ticks "submitted electronically" and still types counts would be counted twice).
- **Consequences:** a monthly run after the reports are filed (about the 12th), dry run first and `--apply --vpn-off` on Ryan's go; the batches sit on the partner accounts, which the 2026-10-15 total's filter 3 (the club's parent is one of the three) does not match until #59; a Monthly Report corrected after the copy becomes an update on the next run (old → new, the ledger keeps the old count).
- 2026-10-21: the partner batches count in the dashboard's tiles since 2026-10-21 (#59, deployed on Ryan's go; see the 2026-10-20 entry).

### 2026-10-20 — The dashboard's headline is girls who attended (Jotform + 3 partners); total attendance is no longer tracked

- Total attendance (girls × sessions) is no longer tracked. The dashboard's top row is two tiles headed "Girls who attended (Jotform + 3 partners)", last month and this month so far; each = the Jotform girls who attended in the month, each girl once (unique `Attendance__c.Contact__c` over Jotform batches), plus the `Girls_Present__c` of the three partners' `Partner report` batches for the month (Education and English for You, Tumaini La Maisha, Ng'aa Maskani: their Monthly Max, copied by #60), with no de-duplication. The monthly chart and the "How to read this dashboard" box follow the same rule (ticket #59; [plan](plans/2026-10-20-girls-attended-tiles.md); RUNBOOK "Attendance dashboard in Salesforce").
- This amends 2026-10-15: its two measures, "Total attendance (Jotform + 3 partners)" and "Attendance (Jotform only)", and the two Jotform-only girls tiles leave the top row. Built 2026-10-20 (`data/sf_girls_tiles_2026-10-20/build/`), deployed on Ryan's go 2026-10-21 04:59-05:10 UTC ([Result](plans/2026-10-20-girls-attended-tiles.md#result)).
- **Why:** Ryan, 2026-10-19: total attendance is "not a number we need to track; we only want unique girls who attended in a month", and "keep it simple": the three partners give one number, added to the Jotform figure, with no girls in two clubs to worry about. Their Monthly Max is roughly the month's unique girls, so the sum is one kind of number; girls × sessions plus a Monthly Max would have been a mixed sum.
- **Rejected:** Jotform girls only until a partner intake existed (the ticket's option b; Ryan chose no separate intake, 2026-10-19); de-duplicating the partners' girls against Jotform (they report a count without names); a joined report (it reaches a dashboard only as a chart, and a Metric tile reads one report, so both parts share one report type, `Attendance_Batches_and_Girls`); keeping the total-attendance tiles beside the new ones.
- **Consequences:**
  - new metadata (seven components): the formula fields `Attendance_Batch__c.Partner_Girls__c`, `Attendance__c.Contact_Key__c` and `Attendance__c.Has_Row__c`, the report type `Attendance_Batches_and_Girls` (batches with or without attendance rows), the reports `Girls_Attended_Last_Month`, `Girls_Attended_This_Month` and `Girls_Attended_by_Month`, and Read on the three fields for `Attendance_Report_Viewer` and in the partial Admin profile (three entries);
  - two fields the build did not plan, found at the deploy (2026-10-21): a summary formula cannot unique-count a lookup (the check-only refused `Attendance__c.Contact__c:UNIQUE`), so `Contact_Key__c` = `CASESAFEID(Contact__c)`, the girl's record id as text (never a name), is what the reports unique-count; and that unique count counts the empty key of a row-less batch as one value (2,889 against SOQL's 2,888), so `Has_Row__c` = 1 on every row and the summary formula is `Attendance__c.Contact_Key__c:UNIQUE - IF(RowCount > Attendance__c.Has_Row__c:SUM, 1, 0) + Attendance_Batch__c.Partner_Girls__c:SUM`, one off only when a row-less batch is in the period;
  - this month's partner part is 0 until the partners' Monthly Report is filed and copied (about the 12th of the next month);
  - the Partner filter set to one of the three partners shows only that partner's Jotform girls (their batch sits on the partner account, whose parent is blank);
  - the deploy had two phases: the fields, the permission set, the Admin profile entries, the report type and the reports first; their two Metric reports were checked against SOQL before the dashboard was deployed (2026-10-21: last month 3,633 = `COUNT_DISTINCT(Contact__c)` over the Jotform rows 2,888 + 745; this month 2,944 + 0); the Partner filter's blank match keeps the partner batches;
  - the reports `Total_Attendance_Last_Month`, `Jotform_Total_Attendance_Last_Month`, `Total_Attendance_by_Partner_by_Month` and `Jotform_Attendance_This_Month` are no longer used by the dashboard and kept until Ryan decides which to delete;
    - 2026-10-21: all four deleted on Ryan's go, 05:22 UTC (deploy `0AfRP000002hhq90AA`); restore one from `data/sf_girls_tiles_2026-10-20/before/` (#59; RUNBOOK "Attendance dashboard in Salesforce");
  - a fourth Salesforce-reporting partner needs its account added to filter 4 of the three reports and to `tools/sf_partner_monthly.py`, on Ryan's go.

### 2026-10-21 — The automatic Salesforce club sync runs as Ryan's own user

- The automatic sync (BACKLOG 27, `SF_SYNC`) logs in to Salesforce as **Ryan's own user**, through the External Client App "GLOW Sync" (OAuth client credentials, scope `api`, Run As Ryan), created 2026-10-21 through the Metadata API on his go (deploys `0AfRP000002hjdR0AQ` and `0AfRP000002hjiH0AQ`). There is no "GLOW Sync" user and no "GLOW Club Sync" permission set. This amends 2026-10-06 ("its own integration user"); the rest of that design (create only, at most 5 per region, all or nothing, the end-of-run check) is unchanged ([plan](plans/2026-10-06-sf-new-club-accounts.md), amendment 2026-10-21; RUNBOOK "New clubs' accounts, automatically").
- **Why:** Ryan, 2026-10-21 (ticket #66): the sync runs as himself, and his administrator rights cover the access. He was told the risks and accepted them.
- **Rejected:** the integration user "GLOW Sync" (Salesforce Integration licence, profile "Minimum Access - API Only Integrations") with a minimum permission set "GLOW Club Sync" (Account Read, Create, View All; no Edit); it keeps the secret's reach small and the creator visible, but needs the user, the licence and the permission set set up and kept.
- **Consequences:**
  - the GitHub secrets `SF_CLIENT_ID` / `SF_CLIENT_SECRET` hold administrator access (scope `api`): the workflow runs only on `main`, the dispatch token loses Contents, only Ryan edits secrets and workflow;
  - a login from GitHub's data-centre addresses can freeze Ryan's user (Salesforce cannot allowlist them), which revokes all his tokens, the Jotform connection's included, as on 2026-09-30; the response (`SF_SYNC=off`, another administrator unfreezes, Jotform re-authorised) is in the RUNBOOK;
  - `CreatedById` and owner no longer tell the sync's accounts from Ryan's own: the Description `created by the automatic sync <date>` does, for any rollback;
  - the first create runs NPSP's and Mailchimp's triggers as an administrator;
  - the code still says "GLOW Sync" (log line, hints, docstrings): the app's name, wording only.

### 2026-10-21 — The photos land in Ryan's My Drive and a standalone Apps Script moves them to the company Shared Drive

- Jotform's Google Drive integration runs on Ryan's company account, not a GLOW role account (the photos plan's open decision 1). It writes only into that account's My Drive, so `drive-sync/`, a standalone Apps Script project owned by the same account, moves each submission subfolder from `Attendance photos - <Region>` into that region's folder on the company Shared Drive every 15 minutes, once it has not changed for 10 minutes (ticket #89; [plan](plans/2026-10-21-drive-photo-mover.md); RUNBOOK "Photo mover").
- A resubmission (the name already there once) is merged file by file and nothing is ever replaced; a name there twice is refused; the mover never shares, links, copies, trashes or e-mails a file; the folder ids live in its Script Properties; its log holds counts and folder names only.
- **Why:** Ryan, 2026-10-21: "Jotform will only use my local company gmail, but it needs to go to a company shared drive." The integration cannot write into a Shared Drive, and photos of minors must not stay in one person's My Drive.
- **Rejected:** a GitHub Actions job with a service account (Ryan's My Drive shared to a robot, its key as a secret, the photos readable from the runner); putting the mover in `appsscript/` (a Drive scope there stops the form-submit trigger until re-authorised, CLAUDE.md rule 11); copy-then-trash (a second copy of the photos in Ryan's trash for 30 days).
- **Consequences:** Ryan's account is at least a Content manager on the Shared Drive (Manager if Drive refuses the folder move); its members are the named list only; the mover goes live on Ryan's go (push, authorise, dry run, the template test, then the trigger); the monthly token check (BACKLOG 70) looks at the Shared Drive's folders.
- 2026-10-22: the order is reversed: the mover is set up before #63, not after it (see the 2026-10-22 entry).

### 2026-10-21 — Duplicate and obsolete records in Salesforce: four flags, and an Account duplicate rule that reports only

- "Duplicate Record" and "Obsolete Record" checkbox fields (`Duplicate_Record__c`, `Obsolete_Record__c`) on Account and on Contact, default false; one Matching Rule and two report-only Duplicate Rules on Account, one per record type (Club and Household), sharing that Matching Rule (ticket #84; [plan](plans/2026-10-21-sf-duplicate-obsolete-flags.md); RUNBOOK "Duplicate and obsolete records in Salesforce"). Two Accounts are duplicates when they have the same name ignoring capitals and spacing, the same parent and the same record type; the deliberate `<club> - <partner>` names never match. The Account rules' action is Allow with Report only, no Alert and no Block. The existing Contact rule "First & Last & Account" is kept as it is, Report only since 2026-10-01 (BACKLOG 54); a Contact is flagged duplicate by the batch (#85) when it sits in one of that rule's duplicate record sets.
- Obsolete: a partner whose `Partner_Status__c` is Archived; a Club account whose club is deactivated in the Roster, or with no attendance batch for 6 months and created more than 6 months ago (the September 2026 clubs are not flagged before March 2027); a Participant contact (a girl) with no attendance in 12 months, while staff, mentor and coordinator contacts are never flagged by rule. The clubs of a partner marked `no` in the Partners tab's `jotform` column (the three Salesforce-reporting partners) are judged by their partner account's `Partner report` batches, not their own, since their attendance arrives as one batch on the partner account and never on the club (review, 2026-10-21; Ryan can overrule it).
- Administrators only set or clear a flag by hand (Edit on the fields); the users who read the reports read the flags (Read in `Attendance_Report_Viewer`). Flagged records are shown in the kept reports and dashboards, with the flags as a filter; nothing is excluded by default.
- The Matching Rule `Account.Name_Parent` matches Name (Exact, case-insensitive) and ParentId (blank matches blank); one report-only Duplicate Rule per record type, Club (`Account.Name_Parent_Club_Report`) and Household (`Account.Name_Parent_Household_Report`), carries the condition Record Type equals that type, since Salesforce does not allow Record Type as a matching-rule field (review, 2026-10-21; Ryan can overrule it). Together the three rules are the "same name, same parent, same record type" answer for the two record types in use.
- **Why:** Ryan, 2026-10-21: "move forward with this." GLOW asked how the terms would be defined and how flagged records would be treated (the annotated SOW, p.9); these are Ryan's working answers, provisional until GLOW defines the terms, and GLOW can change any of them (the deploy waited for Ryan's go, given 2026-10-22). Report only because an alert refuses a record created by code: the Alert on the Contact rule failed live attendance batches mid-way until 2026-10-01 (BACKLOG 54), and the attendance processor, `tools/sf_new_clubs.py` and the Jotform integration create Accounts and batches by code. The two design changes are the review's (2026-10-21), within Ryan's answers: without the exception the 6-month rule would flag the three Salesforce-reporting partners' clubs from March 2027 although their attendance is reported; a RecordTypeId matching item is not available in Salesforce.
- **Rejected:** Alert or Block on the Account rules (an alert refuses the processor's partner-less Club accounts and the sync's new accounts, and over REST needs the `Sforce-Duplicate-Rule-Header` on every insert); excluding flagged records from the kept reports, or hiding them (GLOW's own question about the existing reports: shown, with a filter, so nothing in a report moves until GLOW decides); merging or cleaning legacy records (SOW p.10, out of scope); RecordTypeId as a matching item (Salesforce does not allow Record Type as a matching-rule field); judging a `jotform=no` partner's clubs by their own batches (they have none by design).
- **Consequences:** the deploy waited for Ryan's go, given 2026-10-22 (the plan's Rollout); the rolled-back Apex proof planned here could not work and was replaced by a no-DML diagnostic (the 2026-10-22 entry); the flagging batch is ticket #85, which sets the flags by these criteria, judges the clubs of a `jotform=no` partner by their partner account's `Partner report` batches, and is their only writer besides an administrator; `glow.salesforce.duplicate_account_groups` is the Python side of the Account rules, compared with their `DuplicateRecordSet`s at the read-back and in the monthly check; a third record type on Account would need a third Duplicate Rule; a definition GLOW changes amends this entry and the RUNBOOK section.
- 2026-10-22: amended, see the 2026-10-22 entry below - the rules were deployed that day on Ryan's go (`0AfRP000002htOH0AY`, 12:33 UTC); the rolled-back Apex proof planned here could not work, and the proof is the no-DML `Datacloud.FindDuplicates` diagnostic; the record-type condition picks only which rule runs for the record saved, so Salesforce may report a cross-type pair (a Household account and a Club of one name and parent), which the monthly check reviews by hand.

### 2026-10-21 — Retired Salesforce reports and dashboards are moved to Decommissioned, never deleted; a copy goes there before each change

- A Monthly Report (`DHIS2__c`) report or dashboard that epic #68 retires is moved to the hidden folder "Decommissioned" (a report folder and a dashboard folder, both labelled so, visible to administrators only) and keeps its Id; nothing is deleted in this epic (ticket #69; [plan](plans/2026-10-21-sf-reporting-inventory.md); RUNBOOK "Monthly Report dashboards in Salesforce").
- Before a report or dashboard changes, a copy of it as it was goes to Decommissioned, carrying its source Id and the ticket, in addition to the `before/` retrieve.
- **Why:** Ryan, 2026-10-21: "Create a decommissioned folder to put any old copies in in case we need to revert any changes." A copy in Salesforce is one a Salesforce user opens and restores with Save As or a move.
- **Rejected:** deleting the retired reports and dashboards (an undo would rebuild them from metadata, with new Ids and their links and subscriptions gone); archiving them only in `data/` (the `before/` retrieves), which Salesforce users cannot reach and only a metadata deploy restores.
- **Consequences:** two more folders, both hidden; every later task of epic #68 copies a report or dashboard into Decommissioned before it changes one, and moves a retired one there (`tools/sf_report_folders.py`, #71); the shares API is the measure of the folders' privacy (`Folder.AccessType` reads `Hidden` even on a shared folder); the RUNBOOK section "Monthly Report dashboards in Salesforce" and `.claude/skills/salesforce` carry the rule.
- 2026-10-23: the folders exist since 2026-10-21 (deploy `0AfRP000002hjLh0AI`, hidden, no share). The API proof (#69) amends "moves a retired one there": the Analytics API copies and moves a report and keeps its Id; it clones a dashboard but refuses to rename, describe or move one (400 `JSON_PARSER_ERROR`), so a dashboard's name, description and folder are set by hand in Lightning (Ryan), with its Id unchanged ([plan, API proof](plans/2026-10-21-sf-reporting-inventory.md#api-proof)).

### 2026-10-22 — The photo mover is set up before the forms' Drive integrations (#63 depends on #89)

- The photo mover (#89) is set up first and its My Drive source folders, `Attendance photos - <Region>`, exist before any form's Google Drive integration; #63 then points each form's integration at its region's source folder, the template before any regional form. Each live step on Ryan's go: (1) land PR #91, code only; (2) setup: the Shared Drive's folders named exactly `Africa`, `Asia`, `Latin America`, `Template` (`U.S` only if its form is re-enabled), one My Drive source folder per region, the standalone project (`.clasp.json` from the example) and its push, the Script Properties `SOURCE_FOLDER_<REGION>` / `TARGET_FOLDER_<REGION>`, `previewMoves` on the empty folders (writes nothing); (3) #63 for the template only, Ryan in the builder (RUNBOOK "Photos", steps 1-2); (4) a test upload on the template and its read-back, `previewMoves`, one `moveSettledPhotos`, then `installTrigger`; (5) only then #63 for the regional forms ("Photos", step 5), one at a time, each followed by a check of the next run's log ([plan](plans/2026-10-21-drive-photo-mover.md), Rollout; RUNBOOK "Photo mover").
- This replaces the 2026-10-21 plan's order, in which the mover went live after #63's integration on the template.
- **Why:** Ryan, 2026-10-22: the mover is set up first and makes the My Drive source folders that each form's integration is then pointed at; the folders carry the names the mover requires before any photo lands in them.
- **Rejected:** #63 first, then the mover (the 2026-10-21 order).
- **Consequences:** #63 depends on #89 on the board; the setup's dry run runs on empty folders and shows only the configuration (`CONFIG refused` or every count 0); the template test after #63 is the first real move. Whether Jotform writes into the existing folder or creates a second one of that name is unverified until that test ([plan](plans/2026-10-21-drive-photo-mover.md), Risks).

### 2026-10-22 — The Account duplicate rules' proof is a no-DML diagnostic; cross-type pairs are accepted

- Amends the 2026-10-21 entry (ticket #84): its rules were deployed on 2026-10-22 on Ryan's go (deploy `0AfRP000002htOH0AY`, 12:33 UTC; [Result](plans/2026-10-21-sf-duplicate-obsolete-flags.md#result)), and two things changed after the deploy. The proof of the rules is the no-DML `Datacloud.FindDuplicates` diagnostic: `findDuplicates` on three unsaved copies of existing accounts, printing only `DIAG|` lines with each rule's name and its match count; it inserts nothing (the plan, "The diagnostic's script").
- A Duplicate Rule's record-type condition picks only which rule runs for the record being saved and does not limit the candidates, so Salesforce may report a Household account and a Club of one name and parent as a pair. Such a cross-type pair is accepted and documented (RUNBOOK "Duplicate and obsolete records in Salesforce"), with no code or metadata change: `glow.salesforce.duplicate_account_groups` keeps its own definition (the same record type too), and the monthly check reviews any such pair by hand.
- **Why:** Ryan, 2026-10-22, after the deploy. The rolled-back insert proof of the plan's first version, run at 12:35 UTC on Ryan's go, could not work: Salesforce's duplicate matching does not see records inserted earlier in the same uncommitted transaction, so all 7 inserts were saved and the rollback left 0 records, but 0 DuplicateRecordSets appeared - a flaw of that proof, not of the rules. The diagnostic, run the same day at 12:58 UTC on Ryan's go, showed the rules at work: an upper-cased copy of a Club with a parent ran the Club rule, 1 match; a copy of a Household account ran the Household rule, 1 match; a Household account with a club's name and ParentId ran the Household rule and matched 1 record, the Club, which is how the cross-type pair came to light.
- **Rejected:** keeping the rolled-back insert proof (it cannot see its own inserts); a third rule or a Matching Rule item to keep the two record types out of one set (a Matching Rule cannot carry Record Type, and the condition applies to the record saved only); dropping the Household rule.
- **Consequences:** the plan's proof step and its quoted script are the diagnostic; the monthly check compares the rules' sets with `duplicate_account_groups`, and a set without a group may be a cross-type pair, looked at by id and by hand; step 8, the next day's batch check (2026-10-23 or later), stays the live check of the rules' action and is pending as of this entry.

### 2026-10-22 — A REMOVE matches a girl ignoring capitals, accents and punctuation; a misspelled name is corrected by REMOVE + ADD, never renamed

- The Club Roster Form's REMOVE first looks for the typed name as enrolled (capitals and spacing ignored), as before. A name not spelled so on file is then compared with the club's girls, any status, by letters and digits only, of any script, with capitals, accents, spaces and punctuation ignored (`foldLetters_`: `Mary Jo` and `Mary-Jo`, `JR` and `J.R.`). Exactly one girl spelled so, and active: she is removed (counted in the Audit summary as "matched ignoring accents and punctuation"; the mentor's e-mail shows the name as typed). Only inactive girls spelled so: "already removed", no ReviewQueue item. Every letter counts, so a typo, a dropped letter (`Pea` for `Peña`) or a middle name left out never matches; a name that is only punctuation matches nobody.
- Still a "Removal did not match anyone" ReviewQueue item: a folded spelling shared by two or more girls of the club with an active one among them (sisters, or one girl twice); a second line of the same response that reaches a girl another line already removes (she is removed once, by the line spelled as enrolled if there is one); a girl the same response also ADDs under her enrolled spelling (she stays); and every near spelling or unknown name.
- A misspelled name on the Roster is corrected by the mentor through the Club Roster Form: REMOVE the wrong spelling and ADD the right one. There is no rename path, and the old and new spellings folding equal does not make the pair "kept both" (ticket #112; `appsscript/Normalize.gs`, `appsscript/RosterOps.gs` `planModification_`; RUNBOOK "Working the ReviewQueue", "Removal did not match anyone").
- **Why:** Ryan, 2026-10-22: no rename, the mentor fixes a name with REMOVE + ADD (an ADD mints a new girl; the old id stays on the removed row). Of the 62 open "Removal did not match anyone" items, 31 were girls already removed and 7 an active girl with an accent or punctuation changed; folding settles those two groups without a person. Folding stops at letters and digits so that it cannot join two different girls, and anything with more than one candidate stays staff's call.
- **Rejected:** a rename (a new spelling on the same id); a fuzzy or "closest name" match that removes a girl (a typo or a sister's name would remove the wrong girl); folding an exact-spelling line and a fold line into one removal (two lines of one response are more often two girls than one typed twice); raising an item for an already-removed girl spelled so (folded equal).
- **Consequences:** the 31 + 7 kind of item no longer appears, and items raised before the Apps Script deploy of #112 stay open for staff; the rule is in `test/removal_match_test.js`, where REMOVE wrong + ADD right is a tested case. The Apps Script deploy is Ryan's step after landing.

### 2026-10-22 — A corrected re-submission adds its missing girls to the day's original batch; a different module or nobody new stays Duplicate

- A second batch for a club and date that already has a `Success` batch, with the same `Module__c`, is merged into the oldest `Success` batch of that club and date (the original): it adds only the girls missing from that date's rows - ticked now and without a row for that club and date, whoever made the rows - as `Attendance__c` rows of the original batch; never a row removed, never a girl counted twice. The original's `Girls_Present__c` moves to the new total (Ryan: "the count of that date's rows after the merge"). The correction's own batch is `Success` with `Status_Message__c` exactly `merged into <original batch id>` (no new picklist value), no count and no rows of its own (ticket #108; [plan](plans/2026-10-22-correction-merge.md); RUNBOOK "Attendance totals and partner-reported counts", A mentor's correction).
- A re-submission with a different module (a special event on a curriculum day, or the reverse) stays `Failed` "Duplicate": one session per club per day (2026-10-13). One that adds nobody stays `Failed` "Duplicate" exactly as before; so does one for a day whose `Success` batch has no rows of its own (a typed aggregate, a `Partner report` batch, a merged correction).
- This amends 2026-10-13, which rejected letting a second batch per club and day through: a second batch of the same session now goes through as a merge; the one-session-per-day rule itself stays.
- Three choices Ryan's answers leave open are built as the implementation's defaults, for Ryan to confirm before the deploy (the plan, "The change" 4 and Rollout step 3) - not decided here: (1) a merged row takes the ORIGINAL batch's session fields (date, module, `Module_Week__c`, `Module_Year__c`), not the correction's; (2) the original's `Girls_Present__c` = the count of the original batch's own `Attendance__c` rows after the merge (the field's meaning since 2026-10-07, what `tools/sf_girls_present.py check` compares) - Ryan's "that date's rows" read as the batch's own rows, so a hand-made row on no batch for a girl on that date blocks a second row for her but is not counted on the batch; (3) nothing is merged into a batch with no rows of its own (a typed aggregate, a merged correction) or whose `Creator__c` is `Partner report`: such a correction stays `Failed` "Duplicate". A different answer before the deploy changes the build, not the rule above.
- **Why:** Ryan, 2026-10-22 (ticket #108, answering the design question): the 2026-10-22 trace found 12 girls ticked only in a corrected re-submission and never added, because the processor failed every re-submission whole as "Duplicate" before reading a name - 83 such batches since 2026-09-07, arriving daily. Mentors correct a session by sending the form again; the correction must reach Salesforce without counting anyone twice.
- **Rejected:** keeping the refusal and only reporting the corrections to staff (option b: every correction would still need a hand back-fill, and the 83 batches show how often they come); a new picklist value such as `Merged` for the correction's status - no: it would touch the dashboard's and the reports' status filters and every tool that reads `Processing_Status__c`, and the `merged into <id>` message carries the same information; merging regardless of module (a special event and a curriculum session on one day are two sessions, which 2026-10-13 refuses).
- **Consequences:** `AttendanceBatchProcessor` changes (the Apex tests cover the merge, the refusals and the edge cases; the deploy waits for Ryan's go per the plan); `tools/sf_girls_present.py` leaves merged corrections out of `plan`, `set` and `check` by a condition on `Status_Message__c` in the WHERE only, never selected or printed; `tools/sf_backfill.py` knows the outcome `merged`; the RUNBOOK's template-test recipe ("Photos") ticks only girls already on that date's batch; the 12 girls of the Request are the next ticket's back-fill (their corrections are `Failed` already and are never re-processed).

### 2026-10-23 — Session week by day of the month, the submission's UTC day, no "big delay" flag

- A batch's session week is the week of the month of its `Attendance_Date__c` by day: 1-7 week 1, 8-14 week 2, 15-21 week 3, 22-28 week 4, 29-31 week 5, shown as `2026-10 week 2`; its session month is `2026-10`. This is the calendar week of the session date, not the curriculum "Session N" (`Module_Week__c`), which Salesforce already has (ticket #100; `glow/session_timing.py`).
- A batch's submission time is its `CreatedDate` when `Creator__c` is exactly `Jotform`, else none; the delay is the UTC day of the submission minus the session date, in whole days (negative when submitted before the session day, a date typo, BACKLOG 79). Nothing is flagged: no threshold, field, filter or highlight for "a big delay"; the reports show the delay and staff notice large ones.
- Salesforce computes the same with four formula fields on `Attendance_Batch__c` (`Submitted_At__c`, `Submission_Delay_Days__c`, `Session_Month__c`, `Session_Week__c`; the texts are `glow/session_timing.py`'s `SF_FORMULAS`, deployed by task #101); `tools/sf_session_timing.py check --vpn-off` compares them, read only.
- **Why:** Ryan, 2026-10-22, on the ticket: week (a), the week of the month by day ("week 2", "week 3", as GLOW staff say it); the submission day in UTC; "No 'big delay' threshold and no flag: nothing is flagged automatically; the delay in days is shown in the reports and staff notice large ones themselves." `CreatedDate` is the submission time because the native Jotform Salesforce V2 integration creates the batch when the form is submitted, so no integration mapping, processor (Apex) or form change is needed. The September back-fill batches (`Jotform back-fill <account id> <submission id(s)>`, created 2026-10-02) and the three partners' monthly batches (`Partner report`, `tools/sf_partner_monthly.py`) were created later by tools and get no submission time. Confirmed read only 2026-10-23, counts only: `Creator__c` is exactly `Jotform` (714 batches), `Jotform back-fill ...` (one value per back-fill batch, about 361) or `Partner report` (3).
- **Rejected:** Monday-start ISO weeks (`2026-W41`) and Sunday-start weeks (Salesforce's en_US report grouping); the org's zone (Los Angeles) or the club's region for the submission day (UTC is what the formula gives through `DATEVALUE(TEXT(...))` - `DATEVALUE` on the date/time itself is the running user's day (here the org's default, Los Angeles), the 2026-10-24 entry; it can count a late-evening submission in the Americas as the next day); a "big delay" threshold (the proposed default was 7 days) and its flag.
- **Consequences:** tasks #102 and #103 drop any threshold, filter or highlight they assumed; the back-fill and partner batches have a blank submission time and delay but a session month and week.

### 2026-10-23 — Roster-change reports point their sender to the Club Roster Form; girls "not on the form" count as one

- The sender of a problem report that reads as a roster change, when the reply box holds an address, is e-mailed once after the staff e-mail: the Club Roster Form's name and published link, how to use it (`Add or remove girls …`; a misspelled name is fixed by removing the wrong spelling and adding the right one), and that a report about something else needs nothing more. Never the report text, the typed club or partner. A report that chose the Club Roster Form gets it only when its "what happened" itself asks for the change: a mentor who was on that form and reports it broken is not told to use it. The ReviewQueue item stays staff's to enter or confirm (ticket #110; [plan](plans/2026-10-22-roster-change-reports-to-roster-form.md)).
- The classifier (`looksLikeRosterChange_`) also takes girls "not on the form / list / roster", "not in the portal", "missing from the form / list" (Spanish "no aparece(n) / no está(n) en la lista, el formulario, el portal") — a roster change said without a change word — on a positive sign that what is absent is girls: a people word, or a girl's name (two capitalised words, no digit) in the clause before the phrase, or in the clause before that when it holds only a person pronoun ("two girls came but they are not on the form") or no subject at all (Spanish "vinieron dos niñas pero no aparecen"); never when that clause holds a thing word ("Golden Wings Girls Club", "the number of girls", "the attendance of the girls" — the attendance and the register are things with the girls named in them), and never from a thing pronoun ("I marked all 14 girls present but it is not on the form" is the attendance lost, a bug report; PR #117 re-review).
- A problem report that says the form is not working — it does not load or submit, a blank page, an empty dropdown, an error message, in English or Spanish — becomes a ReviewQueue item of its own, "Form not working report", with its own heading in the Monday e-mail, through the roster-change item's path: queued before the staff e-mail, tagged `[#Feedback!N]`, the form she chose in detail and never her words; the staff e-mail carries a staff note; nothing goes to the sender. Precedence: a roster change wins — one item per report, the roster-change one, also when it says the form fails. The rule (`looksLikeFormProblem_`) is a form thing that fails — the form's own doing negated, an error, or a form thing in a failed state in the same clause — never a list of sentences (Ryan, 2026-10-22, from #67 Q3). The negated doing is the form's when its subject is a form thing, "it", the impersonal Spanish "se" or nothing at all ("the form did not submit", "it would not load", "no se envía", "No carga."); with a person as its subject (I, we, they, the girls, our club, the mentors; the elided Spanish first person) it is news or something not sent, not a failure ("half the girls did not show up", "we did not submit last week because there was no session", "I have not sent the photo yet", "no envié la asistencia") — except the reporter's own inability ("I could not submit", "no pude enviar": she tried and failed), which counts unless a "because / porque" clause gives the reason, when that clause decides on its own ("because there was no session": nothing; "because the page does not load": a failure) (PR #117 re-review).
- **Why:** mentors send roster changes through the problem form (20 open "Roster change sent as a problem report" items on 2026-10-22, the oldest 2026-09-18, nobody working them) and a 2026-10 report of girls who attended but were "not on the form" was not even queued. An auto-reply to a public form's sender is new: it is sent after the one step that throws and is retried, so a retry never sends it twice, and a failed send is one Audit row (addresses masked) that never fails the handler.
- **Rejected:** replying with the report's own text or the typed club (reports name girls; the address is whatever was typed); taking any subject the thing list does not name as people (the first cut, PR #117 review: "today's attendance is not on the form", "our mentor is not in the portal" and "my name is not on the list" became roster changes); letting any pronoun-only clause stand for the girls named before it (the second cut, PR #117 re-review: "I marked all 14 girls present but it is not on the form" and "the attendance of the girls is not on the form" became roster changes — a ReviewQueue item and a pointer e-mail to the mentor); queuing every negated form verb whoever its subject is (the second cut: "half the girls did not show up today" and "we did not submit last week because there was no session" became "Form not working report" items); the pointer for every report that chose the Club Roster Form (a mentor reporting that form broken was told to use it); an auto-reply to the sender of a form-not-working report (there is nothing she can do with one; staff answer her by Reply-To once they know what was wrong); a second item for a roster change that also says the form fails.
- **Consequences:** the trade-offs the tests encode (`test/forms_logic_test.js`, "which reports are roster changes"): a lone capitalised word ("Sunrise is not on the list") is read as a club, not a girl's first name — an accepted miss, the staff e-mail still goes and the Club Roster Form needs her full name anyway; a two-word club named only in the text with the club box blank ("Bright Stars is not on the form") reads as a girl's name — an accepted false alarm, staff resolve it "not a roster change" and the e-mail says a report about something else needs nothing more; a pronoun or a number alone ("they are not on the form") and a name or a people word after a thing word in its clause ("I marked attendance for the girls but they are not on the form") stay misses. Singular "name" stays out (2026-09). On the form-problem rule, a human "error" ("I made an error in a name"), a box the mentor left blank, a Spanish done-form with its subject left out or folded ("no envió la asistencia": she, or the form; "no envío" reads as "no envió") and a reason given without "because" ("I could not submit since there was no session") are accepted false alarms, resolved "not a form problem"; a failed state said of "it" alone ("it is blank"), a verb the lists do not name ("the form would not let me choose my club") and a thing the lists do not name with a people word before the negation ("the photo of the girls did not upload") are accepted misses, e-mail only as today. A mentor and staff both entering the change is safe: the Club Roster Form reports the second as already on the roster or already removed. The deploy waits for Ryan's go (the plan's Rollout); the rollback is the previous `appsscript/` deploy, nothing else to undo.

### 2026-10-23 — GLOW's keep list: 19 items in five dashboards and one table; every kept report by Partner and Month

- GLOW's keep list for the Monthly Report (`DHIS2__c`) has 19 items: 18 reports in five dashboards (GLOW Club Attendance, GLOW Club Implementation, GLOW Club Observations, GLOW Club Training, GLOW Club Reporting) and the "GLOW of the Month Stories" table. `glow/sf_keep_list.csv` maps each item and each of the five dashboards to the report or dashboard it is in the org today, by Id; item 12, "New mentors recruited", is new (#80) (ticket #70; RUNBOOK "Monthly Report dashboards in Salesforce").
- Every kept report and dashboard is by Partner and Month: the 18 reports of the five dashboards are grouped by partner and month, and item 19, the table, stays a tabular report, not grouped, with Partner and Month as its columns and filters (#79). Kept reports and dashboards keep their current names: in the file, `label_target` is `label_today`. Every report and dashboard not on the keep list goes to Decommissioned and is kept there, in case a pick changes later. The scope is the Monthly Report's three folders, "DHIS2 Reports", "DHIS2 Dashboards" and "Dhis2 Dashbords"; never the two Attendance folders or the "Jotform Attendance" dashboard, which epic #68 leaves untouched. Two reports in "Public Reports" that a dashboard of those folders uses today, "Pending Approvals monthly report" (`00ORP000006XSy92AG`) and "New Monthly Reports by account" (`00ORP000006V09x2AC`), are not in the file and sit outside those folders; Ryan decides on #72 whether they move.
- The test-record rule is a report filter on existing fields, applied to every kept report: `Account is not blank AND Account: Account Name does not contain "test"`. It excludes the Monthly Reports filed on a test account or on no account, and no real partner's.
- **Why:** Ryan, 2026-10-21: "This data should be displayed by the Partner and Month." Ryan, 2026-10-23, on the ticket: items 1-19 and dashboards D1-D5 "all as proposed". On the labels: "do NOT change the labels. Kept reports and dashboards keep their current names." On what is off the list: it goes to Decommissioned and is kept there, "in case we change a pick later". On test records: the proposed filter, which "drops no real partner". Item 18's "on time" is a later task, on hold (#119): no kept report computes it today.
- **Rejected:**
  - The label convention first proposed on the ticket: GLOW's measure as each report's label, without "M&P", and each dashboard renamed after its group. Ryan, 2026-10-23, kept the names as they are.
  - `Partner_Status__c` as the test-record rule: it is blank on four real partners with 23 Monthly Reports, as on the test accounts, so it would drop real partners.
  - A new "Test record" checkbox, or reusing `Obsolete_Record__c`: each needs a new field or record writes, a ticket of its own; the filter on the Account and its name needs neither.
  - The other candidates for each item and dashboard (the ticket's tables, 2026-10-23): copies, practice reports, and reports by Partner Manager rather than by partner.
- **Consequences:**
  - `tools/sf_report_folders.py` (#71) and the move plans of #72 and #73 read `glow/sf_keep_list.csv`: #72 moves to Decommissioned every report and dashboard in those three folders whose Id is not in it, and #73 moves the kept ones into their folders with the labels the file gives.
  - #75 to #79 apply the test-record filter to every kept report as they fix each dashboard by Partner and Month, and check each component against SOQL on `DHIS2__c`; #79 applies it to item 19, the table, too.
  - The filter matches a substring: a partner whose account name contains "test" (a "Contest" or "Protestant" partner, say) would drop out of every kept report, so a new partner's account name (its line in `glow/sf_partners.csv`) is checked against the filter when the partner is added (RUNBOOK "Monthly Report dashboards in Salesforce").
  - The epic's definition of done gave the five dashboards their groups' names; this decision amends it: the dashboards keep the names they have today, so D3 is "GLOW Club Training" and D4 is "Mentors", and the file is what ties each group to its dashboard.
  - #80 builds item 12; until then its row reads `new`, with GLOW's measure as its label. Item 18 maps to "Reports completed on time", which lists submission and modified dates; computing "on time" is #119, on hold.
  - The rule covers the Monthly Report reports only: the Attendance side (the "Jotform Attendance" dashboard and its folders) stays outside epic #68.
- 2026-10-23: the kept items go into one report folder, "GLOW Monthly Reports" (`ReportFolder` `GLOW_Monthly_Reports`), and one dashboard folder, "GLOW Monthly Dashboards" (`DashboardFolder` `GLOW_Monthly_Dashboards`), instead of per-category folders (Ryan, 2026-10-21, on #73). The five groups stay as the dashboards' categories, and item 19, the table, goes in the same report folder. Both folders get the same shares, since a dashboard's viewers need its reports' folder: the union of the shares of "DHIS2 Reports", "DHIS2 Dashboards" and "Dhis2 Dashbords", 7 entries (4 internal users View, 2 internal users Manage, 1 group Manage), internal users and groups only, never a guest, portal, community or partner share (RUNBOOK "The five dashboards and their folders"; [plan](plans/2026-10-23-sf-category-folders.md)).

### 2026-10-24 — The delay keeps the UTC day; the formula takes it through DATEVALUE(TEXT(...))

- Amends the 2026-10-23 entry (ticket #101): a Salesforce formula's `DATEVALUE(<date/time>)` converts in the running user's time zone (here the org's default, America/Los_Angeles), not UTC, so the first deploy's delay formula, `DATEVALUE(Submitted_At__c) - Attendance_Date__c`, gave the Los Angeles day and was one day short for every submission between 00:00 and about 07:00 UTC. The definition stands - the submission day is the UTC day of `CreatedDate` - and the formula takes it as `DATEVALUE(TEXT(Submitted_At__c))`: `TEXT()` of a date/time is the UTC timestamp `YYYY-MM-DD HH:MM:SSZ`, and `DATEVALUE` of that text is its UTC date. `Submission_Delay_Days__c` is `IF(ISBLANK(Submitted_At__c), NULL, DATEVALUE(TEXT(Submitted_At__c)) - Attendance_Date__c)` in `glow/session_timing.py SF_FORMULAS` and the plan's Build, one text, and the field is redeployed alone on Ryan's go ([plan](plans/2026-10-23-submission-timing.md), Result).
- **Why:** the first deploy (2026-10-24, `0AfRP000002i4Er0AI`) read back equal to the build, but `tools/sf_session_timing.py check` found `Submission_Delay_Days__c` differing on 153 of 1,123 batches, every one a submission before about 07:00 UTC and one day short - confirmed on BATCH-000405..409 (`CreatedDate` 04:52-05:06 UTC on 2026-10-02). Ryan, 2026-10-24: keep UTC; fix the formula. The Python side (`delay_days`) and the check already count the UTC day, which is the day the 2026-10-23 entry chose.
- **Rejected:** the org's zone (Los Angeles) for the submission day - keeping the first formula and moving the definition, `delay_days` and the check to the org's day.
- **Consequences:** `SF_FORMULAS`, the plan's Build table, the RUNBOOK's time-zone paragraph ("Submission timing in Salesforce") and the 2026-10-23 entry's "UTC is what a formula's `DATEVALUE` gives" are corrected; a formula that needs a date/time's UTC date takes it through `TEXT()`, never `DATEVALUE` on the field itself (`test/session_timing_test.py`, Definitions); the redeploy's check-only, deploy, read-back and the check to every differ count 0 go in the plan's Result; nothing reads the field yet (tasks #102 and #103).

### 2026-10-24 — The weekly not-submitting list leaves out the monthly partners and the U.S clubs by partner name; last week is LAST_WEEK

- `Clubs_Not_Submitting_Last_Week` (ticket #102) leaves out the clubs of the three partners that report monthly through Salesforce (Education and English for You, Tumaini La Maisha, Ng'aa Maskani; 38 clubs, off the forms since 2026-10-16) and the U.S clubs, by a locked filter on their partner account names (`PARENT.NAME` not equal to the three partners and the six U.S partner accounts, as `glow/sf_partners.csv` spells them). The filter is hand-kept: a new partner of that kind needs the report edited (RUNBOOK "Submission timing in Salesforce", The timing reports). `Submissions_by_Club_and_Week`, `Late_Submissions_Last_Month` and `Submission_Delay_by_Partner_by_Month` carry no such filter.
- "Not submitting last week" is no batch of any status whose session date (`Attendance_Date__c`) is in last week, Sunday to Saturday: Salesforce's `LAST_WEEK` in the report's cross filter and in its SOQL check. `LAST_WEEK` follows the locale of the user who runs it: Sunday to Saturday for en_US viewers and on the dashboard, which runs as Ryan. No `In_Last_Week__c` formula field is added to `glow/session_timing.py SF_FORMULAS` or deployed.
- `Late_Submissions_Last_Month` lists every live Jotform batch (`Creator__c` `Jotform`, `Processing_Status__c` `Success`) of last month with its delay, with no cut-off, grouped by partner (the ticket's outline), the largest delay first only within each partner's group: the month's largest delay heads its partner's group, which need not be the first. That was the outline's reading of Ryan's "largest first"; Ryan confirmed it on the ticket on 2026-10-26 (grouped by partner, largest first within each partner; the plan's Task #102 Rollout step 1). If it is ever changed to one list across partners, the report becomes Tabular (no grouping, the partner a column, sorted by the delay, descending).
- **Why:** Ryan, 2026-10-24, on the ticket: (1) leave those clubs out of the weekly list by a filter on their partner account names, stating that a new partner of that kind needs a report edit; the matrix is unaffected; (2) the session date in last week, Sunday-Saturday (`LAST_WEEK`), no new field; the late report every live Jotform batch of last month with its delay, largest first, no cut-off. He took the recommended option: those clubs never have a batch in a week, so the list would carry them, about a quarter of it, every week.
- **Rejected:** keeping them in the list, as the 14-day and since-1-September lists do (DECISIONS 2026-10-06: non-reporting clubs excluded at the source, not by a Salesforce-side marker - still true of those two lists); a marker field on the Account; "not submitting" by the day a submission was sent, or by the week of the month (`Session_Week__c`), which would need the `In_Last_Week__c` formula and another deploy; a delay threshold (DECISIONS 2026-10-23).
- **Consequences:** a partner marked `no` in the Partners tab's `jotform` column, or a new U.S partner, is added to the report's filter by hand (fresh retrieve, check-only, Ryan's go, deploy; RUNBOOK "Clubs that do not use Jotform" says so too); a renamed partner account drops out of the filter and its clubs show again. The matrix's columns are the week of the month while its window and the weekly list use Sunday-to-Saturday weeks, so its first and last columns can be partial weeks. The build and the live steps are in the plan ([plan](plans/2026-10-23-submission-timing.md), "Task #102: the timing reports").

### 2026-10-24 — The Monthly Report dashboards' period is the last 12 months, through DHIS2__c.Period__c

- The default period of the Monthly Report dashboards (epic #68) is the last 12 months, not a fixed year (Ryan, 2026-10-23, on #74). It is built as `DHIS2__c.Period__c`, a Date formula (the first day of the report's month) from `Year__c` and `Month__c`, in the `Dhis2` report type (ticket #128; [plan](plans/2026-10-24-dhis2-period-date.md); RUNBOOK "Monthly Report dashboards in Salesforce").
- The report recipe: the field filter `Period__c equals LAST_N_MONTHS:12` and the standard date filter's column set to `Period__c`, range All Time. The window leaves out the current, incomplete month.
- **Why:** every kept report filters on a fixed year (`Year__c equals 2025`, mostly), so the dashboards went stale. `Month__c` is a picklist of month names and `Year__c` a number, so no report could filter on a date. `Month__c` is a restricted picklist of the 12 month names, so a date comes straight from `Year__c` and `Month__c`, and a Date field lets a report use the relative `LAST_N_MONTHS:12`.
- **Rejected:** keeping a fixed year (`Year__c equals <year>`): it is what went stale, and every kept report would need a new filter each January; Lightning's standard date filter on an existing field, which offers no last-12-months duration; the outline's formula on `YearMonth__c`, which failed the check-only deploy (18,865 characters compiled, over the 15,000 limit: `YearMonth__c` is itself a large formula).
- **Consequences:** #75 to #79 apply the recipe to each kept report. A record with no `Year__c` (6 of 1,051) has a blank `Period__c` and falls outside the window. A rollback of the field waits until no report filters on it.

### 2026-10-24 — The Monthly Report dashboards' only filter is Partner Manager

- The five Monthly Report dashboards (GLOW Club Attendance, GLOW Club Implementation, GLOW Club Observations, GLOW Club Training, GLOW Club Reporting; tickets #75 to #79) have one dashboard filter, Partner Manager, on `DHIS2__c$Account__c.Assigned_Partner_Manager__c`: each manager picks their own name and sees their partners. No dashboard has a Partner filter or a Month filter. The reports stay grouped by Partner (`Account__c`), then the month (`Period__c`), with the last-12-months period and the test-record rule; the table, item 19, keeps its Partner and Month filters as report filters a viewer can change (RUNBOOK "Monthly Report dashboards in Salesforce").
- On GLOW Club Reporting (#79) the filter offers 7 managers: the 6 it offered plus the one active manager it lacked (7 partners, 69 Monthly Reports in the last 12 months on 2026-10-24), added on Ryan's word (2026-10-25, on #79: "Add the missing active manager to the Partner Manager filter."). The eighth manager with Monthly Reports in the window, inactive, with one partner, is left out by a Ruling made in the build, not by Ryan: he can reverse it, and it is no rule for #75 to #78 until he confirms it.
- **Why:** Ryan, 2026-10-24, on #75-#79: "NO Partner filter on any dashboard. The only dashboard filter is Partner Manager (each manager sees their associated partners)." The tickets' outline asked for a Partner and a Month filter; 58 partners have Monthly Reports in the window, over Salesforce's 50 values a filter, and the managers are how GLOW staff divide the partners.
- **Rejected:** a Partner filter split in two (Partner A-K / L-Z, #76's first draft); a Month filter on the dashboards (the components already show each month as a row or a group). Leaving out the inactive manager is not among them: it is the #79 build's ruling, above.
- **Consequences:** this amends the outline of #75 to #79 and the epic's "by Partner and Month", which the groupings carry, not the filters. A manager added to `Assigned_Partner_Manager__c` later is added to each dashboard's filter by a deploy of its own; a manager's name stays out of the repo and the tickets (the builds in `data/` carry it).

### 2026-10-25 — The session notes: one optional field after the rosters, translated on every form; in both e-mails (2026-10-26)

- Every attendance form gets one optional textarea named `sessionNotes`, labelled "Additional information about this session (optional)", with no sub-label and a limit of 1,000 characters (`entryLimit` `Letters-1000`). It is never required or hidden, sits after the last roster and above the links and Submit, and has no rule: the sync generates none and leaves the field alone (ticket #104 built it; ticket #105 put it on the template and the four regional forms on 2026-10-26, [plan](plans/2026-10-25-session-notes.md)). These are Ryan's answers on #104 (2026-10-22: the label, no sub-label, 1,000 characters; 2026-10-23: when no order is free, the tail moves down one to make room, option A).
- The label is translated in every form language: the ten of the 2026-08 pass, Odia, Hindi and Persian (Hindi and Persian reach the Asia form only), written by us and not native-reviewed.
- The e-mails, decided per e-mail by Ryan on 2026-10-26, after the rollout read them (his 2026-10-23 note on #105: mentors' notes can name girls): the notes go in both. The staff notification e-mail ("Notification 1", to GLOW's fixed staff address) carries them, and so does the mentor's confirmation (the autoresponder, to the address she typed).
- Both bodies are custom and list fixed fields, and neither had `{sessionNotes}` (read in the template's builder, 2026-10-26), so Jotform does not add the field to them. Ryan adds `{sessionNotes}` to both bodies on each of the five forms (ten bodies) by hand in the builder, ticket #148, after #105 lands; until then the notes are in Jotform's submissions only.
- **Why:** GLOW staff asked at their meeting (epic #93, Ryan 2026-10-22) for a place where a mentor can add what the attendance does not say; optional free text costs a mentor nothing when she has nothing to add, and its place after the rosters means she meets it once her girls are ticked, above Submit. No rule: the field never needs to hide, and the sync rewrites every rule on each run, so a hand-made one would not last. The staff e-mail: staff are the readers of the notes, and it goes to GLOW's own address, not a mentor's; the mentor's confirmation goes to the address she typed and gives her own words back to her. Translated, because the forms are multilingual (the ticket's request).
- **Rejected:** a sub-label (Ryan, 2026-10-22: the label only); a required field (the request is an optional one); option B on #104, a separate tail move to open a free order before the tool runs (Ryan chose A, the tool makes room itself); the label in English only until a later translation pass (the RUNBOOK's interim before #105); a Salesforce field for the notes now (the epic's "in Salesforce if GLOW wants it there" is a later ask); the mentor's confirmation left without the notes (the plan's proposal; Ryan chose both e-mails, 2026-10-26).
- **Consequences:** `glow/layout.py` `NOTES_EXPECTED` is `True`, so `form_status` reports a form without the field NOT CLEAN and the runner's verify never says in-sync for it: #105 lands only after the rollout, done 2026-10-26 with all five forms CLEAN. The translations are in `tools/translations_additions.json` and the Odia, Hindi and Persian files, posted per form right after the field. The RUNBOOK "Session notes on the attendance forms" carries the procedure; the Salesforce integration's mapping is unchanged, so the notes stay in Jotform and, once #148 is done, in both e-mails.

### 2026-10-26 — The session notes reach Salesforce, every user reads them; a DISABLED form needs no mapping

- A mentor's session note (the optional `sessionNotes` question, task #105) reaches Salesforce as `Attendance_Batch__c.Session_Notes__c`, a Long Text Area of 32,768 characters, mapped from each live form's own `sessionNotes` question in the native integration. Every Salesforce user may read it, so it can appear in reports: System Administrator reads and edits it (the integration's user) and `Attendance_Report_Viewer` reads it (ticket #106; [plan](plans/2026-10-26-session-notes-salesforce.md); RUNBOOK "Session notes in Salesforce").
- The length rule: the field is never shorter than what the form lets a mentor type (1,000 characters today), because Salesforce refuses an insert whose text is too long and the whole batch would be lost. A longer limit on the form needs the field checked first.
- The U.S form is DISABLED and is not mapped while it stays so; `tools/integration_status.py` requires the mapping on every live form except one whose `status` property is exactly `DISABLED` - any other value (`ENABLED`, none, `DELETED`, another spelling) is an enabled form's. A mapping a DISABLED form does carry is checked as on any form. Re-enabling the U.S form means mapping q446 before or with it.
- **Why:** Ryan, 2026-10-26, on the ticket: yes, the notes reach Salesforce; "Every Salesforce user may read the field" (girls' names inside Salesforce are fine, 2026-10-06; never in the repo, logs or tickets). On the U.S form, when asked whether to map it: "Skip U.S: it is disabled" - nobody submits on it (DECISIONS 2026-10-06). Only the exact status excuses a form so that an unknown or mistyped state never hides a live form whose notes would be lost.
- **Rejected:** notes kept out of Salesforce (in Jotform only); notes readable by administrators only (Ryan: every user); mapping the disabled U.S form now (Ryan: skip it); excusing the U.S form by its id rather than its status (re-enabled, it would still be excused); treating any status but `ENABLED` as disabled (an unknown state would excuse a form).
- **Consequences:** `NOTES_MAPPING_WANTED` is committed True in `tools/integration_status.py`; the U.S form's re-enabling (RUNBOOK "Disabling a regional form") includes the mapping; the processor does not read the field; a count of notes is read and counted locally, never printed, since a note may name girls. Rollback: unmap in the builder and set the switch False; the field may stay.
