#!/usr/bin/env python3
"""
tools/restore_translations.py --from-file <saved store>: a form's translated languages put back
exactly as a saved store holds them (backups/translations/<form>-<stamp>-before.json, the file
every translations POST saves first) - the rollback for a POST that read back MISMATCH.

Through main() on a fake Jotform (no network; backups/ in a temporary folder): the dry run
(per language how many keys differ, are added, are removed; nothing written), the apply (the
current store saved first, never over the file restored from; each differing language posted
WHOLE, a replace; English base/en never posted; a language only the live store has left alone;
the re-read), a re-read that does not match, and the refusals (no such file, not JSON, not a
store, another form's file, --source beside --from-file). Fictional strings only.
"""
import contextlib
import copy
import io
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

# first: importing helpers.common puts the repository root and tools/ on sys.path
import helpers.common  # noqa: F401
import restore_translations
from glow import forms as glow_forms
from glow import translations
from glow.text import md5

GIRL = "Amara Fennwhistle"          # fictional; held in base/en, never printed


def k(text):
    return md5(text)


class Fake:
    """A Jotform holding a translation store and a language property per form. A POST
    /translations replaces each language it carries, as Jotform's does, and records which
    files were in backups/translations at that moment. drop: {language: key} removed from the
    store right after a POST that carried that language (the re-read then differs)."""

    def __init__(self, folder, stores, drop=None):
        self.folder, self.stores, self.drop = folder, stores, drop or {}
        self.posts, self.puts = [], []

    def get(self, path, **params):
        fid, what = path.split("/")[2], path.rstrip("/").rsplit("/", 1)[1]
        if what == "translations":
            return copy.deepcopy(self.stores.get(fid, {}))
        if what == "properties":
            return {"language": [{"primaryLanguage": "en", "options": "English (US)|Español"}]}
        return {}

    def post_json(self, path, payload, label):
        fid = path.split("/")[2]
        on_disk = sorted(os.listdir(self.folder)) if os.path.isdir(self.folder) else []
        self.posts.append((fid, copy.deepcopy(payload), on_disk))
        for lang, d in payload.items():
            self.stores.setdefault(fid, {})[lang] = copy.deepcopy(d)
            if lang in self.drop:
                self.stores[fid][lang].pop(self.drop[lang], None)
        return {}

    def put_json(self, path, payload, label):
        self.puts.append((path, copy.deepcopy(payload)))
        return {}

    def post_form(self, path, data, label):
        self.posts.append((path.split("/")[2], dict(data), []))
        return {}

    def posted(self, fid):
        """{language: the dictionary last posted for it} on form `fid`."""
        out = {}
        for f, payload, _ in self.posts:
            if f == fid:
                out.update(copy.deepcopy(payload))
        return out


def counts(saved, live):
    """(differ, added, removed) of one language: keys in both with other text, keys only the
    saved file has, keys only the live store has."""
    return (sum(1 for x in saved if x in live and live[x] != saved[x]),
            sum(1 for x in saved if x not in live),
            sum(1 for x in live if x not in saved))


def english(extra=()):
    texts = ["Date", "Club Name", GIRL, *extra]
    d = {k(t): t for t in texts}
    return {"base": dict(d), "en": dict(d)}


# Two forms, two saved files, two damaged live stores: the counts differ per language and per
# scenario, so no fixed answer passes both.
SCENARIOS = {
    "africa": {
        "form": glow_forms.REGIONALS["Africa"],
        "name": "{form}-2026-10-25T091500-before.json",
        "saved": {**english(),
                  "es": {k("Date"): "Fecha", k("Club Name"): "Nombre del club",
                         k("Session notes"): "Notas de la sesion", k("Week"): "Semana"},
                  "fr": {k("Date"): "Date (fr)", k("Club Name"): "Nom du club"},
                  "pt": {k("Date"): "Data", k("Club Name"): "Nome do clube"}},
        "live": {**english(["Session notes (optional)"]),
                 "es": {k("Date"): "Fecha", k("Club Name"): "Nombre roto",
                        k("Week"): "Semana rota", k("Stray 1"): "uno", k("Stray 2"): "dos",
                        k("Stray 3"): "tres"},
                 "fr": {k("Date"): "Date (fr)", k("Club Name"): "Nom du club"},
                 "th": {k("Date"): "Wan thi (fictional)"}},
        "changed": {"es", "pt"},           # differ from the live store: posted
        "same": {"fr"},                    # read back as saved already: not posted
        "live_only": {"th"},               # the file lacks it: left alone
    },
    "asia": {
        "form": glow_forms.REGIONALS["Asia"],
        "name": "{form}-2026-10-24T201005-2-before.json",
        "saved": {**english(["Notes"]),
                  "es": {k("A"): "a-es", k("B"): "b-es", k("C"): "c-es", k("D"): "d-es",
                         k("E"): "e-es"},
                  "hi": {k("A"): "a-hi", k("B"): "b-hi"},
                  "fa": {k("A"): "a-fa"}},
        "live": {**english(),
                 "es": {k("A"): "a-es wrong", k("B"): "b-es", k("F"): "f-es"},
                 "hi": {k("A"): "a-hi", k("B"): "b-hi wrong"},
                 "fa": {k("A"): "a-fa"},
                 "ne": {k("A"): "a-ne"}},
        "changed": {"es", "hi"},
        "same": {"fa"},
        "live_only": {"ne"},
    },
}


class RestoreFromFile(unittest.TestCase):
    """restore_translations.py --form <id> --from-file <saved store> [--apply]."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = mock.patch.object(translations, "REPO", self.tmp.name)
        self.repo.start()
        self.folder = os.path.join(self.tmp.name, "backups", "translations")
        os.makedirs(self.folder)

    def tearDown(self):
        self.repo.stop()
        self.tmp.cleanup()

    def write_saved(self, name, store, raw=None):
        path = os.path.join(self.folder, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(raw if raw is not None else json.dumps(store, ensure_ascii=False, indent=1))
        os.chmod(path, 0o600)
        return path

    def scenario(self, key, **fake_kw):
        sc = copy.deepcopy(SCENARIOS[key])
        path = self.write_saved(sc["name"].format(form=sc["form"]), sc["saved"])
        fake = Fake(self.folder, {sc["form"]: copy.deepcopy(sc["live"])}, **fake_kw)
        return sc, path, fake

    def run_tool(self, argv, fake):
        """(exit code or message, stdout + stderr) of main() on `fake`."""
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(restore_translations, "Client", lambda *a, **kw: fake), \
                mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}), \
                mock.patch.object(sys, "argv", ["restore_translations.py", *argv]), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                restore_translations.main()
                code = 0
            except SystemExit as e:
                code = e.code
        text = out.getvalue() + err.getvalue()
        self.assertNotIn(GIRL, text + str(code))         # base/en hold names: never printed
        return code, text

    def files(self):
        return set(os.listdir(self.folder))

    @staticmethod
    def lang_lines(out, lang):
        """The output lines that name `lang` (as a whole word) with a count."""
        return [ln for ln in out.splitlines()
                if re.search(rf"(?<![\w-]){re.escape(lang)}(?![\w-])", ln)
                and re.search(r"differ|added|removed", ln)]

    # -- broad behaviour ---------------------------------------------------------------------

    def test_dry_run_reports_each_language_and_writes_nothing(self):
        for key in SCENARIOS:
            with self.subTest(scenario=key):
                sc, path, fake = self.scenario(key)
                before_files = self.files()
                code, out = self.run_tool(["--form", sc["form"], "--from-file", path], fake)
                self.assertIn(code, (0, None), out)
                self.assertIn("DRY RUN", out)
                self.assertEqual((fake.posts, fake.puts), ([], []))           # nothing written
                self.assertEqual(self.files(), before_files)                 # nothing saved
                self.assertEqual(fake.stores[sc["form"]], sc["live"])
                for lang in sorted(sc["changed"]):
                    d, a, r = counts(sc["saved"][lang], sc["live"].get(lang, {}))
                    lines = self.lang_lines(out, lang)
                    self.assertTrue(lines, f"no count line for {lang}:\n{out}")
                    line = " ".join(lines)
                    self.assertRegex(line, rf"\b{d} differ", line)
                    self.assertRegex(line, rf"\b{a} added", line)
                    self.assertRegex(line, rf"\b{r} removed", line)
                for lang in sorted(sc["live_only"]):                         # reported, not deleted
                    self.assertRegex(out, rf"(?<![\w-]){lang}(?![\w-])", out)
                os.remove(path)

    def test_apply_saves_the_current_store_then_posts_each_changed_language_whole(self):
        for key in SCENARIOS:
            with self.subTest(scenario=key):
                sc, path, fake = self.scenario(key)
                before_files = self.files()
                code, out = self.run_tool(["--form", sc["form"], "--from-file", path, "--apply"], fake)
                self.assertEqual(code, 0, out)
                self.assertIn("RESTORED", out)
                self.assertNotIn("MISMATCH", out)
                # the current store saved first, whole, mode 600, beside (not over) the file
                new = self.files() - before_files
                self.assertEqual(len(new), 1, self.files())
                saved_now = os.path.join(self.folder, new.pop())
                self.assertRegex(os.path.basename(saved_now),
                                 rf"^{sc['form']}-\d{{4}}-\d\d-\d\dT\d{{6}}(-\d+)?-before\.json$")
                self.assertEqual(os.stat(saved_now).st_mode & 0o777, 0o600)
                with open(saved_now, encoding="utf-8") as f:
                    self.assertEqual(json.load(f), sc["live"])
                with open(path, encoding="utf-8") as f:
                    self.assertEqual(json.load(f), sc["saved"])               # the source untouched
                self.assertTrue(fake.posts)
                for fid, _, on_disk in fake.posts:
                    self.assertEqual(fid, sc["form"])
                    self.assertIn(os.path.basename(saved_now), on_disk)       # saved before the POST
                # each changed language posted with its WHOLE saved dictionary; nothing else
                posted = fake.posted(sc["form"])
                self.assertEqual(set(posted), sc["changed"])
                for lang in sc["changed"]:
                    self.assertEqual(posted[lang], sc["saved"][lang])
                # the form now holds the saved languages exactly (a replace, not a merge)
                store = fake.stores[sc["form"]]
                for lang in sc["changed"] | sc["same"]:
                    self.assertEqual(store[lang], sc["saved"][lang])
                for lang in sc["live_only"]:                                 # left alone
                    self.assertEqual(store[lang], sc["live"][lang])
                for lang in ("base", "en"):                                  # never posted
                    self.assertEqual(store[lang], sc["live"][lang])
                for name in self.files():
                    os.remove(os.path.join(self.folder, name))

    def test_english_base_and_en_are_never_posted_even_when_they_differ(self):
        form = glow_forms.REGIONALS["Latin America"]
        saved = {"base": {k("Only in the file"): "Only in the file"},
                 "en": {k("Only in the file"): "Only in the file"},
                 "es": {k("Date"): "Fecha"}}
        live = {**english(), "es": {k("Date"): "Fecha rota"}}
        path = self.write_saved(f"{form}-2026-10-25T120000-before.json", saved)
        fake = Fake(self.folder, {form: copy.deepcopy(live)})
        code, out = self.run_tool(["--form", form, "--from-file", path, "--apply"], fake)
        self.assertEqual(code, 0, out)
        self.assertEqual(fake.posted(form), {"es": saved["es"]})
        self.assertEqual({x: fake.stores[form][x] for x in ("base", "en")},
                         {x: live[x] for x in ("base", "en")})

    def test_nothing_differs_nothing_posted(self):
        sc = copy.deepcopy(SCENARIOS["africa"])
        live = {**sc["live"], "es": sc["saved"]["es"], "pt": sc["saved"]["pt"]}
        path = self.write_saved(sc["name"].format(form=sc["form"]), sc["saved"])
        fake = Fake(self.folder, {sc["form"]: copy.deepcopy(live)})
        code, out = self.run_tool(["--form", sc["form"], "--from-file", path, "--apply"], fake)
        self.assertEqual(code, 0, out)
        self.assertEqual(fake.posts, [])
        self.assertNotIn("MISMATCH", out)
        self.assertEqual(fake.stores[sc["form"]], live)

    def test_a_reread_that_differs_is_a_mismatch_naming_the_saved_store(self):
        for key, (lang, dropped) in {"africa": ("es", k("Session notes")), "asia": ("hi", k("B"))}.items():
            with self.subTest(scenario=key):
                sc, path, fake = self.scenario(key, drop={lang: dropped})
                before_files = self.files()
                code, out = self.run_tool(["--form", sc["form"], "--from-file", path, "--apply"], fake)
                self.assertNotIn(code, (0, None), out)
                text = out + str(code)
                self.assertIn("MISMATCH", text)
                self.assertNotIn("RESTORED", out)
                new = self.files() - before_files
                self.assertEqual(len(new), 1, self.files())
                self.assertIn(new.pop(), text)          # where the store before the restore is
                for name in self.files():
                    os.remove(os.path.join(self.folder, name))

    def test_the_saved_file_is_never_overwritten_when_the_stamp_collides(self):
        sc = copy.deepcopy(SCENARIOS["africa"])
        stamp = "2026-10-25T091500"
        path = self.write_saved(f"{sc['form']}-{stamp}-before.json", sc["saved"])
        fake = Fake(self.folder, {sc["form"]: copy.deepcopy(sc["live"])})
        with mock.patch.object(restore_translations.backup, "stamp", lambda now=None: stamp):
            code, out = self.run_tool(["--form", sc["form"], "--from-file", path, "--apply"], fake)
        self.assertEqual(code, 0, out)
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), sc["saved"])
        others = [n for n in self.files() if n != os.path.basename(path)]
        self.assertEqual(len(others), 1, self.files())
        with open(os.path.join(self.folder, others[0]), encoding="utf-8") as f:
            self.assertEqual(json.load(f), sc["live"])

    # -- refusals ----------------------------------------------------------------------------

    def assert_refused(self, argv, fake, *mentions):
        before_files = self.files()
        code, out = self.run_tool(argv, fake)
        self.assertIsInstance(code, str, f"not a sys.exit message: {code!r}\n{out}")
        for m in mentions:
            self.assertIn(m, code + out)
        self.assertEqual((fake.posts, fake.puts), ([], []))
        self.assertEqual(self.files(), before_files)
        return code

    def test_refuses_a_missing_file(self):
        form = glow_forms.REGIONALS["Africa"]
        fake = Fake(self.folder, {form: english()})
        path = os.path.join(self.folder, f"{form}-2026-10-25T091500-before.json")
        for extra in ([], ["--apply"]):
            with self.subTest(apply=bool(extra)):
                self.assert_refused(["--form", form, "--from-file", path, *extra], fake,
                                    os.path.basename(path))

    def test_refuses_a_file_that_is_not_json_or_not_a_store(self):
        form = glow_forms.REGIONALS["Africa"]
        bad = {"garbage": "{not json", "list": "[]", "text": '"a store"',
               "flat": json.dumps({"es": "Fecha"}), "nested list": json.dumps({"es": [["k", "v"]]})}
        for i, (what, raw) in enumerate(bad.items()):
            with self.subTest(what=what):
                path = self.write_saved(f"{form}-2026-10-25T09150{i}-before.json", None, raw=raw)
                fake = Fake(self.folder, {form: english()})
                self.assert_refused(["--form", form, "--from-file", path, "--apply"], fake)
                os.remove(path)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root reads any file")
    def test_refuses_an_unreadable_file(self):
        form = glow_forms.REGIONALS["Africa"]
        path = self.write_saved(f"{form}-2026-10-25T091500-before.json", SCENARIOS["africa"]["saved"])
        os.chmod(path, 0)
        try:
            fake = Fake(self.folder, {form: english()})
            self.assert_refused(["--form", form, "--from-file", path, "--apply"], fake)
        finally:
            os.chmod(path, 0o600)

    def test_refuses_a_file_saved_from_another_form(self):
        pairs = [(glow_forms.REGIONALS["Africa"], glow_forms.REGIONALS["Asia"]),
                 (glow_forms.REGIONALS["Asia"], glow_forms.TEMPLATE),
                 (glow_forms.TEMPLATE, glow_forms.REGIONALS["Africa"])]
        for target, other in pairs:
            for extra in ([], ["--apply"]):
                with self.subTest(target=target, file_of=other, apply=bool(extra)):
                    path = self.write_saved(f"{other}-2026-10-25T091500-before.json",
                                            SCENARIOS["africa"]["saved"])
                    fake = Fake(self.folder, {target: copy.deepcopy(SCENARIOS["africa"]["live"]),
                                              other: english()})
                    self.assert_refused(["--form", target, "--from-file", path, *extra], fake, other)
                    os.remove(path)

    def test_refuses_a_file_whose_name_names_no_form(self):
        form = glow_forms.REGIONALS["Africa"]
        path = self.write_saved("store.json", SCENARIOS["africa"]["saved"])
        fake = Fake(self.folder, {form: copy.deepcopy(SCENARIOS["africa"]["live"])})
        self.assert_refused(["--form", form, "--from-file", path, "--apply"], fake)

    def test_from_file_and_source_are_mutually_exclusive(self):
        sc, path, fake = self.scenario("africa")
        before_files = self.files()
        code, out = self.run_tool(["--form", sc["form"], "--from-file", path,
                                   "--source", glow_forms.TEMPLATE, "--apply"], fake)
        self.assertNotIn(code, (0, None), out)
        text = out + str(code)
        self.assertIn("--from-file", text)
        self.assertIn("--source", text)
        self.assertNotIn("unrecognized", text)
        self.assertEqual((fake.posts, fake.puts), ([], []))
        self.assertEqual(self.files(), before_files)


if __name__ == "__main__":
    unittest.main(verbosity=1)
