# Runbook

Every operational procedure, in one place, each with its dry-run and its
apply form. Everything here talks to LIVE systems (the four regional Jotform
attendance forms, the master enrollment Google Sheet, the Apps Script bound to
it, and through the forms, Salesforce). The forms and the sheet went live on
2026-09-01.

How to read it. A procedure starts with the same short list, where it applies:
**When** to use it, its **Status** (one line, with a link to its plan's Result),
the **Dry run**, the **Apply** (a live write: Ryan's go, CLAUDE.md rule 1), how to
**Verify** it and the **Rollback**. History - who decided what and when, how a
rollout went - lives in the plan it belongs to (`docs/plans/`), linked by a
**History** line. A finished one-time procedure keeps a short stub here; its
full text, commands included, moved to its plan. Tools and tests quote these
headings, so a heading is never renamed (`make check` runs
`scripts/check_doc_refs.py`); add a section rather than reword one.

**Contents**

- [Jotform forms](#jotform-forms)
  - [The forms](#the-forms)
  - [Keeping the forms in step with the Roster (the manual loop)](#keeping-the-forms-in-step-with-the-roster-the-manual-loop)
  - [Automatic sync](#automatic-sync)
  - [Backup and restore (Jotform)](#backup-and-restore-jotform)
  - [The Club picker (mentors choose their club instead of typing it)](#the-club-picker-mentors-choose-their-club-instead-of-typing-it)
  - [One club per submission (the club guard)](#one-club-per-submission-the-club-guard)
  - [The names list sent to Salesforce](#the-names-list-sent-to-salesforce)
  - [The names dictionary and the module values](#the-names-dictionary-and-the-module-values)
  - [Translations](#translations)
  - [Links above Submit (problem report, Club Roster Form)](#links-above-submit-problem-report-club-roster-form)
  - [Rosters above Submit](#rosters-above-submit)
  - [Header logo](#header-logo)
  - [Photos](#photos)
  - [Disabling a regional form](#disabling-a-regional-form)
  - [Building a new regional form (not maintenance)](#building-a-new-regional-form-not-maintenance)
- [Clubs](#clubs)
  - [Renaming a club](#renaming-a-club)
  - [Moving a club to another partner (a mistyped partner)](#moving-a-club-to-another-partner-a-mistyped-partner)
  - [Club names two partners share](#club-names-two-partners-share)
  - [Clubs that do not use Jotform](#clubs-that-do-not-use-jotform)
  - [Deactivating a club](#deactivating-a-club)
  - [Roster rebuild and upload (offline path)](#roster-rebuild-and-upload-offline-path)
- [Sheet and Apps Script](#sheet-and-apps-script)
  - [Working the ReviewQueue](#working-the-reviewqueue)
  - [Missed form responses](#missed-form-responses)
  - [Google Forms wording](#google-forms-wording)
  - [Apps Script deploy](#apps-script-deploy)
  - [Data-quality report](#data-quality-report)
- [Salesforce](#salesforce)
  - [Club accounts in Salesforce](#club-accounts-in-salesforce)
  - [Duplicate girls in Salesforce](#duplicate-girls-in-salesforce)
  - [Attendance totals and partner-reported counts](#attendance-totals-and-partner-reported-counts)
  - [Attendance dashboard in Salesforce](#attendance-dashboard-in-salesforce)
  - [September back-fill: the resolver](#september-back-fill-the-resolver)
  - [Back-fill of attendance into Salesforce](#back-fill-of-attendance-into-salesforce)
- [Admin and work log](#admin-and-work-log)
  - [Credentials](#credentials)
  - [Live gate (Claude Code)](#live-gate-claude-code)
  - [Work log and invoices](#work-log-and-invoices)
- [Offline checks](#offline-checks)
  - [Checks](#checks)

# Jotform forms

## The forms

| Region | Form id | Mentor link |
|---|---|---|
| Africa | `262382821971058` | https://form.jotform.com/262382821971058 |
| Asia | `262383129464057` | https://form.jotform.com/262383129464057 |
| Latin America | `262383455778067` | https://form.jotform.com/262383455778067 |
| U.S | `262382706852058` | https://form.jotform.com/262382706852058 |
| Template (every logic change lands here first) | `262352490535154` | not for mentors |

The same ids live in `glow/forms.py`, in Python only (Apps Script never calls
Jotform; its copy went on 2026-10-09). The tools that keep a table of their own
for its order or labels (`tools/auto_sync.py` `REGIONAL_FORMS`,
`tools/form_status.py`, `backup_forms.py`, …) are pinned to it by
`test/glow_lib_test.py`. The five pre-launch forms
are retitled "… (defunct)" (`260703905772560` Africa, `260704198384564` Asia,
`260704170003542` Latin America, `260703912140547` U.S, `260555608160556`
master), keep their submission history and have been `DISABLED` since
2026-09-30 (read 2026-10-06: `status: DISABLED`, the default "This form is
currently unavailable!" page; how they were switched off is not recorded — the
builder, presumably; BACKLOG 1).

The two Google Forms partners and mentors use were made in the master
enrollment sheet by **GLOW → Google Forms → Create the Google Forms** on
2026-08-27 and renamed since in the Forms UI to "Global Catalyst – Club Roster
Form" and "Global Catalyst – Something isn't working?" (a rename never changes a
link). Their responses land in the sheet's *Roster Form Responses* and
*Feedback* tabs. The owner-only edit links are shown by **GLOW → Google Forms →
Show form links** and are deliberately not written down. The public links are
`glow/links.py`'s defaults; `test/links_layout_test.py` pins them to this table:

| Google Form | Link for partners and mentors |
|---|---|
| Club Roster Form (enroll a new club / add or remove girls — one form, page 1 picks) | https://docs.google.com/forms/d/e/1FAIpQLScPO9Dizjl9G8krMcvs1sVnqYku3k8dB7Ycv-1VahgPDssMzQ/viewform |
| Something isn't working? (the problem-report form) | https://docs.google.com/forms/d/e/1FAIpQLSeYx286-Bre0aSOWnhEDgC4_6FjGyPssldLA3J5WzIeK8cKCA/viewform |

## Keeping the forms in step with the Roster (the manual loop)

- **When:** a region the runner left at `attention` or `failed`, or a change it never applies on its own (a question-5 change, a rules-only difference, a hand rollout).
- **Status:** in use since launch; the runner does the same on every roster change ("Automatic sync").
- **Dry run:** steps 1-4 below, or `python3 tools/auto_sync.py` for every region.
- **Apply:** step 5, with Ryan's go.
- **Verify:** step 6: `CLEAN`.
- **Rollback:** `restore_conditions.py` from step 3's snapshot ("Backup and restore (Jotform)").

The automatic sync (below) does this on every roster change and every
morning. By hand, per region:

```bash
python3 tools/sheets_client.py export Roster data/roster_<date>.csv        # 1. export the Roster...
python3 tools/sheets_client.py export Partners data/partners_<date>.csv    #    ...and the Partners tab
python3 tools/form_status.py --roster data/roster_<date>.csv \
        --partners data/partners_<date>.csv                                # 2. what differs? (read-only)
python3 backup_forms.py --form 262382821971058                             # 3. snapshot the form
python3 sync_attendance_form.py data/roster_<date>.csv --roster \
        --partners data/partners_<date>.csv \
        --region Africa --form 262382821971058                             # 4. dry run
python3 sync_attendance_form.py data/roster_<date>.csv --roster \
        --partners data/partners_<date>.csv \
        --region Africa --form 262382821971058 --apply                     # 5. apply
python3 tools/form_status.py --form 262382821971058 --roster data/roster_<date>.csv \
        --partners data/partners_<date>.csv                                # 6. verify: CLEAN
```

Or all four regions in one go, with the same guards the workflow uses:

```bash
python3 tools/auto_sync.py             # dry run, every region, nothing written anywhere
python3 tools/auto_sync.py --apply     # apply within the bands
# --synclog additionally records the run in the sheet's SyncLog (the workflow always passes it)
# --roster data/roster_<date>.csv --partners data/partners_<date>.csv: today's exports instead of new ones
```

What to know:

- `form_status.py` needs `--roster`: since 2026-10-09 it refuses to run
  without it (it used to fall back to the stale pre-launch build
  `data/roster_build/Roster.csv`). Always pass a fresh export.
- `--partners` is the Partners tab ("Clubs that do not use Jotform"). The
  sync reads which partners' clubs are kept off the forms from it; without it
  a hand run cannot tell a retired roster from one an apply left half-written,
  so the dry run says so per roster (`! '<club>' (q…) has no Club picker entry
  and no show rule although its club is active in the Roster …`) and `--apply`
  refuses to put such a roster back; `form_status.py` reads NOT CLEAN on it.
  The runner always passes it (and refuses `--roster` without it). Its dry run
  prints the form's status first (`Form: <id> status ENABLED`) and refuses
  `--apply` on a disabled form without `--disabled-ok`.
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

## Automatic sync

- **When:** always on: every roster change in the sheet starts a run, and a backstop run every morning.
- **Status:** live since 2026-09-01, applying since 2026-09-12 (`AUTO_SYNC_APPLY=1`, BACKLOG 1b; [plan](plans/2026-09-01-auto-sync.md)).
- **Dry run:** `python3 tools/auto_sync.py` (writes nothing anywhere).
- **Apply:** the workflow, within the bands; by hand `python3 tools/auto_sync.py --apply`, Ryan's go.
- **Verify:** the SyncLog row (`in-sync`, `applied`); anything else has an ATTENTION item.
- **Rollback:** "Rollback" at the end of this section; to stop the automation, `AUTO_SYNC_APPLY=0`.

**Path:** a roster change in the sheet (New Club / Roster Modification form,
a rebuild, or a region refresh) → `appsscript/Dispatch.gs` starts the
workflow on GitHub (`workflow_dispatch`; the older `repository_dispatch` event
is still accepted) → `.github/workflows/auto-sync.yml` →
`tools/auto_sync.py` exports the Roster and Partners tabs and, per region,
reads the form's status (a form that is not `ENABLED` is `skipped`, nothing
run against it; a status that cannot be read is `failed`), dry-runs the
sync, checks the safety bands, backs up, applies, verifies with
`form_status.py`, and appends a row to the sheet's **SyncLog** tab. The
workflow also runs every morning (the cron is UTC: 06:00 Chicago in summer,
05:00 in winter) as a backstop for missed
events and manual sheet edits, and can be started by hand from the Actions
tab ("Run workflow", optional region).

**New clubs' Salesforce accounts**: with the repository variable `SF_SYNC` at `plan` or `apply`
the run also checks Salesforce, and with `apply` creates the account of each new club right
before the region's form puts it on the Club picker ("Club accounts in Salesforce", "New clubs'
accounts, automatically"). It is one more SyncLog row, region `Salesforce`; its problems are
ATTENTION items starting `SF:`. The end-of-run check reports a partner-less stray account
only when every regional form's names were read, and a region whose form is disabled
(`skipped`) counts as read: its clubs keep their accounts, under their partner, so they are
not strays (a `failed` region does not count, and no stray is reported that run).

**Safety bands** (per region, per run; `--max-creates`, `--max-updates`,
`--max-retires`, `--max-restores`):
at most 5 new clubs and 20 roster updates; at most 5 rosters taken off the
Club picker and 5 put back ("Clubs that do not use Jotform"), and none put
back from a Partners export without the `jotform` column (nobody can be
marked in it); never a delete;
not when a roster
would be replaced by one sharing no names with the current one; not when the
export looks truncated (fewer than 1,000 active rows, or many clubs on the
form missing from the export; a Partners export missing a partner with active
clubs makes the sync itself refuse, `failed`); never a change of what an
existing club
sends to question 5, its Salesforce Account name (a renamed club, a
respelled partner — "Club names two partners share"), which stops the
region even when nothing else is planned. Outside the bands nothing is
written, the region is logged as `attention`, and
`data/auto_sync/ATTENTION.md` (kept as a workflow artifact) says what to do.
Four more things raise ATTENTION without stopping a region: a new club that
was not added to its form because another partner's club has its name (the
rest of the region is applied as usual; the SyncLog `detail` says "N new
club(s) not added (name in use)"), a Partners-tab `jotform` cell holding
something other than `yes`, `no` or blank (read as yes; `detail` says "N
jotform value(s) not understood"), a Partners export with no `jotform` column
at all (nobody is marked in it; `detail` says "Partners export without a
jotform column"; a plan that would put a roster back from it is held), and,
once per run, any name that two clubs of the regions synced send to question
5 — and, read with the exports, a sheet time zone that differs from
`glow/sync.py SHEET_ZONE` (the no-active-girl rule's day would be off by the
difference). Until a club that was not
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

Four generated **rollout lines** are applied like a roster change, within the
bands (DECISIONS 2026-10-14: the merge is the rollout; review and the tests
are the gate). First, the sync's warning that **question 18 is calculated the
old way** (`question 18 (Contact_IDs) is not recalculated after the rosters
change`): its rules-only `REPLACE conditions` is never `in-sync`; the runner
applies it to every enabled regional form on its next run, and the SyncLog
`detail` says `question 18 rules rewritten`. Second, a **`REQUIRED roster`
line**: the required flag written on a roster that has no other change; the
runner applies it on its next run, and such lines never count against
`--max-updates` (they come from a constant, not the export, so flipping
`ROSTERS_REQUIRED` is one rollout for every roster). It also creates rosters
required and applies an options update that sets the flag (`UPDATE roster … ;
required: Yes`). Third, an **`UPDATE module dropdown` line**: a module
dropdown's `calcValues` or the special-event options appended with them, not
counted against `--max-updates` either; the runner applies it on its next run,
so a new type in `SPECIAL_EVENTS`, a constant flipped, or a dropdown edited in
the builder reaches every enabled regional form that way ("The names
dictionary and the module values", "Special events"). Fourth, the sync's
warning that **the form's rules let a special event show or send a session**
(the option on the form, the rules from before it: an apply that stopped after
the module writes, or the option added in the builder); its rules-only
`REPLACE conditions` is never `in-sync` either, the runner applies it on its
next run, and `detail` says `special-event rules rewritten`. The bad-data bands
above still hold a region that carries one of these lines, and its ATTENTION
says which: the title carries the plan's summary (the words an apply's `detail`
would carry: `required: … on N roster(s)`, `module values on N dropdown(s)`,
`special-event options on N dropdown(s)`, `question 18 rules rewritten`,
`special-event rules rewritten`); a `REQUIRED roster` or module line is listed
under `Planned:` (`REQUIRED on N roster(s) with no other change`, `MODULE
values q…`); either warning sits under `Warnings:`, and its rules-only `REPLACE
conditions` is no `Planned:` line, so the warning is where to look for the
rewrite. The runner syncs the regional forms only: the
template and a disabled form are applied by hand (the sync's dry run and
`--apply`, Ryan's go). The next run is the next roster change, at the latest
the morning backstop, or one started from the Actions tab on Ryan's go. After
every apply the verify step also audits the form's names dictionary; a store
it could not read is a note in the log, not `applied-unverified`. An apply that
rewrote the rules (`REPLACE conditions`) or a module dropdown is also checked on
the served page (`form_status.py --rendered`, the check hand rollouts stop on):
a problem there reads `applied-with-problems`, an ATTENTION naming the form and
its `rendered page` line. The runner's next run does not repair such a
problem: its dry run plans from the form's definition, not the page, and plans
nothing for it (the region reads `in-sync`). Re-check the page with
`form_status.py --form … --roster … --rendered`; if the problem stays,
re-save the form in the Jotform builder and check again. The page can lag the
API by seconds, so a page that cannot be read or that shows problems is read
once more after a short wait and
the second read is judged; a page unreadable both times is a note in the log
(`note: served page of form … not read …`), not a failure. Problems the first
read showed stand when the re-read cannot be read (`note: … re-read failed …
judged on the first read`).

Once per run, after the regions, the runner also reads **Jotform's storage**
against the account's plan and logs the same `storage:` line `form_status.py`
prints ("Photos", step 7): upload space in all and submissions in the monthly
cycle, each judged on its own. A limit at 80 % or more is an ATTENTION naming
it ("Jotform upload space at NN% - the forms stop at 100%", or "Jotform
submissions this cycle at NN% …"), every morning until acted on; at 50 % the
line reads `warn` and nothing more. A read that fails is one log line,
`storage: could not be read (…)`, never a failed run.

The workflow fails visibly (GitHub emails the repository owner) on any
ATTENTION (exit 2) and on any failure (exit 1).

**SyncLog columns:** `when, trigger, region, mode, creates, updates, rules,
result, detail, run_url`. `when` is the run's start in the sheet's own time
zone (read from the sheet, like the Apps Script's timestamps). Rows written
before commit d9b4f6b reached the runner carry other clocks; the row's
`run_url` gives the true time (History: [plan](plans/2026-09-30-time-zones.md#from-the-runbook-moved-2026-10-09)). The log file and ATTENTION.md show the runner's clock with
its UTC offset. `mode` is
`dry-run` or `apply`; `result` is one of `in-sync`, `dry-run` (would apply), `applied`, `applied-with-problems`,
`applied-unverified`, `attention`, `skipped`, `failed`. `skipped` is a form
whose status is not `ENABLED` (`detail`: `form DISABLED`; nothing was run
against it, and the exit code is unaffected — "Disabling a regional form").
`detail` counts the roster
creates, updates, deletes and warnings, then the rosters retired and restored
(`…, 38 retired`), then names a Club-picker or
club-guard write when there is one (`…, update club picker`): such a
write is applied like a roster change. A rules rewrite the apply carries is
named last (`…, question 18 rules rewritten`, `…, special-event rules
rewritten`). The Partner-box hide (`HIDE partner
textbox`, "Club names two partners share") is neither counted nor named in
`detail`: it only ever rides along with a counted change, and the run's log
(the row's `run_url`, or `data/auto_sync/<stamp>.log`) shows the line. The Audit tab additionally gets
a `syncRequested … → HTTP 204` row every time the sheet sends the event.

**Switches:**

- Repository variable `AUTO_SYNC_APPLY`: normally `1`, so runs apply within the
  bands. `0` is the emergency off switch (every run is a dry run), set only by a
  rollback or an incident, which sets it back to `1` before it ends. A rollout
  never sets it: the merge is the rollout.
- Script Properties `SYNC_DISPATCH_REPO` / `SYNC_DISPATCH_TOKEN` unset = the
  sheet sends nothing (the daily run still happens).
- Manual runs from the Actions tab apply only when both `AUTO_SYNC_APPLY=1`
  and the "apply" input is ticked.

**First-time setup** (once, by the sheet's owner; done 2026-09-01 to 2026-09-12, BACKLOG
1a and 1b): the four steps as run are in the
[plan](plans/2026-09-01-auto-sync.md#from-the-runbook-moved-2026-10-09). The dispatch token's permissions
changed since: "New clubs' accounts, automatically", Setup, step 4.

**Rollback:** before every apply the runner snapshots the form and writes a
conditions-only file `backups/<form>/conditions-<stamp>.json` (that file —
no staff e-mails, no integration settings, no rosters — is what the workflow
keeps as an artifact for 30 days);
`python3 restore_conditions.py --form <id> --from conditions-<stamp>.json --apply`
puts the conditions back. It refuses a snapshot whose rules test a club the
Club picker does not offer today (one from before a form's same-name switch,
before a rename, or before a partner's rosters were retired): restored, those
clubs' rosters would never show — run the sync instead (a retirement is undone
by clearing the Partners cell, "Clubs that do not use Jotform"). Questions are
never deleted by the runner. To stop
the automation: `AUTO_SYNC_APPLY=0` (or clear the two Script Properties).

## Backup and restore (Jotform)

- **When:** before any live write to a form (the tools that write also snapshot on their own); a restore when a rules change must be undone.
- **Dry run:** `restore_conditions.py` without `--apply`: what the snapshot holds against the live form, and any refusal.
- **Apply:** `--apply`, Ryan's go.
- **Verify:** the restore re-reads the form: `RESTORED: N conditions on the server (matches snapshot)`.
- **Rollback:** the restore below, or Jotform's Revision History; a restore is undone with the snapshot it took first.

```bash
python3 backup_forms.py                       # every known form -> backups/<id>/{questions,properties}-<stamp>.json
python3 backup_forms.py --form <id>           # one form (2 API calls)
python3 restore_conditions.py --form <id>              # preview restoring the latest snapshot's conditions
python3 restore_conditions.py --form <id> --apply      # restore
```

Restores touch only the conditions; questions, emails and the Salesforce
integration are left alone. Jotform's own Revision History is the second
rollback path. `backups/` holds rosters and never enters git.

- `<stamp>` is to the second, `2026-10-09T153012` (`glow/backup.py`; to the
  minute until 2026-10-09), so a re-run within the minute never writes over the
  true "before". Every tool that snapshots uses this one stamp.
- `restore_conditions.py --apply` first snapshots the form as it is
  (`backups/<id>/*-<stamp>.json`, never over the `-latest` files, which may be the
  snapshot being restored) and prints the way back: `--from properties-<stamp>.json`.
- It refuses a snapshot without conditions, and one with a rule whose terms or
  action do not parse - `--force` does not override that. A snapshot whose rules
  test a club the Club picker no longer offers is refused too; there `--force`
  restores anyway ("Club names two partners share", Restoring conditions).

## The Club picker (mentors choose their club instead of typing it)

- **When:** a form without the picker (all five live forms have it).
- **Status:** on the template and all four regional forms since 2026-09-12, with leadership's approval ([plan](plans/2026-09-12-picker-rollout.md), [intent](intent/2026-09-01-club-picker.md)).
- **Dry run:** the `--club-picker` dry run below.
- **Apply:** its `--apply`, then the translations.
- **Verify:** `form_status.py` (`club picker: q<id>`, rules CLEAN) and the browser check below.
- **Rollback:** `restore_conditions.py` for the rules; in the builder, delete the Club dropdown and un-hide Club Name.
- **History:** [plan](plans/2026-09-12-picker-rollout.md#from-the-runbook-moved-2026-10-09).

A required **Club** dropdown in Jotform's searchable mode (type to filter,
on phones too) listing every club on the form; the roster rules key on it,
and a calculation copies the pick into the (now hidden) Club Name textbox,
question 5, which is what the Salesforce mapping reads — so `Account_Name__c`
receives the picked entry: the club's name, or `<club> - <partner>` for a
club whose name another partner's club shares ("Club names two partners
share"). Added once per form; from then on every
sync run keeps its option list and properties in the shape `PICKER_PROPS`
defines (`UPDATE club picker (N clubs: options, subLabel…)` in the plan).
The wording follows the training guide — label **Club Name**, sublabel
"Select your Club Name to see your roster." — and lives in `PICKER_PROPS`:
change it there, never in the builder (the sync reverts hand edits). The searchable component does let a
mentor pick several clubs (Jotform ignores `maxSelection` on dropdowns): the guard is "One club per submission" below.

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

## One club per submission (the club guard)

- **When:** a form with the Club picker and no guard; straight away after any APPLY FAILED (below).
- **Status:** live on all five forms since 2026-09-30 (template q482, U.S q445, Latin America q453, Asia q456, Africa q462; [Result](plans/2026-09-29-club-guard.md#result-2026-09-30-with-ryans-go)).
- **Dry run:** `sync_attendance_form.py … --club-guard` (the rollout, in the plan).
- **Apply:** the same with `--apply`, per form, Ryan's go.
- **Verify:** `form_status.py` (`club guard: q<id> (N clubs)`, rules CLEAN) and `--rendered`.
- **Rollback:** per form, below.

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
by one character). The guard leaves the Contact_IDs (q18) sum as it is: with
Submit shown, only one roster is visible. Where that sum sits and what it
lists are covered in "The names list sent to Salesforce" below.

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
spelling fix below.

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

**Rollout** (once per form; done on all five forms 2026-09-30): backup, the translation
audit, the `--club-guard` dry run and `--apply`, a second dry run, `form_status.py
--rendered` (a hard stop on the template: `N options, N with data-calcvalue = value`), the
translations and the browser checks, with the runner paused - as run, with what each
form's dry run showed, in the [plan](plans/2026-09-29-club-guard.md#from-the-runbook-moved-2026-10-09).

Rollback, per form. The guard is on `main`, so a form rolled back alone
disagrees with it: this rollback stops the runner with the emergency switch
from the first step to the last. While the `clubGuard` element exists, any
apply regenerates the guard rules, so the element goes before the switch goes
back to `1`.

1. The emergency switch, `AUTO_SYNC_APPLY=0` (Ryan's go), then
   `python3 backup_forms.py --form <id>`.
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
   none`. Then `AUTO_SYNC_APPLY=1` (Ryan's go), which ends the emergency stop:
   `main` and the form agree again.

Do not revert the merge while any Club picker carries `calcValues`: clear
them first (step 4) and re-read to confirm. The old code would keep the
stale `calcValues` and send the neighbouring club's name to question 5.

## The names list sent to Salesforce

- **When:** the sync warns that question 18 is calculated the old way, or plans `REQUIRED roster` lines; `form_status` reports the rule order, the operand or a roster not required.
- **Status:** live on all five forms since 2026-10-02 02:04 UTC, the template since 2026-10-01 16:37 UTC ([Result](plans/2026-09-30-contact-ids.md#result-2026-10-0102-with-ryans-go-you-have-my-go-push-things)).
- **Dry run:** the sync's dry run (the manual loop).
- **Apply:** the merge: the runner applies it to every enabled regional form on its next run; the template and a disabled form are applied by hand (the sync's `--apply`, Ryan's go).
- **Verify:** `form_status.py --rendered`: `question 18: rule 1 of N, … operand: yes`, every roster required.
- **Rollback:** the constants, below.

Question 18 (Contact_IDs) is the list of girls Salesforce stores as present:
one calculation over every roster, hidden rosters ignored, so only the shown
club's ticks arrive. In September it went wrong on part of the submissions
(no girl ticked, ticks with an empty question 18, another club's girls: [History](plans/2026-09-30-contact-ids.md#from-the-runbook-moved-2026-10-09)). Two checks close
this on the form, both generated by the sync and switched by constants in
`glow/sync.py`:

- **Question 18 is recalculated after the rosters change**
  (`CONTACT_IDS_FIRST`, `CONTACT_IDS_PICKER_OPERAND`). Jotform walks a field's
  rules last to first, and showing or hiding a roster never re-runs a
  calculation. With the sum after the roster rules, a change of club computed
  it before the rosters were shown or hidden. On a form with the Club picker
  the sum is now rule 0, so it runs after them. Its ids are minted first. The
  picker is also one of its operands, never part of its equation. The order is
  the fix: it also covers a page the browser restores (Back). The operand only
  adds one more trigger, and the operand alone did not fix the restored page.
  A form without the picker keeps its rules byte for byte.
- **At least one girl** (`ROSTERS_REQUIRED`): every roster carries Jotform's
  own `required` flag. Jotform checks only the roster that is shown: a roster
  a rule hides is skipped at submit. One ticked box satisfies it, and the error
  is Jotform's own "This field is required.". It is translated only where the
  form's translation store has the `base` entry for that text: read
  2026-10-01, U.S only (every language there but Odia). On the template,
  Africa, Asia and Latin America it is English in every language, as the Club
  picker's own required message already is (BACKLOG 57). The flag
  is written on every roster the sync creates. A roster that lacks it gets it
  in the same write as an options update, `UPDATE roster '<club>' (q…, N girls;
  required: Yes)`, or else on its own, `REQUIRED roster '<club>' (q…: Yes)`.

What the tools say:

- The sync, when the live rules are the old way, warns
  `! question 18 (Contact_IDs) is not recalculated after the rosters change: …`
  and plans one `REPLACE conditions` (`conditions: N-1 kept, 1 new, 1 dropped`).
- `tools/form_status.py` reports a form NOT CLEAN when question 18's rule
  comes after a roster rule, when the picker is not one of its operands, when
  its equation is not exactly one `{qid}` per roster, when a roster rule tests
  a field that question 18's rule does not test (a Partner-box rule from
  before the same-name switch: none live), or when a roster is not required.
  Each expectation follows the constants, so a constant turned off and applied
  is clean. Its report line reads `question 18: rule 1 of N, the Club picker an
  operand: yes   rosters required: M of M`.
- `form_status.py --rendered` also reads the public page. It checks that
  question 18 comes before the roster rules in `JotForm.setConditions`, that
  its `JotForm.setCalculations` entry lists the picker, and that every roster's
  boxes carry `validate[required]`. It also prints the runtime build, all as
  counts.
- The runner (`tools/auto_sync.py`) applies both like a roster change, within
  the bands (DECISIONS 2026-10-14): a region whose sync warns as above is never
  `in-sync`; its rules-only `REPLACE conditions` is applied on the next run and
  the SyncLog `detail` says `question 18 rules rewritten`. `REQUIRED roster`
  lines are applied the same way and never count against `--max-updates` (they
  come from the constant, not the export). It also applies an `UPDATE roster …
  ; required: Yes` and creates rosters with the flag.

**Rollout** (once per form; done on all five forms 2026-10-01/02): the template first, the
merge, then U.S, Latin America, Asia and Africa, each with a backup, the dry run, `--apply`,
a second dry run, `form_status.py --rendered` (a hard stop) and the browser checks (a
console line that prints counts only), the runner paused throughout - as run, with each
form's dry run, in the [plan](plans/2026-09-30-contact-ids.md#from-the-runbook-moved-2026-10-09). A regional form back on
the old rule order (an old snapshot restored, a constant turned off and on again) is rewritten
by the runner on its next run, the SyncLog row `applied` with `question 18 rules rewritten`;
the template and a disabled form are applied by hand: the sync's dry run, `--apply`, then
`form_status.py --rendered`.

**Rollback** (generated: merging the constants-off commit is the rollback): set
`CONTACT_IDS_FIRST`, `CONTACT_IDS_PICKER_OPERAND` and `ROSTERS_REQUIRED` in
`glow/sync.py` to `False` on a ticket branch. The dry run then plans `REPLACE
conditions` (`1 new, 1 dropped`) and `REQUIRED roster '<club>' (q…: No)` for
every roster, with no warning; applied, `form_status` is CLEAN on the old
shape. One constant alone works the same way, for example the required flag
alone if a mentor cannot submit. Merging the constants-off commit to `main` is
the rollback for every enabled regional form: the runner runs `main`'s
constants and puts the old shape back on its next run (the `REQUIRED roster …
No` lines are a change to it, and the rules rewrite rides along in the same
apply). The rule-order constants alone give a rules-only plan, which waits for
each region's next roster change (a difference in the rules alone is not a
change to the runner). To roll a regional form back at once, apply it from
`main` once the commit is in (backup, the sync's dry run, `--apply`, Ryan's
go): no stop is needed, because `main` agrees. The template and a disabled form
are applied by hand the same way (`--disabled-ok` on a disabled form).

One form alone cannot stay rolled back while `main` disagrees with it: the
runner rolls it forward again on its next run (the sync warns as above and the
runner applies the rewrite). If that is ever needed (a mentor cannot submit on
one form), first stop the runner with the emergency switch, `AUTO_SYNC_APPLY=0`
(Ryan's go); then apply that form's rollback (the constants-off branch's dry
run and `--apply`, or the second path below); and switch it back,
`AUTO_SYNC_APPLY=1`, when `main` and the forms agree. The second path is
`restore_conditions.py --form <id> --from properties-<stamp>.json` from the
backup. It brings the old rules back and says so ("the snapshot calculates
question 18 … the old way"), and the form then reads NOT CLEAN. It does not
touch the required flags. Neither path touches the picker, the guard, question
5 or the integration.

Left open: Jotform never recalculates at submit. The order is Jotform's
internal behaviour, not a contract (`--rendered` prints the build). Back-button
restores on iOS Safari and Firefox are untested. **Two clubs picked, then the
form's own language switcher**: the switcher keeps one club picked without
an event (the one higher in the picker's list, not the one picked first), so
the guard lifts while both rosters stay shown with their ticks (the old order
and the new alike; BACKLOG 56). With required rosters Submit then goes
through only if every shown roster has a tick. Ticks in one roster only are
refused, with the required message on the other roster, which may be the one
she meant. Ticks in both still go through, all under the club kept: the daily
question-18 comparison stays the alarm. Support: a mentor told "required" on
a club she did not pick clears the picker and picks her club again; she never
ticks a girl of a club she does not hold.

## The names dictionary and the module values

- **When:** `form_status` reports a names dictionary that alters a roster option, or module values out of line; a module added or reordered in the builder.
- **Status:** fixes 1 and 4 of the plan, live on all five forms since 2026-10-06 11:22 UTC ([Result](plans/2026-10-02-names-and-modules.md#result-2026-10-06-with-ryans-go)).
- **Dry run:** `tools/fix_name_translations.py --form <id>`; the sync's dry run for the module lines.
- **Apply:** names: the tool with `--apply`, one form per run, Ryan's go. Modules: generated, so the merge is the apply: the runner applies it to every enabled regional form on its next run; the template and a disabled form are applied by hand.
- **Verify:** `form_status.py --rendered`: names 0 altered, module values aligned.
- **Rollback:** names `--restore`, modules `MODULE_CALC_VALUES = False` (below).

Salesforce stores what question 18 (the girls' names) and
question 98 (`module_id`) say, and finds a girl by her exact name. Two things
on the forms changed that text after the mentor ticked it:

- **The names dictionary.** Each form's translation store (`base`, `en` and
  one dictionary per offered language, cloned from the template) is built
  into a lookup in the browser, and the calculation that fills question 18
  passes every ticked name through it (the box's `data-calcvalue`, else the
  lookup's answer as it is; the value only on a page without the lookup).
  Building the lookup collapses every whitespace run
  in a key, so a stale entry that spells a girl's name with a double space, a
  tab or a no-break space lands on her exact name and replaces it: 55 roster
  options read 2026-10-02 (Africa 49, Asia 5, Latin America 1, U.S 0; 29
  clubs), each a second Contact in Salesforce on the girl's first live
  submission. `glow/translation_lookup.py` rebuilds the lookup exactly as
  Jotform's `formTranslation.v2.js` does (both runtime builds) and is what the
  tool and the audits below run.
- **The module.** The module dropdowns (q14, q92, q93) had no `calcValues`, so
  question 98 copied the option's visible text, which a browser's "Translate
  page" rewrites (30 of Latin America's 111 September submissions sent a
  Spanish module). The sync now gives each its own options as `calcValues`,
  after the empty slot of a single-select's "Please Select" (the year
  dropdown's `|1|2|3` layout), and keeps them in step on every apply
  (`glow/sync.py` `MODULE_CALC_VALUES`). Question 98 then copies the
  `data-calcvalue`, which page translation does not touch.

The September back-fill sent the exact roster text and the canonical module,
so once both fixes are live the live flow and the back-filled data agree.

**`tools/fix_name_translations.py`** (dry run by default) reads the roster
options of all five forms (a girl who moves region, or a namesake, must not
bring an entry back) and each form's store, and removes from `base` and `en`
exactly the entries whose lookup alters one of them, round after round until
none does (removing one can uncover an older spelling of the same name).
Removal, not correction: a name with no entry is the normal state and comes
out exact. It prints counts and club names, never a girl's name:

```
== Africa 262382821971058
   store: base 4416, en 4424, 11 other language(s)
   altered today: 49 of this form's 4264 roster options, in 23 club(s); its dictionary alters 55 option text(s) of the five forms (en 55; on template 55, U.S 0, Latin America 1, Asia 5, Africa 49)
   clubs: …
   keys to remove: 55 (base 55, en 55) - only the entries behind those alterations
   after the removal (emulated, 12 language(s), both runtime builds): 0 option(s) altered
```

Every form's store holds the same 55 keys (they were cloned), so each form
loses 55 entries in `base` and `en`, the U.S store included. With `--form <id>
--apply` (one form per run) it saves the whole store to
`backups/translations/<id>-<stamp>-before.json` (mode 600: it holds every
girl's name), POSTs `base` and `en` without those keys (no other language is
posted, CLAUDE.md rule 9), re-reads the store and compares every entry
(`re-read: APPLIED`), audits the re-read store (0 altered), then reads the
public page and counts the removed keys it still embeds (`public page: 0
removed keys still served`). If some are still served after three reads 20 s
apart, it makes ONE more write, the form's `pagetitle` posted back unchanged
(the dry run prints it), which makes Jotform re-render the page, and reads it
again. When the page cannot be shown to serve the change (it still lags, or the
re-render's read or write fails), the run ends with "The store is fixed but the
public page could not be shown to serve it": the store IS written, and a second
run only says `nothing to remove` - re-save the form in the builder if the page
still lags, then `tools/form_status.py --form <id> --roster data/roster_<date>.csv
--rendered`. A lost or
non-JSON answer to the POST is re-read and reported as
`UNCHANGED` (nothing written: run again), `APPLIED` or `PARTIAL` (restore,
below). It refuses, writing nothing: a store without `base` or `en`, with
fewer than 1,000 entries in either (a truncated read), or with an entry that
is not text; a key to remove that another language translates, or an
alteration another language's entry makes; more than 300 keys; anything still
altered after the removal; `--apply` without exactly one `--form`. A second
dry run on a fixed form says `nothing to remove`.

**The sync** plans one line per module dropdown without the values:
`UPDATE module dropdown (q14, year 1: calcValues = its 5 options)` (q92: 7,
q93: 8; the same on all five forms, read 2026-10-02). After the apply the next
dry run has nothing to say about them. A module added or reordered in the
builder later makes the line come back: the runner realigns a regional form on
its next run; the template and a disabled form are realigned by hand.

**`tools/form_status.py`** reports a form NOT CLEAN when a module dropdown's
`calcValues` are missing or out of line with its options (`module values: q14
aligned (5 options), …`), and when the form's own dictionary alters any
roster option in any language its store holds (`names dictionary: 0 of 4264
roster options altered (12 language(s) checked)`; one GET more per form).
`--rendered` checks the served page as well: each module option's
`data-calcvalue` equals its value, and the store the page embeds alters none
of the roster boxes it serves. A store that cannot be read is reported, not
guessed (`names dictionary: not checked (…)`), and the runner's verify step
logs it as a note. A stale entry made in the builder later is flagged after
the next apply (or by hand), not prevented.

**The module chain's shape** is pinned by the same report
([plan](plans/2026-10-06-module-selection.md); nothing on the forms changed
for it): `module shape: year q94 single-select required; modules q14/q92/q93
single-select required; sessions q15/q95/q96/q97 single-select required;
clearFieldOnHide disable`. A form is NOT CLEAN when the year, a module or a
session dropdown is a multi-select (a mentor could send two modules, and
question 98 would run them together), is not required (a blank module reaches
Salesforce), is missing, or when the year dropdown is hidden; and when the
form-level `clearFieldOnHide` is anything but `disable`: `dontClear` means a
module dropdown hidden by the Year rule would keep its answer at submit (two
modules, or last year's, in question 98), `enable` was rejected 2026-09-30
(the loop limit drops to 3), and an unset or unknown value is a runtime
behaviour nobody has read, so hidden answers are not treated as cleared.
`--rendered` reads the served page's `JotForm.clearFieldOnHide` and refuses a
module `<select>` served `multiple`. The fix is the builder (the dropdown's
own settings, or the form's setting that clears hidden field values), then
re-run the report - never a sync apply: the sync writes none of it (its one
properties write carries `conditions` alone).

**The runner applies a module line like a roster change** (DECISIONS
2026-10-14; the lines never count against `--max-updates`): the runner applies
it to every enabled regional form on its next run; the template and a disabled
form are applied by hand. Since the rollout a module line means a module
dropdown was edited in the builder: the next run realigns the regional form
(the SyncLog `detail` says `module values on N dropdown(s)`), and that form's
dry run is worth reading for what the edit was. The names tool is never run by
the runner.

**Rollout** (once per form; done on all five forms 2026-10-06): the template first, the
merge, then the regional forms smallest first - per form a backup, the names tool's dry
run and `--apply`, the sync's dry run and `--apply` (the three module lines), `form_status
--rendered` CLEAN and the browser checks, the runner paused throughout - as run, with what
each form's dry run showed, in the [plan](plans/2026-10-02-names-and-modules.md#from-the-runbook-moved-2026-10-09). A
dictionary that alters a name again: the names tool on that form, dry run first.

**Rollback**:

- Names (per form): `python3 tools/fix_name_translations.py --form <id> --restore
  backups/translations/<id>-<stamp>-before.json` (a dry run: the entries it
  puts back, per dictionary), then the same with `--apply`. It puts back every
  `base`/`en` entry of the saved store that the form no longer has, in the
  saved order; entries changed or added since are kept. It saves the store as
  it is first, re-reads and compares, and reads the page. Rolling back
  re-opens the defect: only if something else broke.
- Modules (generated): set `MODULE_CALC_VALUES = False` in `glow/sync.py` on
  a ticket branch. The sync's dry run then plans `UPDATE module dropdown (q14,
  year 1: calcValues cleared)` for each dropdown that carries them; applied,
  `form_status` is CLEAN under the constant. Merging the constants-off commit
  is the rollback: the runner applies those lines as it applies the others, so
  it rolls every enabled regional form back on its next run. To roll one back
  at once, apply it from `main` once the commit is in: no stop is needed,
  because `main` agrees. The template and a disabled form are applied by hand.
  One form alone cannot stay rolled back while `main` disagrees (the runner
  rolls it forward): as with question 18, that needs the emergency switch
  ("The names list sent to Salesforce", Rollback). The second path is the
  questions file `backup_forms.py` wrote (`calcValues` was `""` on every module
  dropdown before the rollout).

Neither touches the rosters, the rules, question 5 or the integration.

**The batches Salesforce held with a translated module** were corrected once, on 2026-10-07,
by `tools/fix_module_values.py` (6 batches and their 43 rows, all Latin America's; ledger
`data/module_fix_2026-10/ledger.csv`; [Result](plans/2026-10-06-module-selection.md#result)). Its
dry run is read-only and stays a check; its undo works until the tool is retired (end of
October). Both need `JOTFORM_API_KEY`, the CLI login and VPN off ("Credentials"):

```bash
python3 tools/fix_module_values.py --vpn-off                       # dry run: the pairs, the UNMATCHED, "would write: B batches, M rows"
python3 tools/fix_module_values.py --undo data/module_fix_2026-10/ledger.csv --vpn-off --apply   # rollback: `old` back by id
```

The procedure as run and what the dry run prints: [plan](plans/2026-10-06-module-selection.md#from-the-runbook-moved-2026-10-09).

## Special events

- **When:** staff add a type of ad-hoc session or retire one; `form_status` reports a special event missing, twice or misspelled, a session rule for one, or the session bridge missing or out of place.
- **Status:** live on all five forms since 2026-10-13 ([plan and Result](plans/2026-10-13-special-events.md#result-2026-10-13-ryans-go-for-each-write)); the types are "Welcome Session", live on all five forms since 2026-10-13, and "IDG Celebrations", live on all five forms since 2026-10-14 ([plan and Result](plans/2026-10-14-idg-celebrations.md#result); still open: staff telling mentors, and the first IDG Celebrations batch in Salesforce to read).
- **Dry run:** the sync's dry run, per form: one module line per dropdown. On a form whose rules are stale (the rollout of 2026-10-13), also one `REPLACE conditions`; for a type added after that, `(conditions unchanged - skipping the rewrite)`, unless roster changes come with it (then `REPLACE conditions` too, as on the template, which the runner never syncs).
- **Apply:** the template first, by hand from the branch (its `--apply`, Ryan's go, then the browser checks); then the merge: the runner applies it to every enabled regional form on its next run; the template and a disabled form are applied by hand.
- **Verify:** `form_status.py --rendered` CLEAN; on the template also the browser checks below.
- **Rollback:** the type's merge reverted first, then the option deleted in the builder; `restore_conditions.py --from` the snapshot only when the rules must come off at once (below).

A special event is an ad-hoc session outside the curriculum (Ryan: "Welcome Session"
on 2026-10-13, "IDG Celebrations" on 2026-10-14). It is one more option of every year's module
dropdown (q14, q92, q93), `Special Event - <type>`, as the electives are `Elective - <name>`
(`glow/sync.py` `SPECIAL_EVENT_PREFIX`, `SPECIAL_EVENTS`). An event shows no session dropdown, so Salesforce
receives `Module__c` = the option's text, `Module_Week__c` blank and `Module_Year__c` the year;
nothing changes in Salesforce. One batch per club and date still holds: a Welcome Session on a
day the club also holds a curriculum session is refused as a duplicate, whichever arrives
second, so mentors submit one per day (DECISIONS 2026-10-13).

The sync owns the event options. It appends a missing one after the curriculum options, in
`SPECIAL_EVENTS` order, in the same write as the dropdown's `calcValues`:
`UPDATE module dropdown (q14, year 1: 1 event option(s) added (Special Event - Welcome Session); calcValues = its 6 options)`
(q92: 8, q93: 9 on the template, read 2026-10-13). It never removes, renames or reorders an
option: one that starts with the prefix but is no type of `SPECIAL_EVENTS` is warned about and
left alone (`! module dropdown q14 (year 1) lists 'Special Event - …', which is no special event
of glow/sync.py SPECIAL_EVENTS: left as it is`), and one in another case or spacing counts as
present (warned, never added twice). The rules come from the options the form will have, so the
dry run shows the whole result: every curriculum module of every year has its own session rule
(year 1: the 8-session dropdown; years 2 and 3: `SESSION_OVERRIDES`), an event has none, and
the **session bridge** heads the cascade. The bridge is one calculation into question 100 over
the session dropdowns shown (`{15}{95}{96}{97}`, hidden fields ignored), tested on and listing as
operands the year, module and session dropdowns (`WEEK_BRIDGE_FIELDS`). Jotform walks a field's
rules last to first, so in each of those fields' walks it runs after the session dropdowns are
shown or hidden: a mentor who picked a session and then switched to the event leaves question
100 blank, and one who switches back gets the session again. The four copy rules stay. On the
template the first apply plans `conditions: 394 kept, 6 new, 1 dropped` (the bridge, five year-1
rules; the year-1 rule on the year alone goes).

**The runner applies an event line like a roster change** (DECISIONS 2026-10-14; the line never
counts against `--max-updates`): once a type is merged, the runner applies it to every enabled
regional form on its next run, the SyncLog `detail` naming it (`…, module values on 3
dropdown(s), special-event options on 3 dropdown(s)`); the template and a disabled form are
applied by hand. Nor does it read a form as `in-sync` whose options are there but whose rules
are not (an apply that stopped after the three module writes, or the option added in the
builder): the sync warns `! the form's rules let a special event show or send a session: …` (a
session rule on the year alone or for an event, the bridge missing, doubled, out of shape or
out of place) and plans only `REPLACE conditions`, which the runner applies on its next run
(`detail`: `special-event rules rewritten`). A line that writes the options alone says so:
`calcValues unchanged)` (the values were already right) or `calcValues none)`
(`MODULE_CALC_VALUES` off).

**`tools/form_status.py`** reports a form NOT CLEAN until it carries each type once per module
dropdown in the exact spelling, no rule shows a session dropdown for an event or on the year
alone, and the bridge is there once, in its shape, before every session rule and every copy
into question 100. Before the apply each of these reads, on an enabled regional form, `awaiting
the runner's next run (or the sync's apply by hand now) (RUNBOOK "Special events")`, and on the
template or a disabled form, `awaiting a sync apply by hand, template first (RUNBOOK "Special
events")`. The report line reads `special events: 2
type(s) on 3 of 3 module dropdowns; session bridge rule N of M, S session rule(s), 0 on no
curriculum module`.
`--rendered` also checks that each module select serves every event once with its
`data-calcvalue`, and that the page's bridge comes before the session rules and keeps its
operands in `JotForm.setCalculations`.

**Add a type** (one line; the template before the land, then the merge is the rollout):

1. Add it to `SPECIAL_EVENTS` in `glow/sync.py` on the ticket branch, `make check`. Translations:
   none today. No form's store translates a module option (read 2026-10-13: only `base`/`en` hold
   them; Swahili one of 18), so an event option is English in every language as the modules are.
   If module options ever get translations, the event gets them too ("Translations").
2. The template, before the land, from the ticket's worktree (the runner never syncs it):
   `backup_forms.py --form 262352490535154`, the sync's dry run (the three module lines;
   `REPLACE conditions` only with roster changes or stale rules, else `(conditions unchanged -
   skipping the rewrite)`), Ryan's go, `--apply`, `form_status.py --rendered` CLEAN, then the
   browser checks below.
3. Land it (`/land-checks`, `/harness:land`): the land is the rollout. The runner adds the
   option to every enabled regional form on its next run: the next roster change, the morning
   backstop, or a run from the Actions tab on Ryan's go. Read each region's SyncLog row
   (`applied`, its `detail` naming `special-event options on 3 dropdown(s)`) and confirm
   `form_status.py --rendered` CLEAN on each of those forms.
4. A disabled form (today the U.S form), by hand on the same day, from `main`: its backup, the
   sync's dry run, Ryan's go, `--apply --disabled-ok`, then `form_status.py` CLEAN.
5. Staff tell mentors: the new option, and one submission per club per day.

**Retire a type**: take it out of `SPECIAL_EVENTS` on a ticket branch and merge that first (else
the next apply adds it back), then delete the option in the builder on each form's three module
dropdowns. The next sync dry run plans one module line per dropdown (its `calcValues`
realigned), and the runner applies the realigned `calcValues` to every enabled regional form on
its next run. The template and a disabled form are applied by hand (the backup, the sync's dry
run, Ryan's go, `--apply`, with `--disabled-ok` on a disabled form). Until the option is
deleted, the sync warns and `form_status` reports it. Salesforce history stays: the batches keep their `Module__c`, and a report can still
select events by `Module__c` starting with `Special Event - `.

**Browser checks** (the template, before any regional form; nothing submitted until the last
step). The session bridge is a reading of Jotform's runtime (build `f4bbef18bb2`), not yet seen
working:

- In each year the event is the module dropdown's last option, and picking it shows no session
  dropdown.
- Pick a curriculum module and a session, then switch to the event: question 100 must be blank.
  In the browser console, `document.getElementById('input_100').value` returns `""`. Switch back
  to the module: the session still shows, and the same check returns its number.
- Change the year after picking a session: question 100 is blank until a session of the new
  year's module shows.
- One test submission by the plan's recipe (Rollout, step 2): a club and date that already have
  a `Success` batch. It arrives `Failed` "Duplicate" with `Module__c` = the event's text and
  `Module_Week__c` blank (read back by SOQL, counts and fields only); then delete the submission.

**Rollback**: revert the type's merge first (a revert on a ticket branch, landed like any
change): while the type is on `main`, the next apply adds the option back. Then delete the event
option in the builder on each form's three module dropdowns (tooling never deletes a question or
an option). The runner realigns `calcValues` on every enabled regional form on its next run; the
template and a disabled form are applied by hand (the sync's dry run, Ryan's go, `--apply`, with
`--disabled-ok` on a disabled form).

When the bridge rules must come off at once (a mentor cannot submit): first the emergency
switch, `AUTO_SYNC_APPLY=0` (Ryan's go), since the runner would roll a form forward while `main`
disagrees with it; then `restore_conditions.py --form <id> --from` the conditions snapshot of
the apply, per form; then the revert, landed; then `AUTO_SYNC_APPLY=1` once `main` and the forms
agree.

## Translations

- **When:** a label lacks translations (`--audit`), a new English string, a new language, a clone.
- **Dry run:** each command without `--apply`.
- **Apply:** with `--apply`, Ryan's go.
- **Verify:** `--audit` again; `switcher_flags.py --check-page`.
- **Rollback:** each write saves the form's whole store before its POST, to `backups/translations/<form>-<stamp>-before.json` (mode 600, never over an earlier file); without that file `glow/translations.py` sends nothing. Since 2026-10-09 that includes `add_language.py` and `restore_translations.py`, which used to POST without it.

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
(details: `.claude/skills/jotform-api/SKILL.md`). The `base`/`en` entries also
decide what question 18 sends for a ticked girl: `tools/fix_name_translations.py`
removes the stale spellings that alter a name, and `form_status.py` flags any
("The names dictionary and the module values"). Saved stores
(`backups/translations/`) are mode 600.

## Links above Submit (problem report, Club Roster Form)

- **When:** placing, re-checking or removing a link; a Google Form whose public link changed.
- **Status:** the problem link (q443) is on all five forms; the Club Roster Form link is built, merged 2026-09-29 and waits for Ryan's go (BACKLOG 46; [plan](plans/2026-09-28-roster-form-link.md#result)).
- **Dry run:** `python3 tools/add_feedback_link.py --link roster`.
- **Apply:** its `--apply`, then `tools/add_translations.py --apply`.
- **Verify:** the tool's re-read after the write; `form_status` (`layout:`).
- **Rollback:** `--remove --apply`, the questions snapshot, or Revision History.

Two text elements sit directly above the Submit button of every attendance
form, each one linked sentence in a grey box, found by its unique name
(`glow/links.py` holds the table; the public Google Form URLs there are pinned
by a test to the table in "The forms"):

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

- **When:** `form_status` says a roster renders below the first link or Submit (its `layout:` line, NOT CLEAN), or a new regional form.
- **Status:** repaired on all five forms 2026-09-30 ([Result](plans/2026-09-29-rosters-above-submit.md#result-2026-09-30-with-ryans-go)).
- **Rollback:** `--undo <stamp>`, below.

A mentor sees her girls' names where her club's roster renders, so every
roster must render above the links and the Submit button. The sync gives a new
roster the order of the last roster above the first link (its plan says `New
rosters go at order N, above …`), and `form_status` checks the layout on every
run, as the runner's verify does. The one-time repair, `tools/fix_roster_order.py`,
moves the links, Submit and the hidden bridge fields below the last roster. For
a relapse or a new form, its dry run, the template first, and its rollback:

```bash
python3 tools/fix_roster_order.py                                        # dry run: the template + 4 regionals
python3 tools/fix_roster_order.py --form 262352490535154 --apply         # the template first; open its page
python3 tools/fix_roster_order.py --form <id> --undo <stamp>             # the rollback (dry run; --apply writes)
```

The full procedure - the runner paused, what the tool refuses, how it stops and
what `--undo` can still restore: [plan](plans/2026-09-29-rosters-above-submit.md#from-the-runbook-moved-2026-10-09).

## Header logo

- **When:** the logo's first upload, or a new logo file.
- **Status:** built; the upload in the builder is Ryan's ([plan](plans/2026-09-24-header-logo.md#result)).
- **Dry run:** `tools/update_static_fields.py --image-src <URL>`.
- **Apply:** the same with `--apply`, after `backup_forms.py`.
- **Verify:** the dry run again; the public page.
- **Rollback:** the `src`/`width`/`height` of the questions snapshot, or Revision History.

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

## Photos

- **When:** setting up the Google Drive copy (once per form, steps 1-5), copies that stop (step 6), the storage line at `warn` or `!!` (step 7).
- **Status:** the plan is accepted (2026-10-06); the Drive set-up is Ryan's, in the builder, and the placeholders below are filled when it is done ([plan](plans/2026-10-06-photos-to-drive.md)).
- **Verify:** `tools/integration_status.py` and `form_status.py`, as each step says.
- **Rollback:** *Rollback*, at the end.

**Photos.** Since 2026-10-01 no attendance photo goes to Salesforce (the CEO's decision: the
files there were deleted that day and the four regional forms' mapping lost its upload row; the
template follows in step 1). Since <date> the photos are copied by Jotform's Google Drive
integration into the My Drive of <role account>, folder `Attendance photos - <Region>`, one
subfolder per submission named `<Club Name> <Attendance Date>`, uploaded files only, no PDF
(the PDF renders every ticked girl's name). The photo stays required on the forms. The photos
before <date> (677 by 2026-10-06) are in Jotform only, behind its login. Sharing: the owner and
<named list>. Retention: <CEO's decision, or "not yet decided: nothing is deleted">.

`python3 tools/integration_status.py` reads every form's integration: `ok (one action, 8
fields, Account_Name__c from q5, no upload)` is right, a mapped photo reads `NOT RIGHT: the
upload field is ['19'], not []`, and `other integrations:` lists the other blocks the form
carries - the Google Drive block's key once step 2 is done (whether the API shows the block at
all is unverified until then; `none` on every form on 2026-10-06).

*Setting it up (Ryan, in the builder; the API cannot; template first). Every builder save is a
live write to a form, so each one follows the ritual: a quiet moment with no other rollout on
the forms, a backup before, a re-read and compare after. The `/properties` snapshot
`backup_forms.py` writes holds `integrations`, `emails` and `conditions`, so the compare is a
plain `diff` of the snapshot before and the one after.*

1. **Template, Salesforce first**. Before: `python3 backup_forms.py` (**all** forms, not just the
   template: a change to the connected account propagates to every form, see below; note the
   stamp it prints). Then Settings → Integrations → Salesforce → the existing action (create
   `Attendance_Batch`) → remove the file upload (Group Photo) → save. **Edit the action; never
   remove the connected Salesforce account - that detaches the integration from all ten forms
   (2026-09-30).** After: `python3 backup_forms.py --form 262352490535154` and
   `diff backups/262352490535154/properties-<before>.json backups/262352490535154/properties-<after>.json`
   → the only hunks are inside `integrations` (the upload row gone); `emails`, `conditions`,
   `clearFieldOnHide` byte-identical; `python3 backup_forms.py` again for the other four and
   the same diff on each → empty. Then `python3 tools/integration_status.py` → every live form
   `ok (one action, 8 fields, Account_Name__c from q5, no upload)`, `integration: ok`. Until
   this step the template reads `NOT RIGHT: the upload field is ['19'], not []`.
2. **Template, Google Drive**. Before: `python3 backup_forms.py --form 262352490535154`. Then
   Settings → Integrations → Google Drive → Authorize → log in as the role account (never your
   own) → Folder Name `Attendance photos - Template` → Create Subfolders for Submissions ON,
   name = the "Club Name" field that is **question 5** (the hidden text field; the builder shows
   the Club picker under the same label - prefer the hidden one; if only the picker is offered,
   use it and say so in the plan's Result), a space, then "Attendance Date" → Send Uploaded Files
   ON → **Send Submission PDFs OFF** → Save. After: `backup_forms.py --form 262352490535154`
   and the diff → hunks inside `integrations` only (a block added, or nothing visible: see the
   next line), nothing else changed. Then
   `python3 tools/integration_status.py --form 262352490535154` → the `other integrations:`
   line names the Drive block, or says none (then the API cannot see it; the Drive check below
   is by eye).
3. **One test submission on the template, arranged to change nothing in Salesforce.** A
   template submission goes through the Salesforce integration like any other and is a real
   batch for a real club ([contact-ids plan](plans/2026-09-30-contact-ids.md), build notes: "a
   delivered one is a real batch for a real club"). The processor refuses a second batch for a
   club and date that already has a Success batch, *before* it reads any name
   (`processBatch` → `resolveClubAccount` → `isDuplicateBatch` → return, the deployed
   `AttendanceBatchProcessor.cls` under `data/sf_processor_2026-10-02/after/`): such a batch is
   Failed `Duplicate: …` with no attendance row and no Contact created. `resolveClubAccount`
   runs first, though, and **creates a partner-less Club account when question 5 matches no
   Account name** (the BACKLOG 27 path, seen twice on 2026-10-03) - so the club must be one
   whose Account name is plain, never one of the seven `<club> - <partner>` names. Mentors
   submit late (19 of the 27 duplicates since 10-01 were September dates re-sent in October) and
   a Success batch dated today is the exception, so the query is a window, not a day - read-only
   SOQL: `SELECT Account_Name__c, Attendance_Date__c FROM Attendance_Batch__c WHERE
   Processing_Status__c = 'Success' AND Attendance_Date__c = LAST_N_DAYS:3 ORDER BY
   Attendance_Date__c DESC LIMIT 5`; take the newest club + date pair whose name has no
   ` - <partner>` suffix; **never a free date**. Also read, before the submission,
   `SELECT COUNT() FROM Account WHERE RecordType.DeveloperName = 'Club' AND ParentId = null`
   (2 on 2026-10-06: the two pilots). On the template pick that club and that date, tick one
   girl (the roster is required), type your own address as the Partner Coordinator Email, and
   upload a **neutral image with nobody in it**. Open the mentor link
   (`https://form.jotform.com/262352490535154`), not the builder's preview (whether a preview
   submission runs the integrations is unverified). **Two e-mails go out with it**: the
   template's staff notification ("Notification 1", to one fixed address set in the form's
   Emails tab - it is not in the repo - with the ticked girl's name and the photo link) and the
   mentor confirmation to the address you typed. Tell the notification's recipient beforehand,
   or pause that e-mail for the test and switch it back on afterwards (whether a paused e-mail
   stays in the `emails` list is unverified; the diff of step 4 shows whatever changed and that
   it came back).
4. **Read back, within a few minutes:**
   - Drive (as the role account): folder `Attendance photos - Template` → one subfolder named
     exactly `<that club> <that date>` → one image file, **no PDF**.
   - Salesforce (read-only SOQL): exactly one new batch for that club and date,
     `Processing_Status__c = 'Failed'`, `Status_Message__c LIKE 'Duplicate:%'`, 0 `Attendance__c`
     rows (`SELECT COUNT() FROM Attendance__c WHERE Attendance_Batch__c = '<id>'`), no new
     Contact (`SELECT COUNT() FROM Contact WHERE CreatedDate = TODAY AND AccountId = '<club
     id>'` unchanged from before the test), and the partner-less Club account count unchanged
     (the query of step 3; 2 today). Then delete that one batch - Ryan's go, one write (the
     write connector or Ryan in the Salesforce UI) - and read it back as gone.
   - Jotform: `python3 tools/form_status.py --form 262352490535154 --roster <csv>` →
     `submissions 2`, CLEAN, `salesforce yes`; `backup_forms.py --form 262352490535154` and the
     diff against step 2's "after" snapshot → nothing but `count` (the submission) and, if you
     paused the notification, `emails` back to the original. Delete the test submission in
     Jotform Tables (Ryan; it frees no space for 30 days), or leave it: it holds one girl's tick
     and a test photo.
   - If the subfolder shows a name other than the club's (the picker's text, or empty): fix the
     Form Fields choice before any regional form.
5. **The regional forms**, at a quiet moment, smallest first: Latin America `262383455778067`,
   Asia `262383129464057`, Africa `262382821971058` (U.S skipped: it is being disabled). Per
   form: `python3 backup_forms.py --form <id>` before; the same settings, folder
   `Attendance photos - <Region>`, the "Club Name" field that is question 5 on that form;
   `backup_forms.py --form <id>` after and the diff → hunks inside `integrations` only;
   `python3 tools/form_status.py --form <id> --roster <csv>` → CLEAN. **No test submission on a
   regional form**: Asia and Africa submit many times a day, Latin America a few; the read-back
   is the first real submission's photo appearing in the form's Drive folder (within a day),
   and `python3 tools/integration_status.py --form <id>` → `other integrations:` naming the
   block (a `drive: yes` line follows once the key is known and coded - the tool's TODO). After
   the last form, and once the U.S form reads `DISABLED` (the clubs-off plan): `DRIVE_WANTED =
   True` in the tool, `integration_status.py` → the template and three regionals `drive: yes`,
   U.S `drive: not wanted (form DISABLED)`, `integration: ok`; `form_status.py` → every form
   CLEAN, `salesforce yes`.
6. **When copies stop** (a subfolder dated more than a week ago is the newest while the form has
   newer submissions; or Jotform e-mails a token error): the Google token has lapsed. In the
   builder, on each affected form: Settings → Integrations → Google Drive → remove → add again
   with the same settings (step 2, backup and diff included); read back with the next real
   submission. Nothing in the repo raises an alarm for this (BACKLOG 70); look at the folders
   once a month.
7. **Storage**: `python3 tools/form_status.py --roster <csv>` prints
   `storage: upload space N GiB of 10.00 GiB (P%) -> ok; submissions this cycle N of 2,500 (P%,
   resets <date>) -> ok; plan SILVER` on its first lines (`glow/usage.py`: `GET /user/usage`
   against the plan's limits; a read that fails is `storage: could not be read (…)`, never a
   form problem). Each limit is judged on its own: `warn` from 50 % of it, and from 80 % the
   automatic sync raises an ATTENTION naming the limit every morning until acted on (`!! ` on
   the line here). **Upload space** is the one Gold or retention answers: at about 50 % of it,
   decide Gold (100 GiB, nonprofit $594 a year against Silver's $234) or a retention policy
   (BACKLOG 68). A **submissions** `warn` is a busy month (1,250 submissions in the cycle) and
   resets on the date printed; it means Gold's 10,000 a month, not retention. Never switch on
   Jotform's Auto Delete Submissions without reading BACKLOG 68 first.

*Rollback.* Removing the Google Drive integration from a form in the builder stops the copies;
the photos stay in Jotform and nothing else on the form changes (the before/after diff of that
save says so). The template's Salesforce upload row is re-added only on the CEO's word, with
`UPLOADS = ["19"]` put back in `tools/integration_status.py`. What is already in Drive is the
owner's to delete (the CEO's retention decision).

## Disabling a regional form

- **When:** a regional form nobody submits on (the U.S form), before its clubs are deactivated.
- **Status:** built 2026-10-07; its first run (the U.S form) is not recorded yet, and it settles whether the API can switch a form off ([plan](plans/2026-10-06-clubs-off-jotform.md), D).
- **Dry run:** `tools/disable_form.py --form <id>`.
- **Apply:** `--message … --apply`, Ryan's go.
- **Verify:** the dry run again reads `DISABLED`; one runner dry run: the region `skipped - form DISABLED`.
- **Rollback:** `--enable --apply` (below).

A regional form nobody will submit on (the U.S form: 0 submissions since
launch, its 11 clubs deactivated - [plan](plans/2026-10-06-clubs-off-jotform.md),
D) is switched off, not synced down to an empty Club picker: Jotform then
serves its "form unavailable" page instead of the form; the runner reads the
form's status on every run and logs `form <id> is DISABLED - not synced` with
the SyncLog result `skipped` (no dry run, no apply, no verify, exit code
unaffected); `form_status.py` prints `[DISABLED]` and skips the region check
and the served-page checks; the form's rosters, picker and rules stay as they
are, frozen. **Order:** disable the form first, deactivate its clubs after
("Deactivating a club"; `deactivate_clubs.py` reads the form's status when
every active club of the region is chosen and refuses `--apply` while it is
not `DISABLED`, unless `--form-enabled-ok`). Deactivated first, every runner
run would fail on the empty region (`read_roster_csv` exits) until the form
is off.

```bash
python3 tools/disable_form.py --form 262382706852058                 # dry run: status, count, last submission, the disabled page's text
python3 tools/disable_form.py --form 262382706852058 --message "The U.S attendance form is paused. Please contact your GLOW coordinator." --apply
python3 tools/disable_form.py --form 262382706852058 --enable --apply   # the way back
```

- `status` (`ENABLED` / `DISABLED`) is a property of every form (`GET
  /form/{id}` and its `properties`). Whether `POST /form/{id}/properties`
  with `properties[status]` **changes** it is unverified until the first run
  (`.claude/skills/jotform-api/SKILL.md`, "Properties"). `--apply` takes a
  `backup_forms.py` snapshot first (its properties file records the status
  and `messageOfLimitedForm`, the disabled page's text, to put back), POSTs,
  re-reads both GETs and prints them. If the status did not move it stops:
  `the API accepted the write but the status did not change - disable the
  form in the builder (Settings -> Form Status) and run this again without
  --apply to confirm`. Either way the dry run afterwards must read
  `DISABLED`; record which way worked in the skill.
- Refusals: the template (never disabled); a form not in `glow.forms.LIVE`
  (the five pre-launch forms are already off); a form with a submission in
  the last 30 days, without `--disable-anyway`. The message is English only:
  whether Jotform's disabled page translates is unverified.
- Afterwards: one runner dry run (`python3 tools/auto_sync.py`) - the region
  reads `skipped - form DISABLED`, the others `in-sync`. `REGIONAL_FORMS`
  keeps the region: the live status is the truth read on every run, nothing
  to flip back in code.
- **The way back** (a U.S club starts): its rows back first ("Deactivating a
  club", the way back), then `python3 tools/disable_form.py --form
  262382706852058 --enable --apply` (or the builder), one runner dry run
  (the region reads `in-sync` or plans the restores), `AUTO_SYNC_APPLY`
  unchanged.

## Building a new regional form (not maintenance)

- **When:** only for a fresh form; never against a live one.
- **Status:** the four regional forms were cloned from the template this way on 2026-08-27 (f542063). The script that did it in one command, `tools/clone_regional.py`, is retired ([Retired tools](ARCHITECTURE.md#retired-tools)); `git show 608bcd2^:tools/clone_regional.py > tools/clone_regional.py` brings it back, but it predates `--partners` - prefer the steps below.
- **Dry run:** steps 1 and 4 (without `--apply`).
- **Apply:** steps 2-4 with `--apply`, Ryan's go: each writes to the Jotform account.
- **Verify:** step 5.
- **Rollback:** delete the new form in Jotform: no mentor has its link yet.

1. Snapshot the template: `python3 backup_forms.py --form 262352490535154`.
2. Clone it: `POST /form/262352490535154/clone`, through `glow.jotform.Client` with
   the key from the environment (never on a command line). The API can answer 504 and
   still create the clone: list `GET /user/forms` before and after, and delete an
   extra clone. Retitle the clone: `POST /form/<clone>/properties` with
   `properties[title]` and `properties[pagetitle]` = the region's title
   (`glow/forms.py` `TITLES`) and `properties[pageTitleChanged]` = `Yes`.
3. Its languages: `python3 tools/restore_translations.py --form <clone>`, then
   `--apply` (the API clone resets the language list to English; the template is the
   default source; the store is saved first).
4. The region's clubs, removing everything else:
   ```bash
   python3 sync_attendance_form.py data/roster_<date>.csv --roster \
           --partners data/partners_<date>.csv --region <region> --form <clone> --prune   # dry run
   python3 sync_attendance_form.py data/roster_<date>.csv --roster \
           --partners data/partners_<date>.csv --region <region> --form <clone> --prune --apply
   ```
   `--prune` deletes questions: only on this fresh clone (the sync refuses it on a
   form with submissions).
5. `python3 tools/form_status.py --form <clone> --roster data/roster_<date>.csv
   --partners data/partners_<date>.csv` → CLEAN, and `python3
   tools/integration_status.py --form <clone>` (the Salesforce integration survives a
   clone). Before mentors get the link, the form goes into `glow/forms.py` and the tool
   tables `test/glow_lib_test.py` pins to it: a code change with its own plan.

# Clubs

## Renaming a club

- **When:** a club's name changes; a new club the sync did not add because its name was in use (`--sheet-only`).
- **Status:** in use since 2026-09-14 ([Result](plans/2026-09-14-rename-club.md#result-executed-2026-09-14)).
- **Dry run:** `rename_club.py` without `--apply`, then the sync's dry run (its `!` line).
- **Apply:** rename the Salesforce Account first, then `--apply`, and the sync with `--apply --q5-change-ok`, in one sitting, Ryan's go.
- **Verify:** `form_status.py`: CLEAN; the Modification form's dropdown refreshed.
- **Rollback:** the tabs saved under `data/rename_club/<stamp>/` and `restore_conditions.py`.

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

- **When:** a club filed under a misspelled partner of its own (the old free-text enrollment).
- **Status:** done once, 2026-09-28 ([Result](plans/2026-09-24-move-club-partner.md#result)).
- **Dry run:** `rename_club.py --partner … --club … --new-partner …`.
- **Apply:** the same with `--apply` (it reads Jotform first), then the dropdown refresh at once.
- **Verify:** the ReviewQueue, a form preview, `auto_sync.py --region` in-sync, `form_status` CLEAN.
- **Rollback:** the last bullet of "What the tool does and guards".

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

## Club names two partners share

- **When:** a new club with a name in use (ATTENTION), a rename or a partner rename of a long-named club, a restore of conditions.
- **Status:** live on all five forms since 2026-09-30, the intake hold (Part 2, Apps Script) pushed the same day ([Result](plans/2026-09-30-same-name-clubs.md#result--the-forms-2026-09-30-with-ryans-go)).
- **Dry run:** the sync's dry run: its `!` lines.
- **Apply:** by hand, as each rule below says; the runner never applies a question-5 change.
- **Verify:** `form_status.py` (`same-name clubs: 7`), the sync's `--summary-json` `sf_names`.
- **Rollback:** fix forward ("The one-time switch", below).
- **History:** [plan](plans/2026-09-30-same-name-clubs.md#from-the-runbook-moved-2026-10-09).

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

A form that is not switched (a new
regional clone) keeps its same-name rosters on one entry, told apart by the
typed Partner box (q331), until its own switch (below).

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
   handler holds such a club before it reaches the Roster — Part 2 of the
   plan, live since 2026-09-30; this is the backstop.)
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
becoming long whose long name is another club's own name; a form carrying a
partner list (retired 2026-09-30, never deployed; `--partner-picker` is no
option at all since 2026-10-09, so argparse rejects it); `--same-name-switch` on a form without the Club picker; and
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
does not name it (the run's log does: `HIDE partner textbox`). Since 2026-09-30
it is hidden on all five forms.

### The one-time switch (`--same-name-switch`)

Done on all five forms on 2026-09-30: the template, Asia and Africa switched; U.S and Latin
America had nothing to switch and only got q331 hidden ([Result](plans/2026-09-30-same-name-clubs.md#result--the-forms-2026-09-30-with-ryans-go)).
By hand, once per form, never by the runner: a form that is not switched (a new regional
clone) needs it. The procedure as run - the runner paused, the backup, the dry run's `!`
lines counted before the apply, the verify and the browser checks - and its rollback
(only before the Salesforce reconnect, so no longer usable: fix forward) are in the
[plan](plans/2026-09-30-same-name-clubs.md#from-the-runbook-moved-2026-10-09).

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
  on the picker's entries. Since 2026-10-09 the restore snapshots the form
  before its write and prints the `--from` that undoes it, and refuses a
  snapshot with a rule that does not parse, `--force` or not. The runner does not apply a rules-only
  difference: it raises ATTENTION ("roster rule(s) test a name the Club
  picker does not list") on every run until that apply, or until a roster
  change in that region makes it apply.

## Clubs that do not use Jotform

- **When:** a partner's clubs stop (or start again) reporting through Jotform: the Partners tab's `jotform` cell.
- **Status:** built 2026-10-07 on wf10 (merged into `main` 2026-10-09). First rollout done 2026-10-16 on Ryan's go: the three partners below marked `no`, their 38 rosters retired by hand on the template (~00:40 UTC) and the Africa form (~00:50 UTC), both `form_status --partners --rendered` CLEAN (38 retired, 38 always-hidden), the runner's dry run `in-sync` ([plan, Result](plans/2026-10-06-clubs-off-jotform.md#result)).
- **Dry run:** the sync's dry run with `--partners`: the `~ retired roster` lines.
- **Apply:** backup, `--apply` with Ryan's go (more than 5 per region: by hand), a second dry run.
- **Verify:** `form_status.py --partners --rendered`: CLEAN, `rendered retired: N retired rosters, N always-hidden`.
- **Rollback:** clear the cell ("The way back", below).

Some partners report attendance to GLOW directly (a monthly total per club),
not through the attendance forms: Education and English for You, Tumaini La
Maisha and Ng'aa Maskani since 2026-10-06, their 38 clubs off the template's
and the Africa form's Club picker since 2026-10-16
([plans/2026-10-06-clubs-off-jotform.md](plans/2026-10-06-clubs-off-jotform.md)).
Their clubs stay in the Roster — the girls are active and enrolled, their ids
are kept, the Club Roster Form still lists the clubs — but they leave the
attendance forms' Club picker. Never give such a club a blank region (CLAUDE.md
rule 6: that says "fix me" and raises ATTENTION on every run); mark the
partner instead.

**The marker.** The Partners tab's fourth column, `jotform`: `no` = the
partner's clubs are not on Jotform; `yes` or blank = on Jotform (the default;
most cells stay empty). GLOW staff set it in the sheet (`Partners!D1` is the
header `jotform`; `no` in the partner's row). Capitals and spacing do not
matter (`No`, ` no `); any other text counts as **yes** — nothing leaves a
form because of a typo — and the runner raises ATTENTION naming the cell
("Partners-tab jotform value(s) not understood") until it is corrected. An
export with no `jotform` column at all (the header renamed or moved, a column
inserted before it) marks nobody: the sync warns (`! Partners tab: the export
has no 'jotform' column …`), the runner raises ATTENTION ("the Partners export
has no jotform column"), `--apply` refuses to restore a retired roster from it
and the runner holds a plan that would — put the header back and the next run
reads the marks again. The tab travels with the Roster: the runner exports it
beside the Roster export on every run, a hand run passes it as `--partners`
(the manual loop above).

**What the next run does.** A roster whose partner is marked `no` is
**retired**: kept on the form, hidden and frozen (its question is never
written to, its girls' names stay in its options), off the Club picker, with
no show rule, still in question 18's sum (harmless: a roster nobody can see
has no ticked box). The dry run says so per roster, a third marker beside `!`
and `?`:

```
Roster: 182 active clubs in Africa (3518 girls); 364 clubs overall; 38 club(s) of 3 partner(s) not on Jotform (Partners tab jotform=no) left off this form
  ~ retired roster '<club>' (q…): not on Jotform (<partner>, Partners tab jotform=no)
DRY RUN (use --apply to write):
  - UPDATE club picker (182 clubs: calcValues, options)
  - REPLACE conditions (213 rules)
```

The picker update and the conditions rewrite are the whole change (rule 3:
generated, nothing hand-made). Once applied, later runs print `Retired
rosters: N already off the Club picker` and nothing to do. The same happens,
in every region, to a club that has **no active girl** once its rows have been
inactive since before the day of the run (`~ retired roster '<club>' (q…): no
active girl in the Roster`; `glow/sync.py RETIRE_INACTIVE`, on since
2026-10-06): a roster emptied and refilled in two Club Roster Form submissions
on one day stays on the picker in between. Days are the sheet's own: the sheet
stamps `removed_date` in its time zone (File → Settings, America/New_York),
and the sync and the audit take "today" in that zone (`glow/sync.py
SHEET_ZONE`, `sheet_today`), never UTC's — the runner reads the sheet's
setting with the exports and raises ATTENTION when it differs from the
constant (change the constant if the sheet's zone was changed on purpose).

**The bands.** The runner retires at most 5 rosters and restores at most 5
per region per run (`--max-retires`, `--max-restores`); more is `attention`,
nothing applied, "apply by hand after checking" — the first rollout (38 on
the template and Africa, 2026-10-16) was a hand apply in any case: backup, dry run, `--apply` with Ryan's
go, second dry run, then `form_status.py --partners --rendered` (CLEAN,
`retired rosters: 38 (not on Jotform 38, no active girl 0)` and `rendered
retired: 38 retired rosters, 38 always-hidden`). The audit's `vs Roster` line
reads `… 38 await retirement (the next sync apply)` between the mark and the
apply (a note, not a problem), `… 38 retired` after it.

**Why a retired roster is hidden and required without a rule.** Jotform
validates a required field only when its element carries neither
`always-hidden` nor `form-field-hidden` (`.claude/skills/jotform-api`, "Required
+ hidden"); a property-hidden question no rule touches renders `always-hidden`
alone, and `form_status.py --rendered` counts exactly that for the retired
rosters (`rendered retired: N retired rosters, N always-hidden` — fewer is a
PROBLEM: stop, no mentor could submit). Proven on the template before any
regional form (the plan's step 7; 2026-10-16: 38 retired, 38 always-hidden on
the template, then on Africa).

**The way back.** Clear the cell (or write `yes`): the next run restores the
rosters (`~ restored roster '<club>' (q…): back on the Club picker`, their
entries and rules back, an options update if the Roster moved on) — within the
hour for 5 or fewer, a hand apply for more. A club that has active girls again
comes back the same way. A restored roster whose club's **name two partners
have had** has no rule left to read what it sent, so it comes back with its
long name `<club> - <partner>` as a question-5 change: the `!` line (`… changes
from '(retired: no rule to read)' to '<club> - <partner>'`), `--apply` refused
without `--q5-change-ok`, the runner's question-5 band — check the Salesforce
Account's name first ("Club names two partners share"). None of the 38 shares
its name. No snapshot is involved: `restore_conditions.py` would refuse the
pre-retirement conditions anyway (their rules test entries the picker no longer
lists).

**What else.** A Partners export missing a partner that has active clubs is
refused by the sync (`Partners export lists 46 of 49 partners with active
clubs - missing: … - a truncated export, or rows deleted from the Partners
tab? nothing done`; the runner logs `failed`): without that floor a cut export
would read every partner as unmarked and restore every retired roster
unattended. The mentor e-mails of a marked partner say the attendance form
does not change for them (Apps Script, once that change is pushed: the plan's
step 11). Salesforce is untouched: the clubs' Accounts keep their names. On
the dashboard they stay in "Clubs with no attendance last month" (that tile
counts Jotform attendance rows, Ryan's decision of 2026-10-06) and in the
batch-based "did not submit" lists planned beside it: their partners' figure
is one monthly batch on the partner account, never per club (2026-10-19,
"Attendance totals and partner-reported counts").

## Deactivating a club

- **When:** a club whose girls stopped coming; a whole region's clubs, after its form is disabled.
- **Status:** built 2026-10-07 ([plan](plans/2026-10-06-clubs-off-jotform.md), C).
- **Dry run:** `tools/deactivate_clubs.py --partner … --check-only`, then without `--apply`.
- **Apply:** `--reason … --apply`, Ryan's go; then the dropdown refresh.
- **Verify:** the template's sync dry run plans `~ retired roster …` from the day after.
- **Rollback:** `--undo data/deactivate_clubs/<stamp>` (below).

A club whose girls stop coming, or whose partner stops using the attendance
form for it, leaves the forms through its Roster rows: every row set
`inactive` with a `removed_date`, the way the Club Roster Form removes one
girl ([plan](plans/2026-10-06-clubs-off-jotform.md), C). The girls keep
their ids and the club its ClubRegistry code, so a reactivation brings the
same ids back; the template's sync then retires the club's roster question -
hidden, off the Club picker, never deleted: `~ retired roster '<club>' (q…):
no active girl in the Roster`, from the day after the removal
(`glow.sync.RETIRE_INACTIVE`). A whole region's clubs leave the same way,
**after** the region's form is disabled ("Disabling a regional form"; the
other way round every runner run fails on the empty region until the form is
off).

```bash
python3 tools/deactivate_clubs.py --partner "<partner>" --check-only                   # who sent what since 2026-09-01 (reads only)
python3 tools/deactivate_clubs.py --region U.S --reason "<why - who decided, when>"     # dry run
python3 tools/deactivate_clubs.py --region U.S --reason "<why>" --apply
python3 tools/deactivate_clubs.py --partner "<partner>" --club "<club>" --reason "<why>" --apply   # one club
python3 tools/deactivate_clubs.py --undo data/deactivate_clubs/<stamp>                 # the way back, dry run
python3 tools/deactivate_clubs.py --undo data/deactivate_clubs/<stamp> --apply
```

What the tool does and guards:

- **The guard.** Before the plan it reads the region's attendance form's
  submissions since 2026-09-01 (`JOTFORM_API_KEY`; counts, days and club
  names only) and credits each to a club by question 5 or the Club picker's
  pick: the same text, or exactly `<club> - <its partner>` - never a bare
  prefix (`QUEENS` is not `Queens of Quest`), and never a namesake's
  `<club> - <other partner>`. A club named in the last 30 days
  (`--recent-days`) stops the run: `'<club>' (<partner>) sent attendance on
  <day> - deactivating a club that reports needs --deactivate-anyway`.
  `--check-only` prints the table and stops: per partner its clubs and
  submissions, then each club that was named with its days and whether it
  was picked together with another club (the 2026-09-25 Africa pick). When
  the chosen clubs are every active club of a region (`--region`, or its
  partners together) the form's status is read too: not `DISABLED`, the
  table says so with `!` and `--apply` refuses without `--form-enabled-ok` -
  the order is form first, clubs after.
- **The write** (`--apply`, with `--reason`: one line for the Audit row).
  `status` → `inactive` and `removed_date` → today in the sheet's zone (the
  text the Apps Script writes) on every ACTIVE row of the chosen clubs, in
  one batch. First the Roster tab is saved to
  `data/deactivate_clubs/<stamp>/Roster.csv` and the rows with their old
  values to `written.json` beside it; then the tab is re-read and the run
  stops, nothing written, if a planned row changed or a club gained an
  active row (a Club Roster Form submission in between: run it again). After
  the write every row is re-read and compared and the two columns are checked
  unchanged everywhere else; then one Audit row `deactivateRows` (`11 club(s)
  of 6 partner(s) in U.S: 155 row(s) set inactive, removed_date <day> -
  tools/deactivate_clubs.py (<reason>)`). A row of a chosen club that arrives
  during the write is left active and named (`!`, exit 1): run the tool
  again for it.
- **Not touched:** ClubRegistry (the code is immutable; `Ids.gs` finds it by
  partner + club when the club comes back), SF Pending (the Accounts exist),
  the Partners tab (the partners stay, with their region), the forms.
- **Afterwards, in the sheet, now:** **GLOW → Google Forms → Update form
  dropdowns from the Roster**, so the Club Roster Form reads `(no active
  clubs)` for the partner; until then it still offers the clubs, and a change
  sent for one runs against the inactive rows and puts girls back by name.
  Then `python3 tools/sheets_client.py export Roster data/roster_<date>.csv`
  and the template's sync dry run (`python3 sync_attendance_form.py
  data/roster_<date>.csv --roster --form 262352490535154`): from the day
  after, it plans `~ retired roster …` for each club (the section on clubs
  that do not use Jotform). The region's form: a `DISABLED` one is `skipped` by the runner
  and left as it is (its rosters, picker and rules frozen); an enabled one
  gets the retirements from its next sync.
- **The way back.** `--undo data/deactivate_clubs/<stamp>` puts back exactly
  the rows `written.json` names - `status` and `removed_date` as they were -
  with the same shape (dry run, stale check, one batch, re-read, Audit
  `reactivateRows`). It refuses before the plan - the dry run too, nothing
  saved - naming the rows and their clubs, when one of those rows has
  changed since or a chosen club has an active row `written.json` does not
  name (a girl reactivated or enrolled through the Club Roster Form, a moved
  club): that club is a human's call. Look at those rows first; for the other
  clubs to go back, take that club out of `written.json` - its rows and its
  line under `"clubs"` (half an edit is refused by name) - and run again; its
  own rows go back by hand from the folder's `Roster.csv` or through the Club
  Roster Form. Then the
  dropdown refresh and a runner dry run (the sync restores the rosters,
  `~ restored roster …`, within its bands). One club that starts again
  without the undo: the partner sends "Enroll a NEW club" (its section shows
  no club to change); the duplicate guard holds it as a re-enrollment with
  its names on file, Ryan releases it from the Monday e-mail ("Working the
  ReviewQueue") and `planClub_` reactivates the rows by name.

## Roster rebuild and upload (offline path)

- **When:** never after launch (below).
- **Status:** pre-launch only, never after 2026-09-01.

**Not after launch.** Since 2026-09-01 the Roster has moved on from the raw
enrollment responses. A rebuild from them, whether this offline path or
**GLOW → Rebuild roster from enrollment responses**, reactivates every girl
removed through the Club Roster Form whose name is still on her club's
original enrollment row (`planClub_`). It also re-creates any enrolled club
that was renamed or moved to another partner, under its old name or partner
and with new ids. Change single clubs with the tools above instead.

After the next `clasp push` of `appsscript/` (the 2026-10-09 cleanup), the menu
item says this in a YES/NO dialog first and does nothing on any other answer;
run from the script editor, it refuses.

The offline path's commands, for the record (pre-launch only):
[archive/runbook-roster-rebuild.md](archive/runbook-roster-rebuild.md). Guarding the
rebuild itself is BACKLOG 39.

# Sheet and Apps Script

## Working the ReviewQueue

- **When:** the Monday e-mail (09:00-10:00 New York time), or any open item.
- **Status:** owner Ryan, since 2026-09-28 ([Result](plans/2026-09-28-problem-report-followup.md#result)).

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
| **Roster change sent as a problem report** | Read `Feedback!N` (the tag). Check the Roster and Audit `rosterChangeForm`: the partner may have sent it since. Enter it as above, or ask the partner to. Not a roster change after all: `resolved …: not a roster change`. A roster-change report whose staff e-mail lacks the "Staff note" line was missed by the keyword check: add a row by hand with this issue and `[#Feedback!N]` as the last text of detail (reports from before 2026-09-28 were added once by a one-off script, since retired: [Retired tools](ARCHITECTURE.md#retired-tools)). |
| **Removal did not match anyone** | Detail shows the typed name and up to 3 "Closest names on file" — other girls, so never send them to the mentor. REMOVE only a match that is clearly her; otherwise ask the mentor for the enrolled spelling (her confirmation said "our team will check"). |
| **Removed girls not put back by an older response** | A Club Roster Form response ran after some girls it lists had been removed — a retry, or an old response confirmed in "Missed form responses" — so they stayed removed instead of coming back (the 2026-09-13 replay cannot recur). Detail names the response row, the day it was sent and the Roster rows; the mentor's confirmation (roster changes) listed the names the mentor typed under "Not added back". Usually nothing to do: `resolved …: stayed removed`. If a girl really has rejoined since her removal (ask the partner), ADD her as above: the same ID comes back. |
| **Same name listed twice** | Only one girl is on the Roster. Ask the partner: two girls → ADD the second with a mark, e.g. `Jane Doe (B)` (the first keeps her ID); one girl typed twice → `resolved …: one girl, no change`. Never resubmit through "Enroll a NEW club". |
| **Partner says two girls share a name** | The partner answered Yes but no name repeats. Compare their note with the club's Roster rows: listed distinctly → resolved, no change; one missing → ADD her with a mark as above. |
| **Girls missing from the latest enrollment** | "Enroll a NEW club" was sent for a club already on file; the girls not in that list stay active. Ask the partner who has left and REMOVE them as above. If the new list was not this club's at all (Radiant Girls, 2026-08-31), REMOVE the rows it added as above: the names whose Roster `source` is that response row (Ryan's go). |
| **Roster change for a club not on file** | Nothing changed, the mentor got no confirmation, and it is never retried. Find the club under another name or partner ("Renaming a club", "Moving a club to another partner"), run **GLOW → Google Forms → Update form dropdowns from the Roster**, then enter the change from the response row (or ask the partner) and tell the mentor. A truly new club uses "Enroll a NEW club". |
| **Partner has no region** | Its girls reach no attendance form. A misspelled partner → "Moving a club to another partner". Otherwise set the Partners-tab region (`Africa`, `Asia`, `Latin America`, `U.S`), run **GLOW → Refresh regions from the Partners tab**, and check that the region's next SyncLog row says `applied`. |
| **Form response could not be processed** | Detail names the response row and the error. Fix the cause (a Script Property, a missing answer), then run **Process any missed form responses** ("Missed form responses"). A Club Roster Form response more than 7 days old, or one refused because its Timestamp cell is not a date (a retry fails the same way): enter the change fresh instead and set its FormLog result to `resolved by hand by <name> <date>`. Close the item once FormLog has a row for that response (same form and `sheet_row`) whose result starts with neither `ERROR:` nor `HELD:` — the retry's success, or the one you set by hand; the earlier `ERROR:` row stays, and **Process any missed form responses** no longer offers it. A retry that was held (`HELD:`) continues as its **New club held as a possible duplicate** or **Club name already used by another partner — ask for a different name** item: close this one. |

## Missed form responses

- **When:** after a scope-adding push and its re-authorization; a FormLog `ERROR:`; a hold staff released.
- **Dry run:** the menu's preview: answer NO.
- **Apply:** YES, per group.
- **Verify:** the Audit tab (`finished: …; N left`), FormLog.
- **Rollback:** none for a run; never roll `appsscript/` back below its floors ("Rolling back `appsscript/`", under "Apps Script deploy").

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

**A Club Roster Form response that failed half-way** (after the next `clasp push`
of `appsscript/`, the 2026-10-09 cleanup). "Enroll a NEW club" writes the
ClubRegistry, the Partners tab and the club's **SF Pending** row first, then its
Roster rows; after the Roster write only best-effort steps follow (the Jotform sync
request, the form dropdowns, the ReviewQueue items, Audit), and a failure among them
is noted in FormLog and Audit but never makes the response an `ERROR:`. So a
failure up to and including the Roster write is an `ERROR:` whose retry here finds
the club still without girls - still new - with its code, its partner and its
pending SF Pending row found again (no second row), and a failure after it needs
no retry. Two things to know: if the Roster write failed and nobody retries, an SF
Pending row waits for a club with no girls (retry the response, or close that row
when the club is not coming); and an SF Pending row closed by hand before the
retry gets a successor (close it again). "Add or remove girls" works the same way
after the Roster write, so its mentor e-mail is sent once. Before that push the
SF Pending row came after the Roster write: a failure there lost it, and the retry
treated the club as existing - check SF Pending for a new club whose response
shows an `ERROR:` and then a success in FormLog.

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

## Google Forms wording

- **When:** once, on the two Google Forms built before 2026-09-28.
- **Status:** the menu item is deployed (2026-09-30, the same-name push); the one-time run is Ryan's and not yet recorded (BACKLOG 43; [plan](plans/2026-09-28-forms-wording.md)).
- **Dry run:** the menu's preview (`now:` / `new:`); NO changes nothing.
- **Apply:** YES.
- **Verify:** `Done — N change(s); re-read: up to date`; a second run says "Nothing to change".
- **Rollback:** the Forms editor (the last bullet).

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

## Apps Script deploy

- **When:** any change under `appsscript/`.
- **Status:** the 2026-10-09 cleanup's changes (the Club Roster Form handlers' write order, the rebuild's YES/NO, the dropdown update under the lock, the consolidations) are in the repository, not deployed: they wait for Ryan's push. No new Google service, so no re-authorization is expected ([Result](plans/2026-10-09-repo-cleanup.md#result)).
- **Dry run:** `make gs` (and `make check`).
- **Apply:** `nvm use 18`, then `npm run clasp:push` at a quiet moment: Ryan, or Claude on his yes to the gate's prompt. Ryan can run the push with Claude through the user-only `/deploy-appsscript` skill.
- **Verify:** a new Google service: authorize at once, then "Process any missed form responses" and read its preview.
- **Rollback:** a push of the previously deployed `appsscript/` ("Rolling back `appsscript/`", below).

```bash
make gs                 # parse, pinned services, calls that resolve (below)
nvm use 18              # clasp 2.4.2: the npm scripts refuse any other Node
npm run clasp:push      # gated: Claude asks, your answer is the go; or run it yourself
```

`make gs` (`scripts/check_gs.js`) checks offline what would otherwise fail only live,
inside the trigger: every `.gs` file parses and the pure files load together; the
Google services used are exactly the 8 pinned ones (`FormApp`, `LockService`, `MailApp`,
`PropertiesService`, `ScriptApp`, `SpreadsheetApp`, `UrlFetchApp`, `Utilities`) - a
9th, a scope-bearing global such as `Session`, an advanced service or `oauthScopes` in
`appsscript.json` fails it (a new scope: the rule below); and every call, and every
function a menu item or trigger names, resolves to a function that exists. `npm run
clasp:push` and `clasp:open` stop with "clasp 2.4.2 needs Node 18" on any other Node
(the Mac's default is newer); `npm install` once per clone.

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
`git checkout 986a325 -- appsscript && npm run clasp:push`. (That deploy went
out with the same-name push on 2026-09-30 10:38 UTC; the script live before it
was the 2026-09-28 one, `a1dc5d7`, confirmed by a `clasp pull` compare.
`986a325` is that script plus the two-reply-column read, so it is the rollback
target whether or not the wording migration has run.) First read
"Rolling back `appsscript/`" below: the floors (`7a175c4`, and `986a325`
once the Feedback tab has two reply columns) and held new clubs.

The same-name push of 2026-09-30 10:38 UTC was a normal push (no new Google service;
what it changed: [History](plans/2026-09-30-same-name-intake.md#from-the-runbook-moved-2026-10-09)). To undo it, push the
`appsscript/` that was deployed before it ("Same-name holds and a rollback below the
same-name check", below).

### Rolling back `appsscript/`

A rollback (`git checkout <target> -- appsscript && npm
run clasp:push`) to a commit before `7a175c4` brings back the old menu item,
which cannot read the new keys and would re-run everything processed since
the deploy, without a preview. Roll back no further than `7a175c4`; it shows
rows logged under the new keys as held. Once the Feedback tab has two reply
columns, no further than `986a325` ("Google Forms wording", above). To undo
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

## Data-quality report

- **When:** no longer run: the report was a pre-launch check of the raw enrollment export.
- **Status:** retired 2026-10-09. `tools/needs_attention.py` wrote `data/needs_attention_<date>.csv` (names listed twice, re-submitted rosters, clubs renamed on a form, …); the 2026-08-26 list is still worked as BACKLOG 4. Restore: `git show 7c24ac7^:tools/needs_attention.py > tools/needs_attention.py` ([Retired tools](ARCHITECTURE.md#retired-tools)).

Since launch the same questions come from the running system instead: the
ReviewQueue ("Working the ReviewQueue": a name listed twice, girls missing from
a re-enrollment, a possible duplicate club), the runner's ATTENTION items
("Automatic sync") and `tools/form_status.py`.

# Salesforce

Claude loads the `salesforce` skill before any procedure in this part.

## Club accounts in Salesforce

- **When:** a new club (while `SF_SYNC` is not `apply`, or an `SF:` ATTENTION item); the Monday e-mail's SF Pending list; a partner-less account.
- **Status:** every active club has an account since 2026-09-30 ([Result](plans/2026-09-30-salesforce-clubs.md#result-2026-09-30)).
- **Apply:** the write connector, one record per call, Ryan's go.
- **Verify:** the Signals below.
- **Rollback:** the rollback files (the last bullet).

Since 2026-09-30 every active club has a **Club account** in Salesforce (production), named
exactly as its attendance form sends it and linked to its partner account through the parent
account field ([plan and result](plans/2026-09-30-salesforce-clubs.md)). The attendance
processor matches the submitted club name against every account name, ignoring capitals only;
when nothing matches it creates a new, partner-less Club account.

- **Never edit a club's name in Salesforce.** A rename starts in the sheet ("Renaming a club"),
  and the account is then renamed to the new picker text - with Ryan's go.
- **A new club** gets its account from the automatic sync when `SF_SYNC` is `apply` (below).
  Otherwise, or when the sync says ATTENTION, it is created by hand before its first attendance:
  it stays in the SF Pending tab and the Monday e-mail until then - while `SF_SYNC` is not `apply`
  that round is weekly: the Monday e-mail's SF Pending list is worked each Monday (Ryan with
  Claude) as a further round of the procedure below. Once `SF_SYNC` is `apply`, create by hand
  only for an `SF:` ATTENTION item, and read the name in Salesforce first (the sync may have
  made it since). A club the sync never puts on a form (its partner marked `jotform=no`, "Clubs
  that do not use Jotform") is a hand create in every mode (BACKLOG 74). A partner-less account
  the processor created meanwhile is re-parented to its partner, never re-created (its Contacts
  and attendance stay; done for two clubs on 2026-10-06). An SF Pending row whose club has no
  Roster rows is a response that failed before its Roster write ("Missed form responses"):
  retry that first, then create the account.
- **The Monday e-mail's SF Pending lines** start with the exact account name: the club name, or
  `<club> - <partner>` when another partner's active club has the same name, worked out from
  the Roster when the e-mail is sent. On a form the long or plain name is sticky, so the form's
  club list is the authority: a line ending "NAME SHARED … use exactly that text" means look the
  club up in its attendance form's club list before creating the account. An account named
  otherwise than the form sends gets a stray twin at the club's first attendance.
- **Signals** (read-only queries, all expected as stated):
  - Club accounts without a parent: exactly the two pilot accounts that are on hold. One more
    means a form sent a name no account carries.
  - Contacts on Club accounts that are not girls (role other than Participant), Contacts on Club
    accounts marked as portal sign-ups, Monthly Reports on Club accounts, programme-income
    records on Club accounts: all 0.
  - Every active club on a form has exactly one right account: `python3 tools/sf_new_clubs.py
    check --vpn-off --roster data/roster_<date>.csv --summary data/auto_sync/plan_<region>_<stamp>.json …`
    (read only, Ryan's CLI login; the summaries of a local `tools/auto_sync.py` dry run) exits 0;
    "Local cross-check", under "New clubs' accounts, automatically". (Until 2026-10-09 this
    signal was the retired `tools/sf_club_accounts.py totals`: 364 Club accounts on 2026-09-30.)
- **Writing accounts to Salesforce** by hand goes through the write connector, one record per call,
  never by a subagent; the live gate does not see those calls, so the only gate is Ryan's go in the
  conversation. The automatic sync writes as its own user, GLOW Sync, and only creates (below). A
  hand create is named exactly as its SF Pending line says, record type Club, its parent the
  partner's account in `glow/sf_partners.csv` (the fields the sync's own create sets, below); then
  the `sf_new_clubs.py check` above. The 2026-09-30 rounds' bookkeeping tool,
  `tools/sf_club_accounts.py`, is retired ([Retired tools](ARCHITECTURE.md#retired-tools)). (Attendance
  is written by `tools/sf_backfill.py`, which the gate does catch: "Back-fill of attendance into
  Salesforce".)
- **Rollback files** (never committed): `data/sf_prep_2026-09-30/created_accounts.csv` (345
  created, 8 linked), `created_accounts_round2.csv` (2 created), `created_accounts_round3.csv` (the
  7 same-name clubs), `link_targets_before.json` (the pilot accounts as they were). A created account may be deleted only while it has no Contacts
  and no attendance, and only with Ryan's go.

### New clubs' accounts, automatically (`SF_SYNC`)

- **When:** switching `SF_SYNC` (`plan`, then `apply`); an `SF:` ATTENTION item; rotating the secret.
- **Status:** built and in `main` since 2026-10-07; the Setup below (Salesforce and GitHub) is Ryan's and not recorded as done ([plan](plans/2026-10-06-sf-new-club-accounts.md)).
- **Dry run:** `SF_SYNC=plan`: every account it would create is an ATTENTION item with the body.
- **Apply:** `SF_SYNC=apply` (with `AUTO_SYNC_APPLY=1`), Ryan's go.
- **Verify:** the run's `SF:` log lines; the local cross-check, below.
- **Rollback:** `SF_SYNC=off`; "Rollback of creates", below.

`tools/sf_new_clubs.py`, called by `tools/auto_sync.py`.

**What each run does:**
- Log in as **GLOW Sync**, an integration user, never Ryan's.
- Read every Account, and stop all Salesforce work for the run if the read is not the whole org.
- Before a region's form puts a new club on its Club picker, create the club's account:
  - Name = exactly what question 5 will send;
  - record type Club;
  - parent = its partner's account from `glow/sf_partners.csv`;
  - Description `GLOW club code <code>; created by the automatic sync <date>`.
- After all regions, check every active club on a form, read only.

**What it never does**: update, rename, delete, change an owner, touch a Contact or attendance, or
create for a club that is not being put on a form.

**The switch**: repository variable `SF_SYNC`; changing it is Ryan's go (CLAUDE.md rule 1).

| `SF_SYNC` | What it does |
|---|---|
| `off` (or unset) | Nothing: no login. |
| `plan` | Reads and checks only. Every account it would create is an ATTENTION item with the exact body, for a person to create that day. |
| `apply` | Creates, at most 5 per region per run, all or nothing. Only when the forms apply too (`AUTO_SYNC_APPLY=1`); the workflow then adds `--apply-salesforce`. |

Without the secrets the log says `SF: not configured`, with no ATTENTION.

**Setup** (Ryan, once, in Salesforce Setup and on GitHub; nothing here goes through a Claude
session):
1. **User** "GLOW Sync":
   - user licence Salesforce Integration, profile "Minimum Access - API Only Integrations";
   - assign it the permission set licence "Salesforce API Integration".
2. **Permission set** "GLOW Club Sync", licence "Salesforce API Integration":
   - Account Read, Create and **View All**; field access `ParentId`, `Description`; record type
     Club;
   - nothing else: no Edit, no Contact, no attendance;
   - assign it to GLOW Sync.
3. **External Client App** "GLOW Sync":
   - OAuth on; scope **api** only; **client credentials** flow on, Run As = GLOW Sync;
   - App Policies: Permitted Users "Admin approved users are pre-authorized", permission set GLOW
     Club Sync;
   - a short session timeout; no refresh token; no login IP ranges (GitHub's addresses change).
4. **The dispatch token**, in this order (the old `Dispatch.gs` needs Contents: write, the new one
   Actions: write, so the token holds both for a few minutes):
   1. On GitHub, Settings → Developer settings → Fine-grained tokens → the sheet's token → Edit:
      add **Actions: Read and write**, keeping Contents for now.
   2. `npm run clasp:push` of `Dispatch.gs`, at a quiet moment. There is no new Google service,
      so no re-authorisation.
   3. GLOW → Google Forms → Request Jotform sync now: the Audit tab must show `HTTP 204`, and the
      Actions tab a run started by `workflow_dispatch`.
   4. Edit the token again: Contents → **No access**. It can no longer change the code that holds
      the Salesforce secret.
   5. Request Jotform sync now once more: `HTTP 204` again.
   - Before step 2 the sheet still uses `repository_dispatch`; after it, a token without Actions
     gets `HTTP 403` in the Audit tab and only the daily run syncs.
   - The workflow runs only on `main` (a token with Actions: write can pick the branch of a run);
     delete stale branches on GitHub, whose older workflow file has no such guard.
5. **GitHub**:
   - secrets `SF_CLIENT_ID` and `SF_CLIENT_SECRET` (the app's consumer key and secret), on the
     web page or `gh secret set` reading stdin;
   - repository variable `SF_SYNC` = `plan`.
6. **First run**: Actions → auto-sync → Run workflow (apply unticked). The log must show:
   - `SF: plan, as GLOW Sync`;
   - `SF: describe ok - Account, Name, ParentId, Description, RecordTypeId createable; Club record
     type available` (otherwise `SF: GLOW Sync cannot create Club accounts: …` names what the
     permission set lacks, and an `apply` run only shows bodies);
   - `SF: 448 Accounts read, 366 Club` (or today's counts);
   - `SF: check - 364 ok, 0 need a person`.

   Then from Ryan's `glow` login: `UserRecordAccess` for GLOW Sync is read access on a club and on
   a partner account.

**ATTENTION items (`SF: …`) and what to do:**

| Item | Meaning | Fix |
|---|---|---|
| `not ready …` | Login refused, the user frozen, or the Account read not whole (View All lost, a page missing, a mapped partner unseen) | Read the detail. **Frozen**: an administrator unfreezes GLOW Sync (Salesforce also e-mails the admins); if it repeats, set `SF_SYNC=off` and ask Salesforce Support. New clubs this run went on the forms without an account: create them by hand. |
| `would create …` (plan) | A new club needs its account | Create it by hand with the body shown, today |
| `… - not created`: club code on another account | The club was renamed in the sheet, not in Salesforce | Rename that account to the question-5 name first ("Renaming a club"); no new account |
| `… - not created`: the name is already an account | The processor made it first, or another record has the name | A partner-less Club: set its `ParentId` as the item says (write connector, Ryan's go). Anything else: look before acting. |
| `… - not created`: nearly the same name, or a character not yet seen in question 5 | A spelling a person must judge | Check, then create by hand with the body shown |
| `… - not created`: partner not in `glow/sf_partners.csv` | A new partner | Add one line, `partner,sf_account_id,sf_account_name`, for its Household account (create that first if needed); commit; the next run proceeds |
| `more than 5 … none created` | A wave of new clubs | Create by hand from the bodies listed, or let the next runs take them |
| `created … check it by hand (first creates)` | Shown until the first creates are checked | Read the account: name, Club, parent, Description, owner GLOW Sync |
| `check by hand: the create's outcome is not as planned` | Salesforce did not answer clearly | Read the name in Salesforce **ten minutes later**. One account, right: nothing to do. None: create by hand. Two: delete the newer (no Contacts). |
| `N club account(s) need a person` | The check found a club whose account is missing, partner-less, under another partner, twice, not a Club, or carrying another code; or a partner-less stray | Each line names the fix |
| `partner map out of date` | A partner account was renamed in Salesforce | Update its line in `glow/sf_partners.csv` |

**SF Pending**: when it creates an account, the run marks that club's SF Pending row
`done (auto <date>)`: one cell, found by its header, read again before the write and after.

**Rotating the secret**: regenerate the consumer secret in the External Client App, update the
GitHub secret, then start a manual run (apply unticked): the log must show `SF: plan` or
`SF: apply` and the counts.

**Off-boarding / stop**:
- `SF_SYNC=off` stops future runs; cancel a run already started in Actions.
- Turning the External Client App off, or deactivating GLOW Sync, removes the access entirely.

**Rollback of creates**:
- The accounts the sync made: `SELECT Id, Name FROM Account WHERE CreatedById = '<GLOW Sync's
  user id>'`.
- One is deleted only while it has no Contacts and no attendance, on Ryan's go.
- Dispatch: revert `Dispatch.gs` and restore a Contents token (not recommended).

**Local cross-check** (read only, Ryan's CLI login, VPN off):

```
python3 tools/sf_new_clubs.py check --vpn-off --roster data/roster_<stamp>.csv \
    --summary data/auto_sync/plan_<region>_<stamp>.json ...
```

It exits 0 when every club on those forms has its one right account. Partner-less strays are
reported only when all four regions are covered: give each region's summary, and
`--disabled <region>` for a region whose form is disabled.

## Duplicate girls in Salesforce

- **When:** the first days of each month; after a change to the names dictionary or the processor.
- **Status:** the first merge was done 2026-10-07 ([Result](plans/2026-10-07-sf-duplicate-girls.md#result-2026-10-07)).
- **Dry run:** `check`, `plan`, then `merge` without a flag.
- **Apply:** `merge … --apply --club <id>` per club; `--rehearse` too is Ryan's go.
- **Verify:** `check` exits 0.
- **Rollback:** "Rollback, per part", below.

([plan](plans/2026-10-07-sf-duplicate-girls.md); `tools/sf_dupes.py`.) The attendance processor
finds a ticked girl by her exact name (capitals ignored) among her club's contacts and creates a
contact when nothing matches. While the forms' names dictionary altered some names (a double
space; fixed 2026-10-06), every such submission made another contact of the same girl, each
holding part of her attendance. The tool finds them, proves each group against the Roster and
merges them with Salesforce's own merge, which moves every attendance row to the contact that
stays.

**VPN off** before any of it: every subcommand reads Salesforce from the Mac and refuses without
`--vpn-off` (see "Back-fill of attendance into Salesforce"). It prints counts, dates and record
ids, never a name.

### The monthly check

```bash
python3 tools/sf_dupes.py check --vpn-off --roster data/roster_<stamp>.csv
```

Read-only. Run it in the first days of each month (its batch check starts on the 1st of the
current month; `--since yyyy-mm-dd` for another start), and after any change to the forms' names
dictionary or to the attendance processor. Exit 0: clean; exit 1: a finding, listed per club by
record id:

- **(a) same name twice in one club** - one girl with two or more contacts (the key ignores
  capitals, spacing and invisible characters). Merge them (below).
- **(b) stored names with odd whitespace or invisible characters** - a contact whose next,
  correctly spelled tick will make a twin. `plan` lists it as a rename (below).
- **(c) batches whose name list has odd whitespace** - a form is sending altered names again: run
  `tools/form_status.py` and fix the names dictionary first ("The names dictionary and the
  module values"), then (a) and (b) follow.
- **(d) names in two or more clubs that the Roster does not have in each** (with `--roster`;
  every Roster row of each club, any status) - reported, never merged: a girl who moved club, two
  club accounts for one club (11 girls in "Las Camelias" and "Las Camelias Primaria", BACKLOG 77),
  or a namesake the Roster spells differently. A person decides.

### The merge (Ryan's go for every `--apply` and every `--rehearse`)

A rehearsal runs the merges' DML in production and then throws, so Salesforce rolls it back: it
leaves nothing behind, but it locks the club's records and runs NPSP's triggers meanwhile; the
live-gate hook asks on `--rehearse` like on any live command. Every `--apply` and `--rehearse`
reads Jotform first (no submission in the last 10 minutes) and the regional forms afterwards
(`merge`): put `JOTFORM_API_KEY` in `.env` or the environment, or it refuses before anything runs.

```bash
python3 tools/sf_dupes.py plan --vpn-off --roster data/roster_<stamp>.csv     # read-only -> data/sf_dupes_<date>/merge_plan.json
P=data/sf_dupes_<date>/merge_plan.json
python3 tools/sf_dupes.py merge $P --vpn-off                  # dry run: re-read, drift check, the Apex written, nothing run
python3 tools/sf_dupes.py merge $P --vpn-off --rehearse       # runs the Apex, then throws: Salesforce rolls it all back
python3 tools/sf_dupes.py rename $P --vpn-off --apply --roster data/roster_<stamp>.csv
python3 tools/sf_dupes.py merge $P --vpn-off --apply --club <account id>     # one club; read back; then the next
python3 tools/sf_dupes.py cleanup $P --vpn-off --dup-sets     # dry run
python3 tools/sf_dupes.py cleanup $P --vpn-off --dup-sets --apply
python3 tools/sf_dupes.py check --vpn-off --roster data/roster_<stamp>.csv    # exit 0
```

- **`plan`** groups a club's Participant contacts by the key and proves each group: the club
  account is exactly one active Roster club (compared as the processor compares names), the name
  is exactly one active girl of that club and spelled as the Roster spells her, the copies agree
  in name, club, role, description and creator, and no two copies hold a row on one date. The
  contact that stays is the back-fill's (`created_contacts.csv`) where there is one, else the
  earliest created (ties: the lowest id); the others go in merge calls of at most two. It prints a
  table per club and `groups N, extras N, same-date N, renames N, needs-a-person N`, and exits 1
  when anything needs a person: such a group is never merged by the tool (same-date pairs go to
  Ryan). Compare the counts with what you expect before going on.
- **`merge`** re-reads first and refuses any drift from the plan (contacts, their club, their
  rows by id, the club's participants, a new copy of a girl): make the plan again. `--apply` and
  `--rehearse` also refuse while a submission reached the Africa or Asia form in the last 10
  minutes, and between 20:30 and 21:30 UTC (NPSP's nightly job) - checked again before each further
  run - and write `merge_rollback.json` before the first run (a rehearsal too, though it records
  no merge). One anonymous-Apex run per club (`--per-run N` merge calls per run if a limit bites:
  each run prints `DIAG|limits|queries=..|dml=..|cpu=..`). The Apex checks everything again and
  any failed check aborts the whole run, so a club is merged completely or not at all. Only `DIAG|`
  lines are printed; the full debug log goes to `logs/` (it can hold names). After `--apply` it
  reads back (participants down by exactly the merged count, rows per date unchanged, every moved
  row on its contact, the merged contacts deleted with their master set). After `--apply` and
  `--rehearse` it compares the submissions on all four regional forms with the new batches of
  every club since the run began: **ATTENTION** (exit 2) when there are more submissions, or when
  the count cannot be made (e.g. Jotform's list did not come newest first) - look at the newest
  submissions and batches by hand.
  - "the rehearsal failed" / "the run failed ... Salesforce rolled it back": nothing changed; read
    the `DIAG|fail|...` reason (and the log file) before anything else.
  - "THE OUTCOME IS UNKNOWN": the CLI's answer was lost. Wait ten minutes, then run the same
    `merge --apply` again: it settles that run first. It refuses to settle when a merged-away
    contact is not even among the deleted ones (Recycle Bin emptied) or was deleted without being
    merged into its kept contact: look at it by hand.
  - "applied, but the read-back differs": STOP; look at the club in Salesforce.
- **`rename`** fixes a stored name with odd whitespace (collapsed, invisible characters dropped)
  when the result is exactly one active girl of that club and no other contact has her name; the
  dry run prints record ids and fields only. `--apply` refuses in the same 10 minutes after a
  submission and the same NPSP hour as `merge`. A girl whose odd contact got a twin is merged into
  her older contact and that one renamed (either order works).
- **`cleanup`** (after the merges): a kept contact's affiliations to its club down to one - the
  Primary one (NPSP's flag) where there is one, else the earliest - deleting only ones the plan
  recorded (anything else is refused). A further **Primary** affiliation (a merge moves the
  merged-away contact's over as it is) is left and listed ("leave ... a further Primary
  affiliation"): NPSP blanks the contact's Primary Affiliation when a Primary affiliation is
  deleted, even with another one to that club left. After each delete the contact's Primary
  Affiliation is read back; if it changed: STOPPED - set it back in Salesforce (both values are in
  the rollback file). `--dup-sets` deletes the plan's duplicate-rule sets left with at most one item
  (report data). Each record is saved in the rollback file before its delete. `--apply` refuses in
  the same 10 minutes after a submission and the same NPSP hour as `merge`.
- Everything is in `data/sf_dupes_<date>/` (never committed; owner-only): `merge_plan.json` (ids,
  dates, counts, and a sha256 of each rename's expected full name - never the name), `apex/` (ids
  only), `logs/` and `merge_rollback.json` (both can hold names).

### Rollback, per part

- **A merge**, within 15 days: undelete the merged-away contact (Recycle Bin; its id and kept
  contact are in `merge_rollback.json`), then delete the moved rows from the kept contact and
  insert them again on the restored one from the saved rows (new ids, created date and creator: a
  master-detail row cannot be moved by an update). After 15 days: a new contact from the saved
  fields, then the rows. Ryan's go.
- **A rename**: FirstName / LastName back to the saved `old` values (`renames` in the rollback file).
- **A deleted affiliation**: insert it again from the saved record (`deleted`). Duplicate-rule
  sets are report data and are not restored.
- `--rehearse` and a failed run leave nothing to roll back. Should a rehearsal ever keep a change
  ("not as before the rehearsal - LOOK AT IT NOW"), the rollback file holds the club's contacts as
  they were just before it.

## Attendance totals and partner-reported counts

- **When:** reading an attendance total; the monthly `check`; the three partners' monthly copy, about the 12th of each month.
- **Status:** the field and the processor change deployed 2026-10-07 03:22 UTC (Ryan's quick deploy `0AfRP000002gKqn0AE` of validation `0AfRP000002gKnZ0AU`), the one-off back-fill and the dashboard's totals done the same day; since 2026-10-15 ~09:05 UTC (Ryan's go, deploy `0AfRP000002h9dB0AQ`) the total counts Jotform plus the three partners below and nothing else ([Result](plans/2026-10-15-attendance-total-three-partners.md#result)); decided 2026-10-19 (BACKLOG 72, ticket #60): the three partners' figure is their Monthly Report's Monthly Max, copied monthly by `tools/sf_partner_monthly.py`; September 2026 copied on Ryan's go 2026-10-20 07:33-07:38 UTC: three `Partner report` batches dated 2026-09-30, 110 + 320 + 315 = 745, read back equal to the three Monthly Reports ([Result](plans/2026-10-19-partner-monthly-max.md#result)); decided 2026-10-19 (ticket #59): the dashboard's measure becomes girls who attended, Jotform girls plus the three partners' Monthly Max - built 2026-10-20, not deployed (awaits Ryan's go, in two phases: the field and the reports, checked against SOQL, then the dashboard; [plan](plans/2026-10-20-girls-attended-tiles.md)).
- **Verify:** the Signals, below.
- **Rollback:** of a monthly copy, from `data/sf_partner_monthly/ledger.csv` (each batch's last row is its state): delete an inserted batch by its `batch_id`, set an updated one's `Girls_Present__c` back to the row's `old` count - one record per call, VPN off, Ryan's go ([plan](plans/2026-10-19-partner-monthly-max.md#rollback)). Of #59's tiles, once deployed: "Attendance dashboard in Salesforce", Rollback. Of the 2026-10-15 rule, redeploy only the three components it changed from `data/sf_totals2_2026-10-15/before/`, after a fresh retrieve of them equals `after/` ("Attendance dashboard in Salesforce", Rollback); of the field and the processor's 03:22 UTC change (2026-10-16): never redeploy `data/sf_totals_2026-10/before/` - it would also undo the processor's name cleaning (2026-10-07 04:38 UTC); retrieve what is live and undo only that change in the copy (DECISIONS 2026-10-16). The name cleaning's own rollback ([plan](plans/2026-10-07-processor-name-spacing.md), Result): a fresh retrieve of the two classes and the trigger must equal `data/sf_processor_2026-10-07/after`, ignoring a missing final newline (Salesforce stores the test class without it; any other difference: stop and build from the retrieve); then redeploy the two classes of `data/sf_totals_2026-10/deployed/`. The fields can stay.

Three partners' clubs report their attendance through Salesforce only (Ryan, 2026-10-06). Since
2026-10-16 the three partners are marked `no` in the Partners tab's `jotform` column and their 38
clubs are off the template's and the Africa form's Club picker
([plan](plans/2026-10-06-clubs-off-jotform.md), [Result](plans/2026-10-06-clubs-off-jotform.md#result)):
since 2026-10-19 (ticket #60) their figure reaches the attendance data as their Monthly Report's
"Monthly Max", one batch per partner per month on the partner account (The monthly copy, below).
- **Double counting**: a partner's monthly batch plus Jotform batches from its clubs in the same
  month would both count. The Jotform path for these clubs is closed (none sent a batch since 1
  September), so the partner's figure counts once. If one of the three partners is unmarked again
  (its clubs back on the picker), the risk returns: stop copying its Monthly Max before its clubs
  submit on Jotform again.

Leadership wants one number that includes them (Ryan, 2026-10-15); since Ryan's decision of
2026-10-19 (ticket #59) that number is girls who attended.

**The field.** `Attendance_Batch__c.Girls_Present__c` (Number, "Girls present") is the one
attendance count. Since the deploy the attendance processor sets it when a Jotform batch
succeeds (= the attendance rows it created) and clears it on every `Failed` path; the three
partners' monthly copy writes their Monthly Max into it. A batch with no names and no count is `Failed` "No
participants submitted" (no rows, blocks nothing); a batch with no names and a count above 0 is
an aggregate and succeeds with no rows.

**The measure** (Ryan's decisions of 2026-10-19, ticket #59,
[plan](plans/2026-10-20-girls-attended-tiles.md); it replaces the two measures of 2026-10-15,
ticket #35):
- Total attendance (girls × sessions) is no longer tracked (Ryan, 2026-10-19). The headline
  measure is girls who attended in a month.
- **Girls who attended (Jotform + 3 partners)** = the Jotform girls who attended in the month,
  each girl once however many sessions she came to (unique `Attendance__c.Contact__c` over the
  month's `Attendance__c` rows from Jotform batches), plus the `Girls_Present__c` of the month's
  `Partner report` batches of the three partners Education and English for You, Tumaini La Maisha
  and Ng'aa Maskani (their Monthly Report's Monthly Max, copied by `tools/sf_partner_monthly.py`:
  The monthly copy, below).
- The two parts are added with no de-duplication: the partners report a number without names, and
  a club reports on one source only (the three partners' clubs are off the forms since
  2026-10-16, #56).
- This month's partner part is 0 until the three partners' Monthly Report is filed and copied,
  about the 12th of the next month: October's lands about 12 November, when October has become
  last month. So this month's tile shows the Jotform girls alone for most of the month.
- Months separate by `Attendance_Date__c` (the session date; a partner batch is dated the month's
  last day), never by when the batch was created: about 4,978 September-dated rows were created
  on 2026-10-02 (the September back-fill's 4,712 plus live submissions), which a report by
  created date would put in October.
- Any other club's attendance entered in Salesforce (a `Success` batch whose `Creator__c` does
  not start with `Jotform`, other than the three partners' `Partner report` batches) is left out
  of the tiles. A Jotform batch from one of the three partners' clubs counts in the Jotform part.
- The reports, the formula field and the filter that make the tiles: "Attendance dashboard in
  Salesforce".
- The deployed dashboard is the 2026-10-15 one until the #59 deploy: its filter 3 (a club whose
  parent is one of the three partners) misses the monthly copy, whose batch sits on the partner
  account itself, so September 2026's three copied batches (745) are in the data and outside its
  figures. Once #59 is deployed, the tiles read them through the report type
  `Attendance_Batches_and_Girls`.
- The Monthly Report's weekly counts are never added to attendance. Only the three partners'
  Monthly Max is copied, as one batch a month (below); every other partner's Monthly Report stays
  out (DECISIONS 2026-10-19).
- The Monthly Max is roughly the month's unique girls, the same kind of number as the Jotform
  girls, so the two parts add up to one figure; added to attendances (girls × sessions) it would
  have been a mixed sum, which is why the measure is girls who attended.

**The monthly copy** (`tools/sf_partner_monthly.py`, ticket #60,
[plan](plans/2026-10-19-partner-monthly-max.md); replaces the per-club intake contract of
2026-10-06). Each of the three partners files one Monthly Report a month (`DHIS2__c`,
`Account__c` = the partner account), between the 5th and the 12th of the next month; its
"Monthly Max" is `Monthly_Total__c`. After the three are filed (about the 12th) the tool writes
one `Attendance_Batch__c` per partner for the month:

| Field | Value |
|---|---|
| `Account_Name__c` | the partner's Salesforce Account name **exactly** (Education and English for You, Tumaini La Maisha, Ng'aa Maskani): the processor matches it against every Account, so the batch attaches to the partner account and creates none |
| `Attendance_Date__c` | the **last day of the month** |
| `Girls_Present__c` | the Monthly Max, a whole number above 0 |
| `Contact_IDs__c` | **empty** - no names, ever |
| `Creator__c` | `Partner report`: the tiles' partner part (`Partner_Girls__c`, once #59 is deployed); it never counts in a Jotform-only report, which takes only `Creator__c` values starting with `Jotform` |
| `enable_fuzzy_matching__c` | false |

```
python3 tools/sf_partner_monthly.py --month 2026-09 --vpn-off                         # dry run (default month: last month)
python3 tools/sf_partner_monthly.py --month 2026-09 --apply --vpn-off --limit 1       # Ryan's go: one write, read back
python3 tools/sf_partner_monthly.py --month 2026-09 --apply --vpn-off                 # the rest
```

- The dry run reads Salesforce too, so it needs `--vpn-off`; it prints each partner's plan by name
  and count (no record ids) and writes nothing. The current month or a later one is refused.
- Per partner, in the order above: no batch yet → insert; a `Success` `Partner report` batch on
  the partner account and day with the same count → skipped; with another count → an update of
  `Girls_Present__c` alone (old → new; a PATCH runs none of the processor). A `Failed` one does not
  count as existing.
- Refused, and named, with no write for that partner: no Monthly Report for the month or more than
  one, a Monthly Max blank, 0, negative or not whole, no single Account with the partner's exact
  name, two `Success` `Partner report` batches on its day, or - when it needs an insert - another
  `Success` batch (any other `Creator__c`) on the partner account and day. The other partners are still
  planned and written; the run ends non-zero. Fix the report in Salesforce (or ask the partner)
  and run again: what is in place is skipped.
- `--apply`: one insert or update per request, each read back (`Success`, on the partner account,
  the count); a write Salesforce refuses or that reads back otherwise stops the run. `--limit N`
  counts writes only. The ledger `data/sf_partner_monthly/ledger.csv` (owner only, never committed)
  keeps every write's batch id, partner, month, date, old and new count: the rollback (above).

The processor's club-and-day lock is per Account and date: any `Success` batch on the partner
account and the month's last day, whatever its `Creator__c`, would make the insert `Failed`
"Duplicate". The partner account has no Jotform batches, so none is expected; if one is there and
no `Partner report` batch is, the tool refuses that partner before sending (the others still go).

**The one-off back-fill** (`tools/sf_girls_present.py`) - **done 2026-10-07**, on Ryan's go:
every `Success` batch from before the deploy got its count (= its attendance rows; 573
written). Since then the processor sets it on every new batch, a second `set` finds `to set:
0`, and **`check` is the signal** (Signals, below). The commands and how the tool guards
each write: [plan](plans/2026-10-06-attendance-totals.md#from-the-runbook-moved-2026-10-09).

**Signals** (the field is deployed since 2026-10-07 03:22 UTC; all expected as stated):
- `python3 tools/sf_girls_present.py check --vpn-off` → `differ: 0, without a value: 0 -> OK`
  (true since the one-off back-fill, 2026-10-07: 575 Jotform Success batches then). A
  `differ` is a Jotform `Success` batch whose count is not its rows; a `without a value` is a
  `Success` batch the processor or the back-fill did not count. Aggregate batches are not compared
  (no rows by design).
- The dashboard's two tiles, once #59 is deployed (and its two reports between the deploy's two
  phases): each tile = `COUNT_DISTINCT(Contact__c)` over the month's Jotform `Attendance__c` rows,
  by the batch's date as the reports filter (`SELECT COUNT_DISTINCT(Contact__c) FROM
  Attendance__c WHERE Attendance_Batch__r.Attendance_Date__c = LAST_MONTH AND
  Attendance_Batch__r.Processing_Status__c = 'Success' AND Attendance_Batch__r.Creator__c LIKE
  'Jotform%'`; `THIS_MONTH` for the other tile) + `SUM(Girls_Present__c)` over the three partners'
  `Partner report` batches for the month (the monthly copy's query, next). Read 2026-10-20: last
  month 2,888 + 745 = 3,633, this month 2,893 + 0.
- **Open until the reports are deployed: the blank `Contact__c`.** The report type gives each
  batch without rows (the three partners' batches among them) one report row with a blank
  `Contact__c`, and whether the unique count ignores it is checked only then, in the reports'
  check between the two phases ([plan](plans/2026-10-20-girls-attended-tiles.md), Rollout step
  4): last month's report equal to the SOQL sum above means it is ignored; one more means the
  blank counts as a girl; 745 less means the Partner filter's `Parent` contains "" drops the
  partner batches. Either way stop and ask Ryan before the dashboard is deployed.
- Before the #59 deploy, the 2026-10-15 last-month tiles that #59 replaces equal `SELECT COUNT(Id)
  FROM Attendance__c WHERE Attendance_Date__c = LAST_MONTH` (September 2026: 7,227, read
  2026-10-15); filter 3 misses the partner account (above), so the copied 745 are outside them.
- The monthly copy, after its run: `SELECT Account__r.Name, Girls_Present__c, Processing_Status__c
  FROM Attendance_Batch__c WHERE Creator__c = 'Partner report' AND Attendance_Date__c = <the
  month's last day> AND Account__r.Name IN ('Education and English for You', 'Tumaini La Maisha',
  'Ng\'aa Maskani')` (SOQL escapes the apostrophe with a backslash) → three `Success` rows, one
  per partner, whose sum equals `SELECT
  SUM(Monthly_Total__c) FROM DHIS2__c` over the three partners' reports for the month (September
  2026: 110 + 320 + 315 = 745, read 2026-10-19); a second dry run says every partner unchanged,
  skipped. A refused partner is a Monthly Report to fix or chase (most often: not filed yet).
- Blank submissions: `SELECT COUNT(Id) FROM Attendance_Batch__c WHERE Status_Message__c = 'No
  participants submitted'` grows only with real blanks; each is a club to ask, not a day blocked.
- Club accounts without a parent: still exactly the two pilot accounts ("Club accounts in
  Salesforce"). One more after a monthly copy means a batch went out under a name no account
  carries.

## Attendance dashboard in Salesforce

- **When:** a new partner (the Partner filter), a new staff user (the permission set), a report change.
- **Status:** live since 2026-10-02 (`fix1` 2026-10-06, `totals1/` 2026-10-07; [Result](plans/2026-10-02-attendance-dashboard.md#result-2026-10-02)); the total counts Jotform plus the three partners since 2026-10-15 ~09:05 UTC ([Result](plans/2026-10-15-attendance-total-three-partners.md#result)); #59, the two "Girls who attended (Jotform + 3 partners)" tiles: built 2026-10-20 in `data/sf_girls_tiles_2026-10-20/build/`, not deployed (awaits Ryan's go, in two phases: the field, the permission set, the report type and the three reports, checked against SOQL; then the dashboard; [plan](plans/2026-10-20-girls-attended-tiles.md#rollout-live-two-phases-each-deploy-on-ryans-go)); the 2026-10-09 Access change (the folders shared, the permission set, "(test)" dropped from the labels) is deployed since 2026-10-09 ~05:35 UTC by the metadata dates, its deploy id not known here (read 2026-10-15; Access, below; [Result](plans/2026-10-09-attendance-reports-public.md#result-2026-10-09-build-and-check-only-nothing-deployed-no-record-written)).
- **Dry run:** the check-only deploy (`--dry-run`), step 4 of "The steps".
- **Apply:** the same without `--dry-run`, Ryan's go (VPN off).
- **Verify:** retrieve again and compare with the build; one report's totals against SOQL.
- **Rollback:** below.

Since 2026-10-02 the dashboard **"Jotform Attendance"** (dashboard folder Attendance,
DeveloperName `Jotform_Attendance_test`) shows the Jotform attendance as charts, built only
from data Salesforce already has ([plan and result](plans/2026-10-02-attendance-dashboard.md)).
Its label lost "(test)" with the 2026-10-09 Access deploy (below); the DeveloperName keeps it.

What it shows - the headline tiles (below), weekly and monthly charts, last month by partner and
by module, the clubs with no attendance or not submitting, the blank submissions - and how to
read its numbers (a session, a blank and "did not submit" defined; late submissions, so "last
month" settles around the 20th; a club without a partner; the refresh is a snapshot): [plan](plans/2026-10-02-attendance-dashboard.md#from-the-runbook-moved-2026-10-09).

**The headline tiles** (ticket #59, [plan](plans/2026-10-20-girls-attended-tiles.md); built
2026-10-20 in `data/sf_girls_tiles_2026-10-20/build/`, awaiting Ryan's go: this part says what the
dashboard does once it is deployed; its `BUILD.md` describes every component. The deploy has two
phases, each check-only first and on Ryan's go: the field, the permission set, the Admin profile
entry, the report type and the three reports (`build/package-phase1.xml`), whose two Metric
reports are checked against SOQL through the Analytics API before phase 2 deploys the dashboard
(`build/package-phase2.xml`; [plan](plans/2026-10-20-girls-attended-tiles.md), Rollout. The
summary formula's token and the `FORMULA1` chartSummary are unverified until the check-only: if
refused, fix the three reports and the dashboard the same way, in `BUILD.md`'s fallback order):
- Once #59 is deployed, the top row is two tiles headed "Girls who attended (Jotform + 3
  partners)", one for last month and one for this month so far.
- Each tile is the month's girls who attended, Jotform and the three partners together; how it is
  computed is in "Attendance totals and partner-reported counts".
- The four tiles of 2026-10-15 are replaced by these two; total attendance (girls × sessions) is
  no longer tracked (Ryan, 2026-10-19). Until the deploy, the 2026-10-15 top row is what is live
  ([plan](plans/2026-10-15-attendance-total-three-partners.md)).
- The monthly chart "Girls who attended per month (Jotform + 3 partners)" (the report
  `Girls_Attended_by_Month`, months since September 2026) replaces "Total attendance per month
  (Jotform + 3 partners)" in the same place; "Girls attending per month (Jotform only)" and every
  other component are unchanged.
- The "How to read this dashboard" box defines girls who attended as the Jotform girls, each girl
  once however many sessions she came to, plus the three partners' Monthly Max, copied in about
  the 12th of the next month. Its next bullet says "Jotform only" means the Jotform girls alone,
  each once, that attendances (girls × sessions) are no longer a headline number, and that the
  Monthly Report of any other partner is never added.
- **The new components:**
  - The formula field `Attendance_Batch__c.Partner_Girls__c` ("Girls (partner report)") =
    `Girls_Present__c` when `Creator__c` is `Partner report`, else 0 (a blank counts as 0). The
    permission set `Attendance_Report_Viewer` and the Admin profile each get Read on it.
  - The report type `Attendance_Batches_and_Girls` ("Attendance batches and girls") is
    `Attendance_Batch__c` with or without `Attendance__c` rows (an outer join on the lookup
    `Attendance__c.Attendance_Batch__c`), so a row-less batch (a partner's monthly batch) reaches
    the reports.
  - The reports `Attendance/Girls_Attended_Last_Month` and `Attendance/Girls_Attended_This_Month`
    (one tile each, grouped by partner) and `Attendance/Girls_Attended_by_Month` (the monthly
    chart, grouped by month) share the filter logic `1 AND (2 OR (3 AND 4)) AND 5 AND 6`: 1
    `Processing_Status__c` = `Success`, 2 the batch's `Creator__c` starts with `Jotform`, 3 it is
    `Partner report`, 4 the batch's account is one of the three partner accounts (by name), 5 and
    6 the unlocked Partner and Club filters.
  - Each report's summary formula `FORMULA1` ("Girls who attended (Jotform + 3 partners)") = the
    unique `Attendance__c.Contact__c` + the sum of `Partner_Girls__c`, the number the tiles and the
    chart show.
  - The dashboard `Attendance/Jotform_Attendance_test` itself: the two tiles, the chart and the box
    above.
- **Known limitation, the Partner filter**: the Partner filter set to one of the three partners
  shows only that partner's Jotform girls (0 since #56 took their clubs off the forms on
  2026-10-16), and its Monthly Max drops out, because the partner's batch sits on the partner
  account itself, whose parent is blank. Any other partner, or All, shows the right number.
- A renamed partner account drops out of filter 4 (it matches the names): rename the filter values
  with the account, on Ryan's go.
- **Reports no longer used** once #59 is deployed: `Total_Attendance_Last_Month`,
  `Jotform_Total_Attendance_Last_Month`, `Total_Attendance_by_Partner_by_Month` and
  `Jotform_Attendance_This_Month`. They are kept until Ryan decides which to delete (only this
  dashboard was retrieved, so another dashboard's use of them is unchecked).
- The signal for each tile (SOQL) and the open blank-`Contact__c` check: "Attendance totals and
  partner-reported counts", Signals.

**Filters:**
- The dashboard's **Partner** filter covers every component. It holds the 49 partner names
  that have clubs, typed in exactly (Salesforce allows 50 values per filter).
  - A new partner must be added by hand to **both** lists: the dashboard's `partners.json`
    (the Partner filter's `Parent.Name` values, below) and `glow/sf_partners.csv` (the partner
    map the automatic club accounts read, partner → its account; "New clubs' accounts,
    automatically"). Two lists of the same 49 partners, kept separate on purpose: one is filter
    text, the other account ids.
  - A renamed partner account makes its option show 0.
  - A 51st partner needs another layout, such as filter values by range.
- **Club and girl** are filters on the reports, not on the dashboard. Click a chart, then use
  that report's Club or Girl filter. Its chart follows.
- The reports' Partner, Club and Girl "contains" filters ignore capitals but **not accents**
  (tested 2026-10-02). In Salesforce, "Fundacion Bibliotec" has no accent and "Fundación
  Kaleidos" has one, so "Fundacion" finds only the first. Type the name as Salesforce spells it,
  or an unaccented part of it.

**Access** (Ryan's decisions of 2026-10-09,
[plan](plans/2026-10-09-attendance-reports-public.md); they reverse his 2026-10-06 "folder
sharing stays as it is"):
- **Status**: deployed 2026-10-09 ~05:35 UTC, by the metadata dates. The permission set
  `Attendance_Report_Viewer` and the report `Jotform_Monthly_Attendance_test` (now labelled
  "Jotform Monthly Attendance") were last modified 2026-10-09 05:35 UTC, and the dashboard's title
  had lost "(test)" before the 2026-10-15 retrieve (SOQL on PermissionSet, Report and Dashboard,
  2026-10-15). The deploy id is not known here; the check-only before it was `0AfRP000002gXhZ0AU`
  (5 of 5, 0 errors). Not checked on 2026-10-15: the folders' shares (the shares API, below), the
  set's assignments and the daily refresh.
- **Never redeploy `data/sf_dashboard_2026-10-02/public_2026-10-09/`**: it is superseded, and its
  dashboard would overwrite the 2026-10-15 one (the total as Jotform plus the three partners). The
  rollback of the 2026-10-15 change is its three changed components from
  `data/sf_totals2_2026-10-15/before/` (Rollback, below).
- **Both Attendance folders are shared as Viewer with All Internal Users**: `folderShares` View,
  `AllInternalUsers`, `Organization`. Never a guest or portal group.
  - The share opens everything in the folders, including the March pilot dashboard "Attendance"
    and its 5 reports.
  - The shares API (`GET /services/data/v62.0/folders/{id}/shares`) is the measure.
    `Folder.AccessType` reads `Hidden` even on a shared folder.
  - Whether a folder deploy replaces or adds shares is not documented. Deploy a folder only from a
    fresh retrieve, and remove a share in the folder's Share dialog.
- **"(test)" was dropped** by the same deploy (2026-10-09): "Jotform Attendance" and "Jotform Monthly
  Attendance". The DeveloperNames stay (`Jotform_Attendance_test`,
  `Jotform_Monthly_Attendance_test`), so the paths below are unchanged.
- **Permission set `Attendance_Report_Viewer`**, read only. The dashboard runs as Ryan and shows
  everything to anyone who opens it. A chart's report runs as the viewer, and Account and Contact
  are private (`Attendance__c` follows its Contact). The set gives:
  - Read on `Attendance__c` and `Attendance_Batch__c`;
  - View All on Contact and on Account;
  - Read on the 21 fields that the reports in both folders show, filter or group, the pilot
    reports included (22 once #59 is deployed: `Attendance_Batch__c.Partner_Girls__c`). The list is in the plan; the derivation is
    `public_2026-10-09/evidence/`.
  A filter on a field the viewer cannot read is dropped silently, or the report fails "Invalid
  Report". Every per-girl report filters on `Creator__c`: without it, the totals would include
  the March pilot rows.
  - **For** the 9 active GLOW Standard Users. One of them is "Portal Login", a shared login
    account, not a person. Ryan included it (2026-10-09), accepting that it sees every Account
    and Contact. The 8 staff already have Modify All on Account and Contact through
    `Portal_User_Login_Access`.
    - Assigning the set is a record write, done on Ryan's go after the deploy.
    - System Administrators need nothing.
  - **A new staff user**: Setup → Permission Sets → Attendance Report Viewer → Manage Assignments
    → Add Assignment. Without it, they see the dashboard with refused or empty reports behind it.
  - **A report change that uses another field**: add that field's Read to the set, or viewers
    lose the column or the filter.
- **Daily refresh** (not metadata): Ryan's Subscribe on the dashboard, Daily 05:00
  America/Los_Angeles. It runs as Ryan, the running user.
- **Girls' names inside Salesforce are fine** (Ryan, 2026-10-06, unchanged): anyone with access
  to Salesforce may see them, so the test report's name column and the Girl filter stay. This is
  about Salesforce only. Names still never go into the repo, logs, commits or the conversation
  (child-privacy).
- **Photos**: none in Salesforce since 2026-10-01; they are in Google Drive ("Photos", above).

**Changing it** (Ryan deploys; VPN off; nothing in this folder is committed):
- **`gen.py` is behind what is live: never use it as it is.** It builds `totals1/` (2026-10-07)
  and was not updated for the 2026-10-09 Access change or the 2026-10-15 change (the total as
  Jotform plus the three partners, the new report `Jotform_Total_Attendance_Last_Month`, the four
  tiles #59 replaces), nor for #59; a deploy of its build would undo them on the dashboard and the
  two Total reports. The 2026-10-15 change was made by editing a fresh retrieve
  (`data/sf_totals2_2026-10-15/before/`), and the deployed state was retrieved back into
  `data/sf_totals2_2026-10-15/after/` (0 differences from the build): that is what is live today.
  #59 was built the same way, from the fresh retrieve `data/sf_girls_tiles_2026-10-20/before/`
  (into `build/`). A change starts from a fresh retrieve of what is live and edits that (The
  steps, below).
- What built `totals1/` and the copies before it is in `data/sf_dashboard_2026-10-02/`. `gen.py`
  builds every report, the batch report type `Attendance_Totals` and the dashboard into `build/`,
  from:
  - `partners.json`: the Partner filter values;
  - `before/`: the test report as it was;
  - the deployed copies (`after/`, `fix1/`, `after2/`, `totals1/`): the dashboard's running
    user, read from the `<runningUser>` they all carry and never written down; copies that
    disagree stop the build, and the CLI login (`sf org display`) is read only while no copy
    exists;
  - `sfdx-project.json`.
  `--without-girls-enrolled` leaves `Girls_Enrolled__c` out of the type. `gen.py.after2` beside
  it is the previous generator (what built `after2/`), kept for comparison; `NOTES.md` says what
  `totals1` added and lists the tokens the first check-only validate was to settle.
- Settled by the `totals1/` deploy (2026-10-07; the plan's Build notes): the partner on a batch
  report is the via-lookup column `Attendance_Batch__c$Account__c.Parent` (Analytics token
  `Attendance_Batch__c.Account__c.Parent.Name`), for grouping and as the Partner filter's column;
  a **cross filter's date is the report's locale format** - `9/1/2026` (`gen.py` `SINCE_CROSS`),
  never ISO `2026-09-01` ("There are errors with your subfilters"); relative values such as
  `LAST_N_DAYS:14` pass as they are; a report's grouping is never also one of its columns
  (`MONTH_COLUMNS`: "You can't include groupings in the selected columns list").
- The other copies:
  - `before/`: the test report before any change (a deployable project);
  - `after/`: the first deploy (2026-10-02 03:46 UTC);
  - `fix1/`: the second change (deployed 2026-10-06 09:29 UTC);
  - `after2/`: what was live before `totals1/`;
  - `live_2026-10-07/`: the backup retrieved right before `totals1/` was deployed (the dashboard
    and the 7 reports then live);
  - `totals1/`: the attendance totals, the three "did not submit" windows and the blank report
    ([plan](plans/2026-10-06-attendance-totals.md) D; made from the build after the check-only
    validate, deployed on Ryan's go 2026-10-07 03:59 UTC (0AfRP000002gLJp0AM), 8 of 8
    components); what `gen.py` builds. Its six reports: `Total_Attendance_by_Partner_by_Month`
    00ORP000009c8ic2AA, `Jotform_Attendance_by_Partner_by_Month` 00ORP000009c8ia2AA,
    `Total_Attendance_Last_Month` 00ORP000009c8ib2AA, `Clubs_Not_Submitting_Last_14_Days`
    00ORP000009c8iY2AQ, `Clubs_Not_Submitting_Since_1_Sept` 00ORP000009c8iZ2AQ,
    `Blank_Submissions` 00ORP000009c8iX2AQ.
  - `data/sf_totals2_2026-10-15/`: the 2026-10-15 change (the total as Jotform plus the three
    partners). `before/` is what was live just before it (the dashboard, the reports
    `Total_Attendance_Last_Month`, `Total_Attendance_by_Partner_by_Month`,
    `Jotform_Attendance_by_Partner_by_Month` and the report type `Attendance_Totals`); the
    rollback deploys only the three of them the deploy changed (Rollback, below); `after/` is the
    read-back of the deploy (0 differences from the build).
- After a deploy, Salesforce writes `expandOthers` true on every report chart and drops or adds a
  few default attributes on the dashboard (for `totals1/`: `useReportChart` dropped,
  `showPicturesOnCharts` and the owner added, apostrophes escaped). A retrieve differs from
  `gen.py` only in those.
- **The steps:**
  1. Back up what is live: `sf project retrieve start -o glow` the reports below (the six
     `Jotform_*` of the first deploy; the six of `totals1/`, the two Total reports
     `Total_Attendance_Last_Month` and `Total_Attendance_by_Partner_by_Month` among them;
     `Jotform_Total_Attendance_Last_Month` of 2026-10-15; and the report type
     `Attendance_Totals`), the test report and the dashboard
     (`Dashboard:Attendance/Jotform_Attendance_test`), into a new dated folder (as
     `data/sf_totals2_2026-10-15/before/`). It is the starting point and, for only the components
     the change then makes, the rollback (Rollback, below); compare it
     with `data/sf_totals2_2026-10-15/after/` (or the latest read-back) to see whether anything
     changed in Salesforce since. Once #59 is deployed, the backup also takes its eight components
     (`data/sf_girls_tiles_2026-10-20/build/package.xml`), and the latest read-back is its
     `after/`.
  2. Copy that retrieve and edit the copy, only the files that change. A new partner's Partner
     filter value is in the dashboard's XML; add it to `partners.json` as well, so the lists stay
     one. Not `gen.py` (above).
  3. Keep only the changed files in a new folder with `sfdx-project.json` (as `fix1/`).
  4. Check-only: `cd` there, then `sf project deploy start --dry-run -o glow -d force-app`.
  5. Ryan's go; then the same command without `--dry-run`.
  6. Check after: retrieve again into a dated folder (as `after/`) and compare with the edited
     copy. Run one changed report through the Analytics API, and compare its totals with SOQL.

**Refreshing through the API** (the PUT is gated by the live gate: Ryan's go): `sf api request rest
'/services/data/v62.0/analytics/dashboards/01ZRP00000BE2TR2A1' -o glow -X PUT -b '{}'`.
- One partner's view: put `?filter1=<option id>` in the path. A `filters` list in the body is
  ignored, and each partner's view has its own cached results.
- Salesforce allows one refresh a minute.

**Rollback:**
- **The rule (Ryan, 2026-10-16: "I don't want to overwrite with an old package")**: every
  dashboard or report deploy, a rollback included, starts from a fresh retrieve of what is live.
  The only rollback for the 2026-10-15 change is the three components it changed, from
  `data/sf_totals2_2026-10-15/before/` (below); for #59, once deployed, the two components it
  changed, from `data/sf_girls_tiles_2026-10-20/before/`, and a `destructiveChanges.xml` for the
  five it created (below).
  Never redeploy an older package: `data/sf_dashboard_2026-10-02/`'s `before/`, `build/`,
  `after/`, `after2/`, `fix1/`, `totals1/`, `live_2026-10-07/`, `public_2026-10-09/`,
  `before_public_2026-10-09/`, or a `gen.py` build - each would overwrite later changes.
- Test report: superseded 2026-10-16 - do not redeploy `before/` (it would undo the 2026-10-09
  label). To undo a change to it, retrieve it, edit only that change in the copy, check-only,
  Ryan's go, deploy.
- The new components: delete them with a `destructiveChanges.xml`. Never delete
  `Jotform_Monthly_Attendance_test`; it predates this work. The new components are:
  - the reports `Jotform_Attendance_by_Week`, `Jotform_Attendance_by_Month`,
    `Jotform_Attendance_Last_Month`, `Jotform_Attendance_This_Month`,
    `Jotform_Sessions_by_Module_Last_Month` and `Jotform_Clubs_No_Attendance_Last_Month`;
  - the dashboard `Jotform_Attendance_test`;
  - since `totals1/` (2026-10-07): the reports `Total_Attendance_by_Partner_by_Month`,
    `Jotform_Attendance_by_Partner_by_Month`, `Total_Attendance_Last_Month`,
    `Clubs_Not_Submitting_Last_14_Days`, `Clubs_Not_Submitting_Since_1_Sept` and
    `Blank_Submissions`, then - **last**, after the six reports that use it - the report type
    `Attendance_Totals`; never `Attendance_Batches` (the vendor's report type). The dashboard
    itself is never rolled back by redeploying `after2/` or `live_2026-10-07/` (superseded
    2026-10-16: they would undo the 2026-10-09 and 2026-10-15 changes); before the six reports go,
    retrieve it, remove the `totals1/` tiles in that copy, check-only, Ryan's go, deploy (the six
    reports and the type may stay).
- The 2026-10-15 change (the total as Jotform plus the three partners, ticket #35): it changed
  three components, the dashboard `Attendance/Jotform_Attendance_test` and the reports
  `Attendance/Total_Attendance_Last_Month` and `Attendance/Total_Attendance_by_Partner_by_Month`
  (and created `Attendance/Jotform_Total_Attendance_Last_Month`). `data/sf_totals2_2026-10-15/before/`
  holds five components (also `Attendance/Jotform_Attendance_by_Partner_by_Month` and the report
  type `Attendance_Totals`, which that deploy did not change: never deploy those two from it);
  `after/` holds the four deployed. VPN off; first retrieve the three changed components fresh and
  compare them with the same files in `after/`; if any differs, someone changed it since - stop
  and build the rollback from that fresh retrieve instead. If they are equal: Ryan's go, then from
  within `data/sf_totals2_2026-10-15/before/` `sf project deploy start --dry-run -o glow -m
  "Dashboard:Attendance/Jotform_Attendance_test" -m "Report:Attendance/Total_Attendance_Last_Month"
  -m "Report:Attendance/Total_Attendance_by_Partner_by_Month"`, then the same without
  `--dry-run` (never `-d force-app` there: it would redeploy all five); retrieve the three again
  and compare with `before/`. The dashboard and the two Total reports then go back to the
  `totals1/` filter (every `Success` batch, from any club); revert ticket #35's RUNBOOK change
  with it. The new report `Jotform_Total_Attendance_Last_Month` may stay (the dashboard no longer
  references it after the rollback), or goes with a `destructiveChanges.xml` after the dashboard.
  Once #59 is deployed, the dashboard's fresh retrieve differs from `after/`, so this rollback
  stops at its check: roll #59 back first (next).
- The #59 change (the two girls-who-attended tiles), once deployed, [plan](plans/2026-10-20-girls-attended-tiles.md#rollback).
  `data/sf_girls_tiles_2026-10-20/before/` is the fresh retrieve of what was live on 2026-10-20
  right before it (its dashboard identical to what the 2026-10-15 deploy left). #59 changed two
  components, the dashboard `Attendance/Jotform_Attendance_test` and the permission set
  `Attendance_Report_Viewer` (and one read-only entry in the Admin profile, which goes with the
  field), and created five: the field `Attendance_Batch__c.Partner_Girls__c`, the report type
  `Attendance_Batches_and_Girls` and the reports `Attendance/Girls_Attended_Last_Month`,
  `Attendance/Girls_Attended_This_Month` and `Attendance/Girls_Attended_by_Month`.
  1. VPN off. Retrieve the dashboard and the permission set fresh and compare them with
     `data/sf_girls_tiles_2026-10-20/build/` (or with its read-back `after/`, once it exists;
     after phase 1 alone, the dashboard with `before/`); if either differs, someone changed it
     since - stop and build the rollback from that fresh retrieve instead.
  2. Equal: Ryan's go. From `data/sf_girls_tiles_2026-10-20/before/`, redeploy only those two
     files: copy `before/dashboards/Attendance/Jotform_Attendance_test.dashboard-meta.xml` to
     `<new folder>/force-app/main/default/dashboards/Attendance/` and
     `before/permissionsets/Attendance_Report_Viewer.permissionset-meta.xml` to
     `<new folder>/force-app/main/default/permissionsets/`, beside an `sfdx-project.json` (as
     `build/`'s), then within `<new folder>` run `sf project deploy start --dry-run -o glow -d
     force-app` and the same command minus `--dry-run`. After phase 1 alone, the permission set
     only. The rest of `before/` (the live reports, the report type `Attendance_Totals`, the
     object, the Admin profile) is never deployed from it.
  3. With the dashboard off the new reports, delete the five new components in three destructive
     deploys, in this order, each a `destructiveChanges.xml` beside an empty `package.xml`,
     check-only first, on Ryan's go:
     - first the reports `Girls_Attended_Last_Month`, `Girls_Attended_This_Month` and
       `Girls_Attended_by_Month` (`Report` members `Attendance/Girls_Attended_Last_Month` and so
       on; they may also go as the `--pre-destructive-changes` file of the report type's deploy);
     - then the report type `Attendance_Batches_and_Girls` (`ReportType`);
     - then the field `Attendance_Batch__c.Partner_Girls__c` (`CustomField`).

     Each deploy is its own folder holding an empty `package.xml` (`<Package>` with only
     `<version>62.0</version>`) and a `destructiveChanges.xml` listing that deploy's components,
     beside an `sfdx-project.json` (as in step 2) and the empty `force-app/` folder it names:
     `--manifest` needs an SFDX project.
     Within the folder, check-only: `sf project deploy start --dry-run -o glow --manifest
     package.xml --post-destructive-changes destructiveChanges.xml`; then Ryan's go and the same
     command minus `--dry-run`. The next deploy starts after this one succeeded.
  4. Retrieve the dashboard and the permission set again and compare with `before/`. The four
     reports #59 stopped using are back on the dashboard; revert #59's RUNBOOK change with it.
- Nothing else depends on them. The pilot "Attendance" dashboard and its reports were not
  touched, nor the vendor's report type `Attendance_Batches`.

## September back-fill: the resolver

- **When:** the first, read-only step of a back-fill ("Back-fill of attendance into Salesforce").
- **Status:** done for September 2026; its rows were sent 2026-10-02 ([plan](plans/2026-09-30-backfill-resolver.md), [Result](plans/2026-09-30-september-backfill.md#result-2026-10-02)).

`tools/backfill_resolve.py` (GET only) writes one row per (submission, ticked
roster) of the four regional forms to `data/backfill_2026-09/resolved.json`;
the club is the roster the mentor ticked girls in, never question 5. Its window
is September's: for another month, edit `SINCE`, `MONTH_START` and
`DEFAULT_OUT` at its top first. Its files hold girls' names and mentors'
contact details: they stay under `data/` (owner-only), and only the counts it
prints go into a plan or a message.

```bash
python3 tools/sheets_client.py export Roster data/roster_<date>.csv     # a fresh export, every time
python3 tools/backfill_resolve.py --roster data/roster_<date>.csv       # GET only; a few minutes (Africa)
```

How to read its report, its flags and its refusals: [plan](plans/2026-09-30-backfill-resolver.md#from-the-runbook-moved-2026-10-09).

## Back-fill of attendance into Salesforce

- **When:** Jotform submissions that never reached Salesforce (a dead connection, refused batches).
- **Status:** done for September 2026 on 2026-10-02: 361 batches, each read back; held on purpose then: 10 sessions of the five pilot clubs and Queens of Quest's 2 ([Result](plans/2026-09-30-september-backfill.md#result-2026-10-02)).
- **Dry run:** `backfill_resolve.py`, `sf_backfill.py snapshot`, `plan`, `send` (no `--apply`).
- **Apply:** `send --apply --vpn-off --limit 1`, then the rest, Ryan's go.
- **Verify:** `sf_backfill.py status`; every batch is read back as it is sent.
- **Rollback:** by id, never by a time window (below).

Never replay a submission as Jotform stored it: question 5 and the name list
were wrong on part of September, and Salesforce turns whatever it gets into
accounts, contacts and attendance at once. `tools/backfill_resolve.py` ("September
back-fill: the resolver") then `tools/sf_backfill.py` stay the procedure for a
new incident, but both are written for September: set the window first
(`SINCE`, `MONTH_START`, `DEFAULT_OUT` in `tools/backfill_resolve.py`; a new
folder for `tools/sf_backfill.py`, `--dir`, whose default is
`data/backfill_2026-09`), then follow the procedure as run:
[plan](plans/2026-09-30-september-backfill.md#from-the-runbook-moved-2026-10-09).

**Before anything talks to Salesforce from the Mac: VPN off.** Salesforce freezes a user whose
app or API connection comes from an anonymising VPN and revokes all their tokens, the Jotform
connection's included (it happened 2026-09-30 12:16 UTC). Only another administrator can
unfreeze; afterwards Jotform is re-authorised on the five forms and `integration_status.py` run.
The live commands of the procedure refuse without `--vpn-off`: the word that you checked.

- **Rollback**: by id, never by a time window. `ledger.csv` has every batch id,
  `created_contacts.csv` every contact a batch created. Remove the attendance rows of those
  batches, the batches, then those contacts - only with Ryan's go - and `close <key> --removed`
  for each.
  - **WARNING (since 2026-10-07): the back-fill's contacts now carry live rows.** Every girl
    ticked on a form since 2026-10-02 is booked on her existing contact, which is often the one
    the back-fill made, and after the duplicate merge ("Duplicate girls in Salesforce", above)
    the contact that stays is the back-fill's wherever a group had one. `Attendance__c.Contact__c`
    is master-detail: **deleting a back-fill contact deletes every attendance row on it, the live
    ones included.** Before removing a contact listed in `created_contacts.csv`, count its rows
    whose batch is not in `ledger.csv`; if there is any, do not delete that contact (remove only
    the back-fill's own rows and batches). A guard in `sf_backfill.py` for this is BACKLOG 78.

# Admin and work log

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
  variable `AUTO_SYNC_APPLY` (`0` = dry runs only, `1` = writes). For the new
  clubs' Salesforce accounts also the secrets `SF_CLIENT_ID` and `SF_CLIENT_SECRET`
  (the consumer key and secret of the External Client App "GLOW Sync", whose client
  credentials log in as the integration user GLOW Sync) and the variable `SF_SYNC`
  (`off` / `plan` / `apply`; changing it is Ryan's go): "New clubs' accounts,
  automatically".
- **Salesforce from the Mac** — the Salesforce CLI's login, alias `glow`
  (`sf org login web --alias glow`, by Ryan); check it with
  `sf org display --target-org glow`, which hides the secrets. Never run
  `sf org auth show-access-token`, `show-sfdx-auth-url` or `show-user-password` in
  a Claude session, and never set `SF_TEMP_SHOW_SECRETS`: they print the token.
  **VPN off before any `sf` command or other call to Salesforce**: Salesforce
  freezes a user whose connection comes from an anonymising VPN and revokes all
  their tokens, the Jotform connection's included (2026-09-30); only another
  administrator can unfreeze, and Jotform is then re-authorised on the five forms
  (`integration_status.py`). The Mac tools that talk to Salesforce refuse without
  `--vpn-off`, the word that you checked ("Back-fill of attendance into
  Salesforce").
- **Salesforce records by hand** — the Claude session's write connector, one record
  per call, never by a subagent, only on Ryan's go; no hook sees those calls
  ("Club accounts in Salesforce").

## Live gate (Claude Code)

Three hooks in `.claude/hooks/`, wired in `.claude/settings.json`, guard what
Claude runs and writes. The hooks are the source of truth (their header
comments list every case); this is the summary.

**`live_gate.sh`** (every Bash command) puts a command that can change a live
system to Ryan as an approval prompt in the session (a PreToolUse `ask`); his
answer is the go. Nothing pre-approves one and the hook never answers `allow`;
since 2026-10-14 `GLOW_LIVE_OK` no longer opens the gate (DECISIONS 2026-10-14).
Live:

- the tools' write flags: `--apply`, `--prune`, `--rehearse` (`sf_dupes.py`'s
  production run, rolled back), `clasp push` / `clasp:push`, and
  `sheets_client.py import` (a subcommand removed 2026-10-09, still in the pattern);
- the raw APIs the tools wrap: `api.jotform.com`, the Sheets writes
  (`values().update|append|clear`, `batchUpdate`, `apply_changes=True`);
- Salesforce through `sf` or `sfdx`: a deploy (`project deploy
  start|quick|validate`, a check-only one too; `deploy metadata`), `project
  delete source`, `data create|update|delete|upsert|import`, `apex run`, the
  `force:` apex, source, mdapi and data commands, the REST API itself
  (`.salesforce.com/services/`), `sf api request graphql`, and `sf api request
  rest` with a method other than GET, a body (`-b`) or a request file (`-f`);
- the automatic sync's switches on GitHub: `gh variable|secret
  set|delete|remove`, `gh workflow enable|disable`, `gh workflow run` that
  applies (`apply` true, inputs from a file or as JSON), `gh run rerun` (a
  `-R`/`--repo` may stand between the words);
- `gh api` writes and reads alike where the sync's switches live: a command with
  a `gh` word, the word `api`, and `actions/`, `dispatches` or `graphql`
  anywhere - the Actions API (variables, secrets, workflows, runs), a repository
  dispatch, GraphQL (a mutation can hide in a query file) - whatever the method;
  so is `api.github.com/…` on those paths (curl, a script). Every other `gh api`
  call (issues, comments, labels, the harness's reads) is ungated.

The patterns are matched as text, never parsed: in any case, on the command on
one line, with each backslash-newline removed, and with quotes and backslashes
removed (`gh 'workflow' run`, `--ap""ply` match). Text that only names a live
command (a commit message, a PR body, a heredoc) asks too. A read-only command
that only mentions a flag passes: its first word is `grep`, `rg` (not `--pre`),
`cat`, `head`, `tail`, `wc`, `ls`, or `git log|show|diff|grep|blame|status`,
and it has no `;`, `&`, `|`, backtick, `$(`, `<(`, `>` or line break.

Refused outright (a `deny`), whatever the mode:

- a self-approval: a command that sets `GLOW_LIVE_OK`, or writes a file the
  next launch takes its environment from (`~/.zshrc` and the other shell
  startup files, `.envrc`, `.env`: a redirect, `tee`, `sed -i`, `perl -i`), or
  `launchctl setenv`;
- a live command from a subagent (an `agent_id` in the hook's input): the main
  session asks Ryan;
- a live command in a session that cannot prompt: a permission mode other than
  `default`, `acceptEdits`, `auto` or `plan` - `bypassPermissions`, `dontAsk`,
  a missing or unknown one. Run it in an interactive session, or Ryan runs it
  in his terminal.

A headless or dispatched run (`claude -p`) in one of the four prompting modes,
`default` for one, gets the hook's `ask`, and Claude Code denies it, since no one
can answer the prompt: a headless run never runs a live command, whatever its
mode (DECISIONS 2026-10-14).

Every decision on a live command is appended to `.claude/live_gate.log`
(gitignored) with its mode: `ASKED` for the hook's `ask`, `BLOCKED` for its
refusal (also when no decision could be built; the hook then exits 2). `ASKED`
means a prompt was shown only in an interactive session: a headless run's ask is
logged `ASKED` too, though Claude Code denied it and nothing ran.
`.claude/settings.json` backs the hook: `ask` rules for the live families (`npm
run clasp*`, `npx clasp`, `gh variable|secret set|delete`, `gh workflow run|enable|disable`, `gh
run rerun`, `sf project deploy start|quick|validate|resume`, `sf apex run`, `sf
data create|update|delete|upsert|import`), and `onFailure: block`, so a hook
that fails stops the command. `Bash(gh api:*)` is in `allow` (the harness reads
with it): any other `gh api` call runs without a prompt, while the hook's `ask`
still prompts on `actions/`, `dispatches` and `graphql`.

The hook is a seatbelt, not the go: it reads the command's text, so a write
through another program, a flag assembled at run time, and the session's
connector tools (Salesforce through claude.ai) are not seen - it guards against
mistakes, not intent. Before answering yes: read the dry run and check the
backup exists. Running commands yourself in a terminal is never affected.

**`protected_paths.sh`** (every Edit and Write) blocks an edit of anything under
`data/`, `backups/` or `credentials/` (its `README.md` and
`config.example.json` excepted), a `.env` or `.env.*` file (not `.env.example`),
`appsscript/Regions.gs` (hand-kept data since 2026-10-09, edited by Ryan; the
hook's message still calls it generated), and `.claude/settings.json`,
`.claude/settings.local.json`, `.claude/live_gate.log` and `.claude/hooks/` -
the project's and the user's (`~/.claude/`) - in any checkout (the main one, a
worktree, a sibling clone), matched on path components, ignoring case, with
symbolic links resolved. **`secret_scan.sh`** runs `scripts/check_secrets.py` on
every file Claude writes; `.githooks/pre-commit` (`make hooks`) does the same for
the added lines of every commit, plus ruff on the staged `.py` files.

## Work log and invoices

- **When:** the end of every working session (`update`), month end (the work-log chore PR lands,
  then `export`), after travel (`zone`).
- **Status:** in use since 2026-09-28 ([Result](plans/2026-09-28-worklog.md#result)); the harness
  plugin's `harness-worklog` replaced the repo's own work-log tool on 2026-10-14, after
  reproducing every row byte for byte.

This is contract work, invoiced monthly from `worklog/worklog.csv` (date, hours, blocks,
description, source, zone). `harness-worklog update` recomputes the hours from Claude
Code's session transcripts: all sessions merged into one timeline, cut into blocks wherever
nothing happened for 30 minutes, a block counting only if Ryan wrote in it (an agent working
alone is not billed), each block on the day it **started** (a session past midnight stays on its
first day), each day rounded to the quarter hour. It keeps a written description, fills an empty
one from the commits made during that day's blocks, and never touches `manual` rows. It
recomputes the last 14 days, reaching back to the last logged day when the log is behind (never
past 29 days), or from `--since`. Claude Code deletes a session's transcript about 30 days after
its last activity, so run `update` at the end of every session (`/harness:worklog` at the end of
every session runs it). `harness-worklog describe --date <yyyy-mm-dd> --text "…"` writes a day's
client-facing description (`/harness:worklog` does this after `update`). Work outside Claude
Code: `harness-worklog add --date 2026-09-29 --hours 1.5 --description "…"`.
At month end, once the month's chore PR has landed (below):
`harness-worklog export --month 2026-09 [--rate 60] --out invoice-2026-09.csv`.

**Committing the log and the handoff (one chore ticket a month).** `branch_guard` refuses
commits on `main`, so `worklog/worklog.csv` and `docs/agent/handoff.md` reach it through a
ticket (DECISIONS "2026-10-14 — The work log and the handoff reach main through a monthly chore
ticket"):

1. During the month `/harness:worklog` (`harness-worklog`) and `/harness:handoff` write both
   files in the main checkout, which stays dirty on those two paths: the log finds its
   transcripts through the main checkout's path, and the session brief reads the handoff there.
   A `harness-worklog` run inside a ticket worktree uses the main checkout's log anyway;
   `--repo <main checkout>` is for a run from outside the repository. Other pull requests never
   change the two paths, so they land while the main checkout's copies are dirty.
2. One ticket a month, titled "Commit the work log and handoff, YYYY-MM", its body the previous
   month's with the dates changed:
   `harness-board task create --title "Commit the work log and handoff, YYYY-MM" --type chore --size S --no-tests --needs-local --body-file <file>`.
   `--no-tests` because on a ticket branch `tests_first` counts `worklog/worklog.csv` as source
   (`*.csv` is not exempt).
3. Its session runs `harness-work start N` (worktree `.claude/worktrees/t-N-<slug>`, branch
   `t/N-<slug>`), copies both files from the main checkout into the worktree, runs
   `scripts/verify.sh`, commits, pushes and opens the PR. Later sessions refresh the PR the same
   way (copy, commit, push); it stays open until month end.
4. Month end (Ryan, before invoicing), in this order: the month's last `/harness:worklog`; a
   final refresh of the PR; `cmp <main checkout>/<path> <worktree>/<path>` prints nothing for
   both paths (if it prints anything, refresh first); `/land-checks` (its step 5 repeats the
   `cmp`).
5. `/harness:land`. It restores the main checkout's copies that are byte-identical to the landed
   content before it fast-forwards `main` (since Harness e372870), so the main checkout ends
   clean; a copy that differs blocks the pull ("main not pulled") instead of being lost. By then
   the PR is merged and its worktree and branch are gone: copy the two files aside, Ryan runs
   `git checkout -- worklog/worklog.csv docs/agent/handoff.md` by hand in the main checkout
   (`branch_guard` refuses Claude's on `main`), `/harness:land <PR>` again (a merged PR resumes at
   the fetch and fast-forward), then copy the two files back; next month's chore carries the
   newer rows.
6. After the land: `harness-worklog export --month YYYY-MM [--rate N] --out invoice-YYYY-MM.csv`,
   then create next month's ticket (step 2).

**Time zones.** Days are counted on the clock the Mac showed at the time, which moves when Ryan
travels. `worklog/timezones.csv` records it (`since` = a UTC instant, `zone` = an IANA name like
`Asia/Tokyo` or an offset like `+03:00`, `evidence`), so a past day never moves when the Mac
does. `update` refuses in two cases, and says what to run:

- the Mac's own zone (read from `/etc/localtime`, whatever `TZ` the shell sets) is not the
  timeline's zone now → record the switch:
  `harness-worklog zone --since <instant> --zone <IANA name>`. Any moment between the
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

`harness-worklog zone` (no arguments) shows the timeline, the Mac's zone and the commit
offsets since the last row.

**Which sessions count.** `update` reads this project's transcript folders only
(`~/.claude/projects/` + the main checkout's path, every character other than a letter or a
digit as `-`, and one folder per ticket worktree under `.claude/worktrees/`, kept after the
worktree is removed). It resolves the repo from `--repo`, else `$CLAUDE_PROJECT_DIR`, else the
git top level, and a linked worktree stands for its main checkout (since Harness 07a4835): a run
inside a ticket worktree reads and writes the main checkout's log; `--repo <main checkout>` is
for a run from outside the repository.
A session started from another folder - the home folder, say - is not counted,
whatever it worked on.
On 2026-10-09 that happened twice (the attendance-reports work and the repo-cleanup
session): the day's row holds only the hours of the sessions started in the
repository. `--transcripts <folder>` reads that folder **instead** (every session in
it counts, whatever its project), and with it no logged row changes or is dropped
without `--rewrite-old`; a day whose work is split between two folders is therefore
Ryan's call (a recount from one folder, or a `manual` row for the other's hours).
Start working sessions from the repository.

**What `update` will not do without being asked.** It refuses when a day before the window would
change (work that moved across the window's edge, or a day never logged) and names the `--since`
to use. It refuses to drop a row that lost all its work until `--drop-stale` is given (then move
that row's written description to the new day by hand, and refresh the descriptions of the days
whose blocks changed). A row older than 29 days, or any row when reading another folder with
`--transcripts`, is never dropped and never changed - one of its sessions may have expired - and
is reported as kept; `--rewrite-old` lets a deliberate correction through when the transcripts are
known to be complete. The 2026-09-30 correction (`docs/plans/2026-09-30-time-zones.md`) re-cut
September this way: Sep 1-14 had been counted at +08:00 although the Mac was on +02:00/+03:00.

# Offline checks

## Checks

```bash
make check      # everything offline: lint, JS and Python tests, .gs checks, secrets, links, doc references, conflict markers, fixture
make hooks      # once per clone: the pre-commit hook (secret scan, ruff) and the commit message template
make docs-index # after adding a plan or an intent, or changing a status: rewrite docs/plans/README.md
make help       # the individual targets
```

Real-data parity runs automatically when `data/enrollment_2026-08-24.csv`
exists (`CSV=<path>` to point elsewhere, `PARITY_REAL=0` to skip).
