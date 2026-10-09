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

Beside the client, what every Salesforce tool relies on: the org's record types and the pilot
accounts on hold, how the attendance processor compares a submitted club name with an Account's
(sf_match), which names may hide nothing (has_invisible), and the partner map
(glow/sf_partners.csv, read_partners).
"""
import argparse
import csv
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
