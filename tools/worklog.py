#!/usr/bin/env python3
"""
The work log behind the monthly invoice: hours per day and what was done.

Hours are reconstructed from Claude Code's session transcripts for this repo
(~/.claude/projects/<this repo's path with '/' as '-'>/*.jsonl), which
timestamp every message: all sessions are merged, split by local calendar
day, and cut into blocks wherever nothing happened for more than 30 minutes.
A block counts only if Ryan wrote at least one message in it, so time an
agent works alone while he is away is not billed. A day's hours are the sum
of its blocks, rounded to the quarter hour.

The log is worklog/worklog.csv (date, hours, blocks, description, source).
`update` rewrites the `auto` rows for the days it can see, keeps a
description once written, fills an empty one from that day's commit
subjects, and never touches `manual` rows or days whose transcripts have
expired (Claude Code deletes them after 30 days by default - run `update`
at least every few weeks, and at the end of every working session).

Usage:
    python3 tools/worklog.py update                      # the last 30 days
    python3 tools/worklog.py update --since 2026-09-01
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
COLS = ["date", "hours", "blocks", "description", "source"]
GAP_MINUTES = 30


def transcripts_dir(repo=REPO):
    """Claude Code keeps a project's sessions under its path with every non-alphanumeric as '-'."""
    return os.path.join(os.path.expanduser("~"), ".claude", "projects", re.sub(r"[^A-Za-z0-9]", "-", repo))


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
    """(local datetime, is Ryan's message) for every user/assistant entry in the transcripts."""
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
                when = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone()
                out.append((when, is_ryans_message(entry)))
    return sorted(out, key=lambda e: e[0])


def day_blocks(evts, gap_minutes=GAP_MINUTES):
    """{date: [(start, end), ...]} — only the blocks that hold one of Ryan's messages."""
    by_day = {}
    for when, human in evts:
        by_day.setdefault(when.date(), []).append((when, human))
    gap = dt.timedelta(minutes=gap_minutes)
    out = {}
    for day, items in by_day.items():
        items.sort(key=lambda e: e[0])
        blocks, cur = [], [items[0]]
        for e in items[1:]:
            if e[0] - cur[-1][0] > gap:
                blocks.append(cur)
                cur = [e]
            else:
                cur.append(e)
        blocks.append(cur)
        kept = [(b[0][0], b[-1][0]) for b in blocks if any(h for _, h in b)]
        if kept:
            out[day] = kept
    return out


def day_hours(blocks):
    """Sum of the blocks, to the nearest quarter hour; at least 0.25 for a day with work."""
    minutes = sum((end - start).total_seconds() for start, end in blocks) / 60
    return max(0.25, math.floor(minutes / 15 + 0.5) * 0.25)


def blocks_text(blocks):
    return ", ".join(f"{s:%H:%M}-{e:%H:%M}" for s, e in blocks)


def git_subjects(repo=REPO):
    """{'yyyy-mm-dd': [commit subjects]} in local time."""
    try:
        text = subprocess.run(["git", "-C", repo, "log", "--date=format-local:%Y-%m-%d",
                               "--format=%ad%x09%s"], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return {}
    out = {}
    for line in text.splitlines():
        day, _, subject = line.partition("\t")
        out.setdefault(day, []).append(subject.strip())
    return out


def merge(rows, computed, subjects):
    """
    rows: the log's rows (dicts); computed: {'yyyy-mm-dd': (hours, blocks_text)}.
    Auto rows of computed days are updated (a written description is kept, an
    empty one filled from commit subjects); manual rows and other days stay.
    """
    auto = {r["date"]: r for r in rows if r.get("source") == "auto"}
    for day, (hours, blocks) in computed.items():
        row = auto.get(day) or {"date": day, "description": "", "source": "auto"}
        row["hours"] = f"{hours:.2f}"
        row["blocks"] = blocks
        if not row.get("description", "").strip():
            row["description"] = "; ".join(reversed(subjects.get(day, [])))
        auto[day] = row
    manual = [r for r in rows if r.get("source") != "auto"]
    return sorted(list(auto.values()) + manual, key=lambda r: (r["date"], r.get("source") != "auto"))


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


def a_date(text):
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r}: give a date like 2026-09-28")


def main():
    ap = argparse.ArgumentParser(description="The work log behind the monthly invoice "
                                             "(worklog/worklog.csv).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    up = sub.add_parser("update", help="recompute hours from the session transcripts")
    up.add_argument("--since", type=a_date, help="first day to recompute (default: 30 days ago)")
    up.add_argument("--gap-minutes", type=int, default=GAP_MINUTES,
                    help="a longer pause ends a block (default 30)")
    up.add_argument("--transcripts", default=None, help="default: this repo's Claude Code project folder")
    add = sub.add_parser("add", help="add a manual row (work outside Claude Code)")
    add.add_argument("--date", type=a_date, required=True)
    add.add_argument("--hours", type=float, required=True)
    add.add_argument("--description", required=True)
    ex = sub.add_parser("export", help="the invoice rows for one month")
    ex.add_argument("--month", required=True, help="yyyy-mm")
    ex.add_argument("--rate", type=float, help="hourly rate: adds an Amount column")
    ex.add_argument("--out", help="write a CSV here (default: print)")
    args = ap.parse_args()

    if args.cmd == "update":
        since = args.since or (dt.date.today() - dt.timedelta(days=30))
        folder = args.transcripts or transcripts_dir()
        paths = sorted(glob.glob(os.path.join(folder, "*.jsonl")))
        if not paths:
            sys.exit(f"no session transcripts in {folder}")
        blocks = {d: b for d, b in day_blocks(events(paths), args.gap_minutes).items() if d >= since}
        computed = {d.isoformat(): (day_hours(b), blocks_text(b)) for d, b in blocks.items()}
        before = {r["date"]: r.get("description", "") for r in read_log() if r.get("source") == "auto"}
        rows = merge(read_log(), computed, git_subjects())
        write_log(rows)
        for day in sorted(computed):
            hours, text = computed[day]
            note = "description kept" if before.get(day, "").strip() else "description from commits"
            print(f"  {day}  {hours:5.2f} h   {text}   ({note})")
        print(f"{len(computed)} day(s) since {since} updated in {os.path.relpath(LOG, REPO)}")
    elif args.cmd == "add":
        if not 0 < args.hours <= 24:
            sys.exit("--hours must be between 0 and 24")
        rows = read_log() + [{"date": args.date.isoformat(), "hours": f"{args.hours:.2f}", "blocks": "",
                              "description": args.description.strip(), "source": "manual"}]
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
