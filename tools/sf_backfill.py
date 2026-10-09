#!/usr/bin/env python3
"""Back-fill: the Jotform attendance that never reached Salesforce, one Attendance_Batch__c per
club session (docs/plans/2026-09-30-september-backfill.md).

Salesforce turns each Attendance_Batch__c into Contacts and Attendance__c rows by itself (Apex
AttendanceBatchProcessor). That code is not bulk-safe, creates a stray Club account for any name
it does not know, stores a batch without names as Failed "No participants submitted", which
blocks nothing (before 2026-10-07: a Success with no rows that blocked the day), keeps only the
FIRST batch per club and date, and on a Success sets Girls_Present__c to the rows it created. So
this tool sends one record per request, in order, after proving each one against Salesforce, and
reads every one back (status, rows, girls, Girls_Present__c).

  snapshot  live, read-only: accounts, batches, attendance and participant COUNTS -> sf_state.json
  plan      offline: resolved.json (tools/backfill_resolve.py) + sf_state.json (+ decisions.csv)
            -> plan.json (the sessions to send, with the names), held.csv, a counts-only report
  send      the queue; dry run by default, --apply writes one batch per request and verifies it
  close     offline: record that a batch the ledger has open was removed by hand, or accepted
  status    what the ledger says was sent, and what a rollback would have to remove

Everything it reads and writes lives in the back-fill folder under data/ (never committed), owner
only: resolved.json, plan.json and sent_names.json hold girls' names; sf_state.json, held.csv,
ledger.csv and created_contacts.csv (record ids) do not. It prints counts, club names, dates, ids
and statuses - never a girl's name, and never the text of a Salesforce status message (only its
kind). It never SELECTs a Contact's name or any other personal field: counts and ids only.

Salesforce access is the Salesforce CLI's stored login (`sf org login web --alias glow`, made by
Ryan); the token is read into memory and goes to curl on stdin, never on a command line or to disk.
Salesforce freezes a user whose API connection comes through a VPN, so the two live commands
refuse without --vpn-off.
"""
import argparse
import csv
import datetime
import io
import json
import os
import re
import sys
import traceback
import unicodedata

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow.private_files import (STAMP, Ledger, keep_private, last_rows, load_json,   # noqa: E402
                                open_private, private_folder, rel, save_private, sha256, stamp)
from glow.salesforce import (ACCOUNT_ID, CLUB_RECORD_TYPE, ON_HOLD_ACCOUNTS, Org, Refused,   # noqa: E402
                             add_vpn_flag, apex_trim, error_codes, has_invisible, plain, positive, quoted,
                             require_vpn_off, sf_match)

DEFAULT_DIR = os.path.join(REPO, "data", "backfill_2026-09")
SCOPE_START = datetime.date(2026, 9, 1)      # attendance dated before the launch is held, not sent
MAX_NEW = 22                                 # new girls in one batch proven so far (2026-03-28)
MAX_AGE_HOURS = 3                            # how old the fetched submissions may be when sending
CREATOR = "Jotform back-fill"                # the processor never reads the batch's Creator__c
OK_STATUS, OK_MESSAGE = "Success", "Processed successfully."
CREATED_AT = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
SETTLE_AFTER_MINUTES = 10                    # a request Salesforce is still working on can commit this late
LEDGER_COLS = ["when_utc", "done_utc", "key", "region", "account_id", "account_name", "attendance_date",
               "submissions", "names", "new_expected", "new_exact", "batch_id", "batch_name", "status",
               "outcome", "rows", "participants_before", "participants_after", "contacts_created",
               "created_by", "note"]
HELD_COLS = ["key", "reasons", "region", "account_name", "attendance_date", "submissions", "names", "detail"]
# resolved.json row flags: the ones that hold a session, and the ones this tool knows and lets pass
# (it has its own rules for dates, repeated names and several rosters). Any other flag is refused.
HOLD_FLAGS = {"no_account_name", "date_missing", "name_has_comma", "name_unknown_to_roster", "module_unresolved"}
PASS_FLAGS = {"multi_club", "q5_differs", "q18_empty", "q18_differs", "typed_era", "bare_shared_name",
              "retired_club", "date_before_2026_09", "name_left_roster", "name_repeats", "module_translated"}
# what Ryan may wave through with `accept <reason>`; everything else needs its cause removed
RELEASABLE = {"several_rosters_ticked", "name_unknown_to_roster", "date_before_september",
              "date_after_submission", "club_has_earlier_contacts", "similar_names",
              "more_new_girls_than_proven"}
DONE, OPEN, UNSETTLED = {"ok", "accepted"}, {"CHECK"}, {"sending", "unknown"}


class Paths:
    def __init__(self, folder):
        folder = private_folder(folder, "the back-fill folder", "it holds names", repo=REPO, make=False)
        self.folder = folder
        self.resolved = os.path.join(folder, "resolved.json")
        self.state = os.path.join(folder, "sf_state.json")
        self.decisions = os.path.join(folder, "decisions.csv")
        self.plan = os.path.join(folder, "plan.json")
        self.held = os.path.join(folder, "held.csv")
        self.ledger = Ledger(os.path.join(folder, "ledger.csv"), LEDGER_COLS)
        self.sent_names = os.path.join(folder, "sent_names.json")
        self.contacts = os.path.join(folder, "created_contacts.csv")

# ---- snapshot ------------------------------------------------------------------------------------
STATE_QUERIES = {
    "accounts": "SELECT Id, Name, RecordTypeId, ParentId FROM Account ORDER BY Id",
    "batches": "SELECT Id, Name, Account__c, Attendance_Date__c, Processing_Status__c "
               "FROM Attendance_Batch__c ORDER BY CreatedDate",
    "attendance": "SELECT Account__c, Attendance_Date__c, COUNT(Id) n FROM Attendance__c "
                  "GROUP BY Account__c, Attendance_Date__c",
    "participants": "SELECT AccountId, COUNT(Id) n FROM Contact WHERE Contact_Role__c = 'Participant' "
                    "GROUP BY AccountId",
}


def cmd_snapshot(args, paths, org):
    state = {"read_at_utc": "", "source": f"sf CLI login '{org.alias}'"}
    for name, soql in STATE_QUERIES.items():
        state[name] = plain(org.query(soql))
    state["read_at_utc"] = stamp()
    save_private(paths.state, json.dumps(state, indent=1))
    print(f"snapshot: {len(state['accounts'])} accounts, {len(state['batches'])} batches, "
          f"{len(state['attendance'])} club days with attendance, {len(state['participants'])} clubs "
          f"with participants -> {rel(paths.state)}")


# ---- the inputs, checked once --------------------------------------------------------------------
def nfc(text):
    return unicodedata.normalize("NFC", text)


def fold(name):
    return " ".join(nfc(name).split()).casefold()


def iso(text):
    """A date from exactly yyyy-mm-dd, else None."""
    try:
        day = datetime.date.fromisoformat(text or "")
    except (ValueError, TypeError):
        return None
    return day if str(day) == text else None


def check_resolved(resolved):
    """Refuse a resolver file this tool cannot trust field by field (and tidy the names)."""
    def bad(what):
        raise Refused(f"resolved.json: {what} - the resolver and this tool are out of step; fix the resolver")
    if not isinstance(resolved, dict) or not isinstance(resolved.get("rows"), list):
        bad("no list of rows")
    try:
        fetched = datetime.datetime.strptime(resolved.get("fetched_at_utc") or "", STAMP)
    except (ValueError, TypeError):
        bad("fetched_at_utc is not a UTC time like 2026-09-30T12:00:00Z")
    if fetched > datetime.datetime.utcnow() + datetime.timedelta(minutes=5):
        bad("fetched_at_utc is in the future")
    if resolved.get("flag_vocabulary") != sorted(HOLD_FLAGS | PASS_FLAGS):
        bad("its flag_vocabulary is not the list of flags this tool knows")
    no_ticks = resolved.get("no_ticks") or {}
    if not isinstance(no_ticks, dict) or not all(isinstance(ids, list) for ids in no_ticks.values()):
        bad("no_ticks is not {region: [submission ids]}")
    for row in resolved["rows"]:
        if not isinstance(row, dict):
            bad("a row is not an object")
        sub = row.get("submission_id")
        for field in ("region", "submission_id", "created_at"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                bad(f"submission {sub}: '{field}' is missing")
        if not CREATED_AT.fullmatch(row["created_at"]) or iso(row["created_at"][:10]) is None:
            bad(f"submission {sub}: created_at is not 'yyyy-mm-dd hh:mm:ss'")
        names = row.get("names")
        if not isinstance(names, list) or not names or not all(isinstance(n, str) and n.strip() for n in names):
            bad(f"submission {sub} has a row without names, or with a blank one (an empty batch would block "
                "that club and date)")
        row["names"] = [nfc(n).strip() for n in names]
        if not isinstance(row.get("attendance_date") or "", str):
            bad(f"submission {sub}: attendance_date is not text")
        try:
            json.dumps(row, ensure_ascii=False).encode("utf-8")
        except (UnicodeError, TypeError, ValueError):
            bad(f"submission {sub} holds text that cannot be stored")
        flags = row.get("flags") or []
        if not isinstance(flags, list) or not all(isinstance(f, str) for f in flags):
            bad(f"submission {sub}: flags is not a list of text")
        unknown = sorted({f.split(":")[0] for f in flags} - HOLD_FLAGS - PASS_FLAGS)
        if unknown:
            bad(f"submission {sub} carries a flag this tool does not know ({', '.join(unknown)})")
        row["flags"] = flags
    return resolved


def check_state(state):
    if not isinstance(state, dict) or not all(isinstance(state.get(k), list) for k in STATE_QUERIES) \
            or not isinstance(state.get("read_at_utc"), str) or not state["read_at_utc"]:
        raise Refused("sf_state.json is not a complete snapshot - run snapshot again")
    return state


def read_decisions(path):
    """key -> {"skip", "use": [ids], "date", "accept": {reasons}}. decisions.csv is Ryan's:
    `key,decision`, the decision being one or more of  skip | use <id>[+<id>] | date yyyy-mm-dd |
    accept <reason>[+<reason>]  joined with ';'."""
    out = {}
    if not os.path.exists(path):
        return out
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            lines = [line for line in csv.reader(io.StringIO(fh.read())) if any(cell.strip() for cell in line)]
    except (UnicodeDecodeError, OSError, csv.Error):
        raise Refused("decisions.csv cannot be read as UTF-8 text") from None
    if not lines or [cell.strip() for cell in lines[0][:2]] != ["key", "decision"]:
        raise Refused("decisions.csv must start with the header line key,decision")
    for line in lines[1:]:
        key, text = line[0].strip(), (line[1].strip() if len(line) > 1 else "")
        if not key or key in out:
            raise Refused(f"decisions.csv: {'an empty key' if not key else 'two lines for ' + key} - one line per session")
        if any(cell.strip() for cell in line[2:]):
            raise Refused(f"decisions.csv: {key}: more than two columns - join several ids or reasons with '+', "
                          "several clauses with ';'")
        entry, words = {"skip": False, "use": [], "date": None, "accept": set()}, []
        for clause in [c.strip() for c in text.split(";") if c.strip()]:
            word, _, value = clause.partition(" ")
            value = value.strip()
            if word in words:
                raise Refused(f"decisions.csv: {key}: '{word}' twice on one line")
            words.append(word)
            if word == "skip" and not value:
                entry["skip"] = True
            elif word == "use" and value:
                entry["use"] = [v.strip() for v in value.split("+") if v.strip()]
            elif word == "date" and iso(value):
                entry["date"] = value
            elif word == "date":
                raise Refused(f"decisions.csv: '{clause}' for {key}: the date must be yyyy-mm-dd")
            elif word == "accept" and value:
                entry["accept"] = {v.strip() for v in value.split("+") if v.strip()}
                if entry["accept"] - RELEASABLE:
                    raise Refused(f"decisions.csv: {key}: '{', '.join(sorted(entry['accept'] - RELEASABLE))}' cannot "
                                  "be accepted - its cause has to be removed")
            else:
                raise Refused(f"decisions.csv: '{clause}' for {key} is not one of skip | use <submission id> | "
                              "date yyyy-mm-dd | accept <reason>")
        if not text or (entry["skip"] and (entry["use"] or entry["date"] or entry["accept"])):
            raise Refused(f"decisions.csv: {key}: {'no decision' if not text else 'skip cannot be combined'}")
        out[key] = entry
    return out


def stamp_of(row):
    return row["done_utc"] or row["when_utc"]


def closed_by_hand(ledger):
    return sum(1 for row in ledger if row["status"] in ("accepted", "removed"))


def read_sent_names(path):
    return load_json(path, "the list of names already sent") if os.path.exists(path) else {}


# ---- plan ----------------------------------------------------------------------------------------
def jaro_winkler(a, b):
    if a == b:
        return 1.0
    reach = max(len(a), len(b)) // 2 - 1
    hit_a, hit_b, matches = [False] * len(a), [False] * len(b), 0
    for i, ch in enumerate(a):
        for j in range(max(0, i - reach), min(len(b), i + reach + 1)):
            if not hit_b[j] and b[j] == ch:
                hit_a[i] = hit_b[j] = True
                matches += 1
                break
    if not matches:
        return 0.0
    seq_a = [ch for ch, hit in zip(a, hit_a) if hit]
    seq_b = [ch for ch, hit in zip(b, hit_b) if hit]
    swaps = sum(x != y for x, y in zip(seq_a, seq_b)) / 2
    jaro = (matches / len(a) + matches / len(b) + (matches - swaps) / matches) / 3
    prefix = 0
    for x, y in zip(a[:4], b[:4]):
        if x != y:
            break
        prefix += 1
    return jaro + prefix * 0.1 * (1 - jaro)


def alike(one, two):
    """Would the Contact duplicate rule (same last name, similar first name, same club) see these
    two different names as one girl? An approximation of Salesforce's first-name matching."""
    first_a, _, last_a = fold(one).partition(" ")
    first_b, _, last_b = fold(two).partition(" ")
    if not last_a or last_a != last_b or first_a == first_b:
        return False
    initial = min(len(first_a), len(first_b)) <= 2 and first_a[0] == first_b[0]
    return initial or jaro_winkler(first_a, first_b) >= 0.85


def bad_name(name):
    first, _, rest = name.partition(" ")
    if not name.strip():
        return "a blank name"
    if "," in name:
        return "a comma (Salesforce would split it into two girls)"
    if name != " ".join(name.split()) or has_invisible(name) or name != nfc(name):
        return "doubled or invisible characters"
    if len(first) > 40 or len(rest) > 80 or (not rest and len(first) > 80):
        return "a name part longer than the Contact fields"
    return None


def accounts_by_length(accounts):
    """{len(Name): [account, ...]}: sf_match accepts only an Account name as long as the trimmed
    question 5, so a name is compared with these alone."""
    out = {}
    for acc in accounts:
        out.setdefault(len(acc["Name"]), []).append(acc)
    return out


def resolve_account(name, by_length):
    """(account, None) or (None, why it cannot be used). The account is the one the processor
    books the name on: glow.salesforce.sf_match (question 5 trimmed as Java trims, case ignored
    one character to one - 'Straße' is not 'STRASSE'), not a case-fold."""
    if not isinstance(name, str) or not name.strip():
        return None, "no_account_name"
    found = [acc for acc in by_length.get(len(apex_trim(name)), []) if sf_match(name, acc["Name"])]
    if not found:
        return None, "account_not_found"     # the processor would CREATE a stray Club account
    if len(found) > 1:
        return None, "account_not_unique"
    acc = found[0]
    if acc["RecordTypeId"] != CLUB_RECORD_TYPE:
        return None, "account_not_a_club"
    if acc["Id"] in ON_HOLD_ACCOUNTS or not acc.get("ParentId"):
        return None, "account_without_partner"
    return acc, None


def as_number(value):
    text = str(value).strip() if value is not None else ""
    return int(text) if text.isascii() and text.isdigit() and len(text) <= 2 else None


def build_plan(resolved, state, decisions, ledger, sent_names, max_new=MAX_NEW, dup_rule_ok=False):
    """(queue, held, skipped, notes): the sessions to send in order, the held ones with EVERY
    reason that holds them, the skipped ones, and counts for the report."""
    by_length = accounts_by_length(state["accounts"])
    batches_on = {}
    for batch in state["batches"]:
        batches_on.setdefault((batch.get("Account__c"), batch.get("Attendance_Date__c")), []).append(batch)
    rows_on = {(a["Account__c"], a["Attendance_Date__c"]): a["n"] for a in state["attendance"]}
    participants = {p["AccountId"]: p["n"] for p in state["participants"]}
    batch_ids = {b["Id"] for b in state["batches"]}
    last = last_rows(ledger, "key")
    if ledger and state["read_at_utc"] < max(stamp_of(r) for r in ledger):
        raise Refused("the Salesforce snapshot is older than the last batch this tool sent - snapshot again")
    done = {key: row for key, row in last.items() if row["status"] in DONE}
    for key, row in done.items():
        if row["batch_id"] not in batch_ids:
            raise Refused(f"the ledger says {key} was sent as {row['batch_name']}, but Salesforce no longer has "
                          f"that batch - if it was removed on purpose: close {key} --removed")
    pending = {key: row for key, row in last.items() if row["status"] in OPEN | UNSETTLED}
    sent_under = {}                          # submission -> the keys it is, or may be, in Salesforce under
    for key, row in list(done.items()) + list(pending.items()):
        for sub in row["submissions"].split("+"):
            sent_under.setdefault(sub, set()).add(key)
    per_submission = {}
    for row in resolved["rows"]:
        per_submission.setdefault(row["submission_id"], []).append(row)

    held, skipped, notes = [], [], {"decisions_read": len(decisions), "set_aside": 0, "unused_accepts": 0}

    def hold(reasons, rows, key="", detail="", account_name="", date=""):
        held.append({"key": key, "reasons": "+".join(reasons), "region": rows[0]["region"],
                     "account_name": account_name or str(rows[0].get("sf_account_name") or rows[0].get("club") or ""),
                     "attendance_date": date or rows[0].get("attendance_date") or "",
                     "submissions": "+".join(sorted({r["submission_id"] for r in rows})),
                     "names": sum(len(r["names"]) for r in rows), "detail": detail})

    # 1. every row to its club; a `date` decision moves a whole reported day BEFORE the days are
    #    grouped, so a moved report joins (or collides with) what that day already has
    groups, origins, clubs_of = {}, set(), {}    # clubs_of: submission -> the clubs its rows lead to today
    for row in resolved["rows"]:
        acc, why = resolve_account(row.get("sf_account_name"), by_length)
        if why:
            hold([why], [row])
            continue
        clubs_of.setdefault(row["submission_id"], set()).add(acc["Id"])
        origin = f"{acc['Id']}|{row.get('attendance_date') or ''}"
        if not row.get("attendance_date"):   # no date says nothing about the day: one line per report,
            origin += "|" + row["submission_id"]     # never one line for all the club's undated reports
        origins.add(origin)
        moved = (decisions.get(origin) or {}).get("date")
        key = f"{acc['Id']}|{moved}" if moved else origin
        group = groups.setdefault(key, {"account": acc, "date": moved or row.get("attendance_date") or "",
                                        "rows": [], "origins": set()})
        group["rows"].append(row)
        group["origins"].add(origin)
        row["_origin"] = origin
    for key, group in groups.items():        # F1: the date of a moved report is changed on its own line
        came = sorted(group["origins"] - {key})
        if came and (decisions.get(key) or {}).get("date"):
            raise Refused(f"decisions.csv: {key}: reports were moved onto this day from {', '.join(came)}; a 'date' "
                          "on this line does not move them - change the date on their own line instead")
        if key not in group["origins"] and (decisions.get(key) or {}).get("use"):
            raise Refused(f"decisions.csv: {key}: every report of this day was moved onto it from {', '.join(came)}; "
                          "'use' on this line reaches none of them - put it on their own line instead")
    unknown = sorted(set(decisions) - origins - set(groups))
    if unknown:
        raise Refused("decisions.csv names sessions that do not exist: " + ", ".join(unknown)
                      + " - copy the key from held.csv or from the dry run")

    candidates = []
    for key, group in groups.items():
        acc, date = group["account"], group["date"]
        rows = sorted(group["rows"], key=lambda r: (r["created_at"], r["submission_id"]))
        mine = [decisions[k] for k in sorted(group["origins"] | {key}) if k in decisions]
        accept = set().union(*(d["accept"] for d in mine)) if mine else set()
        subs = {r["submission_id"] for r in rows}
        moved_from = sorted(group["origins"] - {key})

        def stop(reasons, detail="", rows=rows, acc=acc, key=key, date=date):
            hold(reasons, rows, key=key, detail=detail, account_name=acc["Name"], date=date)

        if key in pending:
            stop(["batch_outcome_open"], f"the ledger has this session as '{pending[key]['status']}': send (or close) "
                 "settles it first")
            continue
        if key in done:
            late = subs - set(done[key]["submissions"].split("+")) \
                - set((sent_names.get(key) or {}).get("set_aside", []))
            if late and not any(d["skip"] for d in mine):
                stop(["later_report_of_sent_session"], f"{len(late)} report(s) came after {done[key]['batch_name']} "
                     "was sent; only the first batch per club and day counts ('skip' to acknowledge)")
            else:
                skipped.append({"key": key, "reason": "sent_by_this_tool"})
            continue
        if any(d["skip"] for d in mine):
            skipped.append({"key": key, "reason": "skip_decided"})
            continue
        # sent under another key: only another club this same report still ticks girls of is no obstacle
        elsewhere = sorted({k for s in subs for k in sent_under.get(s, ()) if k != key
                            and (k.split("|")[0] == acc["Id"] or k.split("|")[0] not in clubs_of[s])})
        if elsewhere:
            stop(["submission_already_sent"], "already sent under " + ", ".join(elsewhere)
                 + " (was its date or its club changed since?)")
            continue
        there, n_rows = batches_on.get((acc["Id"], date), []), rows_on.get((acc["Id"], date), 0)
        if there or n_rows:
            ticked = len({fold(n) for r in rows for n in r["names"]})
            if n_rows and any(b["Processing_Status__c"] == OK_STATUS for b in there):
                if n_rows == ticked:
                    skipped.append({"key": key, "reason": "already_in_salesforce"})
                else:
                    stop(["salesforce_has_different_count"], f"Salesforce has {n_rows} attendance rows for this "
                         f"day, the reports tick {ticked} girls ('skip' to acknowledge)")
            else:
                stop(["salesforce_has_empty_or_failed_batch"],
                     f"{len(there)} batch(es), {n_rows} attendance rows: this tool never adds to a day Salesforce "
                     "has a batch or rows for; a Failed batch no longer blocks the processor itself")
            continue
        set_aside = []
        for origin in sorted(group["origins"]):
            use = (decisions.get(origin) or {}).get("use") or []
            own = {r["submission_id"] for r in rows if r["_origin"] == origin}
            if use and not set(use) <= own:
                raise Refused(f"decisions.csv: {origin}: 'use' names a submission that is not a report of that day")
            if use:
                set_aside += sorted(own - set(use))
        notes["set_aside"] += len(set_aside)
        rows = [r for r in rows if r["submission_id"] not in set_aside]
        reasons, details = [], []
        if moved_from:
            details.append("moved from " + ", ".join(k.split("|")[1] or "no date" for k in moved_from))
        modules = {(str(r.get("module")).strip(), str(r.get("module_week")).strip(), str(r.get("module_year")).strip())
                   for r in rows}
        if len(modules) > 1:
            reasons.append("same_day_different_module")
            details.append(f"{len(rows)} reports, {len(modules)} different module/week/year: use <submission id>")
        if any(len(per_submission[r["submission_id"]]) > 1 for r in rows):
            reasons.append("several_rosters_ticked")
        reasons += sorted({f.split(":")[0] for r in rows for f in r["flags"] if not
                           (f == "date_missing" and r["_origin"] != key)} & HOLD_FLAGS)
        day, created = iso(date), min(iso(r["created_at"][:10]) for r in rows)
        # F2: every report of the day, not just the latest, must have been sent in on or after it
        late = [r for r in rows if day and day > iso(r["created_at"][:10]) + datetime.timedelta(days=1)]
        if day is None:
            reasons.append("date_missing")
        elif day < SCOPE_START or late:
            early = day < SCOPE_START
            if early and moved_from or any(r["_origin"] != key for r in late):
                raise Refused(f"decisions.csv: {key}: the new date is " + (f"before {SCOPE_START}" if early else
                              "after a report it moves was submitted"))
            reasons.append("date_before_september" if early else "date_after_submission")
            swapped = datetime.date(day.year, day.day, day.month) if early and day.day <= 12 else None
            if swapped and SCOPE_START <= swapped <= created:
                details.append("day and month may be swapped")
        week, year = as_number(rows[0].get("module_week")), as_number(rows[0].get("module_year"))
        module = str(rows[0].get("module") or "").strip()
        if week is None or year is None or not module or len(module) > 255:
            reasons.append("module_not_usable")
        names, seen = [], set()
        for row in rows:
            for name in row["names"]:
                if fold(name) not in seen:
                    seen.add(fold(name))
                    names.append(name)
        wrong = next((bad_name(n) for n in names if bad_name(n)), None)
        if wrong:
            reasons.append("bad_name")
            details.append(wrong)
        candidates.append({"key": key, "region": rows[0]["region"], "account_id": acc["Id"],
                           "account_name": acc["Name"], "attendance_date": date,
                           "submissions": [r["submission_id"] for r in rows], "set_aside": set_aside,
                           "names": names, "module": module, "module_week": week, "module_year": year,
                           "reasons": list(dict.fromkeys(reasons)), "details": details, "accept": accept,
                           "rows": rows})
    for row in resolved["rows"]:
        row.pop("_origin", None)

    # 2. per club, in date order: is every participant this tool's own, how many girls each batch
    #    creates, and which batches must wait for an earlier one
    queue, by_account = [], {}
    for session in candidates:
        by_account.setdefault(session["account_id"], []).append(session)
    for account_id, mine in by_account.items():
        mine.sort(key=lambda s: s["attendance_date"])
        before = participants.get(account_id, 0)
        history = [row for row in ledger if row["account_id"] == account_id]
        ours = sorted((row for row in done.values() if row["account_id"] == account_id), key=stamp_of)
        # exact: the club had no participant before this tool's first batch and nothing but plain
        # 'ok' batches since, so the new girls of the next batch can be counted, not just bounded
        listed = all((sent_names.get(row["key"]) or {}).get("submissions") == row["submissions"].split("+")
                     for row in ours)     # the names of every batch sent are on file
        exact = listed and all(row["status"] in ("sending", "unknown", "ok", "not_saved") for row in history) and (
            before == int(ours[-1]["participants_after"]) and ours[0]["participants_before"] == "0"
            and all(r["new_exact"] == "yes" for r in ours) if ours else before == 0)
        known = {n for row in ours for n in (sent_names.get(row["key"]) or {}).get("names", [])}
        everything = sorted(known | {fold(n) for s in mine for n in s["names"]})
        pairs = set()
        for i, one in enumerate(everything):
            for two in everything[i + 1:]:
                if alike(one, two):
                    pairs |= {one, two}
        blocked = False
        for session in mine:
            fresh = [n for n in session["names"] if fold(n) not in known]
            session["new_expected"] = len(fresh) if exact else len(session["names"])
            session["new_exact"] = exact
            reasons, details = session.pop("reasons"), session.pop("details")
            accept, rows = session.pop("accept"), session.pop("rows")
            if not exact:
                reasons.append("club_has_earlier_contacts")
                details.append(f"{before} participants, not all made by this run: a girl spelled differently "
                               "would become a second Contact")
            if pairs & {fold(n) for n in session["names"]} and not dup_rule_ok:
                reasons.append("similar_names")
                details.append("two girls this club's duplicate rule may take for one")
            if session["new_expected"] > max_new:
                reasons.append("more_new_girls_than_proven")
                details.append(f"{session['new_expected']} new girls (proven: {max_new})")
            notes["unused_accepts"] += len(accept - set(reasons))
            left = [r for r in reasons if r not in accept]
            if blocked and not left:
                left, details = ["earlier_session_held"], ["an earlier session of this club is held"]
            if left:
                blocked = True               # later sessions would create the girls this one holds back
                hold(left, rows, key=session["key"], detail="; ".join(details),
                     account_name=session["account_name"], date=session["attendance_date"])
                continue
            session["accepted"] = sorted(set(reasons) & accept)
            known |= {fold(n) for n in session["names"]}
            queue.append(session)
    first_size = {}
    for session in queue:
        first_size.setdefault(session["account_id"], len(session["names"]))
    queue.sort(key=lambda s: (first_size[s["account_id"]], s["account_name"], s["account_id"], s["attendance_date"]))
    return queue, held, skipped, notes


def cmd_plan(args, paths):
    resolved = check_resolved(load_json(paths.resolved, "the resolver's output"))
    state = check_state(load_json(paths.state, "the Salesforce snapshot"))
    queue, held, skipped, notes = build_plan(resolved, state, read_decisions(paths.decisions),
                                             paths.ledger.read(), read_sent_names(paths.sent_names),
                                             max_new=args.max_new, dup_rule_ok=args.dup_rule_ok)
    plan = {"made_at_utc": stamp(), "resolved_sha256": sha256(paths.resolved),
            "decisions_sha256": sha256(paths.decisions), "resolved_fetched_at_utc": resolved["fetched_at_utc"],
            "state_read_at_utc": state["read_at_utc"], "closed_by_hand": closed_by_hand(paths.ledger.read()),
            "sessions": queue}
    save_private(paths.plan, json.dumps(plan, indent=1, ensure_ascii=False))
    with open_private(paths.held, "w") as fh:
        writer = csv.DictWriter(fh, fieldnames=HELD_COLS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted(held, key=lambda h: (h["reasons"], h["region"], h["account_name"], h["attendance_date"])))
    days = {(r.get("sf_account_name"), r.get("attendance_date")) for r in resolved["rows"]}
    print(f"resolver: {len(resolved['rows'])} rows from {len({r['submission_id'] for r in resolved['rows']})} "
          f"submissions with girls ticked ({len(days)} club days), "
          f"{sum(len(ids) for ids in (resolved.get('no_ticks') or {}).values())} submissions with nobody ticked "
          f"(never sent), fetched {resolved['fetched_at_utc']}")
    print(f"Salesforce as of {state['read_at_utc']}: {len(state['batches'])} batches")
    names = {a["Id"]: a["Name"] for a in state["accounts"]}
    rows_on = {(a["Account__c"], a["Attendance_Date__c"]): a["n"] for a in state["attendance"]}
    empty = sorted((names.get(b.get("Account__c"), "?"), b.get("Attendance_Date__c") or "", b["Name"], b["Processing_Status__c"])
                   for b in state["batches"] if (b.get("Attendance_Date__c") or "") >= str(SCOPE_START)
                   and not rows_on.get((b.get("Account__c"), b.get("Attendance_Date__c"))))
    if empty:
        print(f"Salesforce holds {len(empty)} batch(es) from {SCOPE_START} on without any attendance for their club and "
              "day - a Success among them blocks that day for a later batch; this tool never adds to a day with any "
              "batch:")
        for club, day, name, status in empty:
            print(f"  {name} {status} {club} / {day}")
    print(f"decisions: {notes['decisions_read']} read and applied"
          + (f"; {notes['set_aside']} report(s) set aside by 'use'" if notes["set_aside"] else "")
          + (f"; {notes['unused_accepts']} 'accept' that no longer applies" if notes["unused_accepts"] else ""))
    print(f"to send: {len(queue)} batches, {sum(len(s['names']) for s in queue)} attendance rows, "
          f"up to {sum(s['new_expected'] for s in queue)} new girls, {len({s['account_id'] for s in queue})} clubs")
    for region in sorted({s["region"] for s in queue}):
        mine = [s for s in queue if s["region"] == region]
        print(f"  {region}: {len(mine)} batches, {sum(len(s['names']) for s in mine)} rows")
    merged = sum(1 for s in queue if len(s["submissions"]) > 1)
    if merged:
        print(f"  {merged} of them join several reports of one club and day (same module and week)")
    released = sum(1 for s in queue if s["accepted"])
    if released:
        print(f"  {released} of them go on Ryan's 'accept'")
    for reason in sorted({s["reason"] for s in skipped}):
        print(f"skipped, {reason}: {sum(1 for s in skipped if s['reason'] == reason)}")
    print(f"held for a decision: {len(held)} ({rel(paths.held)})")
    tally = {}
    for entry in held:
        for reason in entry["reasons"].split("+"):
            tally.setdefault(reason, [0, 0])
            tally[reason][0] += 1
            tally[reason][1] += entry["names"]
    for reason in sorted(tally):
        print(f"  {reason}: {tally[reason][0]} sessions, {tally[reason][1]} rows")
    print(f"plan: {rel(paths.plan)} (holds names; never committed)")


# ---- send ----------------------------------------------------------------------------------------
def marker(session_or_row):
    """What marks a batch as this tool's and as this session's: the club and the reports it carries."""
    subs = session_or_row["submissions"]
    return f"{CREATOR} {session_or_row['account_id']} {'+'.join(subs) if isinstance(subs, list) else subs}"[:255]


def body_of(session):
    return {"Account_Name__c": session["account_name"], "Attendance_Date__c": session["attendance_date"],
            "Contact_IDs__c": ", ".join(session["names"]), "Module__c": session["module"],
            "Module_Week__c": session["module_week"], "Module_Year__c": session["module_year"],
            "Creator__c": marker(session), "enable_fuzzy_matching__c": False}


def known_code(text):
    """The only word of a Salesforce error this tool repeats: its error code (glow.salesforce.error_codes,
    the first of them), else 'other' - the message itself can quote a girl's name."""
    codes = error_codes(text)
    return codes[0] if codes else "other"


def outcome_of(status, message):
    """The KIND of a batch's status message. The text itself is never printed or stored: a
    Salesforce error can quote the value it choked on, and that value is a girl's name."""
    message = message or ""
    if status == OK_STATUS and message == OK_MESSAGE:
        return "success"
    if message.startswith("Duplicate:"):
        return "duplicate_batch"
    if message.startswith("Attendance already exists"):
        return "attendance_already_exists"
    if message.startswith("No participants"):     # a batch without names and without a count (since 2026-10-07)
        return "no_participants"
    status = status if status in ("Success", "Failed", "Pending") else "no status"
    return f"{status.lower()}_{known_code(message)}"


def number_text(value):
    """A number field as Salesforce gives it (a double such as 3.0, or None when empty), for a message."""
    if value is None:
        return "empty"
    if isinstance(value, (int, float)) and not isinstance(value, bool) and float(value).is_integer():
        return str(int(value))
    return repr(value)


def participants_of(org, account_id):
    return org.count(f"SELECT COUNT() FROM Contact WHERE AccountId = {quoted(account_id)} "
                     "AND Contact_Role__c = 'Participant'")


def find_own_batch(org, row):
    """This tool's batch for a session: by its marker (wherever it landed), never by club and day."""
    found = org.query(f"SELECT Id FROM Attendance_Batch__c WHERE Creator__c = {quoted(marker(row))}")
    if len(found) > 1:
        raise Refused(f"{row['key']}: Salesforce holds {len(found)} batches with this session's marker - "
                      "look at them in Salesforce before anything else is sent")
    return found[0]["Id"] if found else None


def verify(org, row, batch_id, paths, ledger):
    """Read a batch back and close its ledger entry as ok or CHECK. `row` is its 'sending' row."""
    batch = org.query("SELECT Id, Name, Processing_Status__c, Status_Message__c, Account__c, CreatedById, "
                      f"CreatedDate, Girls_Present__c FROM Attendance_Batch__c WHERE Id = {quoted(batch_id)}")
    if len(batch) != 1:
        raise Refused(f"{row['key']}: batch {batch_id} is no longer in Salesforce - if it was removed on purpose: "
                      f"close {row['key']} --removed")
    batch = batch[0]
    counts = org.query("SELECT COUNT(Id) n, COUNT_DISTINCT(Contact__c) girls FROM Attendance__c "
                       f"WHERE Attendance_Batch__c = {quoted(batch_id)}")[0]
    contacts = sorted({r["Contact__c"] for r in org.query(
        f"SELECT Contact__c FROM Attendance__c WHERE Attendance_Batch__c = {quoted(batch_id)} "
        f"AND Contact__r.CreatedDate >= {batch['CreatedDate'][:19]}Z") if r.get("Contact__c")})
    after = participants_of(org, row["account_id"])
    names, expected, before = int(row["names"]), int(row["new_expected"]), int(row["participants_before"])
    made, outcome, wrong = after - before, outcome_of(batch["Processing_Status__c"], batch["Status_Message__c"]), []
    if outcome != "success":
        wrong.append(f"status {outcome}")
    if batch["Account__c"] != row["account_id"]:
        wrong.append("the batch landed on another account")
    if counts["n"] != names or counts["girls"] != names:
        wrong.append(f"{counts['n']} rows for {counts['girls']} girls, {names} sent")
    # the processor sets the count on a Success (= the rows it created) and clears it on every Failed path,
    # so it is compared on a Success only: a Failed batch is CHECK already, by its status
    present = batch.get("Girls_Present__c")
    if batch["Processing_Status__c"] == OK_STATUS and present != counts["n"]:
        wrong.append(f"Girls_Present__c is {number_text(present)}, the batch has {counts['n']} rows")
    if (made != expected) if row["new_exact"] == "yes" else not 0 <= made <= names:
        wrong.append(f"{made} new participants, {expected} expected")
    if len(contacts) != made:
        wrong.append(f"{len(contacts)} contacts made by the batch, the club grew by {made}")
    closed = dict(row, done_utc=stamp(), batch_id=batch_id, batch_name=batch["Name"], rows=counts["n"],
                  participants_after=after, contacts_created=len(contacts), created_by=batch["CreatedById"],
                  outcome=outcome, status="CHECK" if wrong else "ok", note="; ".join(wrong) or row.get("note", ""))
    listed = set()
    if os.path.exists(paths.contacts):
        with open(paths.contacts, encoding="utf-8", newline="") as fh:
            listed = {tuple(line) for line in csv.reader(fh)}
    with open_private(paths.contacts, "a") as fh:     # the rollback list first, then the verdict
        csv.writer(fh, lineterminator="\n").writerows(
            [batch_id, contact] for contact in contacts if (batch_id, contact) not in listed)
    paths.ledger.append(closed, ledger)
    if wrong:
        raise Refused(f"{row['key']}: batch {closed['batch_name']} is in Salesforce but not as planned - "
                      + "; ".join(wrong) + ". STOPPED: it may hold part of the attendance and blocks this club "
                      "and day. Read its status message in Salesforce; then either remove the batch, its rows "
                      f"and its contacts by hand and `close {row['key']} --removed`, or `close {row['key']} "
                      "--accepted` (RUNBOOK, Back-fill of attendance into Salesforce)")
    return closed


def send_one(org, session, ledger, paths):
    """Prove, record, insert, read back, record. Raises Refused at the first thing not as planned."""
    acc_id, date, key = session["account_id"], session["attendance_date"], session["key"]
    names = session["names"]
    if not ACCOUNT_ID.fullmatch(acc_id) or iso(date) is None or not isinstance(names, list) or not names \
            or any(not isinstance(n, str) or bad_name(n) for n in names):
        raise Refused(f"{key}: the plan entry is not usable - run plan again")
    found = org.query(f"SELECT Id, Name, RecordTypeId, ParentId FROM Account WHERE Name = {quoted(session['account_name'])}")
    if len(found) != 1 or found[0]["Id"] != acc_id or found[0]["RecordTypeId"] != CLUB_RECORD_TYPE \
            or not found[0].get("ParentId"):
        raise Refused(f"{key}: the club name no longer leads to exactly its one Club account "
                      f"({len(found)} found) - nothing sent; snapshot and plan again")
    if org.count(f"SELECT COUNT() FROM Attendance_Batch__c WHERE Account__c = {quoted(acc_id)} "
                 f"AND Attendance_Date__c = {date}") or \
            org.count(f"SELECT COUNT() FROM Attendance__c WHERE Account__c = {quoted(acc_id)} "
                      f"AND Attendance_Date__c = {date}"):
        raise Refused(f"{key}: Salesforce already has a batch or attendance for this club and day (a live "
                      "submission?) - nothing sent; snapshot and plan again")
    before = participants_of(org, acc_id)
    mine = sorted((r for r in last_rows(ledger, "key").values() if r["account_id"] == acc_id and r["status"] in DONE),
                  key=stamp_of)
    if session["new_exact"] and before != (int(mine[-1]["participants_after"]) if mine else 0):
        raise Refused(f"{key}: the club has {before} participants, not what this run left - somebody "
                      "else added girls; nothing sent; snapshot and plan again")
    row = {"when_utc": stamp(), "key": key, "region": session["region"], "account_id": acc_id,
           "account_name": session["account_name"], "attendance_date": date,
           "submissions": "+".join(session["submissions"]), "names": len(names),
           "new_expected": session["new_expected"], "new_exact": "yes" if session["new_exact"] else "no",
           "participants_before": before, "status": "sending",
           "note": ("accepted: " + "+".join(session["accepted"])) if session.get("accepted") else ""}
    sent = read_sent_names(paths.sent_names)  # used only once the ledger says this key is done
    sent[key] = {"submissions": session["submissions"], "set_aside": session.get("set_aside") or [],
                 "names": sorted(fold(n) for n in names)}
    save_private(paths.sent_names, json.dumps(sent, indent=1, ensure_ascii=False))
    paths.ledger.append(row, ledger)  # from here on the ledger knows a batch may exist
    status, answer, batch_id = 0, None, None
    try:
        status, answer = org.insert("Attendance_Batch__c", body_of(session))
        batch_id = answer.get("id") if status == 201 and isinstance(answer, dict) else None
        if not batch_id and 400 <= status < 500 and status != 401 and isinstance(answer, list):
            code = known_code(str(answer[0].get("errorCode") or "")) if answer and isinstance(answer[0], dict) else "other"
            paths.ledger.append(dict(row, done_utc=stamp(), status="not_saved", outcome=f"http_{status}_{code}",
                                     note="Salesforce refused the batch and saved nothing"), ledger)
            raise Refused(f"{key}: Salesforce refused the batch (HTTP {status} {code}) and saved nothing. This club "
                          f"waits; decide with Ryan, then `send --apply --vpn-off --retry {key}` (RUNBOOK, Back-fill "
                          "of attendance into Salesforce)")
        batch_id = batch_id or find_own_batch(org, row)
        if not batch_id:
            raise Refused("no answer and no batch yet")
        return verify(org, row, batch_id, paths, ledger)
    except BaseException:
        if ledger[-1]["key"] == key and ledger[-1]["status"] == "sending":   # the outcome is not known
            paths.ledger.append(dict(row, done_utc=stamp(), status="unknown", batch_id=batch_id or "",
                                     outcome=f"http_{status}", note="the answer or the read-back was lost"),
                                ledger)
            raise Refused(f"{key}: the batch was sent but Salesforce's answer or the read-back was lost (HTTP "
                          f"{status}) - A BATCH MAY BE IN SALESFORCE. Nothing more is sent; run `send --apply "
                          "--vpn-off` again: it looks this batch up before anything else") from None
        raise


def settle(org, row, ledger, paths):
    """A batch whose outcome was lost ('sending' / 'unknown'): look it up by its marker and finish."""
    batch_id = row["batch_id"] or find_own_batch(org, row)
    if not batch_id:
        ready = datetime.datetime.strptime(row["when_utc"], STAMP) + datetime.timedelta(minutes=SETTLE_AFTER_MINUTES)
        if datetime.datetime.utcnow() < ready:
            raise Refused(f"{row['key']}: no batch with this session's marker yet, but Salesforce may still be "
                          f"working on it - run send again after {ready.strftime('%H:%M:%S')} UTC")
        paths.ledger.append(dict(row, done_utc=stamp(), status="not_saved", outcome="not_found",
                                 note="looked up later: no batch with this session's marker"), ledger)
        print(f"  settled {row['key']}: Salesforce saved nothing; the club waits for --retry")
        return
    closed = verify(org, row, batch_id, paths, ledger)
    print(f"  settled {row['key']}: {closed['batch_name']} is in Salesforce and as planned")


def cmd_send(args, paths, org):
    plan = load_json(paths.plan, "the plan")
    if plan.get("resolved_sha256") != sha256(paths.resolved) or plan.get("decisions_sha256") != sha256(paths.decisions):
        raise Refused("resolved.json or decisions.csv changed after the plan was made - run plan again")
    ledger = paths.ledger.read()
    stuck = sorted(k for k, r in last_rows(ledger, "key").items() if r["status"] in OPEN)
    if stuck:
        raise Refused("the ledger holds a batch that is in Salesforce but was not right (" + ", ".join(stuck)
                      + ") - deal with it, then `close <key> --removed` or `close <key> --accepted` (RUNBOOK, "
                      "Back-fill of attendance into Salesforce)")
    unsettled = [r for r in last_rows(ledger, "key").values() if r["status"] in UNSETTLED]
    if args.apply:
        for row in unsettled:                # before anything else: it needs the ledger only
            settle(org, row, ledger, paths)
    elif unsettled:
        print(f"{len(unsettled)} batch(es) with an unknown outcome: `send --apply` looks them up first")
    if plan.get("closed_by_hand") != closed_by_hand(ledger):
        raise Refused("a batch was closed by hand after this plan was made - snapshot and plan again: that club's "
                      "sessions must be held for an accept")
    if args.apply:
        try:
            age = datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.strptime(
                plan.get("resolved_fetched_at_utc") or "", STAMP).replace(tzinfo=datetime.timezone.utc)
        except (ValueError, TypeError):
            raise Refused("the plan does not say when the submissions were fetched - run plan again") from None
        if not datetime.timedelta(0) <= age + datetime.timedelta(minutes=5) or age > datetime.timedelta(hours=MAX_AGE_HOURS):
            raise Refused(f"the submissions were fetched more than {MAX_AGE_HOURS} hours ago - run the resolver, "
                          "snapshot and plan again, so a newer report of the same session is not missed")
    last = last_rows(ledger, "key")
    done = {k for k, r in last.items() if r["status"] in DONE}
    retry = set(args.retry or [])
    refused = {k: r for k, r in last.items() if r["status"] == "not_saved"}
    if retry - set(refused):
        raise Refused("--retry: not a session Salesforce refused: " + ", ".join(sorted(retry - set(refused))))
    in_plan = {s["key"] for s in plan["sessions"]}
    parked = {r["account_id"] for k, r in refused.items() if k not in retry and k in in_plan}
    order = {}                               # a club's sessions go in the plan's order, never around it
    for session in plan["sessions"]:
        order.setdefault(session["account_id"], []).append(session["key"])
    queue = [s for s in plan["sessions"] if s["key"] not in done and s["account_id"] not in parked]
    if args.only:
        queue = [s for s in queue if s["key"] == args.only]
        for session in queue:
            mine = order[session["account_id"]]
            if any(k not in done for k in mine[:mine.index(session["key"])]):
                raise Refused(f"--only {args.only}: an earlier session of this club is not sent yet; its count of "
                              "new girls depends on that one")
    if args.limit is not None:
        queue = queue[:args.limit]
    print(f"queue: {len(queue)} batches, {sum(len(s['names']) for s in queue)} attendance rows, "
          f"up to {sum(s['new_expected'] for s in queue)} new girls ({len(done)} already sent by this tool"
          + (f"; {len(parked)} clubs wait for a refused batch" if parked else "") + ")")
    if not args.apply:
        for session in queue[:10]:
            print(f"  would send {session['key']}  {session['region']} / {session['account_name']} / "
                  f"{session['attendance_date']}: {len(session['names'])} girls, {session['new_expected']} new")
        print("dry run: nothing was sent (--apply writes, with Ryan's go)")
        return
    for position, session in enumerate(queue, 1):
        row = send_one(org, session, ledger, paths)
        print(f"  {position}/{len(queue)} {row['batch_name']} {session['account_name']} {session['attendance_date']}: "
              f"{row['rows']} rows, {row['contacts_created']} new girls - ok")
    print(f"sent and verified: {len(queue)} batches; ledger {rel(paths.ledger.path)}")


# ---- close, status -------------------------------------------------------------------------------
def cmd_close(args, paths):
    row = last_rows(paths.ledger.read(), "key").get(args.key)
    if row is None:
        raise Refused(f"the ledger has no session {args.key}")
    if args.accepted and row["status"] != "CHECK":
        raise Refused(f"--accepted is for a batch the ledger marks CHECK; {args.key} is '{row['status']}'")
    if args.removed and (row["status"] not in DONE | OPEN | UNSETTLED or not row["batch_id"]):
        raise Refused(f"--removed is for a batch that was in Salesforce; {args.key} is '{row['status']}'")
    closed = dict(row, done_utc=stamp(), status="accepted" if args.accepted else "removed", new_exact="no",
                  note=("accepted as it is by Ryan" if args.accepted else "removed from Salesforce by hand")
                  + (f": {args.note}" if args.note else ""))
    paths.ledger.append(closed)
    print(f"{args.key}: recorded as {closed['status']} ({row['batch_name']}); this club's later sessions will "
          "be held for Ryan's 'accept' (its participants are no longer all this run's)")


def cmd_status(args, paths):
    last = last_rows(paths.ledger.read(), "key")
    good = [r for r in last.values() if r["status"] in DONE]
    print(f"ledger: {len(good)} batches sent and verified, {sum(int(r['rows'] or 0) for r in good)} attendance rows, "
          f"{sum(int(r['contacts_created'] or 0) for r in good)} new girls, "
          f"{len({r['account_id'] for r in good})} clubs")
    for row in last.values():
        if row["status"] not in DONE:
            print(f"  {row['status']} {row['key']} {row['batch_name'] or '(no batch)'} {row['outcome']} {row['note']}")
    if good:
        print(f"rollback would remove, by id: {len(good)} batches with their attendance rows (ledger.csv, batch_id) "
              f"and the {sum(int(r['contacts_created'] or 0) for r in good)} participant contacts they created "
              f"({rel(paths.contacts)}) - only with Ryan's go")


def main(argv=None, org=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 allow_abbrev=False)
    ap.add_argument("--dir", default=DEFAULT_DIR, help="the back-fill folder (default: data/backfill_2026-09)")
    ap.add_argument("--org", default="glow", help="the Salesforce CLI alias (default: glow)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    snap = sub.add_parser("snapshot", allow_abbrev=False)
    plan = sub.add_parser("plan", allow_abbrev=False)
    plan.add_argument("--max-new", type=positive, default=MAX_NEW, help="largest number of new girls in one batch")
    plan.add_argument("--dup-rule-ok", action="store_true",
                      help="Ryan confirmed the Contact duplicate rule does not block a new girl")
    send = sub.add_parser("send", allow_abbrev=False)
    send.add_argument("--apply", action="store_true", help="write to Salesforce (needs Ryan's go)")
    send.add_argument("--limit", type=positive, help="send only the first N of the queue")
    send.add_argument("--only", help="send only this session key")
    send.add_argument("--retry", action="append", help="a session Salesforce refused, decided since (repeatable)")
    for live in (snap, send):
        add_vpn_flag(live)
    close = sub.add_parser("close", allow_abbrev=False)
    close.add_argument("key")
    how = close.add_mutually_exclusive_group(required=True)
    how.add_argument("--removed", action="store_true", help="the batch, its rows and its contacts were removed by hand")
    how.add_argument("--accepted", action="store_true", help="the batch the ledger marks CHECK is right as it is")
    close.add_argument("--note", default="")
    sub.add_parser("status", allow_abbrev=False)
    args = ap.parse_args(argv)
    try:
        paths = Paths(args.dir)
        keep_private(paths.folder)
        if args.cmd == "plan":
            cmd_plan(args, paths)
        elif args.cmd == "status":
            cmd_status(args, paths)
        elif args.cmd == "close":
            cmd_close(args, paths)
        else:
            if args.cmd == "snapshot" or args.apply:
                require_vpn_off(args)
            org = org or Org(args.org)
            (cmd_snapshot if args.cmd == "snapshot" else cmd_send)(args, paths, org)
    except Refused as stop:
        sys.exit(str(stop))
    except (KeyError, IndexError, ValueError, TypeError, AttributeError, UnicodeError, OSError, csv.Error) as err:
        where = traceback.extract_tb(err.__traceback__)[-1]     # the place only: the text may quote a name
        sys.exit(f"stopped on an unexpected {type(err).__name__} at {os.path.basename(where.filename)}:{where.lineno} - "
                 "a file this tool reads is damaged or has another shape. Nothing was sent by this step; if a send "
                 "was under way, run `send` again: it settles the open batch first")


if __name__ == "__main__":
    main()
