# Launch: what goes out, what is ready, what is still on you

_Last updated 2026-08-27. The four regional Jotforms below were built today
by cloning the upgraded template and syncing each from the **Roster** tab of
the master enrollment sheet, keeping only that region's clubs. Africa stays
one form._

## Links to hand over

### Attendance forms (Jotform) — new links, ready for mentors

| Region | Link for mentors | Clubs | Girls | Rules | Notes |
|---|---|---|---|---|---|
| Africa | https://form.jotform.com/262382821971058 | 204 | 3,923 | 237 | one form, not split; was 428 rules with 6 broken |
| Asia | https://form.jotform.com/262383129464057 | 85 | 1,435 | 113 | |
| Latin America | https://form.jotform.com/262383455778067 | 31 | 760 | 59 | |
| U.S | https://form.jotform.com/262382706852058 | 12 | 176 | 40 | |

Every one of them has: current rosters from the Roster tab, zero
error-flagged rules, the Salesforce integration (identical mapping inherited
from the template), the mentor confirmation email, sessions named "Session 1…",
`enable_fuzzy_matching` sending `false` instead of blank, and the **same ten
languages as before** (English, Español, Thai, Urdu, Telugu, Français,
Vietnamese, Nepali, Khmer, Swahili — the API clone had reset the language
switcher to English-only; restored 2026-08-27 afternoon, `tools/restore_translations.py`). These links are
current as of 2026-08-27 (re-verified: each resolves, is ENABLED, and its
browser-tab title now matches the form name — the clones had inherited a
"Clone of Clone of …" page title, fixed the same day). No "publish" step
exists on Jotform: an ENABLED form is live.

The old forms are still online but retitled **"… (defunct)"** in Jotform
(`260703905772560` Africa, `260704198384564` Asia, `260704170003542` Latin
America, `260703912140547` U.S, `260555608160556` master). They keep their
submission history. **Disabling them is a separate step** (see below) — do it
once the new links are in partners' hands.

### Google Forms — created by you in the master enrollment sheet

Paste the 9 files from `appsscript/` into the sheet's Apps Script, then
**GLOW → Google Forms → Create the Google Forms**. The script shows both
links (again any time via **Show form links**). Fill them in here:

| Form | Link for partners / mentors |
|---|---|
| Club Roster Form (enroll a new club / add or remove girls — one form, page 1 picks) | https://docs.google.com/forms/d/e/1FAIpQLScPO9Dizjl9G8krMcvs1sVnqYku3k8dB7Ycv-1VahgPDssMzQ/viewform |
| Something isn't working? | https://docs.google.com/forms/d/e/1FAIpQLSeYx286-Bre0aSOWnhEDgC4_6FjGyPssldLA3J5WzIeK8cKCA/viewform |

Created 2026-08-27; both forms have since been renamed in the Forms UI to
**"Global Catalyst – Club Roster Form"** and **"Global Catalyst – Something
isn't working?"** — the links above are unchanged (renaming a Google Form
never changes its URL). Edit links (owner only): Club Roster Form
`https://docs.google.com/forms/d/1mFIEtvUApiCgzjmv3sPEfZZxC82krwI-Memel3mhEJM/edit`,
problem report `https://docs.google.com/forms/d/1iglohAbPiyyvjPhZECtnF0sgzeoZIGOexKiHI8vsQ80/edit`.
Responses land in the sheet tabs *Roster Form Responses* and *Feedback*.

## Is it ready? — the thumbs-up checklist

1. **One real submission on the new Africa form** (any club; WESAD's
   *Luminary Sisters* is a good choice — they tested on the old form on
   2026-08-26 and it came through cleanly: 14 girls in `contact_ids`, all
   three bridge fields filled, `enable_fuzzy = false`).
2. **Check Salesforce**: `Attendance_Batch__c` gets a record with the club as
   `Account_Name__c`, the ticked names in `Contact_IDs__c`, `Module_Week__c`
   = the session number, `Module__c` / `Module_Year__c` filled. If that
   record appears, the integration survived the clone — the mapping is
   byte-identical, so the other three forms will behave the same.
3. **Mentor email arrived** (the confirmation goes to the address typed in
   the form).
4. Then: thumbs up, send the four links.

Things that are true today and fine for launch but on the backlog
(`docs/BACKLOG.md`):

- Africa is heavy (3,923 girl checkboxes) — it works, it is just slow to
  load on weak connections. Same as before; fewer rules than before.
- Seven rosters (the ones with a duplicate name in the original enrollment)
  now list each name once; the second girl appears once the duplicate is
  resolved in the sheet (`data/needs_attention_*.csv`).
- Otra Cosa's split clubs and the "Setidevi … Sokhel" spelling variant exist
  as both old and new questions; the mentor's typed club name decides which
  roster shows. Harmless; to be cleaned up.

## After the thumbs-up

- **Problem-report link on the attendance forms** — once the feedback Google
  Form exists:

      export JOTFORM_API_KEY=...
      python3 tools/add_feedback_link.py --url <feedback form link>          # preview
      python3 tools/add_feedback_link.py --url <feedback form link> --apply

- **Disable the defunct forms** (they stop accepting responses and show a
  "this form has moved" message with the new link). Say the word and it is
  one command per form; or in Jotform: form → Settings → Form Status →
  Disabled, with a custom message.
- **Old enrollment Google Form**: ask its owner to close it with a message
  pointing at the two new forms.

## How the regional forms are maintained from now on

Until Phase 2 (automatic hourly sync) is built, a roster change reaches the
attendance forms with three commands, run by whoever has the Jotform key:

    python3 tools/sheets_client.py export Roster data/roster_<date>.csv
    python3 tools/form_status.py                                         # what differs?
    python3 sync_attendance_form.py data/roster_<date>.csv --roster --region Africa --form 262382821971058 --apply
    # (same for Asia 262383129464057, "Latin America" 262383455778067, U.S 262382706852058)

Never `--prune` a live form (it refuses anyway once a form has submissions).
`backup_forms.py` before, `restore_conditions.py` if anything looks wrong.
