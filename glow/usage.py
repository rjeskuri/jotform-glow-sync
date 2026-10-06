"""Jotform's account limits against its usage, read-only
(docs/plans/2026-10-06-photos-to-drive.md).

Two limits matter to the attendance forms, and each is judged on its own: the
upload space (cumulative and account-wide - the group photos, about 1.9 MB
each) and the submissions in the monthly cycle. Reaching either makes Jotform
disable the forms ("Form over quota") and attendance collection stops. Upload
space is what Gold or a retention policy answers (BACKLOG "Gold versus
retention"); a busy month's submissions reset on the cycle's date and would
otherwise read as a storage warning, so the two are never merged into one
level. tools/form_status.py prints the line, tools/auto_sync.py logs it once
per run and raises ATTENTION at alarm. Three GETs, read 2026-10-06:
/user/usage (the counts, as strings; `monthly_usage_reset_date` as
`yyyy-mm-dd 00:00:00`), /user (`account_type`, the plan's URL) and
/system/plan/<NAME> (`limits`, as numbers). Nothing here writes; an answer
that has not the shape read that day is refused (ValueError), never guessed.
"""
import re

WARN_AT = 0.5       # of a limit: the line reads `warn`
ALARM_AT = 0.8      # of a limit: the runner raises ATTENTION
LIMITS = ("uploads", "submissions")
NAMES = {"uploads": "upload space", "submissions": "submissions this cycle"}
LEVELS = ("ok", "warn", "alarm")


def _dict(answer, label):
    if not isinstance(answer, dict):
        raise ValueError(f"{label}: not the object read on 2026-10-06 ({type(answer).__name__})")
    return answer


def plan_name(user):
    """The plan's name from GET /user's `account_type`, the plan's URL
    (…/system/plan/SILVER on 2026-10-06)."""
    value = str(_dict(user, "GET /user").get("account_type") or "").rstrip("/")
    name = value.rsplit("/", 1)[-1].strip()
    if not name:
        raise ValueError("GET /user: no account_type - the plan's limits cannot be looked up")
    return name.upper()


def reset_day(value):
    """The date of `monthly_usage_reset_date` (`2026-10-21 00:00:00` read 2026-10-06);
    a value of another shape is kept as it is, never guessed into a date."""
    text = str(value or "")
    return text[:10] if re.match(r"\d{4}-\d{2}-\d{2}( |$)", text) else text


def read_usage(client):
    """{plan, uploads, uploads_cap, submissions, submissions_cap, reset}, in bytes and
    counts, from the three GETs. Raises glow.jotform.JotformError (the client's) or
    ValueError (an answer of another shape, a limit of 0): the callers decide what a
    failed read means (form_status prints it, the runner logs it)."""
    usage = _dict(client.get("/user/usage"), "GET /user/usage")
    plan = plan_name(client.get("/user"))
    limits = _dict(client.get(f"/system/plan/{plan}"), f"GET /system/plan/{plan}").get("limits")
    limits = _dict(limits if limits is not None else {}, f"GET /system/plan/{plan} limits")
    try:
        out = {"plan": plan,
               "uploads": int(usage["uploads"]), "uploads_cap": int(limits["uploads"]),
               "submissions": int(usage["submissions"]), "submissions_cap": int(limits["submissions"]),
               "reset": reset_day(usage.get("monthly_usage_reset_date"))}
    except (KeyError, TypeError, ValueError) as err:
        raise ValueError("Jotform's usage or plan answer is not the shape read on 2026-10-06 "
                         f"({err.__class__.__name__}: {err})")
    for limit in LIMITS:
        if out[f"{limit}_cap"] <= 0 or out[limit] < 0:
            raise ValueError(f"{NAMES[limit]}: {out[limit]} of a limit of {out[f'{limit}_cap']} cannot be judged")
    return out


def share(u, limit):
    """The part of `limit` used, 0.0-1.0 (above 1.0 once over quota)."""
    return u[limit] / u[f"{limit}_cap"]


def level(ratio):
    return "alarm" if ratio >= ALARM_AT else "warn" if ratio >= WARN_AT else "ok"


def levels(u):
    """One level per limit, each against its own cap: {"uploads": …, "submissions": …}."""
    return {limit: level(share(u, limit)) for limit in LIMITS}


def worst(lv):
    """The highest level among them (the `!!` prefix, the exit)."""
    return max(lv.values(), key=LEVELS.index)


def gib(n):
    return f"{n / 2 ** 30:.2f} GiB"


def pct(ratio):
    return f"{ratio * 100:.1f}%"


def storage_line(u):
    """The one line both tools print, e.g. `storage: upload space 1.25 GiB of 10.00 GiB (12.5%)
    -> ok; submissions this cycle 474 of 2,500 (19.0%, resets 2026-10-21) -> ok; plan SILVER`."""
    lv = levels(u)
    return (f"storage: {NAMES['uploads']} {gib(u['uploads'])} of {gib(u['uploads_cap'])} "
            f"({pct(share(u, 'uploads'))}) -> {lv['uploads']}; "
            f"{NAMES['submissions']} {u['submissions']:,} of {u['submissions_cap']:,} "
            f"({pct(share(u, 'submissions'))}, resets {u['reset'] or '?'}) -> {lv['submissions']}; "
            f"plan {u['plan']}")
