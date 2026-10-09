"""The enrollment/Roster parsers and the structural question ids.

Moved verbatim from sync_attendance_form.py (which imports them back) so the
other tools stop dynamic-loading that script with importlib. The Apps Script
side carries the same logic in appsscript/Normalize.gs and the same ids in
appsscript/Config.gs; test/parity_test.js and test/gs_parity_test.py keep the
two sides honest. Known divergences: docs/ARCHITECTURE.md.
"""
import csv
import datetime
import html
import json
import re
import sys
from collections import defaultdict

from glow.text import key

# ---------------------------------------------------------------- sheet layout
# Column headers in the enrollment sheet (matched loosely, case-insensitive).
COL_PARTNER = "partner organization name"
COL_CLUB = "club name"
COL_ROSTER = "please list the full name"
# The Partners tab's columns (appsscript/Roster.gs and tools/build_roster_offline.js
# carry the same list; test/gs_parity_test.py keeps them equal). `jotform` is the
# marker read_partners_csv reads: `no` = the partner's clubs are not on the
# attendance forms (docs/plans/2026-10-06-clubs-off-jotform.md).
PARTNER_COLS = ("partner", "region", "notes", "jotform")
JOTFORM_COL = "jotform"

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
DATE = "17"          # the attendance date (Salesforce Attendance_Date__c)
PHOTO = "19"         # Group Photo upload: required, off the Salesforce mapping since 2026-10-01
CREATOR = "105"      # `creator` (Salesforce Creator__c)
ENABLE_FUZZY = "109"  # `enableFuzzy` (Salesforce enable_fuzzy_matching__c)

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


def club_picker(questions):
    """qid of the Club picker (the dropdown named PICKER_NAME), or None when mentors type
    the club name."""
    return next((qid for qid, q in questions.items()
                 if q.get("type") == "control_dropdown" and q.get("name") == PICKER_NAME), None)


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


# ------------------------------------------------ the module Salesforce stores
# Question 98 (MODULE_ID, module_id) copies the module dropdown the mentor used
# (q14, q92 or q93, MODULES). Without calcValues the copy reads the option's
# visible text, which a browser's "Translate page" rewrites: 30 of Latin
# America's 111 September submissions sent a Spanish module, which Salesforce
# keeps as text. With calcValues the copy reads each option's data-calcvalue,
# which page translation does not touch (the year and session dropdowns have
# carried them from the start; the Club picker since the club guard). The sync
# writes each module dropdown's calcValues as its own options, with the leading
# empty slot of a single-select's "Please Select" (the year dropdown's |1|2|3,
# read 2026-10-02), and keeps them in step on every apply. Off: the sync clears
# them (the generated rollback). docs/plans/2026-10-02-names-and-modules.md
MODULE_CALC_VALUES = True

# The form-level property `clearFieldOnHide` (GET /form/{id}/properties) is
# `disable` on all five forms (read 2026-10-06). In Jotform's runtime
# (jotform.forms.js, build fc726a121d4) it has three values: `enable` - a
# field is cleared the moment a rule hides it and every calculation re-runs
# (rejected 2026-09-30: the loop limit drops to 3, DECISIONS); `disable` - the
# live mode: a rule-hidden field keeps its answer in the page; `dontClear`. At
# submit, unless the value is `dontClear`, every input, select and textarea
# inside a `.form-field-hidden` element is emptied before the form is sent
# (`always-hidden` fields such as q98/q100/q102 are not touched, and nothing
# recalculates). So a module dropdown hidden by the Year rule can keep a pick
# in the page but never in the submission (0 of 674 since launch). AUDIT ONLY:
# tools/form_status.py pins the value (its `module shape:` line); the sync's
# one PUT to /properties carries the `conditions` key alone and never writes
# this. A runtime reading, not a contract: a new build means re-reading the
# submit handler. docs/plans/2026-10-06-module-selection.md
CLEAR_FIELD_ON_HIDE = "disable"


def aligned_calc_values(options):
    """A single-select dropdown's calcValues equal to its own options: an empty slot
    for "Please Select", then each option ("" for a dropdown without options)."""
    return "|" + "|".join(options) if options else ""


def module_calc_values(options):
    """The calcValues the sync gives a module dropdown with these options
    (MODULE_CALC_VALUES): aligned_calc_values, or "" (none) when off."""
    return aligned_calc_values(options) if MODULE_CALC_VALUES else ""


def dropdown_options(question):
    """A dropdown's options as stored, empty ones dropped (what its calcValues line up with)."""
    return [o for o in (question.get("options") or "").split("|") if o]


# ------------------------------------------- the names list sent to Salesforce
# Question 18 (CONTACT_IDS) is the list of girls Salesforce stores as present:
# ONE calculation over every roster, hidden rosters ignored, so only the shown
# club's ticks arrive (docs/plans/2026-09-30-contact-ids.md). Every reader of
# these three constants - build_conditions, the sync's warning, form_status's
# audits, the runner through them - reads them from this module at run time, so
# turning one off (the generated rollback) changes the rules and what counts as
# clean together.
#
# Jotform's runtime (jotform.forms.js, read 2026-09-30, builds 9e75d6f1d83 and
# 772a1982daf) reverses the rules array and each field's listener walks the
# rules that test it in that reversed order: the rule at index 0 runs LAST. Showing or
# hiding a roster never re-runs a calculation, and nothing recalculates at
# submit. With the sum after the roster rules (the shape until 2026-10), a change
# of club calculated question 18 over the rosters as they were BEFORE the change:
# another club's girls sent, or none at all while three were ticked (2 + 17
# September submissions). On a form with the Club picker the sum is rule 0, its
# ids minted first. Order is the fix: it also holds for a form the browser
# restores (Back), where the only thing that re-shows the roster is Jotform's own
# delayed runAllConditions().
CONTACT_IDS_FIRST = True
# ...and the picker is one of the sum's operands (never in its equation, or the
# club's name would land in question 18): the picker's own change event, which
# bubbles to its <li> after every rule ran, re-runs the sum as well. Only a
# supplement: the delayed runAllConditions() after a restored page dispatches
# an event that does not bubble, so the operand alone left question 18 empty
# there in the browser, and the order alone did not.
CONTACT_IDS_PICKER_OPERAND = True
# At least one girl: every roster carries Jotform's own `required` flag. Jotform
# validates only the roster that is shown (a roster a rule hides is skipped at
# submit: its <li> carries form-field-hidden), one ticked box satisfies it, and
# the error is Jotform's own "This field is required.", translated only where the
# form's translation store has the `base` entry for that text (read 2026-10-01:
# U.S only; English on the template, Africa, Asia and Latin America: BACKLOG 57).
# Without it 64 of September's submissions sent no girl at all, each stored in
# Salesforce as an empty Success batch that blocks the club's real one for the
# day. Proven in headless Chrome on local copies of the Asia, U.S and Africa pages
# (2026-10-01); the server's markup for a required checkbox is read on the
# template after the first write (form_status.py --rendered). The sync writes
# the flag on every roster it creates and, where a roster on the form lacks it, as
# an update; off, it writes "No" (the generated rollback).
ROSTERS_REQUIRED = True
# A roster question is RETIRED - kept on the form, hidden and frozen, off the
# Club picker and without a show rule, still in question 18's sum - when its
# partner is marked `no` in the Partners tab's `jotform` column, and (this
# constant) when its club has no active girl in the Roster: Ryan, 2026-10-06,
# on. Only once the club's latest removed_date is at least a day before the
# day of the run IN THE SHEET'S ZONE (sheet_today, inactive_retires below): a
# roster emptied and refilled in two Club Roster Form submissions minutes apart
# must not leave the picker in between. Off, a club that loses its last active
# girl keeps today's treatment (`?` on the form but not in the sheet export -
# keeping its current roster). docs/plans/2026-10-06-clubs-off-jotform.md
RETIRE_INACTIVE = True
# The spreadsheet's own time zone (File > Settings), the one appsscript/Roster.gs
# today_() stamps removed_date in (getSpreadsheetTimeZone()) - NOT the script
# project's appsscript.json timeZone (America/Chicago), which no stamp uses. The
# sheet moved to it on 2026-09-02 (docs/DECISIONS.md, 2026-09-30, timestamps).
# Comparing a sheet-zone date with the UTC date would retire a club emptied in
# the sheet's evening at the very next dispatch (from 20:00 New York the UTC
# date is already tomorrow). Nothing offline can read the sheet's setting, so
# tools/auto_sync.py compares this with sheets_client.time_zone on every run
# and raises ATTENTION when they differ.
SHEET_ZONE = "America/New_York"


def sheet_today(now=None):
    """Today as a date in the sheet's zone (SHEET_ZONE), the day a removed_date
    written now would carry; `now` (an aware datetime) stands in for the clock.
    Exits when the zone is not in the time zone database (refuse, never guess)."""
    import zoneinfo
    try:
        zone = zoneinfo.ZoneInfo(SHEET_ZONE)
    except zoneinfo.ZoneInfoNotFoundError:
        sys.exit(f"The time zone database has no '{SHEET_ZONE}' (glow/sync.py SHEET_ZONE) - "
                 "install tzdata (pip install tzdata) or the system's zoneinfo; nothing done")
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return now.astimezone(zone).date()


def inactive_retires(latest_removed, today):
    """Whether a club with no active girl is retired on `today` (a date in the
    sheet's zone, sheet_today()): its latest removed_date (text, YYYY-MM-DD as
    the sheet writes it, in that zone) is at least a day before. A club whose
    rows carry no date, or one this cannot read, stays as it is - the safe side."""
    if not RETIRE_INACTIVE or not latest_removed:
        return False
    try:
        removed = datetime.date.fromisoformat(latest_removed.strip())
    except ValueError:
        return False
    return removed < today


def rule_parts(rule):
    """(terms, actions) of one condition, wire (JSON strings, as Jotform serves them) or
    parsed: two lists of dicts - a lone action dict is wrapped, a missing or empty part is [].
    None when a part does not parse or has another shape: a rule no reader can trust."""
    try:
        terms, action = rule.get("terms"), rule.get("action")
        terms = json.loads(terms) if isinstance(terms, str) else terms
        action = json.loads(action) if isinstance(action, str) else action
    except (AttributeError, ValueError):        # not a dict; not JSON
        return None
    if isinstance(action, dict):
        action = [action]
    terms, action = terms or [], action or []
    if not (isinstance(terms, list) and isinstance(action, list)
            and all(isinstance(item, dict) for item in terms + action)):
        return None
    return terms, action


def contact_ids_layout(conditions, rosters):
    """Where question 18's calculation sits among `conditions` (in the order the
    form holds and serves them) and what the rules that show a roster test.
    rosters: qids of the roster questions. Returns {"count": rules,
    "calc_rules": [positions of every rule calculating question 18],
    "position": the first of them or None, "terms": {fields its terms test},
    "operands": [its operands], "equation": str, "roster_rules": [positions of
    the rules showing a roster], "roster_rule_fields": {field: rules testing it}}."""
    rosters = {str(q) for q in rosters}
    out = {"count": len(conditions or []), "calc_rules": [], "position": None, "terms": set(),
           "operands": [], "equation": "", "roster_rules": [], "roster_rule_fields": {}}
    for pos, rule in enumerate(conditions or []):
        parts = rule_parts(rule)
        if parts is None:
            continue
        terms, actions = parts
        for a in actions:
            if str(a.get("resultField")) == CONTACT_IDS:
                out["calc_rules"].append(pos)
                if out["position"] is None:
                    out.update(position=pos, equation=str(a.get("equation") or ""),
                               terms={str(t.get("field")) for t in terms},
                               operands=[x for x in str(a.get("operands") or "").split(",") if x])
        if any(a.get("visibility") == "Show" and str(a.get("field")) in rosters for a in actions):
            out["roster_rules"].append(pos)
            for t in terms:
                f = str(t.get("field"))
                out["roster_rule_fields"][f] = out["roster_rule_fields"].get(f, 0) + 1
    return out


def contact_ids_stale(conditions, rosters, picker):
    """How the live rules miss the shape the constants above ask for, on a form
    with the Club picker: "order" when question 18's calculation comes after a
    rule that shows a roster (CONTACT_IDS_FIRST), "operand" when the picker is not
    one of its operands (CONTACT_IDS_PICKER_OPERAND). [] on a form without the
    picker or without that calculation (nothing to compare: the rewrite adds it)."""
    if not picker:
        return []
    shape = contact_ids_layout(conditions, rosters)
    if shape["position"] is None:
        return []
    stale = []
    if CONTACT_IDS_FIRST and any(p < shape["position"] for p in shape["roster_rules"]):
        stale.append("order")
    if CONTACT_IDS_PICKER_OPERAND and str(picker) not in shape["operands"]:
        stale.append("operand")
    return stale


def roster_required():
    """The `required` value every roster question carries (ROSTERS_REQUIRED)."""
    return "Yes" if ROSTERS_REQUIRED else "No"

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


def roster_removed(csv_path):
    """{(key(partner), key(club)): the latest removed_date} over EVERY Roster
    row that has both cells and a date (YYYY-MM-DD; other text is not a date
    here) - what says how long a club has had no active girl (RETIRE_INACTIVE,
    inactive_retires). {} for an export without the column."""
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows or "removed_date" not in rows[0]:
        return {}
    out = {}
    for r in rows:
        partner, club, when = key(r["partner"]), key(r["club"]), (r["removed_date"] or "").strip()
        if partner and club and re.fullmatch(r"\d{4}-\d{2}-\d{2}", when):
            out[(partner, club)] = max(out.get((partner, club), ""), when)
    return out


def _partners_rows(csv_path):
    """(rows, header as keys) of a Partners export; one without a `partner` column is refused."""
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    header = [key(h) for h in rows[0]] if rows else []
    if "partner" not in header:
        sys.exit(f"Not a Partners export: expected a 'partner' column in {csv_path}"
                 + (" - found: " + ", ".join(rows[0]) if rows else " - the file is empty"))
    return rows, header


def partners_marker_present(csv_path):
    """Whether the Partners export has the `jotform` column at all (by header name,
    as read_partners_csv reads it). Without it nobody is marked, so a sync with
    --apply refuses to restore a retired roster from it (sync_attendance_form.py)."""
    return JOTFORM_COL in _partners_rows(csv_path)[1]


def read_partners_csv(csv_path):
    """{key(partner): "yes" | "no"} from an export of the Partners tab: whether
    each partner's clubs are on the attendance forms. The columns are read by
    header name (capitals and spacing ignored); a file without a `partner`
    column is refused. In the `jotform` column `no` (compared with key) means
    not on Jotform; `yes` or blank is the default; any other text is treated as
    yes - nothing leaves a form because of a typo - and reported through warn,
    so the runner raises ATTENTION for it. A partner listed twice is `no` when
    any of its rows says so. A tab without the column marks nobody, and says so
    through warn as well (a renamed or moved header would otherwise read as
    "every mark lifted" and put every retired roster of an active club back)."""
    rows, header = _partners_rows(csv_path)
    i_p = header.index("partner")
    i_j = header.index(JOTFORM_COL) if JOTFORM_COL in header else None
    if i_j is None:
        warn(f"  ! Partners tab: the export has no '{JOTFORM_COL}' column, so no partner is marked - "
             "a retired roster of an active club would be restored; check the header (Partners!D1) "
             "before applying (docs/RUNBOOK.md, \"Clubs that do not use Jotform\")")

    def cell(row, i):
        return row[i] if i is not None and i < len(row) else ""

    out = {}
    for r in rows[1:]:
        partner = cell(r, i_p)
        if not key(partner):
            continue
        value = cell(r, i_j)
        if key(value) == "no":
            out[key(partner)] = "no"
            continue
        if key(value) not in ("", "yes"):
            warn(f"  ! Partners tab: '{' '.join(partner.split())}' has {JOTFORM_COL}='{value.strip()}' - "
                 "only yes, no or blank are understood; treated as yes")
        out.setdefault(key(partner), "yes")
    return out


def roster_names(csv_path):
    """{(key(partner), key(club)): {key(full_name), ...}} over EVERY Roster row
    that has all three cells - any status, all regions: every girl the Roster
    has ever held for that club. It is how a roster question whose rule names
    no partner (a plain name) is told to be one partner's club and not a
    same-named club of another (sync_attendance_form.py, the owner read-back):
    roster_pairs says who has a club of a name, this says whose girls a
    question holds. Python only - the Apps Script side has no such read."""
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    needed = {"partner", "club", "full_name", "status", "region"}
    if not rows or not needed <= set(rows[0]):
        sys.exit("Not a Roster export: expected the columns " + ", ".join(sorted(needed)))
    out = defaultdict(set)
    for r in rows:
        partner, club, name = key(r["partner"]), key(r["club"]), key(r["full_name"])
        if partner and club and name:
            out[(partner, club)].add(name)
    return dict(out)


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
