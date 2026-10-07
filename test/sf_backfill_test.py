#!/usr/bin/env python3
"""
Offline tests for tools/sf_backfill.py (imported by test/python_test.py, so `make py` runs
them). Everything here is fictional: clubs, girls, submission and Salesforce ids are invented.
A fake org stands in for Salesforce and follows its attendance processor where that matters:
the club is found by name or a stray one is created, the first batch per club and day wins and
a later one is stored as Failed, a batch without names is Failed "No participants submitted"
unless it carries a Girls_Present__c above 0 (an aggregate: a Success without rows), a Success
sets Girls_Present__c to the rows it created and every Failed path clears it (the processor as
deployed 2026-10-07), every new name becomes a contact, and a handled error leaves the rows made
so far behind.
"""
import contextlib
import csv
import io
import json
import os
import re
import stat
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import sf_backfill as bf                                   # noqa: E402
from sf_club_accounts import CLUB_RECORD_TYPE, ON_HOLD_ACCOUNTS, PARTNER_RECORD_TYPE   # noqa: E402

PARTNER = "001000000000000PAA"
SUNRISE, RIVER, PILOT = "001000000000000CAA", "001000000000000CBB", "001000000000000CCC"
ME = "005000000000000MEE"
GIRLS = ["Amara Zibblewick", "Beatrice Quornstead", "Chiara Vexholm"]
K = f"{SUNRISE}|2026-09-05"


def account(acc_id, name, record_type=CLUB_RECORD_TYPE, parent=PARTNER):
    return {"Id": acc_id, "Name": name, "RecordTypeId": record_type, "ParentId": parent}


def row(sub, club="Sunrise Club", date="2026-09-05", names=GIRLS, created=None, week="3",
        module="Self Advocacy", year="1", flags=(), region="Africa"):
    return {"region": region, "form_id": "1", "submission_id": sub, "created_at": created or f"{date} 10:00:00",
            "roster_qid": "200", "club_code": "SUNRISEC", "club": club, "partner": "Example Partner",
            "sf_account_name": club, "attendance_date": date, "names": list(names), "module": module,
            "module_week": week, "module_year": year, "creator": "Jotform", "photo_urls": [], "q5": club,
            "flags": list(flags)}


class FakeOrg:
    """Salesforce, as far as the tool can see it, with the processor's rules."""
    alias = "fake"

    def __init__(self, accounts, participants=None):
        self.accounts = list(accounts)
        self.batches, self.rows, self.inserts, self.strays, self.seen, self.tick = [], [], [], [], [], 0
        self.contacts = {a["Id"]: {f"old girl {i}": ("003OLD%09d" % i, "2026-03-01T00:00:00.000+0000")
                                   for i in range((participants or {}).get(a["Id"], 0))} for a in accounts}
        self.fail_at = None          # a handled error at this name: Failed, the rows before it stay
        self.message = None          # another text on a batch that is otherwise right
        self.refuse = self.lose_answer = False
        self.die_after_insert = 0    # that many reads after an insert fail
        self.updates = []            # every PATCH: (sobject, record id, body)
        self.refuse_update = False   # Salesforce answers a PATCH with 400 and changes nothing
        self.drift_update = False    # Salesforce answers 204 but the value read back is the old one

    def clock(self):
        self.tick += 1
        return f"2026-09-30T14:{self.tick // 60:02d}:{self.tick % 60:02d}.000+0000"

    def state(self, read_at="2026-09-30T13:00:00Z"):
        days = {}
        for r in self.rows:
            days[(r["Account__c"], r["Attendance_Date__c"])] = days.get((r["Account__c"], r["Attendance_Date__c"]), 0) + 1
        return {"read_at_utc": read_at, "accounts": self.accounts,
                "batches": [{k: b[k] for k in ("Id", "Name", "Account__c", "Attendance_Date__c", "Processing_Status__c")}
                            for b in self.batches],
                "attendance": [{"Account__c": a, "Attendance_Date__c": d, "n": n} for (a, d), n in days.items()],
                "participants": [{"AccountId": a, "n": len(c)} for a, c in self.contacts.items() if c]}

    def read(self):
        if self.die_after_insert:
            self.die_after_insert -= 1
            raise bf.Refused("Salesforce did not answer a read (HTTP 0)")

    def query(self, soql):
        self.seen.append(soql)
        self.read()
        for name, text in bf.STATE_QUERIES.items():
            if soql == text:
                return self.state()[name]
        if m := re.search(r"FROM Account WHERE Name = '(.*)'$", soql):
            name = m.group(1).replace("\\'", "'").casefold()
            return [a for a in self.accounts if a["Name"].casefold() == name]
        if m := re.search(r"FROM Attendance_Batch__c WHERE Id = '(\w+)'", soql):
            return [b for b in self.batches if b["Id"] == m.group(1)]
        if m := re.fullmatch(r"SELECT Id FROM Attendance_Batch__c WHERE Creator__c = '(.*)'", soql):
            return [b for b in self.batches if b["Creator__c"] == m.group(1)]
        if m := re.search(r"SELECT Contact__c FROM Attendance__c WHERE Attendance_Batch__c = '(\w+)' "
                          r"AND Contact__r.CreatedDate >= (\S+)Z", soql):
            return [{"Contact__c": r["Contact__c"]} for r in self.rows
                    if r["Attendance_Batch__c"] == m.group(1) and r["contact_created"][:19] >= m.group(2)]
        if m := re.search(r"COUNT_DISTINCT\(Contact__c\) girls FROM Attendance__c WHERE Attendance_Batch__c = '(\w+)'", soql):
            mine = [r for r in self.rows if r["Attendance_Batch__c"] == m.group(1)]
            return [{"n": len(mine), "girls": len({r["Contact__c"] for r in mine})}]
        raise AssertionError(soql)

    def count(self, soql):
        self.seen.append(soql)
        self.read()
        day = r"(\d{4}-\d{2}-\d{2})"
        if m := re.fullmatch(r"SELECT COUNT\(\) FROM Attendance_Batch__c WHERE Account__c = '(\w+)' "
                             r"AND Attendance_Date__c = " + day, soql):
            return len([b for b in self.batches if (b["Account__c"], b["Attendance_Date__c"]) == m.groups()])
        if m := re.fullmatch(r"SELECT COUNT\(\) FROM Attendance__c WHERE Account__c = '(\w+)' "
                             r"AND Attendance_Date__c = " + day, soql):
            return len([r for r in self.rows if (r["Account__c"], r["Attendance_Date__c"]) == m.groups()])
        if m := re.fullmatch(r"SELECT COUNT\(\) FROM Contact WHERE AccountId = '(\w+)' "
                             r"AND Contact_Role__c = 'Participant'", soql):
            return len(self.contacts[m.group(1)])
        raise AssertionError(soql)

    def insert(self, sobject, body):
        assert sobject == "Attendance_Batch__c"
        self.inserts.append(body)
        if self.refuse:
            return 400, [{"errorCode": "CANNOT_INSERT_UPDATE_ACTIVATE_ENTITY", "message": "limit for Amara Zibblewick"}]
        wanted = body["Account_Name__c"].strip().casefold()
        acc = next((a for a in self.accounts if a["Name"].casefold() == wanted), None)
        if acc is None:                      # the processor creates a Club account without a partner
            acc = account("001STRAY%010d" % len(self.strays), body["Account_Name__c"], parent=None)
            self.accounts.append(acc)
            self.strays.append(acc)
            self.contacts[acc["Id"]] = {}
        day, when = body["Attendance_Date__c"], self.clock()
        typed = body.get("Girls_Present__c")         # a partner's count: an aggregate when there are no names
        batch = {"Id": "a1l%015d" % len(self.batches), "Name": "BATCH-%06d" % len(self.batches), "Account__c": acc["Id"],
                 "Attendance_Date__c": day, "Processing_Status__c": "Success", "Creator__c": body["Creator__c"],
                 "Status_Message__c": self.message or "Processed successfully.", "CreatedById": ME, "CreatedDate": when,
                 "Girls_Present__c": typed}
        names = [n.strip() for n in body["Contact_IDs__c"].split(",") if n.strip()]
        if any(b["Account__c"] == acc["Id"] and b["Attendance_Date__c"] == day and b["Processing_Status__c"] == "Success"
               for b in self.batches):
            batch.update(Processing_Status__c="Failed", Status_Message__c="Duplicate: A successful batch already exists "
                         "for this account and date.")
            names = []
        elif any(r["Account__c"] == acc["Id"] and r["Attendance_Date__c"] == day for r in self.rows):
            batch.update(Processing_Status__c="Failed", Status_Message__c=f"Attendance already exists for this club on {day}")
            names = []
        elif not names and not (isinstance(typed, (int, float)) and typed > 0):
            batch.update(Processing_Status__c="Failed", Status_Message__c="No participants submitted")
        self.batches.append(batch)
        before = dict(self.contacts[acc["Id"]])      # read once, before the loop, never refreshed
        made = 0
        for position, name in enumerate(names):
            if self.fail_at == position:
                batch.update(Processing_Status__c="Failed",
                             Status_Message__c=f"Error: Insert failed. DUPLICATES_DETECTED, duplicate of {name}: []")
                break
            contact = before.get(name.casefold())
            if contact is None:
                contact = ("003NEW%09d" % sum(len(c) for c in self.contacts.values()), when)
                mine = self.contacts[acc["Id"]]
                mine[name.casefold() if name.casefold() not in mine else f"{name.casefold()} #{position}"] = contact
            self.rows.append({"Attendance_Batch__c": batch["Id"], "Account__c": acc["Id"], "Attendance_Date__c": day,
                              "Contact__c": contact[0], "contact_created": contact[1]})
            made += 1
        if batch["Processing_Status__c"] != "Success":
            batch["Girls_Present__c"] = None         # every Failed path clears the count
        elif names:
            batch["Girls_Present__c"] = made         # names win over a typed count; an aggregate keeps its own
        if self.lose_answer:
            return 0, None
        return 201, {"id": batch["Id"], "success": True, "errors": []}

    def update(self, sobject, record_id, body):
        """PATCH one record by id: the fields in `body` land on the batch or attendance row that
        carries the id (an update runs none of the processor: its trigger is after-insert only)."""
        self.updates.append((sobject, record_id, dict(body)))
        if self.refuse_update:
            return 400, [{"errorCode": "FIELD_CUSTOM_VALIDATION_EXCEPTION", "message": "refused"}]
        records = self.batches if sobject == "Attendance_Batch__c" else self.rows
        found = [r for r in records if r.get("Id") == record_id]
        if len(found) != 1:
            return 404, [{"errorCode": "NOT_FOUND", "message": "no such record"}]
        if not self.drift_update:
            found[0].update(body)
        return 204, None


class Harness:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name
        self.org = FakeOrg([account(PARTNER, "Example Partner", PARTNER_RECORD_TYPE, None),
                            account(SUNRISE, "Sunrise Club"), account(RIVER, "River Club")])
        self.addCleanup(setattr, bf, "SETTLE_AFTER_MINUTES", bf.SETTLE_AFTER_MINUTES)
        bf.SETTLE_AFTER_MINUTES = 0          # no waiting in tests, except where the wait is the subject

    def path(self, name):
        return os.path.join(self.dir, name)

    def write(self, rows, no_ticks=None, decisions=None, fetched=None, read_at="2026-09-30T13:00:00Z", raw=None):
        resolved = {"fetched_at_utc": fetched or bf.now(), "forms": {}, "rows": rows, "no_ticks": no_ticks or {},
                    "flag_vocabulary": sorted(bf.HOLD_FLAGS | bf.PASS_FLAGS)}
        for name, data in (("resolved.json", raw if raw is not None else resolved),
                           ("sf_state.json", self.org.state(read_at))):
            with open(self.path(name), "w", encoding="utf-8") as fh:
                json.dump(data, fh)
        if decisions is not None:
            with open(self.path("decisions.csv"), "w", encoding="utf-8", newline="") as fh:
                csv.writer(fh).writerows([["key", "decision"]] + decisions)
        elif os.path.exists(self.path("decisions.csv")):
            os.remove(self.path("decisions.csv"))

    def run_tool(self, *argv):
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                bf.main(["--dir", self.dir] + list(argv), org=self.org)
        except SystemExit as stop:
            return out.getvalue(), str(stop.code)
        return out.getvalue(), None

    def plan(self, *argv):
        out, stop = self.run_tool("plan", *argv)
        self.assertIsNone(stop, stop)
        with open(self.path("plan.json"), encoding="utf-8") as fh:
            sessions = json.load(fh)["sessions"]
        with open(self.path("held.csv"), encoding="utf-8", newline="") as fh:
            held = list(csv.DictReader(fh))
        return out, sessions, held

    def send(self, *argv):
        return self.run_tool("send", "--apply", "--vpn-off", *argv)

    def replan(self, rows, **kw):
        self.write(rows, read_at=bf.now(), **kw)
        return self.plan()

    def ledger(self):
        return bf.read_ledger(self.path("ledger.csv"))

    def states(self):
        return [r["status"] for r in self.ledger()]

    def text_of(self, *names):
        text = ""
        for name in names:
            if os.path.exists(self.path(name)):
                with open(self.path(name), encoding="utf-8") as fh:
                    text += fh.read()
        return text

    def mode(self, name):
        return stat.S_IMODE(os.stat(self.path(name)).st_mode)


class SalesforceBackfill(Harness, unittest.TestCase):
    # ---- plan
    def test_one_report_becomes_one_batch_and_nothing_printed_or_listed_names_a_girl(self):
        self.write([row("5001")], no_ticks={"Africa": ["5009"]})
        out, sessions, held = self.plan()
        self.assertEqual([s["key"] for s in sessions], [K])
        self.assertEqual(held, [])
        self.assertEqual(bf.body_of(sessions[0]), {
            "Account_Name__c": "Sunrise Club", "Attendance_Date__c": "2026-09-05",
            "Contact_IDs__c": "Amara Zibblewick, Beatrice Quornstead, Chiara Vexholm",
            "Module__c": "Self Advocacy", "Module_Week__c": 3, "Module_Year__c": 1,
            "Creator__c": f"Jotform back-fill {SUNRISE} 5001", "enable_fuzzy_matching__c": False})
        self.assertIn("to send: 1 batches, 3 attendance rows, up to 3 new girls, 1 clubs", out)
        self.assertIn("resolver: 1 rows from 1 submissions with girls ticked (1 club days), 1 submissions with nobody ticked", out)
        self.assertNotIn("Zibblewick", out + self.text_of("held.csv"))
        self.assertEqual((self.mode("plan.json"), self.mode("held.csv")), (0o600, 0o600))

    def test_an_existing_wider_file_becomes_owner_only(self):
        self.write([row("1")])
        for name in ("plan.json", "held.csv"):
            open(self.path(name), "w").close()
            os.chmod(self.path(name), 0o644)
        self.plan()
        self.assertEqual((self.mode("plan.json"), self.mode("held.csv")), (0o600, 0o600))

    def test_a_name_salesforce_does_not_know_is_held_not_sent(self):
        cases = {"account_not_found": row("1", club="Moonlight Club"),
                 "account_not_a_club": row("2", club="Example Partner"),
                 "no_account_name": dict(row("3"), sf_account_name=None)}
        self.org.accounts.append(account(PILOT, "Pilot Club", parent=None))
        cases["account_without_partner"] = row("5", club="Pilot Club")
        self.org.accounts += [account("001000000000000DAA", "Twin Club"), account("001000000000000DBB", "twin club")]
        cases["account_not_unique"] = row("6", club="Twin Club")
        self.write(list(cases.values()))
        _, sessions, held = self.plan()
        self.assertEqual(sessions, [])
        self.assertEqual(sorted(h["reasons"] for h in held), sorted(cases))
        self.org.accounts.append(account(sorted(ON_HOLD_ACCOUNTS)[0], "Held Pilot Club"))
        self.write([row("7", club="Held Pilot Club")])
        self.assertEqual([h["reasons"] for h in self.plan()[2]], ["account_without_partner"])

    def test_a_resolver_file_that_cannot_be_trusted_is_refused_without_a_traceback(self):
        cases = {"row without names": [row("1", names=[])],
                 "with a blank one": [row("1", names=["Amara Zibblewick", " "])],
                 "has a row without names, or": [dict(row("1"), names="Amara Zibblewick")],
                 "a flag this tool does not know (name_not_on_roster_now)": [row("1", flags=["name_not_on_roster_now:2"])],
                 "created_at is not": [row("1", created="09/05/2026 10:00:00")],
                 "'region' is missing": [{k: v for k, v in row("1").items() if k != "region"}]}
        for message, rows in cases.items():
            with self.subTest(message):
                self.write(rows)
                self.assertIn(message, self.run_tool("plan")[1])
        for raw in ({"rows": "x"}, [], {"fetched_at_utc": "yesterday", "rows": []},
                    {"fetched_at_utc": bf.now(), "rows": [], "no_ticks": ["1"], "flag_vocabulary": sorted(bf.HOLD_FLAGS | bf.PASS_FLAGS)},
                    {"fetched_at_utc": bf.now(), "rows": []}, {"fetched_at_utc": bf.now(), "rows": [], "flag_vocabulary": ["bogus"]},
                    {"fetched_at_utc": bf.now(), "rows": [], "flag_vocabulary": sorted(bf.HOLD_FLAGS | bf.PASS_FLAGS)[1:]}):
            with self.subTest(str(raw)[:30]):
                self.write([], raw=raw)
                self.assertIn("resolved.json:", self.run_tool("plan")[1])
        self.write([row("1")])
        with open(self.path("sf_state.json"), "w") as fh:
            fh.write('{"accounts": [')
        self.assertIn("cannot be read as JSON", self.run_tool("plan")[1])
        with open(self.path("sf_state.json"), "w") as fh:
            json.dump({"read_at_utc": bf.now(), "accounts": []}, fh)
        self.assertIn("not a complete snapshot", self.run_tool("plan")[1])

    def test_two_reports_of_one_session_join_and_a_repeated_girl_counts_once(self):
        self.write([row("1", names=GIRLS[:2] + ["Zoé Quornstead"]),
                    row("2", names=["amara zibblewick", GIRLS[2], "Zoé Quornstead"], created="2026-09-05 11:00:00")])
        out, sessions, _ = self.plan()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["names"], GIRLS[:2] + ["Zoé Quornstead", GIRLS[2]])
        self.assertEqual(sessions[0]["submissions"], ["1", "2"])
        self.assertIn("1 of them join several reports", out)

    def test_two_reports_with_different_weeks_wait_for_ryan_to_name_one(self):
        rows = [row("1", week="3"), row("2", week="4", names=GIRLS[:1], created="2026-09-05 12:00:00"),
                row("3", week="4", names=GIRLS[1:2], created="2026-09-05 13:00:00")]
        self.write(rows)
        _, sessions, held = self.plan()
        self.assertEqual((sessions, [h["reasons"] for h in held]), ([], ["same_day_different_module"]))
        self.write(rows, decisions=[[K, "accept same_day_different_module"]])
        self.assertIn("cannot be accepted", self.run_tool("plan")[1])
        self.write(rows, decisions=[[K, "use 2+3"]])
        out, sessions, held = self.plan()
        self.assertEqual((sessions[0]["submissions"], sessions[0]["module_week"], sessions[0]["names"], held),
                         (["2", "3"], 4, GIRLS[:2], []))
        self.assertIn("1 report(s) set aside by 'use'", out)
        self.write(rows, decisions=[[K, "use 77"]])
        self.assertIn("not a report of that day", self.run_tool("plan")[1])

    def test_every_reason_is_listed_and_a_decision_releases_only_what_it_names(self):
        many = [f"Girl{i:02d} Quornstead{i:02d}" for i in range(28)] + ["Amara Zibblewick", "Amarra Zibblewick"]
        rows = [row("1", date="2026-06-09", created="2026-09-08 10:00:00", names=many)]
        key = f"{SUNRISE}|2026-06-09"
        self.write(rows)
        held = self.plan()[2]
        self.assertEqual(held[0]["reasons"], "date_before_september+similar_names+more_new_girls_than_proven")
        self.assertIn("day and month may be swapped", held[0]["detail"])
        self.write(rows, decisions=[[key, "date 2026-09-06"]])
        _, sessions, held = self.plan()
        self.assertEqual((sessions, held[0]["reasons"], held[0]["key"]),
                         ([], "similar_names+more_new_girls_than_proven", f"{SUNRISE}|2026-09-06"))
        self.assertIn("moved from 2026-06-09", held[0]["detail"])
        self.write(rows, decisions=[[key, "date 2026-09-06; accept similar_names"]])
        self.assertEqual(self.plan()[2][0]["reasons"], "more_new_girls_than_proven")
        self.write(rows, decisions=[[key, "date 2026-09-06; accept similar_names+more_new_girls_than_proven"]])
        out, sessions, held = self.plan()
        self.assertEqual((held, sessions[0]["attendance_date"], sessions[0]["accepted"]),
                         ([], "2026-09-06", ["more_new_girls_than_proven", "similar_names"]))
        self.assertIn("1 of them go on Ryan's 'accept'", out)
        self.write(rows, decisions=[[key, "accept date_before_september+similar_names+more_new_girls_than_proven"]])
        self.assertEqual(self.plan()[1][0]["attendance_date"], "2026-06-09")

    def test_a_date_decision_moves_a_report_before_the_days_are_grouped(self):
        early, other = f"{SUNRISE}|2026-06-09", f"{SUNRISE}|2026-07-09"
        rows = [row("1", date="2026-06-09", created="2026-09-08 10:00:00", names=GIRLS[:1]),
                row("2", date="2026-07-09", created="2026-09-08 11:00:00", names=GIRLS[1:2]),
                row("3", date="2026-09-06", created="2026-09-06 11:00:00", names=GIRLS[2:])]
        self.write(rows, decisions=[[early, "date 2026-09-06"], [other, "date 2026-09-06"]])
        _, sessions, held = self.plan()
        self.assertEqual((len(sessions), sessions[0]["submissions"], sessions[0]["names"], held),
                         (1, ["3", "1", "2"], [GIRLS[2], GIRLS[0], GIRLS[1]], []))
        rows[2]["module_week"] = "9"
        self.write(rows, decisions=[[early, "date 2026-09-06"], [other, "skip"]])
        _, sessions, held = self.plan()
        self.assertEqual((sessions, [h["reasons"] for h in held]), ([], ["same_day_different_module"]))
        for value, message in (("2026-08-06", "before 2026-09-01"), ("2027-01-01", "after a report it moves was submitted"),
                               ("2026-9-6", "must be yyyy-mm-dd"), ("09/06/2026", "must be yyyy-mm-dd"),
                               ("2026-13-45", "must be yyyy-mm-dd")):
            with self.subTest(value):
                self.write(rows[:1], decisions=[[early, f"date {value}"]])
                self.assertIn(message, self.run_tool("plan")[1])

    def test_dates_outside_the_month_are_held(self):
        self.write([row("2", date="2026-08-28", created="2026-09-02 10:00:00", club="River Club"),
                    row("3", date="2026-09-20", created="2026-09-10 10:00:00"),
                    row("4", date="", created="2026-09-10 10:00:00", names=GIRLS[:1])])
        _, sessions, held = self.plan()
        self.assertEqual(sessions, [])
        self.assertEqual({h["submissions"]: h["reasons"] for h in held},
                         {"2": "date_before_september", "3": "date_after_submission", "4": "date_missing"})

    def test_the_decisions_file_is_read_strictly(self):
        self.write([row("1"), row("2", club="River Club")])
        with open(self.path("decisions.csv"), "w", encoding="utf-8-sig", newline="") as fh:
            fh.write(f"key,decision\r\n{K},skip\r\n\r\n")
        out, sessions, _ = self.plan()
        self.assertEqual([s["account_name"] for s in sessions], ["River Club"])
        self.assertIn("skipped, skip_decided: 1", out)
        self.assertIn("decisions: 1 read and applied", out)
        cases = {"must start with the header line": "Key,decision\n" + K + ",skip\n",
                 "sessions that do not exist": f"key,decision\n{SUNRISE}|2026-09-5,skip\n",
                 "two lines for": f"key,decision\n{K},skip\n{K},accept similar_names\n",
                 "an empty key": "key,decision\n,skip\n",
                 "is not one of skip": f"key,decision\n{K},maybe\n",
                 "no decision": f"key,decision\n{K},\n",
                 "skip cannot be combined": f"key,decision\n{K},skip; date 2026-09-06\n"}
        for message, text in cases.items():
            with self.subTest(message):
                with open(self.path("decisions.csv"), "w", encoding="utf-8") as fh:
                    fh.write(text)
                self.assertIn(message, self.run_tool("plan")[1])
        with open(self.path("decisions.csv"), "w", encoding="utf-16") as fh:
            fh.write(f"key,decision\n{K},skip\n")
        self.assertIn("cannot be read as UTF-8", self.run_tool("plan")[1])

    def test_what_salesforce_already_has_for_a_club_day(self):
        body = {"Account_Name__c": "Sunrise Club", "Attendance_Date__c": "2026-09-05", "Creator__c": "Jotform",
                "Contact_IDs__c": ", ".join(GIRLS)}
        self.org.insert("Attendance_Batch__c", body)
        self.write([row("1"), row("2", date="2026-09-12")])
        out, sessions, held = self.plan()
        self.assertIn("skipped, already_in_salesforce: 1", out)
        self.assertEqual((sessions, [h["reasons"] for h in held]), ([], ["club_has_earlier_contacts"]))
        self.write([row("1", names=GIRLS[:2])])
        held = self.plan()[2]
        self.assertEqual(held[0]["reasons"], "salesforce_has_different_count")
        self.assertIn("Salesforce has 3 attendance rows for this day, the reports tick 2 girls", held[0]["detail"])
        self.org.insert("Attendance_Batch__c", dict(body, Attendance_Date__c="2026-09-19", Contact_IDs__c=""))
        self.org.fail_at = 0
        self.org.insert("Attendance_Batch__c", dict(body, Attendance_Date__c="2026-09-26"))
        self.write([row("3", date="2026-09-19"), row("4", date="2026-09-26")], decisions=[])
        out, sessions, held = self.plan()
        self.assertEqual((sessions, [h["reasons"] for h in held]), ([], ["salesforce_has_empty_or_failed_batch"] * 2))
        self.assertNotIn("already_in_salesforce", out)
        self.write([row("5", date="2026-09-28")], decisions=[])       # no report for those days at all: still shown
        out = self.plan()[0]
        self.assertIn("Salesforce holds 2 batch(es) from 2026-09-01 on without any attendance for their club and day - "
                      "a Success among them blocks that day for a later batch; this tool never adds to a day with any "
                      "batch:", out)
        self.assertIn("BATCH-000001 Failed Sunrise Club / 2026-09-19", out)      # a blank: "No participants submitted"
        self.assertIn("BATCH-000002 Failed Sunrise Club / 2026-09-26", out)

    def test_new_girls_are_counted_per_club_in_date_order_and_a_large_batch_holds_the_rest(self):
        many = [f"Girl{i:02d} Quornstead{i:02d}" for i in range(30)]
        self.write([row("1", names=GIRLS[:2]), row("2", date="2026-09-12", names=GIRLS),
                    row("3", club="River Club", names=many), row("4", club="River Club", date="2026-09-12", names=many[:3])])
        out, sessions, held = self.plan()
        self.assertEqual([(s["attendance_date"], s["new_expected"], s["new_exact"]) for s in sessions],
                         [("2026-09-05", 2, True), ("2026-09-12", 1, True)])
        self.assertEqual(sorted((h["attendance_date"], h["reasons"]) for h in held),
                         [("2026-09-05", "more_new_girls_than_proven"), ("2026-09-12", "earlier_session_held")])
        self.assertEqual(len(self.plan("--max-new", "30")[1]), 4)
        self.assertEqual(self.run_tool("plan", "--max-new", "0")[1], "2")

    def test_two_names_the_duplicate_rule_may_take_for_one_girl_are_held(self):
        self.write([row("1", names=["Amara Zibblewick", "Amarra Zibblewick", "Dalia Vexholm"]),
                    row("2", club="River Club", names=["Amara Zibblewick", "Esther Zibblewick", "A Quornstead",
                                                        "Anna Quornstead"])])
        _, sessions, held = self.plan()
        self.assertEqual(sorted(h["reasons"] + " " + h["account_name"] for h in held),
                         ["similar_names River Club", "similar_names Sunrise Club"])
        self.assertEqual(len(self.plan("--dup-rule-ok")[1]), 2)
        self.assertFalse(bf.alike("Amara Zibblewick", "Esther Zibblewick"))
        self.assertFalse(bf.alike("Amara", "Amarra"))                       # one word: no last name to match

    def test_names_that_would_break_the_split_are_held_and_cannot_be_accepted(self):
        for name, why in (("Zibblewick, Amara", "a comma"), ("Amara  Zibblewick", "doubled or invisible"),
                          ("Amara​Zibblewick Quornstead", "doubled or invisible"), ("A" * 41 + " Vexholm", "longer")):
            with self.subTest(why):
                self.write([row("1", names=[name, GIRLS[1]])])
                held = self.plan()[2]
                self.assertEqual(held[0]["reasons"], "bad_name")
                self.assertIn(why, held[0]["detail"])
        self.write([row("1", names=["Zibblewick, Amara"])], decisions=[[K, "accept bad_name"]])
        self.assertIn("cannot be accepted", self.run_tool("plan")[1])

    def test_several_rosters_and_the_resolver_s_flags(self):
        self.write([row("1"), row("1", club="River Club"), row("2", date="2026-09-12", flags=["name_unknown_to_roster:2"]),
                    row("3", date="2026-09-19", flags=["name_left_roster:1", "q18_empty", "module_translated"]),
                    row("4", date="2026-09-26", flags=["module_unresolved"]),
                    row("5", date="2026-09-27", week="³"), row("6", date="2026-09-28", module=" ")])
        _, sessions, held = self.plan()
        self.assertEqual(sessions, [])       # the 09-19 one is fine but waits behind the held ones before it
        self.assertEqual({(h["attendance_date"], h["account_name"]): h["reasons"] for h in held}, {
            ("2026-09-05", "Sunrise Club"): "several_rosters_ticked", ("2026-09-05", "River Club"): "several_rosters_ticked",
            ("2026-09-12", "Sunrise Club"): "name_unknown_to_roster", ("2026-09-19", "Sunrise Club"): "earlier_session_held",
            ("2026-09-26", "Sunrise Club"): "module_unresolved", ("2026-09-27", "Sunrise Club"): "module_not_usable",
            ("2026-09-28", "Sunrise Club"): "module_not_usable"})

    # ---- send
    def test_dry_run_sends_nothing_and_apply_sends_in_order_and_is_safe_to_repeat(self):
        rows = [row("2", date="2026-09-12", names=GIRLS), row("1", names=GIRLS[:2]),
                row("3", club="River Club", names=GIRLS[:1])]
        self.write(rows)
        self.plan()
        out, stop = self.run_tool("send")
        self.assertIsNone(stop)
        self.assertIn("dry run: nothing was sent", out)
        self.assertEqual((self.org.inserts, self.ledger()), ([], []))
        out, stop = self.send("--limit", "1")
        self.assertIsNone(stop, stop)
        self.assertEqual([b["Account_Name__c"] for b in self.org.inserts], ["River Club"])   # the smallest first
        out, stop = self.send()
        self.assertIsNone(stop, stop)
        self.assertEqual([(b["Account_Name__c"], b["Attendance_Date__c"]) for b in self.org.inserts][1:],
                         [("Sunrise Club", "2026-09-05"), ("Sunrise Club", "2026-09-12")])
        done = [r for r in self.ledger() if r["status"] == "ok"]
        self.assertEqual(self.states(), ["sending", "ok"] * 3)
        self.assertEqual([(r["rows"], r["participants_before"], r["participants_after"], r["contacts_created"],
                           r["new_exact"]) for r in done],
                         [("1", "0", "1", "1", "yes"), ("2", "0", "2", "2", "yes"), ("3", "2", "3", "1", "yes")])
        self.assertTrue(all(r["created_by"] == ME and r["batch_id"] and r["done_utc"] for r in done))
        out, stop = self.send()
        self.assertIn("queue: 0 batches", out)
        self.assertEqual(len(self.org.inserts), 3)
        out, _ = self.run_tool("status")
        self.assertIn("3 batches sent and verified, 6 attendance rows, 4 new girls, 2 clubs", out)
        self.assertIn("the 4 participant contacts they created", out)
        self.assertNotIn("Zibblewick", out + self.text_of("ledger.csv", "created_contacts.csv", "held.csv"))
        self.assertEqual(len(self.text_of("created_contacts.csv").splitlines()), 4)
        self.assertEqual([self.mode(n) for n in ("ledger.csv", "created_contacts.csv", "sent_names.json")], [0o600] * 3)
        out, sessions, _ = self.replan(rows + [row("4", date="2026-09-19")])
        self.assertEqual([(s["attendance_date"], s["new_expected"], s["new_exact"]) for s in sessions],
                         [("2026-09-19", 0, True)])
        self.assertIn("skipped, sent_by_this_tool: 3", out)

    def test_the_live_commands_need_the_vpn_word_and_the_whole_write_flag(self):
        self.write([row("1")])
        self.plan()
        self.assertIn("check that no VPN is on", self.run_tool("send", "--apply")[1])
        self.assertIn("check that no VPN is on", self.run_tool("snapshot")[1])
        for short in ("--app", "--a", "--appl"):
            self.assertEqual(self.run_tool("send", short, "--vpn-off")[1], "2")      # argparse: no such flag
        self.assertEqual(self.run_tool("send", "--apply", "--vpn-off", "--limit", "0")[1], "2")
        self.assertEqual(self.org.inserts, [])
        out, stop = self.run_tool("snapshot", "--vpn-off")
        self.assertIsNone(stop, stop)
        self.assertIn("snapshot: 3 accounts, 0 batches", out)
        with open(self.path("sf_state.json"), encoding="utf-8") as fh:
            self.assertEqual(sorted(json.load(fh)), ["accounts", "attendance", "batches", "participants", "read_at_utc",
                                                     "source"])
        self.assertEqual(self.mode("sf_state.json"), 0o600)

    def test_a_folder_inside_the_checkout_but_outside_data_is_refused(self):
        with self.assertRaises(SystemExit) as stop, contextlib.redirect_stdout(io.StringIO()):
            bf.main(["--dir", os.path.join(REPO, "docs"), "plan"], org=self.org)
        self.assertIn("must be under data/", str(stop.exception.code))

    def test_a_snapshot_older_than_the_last_batch_is_refused(self):
        self.write([row("1")])
        self.plan()
        self.assertIsNone(self.send()[1])
        self.write([row("1")], read_at="2026-09-01T00:00:00Z")
        self.assertIn("snapshot again", self.run_tool("plan")[1])

    def test_send_refuses_a_plan_that_no_longer_matches_its_inputs(self):
        self.write([row("1")])
        self.plan()
        self.write([row("1"), row("2", date="2026-09-12")])
        self.assertIn("run plan again", self.send()[1])
        self.write([row("1")])
        self.plan()
        with open(self.path("decisions.csv"), "w", encoding="utf-8") as fh:
            fh.write(f"key,decision\n{K},skip\n")
        self.assertIn("decisions.csv changed after the plan", self.send()[1])
        self.write([row("1")], fetched="2026-09-30T01:00:00Z")
        self.plan()
        self.assertIn("fetched more than 3 hours ago", self.send()[1])
        self.assertEqual(self.org.inserts, [])

    def test_send_proves_each_batch_against_salesforce_first(self):
        def fresh():
            self.org = FakeOrg([account(SUNRISE, "Sunrise Club")])
            self.write([row("1")])
            self.plan()
        fresh()
        self.org.accounts.append(account("001000000000000DAA", "SUNRISE CLUB"))
        self.assertIn("no longer leads to exactly its one Club account", self.send()[1])
        fresh()
        self.org.accounts[0]["ParentId"] = None
        self.assertIn("no longer leads to exactly its one Club account", self.send()[1])
        fresh()
        # a blank is Failed "No participants submitted" and blocks nothing in Salesforce, but this tool never
        # adds to a club and day that has any batch
        self.org.insert("Attendance_Batch__c", {"Account_Name__c": "Sunrise Club", "Attendance_Date__c": "2026-09-05",
                                                "Creator__c": "Jotform", "Contact_IDs__c": ""})
        self.assertEqual(self.org.batches[-1]["Processing_Status__c"], "Failed")
        self.org.inserts.clear()
        self.assertIn("already has a batch or attendance for this club and day", self.send()[1])
        fresh()
        self.org.rows.append({"Attendance_Batch__c": "x", "Account__c": SUNRISE, "Attendance_Date__c": "2026-09-05",
                              "Contact__c": "c", "contact_created": "2026-03-01T00:00:00"})
        self.assertIn("already has a batch or attendance for this club and day", self.send()[1])
        fresh()
        self.org.contacts[SUNRISE]["somebody new"] = ("003X", "2026-09-30T13:30:00.000+0000")
        self.assertIn("somebody else added girls", self.send()[1])
        self.assertEqual((self.org.inserts, self.ledger()), ([], []))
        fresh()
        with open(self.path("plan.json"), encoding="utf-8") as fh:
            plan = json.load(fh)
        plan["sessions"][0]["names"] = ["Amara Zibblewick", " "]
        with open(self.path("plan.json"), "w", encoding="utf-8") as fh:
            json.dump(plan, fh)
        self.assertIn("the plan entry is not usable", self.send()[1])
        self.assertEqual(self.org.inserts, [])

    def test_a_batch_that_is_not_right_stops_the_line_and_its_message_is_never_repeated(self):
        rows = [row("1"), row("2", club="River Club", names=GIRLS[:2]), row("3", club="River Club", date="2026-09-12")]
        key = f"{RIVER}|2026-09-05"
        self.write(rows)
        self.plan()
        self.org.fail_at = 1                 # the second girl fails: one row and one contact stay behind
        out, stop = self.send()
        self.assertIn("is in Salesforce but not as planned", stop)
        self.assertIn("status failed_DUPLICATES_DETECTED; 1 rows for 1 girls, 2 sent", stop)
        self.assertEqual(self.states(), ["sending", "CHECK"])
        self.assertNotIn("Quornstead", out + stop + self.text_of("ledger.csv") + self.run_tool("status")[0])
        self.assertEqual(len(self.org.inserts), 1)
        self.org.fail_at = None
        self.assertIn("deal with it, then `close <key> --removed`", self.send()[1])
        self.assertIn("deal with it", self.run_tool("send")[1])
        self.assertEqual(len(self.org.inserts), 1)
        self.org.batches, self.org.rows, self.org.contacts[RIVER] = [], [], {}       # cleaned up by hand
        self.assertIsNone(self.run_tool("close", key, "--removed", "--note", "cleaned up")[1])
        _, sessions, held = self.replan(rows)
        self.assertEqual([s["account_name"] for s in sessions], ["Sunrise Club"])
        self.assertEqual({h["attendance_date"]: h["reasons"] for h in held},
                         {"2026-09-05": "club_has_earlier_contacts", "2026-09-12": "club_has_earlier_contacts"})
        _, sessions, held = self.replan(rows, decisions=[[key, "accept club_has_earlier_contacts"],
                                                         [f"{RIVER}|2026-09-12", "accept club_has_earlier_contacts"]])
        self.assertEqual((len(sessions), held), (3, []))
        out, stop = self.send()
        self.assertIsNone(stop, stop)
        self.assertEqual(self.states()[-6:], ["sending", "ok"] * 3)
        self.assertEqual([r["new_exact"] for r in self.ledger() if r["status"] == "ok"], ["no", "no", "yes"])

    def test_a_batch_marked_check_can_be_accepted_and_then_counts_as_sent(self):
        rows = [row("1"), row("3", club="River Club", names=GIRLS[:1])]
        key = f"{RIVER}|2026-09-05"
        self.write(rows)
        self.plan()
        self.org.message = "Processed."      # right in every count, but not the text this tool knows
        out, stop = self.send()
        self.assertIn("status success_other", stop)
        self.assertEqual(self.states(), ["sending", "CHECK"])
        self.org.message = None
        self.assertIn("the ledger has no session", self.run_tool("close", "nope", "--removed")[1])
        self.assertIsNone(self.run_tool("close", key, "--accepted")[1])
        self.assertIn("--accepted is for a batch the ledger marks CHECK", self.run_tool("close", key, "--accepted")[1])
        self.assertIn("a batch was closed by hand after this plan was made", self.send()[1])   # the old plan is void
        self.assertEqual(len(self.org.inserts), 1)
        self.replan(rows)
        out, stop = self.send()
        self.assertIsNone(stop, stop)
        self.assertEqual(self.states(), ["sending", "CHECK", "accepted", "sending", "ok"])
        self.assertIn("2 batches sent and verified, 4 attendance rows, 4 new girls, 2 clubs", self.run_tool("status")[0])
        _, sessions, held = self.replan(rows + [row("4", club="River Club", date="2026-09-12")])
        self.assertEqual((sessions, [h["reasons"] for h in held]), ([], ["club_has_earlier_contacts"]))

    def test_a_refused_batch_saves_nothing_parks_its_club_and_the_others_go_on(self):
        self.write([row("1", names=GIRLS[:1]), row("2", date="2026-09-12"), row("3", club="River Club", names=GIRLS[:2])])
        self.plan()
        self.org.refuse = True
        out, stop = self.send()
        self.assertIn("refused the batch (HTTP 400 CANNOT_INSERT_UPDATE_ACTIVATE_ENTITY) and saved nothing", stop)
        self.assertNotIn("Zibblewick", stop + self.text_of("ledger.csv"))
        self.assertEqual([(r["status"], r["batch_id"]) for r in self.ledger()], [("sending", ""), ("not_saved", "")])
        self.org.refuse = False
        out, stop = self.send()
        self.assertIsNone(stop, stop)
        self.assertIn("1 clubs wait for a refused batch", out)
        self.assertEqual([b["Account_Name__c"] for b in self.org.inserts[1:]], ["River Club"])
        self.assertIn("not a session Salesforce refused", self.send("--retry", f"{RIVER}|2026-09-05")[1])
        out, stop = self.send("--retry", K)
        self.assertIsNone(stop, stop)
        self.assertEqual([(b["Account_Name__c"], b["Attendance_Date__c"]) for b in self.org.inserts[2:]],
                         [("Sunrise Club", "2026-09-05"), ("Sunrise Club", "2026-09-12")])

    def test_a_lost_answer_is_looked_up_by_the_batch_s_own_marker(self):
        self.write([row("1")])
        self.plan()
        self.org.lose_answer = True
        out, stop = self.send()
        self.assertIsNone(stop, stop)
        self.assertEqual((len(self.org.inserts), self.states()), (1, ["sending", "ok"]))

    def test_a_read_that_fails_after_the_insert_is_recorded_and_settled_on_the_next_run(self):
        self.write([row("1"), row("2", club="River Club")])
        self.plan()
        real_insert = self.org.insert

        def insert_then_die(sobject, body):
            answer = real_insert(sobject, body)
            self.org.die_after_insert = 1
            return answer
        self.org.insert = insert_then_die
        out, stop = self.send()
        self.assertIn("A BATCH MAY BE IN SALESFORCE", stop)
        self.assertEqual(self.states(), ["sending", "unknown"])
        self.assertTrue(self.ledger()[-1]["batch_id"])
        self.org.insert = real_insert
        self.assertIn("1 batch(es) with an unknown outcome", self.run_tool("send")[0])
        out, stop = self.send()
        self.assertIsNone(stop, stop)
        self.assertIn("is in Salesforce and as planned", out)
        self.assertEqual(self.states(), ["sending", "unknown", "ok", "sending", "ok"])
        self.assertEqual(len(self.org.inserts), 2)
        with open(self.path("sent_names.json"), encoding="utf-8") as fh:
            self.assertEqual(len(json.load(fh)), 2)

    def test_a_lost_answer_with_nothing_saved_is_not_taken_for_somebody_else_s_batch(self):
        self.write([row("1")])
        self.plan()
        real_insert = self.org.insert

        def nothing_saved(sobject, body):
            self.org.inserts.append(body)    # our batch is lost; a live one for the same day lands instead
            self.org.batches.append({"Id": "a1l000000000000LIV", "Name": "BATCH-LIVE", "Account__c": SUNRISE,
                                     "Attendance_Date__c": "2026-09-05", "Processing_Status__c": "Success",
                                     "Creator__c": "Jotform", "Status_Message__c": "Processed successfully.",
                                     "CreatedById": ME, "CreatedDate": self.org.clock()})
            return 0, None
        self.org.insert = nothing_saved
        out, stop = self.send()
        self.assertIn("A BATCH MAY BE IN SALESFORCE", stop)
        self.assertEqual(self.states(), ["sending", "unknown"])
        self.org.insert = real_insert
        out, stop = self.send()
        self.assertIn("Salesforce saved nothing; the club waits for --retry", out)
        self.assertEqual((self.states(), self.ledger()[-1]["batch_id"]), (["sending", "unknown", "not_saved"], ""))

    def test_only_cannot_send_a_club_s_later_session_before_its_earlier_one(self):
        self.write([row("1", names=GIRLS[:2]), row("2", date="2026-09-12")])
        self.plan()
        self.assertIn("an earlier session of this club is not sent yet", self.send("--only", f"{SUNRISE}|2026-09-12")[1])
        self.assertEqual(self.org.inserts, [])
        self.assertIsNone(self.send("--only", K)[1])
        self.assertIsNone(self.send("--only", f"{SUNRISE}|2026-09-12")[1])
        self.assertEqual(self.states(), ["sending", "ok"] * 2)

    def test_after_a_send_only_what_was_sent_counts_as_made(self):
        rows = [row("1", week="3"), row("2", week="4", names=GIRLS[:1], created="2026-09-05 12:00:00"),
                row("3", date="2026-09-12")]
        decisions = [[K, "use 2"]]
        self.write(rows, decisions=decisions)
        self.plan()
        self.assertIsNone(self.send("--limit", "1")[1])
        _, sessions, held = self.replan(rows, decisions=decisions)
        self.assertEqual([(s["attendance_date"], s["new_expected"]) for s in sessions], [("2026-09-12", 2)])
        self.assertEqual(held, [])           # the report set aside by 'use' is not a late one
        self.assertIsNone(self.send()[1])
        # a report that comes later for a day already sent is shown, not dropped
        more = rows + [row("4", week="4", names=["Dalia Vexholm"], created="2026-09-05 15:00:00")]
        _, sessions, held = self.replan(more, decisions=decisions)
        self.assertEqual([h["reasons"] for h in held], ["later_report_of_sent_session"])
        self.assertIn("1 report(s) came after", held[0]["detail"])
        # a sent report whose date was changed in Jotform is not sent a second time
        _, sessions, held = self.replan([dict(rows[1], attendance_date="2026-09-06"), rows[2]])
        self.assertEqual((sessions, [h["reasons"] for h in held]), ([], ["submission_already_sent"]))
        # and a batch the ledger has but Salesforce has lost is a refusal
        self.org.batches.pop(0)
        self.write(rows, decisions=decisions, read_at=bf.now())
        self.assertIn("Salesforce no longer has that batch", self.run_tool("plan")[1])

    def test_a_club_with_contacts_from_before_is_held_for_every_session_until_ryan_accepts_each(self):
        self.org = FakeOrg(self.org.accounts, participants={SUNRISE: 9})
        self.org.contacts[SUNRISE]["chiara vexholm"] = ("003OLDX", "2026-03-01T00:00:00.000+0000")
        rows = [row("1", names=GIRLS[:2]), row("2", date="2026-09-12")]
        self.write(rows)
        _, sessions, held = self.plan()
        self.assertEqual((sessions, [h["reasons"] for h in held]), ([], ["club_has_earlier_contacts"] * 2))
        decisions = [[K, "accept club_has_earlier_contacts"]]
        self.write(rows, decisions=decisions)
        _, sessions, held = self.plan()
        self.assertEqual([(s["new_expected"], s["new_exact"]) for s in sessions], [(2, False)])
        self.assertEqual([h["reasons"] for h in held], ["club_has_earlier_contacts"])
        self.assertIsNone(self.send()[1])
        _, sessions, held = self.replan(rows, decisions=decisions)   # one released batch does not make the club exact
        self.assertEqual((sessions, [h["reasons"] for h in held]), ([], ["club_has_earlier_contacts"]))
        decisions.append([f"{SUNRISE}|2026-09-12", "accept club_has_earlier_contacts"])
        self.replan(rows, decisions=decisions)
        out, stop = self.send()
        self.assertIsNone(stop, stop)        # the girl who was already a contact is matched, not made again
        self.assertEqual([(r["contacts_created"], r["new_exact"]) for r in self.ledger() if r["status"] == "ok"],
                         [("2", "no"), ("0", "no")])

    # ---- the wire
    def test_the_token_never_reaches_a_command_line_and_the_body_survives_curl(self):
        calls = []
        body = {"Contact_IDs__c": "Ng'ozi \"Zi\" Zibblewick, Chiara Vexhölm\\", "Module_Week__c": 3}

        class Done:
            def __init__(self, stdout):
                self.stdout, self.stderr = stdout, ""

        def run(argv, input=None, **_):
            calls.append((argv, input))
            if argv[:3] == ["sf", "org", "display"]:       # the CLI shows a placeholder here, not the token
                return Done(json.dumps({"result": {"accessToken": "hidden", "instanceUrl": "https://example.my.salesforce.com/"}}))
            if argv[:4] == ["sf", "org", "auth", "show-access-token"]:
                return Done(json.dumps({"result": {"accessToken": "00Dfake!token"}}))
            return Done('{"id": "a1l000000000000001", "success": true}\n201')

        org = bf.Org("glow", run=run)
        self.assertEqual(org.insert("Attendance_Batch__c", body), (201, {"id": "a1l000000000000001", "success": True}))
        argv, config = calls[-1]
        self.assertEqual([call[0][:4] for call in calls[:2]], [["sf", "org", "display", "--target-org"],
                                                                ["sf", "org", "auth", "show-access-token"]])
        self.assertEqual(argv[:2], ["curl", "-q"])       # no curlrc: nothing else may trace or reroute the call
        self.assertTrue(all("00Dfake" not in part and "Zibblewick" not in part for call in calls for part in call[0]))
        self.assertIn('header = "Authorization: Bearer 00Dfake!token"', config)
        self.assertIn('noproxy = "*"', config)
        self.assertIn('url = "https://example.my.salesforce.com/services/data/v67.0/sobjects/Attendance_Batch__c"', config)
        data = re.search(r'^data = "(.*)"$', config, re.M).group(1)
        self.assertEqual(json.loads(re.sub(r'\\(["\\])', r"\1", data)), body)     # what curl un-escapes
        self.assertTrue(data.isascii())
        org.update("Attendance_Batch__c", "a1l000000000000001", {"Module__c": "Decision Making"})
        config = calls[-1][1]                # the one PATCH shape the correction tools use
        self.assertIn('request = "PATCH"', config)
        self.assertIn('url = "https://example.my.salesforce.com/services/data/v67.0/sobjects/Attendance_Batch__c/'
                      'a1l000000000000001"', config)
        self.assertIn('data = "{\\"Module__c\\": \\"Decision Making\\"}"', config)

    def test_reads_follow_pages_and_refuse_what_they_cannot_finish(self):
        pages = {"first": {"done": False, "nextRecordsUrl": "/services/data/v67.0/query/next-1", "records": [{"Id": "1"}]},
                 "next-1": {"done": True, "records": [{"Id": "2"}]}}
        seen = []

        def run(argv, input=None, **_):
            if argv[0] == "sf":
                return type("R", (), {"stdout": json.dumps({"result": {"accessToken": "t", "instanceUrl": "https://x"}})})()
            url = re.search(r'^url = "(.*)"$', input, re.M).group(1)
            seen.append(url)
            page = pages["next-1" if url.endswith("next-1") else "first"]
            return type("R", (), {"stdout": json.dumps(page) + "\n200"})()

        org = bf.Org("glow", run=run)
        self.assertEqual(org.query("SELECT Id FROM Account"), [{"Id": "1"}, {"Id": "2"}])
        self.assertEqual(len(seen), 2)
        pages["first"] = {"done": False, "records": []}
        with self.assertRaises(bf.Refused) as stop:
            org.query("SELECT Id FROM Account")
        self.assertIn("part of an answer", str(stop.exception))
        pages["first"] = {"totalSize": 1}
        with self.assertRaises(bf.Refused):
            org.query("SELECT Id FROM Account")

    def test_no_login_and_a_missing_cli_are_clear_refusals(self):
        org = bf.Org("glow", run=lambda *a, **k: type("R", (), {"stdout": '{"status": 1}', "stderr": ""})())
        with self.assertRaises(bf.Refused) as stop:
            org.query("SELECT Id FROM Account")
        self.assertIn("sf org login web --alias glow", str(stop.exception))

        def missing(*a, **k):
            raise FileNotFoundError("sf")
        with self.assertRaises(bf.Refused):
            bf.Org("glow", run=missing).count("SELECT COUNT() FROM Account")

    def test_a_status_message_is_reduced_to_its_kind(self):
        self.assertEqual(bf.outcome_of("Success", "Processed successfully."), "success")
        self.assertEqual(bf.outcome_of("Failed", "Duplicate: A successful batch already exists"), "duplicate_batch")
        self.assertEqual(bf.outcome_of("Failed", "Attendance already exists for this club on 9/5/2026"),
                         "attendance_already_exists")
        self.assertEqual(bf.outcome_of("Failed", "No participants submitted"), "no_participants")
        self.assertEqual(bf.outcome_of("Failed", "Error: STRING_TOO_LONG, First Name: data value too large: "
                                       "WILHELMINA ZIBBLEWICK"), "failed_STRING_TOO_LONG")
        self.assertEqual(bf.outcome_of("Failed", "Error: could not process AMARAZ ZIBBLEWICK"), "failed_other")
        self.assertEqual(bf.outcome_of("AMARA ZIBBLEWICK", None), "no status_other")


class SalesforceBackfillEdges(Harness, unittest.TestCase):
    """What the second review asked to have pinned: the read-back, unclear answers, stricter inputs."""

    def after_insert(self, change):
        real = self.org.insert

        def insert(sobject, body):
            answer = real(sobject, body)
            change()
            return answer
        self.org.insert = insert

    def contact_lines(self):
        return self.text_of("created_contacts.csv").splitlines()

    # ---- decisions and dates
    def test_a_date_on_a_day_reports_were_moved_onto_is_refused(self):
        early = f"{SUNRISE}|2026-06-09"
        rows = [row("1", date="2026-06-09", created="2026-09-08 10:00:00", names=GIRLS[:1]),
                row("3", date="2026-09-06", created="2026-09-06 11:00:00", names=GIRLS[2:])]
        self.write(rows, decisions=[[early, "date 2026-09-06"], [f"{SUNRISE}|2026-09-06", "date 2026-09-07"]])
        self.assertIn("reports were moved onto this day from " + early, self.run_tool("plan")[1])

    def test_every_report_of_a_day_must_have_been_sent_in_on_or_after_it(self):
        rows = [row("1", date="2026-09-20", created="2026-09-08 10:00:00", names=GIRLS[:2]),
                row("2", date="2026-09-20", created="2026-09-20 18:00:00", names=GIRLS[2:])]
        self.write(rows)
        _, sessions, held = self.plan()
        self.assertEqual((sessions, [h["reasons"] for h in held]), ([], ["date_after_submission"]))
        self.write(rows, decisions=[[f"{SUNRISE}|2026-09-20", "use 2"]])
        self.assertEqual([s["submissions"] for s in self.plan()[1]], [["2"]])
        self.write(rows[:1] + [row("5", date="2026-09-25", created="2026-09-25 09:00:00")],
                   decisions=[[f"{SUNRISE}|2026-09-20", "date 2026-09-25"]])
        self.assertIn("after a report it moves was submitted", self.run_tool("plan")[1])

    def test_use_reaches_only_the_reports_of_its_own_day(self):
        rows = [row("1", date="2026-09-19", week="3", created="2026-09-12 11:00:00"),
                row("2", date="2026-09-19", week="4", names=GIRLS[:1], created="2026-09-12 12:00:00"),
                row("5", date="2026-09-12", week="4", names=GIRLS[1:])]
        self.write(rows, decisions=[[f"{SUNRISE}|2026-09-19", "use 2; date 2026-09-12"]])
        out, sessions, held = self.plan()    # report 5 is the 09-12's own: joined, not set aside
        self.assertEqual((sessions[0]["submissions"], sessions[0]["set_aside"], sessions[0]["names"], held),
                         (["5", "2"], ["1"], GIRLS[1:] + GIRLS[:1], []))
        for text, message in ((f"{K},use 2,3", "more than two columns"), (f"{K},use 2; use 1", "'use' twice")):
            with open(self.path("decisions.csv"), "w", encoding="utf-8") as fh:
                fh.write("key,decision\n" + text + "\n")
            self.assertIn(message, self.run_tool("plan")[1])

    def test_a_date_decision_answers_the_resolver_s_missing_date(self):
        self.write([row("1", date="", created="2026-09-10 10:00:00", flags=["date_missing"])],
                   decisions=[[f"{SUNRISE}||1", "date 2026-09-09"]])
        _, sessions, held = self.plan()
        self.assertEqual(([s["attendance_date"] for s in sessions], held), (["2026-09-09"], []))

    def test_undated_reports_are_decided_one_by_one_and_use_on_a_moved_onto_day_is_refused(self):
        rows = [row("1", date="", created="2026-09-06 10:00:00", names=GIRLS[:1]),
                row("2", date="", created="2026-09-13 10:00:00", names=GIRLS[1:])]
        self.write(rows)
        self.assertEqual(sorted(h["key"] for h in self.plan()[2]), [f"{SUNRISE}||1", f"{SUNRISE}||2"])
        self.write(rows, decisions=[[f"{SUNRISE}||1", "date 2026-09-06"], [f"{SUNRISE}||2", "date 2026-09-13"]])
        self.assertEqual([(s["attendance_date"], s["submissions"]) for s in self.plan()[1]],
                         [("2026-09-06", ["1"]), ("2026-09-13", ["2"])])
        self.write(rows, decisions=[[f"{SUNRISE}||1", "date 2026-09-06"], [f"{SUNRISE}|2026-09-06", "use 1"]])
        self.assertIn("'use' on this line reaches none of them", self.run_tool("plan")[1])

    def test_a_report_sent_under_one_club_is_not_sent_again_under_another(self):
        self.write([row("1")])
        self.plan()
        self.assertIsNone(self.send()[1])
        _, sessions, held = self.replan([row("1", club="River Club")])       # the same report now leads to another club
        self.assertEqual((sessions, [h["reasons"] for h in held]), ([], ["submission_already_sent"]))

    def test_the_two_clubs_of_one_submission_have_their_own_markers(self):
        rows = [row("1", names=GIRLS[:1]), row("1", club="River Club", names=GIRLS[1:])]
        decisions = [[K, "accept several_rosters_ticked"], [f"{RIVER}|2026-09-05", "accept several_rosters_ticked"]]
        self.write(rows, decisions=decisions)
        self.plan()
        self.assertIsNone(self.send("--limit", "1")[1])
        self.replan(rows, decisions=decisions)
        real_insert = self.org.insert

        def nothing_saved(sobject, body):
            self.org.inserts.append(body)
            return 0, None
        self.org.insert = nothing_saved
        self.assertIn("A BATCH MAY BE IN SALESFORCE", self.send()[1])     # the first club's batch is not taken for it
        self.assertEqual((self.states()[-2:], self.ledger()[-1]["batch_id"]), (["sending", "unknown"], ""))
        self.org.insert = real_insert
        out, stop = self.send()
        self.assertIn("Salesforce saved nothing", out)
        self.assertEqual(len({b["Creator__c"] for b in self.org.inserts}), 2)

    def test_an_empty_ledger_file_gets_its_header_and_one_without_it_is_refused(self):
        self.write([row("1")])
        self.plan()
        open(self.path("ledger.csv"), "w").close()
        self.assertIsNone(self.send()[1])
        self.assertTrue(self.text_of("ledger.csv").startswith("when_utc,done_utc,key,"))
        with open(self.path("ledger.csv"), "w", encoding="utf-8") as fh:
            fh.write("2026-09-30T15:00:00Z,,k,Africa\n")
        self.assertIn("does not start with its header line", self.run_tool("status")[1])

    def test_a_fetch_time_in_the_future_is_refused(self):
        self.write([row("1")], fetched="2031-01-01T00:00:00Z")
        self.assertIn("fetched_at_utc is in the future", self.run_tool("plan")[1])

    def test_the_two_halves_of_a_several_rosters_submission_can_both_be_sent(self):
        rows = [row("1", names=GIRLS[:1]), row("1", club="River Club", names=GIRLS[1:])]
        decisions = [[K, "accept several_rosters_ticked"], [f"{RIVER}|2026-09-05", "accept several_rosters_ticked"]]
        self.write(rows, decisions=decisions)
        self.plan()
        self.assertIsNone(self.send("--limit", "1")[1])
        _, sessions, held = self.replan(rows, decisions=decisions)
        self.assertEqual((len(sessions), held), (1, []))

    # ---- the folder
    def test_the_folder_and_the_resolver_s_file_are_made_owner_only(self):
        self.write([row("1")])
        os.chmod(self.dir, 0o755)
        os.chmod(self.path("resolved.json"), 0o644)
        self.plan()
        self.assertEqual((stat.S_IMODE(os.stat(self.dir).st_mode), self.mode("resolved.json")), (0o700, 0o600))

    def test_a_link_into_the_checkout_does_not_pass_the_folder_guard(self):
        link = os.path.join(self.dir, "elsewhere")
        os.symlink(os.path.join(REPO, "docs"), link)
        with self.assertRaises(SystemExit) as stop, contextlib.redirect_stdout(io.StringIO()):
            bf.main(["--dir", link, "status"], org=self.org)
        self.assertIn("must be under data/", str(stop.exception.code))
        with self.assertRaises(SystemExit) as stop:
            bf.main(["--dir", os.path.join(self.dir, "nowhere"), "status"], org=self.org)
        self.assertIn("there is no folder", str(stop.exception.code))

    def test_a_damaged_file_stops_without_a_traceback_and_without_its_content(self):
        self.write([row("1")])
        self.plan()
        self.assertIsNone(self.send()[1])
        with open(self.path("ledger.csv"), "a", encoding="utf-8") as fh:
            fh.write("2026-09-30T15:00:00Z,,k2,Africa,acc,Club,2026-09-05,1,1,1,yes,b,B,ok,success,Amara Zibblewick,0\n")
        out, stop = self.run_tool("status")
        self.assertIn("stopped on an unexpected ValueError at sf_backfill.py:", stop)
        self.assertNotIn("Zibblewick", out + stop)

    # ---- the ledger after a close, and open batches
    def test_a_session_whose_batch_is_open_is_not_planned_again_under_another_day(self):
        rows = [row("1")]
        self.write(rows)
        self.plan()
        self.org.fail_at = 1
        self.assertIn("not as planned", self.send()[1])
        self.org.fail_at = None
        _, sessions, held = self.replan(rows)
        self.assertEqual((sessions, [h["reasons"] for h in held]), ([], ["batch_outcome_open"]))
        _, sessions, held = self.replan([dict(rows[0], attendance_date="2026-09-06")])
        self.assertEqual((sessions, [h["reasons"] for h in held]), ([], ["submission_already_sent"]))

    def test_the_names_of_every_sent_batch_must_be_on_file_for_exact_counting(self):
        rows = [row("1", names=GIRLS[:2]), row("2", date="2026-09-12")]
        self.write(rows)
        self.plan()
        self.assertIsNone(self.send("--limit", "1")[1])
        os.remove(self.path("sent_names.json"))
        _, sessions, held = self.replan(rows)
        self.assertEqual((sessions, [h["reasons"] for h in held]), ([], ["club_has_earlier_contacts"]))

    def test_a_lost_answer_is_not_called_nothing_saved_while_salesforce_may_still_be_working(self):
        self.write([row("1")])
        self.plan()
        real_insert, late = self.org.insert, []

        def answer_lost_and_not_committed_yet(sobject, body):
            late.append(body)
            return 0, None
        self.org.insert = answer_lost_and_not_committed_yet
        self.assertIn("A BATCH MAY BE IN SALESFORCE", self.send()[1])
        self.org.insert = real_insert
        bf.SETTLE_AFTER_MINUTES = 10
        self.assertIn("Salesforce may still be working on it - run send again after", self.send()[1])
        self.assertEqual(self.states(), ["sending", "unknown"])
        real_insert("Attendance_Batch__c", late[0])      # it commits after all
        out, stop = self.send()
        self.assertIsNone(stop, stop)
        self.assertEqual((self.states(), len(self.org.inserts)), (["sending", "unknown", "ok"], 1))

    # ---- unclear answers: one POST per batch, and what is looked up afterwards
    def test_a_request_goes_out_once_whatever_comes_back(self):
        for reply, answer in (("Service Unavailable\n503", (503, None)), ("", (0, None)),
                              ('[{"errorCode": "UNKNOWN_EXCEPTION"}]\n500', (500, [{"errorCode": "UNKNOWN_EXCEPTION"}]))):
            posts = []

            def run(argv, input=None, **_):
                if argv[0] == "sf":
                    return type("R", (), {"stdout": json.dumps({"result": {"accessToken": "t", "instanceUrl": "https://x"}})})()
                posts.append(input)
                return type("R", (), {"stdout": reply})()
            with self.subTest(reply[-3:]):
                self.assertEqual(bf.Org("glow", run=run).insert("Attendance_Batch__c", {"Module_Week__c": 3}), answer)
                self.assertEqual(len(posts), 1)          # a write is never sent twice

    def test_a_server_error_after_the_insert_is_looked_up_not_taken_for_nothing_saved(self):
        self.write([row("1")])
        self.plan()
        real_insert = self.org.insert

        def saved_then_500(sobject, body):
            real_insert(sobject, body)
            return 500, [{"errorCode": "UNKNOWN_EXCEPTION", "message": "an unexpected error"}]
        self.org.insert = saved_then_500
        out, stop = self.send()
        self.assertIsNone(stop, stop)
        self.assertEqual((len(self.org.inserts), self.states()), (1, ["sending", "ok"]))

    def test_an_insert_that_raises_is_on_the_ledger_and_settled_by_its_marker(self):
        self.write([row("1")])
        self.plan()
        real_insert = self.org.insert

        def saved_then_raise(sobject, body):
            real_insert(sobject, body)
            raise OSError("connection reset")
        self.org.insert = saved_then_raise
        out, stop = self.send()
        self.assertIn("A BATCH MAY BE IN SALESFORCE", stop)
        self.assertEqual([(r["status"], r["batch_id"]) for r in self.ledger()], [("sending", ""), ("unknown", "")])
        self.org.insert = real_insert
        out, stop = self.send()
        self.assertIsNone(stop, stop)
        self.assertIn("is in Salesforce and as planned", out)
        self.assertEqual((len(self.org.inserts), self.states()), (1, ["sending", "unknown", "ok"]))

    def test_a_run_killed_after_the_sending_line_is_settled_before_anything_is_sent(self):
        self.write([row("1"), row("2", club="River Club", names=GIRLS[:1])])
        self.plan()
        self.assertIsNone(self.send("--only", K)[1])
        with open(self.path("ledger.csv"), encoding="utf-8") as fh:
            lines = fh.read().splitlines(keepends=True)
        with open(self.path("ledger.csv"), "w", encoding="utf-8") as fh:
            fh.writelines(lines[:2])     # header + 'sending': what a kill between insert and read-back leaves
        self.assertIn("1 batch(es) with an unknown outcome", self.run_tool("send")[0])
        out, stop = self.send()
        self.assertIsNone(stop, stop)
        self.assertEqual(self.states(), ["sending", "ok", "sending", "ok"])
        self.assertEqual([b["Account_Name__c"] for b in self.org.inserts], ["Sunrise Club", "River Club"])

    def test_two_batches_with_one_marker_stop_the_run(self):
        self.write([row("1")])
        self.plan()
        real_insert = self.org.insert

        def twice_and_no_answer(sobject, body):
            real_insert(sobject, body)
            real_insert(sobject, body)
            return 0, None
        self.org.insert = twice_and_no_answer
        self.assertIn("A BATCH MAY BE IN SALESFORCE", self.send()[1])
        self.org.insert = real_insert
        self.assertIn("holds 2 batches with this session's marker", self.send()[1])
        self.assertEqual((len(self.org.inserts), self.states()), (2, ["sending", "unknown"]))

    def test_an_open_batch_that_was_removed_is_a_refusal_not_a_traceback(self):
        self.write([row("1")])
        self.plan()
        self.after_insert(lambda: setattr(self.org, "die_after_insert", 1))
        self.assertIn("A BATCH MAY BE IN SALESFORCE", self.send()[1])
        self.org.batches.clear()
        self.assertIn("is no longer in Salesforce - if it was removed on purpose: close", self.send()[1])

    # ---- the read-back
    def test_send_refuses_when_the_club_name_leads_nowhere_or_elsewhere(self):
        def fresh():
            self.org = FakeOrg([account(SUNRISE, "Sunrise Club"), account(RIVER, "River Club")])
            self.write([row("1")])
            self.plan()
        fresh()
        self.org.accounts[0]["Name"] = "Sunrise Girls Club"          # renamed since the plan: a stray would be made
        self.assertIn("no longer leads to exactly its one Club account (0 found)", self.send()[1])
        fresh()
        self.org.accounts[0]["Name"], self.org.accounts[1]["Name"] = "Gone", "Sunrise Club"
        self.assertIn("no longer leads to exactly its one Club account", self.send()[1])
        fresh()
        self.org.accounts[0]["RecordTypeId"] = PARTNER_RECORD_TYPE
        self.assertIn("no longer leads to exactly its one Club account", self.send()[1])
        for change in ({"names": []}, {"attendance_date": "2026-09-05 OR Id != null"}):
            fresh()
            with open(self.path("plan.json"), encoding="utf-8") as fh:
                plan = json.load(fh)
            plan["sessions"][0].update(change)
            with open(self.path("plan.json"), "w", encoding="utf-8") as fh:
                json.dump(plan, fh)
            self.assertIn("the plan entry is not usable", self.send()[1])
        self.assertEqual((self.org.inserts, self.org.strays, self.ledger()), ([], [], []))

    def test_second_batch_is_not_sent_when_somebody_else_added_a_girl(self):
        rows = [row("1", names=GIRLS[:2]), row("2", date="2026-09-12")]
        self.write(rows)
        self.plan()
        self.assertIsNone(self.send("--limit", "1")[1])
        self.org.contacts[SUNRISE]["somebody new"] = ("003STRANGER00001", "2026-09-30T13:30:00.000+0000")
        self.assertIn("somebody else added girls", self.send()[1])
        self.assertEqual((len(self.org.inserts), self.states()), (1, ["sending", "ok"]))
        _, sessions, held = self.replan(rows)
        self.assertEqual((sessions, [h["reasons"] for h in held]), ([], ["club_has_earlier_contacts"]))

    def test_an_exact_batch_that_made_more_girls_than_expected_is_check_and_its_contacts_are_listed(self):
        self.write([row("1")])
        self.plan()
        self.after_insert(lambda: self.org.contacts[SUNRISE].__setitem__(
            "somebody new", ("003STRANGER00001", "2026-09-30T13:30:00.000+0000")))
        out, stop = self.send()
        self.assertIn("4 new participants, 3 expected", stop)
        self.assertIn("3 contacts made by the batch, the club grew by 4", stop)
        self.assertEqual(self.states(), ["sending", "CHECK"])
        self.assertEqual(len(self.contact_lines()), 3)       # the rollback list also has a CHECK batch's contacts
        self.assertTrue(all(line.startswith(self.ledger()[-1]["batch_id"] + ",003NEW") for line in self.contact_lines()))

    def test_a_bounded_batch_that_grew_the_club_by_more_than_its_names_is_check(self):
        self.org = FakeOrg(self.org.accounts, participants={SUNRISE: 9})
        self.write([row("1", names=GIRLS[:2])], decisions=[[K, "accept club_has_earlier_contacts"]])
        self.plan()

        def three_more():
            for i in range(3):
                self.org.contacts[SUNRISE][f"somebody new {i}"] = ("003STRANGER0000%d" % i, self.org.clock())
        self.after_insert(three_more)
        self.assertIn("5 new participants, 2 expected", self.send()[1])
        self.assertEqual(self.states(), ["sending", "CHECK"])

    def test_growth_not_explained_by_the_batch_s_own_contacts_is_check(self):
        self.org = FakeOrg(self.org.accounts, participants={SUNRISE: 9})
        self.org.contacts[SUNRISE]["amara zibblewick"] = ("003OLDX", "2026-03-01T00:00:00.000+0000")
        self.write([row("1", names=GIRLS[:2])], decisions=[[K, "accept club_has_earlier_contacts"]])
        self.plan()
        self.after_insert(lambda: self.org.contacts[SUNRISE].__setitem__(
            "somebody new", ("003STRANGER00001", "2026-09-30T13:30:00.000+0000")))
        out, stop = self.send()
        self.assertIn("1 contacts made by the batch, the club grew by 2", stop)
        self.assertNotIn("new participants", stop)

    def test_a_batch_on_another_account_or_with_two_rows_for_one_girl_is_check(self):
        self.write([row("1")])
        self.plan()
        self.after_insert(lambda: self.org.batches[-1].__setitem__("Account__c", RIVER))
        self.assertIn("the batch landed on another account", self.send()[1])
        self.org = FakeOrg([account(SUNRISE, "Sunrise Club")])
        os.remove(self.path("ledger.csv"))
        self.write([row("1")])
        self.plan()

        def same_girl_twice():
            self.org.rows[-1]["Contact__c"] = self.org.rows[-2]["Contact__c"]
        self.after_insert(same_girl_twice)
        self.assertIn("3 rows for 2 girls, 3 sent", self.send()[1])

    def test_a_success_whose_girls_present_is_not_its_rows_is_check(self):
        for value, wrong in ((3.0, None),                # Salesforce gives the number as a double: equal
                             (2.0, "Girls_Present__c is 2, the batch has 3 rows"),
                             (None, "Girls_Present__c is empty, the batch has 3 rows")):    # a processor without the count
            with self.subTest(value):
                self.org = FakeOrg([account(SUNRISE, "Sunrise Club")])
                if os.path.exists(self.path("ledger.csv")):
                    os.remove(self.path("ledger.csv"))
                self.write([row("1")])
                self.plan()
                self.after_insert(lambda v=value: self.org.batches[-1].__setitem__("Girls_Present__c", v))
                out, stop = self.send()
                if wrong is None:
                    self.assertIsNone(stop, stop)
                    self.assertEqual(self.states(), ["sending", "ok"])
                else:
                    self.assertIn(f"is in Salesforce but not as planned - {wrong}. STOPPED", stop)
                    self.assertEqual(self.states(), ["sending", "CHECK"])
                    self.assertIn(wrong, self.ledger()[-1]["note"])

    # ---- the wire
    def test_a_count_refuses_anything_but_a_number_and_no_read_asks_for_a_contact_s_name(self):
        def org_answering(reply):
            def run(argv, input=None, **_):
                if argv[0] == "sf":
                    return type("R", (), {"stdout": json.dumps({"result": {"accessToken": "t", "instanceUrl": "https://x"}})})()
                return type("R", (), {"stdout": reply})()
            return bf.Org("glow", run=run)
        self.assertEqual(org_answering('{"totalSize": 4, "done": true, "records": []}\n200').count("SELECT COUNT() FROM Contact"), 4)
        for reply in ('{"records": []}\n200', '[{"errorCode": "MALFORMED_QUERY"}]\n400', "\n500", "", '{"totalSize": "4"}\n200'):
            with self.subTest(reply[:20]), self.assertRaises(bf.Refused):
                org_answering(reply).count("SELECT COUNT() FROM Contact")
        self.assertEqual(bf.quoted("Ng'aa \\ Club"), "'Ng\\'aa \\\\ Club'")
        self.write([row("1")])
        self.plan()
        self.assertIsNone(self.run_tool("snapshot", "--vpn-off")[1])
        self.assertIsNone(self.send()[1])
        asked = " ".join(self.org.seen)
        self.assertGreater(len(self.org.seen), 10)
        for field in ("Name FROM Contact", "FirstName", "LastName", "Email", "Birthdate", "Contact__r.Name", "Contact_IDs__c"):
            self.assertNotIn(field, asked)

    def test_the_login_is_refused_unless_it_is_a_plain_https_host_and_a_plain_token(self):
        def org_with(token, url):
            curls = []

            def run(argv, input=None, **_):
                if argv[0] == "sf":
                    return type("R", (), {"stdout": json.dumps({"result": {"accessToken": token, "instanceUrl": url}})})()
                curls.append(input)
                return type("R", (), {"stdout": '{"totalSize": 1}\n200'})()
            return bf.Org("glow", run=run), curls
        for token, url in (("t", "http://example.my.salesforce.com"), ('t"x', "https://example.my.salesforce.com"),
                           ("", "https://example.my.salesforce.com"), ("t\nurl = x", "https://example.my.salesforce.com"),
                           ("t", "https://example.my.salesforce.com@elsewhere"), ("t", "https://a.example/\noutput = x")):
            with self.subTest(url[-18:] + token[:3]):
                org, curls = org_with(token, url)
                with self.assertRaises(bf.Refused):
                    org.count("SELECT COUNT() FROM Account")
                self.assertEqual(curls, [])
        org, curls = org_with("00Dok!token.value_1", "https://example.my.salesforce.com")
        self.assertEqual(org.count("SELECT COUNT() FROM Account"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
