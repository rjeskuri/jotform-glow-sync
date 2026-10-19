#!/usr/bin/env python3
"""Copy the three Salesforce-reporting partners' Monthly Max into the attendance data, once a month
(ticket #60, docs/plans/2026-10-19-partner-monthly-max.md).

Education and English for You, Tumaini La Maisha and Ng'aa Maskani report through Salesforce only.
Their monthly figure is the one their Monthly Report already carries: "Monthly Max"
(DHIS2__c.Monthly_Total__c, roughly the month's unique girls). This tool writes it as one
Attendance_Batch__c per partner per month:

  Account_Name__c     the partner's Account name exactly (the processor attaches the batch to that account)
  Attendance_Date__c  the last day of the month
  Girls_Present__c    the Monthly Max
  Creator__c          Partner report
  Contact_IDs__c      empty - no names
  enable_fuzzy_matching__c  false

  python3 tools/sf_partner_monthly.py --vpn-off                         # dry run, last month
  python3 tools/sf_partner_monthly.py --month 2026-09 --vpn-off         # dry run, September 2026
  python3 tools/sf_partner_monthly.py --month 2026-09 --apply --vpn-off --limit 1   # Ryan's go: one write
  python3 tools/sf_partner_monthly.py --month 2026-09 --apply --vpn-off             # the rest

Run it after the three Monthly Reports are filed (about the 12th of the next month). A partner is
refused - reported, no write, the run ends non-zero, the other partners still planned and written -
when it has no Monthly Report for the month or more than one, a Monthly Max that is blank, 0,
negative or not whole, no single Account carrying its name, more than one Success Partner report
batch on its account and day, or - when it needs an insert - a Success batch of another creator on
its account and day (the processor's per-Account-and-date lock would answer Failed 'Duplicate'). A partner with one such batch already: the same count is skipped, a
different one is an update of Girls_Present__c alone (a PATCH runs none of the processor), shown
old -> new. The current month, or a later one, is refused before Salesforce is asked.

--apply: in the fixed partner order, one insert or update per request, each read back (Success, on
the partner's account, the count); --limit N counts writes only. ledger.csv (data/sf_partner_monthly/,
owner only, never committed) holds every write's batch id, partner, month, date and counts: the
rollback deletes an inserted batch by its id and sets an updated one back to its old count. The tool
reads ids, names of accounts, statuses, creators, dates and counts - never Contact_IDs__c, a status
message or a girl's name. Salesforce access is glow/salesforce.py's (the CLI's login).
"""
import argparse
import calendar
import datetime
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow.private_files import Ledger, private_folder, rel, stamp   # noqa: E402
from glow.salesforce import Org, Refused, add_vpn_flag, as_int, positive, quoted, require_vpn_off, sf_match   # noqa: E402

DEFAULT_DIR = os.path.join(REPO, "data", "sf_partner_monthly")
PARTNERS = ("Education and English for You", "Tumaini La Maisha", "Ng'aa Maskani")   # the write order
SOBJECT, FIELD, OK, CREATOR = "Attendance_Batch__c", "Girls_Present__c", "Success", "Partner report"
MONTH = re.compile(r"(\d{4})-(0[1-9]|1[0-2])")
LEDGER_COLS = ["when_utc", "month", "partner", "account_id", "date", "action", "batch_id", "old", "new",
               "read_back", "outcome"]


def month_arg(text):
    """argparse type: YYYY-MM -> (year, month)."""
    m = MONTH.fullmatch(text or "")
    if not m:
        raise argparse.ArgumentTypeError(f"{text!r} is not a month like 2026-09")
    return int(m.group(1)), int(m.group(2))


def this_month():
    """The current month on the earlier of the Mac's clock and UTC: a month that is still current on
    either is not over."""
    local, utc = datetime.date.today(), datetime.datetime.now(datetime.timezone.utc).date()
    day = min(local, utc)
    return day.year, day.month


def before(year, month):
    first = datetime.date(year, month, 1) - datetime.timedelta(days=1)
    return first.year, first.month


def last_day(year, month):
    return f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


def count_of(value):
    """A count as Salesforce gives it (a double) -> int, or None when blank or not whole."""
    return None if value is None or value == "" else as_int(value)


# ---- the plan ------------------------------------------------------------------------------------
def accounts(org):
    """partner -> its Account id; a partner whose name no single Account carries is absent. The
    processor matches Account_Name__c against every Account, ignoring case, so a second Account
    with the name would make the batch's account a guess."""
    found = org.query("SELECT Id, Name FROM Account WHERE Name IN (" + ", ".join(quoted(p) for p in PARTNERS) + ")")
    out = {}
    for partner in PARTNERS:
        same = [a for a in found if sf_match(partner, a.get("Name"))]
        if len(same) == 1 and same[0]["Name"] == partner:
            out[partner] = same[0]["Id"]
    return out


def reports(org, acc_ids, year, month):
    """account id -> the Monthly Max values of its Monthly Reports for the month. YearMonth__c is
    compared by its digits here, so its field type (text or number) does not matter to the query."""
    if not acc_ids:
        return {}
    wanted, out = f"{year:04d}{month:02d}", {}
    for r in org.query("SELECT Id, Account__c, YearMonth__c, Monthly_Total__c FROM DHIS2__c WHERE Account__c IN ("
                       + ", ".join(quoted(a) for a in acc_ids) + ")"):
        value = r.get("YearMonth__c")
        digits = str(as_int(value)) if as_int(value) is not None else re.sub(r"\D", "", str(value or ""))
        if digits == wanted:
            out.setdefault(r["Account__c"], []).append(r.get("Monthly_Total__c"))
    return out


def batches(org, acc_ids, day):
    """account id -> its Success batches dated `day`, any creator (id, creator, count). The
    processor's lock is per Account and date: any Success there makes an insert Failed 'Duplicate'."""
    if not acc_ids:
        return {}
    out = {}
    for b in org.query(f"SELECT Id, Account__c, Creator__c, Girls_Present__c FROM {SOBJECT} WHERE Account__c IN ("
                       + ", ".join(quoted(a) for a in acc_ids) + f") AND Attendance_Date__c = {day} "
                       f"AND Processing_Status__c = {quoted(OK)}"):
        out.setdefault(b["Account__c"], []).append(b)
    return out


def plan(org, year, month):
    """One entry per partner, in the write order: action insert | update | skip | refused."""
    day, tag = last_day(year, month), f"{year:04d}-{month:02d}"
    acc = accounts(org)
    found = reports(org, list(acc.values()), year, month)
    there = batches(org, list(acc.values()), day)
    entries = []
    for partner in PARTNERS:
        e = {"partner": partner, "account_id": acc.get(partner, ""), "date": day, "month": tag,
             "batch_id": "", "old": None, "new": None}
        entries.append(e)
        if partner not in acc:
            e.update(action="refused", why="no single Salesforce Account carries this name exactly")
            continue
        values = found.get(acc[partner], [])
        if len(values) != 1:
            e.update(action="refused", why=f"{len(values)} Monthly Reports for {tag}, one expected"
                     + (" - is it filed yet?" if not values else " - which is right is decided in Salesforce"))
            continue
        total = count_of(values[0])
        if total is None or total < 1:
            e.update(action="refused", why=f"the Monthly Max for {tag} is {'blank' if values[0] in (None, '') else values[0]}, "
                     "not a whole number above 0")
            continue
        e["new"] = total
        on_day = there.get(acc[partner], [])
        mine = [b for b in on_day if b.get("Creator__c") == CREATOR]
        if len(mine) > 1:
            e.update(action="refused", why=f"{len(mine)} {OK} {CREATOR} batches dated {day} - one at most; "
                     "remove the extra one in Salesforce")
            continue
        if not mine:
            if on_day:
                e.update(action="refused", why=f"{len(on_day)} other {OK} batch(es) on the partner account dated {day} - "
                         "the processor would answer Failed 'Duplicate'; look at them in Salesforce")
            else:
                e["action"] = "insert"
            continue
        old = count_of(mine[0].get(FIELD))
        e.update(batch_id=mine[0]["Id"], old=old)
        if old is None and mine[0].get(FIELD) not in (None, ""):
            e.update(action="refused", why=f"its {CREATOR} batch dated {day} holds {mine[0].get(FIELD)!r}, not a whole number")
        else:
            e["action"] = "skip" if old == total else "update"
    return entries


def describe(e):
    if e["action"] == "refused":
        return f"  {e['partner']}: REFUSED - {e['why']}"
    if e["action"] == "skip":
        return f"  {e['partner']}: Monthly Max {e['new']} already in place ({e['date']}) - unchanged, skipped"
    if e["action"] == "update":
        old = "blank" if e["old"] is None else e["old"]
        return f"  {e['partner']}: update the {CREATOR} batch dated {e['date']}: {old} -> {e['new']}"
    return f"  {e['partner']}: insert a {CREATOR} batch dated {e['date']}: Monthly Max {e['new']}"


# ---- the writes ----------------------------------------------------------------------------------
def read_back(org, batch_id):
    found = org.query(f"SELECT Id, Account__c, Processing_Status__c, {FIELD} FROM {SOBJECT} WHERE Id = {quoted(batch_id)}")
    return found[0] if len(found) == 1 else None


def write_one(org, ledger, e):
    """Ledger row, the insert or the PATCH, read back, closing row. Refused when Salesforce does not
    take it or it does not read back as sent."""
    row = {"when_utc": stamp(), "month": e["month"], "partner": e["partner"], "account_id": e["account_id"],
           "date": e["date"], "action": e["action"], "batch_id": e["batch_id"],
           "old": "" if e["old"] is None else e["old"], "new": e["new"]}
    ledger.append(dict(row, outcome="open"))
    if e["action"] == "insert":
        status, answer = org.insert(SOBJECT, {"Account_Name__c": e["partner"], "Attendance_Date__c": e["date"],
                                              FIELD: e["new"], "Creator__c": CREATOR, "Contact_IDs__c": "",
                                              "enable_fuzzy_matching__c": False})
        batch_id = answer.get("id") if status == 201 and isinstance(answer, dict) else None
    else:
        status, _ = org.update(SOBJECT, e["batch_id"], {FIELD: e["new"]})
        batch_id = e["batch_id"] if status == 204 else None
    if not batch_id:
        ledger.append(dict(row, when_utc=stamp(), outcome=f"failed_{status}"))
        raise Refused(f"{e['partner']}: Salesforce did not take the {e['action']} (HTTP {status}; 0 = no answer, the "
                      f"outcome is unknown: look for a {CREATOR} batch dated {e['date']} on the partner's account) - "
                      f"STOPPED, nothing more written; the ledger {rel(ledger.path)} says what was")
    row["batch_id"] = batch_id
    try:
        back = read_back(org, batch_id)
    except Refused as stop:
        back, lost = None, f"the re-read did not answer ({stop})"
    else:
        lost = "the batch is not there"
    wrong = []
    if back is None:
        wrong.append(lost)
    else:
        if back.get("Processing_Status__c") != OK:
            wrong.append(f"its status is {back.get('Processing_Status__c')}")
        if back.get("Account__c") != e["account_id"]:
            wrong.append("it is on another account")
        if count_of(back.get(FIELD)) != e["new"]:
            wrong.append(f"{FIELD} reads back as {count_of(back.get(FIELD))}, not {e['new']}")
    got = count_of(back.get(FIELD)) if back else None
    ledger.append(dict(row, when_utc=stamp(), read_back="" if got is None else got,
                       outcome="check" if wrong else ("inserted" if e["action"] == "insert" else "updated")))
    if wrong:
        raise Refused(f"{e['partner']}: the {e['action']} answered but " + "; ".join(wrong) + " - STOPPED, nothing more "
                      f"written; look at the batch in Salesforce (its id is in {rel(ledger.path)}: the rollback)")


def main(argv=None, org=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 allow_abbrev=False)
    ap.add_argument("--month", type=month_arg, help="the month, YYYY-MM (default: last month)")
    ap.add_argument("--apply", action="store_true", help="write to Salesforce (needs Ryan's go)")
    ap.add_argument("--limit", type=positive, help="write at most N batches (skipped and refused partners do not count)")
    ap.add_argument("--dir", default=DEFAULT_DIR, help="the folder for ledger.csv (default: data/sf_partner_monthly)")
    ap.add_argument("--org", default="glow", help="the Salesforce CLI alias (default: glow)")
    add_vpn_flag(ap)
    args = ap.parse_args(argv)
    try:
        current = this_month()
        year, month = args.month or before(*current)
        if (year, month) >= current:
            raise Refused(f"{year:04d}-{month:02d} is not over yet: its Monthly Reports are filed in the month after "
                          "(about the 12th) - give a past month")
        require_vpn_off(args)
        folder = private_folder(args.dir, repo=REPO)
        org = org or Org(args.org)
        entries = plan(org, year, month)
        print(f"{year:04d}-{month:02d}: the three partners' Monthly Max as {CREATOR} batches dated {last_day(year, month)}")
        for e in entries:
            print(describe(e))
        refused = [e["partner"] for e in entries if e["action"] == "refused"]
        todo = [e for e in entries if e["action"] in ("insert", "update")]
        if not args.apply:
            print(f"dry run: nothing was written ({len(todo)} to write; --apply --vpn-off writes, with Ryan's go)")
        else:
            ledger = Ledger(os.path.join(folder, "ledger.csv"), LEDGER_COLS)
            ledger.read()                       # a ledger with another header is a refusal before any write
            written = 0
            for e in todo[:args.limit] if args.limit is not None else todo:
                write_one(org, ledger, e)
                written += 1
                print(f"  {e['partner']}: {'inserted' if e['action'] == 'insert' else 'updated'} {e['new']}, read back equal")
            left = len(todo) - written
            print(f"written and read back: {written}" + (f"; left by --limit: {left}" if left else "")
                  + (f"; ledger {rel(ledger.path)}" if written else ""))
        if refused:
            raise Refused(f"refused: {', '.join(refused)} - nothing written for "
                          + ("it" if len(refused) == 1 else "them") + "; fix it in Salesforce and run again")
    except Refused as stop:
        sys.exit(str(stop))


if __name__ == "__main__":
    main()
