#!/usr/bin/env python3
"""
Launch-readiness report for the Jotform attendance forms: is each form
carrying the clubs the Roster says it should, with clean logic and the
Salesforce integration intact?

Read-only. Compares every form's club checkboxes against the Roster tab
(data/roster_build/Roster.csv by default, or --roster <csv>), grouped by
region, and reports what the Jotform API says about conditions, emails,
integration, submissions and the enableFuzzy field, and whether every roster
renders above the links and the Submit button (glow/layout.py; a roster below
them makes the form NOT CLEAN - tools/fix_roster_order.py repairs it), and
whether question 18 (Contact_IDs, the names sent to Salesforce) is calculated
after the rosters show or hide and every roster is required - as glow/sync.py's
constants say (docs/plans/2026-09-30-contact-ids.md) - and, for what Salesforce
stores (docs/plans/2026-10-02-names-and-modules.md), whether each module dropdown
carries calcValues equal to its options (MODULE_CALC_VALUES: question 98 then
copies the module, not the text a translated page shows), whether the module
chain keeps its shape (docs/plans/2026-10-06-module-selection.md: the year,
module and session dropdowns single-select and required, and the form-level
clearFieldOnHide as CLEAR_FIELD_ON_HIDE says, so a dropdown hidden by the Year
rule never sends its answer) and whether the form's
own translation dictionary alters any roster option (the runtime's lookup
emulated, glow/translation_lookup.py, in every language the store holds: question
18 would send another spelling of that girl's name; counts and club names only).
Right after the Roster line comes Jotform's storage against the account's plan
(glow/usage.py: upload space in all and submissions in the monthly cycle, each judged
on its own; docs/plans/2026-10-06-photos-to-drive.md) - account-wide, so never a form
problem.
--rendered reads the public page as well (counts only).

Usage:
    export JOTFORM_API_KEY=...
    python3 tools/form_status.py                  # all six forms
    python3 tools/form_status.py --form <ID> ...  # some
"""
import argparse
import csv
import html
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow import forms as glow_forms       # noqa: E402
from glow import layout                    # noqa: E402  (rosters above the links and Submit)
from glow import sync as glow_sync         # noqa: E402  (question 18's and the modules' constants, read at run time)
from glow import translation_lookup as tl  # noqa: E402  (the runtime's names dictionary, emulated)
from glow import usage                     # noqa: E402  (Jotform's storage against the plan's limits)
from glow.cli import run                   # noqa: E402
from glow.jotform import Client, JotformError     # noqa: E402
from glow.links import order_of, shown_by_rules   # noqa: E402
from glow.sync import (                    # noqa: E402  (shared with the sync tool)
    GUARD_DISABLES_SUBMIT, GUARD_NAME, GUARD_PROPS, MODULES, PICKER_NAME, SF_NAME_SEP, WEEKS, YEAR,
    aligned_calc_values, club_guards, club_partners, dropdown_options, has_calc_values,
    long_name_partner, partner_picker, picker_calc_values)
from glow.text import key, name_key        # noqa: E402

FORMS = {glow_forms.TEMPLATE: ("template", None),
         **{fid: (region, region) for region, fid in glow_forms.REGIONALS.items()}}
DEFUNCT = {glow_forms.DEFUNCT["master"]: ("master (defunct)", None),
           **{fid: (f"{region} (defunct)", region)
              for region, fid in glow_forms.DEFUNCT.items() if region != "master"}}
ENABLE_FUZZY_QID = "109"


def load_roster(path):
    """region -> {key(club): (club, set(name keys), partner)} for ACTIVE girls."""
    by_region = defaultdict(dict)
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if key(row.get("status")) != "active":
                continue
            region = row.get("region", "").strip() or "(no region)"
            ck = key(row["club"])
            entry = by_region[region].setdefault(ck, (row["club"], set(), row["partner"]))
            entry[1].add(name_key(row["full_name"]))
    return by_region


def load_partners(path):
    """{key(club): {key(partner): partner}} for every Roster row - any status, all
    regions: the partners a club's long name ("<club> - <partner>",
    glow.sync.SF_NAME_SEP) may carry."""
    pairs = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            partner = " ".join((row.get("partner") or "").split())
            club = " ".join((row.get("club") or "").split())
            if partner and club:
                pairs.setdefault((partner, club), True)
    return club_partners(pairs)


CLUB_NAME_QID, PARTNER_QID, CONTACT_IDS_QID = "5", "331", "18"


def club_picker(questions):
    """qid of the Club dropdown, or None when mentors type the club name."""
    return next((qid for qid, q in questions.items()
                 if q.get("type") == "control_dropdown" and q.get("name") == PICKER_NAME), None)


def picker_options(questions, picker):
    """The picker's options exactly as stored (what a multi-select's rules compare)."""
    return [o for o in (questions[picker].get("options") or "").split("|") if o]


def _parsed(conditions):
    """[(rule, terms, actions)] for the rules whose terms/action parse."""
    out = []
    for c in conditions or []:
        try:
            terms = json.loads(c["terms"]) if isinstance(c["terms"], str) else c["terms"]
            actions = json.loads(c["action"]) if isinstance(c["action"], str) else c["action"]
        except (KeyError, ValueError, TypeError):
            continue
        out.append((c, terms or [], actions or []))
    return out


def audit_picker(questions, conditions):
    """The Club picker's own checks: on a multi-select, `equals` is exact and
    case-sensitive, so every rule term testing the picker must be one of its
    options as spelled (else that roster never shows); and calcValues, when
    the picker carries them, must be its options in order (the copy into
    question 5 reads them - misaligned, it sends another club's name)."""
    picker = club_picker(questions)
    if not picker:
        return []
    problems = []
    options = picker_options(questions, picker)
    if questions[picker].get("multipleSelections") == "Yes":
        exact, lower = set(options), {o.lower(): o for o in options}
        for c, terms, _ in _parsed(conditions):
            for t in terms:
                if str(t.get("field")) == picker and t.get("operator") == "equals" \
                        and t.get("value") not in exact:
                    hint = lower.get(str(t.get("value")).lower())
                    problems.append(f"rule {c.get('id')} tests the Club picker (q{picker}) equals "
                                    f"{t.get('value')!r}, which is not one of its options"
                                    + (f" (it has {hint!r}; a multi-select compares case)" if hint else "")
                                    + " - that rule never fires; the next sync apply fixes it")
    if has_calc_values(questions[picker]) or club_guards(questions):
        have = questions[picker].get("calcValues") or ""
        if have != picker_calc_values(options):
            problems.append(f"club picker (q{picker}) calcValues are not its {len(options)} options in "
                            f"order ({len(have.split('|')) if have else 0} values) - the copy into "
                            "question 5 would send another club's name; the next sync run realigns them")
    return problems


def audit_club_guard(questions, conditions):
    """The one-club-per-submission guard (glow.sync.GUARD_NAME), when a form
    has it: its element, its placement directly below the picker, its two
    rules with the full term list. [] on a form without it
    (docs/plans/2026-09-29-club-guard.md)."""
    guards = club_guards(questions)
    if not guards:
        return []
    problems = []
    if len(guards) > 1:
        problems.append(f"{len(guards)} elements are named {GUARD_NAME!r} "
                        f"({', '.join('q' + g for g in guards)}) - delete the extra one")
    gid = guards[0]
    g = questions[gid]
    label = f"club guard (q{gid})"
    if g.get("type") != "control_text":
        problems.append(f"{label} is a {g.get('type')}, not a text element")
    if g.get("hidden") != "Yes":
        problems.append(f"{label} is not hidden: every mentor sees the warning")
    if g.get("text") != GUARD_PROPS["text"]:
        problems.append(f"{label} text is not glow.sync.guard_html() - the next sync run rewrites it")
    picker = club_picker(questions)
    if not picker:
        return problems + [f"{label} but no Club picker: nothing can show it"]
    options = picker_options(questions, picker)
    # directly below the picker: nothing a mentor can see renders between them
    shown = shown_by_rules(conditions)
    rank = {qid: (order_of(q), int(qid)) for qid, q in questions.items()}
    if rank[gid] < rank[picker]:
        problems.append(f"{label} renders above the Club picker (q{picker})")
    else:
        between = [qid for qid, q in questions.items() if rank[picker] < rank[qid] < rank[gid]
                   and (q.get("hidden") != "Yes" or q.get("type") == "control_checkbox" or qid in shown)]
        if between:
            problems.append(f"{label} is not directly below the Club picker (q{picker}): "
                            f"{len(between)} element(s) a mentor can see sit between them")
    buttons = [qid for qid, q in questions.items() if q.get("type") == "control_button"]
    if len(buttons) != 1:
        return problems + [f"{len(buttons)} Submit buttons, expected 1 - the guard hides and "
                           "disables one"]
    submit = buttons[0]
    want = {(picker, "isFilled", "")} | {(CLUB_NAME_QID, "notEquals", o) for o in options}
    rules = _parsed(conditions)
    shows = [(c, t, a) for c, t, a in rules
             if any(x.get("visibility") == "Show" and str(x.get("field")) == gid for x in a)]
    disables = [(c, t, a) for c, t, a in rules if c.get("type") == "require"
                and any(x.get("visibility") == "Disable" and str(x.get("field")) == submit for x in a)]

    def check(found, what, rule_type, actions):
        if len(found) != 1:
            problems.append(f"{len(found)} rule(s) {what}, expected 1")
        for c, terms, acts in found[:1]:
            rid = c.get("id")
            if c.get("type") != rule_type or c.get("link") != "All":
                problems.append(f"guard rule {rid} is a {c.get('type')} rule linking its terms with "
                                f"{c.get('link')}, expected a {rule_type} rule with All")
            if sorted((str(x.get("visibility")), str(x.get("field"))) for x in acts) != sorted(actions):
                problems.append(f"guard rule {rid} ({what}): its actions are not "
                                + " + ".join(f"{v} q{f}" for v, f in actions))
            have = {(str(t.get("field")), t.get("operator"), str(t.get("value") or "")) for t in terms}
            missing = [o for o in options if (CLUB_NAME_QID, "notEquals", o) not in have]
            extra = sorted(v or f"q{f} {op}" for f, op, v in have - want)
            if (picker, "isFilled", "") not in have:
                problems.append(f"guard rule {rid} does not test that the Club picker is filled")
            if missing:
                problems.append(f"guard rule {rid} misses {len(missing)} club(s) - their mentors "
                                f"cannot submit: {missing[:5]}")
            if extra:
                problems.append(f"guard rule {rid} tests {len(extra)} value(s) that are not the "
                                f"picker's options: {extra[:5]}")
    check(shows, "show the club guard", "field", [("Hide", submit), ("Show", gid)])
    if GUARD_DISABLES_SUBMIT:
        check(disables, "disable Submit", "require", [("Disable", submit)])
    return problems


MODULE_FIX = ("question 98 (module_id, what Salesforce stores) copies the visible text, which a "
              "browser's page translation rewrites; a sync apply by hand writes them (RUNBOOK \"The "
              "names dictionary and the module values\")")


def audit_module_values(questions):
    """The module dropdowns (glow.sync.MODULES), as glow/sync.py MODULE_CALC_VALUES says:
    on, each carries calcValues equal to its own options after the single-select's empty
    slot; off, none - or, if it still carries some, aligned ones (misaligned, question
    98 would send a neighbouring module). Returns (problems, {qid: {"options", "aligned"}})."""
    problems, summary = [], {}
    for year, qid in MODULES.items():
        q = questions.get(qid)
        if q is None:
            problems.append(f"module dropdown q{qid} (year {year}) is not on the form")
            continue
        options = dropdown_options(q)
        have = q.get("calcValues") or ""
        aligned = bool(options) and have == aligned_calc_values(options)
        summary[qid] = {"options": len(options), "aligned": aligned}
        if glow_sync.MODULE_CALC_VALUES and not aligned and options:
            problems.append(f"module dropdown q{qid} (year {year}): "
                            + (f"calcValues out of line with its {len(options)} options "
                               f"({len(have.split('|'))} values) - question 98 would send another "
                               "module; " if has_calc_values(q) else "no calcValues - ")
                            + MODULE_FIX)
        elif not glow_sync.MODULE_CALC_VALUES and has_calc_values(q) and not aligned:
            problems.append(f"module dropdown q{qid} (year {year}): calcValues out of line with its "
                            f"{len(options)} options - question 98 would send another module; a sync "
                            "apply by hand clears them (glow/sync.py MODULE_CALC_VALUES is off)")
    return problems, summary


SHAPE_FIX = ("fix it in the builder's form settings, then re-run; never a sync apply - the sync does not "
             "write it (RUNBOOK \"The names dictionary and the module values\")")
# what question 98 / 100 copies, per dropdown kind
SHAPE_KINDS = (("year", {None: YEAR}, "a blank year hides every module dropdown", None),
               ("module", {f"year {y}": q for y, q in MODULES.items()}, "a blank module reaches Salesforce", "98"),
               ("session", {f"{n} sessions": q for n, q in WEEKS.items()}, "a blank session reaches Salesforce", "100"))


def audit_module_shape(questions, props):
    """The module chain's shape (docs/plans/2026-10-06-module-selection.md): the year
    dropdown (glow.sync.YEAR) visible, every module and session dropdown (MODULES, WEEKS)
    single-select and required, and the form-level clearFieldOnHide equal to
    glow.sync.CLEAR_FIELD_ON_HIDE - so one module per submission, never blank, and a
    dropdown hidden by the Year rule never sends its answer. An unknown clearFieldOnHide
    value is reported as not read, never treated as cleared. Returns (problems, summary)."""
    problems, summary = [], {}
    for kind, qids, blank, copy_qid in SHAPE_KINDS:
        shapes = {}
        for label, qid in qids.items():
            q = questions.get(qid)
            where = f"{kind} dropdown q{qid}" + (f" ({label})" if label else "")
            if q is None:
                shapes[qid] = None
                problems.append(f"{where} is not on the form - the chain has no {kind} there; {SHAPE_FIX}")
                continue
            shape = {"single": q.get("multipleSelections") != "Yes", "required": q.get("required") == "Yes",
                     "dropdown": q.get("type") == "control_dropdown"}
            if kind == "year":
                shape["visible"] = q.get("hidden") != "Yes"
            shapes[qid] = shape
            if not shape["dropdown"]:
                problems.append(f"{where} is a {q.get('type')}, not a dropdown - {SHAPE_FIX}")
            if not shape["single"]:
                problems.append(f"{where} is a multi-select: a mentor could send two {kind}s"
                                + (f"; question {copy_qid} would run them together" if copy_qid else "")
                                + f" - {SHAPE_FIX}")
            if not shape["required"]:
                problems.append(f"{where} is not required: {blank} - {SHAPE_FIX}")
            if kind == "year" and not shape["visible"]:
                problems.append(f"{where} is hidden: the chain starts visible, or no mentor can pick a module - "
                                + SHAPE_FIX)
        summary[kind] = shapes
    value = props.get("clearFieldOnHide")
    summary["clearFieldOnHide"] = value
    want = glow_sync.CLEAR_FIELD_ON_HIDE
    if value != want:
        why = {"dontClear": "a module dropdown hidden by the Year rule would keep its answer at submit (two "
                            "modules, or last year's, in question 98)",
               "enable": "rejected 2026-09-30: the loop limit drops to 3 (DECISIONS)"}
        problems.append(f"clearFieldOnHide is {value!r}, not {want!r}: "
                        + why.get(value, "a value whose runtime behaviour has not been read - do not treat "
                                         "hidden answers as cleared")
                        + f" - {SHAPE_FIX}")
    return problems, summary


NAMES_FIX = "tools/fix_name_translations.py --form {form} (dry run first; RUNBOOK \"The names dictionary and the module values\")"


def roster_options(questions):
    """[(roster qid, club, option)] for every roster question's options."""
    return [(str(qid), " ".join(str(q.get("text") or "").split()), o)
            for qid, q in questions.items() if q.get("type") == "control_checkbox"
            for o in (q.get("options") or "").split("|") if o]


def audit_names(form_id, options, store, primary=tl.PRIMARY):
    """The form's own translation dictionary against its roster options, emulated as the
    runtime builds and uses it (glow/translation_lookup.py), in every language it holds
    and both runtime builds: question 18 sends what the lookup returns for a ticked girl.
    options: roster_options(). Returns (problems, summary); summary has counts and club
    names only - never a girl's name. A store that cannot be emulated is not checked
    (summary["checked"] False, a note for the runner), never guessed."""
    why = store if isinstance(store, str) else tl.check_store(store)
    if why:
        return [], {"checked": False, "why": why}
    hit = tl.altered(store, {o for _, _, o in options}, primary)
    found = [(qid, club, hit[o]) for qid, club, o in options if o in hit]
    langs = {}
    for _, _, ls in found:
        for lang in ls:
            langs[lang] = langs.get(lang, 0) + 1
    clubs = sorted({club for _, club, _ in found}, key=str.lower)
    summary = {"checked": True, "options": len(options), "altered": len(found), "clubs": clubs,
               "languages": len(tl.target_languages(store)), "by_language": langs}
    problems = []
    if found:
        problems.append(f"names dictionary: {len(found)} roster option(s) in {len(clubs)} club(s) are "
                        "altered by the form's own translation dictionary ("
                        + ", ".join(f"{lang} {n}" for lang, n in sorted(langs.items()))
                        + ") - question 18 would send another spelling of those girls' names "
                        f"(a second Contact in Salesforce): {NAMES_FIX.format(form=form_id)}")
    return problems, summary


def read_storage(client):
    """Jotform's account usage against its plan's limits (glow/usage.py) with the level per
    limit - the report's `storage` key, read once per run. A read that fails is reported
    ({"error": why}) and is never a form problem: the cap is account-wide, and the runner's
    verify step must not fail on it."""
    try:
        u = usage.read_usage(client)
    except (JotformError, ValueError) as err:
        return {"error": str(err)[:200]}
    return dict(u, levels=usage.levels(u))


def storage_status_line(store):
    """The report's `storage:` line, right after the Roster line; `!! ` at alarm (from read_storage)."""
    if "error" in store:
        return f"storage: could not be read ({store['error']})"
    return ("!! " if usage.worst(store["levels"]) == "alarm" else "") + usage.storage_line(store)


def read_store(client, form_id):
    """The form's translation store, or a short reason it could not be read (never the
    answer itself: it holds every girl's name)."""
    try:
        store = client.get(f"/form/{form_id}/translations")
    except JotformError:
        return "the store could not be read (an error or a non-JSON answer from Jotform)"
    return store


def embedded_store(page):
    """(the translation store the public page embeds - window.allTranslations.translations -,
    the primaryLanguage of its FormTranslation.init) in memory only; (None, None) when the
    page has none."""
    i = (page or "").find("window.allTranslations")
    j = page.find("{", i) if i >= 0 else -1
    if j < 0:
        return None, None
    try:
        value, _ = json.JSONDecoder().raw_decode(page, j)
    except ValueError:
        return None, None
    store = value.get("translations") if isinstance(value, dict) else None
    m = re.search(r'FormTranslation\.init\(\{[^<]*?"primaryLanguage"\s*:\s*"([^"]+)"', page)
    return (store if isinstance(store, dict) else None), (m.group(1) if m else tl.PRIMARY)


def rendered_options(page, rosters):
    """[(roster qid, "q<qid>", value)] of the roster checkboxes the page serves (the values
    stay in memory: they are girls' names)."""
    rosters = {str(q) for q in rosters}
    out = []
    for tag in re.findall(r"<input\b[^>]*>", page or ""):
        if not re.search(r'\btype="checkbox"', tag):
            continue
        m = re.search(r'\bid="input_(\d+)_\d+"', tag)
        v = re.search(r'(?<![\w-])value="([^"]*)"', tag)
        if m and v and m.group(1) in rosters:
            out.append((m.group(1), f"q{m.group(1)}", html.unescape(v.group(1))))
    return out


def rendered_calc_values(page, picker):
    """Counts, from the public page's HTML (kept in memory, never printed or
    saved - it lists every roster), of the picker's options whose
    data-calcvalue equals their value: {"options", "aligned", "differ",
    "missing"}; None when the page has no such select."""
    m = re.search(r'<select\b[^>]*\bname="q%s_[^"]*"[^>]*>(.*?)</select>' % re.escape(str(picker)),
                  page or "", re.S)
    if not m:
        return None
    counts = {"options": 0, "aligned": 0, "differ": 0, "missing": 0}
    for attrs in re.findall(r"<option\b([^>]*)>", m.group(1)):
        value = re.search(r'(?<![\w-])value="([^"]*)"', attrs)
        calc = re.search(r'\bdata-calcvalue="([^"]*)"', attrs)
        if not value or not value.group(1):
            continue                         # a placeholder, if the page has one
        counts["options"] += 1
        if not calc:
            counts["missing"] += 1
        elif html.unescape(calc.group(1)) == html.unescape(value.group(1)):
            counts["aligned"] += 1
        else:
            counts["differ"] += 1
    return counts


def page_array(page, name):
    """The JSON array the public page hands to JotForm.<name>(…), parsed (in memory
    only); None when the page has no such call or it does not parse."""
    call = f"JotForm.{name}("
    i = (page or "").find(call)
    if i < 0:
        return None
    start = i + len(call)
    while start < len(page) and page[start].isspace():
        start += 1
    try:
        value, _ = json.JSONDecoder().raw_decode(page, start)
    except ValueError:
        return None
    return value if isinstance(value, list) else None


def runtime_build(page):
    """The build id of Jotform's runtime the page loads (cdn.jotfor.ms/s/static/<build>/…),
    or None. The rule walk question 18 relies on is that runtime's behaviour, not a
    contract: a new build is worth a browser check."""
    m = (re.search(r"/s/static/([0-9a-f]+)/static/jotform\.forms\.js", page or "")
         or re.search(r"/s/static/([0-9a-f]+)/", page or ""))
    return m.group(1) if m else None


def rendered_rules(page, rosters):
    """Question 18 as the page serves it (counts and qids only): {"rules": how many
    JotForm.setConditions holds, "position": the 0-based place of question 18's
    calculation in it (None: not there), "roster_rules": rules showing a roster,
    "first_roster_rule": the place of the first, "operands": question 18's operands
    in JotForm.setCalculations (None: no entry)}. None when the page has neither array."""
    conds, calcs = page_array(page, "setConditions"), page_array(page, "setCalculations")
    if conds is None or calcs is None:
        return None
    shape = glow_sync.contact_ids_layout(conds, rosters)
    calc = next((c for c in calcs if isinstance(c, dict)
                 and str(c.get("resultField")) == CONTACT_IDS_QID), None)
    return {"rules": len(conds), "position": shape["position"], "roster_rules": len(shape["roster_rules"]),
            "first_roster_rule": min(shape["roster_rules"]) if shape["roster_rules"] else None,
            "operands": None if calc is None else [x for x in str(calc.get("operands") or "").split(",") if x]}


def rendered_required(page, rosters):
    """The roster checkboxes on the page, counted (never printed: their values are
    girls' names): {"rosters": rosters with a box, "required": rosters with at least
    one box whose class carries validate[required] - what Jotform checks at submit,
    the whole roster at once - "boxes", "boxes_required"}."""
    rosters = {str(q) for q in rosters}
    per = {}
    for tag in re.findall(r"<input\b[^>]*>", page or ""):
        if not re.search(r'\btype="checkbox"', tag):
            continue
        m = re.search(r'\bid="input_(\d+)_\d+"', tag)
        if not m or m.group(1) not in rosters:
            continue
        cls = re.search(r'\bclass="([^"]*)"', tag)
        # the runtime joins a field's validations in one class: validate[required,Email]
        per.setdefault(m.group(1), []).append(
            bool(cls and re.search(r"validate\[[^\]]*\brequired\b", cls.group(1))))
    return {"rosters": len(per), "required": sum(1 for v in per.values() if any(v)),
            "boxes": sum(len(v) for v in per.values()), "boxes_required": sum(sum(v) for v in per.values())}


def rendered_problems(r, page):
    """--rendered: what the served page says against what the API audit expects,
    each expectation from glow/sync.py's constants. Adds r["build"], r["rendered_rules"],
    r["rendered_required"] (and r["rendered"], the picker's calcValues) and returns problems."""
    problems = []
    r["build"] = runtime_build(page)
    picker = r["club_picker"]
    if picker:
        counts = rendered_calc_values(page, picker)
        r["rendered"] = counts
        if counts is None:
            problems.append("--rendered: the public page has no Club picker select "
                            "(page not served, or its layout changed)")
        elif r["picker_calc_values"]:            # before the rollout the counts are only printed
            if counts["differ"] or counts["missing"] or counts["aligned"] != counts["options"]:
                problems.append(
                    f"rendered page: {counts['differ']} of {counts['options']} picker options carry a "
                    f"data-calcvalue other than their value, {counts['missing']} none - the copy "
                    "into question 5 would send another club's name (RUNBOOK, One club per "
                    "submission: stop and restore)")
            # an option the parser could not read is one the check cannot vouch for
            if counts["options"] != r["picker_options"]:
                problems.append(
                    f"rendered page lists {counts['options']} of the picker's {r['picker_options']} "
                    "options - a page served from before the apply (re-run in a few minutes) or a "
                    "layout this check cannot read: do not treat it as aligned")
        rules = rendered_rules(page, r["roster_qids"])
        r["rendered_rules"] = rules
        if rules is None or rules["position"] is None:
            problems.append("rendered page: no calculation of question 18 in JotForm.setConditions (page "
                            "not served, or its layout changed) - the served order cannot be vouched for")
        else:
            if glow_sync.CONTACT_IDS_FIRST and rules["first_roster_rule"] is not None \
                    and rules["first_roster_rule"] < rules["position"]:
                problems.append(f"rendered page: question 18 is rule {rules['position'] + 1} of {rules['rules']} "
                                "in JotForm.setConditions, after the rosters' rules - the old order (a page "
                                "served from before the apply: re-run in a few minutes; else stop, RUNBOOK "
                                "\"The names list sent to Salesforce\")")
            if glow_sync.CONTACT_IDS_PICKER_OPERAND and str(picker) not in (rules["operands"] or []):
                problems.append(f"rendered page: question 18's entry in JotForm.setCalculations does not list "
                                f"the Club picker (q{picker}) - Jotform dropped the operand, or the page is from "
                                "before the apply (RUNBOOK \"The names list sent to Salesforce\")")
    req = rendered_required(page, r["roster_qids"])
    r["rendered_required"] = req
    if glow_sync.ROSTERS_REQUIRED:
        if req["rosters"] != len(r["roster_qids"]):
            problems.append(f"rendered page shows boxes for {req['rosters']} of the form's "
                            f"{len(r['roster_qids'])} rosters - a page this check cannot read: do not "
                            "treat the rosters as required")
        elif req["required"] != req["rosters"]:
            problems.append(f"rendered page: {req['rosters'] - req['required']} of {req['rosters']} rosters "
                            "carry no validate[required] on their boxes - Jotform would not refuse a "
                            "submission with no girl ticked there (a page from before the apply: re-run in "
                            "a few minutes; else stop, RUNBOOK \"The names list sent to Salesforce\")")
    elif req["required"]:
        problems.append(f"rendered page: {req['required']} rosters still carry validate[required] although "
                        "glow/sync.py ROSTERS_REQUIRED is off")
    return problems + rendered_module_problems(r, page) + rendered_names_problems(r, page)


def rendered_select_attrs(page, qid):
    """The attributes of the <select> the page serves for question `qid` (its opening tag,
    in memory), or None when the page has no such select."""
    m = re.search(r'<select\b([^>]*\bname="q%s_[^"]*"[^>]*)>' % re.escape(str(qid)), page or "")
    return m.group(1) if m else None


def rendered_clear_field_on_hide(page):
    """The clearFieldOnHide value the public page hands its runtime (JotForm.clearFieldOnHide =
    "…", seen on the served template page 2026-10-06), or None when the page has none."""
    m = re.search(r'JotForm\.clearFieldOnHide\s*=\s*"([^"]*)"', page or "")
    return m.group(1) if m else None


def rendered_module_problems(r, page):
    """--rendered: each module dropdown's options and their data-calcvalue, as glow/sync.py
    MODULE_CALC_VALUES says (adds r["rendered_modules"]: {qid: counts or None}), and the
    chain's shape as served (adds r["rendered_shape"]: the page's clearFieldOnHide and the
    module selects served with a `multiple` attribute), as CLEAR_FIELD_ON_HIDE says."""
    problems, seen, multi = [], {}, []
    for year, qid in MODULES.items():
        counts = rendered_calc_values(page, qid)
        seen[qid] = counts
        attrs = rendered_select_attrs(page, qid)
        if attrs is not None and re.search(r"\bmultiple\b", attrs):
            multi.append(qid)
            problems.append(f"rendered page: module dropdown q{qid} is served as a multi-select (<select "
                            "multiple>) - a mentor could send two modules; question 98 would run them together")
        want = ((r.get("module_values") or {}).get(qid) or {}).get("options")
        if counts is None:
            problems.append(f"rendered page: no select for module dropdown q{qid} (page not served, or its "
                            "layout changed) - its values cannot be vouched for")
        elif glow_sync.MODULE_CALC_VALUES and (counts["differ"] or counts["missing"]
                                               or counts["aligned"] != counts["options"]):
            problems.append(f"rendered page: module dropdown q{qid}: {counts['missing']} of {counts['options']} "
                            f"options carry no data-calcvalue, {counts['differ']} one other than their value "
                            "(a page from before the apply: re-run in a few minutes) - " + MODULE_FIX)
        elif glow_sync.MODULE_CALC_VALUES and want is not None and counts["options"] != want:
            problems.append(f"rendered page lists {counts['options']} of module dropdown q{qid}'s {want} options "
                            "- a page from before the apply or a layout this check cannot read: do not treat "
                            "it as aligned")
        elif not glow_sync.MODULE_CALC_VALUES and counts["differ"]:
            problems.append(f"rendered page: module dropdown q{qid}: {counts['differ']} of {counts['options']} "
                            "options carry a data-calcvalue other than their value - question 98 would send "
                            "another module")
    r["rendered_modules"] = seen
    cleared = rendered_clear_field_on_hide(page)
    r["rendered_shape"] = {"clearFieldOnHide": cleared, "multi_select": multi}
    if cleared is None:
        problems.append("rendered page: no JotForm.clearFieldOnHide on the public page (page not served, or its "
                        "layout changed) - whether a hidden module dropdown's answer is cleared at submit cannot "
                        "be vouched for")
    elif cleared != glow_sync.CLEAR_FIELD_ON_HIDE:
        problems.append(f"rendered page: JotForm.clearFieldOnHide is {cleared!r}, not "
                        f"{glow_sync.CLEAR_FIELD_ON_HIDE!r} (a page from before the builder fix: re-run in a few "
                        "minutes; else " + SHAPE_FIX + ")")
    return problems


def rendered_names_problems(r, page):
    """--rendered: the names dictionary the page embeds against the roster boxes it serves,
    emulated (adds r["rendered_names"], counts only)."""
    store, primary = embedded_store(page)
    if store is None:
        r["rendered_names"] = {"checked": False, "why": "the page embeds no translation store"}
        return ["rendered page: no embedded translation store (window.allTranslations) - the names "
                "dictionary it serves cannot be vouched for"]
    options = rendered_options(page, r.get("roster_qids") or [])
    _, summary = audit_names(r.get("id", ""), options, store, primary)
    r["rendered_names"] = {k: v for k, v in summary.items() if k != "clubs"}
    if not summary.get("checked"):
        return [f"rendered page: its translation store cannot be emulated ({summary.get('why')})"]
    if summary["altered"]:
        rosters = len({c for c in summary["clubs"]})
        r["rendered_names"]["rosters"] = rosters
        return [f"rendered page: the embedded dictionary alters {summary['altered']} of the {summary['options']} "
                f"roster options it serves ({rosters} roster(s)) - question 18 would send another spelling "
                "(a page from before the fix: re-run in a few minutes; else "
                + NAMES_FIX.format(form=r.get("id", "<id>")) + ")"]
    return []


def public_page(form_id):
    """The form as a mentor's browser receives it (curl, like every call here)."""
    out = subprocess.run(["curl", "-sSL", "--max-time", "90", f"https://form.jotform.com/{form_id}"],
                         capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else ""


def tested_values(questions, conditions):
    """{roster qid: the text its show rule tests on the club field} - the Club
    picker entry that shows it, which is also what question 5 sends for that
    club. A roster with no such rule, or several, is left out."""
    club_field = club_picker(questions) or CLUB_NAME_QID
    rosters = {qid for qid, q in questions.items() if q.get("type") == "control_checkbox"}
    found = defaultdict(list)
    for _, terms, actions in _parsed(conditions):
        for a in actions:
            if a.get("visibility") == "Show" and str(a.get("field")) in rosters:
                found[str(a["field"])].append(
                    [" ".join(str(t.get("value")).split()) for t in terms
                     if str(t.get("field")) == club_field])
    return {qid: values[0][0] for qid, values in found.items() if len(values) == 1 and values[0]}


def rules_showing(conditions, qid):
    """ids of the rules with a Show action on question `qid`."""
    return [c.get("id") for c, _, actions in _parsed(conditions)
            if any(a.get("visibility") == "Show" and str(a.get("field")) == str(qid) for a in actions)]


def is_long_name(value, text):
    """Whether a tested value is a roster's long name: its own text, the
    separator, and something after it (never split on the separator)."""
    head = key(text) + SF_NAME_SEP
    return key(value).startswith(head) and len(key(value)) > len(head)


def audit_rules(questions, conditions, partners_of=None):
    """Rule-level checks on a form's live conditions. Returns a list of
    problem strings (empty = clean) and a summary dict. partners_of: the
    Roster's {key(club): {key(partner): partner}} (load_partners); with it a
    long name's partner must be one the Roster has for that club."""
    problems = []
    qids = set(questions)
    picker = club_picker(questions)
    club_field = picker or CLUB_NAME_QID
    plist = partner_picker(questions)            # a retired partner list left on the form
    partner_fields = {PARTNER_QID, plist} if plist else {PARTNER_QID}
    clubs = {qid: " ".join(q["text"].split()) for qid, q in questions.items()
             if q.get("type") == "control_checkbox"}
    shown_by = defaultdict(list)     # club qid -> [rule ids that show it]
    for c in conditions:
        try:
            terms = json.loads(c["terms"]) if isinstance(c["terms"], str) else c["terms"]
            actions = json.loads(c["action"]) if isinstance(c["action"], str) else c["action"]
        except (KeyError, ValueError, TypeError):
            problems.append(f"rule {c.get('id')}: terms/action not parseable")
            continue
        for t in terms:
            if str(t.get("field")) not in qids:
                problems.append(f"rule {c.get('id')}: term refers to missing question {t.get('field')}")
        for a in actions:
            f = a.get("field") or a.get("resultField")
            if f is not None and str(f) not in qids:
                problems.append(f"rule {c.get('id')}: action refers to missing question {f}")
            if a.get("visibility") == "Show" and str(a.get("field")) in clubs:
                shown_by[str(a["field"])].append((c.get("id"), terms))
    # Every club roster has exactly one show-rule, whose club term is the text
    # the roster sends to question 5: its own text, or - with the Club picker -
    # its long name, "<text> - <partner>" (docs/plans/2026-09-30-same-name-
    # clubs.md). Rosters are grouped by that tested text, not by their own: two
    # that test the same text need the Partner box to be told apart; one alone
    # on its text must not ask for a partner.
    tested, partner_terms, long_names = {}, {}, 0
    for qid, name in clubs.items():
        rules = shown_by.get(qid, [])
        if len(rules) != 1:
            problems.append(f"'{name}' (q{qid}) has {len(rules)} show-rules, expected 1")
            continue
        _, terms = rules[0]
        partner_terms[qid] = [t for t in terms if str(t.get("field")) in partner_fields]
        club_terms = [t for t in terms if str(t.get("field")) == club_field]
        value = " ".join(str(club_terms[0].get("value")).split()) if club_terms else None
        if value is None or not (key(value) == key(name) or (picker and is_long_name(value, name))):
            problems.append(f"'{name}' (q{qid}): show-rule does not test the club field "
                            f"(q{club_field}) == its text"
                            + (" or its text + ' - ' + its partner" if picker else ""))
            continue
        tested[qid] = value
        if key(value) != key(name):
            long_names += 1
            if partners_of is not None and \
                    long_name_partner(value, name, partners_of.get(key(name))) is None:
                problems.append(f"'{name}' (q{qid}): its rule tests '{value}', but the Roster has no "
                                f"partner of that name with a club '{name}' - the next sync run "
                                "lists it as a question-5 change")
    by_value = defaultdict(list)
    for qid, value in tested.items():
        by_value[key(value)].append(qid)
    for qid, value in tested.items():
        name = clubs[qid]
        if len(by_value[key(value)]) > 1 and not partner_terms[qid]:
            problems.append(f"'{name}' (q{qid}) tests the same text as another roster ('{value}') "
                            "but its rule has no Partner term")
        if len(by_value[key(value)]) == 1 and partner_terms[qid]:
            problems.append(f"'{name}' (q{qid}) is unique but its rule needs a Partner")
    if plist:
        problems.append(f"partner list (q{plist}) on the form: the partner list was retired "
                        "2026-09-30 and the sync refuses a form carrying one - delete it in the "
                        "builder")
    ids_problems, shape = audit_contact_ids(questions, conditions)
    problems += ids_problems
    problems += audit_picker(questions, conditions) + audit_club_guard(questions, conditions)
    summary = {"clubs": len(clubs), "show_rules": sum(len(v) for v in shown_by.values()),
               "aggregate_rosters": len(set(clubs) & set(shape["operands"])), "long_names": long_names,
               # question 18's rule, 1-based (None: no such rule), and whether it lists the picker
               "contact_ids_rule": None if shape["position"] is None else shape["position"] + 1,
               "rules": shape["count"],
               "contact_ids_picker_operand": bool(picker and picker in shape["operands"]),
               "required_rosters": sum(1 for q in clubs if questions[q].get("required") == "Yes")}
    return problems, summary


def audit_contact_ids(questions, conditions):
    """Question 18 (Contact_IDs, the names Salesforce stores as present) and the
    at-least-one-girl guard, each expectation derived from glow/sync.py's
    constants, so a fallback or the generated rollback (a constant off) is clean
    once applied (docs/plans/2026-09-30-contact-ids.md). Returns (problems,
    glow.sync.contact_ids_layout of the rules)."""
    picker = club_picker(questions)
    rosters = {qid for qid, q in questions.items() if q.get("type") == "control_checkbox"}
    shape = glow_sync.contact_ids_layout(conditions, rosters)
    problems = []
    want = glow_sync.roster_required()
    off = sorted((q for q in rosters if (questions[q].get("required") or "No") != want), key=int)
    if off and want == "Yes":
        problems.append(f"{len(off)} of {len(rosters)} roster(s) not required (first q{off[0]}): a mentor "
                        "can send her club with no girl ticked - Salesforce stores an empty batch that "
                        "blocks the club's day; a sync apply by hand sets the flag")
    elif off:
        problems.append(f"{len(off)} of {len(rosters)} roster(s) required (first q{off[0]}) although "
                        "glow/sync.py ROSTERS_REQUIRED is off - a sync apply by hand clears the flag")
    if shape["position"] is None:
        return problems + ["no Contact_IDs aggregate calculation found"], shape
    if len(shape["calc_rules"]) > 1:
        problems.append(f"{len(shape['calc_rules'])} rules calculate question 18 (Contact_IDs), expected 1")
    operands = set(shape["operands"])
    for op in sorted(operands - set(questions)):
        problems.append(f"Contact_IDs aggregate refers to missing question {op}")
    allowed = rosters | ({picker} if picker and glow_sync.CONTACT_IDS_PICKER_OPERAND else set())
    missing, extra = rosters - operands, (operands & set(questions)) - allowed
    if missing:
        problems.append(f"Contact_IDs aggregate misses {len(missing)} roster(s): {sorted(missing, key=int)[:5]}")
    if extra:
        problems.append(f"Contact_IDs aggregate includes {len(extra)} non-roster question(s): {sorted(extra)[:5]}")
    # the equation: one {qid} per roster and nothing else - a picker in it would send the
    # club's name as a girl, a literal would be written between hidden rosters too
    tokens = re.findall(r"\{([^{}]*)\}", shape["equation"])
    rest = re.sub(r"\{[^{}]*\}", "", shape["equation"])
    if rest or sorted(tokens) != sorted(rosters):
        problems.append(f"question 18's equation is not one {{qid}} per roster: {len(tokens)} field(s) for "
                        f"{len(rosters)} roster(s)"
                        + (f", {len(set(tokens) - rosters)} not a roster" if set(tokens) - rosters else "")
                        + (f", {len(tokens) - len(set(tokens))} twice" if len(tokens) != len(set(tokens)) else "")
                        + (", text between them" if rest else "")
                        + " - the next sync apply rewrites it")
    if not picker:            # the typed club name: question 18's rule keeps its shape (byte for byte)
        return problems, shape
    if glow_sync.CONTACT_IDS_FIRST:
        before = [p for p in shape["roster_rules"] if p < shape["position"]]
        if before:
            problems.append(f"question 18 (Contact_IDs) is calculated by rule {shape['position'] + 1} of "
                            f"{shape['count']}, after {len(before)} rule(s) that show a roster: on a change "
                            "of club Jotform calculates it before the rosters show or hide (another club's "
                            "girls sent, or none) - a sync apply by hand puts it first")
    if glow_sync.CONTACT_IDS_PICKER_OPERAND and picker not in operands:
        problems.append(f"the Club picker (q{picker}) is not one of question 18's operands - a sync apply "
                        "by hand adds it")
    # every field a roster rule tests must make question 18 re-run after the rosters: as a
    # term of its rule (then Jotform's walk for that field ends with it: the order), else -
    # with the order off - as an operand
    if glow_sync.CONTACT_IDS_FIRST:
        covered, how = shape["terms"], "test"
    elif glow_sync.CONTACT_IDS_PICKER_OPERAND:      # (the picker's own operand: the check above)
        covered, how = operands | {picker}, "list as an operand"
    else:
        covered, how = None, ""
    for field, n in sorted((shape["roster_rule_fields"] if covered is not None else {}).items()):
        if field not in covered:
            problems.append(f"{n} rule(s) that show a roster test q{field}, which question 18's rule does "
                            f"not {how}: when q{field} shows or hides a roster, question 18 is not "
                            "recalculated (a rule on another field than the Club picker needs it in "
                            "question 18's rule too - not generated by the sync)")
    return problems, shape


def contact_ids_line(summary, picker):
    """The printed report's `question 18:` line, from audit_rules' summary."""
    if summary.get("contact_ids_rule") is None:
        return "no calculation"
    return (f"rule {summary['contact_ids_rule']} of {summary['rules']}"
            + (f", the Club picker an operand: {'yes' if summary['contact_ids_picker_operand'] else 'no'}"
               if picker else ""))


def module_values_line(summary):
    """The printed report's `module values:` line, from form_report's `module_values`."""
    if not summary:
        return "no module dropdown on the form"
    return ", ".join(f"q{qid} {'aligned' if s['aligned'] else 'none or out of line'} ({s['options']} options)"
                     for qid, s in summary.items())


def module_shape_line(summary):
    """The printed report's `module shape:` line, from form_report's `module_shape`."""
    if not summary:
        return "not read"
    parts = []
    for kind, qids, _, _ in SHAPE_KINDS:
        shapes = summary.get(kind) or {}
        odd = []
        for qid in qids.values():
            s = shapes.get(qid)
            if s is None:
                odd.append(f"q{qid} missing")
                continue
            words = ([] if s["dropdown"] else ["not a dropdown"]) + ([] if s["single"] else ["multi-select"]) \
                + ([] if s["required"] else ["not required"]) + ([] if s.get("visible", True) else ["hidden"])
            if words:
                odd.append(f"q{qid} " + ", ".join(words))
        head = f"{kind}{'' if kind == 'year' else 's'} " + "/".join(f"q{q}" for q in qids.values())
        parts.append(head + (" single-select required" if not odd else ": " + "; ".join(odd)))
    return "; ".join(parts) + f"; clearFieldOnHide {summary.get('clearFieldOnHide') or 'unset'}"


def names_line(summary):
    """The printed report's `names dictionary:` line, from form_report's `names_dictionary`
    (counts and club names only)."""
    if not summary or not summary.get("checked"):
        return f"not checked ({(summary or {}).get('why') or 'store not read'})"
    line = (f"{summary['altered']} of {summary['options']} roster options altered "
            f"({summary['languages']} language(s) checked)")
    if summary["altered"]:
        clubs = summary["clubs"]
        line += (f" in {len(clubs)} club(s): " + "; ".join(clubs[:8])
                 + (f"; and {len(clubs) - 8} more" if len(clubs) > 8 else ""))
    return line


def partner_box_line(box, picker):
    """The printed report's `partner box:` line, from form_report's `partner_box`."""
    if not box:
        return f"no q{PARTNER_QID} on the form"
    if box["shown_by_rules"]:
        return (f"q{PARTNER_QID} shown by {box['shown_by_rules']} rule(s): rosters that share a "
                "text are told apart by the typed partner")
    if box["hidden"]:
        return f"q{PARTNER_QID} hidden, no rule shows it"
    return (f"q{PARTNER_QID} VISIBLE to every mentor, and no rule uses it"
            + (" - the next sync apply hides it" if picker else ""))


def layout_line(lo):
    """The printed report's `layout:` line, from form_report's `layout` field."""
    n = lo.get("submit_buttons") or 0
    if n > 1:                    # layout.summary finds no fence then: the links are not looked at
        return f"{n} Submit buttons, expected 1 - rosters not checked"
    if not lo.get("fence"):
        return f"{lo.get('submit_buttons')} Submit button(s), no link"
    if lo.get("rosters_below"):
        return (f"{lo['rosters_below']} of {lo['rosters']} rosters render below {lo['fence']} "
                f"(first q{lo['first_below']}) - {layout.FIX}")
    return f"every roster above {lo['fence']}"


def form_report(form_id, client, roster_by_region, partners_of=None):
    label, region = FORMS.get(form_id) or DEFUNCT.get(form_id) or (form_id, None)
    props = client.get(f"/form/{form_id}/properties", limit=1000)
    questions = client.get(f"/form/{form_id}/questions", limit=1000)
    info = client.get(f"/form/{form_id}", limit=1000)

    clubs = {}
    for q in questions.values():
        if q.get("type") == "control_checkbox":
            text = " ".join(q["text"].split())
            opts = {name_key(o) for o in (q.get("options") or "").split("|") if o.strip()}
            clubs.setdefault(key(text), []).append((text, opts, q["qid"]))

    conditions = props.get("conditions") or []
    # two questions with one text are duplicates unless each has its own picker entry
    # (two partners' clubs of one name: "<club> - <partner>"); rosters the typed Partner
    # box still tells apart test one text and are still listed
    tested = tested_values(questions, conditions)
    dup_clubs = [v[0][0] for v in clubs.values()
                 if len(v) > len({key(tested.get(str(qid), text)) for text, _, qid in v})]
    errored = sum(1 for c in conditions if str(c.get("isError", "")).lower() in ("1", "true"))
    emails = props.get("emails") or []
    autorespond = sum(1 for e in emails if e.get("type") == "autorespond")
    integ = props.get("integrations") or {}
    sf = bool(isinstance(integ, dict) and integ.get("salesforceV2"))
    fuzzy = questions.get(ENABLE_FUZZY_QID, {})
    mentor_email = any(q.get("type") == "control_email" for q in questions.values())

    rule_problems, rule_summary = audit_rules(questions, conditions, partners_of)
    # a roster rendering below the links / Submit shows a mentor her names under the button
    rule_problems += layout.audit_layout(questions)
    # question 98's module: each module dropdown's calcValues (glow/sync.py MODULE_CALC_VALUES)
    module_problems, module_summary = audit_module_values(questions)
    rule_problems += module_problems
    # the chain's shape: one required single-select per step, hidden ones cleared at submit
    shape_problems, shape_summary = audit_module_shape(questions, props)
    rule_problems += shape_problems
    # question 18's names: the form's own translation dictionary must alter no roster option
    # (one more GET; a store that cannot be read or emulated is reported, not a problem)
    lang = props.get("language")
    lang = lang[0] if isinstance(lang, list) and lang else (lang or {})
    names_problems, names_summary = audit_names(form_id, roster_options(questions), read_store(client, form_id),
                                                lang.get("primaryLanguage") or tl.PRIMARY)
    rule_problems += names_problems
    picker = club_picker(questions)
    if picker:
        # the picker's options are the texts the rosters' rules test (a club's own
        # name, or its long name "<club> - <partner>"), no more and no fewer; a
        # roster with no readable rule counts by its own text
        listed = {key(o): o for o in (questions[picker].get("options") or "").split("|") if o.strip()}
        wanted ={str(qid): tested.get(str(qid), text) for v in clubs.values() for text, _, qid in v}
        missing = sorted({text for v in clubs.values() for text, _, qid in v
                          if key(wanted[str(qid)]) not in listed})
        extra = sorted(o for k, o in listed.items() if k not in {key(w) for w in wanted.values()})
        if missing:
            rule_problems.append(f"club picker misses {len(missing)} club(s): {missing[:5]}")
        if extra:
            rule_problems.append(f"club picker lists {len(extra)} name(s) with no roster: {extra[:5]}")
        if questions[picker].get("required") != "Yes":
            rule_problems.append("club picker is not required")
        if questions.get(CLUB_NAME_QID, {}).get("hidden") != "Yes":
            rule_problems.append("club picker present but the Club Name textbox is still visible")
    languages = [x for x in str(lang.get("options", "")).split("|") if x]
    if len(languages) < 2:
        rule_problems.append(f"only {languages or ['no']} language(s) offered - the API clone "
                             "resets this; run tools/restore_translations.py")
    guards = club_guards(questions)
    box = questions.get(PARTNER_QID)
    rep = {
        "rule_problems": rule_problems, "rule_summary": rule_summary,
        # rosters whose rule tests "<club> - <partner>": what question 5 sends for them
        "same_name_rosters": rule_summary.get("long_names", 0),
        # the typed Partner box: hidden, or how many rules show it (informational: on a
        # picker form with no such rule the next sync apply hides it)
        "partner_box": ({"hidden": box.get("hidden") == "Yes",
                         "shown_by_rules": len(rules_showing(conditions, PARTNER_QID))}
                        if box else None),
        "layout": layout.summary(questions),
        "languages": languages, "club_picker": picker, "partner_picker": partner_picker(questions),
        "club_guard": ({"qid": guards[0], "clubs": len(picker_options(questions, picker)) if picker else 0}
                       if guards else None),
        "picker_calc_values": bool(picker and has_calc_values(questions[picker])),
        "picker_options": len(picker_options(questions, picker)) if picker else 0,
        # {module qid: {"options": n, "aligned": calcValues = its options}}; the chain's shape
        # (per kind, {qid: {"single", "required", "dropdown"}}, and "clearFieldOnHide"); the names
        # dictionary: counts and club names only ("checked": False when the store was not read)
        "module_values": module_summary, "module_shape": shape_summary, "names_dictionary": names_summary,
        "id": form_id, "label": label, "title": info.get("title"), "status": info.get("status"),
        "submissions": int(info.get("count") or 0), "last_submission": info.get("last_submission"),
        "questions": len(questions), "club_questions": sum(len(v) for v in clubs.values()),
        # the rosters a mentor can tick a girl on (qids only): what --rendered counts on the page
        "roster_qids": sorted((str(qid) for v in clubs.values() for _, opts, qid in v if opts), key=int),
        "duplicate_club_questions": dup_clubs,
        "options_total": sum(len(o) for v in clubs.values() for _, o, _ in v),
        "conditions": len(conditions), "error_conditions": errored,
        "emails": len(emails), "autoresponders": autorespond, "mentor_email_field": mentor_email,
        "salesforce": sf,
        "enable_fuzzy": {"required": fuzzy.get("required"), "selected": fuzzy.get("selected"),
                         "hidden": fuzzy.get("hidden")},
    }

    if region and region in roster_by_region:
        want = roster_by_region[region]
        have = set(clubs)
        missing = [want[k][0] for k in want if k not in have]
        extra = [clubs[k][0][0] for k in clubs if k not in want]
        stale = []
        for k in want:
            if k in clubs:
                # same-named clubs (different partners) each have their own question;
                # the roster side merges them by name, so compare union against union
                on_form = set().union(*(opts for _, opts, _ in clubs[k]))
                if on_form != want[k][1]:
                    stale.append((want[k][0], len(want[k][1] - on_form), len(on_form - want[k][1])))
        rep["region_check"] = {
            "roster_clubs": len(want), "missing_from_form": missing, "not_in_roster": extra,
            "rosters_out_of_date": stale,
        }
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--form", action="append")
    ap.add_argument("--roster", default=os.path.join(REPO, "data", "roster_build", "Roster.csv"))
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--defunct", action="store_true", help="include the retired forms")
    ap.add_argument("--rendered", action="store_true",
                    help="also read each form's public page (counts only; the page is never "
                         "printed or saved) and check what it serves: every Club picker option's "
                         "data-calcvalue equals its value, question 18's calculation comes before "
                         "the rosters' rules and lists the picker, every roster's boxes carry "
                         "validate[required], every module dropdown option's data-calcvalue equals "
                         "its value, no module select is served `multiple`, JotForm.clearFieldOnHide "
                         "is what glow/sync.py says, and the translation store the page embeds alters "
                         "no roster box it serves; prints the runtime build")
    args = ap.parse_args()
    if args.defunct:
        FORMS.update(DEFUNCT)
    api_key = os.environ.get("JOTFORM_API_KEY") or sys.exit("Set JOTFORM_API_KEY")
    client = Client(api_key)
    storage = read_storage(client)        # once per run: account-wide, every report carries it
    roster = load_roster(args.roster)
    partners_of = load_partners(args.roster) or None     # an empty Roster vouches for no partner

    reports = [form_report(f, client, roster, partners_of) for f in (args.form or FORMS)]
    for r in reports:
        r["storage"] = storage
    if args.rendered:
        for r in reports:
            r["rule_problems"] += rendered_problems(r, public_page(r["id"]))
    if args.json:
        print(json.dumps(reports, indent=1))
        return

    print("Roster (active girls):", {r: len(c) for r, c in roster.items()}, "clubs per region")
    print(storage_status_line(storage) + "\n")
    for r in reports:
        print(f"== {r['label']}  {r['id']}  \"{r['title']}\"  [{r['status']}]")
        last = f"{r['last_submission']} US Eastern" if r["last_submission"] else "none"  # Jotform's clock
        print(f"   submissions {r['submissions']} (last {last})   "
              f"questions {r['questions']}   club questions {r['club_questions']} "
              f"({r['options_total']} girl options)")
        print(f"   conditions {r['conditions']} ({r['error_conditions']} flagged as error)   "
              f"emails {r['emails']} ({r['autoresponders']} autoresponder)   "
              f"mentor email field {'yes' if r['mentor_email_field'] else 'NO'}   "
              f"salesforce {'yes' if r['salesforce'] else 'NO'}")
        f = r["enable_fuzzy"]
        print(f"   enableFuzzy: required={f['required']} selected={f['selected']!r} hidden={f['hidden']}")
        print(f"   languages: {len(r['languages'])} ({', '.join(r['languages'][:4])}{'…' if len(r['languages']) > 4 else ''})")
        print(f"   club picker: {'q' + r['club_picker'] if r['club_picker'] else 'none (mentors type the club name)'}")
        if r.get("partner_picker"):
            print(f"   partner picker: q{r['partner_picker']} (retired 2026-09-30: delete it in the "
                  "builder)")
        if r["club_picker"]:
            print(f"   same-name clubs: {r['same_name_rosters']} rosters send '<club> - <partner>'")
        print(f"   partner box: {partner_box_line(r.get('partner_box'), r['club_picker'])}")
        print(f"   layout: {layout_line(r['layout'])}")
        if r["club_picker"]:
            g = r.get("club_guard")
            print(f"   club guard: q{g['qid']} ({g['clubs']} clubs)" if g
                  else "   club guard: none (a mentor can pick several clubs)")
        rs = r["rule_summary"]
        print(f"   question 18: {contact_ids_line(rs, r['club_picker'])}   "
              f"rosters required: {rs['required_rosters']} of {rs['clubs']}")
        print(f"   module values: {module_values_line(r.get('module_values'))}")
        print(f"   module shape: {module_shape_line(r.get('module_shape'))}")
        print(f"   names dictionary: {names_line(r.get('names_dictionary'))}")
        if "build" in r:
            print(f"   runtime build: {r['build'] or 'not found on the public page'}")
        if "rendered" in r:
            c = r["rendered"]
            print("   rendered picker: " + ("not found on the public page" if c is None else
                  f"{c['options']} options, {c['aligned']} with data-calcvalue = value, "
                  f"{c['differ']} different, {c['missing']} without"))
        if "rendered_rules" in r:
            g = r["rendered_rules"]
            print("   rendered rules: " + ("question 18 not found on the public page"
                                           if g is None or g["position"] is None else
                  f"question 18 is rule {g['position'] + 1} of {g['rules']}, the first roster rule "
                  f"{'-' if g['first_roster_rule'] is None else g['first_roster_rule'] + 1}; its operands "
                  f"list the picker: {'yes' if str(r['club_picker']) in (g['operands'] or []) else 'no'}"))
        if "rendered_required" in r:
            q = r["rendered_required"]
            print(f"   rendered rosters: {q['rosters']} with boxes, {q['required']} with validate[required] "
                  f"({q['boxes_required']} of {q['boxes']} boxes)")
        if "rendered_modules" in r:
            print("   rendered modules: " + ", ".join(
                f"q{qid} " + ("not found" if c is None else
                              f"{c['options']} options, {c['aligned']} with data-calcvalue = value")
                for qid, c in r["rendered_modules"].items()))
        if "rendered_shape" in r:
            s = r["rendered_shape"]
            print(f"   rendered shape: clearFieldOnHide {s['clearFieldOnHide'] or 'not found on the public page'}, "
                  f"module selects served multiple: {', '.join('q' + q for q in s['multi_select']) or 'none'}")
        if "rendered_names" in r:
            n = r["rendered_names"]
            print("   rendered names: " + (f"not checked ({n.get('why')})" if not n.get("checked") else
                  f"the embedded dictionary alters {n['altered']} of the {n['options']} roster options served"))
        print(f"   rules: {rs['show_rules']} show-rules for {rs['clubs']} rosters, "
              f"Contact_IDs aggregate covers {rs['aggregate_rosters']}  → "
              f"{'CLEAN' if not r['rule_problems'] else str(len(r['rule_problems'])) + ' PROBLEM(S)'}")
        for p in r["rule_problems"][:10]:
            print(f"      !! {p}")
        if r["duplicate_club_questions"]:
            print(f"   DUPLICATE club questions: {r['duplicate_club_questions']}")
        rc = r.get("region_check")
        if rc:
            print(f"   vs Roster ({rc['roster_clubs']} clubs in region): "
                  f"{len(rc['missing_from_form'])} missing from form, "
                  f"{len(rc['not_in_roster'])} on form but not in roster, "
                  f"{len(rc['rosters_out_of_date'])} rosters differ")
            for name in rc["missing_from_form"][:8]:
                print(f"      missing: {name}")
            if len(rc["missing_from_form"]) > 8:
                print(f"      ... and {len(rc['missing_from_form']) - 8} more")
            for name in rc["not_in_roster"][:8]:
                print(f"      extra:   {name}")
            for name, plus, minus in rc["rosters_out_of_date"][:8]:
                print(f"      differs: {name} (+{plus} girls in roster, -{minus} only on form)")
        print()


if __name__ == "__main__":
    run(main)
