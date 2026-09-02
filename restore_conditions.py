#!/usr/bin/env python3
"""
Restore a form's conditional logic from a snapshot taken by backup_forms.py.

This is the rollback path when a sync or manual edit breaks a form's logic.
It only touches the `conditions` property; questions, emails, and the
Salesforce integration are left exactly as they are.

Usage:
    export JOTFORM_API_KEY=...
    python3 restore_conditions.py --form 262352490535154                    # dry run
    python3 restore_conditions.py --form 262352490535154 --apply
    python3 restore_conditions.py --form <ID> --from conditions-2026-08-24T1730.json
"""
import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
from glow.cli import run          # noqa: E402
from glow.jotform import Client   # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--form", required=True)
    ap.add_argument("--from", dest="src",
                    help="snapshot filename in backups/<form>/ "
                         "(default: properties-latest.json)")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    api_key = os.environ.get("JOTFORM_API_KEY") or sys.exit(
        "Set JOTFORM_API_KEY in the environment")
    client = Client(api_key, apply=args.apply)

    path = os.path.join(REPO, "backups", args.form,
                        args.src or "properties-latest.json")
    if not os.path.exists(path):
        sys.exit(f"No snapshot at {path} - run backup_forms.py first")
    saved = json.load(open(path))
    conditions = saved["conditions"] if isinstance(saved, dict) else saved
    if not conditions:
        sys.exit(f"{path} holds no conditions - refusing to wipe the form")

    live = client.get(f"/form/{args.form}/properties")
    print(f"form {args.form}: live has {len(live.get('conditions', []))} "
          f"conditions; snapshot has {len(conditions)}")
    print(f"snapshot: {os.path.relpath(path, REPO)}")

    if not args.apply:
        print("\nDRY RUN - re-run with --apply to restore")
        return

    client.put_json(f"/form/{args.form}/properties",
                    {"properties": {"conditions": conditions}}, "PUT conditions")

    after = client.get(f"/form/{args.form}/properties")
    n = len(after.get("conditions", []))
    ok = n == len(conditions)
    print(f"RESTORED: {n} conditions on the server "
          f"({'matches snapshot' if ok else 'MISMATCH - investigate'})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    run(main)
