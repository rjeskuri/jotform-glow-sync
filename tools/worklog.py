#!/usr/bin/env python3
"""
The work log behind the monthly invoice: hours per day and what was done.

Hours are reconstructed from Claude Code's session transcripts for this repo
(~/.claude/projects/<this repo's path with '/' as '-'>/*.jsonl), which
timestamp every message in UTC. All sessions are merged into one timeline and
cut into blocks wherever nothing happened for more than 30 minutes. A block
counts only if Ryan wrote at least one message in it, so time an agent works
alone while he is away is not billed. A block belongs to the day it started,
on the clock the Mac showed then; a day's hours are the sum of its blocks,
rounded to the quarter hour.

The Mac's clock moves when Ryan travels, so the zone it was on is recorded in
worklog/timezones.csv (since, zone, evidence): from each `since` instant the
Mac was on that zone. A past day therefore never moves when the Mac does.
`update` refuses when the Mac is on a zone the file does not have yet, or when
a commit's recorded offset disagrees with the file - `zone` records a change.

The log is worklog/worklog.csv (date, hours, blocks, description, source,
zone). `update` rewrites the `auto` rows of the days it computes (the last 14
days by default), keeps a description once written, fills an empty one from
that day's commit subjects, never touches `manual` rows, and never deletes a
day whose transcripts may have expired (Claude Code deletes a session about
30 days after its last activity - run `update` at the end of every working
session).

Usage:
    python3 tools/worklog.py update                      # the last 14 days
    python3 tools/worklog.py update --since 2026-09-01
    python3 tools/worklog.py zone                        # the zone timeline and the Mac's zone now
    python3 tools/worklog.py zone --since 2026-10-02 --zone Europe/London
    python3 tools/worklog.py add --date 2026-09-29 --hours 1.5 --description "Call with the program team"
    python3 tools/worklog.py export --month 2026-09                    # invoice rows to the screen
    python3 tools/worklog.py export --month 2026-09 --rate 60 --out invoice-2026-09.csv
"""
import argparse
import csv
import datetime as dt
import glob
import json
import math
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(REPO, "worklog", "worklog.csv")
ZONES = os.path.join(REPO, "worklog", "timezones.csv")
COLS = ["date", "hours", "blocks", "description", "source", "zone"]
ZONE_COLS = ["since", "zone", "evidence"]
GAP_MINUTES = 30
WINDOW_DAYS = 14     # update's default window: well inside the transcripts' ~30-day life
KEEP_DAYS = 29       # a day this recent still has all its transcripts; older rows are never dropped
UTC = dt.timezone.utc
LOCALTIME = "/etc/localtime"
GITHUB = "GitHub"     # the committer of merges made on github.com: UTC, not evidence of the Mac's zone


def rel(path):
    return os.path.relpath(path, REPO)


def transcripts_dir(repo=REPO):
    """Claude Code keeps a project's sessions under its path with every non-alphanumeric as '-'."""
    return os.path.join(os.path.expanduser("~"), ".claude", "projects", re.sub(r"[^A-Za-z0-9]", "-", repo))


# ------------------------------------------------------------------ zones
def parse_zone(text):
    """'+09:00', '-03:30' or an IANA name like 'Asia/Tokyo' -> a tzinfo."""
    text = (text or "").strip()
    m = re.fullmatch(r"([+-])(\d{2}):(\d{2})", text)
    if m:
        hours, minutes = int(m.group(2)), int(m.group(3))
        if hours > 14 or minutes >= 60:
            raise ValueError(f"{text!r}: not a UTC offset")
        sign = 1 if m.group(1) == "+" else -1
        return dt.timezone(sign * dt.timedelta(hours=hours, minutes=minutes))
    from zoneinfo import ZoneInfo
    try:
        return ZoneInfo(text)
    except (KeyError, ValueError):
        raise ValueError(f"{text!r}: give an offset like +09:00 or a zone name like Asia/Tokyo") from None


def parse_instant(text):
    """An ISO instant with an offset ('...+00:00' or '...Z') -> an aware UTC datetime."""
    when = dt.datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    if when.tzinfo is None:
        raise ValueError(f"{text!r}: give the offset too, e.g. 2026-09-29T12:37:00+00:00")
    return when.astimezone(UTC)


def offset_text(when):
    """The UTC offset of an aware datetime as '+09:00'."""
    minutes = int(when.utcoffset().total_seconds()) // 60
    sign = "+" if minutes >= 0 else "-"
    return f"{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


def read_zones(path=ZONES):
    """[(since UTC, tzinfo, zone text, evidence), ...] in time order; ValueError says what to fix."""
    if not os.path.exists(path):
        raise ValueError(f"{rel(path)} is missing: it records which zone the Mac was on when "
                         "(docs/RUNBOOK.md, 'Work log and invoices')")
    out = []
    with open(path, encoding="utf-8", newline="") as fh:
        for n, r in enumerate(csv.DictReader(fh), start=2):
            try:
                out.append((parse_instant(r["since"] or ""), parse_zone(r["zone"]), r["zone"].strip(),
                            (r.get("evidence") or "").strip()))
            except (ValueError, KeyError, TypeError) as err:
                raise ValueError(f"{rel(path)} line {n}: {err}") from None
    if not out:
        raise ValueError(f"{rel(path)} has no rows")
    if any(a[0] >= b[0] for a, b in zip(out, out[1:])):
        raise ValueError(f"{rel(path)}: the rows must be in time order")
    return out


def zone_at(zones, when):
    """The zone the Mac was on at instant `when` (the latest row with since <= when); None before the first."""
    found = None
    for since, tz, *_ in zones:
        if since > when:
            break
        found = tz
    return found


def system_zone():
    """(tzinfo, IANA name or None, when /etc/localtime last changed or None) - the Mac's own zone,
    whatever TZ the shell sets; the process zone only when /etc/localtime cannot be read."""
    from zoneinfo import ZoneInfo
    try:
        name = os.readlink(LOCALTIME).split("zoneinfo/", 1)[1]
        changed = dt.datetime.fromtimestamp(os.lstat(LOCALTIME).st_mtime, UTC)
        return ZoneInfo(name), name, changed
    except (OSError, IndexError, KeyError, ValueError):
        return dt.datetime.now().astimezone().tzinfo, None, None


def suggest_since(evts, after, now, changed=None, gap_minutes=GAP_MINUTES):
    """A switch instant strictly inside an idle stretch after `after` (the last sign of the old clock):
    when /etc/localtime changed, if nobody was working near it; else the middle of the FIRST idle
    stretch of 6 h or more after `after`, to the hour. A suggestion to check, not a fact."""
    gap = dt.timedelta(minutes=gap_minutes)
    times = [t for t, _ in evts if after < t <= now]
    if changed and after < changed <= now and all(abs(t - changed) > gap for t in times):
        return changed.replace(second=0, microsecond=0)
    stretches = [(a, b) for a, b in zip([after] + times, times + [now]) if b - a >= dt.timedelta(hours=6)]
    if not stretches:
        return now.replace(second=0, microsecond=0)
    a, b = stretches[0]
    mid = a + (b - a) / 2
    hour = mid.replace(minute=0, second=0, microsecond=0)
    return hour if a + gap < hour < b - gap else mid.replace(second=0, microsecond=0)


def mac_zone_problem(zones, sys_tz, sys_name, now, evts, changed=None, gap_minutes=GAP_MINUTES, commits=()):
    """None when the timeline's zone now has the Mac's offset now; otherwise what to run."""
    have = zone_at(zones, now)
    mac = now.astimezone(sys_tz)
    if have is not None and now.astimezone(have).utcoffset() == mac.utcoffset():
        return None
    old_clock = [c for c in commits if c[0] > zones[-1][0] and c[4] != GITHUB and zone_at(zones, c[0]) is not None
                 and c[1] == c[0].astimezone(zone_at(zones, c[0])).utcoffset() != c[0].astimezone(sys_tz).utcoffset()]
    last = max(old_clock, key=lambda c: c[0]) if old_clock else None
    since = suggest_since(evts, last[0] if last else zones[-1][0], now, changed, gap_minutes)
    zone_arg = sys_name or offset_text(mac)
    basis = (f"after the last commit on the old clock ({last[2]}, {last[0]:%Y-%m-%d %H:%M}Z)" if last
             else f"after {zones[-1][0]:%Y-%m-%d %H:%M}Z")
    note = ""
    if sys_name is None and os.environ.get("TZ"):
        note = (f"\n(/etc/localtime could not be read, so the shell's TZ={os.environ['TZ']} was used "
                "as the Mac's zone.)")
    return (f"The Mac is on {zone_arg} ({offset_text(mac)}), but {rel(ZONES)} has "
            f"{zones[-1][2]} since {zones[-1][0]:%Y-%m-%d %H:%M}Z.\n"
            "Record when the Mac switched - any moment between your last session on the old clock "
            "and the first on the new one gives the same hours. Suggested (the clock change, or the "
            f"first long idle stretch {basis}; check it):\n"
            f"  python3 tools/worklog.py zone --since {since:%Y-%m-%dT%H:%M}+00:00 --zone {zone_arg}{note}")


# ------------------------------------------------------------ transcripts
def is_ryans_message(entry):
    """A message Ryan typed: not a tool result, a task notification, a skill load or a summary."""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isCompactSummary"):
        return False
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content.strip()) and not content.lstrip().startswith("<")
    if isinstance(content, list):
        texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
        return any(t.strip() and not t.lstrip().startswith("<") for t in texts)
    return False


def events(paths):
    """(UTC datetime, is Ryan's message) for every user/assistant entry in the transcripts."""
    out = []
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                stamp = entry.get("timestamp")
                if entry.get("type") not in ("user", "assistant") or not stamp:
                    continue
                when = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(UTC)
                out.append((when, is_ryans_message(entry)))
    return sorted(out, key=lambda e: e[0])


def activity_blocks(evts, gap_minutes=GAP_MINUTES):
    """[(start, end), ...]: runs of events with no pause over gap_minutes, whatever the clock says,
    kept only when they hold one of Ryan's messages."""
    gap = dt.timedelta(minutes=gap_minutes)
    runs, cur = [], []
    for e in sorted(evts, key=lambda e: e[0]):
        if cur and e[0] - cur[-1][0] > gap:
            runs.append(cur)
            cur = []
        cur.append(e)
    if cur:
        runs.append(cur)
    return [(r[0][0], r[-1][0]) for r in runs if any(h for _, h in r)]


def day_blocks(evts, zones, gap_minutes=GAP_MINUTES):
    """{date: [(start, end), ...]} - each block on the Mac's clock when it started, under the date it
    started on (a session past midnight stays on its first day). Blocks before the timeline are left out."""
    out = {}
    for start, end in activity_blocks(evts, gap_minutes):
        tz = zone_at(zones, start)
        if tz is None:
            continue
        s, e = start.astimezone(tz), end.astimezone(tz)
        out.setdefault(s.date(), []).append((s, e))
    return out


def day_hours(blocks):
    """Sum of the blocks, to the nearest quarter hour; at least 0.25 for a day with work."""
    minutes = sum((end - start).total_seconds() for start, end in blocks) / 60
    return max(0.25, math.floor(minutes / 15 + 0.5) * 0.25)


def zones_text(blocks):
    """The offsets a day's blocks are written in, in order: '+03:00', or '+08:00/+09:00' on a travel day."""
    seen = []
    for s, _ in blocks:
        if offset_text(s) not in seen:
            seen.append(offset_text(s))
    return "/".join(seen)


def blocks_text(blocks):
    """'09:00-09:45, 14:00-14:10'; each block carries its offset when the day has more than one."""
    mixed = "/" in zones_text(blocks)
    return ", ".join(f"{s:%H:%M}-{e:%H:%M}" + (f" ({offset_text(s)})" if mixed else "") for s, e in blocks)


# -------------------------------------------------------------------- git
def git_commits(repo=REPO):
    """[(UTC instant, recorded offset, short hash, subject, committer name), ...], newest first."""
    try:
        text = subprocess.run(["git", "-C", repo, "log", "--format=%H%x09%aI%x09%cn%x09%s"],
                              capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    out = []
    for line in text.splitlines():
        parts = line.split("\t", 3)
        if len(parts) < 4:
            continue
        sha, stamp, committer, subject = parts
        when = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        out.append((when.astimezone(UTC), when.utcoffset(), sha[:7], subject.strip(), committer))
    return out


def subjects_by_day(commits, zones):
    """{'yyyy-mm-dd': [subjects, newest first]} - each commit on the Mac's clock when it was made."""
    out = {}
    for when, _, _, subject, _ in commits:
        tz = zone_at(zones, when)
        if tz is not None:
            out.setdefault(when.astimezone(tz).date().isoformat(), []).append(subject)
    return out


def commit_problems(commits, zones, start, ignore=()):
    """Commits made here from `start` on whose recorded offset disagrees with the timeline - a trip
    that was never recorded. Merges made on GitHub (UTC) are not evidence and are skipped."""
    bad = []
    for when, offset, sha, subject, committer in commits:
        if when < start or committer == GITHUB or any(sha.startswith(i[:7]) for i in ignore):
            continue
        tz = zone_at(zones, when)
        if tz is not None and when.astimezone(tz).utcoffset() != offset:
            bad.append(f"{sha} {when:%Y-%m-%d %H:%M}Z was made on {offset_text(when.astimezone(dt.timezone(offset)))}, "
                       f"the timeline says {offset_text(when.astimezone(tz))} ({subject[:60]})")
    return bad


def since_problems(since, new_tz, zones, evts, commits, now, gap_minutes=GAP_MINUTES):
    """Why `since` cannot be where the Mac switched to new_tz (empty when it can)."""
    out = []
    if since > now:
        out.append(f"{since:%Y-%m-%d %H:%M}Z is in the future")
    if since <= zones[-1][0]:
        out.append(f"{since:%Y-%m-%d %H:%M}Z is not after the last row ({zones[-1][0]:%Y-%m-%d %H:%M}Z); "
                   f"edit {rel(ZONES)} by hand to correct an older row")
    gap = dt.timedelta(minutes=gap_minutes)
    near = [t for t, _ in evts if abs(t - since) <= gap]
    if near:
        out.append(f"{since:%Y-%m-%d %H:%M}Z falls inside a session (activity {near[0]:%H:%M}Z-"
                   f"{near[-1]:%H:%M}Z): pick a moment when nobody was working")
    for when, offset, sha, _, committer in commits:
        old = zone_at(zones, when)
        if (when >= since and committer != GITHUB and old is not None
                and offset == when.astimezone(old).utcoffset() != when.astimezone(new_tz).utcoffset()):
            out.append(f"commit {sha} at {when:%Y-%m-%d %H:%M}Z was made on the old clock: the switch came after it")
            break
    return out


# -------------------------------------------------------------------- log
def merge(rows, computed, subjects, drop=()):
    """
    rows: the log's rows (dicts); computed: {'yyyy-mm-dd': (hours, blocks_text, zones_text)}.
    Auto rows of computed days are updated (a written description is kept, an empty one filled from
    commit subjects); auto rows of the `drop` days are removed; manual rows and other days stay.
    """
    auto = {r["date"]: r for r in rows if r.get("source") == "auto" and r["date"] not in drop}
    for day, (hours, blocks, zones) in computed.items():
        row = auto.get(day) or {"date": day, "description": "", "source": "auto"}
        row["hours"] = f"{hours:.2f}"
        row["blocks"] = blocks
        row["zone"] = zones
        if not row.get("description", "").strip():
            row["description"] = "; ".join(reversed(subjects.get(day, [])))
        auto[day] = row
    manual = [r for r in rows if r.get("source") != "auto"]
    return sorted(list(auto.values()) + manual, key=lambda r: (r["date"], r.get("source") != "auto"))


def edge_problem(rows, computed_all, since):
    """The day before --since is not recomputed; refuse when its log row would change (work moved
    across the window's edge), unless the log never covered that day."""
    auto = {r["date"]: r for r in rows if r.get("source") == "auto"}
    edge = (since - dt.timedelta(days=1)).isoformat()
    if not auto or edge < min(auto):
        return None
    logged = auto.get(edge)
    now = computed_all.get(edge)
    was = (logged["hours"], logged["blocks"]) if logged else None
    becomes = (f"{now[0]:.2f}", now[1]) if now else None
    if was == becomes:
        return None
    return (f"{edge}, the day before --since, would change ({was or 'no row'} -> {becomes or 'no work'}): "
            "re-run with an earlier --since")


def stale_days(rows, computed, since, today, custom_folder):
    """(droppable, kept): auto rows from --since on that no longer have any work. Only days of the
    last KEEP_DAYS, read from this repo's own transcripts, may go - older ones may just have expired."""
    stale = sorted(r["date"] for r in rows
                   if r.get("source") == "auto" and r["date"] >= since.isoformat() and r["date"] not in computed)
    floor = max(since, today - dt.timedelta(days=KEEP_DAYS)).isoformat()
    droppable = [d for d in stale if d >= floor and not custom_folder]
    return droppable, [d for d in stale if d not in droppable]


def invoice_rows(rows, month, rate=None):
    """One row per day of the month (hours summed, descriptions joined) and a total row."""
    days = {}
    for r in rows:
        if not r["date"].startswith(month + "-"):
            continue
        d = days.setdefault(r["date"], {"hours": 0.0, "desc": []})
        d["hours"] += float(r["hours"] or 0)
        if r.get("description", "").strip():
            d["desc"].append(r["description"].strip())
    header = ["Date", "Hours", "Description"] + (["Amount"] if rate is not None else [])
    out, total = [header], 0.0
    for day in sorted(days):
        h = days[day]["hours"]
        total += h
        line = [day, f"{h:.2f}", " / ".join(days[day]["desc"])]
        if rate is not None:
            line.append(f"{h * rate:.2f}")
        out.append(line)
    tail = ["Total", f"{total:.2f}", ""] + ([f"{total * rate:.2f}"] if rate is not None else [])
    return out + [tail]


def read_log(path=LOG):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def write_log(rows, path=LOG):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def append_zone(since, zone_text, evidence, path=ZONES):
    with open(path, "a", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerow([since.isoformat(), zone_text, evidence])


def a_date(text):
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r}: give a date like 2026-09-28")


def transcript_events(folder):
    paths = sorted(glob.glob(os.path.join(folder, "*.jsonl")))
    if not paths:
        sys.exit(f"no session transcripts in {folder}")
    return events(paths)


def main():
    ap = argparse.ArgumentParser(description="The work log behind the monthly invoice "
                                             "(worklog/worklog.csv).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    up = sub.add_parser("update", help="recompute hours from the session transcripts")
    up.add_argument("--since", type=a_date, help=f"first day to recompute (default: {WINDOW_DAYS} days ago)")
    up.add_argument("--gap-minutes", type=int, default=GAP_MINUTES,
                    help="a longer pause ends a block (default 30)")
    up.add_argument("--transcripts", default=None, help="default: this repo's Claude Code project folder "
                                                        "(another folder never drops rows)")
    up.add_argument("--drop-stale", action="store_true",
                    help="remove auto rows of recent days that no longer have any work")
    up.add_argument("--ignore-commit", action="append", default=[], metavar="HASH",
                    help="leave this commit out of the time-zone check (repeatable)")
    zn = sub.add_parser("zone", help="show the zone timeline, or record where the Mac switched zone")
    zn.add_argument("--since", help="when the Mac switched: an ISO instant with offset, or a date "
                                    "(midnight on the new clock)")
    zn.add_argument("--zone", help="the new zone: an IANA name like Asia/Tokyo, or an offset like +09:00")
    zn.add_argument("--evidence", default="", help="why you know (default: 'recorded <today>')")
    zn.add_argument("--gap-minutes", type=int, default=GAP_MINUTES)
    zn.add_argument("--transcripts", default=None, help="default: this repo's Claude Code project folder")
    add = sub.add_parser("add", help="add a manual row (work outside Claude Code)")
    add.add_argument("--date", type=a_date, required=True)
    add.add_argument("--hours", type=float, required=True)
    add.add_argument("--description", required=True)
    ex = sub.add_parser("export", help="the invoice rows for one month")
    ex.add_argument("--month", required=True, help="yyyy-mm")
    ex.add_argument("--rate", type=float, help="hourly rate: adds an Amount column")
    ex.add_argument("--out", help="write a CSV here (default: print)")
    args = ap.parse_args()

    if args.cmd in ("update", "zone"):
        try:
            zones = read_zones()
        except ValueError as err:
            sys.exit(str(err))
        now = dt.datetime.now(UTC)
        sys_tz, sys_name, changed = system_zone()
        folder = args.transcripts or transcripts_dir()

    if args.cmd == "update":
        evts = transcript_events(folder)
        commits = git_commits()
        problem = mac_zone_problem(zones, sys_tz, sys_name, now, evts, changed, args.gap_minutes, commits)
        if problem:
            sys.exit(problem)
        today = now.astimezone(sys_tz).date()
        since = args.since or (today - dt.timedelta(days=WINDOW_DAYS))
        start = dt.datetime.combine(since, dt.time(), UTC) - dt.timedelta(hours=14)   # the earliest zone
        early = [s for s, _ in activity_blocks(evts, args.gap_minutes) if s >= start and zone_at(zones, s) is None]
        if early:
            sys.exit(f"work at {early[0]:%Y-%m-%d %H:%M}Z predates {rel(ZONES)}: add an earlier row")
        bad = commit_problems(commits, zones, start, args.ignore_commit)
        if bad:
            sys.exit(f"commits disagree with {rel(ZONES)} - a zone change is missing or wrong:\n  "
                     + "\n  ".join(bad) + "\nFix the timeline with `zone`, or leave a stray commit out "
                     "with --ignore-commit HASH.")
        days = day_blocks(evts, zones, args.gap_minutes)
        computed_all = {d.isoformat(): (day_hours(b), blocks_text(b), zones_text(b)) for d, b in days.items()}
        computed = {d: v for d, v in computed_all.items() if d >= since.isoformat()}
        rows = read_log()
        problem = edge_problem(rows, computed_all, since)
        if problem:
            sys.exit(problem)
        droppable, kept = stale_days(rows, computed, since, today, bool(args.transcripts))
        old = {r["date"]: r for r in rows if r.get("source") == "auto"}
        if droppable and not args.drop_stale:
            sys.exit("these auto rows no longer have any work (their hours moved to another day):\n"
                     + "".join(f"  {d}  {old[d]['hours']} h  {old[d].get('description', '')[:90]}\n" for d in droppable)
                     + "re-run with --drop-stale to remove them; move a written description to its new day by hand")
        write_log(merge(rows, computed, subjects_by_day(commits, zones), drop=droppable))
        for day in sorted(computed):
            hours, text, zone = computed[day]
            note = "description kept" if old.get(day, {}).get("description", "").strip() else "description from commits"
            print(f"  {day}  {hours:5.2f} h   {text}  [{zone}]   ({note})")
        for d in droppable:
            print(f"  {d}  dropped (was {old[d]['hours']} h): {old[d].get('description', '')}")
        for d in kept:
            print(f"  {d}  kept - no work found, but its transcripts may have expired ({old[d]['hours']} h)")
        print(f"{len(computed)} day(s) since {since} updated in {rel(LOG)}")
    elif args.cmd == "zone":
        if not args.since and not args.zone:
            mac = now.astimezone(sys_tz)
            print(f"The Mac's zone now: {sys_name or offset_text(mac)} ({offset_text(mac)})"
                  + (f"; {LOCALTIME} last changed {changed:%Y-%m-%d %H:%M}Z" if changed else ""))
            print(f"Timeline ({rel(ZONES)}):")
            for since, _, text, evidence in zones:
                print(f"  since {since:%Y-%m-%d %H:%M}Z  {text:<16} {evidence}")
            recent = [c for c in git_commits() if c[0] >= zones[-1][0] and c[4] != GITHUB]
            by_offset = {}
            for when, offset, *_ in recent:
                by_offset.setdefault(offset_text(when.astimezone(dt.timezone(offset))), []).append(when)
            print(f"Commit offsets since the last row: "
                  + (", ".join(f"{o} x{len(w)} ({min(w):%m-%d}..{max(w):%m-%d})" for o, w in by_offset.items())
                     or "no commits yet"))
            if zone_at(zones, now) is not None and now.astimezone(zone_at(zones, now)).utcoffset() == mac.utcoffset():
                print("OK: the Mac's zone matches the timeline.")
            else:
                print(mac_zone_problem(zones, sys_tz, sys_name, now, transcript_events(folder), changed,
                                       args.gap_minutes, git_commits()))
            return
        if not (args.since and args.zone):
            sys.exit("give both --since and --zone (or neither, to see the timeline)")
        try:
            new_tz = parse_zone(args.zone)
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.since.strip()):
                since = dt.datetime.combine(dt.date.fromisoformat(args.since.strip()), dt.time(),
                                            new_tz).astimezone(UTC)
            else:
                since = parse_instant(args.since)
        except ValueError as err:
            sys.exit(str(err))
        problems = since_problems(since, new_tz, zones, transcript_events(folder), git_commits(), now,
                                  args.gap_minutes)
        if problems:
            sys.exit("not recorded:\n  " + "\n  ".join(problems))
        evidence = args.evidence.strip() or f"recorded {now.astimezone(sys_tz):%Y-%m-%d}"
        append_zone(since, args.zone.strip(), evidence)
        first = min(since.astimezone(zones[-1][1]).date(), since.astimezone(new_tz).date())
        print(f"recorded: from {since:%Y-%m-%d %H:%M}Z the Mac was on {args.zone.strip()}")
        print(f"now run: python3 tools/worklog.py update --since {first}")
    elif args.cmd == "add":
        if not 0 < args.hours <= 24:
            sys.exit("--hours must be between 0 and 24")
        rows = read_log() + [{"date": args.date.isoformat(), "hours": f"{args.hours:.2f}", "blocks": "",
                              "description": args.description.strip(), "source": "manual", "zone": ""}]
        write_log(sorted(rows, key=lambda r: (r["date"], r.get("source") != "auto")))
        print(f"added {args.hours:.2f} h on {args.date} (manual)")
    else:
        if not re.fullmatch(r"\d{4}-\d{2}", args.month):
            sys.exit("--month: give yyyy-mm, e.g. 2026-09")
        rows = invoice_rows(read_log(), args.month, args.rate)
        if args.out:
            with open(args.out, "w", encoding="utf-8", newline="") as fh:
                csv.writer(fh).writerows(rows)
            print(f"wrote {len(rows) - 2} day(s) to {args.out}; total {rows[-1][1]} h")
        else:
            for r in rows:
                print("  ".join(r))


if __name__ == "__main__":
    main()
