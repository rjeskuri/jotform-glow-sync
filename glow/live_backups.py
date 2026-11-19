"""The backup records the live gate trusts for an automatic go (ticket #146).

record() appends one tab-separated line per backup to <checkout>/.claude/live_backups.log:
`<YYYY-MM-DD HH:MM:SS>\\t<target>\\t<id>\\t<path>` - the local time, the path relative to the
checkout. .claude/hooks/live_gate.sh lets a live write through without a prompt when a record from
today names what it writes (`jotform <form id>|all`, `sheet <Tab>|all`, `github all`) and its path
still exists inside the checkout.

Only the backup tools call it, once the backup is on disk: glow/backup.py snapshot() (so
backup_forms.py --form and every tool's own snapshot), backup_forms.py (`jotform all`, after every
form), tools/sheets_client.py export / export-all, tools/github_switches.py backup. The file is
gitignored and protected (.claude/hooks/protected_paths.sh); a command that writes it by hand, or
calls this module, is refused by the gate as a self-approval.
"""
import datetime
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def log_path(repo=None):
    """<checkout>/.claude/live_backups.log (REPO read at the call, so a test can point it elsewhere)."""
    return os.path.join(repo or REPO, ".claude", "live_backups.log")


def relative(path, repo):
    """`path` relative to the checkout `repo` (a relative path is the working directory's), or None
    when it lies outside it - as written, or with symbolic links resolved."""
    full = os.path.abspath(path)
    for a, b in ((full, os.path.abspath(repo)), (os.path.realpath(full), os.path.realpath(repo))):
        rel = os.path.relpath(a, b)
        if rel != os.pardir and not rel.startswith(os.pardir + os.sep) and not os.path.isabs(rel):
            return rel
    return None


def record(target, ident, path, repo=None):
    """Append `<now>\\t<target>\\t<ident>\\t<path relative to the checkout>` to the checkout's
    .claude/live_backups.log and return the line. `repo` is the checkout the backup was saved in
    (default: this one). Refused (ValueError), with nothing written: an empty field, one holding a
    tab or a line break (it would forge a second record), a backup that does not exist, and one
    outside the checkout (the gate would never count it)."""
    repo = repo or REPO
    for name, value in (("target", target), ("id", ident), ("path", path)):
        if not isinstance(value, str) or not value or any(c in value for c in "\t\r\n"):
            raise ValueError(f"backup record: the {name} {value!r} is empty or holds a tab or a line break")
    if not os.path.exists(path):
        raise ValueError(f"backup record: there is no backup at {path}")
    rel = relative(path, repo)
    if rel is None:
        raise ValueError(f"backup record: {path} is outside the checkout {repo}")
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}\t{target}\t{ident}\t{rel}\n"
    os.makedirs(os.path.dirname(log_path(repo)), exist_ok=True)
    with open(log_path(repo), "a", encoding="utf-8") as f:
        f.write(line)
    return line
