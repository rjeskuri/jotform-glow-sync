#!/usr/bin/env python3
"""
scripts/check_doc_refs.py: the reference shapes it reads (in prose and in string literals
continued over lines), what counts as a RUNBOOK section, GitHub's anchors, BACKLOG items,
the rules docs/BACKLOG.md states for itself.
scripts/docs_index.py: the frontmatter it reads, the status vocabulary, the index's cells.
"""
import contextlib
import io
import os
import sys
import unittest
from unittest import mock

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import REPO

sys.path.insert(0, os.path.join(REPO, "scripts"))
import check_doc_refs as refs
import docs_index


def names(text, code=False):
    out = []
    for m in refs.SECTION_REF.finditer(refs.flatten(text, code)):
        out += [m.group(1)] + refs.re.findall(refs.QUOTED, m.group(2))
    return out


class DocRefs(unittest.TestCase):

    def test_the_shapes_in_prose(self):
        for text in ('see docs/RUNBOOK.md, "Club names two partners share".',
                     'RUNBOOK "Club names two\n  partners share"',
                     'the RUNBOOK.md ("Club names two partners share")',
                     '`docs/RUNBOOK.md` — "Club names two partners share"',
                     "the RUNBOOK's \"Club names two partners share\""):
            self.assertEqual(names(text), ["Club names two partners share"], text)
        self.assertEqual(names('docs/RUNBOOK.md, "Renaming a club" / "Moving a club"'),
                         ["Renaming a club", "Moving a club"])
        self.assertEqual(names('RUNBOOK "Automatic sync" and "Photos", "not this"'), ["Automatic sync", "Photos"])
        # a path in code, a menu item after a colon: not a reference
        for text in ('read(os.path.join(REPO, "docs", "RUNBOOK.md")) x = "y"',
                     'recorded in RUNBOOK:\n "Rebuild roster from enrollment responses"'):
            self.assertEqual(names(text, code=True), [], text)

    def test_string_literals_continued_over_lines_read_whole(self):
        py = 'sys.exit("refused (docs/RUNBOOK.md, \\"Club names "\n             "two partners share\\")")'
        js = "'move it first (docs/RUNBOOK.md, \"Moving a club to another ' +\n    'partner\").'"
        gs = "/**\n * runs the sync (docs/RUNBOOK.md, \"Automatic\n * sync\").\n */"
        self.assertEqual(names(py, code=True), ["Club names two partners share"])
        self.assertEqual(names(js, code=True), ["Moving a club to another partner"])
        self.assertEqual(names(gs, code=True), ["Automatic sync"])

    def test_what_names_a_section(self):
        doc = ("# Runbook\n## One club per submission (the club guard)\n```bash\n# not a heading\n```\n"
               "### Rolling back `appsscript/`\n## Working the ReviewQueue\n| Issue | What |\n|---|---|\n"
               "| **Form response could not be processed** | x |\n## Next\n| **Not an issue** | y |\n")
        found = refs.section_names(doc)
        for name in ("One club per submission (the club guard)", "One club per submission",
                     "Rolling back `appsscript/`", "Form response could not be processed"):
            self.assertIn(name, found)
        self.assertNotIn("not a heading", found)
        self.assertNotIn("Not an issue", found)

    def test_anchors_are_githubs(self):
        doc = "## The one-time switch (`--same-name-switch`)\n## Rollback\n### Rollback\n## New clubs' accounts\n"
        self.assertEqual(refs.slugs(doc), {"the-one-time-switch---same-name-switch", "rollback", "rollback-1",
                                           "new-clubs-accounts"})

    def test_backlog_items_and_citations(self):
        table = "| 1a | **Rotate** | x |\n| ~~45~~ | ~~Partner list~~ |\n"
        sections = "### 50. Delete the dead partner-list code\n### 68. Gold versus retention\n"
        self.assertEqual(set(refs.backlog_items(table)), {"1a", "45"})
        self.assertEqual(refs.backlog_items(sections)["68"], "Gold versus retention")
        cited = []
        for m in refs.BACKLOG_NUM_REF.finditer(refs.flatten(
                "BACKLOG 41/43/46; backlog item 1; BACKLOG 64 and 67; BACKLOG-27; its backlog: 2 rosters", False)):
            cited += [m.group(1)] + refs.re.findall(r"\d+[a-z]?", m.group(2))
        self.assertEqual(cited, ["41", "43", "46", "1", "64", "67", "27"])
        self.assertEqual(refs.BACKLOG_TITLE_REF.search('BACKLOG "Gold versus retention"').group(1),
                         "Gold versus retention")


STATUSES = "open | in-progress | blocked-on-ryan | done YYYY-MM-DD | dropped"


def one_item(num, status, done=False):
    """A made-up backlog of one item `num` with `status`, under a theme or under ## Done."""
    item = f"### {num}. A made-up item\n\nStatus: {status}\n\n- 2026-10-01: a bullet\n"
    theme = "- nothing open\n" if done else item
    finished = item if done else ""
    return (f"# Backlog\n\nA made-up header.\n\n## A theme\n\n{theme}\n## Done\n\n{finished}\n"
            "## Explicitly not planned\n\n- nothing\n")


def backlog(open_items, done_items=()):
    """A made-up backlog: (heading, body) pairs above ## Done, then under it."""
    def section(items):
        return "".join(f"### {h}\n\n{body}\n" for h, body in items)
    return (f"# Backlog\n\nA made-up header.\n\n## A theme\n\n{section(open_items)}## Done\n\n"
            f"{section(done_items)}## Explicitly not planned\n\n- nothing\n")


def names_item(problem, num):
    return refs.re.search(rf"\bitem {refs.re.escape(num)}\b", problem) is not None


def run_main(backlog_text=None):
    """check_doc_refs.main() over the repository with docs/BACKLOG.md's text replaced by
    `backlog_text` (every other path reads the real file): (exit code, stdout)."""
    real_read = refs.read

    def fake_read(rel):
        if backlog_text is not None and os.path.normpath(rel) == os.path.normpath(refs.BACKLOG):
            return backlog_text
        return real_read(rel)

    out, code = io.StringIO(), 0
    with mock.patch.object(refs, "read", fake_read), contextlib.redirect_stdout(out):
        try:
            refs.main()
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return code, out.getvalue()


def items_counted(output):
    """The ok line's count of the BACKLOG items checked: `... <n> BACKLOG items ...`."""
    m = refs.re.search(r"doc-refs: ok\b.*?\b(\d+) BACKLOG items\b", output)
    return int(m.group(1)) if m else None


class BacklogRules(unittest.TestCase):
    """backlog_problems(text) -> list[str]: the rules docs/BACKLOG.md states for itself, one
    problem per broken rule, each naming the item (`item <id>: ...`) or the bad heading."""

    def assert_one_problem(self, text, name, label, heading=False):
        problems = refs.backlog_problems(text)
        self.assertEqual(len(problems), 1, f"{label}: {problems}")
        named = name in problems[0] if heading else names_item(problems[0], name)
        self.assertTrue(named, f"{label}: {problems[0]!r} does not name {name}")

    def test_the_committed_backlog_keeps_its_rules(self):
        text = refs.read(refs.BACKLOG)
        self.assertEqual(refs.backlog_problems(text), [])
        # the items to check: every `### <id>. <title>` heading, found independently here
        ids = refs.re.findall(r"(?m)^### (\d+[a-z]?)\. ", text)
        self.assertEqual(set(ids), set(refs.backlog_items(text)))
        self.assertEqual(len(ids), len(set(ids)))
        # doc-refs passes on the committed backlog, and its ok line counts the items it checked
        code, output = run_main()
        self.assertEqual(code, 0, output)
        self.assertNotIn("FAIL", output)
        self.assertEqual(items_counted(output), len(refs.backlog_items(text)), output)
        # the count follows the backlog: two more valid made-up items, two more counted
        more = text.replace("\n## Done\n", "\n### 998. A made-up open item\n\nStatus: open\n\n"
                            "## Done\n\n### 999. A made-up finished item\n\nStatus: done 2026-10-14\n\n", 1)
        self.assertNotEqual(more, text)
        self.assertEqual(refs.backlog_problems(more), [])
        code, output = run_main(more)
        self.assertEqual(code, 0, output)
        self.assertEqual(items_counted(output), len(ids) + 2, output)

    def test_each_status_is_from_the_vocabulary_with_a_real_date(self):
        passing = [("7", "open", False), ("31b", "in-progress", False), ("120", "blocked-on-ryan", False),
                   ("4", "dropped", True), ("88", "done 2026-10-14", True), ("9a", "done 2024-02-29", True),
                   ("15", "done 2025-12-31", True)]
        for num, status, done in passing:
            self.assertEqual(refs.backlog_problems(one_item(num, status, done)), [], status)
        # an invalid status is a vocabulary problem only: the done-like ones sit under ## Done,
        # the others above it, so placement adds no second problem
        failing = [("42", "finished", False), ("6", "Open", False), ("13c", "done", True),
                   ("57", "done 2026-02-30", True), ("101", "done 14-10-2026", True),
                   ("3", "blocked", False), ("70", "done 2026-02-29", True), ("8", "done 2026-13-01", True),
                   ("26", "in progress", False), ("64", "Dropped", False),
                   # a valid status with trailing text is not a valid status
                   ("19", "done 2026-10-15 (PR #12)", True), ("38", "open - waiting on a reply", False)]
        for num, status, done in failing:
            self.assert_one_problem(one_item(num, status, done), num, status)
        problem = refs.backlog_problems(one_item("42", "finished"))[0]
        self.assertIn("'finished'", problem)
        self.assertIn(STATUSES, problem)

    def test_an_item_needs_exactly_one_status_line_first(self):
        ok = ("5. A made-up item", "Status: open\n\n- 2026-10-01: a bullet\n")
        cases = [("12", "12. No status line", "- 2026-10-01: a bullet\n- 2026-10-02: another\n"),
                 ("27a", "27a. Two status lines", "Status: open\n\n- 2026-10-01: a bullet\n\nStatus: in-progress\n"),
                 ("33", "33. Status after a bullet", "- 2026-10-01: a bullet\n\nStatus: open\n"),
                 # the bold shape is not a status line: the item has none
                 ("48", "48. Bold status", "**Status:** open\n\n- 2026-10-01: a bullet\n")]
        for num, heading, body in cases:
            self.assert_one_problem(backlog([ok, (heading, body)]), num, heading)
            self.assert_one_problem(backlog([(heading, body), ok]), num, heading)
        # a status line belongs to the item it follows: the next item's does not count
        text = backlog([("12. No status line", "- 2026-10-01: a bullet\n"), ("13. Fine", "Status: open\n")])
        self.assert_one_problem(text, "12", "the next item's status")
        # a heading followed straight by its status line is fine
        self.assertEqual(refs.backlog_problems("## A theme\n### 5. Tight\nStatus: open\n- a bullet\n## Done\n"), [])

    def test_finished_items_sit_under_done_and_others_above(self):
        ok_open = ("5. Open", "Status: open\n")
        ok_done = ("6. Done", "Status: done 2026-09-30\n")
        cases = [("21", [ok_open, ("21. Done above", "Status: done 2026-10-01\n")], [ok_done]),
                 ("44b", [ok_open, ("44b. Dropped above", "Status: dropped\n")], [ok_done]),
                 ("50", [ok_open], [ok_done, ("50. Open below", "Status: open\n")]),
                 ("61", [ok_open], [("61. In progress below", "Status: in-progress\n"), ok_done]),
                 ("77", [ok_open], [ok_done, ("77. Blocked below", "Status: blocked-on-ryan\n")])]
        for num, above, below in cases:
            self.assert_one_problem(backlog(above, below), num, num)
        self.assertEqual(refs.backlog_problems(backlog([ok_open], [ok_done])), [])

    def test_a_number_used_twice_or_a_heading_without_one_is_named(self):
        for num in ("17", "2c", "93"):
            text = backlog([(f"{num}. First", "Status: open\n"), ("40. Other", "Status: open\n")],
                           [(f"{num}. Second", "Status: done 2026-10-02\n")])
            self.assert_one_problem(text, num, f"{num} twice")
        for heading in ("Notes", "9 Without the dot", "Ideas for later"):
            text = backlog([("40. Other", "Status: open\n"), (heading, "- 2026-10-01: a bullet\n")])
            self.assert_one_problem(text, heading, heading, heading=True)

    def test_doc_refs_fails_on_a_broken_backlog(self):
        real = refs.read(refs.BACKLOG)
        broken = {
            "997": real.replace("\n## Done\n", "\n### 997. A made-up item\n\nStatus: finished\n\n## Done\n", 1),
            "996": real.replace("\n## Done\n", "\n### 996. A made-up item\n\nStatus: open\n\n"
                                "### 996. Again\n\nStatus: open\n\n## Done\n", 1),
            "995": real.replace("\n## Done\n", "\n## Done\n\n### 995. A made-up item\n\nStatus: open\n\n", 1),
        }
        for num, text in broken.items():
            self.assertNotEqual(text, real)
            code, output = run_main(text)
            self.assertNotEqual(code, 0, output)
            fails = [line for line in output.splitlines() if "FAIL docs/BACKLOG.md:" in line]
            self.assertTrue(fails, output)
            self.assertTrue(any(names_item(line, num) for line in fails), output)
            self.assertNotIn("doc-refs: ok", output)


class DocsIndex(unittest.TestCase):

    def test_the_frontmatter_and_the_title(self):
        keys, h1 = docs_index.frontmatter("---\ntitle: A thing\nstatus: done   # shipped\ndone: 2026-10-01\n"
                                          "backlog: 41, 42\n---\n\n# Plan: A thing\n")
        self.assertEqual((keys["status"], keys["done"], keys["backlog"], h1),
                         ("done   # shipped", "2026-10-01", "41, 42", "Plan: A thing"))
        self.assertEqual(docs_index.frontmatter("# Plan: no frontmatter\n"), ({}, "Plan: no frontmatter"))

    def test_the_status_vocabulary(self):
        for value in ("proposed", "accepted", "in-progress", "blocked", "done", "superseded",
                      "done             # merged 2026-09-29; deployed (BACKLOG 41)"):
            self.assertIsNone(docs_index.status_of(value)[1], value)
        for value in ("blocked-on-ryan", "done (deployed 2026-10-02)", "draft", "accepted (Ryan) - in-progress", ""):
            self.assertIn("is not one of", docs_index.status_of(value)[1], value)

    def test_a_cell_never_breaks_the_table_or_turns_into_html(self):
        self.assertEqual(docs_index.cell("a | b <club> - <partner>"), "a \\| b &lt;club&gt; - &lt;partner&gt;")

    # DECISIONS 2026-10-14: new work is a ticket; a plan is kept beside a ticket whose change has a
    # live rollout, not beside every ticket. The conditional has to be said ("a ticket whose change
    # has / with a / that has a live rollout"), and the wordings that widen it to all work are out.
    CONDITION = r"(whose|with a|that has|that have|which has|when (its|the|a)|if (its|the|a))"
    # "one.line", not the literal: epic #5's done-check greps the repository for the old phrase
    WIDENED = ("straight to a plan", "every change", "any size", "whether or not")
    WIDENED_RE = (r"beyond a one.line fix", r"(each|every|any|all) tickets?", r"however small",
                  r"rollout or not", r"regardless",
                  r"small (change|fix|work|tweak)s?.{0,40}plan")

    def assert_not_widened(self, flat, where):
        for phrase in self.WIDENED:
            self.assertNotIn(phrase, flat, where)
        for pattern in self.WIDENED_RE:
            self.assertNotRegex(flat, pattern, where)

    def test_the_header_puts_a_plan_beside_a_live_rollouts_ticket(self):
        # The header wraps, so its words are compared with whitespace collapsed.
        text = docs_index.render([], [])
        header = " ".join(text.split("## Plans")[0].split())
        flat = header.lower()
        self.assertRegex(flat, r"new work.{0,40}ticket")
        # the plan goes with the ticket, and only a ticket whose change has a live rollout
        self.assertRegex(flat, r"plan.{0,60}ticket.{0,30}" + self.CONDITION + r".{0,40}live rollout")
        self.assertRegex(flat, r"intent.{0,40}optional|optional.{0,40}intent")
        for section in ("Rollout", "Rollback", "Result"):
            self.assertIn(section, header)
        self.assert_not_widened(flat, "docs/plans/README.md header")
        for status in docs_index.STATUSES:
            self.assertIn(f"`{status}`", header, status)

    def test_the_plan_and_intent_templates_agree_with_the_index(self):
        def read(name):
            with open(os.path.join(REPO, "docs", "templates", name), encoding="utf-8") as f:
                return f.read()

        plan = read("plan.md")
        body = refs.re.sub(r"<!--.*?-->", "", plan, flags=refs.re.S)   # a heading, not a mention in the comment
        lines = plan.split("\n")
        for heading in ("## Rollout", "## Rollback", "## Risks", "## Proof", "## Result"):
            self.assertRegex(body, r"(?m)^" + refs.re.escape(heading) + r"\b", heading)
            # and a line of guidance under it, not another heading straight after
            at = next(i for i, line in enumerate(lines) if refs.re.match(refs.re.escape(heading) + r"\b", line))
            after = [line.strip() for line in lines[at + 1:] if line.strip()]
            self.assertTrue(after and not after[0].startswith("#") and refs.re.search(r"\w{3}", after[0]),
                            f"{heading} has no guidance under it")
        keys, _ = docs_index.frontmatter(plan)
        self.assertEqual(set(keys), {"title", "author", "status", "done", "backlog", "created", "intent"})
        # the plan template says when a plan exists: beside the ticket whose change has a live rollout
        flat = " ".join(plan.split()).lower()
        self.assertIn("live rollout", flat, "docs/templates/plan.md")
        self.assertRegex(flat, r"(ticket|change)s?.{0,30}" + self.CONDITION + r".{0,40}live rollout",
                         "docs/templates/plan.md")
        self.assert_not_widened(flat, "docs/templates/plan.md")
        # the intent template: optional, and a plan only beside a ticket whose change has a live rollout
        intent = " ".join(read("intent.md").split()).lower()
        self.assertIn("ticket", intent)
        self.assertIn("optional", intent)
        self.assertRegex(intent, r"plan.{0,60}(ticket|change)s?.{0,30}" + self.CONDITION + r".{0,40}live rollout",
                         "docs/templates/intent.md")
        self.assert_not_widened(intent, "docs/templates/intent.md")


if __name__ == "__main__":
    unittest.main(verbosity=1)
