---
title: The intake checker for club names two partners share (Part 2 of the same-name plan)
author: Claude (workflow track wf6/same-name-intake, 2026-09-30)
status: done             # Part 2 of plans/2026-09-30-same-name-clubs.md, accepted by Ryan 2026-09-30 with that plan; merged (d238b43) and pushed to Apps Script 2026-09-30 10:38 UTC (Result at the end)
done: 2026-09-30
backlog: 49
created: 2026-09-30
intent: none — build notes for Part 2 of [plans/2026-09-30-same-name-clubs.md](2026-09-30-same-name-clubs.md), which stays the authority (its intent: docs/intent/2026-09-01-club-picker.md, amended 2026-09-30)
---

# Plan: the intake checker for club names two partners share (build notes)

Part 2 of [the same-name plan](2026-09-30-same-name-clubs.md): the Apps Script
side. Part 1 (Python, the forms) is another branch; an integrator merges the
two and adds the Python ↔ `Config.gs` parity test for `SF_NAME_SEP`. Examples
here use fictional names (Partner One, Partner Two, Partner Three; Stars,
Alpha Club).

## What it does
1. **Intake checker.** "Enroll a NEW club" with a club name that another
   partner's club already has — any Roster status, any region, compared with
   `key_` — is **held, not imported**: FormLog `HELD: club name already used
   by another partner — ReviewQueue [#…]`, one ReviewQueue item **Club name
   already used by another partner — ask for a different name**, the usual
   short "it is being checked" note to the mentor, nothing else written. The
   Monday e-mail lists the item like any other, right after the
   possible-duplicate holds.
2. **Release only under a free name.** A release of such a hold is refused
   (`ERROR: release refused: …`) until the response row's `Club name` cell
   has a name no other partner's club has. Staff either set that cell and
   release, or have the club sent again under the new name and resolve the
   item without `release`.
3. **The Monday e-mail's Salesforce lines** start with the exact account
   name: the club name, or `<club> - <partner>` when active clubs of two or
   more partners have that name (`Config.gs SF_NAME_SEP`, `RosterOps.gs
   sharedClubNames_` / `sfClubName_` — the rule of the forms' one-time
   `--same-name-switch`). A line with a shared name ends with a reminder to
   check the form's club list.

## Files that change
- `appsscript/Config.gs` — `SF_NAME_SEP = ' - '`.
- `appsscript/RosterOps.gs` — `newClubHoldReasons_` gains the kind
  `samename` (listed first); new `sharedClubNames_(rows)`,
  `sfLongName_(club, partner)`, `sfClubName_(club, partner, shared)`.
- `appsscript/FormHandlers.gs` — `SAME_NAME_ISSUE`, `HOLD_ISSUES`
  (`holdDecisions_` reads both hold issues), `REVIEW_ISSUES` (second),
  `HOLD_KINDS.samename`, `sameNameHoldStep_`, `RELEASE_STEPS` (what a
  release never skips: the typed organization, and now the name),
  `holdSummary_` (the FormLog text), `heldClubReviewItem_` (the new item),
  `sfPendingLines_(rows, shared)` and `sendSfPendingDigest` (name kept: the
  installed trigger calls it), two dialog texts of the missed-responses menu.
- `test/forms_logic_test.js` — the rule (`sharedClubNames_`, `sfClubName_`,
  the separator), the hold reasons, the handler held / released / refused,
  hold → ReviewQueue → menu plan, the Monday e-mail's lines; the old check
  "the same name under another partner: imported" now expects the hold.
- `docs/RUNBOOK.md` — "Working the ReviewQueue" (the new issue's row),
  "Missed form responses" (item 5, both rollback notes), "Apps Script
  deploy" (this push). `appsscript/INSTALL.md` and `docs/ARCHITECTURE.md`
  where they list these pieces (flow box, constants on both sides, parity
  bridges, known divergences).
- Not touched: every Python file, `test/python_test.py`, DECISIONS, BACKLOG,
  CLAUDE.md, the other RUNBOOK sections (Part 1's).

## The rule as built
- **Which names count.** `key_(club)` equal (capitals and spacing ignored;
  a plural, a typo or an added number is a different name — the
  close-name check of 2026-09-28 stays a same-partner check).
- **Which clubs count.** Every Roster row with a partner and a club, any
  status, any region, with a girl's name or not (Python's `roster_pairs`,
  which the sync's own check goes by). A partner the typed organization is
  *close to* ("not in this list" + a retyped partner) is not "another
  partner": that case stays the club + organization hold of 2026-09-28, so
  staff are not told to ask for a new name when it is the same partner,
  retyped.
- **Never an existing club with active girls.** A (partner, club) on file
  that has an active girl is not a new club: its own "Enroll a NEW club"
  runs as before (today's 7 same-name clubs included). An existing club's
  name never changes.
- **A club on file with no active girl is held** when another partner's
  club has its name (review fix, 2026-09-30): the reason reads "this club is
  on file with no active girl, and the club name is already used by …", the
  item and the refused release are those of any same-name hold. A retired
  club's roster is off the forms, so the sync would treat it as a club to
  create and refuse it; unheld, its girls went active on the Roster and
  reached no form, with nothing in the ReviewQueue. A retired club whose
  name nobody else has is reactivated as before.
- **Also held:** a new club whose name reads as a club on file followed by
  its partner (`Stars - Partner One` while Partner One has `Stars`) — the
  sync refuses a club-list entry equal to another club's entry (second
  review, nit).
- **One item per held response.** With other reasons too (the girls are
  active in one club, a close club name, a retyped organization) it is still
  the same-name issue; its text says first to rule out "that club, sent
  under the wrong partner", then to ask for a different name. FormLog says
  both: `HELD: club name already used by another partner; possible duplicate
  (names on file) — …`.
- **The e-mail's name** is worked out from the Roster when the e-mail is
  sent, never stored (a renamed club or partner cannot leave it stale):
  active rows that have a girl's name only (a club is active when it has an
  active girl, as `shared_club_names(active_only=True)`), status read as
  the Python reader reads it.

## What the push changes for staff
- A new club with a name in use no longer lands on the Roster. It shows up
  on the ReviewQueue and in the Monday e-mail under the new issue; the
  RUNBOOK row says what to do (same club → add its girls to the club on
  file; the club on file is under the wrong partner or has moved → move it,
  then `release` with the name unchanged; new club → ask for a different
  name, then edit the cell and `release`, or have it sent again).
- The same happens to "Enroll a NEW club" sent for the partner's own club
  that has no active girl left, when another partner's club has its name —
  today the two clubs retired on 2026-09-30, and no other.
- The "Process any missed form responses" dialogs mention the second kind
  of hold; a released same-name club runs only once its name is free.
- The Monday e-mail's "waiting to be created in Salesforce" section says
  that each line starts with the exact account name. For every club pending
  today the first item is the club name, as before (read-only proof below:
  36 pending, 0 with a long name).
- No new Google service, no re-authorisation, no menu item to run, no
  change to a tab's columns. The clubs that share a name today are not
  touched.

## Deviations and choices (not spelled out in the plan)
1. **Issue text.** The plan wrote "Club name already used by <partner>'s
   club — ask for a different name". An issue is a fixed literal (the Monday
   e-mail groups by it, a guard test ties it to the RUNBOOK), so the literal
   says "another partner" and the item's detail names the club and partner.
2. **Release refused until renamed** (item 2 above) — the plan says "held";
   a release under the old name would put on the Roster a club the sync then
   refuses to add to any form.
3. **Related partner excluded, long-name look-alike included** (the rule).
4. **The mentor's note is unchanged** — it names only what the mentor sent.
   It does not say the name is taken (decision below).
5. **"NAME SHARED …" on a Salesforce line.** Not in the plan. On a form the
   long or plain name is sticky and the sync refuses a new namesake, so once
   the forms are switched a *pending* club can only show a long name here if
   a namesake reached the Roster another way (a hand edit, a retired club
   sent again). The form then still sends the plain name, and an account
   created under the long one would get a stray twin at the club's first
   attendance. The line therefore prints the rule's name and tells staff to
   check the form's club list.
6. **`sharedClubNames_` reads status loosely** (`key_(status) === 'active'`,
   as `read_roster_csv`), while the rest of `RosterOps.gs` compares the cell
   strictly. Local to this function; nothing else changed.
7. **`SF_NAME_SEP` is a top-level `const`** in `Config.gs`. The
   ARCHITECTURE "Constants that exist on both sides" row is written as it
   will be true after the merge with Part 1; the parity test comes with the
   integration.

8. **A hold item restored by hand is matched loosely on its issue**
   (`issueKey_`: capitals, spacing and the kind of dash ignored). The issue
   literal has a long dash no keyboard types; the `[#…]` tag, the
   `(sent …)` time and the word `release` stay exact.
9. **The item's text has a third action**: the club on file is under the
   wrong partner, or has moved — move it (RUNBOOK "Moving a club to another
   partner"), then release with the name unchanged; the response then runs
   as that existing club.

## Known divergences (documented, not fixed — CLAUDE.md rule 10)
- `key_` drops invisible characters; `glow.text.key` keeps them. A club cell
  with a zero-width character inside is the same name for the intake check
  and the e-mail, and a different one for the Python sync. The intake errs
  toward holding; cells the form handlers write never hold such a character.
  Pinned by a test, listed in ARCHITECTURE (BACKLOG 28).
- The intake counts rows of any status; the e-mail's names follow active
  rows; a form's name is sticky. Deviation 5 covers the one case that
  matters.
- The intake holds a club on file with no active girl whose name another
  partner's club has, whether or not its roster is still on the form (Apps
  Script cannot see the form); the sync refuses only a roster it would have
  to create. The one false hold: a same-name club that merely lost every
  girl and re-enrolls. None today; RUNBOOK "Working the ReviewQueue" has
  Ryan's way out (one of its girls set active by hand, then a release).

## Not done here
- A club or partner name with `|` or `{…}` (the sync refuses such a
  club-list entry) is not checked at intake. None on file today (proof).
- The Club Roster Form's "Club name" help is unchanged (a wording migration
  is its own push and menu run).
- A club on file with only Roster rows that have **no girl's name** (none
  today; it takes a hand-typed row) counts for the name check only: it is
  not "the partner's own club on file", its name is not a close name, and
  its partner is not a partner on file — the 2026-09-28 checks are
  unchanged.

## Risks
- **A wrong hold** (a legitimate second club of another partner wanting the
  same name): by design — it costs one question to the partner. Nothing is
  lost; the response stays on its row.
- **Staff release without renaming:** refused, offered again, plus a "Form
  response could not be processed" item to close — a little noise. The same
  happens when the organization was added to the Partners tab but the name
  was left (tested).
- **Rollback of this push** to the code before it: same-name holds stay held
  (the older code lists them as "no ReviewQueue item for this row and time"
  and never imports them); new same-name clubs are imported again and the
  sync refuses them on the form side. RUNBOOK "Rolling back `appsscript/`", its paragraph "Same-name holds and a
  rollback below the same-name check". The floors of CLAUDE.md rule 11 are
  unchanged.
- **Order with Part 1.** Pushed before the forms are switched, the intake
  already refuses new namesakes (good) and the e-mail already prints long
  names for pending clubs that share a name — none today.
- **The Monday e-mail now reads the Roster** when a club is pending (one
  `getValues`, about 7,000 rows). A Roster that cannot be read fails the
  e-mail, as an unreadable ReviewQueue already does.

## Live steps (each needs Ryan's go; none was run here)
1. Merge (with Part 1, through the integration branch) and push `main`.
2. `make gs`, then `npm run clasp:push` at a quiet moment — a normal push,
   no re-authorisation. Open the sheet, GLOW menu → "Process any missed form
   responses": the preview should list only what arrived since the push.
3. Optional check on the live sheet: send "Enroll a NEW club" yourself with
   your own address, a partner from the list and a club name another partner
   has; expect FormLog `HELD: club name already used by another partner`, one
   ReviewQueue item with the new issue, the short note in your inbox, no
   Roster row. Resolve the item `resolved <date> by Ryan: test`.

## Decisions for Ryan
1. **Tell the mentor?** The held-club note could say "another club already
   uses this name — please reply with a different one", saving staff the
   first message. It would tell whoever typed an address into a public form
   that a club of that name exists. Built: the neutral note.
2. **A retired same-name club sent again by its own partner:** hold it for
   staff as well? Built first: not held. **Changed by the review
   (2026-09-30): held** — unheld, the club's girls went active on the
   Roster, no attendance form showed them (the sync refuses to create the
   club and raises ATTENTION on every run), and staff saw nothing in the
   ReviewQueue or the Monday e-mail. Still yours to decide: the alternative
   is to import it and only raise a ReviewQueue item, which brings back the
   duplicate retired on 2026-09-30 and leaves the runner failing until the
   club is renamed.
3. **`|` and `{…}` in a new club's name at intake:** hold, strip, or leave
   to the sync's refusal? Built: left to the sync.
4. **Issue text** as built (deviation 1) — change it before the push if you
   want other words; afterwards open items keep the old text.

## Review fixes (2026-09-30, second pass)
Five verified findings, each with a test that fails without its fix:
- **intake-ops-1 (important).** A retired same-name club sent again by its
  own partner passed the intake and was refused by the sync: now held (the
  rule above; decision 2).
- **intake-2.** A Roster row with no girl's name counted differently from
  Python: `sharedClubNames_` now ignores it (a club is active when it has
  an active girl), and the intake's "who has the name" now counts it (as
  `roster_pairs`). Both functions are new on this branch, so neither is a
  one-sided fix of deployed behaviour; 0 such rows on the live Roster.
- **intake-ops-2.** No staff action for "the club on file is under the
  wrong partner, or has moved": the item's text and the RUNBOOK row now
  give it (deviation 9); the path itself already worked and is now tested.
- **intake-ops-3.** A hold item restored by hand was matched on the exact
  issue literal, long dash included: matched loosely now (deviation 8).
- **intake-1.** The test "nothing pending: the Roster is not read" passed
  whatever the code did (a Roster with only its header is never read): it
  now has Roster rows, and a twin check shows the unreadable Roster does
  stop the e-mail when a club is pending.

Read-only re-run over a fresh Roster export after the fixes (scratch file,
deleted; counts, club and partner names only): 6,946 rows, 6,847 active, 0
rows with a partner and club but no girl's name; 364 clubs on file, 362
with an active girl; 3 names shared by active clubs, 7 long names. Each
club sending its own list with one new girl: **2 held** for their name —
the two clubs retired on 2026-09-30 — and none of the 362 with active
girls. A fictional new "Ruby" under a third partner: held, both Rubys
listed.

## Proof
`make check CSV=<the main checkout>/data/enrollment_2026-08-24.csv` on
`wf6/same-name-intake` (2026-09-30), the healthy lines:

```
real data (…/data/enrollment_2026-08-24.csv): parsed 328 clubs, 6210 girls
ALL CHECKS PASSED          (×3: parity, forms logic, dispatch)
py: 34 files parse, 20 scripts answer --help
Ran 221 tests … OK
gs: 10 files parse
secrets: clean (136 files scanned)
docs-links: ok (59 relative links resolve, 0 absolute paths)
fixtures: up to date
CHECK PASSED
```

Read-only, the same day, after the two duplicate clubs were retired: the
real `.gs` functions run in Node over a fresh export of the Roster and SF
Pending tabs (scratch files, deleted afterwards; counts, club and partner
names only were printed; nothing was written anywhere, no Jotform or
Salesforce call).
- Roster: 6,946 rows, 6,847 active; 364 clubs on file, 362 active.
- `sharedClubNames_`: 3 names shared by active clubs; `sfClubName_` gives 7
  long names, character for character the 7 of the plan's table.
- Any status: 5 names, 11 clubs — the set the intake check protects. Had
  each club on file arrived as a new club today, exactly those 11 would
  have been held for their name, none of the other 353.
- A fictional new club with one of the shared names under a third partner:
  held (`samename`), every club of that name listed. Each club that has the
  name and an active girl, sending its own list with one new girl: not held
  (since the review fixes the two retired clubs are: see above).
- No active club's own re-enrollment is held for its name (0 of 362). No
  club on file has a name that reads as another club's `<club> - <partner>`;
  no club or partner name contains `|`, `{` or `}`.
- SF Pending: 36 rows, all pending; with the new lines none starts with a
  long name and none carries "NAME SHARED", so the next Monday e-mail's
  Salesforce section differs from last week's only in its first sentence.
  Every pending club has active girls on the Roster.

## Result (2026-09-30, with Ryan's go)
- Before the push, a `clasp pull` into a scratch folder showed the deployed script equal to `a1dc5d7`
  (the 2026-09-28 deploy), so this push also carried the four changes merged on 2026-09-29 and never
  pushed: the duplicate-club hold (BACKLOG 11b), the replay guard (41), sheet-safe Club Roster Form
  text (44) and the one-time wording menu item (43). Ryan was asked and chose to push all of it.
- `make gs` (10 files parse), `npm run clasp:push` at 10:38 UTC: 11 files pushed. A second pull: all
  ten `.gs` files equal `main` (`8436cb4` is the last commit touching `appsscript/`). The scratch copies
  were deleted. No new Google service, no re-authorisation.
- Rollback: `git checkout 986a325 -- appsscript && npm run clasp:push` (the 2026-09-28 script plus the
  two-reply-column read; safe whether or not the wording migration has run), after dealing with held
  new clubs (RUNBOOK "Rolling back `appsscript/`" and "Apps Script deploy").
- Still Ryan's: GLOW → Google Forms → "Process any missed form responses" and read its preview (it
  should list only responses that arrived since 10:38 UTC, plus earlier `retry after ERROR` rows);
  the one-time wording menu item when he chooses.

## From the RUNBOOK (moved 2026-10-09)

What `docs/RUNBOOK.md` carried for this plan until its 2026-10-09 restructure (the procedure as run, or its history), word for word (links re-pointed to this folder); the RUNBOOK keeps a stub that links here.

### "Apps Script deploy": the same-name push

**The same-name push (2026-09-30, Part 2 of
[plans/2026-09-30-same-name-clubs.md](2026-09-30-same-name-clubs.md);
build notes: [plans/2026-09-30-same-name-intake.md](2026-09-30-same-name-intake.md))**
is a normal push: no new Google service, so no new scope and no
re-authorisation (`make check` guards the list of services). Nothing runs
at the push and no menu item is needed after it. From the next "Enroll a NEW
club" response on, a club name another partner's club has is held — also
when it is the partner's own club on file, once that has no active girl
("Working the ReviewQueue"); from the next Monday e-mail on, each "waiting
to be created in Salesforce" line starts with the exact account name — the
club name, or `<club> - <partner>` when another partner's active club has
the same name. That name is worked out from the Roster when the e-mail is
sent. On a form the long or plain name is sticky (a club keeps `<club> -
<partner>` after its namesake leaves, and keeps its plain name when a
namesake turns up later), so the form's club list is the authority: a line
with a shared name ends "NAME SHARED … use exactly that text" — look the
club up in its attendance form's club list before creating the account. An
account named otherwise than the form sends gets a stray twin in Salesforce
at the club's first attendance. To undo the push, push the
`appsscript/` that was deployed before it ("Same-name holds and a rollback
below the same-name check", above).
