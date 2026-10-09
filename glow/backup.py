"""Form snapshots: the rollback path every live write takes first (CLAUDE.md: back up
before a live write).

snapshot() GETs a form's questions and properties (conditions, e-mails, the Salesforce
integration, status) into backups/<form id>/<part>-<stamp>.json and <part>-latest.json;
path() names such a file; stamp() is the one stamp format, to the second, so a re-run
within the minute never writes the half-changed form over the true "before";
save_conditions() writes the conditions-only copy, the one file of a snapshot that may
leave the machine (the full properties hold staff e-mail settings and the Salesforce
integration). backups/ is never committed. backup_forms.py at the repository root is the
command line; restore_conditions.py puts the conditions back.
"""
import datetime
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARTS = ("questions", "properties")
STAMP = "%Y-%m-%dT%H%M%S"


def stamp(now=None):
    """The stamp of a snapshot taken at `now` (default: the local clock now), to the second."""
    return (now or datetime.datetime.now()).strftime(STAMP)


_stamp = stamp          # snapshot()'s and path()'s `stamp` parameter shadows the function


def folder(form_id):
    """backups/<form id>/ (read from REPO at the call, so a test can point it elsewhere)."""
    return os.path.join(REPO, "backups", form_id)


def path(form_id, part, stamp="latest"):
    """backups/<form id>/<part>-<stamp>.json: part is questions, properties or conditions."""
    return os.path.join(folder(form_id), f"{part}-{stamp}.json")


def snapshot(form_id, client, stamp=None, latest=True):
    """GET the form's questions and properties into <part>-<stamp>.json and, with
    `latest`, <part>-latest.json (what restore_conditions.py restores by default).
    Returns counts: {"questions", "conditions", "emails", "salesforce": yes|NO, "stamp"}."""
    stamp = stamp or _stamp()
    os.makedirs(folder(form_id), exist_ok=True)
    got = {}
    for part in PARTS:
        content = client.get(f"/form/{form_id}/{part}")
        for name in (stamp, "latest") if latest else (stamp,):
            with open(path(form_id, part, name), "w") as f:
                json.dump(content, f, indent=1)
        got[part] = content

    props = got["properties"]
    integ = props.get("integrations") or {}
    sf = integ.get("salesforceV2") if isinstance(integ, dict) else None
    return {
        "questions": len(got["questions"]),
        "conditions": len(props.get("conditions", [])),
        "emails": len(props.get("emails", [])),
        "salesforce": "yes" if sf else "NO",
        "stamp": stamp,
    }


def save_conditions(form_id, stamp):
    """backups/<form id>/conditions-<stamp>.json: the conditions of properties-latest.json
    alone (restore_conditions.py --form <id> --from conditions-<stamp>.json). Returns its
    path; an unreadable snapshot raises OSError or ValueError."""
    with open(path(form_id, "properties"), encoding="utf-8") as f:
        props = json.load(f)
    out = path(form_id, "conditions", stamp)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"conditions": props.get("conditions", [])}, f, indent=1)
    return out
