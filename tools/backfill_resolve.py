#!/usr/bin/env python3
"""September 2026 back-fill, step one: every attendance submission as clean rows. READ-ONLY.

Reads every active submission of the four regional attendance forms (Jotform, GET only) and
writes ONE ROW PER (submission, ticked roster) to data/backfill_2026-09/resolved.json, for the
Salesforce loader (docs/plans/2026-09-30-backfill-resolver.md; RUNBOOK "September back-fill:
the resolver"). The club of a row is the roster the mentor TICKED girls in, never question 5:
September's question 5 was typed, run together from several picked clubs, altered by page
translation, or a bare name two clubs shared. What each roster is (club, partner, the Club Name
it sends today) comes from the sync's own dry run (sync_attendance_form.py --summary-json), so
nothing here matches clubs a second time.

    python3 tools/sheets_client.py export Roster data/roster_<date>.csv
    python3 tools/backfill_resolve.py --roster data/roster_<date>.csv
    python3 tools/backfill_resolve.py --roster data/roster_<date>.csv --region Asia \
        --out data/backfill_2026-09/asia/resolved.json      # one region: never the loader's file

A submission with no tick gets no row: its id is listed under no_ticks. Submissions created
before 2026-09-01 00:00 US Eastern (Jotform's clock) are left out and counted. Every submission
in range is accounted for, or the tool exits with an error; it also exits, writing no result
(the raw copies fetched so far stay, overwritten), when an answer cannot be resolved honestly
(a shape it does not know, a ticked roster it cannot identify).

The output and the raw copies (raw/<region>.json beside it) hold girls' names and mentors'
contact details: they stay under data/ (git-ignored). What is printed is counts only.
The key comes from JOTFORM_API_KEY.
"""
import argparse
import csv
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict, namedtuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow import forms                  # noqa: E402
from glow.cli import run                # noqa: E402
from glow.jotform import Client         # noqa: E402
from glow.sync import (                 # noqa: E402
    CLUB_NAME, CONTACT_IDS, MODULE_ID, PICKER_NAME, SF_NAME_SEP, WEEK_ID, YEAR_ID, club_partners,
    roster_names, roster_pairs)
from glow.text import key               # noqa: E402

SINCE = "2026-09-01 00:00:00"           # created_at, as Jotform gives it: US Eastern
MONTH_START = "2026-09-01"              # an attendance date before it is flagged
DATE, PHOTO, CREATOR = "17", "19", "105"
PAGE = 100                              # submissions per request (Jotform allows up to 1000)
DEFAULT_OUT = os.path.join(REPO, "data", "backfill_2026-09", "resolved.json")
# every flag a row can carry, in the order a row lists them. The three about names that are
# not an option of the roster today are written with their count on the row
# ("name_not_on_roster_now:3"): UNKNOWN + LEFT = NOT_ON_ROSTER. The loader holds a session on
# UNKNOWN (the Roster has no row of that name for the club: Salesforce would create a Contact)
# and sends LEFT (the Roster knows her; she is not an option today).
NOT_ON_ROSTER, UNKNOWN, LEFT = "name_not_on_roster_now", "name_unknown_to_roster", "name_left_roster"
FLAGS = ["multi_club", "q5_differs", "q18_empty", "q18_differs", "typed_era", "bare_shared_name",
         "retired_club", "no_account_name", "date_before_2026_09", "date_missing", NOT_ON_ROSTER,
         UNKNOWN, LEFT, "name_has_comma", "name_repeats"]
CREATED = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
GIRL_ID = re.compile(r"([A-Z0-9]+)-[A-Z0-9]+-\d+")      # CLUBCODE-LASTCODE-NNN (appsscript/Ids.gs)


def qid_order(qid):
    return (0, int(qid), "") if str(qid).isdigit() else (1, 0, str(qid))


# ------------------------------------------------------------------ the Roster
Roster = namedtuple("Roster", "rows active codes holders known")


def read_roster(path):
    """A Roster export as (rows, active, codes, holders, known): how many rows it has; the
    (key(partner), key(club)) of every club with an active girl (glow.sync.roster_pairs);
    {(key(partner), key(club)): [club code, ...]} - the prefix of the girl ids of that
    club's rows, any status (one code per club, normally); {key(club): {key(partner):
    partner}} - who has or had a club of each name, any status, all regions
    (glow.sync.club_partners); and {(key(partner), key(club)): {key(full name)}} - every girl
    the Roster has ever held for that club (glow.sync.roster_names)."""
    pairs = roster_pairs(path)
    active = {(key(p), key(c)) for (p, c), on in pairs.items() if on}
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if "girl_id" not in rows[0]:
        sys.exit("Not a Roster export: no girl_id column (the club codes are read from it) - "
                 "python3 tools/sheets_client.py export Roster <path>")
    codes = defaultdict(set)
    for r in rows:
        found = GIRL_ID.fullmatch((r["girl_id"] or "").strip())
        if found and key(r["partner"]) and key(r["club"]):
            codes[(key(r["partner"]), key(r["club"]))].add(found.group(1))
    return Roster(len(rows), active, {k: sorted(v) for k, v in codes.items()},
                  club_partners(pairs), roster_names(path))


# --------------------------------------------------- what each roster is, today
def sync_plan(roster_csv, region, form_id, runner=subprocess.run):
    """The sync's own plan for this form as a DRY RUN (no --apply: it writes nothing),
    read from its --summary-json: sf_names says, per roster question, the partner, the
    club and the Club Name it sends. The sync's output is not echoed (it is not redacted)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "plan.json")
        argv = [sys.executable, os.path.join(REPO, "sync_attendance_form.py"), roster_csv,
                "--roster", "--region", region, "--form", form_id, "--summary-json", path]
        done = runner(argv, capture_output=True, text=True, cwd=REPO, env=os.environ.copy())
        if done.returncode != 0 or not os.path.exists(path):
            sys.exit(f"{region}: the sync's dry run exited {done.returncode} and gave no plan - run "
                     f"it by hand to see why: python3 sync_attendance_form.py <roster.csv> --roster "
                     f"--region '{region}' --form {form_id}")
        with open(path, encoding="utf-8") as f:
            plan = json.load(f)
    if plan.get("apply") or not isinstance(plan.get("sf_names"), list):
        sys.exit(f"{region}: the sync's summary is not a dry run's plan with sf_names - "
                 "is sync_attendance_form.py older than this tool?")
    return plan


def rosters_today(plan):
    """{qid: (club, partner or None, the Club Name it sends today)} from the sync's plan.
    sf_names holds what each roster sends AFTER the plan; where the plan would change it
    (sf_name_changes), today's value is the change's `old`. The sync records no change for
    a respelling that is equal under glow.text.key, so the SPELLING may still be the
    Roster's: resolve() takes the live Club picker's. The partner is None for a roster the
    region's active export does not hold, unless its rule names one: resolve() asks the
    Roster who has a club of that name."""
    old = {str(c["qid"]): c["old"] for c in plan.get("sf_name_changes") or []}
    out = {}
    for n in plan["sf_names"]:
        if n.get("qid") is None:          # a club the plan would create: on no form yet
            continue
        qid = str(n["qid"])
        out[qid] = (n["club"], n.get("partner") or None, old.get(qid, n["value"]))
    return out


# ---------------------------------------------------------------- submissions
def fetch_submissions(client, form_id, region):
    """Every submission of the form, any status, fetched page by page. Jotform lists the
    newest first, so one arriving meanwhile repeats a submission on the next page (dropped
    here) and hides none; the form's own count, read afterwards, is the check."""
    seen, out, offset = set(), [], 0
    while True:
        page = client.get(f"/form/{form_id}/submissions", limit=PAGE, offset=offset)
        if not isinstance(page, list):
            sys.exit(f"{region}: the submissions answer is a {type(page).__name__}, not a list - "
                     "an answer shape this tool does not know")
        for sub in page:
            if not isinstance(sub, dict) or not sub.get("id"):
                sys.exit(f"{region}: a submission without an id - an answer shape this tool "
                         "does not know")
            if sub["id"] not in seen:
                seen.add(sub["id"])
                out.append(sub)
        if len(page) < PAGE:
            break
        offset += PAGE
    reported = int((client.get(f"/form/{form_id}") or {}).get("count") or 0)
    if len(out) < reported:
        sys.exit(f"{region}: fetched {len(out)} submissions but the form reports {reported} - "
                 "one was missed while paging (a deletion meanwhile?); run it again")
    return out


def refuse(sub, what):
    sys.exit(f"submission {sub.get('id')} (form {sub.get('form_id')}): {what} - no result written "
             "(the raw copies fetched so far are overwritten; an earlier resolved.json is left as it "
             "was); this tool does not guess (docs/plans/2026-09-30-backfill-resolver.md)")


def answer_of(sub, qid):
    """The answer to a question as submitted, or None when it has none."""
    found = sub["answers"].get(qid)
    return found.get("answer") if isinstance(found, dict) else None


def text_of(sub, qid):
    """A text answer as submitted (None when there is none); any other shape is refused."""
    value = answer_of(sub, qid)
    if value is not None and not isinstance(value, str):
        refuse(sub, f"q{qid} is answered with a {type(value).__name__}, not text")
    return value


def ticked_names(sub, qid, value):
    """The ticked options of one roster answer, each trimmed, order kept ([] = no tick).
    Jotform gives a checkbox answer as a list of strings; no answer at all, an empty list
    and an empty string are 'no tick'; anything else is refused."""
    if value is None or value == "" or value == []:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        refuse(sub, f"roster q{qid} is answered with a {type(value).__name__} that is not a "
                    "list of names")
    return [v.strip() for v in value if v.strip()]


def ticked_rosters(sub, questions):
    """[(qid, answer, names)] for every roster with a tick in this submission, in qid
    order. A roster is a checkbox question of the form as it is today; an answer to a
    question no longer on the form counts when the answer itself says it was a checkbox,
    and is refused when it says nothing (it could be a roster)."""
    answers = sub.get("answers")
    if not isinstance(answers, dict):
        refuse(sub, f"its answers are a {type(answers).__name__}, not a table by question id")
    out = []
    for qid, found in answers.items():
        if not isinstance(found, dict):
            refuse(sub, f"the answer to q{qid} is a {type(found).__name__}")
        now = questions.get(qid)
        if now is not None:
            if now.get("type") != "control_checkbox":
                continue
        elif found.get("type") != "control_checkbox":
            if found.get("type") or found.get("answer") in (None, "", [], {}):
                continue
            refuse(sub, f"q{qid} is answered but is not on the form any more, and the answer does "
                        "not say what kind of question it was: a ticked roster cannot be ruled out")
        names = ticked_names(sub, qid, found.get("answer"))
        if names:
            out.append((qid, found, names))
    return sorted(out, key=lambda t: qid_order(t[0]))


def attendance_date(sub):
    """yyyy-mm-dd from question 17 (Jotform: {year, month, day}), None when missing or
    not a date."""
    value = answer_of(sub, DATE)
    if not isinstance(value, dict):
        return None
    try:
        return datetime.date(int(value["year"]), int(value["month"]), int(value["day"])).isoformat()
    except (KeyError, TypeError, ValueError):
        return None


def photo_urls(sub):
    value = answer_of(sub, PHOTO)
    if value is None or value == "":
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        refuse(sub, f"the photo (q{PHOTO}) is answered with a {type(value).__name__} that is not "
                    "a list of links")
    return [v for v in value if v.strip()]


def picked(sub, picker):
    """The Club picker's answer as a list ([] = none: the club name was typed)."""
    value = answer_of(sub, picker) if picker else None
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        refuse(sub, f"the Club picker (q{picker}) is answered with a {type(value).__name__} that "
                    "is not a list of clubs")
    return [v for v in value if v.strip()]


def is_long(value, club):
    """The Club Name is '<club> - <something>' (glow.sync.SF_NAME_SEP; never split on it)."""
    return bool(value) and key(value) != key(club) and key(value).startswith(key(club) + SF_NAME_SEP)


def resolve(region, form_id, submissions, questions, today, roster):
    """(rows, no_ticks, counts) for one form. submissions: as fetched, any status, any
    date; questions: the form today; today: rosters_today(); roster: read_roster()."""
    active, codes = roster.active, roster.codes
    picker = next((qid for qid, q in questions.items() if q.get("type") == "control_dropdown"
                   and q.get("name") == PICKER_NAME), None)
    options = {qid: {o.strip() for o in (q.get("options") or "").split("|") if o.strip()}
               for qid, q in questions.items() if q.get("type") == "control_checkbox"}
    # the live Club picker's entries: exactly, and by key (the first spelling, as the sync reads it)
    entries, entry_of = set(), {}
    for o in (questions[picker].get("options") or "").split("|") if picker else ():
        if o.strip():
            entries.add(o.strip())
            entry_of.setdefault(key(o), o.strip())
    from_roster = 0                                   # rows whose partner the Roster gave, not the sync
    rows, no_ticks, q18_only = [], [], []
    other_status, flag_rows, flag_subs = Counter(), Counter(), Counter()
    pre_launch = 0
    several = Counter()                               # with ticks or not -> picked 2+ clubs
    created = []                                      # created_at of every submission in range
    for sub in sorted(submissions, key=lambda s: (str(s.get("created_at")), str(s.get("id")))):
        if sub.get("status") != "ACTIVE":
            other_status[str(sub.get("status"))] += 1
            continue
        when = sub.get("created_at")
        if not isinstance(when, str) or not CREATED.fullmatch(when):
            refuse(sub, "its created_at is not 'yyyy-mm-dd hh:mm:ss'")
        if when < SINCE:
            pre_launch += 1
            continue
        created.append(when)
        rosters = ticked_rosters(sub, questions)
        q5, q18 = text_of(sub, CLUB_NAME), text_of(sub, CONTACT_IDS)
        date, picks = attendance_date(sub), picked(sub, picker)
        several[bool(rosters)] += len(picks) > 1
        if not rosters:
            no_ticks.append(sub["id"])
            if (q18 or "").strip():     # names reached question 18, no roster of today's form has a tick
                q18_only.append(sub["id"])
            continue
        every = sorted(n for _, _, names in rosters for n in names)
        shared = []                                   # the flags every row of the submission carries
        if len(rosters) > 1:
            shared.append("multi_club")
        if not (q18 or "").strip():
            shared.append("q18_empty")
        elif sorted(piece.strip() for piece in q18.split(",")) != every:
            shared.append("q18_differs")
        if not picks:
            shared.append("typed_era")
        if date is None:
            shared.append("date_missing")
        elif date < MONTH_START:
            shared.append("date_before_2026_09")
        seen_flags = set()
        for qid, found, names in rosters:
            if qid in today:
                club, partner, sends = today[qid]
                if picker and sends is not None and sends not in entries:
                    # what it sends TODAY is the picker entry as the form spells it (the sync's
                    # value can be the Roster's spelling); the picker has none: it sends nothing
                    sends = entry_of.get(key(sends))
                if not partner:
                    # the sync names no partner for a plain-named roster outside the region's
                    # active export (retired, or its rows carry another region or none): when
                    # ONE partner has, or had, a club of that name it is that club - the rule
                    # by which the sync claims a question; two or more: not told apart here
                    who = roster.holders.get(key(club), {})
                    if len(who) == 1:
                        partner, = who.values()
                        from_roster += 1
            elif qid in questions:
                refuse(sub, f"roster q{qid} is on the form but not in the sync's plan (a club "
                            "added a moment ago?) - run it again")
            else:
                club, partner, sends = " ".join(str(found.get("text") or "").split()), None, None
                if not club:
                    refuse(sub, f"ticked roster q{qid} is not on the form any more and its answer "
                                "carries no club name: it cannot be identified")
            pair = (key(partner), key(club))
            code = codes.get(pair, []) if partner else []
            if len(code) > 1:
                sys.exit(f"'{club}' ({partner}): its girl ids start with {len(code)} different "
                         f"club codes ({', '.join(code)}) - one club has one code; settle it in "
                         "the sheet (ClubRegistry) first")
            flags = set(shared)
            if q5 != sends:
                flags.add("q5_differs")
            if is_long(sends, club) and key(q5) == key(club):
                flags.add("bare_shared_name")
            if qid not in questions or not partner or pair not in active:
                flags.add("retired_club")
            if sends is None:
                flags.add("no_account_name")
            counted = {}
            missing = [n for n in names if n not in options.get(qid, ())]
            if missing:
                # no partner: no Roster rows to look the names up in - all unknown (held)
                known = roster.known.get(pair, ()) if partner else ()
                unknown = sum(1 for n in missing if key(n) not in known)
                counted = {NOT_ON_ROSTER: len(missing), UNKNOWN: unknown, LEFT: len(missing) - unknown}
                flags |= {f for f, n in counted.items() if n}
            if any("," in n for n in names):
                flags.add("name_has_comma")
            if len(set(names)) < len(names):
                flags.add("name_repeats")
            flag_rows.update(flags)
            seen_flags |= flags
            rows.append({
                "region": region, "form_id": form_id, "submission_id": sub["id"],
                "created_at": when, "roster_qid": qid, "club_code": code[0] if code else None,
                "club": club, "partner": partner, "sf_account_name": sends,
                "attendance_date": date, "names": names,
                "module": answer_of(sub, MODULE_ID), "module_week": answer_of(sub, WEEK_ID),
                "module_year": answer_of(sub, YEAR_ID), "creator": answer_of(sub, CREATOR),
                "photo_urls": photo_urls(sub), "q5": q5,
                "flags": [f"{f}:{counted[f]}" if f in counted else f for f in FLAGS if f in flags],
            })
        flag_subs.update(seen_flags)
    # the ledger: every submission in range has rows or is listed as having no tick - once
    in_range, with_rows = len(created), {r["submission_id"] for r in rows}
    if len(with_rows) + len(no_ticks) != in_range or with_rows & set(no_ticks) \
            or len(set(no_ticks)) != len(no_ticks) \
            or sum(other_status.values()) + pre_launch + in_range != len(submissions):
        sys.exit(f"{region}: the ledger does not balance - {len(submissions)} fetched, "
                 f"{sum(other_status.values())} not active, {pre_launch} before the launch, "
                 f"{in_range} in range, but {len(with_rows)} with rows and {len(set(no_ticks))} with "
                 "no tick (a submission id twice?). No result written")
    with_ticks = len(with_rows)
    dates = sorted({r["attendance_date"] for r in rows if r["attendance_date"]})
    again = Counter((r["roster_qid"], r["attendance_date"]) for r in rows)
    counts = {
        "form_id": form_id, "submissions": in_range, "pre_launch": pre_launch, "rows": len(rows),
        "no_ticks": len(no_ticks), "flags": {f: flag_rows[f] for f in FLAGS},
        # beyond the loader's contract, for the report and the cross-checks
        "fetched": len(submissions), "not_active": dict(sorted(other_status.items())),
        "with_ticks": with_ticks, "flag_submissions": {f: flag_subs[f] for f in FLAGS},
        "picked_several": sum(several.values()), "picked_several_with_ticks": several[True],
        "clubs": len({r["roster_qid"] for r in rows}),
        "attendance_dates": len(dates), "attendance_first": dates[0] if dates else None,
        "attendance_last": dates[-1] if dates else None,
        "created_first": min(created) if created else None,
        "created_last": max(created) if created else None,
        # one club, one attendance date, more than one row: kept, never collapsed
        "same_club_and_date": {"groups": sum(1 for n in again.values() if n > 1),
                               "rows": sum(n for n in again.values() if n > 1)},
        # no tick on any roster of today's form, yet question 18 holds names: the ticks were
        # taken back, or sat in a question deleted since (Jotform does not serve its answers)
        "no_ticks_but_q18": q18_only,
        # rows whose partner (and so code) is the Roster's only holder of the club's name,
        # because the sync names none: retired, or its rows carry another region or none
        "partner_from_roster": from_roster,
    }
    return rows, no_ticks, counts


# --------------------------------------------------------------------- output
def report(region, c):
    """The counts of one form. Never a name: numbers, dates and flags only."""
    print(f"\n== {region}  form {c['form_id']}")
    gone = sum(c["not_active"].values())
    print(f"   fetched {c['fetched']}   not active, left out {gone}"
          + (f" ({', '.join(f'{k} {v}' for k, v in c['not_active'].items())})" if gone else "")
          + f"   pre-launch, left out {c['pre_launch']}")
    print(f"   submissions in range {c['submissions']}   with ticks {c['with_ticks']}   "
          f"no ticks {c['no_ticks']}   rows {c['rows']}")
    print(f"   distinct clubs {c['clubs']}   distinct attendance dates {c['attendance_dates']}"
          + (f" ({c['attendance_first']} .. {c['attendance_last']})" if c["attendance_dates"] else ""))
    print("   created_at (US Eastern) "
          + (f"{c['created_first']} .. {c['created_last']}" if c["created_first"] else "none"))
    print(f"   several clubs picked in the Club picker: {c['picked_several']} submissions "
          f"({c['picked_several_with_ticks']} of them with ticks)")
    print(f"   one club and one attendance date more than once: {c['same_club_and_date']['groups']} "
          f"groups, {c['same_club_and_date']['rows']} rows - all kept")
    if c["no_ticks_but_q18"]:
        print(f"   ! {len(c['no_ticks_but_q18'])} submission(s) with no tick carry names in question "
              f"{CONTACT_IDS} (ticks taken back, or in a roster question deleted since - look at "
              "them): " + ", ".join(c["no_ticks_but_q18"]))
    if c["partner_from_roster"]:
        print(f"   {c['partner_from_roster']} row(s) of clubs the sync names no partner for (retired, or "
              "their Roster rows carry another region or none): partner and code are the Roster's "
              "only club of that name")
    print("   flags                    rows  submissions")
    for flag in FLAGS:
        print(f"     {flag:<24}{c['flags'][flag]:>5}{c['flag_submissions'][flag]:>13}")
    print(f"   ledger: {c['with_ticks']} with rows + {c['no_ticks']} no ticks = "
          f"{c['submissions']} in range - balanced")


def resolver_commit():
    """The short hash this tool ran at ('-dirty' when tracked files differ), or 'unknown'."""
    def git(*args):
        return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True)
    try:
        head = git("rev-parse", "--short", "HEAD")
        if head.returncode != 0 or not head.stdout.strip():
            return "unknown"
        dirty = git("status", "--porcelain", "--untracked-files=no").stdout.strip()
        return head.stdout.strip() + ("-dirty" if dirty else "")
    except OSError:
        return "unknown"


def below_checkout(full):
    """The steps from this checkout down to `full` (a real path; [] = the checkout itself),
    or None when it is not inside it. The checkout is recognised by WHAT it is
    (os.path.samefile), not by how its path is spelled: on a disk that ignores case, the
    Mac's, another spelling of the path is the same folder. The walk goes up from the
    target, so the part of it that does not exist yet is just steps."""
    steps, at = [], full
    while not (os.path.exists(at) and os.path.samefile(at, REPO)):
        parent = os.path.dirname(at)
        if parent == at:
            return None
        steps.append(os.path.basename(at))
        at = parent
    return steps[::-1]


def under_data(full):
    """`full` (a real path) is under this checkout's data/, which git ignores."""
    return (below_checkout(full) or [""])[0] == "data"


def private_place(path, what):
    """The output holds girls' names: inside this checkout it may only go under data/
    (git-ignored). Anywhere outside the checkout is the operator's choice."""
    full = os.path.realpath(path)
    steps = below_checkout(full)
    if steps is not None and steps[:1] != ["data"]:
        sys.exit(f"{what} holds girls' names and may not be written inside the repository outside "
                 f"data/ (git-ignored): {os.path.join(*steps) if steps else 'the checkout itself'}")
    return full


def shown(path):
    full = os.path.realpath(path)
    steps = below_checkout(full)
    return os.path.join(*steps) if steps else full


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
        f.write("\n")


def main(argv=None, client=None, plan_of=sync_plan):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roster", required=True, metavar="CSV",
                    help="a fresh export of the Roster tab (tools/sheets_client.py export Roster <path>)")
    ap.add_argument("--region", action="append", choices=sorted(forms.REGIONALS),
                    help="only this region (repeatable; default: all four - the loader wants all "
                         "four, so a run of fewer needs --out)")
    ap.add_argument("--out", metavar="PATH",
                    help="the result (default data/backfill_2026-09/resolved.json); it holds names")
    ap.add_argument("--raw-dir", metavar="DIR",
                    help="where the raw copies go, <region>.json each, overwritten (default: raw/ "
                         "beside the result); they hold names")
    args = ap.parse_args(argv)
    if not os.path.exists(args.roster):
        sys.exit(f"No Roster export at {args.roster} - python3 tools/sheets_client.py export Roster <path>")
    regions = list(dict.fromkeys(args.region or forms.REGIONALS))      # one named twice is read once
    out = private_place(args.out or DEFAULT_OUT, "The result")
    default = os.path.realpath(DEFAULT_OUT)
    is_default = out == default or (os.path.exists(out) and os.path.exists(default)
                                    and os.path.samefile(out, default))
    if len(regions) < len(forms.REGIONALS) and is_default:
        sys.exit("--region gives a result without the other forms, and the default path is the file "
                 "the loader reads, with all four: add --out <another path under data/>, or run it "
                 "without --region")
    raw_dir = private_place(args.raw_dir or os.path.join(os.path.dirname(out), "raw"), "A raw copy")
    if client is None:
        api_key = os.environ.get("JOTFORM_API_KEY") or sys.exit(
            "Set JOTFORM_API_KEY in the environment (RUNBOOK, Credentials)")
        client = Client(api_key, retries=3)

    roster = read_roster(args.roster)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"Back-fill resolver (read-only): submissions created from {SINCE} US Eastern onward")
    print(f"Roster: {roster[0]} rows ({shown(args.roster)})   fetched {stamp}")
    result = {"fetched_at_utc": stamp, "resolver_commit": resolver_commit(),
              "roster_export": {"path": shown(args.roster), "rows": roster[0]},
              "forms": {}, "no_ticks": {}, "rows": []}
    for region in regions:
        form_id = forms.REGIONALS[region]
        submissions = fetch_submissions(client, form_id, region)
        write_json(os.path.join(raw_dir, f"{region}.json"),
                   {"fetched_at_utc": stamp, "region": region, "form_id": form_id,
                    "submissions": submissions})
        questions, today = {}, {}
        if submissions:       # an empty form has nothing to resolve: no dry run needed
            questions = client.get(f"/form/{form_id}/questions")
            plan = plan_of(os.path.abspath(args.roster), region, form_id)   # the sync runs in the repo
            today = rosters_today(plan)
            if plan.get("calls"):
                print(f"   note: {region}'s form is not in step with this Roster export "
                      f"({len(plan['calls'])} planned writes, none made) - each roster's Club "
                      "Name is what it sends TODAY")
        rows, no_ticks, counts = resolve(region, form_id, submissions, questions, today, roster)
        result["forms"][region] = counts
        result["no_ticks"][region] = no_ticks
        result["rows"] += rows
        report(region, counts)

    total = {k: sum(c[k] for c in result["forms"].values())
             for k in ("submissions", "pre_launch", "with_ticks", "no_ticks", "rows")}
    if total["with_ticks"] + total["no_ticks"] != total["submissions"] or total["rows"] != len(result["rows"]):
        sys.exit("The ledger does not balance over the forms - no result written")
    write_json(out, result)
    print(f"\nLEDGER: {total['submissions']} submissions in range = {total['with_ticks']} with rows "
          f"({total['rows']} rows) + {total['no_ticks']} with no tick - balanced; "
          f"{total['pre_launch']} pre-launch left out")
    print(f"Wrote {shown(out)} and {len(result['forms'])} raw copies under {shown(raw_dir)} - they "
          "hold girls' names: "
          + ("keep them where they are (data/ is git-ignored)" if under_data(out) and under_data(raw_dir)
             else "they are outside this checkout's data/ - keep them out of any repository"))
    if len(result["forms"]) < len(forms.REGIONALS):
        print(f"   note: {len(result['forms'])} of {len(forms.REGIONALS)} regions - the loader wants "
              "the file with all four (run it without --region)")


if __name__ == "__main__":
    run(main)
