#!/usr/bin/env python3
"""
Put the optional session-notes field on the Jotform attendance forms - one
textarea, "Additional information about this session (optional)", 1,000
characters, no rule - after the last roster and above the links and Submit,
and take it out again (ticket #104; task #105 runs it on the live forms).

The field's definition is glow/layout.py (NOTES_NAME, NOTES_PROPS); it is found
by its unique name, never by qid. Dry run by default. The plan per form:

  present (qN) - as wanted        nothing to do
  UPDATE <property>: old -> new   a flag or text drifted: set back in place
  move <name> (qN) a -> b         no empty order between the last roster and
                                  the first link: the first link through
                                  Submit and the hidden fields right after
                                  move one down, bottom-up (Ryan, 2026-10-23)
  ADD sessionNotes at order N     one create at an empty order

With --apply each form is snapshotted first (glow/backup.py -> backups/<id>/),
written, then re-read and checked: the field exactly once, its properties as
NOTES_PROPS, every move landed, the field after the rosters and above the links
and Submit, and no rule mentioning it (the sync rewrites rules, never this
field). Re-running is a no-op; --remove deletes the field: the rollback.
Refuses rather than guesses: two fields of the name, the field misplaced, a
roster below the fence, a hidden link or Submit, or anything a mentor can see
between the last roster and Submit besides the links and Submit.

Usage:
    export JOTFORM_API_KEY=...
    python3 tools/add_session_notes.py                       # preview, template + 4 regionals
    python3 tools/add_session_notes.py --form 262352490535154 --apply   # the template first
    python3 tools/add_session_notes.py --apply
    python3 tools/add_session_notes.py --remove --apply      # take it out again
"""
import argparse
import os
import sys
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow import backup               # noqa: E402  (the snapshot before a write)
from glow import layout               # noqa: E402
from glow import links as glow_links   # noqa: E402
from glow.cli import api_key, run, targets               # noqa: E402
from glow.jotform import Client        # noqa: E402

NAME, PROPS = layout.NOTES_NAME, layout.NOTES_PROPS
_label = layout.label


def _have(q, prop):
    """What the form holds for `prop`, as the API reports a property a create
    never set: hidden "No", a sub-label ""."""
    value = q.get(prop)
    if value is None and prop in ("hidden", "subLabel"):
        return PROPS[prop]
    return value


def drift(q):
    """{property: wanted} for every NOTES_PROPS property the field has not got."""
    return {k: v for k, v in PROPS.items() if _have(q, k) != v}


def plan_form(questions, conditions, remove=False):
    """(steps, notes) for one form. A step is {op, qid, fields, label} with op
    add / move / update / delete and `fields` in plain Jotform keys; notes are
    lines to print. Pure: no API calls, so the tests drive it directly."""
    ours = layout.notes_fields(questions)
    if len(ours) > 1:
        sys.exit(f"{len(ours)} fields are named {NAME!r} ({', '.join('q' + q['qid'] for q in ours)}) - "
                 "delete the extra one in the builder first")
    if remove:
        if not ours:
            return [], ["no such field - nothing to remove"]
        q = ours[0]
        return [{"op": "delete", "qid": q["qid"], "fields": {}, "label": f"DELETE {_label(q)}"}], []

    wrong = layout.misplaced(questions)
    if wrong:
        sys.exit("the form's layout is not as expected - fix it first: " + "; ".join(wrong))
    notes = []
    if ours:
        q = ours[0]
        if q.get("type") != PROPS["type"]:
            sys.exit(f"{_label(q)} is a {q.get('type')}, not a {PROPS['type']} - "
                     "delete it in the builder first (the tool never changes a question's type)")
        for rid in glow_links.rules_mentioning(conditions, q["qid"]):
            notes.append(f"! rule {rid} mentions {_label(q)} - hand-made; the next sync rewrite drops it")
        changes = drift(q)
        if not changes:
            return [], notes + [f"present (q{q['qid']}) - as wanted"]
        return [{"op": "update", "qid": q["qid"], "fields": changes,      # one write, every property
                 "label": "; ".join(f"UPDATE {k}: {_have(q, k)!r} -> {v!r}" for k, v in changes.items())}], notes

    order, moves = layout.notes_slot(questions, conditions)
    last, first = layout.notes_neighbours(questions)
    steps = [{"op": "move", "qid": qid, "fields": {"order": str(new_order)},
              "label": f"move {_label(questions[qid])} {glow_links.order_of(questions[qid])} -> {new_order}"}
             for qid, new_order in moves]
    steps.append({"op": "add", "qid": None, "fields": {"name": NAME, "order": str(order), **PROPS},
                  "label": f"ADD {NAME} at order {order} (after q{last['qid']}, above q{first['qid']})"})
    return steps, notes


def verify(questions, conditions, steps, removed=False):
    """What is wrong on a re-read form ([] when the writes landed as intended)."""
    ours = layout.notes_fields(questions)
    if removed:
        return [f"{len(ours)} field(s) named {NAME!r} still present"] if ours else []
    if len(ours) != 1:
        return [f"{len(ours)} fields named {NAME!r}, expected 1"]
    q, problems = ours[0], []
    problems += [f"{k} is {_have(q, k)!r}, not {v!r}" for k, v in drift(q).items()]
    for step in steps:
        moved = questions.get(step["qid"]) if step["op"] == "move" else q if step["op"] == "add" else None
        if moved is not None and glow_links.order_of(moved) != int(step["fields"]["order"]):
            problems.append(f"{_label(moved)} is at order {glow_links.order_of(moved)}, "
                            f"not {step['fields']['order']} as written")
        elif step["op"] == "move" and moved is None:
            problems.append(f"q{step['qid']} is gone")
    problems += layout.misplaced(questions)
    rules = glow_links.rules_mentioning(conditions, q["qid"])
    if rules:
        problems.append(f"rule(s) {', '.join(rules)} mention it")
    return problems


def write(client, form_id, step):
    if step["op"] == "delete":
        return client.delete(f"/form/{form_id}/question/{step['qid']}", f"{form_id} {step['label']}")
    data = {f"question[{k}]": v for k, v in step["fields"].items()}
    path = f"/form/{form_id}/questions" if step["op"] == "add" \
        else f"/form/{form_id}/question/{step['qid']}"
    return client.post_form(path, data, f"{form_id} {step['label']}")


def main(argv=None, client=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--form", action="append", help="limit to these form IDs")
    ap.add_argument("--remove", action="store_true", help="delete the field (the rollback)")
    ap.add_argument("--apply", action="store_true", help="write (dry run without it)")
    args = ap.parse_args(argv)
    if client is None:
        client = Client(api_key(), apply=args.apply)
    chosen = targets(args.form)
    # to the second: a re-run just after a failed one must not snapshot the
    # half-written form over the true "before" (the rollback path)
    stamp = backup.stamp(datetime.now())

    print(("APPLYING" if args.apply else "DRY RUN")
          + f" - {'remove ' if args.remove else ''}{NAME}: {PROPS['text']!r}\n")

    def read_and_plan(form_id):
        questions = client.get(f"/form/{form_id}/questions")
        conditions = client.get(f"/form/{form_id}/properties").get("conditions", [])
        return plan_form(questions, conditions, args.remove)

    # every form is planned before anything is written: a refusal on the
    # fifth form must not leave the first four changed
    planned = {}
    for form_id, label in chosen.items():
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
        print(f"\n== writing {chosen[form_id]} {form_id}")
        backup.snapshot(form_id, client, stamp)    # the rollback path, before any write
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
        problems = verify(after, conditions, steps, args.remove)
        if problems:
            failed += 1
            print("   ! MISMATCH after write: " + "; ".join(problems))
        else:
            print("   re-read: verified")

    if not args.apply:
        print("\nDRY RUN - re-run with --apply to write")
    if failed:
        sys.exit(f"{failed} form(s) did not verify - re-read before retrying (a gateway 504 can "
                 f"hide a completed write); the \"before\" of each form written is "
                 f"backups/<id>/questions-{stamp}.json (--remove --apply takes the field out)")


if __name__ == "__main__":
    run(main)
