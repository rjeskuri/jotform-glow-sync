"""Where the rosters sit relative to the links and the Submit button
(BACKLOG 47, docs/plans/2026-09-29-rosters-above-submit.md).

Every attendance form ends in the same way: the rosters (hidden checkboxes a
rule shows for the picked club), then the link elements (glow/links.py) and
the Submit button, then hidden bridge fields. A mentor sees her girls' names
where her roster renders, so a roster rendering after Submit shows them under
the button. Jotform renders by `order`, equal orders by creation (qid) -
links.render_key.

- fence(): the first of the links and Submit - what every roster must render
  above;
- roster_slot(): the order the sync gives a new roster so that it renders
  above the fence, whether Jotform inserts at a taken order (shifting the
  block below, seen 2026-09) or keeps both at it (the newest after);
- plan_tail_moves(): the one-time repair (tools/fix_roster_order.py) - the
  links, Submit and the hidden fields below them move to empty orders after
  the last one, so no roster is ever written;
- audit_layout(): what tools/form_status.py reports.

Pure functions: no API calls; a refusal is sys.exit("what to fix").
"""
import sys

from . import links

ROSTER = "control_checkbox"
BUTTON = "control_button"
PAGE_BREAK = "control_pagebreak"
FIX = "run tools/fix_roster_order.py (dry run first)"


def label(q):
    return f"{q.get('name') or q.get('type')} (q{q['qid']})"


def is_roster(q):
    return q.get("type") == ROSTER


def buttons(questions):
    return [q for q in questions.values() if q.get("type") == BUTTON]


def in_render_order(questions):
    return sorted(questions.values(), key=links.render_key)


def fence(questions):
    """The first of the link elements and Submit in render order (None when
    the form has neither). Two Submit buttons: a refusal."""
    found = buttons(questions)
    if len(found) > 1:
        sys.exit(f"expected one Submit button, found {len(found)} - "
                 "fix the form in the builder first")
    found += [q for q, _ in links.elements_on(questions)]
    return min(found, key=links.render_key) if found else None


def rosters_below(questions, at=None):
    """The rosters rendering after the fence (or `at`), in render order."""
    at = fence(questions) if at is None else at
    if at is None:
        return []
    return [q for q in in_render_order(questions)
            if is_roster(q) and links.render_key(q) > links.render_key(at)]


def roster_slot(questions):
    """(order, fence) for a roster the sync creates. No fence: the highest
    order + 1 (the end of the form, as before). Otherwise the order of the
    last roster rendering above the fence - inserted there, the new roster
    renders before it; kept equal to it, after it (the newest); either way
    above the fence - or the fence's own order when no roster is above it.
    Several creates in one run all take the same order."""
    at = fence(questions)
    if at is None:
        return max((links.order_of(q) for q in questions.values()), default=0) + 1, None
    above = [q for q in questions.values()
             if is_roster(q) and links.render_key(q) < links.render_key(at)]
    if above:
        return links.order_of(max(above, key=links.render_key)), at
    return links.order_of(at), at


def _sequence(questions, qids):
    """The qids in `qids`, in render order."""
    return [str(q["qid"]) for q in in_render_order(questions) if str(q["qid"]) in qids]


def plan_tail_moves(questions, conditions=()):
    """[(qid, new order)] in write order: the one-time repair. [] when no
    roster renders below the fence.

    The tail = every non-roster question rendering at or below the fence (the
    links, Submit, the hidden fields). Its final sequence is the links in
    render order, then Submit, then the rest in render order; element i gets
    order M+1+i (M = the highest order), so every target is empty when it is
    written and no roster is ever written. Write order: Submit first (every
    roster is then above it), the hidden fields bottom-up, the links
    bottom-up - the fence moves last, so a stop anywhere leaves a roster
    below the fence and a re-run (re-planned from the form as it is) ends in
    the same sequence. Without a link Submit is the fence and goes last.

    Refuses (never guesses): not exactly one Submit; a page break; a link
    below Submit; anything a mentor can see in the tail but the links and
    Submit; a simulation in which a roster stays below the fence, a link
    falls below Submit or out of order at any step, or what a mentor sees
    comes out in another sequence."""
    found = buttons(questions)
    if len(found) != 1:
        sys.exit(f"expected one Submit button, found {len(found)} - "
                 "fix the form in the builder first")
    submit = found[0]
    breaks = [q for q in questions.values() if q.get("type") == PAGE_BREAK]
    if breaks:
        sys.exit(f"the form has {len(breaks)} page break(s) ({', '.join(label(q) for q in breaks)}) - "
                 "this repair is for one-page forms; move the rosters in the builder")
    link_qids = {str(q["qid"]) for q, _ in links.elements_on(questions)}
    low = [q for q in in_render_order(questions)
           if str(q["qid"]) in link_qids and links.render_key(q) > links.render_key(submit)]
    if low:
        sys.exit(f"{', '.join(label(q) for q in low)} render(s) below Submit - move it back "
                 "above Submit first (tools/add_feedback_link.py flags it)")
    at = fence(questions)
    if not rosters_below(questions, at):
        return []

    shown = links.shown_by_rules(conditions)
    tail = [q for q in in_render_order(questions)
            if not is_roster(q) and links.render_key(q) >= links.render_key(at)]
    stray = [q for q in tail if q is not submit and str(q["qid"]) not in link_qids
             and links.can_appear(q, shown)]
    if stray:
        sys.exit(f"{', '.join(label(q) for q in stray)}: a mentor can see it below "
                 f"{label(at)} - move it in the builder first")
    tail_links = [q for q in tail if str(q["qid"]) in link_qids]
    rest = [q for q in tail if q is not submit and str(q["qid"]) not in link_qids]
    top = max(links.order_of(q) for q in questions.values())
    target = {str(q["qid"]): top + 1 + i for i, q in enumerate(tail_links + [submit] + rest)}
    if tail_links:
        writes = [submit] + rest[::-1] + tail_links[::-1]
    else:
        writes = rest[::-1] + [submit]
    moves = [(str(q["qid"]), target[str(q["qid"])]) for q in writes]
    _simulate(questions, moves, [str(q["qid"]) for q in tail_links] + [str(submit["qid"])], shown)
    return moves


def _simulate(questions, moves, bottom, shown):
    """Refuse the plan unless, written one by one as planned: every target is
    empty when written, the links and Submit keep their sequence at every
    step, and at the end no roster is below the fence and what a mentor can
    see comes out in the same sequence as before."""
    def seen(qs):
        return [str(q["qid"]) for q in in_render_order(qs)
                if not is_roster(q) and links.can_appear(q, shown)]
    state = {k: dict(v) for k, v in questions.items()}
    for qid, new_order in moves:
        if any(links.order_of(q) == new_order for q in state.values()):
            sys.exit(f"order {new_order} is taken - the plan would not write to empty slots; "
                     "check the form's layout in the builder first")
        state[qid]["order"] = str(new_order)
        if _sequence(state, set(bottom)) != bottom:
            sys.exit("moving the tail would put a link below Submit on the way - check the "
                     "form's layout in the builder first")
    if rosters_below(state) or seen(state) != seen(questions):
        sys.exit("moving the tail would not bring every roster above the links and Submit "
                 "with the rest unchanged - check the form's layout in the builder first")


def plan_restore(questions, saved):
    """[(qid, order)] that put back the orders of `saved` (the questions as
    snapshotted before the repair): the repair's rollback, for right after
    it. Only what the repair moves (never a roster) goes back; refuses when
    the form's questions or a roster's order differ from the snapshot (the
    form changed since - restore in the builder). Write order: the links
    top-down, the hidden fields, Submit last - the links stay above Submit
    at every step; every target must be empty when written."""
    if set(questions) != set(saved):
        sys.exit(f"the form's questions differ from the snapshot ({len(set(saved) - set(questions))} "
                 f"gone, {len(set(questions) - set(saved))} new) - restore the layout in the builder")
    diff = [qid for qid in questions if links.order_of(questions[qid]) != links.order_of(saved[qid])]
    rosters = sorted((qid for qid in diff if is_roster(questions[qid])), key=int)
    if rosters:
        sys.exit(f"{len(rosters)} roster(s) changed order since the snapshot (first q{rosters[0]}) - "
                 "the form changed since; restore the layout in the builder")
    if not diff:
        return []
    link_qids = {str(q["qid"]) for q, _ in links.elements_on(questions)}
    button = {str(q["qid"]) for q in buttons(questions)}
    ordered = sorted(diff, key=lambda qid: links.render_key(saved[qid]))
    writes = ([q for q in ordered if q in link_qids]
              + [q for q in ordered if q not in link_qids and q not in button]
              + [q for q in ordered if q in button])
    bottom = _sequence(questions, link_qids | button)
    state = {k: dict(v) for k, v in questions.items()}
    for qid in writes:
        target = links.order_of(saved[qid])
        if any(links.order_of(q) == target for q in state.values()):
            sys.exit(f"order {target} is taken - restore the layout in the builder")
        state[qid]["order"] = str(target)
        if _sequence(state, set(bottom)) != bottom:
            sys.exit("putting the orders back would put a link below Submit on the way - "
                     "restore the layout in the builder")
    return [(qid, links.order_of(saved[qid])) for qid in writes]


def audit_layout(questions):
    """Problem lines for tools/form_status.py ([] = the layout is right):
    exactly one Submit, no roster rendering below the fence, no link below
    Submit."""
    found = buttons(questions)
    if len(found) != 1:
        return [f"{len(found)} Submit buttons, expected 1"]
    submit, problems = found[0], []
    at = fence(questions)
    below = rosters_below(questions, at)
    if below:
        problems.append(f"{len(below)} roster(s) render below {label(at)} "
                        f"(first q{below[0]['qid']}) - {FIX}")
    for q, _ in sorted(links.elements_on(questions), key=lambda e: links.render_key(e[0])):
        if links.render_key(q) > links.render_key(submit):
            problems.append(f"{label(q)} renders below Submit - move it back above Submit "
                            "(tools/add_feedback_link.py flags it)")
    return problems


def summary(questions):
    """For form_status --json: the fence and how many rosters render below it."""
    found = buttons(questions)
    at = fence(questions) if len(found) <= 1 else None
    rosters = [q for q in questions.values() if is_roster(q)]
    below = rosters_below(questions, at) if at is not None else []
    return {"submit_buttons": len(found), "fence": label(at) if at is not None else None,
            "rosters": len(rosters), "rosters_below": len(below),
            "first_below": str(below[0]["qid"]) if below else None}
