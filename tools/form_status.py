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
them makes the form NOT CLEAN - tools/fix_roster_order.py repairs it).

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
from glow.cli import run                   # noqa: E402
from glow.jotform import Client            # noqa: E402
from glow.links import order_of, shown_by_rules   # noqa: E402
from glow.sync import (                    # noqa: E402  (shared with the sync tool)
    GUARD_DISABLES_SUBMIT, GUARD_NAME, GUARD_PROPS, PICKER_NAME, SF_NAME_SEP,
    club_guards, club_partners, has_calc_values, long_name_partner, partner_picker,
    picker_calc_values)
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
    aggregate_operands = None
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
            if str(a.get("resultField")) == CONTACT_IDS_QID:
                aggregate_operands = {x for x in str(a.get("operands", "")).split(",") if x}
                for op in aggregate_operands:
                    if op not in qids:
                        problems.append(f"Contact_IDs aggregate refers to missing question {op}")
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
    if aggregate_operands is None:
        problems.append("no Contact_IDs aggregate calculation found")
    else:
        missing = set(clubs) - aggregate_operands
        extra = aggregate_operands - set(clubs)
        if missing:
            problems.append(f"Contact_IDs aggregate misses {len(missing)} roster(s): {sorted(missing, key=int)[:5]}")
        if extra:
            problems.append(f"Contact_IDs aggregate includes {len(extra)} non-roster question(s): {sorted(extra)[:5]}")
    problems += audit_picker(questions, conditions) + audit_club_guard(questions, conditions)
    summary = {"clubs": len(clubs), "show_rules": sum(len(v) for v in shown_by.values()),
               "aggregate_rosters": len(aggregate_operands or []), "long_names": long_names}
    return problems, summary


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
    dup_clubs = [v[0][0] for v in clubs.values() if len(v) > 1]

    conditions = props.get("conditions") or []
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
    picker = club_picker(questions)
    if picker:
        # the picker's options are the texts the rosters' rules test (a club's own
        # name, or its long name "<club> - <partner>"), no more and no fewer; a
        # roster with no readable rule counts by its own text
        listed = {key(o): o for o in (questions[picker].get("options") or "").split("|") if o.strip()}
        tested = tested_values(questions, conditions)
        wanted = {str(qid): tested.get(str(qid), text) for v in clubs.values() for text, _, qid in v}
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
    lang = props.get("language")
    lang = lang[0] if isinstance(lang, list) and lang else (lang or {})
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
        "id": form_id, "label": label, "title": info.get("title"), "status": info.get("status"),
        "submissions": int(info.get("count") or 0), "last_submission": info.get("last_submission"),
        "questions": len(questions), "club_questions": sum(len(v) for v in clubs.values()),
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
                    help="also read each form's public page and check that every Club picker "
                         "option's data-calcvalue equals its value (counts only; the page is "
                         "never printed or saved)")
    args = ap.parse_args()
    if args.defunct:
        FORMS.update(DEFUNCT)
    api_key = os.environ.get("JOTFORM_API_KEY") or sys.exit("Set JOTFORM_API_KEY")
    client = Client(api_key)
    roster = load_roster(args.roster)
    partners_of = load_partners(args.roster) or None     # an empty Roster vouches for no partner

    reports = [form_report(f, client, roster, partners_of) for f in (args.form or FORMS)]
    if args.rendered:
        for r in reports:
            if not r["club_picker"]:
                continue
            counts = rendered_calc_values(public_page(r["id"]), r["club_picker"])
            r["rendered"] = counts
            if counts is None:
                r["rule_problems"].append("--rendered: the public page has no Club picker select "
                                          "(page not served, or its layout changed)")
                continue
            if not r["picker_calc_values"]:
                continue                     # before the rollout the counts are only printed
            if counts["differ"] or counts["missing"] or counts["aligned"] != counts["options"]:
                r["rule_problems"].append(
                    f"rendered page: {counts['differ']} of {counts['options']} picker options carry a "
                    f"data-calcvalue other than their value, {counts['missing']} none - the copy "
                    "into question 5 would send another club's name (RUNBOOK, One club per "
                    "submission: stop and restore)")
            # an option the parser could not read is one the check cannot vouch for
            if counts["options"] != r["picker_options"]:
                r["rule_problems"].append(
                    f"rendered page lists {counts['options']} of the picker's {r['picker_options']} "
                    "options - a page served from before the apply (re-run in a few minutes) or a "
                    "layout this check cannot read: do not treat it as aligned")
    if args.json:
        print(json.dumps(reports, indent=1))
        return

    print("Roster (active girls):", {r: len(c) for r, c in roster.items()}, "clubs per region\n")
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
        if "rendered" in r:
            c = r["rendered"]
            print("   rendered picker: " + ("not found on the public page" if c is None else
                  f"{c['options']} options, {c['aligned']} with data-calcvalue = value, "
                  f"{c['differ']} different, {c['missing']} without"))
        rs = r["rule_summary"]
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
