#!/usr/bin/env python3
"""Copy, move and list the Monthly Report reports and dashboards in Salesforce, and undo the moves
(ticket #71, epic #68; RUNBOOK "Copying and moving reports and dashboards"). It never deletes.

  python3 tools/sf_report_folders.py list --vpn-off --folder "DHIS2 Reports" [--folder NAME ...] [--kind report|dashboard]
  python3 tools/sf_report_folders.py copy --vpn-off --kind report --id 00O... --tag "#72" [--apply]
  python3 tools/sf_report_folders.py move --vpn-off --plan plan.csv [--apply] [--limit 1]
  python3 tools/sf_report_folders.py undo --vpn-off --ledger data/sf_report_folders/ledger.csv [--apply] [--limit N]

list (read-only): CSV on stdout, kind,id,developer_name,label,folder,last_run,used_by (used_by: the
ids of the dashboards with a component on the report, ;-separated); the counts on stderr.
copy: clones a report or a dashboard into the one folder named "Decommissioned" of its kind. A
report's copy keeps its label (cut to 40 characters) and gets the description "copy of <id>, <tag>"
by a PATCH of the copy after the clone (#69's API proof, Report steps 1 and 5);
a dashboard's clone takes no name or description (the API refuses them, #69's API proof).
move: the plan CSV has the columns kind,id,to_folder,new_label; to_folder is a folder name that
must be exactly one folder of the kind; a blank new_label keeps the label. A report is moved (and
relabelled) by PATCH and keeps its Id. A dashboard row is refused: Salesforce refuses every
dashboard PATCH, so a dashboard is moved or renamed by hand in Lightning.
undo: puts each move of the ledger back to its from_folder_id and old_label, last first; copies stay.
A from_folder_id that is the organization's id (00D...) is "Public Reports", which has no Folder.

Every subcommand needs --vpn-off; copy, move and undo are dry runs unless --apply (Ryan's go).
Refused before any write: the folders named "Attendance" (this repo's own dashboard) as a source or
a target, a folder name that is not exactly one folder of the kind, a report label over 40
characters (a new one, or the current one of a report the plan relabels: undo could not restore
it), retiring a report that a dashboard outside Decommissioned still uses, an unknown id.
Each write is one request, read back by SOQL (the same Id, its folder and label); a write that does
not read back stops the run. One ledger row per write (data/sf_report_folders/ledger.csv, owner
only, never committed): on disk as "sending" before its request, rewritten in place as ok or failed
before the next write (a copy's row gets the copy's id first). The tool reads Folder, Report, Dashboard and
DashboardComponent only, and prints ids, labels, folder names, counts and HTTP codes, never an
answer. Salesforce access is glow/salesforce.py's (the CLI's login).
"""
import argparse
import csv
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow.private_files import Ledger, private_folder, rel, stamp   # noqa: E402
from glow.salesforce import (API, Org, Refused, add_vpn_flag, error_codes, plain, positive,   # noqa: E402
                             quoted, require_vpn_off)

DEFAULT_DIR = os.path.join(REPO, "data", "sf_report_folders")
ANALYTICS = f"/services/data/{API}/analytics"
LEDGER_COLS = ["when", "action", "kind", "id", "from_folder_id", "to_folder_id", "old_label", "new_label",
               "copy_id", "tag", "status", "http"]
LIST_COLS = ["kind", "id", "developer_name", "label", "folder", "last_run", "used_by"]
PLAN_COLS = ["kind", "id", "to_folder", "new_label"]
FOLDER_TYPE = {"report": "Report", "dashboard": "Dashboard"}
DECOM, PROTECTED, NAME_LIMIT = "Decommissioned", "Attendance", 40
PUBLIC, ORG_ID_PREFIX = "Public Reports", "00D"     # "Public Reports" has no Folder: its id is the org's
ID18 = re.compile(r"[A-Za-z0-9]{18}")
BY_HAND = ("Salesforce refuses every dashboard PATCH (#69 API proof): move or rename a dashboard by hand "
           "in Lightning (RUNBOOK \"Copying and moving reports and dashboards\")")


def in_list(values):
    return "(" + ", ".join(quoted(v) for v in values) + ")"


# ---- reads ---------------------------------------------------------------------------------------
def folders_named(org, names, kinds):
    """The folders of `kinds` whose Name is exactly one of `names` (SOQL's = ignores case, this does not)."""
    types = in_list(FOLDER_TYPE[k] for k in kinds)
    found = plain(org.query(f"SELECT Id, Name, DeveloperName, Type FROM Folder WHERE Name IN {in_list(names)} "
                            f"AND Type IN {types}"))
    return [f for f in found if f.get("Name") in names]


def one_folder(org, name, kind):
    found = [f for f in folders_named(org, [name], [kind]) if f["Type"] == FOLDER_TYPE[kind]]
    if len(found) != 1:
        raise Refused(f'{len(found)} {kind} folders are named exactly "{name}", one expected - '
                      "check the name (letter case counts)")
    return found[0]


def folder_names(org, ids):
    """{id: folder name}; an organization id (00D...) is "Public Reports", which has no Folder record (a
    report there has the org's id as its OwnerId, #72)."""
    ids = sorted(set(ids))
    names = {i: PUBLIC for i in ids if i.startswith(ORG_ID_PREFIX)}
    rest = [i for i in ids if i not in names]
    if rest:
        names.update((f["Id"], f["Name"]) for f in
                     plain(org.query(f"SELECT Id, Name FROM Folder WHERE Id IN {in_list(rest)}")))
    return names


def items(org, kind, where):
    """Reports or dashboards as {kind, id, developer_name, label, folder_id, folder, last_run}."""
    if kind == "report":
        found = plain(org.query("SELECT Id, DeveloperName, Name, OwnerId, FolderName, LastRunDate FROM Report "
                                f"WHERE {where}"))
        label, folder, last_run = "Name", "OwnerId", "LastRunDate"    # a report's OwnerId is its folder
    else:
        found = plain(org.query(f"SELECT Id, DeveloperName, Title, FolderId, FolderName FROM Dashboard WHERE {where}"))
        label, folder, last_run = "Title", "FolderId", None
    return [{"kind": kind, "id": r["Id"], "developer_name": r.get("DeveloperName") or "",
             "label": r.get(label) or "", "folder_id": r.get(folder) or "", "folder": r.get("FolderName") or "",
             "last_run": (r.get(last_run) or "") if last_run else ""} for r in found]


def by_id(org, kind, ids):
    """{id: item} for every id, or Refused naming the ids that are no item of the kind."""
    found = {i["id"]: i for i in items(org, kind, f"Id IN {in_list(ids)}")} if ids else {}
    missing = [x for x in ids if x not in found]
    if missing:
        raise Refused(f"no {kind} has the id {', '.join(missing)} - check the id and its kind")
    return found


def used_by(org, report_ids):
    """report id -> the ids of the dashboards with a component on it."""
    out = {}
    if report_ids:
        for c in plain(org.query("SELECT Id, DashboardId, CustomReportId FROM DashboardComponent "
                                 f"WHERE CustomReportId IN {in_list(report_ids)}")):
            out.setdefault(c["CustomReportId"], set()).add(c["DashboardId"])
    return out


def read_back(org, kind, item_id, folder_id, label):
    """What SOQL says is wrong with the item, [] when it is in folder_id with label (None: any label)."""
    try:
        found = items(org, kind, f"Id = {quoted(item_id)}")
    except Refused as stop:
        return [f"the read-back did not answer ({stop})"]
    if len(found) != 1:
        return [f"the read-back finds no {kind} {item_id}"]
    wrong = []
    if found[0]["folder_id"] != folder_id:
        wrong.append(f'it reads back in "{found[0]["folder"]}" ({found[0]["folder_id"]}), not {folder_id}')
    if label is not None and found[0]["label"] != label:
        wrong.append(f'its label reads back as "{found[0]["label"]}", not "{label}"')
    return wrong


def http_said(status, answer):
    codes = " ".join(error_codes(answer))
    return f"Salesforce answered HTTP {status}" + (f" {codes}" if codes else "") + \
        (" (no answer: the outcome is unknown)" if status == 0 else "")


def not_protected(item):
    if item["folder"] == PROTECTED:
        raise Refused(f'{item["kind"]} {item["id"]} is in the folder "{PROTECTED}" (the Jotform attendance '
                      "dashboard's): epic #68 never touches it")


# ---- writes --------------------------------------------------------------------------------------
def open_ledger(folder):
    ledger = Ledger(os.path.join(folder, "ledger.csv"), LEDGER_COLS)
    ledger.read()                       # a ledger with another header is a refusal before any write
    return ledger


def sending(ledger, row):
    """The write's row, status "sending", on disk before its request goes out (a crash leaves it so:
    the outcome is unknown); finish() rewrites it in place."""
    row = dict(row, when=stamp(), status="sending", http="")
    ledger.append(row)
    return row


def finish(ledger, row, **fields):
    new = dict(row, when=stamp(), **fields)
    ledger.replace_last(row, new)
    return new


def patch_report(org, ledger, row, folder_id, name, label):
    """One PATCH of a report's folder (and name), read back, its ledger row; Refused when it is not
    as sent. `label` is the label the read-back expects (None: any)."""
    meta = {"folderId": folder_id}
    if name:
        meta["name"] = name
    row = sending(ledger, row)
    status, answer = org.call("PATCH", f"{ANALYTICS}/reports/{row['id']}", {"reportMetadata": meta})
    wrong = read_back(org, "report", row["id"], folder_id, label) if status == 200 else [http_said(status, answer)]
    finish(ledger, row, status="failed" if wrong else "ok", http=status)
    if wrong:
        raise Refused(f"{row['action']} of report {row['id']}: " + "; ".join(wrong) + " - STOPPED, nothing more "
                      f"written; its row is in {rel(ledger.path)} (undo puts back every move Salesforce took)")


# ---- the subcommands -----------------------------------------------------------------------------
def do_list(org, args):
    kinds = [args.kind] if args.kind else ["report", "dashboard"]
    folders = folders_named(org, args.folder, kinds)
    missing = [n for n in args.folder if n not in {f["Name"] for f in folders}]
    if missing:
        raise Refused("no " + " or ".join(kinds) + " folder is named exactly: " + ", ".join(f'"{n}"' for n in missing))
    found = []
    for kind in kinds:
        ids = [f["Id"] for f in folders if f["Type"] == FOLDER_TYPE[kind]]
        if ids:
            where = ("OwnerId" if kind == "report" else "FolderId") + f" IN {in_list(ids)}"
            found += items(org, kind, where)
    names = {f["Id"]: f["Name"] for f in folders}
    users = used_by(org, [i["id"] for i in found if i["kind"] == "report"])
    out = csv.writer(sys.stdout, lineterminator="\n")
    out.writerow(LIST_COLS)
    for i in sorted(found, key=lambda i: (i["kind"], names.get(i["folder_id"], ""), i["label"], i["id"])):
        out.writerow([i["kind"], i["id"], i["developer_name"], i["label"], names.get(i["folder_id"], i["folder"]),
                      i["last_run"], ";".join(sorted(users.get(i["id"], ())))])
    counts = ", ".join(f"{sum(1 for i in found if i['kind'] == k)} {k}s" for k in kinds)
    print(f"{counts} in " + ", ".join(f'"{n}"' for n in args.folder), file=sys.stderr)


def do_copy(org, args, folder):
    if not ID18.fullmatch(args.id):
        raise Refused(f"--id {args.id!r} is not an 18-character Salesforce id")
    item = by_id(org, args.kind, [args.id])[args.id]
    not_protected(item)
    decom = one_folder(org, DECOM, args.kind)
    description = f"copy of {item['id']}, {args.tag}"
    if args.kind == "report":
        label = item["label"][:NAME_LIMIT].rstrip()    # Salesforce stores a name trimmed
        path = f"{ANALYTICS}/reports?cloneId={item['id']}"
        body = {"reportMetadata": {"name": label, "folderId": decom["Id"]}}     # #69 proof, Report step 1
        said = f'as "{label}", then the description "{description}" by a PATCH of the copy'
    else:
        label, path, body = None, f"{ANALYTICS}/dashboards?cloneId={item['id']}", {"folderId": decom["Id"]}
        said = "with its title (rename and describe the copy by hand in Lightning)"
    print(f'  copy {args.kind} {item["id"]} "{item["label"]}" in "{item["folder"]}" into {DECOM} '
          f'({decom["Id"]}) {said}')
    if not args.apply:
        print("dry run: nothing was written (--apply --vpn-off writes, with Ryan's go)")
        return
    ledger = open_ledger(folder)
    row = sending(ledger, {"action": "copy", "kind": args.kind, "id": item["id"], "from_folder_id": item["folder_id"],
                           "to_folder_id": decom["Id"], "old_label": item["label"], "new_label": label or "",
                           "copy_id": "", "tag": args.tag})
    status, answer = org.call("POST", path, body)
    meta = (answer.get("reportMetadata") if args.kind == "report" else answer) if isinstance(answer, dict) else None
    copy_id = meta.get("id") if status == 200 and isinstance(meta, dict) else None
    copy_id = copy_id if isinstance(copy_id, str) and ID18.fullmatch(copy_id) else ""
    if not copy_id:
        wrong = [http_said(status, answer) + ("" if status != 200 else ", without the copy's id")]
    else:
        wrong = read_back(org, args.kind, copy_id, decom["Id"], label)
    if not wrong and args.kind == "report":
        row = finish(ledger, row, status="sending", copy_id=copy_id, http=status)   # the copy's id on disk first
        # #69 proof, Report step 5: the label and the description by a PATCH of the copy
        status, answer = org.call("PATCH", f"{ANALYTICS}/reports/{copy_id}",
                                  {"reportMetadata": {"name": label, "description": description}})
        wrong = read_back(org, "report", copy_id, decom["Id"], label) if status == 200 else \
            [http_said(status, answer) + " to the copy's description PATCH"]
    finish(ledger, row, status="failed" if wrong else "ok", copy_id=copy_id, http=status)
    if wrong:
        raise Refused(f"copy of {args.kind} {item['id']}" + (f" (the copy is {copy_id})" if copy_id else "") + ": "
                      + "; ".join(wrong) + f" - look at it in Salesforce; its row is in {rel(ledger.path)}")
    print(f"copied {args.kind} {item['id']} to {copy_id} in {DECOM}, read back; ledger {rel(ledger.path)}")


def read_plan(path):
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames != PLAN_COLS:
                raise Refused(f"{rel(path)}: the plan's columns must be {','.join(PLAN_COLS)}")
            rows = [{c: (r.get(c) or "").strip() for c in PLAN_COLS} for r in reader]
    except FileNotFoundError:
        raise Refused(f"--plan: there is no file {rel(path)}") from None
    if not rows:
        raise Refused(f"{rel(path)}: the plan has no rows")
    return rows


def check_plan(org, rows):
    """Every row's report and target folder, or Refused with every problem of the plan (before any write)."""
    problems, seen = [], set()
    for n, r in enumerate(rows, 1):
        where = f"row {n} ({r['kind']} {r['id']})"
        if r["kind"] == "dashboard":
            problems.append(f"{where}: {BY_HAND}")
        elif r["kind"] != "report":
            problems.append(f"{where}: the kind is report or dashboard")
        if not ID18.fullmatch(r["id"]):
            problems.append(f"{where}: not an 18-character Salesforce id")
        elif r["id"] in seen:
            problems.append(f"{where}: the id is in the plan twice - one row per report")
        seen.add(r["id"])
        if not r["to_folder"]:
            problems.append(f"{where}: to_folder is blank")
        elif r["to_folder"] == PROTECTED:
            problems.append(f'{where}: nothing moves into a folder "{PROTECTED}" (the Jotform attendance dashboard\'s)')
        if len(r["new_label"]) > NAME_LIMIT:
            problems.append(f"{where}: the new label has {len(r['new_label'])} characters, Salesforce takes "
                            f"{NAME_LIMIT} at most")
    if problems:
        raise Refused("the plan is refused, nothing was written:\n  " + "\n  ".join(problems))
    reports = by_id(org, "report", [r["id"] for r in rows])
    targets = folders_named(org, sorted({r["to_folder"] for r in rows}), ["report"])
    users = used_by(org, [r["id"] for r in rows if r["to_folder"] == DECOM])
    dashboards = {d["id"]: d for d in items(org, "dashboard", f"Id IN {in_list(sorted(set().union(*users.values())))}")} \
        if users else {}
    planned = []
    for n, r in enumerate(rows, 1):
        item, where = reports[r["id"]], f"row {n} (report {r['id']})"
        if item["folder"] == PROTECTED:
            problems.append(f'{where}: it is in the folder "{PROTECTED}" (the Jotform attendance dashboard\'s): '
                            "epic #68 never touches it")
        if r["new_label"] and len(item["label"]) > NAME_LIMIT:
            problems.append(f"{where}: its current label has {len(item['label'])} characters, over Salesforce's "
                            f"{NAME_LIMIT}: undo could not put it back - move it with the label kept")
        found = [f for f in targets if f["Name"] == r["to_folder"]]
        if len(found) != 1:
            problems.append(f'{where}: {len(found)} report folders are named exactly "{r["to_folder"]}", one '
                            "expected - check the name (letter case counts)")
        staying = [dashboards[d] for d in sorted(users.get(r["id"], ())) if d in dashboards
                   and dashboards[d]["folder"] != DECOM]
        if staying:
            problems.append(f"{where}: dashboards outside {DECOM} still use it: "
                            + ", ".join(f'{d["id"]} "{d["label"]}"' for d in staying)
                            + " - retire or change them first")
        planned.append((r, item, found[0] if len(found) == 1 else None))
    if problems:
        raise Refused("the plan is refused, nothing was written:\n  " + "\n  ".join(problems))
    return planned


def do_move(org, args, folder):
    planned = check_plan(org, read_plan(args.plan))
    for r, item, target in planned:
        change = f' as "{r["new_label"]}"' if r["new_label"] else ", label kept"
        print(f'  move report {item["id"]} "{item["label"]}" from "{item["folder"]}" to "{target["Name"]}" '
              f'({target["Id"]}){change}')
    todo = planned[:args.limit] if args.limit else planned
    if not args.apply:
        print(f"dry run: nothing was written ({len(todo)} to move; --apply --vpn-off writes, with Ryan's go)")
        return
    ledger = open_ledger(folder)
    for r, item, target in todo:
        row = {"action": "move", "kind": "report", "id": item["id"], "from_folder_id": item["folder_id"],
               "to_folder_id": target["Id"], "old_label": item["label"], "new_label": r["new_label"]}
        patch_report(org, ledger, row, target["Id"], r["new_label"], r["new_label"] or item["label"])
        print(f"  moved report {item['id']}, read back")
    left = len(planned) - len(todo)
    print(f"moved and read back: {len(todo)}" + (f"; left by --limit: {left}" if left else "")
          + f"; ledger {rel(ledger.path)}")


def pending_moves(rows):
    """The ledger's moves not undone yet, in order. A move Salesforce refused (HTTP 4xx) never moved;
    one it took (or whose outcome is unknown: a row a crash left "sending") is undone whether its
    read-back passed or not. An undo
    row with status ok cancels the latest move of its id before it."""
    pending = []
    for r in rows:
        if r["action"] == "move" and not r["http"].startswith("4"):
            pending.append(r)
        elif r["action"] == "undo" and r["status"] == "ok":
            for n in range(len(pending) - 1, -1, -1):
                if pending[n]["id"] == r["id"]:
                    pending.pop(n)
                    break
    return pending


def do_undo(org, args, folder):
    mine = os.path.join(folder, "ledger.csv")
    path = args.ledger or mine
    if not os.path.isfile(path):
        raise Refused(f"--ledger: there is no file {rel(path)}")
    if os.path.realpath(path) != os.path.realpath(mine):
        raise Refused(f"--ledger {rel(path)} is not {rel(mine)}: undo records what it undoes in the ledger it "
                      "reads - pass --dir with that ledger's folder")
    todo = list(reversed(pending_moves(Ledger(path, LEDGER_COLS).read())))
    todo = todo[:args.limit] if args.limit else todo
    if not todo:
        print(f"nothing to undo: every move in {rel(path)} is undone already")
        return
    bad = [m["id"] for m in todo if m["kind"] != "report"]
    if bad:
        raise Refused(f"the ledger has dashboard moves ({', '.join(bad)}): {BY_HAND}")
    bad = [m["id"] for m in todo if not ID18.fullmatch(m["id"]) or not ID18.fullmatch(m["from_folder_id"])]
    if bad:
        raise Refused(f"the ledger's move rows of {', '.join(bad)} have no plain id or from_folder_id - fix the ledger")
    now = by_id(org, "report", sorted({m["id"] for m in todo}))
    names = folder_names(org, [m["from_folder_id"] for m in todo])
    gone = sorted({m["from_folder_id"] for m in todo} - set(names))
    if gone:
        raise Refused(f"no folder has the id {', '.join(gone)} any more - nothing was written")
    for m in todo:
        name = m["old_label"] if m["new_label"] and m["new_label"] != m["old_label"] else ""
        item = now[m["id"]]
        print(f'  undo: report {m["id"]} "{item["label"]}" in "{item["folder"]}" back to '
              f'"{names[m["from_folder_id"]]}" ({m["from_folder_id"]})'
              + (f' as "{name}"' if name else ", label kept"))
    if not args.apply:
        print(f"dry run: nothing was written ({len(todo)} to undo; --apply --vpn-off writes, with Ryan's go)")
        return
    ledger = open_ledger(folder)
    for m in todo:
        name = m["old_label"] if m["new_label"] and m["new_label"] != m["old_label"] else ""
        row = {"action": "undo", "kind": "report", "id": m["id"], "from_folder_id": m["to_folder_id"],
               "to_folder_id": m["from_folder_id"], "old_label": m["new_label"], "new_label": name}
        patch_report(org, ledger, row, m["from_folder_id"], name, name or None)
        print(f"  put back report {m['id']}, read back")
    print(f"undone and read back: {len(todo)}; ledger {rel(ledger.path)}")


def main(argv=None, org=None):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--org", default="glow", help="the Salesforce CLI alias (default: glow)")
    common.add_argument("--dir", default=DEFAULT_DIR, help="the folder for ledger.csv (default: data/sf_report_folders)")
    add_vpn_flag(common)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 allow_abbrev=False)
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("list", parents=[common], allow_abbrev=False, help="read-only: a folder's items as CSV")
    p.add_argument("--folder", action="append", required=True, help="a folder name, exactly (repeatable)")
    p.add_argument("--kind", choices=sorted(FOLDER_TYPE), help="only reports or only dashboards")
    p = sub.add_parser("copy", parents=[common], allow_abbrev=False, help="clone an item into Decommissioned")
    p.add_argument("--kind", choices=sorted(FOLDER_TYPE), required=True)
    p.add_argument("--id", required=True, help="the report's or dashboard's 18-character id")
    p.add_argument("--tag", required=True, help='the ticket or reason, in the copy\'s description (e.g. "#72")')
    p.add_argument("--apply", action="store_true", help="write to Salesforce (needs Ryan's go)")
    p = sub.add_parser("move", parents=[common], allow_abbrev=False, help="move (and relabel) reports by a plan")
    p.add_argument("--plan", required=True, help="CSV with the columns kind,id,to_folder,new_label")
    p.add_argument("--apply", action="store_true", help="write to Salesforce (needs Ryan's go)")
    p.add_argument("--limit", type=positive, help="move at most N reports")
    p = sub.add_parser("undo", parents=[common], allow_abbrev=False, help="put the ledger's moves back, last first")
    p.add_argument("--ledger", help="the ledger (default and only: ledger.csv in --dir)")
    p.add_argument("--apply", action="store_true", help="write to Salesforce (needs Ryan's go)")
    p.add_argument("--limit", type=positive, help="undo at most the last N moves")
    args = ap.parse_args(argv)
    try:
        require_vpn_off(args)
        if args.command == "list":
            do_list(org or Org(args.org), args)
        else:
            folder = private_folder(args.dir, repo=REPO)
            run = {"copy": do_copy, "move": do_move, "undo": do_undo}[args.command]
            run(org or Org(args.org), args, folder)
    except Refused as stop:
        sys.exit(str(stop))
    return 0


if __name__ == "__main__":
    sys.exit(main())
