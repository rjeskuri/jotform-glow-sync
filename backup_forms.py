#!/usr/bin/env python3
"""
Snapshot every GLOW attendance form's questions, properties (conditions,
emails, Salesforce integration) into backups/<formId>/.

Snapshots are the rollback path: `conditions` can be restored with a single
PUT (see restore_conditions.py). Run this before ANY change to a live form.

Usage:
    export JOTFORM_API_KEY=...
    python3 backup_forms.py                 # snapshot every known form
    python3 backup_forms.py --form <ID>     # just one
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

API_BASE = "https://api.jotform.com"
REPO = os.path.dirname(os.path.abspath(__file__))

FORMS = {
    "262352490535154": "template (every sync-logic change lands here first)",
    "262382821971058": "Africa (live from 2026-08-27)",
    "262383129464057": "Asia (live from 2026-08-27)",
    "262383455778067": "Latin America (live from 2026-08-27)",
    "262382706852058": "U.S (live from 2026-08-27)",
    "260555608160556": "master (defunct)",
    "260703905772560": "Africa (defunct)",
    "260704198384564": "Asia (defunct)",
    "260704170003542": "Latin America (defunct)",
    "260703912140547": "U.S (defunct)",
}


def get(url, label):
    out = subprocess.run(["curl", "-sS", url], capture_output=True, text=True)
    try:
        resp = json.loads(out.stdout)
    except json.JSONDecodeError:
        sys.exit(f"{label}: non-JSON response: {out.stdout[:200]}")
    if resp.get("responseCode") != 200:
        sys.exit(f"{label}: {resp.get('responseCode')} {resp.get('message')}")
    return resp["content"]


def snapshot(form_id, api_key, stamp):
    outdir = os.path.join(REPO, "backups", form_id)
    os.makedirs(outdir, exist_ok=True)
    summary = {}
    for part in ("questions", "properties"):
        content = get(f"{API_BASE}/form/{form_id}/{part}?apiKey={api_key}",
                      f"{form_id}/{part}")
        for name in (f"{part}-{stamp}.json", f"{part}-latest.json"):
            with open(os.path.join(outdir, name), "w") as f:
                json.dump(content, f, indent=1)
        summary[part] = content

    props = summary["properties"]
    integ = props.get("integrations") or {}
    sf = integ.get("salesforceV2") if isinstance(integ, dict) else None
    return {
        "questions": len(summary["questions"]),
        "conditions": len(props.get("conditions", [])),
        "emails": len(props.get("emails", [])),
        "salesforce": "yes" if sf else "NO",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--form", help="snapshot a single form ID")
    args = ap.parse_args()

    api_key = os.environ.get("JOTFORM_API_KEY") or sys.exit(
        "Set JOTFORM_API_KEY in the environment")
    stamp = datetime.now().strftime("%Y-%m-%dT%H%M")
    targets = {args.form: "single"} if args.form else FORMS

    print(f"Snapshot {stamp} -> backups/\n")
    for form_id, label in targets.items():
        s = snapshot(form_id, api_key, stamp)
        print(f"  {form_id}  {s['questions']:>4} questions  "
              f"{s['conditions']:>4} conditions  {s['emails']} emails  "
              f"salesforce={s['salesforce']}   {label}")
    print("\nRestore conditions with: python3 restore_conditions.py --form <ID>")


if __name__ == "__main__":
    main()
