#!/usr/bin/env python3
"""
On-time Monthly Reports, ticket #119 (epic #68), item 18 of `glow/sf_keep_list.csv`.

OnTimeDocs: Ryan, 2026-11-02 (the hold lifted on #119): GLOW asks for a summary chart of the partners
who submitted on time versus not, by month, beside item 18's partner-level list. The rule: a Monthly
Report (`DHIS2__c`) is on time when its `Monthly_Report_submission_date__c` is on or before the 15th
of the month after its `Period__c`. The build (rulings on the ticket): a text formula field
`DHIS2__c.Submitted_On_Time__c` ("On time" or "Late"); a new report "On Time by Month"
(`On_Time_by_Month`, in "GLOW Monthly Reports") grouped by `Period__c` by month, then by the field,
shown on D5 ("Reporting", `01ZRP000006oxSr2AI`) as a stacked column; item 18 ("Reports completed on
time", `00ORP0000054DyH2AU`) keeps its Id and its Partner and Month grouping and gains the field as a
column. The docs say so: a dated DECISIONS section at the end records the rule as Ryan's (GLOW's)
decision of 2026-11-02; the RUNBOOK's `### GLOW Club Reporting` names the field, the report with its
Id, the chart, item 18's column and the rollback; the plan `docs/plans/2026-11-20-sf-on-time.md` has
Rollout, Rollback and Result and is in the plans index. How a blank submission date reads is the
coder's call, recorded in the DECISIONS section or the RUNBOOK.

The wording is free: each fact is looked for as key tokens in one sentence or one unit (a paragraph,
list item or table row), not as a sentence. The new report's Id is not known before the deploy, so
any report Id (`00O…`) next to its name passes, except one of the reports that already exist. No org
figure is pinned, and no person is named.
"""
import csv
import os
import re
import sys
import unittest

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import REPO, flat, md_part, read, sentences

sys.path.insert(0, os.path.join(REPO, "scripts"))
import docs_index

RUNBOOK = os.path.join(REPO, "docs", "RUNBOOK.md")
DECISIONS = os.path.join(REPO, "docs", "DECISIONS.md")
PLAN = os.path.join(REPO, "docs", "plans", "2026-11-20-sf-on-time.md")
INDEX = os.path.join(REPO, "docs", "plans", "README.md")
KEEP_LIST = os.path.join(REPO, "glow", "sf_keep_list.csv")


class OnTimeDocs(unittest.TestCase):
    longMessage = False         # the messages say what to fix

    MONTHLY = "## Monthly Report dashboards in Salesforce"
    PART = "### GLOW Club Reporting"
    FIELD = "Submitted_On_Time__c"
    SUBMITTED = "Monthly_Report_submission_date__c"
    PERIOD = "Period__c"
    REPORT = "On Time by Month"
    DEV_NAME = "On_Time_by_Month"
    FOLDER = "GLOW Monthly Reports"
    D5_ID = "01ZRP000006oxSr2AI"
    ITEM_18_ID = "00ORP0000054DyH2AU"
    ITEM_18_LABEL = "Reports completed on time"
    APPROVAL_OVERVIEW_ID = "00ORP000009p0qb2AA"     # #200's "Approval Status by Month": not the new report
    TICKET = re.compile(r"(?<![\w#])#119\b")
    REPORT_ID = re.compile(r"\b00O[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\b")
    ON_TIME = re.compile(r"(?i)\bon[\s-]time\b")
    # the deadline: the 15th of the month after the period, inclusive
    FIFTEENTH = re.compile(r"(?i)\b15(th)?\b|\bfifteenth\b")
    MONTH_AFTER = re.compile(r"(?i)\b(the\s+)?(month\s+after|following\s+month|next\s+month|month\s+that\s+follows)\b")
    INCLUSIVE = re.compile(r"(?i)\bon\s+or\s+before\b|\bno\s+later\s+than\b|<=|≤|\bat\s+the\s+latest\b")
    STACKED = re.compile(r"(?i)\bstacked\s+(vertical\s+)?(column|bar)s?\b|\bColumnStacked\b|\bcolumn\s+chart,?\s+stacked\b")
    BY_MONTH = re.compile(r"(?i)\bby\s+(calendar\s+)?month\b|\bmonth\s+by\s+month\b|\b(each|per)\s+month\b")
    NEGATION = re.compile(r"(?i)\b(not|never|no|no\s+longer|without|neither|nor|isn['’]t|aren['’]t|wasn['’]t)\b")
    GO = re.compile(r"Ryan['’]s go\b")
    EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}")
    ROLLBACK = re.compile(r"(?i)\brollback\b|\broll(s|ed)?\s+back\b")
    # a blank submission date ("a blank `Monthly_Report_submission_date__c`", "no submission date", "when it is empty")
    BLANK = re.compile(r"(?i)\b(blank|empty|null|missing|unset)\b|\bno\s+(submission\s+)?date\b|"
                       r"\bwithout\s+a\s+(submission\s+)?date\b|\bnot\s+(yet\s+)?(submitted|filed)\b")
    # what it reads: one of the field's values, or that the field is blank too
    READS = re.compile(r"(?i)\blate\b|\bon\s+time\b|\b(blank|empty)\s+(too|as\s+well|also)\b|\bneither\b|"
                       r"\bno\s+value\b|\bempty\s+(text|string)\b")

    # --- helpers ---------------------------------------------------------------------------------------------

    def stated(self, s, rx):
        """`rx` said in sentence `s`, with no negation in the 25 characters before a match."""
        return any(not self.NEGATION.search(s[max(0, m.start() - 25):m.start()]) for m in rx.finditer(s))

    @staticmethod
    def blocks(raw):
        """`raw` cut into its paragraphs, list items and table rows, each flattened."""
        parts = re.split(r"\n\s*\n|\n(?=[ \t]*(?:[-*+]|\d+[.)])\s)|\n(?=[ \t]*\|)", raw)
        return [flat(p) for p in parts if p.strip()]

    def part(self):
        """The RUNBOOK's `### GLOW Club Reporting` under the Monthly Report section, to the next heading."""
        section = md_part(RUNBOOK, self.MONTHLY)
        m = re.search(r"^" + re.escape(self.PART) + r"(?!\w).*$", section, re.M)
        self.assertTrue(m, f"RUNBOOK section {self.MONTHLY[3:]!r}: no `{self.PART}` part under it")
        rest = section[m.start():]
        nxt = re.search(r"\n#{1,3} ", rest)
        return rest[:nxt.start()] if nxt else rest

    def keep(self):
        with open(KEEP_LIST, encoding="utf-8", newline="") as f:
            return {r["item"]: r for r in csv.DictReader(f)}

    def decision(self):
        """(heading, body) of the dated DECISIONS section whose heading names on-time Monthly Reports; it comes
        after every section that was already there before this ticket (dated before 2026-11-20)."""
        text = read(DECISIONS)
        heads = list(re.finditer(r"^#{1,3} .*$", text, re.M))
        found = [i for i, h in enumerate(heads)
                 if re.match(r"#{2,3} \d{4}-\d\d-\d\d\b", h.group(0)) and self.ON_TIME.search(h.group(0))
                 and re.search(r"(?i)\bmonthly\s+reports?\b", h.group(0))]
        self.assertEqual(len(found), 1,
                         "docs/DECISIONS.md: one dated section (`### YYYY-MM-DD — …`) whose heading names on-time "
                         f"Monthly Reports, for ticket #119 (found {[heads[i].group(0) for i in found]})")
        i = found[0]
        body = text[heads[i].start():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        older_after = [h.group(0) for h in heads[i + 1:]
                       if (d := re.match(r"#{2,3} (\d{4}-\d\d-\d\d)\b", h.group(0))) and d.group(1) < "2026-11-20"]
        self.assertFalse(older_after, "docs/DECISIONS.md: the on-time section goes at the end, after every section "
                                      f"already there; these follow it: {older_after}")
        return heads[i].group(0), body

    def plan_part(self, heading):
        text = read(PLAN)
        m = re.search(r"^" + re.escape(heading) + r"\b.*$", text, re.M)
        self.assertTrue(m, f"{os.path.relpath(PLAN, REPO)}: no `{heading}` section")
        rest = text[m.end():]
        nxt = re.search(r"^#{1,2} ", rest, re.M)
        return rest[:nxt.start()] if nxt else rest

    def rule_sentences(self, text):
        """The sentences of `text` that state the rule: both fields, the 15th, the month after, on or before."""
        return [s for s in sentences(text, ".;")
                if self.SUBMITTED in s and self.PERIOD in s and self.FIFTEENTH.search(s)
                and self.MONTH_AFTER.search(s) and self.stated(s, self.INCLUSIVE)]

    # --- DECISIONS --------------------------------------------------------------------------------------------

    def test_the_decision_states_the_on_time_rule(self):
        heading, body = self.decision()
        where = f"docs/DECISIONS.md {heading!r}"
        self.assertTrue(self.rule_sentences(body),
                        f"{where}: state the rule in one sentence: a Monthly Report is on time when its "
                        f"`{self.SUBMITTED}` is on or before the 15th of the month after its `{self.PERIOD}`")
        self.assertIn(self.FIELD, body, f"{where}: name the field that computes it, `DHIS2__c.{self.FIELD}`")
        self.assertRegex(body, r"\bOn time\b", f"{where}: name the field's value \"On time\"")
        self.assertRegex(body, r"\bLate\b", f"{where}: name the field's value \"Late\"")
        self.assertTrue([s for s in sentences(body, ".;") if "2026-11-02" in s and re.search(r"\bRyan\b", s)
                         and re.search(r"\bGLOW\b", s)],
                        f"{where}: say, in one sentence, the rule is Ryan's and GLOW's decision of 2026-11-02")
        self.assertRegex(body, self.TICKET, f"{where}: name ticket #119")

    def test_a_blank_submission_date_is_ruled(self):
        _, body = self.decision()
        text = body + "\n\n" + self.part()
        said = [s for s in sentences(text, ".;")
                if (self.SUBMITTED in s or re.search(r"(?i)\bsubmission\s+date\b", s) or self.FIELD in s)
                and self.BLANK.search(s) and self.READS.search(s)]
        self.assertTrue(said, "docs/DECISIONS.md (the on-time section) or RUNBOOK `### GLOW Club Reporting`: say, in "
                              f"one sentence, what `{self.FIELD}` reads for a Monthly Report with a blank "
                              f"`{self.SUBMITTED}` (\"Late\", \"On time\" or blank)")

    # --- the RUNBOOK ------------------------------------------------------------------------------------------

    def test_the_runbook_describes_the_on_time_field(self):
        where = f"RUNBOOK {self.PART[4:]!r}"
        part = self.part()
        self.assertRegex(part, self.TICKET, f"{where}: name ticket #119")
        units = [b for b in self.blocks(part) if self.FIELD in b]
        self.assertTrue(units, f"{where}: name the formula field `DHIS2__c.{self.FIELD}` (ticket #119)")
        lacks = {}
        for b in units:
            miss = []
            if not re.search(r"(?i)\bformula\b", b):
                miss.append("a formula")
            if not (re.search(r"\bOn time\b", b) and re.search(r"\bLate\b", b)):
                miss.append("its values \"On time\" and \"Late\"")
            if not self.rule_sentences(b):
                miss.append(f"the rule (`{self.SUBMITTED}` on or before the 15th of the month after `{self.PERIOD}`)")
            lacks[b[:80]] = miss
        self.assertTrue([k for k, v in lacks.items() if not v],
                        f"{where}: describe `{self.FIELD}` in one paragraph, list item or row: a text formula giving "
                        f"\"On time\" or \"Late\", by the rule. Lacking: {lacks}")
        # the old claim that nothing computes it is gone, or said as history
        for s in sentences(part, ".;"):
            if re.search(r"(?i)\bno\s+report\s+computes\b", s) or (self.TICKET.search(s) and
                                                                    re.search(r"(?i)\bon\s+hold\b", s)):
                self.assertRegex(s, r"(?i)\b(until|was|were|before|lifted|since|formerly)\b",
                                 f"{where}: since #119 a field computes \"on time\"; say \"no report computes it\" / "
                                 f"\"#119, on hold\" only as history: {s[:160]!r}")

    def test_the_runbook_describes_the_on_time_chart(self):
        where = f"RUNBOOK {self.PART[4:]!r}"
        part = self.part()
        known = {r["id"] for r in self.keep().values()} | {self.APPROVAL_OVERVIEW_ID}
        units = [b for b in self.blocks(part) if self.REPORT in b]
        self.assertTrue(units, f"{where}: name the new report {self.REPORT!r} (ticket #119)")
        lacks = {}
        for b in units:
            miss = []
            ids = [m.group(0) for n in re.finditer(re.escape(self.REPORT), b)
                   for m in self.REPORT_ID.finditer(b[n.end():n.end() + 60])]
            if not [i for i in ids if i not in known]:
                miss.append(f"its own report Id (`00O…`) right after its name, not one of {sorted(known)}")
            for token in (self.DEV_NAME, self.FOLDER, self.FIELD, self.PERIOD):
                if token not in b:
                    miss.append(token)
            ss = sentences(b, ".;")
            if not [s for s in ss if self.stated(s, self.STACKED)]:
                miss.append("a stacked column")
            if not (re.search(r"\bD5\b", b) or self.D5_ID in b):
                miss.append(f"on D5 ({self.D5_ID})")
            if not [s for s in ss if self.stated(s, self.BY_MONTH)]:
                miss.append("by month")
            if not [s for s in ss if self.ON_TIME.search(s) and re.search(r"(?i)\blate\b|\bnot\s+on\s+time\b", s)]:
                miss.append("on time versus late, in one sentence")
            lacks[b[:80]] = miss
        self.assertTrue([k for k, v in lacks.items() if not v],
                        f"{where}: describe the chart in one paragraph, list item or row naming {self.REPORT!r}: its "
                        f"Id, `{self.DEV_NAME}` in {self.FOLDER!r}, grouped by `{self.PERIOD}` by month then "
                        f"`{self.FIELD}`, shown on D5 as a stacked column, on time versus late. Lacking: {lacks}")

    def test_item_18_keeps_its_id_and_shows_on_time_by_partner_and_month(self):
        rows = self.keep()
        self.assertIn("18", rows, "glow/sf_keep_list.csv: no row 18")
        r = rows["18"]
        self.assertEqual((r["kind"], r["id"]), ("report", self.ITEM_18_ID),
                         f"glow/sf_keep_list.csv item 18: the report keeps its Id {self.ITEM_18_ID} (#119 adds a "
                         f"column, it does not replace the report), not {r['id']!r}")
        self.assertEqual((r["label_today"], r["label_target"]), (self.ITEM_18_LABEL, self.ITEM_18_LABEL),
                         f"glow/sf_keep_list.csv item 18: the label stays {self.ITEM_18_LABEL!r}")
        where = f"RUNBOOK {self.PART[4:]!r}"
        units = [b for b in self.blocks(self.part())
                 if (self.ITEM_18_ID in b or re.search(r"(?i)\bitem\s+18\b", b)) and self.FIELD in b]
        self.assertTrue([b for b in units if re.search(r"(?i)\bcolumns?\b", b)
                         and re.search(r"\bPartner\b|\bAccount__c\b", b) and re.search(r"\bMonth\b|\bPeriod__c\b", b)],
                        f"{where}: say, in the paragraph or list item naming item 18 ({self.ITEM_18_ID}), it has "
                        f"`{self.FIELD}` as a column and stays by Partner and Month, so it shows on time versus late "
                        "per partner and month")

    def test_the_runbook_gives_the_rollback(self):
        where = f"RUNBOOK {self.PART[4:]!r}"
        part = self.part()
        m = re.search(r"(?i)\brollback\b[^\n]{0,80}?#119\b|#119\b[^\n]{0,80}?\brollback\b", part)
        self.assertTrue(m, f"{where}: give #119's rollback (\"Rollback of #119\")")
        rest = part[m.start():]
        nxt = re.search(r"(?im)^\s*rollback\s+of\s+#(?!119\b)\d+", rest[1:])
        raw = rest[:nxt.start() + 1] if nxt else rest
        units = self.blocks(raw)
        self.assertTrue([b for b in units if self.REPORT in b and "Decommissioned" in b],
                        f"{where}, #119's rollback: the report {self.REPORT!r} goes to Decommissioned (archived, never "
                        "deleted), in one paragraph or list item")
        self.assertTrue([b for b in units if (re.search(r"\bD5\b", b) or self.D5_ID in b)
                         and re.search(r"(?i)\b(re-?)?deploy\w*\b", b)],
                        f"{where}, #119's rollback: say how D5 is redeployed without the chart")
        self.assertTrue([b for b in units if self.FIELD in b or (self.ITEM_18_ID in b or
                                                                 re.search(r"(?i)\bitem\s+18\b", b))],
                        f"{where}, #119's rollback: say what happens to item 18's column and the field `{self.FIELD}`")
        for s in sentences(raw, ".;"):
            for d in re.finditer(r"(?i)\bdelet\w*\b", s):
                self.assertRegex(s[:d.start()], r"(?i)\b(never|not|no|nothing)\b",
                                 f"{where}, #119's rollback: nothing is deleted (archive rule): {s[:160]!r}")

    # --- the plan ---------------------------------------------------------------------------------------------

    def test_the_plan_has_rollout_rollback_and_result(self):
        name = os.path.relpath(PLAN, REPO)
        self.assertTrue(os.path.isfile(PLAN), f"{name}: no plan for ticket #119 (Rollout, Rollback, Result)")
        text = read(PLAN)
        keys, _ = docs_index.frontmatter(text)
        for k in ("title", "author", "status", "created", "intent"):
            self.assertTrue(keys.get(k), f"{name}: frontmatter `{k}:`")
        _, problem = docs_index.status_of(keys["status"])
        self.assertIsNone(problem, f"{name}: {problem}")
        self.assertRegex(keys["created"].partition("#")[0].strip(), r"^\d{4}-\d\d-\d\d$",
                         f"{name}: `created:` is YYYY-MM-DD")
        self.assertRegex(text.split("\n## ", 1)[0], self.TICKET,
                         f"{name}: name ticket #119 in the frontmatter, the title or the opening paragraph")
        self.assertNotRegex(text, self.EMAIL, f"{name}: ids and names of reports only, no address")
        self.assertRegex(text, r"(?m)^## Result\b", f"{name}: no `## Result` section")

        rollout = self.plan_part("## Rollout")
        where = f"{name}: `## Rollout`"
        for token in (self.FIELD, self.REPORT, self.D5_ID, self.ITEM_18_ID):
            self.assertIn(token, rollout, f"{where}: name {token}")
        self.assertRegex(rollout, r"(?i)\bfresh\s+retriev\w*|\bretriev\w*\b", f"{where}: start from a fresh retrieve "
                                                                               "of D5 and item 18")
        self.assertRegex(rollout, r"(?i)\bcheck-?only\b", f"{where}: a check-only deploy before the deploy")
        self.assertRegex(rollout, self.GO, f"{where}: the deploy waits for Ryan's go")

        rollback = self.plan_part("## Rollback")
        where = f"{name}: `## Rollback`"
        self.assertIn(self.REPORT, rollback, f"{where}: say what becomes of the new report {self.REPORT!r}")
        self.assertTrue(re.search(r"\bD5\b", rollback) or self.D5_ID in rollback, f"{where}: say how D5 comes back")
        self.assertIn("Decommissioned", rollback, f"{where}: the new report goes to Decommissioned, never deleted")

    def test_the_plan_is_in_the_plans_index(self):
        base = os.path.basename(PLAN)
        self.assertIn(f"]({base})", read(INDEX),
                      f"docs/plans/README.md: list {base} (`make docs-index`)")


if __name__ == "__main__":
    unittest.main()
