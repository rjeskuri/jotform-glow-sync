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

TrainingDashboardDocs (ticket #78): the RUNBOOK's `### GLOW Club Training` names items 13-16 by their labels in
`glow/sf_keep_list.csv` with the `DHIS2__c` field each counts, the period (`Period__c` `LAST_N_MONTHS:12`), the
grouping (Partner `Account__c`, then month), the test-record rule, the dashboard's Partner and Month filters, a
SOQL on `DHIS2__c` per component and the rollback; the plan `docs/plans/<date>-sf-dash-training.md` names #78, its
Rollout copies to Decommissioned, checks-only, waits for Ryan's go, reads `after/` back against `build/` and checks
each component by SOQL; its Rollback restores from the copies or from this change's `before/` only while a fresh
retrieve equals `after/`, never from an older build.
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
    recruited", id `new`, built into the folder by #80) included - the table describes GLOW's list (18
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
            self.assertEqual(label, dash[0]["label_today"],
                             f"{at}: the dashboard label is its current label {dash[0]['label_today']!r} "
                             f"({dash[0]['item']} in `glow/sf_keep_list.csv`; labels do not change, Ryan 2026-10-23), "
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
    and step 8's ledger holds 3 moves; steps 1-8 are said done, steps 9 and 10 neither done nor "not needed"; no
    Result line says failed, rolled back, mismatch, not equal, differs (but the read-back's `showValues` line) or
    still to run (but steps 9 and 10); the PUT's body is in the same command as `--method PUT`; the RUNBOOK says
    "was deployed", not "scheduled" or "still runs"."""

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
        """Items 13-16 of `glow/sf_keep_list.csv`, one row each (the file repeats some rows)."""
        import csv
        with open(self.KEEP_LIST, encoding="utf-8", newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["group"] == self.GROUP and r["kind"] == "report"
                    and r["id"] != "new"]
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
        steps 9 and 10 (item 16, #77, the Subscribe) is still to run."""
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
            later = ([1 for got, _s in self.segments(u, self.STEP_REF) if got & {"9", "10"}]
                     or re.search(r"(?i)\bitem\s+16\b|\bSubscribe\b|(?<![\w#])#(77|80)\b", u))
            if not later and self.stated(n, self.STILL_TO_RUN):
                found.append(f"still to run: {u[:160]!r}")
        self.assertEqual(found, [], f"{where}: steps 1-8 ran and every count equals SOQL (2026-10-26); the Result says "
                                    "otherwise: " + "; ".join(found[:3]))

    def test_the_training_plan_is_in_progress_with_steps_9_and_10_left(self):
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
        self.assertEqual(word, "in-progress", f"{name}: `status:` stays `in-progress` while step 9 waits for #77")
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
        missing = sorted({str(i) for i in range(1, 9)} - done, key=int)
        self.assertEqual(missing, [], f"{where}: say steps 1-8 are done (\"steps 1-8 done, 2026-10-26\"); not said "
                                      f"of step(s) {', '.join(missing)}")
        # steps 9 and 10: still to run, step 9 after #77
        self.assertTrue([u for got, u, _seg in steps if "9" in got and re.search(r"(?<![\w#])#77\b", u)
                         and self.stated(self.norm(u), self.REMAINS)],
                        f"{where}: say step 9 (item 16) remains, after #77 lands")
        self.assertTrue([u for got, u, _seg in steps if "10" in got and self.stated(self.norm(u), self.REMAINS)]
                        + [u for u in units if re.search(r"(?i)\bSubscribe\b", u)
                           and self.stated(self.norm(u), self.REMAINS)],
                        f"{where}: say step 10 (the weekly Subscribe) remains")
        over = [seg for got, _u, seg in steps if got & {"9", "10"} and self.stated(self.norm(seg), self.NOT_LEFT)]
        self.assertEqual(over, [], f"{where}: steps 9 and 10 are still to run (step 9 after #77); none is done or "
                                   f"not needed: {over[:1]}")
        # what a reference to steps 2-8 says, to the next step reference, never waits
        waits = [seg for got, _u, seg in steps if got & {str(i) for i in range(2, 9)}
                 and self.stated(self.norm(seg), self.STILL_TO_RUN)]
        self.assertEqual(waits, [], f"{where}: steps 1-8 are done (2026-10-26); none of them waits: {waits[:1]}")
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


if __name__ == "__main__":
    unittest.main(verbosity=1)
