#!/usr/bin/env python3
"""
Write the locally built tabs (data/roster_build/*.csv, from
tools/build_roster_offline.js) into the enrollment spreadsheet.

What happens to each tab:
  Roster, ClubRegistry   replaced wholesale (IDs are minted locally)
  Partners               merged: live rows are kept as they are, a blank
                         region is filled from the local build, new partners
                         are appended - staff edits always survive
  ReviewQueue            local issues appended unless the same open issue is
                         already there; 'resolved' marks are never lost
  Audit                  appended, never cleared

Safety:
  * Dry run by default; --apply writes.
  * If ANY of the five live tabs already has data rows, the run stops unless
    --replace is given, and every live tab is first saved to
    data/roster_build/previous/<stamp>/.
  * With --replace, the live Roster is compared with the local one: if the
    sheet holds a girl ID the local build does not (someone minted IDs in the
    sheet since the build), the upload refuses - the fix is to export the live
    tabs and rebuild with --existing so nothing is re-minted.

Usage:
    python3 tools/upload_roster.py                      # dry run
    python3 tools/upload_roster.py --apply
    python3 tools/upload_roster.py --apply --replace    # onto tabs that have data
"""
import argparse
import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sheets_client as sc  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(REPO, "data", "roster_build")
REPLACE_TABS = ["Roster", "ClubRegistry"]
MERGE_TABS = ["Partners"]
APPEND_TABS = ["ReviewQueue", "Audit"]
TABS = REPLACE_TABS + MERGE_TABS + APPEND_TABS


def key(s):
    return " ".join(str(s or "").split()).lower()


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def merge_partners(live, local):
    """Live rows verbatim; blank live region filled from local; new appended."""
    if not live:
        return local, len(local) - 1, 0
    out = [live[0]]
    seen = {}
    local_by_key = {key(r[0]): r for r in local[1:] if r and key(r[0])}
    filled = 0
    for r in live[1:]:
        r = (r + ["", "", ""])[:3]
        k = key(r[0])
        if not k:
            out.append(r)
            continue
        seen[k] = True
        if not r[1].strip() and k in local_by_key and local_by_key[k][1].strip():
            r = [r[0], local_by_key[k][1], r[2] or local_by_key[k][2]]
            filled += 1
        out.append(r)
    added = 0
    for k, r in local_by_key.items():
        if k not in seen:
            out.append(r[:3])
            added += 1
    return out, added, filled


def new_review_rows(live, local):
    """Local issues not already open (same issue+partner+club, unresolved)."""
    open_keys = set()
    for r in live[1:]:
        r = (r + [""] * 6)[:6]
        if not r[5].strip():
            open_keys.add((key(r[1]), key(r[2]), key(r[3])))
    return [r for r in local[1:] if (key(r[1]), key(r[2]), key(r[3])) not in open_keys]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--replace", action="store_true",
                    help="allow writing when live tabs already hold data")
    args = ap.parse_args()

    local = {}
    for tab in TABS:
        path = os.path.join(BUILD, tab + ".csv")
        if not os.path.exists(path):
            sys.exit(f"Missing {os.path.relpath(path, REPO)} - run "
                     "tools/build_roster_offline.js first")
        local[tab] = read_csv(path)

    svc = sc.service()
    print(f"Spreadsheet {sc.spreadsheet_id()} as {sc.sa_email()}\n")
    live_titles = {t for t, _, _, _ in sc.list_tabs(svc)}
    live = {tab: (sc.read_tab(svc, tab) if tab in live_titles else []) for tab in TABS}
    live_rows = {tab: max(0, len(v) - 1) for tab, v in live.items()}

    if any(live_rows.values()) and not args.replace:
        busy = ", ".join(f"{t} ({n})" for t, n in live_rows.items() if n)
        sys.exit(f"Live tabs already hold data: {busy}.\nEither maintain the "
                 "roster from the sheet's own GLOW menu, or export the live tabs "
                 "(sheets_client.py export-all DIR), rebuild with "
                 "build_roster_offline.js --existing DIR, and re-run with --replace.")

    # staleness check: every ID in the sheet must be in the local build
    if live_rows["Roster"]:
        hdr = live["Roster"][0]
        i_id = hdr.index("girl_id") if "girl_id" in hdr else 0
        live_ids = {key(r[i_id]) for r in live["Roster"][1:] if r and key(r[i_id])}
        local_ids = {key(r[0]) for r in local["Roster"][1:] if r}
        missing = live_ids - local_ids
        if missing:
            sample = ", ".join(sorted(missing)[:3])
            sys.exit(f"The sheet's Roster has {len(missing)} girl ID(s) the local "
                     f"build does not (e.g. {sample}). The build is stale: export "
                     "the live tabs and rebuild with --existing before uploading.")

    partners_merged, p_added, p_filled = merge_partners(live["Partners"], local["Partners"])
    review_new = new_review_rows(live["ReviewQueue"], local["ReviewQueue"])
    audit_new = local["Audit"][1:]

    for tab in REPLACE_TABS:
        print(f"  {tab:<14} {len(local[tab]) - 1:>5} rows  "
              f"({'new tab' if tab not in live_titles else f'replaces {live_rows[tab]} rows'})")
    print(f"  {'Partners':<14} {len(partners_merged) - 1:>5} rows  "
          f"(keeps {live_rows['Partners']} live, fills {p_filled} blank regions, adds {p_added})")
    print(f"  {'ReviewQueue':<14} {len(review_new):>5} new issues appended "
          f"({len(local['ReviewQueue']) - 1 - len(review_new)} already open)")
    print(f"  {'Audit':<14} {len(audit_new):>5} rows appended")

    if not args.apply:
        print("\nDRY RUN - re-run with --apply to write")
        return

    if any(live_rows.values()):
        stamp = datetime.now().strftime("%Y-%m-%dT%H%M")
        prev = os.path.join(BUILD, "previous", stamp)
        os.makedirs(prev, exist_ok=True)
        for tab in TABS:
            if tab in live_titles:
                with open(os.path.join(prev, tab + ".csv"), "w", newline="",
                          encoding="utf-8") as f:
                    csv.writer(f).writerows(live[tab])
        print(f"\nSaved the previous tabs to {os.path.relpath(prev, REPO)}")

    for tab in REPLACE_TABS:
        sc.write_tab(svc, tab, local[tab])
        print(f"  wrote {tab}")
    sc.write_tab(svc, "Partners", partners_merged)
    print("  wrote Partners (merged)")
    if "ReviewQueue" not in live_titles:
        sc.write_tab(svc, "ReviewQueue", [local["ReviewQueue"][0]])
    sc.append_rows(svc, "ReviewQueue", review_new)
    print(f"  appended {len(review_new)} ReviewQueue rows")
    if "Audit" not in live_titles:
        sc.write_tab(svc, "Audit", [local["Audit"][0]])
    sc.append_rows(svc, "Audit", audit_new)
    print(f"  appended {len(audit_new)} Audit rows")

    after = sc.read_tab(svc, "Roster")
    ok = len(after) == len(local["Roster"])
    print(f"\nRoster now has {len(after) - 1} rows "
          f"({'matches' if ok else 'MISMATCH - investigate'})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
