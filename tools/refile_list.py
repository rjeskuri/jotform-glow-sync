#!/usr/bin/env python3
"""
The club -> partner list for the photo mover's one-time re-filing of the club folders already on
the Shared Drive (ticket #237, docs/plans/2026-11-23-refile-photo-folders.md): read-only, files
only, no network.

The folders the mover filed before #225 are named `<Club Name> <MM-DD-YYYY>` or the club alone,
with no partner. drive-sync/Refile.gs finds each one's partner in REFILE_LIST, which this tool
writes once as an Apps Script file (`const REFILE_LIST = [...]`, one {"region", "partner",
"club"} object per line, sorted by region, partner, club). Ryan pastes it into the mover project
beside Refile.gs for the re-filing and deletes it from there afterwards; the mover reads no sheet.

  rows     one per distinct partner + club (compared with glow.text.key) of EVERY Roster row that
           has both cells, any status: old folders belong to clubs now inactive or retired.
           Spelled as glow.sync.roster_pairs spells them (whitespace collapsed; the first active
           row's spelling, else the first row's): the partner string the Partner fill (#236)
           writes into question 331, so a re-filed folder lands in the partner folder new photos
           use.
  region   the club's Roster region (glow.forms.canonical_region), one row per region when its
           rows have two; when none of its rows has one, its partner's region on the Partners tab;
           else blank (the mover then matches it from every region).
  --extra  a CSV with the columns region, partner and club: rows added, e.g. for a club renamed
           since its folders were made (after a dry run lists it as no-partner). A row equal to a
           list row is dropped. Refused, naming the line: a blank partner or club, or a region that
           is neither blank nor one of the regions (spelled any way: `africa` is Africa).

Refused, and nothing written: a file that is not a Roster export, a Partners export without the
partner and region columns, an --extra file without its columns or with a bad row, no club at all,
and an --out inside the repository outside data/ (the list holds the real club names). Prints
counts only; club and partner names go to the file, never a girl's name anywhere.

Usage:
    python3 tools/sheets_client.py export Roster data/roster_<date>.csv
    python3 tools/sheets_client.py export Partners data/partners_<date>.csv
    python3 tools/refile_list.py --roster data/roster_<date>.csv \\
        --partners data/partners_<date>.csv [--extra <csv>] [--out data/RefileList.gs]
"""
import argparse
import csv
import datetime
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow.forms import REGIONS, canonical_region                  # noqa: E402
from glow.sync import _partners_rows, _roster_rows, roster_pairs  # noqa: E402  (the Roster read as the sync reads it)
from glow.text import key                                         # noqa: E402

OUT = os.path.join("data", "RefileList.gs")
COLUMNS = ("region", "partner", "club")


def collapse(text):
    return " ".join(str(text or "").split())


def read_clubs(roster_csv):
    """[(partner, club, [region, ...])]: every club of the Roster export (any status) in its
    roster_pairs spelling, with the distinct regions its rows give, in the order first seen."""
    spelled = {(key(p), key(c)): (p, c) for p, c in roster_pairs(roster_csv)}
    regions = {}
    for r in _roster_rows(roster_csv):
        k = (key(r["partner"]), key(r["club"]))
        if k not in spelled:
            continue
        found = regions.setdefault(k, [])
        region = canonical_region(r["region"])
        if region and region not in found:
            found.append(region)
    return [(*spelled[k], regions.get(k, [])) for k in spelled]


def read_partner_regions(partners_csv):
    """{key(partner): region} from a Partners export: the first non-blank region of the partner's
    rows (glow.forms.canonical_region)."""
    rows, header = _partners_rows(partners_csv)
    if "region" not in header:
        sys.exit(f"--partners {partners_csv}: expected a 'region' column (the Partners tab's export)")
    i_p, i_r = header.index("partner"), header.index("region")
    out = {}
    for row in rows[1:]:
        partner = key(row[i_p]) if i_p < len(row) else ""
        region = canonical_region(row[i_r]) if i_r < len(row) else ""
        if partner and region:
            out.setdefault(partner, region)
    return out


def read_extra(path):
    """[(region, partner, club)] from an --extra CSV; every bad line refused at once."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    header = [key(h) for h in rows[0]] if rows else []
    if not set(COLUMNS) <= set(header):
        sys.exit(f"--extra {path}: expected the columns region, partner and club")
    at = {c: header.index(c) for c in COLUMNS}
    out, problems = [], []
    for n, row in enumerate(rows[1:], 2):
        if not any(cell.strip() for cell in row):
            continue
        cell = {c: collapse(row[i]) if i < len(row) else "" for c, i in at.items()}
        region = canonical_region(cell["region"])
        bad = [what for what, wrong in (("no partner", not cell["partner"]), ("no club", not cell["club"]),
                                        (f"the region '{cell['region']}' is not blank or one of "
                                         + ", ".join(REGIONS), region and region not in REGIONS)) if wrong]
        if bad:
            problems.append(f"  line {n}: " + "; ".join(bad))
            continue
        out.append((region, cell["partner"], cell["club"]))
    if problems:
        sys.exit(f"--extra {path}: refused, nothing written:\n" + "\n".join(problems))
    return out


def check_out(path):
    """Refuse an --out inside the repository but outside data/ (it would be committable)."""
    real = os.path.realpath(path)
    repo, data = os.path.realpath(REPO), os.path.realpath(os.path.join(REPO, "data"))
    inside = lambda p, d: os.path.commonpath([p, d]) == d
    if inside(real, repo) and not inside(real, data):
        sys.exit(f"--out {path}: inside the repository but outside data/; the list holds the real club "
                 "names - write it in data/ or outside the repository")


def gs_line(region, partner, club):
    text = json.dumps({"region": region, "partner": partner, "club": club}, ensure_ascii=False)
    # JSON allows U+2028 / U+2029 raw in a string, older JavaScript did not: escaped, the same string
    return "  " + text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 allow_abbrev=False)
    ap.add_argument("--roster", required=True, help="a Roster export (tools/sheets_client.py export Roster ...)")
    ap.add_argument("--partners", required=True,
                    help="a Partners export: the region of a club whose Roster rows have none")
    ap.add_argument("--extra", help="a CSV with the columns region, partner, club: rows to add")
    ap.add_argument("--out", default=OUT, help=f"the Apps Script file to write (default {OUT})")
    args = ap.parse_args(argv)
    check_out(args.out)

    clubs = read_clubs(args.roster)
    partner_region = read_partner_regions(args.partners)
    if not clubs:
        sys.exit(f"--roster {args.roster}: no row has both a partner and a club; nothing written")
    rows, by = [], {"roster": 0, "partners": 0, "blank": 0}
    for partner, club, regions in clubs:
        if regions:
            by["roster"] += len(regions)
        else:
            regions = [partner_region.get(key(partner), "")]
            by["partners" if regions[0] else "blank"] += 1
        rows += [(region, partner, club) for region in regions]
    listed = set(rows)
    extra = read_extra(args.extra) if args.extra else []
    added = []
    for row in extra:
        if row not in listed:
            listed.add(row)
            added.append(row)
    rows = sorted(rows + added)

    sources = [os.path.basename(p) for p in (args.roster, args.partners, args.extra) if p]
    text = "\n".join([
        "// RefileList.gs: the club -> partner list for the photo mover's one-time re-filing (ticket #237,",
        "// drive-sync/Refile.gs; docs/plans/2026-11-23-refile-photo-folders.md). Generated "
        f"{datetime.date.today().isoformat()} by",
        f"// tools/refile_list.py from {', '.join(sources)}: {len(rows)} row(s), {len(clubs)} club(s) of the Roster",
        f"// ({by['roster']} row(s) with a Roster region, {by['partners']} with the partner's region on the Partners tab, "
        f"{by['blank']} with none), {len(added)} added by --extra.",
        "// Paste it into the mover project beside Refile.gs for the re-filing only (previewRefile, refileExisting),",
        "// and delete it from there afterwards. Club and partner names only.",
        "const REFILE_LIST = [",
        ",\n".join(gs_line(*row) for row in rows),
        "];",
        "",
    ])
    if os.path.dirname(args.out):
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"refile_list: wrote {args.out}: {len(rows)} row(s) for {len(clubs)} club(s) of the Roster "
          f"({by['roster']} with a Roster region, {by['partners']} with the Partners tab's, {by['blank']} with none); "
          f"--extra: {len(added)} added, {len(extra) - len(added)} already listed")
    if by["blank"]:
        print(f"  {by['blank']} row(s) have no region: the mover matches them from every region")
    print("Next: paste it into the mover project beside Refile.gs and run previewRefile "
          "(docs/plans/2026-11-23-refile-photo-folders.md, Rollout)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
