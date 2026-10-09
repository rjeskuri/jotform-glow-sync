#!/usr/bin/env python3
"""
The glow/ library: the Jotform client's dry-run gate and call shapes (GlowClient), glow.text
against the per-script copies it replaced (GlowText), glow.forms (GlowForms) and the runtime's
names dictionary as glow/translation_lookup.py emulates it (TranslationLookup). No network;
fictional names.
"""
import json
import os
import unittest

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import name_store
from glow import translation_lookup as tl
from glow.text import md5


class GlowClient(unittest.TestCase):
    """The dry-run gate and call shapes of glow.jotform.Client (no network)."""

    def setUp(self):
        import glow.jotform as gj
        self.gj = gj
        self.spawned = []
        self.bodies = []

    def fake(self, outputs):
        """subprocess.run replacement yielding the given stdout strings in order."""
        import subprocess as sp

        def runner(argv, capture_output=True, text=True, **kw):
            self.spawned.append(argv)
            self.bodies.append(kw.get("input"))
            out = outputs[min(len(self.spawned) - 1, len(outputs) - 1)]
            return sp.CompletedProcess(argv, 0, stdout=out, stderr="")
        return runner

    def ok(self, content=None):
        return json.dumps({"responseCode": 200, "content": content if content is not None else {"x": 1}})

    def test_writes_are_recorded_and_skipped_without_apply(self):
        from unittest import mock
        c = self.gj.Client("KEY")
        with mock.patch.object(self.gj.subprocess, "run", self.fake([self.ok()])):
            self.assertIsNone(c.post_form("/form/1/questions", {"a": "b"}, "CREATE x"))
            self.assertIsNone(c.put_json("/form/1/properties", {}, "REPLACE y"))
            self.assertIsNone(c.delete("/form/1/question/2", "DELETE z"))
            self.assertEqual(c.get("/form/1/questions"), {"x": 1})
        self.assertEqual(c.calls, ["CREATE x", "REPLACE y", "DELETE z"])
        self.assertEqual(len(self.spawned), 1)          # only the GET ran

    def test_apply_runs_writes_and_still_records_them(self):
        from unittest import mock
        c = self.gj.Client("KEY", apply=True)
        with mock.patch.object(self.gj.subprocess, "run", self.fake([self.ok()])):
            self.assertEqual(c.post_form("/form/1/questions", {"a": "b"}, "CREATE x"), {"x": 1})
        self.assertEqual(c.calls, ["CREATE x"])
        argv = self.spawned[0]
        self.assertEqual(argv[:2], ["curl", "-sS"])
        self.assertIn("--data-urlencode", argv)
        self.assertIn("a=b", argv)
        self.assertEqual(argv.count("https://api.jotform.com/form/1/questions?apiKey=KEY"), 1)

    def test_url_params_and_max_time(self):
        from unittest import mock
        c = self.gj.Client("KEY", max_time=150)
        self.assertEqual(c.url("/form/1/questions", limit=1000),
                         "https://api.jotform.com/form/1/questions?apiKey=KEY&limit=1000")
        with mock.patch.object(self.gj.subprocess, "run", self.fake([self.ok()])):
            c.get("/form/1/questions", limit=1000)
        self.assertIn("--max-time", self.spawned[0])

    def test_url_params_are_encoded_once(self):
        import urllib.parse
        from unittest import mock
        c = self.gj.Client("KEY")
        flt = json.dumps({"created_at:gt": "2026-09-01 00:00:00", "created_at:lt": "2026-09-02 00:00:00"})
        url = c.url("/form/1/submissions", limit=1000, offset=0, filter=flt)
        # byte for byte what the two tools sent when they encoded the filter themselves
        self.assertEqual(url, "https://api.jotform.com/form/1/submissions?apiKey=KEY&limit=1000&offset=0&filter="
                              + urllib.parse.quote(flt, safe=""))
        self.assertNotIn("%25", url)                                     # no "%" was encoded again
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual(query["filter"], [flt])                         # one decoding gives the JSON back
        self.assertEqual(c.url("/form/1", q="a&b=c d"), "https://api.jotform.com/form/1?apiKey=KEY&q=a%26b%3Dc%20d")
        with mock.patch.object(self.gj.subprocess, "run", self.fake([self.ok([])])):
            c.get("/form/1/submissions", limit=1000, filter=flt)
        sent = next(a for a in self.spawned[0] if a.startswith(self.gj.API_BASE))
        self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(sent).query)["filter"], [flt])

    def test_retry_then_success_then_give_up(self):
        import contextlib
        import io
        from unittest import mock
        naps = []
        c = self.gj.Client("KEY", retries=3, backoff=1, sleep=naps.append)
        out = io.StringIO()
        with mock.patch.object(self.gj.subprocess, "run",
                               self.fake(["<html>504</html>", "<html>504</html>", self.ok()])), \
                contextlib.redirect_stdout(out):
            self.assertEqual(c.get("/x"), {"x": 1})
        self.assertEqual((len(self.spawned), naps), (3, [1, 1]))
        self.assertEqual(out.getvalue(), "  ! GET /x: attempt 1/3 failed - retrying in 1s\n"
                                         "  ! GET /x: attempt 2/3 failed - retrying in 1s\n")
        self.spawned.clear()
        c1 = self.gj.Client("KEY")                       # default: one attempt
        out = io.StringIO()
        with mock.patch.object(self.gj.subprocess, "run", self.fake(["nope"])), contextlib.redirect_stdout(out):
            with self.assertRaises(self.gj.JotformError):
                c1.get("/x")
            self.assertIsNone(c1.call([c1.url("/x")], "GET /x", allow_fail=True))
        self.assertEqual(out.getvalue(), "  ! GET /x: GET /x: non-JSON response: 'nope'  (continuing)\n")

    def test_a_json_body_goes_on_standard_input_never_as_an_argument(self):
        # Linux refuses one argument over 131,072 bytes; Africa's rules are about 153 KB
        from unittest import mock
        rules = [{"id": str(i), "terms": "x" * 900} for i in range(250)]       # > 200 KB as JSON
        payload = {"properties": {"conditions": rules}}
        self.assertGreater(len(json.dumps(payload)), 200_000)
        c = self.gj.Client("KEY", apply=True)
        with mock.patch.object(self.gj.subprocess, "run", self.fake([self.ok()])):
            self.assertEqual(c.put_json("/form/1/properties", payload, "REPLACE conditions"), {"x": 1})
            self.assertEqual(c.post_json("/form/1/translations", payload, "POST translations"), {"x": 1})
            c.get("/form/1/questions")
        for argv, body in zip(self.spawned[:2], self.bodies[:2]):
            self.assertEqual(argv[argv.index("--data-binary") + 1], "@-")
            self.assertEqual(json.loads(body), payload)
            self.assertLess(max(len(a.encode()) for a in argv), 131_072)
            self.assertTrue(self.gj.is_write(argv[2:]))
        self.assertIsNone(self.bodies[2])                        # a GET sends nothing
        self.assertEqual(c.calls, ["REPLACE conditions", "POST translations"])

    def test_a_retry_sends_the_body_again(self):
        import contextlib
        import io
        from unittest import mock
        c = self.gj.Client("KEY", apply=True, retries=3, backoff=0, sleep=lambda s: None)
        out = io.StringIO()
        with mock.patch.object(self.gj.subprocess, "run",
                               self.fake(["<html>504</html>", "<html>504</html>", self.ok()])), \
                contextlib.redirect_stdout(out):
            self.assertEqual(c.put_json("/form/1/properties", {"a": "é"}, "REPLACE y"), {"x": 1})
        self.assertEqual(self.bodies, [json.dumps({"a": "é"})] * 3)
        self.assertEqual(out.getvalue(), "  ! REPLACE y: attempt 1/3 failed - retrying in 0s\n"
                                         "  ! REPLACE y: attempt 2/3 failed - retrying in 0s\n")

    def test_an_argument_too_large_for_a_command_line_is_refused_not_tried(self):
        from unittest import mock
        c = self.gj.Client("KEY", apply=True)
        with mock.patch.object(self.gj.subprocess, "run", self.fake([self.ok()])):
            with self.assertRaises(self.gj.JotformError) as e:
                c.post_form("/form/1/question/5", {"question[options]": "n" * 130_000}, "UPDATE q5")
            self.assertIn("cannot go on a command line", str(e.exception))
            self.assertNotIn("nnnn", str(e.exception))
            self.assertEqual(self.spawned, [])                   # curl was never started
            dry = self.gj.Client("KEY")                          # a dry run refuses it as well
            with self.assertRaises(self.gj.JotformError):
                dry.post_form("/form/1/question/5", {"question[options]": "n" * 130_000}, "UPDATE q5")
            self.assertEqual((dry.calls, self.spawned), ([], []))
            self.assertEqual(c.post_form("/form/1/question/5", {"question[options]": "n" * 90_000},
                                         "UPDATE q5"), {"x": 1})

    def test_a_curl_that_cannot_start_is_a_clean_error(self):
        from unittest import mock

        def boom(argv, **kw):
            raise OSError(7, "Argument list too long")
        c = self.gj.Client("KEY")
        with mock.patch.object(self.gj.subprocess, "run", boom), self.assertRaises(self.gj.JotformError) as e:
            c.get("/x")
        self.assertIn("curl could not be started", str(e.exception))

    def test_the_public_page_is_one_keyless_curl_whose_failure_is_refused(self):
        import subprocess as sp
        from unittest import mock
        with mock.patch.object(self.gj.subprocess, "run", self.fake(["<html>page</html>"])):
            self.assertEqual(self.gj.public_page("123"), "<html>page</html>")
        argv, = self.spawned
        self.assertEqual(argv[:2], ["curl", "-sSL"])
        self.assertEqual(argv[-1], "https://form.jotform.com/123")
        self.assertIn("--max-time", argv)
        self.assertFalse(any("apiKey" in a for a in argv))              # no key goes to a public page

        def down(argv, **kw):
            return sp.CompletedProcess(argv, 6, stdout="", stderr="curl: (6) Could not resolve host\n")
        with mock.patch.object(self.gj.subprocess, "run", down), self.assertRaises(self.gj.JotformError) as e:
            self.gj.public_page("123")
        self.assertIn("public page of form 123: curl exited 6", str(e.exception))

    def test_a_page_that_cannot_be_fetched_is_never_an_empty_one(self):
        # switcher_flags --check-page read a network failure as "0 languages"; form_status
        # --rendered as a page without its arrays; fix_name_translations' check stays its own
        import subprocess as sp
        from unittest import mock
        import fix_name_translations
        import switcher_flags

        def down(argv, **kw):
            return sp.CompletedProcess(argv, 28, stdout="", stderr="curl: (28) timed out\n")
        with mock.patch.object(self.gj.subprocess, "run", down):
            with self.assertRaises(self.gj.JotformError):
                switcher_flags.page_flags("123")
            self.assertIsNone(fix_name_translations.page_count("123", {"k"}, True, self.gj.public_page))
        page = '<li data-lang="or" x>a</li><li data-lang="te">b<svg/></li>'
        with mock.patch.object(self.gj.subprocess, "run", self.fake([page])):
            self.assertEqual(switcher_flags.page_flags("123"), (False, {"or": False, "te": True}))

    def test_is_write_catches_every_shape(self):
        w = self.gj.is_write
        self.assertTrue(w(["-X", "POST", "u"]))
        self.assertTrue(w(["-X", "DELETE", "u"]))
        self.assertTrue(w(["u", "--data-binary", "{}"]))
        self.assertTrue(w(["--data-urlencode", "a=b", "u"]))
        self.assertFalse(w(["u"]))
        self.assertFalse(w(["-H", "Accept: x", "u"]))


class GlowText(unittest.TestCase):
    """glow.text must be byte-equal to the per-script copies it replaced."""

    CORPUS = [None, "", "  ", 7, "Ana  Maria\tLopez ", "ÑANDÚ vex", "Zoë", "İstanbul",
              "café", "\u200bGrace", "a\xa0b", "MiXeD CaSe", "ümit-öz"]

    @staticmethod
    def old_key(s):                                     # tools/form_status.py (pre-refactor)
        return " ".join(str(s or "").split()).lower()

    @staticmethod
    def old_name_key(s):
        import unicodedata
        s = unicodedata.normalize("NFKD", str(s or ""))
        s = "".join(c for c in s if not unicodedata.combining(c))
        return " ".join(s.split()).lower()

    def test_byte_equal_to_the_old_implementations(self):
        from glow import text
        import hashlib
        for s in self.CORPUS:
            self.assertEqual(text.key(s), self.old_key(s), repr(s))
            self.assertEqual(text.name_key(s), self.old_name_key(s), repr(s))
        for s in ("Session 4", "Mentor Email", "日本語", ""):
            self.assertEqual(text.md5(s), hashlib.md5(s.encode("utf-8")).hexdigest())


class GlowForms(unittest.TestCase):
    def test_shape(self):
        from glow import forms
        self.assertEqual(set(forms.REGIONALS), set(forms.REGIONS))
        self.assertEqual(len(forms.LABELS), 10)
        self.assertEqual(forms.region_of(forms.REGIONALS["Asia"]), "Asia")
        self.assertIsNone(forms.region_of(forms.TEMPLATE))
        self.assertIsNone(forms.region_of(forms.DEFUNCT["Africa"]))
        ids = {forms.TEMPLATE, *forms.REGIONALS.values(), *forms.DEFUNCT.values()}
        self.assertEqual(len(ids), 10)


class GlowCli(unittest.TestCase):
    """glow/cli.py: the API key every tool reads and the forms a --form selects."""

    def key(self, env, *args, **kw):
        from unittest import mock

        from glow import cli
        with mock.patch.dict(os.environ, env, clear=True):
            return cli.api_key(*args, **kw)

    def test_the_key_comes_from_the_environment_stripped(self):
        self.assertEqual(self.key({"JOTFORM_API_KEY": "  k3y\n"}), "k3y")

    def test_no_key_stops_with_what_to_set(self):
        for env in ({}, {"JOTFORM_API_KEY": ""}, {"JOTFORM_API_KEY": " \t\n"}):
            with self.subTest(env=env), self.assertRaises(SystemExit) as stop:
                self.key(env)
            self.assertEqual(str(stop.exception.code), "Set JOTFORM_API_KEY in the environment (.env)")
        with self.assertRaises(SystemExit) as stop:
            self.key({}, ", or pass --sheet-only")
        self.assertEqual(stop.exception.code, "Set JOTFORM_API_KEY in the environment (.env), or pass --sheet-only")

    def test_a_tool_may_raise_its_own_refusal_instead(self):
        class Refused(Exception):
            pass
        with self.assertRaises(Refused) as stop:
            self.key({}, ": a write reads the forms first", error=Refused)
        self.assertEqual(str(stop.exception), "Set JOTFORM_API_KEY in the environment (.env): a write reads the forms first")

    def test_targets_are_the_forms_given_or_every_live_form(self):
        from glow import cli, forms
        every = cli.targets(None)
        self.assertEqual(every, forms.LIVE)
        self.assertEqual(list(every)[0], forms.TEMPLATE)              # the template first, as LIVE has it
        every["x"] = "y"
        self.assertNotIn("x", forms.LIVE)                            # a copy: a caller cannot change LIVE
        self.assertEqual(cli.targets([]), forms.LIVE)
        asia = forms.REGIONALS["Asia"]
        self.assertEqual(cli.targets([asia, "123", forms.TEMPLATE]), {asia: "Asia", "123": "?", forms.TEMPLATE: "template"})
        self.assertEqual(list(cli.targets([asia, forms.TEMPLATE])), [asia, forms.TEMPLATE])   # in the order given
        titles = {asia: "Asia Attendance Form"}
        self.assertEqual(cli.targets(None, titles), titles)
        self.assertEqual(cli.targets([asia, "123"], titles, unknown=None), {asia: "Asia Attendance Form", "123": "123"})


class GlowSyncHelpers(unittest.TestCase):
    """glow/sync.py's readers of a form that every tool shares."""

    def test_club_picker_is_the_dropdown_by_its_name(self):
        from glow import sync
        qs = {"5": {"type": "control_textbox", "name": "clubName"},
              "331": {"type": "control_textbox", "name": "partner"},
              "600": {"type": "control_dropdown", "name": sync.PARTNER_PICKER_NAME},
              "700": {"type": "control_checkbox", "name": sync.PICKER_NAME},       # not a dropdown
              "500": {"type": "control_dropdown", "name": sync.PICKER_NAME}}
        self.assertEqual(sync.club_picker(qs), "500")
        self.assertEqual(sync.partner_picker(qs), "600")
        del qs["500"]
        self.assertIsNone(sync.club_picker(qs))                  # mentors type the club name
        self.assertIsNone(sync.club_picker({}))

    def test_rule_parts_reads_wire_and_parsed_rules_and_nothing_else(self):
        from glow import sync
        terms = [{"field": "500", "operator": "equals", "value": "Alpha Club"}]
        actions = [{"visibility": "Show", "field": "10"}]
        wire = {"id": "1", "terms": json.dumps(terms), "action": json.dumps(actions)}
        self.assertEqual(sync.rule_parts(wire), (terms, actions))                     # as Jotform serves it
        self.assertEqual(sync.rule_parts({"terms": terms, "action": actions}), (terms, actions))
        self.assertEqual(sync.rule_parts({"terms": terms, "action": actions[0]}), (terms, actions))  # a lone action
        self.assertEqual(sync.rule_parts({}), ([], []))
        self.assertEqual(sync.rule_parts({"terms": None, "action": []}), ([], []))
        for bad in ({"terms": "{broken", "action": "[]"}, {"terms": "[]", "action": "nope"},
                    {"terms": 5, "action": []}, {"terms": {"field": "5"}, "action": []},
                    {"terms": ["5"], "action": []}, {"terms": [], "action": ["Show"]},
                    {"terms": json.dumps("a string"), "action": []}, "not a rule", None):
            with self.subTest(rule=bad):
                self.assertIsNone(sync.rule_parts(bad))

    def test_every_roster_reader_reads_one_way_and_refuses_one_way(self):
        # glow.sync._roster_rows: utf-8-sig, by header, and one refusal for what is not an export
        import tempfile
        import form_status
        from glow import sync
        refusal = "Not a Roster export: expected the columns club, full_name, partner, region, status"
        readers = (sync.roster_pairs, sync.roster_names, sync.read_roster_csv, form_status.load_roster)
        with tempfile.TemporaryDirectory() as tmp:
            other, roster = os.path.join(tmp, "other.csv"), os.path.join(tmp, "roster.csv")
            with open(other, "w", encoding="utf-8") as f:
                f.write("partner,club\nPartner One,Alpha Club\n")
            with open(roster, "w", encoding="utf-8-sig", newline="") as f:
                f.write("partner,club,full_name,status,region,removed_date\r\n"
                        "Partner One,Alpha Club,Ana Example,active,Africa,\r\n"
                        "Partner One,Alpha Club,Bea Example,inactive,Africa,2026-10-01\r\n")
            for reader in readers:
                with self.subTest(reader=reader.__name__):
                    with self.assertRaises(SystemExit) as cm:
                        reader(other)
                    self.assertEqual(cm.exception.code, refusal)
            self.assertEqual(sync.roster_removed(other), {})                  # no removed_date column: none
            self.assertEqual(sync.roster_pairs(roster), {("Partner One", "Alpha Club"): True})
            self.assertEqual(sync.roster_names(roster), {("partner one", "alpha club"): {"ana example", "bea example"}})
            self.assertEqual(sync.read_roster_csv(roster)[0], {("Partner One", "Alpha Club"): ["Ana Example"]})
            self.assertEqual(sync.roster_removed(roster), {("partner one", "alpha club"): "2026-10-01"})
            self.assertEqual(list(form_status.load_roster(roster)), ["Africa"])


class GlowBackup(unittest.TestCase):
    """glow/backup.py: the one stamp (to the second), the snapshot files and the
    conditions-only copy, in a temporary backups/ folder."""

    class Fake:
        def __init__(self):
            self.reads = []

        def get(self, path):
            self.reads.append(path)
            if path.endswith("/questions"):
                return {"1": {"type": "control_head"}, "5": {"type": "control_textbox"}}
            return {"conditions": [{"id": "1"}, {"id": "2"}], "emails": [{}],
                    "integrations": {"salesforceV2": {"integrationAccountID": "x"}}}

    def test_one_stamp_to_the_second(self):
        import datetime as dt
        from glow import backup
        first, again = dt.datetime(2026, 9, 28, 10, 0, 5), dt.datetime(2026, 9, 28, 10, 0, 40)
        self.assertEqual(backup.stamp(first), "2026-09-28T100005")
        self.assertNotEqual(backup.stamp(first), backup.stamp(again))     # a re-run within the minute
        self.assertRegex(backup.stamp(), r"^\d{4}-\d\d-\d\dT\d{6}$")

    def test_no_tool_mints_a_minute_stamp(self):
        from helpers.common import REPO, read
        for folder in ("", "tools", "glow"):
            for name in sorted(os.listdir(os.path.join(REPO, folder))):
                if name.endswith(".py"):
                    with self.subTest(file=os.path.join(folder, name)):
                        self.assertNotIn('"%Y-%m-%dT%H%M"', read(os.path.join(REPO, folder, name)))

    def test_snapshot_writes_the_stamp_and_latest(self):
        import tempfile
        from unittest import mock
        from glow import backup
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(backup, "REPO", tmp):
            fake = self.Fake()
            s = backup.snapshot("123", fake, "2026-10-09T101530")
            self.assertEqual(s, {"questions": 2, "conditions": 2, "emails": 1, "salesforce": "yes",
                                 "stamp": "2026-10-09T101530"})
            self.assertEqual(fake.reads, ["/form/123/questions", "/form/123/properties"])
            self.assertEqual(sorted(os.listdir(os.path.join(tmp, "backups", "123"))),
                             ["properties-2026-10-09T101530.json", "properties-latest.json",
                              "questions-2026-10-09T101530.json", "questions-latest.json"])
            self.assertEqual(backup.path("123", "properties"),
                             os.path.join(tmp, "backups", "123", "properties-latest.json"))
            path = backup.save_conditions("123", "2026-10-09T101530")
            with open(path, encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"conditions": [{"id": "1"}, {"id": "2"}]})
            # latest=False leaves the -latest files alone (restore_conditions' snapshot)
            backup.snapshot("123", fake, "2026-10-09T101600", latest=False)
            with open(backup.path("123", "properties"), encoding="utf-8") as f:
                self.assertEqual(len(json.load(f)["conditions"]), 2)
            self.assertTrue(os.path.exists(backup.path("123", "questions", "2026-10-09T101600")))
            # no stamp given: one is minted, and returned
            self.assertRegex(backup.snapshot("124", fake)["stamp"], r"^\d{4}-\d\d-\d\dT\d{6}$")


class TranslationLookup(unittest.TestCase):
    """glow/translation_lookup.py: the runtime's names dictionary (formTranslation.v2.js:
    setDictionary, trimMultiSpaces, sanitizeKeys, translate's fall-back) and the removal
    plan, on fictional names (docs/plans/2026-10-02-names-and-modules.md)."""

    NAME = "Amara Fennwhistle"

    def test_javascripts_whitespace_simplify_and_key_order(self):
        self.assertEqual(tl.js_trim("\ufeff\u3000 Amara \u2028"), "Amara")
        self.assertEqual(tl.js_trim("\x85Amara\x1c"), "\x85Amara\x1c")      # whitespace to Python only
        self.assertEqual("\x85Amara\x1c".strip(), "Amara")
        self.assertEqual(tl.simplify(" Amara &amp; Grace<br>Fennwhistle\t\t &gt; "), "Amara & Grace Fennwhistle >")
        # the ideographic space is replaced AFTER the double spaces: one double space survives
        self.assertEqual(tl.simplify("Amara\u3000 Fennwhistle"), "Amara  Fennwhistle")
        self.assertEqual(tl.replace_nbsp("Amara\xa0Grace\u202fFennwhistle"), "Amara Grace Fennwhistle")
        self.assertEqual(tl.js_order({"b": 1, "10": 2, "a": 3, "2": 4, "01": 5}), ["2", "10", "b", "a", "01"])

    def test_a_stale_spelling_in_base_and_en_alters_the_exact_name(self):
        for variant in ("Amara  Fennwhistle", "Amara\tFennwhistle", "Amara\xa0Fennwhistle",
                        "Amara \u2003 Fennwhistle", "Amara\nFennwhistle",
                        "Amara\u202fFennwhistle"):
            store = name_store([(self.NAME, self.NAME), (variant, variant)])
            for skip in tl.BUILDS:
                lookup = tl.Lookup(store, skip_missing=skip)
                result, hits = lookup.trace(self.NAME, "en")
                self.assertEqual(result, variant, repr(variant))
                self.assertEqual(lookup.sources(hits), {md5(variant)}, repr(variant))
            self.assertEqual(tl.altered(store, {self.NAME}), {self.NAME: ["en"]})
            self.assertEqual(tl.removal(store, {self.NAME}), ({md5(variant)}, None))      # only that entry
            self.assertEqual(tl.altered(tl.without(store, {md5(variant)}), {self.NAME}), {})

    def test_an_invisible_mark_is_no_whitespace(self):
        lrm = "Amara\u200e Fennwhistle"
        # in base and en alike, its key keeps the mark: the exact name never lands on it
        store = name_store([(self.NAME, self.NAME), (lrm, lrm)])
        self.assertEqual(tl.altered(store, {self.NAME}), {})
        self.assertEqual(tl.removal(store, {self.NAME}), (set(), None))         # nothing that alters no name
        # the exact name in base, the mark in en: sent with the mark
        store = name_store([(self.NAME, lrm)])
        self.assertEqual(tl.altered(store, {self.NAME}), {self.NAME: ["en"]})
        self.assertEqual(tl.removal(store, {self.NAME}), ({md5(self.NAME)}, None))

    def test_the_stale_spelling_wins_in_either_order_and_two_take_two_rounds(self):
        double, tab = "Amara  Fennwhistle", "Amara\tFennwhistle"
        for entries in ([(self.NAME, self.NAME), (double, double)], [(double, double), (self.NAME, self.NAME)]):
            self.assertEqual(tl.Lookup(name_store(entries)).translate(self.NAME, "en"), double)
        store = name_store([(self.NAME, self.NAME), (double, double), (tab, tab)])
        self.assertEqual(tl.Lookup(store).translate(self.NAME, "en"), tab)           # the later one
        self.assertEqual(tl.removal(store, {self.NAME}), ({md5(double), md5(tab)}, None))

    def test_an_exact_entry_or_none_leaves_a_name_alone(self):
        store = name_store([(self.NAME, self.NAME), ("Grace Marrowgate  ", "Grace Marrowgate  ")], pad=3)
        self.assertEqual(tl.altered(store, {self.NAME, "Grace Marrowgate", "Priya Ostrivane"}), {})
        self.assertEqual(tl.removal(store, {self.NAME, "Grace Marrowgate"}), (set(), None))
        # no `en` at all: the runtime builds no dictionary
        self.assertEqual(tl.Lookup({"base": {md5(self.NAME): "Amara  Fennwhistle"}}).dictionary, {})

    def test_a_ui_string_is_never_picked(self):
        store = name_store([(self.NAME, self.NAME), ("Please  Select", "Please  Select"), ("Club Name", "Club Name")],
                           {"es": {"Club Name": "Nombre del club", "Please  Select": "Seleccione"}})
        self.assertEqual(tl.removal(store, {self.NAME}), (set(), None))
        self.assertEqual(tl.Lookup(store).translate("Please Select", "es"), "Seleccione")    # the runtime's own business

    def test_another_languages_entry_is_never_removed(self):
        double = "Amara  Fennwhistle"
        # the stale key translated in Spanish: removing it would orphan the translation
        store = name_store([(self.NAME, self.NAME), (double, double)], {"es": {double: "Amara Fennwhistle (es)"}})
        keys, why = tl.removal(store, {self.NAME})
        self.assertIsNone(keys)
        self.assertIn("another language's entries (es: ", why)
        # a name translated in a language: base/en removal cannot fix it
        store = name_store([(self.NAME, self.NAME)], {"fr": {self.NAME: "Amara Fennwhistle-fr"}})
        self.assertEqual(tl.altered(store, {self.NAME}), {self.NAME: ["fr"]})
        self.assertIn("(fr: ", tl.removal(store, {self.NAME})[1])
        # the fall-back: a Spanish text equal to the name returns its English source
        store = name_store([("Welcome", "Welcome")], {"es": {"Welcome": self.NAME}})
        result, hits = tl.Lookup(store).trace(self.NAME, "en")
        self.assertEqual((result, [h[:2] for h in hits]), ("Welcome", [("match", "es"), ("value", "en")]))
        self.assertIsNone(tl.removal(store, {self.NAME})[0])
        self.assertEqual(tl.target_languages(store), ["en", "es"])                # never base
        # removing base/en entries leaves every other language as it was
        cut = tl.without(store, {md5("Welcome")})
        self.assertEqual((cut["es"], cut["base"], cut["en"]), (store["es"], {}, {}))

    def test_the_two_runtime_builds_differ_on_an_entry_missing_in_en_or_base(self):
        store = name_store([(self.NAME, self.NAME), ("Only In Base", None)], {"es": {"Not In Base": "No en la base"}})
        new, old = tl.Lookup(store, skip_missing=True), tl.Lookup(store, skip_missing=False)
        self.assertNotIn("undefined", new.dictionary["base"])
        self.assertEqual(old.dictionary["base"]["undefined"], "Only In Base")
        self.assertNotIn("undefined", new.dictionary["es"])
        self.assertEqual(old.dictionary["es"]["undefined"], "No en la base")
        # the audits run both builds
        self.assertEqual(tl.altered(store, {"undefined"}, builds=(True,)), {})
        self.assertEqual(tl.altered(store, {"undefined"}), {"undefined": ["es"]})

    def test_what_cannot_be_emulated_or_removed_is_refused(self):
        self.assertIn("not a translation store", tl.check_store({"base": "x"}))
        self.assertIn("no 'base'", tl.check_store({"en": {}}))
        self.assertIn("1 entry is not text", tl.check_store({"base": {"k": 1}, "en": {}}))
        self.assertIsNone(tl.check_store(name_store([(self.NAME, self.NAME)])))
        with self.assertRaises(ValueError):
            tl.Lookup({"en": {}})
        # a no-break space in the option itself: no entry to remove makes it exact
        keys, why = tl.removal(name_store([(self.NAME, self.NAME)]), {"Amara\xa0Fennwhistle"})
        self.assertIsNone(keys)
        self.assertIn("no dictionary entry", why)

    def test_each_step_of_the_runtime_is_pinned(self):
        # trimMultiSpaces, THEN sanitizeKeys: the double space moves first, the <br> spelling over it
        br, double = "Amara<br>Fennwhistle", "Amara  Fennwhistle"
        store = name_store([(br, br), (self.NAME, self.NAME), (double, double)])
        self.assertEqual(tl.Lookup(store).translate(self.NAME, "en"), br)
        self.assertEqual(tl.removal(store, {self.NAME}), ({md5(br), md5(double)}, None))
        # the fall-back never walks the language shown: en's own text equal to the name is no match
        store = name_store([("Amara Fenwhistle", double)])
        self.assertEqual(tl.altered(store, {self.NAME}), {})
        self.assertEqual(tl.removal(store, {self.NAME}), (set(), None))
        # another language is keyed by the base text trimmed (the fall-back reads it there)
        store = name_store([(" Welcome ", " Welcome ")], {"es": {" Welcome ": self.NAME}})
        self.assertEqual(tl.altered(store, {self.NAME}), {self.NAME: ["en"]})
        # ... or by the element id when the en text is one
        store = name_store([("Hello", "text_7")], {"es": {"Hello": "Hola"}})
        self.assertEqual(list(tl.Lookup(store).dictionary["es"]), ["text_7"])
        # a fall-back match is traced to the entry it was when the texts were simplified, and to
        # the one now under its key
        store = name_store([("Club Name", "Club Name"), ("Club  Name", "Club  Name")],
                           {"es": {"Club Name": self.NAME, "Club  Name": "Nombre del club"}})
        lookup = tl.Lookup(store)
        result, hits = lookup.trace(self.NAME, "en")
        self.assertEqual(result, "Club  Name")
        self.assertEqual(lookup.sources(hits), {md5("Club Name"), md5("Club  Name")})

    def test_an_option_that_simplifies_to_nothing_is_sent_empty(self):
        # the checkbox reader pushes translate(value) as it is: '' for a value simplifyfWord
        # empties, never the value (that only on a page without FormTranslation)
        store = name_store([(self.NAME, self.NAME)], {"es": {self.NAME: self.NAME}})
        for option in (" ", "&nbsp;", "\ufeff", "\u00a0"):
            self.assertEqual(tl.Lookup(store).translate(option, "en"), "", repr(option))
            self.assertTrue(tl.is_altered(option, ""), repr(option))
            self.assertEqual(tl.altered(store, {option}), {option: ["en", "es"]}, repr(option))
            keys, why = tl.removal(store, {option})
            self.assertIsNone(keys, repr(option))
            self.assertIn("no dictionary entry", why)
        self.assertFalse(tl.is_altered(self.NAME, self.NAME))


if __name__ == "__main__":
    unittest.main(verbosity=1)
