#!/usr/bin/env python3
"""
The glow/ library: the Jotform client's dry-run gate and call shapes (GlowClient), glow.text
against the per-script copies it replaced (GlowText), glow.forms (GlowForms) and the runtime's
names dictionary as glow/translation_lookup.py emulates it (TranslationLookup). No network;
fictional names.
"""
import json
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
