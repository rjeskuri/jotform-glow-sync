#!/usr/bin/env python3
"""
Sync the GLOW Attendance Form (Jotform) from the enrollment Google Sheet.

The Google Sheet (club enrollment responses) is the single source of truth.
This script reads a CSV export of that sheet and makes the Jotform form match:

  1. Creates a hidden roster checkbox question for any club that doesn't have
     one yet (options = the girls' names from the sheet), at the order of
     the last roster above the links and the Submit button, so it renders
     above them (glow/layout.py). Every roster is required (glow/sync.py
     ROSTERS_REQUIRED): Jotform refuses a submission whose shown roster has
     no girl ticked; a roster a rule hides is not checked.
  2. Updates the roster options of existing club questions when the sheet
     changed (new girls enrolled, corrections), and the required flag where
     a roster lacks it.
  3. Regenerates ALL conditional logic from scratch, in four categories:
       A. ROSTER VISIBILITY  - clubName == "<club>" -> show that roster.
                               With the Club picker, a club whose name another
                               partner's club shares is its own entry,
                               "<club> - <partner>" (the text question 5 sends
                               to Salesforce; --same-name-switch, once per
                               form). Same-named rosters not switched yet, and
                               a form without the picker, are told apart by
                               the typed Partner box
       B. CURRICULUM CASCADE - GLOW year -> module dropdown;
                               year+module -> session dropdown (8/10/14/15;
                               a special event shows none), headed by the
                               session bridge: question 100 from the session
                               dropdown shown, blank for an event
       C. SALESFORCE BRIDGE  - one aggregate Contact_IDs calculation +
                               module_id / week_id / year_id copies; with
                               the Club picker the Contact_IDs sum is rule 0
                               and lists the picker as an operand, so it is
                               recalculated after the rosters show or hide
       D. ONE CLUB           - only on a form with the club guard (added
                               once with --club-guard): several clubs picked
                               -> show the warning, hide + disable Submit
  4. Keeps each module dropdown's calcValues equal to its own options
     (glow/sync.py MODULE_CALC_VALUES), so question 98 (module_id) copies the
     module itself, never the text a browser's page translation shows; and
     appends the special-event options a module dropdown lacks
     ("Special Event - <type>", glow/sync.py SPECIAL_EVENTS) in the same write.

Usage:
    export JOTFORM_API_KEY=...
    python3 sync_attendance_form.py enrollment.csv --form 262352490535154            # dry run (default)
    python3 sync_attendance_form.py enrollment.csv --form 262352490535154 --apply    # write changes

    # From the Roster tab of the master enrollment sheet (one row per girl),
    # one region only, deleting clubs that belong to OTHER regions - meant
    # for a fresh clone (refused on any form that has submissions):
    python3 sync_attendance_form.py roster.csv --roster --region Africa --prune --form <CLONE_ID> --apply

    # By hand, once per form (docs/RUNBOOK.md, "Club names two partners share"):
    # each roster whose club name two partners' active clubs share gets its own
    # Club picker entry "<club> - <partner>" - the text question 5 then sends
    python3 sync_attendance_form.py roster.csv --roster --region Africa --form <ID> --same-name-switch

A change of what an existing club sends to question 5 is a change of its
Salesforce Account name: every run lists it ("! ... Club Name (question 5,
what Salesforce reads) changes from 'X' to 'Y'"), and --apply refuses it
unless it is --same-name-switch's own or --q5-change-ok is given. A NEW club
whose name another partner's club already has is not created.

Clubs that do not report through Jotform (docs/plans/2026-10-06-clubs-off-
jotform.md): with --roster, --partners <Partners export> brings the Partners
tab's `jotform` column (glow/sync.py JOTFORM_COL; `no` = the partner's clubs
are not on the forms). Such a club's roster question is RETIRED - kept on the
form, hidden and frozen, off the Club picker, no show rule, still in question
18's sum ("~ retired roster '<club>' (q…): not on Jotform (<partner>, Partners
tab jotform=no)") - and so is a club with no active girl once its rows have
been inactive since before today (glow/sync.py RETIRE_INACTIVE). When the
mark is lifted or the club has active girls again the roster is restored ("~
restored roster …: back on the Club picker"); a restored roster whose name two
partners have had sends its long name, listed as a question-5 change. A hand
run without --partners cannot tell a retired roster from one an apply left
half-written, so it warns per roster and --apply refuses to restore. The
runner always passes --partners.

Getting enrollment.csv: in Google Sheets, File > Download > Comma Separated
Values (.csv) on the responses tab. Getting roster.csv and partners.csv:
    python3 tools/sheets_client.py export Roster data/roster_<date>.csv
    python3 tools/sheets_client.py export Partners data/partners_<date>.csv

Requires: Python 3.10, standard library plus glow/ (this repo's shared library).
"""
import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
from glow.cli import api_key, run            # noqa: E402
from glow.jotform import Client     # noqa: E402
from glow.layout import label as layout_label, roster_slot   # noqa: E402
from glow.links import order_of as links_order_of, submit_button  # noqa: E402
from glow.sync import (             # noqa: E402  - the parsers and structural ids,
    CLUB_NAME, CONTACT_IDS, GUARD_DISABLES_SUBMIT,   # shared with the
    GUARD_NAME, GUARD_PROPS, JOTFORM_COL,
    MODULE_ID, MODULES, PARTNER, PARTNER_PICKER_NAME, PICKER_NAME, SESSION_OVERRIDES,  # other tools and
    SF_NAME_SEP, WARNINGS, WEEK_BRIDGE_FIELDS, WEEK_ID, WEEKS, YEAR, YEAR_ID, club_guards, club_partners,
    club_picker, dropdown_options, has_calc_values, inactive_retires, is_special_event, long_name_partner,
    partner_picker, partners_marker_present, picker_calc_values, read_partners_csv,
    read_roster_csv, read_sheet, roster_names, roster_pairs, roster_removed, rule_parts,   # against Config.gs
    sf_club_name, shared_club_names, sheet_today, special_event_plan, warn, week_bridge_equation,
)
from glow import sync as glow_sync  # noqa: E402  - CONTACT_IDS_FIRST, CONTACT_IDS_PICKER_OPERAND and
#                                     ROSTERS_REQUIRED are read through the module at run time, so
#                                     the generated rollback (and a test) is one switch for every reader
from glow.text import key           # noqa: E402

# Optional "Club" picker: a required dropdown listing every club on the form,
# so mentors choose their club instead of typing it. Added once per form with
# --club-picker; recognised by name (glow.sync.PICKER_NAME) from then on. When
# present, the roster visibility rules key on it and a calculation copies its
# value into the CLUB_NAME textbox (hidden), which stays the field the
# Salesforce mapping reads. Its option list and properties are kept in this
# shape on every run. multipleSelections=Yes selects Jotform's own searchable
# dropdown component (type to filter, on phones too); the plain single-select
# is a browser <select> that only jumps to the first letter. Verified on the
# template 2026-09-01 (docs/intent/2026-09-01-club-picker.md).
PICKER_TEXT = "Club Name"
PICKER_SUBLABEL = "Select your Club Name to see your roster."   # exact wording from the training guide (2026-09-12)
PICKER_PROPS = {
    "text": PICKER_TEXT,
    "subLabel": PICKER_SUBLABEL,
    "required": "Yes",
    "multipleSelections": "Yes",
    "searchText": "Type to search your club",
    "visibleOptions": "5",
    "emptyText": "Please Select",
}

# Two warnings tools/auto_sync.py acts on (it matches these fragments; its
# tests check they are still here): an existing club's question 5 - its
# Salesforce Account name - would change, which the runner never applies; and
# a new club was not added because its name is in use.
Q5_CHANGES = "Club Name (question 5, what Salesforce reads) changes"
NOT_ADDED = "not added: give it a different name"
# A third: a roster's rule tests a text the Club picker does not list (a
# conditions backup restored over a switched picker, an apply that stopped
# between the picker write and the rules write). Until the rules are rewritten
# that club's roster never shows and the club guard blocks its mentors; the
# runner, which does not apply a rules-only difference, raises ATTENTION.
RULES_OLDER = "which the Club picker does not list"
# A fourth: the live rules calculate question 18 (the names Salesforce stores)
# the old way - after the rosters' rules, or without the Club picker among its
# operands (glow/sync.py CONTACT_IDS_FIRST / CONTACT_IDS_PICKER_OPERAND). The
# rewrite is one REPLACE conditions per form, rolled out by hand: the runner
# raises ATTENTION and does not apply that region (docs/plans/2026-09-30-
# contact-ids.md).
CONTACT_IDS_STALE = "question 18 (Contact_IDs) is not recalculated after the rosters change"
# A fifth: the form carries (or this run gives it) a special-event option, but the live
# rules let an event show a session dropdown or send a session in question 100 - no
# session bridge, or one out of place, or a session rule on no curriculum module (an
# apply that stopped after the module writes, or the option added in the builder). The
# next dry run plans a rules-only REPLACE, which the runner does not count as a change:
# on this warning it raises ATTENTION and applies nothing there; the rewrite is a hand
# apply (docs/plans/2026-10-13-special-events.md)
WEEK_BRIDGE_STALE = "the form's rules let a special event show or send a session"
# A retired roster that comes back (docs/plans/2026-10-06-clubs-off-jotform.md)
# has no rule to read what it sent: when its name is one two partners have had
# it is restored with its long name, listed as a question-5 change from this
# text - the Q5_CHANGES warning, the --q5-change-ok refusal and the runner's
# band all fire, and the Account's name is checked by hand first.
RETIRED_OLD = "(retired: no rule to read)"
RESTORED_WHY = "back on the Club picker"

# SESSION_OVERRIDES (sessions per elective module) lives in glow/sync.py -
# edit it THERE when the curriculum changes, and mirror appsscript/Config.gs.

# ------------------------------------------------------------------ id minting
_counter = [0]
ID_BASE = 1758000000000

def next_id():
    _counter[0] += 1
    return str(ID_BASE + _counter[0])

# ------------------------------------------------------------------- API layer
class Jotform:
    """Form-scoped view over glow.jotform.Client: the same get/post_form/
    put_json/delete surface this script always had, with paths relative to
    /form/{id}. The dry-run gate lives in the shared client."""

    def __init__(self, api_key, form_id, apply_changes=False):
        self._client = Client(api_key, apply=apply_changes)
        self.form = form_id
        self.apply = apply_changes

    @property
    def calls(self):
        return self._client.calls

    def get(self, path):
        return self._client.get(f"/form/{self.form}{path}")

    def post_form(self, path, data, label):
        return self._client.post_form(f"/form/{self.form}{path}", data, label)

    def put_json(self, path, payload, label):
        return self._client.put_json(f"/form/{self.form}{path}", payload, label)

    def delete(self, path, label):
        return self._client.delete(f"/form/{self.form}{path}", label)

# --------------------------------------------------------- condition builders
def mk_term(field, operator, value=""):
    return {"id": f"term_{next_id()}", "field": str(field),
            "operator": operator, "value": value, "isError": False}

def mk_show(field):
    return {"id": f"action_{next_id()}", "visibility": "Show",
            "isError": False, "field": str(field)}

def mk_hide(field):
    return {"id": f"action_{next_id()}", "visibility": "Hide",
            "isError": False, "field": str(field)}

def mk_disable(field):
    """A require-rule action (Jotform's "Enable / Require" rule type)."""
    return {"id": f"action_{next_id()}", "visibility": "Disable",
            "isError": False, "field": str(field)}

def mk_field_rule(terms, actions, link="Any"):
    return {"id": next_id(), "type": "field", "link": link,
            "priority": "0", "index": "0", "terms": terms, "action": actions}

def mk_require_rule(terms, actions, link="Any"):
    return {"id": next_id(), "type": "require", "link": link,
            "priority": "0", "index": "0", "terms": terms, "action": actions}

def mk_calc_rule(terms, result_field, operands, equation, ignore_hidden=False,
                 as_text=False):
    action = {"id": f"action_{next_id()}", "resultField": str(result_field),
              "operands": operands, "equation": equation,
              "newCalculationType": True, "allowZeroCopy": True,
              "readOnly": False, "replaceText": "",
              "useCommasForDecimals": False, "showBeforeInput": False,
              "showEmptyDecimals": False, "ignoreHiddenFields": ignore_hidden,
              "insertAsText": as_text, "decimalPlaces": "2", "isError": False}
    return {"id": next_id(), "type": "calculation", "link": "Any",
            "priority": "0", "index": "0", "terms": terms, "action": [action]}

def build_conditions(club_questions, partner_of, module_options, picker=None,
                     picker_options=None, guard=None, submit=None, retired=()):
    """club_questions: {qid: the text its rule tests} - the club's name, or on
    a form with the Club picker its picker entry, which for a club whose name
    another partner's club shares is "<club> - <partner>" (main() decides;
    glow.sync.SF_NAME_SEP); partner_of: {qid: partner} for the rosters that
    still share one text and are told apart by the typed Partner box (PARTNER);
    picker: qid of the Club dropdown when the form has one (the rules then key
    on it and its value is copied into the CLUB_NAME textbox for Salesforce);
    picker_options: the picker's options exactly as this run writes them (the
    rules test each club in the picker's spelling); guard / submit: qids of the clubGuard
    warning and the Submit button on a form with the one-club guard (section
    D; both, with a picker and its options, or no guard rules at all);
    retired: qids of the retired rosters (docs/plans/2026-10-06-clubs-off-
    jotform.md) - in question 18's operands and equation like every roster,
    but with no show rule (a roster nobody can see has no tick to add).

    On a form with the picker the Contact_IDs sum (section C) is rule 0, built
    before every other rule so its ids are the lowest, and lists the picker
    among its operands (glow/sync.py CONTACT_IDS_FIRST and
    CONTACT_IDS_PICKER_OPERAND; each off gives the shape before 2026-10). A
    form without the picker keeps its rules byte for byte."""
    conds = []
    club_field = picker or CLUB_NAME
    # A picker is a multi-select, where Jotform's "equals" means "this exact
    # option is selected" - case-sensitively - so a rule spelling the club
    # differently from the option never fires ("SUPER GIRLS" vs "Super
    # Girls"): with a picker every club term takes the picker's spelling.
    spelling = {o.lower(): o for o in picker_options} if picker and picker_options else {}

    def club(name):
        return spelling.get(name.lower(), name)

    roster_qids = sorted(set(club_questions) | {str(q) for q in retired}, key=int)

    def contact_ids():
        # no separator between the rosters, guard or not: only one roster can be
        # visible when Submit is (the guard's rules), and a literal ", " would be
        # written between every pair of operands, hidden ones included. The
        # picker is an operand only: in the equation its club name would be sent
        # to Salesforce as a girl
        operands = ([picker] if picker and glow_sync.CONTACT_IDS_PICKER_OPERAND else []) + roster_qids
        return mk_calc_rule(
            [mk_term(club_field, "isFilled")], CONTACT_IDS,
            ",".join(operands), "".join("{%s}" % q for q in roster_qids),
            ignore_hidden=True, as_text=True)

    # Jotform walks a field's rules last to first, so rule 0 runs after every
    # roster is shown or hidden (glow/sync.py CONTACT_IDS_FIRST); minted first,
    # its ids are the lowest, so id order and index still agree
    first = bool(picker and glow_sync.CONTACT_IDS_FIRST)
    if first:
        conds.append(contact_ids())

    # A. roster visibility
    # ambiguity is judged case-insensitively: Jotform's runtime "equals"
    # ignores case on the typed box, and the picker lists such names once
    by_name = defaultdict(list)
    for qid, name in club_questions.items():
        by_name[name.lower()].append(qid)
    for qid, name in sorted(club_questions.items(), key=lambda kv: int(kv[0])):
        if len(by_name[name.lower()]) > 1:
            conds.append(mk_field_rule(
                [mk_term(PARTNER, "equals", partner_of[qid]),
                 mk_term(club_field, "equals", club(name))],
                [mk_show(qid)], link="All"))
        else:
            conds.append(mk_field_rule([mk_term(club_field, "equals", club(name))],
                                       [mk_show(qid)]))
    for _low, qids in sorted(by_name.items()):
        if len(qids) > 1:  # ambiguous name -> reveal the Partner box
            conds.append(mk_field_rule(
                [mk_term(club_field, "equals", club(club_questions[qids[0]]))],
                [mk_show(PARTNER)]))

    # B. curriculum cascade
    # ...headed by the session bridge (glow/sync.py WEEK_BRIDGE_FIELDS): question 100
    # from the session dropdown shown, "" when none is (a special event). Before every
    # rule that shows a session dropdown and before the copies below, so in the walk of
    # each field it tests it runs last; minted here, its ids follow the order
    conds.append(mk_calc_rule([mk_term(f, "isFilled") for f in WEEK_BRIDGE_FIELDS], WEEK_ID,
                              ",".join(WEEK_BRIDGE_FIELDS), week_bridge_equation(), ignore_hidden=True))
    for year, module_qid in MODULES.items():
        conds.append(mk_field_rule([mk_term(YEAR, "equals", year)],
                                   [mk_show(module_qid)]))
    # one rule per module of every year (year 1: the 8-session dropdown for each); a
    # special event (glow/sync.py SPECIAL_EVENTS) has no session, so no rule shows one
    for year in MODULES:
        for module in module_options[year]:
            if is_special_event(module):
                continue
            n = 8 if year == "1" else SESSION_OVERRIDES.get(module, 8)
            conds.append(mk_field_rule(
                [mk_term(MODULES[year], "equals", module),
                 mk_term(YEAR, "equals", year)],
                [mk_show(WEEKS[n])], link="All"))

    # C. salesforce bridge
    if picker:  # the picked club -> the textbox Salesforce reads (Account_Name__c)
        conds.append(mk_calc_rule([mk_term(picker, "isFilled")], CLUB_NAME,
                                  picker, "{%s}" % picker, as_text=True))
    conds.append(mk_calc_rule([mk_term(YEAR, "isFilled")], YEAR_ID,
                              YEAR, "{%s}" % YEAR))
    for module_qid in MODULES.values():
        conds.append(mk_calc_rule([mk_term(module_qid, "isFilled")], MODULE_ID,
                                  module_qid, "{%s}" % module_qid))
    for week_qid in WEEKS.values():
        conds.append(mk_calc_rule([mk_term(week_qid, "isFilled")], WEEK_ID,
                                  week_qid, "{%s}" % week_qid))
    guarded = bool(picker and picker_options and guard and submit)
    if not first:
        conds.append(contact_ids())

    # D. one club per submission: question 5 (the copy of the picker) is not
    # exactly one of its options -> several clubs are picked: show the
    # warning, hide Submit, and (a require rule) disable it too, which closes
    # the desktop Enter key. Appended last, so every other rule keeps its index.
    if guarded:
        def terms():
            return [mk_term(picker, "isFilled")] + \
                   [mk_term(CLUB_NAME, "notEquals", o) for o in picker_options]
        conds.append(mk_field_rule(terms(), [mk_show(guard), mk_hide(submit)], link="All"))
        if GUARD_DISABLES_SUBMIT:
            conds.append(mk_require_rule(terms(), [mk_disable(submit)], link="All"))

    for i, c in enumerate(conds):
        c["index"] = str(i)
        c["priority"] = str(i)
    return conds

def _norm_rules(conds):
    """Rules with the re-minted ids and counters stripped, for comparison."""
    out = []
    for c in conds:
        parts = rule_parts(c)
        if parts is None or c.get("terms") is None or c.get("action") is None:
            # same_conditions then says "not the same" (the rules are rewritten) and rule_delta
            # counts every planned rule as new, as when the json.loads here raised
            raise ValueError(f"rule {c.get('id')}: terms/action missing or not parseable")
        terms, action = parts
        out.append((c.get("type"), c.get("link"),
                    json.dumps([{k: v for k, v in t.items() if k != "id"} for t in terms],
                               sort_keys=True),
                    json.dumps([{k: v for k, v in a.items() if k != "id"} for a in action],
                               sort_keys=True)))
    return out

def same_conditions(current, planned):
    """True when the live rules equal the regenerated ones (ids and the
    index/priority counters aside) - then the rewrite is a no-op and skipped,
    so an unchanged form stays untouched (and its Revision History quiet)."""
    try:
        return _norm_rules(current) == _norm_rules(planned)
    except (TypeError, ValueError, KeyError):
        return False

def rule_delta(current, planned):
    """(kept, new, dropped): how many planned rules the form already has (ids
    and order aside), how many it gains, and how many of its rules go."""
    try:
        cur = Counter(_norm_rules(current))
    except (TypeError, ValueError, KeyError):
        cur = Counter()
    plan = Counter(_norm_rules(planned))
    kept = sum((cur & plan).values())
    return kept, sum(plan.values()) - kept, sum(cur.values()) - kept

def joined_clashes(options):
    """[(a, b, c)]: two picker options whose names run together - what
    question 5 receives when both are picked - equal a third option (as
    Jotform compares a textbox: case and outer spaces ignored). The club
    guard cannot tell such a pair from the one club."""
    by_key = {o.strip().lower(): o for o in options}
    return [(a, b, by_key[(a + b).strip().lower()])
            for a in options for b in options
            if a != b and (a + b).strip().lower() in by_key]

# ------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("csv", help="CSV export of the enrollment sheet (or of the "
                                "Roster tab, with --roster)")
    ap.add_argument("--form", required=True, help="Jotform form ID")
    ap.add_argument("--apply", action="store_true",
                    help="write changes (default is a dry run)")
    ap.add_argument("--roster", action="store_true",
                    help="the CSV is an export of the Roster tab (one row per girl)")
    ap.add_argument("--region", help="with --roster: only this region's clubs")
    ap.add_argument("--partners", metavar="PATH",
                    help="with --roster: an export of the Partners tab, whose `jotform` column "
                         "says which partners' clubs are not on the attendance forms (`no`): their "
                         "rosters are retired - kept hidden, off the Club picker. Without it a hand "
                         "run cannot tell a retired roster from a half-written one and refuses to "
                         "--apply a restore; the runner always passes it")
    ap.add_argument("--disabled-ok", action="store_true",
                    help="with --apply: write to a form whose status is not ENABLED (a disabled form "
                         "is one nobody can open; the runner skips it)")
    ap.add_argument("--prune", action="store_true",
                    help="with --region: DELETE club questions that the Roster "
                         "places in another region (fresh clones only)")
    ap.add_argument("--summary-json", metavar="PATH",
                    help="also write a machine-readable summary of the plan to PATH "
                         "(used by tools/auto_sync.py)")
    ap.add_argument("--club-picker", action="store_true",
                    help="add the Club dropdown to this form (once; afterwards it is "
                         "maintained on every run) and hide the Club Name textbox")
    ap.add_argument("--club-guard", action="store_true",
                    help="add the one-club-per-submission guard to this form (once; afterwards "
                         "it is maintained on every run): a warning below the Club picker, and "
                         "Submit hidden and disabled while several clubs are picked")
    ap.add_argument("--same-name-switch", action="store_true",
                    help="by hand, once per form: every roster on it whose club name two or "
                         "more partners' ACTIVE clubs share (in any region) gets its own Club "
                         "picker entry '<club> - <partner>', which is what question 5 then "
                         "sends to Salesforce. Afterwards each roster keeps the form it has; "
                         "the automatic sync never passes this")
    ap.add_argument("--q5-change-ok", action="store_true",
                    help="with --apply: accept a change of what an existing club sends to "
                         "question 5 (a renamed club, a respelled partner) - rename its "
                         "Salesforce account first. Not needed for --same-name-switch's own "
                         "changes")
    args = ap.parse_args()
    if args.region and not args.roster:
        sys.exit("--region needs --roster (the Roster tab is what carries regions)")
    if args.partners and not args.roster:
        sys.exit("--partners needs --roster (the Partners tab marks Roster clubs, not enrollment rows)")
    if args.prune and not args.region:
        sys.exit("--prune needs --region")

    jf = Jotform(api_key(), args.form, args.apply)

    # the form's status first: a DISABLED form is one nobody can open, so a write
    # to it is refused unless asked for (the runner skips such a form instead)
    info = jf.get("")
    status = str(info.get("status") or "")
    print(f"Form: {args.form} status {status or 'not reported'}")
    if args.apply and status != "ENABLED" and not args.disabled_ok:
        sys.exit(f"Refusing: form {args.form} is {status or 'of unknown status'}, not ENABLED - a write "
                 "nobody can see. Enable the form first (docs/RUNBOOK.md, \"Disabling a regional "
                 "form\"), or pass --disabled-ok to write to it anyway")

    all_clubs, region_of, partners, off_form = {}, {}, None, {}
    marker = False      # whether the Partners export has the jotform column at all
    if args.roster:
        sheet, all_clubs, region_of = read_roster_csv(args.csv, args.region)
        dup_names = {}
        pairs = roster_pairs(args.csv)      # every club the Roster holds: any status, all regions
        ever = roster_names(args.csv)       # ...and every girl it has ever held for each
        if args.partners:
            partners = read_partners_csv(args.partners)     # key(partner) -> "yes" | "no"
            marker = partners_marker_present(args.partners)  # ...else nobody is marked (warned above)
            # the floor: every partner with an active club must be a row of the export,
            # or a cut export would read every partner as unmarked and restore every
            # retired roster unattended (one picker UPDATE, inside every band)
            with_clubs = {key(p): p for p, _ in all_clubs}
            missing = sorted(p for k, p in with_clubs.items() if k not in partners)
            if missing:
                sys.exit(f"Partners export lists {len(with_clubs) - len(missing)} of {len(with_clubs)} "
                         f"partners with active clubs - missing: {', '.join(missing)} - a truncated "
                         "export, or rows deleted from the Partners tab? nothing done")
            # the clubs of a partner marked `no` leave this form's share of the Roster
            # (all_clubs and region_of stay the Roster's truth for foreign_region)
            off_form = {pc: v for pc, v in sheet.items() if partners.get(key(pc[0])) == "no"}
            sheet = {pc: v for pc, v in sheet.items() if pc not in off_form}
            if not sheet:
                sys.exit(f"Every active club{' in ' + args.region if args.region else ''} belongs to a "
                         f"partner marked {JOTFORM_COL}=no in the Partners export - the form would be "
                         "left with an empty Club picker, a shape never tested: disable the form "
                         "instead (docs/RUNBOOK.md, \"Clubs that do not use Jotform\")")
        print(f"Roster: {len(sheet)} active clubs"
              f"{' in ' + args.region if args.region else ''} "
              f"({sum(len(v) for v in sheet.values())} girls); "
              f"{len(all_clubs)} clubs overall"
              + (f"; {len(off_form)} club(s) of {len({key(p) for p, _ in off_form})} partner(s) not "
                 f"on Jotform (Partners tab {JOTFORM_COL}=no) left off this form" if off_form else ""))
    else:
        sheet, dup_names = read_sheet(args.csv)
        pairs = {k: True for k in sheet}
        ever = {}                           # an enrollment export has no history: no owner is read from it
        print(f"Sheet: {len(sheet)} clubs "
              f"({sum(len(v) for v in sheet.values())} girls total)")
    holders = club_partners(pairs)      # key(club) -> the partners that have a club of that name
    shared_any = shared_club_names(pairs)                        # names two partners have ever had
    shared_active = shared_club_names(pairs, active_only=True)   # what --same-name-switch goes by

    if args.prune and int(info.get("count") or 0) > 0:
        msg = (f"form {args.form} already has {info['count']} submission(s); "
               "--prune is for fresh clones only")
        if args.apply:
            sys.exit("Refusing: " + msg)
        warn(f"  ! (preview only) {msg}")

    # clubs whose roster lists the same full name twice: two different girls
    # need a distinguishing suffix in the SHEET before we trust that roster
    frozen = set()
    for ident, dups in dup_names.items():
        if dups:
            frozen.add(ident)
            warn(f"  ! {ident[1]} ({ident[0]}): {', '.join(dups)} appears twice "
                 "in the roster. If these are two different girls, add a "
                 "distinguishing suffix in the sheet (e.g. 'Anh Nguyen (A)'). "
                 "An existing roster on the form is not updated from this "
                 "row; a brand-new club is created with the name listed "
                 "once.")

    questions = jf.get("/questions")
    norm = lambda s: " ".join(s.split())
    # keyed case-insensitively: Jotform's runtime "equals" ignores case, so
    # "explorers" and "Explorers" are the SAME club as far as the form is
    # concerned and must share one roster question
    existing = {}      # lowercased club name -> [qid,...]
    form_text = {}     # qid -> normalized display text
    for qid, q in questions.items():
        if q["type"] == "control_checkbox":
            existing.setdefault(norm(q["text"]).lower(), []).append(qid)
            form_text[qid] = norm(q["text"])

    # each module dropdown's options as this run leaves them: its own, then the special-event
    # options it lacks (glow/sync.py SPECIAL_EVENTS; written below with its calcValues), so
    # the rules - and a dry run - are the whole result
    events = {year: special_event_plan(dropdown_options(questions[mqid])) for year, mqid in MODULES.items()}
    module_options = {year: dropdown_options(questions[mqid]) + events[year]["add"]
                      for year, mqid in MODULES.items()}
    for year, mqid in MODULES.items():
        for option in events[year]["unknown"]:
            warn(f"  ! module dropdown q{mqid} (year {year}) lists '{option}', which is no special event "
                 "of glow/sync.py SPECIAL_EVENTS: left as it is (a retired type is removed by hand in the "
                 "builder; docs/RUNBOOK.md, \"Special events\")")
        for have, want in events[year]["respelled"]:
            warn(f"  ! module dropdown q{mqid} (year {year}) lists '{have}', spelled unlike '{want}' "
                 "(glow/sync.py SPECIAL_EVENTS): Salesforce receives the form's spelling - correct it in "
                 "the builder; not added again")

    picker_qid = club_picker(questions)
    if picker_qid:
        print(f"Club picker: q{picker_qid} (mentors choose their club from a list)")
        if args.club_picker:
            print("  - the form already has the Club picker; --club-picker is not needed")

    # the partner list (docs/plans/2026-09-28-partner-box.md) was never deployed and is
    # retired (2026-09-30): clubs that share a name each have their own picker entry
    partner_qid = partner_picker(questions)
    if partner_qid:
        sys.exit(f"q{partner_qid} is a partner list ({PARTNER_PICKER_NAME!r}), retired 2026-09-30: "
                 "clubs that share a name each have their own Club picker entry now. Delete the "
                 "list in the builder first, then run this again")
    has_picker = picker_qid is not None or args.club_picker
    if args.same_name_switch and picker_qid is None:
        sys.exit("--same-name-switch needs the Club picker on the form (a mentor cannot be asked "
                 "to type '<club> - <partner>'): add it first (--club-picker), then run "
                 "--same-name-switch separately")

    # the one-club guard: refusals before any write
    guards = club_guards(questions)
    if len(guards) > 1:
        sys.exit(f"{len(guards)} elements are named {GUARD_NAME!r} "
                 f"({', '.join('q' + g for g in guards)}) - delete the extra one in the builder first")
    guard_qid = guards[0] if guards else None
    if guard_qid and questions[guard_qid].get("type") != "control_text":
        sys.exit(f"q{guard_qid} is named {GUARD_NAME!r} but is a {questions[guard_qid].get('type')}, "
                 "not a text element - rename or delete it in the builder first")
    if guard_qid:
        print(f"Club guard: q{guard_qid} (one club per submission)")
        if args.club_guard:
            print("  - the form already has the club guard; --club-guard is not needed")
    if args.club_guard and picker_qid is None:
        sys.exit("--club-guard needs the Club picker on the form: add it first (--club-picker), "
                 "then run --club-guard")
    if guard_qid and picker_qid is None:
        warn(f"  ! q{guard_qid} (the club guard) needs the Club picker, which this form lacks - "
             "no guard rules this run")
    guard_on = picker_qid is not None and (guard_qid is not None or args.club_guard)
    submit_qid = None
    if guard_on:   # found by type; refuses unless there is exactly one (q2 on every form)
        button = submit_button(questions)
        submit_qid = next(str(k) for k, q in questions.items() if q is button)

    # What the form's current rules say about each roster (read back before
    # anything is decided):
    #  - current_value: the text its show rule tests on the club field, which
    #    is what question 5 sends for that club today - its plain name, or
    #    "<its text> - <partner>";
    #  - current_partner_of: the partner its rule ties it to, which is how
    #    same-named clubs are matched to their existing questions - the
    #    Partner-box term of a rule that still tells two rosters of one text
    #    apart (`gated`), or the partner inside a long name. That one counts
    #    only when the Roster has that partner + club (any status): a club
    #    renamed from "X - Y" to "X" still tests "X - Y" until this run, and
    #    "Y" is no partner. The roster's own text is stripped as a prefix;
    #    nothing is ever split on " - ".
    current_partner_of, current_value, gated = {}, {}, set()
    club_field = picker_qid or CLUB_NAME
    props = jf.get("/properties")
    for cond in props.get("conditions", []):
        if cond.get("type") != "field":
            continue
        parts = rule_parts(cond)
        if parts is None:
            sys.exit(f"Refusing: the form's rule {cond.get('id')} has terms or an action that do not "
                     "parse - look at it in the builder (Settings > Conditions), or restore the rules "
                     "from a backup (restore_conditions.py)")
        terms, action = parts
        pterm = next((t for t in terms if str(t["field"]) == PARTNER
                      and t["operator"] == "equals"), None)
        cterm = next((t for t in terms if str(t["field"]) == club_field
                      and t["operator"] == "equals"), None)
        for a in action:
            if a.get("visibility") != "Show":
                continue
            if pterm:
                current_partner_of[str(a["field"])] = pterm["value"]
                gated.add(str(a["field"]))
            if cterm and str(a["field"]) in form_text:
                current_value[str(a["field"])] = norm(str(cterm["value"]))
    for qid, value in current_value.items():
        if qid not in current_partner_of:
            partner = long_name_partner(value, form_text[qid], holders.get(key(form_text[qid])))
            if partner:
                current_partner_of[qid] = partner
    # A roster whose rule names no partner (a plain name) is still one club's.
    # When the Roster has more than one partner with a club of that name - a
    # retired namesake, or a new club that was refused and sits in the Roster
    # until someone renames it - its owner is read from the Roster's rows of
    # ANY status: the partner whose rows list the most of the girls the
    # question holds today, when that is at least half of them and more than
    # any other partner's. Without it the matching below goes by the NEW
    # roster alone: another partner's new club took over a retired club's
    # question (its girls on that club's Salesforce Account), and an existing
    # club with a mostly new roster was refused as "new". A tie, or no
    # evidence (the old rows deleted, the girls respelled in place), names no
    # owner and the matching goes on as it did. `inferred` is never `gated`:
    # the rule itself names no partner.
    inferred = set()
    for qid, text in form_text.items():
        who = holders.get(key(text), {})
        if qid in current_partner_of or len(who) < 2:
            continue
        have = {key(o) for o in (questions[qid].get("options") or "").split("|") if o.strip()}
        fits = sorted(((len(have & ever.get((pk, key(text)), set())), partner)
                       for pk, partner in who.items()), key=lambda f: -f[0])
        if have and fits[0][0] * 2 >= len(have) and fits[0][0] > fits[1][0]:
            current_partner_of[qid] = fits[0][1]
            inferred.add(qid)

    def rule_partner(qid):
        """The partner the form's own rules name for this roster ("" when they
        name none - an owner read from the Roster's rows is not the form's word)."""
        return "" if qid in inferred else current_partner_of.get(qid, "")

    # question 18 the old way (glow/sync.py CONTACT_IDS_FIRST / _PICKER_OPERAND):
    # the rewrite below fixes it, but only by hand - the runner reads this line
    stale_ids = glow_sync.contact_ids_stale(props.get("conditions", []), form_text, picker_qid)
    if stale_ids:
        shape = glow_sync.contact_ids_layout(props.get("conditions", []), form_text)
        why = []
        if "order" in stale_ids:
            why.append(f"its calculation is rule {shape['position'] + 1} of {shape['count']}, after "
                       "the rosters' rules, so a change of club calculates it before the rosters "
                       "show or hide")
        if "operand" in stale_ids:
            why.append(f"the Club picker (q{picker_qid}) is not one of its operands")
        warn(f"  ! {CONTACT_IDS_STALE}: {'; '.join(why)} - the rewrite puts it right; apply this "
             "form by hand (docs/RUNBOOK.md, \"The names list sent to Salesforce\")")

    # the special events' rules the old way (glow/sync.py week_bridge_stale): on a form that
    # carries, or after this run will carry, an event option - the runner reads this line too
    if any(is_special_event(o) for options in module_options.values() for o in options):
        stale_bridge = glow_sync.week_bridge_stale(props.get("conditions", []))
        if stale_bridge:
            warn(f"  ! {WEEK_BRIDGE_STALE}: {'; '.join(stale_bridge)} - the rewrite puts it right; apply "
                 "this form by hand (docs/RUNBOOK.md, \"Special events\")")

    # the picker's options as the form holds them: what a mentor can pick today
    listed = {}
    if picker_qid:
        for o in (questions[picker_qid].get("options") or "").split("|"):
            if o.strip():
                listed.setdefault(key(o), norm(o))

    def sends_now(qid, partner):
        """What question 5 receives for this roster's club today: the text its
        rule tests - or, when the picker does not list that text (a conditions
        backup restored over newer options, an apply that stopped between the
        picker and the rules), the entry the picker does list for it: its long
        name, else its plain one. None when nothing says."""
        value = current_value.get(qid)
        if not listed or (value and key(value) in listed):
            return value
        for cand in ([sf_club_name(form_text[qid], partner, True)] if partner else []) \
                + [form_text[qid]]:
            if key(cand) in listed:
                if value:   # a roster with no rule at all (a failed apply's new club) is no such case
                    warn(f"  ! '{form_text[qid]}' (q{qid}): its rule tests '{value}', {RULES_OLDER} "
                         f"(it lists '{listed[key(cand)]}') - the rules and the picker are out of "
                         "step (a restored backup, an apply that stopped half-way?): until an "
                         "--apply rewrites the rules this roster does not show")
                return listed[key(cand)]
        return value

    def picker_entries(text, partner):
        """The picker's entries for this partner's roster of this text: its plain
        name, or its own long name "<text> - <partner>" (never a namesake's)."""
        own = {key(text)} | ({key(sf_club_name(text, partner, True))} if partner else set())
        return [o for k, o in listed.items() if k in own]

    def partner_matches(a, b):
        """Loose partner-name match: 'WESAD' matches 'World Economy ... (WESAD)'."""
        a, b = norm(a).lower(), norm(b).lower()
        return a and b and (a in b or b in a)

    def same_partner(a, b):
        return key(a) == key(b)

    def loosely(club_key):
        """partner_matches for the rosters of one club name - but never when
        the partner in the rule is, exactly, a partner the Roster has for
        that name: then "Partner One" inside "Partner One Trust" is two
        partners' clubs, not one partner spelled two ways."""
        known = holders.get(club_key, {})
        return lambda theirs, partner: key(theirs) not in known and partner_matches(theirs, partner)

    def shared_names(qid, roster):
        """(how many of this roster's names the question holds, the smaller of the two sizes)."""
        have = {norm(o).lower() for o in questions[qid]["options"].split("|") if o}
        want = {n.lower() for n in roster}
        return len(have & want), min(len(have), len(want))

    def roster_overlap(qid, roster):
        shared, smaller = shared_names(qid, roster)
        return shared / smaller if smaller else 0.0

    def foreign_region(qid):
        """The region the FULL roster gives this form question's club, when
        it is not the region being synced; None when unknown or the same.
        Same-name clubs are told apart by the partner in the form's rules."""
        if not args.region:
            return None
        name = form_text[qid].lower()
        cands = [k for k in all_clubs if k[1].lower() == name]
        if len(cands) > 1 and qid in current_partner_of:
            theirs = current_partner_of[qid]      # the exact partner before the loose match
            cands = ([k for k in cands if same_partner(theirs, k[0])]
                     or [k for k in cands if partner_matches(theirs, k[0])])
        if len(cands) != 1:
            return None
        reg = region_of.get(cands[0], "")
        return reg if reg and reg.lower() != args.region.lower() else None

    to_delete = []   # (qid, club, region it belongs to)

    def keep_or_prune(qid):
        """For a question the sheet did not claim: prune it if it belongs to
        another region (and --prune), otherwise keep it and say why."""
        reg = foreign_region(qid)
        if reg and args.prune:
            to_delete.append((qid, form_text[qid], reg))
            return False
        if reg:
            warn(f"  ! '{form_text[qid]}' (q{qid}) belongs to {reg} - kept "
                 "(use --prune on a fresh clone to remove it)")
        return True

    # --- retired rosters (docs/plans/2026-10-06-clubs-off-jotform.md) ----------
    # Decided BEFORE the reconcile loop, so that both of its branches see the
    # same thing. For every roster question the Roster is asked who owns it:
    # the partners with a club of that name (any status), narrowed by the
    # partner its rule names or its owner read-back when the name has several.
    # When the owner is one pair and either its partner is marked `no` in the
    # Partners tab or (RETIRE_INACTIVE) the pair has no active girl and its
    # rows have been inactive since before today - the day in the SHEET's zone,
    # the one its removed_date cells are stamped in - the roster is retired: out of
    # `existing`, so neither branch matches it; not in club_questions nor
    # option_of, so no picker entry, no show rule, no guard term; nothing is
    # written to the question itself (hidden, required, its options frozen);
    # still in question 18's sum (build_conditions). A question whose owner
    # cannot be told, or whose club the Roster does not know at all, keeps
    # today's treatment and lines (an incomplete export looks like that). The
    # `~` line names a roster this run takes off the picker (it still has its
    # rule or its entry): the runner counts those against its band; one the
    # form already holds retired is only counted below.
    retired = {}     # qid -> {"club", "partner", "reason"}
    retiring = {}    # the subset this run takes off the picker (the ~ lines)
    if args.roster:
        marks = partners or {}
        removed = roster_removed(args.csv)
        today = sheet_today()
        pair_by_key = {(key(p), key(c)): (p, c) for p, c in pairs}
        for qid, text in sorted(form_text.items(), key=lambda kv: int(kv[0])):
            who = holders.get(key(text), {})
            if len(who) == 1:
                owner = next(iter(who.values()))
            elif qid in current_partner_of and key(current_partner_of[qid]) in who:
                owner = who[key(current_partner_of[qid])]
            else:
                continue
            pc = pair_by_key[(key(owner), key(text))]
            if marks.get(key(owner)) == "no":
                reason = f"not on Jotform ({owner}, Partners tab {JOTFORM_COL}=no)"
            elif not pairs[pc] and inactive_retires(removed.get((key(owner), key(text))), today):
                reason = "no active girl in the Roster"
            else:
                continue
            retired[qid] = {"club": text, "partner": owner, "reason": reason}
            if qid in current_value or picker_entries(text, owner):
                retiring[qid] = retired[qid]
                print(f"  ~ retired roster '{text}' (q{qid}): {reason}")
            existing[text.lower()].remove(qid)
            if not existing[text.lower()]:
                del existing[text.lower()]
        if len(retired) > len(retiring):
            print(f"Retired rosters: {len(retired) - len(retiring)} already off the Club picker "
                  "(hidden, no show rule; still in question 18's sum)")

    # --- reconcile clubs (grouped case-insensitively) ----------------------
    sheet_by_name = defaultdict(list)
    for (partner, club), roster in sheet.items():
        sheet_by_name[club.lower()].append((partner, club, roster))

    club_questions, partner_of = {}, {}
    pair_of = {}     # qid -> (partner, club) of the Roster club its question was matched to
    to_create, to_update = [], []

    def claim(qid, partner, club, roster, check_names=False):
        """This existing question is that Roster club's."""
        options = "|".join(roster)
        club_questions[qid] = club
        pair_of[qid] = (partner, club)
        if questions[qid]["options"] != options and (partner, club) not in frozen:
            if check_names and roster_overlap(qid, roster) == 0:
                warn(f"  ! '{club}' (q{qid}): proposed roster "
                     "shares NO names with the current one - "
                     "verify it is the same club before "
                     "applying")
            to_update.append((qid, club, options))

    for low, entries in sorted(sheet_by_name.items()):
        qids = list(existing.get(low, []))
        if len(entries) == 1 and len(qids) <= 1:
            partner, club, roster = entries[0]
            if not qids:
                to_create.append((club, partner, "|".join(roster)))
                continue
            qid = qids[0]
            theirs = current_partner_of.get(qid)
            if not theirs or same_partner(theirs, partner) or loosely(low)(theirs, partner):
                claim(qid, partner, club, roster, check_names=True)
            elif roster_overlap(qid, roster) >= 0.5:
                # another partner in its rule (or, for a plain roster, in the
                # Roster's earlier rows), the same girls: the same club, its
                # partner respelled or the club moved - never a second roster
                if qid in inferred:
                    warn(f"  ! '{club}' (q{qid}): the Roster's earlier rows give it to the partner "
                         f"'{theirs}', the sheet says '{partner}' - the same girls, so the same "
                         "club (the club was moved, or the partner respelled?)")
                else:
                    warn(f"  ! '{club}' (q{qid}): its rule names the partner '{theirs}', the sheet "
                         f"says '{partner}' - the same girls, so the same club (the partner was "
                         "respelled?)")
                claim(qid, partner, club, roster)
            else:
                # the same name, a DIFFERENT partner's club: the existing roster
                # is left as it is (the loop below keeps it), and the newcomer
                # goes to the same-name check further down
                to_create.append((club, partner, "|".join(roster)))
            continue

        # the same club name under several partners (or several questions):
        # match each sheet entry to an existing question by, in order, (1) the
        # partner its rule names (or, for a plain roster, the Roster's rows
        # give it to), exactly; (2) that partner, loosely; (3) roster
        # similarity, the best match first over every entry and question still
        # open - never first come in partner order. Each step runs over every
        # entry before the next, so a loose match never takes a question
        # another entry matches exactly. Entries left over are new clubs.
        entries = sorted(entries)
        unclaimed, taken = list(qids), {}
        for test in (same_partner, loosely(low)):
            for i, (partner, _club, _roster) in enumerate(entries):
                if i in taken:
                    continue
                qid = next((q for q in unclaimed if q in current_partner_of
                            and test(current_partner_of[q], partner)), None)
                if qid is not None:
                    taken[i] = qid
                    unclaimed.remove(qid)
        scored = sorted(((roster_overlap(q, roster), shared_names(q, roster)[0], -i, q)
                         for i, (_, _, roster) in enumerate(entries) if i not in taken
                         for q in unclaimed), reverse=True)
        for score, _, i, q in scored:         # a tie goes to the first entry, as before
            if score >= 0.5 and -i not in taken and q in unclaimed:
                taken[-i] = q
                unclaimed.remove(q)
        for i, (partner, club, roster) in enumerate(entries):
            if i in taken:
                claim(taken[i], partner, club, roster)
            else:
                to_create.append((club, partner, "|".join(roster)))
        for qid in unclaimed:
            club = form_text[qid]
            if not keep_or_prune(qid):
                continue
            warn(f"  ! '{club}' (q{qid}) matched no partner in the sheet - "
                 "keeping it, but check it in the builder")
            club_questions[qid] = club

    # clubs on the form but not in the sheet: keep them working, just warn
    # (an incomplete export looks the same - always export the FULL tab) -
    # unless the Roster says they belong to another region and we are pruning
    pruned = {q for q, _, _ in to_delete}
    for _low, qids in sorted(existing.items()):
        for qid in qids:
            if qid in club_questions or qid in pruned:
                continue
            if not keep_or_prune(qid):
                continue
            club_questions[qid] = form_text[qid]
            warn(f"  ? '{form_text[qid]}' (q{qid}) is on the form but "
                 "not in the sheet export - keeping its current roster")

    # --- retired rosters coming back ------------------------------------------
    # A claimed roster with no show rule and no Club picker entry (its plain
    # text or a long name of its own) is a retired roster whose club is active
    # again and whose partner is not marked `no` - or a new roster of an apply
    # that stopped between the question writes and the picker and conditions
    # writes. With --partners both are one path: the ordinary matching above
    # claimed it, so it gets its entry and rule back (and an options update if
    # the Roster moved on). Without --partners the two cannot be told apart from
    # a roster that should stay retired: the dry run says so per roster and
    # --apply refuses (below); so does an export without the jotform column
    # (nobody can be marked in it: a renamed header would lift every mark). The
    # enrollment path (no --roster) has no marker, and a form without the picker
    # (none is live) has no entry to be off: both keep their old behaviour.
    restored = {}    # qid -> {"club", "partner", "reason"}
    if args.roster and has_picker:
        for qid in sorted(pair_of, key=int):
            text = form_text[qid]
            if qid not in current_value and not picker_entries(text, pair_of[qid][0]):
                restored[qid] = {"club": text, "partner": pair_of[qid][0], "reason": RESTORED_WHY}
                if args.partners:
                    print(f"  ~ restored roster '{text}' (q{qid}): {RESTORED_WHY}")
                else:
                    warn(f"  ! '{text}' (q{qid}) has no Club picker entry and no show rule although its "
                         "club is active in the Roster - a retired roster, or a new roster of an apply "
                         "that stopped half-way: pass --partners <Partners export> (the runner always "
                         "does) and the run restores it or keeps it retired")
        if restored and not args.partners and args.apply:
            sys.exit(f"Refusing: {len(restored)} roster(s) would be restored without a Partners export "
                     "(the '!' lines above) - nothing written. Pass --partners <Partners export> and run "
                     "again: the run restores each roster, or keeps it retired")
        if restored and args.partners and not marker and args.apply:
            sys.exit(f"Refusing: {len(restored)} roster(s) would be restored from a Partners export that "
                     f"has no '{JOTFORM_COL}' column (nobody can be marked in it) - nothing written. Check "
                     f"the Partners tab's header (Partners!D1 = {JOTFORM_COL}), export it again and run again "
                     "(docs/RUNBOOK.md, \"Clubs that do not use Jotform\")")

    # --- what each roster sends to question 5 --------------------------------
    # (docs/plans/2026-09-30-same-name-clubs.md) option_of: qid -> the text its
    # rule tests. With the Club picker that is its picker entry, its calcValue,
    # a club-guard term, question 5 and the club's Salesforce Account name: one
    # string, the plain club name or "<club> - <partner>". The form a roster
    # has today is STICKY: the sync never flips one between plain and long on
    # its own (a namesake going inactive, or a new one arriving, changes
    # nothing for it). Only --same-name-switch, by hand, makes long the
    # rosters whose name two or more partners' ACTIVE clubs share - in any
    # region: Salesforce is one org. Without a picker question 5 is typed, so
    # the texts stay the club names and the Partner box tells them apart.
    option_of = dict(club_questions)
    sf_changes = []      # {qid, club, old, new, switch}: an existing club's question 5 changes
    # a new club this run is about to refuse below (another partner has its
    # name) is on no form, and sits active in the Roster until someone renames
    # it: it never makes an existing club long in the switch. (One refused on
    # ANOTHER region's form cannot be told from a real namesake there: the
    # RUNBOOK's check before the switch - no open "not added" ATTENTION.)
    newcomers = {(key(p), key(c)) for c, p, _ in to_create
                 if any(k != key(p) for k in holders.get(key(c), {}))}
    if newcomers:
        shared_active = shared_club_names(
            {pc: active for pc, active in pairs.items() if (key(pc[0]), key(pc[1])) not in newcomers},
            active_only=True)
    if has_picker:
        for qid in club_questions:
            text = form_text[qid]
            head = key(text) + SF_NAME_SEP
            if qid not in pair_of:
                # on the form, not in the export: it keeps sending what it sends
                now = sends_now(qid, current_partner_of.get(qid))
                keeps = now and (key(now) == key(text) or key(now).startswith(head))
                option_of[qid] = now if keeps else text
                new_club = text
            else:
                partner, new_club = pair_of[qid]
                now = sends_now(qid, partner)
                # long today: "<its text> - <a partner the Roster has for that
                # club>"; with a partner the Roster does not have, only when the
                # name is one two partners share (that partner respelled) - else
                # it is a club renamed from "X - Y" to "X", which is plain
                long_now = bool(now) and key(now).startswith(head) and (
                    long_name_partner(now, text, holders.get(key(text))) is not None
                    or key(new_club) in shared_any)
                switch = (args.same_name_switch and not long_now
                          and key(new_club) in shared_active)
                # a restored roster has no rule to read: a name two partners have had
                # comes back long (what every roster of a shared name sends since the
                # 2026-09-30 switch), as a question-5 change by hand (RETIRED_OLD)
                back_long = qid in restored and key(new_club) in shared_any
                option_of[qid] = sf_club_name(new_club, partner, long_now or switch or back_long)
            if now and key(now) != key(option_of[qid]):
                # the switch's own change: plain -> long, nothing else different
                by_switch = (qid in pair_of and args.same_name_switch
                             and key(now) == key(new_club)
                             and key(option_of[qid]) == key(sf_club_name(new_club, pair_of[qid][0], True)))
                sf_changes.append({"qid": qid, "club": new_club, "old": now,
                                   "new": option_of[qid], "switch": bool(by_switch)})
            elif qid in restored and key(option_of[qid]) != key(text):
                sf_changes.append({"qid": qid, "club": new_club, "old": RETIRED_OLD,
                                   "new": option_of[qid], "switch": False})

    # --- a new club may not take a name that is in use ------------------------
    # Ryan, 2026-09-30: an existing club's name never changes, so a club to be
    # CREATED whose name another partner's club already has - in any region,
    # whatever its status - is not created; the rest of the run goes on, and
    # the runner raises ATTENTION (the plan's Part 2 has the Club Roster Form
    # handler hold such a club before it reaches the Roster; this is the
    # backstop, and the only check until then). The same for
    # a name a roster on this form already carries or sends, and for a name
    # that is the long name of a club whose name is shared ("Stars - Partner
    # One" as a club's own name).
    same_name_refused = []
    sent = {key(o): q for q, o in option_of.items()}
    texts = {}
    for q in club_questions:
        texts.setdefault(key(form_text[q]), q)
    long_names = {key(sf_club_name(c, p, True)): (p, c) for p, c in pairs
                  if p.strip() and key(c) in shared_any}
    for club, partner, options in list(to_create):
        others = [p for k, p in sorted(holders.get(key(club), {}).items()) if k != key(partner)]
        if others:
            whose = " and ".join(f"{p}'s club" for p in others)
        elif key(club) in texts:
            whose = f"another club on this form (q{texts[key(club)]})"
        elif key(club) in sent:
            whose = f"what q{sent[key(club)]} sends as its Club Name"
        elif key(club) in long_names:
            whose = "what {}'s club '{}' sends as its Club Name".format(*long_names[key(club)])
        else:
            continue
        to_create.remove((club, partner, options))
        same_name_refused.append({"club": club, "partner": partner, "others": others})
        warn(f"  ! new club '{club}' ({partner}) has the name of {whose} - {NOT_ADDED}")

    # --- refusals on the texts, before any write ------------------------------
    if has_picker:
        entries = [(o, f"q{q}") for q, o in option_of.items()] + \
                  [(c, f"new club '{c}'") for c, _, _ in to_create]
        bad = sorted(o for o, _ in entries if "|" in o or re.search(r"\{[^{}]*\}", o))
        if bad:
            sys.exit("A Club picker entry may not contain '|' (Jotform's option separator) or "
                     "'{...}' (a calculation reads it as a field): " + ", ".join(repr(b) for b in bad)
                     + " - fix the club's or the partner's spelling in the sheet first")
        groups = defaultdict(list)
        for qid, option in option_of.items():
            groups[key(option)].append(qid)
        for qids in groups.values():
            if len(qids) == 1:
                continue
            # rosters still sharing one entry: only the ones the typed Partner
            # box already tells apart (before --same-name-switch) stay that way
            for qid in qids:
                partner_of[qid] = pair_of[qid][0] if qid in pair_of else rule_partner(qid)
            if not all(q in gated and partner_of[q] for q in qids):
                sys.exit(f"{len(qids)} rosters ({', '.join('q' + q for q in sorted(qids, key=int))}) "
                         f"would share the Club picker entry '{option_of[qids[0]]}', and one "
                         "entry can show one roster. If they are two partners' clubs of one "
                         "name, run with --same-name-switch (each gets its own entry, "
                         "'<club> - <partner>'); if one is a leftover question, delete it in "
                         "the builder")
        # a roster that BECOMES long in this run may not take a name that is
        # another club's own ("Stars" of Partner One becoming "Stars - Partner
        # One" while a club is literally named that). One that already sends
        # it is left alone: the existing name wins, the newcomer is refused above
        for c in sf_changes:
            theirs = sorted(holders.get(key(c["new"]), {}).values())
            if theirs and key(c["new"]) != key(c["club"]):
                sys.exit(f"'{c['club']}' (q{c['qid']}) would send '{c['new']}' to question 5, which "
                         f"is the name of {theirs[0]}'s club - Salesforce could not tell the two "
                         "apart. One of the two needs a different name first")
        gated_now = sorted((q for q in partner_of), key=int)
        long_qids = [q for q, o in option_of.items() if key(o) != key(form_text[q])
                     and key(o).startswith(key(form_text[q]) + SF_NAME_SEP)]
        if args.same_name_switch:
            # a roster that is not in the export (a retired club's question left on
            # the form) keeps what it sends: beside long-named rosters of its text it
            # would be alone on the plain entry - the familiar name, first in the
            # list, showing a retired club's girls and sending the plain name
            long_texts = {key(form_text[q]) for q in long_qids}
            left = sorted((q for q, o in option_of.items() if q not in pair_of
                           and key(o) == key(form_text[q]) and key(o) in long_texts), key=int)
            if left:
                sys.exit(f"{', '.join('q' + q for q in left)} would keep the plain Club picker entry "
                         f"'{option_of[left[0]]}' beside the long ones: it is not in the Roster "
                         "export (a retired club's leftover question?), and a mentor picking the "
                         "familiar name would get its girls. Delete the leftover question in the "
                         "builder first, then run the switch again")
        if long_qids:
            print(f"Same-name clubs: {len(long_qids)} roster(s) on this form send "
                  "'<club> - <partner>' to question 5 (each has its own Club picker entry)")
        if gated_now:
            print(f"Partner box: {len(gated_now)} rosters share a Club picker entry with another "
                  f"roster and are told apart by the typed Partner box (q{PARTNER}); "
                  "--same-name-switch gives each its own entry")
        elif args.same_name_switch and not any(c["switch"] for c in sf_changes):
            print("  - --same-name-switch: nothing to switch - no roster on this form has a name "
                  "two partners' active clubs share and still sends the plain name")
    else:
        # every club sharing a (case-insensitive) name with another MUST have a
        # partner for its rule: the sheet's, or the one in the form's current
        # rules for a club that came from the form side
        name_groups = defaultdict(list)
        for qid, name in club_questions.items():
            name_groups[name.lower()].append(qid)
        for _low, qids in name_groups.items():
            if len(qids) > 1:
                for qid in qids:
                    partner_of[qid] = pair_of[qid][0] if qid in pair_of else rule_partner(qid)
                    if not partner_of[qid]:
                        sys.exit(f"Cannot disambiguate '{club_questions[qid]}' "
                                 f"(q{qid}): no partner in the sheet or the "
                                 "form's current rules. Make sure the export "
                                 "includes every club's enrollment row.")

    # a change of what an EXISTING club sends to question 5 is a change of its
    # Salesforce Account name: listed on every run, and written only by hand
    for c in sf_changes:
        others = [p for k, p in sorted(holders.get(key(c["new"]), {}).items())
                  if c["qid"] not in pair_of or k != key(pair_of[c["qid"]][0])]
        warn(f"  ! '{c['club']}' (q{c['qid']}): {Q5_CHANGES} from '{c['old']}' to '{c['new']}'"
             + ("" if c["switch"] else " - rename its Salesforce account first; an --apply "
                                       "needs --q5-change-ok")
             + (f" ({others[0]} has a club of that name too)"
                if others and not c["switch"] and c["qid"] in pair_of else ""))
    unasked = [c for c in sf_changes if not c["switch"]]
    if unasked and args.apply and not args.q5_change_ok:
        sys.exit(f"Refusing: question 5 (what Salesforce reads) would change for {len(unasked)} "
                 "existing club(s) (the '!' lines above) - nothing written. Rename each "
                 "Salesforce account first, then run again with --q5-change-ok")

    # --- where new rosters go: above the links and Submit (glow/layout.py) -
    # computed before the first write: two Submit buttons are a refusal
    slot = None
    if to_create:
        slot, fence = roster_slot(questions)
        if fence is None:
            print(f"New rosters go at order {slot}, the end of the form (no Submit button "
                  "or link found)")
        else:
            print(f"New rosters go at order {slot}, above {layout_label(fence)}")
            if slot == links_order_of(fence):
                warn(f"  ! new rosters take the order of {layout_label(fence)} ({slot}): Jotform "
                     "inserts them there and moves it down; if it ever kept both at that order "
                     "they would render below it - tools/form_status.py would say so")

    # --- prune other regions' clubs (fresh clones only) --------------------
    for qid, club, reg in to_delete:
        jf.delete(f"/question/{qid}", f"DELETE roster '{club}' (q{qid}, belongs to {reg})")

    # --- write roster changes ----------------------------------------------
    used_names = {q.get("name", "") for q in questions.values()}
    pending = []    # (club, partner) of rosters not created (a dry run)
    for club, partner, options in to_create:
        slug = re.sub(r"[^A-Za-z0-9]", "", club)[:56] or "club"
        n = 1
        while (slug if n == 1 else f"{slug}{n}") in used_names:
            n += 1
        slug = slug if n == 1 else f"{slug}{n}"
        used_names.add(slug)
        fields = {
            "question[type]": "control_checkbox",
            "question[text]": club,
            "question[name]": slug,
            "question[order]": str(slot),
            "question[hidden]": "Yes",
            "question[options]": options,
        }
        if glow_sync.ROSTERS_REQUIRED:      # off: Jotform's default, "No"
            fields["question[required]"] = "Yes"
        content = jf.post_form("/questions", fields,
                               f"CREATE roster '{club}' ({options.count('|')+1} girls)")
        if content:
            qid = str(content["qid"])  # API returns new qids as integers
            club_questions[qid] = club
            option_of[qid] = club      # a new club always sends its own, plain name
            pair_of[qid] = (partner, club)
        else:
            pending.append((club, partner))
    # the required flag (glow/sync.py ROSTERS_REQUIRED): with an options update in
    # the same write (the POST merges), else on its own, LAST in the run (below) - a
    # line the runner never applies unattended, so making every roster required is a
    # hand apply per form
    want_required = glow_sync.roster_required()

    def required_differs(qid):
        return (questions[qid].get("required") or "No") != want_required

    for qid, club, options in to_update:
        fields, also = {"question[options]": options}, ""
        if required_differs(qid):
            fields["question[required]"] = want_required
            also = f"; required: {want_required}"
        jf.post_form(f"/question/{qid}", fields,
                     f"UPDATE roster '{club}' (q{qid}, {options.count('|')+1} girls{also})")
    updated = {q for q, _, _ in to_update}
    to_require = [(qid, club_questions[qid]) for qid in sorted(club_questions, key=int)
                  if qid in questions and qid not in updated and required_differs(qid)]

    # --- the Club picker: its options are always exactly what the rosters' rules test ---
    picker_names = {}   # one entry per distinct text (rosters still told apart by the
    for name in list(option_of.values()) + [c for c, _, _ in to_create]:   # Partner box share one)
        picker_names.setdefault(name.lower(), name)
    picker_list = sorted(picker_names.values(), key=str.lower)   # the rules test these spellings
    picker_options = "|".join(picker_list)
    if guard_on:
        for a, b, c in joined_clashes(picker_list):
            warn(f"  ! picking '{a}' and '{b}' fills Club Name with '{c}', another club on this "
                 "form - the club guard cannot tell that pair from one club")
    if picker_qid is None and args.club_picker:
        fields = {"question[type]": "control_dropdown", "question[name]": PICKER_NAME,
                  "question[order]": str(questions[CLUB_NAME].get("order", "3")),
                  "question[options]": picker_options}
        fields.update({f"question[{k}]": v for k, v in PICKER_PROPS.items()})
        content = jf.post_form("/questions", fields,
                               f"CREATE club picker ({len(picker_names)} clubs)")
        if isinstance(content, dict) and content.get("qid"):
            picker_qid = str(content["qid"])
        jf.post_form(f"/question/{CLUB_NAME}",
                     {"question[hidden]": "Yes", "question[required]": "No"},
                     f"HIDE clubName textbox (q{CLUB_NAME}: filled from the picker; "
                     "Salesforce keeps reading it)")
    elif picker_qid is not None:
        current = questions[picker_qid]
        drift = {k: v for k, v in PICKER_PROPS.items() if current.get(k) != v}
        if current.get("options") != picker_options:
            drift["options"] = picker_options
        # calcValues = the options, aligned (the q5 copy reads them): with the guard,
        # and whenever the picker carries some - unaligned, they would copy a
        # neighbouring club into question 5 (a guard rolled back, a new club added)
        calc = picker_calc_values(picker_list)
        if (guard_on or has_calc_values(current)) and (current.get("calcValues") or "") != calc:
            drift["calcValues"] = calc
        if drift:
            jf.post_form(f"/question/{picker_qid}",
                         {f"question[{k}]": v for k, v in drift.items()},
                         f"UPDATE club picker ({len(picker_names)} clubs: "
                         f"{', '.join(sorted(drift))})")

    # --- the club guard: the warning below the picker, kept in shape ---------
    guard_field = None
    if guard_on and guard_qid is None:
        # a create at a taken order inserts (the picker took q5's order 3, q5 is now
        # 4): the order after the picker's puts the warning directly below it.
        # glow.links.order_of, the one form_status checks the placement with
        fields = {"question[type]": "control_text", "question[name]": GUARD_NAME,
                  "question[order]": str(links_order_of(questions[picker_qid]) + 1)}
        fields.update({f"question[{k}]": v for k, v in GUARD_PROPS.items()})
        content = jf.post_form("/questions", fields, "CREATE club guard (below the Club picker)")
        if not args.apply:
            guard_field = "NEW_GUARD"
        elif isinstance(content, dict) and content.get("qid"):
            guard_field = guard_qid = str(content["qid"])
        else:   # the element, hidden, waits for the re-run; no rule may point at nothing
            warn("  ! the club guard was created but Jotform's answer carried no question id - "
                 "this run writes no guard rules; run the same command again (it finds the "
                 "guard by name)")
    elif guard_on:
        current = questions[guard_qid]
        drift = {k: v for k, v in GUARD_PROPS.items() if current.get(k) != v}
        if drift:
            jf.post_form(f"/question/{guard_qid}",
                         {f"question[{k}]": v for k, v in drift.items()},
                         f"UPDATE club guard ({', '.join(sorted(drift))})")
        guard_field = guard_qid

    # --- the module dropdowns' calcValues (glow/sync.py MODULE_CALC_VALUES) --
    # their own options, so question 98 (module_id, what Salesforce stores) copies
    # the option itself, never its visible text, which a browser's page translation
    # rewrites. Kept in step on every run; off, they are cleared. The runner never
    # applies these lines unattended: the first rollout is by hand, template first,
    # and afterwards a difference means a module dropdown was edited in the builder.
    # The special-event options a dropdown lacks (glow/sync.py SPECIAL_EVENTS) are
    # appended in the same write - options and calcValues never out of step on the
    # form - and held by the runner the same way (tools/auto_sync.py MODULE_RX)
    module_values = []
    for year, mqid in MODULES.items():
        current = questions[mqid]
        options, added = module_options[year], events[year]["add"]
        want = glow_sync.module_calc_values(options)
        same = (current.get("calcValues") or "") == want or (not want and not has_calc_values(current))
        if same and not added:
            continue
        fields = {"question[options]": "|".join(options)} if added else {}
        if not same:
            fields["question[calcValues]"] = want
        # the calcValues part says what is written: aligned ("set"), cleared - or, with the
        # options alone, already right ("unchanged") or none while MODULE_CALC_VALUES is off
        calc = ("set" if want else "cleared") if not same else "unchanged" if want else "none"
        module_values.append({"qid": mqid, "year": year, "modules": len(options) if calc == "set" else 0,
                              "events": added, "calc": calc})
        jf.post_form(f"/question/{mqid}", fields,
                     f"UPDATE module dropdown (q{mqid}, year {year}: "
                     + (f"{len(added)} event option(s) added ({', '.join(added)}); " if added else "")
                     + "calcValues " + (f"= its {len(options)} options" if calc == "set" else calc) + ")")

    # --- regenerate all conditions -----------------------------------------
    # The API stores each condition's terms/action as JSON-encoded STRINGS
    # (that is what GET returns and what the builder saves) - encode them.
    # each roster's rule tests its own text (option_of); partner_of holds only the
    # rosters that still share one text and are told apart by the typed Partner box
    conds = build_conditions(option_of, partner_of, module_options,
                             picker=picker_qid or ("NEW" if args.club_picker else None),
                             picker_options=picker_list, guard=guard_field,
                             submit=submit_qid if guard_field else None, retired=retired)
    # The typed Partner box has nothing left to do on a picker form once no rule
    # shows it (every same-name club has its own entry, or the form has none):
    # unhidden, every mentor sees an optional "Partner" box. Hidden, it is still
    # submitted, blank - the staff notification e-mail's Partner row goes empty.
    hide_box = (has_picker and PARTNER in questions
                and questions[PARTNER].get("hidden") != "Yes"
                and not any(a.get("visibility") == "Show" and str(a.get("field")) == PARTNER
                            for c in conds for a in c["action"]))
    if not (to_create or to_update or to_delete) and \
            same_conditions(props.get("conditions", []), conds):
        print("  (conditions unchanged - skipping the rewrite)")
    else:
        kept, new, dropped = rule_delta(props.get("conditions", []), conds)
        print(f"  conditions: {kept} kept, {new} new, {dropped} dropped")
        wire = [{"id": c["id"], "type": c["type"], "link": c["link"],
                 "priority": c["priority"], "index": c["index"],
                 "terms": json.dumps(c["terms"]),
                 "action": json.dumps(c["action"])} for c in conds]
        label = f"REPLACE conditions ({len(conds)} rules"
        if to_create and not args.apply:
            label += f" + ~{len(to_create)} more once the new rosters exist"
        jf.put_json("/properties", {"properties": {"conditions": wire}}, label + ")")

    # the typed box goes only after the rules stopped testing it: a failure
    # before this point leaves the form working on the box
    if hide_box:
        jf.post_form(f"/question/{PARTNER}", {"question[hidden]": "Yes", "question[required]": "No"},
                     f"HIDE partner textbox (q{PARTNER}: no rule shows it; clubs that share a "
                     "name have their own Club picker entry)")

    # the required flag alone, one write per roster (the first rollout: every roster on the
    # form - Africa 220, the template 359), after everything else: a run that stops in this
    # tail leaves no new roster without its rule, and its re-run lists only what is left
    for qid, club in to_require:
        jf.post_form(f"/question/{qid}", {"question[required]": want_required},
                     f"REQUIRED roster '{club}' (q{qid}: {want_required})")

    # --- what each club sends to Salesforce, for --summary-json --------------
    spelled = {o.lower(): o for o in picker_list} if has_picker else {}
    sf_names = [{"qid": q, "club": club_questions[q], "value": spelled.get(o.lower(), o),
                 "partner": pair_of[q][0] if q in pair_of else rule_partner(q)}
                for q, o in sorted(option_of.items(), key=lambda kv: int(kv[0]))]
    sf_names += [{"qid": None, "club": c, "value": c, "partner": p} for c, p in pending]

    # --- report ------------------------------------------------------------
    mode = "APPLIED" if args.apply else "DRY RUN (use --apply to write)"
    print(f"\n{mode}:")
    for call in jf.calls:
        print(f"  - {call}")
    if not jf.calls:
        print("  nothing to do - form already matches the sheet")

    if args.summary_json:
        summary = {
            "form": args.form, "region": args.region, "apply": args.apply,
            "roster_clubs": len(sheet),
            "roster_girls": sum(len(v) for v in sheet.values()),
            "creates": [{"club": c, "partner": p, "girls": o.count("|") + 1}
                        for c, p, o in to_create],
            "updates": [{"qid": q, "club": c, "girls": o.count("|") + 1}
                        for q, c, o in to_update],
            "deletes": [{"qid": q, "club": c, "region": r} for q, c, r in to_delete],
            # rosters whose required flag alone is written (no other change to them)
            "requires": [{"qid": q, "club": c, "required": want_required} for q, c in to_require],
            # module dropdowns written: calc set (modules: how many) / cleared / unchanged / none,
            # and the special-event options appended (events)
            "module_values": module_values,
            # rosters this plan takes off the picker (kept hidden, no show rule), how many
            # the form already holds retired, retired rosters restored to the picker, and
            # the Partners export the marker came from
            "retired": [dict(qid=q, **retiring[q]) for q in sorted(retiring, key=int)],
            "retired_before": len(retired) - len(retiring),
            "restored": [dict(qid=q, **restored[q]) for q in sorted(restored, key=int)],
            "partners": args.partners,
            "rules": len(conds), "warnings": list(WARNINGS), "calls": list(jf.calls),
            "club_picker": picker_qid, "club_guard": guard_qid,
            # what every roster on the form sends to question 5 after this plan = the
            # club's Salesforce Account name (the picker's spelling); a club not created
            # yet (a dry run) has no qid. tools/auto_sync.py compares these across regions
            "sf_names": sf_names,
            "sf_name_changes": sf_changes,
            "same_name_refused": same_name_refused,
            "plan_hash": hashlib.sha1("\n".join(sorted(jf.calls)).encode()).hexdigest(),
        }
        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=1)

if __name__ == "__main__":
    run(main)
