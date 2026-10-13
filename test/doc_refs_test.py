#!/usr/bin/env python3
"""
scripts/check_doc_refs.py: the reference shapes it reads (in prose and in string literals
continued over lines), what counts as a RUNBOOK section, GitHub's anchors, BACKLOG items.
scripts/docs_index.py: the frontmatter it reads, the status vocabulary, the index's cells.
"""
import os
import sys
import unittest

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
    WIDENED = ("beyond a one-line fix", "straight to a plan", "every change", "any size", "whether or not")
    WIDENED_RE = (r"(each|every|any|all) tickets?", r"however small", r"rollout or not", r"regardless",
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
        # the intent template: optional, and it no longer sends a small change to a plan
        intent = " ".join(read("intent.md").split()).lower()
        self.assertIn("ticket", intent)
        self.assertIn("optional", intent)
        self.assert_not_widened(intent, "docs/templates/intent.md")


if __name__ == "__main__":
    unittest.main(verbosity=1)
