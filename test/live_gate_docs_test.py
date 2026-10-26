#!/usr/bin/env python3
"""
Ticket #146's documentation: CLAUDE.md "Things Claude gets wrong" rule 1, docs/RUNBOOK.md "Live
gate (Claude Code)", the plan template (docs/templates/plan.md) and docs/DECISIONS.md describe the
automatic go for a backed-up live write - its condition (a backup from today), the log and the
notification, and what still asks (deletes and --prune) - and no longer say the gate never allows
or that a headless run never runs a live command.

Statements, not words (reviews of the first tests: docs that held every keyword, or every phrase,
and said the opposite passed - "a write with a backup from today is allowed once Ryan answers the
prompt. Deletes and --prune go through too, and nobody asks"). Each doc is cut into sentences (at
`.` and `;`) and must hold:
  - the automatic go, in a sentence of its own: ONE sentence that names a backup (or a backed-up
    write), today, and the go said PROMPT-LESS - without (or with no) prompt, no prompt,
    automatic(ally), auto-approved, on its own; "allow" or "goes through" alone no longer count.
    With those phrases set aside, the sentence holds no negation (never, not, n't, cannot, no, no
    longer, nothing, nobody, no one, none, nowhere, nor, without, rejected, regardless, whether,
    whatever, before today, yesterday, stale, older, predates) and nothing that makes the go wait
    for Ryan after all (answer, confirm, wait, approval by Ryan, once / after / until / if Ryan,
    prompt, ask, refuse, deny, block, skip, bypass);
  - what still asks, in a sentence of its own: ONE sentence that names --prune or a delete and
    ask (asks, asked, asking) or refuse, with no negation of the asking ("unasked", "no longer
    ask", "never ask", "not ask", "without asking", nobody, no one, none, nowhere, nothing, "only
    when", "only if", unless) and nothing in it let through (below);
and must not hold a sentence that names a delete or --prune and lets something through - goes
through, goes ahead, without a prompt (other than "a run / session / mode without a prompt"), with
no prompt, auto-approved, automatically allowed, allowed, on its own, unasked, nobody asks... - with
no negation of the going through (an ask in the same sentence is no excuse), nor the stock
inversions ("counts for nothing", "changes nothing", "makes no difference", "not adopted").
The RUNBOOK says the same of headless runs and subagents (the automatic go, said prompt-less, as
above), of a write without its backup (asked, and refused where no prompt shows - never "too",
"also" or "as well", which say a backed write asks), and of the notification (on an automatic go,
said prompt-less, as above). The reviewer judges the meaning; these stop the cheap inversions.
"""
import os
import re
import unittest

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import REPO, flat, md_part, read, sentences

RUNBOOK_MD = os.path.join(REPO, "docs", "RUNBOOK.md")
DECISIONS = os.path.join(REPO, "docs", "DECISIONS.md")
PLAN_TEMPLATE = os.path.join(REPO, "docs", "templates", "plan.md")
DECISION = "### 2026-10-26 — Backed-up live writes go through without a prompt"

BACKUP = re.compile(r"backup|backed[- ]up", re.I)
TODAY = re.compile(r"\btoday\b", re.I)
# the go, said prompt-less (breaker, round 2: "allowed once Ryan answers the prompt" is a prompt);
# "the automatic sync" is the project's name for the auto-sync, no go
PROMPTLESS = re.compile(r"\bwithout (a |the |any |Ryan's |his )?(prompt|answer|approval|go)\b|\bwith no prompt\b|\bno prompt\b"
                        r"|\bautomatic(ally)?\b(?![- ]sync)|\bauto-approv\w*|\bon (its|their) own\b", re.I)
NEGATION = re.compile(r"\bnever\b|\bnot\b|n't\b|\bcannot\b|\bno longer\b|\bnothing\b|\bnor\b|\brejected\b|\bno\b"
                      r"|\bnobody\b|\bno one\b|\bnone\b|\bnowhere\b|\bwithout\b|\bregardless\b|\bwhether\b|\bwhatever\b"
                      r"|\bbefore today\b|\byesterday|\bstale\b|\bolder\b|\bpredat", re.I)
# what makes a go wait for Ryan after all
HOLDS = re.compile(r"\banswer|(?<!auto-)\bapprov\w*\s+(by|of|from)\s+(Ryan|him)\b|\bconfirm|\bwait"
                   r"|\b(once|after|until|if)\s+(Ryan|he)\b|\bprompt|\bask|\brefus|\bden(y|ies|ied)\b|\bblock|\bskip|\bbypass",
                   re.I)
DELETE = re.compile(r"--prune|\bdelet", re.I)
ASK = re.compile(r"\bask(s|ed|ing)?\b|\brefus", re.I)
# the asking (or the refusal) negated
UNASKED = re.compile(r"\bunasked\b|\bno longer (be )?(ask|refus)|\bnever (be |get )?(ask|refus)|\bnot (be |get )?(ask|refus)"
                     r"|n't (be |get )?(ask|refus)|\bwithout asking\b|\bnobody\b|\bno one\b|\bnone\b|\bnowhere\b|\bnothing\b"
                     r"|\bonly (when|if)\b|\bunless\b", re.I)
LETS_THROUGH = re.compile(r"\bgo(es)? (through|ahead)\b|\bpass(es)? (through|unasked)\b"
                          r"|(?<!run )(?<!runs )(?<!session )(?<!sessions )(?<!mode )(?<!modes )\bwithout (a |the |any )?prompt\b"
                          r"|\bwith no prompt\b|\bauto-approv|\bautomatic(ally)? (go|allow|approv|appl)|\ballowed\b"
                          r"|\bon (its|their) own\b|\bunasked\b|\b(nobody|no one) (asks|is asked)\b", re.I)
HEADLESS = re.compile(r"headless|dispatched|dontAsk|subagent", re.I)
MISSING_BACKUP = re.compile(r"\b(without|no|missing)\b[^.;]{0,20}\bbackup", re.I)
TOO = re.compile(r"\btoo\b|\balso\b|\bas well\b|\blikewise\b|\bjust like\b|\bas (a|any|every) backed", re.I)
INVERSIONS = ("counts for nothing", "changes nothing", "makes no difference", "not adopted")


def statements(text):
    return sentences(text, ends=".;")


def promptless_go(sentence):
    """The sentence says a go with no prompt - and, with the prompt-less phrases set aside, holds
    no negation and nothing that makes the go wait for Ryan."""
    if not PROMPTLESS.search(sentence):
        return False
    rest = PROMPTLESS.sub(" ", sentence)
    return not NEGATION.search(rest) and not HOLDS.search(rest)


def lets_through(sentence):
    """Something in the sentence goes through, and its going through is not negated (a negation
    of the asking - nobody asks - is no negation of the going through)."""
    if not LETS_THROUGH.search(sentence):
        return False
    return not NEGATION.search(UNASKED.sub(" ", LETS_THROUGH.sub(" ", sentence)))


def still_asks(sentence):
    """The sentence says a delete or --prune asks (or is refused), and nothing in it goes through."""
    return bool(DELETE.search(sentence) and ASK.search(sentence) and not UNASKED.search(sentence)
                and not lets_through(sentence))


class LiveGateDocs(unittest.TestCase):
    RULE_1_BEFORE = 469         # rule 1's length on 2026-10-26, whitespace collapsed: no longer than it

    def rule_1(self):
        part = md_part(os.path.join(REPO, "CLAUDE.md"), "## Things Claude gets wrong")
        m = re.search(r"^1\. .*?(?=^2\. )", part, re.S | re.M)
        self.assertIsNotNone(m, "no rule 1 in CLAUDE.md's Things Claude gets wrong")
        return flat(m.group(0))

    def assert_states_the_rule(self, text, where, today=True):
        """The automatic go said prompt-less in a sentence of its own, what still asks in one, and
        no sentence that lets a delete through (the module's docstring)."""
        sents = statements(text)
        go = [s for s in sents if BACKUP.search(s) and (TODAY.search(s) or not today) and promptless_go(s)]
        self.assertTrue(go, f"{where}: no sentence says a live write with a backup from today goes through without a "
                            "prompt (one sentence naming a backup, today and without a prompt / no prompt / automatic / "
                            "auto-approved / on its own, with no negation and no answer, confirm, wait, once Ryan, "
                            "prompt, ask or refuse in it: say the go in a sentence of its own)")
        asks = [s for s in sents if still_asks(s)]
        self.assertTrue(asks, f"{where}: no sentence says deletes and --prune still ask (one sentence naming --prune or a "
                              "delete and ask or refuse, with nobody, unasked, never ask... and nothing let through in it)")
        through = [s for s in sents if DELETE.search(s) and lets_through(s)]
        self.assertEqual(through, [], f"{where}: a sentence names a delete or --prune and lets something through (say "
                                      "the go and what still asks in sentences of their own)")
        low = text.lower()
        for phrase in INVERSIONS:
            self.assertNotIn(phrase, low, f"{where} says {phrase!r}")

    def test_claude_md_rule_1_states_the_automatic_go_and_what_still_asks(self):
        rule = self.rule_1()
        self.assert_states_the_rule(rule, "CLAUDE.md rule 1")
        self.assertIn("live_gate.sh", rule, f"rule 1 does not name the hook: {rule}")
        self.assertNotIn("every live write needs ryan's explicit go", rule.lower(), "rule 1 still says the old rule")
        self.assertLessEqual(len(rule), self.RULE_1_BEFORE, "rule 1 grew")

    def test_the_runbook_describes_the_automatic_go(self):
        part = flat(md_part(RUNBOOK_MD, "## Live gate (Claude Code)"))
        for needle in (".claude/live_backups.log", "ALLOWED", "today", "backup_forms.py --form",
                       "sheets_client.py export", "github_switches.py backup", "--prune", "notif"):
            self.assertIn(needle, part, f"the RUNBOOK's live gate section does not say {needle!r}")
        for gone in ("never answers `allow`", "a headless run never runs a live command"):
            self.assertNotIn(gone, part, "the RUNBOOK still says the old rule")
        self.assert_states_the_rule(part, "the RUNBOOK's live gate section")
        sents = statements(part)
        # headless and dispatched runs, and subagents, get the same automatic go - said prompt-less
        # (breaker, round 2: "A headless run is allowed to wait for Ryan" passed)
        headless = [s for s in sents if HEADLESS.search(s) and promptless_go(s)]
        self.assertTrue(headless, "no sentence says a headless or dispatched run, or a subagent, gets the automatic go "
                                  "(without a prompt / automatic / on its own, with no negation, wait, answer or prompt)")
        # without the backup: asked in the session, refused where no prompt can show - and not "too"
        # (breaker, round 2: "A write with no backup asks Ryan too" passed)
        unbacked = [s for s in sents if MISSING_BACKUP.search(s) and not UNASKED.search(s) and not TOO.search(s)]
        self.assertTrue([s for s in unbacked if re.search(r"\bask(s|ed|ing)?\b", s, re.I)],
                        "no sentence says a write without its backup asks (and not 'too', 'also' or 'as well')")
        self.assertTrue([s for s in unbacked if re.search(r"\brefus|\bdenied\b|needs-input", s, re.I)],
                        "no sentence says a write without its backup is refused where no prompt can show")
        # every automatic go notifies Ryan - said prompt-less (breaker, round 2: "Ryan is notified when a
        # write waits for his go" passed)
        notified = [s for s in sents if re.search(r"notif", s, re.I) and promptless_go(s)]
        self.assertTrue(notified, "no sentence says an automatic go notifies Ryan (notif... with automatic / "
                                  "auto-approved / without a prompt, and no negation, wait, answer or prompt)")

    def test_the_plan_template_says_which_steps_go_through_and_which_still_ask(self):
        part = flat(md_part(PLAN_TEMPLATE, "## Rollout"))
        self.assert_states_the_rule(part, "the plan template's Rollout")
        self.assertNotIn("each step on ryan's go", part.lower(), "the template's Rollout still puts every step on Ryan's go")

    def test_decisions_records_the_change_and_the_earlier_decision_points_at_it(self):
        doc = read(DECISIONS)
        self.assertIn(DECISION, doc)
        earlier = "### 2026-10-14 — The live gate asks Ryan in the session"
        self.assertGreater(doc.index(DECISION), doc.index(earlier), "the decision is not after the one it changes")
        self.assertRegex(md_part(DECISIONS, earlier),
                         r"(?m)^- 2026-10-26\b.*Backed-up live writes go through without a prompt",
                         "no dated bullet on the 2026-10-14 decision pointing at the new one")
        # the decision itself - its bullets before **Why** - states the rule (the options not taken
        # belong under **Rejected**)
        body = md_part(DECISIONS, DECISION).split("\n", 1)[-1]           # without its heading
        decided = flat(body.split("**Why")[0])
        self.assertGreater(len(decided), 40, "the decision has no bullet before **Why**")
        self.assert_states_the_rule(decided, "the 2026-10-26 decision")
        for word in ("rejected", "not adopted", "withdrawn"):
            self.assertNotIn(word, decided.lower(), f"the decision's bullets say {word!r}")


if __name__ == "__main__":
    unittest.main(verbosity=1)
