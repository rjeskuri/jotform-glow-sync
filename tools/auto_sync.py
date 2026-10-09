#!/usr/bin/env python3
"""
Keep the regional Jotform attendance forms in step with the Roster tab, unattended.

Runs from GitHub Actions (.github/workflows/auto-sync.yml) when the sheet's
Apps Script reports a roster change (Dispatch.gs), on a daily schedule, or
by hand:

    python3 tools/auto_sync.py                     # dry run: export, plan, report
    python3 tools/auto_sync.py --apply             # also write, within the safety bands
    python3 tools/auto_sync.py --region Asia --roster data/roster_<date>.csv

One run, per region: export the Roster tab -> guards -> dry-run the existing
sync -> if it plans changes and they are within the bands -> back up the
form -> apply -> verify with form_status.py. With --synclog (the workflow
always passes it; local runs write nothing to the sheet by default) every
region's outcome is appended to the sheet's SyncLog tab; the console and
data/auto_sync/<stamp>.log are redacted (girls' names never appear). Exit
0 = every region in sync or applied cleanly; 2 = something needs a human
(ATTENTION.md says what, and an unverified apply counts); 1 = a step failed.

It never passes --prune, never deletes a question, and refuses to apply when
one region would create more than --max-creates clubs or update more than
--max-updates rosters at once, or when the export looks truncated. It never
passes --same-name-switch or --q5-change-ok either: a change of what an
existing club sends to question 5 (its Salesforce Account name) stops that
region and raises ATTENTION, even when nothing else is planned; a new club
the sync did not add because its name is in use, and a name two clubs send,
raise ATTENTION without stopping anything (docs/RUNBOOK.md, "Club names two
partners share"). A conditions rewrite alone is not a change to it, so roster
rules that test a name the Club picker does not list (a restored backup, a
half-finished hand apply) are never "in-sync": ATTENTION, apply by hand. Rules
that calculate question 18 (the names sent to Salesforce) the old way, the
required flag written on a roster that has no other change, and a module
dropdown's calcValues, stop the region (ATTENTION): each is rolled out by hand,
one form at a time, template first (docs/RUNBOOK.md, "The names list sent to
Salesforce" and "The names dictionary and the module values"). The verify step's
form_status also audits the form's names dictionary; a store it could not read
is a note. Once per run, after the regions, Jotform's storage is read against the
account's plan (glow/usage.py): the line is logged, and a limit at 80 % or more -
upload space in all, or submissions in the monthly cycle, each on its own - is an
ATTENTION, because at 100 % Jotform disables the forms (docs/RUNBOOK.md,
"Photos", step 7); a read that fails is a log line, never a failed run.

The Partners tab travels with the Roster (docs/plans/2026-10-06-clubs-off-
jotform.md): the run exports it too and passes --partners to every sync and
verify call, so a partner marked jotform=no has its clubs' rosters retired (kept
hidden, off the Club picker) and a club with no active girl leaves the picker
the day after (days in the sheet's own zone, glow.sync.SHEET_ZONE, which the run
checks against the sheet's setting: ATTENTION when they differ); a local --roster
run needs --partners as well. More than --max-retires retirements or
--max-restores restores in one region in one run is ATTENTION (the first rollout
is by hand); a jotform value other than yes / no / blank is an ATTENTION that
stops nothing; an export without the jotform column is an ATTENTION, and a plan
that would restore a roster from it is held. Before each region the form's status
is read: a form that is not ENABLED is `skipped` (SyncLog), not failed, and
nothing is run against it; a status that cannot be read is `failed`.
"""
import argparse
import csv
import datetime
import json
import os
import re
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
sys.path.insert(0, REPO)
import sheets_client as sc  # noqa: E402  (Google libraries are imported lazily inside it)
from glow import forms as glow_forms  # noqa: E402
from glow import usage  # noqa: E402  (Jotform's storage against the plan's limits; standard library)
from glow.jotform import Client  # noqa: E402  (the one read this file makes itself: the usage)
from glow.sync import SHEET_ZONE, sf_name_clashes  # noqa: E402  (standard library only)
from glow.salesforce import Org, client_credentials  # noqa: E402
import sf_new_clubs as sfn  # noqa: E402  (new clubs' Salesforce accounts, BACKLOG 27)

# The live regional forms (one source: glow/forms.py, parity-tested against
# appsscript/Config.gs by test/gs_parity_test.py).
REGIONAL_FORMS = glow_forms.REGIONALS
ROSTER_TAB = "Roster"
PARTNERS_TAB = "Partners"
SYNC_LOG_TAB = "SyncLog"
# keep in step with SYNC_LOG_COLS in appsscript/Roster.gs
SYNC_LOG_COLS = ["when", "trigger", "region", "mode", "creates", "updates",
                 "rules", "result", "detail", "run_url"]
MIN_LANGUAGES = 12
DEFAULT_OUT = os.path.join(REPO, "data", "auto_sync")

# The sync tool's plan lines (sync_attendance_form.py; test/auto_sync_test.py
# checks these formats still exist there).
CREATE_RX = re.compile(r"^  - CREATE roster '(?P<club>.+)' \((?P<girls>\d+) girls\)$")
# an options update may carry the roster's required flag in the same write
UPDATE_RX = re.compile(r"^  - UPDATE roster '(?P<club>.+)' \(q(?P<qid>\d+), (?P<girls>\d+) girls"
                       r"(?:; required: (?P<required>Yes|No))?\)$")
# ...else it is written on its own: never applied unattended (check_bands)
REQUIRED_RX = re.compile(r"^  - REQUIRED roster '(?P<club>.+)' \(q(?P<qid>\d+): (?P<required>Yes|No)\)$")
DELETE_RX = re.compile(r"^  - DELETE roster '(?P<club>.+)' \(q(?P<qid>\d+), belongs to (?P<region>.+)\)$")
REPLACE_RX = re.compile(r"^  - REPLACE conditions \((?P<rules>\d+) rules")
PICKER_RX = re.compile(r"^  - (?P<op>CREATE|UPDATE) club picker \((?P<clubs>\d+) clubs(?::[^)]*)?\)$")
PARTNER_PICKER_RX = re.compile(r"^  - (?P<op>CREATE|UPDATE) partner picker "
                               r"\((?P<partners>\d+) partners(?::[^)]*)?\)$")
GUARD_RX = re.compile(r"^  - (?P<op>CREATE|UPDATE) club guard \([^)]*\)$")
# a module dropdown's calcValues (glow/sync.py MODULE_CALC_VALUES): never applied unattended
# (check_bands) - the first rollout is by hand, template first; afterwards a difference means
# the dropdown was edited in the builder (docs/plans/2026-10-02-names-and-modules.md)
MODULE_RX = re.compile(r"^  - UPDATE module dropdown \(q(?P<qid>\d+), year (?P<year>\d+): calcValues "
                       r"(?:= its (?P<modules>\d+) options|cleared)\)$")
ROSTER_RX = re.compile(r"^Roster: (?P<clubs>\d+) active clubs.*\((?P<girls>\d+) girls\); "
                       r"(?P<all>\d+) clubs overall")
# a roster retired (kept hidden, off the Club picker, no show rule) or restored to the
# picker (docs/plans/2026-10-06-clubs-off-jotform.md): the picker UPDATE that carries it
# is the counted change; more than --max-retires / --max-restores in one region is a band
RETIRED_RX = re.compile(r"^  ~ retired roster '(?P<club>.+)' \(q(?P<qid>\d+)\): (?P<reason>.+)$")
RESTORED_RX = re.compile(r"^  ~ restored roster '(?P<club>.+)' \(q(?P<qid>\d+)\): (?P<reason>.+)$")
# the Partners tab's jotform cell holds something other than yes / no / blank: read as
# yes (nothing leaves a form for a typo), reported - ATTENTION without stopping the region
JOTFORM_VALUE = "only yes, no or blank are understood"
# the Partners export has no jotform column at all (a renamed or moved header): nobody is
# marked, so a retired roster of an active club reads as "restore me" - ATTENTION, and a
# plan that restores anything from such an export is outside the bands (check_bands)
JOTFORM_COLUMN = "column, so no partner is marked"
NOT_IN_EXPORT = "is on the form but not in the sheet export"
NO_SHARED_NAMES = "shares NO names with the current one"
# Clubs that share a name (docs/plans/2026-09-30-same-name-clubs.md): what an existing
# club sends to question 5 is its Salesforce Account name, so a change of it is never
# applied unattended; and a new club whose name another partner's club has is not created
SF_NAME_CHANGE = "Club Name (question 5, what Salesforce reads) changes"
SAME_NAME_REFUSED = "not added: give it a different name"
# a roster's rule tests a text the picker does not list: that roster does not show, and
# only a conditions rewrite - which the runner does not count as a change - repairs it
RULES_OLDER = "which the Club picker does not list"
# the live rules calculate question 18 (the names Salesforce stores) the old way: the
# rewrite is rolled out by hand, one form at a time, so the region is never applied here
# (docs/plans/2026-09-30-contact-ids.md) - nor the required flag on rosters that have no
# other change (REQUIRED roster lines: on a form not rolled out yet, every roster)
CONTACT_IDS_STALE = "question 18 (Contact_IDs) is not recalculated after the rosters change"


def key(s):
    return " ".join(str(s or "").split()).lower()


# ------------------------------------------------------------ pure functions
def module_entry(m):
    """A MODULE_RX match -> {"qid", "year", "modules"} (modules: 0 = the calcValues cleared)."""
    return {"qid": m["qid"], "year": m["year"], "modules": int(m["modules"] or 0)}


def parse_plan(text):
    """The sync tool's dry-run output -> what it plans to do."""
    plan = {"creates": [], "updates": [], "deletes": [], "requires": [], "picker": [],
            "partner_picker": [], "club_guard": [], "modules": [], "retired": [], "restored": [],
            "rules": None, "warnings": [], "roster_clubs": None, "roster_girls": None,
            "sf_names": None}     # sf_names: only the summary file has them
    for line in text.splitlines():
        m = REQUIRED_RX.match(line)
        if m:
            plan["requires"].append({"qid": m["qid"], "club": m["club"], "required": m["required"]})
            continue
        m = RETIRED_RX.match(line)
        if m:
            plan["retired"].append({"qid": m["qid"], "club": m["club"], "reason": m["reason"]})
            continue
        m = RESTORED_RX.match(line)
        if m:
            plan["restored"].append({"qid": m["qid"], "club": m["club"], "reason": m["reason"]})
            continue
        m = MODULE_RX.match(line)
        if m:
            plan["modules"].append(module_entry(m))
            continue
        m = PICKER_RX.match(line)
        if m:
            plan["picker"].append({"op": m["op"], "clubs": int(m["clubs"])})
            continue
        m = PARTNER_PICKER_RX.match(line)
        if m:
            plan["partner_picker"].append({"op": m["op"], "partners": int(m["partners"])})
            continue
        m = GUARD_RX.match(line)
        if m:
            plan["club_guard"].append({"op": m["op"]})
            continue
        m = CREATE_RX.match(line)
        if m:
            plan["creates"].append({"club": m["club"], "girls": int(m["girls"])})
            continue
        m = UPDATE_RX.match(line)
        if m:
            plan["updates"].append({"qid": m["qid"], "club": m["club"], "girls": int(m["girls"])})
            continue
        m = DELETE_RX.match(line)
        if m:
            plan["deletes"].append({"qid": m["qid"], "club": m["club"], "region": m["region"]})
            continue
        m = REPLACE_RX.match(line)
        if m:
            plan["rules"] = int(m["rules"])
            continue
        m = ROSTER_RX.match(line)
        if m:
            plan["roster_clubs"], plan["roster_girls"] = int(m["clubs"]), int(m["girls"])
            continue
        if line.startswith(("  ! ", "  ? ")):
            plan["warnings"].append(line.strip())
    return plan


def plan_from_summary(summary):
    """The same shape, from the sync tool's --summary-json file."""
    return {"creates": [{"club": c["club"], "girls": c["girls"]} for c in summary.get("creates", [])],
            "updates": [{"qid": u["qid"], "club": u["club"], "girls": u["girls"]}
                        for u in summary.get("updates", [])],
            "deletes": [{"qid": d["qid"], "club": d["club"], "region": d["region"]}
                        for d in summary.get("deletes", [])],
            "requires": [{"qid": r["qid"], "club": r["club"], "required": r["required"]}
                         for r in summary.get("requires", [])],
            "picker": [{"op": m["op"], "clubs": int(m["clubs"])}
                       for m in (PICKER_RX.match("  - " + c) for c in summary.get("calls", [])) if m],
            "partner_picker": [{"op": m["op"], "partners": int(m["partners"])}
                               for m in (PARTNER_PICKER_RX.match("  - " + c)
                                         for c in summary.get("calls", [])) if m],
            "club_guard": [{"op": m["op"]} for m in (GUARD_RX.match("  - " + c)
                                                     for c in summary.get("calls", [])) if m],
            "modules": [module_entry(m) for m in (MODULE_RX.match("  - " + c)
                                                  for c in summary.get("calls", [])) if m],
            "retired": [{"qid": r["qid"], "club": r["club"], "reason": r["reason"]}
                        for r in summary.get("retired", [])],
            "restored": [{"qid": r["qid"], "club": r["club"], "reason": r["reason"]}
                         for r in summary.get("restored", [])],
            "rules": summary.get("rules"),
            "warnings": [w.strip() for w in summary.get("warnings", [])],
            "roster_clubs": summary.get("roster_clubs"),
            "roster_girls": summary.get("roster_girls"),
            "sf_names": summary.get("sf_names")}


def q5_changes(plan):
    """The warnings saying an existing club's question 5 would change."""
    return [w for w in plan["warnings"] if SF_NAME_CHANGE in w]


def refused_clubs(plan):
    """The warnings saying a new club was not added because its name is in use."""
    return [w for w in plan["warnings"] if SAME_NAME_REFUSED in w]


def stale_rules(plan):
    """The warnings saying a roster's rule tests a text the Club picker does not list."""
    return [w for w in plan["warnings"] if RULES_OLDER in w]


def contact_ids_stale(plan):
    """The warnings saying the live rules calculate question 18 the old way."""
    return [w for w in plan["warnings"] if CONTACT_IDS_STALE in w]


def odd_jotform_values(plan):
    """The warnings saying a Partners-tab jotform cell holds something other than yes / no / blank."""
    return [w for w in plan["warnings"] if JOTFORM_VALUE in w]


def no_jotform_column(plan):
    """The warning saying the Partners export has no jotform column (at most one)."""
    return [w for w in plan["warnings"] if JOTFORM_COLUMN in w]


def name_clashes(sf_names_by_region):
    """{region: the sync summary's sf_names} -> [(name, [club, ...])] for every name
    two different clubs of the regions synced send to question 5 (compared as
    Salesforce matches an Account: case ignored). Salesforce is one org for
    every region, so it would put those clubs' attendance on one Account. A
    club is "<club> (<partner>, <region>)"; one whose partner the form does not
    say is told apart by its question."""
    names, label = [], {}
    for region, entries in sf_names_by_region.items():
        for e in entries or []:
            partner, club = e.get("partner") or "", e.get("club") or ""
            if not e.get("value"):
                continue
            who = (key(partner), key(club)) if partner else (region, str(e.get("qid")), key(club))
            label.setdefault(who, f"{club} ({partner}, {region})" if partner
                             else f"{club} (q{e.get('qid')}, {region})")
            names.append((e["value"], who))
    return [(value, [label[w] for w in clubs]) for value, clubs in sf_name_clashes(names)]


def changes(plan):
    """Roster creates/updates/deletes, required flags written on their own, module dropdowns'
    calcValues, plus a Club-picker, partner-list or club-guard update (never a create: the runner
    passes none of --club-picker, --partner-picker and --club-guard, so a CREATE here means
    someone else did)."""
    return (len(plan["creates"]) + len(plan["updates"]) + len(plan["deletes"])
            + len(plan.get("requires", [])) + len(plan.get("modules", []))
            + len(plan.get("picker", [])) + len(plan.get("partner_picker", []))
            + len(plan.get("club_guard", [])))


def plan_summary(plan):
    """One line for the SyncLog detail and the attention title: the roster counts, then the
    required flags written on their own, the module dropdowns' calcValues, and each Club-picker,
    partner-list or club-guard write by name (only when planned), so a list-only apply does not
    read as "0 create(s), 0 update(s)"."""
    requires = plan.get("requires", [])
    values = sorted({r["required"] for r in requires})
    modules = plan.get("modules", [])
    retired, restored = plan.get("retired", []), plan.get("restored", [])
    return (f"{len(plan['creates'])} create(s), {len(plan['updates'])} update(s), "
            f"{len(plan['deletes'])} delete(s), {len(plan['warnings'])} warning(s)"
            + (f", required: {'/'.join(values)} on {len(requires)} roster(s)" if requires else "")
            + (f", module values on {len(modules)} dropdown(s)" if modules else "")
            + (f", {len(retired)} retired" if retired else "")
            + (f", {len(restored)} restored" if restored else "")
            + "".join(f", {m['op'].lower()} club picker" for m in plan.get("picker", []))
            + "".join(f", {m['op'].lower()} partner list" for m in plan.get("partner_picker", []))
            + "".join(f", {m['op'].lower()} club guard" for m in plan.get("club_guard", [])))


def check_bands(plan, max_creates=5, max_updates=20, max_retires=5, max_restores=5):
    """Reasons NOT to apply this plan unattended (empty = within the bands)."""
    reasons = []
    retired, restored = plan.get("retired", []), plan.get("restored", [])
    if len(retired) > max_retires:
        reasons.append(f"would take {len(retired)} clubs off the Club picker at once (band: {max_retires}) - "
                       "a partner newly marked jotform=no, or a wrong cell on the Partners tab? apply by "
                       "hand after checking")
    if len(restored) > max_restores:
        reasons.append(f"would put {len(restored)} clubs back on the Club picker at once (band: {max_restores}) "
                       "- a cell flipped back, or a Partners export missing its rows? apply by hand after "
                       "checking")
    if restored and no_jotform_column(plan):
        reasons.append(f"would put {len(restored)} club(s) back on the Club picker from a Partners export "
                       "that has no jotform column (nobody can be marked in it: a renamed or moved header?) "
                       "- check the Partners tab's header, then the next run restores or keeps them")
    if plan["deletes"]:
        reasons.append(f"would delete {len(plan['deletes'])} roster question(s) - never done "
                       "automatically (that is what --prune is for, on a fresh clone only)")
    if len(plan["creates"]) > max_creates:
        reasons.append(f"would create {len(plan['creates'])} clubs at once (band: {max_creates}) - "
                       "a real wave of new clubs, or a bad export? apply by hand after checking")
    if len(plan["updates"]) > max_updates:
        reasons.append(f"would update {len(plan['updates'])} rosters at once (band: {max_updates}) - "
                       "apply by hand after checking the export")
    if any(NO_SHARED_NAMES in w for w in plan["warnings"]):
        reasons.append("a roster would be replaced by one that shares no names with the current "
                       "one - confirm it is the same club before applying")
    changed = q5_changes(plan)
    if changed:
        reasons.append(f"question 5 (what Salesforce reads) would change for {len(changed)} existing "
                       "club(s) - rename each Salesforce account named in the warnings first, then "
                       "apply this region by hand with --q5-change-ok (docs/RUNBOOK.md, \"Club names "
                       "two partners share\")")
    if contact_ids_stale(plan):
        reasons.append("the form's rules calculate question 18 (Contact_IDs, the names sent to "
                       "Salesforce) the old way - the new rules are rolled out by hand, one form at a "
                       "time, with the browser checks (docs/RUNBOOK.md, \"The names list sent to "
                       "Salesforce\"); nothing applied here, roster changes included")
    requires = plan.get("requires", [])
    if requires:
        reasons.append(f"would write the required flag on {len(requires)} roster(s) that have no other "
                       "change - never unattended: the first rollout is by hand (docs/RUNBOOK.md, \"The "
                       "names list sent to Salesforce\"), and afterwards a roster that lost the flag was "
                       "edited in the builder")
    modules = plan.get("modules", [])
    if modules:
        reasons.append(f"would write the calcValues of {len(modules)} module dropdown(s) "
                       f"({', '.join('q' + m['qid'] for m in modules)}) - never unattended: the first "
                       "rollout is by hand, template first (docs/RUNBOOK.md, \"The names dictionary and "
                       "the module values\"), and afterwards a difference means a module dropdown was "
                       "edited in the builder; nothing applied here, roster changes included")
    stale = sum(1 for w in plan["warnings"] if NOT_IN_EXPORT in w)
    n = plan["roster_clubs"] or 0
    if stale > max(5, n // 10):
        reasons.append(f"{stale} clubs are on the form but missing from the export (region has "
                       f"{n} clubs in the export) - a truncated export? nothing applied")
    return reasons


def blank_region_rows(rows):
    """Active girls the sync would silently drop: (partner, club, count), sorted."""
    by = {}
    for r in rows:
        if key(r.get("status")) != "active" or (r.get("region") or "").strip():
            continue
        k = (" ".join((r.get("partner") or "").split()), " ".join((r.get("club") or "").split()))
        by[k] = by.get(k, 0) + 1
    return sorted((p, c, n) for (p, c), n in by.items())


def verify_report(rep, min_languages=MIN_LANGUAGES):
    """form_status.py --json for one form -> (problems, notes)."""
    problems, notes = [], []
    if rep.get("error_conditions"):
        problems.append(f"{rep['error_conditions']} condition(s) flagged as error")
    if not rep.get("salesforce"):
        problems.append("Salesforce integration missing")
    rp = rep.get("rule_problems") or []
    if rp:
        problems.append(f"{len(rp)} rule problem(s): " + "; ".join(str(p) for p in rp[:3]))
    langs = rep.get("languages") or []
    if len(langs) < min_languages:
        problems.append(f"only {len(langs)} language(s) offered (expected at least {min_languages})")
    rc = rep.get("region_check")
    if rc is None:
        problems.append("no region check in the report (region spelling in the Roster export?)")
    elif rc.get("skipped"):
        notes.append(f"region check skipped (form {rc['skipped']})")
    else:
        # an apply leaves no roster awaiting retirement: its partner is marked jotform=no
        # (or its club has no active girl) and it still has its rule or its picker entry
        if rc.get("awaiting_retirement"):
            problems.append(f"{len(rc['awaiting_retirement'])} roster(s) still await retirement: "
                            + ", ".join(rc["awaiting_retirement"][:5]))
        if rc.get("missing_from_form"):
            problems.append(f"{len(rc['missing_from_form'])} club(s) still missing from the form: "
                            + ", ".join(rc["missing_from_form"][:5]))
        if rc.get("rosters_out_of_date"):
            problems.append(f"{len(rc['rosters_out_of_date'])} roster(s) still differ from the sheet: "
                            + ", ".join(str(x[0]) for x in rc["rosters_out_of_date"][:5]))
        if rc.get("not_in_roster"):
            notes.append(f"{len(rc['not_in_roster'])} club(s) on the form but not in the roster "
                         "(kept, as always): " + ", ".join(rc["not_in_roster"][:5]))
    if rep.get("duplicate_club_questions"):
        notes.append("duplicate club questions: " + ", ".join(rep["duplicate_club_questions"][:5]))
    # the names dictionary (docs/plans/2026-10-02-names-and-modules.md): an option it alters is
    # one of rule_problems; a store that could not be read is a note, not an unverified apply
    names = rep.get("names_dictionary")
    if names is not None and not names.get("checked"):
        notes.append(f"names dictionary not checked ({names.get('why') or 'store not read'}) - "
                     "run tools/form_status.py for this form by hand")
    return problems, notes


def name_regex(names):
    """Compiled matcher for the listed full names, or None.

    Only names of two or more words are matched (a one-word roster entry like a
    bare first name would garble club names and ordinary words), whole-word,
    longest first, case-insensitively."""
    names = sorted({" ".join(n.split()) for n in names if n and len(n.split()) >= 2},
                   key=len, reverse=True)
    if not names:
        return None
    return re.compile(r"\b(?:" + "|".join(re.escape(n) for n in names) + r")\b", re.IGNORECASE)


def redact(text, names):
    """Replace every listed full name with [girl]."""
    rx = name_regex(names)
    return rx.sub("[girl]", text) if rx else text


def slug(region):
    return re.sub(r"[^A-Za-z]", "", region)


def sheet_when(instant, zone):
    """An aware instant as the sheet's own clock shows it: "YYYY-MM-DD HH:MM:SS" in
    `zone` (an IANA name, from sc.time_zone). SyncLog's `when` is written this way so it
    reads like the Apps Script's timestamps next to it, whatever zone the runner is on."""
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("sheet_when needs an aware instant (a naive one would be read as "
                         "the process's local time)")
    return instant.astimezone(ZoneInfo(zone)).strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------- runner
class Run:
    def __init__(self, args):
        self.args = args
        self.lines = []
        self.attention = []       # (title, detail)
        self.results = []         # SyncLog rows
        self.failed = False
        # the start instant, aware UTC: SyncLog's `when` is rendered from it in the SHEET's
        # zone (append_synclog); stamp/when below are the process's local clock, for the
        # local file names and the log/ATTENTION.md lines (with the offset, so they
        # cannot be misread as sheet time)
        self.started = datetime.datetime.now(datetime.timezone.utc)
        now = self.started.astimezone()
        self.stamp = now.strftime("%Y-%m-%dT%H%M%S")
        self.when = now.strftime("%Y-%m-%d %H:%M:%S %z")
        self.mode = "apply" if args.apply else "dry-run"
        self.sf_names = {}        # region -> what each of its rosters sends to question 5
        self.partners = None      # the Partners export every sync and verify call gets (--partners)
        self.client = None        # glow.jotform.Client: the form-status read before each region
        self.sf, self.sf_on_form = None, set()   # the Salesforce step; regions whose form is as planned
        self.skipped = set()      # regions whose form is not ENABLED: nothing run, no sf_names read
        self.names = []
        self._rx = None          # set once the roster is loaded; from then on every
                                 # logged line is redacted BEFORE it reaches stdout
                                 # (the Actions job log keeps raw step output for 90 days)

    def set_names(self, names):
        self.names = names
        self._rx = name_regex(names)

    def log(self, msg=""):
        if self._rx is not None:
            msg = self._rx.sub("[girl]", msg)
        print(msg, flush=True)
        self.lines.append(msg)

    def cmd(self, argv, label):
        r = subprocess.run(argv, capture_output=True, text=True, cwd=REPO,
                           env={k: v for k, v in os.environ.items() if not k.startswith("SF_")})
        for line in (r.stdout or "").splitlines():
            self.log("    " + line)
        if r.returncode != 0:
            self.log(f"  ! {label} exited {r.returncode}: " + (r.stderr or "").strip()[-300:])
        return r

    def sync(self, csv_path, region, form, apply, summary_path=None):
        argv = [sys.executable, os.path.join(REPO, "sync_attendance_form.py"), csv_path,
                "--roster", "--region", region, "--form", form]
        if self.partners:
            argv += ["--partners", self.partners]
        if apply:
            argv.append("--apply")
        if summary_path:
            argv += ["--summary-json", summary_path]
        return self.cmd(argv, f"sync {region}" + (" --apply" if apply else ""))

    def with_retry(self, fn, label, tries=4, delay=5):
        for i in range(tries):
            try:
                return fn()
            except Exception as err:                      # network errors of any shape
                if i == tries - 1:
                    raise
                self.log(f"  ! {label}: {err.__class__.__name__}: {str(err)[:200]} - retry in {delay}s")
                time.sleep(delay)
                delay *= 2

    def result(self, region, plan, result, detail):
        if result in ("in-sync", "applied", "applied-with-problems", "applied-unverified"):
            self.sf_on_form.add(region)
        elif result == "skipped":
            self.skipped.add(region)
        self.results.append([self.when, self.args.trigger, region, self.mode,
                             len(plan["creates"]) if plan else "", len(plan["updates"]) if plan else "",
                             plan["rules"] if plan and plan["rules"] is not None else "",
                             result, detail[:500], self.args.run_url or ""])
        self.log(f"  => {region}: {result}" + (f" - {detail}" if detail else ""))

    # ---- steps
    def export_roster(self, svc):
        values = self.with_retry(lambda: sc.read_tab(svc, ROSTER_TAB), "export Roster")
        path = os.path.join(self.args.out, f"roster_{self.stamp}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(values)
        self.log(f"Roster: exported {max(0, len(values) - 1)} rows -> {os.path.relpath(path, REPO)}")
        return path

    def export_partners(self, svc):
        """The Partners tab beside the Roster export: the jotform marker the sync reads."""
        values = self.with_retry(lambda: sc.read_tab(svc, PARTNERS_TAB), "export Partners")
        path = os.path.join(self.args.out, f"partners_{self.stamp}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(values)
        self.log(f"Partners: exported {max(0, len(values) - 1)} rows -> {os.path.relpath(path, REPO)}")
        return path

    def read_status(self, form):
        """The form's status as GET /form/{id} says (ENABLED / DISABLED), under the
        retries; raises when the read still fails."""
        info = self.with_retry(lambda: self.client.get(f"/form/{form}"), f"read form {form}")
        return str((info or {}).get("status") or "")

    def region(self, region, csv_path):
        form = REGIONAL_FORMS[region]
        a = self.args
        self.log(f"\n== {region}  form {form}")
        # a form nobody can open is not synced: skipped, not failed, and the exit code is
        # unaffected (the U.S form while its clubs do not report through Jotform). A status
        # that cannot be read is a failure of this region; the run goes on to the next
        try:
            status = self.read_status(form)
        except Exception as err:                      # a JotformError of any shape
            self.failed = True
            self.result(region, None, "failed",
                        f"could not read form status: {err.__class__.__name__}: {str(err)[:200]}")
            return
        if status != "ENABLED":
            self.log(f"  form {form} is {status or 'of no reported status'} - not synced")
            self.result(region, None, "skipped", f"form {status or 'status not reported'}")
            return
        summary_path = os.path.join(a.out, f"plan_{slug(region)}_{self.stamp}.json")
        dry = self.sync(csv_path, region, form, apply=False, summary_path=summary_path)
        if dry.returncode != 0:
            self.failed = True
            self.result(region, None, "failed", "dry run exited "
                        f"{dry.returncode}: {(dry.stderr or '').strip()[-200:]}")
            return
        plan = parse_plan(dry.stdout or "")
        if os.path.exists(summary_path):
            with open(summary_path, encoding="utf-8") as f:
                plan = plan_from_summary(json.load(f))
        self.sf_names[region] = plan.get("sf_names")
        # a new club whose name another partner's club has: the sync did not create it
        # and went on with the rest, so this never stops the region - it needs a human
        refused = refused_clubs(plan)
        if refused:
            self.attention.append((f"{region}: {len(refused)} new club(s) NOT added to the form - "
                                   "the name is another club's",
                                   "A new club may not take a name that is in use (its attendance "
                                   "would land on the other club's Salesforce account). Ask the partner "
                                   "for a different name and rename the club in the sheet with "
                                   "tools/rename_club.py --partner … --old … --new … --sheet-only "
                                   "(--sheet-only: the club has no question on any form, and the "
                                   "question of that name is the other partner's); the next run then "
                                   "creates it. Until then it is on no attendance form, and every "
                                   "apply in this region reads applied-with-problems (the verify step "
                                   "counts the club as missing from the form, or its name's roster as "
                                   "differing). docs/RUNBOOK.md, \"Club names two partners share\".\n\n"
                                   + "\n".join("- " + w for w in refused)))
        # a Partners-tab jotform cell holding something other than yes / no / blank: read as
        # yes, so nothing left the form for it; a human corrects the cell
        odd = odd_jotform_values(plan)
        if odd:
            self.attention.append((f"{region}: {len(odd)} Partners-tab jotform value(s) not understood",
                                   "The Partners tab's `jotform` column takes `no` (the partner's clubs are "
                                   "not on the attendance forms), `yes` or blank. Any other text is read as "
                                   "yes, so these partners' clubs stay on the forms until the cell is "
                                   "corrected. docs/RUNBOOK.md, \"Clubs that do not use Jotform\".\n\n"
                                   + "\n".join("- " + w for w in odd)))
        # ...and an export without the column at all: nobody is marked, so a retired roster of
        # an active club would be restored - said here; a plan that restores is held (check_bands)
        no_column = no_jotform_column(plan)
        if no_column:
            self.attention.append((f"{region}: the Partners export has no jotform column",
                                   "The Partners tab's header row has no `jotform` column (renamed, moved, "
                                   "or an inserted column?), so no partner can be marked and every retired "
                                   "roster of an active club reads as one to restore. Nothing is restored "
                                   "unattended from such an export; retirements already applied stay as they "
                                   "are. Put the header back (Partners!D1 = jotform) and the next run reads "
                                   "the marks again. docs/RUNBOOK.md, \"Clubs that do not use Jotform\".\n\n"
                                   + "\n".join("- " + w for w in no_column)))
        note = "; ".join(filter(None, [f"{len(refused)} new club(s) not added (name in use)" if refused else "",
                                       f"{len(odd)} jotform value(s) not understood" if odd else "",
                                       "Partners export without a jotform column" if no_column else ""]))
        n = changes(plan)
        # a change of what an existing club sends to question 5 stops the region even
        # when nothing else is planned: a rules-only difference is not a "change" here,
        # and this one must never read as in-sync - nor question 18's rules the old way
        if n == 0 and not q5_changes(plan) and not contact_ids_stale(plan):
            # …nor may rules that test a name the picker does not list: those clubs' rosters
            # do not show (with the club guard their mentors cannot submit), and the
            # conditions rewrite that repairs it is not applied unattended
            stale = stale_rules(plan)
            if stale:
                self.attention.append((f"{region}: {len(stale)} roster rule(s) test a name the Club "
                                       "picker does not list - those rosters do not show",
                                       "The form's rules are out of step with its Club picker (a "
                                       "conditions backup restored over newer picker entries, or a "
                                       "hand apply that stopped between the picker write and the "
                                       "rules write). Until the rules are rewritten those clubs' "
                                       "rosters never show and, with the club guard, their mentors "
                                       "cannot submit. The runner does not apply a rules-only "
                                       "difference: run by hand now, python3 sync_attendance_form.py "
                                       f"<roster.csv> --roster --region '{region}' --form {form} (the "
                                       "dry run plans only REPLACE conditions and no question-5 "
                                       "change), then --apply, then tools/form_status.py. "
                                       "docs/RUNBOOK.md, \"Club names two partners share\".\n\n"
                                       + "\n".join("- " + w for w in stale)))
                self.result(region, plan, "attention",
                            f"{len(stale)} roster rule(s) test a name the Club picker does not list - "
                            "apply by hand" + (f"; {note}" if note else ""))
                return
            self.result(region, plan, "in-sync", note)
            return
        summary = plan_summary(plan) + (f"; {note}" if note else "")
        reasons = check_bands(plan, a.max_creates, a.max_updates,
                              getattr(a, "max_retires", 5), getattr(a, "max_restores", 5))
        if reasons:
            self.attention.append((f"{region}: not applied - {summary}",
                                   "\n".join("- " + r for r in reasons) + "\n\nPlanned:\n" +
                                   "\n".join(f"- CREATE {c['club']} ({c['girls']} girls)" for c in plan["creates"]) +
                                   "\n".join(f"\n- UPDATE {u['club']} (q{u['qid']}, {u['girls']} girls)" for u in plan["updates"]) +
                                   "\n".join(f"\n- DELETE {d['club']} (q{d['qid']})" for d in plan["deletes"]) +
                                   (f"\n- REQUIRED on {len(plan['requires'])} roster(s) with no other change"
                                    if plan.get("requires") else "") +
                                   "".join(f"\n- MODULE values q{m['qid']} (year {m['year']}: "
                                           + (f"{m['modules']} modules)" if m["modules"] else "cleared)")
                                           for m in plan.get("modules", [])) +
                                   "".join(f"\n- RETIRE {r['club']} (q{r['qid']}): {r['reason']}"
                                           for r in plan.get("retired", [])) +
                                   "".join(f"\n- RESTORE {r['club']} (q{r['qid']}): {r['reason']}"
                                           for r in plan.get("restored", [])) +
                                   ("\n\nWarnings:\n" + "\n".join("- " + w for w in plan["warnings"]) if plan["warnings"] else "")))
            self.result(region, plan, "attention", "; ".join(reasons))
            return
        if not a.apply:
            self.result(region, plan, "dry-run", "would apply: " + summary)
            return

        self.log(f"  backing up form {form}")
        bk = self.cmd([sys.executable, os.path.join(REPO, "backup_forms.py"), "--form", form], "backup")
        if bk.returncode != 0:
            self.failed = True
            self.result(region, plan, "failed", "backup failed - nothing applied")
            return
        self.save_conditions(form)
        self.sf_create(region, plan)        # the new clubs' accounts: after the backup, before their form
        applied_path = summary_path.replace(".json", "_applied.json")
        applied = self.sync(csv_path, region, form, apply=True, summary_path=applied_path)
        if applied.returncode != 0:
            self.log("  ! apply failed once - retrying (a failure between the question writes and "
                     "the conditions write leaves the form half-synced; the re-run completes it)")
            applied = self.sync(csv_path, region, form, apply=True, summary_path=applied_path)
        if applied.returncode != 0:
            self.failed = True
            self.attention.append((f"{region}: APPLY FAILED - the form may be half-synced",
                                   f"Run by hand now: python3 sync_attendance_form.py <roster.csv> --roster "
                                   f"--region '{region}' --form {form} (dry run first, then --apply), or "
                                   f"restore the conditions from backups/{form}/ with restore_conditions.py. "
                                   "Until then later runs report this form in-sync: when only the rules "
                                   "are stale (a new roster's show rule and Contact_IDs operand; on a form "
                                   "with the club guard, its club list, which blocks that club's mentors), "
                                   "the difference is not a change to the runner.\n\n"
                                   + (applied.stderr or "").strip()[-500:]))
            self.result(region, plan, "failed", "apply exited " + str(applied.returncode))
            return
        if os.path.exists(applied_path):
            with open(applied_path, encoding="utf-8") as f:
                self.sf_names[region] = json.load(f).get("sf_names")
        ver = self.cmd([sys.executable, os.path.join(TOOLS, "form_status.py"), "--form", form,
                        "--roster", csv_path, "--json"]
                       + (["--partners", self.partners] if self.partners else []), "verify")
        rep = None
        if ver.returncode == 0:
            try:
                rep = json.loads(ver.stdout)[0]
            except (ValueError, IndexError):
                rep = None
        if rep is None:
            # a live write whose check could not run must never pass silently
            self.attention.append((f"{region}: applied but NOT verified",
                                   "The write succeeded but form_status could not confirm the form "
                                   "is clean. Check by hand:\n"
                                   f"python3 tools/form_status.py --form {form} --roster <roster.csv>\n\n"
                                   + (ver.stderr or "").strip()[-300:]))
            self.result(region, plan, "applied-unverified", summary + "; verification could not run")
            return
        problems, notes = verify_report(rep)
        for note in notes:
            self.log("  note: " + note)
        if problems:
            self.attention.append((f"{region}: applied, but the form still has problems",
                                   "\n".join("- " + p for p in problems)
                                   # the region check goes by club name, so a club the sync did not
                                   # add shows up here until it is renamed: say so, never filter it
                                   # (the same line would hide a real drift of its namesake's roster)
                                   + ("\n\nA 'missing from the form' or 'differ from the sheet' line "
                                      "naming a club listed above as NOT added is expected until that "
                                      "club is renamed: the check goes by club name, so it counts the "
                                      "club that was not added. By itself it does not say the existing "
                                      "club's roster is out of date."
                                      if refused else "")))
            self.result(region, plan, "applied-with-problems", summary + "; " + "; ".join(problems))
        else:
            self.result(region, plan, "applied", summary + "; verified clean")

    def check_names(self):
        """Across the regions of this run: no two clubs may send the same name to
        question 5 (Salesforce is one org). Reported, never blocking: the forms are
        already that way when this fires."""
        clashes = name_clashes(self.sf_names)
        if not clashes:
            return
        self.attention.append((f"{len(clashes)} Salesforce name(s) are sent by more than one club",
                               "Salesforce matches question 5 to an Account by name, in one org for "
                               "every region, so these clubs' attendance would land on one Account. "
                               "Clubs of two partners: sync_attendance_form.py --same-name-switch on "
                               "each form concerned, by hand (docs/RUNBOOK.md, \"Club names two "
                               "partners share\"). Two questions for one club: delete the leftover.\n\n"
                               + "\n".join(f"- '{name}': " + "; ".join(clubs) for name, clubs in clashes)))
        self.log(f"  ! {len(clashes)} name(s) are sent to question 5 by more than one club: "
                 + ", ".join(f"'{name}'" for name, _ in clashes[:8]))

    def check_sheet_zone(self, zone):
        """The sheet's own time zone (sheets_client.time_zone, read when the tabs are
        exported) against glow.sync.SHEET_ZONE, the zone the sync and the audit take
        "today" in for the no-active-girl rule (docs/plans/2026-10-06-clubs-off-jotform.md):
        the sheet stamps removed_date in its own zone, and a constant that differs from it
        moves the day's edge. A log line when they agree; an ATTENTION when they do not
        (the regions still run: the rule is off by the difference, nothing else is)."""
        if zone == SHEET_ZONE:
            self.log(f"Sheet zone: {zone} (as glow/sync.py SHEET_ZONE)")
            return
        self.attention.append((f"The sheet's time zone is {zone}, the tools expect {SHEET_ZONE}",
                               f"The spreadsheet's time zone (File > Settings) is {zone}; glow/sync.py "
                               f"SHEET_ZONE says {SHEET_ZONE}. A club with no active girl is retired once "
                               "its latest removed_date is before today, and the sheet stamps that date in "
                               "its own zone, so until the two agree a roster emptied in the sheet's evening "
                               "may be retired hours early (or kept hours longer). If the sheet's zone was "
                               "changed on purpose, set SHEET_ZONE to it; otherwise set the sheet back. "
                               "docs/RUNBOOK.md, \"Clubs that do not use Jotform\"."))
        self.log(f"  ! sheet zone {zone} differs from glow/sync.py SHEET_ZONE {SHEET_ZONE}")

    def check_storage(self, read):
        """Jotform's account limits, once per run (docs/plans/2026-10-06-photos-to-drive.md):
        the storage line in the log and, for each limit at alarm (80 % of it), an ATTENTION
        naming it - at 100 % Jotform disables the forms and attendance collection stops.
        Upload space is cumulative and is what Gold or a retention policy answers; the
        submissions count resets every cycle; so the two are judged apart and never merged.
        At warn the line alone (a daily e-mail for months would bury real ATTENTIONs). `read`
        returns glow.usage.read_usage's dict; one that raises is a log line, never a failed
        run. main() bounds each of its three GETs (curl --max-time), so a stalled connection
        is that log line within minutes, not a run held to the job's timeout."""
        try:
            u = read()
        except Exception as err:                      # a Jotform error of any shape
            self.log(f"\nstorage: could not be read ({err.__class__.__name__})")
            return
        self.log("\n" + usage.storage_line(u))
        for limit, lv in usage.levels(u).items():
            if lv != "alarm":
                continue
            pct = f"{usage.share(u, limit) * 100:.0f}%"
            title = f"Jotform {usage.NAMES[limit]} at {pct} - the forms stop at 100%"
            if limit == "uploads":
                detail = (f"The {u['plan']} plan allows {usage.gib(u['uploads_cap'])} of uploaded files in all "
                          f"(the group photos, about 1.9 MB each); {usage.gib(u['uploads'])} are used. At 100% "
                          "Jotform disables the forms (\"Form over quota\") and attendance collection stops; "
                          "copying the photos to Google Drive frees nothing here. Decide now: Gold (more upload "
                          "space) or a retention policy - docs/BACKLOG.md, \"Gold versus retention\"; "
                          "docs/RUNBOOK.md, \"Photos\", step 7. Never switch on Jotform's Auto Delete "
                          "Submissions without reading that BACKLOG item first.")
            else:
                detail = (f"The {u['plan']} plan allows {u['submissions_cap']:,} submissions a month across every "
                          f"form; {u['submissions']:,} have arrived in the cycle that resets on {u['reset'] or '?'}. "
                          "At 100% Jotform disables the forms until the cycle resets. This is a busy month, not "
                          "storage: only a bigger plan answers it - docs/BACKLOG.md, \"Gold versus retention\"; "
                          "docs/RUNBOOK.md, \"Photos\", step 7.")
            self.attention.append((title, detail))
            self.log(f"  ! {title}")
    # ---- Salesforce: the new clubs' accounts (tools/sf_new_clubs.py; RUNBOOK "Club accounts in Salesforce")
    def sf_start(self, csv_path):
        """SF_SYNC (repository variable) off | plan | apply; writes need --apply-salesforce too."""
        mode = (os.environ.get("SF_SYNC") or "off").strip().lower()
        if mode not in ("off", "plan", "apply"):
            self.attention.append(("SF_SYNC is not off, plan or apply",
                                   f"It is {mode!r}: the Salesforce step did not run."))
            return
        if mode == "apply" and not getattr(self.args, "apply_salesforce", False):
            mode = "plan"
        if mode == "off":
            self.log("SF: off (repository variable SF_SYNC)")
            return
        cid, secret = os.environ.get("SF_CLIENT_ID"), os.environ.get("SF_CLIENT_SECRET")
        if not cid or not secret:
            self.log("SF: not configured (secrets SF_CLIENT_ID / SF_CLIENT_SECRET) - skipped")
            return
        self.log(f"SF: {mode}, as GLOW Sync")
        self.sf = sfn.Step(mode, Org(login=client_credentials(cid, secret)), csv_path, log=self.log,
                           retry=self.with_retry)
        try:
            self.sf.prepare()
        except Exception as err:                          # the forms sync whatever happens here
            self.sf.broken = f"{err.__class__.__name__}: {str(err)[:200]}"
            self.sf.warn("not ready - no account is created or checked this run", self.sf.broken)

    def sf_create(self, region, plan):
        if self.sf is None:
            return
        try:
            self.sf.create(region, plan)
        except Exception as err:                          # the form still applies
            self.sf.warn(f"{region}: the create step failed ({err.__class__.__name__})", str(err)[:300])

    def sf_finish(self, svc):
        """After all regions: the read-only check, the SF Pending rows of what was created, one
        SyncLog row. Any error becomes ATTENTION; the session ends either way."""
        if self.sf is None:
            return
        ok = wrong = 0
        try:
            # strays are judged only when every form's names were read; a disabled form is never
            # read (skipped) and counts as read - its clubs keep their accounts, under their partner
            ok, wrong = self.sf.check(self.sf_names, [name for name, _ in name_clashes(self.sf_names)],
                                      on_form=self.sf_on_form,
                                      complete=all(self.sf_names.get(r) is not None or r in self.skipped
                                                   for r in REGIONAL_FORMS))
            if self.sf.created and self.sf.mode == "apply" and getattr(self.args, "synclog", False):
                self.mark_sf_pending(svc or sc.service())
        except (SystemExit, Exception) as err:            # sheets_client reports via sys.exit
            self.sf.warn(f"the end-of-run step failed ({err.__class__.__name__})", str(err)[:300])
        finally:
            self.sf.close()
        self.attention += self.sf.attention
        result = ("failed" if self.sf.broken else "attention" if self.sf.attention
                  else "applied" if self.sf.created else "in-sync")
        detail = self.sf.broken or f"{len(self.sf.created)} account(s) created; check: {ok} ok, {wrong} need a person"
        self.results.append([self.when, self.args.trigger, "Salesforce", self.sf.mode, len(self.sf.created),
                             "", "", result, detail[:500], self.args.run_url or ""])

    def mark_sf_pending(self, svc):
        """`done (auto <date>)` on the SF Pending row of each club this run created - one cell,
        found by its header, the row read again just before the write and once after."""
        for _, club, _id in self.sf.created:
            values = self.with_retry(lambda: sc.read_tab(svc, sfn.SF_PENDING_TAB), "read SF Pending")
            spot = sfn.pending_cell(values, club.partner, club.club)
            if spot is None:
                self.log(f"  SF Pending: no single pending row for {club.club} ({club.partner}) - left as is")
                continue
            if sfn.pending_cell(sc.read_tab(svc, sfn.SF_PENDING_TAB), club.partner, club.club) != spot:
                self.log(f"  SF Pending: the rows moved while marking {club.club} - left as is")
                continue
            sc.write_cell(svc, sfn.SF_PENDING_TAB, *spot, f"done (auto {self.sf.today})")
            self.log(f"  SF Pending: {club.club} ({club.partner}) marked done")

    def save_conditions(self, form):
        """A conditions-only rollback file next to the full snapshot.

        The full properties snapshot holds staff e-mail configs and the
        Salesforce integration settings, so only this file may leave the
        machine (the workflow artifact). Restore with:
        restore_conditions.py --form <id> --from conditions-<stamp>.json"""
        src = os.path.join(REPO, "backups", form, "properties-latest.json")
        try:
            with open(src, encoding="utf-8") as f:
                props = json.load(f)
            out = os.path.join(REPO, "backups", form, f"conditions-{self.stamp}.json")
            with open(out, "w", encoding="utf-8") as f:
                json.dump({"conditions": props.get("conditions", [])}, f, indent=1)
        except (OSError, ValueError) as err:
            self.log(f"  ! could not write the conditions-only copy: {err}")

    def append_synclog(self, svc):
        when = sheet_when(self.started, sc.time_zone(svc))    # the sheet's zone, not the runner's
        for row in self.results:
            row[0] = when
        if not sc._has_tab(svc, SYNC_LOG_TAB) or not sc.read_tab(svc, SYNC_LOG_TAB):
            sc.write_tab(svc, SYNC_LOG_TAB, [SYNC_LOG_COLS])
        sc.append_rows(svc, SYNC_LOG_TAB, self.results)
        self.log(f"SyncLog: {len(self.results)} row(s) appended")

    def write_files(self):
        text = redact("\n".join(self.lines), self.names)
        log_path = os.path.join(self.args.out, f"{self.stamp}.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        att_path = os.path.join(self.args.out, "ATTENTION.md")
        if self.attention:
            body = [f"# Auto-sync needs a human - {self.when}", ""]
            for title, detail in self.attention:
                body += [f"## {title}", "", detail, ""]
            body += ["Log: " + os.path.relpath(log_path, REPO)]
            if self.args.run_url:
                body += ["Run: " + self.args.run_url]
            with open(att_path, "w", encoding="utf-8") as f:
                f.write(redact("\n".join(body), self.names) + "\n")
            print(f"\nATTENTION: {len(self.attention)} item(s) -> {os.path.relpath(att_path, REPO)}")
        elif os.path.exists(att_path):
            os.remove(att_path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="write to the forms (default: dry run)")
    ap.add_argument("--region", action="append", choices=sorted(REGIONAL_FORMS),
                    help="only this region (repeatable; default: all four)")
    ap.add_argument("--trigger", default="manual", help="what started this run (goes to SyncLog)")
    ap.add_argument("--roster", metavar="CSV", help="use this Roster export instead of exporting")
    ap.add_argument("--partners", metavar="CSV",
                    help="with --roster: use this Partners export instead of exporting (the jotform "
                         "marker the sync reads)")
    ap.add_argument("--max-creates", type=int, default=5, help="per region, per run (default 5)")
    ap.add_argument("--max-updates", type=int, default=20, help="per region, per run (default 20)")
    ap.add_argument("--max-retires", type=int, default=5,
                    help="rosters taken off the Club picker, per region, per run (default 5)")
    ap.add_argument("--max-restores", type=int, default=5,
                    help="rosters put back on the Club picker, per region, per run (default 5)")
    ap.add_argument("--min-active", type=int, default=1000,
                    help="refuse an export with fewer active rows than this (default 1000)")
    ap.add_argument("--apply-salesforce", action="store_true",
                    help="create the Salesforce accounts of the new clubs this run puts on a form "
                         "(also needs SF_SYNC=apply; the workflow passes it only then)")
    ap.add_argument("--synclog", action="store_true",
                    help="append this run's outcomes to the sheet's SyncLog tab (the workflow "
                         "always passes this; without it nothing is written to the sheet)")
    ap.add_argument("--out", default=DEFAULT_OUT, help="working directory for exports and logs")
    ap.add_argument("--run-url", default=os.environ.get("AUTO_SYNC_RUN_URL", ""),
                    help="link recorded in SyncLog (Actions sets AUTO_SYNC_RUN_URL)")
    args = ap.parse_args()
    if not os.environ.get("JOTFORM_API_KEY"):
        sys.exit("Set JOTFORM_API_KEY in the environment (a dry run reads the forms too)")
    if args.roster and not args.partners:
        # with --roster nothing is exported, and the sheet service is never built
        sys.exit("--roster needs --partners <Partners export>: with --roster nothing is exported, and "
                 "without the Partners tab the sync cannot tell a retired roster from a broken one")
    if args.partners and not args.roster:
        sys.exit("--partners goes with --roster (without --roster both tabs are exported)")
    os.makedirs(args.out, exist_ok=True)

    run = Run(args)
    run.client = Client(os.environ["JOTFORM_API_KEY"], max_time=60)   # bounded: a stalled GET must not hold the run
    run.log(f"auto-sync {run.when}  trigger={args.trigger}  mode={run.mode}  "
            f"regions={', '.join(args.region or REGIONAL_FORMS)}")
    svc = None
    if args.roster:
        csv_path, run.partners = args.roster, args.partners
        run.log(f"Roster: using {os.path.relpath(csv_path, REPO)}")
        run.log(f"Partners: using {os.path.relpath(run.partners, REPO)}")
    else:
        svc = sc.service()
        csv_path = run.export_roster(svc)
        run.partners = run.export_partners(svc)
        run.check_sheet_zone(sc.time_zone(svc))     # the zone the sync takes "today" in

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    needed = {"partner", "club", "full_name", "status", "region"}
    if not rows or not needed <= set(rows[0]):
        sys.exit("Not a Roster export: expected the columns " + ", ".join(sorted(needed)))
    run.set_names([r["full_name"] for r in rows])
    active = [r for r in rows if key(r["status"]) == "active"]
    run.log(f"Roster: {len(rows)} rows, {len(active)} active")
    if len(active) < args.min_active:
        run.failed = True
        run.log(f"  ! only {len(active)} active rows (floor {args.min_active}) - the export looks "
                "truncated; nothing synced")
        run.write_files()
        sys.exit(1)
    blank = blank_region_rows(rows)
    if blank:
        detail = "\n".join(f"- {p} / {c}: {n} girl(s)" for p, c, n in blank)
        run.attention.append(("Active girls with no region - they reach NO attendance form",
                              "Fill in the region on the Partners tab (rows marked 'region needed'), "
                              "then GLOW -> Refresh regions from the Partners tab.\n\n" + detail))
        run.log(f"  ! {sum(n for _, _, n in blank)} active girl(s) in {len(blank)} club(s) have no region")

    run.sf_start(csv_path)
    for region in args.region or list(REGIONAL_FORMS):
        run.region(region, csv_path)
    run.check_names()
    run.check_storage(lambda: usage.read_usage(run.client))
    run.sf_finish(svc)

    if args.synclog and run.results:
        try:
            svc = svc or sc.service()
            run.with_retry(lambda: run.append_synclog(svc), "SyncLog")
        except (SystemExit, Exception) as err:            # sheets_client reports via sys.exit;
            # a SyncLog failure must not discard the log/ATTENTION files below
            run.attention.append(("SyncLog row could not be written",
                                  f"{err.__class__.__name__}: {str(err)[:300]}\n"
                                  "The sheet is missing this run's record; the log file below has it."))
            run.log(f"  ! could not write SyncLog: {err.__class__.__name__}: {str(err)[:200]}")
    run.write_files()
    if run.failed:
        sys.exit(1)
    if run.attention:
        sys.exit(2)


if __name__ == "__main__":
    main()
