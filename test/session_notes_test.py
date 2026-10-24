#!/usr/bin/env python3
"""
The optional session-notes field of the attendance forms (ticket #104), on fake forms laid out
like the live ones: its definition in glow/layout.py (NOTES_NAME, NOTES_PROPS, NOTES_EXPECTED,
notes_slot, the fence and the audit), tools/add_session_notes.py (plan, snapshot, write,
re-read, --remove; NotesTool), the sync leaving the field alone (SyncLeavesTheNotesAlone) and
tools/form_status.py's `session notes:` line and audit lines (FormStatusNotes).

Ryan's answers (ticket #104, 2026-10-22): label "Additional information about this session
(optional)", NO sub-label, 1,000 characters. Jotform's textarea keeps the limit as `entryLimit`
"<Type>-<N>" and its runtime counts `Letters` as characters: "Letters-1000". The field has no
rule, is never required or hidden, and sits after the last roster and above the links and
Submit, at an EMPTY order (so nothing moves whether Jotform inserts or ties). When none is free -
the live forms today: the tail sits right after the last roster - the tool first moves the first
link through Submit, and the hidden fields at the orders right after, down by one, bottom-up so
each lands on an empty order (the path Jotform keeps exactly), and refuses on a hidden or stray
element in that run (Ryan, 2026-10-23, option A). Fictional clubs and girls only
(helpers.common.link_form).
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
from helpers.common import FakeForm, SameNameFixture, create_at, link_form, move_all, rendered
import auto_sync
import form_status
from glow import backup as glow_backup
from glow import forms as glow_forms
from glow import layout
from glow import links

TEMPLATE = glow_forms.TEMPLATE
AFRICA, ASIA, LATAM, US = (glow_forms.REGIONALS[r] for r in ("Africa", "Asia", "Latin America", "U.S"))

# Ryan's answers, pinned here independently of glow/layout.py
NOTES = "sessionNotes"
LABEL = "Additional information about this session (optional)"
LIMIT = "Letters-1000"
WANT = {"type": "control_textarea", "text": LABEL, "entryLimit": LIMIT, "required": "No"}
# the tail of a live form in render order (what sits at or below the fence)
TAIL = (links.ROSTER.name, links.PROBLEM.name, "submit2", "belowAre", "contact_ids")


def tool():
    """tools/add_session_notes.py, imported at the call: until the ticket creates it each tool
    test fails on this import, and the layout, sync and form_status tests run on their own."""
    import add_session_notes
    return add_session_notes


def field(qid, order, **over):
    """The notes field as Jotform returns it once written as wanted (subLabel and hidden as the
    API reports them when a create never set them)."""
    return {"qid": qid, "name": NOTES, "order": str(order), "subLabel": "", "hidden": "No", **WANT, **over}


def notes_form(gap=3, notes=None, **link_kw):
    """link_form(**link_kw) as the 2026-09-30 repair left the live forms: every roster above
    the links and Submit, the tail (the links, Submit, the hidden fields) at orders after the
    last roster, and the orders the tail held (10-13) empty between the two rosters - with `gap`
    free orders between the last roster (q400, the one the sync had created after Submit) and
    the first of the tail (gap=0: none, the repair's own result). notes: the notes field as
    wanted - True: q700 at the first free order after q400; (qid, order): where you say."""
    qs = link_form(**link_kw)
    top = max(links.order_of(q) for q in qs.values())           # q400's order (14, 15 or 13)
    by_name = {q["name"]: q for q in qs.values()}
    for i, name in enumerate(n for n in TAIL if n in by_name):
        by_name[name]["order"] = str(top + 1 + gap + i)
    if notes is True:
        notes = ("700", top + 1)
    if notes is not None:
        qid, order = notes
        qs[qid] = field(qid, order)
    return qs


def first_of_tail(qs):
    """The qid of the first link / Submit in render order (what the notes must sit above)."""
    return str(min((q for q in qs.values() if q["name"] in TAIL[:3]), key=links.render_key)["qid"])


def shifted_block(qs, first):
    """What moves down by one when no order is free before the links: `first` (the first link /
    Submit) and everything at the consecutive orders below it, down to the first empty order -
    the block Jotform's own insert would shift - bottom-up: written in that sequence every
    target is empty, so Jotform keeps each order exactly. Orders unique, as notes_form's are."""
    at = {links.order_of(q): str(q["qid"]) for q in qs.values()}
    order, block = links.order_of(qs[first]), []
    while order in at:
        block.append(at[order])
        order += 1
    return block[::-1]


class FakeClient:
    """Jotform for add_session_notes.main(): GETs serve the in-memory forms and their
    conditions, a question create lands as create_at() says Jotform might ("insert" or "tie"),
    an update merges, a delete removes. Every write is recorded in order: writes = [(path,
    fields)] (fields None for a delete), labels = their labels."""

    def __init__(self, forms, behaviour="insert", conditions=None):
        self.forms, self.behaviour = forms, behaviour
        self.conditions = conditions or {}
        self.writes, self.labels = [], []

    def get(self, path, **params):
        fid, part = re.fullmatch(r"/form/(\d+)(?:/(questions|properties))?", path).groups()
        if part == "questions":
            return copy.deepcopy(self.forms[fid])
        if part == "properties":
            return {"conditions": copy.deepcopy(self.conditions.get(fid, []))}
        return {"status": "ENABLED", "count": "0"}

    def post_form(self, path, data, label):
        fields = {re.fullmatch(r"question\[(\w+)\]", k).group(1): v for k, v in data.items()}
        self.writes.append((path, fields))
        self.labels.append(label)
        m = re.fullmatch(r"/form/(\d+)/questions", path)
        if m:
            self.forms[m.group(1)], qid = create_at(self.forms[m.group(1)], fields, self.behaviour)
            return {"qid": int(qid)}            # the API answers a new qid as an integer
        fid, qid = re.fullmatch(r"/form/(\d+)/question/(\d+)", path).groups()
        self.forms[fid][qid].update(fields)
        return {}

    def delete(self, path, label):
        self.writes.append((path, None))
        self.labels.append(label)
        fid, qid = re.fullmatch(r"/form/(\d+)/question/(\d+)", path).groups()
        del self.forms[fid][qid]
        return {}


def _no_client(*args, **kwargs):
    raise AssertionError("main(argv, client=fake) must use the client it is given, not build one")


class NotesDefinition(unittest.TestCase):
    """glow/layout.py: NOTES_NAME, NOTES_PROPS, NOTES_EXPECTED, notes_slot, the fence, roster_slot."""

    def test_notes_props_are_ryans_answers(self):
        self.assertEqual(layout.NOTES_NAME, NOTES)
        self.assertIs(layout.NOTES_EXPECTED, False)        # built, not live: absent is no problem yet
        props = layout.NOTES_PROPS
        for k, v in WANT.items():
            self.assertEqual(props[k], v, k)
        self.assertFalse(props.get("subLabel"))             # label only: no sub-label
        self.assertNotEqual(props.get("hidden"), "Yes")
        self.assertLessEqual(set(props), set(WANT) | {"subLabel", "hidden"})
        self.assertNotIn("name", props)                     # the name is NOTES_NAME, the order notes_slot's
        self.assertNotIn("order", props)
        m = re.fullmatch(r"Letters-(\d+)", props["entryLimit"])
        self.assertEqual(int(m.group(1)), 1000)

    def test_notes_slot_is_the_lowest_empty_order_after_the_last_roster(self):
        # notes_slot(questions) -> (order, moves): the order the field takes and, as
        # links.plan_insert gives them, the [(qid, new order)] that free it - [] when it is free
        for kw in ({}, {"roster": True}, {"problem": False}):
            for gap in (1, 2, 5):
                qs = notes_form(gap=gap, **kw)
                # the first free order after q400 - not 10, the gap the tail left between the
                # rosters - and nothing to move
                self.assertEqual(layout.notes_slot(qs), (links.order_of(qs["400"]) + 1, []), (kw, gap))
            # the repair's own result, and the live forms today: no free order, so the first link
            # through Submit and the hidden fields at the orders right after move down by one -
            # bottom-up, each to an empty order - and the field takes the order that frees up
            full = notes_form(gap=0, **kw)
            first = first_of_tail(full)
            block = shifted_block(full, first)
            self.assertEqual(set(block), {q for q in full if links.order_of(full[q]) > links.order_of(full["400"])})
            order, moves = layout.notes_slot(full)
            self.assertEqual(order, links.order_of(full[first]), kw)
            self.assertEqual(moves, [(qid, links.order_of(full[qid]) + 1) for qid in block], kw)
            after = move_all(full, moves)
            self.assertEqual(rendered(after), rendered(full), kw)                    # nothing re-ordered
            self.assertNotIn(order, {links.order_of(q) for q in after.values()}, kw)  # the slot is free now
            self.assertEqual(layout.notes_slot(after), (order, []), kw)              # and a re-plan finds it
        moved = notes_form(gap=3)
        moved["400"]["order"] = "11"                         # the last roster higher up: 12..17 free
        self.assertEqual(layout.notes_slot(moved), (12, []))
        gone = notes_form(gap=3)
        del gone["400"]                                      # q350 (order 9) is the last roster
        self.assertEqual(layout.notes_slot(gone), (10, []))
        spaced = notes_form(gap=0)                           # a gap below Submit: what is past it stays
        for qid in ("103", "18"):
            spaced[qid]["order"] = str(links.order_of(spaced[qid]) + 2)
        at = links.order_of(spaced["443"])
        self.assertEqual(layout.notes_slot(spaced), (at, [("2", at + 2), ("443", at + 1)]))
        tied = notes_form(gap=0)
        tied["350"]["order"] = "15"                          # a roster shares the link's order: the order
        with self.assertRaises(SystemExit):                  # freed would not be empty - a refusal still
            layout.notes_slot(tied)

    def test_a_roster_the_sync_creates_later_renders_above_the_notes(self):
        for kw in ({}, {"roster": True}, {"problem": False}):
            qs = notes_form(gap=3, notes=True, **kw)
            tail_first = first_of_tail(qs)
            self.assertEqual(layout.fence(qs)["qid"], "700", kw)            # the first of notes, links, Submit
            slot, at = layout.roster_slot(qs)
            self.assertEqual((slot, at["qid"]), (links.order_of(qs["400"]), "700"), kw)
            self.assertEqual(layout.rosters_below(qs), [], kw)
            for behaviour in ("insert", "tie"):
                for n in (1, 2):
                    after, new = qs, []
                    for i in range(n):                                        # computed once per run
                        after, qid = create_at(after, {"type": "control_checkbox", "name": f"New{i}",
                                                       "hidden": "Yes", "order": str(slot)}, behaviour)
                        new.append(qid)
                    names = rendered(after)
                    for qid in new:
                        self.assertLess(names.index(after[qid]["name"]), names.index(NOTES), (kw, behaviour, n))
                    self.assertLess(names.index(NOTES), names.index(qs[tail_first]["name"]), (kw, behaviour))
                    self.assertEqual(layout.rosters_below(after), [], (kw, behaviour, n))
                    self.assertEqual([x for x in names if x not in {after[q]["name"] for q in new}],
                                     rendered(qs), (kw, behaviour, n))       # nothing else moves
        # a roster already rendering below the notes (a misplaced field): the slot is the last
        # roster ABOVE the notes, so the next roster does not land below them too
        low = notes_form(gap=3, notes=("700", 10))                           # q400 (order 14) is below it
        slot, at = layout.roster_slot(low)
        self.assertEqual((slot, at["qid"]), (links.order_of(low["350"]), "700"))
        self.assertEqual([q["qid"] for q in layout.rosters_below(low)], ["400"])
        for behaviour in ("insert", "tie"):
            after, qid = create_at(low, {"type": "control_checkbox", "name": "Newest", "hidden": "Yes",
                                         "order": str(slot)}, behaviour)
            names = rendered(after)
            self.assertLess(names.index("Newest"), names.index(NOTES), behaviour)
            self.assertEqual([q["qid"] for q in layout.rosters_below(after)], ["400"], behaviour)


class NotesTool(unittest.TestCase):
    """tools/add_session_notes.py main(argv, client=fake): placement under both create
    behaviours, the dry run, idempotence, the snapshot, the moves when no order is free, the
    refusals, the re-read, --remove."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()      # backups/ of the run (glow.backup.REPO)

    def tearDown(self):
        self.tmp.cleanup()

    def snapshots(self, fid):
        """The files in backups/<fid>/ (none: no snapshot was taken)."""
        folder = os.path.join(self.tmp.name, "backups", fid)
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

    def stamped(self, fid):
        """The stamped questions snapshots of the form, in name order."""
        return [n for n in self.snapshots(fid) if re.fullmatch(r"questions-\d{4}-\d\d-\d\dT\d{6}\.json", n)]

    def saved(self, fid, name):
        with open(os.path.join(self.tmp.name, "backups", fid, name), encoding="utf-8") as f:
            return json.load(f)

    def run_tool(self, fake, *argv):
        """(exit code - 0 when main returns, else what sys.exit got - and stdout) of
        main(list(argv), client=fake), the API key set as every tool test sets it, a Client
        the tool would build itself an assertion failure (the client given IS the forms)."""
        mod = tool()
        out = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(glow_backup, "REPO", self.tmp.name))
            stack.enter_context(mock.patch.object(mod, "Client", _no_client, create=True))
            stack.enter_context(mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}))
            stack.enter_context(mock.patch.object(sys, "argv", ["add_session_notes.py"]))
            stack.enter_context(contextlib.redirect_stdout(out))
            try:
                mod.main(list(argv), client=fake)
                code = 0
            except SystemExit as e:
                code = e.code or 0
        return code, out.getvalue()

    def assertRefused(self, code, msg=None):
        """The repo's refusal: sys.exit("what to fix") - a non-empty message, exit status 1."""
        self.assertTrue(isinstance(code, str) and code.strip(), msg or code)

    @staticmethod
    def cases():
        """[(form id, the form, the last roster above the links, the first link / Submit)]:
        five layouts whose slot, neighbours and fence differ, so no fixed answer passes."""
        moved = notes_form(gap=3)
        moved["400"]["order"] = "11"
        gone = notes_form(gap=4)
        del gone["400"]
        return [(TEMPLATE, notes_form(gap=3), "400", "443"),
                (AFRICA, notes_form(gap=1, roster=True), "400", "460"),
                (ASIA, notes_form(gap=2, problem=False), "400", "2"),
                (US, moved, "400", "443"),
                (LATAM, gone, "350", "443")]

    def test_the_tool_adds_the_field_after_the_rosters_and_above_the_links(self):
        for behaviour in ("insert", "tie"):
            for fid, base, last, first in self.cases():
                with self.subTest(behaviour=behaviour, form=fid):
                    fake = FakeClient({fid: copy.deepcopy(base)}, behaviour)
                    code, out = self.run_tool(fake, "--form", fid, "--apply")
                    self.assertEqual(code, 0, out)
                    after = fake.forms[fid]
                    ours = links.named(after, NOTES)
                    self.assertEqual(len(ours), 1)
                    q = ours[0]
                    for k, v in WANT.items():
                        self.assertEqual(q.get(k), v, k)
                    self.assertFalse(q.get("subLabel"))                   # label only
                    self.assertNotEqual(q.get("hidden"), "Yes")
                    slot = links.order_of(base[last]) + 1                 # the first empty order after the last roster
                    self.assertEqual(q["order"], str(slot))
                    names = rendered(after)
                    i = names.index(NOTES)
                    self.assertEqual(names[i - 1], base[last]["name"])
                    self.assertEqual(names[i + 1], base[first]["name"])
                    self.assertEqual(names[:i] + names[i + 1:], rendered(base))
                    self.assertEqual({k: v for k, v in after.items() if k != q["qid"]}, base)  # nothing else changed
                    # what reached Jotform: one create, the field's definition and nothing more
                    self.assertEqual([p for p, _ in fake.writes], [f"/form/{fid}/questions"])
                    sent = fake.writes[0][1]
                    self.assertEqual(sent["name"], NOTES)
                    self.assertEqual(sent["order"], str(slot))
                    for k, v in WANT.items():
                        self.assertEqual(sent.get(k), v, k)
                    self.assertFalse(sent.get("subLabel"))
                    self.assertNotEqual(sent.get("hidden"), "Yes")
                    self.assertLessEqual(set(sent), set(WANT) | {"name", "order", "subLabel", "hidden"})
                    self.assertIn(f"ADD {NOTES} at order {slot} (after q{last}, above q{first})", out)
                    self.assertEqual(layout.audit_layout(after), [])

    def test_a_dry_run_writes_nothing_and_a_second_apply_changes_nothing(self):
        cases = self.cases()
        forms = {fid: copy.deepcopy(base) for fid, base, _, _ in cases}
        self.assertEqual(set(forms), set(glow_forms.LIVE))              # the template + the four regionals
        fake = FakeClient(copy.deepcopy(forms))
        code, out = self.run_tool(fake)                                  # no --form, no --apply: every form planned
        self.assertEqual(code, 0, out)
        self.assertEqual(fake.writes, [])
        self.assertEqual(fake.forms, forms)
        self.assertEqual([self.snapshots(fid) for fid in forms], [[]] * len(forms))
        self.assertIn("DRY RUN", out)
        for fid, base, last, first in cases:
            self.assertIn(fid, out)
            self.assertIn(f"ADD {NOTES} at order {links.order_of(base[last]) + 1} (after q{last}, above q{first})", out)
        self.assertEqual(out.count(f"ADD {NOTES} at order"), len(cases))
        self.assertNotIn("Girl", out)                                    # girls' names never printed

        # the field already as wanted: present, nothing planned, whatever its qid
        for fid, qid, order in ((TEMPLATE, "700", 15), (AFRICA, "812", 15)):
            fake = FakeClient({fid: notes_form(gap=3, notes=(qid, order))})
            code, out = self.run_tool(fake, "--form", fid)
            self.assertEqual(code, 0, out)
            self.assertIn(f"present (q{qid}) - as wanted", out)
            self.assertNotIn("ADD", out)
            self.assertNotIn("UPDATE", out)
            self.assertEqual(fake.writes, [])

        # apply, then apply again: the second run finds it as wanted and writes nothing
        for behaviour in ("insert", "tie"):
            fake = FakeClient({TEMPLATE: notes_form(gap=3)}, behaviour)
            code, out = self.run_tool(fake, "--form", TEMPLATE, "--apply")
            self.assertEqual(code, 0, out)
            self.assertEqual(len(fake.writes), 1)
            written = copy.deepcopy(fake.forms[TEMPLATE])
            qid = links.named(written, NOTES)[0]["qid"]
            snaps = self.snapshots(TEMPLATE)
            code, out = self.run_tool(fake, "--form", TEMPLATE, "--apply")
            self.assertEqual(code, 0, out)
            self.assertEqual(len(fake.writes), 1, behaviour)              # idempotent
            self.assertEqual(fake.forms[TEMPLATE], written)
            self.assertIn(f"present (q{qid}) - as wanted", out)
            self.assertEqual(self.snapshots(TEMPLATE), snaps)            # nothing to roll back: no new snapshot
            code, out = self.run_tool(fake, "--form", TEMPLATE)          # and the dry run agrees
            self.assertEqual((code, len(fake.writes)), (0, 1))
            self.assertIn(f"present (q{qid}) - as wanted", out)
            self.tmp.cleanup()
            self.tmp = tempfile.TemporaryDirectory()

    def test_a_drifted_field_is_updated_in_place_not_re_added(self):
        cases = (("required", "Yes", "No"),
                 ("text", "Anything else about this session? (optional)", LABEL),
                 ("entryLimit", "Letters-500", LIMIT),
                 ("hidden", "Yes", "No"))
        for prop, old, new in cases:
            with self.subTest(prop=prop):
                qs = notes_form(gap=3, notes=True)
                qs["700"][prop] = old
                fake = FakeClient({TEMPLATE: copy.deepcopy(qs)})
                code, out = self.run_tool(fake, "--form", TEMPLATE)        # dry run
                self.assertEqual(code, 0, out)
                self.assertRegex(out, rf"UPDATE {prop}: '?{re.escape(old)}'? -> '?{re.escape(new)}'?")
                self.assertNotIn("ADD", out)
                self.assertEqual(fake.writes, [])
                code, out = self.run_tool(fake, "--form", TEMPLATE, "--apply")
                self.assertEqual(code, 0, out)
                self.assertEqual(fake.writes, [(f"/form/{TEMPLATE}/question/700", {prop: new})])
                self.assertEqual(fake.forms[TEMPLATE]["700"], field("700", 15))
                self.assertEqual(len(links.named(fake.forms[TEMPLATE], NOTES)), 1)
                self.assertEqual(self.saved(TEMPLATE, self.stamped(TEMPLATE)[0])["700"][prop], old)  # the rollback
                self.tmp.cleanup()
                self.tmp = tempfile.TemporaryDirectory()
        # two properties off: one write with both
        qs = notes_form(gap=3, notes=True)
        qs["700"].update({"required": "Yes", "entryLimit": "Words-200"})
        fake = FakeClient({TEMPLATE: qs})
        code, out = self.run_tool(fake, "--form", TEMPLATE, "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("UPDATE "), 2)
        self.assertEqual(fake.writes, [(f"/form/{TEMPLATE}/question/700", {"required": "No", "entryLimit": LIMIT})])
        self.assertEqual(fake.forms[TEMPLATE]["700"], field("700", 15))

    def test_apply_snapshots_the_form_before_writing(self):
        fid, base = TEMPLATE, notes_form(gap=2)
        fake = FakeClient({fid: copy.deepcopy(base)})
        code, out = self.run_tool(fake, "--form", fid)                   # the dry run takes none
        self.assertEqual((code, fake.writes, self.snapshots(fid)), (0, [], []))

        seen = {}
        post = fake.post_form

        def post_form(path, data, label):
            if "at first write" not in seen:
                seen["at first write"] = [self.saved(fid, n) for n in self.stamped(fid)]
            return post(path, data, label)
        fake.post_form = post_form
        code, out = self.run_tool(fake, "--form", fid, "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(fake.writes), 1)
        self.assertEqual(seen["at first write"], [base])                 # the "before", on disk before the write
        stamped = self.stamped(fid)
        self.assertEqual(len(stamped), 1)
        self.assertEqual(self.saved(fid, stamped[0]), base)
        self.assertIn("properties-latest.json", self.snapshots(fid))     # a full snapshot (glow.backup.snapshot)
        self.assertIn(f"backups/{fid}/{stamped[0]}", out)                # the tool names the rollback path

    def watch_first_write(self, fake, fid):
        """fake.post_form wrapped: the dict returned gets, at the first write, the stamped
        snapshots of the form then on disk (the rollback has to be there before any write)."""
        seen, post = {}, fake.post_form

        def post_form(path, data, label):
            if "at first write" not in seen:
                seen["at first write"] = [self.saved(fid, n) for n in self.stamped(fid)]
            return post(path, data, label)
        fake.post_form = post_form
        return seen

    def test_no_empty_order_before_the_links_makes_room_then_adds_the_field(self):
        # Ryan, 2026-10-23 (option A): the live forms have no free order between the last roster
        # and the first link, so the tool makes room - the first link through Submit and the
        # hidden fields at the orders right after move down by one, bottom-up so each lands on an
        # empty order (the path Jotform keeps exactly), Submit before the links - then creates the
        # field at the order that frees up. Four layouts: one link, two links, no link, a gap
        # below Submit (the hidden fields past it stay put).
        spaced = notes_form(gap=0)
        for qid in ("103", "18"):
            spaced[qid]["order"] = str(links.order_of(spaced[qid]) + 2)
        cases = [(TEMPLATE, notes_form(gap=0), "400", "443"),
                 (AFRICA, notes_form(gap=0, roster=True), "400", "460"),
                 (ASIA, notes_form(gap=0, problem=False), "400", "2"),
                 (US, spaced, "400", "443")]
        for behaviour in ("insert", "tie"):
            for fid, base, last, first in cases:
                with self.subTest(behaviour=behaviour, form=fid):
                    self.assertEqual(layout.audit_layout(base), [])          # healthy, just no room
                    slot = links.order_of(base[first])                       # the first link's order, freed
                    block = shifted_block(base, first)
                    self.assertGreater(len(block), 1)
                    moves = [(f"/form/{fid}/question/{qid}", {"order": str(links.order_of(base[qid]) + 1)})
                             for qid in block]
                    lines = [f"move {base[qid]['name']} (q{qid}) {links.order_of(base[qid])} -> "
                             f"{links.order_of(base[qid]) + 1}" for qid in block]
                    lines.append(f"ADD {NOTES} at order {slot} (after q{last}, above q{first})")
                    # the dry run prints the moves and the create, and writes nothing
                    fake = FakeClient({fid: copy.deepcopy(base)}, behaviour)
                    code, out = self.run_tool(fake, "--form", fid)
                    self.assertEqual(code, 0, out)
                    self.assertIn("DRY RUN", out)
                    for line in lines:
                        self.assertIn(line, out)
                    self.assertEqual(len(re.findall(r"\bmove \S+ \(q\d+\) \d+ -> \d+", out)), len(block))
                    self.assertEqual((fake.writes, fake.forms[fid], self.snapshots(fid)), ([], base, []))
                    # --apply: the snapshot, the moves bottom-up (each target empty when it is
                    # written), then one create at the freed order
                    seen = self.watch_first_write(fake, fid)
                    code, out = self.run_tool(fake, "--form", fid, "--apply")
                    self.assertEqual(code, 0, out)
                    self.assertEqual(fake.writes[:-1], moves)
                    path, sent = fake.writes[-1]
                    self.assertEqual(path, f"/form/{fid}/questions")
                    self.assertEqual((sent["name"], sent["order"]), (NOTES, str(slot)))
                    for k, v in WANT.items():
                        self.assertEqual(sent.get(k), v, k)
                    self.assertLessEqual(set(sent), set(WANT) | {"name", "order", "subLabel", "hidden"})
                    after = fake.forms[fid]
                    ours = links.named(after, NOTES)
                    self.assertEqual(len(ours), 1)
                    q = ours[0]
                    self.assertEqual(q["order"], str(slot))
                    for k, v in WANT.items():
                        self.assertEqual(q.get(k), v, k)
                    self.assertNotEqual(q.get("hidden"), "Yes")
                    names = rendered(after)
                    i = names.index(NOTES)
                    self.assertEqual((names[i - 1], names[i + 1]), (base[last]["name"], base[first]["name"]))
                    self.assertEqual(names[:i] + names[i + 1:], rendered(base))   # nothing else re-ordered
                    want = {qid: dict(x, order=str(links.order_of(x) + 1)) if qid in block else x
                            for qid, x in base.items()}
                    self.assertEqual({k: v for k, v in after.items() if k != q["qid"]}, want)  # orders only
                    self.assertEqual(layout.audit_layout(after), [])
                    for line in lines:
                        self.assertIn(line, out)
                    stamped = self.stamped(fid)
                    self.assertEqual(seen["at first write"], [base])     # the "before", on disk before the first move
                    self.assertEqual((len(stamped), self.saved(fid, stamped[0])), (1, base))
                    self.assertIn(f"backups/{fid}/{stamped[0]}", out)
                    # a second run finds it as wanted: nothing moves again
                    code, out = self.run_tool(fake, "--form", fid, "--apply")
                    self.assertEqual(code, 0, out)
                    self.assertEqual(len(fake.writes), len(block) + 1)
                    self.assertIn(f"present (q{q['qid']}) - as wanted", out)
                    self.tmp.cleanup()
                    self.tmp = tempfile.TemporaryDirectory()

    def test_a_hidden_or_stray_element_in_the_run_is_refused(self):
        # the run the tool would move - the first link through Submit - holds a hidden link or
        # Submit, or something a mentor can see besides the links and Submit: a refusal naming
        # the element, in the dry run and with --apply; nothing written, no snapshot
        def between(q, conditions=None):
            """notes_form(gap=0) with `q` between the problem link and Submit (Submit and the
            hidden fields one further down), and the rules the form's properties answer."""
            qs = notes_form(gap=0)
            for qid in ("2", "103", "18"):
                qs[qid]["order"] = str(links.order_of(qs[qid]) + 1)
            qs[q["qid"]] = dict(q, order=str(links.order_of(qs["443"]) + 1))
            return qs, conditions
        hidden_first = notes_form(gap=0, roster=True)
        hidden_first["460"]["hidden"] = "Yes"
        hidden_second = notes_form(gap=0, roster=True)
        hidden_second["443"]["hidden"] = "Yes"
        hidden_submit = notes_form(gap=0, problem=False)
        hidden_submit["2"]["hidden"] = "Yes"
        stray = {"qid": "470", "type": "control_textbox", "name": "somethingElse"}
        shown = [{"id": "7", "terms": [], "action": [{"visibility": "Show", "field": "470"}]}]
        cases = (("hidden first link", hidden_first, None, "q460", "hidden"),
                 ("hidden second link", hidden_second, None, "q443", "hidden"),
                 ("hidden Submit", hidden_submit, None, "q2", "hidden"),
                 ("visible stray", *between(stray), "q470", "somethingElse"),
                 ("hidden stray a rule shows", *between(dict(stray, hidden="Yes"), shown), "q470", "somethingElse"))
        for name, qs, conditions, who, word in cases:
            self.assertEqual(layout.audit_layout(qs), [], name)          # nothing else wrong with the layout
            for argv in ((), ("--apply",)):
                fake = FakeClient({TEMPLATE: copy.deepcopy(qs)}, conditions={TEMPLATE: conditions or []})
                code, out = self.run_tool(fake, "--form", TEMPLATE, *argv)
                self.assertRefused(code, (name, argv))
                self.assertIn(who, code, (name, argv))                   # the reason names the element
                self.assertIn(word, code, (name, argv))
                self.assertEqual(fake.writes, [], (name, argv))
                self.assertEqual(fake.forms[TEMPLATE], qs, (name, argv))
                self.assertEqual(self.snapshots(TEMPLATE), [], (name, argv))
        # every form is planned before anything is written: a refusal on the second form leaves
        # the first one unchanged too
        forms = {TEMPLATE: notes_form(gap=3), AFRICA: hidden_first}
        fake = FakeClient(copy.deepcopy(forms))
        code, out = self.run_tool(fake, "--form", TEMPLATE, "--form", AFRICA, "--apply")
        self.assertRefused(code)
        self.assertEqual(fake.writes, [])
        self.assertEqual(fake.forms, forms)
        self.assertEqual((self.snapshots(TEMPLATE), self.snapshots(AFRICA)), ([], []))

    def test_a_write_that_lands_wrong_stops_non_zero_and_names_the_snapshot(self):
        fid = TEMPLATE

        class Appending(FakeClient):
            """A Jotform that ignores the order sent: the field lands at the end, below Submit."""
            def post_form(self, path, data, label):
                if path.endswith("/questions"):
                    end = max(links.order_of(q) for q in self.forms[fid].values()) + 1
                    data = dict(data, **{"question[order]": str(end)})
                return super().post_form(path, data, label)

        class Requiring(FakeClient):
            """A Jotform that makes the new field required."""
            def post_form(self, path, data, label):
                out = super().post_form(path, data, label)
                if path.endswith("/questions"):
                    self.forms[fid][str(out["qid"])]["required"] = "Yes"
                return out

        class Ruled(FakeClient):
            """A rule names the field right after it is created."""
            def post_form(self, path, data, label):
                out = super().post_form(path, data, label)
                if path.endswith("/questions"):
                    self.conditions[fid] = [{"id": "9", "type": "field", "terms": [],
                                             "action": [{"visibility": "Show", "field": str(out["qid"])}]}]
                return out

        for kind in (Appending, Requiring, Ruled):
            with self.subTest(kind=kind.__name__):
                fake = kind({fid: notes_form(gap=3)})
                code, out = self.run_tool(fake, "--form", fid, "--apply")
                self.assertRefused(code)
                self.assertEqual(len(fake.writes), 1)                    # written once, then stopped
                stamped = self.stamped(fid)
                self.assertEqual(len(stamped), 1)
                self.assertIn(f"backups/{fid}/{stamped[0]}", code + out)  # the rollback, named
                self.assertEqual(self.saved(fid, stamped[0]), notes_form(gap=3))
                self.tmp.cleanup()
                self.tmp = tempfile.TemporaryDirectory()

    def test_a_mismatch_on_one_form_stops_the_run_before_the_next_is_touched(self):
        # a re-read MISMATCH on one form stops the run there (the outline: "otherwise stops
        # non-zero naming the snapshot"; fix_roster_order.py, whose order moves these are, stops
        # at the first form): the forms after it are neither snapshotted nor written, the forms
        # before it stay written and verified, the exit is non-zero and names the snapshot of
        # the form that did not verify (the review of PR #127)
        class AppendingOn(FakeClient):
            """A Jotform that, on the form `wrong`, ignores the order sent: the field lands at
            the end, below Submit - the re-read finds it misplaced."""
            def __init__(self, forms, wrong):
                super().__init__(forms)
                self.wrong = wrong

            def post_form(self, path, data, label):
                if path == f"/form/{self.wrong}/questions":
                    end = max(links.order_of(q) for q in self.forms[self.wrong].values()) + 1
                    data = dict(data, **{"question[order]": str(end)})
                return super().post_form(path, data, label)

        bases = {fid: base for fid, base, _, _ in self.cases()}
        regionals = [fid for fid in glow_forms.LIVE if fid != TEMPLATE]
        pick = sum((["--form", f] for f in regionals), [])
        # (argv, the forms of the run in order, the form whose write lands wrong)
        runs = [((), list(glow_forms.LIVE), TEMPLATE),          # every form: the first one fails
                (pick, regionals, regionals[0]),                # the regionals: the first one fails
                (pick, regionals, regionals[1])]                # the second: one written before it
        for argv, order, wrong in runs:
            with self.subTest(argv=argv, wrong=wrong):
                forms = {fid: copy.deepcopy(bases[fid]) for fid in order}
                fake = AppendingOn(copy.deepcopy(forms), wrong)
                code, out = self.run_tool(fake, *argv, "--apply")
                self.assertRefused(code)
                self.assertIn("MISMATCH", out)
                at = order.index(wrong)
                before, after = order[:at], order[at + 1:]
                for fid in before:                                       # written and verified
                    self.assertEqual(len(links.named(fake.forms[fid], NOTES)), 1, fid)
                    self.assertEqual(len(self.stamped(fid)), 1, fid)
                self.assertEqual(out.count("re-read: verified"), len(before))
                # the form that did not verify: one create, its snapshot taken and named
                self.assertEqual([p for p, _ in fake.writes if wrong in p], [f"/form/{wrong}/questions"])
                stamped = self.stamped(wrong)
                self.assertEqual(len(stamped), 1)
                self.assertEqual(self.saved(wrong, stamped[0]), forms[wrong])
                self.assertIn(f"backups/{wrong}/{stamped[0]}", code + out)
                # the forms after it: no snapshot, no write, as they were
                for fid in after:
                    self.assertEqual(self.snapshots(fid), [], fid)
                    self.assertEqual([p for p, _ in fake.writes if fid in p], [], fid)
                    self.assertEqual(fake.forms[fid], forms[fid], fid)
                self.assertEqual(len(fake.writes), len(before) + 1)
                self.tmp.cleanup()
                self.tmp = tempfile.TemporaryDirectory()

    @staticmethod
    def with_roster_link(qs):
        """`qs` after tools/add_feedback_link.py --link roster, as links.plan_insert places it:
        the problem link (or Submit) and what is below it down to Submit move one down, the
        element takes the freed order - so Submit comes to share an order with the hidden field
        right after it."""
        order, moves = links.plan_insert(qs, links.ROSTER)
        out = move_all(qs, moves)
        qid = str(max(int(k) for k in out) + 1)
        out[qid] = {"qid": qid, "type": "control_text", "name": links.ROSTER.name, "order": str(order),
                    "text": links.element_html(links.ROSTER.sentence, links.ROSTER_FORM_URL)}
        return out

    def test_a_tie_in_the_tail_is_refused_naming_both_questions(self):
        # --link roster on a live form (BACKLOG 46, pending) leaves Submit sharing an order with
        # the first hidden field after it; making room for the notes would then write onto a
        # taken order. A refusal - and one that names the tied pair (both qids), so the operator
        # knows what blocks it (the review of PR #127) - from notes_slot and from the tool, in
        # the dry run and with --apply; nothing written, no snapshot.
        linked = self.with_roster_link(notes_form(gap=0))                # the live layout, then --link roster
        self.assertEqual(links.order_of(linked["2"]), links.order_of(linked["103"]))    # Submit ties with belowAre
        bare = self.with_roster_link(notes_form(gap=0, problem=False))   # no problem link: the same tie
        self.assertEqual(links.order_of(bare["2"]), links.order_of(bare["103"]))
        hidden_pair = notes_form(gap=0)                                   # two hidden fields share an order
        hidden_pair["18"]["order"] = hidden_pair["103"]["order"]
        for name, qs, pair in (("after --link roster", linked, ("2", "103")),
                               ("after --link roster, no problem link", bare, ("2", "103")),
                               ("two hidden fields tied", hidden_pair, ("103", "18"))):
            with self.subTest(case=name):
                self.assertEqual(layout.audit_layout(qs), [])             # the form is healthy otherwise
                with self.assertRaises(SystemExit) as cm:
                    layout.notes_slot(qs)
                for qid in pair:
                    self.assertRegex(str(cm.exception.code), rf"\bq{qid}\b")
                for argv in ((), ("--apply",)):
                    fake = FakeClient({TEMPLATE: copy.deepcopy(qs)})
                    code, out = self.run_tool(fake, "--form", TEMPLATE, *argv)
                    self.assertRefused(code, argv)
                    for qid in pair:
                        self.assertRegex(code, rf"\bq{qid}\b", argv)
                    self.assertEqual(fake.writes, [], argv)
                    self.assertEqual(fake.forms[TEMPLATE], qs, argv)
                    self.assertEqual(self.snapshots(TEMPLATE), [], argv)

    def test_the_notes_go_on_before_the_roster_link_which_then_goes_between(self):
        # the sequence that works: the notes first, the Club Roster Form link after -
        # links.plan_insert puts it directly above the problem link, below the notes, and the
        # layout audits clean: rosters -> sessionNotes -> roster link -> problem link -> Submit
        for behaviour in ("insert", "tie"):
            for gap in (0, 3):
                with self.subTest(behaviour=behaviour, gap=gap):
                    fake = FakeClient({TEMPLATE: notes_form(gap=gap)}, behaviour)
                    code, out = self.run_tool(fake, "--form", TEMPLATE, "--apply")
                    self.assertEqual(code, 0, out)
                    noted = fake.forms[TEMPLATE]
                    after = self.with_roster_link(noted)
                    names = rendered(after)
                    i = names.index("MoonriseClub")                       # the last roster
                    self.assertEqual(names[i:i + 5],
                                     ["MoonriseClub", NOTES, links.ROSTER.name, links.PROBLEM.name, "submit2"])
                    self.assertEqual([n for n in names if n != links.ROSTER.name], rendered(noted))  # nothing else moved
                    self.assertEqual(layout.audit_layout(after), [])
                    self.assertEqual(layout.rosters_below(after), [])
                    again = FakeClient({TEMPLATE: copy.deepcopy(after)})  # the tool finds its field as wanted
                    code, out = self.run_tool(again, "--form", TEMPLATE, "--apply")
                    self.assertEqual((code, again.writes), (0, []), out)
                    self.assertIn("as wanted", out)
                    self.tmp.cleanup()
                    self.tmp = tempfile.TemporaryDirectory()

    def test_an_existing_misplaced_field_is_refused_and_nothing_written(self):
        # the field is on the form but not where it belongs: the tool sets a field's flags
        # right, never its place - a refusal naming what is wrong, in the dry run and with
        # --apply; nothing written, no snapshot. --remove --apply is the way out.
        below_link = notes_form(gap=3, notes=("700", 19))                # after the problem link, above Submit
        for qid in ("2", "103", "18"):
            below_link[qid]["order"] = str(links.order_of(below_link[qid]) + 2)
        below_submit = notes_form(gap=3, notes=("700", 30), roster=True)  # after everything
        roster_below = notes_form(gap=3, notes=("700", 10))              # q400 (order 14) renders below it
        two_below = notes_form(gap=2, notes=("812", 8), problem=False)   # another qid; q350 and q400 below it
        for name, qs, words in (("below the problem link", below_link, ("q700", "below", "q443")),
                                ("below Submit", below_submit, ("q700", "below")),
                                ("a roster below it", roster_below, ("q700", "q400", "1 roster")),
                                ("two rosters below it", two_below, ("q812", "q350", "2 roster"))):
            for argv in ((), ("--apply",)):
                fake = FakeClient({TEMPLATE: copy.deepcopy(qs)})
                code, out = self.run_tool(fake, "--form", TEMPLATE, *argv)
                self.assertRefused(code, (name, argv))
                for word in words:
                    self.assertIn(word, code, (name, argv))
                self.assertNotIn("ADD", out, (name, argv))
                self.assertEqual(fake.writes, [], (name, argv))
                self.assertEqual(fake.forms[TEMPLATE], qs, (name, argv))
                self.assertEqual(self.snapshots(TEMPLATE), [], (name, argv))
            fake = FakeClient({TEMPLATE: copy.deepcopy(qs)})              # the way out still works
            code, out = self.run_tool(fake, "--form", TEMPLATE, "--remove", "--apply")
            self.assertEqual(code, 0, (name, out))
            self.assertEqual(links.named(fake.forms[TEMPLATE], NOTES), [], name)
            self.assertEqual(len(fake.writes), 1, name)
            self.tmp.cleanup()                                           # the remove's snapshot
            self.tmp = tempfile.TemporaryDirectory()

    def test_remove_takes_the_field_out(self):
        fid, qid = LATAM, "812"
        before = notes_form(gap=2, notes=(qid, 16), roster=True)
        fake = FakeClient({fid: copy.deepcopy(before)})
        code, out = self.run_tool(fake, "--form", fid, "--remove")       # dry run
        self.assertEqual(code, 0, out)
        self.assertIn("DELETE", out)
        self.assertIn(f"q{qid}", out)
        self.assertEqual((fake.writes, self.snapshots(fid)), ([], []))

        seen = {}
        delete = fake.delete

        def delete_(path, label):
            seen["at delete"] = [self.saved(fid, n) for n in self.stamped(fid)]
            return delete(path, label)
        fake.delete = delete_
        code, out = self.run_tool(fake, "--form", fid, "--remove", "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(fake.writes, [(f"/form/{fid}/question/{qid}", None)])
        self.assertEqual(fake.forms[fid], {k: v for k, v in before.items() if k != qid})
        self.assertEqual(seen["at delete"], [before])                    # snapshotted first, the field still in it
        self.assertIn(f"backups/{fid}/{self.stamped(fid)[0]}", out)
        snaps = self.snapshots(fid)
        code, out = self.run_tool(fake, "--form", fid, "--remove", "--apply")   # nothing left to remove
        self.assertEqual(code, 0, out)
        self.assertEqual(len(fake.writes), 1)
        self.assertEqual(self.snapshots(fid), snaps)

        # add then remove puts the form back exactly, under either create behaviour
        for behaviour in ("insert", "tie"):
            fresh = notes_form(gap=3)
            fake = FakeClient({TEMPLATE: copy.deepcopy(fresh)}, behaviour)
            self.assertEqual(self.run_tool(fake, "--form", TEMPLATE, "--apply")[0], 0)
            self.assertEqual(self.run_tool(fake, "--form", TEMPLATE, "--remove", "--apply")[0], 0)
            self.assertEqual(fake.forms[TEMPLATE], fresh, behaviour)

        # two fields carry the name: a refusal, not a guess - nothing written either way
        twice = notes_form(gap=3, notes=True)
        twice["815"] = field("815", 16)
        for argv in (("--remove", "--apply"), ("--apply",), ()):
            fake = FakeClient({TEMPLATE: copy.deepcopy(twice)})
            code, out = self.run_tool(fake, "--form", TEMPLATE, *argv)
            self.assertRefused(code, argv)
            self.assertEqual(fake.writes, [], argv)
            self.assertEqual(fake.forms[TEMPLATE], twice, argv)


class SyncLeavesTheNotesAlone(SameNameFixture, unittest.TestCase):
    """sync_attendance_form.py end to end (fake Jotform, link_form's clubs): the notes field is
    neither written nor named by any generated rule, --prune on a fresh clone never deletes
    it, and a new roster goes above it."""

    ROSTER = {("Partner A", "Sunrise Club"): ["Girl One", "Girl Two", "Girl Four"],
              ("Partner A", "Moonrise Club"): ["Girl Three"],
              ("Partner B", "Starlight Club"): ["Girl Five"]}

    def created(self, fake):
        """[(label, fields)] of the roster creates, fields in plain keys."""
        return [(c, {k[len("question["):-1]: v for k, v in d.items()})
                for c, (m, p, d) in zip(fake.calls, fake.writes) if c.startswith("CREATE roster")]

    def test_the_sync_writes_no_rule_for_the_notes_and_never_prunes_it(self):
        for kw in ({}, {"roster": True}):
            qs = notes_form(gap=3, notes=True, **kw)
            fake = FakeForm(qs, [])
            code, out = self.run_sync(fake, roster=self.ROSTER)
            self.assertEqual(code, 0, out)
            self.assertTrue(any(c.startswith("UPDATE roster 'Sunrise Club'") for c in fake.calls), fake.calls)
            self.assertTrue(any(c.startswith("REPLACE conditions") for c in fake.calls), fake.calls)
            self.assertFalse([p for _, p, _ in fake.writes if p.rstrip("/").endswith("/700")], kw)
            puts = [d for m, p, d in fake.writes if m == "PUT" and p == "/properties"]
            self.assertEqual(len(puts), 1, kw)
            conditions = puts[0]["properties"]["conditions"]
            self.assertTrue(conditions)
            self.assertEqual(links.rules_mentioning(conditions, "700"), [], kw)
            self.assertEqual(links.rules_mentioning(conditions, 700), [], kw)
            # the new roster takes the last roster's order, above the notes - the plan says so
            (label, fields), = self.created(fake)
            self.assertEqual(label, "CREATE roster 'Starlight Club' (1 girls)")
            self.assertTrue(auto_sync.CREATE_RX.match("  - " + label))        # the runner still reads it
            self.assertEqual(fields["order"], qs["400"]["order"], kw)
            self.assertIn(f"New rosters go at order {qs['400']['order']}, above {NOTES} (q700)", out)
            self.assertEqual(auto_sync.parse_plan(out)["warnings"], [], kw)  # not a warning
            for behaviour in ("insert", "tie"):
                after, qid = create_at(qs, fields, behaviour)
                names = rendered(after)
                self.assertLess(names.index(fields["name"]), names.index(NOTES), (kw, behaviour))
                self.assertLess(names.index(NOTES), names.index(qs[first_of_tail(qs)]["name"]), (kw, behaviour))
                self.assertEqual([n for n in names if n != fields["name"]], rendered(qs), (kw, behaviour))
                self.assertEqual(layout.rosters_below(after), [], (kw, behaviour))
            self.assertNotIn("Girl", out)                                    # girls' names never printed

        # --prune on a fresh clone (no submissions): another region's roster goes, the notes stay
        qs = notes_form(gap=3, notes=True)
        fake = FakeForm(qs, [])
        code, out = self.run_sync(fake, "--prune", roster=self.ROSTER,
                                  regions={("Partner A", "Moonrise Club"): "Asia"})
        self.assertEqual(code, 0, out)
        deletes = [(c, p) for c, (m, p, _) in zip(fake.calls, fake.writes) if m == "DELETE"]
        self.assertEqual([p for _, p in deletes], ["/question/400"])
        self.assertTrue(deletes[0][0].startswith("DELETE roster 'Moonrise Club' (q400, belongs to Asia)"), deletes)
        self.assertFalse([p for _, p, _ in fake.writes if p.rstrip("/").endswith("/700")])
        puts = [d for m, p, d in fake.writes if m == "PUT" and p == "/properties"]
        self.assertEqual(links.rules_mentioning(puts[0]["properties"]["conditions"], "700"), [])


class FormStatusNotes(unittest.TestCase):
    """tools/form_status.py: the `session notes:` line, and the audit lines a misplaced,
    duplicated or required field adds (absent: a problem only once NOTES_EXPECTED is True)."""

    STORAGE = {"/user/usage": {"uploads": "1340458410", "submissions": "474", "total_submissions": "690",
                               "monthly_usage_reset_date": "2026-10-21 00:00:00", "form_count": "5"},
               "/user": {"account_type": "https://api.jotform.com/system/plan/SILVER"},
               "/system/plan/SILVER": {"name": "SILVER", "limits": {"uploads": 10738466816, "submissions": 2500}}}

    class Client:
        def __init__(self, qs, storage):
            self.qs, self.storage = qs, storage

        def get(self, path, **params):
            if path.endswith("/properties"):
                return {"conditions": [], "language": [{"options": "English|Español"}],
                        "integrations": {"salesforceV2": {"on": 1}}, "clearFieldOnHide": "disable"}
            if path.endswith("/questions"):
                return copy.deepcopy(self.qs)
            if path in self.storage:
                return copy.deepcopy(self.storage[path])
            return {"title": "Attendance Form (Template)", "status": "ENABLED", "count": "0"}

    def report(self, qs):
        return form_status.form_report(TEMPLATE, self.Client(qs, self.STORAGE), {})

    def printed(self, qs):
        """stdout of form_status.main() on the form (a Roster export of link_form's clubs)."""
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            roster = os.path.join(tmp, "roster.csv")
            with open(roster, "w", encoding="utf-8") as f:
                f.write("partner,club,full_name,status,region\n")
                for club, name in (("Sunrise Club", "Girl One"), ("Moonrise Club", "Girl Three")):
                    f.write(f"Partner A,{club},{name},active,Africa\n")
            with mock.patch.object(form_status, "Client", lambda key: self.Client(qs, self.STORAGE)), \
                    mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}), \
                    mock.patch.object(sys, "argv", ["form_status.py", "--form", TEMPLATE, "--roster", roster]), \
                    contextlib.redirect_stdout(out):
                form_status.main()
        return out.getvalue()

    @staticmethod
    def notes_problems(rep):
        return [p for p in rep["rule_problems"] if NOTES in p]

    def test_form_status_flags_notes_below_submit_twice_or_required(self):
        good = notes_form(gap=3, notes=True)
        self.assertEqual(layout.audit_layout(good), [])
        rep = self.report(good)
        self.assertEqual([p for p in rep["rule_problems"] if NOTES in p or "fix_roster_order" in p], [])
        self.assertIn("session notes: present (q700)", self.printed(good))
        other = notes_form(gap=2, notes=("812", 15), roster=True)        # found by name: another qid, two links
        self.assertEqual(self.notes_problems(self.report(other)), [])
        self.assertIn("session notes: present (q812)", self.printed(other))

        absent = notes_form(gap=3)
        self.assertEqual(self.notes_problems(self.report(absent)), [])     # built, not live: no problem yet
        self.assertIn("session notes: absent", self.printed(absent))
        with mock.patch.object(layout, "NOTES_EXPECTED", True):           # task #105 flips it
            self.assertEqual(len(self.notes_problems(self.report(absent))), 1)
            self.assertTrue(any(NOTES in p for p in layout.audit_layout(absent)))
            self.assertEqual(self.notes_problems(self.report(good)), [])
            self.assertIn("session notes: present (q700)", self.printed(good))

        twice = notes_form(gap=3, notes=True)
        twice["815"] = field("815", 16)
        problems = self.notes_problems(self.report(twice))
        self.assertTrue(any("q700" in p and "q815" in p for p in problems), problems)

        below_link = notes_form(gap=3, notes=("700", 19))                # after the link (18), above Submit
        for qid in ("2", "103", "18"):
            below_link[qid]["order"] = str(links.order_of(below_link[qid]) + 2)
        self.assertEqual(rendered(below_link).index(NOTES), rendered(below_link).index(links.PROBLEM.name) + 1)
        below_submit = notes_form(gap=3, notes=("700", 30))              # after everything
        for name, qs in (("below the link", below_link), ("below Submit", below_submit)):
            problems = self.notes_problems(self.report(qs))
            self.assertTrue(any("q700" in p and "below" in p and (links.PROBLEM.name in p or "Submit" in p)
                                for p in problems), (name, problems))
            self.assertEqual(problems, [p for p in layout.audit_layout(qs) if NOTES in p], name)

        required = notes_form(gap=3, notes=True)
        required["700"]["required"] = "Yes"
        rep = self.report(required)
        problems = self.notes_problems(rep)
        self.assertTrue(any("q700" in p and "required" in p for p in problems), problems)
        # the runner's verify (auto_sync.verify_report) sees it too: a relapse is never CLEAN
        clean = dict(rep, rule_problems=problems, languages=["a"] * 12,
                     region_check={"missing_from_form": [], "not_in_roster": [], "rosters_out_of_date": []})
        verify_problems, _ = auto_sync.verify_report(clean)
        self.assertTrue(any(NOTES in p and "required" in p for p in verify_problems), verify_problems)
        self.assertEqual(auto_sync.verify_report(dict(clean, rule_problems=[]))[0], [])

        low = notes_form(gap=3, notes=("700", 10))                       # q400 (order 14) renders below the notes
        problems = self.notes_problems(self.report(low))
        self.assertTrue(any("q700" in p and "q400" in p and "below" in p for p in problems), problems)
        self.assertIn("session notes: present (q700)", self.printed(low))

    def test_form_status_flags_a_hidden_notes_field(self):
        # hidden, no mentor can fill it: an audit line (audit_layout's), whatever the qid, that
        # the runner's verify sees too; the `session notes:` line still says present
        for kw, qid, order in (({}, "700", 15), ({"roster": True}, "812", 16)):
            qs = notes_form(gap=3, notes=(qid, order), **kw)
            self.assertEqual(self.notes_problems(self.report(qs)), [], qid)     # as wanted: no line
            qs[qid]["hidden"] = "Yes"
            rep = self.report(qs)
            problems = self.notes_problems(rep)
            self.assertTrue(any(f"q{qid}" in p and "hidden" in p for p in problems), problems)
            self.assertEqual(problems, [p for p in layout.audit_layout(qs) if NOTES in p], qid)
            self.assertIn(f"session notes: present (q{qid})", self.printed(qs))
            clean = dict(rep, rule_problems=problems, languages=["a"] * 12,
                         region_check={"missing_from_form": [], "not_in_roster": [], "rosters_out_of_date": []})
            verify_problems, _ = auto_sync.verify_report(clean)
            self.assertTrue(any(NOTES in p and "hidden" in p for p in verify_problems), verify_problems)


class TailRepairWithNotes(unittest.TestCase):
    """tools/fix_roster_order.py (the one-time tail repair, glow.layout.plan_tail_moves /
    plan_restore) on a form that carries the notes field above a stray roster - one the old
    sync created after Submit: the notes move with the links (the notes first in the tail, then
    the links, Submit, the hidden fields) to empty orders after the last roster, no roster is
    written, the audit is clean after, and --undo puts every order back."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()      # backups/ of the run (glow.backup.REPO)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def unrepaired(**kw):
        """link_form(**kw) - q400, the roster the old sync created after Submit, renders last -
        with the notes field q700 at the first link's (or Submit's) order and everything from
        there down moved one down: the notes above the links, the links above Submit, q400
        below them all."""
        qs = link_form(**kw)
        first = min((q for q in qs.values() if q["name"] in TAIL[:3]), key=links.render_key)
        at = links.order_of(first)
        for q in qs.values():
            if links.order_of(q) >= at:
                q["order"] = str(links.order_of(q) + 1)
        qs["700"] = field("700", at)
        return qs

    def run_fix(self, fake, *argv):
        """(exit code or 0, stdout) of fix_roster_order.main() with `fake` as its Client, the
        snapshots in a temporary backups/ (so --undo <stamp> reads what --apply wrote)."""
        import fix_roster_order
        out = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(glow_backup, "REPO", self.tmp.name))
            stack.enter_context(mock.patch.object(fix_roster_order, "Client", lambda key, apply=False: fake))
            stack.enter_context(mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}))
            stack.enter_context(mock.patch.object(sys, "argv", ["fix_roster_order.py", *argv]))
            stack.enter_context(contextlib.redirect_stdout(out))
            try:
                fix_roster_order.main()
                code = 0
            except SystemExit as e:
                code = e.code or 0
        return code, out.getvalue()

    @staticmethod
    def without_orders(qs):
        return {k: {x: y for x, y in v.items() if x != "order"} for k, v in qs.items()}

    def test_the_repair_moves_the_notes_with_the_links_and_undo_puts_every_order_back(self):
        fid = TEMPLATE
        for kw in ({"roster": True}, {}, {"problem": False}):             # two links, one, none
            with self.subTest(**kw):
                before = self.unrepaired(**kw)
                present = {q["name"] for q in before.values()}
                tail = [NOTES] + [n for n in TAIL if n in present]        # the tail in render order
                names = rendered(before)
                self.assertEqual(names[-1], "MoonriseClub")                # the stray roster renders last
                self.assertEqual(names[names.index(NOTES):-1], tail)      # the notes lead the tail
                self.assertTrue(any("render below" in p and "q400" in p for p in layout.audit_layout(before)))
                top = max(links.order_of(q) for q in before.values())
                tail_qids = {str(q["qid"]) for q in before.values() if q["name"] in tail}
                fake = FakeClient({fid: copy.deepcopy(before)})
                # the dry run: the notes are in the plan (first in the tail: the order right
                # after the old top), nothing written
                code, out = self.run_fix(fake, "--form", fid)
                self.assertEqual(code, 0, out)
                self.assertIn(f"move {NOTES} (q700) {links.order_of(before['700'])} -> {top + 1}", out)
                self.assertEqual((fake.writes, fake.forms[fid]), ([], before))
                self.assertNotIn("Girl", out)
                # --apply: one order write per tail element, each to an empty order above the
                # old top, Submit first and the notes (the fence) last; no roster written
                code, out = self.run_fix(fake, "--form", fid, "--apply")
                self.assertEqual(code, 0, out)
                after = fake.forms[fid]
                written = {p.rsplit("/", 1)[1]: int(f["order"]) for p, f in fake.writes}
                self.assertEqual(len(fake.writes), len(tail))
                self.assertEqual(set(written), tail_qids)
                self.assertTrue(all(set(f) == {"order"} for _, f in fake.writes))
                self.assertEqual(sorted(written.values()), list(range(top + 1, top + 1 + len(tail))))
                self.assertEqual(fake.writes[0][0].rsplit("/", 1)[1], "2")
                self.assertEqual(fake.writes[-1][0].rsplit("/", 1)[1], "700")
                self.assertEqual(rendered(after), [n for n in names if n not in tail and n != "MoonriseClub"]
                                 + ["MoonriseClub"] + tail)
                self.assertEqual(self.without_orders(after), self.without_orders(before))   # orders only
                for roster in ("350", "400"):
                    self.assertEqual(after[roster]["order"], before[roster]["order"], roster)
                self.assertEqual(layout.audit_layout(after), [])
                self.assertEqual(layout.rosters_below(after), [])
                self.assertEqual(layout.fence(after)["qid"], "700")
                self.assertIn(f"re-read: verified - every roster above {NOTES} (q700)", out)
                stamp = re.search(r"--undo (\S+)\)", out).group(1)
                code, out = self.run_fix(fake, "--form", fid, "--apply")  # a re-run: nothing to do
                self.assertEqual((code, len(fake.writes)), (0, len(tail)), out)
                self.assertIn("nothing to do", out)
                # --undo <stamp>: the dry run writes nothing; --apply puts every order back, the
                # notes first on the way back and Submit last
                code, out = self.run_fix(fake, "--form", fid, "--undo", stamp)
                self.assertEqual((code, len(fake.writes)), (0, len(tail)), out)
                self.assertIn(f"{len(tail)} element(s) go back to the snapshot's orders", out)
                code, out = self.run_fix(fake, "--form", fid, "--undo", stamp, "--apply")
                self.assertEqual(code, 0, out)
                self.assertEqual(fake.forms[fid], before)
                undo = [p.rsplit("/", 1)[1] for p, _ in fake.writes[len(tail):]]
                self.assertEqual((len(undo), set(undo)), (len(tail), tail_qids))
                self.assertEqual((undo[0], undo[-1]), ("700", "2"))
                self.assertIn(f"the {stamp} orders are back", out)
                self.tmp.cleanup()
                self.tmp = tempfile.TemporaryDirectory()


if __name__ == "__main__":
    unittest.main(verbosity=1)
