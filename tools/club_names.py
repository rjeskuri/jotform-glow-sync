#!/usr/bin/env python3
"""
Club names that look alike across partners and regions (ticket #94), and the plan to rename clubs
into a format that shows their country (ticket #95): read-only, files only.

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
  plan-renames
           every active club in scope (--scope all, or similar: the clubs --similar-csv, what
           `similar --csv` writes, lists; a partner marked jotform=no is retired, not planned)
           gets new_club = --format filled in ({country} from --countries, {club}, {partner},
           {region}; whitespace collapsed) and new_sf_name = glow.sync.sf_club_name(new_club,
           partner, long), long when its question 5 (--sf-names) is "<club> - <partner>" and
           --keep-long yes. A club already in the format (compared with glow.text.key) is
           `unchanged`. Refused, every club named at once and no --out written: no country (or
           no region the format needs); "|", "{" or "}" in the name; two new_sf_names equal by
           key, or one equal to the question 5 of a club not planned (one Salesforce Account); a
           new_club another partner's club has after the renames (any status) unless its
           new_sf_name is the long form; a new_sf_name over 255 characters. Renames nothing.

Prints club and partner names, regions and counts, never a girl's name. No network: the Roster
and Partners exports come from tools/sheets_client.py.

Usage:
    python3 tools/sheets_client.py export Roster data/roster_<date>.csv
    python3 tools/sheets_client.py export Partners data/partners_<date>.csv
    python3 tools/club_names.py similar --roster data/roster_<date>.csv \\
        --partners data/partners_<date>.csv [--countries <csv>] [--sf-names <summary.json> ...] \\
        [--threshold 0.85] [--csv data/similar_clubs.csv]
    python3 tools/club_names.py plan-renames --roster data/roster_<date>.csv \\
        --partners data/partners_<date>.csv --countries <csv> --sf-names <summary.json> ... \\
        --format "{country} - {club}" --scope all|similar [--similar-csv <csv>] \\
        --keep-long yes|no --out data/club_names/renames_<date>.csv
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
from glow.sync import (SF_NAME_SEP, long_name_partner, sf_club_name,  # noqa: E402
                       sf_name_clashes, shared_club_names)
from glow.text import key                               # noqa: E402

THRESHOLD = 0.85
KINDS = ("same", "folded", "close")                     # strongest first
CSV_COLUMNS = ["group", "match", "club", "partner", "region", "form", "country", "sf_name",
               "status", "active_girls", "same_partner"]
DROPPED = str.maketrans("", "", ".'’`")            # removed outright: "G.L.O.W." -> "glow"
PLAN_COLUMNS = ["partner", "club", "region", "old_sf_name", "new_club", "new_sf_name", "action"]
PLACEHOLDERS = ("country", "club", "partner", "region")
PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
BAD_CHARS = "|{}"                                       # the sync refuses them in a club name
SF_NAME_MAX = 255                                       # Salesforce's Account Name


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


def read_similar_csv(path):
    """{(key(partner), key(club))} of the clubs a `similar --csv` file lists."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if rows and not {"partner", "club"} <= set(rows[0]):
        sys.exit(f"--similar-csv {path}: expected the columns partner and club (what `similar --csv` writes)")
    return {(key(r["partner"]), key(r["club"])) for r in rows if key(r["partner"]) and key(r["club"])}


def fill_format(fmt, values):
    """The format with each {placeholder} replaced from `values`, whitespace collapsed; any other
    brace stays as written (and is refused as a bad character)."""
    return " ".join(PLACEHOLDER.sub(lambda m: values[m.group(1)], fmt).split())


def in_format(fmt, club, values):
    """Whether `club` already is the format filled in for some club name, compared with
    glow.text.key: "Kenya - Lotus Club" is in "{country} - {club}" for a partner in Kenya, and a
    renamed club stays as it is on a second run."""
    mark = "\0"                                         # stands for {club}: never in a name
    parts = key(fill_format(fmt, dict(values, club=mark))).split(mark)
    pattern = re.escape(parts[0])
    for n, part in enumerate(parts[1:]):
        pattern += ("(.+)" if n == 0 else r"\1") + re.escape(part)
    return re.fullmatch(pattern, key(club)) is not None


def plan_renames(args):
    unknown = sorted({p for p in PLACEHOLDER.findall(args.format) if p not in PLACEHOLDERS})
    if unknown:
        sys.exit("--format: unknown placeholder " + ", ".join("{" + p + "}" for p in unknown)
                 + " - use " + ", ".join("{" + p + "}" for p in PLACEHOLDERS))
    if args.scope == "similar" and not args.similar_csv:
        sys.exit("--scope similar needs --similar-csv (the CSV `similar --csv` writes)")
    if args.scope == "all" and args.similar_csv:
        sys.exit("--similar-csv goes with --scope similar; --scope all plans every active club")
    clubs = read_clubs(args.roster)
    marks = read_partners_csv(args.partners)
    countries = read_countries(args.countries)
    sf_names = read_sf_names(args.sf_names)
    listed = read_similar_csv(args.similar_csv) if args.scope == "similar" else None
    uses_region = "region" in PLACEHOLDER.findall(args.format)
    ident = lambda c: (key(c["partner"]), key(c["club"]))
    by_id = {ident(c): c for c in clubs}

    planned, plans, refused = [], {}, {}                # refused: ident -> [reason, ...]
    for c in clubs:
        if (not c["active_girls"] or marks.get(key(c["partner"])) == "no"
                or (listed is not None and ident(c) not in listed)):
            continue                                    # inactive, retired or out of scope: keeps its name
        planned.append(c)
        country = countries.get(key(c["partner"]))
        if not country:
            refused.setdefault(ident(c), []).append("no country for its partner in --countries")
        if uses_region and not c["region"]:
            refused.setdefault(ident(c), []).append("no region, and the format has {region}")
        if ident(c) in refused:
            continue
        old = sf_names.get(ident(c), "")
        long = (args.keep_long == "yes"
                and long_name_partner(old, c["club"], {key(c["partner"]): c["partner"]}) is not None)
        values = {"country": country, "club": c["club"], "partner": c["partner"], "region": c["region"]}
        new_club = c["club"] if in_format(args.format, c["club"], values) else fill_format(args.format, values)
        new_sf = sf_club_name(new_club, c["partner"], long)
        unchanged = new_club == c["club"] and (not old or key(old) == key(new_sf))
        plans[ident(c)] = {"partner": c["partner"], "club": c["club"], "region": c["region"],
                           "old_sf_name": old, "new_club": new_club, "new_sf_name": new_sf,
                           "action": "unchanged" if unchanged else "rename", "long": long}

    for k, p in plans.items():
        bad = [ch for ch in BAD_CHARS if ch in p["new_sf_name"]]
        if bad:
            refused.setdefault(k, []).append(f"'{p['new_sf_name']}' has {' '.join(bad)} (the sync refuses them)")
        if len(p["new_sf_name"]) > SF_NAME_MAX:
            refused.setdefault(k, []).append(f"its new_sf_name has {len(p['new_sf_name'])} characters "
                                             f"(a Salesforce Account Name takes {SF_NAME_MAX})")
    # one Salesforce Account per question-5 value: the new values, and those of the clubs keeping theirs
    names = [(p["new_sf_name"], k) for k, p in plans.items()]
    names += [(sf_names[k], k) for k in by_id if k not in plans and sf_names.get(k)]
    for _value, who in sf_name_clashes(names):
        for k in who:
            if k in plans:
                others = ", ".join(f"{by_id[w]['club']} ({by_id[w]['partner']})" for w in who if w != k)
                refused.setdefault(k, []).append(f"new_sf_name '{plans[k]['new_sf_name']}' equals (by key) "
                                                 f"what {others} would send: one Salesforce Account")
    # the sync's rule 2 on the names after the renames: a name two partners have needs the long form
    after = {(c["partner"], plans[ident(c)]["new_club"] if ident(c) in plans else c["club"]): True
             for c in clubs}
    shared = shared_club_names(after)
    for k, p in plans.items():
        if key(p["new_club"]) in shared and not p["long"]:
            refused.setdefault(k, []).append(
                f"another partner's club is named '{p['new_club']}' (by key): it needs the long name "
                f"'{p['new_club']}{SF_NAME_SEP}{p['partner']}' (RUNBOOK \"Club names two partners share\")")

    rows = sorted((p for k, p in plans.items() if k not in refused),
                  key=lambda p: (key(p["partner"]), key(p["club"])))
    missing = [p for p in rows if not p["old_sf_name"]]
    if missing:
        print(f"note: {len(missing)} clubs have no question 5 in --sf-names (planned as plain names): "
              + "; ".join(f"{p['club']} ({p['partner']})" for p in missing))
    if refused:
        print(f"REFUSED: {len(refused)} clubs")
        for c in sorted(planned, key=lambda c: (key(c["partner"]), key(c["club"]))):
            for reason in refused.get(ident(c), []):
                print(f"  {c['club']}  -  partner {c['partner']}: {reason}")
    count = {a: sum(1 for p in rows if p["action"] == a) for a in ("rename", "unchanged")}
    print(f"to rename {count['rename']}, unchanged {count['unchanged']}, refused {len(refused)}")
    if refused:
        sys.exit(f"plan refused for {len(refused)} clubs (listed above), --out not written: fix the names, "
                 "--countries or --format and run it again")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PLAN_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {args.out} ({len(rows)} rows)")
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
    plan = sub.add_parser("plan-renames", allow_abbrev=False,
                          help="read-only: every active club's new name from a format, and its question 5")
    plan.add_argument("--roster", required=True, help="a Roster export (tools/sheets_client.py export Roster ...)")
    plan.add_argument("--partners", required=True, help="a Partners export: a partner marked jotform=no is not planned")
    plan.add_argument("--countries", required=True, help="a partner,country CSV: each partner's {country}")
    plan.add_argument("--sf-names", required=True, action="append", metavar="SUMMARY_JSON",
                      help="a sync --summary-json file (repeatable): each club's current question 5")
    plan.add_argument("--format", required=True, help='the new club name, e.g. "{country} - {club}"; '
                      "placeholders " + ", ".join("{" + p + "}" for p in PLACEHOLDERS))
    plan.add_argument("--scope", required=True, choices=("all", "similar"),
                      help="all: every active club; similar: the clubs --similar-csv lists")
    plan.add_argument("--similar-csv", help="with --scope similar: the CSV `similar --csv` wrote")
    plan.add_argument("--keep-long", required=True, choices=("yes", "no"),
                      help="whether a club whose question 5 is '<club> - <partner>' keeps the partner suffix")
    plan.add_argument("--out", required=True, help="the plan CSV, written only when no club is refused")
    args = ap.parse_args(argv)
    return plan_renames(args) if args.cmd == "plan-renames" else similar(args)


if __name__ == "__main__":
    sys.exit(main())
