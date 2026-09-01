#!/usr/bin/env python3
"""
Keep the docs portable: no absolute paths to this machine or to a session
scratchpad in any tracked text file, and every relative markdown link
resolves to a file that exists.
"""
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# home directories, session scratchpads, bare /tmp (assembled so this file does not match itself)
DEAD = re.compile("/" + "Users/|" + "/private" + "/tmp|(?<![\\w./-])" + "/tmp" + "/")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s#]+)(?:#[^)]*)?\)")
TEXT_SUFFIXES = (".md", ".py", ".js", ".gs", ".json", ".yml", ".yaml", ".sh", ".txt", ".toml")
SKIP_PREFIXES = ("node_modules/", "data/", "backups/")


def tracked():
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, text=True,
                         cwd=REPO, check=True).stdout
    return [p for p in out.split("\0") if p and not p.startswith(SKIP_PREFIXES)]


def main():
    failures, links = [], 0
    for rel in tracked():
        if not (rel.endswith(TEXT_SUFFIXES) or os.path.basename(rel) in ("Makefile", "CLAUDE.md")):
            continue
        if rel.startswith("scripts/check_"):      # the checkers define these patterns
            continue
        path = os.path.join(REPO, rel)
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if DEAD.search(line):
                failures.append(f"{rel}:{n}: absolute path: {line.strip()[:100]}")
        if rel.endswith(".md"):
            for m in LINK.finditer(text):
                target = m.group(1)
                if re.match(r"[a-z]+:", target):
                    continue
                links += 1
                if not os.path.exists(os.path.join(os.path.dirname(path), target)):
                    failures.append(f"{rel}: broken link -> {target}")
    for f in failures:
        print("  FAIL " + f)
    if failures:
        print(f"docs-links: {len(failures)} FAILURE(S)")
        sys.exit(1)
    print(f"docs-links: ok ({links} relative links resolve, 0 absolute paths)")


if __name__ == "__main__":
    main()
