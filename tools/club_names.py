#!/usr/bin/env python3
"""
Club names that look alike across partners and regions (ticket #94): read-only, files only.

  similar  every club of the Roster (one per partner + club, compared with glow.text.key, any
           status) compared with every other; the lookalikes printed in groups (connected
           components: a chain of lookalikes is one group), each club with its partner, region
           and the form it is on. A pair is
             same    equal names apart from case and spacing (glow.text.key)
             folded  equal once accents, punctuation and spacing are folded away (fold)
             close   folded names at least --threshold alike (difflib ratio) that carry the
                     same numbers in the same order ("Club 1" and "Club 2" never match)
           A club's `match` is the strongest kind joining it to its group; a group counts under
           the weakest kind of link it needs to be one group (same when its same pairs alone
           connect it, else folded when same and folded pairs do, else close). --csv (its
           folder made when missing) writes one row per grouped club; --countries (partner,country)
           and --sf-names (the sync's --summary-json files: what each club sends to question 5)
           fill the country and sf_name columns.

Prints club and partner names, regions and counts, never a girl's name. No network: the Roster
and Partners exports come from tools/sheets_client.py.

Usage:
    python3 tools/sheets_client.py export Roster data/roster_<date>.csv
    python3 tools/sheets_client.py export Partners data/partners_<date>.csv
    python3 tools/club_names.py similar --roster data/roster_<date>.csv \\
        --partners data/partners_<date>.csv [--countries <csv>] [--sf-names <summary.json> ...] \\
        [--threshold 0.85] [--csv data/similar_clubs.csv]
"""
import argparse
import csv
import difflib
import json
import os
import re
import sys
import unicodedata

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow.forms import TITLES, canonical_region         # noqa: E402
from glow.sync import _roster_rows, read_partners_csv   # noqa: E402  (headers read as the sync reads them)
from glow.text import key                               # noqa: E402

THRESHOLD = 0.85
KINDS = ("same", "folded", "close")                     # strongest first
CSV_COLUMNS = ["group", "match", "club", "partner", "region", "form", "country", "sf_name",
               "status", "active_girls", "same_partner"]
DROPPED = str.maketrans("", "", ".'’`")            # removed outright: "G.L.O.W." -> "glow"


def fold(name):
    """A club name with case, accents (NFKD, combining marks dropped), punctuation and spacing
    folded away: . ' ’ ` removed, every other character but a letter or digit a space."""
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower().translate(DROPPED)
    return " ".join("".join(c if c.isalnum() else " " for c in s).split())


def _kind(key_a, key_b, fold_a, fold_b, threshold):
    if key_a == key_b:
        return "same"
    if fold_a == fold_b:
        return "folded"
    if re.findall(r"\d+", fold_a) != re.findall(r"\d+", fold_b):
        return None
    sm = difflib.SequenceMatcher(None, fold_a, fold_b)
    # real_quick_ratio and quick_ratio are upper bounds of ratio: cheap rejections first
    if sm.real_quick_ratio() >= threshold and sm.quick_ratio() >= threshold and sm.ratio() >= threshold:
        return "close"
    return None


def match_kind(a, b, threshold=THRESHOLD):
    """"same", "folded", "close" or None for two club names (see the module's docstring)."""
    return _kind(key(a), key(b), fold(a), fold(b), threshold)


def read_clubs(roster_csv):
    """[club dict] from a Roster export: one per key(partner) + key(club), any status, rows
    without a partner or a club skipped. Spelling and region come from the club's first active
    row (status active and a name, as glow.sync.roster_pairs reads it), else its first row."""
    found = {}
    for r in _roster_rows(roster_csv):
        partner, club = " ".join(r["partner"].split()), " ".join(r["club"].split())
        if not (partner and club):
            continue
        active = key(r["status"]) == "active" and bool(r["full_name"].strip())
        c = found.get((key(partner), key(club)))
        if c is None:
            c = found[(key(partner), key(club))] = {"club": club, "partner": partner,
                                                    "region": r["region"], "active_girls": 0}
        if active:
            if not c["active_girls"]:
                c.update(club=club, partner=partner, region=r["region"])
            c["active_girls"] += 1
    for c in found.values():
        c["region"] = canonical_region(c["region"])
    return list(found.values())


def read_countries(path):
    """{key(partner): country} from a partner,country CSV (headers matched by key)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    header = [key(h) for h in rows[0]] if rows else []
    if not {"partner", "country"} <= set(header):
        sys.exit(f"--countries {path}: expected the columns partner and country")
    i_p, i_c = header.index("partner"), header.index("country")
    out = {}
    for r in rows[1:]:
        partner = key(r[i_p]) if i_p < len(r) else ""
        country = " ".join(r[i_c].split()) if i_c < len(r) else ""
        if partner and country:
            out.setdefault(partner, country)
    return out


def read_sf_names(paths):
    """{(key(partner), key(club)): value} from the sync's --summary-json files; a club found
    with two different values shows both, joined by "; "."""
    out = {}
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                entries = json.load(f).get("sf_names")
        except (OSError, ValueError, AttributeError) as err:
            sys.exit(f"--sf-names {path}: not a sync --summary-json file ({err})")
        if not isinstance(entries, list):
            sys.exit(f"--sf-names {path}: no sf_names list - write it with the sync's --summary-json")
        for e in entries:
            k = (key(e.get("partner")), key(e.get("club")))
            value = " ".join(str(e.get("value") or "").split())
            if k[0] and k[1] and value:
                values = out.setdefault(k, [])
                if value not in values:
                    values.append(value)
    return {k: "; ".join(v) for k, v in out.items()}


def form_of(club, marks):
    if marks.get(key(club["partner"])) == "no":
        return "retired (jotform=no)"
    if not club["active_girls"]:
        return "none (no active girl)"
    if club["region"] not in TITLES:
        return "none (no region)"
    return TITLES[club["region"]]


def _components(nodes, links):
    """The connected components of `nodes` over `links` [(i, j)] (union-find)."""
    parent = {n: n for n in nodes}

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, j in links:
        parent[root(i)] = root(j)
    out = {}
    for n in nodes:
        out.setdefault(root(n), []).append(n)
    return list(out.values())


def groups_of(clubs, threshold):
    """[(kind, [club, ...])]: the connected components of the lookalike pairs, each club carrying
    its strongest `match`, each group the weakest kind of link it needs to be one group (`same`
    when its same pairs alone connect it, else `folded` when same and folded pairs do, else
    `close`); groups and clubs sorted by folded name, then partner."""
    keys = [key(c["club"]) for c in clubs]
    folds = [fold(c["club"]) for c in clubs]
    links = []                                          # (i, j, rank of the pair's kind)
    for i in range(len(clubs)):
        for j in range(i + 1, len(clubs)):
            kind = _kind(keys[i], keys[j], folds[i], folds[j], threshold)
            if kind is not None:
                links.append((i, j, KINDS.index(kind)))
    best = {}                                           # club index -> rank of its strongest kind
    for i, j, rank in links:
        for n in (i, j):
            best[n] = min(best.get(n, rank), rank)
    order = lambda i: (folds[i], keys[i], key(clubs[i]["partner"]))
    out = []
    for idx in _components(sorted(best), [(i, j) for i, j, _ in links]):
        idx.sort(key=order)
        mine = set(idx)
        inside = [(i, j, rank) for i, j, rank in links if i in mine]
        kind = next((KINDS[r] for r in range(len(KINDS) - 1)
                     if len(_components(idx, [(i, j) for i, j, rank in inside if rank <= r])) == 1),
                    KINDS[-1])
        out.append((kind, [dict(clubs[i], match=KINDS[best[i]]) for i in idx]))
    out.sort(key=lambda g: (fold(g[1][0]["club"]), key(g[1][0]["club"]), key(g[1][0]["partner"])))
    return out


def similar(args):
    if not 0 < args.threshold <= 1:
        sys.exit("--threshold: a ratio above 0 and at most 1 (default 0.85)")
    clubs = read_clubs(args.roster)
    marks = read_partners_csv(args.partners)
    countries = read_countries(args.countries) if args.countries else {}
    sf_names = read_sf_names(args.sf_names or [])
    groups = groups_of(clubs, args.threshold)

    rows = []
    weakest = {kind: 0 for kind in KINDS}
    for n, (kind, group) in enumerate(groups, 1):
        same_partner = "yes" if len({key(c["partner"]) for c in group}) == 1 else "no"
        weakest[kind] += 1
        for c in group:
            rows.append({
                "group": n, "match": c["match"], "club": c["club"], "partner": c["partner"],
                "region": c["region"], "form": form_of(c, marks),
                "country": countries.get(key(c["partner"]), ""),
                "sf_name": sf_names.get((key(c["partner"]), key(c["club"])), ""),
                "status": "active" if c["active_girls"] else "inactive",
                "active_girls": c["active_girls"], "same_partner": same_partner})

    print(f"groups: {len(groups)} (same {weakest['same']}, folded {weakest['folded']}, "
          f"close {weakest['close']}); clubs in them: {len(rows)}")
    for n, (kind, _) in enumerate(groups, 1):
        mine = [r for r in rows if r["group"] == n]
        print(f"\ngroup {n}: {kind}"                    # the weakest link it needs, as counted
              + (", one partner" if mine[0]["same_partner"] == "yes" else ""))
        for r in mine:
            extra = "".join(f", {label} {r[col]}" for label, col in (("country", "country"),
                                                                      ("sends", "sf_name")) if r[col])
            print(f"  [{r['match']}] {r['club']}  -  partner {r['partner']}, region "
                  f"{r['region'] or '(blank)'}, form {r['form']}, {r['active_girls']} active{extra}")

    if args.csv:
        os.makedirs(os.path.dirname(os.path.abspath(args.csv)), exist_ok=True)   # as sheets_client's export
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            w.writeheader()
            w.writerows(rows)
        print(f"\nwrote {args.csv} ({len(rows)} rows)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 allow_abbrev=False)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sim = sub.add_parser("similar", allow_abbrev=False, help="read-only: club names that look alike")
    sim.add_argument("--roster", required=True, help="a Roster export (tools/sheets_client.py export Roster ...)")
    sim.add_argument("--partners", required=True, help="a Partners export: its jotform=no marks retire a partner's clubs")
    sim.add_argument("--countries", help="a partner,country CSV: fills the country column")
    sim.add_argument("--sf-names", action="append", metavar="SUMMARY_JSON",
                     help="a sync --summary-json file (repeatable): fills the sf_name column")
    sim.add_argument("--threshold", type=float, default=THRESHOLD,
                     help=f"the lowest difflib ratio of a close pair (default {THRESHOLD})")
    sim.add_argument("--csv", help="also write the groups to this CSV, one row per club")
    args = ap.parse_args(argv)
    return similar(args)


if __name__ == "__main__":
    sys.exit(main())
