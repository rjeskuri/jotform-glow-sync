#!/usr/bin/env python3
"""New clubs' Salesforce accounts (BACKLOG 27; docs/plans/2026-10-06-sf-new-club-accounts.md).

The attendance processor in Salesforce books a submission on the Account whose name equals
question 5 (any record type, trimmed, case ignored, first match wins) and, when there is none,
makes a name-only Club account with no partner. So every club on a form needs its account before
its first attendance: named exactly as question 5 sends it, record type Club, its partner's
account as parent.

The automatic sync (tools/auto_sync.py) uses this module, logged in as the GLOW Sync integration
user, in two places:
  Step.create(region, plan)  before a region's form apply: the account of each new club the apply
                             is about to put on the form - created (mode apply) or shown as
                             ATTENTION for a person to create (mode plan)
  Step.check(sf_names)       after all regions, read only: every active club on a form has exactly
                             one account, a Club under its partner's account carrying its club code
Everything else is reported, never written: v1 never updates, renames or deletes an account.

Standalone, read only, with Ryan's CLI login (the cross-check of the rollout; VPN off):
  python3 tools/sf_new_clubs.py check --vpn-off --roster data/roster_<stamp>.csv \\
      --summary <dir>/plan_<region>_<stamp>.json [...]

It prints club and partner names and record ids, never a girl's name; the full Account read stays
in memory.
"""
import argparse
import collections
import csv
import datetime
import json
import os
import re
import sys
import unicodedata

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
from glow.salesforce import Org, Refused, quoted                  # noqa: E402
from glow.text import key, name_key                               # noqa: E402
from sf_club_accounts import (ACCOUNT_ID, CLUB_RECORD_TYPE, ON_HOLD_ACCOUNTS,   # noqa: E402
                              PARTNER_RECORD_TYPE, odd)

PARTNERS = os.path.join(REPO, "glow", "sf_partners.csv")
PARTNER_COLS = ["partner", "sf_account_id", "sf_account_name"]
ACCOUNTS = "SELECT Id, Name, RecordTypeId, ParentId, Description, CreatedById FROM Account"
MAX_PER_REGION = 5          # creates in one region in one run, all or nothing (the forms' band too)
MIN_ACCOUNTS = 400          # fewer visible Accounts than this: View All is not effective - write nothing
CLUB_SLACK = 5              # visible Club accounts may lag the active clubs by this many, no more
MAX_ACCOUNTS = 4500         # the processor reads LIMIT 5000 Accounts: beyond that it misses names
CONFIRM_CREATES = True      # each create also raises "created, check by hand" (plan step 6; off later)
CODE_IN = re.compile(r"GLOW club code ([A-Z0-9]+);")
GIRL_ID = re.compile(r"([A-Z0-9]+)-[A-Z0-9]+-\d+")              # CLUBCODE-LASTCODE-NNN (appsscript/Ids.gs)
PROVEN = set(" -.()'/")     # characters seen arriving intact in question 5 (600 batches, 2026-10-06)
ERROR_WORD = re.compile(r"\b[A-Z][A-Z_]{3,}\b")

Club = collections.namedtuple("Club", "region partner club value code")


# ---- how the processor compares a submitted name with an Account's -------------------------------
def apex_trim(s):
    """Java String.trim(): every character up to U+0020 off both ends, nothing else."""
    start, end = 0, len(s)
    while start < end and s[start] <= " ":
        start += 1
    while end > start and s[end - 1] <= " ":
        end -= 1
    return s[start:end]


def _upper(c):
    u = c.upper()
    return u if len(u) == 1 else c       # Character.toUpperCase maps one character to one


SIMPLE_LOWER = {"\u0130": "i"}     # Java's one-to-one mapping where Python's full one gives two characters


def _lower(c):
    u = c.lower()
    return u if len(u) == 1 else SIMPLE_LOWER.get(c, c)


def sf_match(submitted, name):
    """`submitted.trim().equalsIgnoreCase(name)` as the Apex processor runs it."""
    a, b = apex_trim(submitted or ""), name or ""
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        ux, uy = _upper(x), _upper(y)
        if x != y and ux != uy and _lower(ux) != _lower(uy):
            return False
    return True


def name_problems(value):
    """Why a name may not be created unattended (empty = fine)."""
    problems = []
    if not value or len(value) > 255:
        problems.append("empty or longer than 255 characters")
    elif odd(value) or value != value.strip() or "  " in value:
        problems.append("an invisible character or a stray space")
    elif unicodedata.normalize("NFC", value) != value:
        problems.append("not in composed (NFC) form")
    else:
        strange = sorted({c for c in value if not (unicodedata.category(c).startswith(("L", "N")) or c in PROVEN)})
        if strange:
            problems.append("a character not yet seen arriving intact in question 5: "
                            + " ".join(f"U+{ord(c):04X}" for c in strange))
    return problems


def code_of(account):
    m = CODE_IN.search(account.get("Description") or "")
    return m.group(1) if m else None


# ---- inputs ---------------------------------------------------------------------------------------
def read_partners(path=PARTNERS):
    """{key(partner): (account id, account name)} from glow/sf_partners.csv."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != PARTNER_COLS:
            raise Refused(f"{os.path.relpath(path, REPO)}: the columns must be {','.join(PARTNER_COLS)}")
        out = {}
        for row in reader:
            k, pid = key(row["partner"]), (row["sf_account_id"] or "").strip()
            if not k or not ACCOUNT_ID.fullmatch(pid) or k in out:
                raise Refused(f"{os.path.relpath(path, REPO)}: a partner is blank, repeated or has no "
                              f"plain account id: {row['partner']!r}")
            out[k] = (pid, row["sf_account_name"])
    return out


def read_codes(roster_csv):
    """{(key(partner), key(club)): club code or None} for the active clubs of a Roster export. A club
    whose girls carry more than one code gets None: nothing is created for it."""
    codes = collections.defaultdict(set)
    with open(roster_csv, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if (row.get("status") or "").strip() != "active":
                continue
            m = GIRL_ID.fullmatch((row.get("girl_id") or "").strip())
            codes[(key(row.get("partner")), key(row.get("club")))].add(m.group(1) if m else None)
    return {pair: (next(iter(c)) if len(c) == 1 else None) for pair, c in codes.items()}


def plain(records):
    return [{k: v for k, v in r.items() if k != "attributes"} for r in records]


# ---- the decisions (pure) ------------------------------------------------------------------------
def guard_problems(accounts, partners, active_clubs):
    """Reasons to write nothing at all this run: the read is not the whole org, or the map is wrong."""
    problems = []
    if len(accounts) < MIN_ACCOUNTS:
        problems.append(f"only {len(accounts)} Accounts visible (at least {MIN_ACCOUNTS} expected) - "
                        "is View All on Account still in the GLOW Club Sync permission set?")
    clubs = sum(1 for a in accounts if a.get("RecordTypeId") == CLUB_RECORD_TYPE)
    if clubs < active_clubs - CLUB_SLACK:
        problems.append(f"only {clubs} Club accounts visible for {active_clubs} active clubs")
    by_id = {a["Id"]: a for a in accounts}
    for pid, name in sorted(set(partners.values())):
        a = by_id.get(pid)
        if a is None:
            problems.append(f"partner account {pid} ({name}) of glow/sf_partners.csv is not visible")
        elif a.get("RecordTypeId") != PARTNER_RECORD_TYPE or a.get("ParentId"):
            problems.append(f"partner account {pid} ({name}) is not a Household account without a parent")
    return problems


def partner_notes(accounts, partners):
    """Not a reason to stop: a partner account renamed in Salesforce since the map was written."""
    by_id = {a["Id"]: a for a in accounts}
    return [f"partner account {pid} is now named {by_id[pid]['Name']!r}, the map says {name!r} - "
            "update glow/sf_partners.csv" for pid, name in sorted(set(partners.values()))
            if pid in by_id and by_id[pid].get("Name") != name]


def describe(a):
    kind = "Club" if a.get("RecordTypeId") == CLUB_RECORD_TYPE else (
        "partner/household" if a.get("RecordTypeId") == PARTNER_RECORD_TYPE else "other")
    return f"{a['Id']} {a.get('Name')!r} ({kind}, parent {a.get('ParentId') or 'none'})"


def body_for(club, parent_id, today):
    return {"Name": club.value, "RecordTypeId": CLUB_RECORD_TYPE, "ParentId": parent_id,
            "Description": f"GLOW club code {club.code}; created by the automatic sync {today}"}


def decide_create(club, accounts, partners, today):
    """('create', body) | ('ok', None): the account is already right | ('attention', why, body or None)."""
    who = f"{club.club} ({club.partner}, {club.region})"
    parent = partners.get(key(club.partner))
    body = body_for(club, parent[0], today) if parent and club.code else None
    problems = name_problems(club.value)
    if problems:
        return ("attention", f"{who}: question 5 {club.value!r} has {problems[0]} - create the account "
                             "by hand after checking how the name arrives in Salesforce", body)
    if not parent:
        return ("attention", f"{who}: partner {club.partner!r} is not in glow/sf_partners.csv - add one "
                             "line with its Salesforce account (RUNBOOK, Club accounts in Salesforce)", None)
    if not club.code:
        return ("attention", f"{who}: no single club code in the Roster's girl ids - create by hand", None)
    same = [a for a in accounts if sf_match(club.value, a.get("Name"))]
    coded = [a for a in accounts if code_of(a) == club.code]
    if len(same) == 1 and same[0].get("RecordTypeId") == CLUB_RECORD_TYPE and same[0].get("ParentId") == parent[0] \
            and code_of(same[0]) in (None, club.code) and all(a["Id"] == same[0]["Id"] for a in coded):
        return ("ok", None)
    elsewhere = [a for a in coded if a not in same]
    if elsewhere:
        return ("attention", f"{who}: club code {club.code} is on {describe(elsewhere[0])} - a rename not made in "
                             "Salesforce: rename that account to the question-5 name first (RUNBOOK, Renaming "
                             "a club); nothing created", None)
    if same:
        return ("attention", f"{who}: question 5 {club.value!r} is already the name of "
                             + "; ".join(describe(a) for a in same)
                             + f" - the processor would book this club's attendance there; fix by hand "
                               f"(a partner-less Club: set ParentId = {parent[0]}); nothing created", body)
    near = [a for a in accounts if name_key(a.get("Name")) == name_key(club.value)]
    if near:
        return ("attention", f"{who}: an account with nearly the same name exists: "
                             + "; ".join(describe(a) for a in near)
                             + " - check it is not this club before creating by hand", body)
    return ("create", body)


def check_club(club, accounts, partners):
    """None when the club's account is right, else why not and the one-record fix."""
    who = f"{club.club} ({club.partner}, {club.region})"
    parent = partners.get(key(club.partner))
    if not parent:
        return f"{who}: partner {club.partner!r} is not in glow/sf_partners.csv - add one line"
    same = [a for a in accounts if sf_match(club.value, a.get("Name"))]
    coded = [a for a in accounts if club.code and code_of(a) == club.code]
    if not same:
        if coded:
            return (f"{who}: no account named {club.value!r}, but club code {club.code} is on {describe(coded[0])} "
                    "- rename that account to the question-5 name (RUNBOOK, Renaming a club)")
        return (f"{who}: no account named {club.value!r} - its first attendance will make a partner-less one; "
                f"create it by hand: Club, ParentId {parent[0]}")
    if len(same) > 1:
        return f"{who}: {len(same)} accounts are named {club.value!r}: " + "; ".join(describe(a) for a in same)
    a = same[0]
    if a.get("RecordTypeId") != CLUB_RECORD_TYPE:
        return f"{who}: question 5 {club.value!r} is the name of {describe(a)}, not a Club account"
    if a["Id"] in ON_HOLD_ACCOUNTS:
        return f"{who}: its account {describe(a)} is one of the pilot accounts on hold"
    if not a.get("ParentId"):
        return f"{who}: {describe(a)} has no partner - fix by hand: set ParentId = {parent[0]}"
    if a["ParentId"] != parent[0]:
        return (f"{who}: {describe(a)} is under another partner than {parent[1]} ({parent[0]}) - a partner "
                "move not made in Salesforce?")
    if code_of(a) not in (None, club.code):
        return f"{who}: {describe(a)} carries club code {code_of(a)}, the Roster says {club.code}"
    if any(c["Id"] != a["Id"] for c in coded):
        other = next(c for c in coded if c["Id"] != a["Id"])
        return f"{who}: club code {club.code} is also on {describe(other)}"
    return None


def strays(accounts, matched_ids):
    """Partner-less Club accounts no club on a form uses (not the pilots on hold)."""
    return [a for a in accounts if a.get("RecordTypeId") == CLUB_RECORD_TYPE and not a.get("ParentId")
            and a["Id"] not in ON_HOLD_ACCOUNTS and a["Id"] not in matched_ids]


def clubs_from(region, entries, codes, only_new=False):
    """The sync summary's sf_names entries -> Club tuples for the active clubs of the Roster. With
    only_new: the entries of rosters not yet on the form (qid None)."""
    out = []
    for e in entries or []:
        if only_new != (e.get("qid") is None) or not e.get("value"):
            continue
        pair = (key(e.get("partner")), key(e.get("club")))
        if pair not in codes:
            continue                                     # not an active Roster club (retired, renamed)
        out.append(Club(region, e.get("partner") or "", e.get("club") or "", e["value"], codes[pair]))
    return out


def error_words(answer):
    """Salesforce's error codes only - an error message can quote a record's values."""
    return sorted(set(ERROR_WORD.findall(json.dumps(answer)))) if answer else []


# ---- the step the automatic sync runs -----------------------------------------------------------
class Step:
    """One run's Salesforce work. Every problem ends in self.attention ((title, detail) pairs, the
    shape tools/auto_sync.py collects); nothing here raises past the caller."""

    def __init__(self, mode, org, roster_csv, log=print, partners_path=PARTNERS, today=None):
        assert mode in ("plan", "apply")
        self.mode, self.org, self.roster_csv, self.log = mode, org, roster_csv, log
        self.partners_path = partners_path
        self.today = today or datetime.date.today().isoformat()
        self.attention, self.created, self.stopped = [], [], set()
        self.accounts, self.partners, self.codes, self.broken = [], {}, {}, None

    def warn(self, title, detail=""):
        self.attention.append(("SF: " + title, detail))
        self.log("  ! SF: " + title)

    def prepare(self):
        """Log in, read every Account, check the read is whole. On any failure: self.broken, no writes."""
        try:
            self.partners = read_partners(self.partners_path)
            self.codes = read_codes(self.roster_csv)
            total = self.org.count("SELECT COUNT() FROM Account")
            self.accounts = plain(self.org.query(ACCOUNTS))
            if len(self.accounts) != total or len({a["Id"] for a in self.accounts}) != total:
                raise Refused(f"the Account read gave {len(self.accounts)} records for a count of {total}")
            problems = guard_problems(self.accounts, self.partners, len(self.codes))
            if problems:
                raise Refused("; ".join(problems))
        except (Refused, OSError, KeyError, ValueError) as err:
            self.broken = str(err) or err.__class__.__name__
            self.warn("not ready - no account is created or checked this run", self.broken)
            return False
        for note in partner_notes(self.accounts, self.partners):
            self.warn("partner map out of date", note)
        if len(self.accounts) > MAX_ACCOUNTS:
            self.warn(f"{len(self.accounts)} Accounts - the processor reads at most 5000, so past that it "
                      "misses names and makes twins", "Talk to whoever maintains the attendance processor.")
        self.log(f"  SF: {len(self.accounts)} Accounts read, "
                 f"{sum(1 for a in self.accounts if a.get('RecordTypeId') == CLUB_RECORD_TYPE)} Club")
        return True

    def create(self, region, plan):
        """Before the region's form apply: the accounts of its new clubs. Returns how many were made."""
        new = {key(c["club"]) for c in plan.get("creates", [])}
        clubs = [c for c in clubs_from(region, plan.get("sf_names"), self.codes, only_new=True) if key(c.club) in new]
        if not clubs:
            return 0
        if self.broken:
            self.warn(f"{region}: {len(clubs)} new club(s) put on the form without a Salesforce account",
                      "Salesforce was not ready this run (" + self.broken + "). Create by hand before their "
                      "first attendance:\n" + "\n".join(f"- {c.club} ({c.partner})" for c in clubs))
            return 0
        decisions = [(c, decide_create(c, self.accounts, self.partners, self.today)) for c in clubs]
        creates = [(c, d[1]) for c, d in decisions if d[0] == "create"]
        for c, d in decisions:
            if d[0] == "attention":
                self.warn(f"{region}: {c.club} - not created", d[1] + (
                    "\n\nBody for a hand create: " + json.dumps(d[2], ensure_ascii=False) if d[2] else ""))
        if len(creates) > MAX_PER_REGION:
            self.warn(f"{region}: {len(creates)} new accounts planned, more than {MAX_PER_REGION} - none created",
                      "\n".join(json.dumps(b, ensure_ascii=False) for _, b in creates))
            return 0
        if self.mode == "plan":
            for c, b in creates:
                self.warn(f"{region}: would create the account of {c.club} ({c.partner}) - create it by hand today",
                          json.dumps(b, ensure_ascii=False))
            return 0
        made = 0
        for c, b in creates:
            if region in self.stopped:
                break
            made += self.write(region, c, b)
        return made

    def write(self, region, club, body):
        """One create, proven before and read back after. Never retried."""
        label = f"{club.club} ({club.partner})"
        try:
            now = plain(self.org.query(f"SELECT Id, Name FROM Account WHERE Name = {quoted(club.value)}"))
            if any(sf_match(club.value, a.get("Name")) for a in now):
                self.warn(f"{region}: {label} - an account of that name appeared since the read; nothing created",
                          "; ".join(f"{a['Id']} {a.get('Name')!r}" for a in now))
                return 0
            status, answer = self.org.insert("Account", body)
        except Refused as err:
            self.stopped.add(region)
            self.warn(f"{region}: {label} - not created", str(err))
            return 0
        new_id = answer.get("id") if status == 201 and isinstance(answer, dict) else None
        unknown = status == 0 or status >= 500 or (status == 201 and not new_id)
        if not new_id and not unknown:
            self.stopped.add(region)
            self.warn(f"{region}: {label} - Salesforce refused the create (HTTP {status})",
                      " ".join(error_words(answer)) or "no error code given")
            return 0
        try:                                              # read back - or settle an unknown outcome
            found = plain(self.org.query("SELECT Id, Name, RecordTypeId, ParentId, Description FROM Account "
                                         f"WHERE Name = {quoted(club.value)}"))
            seen = None
        except Refused as err:
            found, seen = [], f"the read-back failed: {err}"
        ours = [a for a in found if sf_match(club.value, a.get("Name"))]
        right = (len(ours) == 1 and (new_id is None or ours[0]["Id"] == new_id)
                 and all(ours[0].get(k) == v for k, v in body.items()))
        if not right:
            self.stopped.add(region)
            self.warn(f"{region}: {label} - check by hand: the create's outcome is not as planned",
                      f"HTTP {status}, id {new_id or 'unknown'}; "
                      + (seen or "found: " + ("; ".join(describe(a) for a in ours) or "nothing (it may still "
                                              "appear: read again in ten minutes before creating by hand)")))
            return 0
        self.accounts.append(dict(ours[0], CreatedById=None))
        self.created.append((region, club, ours[0]["Id"]))
        self.log(f"  SF: created {ours[0]['Id']} {club.value!r} under {body['ParentId']}")
        if CONFIRM_CREATES:
            self.warn(f"{region}: created the account of {label} - check it by hand (first creates)",
                      f"{ours[0]['Id']}: Name, record type Club, parent {body['ParentId']}, Description.")
        return 1

    def check(self, sf_names_by_region, clash_names=()):
        """After all regions: every active club on a form has its one right account. Returns (ok, wrong)."""
        if self.broken:
            return 0, 0
        clash = {key(n) for n in clash_names}
        ok, wrong, matched = 0, [], set()
        for region, entries in sorted(sf_names_by_region.items()):
            for c in clubs_from(region, entries, self.codes):
                same = [a for a in self.accounts if sf_match(c.value, a.get("Name"))]
                matched.update(a["Id"] for a in same)
                if key(c.value) in clash:
                    continue                              # check_names reports it already
                why = check_club(c, self.accounts, self.partners)
                if why:
                    wrong.append(why)
                else:
                    ok += 1
        for a in strays(self.accounts, matched):
            wrong.append(f"{describe(a)}: a Club account without a partner that no club on a form uses "
                         "(the processor made it for a name nobody expected?)")
        if wrong:
            self.warn(f"{len(wrong)} club account(s) need a person", "\n".join("- " + w for w in wrong))
        self.log(f"  SF: check - {ok} ok, {len(wrong)} need a person")
        return ok, len(wrong)

    def close(self):
        try:
            self.org.revoke()
        except Exception:                                  # noqa: BLE001 - best effort, the token is dropped
            self.org.token = None


# ---- standalone: the read-only cross-check ------------------------------------------------------
def main(argv=None, org=None, partners_path=PARTNERS):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("check", help="read only: every active club on a form has its one right account")
    c.add_argument("--roster", required=True, help="a Roster export (tools/sheets_client.py export Roster ...)")
    c.add_argument("--summary", nargs="+", required=True,
                   help="the sync's --summary-json files, one per region (auto_sync's plan_<region>_<stamp>.json)")
    c.add_argument("--alias", default="glow", help="the Salesforce CLI login (Ryan's, read only)")
    c.add_argument("--vpn-off", action="store_true",
                   help="you checked: no VPN is on (Salesforce freezes a user whose API call comes through one)")
    a = p.parse_args(argv)
    if not a.vpn_off:
        sys.exit("say --vpn-off once you have checked that no VPN is on (Salesforce freezes the user otherwise)")
    names = {}
    for path in a.summary:
        with open(path, encoding="utf-8") as fh:
            summary = json.load(fh)
        region = summary.get("region") or os.path.basename(path)
        names[region] = [e for e in summary.get("sf_names") or [] if e.get("qid") is not None]
    step = Step("plan", org or Org(a.alias), a.roster, log=print, partners_path=partners_path)
    try:
        if step.prepare():
            step.check(names)
    finally:
        step.close()
    for title, detail in step.attention:
        print(f"\n{title}\n{detail}")
    sys.exit(1 if step.attention else 0)


if __name__ == "__main__":
    main()
