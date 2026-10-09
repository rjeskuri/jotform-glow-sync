#!/usr/bin/env python3
"""One-off correction in Salesforce: the attendance batches whose Module__c is not one of the module
dropdowns' options - a Spanish rendering of the option that a browser's page translation wrote into
question 98 before the module calcValues were live - and the Attendance__c rows under them, which
the processor copied the batch's module onto (docs/plans/2026-10-06-module-selection.md, (b)).

The ground truth is the Jotform submission the batch came from: the stored answer of the module
dropdown its Year answer names (tools/backfill_resolve.py copied_fields), read the same way the
September back-fill read it. A batch is paired with exactly one submission - the same club (question
5), attendance date, question 98, year and session, on the form of the batch's region, created within
three hours of the batch - or it is listed as UNMATCHED and left alone.

  python3 tools/fix_module_values.py --vpn-off                       # dry run: Jotform GET, Salesforce reads
  python3 tools/fix_module_values.py --vpn-off --apply --limit 1     # Ryan's go: the first batch and its rows
  python3 tools/fix_module_values.py --vpn-off --apply               # the rest, one record per request, each read back
  python3 tools/fix_module_values.py --undo data/module_fix_2026-10/ledger.csv --vpn-off --apply   # put `old` back

Salesforce is read and written through the CLI's login as tools/sf_backfill.py does (the token
never on a command line); every read of a record is an explicit-field SOQL query - never the
names list (Contact_IDs__c) or the status message, never GET /sobjects/<type>/<id>. The ledger
(data/module_fix_2026-10/ledger.csv, owner only) holds ids, module names and outcomes. What is
printed: ids, club names, dates, statuses, candidate counts and module names. The key comes from
JOTFORM_API_KEY.
"""
import argparse
import csv
import datetime
import json
import os
import sys
import zoneinfo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
from glow import forms                                              # noqa: E402
from glow.cli import api_key                                       # noqa: E402
from glow.jotform import Client, JotformError                       # noqa: E402
from glow.sync import CLUB_NAME, MODULE_ID, MODULES, WEEK_ID, YEAR  # noqa: E402
from glow.salesforce import add_vpn_flag, as_int, positive, require_vpn_off   # noqa: E402
from backfill_resolve import PAGE, answer_of, attendance_date, copied_fields   # noqa: E402
from sf_backfill import Org, Refused, now, open_private, quoted, within        # noqa: E402

DEFAULT_DIR = os.path.join(REPO, "data", "module_fix_2026-10")
SINCE = "2026-09-01"                         # batches created from this day on (UTC), the launch
WINDOW = datetime.timedelta(hours=3)         # a submission's created_at against the batch's CreatedDate
JOTFORM_CLOCK = zoneinfo.ZoneInfo("America/New_York")     # created_at as Jotform gives it: US Eastern
# Account__r.Parent.Region__c (the partner account's region, read 2026-10-06) -> the attendance form
SF_REGION_FORM = {"Africa": forms.REGIONALS["Africa"], "Asia": forms.REGIONALS["Asia"],
                  "South America": forms.REGIONALS["Latin America"], "North America": forms.REGIONALS["U.S"]}
BATCH_FIELDS = ("Id, Account_Name__c, Account__c, Account__r.Parent.Region__c, Attendance_Date__c, Module__c, "
                "Module_Week__c, Module_Year__c, Processing_Status__c, Creator__c, CreatedDate")
LEDGER_COLS = ["when_utc", "batch_id", "record_id", "sobject", "old", "new", "outcome"]
WRITTEN = {"written", "check"}               # a correction --undo reverses (check: 204 answered, the value is unknown)


# ---- the canonical options and the batches ------------------------------------------------------
def canonical_options(client):
    """{year: [option, ...]} of the template's module dropdowns, as the sync reads them."""
    questions = client.get(f"/form/{forms.TEMPLATE}/questions")
    out = {}
    for year, qid in MODULES.items():
        question = (questions or {}).get(qid) or {}
        options = [o.strip() for o in (question.get("options") or "").split("|") if o.strip()]
        if question.get("type") != "control_dropdown" or not options:
            raise Refused(f"the template's module dropdown q{qid} (year {year}) is not a dropdown with options - "
                          "nothing is canonical until it is")
        out[year] = options
    return out


def read_batches(org, since):
    return org.query(f"SELECT {BATCH_FIELDS} FROM Attendance_Batch__c WHERE CreatedDate >= {since}T00:00:00Z "
                     "ORDER BY CreatedDate")


def read_rows(org, batch_id):
    return org.query(f"SELECT Id, Module__c FROM Attendance__c WHERE Attendance_Batch__c = {quoted(batch_id)}")


def read_one(org, sobject, record_id):
    return org.query(f"SELECT Id, Module__c FROM {sobject} WHERE Id = {quoted(record_id)}")


def region_of(batch):
    return ((batch.get("Account__r") or {}).get("Parent") or {}).get("Region__c")


# ---- the Jotform side ----------------------------------------------------------------------------
def window_of(created):
    """(from, to) in Jotform's clock, three hours either side of a batch's CreatedDate."""
    when = datetime.datetime.strptime(created, "%Y-%m-%dT%H:%M:%S.%f%z").astimezone(JOTFORM_CLOCK)
    return tuple((when + sign * WINDOW).strftime("%Y-%m-%d %H:%M:%S") for sign in (-1, 1))


def fetch(client, form_id, window=None):
    """The submissions of a form, paged: the ones created inside `window` (Jotform's filter, which
    glow.jotform.Client.url encodes), or the whole form."""
    params = {}
    if window:
        params["filter"] = json.dumps({"created_at:gt": window[0], "created_at:lt": window[1]})
    seen, out, offset = set(), [], 0
    while True:
        page = client.get(f"/form/{form_id}/submissions", limit=PAGE, offset=offset, **params)
        if not isinstance(page, list) or not all(isinstance(s, dict) and s.get("id") for s in page):
            raise Refused(f"form {form_id}: the submissions answer is not a list of submissions with ids")
        for sub in page:
            if sub["id"] not in seen:
                seen.add(sub["id"])
                out.append(sub)
        if len(page) < PAGE:
            break
        offset += PAGE
    if window is None:                       # the whole form: its own count is the check, as the resolver's
        reported = int((client.get(f"/form/{form_id}") or {}).get("count") or 0)
        if len(out) < reported:
            raise Refused(f"form {form_id}: fetched {len(out)} submissions but the form reports {reported} - run again")
    return out


class Jotform:
    """The forms' questions (each form's read once) and submissions (one window per batch, or the four forms whole)."""

    def __init__(self, client, all_forms=False):
        self.client, self.all_forms, self.questions, self.whole = client, all_forms, {}, None

    def questions_of(self, form_id):
        if form_id not in self.questions:
            self.questions[form_id] = self.client.get(f"/form/{form_id}/questions") or {}
        return self.questions[form_id]

    def candidates(self, batch):
        """[(form id, submission)] the batch may have come from, or a reason there are none."""
        if self.all_forms:
            if self.whole is None:
                self.whole = [(fid, sub) for fid in forms.REGIONALS.values() for sub in fetch(self.client, fid)]
            return self.whole, None
        form_id = SF_REGION_FORM.get(region_of(batch))
        if not form_id:
            return [], f"region {region_of(batch)!r} names no form"
        window = window_of(batch["CreatedDate"])
        return [(form_id, sub) for sub in fetch(self.client, form_id, window)
                if window[0] < str(sub.get("created_at")) < window[1]], None


def matches(sub, batch):
    """The submission is the batch's: same club (question 5), date, question 98, year and session."""
    year, week = as_int(answer_of(sub, YEAR)), as_int(answer_of(sub, WEEK_ID))
    return (answer_of(sub, CLUB_NAME) == batch["Account_Name__c"] and attendance_date(sub) == batch["Attendance_Date__c"]
            and answer_of(sub, MODULE_ID) == batch["Module__c"] and year is not None and week is not None
            and year == as_int(batch["Module_Year__c"]) and week == as_int(batch["Module_Week__c"]))


def pair(batch, jotform, canonical):
    """The batch with its English module, or with why it stays UNMATCHED. Only a pairing by the
    whole rule corrects a batch: anything less is listed and left alone."""
    entry = dict(batch, rows=None, new=None, why=None, form_id=None, candidates=0)
    if as_int(batch["Module_Year__c"]) is None or as_int(batch["Module_Week__c"]) is None:
        entry["why"] = "year or session is not a whole number"
        return entry
    found, why = jotform.candidates(batch)
    if why:
        entry["why"] = why
        return entry
    found = [(fid, sub) for fid, sub in found if matches(sub, batch)]
    entry["candidates"] = len(found)
    if len(found) != 1:
        entry["why"] = f"{len(found)} candidates"
        return entry
    form_id, sub = found[0]
    module, _ = copied_fields(sub, jotform.questions_of(form_id))
    if module is None:
        entry["why"] = "the submission's module dropdown holds no option of the form today"
    elif module not in canonical:
        entry["why"] = f"{module!r} is not a template option"
    else:
        entry["form_id"], entry["new"] = form_id, module
    return entry


def describe(entry):
    where = next((f"{r} {fid}" for r, fid in forms.REGIONALS.items() if fid == entry["form_id"]), "")
    return (f"  {entry['Id']}  {entry['Account_Name__c']}  {entry['Attendance_Date__c']}  {entry['Processing_Status__c']}"
            f"  {entry['Module__c']!r}" + (f" -> {entry['new']!r}" if entry["new"] else f"  UNMATCHED ({entry['why']})")
            + f"  ({where + ', ' if where else ''}submission {entry['candidates']} candidate(s), "
            f"year {as_int(entry['Module_Year__c'])}, session {as_int(entry['Module_Week__c'])}; {entry['rows']} rows; "
            f"created {entry['CreatedDate'][:19]} UTC)")


# ---- the ledger and the writes -------------------------------------------------------------------
def private_folder(folder):
    """The folder, created owner-only. Inside the checkout it must be under data/ (never committed)."""
    folder, data = os.path.abspath(folder), os.path.join(REPO, "data")
    if folder == data or folder.startswith(data + os.sep):
        os.makedirs(data, 0o700, exist_ok=True)       # a fresh checkout has no data/ yet, and within() needs it to exist
    if within(folder, REPO) and not within(folder, data):
        raise Refused("--dir: inside the checkout the ledger folder must be under data/ (never committed)")
    os.makedirs(folder, 0o700, exist_ok=True)
    os.chmod(folder, 0o700)
    return folder


def ledger_path(folder):
    return os.path.join(private_folder(folder), "ledger.csv")


def read_ledger(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != LEDGER_COLS:
            raise Refused(f"{path} does not start with this tool's header line: " + ",".join(LEDGER_COLS))
        return list(reader)


def last_rows(ledger):
    """record id -> its last ledger row (append-only; the last line is a record's state)."""
    out = {}
    for row in ledger:
        out[row["record_id"]] = row
    return out


def append_ledger(path, row):
    with open_private(path, "a") as fh:
        writer = csv.DictWriter(fh, fieldnames=LEDGER_COLS, lineterminator="\n")
        if os.fstat(fh.fileno()).st_size == 0:
            writer.writeheader()
        writer.writerow({col: row.get(col, "") for col in LEDGER_COLS})
        fh.flush()
        os.fsync(fh.fileno())


def write_one(org, path, batch_id, sobject, record_id, old, new, prefix=""):
    """Ledger row, PATCH, re-read, closing row. Returns the closing outcome; anything but
    `written` is a stop for the caller (nothing else is written)."""
    row = {"when_utc": now(), "batch_id": batch_id, "record_id": record_id, "sobject": sobject, "old": old, "new": new}
    append_ledger(path, dict(row, outcome=prefix + "open"))
    status, _ = org.update(sobject, record_id, {"Module__c": new})
    if status != 204:
        outcome = f"{prefix}failed_{status}"
        why = f"Salesforce did not take the write (HTTP {status}; 0 = no answer, the outcome is unknown)"
    else:
        try:
            back = read_one(org, sobject, record_id)
            why = "the write answered 204 but the value read back differs"
        except Refused as stop:                  # 204 answered, then no re-read: the value is unknown, the row closes as check
            back, why = [], f"the write answered 204 but the re-read did not ({stop})"
        outcome = prefix + ("written" if len(back) == 1 and back[0].get("Module__c") == new else "check")
    append_ledger(path, dict(row, when_utc=now(), outcome=outcome))
    if outcome != prefix + "written":
        raise Refused(f"{record_id} ({sobject}, batch {batch_id}): {why} - STOPPED, nothing more written; the ledger "
                      f"{os.path.relpath(path, REPO)} says what was")
    return outcome


def apply_entry(org, path, entry):
    rows = read_rows(org, entry["Id"])
    if len(rows) != entry["rows"]:
        raise Refused(f"{entry['Id']}: {len(rows)} rows now, {entry['rows']} when planned - STOPPED before writing")
    if any(r.get("Module__c") != entry["Module__c"] for r in rows):   # the processor copies the batch's module
        raise Refused(f"{entry['Id']}: a row under it carries another module than the batch - STOPPED before "
                      "writing; look at the batch in Salesforce")
    write_one(org, path, entry["Id"], "Attendance_Batch__c", entry["Id"], entry["Module__c"], entry["new"])
    for row in rows:
        write_one(org, path, entry["Id"], "Attendance__c", row["Id"], entry["Module__c"], entry["new"])
    after = read_rows(org, entry["Id"])
    if len(after) != len(rows) or any(r.get("Module__c") != entry["new"] for r in after):
        raise Refused(f"{entry['Id']}: {len(after)} rows after the writes, {len(rows)} before, or one still carries "
                      "another module - STOPPED; look at the batch in Salesforce")
    print(f"  {entry['Id']}  {entry['Account_Name__c']}  {entry['Attendance_Date__c']}  {entry['Processing_Status__c']}"
          f"  {entry['Module__c']!r} -> {entry['new']!r}: batch written and read back equal; {len(rows)} rows written "
          f"and read back equal; rows {len(rows)} before, {len(after)} after")


# ---- the two runs --------------------------------------------------------------------------------
def cmd_correct(args, org, client):
    options = canonical_options(client)
    canonical = {o for year in options.values() for o in year}
    print(f"canonical modules: {len(canonical)} (template {forms.TEMPLATE}: "
          + ", ".join(f"q{MODULES[y]} {len(options[y])}" for y in MODULES) + " options)")
    batches = read_batches(org, args.since)
    blank = sum(1 for b in batches if not b.get("Module__c"))       # a partner-reported aggregate: no module, nothing to translate
    wrong = [b for b in batches if b.get("Module__c") and b["Module__c"] not in canonical]
    scope = f"; without a module, not in scope: {blank}" if blank else ""
    if not wrong:
        print(f"nothing to correct: 0 of {len(batches)} batches since {args.since} carry a module outside the "
              f"{len(canonical)} canonical options{scope}")
        return
    jotform = Jotform(client, all_forms=args.all_forms)
    entries = []
    for batch in wrong:
        entry = pair(batch, jotform, canonical)
        entry["rows"] = len(read_rows(org, batch["Id"]))
        entries.append(entry)
    statuses = {}
    for e in entries:
        statuses[e["Processing_Status__c"]] = statuses.get(e["Processing_Status__c"], 0) + 1
    print(f"batches since {args.since}: {len(batches)}; module not a canonical option: {len(entries)} ("
          + ", ".join(f"{n} {s}" for s, n in sorted(statuses.items())) + f"); rows under them: "
          f"{sum(e['rows'] for e in entries)}{scope}")
    for entry in entries:
        print(describe(entry))
    matched = [e for e in entries if e["new"]]
    unmatched = len(entries) - len(matched)
    if args.limit is not None:
        matched = matched[:args.limit]
    if not args.apply:
        print(f"would write: {len(matched)} batches, {sum(e['rows'] for e in matched)} rows"
              + (f"; UNMATCHED, left alone: {unmatched}" if unmatched else "")
              + "   (dry run - nothing written; --apply --vpn-off after Ryan's go)")
        return
    path = ledger_path(args.dir)
    for entry in matched:
        apply_entry(org, path, entry)
    print(f"written and read back: {len(matched)} batches, {sum(e['rows'] for e in matched)} rows"
          + (f"; UNMATCHED, left alone: {unmatched}" if unmatched else "") + f"; ledger {os.path.relpath(path, REPO)}")


def put_back(row):
    """(what the record holds, what to write back) when a record's last ledger row calls for an undo, else
    None. A correction (`written`, `check`) is reversed. An undo's own row runs the other way already
    (old = the English value, new = the original), so an undo that did not take (`undo_failed_<status>`,
    `undo_check`) is repeated as it stands; `undo_written` is done, `open` and `undo_open` are unknown."""
    outcome = row["outcome"]
    if outcome in WRITTEN:
        return row["new"], row["old"]
    if outcome.startswith("undo_") and outcome not in ("undo_open", "undo_written"):
        return row["old"], row["new"]
    return None


def cmd_undo(args, org):
    path = os.path.abspath(args.undo)
    if not os.path.isfile(path):
        raise Refused(f"--undo: there is no ledger {args.undo}")
    private_folder(os.path.dirname(path))        # the undo's own rows go into the same file: the same rule as --dir
    last = last_rows(read_ledger(path))
    todo = [(row, put_back(row)) for row in last.values() if put_back(row)]
    for row in last.values():
        if not put_back(row):
            print(f"  nothing to undo: {row['record_id']} ({row['sobject']}) is {row['outcome']}"
                  + (" (the write's outcome is unknown: look at the record in Salesforce)" if row["outcome"].endswith("open") else ""))
    if not todo:
        print("nothing to undo")
        return
    if not args.apply:
        for row, (holds, back) in todo:
            print(f"  would put back {row['record_id']} ({row['sobject']}, batch {row['batch_id']}): {holds!r} -> {back!r}")
        print(f"would put back: {len(todo)} records   (dry run - nothing written; --apply --vpn-off after Ryan's go)")
        return
    for row, (holds, back) in todo:
        write_one(org, path, row["batch_id"], row["sobject"], row["record_id"], holds, back, prefix="undo_")
        print(f"  put back {row['record_id']} ({row['sobject']}): {back!r}, read back equal")
    print(f"put back and read back: {len(todo)} records; ledger {os.path.relpath(path, REPO)}")


def main(argv=None, org=None, client=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 allow_abbrev=False)
    ap.add_argument("--apply", action="store_true", help="write to Salesforce (needs Ryan's go)")
    add_vpn_flag(ap)
    ap.add_argument("--limit", type=positive, help="correct only the first N matched batches (their rows included)")
    ap.add_argument("--since", default=SINCE, metavar="YYYY-MM-DD", help=f"batches created from this day on (default {SINCE})")
    ap.add_argument("--all-forms", action="store_true",
                    help="look for each batch's submission on all four forms, whole (default: the form of the batch's "
                         "region, inside a 6-hour window)")
    ap.add_argument("--undo", metavar="LEDGER", help="put `old` back for every record this ledger says was written")
    ap.add_argument("--dir", default=DEFAULT_DIR, help="where the ledger goes (default: data/module_fix_2026-10)")
    ap.add_argument("--org", default="glow", help="the Salesforce CLI alias (default: glow)")
    args = ap.parse_args(argv)
    try:
        if datetime.date.fromisoformat(args.since).isoformat() != args.since:
            raise ValueError
    except ValueError:
        sys.exit("--since: a date like 2026-09-01")
    try:
        talks = not args.undo or args.apply          # the undo's dry run reads the ledger only
        if talks:
            require_vpn_off(args)
        org = org or (Org(args.org) if talks else None)
        if args.undo:
            cmd_undo(args, org)
            return
        if client is None:
            client = Client(api_key(" - docs/RUNBOOK.md, \"Credentials\""), retries=3)
        cmd_correct(args, org, client)
    except (Refused, JotformError) as stop:
        sys.exit(str(stop))


if __name__ == "__main__":
    main()
