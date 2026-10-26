#!/usr/bin/env python3
"""Write the anonymous Apex that runs RecordFlagBatch, the batch that sets the "Duplicate Record" and
"Obsolete Record" flags on Account and Contact (ticket #85; docs/plans/2026-10-23-sf-record-flag-batch.md;
RUNBOOK "Duplicate and obsolete records in Salesforce", The flagging batch).

Read only. It reads the Google Sheet's exports and Salesforce and writes one file, the script; running
the script (the Salesforce CLI's anonymous Apex, `sf apex run -o glow -f <script>`) is Ryan's, behind
the live gate, after the dry run and his confirmation of its counts.

  python3 tools/sf_record_flags.py --sobject Account --mode dryRun --roster data/roster_<date>.csv --partners data/partners_<date>.csv --out data/sf_record_flags_<date>/account_dryRun.apex --vpn-off
  python3 tools/sf_record_flags.py --sobject Contact --mode dryRun --out data/sf_record_flags_<date>/contact_dryRun.apex --vpn-off

Account (decision 1a, Ryan 2026-10-23): two of the agreed obsolete criteria are facts the sheet alone
holds, so the script carries their Account ids. The Club accounts of the clubs deactivated in the
Roster (no active row, by glow.sync's own rule: "Deactivating a club"), each matched to its account as
the attendance processor matches question 5 - the plain name, or `<club> - <partner>` when a Club
account carries it ("Club names two partners share"), compared with glow.salesforce.sf_match; of two
Club accounts of the name, the club's is the one under its partner's account (glow/sf_partners.csv).
And the accounts of the partners marked `no` in the Partners tab's `jotform` column ("Clubs that do
not use Jotform"). A deactivated club with no account or with twins the parent does not tell apart,
a marked partner missing from the map, and a Partners export without the `jotform` column each stop
the run naming what to fix: nothing is guessed. Before every Account script, dryRun, flag and clear alike,
the tool runs the household-naming guard (Ryan, 2026-10-26): one SOQL count of the NPSP Households Settings
rows with Automatic Household Naming on, `SELECT COUNT() FROM npo02__Households_Settings__c WHERE
npo02__Advanced_Household_Naming__c = true` - every row, the org default's, a profile's or a user's - since
with naming on an Account update would rename the partners' households; it writes no script while the
count is not 0.
    Database.executeBatch(new RecordFlagBatch('Account', '<mode>', new Set<Id>{...}, new Set<Id>{...}), 200);

Contact: the criteria are Salesforce's own, so the script is the two-argument call. Before writing it
the tool runs the guard (Ryan, 2026-10-23, option a): three SOQL counts of the Contacts the NPSP and
Volunteers workflow rules would act on at a flag-only update - a blank Email with a Work, Home or
Alternate e-mail set (the rule Preferred_Email__c rewrites Email), a blank Phone with a Work, Home,
Mobile or Other phone set (Preferred_Phone__c rewrites Phone), a Volunteers web signup dated today
(the signup rule mails) - and writes no script while any count is not 0.
    Database.executeBatch(new RecordFlagBatch('Contact', '<mode>'), 200);

Modes: dryRun (the batch counts and writes nothing), flag, clear (the rollback: both flags false). The
output and the script carry counts and record ids only: never a girl's name, and no club's or
partner's name but in a refusal naming what to fix.
"""
import argparse
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow.salesforce import (CLUB_RECORD_TYPE, PARTNERS, SF_ID, Org, Refused, add_vpn_flag, plain,   # noqa: E402
                             read_partners, require_vpn_off, sf_match)
from glow.sync import (JOTFORM_COL, SF_NAME_SEP, _partners_rows, partners_marker_present,   # noqa: E402
                       read_partners_csv, roster_pairs)
from glow.text import key   # noqa: E402

SOBJECTS = ("Account", "Contact")
MODES = ("dryRun", "flag", "clear")
SCOPE = 200                   # records per execute: the ticket's batch size
ACCOUNT_SOQL = "SELECT Id, Name, RecordTypeId, ParentId FROM Account"
# the guard (Ryan, 2026-10-23): the Contacts the NPSP rules Preferred_Email__c and Preferred_Phone__c would
# rewrite on any edit, and the Volunteers signup rule would mail about - counts only, no record read
EMAIL_FIELDS = ("npe01__WorkEmail__c", "npe01__HomeEmail__c", "npe01__AlternateEmail__c")
PHONE_FIELDS = ("npe01__WorkPhone__c", "HomePhone", "MobilePhone", "OtherPhone")
SIGNUP_FIELD = "GW_Volunteers__Volunteer_Last_Web_Signup_Date__c"
GUARD_SOQL = {
    "email": "SELECT COUNT() FROM Contact WHERE Email = null AND ("
             + " OR ".join(f"{f} != null" for f in EMAIL_FIELDS) + ")",
    "phone": "SELECT COUNT() FROM Contact WHERE Phone = null AND ("
             + " OR ".join(f"{f} != null" for f in PHONE_FIELDS) + ")",
    "volunteer": f"SELECT COUNT() FROM Contact WHERE {SIGNUP_FIELD} = TODAY",
}
# what each count is, as the output says it, and why it must be 0: each line names its own kind only
GUARD_WHAT = {
    "email": ("Contacts with a blank Email and a Work, Home or Alternate e-mail set",
              "the NPSP rule Preferred_Email__c would rewrite Email on a flag-only update"),
    "phone": ("Contacts with a blank Phone and a Work, Home, Mobile or Other phone set",
              "the NPSP rule Preferred_Phone__c would rewrite Phone on a flag-only update"),
    "volunteer": ("Contacts with a Volunteers web signup dated today",
                  "the Volunteer Signup workflow rule would send mail"),
}
# the household-naming guard (Ryan, 2026-10-26): with NPSP's Automatic Household Naming on, an Account update
# renames the partners' households. A hierarchy custom setting: every row counts, whoever owns it
NAMING_SOQL = ("SELECT COUNT() FROM npo02__Households_Settings__c "
               "WHERE npo02__Advanced_Household_Naming__c = true")
RUNBOOK = 'RUNBOOK "Duplicate and obsolete records in Salesforce"'


# ---- the sheet-held criteria -------------------------------------------------------------------------
def deactivated_club_ids(roster_csv, accounts, partners):
    """The Account ids of the clubs deactivated in the Roster export (no active row: glow.sync.roster_pairs),
    each matched to its Club account (`accounts`: plain records with Id, Name, RecordTypeId, ParentId;
    `partners`: glow.salesforce.read_partners' map). No repeats. A club with no account, or with twins the
    parent does not tell apart, is refused naming the club."""
    clubs = [a for a in accounts if a.get("RecordTypeId") == CLUB_RECORD_TYPE]
    out = {}
    for (partner, club), active in sorted(roster_pairs(roster_csv).items()):
        if not active:
            out.setdefault(club_account(partner, club, clubs, partners)["Id"], None)
    return list(out)


def club_account(partner, club, clubs, partners):
    """The Club account of a Roster club: the one named as question 5 sends the club (`<club> - <partner>`
    when a Club account carries that name, else the plain name), compared as the attendance processor
    compares (sf_match: the Roster's name trimmed, capitals ignored one character to one, the Account's
    name as it is). Of two of the name, the one under the club's partner's account."""
    long_name = club + SF_NAME_SEP + partner
    found = [a for a in clubs if sf_match(long_name, a.get("Name") or "")]
    if not found:
        found = [a for a in clubs if sf_match(club, a.get("Name") or "")]
    if not found:
        raise Refused(f"'{club}' ({partner}) is deactivated in the Roster but no Club account carries its name as "
                      f"question 5 sends it, '{club}' or '{long_name}': give the club its account, or fix the name "
                      f"first ({RUNBOOK}; \"Club accounts in Salesforce\")")
    if len(found) == 1:
        return found[0]
    partner_id = (partners.get(key(partner)) or (None,))[0]
    under = [a for a in found if a.get("ParentId") and a["ParentId"] == partner_id]
    if len(under) == 1:
        return under[0]
    ids = ", ".join(sorted(a["Id"] for a in (under or found)))
    raise Refused(f"'{club}' ({partner}) is deactivated in the Roster but {len(found)} Club accounts carry its name "
                  f"and the parent does not tell them apart: {ids} - re-parent the stray first "
                  f"({RUNBOOK}; \"Club accounts in Salesforce\")")


def partner_report_partner_ids(partners_csv, partners):
    """The account ids of the partners marked `no` in a Partners-tab export's `jotform` column, read as
    glow.sync.read_partners_csv reads it; `partners` is glow.salesforce.read_partners' map. No repeats. An
    export without the column, or a marked partner missing from the map, is refused."""
    if not partners_marker_present(partners_csv):
        raise Refused(f"{partners_csv}: the Partners export has no '{JOTFORM_COL}' column, so no partner is marked and "
                      "the Salesforce-reporting partners' clubs would be judged by batches they never have: export "
                      "the Partners tab with its header (Partners!D1 is `jotform`; RUNBOOK \"Clubs that do not use "
                      "Jotform\")")
    marks = read_partners_csv(partners_csv)
    rows, header = _partners_rows(partners_csv)             # the same reader: the spelling, for a refusal
    column = header.index("partner")
    spelling = {}
    for row in rows[1:]:
        name = " ".join((row[column] if column < len(row) else "").split())
        spelling.setdefault(key(name), name)
    out = []
    for k, mark in marks.items():
        if mark != "no":
            continue
        if k not in partners:
            raise Refused(f"'{spelling.get(k, k)}' is marked {JOTFORM_COL}=no in the Partners tab but is not in "
                          "glow/sf_partners.csv: add the partner's account to the map first")
        if partners[k][0] not in out:
            out.append(partners[k][0])
    return out


# ---- the Apex the tool writes ------------------------------------------------------------------------
def id_set(ids):
    return "new Set<Id>{" + ", ".join(f"'{i}'" for i in ids) + "}"


def apex_script(sobject, mode, deactivated_ids=(), partner_ids=()):
    """The anonymous Apex, one statement: for Account the four-argument call (the deactivated clubs' ids,
    then the jotform=no partners' ids), for Contact the two-argument one. Ids only."""
    if sobject not in SOBJECTS:
        raise Refused(f"--sobject is Account or Contact, not {sobject!r}")
    if mode not in MODES:
        raise Refused(f"--mode is {', '.join(MODES)}, not {mode!r}")
    deactivated, partners = (list(dict.fromkeys(ids)) for ids in (deactivated_ids, partner_ids))
    for i in deactivated + partners:
        if not isinstance(i, str) or not SF_ID.fullmatch(i):
            raise Refused("something that is not a Salesforce id was about to go into the script: ids only")
    if sobject == "Contact":
        if deactivated or partners:
            raise Refused("the Contact batch takes no club or partner ids: its criteria are Salesforce's own")
        return (f"// RecordFlagBatch Contact {mode} (ticket #85): the Contact criteria are Salesforce's own\n"
                f"Database.executeBatch(new RecordFlagBatch('Contact', '{mode}'), {SCOPE});\n")
    return (f"// RecordFlagBatch Account {mode} (ticket #85): {len(deactivated)} deactivated club(s), "
            f"{len(partners)} jotform=no partner(s); ids only\n"
            f"Database.executeBatch(new RecordFlagBatch('Account', '{mode}',\n"
            f"    {id_set(deactivated)},\n"
            f"    {id_set(partners)}), {SCOPE});\n")


# ---- the guard ----------------------------------------------------------------------------------------
def guard_counts(org):
    """{"email": n, "phone": n, "volunteer": n}: one SOQL count each (`SELECT COUNT() FROM Contact WHERE …`),
    no record read."""
    return {kind: org.count(soql) for kind, soql in GUARD_SOQL.items()}


# ---- the command line -----------------------------------------------------------------------------------
def run(args, org, partners_path):
    given = [flag for flag, value in (("--roster", args.roster), ("--partners", args.partners)) if value]
    if args.sobject == "Account":
        missing = [flag for flag in ("--roster", "--partners") if flag not in given]
        if missing:
            raise Refused(f"--sobject Account reads the sheet's exports: give {' and '.join(missing)} "
                          "(python3 tools/sheets_client.py export Roster|Partners <file>)")
    elif given:
        raise Refused(f"--sobject Contact reads Salesforce alone: {' and '.join(given)} belong to the Account run")
    require_vpn_off(args)
    org = org or Org(args.alias)
    if args.sobject == "Account":
        naming = org.count(NAMING_SOQL)
        print(f"household-naming guard: Households Settings rows with NPSP Automatic Household Naming on: {naming}")
        if naming:
            raise Refused(f"the household-naming guard refuses the Account script: {naming} Households Settings row(s) "
                          "have NPSP Automatic Household Naming on, and an Account update would rename the partners' "
                          f"households ({RUNBOOK}, The flagging batch): turn Automatic Household Naming off in NPSP "
                          "Settings, or ask Ryan, then run again")
        partner_map = read_partners(partners_path)
        partner_ids = partner_report_partner_ids(args.partners, partner_map)
        accounts = plain(org.query(ACCOUNT_SOQL))
        print(f"Accounts read from Salesforce: {len(accounts)}")
        club_ids = deactivated_club_ids(args.roster, accounts, partner_map)
        print(f"deactivated clubs in the Roster (no active row): {len(club_ids)} Club account(s)")
        for i in club_ids:
            print(f"  {i}")
        print(f"partners marked {JOTFORM_COL}=no in the Partners tab: {len(partner_ids)} account(s)")
        for i in partner_ids:
            print(f"  {i}")
        script = apex_script("Account", args.mode, club_ids, partner_ids)
    else:
        counts = guard_counts(org)
        for kind, (what, _why) in GUARD_WHAT.items():
            print(f"guard: {what}: {counts[kind]}")
        bad = [f"{counts[kind]} {what}: {why}" for kind, (what, why) in GUARD_WHAT.items() if counts[kind]]
        if bad:
            raise Refused("the Contact script is refused while a guard count is not 0 (the workflow rules below act "
                          f"on any Contact edit; {RUNBOOK}, The flagging batch):\n  "
                          + "\n  ".join(bad) + "\nfix those first, or wait for the day to pass, then run again")
        script = apex_script("Contact", args.mode)
    folder = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(folder, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(script)
    print(f"script written: {args.out} ({args.sobject}, {args.mode}); it runs with the Salesforce CLI's anonymous "
          "Apex on Ryan's go, behind the live gate:")
    print(script, end="")


def main(argv=None, org=None, partners_path=PARTNERS):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sobject", required=True, choices=SOBJECTS, help="which batch the script runs")
    ap.add_argument("--mode", required=True, choices=MODES, help="dryRun counts and writes nothing; flag; clear")
    ap.add_argument("--roster", help="a Roster export (Account only; tools/sheets_client.py export Roster ...)")
    ap.add_argument("--partners", help="a Partners-tab export (Account only; ... export Partners ...)")
    ap.add_argument("--out", required=True, help="where the script is written (data/sf_record_flags_<date>/...)")
    ap.add_argument("--alias", default="glow", help="the Salesforce CLI login (Ryan's, read only)")
    add_vpn_flag(ap)
    args = ap.parse_args(argv)
    try:
        run(args, org, partners_path)
    except Refused as stop:
        sys.exit(str(stop))


if __name__ == "__main__":
    main()
