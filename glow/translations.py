"""A form's translation store (GET / POST /form/{id}/translations): read it, save it before a
write, expand the "{n}" entries, and replace languages.

POST /form/{id}/translations REPLACES the whole dictionary of every language it carries
(CLAUDE.md rule 9, learned 2026-08-27). So every writer GETs the store (read_store), merges
its entries into each language WHOLE, saves the store it read (save_store), and only then
POSTs and re-reads (replace_languages, which refuses a POST without that saved file). `base`
and `en` are the English source maps; they hold every roster option - every girl's name - so
the saved store is readable by its owner only, and Jotform's answer is never echoed.
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_KEYS = ("base", "en")    # the English source maps, never a language to translate into
SESSIONS = range(1, 16)         # what "{n}" stands for: the session numbers, 1 to 15


def read_store(client, form_id):
    """The form's whole store, {language: {md5 key: text}}; {} when Jotform answers with
    anything else (a store without a language comes back as a list)."""
    store = client.get(f"/form/{form_id}/translations")
    return store if isinstance(store, dict) else {}


def save_store(form_id, store, stamp):
    """The whole translation store, before it is replaced, to
    backups/translations/<form>-<stamp>-before.json (backups/ is never committed). Never
    over an earlier file: after a failed POST, a re-run with the same stamp would otherwise
    replace the true 'before' - the rollback. Readable by its owner only (mode 600): `base`
    and `en` hold every girl's name. Returns the path."""
    folder = os.path.join(REPO, "backups", "translations")
    os.makedirs(folder, exist_ok=True)
    for n in range(1, 100):
        path = os.path.join(folder, f"{form_id}-{stamp}{'' if n == 1 else f'-{n}'}-before.json")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        os.fchmod(fd, 0o600)               # whatever the umask
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=1)
        return path
    sys.exit(f"99 store backups for {form_id} at {stamp} already - look in {folder}")


def expand_n(entries):
    """{English: translation} as the tools/translations_*.json files hold it, with every
    entry whose English carries "{n}" written out for n = 1 to 15 - in the English and in
    the translation (a string, or {language: string}). Keys starting with "_" are comments
    and dropped; every other entry is kept as it is."""
    def fill(value, n):
        if isinstance(value, str):
            return value.replace("{n}", str(n))
        return {lang: text.replace("{n}", str(n)) for lang, text in value.items()}

    out = {}
    for english, value in entries.items():
        if english.startswith("_"):
            continue
        if "{n}" in english:
            for n in SESSIONS:
                out[english.replace("{n}", str(n))] = fill(value, n)
        else:
            out[english] = value if isinstance(value, str) else dict(value)
    return out


def replace_languages(client, form_id, languages, label, saved):
    """POST `languages` - {language: its WHOLE dictionary}, each replacing that language on
    the form - and re-read the store. `saved`: the save_store() path of the store this POST
    replaces; without that file nothing is sent. Returns the store as re-read (read_store)."""
    if not saved or not os.path.exists(saved):
        raise ValueError(f"form {form_id}: save the store (save_store) before a POST replaces "
                         "its languages")
    client.post_json(f"/form/{form_id}/translations", languages, label)
    return read_store(client, form_id)


def reads_back(after, languages):
    """Whether every entry of `languages` ({language: {key: text}}) reads back as sent."""
    return all(after.get(lang, {}).get(k) == v for lang, d in languages.items() for k, v in d.items())
