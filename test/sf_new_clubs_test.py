#!/usr/bin/env python3
"""
Offline tests for tools/sf_new_clubs.py (found by `make py`'s unittest discovery; glow/salesforce.py's
GLOW Sync login: test/salesforce_test.py). Everything here is fictional: clubs, partners,
girls and Salesforce ids are invented.
"""
import contextlib
import csv
import io
import json
import os
import re
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import sf_new_clubs as sfn            # noqa: E402
import helpers                        # noqa: E402,F401  the VPN check's stand-in (#251)
from glow import salesforce          # noqa: E402

CLUB, HOUSE, OTHER = sfn.CLUB_RECORD_TYPE, sfn.PARTNER_RECORD_TYPE, "012000000000000OTH"
P1, P2 = "001000000000000PAA", "001000000000000PBB"
SUN, RIV = "001000000000000SUN", "001000000000000RIV"
PILOT = next(iter(sorted(sfn.ON_HOLD_ACCOUNTS)))
ROSTER_COLS = ["girl_id", "partner", "club", "region", "full_name", "last_name", "status",
               "added_date", "removed_date", "source"]


def gid(code, n):
    """A fictional girl id, built here so no literal one sits in the file."""
    return "-".join((code, "ZQ", f"{n:03d}"))


def acct(i, name, rt=CLUB, parent=None, desc=None):
    return {"Id": i, "Name": name, "RecordTypeId": rt, "ParentId": parent, "Description": desc, "CreatedById": None}


def fillers(n=410):
    return [acct(f"001F{i:014d}", f"Filler Org {i}", OTHER) for i in range(n)]


def base_accounts():
    return fillers() + [acct(P1, "Example Partner Org", HOUSE), acct(P2, "Second Partner", HOUSE),
                        acct(SUN, "Sunrise Club", CLUB, P1, "GLOW club code SUNRISEC; created from the club registry"),
                        acct(RIV, "River Club", CLUB, P2, "GLOW club code RIVERCLU; created from the club registry")]


class FakeOrg:
    """Answers like Salesforce for the queries the step makes; any other query is a test failure."""

    def __init__(self, accounts, insert="ok"):
        self.accounts, self.mode, self.inserts, self.seen, self.revoked = accounts, insert, [], [], False
        self.token = "t"

    def count(self, soql):
        self.seen.append(soql)
        assert soql == "SELECT COUNT() FROM Account", soql
        return len(self.accounts)

    def query(self, soql):
        self.seen.append(soql)
        if soql == sfn.ACCOUNTS:
            return [dict(a, attributes={"type": "Account"}) for a in self.accounts]
        m = re.fullmatch(r"SELECT [A-Za-z, ]+ FROM Account WHERE Name = '((?:[^'\\]|\\.)*)'", soql)
        assert m, soql
        name = re.sub(r"\\(.)", r"\1", m.group(1))
        return [dict(a) for a in self.accounts if a["Name"].lower() == name.lower()]

    GRANT = {"createable": True, "fields": [{"name": n, "createable": True}
                                            for n in ("Name", "ParentId", "Description", "RecordTypeId")],
             "recordTypeInfos": [{"recordTypeId": CLUB, "available": True}]}

    def describe(self, sobject):
        assert sobject == "Account"
        return getattr(self, "grant", self.GRANT)

    def insert(self, sobject, body):
        assert sobject == "Account"
        self.inserts.append(body)
        new = acct(f"001NEW{len(self.inserts):012d}", body["Name"], body["RecordTypeId"], body["ParentId"],
                   body["Description"])
        if self.mode == "ok":
            self.accounts.append(new)
            return 201, {"id": new["Id"], "success": True}
        if self.mode == "refuse":
            return 400, [{"errorCode": "FIELD_CUSTOM_VALIDATION_EXCEPTION", "message": "Zara Quillfeather is wrong"}]
        if self.mode == "unknown_saved":
            self.accounts.append(new)
            return 0, None
        if self.mode == "gateway_saved":                  # a 502/504 page after the POST committed
            self.accounts.append(new)
            return 502, None
        return 0, None                                    # unknown and lost

    def revoke(self):
        self.revoked = True
        self.token = None


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.partners = os.path.join(self.tmp.name, "partners.csv")
        with open(self.partners, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(salesforce.PARTNER_COLS)
            w.writerow(["Example Partner", P1, "Example Partner Org"])
            w.writerow(["Second Partner", P2, "Second Partner"])
        self.roster = os.path.join(self.tmp.name, "roster.csv")
        self.write_roster([("SUNRISEC", "Example Partner", "Sunrise Club"),
                           ("RIVERCLU", "Second Partner", "River Club"),
                           ("DAWNCLUB", "Example Partner", "Dawn Club")])

    def write_roster(self, clubs, extra=()):
        with open(self.roster, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(ROSTER_COLS)
            for n, (code, partner, club) in enumerate(clubs):
                for k in (1, 2):
                    w.writerow([f"{code}-ZQ-{n}{k:02d}", partner, club, "U.S", f"Ada{k} Fictional", "Fictional",
                                "active", "2026-09-01", "", "test"])
            for row in extra:
                w.writerow(row)

    def step(self, org, mode="apply"):
        logged = []
        s = sfn.Step(mode, org, self.roster, log=logged.append, partners_path=self.partners, today="2026-10-07")
        s.logged = logged
        return s

    @staticmethod
    def plan(*clubs):
        """A region's sync summary: new clubs (qid None) and the creates naming them."""
        return {"creates": [{"club": c[0], "girls": 2} for c in clubs],
                "sf_names": [{"qid": None, "club": c[0], "value": c[1] if len(c) > 1 else c[0],
                              "partner": c[2] if len(c) > 2 else "Example Partner"} for c in clubs]}


class SalesforceNewClubs(Fixture):
    # ---- the comparison and the names
    def test_the_regions_are_the_forms_table_s(self):
        from glow import forms
        self.assertIs(sfn.REGIONS, forms.REGIONS)          # one list of the regional forms: glow/forms.py

    def test_names_that_may_be_created_unattended(self):
        for ok in ("Sunrise Club", "Dawn's Club", "Niñas de Oro", "GLOW Club (Kibera) 2", "Club A/B - Example Partner",
                   "St. Mary's"):
            with self.subTest(ok):
                self.assertEqual(sfn.name_problems(ok), [])
        for bad in ("Sun & Moon", "Club, North", 'The "Best" Club', "Club\u00a0X", " Club", "Club  X", "Club\u200bX",
                    "Nin\u0303as", "Dawn\u2019s Club", "", "x" * 256, "Dawn\u02bcs Club", "Club \u00b2",
                    "Club \u00bd", "Uni\ufb01ed Club", "\u1218\u1295 Club", "Club \u0663", "A\u030angel Club",
                    "\U0001E900 Club"):
            with self.subTest(repr(bad)):
                self.assertTrue(sfn.name_problems(bad))

    def test_codes_come_from_active_girl_ids_and_a_club_with_two_codes_gets_none(self):
        self.write_roster([("SUNRISEC", "Example Partner", "Sunrise Club")],
                          extra=[[gid("OTHERCOD", 901), "Example Partner", "Sunrise Club", "U.S", "Bo Fictional",
                                  "Fictional", "inactive", "2026-09-01", "2026-09-20", "test"],
                                 [gid("AAAA", 1), "Example Partner", "Two Codes", "U.S", "C", "F", "active", "", "", ""],
                                 [gid("BBBB", 1), "Example Partner", "Two Codes", "U.S", "D", "F", "active", "", "", ""]])
        codes = sfn.read_codes(self.roster)
        self.assertEqual(codes[("example partner", "sunrise club")], "SUNRISEC")   # the inactive girl does not count
        self.assertIsNone(codes[("example partner", "two codes")])
        with open(self.roster, encoding="utf-8") as fh:
            text = fh.read()
        with open(self.roster, "w", encoding="utf-8") as fh:
            fh.write("\ufeff" + text.replace(",active,", ",Active,"))         # a BOM, a capital: as the sync reads it
        self.assertEqual(sfn.read_codes(self.roster)[("example partner", "sunrise club")], "SUNRISEC")

    def test_the_partner_map_is_read_strictly(self):
        self.assertEqual(salesforce.read_partners(self.partners)["example partner"], (P1, "Example Partner Org"))
        with open(self.partners, "a", encoding="utf-8") as fh:
            fh.write(f"example partner,{P2},Again\n")
        with self.assertRaises(sfn.Refused):
            salesforce.read_partners(self.partners)
        with open(self.partners, "w", encoding="utf-8") as fh:
            fh.write(",".join(salesforce.PARTNER_COLS) + f"\nNameless Partner,{P1},\n")
        with self.assertRaises(sfn.Refused):
            salesforce.read_partners(self.partners)                             # an unnamed partner account
        self.assertEqual(len(salesforce.read_partners()), 50)       # the real map: one line per partner (#212: 50)

    def test_the_real_map_holds_omid_foundation(self):
        """#212: OMID Foundation (Asia) maps to its Household account, so its new clubs get that parent."""
        real = salesforce.read_partners()
        self.assertEqual(real.get("omid foundation"), ("001RP000002nJZiYAM", "OMID Foundation"))
        self.assertEqual([k for k, (pid, _) in real.items() if pid == "001RP000002nJZiYAM"], ["omid foundation"],
                         "001RP000002nJZiYAM is OMID Foundation's account alone")

    # ---- the guard
    def test_a_read_that_is_not_the_whole_org_stops_every_write(self):
        for accounts, says in ((base_accounts()[300:], "only"),                        # View All gone
                               ([a for a in base_accounts() if a["Id"] != P2], P2)):   # a mapped partner unseen
            with self.subTest(says):
                org = FakeOrg(accounts)
                s = self.step(org)
                self.assertFalse(s.prepare())
                self.assertIn(says, s.broken)
                self.assertEqual(s.create("U.S", self.plan(("Dawn Club",))), 0)
                self.assertEqual(org.inserts, [])
                self.assertEqual(s.check({"U.S": []}), (0, 0))
                self.assertTrue(any("without a Salesforce account" in t for t, _ in s.attention))

        class Short(FakeOrg):
            def count(self, soql):
                return len(self.accounts) + 1                    # a page went missing
        s = self.step(Short(base_accounts()))
        self.assertFalse(s.prepare())
        self.assertIn("records for a count", s.broken)

    def test_every_clause_of_the_guard_stops_the_run(self):
        self.write_roster([(f"CODE{n:04d}", "Example Partner", f"Club {n}") for n in range(20)])
        s = self.step(FakeOrg(base_accounts()))                          # 2 Club accounts for 20 clubs
        self.assertFalse(s.prepare())
        self.assertIn("Club accounts visible", s.broken)
        self.setUp()
        accounts = base_accounts()
        next(a for a in accounts if a["Id"] == P1)["RecordTypeId"] = OTHER   # a partner of another type
        s = self.step(FakeOrg(accounts))
        self.assertFalse(s.prepare())
        self.assertIn("not a Household account", s.broken)
        accounts = base_accounts()
        accounts[1] = accounts[0]                                          # one record twice, one missing
        s = self.step(FakeOrg(accounts))
        self.assertFalse(s.prepare())
        self.assertIn("records for a count", s.broken)
        s = self.step(FakeOrg(fillers(4501) + base_accounts()[410:]))     # past the processor's limit: said
        self.assertTrue(s.prepare())
        self.assertTrue(any("4505 Accounts" in t for t, _ in s.attention))

    def test_without_the_right_to_create_an_apply_run_only_shows_the_bodies(self):
        for grant in ({**FakeOrg.GRANT, "createable": False},
                      {**FakeOrg.GRANT, "recordTypeInfos": []},
                      {**FakeOrg.GRANT, "fields": FakeOrg.GRANT["fields"][:1]}):
            with self.subTest(sorted(grant)):
                org = FakeOrg(base_accounts())
                org.grant = grant
                s = self.step(org)
                self.assertTrue(s.prepare())                             # the check still runs
                self.assertEqual(s.mode, "plan")
                self.assertEqual(s.create("U.S", self.plan(("Dawn Club",))), 0)
                self.assertEqual(org.inserts, [])
                self.assertTrue(any("cannot create Club accounts" in t for t, _ in s.attention))
                self.assertTrue(any("would create" in t for t, _ in s.attention))
        s = self.step(FakeOrg(base_accounts()))
        s.prepare()
        self.assertIn("describe ok", "\n".join(s.logged))

    def test_reads_are_retried_and_a_write_never(self):
        tries = []

        def retry(fn, label):
            for _ in range(2):
                try:
                    return fn()
                except sfn.Refused:
                    tries.append(label)
            return fn()

        class Flaky(FakeOrg):
            fails = {"count": 1, "where": 1}

            def count(self, soql):
                if self.fails["count"]:
                    self.fails["count"] -= 1
                    raise sfn.Refused("Salesforce did not answer a count (HTTP 503)")
                return FakeOrg.count(self, soql)

            def query(self, soql):
                if "WHERE" in soql and self.fails["where"]:
                    self.fails["where"] -= 1
                    raise sfn.Refused("Salesforce did not answer a read (HTTP 503)")
                return FakeOrg.query(self, soql)
        org = Flaky(base_accounts(), insert="unknown_lost")
        s = sfn.Step("apply", org, self.roster, log=lambda m: None, partners_path=self.partners, retry=retry)
        self.assertTrue(s.prepare())
        self.assertEqual(s.create("U.S", self.plan(("Dawn Club",))), 0)
        self.assertEqual(len(org.inserts), 1)                            # unknown, and still one POST
        self.assertEqual(tries, ["Salesforce Account read", "Salesforce re-query"])

    def test_a_household_partner_without_parent_is_required(self):
        accounts = base_accounts()
        next(a for a in accounts if a["Id"] == P1)["ParentId"] = P2
        s = self.step(FakeOrg(accounts))
        self.assertFalse(s.prepare())
        self.assertIn("not a Household account without a parent", s.broken)

    # ---- creating
    def test_a_new_club_is_created_under_its_partner_and_read_back(self):
        org = FakeOrg(base_accounts())
        s = self.step(org)
        self.assertTrue(s.prepare())
        self.assertEqual(s.create("U.S", self.plan(("Dawn Club",))), 1)
        self.assertEqual(org.inserts, [{"Name": "Dawn Club", "RecordTypeId": CLUB, "ParentId": P1,
                                        "Description": "GLOW club code DAWNCLUB; created by the automatic sync 2026-10-07"}])
        self.assertEqual(len(s.created), 1)
        self.assertTrue(any("check it by hand" in t for t, _ in s.attention) == sfn.CONFIRM_CREATES)
        # a clean create raises nothing else: any ATTENTION item turns the auto-sync run red (exit 2)
        self.assertEqual(len(s.attention), 1 if sfn.CONFIRM_CREATES else 0)
        # the next run finds it right: nothing more to create, the check is clean
        s2 = self.step(org)
        self.assertTrue(s2.prepare())
        self.assertEqual(s2.create("U.S", self.plan(("Dawn Club",))), 0)
        self.assertEqual(s2.attention, [])
        self.assertEqual(len(org.inserts), 1)
        names = [{"qid": 7, "club": c, "value": c, "partner": p} for c, p in
                 (("Sunrise Club", "Example Partner"), ("River Club", "Second Partner"), ("Dawn Club", "Example Partner"))]
        self.assertEqual(s2.check({"U.S": names}), (3, 0))

    def test_plan_mode_only_shows_the_body(self):
        org = FakeOrg(base_accounts())
        s = self.step(org, mode="plan")
        self.assertTrue(s.prepare())
        self.assertEqual(s.create("U.S", self.plan(("Dawn Club",))), 0)
        self.assertEqual(org.inserts, [])
        title, detail = next((t, d) for t, d in s.attention if "would create" in t)
        self.assertEqual(json.loads(detail)["ParentId"], P1)

    def test_a_mode_other_than_plan_or_apply_is_refused_before_anything_runs(self):
        org = FakeOrg(base_accounts())
        for mode in ("off", "APPLY", None):
            with self.subTest(mode), self.assertRaises(sfn.Refused) as stop:
                self.step(org, mode=mode)
            self.assertIn("not plan or apply", str(stop.exception))
        self.assertEqual((org.seen, org.inserts), ([], []))

    def test_more_than_five_in_a_region_creates_none(self):
        clubs = [(f"Club {n}", "Example Partner") for n in "ABCDEF"]
        self.write_roster([(f"CLUB{n}XX", p, c) for (c, p), n in zip(clubs, "ABCDEF")])
        org = FakeOrg(base_accounts())
        s = self.step(org)
        self.assertTrue(s.prepare())
        self.assertEqual(s.create("U.S", self.plan(*[(c,) for c, _ in clubs])), 0)
        self.assertEqual(org.inserts, [])
        self.assertTrue(any("more than 5" in t for t, _ in s.attention))

    def test_five_in_a_region_are_created(self):
        clubs = [f"Club {n}" for n in "ABCDE"]
        self.write_roster([(f"CLUB{n}XX", "Example Partner", c) for c, n in zip(clubs, "ABCDE")])
        org = FakeOrg(base_accounts())
        s = self.step(org)
        s.prepare()
        self.assertEqual(s.create("U.S", self.plan(*[(c,) for c in clubs])), 5)
        self.assertEqual(len(org.inserts), 5)

    def test_only_this_region_s_new_clubs_are_created(self):
        org = FakeOrg(base_accounts())
        s = self.step(org)
        s.prepare()
        plan = self.plan(("Dawn Club",))
        plan["creates"] = []                                     # on the form already, or not this run's
        self.assertEqual(s.create("U.S", plan), 0)
        plan = self.plan(("Ghost Club",))                         # not an active Roster club
        self.assertEqual(s.create("U.S", plan), 0)
        self.assertEqual(org.inserts, [])

    def test_a_rename_not_made_in_salesforce_creates_no_twin(self):
        self.write_roster([("SUNRISEC", "Example Partner", "Sunrise Girls")])      # renamed in the sheet
        org = FakeOrg(base_accounts())
        s = self.step(org)
        s.prepare()
        self.assertEqual(s.create("U.S", self.plan(("Sunrise Girls",))), 0)
        self.assertEqual(org.inserts, [])
        detail = next(d for t, d in s.attention if "not created" in t)
        self.assertIn("club code SUNRISEC is on 001000000000000SUN", detail)
        self.assertIn("rename that account", detail)

    def test_a_name_already_in_salesforce_is_never_created_again(self):
        for account, says in ((acct("001000000000000HHH", "DAWN CLUB", HOUSE), "partner/household"),
                              (acct("001000000000000STR", "Dawn Club", CLUB), "set ParentId = " + P1),
                              (acct("001000000000000XXX", "Dawn Club", CLUB, P2), "Club, parent " + P2)):
            with self.subTest(says):
                org = FakeOrg(base_accounts() + [account])
                s = self.step(org)
                s.prepare()
                self.assertEqual(s.create("U.S", self.plan(("Dawn Club",))), 0)
                self.assertEqual(org.inserts, [])
                detail = next(d for t, d in s.attention if "not created" in t)
                self.assertIn(says, detail)
                self.assertNotIn("Body for a hand create", detail)            # never a body for a name in use

    def test_a_name_equal_only_as_java_compares_case_is_the_club_s_account(self):
        # equal lengths, unequal case-folds: Java's equalsIgnoreCase (glow.salesforce.sf_match) takes question 5
        # 'Istanbul Girls' for the account 'ıstanbul Girls' (a dotless i), so the processor books there: no twin
        # is created, and the check finds the club's one account
        self.write_roster([("ISTANBUL", "Example Partner", "Istanbul Girls")])
        org = FakeOrg(base_accounts() + [acct("001000000000000IST", "\u0131stanbul Girls", CLUB, P1)])
        s = self.step(org)
        s.prepare()
        self.assertEqual(s.create("U.S", self.plan(("Istanbul Girls",))), 0)
        self.assertEqual((org.inserts, s.attention), ([], []))
        on_form = [{"qid": 1, "club": "Istanbul Girls", "value": "Istanbul Girls", "partner": "Example Partner"}]
        self.assertEqual(s.check({"U.S": on_form}), (1, 0))
        self.assertEqual(s.attention, [])

    def test_what_salesforce_has_is_judged_before_the_name_partner_and_code(self):
        self.write_roster([("SUNMOONX", "Example Partner", "Sun & Moon"), ("HOPELITE", "Example Partner", "Hope Light")])
        org = FakeOrg(base_accounts() + [acct("001000000000000SMX", "Sun & Moon", CLUB, P1, "GLOW club code SUNMOONX; x"),
                                         acct("001000000000000HOP", "Hope Light", HOUSE)])
        s = self.step(org)
        s.prepare()
        self.assertEqual(s.create("U.S", self.plan(("Sun & Moon",), ("Hope Light",))), 0)
        said = json.dumps(s.attention)
        self.assertNotIn("Sun & Moon", said)                             # its right account exists: ok, silent
        self.assertIn("partner/household", said)
        self.assertNotIn("Body for a hand create", said)
        # a club whose code is on its right account and on an older one: a person decides
        self.write_roster([("DAWNCLUB", "Example Partner", "Dawn Club")])
        org = FakeOrg(base_accounts() + [acct("001000000000000DAW", "Dawn Club", CLUB, P1, "GLOW club code DAWNCLUB; x"),
                                         acct("001000000000000OLD", "Old Dawn", CLUB, P1, "GLOW club code DAWNCLUB; x")])
        s = self.step(org)
        s.prepare()
        self.assertEqual(s.create("U.S", self.plan(("Dawn Club",))), 0)
        self.assertIn("001000000000000OLD", json.dumps(s.attention))

    def test_a_nearly_equal_name_is_left_to_a_person(self):
        self.write_roster([("NINASXXX", "Example Partner", "Niñas Club")])
        org = FakeOrg(base_accounts() + [acct("001000000000000NIN", "Ninas Club", CLUB, P1)])
        s = self.step(org)
        s.prepare()
        self.assertEqual(s.create("U.S", self.plan(("Niñas Club",))), 0)
        self.assertIn("nearly the same name", next(d for t, d in s.attention if "not created" in t))

    def test_an_account_appearing_since_the_read_stops_the_create(self):
        org = FakeOrg(base_accounts())
        s = self.step(org)
        s.prepare()
        org.accounts.append(acct("001000000000000RAC", "Dawn Club", CLUB))      # the processor won the race
        self.assertEqual(s.create("U.S", self.plan(("Dawn Club",))), 0)
        self.assertEqual(org.inserts, [])
        self.assertTrue(any("appeared since the read" in t for t, _ in s.attention))

    def test_a_refused_create_stops_the_region_and_repeats_only_error_codes(self):
        self.write_roster([("DAWNCLUB", "Example Partner", "Dawn Club"), ("DUSKCLUB", "Example Partner", "Dusk Club")])
        org = FakeOrg(base_accounts(), insert="refuse")
        s = self.step(org)
        s.prepare()
        self.assertEqual(s.create("U.S", self.plan(("Dawn Club",), ("Dusk Club",))), 0)
        self.assertEqual(len(org.inserts), 1)                     # the second is not tried
        text = json.dumps(s.attention) + "\n".join(s.logged)
        self.assertIn("FIELD_CUSTOM_VALIDATION_EXCEPTION", text)
        self.assertNotIn("Quillfeather", text)
        self.assertIn("Body for a hand create", text)

    def test_a_refusal_quoting_names_in_capitals_repeats_only_its_code(self):
        class Shouting(FakeOrg):
            def insert(self, sobject, body):
                self.inserts.append(body)
                return 400, [{"errorCode": "FIELD_CUSTOM_VALIDATION_EXCEPTION",
                              "message": "DAWN CLUB: ZARA QUILLFEATHER IS NOT ALLOWED"}]
        s = self.step(Shouting(base_accounts()))
        s.prepare()
        self.assertEqual(s.create("U.S", self.plan(("Dawn Club",))), 0)
        detail = next(d for t, d in s.attention if "refused the create" in t)
        self.assertTrue(detail.startswith("FIELD_CUSTOM_VALIDATION_EXCEPTION\n\nBody for a hand create: "), detail)
        for word in ("QUILLFEATHER", "ZARA", "ALLOWED"):          # the club's own name is shown anyway
            self.assertNotIn(word, json.dumps(s.attention) + "\n".join(s.logged))

    def test_an_unknown_outcome_is_settled_by_reading_back_and_never_retried(self):
        org = FakeOrg(base_accounts(), insert="unknown_saved")
        s = self.step(org)
        s.prepare()
        self.assertEqual(s.create("U.S", self.plan(("Dawn Club",))), 1)
        self.assertEqual(len(org.inserts), 1)
        org = FakeOrg(base_accounts(), insert="unknown_lost")
        s = self.step(org)
        s.prepare()
        self.assertEqual(s.create("U.S", self.plan(("Dawn Club",))), 0)
        self.assertEqual(len(org.inserts), 1)                     # never retried
        self.assertIn("U.S", s.stopped)
        self.assertIn("read again in ten minutes", next(d for t, d in s.attention if "check by hand" in t))
        s.check({"U.S": [{"qid": 9, "club": "Dawn Club", "value": "Dawn Club", "partner": "Example Partner"}]})
        said = next(d for t, d in s.attention if "need a person" in t)
        self.assertIn("did not settle", said)
        self.assertNotIn("create it by hand", said)                     # no twin invited
        org = FakeOrg(base_accounts(), insert="gateway_saved")           # a 5xx is unknown too, not a refusal
        s = self.step(org)
        s.prepare()
        self.assertEqual(s.create("U.S", self.plan(("Dawn Club",))), 1)
        self.assertEqual(len(org.inserts), 1)

    def test_a_read_back_that_differs_from_the_body_stops_the_region(self):
        self.write_roster([("DAWNCLUB", "Example Partner", "Dawn Club"), ("DUSKCLUB", "Example Partner", "Dusk Club")])
        for name, change in (("a trigger re-parents it", lambda a, r: a.update(ParentId=P2)),
                             ("the answer names another record", lambda a, r: r.update(id="001000000000000OTH"))):
            with self.subTest(name):
                class Twisted(FakeOrg):
                    def insert(self, sobject, body, change=change):
                        status, answer = FakeOrg.insert(self, sobject, body)
                        change(self.accounts[-1], answer)
                        return status, answer
                org = Twisted(base_accounts())
                s = self.step(org)
                s.prepare()
                self.assertEqual(s.create("U.S", self.plan(("Dawn Club",), ("Dusk Club",))), 0)
                self.assertEqual(len(org.inserts), 1)                    # no further write in the region
                self.assertEqual(s.created, [])
                self.assertIn("U.S", s.stopped)
                self.assertTrue(any("check by hand" in t for t, _ in s.attention))

    def test_a_partner_not_in_the_map_or_a_doubtful_name_is_left_to_a_person(self):
        self.write_roster([("NEWPART1", "Brand New Partner", "Lakeside Club"), ("SUNMOONX", "Example Partner", "Sun & Moon")])
        org = FakeOrg(base_accounts())
        s = self.step(org)
        s.prepare()
        self.assertEqual(s.create("U.S", self.plan(("Lakeside Club", "Lakeside Club", "Brand New Partner"),
                                                   ("Sun & Moon",))), 0)
        self.assertEqual(org.inserts, [])
        said = json.dumps(s.attention)
        self.assertIn("not in glow/sf_partners.csv", said)
        self.assertIn("U+0026", said)
        self.assertIn("Body for a hand create", said)             # the doubtful name gets its body

    # ---- the check
    def test_the_check_reports_every_wrong_account_with_its_fix(self):
        self.write_roster([("SUNRISEC", "Example Partner", "Sunrise Club"), ("RIVERCLU", "Second Partner", "River Club"),
                           ("DAWNCLUB", "Example Partner", "Dawn Club"), ("DUSKCLUB", "Example Partner", "Dusk Club"),
                           ("MOONCLUB", "Example Partner", "Moon Club"), ("STARCLUB", "Second Partner", "Star Club"),
                           ("LAKECLUB", "Example Partner", "Lake Club")])
        accounts = base_accounts() + [
            acct("001000000000000DAW", "Dawn Club", CLUB),                              # partner-less
            acct("001000000000000DU1", "Dusk Club", CLUB, P1), acct("001000000000000DU2", "dusk club", CLUB, P1),
            acct("001000000000000MOO", "Moon Club", CLUB, P2),                          # another partner
            acct("001000000000000STA", "Star Club", HOUSE),                             # not a Club
            acct("001000000000000ODD", "Nobody's Club", CLUB)]                         # a stray
        next(a for a in accounts if a["Id"] == RIV)["Description"] = "GLOW club code OTHERONE; x"
        s = self.step(FakeOrg(accounts), mode="plan")
        self.assertTrue(s.prepare())
        names = [{"qid": n, "club": c, "value": c, "partner": p} for n, (c, p) in enumerate(
            (("Sunrise Club", "Example Partner"), ("River Club", "Second Partner"), ("Dawn Club", "Example Partner"),
             ("Dusk Club", "Example Partner"), ("Moon Club", "Example Partner"), ("Star Club", "Second Partner"),
             ("Lake Club", "Example Partner"), ("Retired Club", "Example Partner")), 1)]
        ok, wrong = s.check({"U.S": names})
        self.assertEqual((ok, wrong), (1, 7))                     # only Sunrise is right; Retired is not checked
        said = next(d for t, d in s.attention if "need a person" in t)
        for words in ("set ParentId = " + P1, "2 accounts are named 'Dusk Club'", "under another partner",
                      "not a Club account", "carries club code OTHERONE", "no account named 'Lake Club'",
                      "001000000000000ODD"):
            self.assertIn(words, said)
        self.assertEqual(s.check({"U.S": names[:1]}, clash_names=["Sunrise Club"])[0], 0)   # a clash is not judged here

    def test_the_pilots_on_hold_are_never_strays(self):
        s = self.step(FakeOrg(base_accounts() + [acct(PILOT, "Pilot Club", CLUB)]), mode="plan")
        s.prepare()
        self.assertEqual(s.check({"U.S": []}), (0, 0))

    def test_a_pilot_account_and_a_code_on_two_accounts_are_reported(self):
        self.write_roster([("SUNRISEC", "Example Partner", "Sunrise Club"), ("PILOTCLU", "Example Partner", "Pilot Club")])
        s = self.step(FakeOrg(base_accounts() + [acct(PILOT, "Pilot Club", CLUB, P1),
                                                 acct("001000000000000OLS", "Old Sunrise", CLUB, P2,
                                                      "GLOW club code SUNRISEC; x")]), mode="plan")
        s.prepare()
        names = [{"qid": 1, "club": "Sunrise Club", "value": "Sunrise Club", "partner": "Example Partner"},
                 {"qid": 2, "club": "Pilot Club", "value": "Pilot Club", "partner": "Example Partner"}]
        s.check({"U.S": names})
        said = next(d for t, d in s.attention if "need a person" in t)
        self.assertIn("pilot accounts on hold", said)
        self.assertIn("club code SUNRISEC is also on 001000000000000OLS", said)

    def test_strays_need_every_form_and_unjudged_regions_still_count_as_users(self):
        accounts = base_accounts() + [acct("001000000000000DAW", "Dawn Club", CLUB)]       # partner-less
        names = {"U.S": [{"qid": 1, "club": "Sunrise Club", "value": "Sunrise Club", "partner": "Example Partner"}],
                 "Asia": [{"qid": 2, "club": "Dawn Club", "value": "Dawn Club", "partner": "Example Partner"}]}
        s = self.step(FakeOrg(accounts), mode="plan")
        s.prepare()
        self.assertEqual(s.check(names, on_form={"U.S"}), (1, 0))       # Asia's club uses it: no stray
        s = self.step(FakeOrg(accounts), mode="plan")
        s.prepare()
        self.assertEqual(s.check({"U.S": names["U.S"]}, complete=False), (1, 0))   # a form unread: no strays
        s = self.step(FakeOrg(accounts), mode="plan")
        s.prepare()
        self.assertEqual(s.check({"U.S": names["U.S"]}), (1, 1))        # every form read: the stray is said
        said = next(d for t, d in s.attention if "need a person" in t)
        self.assertIn("'Dawn Club' (Club, parent none): a Club account without a partner that no club on a form uses", said)
        self.assertIn("or the account of a club whose form is disabled", said)   # a disabled form's club is not matched

    def test_a_case_match_outside_the_bmp_is_left_to_a_person(self):
        self.write_roster([("ADLAMXXX", "Example Partner", "\U0001E900 Club")])
        s = self.step(FakeOrg(base_accounts() + [acct("001000000000000ADL", "\U0001E922 Club", CLUB, P1)]), mode="plan")
        s.prepare()
        s.check({"U.S": [{"qid": 1, "club": "\U0001E900 Club", "value": "\U0001E900 Club", "partner": "Example Partner"}]})
        self.assertIn("outside the BMP", json.dumps(s.attention, ensure_ascii=False))

    # ---- the standalone check
    def test_the_check_command_needs_vpn_off_and_never_writes(self):
        summary = os.path.join(self.tmp.name, "plan_us.json")
        with open(summary, "w", encoding="utf-8") as fh:
            json.dump({"sf_names": [{"qid": 3, "club": "Sunrise Club", "value": "Sunrise Club",
                                     "partner": "Example Partner"}]}, fh)
        with self.assertRaises(SystemExit) as stop:
            sfn.main(["check", "--roster", self.roster, "--summary", summary])
        self.assertIn("--vpn-off", str(stop.exception))
        org = FakeOrg(base_accounts())
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as stop:
            sfn.main(["check", "--vpn-off", "--roster", self.roster, "--summary", summary], org=org,
                     partners_path=self.partners)
        self.assertEqual(stop.exception.code, 0)
        self.assertIn("1 ok, 0 need a person", out.getvalue())
        org = FakeOrg(base_accounts() + [acct("001000000000000ODD", "Nobody's Club", CLUB)])   # a partner-less stray
        for given, disabled, reported in ((["U.S"], [], False),                                  # three forms unread
                                          (["U.S", "Asia", "Africa"], ["Latin America"], True)):  # one disabled
            with self.subTest(disabled):
                paths = []
                for region in given:
                    paths.append(os.path.join(self.tmp.name, f"plan_{region}.json"))
                    with open(paths[-1], "w", encoding="utf-8") as fh:
                        json.dump({"region": region, "sf_names": [{"qid": 3, "club": "Sunrise Club",
                                   "value": "Sunrise Club", "partner": "Example Partner"}] if region == "U.S" else []}, fh)
                out = io.StringIO()
                argv = ["check", "--vpn-off", "--roster", self.roster, "--summary", *paths]
                for region in disabled:
                    argv += ["--disabled", region]
                with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
                    sfn.main(argv, org=FakeOrg(list(org.accounts)), partners_path=self.partners)
                self.assertEqual("001000000000000ODD" in out.getvalue(), reported)
        self.assertEqual(org.inserts, [])
        cli = salesforce.Org("glow", run=lambda *a, **k: self.fail("a CLI login is never revoked"))
        cli.token, cli.base = "t", "https://x.example"
        cli.revoke()
        self.assertIsNone(cli.token)


class AutoSyncSalesforce(unittest.TestCase):
    """How tools/auto_sync.py runs the step: when, on what, and what it leaves behind."""

    def setUp(self):
        import types
        from unittest import mock
        import auto_sync
        self.auto_sync, self.mock, self.types = auto_sync, mock, types
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_obj(self, apply=True, **extra):
        args = self.types.SimpleNamespace(apply=apply, out=self.tmp.name, max_creates=5, max_updates=20,
                                          trigger="test", run_url="", **extra)
        return self.auto_sync.Run(args)

    def test_the_modes(self):
        env = {"SF_CLIENT_ID": "id", "SF_CLIENT_SECRET": "secret"}
        for sf_sync, flag, creds, mode in (("", False, True, None), ("off", True, True, None),
                                           ("plan", False, False, None), ("plan", True, True, "plan"),
                                           ("apply", False, True, "plan"), ("apply", True, True, "apply"),
                                           ("APPLY ", True, True, "apply")):
            with self.subTest((sf_sync, flag, creds)):
                run = self.run_obj(apply_salesforce=flag)
                with self.mock.patch.dict(os.environ, {"SF_SYNC": sf_sync, **(env if creds else {})}, clear=True), \
                        self.mock.patch.object(sfn.Step, "prepare", lambda self: True), \
                        self.mock.patch.object(self.auto_sync.Run, "sf_watch", lambda self, org, now=None: None,
                                               create=True), \
                        self.mock.patch("builtins.print"):
                    run.sf_start(os.path.join(self.tmp.name, "roster.csv"))
                self.assertEqual(run.sf.mode if run.sf else None, mode)
                self.assertEqual(run.attention, [])
        run = self.run_obj()
        with self.mock.patch.dict(os.environ, {"SF_SYNC": "yes"}, clear=True), self.mock.patch("builtins.print"):
            run.sf_start("x.csv")
        self.assertIsNone(run.sf)
        self.assertIn("SF_SYNC is not off, plan or apply", run.attention[0][0])

    def region(self, apply, text, applied_names=None, warnings=(), sf=None, backup_fails=False):
        """Run.region("Africa") over a fabricated dry run with a recording Salesforce step."""
        order = []
        run = self.run_obj(apply=apply)

        class Rec:
            def create(self, region, plan):
                order.append(("sf_create", region, [c["club"] for c in plan["creates"]]))
        run.sf = sf or Rec()
        dry = {"creates": [{"club": "Dawn Club", "partner": "Example Partner", "girls": 2}], "updates": [],
               "deletes": [], "rules": 25, "warnings": list(warnings), "calls": ["CREATE roster 'Dawn Club' (2 girls)"],
               "sf_names": [{"qid": None, "club": "Dawn Club", "value": "Dawn Club", "partner": "Example Partner"}]}

        def sync_(csv_path, region, form, apply, summary_path=None):
            order.append(("apply" if apply else "dry", region))
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(dict(dry, sf_names=applied_names) if apply and applied_names else dry, f)
            return self.types.SimpleNamespace(returncode=0, stdout=text, stderr="")
        clean = {"error_conditions": 0, "salesforce": True, "rule_problems": [], "languages": ["a"] * 12,
                 "region_check": {"missing_from_form": [], "not_in_roster": [], "rosters_out_of_date": []}}

        def cmd(argv, label):
            order.append((label,))
            return self.types.SimpleNamespace(returncode=1 if backup_fails and label == "backup" else 0,
                                              stdout=json.dumps([clean]), stderr="")
        with self.mock.patch.object(run, "sync", sync_), self.mock.patch.object(run, "cmd", cmd), \
                self.mock.patch.object(run, "read_status", lambda form: "ENABLED"), \
                self.mock.patch.object(run, "save_conditions", lambda form: None), self.mock.patch("builtins.print"):
            run.region("Africa", os.path.join(self.tmp.name, "roster.csv"))
        return run, order

    TEXT = ("Roster: 2 active clubs in Africa (4 girls); 9 clubs overall\n"
            "\nDRY RUN (use --apply to write):\n  - CREATE roster 'Dawn Club' (2 girls)\n")

    def test_the_accounts_come_before_the_form_and_only_when_it_applies(self):
        run, order = self.region(False, self.TEXT)
        self.assertNotIn("sf_create", [o[0] for o in order])
        self.assertNotIn("Africa", run.sf_on_form)                 # a dry-run region is not checked
        now = [{"qid": "77", "club": "Dawn Club", "value": "Dawn Club", "partner": "Example Partner"}]
        run, order = self.region(True, self.TEXT, applied_names=now)
        steps = [o[0] for o in order]
        self.assertEqual(steps[:4], ["dry", "backup", "sf_create", "apply"])    # after the backup, before the form
        self.assertEqual(order[2], ("sf_create", "Africa", ["Dawn Club"]))
        self.assertIn("Africa", run.sf_on_form)
        self.assertEqual(run.sf_names["Africa"], now)              # what the form sends AFTER the apply
        run, order = self.region(True, self.TEXT, backup_fails=True)
        self.assertNotIn("sf_create", [o[0] for o in order])          # a failed backup: nothing anywhere

    def test_a_region_not_applied_creates_no_account(self):
        q5 = "Old Club: " + self.auto_sync.SF_NAME_CHANGE + " 'Old Club' -> 'New Club'"
        run, order = self.region(True, self.TEXT, warnings=[q5])
        self.assertIn("attention", [r[7] for r in run.results])
        self.assertNotIn("sf_create", [o[0] for o in order])
        self.assertNotIn("Africa", run.sf_on_form)

    def test_a_failing_create_step_never_keeps_the_form_from_applying(self):
        class Boom:
            def __init__(self):
                self.attention = []

            def create(self, region, plan):
                raise AttributeError("odd answer")

            def warn(self, title, detail=""):
                self.attention.append(("SF: " + title, detail))
        boom = Boom()
        run, order = self.region(True, self.TEXT, sf=boom)
        self.assertEqual([o[0] for o in order][:3], ["dry", "backup", "apply"])
        self.assertIn("the create step failed (AttributeError)", boom.attention[0][0])

    def test_a_failing_prepare_never_stops_the_run(self):
        run = self.run_obj(apply_salesforce=True)

        def boom(step):
            raise TypeError("unexpected")
        with self.mock.patch.dict(os.environ, {"SF_SYNC": "apply", "SF_CLIENT_ID": "i", "SF_CLIENT_SECRET": "s"}), \
                self.mock.patch.object(sfn.Step, "prepare", boom), \
                self.mock.patch.object(self.auto_sync.Run, "sf_watch", lambda self, org, now=None: None,
                                       create=True), \
                self.mock.patch("builtins.print"):
            run.sf_start("roster.csv")
        self.assertIn("TypeError", run.sf.broken)
        self.assertTrue(any("not ready" in t for t, _ in run.sf.attention))

    def test_the_end_check_gets_every_region_and_judges_those_on_the_form(self):
        run = self.run_obj()
        seen = []

        class Rec:
            mode, created, broken, attention = "plan", [], None, []

            def check(self, names, clashes, on_form=None, complete=True):
                seen.append((sorted(names), sorted(on_form), complete))
                return 0, 0

            def close(self):
                pass
        run.sf = Rec()
        run.sf_names = {"Africa": [], "Asia": []}      # Asia: attention - its sf_names are the PLANNED values
        run.sf_on_form = {"Africa"}
        with self.mock.patch("builtins.print"):
            run.sf_finish(None)
        self.assertEqual(seen, [(["Africa", "Asia"], ["Africa"], False)])   # two forms unread: no strays

    def test_a_disabled_forms_region_counts_as_complete_and_an_unread_status_does_not(self):
        # the U.S form DISABLED: its region is skipped - never synced, no sf_names - yet every other
        # form's names were read, so the strays are judged (a disabled form's clubs keep their
        # accounts, under their partner). A status that cannot be read is a failed region: that
        # form is unread this run, and no stray is reported
        seen = []

        class Rec:
            mode, created, broken, attention = "plan", [], None, []

            def check(self, names, clashes, on_form=None, complete=True):
                seen.append((sorted(names), sorted(on_form), complete))
                return 0, 0

            def close(self):
                pass
        others = {r: [] for r in self.auto_sync.REGIONAL_FORMS if r != "U.S"}
        for status, complete in (("DISABLED", True), (RuntimeError("boom"), False)):
            with self.subTest(status):
                run = self.run_obj()
                run.sf = Rec()

                def status_(form, status=status):
                    if isinstance(status, Exception):
                        raise status
                    return status
                with self.mock.patch.object(run, "read_status", status_), self.mock.patch("builtins.print"):
                    run.region("U.S", os.path.join(self.tmp.name, "roster.csv"))
                    run.sf_names.update(others)                 # the three other forms, read and as planned
                    run.sf_on_form.update(others)
                    run.sf_finish(None)
                self.assertEqual(run.results[0][7], "skipped" if complete else "failed")
                self.assertEqual(run.skipped, {"U.S"} if complete else set())
                self.assertNotIn("U.S", run.sf_names)
                self.assertEqual(seen.pop(), (sorted(others), sorted(others), complete))
        self.assertEqual(seen, [])

    def test_the_end_step_turns_errors_into_attention_and_writes_one_synclog_row(self):
        run = self.run_obj(synclog=True)
        closed = []

        class Broken:
            mode, created, broken, today = "apply", [], None, "2026-10-07"

            def __init__(self):
                self.attention = []

            def warn(self, title, detail=""):
                self.attention.append(("SF: " + title, detail))

            def check(self, names, clashes, on_form=None, complete=True):
                raise RuntimeError("boom")

            def close(self):
                closed.append(True)
        run.sf = Broken()
        with self.mock.patch("builtins.print"):
            run.sf_finish(None)
        self.assertEqual(closed, [True])
        self.assertIn("the end-of-run step failed (RuntimeError)", run.attention[0][0])
        (row,) = run.results
        self.assertEqual((row[2], row[3], row[7]), ("Salesforce", "apply", "attention"))

    def test_child_processes_never_see_the_salesforce_credentials(self):
        seen = {}

        def fake(argv, **kw):
            seen.update(kw["env"])
            return self.types.SimpleNamespace(returncode=0, stdout="", stderr="")
        run = self.run_obj()
        with self.mock.patch.dict(os.environ, {"SF_CLIENT_SECRET": "s", "SF_CLIENT_ID": "i", "JOTFORM_API_KEY": "k"}), \
                self.mock.patch.object(self.auto_sync.subprocess, "run", fake), self.mock.patch("builtins.print"):
            run.cmd(["true"], "x")
        self.assertIn("JOTFORM_API_KEY", seen)
        self.assertFalse([k for k in seen if k.startswith("SF_")])

    def test_the_sf_pending_row_and_its_columns(self):
        with open(os.path.join(REPO, "appsscript", "FormHandlers.gs"), encoding="utf-8") as fh:
            gs = re.search(r"const SF_PENDING_COLS = \[([^\]]*)\]", fh.read()).group(1)
        self.assertEqual(re.findall(r"'([^']+)'", gs), sfn.SF_PENDING_COLS)
        head = sfn.SF_PENDING_COLS
        row = dict.fromkeys(head, "")
        values = [head] + [[dict(row, partner=p, club=c, status=s)[h] for h in head] for p, c, s in (
            ("Example Partner", "Dawn Club", "done"), ("Example Partner", "Dawn Club", "Pending "),
            ("Second Partner", "Dawn Club", "pending"))]
        self.assertEqual(sfn.pending_cell(values, "example partner", "DAWN CLUB"), (3, head.index("status") + 1))
        self.assertIsNone(sfn.pending_cell(values + [values[2]], "Example Partner", "Dawn Club"))   # two: none
        self.assertIsNone(sfn.pending_cell([["a", "b"]], "Example Partner", "Dawn Club"))
        self.assertIsNone(sfn.pending_cell([], "Example Partner", "Dawn Club"))
        rev = [list(reversed(r)) for r in values]
        self.assertEqual(sfn.pending_cell(rev, "Example Partner", "Dawn Club"), (3, rev[0].index("status") + 1))

    def pending_run(self, synclog, reads):
        writes, reads = [], list(reads)
        run = self.run_obj(synclog=synclog)

        class Done:
            mode, broken, today = "apply", None, "2026-10-07"
            created = [("U.S", sfn.Club("U.S", "Example Partner", "Dawn Club", "Dawn Club", "DAWNCLUB"), "001x")]

            def __init__(self):
                self.attention = []

            def warn(self, title, detail=""):
                self.attention.append(("SF: " + title, detail))

            def check(self, names, clashes, on_form=None, complete=True):
                return 1, 0

            def close(self):
                pass
        run.sf = Done()
        sc = self.auto_sync.sc
        with self.mock.patch.object(sc, "read_tab", lambda svc, title: reads.pop(0)), \
                self.mock.patch.object(sc, "write_cell", lambda *a: writes.append(a[1:])), \
                self.mock.patch("builtins.print"):
            run.sf_finish(object())
        return run, writes

    def test_sf_pending_is_marked_only_with_synclog_and_only_while_the_row_stays_put(self):
        head = sfn.SF_PENDING_COLS
        row = dict(dict.fromkeys(head, ""), partner="Example Partner", club="Dawn Club", status="pending")
        mine, other = [row[h] for h in head], [dict(row, club="Other Club")[h] for h in head]
        self.assertEqual(self.pending_run(False, [[head, mine]] * 2)[1], [])
        run, writes = self.pending_run(True, [[head, mine]] * 2)
        self.assertEqual(writes, [("SF Pending", 2, head.index("status") + 1, "done (auto 2026-10-07)")])
        self.assertEqual(run.attention, [])
        self.assertEqual(self.pending_run(True, [[head, mine], [head, other, mine]])[1], [])

    def test_one_cell_is_written_raw_and_read_back(self):
        import sheets_client as sc
        calls = []

        class Values:
            def update(self, **kw):
                calls.append(("update", kw["range"], kw["valueInputOption"], kw["body"]))
                return self

            def get(self, **kw):
                calls.append(("get", kw["range"]))
                return self

            def execute(self):
                return {"values": [["done (auto 2026-10-07)"]]}
        svc = self.types.SimpleNamespace(spreadsheets=lambda: self.types.SimpleNamespace(values=Values))
        with self.mock.patch.object(sc, "spreadsheet_id", lambda: "sheet"):
            sc.write_cell(svc, "SF Pending", 3, 9, "done (auto 2026-10-07)")
            self.assertEqual(calls[0][1:], ("'SF Pending'!I3", "RAW", {"values": [["done (auto 2026-10-07)"]]}))
            sc.write_cell(svc, "SF Pending", 2, 27, "done (auto 2026-10-07)")
            self.assertEqual(calls[2][1], "'SF Pending'!AA2")
            with self.assertRaises(SystemExit):
                sc.write_cell(svc, "SF Pending", 2, 1, "something else")


if __name__ == "__main__":
    unittest.main(verbosity=1)
