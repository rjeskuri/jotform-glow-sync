"""When an attendance batch was submitted, and which month and week its session belongs to (ticket #100;
docs/DECISIONS.md, 2026-10-23). Ryan's answers of 2026-10-22:

- the session week is the week of the month by day: 1-7 week 1, 8-14 week 2, 15-21 week 3, 22-28 week 4,
  29-31 week 5, shown as `2026-10 week 2` (the calendar week of the session date, not the curriculum
  "Session N" in `Module_Week__c`);
- the day a batch was submitted is its UTC day; a Salesforce formula takes it as DATEVALUE(TEXT(<date/time>)),
  because TEXT() of a date/time is the UTC timestamp and DATEVALUE on the date/time itself converts in the
  org's zone (America/Los_Angeles): the first deploy's DATEVALUE(Submitted_At__c) was a day short for every
  submission between 00:00 and about 07:00 UTC, 153 of 1,123 batches (2026-10-24; DECISIONS 2026-10-24);
- there is no "big delay" threshold and no flag: the delay in days is shown and staff read it.

Only a live Jotform batch (`Creator__c` exactly `Jotform`) has a submission time: the native Jotform
Salesforce V2 integration creates the batch when the form is submitted, so its `CreatedDate` is the
submission time. The September back-fill (`Jotform back-fill ...`) and the partners' monthly batches
(`Partner report`) were created later by tools and have none.

SF_FORMULAS are the formula fields on `Attendance_Batch__c` that compute the same in Salesforce
(deployed by task #101); `tools/sf_session_timing.py check` compares the two.
"""
from datetime import timezone

JOTFORM_CREATOR = "Jotform"

SF_FORMULAS = {
    # Date/Time
    "Submitted_At__c": 'IF(Creator__c = "Jotform", CreatedDate, NULL)',
    # Number, 0 decimals; DATEVALUE(TEXT(...)) is the UTC date (DATEVALUE on the date/time: the org's zone)
    "Submission_Delay_Days__c": "IF(ISBLANK(Submitted_At__c), NULL, DATEVALUE(TEXT(Submitted_At__c)) - Attendance_Date__c)",
    # Text
    "Session_Month__c": 'TEXT(YEAR(Attendance_Date__c)) & "-" & LPAD(TEXT(MONTH(Attendance_Date__c)), 2, "0")',
    # Text
    "Session_Week__c": 'Session_Month__c & " week " & TEXT(CEILING(DAY(Attendance_Date__c) / 7))',
}


def submitted_at(creator, created_utc):
    """A batch's submission time: its CreatedDate when the live Jotform flow created it, else None."""
    return created_utc if creator == JOTFORM_CREATOR else None


def delay_days(submitted_utc, session_day):
    """Days from the session date to the UTC day of the submission (negative when submitted before the
    session day: a date typo); None without a submission time. A naive datetime is refused."""
    if submitted_utc is None:
        return None
    if submitted_utc.tzinfo is None:
        raise ValueError("delay_days needs an aware datetime (the submission time in UTC)")
    return (submitted_utc.astimezone(timezone.utc).date() - session_day).days


def session_month(day):
    """`2026-10` for any day of October 2026."""
    return f"{day.year:04d}-{day.month:02d}"


def session_week(day):
    """`2026-10 week 2` for 8-14 October 2026: days 1-7 week 1 ... 29-31 week 5."""
    return f"{session_month(day)} week {(day.day + 6) // 7}"
