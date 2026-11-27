#!/usr/bin/env python3
"""
UsMonthlyTotalsDocs (ticket #267, epic #68; Ryan, 2026-11-24/25): the monthly dashboards line up with the interactive
dashboard. Six Monthly Report (`DHIS2__c`) totals reports on D1, D3 and D4 count the six U.S partners' Monthly Reports
with `Period__c` before 2026-11-01 again: in each, the locked #209 item `DHIS2__c$Account__c notEqual <the six>` is
ORed through `booleanFilter` with a new locked item `DHIS2__c$Period__c lessThan 11/1/2026` (Ryan's "go with sums",
2026-11-25: the three D1 attendance reports and items 10, 13 and 14). Every other Monthly report (who reported, what
is approved, on time, item 11, item 19), the three not-submitted lists and the Jotform Attendance dashboard's Partner
filter keep the full #209 exclusion. Deployed 2026-11-25 02:36 UTC (deploy 0AfRP000002l1XN0AY, check-only
0AfRP000002l1Nh0AI), read back, the reports equal to SOQL.

Salesforce metadata is not in git, so the change is the docs': the RUNBOOK's "Monthly Report dashboards in Salesforce"
names the six and the filter shape (with its SOQL term), says what keeps the exclusion, and no longer says the U.S
leaves the totals without #267's exception; its `Rollback of #267` and the plan's Rollback restore by a deploy; the
plan `docs/plans/<date>-sf-us-monthly<…>.md` (`status: done`) runs its Rollout in order (Ryan's go before the copies
and the deploy) and its Result carries the ids, the six copies, each report's filter logic and figures, and the
read-back; a dated DECISIONS entry amends 2026-11-05 (#209), which gets a dated bullet pointing at it.

The ids and figures are the rollout's record (the ticket, 2026-11-25), not read from the docs under test; the after
figures are derived here as before + the U.S amounts. UsPartnersOffReportsDocs (#209, sf_monthly_dashboards_test)
asks its "every Monthly report filters notEqual the six" rule to carry #267's exception. Counts, ids and names of
reports and partners only.
"""
import glob
import os
import re
import sys
import unittest

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import REPO, flat, md_part, read, sentences
import sf_monthly_dashboards_test as dash  # the module, not its classes: its TestCases run once, in their own module


class UsMonthlyTotalsDocs(unittest.TestCase):
    """Ticket #267: the six U.S partners' Monthly Reports through October 2026 count again on the six totals reports;
    the docs side of the deploy of 2026-11-25."""

    longMessage = False         # the messages say what to fix
    RUNBOOK = dash.DecommissionedFoldersDocs.RUNBOOK
    DECISIONS = dash.DecommissionedFoldersDocs.DECISIONS
    MONTHLY = dash.DecommissionedFoldersDocs.MONTHLY
    ATTENDANCE = dash.UsPartnersOffReportsDocs.ATTENDANCE
    # the plan is named after its work folder `data/sf_us_monthly_2026-11-25/`, as #209's is after its own
    PLANS = os.path.join(REPO, "docs", "plans", "*-sf-us-monthly*.md")
    TICKET = re.compile(r"(?<![\w#])#267\b")
    T209 = re.compile(r"(?<![\w#])#209\b")
    DAY = "2026-11-25"
    FOLDER = "data/sf_us_monthly_2026-11-25/"

    # --- the rollout's record (the ticket, 2026-11-25), not read from the docs under test ---------------------
    CHECK_ONLY, DEPLOY_ID = "0AfRP000002l1Nh0AI", "0AfRP000002l1XN0AY"
    # the six totals reports: their labels (item 10 also by its label before #198), Id, item on glow/sf_keep_list.csv
    # (None: D1's overview), the `booleanFilter` deployed, the copy in Decommissioned, and each figure as (before #267,
    # the U.S amount): the after figure is their sum
    TOTALS = {
        "Overall Attendance by Month": dict(
            labels=("Overall Attendance by Month",), id="00ORP000009p0FJ2AY", item=None,
            logic="1 AND 2 AND (3 OR 5) AND 4", copy="00ORP000009ucdJ2AQ", figures=((49337, 639),)),
        "Participation by Month and Partner": dict(
            labels=("Participation by Month and Partner",), id="00ORP000005rSbB2AU", item="3",
            logic="1 AND 2 AND (3 OR 5) AND 4", copy="00ORP000009ucjl2AA", figures=((49337, 639),)),
        "GLOW Club Each Week": dict(          # its Monthly_Total, or its rows 374 -> 410
            labels=("GLOW Club Each Week",), id="00ORP000005ufOz2AI", item="4",
            logic="1 AND 2 AND 3 AND 4 AND (5 OR 7) AND 6", copy="00ORP000009uclN2AQ",
            figures=((374, 36), (49337, 639))),
        "Club Observations by Month and Partner": dict(
            labels=("Club Observations by Month and Partner", "Total Number of Club Observations M&P"),
            id="00ORP000004RJZD2A4", item="10",
            logic="1 AND 2 AND 3 AND (4 OR 6) AND 5", copy="00ORP000009ucmz2AA", figures=((908, 12),)),
        "Number of mentors trained about module": dict(
            labels=("Number of mentors trained about module",), id="00ORP000004RJZE2A4", item="13",
            logic="1 AND 2 AND (3 OR 5) AND 4", copy="00ORP000009ucob2AA", figures=((1282, 1),)),
        "Number of training sessions led": dict(
            labels=("Number of training sessions led",), id="00ORP000004RJZ82AO", item="14",
            logic="1 AND 2 AND (3 OR 5) AND 4", copy="00ORP000009ucqD2AQ", figures=((500, 1),)),
    }
    # the Monthly reports that keep the full #209 exclusion (the classification of 2026-11-25), by Id and label; and
    # the keep list's items among them, by number
    KEPT = {"00ORP000009p0qb2AA": "Approval Status by Month", "00ORP000006XXEf2AO": "Monthly Report Approval Status",
            "00ORP000004RJYv2AO": "Collection of Attendance Roster by Month",
            "00ORP000005uf412AA": "Clubs Observed at Least Once by Month",
            "00ORP000005rY3t2AE": "Club Implementation by Month and Partner",
            "00ORP000005uehR2AQ": "Modules Adapted by Month and Partner",
            "00ORP000009kUNh2AM": "Modules Implemented by Month and Partner",
            "00ORP000004RJZ62AO": "Leading training sessions with mentors",
            "00ORP000005uekf2AA": "Local and Regional Summits By Month 2",
            "00ORP000004RJZ72AO": "Meeting with mentors to discuss program",
            "00ORP000009p0Qb2AI": "Modules Adapted Responses", "00ORP000009taVV2AY": "On Time by Month",
            "00ORP000009kXev2AE": "Partners that recruited new mentors", "00ORP0000054DyH2AU": "Reports completed on time",
            "00ORP000004RJZC2A4": "GC Observation Forms by Month & Partner", "00ORP000009p0Qc2AI": "Summit Types Completed",
            "00ORP000005p2L32AI": "GLOW of the Month Stories Report"}
    KEPT_ITEMS = ("1", "5", "6", "7", "8", "9", "11", "12", "15", "16", "17", "18", "19")
    # Overall Attendance by Month, January to October 2026: before #267 (the six left out) and the U.S amounts
    BEFORE_BY_MONTH = (3277, 4889, 5562, 4978, 5336, 5235, 4856, 4821, 5385, 4998)
    US_BY_MONTH = (132, 130, 111, 90, 97, 40, 0, 5, 5, 29)

    # --- reading the docs ------------------------------------------------------------------------------------
    CUTOFF_ANY = re.compile(r"\b2026-11-01\b|(?<![\d/])11/1/2026\b|(?i:\bthrough\s+(the\s+end\s+of\s+)?October\s+2026\b|"
                            r"\bbefore\s+November\s+2026\b|\bOctober\s+2026\s+and\s+(earlier|before)\b)")
    COUNTS = re.compile(r"(?i)\bcount(s|ed|ing)?\b|\binclud\w*|\bshow(s|n|ing)?\b|\bagain\b|\bback\s+(in|on|into)\b")
    KEEP = re.compile(r"(?i)\b(keep|keeps|kept|stay|stays|stayed|remain|remains|still|unchanged|untouched)\b")
    EXCLUSION = re.compile(r"(?<![\w#])#209\b|\bnotEqual\b|(?i:\bexclu\w*|\bnot\s+equal\b|\bleav\w*\s+out\b|\bleft\s+out\b|"
                           r"\bwithout\s+the\s+(six|U_?S)\b)")
    HIST = re.compile(r"(?i)\b(until|was|were|formerly|previously|no\s+longer|used\s+to)\b")
    ITEM_REF = re.compile(r"(?i)\bitems?\s+((?:\d+\s*(?:,|and|&|-|–|to)\s*)*\d+)\b")
    BOOLEAN = re.compile(r"\bbooleanFilter\b|(?i:\bfilter\s+logic\b)")
    ACCOUNT_ITEM = re.compile(r"DHIS2__c\$Account__c")
    PERIOD_ITEM = re.compile(r"DHIS2__c[$_]Period__c")
    # the new criteria item as deployed: `DHIS2__c$Period__c lessThan 11/1/2026`
    PERIOD_LESS = re.compile(r"DHIS2__c[$_]Period__c`?\s*`?(lessThan|LESS_THAN|less\s+than|<)`?\s*`?"
                             r"(11/1/2026|2026-11-01)\b")
    OR_WORD = re.compile(r"\bOR(ed|s|ing)?\b")          # the filter logic's operator, upper case
    LOCKED = re.compile(r"(?i)\blocked\b")
    CODE = re.compile(r"(`+)(.+?)\1")
    GO = dash.UsPartnersOffReportsDocs.GO
    CHECK = dash.UsPartnersOffReportsDocs.CHECK
    EMAIL = dash.UsPartnersOffReportsDocs.EMAIL
    # the rollback's sources: #267's own folder and the copy tool's ledger; another data/ folder (#209's
    # `data/sf_us_partners_<date>/` among them), an older build or another ticket's folder is none
    OLD_SOURCE = re.compile(r"(?i)\bdata/sf_(?!us_monthly_(2026-11-25|<date>)(?![\w-])|report_folders(?![\w-]))"
                            r"[\w<>-]+(/[\w<>-]+)*/?|"
                            r"\b(older|old|earlier|previous|prior|stale|another|other|original)\s+([\w-]+\s+)?"
                            r"(retrieves?|builds?|backups?|exports?|snapshots?|versions?)\b|"
                            r"#(?!267\b)\d+['’]s\s+(own\s+)?`?(data/|before/|build/|after/|retrieve|build|folder)")
    BEFORE_DIR = re.compile(r"\bdata/sf_us_monthly_2026-11-25/before/")
    AFTER_DIR = r"((?<![\w/])`?after/|\bdata/sf_us_monthly_2026-11-25/after/)"

    @classmethod
    def setUpClass(cls):
        dash.UsPartnersOffReportsDocs.setUpClass()
        cls.u = dash.UsPartnersOffReportsDocs()  # #209's helpers: US_WORD, us_ref, lists_ref, FRESH_EDITED, GUARD_HEAD
        cls.r = cls.u.r                          # #79's helpers: blocks, plan_part, sweep, stated
        cls.d = cls.u.d                          # #69's helpers: locally_denied, NEGATION, denies
        cls.t = cls.u.t                          # #78's helpers: result_units, labels, nearest, num, clauses, COPY

    @staticmethod
    def norm(text):
        return dash.DecommissionedFoldersDocs.norm(text)

    def cl(self, text):
        return sentences(self.norm(text), ".;")

    def stated(self, s, rx):
        """`rx` said in `s`: not denied in the words before it, and not said as the past ("until", "was")."""
        return any(not self.d.locally_denied(s, m) and not self.HIST.search(s[max(0, m.start() - 50):m.start()])
                   for m in rx.finditer(s))

    def us(self, s):
        return bool(self.u.US_WORD.search(s) or self.u.us_ref(s))

    def monthly(self):
        return md_part(self.RUNBOOK, self.MONTHLY)

    def chunks(self, raw):
        """`raw`'s list items, paragraphs and table rows (#79's blocks), and each run of lines between blank lines (a
        paragraph with its list or a whole table), each flattened and normed."""
        runs = [flat(p) for p in re.split(r"\n\s*\n", raw) if p.strip()]
        return [self.norm(b) for b in self.r.blocks(raw) + runs]

    def report_refs(self, text):
        """[(match, key)]: each report named in `text`: a totals report by its label, Id or `item N` (key: its label),
        a report that keeps the exclusion by its label, Id or item number (key: "kept")."""
        out = []
        for key, r in self.TOTALS.items():
            for v in r["labels"] + (r["id"][:15],):
                out += [(m, key) for m in re.finditer(r"(?<!\w)" + re.escape(v) + r"(?!\w)", text)]
        for rid, label in self.KEPT.items():
            for v in (label, rid[:15]):
                out += [(m, "kept") for m in re.finditer(r"(?<!\w)" + re.escape(v) + r"(?!\w)", text)]
        items = {r["item"]: key for key, r in self.TOTALS.items() if r["item"]}
        for m in self.ITEM_REF.finditer(text):
            nums = set(re.findall(r"\d+", m.group(1)))
            for a, b in re.findall(r"(\d+)\s*(?:-|–|to)\s*(\d+)", m.group(1)):
                nums |= {str(i) for i in range(int(a), int(b) + 1)}
            out += [(m, items[n]) for n in sorted(nums) if n in items]
            out += [(m, "kept") for n in sorted(nums) if n in self.KEPT_ITEMS][:1]
        return out

    def owners(self, unit, m, marks):
        """The reports a figure or value at match `m` of `unit` belongs to: those named between the previous mark
        (`marks`, the positions where another figure or value ends) and it; with none there, the nearest one after it."""
        lo = max([e for e in marks if e <= m.start()], default=0)
        refs = self.report_refs(unit)
        before = {k for r, k in refs if lo <= r.start() and r.end() <= m.start()}
        if before:
            return before
        after = [(r, k) for r, k in refs if r.start() >= m.end()]
        return {min(after, key=lambda rk: rk[0].start())[1]} if after else set()

    def plan_path(self):
        found = sorted(glob.glob(self.PLANS))
        self.assertEqual(len(found), 1, "docs/plans/: one plan `YYYY-MM-DD-sf-us-monthly<…>.md` for ticket #267, named "
                                        "after its work folder `data/sf_us_monthly_2026-11-25/` (found "
                                        f"{[os.path.basename(p) for p in found]})")
        self.assertRegex(os.path.basename(found[0]), r"^\d{4}-\d\d-\d\d-sf-us-monthly[a-z0-9-]*\.md$",
                         "docs/plans/: the plan is named `YYYY-MM-DD-sf-us-monthly<-slug>.md` (docs_index's shape)")
        return found[0]

    # --- the RUNBOOK -----------------------------------------------------------------------------------------

    def test_the_runbook_names_the_six_totals_reports_and_their_filter(self):
        """The six totals reports, each by its label, Id or item number, count the six U.S partners' Monthly Reports
        with `Period__c` before 2026-11-01, in one list item or paragraph; no report that keeps the exclusion is said
        to count them; the filter shape (the #209 item ORed with a locked `DHIS2__c$Period__c lessThan 11/1/2026`
        through `booleanFilter`) and the SOQL term that equals the six (`NOT IN (<the six>) OR Period__c <
        2026-11-01`); the deploy id and the plan linked."""
        where = f"RUNBOOK section {self.MONTHLY[3:]!r}"
        section = self.monthly()
        blocks = self.chunks(section)
        named = [b for b in blocks if {k for _, k in self.report_refs(b)} >= set(self.TOTALS) and self.us(b)
                 and self.CUTOFF_ANY.search(b) and self.stated(b, self.COUNTS)]
        self.assertTrue(named, f"{where}: name the six totals reports that count the six U.S partners' Monthly Reports "
                               "with `Period__c` before 2026-11-01 since #267 (" + "; ".join(
                                   f"{k} `{r['id']}`" + (f", item {r['item']}" if r["item"] else "")
                                   for k, r in self.TOTALS.items()) + "), each by its label, Id or item number, in one "
                               "list item, paragraph, list or table with the U.S and the cutoff (not negated, not "
                               "history)")
        for s in self.cl(section):
            if not (self.CUTOFF_ANY.search(s) and self.us(s)) or self.KEEP.search(s):
                continue
            kept = [m.group(0) for m, k in self.report_refs(s) if k == "kept" and not self.d.locally_denied(s, m)]
            self.assertEqual(kept, [], f"{where}: only the six totals reports count the U.S Monthly Reports before "
                                       f"2026-11-01; {kept[:2]} keep the full #209 exclusion (say so with \"keep\" or "
                                       f"\"stay\"): {s[:200]!r}")

        shape = [b for b in blocks if self.BOOLEAN.search(b) and self.ACCOUNT_ITEM.search(b) and self.PERIOD_LESS.search(b)
                 and self.stated(b, self.OR_WORD) and self.LOCKED.search(b)]
        self.assertTrue(shape, f"{where}: give the six reports' filter: the locked #209 item `DHIS2__c$Account__c "
                               "notEqual` the six ORed with a new locked criteria item `DHIS2__c$Period__c lessThan "
                               "11/1/2026` through `booleanFilter` (filter logic), in one list item or paragraph")
        spans = [c for c in (m.group(2) for m in self.CODE.finditer(flat(section)))
                 if re.search(r"\bNOT\s+IN\b[^`]*\bOR\s+Period__c\s*<\s*2026-11-01\b|"
                              r"\bPeriod__c\s*<\s*2026-11-01\s+OR\b[^`]*\bNOT\s+IN\b", c)]
        self.assertTrue(spans, f"{where}: give the SOQL term the six totals reports equal since #267, as code: `AND "
                               "(Account__r.Name NOT IN (<the six>) OR Period__c < 2026-11-01)`")
        self.assertIn(self.DEPLOY_ID, section, f"{where}: record #267's deploy `{self.DEPLOY_ID}`")
        plan = os.path.basename(self.plan_path())
        self.assertIn(f"plans/{plan}", section, f"{where}: link #267's plan (`plans/{plan}`)")

    def test_the_runbook_says_the_rest_keep_the_full_exclusion(self):
        """Every other Monthly report, item 19 among them, keeps the full #209 exclusion; the three not-submitted lists
        and the Jotform Attendance dashboard's Partner filter are unchanged; and no sentence of the section says the
        U.S Monthly Reports leave the dashboards, their totals or components without #267's exception (as the #209
        text "the U.S Monthly Reports of January-October 2026 leave them retroactively" does)."""
        where = f"RUNBOOK section {self.MONTHLY[3:]!r}"
        section = self.monthly()
        cl_m = self.cl(section)
        other = re.compile(r"(?i)\b(every|each|all)\s+other\b|\bthe\s+(other|rest|remaining)\b|\b(other|remaining)\s+"
                           r"(\d+|sixteen|seventeen)\b|\b\d+\s+other\b")
        self.assertTrue([s for s in cl_m if other.search(s) and re.search(r"(?i)\breports?\b", s)
                         and self.u.ITEM_19.search(s) and self.stated(s, self.KEEP) and self.EXCLUSION.search(s)],
                        f"{where}: say every other Monthly report, item 19 (the stories table) among them, keeps the full "
                        "#209 exclusion, in one sentence (\"the other Monthly reports\", \"the rest\"; \"keep\" or "
                        "\"stay\"; #209 or the exclusion named)")
        both = cl_m + self.cl(md_part(self.RUNBOOK, self.ATTENDANCE))
        lists = re.compile(r"(?i)\bnot[- ]submitt\w*\s+(\w+\s+)?lists\b")
        self.assertTrue([s for s in both if (self.u.lists_ref(s) or lists.search(s))
                         and (self.u.PARTNER_FILTER.search(s) or self.u.JOTFORM_DASH.search(s))
                         and (self.stated(s, self.KEEP) or self.stated(s, self.u.UNCHANGED))
                         and (self.TICKET.search(s) or self.us(s))],
                        "RUNBOOK: say the three not-submitted lists and the Jotform Attendance dashboard's Partner filter "
                        "are unchanged by #267 and still leave out the U.S (one sentence naming the lists, the Partner "
                        "filter and #267 or the U.S)")
        leave = re.compile(r"(?i)\bleav(e|es|ing)\b|\bleft\s+out\b|\bout\s+of\b|\bexclud\w*|\bdrop(s|ped)?\s+out\b|"
                           r"\bwithout\s+the\s+(six|U_?S)\b")
        scope = re.compile(r"(?i)\bretroactiv\w*|\bJanuary\b|\bD1\s*(?:-|–|to|through)\s*D5\b|\bdashboards?\b|"
                           r"\bcomponents?\b|\bevery\b|\ball\b|\btotals?\b")
        qualified = re.compile(r"(?<![\w#])#267\b|2026-11-01|11/1/2026|Period__c|(?i:\bNovember\b|\bthrough\s+October\b|"
                               r"\b(other|rest|remaining|kept)\b|\bkeeps?\b|\bitem\s+19\b|\bstories\b|\bapprov\w*|"
                               r"\bon[- ]time\b|\bwho\s+reported\b|\bnot[- ]submitt\w*|\blists?\b|\bPartner\s+filter\b)")
        for s in cl_m:
            p = dash.GlowReviewReportingDocs.prose(s)
            if self.us(p) and scope.search(p) and self.stated(p, leave) and not qualified.search(p):
                self.fail(f"{where}: since #267 the six totals reports count the U.S Monthly Reports before 2026-11-01, so "
                          "the U.S does not leave every dashboard, total or component: say which reports (#267, the "
                          f"cutoff, or the reports that keep the exclusion), or say it as history: {s[:200]!r}")

    def rollback_block(self, section, where):
        """The section's rollback of #267: a paragraph or list item starting `Rollback of #267`, with its list or
        continuation lines, to the next heading, item of its level or paragraph (#209's reading)."""
        lines = section.split("\n")
        start = next((i for i, x in enumerate(lines)
                      if re.match(r"\s*(?:[-*+]\s+)?(?:\*\*)?Rollback of #267\b", x)), None)
        self.assertIsNotNone(start, f"{where}: no rollback of #267 (a paragraph or list item starting `Rollback of #267`)")
        head = lines[start]
        indent = len(head) - len(head.lstrip())
        item = bool(re.match(r"\s*[-*+]\s", head))
        out, blank = [head], False
        for x in lines[start + 1:]:
            st, xi = x.strip(), len(x) - len(x.lstrip())
            if re.match(r"#{1,6}\s", x) or (item and st and xi <= indent) or \
                    (not item and st and blank and xi == 0 and not re.match(r"([-*+]|\d+[.)])\s", st)):
                break
            blank = not st
            out.append(x)
        return "\n".join(out)

    def assertRollbackOf267(self, raw, where):
        """VPN off, after a check-only, on Ryan's go: the six reports restored by a deploy from a fresh retrieve with
        the `booleanFilter` and the Period item removed, or from #267's own `data/sf_us_monthly_2026-11-25/before/`
        only while a fresh retrieve equals `after/`, both in one list item or paragraph; the Decommissioned copies the
        record, never the restore; never an older build or retrieve, nor another change's folder; nothing deleted."""
        cl = sentences(self.norm(raw), ".;")
        units = [self.norm(u) for u in self.r.blocks(raw)]
        self.assertTrue([u for u in units if any(self.r.stated(s, self.u.DEPLOY) for s in sentences(u, ".;"))
                         and self.u.FRESH_EDITED.search(u) and self.BOOLEAN.search(u)
                         and (self.PERIOD_ITEM.search(u) or re.search(r"(?i)\bPeriod\b", u))
                         and self.BEFORE_DIR.search(u) and re.search(self.u.GUARD_HEAD + self.AFTER_DIR, u)],
                        f"{where}: say the six reports are restored by a deploy from a fresh retrieve with the "
                        "`booleanFilter` and the Period item removed, or from `data/sf_us_monthly_2026-11-25/before/` "
                        "only while a fresh retrieve equals `after/`, both in one list item or paragraph")
        self.assertRegex(raw, self.CHECK, f"{where}: the rollback deploys after a check-only")
        self.assertTrue([s for s in cl if self.r.stated(s, self.GO)], f"{where}: the rollback waits for Ryan's go")
        self.assertRegex(raw, r"(?i)\bVPN\s+off\b|--vpn-off", f"{where}: VPN off before any `sf` call")
        self.assertTrue([s for s in cl if re.search(r"(?i)\bcop(y|ies)\b", s) and "Decommissioned" in s
                         and re.search(r"(?i)(?<!test )\brecord\b", s)],
                        f"{where}: say the copies in Decommissioned are the record of what the reports were, not the "
                        "restore (one sentence)")
        self.assertTrue([s for s in cl if re.search(r"(?i)\b(never|not|no)\b[^.;]{0,60}?\b(older|old|earlier|previous|"
                                                    r"stale)\s+(\w+\s+)?(build|retrieve)s?\b", s)],
                        f"{where}: say never from an older build or retrieve (DECISIONS 2026-10-16), in one sentence")
        for s in cl:
            for m in self.OLD_SOURCE.finditer(s):
                self.assertTrue(self.d.locally_denied(s, m),
                                f"{where}: #267's rollback deploys from #267's own `before/` or a fresh retrieve, never "
                                f"from {m.group(0)!r} (a #209 folder would undo #209 too); name it only after a "
                                f"negation: {s[:200]!r}")
            for m in self.u.FROM_COPY.finditer(s):
                self.assertTrue(self.d.locally_denied(s, m) or self.d.NEGATION.search(m.group(0)),
                                f"{where}: the reports are not restored from their Decommissioned copies (a copy saved "
                                f"back is a separate report the dashboards do not show): {s[:200]!r}")
        self.r.sweep(raw, where)
        for rx, what in ((r"destructiveChanges", "a `destructiveChanges` deploy"),
                         (r"\bsf project delete\b", "`sf project delete`"),
                         (r"(-X\s*|--method\s+)DELETE\b|\bDELETE\s+/services/", "an HTTP DELETE")):
            self.assertNotRegex(raw, rx, f"{where}: {what} deletes; the rollback restores and deletes nothing")

    def test_the_runbook_and_the_plan_roll_back_by_a_deploy(self):
        where = f"RUNBOOK section {self.MONTHLY[3:]!r}"
        self.assertRollbackOf267(self.rollback_block(self.monthly(), where), f"{where}, Rollback of #267")
        path = self.plan_path()
        self.assertRollbackOf267(self.r.plan_part(path, "## Rollback", 15), f"{os.path.relpath(path, REPO)}: `## Rollback`")

    # --- the plan --------------------------------------------------------------------------------------------

    def test_the_plan_is_done_and_names_267(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        text = read(path)
        keys, _ = docs_index.frontmatter(text)
        self.assertIn("status", keys, f"{name}: frontmatter `status:`")
        word, problem = docs_index.status_of(keys["status"])
        self.assertIsNone(problem, f"{name}: {problem}")
        self.assertEqual(word, "done", f"{name}: `status: done` (deployed 2026-11-25 on Ryan's go, read back)")
        self.assertEqual(keys.get("done", "").partition("#")[0].strip(), self.DAY, f"{name}: `done: {self.DAY}`")
        self.assertRegex(text.split("\n## ", 1)[0], self.TICKET,
                         f"{name}: name ticket #267 in the frontmatter, the title or the opening paragraph")
        at = []
        for heading in ("## Rollout", "## Rollback", "## Result"):
            m = re.search(r"(?m)^" + re.escape(heading) + r"\b", text)
            self.assertIsNotNone(m, f"{name}: no `{heading}` section")
            at.append(m.start())
        self.assertEqual(at, sorted(at), f"{name}: its sections run Rollout, Rollback, Result, in that order")
        self.assertNotRegex(text, self.EMAIL, f"{name}: counts, ids and names of reports and partners only, no address")
        self.assertIn(self.FOLDER, text, f"{name}: name the work folder `{self.FOLDER}` (before/, build/, after/, copies/)")

    def test_the_plan_rollout_waits_for_ryans_go_before_the_copies_and_the_deploy(self):
        """The numbered Rollout: the fresh retrieve into `before/` first; the check-only before the deploy; Ryan's go
        before the copies and the deploy; the copies (by the tool, VPN off, tagged #267, into Decommissioned) before
        the deploy; after the deploy, `after/` compared with `build/` and the figures checked equal to SOQL. Ryan's
        go is on record: "go with sums", 2026-11-25."""
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        raw = self.r.plan_part(path, "## Rollout", 40)
        where = f"{name}: `## Rollout`"
        segments = re.split(r"`+|\n\s*\n|\n(?=\s*(?:\$\s*)?python3\s)|(?=\bpython3\s)", raw)
        copies = [flat(s) for s in segments if re.search(r"\bsf_report_folders\.py\s+copy\b", s)]
        self.assertTrue(copies, f"{where}: give the copies' command, `python3 tools/sf_report_folders.py copy --vpn-off "
                                "--kind report --id <id> --tag \"#267\"`")
        for c in copies:
            self.assertIn("--vpn-off", c, f"{where}: the tool refuses to run without `--vpn-off`: {c[:160]!r}")
            self.assertRegex(c, r"--tag[ =]\\?[\"“']?#267\b", f"{where}: each copy carries the ticket, `--tag \"#267\"`: "
                                                             f"{c[:160]!r}")
        self.assertTrue([s for s in self.cl(raw) if re.search(r"(?i)\bcop(y|ies)\b", s) and "Decommissioned" in s
                         and not self.d.denies(s)], f"{where}: the copies go to Decommissioned (one sentence)")

        steps = self.u.rollout_steps(raw, where)
        joined = " ".join(steps)

        def first(rx, after=-1):
            return next((m.start() for m in rx.finditer(joined) if m.start() > after
                         and not self.d.locally_denied(joined, m)), None)
        before = first(re.compile(r"\bbefore/"))
        check = first(self.CHECK)
        go = first(self.GO)
        copy_at = [m.start() for m in re.finditer(r"\bsf_report_folders\.py\s+copy\b", joined)]
        self.assertIsNotNone(before, f"{where}: the steps start from a fresh retrieve into `before/`")
        self.assertIsNotNone(check, f"{where}: a step runs the check-only deploy (`--dry-run`)")
        self.assertIsNotNone(go, f"{where}: a step waits for Ryan's go")
        self.assertTrue(copy_at, f"{where}: the copies are a numbered step")
        deploy, at = None, 0
        for piece in sentences(joined, ".;,"):
            at = joined.find(piece, at)
            m = re.search(r"(?i)\b(re-?)?deploy(s|ed|ing)?\b(?!\s+(package|folder|dir\w*|source|manifest)\b)", piece)
            if not m or re.search(r"(?i)check-only|--dry-run|\bvalidat", piece) or self.d.locally_denied(piece, m) \
                    or re.search(r"(?i)\b(before|until|ahead of|prior to|after|once|for|to)\b[^.;,]{0,25}$",
                                 piece[:m.start()]) \
                    or re.search(r"(?i)\b(in|at|from)\s+step\s+\d", piece):
                continue
            deploy = at + m.start()
            break
        self.assertIsNotNone(deploy, f"{where}: a step deploys (`sf project deploy start` without `--dry-run`)")
        self.assertLess(before, check, f"{where}: the `before/` retrieve comes before the check-only")
        self.assertLess(before, copy_at[0], f"{where}: the `before/` retrieve comes before the copies")
        self.assertLess(check, deploy, f"{where}: nothing is deployed before the check-only")
        self.assertLess(go, copy_at[0], f"{where}: the copies (writes through the Analytics API) wait for Ryan's go")
        self.assertLess(go, deploy, f"{where}: Ryan's go comes before the deploy")
        self.assertLess(copy_at[-1], deploy, f"{where}: every copy is made before the deploy (copy first, then change)")
        self.assertTrue([s for s in sentences(joined[deploy:], ".;") if "after/" in s and "build/" in s
                         and re.search(r"(?i)\b(compar\w*|equals?|differ\w*|diff)\b", s)],
                        f"{where}: after the deploy, the read-back retrieves into `after/` and compares it with `build/` "
                        "(one sentence)")
        self.assertTrue([s for s in sentences(joined[deploy:], ".;") if re.search(r"\bSOQL\b|\bSELECT\b", s)
                         and re.search(r"(?i)\b(equal\w*|match\w*)\b", s)],
                        f"{where}: after the deploy, the reports' figures are checked equal to SOQL (one sentence)")
        self.assertTrue([s for s in self.cl(read(path)) if self.r.stated(s, self.GO) and re.search(r"(?i)\bgo with sums\b", s)
                         and self.DAY in s],
                        f"{name}: record Ryan's go, \"go with sums\" ({self.DAY}: the three D1 attendance reports and items "
                        "10, 13 and 14), in one sentence")

    def logic_rx(self, logic):
        body = r"\s*".join(re.escape(tok) for tok in re.findall(r"\(|\)|\w+", logic))
        return re.compile(r"(?<![\w(])" + body + r"(?![\w)])(?!\s*(AND|OR)\b)")

    def test_the_plan_gives_each_totals_report_its_filter_logic(self):
        """The #209 filter values, extended to #267's shape: each of the six reports' `booleanFilter` as deployed,
        beside that report (its label, Id or item number), and no filter logic beside a report that has another."""
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        units = self.t.result_units(read(path))
        rxs = {logic: self.logic_rx(logic) for logic in {r["logic"] for r in self.TOTALS.values()}}
        found = {k: False for k in self.TOTALS}
        for u in units:
            hits = sorted(((m, logic) for logic, rx in rxs.items() for m in rx.finditer(u)), key=lambda h: h[0].start())
            for i, (m, logic) in enumerate(hits):
                owners = self.owners(u, m, [h.end() for h, _ in hits[:i]])
                wrong = sorted(k for k in owners if k == "kept" or self.TOTALS[k]["logic"] != logic)
                self.assertEqual(wrong, [], f"{name}: the filter logic `{logic}` stands beside {wrong}, whose filter logic "
                                            f"is another: {u[:200]!r}")
                for k in owners:
                    found[k] = True
        missing = [f"{k}: `{r['logic']}`" for k, r in self.TOTALS.items() if not found[k]]
        self.assertEqual(missing, [], f"{name}: give each totals report's `booleanFilter` as deployed, beside the report "
                                      f"(\"<label>: `<filter logic>`\", a table row or a list item); missing: {missing}")

    def test_the_result_records_the_check_only_the_deploy_and_the_six_copies(self):
        """The check-only's and the deploy's ids, each beside its own label, with 6/6; each copy in Decommissioned
        beside its source report; the copies tagged #267."""
        path = self.plan_path()
        raw = self.r.plan_part(path, "## Result", 40)
        where = f"{os.path.relpath(path, REPO)}: `## Result`"
        t = self.t

        def deploy_refs(u):
            checks = list(t.CHECK_WORD.finditer(u))
            spans = [(c.start(), c.end()) for c in checks]
            refs = [(m, "check") for m in checks]
            refs += [(m, "deploy") for m in t.DEPLOY_WORD.finditer(u)
                     if not any(a <= m.start() < b or m.start() <= a < m.end() for a, b in spans)
                     and not re.search(r"(?i)check[\s-]*$|--dry-run\s*$", u[:m.start()])]
            return refs
        units = t.result_units(raw)
        for rid, want, what in ((self.CHECK_ONLY, "check", "the check-only"), (self.DEPLOY_ID, "deploy", "the deploy")):
            got = t.labels(raw, rid, deploy_refs)
            self.assertTrue(got, f"{where}: record {what}'s id `{rid}`")
            self.assertIn(want, {k for k, _u in got}, f"{where}: `{rid}` is {what}'s id: name it beside that id")
            self.assertEqual([u for k, u in got if k not in (want, None)], [],
                             f"{where}: `{rid}` is {what}'s id only; here it stands beside the other step's name")
            self.assertTrue([u for u in units if rid in u and re.search(r"\b6\s*(/|of)\s*6\b|(?i:\bsucceeded\b)", u)],
                            f"{where}: say {what} `{rid}` succeeded for the six reports (\"6/6\")")
        for key, r in self.TOTALS.items():
            got = t.labels(raw, r["copy"], self.report_refs)
            self.assertTrue(got, f"{where}: record the copy of {key!r} in Decommissioned, `{r['copy']}`")
            self.assertIn(key, {k for k, _u in got}, f"{where}: the copy `{r['copy']}` is {key!r}'s (`{r['id']}`): name "
                                                    "that report beside it")
            self.assertEqual([u for k, u in got if k not in (key, None)], [],
                             f"{where}: the copy `{r['copy']}` is {key!r}'s only; here it stands beside another report")
        self.assertTrue([s for s in t.clauses(raw) if t.stated(s, t.COPY) and "Decommissioned" in s and self.TICKET.search(s)],
                        f"{where}: say the copies are in Decommissioned, tagged `#267` (one sentence, not negated)")

    def pair_rx(self, a, b):
        """`a` before and `b` after: `a → b`, `a | b` (a table), or `a + <the U.S> = b` (a note in brackets allowed)."""
        num = self.t.num
        note = r"(?:\s*\([^)]{0,30}\))?"
        sep = (r"`?\s*(?:→|->|–>|=>|\bto\b|\|)\s*`?|" + note + r"\s*\+\s*`?[\d,]+`?" + note + r"\s*=\s*`?")
        return re.compile(num(a).pattern + r"(?:" + sep + r")" + num(b).pattern)

    @staticmethod
    def ints(text):
        return [int(x.replace(",", "")) for x in re.findall(r"(?<![\w.,])\d{1,3}(?:,\d{3})+(?![\d])|(?<![\w.,])\d+(?!\d)",
                                                          text)]

    @staticmethod
    def in_order(seq, xs):
        it = iter(xs)
        return all(any(x == want for x in it) for want in seq)

    def test_the_result_gives_each_reports_figures_equal_to_soql(self):
        """Each totals report's Jan-Oct figure before -> after, the after = before + the U.S amount, beside that
        report and said equal to SOQL; no figure beside a report it is not; Overall Attendance by Month by month
        (before + the U.S, each month) and the U.S amounts by month, in month order; the all-Monthly-Reports SOQL
        total equal to the reports' 49,976."""
        self.assertEqual((sum(self.BEFORE_BY_MONTH), sum(self.US_BY_MONTH)), (49337, 639),
                         "the record: Jan-Oct 49,337 before #267, the U.S 639")
        path = self.plan_path()
        raw = self.r.plan_part(path, "## Result", 40)
        where = f"{os.path.relpath(path, REPO)}: `## Result`"
        t = self.t
        units = t.result_units(raw)
        rxs = {(a, d): self.pair_rx(a, a + d) for r in self.TOTALS.values() for a, d in r["figures"]}
        hits = {k: [] for k in self.TOTALS}
        for u in units:
            found = sorted(((m, fig) for fig, rx in rxs.items() for m in rx.finditer(u)), key=lambda h: h[0].start())
            for i, (m, fig) in enumerate(found):
                owners = self.owners(u, m, [h.end() for h, _ in found[:i]])
                wrong = sorted(k for k in owners if k == "kept" or fig not in self.TOTALS[k]["figures"])
                self.assertEqual(wrong, [], f"{where}: {fig[0]:,} -> {sum(fig):,} stands beside {wrong}, whose figure it "
                                            f"is not: {u[:200]!r}")
                for k in owners:
                    hits[k].append(u)
        for key, r in self.TOTALS.items():
            want = " or ".join(f"{a:,} → {a + d:,}" for a, d in r["figures"])
            self.assertTrue(hits[key], f"{where}: give {key!r} Jan-Oct {want} (before + the U.S), the report beside its "
                                       f"figures (\"{key} {want}\")")
            self.assertTrue([u for u in hits[key] if re.search(r"\bSOQL\b", u) and t.stated(self.norm(u), t.EQUAL_STRICT)],
                            f"{where}: say {key!r}'s figure equals SOQL, in the list item, row or sentence that gives it")
        after = [b + u for b, u in zip(self.BEFORE_BY_MONTH, self.US_BY_MONTH)]
        self.assertTrue([u for u in units if self.in_order(after, self.ints(u))],
                        f"{where}: give Overall Attendance by Month by month, January-October 2026, after #267 (before + "
                        f"the U.S, each month): {', '.join(map(str, after))}, in month order in one row, item or sentence")
        self.assertTrue([u for u in units if self.in_order(self.US_BY_MONTH, self.ints(u)) and self.us(self.norm(u))],
                        f"{where}: give the U.S amounts by month, January-October 2026: "
                        f"{', '.join(map(str, self.US_BY_MONTH))}, in month order in one row, item or sentence")
        total = t.num(sum(after))
        self.assertTrue([u for u in units if total.search(u)
                         and re.search(r"(?i)\b(all|every)\s+(the\s+)?(`?DHIS2__c`?|Monthly\s+Reports?)\b|"
                                       r"\bno\s+other\s+filter\b", u)
                         and (t.stated(self.norm(u), t.EQUAL_STRICT) or "=" in u)],
                        f"{where}: say the SOQL total of all Monthly Reports (`DHIS2__c`) with `Period__c` January-October "
                        f"2026, no other filter, equals the reports' {sum(after):,} (one row, item or sentence)")

    def test_the_result_says_the_rest_read_back_unchanged(self):
        """The read-back: `after/` equals `build/` for the six reports, and `before/` for every other component (the
        reports that keep the exclusion, item 19, the three not-submitted lists, the dashboards)."""
        path = self.plan_path()
        raw = self.r.plan_part(path, "## Result", 40)
        where = f"{os.path.relpath(path, REPO)}: `## Result`"
        units = [self.norm(u) for u in self.t.result_units(raw)]
        equal = re.compile(r"(?i)\b(equal(s|led)?|identical|the same as|byte\s+for\s+byte)\b")
        self.assertTrue([u for u in units if "after/" in u and "build/" in u and self.stated(u, equal)
                         and re.search(r"(?i)\b(6|six)\b|\bchanged\b", u)],
                        f"{where}: say `after/` equals `build/` for the six changed reports (one row, item or sentence)")
        self.assertTrue([u for u in units if "after/" in u and "before/" in u and self.stated(u, equal)
                         and re.search(r"(?i)\b(other|rest|remaining|unchanged|kept)\b|\bitem\s+19\b|\bnot[- ]submitt\w*|"
                                       r"\blists\b", u)],
                        f"{where}: say `after/` equals `before/` for every other component (the reports that keep the "
                        "exclusion, item 19, the three not-submitted lists, the dashboards), one row, item or sentence")

    # --- DECISIONS -------------------------------------------------------------------------------------------

    def test_a_decision_records_the_totals_through_october_and_amends_209(self):
        entries = re.split(r"(?m)^(?=### )", read(self.DECISIONS))[1:]

        def day(entry):
            m = re.match(r"### (\d{4}-\d\d-\d\d) ", entry)
            return m.group(1) if m else ""
        old = [e for e in entries if e.startswith("### 2026-11-05 — The six U.S partners") and self.T209.search(e)]
        self.assertEqual(len(old), 1, "docs/DECISIONS.md: the 2026-11-05 entry on #209 (the six U.S partners)")
        new = [e for e in entries if day(e) >= self.DAY and self.TICKET.search(e)]
        self.assertTrue(new, f"docs/DECISIONS.md: no dated entry (`### {self.DAY} — …`, or later) naming #267, the U.S "
                             "Monthly Reports through October 2026 counted on the totals reports")
        e = new[0]
        where = f"docs/DECISIONS.md {day(e)}"
        self.assertGreater(entries.index(e), entries.index(old[0]), f"{where}: the entry comes after #209's 2026-11-05 one")
        for part in ("**Why", "**Rejected", "**Consequences"):
            self.assertIn(part, e, f"{where}: no {part}** bullet (the file's header)")
        cl = self.cl(e)
        self.assertTrue([s for s in cl if ("2026-11-05" in s or self.T209.search(s))
                         and re.search(r"(?i)\bamend\w*|\bnarrow\w*|\bexceptions?\b|\brevers\w*", s)],
                        f"{where}: say the entry amends the 2026-11-05 decision (#209), in one sentence")
        totals = re.compile(r"(?i)\btotals?\b|\bsums?\b|\btrends?\b|\bsix\s+(\w+\s+){0,2}?reports\b")
        self.assertTrue([s for s in cl if self.us(s) and self.CUTOFF_ANY.search(s) and self.stated(s, self.COUNTS)
                         and totals.search(s)],
                        f"{where}: say the totals reports count the U.S partners' Monthly Reports with `Period__c` before "
                        "2026-11-01 (through October 2026), in one sentence")
        self.assertTrue([s for s in cl if self.stated(s, self.KEEP) and self.EXCLUSION.search(s) and re.search(
            r"(?i)\bitem\s+19\b|\bstories\b|\bapprov\w*|\bon[- ]time\b|\bwho\s+reported\b", s)],
                        f"{where}: say the who-reported, approval, on-time and stories reports (item 19) keep the full #209 "
                        "exclusion, in one sentence")
        why = self.norm(e.split("**Why", 1)[1].split("**Rejected", 1)[0])
        self.assertTrue(re.search(r"\bRyan\b", why) and re.search(r"(?i)\binteractive\b", why),
                        f"{where}: **Why** gives Ryan's reason: the monthly dashboards line up with the interactive "
                        "dashboard")
        rejected = sentences(self.norm(e.split("**Rejected", 1)[1].split("**Consequences", 1)[0]), ".;")
        self.assertTrue([s for s in rejected if re.search(r"(?i)\b(every|all|each)\s+(\w+\s+){0,2}?reports?\b", s)],
                        f"{where}: **Rejected** names counting the U.S on every Monthly report (item 19 and the approval "
                        "reports too)")
        self.assertTrue([s for s in rejected if re.search(
            r"(?i)\b(no|without|any|other|later|another|different)\s+(\w+\s+)?cut-?off\b|\bevery\s+month\b|"
            r"\b(after|past|beyond)\s+October\b|\bNovember\b|\bopen[- ]ended\b|\ball\s+months\b", s)],
                        f"{where}: **Rejected** names counting the U.S Monthly Reports with no cutoff (every month, "
                        "November on)")
        cons = sentences(self.norm(e.split("**Consequences", 1)[1]), ".;")
        self.assertTrue([s for s in cons if self.us(s) and re.search(r"(?i)\bNovember\b|2026-11-01|11/1/2026|\bafter\s+"
                                                                     r"October\b|\blater\b", s)
                         and re.search(r"(?i)\bstay\w*\s+out\b|\b(left|leav\w*)\s+out\b|\bout\s+of\b|\bexclud\w*|"
                                       r"\bnot\s+count\w*|\bno\s+longer\s+count\w*", s)],
                        f"{where}: **Consequences**: a U.S Monthly Report for November 2026 or later stays out of every "
                        "report (one sentence)")
        plan = os.path.basename(self.plan_path())
        self.assertIn(f"plans/{plan}", e, f"{where}: link #267's plan (`plans/{plan}`)")
        pointers = re.findall(r"(?m)^\s*- " + re.escape(day(e)) + r"[:,].*(?:\n(?!\s*- |\n|#).*)*", old[0])
        self.assertTrue(pointers, f"docs/DECISIONS.md 2026-11-05 (#209): the entry gets a dated bullet `- {day(e)}: …` "
                                  f"pointing at the {day(e)} entry (the file's header: the earlier decision gets a dated "
                                  "bullet pointing at the one that amends it)")
        joined = " ".join(flat(b) for b in pointers)
        self.assertRegex(joined, self.TICKET, f"docs/DECISIONS.md 2026-11-05: the `- {day(e)}:` bullet names #267")
        self.assertRegex(joined, r"(?i)\bsee\b|\bentry\b|\bamend\w*|\bbelow\b",
                         f"docs/DECISIONS.md 2026-11-05: the `- {day(e)}:` bullet points at the new entry (\"amended by "
                         f"#267\", \"see the {day(e)} entry\")")


if __name__ == "__main__":
    unittest.main(verbosity=1)
