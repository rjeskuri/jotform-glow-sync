#!/usr/bin/env python3
"""
Generate the synthetic enrollment CSV the offline tests run on.

Every name here is fictional (invented surnames, first names chosen at
random from a fixed list, a fixed seed), so the fixture can live in git and
run in CI while the real enrollment export never leaves data/. The layout is
the real export's: eleven columns, the same header fragments the parsers
look for, and every edge case the tests exercise - accents, shared surnames,
duplicated names, invisible characters, list numbering, a case-only
re-submission, a club name with a comma and quotes, one club name under two
partners, a short row and an empty club, and a wrong "number of girls".

    python3 test/fixtures/make_fixture.py --write    # regenerate both files
    python3 test/fixtures/make_fixture.py --check    # committed == generated?

expected.json is written with the Python parser itself (read_sheet), so the
JS tests compare against what the Python tool sees, and `--check` catches a
parser change on the Python side.

Both parsers agree on everything below on purpose. Two known differences are
deliberately NOT exercised (docs/ARCHITECTURE.md, "Known divergences"): rows
with an empty partner, bullets other than "-", and invisible characters in
the partner/club cells.
"""
import argparse
import contextlib
import csv
import io
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
import sync_attendance_form as sync  # noqa: E402

CSV_PATH = os.path.join(HERE, "enrollment_sample.csv")
EXPECTED_PATH = os.path.join(HERE, "expected.json")
SEED = 20260901

HEADER = [
    "Timestamp", "Email Address", "Partner Organization Name", "Club Name",
    "Number of Girls Enrolled in This Club?",
    "For this club, please list the full name (First, Middle and Last Name/Surname) "
    "of all enrolled girls. Enter one full name per line.",
    "Are there any girls in this club with the exact same name (First, middle and "
    "last name/surname)?",
    "Please specify the identical full names and any known identifier (e.g., "
    "additional middle name). Enter one full name per line.",
    "Does the mentor who will submit attendance for this specific club speak English?",
    "If no, what is the primary language of the mentors?",
    "Column 10",
]

PARTNERS = ["Fixture Partner Alpha", "Fixture Partner Beta",
            "Fixture Partner Gamma", "Fixture Partner Delta"]
FIRST = ["Amara", "Beatrice", "Chiara", "Dalia", "Esther", "Fatima", "Grace", "Hana",
         "Ines", "Joy", "Kavya", "Leila", "Maya", "Nadia", "Olivia", "Priya", "Rosa",
         "Sofia", "Thandi", "Uma", "Valeria", "Wanjiru", "Ximena", "Yara", "Zainab",
         "Aisha", "Bianca", "Camila", "Diana", "Elena", "Farah", "Gloria", "Hope",
         "Isabel", "Julia", "Keza", "Luna", "Mercy", "Nia", "Olga"]
# invented; long enough that no real surname is likely to collide
LAST = ["Fennwhistle", "Marrowgate", "Ostrivane", "Pellucidor", "Thornquibble",
        "Umberlash", "Wrenfoldy", "Yexleyton", "Grimboltz", "Halverquist", "Ixworthing",
        "Jubbleton", "Kestrelby", "Lorrimane", "Nimbleford", "Quillstrand", "Vexmoorish",
        "Zaffrewick", "Brindlecote", "Cobblewynd"]
RANDOM_CLUB_WORDS = ["Bright", "Rising", "Golden", "Silver", "Morning", "Evening",
                     "Northern", "Southern", "River", "Mountain", "Ocean", "Valley"]
RANDOM_CLUB_NOUNS = ["Stars", "Lights", "Flames", "Voices", "Wings", "Roots"]


def row(partner, club, names, count=None, same="No", same_detail="", english="Yes",
        language="", stamp="8/20/2026 10:14:02", email="mentor1@example.org"):
    roster = "\n".join(names)
    n = len([x for x in names if x.strip()]) if count is None else count
    return [stamp, email, partner, club, str(n), roster, same, same_detail, english,
            language, ""]


def build_rows(rng):
    rows = []
    alpha, beta, gamma, delta = PARTNERS
    # 1. shared surname within one club + 6. case-only re-submission (last wins)
    trio = ["Grace Fennwhistle", "Mercy Fennwhistle", "Hope Fennwhistle"]
    rows.append(row(alpha, "Glow Club", trio + ["Amara Marrowgate", "Zainab Ostrivane"],
                    stamp="8/20/2026 10:14:02"))
    # 2. accents and diacritics (ids must fold to ASCII)
    rows.append(row(gamma, "Estrellas", ["Lucía Ñandúvex", "Josefa Peñascote",
                                          "Amélie Zörblequist", "Inés Álvarquibble",
                                          "Valeria Cobblewynd"],
                    english="No", language="Español"))
    # 3. duplicated names: exact, case-variant, exact (three clubs flagged)
    rows.append(row(beta, "Bright Stars", ["Amara Marrowgate", "Beatrice Pellucidor",
                                            "Amara Marrowgate", "Chiara Thornquibble"],
                    same="Yes", same_detail="Amara Marrowgate - two girls, one has a middle name"))
    rows.append(row(gamma, "Rising Suns", ["Zainab Ostrivane", "Dalia Umberlash",
                                            "zainab ostrivane", "Esther Wrenfoldy"]))
    rows.append(row(delta, "Dawn Circle", ["Nia Kestrelby", "Olga Lorrimane", "Nia Kestrelby"]))
    # 4. invisible characters inside roster lines (never in partner/club cells)
    rows.append(row(beta, "Hidden Chars", ["\u200bMaya Pellucidor", "Leila\u200e Thornquibble",
                                            "\ufeffYara Umberlash", "Uma Wrenfoldy\u2060"]))
    # 5. numbering, "-" bullets, trailing punctuation, blank lines, stray whitespace
    rows.append(row(alpha, "Numbered List", ["1. Dalia Yexleyton", "12) Esther Grimboltz",
                                              "- Farah Halverquist", "3 Gloria Ixworthing",
                                              "Hana Jubbleton,", "Ines Lorrimane.", "",
                                              "  Joy   Nimbleford  ", "\tKavya Quillstrand\t"],
                    count=8))
    # 7. a club name with a comma and quotes
    rows.append(row(delta, 'Sunrise Club, Eastside "B"', ["Priya Vexmoorish", "Rosa Zaffrewick",
                                                           "Sofia Brindlecote"]))
    # 8. the same club name under two partners
    rows.append(row(alpha, "Stars", ["Thandi Cobblewynd", "Wanjiru Fennwhistle"]))
    rows.append(row(beta, "Stars", ["Ximena Marrowgate", "Yara Ostrivane", "Aisha Pellucidor"]))
    # 10. "number of girls" deliberately off by four (needs_attention material)
    rows.append(row(gamma, "Miscounted", ["Bianca Thornquibble", "Camila Umberlash",
                                           "Diana Wrenfoldy"], count=7))
    # random filler clubs, deterministic under the seed
    used = set()
    for i in range(12):
        partner = PARTNERS[i % 4]
        while True:
            club = f"{rng.choice(RANDOM_CLUB_WORDS)} {rng.choice(RANDOM_CLUB_NOUNS)}"
            if (partner, club) not in used:
                used.add((partner, club))
                break
        n = rng.randint(6, 14)
        names = []
        while len(names) < n:
            name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if name not in names:
                names.append(name)
        rows.append(row(partner, club, names, stamp=f"8/{21 + i % 7}/2026 09:{10 + i:02d}:00",
                        email=f"mentor{2 + i}@example.org"))
    # 9. a short row (too few columns) and a row with an empty club: both skipped
    rows.append(["8/28/2026 08:00:00", "mentor99@example.org", delta, "Short Row"])
    rows.append(row(delta, "", ["Elena Grimboltz", "Farah Halverquist"]))
    # 6. the case-only re-submission of the first club: later row, last wins
    rows.append(row(alpha, "GLOW Club", trio + ["Amara Marrowgate", "Zainab Ostrivane",
                                                 "Gloria Ixworthing"],
                    stamp="8/29/2026 17:45:10"))
    return rows


def render_csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(HEADER)
    w.writerows(rows)
    return buf.getvalue()


def render_expected(csv_text):
    tmp = os.path.join(HERE, ".enrollment_sample.tmp.csv")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(csv_text)
    try:
        with contextlib.redirect_stdout(sys.stderr):    # read_sheet warns about the short row
            sheet, dups = sync.read_sheet(tmp)
    finally:
        os.remove(tmp)
    accented = sum(1 for names in sheet.values() for n in names
                   if any("À" <= ch <= "ÿ" for ch in n))
    expected = {
        "clubs": len(sheet),
        "girls": sum(len(v) for v in sheet.values()),
        "partners": len({p for p, _ in sheet}),
        "duplicate_name_clubs": sum(1 for d in dups.values() if d),
        "accented_names": accented,
        "py_clubs": sorted(f"{p.lower()}||{c.lower()}" for p, c in sheet),
    }
    return json.dumps(expected, indent=1, ensure_ascii=False) + "\n"


def generate():
    csv_text = render_csv(build_rows(random.Random(SEED)))
    return csv_text, render_expected(csv_text)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    args = ap.parse_args()
    csv_text, expected = generate()
    if args.write:
        with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
            f.write(csv_text)
        with open(EXPECTED_PATH, "w", encoding="utf-8") as f:
            f.write(expected)
        e = json.loads(expected)
        print(f"fixtures: wrote {e['clubs']} clubs, {e['girls']} girls, "
              f"{e['partners']} partners, {e['duplicate_name_clubs']} duplicate-name clubs")
        return
    stale = []
    for path, text in ((CSV_PATH, csv_text), (EXPECTED_PATH, expected)):
        try:
            with open(path, encoding="utf-8", newline="") as f:
                if f.read() != text:
                    stale.append(path)
        except FileNotFoundError:
            stale.append(path)
    if stale:
        for p in stale:
            print("  FAIL " + os.path.relpath(p, REPO) + " differs from a fresh generation")
        print("fixtures: STALE - run `make fixtures` (and review the diff)")
        sys.exit(1)
    print("fixtures: up to date")


if __name__ == "__main__":
    main()
