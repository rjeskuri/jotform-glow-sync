#!/usr/bin/env python3
"""
Offline tests for tools/integration_status.py (found by `make py`'s unittest discovery). A fake
client stands in for Jotform; nothing here is a real connection id.

The session notes (ticket #106, SessionNotesMapping): a ninth field, Session_Notes__c, read from
the question named sessionNotes, whose qid differs per form (template q489, Africa q476, Asia
q457, Latin America q454, U.S q446). During the rollout (NOTES_MAPPING_WANTED False) a form is
right with or without the mapping, as long as a present one reads the form's own sessionNotes;
once the switch is True a form without it is NOT RIGHT. Every test pins the switch itself, so
the file holds whatever its committed value - except
SessionNotesDisabledForms.test_the_committed_switch_is_on, which pins the committed True (the
rollout ended 2026-10-26: four forms mapped, U.S DISABLED). A live form whose `status` property
is DISABLED (Ryan, 2026-10-26: "Skip U.S: it is disabled") needs no notes mapping - that exact
value only: any other status is an enabled form's; a mapping a DISABLED form does carry is checked
as on any form, and so is everything else. The fake forms carry what a live form carries beside
the notes question - lookalike text fields, the retired partner list, a header, a special-event
field, roster checkboxes of fictional clubs - so the question is found by its NAME, not as "the
one question the tool does not know".
"""
import contextlib
import io
import json
import os
import re
import sys
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import integration_status as ist      # noqa: E402
from glow import forms as glow_forms  # noqa: E402
from glow.sync import PICKER_NAME     # noqa: E402

US = glow_forms.REGIONALS["U.S"]
OLD = glow_forms.DEFUNCT["Africa"]

# the eight fields the forms have carried since 2026-10-01, pinned here independently of the
# tool's MAPPING (glow/sync.py's qids)
EIGHT = {"Account_Name__c": "5", "Attendance_Date__c": "17", "Contact_IDs__c": "18", "Module__c": "98",
         "Module_Week__c": "100", "Module_Year__c": "102", "Creator__c": "105",
         "enable_fuzzy_matching__c": "109"}
# the ninth (ticket #106) and the question it reads, found by its name
NOTES_FIELD = "Session_Notes__c"
NOTES = "sessionNotes"
PICKER = "444"
# the qid of each live form's sessionNotes question: it differs per form
NOTES_QIDS = {glow_forms.TEMPLATE: "489", glow_forms.REGIONALS["Africa"]: "476",
              glow_forms.REGIONALS["Asia"]: "457", glow_forms.REGIONALS["Latin America"]: "454", US: "446"}


def block(account="1234567", uploads=(), **change):
    """A salesforceV2 block as the forms carry it since 2026-10-01: the eight fields, no upload.
    `Session_Notes__c="<qid>"` maps the ninth, `<field>=None` leaves one out."""
    fields = dict(EIGHT, **change)
    action = {"id": "1", "order": "1", "action": "createRecord", "upsert": "create",
              "object": "Attendance_Batch__c", "uploadFields": list(uploads),
              "fieldMapping": [{"matchId": str(n), "targetId": t, "metadata": {},
                                "source": {"type": "question", "value": q}}
                               for n, (t, q) in enumerate(fields.items()) if q is not None]}
    return {"actionMap": json.dumps([action]), "editBehavior": "update", "integrationAccountID": account}


NOTES_TEXT = "Additional information about this session (optional)"
# what a live form carries beside the notes question, (name, type, text): fields that look like
# it but are not named sessionNotes, then the everyday rest (fictional club names)
LOOKALIKES = [("notes", "control_textarea", "Notes"),
              ("sessionNotes2", "control_textarea", "Session notes"),
              ("SessionNotes", "control_textarea", "Session Notes"),
              ("additionalInformation", "control_textarea", NOTES_TEXT),
              ("sessionNotesHelp", "control_text", "Tell us anything else about the session")]
DECOYS = LOOKALIKES + [("partnerPicker", "control_dropdown", "Partner"),
                       ("attendanceHeader", "control_head", "Attendance"),
                       ("specialEventDescription", "control_textbox", "Describe the special event"),
                       ("mapleRidge", "control_checkbox", "Maple Ridge"),
                       ("sunflowerClub", "control_checkbox", "Sunflower Club"),
                       ("riverBend", "control_checkbox", "River Bend"),
                       ("oakHollow", "control_checkbox", "Oak Hollow")]
# their usual qids: below, between and above every notes qid the tests use (110, 446-490, 1203)
DECOY_QIDS = ["3", "120", "301", "302", "445", "447", "456", "600", "1300", "2000", "2001", "2002"]
USUAL = dict(zip(DECOY_QIDS, DECOYS))


def questions(notes=(), decoys=None):
    """A form's questions as GET /form/{id}/questions returns them (by qid, in qid order): the
    ones the mapping reads and the photo, the Club picker (q444), one textarea named sessionNotes
    per qid in `notes` and the decoys ({qid: (name, type, text)}; default USUAL, {} for none)."""
    decoys = USUAL if decoys is None else decoys
    clash = (set(notes) | set(ist.QUESTIONS) | {PICKER}) & set(decoys)
    assert not clash, f"test bug: a decoy on q{sorted(clash)}"
    found = {qid: {"qid": qid, "name": name, "type": "control_textbox", "text": name}
             for qid, name in ist.QUESTIONS.items()}
    found[PICKER] = {"qid": PICKER, "name": PICKER_NAME, "type": "control_dropdown", "text": "Club"}
    found.update({qid: {"qid": qid, "name": NOTES, "type": "control_textarea", "text": NOTES_TEXT}
                  for qid in notes})
    found.update({qid: {"qid": qid, "name": name, "type": kind, "text": text}
                  for qid, (name, kind, text) in decoys.items()})
    return {qid: found[qid] for qid in sorted(found, key=int)}


def layouts(own):
    """Three ways to lay the decoys out around a form whose sessionNotes is q<own>: the usual
    qids, the same qids reversed, and on the OTHER live forms' notes qids (q446 a plain `notes`
    box on a form whose sessionNotes is q489)."""
    elsewhere = [q for q in NOTES_QIDS.values() if q != own]
    elsewhere += [str(n) for n in range(6, 99) if str(n) not in ist.QUESTIONS]
    return {"usual": USUAL, "reversed": dict(zip(reversed(DECOY_QIDS), DECOYS)),
            "elsewhere": dict(zip(elsewhere, DECOYS))}


class FakeJotform:
    def __init__(self, blocks, others=None, notes=None, status=None):
        self.blocks = blocks
        self.others = others or {}          # form id -> {key: block} of its other integrations
        self.notes = notes or {}            # form id -> its qids named sessionNotes (default: NOTES_QIDS)
        # form id -> its `status` property (ENABLED / DISABLED, as GET /form/{id}/properties
        # carries it); a form not named here, or named with None, has no `status` at all
        self.status = status or {}

    def get(self, path):
        parts = path.split("/")
        assert len(parts) == 4 and parts[3] in ("properties", "questions"), \
            f"the fake serves GET /form/{{id}}/properties and /questions only, not {path}"
        _, _, form_id, part = parts
        if part == "questions":
            own = [NOTES_QIDS[form_id]] if form_id in NOTES_QIDS else []
            return as_sent(questions(self.notes.get(form_id, own)))
        found = self.blocks.get(form_id)
        integrations = dict(self.others.get(form_id, {}), **({"salesforceV2": found} if found else {}))
        props = {"integrations": integrations or []}
        if self.status.get(form_id) is not None:
            props["status"] = self.status[form_id]
        return as_sent(props)


def as_sent(content):
    """What glow/jotform.py hands back: the reply parsed by json.loads, so fresh objects - its
    "DISABLED" is equal to, never the same object as, this module's literal or the tool's constant
    (test round 3: a status compared by `is` must not pass here and fail live)."""
    return json.loads(json.dumps(content))


def run(blocks, *argv, others=None, notes=None, status=None):
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            ist.main(list(argv), client=FakeJotform(blocks, others, notes, status))
    except SystemExit as stop:
        return out.getvalue(), stop.code
    return out.getvalue(), None


def wanted(value):
    """NOTES_MAPPING_WANTED pinned for one test or block. create=True: before the switch exists a
    test fails on what the audit says, not on the patch (test_session_notes_missing_is_wrong_
    only_once_wanted checks that the switch exists)."""
    return mock.patch.object(ist, "NOTES_MAPPING_WANTED", value, create=True)


def section(out, label):
    """What main() prints for one form: its own line and the indented lines under it."""
    lines = out.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"{label}: "))
    end = next((i for i in range(start + 1, len(lines)) if not lines[i].startswith(" ")), len(lines))
    return "\n".join(lines[start:end])


def reads(text, qid):
    """Does the text name q<qid> (and not a longer qid that starts with it)?"""
    return re.search(rf"\bq{qid}(?!\d)", text) is not None


def about_notes(found):
    """The problems that name the Session_Notes__c field."""
    return [line for line in found if NOTES_FIELD in line]


class IntegrationStatus(unittest.TestCase):
    def setUp(self):
        # the eight fields, with the notes switch pinned off (its own tests are in
        # SessionNotesMapping), so these hold whatever its committed value
        switch = wanted(False)
        switch.start()
        self.addCleanup(switch.stop)

    def test_the_known_mapping_is_ok(self):
        out, stop = run({US: block()}, "--form", US)
        self.assertIsNone(stop)
        self.assertIn("U.S: connection 1234567 - ok (one action, 8 fields, Account_Name__c from q5, no upload)", out)
        self.assertIn("integration: ok", out)
        self.assertEqual(ist.UPLOADS, [])          # no photo to Salesforce since 2026-10-01 (DECISIONS)
        self.assertEqual(ist.QUESTIONS["19"], "photo")   # the question itself must still be there

    def test_the_club_picker_as_the_source_of_the_account_name_is_named(self):
        out, stop = run({US: block(Account_Name__c="444")}, "--form", US)
        self.assertEqual(stop, 1)
        self.assertIn("Account_Name__c reads q444 (the Club picker); it must read q5 (clubName)", out)

    def test_every_other_difference_is_named(self):
        cases = {
            "NO Salesforce integration": None,
            "Module__c reads q99; it must read q98": block(Module__c="99"),
            "Creator__c is not mapped from a question": block(Creator__c=None),
            "Processing_Status__c is mapped too": block(Processing_Status__c="17"),
            "the upload field is ['19'], not [] (no photo goes to Salesforce since 2026-10-01)": block(uploads=("19",)),
            "no connected Salesforce account": block(account=""),
        }
        for message, found in cases.items():
            with self.subTest(message):
                out, stop = run({US: found}, "--form", US)
                self.assertEqual(stop, 1)
                self.assertIn(message, out)

    def test_the_other_integrations_of_every_live_form_are_listed(self):
        live = {fid: block() for fid in glow_forms.LIVE}
        out, stop = run(live)
        self.assertIsNone(stop)
        self.assertEqual(out.count("  other integrations: none"), len(glow_forms.LIVE))
        # the Drive block (its key is learned from this line once Ryan sets it up): named, not a problem
        others = {US: {"anotherIntegration": {"folder": "x"}, "aSecondOne": {}}}
        out, stop = run(live, others=others)
        self.assertIsNone(stop)
        self.assertIn("  other integrations: aSecondOne, anotherIntegration", out)
        self.assertEqual(out.count("  other integrations: none"), len(glow_forms.LIVE) - 1)
        # a form with no Salesforce block still has the line; an old form has none
        out, stop = run({}, "--form", US, others=others)
        self.assertEqual(stop, 1)
        self.assertIn("NO Salesforce integration", out)
        self.assertIn("  other integrations: aSecondOne, anotherIntegration", out)
        out, _ = run(live, others={OLD: {"anotherIntegration": {}}})
        self.assertEqual(out.count("other integrations"), len(glow_forms.LIVE))
        # the property as a JSON string, or Jotform's [] for none
        self.assertEqual(ist.other_integrations({"integrations": json.dumps({"salesforceV2": {}, "zzz": {}})}), ["zzz"])
        self.assertEqual((ist.other_integrations({"integrations": []}), ist.block_of({"integrations": []})), ([], None))

    def test_all_forms_one_connection_and_the_old_forms_stay_without(self):
        live = {fid: block() for fid in glow_forms.LIVE}
        out, stop = run(live)
        self.assertIsNone(stop)
        self.assertEqual(out.count("no Salesforce integration (as wanted)"), len(glow_forms.DEFUNCT))
        out, stop = run(dict(live, **{US: block(account="7654321")}))
        self.assertEqual(stop, 1)
        self.assertIn("2 different connections", out)
        out, stop = run(dict(live, **{OLD: block()}))
        self.assertIn("old Africa: STILL CONNECTED", out)

    def test_a_failed_read_is_a_clean_exit_not_a_traceback(self):
        # like every sibling tool, the script runs main under glow.cli.run: a gateway 504 is
        # one line, not a traceback
        import runpy
        from glow import jotform

        def down(client, path, **params):
            raise jotform.JotformError(f"GET {path}: 504 Gateway Time-out")
        with mock.patch.object(jotform.Client, "get", down), \
                mock.patch.dict(os.environ, {"JOTFORM_API_KEY": "test-only"}), \
                mock.patch.object(sys, "argv", ["integration_status.py", "--form", US]), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as cm:
            runpy.run_path(os.path.join(REPO, "tools", "integration_status.py"), run_name="__main__")
        self.assertEqual(cm.exception.code, f"GET /form/{US}/properties: 504 Gateway Time-out")


class SessionNotesMapping(unittest.TestCase):
    """Ticket #106: Session_Notes__c from the form's own sessionNotes question, required once
    NOTES_MAPPING_WANTED is True."""

    # --- broad: the rollout through main(), every live form ---------------------------------

    def test_the_rollout_form_by_form_through_main(self):
        # Ryan maps the five forms one at a time, the template first; with the switch off every
        # stage is right; with it on, exactly the forms not yet mapped are NOT RIGHT, each told
        # the field and its OWN sessionNotes qid
        order = list(glow_forms.LIVE)
        self.assertEqual(sorted(order), sorted(NOTES_QIDS))
        # the fakes are realistic: each form's questions carry the decoys beside its sessionNotes
        for fid in order:
            got = FakeJotform({}).get(f"/form/{fid}/questions")
            self.assertEqual([q for q, v in got.items() if v["name"] == NOTES], [NOTES_QIDS[fid]])
            self.assertLessEqual(set(USUAL), set(got))
        for n in range(len(order) + 1):
            done = order[:n]
            blocks = {fid: block(Session_Notes__c=NOTES_QIDS[fid]) if fid in done else block()
                      for fid in order}
            with self.subTest(mapped=n, wanted=False), wanted(False):
                out, stop = run(blocks)
                self.assertIsNone(stop, out)
                self.assertNotIn("NOT RIGHT", out)
                self.assertIn("integration: ok", out)
            with self.subTest(mapped=n, wanted=True), wanted(True):
                out, stop = run(blocks)
                if n == len(order):
                    self.assertIsNone(stop, out)
                    self.assertIn("integration: ok", out)
                else:
                    self.assertEqual(stop, 1, out)
                    self.assertNotIn("integration: ok", out)
                for fid in order:
                    lines = section(out, glow_forms.LIVE[fid])
                    if fid in done:
                        self.assertNotIn("NOT RIGHT", lines)
                        continue
                    self.assertIn("NOT RIGHT", lines)
                    self.assertIn(NOTES_FIELD, lines)
                    self.assertTrue(reads(lines, NOTES_QIDS[fid]), lines)
                    for other in set(NOTES_QIDS.values()) - {NOTES_QIDS[fid]}:
                        self.assertFalse(reads(lines, other), lines)

    def test_the_ok_line_says_where_the_notes_come_from(self):
        for fid, qid in NOTES_QIDS.items():
            label = glow_forms.LIVE[fid]
            for switch in (False, True):
                with self.subTest(label, wanted=switch), wanted(switch):
                    out, stop = run({fid: block(Session_Notes__c=qid)}, "--form", fid)
                    self.assertIsNone(stop, out)
                    line = section(out, label).splitlines()[0]
                    self.assertIn(f"{label}: connection 1234567 - ok (", line)
                    self.assertIn("9 fields", line)
                    self.assertIn("Account_Name__c from q5", line)
                    self.assertIn(NOTES_FIELD, line)
                    self.assertTrue(reads(line, qid), line)
            # not mapped yet, the switch off: still right, and the eight fields, not nine
            with self.subTest(label, mapped=False), wanted(False):
                out, stop = run({fid: block()}, "--form", fid)
                self.assertIsNone(stop, out)
                line = section(out, label).splitlines()[0]
                self.assertIn("ok (one action, 8 fields, Account_Name__c from q5", line)
                self.assertNotIn("9 fields", line)

    # --- the three the ticket names: problems() -----------------------------------------------

    def test_session_notes_mapped_from_the_notes_question_is_right(self):
        # the live forms' qids and two fictional ones: the qid is read from the form, never fixed
        for qid in [*NOTES_QIDS.values(), "110", "1203"]:
            for switch in (False, True):
                with self.subTest(qid=qid, wanted=switch), wanted(switch):
                    self.assertEqual(ist.problems(block(Session_Notes__c=qid), questions([qid])), [])
        # accepting the ninth leaves every other check as it was
        with wanted(True):
            found = ist.problems(block(Session_Notes__c="446", Module__c="99", Processing_Status__c="17"),
                                 questions(["446"]))
        self.assertTrue(any("Module__c reads q99; it must read q98" in line for line in found), found)
        self.assertTrue(any("Processing_Status__c is mapped too" in line for line in found), found)
        self.assertEqual(about_notes(found), [])

    def test_session_notes_from_another_question_is_wrong(self):
        # whatever the switch: a present mapping must read the form's own sessionNotes qid
        sources = {"17": "the date", "5": "question 5 (Club Name)", PICKER: "the Club picker",
                   "476": "another form's notes qid", "999": "no question at all"}
        for own in ("446", "489"):
            for got, what in sources.items():
                for switch in (False, True):
                    with self.subTest(own=own, source=what, wanted=switch), wanted(switch):
                        found = ist.problems(block(Session_Notes__c=got), questions([own]))
                        about = about_notes(found)
                        self.assertTrue(about, found)
                        self.assertTrue(any(reads(line, own) for line in about), about)
                        # Account_Name__c still reads q5: nothing said about it
                        self.assertFalse(any(line.startswith("Account_Name__c") for line in found), found)
        # through main(): the form is NOT RIGHT, exit 1
        for switch in (False, True):
            with self.subTest("main", wanted=switch), wanted(switch):
                out, stop = run({US: block(Session_Notes__c=PICKER)}, "--form", US)
                self.assertEqual(stop, 1, out)
                self.assertIn("NOT RIGHT", out)
                self.assertIn(NOTES_FIELD, out)
                self.assertTrue(reads(out, NOTES_QIDS[US]), out)

    def test_session_notes_missing_is_wrong_only_once_wanted(self):
        for qid in [*NOTES_QIDS.values(), "1203"]:
            with self.subTest(qid=qid):
                with wanted(False):
                    self.assertEqual(ist.problems(block(), questions([qid])), [])
                with wanted(True):
                    about = about_notes(ist.problems(block(), questions([qid])))
                self.assertTrue(about)
                self.assertTrue(any(reads(line, qid) for line in about), about)
        # through main()
        with wanted(False):
            out, stop = run({US: block()}, "--form", US)
        self.assertIsNone(stop, out)
        with wanted(True):
            out, stop = run({US: block()}, "--form", US)
        self.assertEqual(stop, 1, out)
        self.assertIn("NOT RIGHT", out)
        self.assertIn(NOTES_FIELD, out)
        self.assertTrue(reads(out, NOTES_QIDS[US]), out)
        # the switch is the tool's own module constant (the patches above create it until it exists)
        self.assertIsInstance(getattr(ist, "NOTES_MAPPING_WANTED", None), bool,
                              "tools/integration_status.py has no NOTES_MAPPING_WANTED switch")

    # --- the specific cases ------------------------------------------------------------------

    def test_a_form_without_a_sessionNotes_question(self):
        # the switch off and nothing mapped: nothing to check
        with wanted(False):
            self.assertEqual(ist.problems(block(), questions([])), [])
        # wanted: the question the field must read is missing, and the problem says so by name
        with wanted(True):
            found = ist.problems(block(), questions([]))
        self.assertTrue(any(NOTES in line for line in found), found)
        # a mapping that reads a question not named sessionNotes is wrong either way, a lookalike
        # included: none stands in for the missing question
        for switch in (False, True):
            for got in ["446", *DECOY_QIDS]:
                with self.subTest(source=got, wanted=switch), wanted(switch):
                    found = ist.problems(block(Session_Notes__c=got), questions([]))
                    self.assertTrue(about_notes(found), found)

    # --- the decoys: found by its name, not as the one question the tool does not know ----------

    def test_session_notes_from_a_lookalike_question_is_wrong(self):
        # beside the form's own sessionNotes: other textareas, `sessionNotes2`, `SessionNotes`,
        # one with the notes' very text, the partner list, a header, rosters - wherever they sit
        for own in ("446", "489", "1203"):
            for layout, decoys in layouts(own).items():
                form = questions([own], decoys)
                for switch in (False, True):
                    with self.subTest(own=own, layout=layout, wanted=switch), wanted(switch):
                        self.assertEqual(ist.problems(block(Session_Notes__c=own), form), [])
                        for got, (name, _, _) in decoys.items():
                            found = ist.problems(block(Session_Notes__c=got), form)
                            about = about_notes(found)
                            self.assertTrue(about, (name, found))
                            self.assertTrue(any(reads(line, own) for line in about), (name, about))
                            # only the notes are wrong: nothing about the eight or the nine questions
                            self.assertEqual([line for line in found if line not in about], [], name)
        # through main(), on the U.S form's realistic questions: its own q446 is ok, a decoy is not
        for switch in (False, True):
            with self.subTest("main", wanted=switch), wanted(switch):
                out, stop = run({US: block(Session_Notes__c=NOTES_QIDS[US])}, "--form", US)
                self.assertIsNone(stop, out)
                self.assertIn("9 fields", out)
                for got, (name, _, _) in USUAL.items():
                    out, stop = run({US: block(Session_Notes__c=got)}, "--form", US)
                    self.assertEqual(stop, 1, (name, out))
                    lines = section(out, glow_forms.LIVE[US])
                    self.assertIn("NOT RIGHT", lines)
                    self.assertIn(NOTES_FIELD, lines)
                    self.assertTrue(reads(lines, NOTES_QIDS[US]), (name, lines))

    def test_two_questions_named_sessionNotes_is_a_problem_not_a_guess(self):
        two = questions(["446", "490"])
        # Ruling (#106 orchestrator, round 2): the switch off and nothing mapped, a form carrying
        # the question twice is right HERE - that it carries it once is form_status's job
        # (glow.layout: "2 fields named 'sessionNotes'"), as for a form without it
        with wanted(False):
            self.assertEqual(ist.problems(block(), two), [])
            out, stop = run({US: block()}, "--form", US, notes={US: ["446", "490"]})
        self.assertIsNone(stop, out)
        self.assertNotIn("NOT RIGHT", out)
        # with the switch on, through main(): NOT RIGHT, by name
        with wanted(True):
            out, stop = run({US: block()}, "--form", US, notes={US: ["446", "490"]})
        self.assertEqual(stop, 1, out)
        self.assertIn(NOTES, section(out, glow_forms.LIVE[US]))
        for got in ("446", "490"):
            for switch in (False, True):
                with self.subTest(source=got, wanted=switch), wanted(switch):
                    found = ist.problems(block(Session_Notes__c=got), two)
                    self.assertTrue(any(NOTES in line for line in found), found)
        with wanted(True):
            found = ist.problems(block(), two)
        self.assertTrue(any(NOTES in line for line in found), found)


ENABLED, DISABLED = "ENABLED", "DISABLED"
# statuses that are NOT the exact value DISABLED (Ruling, #106 orchestrator, test round 2): a form
# carrying one is an enabled form - an unknown state never excuses a live form from the notes
# mapping. Jotform's own DELETED, DISABLED in another case or padded, near misses on either side
# (a prefix of it, it with a suffix), the empty string, and (test round 3) eight-letter all-caps
# words that are not it: another word, and it with its last letter changed
NOT_DISABLED = ["disabled", "Disabled", "DELETED", "DISABLED ", " DISABLED", "DISABLED_X", "DIS", "",
                "ARCHIVED", "DISABLEX"]
LIVE_IDS = list(glow_forms.LIVE)
ASIA, LATAM = glow_forms.REGIONALS["Asia"], glow_forms.REGIONALS["Latin America"]


def mapped_all(*unmapped):
    """Every live form's block, each mapping Session_Notes__c from its OWN sessionNotes qid,
    except the forms in `unmapped` (the eight fields only)."""
    return {fid: block() if fid in unmapped else block(Session_Notes__c=NOTES_QIDS[fid]) for fid in LIVE_IDS}


def bullets(lines):
    """The problem lines under a form's NOT RIGHT."""
    return [line for line in lines.splitlines()[1:] if line.startswith("  - ")]


class SessionNotesDisabledForms(unittest.TestCase):
    """Ticket #106, the rollout's end (2026-10-26): the switch on, and a live form whose `status`
    property is DISABLED needs no Session_Notes__c mapping (Ryan: "Skip U.S: it is disabled"; if
    U.S is re-enabled it must be mapped, q446). The rule follows each form's own status, never its
    id: every live form is tried DISABLED, and U.S ENABLED or with no status at all. Only the
    exact value DISABLED excuses a form: any other status (DELETED, `disabled`, `DISABLED `, ...)
    reads exactly as ENABLED. A notes mapping a DISABLED form does carry, and everything else
    about it, is checked as on any form; the old forms are unaffected."""

    def assertNotWanted(self, out, fid):
        """The form is right and its ok line says Session_Notes__c is not wanted, the form being
        DISABLED (the essentials only: the wording is the coder's)."""
        lines = section(out, glow_forms.LIVE[fid])
        line = lines.splitlines()[0]
        self.assertNotIn("NOT RIGHT", lines)
        self.assertIn("ok (", line)
        self.assertIn("8 fields", line)
        self.assertNotIn("9 fields", line)
        self.assertIn(NOTES_FIELD, line)
        self.assertIn(DISABLED, line)

    def assertMappedOk(self, out, fid, enabled=True):
        """The form is right: nine fields, the notes from its own sessionNotes (and, enabled,
        nothing calls it DISABLED)."""
        label = glow_forms.LIVE[fid]
        lines = section(out, label)
        line = lines.splitlines()[0]
        self.assertNotIn("NOT RIGHT", lines)
        self.assertIn(f"{label}: connection 1234567 - ok (", line)
        self.assertIn("9 fields", line)
        self.assertIn(NOTES_FIELD, line)
        self.assertTrue(reads(line, NOTES_QIDS[fid]), line)
        if enabled:
            self.assertNotIn(DISABLED, lines)

    def assertNotesMissing(self, out, fid):
        """The (enabled) form is NOT RIGHT for its missing notes mapping, told its OWN sessionNotes
        qid and no other form's, and nothing calls it DISABLED."""
        lines = section(out, glow_forms.LIVE[fid])
        self.assertIn("NOT RIGHT", lines)
        about = about_notes(bullets(lines))
        self.assertTrue(about, lines)
        self.assertTrue(any(reads(line, NOTES_QIDS[fid]) for line in about), lines)
        for other in set(NOTES_QIDS.values()) - {NOTES_QIDS[fid]}:
            self.assertFalse(reads(lines, other), lines)
        self.assertNotIn(DISABLED, lines)

    # --- broad: the end state through main() ------------------------------------------------

    def test_the_end_state_through_main(self):
        # 2026-10-26: template, Africa, Asia and Latin America map the notes from their own
        # sessionNotes; U.S is DISABLED and unmapped -> right, integration: ok
        blocks = mapped_all(US)
        for enabled in (ENABLED, None):     # the four's status ENABLED, or none in the properties
            four = {fid: enabled for fid in LIVE_IDS if fid != US}
            with self.subTest(others=enabled, us=DISABLED), wanted(True):
                out, stop = run(blocks, status=dict(four, **{US: DISABLED}))
                self.assertIsNone(stop, out)
                self.assertIn("integration: ok", out)
                self.assertNotIn("NOT RIGHT", out)
                self.assertNotWanted(out, US)
                for fid in four:
                    self.assertMappedOk(out, fid)
                self.assertEqual(out.count("no Salesforce integration (as wanted)"), len(glow_forms.DEFUNCT))
                # the old forms are unaffected by a status: whatever theirs, the same output
                for old in (DISABLED, ENABLED):
                    old_status = {fid: old for fid in glow_forms.DEFUNCT.values()}
                    self.assertEqual(run(blocks, status=dict(four, **{US: DISABLED}, **old_status)), (out, stop))
                    still = dict(blocks, **{OLD: block()})
                    self.assertEqual(run(still, status=dict(four, **{US: DISABLED}, **old_status)),
                                     run(still, status=dict(four, **{US: DISABLED})))
                    self.assertIn("old Africa: STILL CONNECTED",
                                  run(still, status=dict(four, **{US: DISABLED}, **old_status))[0])
            # U.S re-enabled (ENABLED, or no status at all) and still unmapped: NOT RIGHT, q446
            for us in (ENABLED, None):
                with self.subTest(others=enabled, us=us), wanted(True):
                    out, stop = run(blocks, status=dict(four, **{US: us}))
                    self.assertEqual(stop, 1, out)
                    self.assertNotIn("integration: ok", out)
                    self.assertNotesMissing(out, US)
                    for fid in four:
                        self.assertMappedOk(out, fid)
        # the U.S form alone
        with wanted(True):
            out, stop = run({US: block()}, "--form", US, status={US: DISABLED})
        self.assertIsNone(stop, out)
        self.assertIn("integration: ok", out)
        self.assertNotWanted(out, US)
        with wanted(True):
            out, stop = run({US: block()}, "--form", US, status={US: ENABLED})
        self.assertEqual(stop, 1, out)
        self.assertNotesMissing(out, US)

    def test_any_disabled_live_form_needs_no_notes_mapping_by_its_own_status(self):
        # every live form in turn DISABLED and unmapped, the other four mapped and ENABLED: right;
        # the same form ENABLED or without a status: NOT RIGHT, told its own sessionNotes qid
        for off in LIVE_IDS:
            label, blocks = glow_forms.LIVE[off], mapped_all(off)
            others = {fid: ENABLED for fid in LIVE_IDS if fid != off}
            with self.subTest(label, status=DISABLED), wanted(True):
                out, stop = run(blocks, status=dict(others, **{off: DISABLED}))
                self.assertIsNone(stop, out)
                self.assertIn("integration: ok", out)
                self.assertNotWanted(out, off)
                for fid in others:
                    self.assertMappedOk(out, fid)
                out, stop = run({off: block()}, "--form", off, status={off: DISABLED})
                self.assertIsNone(stop, out)
                self.assertIn("integration: ok", out)
                self.assertNotWanted(out, off)
            for status in (ENABLED, None):
                with self.subTest(label, status=status), wanted(True):
                    out, stop = run(blocks, status=dict(others, **{off: status}))
                    self.assertEqual(stop, 1, out)
                    self.assertNotIn("integration: ok", out)
                    self.assertNotesMissing(out, off)
                    for fid in others:
                        self.assertMappedOk(out, fid)
                    out, stop = run({off: block()}, "--form", off, status={off: status})
                    self.assertEqual(stop, 1, out)
                    self.assertNotesMissing(out, off)
        # one form's DISABLED excuses no other: U.S and Asia both unmapped, one of them DISABLED
        for disabled, enabled in ((US, ASIA), (ASIA, US)):
            with self.subTest(disabled=glow_forms.LIVE[disabled]), wanted(True):
                out, stop = run(mapped_all(US, ASIA), status={disabled: DISABLED, enabled: ENABLED})
                self.assertEqual(stop, 1, out)
                self.assertNotWanted(out, disabled)
                self.assertNotesMissing(out, enabled)
        # several DISABLED at once (all five here), none mapped: right
        with wanted(True):
            out, stop = run(mapped_all(*LIVE_IDS), status={fid: DISABLED for fid in LIVE_IDS})
        self.assertIsNone(stop, out)
        self.assertIn("integration: ok", out)
        for fid in LIVE_IDS:
            self.assertNotWanted(out, fid)

    def test_only_the_exact_status_DISABLED_excuses_a_form(self):
        # Ruling (#106 orchestrator, test round 2): a status that is not exactly DISABLED - DELETED,
        # DISABLED in another case or padded, a near miss, the empty string - is an enabled
        # form's: unmapped with the switch on it is NOT RIGHT, told Session_Notes__c and its own
        # sessionNotes qid, nothing calls it DISABLED, and it reads exactly as the same form ENABLED
        for fid in LIVE_IDS:
            label, own = glow_forms.LIVE[fid], NOTES_QIDS[fid]
            # what the same form reads ENABLED: alone, among the four mapped, and mapped itself
            with wanted(True):
                alone = run({fid: block()}, "--form", fid, status={fid: ENABLED})
                every = run(mapped_all(fid), status={f: ENABLED for f in LIVE_IDS})
                mapped = run({fid: block(Session_Notes__c=own)}, "--form", fid, status={fid: ENABLED})
            for status in NOT_DISABLED:
                with self.subTest(label, status=status, run="--form"), wanted(True):
                    out, stop = run({fid: block()}, "--form", fid, status={fid: status})
                    self.assertEqual(stop, 1, out)
                    self.assertNotIn("integration: ok", out)
                    self.assertNotesMissing(out, fid)
                    self.assertEqual((out, stop), alone)
                with self.subTest(label, status=status, run="every form"), wanted(True):
                    # the other four mapped and ENABLED
                    out, stop = run(mapped_all(fid), status=dict({f: ENABLED for f in LIVE_IDS}, **{fid: status}))
                    self.assertEqual(stop, 1, out)
                    self.assertNotIn("integration: ok", out)
                    self.assertNotesMissing(out, fid)
                    for other in set(LIVE_IDS) - {fid}:
                        self.assertMappedOk(out, other)
                    self.assertEqual((out, stop), every)
                    # every live form carrying that status, the other four mapped: the same
                    self.assertEqual(run(mapped_all(fid), status={f: status for f in LIVE_IDS}), every)
                with self.subTest(label, status=status, run="--form, mapped"), wanted(True):
                    # mapped, it is right as an enabled form is: nine fields, nothing says DISABLED
                    out, stop = run({fid: block(Session_Notes__c=own)}, "--form", fid, status={fid: status})
                    self.assertIsNone(stop, out)
                    self.assertMappedOk(out, fid)
                    self.assertEqual((out, stop), mapped)
                # beside it in the same run, another unmapped form whose status is exactly DISABLED
                # is excused: the near miss alone is NOT RIGHT
                partner = LIVE_IDS[(LIVE_IDS.index(fid) + 1) % len(LIVE_IDS)]
                with self.subTest(label, status=status, beside=f"{glow_forms.LIVE[partner]} {DISABLED}"), \
                        wanted(True):
                    status_of = dict({f: ENABLED for f in LIVE_IDS}, **{fid: status, partner: DISABLED})
                    out, stop = run(mapped_all(fid, partner), status=status_of)
                    self.assertEqual(stop, 1, out)
                    self.assertNotIn("integration: ok", out)
                    self.assertNotesMissing(out, fid)
                    self.assertNotWanted(out, partner)
                    self.assertEqual(out.count("NOT RIGHT"), 1, out)

    # --- a DISABLED form: no mapping needed, one it carries checked ---------------------------

    def test_a_disabled_form_needs_no_mapping_but_one_it_carries_is_checked(self):
        for fid in LIVE_IDS:
            own, label = NOTES_QIDS[fid], glow_forms.LIVE[fid]
            # unmapped: right, whether the form has its sessionNotes question once, not at all or
            # twice (that is form_status's to flag, as during the rollout)
            for notes in ([own], [], [own, "490"]):
                with self.subTest(label, unmapped=True, notes=notes), wanted(True):
                    out, stop = run({fid: block()}, "--form", fid, notes={fid: notes}, status={fid: DISABLED})
                    self.assertIsNone(stop, out)
                    self.assertNotWanted(out, fid)
            # mapped: checked like any form's, the switch on or off
            sources = {q: name for q, (name, _, _) in USUAL.items()}
            sources.update({"17": "the date", "5": "question 5 (Club Name)", PICKER: "the Club picker",
                            "999": "no question at all"})
            sources.update({q: "another form's sessionNotes" for q in NOTES_QIDS.values() if q != own})
            for switch in (False, True):
                with self.subTest(label, source="its own sessionNotes", wanted=switch), wanted(switch):
                    out, stop = run({fid: block(Session_Notes__c=own)}, "--form", fid, status={fid: DISABLED})
                    self.assertIsNone(stop, out)
                    self.assertMappedOk(out, fid, enabled=False)
                for got, what in sources.items():
                    with self.subTest(label, source=what, q=got, wanted=switch), wanted(switch):
                        out, stop = run({fid: block(Session_Notes__c=got)}, "--form", fid,
                                        status={fid: DISABLED})
                        self.assertEqual(stop, 1, out)
                        self.assertNotIn("integration: ok", out)
                        lines = section(out, label)
                        self.assertIn("NOT RIGHT", lines)
                        about = about_notes(bullets(lines))
                        self.assertTrue(any(reads(line, own) for line in about), lines)
                        # only the notes are wrong
                        self.assertEqual([line for line in bullets(lines) if line not in about], [], lines)
                # two questions named sessionNotes and a mapping from one of them: a problem by name
                with self.subTest(label, notes="two", wanted=switch), wanted(switch):
                    out, stop = run({fid: block(Session_Notes__c=own)}, "--form", fid,
                                    notes={fid: [own, "490"]}, status={fid: DISABLED})
                    self.assertEqual(stop, 1, out)
                    self.assertTrue(any(NOTES in line for line in about_notes(bullets(section(out, label)))), out)

    def test_a_disabled_form_is_otherwise_checked_as_today(self):
        # unmapped and DISABLED, the switch on: every other difference is still NOT RIGHT, and the
        # notes are not among its problems
        cases = {
            "Module__c reads q99; it must read q98": dict(Module__c="99"),
            "Account_Name__c reads q444 (the Club picker); it must read q5 (clubName)": dict(Account_Name__c="444"),
            "Creator__c is not mapped from a question": dict(Creator__c=None),
            "Processing_Status__c is mapped too": dict(Processing_Status__c="17"),
            "the upload field is ['19'], not [] (no photo goes to Salesforce since 2026-10-01)": dict(uploads=("19",)),
            "no connected Salesforce account": dict(account=""),
        }
        for fid in LIVE_IDS:
            label = glow_forms.LIVE[fid]
            for message, change in cases.items():
                with self.subTest(label, problem=message), wanted(True):
                    out, stop = run({fid: block(**change)}, "--form", fid, status={fid: DISABLED})
                    self.assertEqual(stop, 1, out)
                    lines = section(out, label)
                    self.assertIn("NOT RIGHT", lines)
                    self.assertIn(message, lines)
                    self.assertEqual(about_notes(bullets(lines)), [], lines)
            with self.subTest(label, case="no Salesforce integration"), wanted(True):
                out, stop = run({}, "--form", fid, status={fid: DISABLED})
                self.assertEqual(stop, 1, out)
                self.assertIn(f"{label}: NO Salesforce integration", out)
            # its connection still counts: a DISABLED form on another account is a second one
            with self.subTest(label, case="another connection"), wanted(True):
                blocks = dict(mapped_all(fid), **{fid: block(account="7654321")})
                status = dict({f: ENABLED for f in LIVE_IDS}, **{fid: DISABLED})
                out, stop = run(blocks, status=status)
                self.assertEqual(stop, 1, out)
                self.assertIn("2 different connections", out)
                lines = section(out, label)
                self.assertNotIn("NOT RIGHT", lines)
                self.assertIn(DISABLED, lines.splitlines()[0])

    def test_only_the_switch_makes_a_disabled_form_different(self):
        # the switch off: a DISABLED (or ENABLED) form reads exactly as without a status - today
        for fid in LIVE_IDS:
            own, label = NOTES_QIDS[fid], glow_forms.LIVE[fid]
            cases = {"unmapped": block(), "mapped": block(Session_Notes__c=own),
                     "notes from the date": block(Session_Notes__c="17"), "Module__c wrong": block(Module__c="99"),
                     "an upload": block(uploads=("19",)), "no integration": None}
            for name, found in cases.items():
                with self.subTest(label, case=name, wanted=False), wanted(False):
                    today = run({fid: found}, "--form", fid)
                    for status in (DISABLED, ENABLED):
                        self.assertEqual(run({fid: found}, "--form", fid, status={fid: status}), today, status)
            # the switch on: unmapped, the DISABLED form is right where the same form enabled is not
            with self.subTest(label, wanted=True), wanted(True):
                self.assertEqual(run({fid: block()}, "--form", fid)[1], 1)
                out, stop = run({fid: block()}, "--form", fid, status={fid: DISABLED})
                self.assertIsNone(stop, out)
                self.assertNotWanted(out, fid)
        # every form at once, the switch off, U.S DISABLED and unmapped: as without a status, and
        # its line is today's very line
        with wanted(False):
            today = run(mapped_all(US))
            self.assertEqual(run(mapped_all(US), status={US: DISABLED}), today)
            self.assertEqual(run(mapped_all(US), status=dict({f: ENABLED for f in LIVE_IDS}, **{US: DISABLED})), today)
        self.assertIsNone(today[1], today[0])
        self.assertIn("U.S: connection 1234567 - ok (one action, 8 fields, Account_Name__c from q5, no upload)",
                      today[0])

    # --- the committed value ------------------------------------------------------------------

    def test_the_committed_switch_is_on(self):
        """The rollout's committed end. The five live forms were settled on 2026-10-26: the
        template, Africa, Asia and Latin America map Session_Notes__c from their own sessionNotes
        (q489, q476, q457, q454, read back that day) and U.S is DISABLED (Ryan: "Skip U.S: it is
        disabled"), so NOTES_MAPPING_WANTED is committed True: from now on an enabled live form
        without the mapping is NOT RIGHT. The one test that does not pin the switch."""
        self.assertIs(getattr(ist, "NOTES_MAPPING_WANTED", None), True,
                      "tools/integration_status.py must commit NOTES_MAPPING_WANTED = True")
        out, stop = run(mapped_all(US), status={US: DISABLED})
        self.assertIsNone(stop, out)
        self.assertIn("integration: ok", out)
        self.assertNotWanted(out, US)
        out, stop = run(mapped_all(US), status={US: ENABLED})
        self.assertEqual(stop, 1, out)
        self.assertNotesMissing(out, US)


if __name__ == "__main__":
    unittest.main(verbosity=1)
