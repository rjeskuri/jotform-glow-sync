#!/usr/bin/env python3
"""
Deactivate clubs in the Roster tab - every active row of the chosen clubs set
inactive with today's removed_date - and put the same rows back with --undo.

A club leaves the attendance forms when its rows are inactive: the sync
retires its roster question (hidden, off the Club picker), and the girls'
ids and the ClubRegistry row stay for the day it comes back (Ids.gs finds the
code by partner + club). Deactivating by hand is two cells per girl and no
record; the 2026-09-28 and 09-30 deactivations used scratch scripts with a
re-read. This is the command instead: the plan, a guard, one batch, a
re-read, an Audit row, and a folder --undo reads back.

The guard. Before anything is planned, the region's attendance form's
submissions since 2026-09-01 are read (JOTFORM_API_KEY) and matched to the
chosen clubs by question 5 and the Club picker's answer: key equality, or
"<club> - <partner>" (glow.sync.SF_NAME_SEP) - never a bare prefix, or
'QUEENS' would be credited with 'Queens of Quest'. A club named in the last
--recent-days (30) stops the run unless --deactivate-anyway. --check-only
prints the counts per partner and club and stops there (the double-check of
docs/plans/2026-10-06-clubs-off-jotform.md, B). Counts, days and club names
only: nothing else of a submission is read out.

What --apply writes:
  Roster   status -> inactive, removed_date -> today in the sheet's zone (the
           text the Apps Script writes) on every ACTIVE row of the clubs
  Audit    one row, deactivateRows: counts and the --reason text
Not touched: ClubRegistry (the code is immutable), SF Pending, the Partners
tab, the forms. The template's next sync retires the rosters; a regional form
whose clubs all leave is disabled first (tools/disable_form.py) and never
synced down to an empty Club picker.

Before the write the Roster tab is saved to data/deactivate_clubs/<stamp>/
Roster.csv and the rows with their old values to written.json beside it; the
tab is re-read and the run stops, nothing written, if a planned row changed
or a club gained an active row (a Club Roster Form submission in between).
After the write every row is re-read and compared, and the two columns are
checked unchanged everywhere else.

    python3 tools/deactivate_clubs.py --region U.S --reason "<why>"           # dry run
    python3 tools/deactivate_clubs.py --partner "Demo Partner" --check-only   # the counts, nothing planned
    python3 tools/deactivate_clubs.py --partner "Demo Partner" --club "Sunrise Club" --reason "<why>" --apply
    python3 tools/deactivate_clubs.py --undo data/deactivate_clubs/<stamp>    # dry run of the way back
    python3 tools/deactivate_clubs.py --undo data/deactivate_clubs/<stamp> --apply

--undo puts back exactly the rows written.json names (status and removed_date
as they were) with the same shape - stale check, one batch, re-read, Audit
row reactivateRows - and refuses, naming them, when one of those rows has
changed since (a reactivation through the Club Roster Form, a move).

Afterwards (docs/RUNBOOK.md, "Deactivating a club"): in the sheet, GLOW ->
Google Forms -> Update form dropdowns from the Roster, so the Club Roster
Form stops offering the clubs; export the Roster; the template's sync dry run
plans the retirements.
"""
import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sheets_client as sc  # noqa: E402
from rename_club import a1, cell, cell_key, col_letter, describe_rows, nfc_key, tidy, trimmed  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow import forms as glow_forms      # noqa: E402
from glow.cli import run                  # noqa: E402
from glow.jotform import Client           # noqa: E402
from glow.sync import CLUB_NAME, PICKER_NAME, SF_NAME_SEP   # noqa: E402
from glow.text import key                 # noqa: E402

ROSTER, AUDIT = "Roster", "Audit"
ACTIVE, INACTIVE = "active", "inactive"           # Config.gs STATUS, as the handlers write them
OUT = os.path.join(REPO, "data", "deactivate_clubs")
SINCE = "2026-09-01 00:00:00"      # the forms went live; created_at as Jotform gives it (US Eastern)
RECENT_DAYS = 30
PAGE = 1000                        # submissions per request (Jotform's maximum)


def matches(value, club):
    """Whether a submitted text (question 5, or one Club picker pick) names `club`:
    the same text by glow.text.key, or "<club> - <partner>" (the form of a club
    whose name two partners have). Never a bare prefix: 'QUEENS' is a prefix of
    'Queens of Quest' and must not be credited with its submissions."""
    head, value = key(club), key(value)
    return bool(head) and (value == head or value.startswith(head + SF_NAME_SEP))


def columns(rows):
    """{name: index} of the Roster columns this tool reads and writes, by header."""
    if not rows:
        sys.exit(f"{ROSTER}: the tab is empty")
    hdr = [key(h) for h in rows[0]]
    need = ("partner", "club", "region", "status", "removed_date")
    missing = [c for c in need if c not in hdr]
    if missing:
        sys.exit(f"{ROSTER}: expected the columns {', '.join(need)}; missing: " + ", ".join(missing))
    return {c: hdr.index(c) for c in need}


def select(rows, cols, regions=(), partners=(), clubs=()):
    """The active rows of the chosen clubs: ({(partner, club): {"rows": [sheet rows],
    "region": the rows' region}}, [selectors that matched no active row]). regions:
    every active club in those regions; partners: every active club of those partners,
    or with `clubs` only the named clubs of the one partner. Cells are compared as
    the Apps Script's key_ does (capitals, spacing and invisible characters ignored),
    the command line's spelling after Unicode NFC as well. Spellings are the first
    active row's."""
    i_p, i_c, i_r, i_s = cols["partner"], cols["club"], cols["region"], cols["status"]
    want_regions = {nfc_key(r) for r in regions}
    want_partners = {nfc_key(p) for p in partners}
    want_clubs = {nfc_key(c) for c in clubs}
    seen_regions, seen_partners, seen_clubs = set(), set(), set()
    chosen = {}
    for n, r in enumerate(rows[1:], start=2):
        if cell_key(cell(r, i_s)) != ACTIVE:
            continue
        partner, club = tidy(cell(r, i_p)), tidy(cell(r, i_c))
        if not (partner and club):
            continue
        region = tidy(cell(r, i_r))
        hit = False
        if nfc_key(region) in want_regions:
            seen_regions.add(nfc_key(region))
            hit = True
        if nfc_key(partner) in want_partners:
            seen_partners.add(nfc_key(partner))
            if want_clubs:
                if nfc_key(club) in want_clubs:
                    seen_clubs.add(nfc_key(club))
                    hit = True
            else:
                hit = True
        if not hit:
            continue
        pc = next((k for k in chosen if cell_key(k[0]) == cell_key(partner)
                   and cell_key(k[1]) == cell_key(club)), (partner, club))
        entry = chosen.setdefault(pc, {"rows": [], "regions": set()})
        entry["rows"].append(n)
        entry["regions"].add(region)
    empty = ([f"--region {r!r}" for r in regions if nfc_key(r) not in seen_regions]
             + [f"--partner {p!r}" for p in partners if nfc_key(p) not in seen_partners]
             + [f"--club {c!r}" for c in clubs if nfc_key(c) not in seen_clubs])
    for (partner, club), entry in chosen.items():
        if len(entry["regions"]) != 1:
            sys.exit(f"{ROSTER}: the active rows of {club!r} ({partner}) carry "
                     f"{sorted(entry['regions'])} as region - one club, one region; fix the "
                     "rows first (GLOW -> Refresh regions from the Partners tab)")
        entry["region"] = next(iter(entry.pop("regions")))
    return chosen, empty


def active_rows_of(rows, cols, pairs):
    """{(partner, club): [sheet rows]} of the ACTIVE rows of each pair in `rows`."""
    i_p, i_c, i_s = cols["partner"], cols["club"], cols["status"]
    want = {(cell_key(p), cell_key(c)): (p, c) for p, c in pairs}
    out = {pc: [] for pc in pairs}
    for n, r in enumerate(rows[1:], start=2):
        pc = want.get((cell_key(cell(r, i_p)), cell_key(cell(r, i_c))))
        if pc is not None and cell_key(cell(r, i_s)) == ACTIVE:
            out[pc].append(n)
    return out


# ------------------------------------------------------------------ the guard
def fetch_since(client, form_id, since=SINCE):
    """Every submission of the form created after `since`, page by page. Jotform
    lists the newest first, so one arriving meanwhile repeats a submission on the
    next page (dropped here) and hides none."""
    flt = quote(json.dumps({"created_at:gt": since}), safe="")
    seen, out, offset = set(), [], 0
    while True:
        page = client.get(f"/form/{form_id}/submissions", limit=PAGE, offset=offset, filter=flt)
        if not isinstance(page, list):
            sys.exit(f"form {form_id}: the submissions answer is a {type(page).__name__}, not a "
                     "list - an answer shape this tool does not know")
        for sub in page:
            if not isinstance(sub, dict) or not sub.get("id"):
                sys.exit(f"form {form_id}: a submission without an id - an answer shape this tool "
                         "does not know")
            if sub["id"] not in seen:
                seen.add(sub["id"])
                out.append(sub)
        if len(page) < PAGE:
            break
        offset += PAGE
    return out


def picker_of(questions):
    """qid of the form's Club picker (the dropdown named PICKER_NAME), or None."""
    return next((qid for qid, q in questions.items()
                 if q.get("type") == "control_dropdown" and q.get("name") == PICKER_NAME), None)


def answer_of(sub, qid):
    found = (sub.get("answers") or {}).get(qid) if qid else None
    return found.get("answer") if isinstance(found, dict) else None


def picks_of(sub, picker):
    """The Club picker's answer as a list of texts ([] = none); a list or one string."""
    value = answer_of(sub, picker)
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        sys.exit(f"submission {sub.get('id')}: the Club picker (q{picker}) is answered with a "
                 f"{type(value).__name__} that is not a list of clubs - not read")
    return [v for v in value if v.strip()]


def club_hits(subs, picker, clubs):
    """{(partner, club): [(day, several)]} - the submissions naming each of `clubs` in
    question 5 or in a Club picker pick (`matches`), as (created_at's day, whether
    the picker listed more than one club). Nothing else of a submission is read."""
    out = {pc: [] for pc in clubs}
    for sub in subs:
        picks = picks_of(sub, picker)
        q5 = answer_of(sub, CLUB_NAME)
        values = picks + ([q5] if isinstance(q5, str) and q5.strip() else [])
        day = str(sub.get("created_at") or "")[:10]
        for pc in clubs:
            if any(matches(v, pc[1]) for v in values):
                out[pc].append((day, len(picks) > 1))
    return out


def print_counts(region, form_id, subs, hits):
    """The guard's table for one form: per partner, then every club that was named."""
    print(f"{region} form {form_id}: {len(subs)} submissions since {SINCE[:10]} read")
    by_partner = {}
    for (partner, club), found in hits.items():
        by_partner.setdefault(partner, []).append((club, found))
    for partner, entries in sorted(by_partner.items(), key=lambda kv: key(kv[0])):
        n = sum(len(found) for _, found in entries)
        several = sum(1 for _, found in entries for _, s in found if s)
        last = max((day for _, found in entries for day, _ in found), default="")
        note = ""
        if n:
            note = f"  (last {last}" + (f"; {several} picked together with another club" if several else "") + ")"
        print(f"  {partner:<32} {len(entries):>3} club(s) {n:>4} submission(s){note}")
        for club, found in sorted(entries, key=lambda e: key(e[0])):
            if found:
                days = sorted(day for day, _ in found)
                print(f"      {club!r}: {len(found)} submission(s), " + ", ".join(days[-5:])
                      + (" ..." if len(days) > 5 else ""))


def guard(client, chosen, recent_from, check_only, anyway=False):
    """Read each region's form, print the table, and stop when a club was named in a
    submission on or after `recent_from` (yyyy-mm-dd) - unless `check_only` (the
    table is the point; nothing follows) or `anyway` (--deactivate-anyway: said, not
    stopped)."""
    regions = sorted({e["region"] for e in chosen.values()})
    recent = []
    for region in regions:
        form_id = glow_forms.REGIONALS[region]
        clubs = [pc for pc, e in chosen.items() if e["region"] == region]
        subs = fetch_since(client, form_id)
        picker = picker_of(client.get(f"/form/{form_id}/questions") or {})
        hits = club_hits(subs, picker, clubs)
        print_counts(region, form_id, subs, hits)
        recent += [(pc, day) for pc, found in hits.items() for day, _ in found if day >= recent_from]
    if check_only:
        print(f"\n--check-only: {sum(len(e['rows']) for e in chosen.values())} active row(s) of "
              f"{len(chosen)} club(s) would be deactivated; nothing planned, nothing written")
        return
    if not recent:
        print(f"  no chosen club was named in a submission since {recent_from}")
        return
    (partner, club), day = max(recent, key=lambda t: t[1])
    named = {pc for pc, _ in recent}
    if anyway:
        print(f"  ! {len(named)} of the {len(chosen)} club(s) named in a submission since {recent_from} "
              f"(last: {club!r}, {day}) - going on: --deactivate-anyway")
        return
    sys.exit(f"{club!r} ({partner}) sent attendance on {day} - deactivating a club that reports "
             f"needs --deactivate-anyway ({len(named)} of the {len(chosen)} club(s) named in a "
             f"submission since {recent_from})")


# ------------------------------------------------------------------ the writes
def save_roster(folder, rows):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, ROSTER + ".csv"), "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def write_cells(svc, before, cols, changes, pairs, label):
    """Set `changes` ({sheet row: {column index: value}}) on the Roster: re-read first
    and stop (nothing written) when one of those rows changed since `before` was
    read or one of `pairs` gained an active row; one RAW batchUpdate; re-read and
    compare every row (the planned rows as planned, every other row unchanged in
    the written columns). Returns (the tab after the write, [late active rows of
    `pairs` appended during the run])."""
    now = sc.read_tab(svc, ROSTER)
    stale = [n for n in changes if n > len(now) or trimmed(now[n - 1]) != trimmed(before[n - 1])]
    gained = sorted({n for rows in active_rows_of(now, cols, pairs).values() for n in rows} - set(changes))
    if stale or gained:
        what = (f"{describe_rows(stale)} changed" if stale else "") \
            + (" and " if stale and gained else "") \
            + (f"{describe_rows(gained)} came in for the chosen clubs" if gained else "")
        sys.exit(f"{ROSTER}: {what} since the plan was read (a form submission?) - nothing "
                 "written; run the tool again")
    data = [{"range": a1(ROSTER, f"{col_letter(c)}{n}"), "values": [[v]]}
            for n, cells in changes.items() for c, v in cells.items()]
    resp = svc.spreadsheets().values().batchUpdate(
        spreadsheetId=sc.spreadsheet_id(),
        body={"valueInputOption": "RAW", "data": data}).execute()
    if resp.get("totalUpdatedCells") != len(data):
        print(f"  note: Sheets reports {resp.get('totalUpdatedCells')} cell(s) updated for "
              f"{len(data)} sent - the re-read below decides")
    after = sc.read_tab(svc, ROSTER)
    written = {c for cells in changes.values() for c in cells}
    bad = 0
    for n, row in enumerate(before, start=1):
        got = after[n - 1] if n - 1 < len(after) else None
        if n in changes:
            expected = list(row)
            for c, v in changes[n].items():
                expected += [""] * (c + 1 - len(expected))
                expected[c] = v
            ok = got is not None and trimmed(got) == trimmed(expected)
        else:
            ok = got is not None and all(cell(got, c) == cell(row, c) for c in written)
        if not ok:
            bad += 1
            print(f"  ! {ROSTER} row {n} differs after the write")
    if bad:
        sys.exit(f"{bad} row(s) did not verify - {label}; no Audit row written")
    print(f"  {ROSTER}: {len(data)} cell(s) written and verified")
    late = [n for rows in active_rows_of(after, cols, pairs).values() for n in rows if n > len(before)]
    if len(after) > len(before) and not late:
        print(f"  note: {ROSTER} gained {len(after) - len(before)} row(s) during the run "
              "(a form submission?) - left alone")
    return after, sorted(late)


def next_steps(regions, undo_dir=None):
    print("\nNext (docs/RUNBOOK.md, \"Deactivating a club\"):")
    print("  In the sheet, now: GLOW -> Google Forms -> Update form dropdowns from the Roster")
    print("    (until then the Club Roster Form still offers the clubs, and a change sent for one "
          "runs against the inactive rows)")
    print("  python3 tools/sheets_client.py export Roster data/roster_<date>.csv")
    print(f"  python3 sync_attendance_form.py data/roster_<date>.csv --roster --form "
          f"{glow_forms.TEMPLATE}   # template dry run: '~ retired roster' lines the day after")
    for region in regions:
        print(f"  python3 tools/auto_sync.py --region {region!r}     # dry run; a DISABLED form reads "
              "'skipped' and is left as it is")
    if undo_dir:
        print(f"  Undo: python3 tools/deactivate_clubs.py --undo {os.path.relpath(undo_dir, REPO)}")


def deactivate(args, svc, roster, zone):
    cols = columns(roster)
    chosen, empty = select(roster, cols, args.region or [], args.partner or [], args.club or [])
    if empty:
        sys.exit(", ".join(empty) + (" match" if len(empty) > 1 else " matches") + " no active "
                 f"{ROSTER} row - check the spelling against the {ROSTER} tab (regions: "
                 + " / ".join(glow_forms.REGIONS) + ")")
    for (partner, club), entry in chosen.items():
        if entry["region"] not in glow_forms.REGIONALS:
            sys.exit(f"{club!r} ({partner}): its rows carry region {entry['region']!r}, which is no "
                     "attendance form's, so the guard cannot read its submissions - fix the "
                     "Partners tab and GLOW -> Refresh regions first")
    regions = sorted({e["region"] for e in chosen.values()})
    today = datetime.now(zone).strftime("%Y-%m-%d")
    # the sheet's day, as removed_date is; created_at is US Eastern - a day's fuzz on a 30-day guard
    recent_from = (datetime.now(zone) - timedelta(days=args.recent_days)).strftime("%Y-%m-%d")

    api_key = os.environ.get("JOTFORM_API_KEY") or sys.exit(
        "Set JOTFORM_API_KEY in the environment (.env): the guard reads the region's attendance "
        f"form submissions since {SINCE[:10]} before any club is deactivated")
    guard(Client(api_key), chosen, recent_from, args.check_only, args.deactivate_anyway)
    if args.check_only:
        return

    rows = sorted(n for e in chosen.values() for n in e["rows"])
    i_s, i_r = cols["status"], cols["removed_date"]
    print()
    for (partner, club), entry in sorted(chosen.items(), key=lambda kv: (key(kv[0][0]), key(kv[0][1]))):
        print(f"  {partner:<32} {club:<32} {len(entry['rows']):>4} active row(s)   "
              f"{describe_rows(entry['rows'])}")
    print(f"  {ROSTER:<14} {len(rows):>5} row(s) -> status {INACTIVE}, removed_date {today} "
          f"({2 * len(rows)} cells)")
    print(f"  {AUDIT:<14} {1:>5} row appended")
    print(f"  {'Undo':<14} python3 tools/deactivate_clubs.py --undo "
          f"{os.path.relpath(OUT, REPO)}/<stamp>")
    if not args.apply:
        print("\nDRY RUN - re-run with --apply to write")
        return

    stamp = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    out = os.path.join(OUT, stamp)
    save_roster(out, roster)
    record = {"written": stamp, "tab": ROSTER, "status_col": i_s, "removed_col": i_r,
              "set": {"status": INACTIVE, "removed_date": today}, "reason": args.reason,
              "clubs": [[p, c, len(e["rows"]), e["region"]] for (p, c), e in chosen.items()],
              "rows": [{"row": n, "partner": p, "club": c, "status": cell(roster[n - 1], i_s),
                        "removed_date": cell(roster[n - 1], i_r)}
                       for (p, c), e in chosen.items() for n in e["rows"]]}
    with open(os.path.join(out, "written.json"), "w", encoding="utf-8") as f:
        json.dump(record, f, indent=1, ensure_ascii=False)
    print(f"\nSaved the {ROSTER} tab and the rows to {os.path.relpath(out, REPO)}/")

    changes = {n: {i_s: INACTIVE, i_r: today} for n in rows}
    _, late = write_cells(svc, roster, cols, changes, list(chosen), label=f"the {ROSTER} as it was is in "
                          f"{os.path.relpath(out, REPO)}/Roster.csv, the rows planned in written.json")
    partners = {key(p) for p, _ in chosen}
    detail = (f"{len(chosen)} club(s) of {len(partners)} partner(s) in {', '.join(regions)}: "
              f"{len(rows)} row(s) set {INACTIVE}, removed_date {today} - tools/deactivate_clubs.py "
              f"({args.reason})")
    sc.append_rows(svc, AUDIT, [[datetime.now(zone).strftime("%Y-%m-%d %H:%M:%S"), "deactivateRows", detail]])
    print(f"  {AUDIT}: 1 row appended")
    if late:
        print(f"  ! {ROSTER} {describe_rows(late)}: active row(s) of the chosen clubs arrived during "
              "the run - still active; run the tool again for them")
    next_steps(regions, out)
    if late:
        sys.exit(f"{len(late)} row(s) of the chosen clubs arrived during the run and are still active")


def undo(args, svc, roster, zone):
    folder = args.undo
    path = os.path.join(folder, "written.json")
    if not os.path.exists(path):
        sys.exit(f"{folder}: no written.json - pass the run's folder, "
                 f"{os.path.relpath(OUT, REPO)}/<stamp>")
    with open(path, encoding="utf-8") as f:
        record = json.load(f)
    cols = columns(roster)
    i_p, i_c, i_s, i_r = cols["partner"], cols["club"], cols["status"], cols["removed_date"]
    if (i_s, i_r) != (record["status_col"], record["removed_col"]):
        sys.exit(f"{ROSTER}: the status / removed_date columns are not where they were on "
                 f"{record['written']} - put the rows back by hand from "
                 f"{os.path.relpath(folder, REPO)}/Roster.csv")
    was = record["set"]
    changed = []
    for r in record["rows"]:
        n = r["row"]
        row = roster[n - 1] if 1 < n <= len(roster) else None
        if row is None or cell_key(cell(row, i_p)) != cell_key(r["partner"]) \
                or cell_key(cell(row, i_c)) != cell_key(r["club"]) \
                or cell(row, i_s) != was["status"] or cell(row, i_r) != was["removed_date"]:
            changed.append(n)
    if changed:
        sys.exit(f"{ROSTER}: {describe_rows(changed)} changed since the run of {record['written']} "
                 "(a reactivation through the Club Roster Form, a move?) - nothing written. Look at "
                 "those rows; if the rest should still go back, take them out of written.json and "
                 "run again")
    changes = {r["row"]: {i_s: r["status"], i_r: r["removed_date"]} for r in record["rows"]}
    pairs = [(p, c) for p, c, _, _ in record["clubs"]]
    regions = sorted({rg for _, _, _, rg in record["clubs"]})
    for p, c, n, _ in sorted(record["clubs"], key=lambda e: (key(e[0]), key(e[1]))):
        print(f"  {p:<32} {c:<32} {n:>4} row(s) back")
    print(f"  {ROSTER:<14} {len(changes):>5} row(s) -> status and removed_date as before the run of "
          f"{record['written']} ({2 * len(changes)} cells)")
    print(f"  {AUDIT:<14} {1:>5} row appended")
    if not args.apply:
        print("\nDRY RUN - re-run with --apply to write")
        return

    stamp = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    out = os.path.join(folder, "undo-" + stamp)
    save_roster(out, roster)
    print(f"\nSaved the {ROSTER} tab before the undo to {os.path.relpath(out, REPO)}/")
    # the stale check compares the rows with the read above; a row of a chosen club that is
    # active now is one that came back meanwhile, and it stops the undo too
    write_cells(svc, roster, cols, changes, pairs, label=f"the {ROSTER} as it was is in "
                f"{os.path.relpath(out, REPO)}/Roster.csv")
    partners = {key(p) for p, _ in pairs}
    detail = (f"{len(changes)} row(s) of {len(pairs)} club(s) of {len(partners)} partner(s) in "
              f"{', '.join(regions)} set back as before {record['written']} (status, removed_date) - "
              f"tools/deactivate_clubs.py --undo {os.path.relpath(folder, REPO)}")
    sc.append_rows(svc, AUDIT, [[datetime.now(zone).strftime("%Y-%m-%d %H:%M:%S"), "reactivateRows", detail]])
    print(f"  {AUDIT}: 1 row appended")
    next_steps(regions)


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--region", action="append", metavar="REGION",
                    help="every club with an active row in this region (repeatable)")
    ap.add_argument("--partner", action="append", metavar="PARTNER",
                    help="every active club of this partner (repeatable); with --club, the club's partner")
    ap.add_argument("--club", action="append", metavar="CLUB",
                    help="one club of the one --partner given (repeatable)")
    ap.add_argument("--reason", help="one line for the Audit row (required with --apply)")
    ap.add_argument("--recent-days", type=int, default=RECENT_DAYS, metavar="N",
                    help=f"a club named in a submission in the last N days stops the run (default {RECENT_DAYS})")
    ap.add_argument("--deactivate-anyway", action="store_true",
                    help="go on although a chosen club sent attendance in the last --recent-days days")
    ap.add_argument("--check-only", action="store_true",
                    help="print the submission counts per partner and club, then stop (nothing planned)")
    ap.add_argument("--undo", metavar="DIR",
                    help="put back the rows a run's written.json names (data/deactivate_clubs/<stamp>)")
    ap.add_argument("--apply", action="store_true", help="write (dry run without it)")
    args = ap.parse_args()

    selectors = bool(args.region or args.partner or args.club)
    if args.undo and (selectors or args.check_only or args.deactivate_anyway):
        sys.exit("--undo takes no selector and no guard flag: it puts back exactly the rows written.json names")
    if not args.undo and not selectors:
        sys.exit("choose the clubs: --region, --partner (repeatable), or --partner with --club; or --undo <dir>")
    if args.club and len(args.partner or []) != 1:
        sys.exit("--club goes with exactly one --partner (the club's)")
    if args.check_only and args.apply:
        sys.exit("--check-only reads only; drop --apply")
    if args.apply and not args.undo and not tidy(args.reason or ""):
        sys.exit("--apply needs --reason: one line for the Audit row, e.g. "
                 "--reason \"the clubs do not report through Jotform (Ryan, <date>)\"")
    if args.recent_days < 0:
        sys.exit("--recent-days must be 0 or more")

    svc = sc.service()
    print(f"Spreadsheet {sc.spreadsheet_id()} as {sc.sa_email()}\n")
    roster = sc.read_tab(svc, ROSTER)
    # the sheet's own zone, read before anything else: removed_date and the Audit `when` are
    # written in it, like the Apps Script's (the backup folder's stamp stays local)
    zone = sc.named_zone(sc.time_zone(svc))
    if args.undo:
        undo(args, svc, roster, zone)
    else:
        deactivate(args, svc, roster, zone)


if __name__ == "__main__":
    run(main)
