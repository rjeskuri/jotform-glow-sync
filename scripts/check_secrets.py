#!/usr/bin/env python3
"""
Refuse secrets and personal data in the repository.

Scans every tracked text file (default), one file (--file PATH, used by the
PostToolUse hook), or stdin (--stdin, for a diff) for: API keys and tokens,
private-key material, Google Drive/Sheet/Script ids, girl IDs, e-mail
addresses, and session scratchpad paths. Matches are printed masked.
The rules and allowlists live here and nowhere else, so the hook, `make check`
and CI can never disagree.
"""
import argparse
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The allow entries are tested against the MATCHED TEXT itself, never against
# the surrounding line — a real address cannot hide next to an allowed one.
RULES = [
    ("32-hex token (Jotform key / md5)",
     re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{32}(?![0-9a-fA-F])"), []),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_-]{35}"), []),
    ("OAuth access token", re.compile(r"ya29\.[0-9A-Za-z_-]+"), []),
    ("private key material",
     re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----|\"private_key\"\s*:"), []),
    ("API key on a URL", re.compile(r"apiKey=[0-9A-Za-z]{8,}"), []),
    ("Drive / Sheet / Script id",
     re.compile(r"(?<![0-9A-Za-z_-])1[0-9A-Za-z_-]{40,60}(?![0-9A-Za-z_-])"),
     ["1FAIpQLS"]),                    # public viewform links are fine
    ("girl ID",                        # second segment must contain a letter (surname code)
     re.compile(r"(?<![A-Za-z0-9_-])[A-Z0-9]{2,8}-(?=[A-Z0-9]*[A-Z])[A-Z0-9]{2,12}-[0-9]{3}"
                r"(?![A-Za-z0-9_-])"),
     ["DEMOCLUB-SAMPLE-", "SUNRISEC-"]),   # documented / test-only ids
    ("e-mail address",
     re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
     ["@example.org", "@example.com", "@users.noreply.github.com", "noreply@anthropic.com"]),
    # (the literal is assembled so this file does not match its own rule)
    ("session scratchpad path", re.compile("/private" + "/tmp/" + "claude-"), []),
]
SKIP_FILES = {"package-lock.json"}
SKIP_PREFIXES = ("node_modules/", "data/", "backups/", "credentials/service-account")
BINARY_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".woff", ".woff2")


def mask(s):
    return s[:4] + "…" + s[-2:] if len(s) > 8 else "…"


def scan_text(text, label):
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        for name, rx, allow in RULES:
            for m in rx.finditer(line):
                if any(a in m.group(0) for a in allow):
                    continue
                hits.append(f"{label}:{n}: {name}: {mask(m.group(0))}")
    return hits


def scan_file(path, label):
    if os.path.basename(path) in SKIP_FILES or path.endswith(BINARY_SUFFIXES):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return scan_text(f.read(), label)
    except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
        return []


def tracked_files():
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, text=True,
                         cwd=REPO, check=True).stdout
    return [p for p in out.split("\0") if p and not p.startswith(SKIP_PREFIXES)]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--file", help="scan one file instead of every tracked file")
    ap.add_argument("--stdin", action="store_true", help="scan standard input (e.g. a diff)")
    args = ap.parse_args()

    if args.stdin:
        hits, scanned = scan_text(sys.stdin.read(), "stdin"), 1
    elif args.file:
        hits, scanned = scan_file(args.file, os.path.relpath(args.file, REPO)), 1
    else:
        files = tracked_files()
        hits = [h for rel in files for h in scan_file(os.path.join(REPO, rel), rel)]
        scanned = len(files)
    for h in hits:
        print("  FAIL " + h)
    if hits:
        print(f"secrets: {len(hits)} match(es) - remove them (see .claude/skills/child-privacy)")
        sys.exit(1)
    print(f"secrets: clean ({scanned} file{'s' if scanned != 1 else ''} scanned)")


if __name__ == "__main__":
    main()
