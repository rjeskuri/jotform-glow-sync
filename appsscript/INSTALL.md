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

1. Open the enrollment spreadsheet (the one with the "Form Responses 1" tab).
2. **Extensions → Apps Script**. A code editor opens in a new tab.
3. Delete the empty `Code.gs` that Google creates.
4. For each file in this folder — `Config.gs`, `Normalize.gs`, `Ids.gs`,
   `Roster.gs`, `Menu.gs` — click **+ → Script**, name it exactly as the file
   is named here (Google adds the `.gs` itself), and paste the contents in.
5. Click **Save** (the disk icon).
6. Reload the spreadsheet tab. A **GLOW** menu appears next to Help.

## First run

1. **GLOW → Set up tabs** — creates Roster, Partners, ClubRegistry,
   ReviewQueue and Audit. Google will ask you to authorize the script the
   first time; it only ever touches this spreadsheet.
2. **GLOW → Rebuild roster from enrollment responses** — reads every
   enrollment response and fills the Roster tab. On the current data this
   produces **328 clubs and 6,210 girls**, each with a unique ID, and takes a
   minute or two.
3. Open the **Partners** tab and fill in the **region** for each of the 47
   partners (Africa / Asia / Latin America / U.S). Regions decide which
   attendance form each club appears on from Phase 4; clubs whose partner has
   no region are flagged, never silently dropped.
4. Open the **ReviewQueue** tab. Expect around 16 entries about the same girl's
   name appearing twice in a roster. Fix those in the sheet (give the girls
   something that tells them apart, e.g. `Anh Nguyen (A)`), then run the
   rebuild again.

Re-running the rebuild is always safe: existing girls keep their IDs, only new
names get new ones.

## About the IDs

`DEMOCLUB-SAMPLE-001` = club code, surname, and a number that makes same-surname
girls distinct.

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
  json.dump([f'{p.lower()}||{c.lower()}' for p,c in sheet], open('/tmp/py_clubs.json','w'))"
node test/parity_test.js
```

Run it after any change to the shared logic in either language.
