---
title: The intake checker for club names two partners share (Part 2 of the same-name plan)
author: Claude (workflow track wf6/same-name-intake, 2026-09-30)
status: accepted         # Part 2 of plans/2026-09-30-same-name-clubs.md, accepted by Ryan 2026-09-30 with that plan; built on branch wf6/same-name-intake — not merged, not pushed to Apps Script (each needs Ryan's go)
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
  status, any region. A partner the typed organization is *close to*
  ("not in this list" + a retyped partner) is not "another partner": that
  case stays the club + organization hold of 2026-09-28, so staff are not
  told to ask for a new name when it is the same partner, retyped.
- **Never an existing club.** A (partner, club) already on file is not a new
  club: its own "Enroll a NEW club" runs as before (today's 7 same-name
  clubs included). An existing club's name never changes.
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
  active rows only, status read as the Python reader reads it.

## What the push changes for staff
- A new club with a name in use no longer lands on the Roster. It shows up
  on the ReviewQueue and in the Monday e-mail under the new issue; the
  RUNBOOK row says what to do (same club → add its girls to the club on
  file; new club → ask for a different name, then edit the cell and
  `release`, or have it sent again).
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

## Known divergences (documented, not fixed — CLAUDE.md rule 10)
- `key_` drops invisible characters; `glow.text.key` keeps them. A club cell
  with a zero-width character inside is the same name for the intake check
  and the e-mail, and a different one for the Python sync. The intake errs
  toward holding; cells the form handlers write never hold such a character.
  Pinned by a test, listed in ARCHITECTURE (BACKLOG 28).
- The intake counts rows of any status; the e-mail's names follow active
  rows; a form's name is sticky. Deviation 5 covers the one case that
  matters.

## Not done here
- A club or partner name with `|` or `{…}` (the sync refuses such a
  club-list entry) is not checked at intake. None on file today (proof).
- The Club Roster Form's "Club name" help is unchanged (a wording migration
  is its own push and menu run).
- A club on file with **no active girl** that is sent again by its own
  partner is reactivated, as today, even when another partner's club has
  its name (the two clubs retired on 2026-09-30 are such clubs). The sync
  then refuses to add it and raises ATTENTION (Part 1). Decision below.

## Risks
- **A wrong hold** (a legitimate second club of another partner wanting the
  same name): by design — it costs one question to the partner. Nothing is
  lost; the response stays on its row.
- **Staff release without renaming:** refused, offered again, plus a "Form
  response could not be processed" item to close — a little noise.
- **Rollback of this push** to the code before it: same-name holds stay held
  (the older code lists them as "no ReviewQueue item for this row and time"
  and never imports them); new same-name clubs are imported again and the
  sync refuses them on the form side. RUNBOOK "Same-name holds and a
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
2. **A retired same-name club sent again by its own partner** (see "Not done
   here"): hold it for staff as well? Built: not held (an existing club's
   name never changes).
3. **`|` and `{…}` in a new club's name at intake:** hold, strip, or leave
   to the sync's refusal? Built: left to the sync.
4. **Issue text** as built (deviation 1) — change it before the push if you
   want other words; afterwards open items keep the old text.

## Proof
See the end of this file once the branch is finished: `make check` and the
read-only run of the new functions over a fresh Roster export.
