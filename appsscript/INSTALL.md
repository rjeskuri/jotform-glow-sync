# Installing the GLOW scripts in the enrollment spreadsheet

These scripts live *inside* the enrollment Google Sheet, so there is no server
to run and nothing to keep switched on. Installing takes about ten minutes and
only needs doing once.

## What Phase 1 gives you

A **Roster** tab: one row per girl, each with a permanent ID like
`DEMOCLUB-SAMPLE-001`. That tab becomes the thing everything else reads —
today the Python sync tool, and from Phase 2 the attendance forms directly.

Nothing outside the spreadsheet changes yet. This step cannot affect Jotform
or Salesforce.

## Install

1. Open the **master enrollment** spreadsheet (the new one-row-per-girl sheet;
   its *Enrollment Responses* tab is a one-time import of the original
   enrollment form's responses).
2. **Extensions → Apps Script**. A code editor opens in a new tab.
3. Delete the empty `Code.gs` that Google creates.
4. For each file in this folder — `Config.gs`, `Normalize.gs`, `Ids.gs`,
   `Regions.gs`, `RosterOps.gs`, `Roster.gs`, `Forms.gs`, `FormHandlers.gs`,
   `Menu.gs` — click **+ → Script**, name it exactly as the file is named
   here (Google adds the `.gs` itself), and paste the contents in.
5. Click **Save** (the disk icon).
6. Reload the spreadsheet tab. A **GLOW** menu appears next to Help.

## First run

1. **GLOW → Set up tabs** — creates Roster, Partners, ClubRegistry,
   ReviewQueue and Audit. Google will ask you to authorize the script the
   first time. It asks for more than the spreadsheet because of the forms
   step below: creating Google Forms in your Drive, sending email from your
   account (mentor confirmations, problem reports, the weekly digest) and
   managing the script's own triggers. It never reads anything else.
2. **GLOW → Rebuild roster from enrollment responses** — reads every
   enrollment response and fills the Roster tab. On the current data this
   produces **328 clubs and 6,210 girls**, each with a unique ID, and takes a
   minute or two.
3. Open the **Partners** tab. The **region** column (Africa / Asia / Latin
   America / U.S) is already filled in for all 47 partners — it was worked out
   from which regional attendance form each partner's clubs currently sit on
   (`tools/derive_partner_regions.py`; the map lives in `Regions.gs`). The
   **notes** column says how solid each one is; any row whose note starts with
   **PLEASE CONFIRM** is worth a second look. If anything is wrong, correct it
   in this tab — the tab always wins over the derived map — then run
   **GLOW → Refresh regions from the Partners tab**. Regions decide which
   attendance form each club appears on from Phase 4; a partner with no region
   lands in the ReviewQueue, never silently dropped.
4. Open the **ReviewQueue** tab. Expect around 16 entries about the same girl's
   name appearing twice in a roster. Fix those in the sheet (give the girls
   something that tells them apart, e.g. `Anh Nguyen (A)`), then run the
   rebuild again.

Re-running the rebuild is always safe: existing girls keep their IDs, only new
names get new ones.

## The Google Forms (Phase 3)

Once the Roster tab exists, **GLOW → Google Forms → Create the Google Forms**
builds, in your own Google Drive:

| Form | Who uses it | What happens on submit |
|---|---|---|
| **Club Roster Form** | partners and mentors | Page 1 asks *what would you like to do?* and jumps to the right section (Google Forms calls these "sections"; they behave like pages). **Enroll a NEW club**: partner (a "not listed" choice asks for the organization's name), club, roster, mentor → club + girls go into the Roster with IDs, the club is added to the **SF Pending** tab, anything odd goes to the ReviewQueue. **Add or remove girls**: partner → only that partner's clubs (no 300-item dropdown) → ADD / REMOVE lists → girls are added, reactivated, or marked inactive, **never deleted**; names that match nobody are queued for staff with "closest name" hints, never guessed; the mentor gets a confirmation email echoing only the names they typed |
| **Something isn't working?** | anyone | one-minute problem report, emailed to staff |

The run also installs the triggers and shows both links (again later via
**Show form links**). Responses land in the tabs *Roster Form Responses* and
*Feedback*; *FormLog* records what was done with each.

Then:

1. **Script Properties** (Project Settings → Script Properties): add
   `STAFF_NOTIFY_EMAIL` = the address that should receive problem reports and
   the Monday "clubs pending in Salesforce" digest.
2. Put the feedback link at the bottom of the attendance forms (a one-line
   text element above Submit, easy to remove later):

       export JOTFORM_API_KEY=...
       python3 tools/add_feedback_link.py --url <feedback form link>          # preview
       python3 tools/add_feedback_link.py --url <feedback form link> --apply
       python3 tools/add_feedback_link.py --remove --apply                    # later

3. When you are ready to stop using the original enrollment form, ask its
   owner to close it (Responses → "Accepting responses" off) with a message
   pointing at the two new links. (The **Retire the old enrollment form**
   menu item only works when the old form feeds this spreadsheet, which it
   does not — the original sheet stayed with its owner.)

Things to know:

- The dropdowns are refreshed from the Roster after every submission and by
  **Update form dropdowns from the Roster**. A brand-new partner (enrolled via
  the "not in this list" option) gets its own club section automatically.
- If a trigger ever fails (Google quota, a timeout, an incomplete
  submission), nothing is lost: FormLog records it as `ERROR: …`, the
  ReviewQueue gets a line, and **Process any missed form responses** retries
  every response that has not succeeded yet. (Problem reports that arrive
  before `STAFF_NOTIFY_EMAIL` is set are sent by that same menu item once it
  is.)
- You can edit wording and help text in the Forms UI freely, but keep the
  question **titles** as they are — the handlers find answers by title.

## About the IDs

`DEMOCLUB-SAMPLE-001` = club code, surname, and a number that makes
same-surname girls distinct.

- **Permanent.** Once assigned, a girl's ID never changes — not when her club
  is renamed, not when the club splits, not if she leaves and comes back.
- **A stale-looking club code is fine.** The ID is a label, not a description;
  the ClubRegistry tab is what makes it authoritative.
- **Numbers are never reused.** A girl who leaves keeps her number retired, so
  a historical record can never end up pointing at a different person.

## Nobody is ever deleted

Removing a girl sets her status to `inactive` and stamps the date. Her row,
her ID, and every Salesforce record that references her stay exactly as they
were. She simply stops appearing on the attendance form.

## Testing the logic without the spreadsheet

`test/parity_test.js` runs the same normalization and ID code against the real
enrollment CSV and checks it agrees with the Python tool:

```bash
cd ~/jotform-glow-sync
python3 -c "import importlib.util,json; \
  spec=importlib.util.spec_from_file_location('s','sync_attendance_form.py'); \
  m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); \
  sheet,_=m.read_sheet('data/enrollment_2026-08-24.csv'); \
  json.dump([f'{p.lower()}||{c.lower()}' for p,c in sheet], open('data/py_clubs.json','w'))"
node test/parity_test.js
```

(`data/` is gitignored and not world-readable, unlike `/tmp` — club names
occasionally turn out to be a girl's name.)

Run it after any change to the shared logic in either language. It also
fails if a partner in the CSV has no entry in `Regions.gs` — the fix is
`python3 tools/derive_partner_regions.py <csv> --write` (it needs fresh
regional-form snapshots in `backups/`, from `backup_forms.py`).
