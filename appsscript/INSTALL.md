# The Apps Script in the master enrollment spreadsheet

These scripts live *inside* the master enrollment Google Sheet, so there is no
server to run and nothing to keep switched on. They mint the permanent girl
IDs, keep the Roster tab, generate and handle the two Google Forms, and tell
the automatic Jotform sync when the Roster changed.

## Deploy with clasp (the normal way)

`clasp` pushes the whole `appsscript/` folder into the sheet's script project
with one command — every later change too. The repo pins clasp 2.4.2, which
runs on Node 18 (clasp 3 needs Node 20); `npm install` fetches it. The npm
scripts `clasp:push` and `clasp:open` refuse to run on any other Node ("clasp
2.4.2 needs Node 18"): `nvm use 18` first — the Mac's default Node is newer.

One-time, with you at the keyboard (clasp signs in as *your* Google account —
the forms and triggers the script creates belong to you):

1. `npm install`, then `npx clasp login`: a browser tab opens; pick the
   account that owns the master enrollment sheet; allow. The token lands in
   `~/.clasprc.json`, never in the repo.
2. Turn on the Apps Script API for your account:
   <https://script.google.com/home/usersettings> → **Google Apps Script API → On**.
3. Get the script's ID: open the sheet → **Extensions → Apps Script** → ⚙
   **Project Settings** → copy **Script ID**. Put it in `appsscript/.clasp.json`
   (gitignored):

       {"scriptId": "<SCRIPT_ID>", "rootDir": "."}

4. `make gs` (every file parses — a broken file breaks every form handler;
   only the 8 pinned Google services are used, so the push adds no OAuth
   scope; every function called exists), then `nvm use 18` and `npm run
   clasp:push` (that is `clasp push -f` inside `appsscript/`; `.claspignore`
   limits the push to `*.gs` and `appsscript.json`). Reload the sheet: the
   **GLOW** menu appears next to Help.

Edit the `.gs` files in the repo, run `make check`, push — never edit in the
online editor; the next push would overwrite it. Inside Claude Code the push
is gated by `.claude/hooks/live_gate.sh` (`docs/RUNBOOK.md`, "Live gate"), and
Ryan can run it with Claude through the user-only `/deploy-appsscript` skill
(`docs/RUNBOOK.md`, "Apps Script deploy").

### Fallback: paste by hand

**Extensions → Apps Script**, delete the empty `Code.gs`, then for each file
here — `Config.gs`, `Normalize.gs`, `Ids.gs`, `Regions.gs`, `RosterOps.gs`,
`Roster.gs`, `Forms.gs`, `FormHandlers.gs`, `Menu.gs`, `Dispatch.gs` — click
**+ → Script**, name it exactly as the file (Google adds `.gs`), paste, Save.
Reload the spreadsheet.

## First run

1. **GLOW → Set up tabs** — creates Roster, Partners, ClubRegistry,
   ReviewQueue, Audit and SyncLog. Google asks you to authorize the script
   the first time. It asks for more than the spreadsheet because of the
   forms and the sync notification: creating Google Forms in your Drive,
   sending email from your account (mentor confirmations, problem reports,
   the weekly digest), managing the script's own triggers, and connecting
   to an external service (GitHub). It never reads anything else. **Adding a
   Google service to a `.gs` file later grows the scope set, and until you
   re-authorize, the form-submit trigger fails hard — submissions arrive but
   are not processed.** After any push that adds a service, run a GLOW menu
   item at once, accept the prompt, then **Process any missed form
   responses** and read its preview: it should list only what arrived since
   the push, plus any earlier failure shown as `retry after ERROR`
   (`docs/RUNBOOK.md`, "Missed form responses").
2. **GLOW → Rebuild roster from enrollment responses** — reads every
   enrollment response and fills the Roster tab (on the launch data: 328
   clubs and 6,210 girls, a minute or two). Before launch, re-running was
   safe: existing girls keep their IDs, only new names get new ones. **Since
   launch (2026-09-01) do not re-run it.** It reactivates girls removed
   through the Club Roster Form and re-creates renamed or moved clubs under
   their old name or partner (`docs/RUNBOOK.md`, "Roster rebuild and upload").
   Once the 2026-10-09 code is pushed, the item says so in a YES/NO dialog
   first and does nothing unless you answer YES; from the script editor it
   refuses.
3. Open the **Partners** tab. The **region** column (Africa / Asia / Latin
   America / U.S) is prefilled from `Regions.gs`, a map derived before launch
   from which regional attendance form each partner's clubs sat on (the
   script that derived it is retired, and the map is hand-kept data now:
   [Retired tools](../docs/ARCHITECTURE.md#retired-tools)). The **notes**
   column says how solid each one is; a row whose note starts with **PLEASE
   CONFIRM** or says **region needed** is worth a look. Correct it here — the
   tab always wins over the map — then **GLOW → Refresh regions from the
   Partners tab**. A partner with no region lands in the ReviewQueue, and its
   girls reach no attendance form until the region is filled in.
4. Open the **ReviewQueue** tab: one row per question the scripts could not
   decide (a removal that matched nobody, a name listed twice, a partner with
   no region, a problem report asking for a roster change, …). Ryan owns it;
   the Monday e-mail lists what is open. Work it as `docs/RUNBOOK.md`,
   "Working the ReviewQueue" says (e.g. two girls with one name: add the
   second as `Jane Doe (B)`), and close each row with
   `resolved <date> by <name>: <what was done>`. Never delete a row, and
   never fix an item with the rebuild (step 2).

## The Google Forms

**GLOW → Google Forms → Create the Google Forms** builds, in your Drive:

| Form | Who uses it | What happens on submit |
|---|---|---|
| **Club Roster Form** | partners and mentors | Page 1 asks *what would you like to do?* and jumps to the right section. **Enroll a NEW club**: partner (a "not listed" choice asks for the organization's name), club, roster, mentor → club + girls go into the Roster with IDs, the club is added to **SF Pending**, anything odd goes to the ReviewQueue — unless it may duplicate a club already on file (names already in one club, a close club name, a typed organization close to a partner on file, or a re-enrollment with another list), or its club name is one another partner's club already has: then nothing is imported, it is **held** for staff (a ReviewQueue item, FormLog `HELD: …`) and the mentor is told it is being checked. **Add or remove girls**: partner → only that partner's clubs → ADD / REMOVE lists → girls are added, reactivated (never by a response sent before their removal: they stay removed and the ReviewQueue says so), or marked inactive, **never deleted**; names that match nobody are queued for staff with "closest name" hints; the mentor gets a confirmation email echoing only the names they typed |
| **Something isn't working?** | anyone | one-minute problem report (its description sends roster changes to the Club Roster Form; a reply address is optional), emailed to staff; one that asks for a roster change, or says the form is not working, also becomes a ReviewQueue item |

The run installs the triggers and shows both links (again via **Show form
links**). Run again, it reuses both forms; if a saved form id does not open
(another Google account, a Forms outage) it creates nothing and says so —
new forms would leave the live forms' responses unprocessed. Responses land
in *Roster Form Responses* and *Feedback*; *FormLog* records what was done
with each.

Then, in **Project Settings → Script Properties**:

- `STAFF_NOTIFY_EMAIL` — receives problem reports and the Monday e-mail:
  the open ReviewQueue items and the clubs pending in Salesforce, each with
  the exact account name to create — the club name, or `<club> - <partner>`
  when another partner's club has the same name (sent only when there is
  something to report).
- `SYNC_DISPATCH_REPO` and `SYNC_DISPATCH_TOKEN` — switch on the automatic
  Jotform sync (`docs/RUNBOOK.md`, "Automatic sync"); unset, the sheet sends
  nothing. Test with **GLOW → Google Forms → Request Jotform sync now**.

And put the problem-report and Club Roster Form links on the attendance forms
(`tools/add_feedback_link.py`, see `docs/RUNBOOK.md`, "Links above Submit").

Things to know:

- The form dropdowns are refreshed from the Roster after every submission,
  every hour (`syncFormChoicesHourly`, installed by `installTriggers`; it skips
  quietly when the lock is busy and writes an Audit row only when a dropdown
  changed) and, for at once, by **Update form dropdowns from the Roster**. A brand-new partner
  (enrolled via "not in this list") gets its own club section automatically.
  Once the 2026-10-09 code is pushed, the menu item takes the document lock
  as the handlers do (busy: a "try again" message), and **Create the Google
  Forms**, when the lock is busy, stops before installing the triggers and
  says to run it again (it reuses the forms).
- Free text from the Club Roster Form never reaches the sheet as a formula:
  a leading `=`, `+`, `-` or `@` is stripped (`Normalize.gs sheetText_`).
  A girl's name loses only that leading run, so it still matches her Roster
  spelling; her last word, filed on its own as `last_name`, is stripped too
  (`RosterOps.gs newRosterRow_`).
- A held new club stays held until staff start its ReviewQueue item's
  `resolved` cell with `release`; **Process any missed form responses**
  then imports it (`docs/RUNBOOK.md`, "Working the ReviewQueue"). One held
  because another partner's club has its name is released only once the
  response row's `Club name` cell has a name nobody else uses.
- If a trigger ever fails (quota, timeout, an incomplete submission), nothing
  is lost: FormLog records `ERROR: …`, the ReviewQueue gets a line, and
  **Process any missed form responses** lists every response that has not
  succeeded yet and runs the ones you confirm (responses more than a week
  old only after a second YES; see `docs/RUNBOOK.md`, "Missed form
  responses").
- Edit wording and help text in the Forms UI freely, but keep the question
  **titles** as they are — the handlers find answers by title (`Config.gs Q`).
  The generated wording lives in `Forms.gs` `WORDING`. Forms created before
  2026-09-28 get it once through **Update the forms' wording (one-time;
  shows the changes first)**: it lists every change and asks, and leaves any
  text edited by hand as is (`docs/RUNBOOK.md`, "Google Forms wording").
- Every Roster change writes an Audit row; when the sync notification is
  configured it also writes `syncRequested … → HTTP 204`, and the runner's
  outcome appears in **SyncLog**.

## About the IDs

`DEMOCLUB-SAMPLE-001` = club code, surname, and a number that makes
same-surname girls distinct. **Permanent** (a rename or a split never changes
it), **a stale-looking club code is fine** (the ClubRegistry tab is
authoritative), **numbers are never reused** (a girl who leaves keeps her
number retired). Removing a girl sets her status to `inactive` and stamps the
date; her row, her ID and every Salesforce record stay as they were.

## Testing the logic without the spreadsheet

`make check` runs the pure `.gs` files in Node against a synthetic fixture
(and against the real export when `data/enrollment_2026-08-24.csv` exists)
and checks they agree with the Python tool; it also parses every `.gs` file.
`test/forms_logic_test.js` covers the roster-change decisions,
`test/dispatch_test.js` the sync notification. Run it after any change to
the shared logic in either language. With a real export, the parity check
also wants every partner in it to have a `Regions.gs` entry. A partner
missing there gets its region in the Partners tab, which wins; add it to
`Regions.gs` by hand only for a partner the tab lacks, with its
`PARTNER_REGION_NOTES` line (Ryan's edit: the edit hook keeps Claude out of
that file). Nothing regenerates it any more.
