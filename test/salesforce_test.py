#!/usr/bin/env python3
"""
Offline tests for glow/salesforce.py, the one Salesforce client (found by `make py`'s unittest
discovery): the CLI login and the token on curl's stdin (CliLoginAndCurl), the GLOW Sync login
(GlowSyncLogin), queryAll and DELETE (OrgQueryAllAndDelete). Everything here is fictional: ids,
tokens, secrets and names are invented. The tools' own uses are tested beside each tool.
"""
import json
import os
import re
import sys
import types
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow import salesforce          # noqa: E402

P1 = "001000000000000PAA"
SUN = "001000000000000SUN"


def aff_id(n):
    return f"a0x{n:015d}"


class CliLoginAndCurl(unittest.TestCase):
    """glow.salesforce.cli_login and Org: the CLI's stored login, the token on curl's stdin, pages."""

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

        org = salesforce.Org("glow", run=run)
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

        org = salesforce.Org("glow", run=run)
        self.assertEqual(org.query("SELECT Id FROM Account"), [{"Id": "1"}, {"Id": "2"}])
        self.assertEqual(len(seen), 2)
        pages["first"] = {"done": False, "records": []}
        with self.assertRaises(salesforce.Refused) as stop:
            org.query("SELECT Id FROM Account")
        self.assertIn("part of an answer", str(stop.exception))
        pages["first"] = {"totalSize": 1}
        with self.assertRaises(salesforce.Refused):
            org.query("SELECT Id FROM Account")

    def test_no_login_and_a_missing_cli_are_clear_refusals(self):
        org = salesforce.Org("glow", run=lambda *a, **k: type("R", (), {"stdout": '{"status": 1}', "stderr": ""})())
        with self.assertRaises(salesforce.Refused) as stop:
            org.query("SELECT Id FROM Account")
        self.assertIn("sf org login web --alias glow", str(stop.exception))

        def missing(*a, **k):
            raise FileNotFoundError("sf")
        with self.assertRaises(salesforce.Refused):
            salesforce.Org("glow", run=missing).count("SELECT COUNT() FROM Account")

    def test_the_login_is_refused_unless_it_is_a_plain_https_host_and_a_plain_token(self):
        def org_with(token, url):
            curls = []

            def run(argv, input=None, **_):
                if argv[0] == "sf":
                    return type("R", (), {"stdout": json.dumps({"result": {"accessToken": token, "instanceUrl": url}})})()
                curls.append(input)
                return type("R", (), {"stdout": '{"totalSize": 1}\n200'})()
            return salesforce.Org("glow", run=run), curls
        for token, url in (("t", "http://example.my.salesforce.com"), ('t"x', "https://example.my.salesforce.com"),
                           ("", "https://example.my.salesforce.com"), ("t\nurl = x", "https://example.my.salesforce.com"),
                           ("t", "https://example.my.salesforce.com@elsewhere"), ("t", "https://a.example/\noutput = x")):
            with self.subTest(url[-18:] + token[:3]):
                org, curls = org_with(token, url)
                with self.assertRaises(salesforce.Refused):
                    org.count("SELECT COUNT() FROM Account")
                self.assertEqual(curls, [])
        org, curls = org_with("00Dok!token.value_1", "https://example.my.salesforce.com")
        self.assertEqual(org.count("SELECT COUNT() FROM Account"), 1)


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
        for argv_i, config_i in calls:                            # curl follows no redirect, reads no curlrc
            self.assertEqual(argv_i[:2], ["curl", "-q"])
            self.assertFalse({"-L", "--location", "--location-trusted"} & set(argv_i))
            self.assertNotRegex(config_i, r"(?m)^\s*(-L\b|-{0,2}location)")
        org.update("Account", SUN, {"ParentId": P1})
        self.assertIn(f"/sobjects/Account/{SUN}", calls[-1][1])
        self.assertIn('request = "PATCH"', calls[-1][1])
        org.revoke()
        self.assertIn("oauth2/revoke", calls[-1][1])
        self.assertIsNone(org.token)

    def test_a_refused_login_says_why_without_the_body_or_the_secret(self):
        far = json.dumps({"error": "invalid_grant", "error_description": "x" * 110 + " S3CRETfake"}) + "\n400"
        for body, says in (('{"error": "invalid_grant", "error_description": "user is frozen S3CRETfake"}\n400', "user is frozen"),
                           (far, "invalid_grant"),
                           ('{"error": "invalid_client_id", "error_description": "bad 3MVG9fakeclientid"}\n400', "invalid_client_id"),
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
                self.assertNotIn("3MVG9fakeclientid", str(stop.exception))
                self.assertNotIn("html", str(stop.exception))
                self.assertEqual(len(calls), 1)                   # nothing sent after a refused login
        org = salesforce.Org(login=salesforce.client_credentials("", ""))
        with self.assertRaises(salesforce.Refused) as stop:
            org.count("SELECT COUNT() FROM Account")
        self.assertIn("not configured", str(stop.exception))

    def test_the_secret_scanner_knows_salesforce_credentials(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import check_secrets
        token = "00D" + "Ab1" * 5 + "!" + "AQ4AQ.x_9" * 4           # assembled: no literal one in this file
        key, secret = "3MVG9" + "aB3._" * 14, "9F" * 32
        for text, rule in ((token, "Salesforce token"), (key, "Salesforce consumer key"),
                           (secret, "64-hex secret"), (secret.lower(), "64-hex secret"),
                           (token.replace("!", "%21"), "Salesforce token")):
            with self.subTest(rule):
                hits = check_secrets.scan_text("x " + text + " y", "t")
                self.assertTrue(any(rule in h for h in hits), hits)
                self.assertTrue(all(text not in h for h in hits))   # printed masked
        self.assertEqual(check_secrets.scan_text("00Dfake!tok 3MVG9fakeclientid " + "ab" * 16 + "c", "t"), [])


class OrgQueryAllAndDelete(unittest.TestCase):
    """glow.salesforce.Org.query_all pages through queryAll; Org.delete is one DELETE."""

    def org(self, replies):
        configs = []

        def run(argv, input=None, **_):
            configs.append(input)
            return types.SimpleNamespace(stdout=replies.pop(0))
        return salesforce.Org(alias="x", run=run, login=lambda run: ("https://x.example", "tok")), configs

    def test_query_all_follows_its_pages(self):
        first = {"done": False, "records": [{"Id": "a", "IsDeleted": True}],
                 "nextRecordsUrl": f"/services/data/{salesforce.API}/queryAll/01gFAKE-2000"}
        org, configs = self.org([json.dumps(first) + "\n200", json.dumps({"done": True, "records": [{"Id": "b"}]}) + "\n200"])
        records = org.query_all("SELECT Id, IsDeleted FROM Contact WHERE IsDeleted = true")
        self.assertEqual([r["Id"] for r in records], ["a", "b"])
        self.assertIn(f'url = "https://x.example/services/data/{salesforce.API}/queryAll?q=SELECT%20Id', configs[0])
        self.assertIn(f'url = "https://x.example/services/data/{salesforce.API}/queryAll/01gFAKE-2000"', configs[1])
        for bad in ("https://elsewhere.example/services/data/v67.0/queryAll/01g-2000", "/services/data/v67.0/sobjects/x",
                    None):
            with self.subTest(bad):
                org, _ = self.org([json.dumps(dict(first, nextRecordsUrl=bad)) + "\n200"])
                with self.assertRaises(salesforce.Refused):
                    org.query_all("SELECT Id FROM Contact")
        # query() itself is unchanged: it follows /query/ pages only
        org, _ = self.org([json.dumps(first) + "\n200"])
        with self.assertRaises(salesforce.Refused):
            org.query("SELECT Id FROM Contact")
        org, configs = self.org([json.dumps(dict(first, nextRecordsUrl="/services/data/v67.0/query/01g-2000")) + "\n200",
                                 json.dumps({"done": True, "records": []}) + "\n200"])
        self.assertEqual(len(org.query("SELECT Id FROM Contact")), 1)
        self.assertIn("/services/data/v67.0/query?q=", configs[0])

    def test_delete_is_one_delete_request(self):
        org, configs = self.org(["\n204", '[{"errorCode": "ENTITY_IS_DELETED", "message": "gone"}]\n404'])
        self.assertEqual(org.delete("npe5__Affiliation__c", aff_id(1)), (204, None))
        self.assertIn(f'url = "https://x.example/services/data/{salesforce.API}/sobjects/npe5__Affiliation__c/{aff_id(1)}"',
                      configs[0])
        self.assertIn('request = "DELETE"', configs[0])
        self.assertNotIn("data = ", configs[0])
        status, answer = org.delete("npe5__Affiliation__c", aff_id(1))
        self.assertEqual((status, answer[0]["errorCode"]), (404, "ENTITY_IS_DELETED"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
