"""
What more than one test file (test/*_test.py) uses. Importing it puts the repository root and
tools/ on sys.path, so a test file imports it before any tool.

  - REPO and read();
  - FakeForm, an in-memory Jotform form for sync_attendance_form.main();
  - the fixtures other TestCases borrow: SameNameFixture (the fake Africa form with two clubs
    named "Stars") and ClubGuardFixture (that form with the club guard), AutoSyncFixture
    (auto_sync.Run.region over a fabricated dry run), FormStatusFixture (rule edits) and
    RestoreConditionsFixture (restore_conditions.main() on a snapshot);
  - apps_script_same_name() (the Apps Script side of the same-name rule, run in Node);
  - the served-page builders (served_store, served_modules_and_store, served_rules_and_rosters),
    the link and layout helpers (link_form, rendered, create_at, move_all) and name_store.
"""
import copy
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import auto_sync  # noqa: E402
import restore_conditions  # noqa: E402
import sync_attendance_form as sync  # noqa: E402
from glow import links  # noqa: E402
from glow import sync as glow_sync  # noqa: E402
from glow.text import md5  # noqa: E402


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def apps_script_same_name(rows, pairs=(), probes=()):
    """What appsscript/ makes of a Roster, run in Node exactly as the JS tests run
    it (test/load_gs.js; no Google API): {"sep": Config.gs SF_NAME_SEP, "shared":
    the sorted names of RosterOps.gs sharedClubNames_(rows), "names":
    [sfClubName_(club, partner, shared) for each (partner, club) of `pairs`],
    "held": [True when newClubHoldReasons_ holds a new club (partner, club) of
    `probes` for its name (kind samename)]}. rows: dicts with partner, club,
    full_name, status, region - Roster rows as loadRoster_ hands them over. The
    probe's girls are on nobody's roster, so no other hold reason can fire.
    None when Node is not installed (make check runs the JS tests first, so
    there it always is)."""
    import shutil
    import subprocess
    if not shutil.which("node"):
        return None
    script = """
const gs = require(process.argv[1])(['SF_NAME_SEP', 'sharedClubNames_', 'sfClubName_', 'newClubHoldReasons_']);
const inp = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const shared = gs.sharedClubNames_(inp.rows);
process.stdout.write(JSON.stringify({
  sep: gs.SF_NAME_SEP,
  shared: Object.keys(shared).sort(),
  names: inp.pairs.map(p => gs.sfClubName_(p[1], p[0], shared)),
  held: inp.probes.map(p => gs.newClubHoldReasons_(
      { partner: p[0], club: p[1], names: ['Probe Girlone', 'Probe Girltwo'], typedPartner: false },
      inp.rows, []).some(r => r.kind === 'samename')),
}));"""
    done = subprocess.run(["node", "-e", script, os.path.join(REPO, "test", "load_gs.js")],
                          input=json.dumps({"rows": rows, "pairs": list(pairs), "probes": list(probes)}),
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


class AutoSyncFixture:
    """auto_sync.Run.region over a fabricated dry run. AutoSyncPlan inherits it; other TestCases
    borrow run_region (AutoSyncFixture.run_region(self, ...))."""

    def run_region(self, text, apply=False, summary=None, region_check=None, status="ENABLED", **band):
        """auto_sync.Run.region("Africa") over a fabricated dry run; with apply, every
        later step (backup, apply, verify) answers ok and a clean form_status report -
        or one whose region check says `region_check`. status: what the form's status
        read answers (an exception: the read raised, after its retries); band: the
        runner's --max-* overrides."""
        import tempfile
        import types
        from unittest import mock
        clean = {"error_conditions": 0, "salesforce": True, "rule_problems": [], "languages": ["a"] * 12,
                 "region_check": {"missing_from_form": [], "not_in_roster": [], "rosters_out_of_date": [],
                                  **(region_check or {})}}

        def status_(form):
            if isinstance(status, Exception):
                raise status
            return status
        with tempfile.TemporaryDirectory() as out:
            args = types.SimpleNamespace(apply=apply, out=out, max_creates=5, max_updates=20,
                                         trigger="test", run_url="", **band)
            run = auto_sync.Run(args)
            run.synced = []

            def sync_(csv_path, region, form, apply, summary_path=None):
                run.synced.append(apply)
                if summary is not None and summary_path:
                    with open(summary_path, "w", encoding="utf-8") as f:
                        json.dump(summary, f)
                return types.SimpleNamespace(returncode=0, stdout=text, stderr="")

            with mock.patch.object(run, "sync", sync_), mock.patch.object(run, "read_status", status_), \
                    mock.patch.object(run, "cmd", lambda *a, **k: types.SimpleNamespace(
                        returncode=0, stdout=json.dumps([clean]), stderr="")), \
                    mock.patch.object(run, "save_conditions", lambda form: None), \
                    mock.patch("builtins.print"):
                run.region("Africa", os.path.join(out, "roster.csv"))
        return run


class FakeForm:
    """sync_attendance_form.Jotform stand-in: one form held in memory. Reads
    answer from it; writes are recorded (label + payload) and, with apply, a
    question create answers `created` (the new question's id, or {}; a list
    answers one create each, in order)."""

    def __init__(self, questions, conditions, apply=False, created=None, status="ENABLED"):
        self.questions, self.conditions, self.apply = questions, conditions, apply
        self.created = {"qid": 600} if created is None else created
        self.status = status             # what GET /form/{id} says (the sync refuses --apply unless ENABLED)
        self.calls, self.writes = [], []

    def get(self, path):
        if path == "/questions":
            return json.loads(json.dumps(self.questions))
        if path == "/properties":
            return {"conditions": json.loads(json.dumps(self.conditions))}
        return {"count": "0", "status": self.status}

    def _write(self, method, path, payload, label):
        self.calls.append(label)
        self.writes.append((method, path, payload))
        if not self.apply:
            return None
        if (method, path) != ("POST", "/questions"):
            return {}
        return self.created.pop(0) if isinstance(self.created, list) else self.created

    def post_form(self, path, data, label):
        return self._write("POST", path, data, label)

    def put_json(self, path, payload, label):
        return self._write("PUT", path, payload, label)

    def delete(self, path, label):
        return self._write("DELETE", path, None, label)


class SameNameFixture:
    """The fake Africa form SameNameFlow runs the sync on (two partners each have a club named
    "Stars"): its Roster, qids and module options, the form in step with a roster (form, texts),
    sync_attendance_form.main() on it (run_sync, summary, partners_csv) and a conditions write
    read back (rules, shows). SameNameFlow inherits it; other TestCases borrow its parts
    (SameNameFixture.form(SameNameFixture(), ...), SameNameFixture.setUp(self)). summary() and
    shows() assert, so their self is a TestCase. Fictional names."""

    ROSTER = {("Partner One", "Alpha Club"): ["Jane Doe", "Mary Roe"],
              ("Partner One", "Stars"): ["Ann Poe", "Kay Loe"],
              ("Partner Two", "Stars"): ["Sue Moe", "Liz Noe"],
              ("Partner Two", "Beta Club"): ["Eve Hoe", "Ida Toe"]}
    QIDS = {("Partner One", "Alpha Club"): "10", ("Partner One", "Stars"): "11",
            ("Partner Two", "Stars"): "12", ("Partner Two", "Beta Club"): "13"}
    MODULES = {"1": "Core 1", "2": "Core 2|Elective - Healthy GLOW", "3": "Core 3"}
    LONG = ["Alpha Club", "Beta Club", "Stars - Partner One", "Stars - Partner Two"]
    HIDE = "HIDE partner textbox (q331: no rule shows it; clubs that share a name have their own Club picker entry)"

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        del sync.WARNINGS[:]

    def tearDown(self):
        self.tmp.cleanup()
        del sync.WARNINGS[:]

    def texts(self, roster, switched=False, long=()):
        """({qid: the text its rule tests}, {qid: partner} for the rosters the
        typed Partner box still tells apart). switched: every club whose name
        another roster on the form shares has its long entry; long: the clubs
        ((partner, club)) that have it whatever the form holds."""
        from collections import Counter
        names = Counter(club.lower() for _, club in roster)
        option_of, plain = {}, Counter()
        for partner, club in roster:
            qid = self.QIDS[(partner, club)]
            if (partner, club) in long or (switched and names[club.lower()] > 1):
                option_of[qid] = f"{club} - {partner}"
            else:
                option_of[qid] = club
                plain[club.lower()] += 1
        partner_of = {self.QIDS[(p, c)]: p for p, c in roster
                      if option_of[self.QIDS[(p, c)]] == c and plain[c.lower()] > 1}
        return option_of, partner_of

    def form(self, roster=None, switched=False, long=(), rules_switched=None, picker=True,
             box_hidden=None, partner_list=None):
        """(questions, wire conditions) of a form in step with `roster`.
        switched / long: see texts(); rules_switched: the state the RULES are in
        when it differs from the picker's (a restored backup, a half apply);
        picker=False: mentors type the club name (rules on question 5);
        box_hidden: q331's hidden flag (default: hidden once no rule shows it);
        partner_list: the options of a retired partner list left on the form (q600)."""
        roster = self.ROSTER if roster is None else roster
        # the module chain as the live forms carry it: one required single-select per step
        # (form_status.audit_module_shape pins it; docs/plans/2026-10-06-module-selection.md)
        qs = {"5": {"type": "control_textbox", "text": "Club Name", "order": "4", "hidden": "Yes"},
              "331": {"type": "control_textbox", "text": "Partner", "order": "7", "name": "partner"},
              "94": {"type": "control_dropdown", "text": "GLOW Club Year", "options": "1|2|3", "order": "9",
                     "required": "Yes"}}
        for n, (year, mq) in enumerate(sync.MODULES.items()):
            # in step: the calcValues the sync writes (glow.sync.MODULE_CALC_VALUES)
            qs[mq] = {"type": "control_dropdown", "text": "Module", "options": self.MODULES[year],
                      "order": str(10 + n), "required": "Yes",
                      "calcValues": glow_sync.module_calc_values(self.MODULES[year].split("|"))}
        for n, wq in enumerate(sync.WEEKS.values()):
            qs[wq] = {"type": "control_dropdown", "text": "Session", "order": str(13 + n), "required": "Yes"}
        for q in (sync.CONTACT_IDS, sync.MODULE_ID, sync.WEEK_ID, sync.YEAR_ID):
            qs[q] = {"type": "control_textbox", "text": "bridge", "order": "30"}
        for (partner, club), names in roster.items():
            qid = self.QIDS[(partner, club)]
            # in step: the required flag the sync writes (glow.sync.ROSTERS_REQUIRED)
            qs[qid] = {"type": "control_checkbox", "text": club, "options": "|".join(names),
                       "order": str(40 + int(qid)), "hidden": "Yes", "required": glow_sync.roster_required()}
        option_of, partner_of = self.texts(roster, switched, long)
        if picker:
            qs["500"] = dict(sync.PICKER_PROPS, type="control_dropdown", name=sync.PICKER_NAME, order="3",
                             options="|".join(sorted(set(option_of.values()), key=str.lower)))
        else:
            qs["5"]["hidden"] = "No"
        if partner_list is not None:
            qs["600"] = dict(sync.PARTNER_PICKER_PROPS, type="control_dropdown",
                             name=sync.PARTNER_PICKER_NAME, order="7", options=partner_list)
        if picker and not partner_of:
            qs["331"]["hidden"] = "Yes"
        if rules_switched is not None:
            option_of, partner_of = self.texts(roster, rules_switched, long)
        modules = {y: o.split("|") for y, o in self.MODULES.items()}
        conds = sync.build_conditions(option_of, partner_of, modules, picker="500" if picker else None)
        if box_hidden is not None:
            qs["331"]["hidden"] = box_hidden
        wire = [dict(c, terms=json.dumps(c["terms"]), action=json.dumps(c["action"])) for c in conds]
        return qs, wire

    def run_sync(self, fake, *extra, roster=None, regions=None, inactive=None, region="Africa",
                 removed=None, partners=None):
        """(exit code, stdout) of main() on `fake` with a Roster export holding
        `roster` (active; region Africa unless `regions` says otherwise for a
        club) and `inactive` ({(partner, club): [names]}, rows of another status,
        with the removed_date `removed` gives the club, else none); partners:
        {partner: jotform cell} - a Partners export listing every partner of the
        Roster rows written, passed as --partners."""
        import contextlib
        import csv
        import io
        from unittest import mock
        roster = self.ROSTER if roster is None else roster
        path = os.path.join(self.tmp.name, "roster.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["girl_id", "partner", "club", "full_name", "status", "region", "removed_date"])
            for status, clubs in (("active", roster), ("inactive", inactive or {})):
                for (partner, club), names in clubs.items():
                    for n, name in enumerate(names):
                        w.writerow([f"DEMOCLUB-SAMPLE-{n:03d}", partner, club, name, status,
                                    (regions or {}).get((partner, club), "Africa"),
                                    (removed or {}).get((partner, club), "") if status != "active" else ""])
        argv = ["sync_attendance_form.py", path, "--roster", "--region", region, "--form", "999",
                *extra]
        if partners is not None:
            everyone = {p for p, _ in list(roster) + list(inactive or {})} | set(partners)
            argv += ["--partners", self.partners_csv({p: partners.get(p, "") for p in everyone})]
        out = io.StringIO()
        with mock.patch.object(sync, "Jotform", lambda key, form, apply_changes: fake), \
                mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test"}), \
                mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(out):
            try:
                sync.main()
                code = 0
            except SystemExit as e:
                code = e.code
        return code, out.getvalue()

    def partners_csv(self, cells, name="partners.csv"):
        """A Partners export (glow.sync.PARTNER_COLS) with each partner's jotform cell."""
        import csv
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(glow_sync.PARTNER_COLS)
            for partner, cell in sorted(cells.items()):
                w.writerow([partner, "Africa", "", cell])
        return path

    def summary(self, fake, *extra, **kw):
        path = os.path.join(self.tmp.name, "plan.json")
        code, out = self.run_sync(fake, *extra, "--summary-json", path, **kw)
        self.assertEqual(code, 0, code)
        with open(path, encoding="utf-8") as f:
            return json.load(f), out

    @staticmethod
    def rules(payload):
        """[(rule, terms, actions)] of a conditions write."""
        return [(c, json.loads(c["terms"]), json.loads(c["action"]))
                for c in payload["properties"]["conditions"]]

    def shows(self, payload, qid):
        """The terms of the one rule that shows roster `qid`: [(field, operator, value)]."""
        found = [[(t["field"], t["operator"], t["value"]) for t in terms]
                 for _, terms, actions in self.rules(payload)
                 if any(a.get("visibility") == "Show" and a.get("field") == qid for a in actions)]
        self.assertEqual(len(found), 1, qid)
        return found[0]


class ClubGuardFixture:
    """SameNameFixture's form switched (each Stars has its own Club picker entry), with a Submit
    button (q2) below the rosters and, when the form has it, the club guard (q700). ClubGuardFlow
    inherits it; other TestCases borrow form() (ClubGuardFixture.form(ClubGuardFixture(), ...))."""

    ROSTER, QIDS, MODULES = SameNameFixture.ROSTER, SameNameFixture.QIDS, SameNameFixture.MODULES
    OPTIONS = SameNameFixture.LONG        # Alpha Club, Beta Club, Stars - Partner One, Stars - Partner Two
    CALC = "|" + "|".join(OPTIONS)
    NEW_CLUB = {("Partner One", "Gamma Club"): ["Amara Pellucidor", "Beatrice Marrowgate"]}
    texts = SameNameFixture.texts

    def setUp(self):
        SameNameFixture.setUp(self)

    def tearDown(self):
        SameNameFixture.tearDown(self)

    def run_sync(self, fake, *extra, roster=None):
        return SameNameFixture.run_sync(self, fake, *extra, roster=roster)

    def form(self, guard=True, calc=True, roster=None, switched=True):
        """(questions, wire conditions) of a form in step with `roster`; guard:
        the warning q700 and the rules it brings; calc: the picker's calcValues;
        switched=False: the form before --same-name-switch (the two Stars on one
        entry, told apart by the typed Partner box)."""
        roster = self.ROSTER if roster is None else roster
        qs, _ = SameNameFixture.form(self, roster=roster, switched=switched)
        qs["2"] = {"type": "control_button", "text": "Submit", "name": "submit2", "order": "60"}
        options = qs["500"]["options"].split("|")
        if calc:
            qs["500"]["calcValues"] = sync.picker_calc_values(options)
        if guard:
            qs["700"] = dict(sync.GUARD_PROPS, type="control_text", name=sync.GUARD_NAME, order="4")
        for q_id, q in qs.items():
            q.setdefault("qid", q_id)
        option_of, partner_of = self.texts(roster, switched)
        conds = sync.build_conditions(option_of, partner_of, {y: o.split("|") for y, o in self.MODULES.items()},
                                      picker="500", picker_options=options, guard="700" if guard else None,
                                      submit="2" if guard else None)
        return qs, [dict(c, terms=json.dumps(c["terms"]), action=json.dumps(c["action"])) for c in conds]


def served_store(qs, extra=None):
    """A translation store as the forms hold one: an exact base/en entry (key = md5 of
    the text) for every roster option and module, a UI string translated in Spanish;
    extra: {key: (base text, en text)} added (a stale spelling, say)."""
    texts = [o for q in qs.values() if q.get("type") in ("control_checkbox", "control_dropdown")
             for o in (q.get("options") or "").split("|") if o] + ["Club Name"]
    store = {"base": {md5(t): t for t in texts}, "en": {md5(t): t for t in texts},
             "es": {md5("Club Name"): "Nombre del club"}}
    for k, (b, e) in (extra or {}).items():
        store["base"][k], store["en"][k] = b, e
    return store


def served_modules_and_store(qs, store=None, clear="disable"):
    """The module dropdowns' <select>s as Jotform serves a single-select (read from the U.S
    page 2026-10-02: a "Please Select" placeholder, then each option with a data-calcvalue
    when the question carries calcValues, the leading slot being the placeholder's), the
    runtime's clearFieldOnHide (JotForm.clearFieldOnHide="…", the template page 2026-10-06;
    None: no such line) and the store the page embeds (window.allTranslations,
    FormTranslation.init)."""
    import html as html_mod
    parts = [] if clear is None else [f'<script>JotForm.clearFieldOnHide="{clear}";</script>']
    for year, q in sync.MODULES.items():
        if q not in qs:
            continue
        options = [o for o in (qs[q].get("options") or "").split("|") if o]
        calc = (qs[q].get("calcValues") or "").split("|")
        parts.append(f'<select class="form-dropdown validate[required]" id="input_{q}" name="q{q}_module{year}" '
                     'data-component="dropdown"><option value="">Please Select</option>')
        for i, o in enumerate(options):
            cv = calc[i + 1] if i + 1 < len(calc) and calc[i + 1] else None
            attr = f' data-calcvalue="{html_mod.escape(cv)}"' if cv else ""
            parts.append(f'<option{attr} value="{html_mod.escape(o)}">{html_mod.escape(o)}</option>')
        parts.append("</select>")
    store = served_store(qs) if store is None else store
    parts.append('<script>window.allTranslations = {"acceptLanguage":null,"languages":{"English (US)":"en",'
                 '"Español":"es"},"translations":' + json.dumps(store) + "};\n"
                 'FormTranslation.init({"options":"English (US)|Español","primaryLanguage":"en","version":"2"});'
                 "</script>")
    return "\n".join(parts)


def served_rules_and_rosters(qs, wire, required=True, build="9e75d6f1d83", operands=None, store=None):
    """The parts of a public page that form_status --rendered reads besides the
    picker's <select>, shaped as Jotform serves them (read from the U.S page
    2026-10-01): the runtime script, every roster's boxes (validate[required]
    and required="" on each when `required`), JotForm.setConditions with the
    rules parsed, JotForm.setCalculations with each calculation's action and its
    conditionId; and (2026-10-02) the module dropdowns and the embedded store
    (served_modules_and_store; store: the one the page embeds, default a clean
    served_store). operands: replace question 18's operands as served (Jotform
    dropping one). Fictional names, as the fixtures'."""
    import html as html_mod
    parts = [f'<script src="https://cdn.jotfor.ms/s/static/{build}/static/jotform.forms.js"></script>',
             served_modules_and_store(qs, store)]
    for qid, q in sorted(qs.items(), key=lambda kv: int(kv[0])):
        if q.get("type") != "control_checkbox":
            continue
        cls = "form-checkbox validate[required]" if required else "form-checkbox"
        attr = ' required=""' if required else ""
        for i, name in enumerate(o for o in q.get("options", "").split("|") if o):
            parts.append(f'<input type="checkbox" class="{cls}" id="input_{qid}_{i}" name="q{qid}_club[]" '
                         f'value="{html_mod.escape(name)}"{attr} />')
    rules = [dict(c, terms=json.loads(c["terms"]) if isinstance(c["terms"], str) else c["terms"],
                  action=json.loads(c["action"]) if isinstance(c["action"], str) else c["action"])
             for c in wire]
    calcs = [dict(a, conditionId=c["id"], conditionTrue=False) for c in rules if c["type"] == "calculation"
             for a in c["action"]]
    if operands is not None:
        calcs = [dict(a, operands=operands) if a["resultField"] == sync.CONTACT_IDS else a for a in calcs]
    parts.append("<script>JotForm.setCalculations(" + json.dumps(calcs) + ");")
    parts.append("JotForm.setConditions(" + json.dumps(rules) + ");</script>")
    return "\n".join(parts)


class FormStatusFixture:
    """edit(): a wire conditions list with some of its rules changed. FormStatusAudit inherits
    it; other TestCases call FormStatusFixture.edit."""

    @staticmethod
    def edit(wire, pred, **change):
        """wire with change(rule) applied to the rules pred(rule) selects."""
        return [dict(c, **{k: f(c) for k, f in change.items()}) if pred(c) else c for c in wire]


class RestoreConditionsFixture:
    """restore_conditions.main() against a fake Jotform and a snapshot in a temporary backups/
    folder. RestoreConditionsGuard inherits it; other TestCases borrow run_restore
    (RestoreConditionsFixture.run_restore(self, ...)). After a run, self.restore_calls holds
    the fake's calls in order and self.restore_files backups/999/ ({name: content})."""

    def run_restore(self, snapshot, questions, *extra):
        import contextlib
        import io
        import tempfile
        from unittest import mock
        puts, calls = [], []
        self.restore_calls = calls

        class Fake:
            def __init__(self, key, apply=False):
                pass

            def get(self, path):
                calls.append(("GET", path))
                if path.endswith("/questions"):
                    return copy.deepcopy(questions)
                return {"conditions": puts[-1] if puts else [{"id": "live"}]}

            def put_json(self, path, payload, label):
                calls.append(("PUT", path))
                puts.append(payload["properties"]["conditions"])

        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "backups", "999"))
            with open(os.path.join(tmp, "backups", "999", "properties-latest.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"conditions": snapshot}, f)
            with mock.patch.object(restore_conditions, "REPO", tmp), \
                    mock.patch.object(restore_conditions.backup, "REPO", tmp), \
                    mock.patch.object(restore_conditions, "Client", Fake), \
                    mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}), \
                    mock.patch.object(sys, "argv", ["restore_conditions.py", "--form", "999", *extra]), \
                    contextlib.redirect_stdout(out):
                try:
                    restore_conditions.main()
                    code = 0
                except SystemExit as e:
                    code = e.code
            folder = os.path.join(tmp, "backups", "999")
            self.restore_files = {}
            for name in sorted(os.listdir(folder)):
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    self.restore_files[name] = json.load(f)
        return code, out.getvalue(), puts


# ------------------------------------------------ the links above Submit
def link_form(problem=True, roster=False, stray=None):
    """A fake attendance form laid out like the live ones (read 2026-09-28): the
    top fields, a roster, the link elements, Submit, the hidden bridge fields,
    and a roster the sync created after Submit. Fictional clubs and girls."""
    rows = [("1", "control_head", "heading", {}),
            ("444", "control_dropdown", sync.PICKER_NAME,
             {**sync.PICKER_PROPS, "options": "Moonrise Club|Sunrise Club"}),
            (sync.CLUB_NAME, "control_textbox", "clubName", {"hidden": "Yes"}),
            (sync.PARTNER, "control_textbox", "partner", {"text": "Partner"}),
            (sync.YEAR, "control_dropdown", "module94", {"options": "1|2|3"}),
            ("14", "control_dropdown", "module1", {"options": "Core 1"}),
            ("92", "control_dropdown", "module2", {"hidden": "Yes", "options": "Core 2"}),
            ("93", "control_dropdown", "module3", {"hidden": "Yes", "options": "Core 3"}),
            ("350", "control_checkbox", "SunriseClub",
             {"hidden": "Yes", "text": "Sunrise Club", "options": "Girl One|Girl Two"})]
    if roster:
        rows.append(("460", "control_text", links.ROSTER.name,
                     {"text": links.element_html(links.ROSTER.sentence, links.ROSTER_FORM_URL)}))
    if problem:
        rows.append(("443", "control_text", links.PROBLEM.name,
                     {"text": links.element_html(links.PROBLEM.sentence, links.PROBLEM_FORM_URL)}))
    if stray:
        rows.append(stray)
    rows += [("2", "control_button", "submit2", {"text": "Submit"}),
             ("103", "control_head", "belowAre", {"hidden": "Yes"}),
             (sync.CONTACT_IDS, "control_textarea", "contact_ids", {"hidden": "Yes"}),
             ("400", "control_checkbox", "MoonriseClub",
              {"hidden": "Yes", "text": "Moonrise Club", "options": "Girl Three"})]
    return {qid: {"qid": qid, "type": t, "name": n, "order": str(i), **extra}
            for i, (qid, t, n, extra) in enumerate(rows, 1)}


def rendered(questions):
    """Names in render order: by order, equal orders in creation (qid) order."""
    return [q["name"] for q in sorted(questions.values(),
                                      key=lambda q: (links.order_of(q), int(q["qid"])))]


def create_at(questions, fields, behaviour):
    """(form, new qid) after POST /questions with question[order], under one of
    the two behaviours Jotform might show: "insert" - the question takes the
    order and the block from there down to the first gap moves down one (seen
    on the template 2026-09-01 and Africa 2026-09-12) - or "tie" - it just
    takes the order (equal orders render in creation order, the newest last)."""
    qs = copy.deepcopy(questions)
    order = int(fields["order"])
    if behaviour == "insert":
        used, end = {links.order_of(q) for q in qs.values()}, order
        while end in used:
            end += 1
        for q in qs.values():
            if order <= links.order_of(q) < end:
                q["order"] = str(links.order_of(q) + 1)
    qid = str(max(int(k) for k in qs) + 1)
    qs[qid] = {"qid": qid, **fields}
    return qs, qid


def move_all(questions, moves):
    """What fix_roster_order's writes (one question[order] each) do to a form."""
    qs = copy.deepcopy(questions)
    for qid, order in moves:
        qs[qid]["order"] = str(order)
    return qs


def name_store(entries, others=None, pad=0):
    """A translation store as Jotform holds one: [(base text, en text or None)] keyed by
    the md5 of the base text, other languages as {lang: {base text: translation}}, and
    `pad` UI strings ("Label 0001", ...) exact in base and en. Fictional names only."""
    store = {"base": {}, "en": {}}
    for i in range(pad):
        text = f"Label {i:04d}"
        store["base"][md5(text)] = store["en"][md5(text)] = text
    for b, e in entries:
        store["base"][md5(b)] = b
        if e is not None:
            store["en"][md5(b)] = e
    for lang, d in (others or {}).items():
        store[lang] = {md5(b): t for b, t in d.items()}
    return store
