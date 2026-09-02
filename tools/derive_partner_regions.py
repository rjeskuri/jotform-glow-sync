#!/usr/bin/env python3
"""
Work out which region each partner belongs to, without anyone typing it in.

Nobody recorded regions anywhere — but the four regional attendance forms
already encode them: a club that sits on the Africa form is an African club.
This tool reads the regional form snapshots in backups/, matches each
enrollment-sheet club to a regional form, and rolls that up to the partner.

Two matching signals per club, strongest first:
  1. roster overlap  - the club's girl names vs. each regional checkbox's
                       options (Jaccard >= 0.3 and 5+ girls in common).
                       Survives club renames and re-typed rosters.
  2. club-name match - normalized club text against the form's checkbox texts,
                       used only when the name is on exactly one regional form.
Partners are assigned by majority vote of their clubs' matches; any partner
whose clubs point at two different regions is reported as a CONFLICT and left
blank rather than guessed. Clubs on no regional form yet (enrolled after the
forms were last built) simply inherit their partner's region.

Output: appsscript/Regions.gs (the PARTNER_REGIONS map the Sheet scripts use
to prefill the Partners tab) plus a report on stdout. Never prints girls'
names.

Usage:
    python3 tools/derive_partner_regions.py enrollment.csv            # report only
    python3 tools/derive_partner_regions.py enrollment.csv --write    # also regenerate Regions.gs
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow import forms as glow_forms          # noqa: E402
from glow.sync import read_sheet              # noqa: E402
from glow.text import key, name_key           # noqa: E402

# The PRE-LAUNCH regional forms, on purpose: the live regionals were built
# FROM the Partners tab's regions, so deriving from them would be circular.
# These snapshots are the last independent evidence of where each club sat.
REGIONAL_FORMS = {fid: region for region, fid in glow_forms.DEFUNCT.items()
                  if region != "master"}
# A roster "matches" a regional checkbox when the girl sets overlap this much
# (Jaccard) AND share at least MIN_SHARED girls. 0.3 is deliberately below the
# ~0.5 overlap seen when a partner re-types a roster with respellings and a
# few new girls; MIN_SHARED stops tiny clubs matching on a couple of common
# names. Verified 2026-08-24: no sheet club clears 0.3 on two different
# regional forms, so lowering it cannot produce a cross-region vote.
OVERLAP_THRESHOLD = 0.3
MIN_SHARED = 5
OUT_GS = os.path.join(REPO, "appsscript", "Regions.gs")


def load_regional_rosters():
    """[(region, club text, frozenset of girl-name keys)] from the snapshots."""
    rosters = []
    for form_id, region in REGIONAL_FORMS.items():
        path = os.path.join(REPO, "backups", form_id, "questions-latest.json")
        if not os.path.exists(path):
            sys.exit(f"Missing {os.path.relpath(path, REPO)} - run backup_forms.py first")
        questions = json.load(open(path))
        for q in questions.values():
            if q.get("type") != "control_checkbox":
                continue
            text = " ".join(q["text"].split())
            options = frozenset(name_key(o) for o in (q.get("options") or "").split("|")
                                if o.strip())
            rosters.append((region, text, options))
    return rosters


def classify_clubs(sheet, rosters):
    """For each (partner, club) in the sheet, find its region evidence."""
    regions_by_name = defaultdict(set)
    for region, text, _ in rosters:
        regions_by_name[key(text)].add(region)

    results = []
    for (partner, club), girls in sheet.items():
        girl_keys = frozenset(name_key(g) for g in girls)
        best = (0.0, None, None, 0)
        for region, text, options in rosters:
            if not options or not girl_keys:
                continue
            shared = len(girl_keys & options)
            jaccard = shared / len(girl_keys | options)
            if jaccard > best[0]:
                best = (jaccard, region, text, shared)
        matched = best[0] >= OVERLAP_THRESHOLD and best[3] >= MIN_SHARED
        results.append({
            "partner": partner, "club": club, "girls": len(girls),
            "overlap": round(best[0], 2), "shared": best[3],
            "overlap_region": best[1] if matched else None,
            "overlap_form_club": best[2] if matched else None,
            "name_regions": sorted(regions_by_name.get(key(club), ())),
        })
    return results


def roll_up_to_partners(clubs):
    by_partner = defaultdict(list)
    for c in clubs:
        by_partner[c["partner"]].append(c)

    partners = []
    for partner in sorted(by_partner, key=key):
        votes, evidence = Counter(), Counter()
        for c in by_partner[partner]:
            if c["overlap_region"]:
                votes[c["overlap_region"]] += 2
                evidence["roster"] += 1
            elif len(c["name_regions"]) == 1:
                # name-only: the form club could belong to another partner
                # with the same club name, so this is a weak vote
                votes[c["name_regions"][0]] += 1
                evidence["name"] += 1
            elif c["name_regions"]:
                evidence["ambiguous-name"] += 1
            else:
                evidence["unmatched"] += 1
        ranked = votes.most_common()
        n_clubs = len(by_partner[partner])
        matched = evidence["roster"] + evidence["name"]
        if not ranked:
            region, confidence = "", "none"
        elif len(ranked) > 1:
            region, confidence = "", "conflict"
        elif evidence["roster"] >= 2 or (evidence["roster"] >= 1 and matched == n_clubs):
            region, confidence = ranked[0][0], "high"
        else:
            # a single club's rosters (or names alone) carrying the partner
            region, confidence = ranked[0][0], "thin"

        if confidence == "high":
            note = (f"derived from the regional attendance forms "
                    f"({matched}/{n_clubs} clubs on the {region} form)")
        elif confidence == "thin":
            note = (f"PLEASE CONFIRM - only {matched} of {n_clubs} clubs could be "
                    f"matched to a regional form ({region}); the rest are new")
        elif confidence == "conflict":
            note = ("PLEASE CONFIRM - clubs found on more than one regional form: " +
                    ", ".join(f"{r} x{v}" for r, v in ranked))
        else:
            note = "region needed - none of this partner's clubs are on a regional form yet"
        partners.append({
            "partner": partner, "clubs": n_clubs,
            "region": region, "confidence": confidence, "note": note,
            "votes": dict(ranked), "evidence": dict(evidence),
        })
    return partners


def write_regions_gs(partners, csv_name):
    def js_str(s):
        return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"

    lines = [
        "/**",
        " * Partner -> region, derived from which regional attendance form each",
        " * partner's clubs live on. GENERATED by tools/derive_partner_regions.py",
        f" * on {date.today().isoformat()} from {csv_name} - regenerate rather than hand-edit.",
        " *",
        " * The Partners tab in the spreadsheet always wins: this map only prefills",
        " * a region when the tab has none, so staff can correct any entry there",
        " * and the correction sticks. PARTNER_REGION_NOTES is what goes in the",
        " * tab's notes column, so a thin or conflicting derivation is visible",
        " * where staff will actually look.",
        " */",
        "",
        "const PARTNER_REGIONS = {",
    ]
    width = max(len(js_str(p["partner"])) for p in partners) + 1
    for p in partners:
        lhs = js_str(p["partner"]) + ":"
        flag = "" if p["confidence"] == "high" else f"  // {p['confidence'].upper()}"
        lines.append(f"  {lhs:<{width}} {js_str(p['region'])},{flag}")
    lines += ["};", "", "const PARTNER_REGION_NOTES = {"]
    for p in partners:
        lhs = js_str(p["partner"]) + ":"
        lines.append(f"  {lhs:<{width}} {js_str(p['note'])},")
    lines += ["};", ""]
    with open(OUT_GS, "w") as f:
        f.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("csv", help="enrollment responses export")
    ap.add_argument("--write", action="store_true",
                    help="regenerate appsscript/Regions.gs")
    args = ap.parse_args()

    sheet, _ = read_sheet(args.csv)
    rosters = load_regional_rosters()
    clubs = classify_clubs(sheet, rosters)
    partners = roll_up_to_partners(clubs)

    print(f"{len(clubs)} sheet clubs vs {len(rosters)} regional-form rosters "
          f"-> {len(partners)} partners\n")
    width = max(len(p["partner"]) for p in partners)
    for p in partners:
        flag = "" if p["confidence"] == "high" else f"  <-- {p['confidence']}"
        print(f"  {p['partner']:<{width}}  {p['clubs']:>2} clubs  "
              f"{p['region'] or '(none)':<14} {p['evidence']}{flag}")

    unmatched = [c for c in clubs if not c["overlap_region"] and not c["name_regions"]]
    if unmatched:
        print(f"\n{len(unmatched)} club(s) are on no regional form yet (new since "
              "the forms were last built) - they inherit their partner's region:")
        for c in unmatched:
            print(f"  {c['partner']} | {c['club']}")

    renamed = [c for c in clubs if c["overlap_region"]
               and key(c["overlap_form_club"]) != key(c["club"])]
    if renamed:
        print(f"\n{len(renamed)} club(s) matched a regional roster under a different "
              "name (the sync matches by name, so these would get a SECOND "
              "question unless the sheet or the form is renamed first):")
        for c in renamed:
            print(f"  {c['partner']} | sheet '{c['club']}' == form "
                  f"'{c['overlap_form_club']}' ({c['overlap_region']}, {c['overlap']})")

    by_conf = Counter(p["confidence"] for p in partners)
    print(f"\nConfidence: {dict(by_conf)}")

    if args.write:
        write_regions_gs(partners, os.path.basename(args.csv))
        print(f"Wrote {os.path.relpath(OUT_GS, REPO)}")
    else:
        print("Re-run with --write to regenerate appsscript/Regions.gs")

    bad = by_conf.get("conflict", 0) + by_conf.get("none", 0)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
