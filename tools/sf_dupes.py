#!/usr/bin/env python3
"""One Salesforce contact per girl: the duplicate Participant contacts within a club, found, proven
against the Roster and merged (docs/plans/2026-10-07-sf-duplicate-girls.md).

The attendance processor (Apex AttendanceBatchProcessor) matches a ticked name exactly, ignoring
case, among the club's contacts and creates a contact when nothing matches. A spelling the forms
altered (a double space) therefore made a second contact of a girl on every submission. This tool
finds them and merges them with Salesforce's own merge (Database.merge in anonymous Apex), which
moves every attendance row to the contact that stays.

  check    read-only, the monthly check: same-name groups within a club, stored names with odd
           whitespace, batches whose name list has odd whitespace, and (--roster) names in two clubs
           the Roster does not have in both. Exit 1 on any finding.
  plan     read-only: each group proven against the Roster, the contact that stays (the back-fill's,
           else the earliest), the others in merge calls of at most two, the renames
           -> merge_plan.json (record ids, dates and counts only)
  merge    dry run by default (re-read, drift check, the Apex written, nothing run); --rehearse runs
           the Apex and throws at its end, so Salesforce rolls everything back; --apply merges, one
           Apex run per club (or --per-run N merge calls), merge_rollback.json written first
  rename   the plan's renames (whitespace in a stored name); dry run by default
  cleanup  after the merges: a kept contact's extra affiliations to its club, and (--dup-sets) the
           plan's duplicate-rule sets left with at most one item; dry run by default

Every subcommand reads Salesforce through the CLI login (`sf org login web --alias glow`, Ryan's),
so every one refuses without --vpn-off (a connection through a VPN froze Ryan's user on 2026-09-30).
It prints counts, dates and record ids, never a name. The names stay in memory, in the Apex debug
logs saved under <dir>/logs/ and in merge_rollback.json: owner-only files under data/.
"""
import argparse
import collections
import csv
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import traceback
import unicodedata
from zoneinfo import ZoneInfo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
from glow import forms                                          # noqa: E402
from glow.cli import api_key                                   # noqa: E402
from glow.jotform import Client, JotformError                   # noqa: E402
from glow.salesforce import Org, Refused, quoted                # noqa: E402
from glow.sync import SF_NAME_SEP                               # noqa: E402
from glow.text import key as plain_key                          # noqa: E402
from sf_backfill import save_private, within                    # noqa: E402
from sf_new_clubs import sf_match                               # noqa: E402

BACKFILL_CONTACTS = os.path.join(REPO, "data", "backfill_2026-09", "created_contacts.csv")
ROLE = "Participant"
CHUNK = 2                     # Database.merge: one master and at most two duplicates per call
QUIET_MINUTES = 10            # no submission on the Africa or Asia form for this long before a write
NPSP_WINDOW = ((20, 30), (21, 30))      # UTC: NPSP's nightly job
QUIET_FORMS = ("Africa", "Asia")
JOTFORM_CLOCK = ZoneInfo("America/New_York")     # Jotform's created_at
MARKER = "SF_DUPES_REHEARSAL_END"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
IN_CHUNK = 150                # ids per SOQL IN list
APEX_TIMEOUT = 900            # seconds for one `sf apex run`
SUBMISSION_PAGE, SUBMISSION_PAGES = 100, 5
ID = re.compile(r"[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?")
CONTACT_ID = re.compile(r"003[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?")
ACCOUNT_ID = re.compile(r"001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?")
ALIAS = re.compile(r"[A-Za-z0-9_.-]+")
FIELD = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
HEX64 = re.compile(r"[0-9a-f]{64}")
BATCH_NAME = re.compile(r"[A-Z]+-\d+")
_IDS = r"(?:[A-Za-z0-9]{15,18}(?:,[A-Za-z0-9]{15,18})*)?"
# the only DIAG lines the Apex writes: ids and counts, nothing a name could hide in
DIAG_SHAPE = re.compile(r"DIAG\|(?:ok\|[A-Za-z0-9]{15,18}|merged\|[A-Za-z0-9]{15,18}\|" + _IDS + r"\|" + _IDS
                        + r"|limits\|queries=\d+/\d+\|dml=\d+/\d+\|cpu=\d+/\d+)")
FAIL_TOKEN = re.compile(r"DIAG\|fail\|[a-z ]+(?:\|[A-Za-z0-9]{15,18})?")
# Salesforce's error codes (DUPLICATES_DETECTED, UNABLE_TO_LOCK_ROW ...): capitals WITH an underscore,
# which no name has - a bare capitalized word of an error text can be a girl's name written in capitals
ERROR_CODE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
EXCEPTION_KIND = re.compile(r"(?:[A-Za-z0-9_]+\.)*[A-Za-z0-9_]*Exception(?=:)")
NAME_FIELDS = ("Name", "FirstName", "LastName")
RENAMEABLE = ("FirstName", "LastName")
CONTACT_FIELDS = ("Id, Name, FirstName, LastName, AccountId, Account.Name, CreatedDate, CreatedById, "
                  "Description, Contact_Role__c")
ROW_FIELDS = "Id, Contact__c, Account__c, Attendance_Date__c, Attendance_Batch__c"
ROW_KEEP = ("Contact__c", "Account__c", "Attendance_Date__c", "Attendance_Batch__c")
AFF_FIELDS = "Id, npe5__Contact__c, npe5__Organization__c, CreatedDate"
ITEM_FIELDS = "Id, RecordId, DuplicateRecordSetId"
# NPSP: an affiliation flagged Primary, and the contact's Primary Affiliation (an account) - NPSP blanks
# the contact's field when a Primary affiliation is deleted, even with another one to that account left
PRIMARY = "npe5__Primary__c"
CONTACT_PRIMARY = "npsp__Primary_Affiliation__c"


# ---- names: the comparison key and what counts as odd ---------------------------------------------
def cf_free(text):
    """Without Unicode format characters (category Cf: U+200B/U+200E/U+FEFF ...)."""
    return "".join(c for c in str(text or "") if unicodedata.category(c) != "Cf")


def norm(text):
    """Format characters dropped, every whitespace run (tab, NBSP ...) one space, ends trimmed.
    Case is kept: this is the spelling a repaired name gets."""
    return " ".join(cf_free(text).split())


def key(text):
    """The grouping key: norm(), case-folded."""
    return norm(text).casefold()


def odd(text):
    """A stored name part with whitespace or invisible characters that norm() would change."""
    text = text or ""
    return (text != " ".join(text.split()) or "\xa0" in text or "\t" in text
            or any(unicodedata.category(c) == "Cf" for c in text))


def odd_contact(contact):
    return any(odd(contact.get(f)) for f in NAME_FIELDS)


def odd_list(text):
    """A batch's name list with a double space, a tab, a non-plain space or an invisible character."""
    return "  " in text or any(c == "\t" or unicodedata.category(c) == "Cf"
                               or (unicodedata.category(c) == "Zs" and c != " ") for c in text)


def name_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def renamed(contact):
    """((fields to change, the new full name), None) or (None, why it cannot be renamed)."""
    fields = [f for f in RENAMEABLE if contact.get(f) and norm(contact[f]) != contact[f]]
    new_name = " ".join(p for p in (norm(contact.get("FirstName")), norm(contact.get("LastName"))) if p)
    if not fields:
        return None, "odd_name_but_parts_plain"
    if not norm(contact.get("LastName")):
        return None, "last_name_blank"
    if new_name != norm(contact.get("Name")):
        return None, "name_parts_do_not_add_up"
    return (fields, new_name), None


# ---- small helpers --------------------------------------------------------------------------------
def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def stamp(moment):
    return moment.astimezone(datetime.timezone.utc).strftime(STAMP)


def sf_time(text):
    """A Salesforce datetime (2026-10-01T12:00:00.000+0000) as an aware datetime."""
    try:
        return datetime.datetime.strptime(str(text), "%Y-%m-%dT%H:%M:%S.%f%z")
    except ValueError:
        raise Refused("Salesforce gave a created time this tool cannot read - nothing done") from None


def jotform_time(text):
    """Jotform's created_at (US Eastern, 'yyyy-mm-dd hh:mm:ss') in UTC."""
    try:
        moment = datetime.datetime.strptime(str(text), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise Refused("Jotform gave a submission time this tool cannot read - nothing written") from None
    return moment.replace(tzinfo=JOTFORM_CLOCK).astimezone(datetime.timezone.utc)


def iso_day(text):
    try:
        day = datetime.date.fromisoformat(text)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("a date like 2026-10-01") from None
    if str(day) != text:
        raise argparse.ArgumentTypeError("a date like 2026-10-01")
    return day


def positive(text):
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return value


def rel(path):
    path = os.path.abspath(path)
    return os.path.relpath(path, REPO) if path.startswith(REPO + os.sep) else path


def file_sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def plain(records):
    return [{k: v for k, v in r.items() if k != "attributes"} for r in records]


def in_list(ids):
    for x in ids:
        if not isinstance(x, str) or not ID.fullmatch(x):
            raise Refused("a record id that is not a plain Salesforce id - nothing done")
    return "(" + ", ".join(quoted(x) for x in ids) + ")"


def query_in(read, soql, ids):
    """soql with '{ids}' where an IN list goes, run over the ids in chunks."""
    ids, out = sorted(set(ids)), []
    for i in range(0, len(ids), IN_CHUNK):
        out += read(soql.replace("{ids}", in_list(ids[i:i + IN_CHUNK])))
    return plain(out)


def error_codes(text):
    """The Salesforce error codes in an error text or answer - never its words (they can quote a name)."""
    return sorted(set(ERROR_CODE.findall(str(text or ""))))


def field_names(describe):
    return {f.get("name") for f in (describe or {}).get("fields") or [] if isinstance(f, dict)}


def createable(describe, must=()):
    """The createable fields of a describe answer (plain names only), plus `must`."""
    names = {f.get("name") for f in (describe or {}).get("fields") or [] if f.get("createable")}
    names = {n for n in names if isinstance(n, str) and FIELD.fullmatch(n)} | set(must)
    names.discard("Id")
    return sorted(names)


def load_json(path, what):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise Refused(f"{what} is missing: {path}") from None
    except (ValueError, OSError):
        raise Refused(f"{what} cannot be read as JSON: {path}") from None


def save_json(path, data):
    save_private(path, json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True))


# ---- the Roster -------------------------------------------------------------------------------------
class Roster:
    """Every girl row of a Roster export, as the sync reads it (whitespace collapsed), kept per club:
    `active` lists the active girls' names (repeats kept: two girls of one name are two), `ever`
    holds the key of every name the club has had in any status."""
    NEEDED = {"partner", "club", "full_name", "status", "region"}

    def __init__(self, path):
        try:
            with open(path, newline="", encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh))
        except (OSError, UnicodeDecodeError, csv.Error):
            raise Refused(f"--roster: cannot read {path} as a UTF-8 CSV") from None
        if not rows or not set(rows[0]) >= self.NEEDED:
            raise Refused("--roster: not a Roster export (expected the columns "
                          + ", ".join(sorted(self.NEEDED)) + ")")
        self.sha256, self.clubs = file_sha(path), {}
        for row in rows:
            partner, club, name = (" ".join(str(row.get(c) or "").split()) for c in ("partner", "club", "full_name"))
            if not (partner and club and name):
                continue
            entry = self.clubs.setdefault((plain_key(partner), plain_key(club)),
                                          {"partner": partner, "club": club, "active": [], "ever": set()})
            entry["ever"].add(key(name))
            if plain_key(row.get("status")) == "active":
                entry["active"].append(name)

    def club_for(self, account_name, club_account_names):
        """(the active Roster club whose question-5 name is this account's name, None) or
        (None, why). Names are compared as the processor compares them (sf_new_clubs.sf_match);
        a club whose '<club> - <partner>' name is another Club account's name sends that one."""
        active = [c for c in self.clubs.values() if c["active"]]
        long = [c for c in active if sf_match(c["club"] + SF_NAME_SEP + c["partner"], account_name)]
        if len(long) == 1:
            return long[0], None
        if long:
            return None, "club_ambiguous"
        same = [c for c in active if sf_match(c["club"], account_name)
                and not any(sf_match(c["club"] + SF_NAME_SEP + c["partner"], n) for n in club_account_names)]
        if len(same) == 1:
            return same[0], None
        return None, "club_ambiguous" if same else "club_not_on_roster"


def girls_with(club, name_key):
    return [n for n in club["active"] if key(n) == name_key]


def read_backfill(path):
    """The contact ids the September back-fill created (created_contacts.csv: batch id, contact id)."""
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            lines = [line for line in csv.reader(fh) if any(cell.strip() for cell in line)]
    except FileNotFoundError:
        raise Refused(f"the back-fill's contact list is missing: {path} (--backfill-contacts)") from None
    except (OSError, UnicodeDecodeError, csv.Error):
        raise Refused(f"cannot read the back-fill's contact list {path}") from None
    out = set()
    for n, line in enumerate(lines):
        cells = [c.strip() for c in line]
        if len(cells) != 2 or not (ID.fullmatch(cells[0]) and CONTACT_ID.fullmatch(cells[1])):
            if n == 0 and not ID.fullmatch(cells[0]):
                continue                      # a header line
            raise Refused(f"the back-fill's contact list has a line that is not 'batch id,contact id': line {n + 1}")
        out.add(cells[1])
    return out


# ---- reading Salesforce -----------------------------------------------------------------------------
def flat_contact(record):
    return {"Id": record.get("Id"), "Name": record.get("Name"), "FirstName": record.get("FirstName"),
            "LastName": record.get("LastName"), "AccountId": record.get("AccountId"),
            "AccountName": (record.get("Account") or {}).get("Name"), "CreatedDate": record.get("CreatedDate"),
            "CreatedById": record.get("CreatedById"), "Description": record.get("Description"),
            "Contact_Role__c": record.get("Contact_Role__c")}


def club_record_type(org):
    found = {r["Id"] for r in org.query("SELECT Id FROM RecordType WHERE SobjectType = 'Account' "
                                        "AND (DeveloperName = 'Club' OR Name = 'Club')")}
    if len(found) != 1:
        raise Refused(f"Salesforce has {len(found)} Account record types named Club, not one - nothing done")
    return found.pop()


def read_participants(org):
    """(club record type, Club accounts [{Id, Name}], every Participant contact of a Club account)."""
    rt = club_record_type(org)
    accounts = plain(org.query(f"SELECT Id, Name FROM Account WHERE RecordTypeId = {quoted(rt)}"))
    where = f"Contact_Role__c = {quoted(ROLE)} AND Account.RecordTypeId = {quoted(rt)}"
    total = org.count(f"SELECT COUNT() FROM Contact WHERE {where}")
    contacts = [flat_contact(r) for r in org.query(f"SELECT {CONTACT_FIELDS} FROM Contact WHERE {where} ORDER BY Id")]
    if len(contacts) != total or len({c["Id"] for c in contacts}) != total:
        raise Refused(f"the contact read gave {len(contacts)} records for a count of {total} - nothing done")
    for c in contacts:
        if not CONTACT_ID.fullmatch(str(c["Id"])) or not ACCOUNT_ID.fullmatch(str(c["AccountId"])):
            raise Refused("a contact or account id that is not a plain Salesforce id - nothing done")
    return rt, accounts, contacts


def read_rows(org, contact_ids):
    """{contact id: sorted [[row id, date], ...]}."""
    out = collections.defaultdict(list)
    for r in query_in(org.query, f"SELECT {ROW_FIELDS} FROM Attendance__c WHERE Contact__c IN {{ids}}", contact_ids):
        out[r["Contact__c"]].append([r["Id"], r.get("Attendance_Date__c") or ""])
    return {c: sorted(rows) for c, rows in out.items()}


def read_days(org, account_id):
    """{date: attendance rows} of a club."""
    return {(r.get("Attendance_Date__c") or ""): r["n"] for r in plain(org.query(
        f"SELECT Attendance_Date__c, COUNT(Id) n FROM Attendance__c WHERE Account__c = {quoted(account_id)} "
        "GROUP BY Attendance_Date__c"))}


def group_by_key(contacts):
    """{(account id, key): [contacts sorted by id]} for every 2+ contacts with one key in ONE account."""
    by = collections.defaultdict(list)
    for c in contacts:
        k = key(c.get("Name"))
        if k:
            by[(c["AccountId"], k)].append(c)
    return {g: sorted(m, key=lambda c: c["Id"]) for g, m in by.items() if len(m) > 1}


# ---- plan (pure) ------------------------------------------------------------------------------------
def decide(contacts, rows_of, roster, club_names, backfill_ids):
    """(groups, renames, needs a person) from the participants, the rows of every group member
    ({contact id: [[row id, date]]}), the Roster, the Club account names and the back-fill's
    contact ids. Never a name in what it returns."""
    groups, renames, needs, grouped = [], [], [], set()
    by_account = collections.defaultdict(list)
    for c in contacts:
        by_account[c["AccountId"]].append(c)
    found = group_by_key(contacts)
    for (acc, k), members in sorted(found.items(), key=lambda kv: (kv[0][0], kv[1][0]["Id"])):
        ids = [c["Id"] for c in members]
        grouped.update(ids)
        reasons = []
        club, why = roster.club_for(members[0]["AccountName"], club_names)
        if why:
            reasons.append(why)
        if len({tuple(norm(c.get(f)) for f in NAME_FIELDS) for c in members}) != 1:
            reasons.append("names_differ")
        if len({(c["AccountId"], c["Contact_Role__c"], c["Description"], c["CreatedById"]) for c in members}) != 1:
            reasons.append("fields_differ")
        if club:
            girls = girls_with(club, k)
            if len(girls) != 1:
                reasons.append("not_one_roster_girl")
            elif any(norm(c["Name"]) != girls[0] for c in members):
                reasons.append("name_differs_from_roster")
        held = collections.Counter(d for c in members for d in {d for _, d in rows_of.get(c["Id"], [])})
        if any(n > 1 for n in held.values()):
            reasons.append("same_date")
        backfill = [c for c in members if c["Id"] in backfill_ids]
        if len(backfill) > 1:
            reasons.append("two_backfill_contacts")
        order = sorted(members, key=lambda c: (sf_time(c["CreatedDate"]), c["Id"]))
        kept = backfill[0] if len(backfill) == 1 else order[0]
        rename = None
        if not reasons and odd_contact(kept):
            done, why = renamed(kept)
            if why:
                reasons.append(why)
            else:
                rename = {"contact_id": kept["Id"], "account_id": acc, "fields": done[0],
                          "new_name_sha256": name_hash(done[1]), "in_group": True}
        if reasons:
            needs.append({"kind": "group", "account_id": acc, "contact_ids": ids, "reasons": reasons})
            continue
        merged = [c["Id"] for c in order if c is not kept]
        # 'identical': plain names, equal to the letter - the Apex compares them exactly. 'normalized':
        # a member is stored with odd whitespace, so the Apex compares norm()ed names (and still does
        # once the kept contact is renamed before its merge)
        plain_names = len({tuple(c.get(f) for f in NAME_FIELDS) for c in members}) == 1 \
            and not any(odd_contact(c) for c in members)
        groups.append({"account_id": acc, "kept": kept["Id"],
                       "why_kept": "the back-fill's contact" if backfill else "the earliest created",
                       "kind": "identical" if plain_names else "normalized",
                       "members": sorted(ids), "merged": merged,
                       "chunks": [merged[i:i + CHUNK] for i in range(0, len(merged), CHUNK)],
                       "contacts": {c["Id"]: {"created": c["CreatedDate"], "backfill": c["Id"] in backfill_ids,
                                              "odd": odd_contact(c), "rows": rows_of.get(c["Id"], [])}
                                    for c in members}})
        if rename:
            renames.append(rename)
    for c in contacts:
        if c["Id"] in grouped or not odd_contact(c):
            continue
        reasons = []
        club, why = roster.club_for(c["AccountName"], club_names)
        done, why_not = renamed(c)
        reasons += [r for r in (why, why_not) if r]
        if done and club:
            girls = girls_with(club, key(done[1]))
            if len(girls) != 1 or girls[0] != done[1]:
                reasons.append("not_one_roster_girl")
        if done and any(o["Id"] != c["Id"] and key(o.get("Name")) == key(done[1]) for o in by_account[c["AccountId"]]):
            reasons.append("another_contact_has_this_name")
        if reasons:
            needs.append({"kind": "rename", "account_id": c["AccountId"], "contact_ids": [c["Id"]], "reasons": reasons})
        else:
            renames.append({"contact_id": c["Id"], "account_id": c["AccountId"], "fields": done[0],
                            "new_name_sha256": name_hash(done[1]), "in_group": False})
    return groups, renames, needs


# ---- the plan file ----------------------------------------------------------------------------------
def load_plan(path):
    plan = load_json(path, "the plan")

    def bad(what):
        raise Refused(f"{path}: {what} - make the plan again (plan --roster ...)")
    if not isinstance(plan, dict) or plan.get("tool") != "sf_dupes" or plan.get("version") != 1:
        bad("not a plan of this tool")
    clubs, groups = plan.get("clubs"), plan.get("groups")
    if not isinstance(clubs, dict) or not isinstance(groups, list) or not isinstance(plan.get("renames"), list):
        bad("no clubs, groups or renames")
    seen = set()
    for g in groups:
        try:
            members, kept, merged = g["members"], g["kept"], g["merged"]
            ok = (g["account_id"] in clubs and ACCOUNT_ID.fullmatch(g["account_id"])
                  and all(isinstance(x, str) and CONTACT_ID.fullmatch(x) for x in members)
                  and kept in members and sorted(merged + [kept]) == sorted(members) and len(set(members)) == len(members)
                  and [x for chunk in g["chunks"] for x in chunk] == merged
                  and all(1 <= len(chunk) <= CHUNK for chunk in g["chunks"])
                  and set(g["contacts"]) == set(members) and g["kind"] in ("identical", "normalized")
                  and all(isinstance(r, list) and len(r) == 2 and ID.fullmatch(r[0]) and (DAY.fullmatch(r[1]) or r[1] == "")
                          for info in g["contacts"].values() for r in info["rows"])
                  and all(ID.fullmatch(a) for info in g["contacts"].values() for a in info.get("affiliations", []))
                  and all(ID.fullmatch(i) and ID.fullmatch(s) for info in g["contacts"].values()
                          for i, s in info.get("dup_items", [])))
        except (KeyError, TypeError, ValueError):
            ok = False
        if not ok or seen & set(members):
            bad("a group that does not add up")
        seen |= set(members)
    for r in plan["renames"]:
        if not (isinstance(r, dict) and CONTACT_ID.fullmatch(str(r.get("contact_id")))
                and ACCOUNT_ID.fullmatch(str(r.get("account_id"))) and isinstance(r.get("fields"), list)
                and r["fields"] and set(r["fields"]) <= set(RENAMEABLE) and HEX64.fullmatch(str(r.get("new_name_sha256")))):
            bad("a rename that does not add up")
    for acc, info in clubs.items():
        if not ACCOUNT_ID.fullmatch(acc) or not isinstance(info, dict) \
                or not all(isinstance(info.get(k), int) for k in ("participants_before", "participants_after")) \
                or not isinstance(info.get("rows_per_date"), dict):
            bad("a club entry that does not add up")
    plan["sha256"] = file_sha(path)
    return plan


def club_groups(plan, club):
    return [g for g in plan["groups"] if g["account_id"] == club]


# ---- the expected state and the drift check --------------------------------------------------------
def expected(plan, club, done):
    """What Salesforce should hold for the club's planned contacts once the merges of `done` (the
    merged-away contact ids recorded as merged) ran: ({alive contact: {(row id, date)}},
    {kept: [alive members]}, participants)."""
    alive, groups, gone = {}, {}, 0
    for g in club_groups(plan, club):
        own = {cid: {tuple(r) for r in info["rows"]} for cid, info in g["contacts"].items()}
        for cid in g["members"]:
            if cid in done:
                gone += 1
                continue
            alive[cid] = set(own[cid])
            if cid == g["kept"]:
                for m in g["merged"]:
                    if m in done:
                        alive[cid] |= own[m]
        groups[g["kept"]] = sorted(m for m in g["members"] if m not in done)
    return alive, groups, plan["clubs"][club]["participants_before"] - gone


def live_club(org, plan, club):
    """A read of what the drift check and the rehearsal compare (lists only: JSON-comparable)."""
    contacts = [flat_contact(r) for r in org.query(
        f"SELECT {CONTACT_FIELDS} FROM Contact WHERE AccountId = {quoted(club)} "
        f"AND Contact_Role__c = {quoted(ROLE)} ORDER BY Id")]
    planned = [m for g in club_groups(plan, club) for m in g["members"]]
    by_id = {r["Id"]: [r.get("AccountId"), r.get("Contact_Role__c")] for r in query_in(
        org.query, "SELECT Id, AccountId, Contact_Role__c FROM Contact WHERE Id IN {ids}", planned)}
    by_key = collections.defaultdict(list)
    for c in contacts:
        by_key[key(c.get("Name"))].append(c["Id"])
    names = {c["Id"]: key(c.get("Name")) for c in contacts}
    groups = {}
    for g in club_groups(plan, club):
        anchor = next((m for m in [g["kept"]] + g["merged"] if m in names), None)
        groups[g["kept"]] = sorted(by_key[names[anchor]]) if anchor else []
    return {"participants": sorted(c["Id"] for c in contacts), "planned": by_id,
            "rows": read_rows(org, planned), "days": read_days(org, club), "groups": groups}


def drift(plan, club, live, done):
    """What differs from the plan (ids and counts only); empty = as planned."""
    alive, groups, participants = expected(plan, club, done)
    out = []
    for cid in sorted(alive):
        if live["planned"].get(cid) != [club, ROLE]:
            out.append(f"contact {cid} is gone, on another account or not a participant")
    for g in club_groups(plan, club):
        for cid in g["merged"]:
            if cid in done and cid in live["planned"]:
                out.append(f"contact {cid} was merged by an earlier run but is there again")
        if live["groups"].get(g["kept"]) != groups[g["kept"]]:
            out.append(f"the group of {g['kept']} has other members now ({len(live['groups'].get(g['kept']) or [])} "
                       f"live, {len(groups[g['kept']])} planned)")
    if len(live["participants"]) != participants:
        out.append(f"{len(live['participants'])} participants, {participants} expected")
    for cid, rows in sorted(alive.items()):
        if {tuple(r) for r in live["rows"].get(cid, [])} != rows:
            out.append(f"the attendance rows of {cid} changed")
    if live["days"] != plan["clubs"][club]["rows_per_date"]:
        out.append("the club's attendance rows per date changed")
    return out


# ---- the Apex ---------------------------------------------------------------------------------------
APEX_HELPERS = [
    "Boolean same(String a, String b) { return a == null ? b == null : a.equals(b); }",
    r"String norm(String s) { return s == null ? '' : s.replaceAll('\\p{Cf}', '').replaceAll('[\\s\\p{Z}]+', ' ').trim(); }",
]


def apex_text(plan, club, calls, done, rehearse, part, parts, made_at):
    """One anonymous-Apex run: the club's planned merge calls [(kept, [ids])], with record ids only.
    Any failed check throws, and nothing catches it: Salesforce rolls the whole run back."""
    kinds = {g["kept"]: g["kind"] for g in club_groups(plan, club)}
    alive, _, participants = expected(plan, club, done)
    kept_of = {}
    for kept, chunk in calls:
        kept_of[kept] = kept
        kept_of.update({x: kept for x in chunk})
    for x in [club] + list(kept_of):
        if not ID.fullmatch(x):
            raise Refused("a record id that is not a plain Salesforce id - nothing written")
    rows = sum(len(alive.get(x, ())) for x in kept_of)
    merged = sum(len(chunk) for _, chunk in calls)
    normalized = sorted({k for k, _ in calls if kinds[k] == "normalized"})
    say = "ERROR"
    lines = [f"// tools/sf_dupes.py merge: club {club}, part {part} of {parts}"
             + (" - REHEARSAL: it ends by throwing, so Salesforce rolls every change back" if rehearse else ""),
             f"// record ids only; plan {plan['sha256'][:12]}; written {made_at}"]
    if rehearse:
        lines.append("class RehearsalEndException extends Exception {}")
    lines += APEX_HELPERS
    lines += [f"Id acc = '{club}';",
              "Map<Id, Id> keptOf = new Map<Id, Id>{",
              ",\n".join(f"    (Id) '{x}' => (Id) '{k}'" for x, k in sorted(kept_of.items())),
              "};",
              "Set<Id> normalized = new Set<Id>{" + ", ".join(f"(Id) '{k}'" for k in normalized) + "};",
              "Set<Id> allIds = new Set<Id>(keptOf.keySet());",
              "Set<Id> keptIds = new Set<Id>(keptOf.values());",
              "List<Contact> cs = [SELECT Id, AccountId, Contact_Role__c, Description, CreatedById, Name, FirstName, "
              "LastName FROM Contact WHERE Id IN :allIds];",
              f"System.assertEquals({len(kept_of)}, cs.size(), 'DIAG|fail|contacts found|' + acc);",
              "Map<Id, Contact> byId = new Map<Id, Contact>(cs);",
              "for (Contact c : cs) {",
              "    Contact k = byId.get(keptOf.get(c.Id));",
              "    System.assert(k != null && c.AccountId == acc && k.AccountId == acc, 'DIAG|fail|account|' + c.Id);",
              f"    System.assert(same(c.Contact_Role__c, '{ROLE}') && same(c.Contact_Role__c, k.Contact_Role__c), "
              "'DIAG|fail|role|' + c.Id);",
              "    System.assert(c.CreatedById == k.CreatedById, 'DIAG|fail|creator|' + c.Id);",
              "    System.assert(same(c.Description, k.Description), 'DIAG|fail|description|' + c.Id);",
              "    if (normalized.contains(k.Id)) {",
              "        System.assert(norm(c.Name).equals(norm(k.Name)) && norm(c.FirstName).equals(norm(k.FirstName)) "
              "&& norm(c.LastName).equals(norm(k.LastName)), 'DIAG|fail|name|' + c.Id);",
              "    } else {",
              "        System.assert(same(c.Name, k.Name) && same(c.FirstName, k.FirstName) && same(c.LastName, k.LastName), "
              "'DIAG|fail|name|' + c.Id);",
              "    }",
              "}",
              f"Integer participantsBefore = [SELECT COUNT() FROM Contact WHERE AccountId = :acc AND Contact_Role__c = '{ROLE}'];",
              f"System.assertEquals({participants}, participantsBefore, 'DIAG|fail|participants before|' + acc);"]
    for when in ("Before", "After"):
        if when == "After":
            for n, (kept, chunk) in enumerate(calls, 1):
                ids = ", ".join(f"(Id) '{x}'" for x in chunk)
                lines += [f"List<Database.MergeResult> merged{n} = Database.merge(new Contact(Id = '{kept}'), "
                          f"new List<Id>{{{ids}}}, true);",
                          f"for (Database.MergeResult r : merged{n}) {{",
                          f"    System.assert(r.isSuccess() && r.getId() == (Id) '{kept}', 'DIAG|fail|merge|{kept}');",
                          f"    System.debug(LoggingLevel.{say}, 'DIAG|merged|{kept}|' + String.join(r.getMergedRecordIds(), ',') "
                          "+ '|' + String.join(r.getUpdatedRelatedIds(), ','));",
                          "}"]
            lines += [f"Integer participantsAfter = [SELECT COUNT() FROM Contact WHERE AccountId = :acc AND "
                      f"Contact_Role__c = '{ROLE}'];",
                      f"System.assertEquals(participantsBefore - {merged}, participantsAfter, "
                      "'DIAG|fail|participants after|' + acc);",
                      "Integer leftOver = [SELECT COUNT() FROM Contact WHERE Id IN :allIds];",
                      "System.assertEquals(keptIds.size(), leftOver, 'DIAG|fail|merged contacts remain|' + acc);"]
        lines += [f"Map<String, Integer> days{when} = new Map<String, Integer>();",
                  "for (AggregateResult ar : [SELECT Attendance_Date__c attDate, COUNT(Id) n FROM Attendance__c "
                  "WHERE Account__c = :acc GROUP BY Attendance_Date__c]) {",
                  f"    days{when}.put(String.valueOf(ar.get('attDate')), (Integer) ar.get('n'));",
                  "}",
                  f"Map<String, Integer> group{when} = new Map<String, Integer>();",
                  f"Map<Id, Integer> kept{when} = new Map<Id, Integer>();",
                  f"Map<String, Integer> holders{when} = new Map<String, Integer>();",
                  f"Integer rows{when} = 0;",
                  "for (AggregateResult ar : [SELECT Contact__c contactId, Attendance_Date__c attDate, COUNT(Id) n "
                  "FROM Attendance__c WHERE Contact__c IN :allIds GROUP BY Contact__c, Attendance_Date__c]) {",
                  "    Id cid = (Id) ar.get('contactId');",
                  "    Id kid = keptOf.get(cid);"]
        if when == "After":
            lines.append("    System.assert(keptIds.contains(cid), 'DIAG|fail|a row left on a merged contact|' + cid);")
        lines += ["    String dayKey = String.valueOf(kid) + '|' + String.valueOf(ar.get('attDate'));",
                  "    Integer n = (Integer) ar.get('n');",
                  f"    group{when}.put(dayKey, (group{when}.containsKey(dayKey) ? group{when}.get(dayKey) : 0) + n);",
                  f"    kept{when}.put(kid, (kept{when}.containsKey(kid) ? kept{when}.get(kid) : 0) + n);",
                  f"    holders{when}.put(dayKey, (holders{when}.containsKey(dayKey) ? holders{when}.get(dayKey) : 0) + 1);",
                  f"    rows{when} += n;",
                  "}"]
        if when == "Before":
            lines += ["for (String dayKey : holdersBefore.keySet()) {",
                      "    System.assert(holdersBefore.get(dayKey) == 1, 'DIAG|fail|same date|' + acc);",
                      "}",
                      f"System.assertEquals({rows}, rowsBefore, 'DIAG|fail|rows before|' + acc);"]
    lines += ["System.assert(daysAfter.equals(daysBefore), 'DIAG|fail|rows per date|' + acc);",
              "System.assert(groupAfter.equals(groupBefore), 'DIAG|fail|group rows per date|' + acc);",
              "System.assert(keptAfter.equals(keptBefore), 'DIAG|fail|kept rows|' + acc);",
              "System.assertEquals(rowsBefore, rowsAfter, 'DIAG|fail|rows|' + acc);",
              f"System.debug(LoggingLevel.{say}, 'DIAG|limits|queries=' + Limits.getQueries() + '/' + Limits.getLimitQueries() "
              "+ '|dml=' + Limits.getDmlStatements() + '/' + Limits.getLimitDmlStatements() + '|cpu=' + Limits.getCpuTime() "
              "+ '/' + Limits.getLimitCpuTime());",
              f"System.debug(LoggingLevel.{say}, 'DIAG|ok|' + acc);"]
    if rehearse:
        lines.append(f"throw new RehearsalEndException('{MARKER}');")
    return "\n".join(lines) + "\n"


def diag_lines(logs):
    """The DIAG| messages of the USER_DEBUG entries of a debug log - nothing else of it (the log can
    hold names: variable assignments, other code's debug lines)."""
    out = []
    for line in str(logs or "").splitlines():
        parts = line.split("|", 4)
        message = parts[4].replace("&#124;", "|") if len(parts) == 5 else ""   # the log writes a message's | as &#124;
        if parts[1:2] == ["USER_DEBUG"] and message.startswith("DIAG|"):
            ours = DIAG_SHAPE.fullmatch(message) and all(any(ch.isdigit() for ch in token)     # ids, counts
                                                         for token in re.split(r"[|,]", message)[2:] if token)
            out.append(message if ours else "DIAG|(a line not shown: not one this tool writes)")
    return out


def is_marker(message):
    """The rehearsal's own end, as the CLI reports an uncaught exception."""
    text = str(message or "").strip()
    return text == MARKER or bool(re.fullmatch(r"(?:[A-Za-z0-9_]+\.)*RehearsalEndException: " + MARKER, text))


def apex_result(answer):
    """The run's outcome in an `sf apex run --json` answer: under "result" when the Apex finished,
    under "data" when it threw or did not compile (the CLI then answers as an error, e.g.
    executeRuntimeFailure - seen 2026-10-07). None when neither holds one."""
    for key in ("result", "data"):
        part = answer.get(key) if isinstance(answer, dict) else None
        if isinstance(part, dict) and "compiled" in part:
            return part
    return None


def judge(answer, club, rehearse):
    """(good, what to say) for one `sf apex run --json` answer. Never quotes Salesforce's text: only
    the exception's class, this tool's own DIAG|fail token, counts and error codes."""
    result = apex_result(answer)
    if result is None:
        return False, "the CLI gave no result (see the log file)"
    if not result.get("compiled"):
        return False, (f"the Apex did not compile (line {result.get('line')}, column {result.get('column')}) - "
                       "see the log file")
    ok = f"DIAG|ok|{club}" in diag_lines(result.get("logs"))
    message = str(result.get("exceptionMessage") or "")
    if rehearse and result.get("success") is False and is_marker(message) and ok:
        return True, "rehearsal ok: every check passed, then the run threw its own end and Salesforce rolled it back"
    if not rehearse and result.get("success") is True and ok:
        return True, "applied: every check passed"
    kind = EXCEPTION_KIND.match(message)
    said = [kind.group(0) if kind else ("no exception" if not message else "an exception")]
    said += FAIL_TOKEN.findall(message)
    numbers = re.search(r"Expected: (\d+), Actual: (\d+)", message)
    if numbers:
        said.append(f"expected {numbers.group(1)}, actual {numbers.group(2)}")
    said += error_codes(message)
    if result.get("success") is True and not ok:
        said.append("success without the DIAG|ok line")
    return False, "; ".join(said)


def run_apex(org, path, out_path):
    """(the CLI's answer as JSON or None, its raw output). The token never leaves the CLI. The answer
    goes to `out_path` (owner only), not to a pipe: through a pipe the CLI cut its answer at 65,536
    bytes when it exited (an 11-merge log, 2026-10-07)."""
    argv = ["sf", "apex", "run", "--file", path, "--target-org", org.alias, "--json"]
    fd = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            out = org.run(argv, stdout=fh, stderr=subprocess.PIPE, text=True, timeout=APEX_TIMEOUT)
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except OSError:
        raise Refused("the Salesforce CLI (sf) could not be started - nothing ran") from None
    text = getattr(out, "stdout", None)
    if not isinstance(text, str):                     # the real CLI wrote the file; a test's fake answers here
        with open(out_path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    try:
        return json.loads(text or ""), text
    except ValueError:
        return None, text or ""


# ---- the merge run ----------------------------------------------------------------------------------
class Rollback:
    """merge_rollback.json: what a rollback needs, written before each write (owner only)."""

    def __init__(self, folder):
        self.path = os.path.join(folder, "merge_rollback.json")
        self.data = load_json(self.path, "merge_rollback.json") if os.path.exists(self.path) else {
            "tool": "sf_dupes", "contacts": {}, "merges": [], "renames": {}, "deleted": []}
        if not isinstance(self.data, dict) or self.data.get("tool") != "sf_dupes":
            raise Refused(f"{self.path} is not this tool's rollback file - move it aside, never delete it")

    def save(self):
        save_json(self.path, self.data)

    def done(self):
        return {x for m in self.data["merges"] if m.get("status") == "done" for x in m["merged"]}


def parts_of(plan, club, per_run, done):
    calls = []
    for g in club_groups(plan, club):
        for chunk in g["chunks"]:
            if set(chunk) <= done:
                continue
            if set(chunk) & done:
                raise Refused(f"merge call of {g['kept']} is recorded as partly done - look at it by hand")
            calls.append((g["kept"], chunk))
    size = per_run or len(calls) or 1
    return [calls[i:i + size] for i in range(0, len(calls), size)]


def settle(org, rb):
    """Merges the rollback file has as running (the answer was lost): did they commit?"""
    for m in rb.data["merges"]:
        if m.get("status") not in ("running", "unknown"):
            continue
        kept_of = {x: kept for kept, chunk in m["calls"] for x in chunk}
        found = {r["Id"]: r for r in query_in(org.query_all, "SELECT Id, IsDeleted, MasterRecordId FROM Contact "
                                              "WHERE Id IN {ids}", m["merged"])}
        missing = [x for x in m["merged"] if x not in found]
        if missing:                           # out of the Recycle Bin (15 days, or emptied): it says nothing
            raise Refused(f"club {m['club']}, part {m['part']}: contact(s) {', '.join(missing)} are not in Salesforce "
                          "even among the deleted ones - this tool cannot tell whether that run merged; look at it by "
                          "hand (merge_rollback.json), nothing more is run")
        odd_ones = [x for x in m["merged"] if found[x].get("IsDeleted") and found[x].get("MasterRecordId") != kept_of[x]]
        if odd_ones:
            raise Refused(f"club {m['club']}, part {m['part']}: contact(s) {', '.join(odd_ones)} are deleted but not "
                          "merged into their kept contact - look at it by hand, nothing more is run")
        merged = [x for x in m["merged"] if found[x].get("IsDeleted")]
        if len(merged) == len(m["merged"]):
            m.update(status="done", note="settled: the merge had committed")
        elif not merged:
            m.update(status="not_applied", note="settled: nothing had been merged")
        else:
            raise Refused(f"club {m['club']}, part {m['part']}: the merge is only partly in Salesforce - look at it by hand")
        rb.save()
        print(f"  settled an earlier run (club {m['club']}, part {m['part']}): {m['status']}")


def save_for_rollback(org, rb, plan, clubs_calls, at):
    """Every createable field of each contact about to be merged away, its rows, affiliations and
    duplicate-rule items, written to merge_rollback.json before the first write."""
    why = {x: (g["kept"], g["why_kept"], g["account_id"]) for g in plan["groups"] for x in g["merged"]}
    ids = sorted({x for calls in clubs_calls for part in calls for _, chunk in part for x in chunk})
    contact_fields = createable(org.describe("Contact"))
    row_fields = createable(org.describe("Attendance__c"), ROW_KEEP)
    aff_fields = createable(org.describe("npe5__Affiliation__c"), ("npe5__Contact__c", "npe5__Organization__c"))
    contacts = {r["Id"]: r for r in query_in(org.query, "SELECT Id, " + ", ".join(contact_fields)
                                             + " FROM Contact WHERE Id IN {ids}", ids)}
    if set(contacts) != set(ids):
        raise Refused("not every contact to be merged could be read for the rollback file - nothing merged")
    rows = query_in(org.query, "SELECT Id, " + ", ".join(row_fields) + " FROM Attendance__c WHERE Contact__c IN {ids}", ids)
    affs = query_in(org.query, "SELECT Id, " + ", ".join(aff_fields)
                    + " FROM npe5__Affiliation__c WHERE npe5__Contact__c IN {ids}", ids)
    items = query_in(org.query, f"SELECT {ITEM_FIELDS} FROM DuplicateRecordItem WHERE RecordId IN {{ids}}", ids)
    for cid in ids:
        rb.data["contacts"][cid] = {
            "account_id": why[cid][2], "kept": why[cid][0], "why_kept": why[cid][1], "saved_at_utc": at,
            "plan_sha256": plan["sha256"], "fields": {k: v for k, v in contacts[cid].items() if k != "Id"},
            "rows": [r for r in rows if r.get("Contact__c") == cid],
            "affiliations": [a for a in affs if a.get("npe5__Contact__c") == cid],
            "dup_items": [i for i in items if i.get("RecordId") == cid]}
    rb.save()
    print(f"rollback file: {len(ids)} contacts with {len(rows)} rows, {len(affs)} affiliations and "
          f"{len(items)} duplicate-rule items saved before the first Apex run -> {rel(rb.path)}")


def read_back(org, plan, club, calls, snapshot, done):
    """After an applied run: what is not as it should be (empty = all right)."""
    out = []
    alive, _, _ = expected(plan, club, done)
    merged = [x for _, chunk in calls for x in chunk]
    kept_of = {x: k for k, chunk in calls for x in chunk}
    now = live_club(org, plan, club)
    if len(now["participants"]) != len(snapshot["participants"]) - len(merged):
        out.append(f"{len(now['participants'])} participants, {len(snapshot['participants']) - len(merged)} expected")
    if now["days"] != plan["clubs"][club]["rows_per_date"]:
        out.append("the club's attendance rows per date changed")
    moved = {rid: kept_of[x] for x in merged for rid, _ in alive.get(x, ())}
    found = {r["Id"]: r.get("Contact__c") for r in query_in(
        org.query, "SELECT Id, Contact__c FROM Attendance__c WHERE Id IN {ids}", list(moved))} if moved else {}
    for rid, kept in sorted(moved.items()):
        if found.get(rid) != kept:
            out.append(f"row {rid} is not on {kept}")
    gone = {r["Id"]: r for r in query_in(org.query_all, "SELECT Id, IsDeleted, MasterRecordId FROM Contact "
                                         "WHERE Id IN {ids}", merged)}
    for x in merged:
        if not gone.get(x, {}).get("IsDeleted") or gone[x].get("MasterRecordId") != kept_of[x]:
            out.append(f"contact {x} is not merged into {kept_of[x]}")
    return out, now


def quiet_window(ctx):
    """Refuse a write during NPSP's nightly job or while the attendance processor may be at work."""
    now = ctx.clock()
    if NPSP_WINDOW[0] <= (now.hour, now.minute) < NPSP_WINDOW[1]:
        raise Refused(f"it is {now:%H:%M} UTC: NPSP's nightly job runs between 20:30 and 21:30 UTC - run again "
                      "after 21:30 UTC; nothing written")
    jf = ctx.jotform()
    for region in QUIET_FORMS:
        latest = latest_submission(jf, region)
        if latest and now - latest < datetime.timedelta(minutes=QUIET_MINUTES):
            minutes = max(0, int((now - latest).total_seconds() // 60))
            raise Refused(f"a submission reached the {region} form {minutes} minute(s) ago - the attendance processor "
                          f"may be working on it; run again once {QUIET_MINUTES} minutes pass without one; nothing written")


def latest_submission(jf, region):
    """The newest submission's time: the first of Jotform's default order (newest first, the order
    tools/backfill_resolve.py pages by; no `orderby`, whose direction is not proven) or the form's
    own last_submission, whichever is later."""
    fid = forms.REGIONALS[region]
    info = jf.get(f"/form/{fid}")
    page = jf.get(f"/form/{fid}/submissions", limit=1)
    if not isinstance(page, list) or not isinstance(info, dict):
        raise Refused(f"the {region} form's answer has a shape this tool does not know - nothing written")
    times = [jotform_time(s.get("created_at")) for s in page if isinstance(s, dict)]
    if info.get("last_submission"):
        times.append(jotform_time(info["last_submission"]))
    return max(times) if times else None


def submissions_since(jf, region, since):
    """The form's submissions created since `since`, read page by page in Jotform's default order,
    newest first. The order is checked, not assumed: a page that is not newest first refuses (the
    count would otherwise stop early and say 0). A submission arriving meanwhile repeats one on the
    next page: counted once, by id."""
    fid, seen, last = forms.REGIONALS[region], {}, None
    for page_no in range(SUBMISSION_PAGES):
        page = jf.get(f"/form/{fid}/submissions", limit=SUBMISSION_PAGE, offset=page_no * SUBMISSION_PAGE)
        if not isinstance(page, list) or not all(isinstance(s, dict) and s.get("id") for s in page):
            raise Refused(f"the {region} form's submissions have a shape this tool does not know")
        older = False
        for s in page:
            moment = jotform_time(s.get("created_at"))
            if last is not None and moment > last:
                raise Refused(f"the {region} form's submissions did not come newest first - compare them with the "
                              "batches by hand")
            last = moment
            if moment >= since:
                seen[str(s["id"])] = s.get("status")
            else:
                older = True
        if len(page) < SUBMISSION_PAGE or older:
            return sum(1 for status in seen.values() if status != "DELETED")
    raise Refused(f"more than {SUBMISSION_PAGE * SUBMISSION_PAGES} submissions on the {region} form since the run "
                  "started - compare them with the batches by hand")


def window_count(ctx, org, started):
    """Submissions on every regional form vs Attendance_Batch__c (every club) since the run began,
    minus a minute: both sides whole, so a batch of another region cannot hide a missing one."""
    since = started - datetime.timedelta(minutes=1)
    subs = sum(submissions_since(ctx.jotform(), region, since) for region in forms.REGIONALS)
    batches = org.count(f"SELECT COUNT() FROM Attendance_Batch__c WHERE CreatedDate >= {stamp(since)}")
    print(f"since {stamp(since)}: {subs} submission(s) on the regional forms, {batches} new batch(es) in Salesforce")
    if subs > batches:
        print("ATTENTION: more submissions than batches - a submission may not have reached Salesforce during the run; "
              "look at the newest submissions and batches (RUNBOOK, Duplicate girls in Salesforce)")
        return 2
    return 0


def cmd_merge(args, ctx):
    plan = load_plan(args.plan)
    org, rb = ctx.org, Rollback(ctx.folder)
    clubs = sorted({g["account_id"] for g in plan["groups"]})
    if args.club:
        if args.club not in clubs:
            raise Refused(f"--club {args.club}: the plan has no merge for that account")
        clubs = [args.club]
    mode = "rehearse" if args.rehearse else "apply" if args.apply else "dry run"
    live = args.apply or args.rehearse        # both run DML in Salesforce (a rehearsal's is rolled back)
    if live:
        settle(org, rb)
    done = rb.done()
    work = [(club, parts_of(plan, club, args.per_run, done)) for club in clubs]
    work = [(club, parts) for club, parts in work if parts and parts[0]]
    print(f"merge ({mode}): {len(work)} club(s), {sum(len(p) for _, ps in work for p in ps)} merge call(s) "
          f"in {sum(len(ps) for _, ps in work)} Apex run(s); plan {rel(args.plan)}")
    if not work:
        print("nothing left to merge for this plan")
        return 0
    apex_dir, log_dir = os.path.join(ctx.folder, "apex"), os.path.join(ctx.folder, "logs")
    for folder in (apex_dir, log_dir):
        os.makedirs(folder, mode=0o700, exist_ok=True)
        os.chmod(folder, 0o700)
    if live:
        # a rehearsal too: its merges lock the club's records and run NPSP's triggers until the final
        # throw, so it waits for the same quiet moment, and saves the same rollback data in case it ever
        # kept a change
        quiet_window(ctx)
        for club, _ in work:
            problems = drift(plan, club, live_club(org, plan, club), done)
            if problems:
                raise Refused(f"club {club} is no longer as planned: " + "; ".join(problems)
                              + " - nothing merged; make the plan again")
        save_for_rollback(org, rb, plan, [parts for _, parts in work], stamp(ctx.clock()))
    started, failure, ran = ctx.clock(), None, False
    try:
        for club, parts in work:
            for n, calls in enumerate(parts, 1):
                if ran:
                    quiet_window(ctx)                 # again before every further run
                snapshot = live_club(org, plan, club)
                problems = drift(plan, club, snapshot, done)
                if problems:
                    raise Refused(f"club {club} is no longer as planned: " + "; ".join(problems)
                                  + " - nothing more merged; make the plan again")
                path = os.path.join(apex_dir, f"{club}_{n}.apex")
                save_private(path, apex_text(plan, club, calls, done, args.rehearse, n, len(parts), stamp(ctx.clock())))
                merged = [x for _, chunk in calls for x in chunk]
                if not live:
                    print(f"would run {rel(path)}: club {club}, part {n} of {len(parts)}, {len(calls)} merge call(s), "
                          f"{len(merged)} contact(s) into {len({k for k, _ in calls})}")
                    for kept, chunk in calls:
                        print(f"  keep {kept} <- {' + '.join(chunk)}")
                    continue
                print(f"{mode}: club {club}, part {n} of {len(parts)}: {len(calls)} merge call(s), {len(merged)} contact(s)")
                if args.apply:
                    entry = {"club": club, "part": n, "calls": [[k, c] for k, c in calls], "merged": merged,
                             "started_at_utc": stamp(ctx.clock()), "plan_sha256": plan["sha256"], "status": "running"}
                    rb.data["merges"].append(entry)
                    rb.save()
                ran = True
                good, said, diag = run_and_judge(org, path, log_dir, club, n, args.rehearse, ctx)
                if args.rehearse:
                    if live_club(org, plan, club) != snapshot:
                        raise Refused(f"club {club}: Salesforce is not as before the rehearsal - LOOK AT IT NOW; nothing "
                                      "more is run")
                    if not good:
                        raise Refused(f"club {club}: the rehearsal failed ({said}); Salesforce is unchanged - nothing "
                                      "more is run")
                    print(f"  re-read: club {club} is exactly as before the rehearsal")
                    continue
                if good:
                    problems, _ = read_back(org, plan, club, calls, snapshot, done)
                    entry.update(status="CHECK" if problems else "done", finished_at_utc=stamp(ctx.clock()),
                                 results=[d for d in diag if d.startswith("DIAG|merged|")], problems=problems)
                    rb.save()
                    if problems:
                        raise Refused(f"club {club}: applied, but the read-back differs: " + "; ".join(problems)
                                      + " - STOPPED; look at it in Salesforce (rollback: merge_rollback.json)")
                    done |= set(merged)
                    print(f"  read back: club {club} has {len(merged)} participant(s) fewer, rows per date unchanged, "
                          "every moved row on its kept contact, the merged contacts deleted with their master set")
                    continue
                if good is None:                      # no readable answer: Salesforce may still be at work
                    entry.update(status="unknown", finished_at_utc=stamp(ctx.clock()))
                    rb.save()
                    raise Refused(f"club {club}: {said} - THE OUTCOME IS UNKNOWN. Wait ten minutes, then run merge "
                                  "--apply again: it settles this run first")
                gone = query_in(org.query_all, "SELECT Id, IsDeleted FROM Contact WHERE Id IN {ids} AND IsDeleted = true",
                                merged)
                entry.update(status="unknown" if gone else "not_applied", finished_at_utc=stamp(ctx.clock()))
                rb.save()
                if gone:
                    raise Refused(f"club {club}: the run did not report success, but {len(gone)} of its contact(s) are "
                                  "deleted - LOOK AT IT NOW; the next merge run settles it first")
                raise Refused(f"club {club}: the run failed ({said}); Salesforce rolled it back (none of its contacts "
                              "is deleted) - nothing more is run")
    except Refused as stop:
        failure = stop
    code = 0
    if ran:
        try:
            code = window_count(ctx, org, started)
        except (Refused, JotformError) as err:
            print(f"the count of submissions against batches could not be made ({err}) - compare them by hand")
            code = 2
    if failure:
        raise failure
    if not (args.apply or args.rehearse):
        print("dry run: nothing was run (--rehearse rolls back, --apply merges, with Ryan's go)")
    return code


def run_and_judge(org, path, log_dir, club, n, rehearse, ctx):
    """Run one Apex file; (good: True/False/None = unknown, what to say, the DIAG lines). Prints only
    DIAG lines; the CLI's whole answer goes to an owner-only log file (it can hold names)."""
    log = os.path.join(log_dir, f"{stamp(ctx.clock()).replace(':', '')}_{club}_{n}.json")
    answer, raw = run_apex(org, path, log)
    save_private(log, json.dumps(answer, indent=1, ensure_ascii=False) if answer is not None else raw)
    result = apex_result(answer)
    diag = diag_lines(result.get("logs") if result else "")
    for line in diag:
        print("  " + line)
    if answer is None:
        good, said = None, "the CLI gave no readable answer (" + ("a timeout" if raw == "timeout" else "see the log file") + ")"
    else:
        good, said = judge(answer, club, rehearse)
    print(f"  {said}; the full log (it can hold names): {rel(log)}")
    return good, said, diag


# ---- check ------------------------------------------------------------------------------------------
def cmd_check(args, ctx):
    org = ctx.org
    since = args.since or ctx.clock().date().replace(day=1)
    roster = Roster(args.roster) if args.roster else None
    _, accounts, contacts = read_participants(org)
    findings = 0
    groups = group_by_key(contacts)
    per = collections.defaultdict(list)
    for (acc, _), members in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[1][0]["Id"])):
        per[acc].append([c["Id"] for c in members])
    extras = sum(len(m) - 1 for m in groups.values())
    print(f"read: {len(contacts)} participant contacts on {len({c['AccountId'] for c in contacts})} of {len(accounts)} "
          f"Club accounts")
    print(f"(a) same name twice in one club: {len(groups)} group(s), {extras} extra contact(s) in {len(per)} club(s)")
    for acc, gs in sorted(per.items()):
        print(f"  {acc}: {len(gs)} group(s), {sum(len(g) - 1 for g in gs)} extra - " + "; ".join("+".join(g) for g in gs))
    findings += len(groups)
    odd_ones = [c for c in contacts if odd_contact(c)]
    print(f"(b) stored names with odd whitespace or invisible characters: {len(odd_ones)}")
    for c in odd_ones:
        print(f"  {c['AccountId']}: {c['Id']} ({', '.join(f for f in NAME_FIELDS if odd(c.get(f)))})")
    findings += len(odd_ones)
    batches = plain(org.query("SELECT Id, Name, Contact_IDs__c FROM Attendance_Batch__c WHERE CreatedDate >= "
                              f"{since}T00:00:00Z ORDER BY CreatedDate"))
    bad = [b for b in batches if odd_list(str(b.get("Contact_IDs__c") or ""))]
    print(f"(c) batches since {since} whose name list has odd whitespace: {len(bad)} of {len(batches)}"
          + (" - " + ", ".join(b["Name"] if BATCH_NAME.fullmatch(str(b.get("Name"))) else b["Id"] for b in bad) if bad else ""))
    findings += len(bad)
    if roster is None:
        print("(d) names in two or more clubs: not checked (needs --roster)")
    else:
        names = [a["Name"] for a in accounts]
        by_key = collections.defaultdict(lambda: collections.defaultdict(list))
        for c in contacts:
            if key(c.get("Name")):
                by_key[key(c["Name"])][c["AccountId"]].append(c)
        account_name = {a["Id"]: a["Name"] for a in accounts}
        found = []
        for k, places in by_key.items():
            if len(places) < 2:
                continue
            missing = []
            for acc in places:
                club, _ = roster.club_for(account_name.get(acc), names)
                if club is None or k not in club["ever"]:
                    missing.append(acc)
            if missing:
                found.append((places, missing))
        print(f"(d) names in two or more clubs that the Roster does not have in each: {len(found)} (reported, never merged)")
        for places, missing in sorted(found, key=lambda f: sorted(f[0])):
            print("  " + ", ".join(f"{'+'.join(c['Id'] for c in cs)} ({acc})" for acc, cs in sorted(places.items()))
                  + " - not on the Roster in " + ", ".join(sorted(missing)))
        findings += len(found)
    print(f"check: {findings} finding(s)" + (" - exit 1 (RUNBOOK, Duplicate girls in Salesforce)" if findings else " - clean"))
    return 1 if findings else 0


# ---- plan -------------------------------------------------------------------------------------------
def cmd_plan(args, ctx):
    org = ctx.org
    roster = Roster(args.roster)
    backfill = read_backfill(args.backfill_contacts)
    rt, accounts, contacts = read_participants(org)
    names = [a["Name"] for a in accounts]
    members = sorted({c["Id"] for g in group_by_key(contacts).values() for c in g})
    rows_of = read_rows(org, members)
    groups, renames, needs = decide(contacts, rows_of, roster, names, backfill)
    planned = [m for g in groups for m in g["members"]]
    affs = query_in(org.query, f"SELECT {AFF_FIELDS} FROM npe5__Affiliation__c WHERE npe5__Contact__c IN {{ids}}", planned)
    items = query_in(org.query, f"SELECT {ITEM_FIELDS} FROM DuplicateRecordItem WHERE RecordId IN {{ids}}", planned)
    for g in groups:
        for cid, info in g["contacts"].items():
            info["affiliations"] = sorted(a["Id"] for a in affs if a.get("npe5__Contact__c") == cid)
            info["dup_items"] = sorted([i["Id"], i["DuplicateRecordSetId"]] for i in items if i.get("RecordId") == cid)
    participants = collections.Counter(c["AccountId"] for c in contacts)
    clubs = {}
    for acc in sorted({g["account_id"] for g in groups}):
        mine = club_groups({"groups": groups}, acc)
        extras = sum(len(g["merged"]) for g in mine)
        clubs[acc] = {"participants_before": participants[acc], "participants_after": participants[acc] - extras,
                      "groups": len(mine), "extras": extras, "rows_per_date": read_days(org, acc)}
    totals = {"groups": len(groups), "extras": sum(len(g["merged"]) for g in groups),
              "same_date": sum(1 for n in needs if "same_date" in n["reasons"]), "renames": len(renames),
              "needs_a_person": len(needs)}
    plan = {"tool": "sf_dupes", "version": 1, "made_at_utc": stamp(ctx.clock()), "org": args.org,
            "roster_sha256": roster.sha256, "backfill_contacts_sha256": file_sha(args.backfill_contacts),
            "club_record_type": rt, "participants_read": len(contacts), "clubs": clubs, "groups": groups,
            "renames": renames, "needs_a_person": needs, "totals": totals}
    path = os.path.join(ctx.folder, "merge_plan.json")
    save_json(path, plan)
    print(f"read: {len(contacts)} participant contacts, {len(members)} in same-name groups")
    print(f"{'club':<20} {'participants':>14} {'groups':>7} {'extras':>7} {'rows':>6} {'dates':>6}")
    for acc, info in clubs.items():
        print(f"{acc:<20} {info['participants_before']:>6} -> {info['participants_after']:<5} {info['groups']:>7} "
              f"{info['extras']:>7} {sum(info['rows_per_date'].values()):>6} {len(info['rows_per_date']):>6}")
    for r in renames:
        print(f"rename {r['contact_id']} ({r['account_id']}): {', '.join(r['fields'])}"
              + (" - the kept contact of a group" if r["in_group"] else ""))
    for n in needs:
        print(f"needs a person: {n['kind']} in {n['account_id']}: {'+'.join(n['contact_ids'])} - {', '.join(n['reasons'])}")
    print(f"groups {totals['groups']}, extras {totals['extras']}, same-date {totals['same_date']}, "
          f"renames {totals['renames']}, needs-a-person {totals['needs_a_person']}")
    print(f"plan: {rel(path)} (record ids, dates and counts only)")
    return 1 if needs else 0


# ---- rename -----------------------------------------------------------------------------------------
def cmd_rename(args, ctx):
    plan = load_plan(args.plan)
    org = ctx.org
    if not plan["renames"]:
        print("rename: the plan has no renames")
        return 0
    if args.apply and not args.roster:
        raise Refused("rename --apply reads the result back against the Roster: add --roster <the Roster export>")
    roster = Roster(args.roster) if args.roster else None
    ids = [r["contact_id"] for r in plan["renames"]]
    live = {c["Id"]: c for c in (flat_contact(r) for r in query_in(
        org.query, f"SELECT {CONTACT_FIELDS} FROM Contact WHERE Id IN {{ids}}", ids))}
    accounts = sorted({r["account_id"] for r in plan["renames"]})
    others = [flat_contact(r) for r in query_in(org.query, f"SELECT {CONTACT_FIELDS} FROM Contact WHERE AccountId IN "
                                                "{ids} AND Contact_Role__c = 'Participant'", accounts)]
    group_of = {m: set(g["members"]) for g in plan["groups"] for m in g["members"]}
    todo, problems, already = [], [], []
    for r in plan["renames"]:
        cid, c = r["contact_id"], live.get(r["contact_id"])
        if c is None or c["AccountId"] != r["account_id"]:
            problems.append(f"{cid}: gone or on another account")
            continue
        if not odd_contact(c) and name_hash(c["Name"] or "") == r["new_name_sha256"]:
            already.append(cid)
            continue
        new, _ = renamed(c)
        if not new or name_hash(new[1]) != r["new_name_sha256"] or sorted(new[0]) != sorted(r["fields"]):
            problems.append(f"{cid}: the stored name changed since the plan")
            continue
        allowed = group_of.get(cid, {cid}) if r["in_group"] else {cid}
        if any(o["Id"] not in allowed and key(o.get("Name")) == key(new[1]) for o in others if o["AccountId"] == c["AccountId"]):
            problems.append(f"{cid}: another contact of the club has this name now")
            continue
        todo.append((r, c, new))
    for cid in already:
        print(f"  {cid}: already as planned - nothing to do")
    for problem in problems:
        print(f"  {problem}")
    if not args.apply:
        for r, _, _ in todo:
            print(f"would rename {r['contact_id']} ({r['account_id']}): {', '.join(r['fields'])}")
        print("dry run: nothing written (--apply writes, with Ryan's go)")
        return 1 if problems else 0
    if problems:
        raise Refused(f"{len(problems)} rename(s) are no longer as planned - nothing written; make the plan again")
    quiet_window(ctx)
    rb = Rollback(ctx.folder)
    names = [a["Name"] for a in plain(org.query(f"SELECT Id, Name FROM Account WHERE RecordTypeId = "
                                                f"{quoted(club_record_type(org))}"))]
    failed = 0
    for r, c, (fields, new_name) in todo:
        cid = r["contact_id"]
        rb.data["renames"][cid] = {"old": {f: c[f] for f in fields}, "saved_at_utc": stamp(ctx.clock()),
                                   "plan_sha256": plan["sha256"], "status": "saving"}
        rb.save()
        status, _ = org.update("Contact", cid, {f: norm(c[f]) for f in fields})
        back = [flat_contact(x) for x in org.query(f"SELECT {CONTACT_FIELDS} FROM Contact WHERE Id = {quoted(cid)}")]
        club, _ = roster.club_for(back[0]["AccountName"] if back else None, names)
        ok = (len(back) == 1 and all(back[0][f] == norm(c[f]) for f in fields) and back[0]["Name"] == new_name
              and club is not None and girls_with(club, key(new_name)) == [new_name])
        rb.data["renames"][cid].update(status="done" if ok else "CHECK", http=status, done_at_utc=stamp(ctx.clock()))
        rb.save()
        failed += not ok
        print(f"  {cid}: {'OK' if ok else 'FAIL'}" + ("" if ok else f" (HTTP {status}; look at it in Salesforce)"))
    print(f"rename: {len(todo) - failed} done, {failed} failed; old values in {rel(rb.path)}")
    return 1 if failed else 0


# ---- cleanup ----------------------------------------------------------------------------------------
def primary_of(org, contact):
    """The contact's NPSP Primary Affiliation: an account id, or None when blank."""
    found = org.query(f"SELECT Id, {CONTACT_PRIMARY} FROM Contact WHERE Id = {quoted(contact)}")
    value = found[0].get(CONTACT_PRIMARY) if len(found) == 1 else ""
    if value is not None and not (isinstance(value, str) and ID.fullmatch(value)):
        raise Refused(f"kept contact {contact}: its Primary Affiliation could not be read - nothing more deleted")
    return value


def cmd_cleanup(args, ctx):
    plan = load_plan(args.plan)
    org, rb = ctx.org, Rollback(ctx.folder)
    done = rb.done()
    merged_groups = [g for g in plan["groups"] if set(g["merged"]) <= done]
    waiting = len(plan["groups"]) - len(merged_groups)
    deletes = []                          # (sobject, id, note, items kept with a set, contact to watch)
    left = []                             # (affiliation id, kept contact): a further Primary one, never deleted
    kept_ids = [g["kept"] for g in merged_groups]
    has_primary = watch = False
    affs = []
    if kept_ids:
        has_primary = PRIMARY in field_names(org.describe("npe5__Affiliation__c"))
        watch = CONTACT_PRIMARY in field_names(org.describe("Contact"))
        affs = query_in(org.query, f"SELECT {AFF_FIELDS}{', ' + PRIMARY if has_primary else ''} FROM "
                        "npe5__Affiliation__c WHERE npe5__Contact__c IN {ids}", kept_ids)
    for g in merged_groups:
        known = {a for info in g["contacts"].values() for a in info.get("affiliations", [])}
        # the one kept: a Primary one where there is one (a merge moves the merged-away contact's
        # Primary affiliation over as it is), else the earliest
        mine = sorted((a for a in affs if a.get("npe5__Contact__c") == g["kept"]
                       and a.get("npe5__Organization__c") == g["account_id"]),
                      key=lambda a: (a.get(PRIMARY) is not True, sf_time(a["CreatedDate"]), a["Id"]))
        for a in mine[1:]:
            if a["Id"] not in known:
                raise Refused(f"kept contact {g['kept']}: affiliation {a['Id']} is not one the plan recorded - look at "
                              "it by hand; nothing deleted")
            if has_primary and a.get(PRIMARY) is not False:
                left.append((a["Id"], g["kept"]))       # NPSP would blank her Primary Affiliation
                continue
            deletes.append(("npe5__Affiliation__c", a["Id"], f"kept contact {g['kept']} keeps {mine[0]['Id']}", None,
                            g["kept"] if watch else None))
    if args.dup_sets:
        set_ids = sorted({s for g in plan["groups"] for info in g["contacts"].values() for _, s in info.get("dup_items", [])})
        existing = {r["Id"] for r in query_in(org.query, "SELECT Id FROM DuplicateRecordSet WHERE Id IN {ids}",
                                              set_ids)} if set_ids else set()
        items = query_in(org.query, f"SELECT {ITEM_FIELDS} FROM DuplicateRecordItem WHERE DuplicateRecordSetId IN "
                         "{ids}", sorted(existing)) if existing else []
        kept_all = {g["kept"] for g in plan["groups"]}
        for s in sorted(existing):
            mine = [i for i in items if i.get("DuplicateRecordSetId") == s]
            if len(mine) <= 1 and all(i.get("RecordId") in kept_all for i in mine):
                deletes.append(("DuplicateRecordSet", s, f"{len(mine)} item(s) left", mine, None))
            else:
                print(f"  duplicate-rule set {s}: {len(mine)} item(s) left - kept")
    print(f"cleanup: {len(merged_groups)} merged group(s), {waiting} not merged yet; {len(deletes)} record(s) to delete")
    for aid, kept in left:
        print(f"  leave npe5__Affiliation__c {aid} (kept contact {kept}: a further Primary affiliation - NPSP blanks "
              "the contact's Primary Affiliation when a Primary one is deleted; RUNBOOK, Duplicate girls in Salesforce)")
    for sobject, rid, note, _, _ in deletes:
        print(f"  {'would delete' if not args.apply else 'delete'} {sobject} {rid} ({note})")
    if not args.apply or not deletes:
        if not args.apply:
            print("dry run: nothing deleted (--apply deletes, with Ryan's go)")
        return 0
    quiet_window(ctx)
    fields = {s: createable(org.describe(s)) for s in sorted({d[0] for d in deletes})}
    for sobject, rid, note, items, contact in deletes:
        found = plain(org.query(f"SELECT Id{''.join(', ' + f for f in fields[sobject])} FROM {sobject} WHERE Id = {quoted(rid)}"))
        if not found:
            print(f"  {sobject} {rid}: already gone")
            continue
        entry = {"sobject": sobject, "id": rid, "record": found[0], "note": note, "saved_at_utc": stamp(ctx.clock()),
                 "plan_sha256": plan["sha256"], "status": "saved"}
        if items is not None:
            entry["items"] = items
        before = primary_of(org, contact) if contact else None
        if contact:
            entry["contact_primary_before"] = {"contact": contact, CONTACT_PRIMARY: before}
        rb.data["deleted"].append(entry)
        rb.save()
        status, answer = org.delete(sobject, rid)
        back = org.query(f"SELECT Id FROM {sobject} WHERE Id = {quoted(rid)}")
        after = primary_of(org, contact) if contact else None
        changed = bool(contact) and after != before
        entry.update(status="deleted" if status == 204 and not back and not changed else "CHECK", http=status,
                     deleted_at_utc=stamp(ctx.clock()))
        if changed:
            entry["contact_primary_after"] = after
        rb.save()
        if changed:
            raise Refused(f"kept contact {contact}: its Primary Affiliation changed when {sobject} {rid} was deleted "
                          f"(it was {before or 'blank'}, it is {after or 'blank'}) - STOPPED; set it back in Salesforce "
                          "(both values and the deleted record are in the rollback file)")
        if entry["status"] != "deleted":
            codes = error_codes(" ".join(str(e.get("errorCode")) for e in answer if isinstance(e, dict))
                                if isinstance(answer, list) else "")
            raise Refused(f"{sobject} {rid}: not deleted as planned (HTTP {status}{' ' + ' '.join(codes) if codes else ''}) "
                          "- STOPPED; the record is saved in the rollback file")
        print(f"  {sobject} {rid}: deleted, read back gone")
    print(f"cleanup: done; every deleted record is in {rel(rb.path)}")
    return 0


# ---- main -------------------------------------------------------------------------------------------
class Ctx:
    def __init__(self, args, org, jotform, clock):
        self.args, self._org, self._jotform, self.clock, self.folder = args, org, jotform, clock, None

    @property
    def org(self):
        if self._org is None:
            self._org = Org(self.args.org)
        return self._org

    def jotform(self):
        if self._jotform is None:
            self._jotform = Client(api_key(": a write first checks that no submission reached the Africa or "
                                           "Asia form in the last 10 minutes", error=Refused))
        return self._jotform

    def use_folder(self, folder):
        folder = os.path.abspath(folder)
        if within(folder, REPO) and not within(folder, os.path.join(REPO, "data")):
            raise Refused("--dir: inside the checkout this tool's folder must be under data/ (its files can hold names)")
        os.makedirs(folder, mode=0o700, exist_ok=True)
        os.chmod(folder, 0o700)
        self.folder = folder


def main(argv=None, org=None, jotform=None, clock=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 allow_abbrev=False)
    ap.add_argument("--org", default="glow", help="the Salesforce CLI alias (default: glow)")
    ap.add_argument("--dir", help="the folder for the plan, Apex, logs and rollback file (default: "
                                  "data/sf_dupes_<UTC date>; for merge, rename and cleanup: the plan's folder)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    check = sub.add_parser("check", allow_abbrev=False, help="read-only: the monthly check")
    check.add_argument("--roster", help="a Roster export: also report names in two clubs the Roster does not have in both")
    check.add_argument("--since", type=iso_day, help="batches created from this day (default: the 1st of this month, UTC)")
    plan = sub.add_parser("plan", allow_abbrev=False, help="read-only: the merge plan")
    plan.add_argument("--roster", required=True, help="a Roster export (tools/sheets_client.py export Roster ...)")
    plan.add_argument("--backfill-contacts", default=BACKFILL_CONTACTS,
                      help="the back-fill's created_contacts.csv (default: data/backfill_2026-09/created_contacts.csv)")
    merge = sub.add_parser("merge", allow_abbrev=False, help="the merges: dry run, --rehearse or --apply")
    merge.add_argument("plan", help="merge_plan.json")
    merge.add_argument("--club", help="only this club account id")
    merge.add_argument("--per-run", type=positive, help="at most this many merge calls per Apex run")
    how = merge.add_mutually_exclusive_group()
    how.add_argument("--rehearse", action="store_true", help="run the Apex, then throw: Salesforce rolls it all back")
    how.add_argument("--apply", action="store_true", help="merge (needs Ryan's go)")
    rename = sub.add_parser("rename", allow_abbrev=False, help="the plan's renames: dry run or --apply")
    rename.add_argument("plan", help="merge_plan.json")
    rename.add_argument("--roster", help="a Roster export (needed with --apply: the read-back compares with it)")
    rename.add_argument("--apply", action="store_true", help="write (needs Ryan's go)")
    cleanup = sub.add_parser("cleanup", allow_abbrev=False, help="after the merges: extra affiliations, duplicate sets")
    cleanup.add_argument("plan", help="merge_plan.json")
    cleanup.add_argument("--dup-sets", action="store_true", help="also the plan's duplicate-rule sets left with one item")
    cleanup.add_argument("--apply", action="store_true", help="delete (needs Ryan's go)")
    for live in (check, plan, merge, rename, cleanup):
        live.add_argument("--vpn-off", action="store_true",
                          help="you checked: no VPN is on (Salesforce freezes a user whose API call comes through one)")
    args = ap.parse_args(argv)
    code = 0
    try:
        if not args.vpn_off:
            raise Refused("this command talks to Salesforce from this Mac: check that no VPN is on, then add --vpn-off "
                          "(a connection through a VPN froze Ryan's user on 2026-09-30)")
        if not ALIAS.fullmatch(args.org):
            raise Refused("--org: a Salesforce CLI alias is letters, digits, '.', '_' and '-' only")
        ctx = Ctx(args, org, jotform, clock or utc_now)
        if args.cmd != "check":
            ctx.use_folder(args.dir or (os.path.dirname(os.path.abspath(args.plan)) if args.cmd != "plan" else
                                        os.path.join(REPO, "data", "sf_dupes_" + ctx.clock().strftime("%Y-%m-%d"))))
        code = {"check": cmd_check, "plan": cmd_plan, "merge": cmd_merge, "rename": cmd_rename,
                "cleanup": cmd_cleanup}[args.cmd](args, ctx)
    except Refused as stop:
        sys.exit(str(stop))
    except JotformError as err:
        sys.exit(f"Jotform did not answer as expected ({str(err)[:120]}) - nothing written by this step")
    except (KeyError, IndexError, ValueError, TypeError, AttributeError, UnicodeError, OSError, csv.Error) as err:
        where = traceback.extract_tb(err.__traceback__)[-1]     # the place only: the text may quote a name
        sys.exit(f"stopped on an unexpected {type(err).__name__} at {os.path.basename(where.filename)}:{where.lineno} - "
                 "a file or an answer this tool reads has another shape. If a merge was under way, run merge again: it "
                 "settles the open run first")
    if code:
        sys.exit(code)


if __name__ == "__main__":
    main()
