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
import json
import os
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict

API_BASE = "https://api.jotform.com"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FORMS = {
    "262352490535154": ("template", None),
    "262382821971058": ("Africa", "Africa"),
    "262383129464057": ("Asia", "Asia"),
    "262383455778067": ("Latin America", "Latin America"),
    "262382706852058": ("U.S", "U.S"),
}
DEFUNCT = {
    "260555608160556": ("master (defunct)", None),
    "260703905772560": ("Africa (defunct)", "Africa"),
    "260704198384564": ("Asia (defunct)", "Asia"),
    "260704170003542": ("Latin America (defunct)", "Latin America"),
    "260703912140547": ("U.S (defunct)", "U.S"),
}
ENABLE_FUZZY_QID = "109"


def get(path, api_key, label):
    out = subprocess.run(["curl", "-sS", f"{API_BASE}{path}?apiKey={api_key}&limit=1000"],
                         capture_output=True, text=True)
    try:
        resp = json.loads(out.stdout)
    except json.JSONDecodeError:
        sys.exit(f"{label}: non-JSON response: {out.stdout[:200]}")
    if resp.get("responseCode") != 200:
        sys.exit(f"{label}: {resp.get('responseCode')} {resp.get('message')}")
    return resp["content"]


def key(s):
    return " ".join(str(s or "").split()).lower()


def name_key(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split()).lower()


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


def audit_rules(questions, conditions):
    """Rule-level checks on a form's live conditions. Returns a list of
    problem strings (empty = clean) and a summary dict."""
    problems = []
    qids = set(questions)
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
    # every club roster has exactly one show-rule whose clubName term equals its text
    by_name = defaultdict(list)
    for qid, name in clubs.items():
        by_name[name.lower()].append(qid)
    for qid, name in clubs.items():
        rules = shown_by.get(qid, [])
        if len(rules) != 1:
            problems.append(f"'{name}' (q{qid}) has {len(rules)} show-rules, expected 1")
            continue
        _, terms = rules[0]
        club_terms = [t for t in terms if str(t.get("field")) == CLUB_NAME_QID]
        if not club_terms or " ".join(str(club_terms[0].get("value")).split()).lower() != name.lower():
            problems.append(f"'{name}' (q{qid}): show-rule does not test clubName == its text")
        has_partner = any(str(t.get("field")) == PARTNER_QID for t in terms)
        if len(by_name[name.lower()]) > 1 and not has_partner:
            problems.append(f"'{name}' (q{qid}) shares its name but its rule has no Partner term")
        if len(by_name[name.lower()]) == 1 and has_partner:
            problems.append(f"'{name}' (q{qid}) is unique but its rule needs a Partner")
    if aggregate_operands is None:
        problems.append("no Contact_IDs aggregate calculation found")
    else:
        missing = set(clubs) - aggregate_operands
        extra = aggregate_operands - set(clubs)
        if missing:
            problems.append(f"Contact_IDs aggregate misses {len(missing)} roster(s): {sorted(missing, key=int)[:5]}")
        if extra:
            problems.append(f"Contact_IDs aggregate includes {len(extra)} non-roster question(s): {sorted(extra)[:5]}")
    summary = {"clubs": len(clubs), "show_rules": sum(len(v) for v in shown_by.values()),
               "aggregate_rosters": len(aggregate_operands or [])}
    return problems, summary


def form_report(form_id, api_key, roster_by_region):
    label, region = FORMS.get(form_id) or DEFUNCT.get(form_id) or (form_id, None)
    props = get(f"/form/{form_id}/properties", api_key, f"{form_id} properties")
    questions = get(f"/form/{form_id}/questions", api_key, f"{form_id} questions")
    info = get(f"/form/{form_id}", api_key, f"{form_id} info")

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
    rep = {
        "rule_problems": rule_problems, "rule_summary": rule_summary,
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
                on_form = clubs[k][0][1]
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
    args = ap.parse_args()
    if args.defunct:
        FORMS.update(DEFUNCT)
    api_key = os.environ.get("JOTFORM_API_KEY") or sys.exit("Set JOTFORM_API_KEY")
    roster = load_roster(args.roster)

    reports = [form_report(f, api_key, roster) for f in (args.form or FORMS)]
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
    main()
