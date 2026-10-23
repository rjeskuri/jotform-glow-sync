#!/usr/bin/env python3
"""
Ticket #108 (Ryan, 2026-10-22): a mentor's corrected re-submission for a club and date that already
has a `Success` batch no longer fails whole as "Duplicate" - with the same module it adds only the
girls not yet on that date, as rows of the ORIGINAL batch (its `Girls_Present__c` moves to the new
total), and is itself `Success` with the message `merged into <original batch id>`; a different
module, or a correction that adds nobody, stays `Failed` "Duplicate". The docs must say so: the
RUNBOOK (what a correction does; the "Jotform template test" recipe, which relied on the refusal,
ticks only girls already on that date's batch and still expects Failed Duplicate, 0 rows, no new
Contact; its statements of the one-session-per-club-per-day refusal say which case they are), the
salesforce skill (no longer "a second batch is always Duplicate"), a plan for the live Apex change
with Rollout (validate, go, deploy, retrieve, proof, read-back, in that order), Rollback (only this
change's two classes, from a fresh retrieve equal to its `after/`) and Result, and a dated DECISIONS
entry with substance. The tests read for meaning, not prose: only what a reader of the rendered page
sees counts (HTML comments, fenced and indented code, link reference definitions, image alt text, link
targets and titles, collapsed or hidden HTML do not; a plan's Rollout and Rollback keep their fenced
commands), a statement told as the past does not count, and a reasonable wording passes. Counts only,
no girl's name. The helpers are test/runbook_test.py's (flat, md_part, sentences), over the visible text.
"""
import os
import re
import sys
import unittest

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import REPO, read

RUNBOOK = os.path.join(REPO, "docs", "RUNBOOK.md")
SKILL = os.path.join(REPO, ".claude", "skills", "salesforce", "SKILL.md")
PLAN = os.path.join(REPO, "docs", "plans", "2026-10-22-correction-merge.md")
DECISIONS = os.path.join(REPO, "docs", "DECISIONS.md")


def flat(text):
    return " ".join(text.split())


FENCE = re.compile(r"(?ms)^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?^[ \t]*\1[ \t]*$")
# what a Markdown renderer never shows as text: a link reference definition (its title included), an image's
# alt text, a link's destination and title, a <details> block (collapsed until clicked), a script-like or
# hidden HTML element
LINK_REF = re.compile(r"(?m)^ {0,3}\[[^\]\n]+\]:[ \t]*\S[^\n]*$")
IMAGE = re.compile(r"!\[[^\]\n]*\](?:\([^)\n]*\)|\[[^\]\n]*\])")
LINK_TARGET = re.compile(r"(?<=\])\([^()\s]*(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)")
HIDDEN_HTML = re.compile(r"(?is)<(details|script|style|template|noscript)\b[^>]*>.*?</\1\s*>|"
                         r"<([a-z][\w-]*)\b[^>]*\b(?:hidden\b|display\s*:\s*none)[^>]*>.*?</\2\s*>")
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")


def without_indented_code(text):
    """`text` with its indented code blocks blanked: a run of lines indented four spaces (or a tab) that follows
    a blank line and is not inside a list (the nearest line above it starts at the margin and is no list
    item) renders as code, not as a statement. Indented text under a list item is the item's own."""
    out, prev, after_blank, in_code = [], "", True, False
    for line in text.split("\n"):
        indented = re.match(r"^(?: {4}|\t)\S", line) is not None
        if in_code and (indented or not line.strip()):
            out.append("")
            continue
        in_code = False
        if indented and after_blank and (not prev or (prev[0] not in " \t" and not LIST_ITEM.match(prev))):
            in_code = True
            out.append("")
            continue
        out.append(line)
        if line.strip():
            prev, after_blank = line, False
        else:
            after_blank = True
    return "\n".join(out)


def visible(text, keep_fences=False):
    """`text` as a reader of the rendered page sees the document's own statements: without its HTML comments,
    fenced code (kept with keep_fences: a plan's commands are its procedure) and indented code, link reference
    definitions, image alt text, link targets and titles, collapsed and hidden HTML. A paragraph in any of
    them says nothing."""
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    if not keep_fences:
        text = FENCE.sub(" ", text)
    text = HIDDEN_HTML.sub(" ", text)
    text = LINK_REF.sub(" ", text)
    text = IMAGE.sub(" ", text)
    text = LINK_TARGET.sub("", text)
    return without_indented_code(text)


def doc(path, keep_fences=False):
    return visible(read(path), keep_fences)


def md_part(path, heading, keep_fences=False):
    """A Markdown file's part under the first heading line that starts with `heading`, that line
    included, to the next heading of its level or higher. A missing heading fails."""
    text = doc(path, keep_fences)
    m = re.search(r"^" + re.escape(heading) + r"(?!\w).*$", text, re.M)
    if not m:
        raise AssertionError(f"{os.path.relpath(path, REPO)}: no heading starting `{heading}`")
    level = len(heading) - len(heading.lstrip("#"))
    rest = text[m.start():]
    nxt = re.search(r"\n#{1,%d} " % level, rest)
    return rest[:nxt.start()] if nxt else rest


def sentences(text, ends=".;:"):
    """`text` (flattened) cut after each of `ends`."""
    return [s for s in re.split(r"(?<=[%s])\s+" % re.escape(ends), flat(text)) if s.strip()]


def blocks(text):
    """The paragraphs, list items and table rows of the visible `text`, each flattened to one line."""
    out, cur = [], []
    for line in visible(text).split("\n"):
        if not line.strip() or re.match(r"^\s*([-*]|\d+\.|\|)\s", line):
            if cur:
                out.append(flat("\n".join(cur)))
            cur = [line] if line.strip() else []
        else:
            cur.append(line)
    if cur:
        out.append(flat("\n".join(cur)))
    return out


# a statement told as the past does not count - "no longer X" tells what X used to be, nothing of today
PAST = re.compile(r"\b(used to|formerly|no longer|not any ?more|before 2026-10-2\d|until 2026-10-2\d|"
                  r"before (this|that|the) (change|rule|merge)|the old rule|before #108)\b", re.I)


def live(text):
    """`text` (flattened) with every sentence told as the past taken out."""
    return " ".join(s for s in sentences(text, ".;") if not PAST.search(s))


def live_blocks(text):
    """blocks(text), each without its sentences told as the past, the empty ones dropped."""
    return [b for b in (live(b) for b in blocks(text)) if b]


def ticket(text):
    return re.search(r"(?<![\w#])#108\b", text) is not None


# a mentor's corrected re-submission, in any words
CORRECTION = re.compile(r"\b(correct(ed|ion|ions)|re-?submi(ssion|ssions|tted|ts)|second (submission|batch)|"
                        r"(sent|submitted) again|later (submission|batch))\b", re.I)
# only the girls not yet on that date
ONLY_MISSING = re.compile(r"\b(only|just|nothing but)\b[^.;]{0,80}?\b(missing|absent|lacking|forgotten|"
                          r"not (yet|already)\b|new to\b|not (on|in) (that|the) (date|day)|aren['’]t (on|in)|"
                          r"are not (on|in)|without a row)", re.I)
NOT_YET = re.compile(r"\bnot (yet|already) (on|in|among|booked|there)\b|\bmissing (from|on)\b|\babsent from\b|"
                     r"\bwithout a row\b|\bno row (yet|on)\b", re.I)
# the original batch or session, by any of its names, or the merge message
ORIGINAL = re.compile(r"\b(original|first|earlier|existing)\b[^.;]{0,30}\b(batch|session|submission)\b|merged into", re.I)
MERGED_INTO = re.compile(r"merged into", re.I)
DUPLICATE = re.compile(r"\bDuplicate\b")
# the refusal named in any case: the status word, or "refused as a duplicate"
DUPLICATE_ANY = re.compile(r"\bDuplicate\b|\bas a duplicate\b|\bduplicate (check|rule|refusal)\b", re.I)
# a different module or event
OTHER_MODULE = re.compile(r"\b(different|another|other|unlike|not the same)\b[^.;]{0,25}\b(module|event)\b|"
                          r"\bmodule\b[^.;]{0,30}\b(differs|different|does not match|not the same|unequal)\b", re.I)
# a correction that adds nobody
NOBODY = re.compile(r"\b(adds?|adding|ticks?|ticking|brings?|lists?|names?|with)\b[^.;]{0,20}?\b(nobody|no one|no girl|"
                    r"none|no new|no missing|nothing new)\b|\b(nothing|no girl|nobody|none) (new|to add|missing)\b|"
                    r"\b(every|all|each)\b[^.;]{0,20}\bgirls?\b[^.;]{0,50}\balready\b|\balready\b[^.;]{0,50}\b(every|all|each)\b[^.;]{0,20}\bgirls?\b",
                    re.I)
# a statement of the refusal says which case it is: a different module (an event on a curriculum day), nobody new
QUALIFIED = re.compile("|".join((OTHER_MODULE.pattern, NOBODY.pattern,
                                 r"\b(same|matching|its|that) module\b|\bmodule\b[^.;]{0,25}\b(differs?|other than|is not)\b",
                                 r"\b(welcome session|special event|idg celebrations|an? event|the event['’]s)\b[^.;]{0,80}\bcurriculum\b",
                                 r"\bcurriculum\b[^.;]{0,80}\b(welcome session|special event|idg celebrations|an? event|the event['’]s)\b",
                                 r"\balready on\b|\bnobody new\b|\bno new girl\b")), re.I)
# a sentence that states what the processor does with such a batch (not a SOQL read-back expectation)
RULE = re.compile(r"\b(refus\w*|rejected|fails?|arrives?|comes? back|stays?|remains?|is|are|such a batch|would make)\b", re.I)
READ_BACK = re.compile(r"Processing_Status__c\s*=|Status_Message__c\s+LIKE|\bSELECT\b")


def unqualified(text):
    """The live sentences of `text` that state the refusal without saying which case it is."""
    return [s for s in sentences(text, ".;:") if not PAST.search(s) and DUPLICATE_ANY.search(s) and RULE.search(s)
            and not QUALIFIED.search(s) and not READ_BACK.search(s)]


class CorrectionMergeRunbook(unittest.TestCase):
    """docs/RUNBOOK.md says what a correction does now, its statements of the refusal say which case they
    are, and the template-test recipe no longer relies on the refusal."""

    longMessage = False

    def test_the_runbook_says_what_a_correction_does(self):
        text = doc(RUNBOOK)
        paragraphs = live_blocks(text)
        # (1) only the girls not yet on that date are added, to the original batch / session
        adds = [b for b in paragraphs if CORRECTION.search(b) and ONLY_MISSING.search(b) and ORIGINAL.search(b)]
        self.assertTrue(adds, "docs/RUNBOOK.md: say what a mentor's corrected re-submission does now - with the same "
                              "module it adds only the girls not yet on that date (the missing ones), as rows of the "
                              "original batch - in one paragraph")
        # (2) the correction's own batch is Success with the message `merged into <original id>`
        merged = [b for b in paragraphs if CORRECTION.search(b) and MERGED_INTO.search(b)]
        self.assertTrue(merged, "docs/RUNBOOK.md: say the correction's own batch is `Success` with the message `merged "
                                "into <original batch id>` (no count, no rows of its own)")
        sents = [s for b in paragraphs for s in sentences(b, ".;")]
        # (3) a different module (an event on a curriculum day) is still refused as Duplicate
        other = [s for s in sents if OTHER_MODULE.search(s) and DUPLICATE.search(s)
                 and re.search(r"\b(still|stays|remains|refused|is)\b", s, re.I)]
        self.assertTrue(other, "docs/RUNBOOK.md: say a re-submission with a different module (or event) is still "
                               "`Failed` \"Duplicate\" - one session per club per day")
        # (4) a correction that adds nobody is still refused as Duplicate
        nobody = [s for s in sents if NOBODY.search(s) and DUPLICATE.search(s)]
        self.assertTrue(nobody, "docs/RUNBOOK.md: say a re-submission that adds nobody (every girl ticked is already on "
                                "that date) stays `Failed` \"Duplicate\"")
        # (5) the original's count follows its rows
        count = [s for s in sents if "Girls_Present__c" in s
                 and (ORIGINAL.search(s) or re.search(r"\b(new total|its rows|that (date|day)['’]s rows)\b", s, re.I))
                 and re.search(r"\b(moves?|moved|follows?|becomes?|grows?|set to|updated|the new total|its rows)\b", s, re.I)]
        self.assertTrue(count, "docs/RUNBOOK.md: say the original batch's `Girls_Present__c` moves to the new total "
                               "(the count of that date's rows after the merge)")
        # (6) what a merged batch counts as on the dashboard (no second session, not a blank)
        counts_as = [s for s in sents if re.search(r"\bmerged\b", s, re.I)
                     and re.search(r"\b(sessions?|blank|submitted|tiles?|counts?|counted|dashboard)\b", s, re.I)]
        self.assertTrue(counts_as, "docs/RUNBOOK.md: say what a merged correction counts as for the dashboard (not a "
                                   "second session nor a blank: its girls count through the original)")

    def test_the_refusal_is_stated_with_its_case_where_the_runbook_states_it(self):
        # "one submission per club per day" is still true of a different module (a special event on a curriculum
        # day) and of a correction that adds nobody; a sentence that states the refusal must say which, or a
        # reader takes the 2026-10-13 rule for the whole rule. The Special events section (two statements of it
        # on 2026-10-22) and the template-test recipe are where the RUNBOOK states it.
        for heading, where in (("## Special events", "docs/RUNBOOK.md \"Special events\""),
                               (None, "docs/RUNBOOK.md, the \"Jotform template test\" recipe")):
            text = md_part(RUNBOOK, heading) if heading else self.recipe()
            self.assertEqual(unqualified(text), [], f"{where}: a statement of the Duplicate refusal does not say which "
                                                    f"case it is (a different module or event, nobody new): "
                                                    f"{unqualified(text)[:2]}")

    def recipe(self):
        """The "Jotform template test" recipe: from the test-submission step to the regional forms step."""
        text = doc(RUNBOOK)
        m = re.search(r"test submission on the template", text, re.I)
        self.assertTrue(m, "docs/RUNBOOK.md: the \"Jotform template test\" recipe (\"One test submission on the template\") "
                           "is gone")
        start = text.rfind("\n", 0, m.start())
        end = text.find("**The regional forms**", m.start())
        self.assertGreater(end, start, "docs/RUNBOOK.md: the recipe runs to the \"**The regional forms**\" step")
        return text[start:end]

    def test_the_template_test_ticks_only_girls_already_on_that_dates_batch(self):
        recipe = self.recipe()
        sents = [s for s in sentences(recipe, ".;:") if not PAST.search(s)]
        where = "docs/RUNBOOK.md, the \"Jotform template test\" recipe"
        tick = [s for s in sents if re.search(r"\btick", s, re.I)
                and re.search(r"\b(only|just|nobody new|no new|no girl who)\b", s, re.I)
                and re.search(r"\balready\b|\b(on|of) that (date|day)['’]s batch\b|\bthat (date|day) already has\b", s, re.I)]
        self.assertTrue(tick, f"{where}: tick only girls already on that date's batch (a girl not yet on it would now be "
                              "added to the original session)")
        # the reason has changed: no live sentence says the processor refuses the batch before reading any name
        # (a "no longer" sentence tells the past and counts for nothing, either way)
        reads = [s for s in sents if re.search(r"\bbefore\b[^.;]{0,25}\breads? any name", s, re.I)]
        self.assertEqual(reads, [], f"{where}: still says the processor refuses a second batch before it reads any name "
                                    f"({reads[:1]})")
        why = [s for s in sents if NOBODY.search(s) and DUPLICATE.search(s)]
        self.assertTrue(why, f"{where}: say why the submission still changes nothing - it adds nobody, so it is refused "
                             "as Duplicate")
        self.assertEqual(unqualified(recipe), [], f"{where}: a statement of the Duplicate refusal does not say which case "
                                                  f"it is (nobody new): {unqualified(recipe)[:2]}")
        # the read-back still expects Failed Duplicate, 0 rows, no new Contact
        text = flat(recipe)
        self.assertRegex(text, r"Processing_Status__c\s*=\s*'Failed'|`Failed`", f"{where}: the read-back expects `Failed`")
        self.assertRegex(text, r"Duplicate", f"{where}: the read-back expects \"Duplicate\"")
        self.assertRegex(text, r"\b0\b[^.;]{0,20}`?Attendance__c`?\s+rows|\bno attendance row|\b0 rows\b",
                         f"{where}: the read-back expects 0 `Attendance__c` rows")
        self.assertRegex(text, r"no new\s+`?Contact`?|no `?Contact`?\s+(is\s+)?(created|made)|Contact\b[^.;]{0,60}\bunchanged",
                         f"{where}: the read-back expects no new Contact")


class CorrectionMergeSkill(unittest.TestCase):
    """.claude/skills/salesforce/SKILL.md "What lives there" no longer says a second batch is always
    Failed Duplicate, and says what one does instead."""

    longMessage = False

    def test_the_skill_no_longer_says_a_second_batch_is_always_duplicate(self):
        part = md_part(SKILL, "## What lives there")
        sents = [s for s in sentences(part, ".;") if not PAST.search(s)]
        where = ".claude/skills/salesforce/SKILL.md, \"What lives there\""
        qualified = re.compile(r"\b(module|event|merge|merged|unless|only (if|when)|nobody|no one|adds? no|no new|"
                               r"missing|not yet|already on)\b", re.I)
        unqualified_ = [s for s in sents if DUPLICATE.search(s) and re.search(r"\bSuccess\b", s) and not qualified.search(s)]
        self.assertEqual(unqualified_, [], f"{where}: still says a batch for a club and date that has a `Success` one is "
                                           f"always `Failed` \"Duplicate\" ({unqualified_[:1]}); since 2026-10-22 one with "
                                           "the same module adds its missing girls to it")
        # the rule in one place: the merge message, the module condition and what is added - only the girls not yet
        # on that date - together in a bullet or paragraph (its sentences told as the past aside)
        merged = [b for b in live_blocks(part) if MERGED_INTO.search(b) and re.search(r"\bmodule\b", b, re.I)
                  and (ONLY_MISSING.search(b) or NOT_YET.search(b))]
        self.assertTrue(merged, f"{where}: say that a second batch with the same module adds only the girls not yet on "
                                "that date to the first one (`merged into <id>`), and a different module or nobody new "
                                "is Duplicate")
        self.assertTrue([s for s in sents if DUPLICATE.search(s) and (OTHER_MODULE.search(s) or NOBODY.search(s))],
                        f"{where}: say when a second batch is still `Failed` \"Duplicate\" (a different module, nobody new)")


class CorrectionMergePlan(unittest.TestCase):
    """docs/plans/2026-10-22-correction-merge.md carries the live Apex change: front matter like its
    neighbours (status accepted, ticket #108), Rollout in the ritual's order, Rollback and Result."""

    longMessage = False
    CLASSES = ("AttendanceBatchProcessor", "AttendanceBatchTriggerTest")
    # what the rollback must not redeploy: the trigger and the other test class, unless named as left alone
    OTHERS = (r"\bAttendanceBatchTrigger\b(?!Test)", r"\bTestContactTriggerHandler\b")
    LEFT_ALONE = re.compile(r"\b(not|never|neither|nor|no|without|stays?|stay as|unchanged|untouched|left|as retrieved|"
                            r"only)\b", re.I)
    VALIDATE = re.compile(r"check-only|\bvalidat\w*|--dry-run", re.I)
    GO = re.compile(r"Ryan['’]s\s+go\b|\bthe go\b|\bhis go\b|\bgo from Ryan\b", re.I)
    DEPLOY = re.compile(r"\bdeploy", re.I)
    # a deploy named inside a check-only context: `… deploy validate …`, a code span with --dry-run or validate
    VALIDATE_CONTEXT = re.compile(r"`[^`]*(--dry-run|validat)[^`]*`|deploy\s+validate|check-only[^.;:]{0,20}deploy|"
                                  r"validat\w*[^.;:]{0,20}deploy|deploy[^.;:`]{0,40}--dry-run", re.I)
    COMPARE_AFTER = re.compile(r"\b(retriev\w*|compar\w*|equals?|diff\w*)\b[^.;]{0,160}\bafter/|"
                               r"\bafter/[^.;]{0,160}\b(retriev\w*|compar\w*|equals?|diff\w*)\b", re.I)
    READ_BACK = re.compile(r"\bread[- ]back\b|\breads? (it |them |each |the \w+ )?back\b", re.I)
    # the check-only command, shown: `sf project deploy validate …` (or a deploy with --dry-run)
    VALIDATE_COMMAND = re.compile(r"sf project deploy validate\b|--dry-run")

    @staticmethod
    def first(rx, text, start=0):
        m = rx.search(text, start)
        return m.start() if m else None

    @staticmethod
    def commands(part):
        """The commands a plan part shows: its fenced code blocks and inline code spans, each flattened."""
        fences = [flat(m.group(0).split("\n", 1)[1].rsplit("\n", 1)[0]) for m in FENCE.finditer(part)]
        spans = [flat(m.group(1)) for m in re.finditer(r"`([^`\n]+)`", FENCE.sub(" ", part))]
        return fences + spans

    def live_deploy(self, text):
        """Where the Rollout first deploys for real: the first `deploy` outside a check-only context."""
        contexts = [m.span() for m in self.VALIDATE_CONTEXT.finditer(text)]
        for m in self.DEPLOY.finditer(text):
            if not any(a <= m.start() < b for a, b in contexts):
                return m.start()
        return None

    def test_a_plan_carries_the_live_change(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        name = os.path.relpath(PLAN, REPO)
        self.assertTrue(os.path.exists(PLAN), f"{name}: no plan for the live Apex change (CLAUDE.md conventions)")
        text = doc(PLAN)
        keys, _ = docs_index.frontmatter(read(PLAN))
        for key in ("title", "status", "created"):
            self.assertIn(key, keys, f"{name}: frontmatter `{key}:` (docs/templates/plan.md)")
        word, problem = docs_index.status_of(keys["status"])
        self.assertIsNone(problem, f"{name}: {problem}")
        self.assertIn(word, ("accepted", "in-progress", "done"),
                      f"{name}: the plan is accepted (Ryan's decision of 2026-10-22), not `{word}`")
        if word == "done":
            self.assertRegex(keys.get("done", ""), r"^\d{4}-\d\d-\d\d", f"{name}: a done plan carries `done:`")
        self.assertTrue(ticket(text.split("\n## ", 1)[0]),
                        f"{name}: name ticket #108 in the frontmatter, the title or the opening paragraph")
        for heading in ("## Rollout", "## Rollback", "## Result"):
            self.assertRegex(text, r"(?m)^" + re.escape(heading) + r"\b", f"{name}: no `{heading}` section")
        bodies, parts = {}, {}
        for heading, least in (("## Rollout", 60), ("## Rollback", 25)):
            part = md_part(PLAN, heading, keep_fences=True)          # a plan's fenced commands are its procedure
            body = flat(part.split("\n", 1)[1] if "\n" in part else "")
            self.assertNotRegex(body, r"(?i)\b(TBD|TODO|TBA|FIXME)\b", f"{name}: `{heading}` is a placeholder")
            self.assertGreaterEqual(len(re.findall(r"\w+", body)), least,
                                    f"{name}: `{heading}` says too little (at least {least} words): the steps")
            bodies[heading], parts[heading] = body, part
        rollout, rollback = bodies["## Rollout"], bodies["## Rollback"]
        # Rollout, in the ritual's order: a check-only validate running the two test classes, then Ryan's go, then
        # the deploy, then the retrieve compared with after/, then a rolled-back proof with fictional names and
        # the read-back (the same words in another order are another procedure)
        validate = self.first(self.VALIDATE, rollout)
        self.assertIsNotNone(validate, f"{name}: the Rollout validates check-only first")
        deploy = self.live_deploy(rollout)
        self.assertIsNotNone(deploy, f"{name}: the Rollout deploys the processor")
        self.assertLess(validate, deploy, f"{name}: the Rollout's check-only validate comes before its deploy")
        go = self.first(self.GO, rollout, validate)
        self.assertIsNotNone(go, f"{name}: the Rollout's deploy waits for Ryan's go, after the validate")
        self.assertLess(go, deploy, f"{name}: Ryan's go comes between the validate and the deploy, not after the deploy")
        self.assertIn("RunSpecifiedTests", rollout, f"{name}: the Rollout's validate runs the specified tests")
        self.assertLess(rollout.index("RunSpecifiedTests"), go, f"{name}: RunSpecifiedTests belongs to the validate, before the go")
        for cls in ("AttendanceBatchTriggerTest", "TestContactTriggerHandler"):
            self.assertIn(cls, rollout, f"{name}: the Rollout names the test class `{cls}`")
            self.assertLess(rollout.index(cls), go, f"{name}: the test class `{cls}` is named by the validate, before the go")
        # the validate step shows its command - a code span or fence with `sf project deploy validate` (or a deploy
        # with --dry-run) naming both test classes - before the go
        shown = [c for c in self.commands(parts["## Rollout"]) if self.VALIDATE_COMMAND.search(c)
                 and "AttendanceBatchTriggerTest" in c and "TestContactTriggerHandler" in c]
        self.assertTrue(shown, f"{name}: the Rollout shows the check-only command in code (`sf project deploy validate … "
                               "-l RunSpecifiedTests -t AttendanceBatchTriggerTest -t TestContactTriggerHandler`)")
        self.assertTrue(any(c in rollout and rollout.index(c) < go for c in shown),
                        f"{name}: the check-only command is the validate step, before the go")
        # the Rollout names this change's data/sf_processor_<date>/ folder: the fresh retrieve it starts from
        self.assertRegex(rollout, r"data/sf_processor_\d{4}-\d\d-\d\d",
                         f"{name}: the Rollout names this change's `data/sf_processor_<date>/` folder (the fresh retrieve)")
        after = self.first(self.COMPARE_AFTER, rollout, deploy)
        self.assertIsNotNone(after, f"{name}: after the deploy, the Rollout retrieves and compares with `after/`")
        proof = self.first(re.compile(r"\bfictional\b", re.I), rollout, after)
        self.assertIsNotNone(proof, f"{name}: the Rollout's proof uses fictional names, after the retrieve and compare")
        proof_step = rollout[max(0, proof - 400):proof + 600]
        self.assertRegex(proof_step, r"(?i)\b(roll(ed|s)?[- ]back|rolled back|deleted|removed)\b",
                         f"{name}: the Rollout's proof is rolled back (its batches and contacts removed)")
        # ... and names what it expects: the correction's `merged into` and the original's rows / Girls_Present__c
        self.assertRegex(proof_step, MERGED_INTO, f"{name}: the proof step expects the correction's `merged into <id>`")
        self.assertRegex(proof_step, r"Girls_Present__c|Attendance__c|\brows?\b",
                         f"{name}: the proof step expects the original's rows (and its `Girls_Present__c`)")
        self.assertIsNotNone(self.first(self.READ_BACK, rollout, deploy), f"{name}: the Rollout reads back after the deploy")
        # Rollback: only this change's two classes, from this change's data/sf_processor_<date>/ folders - a fresh
        # retrieve equal to after/ first, then before/ - never an older build
        for cls in self.CLASSES:
            self.assertIn(cls, rollback, f"{name}: the Rollback names `{cls}`")
        self.assertRegex(rollback, r"(?i)\bre-?deploy", f"{name}: the Rollback redeploys")
        self.assertRegex(rollback, r"(?i)\bfresh\b[^.;]{0,20}\bretriev|\bretriev\w*\b[^.;]{0,30}\bfresh\b",
                         f"{name}: the Rollback starts from a fresh retrieve")
        self.assertRegex(rollback, r"data/sf_processor_\d{4}-\d\d-\d\d",
                         f"{name}: the Rollback names this change's `data/sf_processor_<date>/` folder")
        self.assertRegex(rollback, r"after/", f"{name}: the Rollback's retrieve must equal this change's `after/`")
        self.assertRegex(rollback, r"before/", f"{name}: the Rollback names `before/`, the classes as retrieved before")
        self.assertRegex(rollback, r"(?i)\b(never|not)\b[^.;]{0,40}\b(older|old|earlier|previous)\b[^.;]{0,15}"
                                   r"\b(build|copy|package|retrieve|version)\b|2026-10-16",
                         f"{name}: the Rollback never redeploys an older build (DECISIONS 2026-10-16)")
        for other in self.OTHERS:
            naming = [s for s in sentences(rollback, ".;") if re.search(other, s)]
            self.assertEqual([s for s in naming if not self.LEFT_ALONE.search(s)], [],
                             f"{name}: the Rollback redeploys only the two classes this change deploys; {other} is "
                             "named without saying it stays")
        # Result: pending until something is deployed, or dated
        result = flat(md_part(PLAN, "## Result"))
        self.assertRegex(result, r"(?i)\bpending\b|nothing (is )?deployed|not (yet )?deployed|\b2026-\d\d-\d\d\b",
                         f"{name}: the Result says pending (nothing deployed yet) or carries a dated result")
        # the plan names the rule it carries
        whole = flat(text)
        self.assertRegex(whole, MERGED_INTO, f"{name}: the plan names the message `merged into <original id>`")
        self.assertRegex(whole, r"Girls_Present__c", f"{name}: the plan says what happens to `Girls_Present__c`")
        self.assertRegex(whole, r"(?i)\bmodule\b", f"{name}: the plan says the merge needs the same module")


class CorrectionMergeDecision(unittest.TestCase):
    """docs/DECISIONS.md: a dated 2026-10-22 entry for Ryan's decision, with the file's Why, Rejected and
    Consequences bullets, each with substance; the 2026-10-13 entry, which rejected letting a second batch
    per club and day through, gets a dated bullet pointing at it (the file's header)."""

    longMessage = False
    LEAST_WORDS = 15            # words of substance: a date and the name of whose decision it is do not count

    def entries(self):
        return re.split(r"(?m)^(?=### )", doc(DECISIONS))[1:]

    @staticmethod
    def bullet(entry, name):
        """The text of the entry's `- **<name>:**` bullet (the file's convention: one per entry), or ''."""
        m = re.search(r"(?ms)^\s*-\s+\*\*" + name + r":?\*\*:?\s*(.*?)(?=^\s*-\s|\Z)", entry)
        return flat(m.group(1)) if m else ""

    @staticmethod
    def words(body):
        """The words of a bullet, dates and Ryan's name left out."""
        return [w for w in re.findall(r"\b[A-Za-z][\w'’-]*", re.sub(r"\b\d{4}-\d\d-\d\d\b", " ", body)) if w != "Ryan"]

    def test_a_decision_records_the_merge_rule(self):
        entries = self.entries()
        new = [e for e in entries if e.startswith("### 2026-10-22") and (ticket(e) or CORRECTION.search(e))
               and MERGED_INTO.search(e)]
        self.assertTrue(new, "docs/DECISIONS.md: no `### 2026-10-22 — …` entry for ticket #108 (a corrected re-submission "
                             "adds its missing girls; `merged into`)")
        e = new[0]
        where = "docs/DECISIONS.md 2026-10-22"
        parts = {name: self.bullet(e, name) for name in ("Why", "Rejected", "Consequences")}
        for name, body in parts.items():
            self.assertTrue(body, f"{where}: no `- **{name}:**` bullet (the file's header)")
            self.assertGreaterEqual(len(self.words(body)), self.LEAST_WORDS,
                                    f"{where}: the **{name}** bullet says too little ({body[:60]!r}): at least "
                                    f"{self.LEAST_WORDS} words besides the date and the name")
        # Why: Ryan's decision of 2026-10-22, as the file cites a decision ("**Why:** Ryan, 2026-10-13: …")
        self.assertRegex(parts["Why"], r"\bRyan\b", f"{where}: the **Why** cites Ryan, whose decision it is")
        self.assertIn("2026-10-22", parts["Why"], f"{where}: the **Why** cites the date of the decision, 2026-10-22")
        # Rejected: the options not taken, each with its reason - a new picklist value (a new status); keeping the
        # refusal and only reporting it to staff
        rejected = parts["Rejected"]
        # a reason: a parenthesis of at least three words (the file's way: "(it would mean changing …)"), or a
        # reason's own words; a bare "(a)" or "(b)" is a label, not a reason
        reason = re.compile(r"\((?:[^()]*?\b\w+\b){3}|\bbecause\b|\bsince\b|\bwould\b|\bmeans\b|\bso that\b|"
                            r"\bas (it|they|that)\b|\btouch\w*\b", re.I)
        for option, rx in (("a new picklist value", r"\bpicklist\b|\bnew (status )?(value|status)\b"),
                           ("keeping the refusal and only reporting it",
                            r"\b(keep\w*|leav\w*|stay\w*|still)\b[^;.]{0,50}\b(refus\w*|fail\w*|Duplicate)\b|\bonly report\w*|"
                            r"\breport\w*\b[^;.]{0,30}\b(only|to staff|instead)\b|\(b\)")):
            naming = [s for s in re.split(r";\s+", rejected) if re.search(rx, s, re.I)]
            self.assertTrue(naming, f"{where}: the **Rejected** bullet names {option}")
            self.assertTrue(any(reason.search(s) for s in naming), f"{where}: the **Rejected** bullet gives a reason "
                                                                    f"for not taking {option}")
        text = flat(e)
        self.assertTrue(ONLY_MISSING.search(text) or re.search(r"(?i)\bnever (removes?|removed|count\w* .{0,20}twice)", text),
                        f"{where}: say only the girls not yet on that date are added (never a row removed, never a girl "
                        "counted twice)")
        self.assertRegex(text, r"Girls_Present__c", f"{where}: say the original's `Girls_Present__c` moves to the new total")
        self.assertRegex(text, r"(?i)\bmodule\b", f"{where}: say the merge needs the same module")
        self.assertTrue([s for s in sentences(text, ".;") if DUPLICATE.search(s) and (OTHER_MODULE.search(s) or NOBODY.search(s))],
                        f"{where}: say a different module, or a correction adding nobody, stays `Failed` \"Duplicate\"")
        # no new picklist value: a sentence that names one says no to it
        naming = [s for s in sentences(text, ".;") if re.search(r"(?i)\bnew (picklist )?(value|status)\b", s)]
        self.assertEqual([s for s in naming if not re.search(r"(?i)\b(no|not|never|none|rejected|without)\b", s)], [],
                         f"{where}: the correction's batch is `Success` with the message - no new picklist value")

    def test_the_amended_decision_points_at_it(self):
        old = [e for e in self.entries() if e.startswith("### 2026-10-13") and re.search(r"(?i)same-day rule", e.split("\n")[0])]
        self.assertTrue(old, "docs/DECISIONS.md: the 2026-10-13 special-events entry (the same-day rule stays) is missing")
        where = "docs/DECISIONS.md 2026-10-13"
        # the file's convention (its header; every amended entry): a dated bullet `- YYYY-MM-DD: …` appended after the
        # entry's own bullets - the decision, Why, Rejected, Consequences and the earlier dated ones (here 2026-10-14)
        bullets = re.findall(r"(?m)^- (.*)$", old[0])
        pointer = [i for i, b in enumerate(bullets) if re.match(r"2026-10-22\b", b) and re.search(r"(?<![\w#])#108\b|merged", b)]
        self.assertTrue(pointer, f"{where}: add a dated bullet pointing at the new rule, e.g. \"- 2026-10-22: amended - a "
                                 "second batch with the same module adds its missing girls to the first (#108); a "
                                 "different module stays Duplicate\"")
        own = [i for i, b in enumerate(bullets) if b.startswith("**Consequences") or re.match(r"2026-10-1\d\b", b)]
        self.assertTrue(own, f"{where}: the entry's **Consequences** bullet and its 2026-10-14 bullet are gone")
        self.assertGreater(pointer[0], max(own), f"{where}: the 2026-10-22 bullet goes after the entry's existing bullets "
                                                 "(after **Consequences** and the 2026-10-14 bullet), as the file appends them")
        later = bullets[pointer[0] + 1:]
        self.assertEqual([b for b in later if not re.match(r"2026-(10-2[2-9]|10-3\d|1[12]-\d\d)\b", b)], [],
                         f"{where}: nothing but later dated bullets follows the 2026-10-22 bullet")


if __name__ == "__main__":
    unittest.main(verbosity=1)
