#!/usr/bin/env python3
"""
Put the links above the Submit button of the Jotform attendance forms - the
problem-report link and the Club Roster Form link - and take them out again.

Each link is ONE text element (no logic, no integration change), found by its
unique name; the table (names, sentences, public URLs, what sits above what)
is glow/links.py:

  --link problem  "Click here to report a problem"              (default)
                  -> the problem-report Google Form, directly above Submit
  --link roster   "A girl missing, or no longer in your club? Tell us on the
                  Club Roster Form."
                  -> the Club Roster Form, directly above the problem link

Dry run by default. With --apply each form is snapshotted first
(backup_forms.py -> backups/<id>/), written, then re-read and checked: the
element exactly once, its text as written, not hidden, above what it must be
above, and no rule mentioning it (the sync rewrites rules, never this
element). Re-running is a no-op; --remove deletes the element. Refuses an
edit URL, a URL the other link already uses, and any layout other than
link elements + Submit where the element goes. Translations are the second
step: tools/add_translations.py --apply (it needs the element to exist).

Usage:
    export JOTFORM_API_KEY=...
    python3 tools/add_feedback_link.py --link roster                    # preview, all five forms
    python3 tools/add_feedback_link.py --link roster --apply
    python3 tools/add_feedback_link.py --link roster --remove --apply   # take it out
    python3 tools/add_feedback_link.py --link roster --form 262352490535154   # one form only
    python3 tools/add_feedback_link.py --url https://forms.gle/xxxx     # another public link
"""
import argparse
import os
import sys
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from backup_forms import snapshot      # noqa: E402
from glow import forms as glow_forms   # noqa: E402
from glow import links as glow_links   # noqa: E402
from glow.cli import run               # noqa: E402
from glow.jotform import Client        # noqa: E402

# the live regional forms + the template they came from
FORMS = {**{fid: region for region, fid in glow_forms.REGIONALS.items()},
         glow_forms.TEMPLATE: "template"}


def _label(q):
    return f"{q.get('name') or q.get('type')} (q{q['qid']})"


def plan_form(questions, conditions, link, url, remove=False):
    """(steps, notes) for one form. A step is {op, qid, fields, label} with op
    add / move / update / delete and `fields` in plain Jotform keys; notes are
    lines to print. Pure: no API calls, so the tests drive it directly."""
    ours = glow_links.named(questions, link.name)
    if len(ours) > 1:
        sys.exit(f"{len(ours)} elements are named {link.name!r} - delete the "
                 "extra one in the builder first")
    if remove:
        if not ours:
            return [], ["no such element - nothing to remove"]
        q = ours[0]
        return [{"op": "delete", "qid": q["qid"], "fields": {},
                 "label": f"DELETE {_label(q)}"}], []

    for other, other_link in glow_links.elements_on(questions):
        if other_link is not link and glow_links.href_of(other.get("text")) == url:
            sys.exit(f"{_label(other)} already links to {url} - the two links "
                     "would open the same form; check --link / --url")

    body = glow_links.element_html(link.sentence, url)
    notes = []
    if ours:
        q = ours[0]
        drift = {}
        if q.get("text") != body:
            drift["text"] = body
        if q.get("hidden") == "Yes":
            drift["hidden"] = "No"
        for rid in glow_links.rules_mentioning(conditions, q["qid"]):
            notes.append(f"! rule {rid} mentions {_label(q)} - hand-made; the next "
                         "sync rewrite drops it")
        below = [o for o in glow_links.must_sit_above(questions, link) if o is not q]
        if any(glow_links.render_key(q) >= glow_links.render_key(o) for o in below):
            notes.append(f"! {_label(q)} sits at order {glow_links.order_of(q)}, not above "
                         + ", ".join(_label(o) for o in below) + " - move it in the builder")
        if not drift:
            return [], notes + [f"{_label(q)} already present and up to date"]
        return [{"op": "update", "qid": q["qid"], "fields": drift,
                 "label": f"UPDATE {_label(q)}: {', '.join(sorted(drift))}"}], notes

    order, moves = glow_links.plan_insert(questions, link, conditions)
    steps = []
    for qid, new_order in moves:
        q = questions[qid]
        steps.append({"op": "move", "qid": qid, "fields": {"order": str(new_order)},
                      "label": f"move {_label(q)} {glow_links.order_of(q)} -> {new_order}"})
    above = glow_links.named(questions, link.above)
    where = _label(above[0]) if above else "Submit"
    steps.append({"op": "add", "qid": None,
                  "fields": {"type": "control_text", "name": link.name,
                             "text": body, "order": str(order)},
                  "label": f"ADD {link.name} at order {order}, directly above {where}"})
    return steps, notes


def verify(questions, conditions, link, url, removed=False):
    """What is wrong on a re-read form ([] when the write landed as intended)."""
    ours = glow_links.named(questions, link.name)
    if removed:
        return [f"{len(ours)} element(s) named {link.name!r} still present"] if ours else []
    if len(ours) != 1:
        return [f"{len(ours)} elements named {link.name!r}, expected 1"]
    q, problems = ours[0], []
    if q.get("text") != glow_links.element_html(link.sentence, url):
        problems.append("its text differs from what was written")
    if q.get("hidden") == "Yes":
        problems.append("it is hidden")
    for o in glow_links.must_sit_above(questions, link):
        if o is not q and glow_links.render_key(q) >= glow_links.render_key(o):
            problems.append(f"it is not above {_label(o)}")
    rules = glow_links.rules_mentioning(conditions, q["qid"])
    if rules:
        problems.append(f"rule(s) {', '.join(rules)} mention it")
    return problems


def write(client, form_id, step):
    if step["op"] == "delete":
        return client.delete(f"/form/{form_id}/question/{step['qid']}",
                             f"{form_id} {step['label']}")
    data = {f"question[{k}]": v for k, v in step["fields"].items()}
    path = f"/form/{form_id}/questions" if step["op"] == "add" \
        else f"/form/{form_id}/question/{step['qid']}"
    return client.post_form(path, data, f"{form_id} {step['label']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--link", choices=sorted(glow_links.LINKS), default="problem",
                    help="which link (default: problem)")
    ap.add_argument("--url", help="the Google Form's public link (default: the one "
                                  "in glow/links.py)")
    ap.add_argument("--form", action="append", help="limit to these form IDs")
    ap.add_argument("--remove", action="store_true", help="delete the element")
    ap.add_argument("--apply", action="store_true", help="write (dry run without it)")
    args = ap.parse_args()
    link = glow_links.LINKS[args.link]
    url = glow_links.check_public_url(args.url or link.url)
    api_key = os.environ.get("JOTFORM_API_KEY") or sys.exit("Set JOTFORM_API_KEY")
    client = Client(api_key, apply=args.apply)
    targets = {f: FORMS.get(f, "?") for f in args.form} if args.form else FORMS
    stamp = datetime.now().strftime("%Y-%m-%dT%H%M")

    print(("APPLYING" if args.apply else "DRY RUN")
          + f" - {'remove ' if args.remove else ''}{link.name}: {link.sentence!r}"
          + ("" if args.remove else f"\n  -> {url}") + "\n")
    def read_and_plan(form_id):
        questions = client.get(f"/form/{form_id}/questions")
        conditions = client.get(f"/form/{form_id}/properties").get("conditions", [])
        return plan_form(questions, conditions, link, url, args.remove)

    # every form is planned before anything is written: a refusal on the
    # fifth form must not leave the first four changed
    planned = {}
    for form_id, label in targets.items():
        print(f"== {label} {form_id}")
        steps, notes = read_and_plan(form_id)
        planned[form_id] = steps
        for line in notes:
            print(f"   {line}")
        for n, step in enumerate(steps, 1):
            print(f"   {n}. {step['label']}")

    failed = 0
    for form_id, steps in planned.items():
        if not args.apply or not steps:
            continue
        print(f"\n== writing {targets[form_id]} {form_id}")
        snapshot(form_id, client, stamp)       # the rollback path, before any write
        print(f"   snapshot: backups/{form_id}/questions-{stamp}.json")
        steps, _ = read_and_plan(form_id)      # the form may have changed since the preview
        if [s["label"] for s in steps] != [s["label"] for s in planned[form_id]]:
            failed += 1
            print("   ! the form changed since the preview - nothing written; re-run")
            continue
        for step in steps:
            created = write(client, form_id, step)
            if step["op"] == "add" and isinstance(created, dict):
                print(f"   added qid {created.get('qid')}")
        after = client.get(f"/form/{form_id}/questions")
        conditions = client.get(f"/form/{form_id}/properties").get("conditions", [])
        problems = verify(after, conditions, link, url, args.remove)
        if problems:
            failed += 1
            print("   ! MISMATCH after write: " + "; ".join(problems))
        else:
            print("   re-read: verified")

    if not args.apply:
        print("\nDRY RUN - re-run with --apply to write; then tools/add_translations.py")
    if failed:
        sys.exit(f"{failed} form(s) did not verify - re-read before retrying "
                 "(a gateway 504 can hide a completed write)")


if __name__ == "__main__":
    run(main)
