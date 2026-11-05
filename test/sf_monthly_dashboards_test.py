#!/usr/bin/env python3
"""
The Monthly Report (`DHIS2__c`) reports and dashboards in Salesforce and the interactive dashboard
(LWC `glowDashboardShell`), epic #68: one class per task.

DecommissionedFoldersDocs (ticket #69): the RUNBOOK says what the Monthly Report dashboards are and
names the two hidden "Decommissioned" folders (a report folder and a dashboard folder, no share);
a retired report or dashboard is moved there and keeps its Id, nothing is deleted; a copy as it was
goes there before each change, and the section says how to revert from it; the interactive
dashboard has its own section naming its code; a plan carries the folder deploy and the API proof;
a dated DECISIONS entry records archive-not-delete; the salesforce skill points at both sections.
Every part a test reads is also swept for what would contradict the rule (contradictions()): a
deletion, a share, or a softener that makes the copy, the check-only or the revert optional.
Counts and names of reports only: no figure from the org is pinned.

KeepListDocs (ticket #70): the RUNBOOK's `### The keep list` names `glow/sf_keep_list.csv`, the five
groups, Partner and Month, the unchanged labels, Decommissioned for what is off the list and the
test-record filter; a dated DECISIONS entry records the keep list, Ryan's words, the rule and what was
rejected (`Partner_Status__c` with its reason). Each rule is checked as stated, not negated, rejected,
renamed, put off or softened, with #69's `locally_denied` and `contradictions`.

CategoryFoldersDocs (ticket #73): one report folder "GLOW Monthly Reports" and one dashboard folder
"GLOW Monthly Dashboards" (Ryan, 2026-10-21) for the kept items; the RUNBOOK's `### The five
dashboards and their folders` table (read against `glow/sf_keep_list.csv`), the folders' shares
copied from the DHIS2 folders (internal only), the plan (deploy, copies before moves, SOQL check,
undo) and a dated bullet on the keep-list DECISIONS entry. Labels do not change (Ryan, 2026-10-23).
RetiredReportsDocs (ticket #72): the RUNBOOK's `### Decommissioned` records the retirement (its date, 29
reports and 10 dashboards moved, the 19 held for #75-#79, the ledger `data/sf_retire_2026-10-23/ledger.csv`)
and how to bring an item back; the plan `docs/plans/<date>-sf-retire-reports.md` names #72, its Rollout has
the dry run, `--limit 1`, Ryan's go, the dashboards by hand and the SOQL check by Id, its Rollback is the
tool's undo from that ledger and deletes nothing, and its Result gives the counts.

ReportingDashboardDocs (ticket #79): the dashboard "GLOW Club Reporting" (D5, "Reporting") and its items 17-19,
read from `glow/sf_keep_list.csv`, not pinned. The RUNBOOK's `### GLOW Club Reporting` names each measure, its
label and Id, says each report groups by Partner (`Account__c`) and Month (`Period__c`), the period (the last 12
months through `Period__c`), the test-record rule, the dashboard's only filter Partner Manager
(`Assigned_Partner_Manager__c`; no Partner or Month filter, Ryan 2026-10-24), item 19 a tabular report with Partner
and Month columns, and one `SELECT ... FROM DHIS2__c` signal per item. The
Rollback (the plan's and the RUNBOOK's): the reports from their Decommissioned copies; the dashboard, dynamic and
so refused an API copy at the org's limit of 5 (Ryan, 2026-10-24), from this change's
`data/sf_dash_reporting_<date>/before/` only while a fresh retrieve equals `after/`, never from an older build.
The plan `docs/plans/<date>-sf-dash-reporting.md` names #79; its Rollout runs before/, the report copies, the
check-only, Ryan's go, the deploy, the `after/` read-back against `build/` and the SOQL check, in that order; its
`## Result` waits for the live deploy, so no org figure is pinned.

ImplementationDashboardDocs (ticket #76): the RUNBOOK's `### GLOW Club Implementation` (D2) names the
dashboard and its four reports (items 5-8 of `glow/sf_keep_list.csv`, read from the CSV), what each counts
(items 5, 7, 8 a `DHIS2__c` field; item 6 the Jotform batches' `Module__c` on `Attendance_Batch__c`), the
one dashboard filter, Partner Manager (no Partner filter, Ryan 2026-10-24; item 6 reached through one new
column on `Attendance_Totals`), the grouping by Partner and Month, the last-12-months period, the
test-record rule and the SOQL signal for each side (AND-joined, no OR, with a period and a one-partner
query); its rollback is the reports' copies in Decommissioned, or this change's `before/` only while a fresh
retrieve equals `after/`, never an older build (D2 is dynamic and has no API copy); the plan
`docs/plans/<date>-sf-dash-implementation.md` names #76, its Rollout copies, checks, waits for Ryan's go,
deploys, reads back and checks by SOQL, in that order, and it has a `## Result`. No count from the org.

ObservationsDashboardDocs (ticket #77): the RUNBOOK's `### GLOW Club Observations` names items 9-11 (GLOW's words and
the report labels from `glow/sf_keep_list.csv`) with each one's `DHIS2__c` field and SOQL signal, the one dashboard
filter Partner Manager (no Partner or Month filter, Ryan 2026-10-24), item 16 taken off, the grouping (`Account__c`, then `Period__c`), the last 12 months and the test-record rule; the
rollback is the Decommissioned copies, or this change's `before/` only while a fresh retrieve equals `after/`, never
an older build; the plan `docs/plans/<date>-sf-dash-observations.md` names #77 and its Rollout has the copies, the
check-only, Ryan's go, the read-back and the SOQL check, in that order, and a `## Result`.

TrainingDashboardDocs (ticket #78): the RUNBOOK's `### GLOW Club Training` names items 13-16 by their labels in
`glow/sf_keep_list.csv` with the `DHIS2__c` field each counts, the period (`Period__c` `LAST_N_MONTHS:12`), the
grouping (Partner `Account__c`, then month), the test-record rule, the dashboard's Partner and Month filters, a
SOQL on `DHIS2__c` per component and the rollback; the plan `docs/plans/<date>-sf-dash-training.md` names #78, its
Rollout copies to Decommissioned, checks-only, waits for Ryan's go, reads `after/` back against `build/` and checks
each component by SOQL; its Rollback restores from the copies or from this change's `before/` only while a fresh
retrieve equals `after/`, never from an older build.

AttendanceDashboardDocs (ticket #75): the RUNBOOK's `### GLOW Club Attendance` (D1) says, per component, what
it counts (items 1, 3 and 4 of `glow/sf_keep_list.csv`, GLOW's wording, the `DHIS2__c` field, a SOQL signal),
that item 2 is retired from D1 and its report goes to Decommissioned, the period (last 12 months on `Period__c`),
the grouping (Partner `Account__c`, then the month), the dashboard's only filter, Partner Manager on
`Assigned_Partner_Manager__c` (no Partner and no Month filter: Ryan, 2026-10-24 on #75), and the test-record
rule; the rollback: the reports from their Decommissioned copies, the dynamic dashboard (no API copy) from this
change's `before/` only while a fresh retrieve equals `after/`, never an older build; the plan
`docs/plans/<date>-sf-dash-attendance.md` names #75 and its Rollout runs before/, copies, check-only, Ryan's go,
deploy, `after/`, SOQL in that order.

NewMentorsDocs (ticket #80): item 12, the report "Partners that recruited new mentors" (Ryan, 2026-10-26: option A),
a component on D4. The RUNBOOK's `### GLOW Club Training` defines it: the Monthly Reports (`DHIS2__c`) answering Yes
and No to `Recruit_any_new_mentors_last_month__c`, by partner (`Account__c`) and month (`Period__c`), blank answers
left out, each Yes one partner's month and not a number of mentors, with a SOQL signal (GROUP BY the answer,
`LAST_N_MONTHS:12`, the test-record rule), kept apart from item 13; `Newly_recruited__c` and "Lead Mentor" contacts
only ever denied. The plan `docs/plans/<date>-sf-new-mentors.md` names #80; its Rollout runs before/, the copy of
D4, check-only, Ryan's go, deploy, `after/` against `build/`, SOQL for six complete months and one partner; its
Rollback restores D4 from its copy or a guarded `before/`, then moves the new report to Decommissioned, deleting
nothing. A dated DECISIONS entry records the definition with **Why**, **Rejected** and **Consequences**.

GlowReviewAttendanceDocs (ticket #196, epic #194, GLOW's review of 2026-11-02): the RUNBOOK's `### GLOW Club
Attendance` says D1's reports filter `In_Reporting_Year__c equals true` (2026 only) and D1 has a Month filter on
`DHIS2__c$Month__c`, with the last 12 months, "no Month filter" and "Partner Manager the only filter" left only as
history; item 3's grand total and item 4's totals (Sum Monthly Max included) are off because they double-count girls
who attend several sessions. The plan `docs/plans/2026-11-02-sf-review-attendance.md` names #196; its Rollout runs
before/, the copies to Decommissioned (`--tag "#196"`), the check-only, Ryan's go, the deploy and the `after/`
read-back against `build/`, in that order; its Rollback restores the reports from the copies and D1 from `before/`,
never an older build; it has a `## Result`. AttendanceDashboardDocs (#75) accepts #196's period and Month filter.
GlowReviewImplementationDocs (ticket #197, epic #194, GLOW's review of 2026-11-02): the RUNBOOK's `### GLOW Club
Implementation` says item 6 counts unique partners per module (not clubs or batches), a horizontal bar, with a SOQL
signal `COUNT_DISTINCT(Account__r.ParentId)` by `Module__c` from September 2026; the data gap (no module data
January-August 2026, from September from Jotform); D2's reports filter `In_Reporting_Year__c equals true` (2026
only) and D2 has a Month filter on `DHIS2__c$Month__c` and `Attendance_Batch__c$Month_Name__c`, the last 12 months
and "no Month filter" left only as history. `glow/sf_keep_list.csv` carries GLOW's names for items 5-7, every
report's target label within 40 characters. The plan `docs/plans/2026-11-02-sf-review-implementation.md` names
#197; its Rollout runs before/, the copies to Decommissioned (`--tag "#197"`), the check-only, Ryan's go, the
deploy, the `after/` read-back against `build/` and the SOQL check, in that order; its Rollback restores the
reports from the copies, D2 from `before/` and moves the new reports to Decommissioned; it has a `## Result`.
ImplementationDashboardDocs (#76) accepts #197's period, Month filter and item 6's grouping.
GlowReviewObservationsDocs (ticket #198, epic #194, GLOW's review of 2026-11-02): the keep list gives items 9-11 GLOW's
names (`label_target`), none with "Alteast" and every report's within 40 characters; the RUNBOOK's `### GLOW Club
Observations` says item 11 derives Observed Yes/No from the sessions observed
(`GC_sessions_did_you_observe_last_month__c`), not from the count question
(`many_clubs_do_you_still_need_to_observe__c`, no answers in 2026). ObservationsDashboardDocs (#77) accepts #198's
reporting year, Month filter, new report labels and `data/sf_glow_review_<month>/` rollback folder, and
CategoryFoldersDocs the new title of D3 in the dashboards table.
GlowReviewReportingDocs (ticket #200, epic #194, GLOW's review of 2026-11-02): item 17's `label_target` in
`glow/sf_keep_list.csv` is "Monthly Report Approval Status"; the RUNBOOK's `### GLOW Club Reporting` describes the
overview chart (approved versus not yet approved by month, a stacked column on D5, from the new report "Approval
Status by Month" without item 17's `Approved__c equals 1` filter, with its SOQL signal) and why it needs its own
report (item 17 lists approved reports only); D5 and items 17-19 show the reporting year (`In_Reporting_Year__c`),
2026 only, said of D5, its reports or a component; D5 has a Month filter on `DHIS2__c$Month__c`; the last 12 months
and "no Month filter" only as history. The plan `docs/plans/2026-11-02-sf-review-reporting.md` names #200; its
Rollout runs before/, the copies (`--tag "#200"`), the check-only, Ryan's go, the deploy and `after/` in that order;
its Rollback restores the reports and D5 by a deploy (a fresh retrieve edited back, or #200's own `before/` only
while a fresh retrieve equals `after/`), the Decommissioned copies only the record, never an older build or another
change's folder. ReportingDashboardDocs (#79) accepts #200's period, Month filter, label and rollback folder.
"""
import glob
import os
import re
import sys
import unittest

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import REPO, flat, md_part, read, sentences


class DecommissionedFoldersDocs(unittest.TestCase):
    """Ticket #69 (Ryan, 2026-10-21): "Create a decommissioned folder to put any old copies in in case
    we need to revert any changes." The docs side of the inventory and the two hidden folders."""

    longMessage = False         # the messages say what to fix; the whole section is not repeated
    RUNBOOK = os.path.join(REPO, "docs", "RUNBOOK.md")
    DECISIONS = os.path.join(REPO, "docs", "DECISIONS.md")
    SKILL = os.path.join(REPO, ".claude", "skills", "salesforce", "SKILL.md")
    PLANS = os.path.join(REPO, "docs", "plans", "*-sf-reporting-inventory.md")
    MONTHLY = "## Monthly Report dashboards in Salesforce"
    DECOM = "### Decommissioned"
    INTERACTIVE = "## Interactive dashboard in Salesforce"
    TICKET = re.compile(r"(?<![\w#])#69\b")
    DHIS2_FOLDERS = ("DHIS2 Reports", "DHIS2 Dashboards", "Dhis2 Dashbords")

    # a statement that denies what it names
    NEGATION = re.compile(r"\b(not|no|never|nothing|none|nor|neither|without|no longer|instead of|rather than)\b|"
                          r"n['’]t\b", re.I)
    # "is never deleted" / "rather than deleted" is the rule itself, not a denial of the move
    NOT_DELETED = re.compile(r"\b(never|not|nothing|no|instead of|rather than)\b[^.;,]{0,25}?\bdelet\w*", re.I)
    REPORT_AND_DASHBOARD = re.compile(r"\breports?\b[^.;]{0,40}?\bdashboards?\b|\bdashboards?\b[^.;]{0,40}?\breports?\b",
                                      re.I)
    # "no `folderShares`", "not shared", "no one but administrators" is what hidden means, not a denial of the folder
    UNSHARED = re.compile(r"(?i)\bno\s+(`?folderShares`?|shares?)\b|\bnot\s+shared\b|\bunshared\b|"
                          r"\bonly\s+(the\s+)?administrators\b|\bno one but\b[^.;]{0,20}\badministrators\b|"
                          r"\bshared with no one\b|\bnobody\b[^.;]{0,20}\bshared?\b")
    SHARES_API = re.compile(r"(?i)\bshares API\b|/folders/[^\s`]*/shares\b")

    # --- the contradiction sweep -----------------------------------------------------------------------
    DELETE = re.compile(r"(?i)\bdelet\w*|\brecycle bin\b|\bempt(y|ies|ied|ying)\s+(the\s+|a\s+|its\s+|both\s+|each\s+)?"
                        r"(\w+\s+)?folders?\b|\bpurg\w*|\bdestroy\w*|\berase\w*")
    SHARE = re.compile(r"(?i)\bshar(e|es|ed|ing)\b|\b(visible|open|available)\s+to\s+(everyone|all|every|any|users|"
                       r"partners|the org)\b")
    # a denial with a time limit ("not deleted ... after a week", "nothing is deleted on day one") is no denial
    TIME_LIMIT = re.compile(r"(?i)\b(until|after|later|afterwards|eventually|then|days?|weeks?|months?|years?)\b")
    # what makes the copy, the check-only or the revert optional
    SOFTENER = re.compile(r"(?i)\b(skip\w*|optional(ly)?|if you\b|unless|in a hurry|impossible|cannot|can['’]t|"
                          r"not needed|need not|needn['’]t|no need|whenever|sometimes|ideally|if (there is )?time|"
                          r"when convenient|without waiting|straight to production|just kidding)\b")
    NO_ROLLBACK = re.compile(r"(?i)\bno rollback\b|\bnothing to roll back\b|\bcannot be rolled back\b|"
                             r"\bno way (back|to roll back)\b")
    # in a Rollback, removing the two folders and the proof clones is allowed; removing reports or dashboards is not
    MANY_REPORTS = re.compile(r"(?i)\b(all|every|any|other|retired|existing|kept|their|the|DHIS2)\s+(\w+\s+){0,2}?"
                              r"(reports|dashboards)\b|\b(reports|dashboards)\s+in\s+(them|it|the\b)")

    def denies(self, text):
        for rx in (self.NOT_DELETED, self.UNSHARED):
            text = rx.sub(" ", text)
        return bool(self.NEGATION.search(text))

    def locally_denied(self, s, m):
        """A negation in the words before match `m` of clause `s`, back to the last comma, dash or "but"."""
        pre = re.split(r"[,—–(]|\bbut\b|\bhowever\b|\bactually\b", s[max(0, m.start() - 40):m.start()])[-1]
        return bool(self.NEGATION.search(pre))

    def contradictions(self, text, share=False, rollback=False):
        """The clauses of `text` that contradict the rules: a deletion not denied where it is said (or denied
        with a time limit); with `share`, a share not denied (or denied with a time limit); a softener (skip,
        optional, unless, impossible, ...) not itself denied. With `rollback`, a deletion of the folders or
        the proof clones is allowed, of reports or dashboards (plural) not, and "no rollback" is one."""
        out = []
        for s in sentences(self.norm(text), ".;:?!"):
            kept = self.SHARES_API.sub(" ", s)
            kept = re.sub(r"(?i)\bShare dialog\b", " ", kept)
            checks = [("deletes", self.DELETE)] + ([("shares", self.SHARE)] if share else [])
            for what, rx in checks:
                for m in rx.finditer(kept):
                    if self.locally_denied(kept, m):
                        if self.TIME_LIMIT.search(kept):
                            out.append(f"{what} with a time limit: {s[:160]!r}")
                            break
                        continue
                    if what == "deletes" and rollback and not self.MANY_REPORTS.search(kept):
                        continue
                    out.append(f"{what}: {s[:160]!r}")
                    break
            for m in self.SOFTENER.finditer(s):
                if not self.locally_denied(s, m):
                    out.append(f"softens a rule ({m.group(0)!r}): {s[:160]!r}")
                    break
            if rollback and self.NO_ROLLBACK.search(s):
                out.append(f"says there is no rollback: {s[:160]!r}")
        return out

    def assertNoContradiction(self, text, where, **kw):
        found = self.contradictions(text, **kw)
        self.assertEqual(found, [], f"{where}: contradicts the rules (nothing deleted, the folders shared with no one, "
                                    "the copy, the check-only and the revert never optional): " + "; ".join(found))

    # --- reading the docs ---------------------------------------------------------------------------------

    @staticmethod
    def norm(text):
        """`text` flattened, a dot inside a name (`DHIS2__c.Account__c`) made `_`, so `[^.]` spans it."""
        return re.sub(r"(?<=\w)\.(?=\w)", "_", flat(text))

    def clauses(self, text, ends=".;"):
        return sentences(self.norm(text), ends)

    def monthly(self):
        return md_part(self.RUNBOOK, self.MONTHLY)

    def decommissioned(self):
        """The `### Decommissioned` part of the Monthly Report section, to the next `###` or `##`."""
        section = self.monthly()
        m = re.search(r"^" + re.escape(self.DECOM) + r"(?!\w).*$", section, re.M)
        self.assertTrue(m, f"RUNBOOK section {self.MONTHLY[3:]!r}: no `{self.DECOM}` part under it")
        rest = section[m.start():]
        nxt = re.search(r"\n#{1,3} ", rest)
        return rest[:nxt.start()] if nxt else rest

    def interactive(self):
        return md_part(self.RUNBOOK, self.INTERACTIVE)

    def plan_path(self):
        found = sorted(glob.glob(self.PLANS))
        self.assertEqual(len(found), 1, "docs/plans/: one plan `YYYY-MM-DD-sf-reporting-inventory.md` for ticket #69 "
                                        f"(found {[os.path.basename(p) for p in found]})")
        self.assertRegex(os.path.basename(found[0]), r"^\d{4}-\d\d-\d\d-sf-reporting-inventory\.md$",
                         "docs/plans/: the plan is named `YYYY-MM-DD-sf-reporting-inventory.md`")
        return found[0]

    def decision(self):
        entries = re.split(r"(?m)^(?=### )", read(self.DECISIONS))[1:]
        new = [e for e in entries if re.match(r"### (\d{4}-\d\d-\d\d) ", e)
               and re.match(r"### (\d{4}-\d\d-\d\d) ", e).group(1) >= "2026-10-21"
               and "Decommissioned" in e and re.search(r"(?i)\bnever deleted\b|\bnot deleted\b|\bnothing is deleted\b", e)]
        self.assertTrue(new, "docs/DECISIONS.md: no dated entry (`### 2026-10-21 — …`, or later) that retired Salesforce "
                             "reports and dashboards are moved to Decommissioned, never deleted")
        return new[0]

    def skill_item(self):
        m = re.search(r"(?m)^- \*\*Reports and dashboards\*\*.*(?:\n(?!- |\n|#).*)*", read(self.SKILL))
        self.assertTrue(m, ".claude/skills/salesforce/SKILL.md: no `- **Reports and dashboards**` item")
        return m.group(0)

    # --- the RUNBOOK's Monthly Report section -------------------------------------------------------

    def test_the_monthly_section_says_what_the_dashboards_are(self):
        where = f"RUNBOOK section {self.MONTHLY[3:]!r}"
        text = self.norm(self.monthly())
        self.assertIn("DHIS2__c", text, f"{where}: name the Monthly Report object `DHIS2__c`")
        for folder in self.DHIS2_FOLDERS:
            self.assertIn(folder, text, f"{where}: name today's folder {folder!r} (sic)")
        self.assertRegex(text, r"(?i)\b\d+\s+(\w+\s+){0,3}?reports\b",
                         f"{where}: give the inventory's count of reports (\"63 reports in …\")")
        self.assertRegex(text, r"(?i)\b\d+\s+(\w+\s+){0,3}?dashboards\b",
                         f"{where}: give the inventory's count of dashboards (\"… dashboards in …\")")
        self.assertRegex(text, r"data/sf_reporting_\d{4}-\d\d-\d\d/",
                         f"{where}: name the retrieve and inventory folder `data/sf_reporting_<date>/`")
        self.assertNoContradiction(self.monthly(), where)

    def test_the_runbook_names_both_decommissioned_folders(self):
        where = f"RUNBOOK section {self.MONTHLY[3:]!r}, {self.DECOM[4:]!r}"
        part = self.decommissioned()
        said = [s for s in self.clauses(part) if not self.denies(s)]
        hidden = re.compile(r"(?i)\bhidden\b")
        for kind, rx in (("report", r"(?i)\breport folders?\b|`?ReportFolder`?"),
                         ("dashboard", r"(?i)\bdashboard folders?\b|`?DashboardFolder`?")):
            self.assertTrue([s for s in said if re.search(rx, s) and "Decommissioned" in s and hidden.search(s)
                             and self.UNSHARED.search(s)],
                            f"{where}: say the {kind} folder \"Decommissioned\" is hidden and not shared (no "
                            "`folderShares`, only administrators see it), in one sentence (not negated)")
        # the shares API is the measure, and it shows no share (Folder.AccessType reads Hidden even on a shared folder)
        shows_none = re.compile(r"(?i)\b(no|neither|none|zero|0)\b[^.;]{0,40}?\bshares?\b|\bempty\b")
        self.assertTrue([s for s in self.clauses(part) if self.SHARES_API.search(s)
                         and shows_none.search(self.SHARES_API.sub(" ", s))],
                        f"{where}: say the shares API shows no share on either folder, in one sentence")
        self.assertNoContradiction(part, where, share=True)

    def test_a_retired_report_is_moved_never_deleted(self):
        where = f"RUNBOOK section {self.MONTHLY[3:]!r}, {self.DECOM[4:]!r}"
        part = self.decommissioned()
        keeps_id = re.compile(r"(?i)\b(keeps?|keeping|same|unchanged)\b[^.;]{0,30}?\bId\b|\bId\b[^.;]{0,30}?"
                              r"\b(unchanged|stays|is kept|the same)\b")
        moved = [s for s in self.clauses(part)
                 if re.search(r"(?i)\bretir\w*\b", s) and re.search(r"(?i)\bmov(e|ed|es|ing)\b", s)
                 and self.REPORT_AND_DASHBOARD.search(s) and keeps_id.search(s) and not self.denies(s)]
        self.assertTrue(moved, f"{where}: say a retired report or dashboard is moved to Decommissioned and keeps its "
                               "Id, in one sentence (not negated)")
        nothing = [s for s in self.clauses(part)
                   if re.search(r"(?i)\b(nothing|never|no\s+(report|dashboard)\w*)\b[^.;]{0,40}?\bdelet\w*\b", s)]
        self.assertTrue(nothing, f"{where}: say nothing is deleted (\"nothing is deleted in this epic\")")
        # no step in the section deletes a report or dashboard
        section = self.monthly()
        if "destructiveChanges" in section:
            self.assertNotRegex(section, r"<name>\s*(Report|Dashboard)\s*</name>",
                                f"RUNBOOK section {self.MONTHLY[3:]!r}: a `destructiveChanges` lists a `Report` or "
                                "`Dashboard`; a retired one is moved to Decommissioned instead")
        for s in self.clauses(section):
            if "destructiveChanges" in s and re.search(r"\b(Reports?|Dashboards?|reports?|dashboards?)\b", s):
                self.assertTrue(self.NEGATION.search(s), f"RUNBOOK section {self.MONTHLY[3:]!r}: a step deletes a "
                                                         f"report or dashboard: {s[:160]!r}")
        for rx, what in ((r"\bsf project delete source\b", "`sf project delete source`"),
                         (r"(?i)(\bDELETE\b|-X\s*DELETE|--method\s+DELETE)[^\n]{0,80}/analytics/(reports|dashboards)",
                          "a DELETE on the analytics API"),
                         (r"(?i)/analytics/(reports|dashboards)[^\n]{0,80}(-X\s*DELETE|--method\s+DELETE)",
                          "a DELETE on the analytics API")):
            self.assertNotRegex(section, rx, f"RUNBOOK section {self.MONTHLY[3:]!r}: {what} deletes a report or "
                                             "dashboard; nothing is deleted")
        self.assertNoContradiction(section, f"RUNBOOK section {self.MONTHLY[3:]!r}")

    def test_a_copy_goes_to_decommissioned_before_every_change(self):
        where = f"RUNBOOK section {self.MONTHLY[3:]!r}, {self.DECOM[4:]!r}"
        part = self.decommissioned()
        as_it_was = re.compile(r"(?i)\bas it (was|stood)\b|\bunchanged\b|\buntouched\b|\boriginal\b")
        source_id = re.compile(r"(?i)\bsource\b[^.;]{0,15}?\bId\b")
        copy = [s for s in self.clauses(part)
                if re.search(r"(?i)\bcop(y|ies)\b", s) and re.search(r"(?i)\bbefore\b", s)
                and re.search(r"(?i)\bchang\w*\b", s) and "Decommissioned" in s and as_it_was.search(s)
                and self.REPORT_AND_DASHBOARD.search(s) and source_id.search(s) and re.search(r"(?i)\bticket\b", s)
                and not self.denies(s)]
        self.assertTrue(copy, f"{where}: say that before a report or dashboard changes, a copy of it as it was goes "
                              "to Decommissioned carrying its source Id and the ticket, in one sentence (not negated)")
        self.assertIn("before/", self.norm(part), f"{where}: the copy is in addition to the `before/` retrieve")
        # how to revert from Salesforce: open the copy, then Save As or move it back - one sentence
        revert = [s for s in self.clauses(part)
                  if re.search(r"(?i)\b(revert\w*|restor\w*|roll\w* back|undo)\b", s)
                  and re.search(r"(?i)\bopen\b[^.;]{0,30}?\bcopy\b", s)
                  and re.search(r"\bSave As\b", s) and re.search(r"(?i)\bmov\w*\b[^.;]{0,30}?\bback\b", s)
                  and not self.denies(s)]
        self.assertTrue(revert, f"{where}: say how to revert from Salesforce (\"To revert, open the copy, then Save As "
                                "or move it back\"), in one sentence")
        self.assertNoContradiction(part, where, share=True)

    # --- the interactive dashboard --------------------------------------------------------------------

    def test_the_interactive_dashboard_section_names_its_code(self):
        where = f"RUNBOOK section {self.INTERACTIVE[3:]!r}"
        text = self.norm(self.interactive())
        self.assertIn("glowDashboardShell", text, f"{where}: name the LWC `glowDashboardShell`")
        self.assertIn("GlowTilesController", text, f"{where}: name the controller `GlowTilesController`")
        self.assertNotRegex(text, r"\bGlowTilesController\b(?!Test)[^.;]{0,20}\bnot\b",
                            f"{where}: name `GlowTilesController` as the controller, not as absent")
        self.assertNoContradiction(self.interactive(), where)

    def test_the_interactive_dashboard_section_says_where_and_since_when(self):
        where = f"RUNBOOK section {self.INTERACTIVE[3:]!r}"
        text = self.norm(self.interactive())
        self.assertIn("GlowDemoController", text, f"{where}: name the other controller `GlowDemoController`")
        # its host is the Lightning tab (CustomTab) `Glow_Interactive_Dashboard`, said as such, not negated
        # (a mention of a Lightning page or FlexiPage proves nothing: "no FlexiPage embeds the LWC")
        self.assertTrue([s for s in self.clauses(text) if "Glow_Interactive_Dashboard" in s
                         and re.search(r"(?i)\b(Lightning\s+)?tab\b|\bCustomTab\b", s) and not self.denies(s)],
                        f"{where}: say where it is hosted - the tab (CustomTab) `Glow_Interactive_Dashboard`, in a "
                        "sentence that is not negated")
        self.assertRegex(text, r"data/sf_reporting_\d{4}-\d\d-\d\d/before/",
                         f"{where}: name the retrieve folder `data/sf_reporting_<date>/before/`")
        self.assertTrue([s for s in self.clauses(text) if "2026-01-04" in s and re.search(r"(?i)\bunchanged\b|"
                         r"\blast modified\b|\bnot (been )?changed\b", s)],
                        f"{where}: its status - unchanged since 2026-01-04")
        self.assertRegex(text, r"(?i)\bnot in git\b|\bnot (kept |tracked |stored )?in (the )?(repo|repository|git)\b|"
                               r"\bonly in the org\b|\blives? (only )?in the org\b",
                         f"{where}: say its code is not in git (it lives only in the org)")
        # a change to it goes through the metadata ritual, never an edit in the org
        for s in self.clauses(text):
            if re.search(r"(?i)\bdeveloper console\b|\bedit\w*\b[^.;]{0,30}\b(straight|directly)\s+in\s+the\s+org",
                         s):
                self.assertTrue(self.denies(s), f"{where}: an edit in the org is not how it changes: {s[:160]!r}")
        self.assertNoContradiction(self.interactive(), where)

    # --- the plan ---------------------------------------------------------------------------------------

    def test_a_plan_carries_the_folder_deploy_and_the_api_proof(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        text = read(path)
        keys, _ = docs_index.frontmatter(text)
        self.assertIn("status", keys, f"{name}: frontmatter `status:`")
        word, problem = docs_index.status_of(keys["status"])
        self.assertIsNone(problem, f"{name}: {problem}")
        self.assertNotEqual(word, "superseded", f"{name}: the plan is the change in force")
        if word == "done":
            self.assertRegex(keys.get("done", ""), r"^\d{4}-\d\d-\d\d", f"{name}: a done plan carries `done:`")
        self.assertRegex(text.split("\n## ", 1)[0], self.TICKET,
                         f"{name}: name ticket #69 in the frontmatter, the title or the opening paragraph")
        self.assertRegex(text, r"(?m)^## Result\b", f"{name}: no `## Result` section")
        bodies, raw = {}, {}
        for heading, least in (("## Rollout", 40), ("## Rollback", 15), ("## Inventory", 15), ("## API proof", 20)):
            part = md_part(path, heading)
            raw[heading] = part.split("\n", 1)[1] if "\n" in part else ""
            body = self.norm(raw[heading])
            self.assertNotRegex(body, r"(?i)\b(TBD|TODO|TBA|FIXME)\b", f"{name}: `{heading}` is a placeholder")
            distinct = {w.lower() for w in re.findall(r"[A-Za-z]\w*", body)}
            self.assertGreaterEqual(len(distinct), least,
                                    f"{name}: `{heading}` says too little (at least {least} distinct words)")
            bodies[heading] = body
        rollout, rollback = bodies["## Rollout"], bodies["## Rollback"]
        self.assertIn("Decommissioned", rollout, f"{name}: the Rollout creates the Decommissioned folders")
        self.assertTrue([s for s in sentences(rollout, ".;") if re.search(r"(?i)(check-only|--dry-run)[^.;]*?\bdeploy", s)
                         and not self.denies(s)],
                        f"{name}: the Rollout validates check-only before it deploys (one sentence, in that order)")
        self.assertRegex(rollout, r"Ryan['’]s go\b", f"{name}: the Rollout's deploy waits for Ryan's go")
        self.assertRegex(rollout, r"(?i)read (it |them )?back|retriev",
                         f"{name}: the Rollout reads the folders back (retrieve and compare)")
        self.assertRegex(rollout, self.SHARES_API,
                         f"{name}: the Rollout confirms with the shares API that neither folder has a share")
        self.assertRegex(rollout, r"(?i)\bclon\w*\b|cloneId",
                         f"{name}: the Rollout carries the API proof (clone and move a report and a dashboard)")
        self.assertNoContradiction(raw["## Rollout"], f"{name}: `## Rollout`")
        self.assertIn("Decommissioned", rollback, f"{name}: the Rollback says what becomes of the Decommissioned "
                                                  "folders and the two proof clones")
        self.assertNoContradiction(raw["## Rollback"], f"{name}: `## Rollback`", rollback=True)
        # the API proof gives each request's form: the clone, then the move with the folder id
        proof_lines = [self.norm(x) for x in raw["## API proof"].split("\n")]
        for kind in ("reports", "dashboards"):
            self.assertTrue([x for x in proof_lines if re.search(r"\bPOST\s+\S*/analytics/" + kind + r"\?cloneId=", x)],
                            f"{name}: `## API proof` gives the clone request `POST …/analytics/{kind}?cloneId=<id>`")
            self.assertTrue([x for x in proof_lines if re.search(r"\bPATCH\s+\S*/analytics/" + kind + r"/\S+", x)
                             and "folderId" in x],
                            f"{name}: `## API proof` gives the move request `PATCH …/analytics/{kind}/<id>` with "
                            "`folderId`, on one line")
        self.assertRegex(bodies["## API proof"], r"(?i)\bMove\b[^.;]{0,40}\b(by hand|Lightning)\b|"
                                                 r"\bLightning\b[^.;]{0,40}\bMove\b",
                         f"{name}: `## API proof` names the fallback if the API refuses (Lightning's Move, by Ryan)")
        self.assertIn("glowDashboardShell", bodies["## Inventory"],
                      f"{name}: `## Inventory` covers the interactive dashboard (`glowDashboardShell`)")

    # --- DECISIONS and the skill ------------------------------------------------------------------------

    def test_a_decision_records_archive_not_delete(self):
        e = self.decision()
        where = f"docs/DECISIONS.md {e.split(chr(10), 1)[0][4:14]}"
        for part in ("**Why", "**Rejected", "**Consequences"):
            self.assertIn(part, e, f"{where}: no {part}** bullet (the file's header)")
        self.assertRegex(e, self.TICKET, f"{where}: name ticket #69")
        why = e.split("**Why", 1)[1].split("**Rejected", 1)[0]
        self.assertRegex(why, r"\bRyan\b", f"{where}: **Why** gives Ryan's words")
        self.assertRegex(self.norm(why), r"(?i)in case we need to revert",
                         f"{where}: **Why** quotes Ryan (\"in case we need to revert any changes\")")
        rejected = self.norm(e.split("**Rejected", 1)[1].split("**Consequences", 1)[0])
        self.assertRegex(rejected, r"(?i)\bdelet\w*\b[^.;]{0,40}?\b(reports?|dashboards?)\b",
                         f"{where}: **Rejected** names deleting the reports and dashboards")
        self.assertRegex(rejected, r"(?i)\barchiv\w*\b[^.;]{0,20}?\bonly in\b[^.;]{0,5}?`?data/",
                         f"{where}: **Rejected** names an archive only in `data/` (Salesforce users cannot reach it)")
        flat_e = self.norm(e)
        self.assertTrue([s for s in sentences(flat_e, ".;") if re.search(r"(?i)\bcop(y|ies)\b", s)
                         and re.search(r"(?i)\bbefore\b", s) and re.search(r"(?i)\bchang\w*\b", s)
                         and not self.denies(s)],
                        f"{where}: the decision says a copy goes to Decommissioned before each change")
        self.assertTrue([s for s in sentences(flat_e, ".;") if re.search(r"(?i)\bmov\w*\b", s)
                         and re.search(r"\bId\b", s) and not self.denies(s)],
                        f"{where}: the decision says a retired report or dashboard is moved and keeps its Id")
        # the Rejected bullet names what was rejected (deleting); the rest of the entry must not contradict the rule
        rest = re.sub(r"(?ms)^- \*\*Rejected.*?(?=^- \*\*|\Z)", "", e)
        self.assertNoContradiction(rest, where)

    def test_the_salesforce_skill_points_at_both_sections(self):
        item = self.skill_item()
        where = ".claude/skills/salesforce/SKILL.md, Reports and dashboards"
        text = flat(item)
        for title in (self.MONTHLY[3:], self.INTERACTIVE[3:], "Attendance dashboard in Salesforce"):
            self.assertRegex(text, r"[\"“]" + re.escape(title) + r"[\"”]",
                             f"{where}: name the RUNBOOK section {title!r} in double quotes")
        self.assertIn("Decommissioned", text, f"{where}: state the archive rule (moved to Decommissioned)")
        self.assertRegex(text, r"(?i)\bnever deleted\b|\bnot deleted\b|\bnothing is deleted\b|\bnever delete\b",
                         f"{where}: the archive rule says nothing is deleted")
        self.assertTrue([s for s in self.clauses(item) if re.search(r"(?i)\bcop(y|ies)\b", s)
                         and re.search(r"(?i)\bbefore\b", s) and re.search(r"(?i)\bchang\w*\b", s)
                         and not self.denies(s)],
                        f"{where}: the archive rule says a copy goes to Decommissioned before each change (one "
                        "sentence, not negated)")
        self.assertNoContradiction(item, where, share=True)


class KeepListDocs(unittest.TestCase):
    """Ticket #70: GLOW's keep list (`glow/sf_keep_list.csv`, test/sf_keep_list_test.py) in the RUNBOOK and
    DECISIONS, as Ryan answered on the ticket, 2026-10-23: the 19 items in five dashboards and one table, every
    kept report by Partner and Month (Ryan, 2026-10-21); the labels unchanged ("Kept reports and dashboards keep
    their current names"); everything off the list goes to Decommissioned and is kept there; the test-record
    rule is the report filter `Account is not blank AND Account: Account Name does not contain "test"`, not
    `Partner_Status__c`. Each rule must be stated as the rule: not negated, rejected, renamed or put off (#69's
    `locally_denied` and `contradictions`)."""

    longMessage = False         # the messages say what to fix
    RUNBOOK = os.path.join(REPO, "docs", "RUNBOOK.md")
    DECISIONS = os.path.join(REPO, "docs", "DECISIONS.md")
    MONTHLY = "## Monthly Report dashboards in Salesforce"
    KEEP = "### The keep list"
    TICKET = re.compile(r"(?<![\w#])#70\b")
    GROUPS = ("GLOW Club Attendance", "GLOW Club Implementation", "GLOW Club Observations", "GLOW Club Training",
              "GLOW Club Reporting")
    NEGATION = DecommissionedFoldersDocs.NEGATION
    RYAN = "This data should be displayed by the Partner and Month"     # Ryan, 2026-10-21, verbatim

    # the rule, in either order of its two conditions, quotes straight or curly
    NOT_BLANK = re.compile(r"(?i)`?Account`?\s+(is\s+)?not\s+blank\b|`?Account`?\s+(is\s+)?not\s+(empty|null)\b|"
                           r"`?Account`?\s*(!=|≠|<>)\s*(blank|null|['\"]{2})")
    NO_TEST = re.compile(r"(?i)\bAccount Name`?\s+does\s+not\s+contain\s+[`\"“']+test[`\"”']+")
    # words that make the rule a rejected one, before it ("A rejected filter: …", "we dropped …") ...
    REJECT = re.compile(r"(?i)\b(reject\w*|dropped|dropping|discard\w*|abandon\w*|withdr[ae]w\w*|superseded|"
                        r"instead|cannot|wrong|replac\w*|retired)\b")
    # ... or after it ("… does not contain "test" was rejected")
    REJECTED_AFTER = re.compile(r"(?i)\b(is|are|was|were|been|be)\s+(\w+\s+)?(rejected|dropped|discarded|abandoned|"
                                r"replaced|superseded|wrong|withdrawn|not used|unused)\b|\brejected\b")
    # Partner_Status__c used as the rule ("use Partner_Status__c", "filter on Partner_Status__c")
    USES_STATUS = re.compile(r"(?i)\b(use|uses|using|used|filters?\s+(on|by)|filtered\s+(on|by)|rel(y|ies)\s+on|"
                             r"keyed\s+on|by|with)\s+`?Partner_Status__c")
    # why Partner_Status__c is rejected: blank on real partners too (it would drop real partners)
    STATUS_REASON = re.compile(r"(?i)\bblank\b[^.;]{0,80}?\breal partners?\b|"
                               r"\b(drops?|dropping|excludes?|excluding|loses?|hides?|removes?)\b[^.;]{0,30}?"
                               r"\breal partners?\b")
    # "keep their current names", "labels stay unchanged", "the labels are not changed", "do not change the labels"
    SAME_LABELS = re.compile(r"(?i)\bkeep(s|ing)?\b[^.;]{0,30}?\b(current|today['’]s|existing|own|present)\s+"
                             r"(labels?|names?)\b|\b(labels?|names?)\b[^.;]{0,40}?\b(unchanged|stay the same|"
                             r"(are|is|stay|stays)\s+as\s+(they|it)\s+(are|is)|(are|is)\s+(not|never)\s+(changed|renamed)|"
                             r"(do|does)\s+not\s+change|not\s+renamed|never\s+renamed)\b|"
                             r"\b(do|does|did|will)\s+not\s+change\s+(the|their|its|any)\s+(\w+\s+)?(labels?|names?)\b")
    # a label change stated as the plan ("rename all of them", "change the labels", "the names are changed")
    RENAME = re.compile(r"(?i)\b(renam\w*|re-?label\w*|chang(e|es|ed|ing)\s+(the\s+|their\s+|its\s+|a\s+|each\s+|"
                        r"every\s+|all\s+)?(\w+\s+)?(labels?|names?)|new\s+(labels?|names?))\b|"
                        r"\b(labels?|names?)\s+(will\s+be\s+|are\s+|is\s+|get\s+)?(chang(e|es|ed)|renamed|relabel\w*)\b")
    # what a rename is said of: an item ("item 17", "items 5-7"), a dashboard (D1-D5), many ("the dashboards", "the
    # reports", "the labels"), or item 17's new label. GLOW's review of 2026-11-02 (epic #194, ticket #200; the
    # RUNBOOK's keep-list paragraph that "supersedes that for item 17") renames item 17 only.
    RENAME_SUBJECT = re.compile(r"(?i)\bitems?\s+(?P<nums>\d+(\s*(,|and|&|-|–|to)\s*\d+)*)\b|\bD[1-5]\b|"
                                r"\b(dashboards|reports|labels|names|tables)\b|(?P<new>\bMonthly Report Approval Status\b)")

    def renames_item_17(self, s, m):
        """Rename match `m` of `s` is item 17's: the nearest subject before it in the sentence is item 17 (or its new
        label), or none is before it and the words after it, to the next comma or semicolon, name item 17; and no
        other item, dashboard or plural is named between that subject and the end of that clause."""
        before = list(self.RENAME_SUBJECT.finditer(s[:m.start()]))
        tail = re.split(r"[,;]", s[m.end():], maxsplit=1)[0]
        after = list(self.RENAME_SUBJECT.finditer(tail))

        def is_17(x):
            return bool(x.group("new")) or (x.group("nums") is not None
                                            and re.findall(r"\d+", x.group("nums")) == ["17"])
        if before:
            subject, between = before[-1], []
        elif after:
            subject, between = after[0], after[1:]
            after = []
        else:
            return False
        return is_17(subject) and all(is_17(x) for x in between + after)
    OFF_LIST = re.compile(r"(?i)\b(not on|off)\s+the\s+(keep\s+)?list\b")
    MOVED = re.compile(r"(?i)\b(goes|go|going|moved?|moves|moving|retired?)\s+(\w+\s+){0,3}?(to|into)\s+(the\s+)?"
                       r"[`\"“]?Decommissioned")
    KEPT_THERE = re.compile(r"(?i)\b(kept|stays?|remains?)\s+(\w+\s+)?there\b|"
                            r"\bkept\s+in\s+(the\s+)?[`\"“]?Decommissioned")
    # what puts the move off or makes it conditional ("only once Ryan asks", "until then it stays in place")
    DELAY = re.compile(r"(?i)\bonly\s+(once|if|when|after|on)\b|\buntil\b|\bunless\b|"
                       r"\b(stays?|remains?|left|leave|kept)\s+in\s+place\b|\bstays?\s+where\b|\beventually\b|"
                       r"\bwhen(ever)?\s+(Ryan|someone|asked|needed)\b|\bif\s+(Ryan|asked|needed|requested)\b|"
                       r"\bon request\b|\boptional\w*|\bmay\b|\bmight\b|\bcould\b|\bsomeday\b|\bone day\b|"
                       r"\bat some point\b|\bfor now\b|\bnot yet\b")
    STAY_PUT = re.compile(r"(?i)\b(stays?|remains?|left|leave|kept)\s+(\w+\s+)?in\s+place\b|"
                          r"\bstays?\s+where\s+(it|they)\s+(is|are)\b")
    EVERY_REPORT = re.compile(r"(?i)\b(every|each|all)\b[^.;]{0,60}?\breports?\b")
    NINETEEN = re.compile(r"(?i)\b19\s+(\w+\s+)?items\b")

    @classmethod
    def setUpClass(cls):
        cls.d = DecommissionedFoldersDocs()     # #69's helpers: locally_denied, contradictions

    @staticmethod
    def norm(text):
        return DecommissionedFoldersDocs.norm(text)

    def said(self, s, m):
        """Match `m` of clause `s` stated, not denied: no negation in the words before it (#69's
        `locally_denied`) and no "nothing", "none" or "no" right after it ("rename nothing")."""
        return not self.d.locally_denied(s, m) and not re.match(r"\s+(nothing|none|no)\b", s[m.end():])

    def stated(self, text, rx):
        """The clauses of `text` where `rx` is said, not denied."""
        return [s for s in sentences(text, ".;") if any(self.said(s, m) for m in rx.finditer(s))]

    def keep_part(self):
        """The `### The keep list` part of the Monthly Report section, to the next `###` or `##`."""
        section = md_part(self.RUNBOOK, self.MONTHLY)
        m = re.search(r"^" + re.escape(self.KEEP) + r"(?!\w).*$", section, re.M)
        self.assertTrue(m, f"RUNBOOK section {self.MONTHLY[3:]!r}: no `{self.KEEP}` part under it")
        rest = section[m.start():]
        nxt = re.search(r"\n#{1,3} ", rest)
        return rest[:nxt.start()] if nxt else rest

    def decision(self):
        entries = re.split(r"(?m)^(?=### )", read(self.DECISIONS))[1:]
        new = [e for e in entries if re.match(r"### (\d{4}-\d\d-\d\d) ", e)
               and re.match(r"### (\d{4}-\d\d-\d\d) ", e).group(1) >= "2026-10-21"
               and re.search(r"(?i)\bkeep list\b", e.split("\n", 1)[0])]
        self.assertTrue(new, "docs/DECISIONS.md: no dated entry (`### 2026-10-2x — GLOW's keep list: 19 items in five "
                             "dashboards and one table; every kept report by Partner and Month`) whose heading names "
                             "the keep list")
        self.assertEqual(len(new), 1, "docs/DECISIONS.md: one dated entry on the keep list, not "
                                      f"{len(new)}")
        return new[0]

    # --- the rules, shared by the RUNBOOK and the DECISIONS checks ------------------------------------------

    def assertTestRecordRule(self, text, where):
        """The rule stated in one clause, as a report filter, not rejected or dropped and without
        `Partner_Status__c`; `Partner_Status__c` named only where it is denied, never used."""
        rules = [s for s in sentences(text, ".;") if self.NOT_BLANK.search(s) and self.NO_TEST.search(s)]
        self.assertTrue(rules, f"{where}: state the test-record rule in one sentence: `Account is not blank AND "
                               "Account: Account Name does not contain \"test\"`")
        for s in rules:             # every statement of it, so a rejected one cannot sit beside a stated one
            a, b = self.NOT_BLANK.search(s), self.NO_TEST.search(s)
            pre, post = s[:min(a.start(), b.start())], s[max(a.end(), b.end()):]
            self.assertFalse(self.NEGATION.search(pre) or self.REJECT.search(pre) or self.REJECTED_AFTER.search(post)
                             or "Partner_Status__c" in s,
                             f"{where}: the test-record rule is stated as the rule (Ryan, 2026-10-23), not negated, "
                             f"rejected or dropped, and `Partner_Status__c` is not in its sentence: {s[:200]!r}")
        self.assertTrue([s for s in rules if re.search(r"(?i)\bfilters?\b", s)],
                        f"{where}: the test-record rule is a report filter (say so in its sentence)")
        for s in sentences(text, ".;"):
            if "Partner_Status__c" not in s:
                continue
            used = [m for m in self.USES_STATUS.finditer(s) if self.said(s, m)]
            self.assertFalse(used or not (self.NEGATION.search(s) or self.REJECT.search(s)),
                             f"{where}: `Partner_Status__c` is not the test-record rule (Ryan, 2026-10-23); name it "
                             f"only to say it is not used: {s[:200]!r}")

    def assertSameLabels(self, text, where):
        self.assertTrue(self.stated(text, self.SAME_LABELS),
                        f"{where}: say kept reports and dashboards keep their current names (labels unchanged, Ryan "
                        "2026-10-23), not negated")
        for s in sentences(text, ".;"):
            for m in self.SAME_LABELS.finditer(s):      # "never keep their current names"
                self.assertFalse(m.group(0).lower().startswith("keep") and not self.said(s, m),
                                 f"{where}: kept reports and dashboards keep their current names (Ryan, 2026-10-23), "
                                 f"not negated: {s[:200]!r}")
            for m in self.RENAME.finditer(s):
                if self.renames_item_17(s, m):
                    continue    # item 17's rename (GLOW's review, epic #194, ticket #200): the exception may say so
                self.assertFalse(self.said(s, m), f"{where}: the labels are not changed (Ryan, 2026-10-23); a rename "
                                                  "or relabel is only ever denied (`not renamed`, `nothing is "
                                                  f"relabelled`): {s[:200]!r}")

    def assertOffListDecommissioned(self, text, where):
        """Everything off the list goes to Decommissioned and is kept there: said in one clause, and no
        clause about the off-list or Decommissioned puts it off, makes it conditional or softens it."""
        for s in sentences(text, ".;"):                 # "until then it stays in place", wherever it is said
            for m in self.STAY_PUT.finditer(s):
                self.assertFalse(self.said(s, m), f"{where}: what is off the keep list goes to Decommissioned, it "
                                                  f"does not stay in place: {s[:200]!r}")
        good = []
        for s in sentences(text, "."):                  # whole sentences: a "; until …" tail belongs to the rule
            if not (self.OFF_LIST.search(s) or "Decommissioned" in s):
                continue
            plain = self.OFF_LIST.sub(" ", s)       # "not on the list" is the subject, not a denial
            delay = [m.group(0) for m in self.DELAY.finditer(plain) if self.said(plain, m)]
            self.assertEqual(delay, [], f"{where}: what is off the keep list goes to Decommissioned now and stays "
                                        f"there, with no condition or delay ({delay[:1]}): {s[:200]!r}")
            found = self.d.contradictions(plain)
            self.assertEqual(found, [], f"{where}: contradicts the rules (moved to Decommissioned, never deleted, "
                                        "never optional): " + "; ".join(found))
            if (self.OFF_LIST.search(s) and any(self.said(plain, m) for m in self.MOVED.finditer(plain))
                    and any(self.said(plain, m) for m in self.KEPT_THERE.finditer(plain))):
                good.append(s)
        self.assertTrue(good, f"{where}: say, in one sentence, every report and dashboard not on the keep list goes to "
                              "Decommissioned and is kept there (Ryan, 2026-10-23)")

    def assertPartnerAndMonth(self, text, where):
        said = [s for s in self.stated(text, re.compile(r"\bPartner and Month\b")) if self.EVERY_REPORT.search(s)]
        self.assertTrue(said, f"{where}: say every kept report is by Partner and Month, in one sentence, not negated")

    @staticmethod
    def in_dashboard_context(part, name):
        """`name` on a line that says dashboard, or in a list or table under a line (or header row) that does."""
        lead = block = ""
        for line in part.splitlines():
            st = line.strip()
            if not st:
                continue
            if not re.match(r"([-*+]|\d+\.)\s|\|", st):
                lead, block = st, ""
            elif not block:
                block = st
            if name in line and re.search(r"(?i)\bdashboards?\b", " ".join((line, block, lead))):
                return True
        return False

    # --- the tests -------------------------------------------------------------------------------------------

    def test_the_runbook_states_the_keep_list_and_the_test_record_rule(self):
        where = f"RUNBOOK section {self.MONTHLY[3:]!r}, {self.KEEP[4:]!r}"
        part = self.keep_part()
        text = self.norm(part)
        self.assertIn("glow/sf_keep_list.csv", part, f"{where}: name the file `glow/sf_keep_list.csv`")
        for group in self.GROUPS:
            self.assertTrue(self.in_dashboard_context(part, group),
                            f"{where}: name the group {group!r} as a dashboard (on a line that says dashboard, or in a "
                            "list or table under one)")
        self.assertRegex(text, r"(?i)\bGLOW of the Month Stories\b", f"{where}: name the table, item 19 \"GLOW of "
                                                                      "the Month Stories\"")
        self.assertTrue(self.stated(text, self.NINETEEN), f"{where}: say the list has 19 items (`19 items`)")
        self.assertPartnerAndMonth(text, where)
        self.assertRegex(text, r"(?i)\btest records?\b", f"{where}: call what the rule excludes test records")
        self.assertTestRecordRule(text, where)
        self.assertSameLabels(text, where)
        self.assertOffListDecommissioned(text, where)

    def test_a_decision_records_the_keep_list(self):
        e = self.decision()
        where = f"docs/DECISIONS.md {e.split(chr(10), 1)[0][4:14]}"
        for part in ("**Why", "**Rejected", "**Consequences"):
            self.assertIn(part, e, f"{where}: no {part}** bullet (the file's header)")
        self.assertRegex(e, self.TICKET, f"{where}: name ticket #70")
        flat_e = self.norm(e)
        self.assertRegex(flat_e, r"\b19 items\b", f"{where}: say the list is 19 items")
        self.assertRegex(flat_e, r"(?i)\bfive dashboards\b", f"{where}: say the 19 items are in five dashboards")
        self.assertIn("glow/sf_keep_list.csv", e, f"{where}: name the file `glow/sf_keep_list.csv`")
        why = self.norm(e.split("**Why", 1)[1].split("**Rejected", 1)[0])
        self.assertTrue([m for m in re.finditer(re.escape(self.RYAN), why) if self.said(why, m)],
                        f"{where}: **Why** quotes Ryan verbatim, not negated: \"{self.RYAN}.\"")
        # everything outside **Rejected** states the agreed rules as rules
        rest = self.norm(re.sub(r"(?ms)^- \*\*Rejected.*?(?=^- \*\*|\Z)", "", e))
        self.assertPartnerAndMonth(rest, where)
        self.assertTestRecordRule(rest, where)
        self.assertSameLabels(rest, where)
        self.assertOffListDecommissioned(rest, where)
        rejected = self.norm(e.split("**Rejected", 1)[1].split("**Consequences", 1)[0])
        self.assertTrue([s for s in sentences(rejected, ".;") if "Partner_Status__c" in s
                         and self.STATUS_REASON.search(s)],
                        f"{where}: **Rejected** names `Partner_Status__c` with its reason, in one sentence: blank on "
                        "real partners too (it would drop real partners)")
        self.assertRegex(rejected, r"(?i)\b(new\s+(\w+\s+)?(field|checkbox)|Obsolete_Record__c)\b",
                         f"{where}: **Rejected** names a new test-record field or reusing `Obsolete_Record__c` (a "
                         "field or record writes)")
        self.assertFalse([s for s in sentences(rejected, ".;") if self.NOT_BLANK.search(s) and self.NO_TEST.search(s)],
                         f"{where}: the agreed test-record rule is not under **Rejected**")


class RetiredReportsDocs(unittest.TestCase):
    """Ticket #72: the reports and dashboards off the keep list moved to Decommissioned, live 2026-10-23..24 on
    Ryan's go (the ticket's comments): 29 reports by `tools/sf_report_folders.py` (27 of the 46 retiring in
    "DHIS2 Reports", the other 19 held there for #75-#79 because kept dashboards use them, and 2 from "Public
    Reports"), the ledger `data/sf_retire_2026-10-23/ledger.csv`; 10 dashboards moved by hand in Lightning (not in
    the ledger). The RUNBOOK's `### Decommissioned` records it and how to bring an item back; the plan
    `docs/plans/<date>-sf-retire-reports.md` carries the Rollout, a Rollback that is the tool's undo (nothing is
    deleted) and the Result. The tool's undo reads only `ledger.csv` in its `--dir`, so a command that brings the
    retirement back names `--dir data/sf_retire_2026-10-23`."""

    longMessage = False         # the messages say what to fix
    RUNBOOK = os.path.join(REPO, "docs", "RUNBOOK.md")
    PLANS = os.path.join(REPO, "docs", "plans", "*-sf-retire-reports.md")
    TICKET = re.compile(r"(?<![\w#])#72\b")
    RETIRE_DIR = "data/sf_retire_2026-10-23"
    LEDGER = RETIRE_DIR + "/ledger.csv"
    DATE = re.compile(r"\b2026-10-2[34]\b")                 # the moves ran 2026-10-23 and 2026-10-24
    MOVED = re.compile(r"(?i)\b(mov(e|ed|es|ing)|retired)\b")
    REPORTS_29 = re.compile(r"(?i)\b29\s+(\w+\s+){0,3}?reports?\b")
    DASHBOARDS_10 = re.compile(r"(?i)\b(10|ten)\s+(\w+\s+){0,3}?dashboards?\b")
    HELD_19 = re.compile(r"(?i)\b19\s+(\w+\s+){0,3}?reports?\b")
    SOQL = re.compile(r"(?i)\bSOQL\b|\bSELECT\b[^.;]{0,80}?\bFROM\s+(Report|Dashboard)\b")
    IN_DECOM = re.compile(r"\bFolderName\s*=\s*['‘’]Decommissioned['‘’]")
    BY_HAND = re.compile(r"(?i)\bby hand\b|\bLightning\b")
    MOVE_VERB = re.compile(r"(?i)\bmov(e|ed|es|ing)\b")
    # a folder a dashboard goes to or comes back to
    FOLDER = re.compile(r"(?i)\bfolders?\b|\bDecommissioned\b|\bDHIS2 Dashboards\b|\bDhis2 Dashbords\b")
    # the retired dashboards left where they were ("the dashboards stay where they are")
    DASHBOARDS_STAY = re.compile(r"(?i)\b(the|retired|retiring|10|ten|these|those|each|all|every)\s+(\w+\s+)?"
                                 r"dashboards?\s+(\w+\s+){0,2}?(stay|stays|stayed|remain|remains|remained|are left|"
                                 r"were left)\b|\bdashboards?\b[^.;]{0,40}?\bwhere (they|it) (are|is|were|was)\b")
    # what makes a factual statement a guess
    HEDGE = re.compile(r"(?i)\b(rumou?r\w*|maybe|perhaps|possibly|probably|presumably|supposedly|allegedly|"
                       r"reportedly|apparently|may or may not|might or might not|some ?day|assum\w*|in some sense|"
                       r"somewhere|of something|(is|are)\s+(just\s+)?(a\s+)?words?|nice idea|ignored|in theory|"
                       r"unverified|hopefully|guess\w*|in truth)\b")
    # the moves' counts (the ticket's comments, 2026-10-23..24): reports moved 29 = 27 + 2 (plan_1 10, plan_2
    # 17, --limit 1 one); dashboards moved 10; reports left 19 held + 17 kept = 36; dashboards left the 5 kept
    COUNT = re.compile(r"(?i)(?<![\w#.\-/])(\d+)\s+((?:[\w\"“”'’-]+\s+){0,3}?)(reports?|dashboards?|rows?)\b")
    MOVED_WORD = re.compile(r"(?i)\bmov(e|ed|es|ing)\b|\bretired\b|\bto\s+[\"“]?Decommissioned\b")
    LEFT_WORD = re.compile(r"(?i)\b(remain\w*|stay\w*|held|left|kept)\b")
    MOVED_COUNTS = {"report": {29, 27, 2, 10, 17, 1}, "dashboard": {10, 1}}
    LEFT_COUNTS = {"report": {19, 17, 36}, "dashboard": {5, 0}}
    ROWS = re.compile(r"(?i)\b31\s+(\w+\s+){0,2}?rows\b")
    ROW_COUNTS = {31, 2}
    # a second row, Decommissioned to Decommissioned: the full --apply run re-moved the row --limit 1 had moved
    NOOP_ROWS = ("00ORP000005rT932AE", "00ORP000005gxSD2AY")
    MOVE_CMD = re.compile(r"\bpython3\s+(\S*/)?sf_report_folders\.py\s+(move|undo)\b")

    @classmethod
    def setUpClass(cls):
        cls.d = DecommissionedFoldersDocs()     # #69's helpers: decommissioned(), contradictions, locally_denied

    @staticmethod
    def norm(text):
        return DecommissionedFoldersDocs.norm(text)

    def stated(self, s, rx):
        """`rx` said in clause `s`, not denied in the words before it."""
        return any(not self.d.locally_denied(s, m) for m in rx.finditer(s))

    def commands(self, raw, verb=None):
        """Each runnable `python3 …sf_report_folders.py move|undo …` command in `raw` (inline code, a fenced
        line), flattened, in order; with `verb`, only that subcommand. An inline span wrapped over a line break
        stays one command."""
        segments = re.split(r"`+|\n\s*\n|\n(?=\s*(?:\$\s*)?python3\s)|(?=\bpython3\s)", raw)
        out = []
        for seg in segments:
            m = self.MOVE_CMD.search(flat(seg))
            if m and (verb is None or m.group(2) == verb):
                out.append(flat(seg)[m.start():])
        return out

    @staticmethod
    def flag(cmd, name):
        """The values of `--name` in `cmd`, quotes and a trailing `/` stripped."""
        return [v.strip("`'\"").rstrip("/") for v in re.findall(r"--" + name + r"(?:=|\s+)(\S+)", cmd)]

    def assertCommandsUseTheDir(self, raw, where):
        """Every move and undo command runs with `--vpn-off` and `--dir` the retirement's folder and no other `--dir`
        (the tool writes and reads `ledger.csv` there, and undo refuses any other ledger); a `--ledger` is that
        folder's `ledger.csv`; a `--plan` is a CSV in that folder."""
        for c in self.commands(raw):
            self.assertIn("--vpn-off", c, f"{where}: the tool refuses to run without `--vpn-off`: {c[:160]!r}")
            dirs = self.flag(c, "dir")
            self.assertTrue(dirs and set(dirs) == {self.RETIRE_DIR},
                            f"{where}: every move and undo of this retirement runs with `--dir {self.RETIRE_DIR}` and no "
                            f"other `--dir` (its ledger is `{self.LEDGER}`): {c[:160]!r}")
            for v in self.flag(c, "ledger"):
                self.assertEqual(v, self.LEDGER, f"{where}: undo reads only `ledger.csv` in its `--dir`; the ledger "
                                                 f"is `{self.LEDGER}`: {c[:160]!r}")
            for v in self.flag(c, "plan"):
                self.assertRegex(v, r"^" + re.escape(self.RETIRE_DIR) + r"/[\w.-]+\.csv$",
                                 f"{where}: a move's `--plan` is a CSV in `{self.RETIRE_DIR}/`: {c[:160]!r}")

    def assertUndoFromTheLedger(self, raw, where):
        """A dry run of the tool's undo for this retirement: `--vpn-off`, `--dir` the retirement's folder, no
        `--apply`; and every move and undo command uses that folder."""
        cmds = self.commands(raw, "undo")
        self.assertTrue(cmds, f"{where}: give the command `python3 tools/sf_report_folders.py undo --vpn-off --dir "
                              f"{self.RETIRE_DIR}`")
        self.assertCommandsUseTheDir(raw, where)
        self.assertTrue([c for c in cmds if "--apply" not in c],
                        f"{where}: the undo's dry run, on one line: `python3 tools/sf_report_folders.py undo --vpn-off "
                        f"--dir {self.RETIRE_DIR}` (no `--apply`)")

    def assertNoHedge(self, text, where):
        found = [f"{m.group(0)!r} in {s[:160]!r}" for s in sentences(self.norm(text), ".;:")
                 for m in [self.HEDGE.search(s)] if m]
        self.assertEqual(found, [], f"{where}: a record of what was done states it, it does not guess: " + "; ".join(found))

    def assertNoDashboardsStay(self, text, where):
        for s in sentences(self.norm(text), ".;:"):
            for m in self.DASHBOARDS_STAY.finditer(s):
                self.assertFalse("kept" not in m.group(0).lower() and not self.d.locally_denied(s, m),
                                 f"{where}: the 10 retired dashboards moved to Decommissioned (by hand in Lightning); "
                                 f"they did not stay where they were: {s[:160]!r}")

    def assertCountsTrue(self, text, where):
        """Every "N reports|dashboards" said moved or left, and every "N rows", is one of the moves' counts."""
        bad = []
        for s in sentences(self.norm(text), ".;"):
            for m in self.COUNT.finditer(s):
                n, noun = int(m.group(1)), m.group(3).lower().rstrip("s")
                if noun == "row":
                    if n not in self.ROW_COUNTS:
                        bad.append(f"{n} rows: {s[:160]!r}")
                    continue
                around = s[max(0, m.start() - 25):m.start()] + " " + m.group(2) + " " + s[m.end():m.end() + 40]
                moved, left = self.MOVED_WORD.search(around), self.LEFT_WORD.search(around)
                ok = set()
                if moved:
                    ok |= self.MOVED_COUNTS[noun]
                if left:
                    ok |= self.LEFT_COUNTS[noun]
                if (moved or left) and n not in ok:
                    bad.append(f"{n} {noun}s: {s[:160]!r}")
        self.assertEqual(bad, [], f"{where}: a count that is not the moves' (29 reports and 10 dashboards moved, 19 "
                                  "held and 17 kept reports and 5 kept dashboards left, 31 ledger rows): "
                                  + "; ".join(bad))

    def retirement(self, text):
        """The sentences of `text` that say, not negated and not hedged, 29 reports and 10 dashboards moved
        to Decommissioned."""
        return [s for s in sentences(self.norm(text), ".;") if self.stated(s, self.MOVED)
                and self.REPORTS_29.search(s) and self.DASHBOARDS_10.search(s) and "Decommissioned" in s
                and not self.HEDGE.search(s)]

    def ledger_rows(self, text):
        """The sentences of `text` that give the ledger's 31 move rows with the 29 reports, not negated."""
        return [s for s in sentences(self.norm(text), ".;") if self.stated(s, self.ROWS) and self.REPORTS_29.search(s)
                and not self.HEDGE.search(s)]

    def back_by_hand(self, text):
        """The sentences of `text` that name a dashboard and, in one of their parts (cut at a colon: "the
        dashboards are not in the ledger: Ryan moves each back by hand to its old folder"), move it back by hand in
        Lightning to a folder, the "back" and the move not denied, nothing hedged."""
        back = re.compile(r"(?i)\bback\b")
        return [s for s in sentences(text, ".;") if re.search(r"(?i)\bdashboards?\b", s) and not self.HEDGE.search(s)
                and [p for p in re.split(r":\s", s) if self.BY_HAND.search(p) and self.stated(p, back)
                     and self.stated(p, self.MOVE_VERB) and self.FOLDER.search(p)]]

    def plan_path(self):
        found = sorted(glob.glob(self.PLANS))
        self.assertEqual(len(found), 1, "docs/plans/: one plan `YYYY-MM-DD-sf-retire-reports.md` for ticket #72 "
                                        f"(found {[os.path.basename(p) for p in found]})")
        self.assertRegex(os.path.basename(found[0]), r"^\d{4}-\d\d-\d\d-sf-retire-reports\.md$",
                         "docs/plans/: the plan is named `YYYY-MM-DD-sf-retire-reports.md`")
        return found[0]

    def plan_part(self, path, heading, least):
        """The body of `heading` in the plan, raw, after checking it says something."""
        name = os.path.relpath(path, REPO)
        part = md_part(path, heading)
        raw = part.split("\n", 1)[1] if "\n" in part else ""
        body = self.norm(raw)
        self.assertNotRegex(body, r"(?i)\b(TBD|TODO|TBA|FIXME)\b", f"{name}: `{heading}` is a placeholder")
        distinct = {w.lower() for w in re.findall(r"[A-Za-z]\w*", body)}
        self.assertGreaterEqual(len(distinct), least, f"{name}: `{heading}` says too little (at least {least} "
                                                      "distinct words)")
        return raw

    # --- the RUNBOOK ----------------------------------------------------------------------------------------

    def test_the_runbook_records_the_retirement_counts_and_ledger(self):
        where = f"RUNBOOK section {self.d.MONTHLY[3:]!r}, {self.d.DECOM[4:]!r}"
        part = self.d.decommissioned()          # the counts belong here, not anywhere in the RUNBOOK
        text = self.norm(part)
        clauses = sentences(text, ".;")
        # one sentence: when, what moved, how many of each
        said = [s for s in self.retirement(text) if self.DATE.search(s)]
        self.assertTrue(said, f"{where}: say, in one sentence (not negated, not hedged), the retirement's date "
                              "(2026-10-23..24), that it moved 29 reports and 10 dashboards to Decommissioned (\"On "
                              "2026-10-23 and 24, #72 moved 29 reports … and 10 dashboards to Decommissioned\")")
        self.assertTrue([s for s in clauses if "Public Reports" in s
                         and re.search(r"(?i)\b(2|two)\s+(\w+\s+){0,3}?reports?\b", s)
                         and re.search(r"(?i)\bfrom\b|\bmov\w*\b", s)],
                        f"{where}: say 2 of the 29 reports came from \"Public Reports\" (in one sentence)")
        self.assertTrue([s for s in clauses if self.HELD_19.search(s) and "DHIS2 Reports" in s
                         and re.search(r"#7[5-9]\b", s) and self.stated(s, self.LEFT_WORD)],
                        f"{where}: say the 19 retiring reports that kept dashboards still use stay in \"DHIS2 Reports\" "
                        "for #75-#79 (in one sentence)")
        self.assertIn(self.LEDGER, part, f"{where}: name the retirement's ledger `{self.LEDGER}`")
        self.assertTrue(self.ledger_rows(text),
                        f"{where}: say the ledger holds 31 move rows for the 29 reports (two reports have a second, "
                        "no-op row from Decommissioned to Decommissioned), in one sentence")
        # how to bring an item back: the reports by the tool's undo from that ledger, the dashboards by hand
        self.assertUndoFromTheLedger(part, where)
        self.assertTrue(self.back_by_hand(text),
                        f"{where}: say a retired dashboard is moved back by hand in Lightning to its old folder (Move), "
                        "in one sentence: the ledger holds only the reports")
        self.assertNoDashboardsStay(part, where)
        self.assertCountsTrue(part, where)
        self.assertNoHedge(part, where)
        self.d.assertNoContradiction(part, where, share=True)

    # --- the plan ---------------------------------------------------------------------------------------------

    def test_the_retirement_rollback_is_the_tools_undo(self):
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        where = f"{name}: `## Rollback`"
        raw = self.plan_part(path, "## Rollback", 15)
        body = self.norm(raw)
        self.assertUndoFromTheLedger(raw, where)
        self.assertTrue([c for c in self.commands(raw, "undo") if "--apply" in c],
                        f"{where}: after the dry run, the undo's own command with `--apply`: `python3 "
                        f"tools/sf_report_folders.py undo --vpn-off --dir {self.RETIRE_DIR} --apply`")
        self.assertTrue([s for s in sentences(body, ".;") if re.search(r"Ryan['’]s go\b", s)
                         and "--apply" in s and not self.HEDGE.search(s)],
                        f"{where}: the undo's `--apply` waits for Ryan's go (in one sentence)")
        self.assertTrue(self.back_by_hand(body),
                        f"{where}: the 10 dashboards are not in the ledger; say they are moved back by hand in "
                        "Lightning to their old folder")
        self.assertNoDashboardsStay(raw, where)
        self.assertNoHedge(raw, where)
        # it deletes nothing: said, and no step contradicts it
        self.assertTrue([s for s in sentences(body, ".;")
                         if re.search(r"(?i)\b(nothing|never|no\s+\w+)\b[^.;]{0,40}?\bdelet\w*", s)],
                        f"{where}: say nothing is deleted (\"nothing is deleted: the undo moves the reports back\")")
        for rx, what in ((r"destructiveChanges", "a `destructiveChanges` deploy"),
                         (r"\bsf project delete\b", "`sf project delete`"),
                         (r"(-X\s*|--method\s+)DELETE\b|\bDELETE\s+/services/", "an HTTP DELETE")):
            self.assertNotRegex(raw, rx, f"{where}: {what} deletes; the rollback is the tool's undo and deletes nothing")
        found = self.d.contradictions(raw)
        found += [f"says there is no rollback: {s[:160]!r}" for s in sentences(body, ".;:")
                  if self.d.NO_ROLLBACK.search(s)]
        self.assertEqual(found, [], f"{where}: contradicts the rule (the undo moves back, nothing is deleted, never "
                                    "optional): " + "; ".join(found))

    def test_a_plan_carries_the_moves(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        text = read(path)
        keys, _ = docs_index.frontmatter(text)
        self.assertIn("status", keys, f"{name}: frontmatter `status:`")
        word, problem = docs_index.status_of(keys["status"])
        self.assertIsNone(problem, f"{name}: {problem}")
        self.assertEqual(word, "done", f"{name}: the moves have run (2026-10-23..24): `status: done`")
        self.assertRegex(keys.get("done", ""), r"^2026-10-(2[3-9]|3[01])\b",
                         f"{name}: a done plan carries `done:` with the date the moves finished (2026-10-24 or later)")
        opening = text.split("\n## ", 1)[0]
        self.assertRegex(opening, self.TICKET,
                         f"{name}: name ticket #72 in the frontmatter, the title or the opening paragraph")
        self.assertNoHedge(opening.split("\n---\n", 1)[-1], f"{name}: the opening")
        flat_text = self.norm(text)
        self.assertTrue([s for s in sentences(flat_text, ".;") if re.search(r"(?i)\b46\s+(\w+\s+){0,3}?reports?\b", s)
                         and re.search(r"(?i)\bretir\w*", s) and not self.HEDGE.search(s)],
                        f"{name}: give the count of retiring reports in \"DHIS2 Reports\" (46 reports retiring), in one "
                        "sentence")
        self.assertTrue([s for s in sentences(flat_text, ".;") if re.search(r"(?i)\b17\s+(\w+\s+){0,3}?reports?\b", s)
                         and re.search(r"(?i)\bkept\b", s) and not self.HEDGE.search(s)],
                        f"{name}: give the count of kept reports staying (17 kept reports), in one sentence")

        # the Rollout: the dry run, then --limit 1 of the same plan on Ryan's go, the dashboards by hand, the SOQL check
        raw = self.plan_part(path, "## Rollout", 40)
        rollout = self.norm(raw)
        rclauses = sentences(rollout, ".;")
        where = f"{name}: `## Rollout`"
        self.assertRegex(rollout, r"(?i)\bdry[- ]run\b", f"{where} has the dry run (`move --vpn-off --plan …` without "
                                                         "`--apply`)")
        self.assertCommandsUseTheDir(raw, where)
        moves = self.commands(raw, "move")
        dry = [(i, self.flag(c, "plan")) for i, c in enumerate(moves) if self.flag(c, "plan") and "--apply" not in c]
        self.assertTrue(dry, f"{where} gives the dry run's command, `python3 tools/sf_report_folders.py move --vpn-off "
                             f"--plan {self.RETIRE_DIR}/<plan>.csv --dir {self.RETIRE_DIR}` without `--apply`")
        first = [(i, self.flag(c, "plan")) for i, c in enumerate(moves)
                 if "--apply" in c and self.flag(c, "limit") == ["1"] and self.flag(c, "plan")]
        self.assertTrue(first, f"{where} moves one report first: `… move … --apply --limit 1`, then reads it back")
        self.assertTrue([1 for i, p in first for j, q in dry if j < i and p == q],
                        f"{where}: the `--apply --limit 1` move runs the same `--plan` as a dry run before it")
        self.assertTrue([s for s in rclauses if re.search(r"Ryan['’]s go\b", s)
                         and re.search(r"--apply|--limit[ =]1\b", s) and not self.d.denies(s)
                         and not self.HEDGE.search(s)],
                        f"{where}: the `--apply` moves wait for Ryan's go (one sentence with Ryan's go and `--apply`)")
        self.assertTrue([s for s in rclauses if re.search(r"(?i)\bdashboards?\b", s) and self.BY_HAND.search(s)
                         and self.stated(s, self.MOVE_VERB) and self.FOLDER.search(s) and not self.HEDGE.search(s)],
                        f"{where}: the 10 dashboards are moved by hand in Lightning to Decommissioned (the API refuses "
                        "it), in one sentence")
        self.assertNoDashboardsStay(raw, where)
        self.assertIn("Monthly_Report_Dashboards", rollout,
                      f"{where}: the FlexiPage `Monthly_Report_Dashboards` loses the retiring dashboards' components "
                      "before they move")
        self.assertTrue([s for s in rclauses if self.SOQL.search(s) and self.IN_DECOM.search(s)
                         and re.search(r"\bId\b", s) and self.stated(s, self.SOQL)],
                        f"{where} checks by SOQL by Id that each item is in Decommissioned (`SELECT COUNT() FROM Report "
                        "WHERE Id IN (…) AND FolderName = 'Decommissioned'`), in one sentence")
        self.assertNoHedge(raw, where)
        self.d.assertNoContradiction(raw, where)

        # the Result: what moved, when, how many, the ledger's rows, checked by SOQL
        self.assertRegex(text, r"(?m)^## Result\b", f"{name}: no `## Result` section")
        result_raw = self.plan_part(path, "## Result", 15)
        result = self.norm(result_raw)
        where = f"{name}: `## Result`"
        self.assertRegex(result, self.DATE, f"{where} gives the dates of the moves (2026-10-23..24)")
        self.assertTrue(self.retirement(result),
                        f"{where}: say, in one sentence (not negated, not hedged), 29 reports and 10 dashboards moved to "
                        "Decommissioned")
        self.assertTrue([s for s in sentences(result, ".;") if self.HELD_19.search(s)
                         and self.stated(s, self.LEFT_WORD) and not self.HEDGE.search(s)],
                        f"{where} gives the 19 reports held in \"DHIS2 Reports\" (\"19 … reports stay …\")")
        self.assertIn(self.LEDGER, result_raw, f"{where} names the ledger `{self.LEDGER}`")
        self.assertTrue(self.ledger_rows(result),
                        f"{where}: say the ledger holds 31 move rows for the 29 reports, in one sentence")
        for rid in self.NOOP_ROWS:
            self.assertIn(rid, result_raw, f"{where}: name report {rid}, one of the two with a second, no-op row from "
                                           "Decommissioned to Decommissioned (the full `--apply` run's first PATCH "
                                           "moved its plan's first row, already moved by `--limit 1`, again)")
        soql = [s for s in sentences(result, ".;:") if self.SOQL.search(s)]
        self.assertTrue([s for s in sentences(result, ".;") if self.stated(s, self.SOQL) and "Decommissioned" in s],
                        f"{where} gives the SOQL read-back of Decommissioned, in one sentence")
        self.assertEqual([s for s in soql if not self.stated(s, self.SOQL)], [],
                         f"{where}: the SOQL read-back was run; no sentence denies it")
        self.assertNoDashboardsStay(result_raw, where)
        self.assertCountsTrue(result_raw, where)
        self.assertNoHedge(result_raw, where)
        self.d.assertNoContradiction(result_raw, where)


class CategoryFoldersDocs(unittest.TestCase):
    """Ticket #73: the kept reports and dashboards (`glow/sf_keep_list.csv`) go into their folders. Ryan,
    2026-10-21: ONE report folder and ONE dashboard folder, not eleven per-category folders; the five groups
    stay as categories (the RUNBOOK table's rows), and item 19 ("Report/Data Table Format") goes in the same
    report folder. The names proposed on the ticket: report folder "GLOW Monthly Reports" (`ReportFolder`
    `GLOW_Monthly_Reports`), dashboard folder "GLOW Monthly Dashboards" (`DashboardFolder`
    `GLOW_Monthly_Dashboards`). Ryan, 2026-10-23: labels do NOT change - no relabel step.

    The table's groups, dashboard labels and report counts are read from `glow/sf_keep_list.csv`, not pinned:
    a group's report count is its rows on GLOW's keep list that are not a dashboard, item 12 ("New mentors
    recruited", built into the folder by #80) included - the table describes GLOW's list (18
    reports in five dashboards, and the table), not what the org holds on one day."""

    longMessage = False         # the messages say what to fix
    RUNBOOK = os.path.join(REPO, "docs", "RUNBOOK.md")
    DECISIONS = os.path.join(REPO, "docs", "DECISIONS.md")
    KEEP_LIST = os.path.join(REPO, "glow", "sf_keep_list.csv")
    PLANS = os.path.join(REPO, "docs", "plans", "*-sf-category-folders.md")
    MONTHLY = "## Monthly Report dashboards in Salesforce"
    PART = "### The five dashboards and their folders"
    TICKET = re.compile(r"(?<![\w#])#73\b")
    GROUPS = KeepListDocs.GROUPS
    TABLE_GROUP = "Report/Data Table Format"
    # dashboards GLOW's review of 2026-11-02 renames (epic #194): item: the title since its ticket's deploy
    RENAMED_DASHBOARDS = {"D3": "Club Observation Dashboards"}      # #198
    REPORT_FOLDER, REPORT_DEV = "GLOW Monthly Reports", "GLOW_Monthly_Reports"
    DASH_FOLDER, DASH_DEV = "GLOW Monthly Dashboards", "GLOW_Monthly_Dashboards"
    DHIS2_FOLDERS = DecommissionedFoldersDocs.DHIS2_FOLDERS
    SHARES_API = DecommissionedFoldersDocs.SHARES_API
    NEGATION = DecommissionedFoldersDocs.NEGATION
    SF_ID = re.compile(r"\b0[0-9A-Z]{2}[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\b")
    # a share outside the org: only ever denied ("Partner and Month" is a grouping, not a share)
    OUTSIDE = re.compile(r"(?i)\b(guest|portal|community|external|sharing\s+sets?|partners?(?!\s+(and|&)\s+month))\b")
    # what puts a rule off or makes it temporary or optional, beyond #69's SOFTENER
    SOFT_TIME = re.compile(r"(?i)\b(at first|for now|initially|to begin with|temporar\w*|for the time being|may|might|"
                           r"could|now and then|from time to time|occasionally|eventually|later|someday|at some point|"
                           r"until|not yet)\b")
    # what makes a check an assumption
    ASSUMED = re.compile(r"(?i)\b(assum\w*|presum\w*|suppos\w*|believ\w*|probably|likely)\b")

    @classmethod
    def setUpClass(cls):
        cls.d = DecommissionedFoldersDocs()     # #69's helpers: locally_denied, contradictions, denies
        KeepListDocs.setUpClass()
        cls.k = KeepListDocs()                  # #70's helpers: assertSameLabels, stated

    @staticmethod
    def norm(text):
        return DecommissionedFoldersDocs.norm(text)

    def clauses(self, text, ends=".;"):
        return sentences(self.norm(text), ends)

    def keep_rows(self):
        import csv
        with open(self.KEEP_LIST, encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    def part(self):
        """The `### The five dashboards and their folders` part of the Monthly Report section."""
        section = md_part(self.RUNBOOK, self.MONTHLY)
        m = re.search(r"^" + re.escape(self.PART) + r"(?!\w).*$", section, re.M)
        self.assertTrue(m, f"RUNBOOK section {self.MONTHLY[3:]!r}: no `{self.PART}` part under it (ticket #73)")
        rest = section[m.start():]
        nxt = re.search(r"\n#{1,3} ", rest)
        return rest[:nxt.start()] if nxt else rest

    @classmethod
    def cell(cls, text):
        """A table cell's text: backticks, quotes, bold and Salesforce ids stripped."""
        text = re.sub(r"\(\s*\)", "", cls.SF_ID.sub("", re.sub(r"[`\"“”*]", "", text)))
        return flat(text).strip().rstrip(".,;").strip()

    def assertOnlyDenied(self, text, where):
        """A guest, portal, community, partner or external share, or a sharing set, only ever denied: a negation
        before it in its clause, and no "but" (or "however", "except", "yet") between."""
        for s in self.clauses(text, ".;:?!"):
            for m in self.OUTSIDE.finditer(s):
                pre = re.split(r"(?i)\bbut\b|\bhowever\b|\bthough\b|\byet\b|\bexcept\b|\bapart from\b", s[:m.start()])[-1]
                self.assertTrue(self.NEGATION.search(pre),
                                f"{where}: a {m.group(0)!r} share is only ever denied (never a guest, portal, community "
                                f"or partner share): {s[:200]!r}")

    def assertNotSoftened(self, text, where):
        """#69's contradiction sweep (a deletion, a softener), and nothing put off, made temporary or optional."""
        self.d.assertNoContradiction(text, where)
        for s in self.clauses(text, ".;:?!"):
            for m in self.SOFT_TIME.finditer(s):
                self.assertTrue(self.d.locally_denied(s, m),
                                f"{where}: the rule holds now and always, not {m.group(0)!r}: {s[:200]!r}")

    def steps(self, raw, where):
        """The Rollout's numbered steps (`1. …` and their indented lines), without any text before or after."""
        out, inside = [], False
        for line in raw.splitlines():
            if re.match(r"\d+[.)]\s", line):
                inside = True
            elif inside and line.strip() and not line[:1].isspace():
                break
            if inside:
                out.append(line)
        self.assertGreaterEqual(len([x for x in out if re.match(r"\d+[.)]\s", x)]), 3,
                                f"{where}: the Rollout is a numbered list of steps (`1. …`)")
        return flat("\n".join(out))

    def table(self, part, where):
        """(columns, rows) of the first Markdown table in `part`: columns maps group, label, dashboard_folder,
        report_folder and count to their index; rows are lists of raw cells."""
        lines = [x.strip() for x in part.splitlines() if x.strip().startswith("|")]
        self.assertGreaterEqual(len(lines), 3, f"{where}: no Markdown table (header, separator, rows)")
        split = [[c.strip() for c in x.strip("|").split("|")] for x in lines]
        header = [self.cell(h).lower() for h in split[0]]
        self.assertTrue(all(re.fullmatch(r":?-{3,}:?", c) for c in split[1]), f"{where}: the table's second line is "
                                                                                "its separator (`|---|---|`)")
        want = {
            "dashboard_folder": lambda h: "dashboard folder" in h,
            "report_folder": lambda h: "report folder" in h,
            "group": lambda h: re.search(r"\bgroup\b", h) and "folder" not in h,
            "label": lambda h: "dashboard" in h and "folder" not in h and "group" not in h,
            "count": lambda h: re.search(r"\b(count|number|reports)\b|#", h) and "folder" not in h
                               and "dashboard" not in h and "group" not in h,
        }
        cols = {}
        for key, ok in want.items():
            found = [i for i, h in enumerate(header) if ok(h)]
            self.assertEqual(len(found), 1, f"{where}: the table has one {key.replace('_', ' ')} column (columns: group, "
                                            f"dashboard label, dashboard folder, report folder, report count); found "
                                            f"{[split[0][i] for i in found]} in {split[0]}")
            cols[key] = found[0]
        rows = split[2:]
        for r in rows:
            self.assertEqual(len(r), len(header), f"{where}: row {r!r} has {len(r)} cells, not {len(header)}")
        return cols, rows

    def row_of(self, rows, cols, group, where):
        found = [r for r in rows if group in self.cell(r[cols["group"]])]
        self.assertEqual(len(found), 1, f"{where}: one table row whose group is {group!r} (found {len(found)})")
        return found[0]

    def plan_path(self):
        found = sorted(glob.glob(self.PLANS))
        self.assertEqual(len(found), 1, "docs/plans/: one plan `YYYY-MM-DD-sf-category-folders.md` for ticket #73 "
                                        f"(found {[os.path.basename(p) for p in found]})")
        self.assertRegex(os.path.basename(found[0]), r"^\d{4}-\d\d-\d\d-sf-category-folders\.md$",
                         "docs/plans/: the plan is named `YYYY-MM-DD-sf-category-folders.md`")
        return found[0]

    def first(self, rx, text, where, what):
        m = re.search(rx, text)
        self.assertTrue(m, f"{where}: {what}")
        return m.start()

    # --- the RUNBOOK ---------------------------------------------------------------------------------------

    def test_the_runbook_lists_the_five_dashboards_and_their_folders(self):
        where = f"RUNBOOK section {self.MONTHLY[3:]!r}, {self.PART[4:]!r}"
        part = self.part()
        cols, rows = self.table(part, where)
        keep = self.keep_rows()
        self.assertEqual(len(rows), len(self.GROUPS) + 1, f"{where}: the table has six rows, the five groups and "
                                                          f"{self.TABLE_GROUP!r} (found {len(rows)})")
        for group in self.GROUPS + (self.TABLE_GROUP,):
            r = self.row_of(rows, cols, group, where)
            at = f"{where}, row {group!r}"
            count = sum(1 for k in keep if k["group"] == group and k["kind"] != "dashboard")
            self.assertRegex(self.cell(r[cols["count"]]), r"^\d+$",
                             f"{at}: the report count cell is a number alone, not {r[cols['count']]!r}")
            self.assertEqual(int(self.cell(r[cols["count"]])), count,
                             f"{at}: the report count is {count}, its rows on `glow/sf_keep_list.csv` (item 12 "
                             f"included), not {r[cols['count']]!r}")
            self.assertEqual(self.cell(r[cols["report_folder"]]), self.REPORT_FOLDER,
                             f"{at}: the report folder is {self.REPORT_FOLDER!r} exactly (one report folder for every "
                             f"kept report, Ryan 2026-10-21), not {r[cols['report_folder']]!r}")
            if group == self.TABLE_GROUP:
                self.assertIn("GLOW of the Month Stories", self.cell(" ".join(r)),
                              f"{at}: name item 19, \"GLOW of the Month Stories\"")
                self.assertRegex(self.cell(r[cols["dashboard_folder"]]), r"^[-—–]?$",
                                 f"{at}: the table is in no dashboard; its dashboard folder cell is blank or a dash, "
                                 f"not {r[cols['dashboard_folder']]!r}")
                continue
            dash = [k for k in keep if k["group"] == group and k["kind"] == "dashboard"]
            self.assertEqual(len(dash), 1, f"glow/sf_keep_list.csv: one dashboard row for {group!r}")
            label = self.cell(r[cols["label"]])
            # GLOW's review of 2026-11-02 renames D3 (ticket #198): its title is "Club Observation Dashboards" since
            # the deploy, the Id unchanged; every other dashboard keeps its label
            # (the keep list's `label_today` for D3 stays "GLOW Club Training", the label #70 recorded; the table says
            # what the org holds now)
            want = self.RENAMED_DASHBOARDS.get(dash[0]["item"], dash[0]["label_today"])
            self.assertEqual(label, want,
                             f"{at}: the dashboard label is its current label {want!r} "
                             f"({dash[0]['item']} in `glow/sf_keep_list.csv`; labels do not change, Ryan 2026-10-23"
                             f"{', except D3 since #198' if dash[0]['item'] in self.RENAMED_DASHBOARDS else ''}), "
                             f"not {label!r}")
            self.assertEqual(self.cell(r[cols["dashboard_folder"]]), self.DASH_FOLDER,
                             f"{at}: the dashboard folder is {self.DASH_FOLDER!r} exactly (one dashboard folder for the "
                             f"five dashboards, Ryan 2026-10-21), not {r[cols['dashboard_folder']]!r}")
        text = self.norm(part)
        for kind, dev in (("ReportFolder", self.REPORT_DEV), ("DashboardFolder", self.DASH_DEV)):
            self.assertTrue([s for s in self.clauses(part) if kind in s and re.search(r"\b%s\b" % dev, s)],
                            f"{where}: give the {kind} DeveloperName `{dev}` (a sentence naming `{kind}` and `{dev}`)")
        others = set(re.findall(r"\bGLOW_Monthly_\w+", flat(part))) - {self.REPORT_DEV, self.DASH_DEV}
        self.assertFalse(others, f"{where}: the DeveloperNames are `{self.REPORT_DEV}` and `{self.DASH_DEV}`, not "
                                 f"{sorted(others)}")
        self.assertNotRegex(text, r"\bGLOW_Club_(Attendance|Implementation|Observations|Training|Reporting)\b",
                            f"{where}: no per-category folder (Ryan, 2026-10-21: one report folder and one dashboard "
                            "folder)")
        self.k.assertSameLabels(text, where)

    def test_the_new_folders_are_shared_with_internal_users_only(self):
        where = f"RUNBOOK section {self.MONTHLY[3:]!r}, {self.PART[4:]!r}"
        part = self.part()
        text = self.norm(part)
        cl = self.clauses(part)
        for folder in self.DHIS2_FOLDERS + (self.REPORT_FOLDER, self.DASH_FOLDER):
            self.assertIn(folder, text, f"{where}: name the folder {folder!r}")
        share = re.compile(r"(?i)\bshar(e|es|ed|ing)\b")
        copies = [s for s in cl if re.search(r"(?i)\bdhis2\b", s)
                  and (all(f in s for f in self.DHIS2_FOLDERS) or re.search(r"(?i)\bunion\b|\ball three\b", s))
                  and not re.search(r"(?i)\balone\b|\bignor\w*|\bonly one\b|\bjust one\b|\bexcept\b|\bexclud\w*|"
                                    r"\bbut not\b", s)
                  and re.search(r"(?i)\bcop(y|ies|ied)\b|\bsame\b", s)
                  and any(not self.d.locally_denied(s, m) for m in share.finditer(s))]
        self.assertTrue(copies, f"{where}: say, in one sentence, the new folders copy the shares of all three DHIS2 "
                                "folders (the union of \"DHIS2 Reports\", \"DHIS2 Dashboards\" and \"Dhis2 Dashbords\"), "
                                "not negated and not one of them alone")
        same = [s for s in cl if share.search(s) and re.search(r"(?i)\bsame\b|\bidentical\b", s)
                and re.search(r"(?i)\bboth\b|\btwo\b", s) and "Decommissioned" not in s]
        self.assertTrue(same, f"{where}: say both new folders get the same shares as each other (a dashboard's viewers "
                              "need its reports' folder), not the Decommissioned folders' (they have none)")
        internal = re.compile(r"(?i)\binternal\s+users\b[^.;]{0,30}?\bgroups\b")
        self.assertTrue([s for s in cl if re.search(r"(?i)\bonly\b", s)
                         and any(not self.d.locally_denied(s, m) for m in internal.finditer(s))],
                        f"{where}: say the new folders are shared with internal users and groups only")
        self.assertTrue([s for s in cl if all(re.search(r"(?i)\b%s\b" % w, s) for w in ("guest", "portal", "community",
                                                                                         "partner"))],
                        f"{where}: say never a guest, portal, community or partner share, in one sentence")
        self.assertOnlyDenied(part, where)
        self.assertTrue([s for s in cl if self.SHARES_API.search(s)
                         and re.search(r"(?i)\b(check\w*|read\w*|confirm\w*|verif\w*)\b", s)],
                        f"{where}: say the shares are checked through the shares API, in one sentence")
        self.assertNotSoftened(part, where)

    def test_the_runbook_quotes_item_19_as_the_org_labels_it(self):
        # the org's label for 00ORP000005p2L32AI (SOQL, 2026-10-23): "GLOW of the Month Stories Report"
        row = [k for k in self.keep_rows() if k["item"] == "19"][0]
        text = self.norm(md_part(self.RUNBOOK, self.MONTHLY))
        self.assertNotIn("Report_2025", text, f"RUNBOOK section {self.MONTHLY[3:]!r}: item 19's label is \"GLOW of "
                                              "the Month Stories Report\" in the org, not \"…Report_2025\"")
        self.assertIn(row["label_today"], text, f"RUNBOOK section {self.MONTHLY[3:]!r}: quote item 19's label as "
                                                f"`glow/sf_keep_list.csv` gives it, {row['label_today']!r}")

    # --- the plan ---------------------------------------------------------------------------------------------

    def test_a_plan_carries_the_folder_deploy_copies_and_moves(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        text = read(path)
        keys, _ = docs_index.frontmatter(text)
        self.assertIn("status", keys, f"{name}: frontmatter `status:`")
        word, problem = docs_index.status_of(keys["status"])
        self.assertIsNone(problem, f"{name}: {problem}")
        self.assertNotEqual(word, "superseded", f"{name}: the plan is the change in force")
        self.assertRegex(text.split("\n## ", 1)[0], self.TICKET,
                         f"{name}: name ticket #73 in the frontmatter, the title or the opening paragraph")
        self.assertRegex(text, r"(?m)^## Result\b", f"{name}: no `## Result` section")
        raw = {}
        for heading, least in (("## Rollout", 40), ("## Rollback", 15)):
            part = md_part(path, heading)
            raw[heading] = part.split("\n", 1)[1] if "\n" in part else ""
            body = self.norm(raw[heading])
            self.assertNotRegex(body, r"(?i)\b(TBD|TODO|TBA|FIXME)\b", f"{name}: `{heading}` is a placeholder")
            distinct = {w.lower() for w in re.findall(r"[A-Za-z]\w*", body)}
            self.assertGreaterEqual(len(distinct), least,
                                    f"{name}: `{heading}` says too little (at least {least} distinct words)")
        where = f"{name}: `## Rollout`"
        flat_out = flat(raw["## Rollout"])          # dots kept: `tools/sf_report_folders.py move`
        cl = self.clauses(raw["## Rollout"])
        for folder in (self.REPORT_FOLDER, self.DASH_FOLDER):
            self.assertIn(folder, flat_out, f"{where}: name the new folder {folder!r}")
        self.assertTrue([s for s in cl if re.search(r"(?i)\bretriev\w*", s) and re.search(r"(?i)\bdhis2\b", s)
                         and not self.d.denies(s)],
                        f"{where}: the folder build starts from a retrieve of the DHIS2 folders (one sentence)")
        self.assertTrue([s for s in cl if re.search(r"(?i)check-only[^.;]*?\bdeploy", s) and not self.d.denies(s)],
                        f"{where}: validate check-only before the deploy (one sentence, in that order)")
        self.assertRegex(flat_out, r"Ryan['’]s go\b", f"{where}: the deploy and each `--apply` wait for Ryan's go")
        self.assertRegex(flat_out, r"\bafter/", f"{where}: the read-back retrieves into `after/` and compares")
        self.assertRegex(flat_out, self.SHARES_API, f"{where}: the read-back reads each new folder's shares through "
                                                    "the shares API")
        self.assertTrue([s for s in cl if re.search(r"(?i)\bcop(y|ies)\b", s) and "Decommissioned" in s
                         and DecommissionedFoldersDocs.REPORT_AND_DASHBOARD.search(s) and not self.d.denies(s)],
                        f"{where}: each kept report and dashboard is copied into Decommissioned (one sentence)")
        # the order, read in the numbered steps only (a preface listing the steps proves nothing)
        steps = self.steps(raw["## Rollout"], where)
        check_only = self.first(r"(?i)check-only", steps, where, "no check-only in the numbered steps")
        deploys = [s for s in sentences(steps, ".;,") if re.search(r"(?i)\bdeploy", s)
                   and not re.search(r"(?i)check-only|--dry-run|\bvalidat", s)]
        self.assertTrue(deploys, f"{where}: no deploy step (after the check-only, on Ryan's go)")
        self.assertLess(check_only, steps.index(deploys[0]), f"{where}: the check-only comes before the deploy")
        copies = [m.start() for m in re.finditer(r"sf_report_folders\.py\s+copy\b", steps)]
        moves = [m.start() for m in re.finditer(r"sf_report_folders\.py\s+move\b", steps)]
        self.assertTrue(copies, f"{where}: the copies into Decommissioned by `tools/sf_report_folders.py copy` (a step)")
        self.assertTrue(moves, f"{where}: the report moves by `tools/sf_report_folders.py move` (a step)")
        self.assertLess(check_only, copies[0], f"{where}: the folders are deployed (check-only, go, deploy) before the "
                                               "copies")
        self.assertLess(copies[-1], moves[0], f"{where}: every copy into Decommissioned comes BEFORE the first move "
                                              "(copy, then move)")
        dry = [m.start() for m in re.finditer(r"(?i)\bdry[- ]run\b", steps) if m.start() > copies[-1]]
        limit = [m.start() for m in re.finditer(r"--limit 1\b", steps)]
        self.assertTrue(dry and limit and dry[0] < limit[0] < moves[-1],
                        f"{where}: after the copies, the moves go dry run, then `--limit 1`, then the rest (the last "
                        "`move` step), in that order in the numbered steps")
        self.assertTrue([s for s in cl if re.search(r"(?i)\bdashboards?\b", s) and re.search(r"(?i)\bmov\w*", s)
                         and re.search(r"(?i)\bby hand\b|\bLightning\b", s) and not self.d.denies(s)
                         and self.DASH_FOLDER in s
                         and not re.search(r"(?i)dhis2", re.sub(r"(?i)\bfrom\s+(the\s+)?[`\"“]?(DHIS2|Dhis2)", "", s))],
                        f"{where}: the dashboards are moved by hand in Lightning (the API refuses a dashboard PATCH) "
                        f"to {self.DASH_FOLDER!r}, not to a DHIS2 folder (one sentence)")
        soql = [s for s in cl if "SOQL" in s and re.search(r"\bId\b|\bIds\b", s) and re.search(r"(?i)\bfolder\b", s)
                and re.search(r"(?i)\blabels?\b[^.;]{0,40}?\b(unchanged|the same)\b", s)]
        self.assertTrue(soql, f"{where}: check by SOQL that each kept Id is in its folder with its label unchanged "
                              "(one sentence)")
        self.assertTrue([m for m in re.finditer(r"SOQL", steps) if m.start() > moves[-1]],
                        f"{where}: the SOQL check comes after the moves (a later step)")
        self.assertTrue([s for s in cl if re.search(r"(?i)\bdhis2\b", s) and re.search(r"(?i)\bkept\b", s)
                         and re.search(r"(?i)\b(no|none|nothing|empty)\b", s)
                         and re.search(r"(?i)\b(SOQL|quer\w*|confirm\w*|check\w*|verif\w*)\b", s)
                         and not self.ASSUMED.search(s)],
                        f"{where}: check (SOQL) that the three DHIS2 folders hold no kept item, not assume it (one "
                        "sentence)")
        self.k.assertSameLabels(self.norm(raw["## Rollout"]), where)
        self.d.assertNoContradiction(raw["## Rollout"], where)
        where = f"{name}: `## Rollback`"
        cl = self.clauses(raw["## Rollback"])
        self.assertTrue([s for s in cl if re.search(r"\bundo\b", s) and "ledger" in s and not self.d.denies(s)],
                        f"{where}: the reports go back by `undo` from the ledger (`data/sf_report_folders/ledger.csv`)")
        self.assertRegex(flat(raw["## Rollback"]), r"(?<![\w/.-])data/sf_report_folders/ledger\.csv(?![\w/-]|\.\w)",
                         f"{where}: name the ledger `data/sf_report_folders/ledger.csv` exactly")
        self.assertTrue([s for s in cl if re.search(r"(?i)\bdashboards?\b", s) and re.search(r"(?i)\bback\b", s)
                         and re.search(r"(?i)\bby hand\b|\bLightning\b", s) and not self.d.denies(s)],
                        f"{where}: the dashboards are moved back by hand in Lightning")
        self.assertTrue([s for s in cl if re.search(r"(?i)\bfolders?\b", s)
                         and re.search(r"(?i)\b(left|leave|stays?|remains?|kept)\b[^.;]{0,30}?\bin place\b", s)],
                        f"{where}: the new folders are left in place, not deleted")
        self.assertNotSoftened(raw["## Rollback"], where)
        self.assertOnlyDenied(raw["## Rollback"], where)

    # --- DECISIONS --------------------------------------------------------------------------------------------

    def test_a_decision_records_one_report_folder_and_one_dashboard_folder(self):
        e = self.k.decision()
        where = f"docs/DECISIONS.md {e.split(chr(10), 1)[0][4:14]} (the keep list)"
        bullets = re.findall(r"(?m)^[ \t]*- .*(?:\n(?![ \t]*- |\n|#).*)*", e)
        dated = [flat(b) for b in bullets if re.match(r"-\s+\W{0,3}(\w+,?\s+){0,2}?2026-10-2[3-9]\b", flat(b))]
        self.assertTrue(dated, f"{where}: no dated bullet (`- 2026-10-23: …`) on the entry")
        good = []
        for b in dated:
            one = [re.search(r"(?i)\b(one|a single|single)\s+%s folder\b" % k, b) for k in ("report", "dashboard")]
            if (all(one) and not any(self.d.locally_denied(b, m) for m in one)
                    and self.REPORT_FOLDER in b and self.DASH_FOLDER in b
                    and re.search(r"\bRyan\b", b) and "2026-10-21" in b
                    and re.search(r"(?i)\b(instead of|rather than|not|in place of|replac\w*)\b[^.;]{0,40}?"
                                  r"\b(per-category|categor(y|ies)|per group|each group|eleven)\b", b)
                    and not re.search(r"(?i)\b(was|were|is|are|been)\s+(only\s+)?proposed\b|\bturned down\b|"
                                      r"\bin favou?r of\b|\bdeclin\w*|\bvetoed\b|\boverruled\b", b)
                    and not KeepListDocs.REJECTED_AFTER.search(b)
                    and not re.search(r"(?i)\b(reject\w*|dropped|discard\w*|abandon\w*|withdr[ae]w\w*|superseded)\b", b)):
                good.append(b)
        self.assertTrue(good, f"{where}: a dated bullet records one report folder, {self.REPORT_FOLDER!r}, and one "
                              f"dashboard folder, {self.DASH_FOLDER!r} (Ryan, 2026-10-21), as the decision, instead of "
                              "per-category folders (\"instead of\", \"not\", \"rather than\", \"replaces\" before them); "
                              "not proposed, turned down or rejected")


class ReportingDashboardDocs(unittest.TestCase):
    """Ticket #79: the dashboard "GLOW Club Reporting" (D5 in `glow/sf_keep_list.csv`, today "Reporting") and its
    reports, items 17 ("Report approved by PO") and 18 ("Report submitted on time"), and the table, item 19 ("GLOW
    of the Month Stories"), by Partner and Month (Ryan, 2026-10-21). Ryan, 2026-10-24 on the ticket: the period is
    the last 12 months through `DHIS2__c.Period__c` (#128), grouped by Partner (`Account__c`), then the month; the
    test-record rule of #70 on every kept report; each report copied into Decommissioned before it changes; the
    three dynamic dashboards (D5 among them) refuse an API copy (the org is at its 5 dynamic dashboards), so for the
    dashboard the retrieve into `before/` is the rollback. Ryan, 2026-10-24 09:55 UTC on #79, for all five
    dashboards: no Partner filter and no Month filter on any dashboard; the only dashboard filter is Partner Manager
    (`Assigned_Partner_Manager__c`, each manager sees their partners); the reports stay grouped by Partner and Month,
    and item 19 stays tabular with Partner and Month columns. Labels, ids and measures are read from the CSV, not
    pinned; the plan's Result waits for the live deploy, so no org figure is pinned either.

    #200 (GLOW's review, Ryan 2026-11-02) replaces four of these rules, so this class accepts its new ones and
    GlowReviewReportingDocs checks them: the period may be `In_Reporting_Year__c` (a signal may read `In_Reporting_Year__c
    = true` as its window), D5 has a Month filter beside Partner Manager (still no Partner filter), item 17 may be
    named by its new label (`label_target`), and a rollback may name #200's `data/sf_glow_review_<month>/` folder. The
    overview's signal (grouped by `Approved__c`) is #200's report, not item 17's."""

    longMessage = False         # the messages say what to fix
    RUNBOOK = os.path.join(REPO, "docs", "RUNBOOK.md")
    KEEP_LIST = os.path.join(REPO, "glow", "sf_keep_list.csv")
    PLANS = os.path.join(REPO, "docs", "plans", "*-sf-dash-reporting.md")
    MONTHLY = "## Monthly Report dashboards in Salesforce"
    PART = "### GLOW Club Reporting"
    TICKET = re.compile(r"(?<![\w#])#79\b")
    ITEMS = ("17", "18", "19")
    DASH = "D5"
    # this change's retrieve: `data/sf_dash_reporting_<date>/before/` (a real date once it has run)
    THIS_DIR = r"data/sf_dash_reporting_(?:\d{4}-\d\d-\d\d|<date>|YYYY-MM-DD)"
    BEFORE = re.compile(THIS_DIR + r"/before/")
    ANY_DATA_DIR = re.compile(r"\bdata/sf_[\w<>-]+")
    PARTNER = re.compile(r"\bPartner\b|Account__c\b")
    MONTH = re.compile(r"\bMonth\b|Period__c\b")
    LAST_12 = re.compile(r"(?i)\bLAST_N_MONTHS:12\b|\blast 12 months\b|\bLAST 12 MONTHS\b")
    SOQL = re.compile(r"\bSELECT\b[^`]*?\bFROM\s+DHIS2__c\b")
    SOQL_SPAN = re.compile(r"\bSELECT\b[^`]*?\bFROM\s+DHIS2__c\b[^`]*")
    # a date field other than the period: never in a signal; `CreatedDate` only ever said to be replaced or unused
    OTHER_DATE = re.compile(r"\b(CreatedDate|LastModifiedDate|SystemModstamp|YearMonth__c)\b")
    CREATED = re.compile(r"\bCreatedDate\b")
    REPLACED_BEFORE = re.compile(r"(?i)\b(in place of|instead of|rather than|replac\w*|swap\w*)\b")
    DENIED_AFTER = re.compile(r"(?i)^\W*((is|are|was|were)\s+)?(never|not|no longer)\b|^\W*(is|are|was|were)\s+"
                              r"(replaced|dropped|removed)\b|^\W*goes\b")
    PERIOD_PRED = re.compile(r"\bPeriod__c\s*(=|!=|<>|>=|<=|<|>|\bIN\b)\s*([\w:.()-]+)", re.I)
    YEAR_PRED = re.compile(r"\bYear__c\s*(=|>=|<=|<|>|!=)\s*(\d+)")
    MONTH_PRED = re.compile(r"\bMonth__c\s*=\s*'(\w+)'")
    MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
              "November", "December")
    FIRST_CHECKED = "2026-09-01"        # the earliest last complete month this change can be checked on
    # one partner's number: grouped by the partner, or one partner by name or Id
    PER_PARTNER = re.compile(r"(?i)\bGROUP\s+BY\s+(DHIS2__c\.)?Account__(c|r\.Name)\b|\bAccount__r\.Name\s*=\s*'[^'%]+'|"
                             r"\bAccount__c\s*=\s*'001\w+'")
    MONTH_FILTER = re.compile(r"(?i)\bMonth\s+filter\b|\bfilters?\s+(on|by|for)\s+(the\s+)?Month\b")
    PARTNER_FILTER = re.compile(r"(?i)\bPartner\s+filter\b|\bfilters?\s+(on|by|for)\s+(the\s+)?Partner\b(?!\s+Manager)")
    # "one filter, Partner Manager", "its only filter is Partner Manager", "the single filter: Partner Manager"
    ONLY_PM_FILTER = re.compile(r"(?i)\b(only|one|single|sole)\s+(dashboard\s+)?filter\b[^.;]{0,40}?\bPartner Manager\b|"
                                r"\bPartner Manager\b[^.;]{0,40}?\b(is|as)\s+(its|the)\s+(only|one|single|sole)\s+"
                                r"(dashboard\s+)?filter\b")
    # since #200 (GLOW's review, Ryan 2026-11-02) D5 has a Month filter too: a Partner Manager filter, "only" or not
    PM_FILTER = re.compile(r"(?i)\bfilter\w*[^.;]{0,40}?\bPartner Manager\b|\bPartner Manager\b[^.;]{0,20}?\bfilter\w*")
    # since #200 the reports' period is the reporting year (#195)
    IN_YEAR = re.compile(r"\bIn_Reporting_Year__c\b")
    IN_YEAR_SOQL = re.compile(r"(?i)\bIn_Reporting_Year__c\s*=\s*true\b")
    # #200's overview signal: grouped by `Approved__c` ("Approval Status by Month"), not item 17's
    OVERVIEW_SIGNAL = re.compile(r"(?is)\bGROUP\s+BY\b[^`]*\bApproved__c\b")
    # a path in a rollback: only this change's retrieve, the copy tool's ledger folder, and the bare before/ after/
    PATH = re.compile(r"(?<![\w/.<>-])(?:[\w.<>*-]+/)+[\w.<>*-]*")
    # a fallback: "if before/ is missing, deploy …", "otherwise restore …"
    FALLBACK = re.compile(r"(?i)\bif\b[^.;]{0,80}?\b(missing|absent|gone|lost|empty|unavailable|not there|does not exist|"
                          r"doesn['’]t exist|deleted|corrupt\w*|unreadable)\b[^.;]{0,80}?\b(deploy|restor|use|roll|redeploy)\w*|"
                          r"\b(otherwise|fall\s*back|fallback|failing that|as a last resort|alternatively|"
                          r"instead(?!\s+of))\b")
    STOP = re.compile(r"(?i)\b(stop\w*|ask\w*|do not|don['’]t|never|nothing)\b")
    # a report left without its copy
    NO_COPY = re.compile(r"(?i)\b(no|without)\s+(a\s+|its\s+|their\s+)?cop(y|ies)\b|\bin place\b|\bnot\s+copied\b|"
                         r"\buncopied\b|\bskip\w*\b|\bexcept\b")
    SOQL_NOT_BLANK = re.compile(r"\bAccount__c\s*(!=|<>)\s*null\b", re.I)
    SOQL_NO_TEST = re.compile(r"\bNOT\s+Account__r\.Name\s+LIKE\s+'%test%'", re.I)
    COPY_CMD = re.compile(r"\bpython3\s+(\S*/)?sf_report_folders\.py\s+copy\b")
    RESTORE = re.compile(r"(?i)\b(restor\w*|revert\w*|roll(s|ed|ing)?\s+back|rollback|redeploy\w*|deploy\w*|"
                         r"back)\b")
    # the condition on before/: "only while (if, as long as) a fresh retrieve equals (matches) `after/`"
    ONLY_WHILE = re.compile(r"(?i)\bonly\s+(while|if|when|as long as|so long as|provided)\b[^.;]*?\bfresh\s+"
                            r"retriev\w*[^.;]*?(\bequals?\b|\bmatch(es)?\b|\bthe same as\b|\bidentical\b|=)[^.;]*?"
                            r"`?after/")
    OLDER_BUILD = re.compile(r"(?i)\bnever\b[^.;]{0,60}?\b(an?\s+|the\s+)?(older|earlier|previous|old|stale)\s+"
                             r"(build|retrieve)s?\b|\b(older|earlier|previous|old|stale)\s+(build|retrieve)s?\b"
                             r"[^.;]{0,40}?\bnever\b")

    @classmethod
    def setUpClass(cls):
        cls.d = DecommissionedFoldersDocs()     # #69's helpers: locally_denied, contradictions
        KeepListDocs.setUpClass()
        cls.k = KeepListDocs()                  # #70's helpers: assertTestRecordRule, EVERY_REPORT
        CategoryFoldersDocs.setUpClass()
        cls.c = CategoryFoldersDocs()           # #73's helpers: steps

    @staticmethod
    def norm(text):
        return DecommissionedFoldersDocs.norm(text)

    def clauses(self, text, ends=".;"):
        return sentences(self.norm(text), ends)

    def keep(self):
        import csv
        with open(self.KEEP_LIST, encoding="utf-8", newline="") as f:
            rows = {r["item"]: r for r in csv.DictReader(f)}
        for item in self.ITEMS + (self.DASH,):
            self.assertIn(item, rows, f"glow/sf_keep_list.csv: no row {item}")
        return rows

    def stated(self, s, rx):
        """`rx` said in clause `s`, not denied in the words before it (#69's `locally_denied`)."""
        return any(not self.d.locally_denied(s, m) for m in rx.finditer(s))

    def sweep(self, text, where, rollback=False):
        """#69's contradiction sweep (a deletion, a softener, "no rollback"); "cannot" and "impossible" are
        allowed, since the dashboard's API copy is refused (Ryan, 2026-10-24) and the docs may say so."""
        found = [x for x in self.d.contradictions(text, rollback=rollback)
                 if not re.match(r"softens a rule \('(cannot|can['’]t|impossible)'\)", x)]
        self.assertEqual(found, [], f"{where}: contradicts the rules (nothing deleted, the copies, the check-only and "
                                    "the rollback never optional): " + "; ".join(found))

    def part(self):
        """The `### GLOW Club Reporting` part of the Monthly Report section, to the next `###` or `##`."""
        section = md_part(self.RUNBOOK, self.MONTHLY)
        m = re.search(r"^" + re.escape(self.PART) + r"(?!\w).*$", section, re.M)
        self.assertTrue(m, f"RUNBOOK section {self.MONTHLY[3:]!r}: no `{self.PART}` part under it (ticket #79)")
        rest = section[m.start():]
        nxt = re.search(r"\n#{1,3} ", rest)
        return rest[:nxt.start()] if nxt else rest

    def items_named(self, text, rows):
        """Which of items 17-19 `text` names: by label, measure or Id from the CSV, by `item(s) N` (a range or
        list too), or as a table row starting `| N |`."""
        out = set()
        for item in self.ITEMS:
            r = rows[item]
            # (since #200 item 17 may be named by its new label, `label_target`)
            if any(v and v in text for v in (r["label_today"], r["label_target"], r["measure"], r["id"])):
                out.add(item)
            if re.match(r"\s*\|\s*%s\s*\|" % item, text):
                out.add(item)
        for m in re.finditer(r"(?i)\bitems?\s+((?:\d+\s*(?:[-–]|to|and|,|&)\s*)*\d+)\b", text):
            nums = re.findall(r"\d+|[-–]|to", m.group(1))
            for i, tok in enumerate(nums):
                if tok.isdigit():
                    out.add(tok)
                elif i and i + 1 < len(nums) and nums[i - 1].isdigit() and nums[i + 1].isdigit():
                    out |= {str(n) for n in range(int(nums[i - 1]), int(nums[i + 1]) + 1)}
        return out & set(self.ITEMS)

    @staticmethod
    def blocks(raw):
        """`raw` cut into its paragraphs, list items and table rows, each flattened."""
        parts = re.split(r"\n\s*\n|\n(?=[ \t]*(?:[-*+]|\d+[.)])\s)|\n(?=[ \t]*\|)", raw)
        return [flat(p) for p in parts if p.strip()]

    def commands(self, raw):
        """Each `python3 …sf_report_folders.py copy …` command in `raw`, flattened."""
        segments = re.split(r"`+|\n\s*\n|\n(?=\s*(?:\$\s*)?python3\s)|(?=\bpython3\s)", raw)
        return [flat(seg)[m.start():] for seg in segments for m in [self.COPY_CMD.search(flat(seg))] if m]

    def plan_path(self):
        found = sorted(glob.glob(self.PLANS))
        self.assertEqual(len(found), 1, "docs/plans/: one plan `YYYY-MM-DD-sf-dash-reporting.md` for ticket #79 "
                                        f"(found {[os.path.basename(p) for p in found]})")
        self.assertRegex(os.path.basename(found[0]), r"^\d{4}-\d\d-\d\d-sf-dash-reporting\.md$",
                         "docs/plans/: the plan is named `YYYY-MM-DD-sf-dash-reporting.md`")
        return found[0]

    def plan_part(self, path, heading, least):
        name = os.path.relpath(path, REPO)
        part = md_part(path, heading)
        raw = part.split("\n", 1)[1] if "\n" in part else ""
        body = self.norm(raw)
        self.assertNotRegex(body, r"(?i)\b(TBD|TODO|TBA|FIXME)\b", f"{name}: `{heading}` is a placeholder")
        distinct = {w.lower() for w in re.findall(r"[A-Za-z]\w*", body)}
        self.assertGreaterEqual(len(distinct), least, f"{name}: `{heading}` says too little (at least {least} "
                                                      "distinct words)")
        return raw

    def assertRollback(self, raw, where, rows):
        """The reports back from their Decommissioned copies; the dashboard from this change's `before/` only while
        a fresh retrieve equals `after/`; never an older build; no other retrieve folder; nothing deleted."""
        text = self.norm(raw)
        cl = sentences(text, ".;")
        for item in self.ITEMS:
            r = rows[item]
            self.assertTrue(self.items_named(raw, rows) >= {item},
                            f"{where}: name the report whose copy restores item {item} ({r['label_today']!r}, "
                            f"{r['id']})")
        copies = [s for s in cl if re.search(r"(?i)\bcop(y|ies)\b", s) and "Decommissioned" in s
                  and re.search(r"(?i)\breports?\b", s) and self.stated(s, self.RESTORE)
                  and self.stated(s, re.compile(r"(?i)\bcop(y|ies)\b"))]
        self.assertTrue(copies, f"{where}: say, in one sentence, the reports (items 17-19) are restored from their "
                                "copies in Decommissioned, not negated")
        self.assertRegex(flat(raw), self.BEFORE, f"{where}: name this change's retrieve, "
                                                 "`data/sf_dash_reporting_<date>/before/`")
        dash = [s for s in sentences(flat(raw), ".;") if self.BEFORE.search(s)
                and re.search(r"(?i)\bdashboard\b|\bD5\b|[\"“`]Reporting[\"”`]", s) and self.stated(s, self.RESTORE)]
        self.assertTrue(dash, f"{where}: say, in one sentence, the dashboard (D5, \"Reporting\") is restored by deploying "
                              "`data/sf_dash_reporting_<date>/before/` (its API copy is refused: the org is at its 5 "
                              "dynamic dashboards)")
        cond = [s for s in sentences(flat(raw), ".;") if "before/" in s and self.ONLY_WHILE.search(s)
                and not self.d.locally_denied(s, self.ONLY_WHILE.search(s))]
        self.assertTrue(cond, f"{where}: say, in the sentence naming `before/`, it is deployed only while a fresh "
                              "retrieve equals `after/` (\"only while a fresh retrieve equals `after/`\")")
        self.assertTrue([s for s in cl if self.OLDER_BUILD.search(s)],
                        f"{where}: say the rollback never deploys an older build (DECISIONS 2026-10-16)")
        others = sorted({p for p in self.PATH.findall(flat(raw)) if self.foreign_path(p)})
        self.assertFalse(others, f"{where}: the rollback restores from this change's `data/sf_dash_reporting_<date>/` "
                                 f"only (or the copy tool's ledger folder), never another retrieve, build or backup: "
                                 f"{others}")
        fallback = [s for s in sentences(flat(raw), ".;") if self.FALLBACK.search(s) and not self.STOP.search(s)]
        self.assertFalse(fallback, f"{where}: no fallback to another source (if `before/` is missing or differs, stop "
                                   f"and ask; never deploy anything else): {[s[:160] for s in fallback]}")
        self.sweep(raw, where, rollback=True)

    def foreign_path(self, p):
        """A path in a rollback that is not this change's retrieve, the copy tool's ledger folder, a bare
        `before/`, `after/` or `build/`, a tool or a doc."""
        if re.fullmatch(r"(before|after|build)/", p):
            return False
        if re.match(self.THIS_DIR + r"(?![\w-])", p) or re.match(r"data/sf_report_folders(?![\w-])", p):
            return False
        # since #200 (GLOW's review, Ryan 2026-11-02) its own retrieve, `data/sf_glow_review_<month>/<topic>/`
        # (GlowReviewReportingDocs checks that #200's rollback names no other change's folder)
        if re.match(r"data/sf_glow_review_(\d{4}-\d\d|<month>)(?![\w-])", p):
            return False
        if re.match(r"(tools|docs|plans|scripts|glow|test)/", p) or re.search(r"\.(py|md|sh|csv)$", p):
            return p.startswith(("data/", "backups/"))
        return bool(re.match(r"(data|backups)/", p) or re.search(r"(^|/)(build|before|after|backups|data)/", p))

    def last_complete_months(self):
        """The first days of the months a check can be the last complete month of: from FIRST_CHECKED to the
        month before this one."""
        import datetime
        today = datetime.date.today()
        this_month = today.replace(day=1).isoformat()
        out, y, m = [], 2026, 9
        while f"{y:04d}-{m:02d}-01" < this_month:
            out.append(f"{y:04d}-{m:02d}-01")
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return out

    def assertSignalWindow(self, soql, where):
        """A signal's period is the check's window: `Period__c = LAST_MONTH`, `Period__c = LAST_N_MONTHS:12`, or one
        explicit month (`Period__c = 2026-09-01`, or `Year__c = 2026 AND Month__c = 'September'`) that a check can have
        as its last complete month; no other date field."""
        other = self.OTHER_DATE.findall(soql)
        self.assertFalse(other, f"{where}: a signal reads the period `Period__c`, never {sorted(set(other))}: "
                                f"{soql[:200]!r}")
        months = self.last_complete_months()
        preds = self.PERIOD_PRED.findall(soql)
        for op, val in preds:
            ok = op == "=" and (val in ("LAST_MONTH", "LAST_N_MONTHS:12") or val in months)
            self.assertTrue(ok, f"{where}: the signal's period is `Period__c = LAST_MONTH`, `Period__c = "
                                f"LAST_N_MONTHS:12` or a last complete month (`Period__c = {months[-1] if months else ''}`)"
                                f", not `Period__c {op} {val}`: {soql[:200]!r}")
        years, mons = self.YEAR_PRED.findall(soql), self.MONTH_PRED.findall(soql)
        if years or mons:
            self.assertTrue(len(years) == 1 and len(mons) == 1 and years[0][0] == "=" and mons[0] in self.MONTHS
                            and f"{int(years[0][1]):04d}-{self.MONTHS.index(mons[0]) + 1:02d}-01" in months,
                            f"{where}: `Year__c = <yyyy> AND Month__c = '<Month>'` names one last complete month: "
                            f"{soql[:200]!r}")
        # (since #200, GLOW's review of 2026-11-02, the reporting year `In_Reporting_Year__c = true` is a window too)
        self.assertTrue(preds or years or self.IN_YEAR_SOQL.search(soql),
                        f"{where}: the signal filters on the period (`Period__c = LAST_MONTH`, or one last complete month, "
                        f"or since #200 `In_Reporting_Year__c = true`): {soql[:200]!r}")

    @staticmethod
    def top_split(text, word):
        """`text` split on ` <word> ` outside parentheses and quotes (case-insensitive)."""
        out, depth, quote, start, i = [], 0, False, 0, 0
        rx = re.compile(r"\s+%s\s+" % word, re.I)
        while i < len(text):
            ch = text[i]
            if ch == "'":
                quote = not quote
            elif not quote and ch == "(":
                depth += 1
            elif not quote and ch == ")":
                depth -= 1
            elif not quote and depth == 0:
                m = rx.match(text, i)
                if m:
                    out.append(text[start:i])
                    start = i = m.end()
                    continue
            i += 1
        out.append(text[start:])
        return [p.strip() for p in out]

    @staticmethod
    def unwrap(p):
        """`p` without parentheses that wrap all of it."""
        while p.startswith("(") and p.endswith(")"):
            depth = 0
            for i, ch in enumerate(p):
                depth += ch == "("
                depth -= ch == ")"
                if depth == 0 and i < len(p) - 1:
                    return p
            p = p[1:-1].strip()
        return p

    def conjuncts(self, soql, where):
        """The top-level AND conjuncts of the signal's WHERE, outer parentheses removed; a top-level OR fails (it
        would cancel the period and the test-record rule)."""
        m = re.search(r"(?i)\bWHERE\b(.*?)(?=\bGROUP\s+BY\b|\bORDER\s+BY\b|\bHAVING\b|\bLIMIT\b|$)", soql)
        self.assertTrue(m, f"{where}: the signal has a WHERE (the period and the test-record rule): {soql[:200]!r}")
        clause = m.group(1).strip()
        ors = self.top_split(clause, "OR")
        self.assertEqual(len(ors), 1, f"{where}: no top-level OR in the signal's WHERE (it cancels the period and the "
                                      f"test-record rule): {soql[:220]!r}")
        return [re.sub(r"\s+", " ", self.unwrap(p)) for p in self.top_split(clause, "AND")]

    def assertSignalConjuncts(self, soql, where, item=None):
        """The period, `Account__c != null` and `NOT Account__r.Name LIKE '%test%'` are top-level conjuncts of the
        WHERE; every conjunct naming `Period__c` (or `Year__c`, `Month__c`) is one of the window's; item 17's
        `Approved__c = true` is a conjunct and no other conjunct names `Approved__c`."""
        cs = self.conjuncts(soql, where)
        months = self.last_complete_months()
        period_ok = re.compile(r"Period__c = (LAST_MONTH|LAST_N_MONTHS:12|%s)" % "|".join(map(re.escape, months or
                                                                                               ["-"])))
        ym_ok = re.compile(r"Year__c = \d{4}|Month__c = '\w+'")
        for c in cs:
            if re.search(r"\b(Period__c|Year__c|Month__c)\b", c):
                self.assertTrue(period_ok.fullmatch(c) or ym_ok.fullmatch(c),
                                f"{where}: a conjunct on the period is `Period__c = LAST_MONTH`, `= LAST_N_MONTHS:12` or "
                                f"one last complete month, alone, not {c!r}: {soql[:220]!r}")
        self.assertTrue([c for c in cs if period_ok.fullmatch(c)] or len([c for c in cs if ym_ok.fullmatch(c)]) == 2
                        or [c for c in cs if re.fullmatch(r"(?i)In_Reporting_Year__c = true", c)],     # since #200
                        f"{where}: the period is a top-level conjunct of the WHERE (`… WHERE Period__c = LAST_MONTH AND "
                        f"…`): {soql[:220]!r}")
        self.assertTrue([c for c in cs if re.fullmatch(r"(?i)Account__c (!=|<>) null", c)],
                        f"{where}: `Account__c != null` is a top-level conjunct of the WHERE: {soql[:220]!r}")
        self.assertTrue([c for c in cs if re.fullmatch(r"(?i)NOT \(?Account__r\.Name LIKE '%test%'\)?", c)],
                        f"{where}: `(NOT Account__r.Name LIKE '%test%')` is a top-level conjunct of the WHERE: "
                        f"{soql[:220]!r}")
        if item == "17":
            on = [c for c in cs if "Approved__c" in c]
            self.assertTrue(on == [c for c in on if re.fullmatch(r"(?i)Approved__c = true", c)] and on,
                            f"{where}: `Approved__c = true` is a top-level conjunct and no other predicate names "
                            f"`Approved__c`: {soql[:220]!r}")
        if item in ("17", "18"):
            select = re.match(r"(?is)SELECT\s+(.*?)\s+FROM\b", soql).group(1)
            self.assertRegex(select, r"(?i)\bCOUNT\(\s*Id\s*\)", f"{where}: the signal counts the month's Monthly "
                                                                 f"Reports, `COUNT(Id)`: {soql[:220]!r}")

    def assertCreatedDateOnlyReplaced(self, raw, where):
        """`CreatedDate` (the ticket: never `CreatedDate`) only where it is said to be replaced or unused."""
        prose = self.SOQL_SPAN.sub(" ", flat(raw))
        for s in sentences(prose, ".;"):
            for m in self.CREATED.finditer(s):
                pre = s[max(0, m.start() - 40):m.start()]
                ok = (self.d.locally_denied(s, m) or self.REPLACED_BEFORE.search(pre)
                      or self.DENIED_AFTER.search(s[m.end():].lstrip("`")))
                self.assertTrue(ok, f"{where}: never `CreatedDate`; name it only to say it is replaced or not used: "
                                    f"{s[:200]!r}")

    # --- the RUNBOOK ---------------------------------------------------------------------------------------

    def test_the_runbook_describes_reporting_by_partner_and_month(self):
        where = f"RUNBOOK section {self.MONTHLY[3:]!r}, {self.PART[4:]!r}"
        rows = self.keep()
        part = self.part()
        flat_part = flat(part)
        text = self.norm(part)
        cl = sentences(text, ".;")
        # the measures, in GLOW's words, with the org's labels and ids
        for item in self.ITEMS:
            r = rows[item]
            for key in ("measure", "id"):
                self.assertIn(r[key], flat_part, f"{where}: name item {item}'s {key.replace('_', ' ')} {r[key]!r} "
                                                 "(`glow/sf_keep_list.csv`)")
            # (since #200, GLOW's review of 2026-11-02, item 17's label is its `label_target`)
            self.assertTrue(r["label_today"] in flat_part or r["label_target"] in flat_part,
                            f"{where}: name item {item}'s label {r['label_today']!r} (or its new label "
                            f"{r['label_target']!r}, `glow/sf_keep_list.csv`)")
        d5 = rows[self.DASH]
        self.assertIn(d5["id"], flat_part, f"{where}: give the dashboard's Id {d5['id']} ({self.DASH})")
        self.assertTrue([s for s in cl if re.search(r"(?i)\bdashboard\b", s)
                         and re.search(r"[\"“`]%s[\"”`]" % re.escape(d5["label_today"]), s)],
                        f"{where}: name the dashboard by its label, \"{d5['label_today']}\" (quoted, in a sentence that "
                        "says dashboard)")
        # grouped by Partner and Month, every report
        group = re.compile(r"(?i)\bgroup(s|ed|ing)?\b")
        self.assertTrue([s for s in cl if self.stated(s, group) and self.stated(s, self.PARTNER)
                         and self.stated(s, self.MONTH)
                         and (self.k.EVERY_REPORT.search(s) or re.search(r"(?i)\bboth\b", s)
                              or self.items_named(s, rows) >= {"17", "18"})],
                        f"{where}: say, in one sentence, each report (items 17 and 18) groups by Partner "
                        "(`Account__c`) and Month (`Period__c`), not negated")
        self.assertIn("Account__c", text, f"{where}: name the Partner field, `DHIS2__c.Account__c`")
        # the period (the last 12 months through `Period__c`; since #200 `In_Reporting_Year__c`, which
        # GlowReviewReportingDocs checks)
        self.assertTrue([s for s in cl if ("Period__c" in s and self.stated(s, self.LAST_12))
                         or self.stated(s, self.IN_YEAR)],
                        f"{where}: state the period in one sentence: the last 12 months (`LAST_N_MONTHS:12`) through "
                        "`Period__c`, or since #200 the reporting year, `In_Reporting_Year__c`")
        # the test records
        self.assertRegex(text, r"(?i)\btest records?\b", f"{where}: call what the rule excludes test records")
        self.k.assertTestRecordRule(text, where)
        # the dashboard's filter: Partner Manager (Ryan, 2026-10-24 on #79, every Monthly Report dashboard); since #200
        # (GLOW's review, Ryan 2026-11-02) a Month filter beside it, so "only" is no longer required
        self.assertTrue([s for s in cl if re.search(r"(?i)\bdashboard\b", s) and "Assigned_Partner_Manager__c" in s
                         and self.stated(s, self.PM_FILTER) and not self.items_named(s, rows) & {"19"}],
                        f"{where}: say, in one sentence, the dashboard filters on Partner Manager "
                        "(`Assigned_Partner_Manager__c`), not negated (Ryan, 2026-10-24)")
        for s in cl:                    # no Partner filter on the dashboard, except denied (a Month filter is #200's)
            if self.items_named(s, rows) & {"19"}:
                continue                # item 19's own report columns and filters are not the dashboard's
            for m in self.PARTNER_FILTER.finditer(s):
                self.assertTrue(self.d.locally_denied(s, m),
                                f"{where}: the dashboard has no Partner filter (Ryan, 2026-10-24); name it only to deny "
                                f"it: {s[:200]!r}")
        self.assertCreatedDateOnlyReplaced(part, where)
        # item 19: tabular, Partner and Month its columns and filters
        about_19 = [s for s in cl if "19" in self.items_named(s, rows)]
        self.assertTrue([s for s in about_19 if self.stated(s, re.compile(r"(?i)\btabular\b"))],
                        f"{where}: say item 19 stays a tabular report (in a sentence naming it), not negated")
        self.assertTrue([s for s in about_19 if self.stated(s, re.compile(r"(?i)\bcolumns?\b"))
                         and self.stated(s, re.compile(r"\bPartner\b")) and self.stated(s, re.compile(r"\bMonth\b"))],
                        f"{where}: say, in one sentence naming item 19, it has Partner and Month as columns")
        # one SOQL signal per item, on DHIS2__c, with the period and the test-record rule
        blocks = self.blocks(part)
        for item in self.ITEMS:
            r = rows[item]
            own = [b for b in blocks if self.items_named(b, rows) == {item} and self.SOQL.search(b)]
            self.assertTrue(own, f"{where}: give item {item}'s SOQL signal (`SELECT … FROM DHIS2__c …`) in a paragraph, "
                                 f"list item or table row that names item {item} ({r['label_today']!r}) and no other of "
                                 "items 17-19")
            spans = [m.group(0) for b in own for m in self.SOQL_SPAN.finditer(b)]
            if item == "17":            # #200's overview signal (grouped by `Approved__c`) may sit beside item 17's
                spans = [q for q in spans if not self.OVERVIEW_SIGNAL.search(q)]
                self.assertTrue(spans, f"{where}: give item 17's own SOQL signal (`… Approved__c = true`), not only the "
                                       "overview's (grouped by `Approved__c`)")
            for soql in spans:          # every signal of the item, so a wrong one cannot sit beside a right one
                at = f"{where}, item {item}'s SOQL signal"
                self.assertSignalWindow(soql, at)
                self.assertSignalConjuncts(soql, at, item)
                self.assertTrue(self.SOQL_NOT_BLANK.search(soql) and self.SOQL_NO_TEST.search(soql),
                                f"{at} carries the test-record rule (`Account__c != null AND (NOT Account__r.Name LIKE "
                                f"'%test%')`): {soql[:200]!r}")
                if item == "17":
                    self.assertRegex(soql, r"(?i)\bApproved__c\s*=\s*true\b", f"{at} counts `Approved__c = true`: "
                                                                              f"{soql[:200]!r}")
            if item in ("17", "18"):    # a dashboard component: its total and one partner's number
                self.assertTrue([q for q in spans if self.PER_PARTNER.search(q)],
                                f"{where}: item {item}'s signal gives one partner's number too (`GROUP BY Account__c`, or "
                                "`Account__r.Name = '<partner>'`)")
            if item == "19":            # the table's columns: the partner and the period, in its SELECT or its text
                partner = re.compile(r"\bAccount__(c|r[._]Name)\b")
                selects = [re.match(r"(?is)SELECT\s+(.*?)\s+FROM\b", q).group(1) for q in spans]
                in_select = [s for s in selects if partner.search(s) and re.search(r"\bPeriod__c\b", s)]
                in_text = [s for s in about_19 if self.stated(s, re.compile(r"(?i)\bcolumns?\b"))
                           and self.stated(s, partner) and self.stated(s, re.compile(r"Period__c\b"))]
                self.assertTrue(in_select or in_text,
                                f"{where}: name item 19's columns by field: the partner (`Account__c` or "
                                "`Account__r.Name`) and `Period__c`, in its signal's SELECT or a sentence naming item 19 "
                                "and its columns")
        for m in self.SOQL_SPAN.finditer(flat_part):    # any other signal in the part reads the period too
            self.assertSignalWindow(m.group(0), f"{where}, a SOQL signal")
            self.assertSignalConjuncts(m.group(0), f"{where}, a SOQL signal")
        self.assertNotIn("Report_2025", text, f"{where}: item 19's label is {rows['19']['label_today']!r}")
        self.sweep(part, where, rollback=True)

    def test_the_reporting_rollback_names_the_copies_and_the_before_folder(self):
        rows = self.keep()
        where = f"RUNBOOK section {self.MONTHLY[3:]!r}, {self.PART[4:]!r}"
        part = self.part()
        self.assertRegex(part, r"(?i)\brollback\b|\broll(s|ed|ing)?\s+back\b", f"{where}: give the rollback")
        self.assertRollback(part, where, rows)
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        where = f"{name}: `## Rollback`"
        raw = self.plan_part(path, "## Rollback", 20)
        self.assertRollback(raw, where, rows)
        self.assertTrue([s for s in self.clauses(raw) if self.stated(s, re.compile(r"Ryan['’]s go\b"))
                         and re.search(r"(?i)\bdeploy\w*|--apply\b", s)],
                        f"{where}: the rollback's deploy waits for Ryan's go (one sentence)")
        for rx, what in ((r"destructiveChanges", "a `destructiveChanges` deploy"),
                         (r"\bsf project delete\b", "`sf project delete`"),
                         (r"(-X\s*|--method\s+)DELETE\b|\bDELETE\s+/services/", "an HTTP DELETE")):
            self.assertNotRegex(raw, rx, f"{where}: {what} deletes; the rollback restores and deletes nothing")

    # --- the plan ---------------------------------------------------------------------------------------------

    def test_a_plan_carries_the_reporting_deploy(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        rows = self.keep()
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        text = read(path)
        keys, _ = docs_index.frontmatter(text)
        self.assertIn("status", keys, f"{name}: frontmatter `status:`")
        word, problem = docs_index.status_of(keys["status"])
        self.assertIsNone(problem, f"{name}: {problem}")
        self.assertNotEqual(word, "superseded", f"{name}: the plan is the change in force")
        self.assertRegex(text.split("\n## ", 1)[0], self.TICKET,
                         f"{name}: name ticket #79 in the frontmatter, the title or the opening paragraph")
        self.assertRegex(text, r"(?m)^## Rollback\b", f"{name}: no `## Rollback` section")
        self.assertRegex(text, r"(?m)^## Result\b", f"{name}: no `## Result` section (its numbers come after the deploy)")

        where = f"{name}: `## Rollout`"
        raw = self.plan_part(path, "## Rollout", 40)
        flat_out = flat(raw)
        cl = self.clauses(raw)
        # the copies into Decommissioned, every report, by the tool, dry run then --apply
        cmds = self.commands(raw)
        self.assertTrue(cmds, f"{where}: copy each report into Decommissioned by `python3 tools/sf_report_folders.py "
                              "copy --vpn-off --kind report --id <id> --tag \"#79\"`")
        for c in cmds:
            self.assertIn("--vpn-off", c, f"{where}: the tool refuses to run without `--vpn-off`: {c[:160]!r}")
            tags = re.findall(r"--tag(?:=|\s+)(\S+)", c)
            self.assertTrue(tags and all(self.TICKET.search(t) for t in tags),
                            f"{where}: each copy is tagged `--tag \"#79\"`: {c[:160]!r}")
        for item in self.ITEMS:         # every report copied, by its own command: a dry run, then --apply
            r = rows[item]
            own = [c for c in cmds if [v.strip("`'\"") for v in re.findall(r"--id(?:=|\s+)(\S+)", c)] == [r["id"]]]
            self.assertTrue([c for c in own if "--apply" not in c] and [c for c in own if "--apply" in c],
                            f"{where}: copy item {item}'s report into Decommissioned, skip none: `python3 "
                            f"tools/sf_report_folders.py copy --vpn-off --kind report --id {r['id']} --tag \"#79\"` (the "
                            "dry run), then the same with `--apply`")
            for c in own:
                self.assertRegex(c, r"--kind(?:=|\s+)report\b", f"{where}: item {item} is a report (`--kind report`): "
                                                                f"{c[:160]!r}")
        self.assertIn("Decommissioned", flat_out, f"{where}: the copies go into Decommissioned")
        for s in cl:                    # no report left without its copy
            for m in self.NO_COPY.finditer(s):
                self.assertFalse(not self.d.locally_denied(s, m) and (self.items_named(s, rows)
                                                                      or re.search(r"(?i)\breports?\b", s))
                                 and not re.search(r"(?i)\bdashboard\b", s),
                                 f"{where}: every report (items 17-19) is copied into Decommissioned before it changes; "
                                 f"none changes in place without its copy: {s[:200]!r}")
        # the check-only, Ryan's go, the deploy
        self.assertTrue([s for s in cl if re.search(r"(?i)\bcheck-only\b", s) and "--dry-run" in s],
                        f"{where}: the check-only, `sf project deploy start --dry-run …`, in one sentence")
        go = re.compile(r"Ryan['’]s go\b")
        self.assertTrue([s for s in cl if self.stated(s, go) and re.search(r"(?i)\bdeploy", s)],
                        f"{where}: the deploy waits for Ryan's go (one sentence)")
        self.assertTrue([s for s in cl if self.stated(s, go) and "--apply" in s],
                        f"{where}: the copies' `--apply` waits for Ryan's go (one sentence)")
        # the read-back: retrieve after/, compare with build/
        self.assertTrue([s for s in cl if "after/" in s and "build/" in s and re.search(r"(?i)\bretriev\w*", s)
                         and re.search(r"(?i)\bcompar\w*|\bequals?\b|\bdiff\w*", s) and not self.d.denies(s)],
                        f"{where}: retrieve into `after/` and compare it with `build/` (one sentence)")
        # the SOQL check: each component against DHIS2__c; the test accounts absent
        self.assertTrue([s for s in cl if self.stated(s, re.compile(r"\bSOQL\b")) and "DHIS2__c" in s
                         and re.search(r"(?i)\bcomponents?\b", s)
                         and re.search(r"(?i)\blast complete month\b|\bLAST_MONTH\b", s)],
                        f"{where}: check each component against SOQL on `DHIS2__c` for the last complete month (one "
                        "sentence)")
        self.assertTrue([s for s in cl if re.search(r"(?i)\b(one|a|each)\s+partner['’]s\b|\bper partner\b|"
                                                    r"\bGROUP\s+BY\s+Account__c\b", s)
                         and self.stated(s, re.compile(r"\bSOQL\b|\bSELECT\b"))],
                        f"{where}: check one partner's number against SOQL too (one sentence: \"one partner's number\" "
                        "or `GROUP BY Account__c`)")
        self.assertTrue([s for s in cl if re.search(r"(?i)\btest\s+(accounts?|records?)\b", s)
                         and re.search(r"(?i)\b(absent|excluded|none|no|not|missing|0)\b", s)],
                        f"{where}: check that the test accounts' records are absent (one sentence)")
        # the order, read in the numbered steps
        steps = self.c.steps(raw, where)
        before = self.c.first(r"\bbefore/", steps, where, "the numbered steps start with a fresh retrieve into "
                                                          "`before/`")
        copies = [m.start() for m in re.finditer(r"sf_report_folders\.py\s+copy\b", steps)]
        self.assertTrue(copies, f"{where}: the copies by `tools/sf_report_folders.py copy` are a numbered step")
        check_only = self.c.first(r"(?i)check-only|--dry-run", steps, where, "no check-only in the numbered steps")
        # every real deploy (not the check-only, not a deploy said to wait or not to happen) after the check-only
        # and after the last copy
        deploys = []
        for m in re.finditer(r"(?i)\bdeploy\w*", steps):
            lo = max([steps.rfind(c, 0, m.start()) for c in ".;,"] + [-1]) + 1
            hi = min([i for i in (steps.find(c, m.end()) for c in ".;,") if i >= 0] + [len(steps)])
            clause = steps[lo:hi]
            if re.search(r"(?i)check-only|--dry-run|\bvalidat", clause) or self.d.NEGATION.search(steps[lo:m.start()]):
                continue
            # a reference to the deploy, not the deploy: "before the deploy", "until anything is deployed"
            if re.search(r"(?i)\b(before|until|ahead of|prior to|after)\s+(the\s+|any\s+|a\s+|its\s+|anything\s+"
                         r"(is\s+)?|something\s+(is\s+)?)?$", steps[lo:m.start()]):
                continue
            deploys.append(m.start())
        self.assertTrue(deploys, f"{where}: no deploy step after the check-only (on Ryan's go)")
        self.assertLess(check_only, deploys[0], f"{where}: the first deploy comes after the check-only (nothing is "
                                                "deployed before it)")
        self.assertLess(copies[-1], deploys[0], f"{where}: the first deploy comes after the last copy into "
                                                "Decommissioned (archive first)")
        after = [m.start() for m in re.finditer(r"\bafter/", steps) if m.start() > deploys[0]]
        soql = [m.start() for m in re.finditer(r"\bSOQL\b", steps) if m.start() > deploys[0]]
        self.assertLess(before, copies[0], f"{where}: the retrieve into `before/` comes before the copies")
        self.assertLess(copies[-1], check_only, f"{where}: every copy into Decommissioned comes before the check-only and "
                                                "the deploy (archive first)")
        self.assertTrue(after, f"{where}: the `after/` read-back comes after the deploy")
        self.assertTrue(soql, f"{where}: the SOQL check comes after the deploy")
        # the check-only and the deploy run from this change's build/, named in their own steps
        starts = [m.start() for m in re.finditer(r"(?:^|\s)\d+[.)]\s", steps)] + [len(steps)]

        def step_of(pos):
            return next(steps[a:b] for a, b in zip(starts, starts[1:]) if a <= pos < b)
        build = re.compile(r"(?<![\w/.<>-])(?:" + self.THIS_DIR + r"/)?build/")
        for what, pos in (("check-only", check_only), ("deploy", deploys[0])):
            self.assertRegex(step_of(pos), build, f"{where}: the {what} step names this change's build, "
                                                  "`data/sf_dash_reporting_<date>/build/` (or `build/`): "
                                                  f"{step_of(pos)[:200]!r}")
        others = sorted({p for p in self.PATH.findall(flat_out) if self.foreign_path(p)
                         and not re.fullmatch(self.THIS_DIR + r"/(before|build|after)/", p)})
        self.assertFalse(others, f"{where}: the Rollout works in this change's `data/sf_dash_reporting_<date>/` only "
                                 f"(and the copy tool's ledger folder), never another retrieve, build or backup: {others}")
        # the SOQL check runs the RUNBOOK subsection's signals
        self.assertTrue([s for s in sentences(flat_out, ".;") if re.search(r"\bSOQL\b|\bsignals?\b", s)
                         and (re.search(r"RUNBOOK", s) and "GLOW Club Reporting" in s
                              or re.search(r"RUNBOOK\.md#glow-club-reporting\b", s))],
                        f"{where}: the SOQL check runs the signals of the RUNBOOK's `### GLOW Club Reporting` (one sentence "
                        "naming the RUNBOOK and \"GLOW Club Reporting\", or linking `RUNBOOK.md#glow-club-reporting`)")
        self.sweep(raw, where)
        # the Result: a heading until the deploy; once the plan is done, its counts
        if word == "done":
            result = flat(md_part(path, "## Result").split("\n", 1)[-1])
            counts = [n for n in re.findall(r"(?<![\w./:-])\d[\d,]*(?![\w/:-])", re.sub(r"\b\d{4}-\d\d-\d\d\b", " ", result))]
            self.assertTrue(counts and re.search(r"\bSOQL\b", result),
                            f"{name}: `status: done`, so `## Result` gives the counts each component showed and SOQL "
                            "gave for the last complete month")


class ImplementationDashboardDocs(unittest.TestCase):
    """Ticket #76: the dashboard "GLOW Club Implementation" (D2, label "Implementation Dashboard") and its
    four reports, items 5-8 of `glow/sf_keep_list.csv`, by Partner and Month (Ryan, 2026-10-21), the period the
    last 12 months (`Period__c`, #128), the test-record rule (#70). Items 5, 7 and 8 count a `DHIS2__c` field
    (#74's check list in the RUNBOOK); item 6 counts the Jotform batches' `Module__c` on `Attendance_Batch__c`
    (Ryan on #74, the ticket's comments; RUNBOOK "Why the dashboards showed old data"). D2 is dynamic and the
    org is at its limit of 5 dynamic dashboards, so it has no API copy: its rollback is the `before/` retrieve;
    the four reports have copies in Decommissioned (Ryan, 2026-10-24, on the ticket). Ryan, 2026-10-24 (on the
    ticket, superseding the definition of done's "Partner filter and Month filter"): no Partner filter on any
    dashboard; the only dashboard filter is Partner Manager (`Assigned_Partner_Manager__c`), which reaches item 6
    through one new column on the shared report type `Attendance_Totals`
    (`Account__c.Parent.Assigned_Partner_Manager__c`), the Attendance reports unchanged; the reports stay grouped
    by Partner and Month with the last-12-months period and the test-record rule.

    The measures and labels are read from the CSV, not pinned; the fields are the RUNBOOK's (#74). No number
    that exists only after the live deploy is asserted: the plan's Result is checked to exist, not its counts.

    #197 (GLOW's review, Ryan 2026-11-02) changes three of these rules, so this class accepts its new ones and
    GlowReviewImplementationDocs checks them: the period may be `In_Reporting_Year__c equals true` (items 5-8, a
    SOQL signal's period too) in place of the last 12 months; D2 has a Month filter beside Partner Manager (still
    no Partner filter); item 6 may be grouped by `Module__c` then the partner (unique partners per module, the
    month from the Month filter) in place of the partner then the month."""

    longMessage = False         # the messages say what to fix
    RUNBOOK = os.path.join(REPO, "docs", "RUNBOOK.md")
    KEEP_LIST = os.path.join(REPO, "glow", "sf_keep_list.csv")
    PLANS = os.path.join(REPO, "docs", "plans", "*-sf-dash-implementation.md")
    # #195's reporting-year flag as a filter (`In_Reporting_Year__c equals true`, `In_Reporting_Year__c = true`)
    YEAR_ON = re.compile(r"\bIn_Reporting_Year__c\b[^.;]{0,25}?\btrue\b")
    MONTHLY = "## Monthly Report dashboards in Salesforce"
    PART = "### GLOW Club Implementation"
    GROUP = "GLOW Club Implementation"
    TICKET = re.compile(r"(?<![\w#])#76\b")
    # what each item counts (RUNBOOK "Why the dashboards showed old data", the check per item)
    FIELDS = {"5": "Did_you_implement_GLOW_Club_last_month_f__c",
              "6": "Module__c",
              "7": "Adapted_to_the_local_culture_or_context__c",
              "8": "Select_summits_completed_last_month__c"}
    BATCH_ITEM = "6"
    ROLLBACK = re.compile(r"(?i)\broll(s|ed|ing)?\s+(it\s+|them\s+)?back\b|\brollback\b|\brestor\w*|\brevert\w*|"
                          r"\b(put|puts|bring|brings|move|moves)\s+(\w+\s+){0,3}?back\b")
    BEFORE_DIR = re.compile(r"data/sf_dash_implementation_(\d{4}-\d\d-\d\d|<date>)/before/")
    NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}

    @classmethod
    def setUpClass(cls):
        cls.d = DecommissionedFoldersDocs()     # #69's helpers: locally_denied, contradictions, denies
        KeepListDocs.setUpClass()
        cls.k = KeepListDocs()                  # #70's helpers: assertTestRecordRule

    @staticmethod
    def norm(text):
        return DecommissionedFoldersDocs.norm(text)

    def clauses(self, text, ends=".;"):
        return sentences(self.norm(text), ends)

    def keep_rows(self):
        import csv
        with open(self.KEEP_LIST, encoding="utf-8", newline="") as f:
            return [r for r in csv.DictReader(f) if r["group"] == self.GROUP]

    def reports(self):
        rows = [r for r in self.keep_rows() if r["kind"] == "report"]
        self.assertEqual(sorted(r["item"] for r in rows), sorted(self.FIELDS),
                         f"glow/sf_keep_list.csv: the {self.GROUP!r} reports are items 5-8")
        return rows

    def dashboard(self):
        rows = [r for r in self.keep_rows() if r["kind"] == "dashboard"]
        self.assertEqual(len(rows), 1, f"glow/sf_keep_list.csv: one dashboard row for {self.GROUP!r}")
        return rows[0]

    def part(self):
        """The `### GLOW Club Implementation` part of the Monthly Report section, to the next `###` or `##`."""
        section = md_part(self.RUNBOOK, self.MONTHLY)
        m = re.search(r"^" + re.escape(self.PART) + r"(?!\w).*$", section, re.M)
        self.assertTrue(m, f"RUNBOOK section {self.MONTHLY[3:]!r}: no `{self.PART}` part under it (ticket #76)")
        rest = section[m.start():]
        nxt = re.search(r"\n#{1,3} ", rest)
        return rest[:nxt.start()] if nxt else rest

    @staticmethod
    def blocks(raw):
        """The part cut into units a reader takes as one: each table row, each list item with its continuation
        lines, each paragraph; in a fenced code block, each query with the comment lines just above it (`-- item 7`);
        flattened (dots kept)."""
        out, cur, fence, note = [], [], False, False
        for line in raw.splitlines():
            st = line.strip()
            if st.startswith("```") or fence:
                if st.startswith("```"):
                    fence, note, new = not fence, False, True
                elif not st:
                    note, new = False, True
                elif re.match(r"(--|#|//)", st):
                    new, note = not note, True
                elif re.match(r"(?i)SELECT\b", st):
                    new, note = not note, False
                else:
                    new, note = False, False
                if new and cur:
                    out.append(flat(" ".join(cur)))
                    cur = []
                if st and not st.startswith("```"):
                    cur.append(st)
                continue
            starts = re.match(r"(\||[-*+]\s|\d+[.)]\s|#)", st)
            if not st or starts:
                if cur:
                    out.append(flat(" ".join(cur)))
                cur = [st] if st else []
                if st.startswith("|") or st.startswith("#"):
                    out.append(flat(st))
                    cur = []
            else:
                cur.append(st)
        if cur:
            out.append(flat(" ".join(cur)))
        return out

    @staticmethod
    def names(row, text):
        """`text` names the item of `row`: GLOW's measure, its label today or its target label, or `item N`."""
        low = flat(text).lower()
        return (any(flat(row[k]).lower() in low for k in ("measure", "label_today", "label_target"))
                or re.search(r"(?i)\bitem\s+%s\b(?![-–]\d)" % re.escape(row["item"]), text) is not None)

    @staticmethod
    def soql(raw, obj):
        """Each SOQL statement in `raw` (inline code or a fenced block) that reads `obj`, up to the next backtick
        or the next SELECT (so the queries of one code block stay apart)."""
        tok = r"(?:(?!\bSELECT\b)[^`])"
        return [m.group(0) for m in re.finditer(r"(?is)\bSELECT\b%s{0,500}?\bFROM\s+%s\b%s{0,600}" % (tok, obj, tok),
                                                raw)]

    @staticmethod
    def _top_split(text):
        """(pieces, joiners, rest): `text` cut at AND / OR outside quotes and parentheses, up to a top-level
        GROUP BY, ORDER BY, HAVING or LIMIT (`rest` from there)."""
        pieces, joiners, depth, quote, start, i = [], [], 0, False, 0, 0
        while i < len(text):
            c = text[i]
            if quote:
                if c == "\\":
                    i += 2
                    continue
                if c == "'":
                    quote = False
            elif c == "'":
                quote = True
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            elif depth == 0 and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] in "_.$")):
                kw = re.match(r"(?i)(AND|OR|GROUP\s+BY|ORDER\s+BY|HAVING|LIMIT)\b", text[i:])
                if kw:
                    word = kw.group(1).upper()
                    if word in ("AND", "OR"):
                        pieces.append(text[start:i])
                        joiners.append(word)
                        i += kw.end()
                        start = i
                        continue
                    pieces.append(text[start:i])
                    return pieces, joiners, text[i:]
            i += 1
        pieces.append(text[start:])
        return pieces, joiners, ""

    @staticmethod
    def _wrapped(t):
        """`t` is one parenthesis around the whole term: `(a AND b)`, not `(a) AND (b)`."""
        if not (t.startswith("(") and t.endswith(")")):
            return False
        depth, quote = 0, False
        for i, c in enumerate(t):
            if quote:
                quote = c != "'"
            elif c == "'":
                quote = True
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0 and i != len(t) - 1:
                    return False
        return True

    def where_terms(self, q):
        """(terms, ored) of query `q`: its WHERE clause as AND-joined terms (whitespace flattened, a term wholly in
        parentheses opened and split again), and whether an OR joins anything at any of those levels. A trailing
        comment line or `;` ends the query. ([], False) without a WHERE."""
        q = re.split(r"\n\s*(?:--|#|//)|;", q)[0]
        m = re.search(r"(?i)\bWHERE\b", q)
        if not m:
            return [], False
        pieces, joiners, _ = self._top_split(q[m.end():])
        terms, ored, todo = [], "OR" in joiners, [flat(p) for p in pieces]
        while todo:
            t = todo.pop(0).strip()
            if self._wrapped(t):
                inner, j, _ = self._top_split(t[1:-1])
                ored = ored or "OR" in j
                todo = [flat(p) for p in inner] + todo
            elif t:
                terms.append(t)
        return terms, ored

    @staticmethod
    def has_term(terms, rx):
        return any(re.fullmatch(rx, t) for t in terms)

    DATE = r"\d{4}-\d\d-\d\d"
    TEST_TERMS = (r"(?i)Account__c\s*(!=|<>)\s*null", r"(?i)NOT\s+Account__r\.Name\s+LIKE\s+'%test%'")

    def period_terms(self, terms, field, month_fields=False):
        """A real period on `field` among AND-joined `terms`: `= LAST_N_MONTHS:12`, `= LAST_MONTH`, one month's
        date, or a `>=` and a `<=` date bound; with `month_fields`, also `Year__c = … AND Month__c = '…'` or
        `YearMonth__c = 202609`; since #197 also #195's `In_Reporting_Year__c = true`."""
        f, d = re.escape(field), self.DATE
        if self.has_term(terms, r"(?i)%s\s*=\s*(LAST_N_MONTHS:12|LAST_MONTH|%s)" % (f, d)):
            return True
        if self.has_term(terms, r"(?i)In_Reporting_Year__c\s*=\s*true"):
            return True
        if (self.has_term(terms, r"(?i)%s\s*>=?\s*%s" % (f, d))
                and self.has_term(terms, r"(?i)%s\s*<=?\s*%s" % (f, d))):
            return True
        return month_fields and ((self.has_term(terms, r"(?i)Year__c\s*=\s*'?\d{4}'?")
                                  and self.has_term(terms, r"(?i)Month__c\s*=\s*'[^']+'"))
                                 or self.has_term(terms, r"(?i)YearMonth__c\s*=\s*'?\d{6}'?"))

    def dhis2_ok(self, q):
        """A `DHIS2__c` query whose WHERE AND-joins the test-record rule, with no OR anywhere in it."""
        terms, ored = self.where_terms(q)
        return not ored and all(self.has_term(terms, rx) for rx in self.TEST_TERMS)

    def batch_ok(self, q):
        """Item 6's query: AND-joined Success, `Creator__c LIKE 'Jotform%'` and a real period on
        `Attendance_Date__c`, no OR, grouped by `Module__c`."""
        terms, ored = self.where_terms(q)
        return (not ored and self.has_term(terms, r"(?i)Processing_Status__c\s*=\s*'Success'")
                and self.has_term(terms, r"(?i)Creator__c\s+LIKE\s+'Jotform%'")
                and self.period_terms(terms, "Attendance_Date__c")
                and re.search(r"(?is)\bGROUP\s+BY\b[^`]*?(?<!\w)Module__c\b", q) is not None)

    def stated(self, s, rx):
        return any(not self.d.locally_denied(s, m) for m in rx.finditer(s))

    @staticmethod
    def field_rx(field):
        """`field` as a whole name (`DHIS2__c.Account__c` and `$Account__c` contain `Account__c`; a longer name
        such as `Select_all_GLOW_Club_modules_implemented__c` does not contain `Module__c`)."""
        return re.compile(r"(?<!\w)%s\b" % re.escape(field))

    def mentions(self, rows, text):
        """[(start, item)]: each place `text` names an item of `rows` (GLOW's measure, a label, `item N`, or the
        item's number as a table row's first cell)."""
        out, low = set(), text.lower()
        for r in rows:
            for k in ("measure", "label_today", "label_target"):
                out |= {(m.start(), r["item"]) for m in re.finditer(re.escape(flat(r[k]).lower()), low)}
            out |= {(m.start(), r["item"]) for m in
                    re.finditer(r"(?i)\bitem\s+%s\b(?![-–]\d)|^\|\s*%s\s*\|" % ((re.escape(r["item"]),) * 2), text)}
        return sorted(out)

    def owner(self, unit, pos, marks):
        """The item a name at `pos` of `unit` is said of: the nearest item named before it in its comma segment,
        else after it in that segment, else the nearest named before it in the unit, else after it."""
        lo = max([m.end() for m in re.finditer(r",", unit[:pos])] or [0])
        hi = pos + (re.search(r",|$", unit[pos:]).start())
        for pick in ([i for p, i in marks if lo <= p < pos][-1:], [i for p, i in marks if pos < p < hi][:1],
                     [i for p, i in marks if p < pos][-1:], [i for p, i in marks if p > pos][:1]):
            if pick:
                return pick[0]
        return None

    def units(self, raw):
        """The part cut into units: each table row whole, each list item and paragraph cut into clauses at `.`
        and `;` (raw names kept: `DHIS2__c.Account__c` is not cut)."""
        out = []
        for b in self.blocks(raw):
            out += [b] if b.startswith("|") else sentences(b, ".;")
        return out

    def pairings(self, raw, rows):
        """{item: [unit, ...]} where a field of `self.FIELDS` is said of its own item, and [(unit, field, item)]
        where a field is said of another item."""
        good, wrong = {}, []
        for u in self.units(raw):
            marks = self.mentions(rows, u)
            for item, field in self.FIELDS.items():
                for m in self.field_rx(field).finditer(u):
                    who = self.owner(u, m.start(), marks)
                    if who == item:
                        good.setdefault(item, []).append(u)
                    elif who is not None:
                        wrong.append((u, field, who))
        return good, wrong

    # a stated rollback redeploys or restores something; a build/ is never what it brings back
    REDEPLOY = re.compile(r"(?i)\bre-?deploy\w*|\brestor\w*|\brevert\w*|\broll(s|ed|ing)?\s+(it\s+|them\s+)?back\b|"
                          r"\brollback\b|\b(put|puts|bring|brings)\s+(\w+\s+){0,3}?back\b")
    DEPLOY = re.compile(r"(?i)\bdeploy\w*")
    OLDER = re.compile(r"(?i)\b(older|old|earlier|previous|prior|stale|another|former|past|archived|"
                       r"last\s+(week|month)['’]s|yesterday['’]s)\s+(\w+\s+)?builds?\b")
    EQUAL = re.compile(r"(?i)\b(equals?|equal to|identical|matches|the same as|unchanged from|no difference\w*)\b")
    COND = re.compile(r"(?i)\b(only|while|as long as|provided)\b")
    EVEN = re.compile(r"(?i)\beven\s+(while|if|when|though)\b|\bregardless\b|\bwhether or not\b|\bno matter\b")
    DIFFERS = re.compile(r"(?i)\bdiffer\w*|\bdifferent\b|\bchanged\b|\bdoes\s*n[o']t\s+(equal|match)\b|\bmismatch\w*")

    def build_redeployed(self, s):
        """A `build/` (or a build) that clause `s` says is redeployed or restored, not denied where it is said.
        Plain "deploy" counts only in a clause about the rollback (rollback, before/, otherwise, instead)."""
        rollbackish = bool(self.ROLLBACK.search(s) or "before/" in s or re.search(r"(?i)\botherwise\b|\binstead\b", s))
        verbs = [self.REDEPLOY] + ([self.DEPLOY] if rollbackish else [])
        neg = self.d.NEGATION
        for m in re.finditer(r"(?i)\bbuilds?\b", s):
            pre = re.split(r"[,;—–(]|\bbut\b|\bhowever\b", s[:m.start()])[-1]
            post = re.split(r"[,;)—–]|\bbut\b", s[m.end():])[0]
            if any(v.search(pre) for v in verbs) and not neg.search(pre):
                return True
            for v in verbs:
                vm = v.search(post)
                if vm and not neg.search(pre) and not neg.search(post[:vm.start()]):
                    return True
        return False

    def assertRollback(self, raw, where, runbook):
        """The rollback in `raw`: the reports from their copies in Decommissioned; this change's `before/` only
        while a fresh retrieve equals `after/` (stated, not denied, not "even while"); no build redeployed and
        an older build only ever denied; nothing deleted, nothing optional. With `runbook`, also the count of
        copies, D2's missing API copy and a stated denial of an older build."""
        cl = self.clauses(raw, ".;")
        back = [s for s in cl if self.stated(s, self.ROLLBACK)]
        self.assertTrue([s for s in back if re.search(r"(?i)\bcop(y|ies)\b", s) and "Decommissioned" in s
                         and re.search(r"(?i)\breports?\b", s)],
                        f"{where}: say the reports are rolled back from their copies in Decommissioned (open the copy, "
                        "Save As or move it back), in one sentence")
        cond = []
        for s in [s for s in cl if "before/" in s and "after/" in s and re.search(r"(?i)\bfresh\b", s)
                  and re.search(r"(?i)\bretriev\w*", s)
                  and (self.stated(s, self.ROLLBACK) or self.stated(s, re.compile(r"(?i)\b(re)?deploy\w*")))]:
            eq = [m for m in self.EQUAL.finditer(s) if not self.d.locally_denied(s, m)
                  and self.COND.search(s[:m.start()])]
            if eq and not self.EVEN.search(s):
                cond.append(s)
        self.assertTrue(cond, f"{where}: say the `before/` retrieve is redeployed only while a fresh retrieve equals "
                              "`after/` (nothing changed in the org since this deploy), in one sentence: the equality "
                              "stated as the condition, not denied, and not \"even while\" or \"even if\"")
        for s in sentences(self.norm(raw), ".;:"):
            if "before/" not in s:
                continue
            diff = [m for m in self.DIFFERS.finditer(s) if not self.d.locally_denied(s, m)]
            redo = [m for m in list(self.REDEPLOY.finditer(s)) + list(self.DEPLOY.finditer(s))
                    if not self.d.locally_denied(s, m)]
            self.assertFalse(diff and redo, f"{where}: `before/` is never redeployed when a fresh retrieve differs "
                                            f"from `after/` (stop and ask instead): {s[:200]!r}")
        found = [s for s in cl if self.OLDER.search(s)]
        if runbook:
            self.assertTrue([s for s in found if all(self.d.locally_denied(s, m) for m in self.OLDER.finditer(s))],
                            f"{where}: say the rollback never redeploys an older build (DECISIONS 2026-10-16), in one "
                            "sentence")
        self.assertEqual([s[:160] for s in found if not all(self.d.locally_denied(s, m) for m in self.OLDER.finditer(s))],
                         [], f"{where}: an older (earlier, prior, previous, last week's, yesterday's) build is never a "
                             "rollback; it is only ever denied")
        self.assertEqual([s[:160] for s in sentences(flat(raw), ".;") if self.build_redeployed(s)], [],
                         f"{where}: no `build/` is ever redeployed or restored as a rollback (the reports come from "
                         "their copies, the dashboard from this change's `before/`)")
        if runbook:
            n = len(self.reports())
            count = re.compile(r"(?i)\b(%d|%s|each|every|all)\s+(\w+\s+){0,3}?reports?\b" % (n, self.NUMBER_WORDS[n]))
            self.assertTrue([s for s in cl if count.search(s) and re.search(r"(?i)\bcop(y|ies)\b", s)
                             and "Decommissioned" in s and not self.d.denies(s)],
                            f"{where}: say the {n} reports each have a copy in Decommissioned (one sentence, not negated)")
            no_copy = re.compile(r"(?i)\brefus\w*|\blimit\b|\bno\s+(\w+\s+)?cop(y|ies)\b|\bnot\s+(been\s+|be\s+)?copied\b|"
                                 r"\bwithout\s+(a\s+|an\s+)?(\w+\s+)?copy\b")
            self.assertTrue([s for s in self.clauses(raw, ".") if re.search(r"(?i)\bdashboard\b|\bD2\b", s)
                             and re.search(r"(?i)\bdynamic\b", s)
                             and no_copy.search(s) and "before/" in s],
                            f"{where}: say the dashboard (D2) is dynamic and has no API copy (the org's limit of 5 "
                            "dynamic dashboards), so its rollback is the `before/` retrieve, in one sentence")
            rb = " ".join(s for s in cl if self.ROLLBACK.search(s) or "before/" in s or "Decommissioned" in s)
        else:
            rb = raw
        self.d.assertNoContradiction(rb, f"{where} (the rollback)", rollback=True)

    def plan_path(self):
        found = sorted(glob.glob(self.PLANS))
        self.assertEqual(len(found), 1, "docs/plans/: one plan `YYYY-MM-DD-sf-dash-implementation.md` for ticket #76 "
                                        f"(found {[os.path.basename(p) for p in found]})")
        self.assertRegex(os.path.basename(found[0]), r"^\d{4}-\d\d-\d\d-sf-dash-implementation\.md$",
                         "docs/plans/: the plan is named `YYYY-MM-DD-sf-dash-implementation.md`")
        return found[0]

    def plan_part(self, path, heading, least):
        name = os.path.relpath(path, REPO)
        part = md_part(path, heading)
        raw = part.split("\n", 1)[1] if "\n" in part else ""
        body = self.norm(raw)
        self.assertNotRegex(body, r"(?i)\b(TBD|TODO|TBA|FIXME)\b", f"{name}: `{heading}` is a placeholder")
        distinct = {w.lower() for w in re.findall(r"[A-Za-z]\w*", body)}
        self.assertGreaterEqual(len(distinct), least, f"{name}: `{heading}` says too little (at least {least} "
                                                      "distinct words)")
        return raw

    # --- the RUNBOOK ---------------------------------------------------------------------------------------

    def test_the_runbook_describes_implementation_by_partner_and_month(self):
        where = f"RUNBOOK section {self.MONTHLY[3:]!r}, {self.PART[4:]!r}"
        part = self.part()
        text = self.norm(part)
        raw_flat = flat(part)
        dash = self.dashboard()
        self.assertIn(dash["label_today"], raw_flat,
                      f"{where}: name the dashboard by its label {dash['label_today']!r} ({dash['item']} in "
                      "`glow/sf_keep_list.csv`)")
        blocks = self.blocks(part)
        rows = self.reports()
        # each of items 5-8: named, and its field said of it in one table row or one clause (the item named
        # nearest before the field), never another item's field
        good, wrong = self.pairings(part, rows)
        self.assertEqual([f"{f} said of item {who}: {u[:160]!r}" for u, f, who in wrong], [],
                         f"{where}: each field is said of its own item (5 `{self.FIELDS['5']}`, 6 `Module__c`, 7 "
                         f"`{self.FIELDS['7']}`, 8 `{self.FIELDS['8']}`), one per table row or clause")
        for row in rows:
            item, field = row["item"], self.FIELDS[row["item"]]
            at = f"{where}, item {item}"
            self.assertTrue(self.names(row, part),
                            f"{at}: name it by GLOW's measure {row['measure']!r} or its label {row['label_today']!r}")
            self.assertTrue(good.get(item),
                            f"{at}: say what it counts, `{field}`, in its own table row or clause (the item named "
                            "nearest before the field)")
            if item == self.BATCH_ITEM:
                mine = [b for b in blocks if self.names(row, b)]
                self.assertTrue([b for b in mine if self.field_rx(field).search(b)
                                 and re.search(r"\bAttendance_Batch__c\b", b)],
                                f"{at}: say, where it is named, that it counts the Jotform batches' `Module__c` on "
                                "`Attendance_Batch__c` (not a `DHIS2__c` field: the form's module field is blank since "
                                "2025-10)")
        # the form's module field (blank since 2025-10) is never item 6's source: named only as what item 6's
        # `Module__c` replaces ("instead of", "in place of", "no longer counts", "replaced", "blank since")
        old = "Select_all_GLOW_Club_modules_implemented__c"
        strong = re.compile(r"(?i)\b(instead of|in place of|rather than|replac\w*)\b")
        before_old = re.compile(r"(?i)\b(instead of|in place of|rather than|replac\w*|no longer|not|never|nor|"
                                r"retired|formerly|used to|previously)\b")
        after_old = re.compile(r"(?i)\b(is|was|has been|were|are)\s+(now\s+)?(replaced|retired|superseded|dropped)\b|"
                               r"\bblank since\b|\bno longer\b")
        counts_old = re.compile(r"(?i)\b(counts?|counted|counting|reads?|measures?|sums?|shows?|uses?)\b")
        for s in [c for b in blocks for c in sentences(flat(b), ".;")]:
            for m in self.field_rx(old).finditer(s):
                pre = re.split(r"[,;]|\bbut\b", s[:m.start()])[-1]
                post = re.split(r"[,;]|\bbut\b", s[m.end():])[0]
                replaced = (before_old.search(pre[-80:]) is not None
                            or (after_old.search(post[:100]) is not None
                                and not re.search(r"(?i)\b(not|never)\s+(been\s+)?blank|n['’]t\s+(been\s+)?blank",
                                                  post)))
                counted = [c for c in counts_old.finditer(pre) if not self.d.locally_denied(pre, c)
                           and not re.search(r"(?i)\b(formerly|used to|previously|once)\s+$", pre[:c.start()])]
                self.assertTrue(replaced and not (counted and not strong.search(pre[counted[-1].end():])),
                                f"{where}: item 6 counts the Jotform batches' `Module__c`; the form's `{old}` is "
                                "named only as what it replaces (\"instead of\", \"no longer counts\", \"replaced\", "
                                f"\"blank since 2025-10\"), never as what a report counts: {s[:200]!r}")
        # the dashboard's one filter is Partner Manager (Ryan, 2026-10-24, on the ticket: no Partner filter on any
        # dashboard; the reports stay grouped by Partner and Month). Sentences cut at `.` only: a `;` inside a
        # parenthesis does not part the filter from the dashboard.
        filt = re.compile(r"(?i)\bfilters?\b")
        mgr = re.compile(r"(?i)\bPartner\s+Manager\b")
        self.assertTrue([s for s in sentences(raw_flat, ".") if re.search(r"(?i)\bdashboard\b|\bD2\b", s)
                         and self.stated(s, filt) and self.stated(s, mgr)
                         and self.stated(s, re.compile(r"DHIS2__c\$Account__c\.Assigned_Partner_Manager__c\b"))],
                        f"{where}: say the dashboard's filter is Partner Manager, on "
                        "`DHIS2__c$Account__c.Assigned_Partner_Manager__c` (a sentence naming the dashboard, its filter, "
                        "Partner Manager and the field, not negated)")
        # item 6 is reached through the shared type `Attendance_Totals`' new column, the Attendance reports unchanged
        col = re.compile(r"(?<![\w$])Account__c\.Parent\.Assigned_Partner_Manager__c\b")
        self.assertTrue([s for s in sentences(raw_flat, ".;") if re.search(r"\bAttendance_Totals\b", s)
                         and re.search(r"(?i)\b(columns?|fields?)\b", s) and self.stated(s, col)
                         and re.search(r"(?i)\b(gets?|gains?|adds?|added|new|one more)\b", s)],
                        f"{where}: say the report type `Attendance_Totals` gets one column, "
                        "`Account__c.Parent.Assigned_Partner_Manager__c` (the partner's manager through the club's "
                        "parent), so the Partner Manager filter reaches item 6 (one clause, not negated)")
        self.assertTrue([s for s in sentences(raw_flat, ".;") if re.search(r"(?i)\bfilters?\b|\bPartner Manager\b", s)
                         and self.stated(s, re.compile(r"Attendance_Batch__c\$Account__c\.Parent\."
                                                       r"Assigned_Partner_Manager__c\b"))],
                        f"{where}: say the Partner Manager filter reaches item 6 on "
                        "`Attendance_Batch__c$Account__c.Parent.Assigned_Partner_Manager__c` (in a clause about the filter)")
        same = re.compile(r"(?i)\bunchanged\b|\buntouched\b|\b(stay|stays|remain|remains)\s+as\s+(they|it)\s+(are|were|is)\b|"
                          r"\b(are|is|stay|stays)\s+(not|never)\s+(changed|touched|edited)\b")
        self.assertTrue([s for s in sentences(raw_flat, ".;") if re.search(r"\bAttendance\b[^.;]{0,60}?\breports\b|"
                                                                          r"\breports\s+on\s+(that|this|the)\s+(report\s+)?type\b", s)
                         and [m for m in same.finditer(s) if not self.d.locally_denied(s, m)
                              or re.search(r"(?i)\b(not|never)\s+(changed|touched|edited)\b", m.group(0))]],
                        f"{where}: say the Attendance reports on `Attendance_Totals` are unchanged by the new column "
                        "(one clause, not negated)")
        # no Partner filter: named only where it is denied ("no Partner filter", "instead of a Partner filter") or
        # said to be dropped (#76 also denied a Month filter; since #197 D2 has one: GlowReviewImplementationDocs)
        gone = re.compile(r"(?i)^\W*(is|was|are|were)\s+(\w+\s+)?(dropped|removed|replaced|retired|gone)\b")
        for word in ("Partner",):
            rx = re.compile(r"(?i)\b%s\s+filters?\b" % word)
            hits = [(s, m) for s in sentences(raw_flat, ".;") for m in rx.finditer(s)]
            self.assertEqual([s[:160] for s, m in hits if not self.d.locally_denied(s, m)
                              and not gone.search(s[m.end():])], [],
                             f"{where}: the dashboard has no {word} filter (Ryan, 2026-10-24: the only dashboard filter "
                             f"is Partner Manager); a {word} filter is named only to deny it")
        self.assertTrue([s for s, m in [(s, m) for s in sentences(raw_flat, ".;")
                                        for m in re.finditer(r"(?i)\bPartner\s+filters?\b", s)]
                         if self.d.locally_denied(s, m) or gone.search(s[m.end():])],
                        f"{where}: say the dashboard has no Partner filter (Ryan, 2026-10-24), e.g. \"no Partner filter\"")
        # grouped by Partner and Month, with the period, in one unit (a table row or a clause)
        units = self.units(part)
        grp = re.compile(r"(?i)\bgroup(s|ed|ing)?\b")
        acct, period, adate = (self.field_rx(f) for f in ("Account__c", "Period__c", "Attendance_Date__c"))
        twelve = re.compile(r"(?i)\bLAST_N_MONTHS:12\b|\blast\s+12\s+months\b|\blast\s+twelve\s+months\b")
        partner, month = re.compile(r"(?i)\bpartners?\b"), re.compile(r"(?i)\bmonths?\b|\bmonthly\b")
        self.assertTrue([u for u in units if self.stated(u, grp) and re.search(r"(?<![\w.])(DHIS2__c\.)?Account__c\b", u)
                         and self.stated(u, acct) and self.stated(u, period) and partner.search(u)
                         and month.search(u)],
                        f"{where}: say items 5, 7 and 8 are grouped by Partner (`DHIS2__c.Account__c`) and by month "
                        "(`Period__c`, #128; never `CreatedDate`), in one table row or clause")
        # the period: the last 12 months (#76), or since #197 `In_Reporting_Year__c equals true`
        self.assertTrue([u for u in units if (self.stated(u, period) and self.stated(u, twelve))
                         or self.stated(u, self.YEAR_ON)],
                        f"{where}: give items 5, 7 and 8's period, the last 12 months of `Period__c` "
                        "(`LAST_N_MONTHS:12`), or since #197 `In_Reporting_Year__c equals true`, in one table row or "
                        "clause")
        item6 = [r for r in rows if r["item"] == self.BATCH_ITEM]
        six = [u for u in units if self.mentions(item6, u)]
        # item 6's grouping: the partner and the month of `Attendance_Date__c` (#76), or since #197 `Module__c` and
        # the partner (unique partners per module; the month from D2's Month filter)
        self.assertTrue([u for u in six if self.stated(u, grp) and partner.search(u)
                         and self.stated(u, re.compile(r"(?<![\w$])Account__[cr]\.Parent\b"))
                         and ((self.stated(u, adate) and month.search(u))
                              or self.stated(u, self.field_rx("Module__c")))],
                        f"{where}, item 6: say it is grouped by the partner, the club's parent (`Account__c.Parent`), "
                        "and by month of `Attendance_Date__c` (the session date), or since #197 by `Module__c` and the "
                        "partner, in a table row or clause naming item 6")
        self.assertTrue([u for u in units if (self.stated(u, adate) and self.stated(u, twelve))
                         or (self.stated(u, self.YEAR_ON)
                             and (re.search(r"\bAttendance_Batch__c\b", u) or adate.search(u) or self.mentions(item6, u)))],
                        f"{where}, item 6: give its period, the last 12 months of `Attendance_Date__c`, or since #197 "
                        "`In_Reporting_Year__c equals true` on `Attendance_Batch__c`, in one table row or clause")
        self.k.assertTestRecordRule(text, where)
        # the SOQL signal: DHIS2__c for items 5, 7, 8 (test accounts excluded), Attendance_Batch__c for item 6
        dhis2 = self.soql(part, "DHIS2__c")
        batch = self.soql(part, "Attendance_Batch__c")
        self.assertTrue(dhis2, f"{where}: give the SOQL signal for items 5, 7 and 8, a `SELECT … FROM DHIS2__c` "
                               "(in backticks or a code block)")
        self.assertEqual([q[:160] for q in dhis2 + batch if re.search(r"(?i)(?<![!<>])=\s*null\b", q)], [],
                         f"{where}: a SOQL signal never asks for `<field> = null` (it would count nothing)")
        # each query's WHERE is cut into its AND-joined terms; an OR anywhere in it fails the query (it would let
        # the test records or another status back in)
        self.assertTrue([q for q in dhis2 if self.dhis2_ok(q)],
                        f"{where}: the `DHIS2__c` SOQL leaves out the test records as the reports do, AND-joined in its "
                        "WHERE with no OR: `Account__c != null AND (NOT Account__r.Name LIKE '%test%')`")
        for item in ("5", "7", "8"):
            f, others = self.FIELDS[item], [self.FIELDS[i] for i in ("5", "7", "8") if i != item]
            frx = self.field_rx(f)
            self.assertTrue([q for q in dhis2 if self.dhis2_ok(q) and frx.search(q)
                             and self.period_terms(self.where_terms(q)[0], "Period__c", month_fields=True)
                             and (re.search(r"(?is)\bGROUP\s+BY\b[^`]*?(?<!\w)%s\b" % re.escape(f), q)
                                  or not any(self.field_rx(o).search(q) for o in others))],
                            f"{where}, item {item}: give its own SOQL signal on `DHIS2__c`: a query that reads `{f}`, "
                            "AND-joins the test-record rule and a period (`Period__c = LAST_N_MONTHS:12`, one month "
                            "such as `Period__c = 2026-09-01`, a `>=`/`<=` range, or `Year__c = … AND Month__c = '…'`), "
                            "has no OR, and either `GROUP BY` the field or no other component's field (one query per "
                            "component)")
        self.assertTrue([q for q in batch if self.batch_ok(q)
                         and not re.search(r"(?i)\bNOT\b[^`]{0,20}?\b(Processing_Status__c|Creator__c)\b|"
                                           r"\bProcessing_Status__c\s*(!=|<>)|\bCreator__c\s*(!=|<>)", q)],
                        f"{where}: give item 6's SOQL signal, `SELECT Module__c, COUNT(Id) FROM Attendance_Batch__c "
                        "WHERE Processing_Status__c = 'Success' AND Creator__c LIKE 'Jotform%' AND Attendance_Date__c = "
                        "LAST_N_MONTHS:12 GROUP BY Module__c` (the three AND-joined, no OR; the period "
                        "`= LAST_N_MONTHS:12`, `= LAST_MONTH`, a `>=`/`<=` date range or, since #197, "
                        "`In_Reporting_Year__c = true`)")
        # one partner's number: the suffix inside a full query that passes the rules (or one manager's partners)
        one = r"(?i)%s\s*=\s*'[^']*'"
        self.assertTrue([q for q in dhis2 if self.dhis2_ok(q)
                         and (self.has_term(self.where_terms(q)[0], one % r"(Account__r\.Name|Account__c)")
                              or self.has_term(self.where_terms(q)[0],
                                               one % r"Account__r\.Assigned_Partner_Manager__(c|r\.Name)"))],
                        f"{where}: give one partner's `DHIS2__c` SOQL: a full query with the test-record rule and "
                        "`AND Account__r.Name = '<partner>'` (or one manager's: `AND "
                        "Account__r.Assigned_Partner_Manager__c = '…'`)")
        self.assertTrue([q for q in batch if self.batch_ok(q)
                         and (self.has_term(self.where_terms(q)[0], one % r"Account__r\.Parent\.Name")
                              or self.has_term(self.where_terms(q)[0],
                                               one % r"Account__r\.Parent\.Assigned_Partner_Manager__(c|r\.Name)"))],
                        f"{where}, item 6: give one partner's SOQL: item 6's full query with `AND Account__r.Parent.Name "
                        "= '<partner>'` (the club's parent; or one manager's: `AND "
                        "Account__r.Parent.Assigned_Partner_Manager__c = '…'`)")

    def test_the_implementation_rollback_names_the_copies_and_the_before_folder(self):
        where = f"RUNBOOK section {self.MONTHLY[3:]!r}, {self.PART[4:]!r}"
        part = self.part()
        self.assertRegex(part, self.TICKET, f"{where}: name ticket #76 (the copies in Decommissioned carry its tag)")
        self.assertRegex(flat(part), self.BEFORE_DIR,
                         f"{where}: name this change's retrieve `data/sf_dash_implementation_<date>/before/`")
        self.assertRollback(part, where, runbook=True)

    # --- the plan ---------------------------------------------------------------------------------------------

    def test_a_plan_carries_the_implementation_deploy(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        text = read(path)
        keys, _ = docs_index.frontmatter(text)
        self.assertIn("status", keys, f"{name}: frontmatter `status:`")
        word, problem = docs_index.status_of(keys["status"])
        self.assertIsNone(problem, f"{name}: {problem}")
        self.assertNotEqual(word, "superseded", f"{name}: the plan is the change in force")
        self.assertRegex(text.split("\n## ", 1)[0], self.TICKET,
                         f"{name}: name ticket #76 in the frontmatter, the title or the opening paragraph")
        self.assertRegex(text, r"(?m)^## Result\b", f"{name}: no `## Result` section")
        rollback = self.plan_part(path, "## Rollback", 15)
        raw = self.plan_part(path, "## Rollout", 40)
        where = f"{name}: `## Rollout`"
        flat_out = flat(raw)
        cl = self.clauses(raw, ".;")
        self.assertRegex(flat_out, r"(?i)\bVPN off\b|--vpn-off", f"{where}: VPN off before any `sf` call")
        self.assertRegex(flat_out, self.BEFORE_DIR,
                         f"{where}: retrieve live into `data/sf_dash_implementation_<date>/before/`")
        self.assertTrue([s for s in cl if re.search(r"(?i)\bcop(y|ies)\b", s) and "Decommissioned" in s
                         and not self.d.denies(s)],
                        f"{where}: each report is copied into Decommissioned before it changes (one sentence)")
        self.assertRegex(flat_out, r"sf_report_folders\.py\s+copy\b[^`\n]*?--tag(=|\s+)[\"']?#76\b",
                         f"{where}: the copies by `tools/sf_report_folders.py copy … --tag \"#76\"`")
        self.assertTrue([s for s in self.clauses(text, ".") if re.search(r"(?i)\bdashboard\b|\bD2\b", s)
                         and re.search(r"(?i)\bdynamic\b", s) and "before/" in s],
                        f"{name}: say the dashboard (D2) is dynamic, has no API copy, and its rollback is `before/`")
        self.assertTrue([s for s in cl if re.search(r"(?i)(check-only|--dry-run)[^.;]*?\bdeploy", s)
                         and not self.d.denies(s)],
                        f"{where}: validate check-only before the deploy (one sentence, in that order)")
        self.assertTrue([s for s in cl if re.search(r"Ryan['’]s go\b", s) and re.search(r"(?i)\bdeploy", s)
                         and not self.d.denies(s)],
                        f"{where}: the deploy waits for Ryan's go (one sentence)")
        # the compare verb's objects are `after/` and `build/` (either order, or "it" for `after/` named before):
        # never `before/` against `build/`
        compare = re.compile(r"(?i)\bcompar\w*|\bdiff\b|\bequals?\b|\bidentical\b")

        def compares_after_build(s):
            for m in compare.finditer(s):
                if self.d.locally_denied(s, m):
                    continue
                obj = re.split(r"[,:;—–(]", s[m.end():])[0]
                dirs = re.findall(r"\b(before|after|build)/", obj)
                if "build" in dirs and "before" not in dirs and ("after" in dirs or (
                        re.match(r"\s*(it|them|that|this)\b", obj) and "after/" in s[:m.start()])):
                    return True
            return False
        self.assertTrue([s for s in cl if "after/" in s and "build/" in s and compares_after_build(s)],
                        f"{where}: read back: retrieve into `after/` and compare `after/` with `build/` (one sentence, "
                        "the comparison's objects `after/` and `build/`, not `before/`, not denied)")
        not_run = re.compile(r"(?i)\b(is|are|was|be|been)\s+(not|never)\s+(run|checked|queried|compared|done)\b|"
                             r"\b(not|never)\s+(run|checked|queried|compared)\b|\bskip\w*")
        soql = [s for s in cl if [m for m in re.finditer(r"\bSOQL\b|\bSELECT\b", s) if not self.d.locally_denied(s, m)]
                and not not_run.search(s)]
        # the SOQL step says what is compared: the SOQL numbers against (equal to, matching) the components
        cmp_rx = re.compile(r"(?i)\b(equals?|equal\s+to|match(es|ing)?|compar\w*|against|the\s+same\s+as|agrees?\s+with)\b")
        cmp_ok = (lambda s: [m for m in cmp_rx.finditer(s) if not self.d.locally_denied(s, m)]
                  and re.search(r"(?i)\bcomponents?\b|\bdashboard\b|\bitem\s+[5-8]\b", s))
        self.assertTrue([s for s in soql if "DHIS2__c" in s and cmp_ok(s)],
                        f"{where}: check each component against SOQL on `DHIS2__c`: say the SOQL numbers equal (match, "
                        "are compared with) the dashboard's components (one sentence, not denied)")
        self.assertTrue([s for s in soql if "Attendance_Batch__c" in s and cmp_ok(s)],
                        f"{where}: check item 6 against SOQL on `Attendance_Batch__c`: say the SOQL number equals "
                        "(matches) item 6's component (one sentence, not denied)")
        # the order, in the numbered steps: copies, check-only, deploy, read-back, SOQL
        steps = CategoryFoldersDocs.steps(self, raw, where)
        copies = [m.start() for m in re.finditer(r"sf_report_folders\.py\s+copy\b", steps)]
        self.assertTrue(copies, f"{where}: the copies are a numbered step")
        check_only = CategoryFoldersDocs.first(self, r"(?i)check-only", steps, where, "no check-only in the numbered steps")
        deploys = [s for s in sentences(steps, ".;,") if re.search(r"(?i)\bdeploy(s|ing)?\b", s)
                   and not re.search(r"(?i)check-only|--dry-run|\bvalidat", s)]
        self.assertTrue(deploys, f"{where}: no deploy step (after the check-only, on Ryan's go)")
        deploy = steps.index(deploys[0])
        self.assertLess(copies[0], check_only, f"{where}: the copies come before the check-only and the deploy")
        self.assertLess(check_only, deploy, f"{where}: the check-only comes before the deploy")
        # Ryan's go before the deploy: every deploy in the steps either is "on Ryan's go" or has Ryan's go between
        # the check-only and it (a go given earlier, for the copies, is not the deploy's go)
        go_rx = re.compile(r"Ryan['’]s go\b")
        gos = [m.start() for m in go_rx.finditer(steps) if not self.d.locally_denied(steps, m)]
        self.assertTrue(gos, f"{where}: the deploy waits for Ryan's go (a numbered step)")
        at, early = 0, []
        for seg in sentences(steps, ".;,"):
            at = steps.find(seg, at)
            dm = re.search(r"(?i)\bdeploy(s|ing)?\b", seg)
            if (dm and not re.search(r"(?i)check-only|--dry-run|\bvalidat", seg)
                    and not self.d.locally_denied(seg, dm) and not go_rx.search(seg)
                    and not [g for g in gos if check_only < g < at]):
                early.append(seg[:160])
        self.assertEqual(early, [], f"{where}: Ryan's go comes before the deploy (\"on Ryan's go, deploy\"), never "
                                    "after it")
        self.assertTrue([m for m in re.finditer(r"\bafter/", steps) if m.start() > deploy],
                        f"{where}: the read-back into `after/` comes after the deploy")
        self.assertTrue([m for m in re.finditer(r"\bSOQL\b|\bSELECT\b", steps) if m.start() > deploy],
                        f"{where}: the SOQL check comes after the deploy")
        self.d.assertNoContradiction(raw, where)
        where = f"{name}: `## Rollback`"
        self.assertIn("Decommissioned", rollback, f"{where}: the reports come back from their copies in Decommissioned")
        self.assertIn("before/", rollback, f"{where}: the dashboard comes back from this change's `before/` retrieve")
        self.assertRollback(rollback, where, runbook=False)


class ObservationsDashboardDocs(unittest.TestCase):
    """Ticket #77: the dashboard "GLOW Club Observations" (D3 in `glow/sf_keep_list.csv`) and its reports, items
    9-11, by Partner and Month. Ryan, 2026-10-24 on #77: the default period is the last 12 months through
    `DHIS2__c.Period__c` (#128); every report groups by the partner (`DHIS2__c.Account__c`), then the month; the
    test-record rule of #70 on every report; labels stay; copies into Decommissioned first
    (`tools/sf_report_folders.py copy`); every deploy waits for Ryan's go.

    The measures, labels and ids are read from `glow/sf_keep_list.csv`; each item's `DHIS2__c` field and the shape
    of its SOQL check (a picklist counted by value, a number summed, item 11 the partners with a count above 0)
    come from the RUNBOOK's check for these items (#74, "Why the dashboards showed old data"). The RUNBOOK's
    `### GLOW Club Observations` and the plan `docs/plans/<date>-sf-dash-observations.md` are what is read."""

    longMessage = False         # the messages say what to fix
    RUNBOOK = os.path.join(REPO, "docs", "RUNBOOK.md")
    KEEP_LIST = CategoryFoldersDocs.KEEP_LIST
    PLANS = os.path.join(REPO, "docs", "plans", "*-sf-dash-observations.md")
    MONTHLY = "## Monthly Report dashboards in Salesforce"
    PART = "### GLOW Club Observations"
    TICKET = re.compile(r"(?<![\w#])#77\b")
    ITEMS = ("9", "10", "11")
    DASHBOARD = "D3"
    # each item's DHIS2__c field and the clauses its own SOQL must carry ON THAT FIELD (RUNBOOK, #74: 9 is a
    # picklist, SELECT <field>, COUNT(Id) ... GROUP BY <field>; 10 a number, SUM(<field>); 11 the same field `> 0`,
    # counted: the partners who observed)
    F9, F10 = "did_you_submit_your_GC_observation_form__c", "GC_sessions_did_you_observe_last_month__c"
    FIELDS = {
        "9": (F9, (re.compile(r"(?i)\bGROUP\s+BY\s+" + F9 + r"\b(?!\s*,)"), re.compile(r"(?i)\bCOUNT\s*\("))),
        "10": (F10, (re.compile(r"(?i)\bSUM\s*\(\s*" + F10 + r"\s*\)"),)),
        "11": (F10, (re.compile(r"\b" + F10 + r"\s*(>\s*0(?![.\d])|>=\s*1(?![.\d]))"), re.compile(r"(?i)\bCOUNT\s*\("))),
    }
    # what every item's SOQL carries: DHIS2__c, the report's test-record rule and one month, the last complete one
    SOQL_FROM = re.compile(r"(?i)\bSELECT\b.*\bFROM\s+DHIS2__c\b")
    NOT_BLANK_SOQL = re.compile(r"\bAccount__c\s*(!=|<>)\s*null\b")
    NO_TEST_SOQL = re.compile(r"(?i)\bNOT\s*\(?\s*Account__r\.Name\s+LIKE\s+'%test%'")
    ONE_MONTH = re.compile(r"\bPeriod__c\s*=\s*LAST_MONTH\b|\bYearMonth__c\s*=\s*20\d\d(0[1-9]|1[0-2])\b|"
                           r"\bYear__c\s*=\s*20\d\d\s+AND\s+Month__c\s*=\s*'[A-Z][a-z]+'|"
                           r"\bPeriod__c\s*=\s*20\d\d-\d\d-01\b")
    ONE_PARTNER = re.compile(r"(?i)\bAND\s+Account__(c|r\.Name)\s*=\s*'")
    # what turns a query's clauses into something other than all of them, or cuts its rows
    LOOSE_SOQL = re.compile(r"(?i)\bOR\b|\bLIMIT\b")
    # a dashboard filter on the partner or the month ("Partner filter", "Partner and Month filters", "filters by
    # month"); "Partner Manager filter" is not one (Ryan, 2026-10-24 on #77: the only dashboard filter is Partner
    # Manager)
    PM_FILTER = re.compile(r"Assigned_Partner_Manager__c\b|\bPartner Manager\b")     # norm() makes `x.Assigned_…` `x_Assigned_…`
    PARTNER_OR_MONTH_FILTER = re.compile(
        r"(?i)\b(Partner|Month)\s+(and|or|&|/)\s+(Partner|Month)\s+filters?\b|"
        r"\b(Partner|Month)\s+filters?\b|"
        r"\bfilters?\s+(on|by|for)\s+(the\s+|a\s+|one\s+)?(partners?|months?)\b(?!\s+Manager)|"
        r"\bfilters?[,:]?\s+(Partner|Month)\s+(and|or|&)\s+(Partner|Month)\b")
    REMOVED = re.compile(r"(?i)\b(tak(e|es|en|ing)\b[^.;]{0,100}?\boff|remov\w*|comes?\s+off|moved?\s+off|"
                         r"no longer on|drop(s|ped)?)\b")
    CODE = re.compile(r"(`+)(.+?)\1")
    # what makes a statement of the current design a past, removed or abandoned one (anywhere in its sentence)
    UNDONE = re.compile(r"(?i)\b(remov\w*|dropp\w*|delet\w*|replaced|no longer|retired|gone|unused|alone|abandon\w*|"
                        r"revert\w*|was|were|had|used to|formerly|previous(ly)?|earlier|old|former|"
                        r"rather than|instead|disabled|turned off|missing|lacks?|without)\b")
    # softeners #69's sweep does not know
    MORE_SOFT = re.compile(r"(?i)\b(at most (once|twice|\w+ times)|rarely|seldom|informational|advisory|"
                           r"for information( only)?|best[- ]effort|nice to have|if convenient|not required|"
                           r"not mandatory|once a (year|quarter)|from time to time|occasionally|now and then)\b")
    # this change's own retrieve folder (the outline: data/sf_dash_observations_<date>/before/)
    BEFORE = re.compile(r"data/sf_dash_observations_(\d{4}-\d\d-\d\d|<date>)/before/"
                        r"|data/sf_glow_review_(\d{4}-\d\d|<month>)/[\w<>-]+/before/")
    OLDER_BUILD = re.compile(r"(?i)\b(older|earlier|previous|old|stale|another\s+change['’]s)\s+(\w+\s+)?"
                             r"(builds?|retrieves?|deploys?|`?build/`?|`?before/`?)")
    ONLY_WHILE = re.compile(r"(?i)\bonly\s+(while|if|when|as long as|so long as)\b|\bas long as\b|\bprovided\b")
    EQUALS = re.compile(r"(?i)\bequal\w*|\bmatch\w*|\bsame as\b|\bidentical\b|\bno differences?\b|\bunchanged\b")
    RESTORE = re.compile(r"(?i)\b(restor\w*|revert\w*|roll\w*\s+back|rollback|undo|bring\w*\s+back|put\w*\s+back)\b")

    @classmethod
    def setUpClass(cls):
        cls.d = DecommissionedFoldersDocs()     # #69's helpers: locally_denied, contradictions, denies
        KeepListDocs.setUpClass()
        cls.k = KeepListDocs()                  # #70's helper: assertTestRecordRule

    @staticmethod
    def norm(text):
        return DecommissionedFoldersDocs.norm(text)

    def keep(self):
        import csv
        with open(self.KEEP_LIST, encoding="utf-8", newline="") as f:
            rows = {r["item"]: r for r in csv.DictReader(f)}
        for item in self.ITEMS + (self.DASHBOARD,):
            self.assertIn(item, rows, f"glow/sf_keep_list.csv: no row {item}")
            self.assertEqual(rows[item]["group"], "GLOW Club Observations",
                             f"glow/sf_keep_list.csv: row {item} is in the group \"GLOW Club Observations\"")
        return rows

    def part(self):
        """The `### GLOW Club Observations` part of the Monthly Report section, to the next `###` or `##`."""
        section = md_part(self.RUNBOOK, self.MONTHLY)
        m = re.search(r"^" + re.escape(self.PART) + r"(?!\w).*$", section, re.M)
        self.assertTrue(m, f"RUNBOOK section {self.MONTHLY[3:]!r}: no `{self.PART}` part under it (ticket #77)")
        rest = section[m.start():]
        nxt = re.search(r"\n#{1,3} ", rest)
        return rest[:nxt.start()] if nxt else rest

    @staticmethod
    def blocks(text):
        """`text` cut into blocks, each flattened: a table row, a top-level list item with its indented lines
        (sub-items included), or a paragraph."""
        out, cur = [], None
        for line in text.splitlines():
            st = line.strip()
            if not st:
                cur = None
                continue
            starts = (st.startswith("|") or st.startswith("#")
                      or (not line[:1].isspace() and re.match(r"([-*+]|\d+[.)])\s", st)))
            if cur is None or starts:
                cur = [st]
                out.append(cur)
            else:
                cur.append(st)
        return [flat(" ".join(b)) for b in out]

    def plan_path(self):
        found = sorted(glob.glob(self.PLANS))
        self.assertEqual(len(found), 1, "docs/plans/: one plan `YYYY-MM-DD-sf-dash-observations.md` for ticket #77 "
                                        f"(found {[os.path.basename(p) for p in found]})")
        self.assertRegex(os.path.basename(found[0]), r"^\d{4}-\d\d-\d\d-sf-dash-observations\.md$",
                         "docs/plans/: the plan is named `YYYY-MM-DD-sf-dash-observations.md`")
        return found[0]

    def plan_part(self, path, heading, least):
        return RetiredReportsDocs.plan_part(self, path, heading, least)

    def stated(self, s, rx):
        return any(not self.d.locally_denied(s, m) for m in rx.finditer(s))

    @staticmethod
    def labelled(text, r):
        """`text` names the report `r` by its label today or, since #198 (GLOW's review of 2026-11-02), by its
        target label: the keep list's two columns differ for the rows #198 renames."""
        return r["label_today"] in text or r["label_target"] in text

    def assertRollback(self, raw, where, whole=True):
        """The rollback: from the Decommissioned copies, or from this change's `before/` only while a fresh retrieve
        equals `after/`; never from an older build; nothing deleted, nothing optional. #69's contradiction sweep
        reads all of `raw` when `whole`, else only its sentences about the rollback (a restore, `before/`, an
        older build)."""
        text = flat(raw)
        restore_or_deploy = re.compile(self.RESTORE.pattern + r"|\b(re-?)?deploy\w*")
        # what the rollback says: all of `raw` (the plan's Rollback), or the RUNBOOK's sentences about a rollback
        cl = [s for s in sentences(text, ".;")
              if whole or self.RESTORE.search(s) or "before/" in s or self.OLDER_BUILD.search(s)]
        self.assertTrue([s for s in cl if "Decommissioned" in s and re.search(r"(?i)\bcop(y|ies)\b", s)
                         and self.stated(s, self.RESTORE)],
                        f"{where}: say the rollback restores from the copies in Decommissioned (one sentence, not "
                        "negated)")
        self.assertRegex(text, self.BEFORE, f"{where}: name this change's retrieve, "
                                            "`data/sf_dash_observations_<date>/before/` (or, since #198, "
                                            "`data/sf_glow_review_<month>/<topic>/before/`)")
        # only this change's before/: no other retrieve folder, no other ticket's build or retrieve (#198's own
        # retrieve folder, `data/sf_glow_review_<month>/`, is this change's since GLOW's review of 2026-11-02)
        for s in cl:
            for p in re.findall(r"\bdata/[^\s`'\"()]*?/before/", s):
                self.assertTrue(p.startswith(("data/sf_dash_observations_", "data/sf_glow_review_")),
                                f"{where}: the rollback restores only this change's `before/` "
                                f"(`data/sf_dash_observations_<date>/before/`, since #198 "
                                f"`data/sf_glow_review_<month>/<topic>/before/`), not {p!r}: {s[:200]!r}")
            for m in restore_or_deploy.finditer(s):
                near = s[max(0, m.start() - 30):m.end() + 30]
                other = [t for t in re.findall(r"(?<![\w#])#(\d+)\b", near) if t not in ("77", "198")]
                self.assertFalse(other, f"{where}: the rollback restores this change's (#77) copies or `before/`, not "
                                        f"ticket #{other[:1]}'s: {s[:200]!r}")
        # the guard: before/ only while a fresh retrieve EQUALS after/
        eq = self.EQUALS.pattern.replace("(?i)", "")
        tied = re.compile(r"(?i)\bretriev\w*[^.;]{0,80}?(" + eq + r")[^.;]{0,40}?after/|"
                          r"after/[^.;]{0,40}?(" + eq + r")[^.;]{0,80}?\bretriev\w*")
        guarded = [s for s in cl if "before/" in s and "after/" in s and self.ONLY_WHILE.search(s)
                   and tied.search(s) and self.stated(s, restore_or_deploy)]
        self.assertTrue(guarded, f"{where}: say, in one sentence, that `before/` is redeployed only while a fresh "
                                 "retrieve equals `after/` (the equality between the retrieve and `after/`)")
        for s in guarded:
            self.assertFalse(re.search(r"(?i)\bdiffer\w*|\bmismatch\w*|\bnot\s+(equal|match|the same)\w*|"
                                       r"\bdoes\s+not\s+(equal|match)\b|\bdoesn['’]t\s+(equal|match)\b|"
                                       r"\b(even if|even when|regardless|"
                                       r"whether or not)\b", s),
                             f"{where}: `before/` only while the fresh retrieve equals `after/`, never when it differs "
                             f"(no \"differ\", \"not equal\", \"even if\" in that sentence): {s[:200]!r}")
        never = [s for s in cl for m in self.OLDER_BUILD.finditer(s) if self.d.locally_denied(s, m)]
        self.assertTrue(never, f"{where}: say a rollback never deploys an older build (DECISIONS 2026-10-16), in one "
                               "sentence")
        for s in cl:
            for m in self.OLDER_BUILD.finditer(s):
                self.assertTrue(self.d.locally_denied(s, m),
                                f"{where}: an older build is never a rollback (DECISIONS 2026-10-16): {s[:200]!r}")
        # the folder names hold the words "before" and "after", which #69's sweep reads as a time limit
        plain = re.sub(r"\b(before|after|build)/", "DIR/", " ".join(cl) if not whole else raw)
        self.d.assertNoContradiction(plain, where, rollback=True)
        self.assertNotSoftened(plain, where)

    def assertNotSoftened(self, text, where):
        for s in sentences(flat(text), ".;:?!"):
            for m in self.MORE_SOFT.finditer(s):
                self.assertTrue(self.d.locally_denied(s, m),
                                f"{where}: the step is the rule, not {m.group(0)!r}: {s[:200]!r}")

    def numbered_steps(self, raw):
        """The Rollout's numbered steps (`1. …`), each flattened with its indented lines, in order."""
        steps, cur = [], None
        for line in raw.splitlines():
            if re.match(r"\d+[.)]\s", line):
                cur = [line]
                steps.append(cur)
            elif cur is not None and line.strip() and line[:1].isspace():
                cur.append(line)
            elif cur is not None and line.strip():
                cur = None
        return [flat(" ".join(s)) for s in steps]

    # --- the RUNBOOK ---------------------------------------------------------------------------------------

    def test_the_runbook_describes_observations_by_partner_and_month(self):
        where = f"RUNBOOK section {self.MONTHLY[3:]!r}, {self.PART[4:]!r}"
        rows = self.keep()
        part = self.part()
        text = flat(part)
        blocks = self.blocks(part)
        dash = rows[self.DASHBOARD]
        self.assertTrue(dash["id"] in text or dash["label_today"] in text,
                        f"{where}: name the dashboard as the org holds it, its Id {dash['id']} or its label "
                        f"{dash['label_today']!r} (row {self.DASHBOARD} of `glow/sf_keep_list.csv`)")
        # each measure: GLOW's words and the report's label, its DHIS2__c field and its own SOQL, in one block
        spans = [m.group(2) for m in self.CODE.finditer(text)]
        partner_variant = [c for c in spans if self.SOQL_FROM.search(c) and self.ONE_PARTNER.search(c)
                           and not self.LOOSE_SOQL.search(c)]
        for item in self.ITEMS:
            r = rows[item]
            field, shapes = self.FIELDS[item]
            self.assertIn(r["measure"], text, f"{where}: name item {item}'s measure as `glow/sf_keep_list.csv` gives "
                                              f"it, {r['measure']!r}")
            self.assertTrue(self.labelled(text, r), f"{where}: name item {item}'s report by its label, "
                                                    f"{r['label_today']!r} or, since #198, {r['label_target']!r}")
            others = {self.FIELDS[i][0] for i in self.ITEMS} - {field}
            mine = [b for b in blocks if r["measure"] in b and self.labelled(b, r) and field in b
                    and not [f for f in others if f in b]]
            self.assertTrue(mine, f"{where}: item {item} ({r['measure']!r}, the report {r['label_today']!r}) and the "
                                  f"`DHIS2__c` field it counts, `{field}` (and no other item's field), in one table "
                                  "row, list item or paragraph")
            # the item's own SOQL: one code span in its block, on its field, with the report's filters
            soql = [c for b in mine for c in (m.group(2) for m in self.CODE.finditer(b)) if self.SOQL_FROM.search(c)]
            self.assertTrue(soql, f"{where}: item {item}'s SOQL signal in its own row, item or paragraph, as code "
                                  "(`SELECT … FROM DHIS2__c …`)")
            need = [(rx, f"on its field: {rx.pattern!r}") for rx in shapes] + [
                (self.NOT_BLANK_SOQL, "`Account__c != null`"),
                (self.NO_TEST_SOQL, "`NOT Account__r.Name LIKE '%test%'`"),
                (self.ONE_MONTH, "one month, the last complete one (`Period__c = LAST_MONTH`, `YearMonth__c = "
                                 "202609`, or `Year__c = 2026 AND Month__c = 'September'`)")]
            good = [c for c in soql if all(rx.search(c) for rx, _ in need) and not [f for f in others if f in c]
                    and not self.LOOSE_SOQL.search(c)]
            missing = [what for rx, what in need if not [c for c in soql if rx.search(c)]]
            self.assertTrue(good, f"{where}: item {item}'s SOQL (one code span, `{field}` and no other item's field, "
                                  "its clauses joined by AND: no OR, no LIMIT; item 9 grouped by its field alone) "
                                  f"carries every clause; missing {missing or 'some clause in the same span'}")
            self.assertTrue([c for c in good if self.ONE_PARTNER.search(c)] or partner_variant,
                            f"{where}: item {item}'s SOQL for one partner's month: `AND Account__r.Name = '<partner>'` "
                            "in its span, or one per-partner query (`SELECT … FROM DHIS2__c … AND Account__r.Name = "
                            "'<partner>'`, no OR, no LIMIT) in code")
        cl = sentences(self.norm(part), ".;")
        # the dashboard's one filter is Partner Manager (Ryan, 2026-10-24 on #77), stated as what it has now
        filt = re.compile(r"(?i)\bfilters?\b")
        said = [s for s in cl if re.search(r"(?i)\bdashboard", s) and self.stated(s, self.PM_FILTER)
                and self.stated(s, filt) and not self.UNDONE.search(s)]
        self.assertTrue(said, f"{where}: say the dashboard's filter is Partner Manager (`Assigned_Partner_Manager__c`), "
                              "in one sentence, present tense, not negated (no \"removed\", \"was\", \"no longer\" … in "
                              "it)")
        # ... and never a Partner or a Month dashboard filter (a report's grouping by Partner and Month is not one)
        # (since #198, GLOW's review of 2026-11-02, it has a Month filter: GlowReviewObservationsDocs' ticket; only a
        # Partner filter stays denied)
        for s in cl:
            if re.search(r"(?i)\breports?\b", s) and not re.search(r"(?i)\bdashboard", s):
                continue
            for m in self.PARTNER_OR_MONTH_FILTER.finditer(s):
                if not re.search(r"(?i)\bPartner\b", m.group(0)):       # a Month filter alone
                    continue
                self.assertTrue(self.d.locally_denied(s, m) or self.UNDONE.search(s),
                                f"{where}: the dashboard has no Partner filter (Ryan, 2026-10-24 on #77; a Month filter "
                                f"since #198): {s[:200]!r}")
        # item 16 is taken off this dashboard (#77; #78 reworks it on its own dashboard)
        r16 = rows["16"]
        names16 = re.compile(re.escape(r16["label_today"]) + "|" + r16["id"] + r"|\bitem\s+16\b", re.I)
        self.assertTrue([s for s in sentences(flat(part), ".;") if names16.search(s) and self.stated(s, self.REMOVED)],
                        f"{where}: say item 16 ({r16['label_today']!r}, {r16['id']}) is taken off this dashboard, in one "
                        "sentence, not negated")
        # every report grouped by the partner, then the month: `group(ed) by … Account__c … Period__c` in one clause
        order = re.compile(r"(?i)\bgroup(s|ed|ing)?\s+(\w+\s+){0,3}?by\b[^.;:]{0,80}?Account__c\b[^.;:]{0,80}?"
                           r"\bPeriod__c\b")
        grouped = [s for s in cl if self.stated(s, order) and not self.UNDONE.search(s)
                   and not re.search(r"(?i)\bonly\b|\bnot\b|\bnever\b", s)]
        self.assertTrue(grouped, f"{where}: say each report groups by the partner (`DHIS2__c.Account__c`), then the "
                                 "month (`Period__c`): `grouped by … Account__c … Period__c` in one clause, not negated, "
                                 "not \"alone\", \"unused\", \"only\" or past")
        self.assertFalse([s for s in grouped if re.search(r"\bCreatedDate\b", s)],
                         f"{where}: the month is `Period__c`, never `CreatedDate`")
        # the default period: the reporting year since #198 (it was the last 12 months through Period__c)
        twelve = r"(LAST_N_MONTHS:12\b|last 12 months\b)"
        past = re.compile(r"(?i)\b(was|were|used to|formerly|previous(ly)?|no longer|old|former|earlier|until)\b|"
                          r"(?<!range )(?<!range: )\ball[- ]time\b")
        # (since #198, GLOW's review of 2026-11-02, the reporting year: `In_Reporting_Year__c equals true`)
        # D3's period is the reporting year now; the last 12 months is said only as what it replaced
        in_year = re.compile(r"\bIn_Reporting_Year__c\b")
        self.assertTrue([s for s in cl if self.stated(s, in_year) and not self.d.denies(s) and not past.search(s)],
                        f"{where}: say the default period is the reporting year, `In_Reporting_Year__c equals true` "
                        "(#198, GLOW's review of 2026-11-02), in one sentence, as the default now (no \"was\", \"old\", "
                        "\"previously\", \"until\")")
        replaced = re.compile(past.pattern + r"|(?i:\b(replac\w*|in place of|instead of|became|becomes|superseded|"
                                             r"rather than)\b)")
        for s in cl:
            prose = re.sub(r"`[^`]*\bSELECT\b[^`]*`", " ", s)       # a query is a check, not a claim
            for m in re.finditer(twelve, prose, re.I):
                if not re.search(r"(?i)Period__c|\bperiod\b|\bdefault\b|\bfilters?\b", prose):
                    continue
                self.assertTrue(replaced.search(prose) or self.d.locally_denied(prose, m),
                                f"{where}: since #198 D3's period is the reporting year; the last 12 months "
                                f"({m.group(0)!r}) is said only as what it replaced (\"until #198\", \"was\", \"in place "
                                f"of\"): {s[:200]!r}")
        # the filters: the test-record rule (#70) as a report filter, nothing negated between its two halves
        self.k.assertTestRecordRule(self.norm(part), where)
        for s in sentences(self.norm(part), ".;"):
            a, b = self.k.NOT_BLANK.search(s), self.k.NO_TEST.search(s)
            if a and b:
                mid = s[min(a.end(), b.end()):max(a.start(), b.start())]
                self.assertFalse(self.d.NEGATION.search(mid) or self.k.REJECT.search(mid) or re.search(r"\bOR\b", mid),
                                 f"{where}: the two halves of the test-record rule are joined by AND, nothing negated "
                                 f"or rejected between them: {s[:200]!r}")

    def test_the_observations_rollback_names_the_copies_and_the_before_folder(self):
        # the RUNBOOK's part says how to roll back ...
        self.assertRollback(self.part(), f"RUNBOOK section {self.MONTHLY[3:]!r}, {self.PART[4:]!r}", whole=False)
        # ... and so does the plan's Rollback
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        raw = self.plan_part(path, "## Rollback", 15)
        self.assertRollback(raw, f"{name}: `## Rollback`")
        for rx, what in ((r"destructiveChanges", "a `destructiveChanges` deploy"),
                         (r"\bsf project delete\b", "`sf project delete`"),
                         (r"(-X\s*|--method\s+)DELETE\b|\bDELETE\s+/services/", "an HTTP DELETE")):
            self.assertNotRegex(raw, rx, f"{name}: `## Rollback`: {what} deletes; the rollback restores and deletes "
                                         "nothing")

    # --- the plan ---------------------------------------------------------------------------------------------

    def test_a_plan_carries_the_observations_deploy(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        rows = self.keep()
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        text = read(path)
        keys, _ = docs_index.frontmatter(text)
        self.assertIn("status", keys, f"{name}: frontmatter `status:`")
        word, problem = docs_index.status_of(keys["status"])
        self.assertIsNone(problem, f"{name}: {problem}")
        self.assertNotEqual(word, "superseded", f"{name}: the plan is the change in force")
        self.assertRegex(text.split("\n## ", 1)[0], self.TICKET,
                         f"{name}: name ticket #77 in the frontmatter, the title or the opening paragraph")
        self.assertRegex(text, r"(?m)^## Result\b", f"{name}: no `## Result` section")
        raw = self.plan_part(path, "## Rollout", 40)
        where = f"{name}: `## Rollout`"
        flat_out = flat(raw)
        cl = sentences(flat_out, ".;")
        # the copies: every item, the dashboard and its three reports, each the `--id` of a copy command of its kind,
        # tagged with the ticket
        copies = [flat(seg) for seg in re.split(r"`+|\n\s*\n", raw) if re.search(r"sf_report_folders\.py\s+copy\b", seg)]
        self.assertTrue(copies, f"{where}: the copies by `python3 tools/sf_report_folders.py copy --vpn-off --kind … "
                                "--id … --tag \"#77\"`")
        for c in copies:
            self.assertIn("--vpn-off", c, f"{where}: the tool refuses to run without `--vpn-off`: {c[:160]!r}")
            tags = re.findall(r"--tag(?:=|\s+)[\"']?(#?\w+)", c)
            self.assertTrue(tags and set(tags) == {"#77"},
                            f"{where}: every copy carries this ticket, `--tag \"#77\"`: {c[:160]!r}")
        for item in self.ITEMS + (self.DASHBOARD,):
            kind = rows[item]["kind"]
            self.assertTrue([c for c in copies if rows[item]["id"] in re.findall(r"--id(?:=|\s+)[\"']?(\w+)", c)
                             and re.search(r"--kind(=|\s+)" + kind + r"\b", c)],
                            f"{where}: copy item {item} ({rows[item]['label_today']!r}) into Decommissioned; skip none: "
                            f"a copy command with `--kind {kind} --id {rows[item]['id']}`")
        self.assertTrue([s for s in cl if re.search(r"(?i)\bcop(y|ies)\b", s) and "Decommissioned" in s
                         and re.search(r"(?i)\bbefore\b", s) and not self.d.denies(s)],
                        f"{where}: say the copies go to Decommissioned before anything changes (one sentence)")
        # the check-only, then Ryan's go, then the deploy
        self.assertTrue([s for s in cl if re.search(r"(?i)(check-only|--dry-run)[^.;]*?\bdeploy", s)
                         and not self.d.denies(s)],
                        f"{where}: validate check-only (`sf project deploy start --dry-run`) before the deploy (one "
                        "sentence, in that order)")
        late = re.compile(r"(?i)\b(afterwards?|after\s+(the\s+|it\s+is\s+|it['’]s\s+)?deploy\w*|once\s+(it\s+is\s+)?"
                          r"deployed|later|retroactive\w*|post[- ]hoc|after the fact|informed|told|notified)\b")
        for s in cl:
            if re.search(r"Ryan['’]s go\b", s):
                self.assertFalse(late.search(s), f"{where}: Ryan's go comes before the deploy, never after it: "
                                                 f"{s[:200]!r}")
        # the read-back: retrieve into after/ and compare with build/
        self.assertTrue([s for s in cl if "after/" in s and "build/" in s and re.search(r"(?i)\bretriev\w*", s)
                         and re.search(r"(?i)\bcompar\w*|\bequal\w*|\bdiff\w*|\bmatch\w*", s) and not self.d.denies(s)],
                        f"{where}: read back: retrieve into `after/` and compare it with `build/` (one sentence)")
        # the SOQL check: each component against DHIS2__c, and no test account's records
        self.assertTrue([s for s in cl if re.search(r"\bSOQL\b", s) and "DHIS2__c" in s and not self.d.denies(s)],
                        f"{where}: check each component against SOQL on `DHIS2__c` (one sentence)")
        absent = re.compile(r"(?i)\b(no|zero|0|none of the)\s+(\w+\s+){0,3}?(records?|rows?)\b|"
                            r"\b(records?|rows?)\b[^.;]{0,40}?\b(absent|excluded|left out|are 0|count 0|zero)\b|"
                            r"\b(absent|excluded|left out)\b[^.;]{0,40}?\b(records?|rows?)\b")
        unchecked = re.compile(r"(?i)\bno\s+(\w+\s+)?checks?\b|\bnot\s+(\w+\s+)?(checked|verified|tested|confirmed)\b|"
                               r"\bunchecked\b|\bwithout\s+(a\s+|any\s+)?check\w*|\bskip\w*\b|\bassum\w*")
        tests = [s for s in cl if re.search(r"(?i)\btest\s+(accounts?|records?)\b", s)]
        self.assertTrue([s for s in tests if absent.search(s) and not unchecked.search(s)],
                        f"{where}: check that a test account's records are absent from every component (one sentence: "
                        "\"no records\", \"absent\", \"0 rows\"), not \"no check\"")
        for s in tests:
            self.assertFalse(unchecked.search(s), f"{where}: the test accounts' absence is checked, not skipped or "
                                                  f"assumed: {s[:200]!r}")
        # the order, in the numbered steps: copies, check-only, Ryan's go, deploy, read-back, SOQL
        steps = CategoryFoldersDocs.steps(self, raw, where)
        copy_at = [m.start() for m in re.finditer(r"sf_report_folders\.py\s+copy\b", steps)]
        check_only = re.search(r"(?i)check-only|--dry-run", steps)
        self.assertTrue(copy_at and check_only, f"{where}: the copies and the check-only are numbered steps")
        self.assertLess(copy_at[-1], check_only.start(), f"{where}: every copy into Decommissioned comes before the "
                                                         "check-only and the deploy")
        deploys = [m for m in re.finditer(r"[^.;,]+", steps) if m.start() > check_only.start()
                   and re.search(r"(?i)\bdeploy", m.group(0))
                   and not re.search(r"(?i)check-only|--dry-run|\bvalidat", m.group(0))]
        self.assertTrue(deploys, f"{where}: no deploy step after the check-only (on Ryan's go)")
        deploy = deploys[0]
        goes = [m.start() for m in re.finditer(r"Ryan['’]s go\b", steps)]
        self.assertTrue([g for g in goes if check_only.start() < g < deploy.end()],
                        f"{where}: Ryan's go comes between the check-only and the deploy (or in the deploy's own "
                        "clause: \"On Ryan's go, deploy\")")
        after = [m.start() for m in re.finditer(r"\bafter/", steps) if m.start() > deploy.start()]
        self.assertTrue(after, f"{where}: the read-back into `after/` comes after the deploy (a later step)")
        # the SOQL check after the deploy: the three items, one partner, against DHIS2__c
        later = [s for s in self.numbered_steps(raw) if re.search(r"\bSOQL\b", s) and steps.find(s[:40]) > deploy.start()]
        self.assertTrue(later, f"{where}: the SOQL check is a numbered step after the deploy")

        def names(s, item):
            r = rows[item]
            return (r["id"] in s or r["label_today"] in s or r["measure"] in s
                    or re.search(r"(?i)\bitems?\s+(\d+\s*(,|and|&)\s*)*" + item + r"\b", s))
        whole = re.compile(r"(?i)\bitems\s+9\s*(-|–|to)\s*11\b|\b9,\s*10\s*(,\s*)?and\s+11\b")
        fields = (re.compile(self.F9), re.compile(self.F10))
        good = [s for s in later if (whole.search(s) or all(names(s, i) for i in self.ITEMS)
                                     or all(f.search(s) for f in fields))
                and re.search(r"(?i)\b(one|a|each|single|every)\s+partner\b|\bper partner\b|Account__r\.Name\s*=", s)]
        self.assertTrue(good, f"{where}: the SOQL step names the three items (items 9-11, their report Ids or labels, "
                              "or their fields) and checks one partner's month too, not one count for the whole org")
        raw_plain = re.sub(r"\b(before|after|build)/", "DIR/", raw)
        self.d.assertNoContradiction(raw_plain, where)
        self.assertNotSoftened(raw_plain, where)

    # --- the live rollout of 2026-10-25 and item 11's fix forward ------------------------------------------------
    #
    # #77 on 2026-10-25: steps 1-6 ran (copies, check-only, deploy, read-back, refresh); item 11's component
    # (01aRP0000089gWVYAY) failed the refresh with 406 "One or more of the fields selected in the component is no
    # longer available in the report". Cause (Analytics describe, the reviewer's finding confirmed on #77): item
    # 11's report has its record count OFF (`<params><name>co</name><value>0</value></params>`, describe
    # `hasRecordCount: false`, since before/), so its aggregates list only its Sum and no RowCount, while its
    # component measures RowCount. Not the Sum: item 10's report sums the same column with co=1 and lists Sum AND
    # RowCount; item 9 has co=1 and RowCount. The fix: item 11's report gets co=1 (record count on) and KEEPS its
    # Sum; its chart measures the record count; item 11's report alone is redeployed on Ryan's go, then a refresh.

    # the live ids of steps 1-6 (the ticket comment of 2026-10-25): each copy and the original it copies
    COPIES = (("00ORP000009kM0L2AU", "00ORP000004RJZC2A4"), ("00ORP000009kM1x2AE", "00ORP000004RJZD2A4"),
              ("00ORP000009kM3Z2AU", "00ORP000005uf412AA"), ("01ZRP00000BP52z2AD", "01ZRP000006k2D32AI"))
    CHECK_ONLY_ID, DEPLOY_ID = "0AfRP000002i5dx0AA", "0AfRP000002i5hB0AQ"
    ITEM11_COMPONENT = "01aRP0000089gWVYAY"
    ITEM11_MDAPI = "Completed_Observing_Clubs_Alteast_Once_P_cn6"
    OTHER_MDAPI = ("Submission_of_GC_observation_forms_M_P_iuz", "Total_Number_of_Club_Observations_by_M_q3M")
    SF_ID = re.compile(r"\b0[0-9A-Za-z]{2}[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\b")
    # the record count a component measures
    RECORD_COUNT = re.compile(r"(?i)\bRowCount\b|\brecords?\s+counts?\b|\bcounts?\s+of\s+(the\s+)?(\w+\s+)?records\b|"
                              r"\bnumber\s+of\s+(\w+\s+)?records\b")
    # a report's record count ON: the report param `co` 1 (`co=1`, "`co` 1", "co set to 1", the XML), describe
    # `hasRecordCount: true`, "record count on / shown / enabled", "turns on the record count"
    RECORD_COUNT_ON = re.compile(
        r"(?i)<name>co</name>\s*<value>1</value>|"
        r"(?<![\w-])`?co`?\s*(=|:|is|to|set\s+to|of|at)?\s*`?1\b(?!\.?\d)|"
        r"\bhasRecordCount`?\s*(:|=|is|as)?\s*`?true\b|"
        r"\brecord\s+count`?\s+(is\s+|turned\s+|switched\s+|set\s+|stays\s+)?(on|shown|enabled|visible)\b|"
        r"\b(shows?|showing|turns?\s+on|turning\s+on|enables?|enabling|switch(es)?\s+on)\s+(the\s+|its\s+|a\s+)?"
        r"record\s+count\b")
    # ... and OFF: `co` 0, `hasRecordCount: false`, "record count off / hidden / disabled"
    RECORD_COUNT_OFF = re.compile(
        r"(?i)<name>co</name>\s*<value>0</value>|"
        r"(?<![\w-])`?co`?\s*(=|:|is|was|to|set\s+to|of|at)?\s*`?0\b(?!\.?\d)|"
        r"\bhasRecordCount`?\s*(:|=|is|was|as)?\s*`?false\b|"
        r"\brecord\s+count`?\s+(is\s+|was\s+|turned\s+|switched\s+|set\s+)?(off|hidden|disabled)\b")
    # "RowCount ... only when / if / while / requires / needs" the record count is on
    CONDITION = re.compile(r"(?i)\bonly\s+(when|if|while|with)\b|\bas\s+long\s+as\b|\brequir\w*|\bneeds?\b|"
                           r"\bdepends?\s+on\b|\bunless\b|\bprovided\b|\bwhenever\b|\bwhen\b|\bif\b")
    # the wrong mechanism: a Sum (a summarized column) causes, removes or blocks RowCount
    # ("a Sum, so no RowCount" is the Sum with "no RowCount" in one sentence: sum_blamed's other branch)
    SUM_CAUSE = re.compile(r"(?i)(\bSum\b|\bsummari[sz]\w*|aggregateTypes)[^.;]{0,100}?\b("
                           r"caus\w*|remov\w*|block\w*|takes?\s+away|took\s+away|drops?|dropp\w*|hides?|hid|"
                           r"replac\w*|prevent\w*|suppress\w*|costs?|loses?|lost)\b[^.;]{0,100}?RowCount|"
                           r"(\bSum\b|\bsummari[sz]\w*|aggregateTypes)[^.;]{0,100}?\b(takes?|took|taking|taken)\b"
                           r"[^.;]{0,60}?RowCount\b[^.;]{0,60}?\baway\b|"
                           r"RowCount[^.;]{0,60}?\b(because|since|due\s+to)\b[^.;]{0,60}?"
                           r"(\bSum\b|\bsummari[sz]\w*|aggregateTypes)")
    # what disowns a sentence about the Sum: the first, wrong diagnosis said as such
    DISOWNED = re.compile(r"(?i)\b(thought|suspected|misread|mistaken\w*|wrong(ly)?|ruled\s+out|first\s+diagnosis|"
                          r"not\s+the\s+cause|isn['’]t\s+the\s+cause|is\s+not\s+what)\b")
    # dropping the Sum (the fix keeps it)
    SUM_DROP = re.compile(r"(?i)\b(drops?|dropping|dropped|removes?|removing|removed|deletes?|deleted|takes?\s+out)\s+"
                          r"(the\s+|its\s+|that\s+|item\s+11['’]s\s+)?(one\s+)?(`?<?aggregateTypes>?\b|`?Sum\b|summar\w*)")
    # the measure a sum (for "measures the sum, not the record count (RowCount)")
    SUM_MEASURE = re.compile(r"(?i)\b(measur\w*|charts?|counts?)\s+(the\s+|a\s+|its\s+)?(sum|total)\b")
    # the org fact: a component's measure must be one of its report's aggregates
    RULE = re.compile(r"(?i)\bcomponents?\b[^.;]{0,120}?\b(must|only|has\s+to|have\s+to|needs?\s+to|always)\b"
                      r"[^.;]{0,120}?\baggregates?\b|"
                      r"\baggregates?\b[^.;]{0,120}?\b(must|only|has\s+to|have\s+to|needs?\s+to|always)\b"
                      r"[^.;]{0,120}?\bcomponents?\b")
    PAST = re.compile(r"(?i)\b(was|were|had|used\s+to|no\s+longer|formerly|previously|once)\b")
    HEDGE = re.compile(r"(?i)\b(may|might|usually|often|sometimes|probably|likely|perhaps|seems?|apparently)\b")
    SUMMARIZES = re.compile(r"(?i)\bsummari[sz]e[sd]?\b|\bSum\b|aggregateTypes")
    # where a SUM_CAUSE match may start: every Sum and RowCount of a sentence, so a later clause is read on its own
    # ("summarizes no column, but item 11's Sum removes RowCount": the match from "summarizes" holds the "no")
    CAUSE_START = re.compile(r"(?i)\bSum\b|\bsummari[sz]|aggregateTypes|RowCount")
    NO_ROWCOUNT = re.compile(r"(?i)\b(no|without|lacks?|lacking|loses?|lost|omits?|omitted|drops?|dropped|"
                             r"not\s+(offer|list|includ|provid)\w*)\s+(a\s+|the\s+|any\s+)?`?RowCount\b|"
                             r"`?RowCount`?[^.;]{0,40}?\b(missing|absent|gone|disappear\w*|"
                             r"not\s+(offered|listed|available|included))\b")

    def item_blocks(self, part, item):
        r = self.keep()[item]
        return [b for b in self.blocks(part) if r["measure"] in b and self.labelled(b, r)]

    def affirmed(self, s, m):
        """Match `m` of clause `s` said, not denied: no negation in the words before it and no "no", "none" or
        "nothing" right after it ("summarizes no column")."""
        return not self.d.locally_denied(s, m) and not re.match(r"`?\s+(nothing|none|no)\b", s[m.end():])

    def sum_blamed(self, text):
        """The sentences of `text` that blame the Sum for the missing RowCount: a Sum (a summarized column) said to
        cause, remove or block RowCount, or said with "no RowCount" and no record count off beside it; not denied
        ("not the Sum") and not disowned as the first, wrong diagnosis."""
        out = []
        for s in sentences(flat(text), ".;"):
            if self.DISOWNED.search(s):
                continue
            sums = [m for m in self.SUMMARIZES.finditer(s) if self.affirmed(s, m)]
            starts = (self.SUM_CAUSE.match(s, c.start()) for c in self.CAUSE_START.finditer(s))
            causal = [m for m in starts if m and not self.d.locally_denied(s, m)
                      and not self.d.NEGATION.search(m.group(0))]
            if causal or (sums and self.NO_ROWCOUNT.search(s) and not self.RECORD_COUNT_OFF.search(s)):
                out.append(s)
        return out

    def test_the_runbook_says_item_11_charts_the_record_count_with_its_reports_record_count_on(self):
        where = f"RUNBOOK section {self.MONTHLY[3:]!r}, {self.PART[4:]!r}"
        rows = self.keep()
        part = self.part()
        mine = self.item_blocks(part, "11")
        self.assertTrue(mine, f"{where}: item 11 ({rows['11']['measure']!r}, the report "
                              f"{rows['11']['label_today']!r}) has its own row, list item or paragraph")
        cl = [s for b in mine for s in sentences(b, ".;")]
        # the component measures the record count (RowCount): partner-months per Yes/No per month
        counted = [s for s in cl if re.search(r"(?i)\b(component|chart)s?\b", s)
                   and any(self.affirmed(s, m) and not self.PAST.search(s[:m.end()]) for m in self.RECORD_COUNT.finditer(s))
                   and not [m for m in self.SUM_MEASURE.finditer(s) if self.affirmed(s, m)]]
        self.assertTrue(counted, f"{where}: item 11's block says its component (chart) measures the record count "
                                 "(`RowCount`), in one sentence, present tense, not negated")
        # its report has the record count on (`co` 1, `hasRecordCount: true`): what makes RowCount one of its
        # aggregates (2026-10-25: item 11's report had co=0, hence the 406); it may keep its Sum
        self.assertTrue([s for s in cl for m in self.RECORD_COUNT_ON.finditer(s) if self.affirmed(s, m)],
                        f"{where}: item 11's block says its report has the record count on (the report param `co` 1, "
                        "describe `hasRecordCount: true`, \"record count on\"), in one sentence, not negated")
        # ... and never that its Sum took RowCount away (item 10 sums the same column and lists RowCount)
        blamed = self.sum_blamed(" ".join(mine))
        self.assertFalse(blamed, f"{where}: item 11's 406 came from its record count off (`co` 0), not from its Sum: "
                                 f"item 10's report sums the same column and offers RowCount: {blamed[0][:200]!r}"
                         if blamed else "")
        for s in cl:
            for m in self.SUM_DROP.finditer(s):
                self.assertFalse(self.affirmed(s, m) and not self.PAST.search(s),
                                 f"{where}: item 11's fix keeps its Sum (it turns the record count on): {s[:200]!r}")
        # the part no longer says the deploy is still to come
        for s in sentences(flat(part), ".;"):
            self.assertNotRegex(s, r"(?i)\buntil\s+(it\s+is\s+)?deployed\b|\bthe\s+org\s+holds\s+the\s+vendor['’]s\b|"
                                   r"\bnothing\s+(is\s+|was\s+|has\s+been\s+)?deployed\b",
                                f"{where}: the build was deployed on 2026-10-25 (deploy {self.DEPLOY_ID}); the part "
                                f"still says it is not: {s[:200]!r}")

    def test_the_monthly_section_states_that_a_component_measures_one_of_its_reports_aggregates(self):
        where = f"RUNBOOK section {self.MONTHLY[3:]!r}"
        section = md_part(self.RUNBOOK, self.MONTHLY)
        # the rule, present tense, not negated, not hedged
        ruled = []
        for s in sentences(self.norm(section), ".;"):
            for m in self.RULE.finditer(s):
                if (not self.d.locally_denied(s, m) and not self.PAST.search(s[:m.end()])
                        and not self.HEDGE.search(m.group(0)) and not self.MORE_SOFT.search(s)):
                    ruled.append(s)
        self.assertTrue(ruled, f"{where}: state the org fact, present tense and not negated: a dashboard component's "
                               "measure must be one of its report's aggregates (\"A component's measure must be one of "
                               "its report's aggregates\")")
        # the fact seen on 2026-10-25, in one row, item or paragraph with the date and the 406: a report offers
        # RowCount only when its record count is on (`co` 1, `hasRecordCount: true`); item 11's report had it off
        # (`co` 0), so its RowCount component failed with 406
        r11 = self.keep()["11"]
        names11 = re.compile(r"(?i)\bitem\s+11\b|" + r11["id"] + "|" + re.escape(r11["label_today"]) + "|"
                             + re.escape(r11["label_target"]))
        on_cond = re.compile(r"(?i)\bRowCount\b")
        seen = []
        for b in self.blocks(section):
            if "406" not in b or "2026-10-25" not in b:
                continue
            ss = sentences(b, ".;")
            cond = [s for s in ss if on_cond.search(s) and self.CONDITION.search(s)
                    and [m for m in self.RECORD_COUNT_ON.finditer(s) if not self.d.locally_denied(s, m)]
                    and not self.HEDGE.search(s)
                    and not re.search(r"(?i)\beven\s+(when|if|with)\b|\bregardless\s+of\s+(the\s+|its\s+)?record", s)]
            off = [s for s in ss if names11.search(s) and self.RECORD_COUNT_OFF.search(s)]
            if cond and off:
                seen.append(b)
        self.assertTrue(seen, f"{where}: say, in one row, item or paragraph with the date 2026-10-25 and the 406, that a "
                              "report offers `RowCount` only when its record count is on (the param `co` 1, describe "
                              "`hasRecordCount: true`), and that item 11's report had it off (`co` 0), hence the 406")
        # ... and nowhere that a summarized column (a Sum) removes RowCount: item 10 sums a column and lists RowCount
        blamed = self.sum_blamed(section)
        self.assertFalse(blamed, f"{where}: a Sum does not take RowCount away (item 10's report sums the same column "
                                 "with the record count on and lists Sum and RowCount); the 406 was item 11's record "
                                 f"count off: {blamed[0][:200]!r}" if blamed else "")

    def test_the_plan_records_the_live_steps_of_2026_10_25(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        text = read(path)
        keys, _ = docs_index.frontmatter(text)
        word, _ = docs_index.status_of(keys.get("status", ""))
        self.assertIn(word, ("in-progress", "done"), f"{name}: the deploy ran on 2026-10-25, so `status:` is "
                                                     f"`in-progress` (or `done` when complete), not {word!r}")
        self.assertNotRegex(keys.get("status", ""), r"(?i)nothing\s+deployed",
                            f"{name}: the status comment still says nothing is deployed")
        raw = self.plan_part(path, "## Result", 40)
        where = f"{name}: `## Result`"
        body = flat(raw)
        blocks = self.blocks(raw)
        self.assertNotRegex(body, r"(?i)\bpending\s+until\s+the\s+deploy\b|\bnothing\s+(is\s+|was\s+|has\s+been\s+)?"
                                  r"deployed\b|\bnot\s+(yet\s+)?deployed\b",
                            f"{where}: the deploy ran on 2026-10-25; the Result still says it is pending")
        # steps 1-2: each copy in Decommissioned with the original it copies, in one row, item or paragraph
        for copy, orig in self.COPIES:
            self.assertIn(copy, body, f"{where}: record the copy {copy} (of {orig}) made in Decommissioned")
            self.assertTrue([b for b in blocks if copy in b and orig in b],
                            f"{where}: the copy {copy} and the original it copies, {orig}, in one row, item or "
                            "paragraph")
        self.assertTrue([s for s in sentences(body, ".;") if "Decommissioned" in s
                         and [c for c, _ in self.COPIES if c in s]],
                        f"{where}: say the copies are in Decommissioned (a sentence with a copy's id and "
                        "\"Decommissioned\")")

        # steps 3-4: the check-only and the deploy, each id beside its own word, each succeeded
        def window(s, ident):
            at = s.find(ident)
            prev = [m.end() for m in self.SF_ID.finditer(s[:at])]
            return s[(prev[-1] if prev else max(0, at - 120)):at]
        check_only = re.compile(r"(?i)check-only|--dry-run|\bvalidat\w*")
        for ident, what in ((self.CHECK_ONLY_ID, "check-only"), (self.DEPLOY_ID, "deploy")):
            self.assertIn(ident, body, f"{where}: record the {what} id {ident}")
            near = [window(b, ident) for b in blocks if ident in b]
            if what == "check-only":
                ok = [w for w in near if check_only.search(w)]
            else:
                ok = [w for w in near if re.search(r"(?i)\bdeploy", w) and not check_only.search(w)]
            self.assertTrue(ok, f"{where}: the {what} id {ident} right after the word {what!r} (no other id between)")
            self.assertTrue([b for b in blocks if ident in b and re.search(r"(?i)\bsucce\w+|\b0 errors\b", b)],
                            f"{where}: the {what} {ident} succeeded (\"Succeeded\")")
        # step 5: the read-back; the reports equal build/, the dashboard differs only in showValues true -> false on
        # the two ColumnStacked components, which Ryan accepted as normalisation
        cl = sentences(body, ".;")
        self.assertTrue([s for s in cl if "build/" in s and re.search(r"(?i)\breports?\b", s)
                         and self.EQUALS.search(s) and not self.d.denies(s.replace("no differences", ""))],
                        f"{where}: say the read-back's reports equal `build/` (one sentence)")
        accept = re.compile(r"(?i)\baccept\w*")
        sv = [b for b in blocks if "showValues" in b]
        good = [b for b in sv if re.search(r"(?i)\btrue\b[^.;]{0,30}?\bfalse\b", b)
                and re.search(r"(?i)ColumnStacked|stacked\s+column", b) and re.search(r"Ryan", b)
                and re.search(r"(?i)\bnormali[sz]\w*", b)
                and [s for s in sentences(b, ".;") for m in accept.finditer(s) if self.affirmed(s, m)]]
        self.assertTrue(good, f"{where}: the read-back's one difference, `showValues` true -> false on the two "
                              "ColumnStacked components, and that Ryan accepted it as Salesforce's normalisation, in one "
                              "row, item or paragraph")
        # step 6: the refresh, item 11's 406 and its cause
        r11 = self.keep()["11"]
        names11 = re.compile(r"(?i)\bitem\s+11\b|" + r11["id"] + "|" + self.ITEM11_COMPONENT + "|"
                             + re.escape(r11["label_today"]))
        failed = [b for b in blocks if re.search(r"\b406\b", b) and names11.search(b)]
        self.assertTrue(failed, f"{where}: record that item 11's component ({self.ITEM11_COMPONENT}) failed the "
                                "refresh with 406, in one row, item or paragraph")
        self.assertTrue([b for b in failed if re.search(r"\bRowCount\b", b) and self.RECORD_COUNT_OFF.search(b)],
                        f"{where}: the 406's cause beside it: item 11's report has its record count off (the param "
                        "`co` 0, describe `hasRecordCount: false`), so it offers no `RowCount`, which its component "
                        "measures")
        # ... not its Sum, anywhere in the plan; and the fix keeps the Sum
        blamed = self.sum_blamed(read(path))
        self.assertFalse(blamed, f"{name}: the 406 came from item 11's record count off (`co` 0), not from its Sum "
                                 "(item 10's report sums the same column and lists RowCount): "
                                 f"{blamed[0][:200]!r}" if blamed else "")
        for s in sentences(flat(read(path)), ".;"):
            for m in self.SUM_DROP.finditer(s):
                self.assertFalse(self.affirmed(s, m) and not self.PAST.search(s) and not self.DISOWNED.search(s),
                                 f"{name}: item 11's fix keeps its Sum and turns its record count on (`co` 1): "
                                 f"{s[:200]!r}")

    def test_the_rollout_fixes_item_11_forward_before_the_soql_check_and_the_moves(self):
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        raw = self.plan_part(path, "## Rollout", 40)
        where = f"{name}: `## Rollout`"
        steps = self.numbered_steps(raw)
        r11 = self.keep()["11"]
        names11 = re.compile(r"(?i)\bitem\s+11\b|" + r11["id"] + "|" + self.ITEM11_MDAPI + "|"
                             + re.escape(r11["label_today"]))
        redeploy = re.compile(r"(?i)\bre-?deploy\w*|\bdeploy\w*")
        eq = self.EQUALS.pattern.replace("(?i)", "")
        fresh_eq_after = re.compile(r"(?i)\bfresh\b[^.;]{0,20}?\bretriev\w*[^.;]{0,80}?(" + eq + r")[^.;]{0,40}?after/|"
                                    r"after/[^.;]{0,40}?(" + eq + r")[^.;]{0,80}?\bfresh\b[^.;]{0,20}?\bretriev\w*")
        fix = [i for i, s in enumerate(steps) if names11.search(s) and redeploy.search(s)
               and fresh_eq_after.search(s) and re.search(r"Ryan['’]s go\b", s)
               and re.search(r"(?i)check-only|--dry-run", s) and re.search(r"(?i)\brefresh", s)]
        self.assertTrue(fix, f"{where}: a numbered step fixes item 11 forward: from a fresh retrieve that equals "
                             "`after/`, check-only, on Ryan's go redeploy item 11's report, then refresh the dashboard")
        i = fix[0]
        s = steps[i]
        self.assertTrue(self.ITEM11_MDAPI in s or re.search(r"(?i)\b(only|alone)\b", s),
                        f"{where}: the fix step redeploys item 11's report only (`-m \"Report:GLOW_Monthly_Reports/"
                        f"{self.ITEM11_MDAPI}\"`, or \"only\"): {s[:200]!r}")
        for other in self.OTHER_MDAPI + ("Dashboard:",):
            self.assertNotIn(other, s, f"{where}: the fix step redeploys item 11's report only, not {other!r}")
        self.assertTrue([m for m in self.RECORD_COUNT_ON.finditer(s) if self.affirmed(s, m)]
                        and re.search(r"\bRowCount\b", s),
                        f"{where}: the fix step says what changes: item 11's report gets its record count on (the "
                        "param `co` 1, describe `hasRecordCount: true`) so it offers `RowCount`, which its component "
                        "measures")
        blamed = self.sum_blamed(s)
        self.assertFalse(blamed, f"{where}: the fix step blames the Sum; the cause is item 11's record count off "
                                 f"(`co` 0): {blamed[0][:200]!r}" if blamed else "")
        for m in self.SUM_DROP.finditer(s):
            self.assertFalse(self.affirmed(s, m), f"{where}: the fix step keeps item 11's Sum (it changes `co` "
                                                  f"only): {s[:200]!r}")
        dep = [m.start() for m in redeploy.finditer(s) if not re.search(r"(?i)check-only|--dry-run", s[m.start():m.end() + 12])]
        self.assertTrue(dep and max(m.start() for m in re.finditer(r"(?i)\brefresh", s)) > dep[0],
                        f"{where}: the fix step refreshes the dashboard after the redeploy")
        # after the first deploy (steps 3-6), before the SOQL check and the moves
        first_deploy = [j for j, t in enumerate(steps) if re.search(r"sf project deploy start\b(?![^`]*--dry-run)", t)
                        and j != i]
        self.assertTrue(first_deploy and first_deploy[0] < i,
                        f"{where}: the fix step comes after the deploy of the build")
        soql = [j for j, t in enumerate(steps) if j != i and j > first_deploy[0] and re.search(r"\bSOQL\b", t)
                and "DHIS2__c" in t]
        moves = [j for j, t in enumerate(steps) if j != i and re.search(r"sf_report_folders\.py\s+move\b", t)]
        self.assertTrue(soql and moves, f"{where}: the SOQL check and the moves stay numbered steps")
        self.assertLess(i, soql[0], f"{where}: item 11's fix comes before the SOQL check (steps 7-8 wait until item "
                                    "11 works)")
        self.assertLess(i, moves[0], f"{where}: item 11's fix comes before the moves")

    # --- the guard itself: sum_blamed flags every phrasing that blames the Sum, and nothing else -----------------
    #
    # A review of #77 (low) found two phrasings the guard let through: the verb split from "away" around RowCount
    # ("A Sum aggregate takes RowCount away."), and a Sum-blaming clause after "summarizes no column" in the same
    # sentence (the exemption for "summarizes no column" swallowed the clause that followed it).

    BLAMES_SUM = (
        # the review's phrasing (a): "takes ... away" around RowCount
        "A Sum aggregate takes RowCount away.",
        "Its Sum takes the RowCount away from item 11's report.",
        "The Sum took `RowCount` away.",
        "A summarized column takes RowCount away from the report.",
        # the review's phrasing (b): a Sum-blaming clause after "summarizes no column", one sentence
        "Item 9's report summarizes no column, but item 11's Sum removes RowCount.",
        "Item 9's report summarizes no column, while a Sum blocks RowCount.",
        "Item 9's report summarizes no column, and its Sum caused the missing RowCount.",
        "Item 9's report summarizes nothing, and item 11's Sum takes RowCount away.",
        # what the guard already flags (kept flagged)
        "The Sum removes RowCount.",
        "Item 11's Sum causes the missing RowCount.",
        "Item 11's report has a Sum, so no RowCount.",
        "RowCount is gone because of the Sum.",
    )
    CLEARS_SUM = (
        "Item 11's report summarizes no column.",
        "Item 9's report summarizes no column, and it lists RowCount.",
        "Item 11's report has its record count off (`co` 0), so its aggregates list only its Sum and no `RowCount`.",
        "Item 10's report sums the same column with `co` 1 and lists the Sum and `RowCount`.",
        "Not the Sum: item 10's report sums the same column and lists RowCount.",
        "A first diagnosis named the wrong cause: the Sum took RowCount away.",
        "Item 11's report keeps its Sum and turns its record count on (`co` 1), so it offers RowCount.",
        "The component measures the record count (`RowCount`).",
    )

    def test_the_sum_blaming_guard_flags_every_phrasing_that_blames_the_sum(self):
        missed = [s for s in self.BLAMES_SUM if not self.sum_blamed(s)]
        self.assertFalse(missed, "sum_blamed (the guard of #77's docs) lets through sentences that blame the Sum for "
                                 f"the missing RowCount: {missed!r}")
        # inside a paragraph of correct sentences too
        for s in self.BLAMES_SUM:
            text = ("Item 11's report has its record count off (`co` 0). " + s
                    + " Item 10's report sums the same column with `co` 1 and lists RowCount.")
            self.assertTrue(self.sum_blamed(text), f"sum_blamed misses {s!r} inside a paragraph")

    def test_the_sum_blaming_guard_passes_what_does_not_blame_the_sum(self):
        flagged = [s for s in self.CLEARS_SUM if self.sum_blamed(s)]
        self.assertFalse(flagged, f"sum_blamed flags sentences that do not blame the Sum: {flagged!r}")
        self.assertFalse(self.sum_blamed(" ".join(self.CLEARS_SUM)),
                         "sum_blamed flags the paragraph of sentences that do not blame the Sum")

    # --- the live steps of 2026-10-26: item 11 fixed forward, the SOQL check, the moves --------------------------
    #
    # #77 on 2026-10-26 ~03:10 UTC, on Ryan's go: step 7 redeployed item 11's report with `co` 1 (check-only
    # 0AfRP000002i7JB0AY, deploy 0AfRP000002i6yE0AQ) after a fresh retrieve `fresh_2026-10-26/` equalled `after/`;
    # the read-back `after_item11/` equals `build_item11/`; the refresh at 03:06 UTC returned data on 3/3 components,
    # item 11's 01aRP0000089gWVYAY included. Step 8: SOQL for September 2026 equals the components (item 9 23 Yes /
    # 3 No, item 10 sum 93 over 42, item 11 27 Yes / 15 No, one partner's September equal); the test-record rule:
    # item 11 No 33 in January and 19 in March 2026 with the rule (34 and 20 without), item 10 46 records each month
    # (47 without). Step 9: 5 reports moved to Decommissioned, 5/5 read back, the ledger holds 5 move rows. Step 10
    # (the weekly Subscribe) and the dashboard copy's rename are Ryan's and stay open.
    #
    # The test-breaker passed the first version with a false Result: the ids beside "failed" and "rolled back",
    # `co` 1 said of the plan, a retrieve that "differed", a read-back that "would" equal, a refresh that "still
    # fails with 406; 3/3 is the goal", the counts swapped between the items, a step 9 "refused", and the stale
    # words put before the step numbers. Each claim is now read in its own sentence (or table row): bound to its
    # id, folder, item or month, said (not denied), real (not a plan, a hope or a guess) and free of failure words.
    LIVE_DAY = "2026-10-26"
    CHECK_ONLY_7, DEPLOY_7 = "0AfRP000002i7JB0AY", "0AfRP000002i6yE0AQ"
    STEP_REF = re.compile(r"(?i)\bsteps?\s+(\d+)(?:\s*(?:-|–|to|through)\s*(\d+))?")
    # what says a live step did not do what the Result claims ("0 errors", "no errors" are no error)
    FAILED = re.compile(r"(?i)\bfail\w*|\brolled\s+back\b|\brollback\b|\brefus\w*|\berrors?\b|\b406\b|\bNO_DATA\b|"
                        r"\babort\w*|\bcancel\w*|\breject\w*|\bundone\b")
    NO_ERRORS = re.compile(r"(?i)\b(0|no|zero|without)\s+errors?\b")
    # what makes a claim a plan, a hope or a guess instead of what happened
    UNREAL = re.compile(r"(?i)\b(would|should|could|might|may|will|shall|in\s+theory|theoretically|expect\w*|"
                        r"supposed|hop(e|es|ed|ing)|plans?\s+to|planned|goal|target|aim(s|ed)?|assum\w*|presum\w*|"
                        r"probably|likely|perhaps|maybe|ideally)\b")
    SUCCEEDED = re.compile(r"(?i)\bsucce\w+|\b0\s+errors\b")
    DIFFERS = re.compile(r"(?i)\bdiffer\w*|\bmismatch\w*|\bdiscrepanc\w*|\bdeviat\w*")
    WAITS = re.compile(r"(?i)\b(a)?wait\w*|\bnot\s+yet\b|\byet\s+to\b|\bstill\s+to\s+(do|run|come)\b|\bpending\b|"
                       r"\bto\s+be\s+(run|done)\b")
    # a side of the test-record rule's check as the label of a count beside it ("33 with the rule", "without it
    # 34", "19 with and 20 without"); "with the VPN off" or "with Yes and No" is no side
    SIDE = re.compile(r"(?i)\b(with(?:out)?)\b(?=\s+(?:the\s+)?(?:test[- ]record\s+)?(?:rule|filter)\b|\s+(?:it|them)\b|"
                      r"\s*[/,;:.()|]|\s*$|\s+\d|\s+and\b)")
    SIDES = re.compile(r"(?i)\b(with(?:out)?)\s*/\s*(with(?:out)?)\b")      # a table's "with / without" header
    # round 2's false Result ended "At 05:10 UTC Ryan undid all of it ... Nothing of the above is in the org now":
    # what says the live steps were taken back afterwards ("read back" is the read-back, not this)
    UNDID = re.compile(r"(?i)\bundid\b|\bundone\b|\bundo(es|ing)\b|\brevert(ed|s|ing)\b|\brestored\b|"
                       r"\b(roll(s|ed|ing)?|went|go(es|ne)?|put|moved?|brought|turned|set)\s+(\w+\s+){0,3}?"
                       r"(?<!read )back\b|"
                       r"(?<!read-)(?<!read )\bback\s+(to|on|in|at|into)\b|\bout\s+of\s+(the\s+)?Decommissioned\b|"
                       r"\b(nothing|none)\s+of\s+(the\s+above|this|that|it)\b")
    # a failure state of item 11 (406, the record count off); a sentence with it is history only when it also says
    # the fix, or says it in the past with no word of a later change
    BROKEN = re.compile(r"(?i)\b406\b|\bNO_DATA\b")
    FIXED = re.compile(r"(?i)\breturn\w*\s+(its\s+)?data\b|\bYes\s+and\s+No\b|\bno\s+longer\b|\bfixed\b|\bgone\b")
    LATER = re.compile(r"(?i)\b(again|now|currently|still|today|back|since|set|changed|switched|turned|"
                       r"redeployed|deployed|moved|returned|is|are|has|have|remains?|stays?|fails?)\b|\b\d\d:\d\d\b")
    PAST = re.compile(r"(?i)\b(had|was|were|failed|before|first|earlier|previously|old)\b|\bbefore/")
    HISTORY_DAY = re.compile(r"\b2026-10-2[45]\b")

    def names_step(self, s, n):
        """`s` names Rollout step `n`: "step n", or a range "steps a-b" around it."""
        for m in self.STEP_REF.finditer(s):
            lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
            if lo <= n <= hi:
                return True
        return False

    def result_blocks(self):
        path = self.plan_path()
        raw = self.plan_part(path, "## Result", 40)
        return os.path.relpath(path, REPO), raw, self.blocks(raw)

    def step_parts(self, blocks, n):
        """Each block of the Result that names step `n`, with the table rows right after it (a list per block)."""
        out = []
        for i, b in enumerate(blocks):
            if not self.names_step(b, n) or b.startswith("|"):
                continue
            j, parts = i + 1, [b]
            while j < len(blocks) and blocks[j].startswith("|"):
                parts.append(blocks[j])
                j += 1
            out.append(parts)
        return out

    @staticmethod
    def units(parts_list):
        """The claims of a step: each sentence of its blocks, and each table row as one claim with every cell
        prefixed by its column's header ("Item: 9 | Yes: 23 | No: 3")."""
        def cells(row):
            return [c.strip() for c in row.strip().strip("|").split("|")]

        def rule(row):
            return row.startswith("|") and all(re.fullmatch(r":?-{2,}:?", c) for c in cells(row))
        out = []
        for parts in parts_list:
            header = None
            for i, p in enumerate(parts):
                if not p.startswith("|"):
                    header = None
                    out += sentences(p, ".;")
                elif i + 1 < len(parts) and rule(parts[i + 1]):
                    header = cells(p)           # the row above a |---| rule names the columns
                elif rule(p):
                    continue
                elif header is None:
                    out.append(p)
                else:
                    row = cells(p)
                    out.append(" | ".join(f"{h}: {c}" for h, c in zip(header + [""] * len(row), row)))
        return out

    def said(self, u, rx):
        """The matches of `rx` in claim `u` said, not denied ("0 errors", "no errors" taken out first)."""
        u = self.NO_ERRORS.sub(" ", u)
        return [m.group(0) for m in rx.finditer(u) if self.affirmed(u, m)]

    def real(self, u):
        """Claim `u` says what happened: no failure word said and no plan, hope or guess."""
        return not self.said(u, self.FAILED) and not self.UNREAL.search(u)

    def equal_said(self, u):
        """Claim `u` affirms an equality ("equals", "matches", "no differences") and no difference, really."""
        plain = re.sub(r"(?i)\bno\s+differences?\b", " ", u)
        return (bool([m for m in self.EQUALS.finditer(u) if self.affirmed(u, m)])
                and not [m for m in self.DIFFERS.finditer(plain) if self.affirmed(plain, m)]
                and not self.UNREAL.search(u))

    def succeeded(self, u, ident):
        """Claim `u` says the job `ident` succeeded: "Succeeded" (or "0 errors") after the id and before the next
        id, or anywhere in `u` when it names no other id, or "both / each ... succeeded" after the last id."""
        ok = [m for m in self.SUCCEEDED.finditer(u) if self.affirmed(u, m)]
        ids = list(self.SF_ID.finditer(u))
        end = u.find(ident) + len(ident)
        nxt = [m.start() for m in ids if m.start() >= end]
        stop = nxt[0] if nxt else len(u)
        if [m for m in ok if end <= m.start() < stop]:
            return True
        if ok and {m.group(0) for m in ids} == {ident}:
            return True
        last = ids[-1].end() if ids else 0
        return bool([m for m in ok if m.start() >= last and re.search(r"(?i)\b(both|each|all)\b", u[last:m.start()])])

    @staticmethod
    def num(n):
        return r"(?<![\d.,/:-])" + n + r"(?![\d.,:-]\d|\d)"

    def pair(self, n, label):
        """`n` bound to `label` ("23 Yes", "27 partners Yes", "Yes 23", "Yes: 23"), no other count or label between."""
        return re.compile(r"(?i)" + self.num(n) + r"(?:\s+(?!(?:yes|no)\b)[A-Za-z]\w*){0,2}\s+" + label + r"\b|"
                          r"\b" + label + r"\s*[:=]?\s*" + self.num(n))

    @staticmethod
    def item_parts(u, item):
        """The parts of claim `u` about `item`: from "item <item>" (a table's "Item: <item>") to the next item."""
        marks = list(re.finditer(r"(?i)\bitem\W{1,3}(9|10|11)\b", u))
        return [u[m.end():(marks[k + 1].start() if k + 1 < len(marks) else len(u))]
                for k, m in enumerate(marks) if m.group(1) == item]

    def in_order(self, u, *words):
        """`words` (a number, or a word) in claim `u` in this order."""
        at = 0
        for w in words:
            m = re.compile(self.num(w) if w.isdigit() else r"(?i)\b" + w + r"\b").search(u, at)
            if not m:
                return False
            at = m.end()
        return True

    def sides(self, u, numbers):
        """{number: {side}}: each of `numbers` in claim `u` bound to "with" or "without" (the test-record rule). A
        table cell "with / without: 46, 43 / 47, 43" binds by its slash; anywhere else the sides and these numbers,
        in their order, bind each number to the side after it when the run starts with a number and ends with a side
        ("33 with the rule and 34 without it"), to the side before it when it starts with a side and ends with a
        number ("with the rule 33, without it 34"); a run with a side at both ends or at neither binds nothing."""
        got = {}
        for cell in u.split(" | "):
            head = self.SIDES.search(cell)
            halves = cell[head.end():].split("/") if head else []
            if len(halves) == 2:
                for side, half in zip(head.groups(), halves):
                    for n in numbers:
                        if re.search(self.num(n), half):
                            got.setdefault(n, set()).add(side.lower())
                continue
            toks = sorted([(m.start(), m.group(1).lower()) for m in self.SIDE.finditer(cell)]
                          + [(m.start(), n) for n in numbers for m in re.finditer(self.num(n), cell)])
            seq = [t for _, t in toks]
            if not seq or (seq[0] in ("with", "without")) == (seq[-1] in ("with", "without")):
                continue
            side = None
            for t in (seq if seq[0] in ("with", "without") else reversed(seq)):
                if t in ("with", "without"):
                    side = t
                else:
                    got.setdefault(t, set()).add(side)
        return got

    def step_refs(self, s):
        return [(int(m.group(1)), int(m.group(2) or m.group(1))) for m in self.STEP_REF.finditer(s)]

    def live_ref(self, s):
        """`s` names one of steps 7-9 (or what only step 7 made), the steps of 2026-10-26."""
        return (bool([r for r in self.step_refs(s) if r[0] <= 9 and r[1] >= 7])
                or bool(re.search(r"fresh_2026-10-26/|after_item11/|build_item11/", s)))

    def history(self, s):
        """`s` is about the dry runs of 2026-10-24 or steps 1-6 of 2026-10-25: it says one of those days, or names
        only steps up to 6, and says neither 2026-10-26 nor one of steps 7-9."""
        early = self.HISTORY_DAY.search(s) or (self.step_refs(s) and all(hi <= 6 for _, hi in self.step_refs(s)))
        return bool(early) and self.LIVE_DAY not in s and not self.live_ref(s)

    def assertNotUndone(self, blocks, where):
        """No sentence of the Result says steps 7-9 were taken back (undid, went back), and none from their first
        claim on says `co` 0 or 406 as the state after, unless it is the history of 2026-10-24 and 2026-10-25: an
        undo word is history only in a sentence of its own about those days; a failure state also in a block led by
        such a sentence (step 6's 406, `co` 0 in `before/`)."""
        seen = False
        for b in blocks:
            said = sentences(b, ".;")
            lead_history = self.history(said[0])
            for s in said:
                if self.history(s):
                    continue
                undid = self.said(s, self.UNDID)
                self.assertFalse(undid, f"{where}: steps 7-9 ran on {self.LIVE_DAY} and stand; a sentence says they "
                                        f"were taken back ({undid[0]!r}): {s[:200]!r}" if undid else "")
                seen = seen or (self.LIVE_DAY in s and self.live_ref(s))
                if not seen or (lead_history and not self.live_ref(s) and self.LIVE_DAY not in s):
                    continue
                broken = [m.group(0) for rx in (self.BROKEN, self.RECORD_COUNT_OFF) for m in rx.finditer(s)
                          if self.affirmed(s, m)]
                if not broken or self.FIXED.search(s) or [m for m in self.RECORD_COUNT_ON.finditer(s)
                                                          if self.affirmed(s, m)]:
                    continue
                self.assertFalse(self.LATER.search(s) or not self.PAST.search(s),
                                 f"{where}: item 11 works since step 7 ({self.LIVE_DAY}); a sentence says "
                                 f"{broken[0]!r} as its state after: {s[:200]!r}")

    def test_the_result_records_item_11s_redeploy_and_refresh_of_2026_10_26(self):
        name, raw, blocks = self.result_blocks()
        where = f"{name}: `## Result`"
        body = flat(raw)
        self.assertIn(self.LIVE_DAY, body, f"{where}: record the live steps of {self.LIVE_DAY} (steps 7-9)")
        self.assertTrue([b for b in blocks if self.LIVE_DAY in b and self.names_step(b, 7)],
                        f"{where}: say step 7 ran on {self.LIVE_DAY} (\"Step 7\" or \"Steps 7-9\" beside the date)")
        parts7 = self.step_parts(blocks, 7)
        self.assertTrue(parts7, f"{where}: a row, item or paragraph for step 7 (\"Step 7, ...\")")
        s7 = " ".join(" ".join(p) for p in parts7)
        units7 = self.units(parts7)

        # the check-only and the deploy, each id beside its own word (no other id between), each succeeded in its
        # own sentence, and no failure, rollback or refusal said beside either id
        def window(s, ident):
            at = s.find(ident)
            prev = [m.end() for m in self.SF_ID.finditer(s[:at])]
            return s[(prev[-1] if prev else max(0, at - 120)):at]
        check_only = re.compile(r"(?i)check-only|--dry-run|\bvalidat\w*")
        for ident, what in ((self.CHECK_ONLY_7, "check-only"), (self.DEPLOY_7, "deploy")):
            self.assertIn(ident, s7, f"{where}: step 7 records item 11's {what} id {ident}")
            w = window(s7, ident)
            ok = check_only.search(w) if what == "check-only" else (re.search(r"(?i)\b(re-?)?deploy", w)
                                                                     and not check_only.search(w))
            self.assertTrue(ok, f"{where}: step 7's {what} id {ident} right after the word {what!r} (no other id "
                                "between)")
            mine = [u for u in units7 if ident in u]
            for u in mine:
                bad = self.said(u, self.FAILED)
                self.assertFalse(bad, f"{where}: step 7's {what} {ident} succeeded; its sentence says {bad[0]!r}: "
                                      f"{u[:200]!r}" if bad else "")
            self.assertTrue([u for u in mine if self.succeeded(u, ident) and not self.UNREAL.search(u)],
                            f"{where}: step 7's {what} {ident} succeeded (\"Succeeded\" after the id, in its sentence)")
        # what changed: item 11's report redeployed with the record count on (`co` 1), in one sentence
        redeploy = re.compile(r"(?i)\b(re-?)?deploy\w*")
        self.assertTrue([u for u in units7 if [m for m in self.RECORD_COUNT_ON.finditer(u) if self.affirmed(u, m)]
                         and [m for m in redeploy.finditer(u) if self.affirmed(u, m)]
                         and self.real(u) and not re.search(r"(?i)\bplan\b|\bRollout\b", u)],
                        f"{where}: step 7 says item 11's report was redeployed with its record count on (`co` 1), in "
                        "one sentence, not denied, not a plan")
        # the guard before it: the fresh retrieve equalled after/
        self.assertTrue([u for u in units7 if "fresh_2026-10-26/" in u and "after/" in u and self.equal_said(u)
                         and self.real(u)],
                        f"{where}: step 7 says the fresh retrieve `fresh_2026-10-26/` equalled `after/` before the "
                        "redeploy (one sentence, no difference)")
        # the read-back after it: after_item11/ equals build_item11/
        self.assertTrue([u for u in units7 if "after_item11/" in u and "build_item11/" in u and self.equal_said(u)
                         and self.real(u)],
                        f"{where}: step 7's read-back `after_item11/` equals `build_item11/` (one sentence, said as "
                        "what happened, no difference)")
        # the refresh: item 11's component returns data, in the sentence that names it, with no failure
        data = re.compile(r"(?i)\b(return\w*|with|show\w*|ha[sd]|have|gave|gives)\s+(its\s+|their\s+)?data\b|"
                          r"\b3/3\b|\b(all\s+)?(three|3)\s+of\s+(the\s+)?(three|3)\b|\ball\s+(three|3)\s+components\b|"
                          r"\bYes\s+and\s+No\b")
        refreshed = [b for b in blocks if self.ITEM11_COMPONENT in b and re.search(r"(?i)\brefresh", b)
                     and (self.LIVE_DAY in b or "03:06" in b)
                     and [u for u in sentences(b, ".;") if self.ITEM11_COMPONENT in u and self.real(u)
                          and [m for m in data.finditer(u) if self.affirmed(u, m)]]]
        self.assertTrue(refreshed, f"{where}: the refresh of {self.LIVE_DAY} (03:06 UTC) and item 11's component "
                                   f"{self.ITEM11_COMPONENT} returning data (3/3 components), the id and the data in "
                                   "one sentence with no failure (406, error) and no goal or expectation")
        blamed = self.sum_blamed(raw)
        self.assertFalse(blamed, f"{where}: the 406 was item 11's record count off, not its Sum: {blamed[0][:200]!r}"
                         if blamed else "")
        self.assertNotUndone(blocks, where)

    def test_the_result_records_the_soql_check_and_the_moves_of_2026_10_26(self):
        name, raw, blocks = self.result_blocks()
        where = f"{name}: `## Result`"
        # step 8: the September counts equal the components, one partner's month equal, the test-record months
        parts8 = self.step_parts(blocks, 8)
        self.assertTrue([p for p in parts8 if self.LIVE_DAY in " ".join(p)],
                        f"{where}: a row, item or paragraph for step 8 (\"Step 8, ...\"), run on {self.LIVE_DAY}")
        s8 = " ".join(" ".join(p) for p in parts8)
        units8 = self.units(parts8)
        self.assertTrue([u for u in units8 if re.search(r"(?i)\bcomponents?\b", u) and self.equal_said(u)
                         and self.real(u)],
                        f"{where}: step 8 says the SOQL counts equal the components (one sentence, not denied)")
        for u in units8:
            if re.search(r"(?i)\bwithout\b", u):
                continue        # the counts without the test-record rule are meant to differ
            plain = re.sub(r"(?i)\bno\s+differences?\b", " ", u)
            denied = [m.group(0) for m in self.EQUALS.finditer(u) if self.d.locally_denied(u, m)]
            denied += self.said(plain, self.DIFFERS)
            self.assertFalse(denied, f"{where}: step 8's SOQL equals the components; a sentence says otherwise "
                                     f"({denied[0]!r}): {u[:200]!r}" if denied else "")
        for month in ("September", "January", "March"):
            self.assertIn(month, s8, f"{where}: step 8 names {month} 2026")
        # each count bound to its item and its answer, in one sentence or table row
        for item, binds, what in (("9", (self.pair("23", "Yes"), self.pair("3", "No")), "23 Yes and 3 No"),
                                  ("11", (self.pair("27", "Yes"), self.pair("15", "No")), "27 Yes and 15 No")):
            self.assertTrue([u for u in units8 for t in self.item_parts(u, item)
                             if all(rx.search(t) for rx in binds) and self.real(u)],
                            f"{where}: step 8 records item {item}'s September, {what}, after \"item {item}\" in one "
                            "sentence or table row")
        def summed(n):
            # `n` beside "sum"/"total", or bound to "sessions" ("93 sessions", a table's "Sessions: 93"): item 10's
            # Sum is its sessions, so "93 sessions in 42 Monthly Reports" is accurate
            return re.compile(r"(?i)\b(sum\w*|total)(\s+(of|was|is|came\s+to|to))?\s*[:=]?\s*" + self.num(n) + "|"
                              + self.num(n) + r"\s+(in\s+)?(sum|total|sessions?)\b|"
                              r"\bsessions?\s*[:=]\s*" + self.num(n))

        def over(n):
            return re.compile(r"(?i)\b(over|across|from|in)\s+(the\s+)?" + self.num(n) + "|" + self.num(n)
                              + r"\s+(\w+\s+)?(Monthly\s+Reports?|records?|reports?)\b")
        self.assertTrue([u for u in units8 for t in self.item_parts(u, "10")
                         if summed("93").search(t) and over("42").search(t)
                         and not summed("42").search(t) and not over("93").search(t) and self.real(u)],
                        f"{where}: step 8 records item 10's September, sum 93 over 42 Monthly Reports (93 beside "
                        "\"sum\" or \"sessions\", 42 beside \"over\" or \"Monthly Reports\"), after \"item 10\" in one "
                        "sentence or table row")
        # the test-record rule's check, each count bound to its side: with the rule 33 (January), 19 (March) and 46
        # records; without it 34, 20 and 47 (round 2 swapped the sides and passed)
        with_rule, without_rule = ("33", "19", "46"), ("34", "20", "47")
        for at, w, wo, what in ((r"\bJanuary\b", "33", "34", "item 11's No in January 2026"),
                                (r"\bMarch\b", "19", "20", "item 11's No in March 2026"),
                                (r"(?i)\bitem\W{1,3}10\b|\brecords\b", "46", "47", "item 10's records each month")):
            self.assertTrue([u for u in units8 if re.search(at, u) and self.real(u)
                             and self.sides(u, with_rule + without_rule).get(w) == {"with"}
                             and self.sides(u, with_rule + without_rule).get(wo) == {"without"}],
                            f"{where}: step 8 records {what}, {w} with the rule and {wo} without it, each count beside "
                            "its side (\"33 with the rule and 34 without it\", or a table's \"with / without\" "
                            "columns), in one sentence or table row")
        for u in units8:
            got = self.sides(u, with_rule + without_rule)
            wrong = ([n for n in with_rule if got.get(n, set()) - {"with"}]
                     + [n for n in without_rule if got.get(n, set()) - {"without"}])
            self.assertFalse(wrong, f"{where}: step 8's test-record counts are 33, 19, 46 with the rule and 34, 20, "
                                    f"47 without it; a claim binds {wrong[0] if wrong else ''} to the other side: "
                                    f"{u[:200]!r}" if wrong else "")
        self.assertTrue([u for u in units8 if re.search(r"(?i)\b(one|a|single)\s+partner", u) and self.equal_said(u)
                         and self.real(u)],
                        f"{where}: step 8 says one partner's month equals the per-partner query (one sentence)")
        # step 9: the 5 moves to Decommissioned, read back, and the ledger's 5 move rows; no refusal or failure
        parts9 = self.step_parts(blocks, 9)
        self.assertTrue(parts9, f"{where}: a row, item or paragraph for step 9 (\"Step 9, ...\")")
        units9 = self.units(parts9)
        dated9 = self.units([p for p in parts9 if self.LIVE_DAY in " ".join(p)])     # the moves' own claims, dated
        bad9 = re.compile(r"(?i)\brefus\w*|\bfail\w*|\berrors?\b|\bnone\b|\brolled\s+back\b|\bundone\b|\bskipp\w*")

        def clean9(u):
            return not self.said(u, bad9) and not self.UNREAL.search(u)
        for u in units9:
            if "2026-10-24" in u:
                continue        # the dry run of 2026-10-24 refused the moves while D3 still used the reports
            bad = self.said(u, re.compile(r"(?i)\brefus\w*|\bfail\w*"))
            self.assertFalse(bad, f"{where}: step 9 moved the 5 reports on {self.LIVE_DAY}; a sentence says "
                                  f"{bad[0]!r}: {u[:200]!r}" if bad else "")
        moved = re.compile(r"(?i)\bmov(e|es|ed)\b")
        self.assertTrue([u for u in dated9 if "Decommissioned" in u and clean9(u)
                         and [m for m in moved.finditer(u) if self.affirmed(u, m)]
                         and re.search(r"(?i)\b(5|five)\s+([\w\"“”'’]+\s+){0,4}reports?\b|\b5/5\b", u)],
                        f"{where}: step 9 moved the 5 reports to Decommissioned on {self.LIVE_DAY} (one sentence, "
                        "not denied, in a part of step 9 that says the date)")
        self.assertTrue([u for u in dated9 if clean9(u)
                         and re.search(r"(?i)\b5/5\b|\b(5|five)\s+of\s+(the\s+)?(5|five)\b", u)
                         and [m for m in re.finditer(r"(?i)\bread\s*-?\s*back\b|\bre-?read\w*", u)
                              if self.affirmed(u, m)]],
                        f"{where}: step 9 read the 5 back in Decommissioned (\"5/5 read back\", one sentence)")
        self.assertTrue([u for u in dated9 if clean9(u) and re.search(
                            r"(?i)\bledger\b[^.;]{0,80}?\b(5|five)\s+(\w+\s+)?move\s+rows?\b|"
                            r"\b(5|five)\s+(\w+\s+)?move\s+rows?\b[^.;]{0,80}?\bledger\b", u)],
                        f"{where}: step 9 says the ledger holds 5 move rows (one sentence, no failure)")
        # no longer: step 7 not yet run, steps 8-10 waiting; each stale word is read against the step reference
        # nearest it in its sentence (`build_item11/` counts as step 7), before or after it
        for s in sentences(flat(raw), ".;"):
            refs = [(m.start(), m.end(), int(m.group(1)), int(m.group(2) or m.group(1)))
                    for m in self.STEP_REF.finditer(s)]
            refs += [(m.start(), m.end(), 7, 7) for m in re.finditer(r"build_item11/", s)]
            if not [r for r in refs if r[2] <= 9 and r[3] >= 7]:
                continue
            for w in self.WAITS.finditer(s):
                if self.d.locally_denied(s, w):
                    continue
                near = min(refs, key=lambda r: max(r[0] - w.end(), w.start() - r[1], 0))
                self.assertFalse(near[2] <= 9 and near[3] >= 7,
                                 f"{where}: steps 7-9 ran on {self.LIVE_DAY}; the Result still says "
                                 f"{s[near[0]:near[1]]!r} {w.group(0)!r}: {s[:200]!r}")
        self.assertNotUndone(blocks, where)


class TrainingDashboardDocs(unittest.TestCase):
    """Ticket #78: the dashboard "GLOW Club Training" (`D4`) and its reports, items 13-16 of `glow/sf_keep_list.csv`,
    fixed by Partner and Month. Ryan's decisions (the ticket's comment, 2026-10-24): the default period is the last
    12 months through `DHIS2__c.Period__c` (`LAST_N_MONTHS:12`, #128); group by Partner (`Account__c`), then the
    month; every report carries the test-record rule (`Account is not blank AND Account: Account Name does not
    contain "test"`, #70); labels stay as they are (#70). The fields each item counts are #74's (RUNBOOK "Why the
    dashboards showed old data": 13 and 14 numbers, checked by SUM; 15 and 16 picklists, checked by GROUP BY the
    field), pinned here, not read from the docs under test. The dashboard is `D4` (`01ZRP000006quAj2AI`, labelled
    "Mentors" in the org; the org's "GLOW Club Training" label is on `D3`, the Observations dashboard); its id and the
    reports' ids come from `glow/sf_keep_list.csv`. Counts only in the docs: no figure from the org is pinned.

    The dashboard's filters (Ryan, 2026-10-24, the ticket's comment, for all five dashboards #75-#79): NO Partner
    filter and NO Month filter; the one dashboard filter is Partner Manager, on
    `DHIS2__c$Account__c.Assigned_Partner_Manager__c` (the column D4 already filters on). This supersedes the
    definition of done's "Partner filter and a Month filter": one partner's month is read from the reports' Partner
    and Month grouping and checked by a one-partner query.

    Round 2 (the test-breaker): a unit naming an item never carries another item's field; no other date field is
    the month; each item's SOQL signal is a real query with
    its aggregate, the test-record rule and a period on `Period__c`; a rollback never deploys a `build/` or another
    ticket's build; the equality checks need "equals"/"matches"/"identical"/"no differences", not "compare" or
    "roughly"; one copy command per item id and for the dashboard; the deploy's go and check-only are read per
    numbered step. Round 3: each copy runs `--apply`; the check-only and deploy steps name `build/` (never `before/`);
    the read-back says `after/` equals `build/` with nothing between; every `before/` deploy carries its guard, and
    nothing ("anyway", "at any time") voids it; the one-partner query is an item's full query.

    The rollout (the ticket's comment of 2026-10-26: steps 1-8 done on Ryan's go): the plan's `## Result` records
    the check-only and deploy ids, the Decommissioned copies' ids (each beside its own item), the ledger dated
    before the deploy, the SOQL check's counts for the 12 months and the one-partner check, and the read-back's one
    difference; it no longer says nothing is deployed, and the plan stays `in-progress` while steps 9 (after #77)
    and 10 remain. Step 6's refresh PUT carries a body (`-b '{}'`; sf 2.151 refuses a bodiless PUT). The RUNBOOK
    says the build is deployed (2026-10-26). These ids and counts are the rollout's record (that comment), pinned
    here as the facts the Result must carry; counts and ids only.

    Tightened after the test-breaker: every occurrence of an id stands beside its own label (never another
    item's or step's); the ledger's "before the deploy" is a fact, not what the plan wanted; item 15's Yes 199 and
    No 325 are never crossed; the 2 test records are left out, not kept; step 1's fresh retrieve equals `before/`
    and step 8's ledger holds 3 moves; steps 1-9 are said done, step 10 neither done nor "not needed"; no
    Result line says failed, rolled back, mismatch, not equal, differs (but the read-back's `showValues` line) or
    still to run (but step 10); the PUT's body is in the same command as `--method PUT`; the RUNBOOK says
    "was deployed", not "scheduled" or "still runs".

    Step 9 (ticket #152, item 16 on D4, after #77 landed): the plan's Result has a part that starts with `Step 9` and
    holds its own facts (item 16's report and D4 by id, grouping by Partner and Month like items 13-15 with the
    answer across, the two new Decommissioned copies, the check-only and deploy ids, the read-back, the refresh and
    last complete month's figure equal to SOQL, with answered = Yes + No); steps 1-9 are done and only step 10 (the
    Subscribe) remains; the frontmatter comment and the RUNBOOK say item 16 is on D4."""

    longMessage = False         # the messages say what to fix
    RUNBOOK = os.path.join(REPO, "docs", "RUNBOOK.md")
    KEEP_LIST = os.path.join(REPO, "glow", "sf_keep_list.csv")
    PLANS = os.path.join(REPO, "docs", "plans", "*-sf-dash-training.md")
    MONTHLY = "## Monthly Report dashboards in Salesforce"
    PART = "### GLOW Club Training"
    GROUP = "GLOW Club Training"
    TICKET = re.compile(r"(?<![\w#])#78\b")
    # #74's per-item fields on DHIS2__c (RUNBOOK "Why the dashboards showed old data", the check that a fix worked)
    FIELDS = {"13": "Mentors_attended_the_training_sessions__c", "14": "how_many_training_sessions_did_you_lead__c",
              "15": "Lead_any_training_sessions__c", "16": "Did_you_meet_with_mentors_as_a_group__c"}
    WORK_DIR = re.compile(r"data/sf_dash_training_\d{4}-\d\d-\d\d/")
    BEFORE = re.compile(r"data/sf_dash_training_\d{4}-\d\d-\d\d/before/")
    SOQL_ON_DHIS2 = re.compile(r"(?i)\bSELECT\b[^;]{0,300}?\bFROM\s+DHIS2__c\b")
    # a query, not the word: SELECT <list> FROM DHIS2__c <rest of the statement, to the end of the unit or a backtick>
    QUERY = re.compile(r"(?i)\bSELECT\s+(?P<select>[^`;]{1,300}?)\s+FROM\s+DHIS2__c\b(?P<rest>[^`;]*)")
    # 13 and 14 are numbers (SUM), 15 and 16 picklists (GROUP BY the field): #74's check, RUNBOOK "Why the dashboards
    # showed old data"
    NUMBER_ITEMS, PICKLIST_ITEMS = ("13", "14"), ("15", "16")
    SOQL_NOT_BLANK = re.compile(r"(?i)\bAccount__c\s*(!=|<>)\s*null\b")
    SOQL_NO_TEST = re.compile(r"(?i)\bNOT\s*\(?\s*Account__r\.Name\s+LIKE\s+'%test%'")
    # the query's period is on Period__c: the default 12 months, the last complete month or a date range
    SOQL_PERIOD = re.compile(r"(?i)\bPeriod__c\s*(=\s*(LAST_N_MONTHS:12|LAST_MONTH)\b|(>=|<=|>|<)\s*\d{4}-\d\d-\d\d\b)")
    # other date fields that are not the Monthly Report's month
    OTHER_DATE = re.compile(r"\b(CreatedDate|LastModifiedDate|SystemModstamp|LastActivityDate|LastViewedDate|"
                            r"LastReferencedDate)\b")
    # the dashboard's one filter (Ryan, 2026-10-24): Partner Manager, on Account__c.Assigned_Partner_Manager__c
    PARTNER_MANAGER = re.compile(r"(?i)\bPartner\s+Manager\b")
    PM_FIELD = re.compile(r"Assigned_Partner_Manager__c\b")        # after norm(): `…Account__c_Assigned_…`
    ONE = re.compile(r"(?i)\b(one|only|single|sole)\b")
    # a Partner or a Month filter, which the dashboard does not have: "Partner filter", "Partner and Month filters",
    # "“Partner (A-K)” filter", "Month is also a filter", "filter by month", "filters: Partner", "a dashboard filter on
    # `Account__c`" (the field itself, not `Account__c.Assigned_Partner_Manager__c`); "Partner Manager" is never one
    _NAME = r"[\"“”`']?(?:Partner(?!\s+Manager)(?:\s*\([^)]{0,12}\))?|Month)(?![\w-])[\"“”`']?"
    PARTNER_OR_MONTH_FILTER = re.compile(
        r"(?i)(?<![\w-])" + _NAME + r"(?:\s*(?:,|and|or|&|/)\s*" + _NAME + r")*"
        r"(?:\s+(?:is|are|as|becomes?)(?:\s+(?!(?:not|no|never)\b)[\w'’]+){0,3}?)?\s+filters?\b|"
        r"\bfilter(?:s|ed|ing)?\s+(?:(?!group|sort)[\w'’]+\s+){0,2}?"
        r"(?:on|by|for|of|named|called|labell?ed|picks?|selects?|chooses?|sets?)\s+"
        r"(?:the\s+|a\s+|one\s+|each\s+)?" + _NAME + r"|"
        r"\bfilters?(?:\s*[:(]|\s+(?:is|are|include\w*|list\w*|cover\w*)\b)\s*(?:[\w,'’]+\s+){0,2}?" + _NAME + r"|"
        r"\bdashboard(?:['’]s)?\s+(?:\w+\s+){0,2}?filters?\s+(?:on|by|for)\s+(?:the\s+)?`?(?:DHIS2__c[_$])?"
        r"(?:Account__c|Period__c)\b")
    # the same control in other words (PR #141 review): "a month selector", "a Partner drop-down", "a slicer for the
    # month", "a picker of partners", "a viewer can pick a month", "choose the partner", "narrow the dashboard to one
    # partner", "switch between months", "view the dashboard by month"; never "grouped by partner then month" (no
    # control word, no viewer's verb) and never "Partner Manager"
    _CNAME = (r"[\"“”`']?(?:(?<![A-Za-z0-9])(?:DHIS2__c[_$])?(?:Account__c|Period__c)(?!\w)|"
              r"(?<![\w-])(?:Partners?|Months?)(?![\w-])(?!\s+Managers?\b))[\"“”`']?")
    _CONTROL = (r"(?:selectors?|pickers?|choosers?|drop[\s-]?downs?|dropdowns?|pull[\s-]?downs?|slicers?|toggles?|"
                r"switch(?:er|ers|es)?|menus?|list[\s-]?box(?:es)?|combo[\s-]?box(?:es)?|controls?|facets?|"
                r"selections?|choices?|options?|widgets?|segmenters?|views?|lens(?:es)?|parameters?|prompts?)")
    _VERB = (r"(?:pick(?:s|ed|ing)?|choos(?:e|es|ing)|chos(?:e|en)|select(?:s|ed|ing)?|switch(?:es|ed|ing)?|"
             r"toggl(?:e|es|ed|ing)|chang(?:e|es|ed|ing)|set(?:s|ting)?|narrow(?:s|ed|ing)?|limit(?:s|ed|ing)?|"
             r"restrict(?:s|ed|ing)?|scop(?:e|es|ed|ing)|slic(?:e|es|ed|ing)|drill(?:s|ed|ing)?|"
             r"focus(?:es|ed|ing)?|zoom(?:s|ed|ing)?|view(?:s|ed|ing)?|brows(?:e|es|ed|ing)|tick(?:s|ed|ing)?|"
             r"click(?:s|ed|ing)?|tap(?:s|ped|ping)?)")
    PARTNER_OR_MONTH_CONTROL = re.compile(
        r"(?i)" + _CNAME + r"(?:\s*(?:,|and|or|&|/)\s*" + _CNAME + r")*[\s-]+(?:[\w'’-]+\s+)??" + _CONTROL + r"\b|"
        r"\b" + _CONTROL + r"\s+(?:[\w'’-]+\s+){0,3}?(?:for|of|by|on|over|with|listing|lists?|between|across|"
        r"to\s+" + _VERB + r")\s+(?:(?:the|a|an|one|each|any|every|their|its|all|which|single)\s+){0,2}" + _CNAME +
        r"|\b" + _VERB + r"\s+(?:(?:it|them|the\s+dashboard|the\s+view|D4|down|in|into|to|on|onto|between|among|"
        r"from|by|per|out|up|through|across)\s+){0,3}(?:(?:the|a|an|one|each|any|every|their|its|his|her|which|"
        r"single|another|other|different)\s+){0,2}(?<![\w-])(?:Partners?|Months?)(?![\w-])(?!\s+Managers?\b)")
    CNAME = re.compile(r"(?i)" + _CNAME)
    # a second filter on the dashboard ("two filters", "another filter", "a second dashboard filter", "another
    # selector")
    FILTER_NAME = re.compile(r"(?i)\bPartner\b(?!\s+Manager)|\bMonth\b")
    MORE_FILTERS = re.compile(r"(?i)\b(two|three|2|3|second|third|another|more|other|extra|further|additional)\s+"
                              r"(dashboard\s+)?(filters?|" + _CONTROL + r")\b")
    # a figure that is not checked, only eyeballed
    SOFT = re.compile(r"(?i)\b(roughly|approximately|approx|about right|close enough|whichever|looks? right|"
                      r"seems? right|more or less|ballpark|eyeball\w*|near(ly)? enough|or so)\b")
    EQUAL_STRICT = re.compile(r"(?i)\b(equal(s|led|ling)?|match(es|ed|ing)?|identical|no differences?|the same as|"
                              r"same\s+(figures?|numbers?|counts?|totals?)\s+as)\b|==")
    DIFFER = re.compile(r"(?i)\b(differ\w*|different|changed|mismatch\w*|diverg\w*)\b")
    BUILD_DIR = re.compile(r"\bbuild/")
    # another ticket's or change's build, retrieve or folder
    OTHER_CHANGE = re.compile(r"#(?!78\b)\d+['’]s\s+(\w+\s+)?`?(build|retrieve|before/|after/|build/|copy|copies|backup)|"
                              r"\b(build|retrieve|before/|after/|build/)`?\s+(of|from)\s+(ticket\s+)?#(?!78\b)\d+|"
                              r"\bdata/sf_(?!dash_training_)[\w.-]+/(build|before|after)/")
    ACCOUNT = re.compile(r"(?<![A-Za-z0-9])Account__c\b")
    PERIOD = re.compile(r"(?<![A-Za-z0-9])Period__c\b")
    LAST_12 = re.compile(r"\bLAST_N_MONTHS:12\b")
    MONTH = re.compile(r"(?<![A-Za-z0-9])Period__c\b|(?i:\bmonths?\b|\bcalendar month\b)")
    GROUPS_BY = re.compile(r"(?i)\bgroup(s|ed|ing)?\b")
    FILTER = re.compile(r"(?i)\bfilters?\b")
    DASHBOARD = re.compile(r"(?i)\bdashboards?\b")
    RESTORE = re.compile(r"(?i)\b(rollback|roll(s|ed)?\s+(it\s+|them\s+)?back|revert\w*|restor\w*|undo|bring\w*\s+(\w+\s+)?back|"
                         r"put\w*\s+(\w+\s+)?back)\b")
    COPY = re.compile(r"(?i)\bcop(y|ies|ied)\b")
    FRESH = re.compile(r"(?i)\b(fresh|new|live|another|second)\s+(\w+\s+)?retriev\w*|\bretriev\w*\s+(\w+\s+)?"
                       r"(fresh|again|anew|live)\b")
    CONDITION = re.compile(r"(?i)\b(only|while|as long as|provided|if|when)\b")
    OLDER_BUILD = re.compile(r"(?i)\b(older|old|earlier|previous|prior|stale|another ticket['’]s)\s+(\w+\s+)?"
                             r"(build|retrieve|`?build/`?)s?\b")
    COPY_CMD = re.compile(r"\bpython3\s+(\S*/)?sf_report_folders\.py\s+copy\b")
    DATE_DENIED = re.compile(r"(?i)\b(not|never|no|instead of|rather than|in place of|replac\w*|nor|without)\b")

    @classmethod
    def setUpClass(cls):
        cls.d = DecommissionedFoldersDocs()     # #69's helpers: locally_denied, denies, contradictions
        KeepListDocs.setUpClass()
        cls.k = KeepListDocs()                  # #70's helpers: assertTestRecordRule

    @staticmethod
    def norm(text):
        return DecommissionedFoldersDocs.norm(text)

    def clauses(self, text, ends=".;"):
        return sentences(self.norm(text), ends)

    def stated(self, s, rx):
        return any(not self.d.locally_denied(s, m) for m in rx.finditer(s))

    def items(self):
        """Items 13-16 of `glow/sf_keep_list.csv`, one row each (the file repeats some rows): the group's reports
        but item 12, which is #80's own report (selected by its item number, not by an id reading `new`)."""
        import csv
        with open(self.KEEP_LIST, encoding="utf-8", newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["group"] == self.GROUP and r["kind"] == "report"
                    and r["item"] != "12"]
        out = {}
        for r in rows:
            out.setdefault(r["item"], r)
        self.assertEqual(sorted(out), ["13", "14", "15", "16"], "glow/sf_keep_list.csv: items 13-16 are the "
                                                                "GLOW Club Training reports")
        for r in out.values():
            self.assertRegex(r["id"], r"^00O\w{15}$", f"glow/sf_keep_list.csv: item {r['item']} has an 18-character "
                                                      "report id")
        return out

    def dashboard(self):
        """The group's dashboard row of `glow/sf_keep_list.csv` (`D4`; its label in the org is not "GLOW Club
        Training": that label is on `D3`, the Observations dashboard)."""
        import csv
        with open(self.KEEP_LIST, encoding="utf-8", newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["group"] == self.GROUP and r["kind"] == "dashboard"]
        self.assertEqual(len(rows), 1, f"glow/sf_keep_list.csv: one dashboard row for {self.GROUP!r}")
        self.assertRegex(rows[0]["id"], r"^01Z\w{15}$", "glow/sf_keep_list.csv: the dashboard has an 18-character id")
        return rows[0]

    @staticmethod
    def item_refs(unit, labels):
        """The items a unit names: by label, by `item N` / `items 13-16` / `items 13, 14 and 15`, or as the number in
        a table row's first cell."""
        refs = {n for n, label in labels.items() if label in unit}
        for m in re.finditer(r"(?i)\bitems?\s+((?:\d+(?:\s*(?:,|and|&|-|–|to)\s*)?)+)", unit):
            nums = m.group(1)
            for a, b in re.findall(r"(\d+)\s*(?:-|–|to)\s*(\d+)", nums):
                refs |= {str(i) for i in range(int(a), int(b) + 1)}
            refs |= set(re.findall(r"\d+", nums))
        first = re.match(r"\|\s*`?(\d+)`?\s*\|", unit)
        if first:
            refs.add(first.group(1))
        return refs

    def queries(self, text):
        """Each `SELECT … FROM DHIS2__c …` in `text` (flattened, dots kept), as (select list, whole query)."""
        return [(m.group("select"), m.group(0)) for m in self.QUERY.finditer(flat(text))]

    def item_query(self, n, query):
        """Query `query` (select list, whole) aggregates item `n`'s field as #74's check does: SUM for a number,
        the field selected and grouped by for a picklist; and it carries the test-record rule and a period on
        `Period__c`."""
        select, q = query
        field = re.escape(self.FIELDS[n])
        if n in self.NUMBER_ITEMS:
            shape = re.search(r"(?i)\bSUM\(\s*%s\s*\)" % field, select)
        else:
            shape = re.search(field, select) and re.search(r"(?i)\bGROUP\s+BY\s+[^`;]*?\b%s\b" % field, q)
        return bool(shape and self.SOQL_NOT_BLANK.search(q) and self.SOQL_NO_TEST.search(q)
                    and self.SOQL_PERIOD.search(q))

    def assertNoOtherDate(self, text, where):
        for s in self.clauses(text, ".;:"):
            for m in self.OTHER_DATE.finditer(s):
                pre = re.split(r"[,—–(]|\bbut\b", s[max(0, m.start() - 40):m.start()])[-1]
                self.assertTrue(self.DATE_DENIED.search(pre),
                                f"{where}: the month is the Monthly Report's period (`Period__c`), never "
                                f"`{m.group(0)}`; name it only as what it replaces: {s[:200]!r}")

    def assertNoOtherChange(self, text, where):
        """Another ticket's build, retrieve or folder is only ever denied; so is a `build/` in a restore sentence."""
        for s in self.clauses(text, ".;:"):
            for m in self.OTHER_CHANGE.finditer(s):
                self.assertTrue(self.d.locally_denied(s, m),
                                f"{where}: restore only from this change's copies or `before/`, never from another "
                                f"ticket's build or retrieve: {s[:200]!r}")
            if self.stated(s, self.RESTORE):
                for m in self.BUILD_DIR.finditer(s):
                    self.assertTrue(self.d.locally_denied(s, m),
                                    f"{where}: a rollback never deploys a `build/` (DECISIONS 2026-10-16); name "
                                    f"`build/` there only to deny it: {s[:200]!r}")

    def assertNotSoft(self, text, where):
        for s in self.clauses(text, ".;:"):
            for m in self.SOFT.finditer(s):
                self.assertTrue(self.d.locally_denied(s, m),
                                f"{where}: a check is exact, not {m.group(0)!r}: {s[:200]!r}")

    # the guard on a `before/` deploy, and what voids it
    BEFORE_DEPLOY = re.compile(r"(?i)\b(deploy\w*|restor\w*|roll\w*\s+(it\s+|them\s+)?back|revert\w*|put\w*\s+(\w+\s+)?back|"
                               r"bring\w*\s+(\w+\s+)?back|rollback)\b")
    ANYWAY = re.compile(r"(?i)\b(anyway|regardless|in any case|at any time|any time|either way|whenever|no matter|"
                        r"if (Ryan|he|you|someone) (prefers?|wants?|likes?|chooses?|decides?)|if preferred|as needed|"
                        r"if needed)\b")
    # after/ <equal word> build/, or build/ <equal word> after/, nothing else between; or "after/ and build/ are
    # identical", "compare after/ with build/: no differences"
    EQ_WORD = (r"(equals?|matches|match|is identical to|are identical to|is the same as|shows? no differences? "
               r"(from|with|to|against))")
    READBACK = re.compile(
        r"(?i)after/`?\s+(?:[\w'’]+\s+){0,4}?" + EQ_WORD + r"\s+(the\s+)?`?(\S*/)?build/|"
        r"build/`?\s+(?:[\w'’]+\s+){0,4}?" + EQ_WORD + r"\s+(the\s+)?`?(\S*/)?after/|"
        r"after/`?\s+(and|with|to|against)\s+`?(\S*/)?build/`?[:,]?\s+(?:[\w'’]+\s+){0,3}?"
        r"(no differences|identical|equal|the same|match)\b")

    def assertBeforeGuarded(self, text, where):
        """Every clause that deploys or restores `before/` carries the guard (a fresh retrieve equals `after/`) or
        denies the `before/`; nothing beside `before/` voids the guard ("anyway", "at any time", "if Ryan prefers")."""
        for s in self.clauses(text, ".;"):
            hits = list(re.finditer(r"before/", s))
            if not hits or not self.stated(s, self.BEFORE_DEPLOY):
                continue
            if all(self.d.locally_denied(s, m) for m in hits):
                continue
            guard = ("after/" in s and self.FRESH.search(s) and self.stated(s, self.EQUAL_STRICT)
                     and self.stated(s, self.CONDITION))
            self.assertTrue(guard, f"{where}: a `before/` deploy carries its guard in the same sentence: only while a "
                                   f"fresh retrieve equals `after/`: {s[:200]!r}")
            for m in self.ANYWAY.finditer(s):
                self.assertTrue(self.d.locally_denied(s, m),
                                f"{where}: `before/` goes back only while a fresh retrieve equals `after/`, never "
                                f"{m.group(0)!r}: {s[:200]!r}")

    def step_clauses(self, raw, where):
        """The Rollout's numbered steps as [(step number, step text, [its clauses])], in order."""
        steps, cur = [], None
        for line in raw.splitlines():
            m = re.match(r"(\d+)[.)]\s", line)
            if m:
                cur = [int(m.group(1)), [line]]
                steps.append(cur)
            elif cur and line.strip() and line[:1].isspace():
                cur[1].append(line)
            elif cur and line.strip():
                cur = None
        self.assertGreaterEqual(len(steps), 3, f"{where}: the Rollout is a numbered list of steps (`1. …`)")
        out = []
        for n, lines in steps:
            text = flat(" ".join(lines))
            out.append((n, text, [c for c in re.split(r"(?<=[.;])\s+|,\s+then\b|\bthen\b", self.norm(text)) if c.strip()]))
        return out

    def part(self):
        """The `### GLOW Club Training` part of the Monthly Report section, to the next `###` or `##`."""
        section = md_part(self.RUNBOOK, self.MONTHLY)
        m = re.search(r"^" + re.escape(self.PART) + r"(?!\w).*$", section, re.M)
        self.assertTrue(m, f"RUNBOOK section {self.MONTHLY[3:]!r}: no `{self.PART}` part under it (ticket #78)")
        rest = section[m.start():]
        nxt = re.search(r"\n#{1,3} ", rest)
        return rest[:nxt.start()] if nxt else rest

    @staticmethod
    def units(raw):
        """The smallest units a statement lives in, each flattened: a table row, a list item (with its
        continuation lines), or a sentence of a paragraph."""
        out, item, para = [], [], []

        def close():
            if item:
                out.append(flat(" ".join(item)))
                item.clear()
            if para:
                out.extend(sentences(" ".join(para), ".;"))
                para.clear()
        for line in raw.splitlines():
            st = line.strip()
            if not st or st.startswith("#"):
                close()
            elif st.startswith("|"):
                close()
                out.append(flat(st))
            elif re.match(r"([-*+]|\d+[.)])\s", st):
                close()
                item.append(st)
            elif item and line[:1].isspace():
                item.append(st)
            else:
                if item:
                    close()
                para.append(st)
        close()
        return out

    def plan_path(self):
        found = sorted(glob.glob(self.PLANS))
        self.assertEqual(len(found), 1, "docs/plans/: one plan `YYYY-MM-DD-sf-dash-training.md` for ticket #78 "
                                        f"(found {[os.path.basename(p) for p in found]})")
        self.assertRegex(os.path.basename(found[0]), r"^\d{4}-\d\d-\d\d-sf-dash-training\.md$",
                         "docs/plans/: the plan is named `YYYY-MM-DD-sf-dash-training.md`")
        return found[0]

    def plan_part(self, path, heading, least):
        name = os.path.relpath(path, REPO)
        part = md_part(path, heading)
        raw = part.split("\n", 1)[1] if "\n" in part else ""
        body = self.norm(raw)
        self.assertNotRegex(body, r"(?i)\b(TBD|TODO|TBA|FIXME)\b", f"{name}: `{heading}` is a placeholder")
        distinct = {w.lower() for w in re.findall(r"[A-Za-z]\w*", body)}
        self.assertGreaterEqual(len(distinct), least, f"{name}: `{heading}` says too little (at least {least} "
                                                      "distinct words)")
        return raw

    def assertNoOlderBuild(self, text, where):
        for s in self.clauses(text, ".;:"):
            for m in self.OLDER_BUILD.finditer(s):
                self.assertTrue(self.d.locally_denied(s, m),
                                f"{where}: never from an older build or retrieve (DECISIONS 2026-10-16); an older "
                                f"build is only ever denied: {s[:200]!r}")

    def one_pm_filter(self, s):
        """Clause `s` says the dashboard's one filter is Partner Manager on `Assigned_Partner_Manager__c`: it names
        the dashboard, a filter, "one"/"only", Partner Manager and, after it, the field, none of them negated."""
        if not (self.stated(s, self.DASHBOARD) and self.stated(s, self.FILTER) and self.stated(s, self.ONE)):
            return False
        for pm in self.PARTNER_MANAGER.finditer(s):
            if self.d.locally_denied(s, pm):
                continue
            if [f for f in self.PM_FIELD.finditer(s, pm.end()) if not self.d.locally_denied(s, f)]:
                return True
        return False

    def denied_before(self, s, at, floor=0):
        """#69's `locally_denied` at position `at` of clause `s`, looking back no further than `floor`."""
        pre = re.split(r"[,—–(]|\bbut\b|\bhowever\b|\bactually\b", s[max(floor, at - 40):at])[-1]
        return bool(DecommissionedFoldersDocs.NEGATION.search(pre))

    def assertNoPartnerOrMonthFilter(self, text, where):
        """No clause states a Partner filter, a Month filter or a second dashboard filter; each is only ever denied
        ("no Partner or Month filter (Ryan, 2026-10-24)")."""
        for s in self.clauses(text, ".;"):
            prev = 0
            found = sorted([(m, self.FILTER_NAME) for m in self.PARTNER_OR_MONTH_FILTER.finditer(s)] +
                           [(m, self.CNAME) for m in self.PARTNER_OR_MONTH_CONTROL.finditer(s)],
                           key=lambda t: (t[0].start(), t[0].end()))
            for m, name in found:
                # the match's first Partner or Month (a list shares it: "no Partner or Month filter") is denied in
                # the words before it, back to the last comma, dash or "but" and never past the previous match ("no
                # Partner filter and a Month filter" states one)
                first = name.search(s, m.start(), m.end())
                denied = self.denied_before(s, first.start() if first else m.start(), min(prev, m.start()))
                prev = max(prev, m.end())
                self.assertTrue(denied,
                                f"{where}: the dashboard has no Partner filter and no Month filter (Ryan, 2026-10-24: "
                                f"its one filter is Partner Manager); name one only to deny it: {m.group(0)!r} in "
                                f"{s[:200]!r}")
            if self.DASHBOARD.search(s):
                for m in self.MORE_FILTERS.finditer(s):
                    # a list keeps its negation across commas ("no Partner, Month or other filter")
                    pre = re.split(r"\bbut\b|\bhowever\b|\bactually\b", s[max(0, m.start() - 40):m.start()])[-1]
                    self.assertTrue(DecommissionedFoldersDocs.NEGATION.search(pre),
                                    f"{where}: the dashboard has one filter, Partner Manager (Ryan, 2026-10-24), not "
                                    f"{m.group(0)!r}: {s[:200]!r}")

    # --- the RUNBOOK ----------------------------------------------------------------------------------------

    def test_the_runbook_describes_training_by_partner_and_month(self):
        where = f"RUNBOOK section {self.MONTHLY[3:]!r}, {self.PART[4:]!r}"
        part = self.part()
        text = self.norm(part)
        cl = self.clauses(part)
        units = self.units(part)
        self.assertIn("DHIS2__c", part, f"{where}: name the Monthly Report object `DHIS2__c`")
        dash = self.dashboard()
        self.assertTrue(dash["id"] in part or re.search(r"[\"“]%s[\"”]" % re.escape(dash["label_today"]), part),
                        f"{where}: name the dashboard this task changes, {dash['item']} (`{dash['id']}`, labelled "
                        f"\"{dash['label_today']}\" in the org), by its id or its quoted label: the org's dashboard "
                        "labelled \"GLOW Club Training\" is D3, the Observations dashboard")
        # each measure: its label (unchanged, as glow/sf_keep_list.csv gives it) with the field it counts, in one
        # table row, list item or sentence that names no other item's field
        items = self.items()
        labels = {n: r["label_today"] for n, r in items.items()}
        for n, row in sorted(items.items()):
            field = self.FIELDS[n]
            others = [f for k, f in self.FIELDS.items() if k != n]
            label = row["label_today"]
            self.assertIn(label, part, f"{where}: name item {n} by its label {label!r} (`glow/sf_keep_list.csv`; "
                                       "labels stay as they are, #70)")
            self.assertTrue([u for u in units if label in u and field in u and not any(f in u for f in others)],
                            f"{where}: say what item {n} ({label!r}) counts, the field `DHIS2__c.{field}`, in one table "
                            "row, list item or sentence that names no other item's field")
        # no unit that names an item gives it another item's field ("item 13 also counts Lead_any_…")
        for u in units:
            refs = self.item_refs(u, labels)
            if not refs:
                continue
            stray = sorted(k for k, f in self.FIELDS.items() if f in u and k not in refs)
            self.assertFalse(stray, f"{where}: a row, item or sentence naming item(s) {sorted(refs)} also carries the "
                                    f"field of item(s) {stray}; each item counts its own field: {u[:200]!r}")
        # the period, the grouping, the test-record rule
        self.assertTrue([s for s in cl if self.PERIOD.search(s) and self.stated(s, self.LAST_12)],
                        f"{where}: the default period is the last 12 months, `Period__c` `LAST_N_MONTHS:12` (Ryan, "
                        "2026-10-24; #128), in one sentence, not negated")
        grouped = []
        for s in cl:
            g = self.GROUPS_BY.search(s)
            if not g or self.d.locally_denied(s, g):
                continue
            acc = self.ACCOUNT.search(s, g.start())
            if acc and [m for m in self.MONTH.finditer(s, acc.end())]:
                grouped.append(s)
        self.assertTrue(grouped, f"{where}: every report groups by the partner (`DHIS2__c.Account__c`), then by the month "
                                 "(`Period__c`), in that order, in one sentence, not negated")
        self.assertNoOtherDate(part, where)
        self.k.assertTestRecordRule(text, where)
        # the dashboard's one filter, Partner Manager; no Partner filter, no Month filter (Ryan, 2026-10-24)
        self.assertTrue([s for s in cl if self.one_pm_filter(s)],
                        f"{where}: the dashboard's one filter is Partner Manager, on "
                        "`DHIS2__c$Account__c.Assigned_Partner_Manager__c` (Ryan, 2026-10-24), in one sentence naming "
                        "the dashboard, its one (or only) filter, Partner Manager and the field, not negated")
        self.assertNoPartnerOrMonthFilter(part, where)
        # the SOQL signal: per component, a real query on DHIS2__c aggregating its field (#74: SUM for 13 and 14,
        # GROUP BY the field for 15 and 16), with the test-record rule and a period on Period__c, in a unit naming it
        for n, field in sorted(self.FIELDS.items()):
            shape = f"SUM({field})" if n in self.NUMBER_ITEMS else f"{field}, COUNT(Id) … GROUP BY {field}"
            self.assertTrue([u for u in units if field in u for q in self.queries(u) if self.item_query(n, q)],
                            f"{where}: give item {n}'s SOQL signal as a query, in one table row, list item or sentence: "
                            f"`SELECT {shape} FROM DHIS2__c WHERE Period__c = LAST_N_MONTHS:12 AND Account__c != null "
                            "AND (NOT Account__r.Name LIKE '%test%')` (or the last complete month on `Period__c`)")
        partner_q = re.compile(r"(?i)\bAccount__r\.Name\s*=\s*'|\bAccount__c\s*=\s*'")
        self.assertTrue([q for q in self.queries(part) if partner_q.search(q[1])
                         and any(self.item_query(n, q) for n in self.FIELDS)],
                        f"{where}: give the query for one partner's number, an item's query (its SUM or GROUP BY, the "
                        "period on `Period__c`, `Account__c != null`, `NOT Account__r.Name LIKE '%test%'`) with `AND "
                        "Account__r.Name = '<partner>'`: the check of one partner's number in the reports' Partner and Month "
                        "grouping (the dashboard has no Partner filter)")
        # the rollback: the copies in Decommissioned and this change's before/ retrieve
        self.assertTrue([s for s in cl if self.stated(s, self.RESTORE) and "Decommissioned" in s
                         and self.COPY.search(s)],
                        f"{where}: name the rollback: the copies in Decommissioned (one sentence, not negated)")
        self.assertRegex(part, self.BEFORE, f"{where}: name this change's retrieve `data/sf_dash_training_<date>/before/`")
        self.assertNoOlderBuild(part, where)
        self.assertNoOtherChange(part, where)
        self.assertBeforeGuarded(part, where)
        self.assertNotSoft(part, where)
        self.d.assertNoContradiction(part, where)

    # --- the plan ---------------------------------------------------------------------------------------------

    def test_the_training_rollback_names_the_copies_and_the_before_folder(self):
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        where = f"{name}: `## Rollback`"
        raw = self.plan_part(path, "## Rollback", 20)
        cl = self.clauses(raw)
        self.assertTrue([s for s in cl if self.stated(s, self.RESTORE) and "Decommissioned" in s and self.COPY.search(s)
                         and DecommissionedFoldersDocs.REPORT_AND_DASHBOARD.search(s)],
                        f"{where}: restore the dashboard and its reports from their copies in Decommissioned (one "
                        "sentence, not negated)")
        self.assertRegex(raw, self.BEFORE, f"{where}: name this change's `before/`, "
                                           "`data/sf_dash_training_<date>/before/`")
        dirs = set(self.WORK_DIR.findall(flat(raw)))
        self.assertEqual(len(dirs), 1, f"{where}: one folder for this change, "
                                                   f"`data/sf_dash_training_<date>/` (found {sorted(dirs)})")
        guarded = [s for s in cl if "before/" in s and "after/" in s and self.FRESH.search(s)
                   and self.stated(s, self.EQUAL_STRICT) and self.stated(s, self.CONDITION)]
        self.assertTrue(guarded, f"{where}: deploy `before/` back only while a fresh retrieve equals `after/` (one "
                                 "sentence naming `before/`, a fresh retrieve, `after/`, the condition and \"equals\", "
                                 "\"matches\", \"is identical to\" or \"shows no differences from\")")
        for s in guarded:
            for m in self.DIFFER.finditer(s):
                self.assertTrue(self.d.locally_denied(s, m),
                                f"{where}: `before/` goes back only while the fresh retrieve EQUALS `after/`, never when "
                                f"it differs: {s[:200]!r}")
        self.assertTrue([s for s in cl for m in self.OLDER_BUILD.finditer(s) if self.d.locally_denied(s, m)],
                        f"{where}: say never from an older build (DECISIONS 2026-10-16), in one sentence")
        self.assertNoOlderBuild(raw, where)
        body = self.norm(raw)
        self.assertRegex(body, r"(?i)check-only|--dry-run", f"{where}: a deploy of `before/` is checked-only first")
        self.assertRegex(body, r"Ryan['’]s go\b", f"{where}: the rollback's writes wait for Ryan's go")
        for rx, what in ((r"destructiveChanges", "a `destructiveChanges` deploy"),
                         (r"\bsf project delete\b", "`sf project delete`"),
                         (r"(-X\s*|--method\s+)DELETE\b|\bDELETE\s+/services/", "an HTTP DELETE")):
            self.assertNotRegex(raw, rx, f"{where}: {what} deletes; the rollback restores and deletes nothing")
        self.assertNoOtherChange(raw, where)
        self.assertBeforeGuarded(raw, where)
        self.assertNotSoft(raw, where)
        self.d.assertNoContradiction(raw, where, rollback=True)

    def test_a_plan_carries_the_training_deploy(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        text = read(path)
        keys, _ = docs_index.frontmatter(text)
        self.assertIn("status", keys, f"{name}: frontmatter `status:`")
        word, problem = docs_index.status_of(keys["status"])
        self.assertIsNone(problem, f"{name}: {problem}")
        self.assertNotEqual(word, "superseded", f"{name}: the plan is the change in force")
        if word == "done":
            self.assertRegex(keys.get("done", ""), r"^\d{4}-\d\d-\d\d", f"{name}: a done plan carries `done:`")
        # the plan, like the RUNBOOK, never gives the dashboard a Partner or Month filter or control (Ryan, 2026-10-24)
        self.assertNoPartnerOrMonthFilter(text, name)
        self.assertRegex(text.split("\n## ", 1)[0], self.TICKET,
                         f"{name}: name ticket #78 in the frontmatter, the title or the opening paragraph")
        self.assertRegex(text, r"(?m)^## Result\b", f"{name}: no `## Result` section")

        raw = self.plan_part(path, "## Rollout", 40)
        where = f"{name}: `## Rollout`"
        cl = self.clauses(raw)
        fl = flat(raw)
        self.assertRegex(fl, self.BEFORE, f"{where}: retrieve fresh into `data/sf_dash_training_<date>/before/`")
        # the copies: tools/sf_report_folders.py copy of the dashboard and of each report, tagged #78, VPN off
        cmds = [flat(seg)[m.start():] for seg in re.split(r"`+|\n\s*\n|(?=\bpython3\s)", raw)
                for m in [self.COPY_CMD.search(flat(seg))] if m]
        self.assertTrue(cmds, f"{where}: the copies by `python3 tools/sf_report_folders.py copy --vpn-off --kind "
                              "report|dashboard --id <id> --tag \"#78\" --apply`")
        for c in cmds:
            self.assertIn("--vpn-off", c, f"{where}: the tool refuses to run without `--vpn-off`: {c[:160]!r}")
            self.assertRegex(c, r"--apply\b", f"{where}: each copy runs with `--apply` (on Ryan's go); without it the "
                                              f"tool makes no copy: {c[:160]!r}")
            tags =[v.strip("`'\"") for v in re.findall(r"--tag(?:=|\s+)(\S+)", c)]
            self.assertTrue(tags and all(t == "#78" for t in tags), f"{where}: each copy is tagged `--tag \"#78\"`: "
                                                                    f"{c[:160]!r}")
        def flag(c, f):
            return [v.strip("`'\".,;") for v in re.findall(r"--%s(?:=|\s+)(\S+)" % f, c)]
        dash = self.dashboard()
        wanted = [("dashboard", dash["id"], f"the dashboard {dash['item']}")]
        wanted += [("report", r["id"], f"item {n}") for n, r in sorted(self.items().items())]
        for kind, rid, what in wanted:
            self.assertTrue([c for c in cmds if rid in flag(c, "id") and flag(c, "kind") == [kind]],
                            f"{where}: copy {what} with its own command, `python3 tools/sf_report_folders.py copy "
                            f"--vpn-off --kind {kind} --id {rid} --tag \"#78\" --apply` (its id from "
                            "`glow/sf_keep_list.csv`, no placeholder)")
        self.assertTrue([s for s in cl if self.stated(s, self.COPY) and "Decommissioned" in s
                         and DecommissionedFoldersDocs.REPORT_AND_DASHBOARD.search(s)],
                        f"{where}: the dashboard and each of its reports are copied into Decommissioned (one sentence, "
                        "not negated)")
        self.assertTrue([s for s in cl if re.search(r"(?i)check-only|--dry-run", s) and re.search(r"(?i)\bdeploy", s)
                         and not self.d.denies(s)],
                        f"{where}: validate check-only (`sf project deploy start --dry-run`) before the deploy (one "
                        "sentence)")
        self.assertTrue([s for s in cl if re.search(r"Ryan['’]s go\b", s) and re.search(r"(?i)\bdeploy|--apply", s)
                         and not self.d.denies(s)],
                        f"{where}: the deploy and each `--apply` wait for Ryan's go (one sentence)")
        readback = [s for s in cl if [m for m in self.READBACK.finditer(s) if not self.d.locally_denied(s, m)]
                    and re.search(r"(?i)\bretriev\w*|\bread\w*\s+(it\s+)?back\b", s)]
        self.assertTrue(readback, f"{where}: read back: retrieve into `after/` and check `after/` equals `build/` (\"…"
                                  "`after/` and check it equals `build/`\", \"`after/` matches `build/`\", \"compare "
                                  "`after/` with `build/`: no differences beyond normalisation\"), in one sentence")
        soql = [s for s in cl if (re.search(r"\bSOQL\b", s) and "DHIS2__c" in s or self.SOQL_ON_DHIS2.search(s))
                and self.stated(s, self.EQUAL_STRICT) and re.search(r"(?i)\bcomponents?\b", s)]
        self.assertTrue(soql, f"{where}: check that each component equals SOQL on `DHIS2__c` (one sentence naming the "
                              "components, SOQL on `DHIS2__c` and that they equal it)")
        self.assertNotSoft(raw, where)
        # the order, step by step (not by distance in the text): before/, copies, check-only, deploy on Ryan's go,
        # after/, SOQL
        steps = self.step_clauses(raw, where)
        flat_cl = [(i, j, n, st, c) for i, (n, st, cs) in enumerate(steps) for j, c in enumerate(cs)]
        not_check = re.compile(r"(?i)check-only|--dry-run|\bvalidat\w*")
        deploy_verb = re.compile(r"(?i)(?<!\bthe )(?<!\ba )(?<!\bits )(?<!\bfor )(?<!\bthis )(?<!\bto )\bdeploy(s|ed|ing)?\b")

        def first(pred, after=(-1, -1), what=""):
            found = [(i, j) for i, j, n, st, c in flat_cl if (i, j) > after and pred(c, st)]
            self.assertTrue(found, f"{where}: in the numbered steps, no {what}"
                                   + (" after the step before it" if after != (-1, -1) else ""))
            return found[0]
        at_before = first(lambda c, st: self.BEFORE.search(c), what="retrieve into `before/`")
        at_copy = first(lambda c, st: re.search(r"sf_report_folders[._]py\s+copy\b", c), at_before,
                        "copy step (`tools/sf_report_folders.py copy`)")
        at_check = first(lambda c, st: not_check.search(c), at_copy, "check-only (`--dry-run`)")
        early = [c for i, j, n, st, c in flat_cl if (i, j) < at_check and not not_check.search(c)
                 for m in deploy_verb.finditer(c) if not self.d.locally_denied(c, m)]
        self.assertEqual(early, [], f"{where}: nothing deploys before the check-only: {early[:1]}")
        at_deploy = first(lambda c, st: re.search(r"(?i)\bdeploy\w*", c) and not not_check.search(c), at_check,
                          "deploy after the check-only")
        deploy_step = steps[at_deploy[0]]
        self.assertRegex(deploy_step[1], r"Ryan['’]s go\b",
                         f"{where}: step {deploy_step[0]}, the deploy, waits for Ryan's go (say so in that step)")
        check_step = steps[at_check[0]]
        for st, what in ((check_step, "the check-only"), (deploy_step, "the deploy")):
            self.assertRegex(st[1], r"\bbuild/", f"{where}: step {st[0]}, {what}, names what it deploys: `build/`")
            nst = self.norm(st[1])
            for m in re.finditer(r"before/", nst):
                self.assertTrue(self.d.locally_denied(nst, m),
                                f"{where}: step {st[0]}, {what}, deploys `build/`, never `before/` (that is the "
                                f"rollback's): {nst[:200]!r}")
        for n, st, _cs in steps:
            if "--apply" in st:
                self.assertRegex(st, r"Ryan['’]s go\b", f"{where}: step {n} runs `--apply`; say in that step it waits "
                                                       "for Ryan's go")
        at_after = first(lambda c, st: "after/" in c, at_deploy, "retrieve into `after/`")
        first(lambda c, st: re.search(r"\bSOQL\b|\bFROM\s+DHIS2__c\b", c), at_after, "SOQL check")
        self.assertNoOlderBuild(raw, where)
        self.d.assertNoContradiction(raw, where)

    # --- the rollout's Result (the ticket's comment of 2026-10-26: steps 1-8 done) ---------------------------------

    # the rollout's record, from that comment (not read from the docs under test)
    CHECK_ONLY_ID = "0AfRP000002i74f0AA"
    DEPLOY_ID = "0AfRP000002i76H0AQ"
    COPIES = {"13": "00ORP000009kU9B2AU", "14": "00ORP000009kUAn2AM", "15": "00ORP000009kUCP2A2",
              "16": "00ORP000009kUE12AM", "D4": "01ZRP00000BPIjN2AX"}
    MOVED = ("00ORP000005ufNN2AY", "00ORP000005uecc2AA")     # step 8: the two "DHIS2 Reports" reports
    ZERO_AF = re.compile(r"(?<![A-Za-z0-9])0Af[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?(?![A-Za-z0-9])")
    CHECK_WORD = re.compile(r"(?i)check-only|--dry-run|\bvalidat\w*|\bcheck\s+only\b")
    DEPLOY_WORD = re.compile(r"(?i)\bdeploy\w*")
    ITEM_REF = re.compile(r"(?i)\bitems?\s+((?:1[2-6]\b(?:\s*(?:,|and|&|-|–|to)\s*(?=1[2-6]\b))?)+)")
    STEP_REF = re.compile(r"(?i)\bsteps?\s+((?:\d{1,2}\b(?:\s*(?:,|and|&|-|–|to)\s*(?=\d{1,2}\b))?)+)")
    # a step still to run; "left" only as "Left:", "is/are left", "left to" (never "nothing left", "#77 left it")
    REMAINS = re.compile(r"(?i)\b(remain\w*|wait\w*|await\w*|pending|not yet|outstanding|later|to do)\b|"
                         r"\bleft\s*:|\b(is|are|still)\s+left\b|\bleft\s+to\b")
    STILL_TO_RUN = re.compile(r"(?i)\b(remain\w*|wait\w*|await\w*|pending|not yet|outstanding)\b")
    DONE = re.compile(r"(?i)\b(done|ran|completed?|succeeded|finished|carried out|performed|executed)\b")
    # what steps 9 and 10 are not (2026-10-26): done, or not needed
    NOT_LEFT = re.compile(r"(?i)\b(done|ran|completed?|succeeded|finished|carried out|performed|executed|not needed|"
                          r"no longer needed|unnecessary|unneeded|needless|skipped|dropped|cancell?ed|moot)\b")
    # a Result line that says something went wrong (a negation before it voids it)
    WRONG = re.compile(r"(?i)\b(mismatch\w*|fail(s|ed|ing|ures?)?|rolled\s+(it\s+|them\s+)?back|reverted|undone|"
                       r"unequal|discrepanc\w*|inconsistent|wrong|errors?)\b|≠")
    # a count that disagrees: the negated equality is itself the contradiction
    NOT_EQUAL = re.compile(r"(?i)\b(does|do|did|is|are|was|were)\s*(not|n['’]t)\s+(equal|match|agree|the same)\w*|"
                           r"\bnot\s+(equal|identical|the same)\b")
    DIFFERS = re.compile(r"(?i)\b(differ|differs|differed|different|diverg\w*)\b")
    # a failure the Result may honestly record: the bodiless PUT in sf 2.151
    PUT_CONTEXT = re.compile(r"\bPUT\b|(?<![^\s`])-b\b|\bbody\b|\b2\.151\b")
    # before what a sentence says happened, a wish, a condition or a future: not that it happened
    WISH = re.compile(r"(?i)\b(should|would|could|must|ought|want\w*|supposed|meant|intended|planned|plans?|expected|"
                      r"asks?|asked|to\s+be|will|shall|needs?\s+to|scheduled|due|going\s+to|ready\s+to|until|once|"
                      r"when|if|can|may|might|be|yet)\b")
    # item 16 may still be "not deployed" (step 9); the build is not
    NOTHING_DEPLOYED = re.compile(r"(?i)\bnothing\s+(is\s+|was\s+|has\s+been\s+)?(yet\s+)?deployed\b")
    PUT_BODY = re.compile(r"(?:(?<![^\s`])-b|--body)(?:=|\s+)['\"]?\{\s*\}['\"]?")
    PUT_METHOD = re.compile(r"(?:--method|-X)(?:=|\s+)['\"]?PUT\b")

    @staticmethod
    def expand(nums):
        """`13-15`, `13, 14 and 15`, `9 and 10` -> the set of numbers, as strings."""
        got = set(re.findall(r"\d+", nums))
        for a, b in re.findall(r"(\d+)\s*(?:-|–|to)\s*(\d+)", nums):
            got |= {str(i) for i in range(int(a), int(b) + 1)}
        return got

    @staticmethod
    def num(n):
        """Integer `n` as written in prose: `1,422` or `1422`, not part of a longer number."""
        body = re.escape(f"{n:,}").replace(",", ",?")
        return re.compile(r"(?<![\d,.])" + body + r"(?![\d]|[,.]\d)")

    @staticmethod
    def at(text, pos):
        """A match at `pos` of `text`, for `locally_denied`."""
        return re.compile("").match(text, pos)

    def result(self):
        path = self.plan_path()
        return path, self.plan_part(path, "## Result", 40)

    def result_units(self, raw):
        """The Result's units (a table row, a list item, a sentence), a `;` kept inside its sentence."""
        return self.units(raw.replace(";", ","))

    def segments(self, unit, rx):
        """[(numbers, text)]: `unit` cut at each reference `rx` (`item 13`, `steps 9 and 10`), each piece running to
        the next reference."""
        refs = list(rx.finditer(unit))
        return [(self.expand(m.group(1)), unit[m.start():refs[i + 1].start() if i + 1 < len(refs) else len(unit)])
                for i, m in enumerate(refs)]

    def item_segments(self, raw):
        """[(items, text)]: each unit cut at each item reference (`item 13`, `items 13 and 14`, a table row's first
        cell), each piece running to the next reference in the same unit."""
        out = []
        for unit in self.result_units(raw):
            row = re.match(r"\|\s*`?(1[2-6])`?\s*\|", unit)
            if row:
                out.append(({row.group(1)}, unit))
            out += self.segments(unit, self.ITEM_REF)
        return out

    def labels(self, raw, rid, refs_of):
        """[(label, unit)]: the label of each occurrence of id `rid` in the Result: in its comma-bounded clause the
        nearest before it, else the nearest after it; with none in that clause, the nearest in its unit (None: none
        in its unit)."""
        got = []
        for u in self.result_units(raw):
            refs = refs_of(u)
            for m in re.finditer(re.escape(rid), u):
                at, end = m.start(), m.end()
                lo, hi = u.rfind(",", 0, at) + 1, (u.find(",", end) + 1 or len(u) + 1) - 1
                before = [(r, k) for r, k in refs if lo <= r.start() and r.end() <= at]
                after = [(r, k) for r, k in refs if end <= r.start() and r.end() <= hi]
                label = (max(before, key=lambda rk: rk[0].end())[1] if before else
                         min(after, key=lambda rk: rk[0].start())[1] if after else self.nearest(u, at, len(rid), refs))
                got.append((label, u))
        return got

    @staticmethod
    def nearest(unit, at, length, refs):
        """Of [(match, key)], the key of the match nearest to `unit[at:at+length]`; before it wins a tie."""
        best = None
        for m, key in refs:
            if m.end() <= at:
                d = (at - m.end(), 0)
            elif m.start() >= at + length:
                d = (m.start() - (at + length), 1)
            else:
                continue
            if best is None or d < best[0]:
                best = (d, key)
        return best[1] if best else None

    def test_the_training_result_records_the_deploy_and_the_copies(self):
        path, raw = self.result()
        where = f"{os.path.relpath(path, REPO)}: `## Result`"
        fl = flat(raw)
        # broad: two deploy-request ids (`0Af…`), one the check-only's and one the deploy's
        ids = set(self.ZERO_AF.findall(fl))
        self.assertGreaterEqual(len(ids), 2, f"{where}: record the check-only's and the deploy's ids (`0Af…`, two "
                                             f"different ids); found {sorted(ids)}")

        def deploy_refs(u):
            checks = list(self.CHECK_WORD.finditer(u))
            spans = [(c.start(), c.end()) for c in checks]
            refs = [(m, "check") for m in checks]
            refs += [(m, "deploy") for m in self.DEPLOY_WORD.finditer(u)
                     if not any(a <= m.start() < b or m.start() <= a < m.end() for a, b in spans)
                     and not re.search(r"(?i)check[\s-]*$|--dry-run\s*$", u[:m.start()])]
            return refs
        # every occurrence of each id beside its own label, never the other's
        for rid, want, what in ((self.CHECK_ONLY_ID, "check", "the check-only (step 3)"),
                                (self.DEPLOY_ID, "deploy", "the deploy (step 4)")):
            got = self.labels(raw, rid, deploy_refs)
            self.assertTrue(got, f"{where}: record {what}'s id `{rid}`")
            self.assertIn(want, {k for k, _u in got}, f"{where}: `{rid}` is {what}'s id: name it beside that id "
                                                     f"(\"check-only `{self.CHECK_ONLY_ID}`\", \"deploy "
                                                     f"`{self.DEPLOY_ID}`\")")
            wrong = [u for k, u in got if k not in (want, None)]
            self.assertEqual(wrong, [], f"{where}: `{rid}` is {what}'s id only; here it stands beside the other "
                                        f"step's name: {wrong[:1]}")
        # the copies in Decommissioned, each id beside its own item (or D4 / the dashboard), never another's
        self.assertTrue([s for s in self.clauses(raw) if self.stated(s, self.COPY) and "Decommissioned" in s],
                        f"{where}: say the copies are in Decommissioned (one sentence, not negated)")
        originals = {n: r["id"] for n, r in self.items().items()}
        originals["D4"] = self.dashboard()["id"]

        def copy_refs(u):
            refs = [(m, min(n)) for m in self.ITEM_REF.finditer(u) for n in [self.expand(m.group(1))] if len(n) == 1]
            refs += [(m, k) for k, oid in originals.items() for m in re.finditer(re.escape(oid), u)]
            refs += [(m, "D4") for m in re.finditer(r"(?i)\bD4\b|\bdashboard\b", u)]
            return refs
        for key, cid in self.COPIES.items():
            what = "D4" if key == "D4" else f"item {key}"
            got = self.labels(raw, cid, copy_refs)
            self.assertTrue(got, f"{where}: record the Decommissioned copy of {what}, `{cid}`")
            self.assertIn(key, {k for k, _u in got}, f"{where}: the copy `{cid}` is {what}'s; name {what} beside it "
                                                    f"(\"{what} `{cid}`\")")
            wrong = [(k, u) for k, u in got if k not in (key, None)]
            self.assertEqual(wrong, [], f"{where}: the copy `{cid}` is {what}'s only; here it stands beside "
                                        f"another: {wrong[:1]}")
        # the ledger, dated before the deploy: said as a fact, not as what was wanted
        self.assertRegex(fl, r"data/sf_dash_training_\d{4}-\d\d-\d\d/ledger\.csv",
                         f"{where}: name the ledger `data/sf_dash_training_2026-10-24/ledger.csv`")
        before = []
        for s in self.clauses(raw):
            for part in re.split(r"(?i)\b(?:though|although|but|however|whereas|yet|while)\b", s):
                m = re.search(r"(?i)\bbefore\s+(the\s+|its\s+|this\s+)?(\w+\s+)?deploy\w*", part)
                if (m and re.search(r"(?i)\bledger\b", part) and not self.d.denies(part)
                        and not self.WISH.search(part[:m.start()])):
                    before.append(part)
        self.assertTrue(before, f"{where}: say the ledger's copy rows are dated before the deploy, as a fact (one "
                                "clause naming the ledger and \"before the deploy\", not negated, not what the plan "
                                "wanted)")

    def test_the_training_result_carries_the_soql_counts_and_the_read_back(self):
        path, raw = self.result()
        where = f"{os.path.relpath(path, REPO)}: `## Result`"
        fl = flat(raw)
        units = self.result_units(raw)
        segs = self.item_segments(raw)
        # broad: the period, then each item's numbers in its own piece of text
        self.assertRegex(fl, r"(?i)LAST_N_MONTHS:12|\b12\s+months\b",
                         f"{where}: the SOQL check runs over the reports' period, the last 12 months")
        want = {"13": (567, 1422), "14": (567, 524), "15": (524, 199, 325)}
        for n, numbers in want.items():
            mine = [t for items, t in segs if n in items]
            self.assertTrue(mine, f"{where}: give item {n}'s counts (\"item {n}: …\")")
            hit = [t for t in mine if all(self.num(x).search(t) for x in numbers)]
            self.assertTrue(hit, f"{where}: item {n}'s report and SOQL: " + ", ".join(f"{x:,}" for x in numbers)
                                 + f" (in the text naming item {n}; found {mine[:3]})")
        # item 15: Yes 199, No 325, each number beside its own answer, never crossed
        pairs = []
        for items, t in segs:
            if "15" in items:
                words = [(m, m.group(0).lower()) for m in re.finditer(r"(?i)\b(yes|no)\b", t)]
                pairs.append(({x: {self.nearest(t, m.start(), len(m.group(0)), words) for m in self.num(x).finditer(t)}
                               for x in (199, 325)}, t))
        self.assertTrue([t for p, t in pairs if p[199] == {"yes"} and p[325] == {"no"}],
                        f"{where}: item 15's split, Yes 199 and No 325, each number beside its answer")
        crossed = [t for p, t in pairs if "no" in p[199] or "yes" in p[325]]
        self.assertEqual(crossed, [], f"{where}: item 15 is Yes 199, No 325, not the other way round: {crossed[:1]}")
        # each equals SOQL
        self.assertTrue([u for u in units if re.search(r"\bSOQL\b", u)
                         and (self.stated(self.norm(u), self.EQUAL_STRICT) or re.search(r"\s=\s|=\s*SOQL", u))],
                        f"{where}: say each component's numbers equal SOQL")
        # the test-record rule: 567 with it, the 2 test records left out (not kept in)
        self.assertTrue([u for u in units if self.num(567).search(u) and re.search(r"(?i)\brule\b|\btest\b", u)],
                        f"{where}: 567 Monthly Reports with the test-record rule")
        two_test = re.compile(r"(?i)(?<![\d,.])2\s+(?:[\w`'-]+\s+){0,2}?test\b|"
                              r"\btest[\w-]*\s+(?:[\w:`'-]+\s+){0,3}?\(?2(?!\d|[,.]\d)")
        out = re.compile(r"(?i)\b(left\s+out|leaves?\s+out|leaving\s+out|exclud\w*|filter(s|ed|ing)?\s+out|"
                         r"drops?|dropped|removes?|removed|without\s+(them|those|the\s+2|the\s+two))\b|"
                         r"(?<![\d,.])567\s+(Monthly\s+Reports\s+|records\s+)?with\s+(the|its)\s+(test[\w-]*\s+)?rule\b")
        keep = re.compile(r"(?i)\b(keeps?|kept|keeping|includ\w*|counted|left\s+in|lets?\s+in|let\s+through|"
                          r"in\s+the\s+count)\b")
        two = []
        for u in units:
            for m in two_test.finditer(u):
                clause = re.split(r"[,(]", u[:m.start()])[-1] + re.split(r"[,)]", u[m.start():])[0]
                if self.stated(u, out) and not self.stated(clause, keep):
                    two.append(u)
        self.assertTrue(two, f"{where}: the 2 test records the rule leaves out (the check means something), not kept "
                             "in")
        # one partner, September 2026, item 14: 1 = 1
        sept = re.compile(r"(?i)\bSept(?:ember|\.)?\s+2026\b|\b2026-09\b|\b202609\b")
        one_partner = re.compile(r"(?i)\b(one|a single|single|one-)\s*partner")
        one_eq = re.compile(r"(?<![\d,.])1\s*(?:=|/|equals?|matches|and|,)\s*(?:the\s+)?(?:SOQL\s+|query\s+)?1(?!\d|[,.]\d)")
        self.assertTrue([t for items, t in segs if "14" in items and one_eq.search(t)
                         and [u for u in units if t in u and sept.search(u) and one_partner.search(u)]],
                        f"{where}: the one-partner check: one partner, September 2026, item 14, report 1 = SOQL 1")
        # step 1: the fresh retrieve equals `before/`
        eq = (r"(equal(s|led)?|match(es|ed)?|(is|was)\s+identical\s+to|identical\s+to|(is|was)\s+the\s+same\s+as|"
              r"byte-equal\s+to)")
        fresh = re.compile(r"(?i)\bfresh\b[^.]{0,80}?\b" + eq + r"\b[^.]{0,30}?before/|"
                           r"before/`?\s+" + eq + r"\b[^.]{0,80}?\bfresh\b")
        self.assertTrue([u for u in units for m in fresh.finditer(self.norm(u)) if re.search(r"(?i)retriev", u)
                         and not self.d.locally_denied(self.norm(u), m)],
                        f"{where}: step 1: the fresh retrieve equals `before/` (\"fresh retrieve `fresh_2026-10-26/` "
                        "equals `before/`\")")
        # the read-back: after/ equals build/ beyond normalisation, the one difference named, on item 15
        rb = [s for s in self.clauses(raw) if [m for m in self.READBACK.finditer(s) if not self.d.locally_denied(s, m)]]
        self.assertTrue(rb, f"{where}: the read-back: `after/` equals `build/` (beyond normalisation)")
        self.assertRegex(fl, r"(?i)normali[sz]ation", f"{where}: `after/` equals `build/` beyond normalisation")
        diff = []
        for u in units:
            sv = re.search(r"showValues", u)
            if not sv or not re.search(r"(?i)\btrue`?\s*(->|→|to)\s*`?false\b", u):
                continue
            refs = [(m, frozenset(self.expand(m.group(1)))) for m in self.ITEM_REF.finditer(u)]
            if self.nearest(u, sv.start(), len(sv.group(0)), refs) == frozenset({"15"}):
                diff.append(u)
        self.assertTrue(diff, f"{where}: the one difference: `showValues` true -> false on item 15's ColumnStacked "
                              "component (item 15 named beside it)")

    def assertNothingWentWrong(self, raw, where):
        """The record of 2026-10-26 is steps 1-8 done, every count equal to SOQL: the Result says no step failed or
        was rolled back, no count disagrees, nothing but the read-back's `showValues` differs, and nothing but
        step 10 (the Subscribe) is still to run: a line about step 9, item 16 or #77 that says it waits is wrong."""
        found = []
        for u in self.result_units(raw):
            n = self.norm(u)
            for m in self.WRONG.finditer(n):
                if re.match(r"(?i)fail|error", m.group(0)) and self.PUT_CONTEXT.search(u):
                    continue            # the bodiless PUT that fails in sf 2.151
                if not self.d.locally_denied(n, m):
                    found.append(f"{m.group(0)!r}: {u[:160]!r}")
                    break
            m = self.NOT_EQUAL.search(n)
            if m:
                found.append(f"{m.group(0)!r}: {u[:160]!r}")
            if "showValues" not in u:
                m = [m for m in self.DIFFERS.finditer(n) if not self.d.locally_denied(n, m)]
                if m:
                    found.append(f"{m[0].group(0)!r}: {u[:160]!r}")
            # only step 10 (Ryan's Subscribe) is still to run: step 9, item 16 and #77 are done (ticket #152)
            later = ([1 for got, _s in self.segments(u, self.STEP_REF) if "10" in got]
                     or re.search(r"(?i)\bSubscribe\b|(?<![\w#])#80\b", u))
            if not later and self.stated(n, self.STILL_TO_RUN):
                found.append(f"still to run: {u[:160]!r}")
        self.assertEqual(found, [], f"{where}: steps 1-8 ran and every count equals SOQL (2026-10-26); the Result says "
                                    "otherwise: " + "; ".join(found[:3]))

    def test_the_training_plan_is_in_progress_with_step_10_left(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        path, raw = self.result()
        name = os.path.relpath(path, REPO)
        where = f"{name}: `## Result`"
        text = read(path)
        keys, _ = docs_index.frontmatter(text)
        front = text.split("\n---", 1)[0] if text.startswith("---") else ""
        for part, label in ((raw, where), (front, f"{name}: the frontmatter")):
            for s in self.clauses(part, ".;:\n"):
                m = self.NOTHING_DEPLOYED.search(s)
                self.assertIsNone(m, f"{label}: the build is deployed (2026-10-26); drop {m and m.group(0)!r}: "
                                     f"{s[:200]!r}")
        word, problem = docs_index.status_of(keys.get("status", ""))
        self.assertEqual(word, "in-progress", f"{name}: `status:` stays `in-progress` while step 10 (Ryan's Subscribe) waits")
        units = self.result_units(raw)
        steps = [(got, u, seg) for u in units for got, seg in self.segments(u, self.STEP_REF)]
        # steps 1-8: done, said as such (in the text from the step reference, or in the lead-in before it)
        done = set()
        for u in units:
            segs = self.segments(u, self.STEP_REF)
            lead = u[:self.STEP_REF.search(u).start()] if segs else ""
            for got, seg in segs:
                if self.stated(self.norm(seg), self.DONE) or self.stated(self.norm(lead), self.DONE):
                    done |= got
        missing = sorted({str(i) for i in range(1, 10)} - done, key=int)
        self.assertEqual(missing, [], f"{where}: say steps 1-9 are done (\"steps 1-8 done, 2026-10-26\", \"step 9 "
                                      f"ran\"); not said of step(s) {', '.join(missing)}")
        # step 10: still to run (ticket #152: step 9, item 16, ran after #77 landed)
        self.assertTrue([u for got, u, _seg in steps if "10" in got and self.stated(self.norm(u), self.REMAINS)]
                        + [u for u in units if re.search(r"(?i)\bSubscribe\b", u)
                           and self.stated(self.norm(u), self.REMAINS)],
                        f"{where}: say step 10 (the weekly Subscribe) remains")
        over = [seg for got, _u, seg in steps if "10" in got and self.stated(self.norm(seg), self.NOT_LEFT)]
        self.assertEqual(over, [], f"{where}: step 10 (the weekly Subscribe) is still to run; it is neither done nor "
                                   f"not needed: {over[:1]}")
        # what a reference to steps 2-9 says, to the next step reference, never waits
        waits = [seg for got, _u, seg in steps if got & {str(i) for i in range(2, 10)}
                 and self.stated(self.norm(seg), self.STILL_TO_RUN)]
        self.assertEqual(waits, [], f"{where}: steps 1-9 are done; none of them waits: {waits[:1]}")
        # step 8: the two reports moved, the ledger holds 3 moves
        moves = [u for u in units for m in re.finditer(r"(?i)\b(3|three)\s+(\w+\s+)?moves\b", u)
                 if re.search(r"(?i)\bledger\b", u) and not self.d.locally_denied(u, m)
                 and not self.WISH.search(re.split(r"[,(]", u[max(0, m.start() - 40):m.start()])[-1])]
        self.assertTrue(moves, f"{where}: step 8 is done: say the ledger holds 3 moves")
        for rid in self.MOVED:
            self.assertTrue([u for u in units if rid in u and re.search(r"\bDecommissioned\b", u)
                             and not self.d.denies(u)],
                            f"{where}: step 8 moved `{rid}` to Decommissioned: say so beside its id")
        # and no line of the Result says otherwise
        self.assertNothingWentWrong(raw, where)

    # --- step 9 (ticket #152): item 16 on D4 ---------------------------------------------------------------------

    ITEM16_ID, D4_ID = "00ORP000004RJZ72AO", "01ZRP000006quAj2AI"
    # every id the plan already carries before step 9 (steps 2-4, #80): a step 9 id is a new one
    KNOWN_IDS = {"0AfRP000002i74f0AA", "0AfRP000002i76H0AQ", "0AfRP000002i9BJ0AY", "0AfRP000002i9850AA",
                 "00ORP000009kU9B2AU", "00ORP000009kUAn2AM", "00ORP000009kUCP2A2", "00ORP000009kUE12AM",
                 "01ZRP00000BPIjN2AX", "00ORP000009kXev2AE"}
    ID_01Z = re.compile(r"(?<![A-Za-z0-9])01Z[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?(?![A-Za-z0-9])")
    ID_00O = re.compile(r"(?<![A-Za-z0-9])00O[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?(?![A-Za-z0-9])")
    STEP9_START = re.compile(r"(?i)^(\s*)(#{1,6}\s+|(?:[-*+]|\d+[.)])\s+)?(?:\*\*|__)?Steps?\s+9\b")
    ANY_STEP_START = re.compile(r"(?i)^\s*(?:#{1,6}\s+|(?:[-*+]|\d+[.)])\s+)?(?:\*\*|__)?Steps?\s+\d")

    def step9_block(self, raw):
        """The Result's step 9 part: the lines from the one that starts with `Step 9` (a list item, a paragraph or a
        heading) to the next line that starts another step or leaves the item (a list item runs over its indented
        lines, a paragraph to its blank line, a heading to the next heading of its level or higher). None when no
        line starts that way."""
        lines = raw.splitlines()
        start = next((n for n, ln in enumerate(lines) if self.STEP9_START.match(ln)), None)
        if start is None:
            return None
        m = self.STEP9_START.match(lines[start])
        indent, marker = len(m.group(1)), (m.group(2) or "").strip()
        out = [lines[start]]
        for line in lines[start + 1:]:
            st = line.strip()
            if self.ANY_STEP_START.match(line):
                break
            if marker.startswith("#"):
                if st.startswith("#") and len(st) - len(st.lstrip("#")) <= len(marker):
                    break
            elif not st:
                if not marker:
                    break
            elif marker and len(line) - len(line.lstrip()) <= indent:
                break
            out.append(line)
        return "\n".join(out)

    def beside(self, fl, rid, refs, want, what, where):
        """Every occurrence of `rid` in `fl` stands nearest to a reference labelled `want`, never another's."""
        got = [self.nearest(fl, m.start(), len(rid), refs) for m in re.finditer(re.escape(rid), fl)]
        self.assertTrue(got, f"{where}: step 9 records {what}, `{rid}`")
        self.assertEqual({k for k in got if k != want}, set(),
                         f"{where}: `{rid}` is {what} only: name {want!r} nearest to it")

    @staticmethod
    def figure(s, word):
        """The numbers written beside `word` in `s`, either side: `answered 41`, `41 answered`, `Yes 37`, `4 No`."""
        return [int((a or b).replace(",", ""))
                for a, b in re.findall(rf"\b{word}\s+(\d+(?:,\d{{3}})*)\b|\b(\d+(?:,\d{{3}})*)\s+{word}\b", s)]

    def test_the_plan_result_records_step_9(self):
        path, raw = self.result()
        where = f"{os.path.relpath(path, REPO)}: `## Result`, step 9"
        block = self.step9_block(raw)
        self.assertIsNotNone(block, f"{where}: start a line of the Result with `Step 9` (a list item such as "
                                    "\"- Step 9: ...\", a paragraph or a heading) and keep step 9's facts in it, up "
                                    "to the next step")
        fl = flat(block)
        cl = self.clauses(block)
        self.assertNotIn("@", fl, f"{where}: counts and ids only, no mentor e-mail")

        def item_d4(u):
            return ([(m, "16") for m in re.finditer(r"(?i)\bitem\s+16\b", u)]
                    + [(m, "D4") for m in re.finditer(r"(?i)\bD4\b|\bdashboard\b", u)])
        # item 16's report and D4, each id beside its own name
        self.beside(fl, self.ITEM16_ID, item_d4(fl), "16", "item 16's report", where)
        self.beside(fl, self.D4_ID, item_d4(fl), "D4", "the dashboard D4", where)

        # item 16 is grouped by Partner and Month like items 13-15, its answer across
        grouped = []
        for s in cl:
            if re.search(r"(?i)\bitem\s+16\b", s) and re.search(r"(?i)\bMonths?\b", s):
                p = re.search(r"(?i)\bPartners?\b(?!\s+Manager)", s)
                refs = [m for m in self.ITEM_REF.finditer(s) if {"13", "14", "15"} <= self.expand(m.group(1))]
                if p and refs and not self.d.locally_denied(s, p):
                    grouped.append(s)
        self.assertTrue(grouped, f"{where}: say item 16 is grouped by Partner and Month like items 13-15 (one "
                                 "sentence naming item 16, Partner, Month and items 13-15, not negated)")
        field = self.FIELDS["16"]
        across = [s for s in cl for m in re.finditer(r"(?i)\bacross\b", s)
                  if field in s and not self.d.locally_denied(s, m)]
        self.assertTrue(across, f"{where}: say item 16's answer `{field}` goes across (one sentence, not negated)")
        for other in (v for k, v in self.FIELDS.items() if k != "16"):
            self.assertNotIn(other, fl, f"{where}: step 9 is item 16's: it carries no other item's field")

        # the two copies made that day: new ids, each beside its own name and in Decommissioned
        for rx, label, what, skip in ((self.ID_01Z, "D4", "D4's copy (`01Z...`)", {self.D4_ID}),
                                      (self.ID_00O, "16", "item 16's copy (`00O...`)", {self.ITEM16_ID})):
            ids = set(rx.findall(fl)) - skip - self.KNOWN_IDS
            self.assertTrue(ids, f"{where}: record {what} in Decommissioned: a new id, not one the plan already "
                                 "carries")
            for cid in sorted(ids):
                self.beside(fl, cid, item_d4(fl), label, what, where)
                self.assertTrue([s for s in cl if cid in s and "Decommissioned" in s and self.COPY.search(s)
                                 and not self.d.denies(s)],
                                f"{where}: `{cid}` is {what}: say in its sentence that it is a copy in "
                                "Decommissioned")
        before = []
        for s in cl:
            m = re.search(r"(?i)\bbefore\s+(the\s+|its\s+|this\s+)?(\w+\s+)?deploy\w*", s)
            if m and re.search(r"(?i)\bledger\b", s) and not self.d.denies(s) and not self.WISH.search(s[:m.start()]):
                before.append(s)
        self.assertTrue(before, f"{where}: say the ledger rows of the two copies are dated before the deploy, as a "
                                "fact (a sentence naming the ledger and \"before the deploy\")")

        # the check-only and the deploy: two new ids, each beside its own word
        new = set(self.ZERO_AF.findall(fl)) - self.KNOWN_IDS
        self.assertGreaterEqual(len(new), 2, f"{where}: record the check-only's and the deploy's ids (`0Af...`, two "
                                             f"new ids); found {sorted(new)}")
        checks = list(self.CHECK_WORD.finditer(fl))
        spans = [(c.start(), c.end()) for c in checks]
        refs = [(m, "check") for m in checks]
        refs += [(m, "deploy") for m in self.DEPLOY_WORD.finditer(fl)
                 if not any(a <= m.start() < b or m.start() <= a < m.end() for a, b in spans)
                 and not re.search(r"(?i)check[\s-]*$|--dry-run\s*$", fl[:m.start()])]
        labels = {i: {self.nearest(fl, m.start(), len(i), refs) for m in re.finditer(re.escape(i), fl)} for i in new}
        self.assertTrue([i for i, k in labels.items() if k == {"check"}],
                        f"{where}: name the check-only beside its id (\"check-only `0Af...`\"); found {labels}")
        self.assertTrue([i for i, k in labels.items() if k == {"deploy"}],
                        f"{where}: name the deploy beside its id (\"deploy `0Af...`\"); found {labels}")

        # the read-back
        readback = [s for s in cl if "after/" in s and "build/" in s
                    for m in re.finditer(r"(?i)\b(equals?|identical|matches|no differences)\b", s)
                    if not self.d.locally_denied(s, m)]
        self.assertTrue(readback, f"{where}: say the read-back: `after/` equals `build/` (one sentence naming both "
                                  "folders and \"equals\", not negated)")

        # the refresh: every component of D4 shows data
        refreshed = []
        for s in cl:
            if re.search(r"(?i)\brefresh\w*", s) and not self.d.denies(s):
                ofs = re.findall(r"\b(\d+)\s+of\s+(\d+)\b", s)
                if "DATA" in s or (ofs and all(a == b and int(a) >= 4 for a, b in ofs)):
                    refreshed.append(s)
        self.assertTrue(refreshed, f"{where}: say the refresh left every component of D4 with data (\"DATA\", or "
                                   "\"N of N components\" with N at least 4: items 12-16 less one)")

        # the last complete month's figure equals SOQL: numbers, and they add up
        found = []
        for s in cl:
            if not (re.search(r"\b(September|October)\b", s) and re.search(r"\bSOQL\b", s)):
                continue
            if not [m for m in re.finditer(r"(?i)\b(equal\w*|match\w*|agree\w*)\b|=", s)
                    if not self.d.locally_denied(s, m)]:
                continue
            ans, yes, no = self.figure(s, "answered"), self.figure(s, "Yes"), self.figure(s, "No")
            if len(ans) == len(yes) == len(no) == 1:
                found.append((s, ans[0], yes[0], no[0]))
        self.assertTrue(found, f"{where}: give item 16's figure for the last complete month, equal to SOQL, as "
                               "numbers: one sentence with the month, \"SOQL\", \"equal\", \"N answered\", \"Yes N\" "
                               "and \"No N\"")
        for s, ans, yes, no in found:
            self.assertGreater(ans, 0, f"{where}: a month with no answers proves nothing: {s[:160]!r}")
            self.assertEqual(ans, yes + no, f"{where}: the answered count is Yes plus No: {s[:160]!r}")

    def test_the_plan_front_matter_says_step_9_ran(self):
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        text = read(path)
        front = text.split("\n---", 1)[0] if text.startswith("---") else ""
        self.assertTrue(front, f"{name}: the plan starts with its frontmatter")
        nine = [seg for line in front.splitlines() for got, seg in self.segments(self.norm(line), self.STEP_REF)
                if "9" in got]
        self.assertTrue(nine, f"{name}: the frontmatter's status comment names step 9")
        left = re.compile(r"(?i)\b(left|remain\w*|wait\w*|await\w*|pending|not yet|outstanding|to do)\b")
        for seg in nine:
            self.assertFalse(self.stated(seg, left), f"{name}: step 9 ran (ticket #152): the frontmatter no longer "
                                                      f"leaves it: {seg[:120]!r}")
        self.assertTrue([seg for seg in nine if self.stated(seg, self.DONE)],
                        f"{name}: the frontmatter's status comment says step 9 ran (\"steps 1-9 ran\")")

    def test_the_runbook_puts_item_16_on_d4(self):
        where = f"RUNBOOK section {self.MONTHLY[3:]!r}, {self.PART[4:]!r}"
        part = self.part()
        said = []
        for s in self.clauses(part):
            if re.search(r"(?i)\bitem\s+16\b", s) and re.search(r"\bD4\b", s):
                for m in re.finditer(r"(?i)\b(joined|deployed|went\s+live|is\s+live|is\s+on|are\s+live|live\s+on)\b",
                                     s):
                    # item 16 is the subject of the verb: it stands in the same part of the sentence
                    pre = re.split(r"[,;(—–]|\bbut\b", s[max(0, m.start() - 60):m.start()])[-1]
                    if (re.search(r"(?i)\bitem\s+16\b", pre) and not self.WISH.search(pre)
                            and not self.d.locally_denied(s, m)):
                        said.append(s)
        self.assertTrue(said, f"{where}: say item 16's component is on D4, as done (\"item 16 joined D4 on <date>\": "
                              "past, not negated, not to be)")
        stale = re.compile(r"(?i)\bitem\s+16\b[^.;]{0,80}\b(joins|will\s+join|waits|to\s+join)\b|"
                           r"\bjoins\s+it\s+after\s+#77\b|\bfree\s+for\s+item\s+16\b|"
                           r"\buntil\s+then\b[^.;]{0,80}\bas\s+#73\s+left\s+it\b|\bgoes\s+on\s+D4\s+once\b")
        for s in self.clauses(part):
            m = stale.search(s)
            self.assertIsNone(m, f"{where}: item 16 is on D4 (ticket #152); drop {m and m.group(0)!r}: {s[:200]!r}")

    @staticmethod
    def code_spans(text):
        """`text` flattened (a fence made one span) and its inline code spans as [(position, content)]."""
        t = re.sub(r"`{3,}[\w-]*", "`", flat(text))
        return t, [(m.start(), m.group(1)) for m in re.finditer(r"`([^`]+)`", t)]

    def test_the_rollout_refresh_put_has_a_body(self):
        path = self.plan_path()
        where = f"{os.path.relpath(path, REPO)}: `## Rollout`"
        raw = self.plan_part(path, "## Rollout", 40)
        steps = [(n, st) for n, st, _c in self.step_clauses(raw, where) if re.search(r"\bPUT\b", st)]
        self.assertTrue(steps, f"{where}: the refresh step names its `PUT` on the dashboard")
        for n, st in steps:
            t, spans = self.code_spans(st)
            ok = [c for pos, c in spans if self.PUT_METHOD.search(c) and self.PUT_BODY.search(c)
                  and not self.d.locally_denied(t, self.at(t, pos))]
            self.assertTrue(ok, f"{where}: step {n}'s PUT carries a body, in the same command: `sf api request rest "
                                f"… --method PUT -b '{{}}'` (sf 2.151 refuses a bodiless PUT: \"No 'mode' found in "
                                f"'body'\")")
        for u in self.units(read(path)):
            t, spans = self.code_spans(u)
            for _pos, c in spans:
                if self.PUT_METHOD.search(c) and not self.PUT_BODY.search(c):
                    self.assertRegex(u, r"(?i)\b(fail\w*|refus\w*|bodiless|without\s+a\s+body|no\s+body)\b",
                                     f"{os.path.relpath(path, REPO)}: every `--method PUT` carries `-b '{{}}'` in "
                                     f"the same command (or is the bodiless form that fails): {u[:200]!r}")

    def test_the_runbook_says_training_is_deployed(self):
        where = f"RUNBOOK section {self.MONTHLY[3:]!r}, {self.PART[4:]!r}"
        part = self.part()
        stale = re.compile(r"(?i)\buntil\s+(it|the\s+build|#78['’]s\s+build|D4)\s+(is|has\s+been)\s+deployed\b|"
                           r"\bholds\s+the\s+vendor['’]s\b|\bnothing\s+(is\s+)?deployed\b|\bundeployed\b|"
                           r"\bstill\s+(runs|holds|shows|has)\b|"
                           r"\b(runs|holds|shows)\s+(the\s+)?(old|vendor['’]s|previous|original)\s+(\w+\s+)?dashboards?\b")
        for s in self.clauses(part):
            m = stale.search(s)
            self.assertIsNone(m, f"{where}: the build is deployed (2026-10-26); drop {m and m.group(0)!r}: {s[:200]!r}")
        said = []
        for s in self.clauses(part):
            if "2026-10-26" not in s:
                continue
            for m in re.finditer(r"(?i)\b(deployed|went\s+live)\b", s):
                pre = re.split(r"[,;(—–]|\bbut\b", s[max(0, m.start() - 50):m.start()])[-1]
                if not self.WISH.search(pre) and not self.d.locally_denied(s, m):
                    said.append(s)
        self.assertTrue(said, f"{where}: say #78's build was deployed on 2026-10-26, as done (\"was deployed on "
                              "2026-10-26\": past, not negated, not scheduled or to be)")


class AttendanceDashboardDocs(unittest.TestCase):
    """Ticket #75: the dashboard "Glow Club Attendance" (D1 in `glow/sf_keep_list.csv`) by Partner and Month. Ryan,
    2026-10-23/24 (#74, #128, #70, on #75): the period is the last 12 months on `DHIS2__c.Period__c`; each report
    groups by the partner (`DHIS2__c.Account__c`), then the month; the dashboard's only filter is Partner Manager
    (`Assigned_Partner_Manager__c`: each manager sees their partners), with no Partner and no Month filter (Ryan,
    2026-10-24 on #75, over the ticket's first wording); the test-record rule `Account is not blank AND
    Account: Account Name does not contain "test"`; item 1 counts `Attendance_submitted_electronically__c`; item 2
    has no source and is retired from D1, its report to Decommissioned; D1 is a dynamic dashboard the API refuses
    to copy (the org is at 5), so its rollback is the metadata retrieve into this change's `before/`, and the
    reports' rollback is their Decommissioned copies.

    The items' measures, labels and ids are read from `glow/sf_keep_list.csv`, not pinned. A component is
    checked in its own unit of the part (a table row, a list item with its sub-items, or a paragraph) that names
    its measure and no other item's: a list of every keyword in one paragraph proves nothing. Its SOQL signal is a
    whole query, as it runs: `FROM DHIS2__c`, one month, the test-record rule; one partner's check likewise. The
    opposite stated beside the rule fails (the month grouped first, a Partner or Month dashboard filter, the Partner Manager one denied, another period,
    item 2 kept on the dashboard, test accounts included, the dashboard restored from anything but this change's
    `before/` or on a fallback, a deploy before the check-only).

    #196 (GLOW's review, Ryan 2026-11-02) changes two of these rules, so this class accepts its new ones and
    GlowReviewAttendanceDocs checks them: the period may be `In_Reporting_Year__c`, D1 has a Month filter beside
    Partner Manager (still no Partner filter), and a rollback may name #196's `data/sf_glow_review_<month>/`."""

    longMessage = False         # the messages say what to fix
    RUNBOOK = os.path.join(REPO, "docs", "RUNBOOK.md")
    KEEP_LIST = os.path.join(REPO, "glow", "sf_keep_list.csv")
    PLANS = os.path.join(REPO, "docs", "plans", "*-sf-dash-attendance.md")
    MONTHLY = "## Monthly Report dashboards in Salesforce"
    PART = "### GLOW Club Attendance"
    GROUP = "GLOW Club Attendance"
    TICKET = re.compile(r"(?<![\w#])#75\b")
    ON_DASHBOARD = ("1", "3", "4")      # item 2 is retired from D1 (Ryan, 2026-10-23 on #74)
    RETIRED = "2"
    # the DHIS2__c field each component counts (#74's check per item; item 4 may read the weeks themselves). Only
    # fields the object has (getObjectSchema, 2026-10-24): `Attendance_submitted_electronically__c` (checkbox),
    # `Monthly_Total__c` ("Monthly Max"), `Week_1__c`-`Week_5__c` ("Week N"), `Week_1_Total__c`-`Week_5_Total__c`
    WEEK = r"Week_[1-5](_Total)?__c"
    FIELD = {"1": r"\bAttendance_submitted_electronically__c\b",
             "3": r"\bMonthly_Total__c\b",
             "4": r"\b(Monthly_Total__c|" + WEEK + r")\b"}
    # its SOQL signal, in the same unit: a SELECT on DHIS2__c whose measure is that field
    SOQL = {"1": r"(?i)\bCOUNT\(\s*Id\s*\).*\bAttendance_submitted_electronically__c\s*=\s*true\b",
            "3": r"(?i)\bSUM\(\s*Monthly_Total__c\s*\)",
            "4": r"(?i)\bSUM\(\s*(Monthly_Total__c|" + WEEK + r")\s*\)"}
    # what every signal carries: one month (the last complete one) and the test-record rule
    MONTH = re.compile(r"(?i)\bPeriod__c\s*=\s*(\d{4}-\d\d-01|LAST_MONTH)\b|\bYearMonth__c\s*=\s*\d{6}\b|"
                       r"\bYear__c\s*=\s*\d{4}\s+AND\s+Month__c\s*=\s*'\w+'")
    NOT_NULL = re.compile(r"(?i)\bAccount__c\s*!=\s*null\b")
    NO_TEST_SOQL = re.compile(r"(?i)\bNOT\s+Account__r\.Name\s+LIKE\s+'%test%'")
    BEFORE_DIR = re.compile(r"\bdata/sf_dash_attendance_\d{4}-\d\d-\d\d/before/")
    # a restore, as the positive checks read it ("the reports are restored from their copies")
    _RESTORE = r"restor\w*|revert\w*|roll\w*\s+back|undo\w*|bring\w*\s+back|put\w*\s+back"
    RESTORE = re.compile(r"(?i)\b(" + _RESTORE + r")\b")
    # a rebuild makes a sentence a rollback sentence ("rebuilt by hand", "re-create it", "redo the dashboard
    # manually"), so the sweeps read it; it never satisfies a positive check (a report rebuilt is not restored)
    _REBUILD = r"rebuil\w*|re-?creat\w*|redo\w*|redone|by\s+hand|manually"
    ROLLBACK_WORD = re.compile(r"(?i)\b(" + _RESTORE + "|" + _REBUILD + r"|rollback)\b")
    # the dashboard as what is restored ("restore the dashboard", "the dashboard is redeployed", "roll D1 back")
    _BACK = (r"(restor\w*|revert\w*|roll\w*\s+back|undo\w*|bring\w*\s+back|brought\s+back|put\w*\s+back|"
             + _REBUILD + r"{deploy})")
    _DASH = r"(dashboard|D1)"
    _DASH_BACK = (r"(?i)\b{b}\s+([\w'’`\"“”-]+\s+){{0,3}}?{d}\b|\b{d}\b[^.;,]{{0,40}}?\b{b}|"
                  r"\broll\w*\s+(the\s+)?{d}\s+back\b")
    DASH_BACK = {False: re.compile(_DASH_BACK.format(b=_BACK.format(deploy=""), d=_DASH)),
                 True: re.compile(_DASH_BACK.format(b=_BACK.format(deploy=r"|(re-?)?deploy\w*"), d=_DASH))}
    # what no item comes back from, the reports included ("rebuilt from screenshots", "re-created from memory",
    # "rebuilt by hand", "a manual rebuild")
    _HANDMADE = r"screen\s*shots?|screen\s*captures?|from\s+memory|by\s+hand|manual(ly)?"
    HANDMADE = re.compile(r"(?i)\b(" + _HANDMADE + r")\b")
    # a source other than this change's `before/` ("the September retrieve", "an older build", another data/ folder,
    # "by hand from screenshots", "from memory"); "undo the moves first then deploy" is an order, not a source
    OTHER_SOURCE = re.compile(r"(?i)\b(January|February|March|April|May|June|July|August|September|October|"
                              r"November|December|older|old|earlier|previous|prior|stale|first(?!,?\s+then\b)|another|"
                              r"other|original|vendor['’]?s?)\s+([\w-]+\s+)?(retrieve|build|backup|export|snapshot|"
                              r"version|copy|deploy(ment)?)\b|\bdata/sf_(?!dash_attendance_|glow_review_)[\w-]+/|"
                              r"\b(" + _HANDMADE + r")\b")
    # a rollback that switches source on a condition ("if before/ is lost", "otherwise", "as a fallback")
    ROLLBACK_SOFT = re.compile(r"(?i)\bif\b[^.;]{0,40}?\b(lost|missing|gone|unavailable|absent|corrupt\w*|deleted|"
                               r"unreadable|not found|cannot be found|broken)\b|"
                               r"\botherwise\b(?![^.;]{0,25}\b(stop|ask|refuse|wait)\w*)|\bfail(ing|s)? that\b|"
                               r"\bfall\s*back\b|\bfallback\b|\balternatively\b|\bor else\b|\bas a last resort\b|"
                               r"\bin a pinch\b|\bif need be\b|\bif necessary\b")
    # test accounts kept in ("test accounts are included", "counts the test records")
    TEST_IN = re.compile(r"(?i)\btest\s+(accounts?|records?)\b(['’]s?)?(\s+[\w'’]+){0,3}?\s+(are|is|stay|stays|remain|"
                         r"remains|get|gets)\s+(still\s+)?(included|counted|shown|kept|in)\b|"
                         r"\b(includ\w*|count(s|ed|ing)?|show(s|n|ing)?|keeps?)\s+([\w'’]+\s+){0,3}?test\s+"
                         r"(accounts?|records?)\b")
    # the test accounts, however named ("test records", `%test%`, "accounts named "Test …"", ""Test …" accounts")
    TEST_TERM = re.compile(r"(?i)\btest\s+(accounts?|records?|partners?|clubs?)\b|%test%|"
                           r"\b(accounts?|partners?|clubs?|records?)\s+(named|called|titled|whose\s+names?\s+"
                           r"(starts?|begins?|contains?)(\s+with)?)\s+[`\"“'‘]*test\b|"
                           r"[`\"“'‘]test\b[^`\"”'’]{0,20}[`\"”'’]+\s+(accounts?|partners?|clubs?)\b")
    # ... and what puts them on the dashboard ("still appear", "stay in", "are counted")
    TEST_SHOWN = re.compile(r"(?i)\b(appear\w*|show(s|n|ed|ing)?|stay(s|ed|ing)?|remain\w*|includ\w*|"
                            r"count(s|ed|ing)?|kept|keeps?|listed|visible)\b")
    # a denial right after the verb ("show none of them", "appear nowhere", "are counted in no component")
    AFTER_DENIED = re.compile(r"(?i)^\s*([\w'’]+\s+){0,2}?(no|none|nowhere|never|not|zero)\b")
    # test accounts out ("a test account's records are absent", "no component includes a test account")
    TEST_OUT = re.compile(r"(?i)\btest\s+(accounts?|records?)\b(['’]s?)?[^.;]{0,40}?\b(absent|excluded|left out|none|"
                          r"zero|0|missing|not\s+(included|counted|shown|there))\b|"
                          r"\b(no|none of the|not one)\s+(\w+\s+){0,3}?(includes?|counts?|shows?)\s+([\w'’]+\s+){0,3}?"
                          r"test\s+(accounts?|records?)\b")
    # a dashboard filter denied ("no filters", "without a Month filter", "not the Partner Manager filter")
    NO_FILTER = re.compile(r"(?i)\b(no|not|never|without|none|nor|neither|n['’]t)\b(?P<what>[^.;]{0,30}?)\bfilter\w*|"
                           r"\bfilters?\b[^.;]{0,20}?\b(removed|dropped|deleted|gone)\b")
    # the partner or the month, not the Partner Manager ("Partner", "Month", `Account__c`, `Period__c`)
    _PM = r"(partners?(?![\s_-]+Manager)|months?|Account__c(?!_)|Period__c(?!_))"
    PM_WHAT = re.compile(r"(?i)\b" + _PM + r"\b")
    # a Partner or Month dashboard filter claimed ("a Partner filter", "a Month (`Period__c`) filter", "a filter on
    # the month", "an `Account__c` filter")
    PM_FILTER = re.compile(r"(?i)\b" + _PM + r"\b`?\s*(\(`?[\w$]+`?\)\s*)?(dashboard\s+)?filters?\b|"
                           r"\bfilter(s|ed|ing)?\s+(on|by|for)\s+(the\s+|a\s+|each\s+)?`?" + _PM + r"\b")
    # a denial that leaves the Partner Manager filter standing ("no filter but Partner Manager", "no filter on the
    # partner or the month")
    BUT_PM = re.compile(r"(?i)^\s*(\w+\s+){0,2}?(other than|but|except|besides|apart from|beyond|save)\b[^.;]{0,30}?"
                        r"\bPartner Manager\b|^\s*(on|by|for)\s+(the\s+|a\s+)?`?" + _PM + r"\b")
    NUMBER = (r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fifteen|eighteen|"
              r"twenty|twenty-four|thirty-six)")
    OTHER_PERIOD = re.compile(r"(?i)\bLAST_N_(?!MONTHS:12\b)\w+:\d+\b|\b(THIS|LAST|NEXT)_(YEAR|QUARTER|FISCAL_\w+)\b|"
                              r"\b(last|past|previous|rolling|trailing)\s+(?!(12|twelve)\b)" + NUMBER +
                              r"\s+(months?|weeks?|years?|days?|quarters?)\b")
    # the grouping's levels, whatever the word order ("the month is the outer grouping", "the inner one is the
    # partner", "`Account__c` nested in `Period__c`"): each level word goes with the nearest partner or month
    LEVEL_SENTENCE = re.compile(r"(?i)\bgroup\w*|\bnest\w*|\blevels?\b")
    LEVEL_TERM = re.compile(r"(?i)(?P<month>Period__c\b|\bmonths?\b)|(?P<partner>Account__c\b|\bpartners?\b(?![\s_-]+"
                            r"Manager))")
    LEVEL_WORD = re.compile(r"(?i)(?P<outer>\b(outer(most)?|first|top(-level)?|primary|highest|leading|parent)\b)|"
                            r"(?P<inner>\b(inner(most)?|nested|second(ary)?|sub-?group\w*|lower|child)\b)")
    GO = re.compile(r"Ryan['’]s go\b")
    EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}")

    @classmethod
    def setUpClass(cls):
        cls.d = DecommissionedFoldersDocs()     # #69's helpers: locally_denied, contradictions, denies
        KeepListDocs.setUpClass()
        cls.k = KeepListDocs()                  # #70's helpers: assertTestRecordRule
        CategoryFoldersDocs.setUpClass()
        cls.c = CategoryFoldersDocs()           # #73's helpers: steps

    @staticmethod
    def norm(text):
        return DecommissionedFoldersDocs.norm(text)

    def keep_rows(self):
        import csv
        with open(self.KEEP_LIST, encoding="utf-8", newline="") as f:
            return {r["item"]: r for r in csv.DictReader(f) if r["group"] == self.GROUP}

    def items(self):
        rows = self.keep_rows()
        reports = {k: v for k, v in rows.items() if v["kind"] == "report"}
        self.assertEqual(sorted(reports), ["1", "2", "3", "4"],
                         f"glow/sf_keep_list.csv: the reports of {self.GROUP!r} are items 1-4 (found {sorted(reports)})")
        dash = [v for v in rows.values() if v["kind"] == "dashboard"]
        self.assertEqual(len(dash), 1, f"glow/sf_keep_list.csv: one dashboard row for {self.GROUP!r}")
        return reports, dash[0]

    def part(self):
        """The `### GLOW Club Attendance` part of the Monthly Report section, to the next `###` or `##`."""
        section = md_part(self.RUNBOOK, self.MONTHLY)
        m = re.search(r"^" + re.escape(self.PART) + r"(?!\w).*$", section, re.M)
        self.assertTrue(m, f"RUNBOOK section {self.MONTHLY[3:]!r}: no `{self.PART}` part under it (ticket #75)")
        rest = section[m.start():]
        nxt = re.search(r"\n#{1,3} ", rest)
        return rest[:nxt.start()] if nxt else rest

    @staticmethod
    def units(part):
        """The part's units, flattened: each table row, each list item with its continuation lines and its deeper
        sub-items, and each blank-line paragraph."""
        lines = part.splitlines()
        out = []
        marker = re.compile(r"(\s*)([-*+]|\d+[.)])\s")
        for i, line in enumerate(lines):
            st = line.strip()
            if st.startswith("|"):
                out.append(flat(st))
                continue
            m = marker.match(line)
            if not m:
                continue
            ind, block = len(m.group(1)), [line]
            for nxt in lines[i + 1:]:
                if not nxt.strip() or nxt.strip().startswith(("|", "#")):
                    break
                m2 = marker.match(nxt)
                if m2 and len(m2.group(1)) <= ind:
                    break
                block.append(nxt)
            out.append(flat("\n".join(block)))
        out += [flat(p) for p in re.split(r"\n\s*\n", part) if p.strip()]
        return out

    def unit_of(self, units, item, reports):
        """The units that name item `item`'s measure and no other item's."""
        own = reports[item]["measure"].lower()
        others = [v["measure"].lower() for k, v in reports.items() if k != item]
        return [u for u in units if own in u.lower() and not any(o in u.lower() for o in others)]

    def said(self, s, rx):
        """`rx` said in clause `s`, not denied in the words before it."""
        return any(not self.d.locally_denied(s, m) for m in re.finditer(rx, s))

    @staticmethod
    def statements(text):
        """The SOQL statements in flattened `text`: each `SELECT` to the next backtick or table bar."""
        return re.findall(r"(?i)\bSELECT\b[^`|]*", text)

    def complete(self, q):
        """A signal one can run as written: on `DHIS2__c`, for one month, with the test-record rule."""
        m = re.search(r"(?i)\bFROM\s+(\w+)", q)
        return bool(m and m.group(1) == "DHIS2__c" and self.MONTH.search(q) and self.NOT_NULL.search(q)
                    and self.NO_TEST_SOQL.search(q))

    def assertTestAccountsOut(self, text, where):
        """No sentence keeps the test accounts in ("test accounts are included"), unless it denies it."""
        for s in sentences(self.norm(text), ".;"):
            for m in self.TEST_IN.finditer(s):
                self.assertTrue(self.d.locally_denied(s, m) or self.d.NEGATION.search(m.group(0)),
                                f"{where}: no component includes a test account's records: {s[:200]!r}")
            # any clause pairing the test accounts with appear/show/stay/included/counted, in either order, denies it
            # (a SOQL statement is code, not a claim: its `NOT ... LIKE '%test%'` is the rule)
            prose = re.sub(r"`[^`]*\bSELECT\b[^`]*`", " ", s)
            for c in re.split(r"[,:|—–(]|\bbut\b|\bwhile\b|\bwhereas\b|\bthough\b", prose):
                if not self.TEST_TERM.search(c):
                    continue
                for v in self.TEST_SHOWN.finditer(c):
                    self.assertTrue(self.d.NEGATION.search(c[:v.start()]) or self.AFTER_DENIED.search(c[v.end():]),
                                    f"{where}: the test accounts' records are on no component; no sentence says they "
                                    f"{v.group(0)!r}: {s[:200]!r}")

    def plan_path(self):
        found = sorted(glob.glob(self.PLANS))
        self.assertEqual(len(found), 1, "docs/plans/: one plan `YYYY-MM-DD-sf-dash-attendance.md` for ticket #75 "
                                        f"(found {[os.path.basename(p) for p in found]})")
        self.assertRegex(os.path.basename(found[0]), r"^\d{4}-\d\d-\d\d-sf-dash-attendance\.md$",
                         "docs/plans/: the plan is named `YYYY-MM-DD-sf-dash-attendance.md`")
        return found[0]

    def plan_part(self, path, heading, least):
        """The body of `heading` in the plan, raw, after checking it says something."""
        name = os.path.relpath(path, REPO)
        part = md_part(path, heading)
        raw = part.split("\n", 1)[1] if "\n" in part else ""
        body = self.norm(raw)
        self.assertNotRegex(body, r"(?i)\b(TBD|TODO|TBA|FIXME)\b", f"{name}: `{heading}` is a placeholder")
        distinct = {w.lower() for w in re.findall(r"[A-Za-z]\w*", body)}
        self.assertGreaterEqual(len(distinct), least, f"{name}: `{heading}` says too little (at least {least} "
                                                      "distinct words)")
        return raw

    def assertRollback(self, raw, where, whole=True):
        """The rollback: the reports from their Decommissioned copies; the dashboard (no API copy: it is dynamic)
        from this change's `before/` retrieve, only while a fresh retrieve equals `after/`; never an older build.
        `whole`: `raw` is all rollback (the plan's section), so no deploy in it names `build/`; otherwise only its
        rollback sentences are held to that."""
        cl = sentences(self.norm(raw), ".;")
        self.assertTrue([s for s in cl if self.said(s, self.RESTORE) and re.search(r"(?i)\breports?\b", s)
                         and re.search(r"(?i)\bcop(y|ies)\b", s) and "Decommissioned" in s],
                        f"{where}: say the reports are restored from their copies in Decommissioned (one sentence, not "
                        "negated)")
        self.assertRegex(flat(raw), self.BEFORE_DIR,
                         f"{where}: name this change's retrieve `data/sf_dash_attendance_<date>/before/`")
        self.assertTrue([s for s in cl if re.search(r"(?i)\bdashboard\b", s) and "before/" in s
                         and (self.said(s, self.RESTORE) or self.said(s, r"(?i)\b(re-?)?deploy\w*\b"))],
                        f"{where}: say the dashboard is restored by deploying the `before/` retrieve (one sentence, not "
                        "negated)")
        self.assertTrue([s for s in cl if re.search(r"(?i)\bdashboard\b", s) and re.search(r"(?i)\bdynamic\b", s)
                         and re.search(r"(?i)\brefus\w*\b|\bno\s+(API\s+)?cop(y|ies)\b|\bnot\s+(be\s+)?copied\b", s)],
                        f"{where}: say why the dashboard has no Decommissioned copy: it is dynamic and the API refuses "
                        "to copy it (the org is at 5 dynamic dashboards), in one sentence")
        equal = re.compile(r"(?i)\b(equals?|matches|match|is the same as|identical to|unchanged from|"
                           r"no differences? (from|with))\b")
        self.assertTrue([s for s in cl if "before/" in s and "after/" in s
                         and re.search(r"(?i)\b(fresh|new|current|live)\b[^.;]{0,20}?\bretriev\w*", s)
                         and re.search(r"(?i)\b(only|while|as long as|provided|so long as)\b", s)
                         and self.said(s, equal)],
                        f"{where}: say `before/` is restored only while a fresh retrieve equals `after/` (nothing "
                        "changed the dashboard since), in one sentence")
        self.assertTrue([s for s in cl if re.search(r"(?i)\b(never|not|no)\b[^.;]{0,60}?\b(older|old|earlier|previous|"
                                                    r"stale)\s+(\w+\s+)?(build|retrieve)\b", s)],
                        f"{where}: say never from an older build or retrieve (DECISIONS 2026-10-16), in one sentence")
        for s in cl:            # `build/` is never what a rollback deploys
            if "build/" in s and (self.ROLLBACK_WORD.search(s) or (whole and re.search(r"(?i)\bdeploy", s))):
                self.assertTrue(self.d.NEGATION.search(s), f"{where}: a rollback never deploys `build/`: {s[:200]!r}")
        # every sentence that brings the dashboard back brings back this change's `before/`, and nothing else
        for s in cl:
            for m in self.DASH_BACK[whole].finditer(s):
                if self.d.locally_denied(s, m) or self.d.NEGATION.search(m.group(0)):
                    continue
                self.assertIn("before/", s, f"{where}: the dashboard comes back only from this change's `before/` "
                                            f"(name it, or deny the sentence): {s[:200]!r}")
                other = [o.group(0) for o in self.OTHER_SOURCE.finditer(s) if not self.d.locally_denied(s, o)]
                self.assertEqual(other, [], f"{where}: the dashboard comes back from this change's `before/` only, "
                                            f"never from another source: {s[:200]!r}")
        # and no condition switches the source ("if before/ is lost, ...", "otherwise", "as a fallback")
        back = cl if whole else [s for s in cl if self.ROLLBACK_WORD.search(s)]
        for s in back:
            for m in self.ROLLBACK_SOFT.finditer(s):
                self.assertTrue(self.d.locally_denied(s, m),
                                f"{where}: the rollback has one source per item, with no fallback "
                                f"({m.group(0)!r}): {s[:200]!r}")
            # nothing comes back from screenshots, memory or by hand: the reports from their copies, D1 from `before/`
            for m in self.HANDMADE.finditer(s):
                self.assertTrue(self.d.locally_denied(s, m) or self.d.NEGATION.search(m.group(0)),
                                f"{where}: the rollback restores from the copies and `before/` only, never from "
                                f"{m.group(0)!r}: {s[:200]!r}")

    UNDO_CMD = re.compile(r"\bsf_report_folders[._]py\s+undo\b")
    # a check-only or deploy ("a check-only of `before/`", "deploy `before/`", "redeployed")
    DEPLOY_WORD = re.compile(r"(?i)\bcheck-only\b|--dry-run\b|\b(re-?)?deploy\w*")
    # ... said as what is still to come ("undo the moves before `before/` is deployed"); "before/" is the folder,
    # not the word (review of PR #143: "First `before/` is deployed" is no deploy still to come)
    LATER = re.compile(r"(?i)\b(before\b(?!/)|(until|ahead of|prior to)\b)[^.;,]{0,25}$")
    # ... or as what fails ("a check-only of `before/` is refused")
    REFUSED = re.compile(r"(?i)^[^.;,]{0,40}?\b((is|are|was|were|gets?|would be)\s+(refused|rejected|denied)|fails?)\b")

    def rollback_text(self):
        """The RUNBOOK part's rollback: from its `Rollback` line to the end of the part."""
        part = self.part()
        m = re.search(r"(?im)^\W*rollback\b", part)
        self.assertTrue(m, f"RUNBOOK {self.PART!r}: no `Rollback` paragraph")
        return part[m.start():]

    def assertUndoFirst(self, raw, where):
        """Step 7's moves are undone (`sf_report_folders.py undo`) before `before/` is checked or deployed: the
        dashboard in `before/` names its reports at the paths the moves changed. Ahead of the undo, no sentence
        brings the dashboard back from `before/` and no clause check-onlies or deploys `before/`; after it, the
        dashboard is restored from `before/`."""
        text = self.norm(raw)
        # the undo is the first one run, not one denied ("do not run `... undo` yet"; review of PR #143)
        undo, at = None, 0
        for s in sentences(text, ".;"):
            at = text.find(s, at)
            m = next((m for m in self.UNDO_CMD.finditer(s) if not self.d.locally_denied(s, m)), None)
            if m:
                undo = self.UNDO_CMD.search(text, at + m.start())
                break
        self.assertTrue(undo, f"{where}: undo step 7's moves, `python3 tools/sf_report_folders.py undo --vpn-off "
                              "--dir data/sf_dash_attendance_<date>`, before `before/` is deployed")
        early, restored, at = [], [], 0
        for s in sentences(text, ".;"):
            at = text.find(s, at)
            if "before/" not in s:
                continue
            for m in self.DASH_BACK[True].finditer(s):
                if not (self.d.locally_denied(s, m) or self.d.NEGATION.search(m.group(0))) \
                        and at + m.start() < undo.start():
                    early.append(s)
            for c in re.finditer(r"[^,:()]+", s):
                clause = c.group(0)
                if "before/" not in clause:
                    continue
                for m in self.DEPLOY_WORD.finditer(clause):
                    if self.d.locally_denied(clause, m) or self.LATER.search(clause[:m.start()]) \
                            or self.REFUSED.search(clause[m.end():]):
                        continue
                    if at + c.start() + m.start() < undo.start():
                        early.append(s)
            if at > undo.start() and re.search(r"(?i)\bdashboard\b", s) \
                    and (self.said(s, self.RESTORE) or self.said(s, r"(?i)\b(re-?)?deploy\w*\b")):
                restored.append(s)
        self.assertEqual(early, [], f"{where}: step 7's moves are undone (`sf_report_folders.py undo`) before "
                                    "`before/` is checked or deployed, and before the dashboard is restored from it: "
                                    + "; ".join(repr(s[:160]) for s in early))
        self.assertTrue(restored, f"{where}: after the undo, say the dashboard is restored by deploying `before/` "
                                  "(one sentence)")

    # --- the RUNBOOK ----------------------------------------------------------------------------------------

    def test_the_runbook_describes_attendance_by_partner_and_month(self):
        where = f"RUNBOOK section {self.MONTHLY[3:]!r}, {self.PART[4:]!r}"
        reports, dash = self.items()
        part = self.part()
        text = self.norm(part)
        cl = sentences(text, ".;")
        units = self.units(part)
        self.assertIn(dash["id"], part, f"{where}: name the dashboard {dash['label_today']!r} by its Id {dash['id']}")
        # each component in its own unit: its measure (GLOW's wording), its report, the field, the SOQL signal
        for item in self.ON_DASHBOARD:
            r = reports[item]
            at = f"{where}, item {item} ({r['measure']!r})"
            mine = self.unit_of(units, item, reports)
            self.assertTrue(mine, f"{at}: name the measure in GLOW's wording, in a row, list item or paragraph of its "
                                  "own (no other item's measure in it)")
            mine = [u for u in mine if r["label_today"] in u]
            self.assertTrue(mine, f"{at}: name its report {r['label_today']!r} beside the measure")
            mine = [u for u in mine if re.search(self.FIELD[item], u)]
            self.assertTrue(mine, f"{at}: name the `DHIS2__c` field it counts ({self.FIELD[item]}) beside the measure")
            for q in [q for u in self.unit_of(units, item, reports) for q in self.statements(u)]:
                m = re.search(r"(?i)\bFROM\s+(\w+)", q)
                self.assertTrue(m and m.group(1) == "DHIS2__c",
                                f"{at}: its SOQL signal reads `DHIS2__c` (`... FROM DHIS2__c WHERE ...`): {q[:200]!r}")
            self.assertTrue([q for u in mine for q in self.statements(u) if re.search(self.SOQL[item], q)
                             and self.complete(q)],
                            f"{at}: give its SOQL signal beside it, in backticks, as it runs: a `SELECT` with "
                            f"{self.SOQL[item]} `FROM DHIS2__c WHERE` one month (`Period__c = 2026-09-01`) `AND "
                            "Account__c != null AND (NOT Account__r.Name LIKE '%test%')`")
        # item 2: named, retired from the dashboard, its report to Decommissioned; not a component any more
        r = reports[self.RETIRED]
        at = f"{where}, item {self.RETIRED} ({r['measure']!r})"
        theirs = self.unit_of(units, self.RETIRED, reports)
        retired = [u for u in theirs
                   if (r["label_today"] in u or r["id"] in u)
                   and [s for s in sentences(self.norm(u), ".;") if self.said(s, r"(?i)\bretir\w*") and
                        "Decommissioned" in s]]
        self.assertTrue(retired, f"{at}: name it with its report ({r['label_today']!r} or {r['id']}) and say it is "
                                 "retired from the dashboard, its report to Decommissioned (Ryan, 2026-10-23), in a "
                                 "row, list item or paragraph of its own")
        stays = re.compile(r"(?i)\b(stays?|remains?|kept|keeps?|still|left)\b[^.;]{0,40}?\b(on|in)\s+(the\s+)?"
                           r"(dashboard|D1)\b|\b(stays?|remains?|still|is)\s+(\w+\s+)?(a\s+|the\s+)?component\b|"
                           r"\bas\s+(a\s+|its\s+)?component\b")
        for u in theirs:
            for s in sentences(self.norm(u), ".;"):
                for m in stays.finditer(s):
                    self.assertTrue(self.d.locally_denied(s, m) or self.d.NEGATION.search(m.group(0)),
                                    f"{at}: it is retired, off the dashboard, not kept on it: {s[:200]!r}")
            self.assertEqual(self.statements(u), [], f"{at}: it is retired, so it has no SOQL signal (no `SELECT`)")
        # the decided rules: the period (the last 12 months on `Period__c`; since #196 `In_Reporting_Year__c`, which
        # GlowReviewAttendanceDocs checks)
        self.assertTrue([s for s in cl if ("Period__c" in s and self.said(s, r"(?i)\bLAST_N_MONTHS:12\b|"
                                                                             r"\blast 12 months\b"))
                         or self.said(s, r"\bIn_Reporting_Year__c\b")],
                        f"{where}: the period is the last 12 months on `Period__c`, or since #196 `In_Reporting_Year__c` "
                        "(one sentence, not negated)")
        for s in cl:
            if not re.search(r"(?i)Period__c|\bperiod\b|\bdate filter\b|LAST_N_", s):
                continue
            for m in self.OTHER_PERIOD.finditer(s):
                self.assertTrue(self.d.locally_denied(s, m),
                                f"{where}: the period is the last 12 months (`LAST_N_MONTHS:12`), not "
                                f"{m.group(0)!r}: {s[:200]!r}")
        # the grouping: the partner, then the month, and never the other way round
        grouped = [s for s in cl if self.said(s, r"(?i)\bgroup\w*") and re.search(r"Account__c\b", s)
                   and re.search(r"Period__c\b", s)
                   and re.search(r"Account__c\b", s).start() < re.search(r"Period__c\b", s).start()]
        self.assertTrue(grouped, f"{where}: every report groups by the partner (`Account__c`), then the month "
                                 "(`Period__c`), in that order in one sentence")
        for s in cl:
            for m in re.finditer(r"(?i)\bgroup\w*", s):
                if self.d.locally_denied(s, m):
                    continue
                rest = s[m.end():]
                a, p = re.search(r"Account__c\b", rest), re.search(r"Period__c\b", rest)
                self.assertFalse(a and p and p.start() < a.start(),
                                 f"{where}: the grouping is the partner (`Account__c`) first, then the month "
                                 f"(`Period__c`), never the month first: {s[:200]!r}")
        for s in cl:            # the month never the outer level, the partner never the inner one
            if not self.LEVEL_SENTENCE.search(s):
                continue
            terms = list(self.LEVEL_TERM.finditer(s))
            for w in self.LEVEL_WORD.finditer(s):
                near = sorted((w.start() - t.end() if t.end() <= w.start() else max(0, t.start() - w.end()), t.start(), t)
                              for t in terms)
                if not near or near[0][0] > 45:
                    continue
                t = near[0][2]
                wrong = (t.lastgroup == "month" and w.lastgroup == "outer") or \
                        (t.lastgroup == "partner" and w.lastgroup == "inner")
                if not wrong:
                    continue
                first, last = (t, w) if t.start() < w.start() else (w, t)
                denied = self.d.locally_denied(s, first) or self.d.NEGATION.search(s[first.end():last.start()])
                self.assertTrue(denied, f"{where}: the partner (`Account__c`) is the outer grouping and the month "
                                        f"(`Period__c`) the inner one, never the other way round ({t.group(0)!r} "
                                        f"{w.group(0)!r}): {s[:200]!r}")
        for s in cl:
            if "CreatedDate" in s:
                m = re.search(r"CreatedDate", s)
                self.assertTrue(self.d.locally_denied(s, m) or re.search(
                    r"(?i)\b(in place of|instead of|replac\w*|rather than)\b[^.;]{0,30}$", s[:m.start()]),
                    f"{where}: `CreatedDate` is never the period or a grouping (only what `Period__c` replaces): "
                    f"{s[:200]!r}")
        # the dashboard's filters (Ryan, 2026-10-24 on #75): Partner Manager, no Partner filter; a Month filter since
        # #196 (GLOW's review, Ryan 2026-11-02: GlowReviewAttendanceDocs checks it)
        dashboard_filter = [s for s in cl if re.search(r"(?i)\bdashboard\b", s) and re.search(r"(?i)\bfilters?\b", s)]
        pm = r"(?i)\bfilter\w*[^.;]{0,40}?\bPartner Manager\b|\bPartner Manager\b[^.;]{0,20}?\bfilter\w*"
        self.assertTrue([s for s in dashboard_filter if self.said(s, pm) and "Assigned_Partner_Manager__c" in s],
                        f"{where}: the dashboard filters on Partner Manager, `Assigned_Partner_Manager__c` (one "
                        "sentence naming the dashboard's filter and the field, not negated; Ryan, 2026-10-24 on #75)")
        no = r"(?i)\b(no|not|without|neither|nor|never)\b[^.;]{0,25}?\bPartner\b(?!\s+Manager)[^.;]{0,20}?\bfilters?\b"
        self.assertTrue([s for s in dashboard_filter if re.search(no, s)],
                        f"{where}: say the dashboard has no Partner filter (one sentence naming the dashboard; Ryan, "
                        "2026-10-24 on #75)")
        for s in dashboard_filter:      # no Partner dashboard filter claimed (a Month filter is #196's)
            for m in self.PM_FILTER.finditer(s):
                if re.search(r"(?i)\bmonths?\b|Period__c|Month__c", m.group(0)):
                    continue
                self.assertTrue(self.d.locally_denied(s, m) or self.d.NEGATION.search(m.group(0)),
                                f"{where}: the dashboard has no Partner filter ({m.group(0)!r}): {s[:200]!r}")
        for s in dashboard_filter:      # and its Partner Manager filter, or every filter, is never denied
            for m in self.NO_FILTER.finditer(s):
                what = m.group("what")
                if what is not None and self.PM_WHAT.search(what) and not re.search(r"(?i)\bManager\b", what):
                    continue            # "no Partner filter", "no Month filter"
                if what is not None and not what.strip() and self.BUT_PM.search(s[m.end():]):
                    continue            # "no filter but Partner Manager", "no filter on the month"
                self.fail(f"{where}: the dashboard keeps its one filter, Partner Manager; no sentence denies it or "
                          f"all filters ({m.group(0)!r}): {s[:200]!r}")
        self.k.assertTestRecordRule(text, where)
        self.assertTestAccountsOut(part, where)
        # one partner's month: a whole query, on DHIS2__c, one month, the test records out, that partner
        self.assertTrue([q for q in self.statements(flat(part)) if self.complete(q)
                         and re.search(r"(?i)\b(COUNT|SUM)\(", q) and re.search(r"(?i)\bAccount__r\.Name\s*=\s*'[^']+'", q)],
                        f"{where}: give the SOQL check of one partner's month as it runs, in backticks: `SELECT ... FROM "
                        "DHIS2__c WHERE Period__c = <month> AND Account__c != null AND (NOT Account__r.Name LIKE "
                        "'%test%') AND Account__r.Name = '<partner>'`")
        self.assertNotRegex(part, self.EMAIL, f"{where}: counts, ids and names of reports and partners only, no address")
        self.d.assertNoContradiction(part, where)

    def test_the_attendance_rollback_names_the_copies_and_the_before_folder(self):
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        where = f"{name}: `## Rollback`"
        raw = self.plan_part(path, "## Rollback", 15)
        self.assertRollback(raw, where)
        found = self.d.contradictions(raw, rollback=True)
        self.assertEqual(found, [], f"{where}: contradicts the rules (nothing deleted, the copies and the retrieve are "
                                    "the rollback, never optional): " + "; ".join(found))
        # the RUNBOOK's part says the same rollback
        self.assertRollback(self.part(), f"RUNBOOK section {self.MONTHLY[3:]!r}, {self.PART[4:]!r}", whole=False)

    def test_the_attendance_rollback_undoes_the_moves_before_the_deploy(self):
        """Review of PR #143: `before/` names reports at their paths before step 7's moves, so its check-only is
        refused until the moves are undone; the undo comes first, in the plan and in the RUNBOOK."""
        path = self.plan_path()
        self.assertUndoFirst(self.plan_part(path, "## Rollback", 15), f"{os.path.relpath(path, REPO)}: `## Rollback`")
        self.assertUndoFirst(self.rollback_text(), f"RUNBOOK {self.PART!r}, its Rollback")

    def test_the_undo_first_check_rejects_a_deploy_ahead_of_the_undo(self):
        """Review of PR #143 (on b8d56e7): the folder name `before/` is not the word "before", and a denied undo
        ("do not run ... undo yet") is not where the undo runs. A correct order still passes."""
        undo = "`python3 tools/sf_report_folders.py undo --vpn-off --dir data/sf_dash_attendance_<date>`"
        wrong = {
            "the folder read as 'before'": f"First `before/` is deployed. Then the moves are undone with {undo}. "
                                           "After that the dashboard is restored by deploying `before/`.",
            "a denied undo, never run": f"Do not run {undo} yet; deploy `before/` now. Then run the undo; "
                                        "the dashboard is restored by deploying `before/`.",
            "a denied undo, run later": f"Do not run {undo} yet; deploy `before/` now. Then run {undo}; "
                                        "the dashboard is restored by deploying `before/`.",
        }
        for name, probe in wrong.items():
            with self.subTest(name), \
                    self.assertRaises(AssertionError, msg=f"assertUndoFirst accepts {name}: {probe!r}"):
                self.assertUndoFirst(probe, name)
        right = {
            "undo, check-only, deploy": f"First the moves are undone with {undo}. Then a check-only of `before/`, "
                                        "then deploy `before/`; the dashboard is restored by deploying `before/`.",
            "undo said ahead of the deploy": f"Undo the moves before `before/` is deployed: {undo}. Then a check-only "
                                             "of `before/` passes and the dashboard is restored by deploying `before/`.",
            "a denial in the sentence before": f"The moves are not reverted by the deploy. Run {undo}; then the "
                                               "dashboard is restored by deploying `before/`.",
        }
        for name, probe in right.items():
            with self.subTest(name):
                self.assertUndoFirst(probe, name)

    # --- the plan ---------------------------------------------------------------------------------------------

    def test_a_plan_carries_the_attendance_deploy(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        reports, dash = self.items()
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        text = read(path)
        keys, _ = docs_index.frontmatter(text)
        self.assertIn("status", keys, f"{name}: frontmatter `status:`")
        word, problem = docs_index.status_of(keys["status"])
        self.assertIsNone(problem, f"{name}: {problem}")
        self.assertNotEqual(word, "superseded", f"{name}: the plan is the change in force")
        if word == "done":
            self.assertRegex(keys.get("done", ""), r"^\d{4}-\d\d-\d\d", f"{name}: a done plan carries `done:`")
        self.assertRegex(text.split("\n## ", 1)[0], self.TICKET,
                         f"{name}: name ticket #75 in the frontmatter, the title or the opening paragraph")
        self.assertRegex(text, r"(?m)^## Result\b", f"{name}: no `## Result` section")
        self.assertNotRegex(text, self.EMAIL, f"{name}: counts, ids and names of reports and partners only, no address")

        raw = self.plan_part(path, "## Rollout", 40)
        where = f"{name}: `## Rollout`"
        cl = sentences(self.norm(raw), ".;")
        for item, r in sorted(reports.items()):
            self.assertIn(r["id"], raw, f"{where}: name item {item}'s report {r['label_today']!r} by its Id {r['id']}")
        self.assertIn(dash["id"], raw, f"{where}: name the dashboard {dash['label_today']!r} by its Id {dash['id']}")
        # the copies: by the tool, VPN off, tagged with the ticket, on Ryan's go
        segments = re.split(r"`+|\n\s*\n|\n(?=\s*(?:\$\s*)?python3\s)|(?=\bpython3\s)", raw)
        copies = [flat(s) for s in segments if re.search(r"\bpython3\s+(\S*/)?sf_report_folders\.py\s+copy\b", s)]
        self.assertTrue(copies, f"{where}: give the copies' command, `python3 tools/sf_report_folders.py copy --vpn-off "
                                "--kind report --id <id> --tag \"#75\"`")
        for c in copies:
            self.assertIn("--vpn-off", c, f"{where}: the tool refuses to run without `--vpn-off`: {c[:160]!r}")
            self.assertRegex(c, r"--tag[ =]\\?[\"“']?#75\b", f"{where}: each copy carries the ticket, `--tag \"#75\"`: "
                                                            f"{c[:160]!r}")
        for item, r in sorted(reports.items()):     # one copy per report, each by its own Id
            self.assertTrue([c for c in copies if re.search(r"--id[ =]" + re.escape(r["id"]) + r"\b", c)
                             and re.search(r"--kind[ =]report\b", c)],
                            f"{where}: item {item}'s report {r['label_today']!r} gets its own copy command, "
                            f"`... copy --vpn-off --kind report --id {r['id']} --tag \"#75\"`")
        self.assertTrue([s for s in cl if re.search(r"(?i)\bdashboard\b", s) and re.search(r"(?i)\bdynamic\b", s)
                         and re.search(r"(?i)\brefus\w*\b|\bno\s+(API\s+)?cop(y|ies)\b|\bnot\s+(be\s+)?copied\b", s)],
                        f"{where}: say the dashboard gets no Decommissioned copy because it is dynamic and the API "
                        "refuses to copy it (the org is at 5), so `before/` is its rollback (one sentence)")
        self.assertTrue([s for s in cl if self.GO.search(s) and re.search(r"(?i)\bcop(y|ies)\b|--apply", s)
                         and not self.d.denies(s)],
                        f"{where}: the copies' `--apply` waits for Ryan's go (one sentence)")
        self.assertTrue([s for s in cl if self.GO.search(s) and re.search(r"(?i)\bdeploy", s) and not self.d.denies(s)],
                        f"{where}: the deploy waits for Ryan's go (one sentence)")
        self.assertTrue([s for s in cl if "after/" in s and "build/" in s
                         and re.search(r"(?i)\b(compar\w*|equals?|differ\w*|diff)\b", s)],
                        f"{where}: the read-back retrieves into `after/` and compares it with `build/` (one sentence)")
        self.assertTrue([s for s in cl if re.search(r"\bSOQL\b|\bSELECT\b", s) and re.search(r"(?i)\bcomponents?\b", s)
                         and re.search(r"(?i)\bpartner\b", s) and re.search(r"(?i)\bmonth\b", s)],
                        f"{where}: check each component, and one partner's month, against SOQL on `DHIS2__c` (one "
                        "sentence)")
        self.assertTrue([s for s in cl if [m for m in self.TEST_OUT.finditer(s) if not self.d.locally_denied(s, m)]],
                        f"{where}: check that no component includes a test account's records (\"a test account's "
                        "records are absent from every component\", one sentence)")
        self.assertTestAccountsOut(raw, where)
        r = reports[self.RETIRED]
        # the order, in the numbered steps: before/, copies, check-only, deploy, after/, SOQL; item 2 moves after
        steps = self.c.steps(raw, where)
        before = self.c.first(self.BEFORE_DIR, steps, where, "the steps start from a fresh retrieve into "
                              "`data/sf_dash_attendance_<date>/before/`")
        copy_at = [m.start() for m in re.finditer(r"\bsf_report_folders\.py\s+copy\b", steps)]
        self.assertTrue(copy_at, f"{where}: the copies are a numbered step")
        self.assertLess(before, copy_at[0], f"{where}: the `before/` retrieve comes before the copies")
        check_only = [m.start() for m in re.finditer(r"(?i)\bcheck-only\b|--dry-run\b", steps) if m.start() > copy_at[-1]]
        self.assertTrue(check_only, f"{where}: the check-only deploy comes after every copy (copy first, then change)")
        # every deploy (the check-only aside) comes after the check-only, and so after the `before/` retrieve:
        # "Deploy build/ first" in step 1 is no plan; "before anything is deployed" is no deploy
        deploys, at = [], 0
        for piece in sentences(steps, ".;,"):
            at = steps.find(piece, at)
            m = re.search(r"(?i)\b(re-?)?deploy\w*", piece)
            if not m or re.search(r"(?i)check-only|--dry-run|\bvalidat", piece) or self.d.locally_denied(piece, m) \
                    or re.search(r"(?i)\b(before|until|ahead of|prior to|after|once)\b[^.;,]{0,25}$", piece[:m.start()]) \
                    or re.search(r"(?i)\b(in|at|from)\s+step\s+\d", piece):
                continue
            self.assertGreater(at, check_only[0], f"{where}: nothing is deployed before the check-only (and the "
                                                  f"`before/` retrieve and the copies): {piece[:160]!r}")
            deploys.append(at)
        self.assertTrue(deploys, f"{where}: the deploy is a step after the check-only (on Ryan's go)")
        after = [m.start() for m in re.finditer(r"\bafter/", steps) if m.start() > deploys[0]]
        self.assertTrue(after, f"{where}: the `after/` read-back comes after the deploy")
        self.assertTrue([m for m in re.finditer(r"\bSOQL\b|\bSELECT\b", steps) if m.start() > after[0]],
                        f"{where}: the SOQL check comes after the `after/` read-back")
        moved = [steps.index(s) for s in sentences(steps, ".;") if (r["id"] in s or r["label_today"] in s)
                 and "Decommissioned" in s and self.said(s, r"(?i)\bmov\w*")]
        self.assertTrue([p for p in moved if p > deploys[0]],
                        f"{where}: item {self.RETIRED}'s report ({r['id']}) is moved to Decommissioned after the deploy, "
                        "once the dashboard no longer uses it (one sentence naming it, `move` and Decommissioned)")
        self.d.assertNoContradiction(raw, where)


class NewMentorsDocs(unittest.TestCase):
    """Ticket #80: keep-list item 12, "New mentors recruited", on the dashboard GLOW Club Training (`D4`).

    The agreed definition (Ryan, 2026-10-26, on the ticket: option A): the report "Partners that recruited new
    mentors" counts the Monthly Reports (`DHIS2__c`) answering Yes and No to
    `Recruit_any_new_mentors_last_month__c` ("Did you recruit any new mentors last month?"), by partner
    (`Account__c`) and month (`Period__c`, the month the report covers), blank answers left out, with the
    test-record rule (#70) and the last 12 months (`Period__c = LAST_N_MONTHS:12`, #128), like items 15 and 16.
    Each Yes is one partner's month, not a number of mentors. Rejected: `Newly_recruited__c` (recruits still
    needing orientation, not recruits), the contacts with a "Lead Mentor" role, and a separate dashboard (a
    component on D4 is enough). These facts are pinned here from the ticket, not read from the docs under test;
    D4's id comes from `glow/sf_keep_list.csv`.

    The live deploy runs later, in an interactive session: the report's id does not exist yet, so item 12's id
    in `glow/sf_keep_list.csv` (test/sf_keep_list_test.py) is not tested here, and the plan's `## Result` may
    say the deploy is pending. The helpers are #78's (`TrainingDashboardDocs`) and #69's; counts and ids only.

    Round 2 (the test-breaker passed with wrong claims beside the right ones): a wrong claim fails wherever it
    stands, in item 12's RUNBOOK units, the whole plan (its `## Result` included) and the whole decision but its
    Rejected bullet: a mentor headcount (a quantity word beside "mentor(s)", not denied: "how many new mentors
    each partner recruited", "adds up the Yes answers as the new mentors", "a mentor headcount"), a month from
    any date field but `Period__c` (standard, or a custom one like `Submitted_On__c`), `Newly_recruited__c` or a
    "Lead Mentor" contact as the source. The plan's six-month query has a period on `Period__c` and runs month by
    month; Rejected gives each source's reason; Consequences says the figure counts partners. The "No" of a
    Yes/No answer is masked before a denial is looked for.

    Round 3: "recruits" count as mentors; a person per partner ("the recruits each partner signed up") or per
    answer ("one new mentor brought in") fails, and a clause saying what a Yes stands for beside a mentor says one
    partner's month; a dashboard of its own or "in place of D4" fails outside Rejected; a window other than 12
    months fails in item 12's units and the decision; each Rejected reason is the agreed one ("still need
    orientation", household accounts with no partner link, D4 enough) and nothing turns it around."""

    longMessage = False         # the messages say what to fix
    DECISIONS = os.path.join(REPO, "docs", "DECISIONS.md")
    PLANS = os.path.join(REPO, "docs", "plans", "*-sf-new-mentors.md")
    TICKET = re.compile(r"(?<![\w#])#80\b")
    ITEM = "12"
    LABEL = "Partners that recruited new mentors"           # the report's label (Ryan, 2026-10-26)
    FIELD = "Recruit_any_new_mentors_last_month__c"         # Yes/No, one answer per partner per month
    NEWLY = "Newly_recruited__c"                            # rejected: recruits still needing orientation
    OTHER_FIELDS = TrainingDashboardDocs.FIELDS             # items 13-16 (#74)
    WORK_DIR = re.compile(r"data/sf_new_mentors_\d{4}-\d\d-\d\d/")
    BEFORE = re.compile(r"data/sf_new_mentors_\d{4}-\d\d-\d\d/before/")
    LAST_12_Q = re.compile(r"(?i)\bPeriod__c\s*=\s*LAST_N_MONTHS:12\b")
    ANSWER_NOT_NULL = re.compile(r"(?i)\bRecruit_any_new_mentors_last_month__c\s*(!=|<>)\s*null\b")
    COUNT = re.compile(r"(?i)\bCOUNT\(\s*(Id)?\s*\)")
    OR = re.compile(r"(?i)\bOR\b")
    PARTNER_Q = re.compile(r"(?i)\bAccount__r\.Name\s*=\s*'|\bAccount__c\s*=\s*'")
    YES_AND_NO = re.compile(r"\bYes\b\s*(,|and|or|/|&)\s*\bNo\b|\bNo\b\s*(,|and|or|/|&)\s*\bYes\b")
    YES = re.compile(r"\bYes\b")
    # "each Yes is one partner's month", "a partner's month", "counts partners"
    PARTNER_MONTH = re.compile(r"(?i)\b(one\s+|a\s+)?partner['’]s\s+month\b")
    # "not a number of mentors", "never a count of new mentors": that denial is the rule itself
    NOT_HEADCOUNT = re.compile(r"(?i)\b(not|never|no)\s+(a\s+|the\s+)?(number|count|head\s*count|total|tally)\s+of\s+"
                               r"(new\s+|recruited\s+)?mentors\b")
    BLANK_OUT = re.compile(r"(?i)\bblank\b[^.;]{0,40}?\b(left out|excluded|not counted|never counted|dropped)\b|"
                           r"\bleav\w*\s+out\s+(\w+\s+){0,2}?blank\b|\bexclud\w*\s+(\w+\s+){0,2}?blank\b")
    EACH_PARTNER_MONTH = re.compile(r"(?i)\b(each|every|per|by)\s+(the\s+)?partner\b[^.;]{0,40}?\bmonths?\b")
    LEAD_MENTOR = re.compile(r"(?i)\bLead Mentor\b")
    SEPARATE_DASHBOARD = re.compile(r"(?i)\b(separate|sixth|own|new|second|standalone|stand-alone|extra|"
                                    r"dedicated)\s+(\w+\s+)?dashboard\b")
    NEW_REPORT = re.compile(r"(?i)\bnew report\b|\bitem 12['’]s report\b|\bthe report of item 12\b|"
                            + re.escape(LABEL))
    MOVE = re.compile(r"(?i)\bmov(e|es|ed|ing)\b")
    NOTHING_DELETED = re.compile(r"(?i)\b(nothing|never|no\s+\w+)\b[^.;]{0,40}?\bdelet\w*")
    REJECT = KeepListDocs.REJECT
    TEST_RECORD = re.compile(r"(?i)\btest[- ]record rule\b")
    SIX_MONTHS = re.compile(r"(?i)\b(six|6)\s+(last\s+)?complete\s+months?\b|\blast\s+(six|6)\s+complete\s+months?\b|"
                            r"\b(six|6)\s+months?\b[^.;]{0,20}?\bcomplete\b")
    ONE_PARTNER = re.compile(r"(?i)\b(one|a single)\s+partner\b")
    # another ticket's build, retrieve or folder (#78's OTHER_CHANGE, for this change)
    OTHER_CHANGE = re.compile(r"#(?!80\b)\d+['’]s\s+(\w+\s+)?`?(build|retrieve|before/|after/|build/|copy|copies|backup)|"
                              r"\b(build|retrieve|before/|after/|build/)`?\s+(of|from)\s+(ticket\s+)?#(?!80\b)\d+|"
                              r"\bdata/sf_(?!new_mentors_)[\w.-]+/(build|before|after)/")
    # round 2 (the test-breaker): the "No" of a Yes/No answer is no negation ("the Yes and No answers for each
    # partner and month"); it is masked (same length) before a denial is looked for
    ANSWER_NO = re.compile(r"\bYes\b\s*(,|and|or|/|&)\s*\bNo\b|\bNo\b\s*(,|and|or|/|&)\s*\bYes\b|"
                           r"\b(a|the|each|every|one)\s+No\b|\bNo\s+answers?\b|\bNo\s+(counts?|groups?|columns?)\b")
    # a headcount claim: a quantity word and "mentor(s)" in one clause, neither denied, once the names that hold
    # "mentors" (field names, the report's label, the keep list's labels, the question) are blanked
    QUANTITY = re.compile(r"(?i)\b(numbers?|counts?|counted|counting|totals?|totall?ed|sums?|summed|summing|"
                          r"add(s|ed|ing)?\s+up|how\s+many|head\s*counts?|tall(y|ies)|figures?|amounts?)\b")
    # round 3: a recruit is a mentor too ("the recruits each partner signed up")
    MENTOR_WORD = re.compile(r"(?i)\bmentors?\b|\brecruits\b|\brecruitees?\b|\brecruited\s+(people|persons|adults|"
                             r"volunteers|women)\b")
    # a person per partner ("the recruits each partner signed up", "new mentors each partner recruited") or one
    # person per answer ("one new mentor brought in"; "at least one new mentor" is what a Yes means, and passes)
    PERSON_PER_PARTNER = re.compile(r"(?i)\b(mentors?|recruits)\s+(that\s+|who\s+|whom\s+)?(each|every|the|a|that|this|"
                                    r"one|per)\s+partner\b")
    ONE_PERSON = re.compile(r"(?i)(?<!least\s)\b(one|a\s+single|each|every)\s+(new\s+|recruited\s+)?(mentor|recruit)\b")
    AT_LEAST_ONE = re.compile(r"(?i)\bat\s+least\s+one\b")
    # the rejected field's own description, which names recruits: "recruits still needing orientation"
    ORIENTATION_REASON = re.compile(r"(?i)\bstill\s+need\w*\s+(\w+\s+){0,3}?orientation\b")
    # a window other than the last 12 months ("the last 24 months", `LAST_N_MONTHS:24`)
    WINDOW = re.compile(r"(?i)\bLAST_N_MONTHS:(?P<n>\d+)\b|\b(last|past|previous)\s+(?P<w>\d+|one|two|three|six|nine|"
                        r"twelve|eighteen|twenty-four|thirty-six)\s+(complete\s+|calendar\s+|full\s+)?months\b")
    # D4 replaced ("in place of D4", "instead of GLOW Club Training")
    IN_PLACE_OF_D4 = re.compile(r"(?i)\b(in\s+place\s+of|instead\s+of|rather\s+than)\s+(the\s+)?"
                                r"(dashboard\s+)?(D4|GLOW Club Training|[\"“]Mentors[\"”])")
    # what turns a Rejected reason around ("rejected only because", "even though", "for now", "D4 is not enough")
    TURNED = re.compile(r"(?i)\b(even\s+though|although|though|despite|only\s+because|for\s+now|later|until|yet|"
                        r"not\s+enough|insufficient|carr(y|ies)\s+a\s+partner|ha(ve|s)\s+a\s+partner\s+link)\b|"
                        r"isn['’]t\s+enough")
    QUESTION = "Did you recruit any new mentors last month?"
    NAME_TOKEN = re.compile(r"\b\w+__[cr]\b")
    # the one way to speak of a mentor count: the true count a future form question would give
    TRUE_COUNT = re.compile(r"(?i)\b(true|real|actual|exact)\s+(number|count|total|headcount)\b")
    FORM_QUESTION = re.compile(r"(?i)\b(question|form)\b")
    # a custom field that reads as a date (`Submitted_On__c`, `YearMonth__c`), which is never the month
    IDENT = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9_]*?__c\b")
    DATE_LIKE = re.compile(r"(?i)date|day|week|month|year|time|stamp|period|created|submitted|modified|_on$|_at$")
    BUILT_FROM = re.compile(r"(?i)\b(built|computed|made|derived|formula|calculated)\b")
    # a query's period on Period__c, and one that gives month by month (grouped by the month, or one month)
    Q_PERIOD = re.compile(r"(?i)\bPeriod__c\s*(=\s*(LAST_N_MONTHS:\d+|LAST_MONTH|\d{4}-\d\d-\d\d)\b|"
                          r"(>=|<=|>|<)\s*\d{4}-\d\d-\d\d\b)")
    # fix round (PR #155 review): the six months' check groups by the month and covers exactly six complete months
    BY_MONTH_GROUP = re.compile(r"(?i)\bGROUP\s+BY\s+[^`;]*?(CALENDAR_MONTH\(\s*Period__c\s*\)|\bPeriod__c\b)")
    N_MONTHS = re.compile(r"(?i)\bPeriod__c\s*=\s*LAST_N_MONTHS:(\d+)\b")
    BOUND = re.compile(r"(?i)\bPeriod__c\s*(>=|<=|>|<|=)\s*(\d{4})-(\d\d)-(\d\d)\b")
    OTHER_LITERAL = re.compile(r"(?i)\bPeriod__c\s*=\s*(?!LAST_N_MONTHS:)[A-Z_]+(:\d+)?\b")
    BY_MONTH_Q = re.compile(r"(?i)\bGROUP\s+BY\s+[^`;]*?(CALENDAR_MONTH\(\s*Period__c\s*\)|\bPeriod__c\b)|"
                            r"\bPeriod__c\s*=\s*(LAST_MONTH|\d{4}-\d\d-\d\d)\b|\bPeriod__c\s*>=?\s*\d{4}-\d\d-\d\d\b")
    # what the measure counts, as a consequence: partners or partner-months, not mentors
    PARTNER_UNIT = re.compile(r"(?i)\bpartner['’]s\s+months?\b|\bpartner[- ]months?\b|\b(number|count)\s+of\s+"
                              r"partners\b|\bcounts?\s+(\w+\s+){0,2}?partners\b|\bpartners,?\s+not\s+mentors\b")
    # each rejected source with its reason
    LEAD_REASON = re.compile(r"(?i)\bhousehold|\bno partner\b|\bnot linked\b|\bno link\b|\bwithout\s+(a\s+)?partner\b|"
                             r"\bnot (tied|attached|connected) to\b|\bno mentor list\b")
    DASH_REASON = re.compile(r"(?i)\bD4\b|\bcomponent\b|GLOW Club Training|\bkeep list\b|\benough\b")

    @classmethod
    def setUpClass(cls):
        TrainingDashboardDocs.setUpClass()
        cls.t = TrainingDashboardDocs()         # #78's helpers: part, units, step_clauses, the guards
        cls.d = cls.t.d                         # #69's: locally_denied, denies, assertNoContradiction
        cls.k = cls.t.k                         # #70's
        import csv
        with open(TrainingDashboardDocs.KEEP_LIST, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        # names of two words or more: D4's label is the bare word "Mentors", which is the word looked for
        names = {r[c] for r in rows for c in ("measure", "label_today", "label_target") if len(r[c].split()) > 1}
        names |= {cls.LABEL, cls.QUESTION}
        cls.NAMES = re.compile("|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
                               + r"|\bLead Mentors?\b", re.I)

    @staticmethod
    def norm(text):
        return DecommissionedFoldersDocs.norm(text)

    def clauses(self, text, ends=".;"):
        return sentences(self.norm(text), ends)

    @classmethod
    def unno(cls, s):
        """`s` with the "No" of a Yes/No answer masked, the same length (positions hold)."""
        return cls.ANSWER_NO.sub(lambda m: re.sub(r"\bNo\b", "N_", m.group(0)), s)

    def denied(self, s, m):
        return self.d.locally_denied(self.unno(s), m)

    def stated(self, s, rx):
        return any(not self.denied(s, m) for m in rx.finditer(s))

    def assertNoHeadcount(self, text, where):
        """No clause of `text` says the measure is a number of mentors ("how many new mentors each partner
        recruited", "adds up the Yes answers as the new mentors", "a mentor headcount"): each Yes is one partner's
        month (Ryan, 2026-10-26). A quantity word beside "mentor(s)" is only ever denied, but for the true count a
        form question would give."""
        rule = "item 12 counts Monthly Reports, each Yes one partner's month, never a number of mentors or recruits " \
               "(Ryan, 2026-10-26)"
        for s in sentences(flat(text), ".;:"):
            if self.TRUE_COUNT.search(s) and self.FORM_QUESTION.search(s):
                continue
            k = self.unno(self.NAMES.sub(lambda m: "X" * len(m.group(0)), self.NAME_TOKEN.sub(
                lambda m: "X" * len(m.group(0)), s)))
            who = [m for m in self.MENTOR_WORD.finditer(k) if not self.d.locally_denied(k, m)]
            if not who:
                continue
            for rx, what in ((self.PERSON_PER_PARTNER, "people per partner"), (self.ONE_PERSON, "one person per answer")):
                for m in rx.finditer(k):
                    self.assertTrue(self.d.locally_denied(k, m), f"{where}: {rule}; {m.group(0)!r} counts {what} (name "
                                                                 f"it only to deny it): {s[:200]!r}")
            # the rejected field's own description ("recruits still needing orientation") is no claim about item 12
            qty = [m for m in self.QUANTITY.finditer(k) if not self.d.locally_denied(k, m)]
            if qty and not self.ORIENTATION_REASON.search(s):
                self.fail(f"{where}: {rule}; {qty[0].group(0)!r} beside {who[0].group(0)!r} says otherwise (name a "
                          f"mentor count only to deny it): {s[:200]!r}")
            # what a Yes stands for, said beside a mentor: one partner's month, or a denied headcount
            if [m for m in self.YES.finditer(k) if not self.d.locally_denied(k, m)]:
                self.assertTrue(self.stated(s, self.PARTNER_MONTH) or self.NOT_HEADCOUNT.search(s)
                                or self.AT_LEAST_ONE.search(s) or re.search(r"(?i)\bpartner['’]s\s+(Yes|answer)\b", s),
                                f"{where}: {rule}; a clause that says what a Yes stands for beside a mentor says one "
                                f"partner's month (\"not a number of mentors\"): {s[:200]!r}")

    def assertTwelveMonths(self, text, where):
        """No window but the last 12 months (`Period__c = LAST_N_MONTHS:12`), unless denied."""
        words = {"twelve": 12}
        for s in sentences(flat(text), ".;:"):
            for m in self.WINDOW.finditer(s):
                n = m.group("n") or m.group("w")
                if (int(n) if n.isdigit() else words.get(n.lower(), 0)) == 12:
                    continue
                self.assertTrue(self.denied(s, m), f"{where}: the period is the last 12 months (`Period__c = "
                                                   f"LAST_N_MONTHS:12`, Ryan 2026-10-26), not {m.group(0)!r}: {s[:200]!r}")

    def assertNoSeparateDashboard(self, text, where):
        """The measure is a component on D4 (Ryan, 2026-10-26: no separate dashboard): a dashboard of its own is
        only ever denied, and nothing replaces D4."""
        for s in sentences(flat(text), ".;:"):
            for m in self.SEPARATE_DASHBOARD.finditer(s):
                self.assertTrue(self.denied(s, m) or re.search(r"(?i)\brejected\b", s[:m.start()]),
                                f"{where}: the measure is a component on D4, GLOW Club Training, and no dashboard of "
                                f"its own (Ryan, 2026-10-26); name one only to deny it: {s[:200]!r}")
            for m in self.IN_PLACE_OF_D4.finditer(s):
                self.assertTrue(self.denied(s, m), f"{where}: the component goes on D4, never in its place: "
                                                   f"{s[:200]!r}")

    def assertMonthIsPeriod(self, text, where):
        """The month is `Period__c`: a standard date field (#78's `assertNoOtherDate`) or a custom field that reads
        as a date (`Submitted_On__c`, `YearMonth__c`) is only ever denied; `Year__c` and `Month__c` may be named
        as what `Period__c` is built from."""
        self.t.assertNoOtherDate(text, where)
        exempt = {"Period__c", self.FIELD, self.NEWLY, "DHIS2__c", "Account__c"} | set(self.OTHER_FIELDS.values())
        for s in sentences(flat(text), ".;:"):
            for m in self.IDENT.finditer(s):
                name = m.group(0)
                if name in exempt or not self.DATE_LIKE.search(name[:-3]):
                    continue
                if name in ("Year__c", "Month__c") and "Period__c" in s and self.BUILT_FROM.search(s):
                    continue
                self.assertTrue(self.denied(s, m),
                                f"{where}: the month is the Monthly Report's `Period__c`, never `{name}`; name it only "
                                f"to deny it: {s[:200]!r}")

    def item_units(self, part):
        """The units (table row, list item, sentence) of `part` about item 12: those carrying its field, or naming
        item 12 (by `item 12` or its label) and no other item."""
        out = []
        for u in self.t.units(part):
            refs = self.t.item_refs(u, {self.ITEM: self.LABEL})
            if self.FIELD in u or (self.ITEM in refs and refs <= {self.ITEM}):
                out.append(u)
        return out

    def item_query(self, q, period=None):
        """Query `q` (a whole `SELECT … FROM DHIS2__c …`) is item 12's: it selects the answer and counts, groups by
        the answer, leaves blank answers out, carries the test-record rule, has no OR, never touches
        `Newly_recruited__c`, and has a period on `Period__c` (`period`, a pattern, when given)."""
        select = re.match(r"(?i)SELECT\s+(.*?)\s+FROM\s", q).group(1)
        f = re.escape(self.FIELD)
        return bool(re.search(f, select) and self.COUNT.search(select)
                    and re.search(r"(?i)\bGROUP\s+BY\s+[^`;]*?\b%s\b" % f, q)
                    and self.ANSWER_NOT_NULL.search(q) and self.t.SOQL_NOT_BLANK.search(q)
                    and self.t.SOQL_NO_TEST.search(q) and not self.OR.search(q) and self.NEWLY not in q
                    and re.search(r"\bPeriod__c\b", q) and (period is None or period.search(q)))

    def queries(self, text):
        return [m.group(0) for m in self.t.QUERY.finditer(flat(text))]

    def six_complete_months(self, q, today=None):
        """Query `q`'s period on `Period__c` (the first day of the report's month) is exactly the last six complete
        months: `Period__c = LAST_N_MONTHS:6` (which leaves out the current month) and no other window, or a closed
        date range (a lower and an upper bound) that six whole months satisfy, the last before the current month."""
        import datetime
        today = today or datetime.date.today()
        relative = self.N_MONTHS.findall(q)
        bounds = [(op, datetime.date(int(y), int(mo), int(d))) for op, y, mo, d in self.BOUND.findall(q)]
        if self.OTHER_LITERAL.search(q):
            return False                                    # LAST_MONTH, THIS_YEAR, …: not six months
        if relative:
            return set(relative) == {"6"} and not bounds
        if any(op == "=" for op, _ in bounds) or not any(op in (">", ">=") for op, _ in bounds) \
                or not any(op in ("<", "<=") for op, _ in bounds):
            return False                                    # a closed range: both bounds
        tests = {">=": lambda a, b: a >= b, ">": lambda a, b: a > b, "<=": lambda a, b: a <= b, "<": lambda a, b: a < b}
        lo = min(d for _, d in bounds)
        months, y, m = [], lo.year, lo.month
        hi = max(d for _, d in bounds)
        while (y, m) <= (hi.year, hi.month):
            first = datetime.date(y, m, 1)
            if all(tests[op](first, d) for op, d in bounds):
                months.append(first)
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return len(months) == 6 and months[-1] < datetime.date(today.year, today.month, 1)

    def assertOnlyDenied(self, text, rx, where, what):
        """Every clause of `text` naming `rx` denies or rejects it."""
        for s in self.clauses(text, ".;:"):
            for m in rx.finditer(s):
                self.assertTrue(self.denied(s, m) or self.d.NEGATION.search(self.unno(s)) or self.REJECT.search(s),
                                f"{where}: {what} is not item 12's source (Ryan, 2026-10-26); name it only to deny or "
                                f"reject it: {s[:200]!r}")

    def assertNoOtherChange(self, text, where):
        for s in self.clauses(text, ".;:"):
            for m in self.OTHER_CHANGE.finditer(s):
                self.assertTrue(self.d.locally_denied(s, m),
                                f"{where}: restore only from this change's copy or `before/`, never from another "
                                f"ticket's build or retrieve: {s[:200]!r}")
            if self.stated(s, self.t.RESTORE):
                for m in self.t.BUILD_DIR.finditer(s):
                    self.assertTrue(self.d.locally_denied(s, m),
                                    f"{where}: a rollback never deploys a `build/` (DECISIONS 2026-10-16); name "
                                    f"`build/` there only to deny it: {s[:200]!r}")

    def plan_path(self):
        found = sorted(glob.glob(self.PLANS))
        self.assertEqual(len(found), 1, "docs/plans/: one plan `YYYY-MM-DD-sf-new-mentors.md` for ticket #80 "
                                        f"(found {[os.path.basename(p) for p in found]})")
        self.assertRegex(os.path.basename(found[0]), r"^\d{4}-\d\d-\d\d-sf-new-mentors\.md$",
                         "docs/plans/: the plan is named `YYYY-MM-DD-sf-new-mentors.md`")
        return found[0]

    def decision(self):
        entries = re.split(r"(?m)^(?=### )", read(self.DECISIONS))[1:]
        new = [e for e in entries if re.match(r"### (\d{4}-\d\d-\d\d) ", e)
               and re.match(r"### (\d{4}-\d\d-\d\d) ", e).group(1) >= "2026-10-26"
               and self.FIELD in e]
        self.assertTrue(new, "docs/DECISIONS.md: no dated entry (`### 2026-10-26 — …`, or later) defining a new mentor "
                             f"by `DHIS2__c.{self.FIELD}` (ticket #80)")
        self.assertEqual(len(new), 1, f"docs/DECISIONS.md: one dated entry defining a new mentor, not {len(new)}")
        return new[0]

    # --- the RUNBOOK ----------------------------------------------------------------------------------------

    def test_the_runbook_defines_a_new_mentor_and_its_month(self):
        where = f"RUNBOOK section {self.t.MONTHLY[3:]!r}, {self.t.PART[4:]!r}, item 12"
        part = self.t.part()
        units = self.item_units(part)
        self.assertTrue([u for u in units if self.FIELD in u], f"{where}: no row, list item or sentence about item "
                                                                f"12 carries its field "
                               f"`DHIS2__c.{self.FIELD}`")
        text = " ".join(units)
        # who counts and which date places it in a month, in one unit: item 12 (its label), the field, Yes,
        # Period__c
        self.assertTrue([u for u in units if self.LABEL in u and self.FIELD in u and self.stated(self.norm(u), self.YES)
                         and self.stated(self.norm(u), self.t.PERIOD)],
                        f"{where}: in one row, list item or sentence: the report \"{self.LABEL}\" (item 12) counts the "
                        f"Monthly Reports (`DHIS2__c`) answering Yes to `{self.FIELD}`, each in the month of its "
                        "`Period__c` (Ryan, 2026-10-26)")
        self.assertIn("DHIS2__c", text, f"{where}: name the source object, the Monthly Report `DHIS2__c`")
        self.assertRegex(text, self.YES_AND_NO, f"{where}: the report counts the Yes and the No answers")
        cl = self.clauses(text)
        self.assertTrue([s for s in cl if self.stated(s, self.BLANK_OUT)
                         and not re.search(r"(?i)\b(not|never)\s+(left|excluded|dropped)\b", s)],
                        f"{where}: say a blank answer is left out (as items 15 and 16), not negated")
        # the month is the Monthly Report's period, and the partner its account
        self.assertTrue([s for s in cl if self.stated(s, self.t.PERIOD) and re.search(r"(?i)\bmonths?\b", s)],
                        f"{where}: the month is the report's `Period__c` (the month the Monthly Report covers), in one "
                        "sentence, not negated")
        self.assertMonthIsPeriod(text, where)
        self.assertTrue(self.stated(self.norm(text), self.t.ACCOUNT),
                        f"{where}: the partner is the Monthly Report's `Account__c`")
        self.assertTrue([s for s in cl if self.stated(s, self.EACH_PARTNER_MONTH)],
                        f"{where}: the counts are for each partner and month (\"for each partner and month\"), not "
                        "negated")
        # what a Yes means: one partner's month, never a number of mentors
        self.assertTrue([s for s in cl if self.stated(s, self.YES) and self.stated(s, self.PARTNER_MONTH)
                         and self.NOT_HEADCOUNT.search(s)],
                        f"{where}: say, in one sentence, that each Yes is one partner's month, not a number of mentors")
        self.assertNoHeadcount(text, where)
        self.assertTwelveMonths(text, where)
        self.assertNoSeparateDashboard(text, where)
        # the SOQL signal: GROUP BY the answer over the last 12 months on Period__c, with the test-record rule
        f = self.FIELD
        self.assertTrue([q for u in units for q in self.queries(u) if self.item_query(q, self.LAST_12_Q)],
                        f"{where}: give item 12's SOQL signal as a query in its row, item or sentence: `SELECT {f}, "
                        f"COUNT(Id) FROM DHIS2__c WHERE Period__c = LAST_N_MONTHS:12 AND Account__c != null AND (NOT "
                        f"Account__r.Name LIKE '%test%') AND {f} != null GROUP BY {f}` (no OR)")
        # kept apart from items 13-16: no unit carries both item 12's field and another item's
        for u in self.t.units(part):
            if self.FIELD in u:
                stray = sorted(n for n, other in self.OTHER_FIELDS.items() if other in u)
                self.assertFalse(stray, f"{where}: item 12's field and the field of item(s) {stray} share a row, item "
                                        f"or sentence; item 12 (recruiting) is not item 13 (mentors trained): {u[:200]!r}")
        for u in units:
            for n, other in self.t.items().items():
                self.assertNotIn(other["label_today"], u, f"{where}: item 12 is never labelled or described as item "
                                                          f"{n}, {other['label_today']!r}: {u[:200]!r}")
        # the rejected sources are only ever denied
        self.assertOnlyDenied(part, re.compile(re.escape(self.NEWLY)), where, f"`{self.NEWLY}`")
        self.assertOnlyDenied(part, self.LEAD_MENTOR, where, "a \"Lead Mentor\" contact")
        self.t.assertNotSoft(text, where)
        self.t.assertNoPartnerOrMonthFilter(text, where)
        self.d.assertNoContradiction(text, where)

    # --- the plan ---------------------------------------------------------------------------------------------

    def test_a_plan_carries_the_new_mentors_deploy(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        text = read(path)
        keys, _ = docs_index.frontmatter(text)
        self.assertIn("status", keys, f"{name}: frontmatter `status:`")
        word, problem = docs_index.status_of(keys["status"])
        self.assertIsNone(problem, f"{name}: {problem}")
        self.assertNotEqual(word, "superseded", f"{name}: the plan is the change in force")
        if word == "done":
            self.assertRegex(keys.get("done", ""), r"^\d{4}-\d\d-\d\d", f"{name}: a done plan carries `done:`")
        self.assertRegex(text.split("\n## ", 1)[0], self.TICKET,
                         f"{name}: name ticket #80 in the frontmatter, the title or the opening paragraph")
        self.assertIn(self.LABEL, text, f"{name}: name the new report, \"{self.LABEL}\"")
        self.assertIn(self.FIELD, text, f"{name}: name the field the report counts, `DHIS2__c.{self.FIELD}`")
        self.assertRegex(text, r"(?m)^## Result\b", f"{name}: no `## Result` section")
        self.t.assertNoPartnerOrMonthFilter(text, name)
        # the whole plan, `## Result` included: no rejected source, no other month, no mentor headcount
        self.assertOnlyDenied(text, re.compile(re.escape(self.NEWLY)), name, f"`{self.NEWLY}`")
        self.assertOnlyDenied(text, self.LEAD_MENTOR, name, "a \"Lead Mentor\" contact")
        self.assertMonthIsPeriod(text, name)
        self.assertNoHeadcount(text, name)
        self.assertNoSeparateDashboard(text, name)
        dash = self.t.dashboard()

        # --- the Rollout
        raw = self.t.plan_part(path, "## Rollout", 40)
        where = f"{name}: `## Rollout`"
        cl = self.clauses(raw)
        self.assertRegex(flat(raw), self.BEFORE, f"{where}: retrieve D4 fresh into `data/sf_new_mentors_<date>/before/`")
        cmds = [flat(seg)[m.start():] for seg in re.split(r"`+|\n\s*\n|(?=\bpython3\s)", raw)
                for m in [self.t.COPY_CMD.search(flat(seg))] if m]
        self.assertTrue(cmds, f"{where}: the copy of D4 by `python3 tools/sf_report_folders.py copy --vpn-off --kind "
                              f"dashboard --id {dash['id']} --tag \"#80\" --apply`")
        for c in cmds:
            self.assertIn("--vpn-off", c, f"{where}: the tool refuses to run without `--vpn-off`: {c[:160]!r}")
            self.assertRegex(c, r"--apply\b", f"{where}: the copy runs with `--apply` (on Ryan's go); without it the "
                                              f"tool makes no copy: {c[:160]!r}")
            tags = [v.strip("`'\"") for v in re.findall(r"--tag(?:=|\s+)(\S+)", c)]
            self.assertTrue(tags and all(t == "#80" for t in tags), f"{where}: the copy is tagged `--tag \"#80\"`: "
                                                                    f"{c[:160]!r}")

        def flag(c, f):
            return [v.strip("`'\".,;") for v in re.findall(r"--%s(?:=|\s+)(\S+)" % f, c)]
        self.assertTrue([c for c in cmds if dash["id"] in flag(c, "id") and flag(c, "kind") == ["dashboard"]],
                        f"{where}: copy the dashboard {dash['item']} with `python3 tools/sf_report_folders.py copy "
                        f"--vpn-off --kind dashboard --id {dash['id']} --tag \"#80\" --apply` (its id from "
                        "`glow/sf_keep_list.csv`, no placeholder)")
        self.assertTrue([s for s in cl if self.stated(s, self.t.COPY) and "Decommissioned" in s
                         and re.search(r"(?i)\bdashboard\b|\bD4\b", s)],
                        f"{where}: the dashboard D4 is copied into Decommissioned before it changes (one sentence, not "
                        "negated)")
        self.assertTrue([s for s in cl if re.search(r"(?i)check-only|--dry-run", s) and re.search(r"(?i)\bdeploy", s)
                         and not self.d.denies(s)],
                        f"{where}: validate check-only (`sf project deploy start --dry-run`) before the deploy (one "
                        "sentence)")
        self.assertTrue([s for s in cl if re.search(r"Ryan['’]s go\b", s) and re.search(r"(?i)\bdeploy|--apply", s)
                         and not self.d.denies(s)],
                        f"{where}: the deploy and each `--apply` wait for Ryan's go (one sentence)")
        readback = [s for s in cl if [m for m in self.t.READBACK.finditer(s) if not self.d.locally_denied(s, m)]
                    and re.search(r"(?i)\bretriev\w*|\bread\w*\s+(it\s+)?back\b", s)]
        self.assertTrue(readback, f"{where}: read back: retrieve into `after/` and check `after/` equals `build/`, in one "
                                  "sentence")
        # the SOQL check: the component equals SOQL on DHIS2__c for six complete months and for one partner
        self.assertTrue([s for s in cl if (re.search(r"\bSOQL\b", s) or self.t.SOQL_ON_DHIS2.search(s))
                         and self.stated(s, self.t.EQUAL_STRICT) and re.search(r"(?i)\bcomponents?\b", s)
                         and self.stated(s, self.SIX_MONTHS)],
                        f"{where}: check that the component equals SOQL on `DHIS2__c` for each of the last six complete "
                        "months (one sentence naming the component, SOQL, six complete months and that they equal)")
        self.assertTrue([s for s in cl if self.stated(s, self.ONE_PARTNER) and self.stated(s, self.t.EQUAL_STRICT)],
                        f"{where}: check one partner's figures equal SOQL (one sentence naming one partner and that "
                        "they equal)")
        qs = self.queries(raw)
        self.assertTrue([q for q in qs if self.item_query(q, self.Q_PERIOD) and self.BY_MONTH_GROUP.search(q)
                         and self.six_complete_months(q) and not self.PARTNER_Q.search(q)],
                        f"{where}: give the six months' query, for all partners (not the one-partner query), month by "
                        f"month, over exactly the last six complete months: item 12's (`SELECT Period__c, {self.FIELD}, COUNT(Id) … GROUP BY Period__c, "
                        f"{self.FIELD}`, or by `CALENDAR_MONTH(Period__c)`) with `Period__c = LAST_N_MONTHS:6`, or a "
                        "closed range of six whole months ending before the current month (`Period__c >= 2026-04-01 "
                        f"AND Period__c < 2026-10-01`), the test-record rule, `{self.FIELD} != null`, no OR")
        self.assertTrue([q for q in qs if self.item_query(q, self.Q_PERIOD) and self.PARTNER_Q.search(q)],
                        f"{where}: give the one-partner query: item 12's query, with a period on `Period__c`, and `AND "
                        "Account__r.Name = '<partner>'`")
        self.t.assertNotSoft(raw, where)
        self.t.assertNoOlderBuild(raw, where)
        self.d.assertNoContradiction(raw, where)
        # the order, step by step: before/, the copy, check-only, deploy on Ryan's go, after/, SOQL
        steps = self.t.step_clauses(raw, where)
        flat_cl = [(i, j, st, c) for i, (n, st, cs) in enumerate(steps) for j, c in enumerate(cs)]
        not_check = re.compile(r"(?i)check-only|--dry-run|\bvalidat\w*")
        deploy_verb = re.compile(r"(?i)(?<!\bthe )(?<!\ba )(?<!\bits )(?<!\bfor )(?<!\bthis )(?<!\bto )"
                                 r"\bdeploy(s|ed|ing)?\b")

        def first(pred, after=(-1, -1), what=""):
            found = [(i, j) for i, j, st, c in flat_cl if (i, j) > after and pred(c, st)]
            self.assertTrue(found, f"{where}: in the numbered steps, no {what}"
                                   + (" after the step before it" if after != (-1, -1) else ""))
            return found[0]
        at_before = first(lambda c, st: self.BEFORE.search(c), what="retrieve into `before/`")
        at_copy = first(lambda c, st: re.search(r"sf_report_folders[._]py\s+copy\b", c), at_before,
                        "copy step (`tools/sf_report_folders.py copy`)")
        at_check = first(lambda c, st: not_check.search(c), at_copy, "check-only (`--dry-run`)")
        early = [c for i, j, st, c in flat_cl if (i, j) < at_check and not not_check.search(c)
                 for m in deploy_verb.finditer(c) if not self.d.locally_denied(c, m)]
        self.assertEqual(early, [], f"{where}: nothing deploys before the check-only: {early[:1]}")
        at_deploy = first(lambda c, st: re.search(r"(?i)\bdeploy\w*", c) and not not_check.search(c), at_check,
                          "deploy after the check-only")
        deploy_step, check_step = steps[at_deploy[0]], steps[at_check[0]]
        self.assertRegex(deploy_step[1], r"Ryan['’]s go\b",
                         f"{where}: step {deploy_step[0]}, the deploy, waits for Ryan's go (say so in that step)")
        for st, what in ((check_step, "the check-only"), (deploy_step, "the deploy")):
            self.assertRegex(st[1], r"\bbuild/", f"{where}: step {st[0]}, {what}, names what it deploys: `build/`")
            nst = self.norm(st[1])
            for m in re.finditer(r"before/", nst):
                self.assertTrue(self.d.locally_denied(nst, m),
                                f"{where}: step {st[0]}, {what}, deploys `build/`, never `before/` (that is the "
                                f"rollback's): {nst[:200]!r}")
        for n, st, _cs in steps:
            if "--apply" in st:
                self.assertRegex(st, r"Ryan['’]s go\b", f"{where}: step {n} runs `--apply`; say in that step it waits "
                                                       "for Ryan's go")
        at_after = first(lambda c, st: "after/" in c, at_deploy, "retrieve into `after/`")
        first(lambda c, st: re.search(r"\bSOQL\b|\bFROM\s+DHIS2__c\b", c), at_after, "SOQL check")

        # --- the Rollback
        raw = self.t.plan_part(path, "## Rollback", 20)
        where = f"{name}: `## Rollback`"
        cl = self.clauses(raw)
        restore_d4 = [k for k, s in enumerate(cl) if self.stated(s, self.t.RESTORE) and "Decommissioned" in s
                      and self.t.COPY.search(s) and re.search(r"(?i)\bdashboard\b|\bD4\b", s)]
        self.assertTrue(restore_d4, f"{where}: restore the dashboard D4 from its copy in Decommissioned (one sentence, "
                                    "not negated)")
        self.assertRegex(raw, self.BEFORE, f"{where}: name this change's `before/`, `data/sf_new_mentors_<date>/before/`")
        dirs = set(self.WORK_DIR.findall(flat(raw)))
        self.assertEqual(len(dirs), 1, f"{where}: one folder for this change, `data/sf_new_mentors_<date>/` (found "
                                       f"{sorted(dirs)})")
        guarded = [s for s in cl if "before/" in s and "after/" in s and self.t.FRESH.search(s)
                   and self.stated(s, self.t.EQUAL_STRICT) and self.stated(s, self.t.CONDITION)]
        self.assertTrue(guarded, f"{where}: deploy `before/` back only while a fresh retrieve equals `after/` (one "
                                 "sentence naming `before/`, a fresh retrieve, `after/`, the condition and \"equals\")")
        for s in guarded:
            for m in self.t.DIFFER.finditer(s):
                self.assertTrue(self.d.locally_denied(s, m),
                                f"{where}: `before/` goes back only while the fresh retrieve EQUALS `after/`, never when "
                                f"it differs: {s[:200]!r}")
        self.assertTrue([s for s in cl for m in self.t.OLDER_BUILD.finditer(s) if self.d.locally_denied(s, m)],
                        f"{where}: say never from an older build (DECISIONS 2026-10-16), in one sentence")
        # the new report: off D4 with it, then moved to Decommissioned (the epic deletes nothing)
        moved = [k for k, s in enumerate(cl) if self.stated(s, self.NEW_REPORT) and "Decommissioned" in s
                 and self.stated(s, self.MOVE)]
        self.assertTrue(moved, f"{where}: the new report (\"{self.LABEL}\") is moved to Decommissioned, not deleted (one "
                               "sentence naming it, a move and Decommissioned, not negated)")
        self.assertGreater(moved[0], restore_d4[0],
                           f"{where}: the dashboard goes back first, then the report it no longer uses moves to "
                           "Decommissioned")
        self.assertTrue([s for s in cl if self.NOTHING_DELETED.search(s)],
                        f"{where}: say nothing is deleted (epic #68)")
        body = self.norm(raw)
        self.assertRegex(body, r"(?i)check-only|--dry-run", f"{where}: a deploy of `before/` is checked-only first")
        self.assertRegex(body, r"Ryan['’]s go\b", f"{where}: the rollback's writes wait for Ryan's go")
        for rx, what in ((r"destructiveChanges", "a `destructiveChanges` deploy"),
                         (r"\bsf project delete\b", "`sf project delete`"),
                         (r"(-X\s*|--method\s+)DELETE\b|\bDELETE\s+/services/", "an HTTP DELETE")):
            self.assertNotRegex(raw, rx, f"{where}: {what} deletes; the rollback restores and deletes nothing")
        self.t.assertNoOlderBuild(raw, where)
        self.assertNoOtherChange(raw, where)
        self.t.assertBeforeGuarded(raw, where)
        self.t.assertNotSoft(raw, where)
        self.d.assertNoContradiction(raw, where, rollback=True)

    def test_the_six_months_check_takes_exactly_six_complete_months(self):
        """The guard behind the plan's six months' query (PR #155 review), on a fixed day, 2026-10-26: Period__c is
        the first of the report's month, so April-September 2026 are the six complete months."""
        import datetime
        today = datetime.date(2026, 10, 26)
        base = ("SELECT Period__c, {f}, COUNT(Id) FROM DHIS2__c WHERE {w} AND Account__c != null AND (NOT "
                "Account__r.Name LIKE '%test%') AND {f} != null GROUP BY Period__c, {f}")
        cases = [
            ("Period__c = LAST_N_MONTHS:6", True),
            ("Period__c >= 2026-04-01 AND Period__c < 2026-10-01", True),
            ("Period__c >= 2026-04-01 AND Period__c <= 2026-09-30", True),
            ("Period__c > 2026-03-31 AND Period__c <= 2026-09-01", True),
            ("Period__c >= 2026-03-01 AND Period__c < 2026-09-01", True),        # six whole months, all complete
            ("Period__c = LAST_N_MONTHS:12", False),                            # twelve
            ("Period__c = LAST_N_MONTHS:5", False),
            ("Period__c = LAST_N_MONTHS:6 AND Period__c = LAST_N_MONTHS:12", False),
            ("Period__c >= 2026-04-01", False),                                 # open: takes in October, partial
            ("Period__c <= 2026-09-30", False),                                 # open below
            ("Period__c >= 2026-05-01 AND Period__c < 2026-11-01", False),      # ends in the current month
            ("Period__c >= 2026-05-01 AND Period__c <= 2026-10-01", False),     # the same, inclusive
            ("Period__c >= 2026-04-01 AND Period__c < 2026-09-01", False),      # five months
            ("Period__c >= 2026-04-02 AND Period__c < 2026-10-01", False),      # April's first day left out: five
            ("Period__c >= 2026-03-01 AND Period__c < 2026-10-01", False),      # seven
            ("Period__c = LAST_MONTH", False),
            ("Period__c = 2026-09-01", False),
        ]
        for window, want in cases:
            q = base.format(f=self.FIELD, w=window)
            self.assertEqual(self.six_complete_months(q, today), want, f"six complete months on 2026-10-26: "
                                                                       f"{window!r} should be {want}")

    # --- DECISIONS --------------------------------------------------------------------------------------------

    def test_a_decision_records_the_new_mentor_definition(self):
        e = self.decision()
        where = f"docs/DECISIONS.md {e.split(chr(10), 1)[0][4:14]}"
        for part in ("**Why", "**Rejected", "**Consequences"):
            self.assertIn(part, e, f"{where}: no {part}** bullet (the file's header)")
        self.assertLess(e.index("**Why"), e.index("**Rejected"), f"{where}: **Why**, then **Rejected**")
        self.assertLess(e.index("**Rejected"), e.index("**Consequences"), f"{where}: **Rejected**, then **Consequences**")
        self.assertRegex(e, self.TICKET, f"{where}: name ticket #80")
        head = e.split("\n", 1)[1].split("**Why", 1)[0]
        why = e.split("**Why", 1)[1].split("**Rejected", 1)[0]
        rejected = e.split("**Rejected", 1)[1].split("**Consequences", 1)[0]
        cons = e.split("**Consequences", 1)[1]
        # the decision itself: who counts, which month, the partner, the window, the rule
        dw = f"{where}, the decision (before **Why**)"
        hc = self.clauses(head)
        self.assertIn(self.FIELD, head, f"{dw}: a new mentor is a Yes to `DHIS2__c.{self.FIELD}`")
        self.assertIn("DHIS2__c", head, f"{dw}: name the source object `DHIS2__c`")
        self.assertTrue([s for s in hc if self.FIELD in s and self.stated(s, self.YES)],
                        f"{dw}: the Monthly Reports answering Yes to `{self.FIELD}` count, in one sentence, not negated")
        self.assertRegex(head, self.YES_AND_NO, f"{dw}: the report counts the Yes and the No answers")
        self.assertTrue([s for s in hc if self.stated(s, self.t.PERIOD) and re.search(r"(?i)\bmonths?\b", s)],
                        f"{dw}: the month is `Period__c`, the month the Monthly Report covers (one sentence, not negated)")
        self.assertTrue(self.stated(self.norm(head), self.t.ACCOUNT), f"{dw}: the partner is `Account__c`")
        self.assertTrue([s for s in hc if self.stated(s, self.BLANK_OUT)
                         and not re.search(r"(?i)\b(not|never)\s+(left|excluded|dropped)\b", s)],
                        f"{dw}: blank answers are left out")
        self.assertRegex(self.norm(head), r"\bLAST_N_MONTHS:12\b|(?i:\blast 12 months\b)",
                         f"{dw}: the period is the last 12 months (`Period__c = LAST_N_MONTHS:12`)")
        self.assertTrue([s for s in hc if self.stated(s, self.TEST_RECORD)], f"{dw}: the test-record rule applies (#70)")
        self.assertTrue([s for s in hc if self.stated(s, self.PARTNER_MONTH) and self.NOT_HEADCOUNT.search(s)],
                        f"{dw}: each Yes is one partner's month, not a number of mentors (one sentence)")
        self.assertIn(self.LABEL, e, f"{where}: name the report, \"{self.LABEL}\"")
        self.assertTrue([s for s in self.clauses(e) if self.stated(s, re.compile(r"(?i)\bcomponent\b"))
                         and re.search(r"\bD4\b|GLOW Club Training", s)],
                        f"{where}: the measure is a component on GLOW Club Training (D4), in one sentence, not negated")
        # Why: Ryan's answer on the ticket
        self.assertRegex(why, r"\bRyan\b", f"{where}: **Why** gives Ryan's answer")
        self.assertIn("2026-10-26", why, f"{where}: **Why** dates Ryan's answer (2026-10-26)")
        # Rejected: each source with its reason, in one clause (`;`, `.` or a sub-bullet apart from the others):
        # Newly_recruited__c (recruits still needing orientation), the Lead Mentor contacts (household accounts, no
        # partner link), a separate dashboard (a component on D4 is enough)
        rw = f"{where}: **Rejected**"
        items = [flat(x) for x in re.split(r"[.;]\s|\n\s*[-*+]\s", rejected) if x.strip()]
        self.assertTrue([x for x in items if self.NEWLY in x and self.ORIENTATION_REASON.search(x)],
                        f"{rw}: name `{self.NEWLY}` with why it is not it, in its clause: it holds recruits who still "
                        "need orientation, not recruits")
        self.assertTrue([x for x in items if self.LEAD_MENTOR.search(x) and self.LEAD_REASON.search(x)],
                        f"{rw}: name the \"Lead Mentor\" contacts with why, in their clause: household accounts, no "
                        "partner link")
        self.assertTrue([x for x in items if self.SEPARATE_DASHBOARD.search(x) and self.DASH_REASON.search(x)],
                        f"{rw}: name a separate dashboard with why, in its clause: a component on D4 (GLOW Club "
                        "Training) is enough")
        # a reason is not turned around ("only because", "even though they carry a partner link", "for now though
        # D4 is not enough")
        for x in items:
            if self.NEWLY in x or self.LEAD_MENTOR.search(x) or self.SEPARATE_DASHBOARD.search(x):
                m = self.TURNED.search(x)
                self.assertFalse(m, f"{rw}: each source is rejected for its reason, as stated, with nothing that turns "
                                    f"it around ({m.group(0)!r}): {x[:200]!r}" if m else rw)
        # Consequences: what the figure is, partners (partner-months), not mentors
        self.assertGreaterEqual(len({w.lower() for w in re.findall(r"[A-Za-z]\w*", self.norm(cons))}), 10,
                                f"{where}: **Consequences** says too little")
        self.assertTrue([s for s in self.clauses(cons) if self.stated(s, self.PARTNER_UNIT)],
                        f"{where}: **Consequences** says what the figure counts: partners (one partner's month each), "
                        "not mentors, in one clause, not negated")
        self.assertNotRegex(e, r"(?i)\b(TBD|TODO|TBA|FIXME)\b", f"{where}: a placeholder")
        # outside Rejected (Consequences included), the rejected sources are only ever denied, the month is only
        # Period__c, no clause makes the figure a mentor headcount, and nothing contradicts the rules
        rest = re.sub(r"(?ms)^- \*\*Rejected.*?(?=^- \*\*|\Z)", "", e)
        self.assertNotIn("**Rejected", rest, f"{where}: **Rejected** is a bullet of its own (`- **Rejected:** …`)")
        self.assertOnlyDenied(rest, re.compile(re.escape(self.NEWLY)), where, f"`{self.NEWLY}`")
        self.assertOnlyDenied(rest, self.LEAD_MENTOR, where, "a \"Lead Mentor\" contact")
        self.assertMonthIsPeriod(rest, where)
        self.assertNoHeadcount(rest, where)
        self.assertTwelveMonths(rest, where)
        self.assertNoSeparateDashboard(rest, where)
        self.d.assertNoContradiction(rest, where)


class GlowReviewAttendanceDocs(unittest.TestCase):
    """Ticket #196 (epic #194, GLOW's review of 2026-11-02): D1 "Glow Club Attendance" and its items 1, 3 and 4
    show the reporting year only, `In_Reporting_Year__c equals true` (#195) in place of `Period__c equals
    LAST_N_MONTHS:12`; D1 gains a Month filter on `DHIS2__c$Month__c` beside Partner Manager; item 3's grand total
    and item 4's column totals (Sum Monthly Max included) are off, because adding counts across weeks and months
    double-counts girls who attend several sessions. The RUNBOOK's `### GLOW Club Attendance` says so, and keeps
    the old rule (the last 12 months, no Month filter, Partner Manager the only filter) only as history ("until
    #196", "was", "replaced"); the plan `docs/plans/2026-11-02-sf-review-attendance.md` carries the copies to
    Decommissioned, the check-only, Ryan's go, the deploy and the read-back, in that order, a Rollback and a
    `## Result`. The wording is free: each rule is looked for as a claim in a sentence or unit, not denied."""

    longMessage = False         # the messages say what to fix
    PLAN = os.path.join(REPO, "docs", "plans", "2026-11-02-sf-review-attendance.md")
    TICKET = re.compile(r"(?<![\w#])#196\b")
    ITEMS = ("1", "3", "4")     # D1's reports; item 2 is retired since #75
    GO = re.compile(r"Ryan['’]s go\b")
    EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}")
    # the reporting-year filter, as set ("`In_Reporting_Year__c equals true`", "`In_Reporting_Year__c = true`")
    YEAR_ON = re.compile(r"\bIn_Reporting_Year__c\b[^.;]{0,25}?\btrue\b")
    # 2026 only, 2025 out ("2026 only", "only 2026", "no 2025 month", "2025 is left out", "the reporting year only")
    ONE_YEAR = re.compile(r"(?i)\b2026\s+only\b|\bonly\s+(\w+\s+){0,3}?2026\b|\bno\s+(\w+\s+){0,3}?2025\b|"
                          r"\b2025\b[^.;]{0,40}?\b(excluded|left out|out|off|gone|dropped|hidden)\b|"
                          r"\breporting year only\b|\bonly\s+(the\s+)?(current\s+)?reporting year\b")
    # the old period, said as today's rule when no history marker is near it
    OLD_PERIOD = re.compile(r"\bLAST_N_MONTHS:12\b|(?i:\blast\s+(12|twelve)\s+months\b)")
    PERIOD_TALK = re.compile(r"(?i)Period__c|\bperiod\b|\bdate filter\b|\bfield filter\b|\breports?['’]? filters?\b")
    # said as the past or as what was replaced, near the old rule
    HISTORY = re.compile(r"(?i)\b(was|were|had|until|before|formerly|former|no longer|previously|used to|replac\w*|"
                         r"in place of|instead of|became|becomes|rather than|superseded|gave way)\b")
    # a Month filter ("a Month filter", "the "Month" filter", "a Month (`DHIS2__c$Month__c`) filter", "a filter on
    # `DHIS2__c$Month__c`")
    MONTH_FILTER = re.compile(r"(?i)\bMonth\b[\"”'’`]?\s*(\([^)]{0,60}\)\s*)?(dashboard\s+)?filters?\b|"
                              r"\bfilter(s|ed|ing)?\s+(on|by|for)\s+(the\s+|a\s+|each\s+)?[`\"“]?(DHIS2__c\$)?"
                              r"Month(__c)?\b")
    MONTH_FIELD = re.compile(r"\bMonth__c\b")
    # a Month filter denied, or Partner Manager the only filter: #75's rule, history since #196
    NO_MONTH = re.compile(r"(?i)\b(no|not|without|neither|nor|never)\b[^.;]{0,25}?\bMonth\b[^.;]{0,20}?\bfilters?\b")
    ONLY_PM = re.compile(r"(?i)\b(only|one|sole|single)\b[^.;]{0,30}?\bfilter\b[^.;]{0,40}?\bPartner Manager\b")
    # the totals and their removal ("the grand total row", "Sum Monthly Max total", "`showTotal` false", "no total")
    TOTAL = re.compile(r"(?i)\b(grand\s+totals?|totals?\s+rows?|column\s+totals?|sub-?totals?|totals?|"
                       r"showGrandTotal|showTotal)\b")
    OFF = re.compile(r"(?i)\b(remov\w*|hid(e|es|den|ing)|off|turned off|switched off|dropp\w*|taken out|takes? out|"
                     r"gone|false)\b|\b(no|without)\s+([\w`'’-]+\s+){0,3}?(grand\s+|column\s+)?totals?\b")
    # why: the totals add the same girls up more than once, so they are no count of unique girls
    DOUBLE = re.compile(r"(?i)\bdouble[- ]?count\w*|\bcount\w*\s+([\w'’-]+\s+){0,4}?(twice|more than once)\b|"
                        r"\bnot\s+(\w+\s+){0,4}?unique\s+girls\b")
    # a total still shown ("the grand total row stays", "`showGrandTotal` true")
    TOTAL_ON = re.compile(r"(?i)\b(grand\s+totals?|totals?\s+rows?|showGrandTotal|showTotal|Monthly Max totals?)\b"
                          r"[^.;]{0,30}?\b(stays?|remains?|kept|still|true)\b|"
                          r"\b(shows?|showing|displays?|displaying|keeps?|keeping|has|have)\s+(its\s+|the\s+|a\s+|their\s+)?"
                          r"(grand\s+totals?|totals?\s+rows?|column\s+totals?|sub-?totals?|Sum Monthly Max totals?)\b")
    # an old source for #196's rollback: #75's folder, another data/ folder, an older build ("the older build",
    # "#75's `before/`"); #196's own `data/sf_glow_review_<month>/` and a fresh retrieve are its sources
    OLD_SOURCE = re.compile(r"(?i)\bdata/sf_(?!glow_review_)[\w-]+/|"
                            r"\b(older|old|earlier|previous|prior|stale|another|other|original)\s+([\w-]+\s+)?"
                            r"(retrieves?|builds?|backups?|exports?|snapshots?|versions?)\b|"
                            r"#75['’]s\s+`?(before/|build/|retrieve|build)")

    @classmethod
    def setUpClass(cls):
        AttendanceDashboardDocs.setUpClass()
        cls.a = AttendanceDashboardDocs()       # #75's helpers: part, units, plan_part, keep_rows, said
        cls.d = cls.a.d                         # #69's helpers: locally_denied, NEGATION
        cls.c = cls.a.c                         # #73's helpers: steps

    @staticmethod
    def norm(text):
        return DecommissionedFoldersDocs.norm(text)

    @staticmethod
    def prose(s):
        """Clause `s` without its backticked SOQL statements: a query is a check, not a claim."""
        return re.sub(r"`[^`]*\bSELECT\b[^`]*`", " ", s)

    def history(self, s, m):
        """Match `m` of `s` said as the past or as what was replaced: a marker in the 50 characters before it or
        the 30 after, or a denial."""
        return bool(self.HISTORY.search(s[max(0, m.start() - 50):m.end() + 30]) or self.d.locally_denied(s, m))

    def reports(self):
        rows = self.a.keep_rows()
        found = {k: rows[k] for k in self.ITEMS if k in rows and rows[k]["kind"] == "report"}
        self.assertEqual(sorted(found), list(self.ITEMS), "glow/sf_keep_list.csv: items 1, 3 and 4 of "
                                                          "'GLOW Club Attendance' are reports")
        dash = [v for v in rows.values() if v["kind"] == "dashboard"]
        self.assertEqual(len(dash), 1, "glow/sf_keep_list.csv: one dashboard row for 'GLOW Club Attendance'")
        return found, dash[0]

    def names_item(self, u, item, r):
        return (r["label_today"] in u or r["id"] in u
                or re.search(r"(?i)\bitems?\s+(\d+\s*(,|and|&)\s*)*" + item + r"\b", u)
                or re.match(r"\|\s*" + item + r"\s*\|", u))

    @staticmethod
    def own_units(part):
        """The part's table rows and list items (each with its continuation lines), and its paragraphs that hold
        neither: a list's paragraph is not one more unit, so one item's sentence never stands for another's."""
        units = AttendanceDashboardDocs.units(part)     # rows and items first, then the paragraphs
        paragraphs = [p for p in re.split(r"\n\s*\n", part) if p.strip()]
        rows_and_items = units[:len(units) - len(paragraphs)]
        return rows_and_items + [flat(p) for p in paragraphs
                                 if not re.search(r"(?m)^\s*([-*+]|\d+[.)])\s|^\s*\|", p)]

    def unit_for(self, units, item, reports):
        """The units about item `item` alone: its label, Id or "item N" in the unit's first 120 characters (its
        subject), and no other D1 item named there."""
        out = []
        for u in units:
            head = re.sub(r"^\s*([-*+]|\d+[.)])\s+", "", u)[:120]
            if self.names_item(head, item, reports[item]) and not any(
                    self.names_item(head, k, r) for k, r in reports.items() if k != item):
                out.append(u)
        return out

    def assertNoOldSource(self, raw, where):
        """#196's rollback names no older source for D1 or the reports (#75's `data/sf_dash_attendance_…/`, another
        data/ folder, an older build or retrieve) unless the clause denies it ("never from an older build",
        "#75's folder is no rollback for this change")."""
        for s in sentences(self.norm(raw), ".;"):
            for c in re.split(r"[:,(]|\bbut\b|\bwhile\b|\bthen\b", s):
                for m in self.OLD_SOURCE.finditer(c):
                    self.assertTrue(self.d.NEGATION.search(c),
                                    f"{where}: #196's rollback restores D1 from #196's own `before/` and the reports from "
                                    f"their copies or a fresh retrieve, never from {m.group(0)!r} (DECISIONS "
                                    f"2026-10-16): {s[:200]!r}")

    # the reports in a rollback unit ("the reports", "each report's deploy", "items 1, 3 and 4")
    REPORTS = re.compile(r"(?i)\breports?\b|\bitems?\s+(\d+\s*(,|and|&)\s*)*[134]\b")
    DEPLOY = re.compile(r"(?i)\b(re-?)?deploy\w*\b")
    # a deploy's sources: a fresh retrieve edited back, or `before/` guarded by a fresh retrieve that equals `after/`
    EDITED_BACK = re.compile(r"(?i)\bfresh\s+retriev\w*\b[^.;]{0,40}?\bedit\w*\s+back\b")
    GUARD = re.compile(r"(?i)\b(only|while|as long as|so long as|provided)\b[^.;]{0,30}?\bfresh\s+retriev\w*\b[^.;]{0,40}?"
                       r"\b(equals?|matches|match|is the same as|identical to)\b[^.;]{0,20}?\bafter/")

    def deployed(self, u):
        """A sentence of unit `u` that restores by a deploy, not denied."""
        return any(self.a.said(s, self.DEPLOY) for s in sentences(u, ".;"))

    def deploy_source(self, u):
        return bool(self.EDITED_BACK.search(u) or ("before/" in u and self.GUARD.search(u)))

    def runbook_rollback(self):
        """The RUNBOOK part's rollback of #196: from the line that starts `Rollback` and names #196 to the end."""
        part = self.a.part()
        m = re.search(r"(?im)^\W*rollback\b[^\n]*#196\b", part)
        self.assertTrue(m, f"RUNBOOK {AttendanceDashboardDocs.PART!r}: no rollback of #196 (a paragraph starting "
                           "`Rollback of #196`)")
        return part[m.start():]

    # --- the RUNBOOK ----------------------------------------------------------------------------------------

    def test_the_runbook_states_the_reporting_year_and_month_filter(self):
        where = f"RUNBOOK {AttendanceDashboardDocs.PART!r}"
        part = self.a.part()
        cl = [self.prose(s) for s in sentences(self.norm(part), ".;")]
        # the period: In_Reporting_Year__c equals true, on the reports, and 2026 only
        self.assertTrue([s for s in cl if re.search(r"(?i)\b(reports?|items?|filters?|period)\b", s)
                         and [m for m in self.YEAR_ON.finditer(s) if not self.d.locally_denied(s, m)]],
                        f"{where}: say the reports' period filter is `In_Reporting_Year__c equals true` (#195), in place "
                        "of `Period__c equals LAST_N_MONTHS:12` (one sentence naming the reports or the filter, not "
                        "negated)")
        self.assertTrue([s for s in cl if [m for m in self.ONE_YEAR.finditer(s) if not self.d.locally_denied(s, m)]],
                        f"{where}: say D1 and its reports show 2026 only, no 2025 month (one sentence)")
        for s in cl:            # the last 12 months stays only as history
            if not self.PERIOD_TALK.search(s):
                continue
            for m in self.OLD_PERIOD.finditer(s):
                self.assertTrue(self.history(s, m),
                                f"{where}: since #196 the period is `In_Reporting_Year__c`; the last 12 months "
                                f"({m.group(0)!r}) is said only as what it replaced (\"until #196\", \"was\", "
                                f"\"in place of\"): {s[:200]!r}")
        # the Month filter on DHIS2__c$Month__c, and nothing left that denies it or makes Partner Manager the only one
        month = [s for s in cl if self.MONTH_FIELD.search(s)
                 and [m for m in self.MONTH_FILTER.finditer(s)
                      if not (self.d.locally_denied(s, m) or self.d.NEGATION.search(m.group(0)))]]
        self.assertTrue(month, f"{where}: say D1 has a Month filter on `DHIS2__c$Month__c` (one sentence naming the "
                               "filter and the field, not negated)")
        for s in cl:
            for m in self.NO_MONTH.finditer(s):
                self.assertTrue(self.history(s, m),
                                f"{where}: D1 has a Month filter since #196; \"no Month filter\" is said only as "
                                f"history (\"until #196 it had no Month filter\"): {s[:200]!r}")
            if s in month:
                continue
            for m in self.ONLY_PM.finditer(s):
                self.assertTrue(self.history(s, m),
                                f"{where}: Partner Manager is no longer D1's only filter (Month is the other); say "
                                f"it only as history: {s[:200]!r}")

    def test_the_runbook_says_totals_are_off_and_why(self):
        where = f"RUNBOOK {AttendanceDashboardDocs.PART!r}"
        reports, _ = self.reports()
        part = self.a.part()
        units = self.own_units(part)

        def off(u):
            """The sentences of unit `u` that take a total off, not denied."""
            out = []
            for s in sentences(self.norm(u), ".;"):
                if not self.TOTAL.search(s):
                    continue
                if [m for m in self.OFF.finditer(s) if not self.d.locally_denied(s, m)]:
                    out.append(s)
            return out
        r3 = reports["3"]
        self.assertTrue([u for u in self.unit_for(units, "3", reports) if off(u)],
                        f"{where}: say item 3 ({r3['label_today']!r}) shows no grand total any more (`showGrandTotal` "
                        "false), in a row, list item or paragraph of its own (naming it first, no other item)")
        r4 = reports["4"]
        self.assertTrue([u for u in self.unit_for(units, "4", reports)
                         if [s for s in off(u) if re.search(r"(?i)\bMonthly Max\b|\bMonthly_Total__c\b", s)]],
                        f"{where}: say item 4's table ({r4['label_today']!r}) shows no total row, the Sum Monthly Max "
                        "total included (`showTotal` false on every column), in one sentence of a row, list item or "
                        "paragraph of its own (naming it first, no other item)")
        cl = sentences(self.norm(part), ".;")
        self.assertTrue([s for s in cl if self.TOTAL.search(s)
                         and [m for m in self.DOUBLE.finditer(s) if not self.d.locally_denied(s, m)]],
                        f"{where}: say why the totals are off: adding the weekly or monthly counts double-counts girls "
                        "who attend several sessions, so a total is not the number of unique girls (one sentence "
                        "naming the totals)")
        for s in cl:            # a total kept is said only as the past, marked before it ("until #196 it showed")
            for m in self.TOTAL_ON.finditer(s):
                self.assertTrue(self.HISTORY.search(s[max(0, m.start() - 50):m.start()]) or self.d.locally_denied(s, m)
                                or self.d.NEGATION.search(m.group(0)),
                                f"{where}: the totals are off since #196; no sentence keeps one on: {s[:200]!r}")

    # --- the plan -------------------------------------------------------------------------------------------

    def test_the_plan_has_rollout_rollback_and_result(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        name = os.path.relpath(self.PLAN, REPO)
        self.assertTrue(os.path.isfile(self.PLAN), f"{name}: no plan for ticket #196 (Rollout, Rollback, Result)")
        reports, dash = self.reports()
        text = read(self.PLAN)
        keys, _ = docs_index.frontmatter(text)
        self.assertIn("status", keys, f"{name}: frontmatter `status:`")
        _, problem = docs_index.status_of(keys["status"])
        self.assertIsNone(problem, f"{name}: {problem}")
        self.assertRegex(text.split("\n## ", 1)[0], self.TICKET,
                         f"{name}: name ticket #196 in the frontmatter, the title or the opening paragraph")
        self.assertRegex(text, r"(?m)^## Result\b", f"{name}: no `## Result` section")
        self.assertNotRegex(text, self.EMAIL, f"{name}: counts, ids and names of reports and partners only, no address")

        raw = self.a.plan_part(self.PLAN, "## Rollout", 40)
        where = f"{name}: `## Rollout`"
        cl = sentences(self.norm(raw), ".;")
        for item, r in sorted(reports.items()):
            self.assertIn(r["id"], raw, f"{where}: name item {item}'s report {r['label_today']!r} by its Id {r['id']} "
                                        "(its copy to Decommissioned)")
        self.assertIn(dash["id"], raw, f"{where}: name the dashboard {dash['label_today']!r} by its Id {dash['id']}")
        # the copies: by the tool, VPN off, tagged with the ticket, into Decommissioned, on Ryan's go
        segments = re.split(r"`+|\n\s*\n|\n(?=\s*(?:\$\s*)?python3\s)|(?=\bpython3\s)", raw)
        copies = [flat(s) for s in segments if re.search(r"\bsf_report_folders\.py\s+copy\b", s)]
        self.assertTrue(copies, f"{where}: give the copies' command, `python3 tools/sf_report_folders.py copy --vpn-off "
                                "--kind report --id <id> --tag \"#196\"`")
        for c in copies:
            self.assertIn("--vpn-off", c, f"{where}: the tool refuses to run without `--vpn-off`: {c[:160]!r}")
            self.assertRegex(c, r"--tag[ =]\\?[\"“']?#196\b", f"{where}: each copy carries the ticket, `--tag \"#196\"`: "
                                                             f"{c[:160]!r}")
        self.assertTrue([s for s in cl if re.search(r"(?i)\bcop(y|ies)\b", s) and "Decommissioned" in s
                         and not self.d.denies(s)],
                        f"{where}: the copies go to Decommissioned before the change (one sentence)")
        self.assertTrue([s for s in cl if re.search(r"(?i)\b(dashboard|D1)\b", s) and re.search(r"(?i)\bdynamic\b", s)
                         and re.search(r"(?i)\brefus\w*\b|\bno\s+(API\s+)?cop(y|ies)\b|\bnot\s+(be\s+)?copied\b|"
                                       r"\bcan(not|['’]t)\s+be\s+copied\b", s)],
                        f"{where}: say D1 gets no Decommissioned copy because it is dynamic (the org is at 5), so "
                        "`before/` is its rollback (one sentence)")
        self.assertTrue([s for s in cl if self.a.said(s, self.GO) and re.search(r"(?i)\bcop(y|ies)\b|--apply", s)],
                        f"{where}: the copies wait for Ryan's go (one sentence, not negated)")
        self.assertTrue([s for s in cl if self.a.said(s, self.GO) and re.search(r"(?i)\bdeploy", s)
                         and not re.search(r"(?i)\bcheck-only\b", s)],
                        f"{where}: the deploy waits for Ryan's go (one sentence, not negated, apart from the check-only)")
        self.assertTrue([s for s in cl if "after/" in s and "build/" in s
                         and re.search(r"(?i)\b(compar\w*|equals?|differ\w*|diff)\b", s)],
                        f"{where}: the read-back retrieves into `after/` and compares it with `build/` (one sentence)")
        # the order, in the numbered steps: before/, copies, check-only, deploy, after/
        steps = self.c.steps(raw, where)
        before = self.c.first(r"\bbefore/", steps, where, "the steps start from a fresh retrieve into `before/`")
        copy_at = [m.start() for m in re.finditer(r"\bsf_report_folders\.py\s+copy\b", steps)]
        self.assertTrue(copy_at, f"{where}: the copies are a numbered step")
        self.assertLess(before, copy_at[0], f"{where}: the `before/` retrieve comes before the copies")
        check_only = [m.start() for m in re.finditer(r"(?i)\bcheck-only\b|--dry-run\b", steps) if m.start() > copy_at[-1]]
        self.assertTrue(check_only, f"{where}: the check-only deploy comes after every copy (copy first, then change)")
        deploys, at = [], 0
        for piece in sentences(steps, ".;,"):
            at = steps.find(piece, at)
            m = re.search(r"(?i)\b(re-?)?deploy\w*", piece)
            # a check-only is no deploy; "deploy ... without `--dry-run`" is one
            if not m or re.search(r"(?i)check-only|(?<!without )(?<!without `)--dry-run|\bvalidat", piece) \
                    or self.d.locally_denied(piece, m) \
                    or re.search(r"(?i)\b(before|until|ahead of|prior to|after|once)\b[^.;,]{0,25}$", piece[:m.start()]) \
                    or re.search(r"(?i)\b(in|at|from)\s+step\s+\d", piece):
                continue
            self.assertGreater(at, check_only[0], f"{where}: nothing is deployed before the check-only (and the "
                                                  f"copies): {piece[:160]!r}")
            deploys.append(at)
        self.assertTrue(deploys, f"{where}: the deploy is a step after the check-only (on Ryan's go)")
        self.assertTrue([m for m in re.finditer(r"\bafter/", steps) if m.start() > deploys[0]],
                        f"{where}: the `after/` read-back comes after the deploy")

        # the rollback: the reports and D1 restored by a deploy, from a fresh retrieve edited back or from #196's
        # own `before/` while a fresh retrieve equals `after/`; the Decommissioned copies are the record of what the
        # reports were, never the restore on their own (D1's components point at the reports themselves)
        raw = self.a.plan_part(self.PLAN, "## Rollback", 15)
        where = f"{name}: `## Rollback`"
        cl = sentences(self.norm(raw), ".;")
        units = [self.norm(u) for u in self.own_units(raw)]
        reports_unit = [u for u in units if self.REPORTS.search(u) and self.deployed(u) and self.deploy_source(u)]
        self.assertTrue(reports_unit,
                        f"{where}: say the reports of items 1, 3 and 4 are restored by a deploy (after a check-only) "
                        "from a fresh retrieve edited back where #196 changed it, or from their files in #196's "
                        "`before/` only while a fresh retrieve equals `after/`, in one list item or paragraph; their "
                        "copies in Decommissioned are the record, not the restore")
        d1_unit = [u for u in units if re.search(r"(?i)\b(dashboard|D1)\b", u) and self.deployed(u)
                   and self.deploy_source(u)]
        self.assertTrue(d1_unit,
                        f"{where}: say D1 is restored by a deploy of its own file in #196's `before/` only while a "
                        "fresh retrieve equals `after/` (or a fresh retrieve edited back), in one list item or "
                        "paragraph, not negated")
        self.assertTrue([s for s in cl if re.search(r"(?i)\b(never|not|no)\b[^.;]{0,60}?\b(older|old|earlier|previous|"
                                                    r"stale)\s+(\w+\s+)?(build|retrieve)\b", s)],
                        f"{where}: say never from an older build or retrieve (DECISIONS 2026-10-16), in one sentence")
        # ... and no older source stands for D1 or the reports, in the plan or in the RUNBOOK's rollback of #196
        self.assertNoOldSource(raw, where)
        self.assertNoOldSource(self.runbook_rollback(), f"RUNBOOK {AttendanceDashboardDocs.PART!r}, Rollback of #196")


class GlowReviewImplementationDocs(unittest.TestCase):
    """Ticket #197 (epic #194, GLOW's review of 2026-11-02): D2 "Implementation Dashboard" and its items 5-8 show
    the reporting year only, `In_Reporting_Year__c equals true` (#195) in place of `LAST_N_MONTHS:12`, and D2 gains
    a Month filter on `DHIS2__c$Month__c` (and `Attendance_Batch__c$Month_Name__c` for item 6). Item 6, GLOW: "the
    total number of partners that implemented each module as opposed to the number of clubs", a horizontal bar;
    Ryan, 2026-11-02: modules from September 2026 onward, from Jotform, because January-August 2026 has no module
    data (the Monthly Report's module question has no answers after September 2025). The RUNBOOK's `### GLOW Club
    Implementation` says so, with the old rules (the last 12 months, no Month filter, Partner Manager the only filter)
    only as history. `glow/sf_keep_list.csv` carries GLOW's names for items 5-7, every report label within 40
    characters. The plan `docs/plans/2026-11-02-sf-review-implementation.md` carries the copies to Decommissioned,
    the check-only, Ryan's go, the deploy, the read-back and the SOQL check, in that order, a Rollback and a
    `## Result`. The wording is free: each rule is looked for as a claim in a sentence or unit, not denied."""

    longMessage = False         # the messages say what to fix
    KEEP_LIST = os.path.join(REPO, "glow", "sf_keep_list.csv")
    PLAN = os.path.join(REPO, "docs", "plans", "2026-11-02-sf-review-implementation.md")
    TICKET = re.compile(r"(?<![\w#])#197\b")
    # GLOW's names (ticket #197, Outline step 4): report labels within Salesforce's 40 characters
    NAMES = {"5": "Club Implementation by Month and Partner",
             "6": "Modules Implemented by Month and Partner",
             "7": "Modules Adapted by Month and Partner"}
    # item 6's report in the org since #76 (RUNBOOK; the keep list keeps the id #70 recorded, now in Decommissioned)
    ITEM_6_REPORT = "00ORP000009kUNh2AM"
    GO = re.compile(r"Ryan['’]s go\b")
    EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}")
    YEAR_ON = ImplementationDashboardDocs.YEAR_ON
    # 2026 only, 2025 out ("2026 only", "only 2026", "no 2025 month", "2025 is left out", "the reporting year only")
    ONE_YEAR = re.compile(r"(?i)\b2026\s+only\b|\bonly\s+(\w+\s+){0,3}?2026\b|\bno\s+(\w+\s+){0,3}?2025\b|"
                          r"\b2025\b[^.;]{0,40}?\b(excluded|left out|out|off|gone|dropped|hidden)\b|"
                          r"\breporting year only\b|\bonly\s+(the\s+)?(current\s+)?reporting year\b")
    # the old period, said as today's rule when no history marker is near it
    OLD_PERIOD = re.compile(r"\bLAST_N_MONTHS:12\b|(?i:\blast\s+(12|twelve)\s+months\b)")
    PERIOD_TALK = re.compile(r"(?i)Period__c|Attendance_Date__c|\bperiod\b|\bdate filter\b|\bfield filter\b|"
                             r"\breports?['’]? filters?\b")
    HISTORY = re.compile(r"(?i)\b(was|were|had|until|before|formerly|former|no longer|previously|used to|replac\w*|"
                         r"in place of|instead of|became|becomes|rather than|superseded|gave way)\b")
    MONTH_FILTER = re.compile(r"(?i)\bMonth\b[\"”'’`]?\s*(\([^)]{0,60}\)\s*)?(dashboard\s+)?filters?\b|"
                              r"\bfilter(s|ed|ing)?\s+(on|by|for)\s+(the\s+|a\s+|each\s+)?[`\"“]?(DHIS2__c\$)?"
                              r"Month(__c)?\b")
    NO_MONTH = re.compile(r"(?i)\b(no|not|without|neither|nor|never)\b[^.;]{0,25}?\bMonth\b[^.;]{0,20}?\bfilters?\b")
    ONLY_PM = re.compile(r"(?i)\b(only|one|sole|single)\b[^.;]{0,30}?\bfilter\b[^.;]{0,40}?\bPartner Manager\b")
    # item 6's measure: each partner counted once per module
    PARTNERS = re.compile(r"(?i)\b(unique|distinct|different)\s+partners\b|\bnumber\s+of\s+(unique\s+|distinct\s+)?"
                          r"partners\b|\bpartners\s+(that|who|which)\s+(have\s+)?implemented\b|\bhow\s+many\s+partners\b|"
                          r"\bonce\s+per\s+partner\b|\beach\s+partner\s+(is\s+)?counted\s+once\b")
    NOT_CLUBS = re.compile(r"(?i)\b(not|never|rather\s+than|instead\s+of|as\s+opposed\s+to|in\s+place\s+of)\b"
                           r"[^.;]{0,40}?\b(clubs?|batch(es)?)\b")
    # the #76 measure said as today's: "counts the Jotform batches", "counts clubs"
    OLD_COUNT = re.compile(r"(?i)\bcount(s|ed|ing)?\s+(the\s+)?(number\s+of\s+)?(Jotform\s+)?(batches|clubs|sessions)\b")
    HBAR = re.compile(r"(?i)\bhorizontal\s+bar")
    MODULE = re.compile(r"(?i)\bmodules?\b|Module__c|\bitem\s+6\b")
    # the data gap: January-August 2026 (or before September 2026) has no module data ...
    GAP_MONTHS = re.compile(r"(?i)\bJan(uary)?\b\W{0,3}(to|through|until|-|–|—)\W{0,3}Aug(ust)?\b[^.;]{0,15}?\b2026\b|"
                            r"\b(before|until|ahead of|prior to)\s+September\s+2026\b|\b(before|until)\s+2026-09-01\b")
    GAP_NONE = re.compile(r"(?i)\b(no|none|nothing|blank|empty|without|missing|gap)\b")
    # ... and from September 2026 the modules come from Jotform
    FROM_SEPT = re.compile(r"(?i)\b(from|since|starting|beginning|on\s+or\s+after)\s+(\w+\s+){0,2}?September\b(?!\s+2025)|"
                           r"\bSeptember\b(?!\s+2025)[^.;]{0,30}?\bonwards?\b|\b(from|since|on\s+or\s+after)\s+2026-09-01\b")
    # what a "2026 only" sentence is about: D2, the dashboard, its reports, a component, items 5-8
    SHOWN = re.compile(r"(?i)\b(D2|dashboards?|components?)\b|\b(its|the|their|D2['’]s|four|all)\s+reports\b|"
                       r"\bitems?\s+[5-8]\b")

    # --- the rollback (review of #197): the reports and D2 restored by a deploy, never from the copies --------
    # the reports in a rollback unit ("the reports", "each report's deploy", "items 5, 6, 7 and 8")
    REPORTS = re.compile(r"(?i)\breports?\b|\bitems?\s+(\d+\s*(,|and|&)\s*)*[5-8]\b")
    DEPLOY = re.compile(r"(?i)\b(re-?)?deploy\w*\b")
    # a deploy's sources: a fresh retrieve edited back, or `before/` guarded by a fresh retrieve that equals `after/`
    EDITED_BACK = re.compile(r"(?i)\bfresh\s+retriev\w*\b[^.;]{0,40}?\bedit\w*\s+back\b")
    GUARD = re.compile(r"(?i)\b(only|while|as long as|so long as|provided)\b[^.;]{0,30}?\bfresh\s+retriev\w*\b[^.;]{0,40}?"
                       r"\b(equals?|matches|match|is the same as|identical to)\b[^.;]{0,20}?\bafter/")
    # an old source: another change's data/ folder, any build/, an older build or retrieve, another ticket's
    # before/ or build ("#76's `before/`"); #197's own `data/sf_glow_review_<month>/` and a fresh retrieve are its sources
    OLD_SOURCE = re.compile(r"(?i)\bdata/sf_(?!glow_review_)[\w-]+/|\bbuild/|"
                            r"\b(older|old|earlier|previous|prior|stale|another|other|original)\s+([\w-]+\s+)?"
                            r"(retrieves?|builds?|backups?|exports?|snapshots?|versions?)\b|"
                            r"#(?!197\b)\d+['’]s\s+`?(before/|build/|retrieve|build)")
    # a restore from the Decommissioned copies ("Save As", "move a copy back", "restored from their copies", "point
    # D2's component at the copy")
    COPY_RESTORE = re.compile(r"(?i)\bSave\s+As\b|\b(move|moves|moved|moving|put|puts|bring|brings)\s+(a|the|each|its|"
                              r"their|that)\s+cop(y|ies)\s+back\b|\bopen\s+(a|the|its|each|their)\s+cop(y|ies)\b|"
                              r"\bpoint\w*\s+(\w+\s+){0,4}?at\s+(a|the|its|their|that)\s+cop(y|ies)\b|"
                              r"\bfrom\s+(a|the|their|its|each|that)\s+(\w+\s+)?cop(y|ies)\b")
    RESTORE = re.compile(r"(?i)\brestor\w*|\broll(s|ed|ing)?\s+(\w+\s+)?back\b|\brollback\b|\brevert\w*|"
                         r"\b(come|comes|came|go|goes|brought|bring|brings|put|puts)\s+back\b|\bre-?deploy\w*|\bdeploy\w*")

    @classmethod
    def setUpClass(cls):
        ImplementationDashboardDocs.setUpClass()
        cls.i = ImplementationDashboardDocs()   # #76's helpers: part, blocks, units, mentions, soql, batch_ok
        cls.d = cls.i.d                         # #69's helpers: locally_denied, denies, NEGATION

    @staticmethod
    def norm(text):
        return DecommissionedFoldersDocs.norm(text)

    @staticmethod
    def prose(s):
        """Clause `s` without its backticked SOQL statements: a query is a check, not a claim."""
        return re.sub(r"`[^`]*\bSELECT\b[^`]*`", " ", s)

    def stated(self, s, rx):
        return any(not self.d.locally_denied(s, m) for m in rx.finditer(s))

    def history(self, s, m):
        """Match `m` of `s` said as the past or as what was replaced: a marker in the 50 characters before it or
        the 30 after, or a denial."""
        return bool(self.HISTORY.search(s[max(0, m.start() - 50):m.end() + 30]) or self.d.locally_denied(s, m))

    def denied_before(self, s, m):
        """A negation in clause `s` before match `m`, back to the last comma, semicolon, dash, "but", "however",
        "then" or "otherwise" and at most 160 characters: "never from #76's `build/`", "not from their copies".
        A denial after the match ("#76's folder is no rollback") does not count."""
        pre = re.split(r"[,;—–]|\bbut\b|\bhowever\b|\bthen\b|\botherwise\b", s[max(0, m.start() - 160):m.start()])[-1]
        return bool(self.d.NEGATION.search(pre))

    def deployed(self, u):
        """A sentence of unit `u` that restores by a deploy, not denied."""
        return any(self.stated(s, self.DEPLOY) for s in sentences(u, ".;"))

    def deploy_source(self, u):
        return bool(self.EDITED_BACK.search(u) or ("before/" in u and self.GUARD.search(u)))

    def assertRollbackSources(self, raw, where):
        """No old source (another change's data/ folder, a `build/`, an older build or retrieve), no restore from
        the Decommissioned copies, unless denied before the match; `before/` never redeployed "even if" or when a
        fresh retrieve differs from `after/`."""
        for s in sentences(self.norm(raw), ".;"):
            for m in self.OLD_SOURCE.finditer(s):
                self.assertTrue(self.denied_before(s, m),
                                f"{where}: #197's rollback deploys a fresh retrieve edited back or #197's own `before/`, "
                                f"never {m.group(0)!r} (DECISIONS 2026-10-16); deny it before naming it (\"never from "
                                f"#76's `build/`\"): {s[:200]!r}")
            for m in self.COPY_RESTORE.finditer(s):
                self.assertTrue(self.denied_before(s, m),
                                f"{where}: the reports come back by a deploy, not from their copies in Decommissioned "
                                f"(D2's components point at the reports themselves); the copies are the record "
                                f"({m.group(0)!r}): {s[:200]!r}")
            if "before/" not in s:
                continue
            self.assertFalse(self.i.EVEN.search(s), f"{where}: `before/` is deployed only while a fresh retrieve equals "
                                                    f"`after/`, never \"even if\" or \"regardless\": {s[:200]!r}")
            diff = [m for m in self.i.DIFFERS.finditer(s) if not self.d.locally_denied(s, m)]
            redo = [m for m in self.RESTORE.finditer(s) if not self.d.locally_denied(s, m)]
            self.assertFalse(diff and redo, f"{where}: `before/` is never deployed when a fresh retrieve differs from "
                                            f"`after/` (stop and ask instead): {s[:200]!r}")

    def keep_rows(self):
        import csv
        self.assertTrue(os.path.isfile(self.KEEP_LIST), "glow/sf_keep_list.csv: missing")
        with open(self.KEEP_LIST, encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    # --- the RUNBOOK ----------------------------------------------------------------------------------------

    def test_the_runbook_says_modules_count_unique_partners_from_september(self):
        where = f"RUNBOOK {ImplementationDashboardDocs.PART!r}"
        part = self.i.part()
        rows = self.i.reports()
        six = [r for r in rows if r["item"] == "6"]
        blocks = [b for b in self.i.blocks(part) if self.i.mentions(six, b)]
        self.assertTrue(blocks, f"{where}: item 6 ({six[0]['measure']!r}) has its own row, list item or paragraph")
        cl6 = [self.prose(s) for b in blocks for s in sentences(self.norm(b), ".;")]
        # the measure: unique partners per module, not clubs or batches, a horizontal bar
        self.assertTrue([s for s in cl6 if self.stated(s, self.PARTNERS) and self.MODULE.search(s)],
                        f"{where}, item 6: say it counts the unique partners that implemented each module (GLOW: \"the "
                        "total number of partners that implemented each module\"), in a sentence of its own row, list "
                        "item or paragraph, not negated")
        self.assertTrue([s for s in cl6 if self.NOT_CLUBS.search(s) and re.search(r"(?i)\bpartners?\b|\bcount", s)],
                        f"{where}, item 6: say the count is of partners, not of clubs or batches (GLOW: \"as opposed to "
                        "the number of clubs\"), in one sentence")
        for s in cl6:
            for m in self.OLD_COUNT.finditer(s):
                self.assertTrue(self.history(s, m),
                                f"{where}, item 6: since #197 it counts unique partners; counting the batches or clubs "
                                f"({m.group(0)!r}) is said only as history (\"until #197\", \"was\", \"instead of\"): "
                                f"{s[:200]!r}")
        self.assertTrue([s for s in cl6 if self.stated(s, self.HBAR)],
                        f"{where}, item 6: say its component is a horizontal bar, one bar per module (not negated)")
        # its SOQL signal: unique partners (the club's parent) by module, from September 2026
        batch = self.i.soql(part, "Attendance_Batch__c")

        def from_september(q):
            terms, _ = self.i.where_terms(q)
            return (self.i.has_term(terms, r"(?i)Attendance_Date__c\s*(>=?|=)\s*2026-09-\d\d")
                    or self.i.has_term(terms, r"(?i)Month_Name__c\s*=\s*'September'"))
        self.assertTrue([q for q in batch if self.i.batch_ok(q) and from_september(q)
                         and re.search(r"(?i)\bCOUNT_DISTINCT\s*\(\s*Account__r\.Parent(Id|\.Id)\s*\)", q)],
                        f"{where}, item 6: give its SOQL signal, `SELECT Module__c, COUNT_DISTINCT(Account__r.ParentId) "
                        "FROM Attendance_Batch__c WHERE Processing_Status__c = 'Success' AND Creator__c LIKE 'Jotform%' "
                        "AND In_Reporting_Year__c = true AND Attendance_Date__c >= 2026-09-01 GROUP BY Module__c` (AND-"
                        "joined, no OR; from September 2026)")
        # the data gap, in the part: no module data January-August 2026; from September, from Jotform
        cl = [self.prose(s) for s in sentences(self.norm(part), ".;")]
        self.assertTrue([s for s in cl if self.GAP_MONTHS.search(s) and self.GAP_NONE.search(s)
                         and self.MODULE.search(s)],
                        f"{where}: say January-August 2026 has no module data (the Monthly Report's module question has "
                        "no answers after September 2025), in one sentence naming the modules")
        self.assertTrue([s for s in cl if self.stated(s, self.FROM_SEPT) and re.search(r"(?i)\bJotform\b", s)
                         and self.MODULE.search(s)],
                        f"{where}: say the modules count from September 2026 onward, from Jotform, in one sentence")
        # the reporting year in place of the last 12 months, 2026 only
        self.assertTrue([s for s in cl if re.search(r"(?i)\b(reports?|items?|filters?|period)\b", s)
                         and self.stated(s, self.YEAR_ON)],
                        f"{where}: say D2's reports filter `In_Reporting_Year__c equals true` (#195) in place of "
                        "`LAST_N_MONTHS:12` (one sentence naming the reports or the filter, not negated)")
        # said of D2, its reports or a component, never only the data gap's "no answers after September 2025"
        self.assertTrue([s for s in cl if self.stated(s, self.ONE_YEAR) and self.SHOWN.search(s)
                         and not self.GAP_MONTHS.search(s)],
                        f"{where}: say D2 and its reports show 2026 only, no 2025 month (one sentence naming D2, the "
                        "dashboard, its reports or a component; the data gap's sentence does not count)")
        for s in cl:
            if not self.PERIOD_TALK.search(s):
                continue
            for m in self.OLD_PERIOD.finditer(s):
                self.assertTrue(self.history(s, m),
                                f"{where}: since #197 the period is `In_Reporting_Year__c`; the last 12 months "
                                f"({m.group(0)!r}) is said only as what it replaced (\"until #197\", \"was\", "
                                f"\"in place of\"): {s[:200]!r}")
        # the Month filter on both report types, and nothing left that denies it or makes Partner Manager the only one
        month = []
        for field in (r"DHIS2__c\$Month__c\b", r"Attendance_Batch__c\$Month_Name__c\b"):
            found = [s for s in cl if re.search(field, s)
                     and [m for m in self.MONTH_FILTER.finditer(s)
                          if not (self.d.locally_denied(s, m) or self.d.NEGATION.search(m.group(0)))]]
            self.assertTrue(found, f"{where}: say D2 has a Month filter on `DHIS2__c$Month__c` and, for item 6, "
                                   f"`Attendance_Batch__c$Month_Name__c` (a sentence naming the filter and "
                                   f"`{field[:-2].replace(chr(92), '')}`, not negated)")
            month += found
        for s in cl:
            for m in self.NO_MONTH.finditer(s):
                self.assertTrue(self.history(s, m),
                                f"{where}: D2 has a Month filter since #197; \"no Month filter\" is said only as "
                                f"history (\"until #197 it had no Month filter\"): {s[:200]!r}")
            if s in month:
                continue
            for m in self.ONLY_PM.finditer(s):
                self.assertTrue(self.history(s, m),
                                f"{where}: Partner Manager is no longer D2's only filter (Month is the other); say it "
                                f"only as history: {s[:200]!r}")

    # --- the keep list --------------------------------------------------------------------------------------

    def test_the_keep_list_carries_glows_names_within_40_characters(self):
        rows = self.keep_rows()
        reports = [r for r in rows if r["kind"] in ("report", "table")]
        self.assertEqual(len(reports), 19, f"glow/sf_keep_list.csv: 19 report rows (items 1-19), found {len(reports)}")
        bad = [(r["item"], r["label_target"], len(r["label_target"])) for r in reports
               if not r["label_target"].strip() or len(r["label_target"]) > 40]
        self.assertEqual(bad, [], "glow/sf_keep_list.csv: every report's label_target is 1-40 characters (Salesforce's "
                                  f"limit on a report's name); (item, label_target, length): {bad}")
        by = {r["item"]: r for r in rows}
        for item, name in sorted(self.NAMES.items()):
            where = f"glow/sf_keep_list.csv item {item}"
            self.assertIn(item, by, f"{where}: no row")
            row = by[item]
            self.assertEqual((row["group"], row["kind"]), ("GLOW Club Implementation", "report"),
                             f"{where}: still a report of 'GLOW Club Implementation'")
            self.assertEqual(row["label_target"], name,
                             f"{where}: label_target is GLOW's name {name!r} (GLOW's review, 2026-11-02; ticket #197), "
                             f"not {row['label_target']!r}")

    # --- the plan -------------------------------------------------------------------------------------------

    def test_the_plan_has_rollout_rollback_and_result(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        name = os.path.relpath(self.PLAN, REPO)
        self.assertTrue(os.path.isfile(self.PLAN), f"{name}: no plan for ticket #197 (Rollout, Rollback, Result)")
        reports = {r["item"]: r for r in self.i.reports()}
        dash = self.i.dashboard()
        text = read(self.PLAN)
        keys, _ = docs_index.frontmatter(text)
        self.assertIn("status", keys, f"{name}: frontmatter `status:`")
        _, problem = docs_index.status_of(keys["status"])
        self.assertIsNone(problem, f"{name}: {problem}")
        self.assertRegex(text.split("\n## ", 1)[0], self.TICKET,
                         f"{name}: name ticket #197 in the frontmatter, the title or the opening paragraph")
        self.assertRegex(text, r"(?m)^## Result\b", f"{name}: no `## Result` section")
        self.assertNotRegex(text, self.EMAIL, f"{name}: counts, ids and names of reports and partners only, no address")

        raw = self.i.plan_part(self.PLAN, "## Rollout", 40)
        where = f"{name}: `## Rollout`"
        flat_out = flat(raw)
        cl = sentences(self.norm(raw), ".;")
        self.assertRegex(flat_out, r"(?i)\bVPN off\b|--vpn-off", f"{where}: VPN off before any `sf` call")
        self.assertRegex(flat_out, r"data/sf_glow_review_\d{4}-\d\d/[\w<>-]+/before/",
                         f"{where}: retrieve live into `data/sf_glow_review_2026-11/<topic>/before/` (epic #194)")
        # the four reports D2 shows today: items 5, 7 and 8 by the keep list's ids, item 6 by #76's report
        ids = {"5": reports["5"]["id"], "6": self.ITEM_6_REPORT, "7": reports["7"]["id"], "8": reports["8"]["id"]}
        for item, sf_id in sorted(ids.items()):
            self.assertIn(sf_id, raw, f"{where}: name item {item}'s report by its Id {sf_id} (its copy to "
                                      "Decommissioned)")
        self.assertIn(dash["id"], raw, f"{where}: name the dashboard {dash['label_today']!r} by its Id {dash['id']}")
        # the copies: by the tool, VPN off, tagged with the ticket, into Decommissioned, on Ryan's go
        segments = re.split(r"`+|\n\s*\n|\n(?=\s*(?:\$\s*)?python3\s)|(?=\bpython3\s)", raw)
        copies = [flat(s) for s in segments if re.search(r"\bsf_report_folders\.py\s+copy\b", s)]
        self.assertTrue(copies, f"{where}: give the copies' command, `python3 tools/sf_report_folders.py copy --vpn-off "
                                "--kind report --id <id> --tag \"#197\"`")
        for c in copies:
            self.assertIn("--vpn-off", c, f"{where}: the tool refuses to run without `--vpn-off`: {c[:160]!r}")
            self.assertRegex(c, r"--tag[ =]\\?[\"“']?#197\b", f"{where}: each copy carries the ticket, `--tag \"#197\"`: "
                                                             f"{c[:160]!r}")
        self.assertTrue([s for s in cl if re.search(r"(?i)\bcop(y|ies)\b", s) and "Decommissioned" in s
                         and not self.d.denies(s)],
                        f"{where}: the copies go to Decommissioned before the change (one sentence)")
        self.assertTrue([s for s in cl if re.search(r"(?i)\b(dashboard|D2)\b", s) and re.search(r"(?i)\bdynamic\b", s)
                         and re.search(r"(?i)\brefus\w*\b|\bno\s+(API\s+)?cop(y|ies)\b|\bnot\s+(be\s+)?copied\b|"
                                       r"\bcan(not|['’]t)\s+be\s+copied\b", s)],
                        f"{where}: say D2 gets no Decommissioned copy because it is dynamic (the org is at 5), so "
                        "`before/` is its rollback (one sentence)")
        self.assertTrue([s for s in cl if self.stated(s, self.GO) and re.search(r"(?i)\bcop(y|ies)\b|--apply", s)],
                        f"{where}: the copies wait for Ryan's go (one sentence, not negated)")
        self.assertTrue([s for s in cl if self.stated(s, self.GO) and re.search(r"(?i)\bdeploy", s)
                         and not re.search(r"(?i)\bcheck-only\b", s)],
                        f"{where}: the deploy waits for Ryan's go (one sentence, not negated, apart from the check-only)")
        self.assertTrue([s for s in cl if "after/" in s and "build/" in s
                         and re.search(r"(?i)\b(compar\w*|equals?|differ\w*|diff)\b", s)],
                        f"{where}: the read-back retrieves into `after/` and compares it with `build/` (one sentence)")
        # the order, in the numbered steps: before/, copies, check-only, deploy, after/, SOQL
        steps = CategoryFoldersDocs.steps(self, raw, where)
        before = CategoryFoldersDocs.first(self, r"\bbefore/", steps, where,
                                           "the steps start from a fresh retrieve into `before/`")
        copy_at = [m.start() for m in re.finditer(r"\bsf_report_folders\.py\s+copy\b", steps)]
        self.assertTrue(copy_at, f"{where}: the copies are a numbered step")
        self.assertLess(before, copy_at[0], f"{where}: the `before/` retrieve comes before the copies")
        check_only = [m.start() for m in re.finditer(r"(?i)\bcheck-only\b|--dry-run\b", steps) if m.start() > copy_at[-1]]
        self.assertTrue(check_only, f"{where}: the check-only deploy comes after every copy (copy first, then change)")
        deploys, at = [], 0
        for piece in sentences(steps, ".;,"):
            at = steps.find(piece, at)
            m = re.search(r"(?i)\b(re-?)?deploy\w*", piece)
            # a check-only is no deploy; "deploy ... without `--dry-run`" is one
            if not m or re.search(r"(?i)check-only|(?<!without )(?<!without `)--dry-run|\bvalidat", piece) \
                    or self.d.locally_denied(piece, m) \
                    or re.search(r"(?i)\b(before|until|ahead of|prior to|after|once)\b[^.;,]{0,25}$", piece[:m.start()]) \
                    or re.search(r"(?i)\b(in|at|from)\s+step\s+\d", piece):
                continue
            self.assertGreater(at, check_only[0], f"{where}: nothing is deployed before the check-only (and the "
                                                  f"copies): {piece[:160]!r}")
            deploys.append(at)
        self.assertTrue(deploys, f"{where}: the deploy is a step after the check-only (on Ryan's go)")
        self.assertTrue([m for m in re.finditer(r"\bafter/", steps) if m.start() > deploys[0]],
                        f"{where}: the `after/` read-back comes after the deploy")
        self.assertTrue([m for m in re.finditer(r"\bSOQL\b|\bSELECT\b|\bCOUNT_DISTINCT\b", steps) if m.start() > deploys[0]],
                        f"{where}: the SOQL check (each component against SOQL) comes after the deploy")

        # the rollback: the reports from their copies, D2 from this change's before/, the new reports to
        # Decommissioned, never an older build. Review of #197: the reports and D2 come back by a deploy (D2's
        # components point at the reports themselves, so a copy saved back would be a separate report D2 does not
        # show), from a fresh retrieve edited back or from #197's own `before/` only while a fresh retrieve equals
        # `after/`; the Decommissioned copies are the record of what the reports were, never the restore.
        raw = self.i.plan_part(self.PLAN, "## Rollback", 15)
        where = f"{name}: `## Rollback`"
        cl = sentences(self.norm(raw), ".;")
        units = [self.norm(u) for u in self.i.blocks(raw)]
        self.assertTrue([u for u in units if self.REPORTS.search(u) and self.deployed(u) and self.deploy_source(u)],
                        f"{where}: say the reports of items 5-8 are restored by a deploy (after a check-only) from a "
                        "fresh retrieve edited back where #197 changed it, or from their files in #197's `before/` only "
                        "while a fresh retrieve equals `after/`, in one list item or paragraph; their copies in "
                        "Decommissioned are the record, not the restore")
        self.assertTrue([u for u in units if re.search(r"(?i)\b(dashboard|D2)\b", u) and "before/" in u
                         and self.deployed(u) and self.deploy_source(u)],
                        f"{where}: say D2 is restored by a deploy of its own file in #197's `before/` only while a fresh "
                        "retrieve equals `after/` (or a fresh retrieve edited back), in one list item or paragraph, not "
                        "negated")
        self.assertRollbackSources(raw, where)
        # ... and the RUNBOOK's rollback of #197 likewise (#76's rollback above it keeps its own sources)
        part = self.i.part()
        m = re.search(r"(?im)^\W*rollback\b[^\n]*#197\b", part)
        self.assertTrue(m, f"RUNBOOK {ImplementationDashboardDocs.PART!r}: no rollback of #197 (a paragraph starting "
                           "`Rollback of #197`)")
        self.assertRollbackSources(part[m.start():], f"RUNBOOK {ImplementationDashboardDocs.PART!r}, Rollback of #197")
        self.assertTrue([s for s in cl if re.search(r"(?i)\bnew\b[^.;]{0,60}?\breports?\b", s) and "Decommissioned" in s
                         and self.stated(s, re.compile(r"(?i)\b(go(es)?|mov\w*|put)\b"))],
                        f"{where}: say the new reports (\"Modules Adapted Responses\", any new summit report) move to "
                        "Decommissioned, deleting nothing (one sentence, not negated)")
        self.assertTrue([s for s in cl if re.search(r"(?i)\b(never|not|no)\b[^.;]{0,60}?\b(older|old|earlier|previous|"
                                                    r"stale)\s+(\w+\s+)?(build|retrieve)\b", s)],
                        f"{where}: say never from an older build or retrieve (DECISIONS 2026-10-16), in one sentence")


class GlowReviewObservationsDocs(unittest.TestCase):
    """Ticket #198 (epic #194, GLOW's review of 2026-11-02): D3, the dashboard "GLOW Club Training" in the org, is
    titled "Club Observation Dashboards" (its Id unchanged), shows 2026 only, has a Month filter and offers no option
    for the former PO; its three reports get GLOW's names within the 40 characters of a report's name: item 9 "GC
    Observation Forms by Month & Partner", item 10 "Club Observations by Month and Partner", item 11 "Clubs Observed at
    Least Once by Month" (no "Alteast"). `glow/sf_keep_list.csv` carries them in `label_target` (`label_today` stays
    the label #70 recorded). GLOW asked whether item 11 still reads the count question
    `many_clubs_do_you_still_need_to_observe__c`, which has no answers in 2026: it does not, it derives Observed
    Yes/No from the sessions observed, `GC_sessions_did_you_observe_last_month__c`, answered in every month of 2026;
    the RUNBOOK's `### GLOW Club Observations` says so."""

    longMessage = False         # the messages say what to fix
    KEEP_LIST = CategoryFoldersDocs.KEEP_LIST
    # item: GLOW's name for the report (the task's Outline step 3), each within 40 characters
    TARGETS = {"9": "GC Observation Forms by Month & Partner",
               "10": "Club Observations by Month and Partner",
               "11": "Clubs Observed at Least Once by Month"}
    COUNT_QUESTION = "many_clubs_do_you_still_need_to_observe__c"
    SESSIONS = "GC_sessions_did_you_observe_last_month__c"
    # What is said OF the count question, anchored to the field itself (a word elsewhere in the sentence, "the old
    # bucket is not used", "its Partner Manager filter had no answers in 2026", says nothing of it):
    _Q = re.escape(COUNT_QUESTION) + r"`?"
    # item 11 does not use it: a negation before the field (`locally_denied`, "does not use … `…`"), or the field
    # followed at once by "is not used" / ", which item 11 does not use"
    NOT_USED = re.compile(_Q + r"\s*,?\s*((which|that)\s+(item 11\s+)?(does\s+not|doesn['’]t|never|no longer)\s+"
                          r"(use|uses|read|reads|count|counts)\b|(itself\s+)?(is|are)\s+(not|no longer)\s+"
                          r"(used|read|counted|the source)\b|(is\s+)?unused\b)", re.I)
    # it has no answers in 2026: the field followed at once by "has no answers in 2026" / "has no 2026 answers" /
    # "was never answered in 2026", or "in 2026 nobody answered … `…`"
    NO_ANSWERS = re.compile(_Q + r"\s*,?\s*((which|that)\s+)?((has|have|had)\s+(no|zero|0)\s+(2026\s+)?(\w+\s+)?"
                            r"(answers?|responses?)\b[^.;,]{0,25}?\b2026\b|(has|have|had)\s+no\s+2026\s+"
                            r"(answers?|responses?)\b|(was|is|were)\s+(never|not)\s+answered\b[^.;,]{0,25}?\b2026\b)|"
                            r"\b2026\b[^.;,]{0,30}?\b(nobody|no\s+one|no\s+partner)\s+answered\s+(the\s+)?"
                            r"(count\s+)?(question\s+)?" + _Q, re.I)

    # --- the plan and the rollback (like #197's): D3 and the reports restored by a deploy, never from the copies ---
    PLAN = os.path.join(REPO, "docs", "plans", "2026-11-02-sf-review-observations.md")
    TICKET = re.compile(r"(?<![\w#])#198\b")
    GO = re.compile(r"Ryan['’]s go\b")
    EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}")
    REPORTS = re.compile(r"(?i)\breports?\b|\bitems?\s+(\d+\s*(,|and|&|-|–)\s*)*(9|10|11)\b")
    DEPLOY = re.compile(r"(?i)\b(re-?)?deploy\w*\b")
    # a deploy's sources: a fresh retrieve edited back, or `before/` guarded by a fresh retrieve that equals `after/`
    EDITED_BACK = re.compile(r"(?i)\bfresh\s+retriev\w*\b[^.;]{0,60}?\bedit\w*\s+back\b")
    GUARD = re.compile(r"(?i)\b(only|while|as long as|so long as|provided)\b[^.;]{0,30}?\bfresh\s+retriev\w*\b[^.;]{0,40}?"
                       r"\b(equals?|matches|match|is the same as|identical to)\b[^.;]{0,20}?\bafter/")
    # an old source: another change's data/ folder (#77's), any build/, an older build or retrieve, another ticket's
    # before/ or build; #198's own `data/sf_glow_review_<month>/` and a fresh retrieve are its sources
    OLD_SOURCE = re.compile(r"(?i)\bdata/sf_(?!glow_review_)[\w-]+/|\bbuild/|"
                            r"\b(older|old|earlier|previous|prior|stale|another|other|original)\s+([\w-]+\s+)?"
                            r"(retrieves?|builds?|backups?|exports?|snapshots?|versions?)\b|"
                            r"#(?!198\b)\d+['’]s\s+`?(before/|build/|retrieve|build)")
    # a restore from the Decommissioned copies ("Save As", "move a copy back", "point the component at the copy")
    COPY_RESTORE = re.compile(r"(?i)\bSave\s+As\b|\b(move|moves|moved|moving|put|puts|bring|brings)\s+(a|the|each|its|"
                              r"their|that)\s+cop(y|ies)\s+back\b|\bopen\s+(a|the|its|each|their)\s+cop(y|ies)\b|"
                              r"\bpoint\w*\s+(\w+\s+){0,4}?at\s+(a|the|its|their|that)\s+cop(y|ies)\b|"
                              r"\bfrom\s+(a|the|their|its|each|that)\s+(\w+\s+)?cop(y|ies)\b")
    EVEN = re.compile(r"(?i)\beven\s+(while|if|when|though)\b|\bregardless\b|\bwhether or not\b|\bno matter\b")
    DIFFERS = re.compile(r"(?i)\bdiffer\w*|\bdifferent\b|\bchanged\b|\bdoes\s*n[o']t\s+(equal|match)\b|\bmismatch\w*")
    RESTORE = re.compile(r"(?i)\brestor\w*|\broll(s|ed|ing)?\s+(\w+\s+)?back\b|\brollback\b|\brevert\w*|"
                         r"\b(come|comes|came|go|goes|brought|bring|brings|put|puts)\s+back\b|\bre-?deploy\w*|\bdeploy\w*")

    @classmethod
    def setUpClass(cls):
        ObservationsDashboardDocs.setUpClass()
        cls.o = ObservationsDashboardDocs()     # #77's helpers: part, blocks, keep, plan_part
        cls.d = cls.o.d                         # #69's helpers: locally_denied

    @staticmethod
    def norm(text):
        return DecommissionedFoldersDocs.norm(text)

    def stated(self, s, rx):
        return any(not self.d.locally_denied(s, m) for m in rx.finditer(s))

    def denied_before(self, s, m):
        """A negation in clause `s` before match `m`, back to the last comma, semicolon, dash, "but", "however",
        "then" or "otherwise" and at most 160 characters: "never from #77's `build/`", "not from their copies".
        A denial after the match ("#77's folder is no rollback") does not count."""
        # ("... and deploys #77's `build/`" starts a new clause: the "never" before "and" does not reach it)
        pre = re.split(r"[,;—–]|\bbut\b|\bhowever\b|\bthen\b|\botherwise\b|"
                       r"\band\s+(?:re-?)?(?:deploy\w*|restor\w*|use\w*|tak\w*|run\w*|put\w*)\b",
                       s[max(0, m.start() - 160):m.start()])[-1]
        return bool(self.d.NEGATION.search(pre))

    def deployed(self, u):
        """A sentence of unit `u` that restores by a deploy, not denied."""
        return any(self.stated(s, self.DEPLOY) for s in sentences(u, ".;"))

    def deploy_source(self, u):
        return bool(self.EDITED_BACK.search(u) or ("before/" in u and self.GUARD.search(u)))

    def assertRollbackSources(self, raw, where):
        """D3 and the reports come back by a deploy from a fresh retrieve edited back or #198's own `before/` only
        while a fresh retrieve equals `after/`: no old source (another change's data/ folder, a `build/`, an older
        build or retrieve) and no restore from the Decommissioned copies, unless denied before the match; `before/`
        never redeployed "even if" or when a fresh retrieve differs from `after/`."""
        units = [self.norm(u) for u in self.o.blocks(raw)]
        self.assertTrue([u for u in units if self.REPORTS.search(u) and self.deployed(u)],
                        f"{where}: say D3 and the reports of items 9-11 are restored by a deploy (after a check-only), "
                        "not from their copies in Decommissioned, in one list item or paragraph")
        self.assertTrue([u for u in units if self.deployed(u) and self.deploy_source(u)],
                        f"{where}: say the deploy is of a fresh retrieve edited back where #198 changed it, or of "
                        "#198's own `before/` only while a fresh retrieve equals `after/`, in one list item or "
                        "paragraph")
        for s in sentences(self.norm(raw), ".;"):
            for m in self.OLD_SOURCE.finditer(s):
                self.assertTrue(self.denied_before(s, m),
                                f"{where}: #198's rollback deploys a fresh retrieve edited back or #198's own "
                                f"`before/`, never {m.group(0)!r} (DECISIONS 2026-10-16); deny it before naming it "
                                f"(\"never from #77's `build/`\"): {s[:200]!r}")
            for m in self.COPY_RESTORE.finditer(s):
                self.assertTrue(self.denied_before(s, m),
                                f"{where}: D3 and the reports come back by a deploy, not from their copies in "
                                f"Decommissioned (D3's components point at the reports themselves); the copies are the "
                                f"record ({m.group(0)!r}): {s[:200]!r}")
            if "before/" not in s:
                continue
            self.assertFalse(self.EVEN.search(s), f"{where}: `before/` is deployed only while a fresh retrieve equals "
                                                  f"`after/`, never \"even if\" or \"regardless\": {s[:200]!r}")
            diff = [m for m in self.DIFFERS.finditer(s) if not self.d.locally_denied(s, m)]
            redo = [m for m in self.RESTORE.finditer(s) if not self.d.locally_denied(s, m)]
            self.assertFalse(diff and redo, f"{where}: `before/` is never deployed when a fresh retrieve differs from "
                                            f"`after/` (stop and ask instead): {s[:200]!r}")

    def test_the_plan_has_rollout_rollback_and_result(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        name = os.path.relpath(self.PLAN, REPO)
        self.assertTrue(os.path.isfile(self.PLAN), f"{name}: no plan for ticket #198 (Rollout, Rollback, Result)")
        rows = self.o.keep()
        text = read(self.PLAN)
        keys, _ = docs_index.frontmatter(text)
        self.assertIn("status", keys, f"{name}: frontmatter `status:`")
        _, problem = docs_index.status_of(keys["status"])
        self.assertIsNone(problem, f"{name}: {problem}")
        self.assertRegex(text.split("\n## ", 1)[0], self.TICKET,
                         f"{name}: name ticket #198 in the frontmatter, the title or the opening paragraph")
        self.assertRegex(text, r"(?m)^## Result\b", f"{name}: no `## Result` section")
        self.assertNotRegex(text, self.EMAIL, f"{name}: counts, ids and names of reports and partners only, no address")

        raw = self.o.plan_part(self.PLAN, "## Rollout", 40)
        where = f"{name}: `## Rollout`"
        cl = sentences(self.norm(raw), ".;")
        self.assertRegex(flat(raw), r"(?i)\bVPN off\b|--vpn-off", f"{where}: VPN off before any `sf` call")
        self.assertRegex(flat(raw), r"data/sf_glow_review_\d{4}-\d\d/[\w<>-]+/before/",
                         f"{where}: retrieve live into `data/sf_glow_review_2026-11/<topic>/before/` (epic #194)")
        for key in ("D3", "9", "10", "11"):
            r = rows[key]
            self.assertIn(r["id"], raw, f"{where}: name {'the dashboard' if key == 'D3' else 'item ' + key} "
                                        f"({r['label_today']!r}) by its Id {r['id']}")
        # the copies: by the tool, VPN off, tagged with the ticket, into Decommissioned, on Ryan's go
        segments = re.split(r"`+|\n\s*\n|\n(?=\s*(?:\$\s*)?python3\s)|(?=\bpython3\s)", raw)
        copies = [flat(s) for s in segments if re.search(r"\bsf_report_folders\.py\s+copy\b", s)]
        self.assertTrue(copies, f"{where}: give the copies' command, `python3 tools/sf_report_folders.py copy --vpn-off "
                                "--kind report --id <id> --tag \"#198\"`")
        for c in copies:
            self.assertIn("--vpn-off", c, f"{where}: the tool refuses to run without `--vpn-off`: {c[:160]!r}")
            self.assertRegex(c, r"--tag[ =]\\?[\"“']?#198\b", f"{where}: each copy carries the ticket, `--tag \"#198\"`: "
                                                             f"{c[:160]!r}")
        self.assertTrue([s for s in cl if re.search(r"(?i)\bcop(y|ies)\b", s) and "Decommissioned" in s
                         and not self.d.denies(s)],
                        f"{where}: the copies go to Decommissioned before the change (one sentence)")
        self.assertTrue([s for s in cl if self.stated(s, self.GO) and re.search(r"(?i)\bcop(y|ies)\b|--apply", s)],
                        f"{where}: the copies wait for Ryan's go (one sentence, not negated)")
        # item 11 cannot be copied by the Analytics API (its bucket field): its copy is by metadata, check-only, deploy
        r11 = rows["11"]

        def check_then_deploy(u):
            c = re.search(r"(?i)\bcheck-only\b|--dry-run", u)
            return bool(c and re.search(r"(?i)\bdeploy", u[c.end():]))
        meta = [u for u in self.o.blocks(raw) if r11["id"] in u and re.search(r"(?i)\bmetadata\b", u)
                and "Decommissioned" in u and "#198" in u and check_then_deploy(u)]
        self.assertTrue(meta, f"{where}: give item 11's copy by metadata (the Analytics API refuses a report with a "
                              f"bucket field): its XML into Decommissioned, described with its Id {r11['id']} and "
                              "\"#198\", check-only first, then the deploy, in one step")
        self.assertTrue([s for s in cl if self.stated(s, self.GO) and re.search(r"(?i)\bdeploy", s)
                         and not re.search(r"(?i)\bcheck-only\b", s)],
                        f"{where}: the deploy waits for Ryan's go (one sentence, not negated, apart from the check-only)")
        self.assertTrue([s for s in cl if "after/" in s and "build/" in s
                         and re.search(r"(?i)\b(compar\w*|equals?|differ\w*|diff)\b", s)],
                        f"{where}: the read-back retrieves into `after/` and compares it with `build/` (one sentence)")
        # the order, in the numbered steps: before/, copies, check-only, deploy of the build, after/
        steps = CategoryFoldersDocs.steps(self, raw, where)
        before = CategoryFoldersDocs.first(self, r"\bbefore/", steps, where,
                                           "the steps start from a fresh retrieve into `before/`")
        copy_at = [m.start() for m in re.finditer(r"\bsf_report_folders\.py\s+copy\b", steps)]
        self.assertTrue(copy_at, f"{where}: the copies are a numbered step")
        self.assertLess(before, copy_at[0], f"{where}: the `before/` retrieve comes before the copies")
        # the build's deploy is the command `sf project deploy start`: with `--dry-run` it is the check-only
        commands = [(m.start(), "--dry-run" in m.group(1)) for m in re.finditer(r"sf project deploy start([^`]*)", steps)]
        dry = [at for at, d in commands if d]
        real = [at for at, d in commands if not d]
        self.assertTrue(dry, f"{where}: the check-only deploy is a step (`sf project deploy start --dry-run …`)")
        self.assertTrue(real, f"{where}: the deploy is a step (`sf project deploy start …`, on Ryan's go)")
        self.assertGreater(dry[0], copy_at[-1], f"{where}: the check-only comes after every copy (copy first, then change)")
        self.assertGreater(real[-1], dry[0], f"{where}: the deploy of the build comes after its check-only")
        self.assertTrue([m for m in re.finditer(r"\bafter/", steps) if m.start() > real[-1]],
                        f"{where}: the `after/` read-back comes after the deploy")

        # the rollback: D3 and the reports restored by a deploy, never from the copies or an older build
        raw = self.o.plan_part(self.PLAN, "## Rollback", 15)
        where = f"{name}: `## Rollback`"
        self.assertRollbackSources(raw, where)
        cl = sentences(self.norm(raw), ".;")
        self.assertTrue([s for s in cl if re.search(r"(?i)\b(never|not|no)\b[^.;]{0,60}?\b(older|old|earlier|previous|"
                                                    r"stale)\s+(\w+\s+)?(build|retrieve)\b", s)],
                        f"{where}: say never from an older build or retrieve (DECISIONS 2026-10-16), in one sentence")
        self.assertTrue([s for s in cl if re.search(r"(?i)\b(nothing|never)\b[^.;]{0,30}?\bdelet\w*", s)],
                        f"{where}: say nothing is deleted (the copies stay in Decommissioned), in one sentence")
        # ... and the RUNBOOK's #198 rollback paragraph likewise
        part = self.o.part()
        m = re.search(r"(?im)^\W*rollback\b[^\n]*#198\b", part)
        self.assertTrue(m, f"RUNBOOK {ObservationsDashboardDocs.PART!r}: no rollback of #198 (a paragraph starting "
                           "`Rollback of #198`)")
        self.assertRollbackSources(part[m.start():], f"RUNBOOK {ObservationsDashboardDocs.PART!r}, the #198 rollback")

    def test_the_keep_list_has_no_alteast_and_stays_within_40_characters(self):
        import csv
        with open(self.KEEP_LIST, encoding="utf-8", newline="") as f:
            rows = {r["item"]: r for r in csv.DictReader(f)}
        for item, want in sorted(self.TARGETS.items(), key=lambda kv: int(kv[0])):
            self.assertIn(item, rows, f"glow/sf_keep_list.csv: no row {item}")
            self.assertEqual(rows[item]["kind"], "report", f"glow/sf_keep_list.csv item {item}: a report")
            self.assertEqual(rows[item]["label_target"], want,
                             f"glow/sf_keep_list.csv item {item}: label_target is GLOW's name {want!r} (GLOW's review, "
                             f"2026-11-02; ticket #198), not {rows[item]['label_target']!r}")
            self.assertLessEqual(len(want), 40, f"test: GLOW's name {want!r} is within 40 characters")
        for item, r in rows.items():
            self.assertNotIn("alteast", r["label_target"].lower(),
                             f"glow/sf_keep_list.csv item {item}: label_target {r['label_target']!r} still has the "
                             "typo \"Alteast\" (GLOW's review, 2026-11-02)")
            if r["kind"] in ("report", "table"):
                self.assertLessEqual(len(r["label_target"]), 40,
                                     f"glow/sf_keep_list.csv item {item}: label_target {r['label_target']!r} is over 40 "
                                     "characters (Salesforce's limit on a report's name)")

    def test_the_runbook_names_the_source_of_item_11(self):
        where = f"RUNBOOK section {ObservationsDashboardDocs.MONTHLY[3:]!r}, {ObservationsDashboardDocs.PART[4:]!r}"
        r11 = self.o.keep()["11"]
        part = self.o.part()
        names11 = re.compile(r"(?i)\bitem\s+11\b(?!\d)|" + re.escape(r11["id"]) + "|" + re.escape(r11["measure"]) + "|"
                             + "|".join(re.escape(r11[c]) for c in ("label_today", "label_target")))
        mine = [b for b in self.o.blocks(part) if names11.search(b)]
        self.assertTrue(mine, f"{where}: item 11 ({r11['measure']!r}) has its own row, list item or paragraph")
        in11 = [s for b in mine for s in sentences(self.norm(b), ".;")]
        # the count question, wherever the part names it, is said not to be item 11's source or to have no 2026 answers
        count = re.compile(re.escape(self.COUNT_QUESTION))
        named = [s for s in sentences(self.norm(part), ".;") if count.search(s)]
        self.assertTrue(named, f"{where}: item 11's block names the count question `{self.COUNT_QUESTION}` (GLOW asked "
                               "whether it was removed from the form)")
        for s in named:
            m = count.search(s)
            ok = self.d.locally_denied(s, m) or self.NOT_USED.search(s) or self.NO_ANSWERS.search(s)
            self.assertTrue(ok, f"{where}: `{self.COUNT_QUESTION}` is only ever said not to be item 11's source (a "
                                "negation right before it, or \"`…` is not used\"), or to have no answers in 2026 "
                                f"(\"`…` has no answers in 2026\"): {s[:200]!r}")
        not_source = [s for s in in11 if count.search(s)
                      and (self.d.locally_denied(s, count.search(s)) or self.NOT_USED.search(s))]
        self.assertTrue(not_source, f"{where}: say, in item 11's block, that item 11 does not use the count question "
                                    f"`{self.COUNT_QUESTION}` (one sentence naming it, denied)")
        no_answers = [s for s in in11 if self.NO_ANSWERS.search(s)]
        self.assertTrue(no_answers, f"{where}: say, in item 11's block, that the count question "
                                    f"`{self.COUNT_QUESTION}` has no answers in 2026 (one sentence naming it and 2026)")
        # ... and the source: Observed Yes/No from the sessions observed, not denied, not the count question
        sessions = re.compile(re.escape(self.SESSIONS))
        derived = [s for s in in11 if sessions.search(s) and not count.search(s)
                   and not self.d.locally_denied(s, sessions.search(s))
                   and re.search(r"(?i)\bobserved\b", s) and re.search(r"\bYes\b", s) and re.search(r"\bNo\b", s)]
        self.assertTrue(derived, f"{where}: say, in item 11's block, that item 11 derives Observed Yes/No from the "
                                 f"sessions observed, `{self.SESSIONS}` (one sentence naming the field, \"Observed\", "
                                 "Yes and No, not negated)")


class GlowReviewReportingDocs(unittest.TestCase):
    """Ticket #200 (epic #194, GLOW's review of 2026-11-02): D5, the dashboard "Reporting", and its items 17-19. Item
    17 is relabelled "Monthly Report Approval Status" (its Id unchanged; `glow/sf_keep_list.csv` carries it in
    `label_target`, `label_today` stays the label #70 recorded). Item 17 lists approved reports only (`Approved__c
    equals 1`), so GLOW's overview, the partner reports approved versus not yet approved by month, is a new report,
    "Approval Status by Month", without that filter, grouped by `Period__c` by month and `Approved__c`, shown as a
    stacked column on D5. Items 17-19 filter `In_Reporting_Year__c equals true` (#195), 2026 only; D5 gains a Month
    filter on `DHIS2__c$Month__c`. The RUNBOOK's `### GLOW Club Reporting` says so, and keeps the old rules (the last
    12 months, no Month filter, Partner Manager the only filter) only as history; the plan
    `docs/plans/2026-11-02-sf-review-reporting.md` carries the copies, the check-only, Ryan's go, the deploy and the
    read-back in that order, a Rollback by deploy and a `## Result`. The wording is free: each rule is looked for as
    a claim in a sentence or unit, not denied."""

    longMessage = False         # the messages say what to fix
    PLAN = os.path.join(REPO, "docs", "plans", "2026-11-02-sf-review-reporting.md")
    KEEP_LIST = ReportingDashboardDocs.KEEP_LIST
    TICKET = re.compile(r"(?<![\w#])#200\b")
    ITEMS = ReportingDashboardDocs.ITEMS
    ITEM_17_ID = "00ORP000006XXEf2AO"                   # ticket #70's id for item 17: the rename keeps it
    ITEM_17_LABEL_TODAY = "Approved Approvals monthly report"
    NEW_LABEL = "Monthly Report Approval Status"        # GLOW's name for item 17 (Outline step 3)
    OVERVIEW = "Approval Status by Month"               # the new report behind the overview chart (Outline step 3)
    GO = re.compile(r"Ryan['’]s go\b")
    EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}")
    # the reporting-year filter, as set ("`In_Reporting_Year__c equals true`", "`In_Reporting_Year__c = true`")
    YEAR_ON = re.compile(r"\bIn_Reporting_Year__c\b[^.;]{0,25}?\btrue\b")
    # 2026 only, 2025 out ("2026 only", "only 2026", "no 2025 month", "2025 is left out", "the reporting year only")
    ONE_YEAR = re.compile(r"(?i)\b2026\s+only\b|\bonly\s+(\w+\s+){0,3}?2026\b|\bno\s+(\w+\s+){0,3}?2025\b|"
                          r"\b2025\b[^.;]{0,40}?\b(excluded|left out|out|off|gone|dropped|hidden)\b|"
                          r"\breporting year only\b|\bonly\s+(the\s+)?(current\s+)?reporting year\b")
    # what a 2026-only sentence is about: D5, its reports (not "Monthly Reports", the records) or a component
    D5_NAMED = re.compile(r"\bD5\b|\b01ZRP000006oxSr2AI\b|[\"“`]Reporting[\"”`]|(?i:\bdashboard\b)")
    REPORTS_NAMED = re.compile(r"(?i)\b(the|its|their|each|every|all|three|both|these|D5['’]s)\s+(\w+\s+){0,2}?"
                               r"reports?\b|\ball\s+three\b|\bcomponents?\b|\bcharts?\b|\btables?\b")
    # every report: "each report", "all three", "items 17-19" (items_named reads the item numbers)
    EVERY = re.compile(r"(?i)\b(each|every|all)\b[^.;]{0,40}?\breports?\b|\ball\s+three\b|\bthe\s+three\s+reports\b")
    # the old period, said as today's rule when no history marker is near it
    OLD_PERIOD = re.compile(r"\bLAST_N_MONTHS:12\b|(?i:\blast\s+(12|twelve)\s+months\b)")
    PERIOD_TALK = re.compile(r"(?i)Period__c|\bperiod\b|\bdate filter\b|\bfield filter\b|\breports?['’]? filters?\b|"
                             r"\bfilters?\b")
    # said as the past or as what was replaced, near the old rule
    HISTORY = re.compile(r"(?i)\b(was|were|had|until|before|formerly|former|no longer|previously|used to|replac\w*|"
                         r"in place of|instead of|became|becomes|rather than|superseded|gave way)\b")
    # a Month filter ("a Month filter", "the "Month" filter", "a filter on `DHIS2__c$Month__c`")
    MONTH_FILTER = re.compile(r"(?i)\bMonth\b[\"”'’`]?\s*(\([^)]{0,60}\)\s*)?(dashboard\s+)?filters?\b|"
                              r"\bfilter(s|ed|ing)?\s+(on|by|for)\s+(the\s+|a\s+|each\s+)?[`\"“]?(DHIS2__c\$)?"
                              r"Month(__c)?\b")
    MONTH_FIELD = re.compile(r"\bDHIS2__c\$Month__c\b")
    NO_MONTH = re.compile(r"(?i)\b(no|not|without|neither|nor|never)\b[^.;]{0,25}?\bMonth\b[^.;]{0,20}?\bfilters?\b")
    ONLY_PM = re.compile(r"(?i)\b(only|one|sole|single)\b[^.;]{0,30}?\bfilter\b[^.;]{0,40}?\bPartner Manager\b")
    # the overview: a stacked column, approved versus not yet approved, by month
    STACKED = re.compile(r"(?i)\bstacked\s+(vertical\s+)?(column|bar)s?\b|\bColumnStacked\b|\bcolumn\s+chart,?\s+"
                         r"stacked\b")
    NOT_APPROVED = re.compile(r"(?i)\bnot\s+(yet\s+)?approved\b|\bunapproved\b|\b(pending|awaiting)\s+approval\b")
    BY_MONTH = re.compile(r"(?i)\bby\s+(calendar\s+)?month\b|\bmonth\s+by\s+month\b|\b(each|per)\s+month\b")
    # item 17's filter ("`Approved__c equals 1`", "`Approved__c` = true", "a filter on `Approved__c`")
    APPROVED_FILTER = re.compile(r"(?i)\bApproved__c`?\s*(equals|=)\s*`?(1|true)\b|\bfilters?\s+(on\s+)?`?Approved__c\b")
    # left out of the overview: a negation, or "drops", "removes", "leaves out" before it
    LEFT_OUT = re.compile(r"(?i)\b(drop\w*|remov\w*|leav\w*\s+out|lacks?|omit\w*|takes?\s+out|minus)\b")
    # item 17 lists approved reports only
    APPROVED_ONLY = re.compile(r"(?i)\bapproved\s+(\w+\s+){0,3}?only\b|\bonly\s+(\w+\s+){0,3}?approved\b|"
                               r"\bApproved__c`?\s*(equals|=)\s*`?(1|true)\b|\bApproved__c`?\s+(ticked|checked)\b")
    # the reason, said ("so", "because", "which is why")
    REASON = re.compile(r"(?i)\b(so|because|since|hence|therefore|thus|which is why|that is why|that['’]s why|"
                        r"for that reason)\b")
    # an old source for #200's rollback: another data/ folder (#79's `data/sf_dash_reporting_…/`, another topic of the
    # review), an older build, another ticket's folder; #200's own `data/sf_glow_review_<month>/reporting…/`, the copy
    # tool's ledger and a fresh retrieve are its sources
    OLD_SOURCE = re.compile(r"(?i)\bdata/sf_(?!glow_review_(\d{4}-\d\d|<month>)/(reporting[\w-]*|<topic>)(?![\w-])|"
                            r"report_folders(?![\w-]))[\w<>-]+(/[\w<>-]+)*/?|"
                            r"\b(older|old|earlier|previous|prior|stale|another|other|original)\s+([\w-]+\s+)?"
                            r"(retrieves?|builds?|backups?|exports?|snapshots?|versions?)\b|"
                            r"#(?!200\b)\d+['’]s\s+`?(data/|before/|build/|after/|retrieve|build|folder)")
    REPORTS = re.compile(r"(?i)\breports?\b|\bitems?\s+(\d+\s*(,|and|&|-|–|to)\s*)*1[789]\b")
    DEPLOY = re.compile(r"(?i)\b(re-?)?deploy\w*\b")
    # a deploy's sources: a fresh retrieve edited back, or `before/` guarded by a fresh retrieve that equals `after/`
    EDITED_BACK = re.compile(r"(?i)\bfresh\s+retriev\w*\b[^.;]{0,40}?\bedit\w*\s+back\b")
    GUARD = re.compile(r"(?i)\b(only|while|as long as|so long as|provided)\b[^.;]{0,30}?\bfresh\s+retriev\w*\b[^.;]{0,40}?"
                       r"\b(equals?|matches|match|is the same as|identical to)\b[^.;]{0,20}?\bafter/")
    # a restore from the Decommissioned copies ("restored from their copies"): they are the record, not the restore
    FROM_COPY = re.compile(r"(?i)\b(restor\w*|revert\w*|roll\w*\s+back|redeploy\w*|deploy\w*|brought\s+back|bring\w*\s+"
                           r"back|re-?sav\w*|sav\w*\s+back)\b[^.;]{0,50}?\bfrom\s+(\w+\s+){0,2}?cop(y|ies)\b")

    @classmethod
    def setUpClass(cls):
        ReportingDashboardDocs.setUpClass()
        cls.r = ReportingDashboardDocs()        # #79's helpers: part, blocks, keep, items_named, plan_part, sweep
        cls.d = cls.r.d                         # #69's helpers: locally_denied, NEGATION, denies
        cls.c = cls.r.c                         # #73's helpers: steps, first

    @staticmethod
    def norm(text):
        return DecommissionedFoldersDocs.norm(text)

    @staticmethod
    def prose(s):
        """Clause `s` without its backticked SOQL statements: a query is a check, not a claim."""
        return re.sub(r"`[^`]*\bSELECT\b[^`]*`", " ", s)

    def stated(self, s, rx):
        return any(not self.d.locally_denied(s, m) for m in rx.finditer(s))

    # after the old rule, only a dated end marks it as history ("…, until #200", "(until then …)"); "as before",
    # "in place of `CreatedDate`" after it are no such marker
    UNTIL_AFTER = re.compile(r"(?i)\buntil\s+(#\d+|then|\d{4}-\d\d-\d\d)\b")

    def history(self, s, m):
        """Match `m` of `s` said as the past or as what was replaced: a marker (`HISTORY`) in the 50 characters
        before it, "until #N" in the 30 after it, or a denial."""
        return bool(self.HISTORY.search(s[max(0, m.start() - 50):m.start()])
                    or self.UNTIL_AFTER.search(s[m.end():m.end() + 30]) or self.d.locally_denied(s, m))

    SHOW = re.compile(r"(?i)\b(show|shows|showing|shown|display|displays|displaying|cover|covers|hold|holds|keep|keeps)"
                      r"\s+((data|records|rows|months?|reports|figures|data\s+from|from)\s+){0,2}$")

    def claims_one_year(self, s, m, rows):
        """Match `m` of ONE_YEAR in `s` is the claim that D5 and its reports show 2026 only: not denied, a verb of
        showing right before it, and D5 and its reports (or components, items 17-19) named before it."""
        if self.d.locally_denied(s, m) or not self.SHOW.search(s[:m.start()]):
            return False
        subject = re.sub(r"(?i)\bMonthly\s+Reports?\b", " ", s[:m.start()])
        return bool(re.search(r"\bD5\b|\b01ZRP000006oxSr2AI\b|[\"“`]Reporting[\"”`]", subject)
                    and (self.REPORTS_NAMED.search(subject) or self.r.items_named(subject, rows)))

    def left_out(self, s, m):
        """Match `m` of `s` said to be left out: a negation ("without") or a verb that drops it in the 40 characters
        before it, back to the last comma or dash."""
        pre = re.split(r"[,—–]|\bbut\b", s[max(0, m.start() - 40):m.start()])[-1]
        return bool(self.d.NEGATION.search(pre) or self.LEFT_OUT.search(pre))

    def names_17(self, s):
        """`s` names item 17 by number, Id or GLOW's measure (its labels alone do not tie a label to it)."""
        rows = self.r.keep()
        return bool(re.search(r"(?i)\bitem\s+17\b", s) or rows["17"]["id"] in s or rows["17"]["measure"] in s
                    or self.r.items_named(s, rows) & {"17"})

    def where_by(self, soql):
        m = re.search(r"(?is)\bWHERE\b(.*?)(?=\bGROUP\s+BY\b|\bORDER\s+BY\b|\bHAVING\b|\bLIMIT\b|$)", soql)
        g = re.search(r"(?is)\bGROUP\s+BY\b(.*?)(?=\bORDER\s+BY\b|\bHAVING\b|\bLIMIT\b|$)", soql)
        return (m.group(1) if m else ""), (g.group(1) if g else "")

    def deployed(self, u):
        """A sentence of unit `u` that restores by a deploy, not denied."""
        return any(self.stated(s, self.DEPLOY) for s in sentences(u, ".;"))

    def deploy_source(self, u):
        return bool(self.EDITED_BACK.search(u) or ("before/" in u and self.GUARD.search(u)))

    # --- the RUNBOOK ----------------------------------------------------------------------------------------

    def test_the_runbook_states_the_approval_overview(self):
        where = f"RUNBOOK section {ReportingDashboardDocs.MONTHLY[3:]!r}, {ReportingDashboardDocs.PART[4:]!r}"
        rows = self.r.keep()
        part = self.r.part()
        blocks = self.r.blocks(part)
        cl = [self.prose(s) for s in sentences(self.norm(part), ".;")]

        # item 17's new name, in a unit that names item 17 by number, Id or measure
        self.assertTrue([b for b in blocks if self.NEW_LABEL in b and self.names_17(b.replace(self.NEW_LABEL, " "))],
                        f"{where}: name item 17 by its new label {self.NEW_LABEL!r} (GLOW's review, 2026-11-02), in a row, "
                        f"list item or paragraph naming item 17 (by number, its Id {rows['17']['id']} or GLOW's measure)")

        # the overview: a unit naming the new report says what it shows and how it is built
        overview = [b for b in blocks if self.OVERVIEW in b]
        self.assertTrue(overview, f"{where}: name the overview's new report {self.OVERVIEW!r} (Outline step 3)")
        d5 = rows[ReportingDashboardDocs.DASH]
        problems = {}

        def check(b):
            """What unit `b` lacks of the overview's description (an empty list: all of it)."""
            ss = [self.prose(s) for s in sentences(self.norm(b), ".;")]
            lacks = []
            if not [s for s in ss if self.stated(s, self.STACKED)]:
                lacks.append("a stacked column")
            if not (re.search(r"\bD5\b", b) or d5["id"] in b):
                lacks.append(f"on D5 ({d5['id']})")
            if not [s for s in ss if self.stated(s, self.NOT_APPROVED) and re.search(r"(?i)\bapproved\b", s)]:
                lacks.append("approved versus not yet approved")
            if not [s for s in ss if self.stated(s, self.BY_MONTH)]:
                lacks.append("by month")
            for field in ("Approved__c", "Period__c"):
                if field not in self.prose(self.norm(b)):
                    lacks.append(f"grouped by `{field}`")
            dropped = [s for s in ss for m in self.APPROVED_FILTER.finditer(s) if self.left_out(s, m)]
            if not dropped:
                lacks.append("without item 17's `Approved__c equals 1` filter (\"without …\")")
            for s in ss:        # the filter said ON is said of item 17, never of the overview
                for m in self.APPROVED_FILTER.finditer(s):
                    if not self.left_out(s, m) and (self.OVERVIEW in s or not self.names_17(s)):
                        lacks.append(f"no `Approved__c` filter on the overview ({s[:120]!r})")
            return lacks
        for b in overview:
            problems[b[:80]] = check(b)
        self.assertTrue([k for k, v in problems.items() if not v],
                        f"{where}: describe the overview chart in one row, list item or paragraph naming "
                        f"{self.OVERVIEW!r}: the partner reports approved versus not yet approved, by month, a stacked "
                        f"column on D5, from the new report grouped by `Period__c` (by month) and `Approved__c`, without "
                        f"item 17's `Approved__c equals 1` filter. Lacking: {problems}")

        # ... and its SOQL signal: grouped by `Approved__c` and the month, no filter on `Approved__c`, 2026, test rule
        spans = [m.group(0) for b in blocks if self.OVERVIEW in b for m in ReportingDashboardDocs.SOQL_SPAN.finditer(b)]
        good = []
        for q in spans:
            wh, gb = self.where_by(q)
            if not re.search(r"\bApproved__c\b", gb):
                continue
            self.assertNotRegex(wh, r"\bApproved__c\b", f"{where}: the overview's signal counts approved and not yet "
                                                        f"approved, so its WHERE has no `Approved__c`: {q[:220]!r}")
            month = re.search(r"\bPeriod__c\b", gb) or re.search(r"\bPeriod__c\s*=", wh)
            year = self.r.IN_YEAR_SOQL.search(wh) or re.search(r"\bPeriod__c\s*=", wh)
            rule = ReportingDashboardDocs.SOQL_NOT_BLANK.search(wh) and ReportingDashboardDocs.SOQL_NO_TEST.search(wh)
            if month and year and rule:
                good.append(q)
        self.assertTrue(good, f"{where}: give the overview's SOQL signal in a unit naming {self.OVERVIEW!r}: `SELECT "
                              "CALENDAR_MONTH(Period__c), Approved__c, COUNT(Id) FROM DHIS2__c WHERE In_Reporting_Year__c = "
                              "true AND Account__c != null AND (NOT Account__r.Name LIKE '%test%') GROUP BY "
                              "CALENDAR_MONTH(Period__c), Approved__c` (or one month's, `Period__c = LAST_MONTH … GROUP BY "
                              "Approved__c`)")

        # why it needs its own report: item 17 lists approved reports only
        why = []
        for b in blocks:
            ss = [self.prose(s) for s in sentences(self.norm(b), ".;")]
            only = [s for s in ss if self.names_17(s) and self.stated(s, self.APPROVED_ONLY)]
            because = [s for s in ss if self.stated(s, self.REASON)
                       and (self.OVERVIEW in s or re.search(r"(?i)\boverview\b|\b(own|new|separate)\s+report\b", s))]
            if only and because:
                why.append(b)
        self.assertTrue(why, f"{where}: say why the overview needs its own report: item 17 lists approved reports only "
                             "(`Approved__c equals 1`), so the overview is the new report without that filter (one row, "
                             "list item or paragraph: a sentence naming item 17 and \"approved … only\", and a sentence "
                             "with \"so\" or \"because\" naming the overview or its own report)")

        # the reporting year: items 17-19 and D5, `In_Reporting_Year__c equals true`
        year = [s for s in cl if [m for m in self.YEAR_ON.finditer(s) if not self.d.locally_denied(s, m)]]
        covered = set()
        for s in year:
            covered |= self.r.items_named(s, rows)
            if self.EVERY.search(re.sub(r"(?i)\bMonthly\s+Reports?\b", " ", s)):
                covered |= set(self.ITEMS)
        self.assertEqual(covered, set(self.ITEMS),
                         f"{where}: say items 17, 18 and 19 filter `In_Reporting_Year__c equals true` (#195), in place of "
                         f"`Period__c equals LAST_N_MONTHS:12` (a sentence naming them, or \"each report\"; missing: "
                         f"{sorted(set(self.ITEMS) - covered, key=int)})")
        one_year = [s for s in cl if [m for m in self.ONE_YEAR.finditer(s) if not self.d.locally_denied(s, m)]]
        # the claim itself, in one sentence: D5 and its reports (or components, items 17-19) as the subject, a verb of
        # showing right before "2026 only" (a check's "no grouping label contains 2025" is no such claim)
        about = [s for s in one_year for m in self.ONE_YEAR.finditer(s) if self.claims_one_year(s, m, rows)]
        self.assertTrue(about, f"{where}: say D5 and its reports show 2026 only, in one sentence: D5 and its reports (or "
                               "its components, items 17-19) as the subject, then \"show 2026 only\" or \"show no 2025 "
                               "month\" (a sentence about something else, a check's figure, does not count)")
        self.assertTrue([s for s in year + one_year if self.D5_NAMED.search(s)],
                        f"{where}: say D5 shows the reporting year (a sentence naming D5 or the dashboard with "
                        "`In_Reporting_Year__c` or \"2026 only\")")
        for s in cl:            # the last 12 months stays only as history
            if not self.PERIOD_TALK.search(s):
                continue
            for m in self.OLD_PERIOD.finditer(s):
                self.assertTrue(self.history(s, m),
                                f"{where}: since #200 the period is `In_Reporting_Year__c`; the last 12 months "
                                f"({m.group(0)!r}) is said only as what it replaced (\"until #200\", \"was\", \"in place "
                                f"of\"): {s[:200]!r}")

        # the Month filter on DHIS2__c$Month__c, D5's, and nothing left that denies it or makes Partner Manager the only one
        month = [s for s in cl if self.MONTH_FIELD.search(s) and self.D5_NAMED.search(s)
                 and [m for m in self.MONTH_FILTER.finditer(s)
                      if not (self.d.locally_denied(s, m) or self.d.NEGATION.search(m.group(0)))]]
        self.assertTrue(month, f"{where}: say D5 has a Month filter on `DHIS2__c$Month__c` (one sentence naming the "
                               "dashboard or D5, the filter and the field, not negated)")
        for s in cl:
            for m in self.NO_MONTH.finditer(s):
                self.assertTrue(self.history(s, m),
                                f"{where}: D5 has a Month filter since #200; \"no Month filter\" is said only as history "
                                f"(\"until #200 it had no Month filter\"): {s[:200]!r}")
            if s in month:
                continue
            for m in self.ONLY_PM.finditer(s):
                self.assertTrue(self.history(s, m),
                                f"{where}: Partner Manager is no longer D5's only filter (Month is the other); say it "
                                f"only as history: {s[:200]!r}")

        # the part's rollback of #200 follows the same rules as the plan's (review of #200)
        self.assertRollbackOf200(self.runbook_rollback(), f"{where}, the rollback of #200")

    # --- the keep list --------------------------------------------------------------------------------------

    def test_the_keep_list_carries_the_approval_name(self):
        import csv
        with open(self.KEEP_LIST, encoding="utf-8", newline="") as f:
            rows = {r["item"]: r for r in csv.DictReader(f)}
        self.assertIn("17", rows, "glow/sf_keep_list.csv: no row 17")
        r = rows["17"]
        where = "glow/sf_keep_list.csv item 17"
        self.assertEqual(r["kind"], "report", f"{where}: a report")
        self.assertEqual(r["label_target"], self.NEW_LABEL,
                         f"{where}: label_target is GLOW's name {self.NEW_LABEL!r} (GLOW's review, 2026-11-02; ticket "
                         f"#200), not {r['label_target']!r}")
        self.assertLessEqual(len(r["label_target"]), 40, f"{where}: label_target {r['label_target']!r} is over 40 "
                                                         "characters (Salesforce's limit on a report's name)")
        self.assertEqual(r["id"], self.ITEM_17_ID, f"{where}: the rename keeps the report's Id {self.ITEM_17_ID}, not "
                                                   f"{r['id']!r}")
        self.assertEqual(r["label_today"], self.ITEM_17_LABEL_TODAY,
                         f"{where}: label_today stays the label #70 recorded, {self.ITEM_17_LABEL_TODAY!r}; the new name "
                         "goes in label_target")
        for item in ("18", "19"):       # #200 renames item 17 only
            self.assertEqual(rows[item]["label_target"], rows[item]["label_today"],
                             f"glow/sf_keep_list.csv item {item}: #200 renames item 17 only; label_target stays "
                             f"{rows[item]['label_today']!r}")

    # --- the plan -------------------------------------------------------------------------------------------

    def test_the_plan_has_rollout_rollback_and_result(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        name = os.path.relpath(self.PLAN, REPO)
        self.assertTrue(os.path.isfile(self.PLAN), f"{name}: no plan for ticket #200 (Rollout, Rollback, Result)")
        rows = self.r.keep()
        dash = rows[ReportingDashboardDocs.DASH]
        text = read(self.PLAN)
        keys, _ = docs_index.frontmatter(text)
        self.assertIn("status", keys, f"{name}: frontmatter `status:`")
        _, problem = docs_index.status_of(keys["status"])
        self.assertIsNone(problem, f"{name}: {problem}")
        self.assertRegex(text.split("\n## ", 1)[0], self.TICKET,
                         f"{name}: name ticket #200 in the frontmatter, the title or the opening paragraph")
        self.assertRegex(text, r"(?m)^## Result\b", f"{name}: no `## Result` section")
        self.assertNotRegex(text, self.EMAIL, f"{name}: counts, ids and names of reports and partners only, no address")

        raw = self.r.plan_part(self.PLAN, "## Rollout", 40)
        where = f"{name}: `## Rollout`"
        cl = sentences(self.norm(raw), ".;")
        for item in self.ITEMS:
            r = rows[item]
            self.assertIn(r["id"], raw, f"{where}: name item {item}'s report {r['label_today']!r} by its Id {r['id']} "
                                        "(its copy to Decommissioned)")
        self.assertIn(dash["id"], raw, f"{where}: name the dashboard {dash['label_today']!r} by its Id {dash['id']}")
        self.assertIn(self.OVERVIEW, raw, f"{where}: the build adds the new report {self.OVERVIEW!r}")
        # the copies: by the tool, VPN off, tagged with the ticket, into Decommissioned, on Ryan's go
        segments = re.split(r"`+|\n\s*\n|\n(?=\s*(?:\$\s*)?python3\s)|(?=\bpython3\s)", raw)
        copies = [flat(s) for s in segments if re.search(r"\bsf_report_folders\.py\s+copy\b", s)]
        self.assertTrue(copies, f"{where}: give the copies' command, `python3 tools/sf_report_folders.py copy --vpn-off "
                                "--kind report --id <id> --tag \"#200\"`")
        for c in copies:
            self.assertIn("--vpn-off", c, f"{where}: the tool refuses to run without `--vpn-off`: {c[:160]!r}")
            self.assertRegex(c, r"--tag[ =]\\?[\"“']?#200\b", f"{where}: each copy carries the ticket, `--tag \"#200\"`: "
                                                             f"{c[:160]!r}")
        self.assertTrue([s for s in cl if re.search(r"(?i)\bcop(y|ies)\b", s) and "Decommissioned" in s
                         and not self.d.denies(s)],
                        f"{where}: the copies go to Decommissioned before the change (one sentence)")
        self.assertTrue([s for s in cl if re.search(r"(?i)\b(dashboard|D5)\b", s) and re.search(r"(?i)\bdynamic\b", s)
                         and re.search(r"(?i)\brefus\w*\b|\bno\s+(API\s+)?cop(y|ies)\b|\bnot\s+(be\s+)?copied\b|"
                                       r"\bcan(not|['’]t)\s+be\s+copied\b", s)],
                        f"{where}: say D5 gets no Decommissioned copy because it is dynamic (the org is at 5), so "
                        "`before/` is its rollback (one sentence)")
        self.assertTrue([s for s in cl if self.stated(s, self.GO) and re.search(r"(?i)\bcop(y|ies)\b|--apply", s)],
                        f"{where}: the copies wait for Ryan's go (one sentence, not negated)")
        self.assertTrue([s for s in cl if self.stated(s, self.GO) and re.search(r"(?i)\bdeploy", s)
                         and not re.search(r"(?i)\bcheck-only\b", s)],
                        f"{where}: the deploy waits for Ryan's go (one sentence, not negated, apart from the check-only)")
        self.assertTrue([s for s in cl if "after/" in s and "build/" in s
                         and re.search(r"(?i)\b(compar\w*|equals?|differ\w*|diff)\b", s)],
                        f"{where}: the read-back retrieves into `after/` and compares it with `build/` (one sentence)")
        # the SOQL checks: the overview month by month, item 19's rows against the 2026 count
        self.assertTrue([s for s in cl if re.search(r"\bSOQL\b|\bSELECT\b", s) and self.NOT_APPROVED.search(s)
                         and re.search(r"(?i)\bmonths?\b|Period__c", s)],
                        f"{where}: check the overview against SOQL, approved and not yet approved month by month (one "
                        "sentence)")
        self.assertTrue([s for s in cl if re.search(r"\bSOQL\b|\bSELECT\b|\bcount\b", s)
                         and "19" in self.r.items_named(s, rows)
                         and re.search(r"\b2026\b|\bIn_Reporting_Year__c\b|(?i:\breporting year\b)", s)],
                        f"{where}: check that item 19's rows equal the 2026 count by SOQL (one sentence naming item 19)")
        # the order, in the numbered steps: before/, copies, check-only, deploy, after/
        steps = self.c.steps(raw, where)
        before = self.c.first(r"\bbefore/", steps, where, "the steps start from a fresh retrieve into `before/`")
        copy_at = [m.start() for m in re.finditer(r"\bsf_report_folders\.py\s+copy\b", steps)]
        self.assertTrue(copy_at, f"{where}: the copies are a numbered step")
        self.assertLess(before, copy_at[0], f"{where}: the `before/` retrieve comes before the copies")
        check_only = [m.start() for m in re.finditer(r"(?i)\bcheck-only\b|--dry-run\b", steps) if m.start() > copy_at[-1]]
        self.assertTrue(check_only, f"{where}: the check-only deploy comes after every copy (copy first, then change)")
        deploys, at = [], 0
        for piece in sentences(steps, ".;,"):
            at = steps.find(piece, at)
            m = re.search(r"(?i)\b(re-?)?deploy\w*", piece)
            # a check-only is no deploy; "deploy ... without `--dry-run`" is one
            if not m or re.search(r"(?i)check-only|(?<!without )(?<!without `)--dry-run|\bvalidat", piece) \
                    or self.d.locally_denied(piece, m) \
                    or re.search(r"(?i)\b(before|until|ahead of|prior to|after|once)\b[^.;,]{0,25}$", piece[:m.start()]) \
                    or re.search(r"(?i)\b(in|at|from)\s+step\s+\d", piece):
                continue
            self.assertGreater(at, check_only[0], f"{where}: nothing is deployed before the check-only (and the "
                                                  f"copies): {piece[:160]!r}")
            deploys.append(at)
        self.assertTrue(deploys, f"{where}: the deploy is a step after the check-only (on Ryan's go)")
        self.assertTrue([m for m in re.finditer(r"\bafter/", steps) if m.start() > deploys[0]],
                        f"{where}: the `after/` read-back comes after the deploy")

        # the rollback: the reports and D5 restored by a deploy, from a fresh retrieve edited back or from #200's own
        # `before/` while a fresh retrieve equals `after/`; the Decommissioned copies are the record of what the
        # reports were, never the restore (D5's components point at the reports themselves)
        raw = self.r.plan_part(self.PLAN, "## Rollback", 15)
        self.assertRollbackOf200(raw, f"{name}: `## Rollback`")

    # --- #200's rollback, in the plan and in the RUNBOOK (review of #200) -------------------------------------

    def runbook_rollback(self):
        """The RUNBOOK part's rollback of #200: from the line that starts `Rollback` and names #200 to the part's end."""
        part = self.r.part()
        m = re.search(r"(?im)^\W*rollback\b[^\n]*#200\b", part)
        self.assertTrue(m, f"RUNBOOK section {ReportingDashboardDocs.PART[4:]!r}: no rollback of #200 (a paragraph "
                           "starting `Rollback of #200`)")
        return part[m.start():]

    def assertRollbackOf200(self, raw, where):
        """#200's rollback: the reports and D5 restored by a deploy, from a fresh retrieve edited back or from #200's
        own `before/` only while a fresh retrieve equals `after/`; the Decommissioned copies only the record of what
        the reports were, never the restore (D5's components point at the reports themselves); never an older build
        or another change's folder unless a negation comes before it; nothing deleted."""
        cl = sentences(self.norm(raw), ".;")
        units = [self.norm(u) for u in self.r.blocks(raw)]
        self.assertTrue([u for u in units if self.REPORTS.search(u) and self.deployed(u) and self.deploy_source(u)],
                        f"{where}: say the reports of items 17-19 are restored by a deploy (after a check-only) from a "
                        "fresh retrieve edited back where #200 changed it, or from their files in #200's `before/` only "
                        "while a fresh retrieve equals `after/`, in one list item or paragraph; their copies in "
                        "Decommissioned are the record, not the restore")
        self.assertTrue([u for u in units if re.search(r"(?i)\b(dashboard|D5)\b", u) and self.deployed(u)
                         and self.deploy_source(u)],
                        f"{where}: say D5 is restored by a deploy of its own file in #200's `before/` only while a fresh "
                        "retrieve equals `after/` (or a fresh retrieve edited back), in one list item or paragraph, not "
                        "negated")
        self.assertTrue([s for s in cl if re.search(r"(?i)\b(never|not|no)\b[^.;]{0,60}?\b(older|old|earlier|previous|"
                                                    r"stale)\s+(\w+\s+)?(build|retrieve)s?\b", s)],
                        f"{where}: say never from an older build or retrieve (DECISIONS 2026-10-16), in one sentence")
        for s in cl:
            for m in self.OLD_SOURCE.finditer(s):       # an older or another change's source only ever denied
                self.assertTrue(self.d.locally_denied(s, m),
                                f"{where}: #200's rollback deploys from #200's own `before/` or a fresh retrieve, never "
                                f"from {m.group(0)!r} (DECISIONS 2026-10-16); name it only after a negation (\"never "
                                f"from …\"): {s[:200]!r}")
            for m in self.FROM_COPY.finditer(s):        # the copies are the record, not the restore
                self.assertTrue(self.d.locally_denied(s, m) or self.d.NEGATION.search(m.group(0)),
                                f"{where}: the reports are not restored from their Decommissioned copies (a copy saved back "
                                f"is a separate report; D5's components point at the reports themselves): {s[:200]!r}")
            if re.search(r"(?i)\bcop(y|ies)\b", s) and "Decommissioned" in s:
                self.assertTrue(re.search(r"(?i)(?<!test )\brecord\b", s) or self.d.denies(s),
                                f"{where}: the copies in Decommissioned are named only as the record of what the reports "
                                f"were (\"… are the record\"), not as the restore: {s[:200]!r}")
        self.r.sweep(raw, where)
        for rx, what in ((r"destructiveChanges", "a `destructiveChanges` deploy"),
                         (r"\bsf project delete\b", "`sf project delete`"),
                         (r"(-X\s*|--method\s+)DELETE\b|\bDELETE\s+/services/", "an HTTP DELETE")):
            self.assertNotRegex(raw, rx, f"{where}: {what} deletes; the rollback restores and deletes nothing")


if __name__ == "__main__":
    unittest.main(verbosity=1)
