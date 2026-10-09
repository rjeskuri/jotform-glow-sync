"""Reading an attendance form's submissions as Jotform gives them (glow.jotform.Client.submissions):
the answer to a question, the ticked rosters, the attendance date, and the module, session and
year a submission holds - from the dropdowns, not their copies in questions 98 / 100 / 102, which
a browser's page translation could rewrite (docs/plans/2026-09-30-backfill-resolver.md).

An answer of a shape these readers do not know raises Unreadable (what is wrong; never the
answer itself, which can hold a girl's name): the caller says what it means for its run.
"""
import datetime

from .sync import MODULE_ID, MODULES, SESSION_OVERRIDES, WEEK_ID, WEEKS, YEAR, YEAR_ID, has_calc_values

DATE = "17"             # the attendance date question (Jotform: {year, month, day})


class Unreadable(ValueError):
    """An answer of a shape the readers do not know: what is wrong, never the answer."""


def qid_order(qid):
    return (0, int(qid), "") if str(qid).isdigit() else (1, 0, str(qid))


def answer_of(sub, qid):
    """The answer to a question as submitted, or None when it has none."""
    found = sub["answers"].get(qid)
    return found.get("answer") if isinstance(found, dict) else None


def text_of(sub, qid):
    """A text answer as submitted (None when there is none); any other shape is Unreadable."""
    value = answer_of(sub, qid)
    if value is not None and not isinstance(value, str):
        raise Unreadable(f"q{qid} is answered with a {type(value).__name__}, not text")
    return value


def ticked_names(qid, value):
    """The ticked options of one roster answer, each trimmed, order kept ([] = no tick).
    Jotform gives a checkbox answer as a list of strings; no answer at all, an empty list
    and an empty string are 'no tick'; anything else is Unreadable."""
    if value is None or value == "" or value == []:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise Unreadable(f"roster q{qid} is answered with a {type(value).__name__} that is not a "
                         "list of names")
    return [v.strip() for v in value if v.strip()]


def ticked_rosters(sub, questions):
    """[(qid, answer, names)] for every roster with a tick in this submission, in qid
    order. A roster is a checkbox question of the form as it is today; an answer to a
    question no longer on the form counts when the answer itself says it was a checkbox,
    and is Unreadable when it says nothing (it could be a roster)."""
    answers = sub.get("answers")
    if not isinstance(answers, dict):
        raise Unreadable(f"its answers are a {type(answers).__name__}, not a table by question id")
    out = []
    for qid, found in answers.items():
        if not isinstance(found, dict):
            raise Unreadable(f"the answer to q{qid} is a {type(found).__name__}")
        now = questions.get(qid)
        if now is not None:
            if now.get("type") != "control_checkbox":
                continue
        elif found.get("type") != "control_checkbox":
            if found.get("type") or found.get("answer") in (None, "", [], {}):
                continue
            raise Unreadable(f"q{qid} is answered but is not on the form any more, and the answer does "
                             "not say what kind of question it was: a ticked roster cannot be ruled out")
        names = ticked_names(qid, found.get("answer"))
        if names:
            out.append((qid, found, names))
    return sorted(out, key=lambda t: qid_order(t[0]))


def attendance_date(sub):
    """Question 17 (Jotform: {year, month, day}) as zero-padded yyyy-mm-dd text; "" - never
    None: the loader reads text - when it is missing or is not a date."""
    value = answer_of(sub, DATE)
    if not isinstance(value, dict):
        return ""
    try:
        return datetime.date(int(value["year"]), int(value["month"]), int(value["day"])).isoformat()
    except (KeyError, TypeError, ValueError):
        return ""


def stored_option(sub, questions, qid):
    """(the stored answer of dropdown `qid`, what a calculation copies from it) when the
    answer is exactly one of the dropdown's options today; (None, None) when it is not, or
    there is no such dropdown on the form, or no answer. The stored answer is the option's
    value, which a browser's page translation leaves alone. The copy is the option's
    calcValue when the dropdown has calcValues (they start with an empty slot for the
    placeholder: .claude/skills/jotform-api), else its text; None when the calcValues do not
    line up with the options."""
    question, answer = questions.get(qid) or {}, answer_of(sub, qid) if qid else None
    options = [o.strip() for o in (question.get("options") or "").split("|")]
    if question.get("type") != "control_dropdown" or not isinstance(answer, str) \
            or not answer or answer not in options:
        return None, None
    if not has_calc_values(question):
        return answer, answer
    values = [v.strip() for v in question["calcValues"].split("|")]
    if len(values) == len(options) + 1:
        values = values[1:]
    if len(values) != len(options):
        return answer, None
    return answer, values[options.index(answer)] or answer


def session_dropdown(year, module):
    """The session dropdown the form shows for a year and a module (the sync's curriculum
    cascade, build_conditions section B): the 8-session one for year 1, for another year
    the one of the module (SESSION_OVERRIDES, else 8). None when that cannot be said."""
    if year == "1":
        return WEEKS[8]
    if year in MODULES and module is not None:
        return WEEKS.get(SESSION_OVERRIDES.get(module, 8))
    return None


def copied_fields(sub, questions):
    """(module, verdicts) of one submission. module: the CANONICAL module - the stored
    answer of the module dropdown the Year answer names (glow.sync.MODULES; the form shows
    that one, and a dropdown hidden again can keep an answer, so any other is ignored) - or
    None when it cannot be told: no guess. verdicts: {module | week | year: same | differ |
    undetermined} - whether question 98 / 100 / 102 as submitted is exactly what its
    source dropdown holds (the module's value; the session's and the year's calcValue)."""
    year, year_copy = stored_option(sub, questions, YEAR)
    module, _ = stored_option(sub, questions, MODULES.get(year))
    _, week_copy = stored_option(sub, questions, session_dropdown(year, module))

    def verdict(qid, source):
        return "undetermined" if source is None else "same" if answer_of(sub, qid) == source else "differ"
    return module, {"module": verdict(MODULE_ID, module), "week": verdict(WEEK_ID, week_copy),
                    "year": verdict(YEAR_ID, year_copy)}
