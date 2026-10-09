#!/usr/bin/env python3
"""
docs/plans/README.md, generated from the frontmatter of every plan (docs/plans/) and intent
(docs/intent/): one table of plans (date, title, status, BACKLOG items, file), one of intents
(date, title, status, the plans that name it).

  --write   write it (make docs-index)
  --check   fail when the committed file is not a fresh generation, when a status is not one of
            proposed | accepted | in-progress | blocked | done | superseded (a comment may follow
            a #), when `done:` is not a date, or when `backlog:` names an item docs/BACKLOG.md
            does not have (make check)
"""
import argparse
import glob
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(REPO, "docs", "plans", "README.md")
STATUSES = ("proposed", "accepted", "in-progress", "blocked", "done", "superseded")
NAME = re.compile(r"(\d{4}-\d\d-\d\d)-[a-z0-9-]+\.md$")


def frontmatter(text):
    """The `key: value` lines between the opening and closing `---`, and the first # heading."""
    keys = {}
    if text.startswith("---\n") and "\n---\n" in text[4:]:
        head = text[4:text.index("\n---\n", 4)]
        for line in head.split("\n"):
            if ":" in line and not line.startswith((" ", "\t")):
                k, v = line.split(":", 1)
                keys[k.strip()] = v.strip()
    h1 = re.search(r"^# (.+)$", text, re.M)
    return keys, (h1.group(1).strip() if h1 else "")


def status_of(value):
    """(word, problem): the status word, or the reason it is not one of STATUSES."""
    word, _, comment = value.partition("#")
    word = word.strip()
    if word not in STATUSES:
        return word, f"status '{value[:60]}' is not one of {' | '.join(STATUSES)} (a comment goes after a #)"
    return word, None


def entries(folder):
    out, problems = [], []
    for path in sorted(glob.glob(os.path.join(REPO, "docs", folder, "*.md"))):
        name = os.path.basename(path)
        if name == "README.md":
            continue
        m = NAME.match(name)
        rel = f"docs/{folder}/{name}"
        if not m:
            problems.append(f"{rel}: not named YYYY-MM-DD-slug.md")
            continue
        with open(path, encoding="utf-8") as f:
            keys, h1 = frontmatter(f.read())
        if "status" not in keys:
            problems.append(f"{rel}: no status in its frontmatter")
            continue
        word, problem = status_of(keys["status"])
        if problem:
            problems.append(f"{rel}: {problem}")
        done = keys.get("done", "").partition("#")[0].strip()          # a template's comment is no date
        if done and not re.fullmatch(r"\d{4}-\d\d-\d\d", done):
            problems.append(f"{rel}: done '{done}' is not YYYY-MM-DD")
        title = keys.get("title") or re.sub(r"^(Plan|Intent|Spec):\s*", "", h1) or name
        out.append({"name": name, "date": m.group(1), "title": title, "status": word, "done": done,
                    "backlog": [b.strip() for b in keys.get("backlog", "").partition("#")[0].split(",")
                                if b.strip()],
                    "intent": keys.get("intent", "")})
    return out, problems


def cell(s):
    return s.replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")


def render(plans, intents):
    def status(e):
        return f"{e['status']} {e['done']}".strip()

    lines = [
        "# Plans and intents",
        "",
        "Generated from each file's frontmatter by `make docs-index` (`scripts/docs_index.py`);",
        "`make check` fails when this file is stale, so it is never edited by hand. A plan is required",
        "for anything beyond a one-line fix and is committed before the code; an intent is optional, to",
        "capture Ryan's ask before a plan exists ([templates](../templates/)). A status is one of",
        "`" + "`, `".join(STATUSES) + "`,",
        "with an optional comment after a `#`; a done one carries `done: YYYY-MM-DD`, and `backlog:`",
        "names the BACKLOG items a plan is about. Newest first.",
        "",
        "## Plans",
        "",
        "| Date | Plan | Status | BACKLOG | File |",
        "|---|---|---|---|---|",
    ]
    for e in sorted(plans, key=lambda e: (e["date"], e["name"]), reverse=True):
        lines.append(f"| {e['date']} | {cell(e['title'])} | {status(e)} | {', '.join(e['backlog'])} | "
                     f"[{e['name']}]({e['name']}) |")
    lines += ["", "## Intents", "", "| Date | Intent | Status | Plans | File |", "|---|---|---|---|---|"]
    for e in sorted(intents, key=lambda e: (e["date"], e["name"]), reverse=True):
        named = sorted(p["name"] for p in plans if e["name"] in p["intent"])
        links = ", ".join(f"[{p[:-3]}]({p})" for p in named)
        lines.append(f"| {e['date']} | {cell(e['title'])} | {status(e)} | {links} | "
                     f"[{e['name']}](../intent/{e['name']}) |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write docs/plans/README.md")
    mode.add_argument("--check", action="store_true", help="fail when it is stale or a frontmatter is wrong")
    args = ap.parse_args()

    plans, p1 = entries("plans")
    intents, p2 = entries("intent")
    problems = p1 + p2
    with open(os.path.join(REPO, "docs", "BACKLOG.md"), encoding="utf-8") as f:
        items = set(re.findall(r"^### (\d+[a-z]?)\. ", f.read(), re.M))
    for e in plans:
        for b in e["backlog"]:
            if b not in items:
                problems.append(f"docs/plans/{e['name']}: backlog {b} is not an item of docs/BACKLOG.md")
    text = render(plans, intents)
    if args.write:
        with open(INDEX, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        try:
            with open(INDEX, encoding="utf-8") as f:
                current = f.read()
        except FileNotFoundError:
            current = ""
        if current != text:
            problems.append("docs/plans/README.md is stale - run `make docs-index` and commit it")
    for p in problems:
        print("  FAIL " + p)
    if problems:
        print(f"docs-index: {len(problems)} FAILURE(S)")
        sys.exit(1)
    print(f"docs-index: {'written' if args.write else 'ok'} ({len(plans)} plans, {len(intents)} intents)")


if __name__ == "__main__":
    main()
