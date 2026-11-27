#!/usr/bin/env python3
"""
Offline tests for glow/salesforce.py, the one Salesforce client, and glow/private_files.py (found
by `make py`'s unittest discovery): the CLI login and the token on curl's stdin (CliLoginAndCurl),
the GLOW Sync login (GlowSyncLogin), queryAll and DELETE (OrgQueryAllAndDelete), the processor's
name comparison and invisible characters (Names), error codes (ErrorCodes), the tools' --vpn-off
and the VPN check it runs (ToolCommandLines), scripts/vpn_check.sh itself (VpnCheck), and the
owner-only folders and ledgers (PrivateFiles). Everything here is fictional: ids, tokens, secrets,
names, addresses are invented. The tools' own uses are tested beside each tool.

The VPN check (ticket #251): --vpn-off was only the session's word. glow.salesforce.require_vpn_off
now also runs the check glow.salesforce.VPN_CHECK names - its argv, read at each call, by default the
repository's scripts/vpn_check.sh - and refuses unless it exits 0 (`vpn: off`). Every other test that
reaches require_vpn_off gets a check that says off from test/helpers/__init__.py, so no test runs the
real one (CI is a Linux container); the tests here set their own.
"""
import datetime
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import helpers                       # noqa: E402,F401  the VPN check's stand-in (#251): test/helpers/__init__.py
from glow import private_files       # noqa: E402
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



class Names(unittest.TestCase):
    """How the attendance processor compares a submitted club name with an Account's (sf_match),
    and the characters no name may hide (has_invisible)."""

    def test_the_processor_s_comparison(self):
        m = salesforce.sf_match
        self.assertTrue(m("Sunrise Club", "sunrise club"))
        self.assertTrue(m("  Sunrise Club\t", "Sunrise Club"))          # question 5 is trimmed ...
        self.assertFalse(m("Sunrise Club", " Sunrise Club"))           # ... the Account name is not
        self.assertFalse(m("Sunrise  Club", "Sunrise Club"))           # inner spaces count
        self.assertFalse(m("Sunrise\xa0Club", "Sunrise Club"))       # a no-break space is not a space
        self.assertFalse(m("\xa0Sunrise Club", "Sunrise Club"))      # nor trimmed (it is above U+0020)
        self.assertFalse(m("Straße", "STRASSE"))                       # one character never becomes two
        self.assertTrue(m("Niñas Valientes", "NIÑAS VALIENTES"))
        self.assertFalse(m("Ninas Valientes", "Niñas Valientes"))      # accents count
        self.assertTrue(m("İstanbul Girls", "istanbul girls"))   # Java maps İ to i, one character to one
        self.assertTrue(m("Straße", "STRAẞE"))                     # ß and ẞ are one character each

    def test_invisible_characters_are_found(self):
        for point in (0x00A0, 0x00AD, 0x200B, 0x2060, 0xFEFF, 0x034F, 0x3164, 0xE0020, 0x0009):
            with self.subTest(hex(point)):
                self.assertTrue(salesforce.has_invisible("Odd" + chr(point) + "Club"))
        for name in ("Sunrise Club", "Niñas de Oro", "Dawn's Club", "Club A/B - Example Partner", ""):
            with self.subTest(name):
                self.assertFalse(salesforce.has_invisible(name))


class ErrorCodes(unittest.TestCase):
    """glow.salesforce.error_codes: Salesforce's codes (capitals with an underscore), never a word of
    the message - a capitalised word there can be a girl's or a club's name."""

    def test_codes_are_repeated_and_names_in_capitals_never(self):
        said = ("System.DmlException: Insert failed. DUPLICATES_DETECTED, AMARA ZIBBLEWICK looks like ZARA "
                "QUILLFEATHER: []; UNABLE_TO_LOCK_ROW; DUPLICATES_DETECTED")
        self.assertEqual(salesforce.error_codes(said), ["DUPLICATES_DETECTED", "UNABLE_TO_LOCK_ROW"])
        answer = [{"errorCode": "FIELD_CUSTOM_VALIDATION_EXCEPTION", "message": "SUNRISE CLUB: WRONG"}]
        self.assertEqual(salesforce.error_codes(json.dumps(answer)), ["FIELD_CUSTOM_VALIDATION_EXCEPTION"])
        self.assertEqual(salesforce.error_codes(answer), ["FIELD_CUSTOM_VALIDATION_EXCEPTION"])
        for nothing in (None, "", "AMARA ZIBBLEWICK", "Contact_IDs__c is wrong", "NPSP ERROR"):
            with self.subTest(nothing):
                self.assertEqual(salesforce.error_codes(nothing), [])


def says(*lines, code=0, err=""):
    """A stand-in VPN check: an argv for VPN_CHECK that prints `lines`, `err` on standard error, and
    exits `code`."""
    script = "".join(f"echo {shlex.quote(line)}; " for line in lines)
    script += f"echo {shlex.quote(err)} >&2; " if err else ""
    return ["/bin/sh", "-c", script + f"exit {code}"]


class ToolCommandLines(unittest.TestCase):
    """What the Salesforce tools' command lines share: --vpn-off, the VPN check it runs, its refusal,
    positive()."""

    def test_the_vpn_flag_and_its_refusal(self):
        # DoD (#251): require_vpn_off refuses while a tunnel is up, even with --vpn-off - the check says so
        # (exit 1, `vpn: on <iface>`, the refusal naming it); and when the check cannot say (it fails,
        # cannot be run): fail closed. Off and --vpn-off: it passes. Without --vpn-off it refuses as
        # before, whatever the check says
        import argparse
        ap = argparse.ArgumentParser()
        salesforce.add_vpn_flag(ap)
        self.assertIn("no VPN is on", ap.format_help())
        off = says("vpn: off")
        missing = [os.path.join(tempfile.gettempdir(), "glow-no-such-vpn-check-251.sh")]
        cases = [
            ("off", off, ["--vpn-off"], None),
            ("on, a full tunnel", says("vpn: on utun4", code=1), ["--vpn-off"], "utun4"),
            ("on, a PPP tunnel", says("vpn: on ppp0", code=1), ["--vpn-off"], "ppp0"),
            ("on, a split tunnel", says("vpn: on ipsec2", code=1), ["--vpn-off"], "ipsec2"),
            ("the state unreadable", says(code=2, err="vpn: unknown (route failed)"), ["--vpn-off"], ""),
            ("no check to run", missing, ["--vpn-off"], ""),
            ("off, no --vpn-off", off, [], salesforce.VPN_REFUSAL),
            ("on, no --vpn-off", says("vpn: on utun4", code=1), [], ""),
        ]
        for label, check, argv, refusal in cases:
            with self.subTest(label), mock.patch.object(salesforce, "VPN_CHECK", check, create=True):
                if refusal is None:
                    salesforce.require_vpn_off(ap.parse_args(argv))                     # passes: no exception
                    continue
                with self.assertRaises(salesforce.Refused, msg=f"{label}: require_vpn_off let it through") as stop:
                    salesforce.require_vpn_off(ap.parse_args(argv))
                if refusal == salesforce.VPN_REFUSAL:
                    self.assertEqual(str(stop.exception), salesforce.VPN_REFUSAL)
                elif refusal:
                    self.assertIn(refusal, str(stop.exception), "the refusal does not name the tunnel")
        with mock.patch.object(salesforce, "VPN_CHECK", off, create=True), \
                self.assertRaises(salesforce.Refused) as stop:                           # a command that has no --vpn-off
            salesforce.require_vpn_off(types.SimpleNamespace())
        self.assertEqual(str(stop.exception), salesforce.VPN_REFUSAL)
        self.assertIn("check that no VPN is on, then add --vpn-off", salesforce.VPN_REFUSAL)
        self.assertEqual(salesforce.positive("3"), 3)
        for bad in ("0", "-1"):
            with self.subTest(bad), self.assertRaises(argparse.ArgumentTypeError):
                salesforce.positive(bad)


# ---- scripts/vpn_check.sh (ticket #251), run as a session runs it, with `route` and `ifconfig` stand-ins
# first on its PATH (the real ones never run: CI is a Linux container). What this Mac shows (2026-11-20):
# `ifconfig -l` always lists utun0..utun7, each with an inet6 address and no IPv4 one, while the VPN is
# off - a tunnel interface that merely exists is no VPN; one is up when the default route goes through
# a tunnel (utun*, ppp*, ipsec*) or a tunnel holds an IPv4 (`inet `) address (a split tunnel)
SCRIPT = os.path.join(REPO, "scripts", "vpn_check.sh")


def route_answer(iface, gateway="192.0.2.1"):
    """`route -n get default` as macOS prints it, the default through `iface`."""
    gw = f"    gateway: {gateway}\n" if gateway else ""
    return ("   route to: default\ndestination: default\n       mask: default\n" + gw
            + f"  interface: {iface}\n      flags: <UP,GATEWAY,DONE,STATIC,PRCLONING,GLOBAL>\n"
            " recvpipe  sendpipe  ssthresh  rtt,msec    rttvar  hopcount      mtu     expire\n"
            "       0         0         0         0         0         0      1500         0\n")


def interface(name, ipv4=None):
    """One interface's block as `ifconfig` prints it: a loopback, an Ethernet/Wi-Fi/bridge one, or a
    point-to-point tunnel; an IPv4 address only when given."""
    if name.startswith("lo"):
        head, extra = "flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384", "\tinet6 ::1 prefixlen 128 \n"
    elif name.startswith(("utun", "ppp", "ipsec", "gif", "stf")):
        head, extra = "flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1380", ""
    else:
        head, extra = ("flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500",
                       "\tether 02:00:5e:00:53:%02x\n" % (sum(map(ord, name)) % 256))
    inet = ""
    if ipv4:
        inet = (f"\tinet {ipv4} --> {ipv4} netmask 0xffffff00\n" if head.startswith("flags=8051")
                else f"\tinet {ipv4} netmask 0xffffff00 broadcast {ipv4.rsplit('.', 1)[0]}.255\n")
    six = f"\tinet6 fe80::{sum(map(ord, name)):x}:2c3d:4e5f:6071%{name} prefixlen 64 scopeid 0x{len(name):x} \n"
    return f"{name}: {head}\n{extra}{inet}{six}\tnd6 options=201<PERFORMNUD,DAD>\n"


IDLE_TUNNELS = [(f"utun{n}", None) for n in range(8)]          # this Mac's, VPN off
MAC = [("lo0", "127.0.0.1"), ("gif0", None), ("stf0", None), ("anpi0", None), ("en0", "192.0.2.23"),
       ("awdl0", None), ("llw0", None)] + IDLE_TUNNELS


def holding(interfaces, name, ipv4):
    """`interfaces` with `name` holding `ipv4`: in its place when it is there, else added last."""
    if any(n == name for n, _ in interfaces):
        return [(n, ipv4 if n == name else a) for n, a in interfaces]
    return interfaces + [(name, ipv4)]


class VpnCheck(unittest.TestCase):
    """scripts/vpn_check.sh: read-only (`route -n get default`, the tunnel interfaces); prints
    `vpn: off` and exits 0, or `vpn: on <iface>` and exits 1; fails closed - never `vpn: off`, never 0 -
    when it cannot read the state (Ruling, test-author #251)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def stand_ins(self, route, interfaces, route_code=0, ifconfig_fails=False):
        """A folder of `route` and `ifconfig` stand-ins answering from these fixtures: route, to any
        question with `get` in it, `route` (and exits route_code); ifconfig `-l [family]` the names
        (those with that family), `<name>` its block, anything else every block. Returns the env."""
        fix = tempfile.mkdtemp(dir=self.tmp.name)
        bin_dir = os.path.join(fix, "bin")
        os.makedirs(os.path.join(fix, "if"))
        os.makedirs(bin_dir)
        with open(os.path.join(fix, "route.out"), "w", encoding="utf-8") as f:
            f.write(route)
        for name, ipv4 in interfaces:
            with open(os.path.join(fix, "if", name), "w", encoding="utf-8") as f:
                f.write(interface(name, ipv4))
        with open(os.path.join(fix, "order"), "w", encoding="utf-8") as f:
            f.write(" ".join(name for name, _ in interfaces) + "\n")
        q = shlex.quote(fix)
        stubs = {
            "route": f"""#!/bin/sh
case " $* " in *" get "*) ;; *) echo "route: usage: route [-n] get default" >&2; exit 64 ;; esac
{'cat ' + q + '/route.out >&2' if route_code else 'cat ' + q + '/route.out'}
exit {int(route_code)}
""",
            "ifconfig": f"""#!/bin/sh
F={q}
{'echo "ifconfig: ioctl (SIOCGIFCONF): Operation not permitted" >&2; exit 1' if ifconfig_fails else ':'}
list=$(cat "$F/order")
listing= want=
for a in "$@"; do
  case "$a" in
    -l*) listing=1 ;;
    -*) ;;
    *) [ -z "$want" ] && want=$a ;;
  esac
done
if [ -n "$listing" ]; then
  out=
  for i in $list; do
    if [ -z "$want" ] || grep -q "^[[:space:]]$want " "$F/if/$i"; then out="$out $i"; fi
  done
  echo $out
  exit 0
fi
if [ -n "$want" ]; then
  [ -f "$F/if/$want" ] || {{ echo "ifconfig: interface $want does not exist" >&2; exit 1; }}
  cat "$F/if/$want"
  exit 0
fi
for i in $list; do cat "$F/if/$i"; done
""",
        }
        for name, text in stubs.items():
            path = os.path.join(bin_dir, name)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            os.chmod(path, 0o755)
        return {"PATH": bin_dir + os.pathsep + os.pathsep.join(["/usr/bin", "/bin"]), "HOME": fix, "LC_ALL": "C"}, fix

    def check(self, *args, **kw):
        env, fix = self.stand_ins(*args, **kw)
        done = subprocess.run([SCRIPT], env=env, cwd=fix, capture_output=True, text=True, timeout=30)
        return done.returncode, (done.stdout.splitlines() or [""])[0].strip(), done

    def test_it_reads_the_default_route_and_the_tunnels(self):
        self.assertTrue(os.access(SCRIPT, os.X_OK), "scripts/vpn_check.sh is missing or not executable")
        off = [
            ("this Mac, VPN off: the default via en0, utun0..utun7 with no IPv4", route_answer("en0"), MAC),
            ("the default via en1 (Wi-Fi), no tunnel interface at all", route_answer("en1", "198.51.100.1"),
             [("lo0", "127.0.0.1"), ("en0", None), ("en1", "198.51.100.40")]),
            ("a VM bridge and a USB adapter hold IPv4 - no tunnel", route_answer("en0"),
             MAC + [("bridge100", "192.0.2.129"), ("en5", "203.0.113.9")]),
        ]
        on = [
            ("a full tunnel: the default via utun4", route_answer("utun4", None), holding(MAC, "utun4", "10.8.0.6"), "utun4"),
            ("a full tunnel: the default via ppp0", route_answer("ppp0", None), holding(MAC, "ppp0", "10.64.0.12"), "ppp0"),
            ("a full tunnel: the default via ipsec0", route_answer("ipsec0", None), holding(MAC, "ipsec0", "172.16.40.2"),
             "ipsec0"),
            ("a split tunnel: the default via en0, utun9 holds IPv4", route_answer("en0"), holding(MAC, "utun9", "10.20.30.4"),
             "utun9"),
            ("a split tunnel: the default via en0, utun2 (one of the eight) holds IPv4", route_answer("en0"),
             holding(MAC, "utun2", "10.20.30.5"), "utun2"),
            ("a split tunnel: the default via en0, ipsec2 holds IPv4", route_answer("en0"), holding(MAC, "ipsec2", "172.16.8.3"),
             "ipsec2"),
        ]
        unknown = [
            ("route fails: no default route", dict(route="route: writing to routing socket: not in table\n", route_code=1)),
            ("route answers no interface", dict(route="   route to: default\ndestination: default\n")),
            ("ifconfig fails, the default via en0", dict(route=route_answer("en0"), ifconfig_fails=True)),
        ]
        for label, route, interfaces in off:
            with self.subTest(label):
                code, first, done = self.check(route, interfaces)
                self.assertEqual((code, first), (0, "vpn: off"), done.stdout + done.stderr)
        for label, route, interfaces, iface in on:
            with self.subTest(label):
                code, first, done = self.check(route, interfaces)
                self.assertEqual(code, 1, done.stdout + done.stderr)
                self.assertEqual(first.split()[:3], ["vpn:", "on", iface], f"not `vpn: on {iface}`: {done.stdout!r}")
        for label, kw in unknown:
            with self.subTest(label):
                code, first, done = self.check(interfaces=MAC, **kw)
                self.assertNotEqual(code, 0, f"fails open: {done.stdout!r}")
                self.assertNotIn("vpn: off", done.stdout, "an unreadable state said off")

    def test_require_vpn_off_runs_this_check_by_default(self):
        # DoD: require_vpn_off runs the same check - scripts/vpn_check.sh, found from the repository
        # whatever the working folder - in a process that never imported the tests' stand-in
        code = ("import sys, types\nsys.path.insert(0, sys.argv[1])\nfrom glow import salesforce\n"
                "try:\n    salesforce.require_vpn_off(types.SimpleNamespace(vpn_off=True))\n"
                "except salesforce.Refused as e:\n    print('refused:', e)\n    sys.exit(3)\nprint('passed')\n")
        for label, route, interfaces, code_wanted in (
                ("off", route_answer("en0"), MAC, 0),
                ("a full tunnel through utun4", route_answer("utun4", None), holding(MAC, "utun4", "10.8.0.6"), 3),
                ("a split tunnel through utun9", route_answer("en0"), holding(MAC, "utun9", "10.20.30.4"), 3)):
            with self.subTest(label):
                env, fix = self.stand_ins(route, interfaces)
                done = subprocess.run([sys.executable, "-c", code, REPO], env=env, cwd=fix, capture_output=True,
                                      text=True, timeout=60)
                self.assertEqual(done.returncode, code_wanted, done.stdout + done.stderr)
                if code_wanted:
                    self.assertIn("refused:", done.stdout, done.stdout + done.stderr)
                    self.assertIn(label.split()[-1], done.stdout, "the refusal does not name the tunnel")
                else:
                    self.assertIn("passed", done.stdout.split(), done.stdout + done.stderr)



class PrivateFiles(unittest.TestCase):
    """glow/private_files.py: the Salesforce tools' owner-only folders, files and ledgers."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_a_ledger_is_one_header_then_rows_each_on_disk(self):
        path = os.path.join(self.tmp.name, "ledger.csv")
        ledger, rows = private_files.Ledger(path, ["when_utc", "key", "note"]), []
        self.assertEqual(ledger.read(), [])
        open(path, "w").close()                                  # left empty by a run that died: header still goes in
        ledger.append({"when_utc": "2026-10-09T12:00:00Z", "key": "a|1", "extra": "never written"}, rows)
        ledger.append({"key": "b", "note": 'says "x", y'})
        with open(path, encoding="utf-8", newline="") as fh:
            self.assertEqual(fh.read(), 'when_utc,key,note\n2026-10-09T12:00:00Z,a|1,\n,b,"says ""x"", y"\n')
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertEqual(rows, [{"when_utc": "2026-10-09T12:00:00Z", "key": "a|1", "note": ""}])
        self.assertEqual(private_files.last_rows(ledger.read() + rows, "key")["a|1"], rows[0])
        with self.assertRaises(salesforce.Refused) as stop:
            private_files.Ledger(path, ["when_utc", "key"]).read()
        self.assertIn("does not start with its header line", str(stop.exception))

    def test_a_folder_is_under_data_inside_the_checkout_and_owner_only(self):
        checkout = os.path.join(self.tmp.name, "checkout")
        os.makedirs(os.path.join(checkout, "docs"))
        self.assertFalse(private_files.within(os.path.join(checkout, "data", "x"), os.path.join(checkout, "data")))
        folder = private_files.private_folder(os.path.join(checkout, "data", "x"), repo=checkout)   # data/ made first
        self.assertTrue(private_files.within(folder, os.path.join(checkout, "data")))
        self.assertEqual([stat.S_IMODE(os.stat(p).st_mode) for p in (os.path.join(checkout, "data"), folder)], [0o700] * 2)
        for refused in (os.path.join(checkout, "docs"), checkout):
            with self.subTest(refused), self.assertRaises(salesforce.Refused) as stop:
                private_files.private_folder(refused, "the ledger folder", repo=checkout)
            self.assertEqual(str(stop.exception), "--dir: inside the checkout the ledger folder must be under data/ "
                                                  "(never committed)")
        outside = os.path.join(self.tmp.name, "elsewhere")
        with self.assertRaises(salesforce.Refused):
            private_files.private_folder(outside, repo=checkout, make=False)             # must exist
        self.assertEqual(private_files.private_folder(outside, repo=checkout), outside)
        eastern = datetime.timezone(datetime.timedelta(hours=-4))
        self.assertEqual(private_files.stamp(datetime.datetime(2026, 10, 9, 4, 0, tzinfo=eastern)), "2026-10-09T08:00:00Z")


if __name__ == "__main__":
    unittest.main(verbosity=1)
