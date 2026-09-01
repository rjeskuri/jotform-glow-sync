#!/usr/bin/env python3
"""
Python smoke check, offline: every tracked .py file parses, every command-line
script answers --help without a traceback (and without needing an API key),
and tools/sheets_client.py prints its usage when called with no arguments.
"""
import ast
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".venv", "venv", "node_modules", "data", "backups", "__pycache__"}


def tracked_py():
    out = []
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for f in files:
            if f.endswith(".py"):
                out.append(os.path.relpath(os.path.join(root, f), REPO))
    return sorted(out)


def is_cli(path):
    with open(os.path.join(REPO, path), encoding="utf-8") as f:
        src = f.read()
    return 'if __name__ == "__main__"' in src or "if __name__ == '__main__'" in src


def main():
    env = {k: v for k, v in os.environ.items() if k != "JOTFORM_API_KEY"}
    files = tracked_py()
    failures = []
    for rel in files:
        with open(os.path.join(REPO, rel), encoding="utf-8") as f:
            try:
                ast.parse(f.read(), filename=rel)
            except SyntaxError as err:
                failures.append(f"{rel}: {err}")
    # the operator-facing tools only: scripts/ and test/ are exercised by their own make targets
    # (and scripts/check_py.py smoking itself would recurse forever)
    scripts = [f for f in files if is_cli(f) and not f.startswith(("test/", "scripts/"))]
    smoked = 0
    for rel in scripts:
        argv = [sys.executable, os.path.join(REPO, rel)]
        if rel.endswith("sheets_client.py"):
            r = subprocess.run(argv, capture_output=True, text=True, env=env, cwd=REPO)
            ok = r.returncode != 0 and "Usage" in (r.stderr + r.stdout) and "Traceback" not in r.stderr
        else:
            r = subprocess.run(argv + ["--help"], capture_output=True, text=True, env=env, cwd=REPO)
            ok = r.returncode == 0 and "Traceback" not in r.stderr and "usage" in r.stdout.lower()
        if ok:
            smoked += 1
        else:
            failures.append(f"{rel}: --help smoke failed (exit {r.returncode}): "
                            f"{(r.stderr or r.stdout).strip()[:200]}")
    for line in failures:
        print("  FAIL " + line)
    if failures:
        print(f"py: {len(failures)} FAILURE(S)")
        sys.exit(1)
    print(f"py: {len(files)} files parse, {smoked} scripts answer --help")


if __name__ == "__main__":
    main()
