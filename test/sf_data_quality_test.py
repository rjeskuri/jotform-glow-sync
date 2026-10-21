#!/usr/bin/env python3
"""
Data quality in Salesforce, epic #68: the "Duplicate Record" and "Obsolete Record" flags on Account
and Contact and the Account matching and duplicate rules (ticket #84; the flagging batch is #85).

DuplicateRuleDocs (ticket #84): the RUNBOOK's new section `## Duplicate and obsolete records in
Salesforce` states the working definitions Ryan gave on 2026-10-21 (a duplicate Account: the same
name ignoring capitals and spacing, the same parent and the same record type, the deliberate
`<club> - <partner>` names never matching; an obsolete Account: a partner Archived, a club
deactivated in the Roster or without an attendance batch for 6 months and created more than 6 months
ago; an obsolete Contact: a Participant without attendance for 12 months, staff, mentors and
coordinators never), the four fields, the two rules and their action - Allow with Report only, no
Alert and no Block, because an alert refuses a record created by code (BACKLOG 54: the attendance
processor, tools/sf_new_clubs.py) - the Contact rule "First & Last & Account" unchanged,
administrators alone setting a flag by hand, flagged records shown in the kept reports with the flags
as a filter; a plan carries the rolled-back `sf apex run` proof before the deploy, the check-only,
Ryan's go, the read-back and the next day's batch check, and its Rollback deactivates the rule; a
dated DECISIONS entry records the definitions as Ryan's provisional answers pending GLOW; the
salesforce skill points at the section. Every part a test reads is swept for what would contradict
the rules (contradictions()): the rule set to Alert or Block (said any way, unless denied where it is
said, without a time limit), a flagged record deleted, merged or kept out of the reports, a softener
on the proof, the check-only, the go or the read-back. Counts and ids only: no figure from the org
is pinned.

DuplicateAccountGroups: glow.salesforce.duplicate_account_groups(accounts), the Python side of the
Account matching rule for the read-back and the monthly check - the groups of Accounts the rule
would report, computed from `SELECT Id, Name, ParentId, RecordTypeId FROM Account` - over fictional
accounts with every criterion varied on its own.
"""
import copy
import glob
import os
import re
import sys
import unittest

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import REPO, flat, md_part, read, sentences
from glow import salesforce


class DuplicateRuleDocs(unittest.TestCase):
    """Ticket #84 (Ryan, 2026-10-21: "move forward with this" - the working answers, used until GLOW
    says otherwise). The docs side of the flags and the Account duplicate rule."""

    longMessage = False         # the messages say what to fix; the whole section is not repeated
    RUNBOOK = os.path.join(REPO, "docs", "RUNBOOK.md")
    DECISIONS = os.path.join(REPO, "docs", "DECISIONS.md")
    SKILL = os.path.join(REPO, ".claude", "skills", "salesforce", "SKILL.md")
    PLANS = os.path.join(REPO, "docs", "plans", "*-sf-duplicate-obsolete-flags.md")
    SECTION = "## Duplicate and obsolete records in Salesforce"
    GIRLS = "Duplicate girls in Salesforce"          # the merge path, which flagging leaves alone
    CONTACT_RULE = "First & Last & Account"
    FIELDS = ("Duplicate_Record__c", "Obsolete_Record__c")
    TICKET = re.compile(r"(?<![\w#])#84\b")
    BATCH_TICKET = re.compile(r"(?<![\w#])#85\b")
    Q, QE = "[\"“]", "[\"”]"               # straight and curly double quotes

    # a statement that denies what it names
    NEGATION = re.compile(r"\b(not|no|never|nothing|none|nor|neither|without|no longer|instead of|rather than)\b|"
                          r"n['’]t\b", re.I)
    # the rules themselves ("no Alert", "never merged", "no attendance batch for 6 months"), not a denial of
    # what the sentence states
    RULE_IDIOM = re.compile(r"\b(never|not|nothing|no|without|instead of|rather than|nor)\b[^.;,]{0,25}?"
                            r"\b(alert|block|warn|delet|merg|exclud|stop|refus|reject|flag|match)\w*|"
                            r"\b(no|without)\s+(an?\s+)?(attendance|batch(es)?|Monthly Reports?|parent|partner|"
                            r"submission)\b", re.I)
    REPORT_ONLY = re.compile(r"(?i)\breports?\b[^.;]{0,10}?\bonly\b")
    ALERT_DENIED = re.compile(r"(?i)\b(no|without|never|not|nor)\s+(an?\s+|the\s+)?alert")
    BLOCK_DENIED = re.compile(r"(?i)\b(no|without|never|not|nor|or)\s+(an?\s+|the\s+)?block")   # "never Alert or Block"
    ACCOUNT = r"(?<!\w)Accounts?(?![A-Za-z])"         # also in `Account_Duplicate_Record__c` (norm() joins the dot)
    CONTACT = r"(?<!\w)Contacts?(?![A-Za-z])"
    # the criteria say "the same parent" and "the same record type" ("under any parent" is another rule)
    SAME_PARENT = r"(?i)\b(same|one|identical)\s+(\w+\s+)?parent\b|\bparent\b\s+(is|are|being|stays?)\s+(the same|identical|equal)\b"
    SAME_TYPE = (r"(?i)\b(same|one|identical)\s+(\w+\s+)?record type\b|"
                 r"\brecord type\b\s+(is|are|being|stays?)\s+(the same|identical|equal)\b")

    # --- the contradiction sweep -----------------------------------------------------------------------
    # the rule's action, said any way ("the rule alerts", "set to Alert", "Allow + Alert", "Block on edit",
    # "warns the user"); allowed: a denial where it is said ("no Alert", "never blocks"), or the cost as a
    # noun with its consequence ("an alert refuses a record created by code", "the Alert would need ...")
    ACTION = re.compile(r"(?i)\b(alert(s|ed|ing)?|block(s|ed|ing)?|warn(s|ed|ing|ings)?)\b")
    ARTICLE = re.compile(r"(?i)\b(an?|the|that|this|such an?|any|each|every|which|its)\s+$")
    SETS = re.compile(r"(?i)\b(set|sets|setting|action\w*|operation\w*|option\w*|configur\w*|chos\w*|choose|"
                      r"switch\w*|chang\w*|turn\w*|rais\w*|mode|use|uses|using|with|plus|to|on|at|as|is|are|be|"
                      r"becomes?|stays?|remains?|keeps?|kept|means)\s+(an?\s+|the\s+)?$")
    CONSEQUENCE = re.compile(r"(?i)\b(would|could|will|can|refus\w*|fail\w*|stop\w*|reject\w*|cost\w*|need\w*|"
                             r"requir\w*|mean\w*|is why|was why|hit|hits|broke|breaks|precedent)\b")
    # a denial with a time limit ("no Alert for now", "never blocks until GLOW decides") is no denial
    TIME_LIMIT = re.compile(r"(?i)\b(until|after|later|afterwards|eventually|then|days?|weeks?|months?|years?|"
                            r"for now|at first|initially|to start|to begin with|meanwhile|temporar\w*)\b")
    # flagged records removed, merged or kept out of the reports
    FLAGGED = re.compile(r"(?i)\bflag\w*|Duplicate_Record__c|Obsolete_Record__c|[\"“](Duplicate|Obsolete) Record"
                         r"[\"”]|\b(duplicate|obsolete)s?\s+(?!rules?\b)(\w+\s+){0,2}?(records?|accounts?|contacts?|"
                         r"girls?|partners?|clubs?|rows?)\b")
    REMOVAL = re.compile(r"(?i)\bdelet\w*|\bmerg\w*|\bpurg\w*|\beras\w*|\bwip(e|es|ed|ing)\b|\bdestroy\w*|"
                         r"\brecycle bin\b|\bremov\w*|\bexclud\w*|\bleft out\b|\bleaves? out\b|\bhid(e|es|den|ing)\b|"
                         r"\bdrop\w*|\bfilter(ed|s)? out\b|\bomit\w*|\bclean\w* (up|out)\b")
    # removing a field or a flag itself is not removing a record
    FIELD_OR_FLAG = re.compile(r"(?i)\b(delet|remov)\w*\s+(the\s+|an?\s+|its\s+|their\s+|both\s+|all\s+|four\s+|new\s+|"
                               r"each\s+|every\s+)*(\w+\s+){0,3}?(fields?|flags?|checkbox(es)?)\b|"
                               r"\b(fields?|flags?)\b[^.;,]{0,30}?\b(delet|remov|clear)\w*")
    # what makes the proof, the check-only, the go or the read-back optional
    SOFTENER = re.compile(r"(?i)\b(skip\w*|optional(ly)?|if you\b|unless|in a hurry|not needed|need not|needn['’]t|"
                          r"no need|whenever|sometimes|ideally|if (there is )?time|when convenient|without waiting|"
                          r"straight to production|just kidding|at your discretion|if possible|where possible|"
                          r"when possible|as time allows|may be omitted|can be omitted)\b")
    NO_ROLLBACK = re.compile(r"(?i)\bno rollback\b|\bnothing to roll back\b|\bcannot be rolled back\b|"
                             r"\bno way (back|to roll back)\b")

    def denies(self, text):
        return bool(self.NEGATION.search(self.RULE_IDIOM.sub(" ", text)))

    def locally_denied(self, s, m):
        """A negation in the words before match `m` of clause `s`, back to the last comma, dash, bracket or
        "but"."""
        return bool(self.NEGATION.search(self.local(s, m)))

    @staticmethod
    def local(s, m):
        return re.split(r"[,;:—–(]|\bbut\b|\bhowever\b|\bactually\b", s[max(0, m.start() - 40):m.start()])[-1]

    def alert_or_block(self, s):
        out = []
        for m in self.ACTION.finditer(s):
            local = self.local(s, m)
            post = re.split(r"[,;:—–()]", s[m.end():])[0]
            if self.NEGATION.search(local):
                if self.TIME_LIMIT.search(local) or self.TIME_LIMIT.search(post):
                    out.append(f"denies {m.group(0)!r} with a time limit: {s[:160]!r}")
                continue
            if self.ARTICLE.search(local) and not self.SETS.search(local) and self.CONSEQUENCE.search(s[m.end():]):
                continue        # the cost: "an alert refuses a record created by code"
            out.append(f"sets the rule to {m.group(0)!r}: {s[:160]!r}")
        return out

    def contradictions(self, text, rollback=False):
        """The clauses of `text` that contradict the rules: the rule's action is Alert or Block (not denied
        where it is said, or denied with a time limit); a flagged, duplicate or obsolete record deleted,
        merged, hidden or excluded (not denied; a field or the flag itself may be removed; the merge path of
        `tools/sf_dupes.py` is its own); a softener not itself denied. With `rollback`, "no rollback" is one."""
        out = []
        girls = re.compile(self.Q + re.escape(self.GIRLS) + self.QE)
        for s in self.clauses(text, ".;:?!"):
            kept = girls.sub(" ", s)
            out += self.alert_or_block(kept)
            if "sf_dupes" not in kept and self.FLAGGED.search(kept):
                scrubbed = self.FIELD_OR_FLAG.sub(" ", kept)
                for m in self.REMOVAL.finditer(scrubbed):
                    if not self.locally_denied(scrubbed, m):
                        out.append(f"removes, merges or hides flagged records ({m.group(0)!r}): {s[:160]!r}")
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
        self.assertEqual(found, [], f"{where}: contradicts the rules (the Account rule is Report only, never Alert or "
                                    "Block - name Alert or Block only to deny them or as the cost, `an alert refuses a "
                                    "record created by code`; a flagged record is never deleted, merged, hidden or "
                                    "excluded; the proof, the check-only, the go and the read-back are never "
                                    "optional): " + "; ".join(found))

    # --- reading the docs ---------------------------------------------------------------------------------

    @staticmethod
    def norm(text):
        """`text` flattened, a dot inside a name (`Account.Duplicate_Record__c`) made `_`, so `[^.]` spans it."""
        return re.sub(r"(?<=\w)\.(?=\w)", "_", flat(text))

    def clauses(self, text, ends=".;"):
        return sentences(self.norm(text), ends)

    def said(self, text, *patterns, ends=".;", negated=False):
        """The clauses of `text` that match every pattern and are not negated (unless `negated`: the
        statement is a denial itself)."""
        return [s for s in self.clauses(text, ends)
                if all(re.search(p, s) for p in patterns) and (negated or not self.denies(s))]

    def section(self):
        return md_part(self.RUNBOOK, self.SECTION)

    def plan_path(self):
        found = sorted(glob.glob(self.PLANS))
        self.assertEqual(len(found), 1, "docs/plans/: one plan `YYYY-MM-DD-sf-duplicate-obsolete-flags.md` for ticket "
                                        f"#84 (found {[os.path.basename(p) for p in found]})")
        self.assertRegex(os.path.basename(found[0]), r"^\d{4}-\d\d-\d\d-sf-duplicate-obsolete-flags\.md$",
                         "docs/plans/: the plan is named `YYYY-MM-DD-sf-duplicate-obsolete-flags.md`")
        return found[0]

    def steps(self, text):
        """The numbered steps of a Rollout (`1. …` at a line start or inline, as the plans write them)."""
        parts = re.split(r"(?:^|(?<=\s))\d{1,2}\.\s+(?=[A-Z`*\"“(])", flat(text))
        return [self.norm(p) for p in parts[1:]]

    def decision(self):
        entries = re.split(r"(?m)^(?=### )", read(self.DECISIONS))[1:]
        new = [e for e in entries if re.match(r"### (\d{4}-\d\d-\d\d) ", e)
               and re.match(r"### (\d{4}-\d\d-\d\d) ", e).group(1) >= "2026-10-21"
               and self.TICKET.search(e) and re.search(r"(?i)\bduplicate\b", e) and re.search(r"(?i)\bobsolete\b", e)]
        self.assertTrue(new, "docs/DECISIONS.md: no dated entry (`### 2026-10-21 — …`, or later) naming ticket #84 and "
                             "the duplicate and obsolete definitions")
        return new[0]

    def skill_item(self):
        items = re.findall(r"(?m)^- .*(?:\n(?!- |\n|#).*)*", read(self.SKILL))
        title = re.compile(self.Q + re.escape(self.SECTION[3:]) + self.QE)
        found = [i for i in items if title.search(flat(i))]
        self.assertTrue(found, ".claude/skills/salesforce/SKILL.md: no `- …` item under \"What lives there\" that names "
                               f"the RUNBOOK section {self.SECTION[3:]!r} in double quotes")
        return found[0]

    # --- the RUNBOOK section ----------------------------------------------------------------------------

    def test_the_runbook_defines_duplicate_and_obsolete(self):
        where = f"RUNBOOK section {self.SECTION[3:]!r}"
        part = self.section()
        # a duplicate Account, in one sentence
        self.assertTrue(self.said(part, r"(?i)\bname\b", r"(?i)\b(capitals?|case)\b", r"(?i)\b(spacing|whitespace|spaces)\b",
                                  self.SAME_PARENT, self.SAME_TYPE),
                        f"{where}: define a duplicate Account in one sentence (not negated): the same name ignoring "
                        "capitals and spacing, the same parent and the same record type")
        self.assertTrue(self.said(part, r"<club> - <partner>", r"(?i)\b(never|not|no)\b[^.;]{0,30}?\bmatch", negated=True),
                        f"{where}: say the deliberate `<club> - <partner>` names never match (RUNBOOK, the clubs two "
                        "partners share)")
        # an obsolete Account: an Archived partner; a club deactivated in the Roster, or without an attendance
        # batch for 6 months and created more than 6 months ago
        self.assertTrue(self.said(part, r"Partner_Status__c", r"\bArchived\b", r"(?i)\bobsolete\b"),
                        f"{where}: say an obsolete Account is a partner whose `Partner_Status__c` is Archived, in one "
                        "sentence with the word obsolete")
        self.assertTrue(self.said(part, r"(?i)\bclub\b", r"(?i)\bdeactivated\b", r"(?i)\bRoster\b"),
                        f"{where}: say a Club account whose club is deactivated in the Roster is obsolete")
        self.assertTrue(self.said(part, r"(?i)\b(6|six) months\b", r"(?i)\b(attendance|batch)", r"(?i)\bcreated\b"),
                        f"{where}: say a Club account with no attendance batch for 6 months AND created more than 6 "
                        "months ago is obsolete, in one sentence (the September 2026 clubs are not flagged before "
                        "March 2027)")
        # an obsolete Contact: a Participant (girl) with no attendance in 12 months; staff, mentors and
        # coordinators never by rule
        self.assertTrue(self.said(part, r"(?i)\b(participants?|girls?)\b", r"(?i)\b(12|twelve) months\b", r"(?i)\battendance\b"),
                        f"{where}: say an obsolete Contact is a Participant (a girl) with no attendance in 12 months, "
                        "in one sentence")
        self.assertTrue(self.said(part, r"(?i)\bstaff\b", r"(?i)\bmentors?\b", r"(?i)\bcoordinators?\b",
                                  r"(?i)\b(never|not|no)\b[^.;]{0,30}?\bflag", negated=True),
                        f"{where}: say staff, mentor and coordinator contacts are never flagged by rule, in one sentence")
        # a duplicate Contact: the existing rule's duplicate record sets, flagged by the batch (#85)
        self.assertTrue(self.said(part, self.BATCH_TICKET.pattern, self.CONTACT, r"(?i)duplicate record sets?|DuplicateRecordSet"),
                        f"{where}: say the Contact's Duplicate Record flag is set by the batch (#85) when the Contact "
                        "sits in one of the Contact rule's duplicate record sets, in one sentence")
        self.assertNoContradiction(part, where)

    def test_the_runbook_names_the_four_fields_and_who_may_set_them(self):
        where = f"RUNBOOK section {self.SECTION[3:]!r}"
        part = self.section()
        text = self.norm(part)
        self.assertTrue(self.said(part, self.FIELDS[0], self.FIELDS[1], self.ACCOUNT, self.CONTACT),
                        f"{where}: name the four fields in one sentence: `Duplicate_Record__c` and `Obsolete_Record__c` "
                        "on Account and on Contact")
        for label in ("Duplicate Record", "Obsolete Record"):
            self.assertRegex(text, self.Q + label + self.QE, f"{where}: give the field label {label!r} in double quotes")
        self.assertTrue(self.said(part, r"(?i)\bdefault\b", r"(?i)\b(false|unchecked|off)\b"),
                        f"{where}: say the fields are checkboxes, default false (unchecked)")
        self.assertRegex(text, r"MatchingRule|Matching Rule", f"{where}: name the Matching Rule on Account")
        self.assertTrue(self.said(part, r"(?i)\b(duplicate rule|DuplicateRule)\b", r"(?i)\b(creat|insert)\w*", r"(?i)\b(edit|updat)\w*"),
                        f"{where}: say the Duplicate Rule on Account runs on create and on edit, in one sentence")
        # who sets a flag by hand: administrators only; report users read
        self.assertTrue(self.said(part, r"(?i)\badministrators?\b", r"(?i)\b(only|alone)\b", r"(?i)\bflag"),
                        f"{where}: say only administrators set or clear a flag by hand, in one sentence")
        self.assertTrue(self.said(part, r"(?i)\bread\b", r"(?i)\breport\w*|\bviewer\w*|Attendance_Report_Viewer|permission set|profile",
                                  r"(?i)\bflag"),
                        f"{where}: say the users who read the reports can read the flags (Read on the fields), in one "
                        "sentence")
        # the kept reports: flagged records shown, the flags a filter, nothing excluded by default
        self.assertTrue(self.said(part, r"(?i)\bshown\b|\bstays? in\b|\bremains? in\b|\bstill\b", r"(?i)\bfilter\b", r"(?i)\breports?\b"),
                        f"{where}: say flagged records are shown in the kept reports, with the flags as a filter, in "
                        "one sentence")
        self.assertTrue(self.said(part, r"(?i)\b(nothing|never|not|no)\b[^.;]{0,30}?\b(exclud\w*|left out|hidden|dropped)",
                                  r"(?i)\bdefault\b", negated=True),
                        f"{where}: say nothing is excluded by default")
        self.assertRegex(flat(part), r"plans/\d{4}-\d\d-\d\d-sf-duplicate-obsolete-flags\.md",
                         f"{where}: link the plan `docs/plans/<date>-sf-duplicate-obsolete-flags.md`")
        for line in ("Verify", "Rollback"):
            self.assertRegex(part, r"\*\*" + line + r":?\*\*", f"{where}: the section's header lines carry `- **{line}:**`")
        self.assertNoContradiction(part, where)

    def test_the_account_rule_never_stops_records_created_by_code(self):
        where = f"RUNBOOK section {self.SECTION[3:]!r}"
        part = self.section()
        text = self.norm(part)
        self.assertTrue([s for s in self.clauses(part) if self.REPORT_ONLY.search(s) and self.ALERT_DENIED.search(s)
                         and self.BLOCK_DENIED.search(s)],
                        f"{where}: state the rule's action in one sentence: Allow with Report only, no Alert and no Block")
        self.assertIn("Allow", text, f"{where}: name the metadata's action `Allow` (`actionOnInsert`, `actionOnUpdate`)")
        self.assertRegex(text, r"(?i)\battendance processor\b|AttendanceBatchProcessor",
                         f"{where}: name the attendance processor (its partner-less Club accounts are records created by code)")
        self.assertIn("tools/sf_new_clubs.py", flat(part), f"{where}: name `tools/sf_new_clubs.py` (records created by code)")
        self.assertRegex(text, r"BACKLOG 54", f"{where}: give the precedent, BACKLOG 54 (the Contact rule's Alert failed live "
                                              "attendance batches)")
        self.assertTrue([s for s in self.clauses(part) if re.search(r"(?i)\b(an|the) alert\b", s)
                         and re.search(r"(?i)\b(refus|fail|stop|reject)\w*", s)
                         and re.search(r"(?i)\b(code|processor|automation|sync|integration)\b", s)],
                        f"{where}: say why in one sentence: an alert refuses (fails) a record created by code")
        self.assertTrue(self.said(part, r"(?i)\b(never|not|no)\b[^.;]{0,30}?\b(stop|refus|reject|fail|block)\w*",
                                  r"(?i)\b(code|processor|sync|integration|automation)\b", negated=True),
                        f"{where}: say the rule never stops a record created by code, in one sentence")
        self.assertIn("DUPLICATES_DETECTED", text,
                      f"{where}: the Verify names the error code `DUPLICATES_DETECTED` that no batch may fail with")
        self.assertNoContradiction(part, where)

    def test_the_contact_rule_stays_report_only(self):
        where = f"RUNBOOK section {self.SECTION[3:]!r}"
        part = self.section()
        unchanged = re.compile(r"(?i)\bunchanged\b|\buntouched\b|\bnot (been )?changed\b|\bnever changed\b|\bstays?\b|"
                               r"\bremains?\b|\bkept\b|\bkeeps?\b|\bas it is\b|\bas is\b")
        self.assertTrue([s for s in self.clauses(part) if self.CONTACT_RULE in s and re.search(self.CONTACT, s)
                         and unchanged.search(s)],
                        f"{where}: say the existing Contact rule {self.CONTACT_RULE!r} is unchanged, in one sentence")
        self.assertTrue([s for s in self.clauses(part) if self.CONTACT_RULE in s and self.REPORT_ONLY.search(s)
                         and re.search(r"2026-10-01|BACKLOG 54", s)],
                        f"{where}: say {self.CONTACT_RULE!r} has been Report only since 2026-10-01 (BACKLOG 54), in one "
                        "sentence")
        self.assertTrue(self.said(part, r"sf_dupes", r"(?i)\bunchanged\b|\bnot change\w*|\bnever change\w*|\bits own key\b|"
                                                     r"\buntouched\b|\bno change\b|\bleaves?\b|\bas it is\b"),
                        f"{where}: say the merge of one girl's duplicate contacts (`tools/sf_dupes.py`, its own key) is "
                        "unchanged by the flags, in one sentence")
        self.assertNoContradiction(part, where)

    # --- the plan ---------------------------------------------------------------------------------------

    def test_a_plan_carries_the_rule_deploy_and_the_rolled_back_proof(self):
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
                         f"{name}: name ticket #84 in the frontmatter, the title or the opening paragraph")
        self.assertRegex(text, r"(?m)^## Result\b", f"{name}: no `## Result` section")
        raw, bodies = {}, {}
        for heading, least in (("## Rollout", 60), ("## Rollback", 15)):
            part = md_part(path, heading)
            raw[heading] = part.split("\n", 1)[1] if "\n" in part else ""
            body = self.norm(raw[heading])
            self.assertNotRegex(body, r"(?i)\b(TBD|TODO|TBA|FIXME)\b", f"{name}: `{heading}` is a placeholder")
            distinct = {w.lower() for w in re.findall(r"[A-Za-z]\w*", body)}
            self.assertGreaterEqual(len(distinct), least,
                                    f"{name}: `{heading}` says too little (at least {least} distinct words)")
            bodies[heading] = body
        rollout, rollback = raw["## Rollout"], raw["## Rollback"]
        flat_rollout = bodies["## Rollout"]
        # what is built: a fresh retrieve, the four fields, the two rules, Report only
        self.assertRegex(flat_rollout, r"data/sf_\w+_\d{4}-\d\d-\d\d/before/",
                         f"{name}: the Rollout starts from a fresh retrieve into `data/sf_<topic>_<date>/before/`")
        self.assertTrue(self.said(rollout, self.FIELDS[0], self.FIELDS[1], self.ACCOUNT, self.CONTACT),
                        f"{name}: the Rollout names the four fields (`Duplicate_Record__c`, `Obsolete_Record__c` on "
                        "Account and Contact) in one sentence")
        self.assertRegex(flat_rollout, r"MatchingRule|Matching Rule", f"{name}: the Rollout builds the Matching Rule on Account")
        self.assertRegex(flat_rollout, r"DuplicateRule|Duplicate Rule", f"{name}: the Rollout builds the Duplicate Rule on Account")
        self.assertTrue([s for s in self.clauses(rollout) if self.REPORT_ONLY.search(s) and self.ALERT_DENIED.search(s)
                         and self.BLOCK_DENIED.search(s)],
                        f"{name}: the Rollout states the rule's action in one sentence: Allow with Report only, no Alert "
                        "and no Block")
        self.assertIn("Allow", flat_rollout, f"{name}: the Rollout gives the metadata's action `Allow`")
        self.assertTrue(self.said(rollout, r"(?<!\w)Edit(?!\w)", r"(?i)\badministrators?\b"),
                        f"{name}: the Rollout gives Edit on the fields to administrators (one sentence)")
        self.assertTrue(self.said(rollout, r"(?<!\w)Read(?!\w)", r"(?i)\breport\w*|\bviewer\w*|Attendance_Report_Viewer|"
                                                                   r"permission set|profile"),
                        f"{name}: the Rollout gives Read on the fields to the users who read the reports (one sentence)")
        # the steps, numbered: check-only, Ryan's go, deploy, then the rolled-back proof at once (a
        # DuplicateRecordSet appears only while the rule is active: the proof runs with the rule live, and a
        # refused insert means the Rollback), the read-back, the next day's check
        steps = self.steps(rollout)
        self.assertGreaterEqual(len(steps), 4, f"{name}: number the Rollout's steps (`1. …`, at least four)")
        proof = [i for i, s in enumerate(steps) if "sf apex run" in s]
        self.assertTrue(proof, f"{name}: a Rollout step runs the proof with `sf apex run`")
        deploy = [i for i, s in enumerate(steps) if re.search(r"sf project deploy (quick|start)\b(?![^.;]{0,60}--dry-run)", s)]
        self.assertTrue(deploy, f"{name}: a Rollout step deploys with `sf project deploy quick -o glow -i <validation id>` "
                                "(or `start` without `--dry-run`)")
        self.assertLess(deploy[0], proof[0], f"{name}: the `sf apex run` proof is the step right after the deploy: the "
                                             "rule must be active for a DuplicateRecordSet to appear and for the proof "
                                             "to show the rule stops neither insert (a refused insert means the Rollback)")
        check = [i for i, s in enumerate(steps) if re.search(r"(?i)check-only|--dry-run|sf project deploy validate", s)]
        self.assertTrue(check and check[0] <= deploy[0], f"{name}: the check-only (`sf project deploy validate` or "
                                                        "`--dry-run`) comes before the deploy")
        go = [i for i, s in enumerate(steps) if re.search(r"Ryan['’]s go\b", s)]
        self.assertTrue(go and go[0] <= deploy[0], f"{name}: the deploy waits for Ryan's go (a step at or before it)")
        proof_text = " ".join(steps[proof[0]:proof[0] + 2])
        self.assertIn("Database.rollback", flat(rollout), f"{name}: the proof's script ends in `Database.rollback`")
        self.assertRegex(proof_text, r"(?i)\b(refus|fail|reject)\w*[^.;]{0,80}?\b(deactivat\w*|rollback)\b|"
                                     r"\b(deactivat\w*|rollback)\b[^.;]{0,80}?\b(refus|fail|reject)\w*",
                         f"{name}: the proof step says a refused insert means the Rollback (deactivate the rule) at once")
        self.assertTrue([s for s in self.clauses(proof_text, ".;") if "Database_rollback" in s
                         and re.search(r"(?i)\b(ends?|ending|last|final|closes?)\b", s)],
                        f"{name}: say the proof's script ends in `Database.rollback` (one sentence of the proof step)")
        self.assertRegex(proof_text, r"(?i)pasted? in full|in full first",
                         f"{name}: the proof's script is pasted in full first (the gate)")
        self.assertTrue(self.said(proof_text, r"(?i)\b(two|2|both)\b", r"(?i)\bfictional\b", self.ACCOUNT),
                        f"{name}: the proof inserts two fictional Accounts that meet the criteria (one sentence)")
        self.assertRegex(proof_text, r"DuplicateRecordSet", f"{name}: the proof shows a `DuplicateRecordSet` holding both")
        self.assertTrue(self.said(proof_text, r"<club> - <partner>", r"(?i)\b(never|not|no)\b[^.;]{0,30}?\bmatch", negated=True),
                        f"{name}: the proof shows an Account that only shares a name with another partner's club "
                        "(`<club> - <partner>`) is not matched")
        self.assertTrue(self.said(proof_text, r"(?i)\b(both|two|2)\b", r"(?i)\binserts?\b|\bDML\b", r"(?i)\bsucceed\w*"),
                        f"{name}: the proof shows both inserts succeed (the rule stops neither)")
        # the read-back: retrieve into after/ and compare; both rules active, four fields; the Contact rule the same
        after = [i for i, s in enumerate(steps) if "after/" in s and re.search(r"(?i)\bcompar\w*|\bdiff\b", s)]
        self.assertTrue(after and after[0] >= deploy[0], f"{name}: after the deploy, retrieve into `after/` and compare")
        self.assertRegex(flat_rollout, r"(?i)\b(both rules|the two rules|DuplicateRule and MatchingRule|MatchingRule and DuplicateRule)\b"
                                       r"[^.;]{0,60}?\bactive\b|\bactive\b[^.;]{0,60}?\b(both rules|the two rules)\b|IsActive",
                         f"{name}: the read-back's SOQL shows both rules active")
        self.assertTrue([s for s in self.clauses(rollout) if self.CONTACT_RULE in s
                         and re.search(r"(?i)\bunchanged\b|\bcompar\w*|\bdiff\b|\bequal\w*|\bthe same\b|\buntouched\b", s)],
                        f"{name}: the Rollout retrieves and compares the Contact rule {self.CONTACT_RULE!r}: unchanged")
        self.assertTrue(self.said(rollout, r"duplicate_account_groups", r"DuplicateRecordSet|DuplicateRecordItem"),
                        f"{name}: the read-back compares `glow.salesforce.duplicate_account_groups` with the rule's "
                        "`DuplicateRecordSet`s (one sentence)")
        # the next day
        day_after = [i for i, s in enumerate(steps) if "DUPLICATES_DETECTED" in s and "Failed" in s
                     and re.search(r"(?i)\bnext day\b|\bday after\b|\bfollowing day\b|\btomorrow\b|\b24 hours\b", s)]
        self.assertTrue(day_after and day_after[0] > proof[0],
                        f"{name}: the next day's step (after the proof) checks that no batch is `Failed` with "
                        "`DUPLICATES_DETECTED`")
        self.assertIn("auto_sync", flat_rollout, f"{name}: the next day's step checks the Salesforce plan of "
                                                 "`tools/auto_sync.py` is unchanged")
        self.assertNoContradiction(rollout, f"{name}: `## Rollout`")
        # the Rollback deactivates the rule
        self.assertTrue(self.said(rollback, r"(?i)\bdeactivat\w*|\binactive\b|isActive>?\s*false|active\s*=\s*false",
                                  r"(?i)\brule\b"),
                        f"{name}: the Rollback deactivates the Duplicate Rule (one sentence, not negated)")
        self.assertNoContradiction(rollback, f"{name}: `## Rollback`", rollback=True)

    # --- DECISIONS and the skill ------------------------------------------------------------------------

    def test_a_decision_records_glows_definitions(self):
        e = self.decision()
        where = f"docs/DECISIONS.md {e.split(chr(10), 1)[0][4:14]}"
        for part in ("**Why", "**Rejected", "**Consequences"):
            self.assertIn(part, e, f"{where}: no {part}** bullet (the file's header)")
        why = e.split("**Why", 1)[1].split("**Rejected", 1)[0]
        self.assertRegex(why, r"\bRyan\b", f"{where}: **Why** gives Ryan's words")
        self.assertRegex(self.norm(why), r"(?i)move forward", f"{where}: **Why** quotes Ryan (\"move forward with this\")")
        # the answers are Ryan's, provisional, pending GLOW's own definitions
        self.assertTrue(self.said(e, r"(?i)\b(working|provisional|interim)\b", r"(?i)\b(answers?|definitions?|criteria)\b",
                                  r"\bGLOW\b", ends=".", negated=True),
                        f"{where}: say the definitions are Ryan's working (provisional) answers, pending GLOW, in one "
                        "sentence")
        flat_e = self.norm(e)
        self.assertTrue(self.said(e, r"Partner_Status__c", r"\bArchived\b"), f"{where}: the obsolete Account criteria "
                                                                            "(`Partner_Status__c` Archived)")
        self.assertRegex(flat_e, r"(?i)\b(6|six) months\b", f"{where}: the obsolete Club criterion (6 months)")
        self.assertRegex(flat_e, r"(?i)\b(12|twelve) months\b", f"{where}: the obsolete Contact criterion (12 months)")
        self.assertTrue(self.said(e, r"(?i)\bname\b", r"(?i)\b(capitals?|case)\b", self.SAME_PARENT, self.SAME_TYPE),
                        f"{where}: the duplicate Account criteria (name ignoring capitals and spacing, the same parent, "
                        "the same record type)")
        self.assertIn(self.CONTACT_RULE, flat_e, f"{where}: the Contact rule {self.CONTACT_RULE!r} is kept")
        self.assertTrue([s for s in self.clauses(e) if self.REPORT_ONLY.search(s) and self.ALERT_DENIED.search(s)
                         and self.BLOCK_DENIED.search(s)],
                        f"{where}: the Account rule's action: Report only, no Alert and no Block (one sentence)")
        self.assertTrue(self.said(e, r"(?i)\badministrators?\b", r"(?i)\b(only|alone)\b"),
                        f"{where}: who sets a flag by hand: administrators only")
        self.assertTrue(self.said(e, r"(?i)\bshown\b|\bstays? in\b|\bremains? in\b", r"(?i)\bfilter\b"),
                        f"{where}: the kept reports show flagged records, the flags as a filter")
        rejected = self.norm(e.split("**Rejected", 1)[1].split("**Consequences", 1)[0])
        self.assertRegex(rejected, r"(?i)\balert\b|\bblock\w*", f"{where}: **Rejected** names Alert or Block")
        self.assertRegex(rejected, r"(?i)\bexclud\w*|\bleft out\b|\bhid\w*|\bfilter\w* out\b|\bdrop\w*",
                         f"{where}: **Rejected** names excluding flagged records from the reports")
        consequences = e.split("**Consequences", 1)[1]
        self.assertRegex(consequences, self.BATCH_TICKET, f"{where}: **Consequences** names the flagging batch, ticket #85")
        self.assertRegex(flat(e), self.Q + re.escape(self.SECTION[3:]) + self.QE,
                         f"{where}: name the RUNBOOK section {self.SECTION[3:]!r} in double quotes")
        # the Rejected bullet names what was rejected (Alert, Block); the rest of the entry must not contradict the rule
        rest = re.sub(r"(?ms)^- \*\*Rejected.*?(?=^- \*\*|\Z)", "", e)
        self.assertNoContradiction(rest, where)

    def test_the_salesforce_skill_points_at_the_section(self):
        item = self.skill_item()
        where = ".claude/skills/salesforce/SKILL.md, the item on the flags"
        text = self.norm(item)
        for f in self.FIELDS:
            self.assertIn(f, text, f"{where}: name the field `{f}`")
        self.assertTrue([s for s in self.clauses(item) if self.REPORT_ONLY.search(s) and self.ALERT_DENIED.search(s)
                         and self.BLOCK_DENIED.search(s)],
                        f"{where}: state the Account rule's action: Report only, no Alert and no Block (one sentence)")
        self.assertRegex(text, r"(?i)\badministrators?\b", f"{where}: say administrators alone set a flag by hand")
        self.assertRegex(text, r"(?i)\bcreated by code\b|\bprocessor\b|BACKLOG 54",
                         f"{where}: say why (an alert refuses a record created by code; BACKLOG 54)")
        self.assertNoContradiction(item, where)


# ---- the Python side of the matching rule --------------------------------------------------------------

P1, P2 = "001000000000000PAA", "001000000000000PBB"          # fictional partner accounts
CLUB, HOUSEHOLD = "012000000000000CLB", "012000000000000HHA"  # fictional record types: Club, partner (household)


def aid(n):
    return f"001{n:015d}"


def account(n, name, parent=P1, record_type=CLUB):
    """An Account as `SELECT Id, Name, ParentId, RecordTypeId FROM Account` gives it (ids fictional)."""
    return {"Id": aid(n), "Name": name, "ParentId": parent, "RecordTypeId": record_type}


class DuplicateAccountGroups(unittest.TestCase):
    """glow.salesforce.duplicate_account_groups(accounts): the groups of two or more Accounts the Account
    matching rule would report - the same Name ignoring capitals and spacing (nothing else: an accent
    is a different name), the same ParentId (a partner-less account's is None) and the same
    RecordTypeId - from records as the API gives them; each group the Accounts' Ids. The deliberate
    `<club> - <partner>` names and two partners' clubs of one name never match. Fictional throughout."""

    def groups(self, accounts):
        fn = getattr(salesforce, "duplicate_account_groups", None)
        self.assertTrue(callable(fn), "glow/salesforce.py has no duplicate_account_groups(accounts) yet: the groups of "
                                      "Accounts the Account matching rule would report (same Name ignoring capitals and "
                                      "spacing, same ParentId, same RecordTypeId), each a list of Ids")
        out = fn(accounts)
        for g in out:
            self.assertTrue(all(isinstance(i, str) and re.fullmatch(r"001\w{15}", i) for i in g),
                            f"duplicate_account_groups: a group is the Accounts' Ids (got {g!r})")
            self.assertGreaterEqual(len(g), 2, f"duplicate_account_groups: a group has two or more Accounts (got {g!r})")
        return sorted(sorted(g) for g in out)

    def test_the_accounts_the_rule_would_report_form_one_group_each(self):
        accounts = [
            account(1, "Shining Stars"),                       # the same club three times under partner 1:
            account(2, "shining stars"),                       #   capitals ...
            account(3, "SHINING  STARS "),                     #   ... and spacing ignored
            account(4, "Shining Stars", parent=P2),            # another partner's club of that name: not a duplicate
            account(5, "Shining Stars - Partner Two", parent=P2),   # the deliberate long name: never matches
            account(6, "Blue Herons", parent=None),            # two partner-less Club accounts the processor made
            account(7, " blue herons", parent=None),           #   (stray twins): the rule reports them
            account(8, "Blue Herons", parent=None, record_type=HOUSEHOLD),   # a partner account of that name: not
            account(9, "Rising Moons"),                        # names that differ beyond capitals and spacing
            account(10, "Rising Moon"),
            account(11, "Café Club"),                     # an accent is a different name
            account(12, "Cafe Club"),
        ]
        before = copy.deepcopy(accounts)
        self.assertEqual(self.groups(accounts), [[aid(1), aid(2), aid(3)], [aid(6), aid(7)]])
        self.assertEqual(accounts, before, "duplicate_account_groups changed its input")
        self.assertEqual(self.groups(list(reversed(accounts))), self.groups(accounts),
                         "the groups do not depend on the order of the accounts")

    def test_each_criterion_changes_the_answer(self):
        cases = [
            # label, name a, name b, parent a, parent b, record type a, record type b, a duplicate?
            ("the same name, parent and record type", "Golden Eagles", "Golden Eagles", P1, P1, CLUB, CLUB, True),
            ("capitals differ", "Golden Eagles", "GOLDEN eagles", P1, P1, CLUB, CLUB, True),
            ("spacing differs (double, leading, trailing)", "Golden Eagles", "  Golden  Eagles ", P1, P1, CLUB, CLUB, True),
            ("capitals and spacing differ", "golden eagles", "GOLDEN  EAGLES", P1, P1, CLUB, CLUB, True),
            ("both partner-less (the processor's strays)", "Golden Eagles", "golden eagles", None, None, CLUB, CLUB, True),
            ("one word more", "Golden Eagles", "Golden Eagles Club", P1, P1, CLUB, CLUB, False),
            ("one letter more", "Golden Eagles", "Golden Eagless", P1, P1, CLUB, CLUB, False),
            ("an accent", "Golden Éagles", "Golden Eagles", P1, P1, CLUB, CLUB, False),
            ("another partner's club of that name", "Golden Eagles", "Golden Eagles", P1, P2, CLUB, CLUB, False),
            ("a partner-less twin of a partnered club", "Golden Eagles", "Golden Eagles", P1, None, CLUB, CLUB, False),
            ("the deliberate long name under the same partner", "Golden Eagles", "Golden Eagles - Partner One",
             P1, P1, CLUB, CLUB, False),
            ("two partners' long names", "Golden Eagles - Partner One", "Golden Eagles - Partner Two",
             P1, P2, CLUB, CLUB, False),
            ("a Club and a partner account of one name", "Golden Eagles", "Golden Eagles", None, None, CLUB, HOUSEHOLD, False),
            ("two partner accounts of one name", "Golden Eagles", "golden eagles", None, None, HOUSEHOLD, HOUSEHOLD, True),
        ]
        for label, name_a, name_b, parent_a, parent_b, rt_a, rt_b, duplicate in cases:
            with self.subTest(label):
                a, b = account(21, name_a, parent_a, rt_a), account(22, name_b, parent_b, rt_b)
                expected = [sorted([a["Id"], b["Id"]])] if duplicate else []
                self.assertEqual(self.groups([a, b]), expected,
                                 f"{label}: {name_a!r} ({parent_a}, {rt_a}) and {name_b!r} ({parent_b}, {rt_b}) "
                                 f"{'are' if duplicate else 'are not'} what the rule reports")

    def test_no_group_without_a_twin(self):
        self.assertEqual(self.groups([]), [], "no accounts: no groups")
        self.assertEqual(self.groups([account(1, "Shining Stars")]), [], "one account: no groups")
        self.assertEqual(self.groups([account(1, "Shining Stars"), account(2, "Rising Moons"), account(3, "Blue Herons", parent=None)]),
                         [], "distinct names: no groups")
        # a missing ParentId key is a partner-less account, as `null` is
        a, b = account(4, "Blue Herons", parent=None), {"Id": aid(5), "Name": "blue herons", "RecordTypeId": CLUB}
        self.assertEqual(self.groups([a, b]), [sorted([a["Id"], b["Id"]])],
                         "an account without a ParentId key is partner-less, like one whose ParentId is null")
        # three of one club and two of another: two groups, every twin in its group, no Id in both
        accounts = [account(1, "Shining Stars"), account(2, "Rising Moons"), account(3, "shining stars"),
                    account(4, "rising moons"), account(5, "Shining  Stars")]
        self.assertEqual(self.groups(accounts), [[aid(1), aid(3), aid(5)], [aid(2), aid(4)]],
                         "a group per name, each with every twin, no Id in two groups")


if __name__ == "__main__":
    unittest.main(verbosity=1)
