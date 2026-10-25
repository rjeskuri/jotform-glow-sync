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

Task #105 puts the field and its translations on the five live forms: the label (and a
sub-label, if NOTES_PROPS ever carries one) in every form language through what
tools/add_translations.py consumes and audits, and in the Odia, Hindi and Persian dictionaries
(NotesTranslations); NOTES_EXPECTED True for real, so a form without the field is a problem
(FormStatusNotes.test_form_status_flags_a_missing_field_once_expected); the plan beside the
ticket, docs/plans/<date>-session-notes.md, with its Rollout per form, Rollback and generated
index row (NotesPlan); the RUNBOOK section and the DECISIONS entry (NotesDocs). The live writes
themselves are Ryan's go, never a test's.
"""
import contextlib
import copy
import glob
import io
import json
import os
import re
import sys
import tempfile
import unicodedata
import unittest
from unittest import mock

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import (REPO, FakeForm, SameNameFixture, create_at, flat, link_form, move_all, read,
                            rendered)
import add_translations
import auto_sync
import form_status
from glow import backup as glow_backup
from glow import forms as glow_forms
from glow import layout
from glow import links
from glow.text import md5

TEMPLATE = glow_forms.TEMPLATE
AFRICA, ASIA, LATAM, US = (glow_forms.REGIONALS[r] for r in ("Africa", "Asia", "Latin America", "U.S"))

# Ryan's answers, pinned here independently of glow/layout.py
NOTES = "sessionNotes"
LABEL = "Additional information about this session (optional)"
LIMIT = "Letters-1000"
WANT = {"type": "control_textarea", "text": LABEL, "entryLimit": LIMIT, "required": "No"}
# the tail of a live form in render order (what sits at or below the fence)
TAIL = (links.ROSTER.name, links.PROBLEM.name, "submit2", "belowAre", "contact_ids")

# Every language a live form offers (task #105: each gets the field's strings): the ten of the
# 2026-08 translation pass, on every form, and Odia, Hindi and Persian, which the Asia form offers
# from a dictionary of their own (tools/translations_<code>.json, posted by add_language.py).
# tools/add_translations.py posts from tools/translations_additions.json alone, so the strings
# reach the Asia form's or/hi/fa only from there - as the Club Roster Form link's and the club
# guard's entries do (test/links_layout_test.py TranslationPlan.OFFERED).
OFFERED = frozenset({"ar", "es", "fr", "km", "ne", "sw", "te", "th", "ur", "vi", "or", "hi", "fa"})
OWN_DICTS = ("or", "hi", "fa")
# the script each non-Latin language is written in (and Vietnamese's diacritics): a character of
# it in every translation, so no language's entry is the English or another language's text
SCRIPTS = {"ar": "؀-ۿ", "ur": "؀-ۿ", "fa": "؀-ۿ",
           "km": "ក-៿", "ne": "ऀ-ॿ", "hi": "ऀ-ॿ",
           "te": "ఀ-౿", "th": "฀-๿", "or": "଀-୿",
           "vi": "À-ɏẠ-ỹ"}
LATIN = frozenset({"es", "fr", "sw", "vi"})          # written in Latin letters (Vietnamese with diacritics)
UNSPACED = frozenset({"th", "km"})                   # no space between words: judged by length alone
# The label ends "(optional)": each language's own word for it, which a translation of ANY other
# sentence lacks (a copy of the club guard's warning passed the script and length checks once).
# Verified word by word, 2026-10-24; the usual alternatives are allowed so a real translation is
# never rejected for its choice of word (the Arabic-script ones with either yeh, ي or ی, and
# with or without a space / ZWNJ before the second word).
OPTIONAL = {
    "es": r"opcional|optativ[oa]|no (?:es )?obligatori[oa]",
    "fr": r"facultati(?:f|ve)|optionnel(?:le)?|non obligatoire",
    "sw": r"\bhiari\b|\bsi(?:y?o)? lazima\b",
    "vi": r"tùy chọn|tuỳ chọn|không bắt buộc",
    "ar": r"اخت[يی]ار[يی]|غ[يی]ر[\s‌]?[إا](?:لزام|جبار)[يی]|غ[يی]ر[\s‌]?مطلوب",
    "ur": r"اخت[يی]ار[يی]|(?:لازم|ضرور)[يی] نہ[يی]ں|غ[يی]ر[\s‌]?(?:لازم|ضرور)[يی]",
    "fa": r"اخت[يی]ار[يی]|دلبخواه|غ[يی]ر[\s‌]?(?:الزام|اجبار)[يی]",
    "hi": r"वैकल्पिक|ऐच्छिक|अनिवार्य नहीं|आवश्यक नहीं|रूरी नहीं",
    "ne": r"वैकल्पिक|ऐच्छिक|अनिवार्य छैन|आवश्यक छैन|रु?रूरी छैन|रुरी छैन",
    "te": r"ఐచ్[ఛచ]ిక|తప్పనిసరి కాదు|ఆప్షనల్",
    "th": r"ไม่บังคับ|ไม่จำเป็น|ถ้ามี",
    "km": r"ជម្រើស|មិនចាំបាច់|ស្រេចចិត្ត|មិនតម្រូវ|បើមាន",
    "or": r"ଐଚ୍ଛିକ|ବୈକଳ୍ପିକ|ଇଚ୍ଛାଧୀନ|ବାଧ୍ୟତାମୂଳକ ନୁହେଁ|ଆବଶ୍ୟକ ନୁହେଁ",
}
assert set(OPTIONAL) == OFFERED
# What the plan's sections talk about, in the project's words - in prose, outside the commands a
# procedure quotes. A section says at least so many DISTINCT ones (a list of unrelated words, or
# one word repeated, is not a procedure): the floors are far below what a real plan says.
ROLLOUT_WORDS = (r"backups?", r"snapshots?", r"dry[ -]runs?", r"appl(?:y|ied|ies)", r"re-?reads?|read[ -]back",
                 r"verif(?:y|ied|ies|ication)", r"translations?|translated", r"dictionar(?:y|ies)", r"stores?", r"label",
                 r"field", r"forms?", r"rosters?", r"Submit", r"runner", r"browser", r"languages?", r"English", r"preview",
                 r"audit", r"untranslated", r"template", r"regions?|regional", r"CLEAN", r"in-sync", r"go", r"Ryan",
                 r"mentors?", r"POST|GET", r"merged?", r"page", r"disabled", r"notes")
ROLLBACK_WORDS = (r"snapshots?", r"remov(?:e|ed|es|al)|take[sn]? [^.;\n]{0,20}out", r"stores?", r"dictionar(?:y|ies)",
                  r"POST", r"questions?", r"backups?", r"restor(?:e|ed|es)", r"re-?reads?|read[ -]back", r"languages?",
                  r"field", r"forms?", r"translations?", r"saved", r"Revision History", r"orders?", r"mov(?:e|ed|es)",
                  r"runner", r"Ryan", r"notes", r"English")
RISK_WORDS = (r"translations?", r"dictionar(?:y|ies)", r"POST", r"replac(?:e|es|ed|ing)", r"e-?mails?", r"notification",
              r"autoresponder|confirmation", r"girls?", r"names?", r"mentors?", r"notes?", r"field", r"snapshots?",
              r"backups?", r"saved", r"re-?reads?|read[ -]back", r"dry[ -]runs?", r"refus(?:e|es|ed|al)", r"orders?",
              r"mov(?:e|ed|es)", r"Jotform", r"stores?", r"languages?", r"Submit", r"rosters?", r"forms?", r"runner",
              r"disabled", r"ties?")
# the tools a Rollout step runs (one per command: a chain of them in one backticked span is not a step)
TOOLS = ("backup_forms.py", "add_session_notes.py", "add_translations.py", "form_status.py")


def nfc(text):
    return unicodedata.normalize("NFC", text)


def says_optional(lang, text):
    """True when the text carries the language's own word for "optional" (OPTIONAL[lang]), the
    Arabic-script vowel marks set aside."""
    bare = re.sub(r"[ً-ْٰ]", "", nfc(text))
    return re.search(nfc(OPTIONAL[lang]), bare, re.I) is not None


def commands(text):
    """A doc's commands in reading order, as (line number, command): every backticked span, and
    every line of a fenced code block. Prose is never a command: `dry run` in backticks is a word."""
    out, fence = [], False
    for n, line in enumerate(text.split("\n")):
        if line.strip().startswith("```"):
            fence = not fence
        elif fence:
            if line.strip():
                out.append((n, line.strip()))
        else:
            out.extend((n, span) for span in re.findall(r"`([^`\n]+)`", line))
    return out


def prose(text):
    """What a doc says to its reader: the text outside backticked spans and fenced code blocks."""
    out, fence = [], False
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            fence = not fence
        elif not fence:
            out.append(re.sub(r"`[^`\n]*`", " ", line))
    return "\n".join(out)


def said(text, words):
    """The `words` (regexes) the prose of `text` uses, each once: the measure of being about the work."""
    plain = prose(text)
    return [w for w in words if re.search(rf"(?i)(?<![\w-])(?:{w})(?![\w-])", plain)]


def assert_about_the_work(case, text, where, words, floor):
    """A section written for its reader says what it does in the project's words: at least `floor`
    distinct `words` in its prose, outside the commands it quotes."""
    hits = said(text, words)
    case.assertGreaterEqual(len(hits), floor,
                            f"{where}: only {len(hits)} of the words a {where} uses ({', '.join(hits)}): not about this rollout")


# How a doc says what the staff notification e-mail does with the notes (the ticket's 2026-10-23
# note: Jotform e-mails can list every field, and mentors' notes can name girls). A clause naming
# the notification: a negation of the carrying, or a carrying word, decides.
NEGATED = (r"\b(?:neither|nor|omits?|omitted|without|lea(?:ve|ves|ving) out|left out|stripp?(?:ed|s)?|remov(?:e|es|ed)|"
           r"dropp?(?:ed|s)?|exclud(?:e|es|ed))\b"
           r"|\b(?:not|never|no longer)\s+(?:\w+\s+){0,3}?(?:carr\w*|includ\w*|list\w*|show\w*|appear\w*|contain\w*|"
           r"reach\w*|keep\w*|kept|go\w*|sent|send\w*|forward\w*|copied|in|there|among)\b")
CARRIES = (r"\b(?:carr(?:y|ies|ied|ying)|includ(?:e|es|ed|ing)|lists?|listed|shows?|shown|appears?|contains?|keeps?|kept|"
           r"reach(?:es|ed)?|too|as well|also|every field|all fields)\b")


def notification_verdict(text):
    """"carries" or "omits": what `text` says the staff notification e-mail does with the notes,
    read from the sentences naming the notification and an e-mail - first from their clauses
    (split at ; : and dashes, and at a comma opening a new clause) that name the notification,
    else from the whole sentence. None: not said; both: the doc contradicts itself."""
    verdicts = set()
    for piece in re.split(r"(?<=[.!?])\s+|\n(?=\s*(?:[-*]|\d+\.)\s)|\n{2,}", text):     # sentences; a bullet ends one
        sentence = flat(piece)
        if not (re.search(r"(?i)\bnotification", sentence) and re.search(r"(?i)\be-?mails?\b", sentence)):
            continue
        clauses = [c for c in re.split(r"\s*[;:]\s*|\s+[-—–]\s+|,\s+(?=(?:the|a|an|and|but|while|whereas|so|its|their|"
                                       r"his|her|our|that|which|whose)\b)", sentence)
                   if re.search(r"(?i)\bnotification", c)]
        def verdict(words):
            if re.search(f"(?i){NEGATED}", words):
                return {"omits"}
            if re.search(f"(?i){CARRIES}", words):
                return {"carries"}
            return set()

        found = set()
        for clause in clauses:
            found |= verdict(clause)
        if not found:
            # the sentence as a whole - its notification half when it also speaks of the mentor's
            # e-mail (the other e-mail's verdict is never the notification's)
            other = re.search(r"(?i)\b(?:autoresponder|auto-?reply|confirmation)\b", sentence)
            if other and other.start() > re.search(r"(?i)\bnotification", sentence).start():
                found = verdict(sentence[:other.start()])
            elif other:
                found = verdict(sentence[other.end():])
            else:
                found = verdict(sentence)
        verdicts |= found
    return verdicts


def notes_strings():
    """The field's English strings a mentor sees, which every form language translates: the
    label, and the sub-label when NOTES_PROPS carries one (today none: Ryan, 2026-10-22)."""
    props = layout.NOTES_PROPS
    return [s for s in (props["text"], props.get("subLabel") or "") if s.strip()]


def healthy_but_for_the_notes(questions):
    """audit_layout's lines on a form that has no notes field, the field's absence set aside
    (NOTES_EXPECTED off for the call): [] = nothing else is wrong with its layout."""
    with mock.patch.object(layout, "NOTES_EXPECTED", False):
        return layout.audit_layout(questions)


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
        self.assertIs(layout.NOTES_EXPECTED, True)         # on every live form (task #105): absent is a problem
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
                    self.assertEqual(healthy_but_for_the_notes(base), [])    # healthy, just no room
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
            self.assertEqual(healthy_but_for_the_notes(qs), [], name)    # nothing else wrong with the layout
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
                self.assertEqual(healthy_but_for_the_notes(qs), [])       # the form is healthy otherwise
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
        self.assertIn("session notes: absent", self.printed(absent))
        with mock.patch.object(layout, "NOTES_EXPECTED", False):          # before task #105 placed it: no problem
            self.assertEqual(self.notes_problems(self.report(absent)), [])
            self.assertEqual(layout.audit_layout(absent), [])
        # live, the flag as shipped (test_form_status_flags_a_missing_field_once_expected)
        self.assertEqual(len(self.notes_problems(self.report(absent))), 1)
        self.assertEqual(self.notes_problems(self.report(good)), [])

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

    def test_form_status_flags_a_missing_field_once_expected(self):
        # task #105 put the field on all five forms and set NOTES_EXPECTED for real (no mock
        # here): a form without it has one audit_layout line, naming the field and the tool that
        # adds it, which form_report carries (one PROBLEM more than the same form with the field,
        # so never CLEAN) and the runner's verify sees (never in-sync without it); the printed
        # line says absent. Three layouts: one link, two links, no link.
        self.assertIs(layout.NOTES_EXPECTED, True)
        for kw, gap in (({}, 3), ({"roster": True}, 2), ({"problem": False}, 1)):
            with self.subTest(**kw, gap=gap):
                absent = notes_form(gap=gap, **kw)
                self.assertEqual(layout.notes_fields(absent), [])
                (line,) = layout.audit_layout(absent)
                self.assertIn(NOTES, line)
                self.assertIn("add_session_notes.py", line)                     # the fix, named
                self.assertEqual(layout.misplaced(absent), [])                  # absence is the only problem
                rep = self.report(absent)
                self.assertEqual(self.notes_problems(rep), [line])
                self.assertEqual(rep["session_notes"], [])
                good = self.report(notes_form(gap=gap, notes=True, **kw))       # the same form, the field on it
                self.assertEqual(self.notes_problems(good), [])
                self.assertEqual(len(rep["rule_problems"]), len(good["rule_problems"]) + 1)
                self.assertEqual([p for p in rep["rule_problems"] if p not in good["rule_problems"]], [line])
                out = self.printed(absent)
                self.assertIn("session notes: absent", out)
                self.assertNotIn("CLEAN", out)
                counted = int(re.search(r"→ (\d+) PROBLEM\(S\)", out).group(1))
                with_field = self.printed(notes_form(gap=gap, notes=True, **kw))
                self.assertIn("session notes: present (q700)", with_field)
                self.assertEqual(counted, int(re.search(r"→ (\d+) PROBLEM\(S\)", with_field).group(1)) + 1)
                clean = dict(rep, rule_problems=self.notes_problems(rep), languages=["a"] * 12,
                             region_check={"missing_from_form": [], "not_in_roster": [], "rosters_out_of_date": []})
                problems, _ = auto_sync.verify_report(clean)
                self.assertTrue(any(NOTES in p for p in problems), problems)
                self.assertEqual(auto_sync.verify_report(dict(clean, rule_problems=self.notes_problems(good)))[0], [])

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


# ---------------------------------------------------------------------------------------------
# Task #105: the field and its translations on the five live forms. Nothing below writes to a
# form: the translations are checked as the tool consumes them, the plan and the docs as text.

class NotesTranslations(unittest.TestCase):
    """The field's strings in every form language: tools/translations_additions.json as
    tools/add_translations.py consumes it (load_additions, plan_additions, merge) and audits it
    (--audit), and the Odia, Hindi and Persian dictionaries of their own."""

    def setUp(self):
        self.raw = json.loads(read(os.path.join(REPO, "tools", "translations_additions.json")))
        self.additions = add_translations.load_additions()                  # what the tool posts
        self.dicts = {lang: json.loads(read(os.path.join(REPO, "tools", f"translations_{lang}.json")))
                      for lang in OWN_DICTS}

    @staticmethod
    def store(*langs):
        """A form's translation store with these languages (empty) and the two English source maps."""
        return {**{lang: {} for lang in langs}, "base": {}, "en": {}}

    def other_texts(self, strings):
        """{language: every OTHER entry's translation in it}: tools/translations_additions.json
        (every entry but the field's, as written) and the Odia, Hindi and Persian dictionaries.
        The field's text is none of them, and holds none of them (a sentence of theirs - the
        club guard's warning was copied under the label once - nor a label of ten characters or
        more with the word for "optional" appended)."""
        pool = {lang: [] for lang in OFFERED}
        for english, entry in self.raw.items():
            if english in strings or not isinstance(entry, dict):
                continue
            for lang, text in entry.items():
                if lang in pool:
                    pool[lang].append(text)
        for lang in OWN_DICTS:
            for english, text in self.dicts[lang].items():
                if english not in strings and not english.startswith("_") and isinstance(text, str):
                    pool[lang].append(text)
        return pool

    def test_every_form_language_has_the_notes_strings(self):
        strings = notes_strings()
        self.assertEqual(strings[0], LABEL)                                 # the label as Ryan spelled it
        others = self.other_texts(strings)
        for lang in OFFERED:
            self.assertGreaterEqual(len(others[lang]), 10, lang)            # the pool is real: the 2026-08 pass
        for english in strings:
            with self.subTest(string=english):
                self.assertIn(english, self.raw, "tools/translations_additions.json: keyed by the exact English")
                entry = self.raw[english]
                self.assertEqual(set(entry) - {"_note"}, OFFERED)           # every language a live form offers
                # written by us, not native-reviewed: said in the note, as the link's and the
                # guard's entries say it (the reviewer knows what to check)
                note = entry.get("_note", "")
                self.assertRegex(note, r"(?i)\bnot native[ -]reviewed\b")
                self.assertRegex(note, r"(?i)\b(written|drafted|translated) by (us|claude)\b")
                self.assertIn(english, self.additions)                      # the tool reads it as it is
                posted = self.additions[english]
                self.assertEqual({k: v for k, v in posted.items() if k != "_note"},
                                 {k: v for k, v in entry.items() if k != "_note"})
                texts = {}
                for lang in sorted(OFFERED):
                    text = posted[lang]
                    self.assertIsInstance(text, str, lang)
                    self.assertTrue(text.strip(), lang)
                    self.assertEqual(text, text.strip(), lang)
                    self.assertNotEqual(flat(text).lower(), flat(english).lower(), lang)   # a translation
                    self.assertNotIn(flat(english).lower(), flat(text).lower(), lang)      # not the English with more
                    self.assertFalse(set("&<>{}") & set(text), lang)                       # plain text, no {n}
                    self.assertNotRegex(text, r"\d", lang)                                 # the label has no number
                    # a sentence of the label's size: at least 40% of its characters, and, where
                    # the language puts spaces between words, at least three words
                    self.assertGreaterEqual(len(text), 0.4 * len(english), (lang, text))
                    if lang not in UNSPACED:
                        self.assertGreaterEqual(len(text.split()), 3, (lang, text))
                    letters = [c for c in text if c.isalpha()]
                    self.assertGreaterEqual(len(letters), 10, (lang, text))
                    if lang in LATIN:                                                      # Latin letters only
                        self.assertTrue(all(ord(c) < 0x250 or "Ạ" <= c <= "ỹ" for c in letters), (lang, text))
                    if lang in SCRIPTS:                                                    # in its own script
                        own = [c for c in letters if re.match(f"[{SCRIPTS[lang]}]", c)]
                        if lang == "vi":
                            self.assertGreaterEqual(len(own), 2, (lang, text))             # its diacritics
                        else:
                            self.assertGreaterEqual(len(own), 0.75 * len(letters), (lang, text))
                    # a translation of THIS string: the language's own word for "(optional)" -
                    # OPTIONAL[lang], alternatives included - which no other string of the form has
                    if english == LABEL:
                        self.assertTrue(says_optional(lang, text), (lang, text, f"no word for optional: {OPTIONAL[lang]}"))
                    # …and not another entry's translation in that language, whole or in part:
                    # neither equal to one, nor inside one (a clause of a longer sentence), nor
                    # holding one of ten characters or more (a label with "optional" appended);
                    # a short word such as the language's "session" may of course appear in it
                    mine = nfc(flat(text)).lower()
                    for other in others[lang]:
                        theirs = nfc(flat(other)).lower()
                        self.assertNotEqual(mine, theirs, (lang, "another entry's translation"))
                        self.assertNotIn(mine, theirs, (lang, text, "part of another entry's translation"))
                        if len(theirs) >= 10:
                            self.assertNotIn(theirs, mine, (lang, text, f"holds another entry's translation: {other}"))
                    texts[lang] = text
                self.assertEqual(len(set(texts.values())), len(OFFERED), "two languages share one text")
                # the Odia, Hindi and Persian dictionaries carry the same text (add_language.py
                # posts them when a form gets the language): one translation, whichever tool posts it
                for lang in OWN_DICTS:
                    self.assertIn(english, self.dicts[lang], lang)
                    self.assertEqual(self.dicts[lang][english], posted[lang], lang)
        # the sub-label: translated if and only if the field has one (today: none)
        sub = layout.NOTES_PROPS.get("subLabel") or ""
        self.assertEqual(sub.strip() in self.raw, bool(sub.strip()))

    def test_the_tool_posts_the_strings_to_every_language_a_form_offers_and_audits_none_untranslated(self):
        strings = notes_strings()
        for english in strings:
            self.assertIn(english, self.additions, "tools/translations_additions.json lacks the string")
        # (form, its questions with the field, the languages its store holds): the Asia form with
        # Odia, Hindi and Persian too; the template with the ten; a store with three
        cases = ((ASIA, notes_form(gap=2, notes=("812", 15), roster=True), OFFERED),
                 (TEMPLATE, notes_form(gap=3, notes=True), OFFERED - set(OWN_DICTS)),
                 (AFRICA, notes_form(gap=1, notes=("905", 15), problem=False), {"es", "fr", "sw"}))
        for fid, qs, langs in cases:
            with self.subTest(form=fid):
                (q,) = layout.notes_fields(qs)
                store = self.store(*langs)
                payload, sources = add_translations.plan_additions(qs, store, self.additions)
                self.assertLessEqual(set(payload), langs)              # a language the form lacks is never posted
                for english in strings:
                    key = md5(english)
                    self.assertEqual(sources[key], english)             # base and en get the source (rule 9)
                    for lang in langs:
                        self.assertEqual(payload[lang][key], self.additions[english][lang], (fid, lang))
                merged = add_translations.merge(store, payload, sources)
                for source in ("base", "en"):
                    for english in strings:
                        self.assertEqual(merged[source][md5(english)], english, source)
                # --audit: the field's strings are visible strings of the form, found at the
                # field, and once the merged store is on the form none is untranslated in any of
                # its languages (the audit's own test: md5(string) in the language's dictionary)
                visible = add_translations.visible_strings(qs)
                self.assertEqual(visible[LABEL], {f"q{q['qid']}.text"})
                for english in strings:
                    self.assertIn(english, visible)
                for lang in langs:
                    missing = sorted(s for s in visible if md5(s) not in merged.get(lang, {}))
                    self.assertEqual([s for s in missing if s in strings], [], (fid, lang))
                    self.assertNotIn("Girl", "".join(merged[lang].values()))   # no roster name in a posted language
        # a form without the field gets none of its keys
        payload, sources = add_translations.plan_additions(notes_form(gap=3), self.store(*OFFERED), self.additions)
        keys = set(sources) | {k for d in payload.values() for k in d}
        for english in strings:
            self.assertNotIn(md5(english), keys)


class NotesPlan(unittest.TestCase):
    """docs/plans/<date>-session-notes.md: the live rollout of the field and its translations,
    form by form on Ryan's go, its rollback, and the generated index (make docs-index)."""

    PATTERN = os.path.join(REPO, "docs", "plans", "*-session-notes.md")
    FORMS = (TEMPLATE, AFRICA, ASIA, LATAM, US)                          # the Rollout's order

    def path(self):
        found = sorted(glob.glob(self.PATTERN))
        self.assertEqual(len(found), 1, f"one docs/plans/<date>-session-notes.md expected, found {found}")
        return found[0]

    def sections(self):
        """({heading word: body}, the whole text) of the plan's `## ` sections, comments removed."""
        text = re.sub(r"<!--.*?-->", "", read(self.path()), flags=re.S)
        parts = re.split(r"^## ", text, flags=re.M)[1:]
        return {p.split("\n", 1)[0].split()[0].strip(":"): (p.split("\n", 1)[1] if "\n" in p else "")
                for p in parts}, text

    def runs(self, cmds, tool, fid, apply):
        """Where, in `cmds` (reading order), the tool runs on the form: its commands carrying
        `--form <id>`, with --apply (apply=True) or without it (the dry run); never a --remove,
        and never a chain - a span naming two of the tools is not one command."""
        who, found = glow_forms.LIVE[fid], []
        for i, (_, cmd) in enumerate(cmds):
            if tool not in cmd or not re.search(rf"--form {fid}\b", cmd):
                continue
            self.assertEqual([t for t in TOOLS if t != tool and t in cmd], [],
                             f"{who}: one command per backticked span or code line, not a chain: {cmd}")
            if "--remove" not in cmd and ("--apply" in cmd) == apply:
                found.append(i)
        return found

    def form_slices(self, rollout):
        """{form id: its part of the Rollout}: from the line that first names the form to the
        line that first names the next one (the last runs to the end). The forms come in the
        Rollout's order - the template, Africa, Asia, Latin America, U.S - each named once
        before the next."""
        starts = []
        for fid in self.FORMS:
            self.assertIn(fid, rollout, glow_forms.LIVE[fid])
            starts.append(rollout.rfind("\n", 0, rollout.index(fid)) + 1)
        self.assertEqual(starts, sorted(starts), "the Rollout names the template first, then Africa, Asia, "
                                                 "Latin America and U.S")
        self.assertEqual(len(set(starts)), len(starts), "each form's steps start on a line of their own")
        ends = starts[1:] + [len(rollout)]
        return {fid: rollout[a:b] for fid, a, b in zip(self.FORMS, starts, ends)}

    def assert_procedure(self, fid, part):
        """One form's steps, each a command of its own (a backticked span or a code line)
        carrying `--form <id>`, in this order: the backup; the notes tool's dry run - its command
        without --apply - then its --apply; the translations tool's dry run, then its --apply;
        form_status --rendered, and CLEAN said after it. The words "dry run" are no run."""
        who, cmds = glow_forms.LIVE[fid], commands(part)
        listed = [c for _, c in cmds]
        backup = self.runs(cmds, "backup_forms.py", fid, apply=False)
        self.assertTrue(backup, f"{who}: no `backup_forms.py --form {fid}` command: {listed}")
        at = backup[0]
        for tool in ("add_session_notes.py", "add_translations.py"):
            dry = [i for i in self.runs(cmds, tool, fid, apply=False) if i > at]
            self.assertTrue(dry, f"{who}: no dry run of {tool} - its command with --form {fid} and without --apply - "
                                 f"after the step before it: {listed}")
            applied = [i for i in self.runs(cmds, tool, fid, apply=True) if i > dry[0]]
            self.assertTrue(applied, f"{who}: no `{tool} --form {fid} … --apply` command after its dry run: {listed}")
            at = applied[0]
        status = [i for i in self.runs(cmds, "form_status.py", fid, apply=False) if i > at and "--rendered" in cmds[i][1]]
        self.assertTrue(status, f"{who}: no `form_status.py --form {fid} --rendered` after the translations' --apply: {listed}")
        # the verdict that proves the writes landed, said to the reader (not a word in a command)
        self.assertRegex(prose(part), r"\bCLEAN\b", f"{who}: CLEAN not said in its steps")

    def test_the_plan_carries_a_plans_frontmatter_and_is_in_the_generated_index(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        path = self.path()
        name = os.path.basename(path)
        keys, h1 = docs_index.frontmatter(read(path))
        template, _ = docs_index.frontmatter(read(os.path.join(REPO, "docs", "templates", "plan.md")))
        self.assertLessEqual(set(keys), set(template))                       # no key a plan does not carry
        for key_ in ("title", "author", "status", "created", "intent"):
            self.assertTrue(keys.get(key_, "").partition("#")[0].strip(), key_)
        word, problem = docs_index.status_of(keys["status"])
        self.assertIsNone(problem, keys["status"])
        self.assertEqual(keys["created"], name[:10])                         # the date in its name
        self.assertGreaterEqual(name[:10], "2026-10-22")                      # not before the ticket
        self.assertRegex(keys["title"] + " " + h1, r"(?i)session[ -]notes|notes field")
        done = keys.get("done", "").partition("#")[0].strip()
        if word == "done":
            self.assertRegex(done, r"^\d{4}-\d\d-\d\d$")
        else:
            self.assertEqual(done, "")
        # the index (make docs-index) lists it with that status and is a fresh generation
        plans, problems = docs_index.entries("plans")
        self.assertEqual(problems, [])
        (entry,) = [p for p in plans if p["name"] == name]
        self.assertEqual(entry["status"], word)
        intents, _ = docs_index.entries("intent")
        index = read(os.path.join(REPO, "docs", "plans", "README.md"))
        self.assertEqual(index, docs_index.render(plans, intents))
        self.assertEqual(len([l for l in index.splitlines() if f"({name})" in l]), 1)

    def test_the_plan_has_rollout_rollback_risks_and_result_in_that_order(self):
        sections, text = self.sections()
        headings = re.findall(r"^## (.+)$", text, re.M)
        names = ("Rollout", "Rollback", "Risks", "Result")
        for name in names:
            self.assertEqual(len([h for h in headings if h.startswith(name)]), 1, name)
        order = [next(i for i, h in enumerate(headings) if h.startswith(n)) for n in names]
        self.assertEqual(order, sorted(order))
        # prose about this rollout, not tokens or filler: the project's words, outside the commands
        assert_about_the_work(self, sections["Rollout"], "Rollout", ROLLOUT_WORDS, 10)
        assert_about_the_work(self, sections["Rollback"], "Rollback", ROLLBACK_WORDS, 6)
        assert_about_the_work(self, sections["Risks"], "Risks", RISK_WORDS, 6)
        # the plan is about this field: its name, its tools, the flag, the ticket, the label
        for word in (NOTES, "add_session_notes.py", "add_translations.py", "NOTES_EXPECTED", "#105", LABEL):
            self.assertIn(word, text)
        # Risks: at least two, each a bullet with its mitigation; among them a translations POST
        # replacing a language's dictionary (CLAUDE.md rule 9) and the notification e-mails that
        # list every field - mentors' notes can name girls (the ticket's 2026-10-23 note)
        risks = sections["Risks"]
        bullets = [b for b in re.split(r"\n(?=- |\d+\. )", "\n" + risks.strip()) if b.strip()]
        self.assertGreaterEqual(len(bullets), 2, risks)
        for b in bullets:
            self.assertGreaterEqual(len(b.split()), 12, b)                    # a risk and what is done about it
        self.assertRegex(risks, r"(?i)translation")
        self.assertRegex(risks, r"(?i)notification|e-?mail")
        mitigations = {m for m in ("saved", "snapshot", "backup", "re-read", "read back", "dry run", "--remove", "refuses")
                       if m in risks.lower()}
        self.assertGreaterEqual(len(mitigations), 2, risks)
        # Result: the template's placeholder gone; while the plan is not done it says the rollout
        # has not run and awaits Ryan's go (true: the live writes come after this branch); done,
        # it is the record of the rollout (dates, every form CLEAN, Ryan's go)
        result = sections["Result"]
        self.assertTrue(result.strip())
        self.assertIsNone(re.search(r"<[a-z][^>]*>|\bTODO\b|\bTBD\b|\bXXX\b", result), result)
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        word = docs_index.status_of(docs_index.frontmatter(read(self.path()))[0]["status"])[0]
        if word == "done":
            self.assertGreaterEqual(len(result.split()), 60, result)
            self.assertRegex(result, r"2026-\d\d-\d\d")
            self.assertIn("CLEAN", result)
            for fid in self.FORMS:
                self.assertIn(fid, result, glow_forms.LIVE[fid])
            self.assertRegex(result, r"(?i)\bryan\b")
        else:
            self.assertRegex(result, r"(?i)\b(not (yet )?(run|applied|done|started|happened)|has not|hasn't|"
                                     r"pending|awaits?|awaiting|waits? for|to come|yet to)\b")
            self.assertRegex(result, r"(?i)\bryan\b")                          # whose go it waits for
        self.assertNotIn("AUTO_SYNC_APPLY=", text)                             # no step toggles the runner

    def test_the_plan_backs_up_adds_translates_and_verifies_each_form(self):
        sections, _ = self.sections()
        rollout, rollback = sections["Rollout"], sections["Rollback"]
        # each step on Ryan's go; the template first, then Africa, Asia, Latin America and U.S -
        # every form by its id, in that order
        self.assertRegex(rollout, r"(?i)ryan.s\b.{0,30}\bgo\b")
        self.assertRegex(rollout, r"(?i)\btemplate\b")
        for region in ("Africa", "Asia", "Latin America", "U.S"):
            self.assertIn(region, rollout)
        # per form - its own lines, in the Rollout's order - the same procedure, each command
        # naming the form: the backup; the notes tool's dry run, then its --apply; the
        # translations tool's dry run, then its --apply; form_status --rendered, CLEAN
        parts = self.form_slices(rollout)
        for fid, part in parts.items():
            with self.subTest(form=glow_forms.LIVE[fid]):
                self.assert_procedure(fid, part)
        # the audit over the forms (nothing untranslated), the public page in English and another
        # language with nothing submitted, and the runner's next run in-sync with the flag on
        self.assertTrue(any("add_translations.py" in c and "--audit" in c for _, c in commands(rollout)),
                        "no `add_translations.py … --audit` command in the Rollout")
        self.assertRegex(rollout, r"(?i)browser|public page|preview")
        self.assertRegex(rollout, r"(?i)\b(never|not|nothing|no)\b[^.\n]{0,40}\bsubmit")
        self.assertIn("in-sync", rollout + sections.get("Proof", ""))
        # the rollback: the field out by the tool's --remove --apply (a command); each language
        # back from the store the translations tool saved before its POST (backups/translations/)
        self.assertTrue(any("add_session_notes.py" in c and "--remove" in c and "--apply" in c
                            for _, c in commands(rollback)), "no `add_session_notes.py … --remove --apply` command")
        self.assertIn("backups/translations", rollback)


class NotesDocs(unittest.TestCase):
    """docs/RUNBOOK.md "Session notes on the attendance forms" and docs/DECISIONS.md once the
    rollout has its plan: checkable facts only - the plan linked, the translations in the
    procedure, the e-mail decision, the decision's label, limit, place and no rule."""

    RUNBOOK = os.path.join(REPO, "docs", "RUNBOOK.md")
    HEADING = "\n## Session notes on the attendance forms\n"

    def section(self):
        doc = read(self.RUNBOOK)
        self.assertEqual(doc.count(self.HEADING), 1, "keep the RUNBOOK heading word for word")
        return doc.split(self.HEADING, 1)[1].split("\n## ", 1)[0]

    def bullet(self, section, name):
        found = [l for l in section.split("\n") if l.startswith(f"- **{name}:**")]
        self.assertEqual(len(found), 1, f"one `- **{name}:**` header bullet")
        return found[0]

    def test_the_runbook_section_rolls_the_translations_out_with_the_field(self):
        section = self.section()
        status = self.bullet(section, "Status")
        plan = re.search(r"plans/(\d{4}-\d\d-\d\d-session-notes\.md)", status)   # links the plan
        self.assertTrue(plan, status)
        self.assertIn("#105", status)
        self.assertNotIn("built, not live", status)                            # #104's wording: superseded
        # …and says where the plan stands, in the plan's own status word (done: live, with its date)
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import docs_index
        plan_path = os.path.join(REPO, "docs", "plans", plan.group(1))
        self.assertTrue(os.path.exists(plan_path), plan_path)
        word = docs_index.status_of(docs_index.frontmatter(read(plan_path))[0]["status"])[0]
        self.assertRegex(status, r"(?i)\b" + word.replace("-", "[ -]") + r"\b", f"the Status bullet says {word!r}")
        if word == "done":
            self.assertRegex(status, r"(?i)\blive\b")
            self.assertRegex(status, r"2026-\d\d-\d\d")
        # the Apply bullet: the translations tool's command is a step of the rollout, the field's
        # English-only interim is gone
        apply = self.bullet(section, "Apply")
        self.assertRegex(apply, r"python3 tools/add_translations\.py( --\w+( \S+)?)*")
        self.assertIn("--form", apply)
        self.assertNotIn("second step", apply)
        self.assertNotIn("until then every language shows it in English", section)
        self.assertIn("--audit", self.bullet(section, "Verify"))
        rollback = self.bullet(section, "Rollback")
        self.assertIn("--remove --apply", rollback)
        self.assertRegex(rollback, r"backups/translations|translation store")
        text = flat(section)
        for word_ in ("tools/add_translations.py", "tools/form_status.py", "--rendered"):
            self.assertIn(word_, text)
        # the e-mails: Jotform's notification and autoresponder can list every field, and
        # mentors' notes can name girls (the ticket's 2026-10-23 note) - the section names both,
        # the staff notification e-mail and the mentor's confirmation / autoresponder, and says
        # in a clause what the notification does with the notes: carries or omits
        # (notification_verdict reads it; the DECISIONS entry says the same:
        # test_the_runbook_and_decisions_agree_on_the_notification_email)
        self.assertRegex(text, r"(?i)\bnotification\b[^.]*\be-?mails?\b|\be-?mails?\b[^.]*\bnotification\b",
                         "no sentence about the staff notification e-mail")
        self.assertRegex(text, r"(?i)\b(autoresponder|auto-?reply|confirmation)\b", "the mentor's e-mail is not decided")
        verdict = notification_verdict(self.section())
        self.assertEqual(len(verdict), 1, "one clause says what the staff notification e-mail does with the notes - "
                                          f"carries or omits - read: {verdict or 'nothing'}")
        self.assertNotIn("Girl ", text)                                        # fictional names stay in the tests

    def decisions_entry(self):
        """The one dated docs/DECISIONS.md entry (2026-10-22 or later) whose heading names the session notes."""
        doc = read(os.path.join(REPO, "docs", "DECISIONS.md"))
        entries = re.split(r"^### ", doc, flags=re.M)[1:]
        ours = [e for e in entries if re.match(r"\d{4}-\d\d-\d\d", e) and e[:10] >= "2026-10-22"
                and re.search(r"(?i)session[ -]notes", e.split("\n", 1)[0])]
        self.assertEqual(len(ours), 1, "one dated DECISIONS entry whose heading names the session notes")
        return ours[0]

    # what each bullet of the entry is about - the project's words, two of them at least (one for
    # Consequences): a reason of the domain, a concrete alternative, a file or tool the decision reached
    WHY_WORDS = (r"mentors?", r"girls?", r"Salesforce", r"rules?", r"required", r"hidden", r"limit", r"characters",
                 r"rosters?", r"Submit", r"sync", r"optional", r"free[ -]text", r"translat\w*")
    REJECTED_WORDS = (r"sub-?label", r"required", r"rules?", r"\d[\d,]* characters", r"above", r"below", r"hidden",
                      r"translations?", r"Salesforce", r"dropdown", r"per[ -]girl", r"sub-?heading")
    CONSEQUENCE_WORDS = (r"glow/layout\.py", r"add_session_notes\.py", r"add_translations\.py", r"form_status",
                         r"NOTES_EXPECTED", r"RUNBOOK", r"auto_sync")

    def test_decisions_records_the_label_the_limit_the_place_and_no_rule(self):
        ours = self.decisions_entry()
        entry = flat(ours)
        self.assertIn(LABEL, entry)                                            # the label, verbatim
        self.assertRegex(entry, r"1,000|1000|Letters-1000")                    # the limit
        self.assertRegex(entry, r"(?i)after the last roster|above the links|above (the )?Submit")   # the place
        self.assertRegex(entry, r"(?i)\bno rule\b|without (a |any )?rule|never [^.;]{0,30}\brule")   # no rule
        self.assertRegex(entry, r"(?i)sub-?label")                             # Ryan's "no sub-label"
        # the shape every entry since 2026-10 has: the decision, then Why, Rejected, Consequences -
        # each said, not named (a reason of fifteen words; alternatives; what follows from it)…
        body = ours.split("\n", 1)[1]
        bullets = {}
        for name, floor in (("Why", 15), ("Rejected", 8), ("Consequences", 8)):
            m = re.search(rf"- \*\*{name}:\*\*(.*?)(?=\n- \*\*|\Z)", body, re.S)
            self.assertTrue(m, f"no `- **{name}:**` bullet")
            self.assertGreaterEqual(len(m.group(1).split()), floor, (name, m.group(1)))
            bullets[name] = m.group(1)
        self.assertRegex(flat(body.split("- **Why:**", 1)[0]), r"(?i)\bRyan\b")  # whose answers (2026-10-22)
        # …and each about this decision, not a list of unrelated words: Why names reasons of the
        # domain, Rejected names concrete alternatives, Consequences names what the decision reached
        for name, words, floor in (("Why", self.WHY_WORDS, 2), ("Rejected", self.REJECTED_WORDS, 2),
                                   ("Consequences", self.CONSEQUENCE_WORDS, 1)):
            hits = [w for w in words if re.search(rf"(?i)(?<![\w/.-])(?:{w})(?![\w-])", bullets[name])]
            self.assertGreaterEqual(len(hits), floor, (name, hits, bullets[name]))
        # the e-mail decision (the ticket's 2026-10-23 note), per e-mail: the entry names the staff
        # notification and the mentor's confirmation / autoresponder, and says in a clause what the
        # notification does with the notes - carries or omits (the RUNBOOK says the same:
        # test_the_runbook_and_decisions_agree_on_the_notification_email)
        self.assertRegex(entry, r"(?i)\bnotification\b[^.]*\be-?mails?\b|\be-?mails?\b[^.]*\bnotification\b",
                         "no sentence about the staff notification e-mail")
        self.assertRegex(entry, r"(?i)\b(autoresponder|auto-?reply|confirmation)\b", "the mentor's e-mail is not decided")
        verdict = notification_verdict(ours)
        self.assertEqual(len(verdict), 1, "one clause says what the staff notification e-mail does with the notes - "
                                          f"carries or omits - read: {verdict or 'nothing'}")

    def test_the_runbook_and_decisions_agree_on_the_notification_email(self):
        # Jotform's staff notification e-mail lists every field by default, and mentors' notes can
        # name girls: whether it carries the notes is one decision, said in the RUNBOOK section
        # (what staff see) and in the DECISIONS entry (why) - the same verdict in both
        runbook, decisions = notification_verdict(self.section()), notification_verdict(self.decisions_entry())
        self.assertEqual(len(runbook), 1, f"RUNBOOK: the staff notification e-mail carries or omits the notes - read {runbook or 'nothing'}")
        self.assertEqual(len(decisions), 1, f"DECISIONS: the staff notification e-mail carries or omits the notes - read {decisions or 'nothing'}")
        self.assertEqual(runbook, decisions, "the RUNBOOK and the DECISIONS entry disagree on the staff notification e-mail")


if __name__ == "__main__":
    unittest.main(verbosity=1)
