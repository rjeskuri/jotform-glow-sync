#!/usr/bin/env python3
"""
Rename a club in place - master sheet and attendance forms - so it keeps its
club code, its girls' ids and its Jotform roster question.

A club is keyed by its name almost everywhere: the Roster and SF Pending tabs,
the ClubRegistry (whose club_code must stay - Ids.gs: an id never changes when
a club is renamed) and the label of its roster checkbox question on the
region's attendance form and on the template. Editing the sheet alone would
make the next sync CREATE a second question under the new name and leave the
old one orphaned in the Club picker. This tool renames the question label
too, so the next sync only rewrites the picker options and the rules.

What --apply writes:
  sheet    the 'club' cell of every Roster row of the club (any status), of
           its ClubRegistry row and of its SF Pending rows; one Audit row
  Jotform  question[text] of the club's roster question on each form

It refuses when the club is not in the Roster, has no single ClubRegistry
row, when the partner already has a club with the new name (sheet or form),
or when a form holds more than one question with the old name. Dry run by
default; --apply first saves the tabs it touches under
data/rename_club/<stamp>/ and takes a backup_forms.py snapshot of each form,
then re-reads and compares every write.

    python3 tools/rename_club.py --partner "Demo Partner" \\
        --old "Old Club Name" --new "New Club Name"          # dry run
    python3 tools/rename_club.py ... --apply                 # write

Afterwards (docs/RUNBOOK.md, "Renaming a club"): export the Roster, sync the
region's form and the template (dry run, then --apply), form_status CLEAN,
and refresh the Google Form dropdowns from the sheet's GLOW menu.
"""
import argparse
import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sheets_client as sc  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import backup_forms                       # noqa: E402
from glow import forms as glow_forms      # noqa: E402
from glow.cli import run                  # noqa: E402
from glow.jotform import Client           # noqa: E402
from glow.text import key                 # noqa: E402

TABS = ("Roster", "ClubRegistry", "SF Pending")   # every tab with a 'club' column
OUT = os.path.join(REPO, "data", "rename_club")


def col_letter(index):
    """0-based column index -> A1 column letters (0 -> A, 26 -> AA)."""
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def a1(tab, cell):
    return "'" + tab.replace("'", "''") + "'!" + cell


def find_cells(rows, partner, old, new):
    """For one tab's values (header first): (index of the 'club' column,
    [sheet row numbers holding the old name], [rows already holding the new
    name], {regions of the hits}). Rows are matched on partner AND club with
    glow.text.key (case- and whitespace-insensitive, the Apps Script's key_)."""
    if not rows:
        return None, [], [], set()
    hdr = [key(h) for h in rows[0]]
    if "partner" not in hdr or "club" not in hdr:
        sys.exit("expected the columns 'partner' and 'club'; found: " + ", ".join(rows[0]))
    i_p, i_c = hdr.index("partner"), hdr.index("club")
    i_r = hdr.index("region") if "region" in hdr else None
    hits, clashes, regions = [], [], set()
    for n, r in enumerate(rows[1:], start=2):
        if key(r[i_p]) != key(partner):
            continue
        if key(r[i_c]) == key(old):
            hits.append(n)
            if i_r is not None:
                regions.add(" ".join(r[i_r].split()))
        elif key(r[i_c]) == key(new):
            clashes.append(n)
    return i_c, hits, clashes, regions


def describe_rows(rows):
    if not rows:
        return "no rows"
    if len(rows) > 1 and rows == list(range(rows[0], rows[-1] + 1)):
        return f"rows {rows[0]}-{rows[-1]}"
    shown = ", ".join(map(str, rows[:8])) + (", ..." if len(rows) > 8 else "")
    return ("row " if len(rows) == 1 else "rows ") + shown


def form_questions(client, form_id, old, new):
    """([qids of roster questions named old], [qids named new]) on one form."""
    questions = client.get(f"/form/{form_id}/questions")
    hits, clashes = [], []
    for qid, q in questions.items():
        if q.get("type") != "control_checkbox":
            continue
        if key(q.get("text")) == key(old):
            hits.append(qid)
        elif key(q.get("text")) == key(new):
            clashes.append(qid)
    return hits, clashes


def trimmed(row):
    row = list(row)
    while row and row[-1] == "":
        row.pop()
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--partner", required=True, help="partner organization, as in the Roster")
    ap.add_argument("--old", required=True, help="the club's current name")
    ap.add_argument("--new", required=True, help="the name it should have")
    ap.add_argument("--form", action="append", metavar="ID",
                    help="form to rename the question on (repeatable; default: the "
                         "region's live form and the template)")
    ap.add_argument("--sheet-only", action="store_true", help="leave the forms alone")
    ap.add_argument("--apply", action="store_true", help="write (dry run without it)")
    args = ap.parse_args()

    partner = " ".join(args.partner.split())
    old, new = " ".join(args.old.split()), " ".join(args.new.split())
    if not new or old == new:
        sys.exit("--new must be a different, non-empty name")

    svc = sc.service()
    print(f"Spreadsheet {sc.spreadsheet_id()} as {sc.sa_email()}\n")
    tabs = {tab: sc.read_tab(svc, tab) for tab in TABS}
    plan, regions = {}, set()
    for tab, rows in tabs.items():
        i_c, hits, clashes, regs = find_cells(rows, partner, old, new)
        if clashes:
            sys.exit(f"{tab}: {partner!r} already has a club named {new!r} "
                     f"({describe_rows(clashes)}) - not merging two clubs")
        plan[tab] = (i_c, hits)
        if tab == "Roster":
            regions = {r for r in regs if r}
    if not plan["Roster"][1]:
        sys.exit(f"Roster: no row has partner {partner!r} and club {old!r} - "
                 "check the spelling against the Roster tab")
    if len(plan["ClubRegistry"][1]) != 1:
        sys.exit(f"ClubRegistry: expected exactly one row for {partner!r} / {old!r}, "
                 f"found {len(plan['ClubRegistry'][1])} - fix the registry first")
    reg_rows = tabs["ClubRegistry"]
    code = reg_rows[plan["ClubRegistry"][1][0] - 1][[key(h) for h in reg_rows[0]].index("club_code")]

    print(f"{partner}: club {old!r} -> {new!r}")
    for tab, (i_c, hits) in plan.items():
        note = f"club_code {code} stays" if tab == "ClubRegistry" else \
               f"column {col_letter(i_c)}"
        print(f"  {tab:<14} {len(hits):>5} cell(s)  {describe_rows(hits)}  ({note})")
    print(f"  {'Audit':<14} {1:>5} row appended")

    forms, client = [], None
    if not args.sheet_only:
        api_key = os.environ.get("JOTFORM_API_KEY") or sys.exit(
            "Set JOTFORM_API_KEY in the environment (.env), or pass --sheet-only")
        client = Client(api_key, apply=args.apply)
        ids = args.form or []
        if not ids:
            if len(regions) != 1:
                sys.exit(f"the club's Roster rows carry {sorted(regions) or 'no'} region - "
                         "pass --form explicitly")
            region = next(iter(regions))
            if region not in glow_forms.REGIONALS:
                sys.exit(f"unknown region {region!r} - fix the Partners tab first "
                         f"(one of {', '.join(glow_forms.REGIONS)})")
            ids = [glow_forms.REGIONALS[region], glow_forms.TEMPLATE]
        for fid in ids:
            hits, clashes = form_questions(client, fid, old, new)
            label = glow_forms.LABELS.get(fid, fid)
            if clashes:
                sys.exit(f"form {fid}: a roster question named {new!r} already exists "
                         f"(q{', q'.join(clashes)}) - not merging two clubs")
            if len(hits) > 1:
                sys.exit(f"form {fid}: {len(hits)} questions named {old!r} "
                         f"(q{', q'.join(hits)}) - fix the form first")
            if not hits:
                print(f"  form {fid}: no roster question named {old!r} - nothing to "
                      f"rename there (the next sync creates {new!r})")
                continue
            forms.append((fid, hits[0]))
            print(f"  form {fid}  q{hits[0]}: text {old!r} -> {new!r}   [{label}]")

    if not args.apply:
        print("\nDRY RUN - re-run with --apply to write")
        return

    # --- backups: the tabs as they are now, and a form snapshot ---------------
    stamp = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    out = os.path.join(OUT, stamp)
    os.makedirs(out, exist_ok=True)
    for tab, rows in tabs.items():
        with open(os.path.join(out, tab + ".csv"), "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
    print(f"\nSaved the tabs before the change to {os.path.relpath(out, REPO)}/")
    for fid, _ in forms:
        s = backup_forms.snapshot(fid, client, stamp)
        print(f"  backup_forms: form {fid} ({s['questions']} questions, {s['conditions']} "
              f"conditions) -> backups/{fid}/*-{stamp}.json")

    # --- the sheet: only the planned cells, RAW, in one batch -----------------
    data = [{"range": a1(tab, f"{col_letter(i_c)}{n}"), "values": [[new]]}
            for tab, (i_c, hits) in plan.items() for n in hits]
    resp = svc.spreadsheets().values().batchUpdate(
        spreadsheetId=sc.spreadsheet_id(),
        body={"valueInputOption": "RAW", "data": data}).execute()
    if resp.get("totalUpdatedCells") != len(data):
        sys.exit(f"wrote {resp.get('totalUpdatedCells')} cells, expected {len(data)} - "
                 f"compare the sheet with {os.path.relpath(out, REPO)}/ before retrying")

    problems = 0
    for tab, (i_c, hits) in plan.items():
        before, after = tabs[tab], sc.read_tab(svc, tab)
        want = set(hits)
        for n, row in enumerate(before, start=1):
            expected = list(row)
            if n in want:
                expected[i_c] = new
            got = after[n - 1] if n - 1 < len(after) else None
            if got is None or trimmed(got) != trimmed(expected):
                problems += 1
                print(f"  ! {tab} row {n} differs after the write")
        if len(after) > len(before):
            print(f"  note: {tab} gained {len(after) - len(before)} row(s) during the run "
                  "(a form submission?) - left alone")
        print(f"  {tab}: {len(hits)} cell(s) written and verified")
    if problems:
        sys.exit(f"{problems} row(s) did not verify - the tabs as they were are in "
                 f"{os.path.relpath(out, REPO)}/")
    detail = (f"{partner}: club '{old}' -> '{new}' ({len(plan['Roster'][1])} Roster rows, "
              f"ClubRegistry {code} kept, {len(plan['SF Pending'][1])} SF Pending rows"
              + (f"; forms {', '.join(f'{f} q{q}' for f, q in forms)}" if forms else "")
              + ") - tools/rename_club.py")
    sc.append_rows(svc, "Audit", [[datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                   "renameClub", detail]])
    print("  Audit: 1 row appended")

    # --- the forms: the question label, re-read after ------------------------
    mismatches = 0
    for fid, qid in forms:
        client.post_form(f"/form/{fid}/question/{qid}", {"question[text]": new},
                         f"RENAME q{qid} on {fid}: {old!r} -> {new!r}")
        after = client.get(f"/form/{fid}/question/{qid}")
        if key(after.get("text")) != key(new):
            mismatches += 1
            print(f"  ! MISMATCH after write on form {fid} q{qid}: text is {after.get('text')!r}")
        else:
            print(f"  form {fid} q{qid}: renamed and verified")
    if mismatches:
        sys.exit(f"{mismatches} question(s) did not verify - re-read before retrying")

    region_form = forms[0][0] if forms else "<form id>"
    print("\nNext (docs/RUNBOOK.md, \"Renaming a club\"): the sync rewrites the picker "
          "options and the rules -")
    print("  python3 tools/sheets_client.py export Roster data/roster_<date>.csv")
    print(f"  python3 sync_attendance_form.py data/roster_<date>.csv --roster "
          f"--region <region> --form {region_form}      # dry run, then --apply")
    print(f"  python3 sync_attendance_form.py data/roster_<date>.csv --roster "
          f"--form {glow_forms.TEMPLATE}                       # the template, same")
    print(f"  python3 tools/form_status.py --form {region_form} --roster data/roster_<date>.csv"
          "   # CLEAN")
    print("  In the sheet: GLOW -> Google Forms -> Update form dropdowns from the Roster")


if __name__ == "__main__":
    run(main)
