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
import subprocess
import sys

API_BASE = "https://api.jotform.com"
REPO = os.path.dirname(os.path.abspath(__file__))


def call(args, label):
    out = subprocess.run(["curl", "-sS"] + args, capture_output=True, text=True)
    try:
        resp = json.loads(out.stdout)
    except json.JSONDecodeError:
        sys.exit(f"{label}: non-JSON response: {out.stdout[:200]}")
    if resp.get("responseCode") != 200:
        sys.exit(f"{label}: {resp.get('responseCode')} {resp.get('message')}")
    return resp["content"]


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

    path = os.path.join(REPO, "backups", args.form,
                        args.src or "properties-latest.json")
    if not os.path.exists(path):
        sys.exit(f"No snapshot at {path} - run backup_forms.py first")
    saved = json.load(open(path))
    conditions = saved["conditions"] if isinstance(saved, dict) else saved
    if not conditions:
        sys.exit(f"{path} holds no conditions - refusing to wipe the form")

    live = call([f"{API_BASE}/form/{args.form}/properties?apiKey={api_key}"],
                "GET properties")
    print(f"form {args.form}: live has {len(live.get('conditions', []))} "
          f"conditions; snapshot has {len(conditions)}")
    print(f"snapshot: {os.path.relpath(path, REPO)}")

    if not args.apply:
        print("\nDRY RUN - re-run with --apply to restore")
        return

    payload = json.dumps({"properties": {"conditions": conditions}})
    call(["-X", "PUT", f"{API_BASE}/form/{args.form}/properties?apiKey={api_key}",
          "-H", "Content-Type: application/json", "--data-binary", payload],
         "PUT conditions")

    after = call([f"{API_BASE}/form/{args.form}/properties?apiKey={api_key}"],
                 "GET properties (verify)")
    n = len(after.get("conditions", []))
    ok = n == len(conditions)
    print(f"RESTORED: {n} conditions on the server "
          f"({'matches snapshot' if ok else 'MISMATCH - investigate'})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
