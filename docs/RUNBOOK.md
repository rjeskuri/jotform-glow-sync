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
  - [Session notes on the attendance forms](#session-notes-on-the-attendance-forms)
  - [Header logo](#header-logo)
  - [Photos](#photos)
  - [Photo mover](#photo-mover)
  - [Disabling a regional form](#disabling-a-regional-form)
  - [Building a new regional form (not maintenance)](#building-a-new-regional-form-not-maintenance)
- [Clubs](#clubs)
  - [Renaming a club](#renaming-a-club)
  - [Moving a club to another partner (a mistyped partner)](#moving-a-club-to-another-partner-a-mistyped-partner)
  - [Club names two partners share](#club-names-two-partners-share)
  - [Club names that look alike](#club-names-that-look-alike)
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
  - [Submission timing in Salesforce](#submission-timing-in-salesforce)
  - [Session notes in Salesforce](#session-notes-in-salesforce)
  - [Monthly Report dashboards in Salesforce](#monthly-report-dashboards-in-salesforce)
  - [Interactive dashboard in Salesforce](#interactive-dashboard-in-salesforce)
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
second, so mentors submit one per day (DECISIONS 2026-10-13). Since 2026-10-22 (#108) a
re-submission of that same session - the same module - is merged into the day's batch instead,
adding only the girls not yet on it ("Attendance totals and partner-reported counts", A mentor's
correction); a different module stays "Duplicate".

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
  a `Success` batch, with the event as the module. It arrives `Failed` "Duplicate" - the event's
  module is not that day's session's, one session per club per day (since 2026-10-22 only a
  re-submission with the same module merges) - with `Module__c` = the event's text and
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
- **Rollback:** each write saves the form's whole store before its POST, to `backups/translations/<form>-<stamp>-before.json` (mode 600, never over an earlier file); without that file `glow/translations.py` sends nothing. Since 2026-10-09 that includes `add_language.py` and `restore_translations.py`, which used to POST without it. To put a saved store back: `python3 tools/restore_translations.py --form <id> --from-file backups/translations/<id>-<stamp>-before.json` (a dry run: per language how many keys differ, are added, are removed), then the same command with `--apply` on Ryan's go (the current store saved first, each differing language posted whole, re-read: RESTORED or MISMATCH).

```bash
python3 tools/add_translations.py --audit                 # which labels lack translations
python3 tools/add_translations.py                         # preview (uses tools/translations_additions.json)
python3 tools/add_translations.py --apply
python3 tools/add_language.py --code or --name Oriya --dict tools/translations_or.json          # preview
python3 tools/add_language.py --code or --name Oriya --dict tools/translations_or.json --apply
python3 tools/restore_translations.py --form <clone id> --check   # after a clone: is the switcher intact?
python3 tools/restore_translations.py --form <id> --from-file backups/translations/<id>-<stamp>-before.json   # put a saved store back: dry run
python3 tools/restore_translations.py --form <id> --from-file backups/translations/<id>-<stamp>-before.json --apply   # on Ryan's go
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
roster change meets it first. Place it only after the session-notes field
(on all five forms since 2026-10-26, task #105; "Session notes on the
attendance forms"): the notes go on first,
because placing this link leaves Submit sharing an order with the hidden field
below it, and `add_session_notes.py` then refuses on the tie. Adding,
re-checking or removing one:

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

## Session notes on the attendance forms

- **When:** placing, re-checking or removing the optional session-notes field; `form_status` says `session notes: absent` once the field is expected, or flags one (`!!` lines naming `sessionNotes`).
- **Status:** live on all five forms since 2026-10-26, the label translated in every language each form offers ([plan](plans/2026-10-25-session-notes.md), status done; ticket #105, on Ryan's go): the template q489, Africa q476, Asia q457, Latin America q454 and the disabled U.S q446, each CLEAN. `glow/layout.py` `NOTES_EXPECTED` is `True` from #105's land on (a form without the field is then NOT CLEAN); the runner's first run after the land is still to be read for in-sync (plan, Result). The limit is `entryLimit` `Letters-1000`, verified by the template write's re-read. Neither e-mail shows the notes yet: ticket #148 adds them to both (below).
- **Dry run:** `python3 tools/add_session_notes.py --form <id>`, then `python3 tools/add_translations.py --form <id>`.
- **Apply:** per form, after `python3 backup_forms.py --form <id>`: `python3 tools/add_session_notes.py --form <id> --apply`, then its translations with `python3 tools/add_translations.py --form <id> --apply` (GET, merge, POST; the store saved first), the template first.
- **Verify:** the tool's re-read after the write; `python3 tools/form_status.py --form <id> --roster data/roster_<date>.csv --partners data/partners_<date>.csv --rendered` (`session notes: present`, `layout:`, CLEAN); once all five carry it, `python3 tools/add_translations.py --audit` (the label untranslated nowhere; the audit truncates its lists, so the 2026-10-26 rollout's proof was a direct read of each form's store, plan Result).
- **Rollback:** `python3 tools/add_session_notes.py --form <id> --remove --apply`, the questions snapshot, or Revision History. A language a translations POST damaged (`MISMATCH after write`) comes back from the translation store that POST saved first: `python3 tools/restore_translations.py --form <id> --from-file backups/translations/<id>-<stamp>-before.json` (a dry run: per language how many keys differ, are added, are removed), then the same command with `--apply` on Ryan's go (the current store saved first, each differing language posted whole, re-read: RESTORED or MISMATCH; [plan](plans/2026-10-25-session-notes.md), Rollback).

One textarea named `sessionNotes` on every attendance form, found by its name
(the qid differs per form): the label "Additional information about this
session (optional)", no sub-label, 1,000 characters, not required, not hidden,
no rule (Ryan's answers, 2026-10-22; `glow/layout.py` `NOTES_PROPS`). It sits
after the last roster and above the links and Submit, so a mentor meets it
once her girls are ticked. The sync leaves it alone: no generated rule names
it, `--prune` deletes rosters only, and a roster the sync creates afterwards
goes above it (the field is the first element of the fence `glow/layout.py`
guards, like the links and Submit; test-pinned). Mentors' notes are free text
that can name girls: no tool prints a submission's notes, counts only.

The e-mails (ticket #105; [plan](plans/2026-10-25-session-notes.md), Result). Mentors' notes
can name girls, so Ryan decided per e-mail, on 2026-10-26: the notes go in both. The staff
notification e-mail ("Notification 1", to GLOW's fixed staff address) carries them, and so does
the mentor's confirmation (the autoresponder, to the address she typed). Both are custom bodies
that list fixed fields (read in the template's builder, Settings, Emails, 2026-10-26), and
Jotform rebuilds only a default body when questions change, so today neither shows the notes:
they are in Jotform's submissions only. Ticket #148, Ryan's by hand in the builder after #105
lands, adds `{sessionNotes}` to both bodies on each of the five forms (ten bodies).

The label is translated in every form language (`tools/translations_additions.json`, and the
Odia, Hindi and Persian files; written by us, not native-reviewed): per form, the translations
go on right after the field, since `tools/add_translations.py` posts a string only to a form
that shows it.

```bash
python3 tools/add_session_notes.py                                     # dry run, template + 4 regionals
python3 backup_forms.py --form 262352490535154
python3 tools/add_session_notes.py --form 262352490535154 --apply      # the template first; open its page
python3 tools/add_translations.py --form 262352490535154               # dry run: one new entry per language
python3 tools/add_translations.py --form 262352490535154 --apply       # the store saved first; GET, merge, POST
python3 tools/add_translations.py --audit                              # after all five: nothing untranslated
python3 tools/add_session_notes.py --form <id> --remove --apply        # take it out again (the rollback)
```

The tool plans all five forms before it writes any. The field goes at an
empty order between the last roster and the first link, where nothing moves
whether Jotform inserts or ties. The live forms had none before the
2026-10-26 rollout (the 2026-09-30 repair put the links, Submit and the hidden
bridge fields at the orders right after the last roster, and every roster
inserted since kept them there), so the tool first made room the way
`add_feedback_link.py` does (Ryan, 2026-10-23): the first link through Submit
and the hidden fields at the orders right after move one down, bottom-up so
each lands on an empty order (the path Jotform keeps exactly), then one create
at the freed order - ten writes per form (9 moves and the create), each
printed as `move <name> (qN) a -> b`. So the
sequence matters: **the session notes go on before the Club Roster Form link**
(`add_feedback_link.py --link roster`, BACKLOG 46; "Links above Submit"), whose
placing leaves Submit sharing an order with the hidden field below it. After
that link the tool refuses on the tie, naming both questions: take the link
out (`--link roster --remove --apply`), add the notes, then place the link
again - it goes directly above the problem link, below the notes
(test-pinned). Refuses rather than guesses: two fields of the name, the field
below a link or Submit or a roster below it (move it in the builder, or
`--remove --apply` and add it again), a hidden link or Submit, anything a
mentor can see between the last roster and Submit besides the links and
Submit, two questions of the tail sharing an order. A drifted flag or text
(`required`, `hidden`, the label, the limit, a sub-label) is set back in place
in one write (`UPDATE <property>: old -> new`); re-running is a no-op. With
`--apply` each form is snapshotted first (`backups/<id>/questions-<stamp>.json`),
then re-read: the field exactly once, its properties, every move landed, its
place, no rule mentioning it - a mismatch stops the tool there, non-zero,
naming that form's snapshot; the forms after it are neither snapshotted nor
written, the forms before it stay written and verified.

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
integration into the My Drive of Ryan's company account (Ryan, 2026-10-21: Jotform uses only
that account), folder `Attendance photos - <Region>`, one subfolder per submission named
`{Club Name} {Date}` (since 2026-10-30, e.g. `Sunrise Club 10-30-2026`; before that the club
name only), uploaded files only, no PDF (the PDF renders every ticked
girl's name). The photo mover then moves each subfolder into that region's folder on the
company Shared Drive ("Photo mover", below). The photo stays required on the forms. The photos
before <date> (677 by 2026-10-06) are in Jotform only, behind its login. Sharing: the owner and
<named list>. Retention (the CEO's decision, approved 2026-10-30 per Ryan; DECISIONS
2026-10-30): photos on the company Shared Drive go to its trash 90 days after they arrive,
trash only, never deleted for good; the photo mover does it, under every region folder, never
the region folders themselves ([retention plan](plans/2026-10-30-photo-retention.md)). Nothing
is deleted from Drive until the photo mover's retention is live. Jotform keeps its own copy
(Auto Delete Submissions stays off, BACKLOG 68).

`python3 tools/integration_status.py` reads every form's integration: an `ok (one action, …,
Account_Name__c from q5, …, no upload)` line is right, a mapped photo reads `NOT RIGHT: the
upload field is ['19'], not []`, and `other integrations:` lists the other blocks the form
carries - the Google Drive block's key once step 2 is done (whether the API shows the block at
all is unverified until then; `none` on every form on 2026-10-06). A form with the session
notes mapped (ticket #106) reads `ok (one action, 9 fields, Account_Name__c from q5,
Session_Notes__c from q<N>, no upload)`, q<N> being that form's own question named
`sessionNotes` (found by its name: the qid differs per form); a notes mapping from any other
question is `NOT RIGHT`. Until step 1 below the template stays `NOT RIGHT` on its upload row
(exit 1) whatever its notes: only a `Session_Notes__c` line there is the notes' concern. Since
2026-10-26 `NOTES_MAPPING_WANTED` in the tool is True: a live form without the mapping is `NOT
RIGHT`, except one whose `status` is exactly `DISABLED` (the U.S form), which reads `ok (one
action, 8 fields, Account_Name__c from q5, Session_Notes__c not wanted (form DISABLED), no
upload)` ("Session notes in Salesforce").

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
   `ok (one action, 9 fields, Account_Name__c from q5, Session_Notes__c from q<N>, no upload)`
   (the U.S form, DISABLED: 8 fields, `Session_Notes__c not wanted (form DISABLED)`),
   `integration: ok`. Until this step the template reads `NOT RIGHT: the upload field is
   ['19'], not []`.
2. **Template, Google Drive**. Before: `python3 backup_forms.py --form 262352490535154`. Then
   Settings → Integrations → Google Drive → Authorize → log in as Ryan's company account (the
   one the photo mover runs on) → Folder Name `Attendance photos - Template` (the photo mover's
   source folder, made at its setup before this step: "Photo mover") → Create Subfolders for Submissions ON,
   name = the "Club Name" field that is **question 5** (the hidden text field; the builder shows
   the Club picker under the same label - prefer the hidden one; if only the picker is offered,
   use it and say so in the plan's Result), a space, then the "Date" field (question 17,
   mmddyyyy with `-`) - the setting reads `{Club Name} {Date}`, as on every active form since
   2026-10-30 (before that it was the club name only) → Send Uploaded Files
   ON → **Send Submission PDFs OFF** → Save. After: `backup_forms.py --form 262352490535154`
   and the diff → hunks inside `integrations` only (a block added, or nothing visible: see the
   next line), nothing else changed. Then
   `python3 tools/integration_status.py --form 262352490535154` → the `other integrations:`
   line names the Drive block, or says none (then the API cannot see it; the Drive check below
   is by eye).
3. **One test submission on the template, arranged to change nothing in Salesforce.** A
   template submission goes through the Salesforce integration like any other and is a real
   batch for a real club ([contact-ids plan](plans/2026-09-30-contact-ids.md), build notes: "a
   delivered one is a real batch for a real club"). Since 2026-10-22 (#108) the processor
   merges a second batch for a club and date that already has a `Success` batch when it ticks a
   girl not yet on that date - she would get a row on the original batch ("Attendance totals and
   partner-reported counts", A mentor's correction) - so the test ticks only girls already on
   that date's batch, with its module: it then adds nobody and is refused as `Failed`
   "Duplicate", with no attendance row and no Contact created (the deployed
   `AttendanceBatchProcessor.cls` under `data/sf_processor_2026-10-22/after/`).
   `resolveClubAccount` runs first, though, and **creates a partner-less Club account when
   question 5 matches no Account name** (the BACKLOG 27 path, seen twice on 2026-10-03) - so
   the club must be one whose Account name is plain, never one of the seven `<club> - <partner>`
   names. Mentors submit late (19 of the 27 duplicates since 10-01 were September dates re-sent
   in October) and a Success batch dated today is the exception, so the query is a window, not a
   day - read-only SOQL: `SELECT Id, Account_Name__c, Attendance_Date__c, Module__c FROM
   Attendance_Batch__c WHERE Processing_Status__c = 'Success' AND Attendance_Date__c =
   LAST_N_DAYS:3 ORDER BY Attendance_Date__c DESC LIMIT 5`; take the newest club + date pair
   whose name has no ` - <partner>` suffix; **never a free date**. Also read, before the
   submission, `SELECT COUNT() FROM Account WHERE RecordType.DeveloperName = 'Club' AND
   ParentId = null` (2 on 2026-10-06: the two pilots). On the template pick that club, that date
   and that batch's module; open the batch in Salesforce to see which girls its attendance rows
   hold (their names stay in Salesforce, never in the conversation, a log or the repo), note its
   `Girls_Present__c` and row count, and tick only girls already on that date's batch - one is
   enough (the roster is required); type your own address as the Partner Coordinator Email, and
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
   - Drive (as Ryan's company account; once the photo mover runs, on the Shared Drive's
     Template folder instead): folder `Attendance photos - Template` → one subfolder named
     exactly `<that club> <that date>` → one image file, **no PDF**.
   - Salesforce (read-only SOQL): exactly one new batch for that club and date,
     `Processing_Status__c = 'Failed'`, `Status_Message__c LIKE 'Duplicate:%'` (it added nobody),
     0 `Attendance__c` rows (`SELECT COUNT() FROM Attendance__c WHERE Attendance_Batch__c =
     '<id>'`), no new Contact (`SELECT COUNT() FROM Contact WHERE CreatedDate = TODAY AND
     AccountId = '<club id>'` unchanged from before the test), the original batch's
     `Girls_Present__c` and row count unchanged (`SELECT Girls_Present__c FROM
     Attendance_Batch__c WHERE Id = '<original id>'`; `SELECT COUNT() FROM Attendance__c WHERE
     Attendance_Batch__c = '<original id>'`), and the partner-less Club account count unchanged
     (the query of step 3; 2 today). If the original's row count or `Girls_Present__c` changed,
     the submission merged after all (its batch then reads `Success`, `merged into <original
     id>`, and the row it added sits on the original): put the original back first, two writes,
     each one record on Ryan's go (one record per call, never from a subagent:
     `.claude/skills/salesforce`) - delete the row the test added on the original, by its id
     (`SELECT Id, CreatedDate FROM Attendance__c WHERE Attendance_Batch__c = '<original id>'
     ORDER BY CreatedDate DESC`: the one created at the test's time, the others at the original
     submission's), then set the original's `Girls_Present__c` back to the value noted in step 3
     - and read both back with the two queries above. Then delete that one batch - Ryan's go,
     one write (the write connector or Ryan in the Salesforce UI) - and read it back as gone.
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
   newer submissions - look in the region's folder on the Shared Drive once the photo mover runs;
   or Jotform e-mails a token error): the Google token has lapsed. In the
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
`UPLOADS = ["19"]` put back in `tools/integration_status.py`. What is already in Drive is
trashed by the photo mover 90 days after it arrives, once its retention is live (DECISIONS
2026-10-30); a Content manager can restore an item from the Shared Drive's trash within 30
days, and after that Google deletes it.

## Photo mover

- **When:** setting it up (once, before #63 points the forms' Drive integrations at its source folders), the template's test upload after #63, a `REFUSED`, `MOVE_FAILED`, `MERGE_FAILED`, `REMOVE_FAILED` or `RESCUE_FAILED` in the log, restoring a removed subfolder, or stopping it.
- **Status:** built offline 2026-10-21 (ticket #89); set up and its trigger installed 2026-10-23 ([plan](plans/2026-10-21-drive-photo-mover.md#result)); every real move then failed (Drive does not move a folder from My Drive into a Shared Drive), fixed in the repo 2026-10-24 (#132: the files move one by one into a folder made there) and pasted live by Ryan 2026-10-25; #144 (the emptied subfolders removed to the trash, and the rescue) built offline 2026-10-30, waiting for Ryan to confirm its rule and paste it, "Updating the live project (#144)" below.
- **Dry run:** `previewMoves` in the standalone project's editor (as Ryan's company account): the log lists what would move, be removed (`would remove N`) and be rescued from the trash (`would rescue N`), by counts and folder names; nothing changes.
- **Apply:** Ryan's go, after the template's integration (#63, "Photos" steps 1-2) and its test upload, before any regional form's: `moveSettledPhotos` by hand once, then `installTrigger` (every 15 minutes). Pushing the code: `drive-sync/README.md`, step 4 (Node 18, clasp 2.4.2; or paste by hand, below).
- **Verify:** the execution's log (`done: N folder(s) moved (N file(s)), N file(s) merged, …; N emptied folder(s) removed (to the trash); 0 failure(s)`); a folder of the subfolder's name is in the region's folder on the Shared Drive with its photos; the emptied subfolder stays in `Attendance photos - <Region>` until a later run removes it (`remove "<name>"`; then it is in My Drive's trash), and that folder itself stays.
- **Rollback:** `removeTrigger` (or delete the trigger in the editor) stops it. A removed subfolder is in My Drive's trash for 30 days: Drive → Trash → the folder → Restore puts it back in `Attendance photos - <Region>`. To undo a move, move the files back into the emptied subfolder there (restored first, or a new folder of its name) by hand. That move out of the Shared Drive needs **Manager** on it: Google's "How file access works in shared drives" (https://support.google.com/a/users/answer/12380484) lets a Contributor or Content manager move files from My Drive into a shared drive and a Content manager move them within it, but for out of it says only "If you have Manager access to a shared drive, you can move files and folders out of shared drive to My Drive". So a Manager does it, or Ryan's role is raised for it.

Jotform's Google Drive integration writes only into Ryan's My Drive ("Photos", above); the
photos belong on the company Shared Drive. `drive-sync/` is a standalone Apps Script project
owned by Ryan's company account - not the sheet's script, whose scopes must not change
(CLAUDE.md rule 11) - that every 15 minutes moves each submission subfolder that has not changed
for 10 minutes from `Attendance photos - <Region>` into that region's folder on the Shared Drive.
Setup, Script Properties and the push: `drive-sync/README.md`.

The order, each live step on Ryan's go (Ryan, 2026-10-22):

1. PR #91 lands: code only, nothing live.
2. Setup (`drive-sync/README.md`, steps 1-6): the Shared Drive's folders, named exactly
   `Africa`, `Asia`, `Latin America`, `Template` (`U.S` only if its form is re-enabled); one My
   Drive source folder per region for Jotform's uploads, `Attendance photos - <Region>`; the
   standalone project (`.clasp.json` from the example) and its push; the Script Properties
   `SOURCE_FOLDER_<REGION>` / `TARGET_FOLDER_<REGION>`; `previewMoves` on the empty folders
   (writes nothing).
3. #63, the template only (Ryan): the template's Google Drive integration pointed at
   `Attendance photos - Template` ("Photos", above, steps 1-2). No regional form yet.
4. A test upload on the template and its read-back ("Photos", steps 3-4), `previewMoves`, one
   `moveSettledPhotos`, then `installTrigger`.
5. #63, the regional forms (Ryan), only after step 4 passed: "Photos", step 5, one form at a
   time, each followed by a check of the next run's log for that region (no `CONFIG refused`,
   no `UNKNOWN`; its first subfolder moved) before the next form.

**Updating the live project** (#132; Ryan, once). Every run since 2026-10-23 ended in
`MOVE_FAILED … cannot use this operation on a shared drive item`: Google's API does not move a
folder from My Drive into a shared drive at any role (`teamDrivesFolderMoveInNotSupported`), so
the mover now makes the folder on the Shared Drive and moves the files into it one by one through
the advanced Drive service. The code is in the repo; the live project is updated by hand (clasp
is logged in as another account):

1. As the company account, open the `GLOW photo mover` project at script.google.com.
2. Replace the editor's `Plan.gs` and `Mover.gs` with the repo's `drive-sync/Plan.gs` and
   `drive-sync/Mover.gs` (the whole file each).
3. Project Settings → "Show appsscript.json manifest file in editor"; replace the editor's
   `appsscript.json` with the repo's `drive-sync/appsscript.json` (it enables the advanced Drive
   service; the scopes are unchanged). Or: Editor → Services `+` → Drive API, version v3,
   identifier `Drive` → Add. Save.
4. Run `previewMoves`; re-authorise if asked. Its log is the plan as before (`would move N …`);
   nothing changes.
5. Run `moveSettledPhotos` once. Executions → its log: `done: N folder(s) moved (N file(s)), N
   file(s) merged, 0 failure(s)`; a `MOVE_FAILED` line names the region and the folder (never a
   file). The photos are in a folder of each subfolder's name in the region's folder.
6. The emptied subfolders stay in `Attendance photos - <Region>` in My Drive. Since #144 (below)
   a later run removes them; until #144 is pasted, delete them by hand. The trigger needs no
   change (it keeps calling `moveSettledPhotos`).

**Updating the live project (#144)** (Ryan, once, on his go; [plan](plans/2026-10-21-drive-photo-mover.md),
Rollout). The mover now moves each emptied, settled subfolder to My Drive's trash, and rescues a
photo Jotform writes into one it trashed. Same paste as above, without the manifest (unchanged:
no new scope, no new service):

1. Ryan confirms the plan's "safe to remove" rule (Design, "What is removed") on ticket #144.
2. Run `removeTrigger` (`removeTrigger: 1 trigger(s) deleted; the mover is stopped`): the
   trigger (installed 2026-10-23) would run the new code within 15 minutes of the paste,
   trashing and rescuing before step 4's check. Until step 6, new photos wait in My Drive.
3. Replace the editor's `Plan.gs` and `Mover.gs` with the repo's (the whole file each). Save.
4. Run `previewMoves`: each region's line ends `would remove N, would rescue N`, and each folder
   it would remove is named on a `would remove "<name>"` line. Check they are emptied
   subfolders (the leftovers in `Attendance photos - <Region>`). `would rescue` is expected 0;
   above 0, stop and look before going on, the trigger still off: each such subfolder is in My
   Drive's trash, named on a `would move "<name>" (in the trash)` or `would merge "<name>" (in
   the trash)` line. Did someone trash it to discard its photos? Then trash the photos
   themselves (the rescue leaves those alone) and run `previewMoves` again. A leftover trashed
   by hand that Jotform wrote into since is what the rescue is for.
5. Run `moveSettledPhotos` once and compare its log with the preview: its region lines are the
   preview's without `would` (unless a folder settled in between), and `done: … N of these
   file(s) out of the trash; N emptied folder(s) removed (to the trash)`, the first 0 when
   `would rescue` was 0, the second the `would remove` total (less one per `not trashed
   "<name>"` line). Those folders are in My Drive's trash; apart from the moves its log names,
   the photos and the Shared Drive are as before.
6. Run `installTrigger` (`installTrigger: moveSettledPhotos every 15 minutes`). The counts go in
   the plan's Result. From then on the mover removes the emptied subfolders (step 6 of the
   paste above).

What the log says, per region: `move N, merge N (F file(s) in, K kept), waiting N, refused N,
remove N, rescue N`, then the folders by name (club and date; never a file's name or contents).

- **move**: a folder of that name was made in the region's folder and the subfolder's files
  moved into it (Drive cannot move the folder itself, #132); the emptied subfolder stays in My
  Drive until a later run removes it.
- **merge**: that name was already there once (a resubmission): its files went in one by one,
  beside what is there; **kept** files (same name and size already there) stay in My Drive. A
  subfolder of kept files only (`0 file(s) in`) changes nothing, never holds up a same-name copy
  with new photos, is never removed while it holds them, and is logged again every run until
  Ryan clears it after a look: trash its **files**, then the folder (a file trashed by itself is
  left alone by the **rescue**; the mover never removes a subfolder still holding a file, even
  one in the trash).
- **remove** (#144): the subfolder held no file and no subfolder and had not changed for 10
  minutes; the real run re-read and re-listed it just before, then moved it to My Drive's trash
  (restore: Rollback, above). `not trashed "<name>": …` after the `done:` line: it changed
  since the run read it (something arrived, it was moved, or it is already in the trash), so it
  stays; no error, the next run looks again. Never a source folder itself, never anything on the
  Shared Drive, never a file.
- **rescue** (#144) and **(in the trash)** after a folder's name: a photo was found in a
  subfolder in My Drive's trash (Jotform can re-send an edited submission's photos into the
  folder of that name after the mover trashed it); it moves like any other, out of the trash.
  The rescue cannot tell a folder the mover trashed from one a person trashed: **to discard a
  photo in My Drive, trash the photo itself**, not only its subfolder; a photo trashed by itself
  is left alone.
- **waiting**: a file changed less than 10 minutes ago, or another subfolder of the same name
  moved or merged files this run; the next run takes it (a backlog of same-name copies clears
  one per run).
- **TIME_BUDGET**: the run stopped reading after about 2 minutes (half its budget), or stopped
  moving at 4.5; what it did not read is not touched, and the next run carries on (a move cut
  short, its folder made and some files moved, is finished by the next run as a merge).
- **REFUSED**: two or more folders of that name on the Shared Drive already. Move or merge it by
  hand (pick the right folder), or rename one of the two there.
- **UNKNOWN**: a folder that is no region's; left alone.
- **CONFIG refused**: a Script Property is missing or wrong (half a pair, an id used twice, a
  source folder not named `Attendance photos - <Region>`, a Shared Drive folder not named exactly
  `Africa`, `Asia`, `Latin America`, `U.S` or `Template`); nothing read, nothing moved. Fix the
  property in Project Settings → Script Properties, or the folder's name.
- **MOVE_FAILED** / **MERGE_FAILED**: Drive refused a file's move, or did not confirm the new
  folder (`folder not confirmed, its files stay in My Drive`: the next run merges into it if it
  exists, or moves again); the line names the region and the folder, the rest of the run goes
  on, the run ends in an error and Google sends the owner its failure summary. A move whose
  folder exists but whose files did not all move is finished by the next run as a merge.
  A permission error means Ryan's role on the Shared Drive is below Content manager, or the
  advanced Drive service is not enabled (above). Before 2026-10-24 every move failed with
  `cannot use this operation on a shared drive item`: the folder move Drive does not support
  (#132; [plan](plans/2026-10-21-drive-photo-mover.md), Risks).
- **REMOVE_FAILED** (#144): Drive refused the trash of an emptied subfolder (or the trash helper
  refused it: never a configured folder or the Shared Drive's root); the folder stays, the line
  names the region and the folder, the run ends in an error. Nothing to undo.
- **RESCUE_FAILED** (#144): Drive accepted a rescued photo's move but the re-read finds it still
  in the trash, or not in the folder it was sent to. Look for it by the folder's name: in the
  region's folder on the Shared Drive, then in the Shared Drive's trash and in My Drive's trash
  (inside the trashed subfolder of that name), and restore or move it there by hand. The run ends
  in an error. The rescue is unproven live (the plan's Risks): the first one is its test.

Nothing is shared beyond the Shared Drive's members (the named list: the CEO and Ryan, never
"anyone with the link"): the mover never shares, links, copies or e-mails a file, never trashes
one, and never deletes anything for good; its one trash is an emptied subfolder (#144).

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
  unchanged. Its Salesforce integration needs the session notes mapped
  (q446) before or with the re-enabling ("Session notes in Salesforce").

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

## Club names that look alike

- **When:** before GLOW renames clubs into a country format, to see which names already collide or nearly do; as the input for the duplicate-club checks (ticket #84).
- **Status:** built 2026-10 (ticket #94; `plan-renames` ticket #95, waiting on GLOW's format, task #99); it runs without `--countries` meanwhile, and the `country` column fills once the Account field is chosen. Which Salesforce Account field holds a partner's country (the ticket outline's step 4) is not settled: the candidates are `Country__c` (a picklist), `BillingCountry` and `ShippingCountry`, and their non-blank counts over the partner accounts are not taken yet.
- **Dry run:** the whole tool is one: it reads exports and writes only its own CSV.
- **Apply:** none; a rename it points at goes through "Renaming a club".
- **Verify:** the counts line, against the CSV's rows.
- **Rollback:** none needed (nothing is written outside `data/`).

`tools/club_names.py similar` compares every club of the Roster with every
other and prints the lookalikes in groups. A club is one partner + club name
(compared with case and spacing ignored, `glow.text.key`), whatever its
status, so a retired club still counts. The tool reads files only: no
Jotform, Sheets or Salesforce call, and it prints club and partner names,
regions and counts, never a girl's name. Its exports and its CSV live in
`data/`, which stays uncommitted (the Roster export holds the girls' names).

```bash
mkdir -p data/club_names                     # the sync's --summary-json does not make it
python3 tools/sheets_client.py export Roster data/roster_<date>.csv
python3 tools/sheets_client.py export Partners data/partners_<date>.csv
# optional, for the sf_name column: each region's sync dry run with its summary (Jotform GET only)
python3 sync_attendance_form.py data/roster_<date>.csv --roster \
        --partners data/partners_<date>.csv \
        --region Africa --form 262382821971058 \
        --summary-json data/club_names/plan_africa_<date>.json            # and Asia, Latin America, U.S
python3 tools/club_names.py similar --roster data/roster_<date>.csv \
        --partners data/partners_<date>.csv \
        [--countries data/club_names/partner_countries.csv] \
        [--sf-names data/club_names/plan_africa_<date>.json --sf-names ...] \
        --csv data/club_names/similar_<date>.csv
```

Two names match as

- `same`: equal apart from capitals and spacing ("Sunrise Club", "SUNRISE  CLUB");
- `folded`: equal once accents, punctuation and spacing are folded away
  ("Niñas Unidas", "Ninas-Unidas"; "G.L.O.W. Club", "Glow Club");
- `close`: the folded names at least `--threshold` alike (difflib's ratio,
  default 0.85: "Sunrise Club", "Sunrize Club") and carrying the same numbers
  in the same order, so "Harbor Club 1" and "Harbor Club 2" never match.

A group is every club joined by a chain of matches, so two clubs in one group
need not match each other directly. The first line counts them:
`groups: N (same A, folded B, close C); clubs in them: M`. A mixed group
counts under the **weakest link it needs** to be one group: `same` when its
`same` pairs alone connect it, else `folded` when its `same` and `folded`
pairs do, else `close`. So two `same` pairs joined only by a `close` pair are
one `close` group, although every club's own `match` is `same`. Each group follows, one line per club with its
partner, region, form and active girls. The seven names two partners share
("Club names two partners share") come out with match `same`, and with
`--sf-names` each of those clubs' `sf_name` is its `<club> - <partner>`.

The CSV (`--csv`, its folder made when missing; only the header when there is no group), one row per club in a group:

| Column | What |
|---|---|
| `group` | the group's number in this run (groups ordered by folded name) |
| `match` | the strongest kind joining this club to another of its group: `same`, `folded` or `close` |
| `club`, `partner` | as the Roster spells them (whitespace collapsed), from the club's first active row, else its first row |
| `region` | the region cell of that row, in the forms' spelling when it is one of theirs, else as written |
| `form` | `retired (jotform=no)` (its partner is marked `no` in the Partners tab), else `none (no active girl)`, else `none (no region)` (a blank region or one no form has), else the form's title, such as `Africa Attendance Form` - checked in that order |
| `country` | the partner's country from `--countries` (a `partner,country` CSV); blank without it |
| `sf_name` | what the club sends to question 5 (its Salesforce Account name), from the `sf_names` of the `--sf-names` summaries; blank without them, or for a club none of them lists |
| `status` | `active` (at least one active girl) or `inactive` |
| `active_girls` | the club's active rows |
| `same_partner` | `yes` when every club of the group has one partner (one partner's own lookalikes), else `no` |

`tools/club_names.py plan-renames` (ticket #95) plans the rename into the
format GLOW picks, and renames nothing: from the same exports, a
`partner,country` CSV (`--countries`), every region's `--summary-json`
(`--sf-names`: each club's question 5 now) and `--format` (placeholders
`{country}`, `{club}`, `{partner}`, `{region}`, e.g. `"{country} - {club}"`),
each active club of a partner not marked `jotform=no` gets `new_club`, the
format filled in (spacing collapsed), and `new_sf_name`, what its question 5
(its Salesforce Account name) becomes. `--scope all` takes every such club,
`--scope similar --similar-csv data/club_names/similar_<date>.csv` only those
`similar --csv` listed; inactive and retired clubs keep their names. A club
whose question 5 is `<club> - <partner>` keeps that suffix after the new name
with `--keep-long yes` and drops it with `no`; a plain one never gains it. A
club already in the format is `unchanged`, so a second run over the renamed
Roster plans nothing. Any refusal stops the plan, lists every refused club
with its reason and writes no `--out`: no country for its partner (or no
region when the format has `{region}`); `|`, `{` or `}` in the new name; a
`new_sf_name` equal (by key) to another club's, planned or keeping its name
(one Salesforce Account); a `new_club` another partner's club has after the
renames, in any status, unless its `new_sf_name` is the long form ("Club names
two partners share"); a `new_sf_name` over 255 characters; a cycle of planned
clubs each taking another's current question 5 (two clubs swapping names, or a
ring of three or more: no rename order works), every club of the cycle named.
The last line counts `to rename N, unchanged N, refused N`; the CSV has
`partner, club, region, old_sf_name, new_club, new_sf_name, action` (`rename`
or `unchanged`) and `after`. `after` is blank unless the club's `new_sf_name`
equals (by key) another planned club's current question 5: then it holds that
`old_sf_name` as the other club's row has it, and the run prints an
`order: rename <that club> ... first, then <this club> ...` line. In the
rollout, **rename the Account named in `after` first** (and that club's
question 5 with it), then this club's: renamed the other way round, two clubs
would send one Account name for a while. The rename itself, Accounts first, is
task #99's plan.

```bash
python3 tools/club_names.py plan-renames --roster data/roster_<date>.csv \
        --partners data/partners_<date>.csv \
        --countries data/club_names/partner_countries.csv \
        --sf-names data/club_names/plan_africa_<date>.json --sf-names ... \
        --format "{country} - {club}" --scope all --keep-long yes \
        --out data/club_names/renames_<date>.csv
```

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
partner instead. A partner marked `no` also goes, by hand, into the partner-name
filter of the Salesforce report `Clubs_Not_Submitting_Last_Week` ("Submission
timing in Salesforce", The timing reports), or its clubs show there every week.

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
  (capitals, spacing, accents and punctuation are ignored, when that leaves
  one girl of the club; a middle name left out or a letter changed is not
  matched): copy each name from the club's Roster rows.

| Issue | What to do |
|---|---|
| **New club held as a possible duplicate** | "Enroll a NEW club" was sent for what may be a club already on file: nothing was imported, and the mentor was told it is being checked. Detail says why — names already active in one club, a club name close to one of the partner's, a typed organization close to a partner on file, or a re-enrollment whose list is mostly not the club's — and names the club(s) on file. Compare the response row (the tag) with those clubs' Roster rows. **Same club:** enter only its new girls on "Add or remove girls" for the club on file (REMOVE anyone who has left), then `resolved <date> by <name>: same club as <club>`. **A new club after all, or the new list is right:** `release <date> by <name>: <why>` (`release` must be the first word), then run **Process any missed form responses**: it asks about released rows separately and imports each as sent. **If the reason says "the organization was typed as …, close to … on file"**, fix that first, or the club is filed under a second spelling of the partner (no region, a second form section — the `ion bu` case): if it is that partner, set the response row's `Partner organization` cell to the partner exactly as the Partners tab spells it (the row stays matched to its item by its Timestamp, and the release preview shows the corrected partner); if it really is another organization, add it to the Partners tab with its region. Until then the release run refuses it (`ERROR: release refused: …`, offered again by the next run). **Sent again under another name and already imported** (a later "Enroll a NEW club" row of the partner's, its club now on file with most of these girls — 2026-10-16: Kawempe Youth Center's Burning Flames): compare the two lists first — a girl on the held list but not on the one sent again is entered on "Add or remove girls" for the imported club, or the partner is asked, since the held response never runs — then `resolved <date> by <name>: sent again as <club> (Roster Form Responses!N)`; never release it as well — a release imports the girls a second time, as a second club. **Sent by mistake:** `resolved …: not imported`. Never ask the partner to send it again, and never edit the `(sent …)` or the `[#…]` tag in detail: the menu matches both to the response row. |
| **Club name already used by another partner — ask for a different name** | "Enroll a NEW club" was sent with a club name that another partner's club already has — any status, any region; capitals and spacing are ignored, a plural or a typo is a different name — or that reads as a club on file followed by its partner (`<club> - <partner>`). Nothing was imported, and the mentor got the same "it is being checked" note as any held club. A new club may not take a name in use: the attendance forms and Salesforce tell clubs apart by name, and the sync would refuse to add it ([plans/2026-09-30-same-name-clubs.md](plans/2026-09-30-same-name-clubs.md)). Detail names the club(s) that have the name. **First rule out a mix-up:** compare the response row (the tag) with that club's Roster rows — it may be that club, sent under the wrong partner — and, when detail gives more reasons (names on file, a close club name), with the other clubs it names. **Same club:** enter only its new girls on "Add or remove girls" for the club on file, then `resolved <date> by <name>: same club as <club> (<partner>)`. **That club, but the Roster has it under the wrong partner (or it has moved to this one):** move the club on file first ("Moving a club to another partner" — the tool refuses a club whose name two partners already share, and a partner in another region: Ryan's call), then write `release <date> by <name>: club moved to <partner>` with the `Club name` cell unchanged and run **Process any missed form responses**: the response now runs as that existing club (its new girls are added; no second club, no Salesforce line). **A new club:** ask the partner for a different name (the school or the place added is enough: `Stars (Testville Sec Sch)`). Then either **(a) release it under the new name:** set the response row's `Club name` cell to the new name (the row stays matched to its item by its Timestamp), write `release <date> by <name>: renamed to <new name>` (`release` must be the first word), and run **Process any missed form responses** — its preview shows the new name, and YES imports the club as sent otherwise; or **(b) have it sent again:** the partner (or you, from the response row's answers) sends "Enroll a NEW club" under the new name, and you close this item `resolved <date> by <name>: sent again as <new name>` — the held response is then never run. A release with the name unchanged, or changed to another name in use, is refused (`ERROR: release refused: …`, offered again by the next run) and adds a **Form response could not be processed** item: fix the cell, run it again, then close that item. **If detail also says "the organization was typed as …, close to … on file"**, fix that first, as in the row above. **If detail says "this club is on file with no active girl":** the partner sent "Enroll a NEW club" for a club of its own that has no active girl left, and another partner's club has its name. A club retired as a duplicate (the two of 2026-09-30) has no roster on the attendance forms any more, so bringing it back would add a new club under a name in use, which the sync refuses. Work it as above: the girls usually belong to the partner's up-to-date club (**Same club**); a club that really starts again needs a different name (**A new club**). The one false hold: a club that only lost every girl still has its roster on its attendance form, and keeps its name and its Salesforce account — none on 2026-09-30 (the only clubs with no active girl are the two retired ones). That one is Ryan's: he sets one of its girls back to `active` in the Roster (one who is on the list sent, if there is one; `removed_date` emptied — the only Roster cells typed by hand for an item), then releases with the `Club name` cell unchanged: the response runs as that existing club. Never edit the `(sent …)` or the `[#…]` tag in detail. The clubs that already share a name and have active girls are not affected: their own enrollments and roster changes run as always. |
| **Roster change sent as a problem report** | Read `Feedback!N` (the tag). Check the Roster and Audit `rosterChangeForm`: the partner may have sent it since. Enter it as above, or ask the partner to. Not a roster change after all: `resolved …: not a roster change`. Since #110 the sender is e-mailed the Club Roster Form link when the report gave a reply address and its words ask for the change (not when she chose the Club Roster Form and only describes it broken; FormLog `sender pointed to the Club Roster Form`; the Audit row `sendRosterFormPointer_` when that e-mail failed): the item is still yours — enter the change or confirm the partner sent it, then resolve. A roster-change report whose staff e-mail lacks the "Staff note" line was missed by the keyword check: add a row by hand with this issue and `[#Feedback!N]` as the last text of detail (reports from before 2026-09-28 were added once by a one-off script, since retired: [Retired tools](ARCHITECTURE.md#retired-tools)). |
| **Form not working report** | A problem report says the form is not working — it does not load or submit, a blank page, an empty dropdown, an error message, in English or Spanish (the rule above `FP_FAIL_EN` in `appsscript/FormHandlers.gs`). Read `Feedback!N` (the tag) and the staff e-mail (its "Staff note" line names this row); detail names the form she chose, never her words. Try that form as she did: an attendance form (Jotform) — is it enabled, is her club in its picker, does a test submission on a test club go through (`python3 tools/auto_sync.py` shows a disabled form and a region out of sync); the Club Roster Form or the problem form (Google Forms) — open its link, check its dropdowns. Fix or escalate (Jotform support for an outage; "Automatic sync" for a roster or picker problem), answer the sender when the report gave a reply address (the staff e-mail's Reply-To), then `resolved <date> by <name>: <what was wrong>`. The form was fine (a one-off, her phone or network, an "error" that was not the form's): `resolved …: not a form problem`. A report that is also a roster change is queued as **Roster change sent as a problem report** instead — one item per report — and the sender of this item is never e-mailed automatically. A report whose staff e-mail lacks the "Staff note" line was missed by the rule: add a row by hand with this issue and `[#Feedback!N]` as the last text of detail. |
| **Removal did not match anyone** | Detail shows the typed name and up to 3 "Closest names on file" — other girls, so never send them to the mentor. Since #112 the matcher settles the clear cases itself, and they raise no item: a typed name that is one of the club's girls once capitals, accents and punctuation are ignored (the same letters and digits, in that order: `Lucia Zorblewick` for `Lucía Zörblewick`, `Mary Jo` for `Mary-Jo`, `JR` for `J.R.`) is her removal when she is the only girl of the club spelled so and is active (Audit `rosterChangeForm`: `1 removed, 1 of them matched ignoring accents and punctuation`; the mentor's e-mail shows the name as typed), and "already removed" (nothing changes, `1 already removed` in Audit) when every girl of the club spelled so is inactive. What still reaches you: a spelling two or more of the club's girls share once folded with an active one among them (`Zoe` and `Zoë`: sisters, or one girl twice), a second line of one response that reaches a girl another line of it removes (she is removed once, by the line spelled as enrolled if there is one; the other line is this item), a REMOVE of a girl the same response also ADDs under her enrolled spelling (she stays), a middle name left out, a letter changed or dropped (`Pea` for `Peña`), a name that is only punctuation, a name nobody has — and every item raised before #112 was deployed. The "Closest names" are girls who were **active when the response ran** (one of them may since have been removed by another line of it), so first look for her among the club's `inactive` Roster rows: a close spelling removed on or after the day the response was sent (by another line of it, or by a repeat submission) means she is already off — `resolved <date> by <name>: already removed` (2026-10-21: 31 of the 62 open, before #112) — but only when no **active** girl of the club is also close to the typed name: two lines of one response are more often two girls (sisters, a shared first name) than one typed twice, so with an active close match go on to the next step. Otherwise REMOVE only an active match that is clearly her (a middle name left out, one letter off, and no other girl of the club close to it). An item whose typed name differs from one active girl only by capitals, accents or punctuation does not mean a second girl exists: it is raised when another line of the same response removed or ADDed her (read the response row — the tag — first: removed by another line is `already removed`; ADDed is nothing to do), when two or more girls of the club fold to it (never guess which), and for every item from before #112 — do not look for a second girl before you have ruled those out. Otherwise ask the mentor for the enrolled spelling (her confirmation said "our team will check"). One response's unmatched names are separate items with the same response row in detail: work them together. |
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
- **Status:** built and in `main` since 2026-10-07; **live in `apply` since 2026-10-22 12:52 UTC** (Ryan's go). History ([plan](plans/2026-10-06-sf-new-club-accounts.md), amendment 2026-10-21 and Result; DECISIONS 2026-10-21):
  - 2026-10-21: the External Client App "GLOW Sync" exists in Salesforce (client credentials, Run As **Ryan's own user**; Setup steps 1-2 below).
  - 2026-10-22: Ryan set the secrets `SF_CLIENT_ID` and `SF_CLIENT_SECRET` (12:17 UTC). The dispatch token's step 4.4 is done (Contents: No access) and 4.5 checked (run 39778511710, `workflow_dispatch`, success). `SF_SYNC=plan` from 12:31 UTC.
  - The first plan run, 39779117991, was refused: `HTTP 400 invalid_app_access` (the app's policies lacked the System Administrator profile, Setup step 2). Ryan added it.
  - Run 39780929667: describe ok; 455 Accounts read, 372 Club (equal to the count from Ryan's `glow` login on 2026-10-21); check 317 ok, 5 need a person. Those five were fixed by hand on Ryan's go (4 partner-less club accounts parented, 1 club account created).
  - Run 39784745392: 456 Accounts, 373 Club; check 322 ok, 0 need a person. `SF_SYNC=apply` since 12:52 UTC.
  - **Still to do:** check the first automatic creates by hand (ATTENTION table, `created … check it by hand (first creates)`).
- **Dry run:** `SF_SYNC=plan`: every account it would create is an ATTENTION item with the body.
- **Apply:** `SF_SYNC=apply` (with `AUTO_SYNC_APPLY=1`), Ryan's go.
- **Verify:** the run's `SF:` log lines; the local cross-check, below.
- **Rollback:** `SF_SYNC=off`; "Rollback of creates", below.

`tools/sf_new_clubs.py`, called by `tools/auto_sync.py`.

**What each run does:**
- Log in as **Ryan's own Salesforce user**, through the External Client App **GLOW Sync** (OAuth
  client credentials flow, scope `api`, Run As = Ryan). There is no GLOW Sync user and no GLOW
  Club Sync permission set (DECISIONS 2026-10-21): the access is Ryan's administrator rights.
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
session). All steps are done (2026-10-22); the consumer key and secret are never written in a file, a message
or a command line.
1. **No integration user and no permission set** (decision 2026-10-21). The run is Ryan's user,
   so there is nothing to create for access.
2. **External Client App "GLOW Sync"**: created 2026-10-21 through the Metadata API (check-only
   first, then deploy `0AfRP000002hjdR0AQ` for the app and its OAuth settings, and
   `0AfRP000002hjiH0AQ` for the policies), on Ryan's go:
   - Setup → External Client App Manager → **GLOW Sync**;
   - OAuth settings: scope **Api** only; the client credentials flow on;
   - policies: client credentials Run As = **Ryan's user**; Permitted Users "Admin approved users
     are pre-authorized"; IP relaxation **Bypass** (GitHub's addresses change); session timeout 15
     minutes; refresh token **Zero** (none);
   - the consumer key and secret: Settings → OAuth Settings → **Consumer Key and Secret**; copy
     them from that page only, straight into the GitHub secrets of step 5.
   - **the policies must include the System Administrator profile** (Setup → External Client App
     Manager → GLOW Sync → Policies → Edit → select profiles). With "Admin approved users are
     pre-authorized" the Run As user has to be given the app; without the profile every login is
     refused `HTTP 400 invalid_app_access - user is not admin approved to access this app` (run
     39779117991, 2026-10-22). Ryan added it 2026-10-22; the deploy of 2026-10-21 did not carry it.
   - The Metadata reference says the Run As user "must have the API Only permission"; the deploy
     accepted Ryan's System Administrator user, and with the profile above the 2026-10-22 login
     was issued a token. If a login is refused, the log says `SF: not ready … Salesforce refused
     the GLOW Sync login (HTTP …)`: set `SF_SYNC=off` and read the app's policies before trying
     again.
3. *(Was: the app's Run As GLOW Sync and its permission set; replaced by step 2.)*
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
   - Done 2026-10-07: 4.1-4.3 (`HTTP 204`; the runs since start by `workflow_dispatch`). Done
     2026-10-22: 4.4 (Contents: No access) and 4.5 (run 39778511710, `workflow_dispatch`, success).
   - Before step 2 the sheet still uses `repository_dispatch`; after it, a token without Actions
     gets `HTTP 403` in the Audit tab and only the daily run syncs.
   - The workflow runs only on `main` (a token with Actions: write can pick the branch of a run);
     delete stale branches on GitHub, whose older workflow file has no such guard.
5. **GitHub**:
   - secrets `SF_CLIENT_ID` and `SF_CLIENT_SECRET` (the app's consumer key and secret, from
     Setup → External Client App Manager → GLOW Sync), set by Ryan on the repository's Settings →
     Secrets and variables → Actions page, never on a command line or in a conversation. They
     now hold **administrator access**: whoever can read them acts as Ryan ("The risks of running
     as Ryan", below); set 2026-10-22 12:17 UTC;
   - repository variable `SF_SYNC` = `plan` (Ryan's go; CLAUDE.md rule 1); set 2026-10-22 12:31
     UTC, `apply` since 12:52 UTC.
6. **First run**: Actions → auto-sync → Run workflow (apply unticked). The log must show:
   - `SF: plan, as GLOW Sync` (the code prints this literally: "GLOW Sync" now names the app,
     and the user behind it is Ryan; the wording stays until a code ticket changes it);
   - `SF: describe ok - Account, Name, ParentId, Description, RecordTypeId createable; Club record
     type available` (otherwise `SF: GLOW Sync cannot create Club accounts: …` names what Ryan's
     user lacks, and an `apply` run only shows bodies; its hint still names the "GLOW Club Sync
     permission set", which does not exist: read it as Ryan's profile);
   - `SF: 448 Accounts read, 366 Club` (or today's counts);
   - `SF: check - 364 ok, 0 need a person`.

   What the runs of 2026-10-22 showed: the first (39779117991) was refused (`invalid_app_access`,
   step 2). The next (39780929667): describe ok; `SF: 455 Accounts read, 372 Club`; `SF: check -
   317 ok, 5 need a person` (4 partner-less club accounts and 1 club without an account, fixed by
   hand on Ryan's go). The one after (39784745392): `SF: 456 Accounts read, 373 Club`; `SF: check -
   322 ok, 0 need a person`.

   The old design's `UserRecordAccess` cross-check for GLOW Sync is not needed: Ryan's user sees
   everything. Instead compare the run's Account counts with a count from Ryan's `glow` login
   (VPN off).

**ATTENTION items (`SF: …`) and what to do:**

| Item | Meaning | Fix |
|---|---|---|
| `not ready …` | Login refused, the user frozen, or the Account read not whole (a page missing, a mapped partner unseen; its hint may still name a "GLOW Club Sync" permission set: read it as Ryan's profile) | Read the detail. **`HTTP 400 invalid_app_access`**: the app's policies lack the System Administrator profile (Setup step 2). **Frozen**: it is Ryan's user, so also the Jotform connection: "The risks of running as Ryan", below. New clubs this run went on the forms without an account: create them by hand. |
| `would create …` (plan) | A new club needs its account | Create it by hand with the body shown, today |
| `… - not created`: club code on another account | The club was renamed in the sheet, not in Salesforce | Rename that account to the question-5 name first ("Renaming a club"); no new account |
| `… - not created`: the name is already an account | The processor made it first, or another record has the name | A partner-less Club: set its `ParentId` as the item says (write connector, Ryan's go). Anything else: look before acting. |
| `… - not created`: nearly the same name, or a character not yet seen in question 5 | A spelling a person must judge | Check, then create by hand with the body shown |
| `… - not created`: partner not in `glow/sf_partners.csv` | A new partner | Add one line, `partner,sf_account_id,sf_account_name`, for its Household account (create that first if needed); commit; the next run proceeds. Check its account name against the Monthly Reports' "test" filter ("The keep list") |
| `more than 5 … none created` | A wave of new clubs | Create by hand from the bodies listed, or let the next runs take them |
| `created … check it by hand (first creates)` | Shown until the first creates are checked | Read the account: name, Club, parent, Description (`created by the automatic sync <date>`); its owner and creator are Ryan |
| `check by hand: the create's outcome is not as planned` | Salesforce did not answer clearly | Read the name in Salesforce **ten minutes later**. One account, right: nothing to do. None: create by hand. Two: delete the newer (no Contacts). |
| `N club account(s) need a person` | The check found a club whose account is missing, partner-less, under another partner, twice, not a Club, or carrying another code; or a partner-less stray | Each line names the fix |
| `partner map out of date` | A partner account was renamed in Salesforce | Update its line in `glow/sf_partners.csv`; check the new name against the Monthly Reports' "test" filter ("The keep list") |

**SF Pending**: when it creates an account, the run marks that club's SF Pending row
`done (auto <date>)`: one cell, found by its header, read again before the write and after.

**The risks of running as Ryan** (accepted by Ryan 2026-10-21, DECISIONS):
- **A freeze of Ryan's user.** Salesforce freezes a user whose connection comes from anonymising
  or high-risk addresses, and cannot be told to allow GitHub's data-centre addresses (plan, "The
  freeze rule"). A frozen user is locked out and **all his tokens are revoked, the Jotform
  connection's included, as on 2026-09-30 12:16 UTC**: no submission then reaches Salesforce
  until it is repaired. What to do, in this order:
  1. Set `SF_SYNC=off` (Ryan's go) so no further run logs in, and cancel a run under way.
  2. Another Salesforce administrator unfreezes Ryan's user (Salesforce e-mails the admins);
     Ryan cannot do it himself.
  3. Re-authorise Jotform on the five forms and run `tools/integration_status.py`, then a live
     test submission (as after 2026-09-30: "Back-fill of attendance into Salesforce").
  4. Switch `SF_SYNC` back on only on Ryan's word; repeated tries mean repeated containment. The
     forms and the sheet keep syncing meanwhile.
- **Admin rights in a GitHub secret.** `SF_CLIENT_ID` and `SF_CLIENT_SECRET` log in as Ryan with
  his administrator rights (scope `api`: records and metadata over the API). Hence the workflow
  runs only on `main`, the dispatch token loses Contents (Setup step 4.4), only Ryan edits the
  secrets and the workflow, and the app has no refresh token and a 15-minute session.
- **The creator no longer shows who made an account** ("Rollback of creates", below).

**Rotating the secret** (also if it may have been seen): in the External Client App GLOW Sync,
Settings → OAuth Settings → Consumer Key and Secret, regenerate the secret; update the GitHub
secret `SF_CLIENT_SECRET` (and `SF_CLIENT_ID` if the key changed) on the web page; then start a
manual run (apply unticked): the log must show `SF: plan` or `SF: apply` and the counts. Until
the secret is updated every run logs `SF: not ready`.

**Off-boarding / stop**, lightest first:
- `SF_SYNC=off` stops future runs (no login); cancel a run already started in Actions.
- Disable the app's policies (External Client App Manager → GLOW Sync → Policies: the client
  credentials flow off, or the Run As user cleared): the next login is refused, the app and its
  key stay.
- Delete the app (External Client App Manager, or a destructive change of the `GLOW_Sync`
  components): its key and secret stop working at once. Then delete the two GitHub secrets.
- Rotate the secret (above) if it may have been exposed.
- There is no user to deactivate, and Ryan's must not be.

**Rollback of creates**:
- The sync's accounts are **not** listed by `CreatedById`: Ryan's user creates them, as it does
  his hand-made ones. Separate them by the Description the sync always writes,
  `GLOW club code <code>; created by the automatic sync <date>`: `SELECT Id, Name, CreatedDate
  FROM Account WHERE Description LIKE '%created by the automatic sync%'`. The run's log and the
  SF Pending row (`done (auto <date>)`) name the same clubs.
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

## Duplicate and obsolete records in Salesforce

- **When:** the monthly check (with "Duplicate girls in Salesforce"); a flag to set or clear; GLOW's own definitions arrive (DECISIONS 2026-10-21).
- **Status:** deployed 2026-10-22 12:33 UTC on Ryan's go (ticket #84; deploy `0AfRP000002htOH0AY`, 9/9, check-only `0AfRP000002hlVZ0AY`): the three Account rules active and report only, the `Datacloud.FindDuplicates` diagnostic run the same day, 12:58 UTC, on his go ([plan](plans/2026-10-21-sf-duplicate-obsolete-flags.md), [Result](plans/2026-10-21-sf-duplicate-obsolete-flags.md#result)); step 8, the next day's batch check, is pending, due on or after 2026-10-23; the flagging batch `RecordFlagBatch` (ticket #85) is deployed (`0AfRP000002i7np0AA`, 2026-10-26 07:03 UTC). The flagging batch ran on 2026-10-26 on Ryan's go: Account in flag mode, job `707RP00002cLzc0YAC`, 07:45 UTC, duplicate 0, obsolete 26; Contact in flag mode, job `707RP00002cM4WlYAK`, 07:48 UTC, duplicate 20, obsolete 0 ("The flagging batch", below; the plan's [Result](plans/2026-10-23-sf-record-flag-batch.md#result)).
- **Dry run:** the check-only deploy (`sf project deploy start --dry-run`), step 3 of the plan's Rollout.
- **Apply:** the same with its dry-run flag taken off, Ryan's go (VPN off); then the proof, also on his go: the no-DML `Datacloud.FindDuplicates` diagnostic (`sf apex run -f diag.apex`, the plan's step 6), which runs the active rules over three unsaved copies of existing accounts, inserts nothing and prints only `DIAG|` lines with each rule's name and its match count.
- **Verify:** SOQL on `DuplicateRule` and `MatchingRule` (the three Account rules active, the Contact rule as before), the four fields in `describe`, `glow.salesforce.duplicate_account_groups` against the rules' `DuplicateRecordSet`s (a cross-type pair, a Household account and a Club of one name and parent, is a set without a group: looked at by hand), and the next day no `Attendance_Batch__c` `Failed` with `DUPLICATES_DETECTED` among its `Status_Message__c` codes (`glow.salesforce.error_codes`).
- **Rollback:** deactivate the two Account Duplicate Rules, each rule by the same step (`isActive` false, by a deploy or in Setup, Duplicate Rules), Ryan's go; the four fields stay ([plan](plans/2026-10-21-sf-duplicate-obsolete-flags.md#rollback)). The flags the batch (#85) set: a `clear` run of the same batch, `new RecordFlagBatch('Account', 'clear')` then `new RecordFlagBatch('Contact', 'clear')`, through `tools/sf_record_flags.py --mode clear` and `sf apex run`, Ryan's go, the hand-set flags counted first since `clear` takes them off too (the plan's Rollback, "The flagging batch" below).

GLOW's annotated SOW (p.9) asks for "Duplicate Record" and "Obsolete Record" checkbox fields on
Account and Contact, and for one Matching Rule and one Duplicate Rule on Account. The definitions
below are Ryan's working answers of 2026-10-21 ("move forward with this"), provisional until GLOW
defines the terms (DECISIONS 2026-10-21). The fields and the rules are live since 2026-10-22
(DECISIONS 2026-10-22: the proof and the cross-type pairs). The legacy records themselves are
never merged or cleaned by this (SOW p.10); the batch that sets the flags by these criteria is
ticket #85.

### What is a duplicate, what is obsolete

- **A duplicate Account:** two Accounts are duplicates when they have the same name ignoring
  capitals and spacing (any run of whitespace is one space), the same parent and the same record
  type. An accent counts: "Café Club" and "Cafe Club" are different names. The deliberate
  `<club> - <partner>` names ("Club names two partners share") never match a plain name, and two
  partners' clubs of one name never match each other: another parent keeps them apart. Matches
  on 2026-10-21: 0 (455 Accounts: 372 clubs, 83 partners).
- **A duplicate Contact:** the existing Contact rule "First & Last & Account" (same first name,
  last name and account) stays unchanged, Report only since 2026-10-01 (BACKLOG 54). A Contact's
  "Duplicate Record" flag is set by the flagging batch (#85) when the Contact sits in one of that
  rule's duplicate record sets (`DuplicateRecordSet`). `tools/sf_dupes.py` still merges one girl's
  duplicate contacts by its own key ("Duplicate girls in Salesforce") and never merges a record
  for being flagged.
- **An obsolete Account:** a partner whose `Partner_Status__c` is Archived is obsolete; so is a
  Club account whose club is deactivated in the Roster ("Deactivating a club"), and a Club account
  with no attendance batch for 6 months that was created more than 6 months ago (so the clubs
  created in September 2026 are not flagged before March 2027). The clubs of a partner marked
  `no` in the Partners tab's `jotform` column (the three Salesforce-reporting partners, "Clubs
  that do not use Jotform") report as one `Partner report` batch on the partner account, so they
  are judged by their partner account's `Partner report` batches, not their own (review,
  2026-10-21).
- **An obsolete Contact:** a Participant (a girl) with no attendance in 12 months. Staff, mentor
  and coordinator contacts are never flagged by rule (on 2026-10-21 every girl has attendance; the
  216 contacts without any are staff, mentors or coordinators).
- **Who sets a flag by hand:** administrators only (the System Administrator profile has Edit on
  the four fields). The users who read the reports read the flags too: the
  `Attendance_Report_Viewer` permission set has Read on the four fields.
- **The kept reports and dashboards:** flagged records are shown as before, with the two flags
  available as a filter on any report that lists Accounts or Contacts; nothing is excluded by
  default.

### The fields and the rules

Four checkbox fields, "Duplicate Record" and "Obsolete Record" (`Duplicate_Record__c` and
`Obsolete_Record__c`, on Account and on Contact), default false (unchecked), on every Account and
every Contact, the girls' records included. A flag is report data: it marks a record, and the
record keeps everything it has (its attendance, its contacts, its place in the reports).

**The Matching Rule on Account** (`Account.Name_Parent`, "Name and parent") has two
`MatchingRuleItems`, both required: Name with the Exact method (case-insensitive) and ParentId
(Exact, blank matching blank, so two partner-less strays match). RecordTypeId is not a matching
item: Salesforce does not allow Record Type as a matching-rule field (review, 2026-10-21).
Salesforce's Exact method ignores case (on 2026-10-22 the diagnostic's upper-cased copy of a Club
matched its original); whether it also ignores a difference in spacing (a double space, a tab, a
no-break space) is not documented with certainty and the diagnostic did not probe it, so the
read-back and the monthly check compare the rules' `DuplicateRecordSet`s with
`glow.salesforce.duplicate_account_groups`, which ignores both, and a difference between the two
lists is looked at by hand.

**One report-only Duplicate Rule per record type**, Club (`Account.Name_Parent_Club_Report`,
`sortOrder` 1) and Household (`Account.Name_Parent_Household_Report`, the partner accounts,
`sortOrder` 2), uses that Matching Rule, runs on create and on edit, and carries the condition
Record Type equals that type. That condition picks only which rule runs for the record being
saved: together the two rules are "same name, same parent, same record type" for the record
saved, for the two record types in use. It does not limit the candidates (the records the
Matching Rule finds, whatever their record type), so Salesforce may report a Household account
and a Club of one name and parent as a pair: on 2026-10-22 the diagnostic's Household probe
carrying a club's name and ParentId matched that Club under the Household rule. Ryan accepted
that the same day, with no code or metadata change: `glow.salesforce.duplicate_account_groups`
keeps its own definition (the same record type too), and the monthly check below reviews any such
pair by hand (DECISIONS 2026-10-22). Each Duplicate Rule's action is Allow with Report only, no
Alert and no Block: in
the metadata `actionOnInsert` and `actionOnUpdate` are `Allow`, each operation is Report, and
there is no `alertText`. A possible duplicate is written to a `DuplicateRecordSet` (a Duplicate
Record Set, with one `DuplicateRecordItem` per record) and the save goes through: the rules never
stop a record created by code, and a user sees nothing at the save. The rules never catch the
partner-less twin of a parented club (their parents differ): that stays for the monthly check
below and for the Signals of "Club accounts in Salesforce" (Club accounts without a parent).

Why Report only: an alert refuses a record created by code, and code creates Accounts here. The
Alert on the Contact rule failed live attendance batches mid-way until 2026-10-01 (BACKLOG 54: a
Failed batch with part of the girls saved), and over REST an Alert would need the
`Sforce-Duplicate-Rule-Header: allowSave=true` header on every insert. The attendance processor
(`AttendanceBatchProcessor`) creates a partner-less Club account when a submitted club name
matches no Account, `tools/sf_new_clubs.py` creates the accounts of new clubs from the automatic
sync, and the Jotform integration creates every batch. Only Ryan can choose otherwise, on ticket
#84, knowing that cost.

### The monthly check

With the duplicate-girls check ("Duplicate girls in Salesforce"), read-only, VPN off, from the
repository root:

```bash
sf data query -o glow --json -q "SELECT Id, RecordCount, (SELECT RecordId FROM DuplicateRecordItems) FROM DuplicateRecordSet WHERE DuplicateRule.SobjectType = 'Account'"
python3 - <<'EOF'
from glow.salesforce import Org, duplicate_account_groups
print(duplicate_account_groups(Org("glow").query("SELECT Id, Name, ParentId, RecordTypeId FROM Account")))
EOF
```

Compare the two by Account id: each set's `RecordId`s are one group of `duplicate_account_groups`,
and each group is one set. Expected: the same groups on both sides, and today none (0 sets, 0
groups and 0 cross-type pairs on 2026-10-22). A group is a stray twin, as a rule a partner-less
account the processor made for a name no account carried: re-parent it, never re-create it ("Club
accounts in Salesforce"). A set without a group, or a group without a set, means the rule and the
Python side disagree: on spacing, or on record type - a set holding a Household account and a
Club of one name and parent (cross-type), which Salesforce may report and
`duplicate_account_groups`, keeping its own definition, never groups. Look at the two records of
such a pair by id and decide by hand whether one is a stray of the other (Ryan, 2026-10-22).
Counts and ids only in what is said about it.

### The flagging batch

`RecordFlagBatch` (ticket #85; [plan](plans/2026-10-23-sf-record-flag-batch.md); deployed and
run on 2026-10-26, the Status line above) sets the two flags by the criteria above, one batch job per object in scopes of 200
(`Database.Batchable` with `Database.Stateful`); the class and its test class live in
`data/sf_record_flags_2026-10-23/build/`, never in git. Three modes: `dryRun` counts and writes
nothing; `flag` only sets a flag and never unsets one - it sets a flag where the criteria ask for
one, and a flag set by hand on a record outside the criteria stays (Ryan, 2026-10-24, option a,
after the review of PR #133); `clear` alone takes a flag off: it sets both flags false on every
record that has one, a flag set by hand included. A stale flag - an obsolete flag on a club that
reports again - stays until a `clear` run and a `flag` run, each on Ryan's go. A run writes only
the two flag fields, and only on a record whose flag changes, so a second `flag` run writes
nothing, and so does a `flag` run over a hand-set flag the criteria do not ask for; `finish` logs
counts alone, never a name or a field's value. Account duplicates are judged in code, as
`glow.salesforce.duplicate_account_groups` judges them (the same name ignoring capitals and
spacing - every run of whitespace, a tab or a no-break space included, is one space - the same
parent and the same record type), computed once per job over every Account; every member of a
group is flagged, with no keeper (Ryan, decision 2a). One divergence between the two sides: the
batch lower-cases a name (`toLowerCase`) where `glow.salesforce.duplicate_account_groups` uses
Python's `casefold`, so `Straße` and `STRASSE` are two names to the batch and one to the monthly
check, and a group the check shows with no flag on its members is looked at by hand before
anything else. `Datacloud.FindDuplicates`
is not used by the batch: it does not see records inserted in the same transaction, so the tests
could not prove it. A Contact is a duplicate when it sits in a `DuplicateRecordSet` of the Contact
rule "First & Last & Account" holding two or more records (a set left with one item is no group:
`tools/sf_dupes.py cleanup`). Obsolete is as defined above: a Club's six months are read on
`Attendance_Batch__c.Attendance_Date__c` of its own batches, any status, or, for a club of a
`jotform=no` partner, of the partner account's `Partner report` batches; a Participant's twelve
months on `Attendance__c.Attendance_Date__c`.

**Running it** (the plan's Rollout; each live step on Ryan's go, VPN off, from the repository
root). The script writer `tools/sf_record_flags.py` reads the sheet's exports and Salesforce and
writes the anonymous Apex, ids only: for Account it needs the day's Roster and Partners exports
(the deactivated clubs' Club accounts and the `jotform=no` partners' accounts, which Apex cannot
read: Ryan, decision 1a); for Account it first counts the Households Settings rows with NPSP Automatic Household Naming
on, and for Contact the three things the NPSP and Volunteers workflow rules act on; it writes no
script while any count is not 0 (the guards, below). Each
script is pasted in full in the session, then `sf apex run` runs it and prints no job id (a
one-statement script prints nothing): the read-only `AsyncApexJob` query below, newest first,
gives the job's id and status, and the batch job's finish line in the debug log,
`RecordFlagBatch|<object>|<mode>|duplicate=N|obsolete=N|written=N|failed=N`, gives the counts.

```bash
python3 tools/sheets_client.py export Roster data/roster_<date>.csv
python3 tools/sheets_client.py export Partners data/partners_<date>.csv
python3 tools/sf_record_flags.py --sobject Account --mode dryRun --roster data/roster_<date>.csv --partners data/partners_<date>.csv --out data/sf_record_flags_<date>/scripts/account_dryRun.apex --vpn-off
sf apex run -o glow -f data/sf_record_flags_<date>/scripts/account_dryRun.apex      # Ryan's go
python3 tools/sf_record_flags.py --sobject Contact --mode dryRun --out data/sf_record_flags_<date>/scripts/contact_dryRun.apex --vpn-off
sf apex run -o glow -f data/sf_record_flags_<date>/scripts/contact_dryRun.apex      # Ryan's go
sf data query -o glow -q "SELECT Id, Status, JobItemsProcessed, TotalJobItems, NumberOfErrors, CreatedDate FROM AsyncApexJob WHERE ApexClass.Name = 'RecordFlagBatch' ORDER BY CreatedDate DESC LIMIT 1"   # after each run: the job's id and status, read only
```

The same with `--mode flag` is the run (Account first, then the guard and Contact, at a quiet
hour), after Ryan confirmed the dry run's counts on the ticket; `--mode clear` is the way back.

**The guard** (Ryan, 2026-10-23, option a): two NPSP workflow rules, `Preferred_Email__c` and
`Preferred_Phone__c`, fire on any edit of a Contact whose Email or Phone is blank and fill it from
the Work, Home and Alternate e-mail fields (or the Work, Home, Mobile and Other phone fields), and
the Volunteers signup rule sends mail for a web signup of the day; the other Contact rules need a
changed Email or Phone or a new record, and Account has only a Flow that acts when the owner
changes. On 2026-10-23 the three counts were 0, 0 and 0, so a flag-only update changes nothing
else. The tool counts them right before each Contact script (three `SELECT COUNT() FROM Contact
WHERE …`, counts only) and refuses the script while any count is not 0; the plan's Rollout counts
them again before the Contact run. The NPSP handlers and MC4SF are accepted as harmless for a
flag-only update (Ryan, 2026-10-23).

**The household-naming guard** (Ryan, 2026-10-26): with NPSP's Automatic Household Naming on, an
update of a partner's household Account renames it, so a `flag` or `clear` run over Accounts would
rename partners. Production has it off (the org default, `npo02__Households_Settings__c`), but
NPSP forces it on inside Apex tests, which is how the second check-only of 2026-10-26 found it.
Before every Account script, in each mode, the tool runs `SELECT COUNT() FROM
npo02__Households_Settings__c WHERE npo02__Advanced_Household_Naming__c = true` (every row: the
org default, a profile's or a user's), prints it, and writes no script while it is not 0: turn
the naming off in NPSP Settings, or ask Ryan.

**The way back:** a `clear` run of the same batch, `new RecordFlagBatch('Account', 'clear')` and
`new RecordFlagBatch('Contact', 'clear')` through `tools/sf_record_flags.py --mode clear` and
`sf apex run`, sets both flags false on every record that has one - the only way a flag comes off,
since a `flag` run never unsets one; every flag was false before the fields were created on
2026-10-22, and the flags set by hand come off with it, so the plan's Rollout counts those first. The ids a run flagged are saved in
`data/sf_record_flags_<date>/flagged.csv` (ids only) for a rollback of that run alone, record by
record through the write connector.

## Attendance totals and partner-reported counts

- **When:** reading an attendance total; the monthly `check`; the three partners' monthly copy, about the 12th of each month.
- **Status:** the field and the processor change deployed 2026-10-07 03:22 UTC (Ryan's quick deploy `0AfRP000002gKqn0AE` of validation `0AfRP000002gKnZ0AU`), the one-off back-fill and the dashboard's totals done the same day; since 2026-10-15 ~09:05 UTC (Ryan's go, deploy `0AfRP000002h9dB0AQ`) the total counts Jotform plus the three partners below and nothing else ([Result](plans/2026-10-15-attendance-total-three-partners.md#result)); decided 2026-10-19 (BACKLOG 72, ticket #60): the three partners' figure is their Monthly Report's Monthly Max, copied monthly by `tools/sf_partner_monthly.py`; September 2026 copied on Ryan's go 2026-10-20 07:33-07:38 UTC: three `Partner report` batches dated 2026-09-30, 110 + 320 + 315 = 745, read back equal to the three Monthly Reports ([Result](plans/2026-10-19-partner-monthly-max.md#result)); decided 2026-10-19 (ticket #59): the dashboard's measure is girls who attended, Jotform girls plus the three partners' Monthly Max - deployed on Ryan's go 2026-10-21 04:59-05:10 UTC, the reports first (checked against SOQL), then the dashboard, read back; tiles 3,633 last month and 2,944 this month at the 05:10 UTC refresh ([Result](plans/2026-10-20-girls-attended-tiles.md#result)).
- **Verify:** the Signals, below.
- **Rollback:** of a monthly copy, from `data/sf_partner_monthly/ledger.csv` (each batch's last row is its state): delete an inserted batch by its `batch_id`, set an updated one's `Girls_Present__c` back to the row's `old` count - one record per call, VPN off, Ryan's go ([plan](plans/2026-10-19-partner-monthly-max.md#rollback)). Of #59's tiles: "Attendance dashboard in Salesforce", Rollback. Of the 2026-10-15 rule, redeploy only the three components it changed from `data/sf_totals2_2026-10-15/before/`, after a fresh retrieve of them equals `after/` ("Attendance dashboard in Salesforce", Rollback); of the field and the processor's 03:22 UTC change (2026-10-16): never redeploy `data/sf_totals_2026-10/before/` - it would also undo the processor's name cleaning (2026-10-07 04:38 UTC); retrieve what is live and undo only that change in the copy (DECISIONS 2026-10-16). The name cleaning's own rollback ([plan](plans/2026-10-07-processor-name-spacing.md), Result): a fresh retrieve of the two classes and the trigger must equal `data/sf_processor_2026-10-07/after`, ignoring a missing final newline (Salesforce stores the test class without it; any other difference: stop and build from the retrieve); then redeploy the two classes of `data/sf_totals_2026-10/deployed/`. The fields can stay.

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

**A mentor's correction** (since 2026-10-22, ticket #108;
[plan](plans/2026-10-22-correction-merge.md)). A re-submission for a club and date that already
has a `Success` batch, with the same module, adds only the girls missing from that date's rows -
ticked now and without a row for that club and date, whoever made the rows - as `Attendance__c`
rows of the original batch (the oldest `Success` batch of that club and date; the rows carry its
module, week and year); never a row removed, never a girl counted twice. The original's
`Girls_Present__c` moves to the new total, the count of its own rows after the merge. The
correction's own batch is `Success` with `Status_Message__c` `merged into <original batch id>`,
no count and no rows of its own. A re-submission with a different module (a special event on a
curriculum day, or the other way round) is still `Failed` "Duplicate": one session per club per
day (DECISIONS 2026-10-13). A re-submission that adds nobody (every girl ticked is already on
that date) stays `Failed` "Duplicate" exactly as before, as does one for a day whose `Success`
batch has no rows of its own (a typed aggregate, a `Partner report` batch, one of the three
legacy blanks of BACKLOG 73). On the dashboard a merged correction is not a second session and
not a blank: its girls count through the original batch's rows (the tiles read `Attendance__c`),
and its empty `Girls_Present__c` is not a 0, so the blank-submissions report does not list it;
`sf_girls_present.py check` leaves merged corrections out (Signals, below). The message is
filtered on, never selected or printed (on other batches it can quote a name).

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
- The reports, the formula fields and the filter that make the tiles: "Attendance dashboard in
  Salesforce".
- The monthly copy's batch sits on the partner account itself, which the 2026-10-15 filter 3 (a
  club whose parent is one of the three partners) missed; since 2026-10-21 the tiles read these
  batches through the report type `Attendance_Batches_and_Girls` (September 2026: 745 of last
  month's 3,633).
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
| `Creator__c` | `Partner report`: the tiles' partner part (`Partner_Girls__c`, since #59); it never counts in a Jotform-only report, which takes only `Creator__c` values starting with `Jotform` |
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
"Duplicate" (the copy names nobody, so it adds nobody: since 2026-10-22 only a re-submission that
adds a girl merges). The partner account has no Jotform batches, so none is expected; if one is there and
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
  (no rows by design), and a merged correction (`Success`, `merged into <id>`, no count and no
  rows by design since 2026-10-22) is left out of both counts: the tool tells it apart by a
  condition on `Status_Message__c` in the WHERE, never by selecting it. An original whose count
  did not move with the rows a correction added is a `differ`.
- The dashboard's two tiles (since 2026-10-21, #59): each tile, the reports' `FORMULA1`, =
  `COUNT_DISTINCT(Contact__c)` over the month's Jotform `Attendance__c` rows, by the batch's date
  as the reports filter (`SELECT COUNT_DISTINCT(Contact__c) FROM Attendance__c WHERE
  Attendance_Batch__r.Attendance_Date__c = LAST_MONTH AND Attendance_Batch__r.Processing_Status__c
  = 'Success' AND Attendance_Batch__r.Creator__c LIKE 'Jotform%'`; `THIS_MONTH` for the other
  tile) + `SUM(Girls_Present__c)` over the three partners' `Partner report` batches for the month
  (the monthly copy's query, next). Read 2026-10-21: last month 3,633 = 2,888 + 745, this month
  2,944 = 2,944 + 0; the by-month chart September 3,633, October 2,944.
- **The blank key, settled 2026-10-21.** The report type gives each batch without rows (the three
  partners' batches among them) one report row with an empty `Contact_Key__c`, and the unique
  count counts it as one value (read 2026-10-21: 2,889 against SOQL's 2,888 last month, 2,945
  against 2,944 this month). `FORMULA1` takes it back off - one when the period has a row-less
  batch (`RowCount` above the sum of `Has_Row__c`), else 0 - so the tiles equal the SOQL sum
  above. A tile one above it means that correction broke; 745 less last month means the
  partners' batches dropped out of the filter: stop and ask Ryan either way.
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
- **Status:** live since 2026-10-02 (`fix1` 2026-10-06, `totals1/` 2026-10-07; [Result](plans/2026-10-02-attendance-dashboard.md#result-2026-10-02)); the total counts Jotform plus the three partners since 2026-10-15 ~09:05 UTC ([Result](plans/2026-10-15-attendance-total-three-partners.md#result)); #59, the two "Girls who attended (Jotform + 3 partners)" tiles: deployed on Ryan's go 2026-10-21 - phase 1 (the fields, the report type, the three reports, the permission set and the Admin profile entries) `0AfRP000002hhdF0AQ` 04:59 UTC, the `Has_Row__c` fix `0AfRP000002hhi50AA` 05:06 UTC (check-only `0AfRP000002hhgT0AQ`), phase 2 (the dashboard) `0AfRP000002hhlJ0AQ` 05:08 UTC (check-only `0AfRP000002hhjh0AA`); all 10 components read back into `data/sf_girls_tiles_2026-10-20/after/`, equal to `build/` apart from Salesforce's normalisation ([Result](plans/2026-10-20-girls-attended-tiles.md#result)); the 2026-10-09 Access change (the folders shared, the permission set, "(test)" dropped from the labels) is deployed since 2026-10-09 ~05:35 UTC by the metadata dates, its deploy id not known here (read 2026-10-15; Access, below; [Result](plans/2026-10-09-attendance-reports-public.md#result-2026-10-09-build-and-check-only-nothing-deployed-no-record-written)).
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

**The headline tiles** (ticket #59, [plan and Result](plans/2026-10-20-girls-attended-tiles.md);
deployed 2026-10-21 in two phases, the reports first, checked against SOQL through the Analytics
API, then the dashboard; `data/sf_girls_tiles_2026-10-20/build/BUILD.md` describes the build, and
`after/` beside it is the read-back):
- Since 2026-10-21 (#59) the top row is two tiles headed "Girls who attended (Jotform + 3
  partners)", one for last month and one for this month so far.
- Each tile is the month's girls who attended, Jotform and the three partners together; how it is
  computed is in "Attendance totals and partner-reported counts".
- The four tiles of 2026-10-15 are replaced by these two; total attendance (girls × sessions) is
  no longer tracked (Ryan, 2026-10-19). The 2026-10-15 change:
  [plan](plans/2026-10-15-attendance-total-three-partners.md).
- The monthly chart "Girls who attended per month (Jotform + 3 partners)" (the report
  `Girls_Attended_by_Month`, months since September 2026) replaces "Total attendance per month
  (Jotform + 3 partners)" in the same place; "Girls attending per month (Jotform only)" and every
  other component are unchanged. The component headers carry "(Jotform + 3 partners)"; the
  report's own chart title is "Girls who attended per month".
- The "How to read this dashboard" box defines girls who attended as the Jotform girls, each girl
  once however many sessions she came to, plus the three partners' Monthly Max, copied in about
  the 12th of the next month. Its next bullet says "Jotform only" means the Jotform girls alone,
  each once, that attendances (girls × sessions) are no longer a headline number, and that the
  Monthly Report of any other partner is never added.
- **The new components** (seven, and Read on the three fields in the permission set
  `Attendance_Report_Viewer` and the Admin profile):
  - The formula field `Attendance_Batch__c.Partner_Girls__c` ("Girls (partner report)") =
    `Girls_Present__c` when `Creator__c` is `Partner report`, else 0 (a blank counts as 0).
  - The text formula field `Attendance__c.Contact_Key__c` = `CASESAFEID(Contact__c)`: the girl's
    record id as text, never a name. The reports unique-count it, because a summary formula
    cannot unique-count a lookup (the check-only refused `Attendance__c.Contact__c:UNIQUE`,
    2026-10-21).
  - The number formula field `Attendance__c.Has_Row__c` = 1 on every attendance row: its sum is
    the count of real rows, which tells the summary formula whether a row-less batch is in the
    period (the blank key, "Attendance totals and partner-reported counts", Signals).
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
  - Each report's summary formula `FORMULA1` ("Girls who attended (Jotform + partners)", within
    the label's 40-character limit) = the unique `Contact__c` key + the sum of `Partner_Girls__c`,
    less one for the empty key of a row-less batch, the number the tiles and the chart show:
    `Attendance__c.Contact_Key__c:UNIQUE - IF(RowCount > Attendance__c.Has_Row__c:SUM, 1, 0) +
    Attendance_Batch__c.Partner_Girls__c:SUM`.
  - The dashboard `Attendance/Jotform_Attendance_test` itself: the two tiles, the chart and the box
    above.
- **Known limitation, the Partner filter**: the Partner filter set to one of the three partners
  shows only that partner's Jotform girls (0 since #56 took their clubs off the forms on
  2026-10-16), and its Monthly Max drops out, because the partner's batch sits on the partner
  account itself, whose parent is blank. Any other partner, or All, shows the right number.
- A renamed partner account drops out of filter 4 (it matches the names): rename the filter values
  with the account, on Ryan's go.
- **Reports deleted** 2026-10-21 05:22:34 UTC on Ryan's go, the four the dashboard stopped using
  with #59: `Total_Attendance_Last_Month`, `Jotform_Total_Attendance_Last_Month`,
  `Total_Attendance_by_Partner_by_Month` and `Jotform_Attendance_This_Month` (destructive deploy
  `0AfRP000002hhq90AA`, check-only `0AfRP000002hhmv0AA`, from
  `data/sf_girls_tiles_2026-10-20/delete_old_reports/`). Before the delete, SOQL on
  `DashboardComponent` showed no dashboard using them; after it, SOQL on `Report` finds only the
  three `Girls_Attended_*` of the seven names. Their rollback: Rollback, below.
- The signal for each tile (SOQL) and the blank key: "Attendance totals and partner-reported
  counts", Signals.

**Filters:**
- The dashboard's **Partner** filter covers every component. It holds the 49 partner names
  that have clubs, typed in exactly (Salesforce allows 50 values per filter).
  - A new partner must be added by hand to **both** lists: the dashboard's `partners.json`
    (the Partner filter's `Parent.Name` values, below) and `glow/sf_partners.csv` (the partner
    map the automatic club accounts read, partner → its account; "New clubs' accounts,
    automatically"). Two lists of the same 49 partners, kept separate on purpose: one is filter
    text, the other account ids. Check its account name against the Monthly Reports' "test"
    filter ("The keep list").
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
    reports included, and since 2026-10-21 (#59) the three new fields
    `Attendance_Batch__c.Partner_Girls__c`, `Attendance__c.Contact_Key__c` and
    `Attendance__c.Has_Row__c`. The list is in the plan; the derivation is
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
  Jotform plus the three partners, the new report `Jotform_Total_Attendance_Last_Month`
  (deleted 2026-10-21), the four tiles #59 replaces), nor for #59; a deploy of its build would
  undo them on the dashboard and the two Total reports. The 2026-10-15 change was made by
  editing a fresh retrieve (`data/sf_totals2_2026-10-15/before/`), and the deployed state was
  retrieved back into `data/sf_totals2_2026-10-15/after/` (0 differences from the build). #59
  was built the same way, from the fresh retrieve `data/sf_girls_tiles_2026-10-20/before/` (into
  `build/`), deployed 2026-10-21 and read back into `data/sf_girls_tiles_2026-10-20/after/`: that
  is what is live today. A change starts from a fresh retrieve of what is live and edits that
  (The steps, below).
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
    `Blank_Submissions` 00ORP000009c8iX2AQ. The two Total reports among them were deleted
    2026-10-21 (#59; "The headline tiles", above).
  - `data/sf_totals2_2026-10-15/`: the 2026-10-15 change (the total as Jotform plus the three
    partners). `before/` is what was live just before it (the dashboard, the reports
    `Total_Attendance_Last_Month`, `Total_Attendance_by_Partner_by_Month`,
    `Jotform_Attendance_by_Partner_by_Month` and the report type `Attendance_Totals`); the
    rollback deploys only the three of them the deploy changed (Rollback, below); `after/` is the
    read-back of the deploy (0 differences from the build). Its two Total reports and
    `Jotform_Total_Attendance_Last_Month` were deleted 2026-10-21.
- After a deploy, Salesforce writes `expandOthers` true on every report chart and drops or adds a
  few default attributes on the dashboard (for `totals1/`: `useReportChart` dropped,
  `showPicturesOnCharts` and the owner added, apostrophes escaped). A retrieve differs from
  `gen.py` only in those.
- **The steps:**
  1. Back up what is live: `sf project retrieve start -o glow` the reports below (the
     `Jotform_*` of the first deploy; the six of `totals1/`; and the report type
     `Attendance_Totals`; since 2026-10-21 without the four deleted reports,
     `Jotform_Attendance_This_Month`, the two Total reports `Total_Attendance_Last_Month` and
     `Total_Attendance_by_Partner_by_Month`, and `Jotform_Total_Attendance_Last_Month`), the
     test report and the dashboard (`Dashboard:Attendance/Jotform_Attendance_test`), into a new
     dated folder (as `data/sf_totals2_2026-10-15/before/`). It is the starting point and, for
     only the components the change then makes, the rollback (Rollback, below); compare it with
     `data/sf_totals2_2026-10-15/after/` (or the latest read-back) to see whether anything
     changed in Salesforce since. Since #59 (2026-10-21) the backup also takes its 10 components
     (as in `data/sf_girls_tiles_2026-10-20/after/`), and that `after/` is the latest read-back.
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
  `data/sf_totals2_2026-10-15/before/` (below); for #59 (deployed 2026-10-21), the two components it
  changed, from `data/sf_girls_tiles_2026-10-20/before/`, and destructive deploys for the seven
  it created (below).
  Never redeploy an older package: `data/sf_dashboard_2026-10-02/`'s `before/`, `build/`,
  `after/`, `after2/`, `fix1/`, `totals1/`, `live_2026-10-07/`, `public_2026-10-09/`,
  `before_public_2026-10-09/`, or a `gen.py` build - each would overwrite later changes.
- Test report: superseded 2026-10-16 - do not redeploy `before/` (it would undo the 2026-10-09
  label). To undo a change to it, retrieve it, edit only that change in the copy, check-only,
  Ryan's go, deploy.
- The new components: delete them with a `destructiveChanges.xml`, except task #102's (the last
  entry below), which are moved to Decommissioned and never deleted. Never delete
  `Jotform_Monthly_Attendance_test`; it predates this work. The new components are:
  - the reports `Jotform_Attendance_by_Week`, `Jotform_Attendance_by_Month`,
    `Jotform_Attendance_Last_Month`, `Jotform_Attendance_This_Month` (deleted 2026-10-21),
    `Jotform_Sessions_by_Module_Last_Month` and `Jotform_Clubs_No_Attendance_Last_Month`;
  - the dashboard `Jotform_Attendance_test`;
  - since `totals1/` (2026-10-07): the reports `Total_Attendance_by_Partner_by_Month` (deleted
    2026-10-21), `Jotform_Attendance_by_Partner_by_Month`, `Total_Attendance_Last_Month` (deleted
    2026-10-21),
    `Clubs_Not_Submitting_Last_14_Days`, `Clubs_Not_Submitting_Since_1_Sept` and
    `Blank_Submissions`, then - **last**, after the six reports that use it - the report type
    `Attendance_Totals`; never `Attendance_Batches` (the vendor's report type). The dashboard
    itself is never rolled back by redeploying `after2/` or `live_2026-10-07/` (superseded
    2026-10-16: they would undo the 2026-10-09 and 2026-10-15 changes); before the six reports go,
    retrieve it, remove the `totals1/` tiles in that copy, check-only, Ryan's go, deploy (the six
    reports and the type may stay).
  - the exception, never deleted: since task #102 (built 2026-10-24; deployed only on Ryan's
    go), the reports
    `Clubs_Not_Submitting_Last_Week`, `Submissions_by_Club_and_Week`,
    `Late_Submissions_Last_Month` and `Submission_Delay_by_Partner_by_Month`, each moved to
    Decommissioned, never deleted (DECISIONS 2026-10-21), after any dashboard component that
    reads them (task #103), and edited there to drop the timing fields before the columns go; and
    the four columns `Submitted_At__c`, `Submission_Delay_Days__c`,
    `Session_Month__c` and `Session_Week__c` that #102 adds to the report type `Attendance_Totals`,
    taken out of a fresh retrieve of it and deployed (check-only, Ryan's go), never by deleting
    the type or redeploying an older copy ("Submission timing in Salesforce", The timing reports).
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
  Since #59 is deployed (2026-10-21), the dashboard's fresh retrieve differs from `after/`, so
  this rollback stops at its check: roll #59 back first (next). Its three reports,
  `Total_Attendance_Last_Month`, `Total_Attendance_by_Partner_by_Month` and
  `Jotform_Total_Attendance_Last_Month`, were deleted 2026-10-21 too: they come back with the
  deleted reports' rollback (below).
- The #59 change (the two girls-who-attended tiles, deployed 2026-10-21), [plan](plans/2026-10-20-girls-attended-tiles.md#rollback).
  `data/sf_girls_tiles_2026-10-20/before/` is the fresh retrieve of what was live on 2026-10-20
  right before it (its dashboard identical to what the 2026-10-15 deploy left). #59 changed two
  components, the dashboard `Attendance/Jotform_Attendance_test` and the permission set
  `Attendance_Report_Viewer` (and three read-only entries in the Admin profile, which go with the
  fields), and created seven: the fields `Attendance_Batch__c.Partner_Girls__c`,
  `Attendance__c.Contact_Key__c` and `Attendance__c.Has_Row__c`, the report type
  `Attendance_Batches_and_Girls` and the reports `Attendance/Girls_Attended_Last_Month`,
  `Attendance/Girls_Attended_This_Month` and `Attendance/Girls_Attended_by_Month`.
  1. VPN off. Retrieve the dashboard and the permission set fresh and compare them with
     `data/sf_girls_tiles_2026-10-20/after/`, the read-back; if either differs (beyond
     Salesforce's normalisation), someone changed it since - stop and build the rollback from
     that fresh retrieve instead.
  2. Equal: Ryan's go. First bring back the four deleted reports (the deleted reports' rollback,
     below), because `before/`'s dashboard reads them. From `data/sf_girls_tiles_2026-10-20/before/`,
     redeploy only those two files: copy `before/dashboards/Attendance/Jotform_Attendance_test.dashboard-meta.xml` to
     `<new folder>/force-app/main/default/dashboards/Attendance/` and
     `before/permissionsets/Attendance_Report_Viewer.permissionset-meta.xml` to
     `<new folder>/force-app/main/default/permissionsets/`, beside an `sfdx-project.json` (as
     `build/`'s), then within `<new folder>` run `sf project deploy start --dry-run -o glow -d
     force-app` and the same command minus `--dry-run`. The rest of `before/` (the live reports,
     the report type `Attendance_Totals`, the object, the Admin profile) is never deployed from it.
  3. With the dashboard off the new reports, delete the seven new components in three destructive
     deploys, in this order, each a `destructiveChanges.xml` beside an empty `package.xml`,
     check-only first, on Ryan's go:
     - first the reports `Girls_Attended_Last_Month`, `Girls_Attended_This_Month` and
       `Girls_Attended_by_Month` (`Report` members `Attendance/Girls_Attended_Last_Month` and so
       on; they may also go as the `--pre-destructive-changes` file of the report type's deploy);
     - then the report type `Attendance_Batches_and_Girls` (`ReportType`);
     - then the three fields `Attendance_Batch__c.Partner_Girls__c`, `Attendance__c.Contact_Key__c`
       and `Attendance__c.Has_Row__c` (`CustomField`; their Admin profile entries go with them).

     Each deploy is its own folder holding an empty `package.xml` (`<Package>` with only
     `<version>62.0</version>`) and a `destructiveChanges.xml` listing that deploy's components,
     beside an `sfdx-project.json` (as in step 2) and the empty `force-app/` folder it names:
     `--manifest` needs an SFDX project.
     Within the folder, check-only: `sf project deploy start --dry-run -o glow --manifest
     package.xml --post-destructive-changes destructiveChanges.xml`; then Ryan's go and the same
     command minus `--dry-run`. The next deploy starts after this one succeeded.
  4. Retrieve the dashboard and the permission set again and compare with `before/`. The four
     reports #59 stopped using are back on the dashboard; revert #59's RUNBOOK change with it.
- The four reports deleted 2026-10-21 (`Total_Attendance_Last_Month`,
  `Jotform_Total_Attendance_Last_Month`, `Total_Attendance_by_Partner_by_Month`,
  `Jotform_Attendance_This_Month`; destructive deploy `0AfRP000002hhq90AA`): redeploy any of them
  from `data/sf_girls_tiles_2026-10-20/before/reports/Attendance/` - a new folder with an
  `sfdx-project.json` and the report's file under `force-app/main/default/reports/Attendance/`,
  check-only, Ryan's go, deploy.
- Nothing else depends on them. The pilot "Attendance" dashboard and its reports were not
  touched, nor the vendor's report type `Attendance_Batches`.

## Submission timing in Salesforce

- **When:** a report or dashboard on when clubs submit (tasks #102 and #103); the monthly
  Salesforce checks; a question about a batch's session week or its delay.
- **Status:** the four formula fields are live since 2026-10-24 (deploy `0AfRP000002i4Er0AI`,
  06:41 UTC, Ryan's go). The first delay formula was a day short for submissions before about
  07:00 UTC (the check: 153 of 1,123 batches); `Submission_Delay_Days__c` was redeployed alone
  with the corrected text the same day (deploy `0AfRP000002i4LJ0AY`, 06:59 UTC), and the check
  reads `-> OK` on all 1,123 ([plan](plans/2026-10-23-submission-timing.md), Result). The four
  timing reports of task #102 are built, not deployed ("The timing reports", below).
- **Dry run:** the check-only deploy (`--dry-run`), the plan's Rollout step 4; the check below
  is read-only.
- **Apply:** the deploy, Ryan's go, VPN off (the plan's Rollout steps 5-6).
- **Verify:** retrieve again and compare with the build and with `before/`; then
  `python3 tools/sf_session_timing.py check --vpn-off` -> `-> OK`.
- **Rollback:** below.
- **History:** [plan](plans/2026-10-23-submission-timing.md) (the proofs, the deploy, tasks
  #102 and #103).

Since task #100 (DECISIONS 2026-10-23) a batch's session month and week, and for a live Jotform
batch its submission time and the delay from the session to it, are four formula fields on
`Attendance_Batch__c`, computed by Salesforce from `Creator__c`, `CreatedDate` and
`Attendance_Date__c`; the formula texts are `glow/session_timing.py SF_FORMULAS`, and task #101
deploys them. A formula field changes no record and runs nothing: the processor's trigger and
the Jotform integration are untouched.

**The fields** (API name, label, type):
- `Submitted_At__c` ("Submitted at", Date/Time): the batch's `CreatedDate` when `Creator__c` is
  `Jotform`, else blank.
- `Submission_Delay_Days__c` ("Days from session to submission", Number): whole days from
  `Attendance_Date__c`, the session date, to the UTC day of the submission, blank without a
  submission time, negative when the form was submitted before the session date (a date typo,
  BACKLOG 79).
- `Session_Month__c` ("Session month", Text): the session's month as `2026-10`, from
  `Attendance_Date__c`.
- `Session_Week__c` ("Session week", Text): the week of the month the session date falls in, as
  `2026-10 week 2`.

**The week rule:** the week is the week of the month by day of the session date: days 1-7 are
week 1, 8-14 week 2, 15-21 week 3, 22-28 week 4 and 29-31 week 5, shown as `2026-10 week 2`.
It is the calendar week of the session date, not the curriculum "Session N" in `Module_Week__c`
and not Salesforce's Sunday-start report weeks (DECISIONS 2026-10-23).

**The time zone:** the submission day, the day the delay counts to, is the UTC day of
`CreatedDate`, which the formula takes as `DATEVALUE(TEXT(Submitted_At__c))`: `TEXT()` of a
date/time is the UTC timestamp `YYYY-MM-DD HH:MM:SSZ` and `DATEVALUE` of that text is its UTC
date. `DATEVALUE` on the date/time itself converts in the running user's time zone (here the org's default,
America/Los_Angeles): the
first deploy's formula did, and the check found it a day short for every submission between
00:00 and about 07:00 UTC (2026-10-24, 153 of 1,123 batches), so the field is redeployed with
the `TEXT()` form (DECISIONS 2026-10-24; the plan's Result says when). That is the clock's day
in UTC rather than the mentor's local day: a late-evening submission in the Americas counts as
the next day and an early-morning one in Asia as the same day, so a delay of 1 can be a form sent
the same evening.

**Which batches have one:** only a batch whose `Creator__c` is exactly `Jotform` has a
submission time, because the native Jotform Salesforce V2 integration creates the batch the
moment the form is submitted, so its `CreatedDate` is the submission time. The September
back-fill batches (`Creator__c` starting `Jotform back-fill`) and the three partners' monthly
batches (`Partner report`, `tools/sf_partner_monthly.py`) were created later by tools, so they
have no submission time and no delay, but they do have a session month and week. A batch that
`tools/sf_backfill.py` sends later carries the same back-fill creator and gets none either.

**The check** (read only, VPN off): `python3 tools/sf_session_timing.py check --vpn-off`
compares every batch since 2026-09-01 with `glow/session_timing.py` in one explicit-field SOQL
query (never `Contact_IDs__c`) and prints `checked N batches` with the count of differing values
per field, then `-> OK`, or `-> DIFFER` with up to 10 lines of batch Name, field, Salesforce's
value and the expected one, exit 1; `--since 2026-10-01` narrows the window. Batch Names and
counts only, nothing written. An HTTP 400 means the fields are not deployed yet (task #101), or
the login cannot read them. Run it after the deploy, after any change to `SF_FORMULAS`, and
with the monthly Salesforce checks.

**Access:** the permission set `Attendance_Report_Viewer` and the Admin profile read the four
fields (one Read entry per field in each, deployed with the fields), so a report that shows,
groups or filters on them works for every viewer; a filter on a field the viewer cannot read is
dropped silently ("Attendance dashboard in Salesforce", Access). A new report on another field
needs that field's Read added to the set.

**Rollback** ([plan](plans/2026-10-23-submission-timing.md#rollback)): the reports that use or
filter on the fields go first, never deleted (the archive rule of DECISIONS 2026-10-21): each is
edited to drop the fields, since a report that uses a field blocks its deletion wherever the
report is: a report kept is edited, and its copy to Decommissioned is edited to drop them too
(a copy that kept them would block the deletion), so the report as it was, fields and all, is
kept only in the fresh retrieve the edit starts from; a report retired is moved to
Decommissioned and edited there to drop them; then the four fields `Submitted_At__c`,
`Submission_Delay_Days__c`, `Session_Month__c` and `Session_Week__c` are deleted by a
`destructiveChanges.xml` deploy, check-only first and on Ryan's go, their permission-set and
Admin profile entries with them. Never an older build (DECISIONS 2026-10-16): the deploy created
the four fields and only added their entries to the permission set and the Admin profile, which
go with the fields when they are deleted, so nothing is redeployed from its `before/`.

### The timing reports

**Status:** built 2026-10-24 offline (task #102), in `data/sf_session_timing_2026-10-24/t102_build/`
(`build/`, `pattern/`; owner only, never committed): the four reports below, and the report
type `Attendance_Totals` with the four fields added to its columns (a custom report type offers
a new field only once it is in its layout; the retrieve of 2026-10-24 09:24 UTC, after the fields' deploy, had none of
them). Nothing is deployed: the fresh retrieve, the check-only deploy, the deploy, the read-back
and each report's run through the Analytics API against its SOQL check wait for Ryan's go, VPN
off ([plan](plans/2026-10-23-submission-timing.md), "Task #102: the timing reports").

The four reports are in the Attendance report folder (`Attendance`), beside the dashboard's other
reports, and answer what GLOW staff asked on 2026-10-22: which clubs have not submitted for a
week, and how long clubs take from a session to its submission. Each report carries the partner,
the column the dashboard's Partner filter uses (`PARENT.NAME` on the Account report,
`Attendance_Batch__c$Account__c.Parent` on the three batch reports), and the unlocked Partner and
Club "contains" filters of the other attendance reports. They read only fields the existing
reports already show and the four timing fields, which `Attendance_Report_Viewer` reads (Access,
above). The SOQL check beside each name reproduces the report's total (read only, VPN off, the CLI
login `glow` or the read-only connector; counts and partner names only):

- `Clubs_Not_Submitting_Last_Week` ("Clubs Not Submitting - Last Week", on Accounts, built from
  `Clubs_Not_Submitting_Last_14_Days`) answers which clubs sent nothing for last week's sessions:
  the club accounts with a partner and no batch of any status dated last week, grouped by
  partner, less the partners left out (below). Check: `SELECT COUNT(Id) FROM Account WHERE
  RecordType.DeveloperName = 'Club' AND ParentId != null AND Parent.Name NOT IN ('Education and
  English for You', 'Tumaini La Maisha', 'Ng\'aa Maskani', 'Angelo Patri School', 'Detroit Public
  Schools', 'Ewa Makai Middle School', 'Farmington Municipal School District', 'HOLA', 'Holbrook
  Unified School District') AND Id NOT IN (SELECT Account__c FROM Attendance_Batch__c WHERE
  Attendance_Date__c = LAST_WEEK)`.
- `Submissions_by_Club_and_Week` ("Submissions by Club and Week", a matrix on `Attendance_Totals`)
  answers in which weeks each club submitted: rows partner then club, columns the session week
  (`Session_Week__c`, as `2026-10 week 2`), each cell the count of batches of any status, for
  sessions dated this week and the 8 weeks before it (`N_WEEKS_AGO:8` to `THIS_WEEK`); a blank
  cell is a week with no submission. Check: `SELECT Account__r.Parent.Name, Account__r.Name,
  Session_Week__c, COUNT(Id) FROM Attendance_Batch__c WHERE Attendance_Date__c >= N_WEEKS_AGO:8
  AND Attendance_Date__c <= THIS_WEEK GROUP BY Account__r.Parent.Name, Account__r.Name,
  Session_Week__c`.
- `Late_Submissions_Last_Month` ("Late Submissions - Last Month", a summary on
  `Attendance_Totals`) answers how long each submission of last month took: every live Jotform
  batch (`Creator__c` `Jotform`, `Processing_Status__c` `Success`) with a session date last month,
  grouped by partner, with its club, session date, submission time (`Submitted_At__c`) and days
  from session to submission (`Submission_Delay_Days__c`), each partner's batches sorted with the
  largest delay first. Check: `SELECT
  Account__r.Parent.Name, Account__r.Name, Attendance_Date__c, Submitted_At__c,
  Submission_Delay_Days__c FROM Attendance_Batch__c WHERE Creator__c = 'Jotform' AND
  Processing_Status__c = 'Success' AND Attendance_Date__c = LAST_MONTH ORDER BY
  Submission_Delay_Days__c DESC`.
- `Submission_Delay_by_Partner_by_Month` ("Submission Delay by Partner by Month", a summary with a
  bar chart) answers how long each partner's clubs take, month by month: the average and the
  maximum of `Submission_Delay_Days__c` over the live Jotform batches, by partner and session
  month (`Session_Month__c`), this month and the 11 before it (`N_MONTHS_AGO:11`); the chart shows
  the average, a bar per partner and month. Check: `SELECT Account__r.Parent.Name,
  Session_Month__c, AVG(Submission_Delay_Days__c), MAX(Submission_Delay_Days__c), COUNT(Id) FROM
  Attendance_Batch__c WHERE Creator__c = 'Jotform' AND Processing_Status__c = 'Success' AND
  Attendance_Date__c >= N_MONTHS_AGO:11 GROUP BY Account__r.Parent.Name, Session_Month__c`.

Not confirmed offline: SOQL often refuses `GROUP BY`, `AVG` or `MAX` on a formula field
(`Session_Week__c`, `Session_Month__c`, `Submission_Delay_Days__c`). The `GROUP BY` statements
above are the first try. When SOQL refuses one, the check that the plan's Task #102 Rollout step 7 runs is
the fallback: select the same rows ungrouped, with the same `WHERE` and the fields the statement
would group or aggregate, and total them offline (the count per partner, club and week; the
average and the maximum per partner and month). The reports themselves group by those fields,
which reports allow.

**Who is left out** (Ryan, 2026-10-24): the clubs of the three partners that report monthly
through Salesforce (Education and English for You, Tumaini La Maisha and Ng'aa Maskani, 38 clubs
off the forms since 2026-10-16) and the U.S clubs (their form is disabled) are left out of
`Clubs_Not_Submitting_Last_Week`, where they would otherwise show every week. They are left out
by a filter on their partner account names, `Parent.Name` in the SOQL check and a locked
`PARENT.NAME` "not equal to" in the report, which names the three partners and the six U.S
partner accounts, Angelo Patri School, Detroit Public Schools, Ewa Makai Middle School,
Farmington Municipal School District, HOLA and Holbrook Unified School District, as
`glow/sf_partners.csv` spells them. A new partner of that kind needs the report's filter edited by
hand (a fresh retrieve, check-only, Ryan's go, deploy): one that reports monthly through
Salesforce, or whose clubs stop using Jotform (the Partners tab's `jotform` set to `no`, "Clubs
that do not use Jotform"). `Submissions_by_Club_and_Week` is unaffected: it shows only the clubs
with a batch in its window. The two delay reports keep every partner: they show a club only for
a month in which it submitted through Jotform.

**Not submitting last week** means no batch of any status whose session date
(`Attendance_Date__c`) is in last week, as the existing lists count it (DECISIONS 2026-10-06): a
blank or a refused duplicate counts as submitted, and the day a submission arrived plays no part.
The week runs Sunday to Saturday for en_US viewers and on the dashboard, which runs as Ryan:
`LAST_WEEK`, in the report's cross filter and in its SOQL check, is then the Sunday-to-Saturday
week before this one. `LAST_WEEK` follows the locale of the user who runs the report (a report
runs as its viewer), so a staff user whose locale starts the week on another day sees that
locale's week when opening the report by hand; the SOQL check follows the locale of whoever runs
it the same way. That week is a different thing from the session week `Session_Week__c` (the week of the month), which
only labels the matrix's columns. `LAST_WEEK` needs no new field, so the formula checkbox
`In_Last_Week__c` the ticket weighed is not built (DECISIONS 2026-10-24).

**The late report:** `Late_Submissions_Last_Month` has no cut-off: every live Jotform batch of
last month is in it with its delay, the largest delay first (Ryan, 2026-10-24; DECISIONS
2026-10-23: nothing is flagged, staff read the delays). It is grouped by partner, as the ticket's
outline has it, and the largest delay comes first only within each partner's group: the month's
largest delay heads its partner's group, which need not be the first. Ryan confirmed that reading
on the ticket on 2026-10-26 (the plan's Task #102 Rollout step 1); if it is ever changed to one list
across partners, the report becomes Tabular, sorted by the delay across every partner.

**Rollback** of the timing reports: the dashboard components that read them go first (task
#103); then the four reports are retired, never deleted (the archive rule, DECISIONS
2026-10-21): each is moved to Decommissioned and keeps its Id, by the Analytics API move
(`PATCH …/analytics/reports/<id>` with `reportMetadata.folderId`, as "Copying and moving reports
and dashboards" describes; `tools/sf_report_folders.py` refuses the Attendance folder as a
source) or by hand in Lightning, on Ryan's go, read back by SOQL on `Report`. A moved report
still uses the timing fields, and a report that uses a field blocks its deletion wherever the
report is, so the three moved reports on `Attendance_Totals` are edited next to drop the fields:
retrieve them fresh from Decommissioned; take `Session_Week__c` (the column grouping; the format
becomes Summary) out of `Submissions_by_Club_and_Week`, the `Submitted_At__c` and
`Submission_Delay_Days__c` columns and the sort on the delay out of
`Late_Submissions_Last_Month`, and the `Session_Month__c` grouping, the delay column and the
chart out of `Submission_Delay_by_Partner_by_Month`; check-only, Ryan's go, deploy.
`Clubs_Not_Submitting_Last_Week` (on Accounts) uses none of the fields and moves as it is; the
read-back `after/` keeps all four as deployed, to put one back from. Then the four columns come
off the report type `Attendance_Totals`: retrieve it fresh, delete the four `<columns>` entries
in that copy, check-only, Ryan's go, deploy. Never redeploy an older copy of `Attendance_Totals`
(DECISIONS 2026-10-16). The fields' own rollback (above) needs both
done first.

## Session notes in Salesforce

- **When:** a question about the session notes on a batch; a form's Salesforce integration
  changed or re-checked; the U.S form re-enabled; the monthly Salesforce checks.
- **Status:** the field is live since 2026-10-26 (deploy `0AfRP000002i7O10AI`, about 03:40
  UTC, Ryan's go); the template, Africa, Asia and Latin America map it since 2026-10-26 (Ryan,
  in the builder); the U.S form is DISABLED and not mapped. The proof (the first batches through
  a mapped form, a batch with a note counted) is pending
  ([plan](plans/2026-10-26-session-notes-salesforce.md), Result).
- **Dry run:** `python3 tools/integration_status.py` (read only).
- **Apply:** a mapping is a builder save per form (a live write, Ryan's go); the field was a
  metadata deploy (the plan's Rollout step 3).
- **Verify:** `python3 tools/integration_status.py --form <id>` → `ok (one action, 9 fields,
  Account_Name__c from q5, Session_Notes__c from q<N>, no upload)`.
- **Rollback:** below.
- **History:** [plan](plans/2026-10-26-session-notes-salesforce.md).

A mentor's note - the optional question named `sessionNotes` on every attendance form ("Session
notes on the attendance forms") - reaches Salesforce as `Attendance_Batch__c.Session_Notes__c`
("Session notes", Long Text Area of 32,768 characters; the form takes 1,000, so no insert is
refused for length), written by the forms' native integration when it creates the batch. Every
Salesforce user may read it (Ryan, 2026-10-26; DECISIONS 2026-10-26): System Administrator
reads and edits it (the integration's user) and the permission set `Attendance_Report_Viewer`
reads it. It is on the batch's page ("Attendance_Batch Layout", Information section, last) and
a column of the `Attendance_Totals` report type, not checked by default: add it to a report to
show it. The processor does not read it. A note is free text and can name girls: fine in
Salesforce, never in the repo, a log, a ticket or the conversation, so the tools count notes
and never print one.

**The mapping, per form** (the builder only: the API cannot write the integration).
`Session_Notes__c` ← the question named `sessionNotes`, whose qid differs per form:

| Form | id | `sessionNotes` | Mapped |
|---|---|---|---|
| template | 262352490535154 | q489 | 2026-10-26 |
| Africa | 262382821971058 | q476 | 2026-10-26 |
| Asia | 262383129464057 | q457 | 2026-10-26 |
| Latin America | 262383455778067 | q454 | 2026-10-26 |
| U.S | 262382706852058 | q446 | not mapped: DISABLED |

To map a form, in a quiet moment: `python3 backup_forms.py --form <id>`; in the builder,
Settings → Integrations → Salesforce → **edit** the action (create `Attendance_Batch`) → add a
row: Session notes (`Session_Notes__c`) ← "Additional information about this session
(optional)" → save, every other row as it is (never question 5's or question 18's), and **never
remove the connected account** (it detaches all ten forms, 2026-09-30); `python3
backup_forms.py --form <id>` again and the diff of the two properties snapshots → hunks inside
`integrations` only; then `python3 tools/integration_status.py --form <id>` → 9 fields.

**The audit.** `tools/integration_status.py` requires the mapping (`NOTES_MAPPING_WANTED`,
True since 2026-10-26): a live form without it is `NOT RIGHT` (exit 1), told its own
`sessionNotes` qid, and a mapping from any other question is `NOT RIGHT` on any form. A live
form whose `status` is exactly `DISABLED` needs none: unmapped, it reads `ok (one action, 8
fields, Account_Name__c from q5, Session_Notes__c not wanted (form DISABLED), no upload)`. Any
other status (`ENABLED`, none, `DELETED`, another spelling) is an enabled form's. The template
stays `NOT RIGHT` on its upload row until "Photos" step 1, whatever its notes.

**Re-enabling the U.S form** ("Disabling a regional form", the way back): map q446 in its
builder first, or with the re-enabling, before a mentor can submit; then `python3
tools/integration_status.py --form 262382706852058` → 9 fields, `Session_Notes__c from q446`.
Re-enabled and unmapped, it reads `NOT RIGHT`, and the notes typed until it is mapped stay in
Jotform only.

**Counting the notes** (read only, VPN off; the proof and the monthly checks). SOQL cannot
filter a long text field, so the query selects it and a local one-liner counts the non-blank
ones and prints the counts only, never a note:

```bash
sf data query -o glow --json -q "SELECT Session_Notes__c, Processing_Status__c FROM Attendance_Batch__c WHERE Creator__c = 'Jotform' AND CreatedDate >= 2026-10-26T05:40:00Z" \
  | python3 -c 'import json,sys,collections; r=json.load(sys.stdin)["result"]["records"]; print(len(r), "batches,", sum(1 for x in r if (x.get("Session_Notes__c") or "").strip()), "with a note,", dict(collections.Counter(x["Processing_Status__c"] for x in r)))'
```

**Rollback** ([plan](plans/2026-10-26-session-notes-salesforce.md#rollback)): unmap in the
builder, form by form (edit the action → remove the Session notes row → save; never remove the
connected account), and set `NOTES_MAPPING_WANTED = False` in the tool; the field may stay. The
field itself goes only on Ryan's word and only after every form is unmapped:
`NOTES_MAPPING_WANTED = False` first (so the audit does not demand the mapping), then `python3
tools/integration_status.py` → 8 fields on every live form but the template. Until "Photos"
step 1 the template prints only its upload row (`NOT RIGHT`, exit 1), mapped or not: confirm it
unmapped by its properties diff instead, `python3 backup_forms.py --form 262352490535154` before
and after its builder save, `diff` of the two `backups/262352490535154/properties-<stamp>.json`
→ the Session notes row (`Session_Notes__c`) gone inside `integrations`, nothing else changed.
A field deleted while a form still maps it (empty, because no note was typed yet, is not enough)
makes Salesforce refuse each insert from that form, and the whole batch is lost. Then the
layout, the permission set and the
report type from the deploy's `before/` while a fresh retrieve equals its `after/` (never an
older build, DECISIONS 2026-10-16), and the field by a destructive change
(`destructiveChanges.xml`, check-only first, Ryan's go). While it holds no data that loses
nothing; once a note has reached Salesforce, deleting the field deletes the notes, so it goes
only on Ryan's decision with the count of notes (above) in front of him.

## Monthly Report dashboards in Salesforce

- **When:** before any change to a Monthly Report (`DHIS2__c`) report or dashboard (epic #68), and to revert one.
- **Status:** inventoried read-only 2026-10-21 (#69); the two Decommissioned folders (below) exist since 2026-10-21, deployed on Ryan's go (deploy `0AfRP000002hjLh0AI`, check-only `0AfRP000002hisf0AA`), read back, hidden, with no share; the API proof 2026-10-21: a report is copied and moved by the Analytics API, a dashboard is cloned by it and moved or renamed by hand in Lightning (Ryan; the API refuses a dashboard `PATCH`, 400 `JSON_PARSER_ERROR`), proved 2026-10-23; the two proof copies stay in Decommissioned ([plan and Result](plans/2026-10-21-sf-reporting-inventory.md#result)); the items off the keep list moved to Decommissioned 2026-10-23 and 2026-10-24 on Ryan's go (#72, Decommissioned, below); the folders of the kept items, "GLOW Monthly Reports" and "GLOW Monthly Dashboards" (#73), deployed and filled 2026-10-24 on Ryan's go ([plan](plans/2026-10-23-sf-category-folders.md)); `DHIS2__c.Period__c` and its column in the `Dhis2` report type deployed 2026-10-24 on Ryan's go (#128; deploy `0AfRP000002i4l70AA`, check-only `0AfRP000002i4ht0AA`), read back, the before/after retrieve compare showing only those additions ([plan and Result](plans/2026-10-24-dhis2-period-date.md#result)); D3 and items 9-11 (#77) deployed 2026-10-25 on Ryan's go (deploy `0AfRP000002i5hB0AQ`, check-only `0AfRP000002i5dx0AA`) and read back; item 11's report redeployed 2026-10-26 on Ryan's go with its record count on (`co` 1; deploy `0AfRP000002i6yE0AQ`, check-only `0AfRP000002i7JB0AY`), read back equal to `build_item11/`, that day's refresh returning data on all three D3 components; the 5 "DHIS2 Reports" reports D3 no longer uses moved to Decommissioned 2026-10-26 ([plan and Result](plans/2026-10-24-sf-dash-observations.md#result); D1 "Glow Club Attendance" and its reports by Partner and Month (#75) deployed 2026-10-26 on Ryan's go (deploy `0AfRP000002i7HZ0AY`, check-only `0AfRP000002i7Fx0AI`), with item 1's column in the `Dhis2` report type, read back and checked against SOQL; the 5 reports it no longer uses moved to Decommissioned ([plan and Result](plans/2026-10-24-sf-dash-attendance.md#result); GLOW Club Attendance, below).
- **Dry run:** the check-only deploy (`--dry-run`); the inventory itself is reads (SOQL, the retrieve, the shares API).
- **Apply:** the same deploy without `--dry-run`, Ryan's go (VPN off); each non-GET Analytics API call (a copy, a move), Ryan's go.
- **Verify:** retrieve again and compare with the build; SOQL on `Report` or `Dashboard` shows the same Id after a move, with `FolderName` following.
- **Rollback:** the copy in Decommissioned and the `before/` retrieve (Decommissioned, below).

The Monthly Report is the object `DHIS2__c`: one record per partner per month (`Account__c` the
partner account, `YearMonth__c` like `202609`). The vendor built its reports and dashboards; the
inventory of 2026-10-21 (#69, [plan](plans/2026-10-21-sf-reporting-inventory.md#inventory)):
- The report folder "DHIS2 Reports" (`DHIS2Reports`) holds 63 reports.
- The dashboard folders "DHIS2 Dashboards" (`DHIS2Dashboards`) and "Dhis2 Dashbords" (sic,
  `Dhis2Dashbords`) hold 9 and 6 dashboards, 15 in all.
- The 15 dashboards have 64 components on 55 reports: 52 in "DHIS2 Reports" and 3 in "Public
  Reports". 11 of the 63 reports in "DHIS2 Reports" are used by no dashboard.
- Report types: `Dhis2` (65 reports) and `Monthly_Reports` (1), both on `DHIS2__c`.
- 11 of the 15 dashboards filter on `DHIS2__c$Account__c.Assigned_Partner_Manager__c`.
- 10 of the 15 dashboards are embedded in the Lightning page (FlexiPage)
  `Monthly_Report_Dashboards`, the tab `Monthly_Report_Dashbords` (sic) of the app "Monthly
  Report Dashboards".
- The three folders' shares (the shares API, 2026-10-21): "DHIS2 Reports" 6, "DHIS2 Dashboards"
  6, "Dhis2 Dashbords" 2, all to internal users or one Regular group; no guest, portal, community
  or partner share.
- Counted with `SELECT OwnerId, COUNT(Id) FROM Report GROUP BY OwnerId` (a report's `OwnerId` is
  its folder) and `SELECT FolderId, COUNT(Id) FROM Dashboard GROUP BY FolderId`; Salesforce
  refuses `GROUP BY FolderName`.

`data/sf_reporting_2026-10-21/` (owner only, never committed) holds the read-only retrieve
`before/` (66 reports, 15 dashboards, the 3 folders, 2 report types, the FlexiPage, 2 tabs, 1 app
and the interactive dashboard's code) and `evidence/inventory.csv`, one row per report and
dashboard: its folder, report type, format, created, last modified, last run, last viewed, and
the dashboards and components that use it. The retrieved XML carries staff names (shares,
running users, filter values): never quote it.

The "Jotform Attendance" dashboard and the two Attendance folders are another set ("Attendance
dashboard in Salesforce"); epic #68 leaves them untouched. A change here follows the epic's
ritual: VPN off, retrieve live into `data/sf_<topic>_<date>/before/`, build in a copy,
check-only, Ryan's go, deploy, retrieve `after/` and compare; never an older build (DECISIONS
2026-10-16).

A dashboard component's measure must be one of its report's aggregates, as the Analytics describe
lists them (`GET /analytics/reports/<id>/describe`, its `aggregates`). A report offers `RowCount`
only when its record count is on (the report param `co` 1, describe `hasRecordCount: true`),
whatever columns it summarizes: item 10's report sums `GC_sessions_did_you_observe_last_month__c`
with `co` 1 and lists the Sum and `RowCount` together. On 2026-10-25 item 11's report (#77) had
its record count off (`co` 0, describe `hasRecordCount: false`) and listed only its Sum, so its
component, which measures `RowCount`, failed the refresh with 406 ("One or more of the fields
selected in the component is no longer available in the report"). The check-only deploy passes
such a component; only the refresh shows the 406.

### Decommissioned

Two folders, both labelled "Decommissioned", hold what epic #68 retires and the copies it keeps
(DECISIONS 2026-10-21). Built in `data/sf_reporting_2026-10-21/folders/`; deployed on Ryan's go
2026-10-21 (deploy `0AfRP000002hjLh0AI`, check-only `0AfRP000002hisf0AA`); read back into
`after/`, identical to the build.
- The report folder "Decommissioned" (`ReportFolder` `Decommissioned`, `00lRP000007iOiXYAU`) is
  hidden, with no `folderShares`: only administrators see it.
- The dashboard folder "Decommissioned" (`DashboardFolder` `Decommissioned_Dashboards`,
  `00lRP000007iOiYYAU`) is hidden, with no `folderShares`: only administrators see it.
- The measure is the shares API (`GET /services/data/v67.0/folders/<id>/shares`): on 2026-10-21
  it showed no share on either folder, not even a Manage entry for the deploying administrator.
- An entry for anyone (a group, a role, guest, portal, community or partner users, All Internal
  Users) is a failure, removed before anything more is moved in.
- The two proof copies of #69 stay there (Ryan, 2026-10-23): the report `00ORP000009igCr2AI`
  "proof #69 Club meet freq (moved)" and the dashboard `01ZRP00000BNDJB2A5` "proof #69 DHIS2
  dashboard". The dashboard copy has no description: the API refused it and it was not set by
  hand; Ryan said 2026-10-23 to leave the copies as they are.

The archive rule:
- A retired report or dashboard is moved to Decommissioned and keeps its Id; nothing is deleted
  in this epic.
- Before a report or dashboard changes, a copy of it as it was goes to Decommissioned, carrying
  its source Id and the ticket in its description, in addition to the `before/` retrieve.
- The copy's label stays within 40 characters, Salesforce's limit on a report's name.
- A dynamic dashboard's copy (the original runs as the logged-in user) runs as a specified user,
  the administrator who makes the copy: dynamic dashboards count against an org limit, and the
  `before/` retrieve keeps the original's running-user setting.
- The `before/` retrieve is what a metadata redeploy starts from; the copy is what a Salesforce
  user opens.
- To revert from Salesforce, open the copy in Decommissioned, then Save As into the original
  folder or move it back there. Save As makes a new Id; a move keeps the copy's Id.
- A dynamic dashboard put back from its copy has "View dashboard as" reset to the dashboard
  viewer (`LoggedInUser`) before it returns to its original folder; the `before/` retrieve's
  running-user setting is the check.
- How a copy and a move are made ([plan, API proof](plans/2026-10-21-sf-reporting-inventory.md#api-proof)):
  a report is copied and moved by the Analytics API (`POST …/analytics/reports?cloneId=<id>`,
  then `PATCH …/analytics/reports/<id>` with `reportMetadata.folderId`), and keeps its Id.
- A dashboard is copied by the Analytics API (`POST …/analytics/dashboards?cloneId=<id>` with
  `folderId`). The API refuses to rename, describe or move a dashboard (`PATCH` returns 400
  `JSON_PARSER_ERROR`), so Ryan does it by hand in Lightning: in the dashboard's Properties
  (Name, Description, Folder) he sets the name and the description `copy of <source id>,
  #<ticket>`, and moves it with its Move action; the Id stays the same, checked with SOQL.

The retirement (#72, [plan and Result](plans/2026-10-23-sf-retire-reports.md#result)):
- On 2026-10-23 and 2026-10-24, on Ryan's go, #72 moved 29 reports and 10 dashboards to
  Decommissioned, each with its Id unchanged.
- 27 of the 29 came from "DHIS2 Reports"; 2 reports moved from "Public Reports"
  (`00ORP000006XSy92AG`, `00ORP000006V09x2AC`, Ryan's decision of 2026-10-23), because only
  retiring dashboards used them.
- 19 retiring reports stay in "DHIS2 Reports", held for #75-#79 because the 5 kept dashboards
  use them; each moves when its dashboard is reworked (#75 moved D1's four on 2026-10-26).
- The ledger `data/sf_retire_2026-10-23/ledger.csv` has 31 move rows for the 29 reports: two
  reports have a second row, Decommissioned to Decommissioned, which changed nothing. Each is the
  first PATCH of a plan's full `--apply` run, which moved that plan's first report again after
  `--limit 1` had moved it; the undo, newest first, still ends with the report back in its old
  folder. The ledger is owner only and never committed.
- The 10 dashboards moved by hand in Lightning, so they are in no ledger;
  `data/sf_retire_2026-10-23/dashboards_by_hand.csv` lists each with its old folder.
- To bring a report back: the undo's dry run lists every move of the ledger, newest first, with
  the folder each report goes back to:
  `python3 tools/sf_report_folders.py undo --vpn-off --dir data/sf_retire_2026-10-23`.
  On Ryan's go, `python3 tools/sf_report_folders.py undo --vpn-off --dir data/sf_retire_2026-10-23 --apply`
  puts each back and reads it back (`--limit N` undoes the last N moves only).
- The undo puts the two "Public Reports" reports back first (their rows are the newest) by a PATCH
  with `folderId` the organization's id, not yet proven in the org. If Salesforce refuses it, the
  run stops there: Ryan moves the two back by hand in Lightning, an undo row with status `ok` is
  added to the ledger for each, and the undo then goes on with the other 27 reports
  ([plan, Rollback](plans/2026-10-23-sf-retire-reports.md#rollback)).
- To bring a dashboard back: Ryan moves it back by hand in Lightning (its Move action) to its old
  folder, "DHIS2 Dashboards" or "Dhis2 Dashbords", and SOQL shows the same Id. One that the
  FlexiPage `Monthly_Report_Dashboards` embedded gets its component back from
  `data/sf_flexipage_2026-10-23/before/` by the ritual above (check-only, Ryan's go, deploy).

### The keep list

`glow/sf_keep_list.csv` is GLOW's keep list (the GLOW team via Ryan, 2026-10-21) mapped to what
is in the org today, as Ryan agreed it on ticket #70 (2026-10-23; DECISIONS 2026-10-23). The
list has 19 items: 18 reports in five groups, and one table. The file has a row for each item and
for each of the five dashboards, with the header `item,group,measure,kind,id,label_today,label_target`:
GLOW's measure verbatim, the kind (`report`, `table` or `dashboard`), the 18-character Id of the
report or dashboard the item is today, and its label. It holds report and dashboard Ids and names
only, never record data. Tasks #71 to #73 build their move plans from it.

The five groups are the five Monthly Report dashboards (D1 to D5 in the file), each mapped to the
dashboard that becomes it:
- D1, the GLOW Club Attendance dashboard: "Glow Club Attendance" (`01ZRP000006iWqL2AU`), items 1-4.
- D2, the GLOW Club Implementation dashboard: "Implementation Dashboard" (`01ZRP000006jU9o2AE`),
  items 5-8.
- D3, the GLOW Club Observations dashboard: the dashboard named "GLOW Club Training" today
  (`01ZRP000006k2D32AI`), items 9-11. Five of its nine components are observations, and no
  dashboard today is about observations alone.
- D4, the GLOW Club Training dashboard: "Mentors" (`01ZRP000006quAj2AI`), items 12-16. The group
  "GLOW Club Training" is this dashboard, D4, and the dashboard named "GLOW Club Training" is D3:
  the file's Ids tell them apart.
- D5, the GLOW Club Reporting dashboard: "Reporting" (`01ZRP000006oxSr2AI`), items 17 and 18.

Item 2 is retired (Ryan, 2026-10-23 on #74): it has no source, and #75 moves its report to
Decommissioned, kept there; #73 leaves item 2's report in its folder, for #75 to move.

Item 19, "GLOW of the Month Stories" (group "Report/Data Table Format"), is the report "GLOW of the
Month Stories Report" (`00ORP000005p2L32AI`), the org's label since 2026-10-21, which the file
follows (Ryan, 2026-10-23). It is the table: a tabular report on no
dashboard, and it stays tabular, not grouped (below). Item 12, "New mentors recruited", is the report #80
deployed on 2026-10-26, "Partners that recruited new mentors" (`00ORP000009kXev2AE`, `### GLOW Club
Training`), and the file carries its Id. Item 18, "Report submitted on time", maps to "Reports
completed on time" (`00ORP0000054DyH2AU`), which lists submission and modified dates; no report
computes "on time" today, and that computation is a later task, on hold (#119).

Every kept report and dashboard is by Partner and Month (Ryan, 2026-10-21: "This data should be
displayed by the Partner and Month."): the 18 reports of the five dashboards are grouped by the
partner (`DHIS2__c.Account__c`) and the month. Item 19, the table, is the one exception to the
grouping: it stays a tabular report, not grouped, with Partner and Month as its columns and
filters. Tasks #75 to #79 bring each dashboard and its reports to that, with current data; #79
("Fix GLOW Club Reporting and the GLOW of the Month table") does item 19 too.

Kept reports and dashboards keep their current names (Ryan, 2026-10-23): in every row
`label_target` is `label_today`, abbreviations and spelling as they are in the org, and D1 to D5
keep the dashboard names listed above. Item 12's `label_today` and `label_target` are the label
of the report #80 deployed, "Partners that recruited new mentors" (Ryan, 2026-10-26). GLOW's
review of 2026-11-02 (epic #194) supersedes that for items 5-7 only: since #197 their
`label_target` is GLOW's name within 40 characters, live in the org, and `label_today` stays the
label #70 recorded (RUNBOOK "GLOW Club Implementation").

Every report and dashboard not on the keep list goes to Decommissioned and is kept there, in case
a pick changes later (Ryan, 2026-10-23). The scope is the Monthly Report's three folders, which
task #72 moves: every report in "DHIS2 Reports" and every dashboard in "DHIS2 Dashboards" and
"Dhis2 Dashbords" whose Id is not in the file; the archive rule above holds for each move. Two
reports outside those folders are on one of their 15 dashboards today and not in the file, both in
"Public Reports": "Pending Approvals monthly report" (`00ORP000006XSy92AG`) and "New Monthly
Reports by account" (`00ORP000006V09x2AC`); the third "Public Reports" report on a dashboard is
item 17, kept. Those two sit outside #72's folders, and Ryan decides on #72 whether they move. The
two Attendance folders and the "Jotform Attendance" dashboard
are outside the scope: epic #68 leaves them untouched.

Test records are Monthly Reports filed on a test account or on no account. The test-record rule
is one report filter on existing fields, applied to every kept report:
`Account is not blank AND Account: Account Name does not contain "test"` (Ryan, 2026-10-23). On
the count of 2026-10-23 it excludes the five Monthly Reports of the two test accounts and the six
with a blank Account, and no real partner's. `Partner_Status__c` is not the rule: it is blank on
four real partners with 23 Monthly Reports, the same as on the test accounts. Tasks #75 to #79
add the filter as they fix each dashboard, and #79 adds it to item 19, the table, too. The filter
matches a substring: a partner whose account name contains "test" (a "Contest" or "Protestant"
partner, say) would drop out of every kept report, so a new partner's account name (its line in
`glow/sf_partners.csv`, RUNBOOK "Club accounts in Salesforce") is checked against the filter
when the partner is added.

### The five dashboards and their folders

The kept reports and dashboards (`glow/sf_keep_list.csv`) go into two new folders, one for
reports and one for dashboards (Ryan, 2026-10-21; ticket #73,
[plan](plans/2026-10-23-sf-category-folders.md)): the report folder "GLOW Monthly Reports" holds
every kept report, the table included, and the dashboard folder "GLOW Monthly Dashboards" holds
the five dashboards. The five groups are categories, the rows of this table:

| Group | Dashboard label | Dashboard folder | Report folder | Report count |
|---|---|---|---|---|
| GLOW Club Attendance | "Glow Club Attendance" (`01ZRP000006iWqL2AU`) | GLOW Monthly Dashboards | GLOW Monthly Reports | 4 |
| GLOW Club Implementation | "Implementation Dashboard" (`01ZRP000006jU9o2AE`) | GLOW Monthly Dashboards | GLOW Monthly Reports | 4 |
| GLOW Club Observations | "GLOW Club Training" (`01ZRP000006k2D32AI`) | GLOW Monthly Dashboards | GLOW Monthly Reports | 3 |
| GLOW Club Training | "Mentors" (`01ZRP000006quAj2AI`) | GLOW Monthly Dashboards | GLOW Monthly Reports | 5 |
| GLOW Club Reporting | "Reporting" (`01ZRP000006oxSr2AI`) | GLOW Monthly Dashboards | GLOW Monthly Reports | 2 |
| Report/Data Table Format | — (item 19, the table "GLOW of the Month Stories Report", on no dashboard) | — | GLOW Monthly Reports | 1 |

- The counts are GLOW's list: 18 reports in five dashboards and the table. Item 12 ("New mentors
  recruited", GLOW Club Training) is the report #80 deployed into "GLOW Monthly Reports" on
  2026-10-26. The report folder holds all 19 kept reports: 18 of the five dashboards and item 19.
- The report folder is the `ReportFolder` `GLOW_Monthly_Reports` and the dashboard folder the
  `DashboardFolder` `GLOW_Monthly_Dashboards`, both new, built in
  `data/sf_folders_2026-10-23/build/` from a retrieve of the three DHIS2 folders.
- The kept reports and dashboards keep their current labels (Ryan, 2026-10-23): the labels in this
  table and in `glow/sf_keep_list.csv` are the ones in the org.

Shares:
- Both new folders get the same shares, since a dashboard's viewers need its reports' folder: the
  union of the shares of "DHIS2 Reports", "DHIS2 Dashboards" and "Dhis2 Dashbords", copied into
  the build.
- That union is 7 entries: 4 internal users with View, 2 internal users with Manage and 1 group
  with Manage.
- The new folders are shared with internal users and groups only. Never a guest, portal,
  community or partner share.
- The shares are checked through the shares API (`GET /services/data/v67.0/folders/<id>/shares`)
  on both new folders after the deploy; an entry of any other kind is removed before anything
  moves in.

The moves:
- The reports move by `tools/sf_report_folders.py move` (above) to "GLOW Monthly Reports": from
  "DHIS2 Reports", and item 17 from "Public Reports". Each keeps its Id.
- The five dashboards are moved by hand in Lightning by Ryan into "GLOW Monthly Dashboards" (the
  API refuses a dashboard `PATCH`). Each keeps its Id, checked with SOQL on `Dashboard`.
- Before each move, a copy of the report or dashboard as it was goes to Decommissioned (the
  archive rule above, `copy --tag "#73"`). The 3 dynamic dashboards (Glow Club Attendance,
  Implementation Dashboard, Reporting) have no copy: the clone was refused at the org's limit of
  5 dynamic dashboards (2026-10-24), so their rollback is the metadata retrieve in the plan's
  `before/`.
- The three DHIS2 folders stay; #72 moves what is left in them to Decommissioned.

### Copying and moving reports and dashboards

`tools/sf_report_folders.py` (ticket #71) makes the copies and the moves of the archive rule
above through the Analytics API, exactly as the API proof sent them. It never deletes, and it
reads `Folder`, `Report`, `Dashboard`, `DashboardComponent` and a report's describe only, never a record. Every
subcommand needs `--vpn-off`; `copy`, `move`, `undo` and `restore-descriptions` are dry runs
until `--apply` (Ryan's go, the live gate asks him). The folders named "Attendance" are never a source or a target.

- List what a folder holds (read-only; CSV on stdout, the counts on stderr, which must equal SOQL's
  `SELECT OwnerId, COUNT(Id) FROM Report GROUP BY OwnerId` for that folder):
  `python3 tools/sf_report_folders.py list --vpn-off --folder "DHIS2 Reports" [--folder "Dhis2 Dashbords"] [--kind report|dashboard]`.
  The `used_by` column lists the dashboards with a component on each report.
- Copy one report or dashboard into Decommissioned before it changes:
  `python3 tools/sf_report_folders.py copy --vpn-off --kind report --id <id> --tag "#72"`, read
  the line it prints, then the same with `--apply`. A report's copy keeps its label (cut to 40
  characters) and gets the description `copy of <id>, <tag>` by a PATCH of the copy once the
  clone reads back in Decommissioned (the API proof's steps); a refused PATCH stops with the copy's
  id in its `failed` ledger row. A dashboard's copy keeps its title
  and has no description (the API refuses both): set them by hand in Lightning if wanted.
- Move (and relabel) reports by a plan, a CSV with the columns `kind,id,to_folder,new_label`
  (`to_folder` a folder name, exactly one report folder of that name; a blank `new_label` keeps
  the label; a label is at most 40 characters, and a report whose current label is longer moves
  only with its label kept, since undo could not put that label back):
  `python3 tools/sf_report_folders.py move --vpn-off --plan <plan.csv>` (the dry run: one line per
  row with the current label and folder and the change), then `--apply --limit 1` first, check
  that report in Salesforce, then `--apply` for the rest. The whole plan is checked before the
  first write: a report that a dashboard outside Decommissioned still uses is refused a move to
  Decommissioned. Each move keeps the report's Id and is read back by SOQL; a read-back that
  differs stops the run. Each move's (and undo's) `PATCH` carries the description the report's
  describe (`GET analytics/reports/<id>/describe`) answers just before it, since Salesforce blanks
  a description the `PATCH` leaves out (#142: 32 reports lost theirs); a describe that does not
  answer it stops the run before that report's `PATCH`. The read-back checks the description too
  (`None` and `""` are the same blank): one that does not read back as sent stops the run there.
- Dashboards are moved and renamed by hand in Lightning (the API proof: Salesforce refuses every
  dashboard `PATCH`, 400 `JSON_PARSER_ERROR`); a plan row of kind `dashboard` is refused. Check
  the hand move with SOQL on `Dashboard` (the same Id, `FolderName` following).
- The ledger `data/sf_report_folders/ledger.csv` (owner only, never committed) holds one row per
  write: the item, its folder and label before and after, a copy's id and tag, the status and the
  HTTP code. The row is on disk as `sending` before the request and rewritten in place as `ok` or
  `failed`; a row left `sending` (the run died) has an unknown outcome, and undo puts that move back.
- Undo: `python3 tools/sf_report_folders.py undo --vpn-off --ledger data/sf_report_folders/ledger.csv`
  (the dry run), then with `--apply` (`--limit N` undoes the last N only). It puts each move back
  to its old folder and label, last first, and adds an `undo` row for each; a move Salesforce
  refused (HTTP 4xx) never moved and is left as it is, and a move already undone is not undone
  again. Copies stay in
  Decommissioned.
- Restore the descriptions the moves blanked (#142, Ryan's decision 2026-10-25: the kept reports
  only, stray leading bullets stripped), from local metadata retrieves (sfdx project dirs, the
  report files under `force-app/main/default/reports/<folder>/<DeveloperName>.report-meta.xml`):
  `python3 tools/sf_report_folders.py restore-descriptions --vpn-off --expect 12 --from <retrieve dir> [--from <another>]`
  (the dry run: one line per planned report with its id, label and folder, the names no report has,
  and the counts planned, already described, decommissioned, protected, not found; never a text).
  `--expect 12` is the agreed set, the 12 kept reports of #73 (its moves' ledgers are gone): a
  planned count (the whole plan, before `--limit`) other than `--expect` is refused, the dry run
  too, and nothing is written - stop and look when the dry run's count differs. Then
  `--apply --limit 1 --expect 12`, check that report in Salesforce, then `--apply --expect 11` for
  the rest (the plan is what is left). Each saved
  `<description>` is unescaped, stripped of leading bullets (`●•*-`) and whitespace and of trailing
  whitespace; an empty one is ignored. Only a report whose description is blank now and that is not
  in Decommissioned gets one; one in "Attendance" is left as it is (counted as protected). Refused before any write: a `--from`
  dir that is missing or holds no report file, two different texts for one developer name, a name
  two reports have, a text over 255 characters, a planned report whose label is over 40 characters
  (the `PATCH` sends the label and folder it has now with the description). Each `PATCH` has a
  `describe` ledger row and is read back by SOQL, the description included; one that does not read
  back stops the run. Undo ignores `describe` rows; a second run finds the restored reports
  "already described".

### Why the dashboards showed old data

Read-only diagnosis, 2026-10-23 (#74). A fresh retrieve of D1-D5, the 18 kept reports that exist
(items 1-19 but 12), the report types `Dhis2` and `Monthly_Reports`, `DHIS2__c` and the form
(LWC `dHIS2Forms`, Apex `dHIS2Controller`) is in `data/sf_stale_2026-10-23/before/`; each report
was run by the Analytics API (a GET) and the runs, the SOQL counts and their summaries are in
`data/sf_stale_2026-10-23/evidence/`. The month compared is September 2026, the last complete
month: 42 Monthly Reports from 42 partners, none on a test account or a blank Account.

The cause: every kept report filters on a fixed year, and groups by the month's name alone.
- 14 of the 18 filter `Year__c equals 2025`; items 4 and 19 filter `Year__c equals 2026` (current
  today, old again in January 2027); items 17 and 18 have no year filter and add September 2025
  and September 2026 into one "September". Every other report on the five dashboards filters
  `Year__c equals 2025` too, except "Participation by month" (2026).
- The month is `Month__c`, a picklist of month names; `Year__c` is a number. `YearMonth__c` (a
  number formula, `202609`) is not in the `Dhis2` report type's layout, so no report offers it;
  since #128 the type offers `Period__c` (below).
- The standard date filter of every report is `CreatedDate`, all time: it narrows nothing.

Three of the form's fields have been blank since October 2025, when the form moved to the record
type `Monthly_reports_new` (every record from `202510` on has it; 470 older ones have none):
`collect_last_month_s_attendance__c` (item 1), `Submit__c` (item 2) and
`Select_all_GLOW_Club_modules_implemented__c` (item 6, through its 18 module formula fields such
as `GLOW_Create_Year_1_Relationships_101__c`). All three are blank on the 425 records of 2026; the
form no longer asks those questions. The form's change of 2026-09-23 (`dHIS2Controller` and
`dHIS2Forms` last modified in the org 2026-09-30) added the checkbox
`Attendance_submitted_electronically__c`, first set on the September 2026 reports (21 of 42
ticked), and stopped no field a kept report reads: the others are filled on 26 to 42 of the 42.

Not causes: no kept report filters on a record type (`DHIS2__c` has one, `Monthly_reports_new`);
the `Dhis2` report type's inner join to Duplicate Record Items drops no record (item 18 returns
all 1,051 Monthly Reports, item 1 all 619 of 2025; `DHIS2__c` has 0 duplicate record items); the
formula `Monthly_Total__c` (the largest week total) is current (item 4). The dashboards' running
user is active (another administrator). D1, D2 and D5 run as the viewer (`LoggedInUser`) and are
live; D3 and D4 run as that specified user and show the snapshot of their last refresh,
2026-07-10 (D3) and 2026-08-13 (D4), and no refresh of them is scheduled (`CronTrigger` has no
dashboard-refresh job; the org's one report subscription, weekly since 2026-10-02, is tied to no
dashboard here by the API). The ticked count, the running user, the scheduled jobs and the
dynamic dashboards: `evidence/soql_2026-10-23_review.txt`.

Components more than one dashboard shares:
- The period design (a fixed year, a month name with no year) is in every report of all five.
  Each dashboard ticket fixes its own reports the same way (below). GLOW's period is the last 12
  months (Ryan, 2026-10-23), which needed one shared change first: #128 added the date field
  `DHIS2__c.Period__c` for the report's month, and the `Dhis2` report type's column for it
  (2026-10-24, below), before #75-#79.
- The org's limit on dynamic dashboards: Enterprise Edition, 5 dashboards that run as the viewer,
  all 5 in use (D1, D2, D5, "Attendance According to Attendance Rosters" `01ZRP000006s43B2AQ`,
  which #72 moves to Decommissioned, and "Activities Dashboard", outside the epic). D3 and D4
  therefore stay on a specified user and are kept fresh by a scheduled refresh.
- Item 16 ("Meeting with mentors to discuss program", `00ORP000004RJZ72AO`), a D4 report, is a
  component of D3, not of D4. #77 takes that component off D3 and #78 puts item 16 on D4; until
  #77 is done, #78's change to item 16 (its period and grouping) changes D3's component too.
  No other kept report is on a dashboard other than its own.
- Item 6 on D2 and the report type `Attendance_Totals`, which the Attendance-folder reports share
  (they stay as they are). The type carries the club's parent's name, not the partner's
  `Assigned_Partner_Manager__c` ([plan](plans/2026-10-06-attendance-totals.md) D.1), so D2's
  filter on it does not apply to item 6 until that field is reachable from the type (e.g. a
  lookup through the club's parent added to `Attendance_Totals`, deployed only from a fresh
  retrieve, the Attendance reports unchanged). #76 settles it before building item 6; named on
  #74.

`DHIS2__c.Period__c` (#128), deployed 2026-10-24 on Ryan's go: label "Period", a Date formula,
the first day of the report's month, built from `Year__c` and `Month__c` the same way
`YearMonth__c` is (a formula on `YearMonth__c` itself compiled to 18,865 characters, over the
15,000 limit, because `YearMonth__c` is a large formula). Blank when `Year__c` is blank or the
month is not a month name. Read-only for the two profiles that read `YearMonth__c` (System
Administrator, GLOW Standard User), and a column of the `Dhis2` report type (section "DHIS2S",
beside `Year__c`). The before/after retrieve compare shows only those additions (the field, two
read permissions, one report-type column): `data/sf_period_2026-10-24/`. The check, 2026-10-24
(window 2025-10-01 to 2026-09-30): `SELECT COUNT(Id) FROM DHIS2__c WHERE Period__c =
LAST_N_MONTHS:12` = 569, and `... WHERE YearMonth__c >= 202510 AND YearMonth__c <= 202609` =
569; an unsaved report (Analytics API `reports/query`, saves nothing) on `Dhis2` with
`Period__c` as its date column and that filter returned 569 rows. Of 1,051 Monthly Reports, 6
have no `Year__c`: `Period__c` is blank on them and `YearMonth__c` (blanks as zero) gives the
bare month number (1 to 11), so neither count includes them. Two of the six (October and
November, created 2025-11-28 and 2025-12-17) probably belong to the window and show only once an
administrator fills in their year (not #128). Rollback: only once no report filters on
`Period__c` (the dashboard tickets will), a destructive change of the field and the report
type's column, each from a fresh retrieve (DECISIONS 2026-10-16). Plan, rollout and Result: [plan](plans/2026-10-24-dhis2-period-date.md).

The fix, for each kept report, after its copy goes to Decommissioned (#75 D1, #76 D2, #77 D3,
#78 D4, #79 D5 and item 19; item 6 takes its own steps 1-3, below):
1. Replace `Year__c equals <year>` with GLOW's period: the last 12 months, which leaves out the
   current, incomplete month. Lightning's standard date filter has no "last 12 months" (its
   month options are last, this and next month), so the report gets the field filter
   `Period__c equals LAST_N_MONTHS:12` (shown as "LAST 12 MONTHS"), and its standard date
   filter's column is set to `Period__c`, range All Time (Custom, no dates), in place of
   `CreatedDate`.
2. Group by the partner (`DHIS2__c.Account__c`), then by `Period__c` by calendar month.
   The `Account__c.Owner` or `Account_Owner_Check__c` grouping goes; the dashboards'
   filter on `Assigned_Partner_Manager__c` stays. Item 19 stays tabular, with the filter only.
3. Add the test-record rule (above).
4. Put the kept reports on their dashboard: today D1 shows items 2 and 3 (and a copy of item 1's
   report, not item 1), D2 items 6-8, D3 items 9-11 and 16 (above), D4 none of items 13-16, D5
   neither 17 nor 18; the dashboards' other components are on reports #72 moves to
   Decommissioned.
5. D3 and D4: a refresh after the fix (a PUT, Ryan's go), and a weekly refresh by a dashboard
   subscription in Lightning.

Item 6 is the exception to steps 1-3 (Ryan, 2026-10-23 on #74: it counts the Jotform batches'
`Module__c`). Its source is `Attendance_Batch__c`, not `DHIS2__c`, so #76 builds it on the batch
report type `Attendance_Totals` (base `Attendance_Batch__c`, with `Module__c`,
`Attendance_Date__c`, `Creator__c`, `Processing_Status__c` and the club's parent; "Attendance
dashboard in Salesforce", [plan](plans/2026-10-06-attendance-totals.md) D.1):
1. Filters: `Processing_Status__c` equals `Success` and `Creator__c` starts with `Jotform`, as
   the girls tiles' filters 1 and 2, so a `Failed` "Duplicate" batch and a `Partner report`
   batch never count.
2. Period: `Attendance_Date__c` `LAST_N_MONTHS:12`, the session date (`Period__c` is on
   `DHIS2__c` only).
3. Grouping: the partner, which is the club's parent account
   (`Attendance_Batch__c$Account__c.Parent`, the column the Partner filter uses), then
   `Attendance_Date__c` by calendar month, then `Module__c`; the measure is the record count,
   one batch per club and session date.
- Test records: the RUNBOOK has no batch-side rule. The 11 February 2026 pilot batches are
  `Creator__c` "Jotform" and `Success` (plan, Context), so they pass filters 1 and 2, fall inside
  `LAST_N_MONTHS:12` until February 2027 and would show as a February 2026 bar. The Jotform
  Attendance reports leave them out only by their window, `Attendance_Date__c` since 2026-09-01
  (the `Creator__c` filter keeps the March pilot's per-girl rows out, "Access", not these
  batches). Whether item 6 leaves them out (e.g. the same `Attendance_Date__c` floor of
  2026-09-01) and takes the test-record rule on the parent account, #76 decides.
- Whether item 6's report is rebuilt or a new report takes its place (the Id in
  `glow/sf_keep_list.csv`), #76 decides; D2's `Assigned_Partner_Manager__c` filter does not
  reach it yet (Components more than one dashboard shares, above). The copy to Decommissioned
  comes first either way.

| Item | Report | Year filter | The report's "September" | SOQL, September 2026 | Cause and fix |
|---|---|---|---|---|---|
| 1 | Collection of Attendance Roster by Month | 2025 | 52 records (September 2025) | 42 records, 0 with the field | Year; field blank since 2025-10: counts `Attendance_submitted_electronically__c` instead (21 of 42; #75) |
| 2 | Attendance Roster Uploaded on DR by M&P | 2025, `Submit__c` set | 46 (2025); no month after September 2025 | 0 of 42 | Field blank since 2025-10, no source: retired from D1, its report to Decommissioned, kept (#75) |
| 3 | Participation by Month and Partner | 2025 | sum 5,225 (SOQL, September 2025: 5,225) | sum 4,779 over 42 | Year: steps 1-4 |
| 4 | GLOW Club Each Week | 2026 | sum 4,779 over 36 | 4,779 over 36 (total not 0) | Current; fixed year: steps 1-4, onto D1 |
| 5 | Copy of GLOW Club Implementation by M&P | 2025 | 50 | 41 answered (39 Yes, 2 No) | Year: steps 1-4, onto D2 |
| 6 | Glow Club Modules Implemented by M&P | 2025 | 95 module ticks on 52; 0 in October-December 2025 | 0 of 42 | Year; field blank since 2025-10: counts the Jotform batches' `Module__c` instead, on `Attendance_Totals`, by partner, month and module (#76; item 6's steps 1-3, above) |
| 7 | GLOW Club Modules Adapted By Month | 2025 | 51 | 42 (29 Yes, 13 No) | Year: steps 1-4 |
| 8 | Local and Regional Summits By Month 2 | 2025 | 47 | 38 (5 summits, 33 none) | Year: steps 1-4 |
| 9 | Submission of GC observation forms M & P | 2025 | 52 | 26 (23 Yes, 3 No) | Year: steps 1-4 |
| 10 | Total Number of Club Observations M&P | 2025 | sum 93 over 50 | sum 93 over 42 (the same sum by chance) | Year: steps 1-4 |
| 11 | Completed Observing Clubs Alteast Once P | 2025 | sum 93; total 1,215 = all of 2025 | 27 partners observed (sum 93); January-September 796 | Year: steps 1-4 |
| 13 | Number of mentors trained about module | 2025, month a column | total 1,676 = all of 2025 | 152 (September 2025: 107) | Year; month a column: steps 1-4 |
| 14 | Number of training sessions led | 2025, month a column | total 791 = all of 2025 | 27 | Year; month a column: steps 1-4 |
| 15 | Leading training sessions with mentors | 2025, month a column | 619 records = all of 2025 | 41 answered (19 Yes, 22 No) | Year; month a column: steps 1-4 |
| 16 | Meeting with mentors to discuss program | 2025 | 52 | 41 (37 Yes, 4 No) | Year: steps 1-4 |
| 17 | Approved Approvals monthly report | none | 58 = 44 (2025) + 14 (2026) | 14 of 42 approved | Two years in one month, by owner: steps 1-4 |
| 18 | Reports completed on time | none | 94 = 52 (2025) + 42 (2026) | 42 | Two years in one month: steps 1-4 |
| 19 | GLOW of the Month Stories Report | 2026 | 42 | 42 | Current; fixed year: steps 1 and 3 (#79) |

Item 19's label in the org is "GLOW of the Month Stories Report" since 2026-10-21 (changed by
another administrator); `glow/sf_keep_list.csv` follows the org's label (Ryan, 2026-10-23), with
no rename in Salesforce.

The check that a fix worked: the report's cell for 2026 and September equals a query on
`DHIS2__c` with
`WHERE Year__c = 2026 AND Month__c = 'September' AND Account__c != null AND (NOT Account__r.Name LIKE '%test%')`
and, per item:
- A number: `SELECT COUNT(Id), SUM(<field>)` with `AND <field> != null`. Items 3 and 4
  `Monthly_Total__c` (item 4 also `AND Monthly_Total__c != 0`), 10
  `GC_sessions_did_you_observe_last_month__c`, 11 the same field with `> 0` in place of `!= null`
  (the partners who observed), 13 `Mentors_attended_the_training_sessions__c`, 14
  `how_many_training_sessions_did_you_lead__c`.
- A picklist (SUM is not valid on one): `SELECT <field>, COUNT(Id)` with `AND <field> != null
  GROUP BY <field>`. Items 5 `Did_you_implement_GLOW_Club_last_month_f__c`, 7
  `Adapted_to_the_local_culture_or_context__c`, 8 `Select_summits_completed_last_month__c`, 9
  `did_you_submit_your_GC_observation_form__c`, 15 `Lead_any_training_sessions__c`, 16
  `Did_you_meet_with_mentors_as_a_group__c`.
- Items 1 and 17-19: `SELECT COUNT(Id)`, for item 1 with
  `AND Attendance_submitted_electronically__c = true` (a checkbox; 21 for September 2026), for
  item 17 with `AND Approved__c = true`.
- Item 6 is not on `DHIS2__c`: the report's September 2026 total per module equals
  `SELECT Module__c, COUNT(Id) FROM Attendance_Batch__c WHERE Processing_Status__c = 'Success'
  AND Creator__c LIKE 'Jotform%' AND Attendance_Date__c >= 2026-09-01 AND Attendance_Date__c <=
  2026-09-30 GROUP BY Module__c`; one partner's cells, the same with `AND Account__r.Parent.Name
  = '<partner>'`; with the test-record rule too if #76 adds it. Not run yet, so no number here.
- Item 2 has no check: it is retired (#75).

Each but item 6 was run once for September 2026 and gives the table's cell
(`evidence/soql_2026-10-23_check_per_item.txt`; item 1's ticked count:
`evidence/soql_2026-10-23_review.txt`), the numbers as of 2026-10-23; a report filed or
approved later moves both sides.

Questions for GLOW:
- The labels are answered: Ryan, 2026-10-23 on #74, "Labels stay (#70)": the Monthly Report
  attendance totals (items 3 and 4) keep their labels, with no "(Monthly Report)".
- The period is answered: Ryan, 2026-10-23 on #74, the last 12 months is the default period of
  every Monthly Report dashboard; its date field is `Period__c` (#128, kept minimal, added
  2026-10-24), before #75-#79.
- The sources are answered: Ryan, 2026-10-23 on #74, "use the candidates": item 1 counts
  `Attendance_submitted_electronically__c` (#75), item 6 the Jotform batches' `Module__c` (#76),
  and item 2, with no source, is retired from D1 and its report goes to Decommissioned, kept (#75).

The reporting year (GLOW's review, epic #194; Ryan, 2026-11-02): the dashboards show the current
reporting year only, never 2025 and 2026 together, and offer a Month filter. Since #195
([plan](plans/2026-11-02-sf-reporting-year.md)) the period filter is `In_Reporting_Year__c equals
true`, a checkbox formula on `DHIS2__c` (from `Period__c`) and on `Attendance_Batch__c` (from
`Attendance_Date__c`): the year of today less 45 days, so the dashboards move to the new year on
15 February, once December's reports are in. Never a fixed `Year__c` (the cause above), and never
`THIS_YEAR` (it drops December's reports on 1 January). The Month filter is on
`DHIS2__c$Month__c`, and on `Attendance_Batch__c$Month_Name__c` (the same month names) for item 6.
Tasks #196 to #200 apply both, dashboard by dashboard; until each lands, its dashboard keeps the
last 12 months.

### GLOW Club Attendance

D1 (ticket #75, [plan](plans/2026-10-24-sf-dash-attendance.md)): the dashboard "Glow Club
Attendance" (`01ZRP000006iWqL2AU`) in "GLOW Monthly Dashboards", and items 1-4 of
`glow/sf_keep_list.csv` in "GLOW Monthly Reports". Status: retrieved live 2026-10-24 into
`data/sf_dash_attendance_2026-10-24/before/` and built in `data/sf_dash_attendance_2026-10-24/build/`;
the 4 copies made 2026-10-25 and the build deployed 2026-10-26 on Ryan's go (deploy
`0AfRP000002i7HZ0AY`, check-only `0AfRP000002i7Fx0AI`), read back into `after/`, each report's
September 2026 total equal to its SOQL signal below; the 5 reports D1 no longer uses moved to
Decommissioned the same day; no dashboard subscription (Ryan, 2026-10-25)
([Result](plans/2026-10-24-sf-dash-attendance.md#result)).
Ticket #196 (epic #194, GLOW's review of 2026-11-02; [plan](plans/2026-11-02-sf-review-attendance.md)):
retrieved live 2026-11-04 into `data/sf_glow_review_2026-11/attendance/before/` (equal to #75's
`after/`), items 1, 3 and 4 copied to Decommissioned the same day (`copy --tag "#196"`), and the
build deployed on Ryan's go (deploy `0AfRP000002j8mf0AA`, check-only `0AfRP000002j8l30AA`), read
back into `after/` and checked against SOQL ([Result](plans/2026-11-02-sf-review-attendance.md#result)).
- Item 1's column `Attendance_submitted_electronically__c` was not in the custom report type
  `Dhis2`, so the first check-only (`0AfRP000002i7EL0AY`) refused item 1; on Ryan's decision
  (2026-10-26) the same deploy added `DHIS2__c$Attendance_submitted_electronically__c` to
  `Dhis2` (not checked by default). Its rollback: the column is additive and harmless and may
  stay; to take it out, once item 1's report no longer uses it, retrieve `Dhis2` fresh, take
  that one column out of the retrieved file and deploy it after a check-only, on Ryan's go, never
  an older build or retrieve (DECISIONS 2026-10-16: `Dhis2` is shared with #76-#79, which may add
  columns later). While the fresh retrieve still equals `after/`'s, the result is byte-for-byte
  `data/sf_dash_attendance_2026-10-24/fresh_2026-10-26/`'s file, the comparison, not a source to
  deploy.

The retrieve of 2026-10-24 has the labels and folders #73 left. D1 runs as the viewer
(`LoggedInUser`, a dynamic dashboard), and its one dashboard filter was then Assigned Partner
Manager, with 6 values. Its six components were on item 3, item 2 and four reports #72 held in
"DHIS2 Reports" for D1 alone: "Participation by month" (`00ORP000004RJZ92AO`), "Attendance
Rosters Uploaded On DR By M" (`00ORP000005rTk92AE`), "Collection of Attendance Roster By Month"
(`00ORP000005rTNZ2A2`, a copy of item 1's report) and "Collection of Attendance Roster By M&P"
(`00ORP000005rTQn2AM`). Items 1 and 4 were on no component.

After #75's fix, D1 had three components, one per kept item on it, each titled with its report's
label (labels unchanged, #70); #196 added a fourth, the overall chart (below):

| Item | GLOW's measure | Report (component title) | What it counts on `DHIS2__c` | Component | SOQL signal, September 2026 (run 2026-10-24) |
|---|---|---|---|---|---|
| 1 | Whether attendance rosters were collected | "Collection of Attendance Roster by Month" (`00ORP000004RJYv2AO`) | The Monthly Reports with the checkbox `Attendance_submitted_electronically__c` ticked: the report filters it true and counts records (Ryan, 2026-10-23 on #74), in place of `collect_last_month_s_attendance__c`, blank since October 2025 | Bar chart: the record count per partner and month | `SELECT COUNT(Id) FROM DHIS2__c WHERE Period__c = 2026-09-01 AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') AND Attendance_submitted_electronically__c = true` = 21 |
| 3 | Monthly attendance totals | "Participation by Month and Partner" (`00ORP000005rSbB2AU`) | `Monthly_Total__c` ("Monthly Max", the largest of the partner's week counts), summed | Bar chart: the sum per partner and month | `SELECT COUNT(Id), SUM(Monthly_Total__c) FROM DHIS2__c WHERE Period__c = 2026-09-01 AND Account__c != null AND (NOT Account__r.Name LIKE '%test%')` = 42 records, sum 4,861 |
| 4 | Weekly attendance totals | "GLOW Club Each Week" (`00ORP000005ufOz2AI`) | `Week_1__c` to `Week_5__c` (the partner's count for each week, typed into the Monthly Report) and `Monthly_Total__c`, each summed, on the Monthly Reports whose `Monthly_Total__c` is neither blank nor 0 (the report's own two filters, kept) | Lightning table: the partner, the month, the sums of Weeks 1-5 and of Monthly Max | `SELECT COUNT(Id), SUM(Week_1__c), SUM(Week_2__c), SUM(Week_3__c), SUM(Week_4__c), SUM(Week_5__c), SUM(Monthly_Total__c) FROM DHIS2__c WHERE Period__c = 2026-09-01 AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') AND Monthly_Total__c != null AND Monthly_Total__c != 0` = 36 records; weeks 2,428, 1,676, 1,492, 1,314 and 518; sum 4,861 |

- Item 2, "Attendance rosters uploaded on the Drive" (report "Attendance Roster Uploaded on DR by
  M&P", `00ORP000005rTiX2AU`), is retired from D1 and its report moves to Decommissioned after
  the deploy (Ryan, 2026-10-23 on #74). It read `Submit__c`, blank on every Monthly Report since
  October 2025: the form stopped asking. Its component goes with the fix, and it has no SOQL
  signal.
- The four reports #72 held for D1 alone (above) also move to Decommissioned after the deploy,
  once no dashboard outside Decommissioned uses them; `tools/sf_report_folders.py move` refuses
  them before that (its dry run, 2026-10-24).
- Items 3 and 4 are the partners' own weekly counts in the Monthly Report, a different measure
  from the "Jotform Attendance" dashboard's "Girls who attended" (DECISIONS 2026-10-20), and are
  never added to it. A week count of 0 may be a blank the form saved as 0.
- Item 3, "Participation by Month and Partner" (`00ORP000005rSbB2AU`): since #196 the report shows
  no grand total (`showGrandTotal` false). GLOW asked to hide its total of 57,873: a sum of
  Monthly Max over partners and months, which double-counts girls who attend in several months,
  so it is not the number of unique girls.
- Item 4, "GLOW Club Each Week" (`00ORP000005ufOz2AI`), D1's weekly table: since #196 it shows no
  total row and no subtotals: `showTotal` is false on all 8 columns, the Sum Monthly Max
  (`Monthly_Total__c`) column included. The totals are off because adding the weekly counts
  across weeks and months double-counts girls who attend several sessions, and the same goes for
  the sum of Monthly Max over months (GLOW, 2026-11-02).
- The overall chart (#196): D1's top component, full width, is the column chart "Overall
  Attendance by Month" on the new report "Overall Attendance by Month" (`00ORP000009p0FJ2AY`,
  `Overall_Attendance_by_Month`, in "GLOW Monthly Reports"), its values shown and no total; the
  other three components sit below it. The report is a summary report grouped by `Period__c` by
  calendar month, with the sum of `Monthly_Total__c` (Monthly Max) over all partners and item 3's
  report filters (the reporting year and the test-record rule). It answers GLOW's request for
  "the overall attendance total by month, in addition to the partner-level breakdown". It is not
  on the keep list: `glow/sf_keep_list.csv` holds GLOW's items 1-19 and D1-D5, one row each.

The rules of every report (Ryan, 2026-10-23 and 2026-10-24; the period, the Month filter and the
Partner Manager values changed by #196, Ryan 2026-11-02):
- The period is the reporting year: the field filter `In_Reporting_Year__c equals true` (#195,
  true for the calendar year of today less 45 days, so 2026 only until the year rolls over on 15
  February 2027), in place of `Period__c equals LAST_N_MONTHS:12` (#128), the last 12 months until
  #196. D1 and its reports show no 2025 month. The standard date filter's column is `Period__c`,
  range All Time, in place of `CreatedDate`.
- Each report groups by the partner (`Account__c`), then by the month (`Period__c`, by calendar
  month): items 1 and 3 are matrices with the partner down and the month across, item 4 a summary
  report. The `Account__c.Owner`, `Account_Owner_Check__c` and `Month__c` groupings and the
  `Year__c` filter go. A grouping is never also a column: item 1's column is the checkbox, items 3
  and 4 show their sums.
- The charts of items 1 and 3 show the partner (`Account__c`), then the month (`Period__c`), and
  item 4's table the partner, the month and the six sums.
- The test-record filter is on every report: `Account is not blank AND Account: Account Name does not contain "test"`
  (#70), as two filter lines on `Account__c` (not equal to blank, and does not contain `test`; a
  lookup filters on the account's name). On 2026-10-24, over the last 12 months, it took out the 2
  Monthly Reports of test accounts, and none had a blank Account (SOQL).
- The dashboard's first filter is Assigned Partner Manager
  (`DHIS2__c$Account__c.Assigned_Partner_Manager__c`) on every component, so each manager sees
  the partners assigned to them (Ryan, 2026-10-24, for all five Monthly Report dashboards). Since
  #196 (GLOW's review, Ryan 2026-11-02) the dashboard has a second filter, Month: a filter on
  `DHIS2__c$Month__c` with 12 `equals` options, January to December, mapped on every component.
  Until #196 the dashboard had no Month filter. The dashboard has no Partner filter: the partner
  is one of the reports' groupings.
- The Partner Manager filter got 7 values from #75 (2026-10-26), within Salesforce's 50 per
  filter. Since #196 it has 6: the former PO's value (user `005RP000001RERJYA4`) is off it, as
  neither of that user's two partners has a Monthly Report in 2026 (both last reported in 2025).
  A partner whose manager has no value shows only with the filter cleared.
- The running user stays as the retrieve has it: Ryan's user since his hand move of D1 on
  2026-10-24 (#73), active. D1 runs as the viewer.

#75's check (SOQL on `DHIS2__c` for the last complete month, the test-record rule in every query;
numbers of 2026-10-24, and a Monthly Report filed or corrected later moves both sides):
- Each component: the signal in its row above equals the component's total.
- One partner's month, "Mahila Margadarshi", September 2026:
  `SELECT COUNT(Id), SUM(Monthly_Total__c), SUM(Week_1__c), SUM(Week_2__c), SUM(Week_3__c), SUM(Week_4__c), SUM(Week_5__c) FROM DHIS2__c WHERE Period__c = 2026-09-01 AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') AND Account__r.Name = 'Mahila Margadarshi'`
  = 1 record, Monthly Max 220, weeks 60, 61, 60, 25 and 0; with
  `AND Attendance_submitted_electronically__c = true` added, 1.
- One manager's view: the filter value of the manager with User Id `005RP000000qlipYAA` shows 12
  partners over the 12 months and, for September 2026, 9 partners, Monthly Max 1,300 and 7
  ticked: the same queries with `AND Account__r.Assigned_Partner_Manager__c = '005RP000000qlipYAA'`
  in place of the partner's name.
- No component includes a test account's records:
  `SELECT COUNT(Id) FROM DHIS2__c WHERE Period__c = LAST_N_MONTHS:12 AND Account__r.Name LIKE '%test%'`
  = 2, and the components show none of them.

#196's check (2026-11-04, after the refresh; a Monthly Report filed or corrected later moves both
sides):
- The overall chart equals
  `SELECT CALENDAR_MONTH(Period__c), SUM(Monthly_Total__c) FROM DHIS2__c WHERE In_Reporting_Year__c = true AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') GROUP BY CALENDAR_MONTH(Period__c)`
  in every month: January 3,409, February 5,019, March 5,673, April 5,068, May 5,433, June 5,275,
  July 4,856, August 4,826, September 5,385 and October 0 (3 early reports, no figure yet).
- September is the same as before #196: Salesforce's September Monthly Max with these filters was
  5,385 on 2026-11-02 (the 2026-11-02/03 handoff, quoted in ticket #201), and the overall chart
  shows 5,385. Item 3's September signal above, 4,861 on 2026-10-24, is older: September's
  reports were due by 15 October, and late or corrected September reports reached Salesforce
  between 2026-10-24 and 2026-11-02.
- No grouping label in any component reads 2025 (0 of 949 labels).
- With the Month filter on September, every component shows September 2026 only, with data.
- The live Partner Manager filter has 6 options, none of them the former PO's.
- Item 4's table shows no total row and item 3 no grand total.
- Unfiltered, item 1's roster chart shows one month: it counts only rosters submitted
  electronically.
- Refresh: `sf api request rest '/services/data/v67.0/analytics/dashboards/01ZRP000006iWqL2AU' -o glow -X PUT -b '{}'`
  (VPN off, on Ryan's go). A filtered view needs its own refresh, the same PUT with
  `?filter2=<option id>` (the Month filter's option), before a GET returns its data.

Rollback (DECISIONS 2026-10-16):
- D1 is dynamic and the API refuses to copy it (the org is at its limit of 5 dynamic dashboards,
  and #73's clone was refused with HTTP 400), so the dashboard has no Decommissioned copy: its
  rollback is this change's retrieve `data/sf_dash_attendance_2026-10-24/before/`.
- The order, the moves undone before anything is deployed: the dashboard in `before/` names its
  six reports by folder path, and the plan's step 7 moves five of them (item 2's report from
  "GLOW Monthly Reports", the four held reports from "DHIS2 Reports") to Decommissioned, so after
  the moves a check-only of `before/` is refused (those reports are no longer at their paths)
  until the moves are put back.
  The moves of item 2's report and the four held reports are put back by
  `python3 tools/sf_report_folders.py undo --vpn-off --dir data/sf_dash_attendance_2026-10-24`
  (its dry run first, then `--apply` on Ryan's go), last first. Before the moves there is nothing
  to undo.
- Then the dashboard and its three reports are restored by deploying their files in `before/`
  only while a fresh retrieve of them equals `after/` (nothing has changed them since this
  change's deploy), never from an older build or retrieve, on Ryan's go after a check-only.
- A Salesforce user restores a report from its copy in Decommissioned, made by
  `copy --tag "#75"` before the change: open the copy, then Save As or move it into "GLOW Monthly
  Reports" (the archive rule above).
- Nothing is deleted: the copies stay in Decommissioned.

Rollback of #196 ([plan](plans/2026-11-02-sf-review-attendance.md#rollback); DECISIONS
2026-10-16), each write on Ryan's go after a check-only, VPN off:
- Since #196's deploy a fresh retrieve no longer equals #75's `after/`, so #75's rollback above
  runs only after this one.
- Items 1, 3 and 4 come back by a deploy, not from their copies: D1's components point at the
  reports themselves, so a copy saved into "GLOW Monthly Reports" would be a separate report that
  D1 does not show. The copies in Decommissioned (`00ORP000009p02P2AQ`, `00ORP000009p0412AA` and
  `00ORP000009p05d2AA`, made by `copy --tag "#196"` before the change) are the record of what the
  reports were.
- Each report's deploy is one of two, after a check-only: a fresh retrieve of it, edited back
  where #196 changed it; or its file in #196's retrieve
  `data/sf_glow_review_2026-11/attendance/before/`, only while a fresh retrieve of it equals
  `after/` (DECISIONS 2026-10-16).
- D1 is dynamic and has no Decommissioned copy (the org is at its limit of 5 dynamic dashboards),
  so the dashboard is restored the same way, by deploying only its own file in that `before/`,
  only while a fresh retrieve of it equals `after/` (nothing has changed it since #196's deploy),
  or a fresh retrieve of it edited back, never from an older build or retrieve.
- This rollback never deploys #75's `data/sf_dash_attendance_2026-10-24/before/` or `build/`.
- The new report "Overall Attendance by Month" (`00ORP000009p0FJ2AY`) is not in `before/`, and
  D1 as `before/` has it shows no component on it: the report may stay, harmless, or move to
  Decommissioned once D1 no longer uses it. Nothing is deleted.

### GLOW Club Observations

D3 in `glow/sf_keep_list.csv`, the GLOW Club Observations dashboard, is the dashboard "GLOW Club
Training" (`01ZRP000006k2D32AI`) in "GLOW Monthly Dashboards", with items 9-11 (ticket #77,
[plan](plans/2026-10-24-sf-dash-observations.md)). Its label and its reports' labels stay as they
are (Ryan, 2026-10-23), and each component's title is its report's label. It runs as the
specified running user (`SpecifiedUser`), so it shows the data of its last refresh: a refresh
after each change (a PUT, Ryan's go) and Ryan's weekly Subscribe in Lightning keep it current.
#77's build `data/sf_dash_observations_2026-10-24/build/` is deployed since 2026-10-25 on Ryan's
go (deploy `0AfRP000002i5hB0AQ`, the plan's Result) and read back into `after/`. Item 11's report
was redeployed from `data/sf_dash_observations_2026-10-24/build_item11/` on 2026-10-26 on Ryan's
go (deploy `0AfRP000002i6yE0AQ`; item 11, below), and that day's refresh returned data on all
three components.

The three components, each on its report in "GLOW Monthly Reports":
- Item 9, "GLOW Club observation form submitted": the report "Submission of GC observation forms
  M & P" (`00ORP000004RJZC2A4`, matrix) counts Monthly Reports by the answer to
  `did_you_submit_your_GC_observation_form__c` (its values across: Yes, No, and NA in some older
  months; a blank answer is filtered out), for each partner and month. The form in use today
  (`dHIS2Controller`) clears this answer when the partner observed no session, so a partner with
  0 sessions has no answer here. The component is a stacked column for each month, one segment
  per answer. SOQL signal (September 2026: 23 Yes, 3 No; January 2026: 7 Yes, 7 No, 8 NA):
  `SELECT did_you_submit_your_GC_observation_form__c, COUNT(Id) FROM DHIS2__c WHERE Period__c = LAST_MONTH AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') AND did_you_submit_your_GC_observation_form__c != null GROUP BY did_you_submit_your_GC_observation_form__c`.
- Item 10, "Number of GLOW Club sessions observed": the report "Total Number of Club Observations
  M&P" (`00ORP000004RJZD2A4`, summary) sums `GC_sessions_did_you_observe_last_month__c` for each
  partner and month. The component is a column of the sum for each month. SOQL signal (September
  2026: 42 Monthly Reports, sum 93):
  `SELECT COUNT(Id), SUM(GC_sessions_did_you_observe_last_month__c) FROM DHIS2__c WHERE Period__c = LAST_MONTH AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') AND GC_sessions_did_you_observe_last_month__c != null`.
- Item 11, "Whether or not PC has observed sessions": the report "Completed Observing Clubs
  Alteast Once P" (`00ORP000005uf412AA`, matrix) is a yes/no for each partner and month. Its
  bucket "Observed" on `GC_sessions_did_you_observe_last_month__c` reads Yes for 1 or more
  sessions and No for 0 (across); each Monthly Report is one partner's month, so its counts are
  partners. Its report keeps the sum of `GC_sessions_did_you_observe_last_month__c` as a column
  and has its record count on (the report param `co` 1, redeployed on 2026-10-26), so
  its aggregates offer `RowCount` beside the Sum. The component is a stacked column for each
  month, Yes and No; its chart measures the record count (`RowCount`), the partner-months in each
  Yes/No bucket for each month. Before that redeploy from `build_item11/` its record count was
  off (`co` 0) and the chart failed the refresh with 406 (2026-10-25). SOQL signal, the partners who observed (September 2026: 27, and 15 with 0):
  `SELECT COUNT(Id) FROM DHIS2__c WHERE Period__c = LAST_MONTH AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') AND GC_sessions_did_you_observe_last_month__c > 0`;
  the partners who observed none: the same query with `= 0`.
  The field is never blank: the form shows it as 0 until the partner types a number, and
  `dHIS2Controller` (`setNumber`) saves a blank number as 0. So a No is either 0 sessions
  observed or the question left unanswered, and the report does not tell the two apart; the report's
  `!= null` filter removes nothing (0 blank in September 2026, by the form, not by chance).

Two kinds of "no answer" the reports show differently:
- A partner that filed no Monthly Report for a month has no `DHIS2__c` record for it, so it has
  no row in any of the three reports: a missing response, which the reports keep apart from a No
  by leaving it out. Who filed is "Reports completed on time" (item 18, D5).
- A partner that filed but left the sessions question unanswered counts as 0 sessions: a No in item 11
  and nothing added in item 10 (above).

How the reports read the data:
- Each report is grouped by the partner (`DHIS2__c.Account__c`), then by `Period__c` by calendar
  month; the month is never `CreatedDate`, and a grouping is never also a column.
- The default period is the last 12 months: the report filter `Period__c equals LAST_N_MONTHS:12`,
  which leaves out the current, incomplete month. The standard date filter's column is
  `Period__c`, range All Time, so the field filter sets the period.
- Each report carries the test-record rule as a report filter: `Account is not blank AND Account: Account Name does not contain "test"`
  (#70), in the report XML `DHIS2__c$Account__c` `notEqual` blank and `DHIS2__c$Account__c`
  `notContain` `test` (the lookup matches on the account's name). In September 2026 no Monthly
  Report is on a test account or a blank Account; in the last 12 months, 2 are, both on a test
  account: one in January 2026 and one in March 2026, each with 0 sessions and no item 9 answer.
  With the rule, item 11 counts 33 No in January and 19 in March (34 and 20 without it), and
  item 10's report 46 records in each of the two months (47 without it).
- Each report also keeps its filter on a non-blank answer (its own field `!= null`).

The dashboard's only filter is Partner Manager (`DHIS2__c$Account__c.Assigned_Partner_Manager__c`,
its 6 partner managers), on every component, and viewers read the partner and the month from the
reports' groupings (Ryan, 2026-10-24 on #77). It has no Partner filter and no Month filter. #77
takes item 16 ("Meeting with mentors to discuss program", `00ORP000004RJZ72AO`) off this
dashboard, with the five components on reports in "DHIS2 Reports"; #78 puts item 16 on D4. Those
five reports were moved to Decommissioned by `tools/sf_report_folders.py move` on 2026-10-26,
once this dashboard used none of them; the only components still on them are on dashboards in
Decommissioned.

For one partner's month, the same queries take `AND Account__r.Name = '<partner>'`; the three
items' values for one partner in one query (September 2026, Abaana Community Outreach (ACO)
Africa: Yes, 3 sessions, so observed):
`SELECT Account__r.Name, did_you_submit_your_GC_observation_form__c, GC_sessions_did_you_observe_last_month__c FROM DHIS2__c WHERE Period__c = LAST_MONTH AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') AND Account__r.Name = '<partner>'`.

Rollback:
- The dashboard and items 9-11 roll back together: redeploy those 4 components of this change's
  retrieve `data/sf_dash_observations_2026-10-24/before/` (check-only, Ryan's go, deploy) only
  while a fresh retrieve of the same 4 equals `after/`. The deploy names each of the 4 with `-m`,
  within `before/`:
  `sf project deploy start -o glow -m "Dashboard:GLOW_Monthly_Dashboards/vbKFAhzWWcXLOmmkSckbvWkgmwtdrM" -m "Report:GLOW_Monthly_Reports/Submission_of_GC_observation_forms_M_P_iuz" -m "Report:GLOW_Monthly_Reports/Total_Number_of_Club_Observations_by_M_q3M" -m "Report:GLOW_Monthly_Reports/Completed_Observing_Clubs_Alteast_Once_P_cn6"`,
  with `--dry-run` for the check-only. `before/` also holds item 16's report, the five "DHIS2
  Reports" reports, two report types and `DHIS2__c`, which a whole-folder deploy would put back
  too, unseen by the `after/` compare: the rollback deploy is the 4 only. That keeps every Id, so
  the dashboard's components read the old reports again and the FlexiPage
  `Monthly_Report_Dashboards` keeps D3 in its place. The five "DHIS2 Reports" reports go back to
  their folder first (the plan's Rollback). After item 11's fix forward (the plan's Rollout),
  item 11's report is compared with `data/sf_dash_observations_2026-10-24/build_item11/` in place
  of `after/`; the fix alone rolls back by redeploying item 11's report from `after/` only while
  a fresh retrieve of it equals `build_item11/`.
- When they differ, someone has changed the dashboard or a report since the deploy, and the
  rollback starts from a fresh retrieve by the ritual above. A rollback never deploys an older
  build or another change's retrieve (DECISIONS 2026-10-16).
- The copies in Decommissioned made before the deploy (`copy --tag "#77"`) restore D3 and its
  reports in Lightning only as a set. The dashboard copy points at the reports' original Ids,
  whose content this deploy rewrites, so its three observation components show the new reports.
  Move the three report copies and the dashboard copy back (Decommissioned, above), then point
  each of the dashboard copy's three components at its report's copy. The copies keep their own
  Ids, so the FlexiPage then needs the dashboard copy in D3's place (the ritual: check-only,
  Ryan's go, deploy).

### GLOW Club Implementation

D2 in `glow/sf_keep_list.csv`, the GLOW Club Implementation dashboard, is the dashboard
"Implementation Dashboard" (`01ZRP000006jU9o2AE`) in "GLOW Monthly Dashboards", with items 5-8
(ticket #76, [plan](plans/2026-10-24-sf-dash-implementation.md); ticket #197,
[plan](plans/2026-11-02-sf-review-implementation.md)). The dashboard keeps its label. Until #197
its reports kept the labels #70 recorded; since #197 (GLOW's review, Ryan 2026-11-02) items 5-7
carry GLOW's names within Salesforce's 40 characters and D2's components GLOW's full names, as
`glow/sf_keep_list.csv`'s `label_target` gives them; item 8 is as it was.
It runs as the viewer (`LoggedInUser`); a daily Subscribe in Lightning refreshes it (a
subscription, not metadata; Ryan's to set, as for "Jotform Attendance"). #76's changes are live since 2026-10-26 on Ryan's go (deploy
`0AfRP000002i7Cj0AI`, check-only `0AfRP000002i7B70AI`), read back into `after/` and checked
against SOQL (the plan's Result).
Ticket #197 (epic #194, GLOW's review of 2026-11-02): retrieved live 2026-11-04 into
`data/sf_glow_review_2026-11/implementation/before/` (equal to #76's `after/`), items 5-8 copied
to Decommissioned the same day (`copy --tag "#197"`), and live on Ryan's go (deploy
`0AfRP000002j8zZ0AQ`, check-only `0AfRP000002j8xx0AA`), read back into `after/` and checked
against SOQL ([Result](plans/2026-11-02-sf-review-implementation.md#result)).

D2 and its reports show 2026 only, no 2025 month (GLOW's review: no October-December 2025), until
the reporting year moves on 15 February 2027 (#195).

The modules' data gap (Ryan, 2026-11-02, DECISIONS 2026-11-02): January-August 2026 has no module
data, because the Monthly Report's module question has no answers after September 2025 (400 rows
in 2025, 0 in 2026). From September 2026 the modules come from Jotform
(`Attendance_Batch__c.Module__c`), one batch per club and session date; the 15 pilot batches of
February-August 2026 stay out. GLOW asked for the earlier 2026 months "based on the partner
monthly report": there is nothing there to show.

The six components:
- Item 5, "GLOW Club activities carried out": the report "Club Implementation by Month and
  Partner" (`00ORP000005rY3t2AE`, matrix; "Copy of GLOW Club Implementation by M&P" until #197),
  component "GLOW Club Implementation by Month and Partner", a stacked column for each month, one
  segment per answer, counts Monthly Reports by the answer to
  `Did_you_implement_GLOW_Club_last_month_f__c` (across), for each partner and month. Its filter
  leaves out a blank answer and the answer "No, we did not implement at all", as before #76. SOQL
  signal (its total equals the component's):
  `SELECT Did_you_implement_GLOW_Club_last_month_f__c, COUNT(Id) FROM DHIS2__c WHERE In_Reporting_Year__c = true AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') AND Did_you_implement_GLOW_Club_last_month_f__c != null AND Did_you_implement_GLOW_Club_last_month_f__c != 'No, we did not implement at all' GROUP BY Did_you_implement_GLOW_Club_last_month_f__c`.
- Item 6, "GLOW Club modules implemented": the report "Modules Implemented by Month and Partner"
  (`00ORP000009kUNh2AM`, `Glow_Club_Modules_Implemented_Jotform`, new in #76 on the report type
  `Attendance_Totals`; "Glow Club Modules Implemented by M&P" until #197) reads the Jotform
  batches on `Attendance_Batch__c` and their `Module__c`, one batch per club and session date,
  where `Processing_Status__c` equals `Success`, `Creator__c` starts with `Jotform`,
  `In_Reporting_Year__c` equals true and `Attendance_Date__c` (the session date) is on or after
  2026-09-01 (Ryan, 2026-10-25: the February-August 2026 pilot batches stay out). In the report
  filter that floor is in the locale format, `9/1/2026`. Since #197 item 6 counts the unique
  partners that implemented each module, not clubs or batches (GLOW: "the total number of
  partners that implemented each module as opposed to the number of clubs"). Item 6 is a summary
  report grouped by `Module__c`, then by the partner, the club's parent (`Account__c.Parent`),
  with the custom summary formula `FORMULA1`, `Attendance_Batch__c.Account__c.Parent.Name:UNIQUE`
  (label "Partners"), at the module level, as item 18's `FORMULA1` does. Its component "GLOW Club
  Modules Implemented by Month and Partner" is a horizontal bar, one bar per module, its length
  the number of unique partners, values shown, sorted by value descending; the month comes from
  D2's Month filter. Until #197 item 6 counted the batches per module, for each partner and month
  of `Attendance_Date__c`, a matrix, and its period was the last 12 months. Item 6 takes the
  test-record rule on the club's parent: not blank, and its name does not contain "test". The old
  item 6 report (`00ORP000005rZxd2AE`) counted the form's module field, which is blank since
  2025-10; it is in Decommissioned since 2026-10-26. Until #197 `glow/sf_keep_list.csv` kept its
  id as #70 recorded it; since #197 the keep list carries the live report's id,
  `00ORP000009kUNh2AM`. SOQL signal (2026-11-04: 20 modules, for example Power of Girls 101 20
  partners, Community 101 16, Self Advocacy 13):
  `SELECT Module__c, COUNT_DISTINCT(Account__r.ParentId) FROM Attendance_Batch__c WHERE Processing_Status__c = 'Success' AND Creator__c LIKE 'Jotform%' AND In_Reporting_Year__c = true AND Attendance_Date__c >= 2026-09-01 AND Account__r.ParentId != null AND (NOT Account__r.Parent.Name LIKE '%test%') GROUP BY Module__c`;
  with the Month filter on September, the same query with `AND Month_Name__c = 'September'`
  (2026-11-04: 17 modules).
- Item 7, "GLOW Club modules adapted to the local context": the report "Modules Adapted by Month
  and Partner" (`00ORP000005uehR2AQ`, matrix; "GLOW Club Modules Adapted By Month" until #197),
  component "GLOW Club Modules Adapted by Month and Partner", a stacked column for each month,
  counts Monthly Reports by the answer to `Adapted_to_the_local_culture_or_context__c` (Yes or
  No, across), for each partner and month; a blank answer is filtered out. SOQL signal (its total
  equals the component's):
  `SELECT Adapted_to_the_local_culture_or_context__c, COUNT(Id) FROM DHIS2__c WHERE In_Reporting_Year__c = true AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') AND Adapted_to_the_local_culture_or_context__c != null GROUP BY Adapted_to_the_local_culture_or_context__c`.
- Item 8, "Summits completed": the report "Local and Regional Summits By Month 2"
  (`00ORP000005uekf2AA`, matrix, label and component title as they were), a stacked column for
  each month, counts Monthly Reports by the answer to `Select_summits_completed_last_month__c`
  (across), for each partner and month; a blank answer is filtered out. SOQL signal (2026-11-04:
  Other 32, Local Advocacy Summit 9, Ways We GLOW Summit 5, IDG Summit 2, "No summit(s) were
  done" 321):
  `SELECT Select_summits_completed_last_month__c, COUNT(Id) FROM DHIS2__c WHERE In_Reporting_Year__c = true AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') AND Select_summits_completed_last_month__c != null GROUP BY Select_summits_completed_last_month__c`.
- Item 8's summit types (#197, GLOW: "consolidated responses for the types of summits
  completed"): the Bar component "Types of Summits Completed" (row 16, full width, values shown,
  by value descending) on the new report "Summit Types Completed" (`00ORP000009p0Qc2AI`,
  `Summit_Types_Completed`, in "GLOW Monthly Reports"), a summary report grouped by
  `Select_summits_completed_last_month__c`, the record count, with item 8's filters and the
  answer "No summit(s) were done" left out. It is a new report because that filter on item 8
  itself would change item 8's monthly chart. Its bars are item 8's SOQL signal above without
  "No summit(s) were done".
- The adapted modules' responses (#197, GLOW: "consolidated responses for which modules were
  adapted"): the Lightning table "GLOW Club Modules Adapted: Responses" (row 24, full width) on
  the new report "Modules Adapted Responses" (`00ORP000009p0Qb2AI`, `Modules_Adapted_Responses`,
  in "GLOW Monthly Reports"), a tabular report of the partner, `Period__c`,
  `If_so_please_select_which_ones__c` (the modules adapted) and
  `Please_describe_how_you_adapted_the_curr__c` (how), sorted by `Period__c`. Its filters are
  item 7's, with `If_so_please_select_which_ones__c` not blank in place of the Yes or No answer:
  the rows with modules picked (the long-text description takes no filter). The table is sorted
  by `Period__c` (`flexTableSortInfo`: Salesforce refuses a Lightning table on a tabular report
  without it). The dashboard shows the first 255 characters of the long text; the report has it
  in full. SOQL signal (2026-11-04: 244 rows, 243 on 2026-11-02; September 29):
  `SELECT COUNT(Id) FROM DHIS2__c WHERE In_Reporting_Year__c = true AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') AND If_so_please_select_which_ones__c != null`.

How the reports read the data:
- Items 5, 7 and 8 are each grouped by the partner (`DHIS2__c.Account__c`), then by `Period__c`
  by calendar month (the Monthly Report's month, never `CreatedDate`), the answer across; a
  grouping is never also a column.
- Since #197 their period is the reporting year, the report filter `In_Reporting_Year__c equals
  true` (#195), in place of `Period__c equals LAST_N_MONTHS:12`, which was the period from #76
  until #197; the standard date filter's column is `Period__c`, range All Time, so the field
  filter sets the period. The two new reports have the same period.
- Items 5, 7 and 8 carry the test-record rule as a report filter: `Account is not blank AND Account: Account Name does not contain "test"`
  (#70), in the report XML `DHIS2__c$Account__c` `notEqual` blank and `DHIS2__c$Account__c`
  `notContain` `test` (the lookup matches on the account's name).
- Item 6 reads `Attendance_Batch__c`, not the Monthly Report: its period
  (`Attendance_Batch__c.In_Reporting_Year__c` equals true and the September 2026 floor), grouping
  and test-record rule are in its own entry above.

D2's first dashboard filter is Partner Manager ("Assigned Partner Manager"), on
`DHIS2__c$Account__c.Assigned_Partner_Manager__c` for items 5, 7 and 8 and the two new reports
and on `Attendance_Batch__c$Account__c.Parent.Assigned_Partner_Manager__c` for item 6 (Ryan,
2026-10-24 on #76). It had 6 options from #76; since #197 it has 5: the former PO's option (user
`005RP000001RERJYA4`) is off it, as on D1 (#196). Since #197 (GLOW's review, Ryan 2026-11-02) D2
has a second filter, a Month filter with 12 `equals` options, January to December, on
`DHIS2__c$Month__c` for items 5, 7 and 8 and the two new reports and on
`Attendance_Batch__c$Month_Name__c` for item 6. Until #197 D2 had no Month filter. D2 has no
Partner filter: viewers read the partner from the reports' groupings. The shared report type
`Attendance_Totals` gets one new column, `Account__c.Parent.Assigned_Partner_Manager__c` (the
partner's manager, through the club's parent), so that the Partner Manager filter reaches item 6;
the Attendance reports on that type are unchanged (#195 later added its own columns there). The 7
"DHIS2 Reports" reports D2 used before #76 and the old item 6 report moved to Decommissioned on
2026-10-26; no dashboard component uses any of them.

For one partner's month, the three `DHIS2__c` answers in one query:
`SELECT Account__r.Name, Did_you_implement_GLOW_Club_last_month_f__c, Adapted_to_the_local_culture_or_context__c, Select_summits_completed_last_month__c FROM DHIS2__c WHERE In_Reporting_Year__c = true AND Month__c = 'September' AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') AND Account__r.Name = '<partner>'`;
and for one partner, the modules item 6 counts it in (each listed module counts the partner once):
`SELECT Module__c, COUNT(Id) FROM Attendance_Batch__c WHERE Processing_Status__c = 'Success' AND Creator__c LIKE 'Jotform%' AND In_Reporting_Year__c = true AND Attendance_Date__c >= 2026-09-01 AND Account__r.Parent.Name = '<partner>' GROUP BY Module__c`.

#197's check (2026-11-04, after the refresh; a Monthly Report or a batch filed later moves both
sides):
- Item 6 equals its SOQL signal above in 20 of 20 modules; with the Month filter on September (a
  filtered refresh, `?filter2=<option id>`), 17 of 17 modules equal the same query with
  `AND Month_Name__c = 'September'`, and all 6 components return data.
- The summit types chart equals item 8's SOQL by answer: Other 32, Local Advocacy Summit 9, Ways
  We GLOW Summit 5, IDG Summit 2 ("No summit(s) were done", 321, left out).
- The responses table has 244 rows, the SOQL count of 2026 rows with modules picked; September
  29, equal.
- No grouping label in any component reads 2025 (0 of 122).
- The live Partner Manager filter has 5 options, none of them the former PO's; the Month filter
  has 12.
- Refresh: `sf api request rest '/services/data/v67.0/analytics/dashboards/01ZRP000006jU9o2AE' -o glow -X PUT -b '{}'`
  (VPN off, on Ryan's go); a filtered view needs its own refresh, the same PUT with
  `?filter2=<option id>`, before a GET returns its data.

Rollback (#76; this change's retrieve is `data/sf_dash_implementation_2026-10-24/before/`):
- Each of the four reports has a copy in Decommissioned, made 2026-10-26 before the deploy
  (`copy --tag "#76"`, ledger `data/sf_dash_implementation_2026-10-24/ledger.csv`):
  `00ORP000009kUFd2AM` of item 5, `00ORP000009kUHF2A2` of the old item 6, `00ORP000009kUIr2AM`
  of item 7 and `00ORP000009kUKT2A2` of item 8.
- The reports roll back from their copies in Decommissioned: move a copy back into "GLOW Monthly
  Reports" (Decommissioned, above) and point D2's component at it in Lightning; the copies keep
  their own Ids.
- D2 is a dynamic dashboard and the org is at its limit of 5 dynamic dashboards, so the
  Analytics API refuses its copy and D2 has no copy in Decommissioned: its rollback is this
  change's retrieve `data/sf_dash_implementation_2026-10-24/before/`.
- First the 8 moved reports go back to their folders by the undo of this change's ledger
  (`python3 tools/sf_report_folders.py undo --vpn-off --dir data/sf_dash_implementation_2026-10-24`,
  its dry run, then the same with the apply flag on Ryan's go), because D2's old components read
  them.
- Then D2, items 5, 7 and 8 and `Attendance_Totals` roll back together: redeploy those 5
  components of `data/sf_dash_implementation_2026-10-24/before/` (check-only, Ryan's go, deploy,
  each named with `-m` within `before/`) only while a fresh retrieve of the same 5 equals
  `after/`. That keeps every Id, so D2's components read the old reports again; the new item 6
  report then goes to Decommissioned by `move` (the plan's Rollback).
- `before/` also holds the old item 6 report, the 7 "DHIS2 Reports" reports and the report type
  `Dhis2`, which #76 leaves as they are: the rollback deploy is the 5 only, never the whole
  folder.
- When a fresh retrieve and `after/` differ, someone has changed D2 or a report since the
  deploy: stop, ask Ryan, and start the rollback from that fresh retrieve by the ritual above.
- A rollback never deploys an older build or another change's retrieve (DECISIONS 2026-10-16).

Rollback of #197 ([plan](plans/2026-11-02-sf-review-implementation.md#rollback); DECISIONS
2026-10-16), each write on Ryan's go after a check-only, VPN off:
- Since #197's deploy a fresh retrieve no longer equals #76's `after/`, so #76's rollback above
  runs only after this one.
- Items 5, 6, 7 and 8 come back by a deploy, not from their copies: D2's components point at the
  reports themselves, so a copy saved into "GLOW Monthly Reports" would be a separate report that
  D2 does not show. The copies in Decommissioned (`00ORP000009p0IX2AY`, `00ORP000009p0K92AI`,
  `00ORP000009p0Ll2AI` and `00ORP000009p0NN2AY`, made by `copy --tag "#197"` before the change)
  are the record of what the reports were.
- Each report's deploy is one of two, after a check-only: a fresh retrieve of it, edited back
  where #197 changed it; or its file in #197's retrieve
  `data/sf_glow_review_2026-11/implementation/before/`, only while a fresh retrieve of it equals
  `after/` (DECISIONS 2026-10-16).
- D2 is dynamic and has no Decommissioned copy (the org is at its limit of 5 dynamic dashboards),
  so the dashboard is restored the same way, by deploying only its own file in that `before/`,
  only while a fresh retrieve of it equals `after/` (nothing has changed it since #197's deploy),
  or a fresh retrieve of it edited back, never from an older build or retrieve. D2 and the four
  reports go in one deploy, so D2's old components meet the reports as they were.
- This rollback never deploys #76's `data/sf_dash_implementation_2026-10-24/before/` or `build/`.
- The two new reports, "Summit Types Completed" (`00ORP000009p0Qc2AI`) and "Modules Adapted
  Responses" (`00ORP000009p0Qb2AI`), are not in `before/`: D2's redeploy takes them off the
  dashboard first, as D2 in `before/` has no component on them, and then they move to
  Decommissioned (the archive rule above). Nothing is deleted.

### GLOW Club Reporting

The dashboard "Reporting" (`01ZRP000006oxSr2AI`, D5 in `glow/sf_keep_list.csv`, in "GLOW Monthly
Dashboards") is the GLOW Club Reporting dashboard: items 17 and 18. Item 19 is the table, on no
dashboard. Ticket #79, [plan](plans/2026-10-24-sf-dash-reporting.md). Status: deployed 2026-10-26
(`0AfRP000002i7330AA`) from `data/sf_dash_reporting_2026-10-24/build/`, read back into `after/`
and checked against SOQL (the plan's Result).

What each one counts (`DHIS2__c`, one Monthly Report per partner per month):
- Item 17, GLOW's "Report approved by PO", is the report "Approved Approvals monthly report"
  (`00ORP000006XXEf2AO`): the Monthly Reports with `Approved__c` ticked, a record count.
- Item 18, GLOW's "Report submitted on time", is the report "Reports completed on time"
  (`00ORP0000054DyH2AU`): the Monthly Reports filed, a record count, with each one's
  `Monthly_Report_submission_date__c` and `Monthly_Report_Modified_Date__c` as columns. No report
  computes "on time" yet (#119, on hold).
- Item 19, GLOW's "GLOW of the Month Stories", is the report "GLOW of the Month Stories Report"
  (`00ORP000005p2L32AI`): one row per Monthly Report with its stories (outstanding stories, peer
  support, community impact, success story, personal growth).

How they are built (RUNBOOK "Why the dashboards showed old data", The fix):
- Each report filters `Period__c equals LAST_N_MONTHS:12`, the last 12 months through `Period__c`
  (#128), which leaves out the current, incomplete month. Its standard date column is `Period__c`,
  range All Time, in place of `CreatedDate`. Item 19's fixed year (`Year__c equals 2026`) is
  removed.
- Both dashboard reports, items 17 and 18, group by Partner (`DHIS2__c.Account__c`, the partner
  account), then by Month (`Period__c` by calendar month). The owner groupings
  (`Account_Owner_Check__c`, `Account__c.Owner`) and item 17's `Approved__c` grouping are removed,
  and a grouping is never also a column.
- The test-record rule of #70 is a report filter on all three: `Account is not blank AND Account:
  Account Name does not contain "test"`. It keeps the test records, a test account's or a blank
  Account's Monthly Reports, out of every component and of the table. On 2026-10-24 it leaves out
  2 of the 569 Monthly Reports of the window, and none of September 2026.
- Item 19 is a tabular report: the org had it as a summary report grouped by `Month__c`, and the
  build makes it tabular, with no grouping. Item 19 has Partner and Month as its columns and its
  filters: the columns `Account__c` and `Period__c`, beside the stories.
- Item 19's Month filter reads `Period__c` (`Period__c equals LAST_N_MONTHS:12`, which a viewer
  can narrow to one month) and its Partner filter reads `Account__c` (Account not blank, which a
  viewer can narrow to one partner). The "test" condition is locked.
- The dashboard has one filter, Partner Manager (`DHIS2__c$Account__c.Assigned_Partner_Manager__c`),
  as today, so each manager picks their own partners (Ryan, 2026-10-24 on #79). It has no Partner
  filter and no Month filter (Ryan, 2026-10-24, for every Monthly Report dashboard; DECISIONS
  2026-10-24). The filter offers 7 managers: the 6 it offered plus the active manager it lacked
  (Ryan, 2026-10-25); of the 8 managers with partners in the window, the eighth, inactive, is
  left out by a Ruling made in the build, not by Ryan: open for him to reverse, and no rule for
  the other Monthly Report dashboards until he confirms it.
- The dashboard's components are two tables titled with the reports' labels, "Approved Approvals
  monthly report" and "Reports completed on time", each a row per partner and month with its
  count. They take the place of the one component today, on "Partner Report Submission On Time"
  (`00ORP000005u1WP2AY`), one of the 19 reports held in "DHIS2 Reports", which moves to
  Decommissioned once the dashboard no longer uses it.
- The dashboard runs as the viewer (`LoggedInUser`), as today; its running user is unchanged.

The SOQL signals, for the last complete month, each with the period and the test-record rule. A
component is right when, refreshed, it shows the same total and the same number for one partner:
- Item 17, "Report approved by PO": the total is `SELECT COUNT(Id) FROM DHIS2__c WHERE Period__c =
  LAST_MONTH AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') AND Approved__c = true`,
  and one partner's number is `SELECT Account__r.Name, COUNT(Id) FROM DHIS2__c WHERE Period__c =
  LAST_MONTH AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') AND Approved__c = true
  GROUP BY Account__r.Name`.
- Item 18, "Report submitted on time": the total is `SELECT COUNT(Id) FROM DHIS2__c WHERE
  Period__c = LAST_MONTH AND Account__c != null AND (NOT Account__r.Name LIKE '%test%')`, and one
  partner's number is `SELECT Account__r.Name, COUNT(Id) FROM DHIS2__c WHERE Period__c =
  LAST_MONTH AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') GROUP BY
  Account__r.Name`.
- Item 19, "GLOW of the Month Stories": the table's rows are `SELECT Account__r.Name, Period__c
  FROM DHIS2__c WHERE Period__c = LAST_MONTH AND Account__c != null AND (NOT Account__r.Name LIKE
  '%test%') ORDER BY Account__r.Name`, and their count `SELECT COUNT(Id) FROM DHIS2__c WHERE
  Period__c = LAST_MONTH AND Account__c != null AND (NOT Account__r.Name LIKE '%test%')`.

The baseline, 2026-10-24 (September 2026, before the change; `evidence/` of this change): 16
approved, 42 filed, 42 stories rows, from 42 partners; one partner, Development Consortium, 1 each.

Rollback, each step on Ryan's go:
- The reports, items 17-19, are restored from their copies in Decommissioned (`copy --tag "#79"`,
  made before the change), as Decommissioned (above) says.
- "Partner Report Submission On Time" (`00ORP000005u1WP2AY`), moved to Decommissioned once the
  dashboard no longer uses it, comes back first, before the dashboard, whose `before/` has its one
  component on that report. It is one move in this change's own ledger:
  `python3 tools/sf_report_folders.py undo --vpn-off --dir data/sf_dash_reporting_2026-10-24 --limit 1`,
  whose dry run lists that report alone, then the same with `--apply`. If the dry run lists any
  other move, stop and ask Ryan; he moves the report back to "DHIS2 Reports" by hand in Lightning.
- The dashboard "Reporting" (D5) is dynamic, and the API refuses its copy at the org's limit of 5
  dynamic dashboards (Ryan, 2026-10-24). The dashboard is restored by redeploying it from
  `data/sf_dash_reporting_2026-10-24/before/`, only while a fresh retrieve of it equals `after/`.
- Only the dashboard is deployed from `before/`, check-only first
  (`-m "Dashboard:GLOW_Monthly_Dashboards/DGdiHNHQWRoBNviGBlNWJPnSYqTlMR"`), never the report type
  `Dhis2`, the folders or the "DHIS2 Reports" report it also holds.
- If a fresh retrieve differs from `after/`, stop and ask Ryan. A rollback never deploys an older
  build or an earlier retrieve (DECISIONS 2026-10-16). Nothing is deleted.

### GLOW Club Training

D4 in `glow/sf_keep_list.csv`, the GLOW Club Training dashboard, is the dashboard "Mentors"
(`01ZRP000006quAj2AI`) in "GLOW Monthly Dashboards", with items 12-16 (ticket #78,
[plan](plans/2026-10-25-sf-dash-training.md)). The org's dashboard labelled "GLOW Club Training" is
D3, the GLOW Club Observations dashboard. D4's label and its reports' labels stay as they are
(#70), and each component's title is its report's label. It runs as the specified running user
(`SpecifiedUser`), so it shows the data of its last refresh: a refresh after each change (a PUT,
Ryan's go) and Ryan's weekly Subscribe in Lightning keep it current. #78's build
(`data/sf_dash_training_2026-10-24/build/`) was deployed on 2026-10-26 (deploy
`0AfRP000002i76H0AQ`, the plan's Result): items 13-15 are live on D4, and item 16 joins it after
#77 lands (the plan's step 9). Item 12's component joined D4 on 2026-10-26 (#80, deploy
`0AfRP000002i9BJ0AY`; below).

The measures, each a report in "GLOW Monthly Reports" on the Monthly Report object `DHIS2__c`, and
each component on its own report:
- Item 13, "Number of mentors who attended training": the report
  "Number of mentors trained about module" (`00ORP000004RJZE2A4`, summary) sums
  `DHIS2__c.Mentors_attended_the_training_sessions__c` for each partner and month. The component is a column of the sum for each month. SOQL signal,
  the last complete month:
  `SELECT COUNT(Id), SUM(Mentors_attended_the_training_sessions__c) FROM DHIS2__c WHERE Period__c = LAST_MONTH AND Account__c != null AND (NOT Account__r.Name LIKE '%test%')`.
- Item 14, "Number of training sessions led": the report "Number of training sessions led"
  (`00ORP000004RJZ82AO`, summary) sums `DHIS2__c.how_many_training_sessions_did_you_lead__c` for
  each partner and month. The component is a column of the sum for each month. SOQL signal, the
  last complete month:
  `SELECT COUNT(Id), SUM(how_many_training_sessions_did_you_lead__c) FROM DHIS2__c WHERE Period__c = LAST_MONTH AND Account__c != null AND (NOT Account__r.Name LIKE '%test%')`.
- Item 15, "Whether PC led any training sessions with mentors": the report
  "Leading training sessions with mentors" (`00ORP000004RJZ62AO`, matrix) counts Monthly Reports by the answer to
  `DHIS2__c.Lead_any_training_sessions__c` (Yes or No, across; a blank answer is left out), for
  each partner and month. Each Monthly Report is one partner's month, so its counts are partners.
  The component is a stacked column for each month, Yes and No. SOQL signal, the last complete
  month:
  `SELECT Lead_any_training_sessions__c, COUNT(Id) FROM DHIS2__c WHERE Period__c = LAST_MONTH AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') AND Lead_any_training_sessions__c != null GROUP BY Lead_any_training_sessions__c`.
- Item 16, "Whether PC met with mentors as a group to discuss program implementation": the report
  "Meeting with mentors to discuss program" (`00ORP000004RJZ72AO`, matrix) counts Monthly Reports
  by the answer to `DHIS2__c.Did_you_meet_with_mentors_as_a_group__c` (Yes or No, across; a blank
  answer is left out), for each partner and month, as item 15 does. Its component goes on D4 once
  #77 has taken it off D3 (Ryan, 2026-10-24: #77 lands first); until then item 16's report is as
  #73 left it. SOQL signal, the last complete month:
  `SELECT Did_you_meet_with_mentors_as_a_group__c, COUNT(Id) FROM DHIS2__c WHERE Period__c = LAST_MONTH AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') AND Did_you_meet_with_mentors_as_a_group__c != null GROUP BY Did_you_meet_with_mentors_as_a_group__c`.
- Item 12, "New mentors recruited": the report "Partners that recruited new mentors" (matrix, in
  "GLOW Monthly Reports") counts the Monthly Reports (`DHIS2__c`) by the answer to
  `DHIS2__c.Recruit_any_new_mentors_last_month__c` (Yes or No, across), each in the month of its
  `Period__c`, for each partner and month. The partner is the Monthly Report's `Account__c`, and the
  month is its `Period__c`, the month the report covers. A blank answer is left out, as in items 15
  and 16, and the test-record rule applies. Each Yes is one partner's month, not a number of
  mentors: no Salesforce field holds how many were recruited (Ryan, 2026-10-26). It is not
  `Newly_recruited__c`, the recruits who still need orientation, and not a contact with a "Lead
  Mentor" role, which sits on a household account with no partner. The component is a stacked
  column for each month, Yes and No, in the left half of D4's third row; the second row's right
  half stays free for item 16. SOQL signal, the last 12 months:
  `SELECT Recruit_any_new_mentors_last_month__c, COUNT(Id) FROM DHIS2__c WHERE Period__c = LAST_N_MONTHS:12 AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') AND Recruit_any_new_mentors_last_month__c != null GROUP BY Recruit_any_new_mentors_last_month__c`
  (2026-10-26: 73 Yes, 451 No). Status: deployed 2026-10-26 11:54 UTC on Ryan's go (#80; deploy
  `0AfRP000002i9BJ0AY`, check-only `0AfRP000002i9850AA`), the report `00ORP000009kXev2AE`, read
  back and checked against SOQL month by month; the keep list carries its id
  ([plan and Result](plans/2026-10-26-sf-new-mentors.md#result)).

A partner that filed no Monthly Report for a month has no `DHIS2__c` record for it, so it has no
row in items 15 and 16: a missing response, which the reports keep apart from a No by leaving it
out. Who filed is "Reports completed on time" (item 18, D5).

How the reports read the data:
- Each report is grouped by the partner (`DHIS2__c.Account__c`), then by `Period__c` by calendar
  month; the month is never `CreatedDate`, and a grouping is never also a column.
- The default period is the last 12 months: the report filter `Period__c equals LAST_N_MONTHS:12`,
  which leaves out the current, incomplete month. The standard date filter's column is
  `Period__c`, range All Time, so the field filter sets the period.
- Each report carries the test-record rule as a report filter: `Account is not blank AND Account: Account Name does not contain "test"`
  (#70), in the report XML `DHIS2__c$Account__c` `notEqual` blank and `DHIS2__c$Account__c`
  `notContain` `test` (the lookup matches on the account's name). In the last 12 months the rule
  leaves out 2 of 569 Monthly Reports (2026-10-24; on 2026-10-26 the same, 567 with the rule).
- Items 15 and 16 also keep their filter on a non-blank answer.

The dashboard's only filter is Partner Manager (`DHIS2__c$Account__c.Assigned_Partner_Manager__c`,
its 6 partner managers), on every component (Ryan, 2026-10-24): each manager sees their partners.
It has no Partner or Month filter (Ryan, 2026-10-24); viewers read one partner's month from the
reports' grouping by partner and month. The two tables it had, on the "DHIS2 Reports" reports
"Mentors Discuss Program Implementation" (`00ORP000005uecc2AA`) and "Lead Training Session with
Mentors LastM" (`00ORP000005ufNN2AY`), both on 2025 only, came off it with the deploy. On
2026-10-26, on Ryan's go, `tools/sf_report_folders.py move` moved both reports to Decommissioned
(the plan's step 8); its ledger `data/sf_dash_training_2026-10-24/ledger.csv` holds 3 moves, the
ones the Rollback's step 1 undoes.

For one partner's month, each query takes `AND Account__r.Name = '<partner>'`; for item 14:
`SELECT SUM(how_many_training_sessions_did_you_lead__c) FROM DHIS2__c WHERE Period__c = LAST_MONTH AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') AND Account__r.Name = '<partner>'`
equals that partner's cell for that month in item 14's report.

Rollback, in this order ([plan](plans/2026-10-25-sf-dash-training.md#rollback)):
1. The two "DHIS2 Reports" reports are in Decommissioned since 2026-10-26, and D4 as it was reads
   them, so they go back first: `python3 tools/sf_report_folders.py undo --vpn-off --dir data/sf_dash_training_2026-10-24`
   (the dry run lists 3 moves, last first: the plan's `--limit 1` run moved its first report and
   the full `--apply` run moved that report again, Decommissioned to Decommissioned, and the
   second; the undo puts both reports back in "DHIS2 Reports"), then the same with `--apply` on
   Ryan's go.
2. Then restore from the copies in Decommissioned of the reports and the dashboard, made before
   the deploy by `copy --tag "#78"`; open the copy, then Save As or move it back (Decommissioned,
   above).
3. Or redeploy from this change's retrieve `data/sf_dash_training_2026-10-24/before/` only the
   four components it touched, items 13-15 and D4, and only while a fresh retrieve of those four
   equals `after/`. That fresh retrieve goes into a new folder
   `data/sf_dash_training_2026-10-24/fresh_<date>/` (UTC date), made with
   `mkdir -p fresh_<date>/force-app` and `cp before/sfdx-project.json fresh_<date>/` in
   `data/sf_dash_training_2026-10-24/`. Within that folder:
   `sf project retrieve start -o glow -x ../rollback/package.xml`. A retrieve never goes into
   `before/`, which it would overwrite. Only while that fresh retrieve equals `after/`, within
   `before/`, the check-only
   `sf project deploy start --dry-run -o glow -x ../rollback/package.xml`, then on Ryan's go the
   same without `--dry-run`. The manifest `data/sf_dash_training_2026-10-24/rollback/package.xml`
   lists exactly those four; nothing else that folder holds goes back (not item 16, the two "DHIS2
   Reports" reports, the report types, the `DHIS2__c` fields, nor the folders; DECISIONS
   2026-10-16).

When the fresh retrieve and `after/` differ, someone has changed the dashboard or a report since
the deploy, and the rollback starts from a fresh retrieve by the ritual above. A rollback never
deploys an older build or another change's retrieve (DECISIONS 2026-10-16).

## Interactive dashboard in Salesforce

- **When:** before a change to the interactive dashboard (#81, #82, #83), or to read how it counts.
- **Status:** unchanged by this repo; last modified in the org: the Apex classes 2026-01-04, the LWC bundles 2026-01-13 (`glowTileWeeklyAttendance` 2026-01-22). Retrieved read-only 2026-10-21 (#69).
- **Dry run:** the check-only deploy (`--dry-run`) with the Apex tests.
- **Apply:** the same deploy without `--dry-run`, Ryan's go (VPN off).
- **Verify:** retrieve again and compare with the build.
- **Rollback:** a fresh retrieve first, then the `before/` of that change (DECISIONS 2026-10-16).

The LWC `glowDashboardShell` is the vendor's interactive dashboard on `DHIS2__c`. Its code is not
in git: it lives only in the org, and the read-only retrieve of 2026-10-21 is in
`data/sf_reporting_2026-10-21/before/` (`lwc/`, `classes/`, `staticresources/`, `tabs/`). Each
Apex method, its signature and what it reads: [plan, Inventory](plans/2026-10-21-sf-reporting-inventory.md#inventory).
- **Where it is hosted:** the Lightning tab `Glow_Interactive_Dashboard`, a CustomTab whose
  `lwcComponent` is `glowDashboardShell`; no app lists the tab, and no Lightning page (FlexiPage)
  embeds the LWC (its `isExposed` is `false`).
- **The LWC:** `glowDashboardShell` holds `glowFilterBar`, seven tiles (`glowTileActivity`,
  `glowTileSummits`, `glowTileWeeklyAttendance`, `glowTileMentorOrientation`,
  `glowTileMentorGroup`, `glowTileSessionsObserved`, `glowTileMentorTraining`) and
  `glowRangeBadge`, with shared chart modules on the static resource `chartjs_v280`.
- **The controllers:** `GlowDemoController` gives the filter options (`getFilterOptions`,
  `getDependentOptions`; `getMetrics` is unused) and `GlowTilesController` the tiles (8 methods
  called, 2 unused, 1 commented out). Every method is `public static` and
  `@AuraEnabled(cacheable=true)` in a `with sharing` class, reads `DHIS2__c` and has no DML.
  The tests `GlowDemoControllerTest` and `GlowTilesControllerTest` cover 92.4% and 93.4% and
  assert nothing.
- **Where it counts:**
  - the Partner-Month count is `COUNT()` of `DHIS2__c` rows (`GlowTilesController.cls:156-163`),
    rows rather than distinct partners;
  - there is no majority-across-months logic: the badge is one ratio over the whole range
    (`pct >= 50`, `glowTileActivity.js:26`);
  - the Partner Manager and Partner options are distinct values over every `DHIS2__c` row of any
    date (`GlowDemoController.cls:149-219`);
  - the Partner -> Partner Manager mapping is the account's current
    `Account__r.Assigned_Partner_Manager__c`, applied to every month.
- **A change** (#81, #82, #83) follows the epic's ritual: retrieve live, build in a copy,
  check-only with the Apex tests, Ryan's go, deploy, retrieve `after/` and compare; never an edit
  directly in the org.

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

### Re-send of the corrections failed as "Duplicate" (`resend`)

- **When:** corrected re-submissions the processor failed whole as `Duplicate` before 2026-10-24
  (it merges a correction since: ticket #108); their girls are missing from that club and day.
- **Status:** built 2026-10-24 (ticket #109, [plan](plans/2026-10-24-resend-duplicate-batches.md)); the live run waits for Ryan's go.
- **Dry run:** `python3 tools/sf_backfill.py resend --vpn-off` (it reads Salesforce, so `--vpn-off` too).
- **Apply:** `resend --apply --vpn-off --limit 1`, read back, then the rest, Ryan's go.
- **Verify:** every copy is read back as it is sent; `sf_backfill.py status`.
- **Rollback:** by id from `resend_ledger.csv` and `resend_added.csv` (below).

`resend` reads every `Failed` batch whose message starts `Duplicate:` created since `--since`
(default 2026-09-07), in `CreatedDate` order, and predicts in memory, by the processor's merge rule,
what a copy of it would add to the day's original batch (the oldest `Success`): the girls it ticked
without a row on that club and day, and how many of them get a new contact. Each candidate prints
one line - the failed batch, the original, the club, the date, names ticked / girls to add / new
contacts - then the totals, a line per club and `skipped, <reason>: N`: `no_success_original`,
`original_not_mergeable` (a `Partner report` or no rows of its own), `module_differs`, `no_names`,
`fuzzy_matching` (`enable_fuzzy_matching__c` true: the processor would match the names by edit
distance, which the exact-match prediction cannot follow), `adds_nobody`, `own_batch` (a copy of
this tool), `already_resent` (in the ledger, whatever the outcome). A skipped batch is counted,
never listed and never sent; `--only` on it refuses with `skipped, <reason>`. Corrections of one
club and day are predicted in order, each after the earlier ones.
Girls' names are compared inside the script; it prints counts, club names, dates and ids only.

`--apply` sends one copy per request, in that order: the failed batch's fields as they are, with
`Creator__c` `Jotform back-fill re-send <failed id>` (its marker; the copy gets no `Submitted_At__c`).
Before each copy it reads the club and day again and refuses when the prediction changed (a live
correction got there first); after it, it reads back that the copy is `Success` `merged into
<original id>` with no rows or count of its own, that the original gained exactly the predicted
rows and the club exactly the predicted contacts (the rows and contacts written inside the copy's
window: `CreatedDate` from the copy's `CreatedDate` to its `LastModifiedDate`, the processor's
status update and its last write, since nothing promises one timestamp for the whole
transaction; a live correction merged into the same original after the window is neither counted
nor listed for the copy's rollback), and that the original's `Girls_Present__c` is
its rows - else the copy is `CHECK` and nothing more is sent until it is closed (`close <failed
id> --removed` or `--accepted`). Another batch of the club and day created inside the window is
`CHECK` too: its rows cannot be told from the copy's by time, so the window's rows and contacts
are listed with `uncertain` `yes`. When the CHECK's rollback list may be incomplete (another
batch in the window, or fewer rows or contacts in it than predicted or than the original and the
club grew by) the message says so instead of "listed by id": find the copy's rows by hand before
removing anything. A lost answer is `unknown` and settled by the marker before the
next `--apply` sends anything. `--only <failed id>` sends one (refused while an earlier correction
of its club and day is not re-sent), `--limit N` the first N. The original Failed batches stay as
they are (history); a failed batch is never copied twice.

- **Rollback** (only with Ryan's go): `resend_added.csv` lists, per copy, every attendance row it
  added to the original and every contact it created. Delete those rows, then each listed contact
  only while it carries no other attendance row (master-detail: deleting a contact deletes its
  rows), then the copies (`batch_id` in `resend_ledger.csv`); set each original's
  `Girls_Present__c` back to the count of its own rows (`tools/sf_girls_present.py check`), and
  `close <failed id> --removed` for each.

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
  credentials log in as Ryan's own Salesforce user) and the variable `SF_SYNC`
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
