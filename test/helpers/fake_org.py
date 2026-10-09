"""
FakeOrg: Salesforce as far as the back-fill tools can see it (tools/sf_backfill.py, and through
subclasses tools/sf_girls_present.py and tools/fix_module_values.py), with the attendance
processor's rules where they matter: the club is found by name or a stray one is created, the first
batch per club and day wins and a later one is stored as Failed, a batch without names is Failed "No
participants submitted" unless it carries a Girls_Present__c above 0 (an aggregate: a Success
without rows), a Success sets Girls_Present__c to the rows it created and every Failed path clears
it (the processor as deployed 2026-10-07), every new name becomes a contact, and a handled error
leaves the rows made so far behind. Everything in it is fictional.
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from glow.salesforce import CLUB_RECORD_TYPE, Refused  # noqa: E402

ME = "005000000000000MEE"


class FakeOrg:
    """Salesforce, as far as the tool can see it, with the processor's rules."""
    alias = "fake"
    state_queries = {}           # {name: SOQL} answered from state(): sf_backfill's snapshot (STATE_QUERIES)

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
            raise Refused("Salesforce did not answer a read (HTTP 0)")

    def query(self, soql):
        self.seen.append(soql)
        self.read()
        for name, text in self.state_queries.items():
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
            acc = {"Id": "001STRAY%010d" % len(self.strays), "Name": body["Account_Name__c"],
                   "RecordTypeId": CLUB_RECORD_TYPE, "ParentId": None}
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
