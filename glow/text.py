"""Text normalization shared by every tool (byte-equal to the copies it replaced;
test/glow_lib_test.py compares against the old implementations)."""
import hashlib
import unicodedata


def key(s):
    """Case-insensitive comparison key: collapse whitespace, lowercase."""
    return " ".join(str(s or "").split()).lower()


def name_key(s):
    """key(), plus accents folded away (NFKD, combining marks dropped)."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split()).lower()


def md5(s):
    """Jotform's translation-dictionary key: md5 of the plain English text."""
    return hashlib.md5(s.encode("utf-8")).hexdigest()
