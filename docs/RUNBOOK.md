# Runbook

Every operational procedure, in one place, each with its dry-run and its
apply form. Everything here talks to LIVE systems (the four regional Jotform
attendance forms, the master enrollment Google Sheet, the Apps Script bound to
it, and through the forms, Salesforce). The forms and the sheet went live on
2026-09-01.

## The forms

| Region | Form id | Mentor link |
|---|---|---|
| Africa | `262382821971058` | https://form.jotform.com/262382821971058 |
| Asia | `262383129464057` | https://form.jotform.com/262383129464057 |
| Latin America | `262383455778067` | https://form.jotform.com/262383455778067 |
| U.S | `262382706852058` | https://form.jotform.com/262382706852058 |
| Template (every logic change lands here first) | `262352490535154` | not for mentors |

The five pre-launch forms are retitled "(defunct)" and still enabled until
they are switched off (backlog item 1). The same table lives in
`tools/auto_sync.py` (`REGIONAL_FORMS`), `tools/form_status.py`,
`backup_forms.py` and `appsscript/Config.gs`; `test/python_test.py` fails if
they drift apart.

## Credentials

- **Jotform API key** — `JOTFORM_API_KEY` in the environment. Put it in `.env`
  (`cp .env.example .env`, `chmod 600 .env`) and load with
  `set -a; source .env; set +a`. Never type it on a command line inside Claude
  Code: command lines end up in `.claude/settings.local.json` and in
  transcripts (that happened once; the key was rotated). A read-only key is
  enough for `form_status.py`, `backup_forms.py` and every dry run.
- **Google Sheet** — service account key at `credentials/service-account.json`
  (or `GLOW_SA_KEY`), sheet id in `credentials/config.json` (or
  `GLOW_SHEET_ID`). Setup: [SHEETS-ACCESS.md](SHEETS-ACCESS.md).
- **Apps Script** — Script Properties (File → Project Settings): `FORM_ROSTER_ID`,
  `FORM_FEEDBACK_ID`, `STAFF_NOTIFY_EMAIL`, and for the automatic sync
  `SYNC_DISPATCH_REPO`, `SYNC_DISPATCH_TOKEN`.
- **GitHub Actions** (automatic sync) — repository secrets `JOTFORM_API_KEY`,
  `GLOW_SA_JSON` (the whole service-account file), `GLOW_SHEET_ID`; repository
  variable `AUTO_SYNC_APPLY` (`0` = dry runs only, `1` = writes).

## The live gate (Claude Code)

`.claude/hooks/live_gate.sh` blocks any command Claude runs that contains
`--apply`, `--prune`, `clasp push`, `clasp:push` or `sheets_client.py import`,
unless `GLOW_LIVE_OK=1` was exported in the shell **before** Claude Code was
started. A command that sets `GLOW_LIVE_OK` itself is always blocked. Every
decision is logged to `.claude/live_gate.log`. To let Claude write to a live
system: read the dry run, check the backup exists, then either run the command
yourself or restart Claude Code with the variable exported. Running commands
yourself in a terminal is never affected.

## Keeping the forms in step with the Roster (the manual loop)

The automatic sync (below) does this on every roster change and every
morning. By hand, per region:

```bash
python3 tools/sheets_client.py export Roster data/roster_<date>.csv        # 1. export
python3 tools/form_status.py --roster data/roster_<date>.csv               # 2. what differs? (read-only)
python3 backup_forms.py --form 262382821971058                             # 3. snapshot the form
python3 sync_attendance_form.py data/roster_<date>.csv --roster \
        --region Africa --form 262382821971058                             # 4. dry run
python3 sync_attendance_form.py data/roster_<date>.csv --roster \
        --region Africa --form 262382821971058 --apply                     # 5. apply
python3 tools/form_status.py --form 262382821971058 --roster data/roster_<date>.csv   # 6. verify: CLEAN
```

Or all four regions in one go, with the same guards the workflow uses:

```bash
python3 tools/auto_sync.py             # dry run, every region, nothing written anywhere
python3 tools/auto_sync.py --apply     # apply within the bands
# --synclog additionally records the run in the sheet's SyncLog (the workflow always passes it)
```

What to know:

- `form_status.py` without `--roster` compares against the stale offline
  build `data/roster_build/Roster.csv` — always pass the fresh export.
- The sync rewrites every condition on every run (`REPLACE conditions` is
  always in the plan); "changed" means a `CREATE`, `UPDATE` or `DELETE` line.
- Never `--prune` a live form. It deletes questions and is for fresh clones
  only; the sync refuses it on any form with submissions.
- Active roster rows with a **blank region** reach no form and no tool warns
  except `auto_sync.py` (ATTENTION) and the sheet's ReviewQueue. Fill in the
  Partners tab, then **GLOW → Refresh regions from the Partners tab**. Since
  2026-09 NEW partners choose a region on the Club Roster Form itself; a blank
  region can still come from older rows, a cleared Partners cell, or a known
  partner whose Partners row has no region (the picker is only shown to
  organizations not yet in the partner list).
- Region spelling must be exactly `Africa`, `Asia`, `Latin America`, `U.S`.

## Renaming a club

A club is keyed by its name in the Roster, ClubRegistry and SF Pending tabs
and by its roster question's label on the region's form and the template.
Never rename by editing the sheet alone: the next sync would CREATE a second
question and leave the old one orphaned in the Club picker. Rename in place,
then let the sync rewrite the picker options and the rules:

```bash
python3 tools/rename_club.py --partner "<partner>" --old "<current name>" --new "<new name>"   # dry run
python3 tools/rename_club.py --partner "<partner>" --old "<current name>" --new "<new name>" --apply
python3 tools/sheets_client.py export Roster data/roster_<date>.csv
python3 sync_attendance_form.py data/roster_<date>.csv --roster --region <region> --form <id>   # then --apply
python3 sync_attendance_form.py data/roster_<date>.csv --roster --form 262352490535154         # template, same
python3 tools/form_status.py --form <id> --roster data/roster_<date>.csv                        # CLEAN
```

The club keeps its `club_code`, so the girls' ids do not change (`Ids.gs`).
`--apply` saves the tabs under `data/rename_club/<stamp>/` and snapshots the
forms first; the rollback is those CSVs and `restore_conditions.py`. Then, in
the sheet, **GLOW → Google Forms → Update form dropdowns from the Roster** so
the Modification form offers the new name (it also refreshes on the next
submission). Attendance already submitted under the old name keeps it.

## Moving a club to another partner (a mistyped partner)

The old enrollment form took the partner's name as free text, so a club can
sit under a misspelled partner of its own (2026-09-24: Club Glow Traslasierra
under `ion bu` instead of Fundación Kaleidos,
[plans/2026-09-24-move-club-partner.md](plans/2026-09-24-move-club-partner.md)).
The attendance form does not notice, because it keys a club by its label. The
Club Roster Form, though, lists the club in the typo's own section, so the
partner cannot find it to add or remove girls. Move it in place:

```bash
python3 tools/rename_club.py --partner "<typo>" --club "<club>" --new-partner "<partner>"           # dry run
python3 tools/rename_club.py --partner "<typo>" --club "<club>" --new-partner "<partner>" --apply
```

The dry run can take `--sheet-only`; the `--apply` cannot, because it first
reads the region's form and the template (`JOTFORM_API_KEY`) to make sure no
rule shows the club only for a typed Partner.

Then, in the sheet, **straight away**: **GLOW → Google Forms → Update form
dropdowns from the Roster**. A direct sheet write triggers nothing. Until
the refresh, a change sent through the typo's section is skipped as "club not
on file": it is never retried ("Process any missed form responses" treats it
as done), and the mentor gets no confirmation. So afterwards, look in the
ReviewQueue for "Roster change for a club not on file" under the typo, and
ask the partner to send any such change again. Preview the form (never submit
a test): Existing club → the partner should list the club. Then export the
Roster; `tools/auto_sync.py --region "<region>"` (dry run) should say
`in-sync`, and `form_status.py` should say `CLEAN`. A move without `--new`
writes nothing to Jotform, so a `CREATE` for the club means stop. Salesforce
is outside the tools: check that the club's Account is not filed under the
typo.

What the tool does and guards:

- It changes the partner cell of every Roster row of the club (any status),
  its one ClubRegistry row (the code, and so the girls' ids, stay) and its SF
  Pending rows, all in one batch. Roster and ClubRegistry must never disagree,
  because `Ids.gs` looks a code up by partner + club: a mismatch mints a
  second code on the next submission. A part-moved club looks like two
  same-named clubs to the sync, which then Partner-gates both roster questions.
  So never do this by hand with Find & Replace, and never sort the Roster
  (the attendance forms list each club's girls in Roster row order, and this
  tool and the form handlers address cells by row number).
- Just before it writes, it re-reads the tabs and stops, with nothing
  written, if the club gained a row or a planned row changed (a form
  submission in the meantime); run it again. Rows of the club that arrive
  during the write are moved too, in a second verified batch.
- It writes the partner exactly as the **Partners tab** spells it. `key_`
  folds neither accents nor Unicode form, so `Fundacion` would be a third
  partner. It refuses a target that is missing from the tab (and suggests the
  accented spelling), one in another region, a club whose name another
  partner's club shares, and a club whose show rule already tests the
  Partner box.
- When nothing else names the typo, it blanks the typo's Partners row and
  notes why, which takes the typo out of both partner lists on the Club Roster
  Form. No row is deleted; `--keep-old-partner` leaves it. The typo's section
  stays on the Google Form, unreachable. Leave it; if anyone removes it, they
  must remove the page break **and** its `Club (<typo>)` list together.
- Rollback: put the typo back into its Partners row (from
  `data/rename_club/<stamp>/Partners.csv`), run the tool the other way
  (`--partner "<partner>" --club "<club>" --new-partner "<typo>"`), and
  refresh the dropdowns.

While a club is missing from its partner's list, tell the partner **not** to
use "Enroll a NEW club": the Existing-club page's help text ("Not listed? Your
organization has no enrolled clubs yet — go back and choose …") points there,
and it would
enroll the club a second time with new ids and gate its roster behind the
Partner box. Until the move, they can reach the club through Existing club →
the typo's name.

The raw Enrollment Responses keep the typo (the tab is append-only), so a
rebuild from them brings it back — see the warning under "Roster rebuild and
upload".

## Automatic sync

**Path:** a roster change in the sheet (New Club / Roster Modification form,
a rebuild, or a region refresh) → `appsscript/Dispatch.gs` sends a
`repository_dispatch` event to GitHub → `.github/workflows/auto-sync.yml` →
`tools/auto_sync.py` exports the Roster tab and, per region, dry-runs the
sync, checks the safety bands, backs up, applies, verifies with
`form_status.py`, and appends a row to the sheet's **SyncLog** tab. The
workflow also runs every morning (the cron is UTC: 06:00 Chicago in summer,
05:00 in winter) as a backstop for missed
events and manual sheet edits, and can be started by hand from the Actions
tab ("Run workflow", optional region).

**Safety bands** (per region, per run; `--max-creates`, `--max-updates`):
at most 5 new clubs and 20 roster updates; never a delete; not when a roster
would be replaced by one sharing no names with the current one; not when the
export looks truncated (fewer than 1,000 active rows, or many clubs on the
form missing from the export). Outside the bands nothing is written, the
region is logged as `attention`, and `data/auto_sync/ATTENTION.md` (kept as
a workflow artifact) says what to do. The workflow fails visibly (GitHub
emails the repository owner) on `attention` (exit 2) and on any failure
(exit 1).

**SyncLog columns:** `when, trigger, region, mode, creates, updates, rules,
result, detail, run_url`. `mode` is `dry-run` or `apply`; `result` is one of
`in-sync`, `dry-run` (would apply), `applied`, `applied-with-problems`,
`applied-unverified`, `attention`, `failed`. The Audit tab additionally gets
a `syncRequested … → HTTP 204` row every time the sheet sends the event.

**Switches:**

- Repository variable `AUTO_SYNC_APPLY`: `0` = every run is a dry run (start
  here; read a day of SyncLog rows), `1` = runs apply within the bands.
- Script Properties `SYNC_DISPATCH_REPO` / `SYNC_DISPATCH_TOKEN` unset = the
  sheet sends nothing (the daily run still happens).
- Manual runs from the Actions tab apply only when both `AUTO_SYNC_APPLY=1`
  and the "apply" input is ticked.

**First-time setup** (once, by the sheet's owner):

1. Rotate the Jotform key; add the three secrets and the variable to the
   private GitHub repo (Settings → Secrets and variables → Actions).
2. Create a fine-grained personal access token limited to this repository
   with *Contents: read and write*; set `SYNC_DISPATCH_REPO=<owner>/<repo>`
   and `SYNC_DISPATCH_TOKEN=<token>` in the sheet's Script Properties.
3. `npm run clasp:push` at a quiet moment, **then immediately, in the same
   sitting**, open the sheet, run **GLOW → Set up tabs** (creates `SyncLog`)
   and accept the authorization prompt. The push adds the "connect to an
   external service" scope, and **until the trigger owner re-authorizes, the
   form-submit trigger fails hard** — submissions land in the response tabs
   but are NOT processed (no Roster/FormLog/Audit rows; only trigger-failure
   e-mails show it). After authorizing, run **GLOW → Google Forms → Process
   any missed form responses** to catch anything that arrived in between —
   read its preview first ("Missed form responses") — then **Request
   Jotform sync now** to test the notification.
4. Watch the Actions run (dry run) and the SyncLog row; after a clean day set
   `AUTO_SYNC_APPLY=1`.

**Rollback:** before every apply the runner snapshots the form and writes a
conditions-only file `backups/<form>/conditions-<stamp>.json` (that file —
no staff e-mails, no integration settings, no rosters — is what the workflow
keeps as an artifact for 30 days);
`python3 restore_conditions.py --form <id> --from conditions-<stamp>.json --apply`
puts the conditions back. Questions are never deleted by the runner. To stop
the automation: `AUTO_SYNC_APPLY=0` (or clear the two Script Properties).

## The Club picker (mentors choose their club instead of typing it)

Intent: [intent/2026-09-01-club-picker.md](intent/2026-09-01-club-picker.md).
A required **Club** dropdown in Jotform's searchable mode (type to filter,
on phones too) listing every club on the form; the roster rules key on it,
and a calculation copies the pick into the (now hidden) Club Name textbox,
question 5, which is what the Salesforce mapping reads — so `Account_Name__c`
still receives the plain club name. Added once per form; from then on every
sync run keeps its option list and properties in the shape `PICKER_PROPS`
defines (`UPDATE club picker (N clubs: options, subLabel…)` in the plan).
**Status:** rolled out to the template and all four regional forms on
2026-09-12 with leadership's approval (`plans/2026-09-12-picker-rollout.md`).
The wording follows the training guide — label **Club Name**, sublabel
"Select your Club Name to see your roster." — and lives in `PICKER_PROPS`:
change it there, never in the builder (the sync reverts hand edits). The same
day `tools/update_static_fields.py` renamed the mentor email field to
"Partner Coordinator Email" and opened the Group Photo question (one photo,
faces visible, 10 MB, HEIC accepted). Still to confirm in the browser: that
the searchable component lets a mentor pick only one club (Jotform ignores
`maxSelection` on dropdowns); if two can be picked, the sync must add a
guard rule.

```bash
python3 backup_forms.py --form 262352490535154
python3 sync_attendance_form.py data/roster_<date>.csv --roster --form 262352490535154 --club-picker            # dry run
python3 sync_attendance_form.py data/roster_<date>.csv --roster --form 262352490535154 --club-picker --apply    # add it
python3 tools/form_status.py --form 262352490535154 --roster data/roster_<date>.csv     # "club picker: q<id>", rules CLEAN
```

(The template takes no `--region`; a regional form takes its `--region`.)
Verify in the browser: pick a club → its names appear; pick another → they
swap; submit a test → the submission and Salesforce show the club name in
the Club Name field. Rollback: `restore_conditions.py` for the rules, and in
the builder delete the Club dropdown and un-hide Club Name (or
`question[hidden]=No`, `question[required]=Yes` on q5 via the API).

Translations for the picker strings and the static-field wording are in
`tools/translations_additions.json` (ten languages plus Odia for the newer
strings; written by us — have a native speaker glance at them, as with the
Odia set). The tool only posts strings that exist on a form, so run it AFTER
the picker is there: `sync … --club-picker --apply`, then
`tools/add_translations.py --form <id> --apply`. A gateway 504 on the POST
can hide a completed write: re-run the dry run, and "0 new" means it landed.
Club names (the picker's options and the roster labels) are deliberately
never translated — they display in English in every language.

## The partner list (club names two partners share)

Plan: [plans/2026-09-28-partner-box.md](plans/2026-09-28-partner-box.md).
When two partners each have a club of the same name ("Ruby", "Angels Club"…),
the Club picker lists the name once, and the form asks for the partner. Until
now that was the typed **Partner** box (q331), and the roster appeared only
when the typed text equalled the partner's full name as the Roster spells it,
so "HAFAI" for Health Aid For All Initiative showed nothing. `--partner-picker`
replaces the box with a **Partner** dropdown (field name `partnerPicker`). It
lists the partners whose club name is shared on that form, stays hidden until
such a name is picked, and is required once shown. It has the Module/Session
dropdowns' shape, so it is a plain list and only one partner can be chosen.
The gated rules test it and q331 is hidden. Question 5 (Salesforce) is
untouched, and the partner choice goes nowhere else. Added once per form;
from then on every run keeps its options and shape
(`UPDATE partner picker (N partners: …)`, which the runner applies like a Club
picker update). A form without it keeps the typed box and exactly today's
rules. **Status:** built 2026-09-28, not deployed. Today only Africa (8
partners, 10 rosters) and the template (9 partners, 11 rosters) have shared
names; on the others the flag refuses ("nothing to choose").

Order matters: the runner syncs from `main`, and the old code would put the
rules back on the hidden box. So **merge first**, and keep
`AUTO_SYNC_APPLY=0` for the window.

```bash
python3 backup_forms.py --form 262352490535154
python3 sync_attendance_form.py data/roster_<date>.csv --roster --form 262352490535154 --partner-picker            # dry run
python3 sync_attendance_form.py data/roster_<date>.csv --roster --form 262352490535154 --partner-picker --apply    # add it
python3 tools/form_status.py --form 262352490535154 --roster data/roster_<date>.csv     # "partner picker: q<id>", rules CLEAN
python3 tools/add_translations.py --audit --form 262352490535154                       # "Partner" already translated: nothing new
```

The dry run prints `conditions: K kept, N new, D dropped`. Expected: template
360 / 16 / 16, and Africa (`--region Africa --form 262382821971058`)
239 / 15 / 15. The rule count does not change (376 and 254), and there are no
roster creates or updates beyond what the same command prints without the
flag.

Check in the browser (template first, then Africa):

1. Pick a unique club: no Partner question.
2. Pick "Ruby": Partner appears, required, listing the partners.
3. Choose Health Aid For All Initiative: its roster appears. Choose Binti
   Network instead: the rosters swap.
4. Switch the language (e.g. Kiswahili): "Partner" is translated, the
   partner names stay English.
5. Submit a test on the template: the Club Name field (q5) says "Ruby".

Rollback, per form:

1. `restore_conditions.py --form <id> --from conditions-<stamp>.json --apply`
   puts the rules back on q331.
2. Un-hide q331 (`question[hidden]=No`).
3. Delete the Partner dropdown in the builder.
4. Revert the merge (otherwise the next run re-points the rules at the list,
   if it still exists).

Until it is deployed, a mentor of a shared-name club must type the partner's
full name exactly as the Club Roster Form lists it.

## Header logo

The logo above the form title is the `image` field (q13 on every form), and
`tools/update_static_fields.py` maintains it. **Jotform's API cannot upload an
asset** — `src` only ever points at a file that is already hosted — so the
file goes into the account through the builder once and its URL is passed to
every form:

1. Open any form in the builder, click the image element, upload
   `assets/global-catalyst-header.png` (410×206, i.e. 2× the displayed size so
   it stays sharp on phones), and copy the URL it gets
   (`https://www.jotform.com/uploads/<account>/form_files/<file>.png`).
2. Point all five forms at it (the dry run prints the current value first, and
   refuses a URL that is not a reachable image at least as large as the box):

```bash
python3 backup_forms.py                                        # snapshot everything first
python3 tools/update_static_fields.py --image-src <URL>        # dry run, template + 4 regionals
python3 tools/update_static_fields.py --image-src <URL> --apply
```

The display size lives in `IMAGE_PROPS` (205×103: the height of the banner it
replaced, the width from the logo's own proportions). Without `--image-src`
the image field is left alone, so the tool's other fields can be re-run
safely. Rollback: the `src`/`width`/`height` in
`backups/<id>/questions-<stamp>.json`, re-applied with the same flag, or
Jotform's Revision History. The image carries no translated text (q13 is in
`add_translations.py`'s `NEVER_SHOWN`), and the sync never touches it.

## Backup and restore (Jotform)

```bash
python3 backup_forms.py                       # every known form -> backups/<id>/{questions,properties}-<stamp>.json
python3 backup_forms.py --form <id>           # one form (2 API calls)
python3 restore_conditions.py --form <id>              # preview restoring the latest snapshot's conditions
python3 restore_conditions.py --form <id> --apply      # restore
```

Restores touch only the conditions; questions, emails and the Salesforce
integration are left alone. Jotform's own Revision History is the second
rollback path. `backups/` holds rosters and never enters git.

## Translations

```bash
python3 tools/add_translations.py --audit                 # which labels lack translations
python3 tools/add_translations.py                         # preview (uses tools/translations_additions.json)
python3 tools/add_translations.py --apply
python3 tools/add_language.py --code or --name Oriya --dict tools/translations_or.json          # preview
python3 tools/add_language.py --code or --name Oriya --dict tools/translations_or.json --apply
python3 tools/restore_translations.py --form <clone id> --check   # after a clone: is the switcher intact?
python3 tools/add_language.py --form 262383129464057 --code hi --name Hindi --dict tools/translations_hi.json     # Asia only (2026-09-20)
python3 tools/add_language.py --form 262383129464057 --code fa --name Persian --dict tools/translations_fa.json   # Asia only (2026-09-20)
python3 tools/switcher_flags.py --check-page             # which switcher languages have no built-in flag (public page, no key)
python3 tools/switcher_flags.py                          # preview the flag CSS block per form; --apply writes injectCSS
```

Jotform's switcher shows a nation flag per language from its own table; a
language outside it (Oriya) gets an empty slot. `tools/switcher_flags.py`
paints one through the form's `injectCSS` (Jotform's own India SVG for
Oriya, `tools/switcher_flags/or.svg`, as a base64 data URI — the public page
rewrites `http:` inside injected CSS, which breaks a percent-encoded SVG) —
add a code + SVG to `FLAGS` for any other flagless language, dry-run,
`--apply`, then `--check-page`. Hindi and
Persian are offered on the Asia form only; the other forms can get them with
the same two `add_language.py` commands minus `--form`.

Jotform's `POST /form/{id}/translations` replaces a language's whole
dictionary — the tools always GET, merge, then POST. A new English string
must also be written to `base` and `en` or its translations never apply
(details: `.claude/skills/jotform-api/SKILL.md`).

## Missed form responses

**GLOW → Google Forms → Process any missed form responses** runs the Club
Roster Form responses and problem reports that were never processed (a
trigger failed, e.g. between a scope-adding push and the re-authorization)
or that failed (FormLog `ERROR: …`). It changes nothing until you confirm:

1. One dialog per group lists what it would run — problem reports not yet
   sent to staff, then Club Roster Form responses not yet processed. Each
   line: sheet row · when it was sent · new club / roster change / problem
   report · the club (partner), or the form a report is about · the last
   error, for a retry. YES runs that group; NO skips it.
2. Club Roster Form responses **sent more than 7 days ago** get a dialog of
   their own. Answer NO unless you know why that response never ran: a
   handler applies a response to *today's* roster, so an old one can put
   back girls removed since it was sent — which is what the 2026-09-13 run
   did to Radiant Girls.
3. **Held** rows are listed and never run: FormLog already has that form +
   sheet row as processed, under a key that no longer matches the row.
   Something changed the row or its key — rows sorted or deleted in a
   response tab, a question title renamed (`Config.gs` `Q`), a Timestamp
   cell edited. Find out what first. To run one deliberately: in FormLog,
   find **every** row with that form and `sheet_row` whose `result` does not
   start with `ERROR:` (after a sort they record *another* response) and
   change only their `sheet_row` cell, e.g. `released 5 by <name> <date>`.
   Leave `response_key` and `result` alone, so what they record stays
   processed. The next run offers the held row as new; check the preview
   lists only that row before answering YES.
4. A failure you have **dealt with by hand** (the report was read, the
   change was entered another way) is offered again on every run until
   FormLog says otherwise: change the `result` of its FormLog row from
   `ERROR: …` to `resolved by hand by <name> <date>` — any result that does
   not start with `ERROR:` counts as done.

The run takes the document lock one row at a time (form submissions keep
flowing) and starts no row after 4 minutes (Apps Script stops any run at 6);
if it says rows were not started, run it again. The Audit tab records every
use: `cancelled at the preview (would have run …)`, `started: …`,
`finished: …; N left`. Problem reports first, then Club Roster Form
responses in row order.

**Never sort the response tabs** (Roster Form Responses, Feedback) — use a
filter view. FormLog knows a response by its form, the text of its Timestamp
cell to the millisecond, and its partner | club. Keys written before
2026-09-27 used the Timestamp's milliseconds, which move when the
spreadsheet's time zone changes (File → Settings) — the cause of the
2026-09-13 replay; they are still recognised under any zone
([plans/2026-09-27-formlog-key.md](plans/2026-09-27-formlog-key.md)).

**Rolling back `appsscript/`** to a commit before `7a175c4` brings back the
old menu item, which cannot read the new keys and would re-run everything
processed since the deploy, without a preview. Roll back no further than
`7a175c4` (`git checkout 7a175c4 -- appsscript && npm run clasp:push`); it
shows rows logged under the new keys as held.

## Working the ReviewQueue

The **ReviewQueue** tab holds every question the scripts could not decide.
**Owner: Ryan.** The Monday e-mail (08:00, to `STAFF_NOTIFY_EMAIL`) lists the
open items by issue, with their ReviewQueue row; work them that week.

- An item is open while **resolved** is empty. The e-mail's "new" means raised since the previous Monday e-mail. Close it with
  `resolved <yyyy-mm-dd> by <name>: <what was done>` — by reference (counts,
  `Roster Form Responses!41`), **never a girl's name**. Any text closes it and
  drops it from the e-mail; while you wait on a partner, leave it empty and
  keep notes in a cell note (Insert → Note).
- Never delete or sort rows (use filter views), here or in the Feedback and
  response tabs, and never type after the `[#…]` tag that ends **detail**: it
  is how the queue recognises a repeat.
- The Monday e-mail shows no girls' names, by design: names live only in the
  sheet. Work the queue in the sheet; never copy a detail cell into e-mail,
  chat, GitHub, a commit or a Claude prompt.
- Nothing closes an item for you — not a later submission, not "Process any
  missed form responses". Never fix one with **Rebuild roster from enrollment
  responses** (not after launch) or by typing in Roster cells.
- **Entering a change yourself:** Club Roster Form → "Add or remove girls in
  a club that is already enrolled" → partner → club → ADD / REMOVE, one
  submission per club. For the mentor e-mail use your own address (the
  confirmation echoes what you typed). REMOVE matches the enrolled spelling
  only (capitals and spacing are ignored; accents, punctuation and middle
  names are not): copy each name from the club's Roster rows.

| Issue | What to do |
|---|---|
| **Roster change sent as a problem report** | Read `Feedback!N` (the tag). Check the Roster and Audit `rosterChangeForm`: the partner may have sent it since. Enter it as above, or ask the partner to. Not a roster change after all: `resolved …: not a roster change`. A roster-change report whose staff e-mail lacks the "Staff note" line was missed by the keyword check: add a row by hand with this issue and `[#Feedback!N]` as the last text of detail (reports from before 2026-09-28 were added by `tools/backfill_feedback_review.py`). |
| **Removal did not match anyone** | Detail shows the typed name and up to 3 "Closest names on file" — other girls, so never send them to the mentor. REMOVE only a match that is clearly her; otherwise ask the mentor for the enrolled spelling (her confirmation said "our team will check"). |
| **Same name listed twice** | Only one girl is on the Roster. Ask the partner: two girls → ADD the second with a mark, e.g. `Jane Doe (B)` (the first keeps her ID); one girl typed twice → `resolved …: one girl, no change`. Never resubmit through "Enroll a NEW club". |
| **Partner says two girls share a name** | The partner answered Yes but no name repeats. Compare their note with the club's Roster rows: listed distinctly → resolved, no change; one missing → ADD her with a mark as above. |
| **Girls missing from the latest enrollment** | "Enroll a NEW club" was sent for a club already on file; the girls not in that list stay active. Ask the partner who has left and REMOVE them as above. If the new list was not this club's at all (Radiant Girls, 2026-08-31), REMOVE the rows it added as above: the names whose Roster `source` is that response row (Ryan's go). |
| **Roster change for a club not on file** | Nothing changed, the mentor got no confirmation, and it is never retried. Find the club under another name or partner ("Renaming a club", "Moving a club to another partner"), run **GLOW → Google Forms → Update form dropdowns from the Roster**, then enter the change from the response row (or ask the partner) and tell the mentor. A truly new club uses "Enroll a NEW club". |
| **Partner has no region** | Its girls reach no attendance form. A misspelled partner → "Moving a club to another partner". Otherwise set the Partners-tab region (`Africa`, `Asia`, `Latin America`, `U.S`), run **GLOW → Refresh regions from the Partners tab**, and check that the region's next SyncLog row says `applied`. |
| **Form response could not be processed** | Detail names the response row and the error. Fix the cause (a Script Property, a missing answer), then run **Process any missed form responses** ("Missed form responses"). A Club Roster Form response more than 7 days old: enter the change fresh instead and set its FormLog result to `resolved by hand by <name> <date>`. Close the item once FormLog has a row for that response (same form and `sheet_row`) whose result does not start with `ERROR:` — the retry's success, or the one you set by hand; the earlier `ERROR:` row stays, and **Process any missed form responses** no longer offers it. |

## Apps Script deploy

```bash
make gs                 # every .gs file parses (a broken file breaks every form handler)
npm run clasp:push      # gated: GLOW_LIVE_OK=1 for Claude, or run it yourself
```

Setup and the manual-paste fallback: [../appsscript/INSTALL.md](../appsscript/INSTALL.md).
**Scope rule:** adding a Google service to a `.gs` file (UrlFetchApp,
MailApp…) grows the project's OAuth scopes, and until the trigger owner
re-authorizes interactively, the installable triggers **fail hard** — form
submissions go unprocessed. So: push at a quiet moment, immediately run a
GLOW menu item and accept the prompt, then **Process any missed form
responses** and read its preview: it should list only responses that
arrived since the push, plus any earlier failure shown as `retry after
ERROR` ("Missed form responses" above). Rollback is a push of the previous
commit's `appsscript/` — never to before `7a175c4`.

## Roster rebuild and upload (offline path)

**Not after launch.** Since 2026-09-01 the Roster has moved on from the raw
enrollment responses. A rebuild from them, whether this offline path or
**GLOW → Rebuild roster from enrollment responses**, reactivates every girl
removed through the Club Roster Form whose name is still on her club's
original enrollment row (`planClub_`). It also re-creates any enrolled club
that was renamed or moved to another partner, under its old name or partner
and with new ids. Change single clubs with the tools above instead.

Used when the Roster tab has to be rebuilt from the raw enrollment responses
outside the sheet:

```bash
python3 tools/sheets_client.py export-all data/live_<date>
node tools/build_roster_offline.js data/enrollment_<date>.csv --existing data/live_<date>
python3 tools/upload_roster.py                      # preview
python3 tools/upload_roster.py --apply --replace    # write; previous tabs saved under data/roster_build/previous/
```

## Data-quality report

```bash
python3 tools/needs_attention.py data/enrollment_<date>.csv     # -> data/needs_attention_<date>.csv
```

## Building a new regional form (not maintenance)

`tools/clone_regional.py <region> <roster.csv> [--apply]` clones the
template, restores the languages, syncs one region with `--prune` and prints
the status. Only for a fresh form; never against a live one.

## Checks

```bash
make check      # everything offline: JS parity + logic tests, Python tests, .gs parse, secrets, links, fixture
make help       # the individual targets
```

Real-data parity runs automatically when `data/enrollment_2026-08-24.csv`
exists (`CSV=<path>` to point elsewhere, `PARITY_REAL=0` to skip).
