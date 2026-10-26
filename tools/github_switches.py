#!/usr/bin/env python3
"""
Back up the automatic sync's switches on GitHub before one is changed (ticket #146). Read-only.

`backup` saves, through the GitHub CLI, the repository's Actions variables with their values
(`gh variable list --json name,value,updatedAt`: SF_SYNC, AUTO_SYNC_APPLY), its secrets by name
and date only (`gh secret list --json name,updatedAt`: a secret's value cannot be read), and every
workflow with its state, a disabled one too (`gh workflow list --all --json id,name,state`), into
backups/github/switches-<stamp>.json, and records it as `github all` in .claude/live_backups.log:
the backup from today the live gate (.claude/hooks/live_gate.sh) wants before it lets `gh variable
set`, `gh secret set`, `gh workflow enable|disable` or `gh api` on actions/ through without a
prompt. A gh call that fails stops it before anything is saved or recorded.

Rollback with the saved file: a variable's old value (`gh variable set NAME --body <value>`), a
workflow's old state (`gh workflow enable|disable <name>`); a secret only from its source (the
file shows when it last changed).

Usage:
    python3 tools/github_switches.py backup
"""
import argparse
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow import backup, live_backups   # noqa: E402

# what is saved, and the gh list command that reads it (no other gh call is ever made)
LISTS = (("variables", ["variable", "list", "--json", "name,value,updatedAt"]),
         ("secrets", ["secret", "list", "--json", "name,updatedAt"]),
         ("workflows", ["workflow", "list", "--all", "--json", "id,name,state"]))
SECRET_FIELDS = ("name", "updatedAt")


def gh_list(args):
    """The JSON list `gh <args>` prints, run from the checkout (gh reads the repository from it);
    exits with what to fix when gh fails or prints no list."""
    shown = "gh " + " ".join(args)
    try:
        done = subprocess.run(["gh", *args], cwd=REPO, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as err:
        sys.exit(f"{shown}: {err} - is the GitHub CLI installed and logged in (gh auth status)? "
                 "Nothing saved or recorded.")
    if done.returncode != 0:
        sys.exit(f"{shown} failed (exit {done.returncode}): {done.stderr.strip()[:300]}\n"
                 "Nothing saved or recorded.")
    try:
        rows = json.loads(done.stdout)
    except ValueError:
        rows = None
    if not isinstance(rows, list):
        sys.exit(f"{shown}: the answer is no JSON list. Nothing saved or recorded.")
    return rows


def save_switches():
    """Read the three lists, save them, record `github all`; returns the saved file's path."""
    saved = {key: gh_list(args) for key, args in LISTS}
    # names and dates only, whatever gh hands back
    saved["secrets"] = [{k: s[k] for k in SECRET_FIELDS if k in s} for s in saved["secrets"] if isinstance(s, dict)]
    stamp = backup.stamp()
    folder = os.path.join(REPO, "backups", "github")
    os.makedirs(folder, exist_ok=True)
    out = os.path.join(folder, f"switches-{stamp}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"saved": stamp, **saved}, f, indent=1)
    live_backups.record("github", "all", out, repo=REPO)
    return out, saved


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("backup", help="save the variables, the secrets' names and dates and the workflows' states")
    ap.parse_args()
    out, saved = save_switches()
    print(f"Saved {os.path.relpath(out, REPO)}:")
    print(f"  variables: {', '.join(v.get('name', '?') for v in saved['variables']) or 'none'}")
    print(f"  secrets (names and dates only): {', '.join(s.get('name', '?') for s in saved['secrets']) or 'none'}")
    print(f"  workflows: {', '.join(str(w.get('name', '?')) + ' ' + str(w.get('state', '?')) for w in saved['workflows']) or 'none'}")
    print("Recorded for the live gate (.claude/live_backups.log): github all")


if __name__ == "__main__":
    main()
