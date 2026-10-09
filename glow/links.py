"""The text elements the attendance forms carry just above the Submit button,
in one table: the problem-report link and the Club Roster Form link.

tools/add_feedback_link.py places them; tools/add_translations.py and
tools/add_language.py translate them. Jotform translates a text element by its
element id (`text_<qid>`: the whole inner HTML is swapped), so each element
holds ONE plain sentence wrapped in its link - the sentence is the unit that
tools/translations_additions.json translates. Every tool finds an element by
its unique name, never by qid (the qid differs per form).

The sync never touches them: sync_attendance_form.py writes roster checkboxes,
the Club picker, the hidden flags of q5 and q331, the
club guard's warning and the conditions, and no generated rule mentions a link
element (test/sync_conditions_test.py, SyncLeavesTheLinksAlone). The club guard's two
rules are the only generated rules that mention an element other than the
rosters and the structural fields: its warning and the Submit button
(docs/plans/2026-09-29-club-guard.md).

Where the rosters sit relative to these elements and Submit - the order the
sync gives a new roster, the one-time repair, the form_status check - is
glow/layout.py, built on the render-order helpers here.

The translation tools key every one-sentence text element the same way; the
club guard's warning (glow/sync.py) is one too - translated_elements() lists
them all.
"""
import html
import re
import sys
from collections import namedtuple

from .sync import GUARD_SENTENCE, club_guards, rule_parts

# The public "fill in" links of the two Google Forms (docs/RUNBOOK.md, "The forms",
# which the test suite pins them to; first listed in docs/archive/2026-09-01-launch.md).
# Never an edit link: those are for the owner only.
PROBLEM_FORM_URL = ("https://docs.google.com/forms/d/e/"
                    "1FAIpQLSeYx286-Bre0aSOWnhEDgC4_6FjGyPssldLA3J5WzIeK8cKCA/viewform")
ROSTER_FORM_URL = ("https://docs.google.com/forms/d/e/"
                   "1FAIpQLScPO9Dizjl9G8krMcvs1sVnqYku3k8dB7Ycv-1VahgPDssMzQ/viewform")

SUBMIT = "submit"   # `above` value: directly above the Submit button

Link = namedtuple("Link", "key name sentence url above")
#   key       the tool's --link value
#   name      the element's unique Jotform name (how every tool finds it)
#   sentence  the English text; its translations are in translations_additions.json
#   url       the public form it opens (default; the tool's --url overrides)
#   above     the element it sits directly above (SUBMIT, or another link's name)

PROBLEM = Link("problem", "somethingNotWorking", "Click here to report a problem",
               PROBLEM_FORM_URL, SUBMIT)
ROSTER = Link("roster", "clubRosterFormLink",
              "A girl missing, or no longer in your club? Tell us on the Club Roster Form.",
              ROSTER_FORM_URL, PROBLEM.name)

LINKS = {link.key: link for link in (PROBLEM, ROSTER)}
BY_NAME = {link.name: link for link in LINKS.values()}

_PUBLIC_URL = re.compile(
    r"https://(?:docs\.google\.com/forms/d/e/[A-Za-z0-9_-]{20,}/viewform"
    r"(?:\?[A-Za-z0-9_.~%=&+-]*)?|forms\.gle/[A-Za-z0-9]+)")


def element_html(sentence, url):
    """The element's HTML: one sentence, the whole of it the link. Byte-equal
    to what the problem-report link (q443) has carried since 2026-09."""
    u = html.escape(url, quote=True)
    return ('<p style="margin:12px 0;padding:10px 12px;border:1px solid #ddd;'
            'border-radius:6px;background:#f7f7f7;font-size:14px">'
            f'<a href="{u}" target="_blank" rel="noopener">'
            f'{html.escape(sentence, quote=False)}</a></p>')


def href_of(text):
    """The link target inside an element's HTML ('' when there is none)."""
    m = re.search(r'href="([^"]*)"', text or "")
    return html.unescape(m.group(1)) if m else ""


def check_public_url(url):
    """Refuse anything but a Google Form's public link (what a respondent sees)."""
    if not _PUBLIC_URL.fullmatch(url or ""):
        sys.exit(f"not a Google Form's public link: {url!r} - use the address a "
                 "respondent sees (https://docs.google.com/forms/d/e/…/viewform or "
                 "https://forms.gle/…), never an edit link")
    return url


def order_of(q):
    try:
        return int(float(q.get("order", 0) or 0))
    except (TypeError, ValueError):
        return 0


def named(questions, name):
    """Every question carrying this unique name (normally zero or one)."""
    return [q for q in questions.values() if q.get("name") == name]


def elements_on(questions):
    """[(question, Link)] for the link elements present on a form."""
    return [(q, BY_NAME[q["name"]]) for q in questions.values()
            if q.get("type") == "control_text" and q.get("name") in BY_NAME]


def translated_elements(questions):
    """[(question, English sentence)] for every one-sentence text element on a
    form that the translation tools key by sentence, element id (`text_<qid>`)
    and stored HTML: the links above Submit and the club guard's warning."""
    out = [(q, link.sentence) for q, link in elements_on(questions)]
    out += [(questions[qid], GUARD_SENTENCE) for qid in club_guards(questions)
            if questions[qid].get("type") == "control_text"]
    return out


def submit_button(questions):
    buttons = [q for q in questions.values() if q.get("type") == "control_button"]
    if len(buttons) != 1:
        sys.exit(f"expected one Submit button, found {len(buttons)} - "
                 "fix the form in the builder first")
    return buttons[0]


def render_key(q):
    """Jotform renders by order, and equal orders in creation order (qid)."""
    return (order_of(q), int(q["qid"]))


def _parts(rule):
    """rule_parts(rule), or a ValueError: a rule that does not parse stops the caller."""
    parts = rule_parts(rule)
    if parts is None:
        ident = rule.get("id") if isinstance(rule, dict) else "?"
        raise ValueError(f"rule {ident}: its terms or action do not parse")
    return parts


def shown_by_rules(conditions):
    """qids some rule shows: hidden fields a mentor can still get to see."""
    out = set()
    for c in conditions or []:
        _, action = _parts(c)
        out |= {str(a.get("field")) for a in action if a.get("visibility") == "Show"}
    return out


def can_appear(q, shown):
    """Whether a mentor can ever see the element: not hidden, a roster (its
    club's rule shows it), or anything else a rule shows."""
    return (q.get("hidden") != "Yes" or q.get("type") == "control_checkbox"
            or str(q["qid"]) in shown)


def must_sit_above(questions, link):
    """The elements `link` has to render above, in render order: its anchor
    (when present) and everything down to the Submit button, Submit included."""
    submit = submit_button(questions)
    anchor = named(questions, link.above) if link.above != SUBMIT else []
    lo, hi = render_key(anchor[0] if anchor else submit), render_key(submit)
    return sorted((q for q in questions.values() if lo <= render_key(q) <= hi),
                  key=render_key)


def out_of_place(questions, link, q):
    """[(element, what it should render above but does not)] for the element
    `q` of `link`: above everything must_sit_above names, and - checked on
    their own, since that run is empty once the anchor has slipped below the
    button - `q` above its anchor and Submit, the anchor above Submit."""
    submit = submit_button(questions)
    anchor = [a for a in named(questions, link.above) if a is not q] if link.above != SUBMIT else []
    pairs = [(q, o) for o in must_sit_above(questions, link) if o is not q]
    pairs += [(q, a) for a in anchor] + [(q, submit)] + [(a, submit) for a in anchor]
    out, seen = [], set()
    for x, o in pairs:
        if render_key(x) >= render_key(o) and (x["qid"], o["qid"]) not in seen:
            seen.add((x["qid"], o["qid"]))
            out.append((x, o))
    return out


def plan_insert(questions, link, conditions=()):
    """Where a missing element goes: (order, moves). It takes the order of the
    element it sits above (Submit when that one is missing); that element and
    everything down to Submit move one down. `moves` = [(qid, new order)] tail
    first, so each intermediate state still renders in order.

    Refuses (never guesses) when the element it goes above is hidden, when
    that run holds anything a mentor could see other than link elements and
    Submit, and when a dry simulation shows the elements a mentor can see
    would come out in any other sequence than before with the new one
    directly above its anchor - equal orders render in creation order, and a
    new element is always the newest."""
    submit = submit_button(questions)
    anchor = named(questions, link.above) if link.above != SUBMIT else []
    if len(anchor) > 1:
        sys.exit(f"{len(anchor)} elements are named {link.above!r} - "
                 "delete the extra one in the builder first")
    if anchor and render_key(anchor[0]) > render_key(submit):
        sys.exit(f"{link.above!r} (q{anchor[0]['qid']}) sits below Submit - "
                 "move it back above Submit first")
    shown = shown_by_rules(conditions)
    run = must_sit_above(questions, link)
    if not can_appear(run[0], shown):   # what the new element must sit directly above
        q = run[0]
        fix = (f"unhide it (--link {BY_NAME[q['name']].key}) or take it out "
               f"(--link {BY_NAME[q['name']].key} --remove)" if q.get("name") in BY_NAME
               else "unhide it in the builder")
        sys.exit(f"{q.get('name') or q.get('type')} (q{q['qid']}) is hidden, so nothing can "
                 f"sit directly above it - {fix} first")
    stray =[q for q in run if q is not submit and q.get("name") not in BY_NAME
             and can_appear(q, shown)]
    if stray:
        sys.exit("unexpected element(s) between the insertion point and Submit: "
                 + ", ".join(f"q{q['qid']} {q.get('type')} {q.get('name')!r}" for q in stray)
                 + " - check the form's layout in the builder first")
    order = order_of(run[0])
    moves = [(str(q["qid"]), order_of(q) + 1) for q in reversed(run)]

    new_qid = str(max(int(k) for k in questions) + 1)
    after = {k: dict(v) for k, v in questions.items()}
    for qid, new_order in moves:
        after[qid]["order"] = str(new_order)
    after[new_qid] = {"qid": new_qid, "type": "control_text", "name": link.name,
                      "order": str(order)}

    def seen(qs):
        return [str(q["qid"]) for q in sorted(qs.values(), key=render_key) if can_appear(q, shown)]
    want = seen(questions)
    want.insert(want.index(str(run[0]["qid"])), new_qid)
    if seen(after) != want:
        sys.exit("inserting there would reorder what mentors see - check the form's "
                 "layout in the builder first")
    return order, moves


def rules_mentioning(conditions, qid):
    """Ids of the rules whose terms or actions mention question `qid`."""
    qid = str(qid)
    hits = []
    for c in conditions or []:
        for items in _parts(c):
            if any(qid in (str(i.get("field", "")), str(i.get("resultField", "")))
                   or qid in str(i.get("operands", "")).split(",")
                   or "{%s}" % qid in str(i.get("equation", ""))
                   for i in items):
                hits.append(str(c.get("id")))
                break
    return hits
