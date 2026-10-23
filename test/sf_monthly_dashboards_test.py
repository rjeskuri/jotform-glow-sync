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


if __name__ == "__main__":
    unittest.main(verbosity=1)
