#!/usr/bin/env python3
"""Read-only check that Salesforce's session-timing formula fields on Attendance_Batch__c compute what
glow/session_timing.py defines (ticket #100; the fields are deployed by task #101; docs/DECISIONS.md,
2026-10-23):

  Submitted_At__c           the CreatedDate of a live Jotform batch (Creator__c `Jotform`), else blank
  Submission_Delay_Days__c  the UTC day of Submitted_At__c minus Attendance_Date__c, else blank
  Session_Month__c          `2026-10`
  Session_Week__c           `2026-10 week 2` (days 1-7 week 1 ... 29-31 week 5)

  python3 tools/sf_session_timing.py check --vpn-off                       # batches since 2026-09-01
  python3 tools/sf_session_timing.py check --vpn-off --since 2026-10-01

One SOQL query with explicit fields (never Contact_IDs__c, the girls' names); every batch's four values
are compared with the ones expected from its Creator__c, CreatedDate and Attendance_Date__c - the
expected delay from the expected submission time, never from Salesforce's own Submitted_At__c. Prints
`checked N batches; differ: ... -> OK`, or `-> DIFFER` with up to 10 lines of batch Name, field,
Salesforce's value and the expected one, and exits 1. Batch Names and counts only; nothing is written.
Salesforce access is glow/salesforce.py's (the CLI's login, VPN off).
"""
import argparse
import os
import re
import sys
from datetime import date, datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow import session_timing as st   # noqa: E402
from glow.salesforce import Org, Refused, add_vpn_flag, require_vpn_off   # noqa: E402

SOBJECT = "Attendance_Batch__c"
FIELDS = ["Submitted_At__c", "Submission_Delay_Days__c", "Session_Month__c", "Session_Week__c"]
SELECT = ["Id", "Name", "Creator__c", "CreatedDate", "Attendance_Date__c", *FIELDS]
BATCHES = f"SELECT {', '.join(SELECT)} FROM {SOBJECT} WHERE Attendance_Date__c >= {{since}} ORDER BY Name"
DEFAULT_SINCE = "2026-09-01"                 # the forms' launch
SHOWN = 10                                   # difference lines printed; all are counted
DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def since_day(text):
    """argparse type: a calendar day YYYY-MM-DD (it goes into the SOQL, so nothing else)."""
    try:
        if not DAY.fullmatch(text):
            raise ValueError
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a day YYYY-MM-DD") from None


def timestamp(value):
    """A REST Date/Time (`2026-10-06T01:30:00.000+0000`, `...Z`, with or without milliseconds) -> an aware
    datetime; None for blank; ValueError for anything else."""
    if value is None or value == "":
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(value, fmt)
        except (TypeError, ValueError):
            pass
    raise ValueError(f"not a Date/Time: {value!r}")


def number(value):
    """A REST Number (float or int) -> float; None for blank; ValueError for anything else."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"not a number: {value!r}")
    return float(value)


def shown(value):
    """A value as the difference lines show it: a whole float without its `.0`, blank as `blank`."""
    if value is None or value == "":
        return "blank"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def same_time(actual, expected):
    try:
        return timestamp(actual) == expected
    except ValueError:
        return False


def same_number(actual, expected):
    try:
        return number(actual) == expected
    except ValueError:
        return False


def expected_values(b):
    """The four values glow/session_timing.py gives a batch, from its Creator__c, CreatedDate and day."""
    try:
        created, day = timestamp(b.get("CreatedDate")), date.fromisoformat(b.get("Attendance_Date__c") or "")
    except (TypeError, ValueError):
        raise Refused(f"{b.get('Name')}: its CreatedDate or Attendance_Date__c is not a date Salesforce gives "
                      "- look at the batch in Salesforce") from None
    submitted = st.submitted_at(b.get("Creator__c"), created)
    return {"Submitted_At__c": submitted, "Submission_Delay_Days__c": st.delay_days(submitted, day),
            "Session_Month__c": st.session_month(day), "Session_Week__c": st.session_week(day)}


def differences(b):
    """[(field, Salesforce's value, the expected one)] for one batch."""
    want, out = expected_values(b), []
    for field in FIELDS:
        actual, expected = b.get(field), want[field]
        if field == "Submitted_At__c":
            same = same_time(actual, expected)
        elif field == "Submission_Delay_Days__c":
            same = same_number(actual, expected)
        else:
            same = actual == expected
        if not same:
            out.append((field, actual, expected))
    return out


def not_deployed_hint(stop):
    """Salesforce refuses (HTTP 400, INVALID_FIELD) a query that names a field the org does not have."""
    if "HTTP 400" in str(stop):
        return Refused(f"{stop} - are the session-timing fields ({', '.join(FIELDS)}) deployed on {SOBJECT}? "
                       "Most likely not deployed yet (task #101 deploys them), or this login cannot read them")
    return stop


def cmd_check(args, org):
    try:
        batches = org.query(BATCHES.format(since=args.since.isoformat()))
    except Refused as stop:
        raise not_deployed_hint(stop) from None
    counts, lines = {field: 0 for field in FIELDS}, []
    for b in batches:
        for field, actual, expected in differences(b):
            counts[field] += 1
            lines.append(f"  {b.get('Name')} {field}: Salesforce {shown(actual)}, expected {shown(expected)}")
    differ = any(counts.values())
    print(f"checked {len(batches)} batches; differ: " + ", ".join(f"{f} {counts[f]}" for f in FIELDS)
          + (" -> DIFFER" if differ else " -> OK"))
    for line in lines[:SHOWN]:
        print(line)
    if len(lines) > SHOWN:
        print(f"  ... and {len(lines) - SHOWN} more")
    if differ:
        sys.exit(1)


def main(argv=None, org=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 allow_abbrev=False)
    ap.add_argument("--org", default="glow", help="the Salesforce CLI alias (default: glow)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    check = sub.add_parser("check", allow_abbrev=False)
    check.add_argument("--since", type=since_day, default=since_day(DEFAULT_SINCE),
                       help=f"batches whose Attendance_Date__c is this day or later (default {DEFAULT_SINCE})")
    add_vpn_flag(check)
    args = ap.parse_args(argv)
    try:
        require_vpn_off(args)
        cmd_check(args, org or Org(args.org))
    except Refused as stop:
        sys.exit(str(stop))


if __name__ == "__main__":
    main()
