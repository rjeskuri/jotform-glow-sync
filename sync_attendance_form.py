#!/usr/bin/env python3
"""
Sync the GLOW Attendance Form (Jotform) from the enrollment Google Sheet.

The Google Sheet (club enrollment responses) is the single source of truth.
This script reads a CSV export of that sheet and makes the Jotform form match:

  1. Creates a hidden roster checkbox question for any club that doesn't have
     one yet (options = the girls' names from the sheet).
  2. Updates the roster options of existing club questions when the sheet
     changed (new girls enrolled, corrections).
  3. Regenerates ALL conditional logic from scratch, in three categories:
       A. ROSTER VISIBILITY  - clubName == "<club>" -> show that roster
                               (same-named clubs from different partners are
                               disambiguated with the Partner box)
       B. CURRICULUM CASCADE - GLOW year -> module dropdown;
                               year+module -> session dropdown (8/10/14/15)
       C. SALESFORCE BRIDGE  - one aggregate Contact_IDs calculation +
                               module_id / week_id / year_id copies

Usage:
    export JOTFORM_API_KEY=...
    python3 sync_attendance_form.py enrollment.csv --form 262352490535154            # dry run (default)
    python3 sync_attendance_form.py enrollment.csv --form 262352490535154 --apply    # write changes

    # From the Roster tab of the master enrollment sheet (one row per girl),
    # one region only, deleting clubs that belong to OTHER regions - meant
    # for a fresh clone (refused on any form that has submissions):
    python3 sync_attendance_form.py roster.csv --roster --region Africa --prune --form <CLONE_ID> --apply

Getting enrollment.csv: in Google Sheets, File > Download > Comma Separated
Values (.csv) on the responses tab. Getting roster.csv:
    python3 tools/sheets_client.py export Roster data/roster_<date>.csv

Requires: Python 3.8+, no third-party packages.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

API_BASE = "https://api.jotform.com"

# ---------------------------------------------------------------- sheet layout
# Column headers in the enrollment sheet (matched loosely, case-insensitive).
COL_PARTNER = "partner organization name"
COL_CLUB = "club name"
COL_ROSTER = "please list the full name"

# ------------------------------------------------------------- fixed field ids
# Structural fields of the master form. If the form is ever rebuilt from
# scratch, update these ids (GET /form/{id}/questions to look them up).
CLUB_NAME = "5"      # Club Name textbox (matched by the visibility rules)
PARTNER = "331"      # Partner textbox (shown only for ambiguous club names)
YEAR = "94"          # GLOW Club Year dropdown (1|2|3)
MODULES = {"1": "14", "2": "92", "3": "93"}       # year -> module dropdown qid
WEEKS = {8: "15", 10: "95", 14: "96", 15: "97"}   # session count -> dropdown qid
CONTACT_IDS, MODULE_ID, WEEK_ID, YEAR_ID = "18", "98", "100", "102"

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

# ------------------------------------------------------------------ id minting
_counter = [0]
ID_BASE = 1758000000000

def next_id():
    _counter[0] += 1
    return str(ID_BASE + _counter[0])

# ------------------------------------------------------------------- API layer
class Jotform:
    def __init__(self, api_key, form_id, apply_changes=False):
        self.key = api_key
        self.form = form_id
        self.apply = apply_changes
        self.calls = []

    def _url(self, path):
        return f"{API_BASE}/form/{self.form}{path}?apiKey={self.key}"

    def _curl(self, args, label):
        out = subprocess.run(["curl", "-sS", "--fail-with-body"] + args,
                             capture_output=True, text=True)
        try:
            resp = json.loads(out.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"{label}: non-JSON response: "
                               f"{out.stdout[:300]} {out.stderr[:300]}")
        if resp.get("responseCode") != 200:
            raise RuntimeError(f"{label}: {resp.get('responseCode')} "
                               f"{resp.get('message')}")
        return resp["content"]

    def get(self, path):
        return self._curl([self._url(path)], f"GET {path}")

    def post_form(self, path, data, label):
        """form-urlencoded POST (question create/update)."""
        self.calls.append(label)
        if not self.apply:
            return None
        args = ["-X", "POST", self._url(path)]
        for k, v in data.items():
            args += ["--data-urlencode", f"{k}={v}"]
        return self._curl(args, label)

    def put_json(self, path, payload, label):
        """JSON PUT (properties update)."""
        self.calls.append(label)
        if not self.apply:
            return None
        return self._curl(["-X", "PUT", self._url(path),
                           "-H", "Content-Type: application/json",
                           "--data-binary", json.dumps(payload)], label)

    def delete(self, path, label):
        """DELETE (question removal - only ever used with --prune)."""
        self.calls.append(label)
        if not self.apply:
            return None
        return self._curl(["-X", "DELETE", self._url(path)], label)

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

# --------------------------------------------------------- condition builders
def mk_term(field, operator, value=""):
    return {"id": f"term_{next_id()}", "field": str(field),
            "operator": operator, "value": value, "isError": False}

def mk_show(field):
    return {"id": f"action_{next_id()}", "visibility": "Show",
            "isError": False, "field": str(field)}

def mk_field_rule(terms, actions, link="Any"):
    return {"id": next_id(), "type": "field", "link": link,
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

def build_conditions(club_questions, partner_of, module_options):
    """club_questions: {qid: club display name}; partner_of: {qid: partner}
    for clubs whose name is shared by several partners."""
    conds = []

    # A. roster visibility
    # ambiguity is judged case-insensitively because Jotform's runtime
    # "equals" ignores case ("SUPER GIRLS" would also match "Super Girls")
    by_name = defaultdict(list)
    for qid, name in club_questions.items():
        by_name[name.lower()].append(qid)
    for qid, name in sorted(club_questions.items(), key=lambda kv: int(kv[0])):
        if len(by_name[name.lower()]) > 1:
            conds.append(mk_field_rule(
                [mk_term(PARTNER, "equals", partner_of[qid]),
                 mk_term(CLUB_NAME, "equals", name)],
                [mk_show(qid)], link="All"))
        else:
            conds.append(mk_field_rule([mk_term(CLUB_NAME, "equals", name)],
                                       [mk_show(qid)]))
    for low, qids in sorted(by_name.items()):
        if len(qids) > 1:  # ambiguous name -> reveal the Partner box
            conds.append(mk_field_rule(
                [mk_term(CLUB_NAME, "equals", club_questions[qids[0]])],
                [mk_show(PARTNER)]))

    # B. curriculum cascade
    for year, module_qid in MODULES.items():
        conds.append(mk_field_rule([mk_term(YEAR, "equals", year)],
                                   [mk_show(module_qid)]))
    conds.append(mk_field_rule([mk_term(YEAR, "equals", "1")],
                               [mk_show(WEEKS[8])]))  # every year-1 module is 8 sessions
    for year in ("2", "3"):
        for module in module_options[year]:
            n = SESSION_OVERRIDES.get(module, 8)
            conds.append(mk_field_rule(
                [mk_term(MODULES[year], "equals", module),
                 mk_term(YEAR, "equals", year)],
                [mk_show(WEEKS[n])], link="All"))

    # C. salesforce bridge
    conds.append(mk_calc_rule([mk_term(YEAR, "isFilled")], YEAR_ID,
                              YEAR, "{%s}" % YEAR))
    for module_qid in MODULES.values():
        conds.append(mk_calc_rule([mk_term(module_qid, "isFilled")], MODULE_ID,
                                  module_qid, "{%s}" % module_qid))
    for week_qid in WEEKS.values():
        conds.append(mk_calc_rule([mk_term(week_qid, "isFilled")], WEEK_ID,
                                  week_qid, "{%s}" % week_qid))
    roster_qids = sorted(club_questions, key=int)
    conds.append(mk_calc_rule(
        [mk_term(CLUB_NAME, "isFilled")], CONTACT_IDS,
        ",".join(roster_qids), "".join("{%s}" % q for q in roster_qids),
        ignore_hidden=True, as_text=True))

    for i, c in enumerate(conds):
        c["index"] = str(i)
        c["priority"] = str(i)
    return conds

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
    ap.add_argument("--prune", action="store_true",
                    help="with --region: DELETE club questions that the Roster "
                         "places in another region (fresh clones only)")
    ap.add_argument("--summary-json", metavar="PATH",
                    help="also write a machine-readable summary of the plan to PATH "
                         "(used by tools/auto_sync.py)")
    args = ap.parse_args()
    if args.region and not args.roster:
        sys.exit("--region needs --roster (the Roster tab is what carries regions)")
    if args.prune and not args.region:
        sys.exit("--prune needs --region")

    api_key = os.environ.get("JOTFORM_API_KEY") or sys.exit(
        "Set JOTFORM_API_KEY in the environment")
    jf = Jotform(api_key, args.form, args.apply)

    all_clubs, region_of = {}, {}
    if args.roster:
        sheet, all_clubs, region_of = read_roster_csv(args.csv, args.region)
        dup_names = {}
        print(f"Roster: {len(sheet)} active clubs"
              f"{' in ' + args.region if args.region else ''} "
              f"({sum(len(v) for v in sheet.values())} girls); "
              f"{len(all_clubs)} clubs overall")
    else:
        sheet, dup_names = read_sheet(args.csv)
        print(f"Sheet: {len(sheet)} clubs "
              f"({sum(len(v) for v in sheet.values())} girls total)")

    if args.prune:
        info = jf.get("")
        if int(info.get("count") or 0) > 0:
            msg = (f"form {args.form} already has {info['count']} submission(s); "
                   "--prune is for fresh clones only")
            if args.apply:
                sys.exit("Refusing: " + msg)
            warn(f"  ! (preview only) {msg}")

    # clubs whose roster lists the same full name twice: two different girls
    # need a distinguishing suffix in the SHEET before we trust that roster
    frozen = set()
    for key, dups in dup_names.items():
        if dups:
            frozen.add(key)
            warn(f"  ! {key[1]} ({key[0]}): {', '.join(dups)} appears twice "
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

    module_options = {
        year: [o for o in questions[mqid]["options"].split("|") if o]
        for year, mqid in MODULES.items()}

    # partner mapping already encoded in the form's current rules
    # (used to match same-named clubs to their existing questions)
    current_partner_of = {}
    props = jf.get("/properties")
    for cond in props.get("conditions", []):
        if cond.get("type") != "field":
            continue
        terms = json.loads(cond["terms"]) if isinstance(cond["terms"], str) \
            else cond["terms"]
        action = json.loads(cond["action"]) if isinstance(cond["action"], str) \
            else cond["action"]
        pterm = next((t for t in terms if t["field"] == PARTNER
                      and t["operator"] == "equals"), None)
        if pterm:
            for a in action:
                if a.get("visibility") == "Show":
                    current_partner_of[a["field"]] = pterm["value"]

    def partner_matches(a, b):
        """Loose partner-name match: 'WESAD' matches 'World Economy ... (WESAD)'."""
        a, b = norm(a).lower(), norm(b).lower()
        return a and b and (a in b or b in a)

    def roster_overlap(qid, roster):
        have = {norm(o).lower() for o in questions[qid]["options"].split("|") if o}
        want = {n.lower() for n in roster}
        if not have or not want:
            return 0.0
        return len(have & want) / min(len(have), len(want))

    def foreign_region(qid):
        """The region the FULL roster gives this form question's club, when
        it is not the region being synced; None when unknown or the same.
        Same-name clubs are told apart by the partner in the form's rules."""
        if not args.region:
            return None
        name = form_text[qid].lower()
        cands = [k for k in all_clubs if k[1].lower() == name]
        if len(cands) > 1 and qid in current_partner_of:
            cands = [k for k in cands if partner_matches(current_partner_of[qid], k[0])]
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

    # --- reconcile clubs (grouped case-insensitively) ----------------------
    sheet_by_name = defaultdict(list)
    for (partner, club), roster in sheet.items():
        sheet_by_name[club.lower()].append((partner, club, roster))

    club_questions, partner_of = {}, {}
    to_create, to_update = [], []

    for low, entries in sorted(sheet_by_name.items()):
        qids = list(existing.get(low, []))
        if len(entries) == 1 and len(qids) <= 1:
            partner, club, roster = entries[0]
            options = "|".join(roster)
            if qids:
                qid = qids[0]
                if qid in current_partner_of and \
                        not partner_matches(current_partner_of[qid], partner):
                    # same name but a DIFFERENT partner's club: don't overwrite
                    # the existing roster - create a sibling, partner-gated
                    warn(f"  ! '{club}' from {partner} shares its name with "
                         f"q{qid} ({current_partner_of[qid]}) - creating a "
                         "separate roster")
                    club_questions[qid] = form_text[qid]
                    partner_of[qid] = current_partner_of[qid]
                    to_create.append((club, partner, options, True))
                else:
                    club_questions[qid] = club
                    if questions[qid]["options"] != options \
                            and (partner, club) not in frozen:
                        if roster_overlap(qid, roster) == 0:
                            warn(f"  ! '{club}' (q{qid}): proposed roster "
                                 "shares NO names with the current one - "
                                 "verify it is the same club before "
                                 "applying")
                        to_update.append((qid, club, options))
            else:
                to_create.append((club, partner, options, False))
            continue

        # same club name under several partners (or several questions):
        # match each sheet entry to an existing question by, in order,
        # (1) the partner recorded in the form's current rules,
        # (2) roster similarity; entries left over become new questions.
        unclaimed = list(qids)
        for partner, club, roster in sorted(entries):
            options = "|".join(roster)
            qid = next((q for q in unclaimed
                        if q in current_partner_of
                        and partner_matches(current_partner_of[q], partner)),
                       None)
            if qid is None:
                scored = sorted(((roster_overlap(q, roster), q)
                                 for q in unclaimed), reverse=True)
                if scored and scored[0][0] >= 0.5:
                    qid = scored[0][1]
            if qid is not None:
                unclaimed.remove(qid)
                club_questions[qid] = club
                partner_of[qid] = partner
                if questions[qid]["options"] != options \
                        and (partner, club) not in frozen:
                    to_update.append((qid, club, options))
            else:
                to_create.append((club, partner, options, True))
        for qid in unclaimed:
            club = form_text[qid]
            if not keep_or_prune(qid):
                continue
            warn(f"  ! '{club}' (q{qid}) matched no partner in the sheet - "
                 "keeping it, but check it in the builder")
            club_questions[qid] = club
            partner_of[qid] = current_partner_of.get(qid, "")
            if not partner_of[qid]:
                sys.exit(f"Cannot disambiguate '{club}' (q{qid}): no partner "
                         "in the sheet or the form's current rules")

    # clubs on the form but not in the sheet: keep them working, just warn
    # (an incomplete export looks the same - always export the FULL tab) -
    # unless the Roster says they belong to another region and we are pruning
    pruned = {q for q, _, _ in to_delete}
    for low, qids in sorted(existing.items()):
        for qid in qids:
            if qid in club_questions or qid in pruned:
                continue
            if not keep_or_prune(qid):
                continue
            club_questions[qid] = form_text[qid]
            warn(f"  ? '{form_text[qid]}' (q{qid}) is on the form but "
                 "not in the sheet export - keeping its current roster")

    # every club sharing a (case-insensitive) name with another MUST have a
    # partner for its rule; fall back to the form's current rules for clubs
    # that came from the form side rather than the sheet
    name_groups = defaultdict(list)
    for qid, name in club_questions.items():
        name_groups[name.lower()].append(qid)
    for low, qids in name_groups.items():
        if len(qids) > 1:
            for qid in qids:
                if not partner_of.get(qid):
                    partner_of[qid] = current_partner_of.get(qid, "")
                if not partner_of[qid]:
                    sys.exit(f"Cannot disambiguate '{club_questions[qid]}' "
                             f"(q{qid}): no partner in the sheet or the "
                             "form's current rules. Make sure the export "
                             "includes every club's enrollment row.")

    # --- prune other regions' clubs (fresh clones only) --------------------
    for qid, club, reg in to_delete:
        jf.delete(f"/question/{qid}", f"DELETE roster '{club}' (q{qid}, belongs to {reg})")

    # --- write roster changes ----------------------------------------------
    def order_of(q):
        try:
            return int(float(q.get("order", 0)))
        except (TypeError, ValueError):
            return 0
    max_order = max(order_of(q) for q in questions.values())
    used_names = {q.get("name", "") for q in questions.values()}
    for club, partner, options, ambiguous in to_create:
        max_order += 1
        slug = re.sub(r"[^A-Za-z0-9]", "", club)[:56] or "club"
        n = 1
        while (slug if n == 1 else f"{slug}{n}") in used_names:
            n += 1
        slug = slug if n == 1 else f"{slug}{n}"
        used_names.add(slug)
        content = jf.post_form("/questions", {
            "question[type]": "control_checkbox",
            "question[text]": club,
            "question[name]": slug,
            "question[order]": str(max_order),
            "question[hidden]": "Yes",
            "question[options]": options,
        }, f"CREATE roster '{club}' ({options.count('|')+1} girls)")
        if content:
            qid = str(content["qid"])  # API returns new qids as integers
            club_questions[qid] = club
            if ambiguous:
                partner_of[qid] = partner
    for qid, club, options in to_update:
        jf.post_form(f"/question/{qid}", {"question[options]": options},
                     f"UPDATE roster '{club}' (q{qid}, "
                     f"{options.count('|')+1} girls)")

    # --- regenerate all conditions -----------------------------------------
    # The API stores each condition's terms/action as JSON-encoded STRINGS
    # (that is what GET returns and what the builder saves) - encode them.
    conds = build_conditions(club_questions, partner_of, module_options)
    wire = [{"id": c["id"], "type": c["type"], "link": c["link"],
             "priority": c["priority"], "index": c["index"],
             "terms": json.dumps(c["terms"]),
             "action": json.dumps(c["action"])} for c in conds]
    label = f"REPLACE conditions ({len(conds)} rules"
    if to_create and not args.apply:
        label += f" + ~{len(to_create)} more once the new rosters exist"
    jf.put_json("/properties", {"properties": {"conditions": wire}}, label + ")")

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
                        for c, p, o, _ in to_create],
            "updates": [{"qid": q, "club": c, "girls": o.count("|") + 1}
                        for q, c, o in to_update],
            "deletes": [{"qid": q, "club": c, "region": r} for q, c, r in to_delete],
            "rules": len(conds), "warnings": list(WARNINGS), "calls": list(jf.calls),
            "plan_hash": hashlib.sha1("\n".join(sorted(jf.calls)).encode()).hexdigest(),
        }
        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=1)

if __name__ == "__main__":
    main()
