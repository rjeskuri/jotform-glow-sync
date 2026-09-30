"""The enrollment/Roster parsers and the structural question ids.

Moved verbatim from sync_attendance_form.py (which imports them back) so the
other tools stop dynamic-loading that script with importlib. The Apps Script
side carries the same logic in appsscript/Normalize.gs and the same ids in
appsscript/Config.gs; test/parity_test.js and test/python_test.py keep the
two sides honest. Known divergences: docs/ARCHITECTURE.md.
"""
import csv
import html
import re
import sys
from collections import defaultdict

from glow.text import key

# ---------------------------------------------------------------- sheet layout
# Column headers in the enrollment sheet (matched loosely, case-insensitive).
COL_PARTNER = "partner organization name"
COL_CLUB = "club name"
COL_ROSTER = "please list the full name"

# ------------------------------------------------------------- fixed field ids
# Structural fields of the master form. If the form is ever rebuilt from
# scratch, update these ids (GET /form/{id}/questions to look them up).
CLUB_NAME = "5"      # Club Name textbox (Salesforce Account_Name__c reads it)
PARTNER = "331"      # Partner textbox. With the Club picker it is hidden once no rule shows it
                     # (a club name two partners share is its own picker entry, SF_NAME_SEP
                     # below) and only the staff notification e-mail reads it; without the
                     # picker it is typed, and shown for an ambiguous club name
YEAR = "94"          # GLOW Club Year dropdown (1|2|3)
MODULES = {"1": "14", "2": "92", "3": "93"}       # year -> module dropdown qid
WEEKS = {8: "15", 10: "95", 14: "96", 15: "97"}   # session count -> dropdown qid
CONTACT_IDS, MODULE_ID, WEEK_ID, YEAR_ID = "18", "98", "100", "102"

# The Club picker question is recognised by this Jotform field name on every
# side (created by sync_attendance_form.py --club-picker, audited by
# tools/form_status.py).
PICKER_NAME = "clubPicker"

# The partner list (docs/plans/2026-09-28-partner-box.md) was built, never
# deployed, and is RETIRED (2026-09-30, docs/plans/2026-09-30-same-name-clubs.md):
# the sync refuses --partner-picker and a form carrying one. The name stays so
# that refusal, the audit and the other tools still recognise such a question;
# the rest of the partner-list code is dead and waits for its clean-up
# (docs/BACKLOG.md).
PARTNER_PICKER_NAME = "partnerPicker"


def partner_picker(questions):
    """qid of the partner list, or None while the form has only the typed box."""
    return next((qid for qid, q in questions.items()
                 if q.get("type") == "control_dropdown" and q.get("name") == PARTNER_PICKER_NAME),
                None)


def partner_fields(questions):
    """The fields a partner-gated rule may test: the typed box (q331) and,
    once the form has it, the partner list."""
    pp = partner_picker(questions)
    return {PARTNER, pp} if pp else {PARTNER}


# ------------------------------------------------- one club per submission
# The Club picker is a multi-select (its searchable mode), so a mentor can
# pick several clubs, and question 5 then receives their names run together.
# On a form carrying the warning element below (added once per form by
# sync_attendance_form.py --club-guard, docs/plans/2026-09-29-club-guard.md)
# two generated rules show it and hide and disable Submit whenever question 5
# is not exactly one of the picker's options. Recognised by name, like the
# pickers; tools/form_status.py audits it.
GUARD_NAME = "clubGuard"
# the English sentence: its translations are keyed by it in
# tools/translations_additions.json, so a change needs them re-written
GUARD_SENTENCE = ("You chose more than one club. Keep only your own club in Club Name, "
                  "and the Submit button comes back.")
# hiding Submit alone leaves desktop Enter in a text box able to submit
GUARD_DISABLES_SUBMIT = True
# On a guarded form the picker's calcValues are its own options, so the copy
# into question 5 reads a value the browser's page translation cannot alter.
# A single-select stores a leading empty slot for its "Please Select" (|1|2|3,
# read on the live forms); a multi-select renders no placeholder, and whether
# it still wants the slot is UNVERIFIED: the template's rendered page decides
# (tools/form_status.py --rendered) before any regional form gets the guard.
PICKER_CALC_LEADING_EMPTY = True


def guard_html(sentence=GUARD_SENTENCE):
    """The warning element's HTML: one sentence in a styled paragraph (the
    links' box, glow/links.py, in amber). Pinned byte for byte in the tests:
    a change re-keys its translations (md5 of the stored HTML)."""
    return ('<p style="margin:8px 0;padding:10px 12px;border:1px solid #e0a800;'
            'border-radius:6px;background:#fff8e1;font-size:14px">'
            f'{html.escape(sentence, quote=False)}</p>')


# the element's shape, kept on every run: hidden until the guard rule shows it
GUARD_PROPS = {"text": guard_html(), "hidden": "Yes"}


def club_guards(questions):
    """qids of every question named GUARD_NAME, in qid order (normally zero
    or one; any type, so a misnamed element is refused rather than missed)."""
    return sorted((str(qid) for qid, q in questions.items() if q.get("name") == GUARD_NAME),
                  key=int)


def picker_calc_values(options):
    """The picker's calcValues for these options (PICKER_CALC_LEADING_EMPTY)."""
    return ("|" if PICKER_CALC_LEADING_EMPTY else "") + "|".join(options)


def has_calc_values(question):
    """Whether a dropdown carries calcValues (more than empty slots)."""
    return bool((question.get("calcValues") or "").replace("|", "").strip())

# Sessions per module. Modules not listed default to 8 sessions.
# EDIT HERE when the curriculum changes; the cascade rules are generated
# from this table and from the module dropdowns' live option lists.
SESSION_OVERRIDES = {
    "Elective - Healthy GLOW": 14,
    "Elective - Girl Boss Basics": 10,
    "Elective - Girl Boss Pro": 15,
}

# Warnings are printed as they happen and collected for --summary-json
# (tools/auto_sync.py decides from them whether a plan is safe to apply).
WARNINGS = []


def warn(msg):
    WARNINGS.append(msg)
    print(msg)


# ------------------------------------------------- clubs that share a name
# Salesforce finds a club's Account by question 5, exactly apart from case, in
# ONE org for every region, and creates an Account when nothing matches. A club
# whose name another partner's club also has therefore sends "<club> - <partner>"
# (Ryan, 2026-09-30; docs/plans/2026-09-30-same-name-clubs.md): that text is the
# club's Club-picker option, its calcValue, what its roster rule and the club
# guard test, question 5, and the Salesforce Account name - one string. The
# roster question's own text stays the plain club name. Which clubs send the
# long name is read back from each form (sync_attendance_form.py: an existing
# roster never flips on its own); these functions only say what the Roster
# holds. Names are compared with glow.text.key (whitespace collapsed, case
# ignored), at least as broad as Salesforce's comparison. NEVER split a value on
# the separator: club names contain it ("Alpha Club - Juniors").
SF_NAME_SEP = " - "     # ASCII space, hyphen-minus, space


def roster_pairs(csv_path):
    """{(partner, club): active} for EVERY Roster row that has both cells - any
    status, all regions (read_roster_csv keeps active rows only). `active` is
    True when the club has at least one active girl. Spellings are whitespace-
    collapsed; one entry per key(partner) + key(club), in the spelling of its
    first active row (what read_roster_csv returns), else of its first row."""
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    needed = {"partner", "club", "full_name", "status", "region"}
    if not rows or not needed <= set(rows[0]):
        sys.exit("Not a Roster export: expected the columns " + ", ".join(sorted(needed)))
    found = {}                       # (key, key) -> [partner, club, active]
    for r in rows:
        partner, club = " ".join(r["partner"].split()), " ".join(r["club"].split())
        if not (partner and club):
            continue
        active = key(r["status"]) == "active" and bool(r["full_name"].strip())
        entry = found.setdefault((key(partner), key(club)), [partner, club, False])
        if active and not entry[2]:
            entry[:] = [partner, club, True]
    return {(p, c): active for p, c, active in found.values()}


def club_partners(pairs):
    """{key(club): {key(partner): partner}}: who has a club of each name."""
    out = defaultdict(dict)
    for partner, club in pairs:
        out[key(club)].setdefault(key(partner), partner)
    return dict(out)


def shared_club_names(pairs, active_only=False):
    """key(club) of every club name that two or more partners (compared by
    key) have. active_only: count only clubs with an active girl - what the
    one-time --same-name-switch goes by; the default counts every club the
    Roster has ever held, which is what a NEW club's name is checked against."""
    who = defaultdict(set)
    for (partner, club), active in pairs.items():
        if active or not active_only:
            who[key(club)].add(key(partner))
    return {name for name, partners in who.items() if len(partners) > 1}


def sf_club_name(club, partner, long):
    """What question 5 sends for this club, and so its Salesforce Account name:
    the club's own name, or (long) "<club> - <partner>", both as the Roster
    spells them (whitespace collapsed, nothing else changed)."""
    club, partner = " ".join(str(club).split()), " ".join(str(partner or "").split())
    if not long:
        return club
    if not partner:
        sys.exit(f"'{club}' needs its partner for the name it sends to Salesforce "
                 f"('{club}{SF_NAME_SEP}<partner>'), and the sheet has none for it - fill in "
                 "the partner first")
    return f"{club}{SF_NAME_SEP}{partner}"


def long_name_partner(value, club, partners):
    """The partner inside `value` when it is `club` + SF_NAME_SEP + one of
    `partners` ({key(partner): partner}: the partners the Roster has for that
    club), compared by key; None otherwise. The club's own text is stripped as
    a prefix - the value is never split on the separator."""
    head, value = key(club) + SF_NAME_SEP, key(value)
    if not value.startswith(head):
        return None
    return (partners or {}).get(value[len(head):])


def sf_name_clashes(names):
    """names: (value, who) pairs - what a club sends to question 5, and any
    hashable id of that club. Returns [(value, [who, ...])], sorted, for every
    value (compared by key, as Salesforce matches Accounts) that two or more
    different clubs send: Salesforce would put them on one Account."""
    by = defaultdict(list)
    for value, who in names:
        if who not in [w for _, w in by[key(value)]]:
            by[key(value)].append((value, who))
    return sorted((group[0][0], [w for _, w in group]) for group in by.values() if len(group) > 1)


# -------------------------------------------------------------- sheet parsing
def parse_roster(cell):
    """Parse one roster cell: one name per line, optional '1.' numbering.
    Returns (names, duplicates): duplicates are names listed more than once -
    usually two different girls with the same full name, who need
    distinguishing suffixes added in the sheet (e.g. 'Jane Doe (A)')."""
    names = []
    for line in cell.splitlines():
        # drop invisible format characters (zero-width, LTR/RTL marks, BOM)
        line = re.sub("[\\u200b\\u200c\\u200d\\u200e\\u200f\\u2060\\ufeff]", "", line)
        line = re.sub(r"^\s*\d+[\.\)]?\s*", "", line).strip(" \t,.-")
        if line:
            names.append(" ".join(line.split()))  # collapse inner whitespace
    seen, out, dups = set(), [], []
    for n in names:
        if n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
        else:
            dups.append(n)
    return out, dups


def read_sheet(csv_path):
    """Return ({(partner, club): [girl, ...]}, {(partner, club): [dup, ...]}).
    Last submission per club wins."""
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    header = [h.lower() for h in rows[0]]

    def col(fragment):
        for i, h in enumerate(header):
            if fragment in h:
                return i
        sys.exit(f"Could not find a column containing {fragment!r} in the CSV header")

    ip, ic, ir = col(COL_PARTNER), col(COL_CLUB), col(COL_ROSTER)
    # identity is case-insensitive (partner, club): re-submissions that only
    # change capitalization ("Glow Club" -> "GLOW Club") are the same club,
    # and the LAST submission wins, keeping its spelling
    clubs, dup_names, skipped = {}, {}, 0
    for row in rows[1:]:
        if len(row) <= max(ip, ic, ir):
            if any(cell.strip() for cell in row):
                skipped += 1
            continue
        partner = " ".join(row[ip].split())
        club = " ".join(row[ic].split())
        roster, dups = parse_roster(row[ir])
        if club and roster:
            ident = (partner.lower(), club.lower())
            clubs[ident] = (partner, club, roster)
            dup_names[ident] = dups
    if skipped:
        warn(f"  ! {skipped} non-empty CSV row(s) had too few columns and "
             "were skipped - check the export")
    return ({(p, c): r for (p, c, r) in clubs.values()},
            {clubs[i][:2]: d for i, d in dup_names.items()})


def read_roster_csv(csv_path, region=None):
    """Read an export of the Roster tab (one row per girl, ACTIVE rows only).

    Returns (clubs_in_region, all_clubs, region_of) where the first two map
    (partner, club) -> [girl, ...] in sheet order and region_of maps
    (partner, club) -> region. With no region, clubs_in_region is all_clubs.
    Rosters here never contain a duplicate name (the sheet rebuild already
    routed those to the ReviewQueue), so there is no 'frozen' set."""
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    needed = {"partner", "club", "full_name", "status", "region"}
    if not rows or not needed <= set(rows[0]):
        sys.exit("Not a Roster export: expected the columns " + ", ".join(sorted(needed)))
    clubs, region_by_ident = {}, {}
    for r in rows:
        if " ".join(r["status"].split()).lower() != "active":
            continue
        partner = " ".join(r["partner"].split())
        club = " ".join(r["club"].split())
        name = " ".join(r["full_name"].split())
        if not (partner and club and name):
            continue
        ident = (partner.lower(), club.lower())
        entry = clubs.setdefault(ident, (partner, club, [], set()))
        if name.lower() not in entry[3]:
            entry[2].append(name)
            entry[3].add(name.lower())
        region_by_ident[ident] = " ".join(r["region"].split())
    all_clubs = {(p, c): names for (p, c, names, _) in clubs.values()}
    region_of = {(v[0], v[1]): region_by_ident[i] for i, v in clubs.items()}
    if region:
        want = {k: v for k, v in all_clubs.items()
                if region_of.get(k, "").lower() == region.lower()}
        if not want:
            sys.exit(f"No active clubs have region {region!r} in {csv_path} - "
                     "check the Partners tab spelling (Africa / Asia / Latin America / U.S)")
    else:
        want = all_clubs
    return want, all_clubs, region_of
