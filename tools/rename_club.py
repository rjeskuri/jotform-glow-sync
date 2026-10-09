#!/usr/bin/env python3
"""
Rename a club in place, or move it to another partner - master sheet and
attendance forms - so it keeps its club code, its girls' ids and its Jotform
roster question.

A club is keyed by its name almost everywhere: the Roster and SF Pending tabs,
the ClubRegistry (whose club_code must stay - Ids.gs: an id never changes when
a club is renamed) and the label of its roster checkbox question on the
region's attendance form and on the template. Editing the sheet alone would
make the next sync CREATE a second question under the new name and leave the
old one orphaned in the Club picker. This tool renames the question label
too, so the next sync only rewrites the picker options and the rules.

A club filed under a mistyped partner (the old enrollment form took the
partner as free text) is moved with --new-partner: the partner cells of the
same tabs, the ClubRegistry row in the same batch as the Roster rows (Ids.gs
looks a code up by partner + club, so the two must never disagree). The forms
key a club by its label, so a move alone writes nothing there. The target
must be in the Partners tab, and its spelling there is what gets written
(key_ folds neither accents nor Unicode form). When the old partner has no
rows left, its Partners row is blanked with a note, which takes it out of the
Club Roster Form's partner lists; no row is deleted.

What --apply writes:
  sheet    the 'club' (rename) and/or 'partner' (move) cell of every Roster
           row of the club (any status), of its ClubRegistry row and of its
           SF Pending rows; on a move, the old partner's Partners row
           (partner cell blanked, note added); one Audit row
  Jotform  question[text] of the club's roster question on each form (rename)

It refuses when the club is not in the Roster, has no single ClubRegistry
row, when the partner already has a club with the new name (sheet or form),
or when a form holds more than one question with the old name. A question is
found by its text alone, so when another partner also has a club of the old
name a rename refuses a question that holds that other club's girls: this
club then has no question on the form (the sync does not add a new club whose
name is in use) and is renamed with --sheet-only, after which the next sync
creates its roster under the new name. A move also
refuses a target that is not in the Partners tab or sits in another region,
a club whose current name another partner's club shares, and a club whose
show rule tests the Partner box (so a move's --apply needs the Jotform key).
Dry run by default; --apply first saves the tabs it touches under
data/rename_club/<stamp>/ and takes a snapshot (glow/backup.py) of each form
it writes, re-reads the tabs and stops (nothing written) if the club gained a
row or a planned row changed meanwhile, writes, then re-reads and compares
every write. Rows of the club that a form submission appends during the
write are written in a second, verified batch.

    python3 tools/rename_club.py --partner "Demo Partner" \\
        --old "Old Club Name" --new "New Club Name"          # dry run
    python3 tools/rename_club.py --partner "Demo Partmer" \\
        --club "Sunrise Club" --new-partner "Demo Partner"   # dry run of a move
    python3 tools/rename_club.py ... --apply                 # write

Afterwards (docs/RUNBOOK.md, "Renaming a club" / "Moving a club to another
partner"): refresh the Google Form dropdowns from the sheet's GLOW menu,
export the Roster, sync (rename) or dry-run (move) the region's form,
form_status CLEAN.
"""
import argparse
import csv
import difflib
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sheets_client as sc
from sheets_client import a1, cell, col_letter, describe_rows, trimmed

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow import backup                   # noqa: E402  (the snapshot before a write)
from glow import forms as glow_forms      # noqa: E402
from glow.cli import api_key, run                  # noqa: E402
from glow.jotform import Client           # noqa: E402
from glow.sync import PARTNER, rule_parts   # noqa: E402
from glow.text import cell_key, key, name_key, nfc_key, tidy   # noqa: E402

TABS = ("Roster", "ClubRegistry", "SF Pending")   # every tab with a 'partner' and a 'club' column
PARTNERS = "Partners"
OUT = os.path.join(REPO, "data", "rename_club")

def columns(rows):
    """(partner, club, region or None) column indexes of a tab, header first."""
    hdr = [key(h) for h in rows[0]]
    if "partner" not in hdr or "club" not in hdr:
        sys.exit("expected the columns 'partner' and 'club'; found: " + ", ".join(rows[0]))
    return hdr.index("partner"), hdr.index("club"), (hdr.index("region") if "region" in hdr else None)


def find_cells(rows, partner, old, new, new_partner=None):
    """For one tab's values (header first): (index of the 'club' column,
    [sheet row numbers of the club: partner and old name], [rows that already
    hold what it becomes: (new_partner or partner, new)], {regions of the
    hits}). Matched with cell_key (the Apps Script's key_)."""
    if not rows:
        return None, [], [], set()
    i_p, i_c, i_r = columns(rows)
    target = new_partner or partner
    hits, clashes, regions = [], [], set()
    for n, r in enumerate(rows[1:], start=2):
        p, c = cell_key(cell(r, i_p)), cell_key(cell(r, i_c))
        if p == cell_key(partner) and c == cell_key(old):
            hits.append(n)
            if i_r is not None:
                regions.add(tidy(cell(r, i_r)))
        elif p == cell_key(target) and c == cell_key(new):
            clashes.append(n)
    return i_c, hits, clashes, regions


def partner_count(rows, partner):
    """Rows of a tab (header first) whose partner is `partner`: any club, any status."""
    if not rows:
        return 0
    i_p = columns(rows)[0]
    return sum(1 for r in rows[1:] if cell_key(cell(r, i_p)) == cell_key(partner))


def late_rows(rows, start, partner, club):
    """Sheet rows after the first `start` (rows appended since the plan was read,
    e.g. by a Club Roster Form submission) that hold `club` under `partner`."""
    if not rows or len(rows) <= start:
        return []
    i_p, i_c, _ = columns(rows)
    return [n for n, r in enumerate(rows[start:], start=start + 1)
            if cell_key(cell(r, i_p)) == cell_key(partner) and cell_key(cell(r, i_c)) == cell_key(club)]


def sharing_partners(rows, partners, names):
    """The other partners (not `partners`) with a club named one of `names`.
    A name two partners share gets a Partner term in the forms' rules, which a
    move would leave pointing at the old partner."""
    if not rows:
        return []
    i_p, i_c, _ = columns(rows)
    skip = {cell_key(p) for p in partners}
    want = {cell_key(n) for n in names}
    return sorted({tidy(cell(r, i_p)) for r in rows[1:]
                   if cell_key(cell(r, i_c)) in want and tidy(cell(r, i_p))
                   and cell_key(cell(r, i_p)) not in skip})


def club_girls(rows, partner, club):
    """cell_key of every full name a tab (header first; the Roster) holds for
    this partner's club - any status: every girl it has ever had."""
    if not rows:
        return set()
    hdr = [key(h) for h in rows[0]]
    if "full_name" not in hdr:
        sys.exit("Roster: expected a 'full_name' column; found: " + ", ".join(rows[0]))
    i_p, i_c, _ = columns(rows)
    i_n = hdr.index("full_name")
    return {cell_key(cell(r, i_n)) for r in rows[1:]
            if cell_key(cell(r, i_p)) == cell_key(partner) and cell_key(cell(r, i_c)) == cell_key(club)
            and cell_key(cell(r, i_n))}


def partner_rows(rows, name):
    """The Partners tab's rows (header first) for `name`, compared as key_ does
    after Unicode NFC: [(sheet row, partner as the tab spells it, region, notes)]."""
    if not rows or not nfc_key(name):
        return []
    hdr = [key(h) for h in rows[0]]
    if "partner" not in hdr:
        sys.exit(f"{PARTNERS}: expected a 'partner' column; found: " + ", ".join(rows[0]))
    i_p = hdr.index("partner")
    i_r = hdr.index("region") if "region" in hdr else None
    i_n = hdr.index("notes") if "notes" in hdr else None
    return [(n, tidy(cell(r, i_p)), tidy(cell(r, i_r)), cell(r, i_n))
            for n, r in enumerate(rows[1:], start=2) if nfc_key(cell(r, i_p)) == nfc_key(name)]


def near_partners(rows, name):
    """Partners-tab spellings that differ from `name` only in accents, or else
    come close - the suggestion when a --new-partner is not in the tab."""
    if not rows:
        return []
    i_p = [key(h) for h in rows[0]].index("partner")
    names = sorted({tidy(cell(r, i_p)) for r in rows[1:] if tidy(cell(r, i_p))})
    same = [p for p in names if name_key(p) == name_key(name)]
    return same or difflib.get_close_matches(name, names, n=3, cutoff=0.8)


def partner_gated(conditions, qids):
    """Ids of the rules that show one of `qids` and test the typed Partner box
    (q331). The sync writes such a term only for a club name several partners
    share."""
    out = []
    for c in conditions:
        parts = rule_parts(c)
        if parts is None:
            continue
        terms, actions = parts
        shows = any(str(a.get("field")) in qids for a in actions)
        if shows and any(str(t.get("field")) == PARTNER for t in terms):
            out.append(str(c.get("id")))
    return out


def form_questions(client, form_id, old, new):
    """([qids of roster questions named old], [qids named new], {qid named old:
    cell_key of each girl it lists}) on one form."""
    questions = client.get(f"/form/{form_id}/questions")
    hits, clashes, girls = [], [], {}
    for qid, q in questions.items():
        if q.get("type") != "control_checkbox":
            continue
        if key(q.get("text")) == key(old):
            hits.append(qid)
            girls[qid] = {cell_key(o) for o in str(q.get("options") or "").split("|") if cell_key(o)}
        elif key(q.get("text")) == key(new):
            clashes.append(qid)
    return hits, clashes, girls


def masked(row, free):
    """trimmed(row) with the columns in `free` blanked - the cells a form handler
    may change in place meanwhile (setRowsStatus_: status, removed_date)."""
    return trimmed(["" if i in free else v for i, v in enumerate(row)])


def handler_cells(rows, tab):
    """The Roster columns the Apps Script edits in place; none elsewhere."""
    if tab != "Roster" or not rows:
        return set()
    hdr = [key(h) for h in rows[0]]
    return {hdr.index(c) for c in ("status", "removed_date") if c in hdr}


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--partner", required=True, help="partner organization, as in the Roster")
    ap.add_argument("--old", "--club", dest="old", required=True, help="the club's current name")
    ap.add_argument("--new", help="the name it should have (default: keep the name)")
    ap.add_argument("--new-partner", metavar="PARTNER",
                    help="move the club to this partner (spelled as in the Partners tab)")
    ap.add_argument("--keep-old-partner", action="store_true",
                    help="on a move, leave the old partner's Partners row as it is")
    ap.add_argument("--form", action="append", metavar="ID",
                    help="form to rename the question on, or on a move to check for a "
                         "Partner-gated rule (repeatable; default: the region's live form "
                         "and the template)")
    ap.add_argument("--sheet-only", action="store_true", help="leave the forms alone")
    ap.add_argument("--apply", action="store_true", help="write (dry run without it)")
    args = ap.parse_args()

    partner, old = tidy(args.partner), tidy(args.old)
    new = old if args.new is None else tidy(args.new)
    if not new:
        sys.exit("--new must be a non-empty name")
    moving = args.new_partner is not None
    renaming = new != old
    if moving and nfc_key(args.new_partner) == nfc_key(partner):
        sys.exit("--new-partner must name a different partner")
    if not (moving or renaming):
        sys.exit("--new must be a different, non-empty name (or pass --new-partner)")
    if args.keep_old_partner and not moving:
        sys.exit("--keep-old-partner goes with --new-partner")
    if moving and args.sheet_only and args.apply:
        sys.exit("a move checks the forms' rules before it writes - set JOTFORM_API_KEY and "
                 "drop --sheet-only")

    svc = sc.service()
    print(f"Spreadsheet {sc.spreadsheet_id()} as {sc.sa_email()}\n")
    tabs = {tab: sc.read_tab(svc, tab) for tab in TABS + ((PARTNERS,) if moving else ())}

    # --- a move: the target as the Partners tab spells it, same region ----------
    target, target_region, retire = partner, None, []
    if moving:
        found = partner_rows(tabs[PARTNERS], args.new_partner)
        if not found:
            near = near_partners(tabs[PARTNERS], tidy(args.new_partner))
            sys.exit(f"{PARTNERS}: no partner {tidy(args.new_partner)!r}"
                     + (f" - did you mean {' or '.join(map(repr, near))}?" if near else "")
                     + " Copy the spelling from the Partners tab; a new partner is added "
                       "there first, with its region.")
        spellings = {sp for _, sp, _, _ in found}
        target_regions = {rg for _, _, rg, _ in found}
        if len(spellings) > 1 or len(target_regions) > 1:
            sys.exit(f"{PARTNERS}: {tidy(args.new_partner)!r} is listed "
                     f"{describe_rows([n for n, *_ in found])} with different spellings "
                     "or regions - make them one row first")
        target, target_region = next(iter(spellings)), next(iter(target_regions))
        if not target_region:
            sys.exit(f"{PARTNERS}: {target!r} has no region - fill it in first")

    plan, regions = {}, set()
    for tab in TABS:
        rows = tabs[tab]
        i_c, hits, clashes, regs = find_cells(rows, partner, old, new, target)
        if clashes:
            sys.exit(f"{tab}: {target!r} already has a club named {new!r} "
                     f"({describe_rows(clashes)}) - not merging two clubs")
        cols = {}           # column -> value, for the club's rows (and any that arrive late)
        if rows:
            if moving:
                cols[columns(rows)[0]] = target
            if renaming:
                cols[i_c] = new
        plan[tab] = (cols, hits)
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

    if moving:
        shared = sharing_partners(tabs["Roster"], (partner, target), {old, new})
        if shared:
            sys.exit(f"Roster: {', '.join(map(repr, shared))} also ha{'s' if len(shared) == 1 else 've'} "
                     f"a club named {old!r}{'' if new == old else f' or {new!r}'} - the forms "
                     "tell same-named clubs apart by partner; move this one by hand with a "
                     "sync dry run")
        if regions != {target_region}:
            sys.exit(f"Roster: the club's rows carry {sorted(regions) or 'no'} region, "
                     f"{target!r} is {target_region!r} - a move must not change the club's "
                     "attendance form; fix the regions first")
        left = sum(partner_count(tabs[t], partner) - len(plan[t][1]) for t in TABS)
        if not args.keep_old_partner and not left:
            retire = partner_rows(tabs[PARTNERS], partner)

    if moving:
        print(f"club {old!r}: partner {partner!r} -> {target!r}"
              + (f", name -> {new!r}" if renaming else ""))
        i_p = columns(tabs["Roster"])[0]
        exact = sum(1 for r in tabs["Roster"][1:] if cell(r, i_p) == target)
        print(f"  {target!r} as spelled in {PARTNERS} {describe_rows([n for n, *_ in found])} "
              f"(region {target_region}); {exact} Roster row(s) already carry that spelling")
    else:
        print(f"{partner}: club {old!r} -> {new!r}")
    for tab, (cols, hits) in plan.items():
        letters = ", ".join(col_letter(c) for c in sorted(cols))
        note = ("column " if len(cols) == 1 else "columns ") + letters if hits else "nothing to change"
        if tab == "ClubRegistry":
            note += f"; club_code {code} stays"
        print(f"  {tab:<14} {len(hits):>5} row(s)   {describe_rows(hits)}  ({note})")
    if moving:
        if retire:
            print(f"  {PARTNERS:<14} {len(retire):>5} row(s)   "
                  f"{describe_rows([n for n, *_ in retire])}  ({partner!r} blanked, note added)")
        elif args.keep_old_partner:
            print(f"  {PARTNERS:<14}     0 rows     ({partner!r} kept: --keep-old-partner)")
        elif left:
            print(f"  {PARTNERS:<14}     0 rows     ({partner!r} kept: {left} other row(s) "
                  "still name it)")
        else:
            print(f"  {PARTNERS:<14}     0 rows     ({partner!r} has no Partners row)")
    print(f"  {'Audit':<14} {1:>5} row appended")

    forms, client = [], None
    if not args.sheet_only:
        client = Client(api_key(", or pass --sheet-only"), apply=args.apply)
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
        # a question is found by its text alone. When another partner also has a club of
        # that name, the one question may be THAT club's - this club then has none (the sync
        # does not add a new club whose name is in use): never relabel another club's roster
        namesakes = sharing_partners(tabs["Roster"], (partner,), {old}) if renaming else []
        own = club_girls(tabs["Roster"], partner, old) if namesakes else set()
        for fid in ids:
            hits, clashes, girls = form_questions(client, fid, old, new)
            label = glow_forms.LABELS.get(fid, fid)
            if clashes:
                sys.exit(f"form {fid}: a roster question named {new!r} already exists "
                         f"(q{', q'.join(clashes)}) - not merging two clubs")
            if len(hits) > 1:
                sys.exit(f"form {fid}: {len(hits)} questions named {old!r} "
                         f"(q{', q'.join(hits)}) - fix the form first. (A club that is on no "
                         "form yet, because the sync did not add it while its name was in use, "
                         "is renamed with --sheet-only)")
            if not hits:
                print(f"  form {fid}: no roster question named {old!r} - nothing to "
                      f"{'rename' if renaming else 'check'} there"
                      + (f" (the next sync creates {new!r})" if renaming else ""))
                continue
            if namesakes:
                # the sync's own measure (its owner read-back): at least half of the girls
                # the question holds are this club's Roster rows, of any status
                have = girls[hits[0]]
                mine = len(have & own)
                if not have or mine * 2 < len(have):
                    sys.exit(f"form {fid}: q{hits[0]} is named {old!r} but holds another club's "
                             f"girls - {mine} of its {len(have)} are in the Roster under "
                             f"{partner!r}, and {', '.join(map(repr, namesakes))} also "
                             f"ha{'s' if len(namesakes) == 1 else 've'} a club of that name. "
                             f"{partner!r}'s club has no roster question on this form (the sync "
                             "does not add a new club whose name is in use). Nothing written: "
                             "rename it in the sheet only - run again with --sheet-only - and the "
                             "next sync creates its roster under the new name")
            if moving:
                props = client.get(f"/form/{fid}/properties")
                gated = partner_gated(props.get("conditions") or [], {hits[0]})
                if gated:
                    sys.exit(f"form {fid}: rule {', '.join(gated)} shows q{hits[0]} only for a "
                             "given Partner (the typed Partner box) - the name "
                             "is shared on this form, and a move would leave that rule on the "
                             "old partner until the next sync; sync the "
                             "form and check form_status first")
            if renaming:
                forms.append((fid, hits[0]))
                print(f"  form {fid}  q{hits[0]}: text {old!r} -> {new!r}   [{label}]")
            else:
                print(f"  form {fid}  q{hits[0]}: label stays; its show rule has no Partner "
                      f"term - nothing to write   [{label}]")
    elif moving:
        print("  forms          not checked (--sheet-only); --apply needs JOTFORM_API_KEY and "
              "checks that no rule shows the club only for a given Partner")

    if not args.apply:
        print("\nDRY RUN - re-run with --apply to write")
        return

    # the sheet's own zone, read once before anything is written (backups included): the
    # Audit `when` and the Partners note's date are in it, like the Apps Script's (the backup
    # stamp stays local). A zone that is no IANA name refuses here, with nothing written.
    zone = sc.named_zone(sc.time_zone(svc))

    # --- backups: the tabs as they are now, and a snapshot of each form written --
    stamp = backup.stamp(datetime.now())
    out = os.path.join(OUT, stamp)
    os.makedirs(out, exist_ok=True)
    for tab, rows in tabs.items():
        with open(os.path.join(out, tab + ".csv"), "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
    print(f"\nSaved the tabs before the change to {os.path.relpath(out, REPO)}/")
    for fid, _ in forms:
        s = backup.snapshot(fid, client, stamp)
        print(f"  backup_forms: form {fid} ({s['questions']} questions, {s['conditions']} "
              f"conditions) -> backups/{fid}/*-{stamp}.json")

    # --- the sheet: only the planned cells, RAW, in one batch -----------------
    writes = {tab: {n: dict(cols) for n in hits} for tab, (cols, hits) in plan.items()}
    if retire:
        hdr = [key(h) for h in tabs[PARTNERS][0]]
        i_p = hdr.index("partner")
        i_n = hdr.index("notes") if "notes" in hdr else None
        roster = tabs["Roster"]
        club = new if renaming else tidy(cell(roster[plan["Roster"][1][0] - 1], columns(roster)[1]))
        today = datetime.now(zone).strftime("%Y-%m-%d")
        writes[PARTNERS] = {}
        for n, spelled, _, notes in retire:
            note = (f"was '{spelled}': its club '{club}' moved to '{target}' on {today} "
                    "(tools/rename_club.py)" + (f"; earlier note: {notes}" if notes.strip() else ""))
            writes[PARTNERS][n] = {i_p: ""} if i_n is None else {i_p: "", i_n: note}

    # nothing written yet: a Club Roster Form submission since the read (a planned
    # row changed, a row of the club added or edited in, another club enrolled
    # under the partner whose Partners row is about to be blanked) means start over
    fresh = {}
    for tab, rows in writes.items():
        now = fresh[tab] = sc.read_tab(svc, tab)
        stale = [n for n in rows if n > len(now) or trimmed(now[n - 1]) != trimmed(tabs[tab][n - 1])]
        if tab in TABS:
            stale += sorted(set(find_cells(now, partner, old, new, target)[1]) - set(rows))
        if stale:
            sys.exit(f"{tab}: {describe_rows(stale)} changed since the plan was read (a form "
                     "submission?) - nothing written; run the tool again")
    if retire and sum(partner_count(fresh[t], partner) - len(plan[t][1]) for t in TABS):
        sys.exit(f"{partner!r} gained a row of another club since the plan was read, so its "
                 f"{PARTNERS} row must stay - nothing written; run the tool again")

    data = [{"range": a1(tab, f"{col_letter(c)}{n}"), "values": [[v]]}
            for tab, rows in writes.items() for n, cols in rows.items() for c, v in cols.items()]
    resp = svc.spreadsheets().values().batchUpdate(
        spreadsheetId=sc.spreadsheet_id(),
        body={"valueInputOption": "RAW", "data": data}).execute()
    if resp.get("totalUpdatedCells") != len(data):
        print(f"  note: Sheets reports {resp.get('totalUpdatedCells')} cell(s) updated for "
              f"{len(data)} sent - the re-read below decides")

    # re-read: every addressed row as planned (bar the cells a form handler may
    # flip meanwhile); elsewhere the written columns as they were - a row shift
    # shows there, an unrelated handler edit is not our business
    problems, late, afters = 0, {}, {}
    for tab, rows in writes.items():
        before, after = tabs[tab], sc.read_tab(svc, tab)
        afters[tab], free = after, handler_cells(before, tab)
        written = {c for cols in rows.values() for c in cols}
        if tab == PARTNERS:     # seedPartners_ may fill another row's notes; its partner cell must stay
            written = {[key(h) for h in before[0]].index("partner")}
        bad = 0
        for n, row in enumerate(before, start=1):
            got = after[n - 1] if n - 1 < len(after) else None
            if n in rows:
                expected = list(row)
                for c, v in rows[n].items():
                    expected += [""] * (c + 1 - len(expected))
                    expected[c] = v
                ok = got is not None and masked(got, free) == masked(expected, free)
            else:
                ok = got is not None and all(cell(got, c) == cell(row, c) for c in written)
            if not ok:
                bad += 1
                print(f"  ! {tab} row {n} differs after the write")
        stragglers = late_rows(after, len(before), partner, old) if tab in TABS else []
        if stragglers and tab == "ClubRegistry":
            bad += len(stragglers)
            print(f"  ! ClubRegistry {describe_rows(stragglers)}: a second row for {partner!r} / "
                  f"{old!r} appeared during the run (a new-club submission minted a code) - fix "
                  "the registry by hand; its late Roster rows are kept in the moved club, and "
                  "its SF Pending row is a duplicate request (no second Account)")
        elif stragglers:
            late[tab] = stragglers
            print(f"  note: {tab} {describe_rows(stragglers)} arrived during the run under "
                  f"{partner!r} / {old!r} - writing those too")
        elif len(after) > len(before):
            print(f"  note: {tab} gained {len(after) - len(before)} row(s) during the run "
                  "(a form submission?) - left alone")
        problems += bad
        if not bad:
            print(f"  {tab}: {sum(len(c) for c in rows.values())} cell(s) written and verified")
    if late:
        data = [{"range": a1(tab, f"{col_letter(c)}{n}"), "values": [[v]]}
                for tab, ns in late.items() for n in ns for c, v in plan[tab][0].items()]
        svc.spreadsheets().values().batchUpdate(
            spreadsheetId=sc.spreadsheet_id(),
            body={"valueInputOption": "RAW", "data": data}).execute()
        for tab, ns in late.items():
            now, free, off = sc.read_tab(svc, tab), handler_cells(afters[tab], tab), []
            for n in ns:            # the whole row as it was read, with the planned cells applied
                expected = list(afters[tab][n - 1])
                for c, v in plan[tab][0].items():
                    expected += [""] * (c + 1 - len(expected))
                    expected[c] = v
                if n > len(now) or masked(now[n - 1], free) != masked(expected, free):
                    off.append(n)
            for n in off:
                print(f"  ! {tab} row {n} differs after the write - it should be the club's row "
                      f"under {target!r} / {new!r}; set it by hand")
            problems += len(off)
            if not off:
                print(f"  {tab}: {len(ns)} late row(s) written and verified")
    if problems:
        sys.exit(f"{problems} row(s) did not verify - the tabs as they were are in "
                 f"{os.path.relpath(out, REPO)}/ (no Audit row written)")
    moved = {t: len(plan[t][1]) + len(late.get(t, [])) for t in TABS}
    what = (f"partner '{partner}' -> '{target}'" if moving else "")
    what += ("; " if moving and renaming else "") + (f"name -> '{new}'" if renaming else "")
    detail = ((f"club '{old}': {what}" if moving else f"{partner}: club '{old}' -> '{new}'")
              + f" ({moved['Roster']} Roster rows, ClubRegistry {code} kept, "
              f"{moved['SF Pending']} SF Pending rows"
              + (f"; Partners {describe_rows([n for n, *_ in retire])} '{partner}' blanked"
                 if retire else "")
              + (f"; forms {', '.join(f'{f} q{q}' for f, q in forms)}" if forms else "")
              + ") - tools/rename_club.py")
    sc.append_rows(svc, "Audit", [[datetime.now(zone).strftime("%Y-%m-%d %H:%M:%S"),
                                   "moveClub" if moving else "renameClub", detail]])
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

    region = next(iter(regions)) if len(regions) == 1 else "<region>"
    region_form = glow_forms.REGIONALS.get(region) or (forms[0][0] if forms else "<form id>")
    if moving:
        print("\nNext (docs/RUNBOOK.md, \"Moving a club to another partner\"):")
        print("  In the sheet, now: GLOW -> Google Forms -> Update form dropdowns from the Roster")
        print(f"    (until then the Club Roster Form lists the club under {partner!r}; a change "
              "sent that way is skipped and never retried -")
        print(f"    ReviewQueue 'Roster change for a club not on file' under {partner!r} = ask "
              "the partner to send it again)")
    elif not forms:
        # nothing was renamed on a form (--sheet-only, or no form has a question of the old
        # name): the next sync CREATES the club's roster - no Account to rename, no flag
        print("\nNext (docs/RUNBOOK.md, \"Club names two partners share\"): no roster question "
              "was renamed, so the next")
        print("  sync creates this club's roster under its new name. Salesforce: the club sent "
              "nothing yet - if an Account was")
        print("  already made for it under the old name, rename that Account; no --q5-change-ok "
              "is involved.")
        print("  If the club DOES have its own roster question under the old name, stop and run "
              "this again without --sheet-only.")
    else:
        print("\nNext (docs/RUNBOOK.md, \"Renaming a club\"): the sync rewrites the picker "
              "options and the rules -")
    print("  python3 tools/sheets_client.py export Roster data/roster_<date>.csv")
    if renaming and not forms:
        print(f"  python3 tools/auto_sync.py --region {region!r}     # dry run: CREATE roster {new!r}, "
              "and no 'not added' line for it")
    elif renaming:
        # the club's name is what question 5 sends to Salesforce: the sync lists the change
        # and applies it only with --q5-change-ok (docs/plans/2026-09-30-same-name-clubs.md)
        print("  Salesforce: rename the club's Account to the new name FIRST (the dry run's "
              "'!' line gives the exact text)")
        print(f"  python3 sync_attendance_form.py data/roster_<date>.csv --roster "
              f"--region {region!r} --form {region_form}      # dry run, then --apply --q5-change-ok")
        print(f"  python3 sync_attendance_form.py data/roster_<date>.csv --roster "
              f"--form {glow_forms.TEMPLATE}                       # the template, same")
    else:
        print(f"  python3 tools/auto_sync.py --region {region!r}     # dry run: in-sync "
              "(a CREATE for this club means stop)")
    print(f"  python3 tools/form_status.py --form {region_form} --roster data/roster_<date>.csv"
          "   # CLEAN")
    if not moving:
        print("  In the sheet: GLOW -> Google Forms -> Update form dropdowns from the Roster")


if __name__ == "__main__":
    run(main)
