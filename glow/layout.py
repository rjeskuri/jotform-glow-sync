"""Where the rosters sit relative to the links and the Submit button
(BACKLOG 47, docs/plans/2026-09-29-rosters-above-submit.md).

Every attendance form ends in the same way: the rosters (hidden checkboxes a
rule shows for the picked club), then the optional session-notes field
(ticket #104, once tools/add_session_notes.py has placed it), the link
elements (glow/links.py) and the Submit button, then hidden bridge fields. A
mentor sees her girls' names where her roster renders, so a roster rendering
after Submit shows them under the button. Jotform renders by `order`, equal
orders by creation (qid) - links.render_key.

- fence(): the first of the notes field, the links and Submit - what every
  roster must render above;
- roster_slot(): the order the sync gives a new roster so that it renders
  above the fence, whether Jotform inserts at a taken order (shifting the
  block below, seen 2026-09) or keeps both at it (the newest after);
- notes_slot(): the order tools/add_session_notes.py gives the notes field -
  an empty one after the last roster and before the links - and, when none
  is free, the moves that free one;
- plan_tail_moves(): the one-time repair (tools/fix_roster_order.py) - the
  notes field, the links, Submit and the hidden fields below them move to
  empty orders after the last one, so no roster is ever written;
- audit_layout(): what tools/form_status.py reports.

Pure functions: no API calls; a refusal is sys.exit("what to fix").
"""
import sys

from . import links

ROSTER = "control_checkbox"
BUTTON = "control_button"
PAGE_BREAK = "control_pagebreak"
FIX = "run tools/fix_roster_order.py (dry run first)"

# The optional session-notes field (ticket #104; Ryan's answers, 2026-10-22: the
# label, no sub-label, 1,000 characters). One textarea, found by its name - the
# qid differs per form - with no rule, never required or hidden; the sync leaves
# it alone. Jotform's textarea keeps its limit as `entryLimit` "<Type>-<N>" and
# the runtime counts `Letters` as characters: task #105 reads a live textarea's
# value before the first create (RUNBOOK "Session notes on the attendance forms").
NOTES_NAME = "sessionNotes"
NOTES_PROPS = {
    "type": "control_textarea",
    "text": "Additional information about this session (optional)",
    "subLabel": "",
    "entryLimit": "Letters-1000",
    "required": "No",
    "hidden": "No",
}
NOTES_EXPECTED = False    # True once task #105 has placed it: a form without it is then a problem
NOTES_FIX = "tools/add_session_notes.py (dry run first)"


def label(q):
    return f"{q.get('name') or q.get('type')} (q{q['qid']})"


def is_roster(q):
    return q.get("type") == ROSTER


def buttons(questions):
    return [q for q in questions.values() if q.get("type") == BUTTON]


def notes_fields(questions):
    """Every question named NOTES_NAME (normally zero or one), by qid."""
    return sorted(links.named(questions, NOTES_NAME), key=lambda q: int(q["qid"]))


def in_render_order(questions):
    return sorted(questions.values(), key=links.render_key)


def fence(questions):
    """The first of the notes field, the link elements and Submit in render
    order (None when the form has none of them). Two Submit buttons: a
    refusal."""
    found = buttons(questions)
    if len(found) > 1:
        sys.exit(f"expected one Submit button, found {len(found)} - "
                 "fix the form in the builder first")
    found += [q for q, _ in links.elements_on(questions)] + notes_fields(questions)
    return min(found, key=links.render_key) if found else None


def _front(questions):
    """qids of what sits between the rosters and Submit by design: the notes
    field and the link elements."""
    return ({str(q["qid"]) for q, _ in links.elements_on(questions)}
            | {str(q["qid"]) for q in notes_fields(questions)})


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


def notes_neighbours(questions):
    """(the last roster rendering above the links and Submit, the first of the
    links and Submit): what the notes field sits between. Refuses without
    exactly one Submit, and when no roster renders above them."""
    submit = links.submit_button(questions)
    first = min([q for q, _ in links.elements_on(questions)] + [submit], key=links.render_key)
    above = [q for q in questions.values()
             if is_roster(q) and links.render_key(q) < links.render_key(first)]
    if not above:
        sys.exit(f"no roster renders above {label(first)} - the notes go after the last "
                 "roster; check the form's layout in the builder first")
    return max(above, key=links.render_key), first


def notes_slot(questions, conditions=()):
    """(order, moves) for the notes field tools/add_session_notes.py creates:
    the lowest empty order after the last roster rendering above the links
    and Submit and below the first of them, and no moves - created at an
    empty order, nothing else moves whether Jotform inserts or ties. When no
    order is free (the 2026-09-30 repair put the tail right after the last
    roster, and every roster inserted since kept it there): the first link's
    order, and the [(qid, new order)] that free it - the block from the first
    link down to the first empty order (the links, Submit, the hidden fields
    right after) each one down, bottom-up so every target is empty when it is
    written (the path Jotform keeps exactly): what Jotform's own insert would
    shift, done first and read back (Ryan, 2026-10-23).

    Refuses (never guesses): a hidden link or Submit between the first link
    and Submit, anything a mentor can see between the last roster and Submit
    but the links and Submit (visible, or hidden and shown by a rule), a
    roster in the block, two questions of the block sharing an order (both
    named; tools/add_feedback_link.py --link roster leaves Submit tied with
    the field below it, so the notes go on before that link), a move onto a
    taken order, and a simulation in which the form's sequence changes or
    the freed order is still taken."""
    last, first = notes_neighbours(questions)
    submit = links.submit_button(questions)
    shown = links.shown_by_rules(conditions)
    link_qids = {str(q["qid"]) for q, _ in links.elements_on(questions)}
    lo, hi = links.render_key(last), links.render_key(submit)
    for q in in_render_order(questions):
        if not lo < links.render_key(q) <= hi:
            continue
        ours = q is submit or str(q["qid"]) in link_qids
        if ours and not links.can_appear(q, shown):
            fix = (f"unhide it or take it out (tools/add_feedback_link.py --link "
                   f"{links.BY_NAME[q['name']].key} [--remove])" if q.get("name") in links.BY_NAME
                   else "unhide it in the builder")
            sys.exit(f"{label(q)} is hidden, so nothing can sit directly above it - {fix} first")
        if not ours and links.can_appear(q, shown):
            sys.exit(f"q{q['qid']} {q.get('type')} {q.get('name')!r}: a mentor can see it between "
                     f"{label(last)} and Submit - move it in the builder first")
    taken = {links.order_of(q) for q in questions.values()}
    free = [o for o in range(links.order_of(last) + 1, links.order_of(first)) if o not in taken]
    if free:
        return free[0], []

    order = links.order_of(first)
    at = {}
    for q in questions.values():
        at.setdefault(links.order_of(q), []).append(q)
    block, o = [], order
    while o in at:
        block += at[o]
        o += 1
    rosters = [q for q in block if is_roster(q)]
    if rosters:
        sys.exit(f"{label(rosters[0])} shares the run of orders from {label(first)} ({order}) down - "
                 f"the order freed would not be empty; {FIX}")
    tied = next((at[k] for k in range(order, o) if len(at[k]) > 1), None)
    if tied:    # both named: the operator sees what blocks it
        pair = " and ".join(label(q) for q in sorted(tied, key=links.render_key))
        sys.exit(f"{pair} share order {links.order_of(tied[0])} - making room writes only to empty "
                 "orders, so it cannot move them apart. The notes go on before the Club Roster Form "
                 "link (tools/add_feedback_link.py --link roster leaves Submit tied with the field "
                 "below it): with that link on, take it out (--link roster --remove --apply), add "
                 "the notes, then place the link again; any other tie: untie it in the builder "
                 "first (RUNBOOK \"Session notes on the attendance forms\")")
    moves = [(str(q["qid"]), links.order_of(q) + 1)
             for q in sorted(block, key=links.render_key, reverse=True)]
    state = {k: dict(v) for k, v in questions.items()}
    for qid, new_order in moves:
        if any(links.order_of(q) == new_order for q in state.values()):
            sys.exit(f"order {new_order} is taken - making room would not write to empty orders; "
                     "check the form's layout in the builder first")
        state[qid]["order"] = str(new_order)
    if ([q["qid"] for q in in_render_order(state)] != [q["qid"] for q in in_render_order(questions)]
            or any(links.order_of(q) == order for q in state.values())):
        sys.exit("making room would re-order the form - check the form's layout in the builder first")
    return order, moves


def _sequence(questions, qids):
    """The qids in `qids`, in render order."""
    return [str(q["qid"]) for q in in_render_order(questions) if str(q["qid"]) in qids]


def plan_tail_moves(questions, conditions=()):
    """[(qid, new order)] in write order: the one-time repair. [] when no
    roster renders below the fence.

    The tail = every non-roster question rendering at or below the fence (the
    notes field, the links, Submit, the hidden fields). Its final sequence is
    the notes field and the links in render order, then Submit, then the rest
    in render order; element i gets order M+1+i (M = the highest order), so
    every target is empty when it is written and no roster is ever written.
    Write order: Submit first (every roster is then above it), the hidden
    fields bottom-up, the notes field and the links bottom-up - the fence
    moves last, so a stop anywhere leaves a roster below the fence and a
    re-run (re-planned from the form as it is) ends in the same sequence.
    Without a link Submit is the fence and goes last.

    Refuses (never guesses): not exactly one Submit; a page break; a link or
    the notes field below Submit; anything a mentor can see in the tail but
    the notes field, the links and Submit; a simulation in which a roster
    stays below the fence, a link falls below Submit or out of order at any
    step, or what a mentor sees comes out in another sequence."""
    submit = links.submit_button(questions)          # exactly one, or a refusal
    breaks = [q for q in questions.values() if q.get("type") == PAGE_BREAK]
    if breaks:
        sys.exit(f"the form has {len(breaks)} page break(s) ({', '.join(label(q) for q in breaks)}) - "
                 "this repair is for one-page forms; move the rosters in the builder")
    front = _front(questions)
    low = [q for q in in_render_order(questions)
           if str(q["qid"]) in front and links.render_key(q) > links.render_key(submit)]
    if low:
        sys.exit(f"{', '.join(label(q) for q in low)} render(s) below Submit - move it back "
                 "above Submit first (tools/form_status.py flags it)")
    at = fence(questions)
    if not rosters_below(questions, at):
        return []

    shown = links.shown_by_rules(conditions)
    tail = [q for q in in_render_order(questions)
            if not is_roster(q) and links.render_key(q) >= links.render_key(at)]
    stray = [q for q in tail if q is not submit and str(q["qid"]) not in front
             and links.can_appear(q, shown)]
    if stray:
        sys.exit(f"{', '.join(label(q) for q in stray)}: a mentor can see it below "
                 f"{label(at)} - move it in the builder first")
    tail_front = [q for q in tail if str(q["qid"]) in front]
    rest = [q for q in tail if q is not submit and str(q["qid"]) not in front]
    top = max(links.order_of(q) for q in questions.values())
    target = {str(q["qid"]): top + 1 + i for i, q in enumerate(tail_front + [submit] + rest)}
    if tail_front:     # noqa: SIM108  (two layouts read better as two branches)
        writes = [submit] + rest[::-1] + tail_front[::-1]
    else:
        writes = rest[::-1] + [submit]
    moves = [(str(q["qid"]), target[str(q["qid"])]) for q in writes]
    _simulate(questions, moves, [str(q["qid"]) for q in tail_front] + [str(submit["qid"])], shown)
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
    form changed since - restore in the builder), and when the snapshot
    holds another question at an order to be written back (a tie, e.g. the
    Club Roster Form link placed before the repair leaves Submit sharing the
    next field's order): that cannot be rebuilt by writing to empty orders,
    and writing onto a taken one would rest on unobserved semantics. Write
    order: the notes field and the links top-down, the hidden fields, Submit
    last - the links stay above Submit at every step; every target must be
    empty when written."""
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
    front = _front(questions)
    button = {str(q["qid"]) for q in buttons(questions)}
    ordered = sorted(diff, key=lambda qid: links.render_key(saved[qid]))
    writes = ([q for q in ordered if q in front]
              + [q for q in ordered if q not in front and q not in button]
              + [q for q in ordered if q in button])
    for qid in writes:
        target = links.order_of(saved[qid])
        tied = sorted((k for k in saved if k != qid and links.order_of(saved[k]) == target), key=int)
        if tied:
            sys.exit(f"the snapshot holds more than one question at order {target} (q{qid}, "
                     f"q{tied[0]}) - --undo writes only to empty orders, so it cannot rebuild "
                     "that; restore with Jotform's Revision History (or the builder)")
    bottom = _sequence(questions, front | button)
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


def misplaced(questions):
    """Problem lines about where things sit ([] = every element is where it
    belongs): exactly one Submit, no roster rendering below the fence, no
    link below Submit, the notes field at most once and above the links and
    Submit. What tools/add_session_notes.py refuses on: it sets the field's
    flags right, never its place."""
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
    notes = notes_fields(questions)
    if len(notes) > 1:
        problems.append(f"{len(notes)} fields named {NOTES_NAME!r} "
                        f"({', '.join('q' + str(q['qid']) for q in notes)}), expected 1 - "
                        "delete the extra one in the builder")
    elif notes:
        q = notes[0]
        tail = [o for o, _ in links.elements_on(questions)] + [submit]
        low = [o for o in sorted(tail, key=links.render_key) if links.render_key(o) < links.render_key(q)]
        if low:
            problems.append(f"{label(q)} renders below {'Submit' if low[0] is submit else label(low[0])} - "
                            "it belongs after the last roster and above the links and Submit; move it "
                            "in the builder, or tools/add_session_notes.py --remove --apply and add it again")
    return problems


def audit_layout(questions):
    """Problem lines for tools/form_status.py ([] = the layout is right):
    misplaced(), then the notes field's flags - required or hidden - and,
    with NOTES_EXPECTED, its absence."""
    problems = misplaced(questions)
    notes = notes_fields(questions)
    if len(notes) == 1:
        q = notes[0]
        if q.get("required") == "Yes":
            problems.append(f"{label(q)} is required - the notes are optional; {NOTES_FIX} sets it back")
        if q.get("hidden") == "Yes":
            problems.append(f"{label(q)} is hidden - no mentor can fill it; {NOTES_FIX} unhides it")
    elif not notes and NOTES_EXPECTED:
        problems.append(f"no field named {NOTES_NAME!r} - run {NOTES_FIX}")
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
