#!/usr/bin/env python3
"""One-off back-fill of Girls_Present__c on Attendance_Batch__c - the count behind every Success batch
from before the field existed - and the read-only check that keeps it honest afterwards
(docs/plans/2026-10-06-attendance-totals.md, C).

The field and the processor change are deployed (2026-10-07 03:22 UTC, plan sections A and B):
since then the attendance processor sets Girls_Present__c when a Jotform batch succeeds (= the
attendance rows it created) and clears it on a Failed one; a partner-reported total is typed into
it (Creator__c 'Partner report': no names, no rows). Batches from before the deploy have it empty;
this tool fills them once, from their rows.

  plan    live, read-only: every batch's id, status, creator kind, rows and current value -> plan.csv
  set     offline from plan.csv: what would be written; --apply --vpn-off writes, one PATCH per
          batch, each read back
  check   live, read-only: Jotform Success batches whose count differs from their rows, and Success
          batches without a value - both 0 when healthy

  python3 tools/sf_girls_present.py plan --vpn-off
  python3 tools/sf_girls_present.py set                                # dry run
  python3 tools/sf_girls_present.py set --apply --vpn-off --limit 1    # Ryan's go: one batch, read back
  python3 tools/sf_girls_present.py set --apply --vpn-off              # the rest
  python3 tools/sf_girls_present.py check --vpn-off

Only a Success batch whose Girls_Present__c is empty is written (= its rows; 0 for a blank). Failed
batches stay empty, as the processor leaves them, so the field means one thing: the count behind a
success. A batch with a value is never touched - a typed aggregate survives, and a second run finds
nothing to set. Salesforce access is tools/sf_backfill.py's (the CLI's login, the token on curl's
stdin, never on a command line); it reads ids, names of batches, statuses, creators and counts -
never a girl's name, never Contact_IDs__c. plan.csv and ledger.csv live in data/sf_girls_present/
(never committed, owner only), although they hold ids and counts only.
"""
import argparse
import csv
import io
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
from glow.salesforce import add_vpn_flag, as_int, positive, require_vpn_off   # noqa: E402
from sf_backfill import Org, Refused, now, open_private, quoted, save_private, within   # noqa: E402

DEFAULT_DIR = os.path.join(REPO, "data", "sf_girls_present")
FIELD, SOBJECT, OK = "Girls_Present__c", "Attendance_Batch__c", "Success"
JOTFORM = "Jotform"                          # Creator__c of the live flow and of the back-fill ("Jotform back-fill ...")
BATCHES = f"SELECT Id, Name, Processing_Status__c, Creator__c, {FIELD} FROM {SOBJECT} ORDER BY Name"
ROWS = "SELECT Attendance_Batch__c, COUNT(Id) n FROM Attendance__c WHERE Attendance_Batch__c IN ({ids}) GROUP BY Attendance_Batch__c"
CHUNK = 200                                  # batch ids per ROWS query: an aggregate query is one page (2,000 groups), no next page
JOTFORM_SUCCESS = (f"SELECT Id, {FIELD} FROM {SOBJECT} WHERE Processing_Status__c = '{OK}' "
                   f"AND Creator__c LIKE '{JOTFORM}%'")
WITHOUT_VALUE = f"SELECT COUNT() FROM {SOBJECT} WHERE Processing_Status__c = '{OK}' AND {FIELD} = null"
PLAN_COLS = ["batch_id", "name", "status", "creator", "rows", "value"]
LEDGER_COLS = ["when_utc", "batch_id", "rows", "read_back", "outcome"]


class Paths:
    """plan.csv and ledger.csv in one owner-only folder; inside the checkout it must be under data/."""

    def __init__(self, folder):
        folder, data = os.path.abspath(folder), os.path.join(REPO, "data")
        if folder == data or folder.startswith(data + os.sep):
            os.makedirs(data, 0o700, exist_ok=True)   # a fresh checkout has no data/ yet, and within() needs it to exist
        if within(folder, REPO) and not within(folder, data):
            raise Refused("--dir: inside the checkout the folder must be under data/ (never committed)")
        os.makedirs(folder, 0o700, exist_ok=True)
        os.chmod(folder, 0o700)
        self.plan, self.ledger = os.path.join(folder, "plan.csv"), os.path.join(folder, "ledger.csv")


def rel(path):
    return os.path.relpath(path, REPO)


def one_batch(org, batch_id):
    return org.query(f"SELECT Id, Processing_Status__c, {FIELD} FROM {SOBJECT} WHERE Id = {quoted(batch_id)}")


def row_counts(org, batch_ids):
    """batch id -> its Attendance__c rows, for the batches named (a batch with none is absent). One GROUP BY
    per CHUNK ids: Salesforce gives an aggregate query a single page and no way to read more (documented at
    2,000 groups; not tried against this org), and the batches pass that within a year at the live rate."""
    ids, counts = sorted(set(batch_ids)), {}
    for start in range(0, len(ids), CHUNK):
        for r in org.query(ROWS.format(ids=", ".join(quoted(b) for b in ids[start:start + CHUNK]))):
            counts[r["Attendance_Batch__c"]] = int(r["n"])
    return counts


def creator_kind(text):
    return "jotform" if str(text or "").startswith(JOTFORM) else ("other" if text else "")


def as_count(value):
    """Girls_Present__c as Salesforce gives it (a double, or None when empty) -> int or None;
    anything but a whole number is a refusal."""
    if value is None or value == "":
        return None
    number = as_int(value)
    if number is None:
        raise Refused(f"{FIELD} holds {value!r}, not a whole number - look at it in Salesforce")
    return number


def no_field_hint(stop):
    """A read that Salesforce refuses for the field gets the likely causes named: the field is deployed
    (2026-10-07 03:22 UTC) with read access on the System Administrator profile only, so an org without
    it, or a login on another profile, gets HTTP 400 for any query that names it."""
    if "HTTP 400" in str(stop):
        return Refused(f"{stop} - is {FIELD} deployed on {SOBJECT}? (in production since 2026-10-07, readable on "
                       "the System Administrator profile only: is this login on it? "
                       "docs/plans/2026-10-06-attendance-totals.md, A)")
    return stop


# ---- plan ----------------------------------------------------------------------------------------
def tally(entries):
    """(the Success entries without a value, the lines that describe the plan)."""
    statuses = {}
    for e in entries:
        statuses[e["status"]] = statuses.get(e["status"], 0) + 1
    todo = [e for e in entries if e["status"] == OK and e["value"] == ""]
    with_rows = [e for e in todo if int(e["rows"])]
    lines = [f"batches: {len(entries)} (" + ", ".join(f"{n} {s}" for s, n in sorted(statuses.items(), key=lambda x: -x[1]))
             + f"); to set: {len(todo)} {OK} batches with no Girls present ({len(with_rows)} with rows, "
             f"{len(todo) - len(with_rows)} with none, {sum(int(e['rows']) for e in todo):,} rows); "
             f"already set: {sum(1 for e in entries if e['status'] == OK and e['value'] != '')}; "
             f"Failed batches are left empty: {sum(1 for e in entries if e['status'] != OK)}"]
    return todo, lines


def cmd_plan(args, paths, org):
    try:
        batches = org.query(BATCHES)
        counts = row_counts(org, [b["Id"] for b in batches])
    except Refused as stop:
        raise no_field_hint(stop) from None
    entries = [{"batch_id": b["Id"], "name": b["Name"], "status": b["Processing_Status__c"],
                "creator": creator_kind(b.get("Creator__c")), "rows": counts.get(b["Id"], 0),
                "value": "" if as_count(b.get(FIELD)) is None else as_count(b.get(FIELD))} for b in batches]
    text = io.StringIO()
    writer = csv.DictWriter(text, fieldnames=PLAN_COLS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(entries)
    save_private(paths.plan, text.getvalue())
    _, lines = tally([{k: str(v) for k, v in e.items()} for e in entries])
    print("\n".join(lines))
    print(f"plan: {rel(paths.plan)} (ids and counts; never committed)")


def read_plan(path):
    if not os.path.exists(path):
        raise Refused(f"there is no plan yet: `plan --vpn-off` writes {rel(path)}")
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != PLAN_COLS:
            raise Refused(f"{rel(path)} is not this tool's plan (header {','.join(PLAN_COLS)} expected) - run plan again")
        return list(reader)


# ---- set -----------------------------------------------------------------------------------------
def append_ledger(path, row):
    with open_private(path, "a") as fh:
        writer = csv.DictWriter(fh, fieldnames=LEDGER_COLS, lineterminator="\n")
        if os.fstat(fh.fileno()).st_size == 0:
            writer.writeheader()
        writer.writerow({col: row.get(col, "") for col in LEDGER_COLS})
        fh.flush()
        os.fsync(fh.fileno())


def set_one(org, paths, entry):
    """Re-read, ledger row, PATCH, re-read, closing row. True when written; False when the batch has
    a value by now (left alone); Refused at the first thing not as planned."""
    batch_id, rows = entry["batch_id"], int(entry["rows"])
    found = one_batch(org, batch_id)
    if len(found) != 1:
        raise Refused(f"{entry['name']} {batch_id} is no longer in Salesforce - STOPPED; run plan again")
    if found[0]["Processing_Status__c"] != OK:
        raise Refused(f"{entry['name']} {batch_id} is {found[0]['Processing_Status__c']} now, {OK} when planned - STOPPED; "
                      "run plan again")
    if as_count(found[0].get(FIELD)) is not None:
        return False
    row = {"when_utc": now(), "batch_id": batch_id, "rows": rows}
    append_ledger(paths.ledger, dict(row, outcome="open"))
    status, _ = org.update(SOBJECT, batch_id, {FIELD: rows})
    if status != 204:
        append_ledger(paths.ledger, dict(row, when_utc=now(), outcome=f"failed_{status}"))
        raise Refused(f"{entry['name']} {batch_id}: Salesforce did not take the write (HTTP {status}; 0 = no answer, "
                      f"the outcome is unknown) - STOPPED, nothing more written; the ledger {rel(paths.ledger)} says what was")
    try:
        back = one_batch(org, batch_id)
        read_back = as_count(back[0].get(FIELD)) if len(back) == 1 else None
        why = f"{FIELD} reads back as {read_back!r}, not {rows}"
    except Refused as stop:                      # 204 answered, then no re-read: the value is unknown, the row closes as check
        read_back, why = None, f"the re-read did not answer ({stop})"
    outcome = "written" if read_back == rows else "check"
    append_ledger(paths.ledger, dict(row, when_utc=now(), read_back="" if read_back is None else read_back, outcome=outcome))
    if outcome != "written":
        raise Refused(f"{entry['name']} {batch_id}: the write answered 204 but {why} - STOPPED; look at the batch in Salesforce")
    return True


def cmd_set(args, paths, org):
    entries = read_plan(paths.plan)
    todo, lines = tally(entries)
    print("\n".join(lines))
    if args.limit is not None:
        todo = todo[:args.limit]
    if not args.apply:
        for entry in todo[:10]:
            print(f"  would set {entry['name']} {entry['batch_id']}: {FIELD} = {entry['rows']}")
        if len(todo) > 10:
            print(f"  ... and {len(todo) - 10} more")
        print("dry run: nothing was written (--apply writes, with Ryan's go)")
        return
    written = skipped = 0
    for entry in todo:
        if set_one(org, paths, entry):
            written += 1
            print(f"  {entry['name']} {entry['batch_id']}: {FIELD} = {entry['rows']}, read back equal")
        else:
            skipped += 1
            print(f"  {entry['name']} {entry['batch_id']}: has a value now - left alone")
    print(f"set and read back: {written}" + (f"; skipped, already has a value: {skipped}" if skipped else "")
          + f"; ledger {rel(paths.ledger)}")


# ---- check ---------------------------------------------------------------------------------------
def cmd_check(args, paths, org):
    try:
        batches, without = org.query(JOTFORM_SUCCESS), org.count(WITHOUT_VALUE)
        counts = row_counts(org, [b["Id"] for b in batches])
    except Refused as stop:
        raise no_field_hint(stop) from None
    differ = [b["Id"] for b in batches if as_count(b.get(FIELD)) is not None and as_count(b.get(FIELD)) != counts.get(b["Id"], 0)]
    healthy = not differ and not without
    print(f"check: {len(batches)} Jotform {OK} batches; differ: {len(differ)}, without a value: {without} -> "
          + ("OK" if healthy else "NOT OK"))
    for batch_id in differ[:10]:
        print(f"  differs: {batch_id}")
    if not healthy:
        sys.exit(1)


def main(argv=None, org=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 allow_abbrev=False)
    ap.add_argument("--dir", default=DEFAULT_DIR, help="the folder for plan.csv and ledger.csv (default: data/sf_girls_present)")
    ap.add_argument("--org", default="glow", help="the Salesforce CLI alias (default: glow)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    plan = sub.add_parser("plan", allow_abbrev=False)
    setter = sub.add_parser("set", allow_abbrev=False)
    setter.add_argument("--apply", action="store_true", help="write to Salesforce (needs Ryan's go)")
    setter.add_argument("--limit", type=positive, help="set only the first N batches of the plan")
    check = sub.add_parser("check", allow_abbrev=False)
    for live in (plan, setter, check):
        add_vpn_flag(live)
    args = ap.parse_args(argv)
    try:
        paths = Paths(args.dir)
        talks = args.cmd != "set" or args.apply
        if talks:
            require_vpn_off(args)
        org = org or (Org(args.org) if talks else None)
        {"plan": cmd_plan, "set": cmd_set, "check": cmd_check}[args.cmd](args, paths, org)
    except Refused as stop:
        sys.exit(str(stop))


if __name__ == "__main__":
    main()
