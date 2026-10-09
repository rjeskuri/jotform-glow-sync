"""The one Jotform API client, dry-run gated.

It replaced eight per-script curl wrappers (docs/intent/2026-09-01-shared-
jotform-client.md). The single primitive is call(): any argument list that
contains -X POST/PUT/DELETE or a --data* flag is a WRITE - it is recorded in
self.calls and skipped unless the client was built with apply=True. Reads
always run. A mislabelled write can therefore never slip through the gate.

Failures raise JotformError with the label; retries (add_language.py's
behaviour) and allow_fail (the retired clone script's) are per-client / per-call
options. glow.cli.run(main) turns the error into a clean sys.exit message.

A JSON body goes to curl on standard input ("--data-binary @-"), never as an
argument: Linux refuses any single argument over 131,072 bytes ("Argument
list too long"), and a form's rules pass that (Africa's conditions are about
153 KB since the club guard, 2026-09-30) - on the Mac such a call works, on
the GitHub runner it would not.
"""
import json
import subprocess
import time
import urllib.parse
from zoneinfo import ZoneInfo

API_BASE = "https://api.jotform.com"
_WRITE_METHODS = {"POST", "PUT", "DELETE"}
# Linux: one argument may not exceed 131,072 bytes (MAX_ARG_STRLEN); stay clear of it.
MAX_ARG_BYTES = 120_000
# Jotform's clock: a submission's created_at and a form's last_submission are US Eastern wall
# time, 'yyyy-mm-dd hh:mm:ss' (not the sheet's zone, glow.sync.SHEET_ZONE, though the same today)
CLOCK = ZoneInfo("America/New_York")


class JotformError(RuntimeError):
    pass


def is_write(args):
    """True when the curl argument list would change something."""
    for i, a in enumerate(args):
        if a == "-X" and i + 1 < len(args) and args[i + 1].upper() in _WRITE_METHODS:
            return True
        if isinstance(a, str) and a.startswith("--data"):
            return True
    return False


class Client:
    def __init__(self, api_key, apply=False, *, retries=1, backoff=8.0, max_time=None,
                 sleep=time.sleep):
        self.key = api_key
        self.apply = apply
        self.retries = max(1, retries)
        self.backoff = backoff
        self.max_time = max_time
        self.sleep = sleep
        self.calls = []          # every write's label, in order (dry run and apply alike)

    def url(self, path, **params):
        """The API URL of `path`: the key and `params` as its query, every value URL-encoded
        here, once - a caller passes plain values (a submissions filter is its JSON text)."""
        query = urllib.parse.urlencode({"apiKey": self.key, **params}, quote_via=urllib.parse.quote, safe="")
        return f"{API_BASE}{path}?{query}"

    def call(self, args, label, *, allow_fail=False, body=None):
        """Run curl with `args`; `body`, when given, is sent on curl's standard input
        (the argument list then says "--data-binary @-"). Writes are gated on
        self.apply; see the module doc."""
        big = max((len(str(a).encode("utf-8")) for a in args), default=0)
        if big > MAX_ARG_BYTES:           # before the gate: a dry run must refuse what an apply would
            raise JotformError(f"{label}: an argument of {big} bytes cannot go on a command line "
                               f"(Linux allows 131,072) - send it as the body")
        if is_write(args):
            self.calls.append(label)
            if not self.apply:
                return None
        if self.max_time is not None:
            args = ["--max-time", str(self.max_time)] + list(args)
        extra = {} if body is None else {"input": body}
        last = None
        for attempt in range(1, self.retries + 1):
            try:
                out = subprocess.run(["curl", "-sS"] + list(args), capture_output=True,
                                     text=True, encoding="utf-8", **extra)
            except OSError as e:          # e.g. E2BIG: never a half-made request
                raise JotformError(f"{label}: curl could not be started: {e.strerror or e}") from e
            try:
                resp = json.loads(out.stdout)
            except json.JSONDecodeError:
                # a cut-off JSON answer is API content (a page of submissions starts with a
                # submission's id and the submitter's IP address): say how much came, never
                # quote it. Anything else (an HTML 504 page) is quoted as before.
                shown = (f"a cut-off JSON answer, {len(out.stdout)} characters, not shown"
                         if out.stdout.lstrip()[:1] in ("{", "[") else repr(out.stdout[:200]))
                last = JotformError(f"{label}: non-JSON response: {shown} {out.stderr[:200]}")
            else:
                if resp.get("responseCode") == 200:
                    return resp["content"]
                last = JotformError(f"{label}: {resp.get('responseCode')} "
                                    f"{resp.get('message')}")
            if attempt < self.retries:
                print(f"  ! {label}: attempt {attempt}/{self.retries} failed - "
                      f"retrying in {self.backoff:g}s")
                self.sleep(self.backoff)
        if allow_fail:
            print(f"  ! {label}: {last} (continuing)")
            return None
        raise last

    # ---- the shapes the tools use
    def get(self, path, **params):
        return self.call([self.url(path, **params)], f"GET {path}")

    def submissions(self, form_id, filter=None, *, page=100, enough=None, label=None):
        """The form's submissions, any status, read page by page (`page` per request; Jotform
        allows up to 1000) in Jotform's default order, newest first - no `orderby`, whose
        direction is not proven. `filter`: Jotform's submissions filter as a dict
        ({"created_at:gt": "2026-09-24 08:03:00"}), sent as its JSON text (url() encodes it).
        A submission arriving meanwhile repeats one on the next page: kept once, by id, as first
        read. enough(page), given each page as it came: True stops the reading after it. Reading
        the whole form (no filter, no enough), the form's own count, read afterwards, is the
        check. JotformError, with `label` (default 'form <id>'), for an answer that is not a list
        of submissions with ids and for a count the pages fall short of."""
        label = label or f"form {form_id}"
        params = {} if filter is None else {"filter": json.dumps(filter)}
        seen, out, offset = set(), [], 0
        while True:
            got = self.get(f"/form/{form_id}/submissions", limit=page, offset=offset, **params)
            if not isinstance(got, list) or not all(isinstance(s, dict) and s.get("id") for s in got):
                raise JotformError(f"{label}: the submissions answer is not a list of submissions with "
                                   "ids - an answer shape this tool does not know")
            for sub in got:
                if sub["id"] not in seen:
                    seen.add(sub["id"])
                    out.append(sub)
            stop = enough is not None and enough(got)
            if stop or len(got) < page:
                break
            offset += page
        if filter is None and enough is None:
            reported = int((self.get(f"/form/{form_id}") or {}).get("count") or 0)
            if len(out) < reported:
                raise JotformError(f"{label}: fetched {len(out)} submissions but the form reports {reported} - "
                                   "one was missed while paging (a deletion meanwhile?); run it again")
        return out

    def post_form(self, path, data, label):
        """form-urlencoded POST (question create/update - MERGES properties)."""
        args = ["-X", "POST", self.url(path)]
        for k, v in data.items():
            args += ["--data-urlencode", f"{k}={v}"]
        return self.call(args, label)

    def post_json(self, path, payload, label):
        """JSON POST (translations - REPLACES each posted language)."""
        return self.call(["-X", "POST", self.url(path),
                          "-H", "Content-Type: application/json",
                          "--data-binary", "@-"], label, body=json.dumps(payload))

    def put_json(self, path, payload, label):
        """JSON PUT (properties update)."""
        return self.call(["-X", "PUT", self.url(path),
                          "-H", "Content-Type: application/json",
                          "--data-binary", "@-"], label, body=json.dumps(payload))

    def delete(self, path, label):
        return self.call(["-X", "DELETE", self.url(path)], label)


def public_page(form_id, max_time=90):
    """The form's public page (https://form.jotform.com/<id>) as a mentor's browser receives
    it - no API key, so nothing of the account goes with the request. Kept in memory by every
    caller (a served page lists every roster: never printed or saved). Raises JotformError when
    curl fails: a page that could not be fetched never reads as an empty one."""
    url = f"https://form.jotform.com/{form_id}"
    try:
        out = subprocess.run(["curl", "-sSL", "--max-time", str(max_time), "-A", "Mozilla/5.0", url],
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as e:
        raise JotformError(f"public page of form {form_id}: curl could not be started: "
                           f"{e.strerror or e}") from e
    if out.returncode != 0:
        raise JotformError(f"public page of form {form_id}: curl exited {out.returncode}: "
                           f"{out.stderr.strip()[:200]}")
    return out.stdout
