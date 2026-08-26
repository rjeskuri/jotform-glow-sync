#!/usr/bin/env python3
"""
The list of things a human has to chase down before the roster is trustworthy.

Reads the enrollment CSV (and the regional-form snapshots in backups/ when
present) and writes data/needs_attention_<date>.csv: one row per question,
with the partner, the club, what looks wrong, and what would resolve it.

Checks, roughly in order of how much they matter:
  DUPLICATE_NAME       a roster lists the same full name twice
  IDENTICAL_NAMES      the partner said "yes, girls share a name" on the form
  POSSIBLE_SAME_CLUB   two clubs of one partner share most of their girls:
                       a respelled club name, or a stale combined club that
                       has since been split
  RENAMED_ON_FORM      a club is on a regional attendance form under a
                       different name than in the sheet - the sync matches by
                       name, so it would add a second question
  RESUBMITTED          a club was submitted again and names from the earlier
                       submission are missing from the newest one, after
                       accounting for respellings and moves to sibling clubs
  GIRL_IN_TWO_CLUBS    the same name appears in two clubs of one partner
  CLUB_NAMED_AFTER_GIRL the club name is one of its girls' names
  ODD_LINE             a roster line with 6+ words (two names on one line?)
                       or a single-word name
  COUNT_MISMATCH       "number of girls" answer differs from names listed by 3+
  TINY_CLUB            fewer than 5 names
  ON_FORM_NOT_SHEET    a club exists on a regional attendance form but not in
                       the sheet - does it still exist?
  REGION_UNSURE        partner region derived from thin evidence

Usage:
    python3 tools/needs_attention.py data/enrollment_2026-08-24.csv [--out FILE]
"""
import argparse
import csv
import difflib
import importlib.util
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import derive_partner_regions as regions  # noqa: E402

COLUMNS = ["priority", "issue", "partner", "club", "detail", "what_to_do",
           "sheet_row", "resolved"]
SIMILAR = 0.8          # difflib ratio at which two names count as a respelling


def key(s):
    return " ".join(str(s or "").split()).lower()


def name_key(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split()).lower()


def similar(a, b):
    return difflib.SequenceMatcher(None, name_key(a), name_key(b)).ratio()


def load_sync():
    spec = importlib.util.spec_from_file_location(
        "sync", os.path.join(REPO, "sync_attendance_form.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def find_col(header, fragment):
    for i, h in enumerate(header):
        if fragment in h.lower():
            return i
    return None


def club_stem(c):
    return re.sub(r"\b(primaria|secundaria|glow|g\.l\.o\.w\.?|club|girls?)\b", "",
                  key(c)).strip(" -,.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("csv")
    ap.add_argument("--out", help="output CSV (default data/needs_attention_<date>.csv)")
    args = ap.parse_args()

    sync = load_sync()
    sheet, dup_names = sync.read_sheet(args.csv)
    with open(args.csv, newline="", encoding="utf-8-sig") as f:
        raw = list(csv.reader(f))
    header = raw[0]
    i_partner = find_col(header, "partner organization name")
    i_club = find_col(header, "club name")
    i_roster = find_col(header, "please list the full name")
    i_count = find_col(header, "number of girls")
    i_same = find_col(header, "exact same name")
    i_same_detail = find_col(header, "identical full names")

    items = []

    def add(priority, issue, partner, club, detail, todo, row=""):
        items.append({"priority": priority, "issue": issue, "partner": partner,
                      "club": club, "detail": detail, "what_to_do": todo,
                      "sheet_row": row, "resolved": ""})

    # every submission that read_sheet would consider, in sheet order
    submissions = defaultdict(list)
    for n, row in enumerate(raw[1:], start=2):
        if len(row) <= max(i_partner, i_club, i_roster):
            continue
        club = " ".join(row[i_club].split())
        partner = " ".join(row[i_partner].split())
        if not club:
            continue
        names, _ = sync.parse_roster(row[i_roster])
        if not names:
            continue   # read_sheet ignores these too
        submissions[(key(partner), key(club))].append({
            "row": n, "partner": partner, "club": club, "names": names, "raw": row})

    latest_row = {k: v[-1]["row"] for k, v in submissions.items()}
    # girls of every club of a partner (for "moved to a sibling club" checks)
    by_partner = defaultdict(list)
    for (partner, club), names in sheet.items():
        by_partner[key(partner)].append((partner, club, {name_key(n) for n in names}))

    # --- DUPLICATE_NAME
    for (partner, club), dups in dup_names.items():
        if dups:
            add(1, "DUPLICATE_NAME", partner, club,
                "Listed twice: " + "; ".join(dups),
                "If these are two different girls, add something that tells them "
                "apart in the sheet (e.g. a middle name or '(A)'/'(B)'). If it is "
                "one girl typed twice, delete the extra line.",
                latest_row.get((key(partner), key(club)), ""))

    # --- IDENTICAL_NAMES (the form's own question)
    if i_same is not None:
        for k, subs in submissions.items():
            last = subs[-1]["raw"]
            if len(last) > i_same and last[i_same].strip().lower().startswith("y"):
                detail = (last[i_same_detail].strip()
                          if i_same_detail is not None and len(last) > i_same_detail else "")
                flagged = bool(dup_names.get((subs[-1]["partner"], subs[-1]["club"])))
                add(2 if flagged else 1, "IDENTICAL_NAMES", subs[-1]["partner"], subs[-1]["club"],
                    "Partner answered YES to 'girls with the exact same name'. Their note: "
                    + (" ".join(detail.split()) or "(nothing written)"),
                    "Make sure each of those girls is listed with a distinguishing "
                    "detail so they get separate IDs." +
                    ("" if flagged else " (The roster itself has no repeated name, so "
                     "either it was already fixed or the note is out of date.)"),
                    subs[-1]["row"])

    # --- POSSIBLE_SAME_CLUB (within a partner: shared girls or near-identical name)
    reported_pairs = set()
    for pk, cs in by_partner.items():
        # which smaller same-stem clubs does each club contain? (for the split story)
        for a in range(len(cs)):
            for b in range(a + 1, len(cs)):
                pa, ca, ga = cs[a]
                pb, cb, gb = cs[b]
                inter = len(ga & gb)
                jac = inter / len(ga | gb) if (ga | gb) else 0
                same_stem = bool(club_stem(ca)) and club_stem(ca) == club_stem(cb)
                spelling = similar(ca, cb) >= 0.85
                if jac < 0.3 and not (same_stem and inter):
                    if same_stem:
                        add(3, "POSSIBLE_SAME_CLUB", pa, f"{ca}  /  {cb}",
                            f"Near-identical names, no girls in common ({len(ga)} and {len(gb)} girls).",
                            "Probably two real clubs (e.g. primaria / secundaria). Confirm "
                            "and, if so, nothing to do.",
                            f"{latest_row.get((pk, key(ca)), '')}, {latest_row.get((pk, key(cb)), '')}")
                    continue
                reported_pairs.add((pk, key(ca), key(cb)))
                reported_pairs.add((pk, key(cb), key(ca)))
                row_a = latest_row.get((pk, key(ca)), 0)
                row_b = latest_row.get((pk, key(cb)), 0)
                big, small = (ca, ga, row_a), (cb, gb, row_b)
                if len(gb) > len(ga):
                    big, small = small, big
                covers = len(big[1] & small[1]) >= 0.9 * len(small[1])
                newer, older = (big, small) if big[2] > small[2] else (small, big)
                rows = f"{row_a}, {row_b}"
                if spelling and covers:
                    detail = (f"'{newer[0]}' (row {newer[2]}, {len(newer[1])} girls) and "
                              f"'{older[0]}' (row {older[2]}, {len(older[1])}) are the same club "
                              f"under two spellings: {inter} girls in common.")
                    todo = (f"Keep the newer entry '{newer[0]}' and retire '{older[0]}' (the "
                            "sync treats different spellings as different clubs). If the "
                            "older spelling is the correct one, fix the spelling in the "
                            "newer row instead.")
                elif covers and same_stem:
                    # look for the other split sibling
                    sibs = [c2 for (_, c2, g2) in cs
                            if c2 not in (big[0], small[0]) and club_stem(c2) == club_stem(big[0])
                            and len(big[1] & g2) >= 0.9 * len(g2)]
                    detail = (f"'{big[0]}' (row {big[2]}, {len(big[1])} girls) contains "
                              f"{len(big[1] & small[1])} of the {len(small[1])} girls of "
                              f"'{small[0]}' (row {small[2]})" +
                              (f" and also those of '{sibs[0]}'" if sibs else "") +
                              ". Looks like the combined club from before it was split.")
                    todo = (f"If the club was split, retire '{big[0]}' and keep the split "
                            "clubs, so nobody is counted twice.")
                else:
                    detail = (f"'{ca}' (row {row_a}, {len(ga)} girls) and '{cb}' (row {row_b}, "
                              f"{len(gb)}) share {inter} girls" +
                              (" and have near-identical names" if same_stem or spelling else "") + ".")
                    todo = ("Decide whether these are one club under two names (keep one, "
                            "retire the other) or two real clubs that share girls (then say "
                            "which girls belong where).")
                add(1, "POSSIBLE_SAME_CLUB", pa, f"{ca}  /  {cb}", detail, todo, rows)

    # --- RESUBMITTED
    for k, subs in submissions.items():
        if len(subs) < 2:
            continue
        pk = k[0]
        final_names = subs[-1]["names"]
        final = {name_key(n) for n in final_names}
        earlier = {}
        for s in subs[:-1]:
            for n in s["names"]:
                earlier.setdefault(name_key(n), n)
        gone = [n for nk, n in earlier.items() if nk not in final]
        if not gone:
            continue
        brand_new = [n for n in final_names if name_key(n) not in earlier]
        moved, respelled, missing = [], [], []
        for g in gone:
            other = [c for (p, c, girls) in by_partner[pk]
                     if key(c) != k[1] and name_key(g) in girls]
            if other:
                moved.append(f"{g} (now under '{other[0]}')")
                continue
            best = max(((similar(g, n), n) for n in brand_new), default=(0, None))
            if best[0] >= SIMILAR:
                respelled.append(f"{g} -> {best[1]}")
                brand_new.remove(best[1])
            else:
                missing.append(g)
        parts = []
        if missing:
            parts.append(f"{len(missing)} not in the newest list at all: " + "; ".join(missing))
        if respelled:
            parts.append(f"{len(respelled)} look respelled: " + "; ".join(respelled))
        if moved:
            parts.append(f"{len(moved)} moved to another club: " + "; ".join(moved))
        detail = (f"Submitted {len(subs)} times (rows {subs[0]['row']}–{subs[-1]['row']}); only "
                  f"the newest ({len(final_names)} girls) counts. Of the {len(gone)} earlier "
                  f"names absent from it: " + " | ".join(parts) +
                  (f". The newest list also adds {len(brand_new)} completely new name(s)."
                   if brand_new else "."))
        todo = ("Ask the partner whether the girls not in the newest list have left "
                "(fine) or were dropped by mistake (re-add them)."
                if missing else "") + \
               (" For respellings, confirm which spelling is right; the newest one "
                "becomes the ID." if respelled else "")
        add(1 if missing else 2, "RESUBMITTED", subs[-1]["partner"], subs[-1]["club"],
            detail, todo.strip(), subs[-1]["row"])

    # --- GIRL_IN_TWO_CLUBS (skip pairs already reported as possible same club)
    for pk, cs in by_partner.items():
        where = defaultdict(list)
        for partner, club, girls in cs:
            for g in girls:
                where[g].append(club)
        groups = defaultdict(list)
        for g, clubs_of in where.items():
            if len(clubs_of) > 1:
                groups[tuple(sorted(clubs_of, key=key))].append(g)
        for clubs_of, girls in groups.items():
            pairs = [(clubs_of[i], clubs_of[j]) for i in range(len(clubs_of))
                     for j in range(i + 1, len(clubs_of))]
            if all((pk, key(a), key(b)) in reported_pairs for a, b in pairs):
                continue
            partner = cs[0][0]
            add(2, "GIRL_IN_TWO_CLUBS", partner, "  /  ".join(clubs_of),
                f"{len(girls)} name(s) appear in {'both' if len(clubs_of) == 2 else 'all ' + str(len(clubs_of))}: "
                + "; ".join(sorted(girls)),
                "A girl should be on one roster. Confirm which club she attends "
                "(or whether these are different girls with the same name).")

    # --- CLUB_NAMED_AFTER_GIRL
    for (partner, club), names in sheet.items():
        if name_key(club) in {name_key(n) for n in names}:
            add(2, "CLUB_NAMED_AFTER_GIRL", partner, club,
                "The club name is also one of the girls' names on its roster.",
                "Check whether the club name was typed into the wrong box; if the "
                "club really is called that, nothing to do.",
                latest_row.get((key(partner), key(club)), ""))

    # --- ODD_LINE
    for (partner, club), names in sheet.items():
        long_lines = [n for n in names if len(n.split()) >= 6]
        singles = [n for n in names if len(n.split()) == 1]
        row = latest_row.get((key(partner), key(club)), "")
        if long_lines:
            add(2, "ODD_LINE", partner, club,
                "Very long line(s): " + "; ".join(long_lines),
                "Check whether two girls were typed on one line, or the line "
                "includes notes that should be removed.", row)
        if singles:
            add(3, "ODD_LINE", partner, club,
                "Single-word name(s): " + "; ".join(singles),
                "Ask the partner for the full name; a surname is needed for a "
                "stable ID and for matching in Salesforce.", row)

    # --- COUNT_MISMATCH and TINY_CLUB
    for k, subs in submissions.items():
        last = subs[-1]
        names = last["names"]
        declared = None
        if i_count is not None and len(last["raw"]) > i_count:
            digits = re.sub(r"\D", "", last["raw"][i_count])
            declared = int(digits) if digits else None
        if declared and abs(declared - len(names)) >= 3:
            add(2, "COUNT_MISMATCH", last["partner"], last["club"],
                f"Partner said {declared} girls; {len(names)} names are listed.",
                "Ask the partner which is right - names may be missing from the "
                "list (or the count is out of date).", last["row"])
        if len(names) < 5:
            add(2, "TINY_CLUB", last["partner"], last["club"],
                f"Only {len(names)} name(s) listed.",
                "Confirm this is a real club and get the full roster.", last["row"])

    # --- RENAMED_ON_FORM, ON_FORM_NOT_SHEET, REGION_UNSURE (need backups/)
    have_backups = all(os.path.exists(os.path.join(REPO, "backups", fid, "questions-latest.json"))
                       for fid in regions.REGIONAL_FORMS)
    if have_backups:
        rosters = regions.load_regional_rosters()
        sheet_keys = {key(c) for _, c in sheet}
        sheet_rosters = [(p, c, {name_key(n) for n in names}) for (p, c), names in sheet.items()]
        for region, text, opts in rosters:
            if key(text) in sheet_keys:
                continue
            best = max(((len(opts & g) / len(opts | g) if opts | g else 0, len(opts & g), p, c)
                        for p, c, g in sheet_rosters), default=(0, 0, "", ""))
            if best[0] >= regions.OVERLAP_THRESHOLD and best[1] >= regions.MIN_SHARED:
                add(2, "RENAMED_ON_FORM", best[2], best[3],
                    f"On the {region} attendance form this club is called '{text}' "
                    f"({len(opts)} girls, {best[1]} in common with the sheet's '{best[3]}'). "
                    "The sync matches clubs by name, so as things stand it would add a "
                    "second question for the sheet name and leave the old one.",
                    f"Decide on one name: either rename the club in the sheet to '{text}', "
                    f"or plan to rename/retire the form's '{text}' question when the "
                    "form is next synced.",
                    latest_row.get((key(best[2]), key(best[3])), ""))
            else:
                add(2, "ON_FORM_NOT_SHEET", "", text,
                    f"'{text}' is on the {region} attendance form ({len(opts)} girls) but no "
                    "club by that name - or with those girls - is in the enrollment sheet.",
                    "Find out whether this club still runs. If yes, it needs an enrollment "
                    "submission; if no, it will simply not be carried onto the new forms.")
        clubs = regions.classify_clubs(sheet, rosters)
        for p in regions.roll_up_to_partners(clubs):
            if p["confidence"] == "high":
                continue
            ev = p["evidence"]
            matched = ev.get("roster", 0) + ev.get("name", 0)
            add(2, "REGION_UNSURE", p["partner"], "",
                (f"Region set to '{p['region']}' but only {matched} of {p['clubs']} clubs "
                 f"could be matched to a regional attendance form; the other "
                 f"{p['clubs'] - matched} are not on any form yet."
                 if p["region"] else
                 f"No region could be derived: {p['note']}."),
                "Confirm the partner's region; correct it in the Partners tab if wrong, "
                "then run GLOW → Refresh regions.")
    else:
        print("  (no regional-form snapshots in backups/ - skipping RENAMED_ON_FORM, "
              "ON_FORM_NOT_SHEET and REGION_UNSURE)", file=sys.stderr)

    # --- write
    items.sort(key=lambda x: (x["priority"], x["issue"], key(x["partner"]), key(x["club"])))
    out = args.out or os.path.join(REPO, "data", f"needs_attention_{date.today().isoformat()}.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(items)

    counts = Counter((x["priority"], x["issue"]) for x in items)
    print(f"{len(items)} item(s) -> {os.path.relpath(out, REPO)}\n")
    for (prio, issue), n in sorted(counts.items()):
        print(f"  P{prio}  {issue:<22} {n}")
    partners_hit = len({key(x['partner']) for x in items if x['partner']})
    print(f"\n{partners_hit} partner(s) involved; P1 = blocks a clean roster, "
          "P2 = worth asking, P3 = probably fine")


if __name__ == "__main__":
    main()
