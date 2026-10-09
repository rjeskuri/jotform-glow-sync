#!/usr/bin/env python3
"""
The link elements and the roster layout on fake forms: tools/update_static_fields.py's header
logo (HeaderImage), glow/links.py (Links), tools/add_feedback_link.py (LinkTool),
tools/add_translations.py's plan (TranslationPlan), glow/layout.py (RosterLayout) and
tools/fix_roster_order.py (FixRosterOrderTool).
"""
import copy
import json
import os
import re
import struct
import sys
import unittest

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import REPO, SameNameFixture, create_at, link_form, move_all, read, rendered
import add_feedback_link
import add_language
import add_translations
import fix_roster_order
import sync_attendance_form as sync
import update_static_fields
from glow import forms as glow_forms
from glow import layout
from glow import links
from glow import sync as glow_sync
from glow.text import md5


class HeaderImage(unittest.TestCase):
    """tools/update_static_fields.py: the header-logo field and its URL guard."""

    @staticmethod
    def png(width, height):
        return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
                + struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))

    def fetch(self, status="200", content_type="image/png", head=None):
        return lambda url: (status, content_type, self.png(410, 206) if head is None else head)

    def test_png_size_reads_the_ihdr_and_rejects_other_bytes(self):
        self.assertEqual(update_static_fields.png_size(self.png(410, 206)), (410, 206))
        self.assertIsNone(update_static_fields.png_size(b"GIF89a" + b"\0" * 40))
        self.assertIsNone(update_static_fields.png_size(b""))

    def test_the_image_field_is_left_alone_without_a_url(self):
        fields = update_static_fields.wanted_fields()
        self.assertEqual(set(fields), {"mentorEmail", "photo"})
        self.assertEqual(fields, update_static_fields.WANTED)
        fields["photo"] = {}                       # a copy, not the constant
        self.assertNotEqual(update_static_fields.WANTED["photo"], {})

    def test_the_image_field_carries_the_url_size_and_derived_name(self):
        url = "https://www.jotform.com/uploads/Someone/form_files/logo-2x.png?v=3"
        image = update_static_fields.wanted_fields(url)[update_static_fields.IMAGE_FIELD]
        self.assertEqual(image["src"], url)
        self.assertEqual(image["text"], "logo-2x")          # basename, no extension, no query
        self.assertEqual((image["width"], image["height"]), ("205", "103"))
        self.assertEqual(image["align"], "Center")
        # 205x103 keeps the replaced banner's height and the new logo's own shape
        self.assertEqual(int(image["height"]), 103)
        self.assertAlmostEqual(int(image["width"]) / int(image["height"]), 1.99, places=1)

    def test_check_src_accepts_a_2x_png_and_describes_it(self):
        line = update_static_fields.check_src("https://x.test/logo.png", self.fetch())
        self.assertIn("410x206", line)
        self.assertIn("205x103", line)
        self.assertIn("2x", line)

    def test_check_src_refuses_what_a_browser_could_not_load(self):
        for url, fetch in (
            ("http://x.test/logo.png", self.fetch()),                       # not https
            ("https://x.test/logo.png", self.fetch(status="404")),          # missing
            ("https://x.test/logo.png", self.fetch(content_type="text/html")),
            ("https://x.test/logo.png", self.fetch(head=self.png(100, 50))),  # too small
        ):
            with self.assertRaises(SystemExit):
                update_static_fields.check_src(url, fetch)

    def test_check_src_passes_a_non_png_image_through(self):
        line = update_static_fields.check_src(
            "https://x.test/logo.svg", self.fetch(content_type="image/svg+xml", head=b"<svg/>"))
        self.assertIn("image/svg+xml", line)

    def test_the_committed_header_asset_is_big_enough_to_display(self):
        path = os.path.join(REPO, "assets", "global-catalyst-header.png")
        self.assertTrue(os.path.exists(path), path)
        with open(path, "rb") as f:
            size = update_static_fields.png_size(f.read(64))
        self.assertIsNotNone(size, "the header asset must be a PNG")
        props = update_static_fields.IMAGE_PROPS
        self.assertEqual(size, (int(props["width"]) * 2, int(props["height"]) * 2))


def apply_steps(questions, steps):
    """What add_feedback_link's steps do to a form, the way the API does it."""
    qs = copy.deepcopy(questions)
    for s in steps:
        if s["op"] == "delete":
            del qs[str(s["qid"])]
        elif s["op"] == "add":
            qid = str(max(int(k) for k in qs) + 1)
            qs[qid] = {"qid": qid, **s["fields"]}
        else:
            qs[str(s["qid"])].update(s["fields"])
    return qs


class FakeFormClient:
    """Jotform for add_feedback_link.main(): GETs serve the in-memory forms and
    writes change them as the API would."""

    def __init__(self, forms):
        self.forms, self.writes = forms, []

    def get(self, path, **params):
        fid, part = re.fullmatch(r"/form/(\d+)/(questions|properties)", path).groups()
        return copy.deepcopy(self.forms[fid]) if part == "questions" else {"conditions": []}

    def post_form(self, path, data, label):
        self.writes.append(label)
        fields = {re.fullmatch(r"question\[(\w+)\]", k).group(1): v for k, v in data.items()}
        m = re.fullmatch(r"/form/(\d+)/questions", path)
        if m:
            qs = self.forms[m.group(1)]
            qid = str(max(int(k) for k in qs) + 1)
            qs[qid] = {"qid": qid, **fields}
            return {"qid": qid}
        fid, qid = re.fullmatch(r"/form/(\d+)/question/(\d+)", path).groups()
        self.forms[fid][qid].update(fields)
        return {}

    def delete(self, path, label):
        self.writes.append(label)
        fid, qid = re.fullmatch(r"/form/(\d+)/question/(\d+)", path).groups()
        del self.forms[fid][qid]


class Links(unittest.TestCase):
    """glow/links.py: the element table, its HTML, the URL guard, rule lookup."""

    def test_the_problem_link_html_is_byte_identical_to_the_live_element(self):
        # q443 as read from all five live forms on 2026-09-28: a change here would
        # re-key its translations (md5 of the HTML) and rewrite a live element
        live = ('<p style="margin:12px 0;padding:10px 12px;border:1px solid #ddd;'
                'border-radius:6px;background:#f7f7f7;font-size:14px"><a href="'
                'https://docs.google.com/forms/d/e/1FAIpQLSeYx286-Bre0aSOWnhEDgC4_6FjGyPssldLA3J5WzIeK8cKCA'
                '/viewform" target="_blank" rel="noopener">Click here to report a problem</a></p>')
        self.assertEqual(links.element_html(links.PROBLEM.sentence, links.PROBLEM.url), live)
        self.assertEqual(links.href_of(live), links.PROBLEM_FORM_URL)

    def test_the_urls_are_the_public_links_in_the_runbook(self):
        rows = dict(re.findall(r"^\| (.+?) \| (https://\S+) \|$",
                               read(os.path.join(REPO, "docs", "RUNBOOK.md")), re.M))
        roster = [u for label, u in rows.items() if label.startswith("Club Roster Form")]
        problem = [u for label, u in rows.items() if label.startswith("Something")]
        self.assertEqual(roster, [links.ROSTER_FORM_URL])
        self.assertEqual(problem, [links.PROBLEM_FORM_URL])
        self.assertEqual(links.ROSTER.url, links.ROSTER_FORM_URL)
        self.assertNotEqual(links.ROSTER_FORM_URL, links.PROBLEM_FORM_URL)

    def test_the_table(self):
        self.assertEqual(set(links.LINKS), {"problem", "roster"})
        self.assertEqual(links.ROSTER.above, links.PROBLEM.name)   # the specific path first
        self.assertEqual(links.PROBLEM.above, links.SUBMIT)
        self.assertEqual(len(links.BY_NAME), len(links.LINKS))
        for link in links.LINKS.values():
            self.assertEqual(link.sentence, link.sentence.strip())
            self.assertFalse(set("&<>\"") & set(link.sentence), link.sentence)

    def test_only_a_public_form_link_is_accepted(self):
        for url in (links.ROSTER_FORM_URL, links.PROBLEM_FORM_URL,
                    links.ROSTER_FORM_URL + "?usp=sf_link", "https://forms.gle/AbCdEf123"):
            self.assertEqual(links.check_public_url(url), url)
        for url in (links.ROSTER_FORM_URL.replace("/viewform", "/edit"),       # owner's edit link
                    "https://docs.google.com/forms/d/" + "1" + "x" * 43 + "/edit",
                    links.ROSTER_FORM_URL.replace("https://", "http://"),
                    "https://example.org/forms/d/e/" + "x" * 30 + "/viewform",
                    links.ROSTER_FORM_URL + '"><b>', links.ROSTER_FORM_URL + " ", "", None):
            with self.assertRaises(SystemExit, msg=url):
                links.check_public_url(url)

    def test_rules_mentioning(self):
        conds = [{"id": "1", "terms": json.dumps([{"field": "443", "operator": "isFilled"}]),
                  "action": json.dumps([{"visibility": "Show", "field": "350"}])},
                 {"id": "2", "terms": [], "action": [{"resultField": "18", "operands": "350,460",
                                                      "equation": "{350}{460}"}]},
                 {"id": "3", "terms": [{"field": "4430"}], "action": [{"field": "44"}]}]
        self.assertEqual(links.rules_mentioning(conds, "443"), ["1"])
        self.assertEqual(links.rules_mentioning(conds, "460"), ["2"])
        self.assertEqual(links.rules_mentioning(conds, 350), ["1", "2"])
        self.assertEqual(links.rules_mentioning(conds, "44"), ["3"])
        self.assertEqual(links.rules_mentioning(conds, "4"), [])
        self.assertEqual(links.rules_mentioning(None, "4"), [])
        self.assertEqual(links.shown_by_rules(conds), {"350"})
        for broken in ({"id": "9", "terms": "{broken", "action": "[]"}, {"id": "9", "terms": [], "action": 5}):
            with self.subTest(broken=broken):
                with self.assertRaises(ValueError) as stop:
                    links.rules_mentioning(conds + [broken], "4")
                self.assertIn("rule 9: its terms or action do not parse", str(stop.exception))
                with self.assertRaises(ValueError):
                    links.shown_by_rules([broken])


class LinkTool(unittest.TestCase):
    """tools/add_feedback_link.py: placement, idempotence, removal, refusals."""

    R, P = links.ROSTER, links.PROBLEM

    def plan(self, qs, link, url=None, conditions=(), remove=False):
        return add_feedback_link.plan_form(qs, list(conditions), link, url or link.url, remove)

    def test_the_roster_link_goes_directly_above_the_problem_link(self):
        qs = link_form()
        steps, _ = self.plan(qs, self.R)
        self.assertEqual([(s["op"], s["qid"]) for s in steps],
                         [("move", "2"), ("move", "443"), ("add", None)])   # tail first
        self.assertEqual(steps[2]["fields"]["order"], qs["443"]["order"])
        self.assertEqual(steps[2]["fields"]["type"], "control_text")
        self.assertNotIn("hidden", steps[2]["fields"])
        after = apply_steps(qs, steps)
        names = rendered(after)
        i = names.index(self.R.name)
        self.assertEqual(names[i:i + 3], [self.R.name, self.P.name, "submit2"])
        self.assertEqual([n for n in names if n != self.R.name], rendered(qs))  # nothing else moves
        self.assertEqual(add_feedback_link.verify(after, [], self.R, self.R.url), [])
        self.assertEqual(add_feedback_link.verify(after, [], self.P, self.P.url), [])
        for n in range(1, len(steps)):   # every intermediate state still renders in order
            part = rendered(apply_steps(qs, steps[:n]))
            self.assertLess(part.index(self.P.name), part.index("submit2"))
        again, notes = self.plan(after, self.R)
        self.assertEqual(again, [])                                     # a re-run is a no-op
        self.assertIn("already present", notes[-1])

    def test_without_the_problem_link_it_sits_above_submit_and_the_problem_link_goes_between(self):
        qs = link_form(problem=False)
        steps, _ = self.plan(qs, self.R)
        self.assertEqual([s["op"] for s in steps], ["move", "add"])
        after = apply_steps(qs, steps)
        steps, _ = self.plan(after, self.P)
        after = apply_steps(after, steps)
        seen = [q["name"] for q in sorted(after.values(), key=links.render_key)
                if links.can_appear(q, set())]      # the hidden q103 header may sit between
        i = seen.index(self.R.name)
        self.assertEqual(seen[i:i + 3], [self.R.name, self.P.name, "submit2"])
        self.assertEqual(add_feedback_link.verify(after, [], self.R, self.R.url), [])
        self.assertEqual(add_feedback_link.verify(after, [], self.P, self.P.url), [])

    def test_remove_deletes_only_its_own_element(self):
        qs = link_form(roster=True)
        steps, _ = self.plan(qs, self.R, remove=True)
        self.assertEqual([(s["op"], s["qid"]) for s in steps], [("delete", "460")])
        after = apply_steps(qs, steps)
        self.assertEqual(add_feedback_link.verify(after, [], self.R, self.R.url, removed=True), [])
        self.assertEqual(add_feedback_link.verify(after, [], self.P, self.P.url), [])
        steps, notes = self.plan(after, self.R, remove=True)
        self.assertEqual(steps, [])
        self.assertIn("nothing to remove", notes[0])

    def test_a_changed_or_hidden_element_is_updated_in_place(self):
        qs = link_form(roster=True)
        qs["460"]["text"] = links.element_html(self.R.sentence, self.R.url + "?usp=old")
        qs["460"]["hidden"] = "Yes"
        steps, _ = self.plan(qs, self.R)
        self.assertEqual([(s["op"], s["qid"]) for s in steps], [("update", "460")])
        self.assertEqual(steps[0]["fields"], {"text": links.element_html(self.R.sentence, self.R.url),
                                              "hidden": "No"})
        self.assertEqual(add_feedback_link.verify(apply_steps(qs, steps), [], self.R, self.R.url), [])

    def test_it_refuses_rather_than_guessing(self):
        stray = link_form(stray=("470", "control_textbox", "somethingElse", {}))
        two_buttons = link_form()
        two_buttons["471"] = {"qid": "471", "type": "control_button", "name": "b2", "order": "30"}
        twice = link_form(roster=True)
        twice["472"] = dict(twice["460"], qid="472", order="31")
        below = link_form()
        below["443"]["order"] = "99"
        shown = link_form(stray=("470", "control_dropdown", "extra", {"hidden": "Yes"}))
        rule = [{"id": "7", "terms": [], "action": [{"visibility": "Show", "field": "470"}]}]
        tied = link_form()   # a roster sharing Submit's order renders after it, until Submit moves
        tied["480"] = {"qid": "480", "type": "control_checkbox", "name": "TiedClub",
                       "hidden": "Yes", "order": tied["2"]["order"]}
        for qs, link, url, conds in ((stray, self.R, None, ()), (two_buttons, self.R, None, ()),
                                     (twice, self.R, None, ()), (below, self.R, None, ()),
                                     (link_form(), self.R, self.P.url, ()),   # the other link's form
                                     (shown, self.R, None, rule),             # hidden, but a rule shows it
                                     (tied, self.R, None, ())):               # would land between the links
            with self.assertRaises(SystemExit):
                self.plan(qs, link, url, conditions=conds)
        # a hidden field no rule shows may sit in the run: it moves along
        quiet = link_form(stray=("470", "control_textbox", "bridge", {"hidden": "Yes"}))
        steps, _ = self.plan(quiet, self.R)
        self.assertEqual([s["qid"] for s in steps], ["2", "470", "443", None])

    def test_a_submit_tied_with_a_hidden_field_does_not_block_the_next_insert(self):
        # after an insert, Submit shares its order with the hidden q103 header
        # (Submit, the older, renders first): a later insert still plans cleanly
        qs = link_form(problem=False)
        after = apply_steps(qs, self.plan(qs, self.R)[0])
        self.assertEqual(after["2"]["order"], after["103"]["order"])
        after = apply_steps(after, self.plan(after, self.P)[0])
        visible = [n for n in rendered(after) if n in (self.R.name, self.P.name, "submit2")]
        self.assertEqual(visible, [self.R.name, self.P.name, "submit2"])

    def test_verify_catches_what_would_hide_or_misplace_it(self):
        qs = link_form(roster=True)
        self.assertEqual(add_feedback_link.verify(qs, [], self.R, self.R.url), [])
        rule = [{"id": "9", "terms": [{"field": sync.YEAR, "operator": "equals", "value": "1"}],
                 "action": [{"visibility": "Show", "field": "460"}]}]
        self.assertTrue(any("rule(s) 9" in p for p in add_feedback_link.verify(qs, rule, self.R, self.R.url)))
        _, notes = self.plan(qs, self.R, conditions=rule)
        self.assertTrue(any("rule 9" in n for n in notes))
        hidden = copy.deepcopy(qs)
        hidden["460"]["hidden"] = "Yes"
        self.assertIn("it is hidden", add_feedback_link.verify(hidden, [], self.R, self.R.url))
        low = copy.deepcopy(qs)
        low["460"]["order"] = "99"
        self.assertTrue(any("not above" in p for p in add_feedback_link.verify(low, [], self.R, self.R.url)))

    def run_main(self, fake, *argv, clock=None):
        """(snapshotted form ids, stdout); the stamps the snapshots were given
        land in self.stamps. `clock` stands in for datetime (its now())."""
        import contextlib
        import io
        from unittest import mock
        snaps, out, self.stamps = [], io.StringIO(), []

        def snapshot(fid, client, stamp):
            snaps.append(fid)
            self.stamps.append(stamp)
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(add_feedback_link, "Client",
                                                  lambda key, apply=False: fake))
            stack.enter_context(mock.patch.object(add_feedback_link.backup, "snapshot", snapshot))
            stack.enter_context(mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}))
            stack.enter_context(mock.patch.object(sys, "argv", ["add_feedback_link.py", *argv]))
            if clock:
                stack.enter_context(mock.patch.object(add_feedback_link, "datetime", clock))
            stack.enter_context(contextlib.redirect_stdout(out))
            add_feedback_link.main()
        return snaps, out.getvalue()

    def test_apply_snapshots_first_writes_tail_first_and_verifies(self):
        from glow import forms as glow_forms
        fid = glow_forms.TEMPLATE
        fake = FakeFormClient({fid: link_form()})
        snaps, out = self.run_main(fake, "--link", "roster", "--form", fid)   # dry run
        self.assertEqual((snaps, fake.writes), ([], []))
        self.assertIn("3. ADD clubRosterFormLink", out)
        snaps, out = self.run_main(fake, "--link", "roster", "--form", fid, "--apply")
        self.assertEqual(snaps, [fid])
        self.assertEqual([w.split(" ", 2)[1] for w in fake.writes], ["move", "move", "ADD"])
        self.assertIn("re-read: verified", out)
        fake.writes.clear()
        snaps, out = self.run_main(fake, "--link", "roster", "--form", fid, "--apply")
        self.assertEqual((snaps, fake.writes), ([], []))                   # idempotent
        self.assertIn("already present", out)

    def test_a_changed_url_says_the_translations_must_be_re_applied(self):
        # every other language shows its copy of the element (keyed text_<qid>),
        # and that copy keeps the old link until add_translations.py runs again
        from glow import forms as glow_forms
        fid, new = glow_forms.TEMPLATE, "https://forms.gle/NewRosterForm1"
        fake = FakeFormClient({fid: link_form(roster=True)})
        _, notes = self.plan(fake.forms[fid], self.R, new)
        self.assertTrue(any("tools/add_translations.py --apply" in n for n in notes), notes)
        _, out = self.run_main(fake, "--link", "roster", "--url", new, "--form", fid, "--apply")
        self.assertEqual([w.split(" ", 2)[1] for w in fake.writes], ["UPDATE"])
        after = out.split("re-read: verified", 1)[1]
        self.assertIn("tools/add_translations.py --apply", after)
        self.assertIn("old link", after)
        _, out = self.run_main(fake, "--link", "roster", "--url", new, "--form", fid, "--apply")
        self.assertNotIn("add_translations", out)                          # nothing written, nothing to redo
        fresh = FakeFormClient({fid: link_form()})                         # a new element: English only until then
        _, out = self.run_main(fresh, "--link", "roster", "--form", fid, "--apply")
        self.assertIn("tools/add_translations.py --apply", out.split("re-read: verified", 1)[1])

    def test_a_hidden_anchor_or_submit_is_refused_not_a_traceback(self):
        hidden = link_form()
        hidden["443"]["hidden"] = "Yes"
        with self.assertRaises(SystemExit) as cm:
            self.plan(hidden, self.R)
        self.assertIn("hidden", str(cm.exception.code))
        self.assertIn("--link problem", str(cm.exception.code))
        rule = [{"id": "5", "terms": [], "action": [{"visibility": "Show", "field": "443"}]}]
        steps, _ = self.plan(hidden, self.R, conditions=rule)             # a rule shows it: fine
        self.assertEqual([s["op"] for s in steps], ["move", "move", "add"])
        no_button = link_form(problem=False)
        no_button["2"]["hidden"] = "Yes"
        with self.assertRaises(SystemExit) as cm:
            self.plan(no_button, self.R)
        self.assertIn("submit2 (q2)", str(cm.exception.code))

    def test_verify_and_the_plan_catch_the_anchor_below_submit(self):
        # the tail-first moves put Submit below the anchor first; a Submit move
        # acknowledged but not applied leaves the problem link under the button
        qs = link_form()
        steps, _ = self.plan(qs, self.R)
        self.assertEqual((steps[0]["op"], steps[0]["qid"]), ("move", "2"))
        partial = apply_steps(qs, steps[1:])
        self.assertEqual([n for n in rendered(partial) if n in (self.R.name, self.P.name, "submit2")],
                         [self.R.name, "submit2", self.P.name])
        problems = add_feedback_link.verify(partial, [], self.R, self.R.url)
        self.assertTrue(any(self.P.name in p and "submit2" in p for p in problems), problems)
        self.assertEqual(add_feedback_link.verify(apply_steps(qs, steps), [], self.R, self.R.url), [])
        below = link_form(roster=True)
        below["443"]["order"] = "99"
        steps, notes = self.plan(below, self.R)                            # present: flagged, not moved
        self.assertEqual(steps, [])
        self.assertTrue(any(self.P.name in n and "submit2" in n for n in notes), notes)

    def test_a_retry_in_the_same_minute_keeps_the_first_snapshot(self):
        # the pre-write snapshot is the rollback path: a re-run seconds after a
        # failed one must not write the half-changed form over it
        from datetime import datetime as real
        from glow import forms as glow_forms
        ticks = iter([real(2026, 9, 28, 10, 0, 5), real(2026, 9, 28, 10, 0, 40)])

        class Clock:
            @staticmethod
            def now():
                return next(ticks)
        fid, stamps = glow_forms.TEMPLATE, []
        for _ in range(2):
            self.run_main(FakeFormClient({fid: link_form()}), "--link", "roster", "--form", fid,
                          "--apply", clock=Clock)
            stamps += self.stamps
        self.assertEqual(len(stamps), 2)
        self.assertNotEqual(stamps[0], stamps[1])


class TranslationPlan(unittest.TestCase):
    """tools/add_translations.py plan_additions/merge and add_language's text-element keys."""

    OFFERED = {"es", "fr", "th", "ur", "te", "vi", "ne", "km", "sw", "ar", "or", "hi", "fa"}

    def setUp(self):
        self.additions = add_translations.load_additions()

    @staticmethod
    def store(*langs):
        return {**{lang: {} for lang in langs}, "base": {}, "en": {}}

    def test_the_roster_sentence_is_translated_for_every_offered_language(self):
        raw = json.loads(read(os.path.join(REPO, "tools", "translations_additions.json")))
        entry = raw[links.ROSTER.sentence]
        self.assertEqual(set(entry) - {"_note"}, self.OFFERED)
        self.assertIn("not native-reviewed", entry["_note"].lower())
        for lang in self.OFFERED:
            text = entry[lang]
            self.assertIn("Club Roster Form", text, lang)     # the form's own (English) name
            self.assertNotEqual(text, links.ROSTER.sentence, lang)
            self.assertFalse(set("&<>") & set(text), lang)
        self.assertIn(links.PROBLEM.sentence, raw)

    def test_both_link_elements_are_keyed_by_sentence_element_id_and_html(self):
        qs = link_form(roster=True)
        payload, sources = add_translations.plan_additions(qs, self.store("es", "hi"), self.additions)
        self.assertEqual(set(payload), {"es", "hi"})               # only what the form offers
        for qid, link in (("460", links.ROSTER), ("443", links.PROBLEM)):
            stored, text_id = qs[qid]["text"], f"text_{qid}"
            for lang in payload:
                if lang not in self.additions[link.sentence]:
                    continue
                want = self.additions[link.sentence][lang]
                html_t = payload[lang][md5(text_id)]
                self.assertEqual(payload[lang][md5(stored)], html_t)
                self.assertEqual(payload[lang][md5(link.sentence)], want)
                self.assertIn(want, html_t)
                self.assertNotIn(link.sentence, html_t)
                self.assertEqual(links.href_of(html_t), link.url)   # the link is untouched
            self.assertEqual(sources[md5(link.sentence)], link.sentence)
            self.assertEqual(sources[md5(text_id)], text_id)
            self.assertEqual(sources[md5(stored)], stored)
        self.assertIn(md5("text_460"), payload["hi"])              # Hindi reaches the new link
        self.assertNotIn(md5("text_443"), payload["hi"])           # its problem-link Hindi is add_language's

    def test_a_form_without_the_element_gets_none_of_its_keys(self):
        qs = link_form()
        payload, sources = add_translations.plan_additions(qs, self.store(*self.OFFERED), self.additions)
        keys = {k for d in payload.values() for k in d} | set(sources)
        self.assertNotIn(md5(links.ROSTER.sentence), keys)
        self.assertIn(md5(links.PROBLEM.sentence), keys)
        payload, _ = add_translations.plan_additions(link_form(roster=True), self.store("es", "fr"),
                                                     self.additions)
        self.assertFalse({"hi", "fa", "or"} & set(payload))       # a language the form lacks is never posted

    def test_merge_keeps_every_existing_entry_and_never_overwrites_a_source(self):
        qs = link_form(roster=True)
        store = self.store("es", "fr")
        store["es"]["k-existing"] = "ya estaba"
        store["fr"]["k-existing"] = "déjà là"
        store["base"][md5(links.ROSTER.sentence)] = "an older source text"
        store["base"]["k-roster-option"] = "Girl One"
        payload, sources = add_translations.plan_additions(qs, store, self.additions)
        merged = add_translations.merge(store, payload, sources)
        self.assertEqual(merged["es"]["k-existing"], "ya estaba")
        self.assertEqual(merged["fr"]["k-existing"], "déjà là")
        self.assertEqual(merged["base"]["k-roster-option"], "Girl One")
        self.assertEqual(merged["base"][md5(links.ROSTER.sentence)], "an older source text")
        self.assertEqual(merged["en"][md5(links.ROSTER.sentence)], links.ROSTER.sentence)
        self.assertEqual(merged["en"][md5("text_460")], "text_460")
        for lang in ("es", "fr"):
            self.assertLessEqual(set(store[lang]), set(merged[lang]))

    def test_add_language_keys_both_elements(self):
        qs = link_form(roster=True)
        base = {md5("text_460"): "text_460", md5(qs["460"]["text"]): qs["460"]["text"],
                md5("text_443"): "text_443", "k-roster-option": "Girl One"}
        words = {links.ROSTER.sentence: "RR", links.PROBLEM.sentence: "PP"}
        out = add_language.text_element_keys(qs, base, words)
        self.assertEqual(set(out), {md5("text_460"), md5(qs["460"]["text"]), md5("text_443")})
        self.assertEqual(out[md5("text_460")], qs["460"]["text"].replace(links.ROSTER.sentence, "RR"))
        self.assertEqual(out[md5("text_443")], qs["443"]["text"].replace(links.PROBLEM.sentence, "PP"))
        self.assertEqual(add_language.text_element_keys(qs, base, {links.PROBLEM.sentence: "PP"}),
                         {md5("text_443"): qs["443"]["text"].replace(links.PROBLEM.sentence, "PP")})

    def test_re_applying_after_a_url_change_replaces_every_languages_copy(self):
        # the remedy add_feedback_link.py names after it changes a link
        qs = link_form(roster=True)
        store = add_translations.merge(self.store("es", "fr"), *add_translations.plan_additions(
            qs, self.store("es", "fr"), self.additions))
        new = "https://forms.gle/NewRosterForm1"
        qs["460"]["text"] = links.element_html(links.ROSTER.sentence, new)
        store = add_translations.merge(store, *add_translations.plan_additions(qs, store, self.additions))
        for lang in ("es", "fr"):
            self.assertEqual(links.href_of(store[lang][md5("text_460")]), new, lang)
            self.assertEqual(links.href_of(store[lang][md5(qs["460"]["text"])]), new, lang)

    @staticmethod
    def guard_form():
        qs = link_form(roster=True)
        qs["700"] = {"qid": "700", "type": "control_text", "name": glow_sync.GUARD_NAME, "order": "3",
                     **glow_sync.GUARD_PROPS}
        return qs

    def test_the_guard_sentence_is_translated_for_every_offered_language(self):
        raw = json.loads(read(os.path.join(REPO, "tools", "translations_additions.json")))
        entry = raw[glow_sync.GUARD_SENTENCE]
        self.assertEqual(set(entry) - {"_note"}, self.OFFERED)
        self.assertIn("not native-reviewed", entry["_note"].lower())
        # it names the picker by its label in that language, as the mentor sees it
        label = dict(raw["Club Name"])
        for lang in ("or", "hi", "fa"):
            label[lang] = json.loads(read(os.path.join(REPO, "tools", f"translations_{lang}.json")))["Club Name"]
        for lang in self.OFFERED:
            text = entry[lang]
            self.assertIn(label[lang], text, lang)
            self.assertNotEqual(text, glow_sync.GUARD_SENTENCE, lang)
            self.assertFalse(set("&<>") & set(text), lang)

    def test_the_guard_is_keyed_by_sentence_element_id_and_html(self):
        qs = self.guard_form()
        payload, sources = add_translations.plan_additions(qs, self.store("es", "fa"), self.additions)
        stored, sentence = qs["700"]["text"], glow_sync.GUARD_SENTENCE
        for lang in ("es", "fa"):
            want = self.additions[sentence][lang]
            html_t = payload[lang][md5("text_700")]
            self.assertEqual(payload[lang][md5(stored)], html_t)
            self.assertEqual(payload[lang][md5(sentence)], want)
            self.assertEqual(html_t, glow_sync.guard_html(want))       # the same box, translated
        self.assertEqual((sources[md5(sentence)], sources[md5("text_700")], sources[md5(stored)]),
                         (sentence, "text_700", stored))
        # the links keep their keys
        self.assertIn(md5("text_460"), payload["es"])
        # a form without the warning gets none of its keys
        payload, sources = add_translations.plan_additions(link_form(roster=True), self.store("es"),
                                                           self.additions)
        self.assertNotIn(md5(sentence), set(payload["es"]) | set(sources))
        # add_language keys it too, beside the links
        base = {md5("text_700"): "text_700", md5(stored): stored, md5("text_460"): "text_460"}
        out = add_language.text_element_keys(qs, base, {sentence: "GG", links.ROSTER.sentence: "RR"})
        self.assertEqual(set(out), {md5("text_700"), md5(stored), md5("text_460")})
        self.assertEqual(out[md5("text_700")], glow_sync.guard_html("GG"))
        self.assertEqual(out[md5(stored)], glow_sync.guard_html("GG"))

    def test_only_a_text_element_named_club_guard_is_translated(self):
        qs = self.guard_form()
        qs["700"]["type"] = "control_textbox"
        self.assertEqual([s for _, s in links.translated_elements(qs)],
                         [links.ROSTER.sentence, links.PROBLEM.sentence])

    def test_the_store_backup_is_never_overwritten(self):
        # a same-stamp re-run after a failed POST must keep the true 'before'
        import tempfile
        from unittest import mock
        from glow import translations
        self.assertIn("<form>-<stamp>-before.json", add_translations.__doc__)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(translations, "REPO", tmp):
            first = translations.save_store("123", {"es": {"k": "before"}}, "2026-09-28T100005")
            again = translations.save_store("123", {"es": {"k": "half-written"}}, "2026-09-28T100005")
            self.assertNotEqual(first, again)
            self.assertTrue(first.endswith(os.path.join("translations", "123-2026-09-28T100005-before.json")))
            with open(first, encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"es": {"k": "before"}})
            with open(again, encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"es": {"k": "half-written"}})


class RosterLayout(unittest.TestCase):
    """glow/layout.py: the fence, the new-roster slot, the one-time tail
    repair and the audit, on the fake form laid out like the live ones."""

    def test_the_fence_is_the_first_of_the_links_and_submit(self):
        self.assertEqual(layout.fence(link_form())["qid"], "443")
        self.assertEqual(layout.fence(link_form(roster=True))["qid"], "460")
        self.assertEqual(layout.fence(link_form(problem=False))["qid"], "2")
        low = link_form()
        low["443"]["order"] = "50"                   # a link below Submit: Submit is the fence
        self.assertEqual(layout.fence(low)["qid"], "2")
        bare = {k: v for k, v in link_form().items() if k not in ("443", "2")}
        self.assertIsNone(layout.fence(bare))
        self.assertEqual(layout.rosters_below(bare), [])
        two = link_form()
        two["471"] = {"qid": "471", "type": "control_button", "name": "b2", "order": "30"}
        with self.assertRaises(SystemExit):
            layout.fence(two)

    def test_rosters_below_and_the_slot(self):
        qs = link_form()
        self.assertEqual([q["qid"] for q in layout.rosters_below(qs)], ["400"])
        slot, fence = layout.roster_slot(qs)
        self.assertEqual((slot, fence["qid"]), (links.order_of(qs["350"]), "443"))
        # no Submit and no link (the SameNameFlow form): the end of the form, as before
        pp, _ = SameNameFixture.form(SameNameFixture())
        self.assertEqual(layout.roster_slot(pp), (max(links.order_of(q) for q in pp.values()) + 1, None))
        # no roster above the fence: the fence's own order
        qs["350"]["order"] = "99"
        slot, fence = layout.roster_slot(qs)
        self.assertEqual((slot, fence["qid"]), (links.order_of(qs["443"]), "443"))

    def test_one_and_two_new_rosters_render_above_the_fence_under_both_behaviours(self):
        for base in (link_form(), link_form(roster=True), link_form(problem=False)):
            fence = layout.fence(base)["qid"]
            for behaviour in ("insert", "tie"):
                for n in (1, 2):
                    qs, new = base, []
                    for i in range(n):
                        slot, _ = layout.roster_slot(base)          # computed once per run
                        qs, qid = create_at(qs, {"type": "control_checkbox", "name": f"New{i}",
                                                 "hidden": "Yes", "order": str(slot)}, behaviour)
                        new.append(qid)
                    order = [str(q["qid"]) for q in layout.in_render_order(qs)]
                    for qid in new:
                        self.assertLess(order.index(qid), order.index(fence), (behaviour, n))
                    self.assertEqual([q["qid"] for q in layout.rosters_below(qs)], ["400"])
                    # where among the rosters (RUNBOOK "Rosters above Submit"): inserted,
                    # just above the last roster above the fence, newest first; tied,
                    # just after it, in creation order
                    i = order.index("350")
                    if behaviour == "insert":
                        self.assertEqual(order[i - n:i], new[::-1], n)
                    else:
                        self.assertEqual(order[i + 1:i + 1 + n], new, n)

    def test_the_tail_plan(self):
        qs = link_form()
        top = max(links.order_of(q) for q in qs.values())
        moves = layout.plan_tail_moves(qs)
        # Submit first, then the hidden fields bottom-up, the link (the fence) last
        self.assertEqual(moves, [("2", top + 2), ("18", top + 4), ("103", top + 3), ("443", top + 1)])
        self.assertFalse({qid for qid, _ in moves} & {"350", "400"})    # no roster is ever written
        after = move_all(qs, moves)
        self.assertEqual(layout.rosters_below(after), [])
        self.assertEqual(rendered(after)[-4:], [links.PROBLEM.name, "submit2", "belowAre", "contact_ids"])
        seen = [n for n in rendered(qs) if n not in ("MoonriseClub", "SunriseClub")]
        self.assertEqual([n for n in rendered(after) if n not in ("MoonriseClub", "SunriseClub")], seen)
        self.assertEqual(layout.plan_tail_moves(after), [])            # a second run plans nothing
        self.assertEqual(layout.audit_layout(after), [])

    def test_with_both_links_they_move_bottom_up_and_stay_above_submit_at_every_step(self):
        qs = link_form(roster=True)
        top = max(links.order_of(q) for q in qs.values())
        moves = layout.plan_tail_moves(qs)
        self.assertEqual([qid for qid, _ in moves], ["2", "18", "103", "443", "460"])
        self.assertEqual(dict(moves), {"460": top + 1, "443": top + 2, "2": top + 3,
                                       "103": top + 4, "18": top + 5})
        for n in range(len(moves) + 1):
            part = rendered(move_all(qs, moves[:n]))
            self.assertEqual([x for x in part if x in (links.ROSTER.name, links.PROBLEM.name, "submit2")],
                             [links.ROSTER.name, links.PROBLEM.name, "submit2"], n)
            if n:                                     # after the first write every roster is above Submit
                self.assertGreater(part.index("submit2"), part.index("MoonriseClub"), n)
        self.assertEqual(layout.rosters_below(move_all(qs, moves)), [])

    def test_a_re_run_after_a_half_finished_apply_ends_identical(self):
        for qs in (link_form(), link_form(roster=True), link_form(problem=False)):
            moves = layout.plan_tail_moves(qs)
            whole = rendered(move_all(qs, moves))
            for n in range(1, len(moves)):
                half = move_all(qs, moves[:n])
                again = layout.plan_tail_moves(half)
                self.assertTrue(again, n)             # the fence moves last: a stop leaves work to do
                self.assertEqual(rendered(move_all(half, again)), whole, n)

    def test_without_a_link_submit_is_the_fence_and_moves_last(self):
        qs = link_form(problem=False)
        moves = layout.plan_tail_moves(qs)
        self.assertEqual([qid for qid, _ in moves], ["18", "103", "2"])
        self.assertEqual(layout.rosters_below(move_all(qs, moves)), [])

    def test_it_refuses_rather_than_guessing(self):
        pagebreak = link_form()
        pagebreak["480"] = {"qid": "480", "type": "control_pagebreak", "name": "page2", "order": "8"}
        visible = link_form()
        visible["481"] = {"qid": "481", "type": "control_textbox", "name": "extra", "order": "13"}
        shown = link_form()
        shown["482"] = {"qid": "482", "type": "control_textbox", "name": "extra", "order": "13",
                        "hidden": "Yes"}
        rule = [{"id": "7", "terms": [], "action": [{"visibility": "Show", "field": "482"}]}]
        below = link_form(roster=True)
        below["460"]["order"] = "12"                  # a link below Submit
        none = link_form()
        del none["2"]
        two = link_form()
        two["471"] = {"qid": "471", "type": "control_button", "name": "b2", "order": "30"}
        for name, qs, conds in (("page break", pagebreak, ()), ("visible field", visible, ()),
                                ("shown by a rule", shown, rule), ("link below Submit", below, ()),
                                ("no Submit", none, ()), ("two Submits", two, ())):
            with self.assertRaises(SystemExit, msg=name):
                layout.plan_tail_moves(qs, conds)
        quiet = copy.deepcopy(shown)                  # hidden and no rule shows it: it moves along
        moves = layout.plan_tail_moves(quiet)
        self.assertIn("482", [qid for qid, _ in moves])

    def test_the_restore_plan_puts_every_order_back_with_the_links_above_submit(self):
        for saved in (link_form(), link_form(roster=True), link_form(problem=False)):
            moves = layout.plan_tail_moves(saved)
            for n in range(1, len(moves) + 1):           # after a whole or a stopped repair
                now = move_all(saved, moves[:n])
                back = layout.plan_restore(now, saved)
                self.assertEqual(sorted(q for q, _ in back), sorted(q for q, _ in moves[:n]), n)
                for i in range(len(back) + 1):
                    part = rendered(move_all(now, back[:i]))
                    seen = [x for x in part if x in (links.ROSTER.name, links.PROBLEM.name, "submit2")]
                    self.assertEqual(seen, [x for x in rendered(saved) if x in seen], (n, i))
                self.assertEqual(move_all(now, back), saved, n)
            self.assertEqual(layout.plan_restore(saved, saved), [])
        qs = link_form()
        repaired = move_all(qs, layout.plan_tail_moves(qs))
        grown = copy.deepcopy(repaired)
        grown["490"] = {"qid": "490", "type": "control_checkbox", "name": "LateClub", "order": "9"}
        shifted = copy.deepcopy(repaired)
        shifted["400"]["order"] = "99"
        for name, now in (("a new question", grown), ("a roster moved", shifted)):
            with self.assertRaises(SystemExit, msg=name):
                layout.plan_restore(now, qs)

    def test_the_restore_plan_refuses_a_snapshot_with_a_tie_and_says_why(self):
        # the Club Roster Form link placed before the repair: plan_insert moves
        # q443 and Submit one down, so Submit shares the next hidden field's order
        qs = link_form()
        order, moves = links.plan_insert(qs, links.ROSTER)
        linked = move_all(qs, moves)
        linked["460"] = {"qid": "460", "type": "control_text", "name": links.ROSTER.name,
                         "order": str(order)}
        self.assertEqual(links.order_of(linked["2"]), links.order_of(linked["103"]))
        repaired = move_all(linked, layout.plan_tail_moves(linked))
        self.assertEqual(layout.audit_layout(repaired), [])           # the repair itself is fine
        with self.assertRaises(SystemExit) as cm:                      # its undo refuses, and says why
            layout.plan_restore(repaired, linked)
        self.assertIn(f"the snapshot holds more than one question at order {links.order_of(linked['2'])}",
                      str(cm.exception.code))
        self.assertIn("Revision History", str(cm.exception.code))

    def test_the_audit(self):
        qs = link_form()
        problems = layout.audit_layout(qs)
        self.assertEqual(problems, ["1 roster(s) render below somethingNotWorking (q443) (first q400) - "
                                    "run tools/fix_roster_order.py (dry run first)"])
        self.assertEqual(layout.audit_layout(move_all(qs, layout.plan_tail_moves(qs))), [])
        below = link_form(roster=True)
        below["460"]["order"] = "12"
        self.assertTrue(any("clubRosterFormLink (q460) renders below Submit" in p
                            for p in layout.audit_layout(below)))
        two = link_form()
        two["471"] = {"qid": "471", "type": "control_button", "name": "b2", "order": "30"}
        self.assertEqual(layout.audit_layout(two), ["2 Submit buttons, expected 1"])
        self.assertEqual(layout.summary(qs), {"submit_buttons": 1, "fence": "somethingNotWorking (q443)",
                                              "rosters": 2, "rosters_below": 1, "first_below": "400"})


class FixRosterOrderTool(unittest.TestCase):
    """tools/fix_roster_order.py main() on fake forms (FakeFormClient keeps an
    order as sent): planning, refusals, snapshot, drift, probe, verify."""

    FIDS = [glow_forms.TEMPLATE, *glow_forms.REGIONALS.values()]

    def run_main(self, fake, *argv):
        """(exit code or 0, stdout, events): events = 'snap <fid>' / 'write <label>' in order."""
        import contextlib
        import io
        from unittest import mock
        events, out = [], io.StringIO()
        post = fake.post_form

        def post_form(path, data, label):
            events.append("write " + label)
            return post(path, data, label)
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(fix_roster_order, "Client",
                                                  lambda key, apply=False: fake))
            stack.enter_context(mock.patch.object(
                fix_roster_order.backup, "snapshot", lambda fid, client, stamp: events.append("snap " + fid)))
            stack.enter_context(mock.patch.object(fake, "post_form", post_form))
            stack.enter_context(mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}))
            stack.enter_context(mock.patch.object(sys, "argv", ["fix_roster_order.py", *argv]))
            stack.enter_context(contextlib.redirect_stdout(out))
            try:
                fix_roster_order.main()
                code = 0
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), events

    def forms(self, **overrides):
        return {fid: overrides.get(fid) or link_form() for fid in self.FIDS}

    def test_the_template_is_planned_and_written_first(self):
        self.assertEqual(list(fix_roster_order.FORMS), self.FIDS)

    def test_dry_run_plans_every_form_and_writes_nothing(self):
        fake = FakeFormClient(self.forms())
        code, out, events = self.run_main(fake)
        self.assertEqual((code, events), (0, []))
        self.assertEqual(out.count("1 of 2 rosters render below somethingNotWorking (q443)"), 5)
        self.assertIn("1. move submit2 (q2) 11 -> 16", out)
        self.assertIn("4. move somethingNotWorking (q443) 10 -> 15", out)
        self.assertNotIn("Girl", out)                 # girls' names never printed

    def test_apply_snapshots_first_probes_then_verifies_and_a_re_run_is_a_no_op(self):
        fid = glow_forms.TEMPLATE
        fake = FakeFormClient({fid: link_form(roster=True)})
        code, out, events = self.run_main(fake, "--form", fid, "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(events[0], "snap " + fid)
        self.assertEqual([e.split(" ")[3] for e in events[1:]], ["submit2", "contact_ids", "belowAre",
                                                                 "somethingNotWorking", "clubRosterFormLink"])
        self.assertIn("probe: q2 holds order", out)
        self.assertIn("re-read: verified - every roster above clubRosterFormLink (q460)", out)
        self.assertEqual(layout.rosters_below(fake.forms[fid]), [])
        self.assertEqual(layout.audit_layout(fake.forms[fid]), [])
        code, out, events = self.run_main(fake, "--form", fid, "--apply")
        self.assertEqual((code, events), (0, []))
        self.assertIn("nothing to do", out)

    def test_form_limits_what_is_read_and_written(self):
        fake = FakeFormClient({self.FIDS[1]: link_form()})     # only Africa exists in the fake
        code, _, events = self.run_main(fake, "--form", self.FIDS[1], "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(events[0], "snap " + self.FIDS[1])
        self.assertTrue(all(self.FIDS[1] in e for e in events))

    def test_a_refusal_on_the_last_form_writes_no_form(self):
        two = link_form()
        two["471"] = {"qid": "471", "type": "control_button", "name": "b2", "order": "30"}
        fake = FakeFormClient(self.forms(**{self.FIDS[-1]: two}))
        code, _, events = self.run_main(fake, "--apply")
        self.assertIn("expected one Submit button, found 2", str(code))
        self.assertEqual(events, [])

    def test_a_form_changed_since_the_preview_is_not_written(self):
        fid = glow_forms.TEMPLATE
        fake = FakeFormClient({fid: link_form()})
        gets = fake.get

        def get(path, **params):
            if path.endswith("/questions") and not hasattr(fake, "seen"):
                fake.seen = True
                return gets(path, **params)
            fake.forms[fid]["490"] = {"qid": "490", "type": "control_checkbox", "name": "LateClub",
                                      "hidden": "Yes", "order": "40"}   # the runner, mid-run
            return gets(path, **params)
        fake.get = get
        code, _, events = self.run_main(fake, "--form", fid, "--apply")
        self.assertIn("changed since the preview - nothing written", str(code))
        self.assertEqual(events, ["snap " + fid])

    def test_the_probe_stops_the_run_when_jotform_renumbers(self):
        # a Jotform that renumbers the form 1..N after an order update: the second
        # target would no longer be an empty slot - stop after the first write
        class Renumbering(FakeFormClient):
            def post_form(self, path, data, label):
                out = super().post_form(path, data, label)
                fid = re.fullmatch(r"/form/(\d+)/.*", path).group(1)
                for n, q in enumerate(sorted(self.forms[fid].values(), key=links.render_key), 1):
                    q["order"] = str(n)
                return out
        fake = Renumbering(self.forms())
        code, out, events = self.run_main(fake, "--apply")
        self.assertIn("after the first write", str(code))
        self.assertIn("does not keep an order update as sent", str(code))
        self.assertEqual([e.split(" ")[0] for e in events], ["snap", "write"])   # the template only
        tpl = fake.forms[glow_forms.TEMPLATE]
        names = rendered(tpl)                          # safe: every roster above Submit, the link too
        self.assertLess(names.index(links.PROBLEM.name), names.index("submit2"))
        self.assertLess(names.index("MoonriseClub"), names.index("submit2"))
        for fid in self.FIDS[1:]:
            self.assertEqual(fake.forms[fid], link_form(), fid)
        # the message says what the re-read shows, and no longer that only one
        # element moved - with a roster renumbered, --undo refuses (it says so)
        self.assertIn("other question(s) changed order", str(code))
        self.assertNotIn("only that element moved", str(code))
        self.assertIn("the re-read shows every roster above Submit", str(code))
        self.assertIn("--undo (below) refuses: a roster's order changed too (q400)", str(code))
        self.assertIn("Revision History", str(code))
        with self.assertRaises(SystemExit) as cm:
            layout.plan_restore(tpl, link_form())
        self.assertIn("roster(s) changed order since the snapshot", str(cm.exception.code))

    def test_a_probe_that_finds_only_the_written_order_off_says_undo_puts_it_back(self):
        # a Jotform that ignores the order sent: nothing else moved - and the
        # re-read is measured, not assumed safe (the roster is still below Submit)
        class Ignoring(FakeFormClient):
            def post_form(self, path, data, label):
                self.writes.append(label)
                return {}
        fid = glow_forms.TEMPLATE
        fake = Ignoring({fid: link_form()})
        code, _, events = self.run_main(fake, "--form", fid, "--apply")
        self.assertEqual([e.split(" ")[0] for e in events], ["snap", "write"])
        self.assertIn("q2 holds 11, sent 16", str(code))
        self.assertNotIn("other question(s) changed order", str(code))
        self.assertIn("no other order changed, so --undo (below) puts that element back", str(code))
        self.assertIn("the re-read shows 1 roster(s) below Submit", str(code))
        self.assertRegex(str(code), rf"--form {fid} --undo \d{{4}}-\d\d-\d\dT\d{{6}}")

        class Nudging(FakeFormClient):              # another (non-roster) order moves as well
            def post_form(self, path, data, label):
                self.forms[fid]["103"]["order"] = "112"
                return super().post_form(path, data, label)
        fake = Nudging({fid: link_form()})
        code, _, _ = self.run_main(fake, "--form", fid, "--apply")
        self.assertIn("1 other question(s) changed order, e.g. q103 12 -> 112", str(code))
        self.assertIn("the --undo dry run (below) plans the way back or refuses", str(code))
        self.assertEqual(move_all(fake.forms[fid], layout.plan_restore(fake.forms[fid], link_form())),
                         link_form())                # here it plans it

    def test_a_write_that_changes_anything_else_fails_the_verify_and_stops(self):
        class Meddling(FakeFormClient):
            def post_form(self, path, data, label):
                out = super().post_form(path, data, label)
                if "somethingNotWorking" in label:                # the last write
                    fid = re.fullmatch(r"/form/(\d+)/.*", path).group(1)
                    self.forms[fid]["350"]["options"] = "Girl One|Girl Two|Girl Nine"
                return out
        fake = Meddling(self.forms())
        code, out, _ = self.run_main(fake, "--apply")
        self.assertIn("MISMATCH after the writes", str(code))
        self.assertIn("1 question(s) changed apart from their order: q350", str(code))
        self.assertNotIn("Girl", str(code) + out)       # compared by hash, never printed
        for fid in self.FIDS[1:]:
            self.assertEqual(fake.forms[fid], link_form(), fid)

    def test_a_failed_write_says_to_re_run_the_dry_run(self):
        class Failing(FakeFormClient):
            def post_form(self, path, data, label):
                if "belowAre" in label:
                    raise fix_roster_order.JotformError(label + ": non-JSON response: '<html>504'")
                return super().post_form(path, data, label)
        fake = Failing(self.forms())
        code, _, _ = self.run_main(fake, "--apply")
        self.assertIn("2 of 4 moves were confirmed", str(code))
        self.assertIn("Re-run the dry run", str(code))
        half = fake.forms[glow_forms.TEMPLATE]           # the re-run finishes it identically
        again = layout.plan_tail_moves(half)
        self.assertEqual(rendered(move_all(half, again)),
                         rendered(move_all(link_form(), layout.plan_tail_moves(link_form()))))

    def test_after_a_stop_the_stopped_runs_stamp_stays_the_rollback(self):
        # run 1 stops part-way; its stop repeats its stamp, and the re-run's
        # plan says the form is part-way, so the re-run's snapshot (of the
        # part-way form) is not taken for the form before the repair
        fid = glow_forms.TEMPLATE

        class Failing(FakeFormClient):
            def post_form(self, path, data, label):
                if "belowAre" in label:
                    raise fix_roster_order.JotformError(label + ": non-JSON response: '<html>504'")
                return super().post_form(path, data, label)
        fake = Failing({fid: link_form()})
        code, out, _ = self.run_main(fake, "--form", fid, "--apply")
        stamp = re.search(r"--undo (\S+)\)", out).group(1)
        self.assertIn(f"the rollback to this form as this run found it: --form {fid} --undo {stamp}",
                      str(code))
        code, out, events = self.run_main(FakeFormClient(fake.forms), "--form", fid)   # the dry run
        self.assertEqual((code, events), (0, []))
        self.assertIn("part-way: 2 element(s) already render after the last roster", out)
        self.assertIn("the --undo stamp that run printed", out)
        _, fresh, _ = self.run_main(FakeFormClient({fid: link_form()}), "--form", fid)
        self.assertNotIn("part-way", fresh)
        # nothing written (a changed form, or an error before the first POST): no rollback line
        for fail in ("drift", "read"):
            class Reading(FakeFormClient):
                gets = 0

                def get(self, path, fail=fail, **params):
                    if path.endswith("/questions"):
                        self.gets += 1
                        if self.gets == 2 and fail == "read":
                            raise fix_roster_order.JotformError(path + ": non-JSON response: '<html>504'")
                        if self.gets == 2:
                            self.forms[fid]["490"] = {"qid": "490", "type": "control_checkbox",
                                                      "name": "LateClub", "hidden": "Yes", "order": "40"}
                    return super().get(path, **params)
            code, _, events = self.run_main(Reading({fid: link_form()}), "--form", fid, "--apply")
            self.assertEqual(events, ["snap " + fid], fail)
            self.assertNotIn("--undo", str(code), fail)
        self.assertIn("nothing was written to it", str(code))

    def test_a_failed_re_read_stops_with_the_count_and_what_was_not_verified(self):
        # a 504 on the probe's GET or on the verify's: stop() with the count, not
        # a bare API error - after the last write the dry run says "nothing to do"
        fid = glow_forms.TEMPLATE
        for writes, confirmed in ((1, "1 of 4"), (4, "4 of 4")):
            class Failing(FakeFormClient):
                failed = False

                def get(self, path, writes=writes, **params):
                    if path.endswith("/questions") and len(self.writes) == writes and not self.failed:
                        self.failed = True
                        raise fix_roster_order.JotformError(path + ": non-JSON response: '<html>504'")
                    return super().get(path, **params)
            fake = Failing({fid: link_form()})
            code, _, events = self.run_main(fake, "--form", fid, "--apply")
            self.assertEqual(len(events), 1 + writes, writes)             # the snapshot, then the writes
            self.assertIn(f"{confirmed} moves were confirmed; the re-read that verifies the form "
                          "did not run", str(code))
            self.assertNotIn("can hide a completed write", str(code))    # every POST answered
            self.assertIn(f"tools/form_status.py --form {fid}", str(code))
            self.assertIn("Re-run the dry run", str(code))
            self.assertRegex(str(code), rf"--form {fid} --undo \S+")

    def test_undo_puts_the_snapshot_orders_back_by_the_same_path(self):
        from unittest import mock
        fid = glow_forms.TEMPLATE
        before = link_form(roster=True)
        fake = FakeFormClient({fid: copy.deepcopy(before)})
        self.assertEqual(self.run_main(fake, "--form", fid, "--apply")[0], 0)
        code, _, _ = self.run_main(fake, "--undo", "2026-09-29T100000")
        self.assertIn("--undo needs --form", str(code))
        with mock.patch.object(fix_roster_order, "load_snapshot", lambda f, stamp: copy.deepcopy(before)):
            code, out, events = self.run_main(fake, "--form", fid, "--undo", "2026-09-29T100000")
            self.assertEqual((code, events), (0, []))                         # a dry run
            self.assertIn("5 element(s) go back to the snapshot's orders", out)
            code, out, events = self.run_main(fake, "--form", fid, "--undo", "2026-09-29T100000", "--apply")
            self.assertEqual(code, 0, out)
            self.assertEqual(events[0], "snap " + fid)
            self.assertEqual([e.split(" ")[3] for e in events[1:]], ["clubRosterFormLink", "somethingNotWorking",
                                                                     "belowAre", "contact_ids", "submit2"])
            self.assertIn("the 2026-09-29T100000 orders are back", out)
            self.assertEqual(fake.forms[fid], before)
            code, out, events = self.run_main(fake, "--form", fid, "--undo", "2026-09-29T100000", "--apply")
            self.assertEqual((code, events), (0, []))
            self.assertIn("nothing to do", out)

    def test_undo_reads_the_snapshot_the_tool_names(self):
        import tempfile
        from unittest import mock
        fid = glow_forms.TEMPLATE
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(fix_roster_order.backup, "REPO", tmp):
            with self.assertRaises(SystemExit) as cm:
                fix_roster_order.load_snapshot(fid, "2026-09-29T100000")
            self.assertIn(f"no snapshot backups/{fid}/questions-2026-09-29T100000.json", str(cm.exception.code))
            os.makedirs(os.path.join(tmp, "backups", fid))
            with open(os.path.join(tmp, "backups", fid, "questions-2026-09-29T100000.json"), "w") as f:
                json.dump(link_form(), f)
            self.assertEqual(fix_roster_order.load_snapshot(fid, "2026-09-29T100000"), link_form())

    def test_verify_catches_a_roster_left_below_and_changed_rules(self):
        qs = link_form()
        moves = layout.plan_tail_moves(qs)
        after = move_all(qs, moves)
        self.assertEqual(fix_roster_order.verify(qs, after, [], [], moves), [])
        rule = [{"id": "1", "type": "field", "link": "Any", "terms": json.dumps([]),
                 "action": json.dumps([{"visibility": "Show", "field": "350"}])}]
        self.assertIn("the rules changed", fix_roster_order.verify(qs, after, rule, [], moves))
        partial = move_all(qs, moves[:1])
        problems = fix_roster_order.verify(qs, partial, [], [], moves)
        self.assertTrue(any("hold another order than sent" in p for p in problems), problems)
        self.assertTrue(any("render below somethingNotWorking" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main(verbosity=1)
