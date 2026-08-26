# GLOW Attendance Form Sync

Keeps the Jotform Attendance Form in sync with the club enrollment Google
Sheet. The sheet is the single source of truth; this tool makes the form match
it — rosters and all conditional logic — in one command.

## Scripts in this repo

| Script | What it does |
|---|---|
| `sync_attendance_form.py` | The main tool: makes a form match the enrollment sheet |
| `backup_forms.py` | Snapshots every form's questions + properties into `backups/` |
| `restore_conditions.py` | Rolls a form's conditional logic back to a snapshot |
| `appsscript/` | Scripts that live in the Google Sheet — see `appsscript/INSTALL.md` |
| `tools/derive_partner_regions.py` | Works out each partner's region from the regional forms; regenerates `appsscript/Regions.gs` |
| `test/parity_test.js` | Checks the Sheet scripts and the Python tool agree |

**Always run `backup_forms.py` before changing a live form.** Restores are
proven working (rehearsed 2026-08-24 on the working copy): `restore_conditions.py
--form <ID>` previews, `--apply` restores. It touches only the conditions —
questions, emails, and the Salesforce integration are left alone.

## What it manages

| Form piece | Driven by |
|---|---|
| One hidden roster checkbox question per club | Sheet: Club Name + girls list |
| Roster visibility rules (`clubName == X → show roster`) | Sheet club names |
| Partner disambiguation (two partners, same club name) | Sheet partner column |
| Curriculum cascade (Year → Module → Session dropdown) | `SESSION_OVERRIDES` table in the script + the module dropdowns' live options |
| Salesforce bridge (`Contact_IDs`, `Module_ID`, `Week_ID`, `Year_ID`) | generated automatically |

It does **not** touch: the static header fields, the Session dropdowns'
options, email notifications, or any question it does not recognize as a
club roster.

## Usage

```bash
export JOTFORM_API_KEY=...   # a full-access key for the account

# 1. In Google Sheets: File > Download > .csv on the enrollment responses tab
# 2. Preview what would change (writes nothing):
python3 sync_attendance_form.py enrollment.csv --form <FORM_ID>

# 3. Apply:
python3 sync_attendance_form.py enrollment.csv --form <FORM_ID> --apply
```

Typical output:

```
Sheet: 220 clubs (4813 girls total)
DRY RUN (use --apply to write):
  - CREATE roster 'New Hope Club' (22 girls)
  - UPDATE roster 'San Carlos' (q120, 51 girls)
  - REPLACE conditions (250 rules)
```

## Routine tasks

- **New enrollment submissions / roster changes:** re-export the CSV, dry-run,
  apply. New clubs get a question + rules automatically; changed rosters are
  updated in place (submission history for other clubs is untouched because
  existing question IDs never change).
- **Curriculum changes** (module added/renamed, or a module's session count
  changes): edit the module dropdown options in the Jotform builder and/or the
  `SESSION_OVERRIDES` table at the top of the script, then re-run. The cascade
  rules are regenerated from those two sources.
- **Two partners with the same club name:** handled automatically — the form
  asks for the Partner and shows the right roster. The partner value comes
  from the sheet (or, for pre-existing clubs, from the form's current rules).

## Safety properties

- Dry run by default; `--apply` is required to write anything.
- Existing roster questions are updated, never deleted; clubs that are on the
  form but missing from the CSV are kept and warned about.
- Conditions are regenerated wholesale from scratch every run — there is no
  rule drift, and the builder's Revision History remains the rollback path.
- The script exits with an error instead of guessing when it meets an
  ambiguity it cannot resolve (e.g. a duplicate club name with no partner
  information anywhere).

## How the conditional logic is organized

Every run writes three cleanly-separated groups of rules, in order:

1. **Roster visibility** — one rule per club, `IF clubName equals "<club>"
   SHOW <roster>`; ambiguous names additionally require the Partner match,
   plus one rule that reveals the Partner box.
   (Jotform's `equals` is case-insensitive and trims outer whitespace, so
   mentors' typing is matched forgivingly.)
2. **Curriculum cascade** — `Year → Module dropdown`, `Year + Module →
   Session dropdown` (8, 10, 14, or 15 sessions).
3. **Salesforce bridge** — copies of year/module/session into the hidden
   `Year_ID` / `Module_ID` / `Week_ID` fields, plus ONE aggregate
   `Contact_IDs` calculation that concatenates all rosters with
   "ignore hidden fields" on, so exactly the visible club's ticked names come
   through (this replaced 219 near-identical per-club rules).

## Field IDs

The script pins the master form's structural question IDs near the top
(`CLUB_NAME = 5`, `PARTNER = 331`, week/module dropdown ids, hidden bridge
ids). If the form is ever rebuilt, update those constants — everything else
is discovered live via the API.
