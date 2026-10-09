#!/usr/bin/env python3
"""
Snapshot every GLOW attendance form's questions, properties (conditions,
emails, Salesforce integration) into backups/<formId>/.

Snapshots are the rollback path: `conditions` can be restored with a single
PUT (see restore_conditions.py). Run this before ANY change to a live form.
The snapshot itself, its file names and its stamp are glow/backup.py's; the
tools that write a form take theirs through it.

Usage:
    export JOTFORM_API_KEY=...
    python3 backup_forms.py                 # snapshot every known form
    python3 backup_forms.py --form <ID>     # just one
"""
import argparse
import os
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
from glow import backup                 # noqa: E402
from glow.backup import snapshot        # noqa: E402  (also the name tools imported from here)
from glow.cli import api_key, run            # noqa: E402
from glow.forms import LABELS as FORMS  # noqa: E402
from glow.jotform import Client     # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--form", help="snapshot a single form ID")
    args = ap.parse_args()

    client = Client(api_key())
    stamp = backup.stamp()
    targets = {args.form: "single"} if args.form else FORMS

    print(f"Snapshot {stamp} -> backups/\n")
    for form_id, label in targets.items():
        s = snapshot(form_id, client, stamp)
        print(f"  {form_id}  {s['questions']:>4} questions  "
              f"{s['conditions']:>4} conditions  {s['emails']} emails  "
              f"salesforce={s['salesforce']}   {label}")
    print("\nRestore conditions with: python3 restore_conditions.py --form <ID>")


if __name__ == "__main__":
    run(main)
