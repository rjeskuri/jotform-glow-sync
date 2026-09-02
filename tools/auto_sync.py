#!/usr/bin/env python3
"""
Keep the regional Jotform attendance forms in step with the Roster tab, unattended.

Runs from GitHub Actions (.github/workflows/auto-sync.yml) when the sheet's
Apps Script reports a roster change (Dispatch.gs), on a daily schedule, or
by hand:

    python3 tools/auto_sync.py                     # dry run: export, plan, report
    python3 tools/auto_sync.py --apply             # also write, within the safety bands
    python3 tools/auto_sync.py --region Asia --roster data/roster_<date>.csv

One run, per region: export the Roster tab -> guards -> dry-run the existing
sync -> if it plans changes and they are within the bands -> back up the
form -> apply -> verify with form_status.py. With --synclog (the workflow
always passes it; local runs write nothing to the sheet by default) every
region's outcome is appended to the sheet's SyncLog tab; the console and
data/auto_sync/<stamp>.log are redacted (girls' names never appear). Exit
0 = every region in sync or applied cleanly; 2 = something needs a human
(ATTENTION.md says what, and an unverified apply counts); 1 = a step failed.

It never passes --prune, never deletes a question, and refuses to apply when
one region would create more than --max-creates clubs or update more than
--max-updates rosters at once, or when the export looks truncated.
"""
import argparse
import csv
import datetime
import json
import os
import re
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
sys.path.insert(0, REPO)
import sheets_client as sc  # noqa: E402  (Google libraries are imported lazily inside it)
from glow import forms as glow_forms  # noqa: E402

# The live regional forms (one source: glow/forms.py, parity-tested against
# appsscript/Config.gs by test/python_test.py).
REGIONAL_FORMS = glow_forms.REGIONALS
ROSTER_TAB = "Roster"
SYNC_LOG_TAB = "SyncLog"
# keep in step with SYNC_LOG_COLS in appsscript/Roster.gs
SYNC_LOG_COLS = ["when", "trigger", "region", "mode", "creates", "updates",
                 "rules", "result", "detail", "run_url"]
MIN_LANGUAGES = 12
DEFAULT_OUT = os.path.join(REPO, "data", "auto_sync")

# The sync tool's plan lines (sync_attendance_form.py; test/python_test.py
# checks these formats still exist there).
CREATE_RX = re.compile(r"^  - CREATE roster '(?P<club>.+)' \((?P<girls>\d+) girls\)$")
UPDATE_RX = re.compile(r"^  - UPDATE roster '(?P<club>.+)' \(q(?P<qid>\d+), (?P<girls>\d+) girls\)$")
DELETE_RX = re.compile(r"^  - DELETE roster '(?P<club>.+)' \(q(?P<qid>\d+), belongs to (?P<region>.+)\)$")
REPLACE_RX = re.compile(r"^  - REPLACE conditions \((?P<rules>\d+) rules")
PICKER_RX = re.compile(r"^  - (?P<op>CREATE|UPDATE) club picker \((?P<clubs>\d+) clubs(?::[^)]*)?\)$")
ROSTER_RX = re.compile(r"^Roster: (?P<clubs>\d+) active clubs.*\((?P<girls>\d+) girls\); "
                       r"(?P<all>\d+) clubs overall")
NOT_IN_EXPORT = "is on the form but not in the sheet export"
NO_SHARED_NAMES = "shares NO names with the current one"


def key(s):
    return " ".join(str(s or "").split()).lower()


# ------------------------------------------------------------ pure functions
def parse_plan(text):
    """The sync tool's dry-run output -> what it plans to do."""
    plan = {"creates": [], "updates": [], "deletes": [], "picker": [], "rules": None,
            "warnings": [], "roster_clubs": None, "roster_girls": None}
    for line in text.splitlines():
        m = PICKER_RX.match(line)
        if m:
            plan["picker"].append({"op": m["op"], "clubs": int(m["clubs"])})
            continue
        m = CREATE_RX.match(line)
        if m:
            plan["creates"].append({"club": m["club"], "girls": int(m["girls"])})
            continue
        m = UPDATE_RX.match(line)
        if m:
            plan["updates"].append({"qid": m["qid"], "club": m["club"], "girls": int(m["girls"])})
            continue
        m = DELETE_RX.match(line)
        if m:
            plan["deletes"].append({"qid": m["qid"], "club": m["club"], "region": m["region"]})
            continue
        m = REPLACE_RX.match(line)
        if m:
            plan["rules"] = int(m["rules"])
            continue
        m = ROSTER_RX.match(line)
        if m:
            plan["roster_clubs"], plan["roster_girls"] = int(m["clubs"]), int(m["girls"])
            continue
        if line.startswith(("  ! ", "  ? ")):
            plan["warnings"].append(line.strip())
    return plan


def plan_from_summary(summary):
    """The same shape, from the sync tool's --summary-json file."""
    return {"creates": [{"club": c["club"], "girls": c["girls"]} for c in summary.get("creates", [])],
            "updates": [{"qid": u["qid"], "club": u["club"], "girls": u["girls"]}
                        for u in summary.get("updates", [])],
            "deletes": [{"qid": d["qid"], "club": d["club"], "region": d["region"]}
                        for d in summary.get("deletes", [])],
            "picker": [{"op": m["op"], "clubs": int(m["clubs"])}
                       for m in (PICKER_RX.match("  - " + c) for c in summary.get("calls", [])) if m],
            "rules": summary.get("rules"),
            "warnings": [w.strip() for w in summary.get("warnings", [])],
            "roster_clubs": summary.get("roster_clubs"),
            "roster_girls": summary.get("roster_girls")}


def changes(plan):
    """Roster creates/updates/deletes plus a Club-picker option update (never a create:
    the runner does not pass --club-picker, so a CREATE here means someone else did)."""
    return (len(plan["creates"]) + len(plan["updates"]) + len(plan["deletes"])
            + len(plan.get("picker", [])))


def check_bands(plan, max_creates=5, max_updates=20):
    """Reasons NOT to apply this plan unattended (empty = within the bands)."""
    reasons = []
    if plan["deletes"]:
        reasons.append(f"would delete {len(plan['deletes'])} roster question(s) - never done "
                       "automatically (that is what --prune is for, on a fresh clone only)")
    if len(plan["creates"]) > max_creates:
        reasons.append(f"would create {len(plan['creates'])} clubs at once (band: {max_creates}) - "
                       "a real wave of new clubs, or a bad export? apply by hand after checking")
    if len(plan["updates"]) > max_updates:
        reasons.append(f"would update {len(plan['updates'])} rosters at once (band: {max_updates}) - "
                       "apply by hand after checking the export")
    if any(NO_SHARED_NAMES in w for w in plan["warnings"]):
        reasons.append("a roster would be replaced by one that shares no names with the current "
                       "one - confirm it is the same club before applying")
    stale = sum(1 for w in plan["warnings"] if NOT_IN_EXPORT in w)
    n = plan["roster_clubs"] or 0
    if stale > max(5, n // 10):
        reasons.append(f"{stale} clubs are on the form but missing from the export (region has "
                       f"{n} clubs in the export) - a truncated export? nothing applied")
    return reasons


def blank_region_rows(rows):
    """Active girls the sync would silently drop: (partner, club, count), sorted."""
    by = {}
    for r in rows:
        if key(r.get("status")) != "active" or (r.get("region") or "").strip():
            continue
        k = (" ".join((r.get("partner") or "").split()), " ".join((r.get("club") or "").split()))
        by[k] = by.get(k, 0) + 1
    return sorted((p, c, n) for (p, c), n in by.items())


def verify_report(rep, min_languages=MIN_LANGUAGES):
    """form_status.py --json for one form -> (problems, notes)."""
    problems, notes = [], []
    if rep.get("error_conditions"):
        problems.append(f"{rep['error_conditions']} condition(s) flagged as error")
    if not rep.get("salesforce"):
        problems.append("Salesforce integration missing")
    rp = rep.get("rule_problems") or []
    if rp:
        problems.append(f"{len(rp)} rule problem(s): " + "; ".join(str(p) for p in rp[:3]))
    langs = rep.get("languages") or []
    if len(langs) < min_languages:
        problems.append(f"only {len(langs)} language(s) offered (expected at least {min_languages})")
    rc = rep.get("region_check")
    if rc is None:
        problems.append("no region check in the report (region spelling in the Roster export?)")
    else:
        if rc.get("missing_from_form"):
            problems.append(f"{len(rc['missing_from_form'])} club(s) still missing from the form: "
                            + ", ".join(rc["missing_from_form"][:5]))
        if rc.get("rosters_out_of_date"):
            problems.append(f"{len(rc['rosters_out_of_date'])} roster(s) still differ from the sheet: "
                            + ", ".join(str(x[0]) for x in rc["rosters_out_of_date"][:5]))
        if rc.get("not_in_roster"):
            notes.append(f"{len(rc['not_in_roster'])} club(s) on the form but not in the roster "
                         "(kept, as always): " + ", ".join(rc["not_in_roster"][:5]))
    if rep.get("duplicate_club_questions"):
        notes.append("duplicate club questions: " + ", ".join(rep["duplicate_club_questions"][:5]))
    return problems, notes


def name_regex(names):
    """Compiled matcher for the listed full names, or None.

    Only names of two or more words are matched (a one-word roster entry like a
    bare first name would garble club names and ordinary words), whole-word,
    longest first, case-insensitively."""
    names = sorted({" ".join(n.split()) for n in names if n and len(n.split()) >= 2},
                   key=len, reverse=True)
    if not names:
        return None
    return re.compile(r"\b(?:" + "|".join(re.escape(n) for n in names) + r")\b", re.IGNORECASE)


def redact(text, names):
    """Replace every listed full name with [girl]."""
    rx = name_regex(names)
    return rx.sub("[girl]", text) if rx else text


def slug(region):
    return re.sub(r"[^A-Za-z]", "", region)


# ------------------------------------------------------------------- runner
class Run:
    def __init__(self, args):
        self.args = args
        self.lines = []
        self.attention = []       # (title, detail)
        self.results = []         # SyncLog rows
        self.failed = False
        now = datetime.datetime.now()
        self.stamp = now.strftime("%Y-%m-%dT%H%M%S")
        self.when = now.strftime("%Y-%m-%d %H:%M:%S")
        self.mode = "apply" if args.apply else "dry-run"
        self.names = []
        self._rx = None          # set once the roster is loaded; from then on every
                                 # logged line is redacted BEFORE it reaches stdout
                                 # (the Actions job log keeps raw step output for 90 days)

    def set_names(self, names):
        self.names = names
        self._rx = name_regex(names)

    def log(self, msg=""):
        if self._rx is not None:
            msg = self._rx.sub("[girl]", msg)
        print(msg, flush=True)
        self.lines.append(msg)

    def cmd(self, argv, label):
        r = subprocess.run(argv, capture_output=True, text=True, cwd=REPO, env=os.environ.copy())
        for line in (r.stdout or "").splitlines():
            self.log("    " + line)
        if r.returncode != 0:
            self.log(f"  ! {label} exited {r.returncode}: " + (r.stderr or "").strip()[-300:])
        return r

    def sync(self, csv_path, region, form, apply, summary_path=None):
        argv = [sys.executable, os.path.join(REPO, "sync_attendance_form.py"), csv_path,
                "--roster", "--region", region, "--form", form]
        if apply:
            argv.append("--apply")
        if summary_path:
            argv += ["--summary-json", summary_path]
        return self.cmd(argv, f"sync {region}" + (" --apply" if apply else ""))

    def with_retry(self, fn, label, tries=4, delay=5):
        for i in range(tries):
            try:
                return fn()
            except Exception as err:                      # noqa: BLE001 - network errors of any shape
                if i == tries - 1:
                    raise
                self.log(f"  ! {label}: {err.__class__.__name__}: {str(err)[:200]} - retry in {delay}s")
                time.sleep(delay)
                delay *= 2

    def result(self, region, plan, result, detail):
        self.results.append([self.when, self.args.trigger, region, self.mode,
                             len(plan["creates"]) if plan else "", len(plan["updates"]) if plan else "",
                             plan["rules"] if plan and plan["rules"] is not None else "",
                             result, detail[:500], self.args.run_url or ""])
        self.log(f"  => {region}: {result}" + (f" - {detail}" if detail else ""))

    # ---- steps
    def export_roster(self, svc):
        values = self.with_retry(lambda: sc.read_tab(svc, ROSTER_TAB), "export Roster")
        path = os.path.join(self.args.out, f"roster_{self.stamp}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(values)
        self.log(f"Roster: exported {max(0, len(values) - 1)} rows -> {os.path.relpath(path, REPO)}")
        return path

    def region(self, region, csv_path):
        form = REGIONAL_FORMS[region]
        a = self.args
        self.log(f"\n== {region}  form {form}")
        summary_path = os.path.join(a.out, f"plan_{slug(region)}_{self.stamp}.json")
        dry = self.sync(csv_path, region, form, apply=False, summary_path=summary_path)
        if dry.returncode != 0:
            self.failed = True
            self.result(region, None, "failed", "dry run exited "
                        f"{dry.returncode}: {(dry.stderr or '').strip()[-200:]}")
            return
        plan = parse_plan(dry.stdout or "")
        if os.path.exists(summary_path):
            with open(summary_path, encoding="utf-8") as f:
                plan = plan_from_summary(json.load(f))
        n = changes(plan)
        if n == 0:
            self.result(region, plan, "in-sync", "")
            return
        summary = (f"{len(plan['creates'])} create(s), {len(plan['updates'])} update(s), "
                   f"{len(plan['deletes'])} delete(s), {len(plan['warnings'])} warning(s)")
        reasons = check_bands(plan, a.max_creates, a.max_updates)
        if reasons:
            self.attention.append((f"{region}: not applied - {summary}",
                                   "\n".join("- " + r for r in reasons) + "\n\nPlanned:\n" +
                                   "\n".join(f"- CREATE {c['club']} ({c['girls']} girls)" for c in plan["creates"]) +
                                   "\n".join(f"\n- UPDATE {u['club']} (q{u['qid']}, {u['girls']} girls)" for u in plan["updates"]) +
                                   "\n".join(f"\n- DELETE {d['club']} (q{d['qid']})" for d in plan["deletes"]) +
                                   ("\n\nWarnings:\n" + "\n".join("- " + w for w in plan["warnings"]) if plan["warnings"] else "")))
            self.result(region, plan, "attention", "; ".join(reasons))
            return
        if not a.apply:
            self.result(region, plan, "dry-run", "would apply: " + summary)
            return

        self.log(f"  backing up form {form}")
        bk = self.cmd([sys.executable, os.path.join(REPO, "backup_forms.py"), "--form", form], "backup")
        if bk.returncode != 0:
            self.failed = True
            self.result(region, plan, "failed", "backup failed - nothing applied")
            return
        self.save_conditions(form)
        applied = self.sync(csv_path, region, form, apply=True)
        if applied.returncode != 0:
            self.log("  ! apply failed once - retrying (a failure between the question writes and "
                     "the conditions write leaves the form half-synced; the re-run completes it)")
            applied = self.sync(csv_path, region, form, apply=True)
        if applied.returncode != 0:
            self.failed = True
            self.attention.append((f"{region}: APPLY FAILED - the form may be half-synced",
                                   f"Run by hand: python3 sync_attendance_form.py <roster.csv> --roster "
                                   f"--region '{region}' --form {form} (dry run first), or restore the "
                                   f"conditions from backups/{form}/ with restore_conditions.py.\n\n"
                                   + (applied.stderr or "").strip()[-500:]))
            self.result(region, plan, "failed", "apply exited " + str(applied.returncode))
            return
        ver = self.cmd([sys.executable, os.path.join(TOOLS, "form_status.py"), "--form", form,
                        "--roster", csv_path, "--json"], "verify")
        rep = None
        if ver.returncode == 0:
            try:
                rep = json.loads(ver.stdout)[0]
            except (ValueError, IndexError):
                rep = None
        if rep is None:
            # a live write whose check could not run must never pass silently
            self.attention.append((f"{region}: applied but NOT verified",
                                   "The write succeeded but form_status could not confirm the form "
                                   "is clean. Check by hand:\n"
                                   f"python3 tools/form_status.py --form {form} --roster <roster.csv>\n\n"
                                   + (ver.stderr or "").strip()[-300:]))
            self.result(region, plan, "applied-unverified", summary + "; verification could not run")
            return
        problems, notes = verify_report(rep)
        for note in notes:
            self.log("  note: " + note)
        if problems:
            self.attention.append((f"{region}: applied, but the form still has problems",
                                   "\n".join("- " + p for p in problems)))
            self.result(region, plan, "applied-with-problems", summary + "; " + "; ".join(problems))
        else:
            self.result(region, plan, "applied", summary + "; verified clean")

    def save_conditions(self, form):
        """A conditions-only rollback file next to the full snapshot.

        The full properties snapshot holds staff e-mail configs and the
        Salesforce integration settings, so only this file may leave the
        machine (the workflow artifact). Restore with:
        restore_conditions.py --form <id> --from conditions-<stamp>.json"""
        src = os.path.join(REPO, "backups", form, "properties-latest.json")
        try:
            with open(src, encoding="utf-8") as f:
                props = json.load(f)
            out = os.path.join(REPO, "backups", form, f"conditions-{self.stamp}.json")
            with open(out, "w", encoding="utf-8") as f:
                json.dump({"conditions": props.get("conditions", [])}, f, indent=1)
        except (OSError, ValueError) as err:
            self.log(f"  ! could not write the conditions-only copy: {err}")

    def append_synclog(self, svc):
        if not sc._has_tab(svc, SYNC_LOG_TAB) or not sc.read_tab(svc, SYNC_LOG_TAB):
            sc.write_tab(svc, SYNC_LOG_TAB, [SYNC_LOG_COLS])
        sc.append_rows(svc, SYNC_LOG_TAB, self.results)
        self.log(f"SyncLog: {len(self.results)} row(s) appended")

    def write_files(self):
        text = redact("\n".join(self.lines), self.names)
        log_path = os.path.join(self.args.out, f"{self.stamp}.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        att_path = os.path.join(self.args.out, "ATTENTION.md")
        if self.attention:
            body = [f"# Auto-sync needs a human - {self.when}", ""]
            for title, detail in self.attention:
                body += [f"## {title}", "", detail, ""]
            body += ["Log: " + os.path.relpath(log_path, REPO)]
            if self.args.run_url:
                body += ["Run: " + self.args.run_url]
            with open(att_path, "w", encoding="utf-8") as f:
                f.write(redact("\n".join(body), self.names) + "\n")
            print(f"\nATTENTION: {len(self.attention)} item(s) -> {os.path.relpath(att_path, REPO)}")
        elif os.path.exists(att_path):
            os.remove(att_path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="write to the forms (default: dry run)")
    ap.add_argument("--region", action="append", choices=sorted(REGIONAL_FORMS),
                    help="only this region (repeatable; default: all four)")
    ap.add_argument("--trigger", default="manual", help="what started this run (goes to SyncLog)")
    ap.add_argument("--roster", metavar="CSV", help="use this Roster export instead of exporting")
    ap.add_argument("--max-creates", type=int, default=5, help="per region, per run (default 5)")
    ap.add_argument("--max-updates", type=int, default=20, help="per region, per run (default 20)")
    ap.add_argument("--min-active", type=int, default=1000,
                    help="refuse an export with fewer active rows than this (default 1000)")
    ap.add_argument("--synclog", action="store_true",
                    help="append this run's outcomes to the sheet's SyncLog tab (the workflow "
                         "always passes this; without it nothing is written to the sheet)")
    ap.add_argument("--out", default=DEFAULT_OUT, help="working directory for exports and logs")
    ap.add_argument("--run-url", default=os.environ.get("AUTO_SYNC_RUN_URL", ""),
                    help="link recorded in SyncLog (Actions sets AUTO_SYNC_RUN_URL)")
    args = ap.parse_args()
    if not os.environ.get("JOTFORM_API_KEY"):
        sys.exit("Set JOTFORM_API_KEY in the environment (a dry run reads the forms too)")
    os.makedirs(args.out, exist_ok=True)

    run = Run(args)
    run.log(f"auto-sync {run.when}  trigger={args.trigger}  mode={run.mode}  "
            f"regions={', '.join(args.region or REGIONAL_FORMS)}")
    svc = None
    if args.roster:
        csv_path = args.roster
        run.log(f"Roster: using {os.path.relpath(csv_path, REPO)}")
    else:
        svc = sc.service()
        csv_path = run.export_roster(svc)

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    needed = {"partner", "club", "full_name", "status", "region"}
    if not rows or not needed <= set(rows[0]):
        sys.exit("Not a Roster export: expected the columns " + ", ".join(sorted(needed)))
    run.set_names([r["full_name"] for r in rows])
    active = [r for r in rows if key(r["status"]) == "active"]
    run.log(f"Roster: {len(rows)} rows, {len(active)} active")
    if len(active) < args.min_active:
        run.failed = True
        run.log(f"  ! only {len(active)} active rows (floor {args.min_active}) - the export looks "
                "truncated; nothing synced")
        run.write_files()
        sys.exit(1)
    blank = blank_region_rows(rows)
    if blank:
        detail = "\n".join(f"- {p} / {c}: {n} girl(s)" for p, c, n in blank)
        run.attention.append(("Active girls with no region - they reach NO attendance form",
                              "Fill in the region on the Partners tab (rows marked 'region needed'), "
                              "then GLOW -> Refresh regions from the Partners tab.\n\n" + detail))
        run.log(f"  ! {sum(n for _, _, n in blank)} active girl(s) in {len(blank)} club(s) have no region")

    for region in args.region or list(REGIONAL_FORMS):
        run.region(region, csv_path)

    if args.synclog and run.results:
        try:
            svc = svc or sc.service()
            run.with_retry(lambda: run.append_synclog(svc), "SyncLog")
        except (SystemExit, Exception) as err:            # noqa: BLE001 - sheets_client reports via sys.exit;
            # a SyncLog failure must not discard the log/ATTENTION files below
            run.attention.append(("SyncLog row could not be written",
                                  f"{err.__class__.__name__}: {str(err)[:300]}\n"
                                  "The sheet is missing this run's record; the log file below has it."))
            run.log(f"  ! could not write SyncLog: {err.__class__.__name__}: {str(err)[:200]}")
    run.write_files()
    if run.failed:
        sys.exit(1)
    if run.attention:
        sys.exit(2)


if __name__ == "__main__":
    main()
