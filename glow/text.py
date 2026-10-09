"""Text normalization shared by every tool (byte-equal to the copies it replaced;
test/glow_lib_test.py compares against the old implementations).

key / name_key are the Python side's comparison keys; tidy / cell_key / nfc_key are
the sheet's own (appsscript/Normalize.gs tidy_ and key_), for tools that match the
tabs' cells as its scripts do. The two differ on invisible characters (key keeps them,
cell_key drops them): a known divergence, BACKLOG 28 - never swap one for the other.
"""
import hashlib
import re
import unicodedata

# the invisible characters the Apps Script's tidy_ drops (Normalize.gs INVISIBLE)
INVISIBLE = re.compile("[\u200b\u200c\u200d\u200e\u200f\u2060\ufeff]")


def key(s):
    """Case-insensitive comparison key: collapse whitespace, lowercase."""
    return " ".join(str(s or "").split()).lower()


def name_key(s):
    """key(), plus accents folded away (NFKD, combining marks dropped)."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split()).lower()


def tidy(s):
    """Normalize.gs tidy_: invisible characters dropped, whitespace collapsed."""
    return " ".join(INVISIBLE.sub("", str(s or "")).split())


def cell_key(s):
    """Normalize.gs key_ - how the sheet's own scripts group partner and club
    cells (key() keeps invisible characters: BACKLOG 28)."""
    return tidy(s).lower()


def nfc_key(s):
    """cell_key after Unicode NFC, for finding a name typed on a command line."""
    return cell_key(unicodedata.normalize("NFC", str(s or "")))


def md5(s):
    """Jotform's translation-dictionary key: md5 of the plain English text."""
    return hashlib.md5(s.encode("utf-8")).hexdigest()
