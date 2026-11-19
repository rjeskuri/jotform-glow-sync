#!/usr/bin/env python3
"""
Offline tests for the `merge` decision and subcommand of `tools/sf_backfill.py` (ticket #244; found by
`make py`'s unittest discovery): a back-fill session for a club and day Salesforce already has, sent on
Ryan's word as ONE batch that the processor (since 2026-10-24, ticket #108) merges into the day's
original batch. Everything here is fictional: clubs, girls and ids are invented; the girls come from
test/fixtures/make_fixture.py's pools. The shared fake org (test/helpers/fake_org.py) is the processor
with its merge rule.

The contract these tests pin:
- decisions.csv takes the clause `merge` (no value). `merge <anything>` is refused, `skip` cannot be
  combined with it, it combines with `use` and `accept`, and the refusal listing the clauses names it.
- plan: a session with `merge` whose club and day Salesforce has with a Success batch AND attendance rows
  is neither held `salesforce_has_different_count` nor skipped `already_in_salesforce`; every other hold
  applies as for any session (the releasable ones released by `accept`); when nothing holds it, it is a
  planned merge - never in the `send` queue (plan.json's "sessions"), never listed or sent by `send`.
  A `merge` on a day without a Success batch with rows is held `merge_without_original`, which `accept`
  cannot release. The printed report counts the planned merges. Without `merge` nothing changes.
- `merge` (dry run) and `merge --apply` need --vpn-off; both refuse a plan whose resolved.json or
  decisions.csv changed since; neither cares how old the fetch is. Per planned merge it reads the club and
  day live and predicts by the processor's rule (the original: the oldest Success batch of the day):
  skipped `no_success_original`, `original_not_mergeable` (a Partner report, or no rows of its own),
  `module_differs` (case ignored), `adds_nobody`; else the girls ticked without a row that day and how
  many of them get a new contact. The dry run prints one line per planned merge with its key, club,
  date, the original's Name and Id and the counts names ticked / girls to add / new contacts (a skipped
  one: its key and `skipped, <reason>`), a totals line and `dry run: nothing was sent`.
- `--apply`: one insert per merge (its names `, `-joined, module/week/year, no fuzzy matching, Creator__c
  `Jotform back-fill...` identifying the session), the day read again first (a changed prediction sends
  nothing for it), then read back: Success `merged into <original id>` (18 or 15 characters), no rows or
  count of its own, the original grew by exactly the predicted rows inside the batch's window, the club
  by exactly the predicted contacts, the original's Girls_Present__c its rows, no other batch of the day
  inside the window - `ok`; anything else `CHECK`, the run stops and `--apply` refuses until `close`.
  A lost answer or read-back is `unknown`, settled by the marker before the next `--apply` sends; an HTTP
  4xx is `not_saved` and nothing more is sent. A merge already `ok` is never sent again; a skipped one
  stays planned for a later run. `--only <key>` and `--limit N` narrow it.
- Ruling (file names, a reversible choice of this test): the merges' ledger is MERGE_LEDGER
  (merge_ledger.csv, at least MERGE_COLS, rows `sending` then `ok` / `CHECK` / `unknown` / `not_saved`,
  closed `accepted` / `removed`) and the rollback list MERGE_ADDED (merge_added.csv: each attendance row
  added and each contact created, by id, on a line naming its merge's key or batch id), both in the
  back-fill folder, owner-only, apart from ledger.csv. `status` reports the merges and the rollback.
- Never a girl's name, never a status message's text, printed or written (plan.json, resolved.json and
  send's sent_names.json hold names by design and are the only exceptions; a merge never writes the last).
"""
import csv
import datetime
import os
import re
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import sf_backfill as bf                                     # noqa: E402
from glow.salesforce import PARTNER_RECORD_TYPE              # noqa: E402
from helpers.fake_org import DUPLICATE, ME                   # noqa: E402
from sf_backfill_test import PARTNER, FakeOrg, Harness, account, row   # noqa: E402
sys.path.insert(0, os.path.join(REPO, "test", "fixtures"))
import make_fixture                                          # noqa: E402  the invented name pools

SUNRISE, RIVER, PILOT = "001000000000000CAA", "001000000000000CBB", "001000000000000CCC"
CLUBS = {SUNRISE: "Sunrise Club", RIVER: "River Club", PILOT: "Pilot Club"}
# girls: invented, from the fixture's pools; distinct surnames, so no two look alike to the duplicate rule
A, B, C, D, E, F, G, H, I, J = [f"{make_fixture.FIRST[i]} {make_fixture.LAST[i]}" for i in range(10)]
SURNAMES = list(make_fixture.LAST)
D1, D2 = "2026-10-03", "2026-10-10"
K1, K2, K3 = f"{SUNRISE}|{D1}", f"{RIVER}|{D2}", f"{PILOT}|{D1}"
MODULE = "Self Advocacy"
MERGE = "merge; accept club_has_earlier_contacts"   # every merge day's club has contacts this run did not make
# what each planned merge adds, by the processor's rule, worked out by hand from history() and reports():
#   K1 Sunrise 10-03: ticks A B D E (report 101) + C F (102) = 6; the day has A B C -> adds D E F = 3;
#      F has a contact (Sunrise 09-26), D and E get new ones = 2
#   K2 River 10-10: ticks G I = 2, as many as the day's 2 rows (G H) -> adds I = 1, new 1
EXPECT = {K1: (6, 3, 2), K2: (2, 1, 1)}
MERGE_LEDGER, MERGE_ADDED = "merge_ledger.csv", "merge_added.csv"
MERGE_COLS = {"key", "status", "batch_id", "original_id", "rows_added", "contacts_created"}
MARKER = "Jotform back-fill"
VPN = "check that no VPN is on"
WRITTEN = ("sending", "ok", "CHECK", "unknown")      # ledger states that say a batch went out


def later(stamp, seconds):
    """A Salesforce datetime `seconds` after `stamp`, in the fake's format."""
    when = datetime.datetime.fromisoformat(stamp[:19]) + datetime.timedelta(seconds=seconds)
    return when.strftime("%Y-%m-%dT%H:%M:%S.000+0000")


class MergeHarness(Harness):
    def setUp(self):
        super().setUp()
        self.fresh()

    def fresh(self):
        """A fake org of three clubs and an empty back-fill folder."""
        self.org = FakeOrg([account(PARTNER, "Example Partner", PARTNER_RECORD_TYPE, None)]
                           + [account(acc_id, name) for acc_id, name in CLUBS.items()])
        for name in os.listdir(self.dir):
            os.remove(self.path(name))

    def batch(self, club, date, names, module=MODULE, week=3, year=1, creator="Jotform", **extra):
        """One batch through the fake's processor (history, not something the tool sent)."""
        body = {"Account_Name__c": CLUBS[club], "Attendance_Date__c": date, "Module__c": module, "Module_Week__c": week,
                "Module_Year__c": year, "Creator__c": creator, "enable_fuzzy_matching__c": False,
                "Contact_IDs__c": names if isinstance(names, str) else ", ".join(names), **extra}
        self.org.insert("Attendance_Batch__c", body)
        self.org.inserts.pop()
        return self.org.batches[-1]

    def live_correction(self, club, date, names, module=MODULE, week=3, year=1):
        """A mentor's batch the processor takes while the tool runs: straight into the fake, past any hook."""
        body = {"Account_Name__c": CLUBS[club], "Attendance_Date__c": date, "Module__c": module, "Module_Week__c": week,
                "Module_Year__c": year, "Creator__c": "Jotform", "enable_fuzzy_matching__c": False,
                "Contact_IDs__c": ", ".join(names)}
        type(self.org).insert(self.org, "Attendance_Batch__c", body)
        self.org.inserts.pop()
        return self.org.batches[-1]

    def history(self):
        """Salesforce before the back-fill: Sunrise 09-26 (F), the originals of K1 (A B C) and K2 (G H)."""
        h = {"F0": self.batch(SUNRISE, "2026-09-26", [F]),
             "O1": self.batch(SUNRISE, D1, [A, B, C]),
             "O2": self.batch(RIVER, D2, [G, H], module="Leadership", week=5, year=2)}
        for label, record in h.items():
            assert (record["Processing_Status__c"], record["Status_Message__c"]) == ("Success", "Processed successfully."), label
        return h

    @staticmethod
    def reports():
        return [row("101", date=D1, names=[A, B, D, E]),
                row("102", date=D1, names=[C, F], created=f"{D1} 11:00:00"),
                row("201", club="River Club", date=D2, names=[G, I], module="Leadership", week="5", year="2")]

    def planned(self, keys=(K1, K2), **kw):
        """history() + reports() + `merge` on `keys`, planned; the history's records."""
        h = self.history()
        self.write(self.reports(), decisions=[[k, MERGE] for k in keys], **kw)
        self.plan()
        return h

    def merge(self, *argv):
        return self.run_tool("merge", "--vpn-off", *argv)

    def apply(self, *argv):
        return self.run_tool("merge", "--apply", "--vpn-off", *argv)

    def hook(self, before=None, after=None):
        """Something that happens around each of the tool's next inserts."""
        real = self.org.insert

        def insert(sobject, body):
            if before:
                before()
            answer = real(sobject, body)
            if after:
                after()
            return answer
        self.org.insert = insert

    def mledger(self):
        path = self.path(MERGE_LEDGER)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))

    def mstates(self, key=None):
        return [r["status"] for r in self.mledger() if key is None or r["key"] == key]

    def rows_of(self, batch):
        return [r for r in self.org.rows if r["Attendance_Batch__c"] == batch["Id"]]

    def contact_ids(self, acc=None):
        return {cid for a, mine in self.org.contacts.items() if acc in (None, a) for cid, _ in mine.values()}

    def key_of(self, body):
        return {("Sunrise Club", D1): K1, ("River Club", D2): K2}[(body["Account_Name__c"], body["Attendance_Date__c"])]

    def folder_text(self):
        """Every file of the back-fill folder but the three that hold names by design (send's sent_names.json:
        a merge never writes it, MergeApply pins that)."""
        text = ""
        for name in sorted(os.listdir(self.dir)):
            if name not in ("resolved.json", "plan.json", "sent_names.json"):
                with open(self.path(name), encoding="utf-8", errors="replace") as fh:
                    text += fh.read()
        return text

    def assert_private(self, *texts):
        """Nothing printed and nothing written names a girl or quotes a status message."""
        text = "".join(t or "" for t in texts) + self.folder_text()
        for surname in SURNAMES:
            self.assertNotIn(surname.lower(), text.lower())
        self.assertNotIn(DUPLICATE[:20], text)
        self.assertNotIn("Processed successfully", text)
        self.assertNotIn("No participants submitted", text)
        for record in self.org.batches:      # 'merged into <id>', 18 or 15 characters
            self.assertNotIn(f"merged into {record['Id'][:15]}", text)

    def counts_in(self, line, *remove):
        """The whole numbers on a line once the ids, batch names, dates and `remove` are taken out."""
        for word in remove:
            line = line.replace(word, " ")
        line = re.sub(r"\d{4}-\d{2}-\d{2}T?[\d:Z]*|BATCH-\d+|\b[A-Za-z0-9]{18}\b|\b[A-Za-z0-9]{15}\b", " ", line)
        return {int(t) for t in re.findall(r"\b\d+\b", line)}

    def line_of(self, out, key, original):
        lines = [line for line in out.splitlines() if key in line and original["Id"] in line]
        self.assertEqual(len(lines), 1, f"{key}: one line with the key and the original's Id expected:\n{out}")
        return lines[0]

    def assert_listed(self, out, key, original, ticked, adds, new):
        acc, date = key.split("|")
        line = self.line_of(out, key, original)
        for piece in (original["Name"], CLUBS[acc], date):
            self.assertIn(piece, line)
        self.assertNotIn("skipped", line)
        self.assertTrue({ticked, adds, new} <= self.counts_in(line, CLUBS[acc]), (line, ticked, adds, new))

    def assert_skipped(self, out, key, reason):
        lines = [line for line in out.splitlines() if key in line]
        self.assertTrue(any(f"skipped, {reason}" in line for line in lines), (key, reason, out))


class MergePlan(MergeHarness, unittest.TestCase):
    def test_a_day_salesforce_has_is_planned_as_a_merge_on_ryan_s_word_and_send_never_sends_it(self):
        h = self.history()
        rows = self.reports() + [row("301", club="Pilot Club", date=D1, names=[J])]
        # without the clause, as before: K1 held for its count, K2 (as many ticks as rows) skipped, K3 queued
        self.write(rows)
        out, sessions, held = self.plan()
        self.assertEqual(([s["key"] for s in sessions], {x["key"]: x["reasons"] for x in held}),
                         ([K3], {K1: "salesforce_has_different_count"}))
        self.assertIn("skipped, already_in_salesforce: 1", out)
        # with it: two planned merges, outside the send queue, nothing held, nothing skipped for Salesforce's day
        self.write(rows, decisions=[[K1, MERGE], [K2, MERGE]])
        out, sessions, held = self.plan()
        self.assertEqual(([s["key"] for s in sessions], held), ([K3], []))
        self.assertNotIn("already_in_salesforce", out)
        self.assertNotIn("salesforce_has_different_count", out)
        merge_lines = [line for line in out.splitlines() if "merge" in line.lower() and "merge_without_original" not in line]
        self.assertTrue(any(2 in self.counts_in(line) for line in merge_lines), out)
        self.assert_private(out)
        # send neither lists nor sends a planned merge
        out, stop = self.run_tool("send")
        self.assertIsNone(stop, stop)
        self.assertIn("queue: 1 batches", out)
        for key in (K1, K2):
            self.assertNotIn(key, out)
        out, stop = self.send()
        self.assertIsNone(stop, stop)
        self.assertEqual([(b["Account_Name__c"], b["Attendance_Date__c"]) for b in self.org.inserts], [("Pilot Club", D1)])
        self.assertEqual((len(self.rows_of(h["O1"])), len(self.rows_of(h["O2"]))), (3, 2))
        # the merge dry run: one line per planned merge, a totals line, nothing sent or written
        out, stop = self.merge()
        self.assertIsNone(stop, stop)
        self.assert_listed(out, K1, h["O1"], *EXPECT[K1])
        self.assert_listed(out, K2, h["O2"], *EXPECT[K2])
        self.assertNotIn(K3, out)
        totals = [line for line in out.splitlines() if K1 not in line and K2 not in line]
        self.assertTrue(any({2, 4, 3} <= self.counts_in(line) for line in totals), out)    # 2 merges, 4 to add, 3 new
        self.assertIn("dry run: nothing was sent", out)
        self.assertEqual((len(self.org.inserts), self.org.updates), (1, []))
        self.assertFalse(os.path.exists(self.path(MERGE_LEDGER)))
        self.assert_private(out)

    def test_merge_without_an_original_with_rows_is_held_and_cannot_be_accepted(self):
        cases = {"2026-10-17": "nothing at all", "2026-10-24": "a Failed batch only",
                 "2026-10-31": "rows, but no Success batch", "2026-11-07": "a Success without rows (a typed aggregate)"}
        self.batch(SUNRISE, "2026-10-24", "")
        assert self.org.batches[-1]["Processing_Status__c"] == "Failed"
        gone = self.batch(SUNRISE, "2026-10-31", [A])
        self.org.batches.remove(gone)
        self.batch(SUNRISE, "2026-11-07", "", Girls_Present__c=10)
        assert self.org.batches[-1]["Processing_Status__c"] == "Success"
        rows = [row(str(n), date=day, names=[B, C]) for n, day in enumerate(cases, 1)]
        keys = {f"{SUNRISE}|{day}": why for day, why in cases.items()}
        self.write(rows, decisions=[[key, MERGE] for key in keys])
        out, sessions, held = self.plan()
        self.assertEqual(sessions, [])
        reasons = {x["key"]: x["reasons"].split("+") for x in held}
        for key, why in keys.items():
            with self.subTest(why):
                self.assertIn("merge_without_original", reasons.get(key, []), (why, reasons))
        out, stop = self.merge()
        self.assertIsNone(stop, stop)
        self.assertEqual(self.org.inserts, [])
        self.assert_private(out)
        self.write(rows, decisions=[[f"{SUNRISE}|2026-10-17", "merge; accept merge_without_original"]])
        self.assertIn("cannot be accepted", self.run_tool("plan")[1] or "")

    def test_the_decisions_file_reads_merge_strictly(self):
        self.history()
        rows = self.reports()

        def plan_with(decision):
            self.write(rows)
            with open(self.path("decisions.csv"), "w", encoding="utf-8") as fh:
                fh.write(f"key,decision\n{K1},{decision}\n")
            return self.run_tool("plan")
        for decision, message in (("merge now", "decisions.csv"), (f"merge {D1}", "decisions.csv"),
                                  ("skip; merge", "skip cannot be combined"), ("merge; skip", "skip cannot be combined")):
            with self.subTest(decision):
                stop = plan_with(decision)[1]
                self.assertIsNotNone(stop)
                self.assertNotEqual(stop, "2")
                self.assertIn(message, stop)
        stop = plan_with("maybe")[1]             # the refusal lists the clauses, merge among them
        self.assertIn("is not one of", stop or "")
        self.assertIn("merge", stop)
        for decision in ("merge", "merge; use 101", MERGE, "use 101+102; merge; accept club_has_earlier_contacts+similar_names"):
            with self.subTest(decision):
                out, stop = plan_with(decision)
                self.assertIsNone(stop, stop)
                self.assertIn("decisions: 1 read and applied", out)

    def test_a_merge_is_held_for_every_other_reason_a_session_is_and_released_as_one_is(self):
        many = [A, B] + [f"Girl{i:02d} Fennwhistle{i:02d}" for i in range(22)]
        cases = [   # name, the reports of Sunrise 10-03, the decision that holds, the reason, the one that releases,
                    # and what the merge then adds (names ticked, girls to add, new contacts)
            ("two reports with different weeks", [row("101", date=D1, names=[A, B, D, E]),
                                                  row("102", date=D1, week="4", names=[C, F], created=f"{D1} 11:00:00")],
             MERGE, "same_day_different_module", "merge; use 101; accept club_has_earlier_contacts", (4, 2, 2)),
            ("a name with a comma", [row("101", date=D1, names=[A, f"{make_fixture.LAST[3]}, {make_fixture.FIRST[3]}"])],
             MERGE, "bad_name", None, None),
            ("a report that ticks two rosters", [row("101", date=D1, names=[A, B, D, E]),
                                                 row("101", club="River Club", date=D1, names=[I])],
             MERGE, "several_rosters_ticked", "merge; accept club_has_earlier_contacts+several_rosters_ticked", (4, 2, 2)),
            ("no usable module", [row("101", date=D1, module=" ", names=[A, D])], MERGE, "module_not_usable", None, None),
            ("a club with contacts from before", self.reports()[:2], "merge", "club_has_earlier_contacts", MERGE, EXPECT[K1]),
            ("more new girls than proven", [row("101", date=D1, names=many)], MERGE, "more_new_girls_than_proven",
             "merge; accept club_has_earlier_contacts+more_new_girls_than_proven", (24, 22, 22)),
            ("two names the duplicate rule may take for one",
             [row("101", date=D1, names=[A, B, D, A.replace("Amara", "Amarra")])], MERGE, "similar_names",
             "merge; accept club_has_earlier_contacts+similar_names", (4, 2, 2)),
        ]
        assert A.startswith("Amara ")
        for name, rows, holding, reason, releasing, adds in cases:
            with self.subTest(name):
                self.fresh()
                h = self.history()
                self.write(rows, decisions=[[K1, holding]])
                out, sessions, held = self.plan()
                self.assertNotIn(K1, [s["key"] for s in sessions])
                self.assertIn(reason, {x["key"]: x["reasons"].split("+") for x in held}.get(K1, []), (name, held))
                self.assert_private(out)
                if releasing is None:
                    self.write(rows, decisions=[[K1, f"merge; accept {reason}"]])
                    self.assertIn("cannot be accepted", self.run_tool("plan")[1] or "")
                    continue
                self.write(rows, decisions=[[K1, releasing]])
                out, sessions, held = self.plan()
                self.assertNotIn(K1, [s["key"] for s in sessions] + [x["key"] for x in held])
                merge_lines = [line for line in out.splitlines() if "merge" in line.lower() and "merge_without" not in line]
                self.assertTrue(any(1 in self.counts_in(line) for line in merge_lines), out)     # one planned merge
                out, stop = self.merge()
                self.assertIsNone(stop, stop)
                self.assert_listed(out, K1, h["O1"], *adds)
                self.assert_private(out)


class MergeGuards(MergeHarness, unittest.TestCase):
    def test_merge_needs_the_vpn_word_in_both_modes_and_a_plan_of_its_inputs_but_not_a_fresh_fetch(self):
        self.planned()
        self.org.seen.clear()
        for argv in (("merge",), ("merge", "--apply")):
            with self.subTest(argv):
                self.assertIn(VPN, self.run_tool(*argv)[1] or "")
        self.assertEqual((self.org.seen, self.org.inserts), ([], []))
        self.assertEqual(self.run_tool("merge", "--apply", "--vpn-off", "--limit", "0")[1], "2")    # argparse
        # decisions.csv or resolved.json changed after the plan: both modes refuse
        with open(self.path("decisions.csv"), "a", encoding="utf-8") as fh:
            fh.write("\n")
        for run in (self.merge, self.apply):
            self.assertIn("plan again", run()[1] or "")
        self.write(self.reports(), decisions=[[K1, MERGE], [K2, MERGE]])
        self.plan()
        self.write(self.reports() + [row("301", club="Pilot Club", date=D1, names=[J])],
                   decisions=[[K1, MERGE], [K2, MERGE]])
        for run in (self.merge, self.apply):
            self.assertIn("plan again", run()[1] or "")
        self.assertEqual((self.org.inserts, self.mledger()), ([], []))
        # a fetch hours old is no obstacle: the prediction is read live from Salesforce
        self.write(self.reports(), decisions=[[K1, MERGE], [K2, MERGE]], fetched="2026-09-30T01:00:00Z")
        self.plan()
        out, stop = self.apply()
        self.assertIsNone(stop, stop)
        self.assertEqual((len(self.org.inserts), sorted(self.mstates())), (2, ["ok", "ok", "sending", "sending"]))
        self.assert_private(out)

    def test_only_and_limit_narrow_the_merges(self):
        h = self.planned()
        out, stop = self.merge("--only", K2)
        self.assertIsNone(stop, stop)
        self.assert_listed(out, K2, h["O2"], *EXPECT[K2])
        self.assertNotIn(K1, out)
        for only in (f"{SUNRISE}|2026-10-04", K3, "nonsense"):
            with self.subTest(only):
                self.assertIsNotNone(self.apply("--only", only)[1])
        self.assertEqual(self.org.inserts, [])
        self.assertIsNone(self.apply("--only", K2)[1])
        self.assertEqual([self.key_of(b) for b in self.org.inserts], [K2])
        self.assertIsNone(self.apply("--limit", "1")[1])
        self.assertEqual([self.key_of(b) for b in self.org.inserts], [K2, K1])
        self.assertIsNone(self.apply()[1])
        self.assertEqual(len(self.org.inserts), 2)
        self.assertEqual((self.mstates(K1), self.mstates(K2)), (["sending", "ok"], ["sending", "ok"]))

    def test_a_merge_the_day_would_not_take_is_skipped_sends_nothing_and_stays_planned(self):
        def elsewhere(h, to):
            for r in self.org.rows:
                if r["Attendance_Batch__c"] in (h["O1"]["Id"], "a1lELSEWHERE000001"):
                    r["Attendance_Batch__c"] = to
        cases = {   # reason: (make the cause, take it away again or None)
            "no_success_original": (lambda h: self.org.batches.remove(h["O1"]), lambda h: self.org.batches.append(h["O1"])),
            "original_not_mergeable": (lambda h: h["O1"].__setitem__("Creator__c", "Partner report"),
                                       lambda h: h["O1"].__setitem__("Creator__c", "Jotform")),
            "original_not_mergeable (no rows of its own)": (lambda h: elsewhere(h, "a1lELSEWHERE000001"),
                                                            lambda h: elsewhere(h, h["O1"]["Id"])),
            "module_differs": (lambda h: h["O1"].__setitem__("Module__c", "Leadership"),
                               lambda h: h["O1"].__setitem__("Module__c", MODULE.upper())),    # case ignored
            "adds_nobody": (lambda h: self.live_correction(SUNRISE, D1, [D, E, F]), None),
        }
        for label, (cause, cure) in cases.items():
            reason = label.split()[0]
            with self.subTest(label):
                self.fresh()
                h = self.planned(keys=(K1,))
                cause(h)
                out, stop = self.merge()
                self.assertIsNone(stop, stop)
                self.assert_skipped(out, K1, reason)
                out, stop = self.apply()
                self.assertIsNone(stop, stop)
                self.assertEqual(self.org.inserts, [])
                self.assertFalse(set(self.mstates(K1)) & set(WRITTEN), self.mstates(K1))
                self.assert_private(out)
                if cure is None:
                    continue
                cure(h)                      # the same plan, a later run: now it merges
                out, stop = self.apply()
                self.assertIsNone(stop, stop)
                self.assertEqual((len(self.org.inserts), self.mstates(K1)[-2:]), (1, ["sending", "ok"]))
                self.assertEqual((len(self.rows_of(h["O1"])), h["O1"]["Girls_Present__c"]), (6, 6))
                self.assert_private(out)

    def test_the_day_is_read_again_before_each_insert_and_a_changed_prediction_sends_nothing(self):
        cases = {   # what happens to the OTHER merge's day while the first one is sent
            "a live correction got there first": lambda h, key: self.live_correction(
                *((SUNRISE, D1, [D]) if key == K1 else (RIVER, D2, [I])),
                **({} if key == K1 else {"module": "Leadership", "week": 5, "year": 2})),
            "the original is now a Partner report": lambda h, key: h["O1" if key == K1 else "O2"].__setitem__(
                "Creator__c", "Partner report"),
            "the original is gone": lambda h, key: self.org.batches.remove(h["O1" if key == K1 else "O2"]),
        }
        for name, change in cases.items():
            with self.subTest(name):
                self.fresh()
                h = self.planned()
                once = []

                def after(change=change, once=once, h=h):
                    if not once:
                        once.append(self.key_of(self.org.inserts[0]))
                        change(h, K2 if once[0] == K1 else K1)
                self.hook(after=after)
                out, stop = self.apply()
                self.assertEqual(len(self.org.inserts), 1, name)
                first, other = once[0], (K2 if once[0] == K1 else K1)
                self.assertEqual(self.mstates(first), ["sending", "ok"])
                self.assertFalse(set(self.mstates(other)) & set(WRITTEN), self.mstates(other))
                self.assert_private(out, stop)


class MergeApply(MergeHarness, unittest.TestCase):
    def test_apply_sends_one_batch_per_merge_reads_it_back_records_it_and_never_sends_it_twice(self):
        h = self.planned()
        rows_before, contacts_before = {r["Id"] for r in self.org.rows}, self.contact_ids()
        participants = {acc: len(mine) for acc, mine in self.org.contacts.items()}
        batches_before = len(self.org.batches)
        out1, stop = self.apply("--limit", "1")
        self.assertIsNone(stop, stop)
        self.assertEqual(len(self.org.inserts), 1)
        out2, stop = self.apply()
        self.assertIsNone(stop, stop)
        self.assertEqual(len(self.org.inserts), 2)
        # what went out: one batch per merge, the session's names, its module, week and year, its own marker
        sent = {self.key_of(b): b for b in self.org.inserts}
        for key, (names, module, week, year) in {K1: ([A, B, D, E, C, F], MODULE, 3, 1),
                                                 K2: ([G, I], "Leadership", 5, 2)}.items():
            with self.subTest(key):
                body = sent[key]
                self.assertEqual(sorted(body["Contact_IDs__c"].split(", ")), sorted(names))
                self.assertEqual((body["Module__c"], body["Module_Week__c"], body["Module_Year__c"],
                                  body["enable_fuzzy_matching__c"]), (module, week, year, False))
                self.assertTrue(str(body["Creator__c"]).startswith(MARKER), body["Creator__c"])
        self.assertNotEqual(sent[K1]["Creator__c"], sent[K2]["Creator__c"])
        self.assertEqual(self.org.updates, [])
        # Salesforce afterwards: each original grew by its girls, each new batch merged with nothing of its own
        new = {b["Account__c"]: b for b in self.org.batches[batches_before:]}
        self.assertEqual(sorted(new), sorted([SUNRISE, RIVER]))
        for acc, original, rows_now in ((SUNRISE, h["O1"], 6), (RIVER, h["O2"], 3)):
            with self.subTest(acc):
                b = new[acc]
                self.assertEqual((b["Processing_Status__c"], b["Status_Message__c"], b["Girls_Present__c"], self.rows_of(b)),
                                 ("Success", f"merged into {original['Id']}", None, []))
                self.assertEqual((len(self.rows_of(original)), original["Girls_Present__c"]), (rows_now, rows_now))
        self.assertEqual({acc: len(mine) - participants[acc] for acc, mine in self.org.contacts.items()},
                         {PARTNER: 0, SUNRISE: 2, RIVER: 1, PILOT: 0})
        # the merge ledger: its own file, owner-only, sending then ok, the counts read back
        ledger = self.mledger()
        self.assertTrue(set(ledger[0]) >= MERGE_COLS, set(ledger[0]))
        self.assertEqual((self.mstates(K1), self.mstates(K2)), (["sending", "ok"], ["sending", "ok"]))
        ok = {r["key"]: r for r in ledger if r["status"] == "ok"}
        self.assertEqual({k: (r["original_id"], r["batch_id"], r["rows_added"], r["contacts_created"]) for k, r in ok.items()},
                         {K1: (h["O1"]["Id"], new[SUNRISE]["Id"], "3", "2"), K2: (h["O2"]["Id"], new[RIVER]["Id"], "1", "1")})
        self.assertEqual((self.mode(MERGE_LEDGER), self.mode(MERGE_ADDED)), (0o600, 0o600))
        self.assertFalse([r for r in self.ledger() if r["key"] in (K1, K2)])      # ledger.csv is send's alone
        self.assertFalse(os.path.exists(self.path("sent_names.json")))           # and so is its list of names
        # the rollback list: every row added and contact made, each on a line naming its merge; nothing from before
        lines = self.text_of(MERGE_ADDED).splitlines()
        added = [r for r in self.org.rows if r["Id"] not in rows_before]
        created = {acc: self.contact_ids(acc) - contacts_before for acc in (SUNRISE, RIVER)}
        self.assertEqual((len(added), len(created[SUNRISE]), len(created[RIVER])), (4, 2, 1))
        tie = {SUNRISE: (K1, new[SUNRISE]["Id"]), RIVER: (K2, new[RIVER]["Id"])}
        for record_id, acc in [(r["Id"], r["Account__c"]) for r in added] + [(c, a) for a in created for c in created[a]]:
            self.assertTrue(any(record_id in line and (tie[acc][0] in line or tie[acc][1] in line) for line in lines),
                            (record_id, lines))
        text = self.folder_text()
        for record_id in rows_before | contacts_before:
            self.assertNotIn(record_id, text)
        # never a second time: not on the next run, not after a new snapshot and plan
        out3, stop = self.apply()
        self.assertIsNone(stop, stop)
        self.write(self.reports(), decisions=[[K1, MERGE], [K2, MERGE]], read_at=bf.stamp())
        self.plan()
        out4, _ = self.apply()
        self.assertEqual(len(self.org.inserts), 2)
        # status: the merges verified, the rows they added, the girls they made, and what a rollback removes
        out5, stop = self.run_tool("status")
        self.assertIsNone(stop, stop)
        merge_lines = [line for line in out5.splitlines() if "merge" in line.lower()]
        self.assertTrue(any({2, 4, 3} <= self.counts_in(line) for line in merge_lines), out5)
        self.assertTrue(any("rollback" in line.lower() for line in merge_lines), out5)
        self.assert_private(out1, out2, out3, out4, out5)

    def test_a_merge_that_is_not_as_predicted_is_check_and_stops_the_line(self):
        def stranger():
            self.org.contacts[SUNRISE]["somebody new"] = ("003STRANGER0000001", self.org.clock())

        def failed():
            self.org.merge_corrections = False

        def other_batch_inside_the_window():
            mine = self.org.batches[-1]
            self.org.batches.append({"Id": "a1lOTHER0000000001", "Name": "BATCH-OTHER", "Account__c": SUNRISE,
                                     "Account_Name__c": "Sunrise Club", "Attendance_Date__c": D1,
                                     "Processing_Status__c": "Failed", "Status_Message__c": DUPLICATE,
                                     "Creator__c": "Jotform", "CreatedById": ME, "Module__c": MODULE,
                                     "CreatedDate": later(mine["CreatedDate"], 1),
                                     "LastModifiedDate": later(mine["CreatedDate"], 1)})
        cases = {   # name: (when, change, processor lag, the verdict)
            "comes back Failed": ("before", failed, 0, "CHECK"),
            "merged into another batch": ("after", lambda: self.org.batches[-1].__setitem__(
                "Status_Message__c", f"merged into {self.h['F0']['Id']}"), 0, "CHECK"),
            "added fewer rows": ("after", lambda: self.org.rows.pop(), 0, "CHECK"),
            "added more rows": ("after", lambda: self.org.rows.append(dict(
                self.org.rows[-1], Id="a1mEXTRA0000000001", Contact__c="003STRANGER0000001")), 0, "CHECK"),
            "a row of its own": ("after", lambda: self.org.rows.append(dict(
                self.org.rows[-1], Id="a1mOWN000000000001", Attendance_Batch__c=self.org.batches[-1]["Id"])), 0, "CHECK"),
            "a count of its own": ("after", lambda: self.org.batches[-1].__setitem__("Girls_Present__c", 3.0), 0, "CHECK"),
            "the original's count is not its rows": ("after", lambda: self.h["O1"].__setitem__("Girls_Present__c", 3.0),
                                                     0, "CHECK"),
            "the club grew by more": ("after", stranger, 0, "CHECK"),
            "the club grew by fewer": ("after", lambda: self.org.contacts[SUNRISE].popitem(), 0, "CHECK"),
            "landed on another account": ("after", lambda: self.org.batches[-1].__setitem__("Account__c", RIVER), 0, "CHECK"),
            "another batch of the day inside its window": ("after", other_batch_inside_the_window, 2, "CHECK"),
            # right after all: the original's 15-character id, the count as a double, the processor's writes late
            "merged into the original's 15-character id": ("after", lambda: self.org.batches[-1].__setitem__(
                "Status_Message__c", f"merged into {self.h['O1']['Id'][:15]}"), 0, "ok"),
            "the original's count as a double": ("after", lambda: self.h["O1"].__setitem__("Girls_Present__c", 6.0), 0, "ok"),
            "the processor's rows land after the batch's CreatedDate": (None, None, 2, "ok"),
        }
        for name, (when, change, lag, verdict) in cases.items():
            with self.subTest(name):
                self.fresh()
                self.h = self.planned(keys=(K1,))
                rows_before, contacts_before = {r["Id"] for r in self.org.rows}, self.contact_ids()
                self.org.processor_lag = lag
                if when:
                    self.hook(**{when: change})
                out, stop = self.apply()
                self.assertEqual(len(self.org.inserts), 1)
                self.assertEqual(self.mstates(K1), ["sending", verdict])
                if verdict == "ok":
                    self.assertIsNone(stop, stop)
                    lines = self.text_of(MERGE_ADDED).splitlines()
                    mine = ({r["Id"] for r in self.org.rows} - rows_before) | (self.contact_ids() - contacts_before)
                    self.assertEqual(len(mine), 5)       # 3 rows on the original, 2 new contacts
                    for record_id in mine:
                        self.assertTrue(any(record_id in line for line in lines), (record_id, lines))
                    self.assertEqual(self.mledger()[-1]["rows_added"], "3")
                    self.assert_private(out)
                    continue
                self.assertIsNotNone(stop, name)
                again, refused = self.apply()       # nothing more until it is closed
                self.assertIsNotNone(refused, name)
                self.assertEqual(len(self.org.inserts), 1)
                status, _ = self.run_tool("status")
                self.assert_private(out, stop, again, refused, status)

    def test_a_check_is_closed_by_hand_and_then_the_other_merges_go_on(self):
        for how in ("--accepted", "--removed"):
            with self.subTest(how):
                self.fresh()
                h = self.planned()
                rows_before, contacts_before = {r["Id"] for r in self.org.rows}, self.contact_ids()
                once = []

                def after(once=once):
                    if not once:                 # the first merge gets a count of its own: CHECK
                        once.append(self.org.batches[-1])
                        self.org.batches[-1]["Girls_Present__c"] = 2.0
                self.hook(after=after)
                out, stop = self.apply()
                self.assertIsNotNone(stop)
                first = once[0]
                key, other = (K1, K2) if first["Account__c"] == SUNRISE else (K2, K1)
                self.assertEqual((len(self.org.inserts), self.mstates(key), self.mstates(other)), (1, ["sending", "CHECK"], []))
                self.assertIsNotNone(self.apply()[1])
                self.assertEqual(len(self.org.inserts), 1)
                if how == "--removed":           # by hand: the batch, the rows it added, the contacts it made
                    original = h["O1"] if key == K1 else h["O2"]
                    self.org.batches.remove(first)
                    self.org.rows = [r for r in self.org.rows if r["Id"] in rows_before]
                    for mine in self.org.contacts.values():
                        for name, (cid, _) in list(mine.items()):
                            if cid not in contacts_before:
                                del mine[name]
                    original["Girls_Present__c"] = len(self.rows_of(original))
                out, stop = self.run_tool("close", key, how)
                self.assertIsNone(stop, stop)
                self.assertEqual(self.mstates(key)[-1], how[2:])
                self.write(self.reports(), decisions=[[K1, MERGE], [K2, MERGE]], read_at=bf.stamp())
                self.plan()
                out2, stop = self.apply()
                self.assertIsNone(stop, stop)
                self.assertEqual(self.mstates(other), ["sending", "ok"])
                if how == "--accepted":          # an accepted merge is never sent again
                    self.assertEqual(len(self.org.inserts), 2)
                    self.assertEqual(self.mstates(key), ["sending", "CHECK", "accepted"])
                self.assert_private(out, out2)

    def test_a_lost_answer_is_settled_by_the_merge_s_own_marker(self):
        h = self.planned(keys=(K1,))
        self.org.lose_answer = True
        out, stop = self.apply()
        self.assertIsNone(stop, stop)
        self.assertEqual((len(self.org.inserts), self.mstates(K1)), (1, ["sending", "ok"]))
        self.assertEqual(self.mledger()[-1]["batch_id"], self.org.batches[-1]["Id"])
        self.assertEqual((len(self.rows_of(h["O1"])), h["O1"]["Girls_Present__c"]), (6, 6))
        self.assert_private(out)

    def test_a_read_back_that_fails_is_unknown_and_settled_before_the_next_run_sends(self):
        h = self.planned()
        real = self.org.insert

        def insert_then_die(sobject, body):
            answer = real(sobject, body)
            self.org.die_after_insert = 1    # the read-back gets no answer
            return answer
        self.org.insert = insert_then_die
        out, stop = self.apply()
        self.assertIsNotNone(stop)
        first = self.key_of(self.org.inserts[0])
        self.assertEqual((len(self.org.inserts), self.mstates()), (1, ["sending", "unknown"]))
        self.org.insert = real
        out2, stop = self.apply()            # settled by its marker first, then the other
        self.assertIsNone(stop, stop)
        self.assertEqual(self.mstates(), ["sending", "unknown", "ok", "sending", "ok"])
        settled = self.mledger()[2]
        self.assertEqual((settled["key"], settled["rows_added"], settled["contacts_created"]),
                         (first, str(EXPECT[first][1]), str(EXPECT[first][2])))
        self.assertEqual(len(self.org.inserts), 2)
        self.assertEqual([(len(self.rows_of(h[o])), h[o]["Girls_Present__c"]) for o in ("O1", "O2")], [(6, 6), (3, 3)])
        self.assert_private(out, stop, out2)

    def test_a_lost_answer_with_nothing_saved_is_not_taken_for_another_batch_of_the_day(self):
        self.planned(keys=(K1,))
        real, live = self.org.insert, []

        def nothing_saved(sobject, body):
            self.org.inserts.append(body)    # ours is lost; a mentor's correction of the day lands instead
            live.append(self.live_correction(SUNRISE, D1, [D]))
            return 0, None
        self.org.insert = nothing_saved
        out, stop = self.apply()
        self.assertIsNotNone(stop)
        self.assertEqual(self.mstates(K1), ["sending", "unknown"])
        self.org.insert = real
        out2, stop2 = self.apply()
        self.assertNotIn(live[0]["Id"], [r["batch_id"] for r in self.mledger()])
        self.assertNotIn(live[0]["Id"], self.text_of(MERGE_ADDED))
        self.assert_private(out, stop, out2, stop2)

    def test_a_merge_salesforce_refuses_saves_nothing_and_nothing_more_is_sent(self):
        h = self.planned()
        self.org.refuse = True               # HTTP 400; the fake's message quotes a girl's name
        out, stop = self.apply()
        self.assertIsNotNone(stop)
        self.assertEqual((len(self.org.inserts), self.mstates()), (1, ["sending", "not_saved"]))
        self.assertEqual(self.mledger()[-1]["batch_id"], "")
        self.assertEqual((len(self.rows_of(h["O1"])), len(self.rows_of(h["O2"]))), (3, 2))
        self.assert_private(out, stop)


if __name__ == "__main__":
    unittest.main(verbosity=1)
