"""
FakeOrg: Salesforce as far as the back-fill tools can see it (tools/sf_backfill.py, and through
subclasses tools/sf_girls_present.py and tools/fix_module_values.py), with the attendance
processor's rules where they matter: the club is found by name or a stray one is created, the first
batch per club and day wins and a later one is stored as Failed, a batch without names is Failed "No
participants submitted" unless it carries a Girls_Present__c above 0 (an aggregate: a Success
without rows), a Success sets Girls_Present__c to the rows it created and every Failed path clears
it (the processor as deployed 2026-10-07), every new name becomes a contact, and a handled error
leaves the rows made so far behind. Since 2026-10-24 (ticket #108, `merge_corrections`) a later batch
of a club and day with the same module merges into the day's ORIGINAL batch (the oldest Success):
one row of the original for each ticked girl without a row on that club and day, the contact created
when the club has none matching, the original's Girls_Present__c moved to its own rows, and the
correction stored as Success "merged into <original id>" with no count and no rows of its own; a
correction that adds nobody, names nobody, has another module, or an original with no rows of its
own or with Creator__c 'Partner report' stays Failed "Duplicate". With `merge_corrections` False the
fake is the processor before that day (every later batch Failed "Duplicate"): how a test builds the
history the resend works on. Everything in it is fictional.

Reads: the exact SOQL shapes the tools are known to send, then any explicit-field SELECT on the four
sobjects the fake holds (FIELDS) with a WHERE of conditions joined by AND (=, !=, <, <=, >, >=, LIKE,
IN, NOT IN; text compared as Salesforce does, case ignored; dates and datetimes by their moment),
GROUP BY, ORDER BY and LIMIT. A field the fake does not hold, OR, or a shape it does not know is an
AssertionError, never a silent empty answer.
"""
import datetime
import os
import re
import sys
import unicodedata

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from glow.salesforce import CLUB_RECORD_TYPE, Refused  # noqa: E402

ME = "005000000000000MEE"
DUPLICATE = "Duplicate: A successful batch already exists for this account and date."
# the fields a read may name, per sobject; Contact__r.CreatedDate is a row's contact's CreatedDate
FIELDS = {
    "Account": ("Id", "Name", "RecordTypeId", "ParentId"),
    "Attendance_Batch__c": ("Id", "Name", "Account__c", "Account_Name__c", "Attendance_Date__c", "Module__c",
                            "Module_Week__c", "Module_Year__c", "Contact_IDs__c", "Creator__c", "CreatedDate",
                            "CreatedById", "Processing_Status__c", "Status_Message__c", "Girls_Present__c",
                            "enable_fuzzy_matching__c"),
    "Attendance__c": ("Id", "Attendance_Batch__c", "Account__c", "Attendance_Date__c", "Contact__c", "CreatedDate",
                      "Contact__r.CreatedDate"),
    "Contact": ("Id", "Name", "AccountId", "Contact_Role__c", "CreatedDate"),
}
SOQL_RX = re.compile(r"SELECT (?P<fields>.+?) FROM (?P<sobject>\w+)(?: WHERE (?P<where>.+?))?"
                     r"(?: GROUP BY (?P<group>.+?))?(?: ORDER BY (?P<order>.+?))?(?: LIMIT (?P<limit>\d+))?", re.S)
COND_RX = re.compile(r"(?P<field>[\w.]+)\s*(?P<op>!=|>=|<=|=|>|<|NOT IN|IN|LIKE)\s*"
                     r"(?P<value>'(?:[^'\\]|\\.)*'|\([^)]*\)|[\w:+.-]+)", re.I)
AGG_RX = re.compile(r"(COUNT|COUNT_DISTINCT)\((\w*)\)(?: (\w+))?")
MOMENT_RX = re.compile(r"(\d{4}-\d{2}-\d{2})(?:T(\d{2}:\d{2}:\d{2})(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?)?")


def clean_names(text):
    """The processor's name cleaning (2026-10-22): split on ',', format characters (Cf) removed, any
    run of whitespace or separators one space, trimmed, blanks dropped; a name twice counts once,
    case ignored. The order is the order ticked."""
    out, seen = [], set()
    for part in (text or "").split(","):
        part = "".join(" " if unicodedata.category(c).startswith("Z") else c
                       for c in part if unicodedata.category(c) != "Cf")
        part = " ".join(part.split())
        if part and part.casefold() not in seen:
            seen.add(part.casefold())
            out.append(part)
    return out


def moment(text):
    """A date or datetime literal, or a field's value, as 'yyyy-mm-ddThh:mm:ss' UTC; None when it is
    neither (Salesforce gives '2026-09-30T14:00:01.000+0000', SOQL writes '2026-09-30T14:00:01Z')."""
    m = MOMENT_RX.fullmatch(str(text or "").strip())
    if not m:
        return None
    day, clock, zone = m.groups()
    when = datetime.datetime.fromisoformat(f"{day}T{clock or '00:00:00'}")
    if zone and zone != "Z":
        sign, hours, minutes = (1 if zone[0] == "+" else -1), int(zone[1:3]), int(zone[-2:])
        when -= sign * datetime.timedelta(hours=hours, minutes=minutes)
    return when.strftime("%Y-%m-%dT%H:%M:%S")


def like(pattern, text):
    """SOQL LIKE: `%` any run, `_` one character, case ignored."""
    rx = ".*".join(".".join(re.escape(piece) for piece in part.split("_")) for part in pattern.split("%"))
    return re.fullmatch(rx, text, re.I | re.S) is not None


def soql_value(text):
    """A literal of a condition: 'text' (SOQL escapes), (a, list), null, true/false, a number, or a
    date/datetime left as text."""
    text = text.strip()
    if text.startswith("'"):
        return re.sub(r"\\(.)", r"\1", text[1:-1])
    if text.startswith("("):
        return [soql_value(v) for v in text[1:-1].split(",") if v.strip()]
    low = text.lower()
    if low == "null":
        return None
    if low in ("true", "false"):
        return low == "true"
    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        return float(text)
    return text


def same(value, literal):
    """`=` as Salesforce compares: '' is null, text case ignored, a number by value, a moment by its
    instant."""
    if literal is None:
        return value is None or value == ""
    if value is None or value == "":
        return False
    if isinstance(literal, bool):
        return value == literal
    if isinstance(literal, float):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) == literal
    a, b = moment(value), moment(literal)
    return a == b if a and b else str(value).lower() == str(literal).lower()


def holds(value, op, literal):
    """One condition `field op literal` against a record's value."""
    op = op.upper()
    if op in ("IN", "NOT IN"):
        return any(same(value, item) for item in literal) == (op == "IN")
    if op == "LIKE":
        return value is not None and like(str(literal), str(value))
    if op in ("=", "!="):
        return same(value, literal) == (op == "=")
    if value is None or value == "" or literal is None:
        return False                             # null is neither before nor after anything
    if isinstance(literal, float) or isinstance(value, (int, float)):
        a, b = float(value), float(literal)
    else:
        a, b = (moment(value) or str(value)), (moment(literal) or str(literal))
    return {">": a > b, ">=": a >= b, "<": a < b, "<=": a <= b}[op]


def where_filter(where, known, soql):
    """A predicate on a record for a WHERE of conditions joined by AND (None: everything passes)."""
    if where is None:
        return lambda record: True
    conds = list(COND_RX.finditer(where))
    rest = COND_RX.sub(" _ ", where)
    if not conds or not re.fullmatch(r"(?:\s*_\s*)(?:AND\s*_\s*)*", rest, re.I) or rest.count("_") != len(conds):
        raise AssertionError(f"a WHERE this fake org does not understand (conditions joined by AND only): {soql}")
    parsed = []
    for cond in conds:
        if cond.group("field") not in known:
            raise AssertionError(f"{cond.group('field')}: not a field of this fake's records: {soql}")
        parsed.append((cond.group("field"), cond.group("op"), soql_value(cond.group("value"))))
    return lambda record: all(holds(record.get(field), op, literal) for field, op, literal in parsed)


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
        self.merge_corrections = True    # the processor since 2026-10-24; False: every later batch Failed "Duplicate"

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
        fields, found = self.select(soql)
        if fields == ["COUNT()"]:
            raise AssertionError(f"a COUNT() through query(); count() answers it: {soql}")
        return found

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
        fields, found = self.select(soql)
        if fields != ["COUNT()"]:
            raise AssertionError(f"count() answers a COUNT() query only: {soql}")
        return len(found)

    # ---- any explicit-field SELECT on what the fake holds
    def records(self, sobject):
        """The fake's records of `sobject` with every field of FIELDS (None when unset)."""
        if sobject == "Account":
            found = self.accounts
        elif sobject == "Attendance_Batch__c":
            found = self.batches
        elif sobject == "Attendance__c":
            found = [dict(r, **{"Contact__r.CreatedDate": r.get("contact_created")}) for r in self.rows]
        elif sobject == "Contact":
            found = [{"Id": cid, "Name": name, "AccountId": acc, "Contact_Role__c": "Participant", "CreatedDate": made}
                     for acc, mine in self.contacts.items() for name, (cid, made) in mine.items()]
        else:
            raise AssertionError(f"{sobject}: not an sobject this fake org holds")
        return [{f: r.get(f) for f in FIELDS[sobject]} for r in found]

    def select(self, soql):
        """(the fields named, the records answered - only those fields, in the query's order)."""
        m = SOQL_RX.fullmatch(soql.strip())
        if not m or m.group("sobject") not in FIELDS:
            raise AssertionError(soql)
        known = FIELDS[m.group("sobject")]
        fields = [f.strip() for f in m.group("fields").split(",")]
        plain, aggregates = [], []
        for f in fields:
            if agg := AGG_RX.fullmatch(f):
                kind, on, alias = agg.groups()
                if on and on not in known:
                    raise AssertionError(f"{on}: not a field of this fake's {m.group('sobject')}: {soql}")
                aggregates.append((kind, on, alias or f"expr{len(aggregates)}"))
            elif f in known:
                plain.append(f)
            else:
                raise AssertionError(f"{f}: not a field of this fake's {m.group('sobject')}: {soql}")
        passes = where_filter(m.group("where"), known, soql)
        found = [r for r in self.records(m.group("sobject")) if passes(r)]
        if fields == ["COUNT()"]:
            return fields, found
        if aggregates:
            group = [g.strip() for g in (m.group("group") or "").split(",") if g.strip()]
            if set(plain) != set(group) or any(g not in known for g in group):
                raise AssertionError(f"an aggregate query must GROUP BY exactly the plain fields it names: {soql}")
            buckets = {}
            for r in found:
                buckets.setdefault(tuple(r[g] for g in group), []).append(r)
            if not group and not buckets:
                buckets[()] = []
            found = []
            for key, members in buckets.items():
                out = dict(zip(group, key))
                for kind, on, alias in aggregates:
                    values = [x[on] for x in members if x[on] is not None] if on else members
                    out[alias] = len(set(values)) if kind == "COUNT_DISTINCT" else len(values)
                found.append(out)
            fields = group + [alias for _, _, alias in aggregates]
        if m.group("order"):
            for part in reversed([p.strip() for p in m.group("order").split(",")]):
                words = part.split()
                if words[0] not in fields and words[0] not in known:
                    raise AssertionError(f"ORDER BY {words[0]}: not a field of this query: {soql}")
                found.sort(key=lambda r, f=words[0]: (r.get(f) is not None, str(moment(r.get(f)) or r.get(f) or "")),
                           reverse=len(words) > 1 and words[1].upper() == "DESC")
        if m.group("limit"):
            found = found[:int(m.group("limit"))]
        return fields, [{f: r.get(f) for f in fields} for r in found]

    def merge(self, batch, original, acc_id, day, body, when):
        """The processor's merge rule (deployed 2026-10-24): True when `batch`, a correction of the day
        `original` is the Success of, was merged into it; False when it stays Failed "Duplicate"."""
        own = [r for r in self.rows if r["Attendance_Batch__c"] == original["Id"]]
        if not self.merge_corrections or not own or str(original.get("Creator__c") or "").casefold() == "partner report":
            return False
        if str(body.get("Module__c") or "").casefold() != str(original.get("Module__c") or "").casefold():
            return False
        names = clean_names(body.get("Contact_IDs__c"))
        if not names:
            return False
        on_day = {r["Contact__c"] for r in self.rows if r["Account__c"] == acc_id and r["Attendance_Date__c"] == day}
        mine, adds = self.contacts[acc_id], []
        for name in names:                   # the exact match, the oldest contact first; a girl without one is new
            found = sorted((c for k, c in mine.items() if k == name.casefold()), key=lambda c: (c[1], c[0]))
            if found and found[0][0] in on_day:
                continue
            adds.append((name, found[0] if found else None))
        if not adds:
            return False
        for name, contact in adds:
            if contact is None:
                contact = ("003NEW%09d" % sum(len(c) for c in self.contacts.values()), when)
                mine[name.casefold()] = contact
            self.rows.append({"Id": "a1m%015d" % len(self.rows), "Attendance_Batch__c": original["Id"], "Account__c": acc_id,
                              "Attendance_Date__c": day, "Contact__c": contact[0], "contact_created": contact[1],
                              "CreatedDate": when})
        original["Girls_Present__c"] = sum(1 for r in self.rows if r["Attendance_Batch__c"] == original["Id"])
        batch.update(Processing_Status__c="Success", Status_Message__c=f"merged into {original['Id']}", Girls_Present__c=None)
        return True

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
                 "Account_Name__c": body["Account_Name__c"], "Attendance_Date__c": day, "Processing_Status__c": "Success",
                 "Creator__c": body["Creator__c"], "Status_Message__c": self.message or "Processed successfully.",
                 "CreatedById": ME, "CreatedDate": when, "Girls_Present__c": typed, "Module__c": body.get("Module__c"),
                 "Module_Week__c": body.get("Module_Week__c"), "Module_Year__c": body.get("Module_Year__c"),
                 "Contact_IDs__c": body.get("Contact_IDs__c"), "enable_fuzzy_matching__c": body.get("enable_fuzzy_matching__c")}
        names = [n.strip() for n in (body.get("Contact_IDs__c") or "").split(",") if n.strip()]
        originals = sorted((b for b in self.batches if b["Account__c"] == acc["Id"] and b["Attendance_Date__c"] == day
                            and b["Processing_Status__c"] == "Success"), key=lambda b: (b["CreatedDate"], b["Id"]))
        if originals:
            if not self.merge(batch, originals[0], acc["Id"], day, body, when):
                batch.update(Processing_Status__c="Failed", Status_Message__c=DUPLICATE)
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
            self.rows.append({"Id": "a1m%015d" % len(self.rows), "Attendance_Batch__c": batch["Id"], "Account__c": acc["Id"],
                              "Attendance_Date__c": day, "Contact__c": contact[0], "contact_created": contact[1],
                              "CreatedDate": when})
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
