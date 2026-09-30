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
- A `!` line saying Club Name (question 5) **changes** for an existing club
  is a change of its Salesforce Account name: `--apply` refuses it without
  `--q5-change-ok`. A `!` line saying a new club was **not added** means
  another partner's club has its name. Both: "Club names two partners
  share".
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
python3 sync_attendance_form.py data/roster_<date>.csv --roster --region <region> --form <id>   # dry run: the '!' line; then --apply --q5-change-ok
python3 sync_attendance_form.py data/roster_<date>.csv --roster --form 262352490535154         # template, same
python3 tools/form_status.py --form <id> --roster data/roster_<date>.csv                        # CLEAN
```

The club's name is what question 5 sends, so a rename changes the name
Salesforce looks its Account up by. The sync's dry run lists it (`! '<new
name>' (q…): Club Name (question 5, what Salesforce reads) changes from
'<old>' to '<new>'`), refuses `--apply` without `--q5-change-ok`, and the
runner never applies it (ATTENTION, region "not applied"). After the
Salesforce reconnect: **rename the club's Account to the new text first**,
then apply with the flag in the same sitting — otherwise the club's next
submission makes Salesforce create a second Account with new Contacts for
every girl. The new name may not be one another partner's club has. The
tool cannot rename one of the clubs that share a name ("Club names two
partners share": two questions carry the old name, and it refuses).

The one exception to "never the sheet alone": a **new club the sync did not
add** because its name was in use has no question on any form. The tool
finds a question by its text, and the question of that name is the other
partner's — so it refuses (a question named like the club that holds
another club's girls), and the club is renamed with `--sheet-only`:

```bash
python3 tools/rename_club.py --partner "<partner>" --old "<name in use>" --new "<new name>" --sheet-only           # dry run
python3 tools/rename_club.py --partner "<partner>" --old "<name in use>" --new "<new name>" --sheet-only --apply
```

The next sync run then creates its roster under the new name. No Salesforce
Account is renamed and no `--q5-change-ok` is needed: the club sent nothing
yet.

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
  clubs of one name to the sync: it keeps the club's question for one half
  (the roster shrinks to that half's girls, a change the automatic run
  applies) and does not add the other half (a new club whose name is in
  use: ATTENTION, "new club(s) NOT added"), so those girls are on no
  attendance form until the move is finished.
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
enroll the club a second time with new ids — and the second club would
reach no attendance form: the sync does not add a new club whose name
another partner's club (here the typo's) already has ("Club names two
partners share"). Until the move, they can reach the club through Existing
club → the typo's name.

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
form missing from the export); never a change of what an existing club
sends to question 5, its Salesforce Account name (a renamed club, a
respelled partner — "Club names two partners share"), which stops the
region even when nothing else is planned. Outside the bands nothing is
written, the region is logged as `attention`, and
`data/auto_sync/ATTENTION.md` (kept as a workflow artifact) says what to do.
Two more things raise ATTENTION without stopping a region: a new club that
was not added to its form because another partner's club has its name (the
rest of the region is applied as usual; the SyncLog `detail` says "N new
club(s) not added (name in use)"), and, once per run, any name that two
clubs of the regions synced send to question 5. Until a club that was not
added is renamed, every apply in its region reads `applied-with-problems`,
with a second ATTENTION ("applied, but the form still has problems"): the
verify step goes by club name, so its "still missing from the form: <club>"
line (the namesake is on another region's form) or "roster(s) still differ
from the sheet: <club>" line (the namesake is on this form) counts the club
that was not added. By itself that line does not say the existing club's
roster is out of date.

One thing reads `attention` where it used to read `in-sync`: **roster rules
that test a name the Club picker does not list** (a conditions backup
restored over newer picker entries, a hand apply that stopped between the
picker write and the rules write). Those clubs' rosters do not show and,
with the club guard, their mentors cannot submit. The sync's dry run says
so per roster (`! '<club>' (q…): its rule tests '<X>', which the Club picker
does not list …`) and plans only `REPLACE conditions`, which the runner does
not count as a change and never applies on its own: run the dry run and
`--apply` by hand. When the same region also has a roster change, the
runner's ordinary apply rewrites the rules and nothing more is needed.

The workflow fails visibly (GitHub emails the repository owner) on any
ATTENTION (exit 2) and on any failure (exit 1).

**SyncLog columns:** `when, trigger, region, mode, creates, updates, rules,
result, detail, run_url`. `when` is the run's start in the sheet's own time
zone (read from the sheet, like the Apps Script's timestamps). The cut-over:
rows written before commit d9b4f6b reached the runner on GitHub carry the
runner's America/Chicago time (one hour behind the sheet and the Audit tab;
before 2026-09-02, when the sheet was on UTC, five hours), and a Mac
`--synclog` run before then wrote the Mac's clock; the row's `run_url` gives
the true time. The log file and ATTENTION.md show the runner's clock with
its UTC offset. `mode` is
`dry-run` or `apply`; `result` is one of `in-sync`, `dry-run` (would apply), `applied`, `applied-with-problems`,
`applied-unverified`, `attention`, `failed`. `detail` counts the roster
creates, updates, deletes and warnings, then names a Club-picker or
club-guard write when there is one (`…, update club picker`): such a
write is applied like a roster change. The Partner-box hide (`HIDE partner
textbox`, "Club names two partners share") is neither counted nor named in
`detail`: it only ever rides along with a counted change, and the run's log
(the row's `run_url`, or `data/auto_sync/<stamp>.log`) shows the line. The Audit tab additionally gets
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
puts the conditions back. It refuses a snapshot whose rules test a club the
Club picker does not offer today (one from before a form's same-name switch,
or before a rename): restored, those clubs' rosters would never show — run
the sync instead. Questions are never deleted by the runner. To stop
the automation: `AUTO_SYNC_APPLY=0` (or clear the two Script Properties).

## The Club picker (mentors choose their club instead of typing it)

Intent: [intent/2026-09-01-club-picker.md](intent/2026-09-01-club-picker.md).
A required **Club** dropdown in Jotform's searchable mode (type to filter,
on phones too) listing every club on the form; the roster rules key on it,
and a calculation copies the pick into the (now hidden) Club Name textbox,
question 5, which is what the Salesforce mapping reads — so `Account_Name__c`
receives the picked entry: the club's name, or `<club> - <partner>` for a
club whose name another partner's club shares ("Club names two partners
share"). Added once per form; from then on every
sync run keeps its option list and properties in the shape `PICKER_PROPS`
defines (`UPDATE club picker (N clubs: options, subLabel…)` in the plan).
**Status:** rolled out to the template and all four regional forms on
2026-09-12 with leadership's approval (`plans/2026-09-12-picker-rollout.md`).
The wording follows the training guide — label **Club Name**, sublabel
"Select your Club Name to see your roster." — and lives in `PICKER_PROPS`:
change it there, never in the builder (the sync reverts hand edits). The same
day `tools/update_static_fields.py` renamed the mentor email field to
"Partner Coordinator Email" and opened the Group Photo question (one photo,
faces visible, 10 MB, HEIC accepted). The searchable component does let a
mentor pick several clubs (20 submissions since 09-01; Jotform ignores
`maxSelection` on dropdowns): the guard is "One club per submission" below.

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

## Club names two partners share

Plan: [plans/2026-09-30-same-name-clubs.md](plans/2026-09-30-same-name-clubs.md).
Salesforce finds a club's Account by question 5, exactly apart from case, in
one org for every region, and creates an Account when nothing matches. So a
club whose name another partner's club also has sends `<club> - <partner>`
(Ryan, 2026-09-30). That one string is the club's entry in the Club picker,
its `calcValue`, what its roster rule and the club guard test, question 5,
and the name of its Salesforce Account. The roster question's own text (the
heading above the names) stays the plain club name. Nothing ever splits a
name on " - ": club names contain it. The seven clubs, once every form is
switched (below):

| Picker entry = question 5 = Salesforce Account | Form |
|---|---|
| `Angels Club - Abaana Community Outreach (ACO) Africa` | Africa |
| `Angels Club - Ready for Reading` | Africa |
| `Ruby - Binti Network` | Africa |
| `Ruby - Health Aid For All Initiative` | Africa |
| `Shining Stars - Seeds of Hope Foundation` | Asia |
| `Shining Stars - World Economy Skills and Agro Development (WESAD)` | Africa |
| `Shining Stars - Youth and Women Opportunities Uganda (YWOU)` | Africa |

Every other club sends its plain name, `Shinning Stars` (Ready for Reading)
and `Super Girls` (Feminature Uganda Limited) included: their namesakes were
retired on 2026-09-30. The sync's `--summary-json` lists what every roster
sends (`sf_names`: qid, partner, club, value); the Salesforce Accounts are
named from those values, character for character.

**Status:** live on all five forms since 2026-09-30 (the template, Asia and
Africa switched; q331 hidden on all five). The intake hold (Part 2, Apps
Script) is merged but not pushed yet. A form that is not switched (a new
regional clone) keeps its same-name rosters on one entry, told apart by the
typed Partner box (q331), until its own switch.

What the sync keeps to, on every run:

1. **Each roster keeps the form it has.** The sync reads back what every
   roster's rule tests — its text, or its text + " - " + a partner the Roster
   has for that club — and never flips one between plain and long on its own.
   A namesake going inactive, or a new one arriving, changes nothing for an
   existing club. When the rules are older than the picker (a restored
   backup, an apply that stopped half-way), the picker's entries say what a
   club sends, and the run says so for each such roster
   (`! '<club>' (q…): its rule tests '<X>', which the Club picker does not list …`):
   until an `--apply` rewrites the rules that roster does not show. The
   runner raises ATTENTION for it and never reads such a form as `in-sync`
   ("Automatic sync").
   A plain roster's rule names no partner. When the Roster has another
   partner's club of that name (a retired one, or a new one that was not
   added), the roster's owner is read from the Roster's rows of any status:
   the partner whose rows list the most of the girls the question holds —
   at least half of them, and more than any other partner's. So a retired
   club's question is never handed to another partner's new club, and an
   existing club keeps its question whatever its new roster is. A tie (the
   same girls under two partners) or no evidence (the old rows deleted, the
   girls respelled in place) names no owner, and the club is matched by its
   girls as before.
2. **A new club may not take a name that is in use.** A club to be created
   whose name another partner's club has — in any region, whatever its
   status — is not created:
   `! new club '<club>' (<partner>) has the name of <other partner>'s club - not added: give it a different name`.
   The rest of the run goes on. The runner raises ATTENTION for it and keeps
   syncing the region. The same when the club of that name is retired and
   its question is still on the form: the newcomer never takes that
   question over. Ask the partner for a different name and rename the club
   in the sheet with
   `tools/rename_club.py --partner … --old … --new … --sheet-only`
   (`--sheet-only` because the club has no question on any form, and the
   question of that name is the other partner's: without it the tool
   refuses; "Renaming a club"). The next run creates it. Until then it is
   on no attendance form, and every apply in its region reads
   `applied-with-problems` ("Automatic sync"). (The Club Roster Form
   handler is to hold such a club before it reaches the Roster — Part 2 of
   the plan; this is the backstop.)
3. **Any other change of what an existing club sends is made by hand.** A
   renamed club, a respelled partner of a long-named club, a rule edited by
   hand: the dry run lists
   `! '<club>' (q…): Club Name (question 5, what Salesforce reads) changes from 'X' to 'Y' - rename its Salesforce account first; an --apply needs --q5-change-ok`,
   `--apply` refuses without `--q5-change-ok`, and the runner never applies
   that region (ATTENTION "not applied", even when nothing else is planned).
   After the Salesforce reconnect: rename the Account to the new text, then
   apply by hand with the flag, in one sitting.

It refuses, before any write: `|` or `{…}` in an entry; two rosters that
would share one entry without the Partner box telling them apart (the way
out is `--same-name-switch`, or deleting a leftover question); a roster
becoming long whose long name is another club's own name; `--partner-picker`
and a form carrying a partner list (both retired 2026-09-30, never
deployed); `--same-name-switch` on a form without the Club picker; and
`--same-name-switch` when a roster that is not in the Roster export (a
retired club's question left on the form) would be alone on the plain entry
beside the long ones (`q… would keep the plain Club picker entry '<club>'
beside the long ones`): a mentor picking the familiar name would get the
retired club's girls. Delete that leftover question in the builder first.

**The typed Partner box (q331)** has nothing left to do once no rule shows
it, and unhidden every mentor sees an optional box: on a form with the Club
picker the sync hides it (`HIDE partner textbox (q331: no rule shows it; …)`,
written after the rules). It is still submitted, blank, so the staff
notification e-mail's "Partner" row is empty from then on. The runner does
not count the hide as a change: it rides along with the next roster change
it applies on that form, or a hand apply, and that run's SyncLog `detail`
does not name it (the run's log does: `HIDE partner textbox`). Today no
rule shows it on Asia, Latin America and U.S, so their next apply hides it,
switch or not.

### The one-time switch (`--same-name-switch`)

By hand, once per form; the runner never passes it. Every roster on the
form whose club name two or more partners' **active** clubs share — in any
region: Asia's Shining Stars shares its name with Africa's — gets its long
entry. Order matters: the runner syncs from `main`, and code from before
this change puts a switched form back on the plain names unattended (read
2026-09-30, in memory: it plans `UPDATE club picker` and the rules, within
the bands). So **merge first**, keep `AUTO_SYNC_APPLY=0` for the window, and
from then on never run `sync_attendance_form.py --apply` from a checkout
without this code. Each step needs Ryan's go. Before the first form: no
open "new club(s) NOT added" ATTENTION in any region (a club that was not
added sits active in the Roster until it is renamed; one on this form's own
list is left out of the switch, one in another region counts as a namesake
and would make an existing one-of-a-kind club long). The template first,
then Asia, Africa (each with its `--region`), then U.S and Latin America,
which have nothing to switch and only get q331 hidden (no flag needed):

```bash
python3 tools/sheets_client.py export Roster data/roster_<date>.csv
python3 backup_forms.py --form 262352490535154                                         # the state before
python3 tools/add_translations.py --audit --form 262352490535154                       # before: note the counts
python3 sync_attendance_form.py data/roster_<date>.csv --roster --form 262352490535154 --same-name-switch            # dry run: the '!' lines
python3 sync_attendance_form.py data/roster_<date>.csv --roster --form 262352490535154 --same-name-switch --apply
python3 sync_attendance_form.py data/roster_<date>.csv --roster --form 262352490535154                               # nothing to do, no '!' line
python3 tools/form_status.py --form 262352490535154 --roster data/roster_<date>.csv              # CLEAN; same-name clubs: 7; partner box: q331 hidden
python3 tools/form_status.py --form 262352490535154 --roster data/roster_<date>.csv --rendered   # N options, N with data-calcvalue = value
python3 tools/add_translations.py --audit --form 262352490535154                       # the "before" counts + the entries added
```

The dry run lists one `! '<club>' (q…): Club Name (question 5, what
Salesforce reads) changes from '<club>' to '<club> - <partner>'` per roster
(no `--q5-change-ok` needed for these), then `UPDATE club picker (N clubs:
calcValues, options)`, `REPLACE conditions`, and `HIDE partner textbox`.
Read on 2026-09-30, after the two retirements:

| Form | `!` lines | Picker entries | `conditions:` | Rules after |
|---|---|---|---|---|
| Template | 7 | 358 → 362 | 384 kept, 9 new, 12 dropped | 393 |
| Asia | 1 | 95 (one renamed) | 123 kept, 3 new, 3 dropped | 126 |
| Africa | 6 | 215 → 218 | 241 kept, 8 new, 11 dropped | 249 |
| Latin America, U.S | 0 | 38, 11 | unchanged | the hide only |

The number of `!` lines must equal the table (or today's count of such
clubs): **one more means stop** — a club is being made long that should
not be. The switch is never the answer to a refused new club; that is a
rename (rule 2).

The new rules are the switched rosters' and the two club-guard rules (their
club lists); the dropped ones are those plus the "show the Partner box"
rule of each name. Between the picker write and the rules write (seconds)
the switched clubs' rosters do not show and their Submit is hidden: apply
each region in its quiet hours, and if an apply stops there, run the same
command again at once (the picker already lists the long names, and the
run finishes the rules; it prints one `! … its rule tests '<club>', which
the Club picker does not list …` per switched roster, and no question-5
line). Left alone, the runner raises ATTENTION for a regional form in that
state on its next run; it does not finish the rules itself, and nothing
watches the template. The translation audit counts picker entries as
untranslated strings, so it rises by the entries added (template 4, Africa
3, Asia 0).

Check in the browser (the template, then Africa):

1. Type "Ruby": two entries, each with its partner. Pick one: only that
   club's roster shows, and no Partner question appears.
2. Pick a second club: the club guard's warning, Submit gone.
3. Chrome "Translate page" with one long-named club picked: no warning,
   Submit shows.
4. At phone width, the two long "Shining Stars" entries can be told apart.
5. The template only: one test submission with a long name. Question 5
   holds it exactly, and question 18 lists the ticked names.

Then `python3 tools/auto_sync.py` (dry run): every region `in-sync` and no
ATTENTION, and `AUTO_SYNC_APPLY=1`. Until every form is switched the runner
reports, once per run, the names more than one club sends ("N Salesforce
name(s) are sent by more than one club"): that is this procedure's job.

### Afterwards

- **A new club with a name in use** is refused (rule 2). `auto_sync`'s
  ATTENTION names the club and whose name it has. Rename it with
  `tools/rename_club.py … --sheet-only`; until then each apply in that
  region reads `applied-with-problems`, and the "missing" or "differ" line
  of that name counts the club that was not added.
- **Renaming a club** is a question-5 change (rule 3, "Renaming a club"
  above). `tools/rename_club.py` cannot rename one of the seven: it refuses a
  form with two questions of the old name (BACKLOG).
- **Renaming a partner** that has a long-named club changes that club's
  entry ("Ruby - <partner>"): the same rule 3. Rename the Salesforce Account
  first. The sync recognises the club by its girls and keeps its roster.
- **A namesake retired later** changes nothing: the club that is left keeps
  its long name (its Salesforce Account keeps its history).
- **Restoring conditions.** `restore_conditions.py` refuses a snapshot
  whose rules test a club the picker no longer offers — every backup from
  before a form's switch, and any from before a rename. Restored, those
  clubs' rosters would never show and the club guard would block their
  mentors. Run the sync instead. `--force` restores anyway: run the sync by
  hand straight after (dry run, then `--apply`), which rebuilds the rules
  on the picker's entries. The runner does not apply a rules-only
  difference: it raises ATTENTION ("roster rule(s) test a name the Club
  picker does not list") on every run until that apply, or until a roster
  change in that region makes it apply.

### Rollback

All forms together, the runner paused from the first step to the last, and
**only before the Salesforce reconnect**. Afterwards plain "Ruby" would
reach Salesforce and put two clubs on one Account: fix forward, or rename
the seven Accounts first.

1. `AUTO_SYNC_APPLY=0`, then `python3 backup_forms.py` (every form).
2. Revert the merge on `main`.
3. With the reverted code, each switched form (the template, Asia, Africa):
   the sync dry run, then `--apply`. It matches the same-name rosters by
   their girls and plans `UPDATE club picker (… calcValues, options)` and
   `REPLACE conditions`, which put back the plain names and the Partner-box
   rules (read 2026-09-30, in memory, on all three). A second dry run says
   nothing to do.
4. Un-hide q331 (`question[hidden]=No`, or the builder) on the template and
   Africa, where rules show it again, and on the others if the box is
   wanted back.
5. `tools/form_status.py`: every form CLEAN. Then `AUTO_SYNC_APPLY=1`.

`restore_conditions.py` is not a rollback here: it leaves the picker on the
long names while the old rules test the plain ones.

## One club per submission (the club guard)

Plan: [plans/2026-09-29-club-guard.md](plans/2026-09-29-club-guard.md).
The Club picker is a multi-select (its searchable mode), so a mentor can pick
several clubs: 20 submissions did between 09-01 and 09-29 (Africa 12, Asia
8). Question 5, the Salesforce field, then receives the names run together
with no separator; Salesforce would create a junk Club Account from it. The
guard stops that on the form. `--club-guard` adds a hidden text element named
`clubGuard` directly below the picker ("You chose more than one club. Keep
only your own club in Club Name, and the Submit button comes back."). It also
generates two rules, whose terms are "the picker is filled" plus "question 5
is not <club>" for every club on the picker:

- a field rule shows the warning and hides Submit;
- a require rule disables Submit, which stops desktop Enter in a text box from
  submitting.

One club picked: question 5 is exactly that club, and the rules stay off. Two
picked: question 5 is no club, and the warning shows while Submit goes away.
Removing the extra club brings Submit back. On a guarded form the picker's
`calcValues` are its own club names, so the copy into question 5 reads a value
the browser's "Translate page" cannot alter (it altered 5 single-club picks,
by one character). The Contact_IDs (q18) sum is left exactly as it is: with
Submit shown, only one roster is visible.

Added once per form. From then on every apply, the runner's included, keeps
the warning, both rules, the club list in the rules and the `calcValues` in
step (`UPDATE club guard (…)`, counted and named by the runner like a picker
update). The runner applies only when something besides the rules changed:
if an apply stops after the picker write and its retry fails too (ATTENTION
"APPLY FAILED"), the new club is on the picker but not in the guard rules,
so its mentors cannot submit, and every later run reports `in-sync` (a
rules-only difference is not a change to the runner, as on a form without
the guard, where the new roster never shows). **Do the dry run and
`--apply` by hand straight away** after any APPLY FAILED. A form without the element keeps exactly today's rules, except the
spelling fix below. **Status:** live on all five forms since 2026-09-30
(template q482, U.S q445, Latin America q453, Asia q456, Africa q462).

The spelling fix is not gated. On a multi-select, Jotform's `equals` is
case-sensitive, so a roster rule spelled unlike the picker's option never
fires. Africa's "SUPER GIRLS" roster (and the template's) can never appear
today. With a picker, every rule now uses the picker's own spelling.
`form_status` flags the old rule ("… which is not one of its options") until
the next apply on that form. The runner does not apply a rules-only
difference, so the fix waits for a roster change in Africa, or for an apply
by hand.

Refusals, before any write: no Club picker on the form (add it first with
`--club-picker`, then run `--club-guard` separately); two elements named
`clubGuard`, or one that is not a text element (on every run, the runner's
included); not exactly one Submit button. A warning (not a refusal): two club
names that, run together, equal a third club. The guard cannot tell that
pair from the one club (none today).

Order matters: the runner syncs from `main`, and older code rewrites the
picker's options but not its `calcValues`, and drops the guard rules. After
the next new club, question 5 would get the neighbouring club's name with no
warning (every one is still a valid club, so nothing blocks it). So **merge
first**, and never run `sync_attendance_form.py --apply` from a checkout
without this code (rebase such a branch first) while any Club picker carries
`calcValues`.

Rollout, with `AUTO_SYNC_APPLY=0` for the whole window. Each step needs
Ryan's go. Only on a form the roster-order repair has finished ("Rosters
above Submit": `form_status` says `layout: every roster above …`) — the
CLEAN below needs it, and the warning's create moves the rosters' orders, so
the repair's `--undo` refuses from then on. The template goes first; after
it, U.S, Latin America, Asia, then Africa (smallest first), each with its
`--region`:

```bash
python3 backup_forms.py --form 262352490535154                                         # note its stamp: the rollback restores it
python3 tools/add_translations.py --audit --form 262352490535154                       # before: note the counts
python3 sync_attendance_form.py data/roster_<date>.csv --roster --form 262352490535154 --club-guard            # dry run
python3 sync_attendance_form.py data/roster_<date>.csv --roster --form 262352490535154 --club-guard --apply    # add it
python3 sync_attendance_form.py data/roster_<date>.csv --roster --form 262352490535154                         # "Club guard: q<id>", nothing to do (else Jotform altered what was written: stop)
python3 tools/form_status.py --form 262352490535154 --roster data/roster_<date>.csv              # "club guard: q<id> (N clubs)", rules CLEAN
python3 tools/form_status.py --form 262352490535154 --roster data/roster_<date>.csv --rendered   # HARD STOP: N options, N with data-calcvalue = value
python3 tools/add_translations.py --form 262352490535154                               # dry run: the warning's entries appear
python3 tools/add_translations.py --form 262352490535154 --apply
python3 tools/add_translations.py --audit --form 262352490535154                       # the "before" counts plus one per club this apply created (see below); any other rise: stop
```

The dry run prints `UPDATE club picker (N clubs: calcValues)`, `CREATE club
guard (below the Club picker)` and `REPLACE conditions (M + 2 rules)`, with
`conditions: K kept, 2 new, 0 dropped`: the 2 new are the two guard rules;
every other rule, the Contact_IDs sum included, is unchanged. Read on
2026-09-29: U.S 12 clubs, 41 → 43 rules; Latin America 39, 68 → 70;
Asia 96, 125 → 127. Africa (216 clubs, 255 → 257) and the template show
`3 new, 1 dropped` while the SUPER GIRLS rule has not landed. The template
also carries the roster creates and updates it is behind on (35 that day,
the same ones the dry run without the flag plans).

The translation audit counts every Club-picker option as an untranslated
string (club names stay English), so after the apply it reads the "before"
counts plus one per language for each club the apply created: the dry run's
`CREATE roster` lines, 23 on the template on 2026-09-30, none on a form in
step. The warning itself adds nothing once `add_translations.py --apply` has
run: it is translated in every language the forms offer.

**The `--rendered` check is a hard stop on the template.** How a
multi-select lays out `calcValues` is unverified: a leading empty slot, as
single-selects have, or none (`glow/sync.py PICKER_CALC_LEADING_EMPTY`). If
the check reports any option whose `data-calcvalue` differs from its value,
question 5 would receive a neighbouring club's name, with no warning.
Restore the template's conditions, delete the element, clear the
`calcValues` (below), flip the constant, and start again. The check also
refuses to pass when the page lists a different number of options than the
picker has ("rendered page lists N of the picker's M options"): an option it
could not read is one it cannot vouch for. (All options
"without" a `data-calcvalue` right after the apply can be a page served from
before it: re-run the check a few minutes later before calling it a
failure.) No regional form
gets the guard until the template's rendered check is aligned.

Check in the browser (the template, then each regional form):

1. Pick one club: no warning; its roster and Submit show.
2. Pick a second club: the warning appears below the picker and Submit is
   gone. Remove it: the warning goes and Submit comes back, not greyed out
   (the require rule's Disable must lift too).
3. With two clubs picked, press Enter in the Partner Coordinator Email box
   on a desktop: the form does not submit.
4. Switch the language (e.g. Español): the warning is translated. Every
   form saves the chosen language in the browser (`saveUserLanguage`), so
   the next form opened there starts in it too; switch back to English.
5. Chrome "Translate page" with one club picked: no warning, Submit shows.
6. The builder's Conditions page shows no error marks.
7. The template only: one test submission. Question 5 holds exactly the
   club, and question 18 lists the ticked names.

When every form passes, set `AUTO_SYNC_APPLY=1`. Then an `auto_sync.py` dry
run shows every region `in-sync`.

Rollback, per form (the runner paused from the first step to the last).
While the `clubGuard` element exists, any apply regenerates the guard rules,
so the element goes before the runner resumes.

1. `AUTO_SYNC_APPLY=0`, then `python3 backup_forms.py --form <id>`.
2. `python3 restore_conditions.py --form <id> --from properties-<stamp>.json`
   (dry run, then `--apply`). `<stamp>` is the backup taken just before the
   `--club-guard --apply`, not `properties-latest.json`. On a form switched
   to the long same-name entries since, that snapshot is refused (its rules
   test the plain names): add `--force`, and do step 5's apply straight
   after — it rebuilds the rules on the picker's entries, without the guard.
3. Delete the `clubGuard` element in the builder.
4. Clear the picker's `calcValues` (its calculation values in the builder, or
   `question[calcValues]` via the API; re-read to confirm it took — an empty
   value through the API is untested). Optional while the form keeps syncing
   on this code, which keeps them aligned with the options. Required before
   anything older syncs the form: older code shifts them on the next new club.
5. The sync dry run without the flag: `nothing to do`, or a `REPLACE
   conditions` for what the snapshot predates. That means roster changes
   applied since it was taken, and on Africa and the template the SUPER
   GIRLS spelling rule (`1 new, 1 dropped` with no roster change) unless an
   apply had already landed it. Back up, then `--apply`.
6. `tools/form_status.py --form <id> --roster …`: rules CLEAN, `club guard:
   none`. Then `AUTO_SYNC_APPLY=1`.

Do not revert the merge while any Club picker carries `calcValues`: clear
them first (step 4) and re-read to confirm. The old code would keep the
stale `calcValues` and send the neighbouring club's name to question 5.

Before any Salesforce back-fill, split or assign the 20 fused question-5
submissions by hand (BACKLOG 48). Nothing has reached Salesforce since
2026-03-28, so none of them has created an Account yet.

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

## Links above Submit (problem report, Club Roster Form)

Two text elements sit directly above the Submit button of every attendance
form, each one linked sentence in a grey box, found by its unique name
(`glow/links.py` holds the table; the public Google Form URLs there are pinned
by a test to the table in [LAUNCH.md](LAUNCH.md)):

| `--link` | Element name | Sentence | Opens |
|---|---|---|---|
| `roster` | `clubRosterFormLink` | A girl missing, or no longer in your club? Tell us on the Club Roster Form. | the Club Roster Form |
| `problem` | `somethingNotWorking` (q443) | Click here to report a problem | the problem-report form |

The Club Roster Form link sits above the problem link, so a mentor with a
roster change meets it first. Adding, re-checking or removing one:

```bash
python3 backup_forms.py                                           # optional: the tool snapshots each form it writes
python3 tools/add_feedback_link.py --link roster                  # dry run, template + 4 regionals
python3 tools/add_feedback_link.py --link roster --apply          # move Submit, move q443, add; re-read and verify
python3 tools/add_translations.py                                 # dry run: the new element's entries appear
python3 tools/add_translations.py --apply                         # GET-merge-POST; the store is saved first
python3 tools/add_feedback_link.py --link roster --remove --apply # take it out again
```

The tool plans all five forms before it writes any, and refuses rather than
guesses: an edit URL (only a `…/forms/d/e/…/viewform` or `forms.gle` link is
accepted), a URL the other link already uses, two Submit buttons, and any
layout where inserting would change the sequence of what a mentor can see
(it simulates the write in render order — by `order`, equal orders in
creation order — before sending it). Re-running is a no-op; a changed URL is
updated in place — then run `tools/add_translations.py --apply` again, since
every other language keeps its own copy of the element, old link included,
until it does (the tool says so after the write). After a write it re-reads
the form: the element once, its text, not hidden, above its anchor and Submit,
the anchor above Submit, and no rule mentioning it.

Translations are a second step because they are keyed by the element's qid
(`text_<qid>`), which exists only once the element does; the sentence's
translations (all offered languages; Hindi and Persian reach Asia only) are
in `tools/translations_additions.json`, written by us and not
native-reviewed. "Club Roster Form" stays in English in every language: the
Google Form it opens is English-only.

The sync never touches these elements: it writes roster checkboxes, the Club
picker, the club guard's warning, the hidden flags of q5
and q331, and the conditions, and no generated rule mentions a link element
(both test-pinned; the club guard's two rules mention only its warning and
Submit). A rule
hand-made on an element would be dropped by the next sync, and the tool
flags one. Rollback: `--remove --apply` (the order gap it leaves is
harmless), the old orders in `backups/<id>/questions-<stamp>.json`, or
Jotform's Revision History.

Every roster must render **above** these links and Submit (next section):
place a link only on a repaired form — `form_status` says `layout: every
roster above …` — and both tools keep that true afterwards (the link goes
directly above its anchor; the sync creates rosters above the first link).

## Rosters above Submit

A mentor sees her girls' names where her club's roster renders, so every
roster must render above the links and the Submit button. Until 2026-09-29
the sync created each new roster at the form's highest order + 1 — after
Submit — and every roster created since the 2026-08-24 overhaul rendered
under the button (Africa 98 of 221 on 2026-09-29; BACKLOG 47). Two parts
(`glow/layout.py`, [plan](plans/2026-09-29-rosters-above-submit.md)). The
repair ran on all five forms on 2026-09-30; the steps below stay for a
relapse (`form_status` names it) or a new regional form:

- **The sync** gives a new roster the order of the last roster rendering
  above the first link (or above Submit when there is no link). Jotform
  inserts a question created at a taken order there and moves the block
  below down by one, so the new roster lands just above that roster; were
  it to keep both at that order, the newer one would render just after it.
  Either way it is above the first link. Its plan says where: `New rosters
  go at order 139, above somethingNotWorking (q443)`. No extra write; the
  links and Submit are never written by the sync. A form with no Submit and
  no link (the test fixtures) still gets the highest order + 1.
- **The one-time repair**, `tools/fix_roster_order.py`, moves what renders
  at and below the first link — the links, Submit, the seven hidden bridge
  fields — to empty orders after the last one, in the same sequence. Nine
  order writes per form (ten once the Club Roster Form link is on it); no
  roster, rule, translation, e-mail or Salesforce mapping is written.

```bash
# first: AUTO_SYNC_APPLY=0, before the merge (below)
python3 tools/fix_roster_order.py                                        # dry run: the template + 4 regionals
python3 tools/fix_roster_order.py --form 262352490535154 --apply         # the template first; open its page
python3 tools/fix_roster_order.py --apply                                # then the four regionals
python3 tools/form_status.py --roster data/roster_<date>.csv             # every form: layout: every roster above …
python3 tools/fix_roster_order.py --form <id> --undo <stamp>             # the rollback (dry run; --apply writes)
```

From the merge (the check ships with it) until every form is CLEAN:
repository variable `AUTO_SYNC_APPLY=0`, set before merging — an unrepaired
form is NOT CLEAN for `form_status`, so a runner apply would end
`applied-with-problems` — then back to `1`. Run the repair in the same
sitting as the merge: until a form is repaired, `form_status` shows the
`layout` problem on it, so no other procedure's "CLEAN" can pass there (the
manual loop, renaming or moving a club, the Club picker, the same-name
switch, the club guard). That line is this section's job, not theirs.

The tool plans all five forms before it writes any and refuses — on every
form — rather than guess: two Submit buttons, a page break, a field a mentor can
see below the first link, a link below Submit, or a simulation of the moves
that would leave a roster below the links or change what a mentor sees.
With `--apply`, per form: a snapshot (`backups/<id>/questions-<stamp>.json`,
stamped to the second; the tool prints the `--undo` line), a re-read and
re-plan (a form changed since the preview is not written), Submit first
(then every roster is above it), the hidden fields, the links last. After
the first write a re-read checks that Jotform kept the order as sent and
moved nothing else. Otherwise it stops after that one write and says what
Jotform stored and what the re-read shows (whether every roster is above
Submit). If other questions shifted too, open the form; if a roster's order
changed, `--undo` refuses (then the builder, or Revision History). After the
last write a re-read verifies the whole form: the same questions, identical
apart from `order`, the orders as sent, every roster above the links and
Submit, the rules unchanged. Anything unexpected — an API error on any read
or write included — stops the run, and later forms stay untouched; the stop
says how many moves were confirmed and, once anything was written, repeats
the `--undo` line. After a
stop (or a gateway 504) run the dry run again first: it re-plans from what
the form holds, a form left part-way says `part-way: …`, and a finished
form says `nothing to do` — if the stop came before the verify, then run
`form_status --form <id>` on it. Keep the stopped run's `--undo` stamp: it
is the rollback to the form before the repair, and it works from the
finished form too; a re-run's snapshot holds the part-way form (undoing it,
then the first stamp, still gets back).

`form_status` checks the layout on every run (`layout:` line, `layout` in
`--json`): a roster rendering below the first link or Submit, a link below
Submit, or not exactly one Submit makes the form NOT CLEAN — and the
runner's verify sees it. Rollback: `--undo <stamp>` puts the snapshot's
orders back by the same path (planned, probed, verified). It is for right
after the repair, before the Club Roster Form link or the club guard is
placed (the guard's warning is created at the picker's order + 1, which
moves the rosters below it down by one, up to the first gap): it refuses
once the form's questions or a roster's order have changed since, and when
the snapshot holds two questions at one order (the link placed before the
repair leaves Submit sharing the next field's order) — then the builder, or
Jotform's Revision History. The builder and the submissions table list
fields by `order`, so the hidden fields move to the end there too
(cosmetic).

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
trigger failed, e.g. between a scope-adding push and the re-authorization),
that failed (FormLog `ERROR: …`), or that were held as a new club — a
possible duplicate, or a club name another partner's club has — and staff
have since released (FormLog `HELD: …`, item 5). It changes nothing
until you confirm:

1. One dialog per group lists what it would run — problem reports not yet
   sent to staff, then Club Roster Form responses not yet processed. Each
   line: sheet row · when it was sent · new club / roster change / problem
   report · the club (partner), or the form a report is about · the last
   error, for a retry. YES runs that group; NO skips it.
2. Club Roster Form responses **sent more than 7 days ago** get a dialog of
   their own. Answer NO unless you know why that response never ran: a
   handler applies a response to *today's* roster. Girls it lists who were
   removed after it was sent stay removed (the replay guard; the ReviewQueue
   gets "Removed girls not put back by an older response") — the 2026-09-13
   run, before the guard, put 20 Radiant Girls back. But its removals and
   new names still apply: an old REMOVE takes off a girl re-added since. A
   row whose "sent" shows text rather than a date (its Timestamp cell is not
   a date) is refused, never run unguarded: FormLog `ERROR: its Timestamp
   cell is not a date …`.
3. **Held** rows are listed and never run: FormLog already has that form +
   sheet row as processed, under a key that no longer matches the row.
   Something changed the row or its key — rows sorted or deleted in a
   response tab, a question title renamed (`Config.gs` `Q`), a Timestamp
   cell edited. Find out what first. To run one deliberately: in FormLog,
   find **every** row with that form and `sheet_row` whose `result` starts
   with neither `ERROR:` nor `HELD:` (after a sort they record *another* response) and
   change only their `sheet_row` cell, e.g. `released 5 by <name> <date>`.
   Leave `response_key` and `result` alone, so what they record stays
   processed. The next run offers the held row as new; check the preview
   lists only that row before answering YES.
4. A failure you have **dealt with by hand** (the report was read, the
   change was entered another way) is offered again on every run until
   FormLog says otherwise: change the `result` of its FormLog row from
   `ERROR: …` to `resolved by hand by <name> <date>` — any result that starts
   with neither `ERROR:` nor `HELD:` counts as done.
5. **Held for review** rows are "Enroll a NEW club" responses the
   duplicate-club guard held (FormLog `HELD: possible duplicate (…)`, a
   **New club held as a possible duplicate** item on the ReviewQueue,
   nothing imported), or that were held because another partner's club
   already has the club name (FormLog `HELD: club name already used by
   another partner`, a **Club name already used by another partner — ask for a different name** item). They are listed with the result, never run, until the
   item's `resolved` cell starts with the word `release` ("Working the
   ReviewQueue"). The next run then asks about them in a dialog of their
   own, "New clubs held for review that staff released": YES imports each
   as sent, against today's roster (girls removed since it was sent stay
   removed, as in item 2), without the duplicate check — except
   an organization typed close to a partner on file, which fails
   `ERROR: release refused: …` until the response row's `Partner
   organization` cell names that partner, or the Partners tab has the new
   organization, and except a club name another partner's club has, which
   fails the same way until the response row's `Club name` cell has a name
   nobody else uses ("Working the ReviewQueue"). An item
   resolved any other way is never run: its row is only named on the
   preview's last line, "Not imported — … resolved without "release"", as
   `row N (ReviewQueue row M)`. A club meant to be imported but resolved
   `Released`, `ok release` or `resolved …: a new club` shows there: change
   that cell to start with `release` and run it again. A held row
   listed as "no ReviewQueue item for this row and time" lost its item (row
   deleted, text typed after the `[#…]` tag, or the tab sorted so the item's
   `(sent …)` no longer matches the row's Timestamp): add the item back by
   hand with its issue (the one of the two above that its FormLog `HELD:`
   row names; every word of it, though capitals do not matter and any dash
   will do for its long one), detail `Roster Form Responses!N (sent <yyyy-mm-dd
   hh:mm:ss from the row's Timestamp>): … [#Roster Form Responses!N]`.

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

**Rolling back `appsscript/`** (`git checkout <target> -- appsscript && npm
run clasp:push`) to a commit before `7a175c4` brings back the old menu item,
which cannot read the new keys and would re-run everything processed since
the deploy, without a preview. Roll back no further than `7a175c4`; it shows
rows logged under the new keys as held. Once the Feedback tab has two reply
columns, no further than `986a325` ("Google Forms wording", below). To undo
the 2026-09-28 integration deploy, the target is `986a325`: `main`'s code
before the merge plus that two-column read.

**Held new clubs and a rollback below the duplicate-club guard.** Code
without the guard (`git grep -q HOLD_PREFIX <target> -- appsscript/FormHandlers.gs`
finds nothing: `986a325`, and `main` before the 2026-09-28 integration)
reads a FormLog `HELD:` row as done. There, `release` followed by **Process
any missed form responses** imports nothing ("Nothing to process.") and
still closes the item, after the mentor was told the club would be added.
Before such a rollback, filter the ReviewQueue for **New club held as a
possible duplicate** and **Club name already used by another partner — ask for a different name**
items that are open, or released with no later FormLog
row for that response (same form and `sheet_row`) whose result starts with
neither `ERROR:` nor `HELD:`. While rolled back, never write `release` on
them: after rolling forward, release them and the menu offers them as usual.
Staying rolled back, handle each really-new club by hand: send "Enroll a NEW
club" yourself with the response row's answers (the old code imports it),
then resolve its item `resolved <date> by <name>: entered by hand` (over a
`release` already there), so a later roll-forward never imports it twice.
For a club held for its name, send it under the new name the partner gave.

**Same-name holds and a rollback below the same-name check.** Code that has
the duplicate-club guard but not the same-name check (`git grep -q
SAME_NAME_ISSUE <target> -- appsscript/FormHandlers.gs` finds nothing, `git
grep -q HOLD_PREFIX …` finds the guard: `main` from the 2026-09-28
integration up to the same-name push) keeps a response held for its name
held: it does not know a **Club name already used by another partner — ask for a different name** item, so the menu lists that
row as "no ReviewQueue item for this row and time" and never imports it,
whatever the item says. Nothing is lost: release it after rolling forward.
While rolled back, a new club whose name another partner's club has is
imported again, as before the push: the automatic sync then refuses to add
it to the forms and says so (ATTENTION, "not added: give it a different
name"), and the Monday e-mail's Salesforce lines show the plain club name
for every club — for a club that shares its name, the account name is the
text of its entry in the attendance form's club list
([plans/2026-09-30-same-name-clubs.md](plans/2026-09-30-same-name-clubs.md)).

## Working the ReviewQueue

The **ReviewQueue** tab holds every question the scripts could not decide.
**Owner: Ryan.** The Monday e-mail (to `STAFF_NOTIFY_EMAIL`) lists the
open items by issue, with their ReviewQueue row; work them that week. It
arrives between 09:00 and 10:00 New York time. Apps Script writes every
timestamp in the sheet's zone (America/New_York); the one exception is this
trigger's hour, which follows the script project's zone
(`appsscript/appsscript.json`: America/Chicago), so `atHour(8)` fires
08:00-09:00 Chicago time, 09:00-10:00 in the sheet's zone.

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
| **New club held as a possible duplicate** | "Enroll a NEW club" was sent for what may be a club already on file: nothing was imported, and the mentor was told it is being checked. Detail says why — names already active in one club, a club name close to one of the partner's, a typed organization close to a partner on file, or a re-enrollment whose list is mostly not the club's — and names the club(s) on file. Compare the response row (the tag) with those clubs' Roster rows. **Same club:** enter only its new girls on "Add or remove girls" for the club on file (REMOVE anyone who has left), then `resolved <date> by <name>: same club as <club>`. **A new club after all, or the new list is right:** `release <date> by <name>: <why>` (`release` must be the first word), then run **Process any missed form responses**: it asks about released rows separately and imports each as sent. **If the reason says "the organization was typed as …, close to … on file"**, fix that first, or the club is filed under a second spelling of the partner (no region, a second form section — the `ion bu` case): if it is that partner, set the response row's `Partner organization` cell to the partner exactly as the Partners tab spells it (the row stays matched to its item by its Timestamp, and the release preview shows the corrected partner); if it really is another organization, add it to the Partners tab with its region. Until then the release run refuses it (`ERROR: release refused: …`, offered again by the next run). **Sent by mistake:** `resolved …: not imported`. Never ask the partner to send it again, and never edit the `(sent …)` or the `[#…]` tag in detail: the menu matches both to the response row. |
| **Club name already used by another partner — ask for a different name** | "Enroll a NEW club" was sent with a club name that another partner's club already has — any status, any region; capitals and spacing are ignored, a plural or a typo is a different name — or that reads as a club on file followed by its partner (`<club> - <partner>`). Nothing was imported, and the mentor got the same "it is being checked" note as any held club. A new club may not take a name in use: the attendance forms and Salesforce tell clubs apart by name, and the sync would refuse to add it ([plans/2026-09-30-same-name-clubs.md](plans/2026-09-30-same-name-clubs.md)). Detail names the club(s) that have the name. **First rule out a mix-up:** compare the response row (the tag) with that club's Roster rows — it may be that club, sent under the wrong partner — and, when detail gives more reasons (names on file, a close club name), with the other clubs it names. **Same club:** enter only its new girls on "Add or remove girls" for the club on file, then `resolved <date> by <name>: same club as <club> (<partner>)`. **That club, but the Roster has it under the wrong partner (or it has moved to this one):** move the club on file first ("Moving a club to another partner" — the tool refuses a club whose name two partners already share, and a partner in another region: Ryan's call), then write `release <date> by <name>: club moved to <partner>` with the `Club name` cell unchanged and run **Process any missed form responses**: the response now runs as that existing club (its new girls are added; no second club, no Salesforce line). **A new club:** ask the partner for a different name (the school or the place added is enough: `Stars (Testville Sec Sch)`). Then either **(a) release it under the new name:** set the response row's `Club name` cell to the new name (the row stays matched to its item by its Timestamp), write `release <date> by <name>: renamed to <new name>` (`release` must be the first word), and run **Process any missed form responses** — its preview shows the new name, and YES imports the club as sent otherwise; or **(b) have it sent again:** the partner (or you, from the response row's answers) sends "Enroll a NEW club" under the new name, and you close this item `resolved <date> by <name>: sent again as <new name>` — the held response is then never run. A release with the name unchanged, or changed to another name in use, is refused (`ERROR: release refused: …`, offered again by the next run) and adds a **Form response could not be processed** item: fix the cell, run it again, then close that item. **If detail also says "the organization was typed as …, close to … on file"**, fix that first, as in the row above. **If detail says "this club is on file with no active girl":** the partner sent "Enroll a NEW club" for a club of its own that has no active girl left, and another partner's club has its name. A club retired as a duplicate (the two of 2026-09-30) has no roster on the attendance forms any more, so bringing it back would add a new club under a name in use, which the sync refuses. Work it as above: the girls usually belong to the partner's up-to-date club (**Same club**); a club that really starts again needs a different name (**A new club**). The one false hold: a club that only lost every girl still has its roster on its attendance form, and keeps its name and its Salesforce account — none on 2026-09-30 (the only clubs with no active girl are the two retired ones). That one is Ryan's: he sets one of its girls back to `active` in the Roster (one who is on the list sent, if there is one; `removed_date` emptied — the only Roster cells typed by hand for an item), then releases with the `Club name` cell unchanged: the response runs as that existing club. Never edit the `(sent …)` or the `[#…]` tag in detail. The clubs that already share a name and have active girls are not affected: their own enrollments and roster changes run as always. |
| **Roster change sent as a problem report** | Read `Feedback!N` (the tag). Check the Roster and Audit `rosterChangeForm`: the partner may have sent it since. Enter it as above, or ask the partner to. Not a roster change after all: `resolved …: not a roster change`. A roster-change report whose staff e-mail lacks the "Staff note" line was missed by the keyword check: add a row by hand with this issue and `[#Feedback!N]` as the last text of detail (reports from before 2026-09-28 were added by `tools/backfill_feedback_review.py`). |
| **Removal did not match anyone** | Detail shows the typed name and up to 3 "Closest names on file" — other girls, so never send them to the mentor. REMOVE only a match that is clearly her; otherwise ask the mentor for the enrolled spelling (her confirmation said "our team will check"). |
| **Removed girls not put back by an older response** | A Club Roster Form response ran after some girls it lists had been removed — a retry, or an old response confirmed in "Missed form responses" — so they stayed removed instead of coming back (the 2026-09-13 replay cannot recur). Detail names the response row, the day it was sent and the Roster rows; the mentor's confirmation (roster changes) listed the names the mentor typed under "Not added back". Usually nothing to do: `resolved …: stayed removed`. If a girl really has rejoined since her removal (ask the partner), ADD her as above: the same ID comes back. |
| **Same name listed twice** | Only one girl is on the Roster. Ask the partner: two girls → ADD the second with a mark, e.g. `Jane Doe (B)` (the first keeps her ID); one girl typed twice → `resolved …: one girl, no change`. Never resubmit through "Enroll a NEW club". |
| **Partner says two girls share a name** | The partner answered Yes but no name repeats. Compare their note with the club's Roster rows: listed distinctly → resolved, no change; one missing → ADD her with a mark as above. |
| **Girls missing from the latest enrollment** | "Enroll a NEW club" was sent for a club already on file; the girls not in that list stay active. Ask the partner who has left and REMOVE them as above. If the new list was not this club's at all (Radiant Girls, 2026-08-31), REMOVE the rows it added as above: the names whose Roster `source` is that response row (Ryan's go). |
| **Roster change for a club not on file** | Nothing changed, the mentor got no confirmation, and it is never retried. Find the club under another name or partner ("Renaming a club", "Moving a club to another partner"), run **GLOW → Google Forms → Update form dropdowns from the Roster**, then enter the change from the response row (or ask the partner) and tell the mentor. A truly new club uses "Enroll a NEW club". |
| **Partner has no region** | Its girls reach no attendance form. A misspelled partner → "Moving a club to another partner". Otherwise set the Partners-tab region (`Africa`, `Asia`, `Latin America`, `U.S`), run **GLOW → Refresh regions from the Partners tab**, and check that the region's next SyncLog row says `applied`. |
| **Form response could not be processed** | Detail names the response row and the error. Fix the cause (a Script Property, a missing answer), then run **Process any missed form responses** ("Missed form responses"). A Club Roster Form response more than 7 days old, or one refused because its Timestamp cell is not a date (a retry fails the same way): enter the change fresh instead and set its FormLog result to `resolved by hand by <name> <date>`. Close the item once FormLog has a row for that response (same form and `sheet_row`) whose result starts with neither `ERROR:` nor `HELD:` — the retry's success, or the one you set by hand; the earlier `ERROR:` row stays, and **Process any missed form responses** no longer offers it. A retry that was held (`HELD:`) continues as its **New club held as a possible duplicate** or **Club name already used by another partner — ask for a different name** item: close this one. |

## Google Forms wording

The two Google Forms (the Club Roster Form and the problem form "Something
isn't working?") take their descriptions and help texts from
`appsscript/Forms.gs` `WORDING`. A fresh build already has the current
wording; forms built before 2026-09-28 get it once, from the menu
([plans/2026-09-28-forms-wording.md](plans/2026-09-28-forms-wording.md)):

1. Deploy ("Apps Script deploy" below; no new Google service, so no
   authorization prompt). Reload the sheet.
2. **GLOW → Google Forms → Update the forms' wording (one-time; shows the
   changes first)**. The preview lists each change as `now:` / `new:`. On the
   live forms there are five: the problem form's description (a new paragraph
   sending roster changes to the Club Roster Form), its reply-email question
   (re-added), the Club Roster Form's description (its last line), the "Club
   name" help text (new club) and the REMOVE help text. Anything **left as
   is**, because someone edited it by hand, is listed after them with the
   suggested text. YES makes exactly the listed changes; NO changes nothing
   (Audit: `cancelled at the preview`).
3. It ends with `Done — N change(s); re-read: up to date` and one Audit row
   `migrateFormWording: changed: …`. Open both fill-in links from the dialog;
   **do not submit a test response**. A second run says "Nothing to change".

- "The forms changed since the preview", "the preview was open too long",
  "Another GLOW operation is still running": nothing was changed; run it
  again.
- "Could not open the … saved in Script Properties": nothing was changed.
  Run it from the Google account that owns the forms, or later (a Forms
  outage). **Never** run "Create the Google Forms" to fix this: it would
  make new forms, and the live forms' responses would no longer be
  processed (it refuses in that case, "Nothing was created").
- "Stopped after N of M change(s)": what landed stays; run it again, and it
  makes only the changes still missing. If the dialog says the reply-email
  question was **PARTLY added**, first open the problem form in the Forms
  editor: give that question exactly its title, Response validation
  "Text → Email address", and move it right after the device question, or
  delete it; then run it again. A run cannot see a missing validation (the
  handler then simply does not use a non-address as Reply-To). An untitled
  short-answer question, or the reply question away from the device
  question, is listed as left as is and never gets a second question.
- A text left as is: paste the suggested text in the Forms editor if you
  want it, or leave it.
- **The Feedback tab will most likely get a second column** titled "Your
  email, if you would like a reply (optional)": the old one (kept by Google
  when the question was removed by hand; the reports since carry no address)
  and the new one. Leave both — the handler reads whichever cell is filled
  in. Never delete, move or retitle response columns.
- Wording can be edited in the Forms editor, but never a question **title**:
  the handlers read answers by title (`Config.gs` `Q`).
- Rollback: the Forms editor. The 2026-08 texts are in `Forms.gs`: the
  problem form's description `WORDING.FEEDBACK_INTRO`, the Club Roster
  Form's description `rosterDescription2026_08_()` (ending with the problem
  form's link), and the help texts `WORDING.CLUB_HELP_2026_08` ("Club name")
  and `WORDING.REMOVE_HELP_2026_08`. A wrongly added question is deleted
  there, and its column in the tab stays, harmless. Rolling back
  `appsscript/` changes nothing on the forms and removes the menu item, but
  before 986a325 it also reverts the handler's read of two same-titled
  columns (`responseFromValues_`): with the new reply column left of the old
  one, every reply address would read blank again. So never roll
  `appsscript/` back before 986a325 while the Feedback tab has two reply
  columns.

## Club accounts in Salesforce

Since 2026-09-30 every active club has a **Club account** in Salesforce (production), named
exactly as its attendance form sends it and linked to its partner account through the parent
account field ([plan and result](plans/2026-09-30-salesforce-clubs.md)). The attendance
processor matches the submitted club name against every account name, ignoring capitals only;
when nothing matches it creates a new, partner-less Club account.

- **Never edit a club's name in Salesforce.** A rename starts in the sheet ("Renaming a club"),
  and the account is then renamed to the new picker text - with Ryan's go.
- **A new club** reaches the forms automatically but not Salesforce (BACKLOG 27). It shows in the
  SF Pending tab and the Monday e-mail; its account is created by hand or as a further round of
  the procedure below, before its first attendance if possible.
- **Signals** (read-only queries, all expected as stated):
  - Club accounts without a parent: exactly the two pilot accounts that are on hold. One more
    means a form sent a name no account carries.
  - Contacts on Club accounts that are not girls (role other than Participant), Contacts on Club
    accounts marked as portal sign-ups, Monthly Reports on Club accounts, programme-income
    records on Club accounts: all 0.
  - `python3 tools/sf_club_accounts.py soql --totals`, then
    `totals --result <saved answer> --also data/sf_prep_2026-09-30/created_accounts_round2.csv
    data/sf_prep_2026-09-30/created_accounts_round3.csv` → `totals ok` (364 Club accounts).
- **Writing to Salesforce** is not covered by the live gate: the only gate is Ryan's go in the
  conversation. Records are written one per call through the write connector, never by a
  subagent; `tools/sf_club_accounts.py` (which never calls Salesforce) cuts the batches, checks
  each saved answer and keeps the rollback files.
- **Rollback files** (never committed): `data/sf_prep_2026-09-30/created_accounts.csv` (345
  created, 8 linked), `created_accounts_round2.csv` (2 created), `created_accounts_round3.csv` (the
  7 same-name clubs), `link_targets_before.json` (the pilot accounts as they were). A created account may be deleted only while it has no Contacts
  and no attendance, and only with Ryan's go.

## Work log and invoices

This is contract work, invoiced monthly from `worklog/worklog.csv` (date, hours, blocks,
description, source, zone). `python3 tools/worklog.py update` recomputes the hours from Claude
Code's session transcripts: all sessions merged into one timeline, cut into blocks wherever
nothing happened for 30 minutes, a block counting only if Ryan wrote in it (an agent working
alone is not billed), each block on the day it **started** (a session past midnight stays on its
first day), each day rounded to the quarter hour. It keeps a written description, fills an empty
one from the commits made during that day's blocks, and never touches `manual` rows. It
recomputes the last 14 days, reaching back to the last logged day when the log is behind (never
past 29 days), or from `--since`. Claude Code deletes a session's transcript about 30 days after
its last activity, so run `update` at the end of every session (CLAUDE.md asks Claude to). Work
outside Claude Code: `python3 tools/worklog.py add --date 2026-09-29 --hours 1.5 --description "…"`.
At month end: `python3 tools/worklog.py export --month 2026-09 [--rate 60] --out invoice-2026-09.csv`.

**Time zones.** Days are counted on the clock the Mac showed at the time, which moves when Ryan
travels. `worklog/timezones.csv` records it (`since` = a UTC instant, `zone` = an IANA name like
`Asia/Tokyo` or an offset like `+03:00`, `evidence`), so a past day never moves when the Mac
does. `update` refuses in two cases, and says what to run:

- the Mac's own zone (read from `/etc/localtime`, whatever `TZ` the shell sets) is not the
  timeline's zone now → record the switch:
  `python3 tools/worklog.py zone --since <instant> --zone <IANA name>`. Any moment between the
  last session on the old clock and the first on the new one gives the same hours. The tool
  bounds it by the last commit made on the old clock and the first made on the new one, and
  suggests the clock-change time (or the idle stretch just before the session after it, or the
  longest idle stretch) - check it against when you actually travelled. `zone` refuses a moment
  before a commit made on the old clock, after one made on the new clock, or inside a session
  (unless the clock changed during that session: then any moment between its two commits). Prefer
  the IANA name: it follows daylight saving;
- a commit's recorded offset disagrees with the timeline → a trip was never recorded. If the Mac
  went away and came back, add both switches to `worklog/timezones.csv` by hand, in time order
  (`zone` records only a switch after the last row). `--ignore-commit HASH` is only for a commit
  not made on this Mac.

`python3 tools/worklog.py zone` (no arguments) shows the timeline, the Mac's zone and the commit
offsets since the last row.

**What `update` will not do without being asked.** It refuses when a day before the window would
change (work that moved across the window's edge, or a day never logged) and names the `--since`
to use. It refuses to drop a row that lost all its work until `--drop-stale` is given (then move
that row's written description to the new day by hand, and refresh the descriptions of the days
whose blocks changed). A row older than 29 days, or any row when reading another folder with
`--transcripts`, is never dropped and never changed - one of its sessions may have expired - and
is reported as kept; `--rewrite-old` lets a deliberate correction through when the transcripts are
known to be complete. The 2026-09-30 correction (`docs/plans/2026-09-30-time-zones.md`) re-cut
September this way: Sep 1-14 had been counted at +08:00 although the Mac was on +02:00/+03:00.

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
ERROR` ("Missed form responses" above). Rollback is a push of the
previously deployed `appsscript/`, not "the previous commit" (after a merge
that can be the same code). For the 2026-09-28 integration deploy that is
`git checkout 986a325 -- appsscript && npm run clasp:push`. First read
"Rolling back `appsscript/`" above: the floors (`7a175c4`, and `986a325`
once the Feedback tab has two reply columns) and held new clubs.

**The same-name push (2026-09-30, Part 2 of
[plans/2026-09-30-same-name-clubs.md](plans/2026-09-30-same-name-clubs.md);
build notes: [plans/2026-09-30-same-name-intake.md](plans/2026-09-30-same-name-intake.md))**
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
node tools/build_roster_offline.js data/enrollment_<date>.csv --tz America/New_York --existing data/live_<date>
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
