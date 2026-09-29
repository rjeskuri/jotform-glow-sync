#!/usr/bin/env python3
"""
Launch-readiness report for the Jotform attendance forms: is each form
carrying the clubs the Roster says it should, with clean logic and the
Salesforce integration intact?

Read-only. Compares every form's club checkboxes against the Roster tab
(data/roster_build/Roster.csv by default, or --roster <csv>), grouped by
region, and reports what the Jotform API says about conditions, emails,
integration, submissions and the enableFuzzy field.

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
from glow.cli import run                   # noqa: E402
from glow.jotform import Client            # noqa: E402
from glow.links import order_of, shown_by_rules   # noqa: E402
from glow.sync import (                    # noqa: E402  (shared with the sync tool)
    CONTACT_IDS_SEPARATOR, GUARD_DISABLES_SUBMIT, GUARD_NAME, GUARD_PROPS, PICKER_NAME,
    club_guards, has_calc_values, partner_picker, picker_calc_values)
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
    rules with the full term list, and the Contact_IDs separator. [] on a
    form without it (docs/plans/2026-09-29-club-guard.md)."""
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
    if CONTACT_IDS_SEPARATOR:
        for c, _, acts in rules:
            for x in acts:
                if str(x.get("resultField")) == CONTACT_IDS_QID:
                    gaps = re.findall(r"\}(.*?)\{", str(x.get("equation", "")))
                    if any(gap != CONTACT_IDS_SEPARATOR for gap in gaps):
                        problems.append(f"the Contact_IDs calculation joins the rosters without the "
                                        f"{CONTACT_IDS_SEPARATOR!r} the guard brings")
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


def audit_rules(questions, conditions):
    """Rule-level checks on a form's live conditions. Returns a list of
    problem strings (empty = clean) and a summary dict."""
    problems = []
    qids = set(questions)
    club_field = club_picker(questions) or CLUB_NAME_QID
    plist = partner_picker(questions)            # the partner list, once the form has one
    partner_fields = {PARTNER_QID, plist} if plist else {PARTNER_QID}
    clubs = {qid: " ".join(q["text"].split()) for qid, q in questions.items()
             if q.get("type") == "control_checkbox"}
    shown_by = defaultdict(list)     # club qid -> [rule ids that show it]
    list_shown_for = set()           # club names (lower) whose pick shows the partner list
    box_shown_by = []                # rule ids that show the typed box while the list exists
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
            if plist and a.get("visibility") == "Show" and str(a.get("field")) == plist:
                list_shown_for.update(" ".join(str(t.get("value")).split()).lower() for t in terms
                                      if str(t.get("field")) == club_field)
            if plist and a.get("visibility") == "Show" and str(a.get("field")) == PARTNER_QID:
                box_shown_by.append(c.get("id"))
            if str(a.get("resultField")) == CONTACT_IDS_QID:
                aggregate_operands = {x for x in str(a.get("operands", "")).split(",") if x}
                for op in aggregate_operands:
                    if op not in qids:
                        problems.append(f"Contact_IDs aggregate refers to missing question {op}")
    # every club roster has exactly one show-rule whose clubName term equals its text
    tested_partners = {}             # key(partner) -> partner, for every term on the list
    by_name = defaultdict(list)
    for qid, name in clubs.items():
        by_name[name.lower()].append(qid)
    for qid, name in clubs.items():
        rules = shown_by.get(qid, [])
        if len(rules) != 1:
            problems.append(f"'{name}' (q{qid}) has {len(rules)} show-rules, expected 1")
            continue
        _, terms = rules[0]
        club_terms = [t for t in terms if str(t.get("field")) == club_field]
        if not club_terms or " ".join(str(club_terms[0].get("value")).split()).lower() != name.lower():
            problems.append(f"'{name}' (q{qid}): show-rule does not test the club field "
                            f"(q{club_field}) == its text")
        partner_terms = [t for t in terms if str(t.get("field")) in partner_fields]
        has_partner = bool(partner_terms)
        if len(by_name[name.lower()]) > 1 and not has_partner:
            problems.append(f"'{name}' (q{qid}) shares its name but its rule has no Partner term")
        if len(by_name[name.lower()]) == 1 and has_partner:
            problems.append(f"'{name}' (q{qid}) is unique but its rule needs a Partner")
        for t in partner_terms:
            if plist and str(t.get("field")) != plist:
                problems.append(f"'{name}' (q{qid}): rule tests the typed Partner box "
                                f"(q{PARTNER_QID}), not the partner list (q{plist})")
            elif plist:
                tested_partners.setdefault(key(t.get("value")), str(t.get("value")))
    if plist:
        q = questions[plist]
        listed = {key(o): o for o in (q.get("options") or "").split("|") if o.strip()}
        missing = sorted(v for k, v in tested_partners.items() if k not in listed)
        if missing:
            problems.append(f"partner list (q{plist}) misses {len(missing)} partner(s) a rule "
                            f"tests: {missing[:5]}")
        extra = sorted(o for k, o in listed.items() if k not in tested_partners)
        if tested_partners and extra:
            problems.append(f"partner list (q{plist}) offers {len(extra)} partner(s) no rule "
                            f"tests: {extra[:5]}")
        if q.get("required") != "Yes":
            problems.append(f"partner list (q{plist}) is not required")
        if q.get("hidden") != "Yes":
            problems.append(f"partner list (q{plist}) is not hidden: every mentor is asked for "
                            "a partner")
        # a shared name must show the list (else its rosters never appear), and only a
        # shared name may (else that club's mentor must pick a partner to submit)
        shared = {low: clubs[qs[0]] for low, qs in by_name.items() if len(qs) > 1}
        for low, name in sorted(shared.items()):
            if low not in list_shown_for:
                problems.append(f"'{name}' is shared, but no rule shows the partner list "
                                f"(q{plist}) for it")
        for low in sorted(list_shown_for - set(shared)):
            name = next((clubs[qs[0]] for n, qs in by_name.items() if n == low), low)
            problems.append(f"the partner list (q{plist}) is shown for '{name}', which no two "
                            "rosters share")
        if box_shown_by:
            problems.append(f"{len(box_shown_by)} rule(s) show the typed Partner box "
                            f"(q{PARTNER_QID}), which the partner list replaces: {box_shown_by[:5]}")
        if questions.get(PARTNER_QID, {}).get("hidden") != "Yes":
            problems.append(f"partner list present but the typed Partner box (q{PARTNER_QID}) "
                            "is still visible")
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
               "aggregate_rosters": len(aggregate_operands or [])}
    return problems, summary


def form_report(form_id, client, roster_by_region):
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

    rule_problems, rule_summary = audit_rules(questions, conditions)
    picker = club_picker(questions)
    if picker:
        listed = {key(o) for o in (questions[picker].get("options") or "").split("|") if o.strip()}
        missing = [v[0][0] for k, v in clubs.items() if k not in listed]
        extra = sorted(o for o in listed if o not in clubs)
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
    rep = {
        "rule_problems": rule_problems, "rule_summary": rule_summary,
        "languages": languages, "club_picker": picker, "partner_picker": partner_picker(questions),
        "club_guard": ({"qid": guards[0], "clubs": len(picker_options(questions, picker)) if picker else 0}
                       if guards else None),
        "picker_calc_values": bool(picker and has_calc_values(questions[picker])),
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

    reports = [form_report(f, client, roster) for f in (args.form or FORMS)]
    if args.rendered:
        for r in reports:
            if not r["club_picker"]:
                continue
            counts = rendered_calc_values(public_page(r["id"]), r["club_picker"])
            r["rendered"] = counts
            if counts is None:
                r["rule_problems"].append("--rendered: the public page has no Club picker select "
                                          "(page not served, or its layout changed)")
            elif r["picker_calc_values"] and (counts["differ"] or counts["missing"]
                                              or counts["aligned"] != counts["options"]):
                r["rule_problems"].append(
                    f"rendered page: {counts['differ']} of {counts['options']} picker options carry a "
                    f"data-calcvalue other than their value, {counts['missing']} none - the copy "
                    "into question 5 would send another club's name (RUNBOOK, One club per "
                    "submission: stop and restore)")
    if args.json:
        print(json.dumps(reports, indent=1))
        return

    print("Roster (active girls):", {r: len(c) for r, c in roster.items()}, "clubs per region\n")
    for r in reports:
        print(f"== {r['label']}  {r['id']}  \"{r['title']}\"  [{r['status']}]")
        print(f"   submissions {r['submissions']} (last {r['last_submission']})   "
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
            print(f"   partner picker: q{r['partner_picker']} (a shared club name: mentors choose "
                  "the partner)")
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
