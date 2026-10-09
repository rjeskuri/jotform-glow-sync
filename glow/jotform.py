"""The one Jotform API client, dry-run gated.

It replaced eight per-script curl wrappers (docs/intent/2026-09-01-shared-
jotform-client.md). The single primitive is call(): any argument list that
contains -X POST/PUT/DELETE or a --data* flag is a WRITE - it is recorded in
self.calls and skipped unless the client was built with apply=True. Reads
always run. A mislabelled write can therefore never slip through the gate.

Failures raise JotformError with the label; retries (add_language.py's
behaviour) and allow_fail (clone_regional.py's) are per-client / per-call
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

API_BASE = "https://api.jotform.com"
_WRITE_METHODS = {"POST", "PUT", "DELETE"}
# Linux: one argument may not exceed 131,072 bytes (MAX_ARG_STRLEN); stay clear of it.
MAX_ARG_BYTES = 120_000


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
