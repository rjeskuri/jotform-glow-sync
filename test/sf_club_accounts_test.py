#!/usr/bin/env python3
"""
Offline tests for tools/sf_club_accounts.py (imported by test/python_test.py, so `make py`
runs them). Everything here is fictional: clubs, partners and Salesforce ids are invented,
and the tool is pointed at a temporary folder with --dir semantics (Paths).
"""
import argparse
import contextlib
import csv
import io
import json
import os
import sys
import tempfile
import time
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import sf_club_accounts as sfc        # noqa: E402

P1, P2 = "001000000000000PAA", "001000000000000PBB"
PILOT = "001000000000000LAA"
OWNER = "005000000000000OAA"
COLS = ["region", "club_name", "partner_name", "sf_partner_account_id", "sf_partner_account_name",
        "match", "already_in_sf", "notes", "club_code", "active_girls", "sf_account_name", "action"]


def club(code, name, region="U.S", partner=("Example Partner", P1, "exact"), action="create",
         already="", account_name=None):
    return {"region": region, "club_name": name, "partner_name": partner[0],
            "sf_partner_account_id": partner[1], "sf_partner_account_name": partner[0],
            "match": partner[2], "already_in_sf": already, "notes": "", "club_code": code,
            "active_girls": "12", "sf_account_name": account_name or name, "action": action}


ALIAS = ("Second Partner", P2, "normalised")
HELD = "create (name incl. partner: same-name club)"
CLUBS = [
    club("DAWNSCLU", "Dawn's Club"),
    club("NINASCLU", "Niñas Club", region="Latin America"),
    club("SUNRISEC", "Sunrise Club", region="Asia"),
    club("ALIASCLU", "Alias Club", partner=ALIAS),
    club("PILOTCLU", "Pilot Club", action="link existing (set Parent Account)", already=PILOT),
    club("TWINCLU1", "Twin Club", region="Africa", action=HELD, account_name="Twin Club - Example Partner"),
    club("TWINCLU2", "Twin Club", region="Africa", partner=ALIAS, action=HELD,
         account_name="Twin Club - Second Partner"),
]


def parent(pid, name):
    return {"Id": pid, "Name": name, "RecordTypeId": sfc.PARTNER_RECORD_TYPE, "ParentId": None}


PARENTS = {P1: parent(P1, "Example Partner"), P2: parent(P2, "Second Partner")}


class SalesforceClubAccounts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paths = sfc.Paths(self.tmp.name)
        self.saved = 0
        self.write_csv(CLUBS)

    def write_csv(self, clubs):
        with open(self.paths.csv, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLS)
            w.writeheader()
            w.writerows(clubs)

    def run_tool(self, fn, **kw):
        """(printed text, exit message or None) of one command."""
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                fn(argparse.Namespace(**kw), self.paths)
        except SystemExit as stop:
            return out.getvalue(), str(stop.code)
        return out.getvalue(), None

    def build(self, **kw):
        args = {"created_on": "2026-09-30", "first_create": "DAWNSCLU", "first_link": "PILOTCLU",
                "first_accent": "NINASCLU"}
        args.update(kw)
        return self.run_tool(sfc.build, **args)

    def save(self, recs, **extra):
        """A saved connector answer, newer than anything the run has logged."""
        self.saved += 1
        path = os.path.join(self.tmp.name, f"read_{self.saved}.json")
        answer = {"totalSize": len(recs), "done": True, "records": recs}
        answer.update(extra)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(answer, fh)
        ahead = time.time() + 5 * self.saved
        os.utime(path, (ahead, ahead))
        return path

    def item(self, batch, n=0):
        with open(self.paths.write_set, encoding="utf-8") as fh:
            return json.load(fh)["batches"][batch][n]

    def made(self, batch, sf_id, n=0, **change):
        i = self.item(batch, n)
        rec = {"Id": sf_id, "Name": i["name"], "RecordTypeId": sfc.CLUB_RECORD_TYPE,
               "ParentId": i["parent_id"], "Description": i["body"].get("Description"), "OwnerId": OWNER}
        rec.update(change)
        return rec

    def pilot(self, **change):
        rec = {"Id": PILOT, "Name": "Pilot Club", "RecordTypeId": sfc.CLUB_RECORD_TYPE,
               "ParentId": None, "Description": None, "OwnerId": OWNER}
        rec.update(change)
        return rec

    def ids_file(self, *ids):
        path = os.path.join(self.tmp.name, "ids.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(ids) + "\n")
        return path

    def precheck(self, batch, recs):
        return self.run_tool(sfc.precheck, batch=batch, all=False, result=[self.save(recs)])

    def verify(self, batch, recs, ids=None, club_count=None, no_ids=False):
        return self.run_tool(sfc.verify, batch=batch, result=self.save(recs), ids=ids,
                             no_ids=no_ids, club_count=club_count)

    def created(self):
        with open(self.paths.created, encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))

    def close_batch_0(self):
        self.build()
        self.precheck(0, [PARENTS[P1]])
        return self.verify(0, [PARENTS[P1], self.made(0, "001000000000000CAA")],
                           ids=self.ids_file("001000000000000CAA"), club_count=sfc.BASELINE_CLUBS + 1)

    # ---- build
    def test_build_cuts_three_single_batches_then_the_rest_then_the_links(self):
        out, stop = self.build()
        self.assertIsNone(stop)
        self.assertIn("write set: 4 create + 1 link = 5 writes in 4 batches; 2 same-name rows held", out)
        self.assertEqual([self.item(b)["club_code"] for b in range(3)], ["DAWNSCLU", "PILOTCLU", "NINASCLU"])
        self.assertEqual(self.item(0)["body"], {
            "Name": "Dawn's Club", "RecordTypeId": sfc.CLUB_RECORD_TYPE, "ParentId": P1,
            "Description": "GLOW club code DAWNSCLU; created from the club registry 2026-09-30"})
        self.assertEqual(self.item(1)["body"], {"ParentId": P1})

    def test_build_refuses_a_first_record_under_an_alias_partner_or_without_an_accent(self):
        self.assertIn("matched by alias", self.build(first_create="ALIASCLU")[1])
        self.assertIn("no accented letter", self.build(first_accent="SUNRISEC")[1])

    def test_build_refuses_names_that_could_not_be_told_apart(self):
        cases = {
            "shared with another row": club("SUNRISE2", "SUNRISE CLUB"),
            # the plain name a held same-name club sends today
            "shared with another row (": club("TWINCLU3", "twin club"),
            "edge/double/invisible": club("SPACECLU", "Space  Club"),
            "sf_account_name differs": club("OTHERCLU", "Other Club", account_name="Other Club!"),
            "not a form region": club("MOONCLUB", "Moon Club", region="Moon"),
            "on-hold pilot account": club("HOLDCLUB", "Hold Club",
                                          partner=("Example Partner", sorted(sfc.ON_HOLD_ACCOUNTS)[0], "exact")),
        }
        for message, extra in cases.items():
            with self.subTest(message):
                self.write_csv(CLUBS + [extra])
                self.assertIn(message, self.build()[1])

    def test_invisible_characters_are_refused(self):
        for point in (0x00A0, 0x00AD, 0x200B, 0x2060, 0xFEFF):
            with self.subTest(hex(point)):
                self.write_csv(CLUBS + [club("ODDCLUB1", "Odd" + chr(point) + "Club")])
                self.assertIn("edge/double/invisible", self.build()[1])

    def test_the_csv_may_not_change_after_build_and_the_batches_not_after_the_run_started(self):
        self.close_batch_0()
        self.assertIn("would change the batches", self.build(first_create="SUNRISEC")[1])
        self.write_csv(CLUBS + [club("LATECLUB", "Late Club")])
        self.assertIn("changed after `build`", self.run_tool(sfc.bodies, batch=0)[1])

    # ---- queries
    def test_soql_escapes_the_apostrophe_and_always_asks_for_the_parents(self):
        self.build()
        out, _ = self.run_tool(sfc.soql, batch=0, all=False, parents=False, totals=False, count=False, chunk=50)
        self.assertIn("WHERE Name IN ('Dawn\\'s Club') OR Id IN ('" + P1 + "') LIMIT 200", out)

    # ---- precheck
    def test_precheck_refuses_an_empty_a_foreign_and_a_cut_read(self):
        self.build()
        self.assertIn("0 records in the read (want 1)", self.precheck(0, [])[1])
        stranger = {"Id": "001000000000000XAA", "Name": "Somebody Else", "RecordTypeId": sfc.CLUB_RECORD_TYPE}
        self.assertIn("did not ask for", self.precheck(0, [PARENTS[P1], stranger])[1])
        cut = self.save([PARENTS[P1]], totalSize=40)
        self.assertIn("cut, incomplete", self.run_tool(sfc.precheck, batch=0, all=False, result=[cut])[1])
        self.assertFalse(os.path.exists(self.paths.log))

    def test_precheck_refuses_an_existing_name_and_a_changed_parent(self):
        self.build()
        twin = self.made(0, "001000000000000XAA", Name="DAWN'S CLUB")
        self.assertIn("already exists (001000000000000XAA)", self.precheck(0, [PARENTS[P1], twin])[1])
        renamed = dict(PARENTS[P1], Name="Example Partner Ltd")
        self.assertIn("not the CSV's sf_partner_account_name", self.precheck(0, [renamed])[1])
        a_club = dict(PARENTS[P1], RecordTypeId=sfc.CLUB_RECORD_TYPE)
        self.assertIn("not a partner account", self.precheck(0, [a_club])[1])

    def test_batches_go_in_order_and_are_never_written_twice(self):
        self.build()
        self.assertIn("batch 0 is not verified yet", self.precheck(1, [PARENTS[P1], self.pilot()])[1])
        out, stop = self.precheck(0, [PARENTS[P1]])
        self.assertIsNone(stop)
        self.assertIn("the batch is open", out)
        out, stop = self.verify(0, [PARENTS[P1], self.made(0, "001000000000000CAA")],
                                ids=self.ids_file("001000000000000CAA"), club_count=sfc.BASELINE_CLUBS + 1)
        self.assertIsNone(stop)
        self.assertIn("batch 0 verify ok; the batch is closed", out)
        self.assertIn("written and verified already", self.precheck(0, [PARENTS[P1]])[1])

    def test_a_read_older_than_the_last_step_is_refused(self):
        self.close_batch_0()
        old = self.save([PARENTS[P1], self.pilot()])
        os.utime(old, (time.time() - 3600, time.time() - 3600))
        self.assertIn("older than the last step", self.run_tool(sfc.precheck, batch=1, all=False, result=[old])[1])

    # ---- verify
    def test_verify_needs_the_precheck_the_ids_and_the_club_count(self):
        self.build()
        good = [PARENTS[P1], self.made(0, "001000000000000CAA")]
        self.assertIn("not prechecked", self.verify(0, good)[1])
        self.precheck(0, [PARENTS[P1]])
        self.assertIn("needs --club-count", self.verify(0, good)[1])
        self.assertIn("needs --ids", self.verify(0, good, club_count=11)[1])

    def test_verify_records_the_account_and_fails_on_any_difference(self):
        cases = {
            "stored Name differs": ({"Name": "Dawn's club"}, 11, "001000000000000CAA"),
            "RecordType is not Club": ({"RecordTypeId": sfc.PARTNER_RECORD_TYPE}, 11, "001000000000000CAA"),
            "ParentId is None": ({"ParentId": None}, 11, "001000000000000CAA"),
            "Description differs": ({"Description": None}, 11, "001000000000000CAA"),
            "an account exists that this run does not know": ({}, 12, "001000000000000CAA"),
            "not found by name ['001000000000000ZAA']": ({}, 11, "001000000000000ZAA"),
        }
        for message, (change, count, returned) in cases.items():
            with self.subTest(message):
                for leftover in (self.paths.log, self.paths.created):
                    if os.path.exists(leftover):
                        os.remove(leftover)
                self.build()
                self.precheck(0, [PARENTS[P1]])
                out, stop = self.verify(0, [PARENTS[P1], self.made(0, "001000000000000CAA", **change)],
                                        ids=self.ids_file(returned), club_count=count)
                self.assertIn(message, stop)
                rows = self.created()              # it exists, so the rollback file knows it
                self.assertEqual([r["sf_account_id"] for r in rows], ["001000000000000CAA"])
                self.assertEqual(rows[0]["action"],
                                 "found-unconfirmed" if "Description" in change else "create")
                self.assertEqual(sfc.batch_state(sfc.read_log(self.paths), 0)[0], "open")

    def test_a_double_write_is_recorded_twice_and_fails(self):
        self.build()
        self.precheck(0, [PARENTS[P1]])
        two = [self.made(0, "001000000000000CAA"), self.made(0, "001000000000000CBB")]
        out, stop = self.verify(0, [PARENTS[P1]] + two, no_ids=True, club_count=12)
        self.assertIn("2 Accounts carry the name", stop)
        self.assertEqual([(r["sf_account_id"], r["note"]) for r in self.created()],
                         [("001000000000000CAA", "duplicate"), ("001000000000000CBB", "duplicate")])

    def test_a_link_keeps_its_before_image_and_stops_on_a_changed_owner(self):
        self.close_batch_0()
        self.assertIn("has a parent already", self.precheck(1, [PARENTS[P1], self.pilot(ParentId=P2)])[1])
        self.assertIsNone(self.precheck(1, [PARENTS[P1], self.pilot()])[1])
        not_yet = self.verify(1, [PARENTS[P1], self.pilot()])
        self.assertIn("ParentId is None", not_yet[1])
        self.assertEqual(len(self.created()), 1)           # a link is recorded only once it is set
        moved = self.verify(1, [PARENTS[P1], self.pilot(ParentId=P1, OwnerId="005000000000000ZAA")])
        self.assertIn("Name, owner or record type changed", moved[1])
        out, stop = self.verify(1, [PARENTS[P1], self.pilot(ParentId=P1)])
        self.assertIsNone(stop)
        row = self.created()[1]
        self.assertEqual((row["action"], row["parent_id"], row["previous_parent_id"]), ("link", P1, ""))

    # ---- all names, parents, totals
    def test_precheck_of_all_names_wants_exactly_the_link_targets(self):
        self.build()
        self.assertIsNone(self.run_tool(sfc.precheck, batch=None, all=True, result=[self.save([self.pilot()])])[1])
        self.assertIn("expected exactly the pilot account",
                      self.run_tool(sfc.precheck, batch=None, all=True, result=[self.save([])])[1])

    def test_parents_wants_every_partner_account_and_nothing_else(self):
        self.build()
        both = [PARENTS[P1], PARENTS[P2]]
        self.assertIn("parents ok: 2 partner accounts", self.run_tool(sfc.parents, result=[self.save(both)])[0])
        self.assertIn("0 records in the read", self.run_tool(sfc.parents, result=[self.save(both[:1])])[1])

    def test_totals_counts_every_club_account(self):
        self.close_batch_0()
        self.precheck(1, [PARENTS[P1], self.pilot()])
        self.verify(1, [PARENTS[P1], self.pilot(ParentId=P1)])
        self.precheck(2, [PARENTS[P1]])
        self.verify(2, [PARENTS[P1], self.made(2, "001000000000000CCC")],
                    ids=self.ids_file("001000000000000CCC"), club_count=12)
        self.precheck(3, [PARENTS[P1], PARENTS[P2]])
        rest = [self.made(3, "001000000000000CDD", 0), self.made(3, "001000000000000CEE", 1)]
        self.verify(3, [PARENTS[P1], PARENTS[P2]] + rest,
                    ids=self.ids_file("001000000000000CDD", "001000000000000CEE"), club_count=14)
        on_hold = [{"Id": i, "Name": f"On hold {n}", "RecordTypeId": sfc.CLUB_RECORD_TYPE, "ParentId": None}
                   for n, i in enumerate(sorted(sfc.ON_HOLD_ACCOUNTS))]
        clubs = [self.made(0, "001000000000000CAA"), self.pilot(ParentId=P1),
                 self.made(2, "001000000000000CCC")] + rest + on_hold
        out, stop = self.run_tool(sfc.totals, result=self.save(clubs))
        self.assertIsNone(stop)
        self.assertIn("totals ok", out)
        self.assertIn("Example Partner: 4/4", out)
        stray = {"Id": "001000000000000XAA", "Name": "Typed By Hand", "RecordTypeId": sfc.CLUB_RECORD_TYPE}
        self.assertIn("is not in the write set", self.run_tool(sfc.totals, result=self.save(clubs + [stray]))[1])
        self.assertIn("is not among the Club accounts", self.run_tool(sfc.totals, result=self.save(clubs[:-1]))[1])


if __name__ == "__main__":
    unittest.main(verbosity=1)
