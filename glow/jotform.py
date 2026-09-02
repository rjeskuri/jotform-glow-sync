"""The one Jotform API client, dry-run gated.

It replaced eight per-script curl wrappers (docs/intent/2026-09-01-shared-
jotform-client.md). The single primitive is call(): any argument list that
contains -X POST/PUT/DELETE or a --data* flag is a WRITE - it is recorded in
self.calls and skipped unless the client was built with apply=True. Reads
always run. A mislabelled write can therefore never slip through the gate.

Failures raise JotformError with the label; retries (add_language.py's
behaviour) and allow_fail (clone_regional.py's) are per-client / per-call
options. glow.cli.run(main) turns the error into a clean sys.exit message.
"""
import json
import subprocess
import time

API_BASE = "https://api.jotform.com"
_WRITE_METHODS = {"POST", "PUT", "DELETE"}


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
        extra = "".join(f"&{k}={v}" for k, v in params.items())
        return f"{API_BASE}{path}?apiKey={self.key}{extra}"

    def call(self, args, label, *, allow_fail=False):
        """Run curl with `args`. Writes are gated on self.apply; see the module doc."""
        if is_write(args):
            self.calls.append(label)
            if not self.apply:
                return None
        if self.max_time is not None:
            args = ["--max-time", str(self.max_time)] + list(args)
        last = None
        for attempt in range(1, self.retries + 1):
            out = subprocess.run(["curl", "-sS"] + list(args),
                                 capture_output=True, text=True)
            try:
                resp = json.loads(out.stdout)
            except json.JSONDecodeError:
                last = JotformError(f"{label}: non-JSON response: "
                                    f"{out.stdout[:200]!r} {out.stderr[:200]}")
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
                          "--data-binary", json.dumps(payload)], label)

    def put_json(self, path, payload, label):
        """JSON PUT (properties update)."""
        return self.call(["-X", "PUT", self.url(path),
                          "-H", "Content-Type: application/json",
                          "--data-binary", json.dumps(payload)], label)

    def delete(self, path, label):
        return self.call(["-X", "DELETE", self.url(path)], label)
