#!/usr/bin/env python3
"""
Print the club identities the Python tool reads from an enrollment CSV, as a
JSON list of "partner||club" keys (lowercased), so test/parity_test.js can
compare them with what the Apps Script code reads from the same file.

    python3 test/helpers/py_clubs.py <enrollment.csv>
"""
import contextlib
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
import sync_attendance_form as sync  # noqa: E402


def club_keys(csv_path):
    with contextlib.redirect_stdout(sys.stderr):   # read_sheet may print warnings
        sheet, _ = sync.read_sheet(csv_path)
    return sorted(f"{p.lower()}||{c.lower()}" for p, c in sheet)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(json.dumps(club_keys(sys.argv[1])))
