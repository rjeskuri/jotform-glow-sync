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

RetiredReportsDocs (ticket #72): the RUNBOOK's `### Decommissioned` records the retirement (its date, 29
reports and 10 dashboards moved, the 19 held for #75-#79, the ledger `data/sf_retire_2026-10-23/ledger.csv`)
and how to bring an item back; the plan `docs/plans/<date>-sf-retire-reports.md` names #72, its Rollout has
the dry run, `--limit 1`, Ryan's go, the dashboards by hand and the SOQL check by Id, its Rollback is the
tool's undo from that ledger and deletes nothing, and its Result gives the counts.
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
    NOOP_ROWS = ("00ORP000005rT932AE", "00ORP000005gxSD2AY")   # a second row, Decommissioned to Decommissioned
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
                                           "Decommissioned to Decommissioned (a repeated `--limit 1` run)")
        soql = [s for s in sentences(result, ".;:") if self.SOQL.search(s)]
        self.assertTrue([s for s in sentences(result, ".;") if self.stated(s, self.SOQL) and "Decommissioned" in s],
                        f"{where} gives the SOQL read-back of Decommissioned, in one sentence")
        self.assertEqual([s for s in soql if not self.stated(s, self.SOQL)], [],
                         f"{where}: the SOQL read-back was run; no sentence denies it")
        self.assertNoDashboardsStay(result_raw, where)
        self.assertCountsTrue(result_raw, where)
        self.assertNoHedge(result_raw, where)
        self.d.assertNoContradiction(result_raw, where)


if __name__ == "__main__":
    unittest.main(verbosity=1)
