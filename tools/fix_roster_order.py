#!/usr/bin/env python3
"""
Bring every roster above the links and the Submit button of the Jotform
attendance forms - the one-time repair of BACKLOG 47
(docs/plans/2026-09-29-rosters-above-submit.md).

Until 2026-09-29 the sync created each new roster at the form's highest
order + 1, i.e. after Submit and the links above it, so a mentor of a newer
club saw her girls' names under the button. The sync now creates rosters
above them (glow/layout.py roster_slot); this tool moves what sits at and
below the first link - the links, Submit, the hidden bridge fields - to empty
orders after the last one, in the same sequence. No roster is written, no
rule, no translation (keyed by text or text_<qid>), no e-mail, no Salesforce
mapping (keyed by qid): only `order`, one POST per moved element (nine on
every form today; ten once the Club Roster Form link is on it).

Dry run by default. Every form is planned before any is written; the tool
refuses - on every form - rather than guess (two Submit buttons, a page
break, a field a mentor can see below the links, a link below Submit). With
--apply, per form: a snapshot (backup_forms.py -> backups/<id>/), a re-read
and re-plan (a form changed since the preview is not written), Submit first
(then every roster is above it), the hidden fields, the links last; after
the first write a re-read checks Jotform kept the order as sent and moved
nothing else, and after the last a re-read verifies the whole form (the same
questions, identical apart from `order`, the orders as sent, every roster
above the links and Submit, the rules unchanged). Anything unexpected stops
the run: later forms stay untouched. Re-running is safe: it re-plans from
what the form holds, and a finished form says "nothing to do".

Usage:
    export JOTFORM_API_KEY=...
    python3 tools/fix_roster_order.py                                  # dry run: template + 4 regionals
    python3 tools/fix_roster_order.py --form 262352490535154 --apply   # the template first
    python3 tools/fix_roster_order.py --apply                          # then the rest
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from backup_forms import snapshot                  # noqa: E402
from glow import forms as glow_forms               # noqa: E402
from glow import layout                            # noqa: E402
from glow.cli import run                           # noqa: E402
from glow.jotform import Client, JotformError      # noqa: E402
from glow.links import order_of                    # noqa: E402
from sync_attendance_form import same_conditions   # noqa: E402

# the template first: it is repaired (and looked at) before any live form
FORMS = {glow_forms.TEMPLATE: "template",
         **{fid: region for region, fid in glow_forms.REGIONALS.items()}}


def plan_form(questions, conditions):
    """(steps, notes) for one form; a step is {qid, order, label}. Pure."""
    moves = layout.plan_tail_moves(questions, conditions)
    at = layout.fence(questions)
    if not moves:
        return [], [f"nothing to do - every roster renders above {layout.label(at)}"]
    rosters = sum(1 for q in questions.values() if layout.is_roster(q))
    below = layout.rosters_below(questions, at)
    notes = [f"{len(below)} of {rosters} rosters render below {layout.label(at)}; "
             f"{len(moves)} element(s) move to orders {min(o for _, o in moves)}-"
             f"{max(o for _, o in moves)}"]
    steps = [{"qid": qid, "order": order,
              "label": f"move {layout.label(questions[qid])} {order_of(questions[qid])} -> {order}"}
             for qid, order in moves]
    return steps, notes


def fingerprint(q):
    """Everything about a question but its order, hashed - compared, never
    printed (a roster's options are girls' names)."""
    rest = {k: v for k, v in q.items() if k != "order"}
    return hashlib.sha1(json.dumps(rest, sort_keys=True).encode("utf-8")).hexdigest()


def check_orders(before, after, done):
    """Problems with the orders on a re-read form: an element moved by `done`
    ([(qid, order)]) holding another order than sent, or any other question's
    order changed. qids and orders only."""
    sent = dict(done)
    problems = []
    wrong = [f"q{qid} holds {order_of(after[qid])}, sent {o}" for qid, o in done
             if qid in after and order_of(after[qid]) != o]
    if wrong:
        problems.append("moved element(s) hold another order than sent: " + "; ".join(wrong))
    moved = sorted((qid for qid in before if qid not in sent and qid in after
                    and order_of(after[qid]) != order_of(before[qid])), key=int)
    if moved:
        problems.append(f"{len(moved)} other question(s) changed order, e.g. "
                        + "; ".join(f"q{q} {order_of(before[q])} -> {order_of(after[q])}"
                                    for q in moved[:5]))
    return problems


def verify(before, after, rules_before, rules_after, done):
    """What is wrong on the re-read form ([] when the moves landed as planned)."""
    problems = []
    if set(before) != set(after):
        problems.append(f"the questions differ: {len(set(before) - set(after))} gone, "
                        f"{len(set(after) - set(before))} new")
    changed = sorted((qid for qid in set(before) & set(after)
                      if fingerprint(before[qid]) != fingerprint(after[qid])), key=int)
    if changed:
        problems.append(f"{len(changed)} question(s) changed apart from their order: "
                        + ", ".join(f"q{q}" for q in changed[:10]))
    problems += check_orders(before, after, done)
    problems += layout.audit_layout(after)
    if not same_conditions(rules_before, rules_after):
        problems.append("the rules changed")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    ap.add_argument("--form", action="append",
                    help="limit to these form IDs (default: the template, then the four regionals)")
    ap.add_argument("--apply", action="store_true", help="write (dry run without it)")
    args = ap.parse_args()
    api_key = os.environ.get("JOTFORM_API_KEY") or sys.exit("Set JOTFORM_API_KEY")
    client = Client(api_key, apply=args.apply)
    targets = {f: FORMS.get(f, "?") for f in args.form} if args.form else FORMS
    # to the second: a re-run just after a stopped one must not snapshot the
    # half-moved form over the true "before" (the rollback path)
    stamp = datetime.now().strftime("%Y-%m-%dT%H%M%S")

    def read(form_id):
        questions = client.get(f"/form/{form_id}/questions")
        conditions = client.get(f"/form/{form_id}/properties").get("conditions", [])
        return questions, conditions

    print(("APPLYING" if args.apply else "DRY RUN") + " - the links, Submit and the hidden "
          "fields below them move after the last roster\n")
    # every form is planned before anything is written: a refusal on the
    # fifth form must not leave the first four changed
    planned = {}
    for form_id, label in targets.items():
        print(f"== {label} {form_id}")
        steps, notes = plan_form(*read(form_id))
        planned[form_id] = steps
        for line in notes:
            print(f"   {line}")
        for n, step in enumerate(steps, 1):
            print(f"   {n}. {step['label']}")
    if not args.apply:
        print("\nDRY RUN - re-run with --apply to write (the template first: "
              f"--form {glow_forms.TEMPLATE} --apply)")
        return

    repaired = []

    def stop(form_id, msg):
        done = f"; repaired before it: {', '.join(repaired)}" if repaired else ""
        sys.exit(f"   ! {targets[form_id]} {form_id}: {msg}\nstopped - the forms after it are "
                 f"untouched{done}. Re-run the dry run before anything else.")

    for form_id, steps in planned.items():
        if not steps:
            continue
        print(f"\n== writing {targets[form_id]} {form_id}")
        snapshot(form_id, client, stamp)                  # the rollback path, before any write
        print(f"   snapshot: backups/{form_id}/questions-{stamp}.json")
        before, rules_before = read(form_id)              # the form may have changed since the preview
        again, _ = plan_form(before, rules_before)
        if [s["label"] for s in again] != [s["label"] for s in steps]:
            stop(form_id, "the form changed since the preview - nothing written to it")
        done = []
        for step in steps:
            try:
                client.post_form(f"/form/{form_id}/question/{step['qid']}",
                                 {"question[order]": str(step["order"])},
                                 f"{form_id} {step['label']}")
            except JotformError as err:
                stop(form_id, f"{err} - {len(done)} of {len(steps)} moves were confirmed (a "
                              "gateway 504 can hide a completed write)")
            done.append((step["qid"], step["order"]))
            if len(done) == 1:
                # the plan assumes a stored order is kept as sent and nothing else
                # moves; one re-read proves it before the second write
                problems = check_orders(before, client.get(f"/form/{form_id}/questions"), done)
                if problems:
                    stop(form_id, "after the first write: " + "; ".join(problems)
                         + " - Jotform does not keep an order update as sent; the form is "
                         "safe (only that element moved); record this in the jotform-api skill")
                print(f"   probe: q{step['qid']} holds order {step['order']} as sent; "
                      "no other order changed")
        after, rules_after = read(form_id)
        problems = verify(before, after, rules_before, rules_after, done)
        if problems:
            stop(form_id, "MISMATCH after the writes: " + "; ".join(problems)
                 + f" - the snapshot backups/{form_id}/questions-{stamp}.json holds the old orders")
        repaired.append(targets[form_id])
        print(f"   re-read: verified - every roster above {layout.label(layout.fence(after))}, "
              f"{len(done)} orders as sent, nothing else changed")
    if repaired:
        print(f"\nrepaired: {', '.join(repaired)}. Next: python3 tools/form_status.py --roster "
              "data/roster_<date>.csv (layout lines), and open the page: a newer club's roster "
              "above Submit")


if __name__ == "__main__":
    run(main)
