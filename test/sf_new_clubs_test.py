#!/usr/bin/env python3
"""
Offline tests for tools/sf_new_clubs.py and glow/salesforce.py's GLOW Sync login (imported by
test/python_test.py, so `make py` runs them). Everything here is fictional: clubs, partners,
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
            w.writerow(sfn.PARTNER_COLS)
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
    def test_the_processor_s_comparison(self):
        m = sfn.sf_match
        self.assertTrue(m("Sunrise Club", "sunrise club"))
        self.assertTrue(m("  Sunrise Club\t", "Sunrise Club"))          # question 5 is trimmed ...
        self.assertFalse(m("Sunrise Club", " Sunrise Club"))           # ... the Account name is not
        self.assertFalse(m("Sunrise  Club", "Sunrise Club"))           # inner spaces count
        self.assertFalse(m("Sunrise Club", "Sunrise Club"))       # a no-break space is not a space
        self.assertFalse(m(" Sunrise Club", "Sunrise Club"))      # nor trimmed (it is above U+0020)
        self.assertFalse(m("Straße", "STRASSE"))                       # one character never becomes two
        self.assertTrue(m("Niñas Valientes", "NIÑAS VALIENTES"))
        self.assertFalse(m("Ninas Valientes", "Niñas Valientes"))      # accents count
        self.assertTrue(m("İstanbul Girls", "istanbul girls"))   # Java maps İ to i, one character to one

    def test_names_that_may_be_created_unattended(self):
        for ok in ("Sunrise Club", "Dawn's Club", "Niñas de Oro", "GLOW Club (Kibera) 2", "Club A/B - Example Partner",
                   "St. Mary's"):
            with self.subTest(ok):
                self.assertEqual(sfn.name_problems(ok), [])
        for bad in ("Sun & Moon", "Club, North", 'The "Best" Club', "Club X", " Club", "Club  X", "Club​X",
                    "Niñas", "Dawn’s Club", "", "x" * 256):
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

    def test_the_partner_map_is_read_strictly(self):
        self.assertEqual(sfn.read_partners(self.partners)["example partner"], (P1, "Example Partner Org"))
        with open(self.partners, "a", encoding="utf-8") as fh:
            fh.write(f"example partner,{P2},Again\n")
        with self.assertRaises(sfn.Refused):
            sfn.read_partners(self.partners)
        self.assertEqual(len(sfn.read_partners()), 49)       # the real map: one line per partner

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
        # the next run finds it right: nothing more to create, the check is clean
        s2 = self.step(org)
        self.assertTrue(s2.prepare())
        self.assertEqual(s2.create("U.S", self.plan(("Dawn Club",))), 0)
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

    def test_more_than_five_in_a_region_creates_none(self):
        clubs = [(f"Club {n}", "Example Partner") for n in "ABCDEF"]
        self.write_roster([(f"CLUB{n}XX", p, c) for (c, p), n in zip(clubs, "ABCDEF")])
        org = FakeOrg(base_accounts())
        s = self.step(org)
        self.assertTrue(s.prepare())
        self.assertEqual(s.create("U.S", self.plan(*[(c,) for c, _ in clubs])), 0)
        self.assertEqual(org.inserts, [])
        self.assertTrue(any("more than 5" in t for t, _ in s.attention))

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
                self.assertIn(says, next(d for t, d in s.attention if "not created" in t))

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
        self.assertEqual(org.inserts, [])
        self.assertTrue(org.revoked)


class GlowSyncLogin(unittest.TestCase):
    """glow.salesforce.client_credentials: the secret never on a command line or in a message."""

    def org_with(self, reply):
        calls = []

        def run(argv, input=None, **_):
            calls.append((argv, input))
            return type("R", (), {"stdout": reply(input)})()
        return salesforce.Org(login=salesforce.client_credentials("3MVG9fakeclientid", "S3CRETfake", "https://x.example")), calls, run

    def test_the_login_sends_the_secret_in_the_body_only(self):
        def reply(config):
            if "oauth2/token" in config:
                return json.dumps({"access_token": "00Dfake!tok", "instance_url": "https://x.example"}) + "\n200"
            return '{"totalSize": 3}\n200'
        org, calls, run = self.org_with(reply)
        org.run = run
        self.assertEqual(org.count("SELECT COUNT() FROM Account"), 3)
        argv, config = calls[0]
        self.assertTrue(all("S3CRET" not in part and "00Dfake" not in part for c in calls for part in c[0]))
        self.assertIn('url = "https://x.example/services/oauth2/token"', config)
        self.assertIn("client_secret=S3CRETfake", re.search(r'^data = "(.*)"$', config, re.M).group(1))
        self.assertIn('noproxy = "*"', config)
        self.assertIn('header = "Authorization: Bearer 00Dfake!tok"', calls[1][1])
        self.assertNotIn("-L", calls[1][0])                       # curl follows no redirect
        org.update("Account", SUN, {"ParentId": P1})
        self.assertIn(f"/sobjects/Account/{SUN}", calls[-1][1])
        self.assertIn('request = "PATCH"', calls[-1][1])
        org.revoke()
        self.assertIn("oauth2/revoke", calls[-1][1])
        self.assertIsNone(org.token)

    def test_a_refused_login_says_why_without_the_body_or_the_secret(self):
        for body, says in (('{"error": "invalid_grant", "error_description": "user is frozen S3CRETfake"}\n400', "user is frozen"),
                           ('{"error": "invalid_client"}\n401', "invalid_client"),
                           ("<html>gateway</html>\n502", "no readable answer"),
                           (json.dumps({"access_token": "t", "instance_url": "https://elsewhere.example"}) + "\n200", "another address"),
                           (json.dumps({"access_token": 't"x', "instance_url": "https://x.example"}) + "\n200", "not a plain token")):
            with self.subTest(says):
                org, calls, run = self.org_with(lambda _c, b=body: b)
                org.run = run
                with self.assertRaises(salesforce.Refused) as stop:
                    org.count("SELECT COUNT() FROM Account")
                self.assertIn(says, str(stop.exception))
                self.assertNotIn("S3CRET", str(stop.exception))
                self.assertNotIn("html", str(stop.exception))
                self.assertEqual(len(calls), 1)                   # nothing sent after a refused login
        org = salesforce.Org(login=salesforce.client_credentials("", ""))
        with self.assertRaises(salesforce.Refused) as stop:
            org.count("SELECT COUNT() FROM Account")
        self.assertIn("not configured", str(stop.exception))

    def test_the_secret_scanner_knows_salesforce_credentials(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import check_secrets                                       # noqa: E402
        token = "00D" + "Ab1" * 5 + "!" + "AQ4AQ.x_9" * 4           # assembled: no literal one in this file
        key, secret = "3MVG9" + "aB3._" * 14, "9F" * 32
        for text, rule in ((token, "Salesforce token"), (key, "Salesforce consumer key"),
                           (secret, "64-hex secret"), (secret.lower(), "64-hex secret")):
            with self.subTest(rule):
                hits = check_secrets.scan_text("x " + text + " y", "t")
                self.assertTrue(any(rule in h for h in hits), hits)
                self.assertTrue(all(text not in h for h in hits))   # printed masked
        self.assertEqual(check_secrets.scan_text("00Dfake!tok 3MVG9fakeclientid " + "ab" * 16 + "c", "t"), [])



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
                        self.mock.patch("builtins.print"):
                    run.sf_start(os.path.join(self.tmp.name, "roster.csv"))
                self.assertEqual(run.sf.mode if run.sf else None, mode)
                self.assertEqual(run.attention, [])
        run = self.run_obj()
        with self.mock.patch.dict(os.environ, {"SF_SYNC": "yes"}, clear=True), self.mock.patch("builtins.print"):
            run.sf_start("x.csv")
        self.assertIsNone(run.sf)
        self.assertIn("SF_SYNC is not off, plan or apply", run.attention[0][0])

    def region(self, apply, text, applied_names=None):
        """Run.region("Africa") over a fabricated dry run with a recording Salesforce step."""
        order = []
        run = self.run_obj(apply=apply)

        class Rec:
            def create(self, region, plan):
                order.append(("sf_create", region, [c["club"] for c in plan["creates"]]))
        run.sf = Rec()
        dry = {"creates": [{"club": "Dawn Club", "partner": "Example Partner", "girls": 2}], "updates": [],
               "deletes": [], "rules": 25, "warnings": [], "calls": ["CREATE roster 'Dawn Club' (2 girls)"],
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
            return self.types.SimpleNamespace(returncode=0, stdout=json.dumps([clean]), stderr="")
        with self.mock.patch.object(run, "sync", sync_), self.mock.patch.object(run, "cmd", cmd), \
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
        self.assertEqual(steps[:3], ["dry", "sf_create", "backup"])    # before the backup and the apply
        self.assertEqual(order[1], ("sf_create", "Africa", ["Dawn Club"]))
        self.assertIn("Africa", run.sf_on_form)
        self.assertEqual(run.sf_names["Africa"], now)              # what the form sends AFTER the apply

    def test_the_end_step_turns_errors_into_attention_and_writes_one_synclog_row(self):
        run = self.run_obj(synclog=True)
        closed = []

        class Broken:
            mode, created, broken, today = "apply", [], None, "2026-10-07"

            def __init__(self):
                self.attention = []

            def warn(self, title, detail=""):
                self.attention.append(("SF: " + title, detail))

            def check(self, names, clashes):
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
