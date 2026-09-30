#!/usr/bin/env python3
"""Checks and bookkeeping for creating the Club accounts in Salesforce
(docs/plans/2026-09-30-salesforce-clubs.md).

This script never talks to Salesforce: the writes and the SOQL reads go through the
Salesforce connector in a Claude Code session, one record per call. It only

  build     validates clubs_to_create.csv and cuts the write set into batches (write_set.json)
  pickers   GETs the live Club pickers (read-only) and compares them with the write set
  soql      prints the SOQL for a batch, for all names, for the parents, the totals or the count
  bodies    prints the request bodies of the open batch that are not recorded yet
  parents   checks a saved read of the parent (partner) accounts
  precheck  checks a saved read BEFORE a batch is written, and opens the batch in run_log.csv
  verify    checks a saved read AFTER a batch, keeps created_accounts.csv, and closes the batch
  totals    compares a saved read of all Club accounts with the write set

A "saved read" is the connector's whole answer ({totalSize, done, records}) to the query that
`soql` printed, saved as JSON with the time of the answer - copied, never retyped. Inputs and
outputs live in the prep folder under data/ (never committed); a rehearsal folder (--dir)
belongs outside the checkout. It prints counts and club codes; club names appear only where a
request body, a query or a picker difference needs them.
"""
import argparse
import collections
import csv
import datetime
import hashlib
import json
import os
import re
import sys
import unicodedata

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DIR = os.path.join(REPO, "data", "sf_prep_2026-09-30")

CLUB_RECORD_TYPE = "012RP000002uklNYAQ"      # RecordType 'Club' on Account (read 2026-09-30)
PARTNER_RECORD_TYPE = "0126A000000cdYFQAY"   # 'Household Account': every partner account has it
# the two pilot Club accounts Ryan is checking: never a parent, never a link target
ON_HOLD_ACCOUNTS = {"001RP00000nMZXfYAO", "001RP00000mgVVMYA2"}
BASELINE_CLUBS = 10                          # Club accounts before this plan (the pilot ones)
# the three single-record batches: an apostrophe, a pilot account with little history, an accent
FIRST_CREATE, FIRST_LINK, FIRST_ACCENT = "GLOWINGP", "ELOHIM", "LASNINAS"
BATCH = 25
REGION_ORDER = {"U.S": 0, "Latin America": 1, "Asia": 2, "Africa": 3}
CSV_COLS = {"region", "club_name", "partner_name", "sf_partner_account_id", "sf_partner_account_name",
            "match", "already_in_sf", "notes", "club_code", "active_girls", "sf_account_name", "action"}
CREATED_COLS = ["when_utc", "batch", "seq", "action", "region", "club_code", "sf_account_id",
                "sf_account_name", "parent_id", "previous_parent_id", "note"]
LOG_COLS = ["when_utc", "batch", "event"]
FIELDS = "Id, Name, RecordTypeId, ParentId, Description, OwnerId, CreatedById, CreatedDate"
ACCOUNT_ID = re.compile(r"001[A-Za-z0-9]{15}")
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# characters that render as nothing or as a space but are not one, beyond the Unicode categories
FILLERS = {0x034F, 0x115F, 0x1160, 0x2800, 0x3164, 0xFFA0, 0xFFFC} | set(range(0xFE00, 0xFE10))


def odd(name):
    """Control, format, private, unassigned, line/paragraph separators, any space that is not
    the plain one, and the invisible fillers: none of them may hide in a name."""
    for c in name:
        cat = unicodedata.category(c)
        if cat in ("Cc", "Cf", "Co", "Cn", "Cs", "Zl", "Zp") or (cat == "Zs" and c != " ") \
                or ord(c) in FILLERS:
            return True
    return False


class Paths:
    def __init__(self, folder):
        self.csv = os.path.join(folder, "clubs_to_create.csv")
        self.write_set = os.path.join(folder, "write_set.json")
        self.created = os.path.join(folder, "created_accounts.csv")
        self.log = os.path.join(folder, "run_log.csv")
        self.before = os.path.join(folder, "link_targets_before.json")
        self.hold = os.path.join(folder, "hold_codes.txt")     # one club_code per line, '#' comments


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(STAMP)


def stamp_seconds(stamp):
    try:
        return datetime.datetime.strptime(stamp, STAMP).replace(tzinfo=datetime.timezone.utc).timestamp()
    except ValueError:
        sys.exit(f"run_log.csv has a time that is not like {now()}: {stamp!r} - restore the file")


def saved_second(path):
    """The whole second a read was saved in. A read counts as newer than a step only when it
    was saved in a LATER second, so the read a step was made from never passes as fresh again."""
    if not os.path.exists(path):
        sys.exit(f"{path}: no such saved read")
    return int(os.path.getmtime(path))


def key(name):
    """How Salesforce and the Apex processor compare names: trimmed, case-insensitive."""
    return name.strip().casefold()


def csv_sha(paths):
    with open(paths.csv, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def rows(paths):
    if not os.path.exists(paths.csv):
        sys.exit(f"{paths.csv} is missing: the prep folder holds the approved club list")
    with open(paths.csv, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = CSV_COLS - set(reader.fieldnames or [])
        if missing:
            sys.exit(f"clubs_to_create.csv has no column {sorted(missing)}: it is not the approved list")
        rs = list(reader)
    if any(None in r or None in r.values() for r in rs):
        sys.exit("clubs_to_create.csv has a row with too few or too many cells: fix the export")
    return rs


def hold_codes(paths):
    if not os.path.exists(paths.hold):
        return set()
    with open(paths.hold, encoding="utf-8-sig") as fh:
        return {line.split("#")[0].strip() for line in fh if line.split("#")[0].strip()}


def split_rows(rs):
    create = [r for r in rs if r["action"] == "create"]
    link = [r for r in rs if r["action"].startswith("link existing")]
    same = [r for r in rs if r["action"].startswith("create (")]
    if len(create) + len(link) + len(same) != len(rs):
        sys.exit("an action value is not one of create / link existing / create (...): fix the CSV")
    return create, link, same


def csv_problems(rs, create, link, same, held_codes):
    problems = []
    for r in rs:
        if not re.fullmatch(r"[A-Z0-9]+", r["club_code"]):
            problems.append(f"a {r['region']} row has a club_code that is not capitals and digits: "
                            f"{r['club_code']!r}")
    partners = {key(r["sf_partner_account_name"]) for r in rs} | {key(r["partner_name"]) for r in rs}
    for r in create + link:
        code, name = r["club_code"], r["sf_account_name"]
        if not name or name != name.strip() or "  " in name or odd(name):
            problems.append(f"{code}: name is empty or has edge/double/invisible whitespace")
        if name != unicodedata.normalize("NFC", name):
            problems.append(f"{code}: name is not NFC-normalised")
        if len(name) > 255:
            problems.append(f"{code}: name longer than 255")
        if name != r["club_name"]:
            problems.append(f"{code}: sf_account_name differs from club_name")
        if key(name) in partners:
            problems.append(f"{code}: the club is named like a partner account (the processor "
                            "matches every Account by name)")
        if r["region"] not in REGION_ORDER:
            problems.append(f"{code}: region {r['region']!r} is not a form region")
        if not ACCOUNT_ID.fullmatch(r["sf_partner_account_id"]):
            problems.append(f"{code}: partner account id is not an 18-character Account id")
        if r["sf_partner_account_id"] in ON_HOLD_ACCOUNTS:
            problems.append(f"{code}: parent is an on-hold pilot account")
        girls = r["active_girls"].strip()
        if girls and not (girls.isascii() and girls.isdecimal()):
            problems.append(f"{code}: active_girls is not a whole number")
    for r in create:
        if r["already_in_sf"].strip():
            problems.append(f"{r['club_code']}: a create row carries already_in_sf")
    targets = collections.Counter(r["already_in_sf"] for r in link)
    for r in link:
        if not ACCOUNT_ID.fullmatch(r["already_in_sf"]):
            problems.append(f"{r['club_code']}: link row without an 18-character already_in_sf id")
        if r["already_in_sf"] in ON_HOLD_ACCOUNTS:
            problems.append(f"{r['club_code']}: link target is an on-hold pilot account")
        if targets[r["already_in_sf"]] > 1:
            problems.append(f"{r['club_code']}: its link target is on two rows")
    for r in create + link:
        if r["sf_partner_account_id"] in targets:
            problems.append(f"{r['club_code']}: its parent is a link target (a club, not a partner)")
    # a name may be used once: against every row's account name and the held clubs' plain names
    names = collections.Counter(key(r["sf_account_name"]) for r in rs)
    plain = {key(r["club_name"]) for r in same}
    for r in create + link:
        if names[key(r["sf_account_name"])] > 1 or key(r["sf_account_name"]) in plain:
            problems.append(f"{r['club_code']}: name is shared with another row (case-insensitive)")
    codes = collections.Counter(r["club_code"] for r in rs)
    problems += [f"{c}: club_code used {n} times" for c, n in codes.items() if n > 1]
    ids, labels = collections.defaultdict(set), collections.defaultdict(set)
    for r in rs:
        ids[r["partner_name"]].add(r["sf_partner_account_id"])
        labels[r["sf_partner_account_id"]].add(r["sf_partner_account_name"])
    problems += [f"partner {p!r} maps to {len(v)} Salesforce accounts" for p, v in ids.items() if len(v) > 1]
    problems += [f"partner account {i} carries {len(v)} names in the CSV" for i, v in labels.items() if len(v) > 1]
    problems += [f"{c}: hold_codes.txt names a code that is not a create/link row"
                 for c in sorted(held_codes - {r["club_code"] for r in create + link})]
    return problems


def build(args, paths):
    rs = rows(paths)
    held_codes = hold_codes(paths)
    create, link, same = split_rows(rs)
    problems = csv_problems(rs, create, link, same, held_codes)
    if problems:
        sys.exit("refusing to build the write set:\n  " + "\n  ".join(problems))
    create = [r for r in create if r["club_code"] not in held_codes]
    link = [r for r in link if r["club_code"] not in held_codes]
    create.sort(key=lambda r: (REGION_ORDER[r["region"]], r["partner_name"].casefold(),
                               r["sf_account_name"].casefold()))
    link.sort(key=lambda r: (REGION_ORDER[r["region"]], r["sf_account_name"].casefold()))

    def first(rs_, code, what, needs):
        r = next((r for r in rs_ if r["club_code"] == code), None)
        if r is None:
            sys.exit(f"{what} {code} is not in the write set: choose another with --{what}")
        if r["match"] != "exact":
            sys.exit(f"{what} {code} hangs on a partner matched by alias: choose an exact match")
        name = r["sf_account_name"]
        if needs == "apostrophe" and "'" not in name:
            sys.exit(f"{what} {code} has no apostrophe: choose a name that has one")
        if needs == "accent" and not any(c.isalpha() and not c.isascii() for c in name):
            sys.exit(f"{what} {code} has no accented letter: choose a name that has one")
        return r

    c0 = first(create, args.first_create, "first-create", "apostrophe")
    l0 = first(link, args.first_link, "first-link", None)
    c1 = first(create, args.first_accent, "first-accent", "accent")
    if c0 is c1:
        sys.exit("first-create and first-accent are the same club: choose two")

    def item(r):
        out = {"action": "create" if r["action"] == "create" else "link", "region": r["region"],
               "club_code": r["club_code"], "partner": r["sf_partner_account_name"],
               "parent_id": r["sf_partner_account_id"], "name": r["sf_account_name"],
               "active_girls": int(r["active_girls"].strip() or 0)}
        if out["action"] == "create":
            out["body"] = {"Name": r["sf_account_name"], "RecordTypeId": CLUB_RECORD_TYPE,
                           "ParentId": r["sf_partner_account_id"],
                           "Description": f"GLOW club code {r['club_code']}; created from the club "
                                          f"registry {args.created_on}"}
        else:
            out["id"] = r["already_in_sf"]
            out["body"] = {"ParentId": r["sf_partner_account_id"]}
        return out

    # three single records first (a create, a link, an accented create), then the rest
    rest = [item(r) for r in create if r is not c0 and r is not c1]
    batches = [[item(c0)], [item(l0)], [item(c1)]]
    batches += [rest[i:i + BATCH] for i in range(0, len(rest), BATCH)]
    others = [item(r) for r in link if r is not l0]
    if others:
        batches.append(others)
    seq = 0
    for b, items in enumerate(batches):
        for it in items:
            seq += 1
            it["seq"], it["batch"] = seq, b
    fresh = {"csv_sha256": csv_sha(paths), "created_on": args.created_on,
             "held": sorted(held_codes), "batches": batches}
    if read_log(paths) or read_created(paths):
        old = None
        if os.path.exists(paths.write_set):
            with open(paths.write_set, encoding="utf-8") as fh:
                old = json.load(fh)
        if old != fresh:
            sys.exit("the run has started (run_log.csv, created_accounts.csv) and write_set.json is gone "
                     "or this build would change the batches: restore write_set.json, the CSV, "
                     "hold_codes.txt and the options the run was built with")
    with open(paths.write_set, "w", encoding="utf-8") as fh:
        json.dump(fresh, fh, ensure_ascii=False, indent=1)
    print(f"write set: {len(create)} create + {len(link)} link = {seq} writes in {len(batches)} batches; "
          f"{len(same)} same-name rows held; {len(held_codes)} more held by hold_codes.txt")
    print("batch sizes:", " ".join(f"{b}:{len(items)}{items[0]['action'][0]}"
                                   for b, items in enumerate(batches)))
    by_region = collections.Counter((i["region"], i["action"]) for items in batches for i in items)
    print("by region:", ", ".join(f"{r} {a} {n}" for (r, a), n in sorted(by_region.items())))
    print("distinct parent accounts:", len({i["parent_id"] for items in batches for i in items}),
          "| active girls covered:", sum(i["active_girls"] for items in batches for i in items))


def load_batches(paths):
    if not os.path.exists(paths.write_set):
        sys.exit("no write_set.json: run `build` first (if the run had started, restore the file)")
    with open(paths.write_set, encoding="utf-8") as fh:
        data = json.load(fh)
    if data["csv_sha256"] != csv_sha(paths):
        sys.exit("clubs_to_create.csv changed after `build`: restore it, or build again before any write")
    if data.get("held") != sorted(hold_codes(paths)):
        sys.exit("hold_codes.txt changed after `build`: build again before any write; once the run "
                 "has started a club cannot be held - restore the file, stop and ask Ryan")
    return data["batches"]


def batch_items(paths, n):
    batches = load_batches(paths)
    if not 0 <= n < len(batches):
        sys.exit(f"batch {n} does not exist (0..{len(batches) - 1})")
    return batches[n]


def all_items(paths):
    return [i for items in load_batches(paths) for i in items]


def soql_quote(s):
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def returned_ids(path):
    """The ids the connector returned for a batch's creates, one per line."""
    if not os.path.exists(path):
        sys.exit(f"{path}: no such file (the ids the connector returned, one per line)")
    with open(path, encoding="utf-8") as fh:
        ids = {line.strip() for line in fh if line.strip()}
    wrong = sorted(i for i in ids if not ACCOUNT_ID.fullmatch(i))
    if wrong:
        sys.exit(f"{path}: not 18-character Account ids: {wrong}")
    return ids


def names_query(items, more_ids=()):
    """The accounts of these names AND these items' parents (and any further ids): the parents
    always come back, so an empty or foreign answer can never pass for "nothing exists yet"."""
    by_id = sorted({i["parent_id"] for i in items} | set(more_ids))
    return (f"SELECT {FIELDS} FROM Account WHERE Name IN "
            f"({', '.join(soql_quote(i['name']) for i in items)}) OR Id IN "
            f"({', '.join(soql_quote(p) for p in by_id)}) LIMIT 200")


def chunks_of(items, size):
    return [items[s:s + size] for s in range(0, len(items), size)]


def soql(args, paths):
    if args.ids and args.batch is None:
        sys.exit("--ids goes with --batch (the read after the writes)")
    if args.count:
        print(f"SELECT COUNT(Id) n FROM Account WHERE RecordTypeId = '{CLUB_RECORD_TYPE}'")
    elif args.totals:
        print(f"SELECT {FIELDS} FROM Account WHERE RecordTypeId = '{CLUB_RECORD_TYPE}' "
              "ORDER BY Id LIMIT 1000")
    elif args.parents:
        ids = sorted({i["parent_id"] for i in all_items(paths)})
        print(f"SELECT Id, Name, RecordTypeId, ParentId FROM Account WHERE Id IN "
              f"({', '.join(soql_quote(i) for i in ids)}) LIMIT 200")
    elif args.all:
        for n, chunk in enumerate(chunks_of(all_items(paths), args.chunk)):
            print(f"-- chunk {n} ({len(chunk)} names and their parents)")
            print(names_query(chunk))
    else:
        # after the writes, --ids adds the ids the connector returned: an account stored under
        # another name than the one sent is then in the read too
        print(names_query(batch_items(paths, args.batch), returned_ids(args.ids) if args.ids else ()))


def bodies(args, paths):
    items = batch_items(paths, args.batch)
    state = batch_state(read_log(paths), args.batch)[0]
    if args.preview:
        print(f"PREVIEW of batch {args.batch} ({state or 'not prechecked'}): for reading, write nothing from it")
    elif state != "open":
        sys.exit(f"batch {args.batch} is {state or 'not prechecked'}: bodies are printed for the open "
                 "batch only (`precheck` first; a closed batch is never written again); --preview to read them")
    done = set() if args.preview else {r["club_code"] for r in read_created(paths)}
    for i in items:
        if i["club_code"] in done:
            print(f"#{i['seq']} {i['club_code']}: in created_accounts.csv already - never written twice")
            continue
        head = f"#{i['seq']} {i['action']} {i['club_code']} ({i['region']})"
        if i["action"] == "link":
            head += f" id={i['id']}"
        print(head)
        print(json.dumps(i["body"], ensure_ascii=False))


def records(path):
    """The records of one saved connector answer; refuses anything else."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as err:
        sys.exit(f"{path}: not a saved read ({err}): save the connector's whole answer as JSON")
    recs = data.get("records") if isinstance(data, dict) else None
    size = data.get("totalSize") if isinstance(data, dict) else None
    if not isinstance(recs, list) or data.get("done") is not True or isinstance(size, bool) or size != len(recs):
        sys.exit(f"{path}: save the connector's whole answer ({{totalSize, done, records}}); this one "
                 "is cut, incomplete or another shape")
    if any(not isinstance(r, dict) or not isinstance(r.get("Id"), str)
           or not isinstance(r.get("Name"), str) for r in recs):
        sys.exit(f"{path}: every record needs Id and Name (use the query `soql` prints)")
    return recs


def unread(rec, *fields):
    """The fields this read did not select: a field that was not read is not an empty field."""
    missing = [f for f in fields if f not in rec]
    return f"the read has no {', '.join(missing)} (use the query `soql` prints)" if missing else ""


def by_name(recs):
    out = collections.defaultdict(list)
    for rec in recs:
        out[key(rec["Name"])].append(rec)
    return out


def read_log(paths):
    if not os.path.exists(paths.log) or os.path.getsize(paths.log) == 0:
        return []
    with open(paths.log, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != LOG_COLS:
            sys.exit("run_log.csv has lost its header row: restore it before going on")
        return list(reader)


def log_event(paths, batch, event):
    fresh = not os.path.exists(paths.log) or os.path.getsize(paths.log) == 0
    with open(paths.log, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=LOG_COLS)
        if fresh:
            w.writeheader()
        w.writerow({"when_utc": now(), "batch": batch, "event": event})


def batch_state(log, batch):
    """(state, when it was last opened) for a batch: closed > open > None."""
    events = [e for e in log if e["batch"] == str(batch)]
    opened = [e["when_utc"] for e in events if e["event"] == "open"]
    if any(e["event"] == "closed" for e in events):
        return "closed", opened[-1] if opened else None
    return ("open", opened[-1]) if opened else (None, None)


def read_created(paths):
    if not os.path.exists(paths.created) or os.path.getsize(paths.created) == 0:
        return []
    with open(paths.created, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != CREATED_COLS:
            sys.exit("created_accounts.csv has lost its header row: restore it before going on")
        return list(reader)


def write_created(paths, created):
    tmp = paths.created + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CREATED_COLS)
        w.writeheader()
        w.writerows(created)
    os.replace(tmp, paths.created)


def made_count(created):
    """The Club accounts the run has added to Salesforce, by the rollback file."""
    return sum(r["action"] not in ("link", "gone") for r in created)


def read_before(paths):
    if not os.path.exists(paths.before):
        return {}
    with open(paths.before, encoding="utf-8") as fh:
        return json.load(fh)


def check_state(paths, log):
    """run_log.csv, created_accounts.csv and write_set.json must tell one story: a lost or
    emptied file is a stop, never something to work around."""
    created = read_created(paths)
    known = {e["batch"] for e in log}
    if any(str(r["batch"]) not in known for r in created):
        sys.exit("created_accounts.csv has rows of a batch that run_log.csv does not know: run_log.csv "
                 "has lost rows - stop, write nothing, restore it (the plan, 'If a state file is lost')")
    recorded = {(str(r["batch"]), r["club_code"]) for r in created}
    lost = [i["club_code"] for b, items in enumerate(load_batches(paths))
            if batch_state(log, b)[0] == "closed" for i in items if (str(b), i["club_code"]) not in recorded]
    if lost:
        sys.exit(f"{len(lost)} clubs of closed batches (first: {lost[0]}) are not in created_accounts.csv: "
                 "it has lost rows, or write_set.json is not the one the run was made with - stop, write "
                 "nothing, restore it (the plan, 'If a state file is lost')")


def parent_problems(items, recs):
    """Every parent of these items must be in the read: a partner account of the expected
    name, itself without a parent, not on hold."""
    got = collections.defaultdict(list)
    for rec in recs:
        got[rec["Id"]].append(rec)
    bad = []
    for pid, partner in sorted({(i["parent_id"], i["partner"]) for i in items}):
        found = got.get(pid, [])
        if len(found) != 1:
            bad.append(f"parent {pid}: {len(found)} records in the read (want 1)")
        elif unread(found[0], "RecordTypeId", "ParentId"):
            bad.append(f"parent {pid}: {unread(found[0], 'RecordTypeId', 'ParentId')}")
        elif found[0]["Name"] != partner:
            bad.append(f"parent {pid}: its name is not the CSV's sf_partner_account_name")
        elif found[0]["RecordTypeId"] != PARTNER_RECORD_TYPE or found[0]["ParentId"]:
            bad.append(f"parent {pid}: not a partner account (record type), or it has a parent itself")
        if pid in ON_HOLD_ACCOUNTS:
            bad.append(f"parent {pid}: on hold")
    return bad


def named_records(items, recs):
    """The read without the parents that were only asked for by id."""
    names, parent_ids = {key(i["name"]) for i in items}, {i["parent_id"] for i in items}
    return [r for r in recs if r["Id"] not in parent_ids or key(r["Name"]) in names]


def parents(args, paths):
    items, recs = all_items(paths), records(args.result[0])
    wanted = {i["parent_id"] for i in items}
    bad = parent_problems(items, recs)
    bad += [f"{r['Id']}: in the read but not a parent of the write set" for r in recs
            if r["Id"] not in wanted]
    if bad:
        sys.exit("parents FAILED - write nothing:\n  " + "\n  ".join(bad))
    print(f"parents ok: {len(wanted)} partner accounts, each of the expected name and record type, "
          "none with a parent, none on hold")


def precheck_problems(items, recs):
    """No Account carries a create row's name; each link target is the one Account of that
    name, a Club, still without a parent; nothing else is in the read."""
    found_by = by_name(recs)
    wanted = {key(i["name"]) for i in items}
    bad = [f"{r['Id']}: an account this batch did not ask for is in the read (wrong file?)"
           for r in recs if key(r["Name"]) not in wanted]
    for i in items:
        found = found_by.get(key(i["name"]), [])
        if i["action"] == "create":
            if found:
                bad.append(f"{i['club_code']}: an Account of that name already exists "
                           f"({', '.join(r['Id'] for r in found)})")
        elif [r["Id"] for r in found] != [i["id"]]:
            bad.append(f"{i['club_code']}: expected exactly the pilot account {i['id']}, found "
                       f"{[r['Id'] for r in found]}")
        elif unread(found[0], "RecordTypeId", "ParentId", "OwnerId"):
            bad.append(f"{i['club_code']}: {unread(found[0], 'RecordTypeId', 'ParentId', 'OwnerId')}")
        elif found[0]["ParentId"] or found[0]["RecordTypeId"] != CLUB_RECORD_TYPE:
            bad.append(f"{i['club_code']}: the link target has a parent already or is not a Club")
    return bad


def after_problems(items, recs, created):
    """At the end: every name is carried by exactly one Account, the one the run recorded."""
    found_by = by_name(recs)
    ours = {r["club_code"]: r["sf_account_id"] for r in created if r["action"] in ("create", "link")}
    bad = []
    for i in items:
        found = [r["Id"] for r in found_by.get(key(i["name"]), [])]
        if found != [ours.get(i["club_code"])]:
            bad.append(f"{i['club_code']}: the accounts of that name are {found}, the run recorded "
                       f"{ours.get(i['club_code'])}")
    return bad


def precheck_all(args, paths):
    """All names at once, one saved read per chunk of `soql --all`, in order. Before the run:
    only the link targets exist. With --after: one Account per name, the recorded one."""
    items = all_items(paths)
    chunks = chunks_of(items, args.chunk)
    if len(args.result) != len(chunks) or len({os.path.realpath(p) for p in args.result}) != len(chunks):
        sys.exit(f"precheck --all takes one saved read per chunk of `soql --all --chunk {args.chunk}`, "
                 f"in order, each file once: {len(chunks)} chunks, {len(args.result)} files given")
    created = read_created(paths)
    bad, existing = [], 0
    for n, (chunk, path) in enumerate(zip(chunks, args.result)):
        recs = records(path)
        named = named_records(chunk, recs)
        found = parent_problems(chunk, recs)
        found += after_problems(chunk, named, created) if args.after else precheck_problems(chunk, named)
        bad += [f"chunk {n}: {b}" for b in found]
        existing += len(named)
    if bad:
        sys.exit("precheck of all names FAILED" + ("" if args.after else " - write nothing")
                 + ":\n  " + "\n  ".join(bad))
    if args.after:
        print(f"all names ok after the run: {len(items)} names in {len(chunks)} chunks, each carried by "
              "exactly one Account, the one in created_accounts.csv")
    else:
        print(f"precheck of all names ok: {len(items)} names in {len(chunks)} chunks, each read with its "
              f"parents; {existing} existing accounts, all of them the "
              f"{sum(i['action'] == 'link' for i in items)} link targets (Club, no parent)")


def precheck(args, paths):
    if args.all:
        return precheck_all(args, paths)
    if len(args.result) != 1:
        sys.exit("precheck --batch takes one saved read (the query `soql --batch N` prints)")
    result = args.result[0]
    n, log = args.batch, read_log(paths)
    items = batch_items(paths, n)
    check_state(paths, log)
    creates = [i for i in items if i["action"] == "create"]
    state, opened = batch_state(log, n)
    if state == "closed":
        sys.exit(f"batch {n} is written and verified already: go on with batch {n + 1}")
    earlier = [b for b in range(n) if batch_state(log, b)[0] != "closed"]
    if earlier:
        sys.exit(f"batch {earlier[0]} is not verified yet: finish it before batch {n}")
    if state == "open" and saved_second(result) <= stamp_seconds(opened):
        sys.exit(f"batch {n} was prechecked at {opened} and this read is not newer: if the writes "
                 "were made, read again and run `verify`; if not, read again and repeat `precheck`")
    if log and saved_second(result) <= stamp_seconds(log[-1]["when_utc"]):
        sys.exit(f"this read is not newer than the last step of the run ({log[-1]['when_utc']}): read again")
    created = read_created(paths)
    done = {r["club_code"] for r in created}
    again = [i["club_code"] for i in items if i["club_code"] in done]
    if again:
        sys.exit(f"batch {n}: {again} are in created_accounts.csv already: read the names again "
                 "and run `verify`, do not write them twice")
    if creates and args.club_count is None:
        sys.exit("a batch with creates needs --club-count (the answer of the `soql --count` query): "
                 "it shows an account that exists although the read does not name it")
    recs = records(result)
    bad = parent_problems(items, recs) + precheck_problems(items, named_records(items, recs))
    if args.club_count is not None and args.club_count != BASELINE_CLUBS + made_count(created):
        bad.append(f"Salesforce has {args.club_count} Club accounts; {BASELINE_CLUBS} pilot + "
                   f"{made_count(created)} recorded were expected: an account exists that this run "
                   "does not know (a write already made? a submission? somebody else?)")
    if bad:
        sys.exit(f"batch {n} precheck FAILED - write nothing:\n  " + "\n  ".join(bad))
    before = read_before(paths)
    for i in items:
        if i["action"] == "link" and i["id"] not in before:       # the first image wins
            rec = next(r for r in recs if r["Id"] == i["id"])
            before[i["id"]] = {f: rec.get(f) for f in ("Name", "RecordTypeId", "ParentId", "OwnerId")}
    tmp = paths.before + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(before, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, paths.before)
    log_event(paths, n, "open")
    print(f"batch {n} precheck ok: {len(items)} rows, {len({i['parent_id'] for i in items})} parents "
          f"present, {sum(i['action'] == 'link' for i in items)} link targets as expected; the batch is open")


def verify(args, paths):
    """After a batch: exactly one Account per name, the Name character for character,
    RecordType Club, ParentId as sent; for creates the Description and the ids the connector
    returned; for links the owner and the name as they were before. Whatever the run made is
    recorded, under whatever name it is stored."""
    n, log = args.batch, read_log(paths)
    items = batch_items(paths, n)
    check_state(paths, log)
    creates = [i for i in items if i["action"] == "create"]
    state, opened = batch_state(log, n)
    if state != "open":
        sys.exit(f"batch {n} is {state or 'not prechecked'}: `verify` follows `precheck` and the writes")
    if saved_second(args.result) <= stamp_seconds(opened):
        sys.exit(f"this read is not newer than the precheck of batch {n} ({opened}): read again")
    if creates and args.club_count is None:
        sys.exit("a batch with creates needs --club-count (the answer of the `soql --count` query)")
    if creates and not args.ids and not args.no_ids:
        sys.exit("a batch with creates needs --ids (the ids the connector returned, one per line), "
                 "or --no-ids when an id was not returned or was lost with the session")
    returned = returned_ids(args.ids) if args.ids else set()
    all_recs = records(args.result)
    recs = named_records(items, all_recs)
    found_by, before = by_name(recs), read_before(paths)
    wanted = {key(i["name"]) for i in items}
    described = {i["body"]["Description"]: i for i in all_items(paths) if i["action"] == "create"}
    blank = {"batch": n, "seq": "", "region": "", "club_code": "", "action": "create"}
    bad, good = [], []                                 # good: (item, record, action, note)
    for rec in recs:                                   # under a name this batch did not send
        if key(rec["Name"]) in wanted:
            continue
        item = described.get(rec.get("Description"))
        if item or rec["Id"] in returned:
            good.append((item or blank, rec, "create" if item else "found-unconfirmed",
                         "stored under a Name this batch did not send"))
            bad.append(f"{rec['Id']}: made by this run but stored under another Name than the one sent")
        else:
            bad.append(f"{rec['Id']}: an account this batch did not ask for is in the read (wrong file?)")
    for i in items:
        found = found_by.get(key(i["name"]), [])
        sent = i["body"]
        if i["action"] == "create":
            if len(found) != 1:
                bad.append(f"{i['club_code']}: {len(found)} Accounts carry the name (want 1)"
                           + (f": {', '.join(r['Id'] for r in found)}" if found else ""))
                good += [(i, r, "create" if r.get("Description") == sent["Description"]
                          else "found-unconfirmed", "duplicate") for r in found]
                continue
            rec, wrong = found[0], []
            ours = rec.get("Description") == sent["Description"]
            if rec["Name"] != sent["Name"]:
                wrong.append("stored Name differs from the one sent")
            if not ours:
                wrong.append("Description differs (is this the account this plan made?)")
            if rec.get("RecordTypeId") != CLUB_RECORD_TYPE:
                wrong.append("RecordType is not Club")
            if rec.get("ParentId") != sent["ParentId"]:
                wrong.append(f"ParentId is {rec.get('ParentId')}, sent {sent['ParentId']}")
            bad += [f"{i['club_code']}: {w}" for w in wrong]
            # it exists, so it is recorded - as ours only when it carries our Description
            good.append((i, rec, "create" if ours else "found-unconfirmed", "; ".join(wrong)))
        else:
            was = before.get(i["id"])
            if [r["Id"] for r in found] != [i["id"]]:
                bad.append(f"{i['club_code']}: the Account of that name is not exactly the pilot account")
            elif was is None:
                bad.append(f"{i['club_code']}: no before-image (precheck saves it): not verifiable")
            elif unread(found[0], "RecordTypeId", "ParentId", "OwnerId"):
                bad.append(f"{i['club_code']}: {unread(found[0], 'RecordTypeId', 'ParentId', 'OwnerId')}")
            elif found[0]["Name"] != was["Name"] or found[0]["OwnerId"] != was["OwnerId"] \
                    or found[0]["RecordTypeId"] != was["RecordTypeId"]:
                bad.append(f"{i['club_code']}: Name, owner or record type changed with the update - STOP")
            elif found[0]["ParentId"] != sent["ParentId"]:
                bad.append(f"{i['club_code']}: ParentId is {found[0]['ParentId']}, sent {sent['ParentId']}")
            else:
                good.append((i, found[0], "link", ""))
    if args.ids:
        have = {rec["Id"] for i, rec, _, _ in good if i["action"] == "create"}
        if returned != have:
            bad.append(f"the connector returned {len(returned)} ids and the read found {len(have)} "
                       f"accounts of this run: returned but not read {sorted(returned - have)}, read "
                       f"but not returned {sorted(have - returned)}")
        for sf_id in sorted(returned - have):          # it exists somewhere: the rollback file knows it
            good.append((blank, {"Id": sf_id, "Name": ""}, "returned-unread",
                         "returned by the connector; read again with `soql --batch N --ids`"))
    created = read_created(paths)
    rows_by_id = {r["sf_account_id"]: r for r in created}
    stamp = now()
    for i, rec, action, note in good:
        was = before.get(rec["Id"], {})
        row = {"when_utc": stamp, "batch": i["batch"], "seq": i["seq"], "action": action,
               "region": i["region"], "club_code": i["club_code"], "sf_account_id": rec["Id"],
               "sf_account_name": rec["Name"], "parent_id": rec.get("ParentId") or "",
               "previous_parent_id": (was.get("ParentId") or "") if action == "link" else "",
               "note": note}
        if rec["Id"] in rows_by_id:
            row["when_utc"] = rows_by_id[rec["Id"]]["when_utc"]
            rows_by_id[rec["Id"]].update({k: str(v) for k, v in row.items()})
        else:
            created.append(row)
            rows_by_id[rec["Id"]] = row
    in_read = {r["Id"] for r in all_recs}
    for row in created:          # recorded for this batch under a name of it, and not there any more
        if str(row["batch"]) == str(n) and row["action"] in ("create", "found-unconfirmed") \
                and key(row["sf_account_name"]) in wanted and row["sf_account_id"] not in in_read:
            row["note"] = f"was {row['action']}; not in the read of {stamp}"
            row["action"] = "gone"
    write_created(paths, created)
    made, gone = made_count(created), sum(r["action"] == "gone" for r in created)
    if args.club_count is not None and args.club_count != BASELINE_CLUBS + made:
        diff = args.club_count - BASELINE_CLUBS - made
        bad.append(f"Salesforce has {args.club_count} Club accounts; {BASELINE_CLUBS} pilot + {made} "
                   "recorded were expected: "
                   + (f"{diff} more - an account exists that this run does not know" if diff > 0 else
                      f"{-diff} fewer - a recorded account is not a Club account any more, or the "
                      "count is of another moment"))
    confirmed = sum(1 for i, _, action, note in good if action in ("create", "link") and not note)
    print(f"batch {n}: {confirmed} of {len(items)} confirmed; created_accounts.csv has {len(created)} "
          f"rows ({made} created, {len(created) - made - gone} linked, {gone} gone)")
    if bad:
        sys.exit(f"batch {n} verify FAILED - stop and look before writing more:\n  " + "\n  ".join(bad))
    log_event(paths, n, "closed")
    print(f"batch {n} verify ok; the batch is closed")


def totals(args, paths):
    """All Club accounts (the `soql --totals` query) against the write set,
    created_accounts.csv, the run log and the link targets' before-images."""
    recs = [r for path in args.result for r in records(path)]
    items, log = all_items(paths), read_log(paths)
    batches = load_batches(paths)
    created = {r["sf_account_id"]: r for r in read_created(paths)}
    live = {i: r for i, r in created.items() if r["action"] != "gone"}
    before = read_before(paths)
    by_id = {r["Id"]: r for r in recs}
    want = {key(i["name"]): i for i in items}
    held = hold_codes(paths)
    untouched = ON_HOLD_ACCOUNTS | {r["already_in_sf"] for r in rows(paths)
                                    if r["club_code"] in held and r["already_in_sf"].strip()}
    matched, problems = 0, []
    sf_partner, sf_region = collections.Counter(), collections.Counter()
    owners = collections.Counter()
    if len(by_id) != len(recs):
        problems.append("one account is in the read twice: give each saved page once")
    if len(recs) >= 1000:
        problems.append("the read hit its LIMIT: it may be cut")
    problems += [f"batch {b} is not closed" for b in range(len(batches)) if batch_state(log, b)[0] != "closed"]
    for stay in sorted(untouched - set(by_id)):
        problems.append(f"pilot account {stay} (on hold) is not among the Club accounts")
    for rec in recs:
        if rec.get("RecordTypeId") != CLUB_RECORD_TYPE:
            problems.append(f"{rec['Id']}: not a Club record (use the query `soql --totals` prints)")
        if rec["Id"] in untouched:
            if rec.get("ParentId"):
                problems.append(f"pilot account {rec['Id']} (on hold) has a parent now")
            continue
        item = want.get(key(rec["Name"]))
        if not item:
            problems.append(f"Club account {rec['Id']} is not in the write set")
            continue
        matched += 1
        code = item["club_code"]
        if rec.get("ParentId") != item["parent_id"]:
            problems.append(f"{code}: ParentId differs from the CSV")
        if rec["Id"] not in live:
            problems.append(f"{code}: id {rec['Id']} is missing from created_accounts.csv")
        if item["action"] == "create":
            if rec["Name"] != item["name"] or rec.get("Description") != item["body"]["Description"]:
                problems.append(f"{code}: Name or Description is not what was sent")
            owners[(rec.get("OwnerId"), rec.get("CreatedById"))] += 1
        else:
            was = before.get(rec["Id"]) or {}
            if rec["Id"] != item["id"] or rec["Name"] != was.get("Name") or rec.get("OwnerId") != was.get("OwnerId"):
                problems.append(f"{code}: the linked pilot account's id, name or owner changed")
        sf_partner[rec.get("ParentId")] += 1
        sf_region[item["region"]] += 1
    names = collections.Counter(key(r["Name"]) for r in recs)
    problems += [f"{n} Club accounts share one name" for n in names.values() if n > 1]
    problems += [f"{i['club_code']}: no Club account of that name" for i in items
                 if key(i["name"]) not in names]
    problems += [f"created_accounts.csv id {i} is not a Club account any more"
                 for i in live if i not in by_id]
    problems += [f"created_accounts.csv row {r['club_code'] or r['sf_account_id']} is {r['action']} ({r['note']})"
                 for r in live.values() if r["action"] not in ("create", "link") or r["note"]]
    if len(owners) > 1 or any(None in pair for pair in owners):
        problems.append(f"the created accounts have {len(owners)} owner/creator pairs (want one, both read)")
    if len(recs) != len(items) + len(untouched):
        problems.append(f"{len(recs)} Club accounts; the write set plus the {len(untouched)} "
                        f"left alone is {len(items) + len(untouched)}")
    csv_partner = collections.Counter(i["parent_id"] for i in items)
    csv_region = collections.Counter(i["region"] for i in items)
    print(f"Club accounts in Salesforce: {len(recs)} | in the write set: {len(items)} | "
          f"matched: {matched} | recorded ids: {len(live)} | gone: {len(created) - len(live)}")
    for (owner, creator), n in owners.items():
        print(f"created accounts: {n} owned by {owner}, created by {creator}")
    print("by region (Salesforce/CSV):",
          ", ".join(f"{r} {sf_region[r]}/{csv_region[r]}" for r in sorted(csv_region)))
    differ = {p for p in set(csv_partner) | set(sf_partner) if csv_partner[p] != sf_partner[p]}
    print(f"by partner: {len(csv_partner)} partners in the CSV, {len(sf_partner)} in Salesforce, "
          f"{len(differ)} with a different club count")
    partner_name = {i["parent_id"]: i["partner"] for i in items}
    for p in sorted(csv_partner, key=lambda p: partner_name[p].casefold()):
        print(f"  {partner_name[p]}: {sf_partner[p]}/{csv_partner[p]}"
              + ("  <-- differs" if p in differ else ""))
    if problems:
        sys.exit("totals FAILED:\n  " + "\n  ".join(problems))
    print("totals ok")


def pickers(_args, paths, client=None):
    """Read-only: every write-set name must be an option of its region's live Club picker,
    character for character; the picker's calcValues must be its options in order (what
    question 5 receives; form_status.py checks that question 5 is fed from it); and the picker
    may offer nothing this list does not know. A name that is also a line of a roster on that
    form is reported (a roster artefact), not failed."""
    sys.path.insert(0, REPO)
    from glow import forms, jotform
    from glow.sync import PICKER_NAME, picker_calc_values
    if client is None:
        api_key = os.environ.get("JOTFORM_API_KEY")
        if not api_key:
            sys.exit("JOTFORM_API_KEY is not in the environment (RUNBOOK, Credentials)")
        client = jotform.Client(api_key)
    items, rs = all_items(paths), rows(paths)
    same = [r for r in rs if r["action"].startswith("create (")]
    held = hold_codes(paths)
    off_list = same + [r for r in rs if r["club_code"] in held]
    failed, compared = False, 0
    for region, form_id in forms.REGIONALS.items():
        questions = client.get(f"/form/{form_id}/questions")
        picker = next((q for q in questions.values()
                       if q.get("type") == "control_dropdown" and q.get("name") == PICKER_NAME), None)
        if not picker:
            sys.exit(f"{region}: no Club picker on the form")
        slots = (picker.get("options") or "").split("|")
        options = [o for o in slots if o]
        calc_ok = "" not in slots and (picker.get("calcValues") or "") == picker_calc_values(options)
        roster_lines = set()
        for q in questions.values():
            if q.get("type") == "control_checkbox":
                roster_lines |= {key(o) for o in (q.get("options") or "").split("|") if o}
        mine = [i for i in items if i["region"] == region]
        compared += len(mine)
        exact, lower = set(options), collections.Counter(key(o) for o in options)
        missing = [i["club_code"] for i in mine if key(i["name"]) not in lower]
        case_only = [i["club_code"] for i in mine if i["name"] not in exact and key(i["name"]) in lower]
        twice = [i["club_code"] for i in mine if lower[key(i["name"])] > 1]
        person = [i["club_code"] for i in mine if key(i["name"]) in roster_lines]
        known = ({key(i["name"]) for i in mine}
                 | {key(r[c]) for r in off_list if r["region"] == region
                    for c in ("club_name", "sf_account_name")})
        outside = [o for o in options if key(o) not in known]
        print(f"{region}: picker {len(options)} options, calcValues "
              f"{'= options' if calc_ok else 'DIFFER (or an empty option)'}; write set {len(mine)}: exact "
              f"{len(mine) - len(missing) - len(case_only)}, case-only {len(case_only)} {case_only}, "
              f"not on the picker {len(missing)} {missing}, on it twice {len(twice)} {twice}; also a "
              f"roster line {len(person)} {person}; options this list does not know {len(outside)} {outside}")
        failed = failed or bool(missing or case_only or twice or outside) or not calc_ok
    if compared != len(items):
        sys.exit(f"pickers FAILED: {len(items) - compared} write-set rows are in no form region")
    if failed:
        sys.exit("pickers FAILED: a name the form cannot send, calcValues out of line, or a picker "
                 "option this list does not know (a new or renamed club)")
    print("pickers ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=DEFAULT_DIR,
                    help="the prep folder (default: data/sf_prep_2026-09-30); a rehearsal folder "
                         "belongs under data/ or outside the checkout")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("build")
    p.add_argument("--created-on", default="2026-09-30",
                   help="the date in each Description: the day the registry was exported")
    p.add_argument("--first-create", default=FIRST_CREATE,
                   help="club code of the single first create (a name with an apostrophe)")
    p.add_argument("--first-link", default=FIRST_LINK, help="club code of the single first link")
    p.add_argument("--first-accent", default=FIRST_ACCENT,
                   help="club code of the single create that proves accented letters")
    p.set_defaults(fn=build)
    sub.add_parser("pickers").set_defaults(fn=pickers)
    p = sub.add_parser("soql")
    which = p.add_mutually_exclusive_group(required=True)
    which.add_argument("--batch", type=int, help="the names of one batch and its parents")
    which.add_argument("--all", action="store_true", help="every name of the write set, in chunks")
    which.add_argument("--parents", action="store_true", help="the parent (partner) accounts by id")
    which.add_argument("--totals", action="store_true", help="every Club account")
    which.add_argument("--count", action="store_true", help="the number of Club accounts")
    p.add_argument("--chunk", type=int, default=50, choices=range(1, 151), metavar="1..150")
    p.add_argument("--ids", help="with --batch, after the writes: also read the ids in this file")
    p.set_defaults(fn=soql)
    p = sub.add_parser("bodies")
    p.add_argument("--batch", type=int, required=True)
    p.add_argument("--preview", action="store_true", help="print a batch that is not open, for reading only")
    p.set_defaults(fn=bodies)
    p = sub.add_parser("parents")
    p.add_argument("--result", required=True, nargs=1, help="the saved read of `soql --parents`")
    p.set_defaults(fn=parents)
    p = sub.add_parser("precheck")
    which = p.add_mutually_exclusive_group(required=True)
    which.add_argument("--batch", type=int)
    which.add_argument("--all", action="store_true", help="all names at once (no batch is opened)")
    p.add_argument("--result", required=True, nargs="+", help="the saved read(s); --all: one per chunk, in order")
    p.add_argument("--chunk", type=int, default=50, choices=range(1, 151), metavar="1..150",
                   help="with --all: the chunk size `soql --all` was run with")
    p.add_argument("--after", action="store_true",
                   help="with --all, at the end: one Account per name, the recorded one")
    p.add_argument("--club-count", type=int, help="the answer of the `soql --count` query")
    p.set_defaults(fn=precheck)
    p = sub.add_parser("verify")
    p.add_argument("--batch", type=int, required=True)
    p.add_argument("--result", required=True, help="the saved read made after the writes")
    p.add_argument("--ids", help="file with the ids the connector returned for the creates")
    p.add_argument("--no-ids", action="store_true", help="an id was not returned or was lost (recovery)")
    p.add_argument("--club-count", type=int, help="the answer of the `soql --count` query")
    p.set_defaults(fn=verify)
    p = sub.add_parser("totals")
    p.add_argument("--result", required=True, nargs="+", help="the saved read(s) of `soql --totals`")
    p.set_defaults(fn=totals)
    args = ap.parse_args()
    args.fn(args, Paths(args.dir))


if __name__ == "__main__":
    main()
