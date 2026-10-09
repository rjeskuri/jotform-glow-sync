#!/usr/bin/env python3
"""
tools/fix_name_translations.py on five fake forms whose translation stores hold one stale
spelling of a girl's name: the dry run, every refusal, the write and its re-read, --restore.
Fictional names.
"""
import copy
import json
import os
import sys
import unittest

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import name_store
import add_translations
import fix_name_translations
from glow import forms as glow_forms
from glow.text import md5


class FakeStoreClient:
    """glow.jotform.Client stand-in for tools/fix_name_translations.py: the five forms'
    questions, translation stores and properties in memory. A POST /translations
    replaces each posted language, as Jotform's does. mode "lose": written, the answer
    lost; "nothing": not written, an error; "partial": one removed entry comes back;
    "clobber": written, and Spanish emptied (another language changed by the POST);
    "notstore": written, and the store re-read after it is no store.
    before_post(): called at the POST (what was on disk by then)."""

    def __init__(self, questions, stores, mode=None, before_post=None, primary="en"):
        self.questions, self.stores, self.mode, self.before_post = questions, stores, mode, before_post
        self.props = {fid: {"pagetitle": f"{glow_forms.LIVE[fid]} title",
                            "language": [{"primaryLanguage": primary, "options": "English (US)|Español"}]}
                      for fid in questions}
        self.writes = []

    def get(self, path, **params):
        fid, what = path.split("/")[2], path.rsplit("/", 1)[1]
        if self.mode == "notstore" and self.writes and what == "translations":
            return []
        return copy.deepcopy({"questions": self.questions, "translations": self.stores,
                              "properties": self.props}[what][fid])

    def post_json(self, path, payload, label):
        from glow.jotform import JotformError
        fid = path.split("/")[2]
        if self.before_post:
            self.before_post()
        self.writes.append((path, copy.deepcopy(payload), label))
        if self.mode == "nothing":
            raise JotformError(f"{label}: non-JSON response")
        before = copy.deepcopy(self.stores[fid])
        for lang, d in payload.items():
            self.stores[fid][lang] = copy.deepcopy(d)
        if self.mode == "partial":
            gone = next(k for k in before["en"] if k not in payload["en"])
            self.stores[fid]["en"][gone] = before["en"][gone]
        if self.mode == "clobber":
            self.stores[fid]["es"] = {}
        if self.mode == "lose":
            raise JotformError(f"{label}: non-JSON response")
        return {}

    def post_form(self, path, data, label):
        self.writes.append((path, dict(data), label))
        return {}


def served_page(store):
    """The part of a public page tools/fix_name_translations.py reads: the embedded store."""
    return ('<script>window.allTranslations = {"acceptLanguage":null,"translations":'
            + json.dumps(store) + '};\nFormTranslation.init({"primaryLanguage":"en"});</script>')


class FixNameTranslations(unittest.TestCase):
    """tools/fix_name_translations.py on five fake forms whose stores (cloned, as the live
    ones) hold one stale spelling of an Africa girl's name: what the dry run says, every
    refusal, the write (store saved first, base and en only, re-read, audited, the page
    read and re-rendered), a lost answer, and the rollback. Fictional names; none of them
    may be printed."""

    NAME, DOUBLE = "Amara Fennwhistle", "Amara  Fennwhistle"
    CLUBS = {"Africa": ("Sunrise Club", ["Amara Fennwhistle", "Beatrice Wrenfoldy"]),
             "Asia": ("Lotus Club", ["Grace Marrowgate"]),
             "Latin America": ("Andes Club", ["Priya Ostrivane"]),
             "U.S": ("Liberty Club", ["Hope Thornquibble"])}
    AFRICA = glow_forms.REGIONALS["Africa"]
    GIRLS = [g for _, girls in CLUBS.values() for g in girls]

    def setUp(self):
        import tempfile
        from unittest import mock
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = mock.patch.object(add_translations, "REPO", self.tmp.name)
        self.repo.start()

    def tearDown(self):
        self.repo.stop()
        self.tmp.cleanup()

    def questions(self):
        out = {}
        for fid in fix_name_translations.ORDER:
            region = glow_forms.LIVE[fid]
            clubs = list(self.CLUBS.values()) if region == "template" else [self.CLUBS[region]]
            out[fid] = {str(10 + i): {"type": "control_checkbox", "text": club, "options": "|".join(girls)}
                        for i, (club, girls) in enumerate(clubs)}
            out[fid]["2"] = {"type": "control_button", "text": "Submit"}
        return out

    def store(self, extra=()):
        return name_store([(g, g) for g in self.GIRLS] + [("Club Name", "Club Name"), (self.DOUBLE, self.DOUBLE)]
                          + list(extra), {"es": {"Club Name": "Nombre del club"}},
                          pad=fix_name_translations.STORE_FLOOR)

    def fake(self, **kw):
        return FakeStoreClient(self.questions(), {fid: self.store() for fid in fix_name_translations.ORDER}, **kw)

    def run_main(self, fake, *argv, page=None):
        """(exit code or message, stdout) of main() on `fake`; page(fid): the public page."""
        import contextlib
        import io
        from unittest import mock
        out = io.StringIO()
        page = page or (lambda fid: served_page(fake.stores[fid]))
        with mock.patch.object(fix_name_translations, "Client", lambda key, apply=False: fake), \
                mock.patch.object(fix_name_translations, "public_page", page), \
                mock.patch.object(fix_name_translations.time, "sleep", lambda s: None), \
                mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}), \
                mock.patch.object(sys, "argv", ["fix_name_translations.py", *argv]), \
                contextlib.redirect_stdout(out):
            try:
                fix_name_translations.main()
                code = 0
            except SystemExit as e:
                code = e.code
        for name in self.GIRLS + [self.DOUBLE]:          # counts and club names only, ever
            self.assertNotIn(name, out.getvalue() + str(code))
        return code, out.getvalue()

    def saved(self):
        folder = os.path.join(self.tmp.name, "backups", "translations")
        return sorted(os.path.join(folder, f) for f in os.listdir(folder)) if os.path.isdir(folder) else []

    def test_the_dry_run_counts_and_names_clubs_never_girls(self):
        fake = self.fake()
        code, out = self.run_main(fake)
        self.assertEqual((code, fake.writes), (0, []))
        self.assertIn("Roster options read from all five forms: template 5, U.S 1, Latin America 1, Asia 1, "
                      "Africa 2 (5 distinct texts)", out)
        africa = out.split(f"== Africa {self.AFRICA}", 1)[1]
        self.assertIn("altered today: 1 of this form's 2 roster options, in 1 club(s); its dictionary alters 1 "
                      "option text(s) of the five forms (en 1; on template 1, U.S 0, Latin America 0, Asia 0, "
                      "Africa 1)", africa)
        self.assertIn("clubs: Sunrise Club", africa)
        self.assertEqual(out.count("keys to remove: 1 (base 1, en 1)"), 5)      # every form: all five count
        self.assertEqual(out.count("both runtime builds): 0 option(s) altered"), 5)
        us = out.split("== U.S", 1)[1].split("==", 1)[0]
        self.assertIn("altered today: 0 of this form's 1 roster options;", us)
        self.assertIn("properties[pagetitle] = 'Africa title'", africa)
        self.assertIn("DRY RUN", out)
        # the other forms' options are what make the U.S store's entry go
        options = {fid: opts for fid, opts in fix_name_translations.read_options(fake).items()
                   if glow_forms.LIVE[fid] == "U.S"}
        self.assertEqual(fix_name_translations.plan_form(self.store(), options)["keys"], set())

    def test_every_refusal_writes_nothing(self):
        from unittest import mock
        options = fix_name_translations.read_options(self.fake())

        def refusals(store):
            return " | ".join(fix_name_translations.plan_form(store, options)["refusals"])

        good = self.store()
        self.assertEqual(refusals(good), "")
        self.assertIn("no 'en' dictionary", refusals({k: v for k, v in good.items() if k != "en"}))
        self.assertIn("no 'base' dictionary", refusals({k: v for k, v in good.items() if k != "base"}))
        self.assertIn("below 1000 (a truncated read?)", refusals(name_store([(self.DOUBLE, self.DOUBLE)])))
        bad = copy.deepcopy(good)
        bad["es"]["x"] = 7
        self.assertIn("1 entry is not text", refusals(bad))
        translated = copy.deepcopy(good)
        translated["es"][md5(self.DOUBLE)] = "Amara (es)"
        self.assertIn("another language's entries", refusals(translated))
        with mock.patch.object(fix_name_translations, "MAX_KEYS", 0):
            self.assertIn("1 keys to remove, more than 0", refusals(good))
        with mock.patch.object(fix_name_translations.tl, "removal", lambda *a, **k: (set(), None)):
            self.assertIn("1 option(s) would still be altered after the removal", refusals(good))
        # through main: refused forms are named, nothing is written, --apply included
        fake = self.fake()
        fake.stores[self.AFRICA]["es"][md5(self.DOUBLE)] = "Amara (es)"
        for argv in ((), ("--form", self.AFRICA, "--apply")):
            code, out = self.run_main(fake, *argv)
            self.assertIn("Refused, nothing written: ", str(code))
            self.assertIn("REFUSED: ", out)
            self.assertEqual(fake.writes, [])
        for argv, says in (((("--apply",)), "exactly one --form"),
                           (("--form", self.AFRICA, "--form", glow_forms.TEMPLATE, "--apply"), "exactly one --form"),
                           (("--restore", "x.json"), "exactly one --form"),
                           (("--form", "123"), "Not one of the five forms: 123")):
            code, _ = self.run_main(self.fake(), *argv)
            self.assertIn(says, str(code), argv)
        code, _ = self.run_main(self.fake(primary="es"), "--form", self.AFRICA)
        self.assertIn("primaryLanguage is 'es'", str(code))

    def test_the_write_saves_the_store_first_posts_base_and_en_only_and_verifies(self):
        on_disk = []
        fake = self.fake(before_post=lambda: on_disk.append(self.saved()))
        before = copy.deepcopy(fake.stores[self.AFRICA])
        code, out = self.run_main(fake, "--form", self.AFRICA, "--apply")
        self.assertEqual(code, 0, out)
        (path, payload, label), = fake.writes
        self.assertEqual(path, f"/form/{self.AFRICA}/translations")
        self.assertEqual(set(payload), {"base", "en"})                       # no other language posted
        for lang in ("base", "en"):
            self.assertEqual(payload[lang], {k: v for k, v in before[lang].items() if k != md5(self.DOUBLE)})
        self.assertEqual(fake.stores[self.AFRICA]["es"], before["es"])
        # saved before the POST, whole, readable by its owner only
        self.assertEqual(len(on_disk[0]), 1)
        with open(on_disk[0][0], encoding="utf-8") as f:
            self.assertEqual(json.load(f), before)
        self.assertEqual(os.stat(on_disk[0][0]).st_mode & 0o777, 0o600)
        self.assertTrue(os.path.basename(on_disk[0][0]).startswith(f"{self.AFRICA}-"))
        for line in ("re-read: APPLIED", "audit of the re-read store: 0 of this form's roster options altered",
                     "public page: 0 removed keys still served"):
            self.assertIn(line, out)
        # the other forms are untouched; a second run has nothing to remove on this one
        self.assertEqual(fake.stores[glow_forms.TEMPLATE], self.store())
        code, out = self.run_main(fake, "--form", self.AFRICA)
        self.assertIn("nothing to remove", out)

    def test_a_lost_or_failed_answer_is_re_read_never_guessed(self):
        code, out = self.run_main(self.fake(mode="lose"), "--form", self.AFRICA, "--apply")
        self.assertEqual(code, 0)
        self.assertIn("answer to the POST was lost or not JSON - re-reading", out)
        self.assertIn("re-read: APPLIED - despite the lost answer", out)
        fake = self.fake(mode="nothing")
        code, out = self.run_main(fake, "--form", self.AFRICA, "--apply")
        self.assertIn("re-read: UNCHANGED", out)
        self.assertIn("the store reads unchanged after the POST. Nothing was written; run again.", str(code))
        self.assertEqual(fake.stores[self.AFRICA], self.store())
        code, out = self.run_main(self.fake(mode="partial"), "--form", self.AFRICA, "--apply")
        self.assertIn("re-read: PARTIAL (en: 0 entr(ies) missing, 1 that should be gone, 0 changed)", out)
        self.assertIn(f"--form {self.AFRICA} --restore backups/translations/{self.AFRICA}-", str(code))
        from glow.jotform import JotformError
        # the re-read itself fails: it never says "nothing written", and it names the saved store
        fake = self.fake()
        real_get = fake.get

        def get_after_post(path, **params):
            if fake.writes and path.endswith("/translations"):
                raise JotformError("GET: a cut-off JSON answer, 900 characters, not shown")
            return real_get(path, **params)
        fake.get = get_after_post
        code, _ = self.run_main(fake, "--form", self.AFRICA, "--apply")
        self.assertIn("the write may or may not have happened", str(code))
        self.assertIn(f"the store before the POST is backups/translations/{self.AFRICA}-", str(code))
        self.assertNotIn("nothing written", str(code))

        class Failing:
            def get(self, path, **params):
                raise JotformError("GET: a cut-off JSON answer")
        with self.assertRaises(SystemExit) as cm:
            fix_name_translations.get(Failing(), "/form/1/translations", "the store")
        self.assertEqual(str(cm.exception.code), "Could not read the store (an error or a non-JSON answer from "
                                                 "Jotform) - nothing written; run again")

    def test_a_page_still_serving_a_removed_key_is_re_rendered_once(self):
        fake = self.fake()
        old = copy.deepcopy(fake.stores[self.AFRICA])
        reads = []

        def page(fid):          # Jotform's cache: the old store for PAGE_TRIES reads
            reads.append(fid)
            return served_page(old if len(reads) <= fix_name_translations.PAGE_TRIES else fake.stores[fid])

        code, out = self.run_main(fake, "--form", self.AFRICA, "--apply", page=page)
        self.assertEqual(code, 0, out)
        self.assertEqual([w[0] for w in fake.writes], [f"/form/{self.AFRICA}/translations",
                                                       f"/form/{self.AFRICA}/properties"])
        self.assertEqual(fake.writes[1][1], {"properties[pagetitle]": "Africa title"})
        for line in ("public page: 1 removed keys still served - re-rendering it", "pagetitle re-read: unchanged",
                     "public page: 0 removed keys still served"):
            self.assertIn(line, out)
        # a page that never follows, or cannot be read: the write stands, the run says to check
        for page, says in ((lambda fid: served_page(old), "public page: 1 removed keys still served"),
                           (lambda fid: "<html></html>", "could not read its embedded store")):
            code, out = self.run_main(self.fake(), "--form", self.AFRICA, "--apply", page=page)
            self.assertIn("could not be shown to serve it", str(code))
            self.assertIn(says, out)

    def test_a_re_read_with_another_language_changed_or_no_store_is_partial(self):
        # CLAUDE.md rule 9: a POST that changed a language it was not sent is never "applied"
        fake = self.fake(mode="clobber")
        code, out = self.run_main(fake, "--form", self.AFRICA, "--apply")
        self.assertIn("re-read: PARTIAL (other languages changed: es)", out)
        self.assertIn(f"Stopped: the store reads partial after the POST. Put it back: --form {self.AFRICA} "
                      f"--restore backups/translations/{self.AFRICA}-", str(code))
        self.assertNotIn("audit of the re-read store", out)
        code, out = self.run_main(self.fake(mode="notstore"), "--form", self.AFRICA, "--apply")
        self.assertIn("re-read: PARTIAL (the re-read store is not a translation store)", out)
        self.assertIn("Stopped: the store reads partial after the POST", str(code))
        # the restore's POST too
        fake, earlier = self.fake(), set(self.saved())
        self.assertEqual(self.run_main(fake, "--form", self.AFRICA, "--apply")[0], 0)
        (saved,) = set(self.saved()) - earlier
        fake.mode = "clobber"
        code, out = self.run_main(fake, "--form", self.AFRICA, "--restore", saved, "--apply")
        self.assertIn("re-read: PARTIAL (other languages changed: es)", out)
        self.assertIn("Stopped: the store reads partial after the restore POST - compare it with "
                      f"backups/translations/{self.AFRICA}-", str(code))
        self.assertNotIn("public page:", out)

    def test_the_audit_of_the_re_read_store_stops_the_run(self):
        import contextlib
        import io
        # a plan that missed a stale spelling (the tab one): the POST lands as planned, the
        # audit of the re-read store still finds the name altered and stops before the page
        tab = "Amara\tFennwhistle"
        fake = self.fake()
        store = self.store(extra=[(tab, tab)])
        fake.stores[self.AFRICA] = copy.deepcopy(store)
        plan = {"keys": {md5(self.DOUBLE)}, "refusals": []}
        out, pages = io.StringIO(), []
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as cm:
            fix_name_translations.apply_form(fake, self.AFRICA, store, plan, fix_name_translations.read_options(fake),
                                             "s", page_of=lambda fid: pages.append(fid) or "", sleep=lambda s: None)
        self.assertIn("Stopped: the re-read store still alters roster options", str(cm.exception.code))
        self.assertIn("re-read: APPLIED", out.getvalue())
        self.assertIn("audit of the re-read store: 1 of this form's roster options altered, 1 option text(s) "
                      "of the five forms", out.getvalue())
        self.assertEqual(pages, [])
        for name in self.GIRLS + [self.DOUBLE, tab]:
            self.assertNotIn(name, out.getvalue() + str(cm.exception.code))

    def test_a_restore_with_nothing_to_put_back_or_no_store_writes_nothing(self):
        fake = self.fake()
        same = os.path.join(self.tmp.name, "backups", "translations", f"{self.AFRICA}-same-before.json")
        os.makedirs(os.path.dirname(same))
        with open(same, "w", encoding="utf-8") as f:
            json.dump(fake.stores[self.AFRICA], f)
        code, out = self.run_main(fake, "--form", self.AFRICA, "--restore", same, "--apply")
        self.assertEqual((code, fake.writes), (0, []))
        self.assertIn("base: 0 entr(ies) put back", out)
        self.assertIn("nothing to restore", out)
        fake.stores[self.AFRICA] = ["not", "a", "store"]
        code, out = self.run_main(fake, "--form", self.AFRICA, "--restore", same, "--apply")
        self.assertIn("Refused, nothing written: the form's store: not a translation store", str(code))
        self.assertEqual(fake.writes, [])

    def test_the_re_render_failing_after_the_post_never_says_nothing_written(self):
        from glow.jotform import JotformError
        stale_page = None

        def failing(fake, step):
            """fake with the re-render's `step` failing once the store POST has landed:
            "props" the first properties read, "post" the pagetitle POST, "again" its re-read."""
            real_get, real_post = fake.get, fake.post_form
            reads = []

            def get(path, **params):
                if fake.writes and path.endswith("/properties"):
                    reads.append(path)
                    if step == "props" or (step == "again" and len(reads) == 2):
                        raise JotformError("GET: a cut-off JSON answer, 900 characters, not shown")
                return real_get(path, **params)

            def post_form(path, data, label):
                real_post(path, data, label)
                if step == "post":
                    raise JotformError(f"{label}: non-JSON response")
            fake.get, fake.post_form = get, post_form
            return fake

        for step in ("props", "post", "again"):
            fake = self.fake()
            stale_page = served_page(copy.deepcopy(fake.stores[self.AFRICA]))     # the page never follows
            code, out = self.run_main(failing(fake, step), "--form", self.AFRICA, "--apply",
                                      page=lambda fid, stale_page=stale_page: stale_page)
            self.assertIn("re-read: APPLIED", out, step)
            self.assertNotIn(md5(self.DOUBLE), fake.stores[self.AFRICA]["en"])       # the store is written
            self.assertIn("The store is fixed but the public page could not be shown to serve it", str(code), step)
            self.assertNotIn("nothing written", str(code) + out, step)
            self.assertIn("the re-render could not be done or confirmed", out, step)
            self.assertNotIn("cut-off", out + str(code))                             # Jotform's answer never echoed
        # the restore: the same accurate exit after its POST
        fake, earlier = self.fake(), set(self.saved())
        self.assertEqual(self.run_main(fake, "--form", self.AFRICA, "--apply")[0], 0)
        (saved,) = set(self.saved()) - earlier
        stale_page = served_page(copy.deepcopy(fake.stores[self.AFRICA]))           # without the restored key
        fake.writes.clear()
        code, out = self.run_main(failing(fake, "props"), "--form", self.AFRICA, "--restore", saved, "--apply",
                                  page=lambda fid: stale_page)
        self.assertIn("re-read: APPLIED", out)
        self.assertIn(md5(self.DOUBLE), fake.stores[self.AFRICA]["en"])
        self.assertIn("Restored, but the public page could not be shown to serve it", str(code))
        self.assertNotIn("nothing written", str(code) + out)

    def test_the_restore_puts_back_what_was_removed_in_the_saved_order(self):
        fake = self.fake()
        original = copy.deepcopy(fake.stores[self.AFRICA])
        self.assertEqual(self.run_main(fake, "--form", self.AFRICA, "--apply")[0], 0)
        (saved,) = self.saved()
        fake.stores[self.AFRICA]["en"]["k-new"] = "Added Since"            # kept by the restore
        fake.stores[self.AFRICA]["en"][md5("Label 0000")] = "Label zero"   # changed since: kept too
        fake.writes.clear()
        code, out = self.run_main(fake, "--form", self.AFRICA, "--restore", saved)
        self.assertEqual((code, fake.writes), (0, []))
        self.assertIn("base: 1 entr(ies) put back; 0 changed since and 0 added since", out)
        self.assertIn("en: 1 entr(ies) put back; 1 changed since and 1 added since", out)
        self.assertIn("after the restore: 1 of this form's roster options altered again, in 1 club(s)", out)
        code, out = self.run_main(fake, "--form", self.AFRICA, "--restore", saved, "--apply")
        self.assertEqual(code, 0, out)
        (_, payload, _), = fake.writes
        self.assertEqual(set(payload), {"base", "en"})
        self.assertEqual(list(payload["base"]), list(original["base"]))
        self.assertEqual(list(payload["en"]), list(original["en"]) + ["k-new"])
        self.assertEqual(payload["en"][md5("Label 0000")], "Label zero")     # not the saved text
        self.assertEqual(payload["base"][md5("Label 0000")], "Label 0000")
        self.assertIn("public page: 0 restored keys not yet served", out)
        self.assertEqual(len(self.saved()), 2)                               # the store before the restore too
        # refusals: another form's file, a truncated one
        other = os.path.join(os.path.dirname(saved), f"{glow_forms.TEMPLATE}-x-before.json")
        with open(other, "w", encoding="utf-8") as f:
            json.dump(original, f)
        code, _ = self.run_main(self.fake(), "--form", self.AFRICA, "--restore", other, "--apply")
        self.assertIn("is not a saved store of form", str(code))
        short = os.path.join(os.path.dirname(saved), f"{self.AFRICA}-short-before.json")
        with open(short, "w", encoding="utf-8") as f:
            json.dump(name_store([(self.DOUBLE, self.DOUBLE)]), f)
        code, _ = self.run_main(self.fake(), "--form", self.AFRICA, "--restore", short, "--apply")
        self.assertIn("below 1000", str(code))


if __name__ == "__main__":
    unittest.main(verbosity=1)
