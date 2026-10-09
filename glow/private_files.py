"""Files that can hold girls' names or record ids, kept the way the Salesforce tools keep them:
owner-only (folders 0700, files 0600 - also when they were there with a wider mode) and, inside
this checkout, only under data/ (git-ignored).

  private_folder(folder, ...)  the --dir guard: under data/ inside the checkout; made, owner-only
  keep_private(folder)         the folder and the files in it owner-only again
  open_private / save_private  a file opened owner-only; a whole file replaced all at once
  Ledger(path, cols)           an append-only CSV ledger (each tool's ledger.csv), last_rows()
  stamp, rel, sha256, load_json  the UTC stamp, a path as printed, a file's hash, a JSON input

A refusal is glow.salesforce.Refused: the tools that use this module stop on it.
"""
import csv
import datetime
import hashlib
import json
import os

from .salesforce import Refused

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAMP = "%Y-%m-%dT%H:%M:%SZ"


def stamp(moment=None):
    """A moment (default: now) as UTC text like 2026-09-30T12:00:00Z."""
    if moment is None:
        moment = datetime.datetime.now(datetime.timezone.utc)
    return moment.astimezone(datetime.timezone.utc).strftime(STAMP)


def rel(path):
    """A path as the tools print it: relative to the checkout when inside it, else absolute."""
    path = os.path.abspath(path)
    return os.path.relpath(path, REPO) if path.startswith(REPO + os.sep) else path


def sha256(path):
    """The file's SHA-256 (hex), or 'absent' when there is no such file."""
    if not os.path.exists(path):
        return "absent"
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def load_json(path, what):
    """A JSON input; a missing or unreadable one is a refusal that names `what`."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise Refused(f"{what} is missing: {rel(path)}") from None
    except (ValueError, OSError):
        raise Refused(f"{what} cannot be read as JSON: {rel(path)}") from None


# ---- folders ------------------------------------------------------------------------------------
def within(path, root):
    """Is `path` the folder `root` or somewhere under it? By inode: symlinks and letter case do not
    fool it. A root that does not exist holds nothing."""
    if not os.path.exists(root):
        return False
    path = os.path.realpath(path)
    while True:
        if os.path.exists(path) and os.path.samefile(path, root):
            return True
        parent = os.path.dirname(path)
        if parent == path:
            return False
        path = parent


def private_folder(folder, what="the folder", why="never committed", repo=REPO, make=True):
    """`folder`, absolute, ready for owner-only files. Inside the checkout `repo` it must be under
    data/; a fresh checkout has no data/ yet, so data/ is made first (0700) when the folder's path
    is under it - within() sees only what exists. make: the folder is made when missing; otherwise
    a missing one is a refusal. Either way it is set 0700."""
    folder, data = os.path.abspath(folder), os.path.join(repo, "data")
    if not make and not os.path.isdir(folder):
        raise Refused(f"--dir: there is no folder {folder}")
    if folder == data or folder.startswith(data + os.sep):
        os.makedirs(data, 0o700, exist_ok=True)
    if within(folder, repo) and not within(folder, data):
        raise Refused(f"--dir: inside the checkout {what} must be under data/ ({why})")
    if make:
        os.makedirs(folder, 0o700, exist_ok=True)
    os.chmod(folder, 0o700)
    return folder


def keep_private(folder):
    """The folder and the files in it hold names: the owner only, whoever created them."""
    os.chmod(folder, 0o700)
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if os.path.isfile(path) and not os.path.islink(path):
            os.chmod(path, 0o600)


# ---- files --------------------------------------------------------------------------------------
def open_private(path, mode):
    """A file only the owner can read, also when it already existed with a wider mode."""
    flags = os.O_WRONLY | os.O_CREAT | (os.O_APPEND if mode == "a" else os.O_TRUNC)
    fd = os.open(path, flags, 0o600)
    os.fchmod(fd, 0o600)
    return os.fdopen(fd, mode, encoding="utf-8", newline="")


def save_private(path, text):
    """All of the new content or none of it: written beside the file, then moved onto it."""
    with open_private(path + ".new", "w") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(path + ".new", path)


class Ledger:
    """An append-only CSV of fixed columns, owner-only: the header goes in with the first row (also
    into a file a run left empty), and every row is on disk (fsync) before append() returns. A
    record's last row is its state (last_rows)."""

    def __init__(self, path, cols):
        self.path, self.cols = path, list(cols)

    def read(self):
        """Every row, as text; [] when there is no file or an empty one. Another header is a refusal."""
        if not os.path.exists(self.path) or os.path.getsize(self.path) == 0:
            return []
        with open(self.path, encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames != self.cols:
                raise Refused(f"{rel(self.path)} does not start with its header line - restore it before "
                              "anything else: " + ",".join(self.cols))
            return list(reader)

    def append(self, row, rows=None):
        """One row, its columns in order ('' for one it lacks). `rows` (what read() gave) gets it too,
        as read() would give it back."""
        with open_private(self.path, "a") as fh:
            writer = csv.DictWriter(fh, fieldnames=self.cols, lineterminator="\n")
            if os.fstat(fh.fileno()).st_size == 0:
                writer.writeheader()
            writer.writerow({col: row.get(col, "") for col in self.cols})
            fh.flush()
            os.fsync(fh.fileno())
        if rows is not None:
            rows.append({col: str(row.get(col, "")) for col in self.cols})


def last_rows(rows, key):
    """{row[key]: its last row}: in an append-only ledger the last line is a record's state."""
    out = {}
    for row in rows:
        out[row[key]] = row
    return out
