#!/usr/bin/env python3
"""
Back-fill the ReviewQueue with problem reports that asked for a roster change
before 2026-09-28, when handleFeedback_ started queuing them itself
(docs/plans/2026-09-28-problem-report-followup.md).

It runs the Apps Script's own looksLikeRosterChange_ and feedbackReviewItem_
(appsscript/FormHandlers.gs, through Node) on the Feedback tab, so each row it
adds is exactly what the handler would have added, and review_ recognises it
later by issue | partner | club | [#Feedback!N]. A report already on the queue
(open or resolved) is skipped, so running it twice adds nothing.

It prints sheet rows, yes/no and counts only - problem reports name girls.

Usage:
    python3 tools/backfill_feedback_review.py                        # dry run, Feedback rows 4-12
    python3 tools/backfill_feedback_review.py --rows 4-12 --apply
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEEDBACK_TAB = "Feedback"   # the live tab name: the handler's source is "<tab>!<row>"

# Node side: the .gs code decides; Python only reads and writes the sheet.
NODE = r"""
const loadGs = require('./test/load_gs');
const gs = loadGs(['looksLikeRosterChange_', 'feedbackReviewItem_', 'tidy_', 'key_'],
                  ['Config.gs', 'Normalize.gs', 'FormHandlers.gs']);
const d = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const tagOf = detail => { const m = String(detail || '').match(/\[#([^\]]*)\]\s*$/); return m ? m[1] : ''; };
// A Feedback!N tag names one report, so issue + tag is enough - and a report already on
// the queue, open OR resolved, is never queued again (a back-fill has no reason to).
const identity = (issue, tag) => gs.key_(issue) + '||' + tag;
const onQueue = new Set(d.review.filter(r => gs.tidy_(r[1])).map(r => identity(r[1], tagOf(r[4]))));
const partners = new Set(d.clubs.map(r => gs.key_(r[1])).filter(Boolean));
const clubs = new Set(d.clubs.map(r => gs.key_(r[2])).filter(Boolean));
const onFile = (v, set) => (gs.tidy_(v) ? (set.has(gs.key_(v)) ? 'on file' : 'not on file') : 'blank');
const out = d.reports.map(rep => {
  try {
    const a = {};
    d.header.forEach((h, i) => { a[gs.tidy_(h)] = rep.values[i] === undefined ? '' : rep.values[i]; });
    const reason = gs.looksLikeRosterChange_(a);
    if (!reason) return { row: rep.row, reason: 'no' };
    const source = d.tab + '!' + rep.row;
    const it = gs.feedbackReviewItem_(a, source, rep.day, reason);
    const id = identity(it.issue, it.dedupeKey);
    const res = { row: rep.row, reason, partner: onFile(it.partner, partners), club: onFile(it.club, clubs) };
    if (onQueue.has(id)) return Object.assign(res, { skip: 'already on the ReviewQueue' });
    onQueue.add(id);   // a duplicate within this batch is skipped too
    return Object.assign(res, { append: [rep.day, it.issue, it.partner, it.club,
      it.detail + ' (back-filled ' + d.today + ') [#' + it.dedupeKey + ']', ''] });
  } catch (err) {
    return { row: rep.row, error: err.name };   // never the message: it could quote the row
  }
});
process.stdout.write(JSON.stringify(out));
"""


def parse_rows(spec):
    lo, _, hi = spec.partition("-")
    lo, hi = int(lo), int(hi or lo)
    if lo < 2 or hi < lo:
        sys.exit(f"--rows {spec}: give sheet rows like 4-12 (row 1 is the header)")
    return list(range(lo, hi + 1))


def report_day(stamp):
    """The Timestamp cell as the export shows it (M/D/YYYY H:MM:SS, sheet zone) -> YYYY-MM-DD."""
    try:
        return dt.datetime.strptime(stamp.strip().split(" ")[0], "%m/%d/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def main():
    ap = argparse.ArgumentParser(description="Back-fill ReviewQueue items for problem reports "
                                             "that asked for a roster change (dry run by default).")
    ap.add_argument("--rows", default="4-12", help="Feedback sheet rows, e.g. 4-12 (default)")
    ap.add_argument("--apply", action="store_true", help="append the rows (default: dry run)")
    args = ap.parse_args()
    rows = parse_rows(args.rows)

    sys.path.insert(0, os.path.join(REPO, "tools"))
    import sheets_client as sc   # noqa: E402  (only now: --help needs no credentials)
    svc = sc.service()
    feedback = sc.read_tab(svc, FEEDBACK_TAB)
    formlog = sc.read_tab(svc, "FormLog")
    review = sc.read_tab(svc, "ReviewQueue")
    clubs = sc.read_tab(svc, "ClubRegistry")
    if not feedback or not review:
        sys.exit("Feedback or ReviewQueue tab is empty or missing")

    reports = []
    for n in rows:
        if n > len(feedback) or not any(c.strip() for c in feedback[n - 1]):
            sys.exit(f"{FEEDBACK_TAB}!{n}: no such report")
        logged = [r for r in formlog[1:] if r[1] == "FEEDBACK" and str(r[2]).strip() == str(n)]
        if not logged or logged[-1][4].startswith("ERROR:"):
            sys.exit(f"{FEEDBACK_TAB}!{n}: FormLog has no successful run of it - that is the menu's "
                     "job (Process any missed form responses), not this back-fill")
        day = report_day(feedback[n - 1][0])
        if not day:
            sys.exit(f"{FEEDBACK_TAB}!{n}: could not read its Timestamp")
        reports.append({"row": n, "values": feedback[n - 1], "day": day})

    zone = svc.spreadsheets().get(spreadsheetId=sc.spreadsheet_id(),
                                  fields="properties.timeZone").execute()["properties"]["timeZone"]
    from zoneinfo import ZoneInfo
    now = dt.datetime.now(ZoneInfo(zone))
    payload = {"header": feedback[0], "reports": reports, "review": review[1:], "clubs": clubs[1:],
               "tab": FEEDBACK_TAB, "today": now.strftime("%Y-%m-%d")}
    done = subprocess.run(["node", "-e", NODE], cwd=REPO, input=json.dumps(payload),
                          capture_output=True, text=True)
    if done.returncode != 0:
        sys.exit("the .gs classifier could not run (node exit %d)" % done.returncode)
    result = json.loads(done.stdout)

    to_add = []
    for r in result:
        where = f"{FEEDBACK_TAB}!{r['row']}"
        day = next(x["day"] for x in reports if x["row"] == r["row"])
        if r.get("error"):
            print(f"  {where:12} {day}  could not classify ({r['error']})")
        elif r["reason"] == "no":
            print(f"  {where:12} {day}  roster change: no")
        else:
            action = "already on the ReviewQueue - skipped" if r.get("skip") else "append"
            print(f"  {where:12} {day}  roster change: {r['reason']:4}  partner {r['partner']:11}  "
                  f"club {r['club']:11}  -> {action}")
            if r.get("append"):
                to_add.append((where, r["append"]))
    if any(r.get("error") for r in result):
        sys.exit("some reports could not be classified: nothing written")
    print(f"{len(result)} report(s) read, {len(to_add)} to add to the ReviewQueue")

    if not args.apply:
        print(f"DRY RUN - would append {len(to_add)} row(s); re-run with --apply to write")
        return
    if not to_add:
        print("nothing to write")
        return
    sc.append_rows(svc, "ReviewQueue", [row for _, row in to_add])
    after = sc.read_tab(svc, "ReviewQueue")
    for where, row in to_add:
        hits = [r for r in after[1:] if r[1] == row[1] and r[4].endswith("[#" + where + "]")
                and not r[5].strip()]
        if len(hits) != 1:
            sys.exit(f"re-read: {where} is on the ReviewQueue {len(hits)} time(s), expected once - check the tab")
    sc.append_rows(svc, "Audit", [[now.strftime("%Y-%m-%d %H:%M:%S"), "backfillFeedbackReview",
                                   f"added {len(to_add)} item(s): " + ", ".join(w for w, _ in to_add)]])
    print(f"appended {len(to_add)} row(s), each re-read once on the ReviewQueue; Audit row added")


if __name__ == "__main__":
    main()
