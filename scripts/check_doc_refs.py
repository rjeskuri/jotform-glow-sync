#!/usr/bin/env python3
"""
Keep the references into the docs alive, offline:

- every RUNBOOK section a tracked file quotes - `docs/RUNBOOK.md, "<Section>"`,
  `RUNBOOK "<Section>"`, `RUNBOOK.md ("<Section>")`, `` `docs/RUNBOOK.md` — "<Section>" ``,
  also inside a string literal continued over lines - is a heading of docs/RUNBOOK.md
  (exactly, or without its trailing parenthetical: "One club per submission" names
  "One club per submission (the club guard)"), or an issue of its ReviewQueue table
  (the Apps Script points staff at one by name);
- every markdown link with an #anchor into a tracked .md file names a heading there
  (GitHub's slugs), the runbook's table of contents included;
- every BACKLOG item a file cites by number (`BACKLOG 50`, `backlog item 1`,
  `BACKLOG 41/43/46`) exists, and a title it quotes (`BACKLOG "Gold versus retention"`)
  is in an item's heading.

docs/archive/ is history and is not read. Tools and tests that print or assert a section
name are what this protects: renaming a heading breaks them silently otherwise.
"""
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNBOOK, BACKLOG = "docs/RUNBOOK.md", "docs/BACKLOG.md"
TEXT_SUFFIXES = (".md", ".py", ".js", ".gs", ".json", ".yml", ".yaml", ".sh", ".txt", ".toml")
CODE_SUFFIXES = (".py", ".js", ".gs", ".sh", ".yml", ".yaml", ".toml")
# the checkers and this one's test spell the patterns out on purpose
SKIP_PREFIXES = ("node_modules/", "data/", "backups/", "docs/archive/", "scripts/check_", "test/doc_refs_test.py")

Q = "\"\u201c\u201d"                           # straight and curly double quotes
QUOTED = rf"[{Q}]([^{Q}]{{2,100}})[{Q}]"
MORE = rf"((?:\s*(?:/|\band\b|\bor\b)\s*[{Q}][^{Q}]{{2,100}}[{Q}])*)"
LEAD = r"`?(?:'s)?[\s,(" + "\u2014\u2013" + r"-]+(?:(?:new|a|an|the|its|section|sections)\s+)?"   # , ( — – -
SECTION_REF = re.compile(r"RUNBOOK(?:\.md)?" + LEAD + QUOTED + MORE)
BACKLOG_TITLE_REF = re.compile(r"\bBACKLOG(?:\.md)?" + LEAD + QUOTED)
BACKLOG_NUM_REF = re.compile(r"(?i)\bbacklog(?:\.md)?`?[ \t(-]+(?:items?[ \t]+)?(\d+[a-z]?)\b"
                             r"((?:\s*(?:/|\band\b)\s*\d+[a-z]?\b)*)")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]*#[^)\s]+)\)")


def tracked():
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, text=True,
                         cwd=REPO, check=True).stdout
    return [p for p in out.split("\0") if p and not p.startswith(SKIP_PREFIXES)
            and (p.endswith(TEXT_SUFFIXES) or os.path.basename(p) in ("Makefile", "CLAUDE.md"))
            and os.path.isfile(os.path.join(REPO, p))]


def read(rel):
    with open(os.path.join(REPO, rel), encoding="utf-8") as f:
        return f.read()


def headings(text):
    """(level, text) of every ATX heading outside a fenced code block."""
    out, fence = [], None
    for line in text.splitlines():
        m = re.match(r"\s*(```+|~~~+)", line)
        if m:
            if fence is None:
                fence = m.group(1)[:3]
            elif line.strip().startswith(fence):
                fence = None
            continue
        if fence is None:
            h = re.match(r"(#{1,6})\s+(.+?)\s*#*\s*$", line)
            if h:
                out.append((len(h.group(1)), h.group(2)))
    return out


def norm(s):
    return " ".join(s.split())


def section_names(text):
    names = set()
    for _, h in headings(text):
        names.add(norm(h))
        names.add(norm(re.sub(r"\s*\([^()]*\)$", "", h)))     # without a trailing (qualifier)
    # the ReviewQueue's issues: one bold first cell per row of the table in that section
    review = text.split("\n## Working the ReviewQueue", 1)[-1].split("\n## ", 1)[0]
    names.update(norm(m) for m in re.findall(r"^\| \*\*(.+?)\*\* \|", review, re.M))
    return names


def slugs(text):
    """GitHub's anchors: lower case, punctuation dropped, spaces to '-', repeats numbered."""
    seen, out = {}, set()
    for _, h in headings(text):
        h = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", h)       # a link in a heading: its text
        s = re.sub(r"[^\w\- ]", "", h.strip().lower()).replace(" ", "-")
        n = seen.get(s, 0)
        out.add(s if n == 0 else f"{s}-{n}")
        seen[s] = n + 1
    return out


def flatten(text, code):
    """One line per file: string literals continued over lines joined, comment leaders and
    escaped quotes dropped, whitespace collapsed - so a name split across lines reads whole."""
    if code:
        text = re.sub(r"([\"'])\s*\+?\s*\n\s*[fFrRbBuU]{0,2}\1", "", text)   # "a "\n"b" / 'a ' +\n'b'
        text = re.sub(r"\n[ \t]*(?:\*|#+|//+)[ \t]?", "\n", text)            # comment leaders
        text = text.replace('\\"', '"')
    return norm(text)


def backlog_items(text):
    """item number -> the text a quoted title must be found in (its heading, or its row)."""
    items = {}
    for line in text.splitlines():
        m = re.match(r"### (\d+[a-z]?)\. (.+)", line) or re.match(r"\| (?:~~)?(\d+[a-z]?)(?:~~)? \|(.*)", line)
        if m:
            items[m.group(1)] = norm(m.group(2))
    return items


def main():
    files = tracked()
    runbook = read(RUNBOOK)
    names = section_names(runbook)
    items = backlog_items(read(BACKLOG))
    anchors = {}
    failures, counts = [], {"sections": 0, "anchors": 0, "items": 0}
    for rel in files:
        text = read(rel)
        flat = flatten(text, rel.endswith(CODE_SUFFIXES))
        for m in SECTION_REF.finditer(flat):
            for name in [m.group(1)] + re.findall(QUOTED, m.group(2)):
                counts["sections"] += 1
                if norm(name) not in names:
                    failures.append(f'{rel}: RUNBOOK "{norm(name)}" is not a heading of {RUNBOOK}')
        for m in BACKLOG_NUM_REF.finditer(flat):
            for num in [m.group(1)] + re.findall(r"\d+[a-z]?", m.group(2)):
                counts["items"] += 1
                if num.lower() not in items:
                    failures.append(f"{rel}: BACKLOG {num} is not an item of {BACKLOG}")
        for m in BACKLOG_TITLE_REF.finditer(flat):
            counts["items"] += 1
            if not any(norm(m.group(1)) in t for t in items.values()):
                failures.append(f'{rel}: BACKLOG "{norm(m.group(1))}" is in no item\'s heading')
        if rel.endswith(".md"):
            for m in LINK.finditer(text):
                path, anchor = m.group(1).split("#", 1)
                if re.match(r"[a-z]+:", path):
                    continue
                target = os.path.normpath(os.path.join(os.path.dirname(rel), path)) if path else rel
                if not target.endswith(".md") or not os.path.isfile(os.path.join(REPO, target)):
                    continue                    # a missing file is check_docs_links.py's to report
                if target not in anchors:
                    anchors[target] = slugs(read(target))
                counts["anchors"] += 1
                if anchor not in anchors[target]:
                    failures.append(f"{rel}: link #{anchor} is not a heading of {target}")
    for f in failures:
        print("  FAIL " + f)
    if failures:
        print(f"doc-refs: {len(failures)} FAILURE(S) - rename the reference, not the heading "
              "(tools and tests quote headings)")
        sys.exit(1)
    print(f"doc-refs: ok ({counts['sections']} RUNBOOK section references, {counts['anchors']} "
          f"anchors, {counts['items']} BACKLOG references resolve)")


if __name__ == "__main__":
    main()
