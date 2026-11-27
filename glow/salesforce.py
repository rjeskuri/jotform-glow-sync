"""Salesforce REST through curl: the one client every tool uses
(docs/plans/2026-10-06-sf-new-club-accounts.md).

Two ways to log in, never mixed:
  cli_login(alias)      the Salesforce CLI's stored login on Ryan's Mac (the back-fill tools)
  client_credentials()  the "GLOW Sync" integration user through an External Client App - the
                        automatic sync in GitHub Actions only
A local run therefore never writes as GLOW Sync, and the automatic sync never runs as Ryan.

The token stays in memory and goes to curl in a config on stdin: never on a command line, in a log
or on disk. curl ignores any curlrc (-q) and any proxy, and follows no redirect, so the
Authorization header never reaches another host. A refusal carries Salesforce's error code and
short description, never a response body.

Beside the client, what every Salesforce tool relies on: the org's record types, ids and the pilot
accounts on hold; how the attendance processor compares a submitted club name with an Account's
(sf_match); the groups of Accounts the Account duplicate rule reports (duplicate_account_groups);
the characters no name may hide (has_invisible); the error codes of an answer, never its words
(error_codes); the partner map (glow/sf_partners.csv, read_partners); and the tools' --vpn-off and
the VPN check behind it (add_vpn_flag, require_vpn_off, VPN_CHECK: scripts/vpn_check.sh). Their
owner-only files: glow/private_files.py. And what the automatic runner watches (#242, after
incident #238): the attendance processor's Apex against the build we deployed (apex_fingerprint,
expected_apex from glow/apex_fingerprints.json, apex_attention) and Jotform batches that stop
arriving (batch_gap_attention).
"""
import argparse
import csv
import datetime
import hashlib
import json
import os
import re
import subprocess
import unicodedata
import urllib.parse

from .text import key

API = "v67.0"
INSTANCE = "https://globalglow.my.salesforce.com"      # production (read 2026-10-06)
NEXT_PAGE = re.compile(r"/services/data/v\d+\.\d+/query/[A-Za-z0-9_-]+")
NEXT_PAGE_ALL = re.compile(r"/services/data/v\d+\.\d+/query(?:All)?/[A-Za-z0-9_-]+")   # queryAll's next pages
PLAIN_HOST = re.compile(r"https://[A-Za-z0-9.-]+(:\d+)?")
UNSAFE = re.compile(r'[\x00-\x20\x7f"\\]')              # nothing a curl config line could misread
SAY = re.compile(r"[^A-Za-z0-9 _.,:;'()/-]")            # what of an OAuth error may be repeated
# Salesforce's error codes (DUPLICATES_DETECTED, UNABLE_TO_LOCK_ROW ...): capitals WITH an underscore,
# which no name has - a bare capitalised word of an error text can be a girl's or a club's name
ERROR_CODE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")

# ---- the org (read 2026-09-30)
CLUB_RECORD_TYPE = "012RP000002uklNYAQ"      # RecordType 'Club' on Account
PARTNER_RECORD_TYPE = "0126A000000cdYFQAY"   # 'Household Account': every partner account has it
# the two pilot Club accounts Ryan is checking: never a parent, never a link target
ON_HOLD_ACCOUNTS = {"001RP00000nMZXfYAO", "001RP00000mgVVMYA2"}
SF_ID = re.compile(r"[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?")   # any record id, 15 or 18 characters
ACCOUNT_ID = re.compile(r"001[A-Za-z0-9]{15}")          # an Account's id as the API gives it: 18 characters
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARTNERS = os.path.join(REPO, "glow", "sf_partners.csv")
PARTNER_COLS = ["partner", "sf_account_id", "sf_account_name"]
# characters that render as nothing or as a space but are not one, beyond the Unicode categories
FILLERS = {0x034F, 0x115F, 0x1160, 0x2800, 0x3164, 0xFFA0, 0xFFFC} | set(range(0xFE00, 0xFE10))


class Refused(Exception):
    """Stop: what is wrong and what to do."""


def quoted(value):
    """A SOQL string literal."""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def plain(records):
    """Records without Salesforce's `attributes` entry."""
    return [{k: v for k, v in r.items() if k != "attributes"} for r in records]


def as_int(value):
    """A whole number from what Salesforce (a double) or Jotform (text) gives, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    text = str(value).strip() if value is not None else ""
    return int(text) if text.isascii() and text.isdigit() else None


def error_codes(text):
    """The Salesforce error codes in an error text or answer, sorted - never its words: an error
    message can quote a record's values, a girl's name among them (in capitals too)."""
    return sorted(set(ERROR_CODE.findall(str(text or ""))))


def config_value(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def curl(run, lines):
    """(http status, answer text). Status 0: curl did not run or gave no status."""
    try:
        out = run(["curl", "-q", "-sS", "--max-time", "120", "--config", "-", "-w", "\n%{http_code}"],
                  input="\n".join(lines + ['noproxy = "*"']) + "\n", capture_output=True, text=True)
    except OSError:
        return 0, ""
    text, _, code = (out.stdout or "").rpartition("\n")
    return (int(code) if code.strip().isdigit() else 0), text


def cli_login(alias):
    """The Salesforce CLI's stored login (`sf org login web --alias <alias>`, made by Ryan)."""
    def login(run):
        try:
            shown = [json.loads(run(["sf", "org", *words, "--target-org", alias, "--json"],
                                    capture_output=True, text=True).stdout)["result"]
                     for words in (["display"], ["auth", "show-access-token"])]   # the CLI hides the token in `display`
            base, token = shown[0]["instanceUrl"].rstrip("/"), shown[1]["accessToken"]
            if not PLAIN_HOST.fullmatch(base) or not token or UNSAFE.search(token):
                raise ValueError
            return base, token
        except (ValueError, KeyError, TypeError, OSError, AttributeError):
            raise Refused(f"the Salesforce CLI has no usable login for '{alias}' - Ryan signs in, VPN "
                          f"off, with `sf org login web --alias {alias}` (RUNBOOK, Back-fill of "
                          "attendance into Salesforce)") from None
    return login


def oauth_error(text, hide=()):
    """Salesforce's error code and short description only, cleaned - never the body itself, and
    never any of `hide` (hidden on the raw text, before the cut)."""
    try:
        answer = json.loads(text)
    except ValueError:
        return "no readable answer"
    if not isinstance(answer, dict):
        return "no readable answer"
    said = " - ".join(str(answer.get(k) or "") for k in ("error", "error_description") if answer.get(k))
    for value in hide:
        if value:
            said = said.replace(value, "(hidden)")
    return SAY.sub("", said)[:120] or "no error given"


def client_credentials(client_id, client_secret, instance=INSTANCE):
    """The GLOW Sync integration user (OAuth client credentials). The id and secret go to curl in
    the POST body, on stdin; Salesforce must answer for `instance` and nowhere else."""
    def login(run):
        if not client_id or not client_secret:
            raise Refused("not configured: SF_CLIENT_ID / SF_CLIENT_SECRET are not set")
        body = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": client_id,
                                       "client_secret": client_secret})
        status, text = curl(run, [f"url = {config_value(instance + '/services/oauth2/token')}",
                                  'request = "POST"', 'header = "Accept: application/json"',
                                  'header = "Content-Type: application/x-www-form-urlencoded"',
                                  f"data = {config_value(body)}"])
        try:
            answer = json.loads(text)
        except ValueError:
            answer = None
        if status != 200 or not isinstance(answer, dict) or not isinstance(answer.get("access_token"), str):
            raise Refused(f"Salesforce refused the GLOW Sync login (HTTP {status}): "
                          f"{oauth_error(text, (client_secret, client_id))}")
        base, token = str(answer.get("instance_url") or "").rstrip("/"), answer["access_token"]
        if base != instance:
            raise Refused("Salesforce answered the GLOW Sync login for another address - nothing sent")
        if not token or UNSAFE.search(token):
            raise Refused("Salesforce's GLOW Sync token is not a plain token - nothing sent")
        return base, token
    return login


class Org:
    """One REST call at a time. `Org(alias)` logs in with the CLI; `Org(login=client_credentials(...))`
    as GLOW Sync."""

    def __init__(self, alias=None, run=subprocess.run, login=None):
        self.alias, self.run, self.token, self.base = alias, run, None, None
        self.login_with = login or cli_login(alias)
        self.revocable = login is not None      # GLOW Sync's sessions end with the run; Ryan's CLI login never

    def login(self):
        self.base, self.token = self.login_with(self.run)

    def call(self, method, path, body=None):
        """(http status, parsed answer). Status 0: curl failed or the answer could not be read -
        the outcome of a write is then unknown."""
        if self.token is None:
            self.login()
        for attempt in (1, 2):
            config = [f'url = "{self.base}{path}"', f'request = "{method}"',
                      f'header = "Authorization: Bearer {self.token}"', 'header = "Accept: application/json"']
            if body is not None:
                text = json.dumps(body, ensure_ascii=True)
                config += ['header = "Content-Type: application/json"', f"data = {config_value(text)}"]
            status, text = curl(self.run, config)
            if status == 401 and attempt == 1:       # the session ran out: log in again, once
                self.login()
                continue
            try:
                return status, json.loads(text) if text.strip() else None
            except ValueError:
                return (status if status >= 500 else 0), None
        return 0, None

    def query(self, soql):
        """Every record of a query, following Salesforce's pages."""
        return self._pages("query", soql, NEXT_PAGE)

    def query_all(self, soql):
        """query(), deleted and merged-away records included (REST queryAll: IsDeleted,
        MasterRecordId). Its next pages come as /queryAll/<locator> (or /query/<locator>)."""
        return self._pages("queryAll", soql, NEXT_PAGE_ALL)

    def _pages(self, resource, soql, next_page):
        path, records = f"/services/data/{API}/{resource}?q=" + urllib.parse.quote(soql), []
        while path:
            status, answer = self.call("GET", path)
            if status != 200 or not isinstance(answer, dict) or not isinstance(answer.get("records"), list):
                raise Refused(f"Salesforce did not answer a read (HTTP {status})")
            records += answer["records"]
            path = None if answer.get("done") else answer.get("nextRecordsUrl")
            if not answer.get("done") and not (isinstance(path, str) and next_page.fullmatch(path)):
                raise Refused("Salesforce gave part of an answer and no way to read the rest: " + soql[:60])
        return records

    def count(self, soql):
        status, answer = self.call("GET", f"/services/data/{API}/query?q=" + urllib.parse.quote(soql))
        if status != 200 or not isinstance(answer, dict) or not isinstance(answer.get("totalSize"), int):
            raise Refused(f"Salesforce did not answer a count (HTTP {status})")
        return answer["totalSize"]

    def describe(self, sobject):
        status, answer = self.call("GET", f"/services/data/{API}/sobjects/{sobject}/describe")
        if status != 200 or not isinstance(answer, dict):
            raise Refused(f"Salesforce did not describe {sobject} (HTTP {status})")
        return answer

    def insert(self, sobject, body):
        return self.call("POST", f"/services/data/{API}/sobjects/{sobject}", body)

    def update(self, sobject, record_id, body):
        return self.call("PATCH", f"/services/data/{API}/sobjects/{sobject}/{record_id}", body)

    def delete(self, sobject, record_id):
        """(http status, answer): 204 = deleted (to the Recycle Bin)."""
        return self.call("DELETE", f"/services/data/{API}/sobjects/{sobject}/{record_id}")

    def revoke(self):
        """End a GLOW Sync session (best effort); a CLI login's token is only forgotten here."""
        if self.token is not None and self.base and self.revocable:
            curl(self.run, [f"url = {config_value(self.base + '/services/oauth2/revoke')}", 'request = "POST"',
                            'header = "Content-Type: application/x-www-form-urlencoded"',
                            f"data = {config_value(urllib.parse.urlencode({'token': self.token}))}"])
        self.token = None


# ---- how the attendance processor compares a submitted name with an Account's ---------------------
def apex_trim(s):
    """Java String.trim(): every character up to U+0020 off both ends, nothing else."""
    start, end = 0, len(s)
    while start < end and s[start] <= " ":
        start += 1
    while end > start and s[end - 1] <= " ":
        end -= 1
    return s[start:end]


def _upper(c):
    u = c.upper()
    return u if len(u) == 1 else c       # Character.toUpperCase maps one character to one


SIMPLE_LOWER = {"\u0130": "i"}     # Java's one-to-one mapping where Python's full one gives two characters


def _lower(c):
    u = c.lower()
    return u if len(u) == 1 else SIMPLE_LOWER.get(c, c)


def sf_match(submitted, name):
    """`submitted.trim().equalsIgnoreCase(name)` as the Apex processor runs it: question 5 is
    trimmed, the Account's name is not; one character never becomes two ('Straße' is not
    'STRASSE'), and a no-break space is neither a space nor trimmed."""
    a, b = apex_trim(submitted or ""), name or ""
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        ux, uy = _upper(x), _upper(y)
        if x != y and ux != uy and _lower(ux) != _lower(uy):
            return False
    return True


# ---- the Account duplicate rule's Python side ------------------------------------------------------
def duplicate_account_groups(accounts):
    """The groups of two or more Accounts the Account matching rule reports (RUNBOOK "Duplicate and
    obsolete records in Salesforce"), for the read-back and the monthly check: the same Name ignoring
    capitals and spacing (casefold, so 'Straße' is 'STRASSE' - not text.key's lower(); any run of
    whitespace, a tab or a no-break space included, is one space; an accent is a different name), the
    same ParentId ("" and a missing key are null: partner-less) and the same RecordTypeId (missing is
    null). `accounts` as `SELECT Id, Name, ParentId, RecordTypeId FROM Account` gives them; each group
    is the Accounts' Ids, sorted, the groups sorted too; the input is left as it is."""
    groups = {}
    for account in accounts:
        name = " ".join(str(account.get("Name") or "").split()).casefold()
        parent, record_type = account.get("ParentId") or None, account.get("RecordTypeId") or None
        groups.setdefault((name, parent, record_type), []).append(account["Id"])
    return sorted(sorted(ids) for ids in groups.values() if len(ids) > 1)


# ---- names ----------------------------------------------------------------------------------------
def has_invisible(name):
    """Control, format, private, unassigned, line/paragraph separators, any space that is not
    the plain one, and the invisible fillers: none of them may hide in a name."""
    for c in name:
        cat = unicodedata.category(c)
        if cat in ("Cc", "Cf", "Co", "Cn", "Cs", "Zl", "Zp") or (cat == "Zs" and c != " ") \
                or ord(c) in FILLERS:
            return True
    return False


# ---- the tools' command lines ---------------------------------------------------------------------
VPN_REFUSAL = ("this command talks to Salesforce from this Mac: check that no VPN is on, then add --vpn-off "
               "(scripts/vpn_check.sh; a connection through a VPN froze Ryan's user on 2026-09-30)")
# the VPN check require_vpn_off runs beside --vpn-off (ticket #251): its argv, read at each call - the
# tests put a stand-in here (test/helpers/__init__.py); it must exit 0 and print `vpn: off` first
VPN_CHECK = [os.path.join(REPO, "scripts", "vpn_check.sh")]
VPN_CHECK_TIMEOUT = 15      # seconds; a check that hangs refuses


def add_vpn_flag(parser):
    """--vpn-off on a (sub)command that talks to Salesforce from this Mac; require_vpn_off() reads it."""
    parser.add_argument("--vpn-off", action="store_true",
                        help="you checked: no VPN is on (Salesforce freezes a user whose API call comes through one); "
                             "scripts/vpn_check.sh runs as well, and refuses while a tunnel is up")


def require_vpn_off(args):
    """Refused unless the operator said --vpn-off AND the VPN check (VPN_CHECK) exits 0 with `vpn: off`
    as the first line it prints: Salesforce freezes a user whose API call comes through a VPN. A
    check that says a tunnel is up, fails, cannot run or hangs refuses: it fails closed."""
    if not getattr(args, "vpn_off", False):
        raise Refused(VPN_REFUSAL)
    check = list(VPN_CHECK)
    try:
        done = subprocess.run(check, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              timeout=VPN_CHECK_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as e:
        raise Refused(f"--vpn-off, but the VPN check could not run ({type(e).__name__}): run scripts/vpn_check.sh "
                      "alone and read what it says") from None
    lines = done.stdout.splitlines()
    if done.returncode == 0 and lines and lines[0] == "vpn: off":
        return
    said = (lines[0].strip() if lines else "") or (done.stderr.strip().splitlines() or ["nothing"])[0]
    raise Refused(f"--vpn-off, but the VPN check says {said!r} (exit {done.returncode}): turn the VPN off, run "
                  "scripts/vpn_check.sh until it says `vpn: off`, then run the command again")


def positive(text):
    """argparse type: a whole number of 1 or more (--limit, --max-new, --per-run)."""
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return value


# ---- the partner map ------------------------------------------------------------------------------
def read_partners(path=PARTNERS):
    """{key(partner): (account id, account name)} from glow/sf_partners.csv."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != PARTNER_COLS:
            raise Refused(f"{os.path.relpath(path, REPO)}: the columns must be {','.join(PARTNER_COLS)}")
        out = {}
        for row in reader:
            k, pid = key(row["partner"]), (row["sf_account_id"] or "").strip()
            name = (row["sf_account_name"] or "").strip()
            if not k or not name or not ACCOUNT_ID.fullmatch(pid) or k in out:
                raise Refused(f"{os.path.relpath(path, REPO)}: a partner is blank, repeated, unnamed or has "
                              f"no plain account id: {row['partner']!r}")
            out[k] = (pid, name)
    return out


# ---- the runner's watch on the attendance processor (#242, after incident #238) -------------------
# Another team's release overwrote the processor on 2026-10-26 and nobody noticed for 3 1/2 weeks:
# each run with a Salesforce login compares the watched Apex with the build we deployed, and says
# when no Jotform batch has arrived for two days (docs/RUNBOOK.md, "Attendance processor watch").
FINGERPRINTS = os.path.join(REPO, "glow", "apex_fingerprints.json")
APEX_KINDS = {"ApexClass": "class", "ApexTrigger": "trigger"}
SHA256 = re.compile(r"[0-9a-f]{64}")
# the newest batch the Jotform flow made (Creator__c `Jotform`; the back-fill's `Jotform back-fill`
# too); a partner's report or a batch made by hand does not count
NEWEST_JOTFORM_BATCH = ("SELECT Id, CreatedDate FROM Attendance_Batch__c WHERE Creator__c LIKE 'Jotform%' "
                        "ORDER BY CreatedDate DESC LIMIT 1")
WATCH_SECTION = 'docs/RUNBOOK.md, "Attendance processor watch"'


def apex_fingerprint(body):
    """The sha256 (hex) of an Apex body, normalised: CRLF -> LF, surrounding whitespace trimmed, UTF-8."""
    return hashlib.sha256(body.replace("\r\n", "\n").strip().encode("utf-8")).hexdigest()


def expected_apex(path=FINGERPRINTS):
    """{name: {"kind": "ApexClass" | "ApexTrigger", "sha256": hex}}: the build we deployed, from
    glow/apex_fingerprints.json (its `recorded` and `refresh` say where the digests came from and
    how to renew them after a deploy of ours). The file writes each digest in groups of 8 hex
    digits (64 in a row is a secret to scripts/check_secrets.py); here they are joined."""
    rel = os.path.relpath(path, REPO)
    try:
        with open(path, encoding="utf-8") as fh:
            components = json.load(fh)["components"]
        out = {name: {"kind": c["kind"], "sha256": "".join(c["sha256"].split())} for name, c in components.items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as err:
        raise Refused(f"{rel} could not be read ({err.__class__.__name__}): restore it from git") from None
    for name, c in out.items():
        if c["kind"] not in APEX_KINDS or not isinstance(c["sha256"], str) or not SHA256.fullmatch(c["sha256"]):
            raise Refused(f"{rel}: {name} needs a kind (ApexClass or ApexTrigger) and a sha256")
    return out


def sf_moment(text):
    """A Salesforce datetime ('2026-10-26T14:03:11.000+0000') as an aware UTC datetime, else None."""
    for shape in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.datetime.strptime(str(text or ""), shape).astimezone(datetime.timezone.utc)
        except ValueError:
            continue
    return None


def utc_text(when):
    return when.strftime("%Y-%m-%d %H:%M UTC") if when else "an unreadable date"


def apex_attention(org, expected=None):
    """ATTENTION items, (title, detail), for each watched Apex component whose body in the org is
    not the build recorded in `expected` (default: expected_apex(), read at call time): changed,
    missing, or a body that could not be read. Each item names its component, the LastModifiedDate
    and the modifier's user id - never a name, never a line of the body. Reads only."""
    if expected is None:
        expected = expected_apex()
    items = []
    for kind, word in APEX_KINDS.items():
        names = sorted(n for n, c in expected.items() if c["kind"] == kind)
        if not names:
            continue
        found = {}
        for r in org.query(f"SELECT Id, Name, Body, LastModifiedDate, LastModifiedById FROM {kind} "
                           f"WHERE NamespacePrefix = null AND Name IN ({', '.join(quoted(n) for n in names)})"):
            found.setdefault(r.get("Name"), r)
        for name in names:
            r = found.get(name)
            if r is None:
                items.append((f"SF: the Apex {word} {name} is not in Salesforce",
                              f"The runner found no {kind} named {name} (no namespace): attendance from "
                              f"Jotform may not be processed at all. Incident #238; {WATCH_SECTION}."))
                continue
            who = str(r.get("LastModifiedById") or "")
            who = who if SF_ID.fullmatch(who) else "an unreadable id"
            changed = f"Last modified {utc_text(sf_moment(r.get('LastModifiedDate')))} by user {who}."
            body = r.get("Body")
            if not isinstance(body, str) or not body.strip() or body.strip() == "(hidden)":
                items.append((f"SF: the Apex {word} {name}: could not read the body",
                              f"Salesforce answered no body for it, so it could not be compared with "
                              f"glow/apex_fingerprints.json. {changed} The runner's user may lack the "
                              f"permission to read Apex; {WATCH_SECTION}."))
            elif apex_fingerprint(body) != expected[name]["sha256"]:
                items.append((f"SF: the Apex {word} {name} has changed in Salesforce",
                              f"Its body is not the build recorded in glow/apex_fingerprints.json. {changed} "
                              f"Another team's release overwrote the attendance processor on 2026-10-26 "
                              f"unnoticed (#238): find out who changed it and why before anything else; "
                              f"{WATCH_SECTION}."))
    return items


def batch_gap_attention(org, now, hours=48):
    """[(title, detail)] when, on a weekday (UTC), the newest Jotform batch is older than `hours`
    or there is none; [] otherwise. Exactly `hours` old is not yet a gap. Reads only."""
    now = now.astimezone(datetime.timezone.utc)
    if now.weekday() >= 5:
        return []
    records = org.query(NEWEST_JOTFORM_BATCH)
    newest = sf_moment(records[0].get("CreatedDate")) if records else None
    if records and newest is None:
        raise Refused("the newest Jotform batch has no readable CreatedDate")
    if newest is not None and now - newest <= datetime.timedelta(hours=hours):
        return []
    since = (f"The newest batch created by Jotform is from {utc_text(newest)}, "
             f"{(now - newest).total_seconds() / 3600:.0f} hours before this run."
             if newest else "Salesforce has no batch created by Jotform at all.")
    return [(f"SF: no Jotform attendance batch for over {hours} hours",
             f"{since} Submissions may not be reaching Salesforce (a frozen user, a Jotform connection "
             f"that needs re-authorising): run tools/integration_status.py; {WATCH_SECTION}.")]
