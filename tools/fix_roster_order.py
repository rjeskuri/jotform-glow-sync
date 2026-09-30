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
above the links and Submit, the rules unchanged). Anything unexpected -
an API error on any read or write included - stops the run: later forms
stay untouched. Re-running is safe: it re-plans from what the form holds, a
form an earlier run left part-way says so, and a finished form says
"nothing to do".

The rollback is --form <id> --undo <stamp> (the stamp printed with the
snapshot, and again when the run stops): the orders of the snapshot taken
before this run's writes go back, by the same path - dry run first, planned
before written, probed, verified. After a stop and a re-run, the stopped
run's stamp is the form before the repair; the re-run's is the part-way
form. It refuses once the form's questions or a roster's order have changed
since, or when the snapshot holds two questions at one order (then the
builder, or Jotform's Revision History).

Usage:
    export JOTFORM_API_KEY=...
    python3 tools/fix_roster_order.py                                  # dry run: template + 4 regionals
    python3 tools/fix_roster_order.py --form 262352490535154 --apply   # the template first
    python3 tools/fix_roster_order.py --apply                          # then the rest
    python3 tools/fix_roster_order.py --form <id> --undo <stamp>       # rollback preview (--apply writes)
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
from glow.links import order_of, render_key        # noqa: E402
from sync_attendance_form import same_conditions   # noqa: E402

# the template first: it is repaired (and looked at) before any live form
FORMS = {glow_forms.TEMPLATE: "template",
         **{fid: region for region, fid in glow_forms.REGIONALS.items()}}


def _steps(questions, moves):
    return [{"qid": qid, "order": order,
             "label": f"move {layout.label(questions[qid])} {order_of(questions[qid])} -> {order}"}
            for qid, order in moves]


def plan_form(questions, conditions):
    """(steps, notes) for one form; a step is {qid, order, label}. Pure."""
    moves = layout.plan_tail_moves(questions, conditions)
    at = layout.fence(questions)
    if not moves:
        return [], [f"nothing to do - every roster renders above {layout.label(at)}"]
    rosters = [q for q in questions.values() if layout.is_roster(q)]
    below = layout.rosters_below(questions, at)
    notes = [f"{len(below)} of {len(rosters)} rosters render below {layout.label(at)}; "
             f"{len(moves)} element(s) move to orders {min(o for _, o in moves)}-"
             f"{max(o for _, o in moves)}"]
    # unrepaired, the last element is the newest roster; the first write of a
    # repair lands after it - so this is what a stopped run leaves
    last = max(rosters, key=render_key)
    ahead = [q for q in questions.values()
             if not layout.is_roster(q) and render_key(q) > render_key(last)]
    if ahead:
        notes.append(f"part-way: {len(ahead)} element(s) already render after the last roster "
                     "- an earlier --apply stopped here (or a hand edit); the rollback to the "
                     "form before the repair is the --undo stamp that run printed, not the "
                     "snapshot this run takes")
    return _steps(questions, moves), notes


def plan_undo(questions, saved):
    """(steps, notes): the orders of the snapshot `saved` put back. Pure."""
    moves = layout.plan_restore(questions, saved)
    if not moves:
        return [], ["nothing to do - every order is the snapshot's"]
    return _steps(questions, moves), [f"{len(moves)} element(s) go back to the snapshot's orders"]


def load_snapshot(form_id, stamp):
    """The questions backups/<id>/questions-<stamp>.json holds (read, never printed)."""
    path = os.path.join(REPO, "backups", form_id, f"questions-{stamp}.json")
    if not os.path.exists(path):
        sys.exit(f"no snapshot backups/{form_id}/questions-{stamp}.json - --undo takes the stamp "
                 "this tool printed when it wrote the form")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fingerprint(q):
    """Everything about a question but its order, hashed - compared, never
    printed (a roster's options are girls' names)."""
    rest = {k: v for k, v in q.items() if k != "order"}
    return hashlib.sha1(json.dumps(rest, sort_keys=True).encode("utf-8")).hexdigest()


def moved_others(before, after, done):
    """The qids not written by `done` ([(qid, order)]) whose order changed."""
    sent = dict(done)
    return sorted((qid for qid in before if qid not in sent and qid in after
                   and order_of(after[qid]) != order_of(before[qid])), key=int)


def check_orders(before, after, done):
    """Problems with the orders on a re-read form: an element moved by `done`
    ([(qid, order)]) holding another order than sent, or any other question's
    order changed. qids and orders only."""
    problems = []
    wrong = [f"q{qid} holds {order_of(after[qid])}, sent {o}" for qid, o in done
             if qid in after and order_of(after[qid]) != o]
    if wrong:
        problems.append("moved element(s) hold another order than sent: " + "; ".join(wrong))
    moved = moved_others(before, after, done)
    if moved:
        problems.append(f"{len(moved)} other question(s) changed order, e.g. "
                        + "; ".join(f"q{q} {order_of(before[q])} -> {order_of(after[q])}"
                                    for q in moved[:5]))
    return problems


def probe_stop(before, now, done):
    """The stop message when the probe after the first write finds the orders
    not as planned: what it found, what the re-read shows of the rosters and
    Submit (measured, not assumed), and the way back that works in that case.
    qids, orders and counts only."""
    found = layout.buttons(now)
    if len(found) == 1:
        n = len(layout.rosters_below(now, found[0]))
        seen = (f"the re-read shows {n} roster(s) below Submit" if n
                else "the re-read shows every roster above Submit")
    else:
        seen = f"the re-read shows {len(found)} Submit buttons"
    msg = ("after the first write: " + "; ".join(check_orders(before, now, done))
           + " - Jotform does not keep an order update as sent")
    others = moved_others(before, now, done)
    if not others:
        return (msg + "; nothing more was written to it and no other order changed, so --undo "
                "(below) puts that element back; " + seen + ". Record this in the jotform-api skill")
    rosters = [q for q in others if layout.is_roster(now[q])]
    back = (f"--undo (below) refuses: a roster's order changed too (q{rosters[0]}) - go back in "
            "the builder, or with Jotform's Revision History" if rosters else
            "the --undo dry run (below) plans the way back or refuses (then the builder, or "
            "Jotform's Revision History)")
    return (msg + ", or another writer changed the form; nothing more was written to it; "
            + seen + ". Other orders changed too: open the form; " + back
            + "; rule out another writer before recording this in the jotform-api skill")


def verify(before, after, rules_before, rules_after, done, restored=None):
    """What is wrong on the re-read form ([] when the moves landed as planned).
    After a repair every roster must render above the fence; after an undo
    (`restored` = the snapshot's questions) every order must be the snapshot's."""
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
    if restored is None:
        problems += layout.audit_layout(after)
    else:
        back = [q for q in restored if q in after and order_of(after[q]) != order_of(restored[q])]
        if back:
            problems.append(f"{len(back)} question(s) do not hold the snapshot's order")
    if not same_conditions(rules_before, rules_after):
        problems.append("the rules changed")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    ap.add_argument("--form", action="append",
                    help="limit to these form IDs (default: the template, then the four regionals)")
    ap.add_argument("--apply", action="store_true", help="write (dry run without it)")
    ap.add_argument("--undo", metavar="STAMP",
                    help="the rollback: put back the orders of backups/<id>/questions-STAMP.json, "
                         "the snapshot this tool took before writing (needs --form)")
    args = ap.parse_args()
    if args.undo and not args.form:
        sys.exit("--undo needs --form (each form whose orders go back)")
    api_key = os.environ.get("JOTFORM_API_KEY") or sys.exit("Set JOTFORM_API_KEY")
    client = Client(api_key, apply=args.apply)
    targets = {f: FORMS.get(f, "?") for f in args.form} if args.form else FORMS
    saved = {f: load_snapshot(f, args.undo) for f in targets} if args.undo else {}
    # to the second: a re-run just after a stopped one must not snapshot the
    # half-moved form over the true "before" (the rollback path)
    stamp = datetime.now().strftime("%Y-%m-%dT%H%M%S")

    def read(form_id):
        questions = client.get(f"/form/{form_id}/questions")
        conditions = client.get(f"/form/{form_id}/properties").get("conditions", [])
        return questions, conditions

    def plan(form_id, questions, conditions):
        if args.undo:
            return plan_undo(questions, saved[form_id])
        return plan_form(questions, conditions)

    print(("APPLYING" if args.apply else "DRY RUN") + " - "
          + (f"the orders of the {args.undo} snapshot go back" if args.undo else
             "the links, Submit and the hidden fields below them move after the last roster")
          + "\n")
    # every form is planned before anything is written: a refusal on the
    # fifth form must not leave the first four changed
    planned = {}
    for form_id, label in targets.items():
        print(f"== {label} {form_id}")
        steps, notes = plan(form_id, *read(form_id))
        planned[form_id] = steps
        for line in notes:
            print(f"   {line}")
        for n, step in enumerate(steps, 1):
            print(f"   {n}. {step['label']}")
    if not args.apply:
        print("\nDRY RUN - re-run with --apply to write"
              + ("" if args.undo else f" (the template first: --form {glow_forms.TEMPLATE} --apply)"))
        return

    written = []

    def stop(form_id, msg, wrote=False):
        done = f"; written before it: {', '.join(written)}" if written else ""
        # this run's stamp: after an earlier stop, that run's stamp is the form
        # before the repair (the part-way note in the plan says so)
        back = (f"\n   the rollback to this form as this run found it: --form {form_id} "
                f"--undo {stamp} (dry run first)" if wrote else "")
        sys.exit(f"   ! {targets[form_id]} {form_id}: {msg}\nstopped - the forms after it are "
                 f"untouched{done}. Re-run the dry run before anything else.{back}")

    for form_id, steps in planned.items():
        if not steps:
            continue
        print(f"\n== writing {targets[form_id]} {form_id}")
        sent, done = [], []      # POSTs sent / confirmed ([(qid, order)])
        # an API error on any read or write stops the run here: a 504 on the
        # probe or the verify re-read must not skip the verify unannounced
        try:
            snapshot(form_id, client, stamp)              # the rollback path, before any write
            print(f"   snapshot: backups/{form_id}/questions-{stamp}.json (the rollback to the "
                  f"form as this run found it: --form {form_id} --undo {stamp})")
            before, rules_before = read(form_id)          # the form may have changed since the preview
            again, _ = plan(form_id, before, rules_before)
            if [s["label"] for s in again] != [s["label"] for s in steps]:
                stop(form_id, "the form changed since the preview - nothing written to it")
            for step in steps:
                sent.append(step["qid"])
                client.post_form(f"/form/{form_id}/question/{step['qid']}",
                                 {"question[order]": str(step["order"])},
                                 f"{form_id} {step['label']}")
                done.append((step["qid"], step["order"]))
                if len(done) == 1:
                    # the plan assumes a stored order is kept as sent and nothing else
                    # moves; one re-read proves it before the second write
                    now = client.get(f"/form/{form_id}/questions")
                    if check_orders(before, now, done):
                        stop(form_id, probe_stop(before, now, done), wrote=True)
                    print(f"   probe: q{step['qid']} holds order {step['order']} as sent; "
                          "no other order changed")
            after, rules_after = read(form_id)
        except JotformError as err:
            if not sent:
                stop(form_id, f"{err} - nothing was written to it")
            stop(form_id, f"{err} - {len(done)} of {len(steps)} moves were confirmed"
                 + (" (a gateway 504 can hide a completed write)" if len(done) < len(sent) else "")
                 + "; the re-read that verifies the form did not run - after the dry run, "
                 f"python3 tools/form_status.py --form {form_id} --roster data/roster_<date>.csv",
                 wrote=True)
        problems = verify(before, after, rules_before, rules_after, done, saved.get(form_id))
        if problems:
            stop(form_id, "MISMATCH after the writes: " + "; ".join(problems), wrote=True)
        written.append(targets[form_id])
        if args.undo:
            print(f"   re-read: verified - the {args.undo} orders are back, nothing else changed")
        else:
            print(f"   re-read: verified - every roster above {layout.label(layout.fence(after))}, "
                  f"{len(done)} orders as sent, nothing else changed")
    if written and not args.undo:
        print(f"\nrepaired: {', '.join(written)}. Next: python3 tools/form_status.py --roster "
              "data/roster_<date>.csv (layout lines), and open the page: a newer club's roster "
              "above Submit")


if __name__ == "__main__":
    run(main)
