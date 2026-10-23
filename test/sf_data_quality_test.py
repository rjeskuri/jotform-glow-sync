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
as a filter; a plan carries the fresh retrieve, the check-only, Ryan's go (his answer after the
check-only's result), the deploy, the proof after it, the read-back and the next day's batch check,
in that order, and its Rollback deactivates the rule in the org by a named action; the RUNBOOK states
the rules' exact settings (`actionOnInsert`/`actionOnUpdate` Allow, no `alertText`; the
MatchingRuleItems Name (Exact, case-insensitive) and ParentId (blank matches blank), never
RecordTypeId; one report-only Duplicate Rule per record type, Club and Household, with the condition
Record Type equals that type), the obsolete Club exception (the clubs of a partner marked `no` in the
Partners tab's `jotform` column are judged by their partner account's `Partner report` batches), the
monthly check's SOQL with the sets' member ids, and what the rule does not catch (the partner-less
twin of a parented club); a dated DECISIONS entry records the definitions as Ryan's provisional
answers pending GLOW and the review's two design changes; the salesforce skill's "What lives there"
points at the section.

Deployed 2026-10-22 (Ryan's go): deploy 0AfRP000002htOH0AY 12:33 UTC, 9/9 (check-only
0AfRP000002hlVZ0AY), each Duplicate Rule with its own sortOrder (Club 1, Household 2: two rules with
sortOrder 1 are refused, "SortOrder must be in sequential order from 1"). Two decisions of Ryan's the
same day, which the plan and the RUNBOOK section must carry: (1) the proof is a no-DML diagnostic -
`Datacloud.FindDuplicates.findDuplicates` on unsaved copies of existing accounts, printing only rule
names and match counts as `DIAG|` lines; three probes: an upper-cased copy of a parented Club (the Club
rule, 1 match), a copy of a Household account (the Household rule, 1 match), a Household account with
a club's name and ParentId (the Household rule, 1 match: the Club) - because the rolled-back insert
proof could not work (Salesforce's duplicate matching does not see records inserted earlier in the
same uncommitted transaction: 7/7 inserts, 0 sets), so no doc names the rolled-back insert as the
proof except as history, and none says the proof probes spacing; (2) cross-type pairs are accepted: a
Duplicate Rule's record-type condition picks the rule for the record saved and does not limit the
candidates, so Salesforce may report a Household account and a Club of one name and parent as a pair,
`duplicate_account_groups` keeps its own definition, and the monthly check reviews such a pair by
hand - so no doc says the condition applies to the candidates, or that a Club and a Household account
never match. The plan records the deploy id, time and count, the read-back (after/ = build/ but for
Salesforce's normalisation, the four field permissions present), the three rules active, the Contact
rule unchanged, the counts (0 groups, 0 cross-type, 0 sets), and is not `done` while the next day's
batch check (step 8) is pending. Every part a test reads is swept for what would
contradict the rules (contradictions()): the rule set to Alert or Block (said any way, unless denied
where it is said, without a time limit) or stopping a save in other words (a halt, pop-up, message,
prompt, refusal), a flagged record deleted, merged, hidden or kept out of the reports (said any way),
a softener on the proof, the check-only, the go or the read-back. Counts and ids only: no figure
from the org is pinned.

DuplicateAccountGroups: glow.salesforce.duplicate_account_groups(accounts), the Python side of the
Account matching rule for the read-back and the monthly check - the groups of Accounts the rule
would report, computed from `SELECT Id, Name, ParentId, RecordTypeId FROM Account` - over fictional
accounts with every criterion varied on its own: any whitespace run (tab, no-break space) is one
space, casefold (Straße = STRASSE), ParentId "" = null = missing, RecordTypeId missing = null, and
the `<club> - <partner>` names get no special case (only another parent keeps twins apart).
"""
import copy
import datetime
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
                            r"submission|`?alertText`?)\b", re.I)
    REPORT_ONLY = re.compile(r"(?i)\breports?\b[^.;]{0,10}?\bonly\b")
    ALERT_DENIED = re.compile(r"(?i)\b(no|without|never|not|nor)\s+(an?\s+|the\s+)?alert")
    BLOCK_DENIED = re.compile(r"(?i)\b(no|without|never|not|nor|or)\s+(an?\s+|the\s+)?block")   # "never Alert or Block"
    ACCOUNT = r"(?<!\w)Accounts?(?![A-Za-z])"         # also in `Account_Duplicate_Record__c` (norm() joins the dot)
    CONTACT = r"(?<!\w)Contacts?(?![A-Za-z])"
    # "their partner's batches", "the partner account's `Partner report` batches"
    PARTNER_BATCHES = r"(?i)\bpartner(['’]s| account['’]s)?\s+(account['’]s\s+)?(`?Partner report`?\s+)?batch"
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
    # the rule stopping a save, said in other words: a save, insert, record, the processor or a create paired
    # with a halt, stop, turn-away, pop-up, message, prompt, refusal or rejection - unless denied where it is
    # said, the cost form ("an alert refuses a record created by code") or a conditional ("if an insert is
    # refused, the Rollback follows")
    SAVE = re.compile(r"(?i)\b(saves?|saving|inserts?|inserting|records?|processor|creat\w*)\b")
    STOPS = re.compile(r"(?i)\bhalt\w*|\bstop\w*|\bturn(s|ed|ing)?\s+away|\bpop-?ups?\b|\bmessages?\b|\bprompt\w*|"
                       r"\brefus\w*|\breject\w*")
    COST = re.compile(r"(?i)\b(alert|block)\w*")
    CONDITIONAL = re.compile(r"(?i)\b(if|should|in case|would|could|were)\b")
    # flagged records kept out of the reports, said in other words (the phrases are the hiding: a negation
    # before them does not make them a denial, but for "filtered out" and "= false")
    HIDDEN = re.compile(r"(?i)\bdoes not appear\b|\bnot appear\b|\bkeeps? only\b|\bonly clean\b|=\s*false\b|"
                        r"\bunflagged only\b|\bfiltered out\b")
    HIDDEN_DENIABLE = re.compile(r"(?i)\bfiltered out\b|=\s*false\b")
    # the one merge a clause may name: one girl's duplicate contacts (tools/sf_dupes.py), in a clause that also
    # says flagged records are not merged by it
    GIRL_WORDS = re.compile(r"(?i)\b(contacts?|girls?)\b")
    NOT_FOR_FLAG = re.compile(r"(?i)\b(never|not|no|nor)\b[^.;]{0,40}?\bflag")

    # --- the deploy of 2026-10-22 and Ryan's two decisions of that day ------------------------------------
    DEPLOY_ID, CHECK_ONLY_ID = "0AfRP000002htOH0AY", "0AfRP000002hlVZ0AY"
    DEPLOY_DAY, DEPLOY_TIME, NEXT_DAY = "2026-10-22", "12:33", "2026-10-23"
    FIND_DUPLICATES = r"FindDuplicates"
    DIAGNOSTIC = r"FindDuplicates|(?i:\bdiagnostic\b)"
    # the diagnostic inserts, writes and saves nothing: its probes are unsaved copies
    NO_DML = (r"(?i)\bno[- ]DML\b|\bwithout (any )?DML\b|\bDML-free\b|\bno (inserts?|writes?|saves?)\b|"
              r"\b(inserts?|writes?|saves?|creates?|stores?|commits?)\s+(nothing|no records?|no accounts?|none)\b|"
              r"\bnothing (is |gets )?(inserted|written|saved|created|stored|committed)\b|\bunsaved\b|\bnever saved\b|"
              r"\bnot saved\b|\bin memory\b|\bno (record|account) is (inserted|saved|written|created)\b|\bread-only\b")
    COPIES = r"(?i)\b(cop(y|ies)|clones?|twins?)\b"
    EXISTING = r"(?i)\b(existing|real|live|current|on file)\b"
    RULE_NAMES = r"(?i)\brule['’]?s? names?\b|\bnames? of (the|each|a) rule\b|\brules?\b"
    COUNTS = r"(?i)\bcounts?\b|\bmatches\b|\bnumber of matches\b"
    ONLY = r"(?i)\bonly\b|\bnothing else\b|\balone\b|\bno names?\b|\bnever a name\b|\bnothing more\b"
    ONE_MATCH = r"(?<![\w/.-])(1|one)\s+match(es)?\b"
    CLUB_RULE = r"(?i)\bClub rule\b|Name_Parent_Club_Report|\bClub['’]s rule\b|\brule for Clubs?\b"
    HOUSEHOLD_RULE = r"(?i)\bHousehold rule\b|Name_Parent_Household_Report|\bHousehold['’]s rule\b|\brule for Households?\b"
    UPPER = r"(?i)\bupper-?cased?\b|\bupper case\b|\buppercase\b|\bcapitals\b|\bcapitalis\w*|toUpperCase|\bin capitals\b"
    CLUBS_NAME = (r"(?i)\bclub['’]s name\b|\bname (and (parent|ParentId) )?of a club\b|\bclub name\b|"
                  r"\bnamed (like|as|after) a club\b|\ba club['’]s\b|\blike a club\b|\bas a club\b")
    THE_CLUB = r"(?i:\bcross-?type\b|\bthe original\b)|(?<![\w'’-])(the|that|its|one|a|The) Club(?![\w'’-])"
    PAIR = r"(?i)\bpairs?\b|\bcross-?type\b|\b(same|one) (set|DuplicateRecordSet)\b|\btogether\b|\bas twins\b"
    HOUSEHOLD = r"(?i)\bHousehold\b"
    ANY_CLUB = r"(?i)\bclub\b"
    # the rolled-back insert proof may be named as history only (dropped, could not work, a flaw): never as the
    # proof; what a clause says of it is read from the last comma, dash or bracket before the words to the
    # next `, so|and|but|then|which|...` or `;` after them
    ROLLED_BACK = re.compile(r"(?i)\brolled[- ]back\b|Database_rollback|\broll(ed|s|ing)? back\b")
    PROOF_WORDS = re.compile(r"(?i)\bproof\b|\binsert\w*|\bDML\b|\bapex\b")
    DROPPED = re.compile(r"(?i)\b(dropped|drops|replaced|superseded|abandoned|withdrawn|retired|scrapped|flaws?|flawed|"
                         r"could not|cannot|can['’]t|did not|didn['’]t|does not|doesn['’]t|was not|were not|old|former|"
                         r"(first|earlier|previous|original) (version|form|design|proof|plan|step)|no longer|instead|"
                         r"history|redesign\w*|rewritten|rethought|failed|fails|failure|dead end|not the proof)\b")
    SEGMENT_END = re.compile(r",\s+(so|and|but|then|which|while|whereas|because|since)\s+|;")
    # the proof (the diagnostic, a probe, the script) answering the spacing question - the three probes do not
    PROOF_SUBJECT = re.compile(r"(?i)\b(proof|diagnostic|probe|script)['’]?s?\b[^.;,]{0,20}?"
                               r"\b(probes?|tests?|answers?|settles?|decides?|says|shows|tells|records?)\b")
    SPACING = re.compile(r"(?i)\bspacing\b|\bdouble space\b|\bwhitespace\b")
    # a Duplicate Rule's record-type condition said to apply to the candidates (the records matched), not only
    # to the record saved
    CONDITION = re.compile(r"(?i)\bcondition\b|\bduplicateRuleFilter\w*|\bfilter\b")
    CANDIDATES = re.compile(r"(?i)\bcandidates?\b|\brecords? (it |that are |that were |being )?matched\b|\bmatched records?\b|"
                            r"\bthe match(es)?\b|\bboth (records|sides)\b|\bthe twin\b|\bthe other record\b|"
                            r"\bthe records? (found|compared)\b")
    UNFILTERED = re.compile(r"(?i)\b(whatever|whichever|regardless|irrespective|any|all|every|either|both|unfiltered|"
                            r"unrestricted|not|never|no|cannot|can['’]t|only|decides|picks|chooses|selects)\b")
    AFTER_UNFILTERED = re.compile(r"(?i)\s*(is|are|was|were|come|comes|remains?|stays?|of)?\s*(not|never|no|cannot|can['’]t|"
                                  r"whatever|whichever|any|all|either|both|unfiltered|unrestricted)\b")
    # a Club and a Household (partner) account of one name said never to match or to be kept apart - true of
    # the Python side only
    CROSS_PAIR = re.compile(r"(?i)\bHousehold( account)?\b|\bpartner account\b|\b(a|the|one) club and (a|the) partner\b|"
                            r"\b(a|the) partner and (a|the) club\b")
    NEVER_MATCH = re.compile(r"(?i)\b(never|not|cannot|can['’]t|no)\s+(be )?(match\w*|report\w*|pair\w*|meet|twins?|"
                             r"duplicates?)\b|\bkept apart\b|\bkeeps? [^.;]{0,30}?\bapart\b")
    PYTHON_SIDE = re.compile(r"(?i)duplicate_account_groups|\bPython\b|\bthe batch\b|(?<![\w#])#85\b")
    NEXT_DAY_WORDS = re.compile(r"(?i)\bnext day\b|\bday after\b|\bfollowing day\b|\bstep 8\b|2026-10-23|\bbatch check\b")
    PENDING = re.compile(r"(?i)\bpending\b|\bto come\b|\bstill to\b|\bawait\w*|\bnot yet\b|\btomorrow\b|\bto do\b|\bopen\b|"
                         r"\boutstanding\b|\bdue\b|\bwhen done\b|\bonce done\b|\bstill\b")
    # the deploy said to be pending or waiting (for Ryan's go, or "his go"), in any tense but the past
    NOTHING_DEPLOYED = re.compile(r"(?i)\bnothing (is |has been |was )?deployed\b|\bthe deploy(ment)?,? (which |that |still )?"
                                  r"waits\b|\bnot yet deployed\b|\bawaits? (the |its )?deploy|\bbefore the deploy\b[^.;]{0,40}?"
                                  r"\bwaits? for (Ryan['’]s|his) go\b|\bdeploy\w*\b[^.;]{0,40}?\bwaits? for (Ryan['’]s|his) go\b|"
                                  r"\bdeploy\w* waits?\b")
    DML = re.compile(r"(?m)^\s*(insert|update|delete|undelete|upsert|merge)\s|Database\.(insert|update|delete|undelete|"
                     r"upsert|merge|emptyRecycleBin)\(")
    ROLLBACK_CODE = re.compile(r"\bSavepoint\b|Database\.setSavepoint\s*\(|Database\.rollback\s*\(")
    # an unsaved copy made in Apex: a new Account or a clone of a queried one
    PROBE_MAKER = r"new Account\s*\(|\.\s*clone\s*\("
    # a save refused "all the same": the rule's action hedged into a refusal
    HEDGED_REFUSAL = re.compile(r"(?i)\b(inserts?|saves?|records?|batch(es)?|accounts?)\b[^.;]{0,40}?\b(refus|reject|block|"
                                r"stop)\w*[^.;]{0,25}?\b(all the same|anyway|nevertheless|regardless|after all|despite|"
                                r"even so|still|nonetheless)\b")
    # "same record type" claimed of the rules (not of the Python side's definition)
    SAME_TYPE_CLAIM = re.compile(r"(?i)same record type")
    RULES_ANSWER = re.compile(r"(?i)\brules?\b|\banswer\b|\bcomes? from\b")
    SAVED_ONLY = re.compile(r"(?i)\bsav(ed|ing)\b|\bpicks?\b|\bwhich rule\b|\bnot\b|\bcannot\b|\bnever\b|\bno longer\b|\bexcept\b")

    def rules_give_same_type(self, text):
        """The clauses (split at `.;:` too) that say the rules, or the answer, are "same record type" without
        saying it holds for the record saved only - the Python side's own definition excepted."""
        return [s[:160] for s in self.clauses(text, ".;:") if self.SAME_TYPE_CLAIM.search(s) and self.RULES_ANSWER.search(s)
                and not self.PYTHON_SIDE.search(s) and not re.search(r"(?i)\bduplicates when\b|\bdefinition\b|\bcriteri", s)
                and not self.SAVED_ONLY.search(s)]

    @staticmethod
    def fences(text):
        """Every fenced code block of `text`, whatever its language."""
        return re.findall(r"(?ms)^```[^\n]*\n(.*?)^```", text)

    @staticmethod
    def prose(text):
        """`text` without its fenced code blocks (a quoted script is checked on its own)."""
        return re.sub(r"(?ms)^```.*?^```[^\n]*$", " ", text)

    @staticmethod
    def balanced(code, start):
        """`code` from `start` (just past an opening bracket) to the bracket that closes it, exclusive."""
        depth, i = 1, start
        while i < len(code) and depth:
            depth += {"(": 1, "[": 1, "{": 1, ")": -1, "]": -1, "}": -1}.get(code[i], 0)
            i += 1
        return code[start:i - 1]

    def apex_bindings(self, code):
        """(sources, probes) of an Apex script without comments: the names bound to queried accounts
        (`x = [SELECT …]`, `Database.query(`, a cast of either, the variable of a loop over them) and the
        names bound to unsaved copies - a variable set to `new Account(` or `x.clone(`, a List/Map/Set
        literal or an `.add(`/`.put(`/`.addAll(` that holds one of those or a probe name already found,
        and the variable of a loop over such a collection."""
        sources = set(re.findall(r"(\w+)\s*[=:]\s*(?:\(\s*(?:List\s*<\s*Account\s*>|Account)\s*\)\s*|"
                                 r"new\s+(?:List|Map)\s*<[^;({]*?>\s*\(\s*)?(?:\[\s*SELECT\b|Database\s*\.\s*query\s*\()",
                                 code))
        probes = set(re.findall(rf"(\w+)\s*=\s*(?:\w+\s*)?(?:{self.PROBE_MAKER})", code))
        grew = True
        while grew:
            grew = False
            for m in re.finditer(r"(\w+)\s*(?:=\s*new\s+(?:List|Map|Set)\s*<[^;{]*?>\s*\{|\.\s*(?:add|put|addAll)\s*\()",
                                 code):
                body = self.balanced(code, m.end())
                if m.group(1) not in probes and (re.search(self.PROBE_MAKER, body)
                                                 or any(re.search(rf"\b{re.escape(p)}\b", body) for p in probes)):
                    probes.add(m.group(1))
                    grew = True
            for m in re.finditer(r"for\s*\(\s*Account\s+(\w+)\s*:\s*(\w+)", code):
                var, over = m.groups()
                if over in probes and var not in probes:
                    probes.add(var)
                    grew = True
                if over in sources and var not in sources:
                    sources.add(var)
                    grew = True
        return sources, probes

    @staticmethod
    def passes_record(arg, name):
        """Whether a call's argument text `arg` hands over the record `name` itself - bare, or an element of
        it (`name[0]`, `name.get(0)`) - rather than reading a field of it (`name.Name`) or cloning it."""
        for m in re.finditer(rf"\b{re.escape(name)}\b", arg):
            tail = arg[m.end():]
            if re.match(r"\s*\.\s*clone\s*\(", tail) or re.match(r"\s*\.\s*\w+\b(?!\s*\()", tail):
                continue
            return True
        return False

    def old_proof_claims(self, text):
        """The clauses of `text` that name the rolled-back insert proof as the proof: `rolled back`, `rolled-back`
        or `Database.rollback` with a proof, insert, DML or Apex word in reach, and neither a denial nor a
        history word (dropped, could not work, a flaw, the first version) in reach."""
        out = []
        for s in self.clauses(text):
            for m in self.ROLLED_BACK.finditer(s):
                window = self.local(s, m) + " " + self.SEGMENT_END.split(s[m.end():])[0]
                if self.PROOF_WORDS.search(window) and not (self.NEGATION.search(window) or self.DROPPED.search(window)):
                    out.append(s[:160])
                    break
        return out

    def proof_probes_spacing(self, text):
        """The clauses saying the proof (the diagnostic, a probe, the script) probes, tests or answers the spacing
        question, unless denied in the words themselves or right after ("the probes do not test spacing")."""
        return [s[:160] for s in self.clauses(text) if self.SPACING.search(s)
                and any(not self.NEGATION.search(s[m.start():m.end() + 25]) for m in self.PROOF_SUBJECT.finditer(s))]

    def condition_filters_candidates(self, text):
        """The clauses where a rule's condition (or filter) is said to apply to the candidates, the records
        matched: the words before the candidates (back to the last comma, dash or bracket) or right after them
        neither deny it nor say whatever/any/all/only."""
        out = []
        for s in self.clauses(text):
            if not self.CONDITION.search(s):
                continue
            for m in self.CANDIDATES.finditer(s):
                if self.UNFILTERED.search(self.local(s, m)) or self.AFTER_UNFILTERED.match(s[m.end():]):
                    continue
                out.append(f"{m.group(0)!r}: {s[:160]!r}")
                break
        return out

    def club_and_household_never_match(self, text):
        """The clauses saying a Club and a Household (partner) account never match or are kept apart - about the
        rules or Salesforce, not the Python side - unless denied where it is said."""
        out = []
        for s in self.clauses(text):
            if not (re.search(self.ANY_CLUB, s) and self.CROSS_PAIR.search(s)) or self.PYTHON_SIDE.search(s):
                continue
            for m in self.NEVER_MATCH.finditer(s):
                if not self.locally_denied(s, m):
                    out.append(f"{m.group(0)!r}: {s[:160]!r}")
                    break
        return out

    def says_cross_type_pair(self, text):
        """The clauses saying Salesforce may report a Household account and a Club of one name and parent as a
        pair (one set), not denied where the pair is said."""
        return [s for s in self.clauses(text) if re.search(self.HOUSEHOLD, s) and re.search(self.ANY_CLUB, s)
                and any(not self.locally_denied(s, m) for m in re.finditer(self.PAIR, s))]

    def probe_clauses(self, text):
        """(a, b, c): the clauses of `text` that state each probe of the diagnostic with its result - an
        upper-cased copy of a parented Club (the Club rule, 1 match); a copy of a Household account (the
        Household rule, 1 match); a Household account with a club's name and ParentId (the Household rule, 1
        match, the Club: cross-type)."""
        a = self.said(text, self.UPPER, self.ANY_CLUB, r"(?i)\bparent(ed|Id)?\b", self.CLUB_RULE, self.ONE_MATCH, negated=True)
        b = self.said(text, self.HOUSEHOLD, self.COPIES, self.HOUSEHOLD_RULE, self.ONE_MATCH, negated=True)
        c = self.said(text, self.HOUSEHOLD, self.CLUBS_NAME, r"(?i)\bParentId\b|\bparent\b", self.HOUSEHOLD_RULE,
                      self.ONE_MATCH, self.THE_CLUB, negated=True)
        return a, b, c

    def header_line(self, part, label):
        """The `- **<label>:** …` line of a RUNBOOK section's header."""
        m = re.search(r"\*\*" + label + r":?\*\*(.*?)(?=\n- \*\*|\n\n|\Z)", part, re.S)
        self.assertTrue(m, f"RUNBOOK section {self.SECTION[3:]!r}: no `- **{label}:**` header line")
        return flat(m.group(1))

    def subpart(self, part, heading):
        """The `### …` subsection of the RUNBOOK section `part` headed `heading`, to the next heading."""
        m = re.search(r"^" + re.escape(heading) + r"(?!\w).*$", part, re.M)
        self.assertTrue(m, f"RUNBOOK section {self.SECTION[3:]!r}: no `{heading}` subsection")
        rest = part[m.start():]
        nxt = re.search(r"\n#{1,3} ", rest)
        return rest[:nxt.start()] if nxt else rest

    def denies(self, text):
        return bool(self.NEGATION.search(self.RULE_IDIOM.sub(" ", text)))

    def locally_denied(self, s, m):
        """A negation in the words before match `m` of clause `s`, back to the last comma, dash, bracket or
        "but"."""
        return bool(self.NEGATION.search(self.local(s, m)))

    @staticmethod
    def local(s, m):
        return re.split(r"[,;:—–(]|\bbut\b|\bhowever\b|\bactually\b", s[max(0, m.start() - 40):m.start()])[-1]

    def denied_near(self, s, m):
        """locally_denied, or a negation right after the match ("RecordTypeId is not a matching item")."""
        return self.locally_denied(s, m) or bool(re.match(r"(?i)\s*(is|are|was|were|remains?|stays?)?\s*(not|never|no)\b",
                                                          s[m.end():]))

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

    def stops_a_save(self, s):
        """The clauses' stop words (STOPS) paired with a save, insert, record, the processor or a create, but for
        one denied where it is said, the cost form (an alert or block as the subject) or a conditional."""
        if not self.SAVE.search(s):
            return []
        out = []
        for m in self.STOPS.finditer(s):
            local = self.local(s, m)
            if self.NEGATION.search(local) or self.COST.search(local) or self.CONDITIONAL.search(local):
                continue
            out.append(f"stops a save in other words ({m.group(0)!r}): {s[:160]!r}")
            break
        return out

    def removes_flagged(self, s):
        """A flagged, duplicate or obsolete record deleted, merged, hidden or excluded in clause `s`, not denied
        where it is said. A field or the flag itself may be removed. The one merge a clause may name is one
        girl's duplicate contacts (`tools/sf_dupes.py`), in a clause that also says flagged records are not
        merged by it. The hiding phrases (HIDDEN) count even after a negation, but for "filtered out" and
        "= false"."""
        if not self.FLAGGED.search(s):
            return []
        for m in self.HIDDEN.finditer(s):
            if self.HIDDEN_DENIABLE.fullmatch(m.group(0)) and self.locally_denied(s, m):
                continue
            return [f"keeps flagged records out of the reports ({m.group(0)!r}): {s[:160]!r}"]
        scrubbed = self.FIELD_OR_FLAG.sub(" ", s)
        for m in self.REMOVAL.finditer(scrubbed):
            if self.locally_denied(scrubbed, m):
                continue
            if m.group(0).lower().startswith("merg") and self.GIRL_WORDS.search(scrubbed) \
                    and self.NOT_FOR_FLAG.search(scrubbed):
                continue
            return [f"removes, merges or hides flagged records ({m.group(0)!r}): {s[:160]!r}"]
        return []

    def contradictions(self, text, rollback=False):
        """The clauses of `text` that contradict the rules: the rule's action is Alert or Block (not denied
        where it is said, or denied with a time limit), or it stops a save said in other words; a flagged,
        duplicate or obsolete record deleted, merged, hidden or kept out of the reports (removes_flagged); a
        softener not itself denied. With `rollback`, "no rollback" is one."""
        out = []
        girls = re.compile(self.Q + re.escape(self.GIRLS) + self.QE)
        for s in self.clauses(text, ".;:?!"):
            kept = girls.sub(" ", s)
            out += self.alert_or_block(kept)
            out += self.stops_a_save(kept)
            out += self.removes_flagged(kept)
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
                                    "Block and never stops, halts, refuses or prompts on a save - name Alert or Block "
                                    "only to deny them or as the cost, `an alert refuses a record created by code`; a "
                                    "flagged record is never deleted, merged, hidden, filtered out or kept out of the "
                                    "reports; the proof, the check-only, the go and the read-back are never optional): "
                                    + "; ".join(found))

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
        """The `- …` item of the skill's `## What lives there` part (beside Accounts and Reports and dashboards,
        not under Access or the writers) that names the RUNBOOK section in double quotes."""
        items = re.findall(r"(?m)^- .*(?:\n(?!- |\n|#).*)*", md_part(self.SKILL, "## What lives there"))
        title = re.compile(self.Q + re.escape(self.SECTION[3:]) + self.QE)
        found = [i for i in items if title.search(flat(i))]
        self.assertTrue(found, ".claude/skills/salesforce/SKILL.md: no `- …` item under `## What lives there` that "
                               f"names the RUNBOOK section {self.SECTION[3:]!r} in double quotes")
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
        # the exception (review, 2026-10-21): the clubs of a partner marked `no` in the Partners tab's `jotform`
        # column report as one `Partner report` batch on the partner account, so they are judged by their partner's
        # batches, never by their own
        self.assertTrue(self.said(part, r"`?jotform`?", r"(?<![\w-])`?no`?(?![\w-])", r"(?i)\bPartners tab\b",
                                  r"`?Partner report`?", self.PARTNER_BATCHES,
                                  negated=True),
                        f"{where}: state the exception in one sentence: the clubs of a partner marked `no` in the Partners "
                        "tab's `jotform` column are judged by their partner account's `Partner report` batches, not "
                        "their own")
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

    def test_the_runbook_states_the_rules_exact_settings(self):
        """The metadata as deployed, in the RUNBOOK (the XML itself lives in data/, not in git): the Duplicate
        Rule's `actionOnInsert` and `actionOnUpdate` are `Allow` with no `alertText`; the Matching Rule's
        items are Name (exact, case-insensitive), ParentId and RecordTypeId; the Rollback deactivates the rule."""
        where = f"RUNBOOK section {self.SECTION[3:]!r}"
        part = self.section()
        text = self.norm(part)
        self.assertTrue(self.said(part, r"actionOnInsert", r"actionOnUpdate", r"\bAllow\b"),
                        f"{where}: say `actionOnInsert` and `actionOnUpdate` are `Allow`, in one sentence")
        self.assertRegex(text, r"(?i)\b(no|without|empty|blank)\s+`?alertText`?\b|\balertText\b[^.;]{0,25}?"
                               r"\b(empty|none|absent|unset|blank|omitted)\b",
                         f"{where}: say the rule has no `alertText` (nothing is shown to a user)")
        self.assertRegex(text, r"(?i)MatchingRuleItems?|matching rule items?",
                         f"{where}: name the Matching Rule's items (`MatchingRuleItems`)")
        # the matching design (review, 2026-10-21): the Matching Rule matches Name (Exact, case-insensitive) and
        # ParentId (blank matches blank), never RecordTypeId; "same record type" comes from one report-only
        # Duplicate Rule per record type (Club, Household), each with the condition Record Type equals that type
        items = self.said(part, r"(?i)MatchingRuleItems?|matching rule items?", r"\bName\b", r"(?i)\bexact\w*\b",
                          r"(?i)case-insensitive|ignoring (capitals|case)|(capitals|case) ignored", r"ParentId",
                          r"(?i)\bblank\b[^.;]{0,20}?\bblank\b|\bempty\b[^.;]{0,20}?\bempty\b|\bnull\b[^.;]{0,20}?\bnull\b")
        self.assertTrue(items, f"{where}: give the Matching Rule's items in one sentence: Name (Exact, case-insensitive) "
                               "and ParentId (blank matches blank)")
        self.assertFalse([s for s in items if "RecordTypeId" in s],
                         f"{where}: RecordTypeId is not a matching item (Salesforce refuses Record Type as a matching-rule "
                         "field): the record type is the Duplicate Rule's condition")
        for s in self.clauses(part):
            if "RecordTypeId" in s and re.search(r"(?i)\bmatch\w*", s):
                m = re.search(r"RecordTypeId", s)
                self.assertTrue(self.denied_near(s, m), f"{where}: a clause names RecordTypeId as something matched; "
                                                        f"say it is not a matching item: {s[:160]!r}")
        self.assertTrue(self.said(part, r"(?i)\bduplicate rules?\b|DuplicateRule",
                                  r"(?i)\b(per|each|every|one for each|two)\b[^.;]{0,25}?\brecord types?\b|\btwo duplicate rules\b",
                                  r"(?<!\w)Club(?!\w)", r"(?<!\w)Household(?!\w)", r"(?i)\brecord type\b[^.;]{0,25}?\b(equals|=|is)\b"),
                        f"{where}: say there is one report-only Duplicate Rule per record type (Club, Household), each "
                        "with the condition Record Type equals that type, in one sentence")
        self.assertTrue(self.said(part, r"(?i)\brollback\b", r"(?i)\bdeactivat\w*|\binactive\b|isActive"),
                        f"{where}: the Rollback deactivates the Duplicate Rules (`isActive` false), said in the section")
        self.assertNoContradiction(part, where)

    def test_the_runbook_gives_the_monthly_check_and_what_the_rule_misses(self):
        """The monthly check reads the rule's duplicate record sets with their members' ids (counts and ids only,
        never a name) and compares them with `duplicate_account_groups`; the rule does not catch the partner-less
        twin of a parented club (their parents differ): that stays for the monthly check."""
        where = f"RUNBOOK section {self.SECTION[3:]!r}"
        part = self.section()
        text = flat(part)
        self.assertRegex(text, r"(?i)\bmonthly check\b", f"{where}: give the monthly check")
        self.assertRegex(text, r"FROM\s+DuplicateRecordSet\b", f"{where}: the monthly check's SOQL reads `DuplicateRecordSet`")
        self.assertRegex(text, r"\(\s*SELECT\s+RecordId\s+FROM\s+DuplicateRecordItems\s*\)",
                         f"{where}: the monthly check's SOQL selects the members' ids: `(SELECT RecordId FROM "
                         "DuplicateRecordItems)`")
        self.assertRegex(text, r"duplicate_account_groups", f"{where}: the monthly check compares the sets with "
                                                            "`glow.salesforce.duplicate_account_groups`")
        self.assertTrue(self.said(part, r"(?i)\b(does not|will not|never|cannot|can['’]t|doesn['’]t)\s+(catch|report|"
                                        r"match|find|see)\w*|\bmisses\b|\bnot caught\b|\bnot reported\b|\bnot matched\b",
                                  r"(?i)\bpartner-?less\b|\bparent-?less\b|\bwithout a parent\b|\bno parent\b",
                                  r"(?i)\btwins?\b|\bstrays?\b|\bcop(y|ies)\b|\bduplicates?\b",
                                  r"(?i)\bmonthly check\b", negated=True),
                        f"{where}: say what the rule does not catch, in one sentence: the partner-less twin of a parented "
                        "club (their parents differ), which stays for the monthly check")
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
                        f"{where}: say `tools/sf_dupes.py` still merges one girl's duplicate contacts by its own key and "
                        "never merges a record for being flagged, in one sentence")
        self.assertNoContradiction(part, where)

    # --- the proof and the cross-type pairs: the docs as deployed (Ryan, 2026-10-22) ------------------------

    def test_the_docs_describe_the_find_duplicates_diagnostic_as_the_proof(self):
        """Ryan, 2026-10-22 (decision 1): the proof is a no-DML diagnostic, `Datacloud.FindDuplicates` on
        unsaved copies of existing accounts, printing only rule names and match counts as `DIAG|` lines; the
        RUNBOOK's Apply line and the plan's proof step say so."""
        part = self.section()
        where = f"RUNBOOK section {self.SECTION[3:]!r}"
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        rollout = md_part(path, "## Rollout")
        steps = self.steps(self.prose(rollout))
        proof = next((i for i, s in enumerate(steps) if re.search(r"sf apex run", s)), None)
        self.assertIsNotNone(proof, f"{name}: a Rollout step runs the proof with `sf apex run`")
        step = steps[proof]
        # the RUNBOOK says it where the procedure is: the `- **Apply:**` header line, not a paragraph anywhere
        apply = self.header_line(part, "Apply")
        for text, place in ((apply, f"{where}: the `- **Apply:**` line"),
                            (step, f"{name}: the Rollout's proof step (step {proof + 1})")):
            self.assertRegex(self.norm(text), self.FIND_DUPLICATES,
                             f"{place}: name the proof that follows the deploy: the `Datacloud.FindDuplicates` diagnostic")
            self.assertTrue(self.said(text, self.DIAGNOSTIC, self.NO_DML, negated=True),
                            f"{place}: say in one sentence that the diagnostic (`Datacloud.FindDuplicates`) runs no DML: "
                            "it inserts, writes and saves nothing (unsaved copies)")
            self.assertTrue(self.said(text, self.DIAGNOSTIC + r"|(?i:\bprobes?\b)", self.COPIES, self.EXISTING,
                                      self.ACCOUNT + r"|(?i:\baccounts?\b)", negated=True),
                            f"{place}: say the diagnostic runs on unsaved copies of existing accounts (one sentence)")
            self.assertTrue(self.said(text, r"DIAG", self.RULE_NAMES, self.COUNTS, self.ONLY, negated=True),
                            f"{place}: say the diagnostic prints only `DIAG|` lines with the rule's name and the match "
                            "count (one sentence: rule names and match counts only, never a record's name)")
        self.assertRegex(step, r"(?i)\b(three|3)\b[^.;]{0,30}?\b(probes?|copies|accounts?)\b",
                         f"{name}: the proof step says the diagnostic runs three probes (unsaved copies)")
        self.assertRegex(step, r"(?i)pasted? in full|in full first",
                         f"{name}: the proof's script is pasted in full first (the gate on `sf apex run`)")
        # the probes and what each showed: three distinct clauses of the plan
        plan = self.prose(read(path))
        a, b, c = self.probe_clauses(plan)
        self.assertTrue(a, f"{name}: state probe A with its result in one sentence: an upper-cased copy of a Club that "
                           "has a parent - the Club rule ran, 1 match")
        self.assertTrue(b, f"{name}: state probe B with its result in one sentence: a copy of a Household account - "
                           "the Household rule, 1 match")
        self.assertTrue(c, f"{name}: state probe C with its result in one sentence: a Household account with a club's "
                           "name and ParentId - the Household rule, 1 match, and the match is the Club (cross-type)")
        self.assertTrue(any(x != y and y != z and x != z for x in a for y in b for z in c),
                        f"{name}: the three probes are three sentences (or clauses split by `;`), one each")
        self.assertTrue(self.said(plan, r"(?i)\btransaction\b",
                                  r"(?i)\b(not|never|cannot|can['’]t|don['’]t|doesn['’]t)\s+(be )?(seen|see|sees|visible|"
                                  r"match\w*|find\w*|report\w*)\b|\binvisible\b|\bunseen\b|\bblind\b", negated=True),
                        f"{name}: say why the insert proof could not work, in one sentence: Salesforce's duplicate "
                        "matching does not see records inserted earlier in the same uncommitted transaction")
        self.assertTrue(self.said(plan, self.DEPLOY_DAY, r"\bRyan\b|(?i:\bdecid\w*|\bdecision\b)",
                                  self.DIAGNOSTIC + r"|(?i:\bproof\b|\bcross-?type\b|\bpairs?\b)", negated=True),
                        f"{name}: attribute the proof's redesign (and the cross-type decision) to Ryan, {self.DEPLOY_DAY}, "
                        "in one sentence")
        self.assertNoContradiction(self.prose(rollout), f"{name}: `## Rollout`")

    def test_the_docs_no_longer_describe_the_rolled_back_insert_as_the_proof(self):
        """The rolled-back insert proof is history: no clause of the RUNBOOK section or the plan names it as the
        proof (only as dropped, could not work, a flaw), none says the proof probes spacing (the three probes do
        not), the Rollout no longer makes a missing DuplicateRecordSet the signal to stop, and no quoted Apex
        inserts."""
        part = self.section()
        where = f"RUNBOOK section {self.SECTION[3:]!r}"
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        raw = read(path)            # fences included: a ```text fence is no hiding place for the old proof
        for text, place in ((part, where), (raw, name)):
            found = self.old_proof_claims(text)
            self.assertEqual(found, [], f"{place}: names the rolled-back insert proof as the proof (fenced text included); "
                                        "the proof is the no-DML `Datacloud.FindDuplicates` diagnostic (Ryan, 2026-10-22), "
                                        "and the rolled-back insert is named only as history, in a clause that says it "
                                        "was dropped or could not work: " + " | ".join(repr(s) for s in found))
            found = self.proof_probes_spacing(text)
            self.assertEqual(found, [], f"{place}: says the proof (a probe, the script) answers the spacing question; "
                                        "the diagnostic's three probes do not probe spacing - the read-back and the "
                                        "monthly check compare the sets with `duplicate_account_groups`: "
                                        + " | ".join(repr(s) for s in found))
            found = [s[:160] for s in self.clauses(text) if self.HEDGED_REFUSAL.search(s)]
            self.assertEqual(found, [], f"{place}: hedges the rule's action into a refusal (\"if an insert is refused all "
                                        "the same\"): Report only never refuses a save; the next day's `DUPLICATES_DETECTED` "
                                        "check is the guard, said as that check: " + " | ".join(repr(s) for s in found))
        self.assertNotRegex(self.norm(raw), r"(?i)\b(missing|absent|no|without)\b[^.;]{0,30}?DuplicateRecordSet[^.;]{0,80}?"
                                            r"\b(failure|fail\w*|stop\w*|deactivat\w*)|DuplicateRecordSet[^.;]{0,40}?"
                                            r"\b(missing|absent|does not appear|none)\b[^.;]{0,60}?\b(failure|fail\w*|stop\w*|"
                                            r"deactivat\w*)",
                            f"{name}: the plan still makes a missing DuplicateRecordSet the signal to stop and deactivate "
                            "(fenced text included): that was the insert proof's condition, dropped with it")
        rollout = self.norm(self.prose(md_part(path, "## Rollout")))
        steps = self.steps(rollout)
        proof = next((i for i, s in enumerate(steps) if re.search(r"sf apex run", s)), None)
        self.assertIsNotNone(proof, f"{name}: a Rollout step runs the proof with `sf apex run`")
        step = steps[proof]
        for s in self.clauses(step):
            if self.DROPPED.search(s):
                continue            # the dropped insert proof, as history
            for m in re.finditer(r"(?i)\binsert(s|ed|ing)?\b", s):
                local, post = self.local(s, m), s[m.end():m.end() + 80]
                self.assertTrue(any(rx.search(where) for where in (local, post)
                                    for rx in (self.NEGATION, self.DROPPED, self.CONDITIONAL)),
                                f"{name}: the proof step (step {proof + 1}) inserts: the diagnostic inserts nothing "
                                f"(name an insert only to deny it, or as the dropped proof in a clause that says so): "
                                f"{s[max(0, m.start() - 60):m.end() + 80]!r}")
        self.assertNotRegex(step, r"Database_rollback|\bsavepoint\b|\bSavepoint\b",
                            f"{name}: the proof step names a savepoint or `Database.rollback`: with no DML there is "
                            "nothing to roll back")
        for code in self.fences(raw):
            self.assertNotRegex(code, self.DML, f"{name}: a fenced block (any language) runs DML (insert, update, delete, "
                                                "upsert, merge): the proof is the no-DML diagnostic, and the dropped "
                                                "insert script is not quoted, in no fence")
            self.assertNotRegex(code, self.ROLLBACK_CODE, f"{name}: a fenced block sets a savepoint or rolls back: with no "
                                                          "DML there is nothing to roll back, and the dropped script is not "
                                                          "quoted")

    def test_a_plan_quotes_the_diagnostic_script(self):
        """The script lives in data/ (never committed), so the plan quotes it in full in an ```apex block that does
        what the docs say: reads existing accounts with SOQL, builds three unsaved copies (`new Account(` with
        RecordTypeId and ParentId, or `.clone(`; no name literal), upper-cases one name, hands those probes (and
        never a queried account or an empty list) to `Datacloud.FindDuplicates.findDuplicates`, keeps the result,
        and prints `DIAG|` lines built from `getDuplicateRule()` and the match results' size - never a literal,
        never a record's Name or Id - with no DML and no savepoint."""
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        blocks = [b for b in re.findall(r"(?ms)^```apex[^\n]*\n(.*?)^```", read(path)) if "FindDuplicates" in b]
        self.assertTrue(blocks, f"{name}: quote the diagnostic's script in full in a ```apex block that calls "
                               "`Datacloud.FindDuplicates.findDuplicates`")
        code = re.sub(r"//[^\n]*|/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group()), blocks[0], flags=re.S)
        self.assertRegex(code, r"(List\s*<\s*Datacloud\.FindDuplicatesResult\s*>|Datacloud\.FindDuplicatesResult\s*\[\s*\])"
                               r"\s+\w+\s*=\s*Datacloud\.FindDuplicates\.findDuplicates\s*\(",
                         f"{name}: the ```apex block keeps the result: `List<Datacloud.FindDuplicatesResult> results = "
                         "Datacloud.FindDuplicates.findDuplicates(…)` (the lines are read from it, not thrown away)")
        self.assertRegex(code, r"\[\s*SELECT\b[^\]]*?\bFROM\s+Account\b",
                         f"{name}: the ```apex block reads the existing accounts it copies with SOQL (`[SELECT … FROM Account …]`)")
        # the probes: each `new Account(` to its matching `)`, wherever it sits (a statement, a list or a map literal)
        probes = [self.balanced(code, m.end()) for m in re.finditer(r"new Account\s*\(", code)]
        clones = re.findall(r"\.clone\s*\(", code)
        self.assertGreaterEqual(len(probes) + len(clones), 3,
                                f"{name}: the ```apex block builds three unsaved probes (`new Account(` or `.clone(`)")
        for fields in probes:
            for field in ("RecordTypeId", "ParentId"):
                self.assertIn(field, fields, f"{name}: every `new Account(` probe carries {field} (the rules match on "
                                             f"ParentId and run per record type): `new Account({fields.strip()[:80]}…)`")
        self.assertNotRegex(code, r"\bName\s*=\s*'", f"{name}: a probe's Name is a literal; the probes copy existing accounts' "
                                                     "names (`Name = club.Name…`)")
        # the three probes as the plan describes them: A copies a queried account's Name upper-cased, with its ParentId
        # and record type; C takes the same account's Name and ParentId with the other record type; B copies another
        # queried account with that other record type
        def parts(fields):
            src = re.search(r"\bName\s*=\s*(\w+)\.Name\b", fields)
            parent = re.search(r"\bParentId\s*=\s*(\w+)\.ParentId\b", fields)
            rtype = re.search(r"\bRecordTypeId\s*=\s*(\w+)", fields)
            return (src and src.group(1), parent and parent.group(1), rtype and rtype.group(1),
                    bool(re.search(r"\bName\s*=\s*\w+\.Name\.toUpperCase\(\)", fields)))
        parsed = [parts(f) for f in probes]
        uppers = [p for p in parsed if p[3]]
        self.assertTrue(uppers, f"{name}: probe A's Name is a queried account's Name upper-cased "
                                "(`Name = club.Name.toUpperCase()`)")
        a = uppers[0]
        self.assertTrue(a[0] and a[0] == a[1] and a[2],
                        f"{name}: probe A copies one queried account's Name and ParentId (`Name = x.Name.toUpperCase(), "
                        f"ParentId = x.ParentId`) with a record type variable; got {a!r}")
        c = [p for p in parsed if p is not a and p[0] == a[0] and p[1] == a[1] and p[2] and p[2] != a[2]]
        self.assertTrue(c, f"{name}: probe C takes the same account's Name and ParentId as probe A (`{a[0]}.Name`, "
                           f"`{a[1]}.ParentId`) with the other record type (a Household account named and parented like "
                           "the club)")
        self.assertTrue([p for p in parsed if p is not a and p[0] and p[0] != a[0] and p[2] == c[0][2]],
                        f"{name}: probe B copies another queried account (`Name = hh.Name`) with the Household record type, "
                        f"the one probe C uses ({c[0][2]})")
        # the probes are what findDuplicates gets: every call's argument names a probe - a variable bound to
        # `new Account(` or `.clone(`, the collection holding them (bare, `.get(k)`, `[i]`, `.values()`), the
        # variable of a loop over that collection, or a copy built in the call - and never a queried account
        # itself (`new List<Account>{ club }`, the saved original) nor nothing (`new List<Account>()`)
        sources, probe_names = self.apex_bindings(code)
        calls = list(re.finditer(r"FindDuplicates\s*\.\s*findDuplicates\s*\(", code))
        self.assertTrue(calls, f"{name}: the ```apex block calls `Datacloud.FindDuplicates.findDuplicates(`")
        for m in calls:
            arg = re.sub(r"'(?:[^'\\]|\\.)*'", "''", self.balanced(code, m.end()))
            shown = " ".join(arg.split())
            passed = [s for s in sorted(sources) if self.passes_record(arg, s)]
            self.assertFalse(passed, f"{name}: `findDuplicates({shown})` is given the queried account "
                                     f"`{', '.join(passed)}` itself (the saved original) - the diagnostic probes unsaved "
                                     "copies, so the argument is a probe, never a record read from the org")
            self.assertTrue(re.search(self.PROBE_MAKER, arg)
                            or any(re.search(rf"\b{re.escape(p)}\b", arg) for p in probe_names),
                            f"{name}: `findDuplicates({shown})` is given none of the probes {sorted(probe_names)}: "
                            "pass a probe variable, the probe collection or one of its elements (`probes.get(k)`), "
                            "never an empty list")
        self.assertNotRegex(code, self.DML, f"{name}: the ```apex block runs DML: the diagnostic inserts nothing")
        self.assertNotRegex(code, self.ROLLBACK_CODE, f"{name}: the ```apex block sets a savepoint or rolls back: no DML, "
                                                      "nothing to roll back")
        self.assertIn("getDuplicateRule()", code, f"{name}: the ```apex block reads each rule's name from the result "
                                                  "(`getDuplicateRule()`)")
        self.assertIn("getMatchResults()", code, f"{name}: the ```apex block reads the match results (`getMatchResults()`)")
        self.assertRegex(code, r"getMatchRecords\(\)\s*\.size\(\)|\bgetSize\(\)",
                         f"{name}: the ```apex block counts the matches (`getMatchRecords().size()` or `getSize()`)")
        debugs = re.findall(r"(?m)^.*System\.debug\s*\(.*$", code)
        self.assertTrue(debugs, f"{name}: the ```apex block prints `DIAG|` lines with `System.debug`")
        for line in debugs:
            self.assertIn("DIAG|", line, f"{name}: every `System.debug` of the ```apex block prints a `DIAG|` line: {line.strip()!r}")
            self.assertNotRegex(line, r"System\.debug\s*\(\s*'[^']*'\s*\)",
                                f"{name}: a `DIAG|` line is a string literal (a hard-coded result): build it from the result, "
                                f"`getDuplicateRule()` and the match count: {line.strip()!r}")
            self.assertNotRegex(line, r"\.Name\b|getRecord\(\)|\.Id\b",
                                f"{name}: a `DIAG|` line prints a record's Name or Id; rule names and match counts only: "
                                f"{line.strip()!r}")
        self.assertTrue(any("getDuplicateRule()" in line for line in debugs),
                        f"{name}: a `DIAG|` line carries the rule's name from the result (`getDuplicateRule()`)")
        loop = re.search(r"for\s*\(\s*Datacloud\.DuplicateResult\b", code)
        self.assertTrue(loop and re.search(r"System\.debug\s*\([^\n]*getDuplicateRule\(\)", code[loop.end():]),
                        f"{name}: the `DIAG|` line with `getDuplicateRule()` is printed inside the loop over the results "
                        "(`for (Datacloud.DuplicateResult d : …getDuplicateResults())`), one line per rule that ran")

    def test_the_docs_state_the_cross_type_pairs_and_the_by_hand_review(self):
        """Ryan, 2026-10-22 (decision 2): a Duplicate Rule's record-type condition only picks the rule for the
        record saved and does not limit the candidates, so Salesforce may report a Household account and a Club
        of one name and parent as a pair; `duplicate_account_groups` keeps its own definition and the monthly
        check reviews such a pair by hand. No clause says the condition applies to the candidates, or that a Club
        and a Household account never match."""
        part = self.section()
        where = f"RUNBOOK section {self.SECTION[3:]!r}"
        rules = self.subpart(part, "### The fields and the rules")
        monthly = self.subpart(part, "### The monthly check")
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        raw = read(path)
        plan = self.prose(raw)
        # where it is said: the rules subsection says what the condition does; the monthly check says what to do
        # with a cross-type pair (a paragraph of keywords anywhere else is not the procedure)
        for text, place in ((rules, f"{where}, `### The fields and the rules`"), (plan, name)):
            self.assertTrue(self.says_cross_type_pair(text),
                            f"{place}: say in one sentence that Salesforce may report a Household account and a Club of "
                            "one name and parent as a pair (one DuplicateRecordSet): the record-type condition picks the "
                            "rule for the record saved and does not limit the candidates")
            self.assertTrue(self.said(text, r"(?i)\bcondition\b", r"(?i)\b(record )?(being )?saved\b|\bthe record saved\b|"
                                                                   r"\bsaving\b|\bon save\b|\bthe saved record\b",
                                      r"(?i)\bonly\b|\bpicks\b|\bdecides\b|\bchooses\b|\bselects\b|\bwhich rule\b", negated=True),
                            f"{place}: say what the record-type condition does: it picks (decides only) which rule runs "
                            "for the record being saved, in one sentence")
        for text, place in ((part, where), (raw, name)):
            found = self.condition_filters_candidates(text)
            self.assertEqual(found, [], f"{place}: says a rule's record-type condition applies to the candidates (the "
                                        "records matched); it decides only which rule runs for the record saved: "
                                        + " | ".join(found))
            found = self.club_and_household_never_match(text)
            self.assertEqual(found, [], f"{place}: says a Club and a Household (partner) account never match or are "
                                        "kept apart; Salesforce may report them as a pair (only the Python side, "
                                        "`duplicate_account_groups`, keeps record types apart): " + " | ".join(found))
            found = self.rules_give_same_type(text)
            self.assertEqual(found, [], f"{place}: says the rules (or the answer) are \"same record type\" without saying "
                                        "that holds for the record saved only (the candidates are of any record type): "
                                        + " | ".join(repr(s) for s in found))
        self.assertTrue(self.says_cross_type_pair(monthly),
                        f"{where}, `### The monthly check`: say a Household account and a Club of one name and parent may "
                        "be reported as a pair (a set `duplicate_account_groups` has no group for), in one sentence")
        self.assertTrue(self.said(monthly, r"(?i)\bpairs?\b|\bcross-?type\b|\bHousehold\b",
                                  r"(?i)\bby hand\b|\bmanual\w*|\blooked at\b|\breview\w*|\bjudge\w*|\bdecide\w*", negated=True),
                        f"{where}, `### The monthly check`: say such a (cross-type) pair is reviewed by hand, in one sentence")
        self.assertTrue(self.said(monthly, r"duplicate_account_groups", r"(?i)\bits own\b|\bown (definition|rule|criteria)\b|"
                                                                        r"\bsame record type\b|\bunchanged\b|\bkeeps?\b|\bstays?\b|"
                                                                        r"\bas before\b|\bnot changed\b|\bno change\b|\bstill\b|"
                                                                        r"\bdoes not\b|\bnever\b",
                                  negated=True),
                        f"{where}, `### The monthly check`: say `duplicate_account_groups` keeps its own definition (the "
                        "same record type: it never groups a Club with a Household account), in one sentence")
        # the Verify line and the monthly paragraph agree with it: a cross-type set is a set without a group, looked at
        # by hand, not a spacing disagreement
        verify = self.header_line(part, "Verify")
        self.assertRegex(verify, r"(?i)\bcross-?type\b|\bpairs?\b",
                         f"{where}: the `- **Verify:**` line names the cross-type pair the comparison with "
                         "`duplicate_account_groups` may show")
        self.assertRegex(verify, r"(?i)\bby hand\b|\blooked at\b|\breview\w*|\bjudge\w*",
                         f"{where}: the `- **Verify:**` line says a cross-type pair is looked at by hand")
        self.assertTrue(self.said(monthly, r"(?i)\bdisagree\w*|\bdiffer\w*|\bwithout a group\b|\bset without\b|\bgroup without\b",
                                  r"(?i)\bcross-?type\b|\bHousehold\b|\brecord type\b", negated=True),
                        f"{where}, `### The monthly check`: the paragraph on a set without a group names the cross-type "
                        "case beside spacing, in one sentence")
        self.assertNoContradiction(part, where)

    # --- the plan ---------------------------------------------------------------------------------------

    def test_a_plan_carries_the_rule_deploy_and_the_read_back(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        text = read(path)
        keys, _ = docs_index.frontmatter(text)
        self.assertIn("status", keys, f"{name}: frontmatter `status:`")
        word, problem = docs_index.status_of(keys["status"])
        self.assertIsNone(problem, f"{name}: {problem}")
        self.assertIn(word, ("accepted", "in-progress", "done"),
                      f"{name}: the plan is accepted, in-progress or done once implemented (not {word!r})")
        if word == "done":
            self.assertRegex(keys.get("done", ""), r"^\d{4}-\d\d-\d\d", f"{name}: a done plan carries `done:`")
        self.assertRegex(text.split("\n## ", 1)[0], self.TICKET,
                         f"{name}: name ticket #84 in the frontmatter, the title or the opening paragraph")
        self.assertRegex(text, r"(?m)^## Result\b", f"{name}: no `## Result` section")
        result = self.norm(md_part(path, "## Result").split("\n", 1)[1] if "\n" in md_part(path, "## Result") else "")
        self.assertTrue(re.search(r"[A-Za-z]{3,}", result), f"{name}: `## Result` is empty")
        raw, bodies = {}, {}
        for heading, least in (("## Rollout", 60), ("## Rollback", 15)):
            part = md_part(path, heading)
            raw[heading] = self.prose(part.split("\n", 1)[1] if "\n" in part else "")
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
        self.assertRegex(flat_rollout, r"DuplicateRule|Duplicate Rule", f"{name}: the Rollout builds the Duplicate Rules on Account")
        self.assertTrue(self.said(rollout, r"(?i)\bduplicate rules?\b|DuplicateRule", r"(?<!\w)Club(?!\w)", r"(?<!\w)Household(?!\w)",
                                  r"(?i)\b(per|each|every|one for each|two)\b[^.;]{0,25}?\brecord types?\b|\btwo duplicate rules\b"),
                        f"{name}: the Rollout builds one Duplicate Rule per record type (Club, Household), in one sentence")
        self.assertTrue(self.said(rollout, r"(?i)MatchingRule|Matching Rule", r"\bName\b", r"ParentId"),
                        f"{name}: the Rollout's Matching Rule matches Name and ParentId (one sentence)")
        for s in self.clauses(rollout):
            if "RecordTypeId" in s and re.search(r"(?i)\bmatch\w*", s):
                self.assertTrue(self.denied_near(s, re.search(r"RecordTypeId", s)),
                                f"{name}: RecordTypeId is not a matching item (the record type is each Duplicate Rule's "
                                f"condition): {s[:160]!r}")
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
        # the steps, numbered: the retrieve, the check-only, Ryan's go, the deploy, then the proof (the rules
        # must be active for the diagnostic to run them), the read-back, the next day's check
        steps = self.steps(rollout)
        self.assertGreaterEqual(len(steps), 6, f"{name}: number the Rollout's steps (`1. …`, at least six: the retrieve, "
                                               "the check-only, Ryan's go, the deploy, the proof, the read-back, the "
                                               "next day)")
        def first(rx):
            return next((i for i, s in enumerate(steps) if re.search(rx, s)), None)

        retrieve = first(r"before/")
        self.assertIsNotNone(retrieve, f"{name}: a Rollout step retrieves what is live into `before/`")
        check = first(r"(?i)check-only|--dry-run|sf project deploy validate")
        self.assertIsNotNone(check, f"{name}: a Rollout step is the check-only (`sf project deploy validate` or `--dry-run`)")
        go = first(r"Ryan['’]s (go|answer|yes)\b")
        self.assertIsNotNone(go, f"{name}: a Rollout step is Ryan's go")
        deploy = first(r"sf project deploy (quick|start)\b(?![^.;]{0,60}--dry-run)")
        self.assertIsNotNone(deploy, f"{name}: a Rollout step deploys with `sf project deploy quick -o glow -i <validation "
                                     "id>` (or `start` without `--dry-run`)")
        proof = first(r"sf apex run")
        self.assertIsNotNone(proof, f"{name}: a Rollout step runs the proof with `sf apex run`")
        after = first(r"after/")
        self.assertIsNotNone(after, f"{name}: a Rollout step retrieves into `after/` and compares")
        self.assertTrue(retrieve < check < go < deploy,
                        f"{name}: the Rollout's steps come in this order, each its own step: the retrieve into `before/` "
                        f"(step {retrieve + 1}), the check-only (step {check + 1}), Ryan's go (step {go + 1}), the "
                        f"deploy (step {deploy + 1})")
        self.assertTrue(re.search(r"(?i)\b(answer\w*|repl\w*|says|said|yes)\b", steps[go])
                        and re.search(r"(?i)\b(check-only|validat\w*|result)\b", steps[go]),
                        f"{name}: Ryan's go is his answer, given after the check-only's result is shown to him (the "
                        "go step says so)")
        self.assertNotRegex(flat_rollout, r"(?i)\btaken as (the|his|a) go\b|\bcounts? as (the|his|a) go\b|\bno further "
                                          r"prompt\b|\bstanding go\b|\bblanket go\b|\bgo in advance\b|\b(earlier|previous|"
                                          r"prior) go\b|\bwithout (asking|a prompt|his answer)\b|move forward[^.;]{0,60}?"
                                          r"\b(is|as|was) (the|his|a) go\b",
                            f"{name}: nothing said earlier is the go: the go is Ryan's answer to this deploy's prompt")
        self.assertTrue(deploy < proof, f"{name}: the `sf apex run` proof comes after the deploy (the rules must be active "
                                        "for `Datacloud.FindDuplicates` to run them)")
        self.assertGreaterEqual(after, deploy, f"{name}: after the deploy, retrieve into `after/` and compare")
        # the read-back: retrieve into after/ and compare; both rules active, four fields; the Contact rule the same
        self.assertTrue(re.search(r"(?i)\bcompar\w*|\bdiff\b", steps[after]),
                        f"{name}: the `after/` step compares the retrieve with the build")
        self.assertRegex(flat_rollout, r"(?i)\b(all|both|every|each|the three|three|the two|two|the)\s+(\w+\s+)?rules\b"
                                       r"[^.;]{0,60}?\bactive\b|\bactive\b[^.;]{0,60}?\b(all|both|the three|three)\s+(\w+\s+)?rules\b|IsActive",
                         f"{name}: the read-back's SOQL shows every rule active (the Matching Rule and the Duplicate Rule "
                         "per record type)")
        self.assertTrue([s for s in self.clauses(rollout) if self.CONTACT_RULE in s
                         and re.search(r"(?i)\bunchanged\b|\bcompar\w*|\bdiff\b|\bequal\w*|\bthe same\b|\buntouched\b", s)],
                        f"{name}: the Rollout retrieves and compares the Contact rule {self.CONTACT_RULE!r}: unchanged")
        self.assertTrue(self.said(rollout, r"duplicate_account_groups", r"DuplicateRecordSet|DuplicateRecordItem"),
                        f"{name}: the read-back compares `glow.salesforce.duplicate_account_groups` with the rule's "
                        "`DuplicateRecordSet`s (one sentence)")
        # the next day
        day_after = [i for i, s in enumerate(steps) if "DUPLICATES_DETECTED" in s and "Failed" in s
                     and re.search(r"(?i)\bnext day\b|\bday after\b|\bfollowing day\b|\btomorrow\b|\b24 hours\b", s)]
        self.assertTrue(day_after and day_after[0] > proof,
                        f"{name}: the next day's step (after the proof) checks that no batch is `Failed` with "
                        "`DUPLICATES_DETECTED`")
        self.assertIn("auto_sync", flat_rollout, f"{name}: the next day's step checks the Salesforce plan of "
                                                 "`tools/auto_sync.py` is unchanged")
        self.assertNoContradiction(rollout, f"{name}: `## Rollout`")
        # the Rollback deactivates the rule in the org, by a named action
        self.assertTrue(self.said(rollback, r"(?i)\bdeactivat\w*|\binactive\b|isActive>?\s*false|active\s*=\s*false",
                                  r"(?i)\brule\b"),
                        f"{name}: the Rollback deactivates the Duplicate Rule (one sentence, not negated)")
        self.assertRegex(bodies["## Rollback"], r"sf project deploy (start|quick)\b|sf data update record\b[^.;]{0,80}?"
                                                r"--sobject DuplicateRule\b|\bSetup\b[^.;]{0,60}?\bDuplicate Rules?\b|"
                                                r"\bDuplicate Rules?\b[^.;]{0,60}?\bSetup\b",
                         f"{name}: the Rollback names the action on the org: a `sf project deploy start|quick` of the rule "
                         "with `isActive` false, `sf data update record --sobject DuplicateRule …`, or the Setup path")
        self.assertNotRegex(bodies["## Rollback"], r"(?i)\brepository copy\b|\bin this plan\b|\bstay\w* as deployed\b|"
                                                   r"\bseparate decision\b|\blater ticket\b|\bonly in the repo\b|"
                                                   r"\bon disk only\b|\bnot (be )?deployed\b",
                            f"{name}: the Rollback acts on the org, not on a file in the repository or a later ticket")
        self.assertNoContradiction(rollback, f"{name}: `## Rollback`", rollback=True)

    def test_a_plan_records_the_deploy_the_read_back_and_the_sort_order(self):
        """The Result of 2026-10-22: the deploy id with its time and count, the check-only id, each Duplicate
        Rule's own sortOrder and why, the read-back (after/ = build/ but for Salesforce's normalisation, the four
        field permissions present), the three rules active and the Contact rule unchanged, the diagnostic that
        day, and the counts (0 groups, 0 cross-type, 0 sets). Counts and ids only."""
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        plan = self.prose(read(path))
        result = self.norm(self.prose(md_part(path, "## Result")))
        deploy = [s for s in self.clauses(plan) if self.DEPLOY_ID in s]
        self.assertTrue(deploy, f"{name}: record the deploy id `{self.DEPLOY_ID}`")
        self.assertTrue([s for s in deploy if self.DEPLOY_TIME in s and "UTC" in s],
                        f"{name}: the deploy id's sentence gives its time, `{self.DEPLOY_DAY} {self.DEPLOY_TIME} UTC`")
        at = self.norm(plan).find(self.DEPLOY_ID)
        self.assertIn(self.DEPLOY_DAY, self.norm(plan)[max(0, at - 400):at + 200],
                      f"{name}: the deploy id is dated {self.DEPLOY_DAY} (the date near the id)")
        self.assertTrue([s for s in deploy if re.search(r"(?<![\w.])9\s*(/|of)\s*9\b|\bnine of nine\b|\ball nine\b", s)],
                        f"{name}: the deploy id's sentence gives its count, 9/9 components")
        self.assertIn(self.CHECK_ONLY_ID, self.norm(plan), f"{name}: record the check-only id `{self.CHECK_ONLY_ID}`")
        # each Duplicate Rule has its own sortOrder (Club 1, Household 2): two rules with sortOrder 1 are refused
        self.assertTrue(self.said(plan, r"sortOrder",
                                  r"(?<![\w.])1(?![\w.:])[^.;]{0,30}?\bClub\b|\bClub\b[^.;]{0,30}?(?<![\w.])1(?![\w.:])",
                                  r"(?<![\w.])2(?![\w.:])[^.;]{0,30}?\bHousehold\b|\bHousehold\b[^.;]{0,30}?(?<![\w.])2(?![\w.:])",
                                  negated=True),
                        f"{name}: say each Duplicate Rule has its own `sortOrder` - Club 1, Household 2 - in one sentence")
        self.assertTrue(self.said(plan, r"sortOrder", r"(?i)\bsequential\b|\brefus\w*|\breject\w*", negated=True),
                        f"{name}: say why: two rules with `sortOrder` 1 were refused (\"SortOrder must be in sequential "
                        "order from 1\"), in one sentence")
        self.assertIn("SortOrder must be in sequential order from 1", result,
                      f"{name}: the Result quotes Salesforce's refusal as it was: \"SortOrder must be in sequential order from 1\"")
        # the read-back
        self.assertIn("data/sf_dupflags_2026-10-21/after/", result,
                      f"{name}: the Result names the read-back folder, `data/sf_dupflags_2026-10-21/after/`")
        self.assertTrue(self.said(result, r"after/", r"build/", r"(?i)\bnormali[sz]\w*", negated=True),
                        f"{name}: the Result says `after/` equals `build/` but for Salesforce's normalisation (one sentence)")
        self.assertTrue(self.said(result, r"(?i)\b(four|4)\b", r"(?i)\bfield ?permissions?\b",
                                  r"(?i)\bpresent\b|\bthere\b|\bin place\b|\bfound\b|\ball\b|\bread back\b", negated=True),
                        f"{name}: the Result says the four field permissions are present in `after/` (one sentence)")
        self.assertTrue(self.said(result, r"Name_Parent_Club_Report", r"Name_Parent_Household_Report", r"(?i)\bactive\b", negated=True),
                        f"{name}: the Result says both Duplicate Rules are active, by name (one sentence)")
        self.assertTrue(self.said(result, r"(?i)\bMatching ?Rule\b|\bName_Parent\b(?!_)", r"(?i)\bactive\b", negated=True),
                        f"{name}: the Result says the Matching Rule `Name_Parent` is active")
        self.assertTrue(self.said(result, r"First & Last & Account|First_Last|(?i:\bContact rule\b)",
                                  r"(?i)\bunchanged\b|\bequal\w*|\bthe same\b|\buntouched\b|\bidentical\b", negated=True),
                        f"{name}: the Result says the Contact rule {self.CONTACT_RULE!r} is unchanged (its metadata equal "
                        "to `before/`)")
        # the diagnostic that day, and the counts
        self.assertIn(self.DEPLOY_DAY, result, f"{name}: the Result is dated {self.DEPLOY_DAY}")
        self.assertRegex(result, self.DIAGNOSTIC, f"{name}: the Result records the `Datacloud.FindDuplicates` diagnostic")
        self.assertRegex(result, r"(?<![\w.])0\s+(\w+[\s+-]*){0,4}?groups?\b",
                         f"{name}: the Result gives the count of same-name-and-parent groups that day (0 groups)")
        self.assertRegex(result, r"(?<![\w.])0\s+cross-?type", f"{name}: the Result gives the count of cross-type pairs (0)")
        self.assertRegex(result, r"(?<![\w.])0\s+(\w+\s+){0,3}?(sets|DuplicateRecordSets?)\b",
                         f"{name}: the Result gives the count of Account DuplicateRecordSets that day (0 sets)")
        self.assertNoContradiction(result, f"{name}: `## Result`")

    def test_the_plan_is_not_done_before_the_next_day_check(self):
        """Deployed 2026-10-22, so the plan is in-progress or done, says nowhere that nothing is deployed, and is
        `done` only once the Result records the next day's batch check (step 8) with its date; while that check
        is pending the Result says so."""
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        path = self.plan_path()
        name = os.path.relpath(path, REPO)
        text = read(path)
        keys, _ = docs_index.frontmatter(text)
        word, _ = docs_index.status_of(keys.get("status", ""))
        self.assertIn(word, ("in-progress", "done"), f"{name}: deployed {self.DEPLOY_DAY}: the status is in-progress "
                                                      f"(step 8 pending) or done (not {word!r})")
        self.assertNotRegex(self.norm(text), self.NOTHING_DEPLOYED,
                            f"{name}: says the deploy waits (for Ryan's go, for his go) or nothing is deployed - the "
                            f"frontmatter's comment, the opening, the Result, a fence: deployed {self.DEPLOY_DAY} "
                            f"{self.DEPLOY_TIME} UTC (say it in the past: \"waited for his go, given {self.DEPLOY_DAY}\")")
        today = datetime.date.today().isoformat()
        result = self.norm(self.prose(md_part(path, "## Result")))
        clauses = self.clauses(result)
        pending = [s for s in clauses if self.NEXT_DAY_WORDS.search(s) and self.PENDING.search(s)]
        recorded = [s for s in clauses if self.NEXT_DAY_WORDS.search(s) and not self.PENDING.search(s)
                    and re.search(r"2026-10-2[3-9]|2026-1[12]-\d\d|202[7-9]-\d\d-\d\d", s)
                    and re.search(r"DUPLICATES_DETECTED|\bFailed\b|auto_sync|\bbatches\b", s)]
        for s in recorded:
            for d in re.findall(r"\d{4}-\d\d-\d\d", s):
                self.assertLessEqual(d, today, f"{name}: the next day's check is recorded on {d}, after today ({today}): "
                                               "a result is written when it exists, never ahead")
        if word == "done":
            self.assertTrue(recorded, f"{name}: a done plan's Result records the next day's batch check (step 8) with its "
                                      f"date ({self.NEXT_DAY} or later) and its counts (no batch `Failed` with "
                                      "`DUPLICATES_DETECTED`, `auto_sync` unchanged)")
            self.assertEqual(pending, [], f"{name}: done, but the Result still says the next day's check is pending: "
                                          + " | ".join(repr(s[:120]) for s in pending))
            self.assertGreaterEqual(keys.get("done", "")[:10], self.NEXT_DAY,
                                    f"{name}: `done:` is the day of the next day's check, {self.NEXT_DAY} or later")
            self.assertLessEqual(keys.get("done", "")[:10], today, f"{name}: `done:` is after today ({today})")
        else:
            self.assertTrue(pending or recorded,
                            f"{name}: the Result says where the next day's batch check (step 8, {self.NEXT_DAY}) stands: "
                            "pending, or recorded with its date and counts")
        # the RUNBOOK's Status line and the plan agree on step 8: both pending, or both recorded
        status = self.header_line(self.section(), "Status")
        step8 = [s for s in self.clauses(status) if self.NEXT_DAY_WORDS.search(s)]
        self.assertTrue(step8, f"RUNBOOK section {self.SECTION[3:]!r}: the `- **Status:**` line says where the next day's "
                               "batch check (step 8) stands")
        runbook_pending = any(self.PENDING.search(s) for s in step8)
        plan_pending = not recorded
        self.assertEqual(plan_pending, runbook_pending,
                         f"{name} and the RUNBOOK's `- **Status:**` line disagree on step 8: the plan says it is "
                         f"{'pending' if plan_pending else 'recorded'}, the RUNBOOK says it is "
                         f"{'pending' if runbook_pending else 'done'}")

    def test_the_runbook_status_carries_the_deploy_and_the_next_day_check(self):
        """The section's Status line says the rules are live: the deploy id and its date, and where the next day's
        batch check stands."""
        part = self.section()
        where = f"RUNBOOK section {self.SECTION[3:]!r}"
        status = self.header_line(part, "Status")
        self.assertIn(self.DEPLOY_ID, status, f"{where}: the `- **Status:**` line carries the deploy id `{self.DEPLOY_ID}`")
        self.assertIn(self.DEPLOY_DAY, status, f"{where}: the `- **Status:**` line dates the deploy {self.DEPLOY_DAY}")
        self.assertRegex(status, r"(?i)\bdeployed\b|\blive\b", f"{where}: the `- **Status:**` line says deployed (live)")
        self.assertNotRegex(self.norm(part), self.NOTHING_DEPLOYED,
                            f"{where}: says the deploy waits or nothing is deployed: deployed {self.DEPLOY_DAY}")
        self.assertTrue(self.NEXT_DAY_WORDS.search(status),
                        f"{where}: the `- **Status:**` line says where the next day's batch check (step 8, {self.NEXT_DAY}) "
                        "stands: pending, or done with its date")
        self.assertNoContradiction(part, where)

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
        # the review's two design changes (2026-10-21), recorded as decisions Ryan can overrule
        self.assertTrue(self.said(e, r"`?jotform`?", r"(?<![\w-])`?no`?(?![\w-])", r"`?Partner report`?",
                                  self.PARTNER_BATCHES, negated=True),
                        f"{where}: the obsolete Club exception: the clubs of a partner marked `no` in the Partners tab's "
                        "`jotform` column are judged by their partner account's `Partner report` batches, not their own")
        self.assertTrue(self.said(e, r"(?i)\bduplicate rules?\b|DuplicateRule",
                                  r"(?i)\b(per|each|every|one for each|two)\b[^.;]{0,25}?\brecord types?\b|\btwo duplicate rules\b",
                                  r"(?<!\w)Household(?!\w)", negated=True),
                        f"{where}: the matching design: one report-only Duplicate Rule per record type (Club, Household) "
                        "with the condition Record Type equals that type; the Matching Rule on Name and ParentId")
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

    def test_a_decision_records_the_proof_and_the_cross_type_pairs(self):
        """Ryan's two decisions of 2026-10-22 are a dated section at the end of DECISIONS (the file's header): the
        proof is the no-DML `Datacloud.FindDuplicates` diagnostic because the rolled-back insert could not work
        (the same uncommitted transaction), and cross-type pairs are accepted and documented, the record-type
        condition picking the rule for the record being saved only; the entry says it amends the 2026-10-21
        one, and that entry gets a dated `- 2026-10-22:` bullet pointing at it, so its sentences on the
        rolled-back proof waiting for the go and on "same record type" as the rules' answer are dated history,
        never current without the pointer."""
        entries = re.split(r"(?m)^(?=### )", read(self.DECISIONS))[1:]

        def day(entry):
            m = re.match(r"### (\d{4}-\d\d-\d\d) ", entry)
            return m.group(1) if m else ""

        old = [x for x in entries if day(x) == "2026-10-21" and self.TICKET.search(x) and re.search(r"(?i)\bobsolete\b", x)]
        self.assertTrue(old, "docs/DECISIONS.md: the 2026-10-21 entry on ticket #84 (the definitions) is missing")
        new = [x for x in entries if day(x) >= self.DEPLOY_DAY and self.TICKET.search(x)
               and re.search(self.DIAGNOSTIC, self.norm(x)) and re.search(r"(?i)\bcross-?type\b|\bpairs?\b", x)]
        self.assertTrue(new, f"docs/DECISIONS.md: no dated entry `### {self.DEPLOY_DAY} — …` (or later) naming ticket #84, "
                             "the `Datacloud.FindDuplicates` diagnostic and the cross-type pairs (one section for Ryan's "
                             "two decisions of 2026-10-22)")
        e = new[0]
        where = f"docs/DECISIONS.md {day(e)}"
        self.assertGreater(entries.index(e), entries.index(old[0]),
                           f"{where}: the new entry comes after the 2026-10-21 one (the file is in date order, new "
                           "entries at the end)")
        for part in ("**Why", "**Rejected", "**Consequences"):
            self.assertIn(part, e, f"{where}: no {part}** bullet (the file's header)")
        self.assertTrue(self.said(e, r"\bRyan\b", self.DEPLOY_DAY, negated=True),
                        f"{where}: attribute the decisions to Ryan, {self.DEPLOY_DAY}, in one sentence")
        # decision 1: the proof is the no-DML diagnostic, because the rolled-back insert could not work
        self.assertTrue(self.said(e, self.DIAGNOSTIC, self.NO_DML, negated=True),
                        f"{where}: say the proof is the no-DML `Datacloud.FindDuplicates` diagnostic (inserts, writes, saves "
                        "nothing; unsaved copies), in one sentence")
        self.assertTrue(self.said(e, r"(?i)\btransaction\b",
                                  r"(?i)\b(not|never|cannot|can['’]t|don['’]t|doesn['’]t)\s+(be )?(seen|see|sees|visible|"
                                  r"match\w*|find\w*|report\w*)\b|\binvisible\b|\bunseen\b|\bblind\b", negated=True),
                        f"{where}: say why, in one sentence: the rolled-back insert proof could not work because Salesforce's "
                        "duplicate matching does not see records inserted earlier in the same uncommitted transaction")
        found = self.old_proof_claims(e)
        self.assertEqual(found, [], f"{where}: names the rolled-back insert proof as the proof (name it only as dropped, "
                                    "could not work): " + " | ".join(repr(s) for s in found))
        self.assertEqual(self.proof_probes_spacing(e), [], f"{where}: says the proof probes spacing; the three probes do not")
        # decision 2: cross-type pairs accepted and documented; the condition picks the rule for the record saved only
        self.assertTrue(self.says_cross_type_pair(e),
                        f"{where}: say Salesforce may report a Household account and a Club of one name and parent as a "
                        "pair, in one sentence")
        self.assertTrue(self.said(e, r"(?i)\bcross-?type\b|\bpairs?\b", r"(?i)\baccept\w*|\bdocumented\b", negated=True),
                        f"{where}: say the cross-type pairs are accepted and documented (one sentence)")
        self.assertTrue(self.said(e, r"(?i)\bcondition\b", r"(?i)\b(record )?(being )?saved\b|\bthe record saved\b|\bsaving\b|"
                                                           r"\bon save\b|\bthe saved record\b",
                                  r"(?i)\bonly\b|\bpicks\b|\bdecides\b|\bchooses\b|\bselects\b|\bwhich rule\b", negated=True),
                        f"{where}: say the record-type condition picks (decides only) which rule runs for the record being "
                        "saved, in one sentence")
        found = self.condition_filters_candidates(e)
        self.assertEqual(found, [], f"{where}: says the condition applies to the candidates: " + " | ".join(found))
        found = self.club_and_household_never_match(e)
        self.assertEqual(found, [], f"{where}: says a Club and a Household account never match (Salesforce may report them "
                                    "as a pair; only the Python side keeps record types apart): " + " | ".join(found))
        self.assertTrue(self.said(e, r"(?i)\b(no|without|not a)\b[^.;]{0,25}?\b(code|metadata)\b[^.;]{0,25}?\bchange",
                                  negated=True),
                        f"{where}: say the cross-type decision changes no code and no metadata (one sentence)")
        self.assertTrue(self.said(e, r"2026-10-21", r"(?i)\bamend\w*|\bsupersed\w*|\brevers\w*|\bchang\w*|\breplac\w*|"
                                                     r"\bupdat\w*|\bearlier\b|\bprevious\b|\bthat entry\b", negated=True),
                        f"{where}: say the entry amends the 2026-10-21 decision (the file's header: a decision that amends "
                        "an earlier one says so), in one sentence")
        rejected = self.norm(e.split("**Rejected", 1)[1].split("**Consequences", 1)[0])
        self.assertRegex(rejected, r"(?i)\binsert\w*|\brolled[- ]back\b|\bmetadata\b|\bcandidates?\b|\bcross-?type\b|"
                                   r"\bthird rule\b|\bapart\b",
                         f"{where}: **Rejected** names what was not done: keeping the rolled-back insert proof, or a "
                         "metadata change to keep a Club and a Household account apart")
        rest = re.sub(r"(?ms)^- \*\*Rejected.*?(?=^- \*\*|\Z)", "", e)
        self.assertNoContradiction(rest, where)
        found = self.rules_give_same_type(e)
        self.assertEqual(found, [], f"{where}: says the rules are \"same record type\" without \"for the record saved\": "
                                    + " | ".join(repr(s) for s in found))
        # the 2026-10-21 entry: a dated bullet pointing at the new entry (the file's convention), naming the proof and
        # the cross-type pairs, so what it says of the rolled-back proof and of "same record type" as the rules' answer
        # is dated history; the bullet itself states neither as current, and nothing in the entry still has the deploy
        # waiting for Ryan's go (the go was given 2026-10-22: say it in the past)
        o = old[0]
        pointer_rx = r"(?m)^\s*- " + self.DEPLOY_DAY + r"[:,].*(?:\n(?!\s*- |\n|#).*)*"
        pointers = re.findall(pointer_rx, o)
        self.assertNotRegex(self.norm(re.sub(pointer_rx, " ", o)), self.NOTHING_DEPLOYED,
                            f"docs/DECISIONS.md 2026-10-21: still says the deploy (or the proof) waits for Ryan's go; the go was "
                            f"given {self.DEPLOY_DAY}: say it in the past (\"waited for Ryan's go, given {self.DEPLOY_DAY}\") "
                            "or point at the new entry in that sentence")
        self.assertTrue(pointers, f"docs/DECISIONS.md 2026-10-21: the entry gets a dated bullet `- {self.DEPLOY_DAY}: …` "
                                  f"pointing at the {day(e)} entry (the file's header: the earlier decision gets a dated "
                                  "bullet pointing at the one that amends it)")
        joined = " ".join(flat(b) for b in pointers)
        self.assertRegex(joined, r"(?i)\bsee\b|\bentry\b|\bamend\w*|\bsupersed\w*|\bdecision\b|\bbelow\b",
                         f"docs/DECISIONS.md 2026-10-21: the `- {self.DEPLOY_DAY}:` bullet points at the new entry (\"see the "
                         f"{day(e)} entry\", \"amended\")")
        self.assertRegex(self.norm(joined), self.DIAGNOSTIC + r"|(?i:\bproof\b)",
                         f"docs/DECISIONS.md 2026-10-21: the `- {self.DEPLOY_DAY}:` bullet names the proof's change (the "
                         "diagnostic)")
        self.assertRegex(joined, r"(?i)\bcross-?type\b|\bpairs?\b|\brecord type\b",
                         f"docs/DECISIONS.md 2026-10-21: the `- {self.DEPLOY_DAY}:` bullet names the cross-type pairs")
        self.assertEqual(self.old_proof_claims(joined), [], f"docs/DECISIONS.md 2026-10-21: the `- {self.DEPLOY_DAY}:` bullet "
                                                             "names the rolled-back proof as current")
        self.assertEqual(self.condition_filters_candidates(joined), [],
                         f"docs/DECISIONS.md 2026-10-21: the `- {self.DEPLOY_DAY}:` bullet says the condition applies to "
                         "the candidates")
        self.assertNotRegex(self.norm(joined), self.NOTHING_DEPLOYED,
                            f"docs/DECISIONS.md 2026-10-21: the `- {self.DEPLOY_DAY}:` bullet says the deploy waits")

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
            ("three spaces against a tab (any whitespace run is one space)", "Golden   Eagles", "Golden\tEagles",
             P1, P1, CLUB, CLUB, True),
            ("a no-break space", "Golden Eagles", "golden eagles", P1, P1, CLUB, CLUB, True),
            ("ß against SS (casefold, not lower)", "Straße Club", "STRASSE CLUB", P1, P1, CLUB, CLUB, True),
            ("the deliberate long name twice under one partner (only another parent keeps twins apart)",
             "Golden Eagles - Partner One", "golden eagles - partner one", P1, P1, CLUB, CLUB, True),
            ("ParentId empty against null (both partner-less)", "Golden Eagles", "Golden Eagles", "", None, CLUB, CLUB, True),
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
        # three of one club and two of another: two groups, every twin in its group, no Id in both
        accounts = [account(1, "Shining Stars"), account(2, "Rising Moons"), account(3, "shining stars"),
                    account(4, "rising moons"), account(5, "Shining  Stars")]
        self.assertEqual(self.groups(accounts), [[aid(1), aid(3), aid(5)], [aid(2), aid(4)]],
                         "a group per name, each with every twin, no Id in two groups")

    def test_a_missing_or_empty_parent_or_record_type_is_one_value(self):
        """`ParentId` "" (a CSV export), null (the API) and a missing key are the same partner-less value; a
        missing or null `RecordTypeId` is one value too (never a KeyError), and differs from a Club's."""
        a = {"Id": aid(1), "Name": "Blue Herons", "ParentId": "", "RecordTypeId": CLUB}
        b = {"Id": aid(2), "Name": "blue herons", "ParentId": None, "RecordTypeId": CLUB}
        c = {"Id": aid(3), "Name": "BLUE HERONS", "RecordTypeId": CLUB}
        self.assertEqual(self.groups([a, b, c]), [[aid(1), aid(2), aid(3)]],
                         'ParentId "", null and a missing key are one partner-less value')
        d = {"Id": aid(4), "Name": "Blue Herons", "ParentId": None}
        e = {"Id": aid(5), "Name": "blue herons", "ParentId": None, "RecordTypeId": None}
        self.assertEqual(self.groups([d, e]), [[aid(4), aid(5)]],
                         "a missing RecordTypeId and a null one are one value (no KeyError)")
        self.assertEqual(self.groups([b, d]), [], "a Club and an account without a record type are not twins")
        self.assertEqual(self.groups([account(6, "Blue Herons", parent=P1), d]), [],
                         "a partnered account and a partner-less one are not twins")


if __name__ == "__main__":
    unittest.main(verbosity=1)
