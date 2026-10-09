#!/usr/bin/env python3
"""
Build a regional attendance form the safe way: clone the upgraded working
copy, retitle it, then sync it from the Roster with that region's clubs only
(pruning the others). The live regional form is never touched; swapping links
over is a separate, human decision.

Steps (each printed, each verifiable in the Jotform builder):
  1. POST /form/<working copy>/clone   (the API sometimes answers 504 while
     the clone still gets created - we compare the account's form list
     before and after, and delete accidental extras)
  2. retitle the clone (form title + browser-tab title) and restore the
     list of offered languages, which the API clone resets to English only
     (tools/restore_translations.py)
  3. sync_attendance_form.py <roster.csv> --roster --region <R> --prune --form <clone> --apply
  4. tools/form_status.py --form <clone>

Usage:
    export JOTFORM_API_KEY=...
    python3 tools/clone_regional.py "Africa" data/roster_2026-08-27.csv            # dry run: clone + retitle + sync preview
    python3 tools/clone_regional.py "Africa" data/roster_2026-08-27.csv --apply
    python3 tools/clone_regional.py "Africa" data/roster_2026-08-27.csv --apply --existing <CLONE_ID>   # re-sync a clone made earlier
"""
import argparse
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow.cli import api_key, run                                # noqa: E402
from glow.forms import TEMPLATE as WORKING_COPY, TITLES  # noqa: E402
from glow.jotform import Client                          # noqa: E402


def live_form_ids(client):
    forms = client.get("/user/forms", limit=200)
    return {f["id"]: f for f in forms if f.get("status") != "DELETED"}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("region", choices=sorted(TITLES))
    ap.add_argument("roster_csv", help="export of the Roster tab")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--existing", help="re-sync this clone instead of making one")
    ap.add_argument("--source", default=WORKING_COPY, help="form to clone (default: working copy)")
    args = ap.parse_args()
    key = api_key()
    client = Client(key, apply=args.apply)
    title = TITLES[args.region]

    if args.existing:
        clone_id = args.existing
        print(f"Re-syncing existing clone {clone_id}")
    elif not args.apply:
        print(f"DRY RUN: would clone {args.source} -> \"{title}\", then sync {args.region} "
              "with --prune. Previewing the sync against the SOURCE form instead:\n")
        clone_id = args.source
    else:
        before = live_form_ids(client)
        print(f"1. cloning {args.source} ...")
        content = client.call(["-X", "POST", client.url(f"/form/{args.source}/clone")],
                              "clone", allow_fail=True)
        after = live_form_ids(client)
        new_ids = [i for i in after if i not in before]
        if content and content.get("id") and content["id"] not in new_ids:
            new_ids.append(content["id"])
        if not new_ids:
            sys.exit("Clone did not appear in the form list - check the Jotform account and retry.")
        clone_id = new_ids[0]
        for extra in new_ids[1:]:
            print(f"   deleting accidental extra clone {extra}")
            client.delete(f"/form/{extra}", "delete extra")
        print(f"   clone is {clone_id}")

        print(f"2. retitling to \"{title}\" (form title and browser-tab title)")
        client.post_form(f"/form/{clone_id}/properties", {
            "properties[title]": title,
            "properties[pagetitle]": title,
            "properties[pageTitleChanged]": "Yes",
        }, "retitle")
        info = client.get(f"/form/{clone_id}")
        print(f"   title now: \"{info.get('title')}\"  url: {info.get('url')}")

        # the API clone resets the offered-languages list to English only
        print("2b. restoring the language list (the clone drops it)")
        subprocess.run([sys.executable, os.path.join(REPO, "tools", "restore_translations.py"),
                        "--form", clone_id, "--source", args.source, "--apply"],
                       env={**os.environ, "JOTFORM_API_KEY": key})

    print(f"\n3. syncing {args.region} clubs" + (" (dry run)" if not args.apply else ""))
    cmd = [sys.executable, os.path.join(REPO, "sync_attendance_form.py"), args.roster_csv,
           "--roster", "--region", args.region, "--prune", "--form", clone_id]
    if args.apply and clone_id != args.source:
        cmd.append("--apply")
    r = subprocess.run(cmd, env={**os.environ, "JOTFORM_API_KEY": key})
    if r.returncode:
        sys.exit(f"sync failed ({r.returncode}) - the clone {clone_id} is left as is")

    if args.apply and clone_id != args.source:
        print("\n4. status")
        subprocess.run([sys.executable, os.path.join(REPO, "tools", "form_status.py"),
                        "--form", clone_id, "--roster", args.roster_csv],
                       env={**os.environ, "JOTFORM_API_KEY": key})
        info = client.get(f"/form/{clone_id}")
        print(f"\nDONE: {title}  id {clone_id}\n  fill in: {info.get('url')}\n"
              f"  builder: https://www.jotform.com/build/{clone_id}")


if __name__ == "__main__":
    run(main)
