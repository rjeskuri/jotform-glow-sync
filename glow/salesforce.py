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
"""
import json
import re
import subprocess
import urllib.parse

API = "v67.0"
INSTANCE = "https://globalglow.my.salesforce.com"      # production (read 2026-10-06)
NEXT_PAGE = re.compile(r"/services/data/v\d+\.\d+/query/[A-Za-z0-9_-]+")
NEXT_PAGE_ALL = re.compile(r"/services/data/v\d+\.\d+/query(?:All)?/[A-Za-z0-9_-]+")   # queryAll's next pages
PLAIN_HOST = re.compile(r"https://[A-Za-z0-9.-]+(:\d+)?")
UNSAFE = re.compile(r'[\x00-\x20\x7f"\\]')              # nothing a curl config line could misread
SAY = re.compile(r"[^A-Za-z0-9 _.,:;'()/-]")            # what of an OAuth error may be repeated


class Refused(Exception):
    """Stop: what is wrong and what to do."""


def quoted(value):
    """A SOQL string literal."""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


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
