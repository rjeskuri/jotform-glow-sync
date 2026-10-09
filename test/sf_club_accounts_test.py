#!/usr/bin/env python3
"""
Offline tests for tools/sf_club_accounts.py (found by `make py`'s unittest discovery).
Everything here is fictional: clubs, partners and Salesforce ids are invented,
and the tool is pointed at a temporary folder (its --dir).
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
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import sf_club_accounts as sfc        # noqa: E402
from glow import forms as glow_forms  # noqa: E402
from glow.sync import PICKER_NAME, picker_calc_values  # noqa: E402

P1, P2 = "001000000000000PAA", "001000000000000PBB"
PILOT = "001000000000000LAA"
OWNER, ME = "005000000000000OAA", "005000000000000MEE"
A, B, C, D, E, Z = ("001000000000000CAA", "001000000000000CBB", "001000000000000CCC",
                    "001000000000000CDD", "001000000000000CEE", "001000000000000ZAA")
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


class FakeForms:
    """A Jotform client that answers GET /form/<id>/questions with one Club picker per region."""
    def __init__(self, options, calc=None):
        self.options, self.calc = options, calc or {}

    def get(self, path):
        region = {fid: r for r, fid in glow_forms.REGIONALS.items()}[path.split("/")[2]]
        options = self.options.get(region, [])
        return {"5": {"type": "control_dropdown", "name": PICKER_NAME, "options": "|".join(options),
                      "calcValues": self.calc.get(region, picker_calc_values(options))}}


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
               "ParentId": i["parent_id"], "Description": i["body"].get("Description"),
               "OwnerId": ME, "CreatedById": ME}
        rec.update(change)
        return rec

    def pilot(self, **change):
        rec = {"Id": PILOT, "Name": "Pilot Club", "RecordTypeId": sfc.CLUB_RECORD_TYPE,
               "ParentId": None, "Description": None, "OwnerId": OWNER, "CreatedById": OWNER}
        rec.update(change)
        return rec

    def ids_file(self, *ids):
        path = os.path.join(self.tmp.name, "ids.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(ids) + "\n")
        return path

    def count(self):
        return sfc.BASELINE_CLUBS + sfc.made_count(sfc.read_created(self.paths))

    def precheck(self, batch, recs, club_count="as recorded", path=None):
        if club_count == "as recorded":
            club_count = self.count()
        return self.run_tool(sfc.precheck, batch=batch, all=False, result=[path or self.save(recs)],
                             chunk=50, after=False, club_count=club_count)

    def precheck_all(self, *answers, chunk=50, after=False):
        return self.run_tool(sfc.precheck, batch=None, all=True, result=[self.save(a) for a in answers],
                             chunk=chunk, after=after, club_count=None)

    def verify(self, batch, recs, ids=None, club_count=None, no_ids=False):
        return self.run_tool(sfc.verify, batch=batch, result=self.save(recs), ids=ids,
                             no_ids=no_ids, club_count=club_count)

    def bodies(self, batch, preview=False):
        return self.run_tool(sfc.bodies, batch=batch, preview=preview)

    def created(self):
        with open(self.paths.created, encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))

    def state(self, batch):
        return sfc.batch_state(sfc.read_log(self.paths), batch)[0]

    def close_batch_0(self):
        self.build()
        self.precheck(0, [PARENTS[P1]])
        return self.verify(0, [PARENTS[P1], self.made(0, A)], ids=self.ids_file(A), club_count=11)

    def close_all(self):
        self.close_batch_0()
        self.precheck(1, [PARENTS[P1], self.pilot()])
        self.verify(1, [PARENTS[P1], self.pilot(ParentId=P1)])
        self.precheck(2, [PARENTS[P1]])
        self.verify(2, [PARENTS[P1], self.made(2, C)], ids=self.ids_file(C), club_count=12)
        self.precheck(3, [PARENTS[P1], PARENTS[P2]])
        rest = [self.made(3, D, 0), self.made(3, E, 1)]
        self.verify(3, [PARENTS[P1], PARENTS[P2]] + rest, ids=self.ids_file(D, E), club_count=14)
        on_hold = [{"Id": i, "Name": f"On hold {n}", "RecordTypeId": sfc.CLUB_RECORD_TYPE, "ParentId": None}
                   for n, i in enumerate(sorted(sfc.ON_HOLD_ACCOUNTS))]
        return [self.made(0, A), self.pilot(ParentId=P1), self.made(2, C)] + rest + on_hold

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

    def test_build_chooses_the_first_records_with_care(self):
        self.assertIn("matched by alias", self.build(first_create="ALIASCLU")[1])
        self.assertIn("no apostrophe", self.build(first_create="SUNRISEC")[1])
        self.assertIn("no accented letter", self.build(first_accent="SUNRISEC")[1])
        self.assertIn("is not in the write set", self.build(first_link="TWINCLU1")[1])

    def test_build_refuses_names_that_could_not_be_told_apart(self):
        cases = {
            "shared with another row": club("SUNRISE2", "SUNRISE CLUB"),
            # the plain name a held same-name club sends today
            "shared with another row (": club("TWINCLU3", "twin club"),
            "named like a partner account": club("PARTNERC", "example partner"),
            "edge/double/invisible": club("SPACECLU", "Space  Club"),
            "sf_account_name differs": club("OTHERCLU", "Other Club", account_name="Other Club!"),
            "not a form region": club("MOONCLUB", "Moon Club", region="Moon"),
            "not capitals and digits": club("moon club", "Moon Club"),
            "active_girls is not a whole number": dict(club("MOONCLUB", "Moon Club"), active_girls="n/a"),
            "on-hold pilot account": club("HOLDCLUB", "Hold Club",
                                          partner=("Example Partner", sorted(sfc.ON_HOLD_ACCOUNTS)[0], "exact")),
            "maps to 2 Salesforce accounts": club("MOONCLUB", "Moon Club", partner=("Example Partner", P2, "exact")),
            "its link target is on two rows": club("PILOT2CL", "Pilot Two", already=PILOT,
                                                   action="link existing (set Parent Account)"),
            "its parent is a link target": club("MOONCLUB", "Moon Club", partner=("Pilot Partner", PILOT, "exact")),
        }
        for message, extra in cases.items():
            with self.subTest(message):
                self.write_csv(CLUBS + [extra])
                self.assertIn(message, self.build()[1])

    def test_invisible_characters_are_refused(self):
        for point in (0x00A0, 0x00AD, 0x200B, 0x2060, 0xFEFF, 0x034F, 0x3164, 0xE0020, 0x0009):
            with self.subTest(hex(point)):
                self.write_csv(CLUBS + [club("ODDCLUB1", "Odd" + chr(point) + "Club")])
                self.assertIn("edge/double/invisible", self.build()[1])

    def test_the_list_is_sealed_by_build_and_the_batches_by_the_first_step(self):
        self.build()
        with open(self.paths.write_set, encoding="utf-8") as fh:
            first = fh.read()
        self.assertIsNone(self.build()[1])                 # an unchanged rebuild is fine
        with open(self.paths.write_set, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), first)
        self.close_batch_0()
        self.assertIn("would change the batches", self.build(created_on="2026-10-01")[1])
        os.rename(self.paths.write_set, self.paths.write_set + ".lost")
        self.assertIn("write_set.json is gone", self.build(created_on="2026-10-01")[1])
        os.rename(self.paths.write_set + ".lost", self.paths.write_set)
        self.write_csv(CLUBS + [club("LATECLUB", "Late Club")])
        self.assertIn("changed after `build`", self.bodies(0, preview=True)[1])

    def test_a_hold_is_sealed_too(self):
        self.build()
        with open(self.paths.hold, "w", encoding="utf-8") as fh:
            fh.write("SUNRISEC  # waiting for an answer\n")
        self.assertIn("hold_codes.txt changed after `build`", self.bodies(3, preview=True)[1])
        self.assertIn("hold_codes.txt changed after `build`", self.precheck(0, [PARENTS[P1]])[1])
        self.assertEqual(sfc.read_log(self.paths), [])
        out, stop = self.build()
        self.assertIn("1 more held by hold_codes.txt", out)
        self.assertNotIn("SUNRISEC", self.bodies(3, preview=True)[0])
        os.remove(self.paths.hold)
        self.assertIn("hold_codes.txt changed after `build`", self.bodies(3, preview=True)[1])

    # ---- queries and bodies
    def test_soql_escapes_the_apostrophe_and_always_asks_for_the_parents(self):
        self.build()
        ask = dict(all=False, parents=False, totals=False, count=False, chunk=50)
        out, _ = self.run_tool(sfc.soql, batch=0, ids=None, **ask)
        self.assertIn("WHERE Name IN ('Dawn\\'s Club') OR Id IN ('" + P1 + "') LIMIT 200", out)
        out, _ = self.run_tool(sfc.soql, batch=0, ids=self.ids_file(A), **ask)     # after the writes
        self.assertIn("OR Id IN ('" + A + "', '" + P1 + "') LIMIT 200", out)
        self.assertIn("not 18-character Account ids",
                      self.run_tool(sfc.soql, batch=0, ids=self.ids_file("oops"), **ask)[1])

    def test_bodies_are_printed_for_the_open_batch_only(self):
        self.build()
        self.assertIn("not prechecked", self.bodies(0)[1])
        self.assertIn("PREVIEW of batch 0", self.bodies(0, preview=True)[0])
        self.precheck(0, [PARENTS[P1]])
        self.assertIn('"Name": "Dawn\'s Club"', self.bodies(0)[0])
        self.verify(0, [PARENTS[P1], self.made(0, A)], ids=self.ids_file(A), club_count=11)
        self.assertIn("batch 0 is closed", self.bodies(0)[1])

    # ---- precheck
    def test_precheck_refuses_an_empty_a_foreign_and_a_cut_read(self):
        self.build()
        self.assertIn("0 records in the read (want 1)", self.precheck(0, [])[1])
        stranger = {"Id": Z, "Name": "Somebody Else", "RecordTypeId": sfc.CLUB_RECORD_TYPE}
        self.assertIn("did not ask for", self.precheck(0, [PARENTS[P1], stranger])[1])
        cut = self.save([PARENTS[P1]], totalSize=40)
        self.assertIn("cut, incomplete", self.precheck(0, None, path=cut)[1])
        self.assertIn("needs --club-count", self.precheck(0, [PARENTS[P1]], club_count=None)[1])
        self.assertIn("an account exists that this run does not know",
                      self.precheck(0, [PARENTS[P1]], club_count=11)[1])
        self.assertFalse(os.path.exists(self.paths.log))

    def test_precheck_refuses_an_existing_name_and_a_changed_parent(self):
        self.build()
        twin = self.made(0, Z, Name="DAWN'S CLUB")
        self.assertIn(f"already exists ({Z})", self.precheck(0, [PARENTS[P1], twin])[1])
        renamed = dict(PARENTS[P1], Name="Example Partner Ltd")
        self.assertIn("not the CSV's sf_partner_account_name", self.precheck(0, [renamed])[1])
        a_club = dict(PARENTS[P1], RecordTypeId=sfc.CLUB_RECORD_TYPE)
        self.assertIn("not a partner account", self.precheck(0, [a_club])[1])

    def test_a_field_that_was_not_read_is_not_an_empty_field(self):
        self.close_batch_0()
        lean_parent = {"Id": P1, "Name": "Example Partner", "RecordTypeId": sfc.PARTNER_RECORD_TYPE}
        self.assertIn("the read has no ParentId", self.precheck(1, [lean_parent, self.pilot()])[1])
        lean_pilot = {"Id": PILOT, "Name": "Pilot Club", "RecordTypeId": sfc.CLUB_RECORD_TYPE}
        self.assertIn("the read has no ParentId, OwnerId", self.precheck(1, [PARENTS[P1], lean_pilot])[1])
        self.assertNotIn(PILOT, sfc.read_before(self.paths))
        self.precheck(1, [PARENTS[P1], self.pilot()])
        no_owner = {k: v for k, v in self.pilot(ParentId=P1).items() if k != "OwnerId"}
        self.assertIn("the read has no OwnerId", self.verify(1, [PARENTS[P1], no_owner])[1])
        self.assertIn("parents FAILED", self.run_tool(sfc.parents, result=[self.save([lean_parent, PARENTS[P2]])])[1])

    def test_batches_go_in_order_and_are_never_written_twice(self):
        self.build()
        self.assertIn("batch 0 is not verified yet", self.precheck(1, [PARENTS[P1], self.pilot()])[1])
        out, stop = self.precheck(0, [PARENTS[P1]])
        self.assertIsNone(stop)
        self.assertIn("the batch is open", out)
        self.assertIn("batch 0 is not verified yet", self.precheck(1, [PARENTS[P1], self.pilot()])[1])
        out, stop = self.verify(0, [PARENTS[P1], self.made(0, A)], ids=self.ids_file(A), club_count=11)
        self.assertIsNone(stop)
        self.assertIn("batch 0 verify ok; the batch is closed", out)
        self.assertIn("written and verified already", self.precheck(0, [PARENTS[P1]])[1])

    def test_a_read_is_fresh_only_when_saved_in_a_later_second_than_the_last_step(self):
        self.build()
        read = self.save([PARENTS[P1]])
        self.assertIsNone(self.precheck(0, None, path=read)[1])
        opened = sfc.stamp_seconds(sfc.read_log(self.paths)[-1]["when_utc"])
        os.utime(read, (opened + 0.9, opened + 0.9))       # saved in the second the batch was opened
        self.assertIn("this read is not newer", self.precheck(0, None, path=read)[1])
        after = self.save([PARENTS[P1], self.made(0, A)])
        os.utime(after, (opened + 0.9, opened + 0.9))
        self.assertIn("not newer than the precheck",
                      self.run_tool(sfc.verify, batch=0, result=after, ids=None, no_ids=True, club_count=11)[1])
        self.verify(0, [PARENTS[P1], self.made(0, A)], ids=self.ids_file(A), club_count=11)
        old = self.save([PARENTS[P1], self.pilot()])
        os.utime(old, (time.time() - 3600, time.time() - 3600))
        self.assertIn("not newer than the last step", self.precheck(1, None, path=old)[1])
        self.assertIn("no such saved read", self.precheck(1, None, path=old + ".missing")[1])

    def test_a_precheck_may_be_repeated_but_not_after_the_writes(self):
        self.build()
        self.assertIsNone(self.precheck(0, [PARENTS[P1]])[1])
        self.assertIsNone(self.precheck(0, [PARENTS[P1]])[1])          # nothing written: a fresh read
        # the writes were made and the session died: the old answer, saved again, says "nothing exists"
        self.assertIn("an account exists that this run does not know",
                      self.precheck(0, [PARENTS[P1]], club_count=11)[1])

    # ---- verify
    def test_verify_needs_the_precheck_the_ids_and_the_club_count(self):
        self.build()
        good = [PARENTS[P1], self.made(0, A)]
        self.assertIn("not prechecked", self.verify(0, good)[1])
        self.precheck(0, [PARENTS[P1]])
        self.assertIn("needs --club-count", self.verify(0, good)[1])
        self.assertIn("needs --ids", self.verify(0, good, club_count=11)[1])

    def test_verify_records_the_account_and_fails_on_any_difference(self):
        cases = {
            "stored Name differs": ({"Name": "Dawn's club"}, 11, A),
            "RecordType is not Club": ({"RecordTypeId": sfc.PARTNER_RECORD_TYPE}, 11, A),
            "ParentId is None": ({"ParentId": None}, 11, A),
            "Description differs": ({"Description": None}, 11, A),
            "1 more - an account exists that this run does not know": ({}, 12, A),
            f"returned but not read ['{Z}']": ({}, 12, Z),
        }
        for message, (change, count, returned) in cases.items():
            with self.subTest(message):
                for leftover in (self.paths.log, self.paths.created):
                    if os.path.exists(leftover):
                        os.remove(leftover)
                self.build()
                self.precheck(0, [PARENTS[P1]])
                out, stop = self.verify(0, [PARENTS[P1], self.made(0, A, **change)],
                                        ids=self.ids_file(returned), club_count=count)
                self.assertIn(message, stop)
                rows = self.created()              # it exists, so the rollback file knows it
                self.assertEqual(rows[0]["sf_account_id"], A)
                self.assertEqual(rows[0]["action"], "found-unconfirmed" if "Description" in change else "create")
                self.assertEqual([(r["sf_account_id"], r["action"]) for r in rows[1:]],
                                 [(Z, "returned-unread")] if returned == Z else [])
                self.assertEqual(self.state(0), "open")

    def open_batch_2(self):
        self.close_batch_0()
        self.precheck(1, [PARENTS[P1], self.pilot()])
        self.verify(1, [PARENTS[P1], self.pilot(ParentId=P1)])
        self.precheck(2, [PARENTS[P1]])
        return self.made(2, C, Name="Ni?as Club")

    def test_an_account_stored_under_another_name_reaches_the_rollback_file(self):
        mangled = self.open_batch_2()
        # read by name only: nothing of that name, but the id the connector returned is kept
        out, stop = self.verify(2, [PARENTS[P1]], ids=self.ids_file(C), club_count=12)
        self.assertIn("0 Accounts carry the name", stop)
        self.assertEqual([(r["sf_account_id"], r["action"]) for r in self.created()[2:]], [(C, "returned-unread")])
        # read by name and by returned id (`soql --batch 2 --ids`): recorded as this run's, with its club
        out, stop = self.verify(2, [PARENTS[P1], mangled], ids=self.ids_file(C), club_count=12)
        self.assertIn("stored under another Name than the one sent", stop)
        row = self.created()[2]
        self.assertEqual((row["sf_account_id"], row["action"], row["club_code"], row["sf_account_name"]),
                         (C, "create", "NINASCLU", "Ni?as Club"))
        self.assertEqual(self.state(2), "open")

    def test_without_the_ids_the_description_still_says_whose_account_it_is(self):
        mangled = self.open_batch_2()
        lost = dict(PARENTS[P2], Id=Z, Name="Somebody Else")            # not this run's: only reported
        out, stop = self.verify(2, [PARENTS[P1], mangled, lost], no_ids=True, club_count=12)
        self.assertIn(f"{Z}: an account this batch did not ask for", stop)
        self.assertEqual([(r["sf_account_id"], r["action"], r["club_code"]) for r in self.created()[2:]],
                         [(C, "create", "NINASCLU")])

    def open_batch_3(self):
        self.open_batch_2()
        self.verify(2, [PARENTS[P1], self.made(2, C)], ids=self.ids_file(C), club_count=12)
        self.precheck(3, [PARENTS[P1], PARENTS[P2]])
        return [PARENTS[P1], PARENTS[P2]], self.made(3, D, 0), self.made(3, E, 1)

    def test_a_batch_never_closes_over_an_unresolved_row(self):
        parents, d, e = self.open_batch_3()
        out, stop = self.verify(3, parents + [dict(d, Name="Alias Clup"), e], ids=self.ids_file(D, E), club_count=14)
        self.assertIn("stored under another Name", stop)
        # the name is written again (a second account) and only the new id is handed over
        again = self.made(3, Z, 0)
        out, stop = self.verify(3, parents + [again, e], ids=self.ids_file(Z, E), club_count=15)
        self.assertIn(f"rows of this batch that are not confirmed ({D}) - STOP", stop)
        self.assertEqual(self.state(3), "open")
        self.assertIn("has rows that are not confirmed", self.bodies(3)[1])

    def test_the_ids_of_another_batch_never_damage_its_rows(self):
        parents, d, e = self.open_batch_3()
        before = self.created()
        out, stop = self.verify(3, parents + [d, e], ids=self.ids_file(C), club_count=14)
        self.assertIn(f"returned but not read ['{C}']", stop)
        self.assertEqual(self.created()[:3], before)               # batch 2's row is as it was
        out, stop = self.verify(3, parents + [d, e, self.made(2, C)], ids=self.ids_file(D, E), club_count=14)
        self.assertIn(f"{C}: recorded for batch 2 and in this read", stop)
        self.assertEqual(self.created()[:3], before)
        out, stop = self.verify(3, parents + [d, e], ids=self.ids_file(D, E), club_count=14)
        self.assertIsNone(stop)
        self.assertEqual(self.state(3), "closed")

    def test_a_double_write_is_recorded_twice_and_fails(self):
        self.build()
        self.precheck(0, [PARENTS[P1]])
        two = [self.made(0, A), self.made(0, B, Description=None)]
        out, stop = self.verify(0, [PARENTS[P1]] + two, ids=self.ids_file(A, B), club_count=12)
        self.assertIn(f"2 Accounts carry the name (want 1): {A}, {B}", stop)
        self.assertNotIn("does not know", stop)
        self.assertEqual([(r["sf_account_id"], r["action"], r["note"]) for r in self.created()],
                         [(A, "create", "duplicate"), (B, "found-unconfirmed", "duplicate")])
        # the twin is deleted (Ryan's go): the honest count closes the batch, the row stays as gone
        out, stop = self.verify(0, [PARENTS[P1], self.made(0, A)], ids=self.ids_file(A), club_count=11)
        self.assertIsNone(stop)
        self.assertIn("(1 created, 0 linked, 1 gone)", out)
        self.assertEqual([(r["sf_account_id"], r["action"]) for r in self.created()], [(A, "create"), (B, "gone")])

    def test_a_link_keeps_its_before_image_and_stops_on_a_changed_owner(self):
        self.close_batch_0()
        self.assertIn("has a parent already", self.precheck(1, [PARENTS[P1], self.pilot(ParentId=P2)])[1])
        self.assertIsNone(self.precheck(1, [PARENTS[P1], self.pilot()])[1])
        not_yet = self.verify(1, [PARENTS[P1], self.pilot()])
        self.assertIn("ParentId is None", not_yet[1])
        self.assertEqual(len(self.created()), 1)           # a link is recorded only once it is set
        moved = self.verify(1, [PARENTS[P1], self.pilot(ParentId=P1, OwnerId=ME)])
        self.assertIn("Name, owner or record type changed", moved[1])
        renamed = self.verify(1, [PARENTS[P1], self.pilot(ParentId=P1, Name="pilot club")])
        self.assertIn("Name, owner or record type changed", renamed[1])
        out, stop = self.verify(1, [PARENTS[P1], self.pilot(ParentId=P1)])
        self.assertIsNone(stop)
        row = self.created()[1]
        self.assertEqual((row["action"], row["parent_id"], row["previous_parent_id"]), ("link", P1, ""))

    def test_a_lost_state_file_is_a_stop(self):
        self.close_batch_0()
        self.precheck(1, [PARENTS[P1], self.pilot()])
        with open(self.paths.log, encoding="utf-8") as fh:
            log = fh.read()
        os.remove(self.paths.log)
        self.assertIn("run_log.csv has lost rows", self.verify(1, [PARENTS[P1], self.pilot(ParentId=P1)])[1])
        self.assertIn("run_log.csv has lost rows", self.precheck(0, [PARENTS[P1]])[1])
        self.assertIn("would change the batches", self.build(created_on="2026-10-01")[1])
        with open(self.paths.log, "w", encoding="utf-8") as fh:
            fh.write(log)
        os.remove(self.paths.created)
        self.assertIn("are not in created_accounts.csv", self.verify(1, [PARENTS[P1], self.pilot(ParentId=P1)])[1])

    # ---- all names, parents, totals
    def test_precheck_of_all_names_wants_one_read_per_chunk_with_its_parents(self):
        self.build()
        everything = [PARENTS[P1], PARENTS[P2], self.pilot()]
        out, stop = self.precheck_all(everything)
        self.assertIsNone(stop)
        self.assertIn("5 names in 1 chunks", out)
        self.assertIn("expected exactly the pilot account", self.precheck_all([PARENTS[P1], PARENTS[P2]])[1])
        self.assertIn("0 records in the read (want 1)", self.precheck_all([])[1])
        # three chunks of two names: a chunk left out, or answered empty, cannot pass
        self.assertIn("3 chunks, 2 files given", self.precheck_all(everything, everything, chunk=2)[1])
        self.assertIn("chunk 2: parent", self.precheck_all([PARENTS[P1], self.pilot()], [PARENTS[P1], PARENTS[P2]],
                                                           [], chunk=2)[1])

    def test_parents_wants_every_partner_account_and_nothing_else(self):
        self.build()
        both = [PARENTS[P1], PARENTS[P2]]
        self.assertIn("parents ok: 2 partner accounts", self.run_tool(sfc.parents, result=[self.save(both)])[0])
        self.assertIn("0 records in the read", self.run_tool(sfc.parents, result=[self.save(both[:1])])[1])

    def test_totals_counts_every_club_account(self):
        clubs = self.close_all()
        out, stop = self.run_tool(sfc.totals, also=None, result=[self.save(clubs)])
        self.assertIsNone(stop)
        self.assertIn("totals ok", out)
        self.assertIn("Example Partner: 4/4", out)
        self.assertIn(f"created accounts: 4 owned by {ME}, created by {ME}", out)
        self.assertIsNone(self.run_tool(sfc.totals, also=None, result=[self.save(clubs[:3]), self.save(clubs[3:])])[1])
        stray = {"Id": Z, "Name": "Typed By Hand", "RecordTypeId": sfc.CLUB_RECORD_TYPE}
        wrong = {
            "is not in the write set": clubs + [stray],
            "is not among the Club accounts": clubs[:-1],
            "has a parent now": clubs[:-1] + [dict(clubs[-1], ParentId=P1)],
            "Name or Description is not what was sent": [dict(clubs[0], Name="DAWN'S CLUB")] + clubs[1:],
            "ParentId differs from the CSV": [dict(clubs[0], ParentId=P2)] + clubs[1:],
            "name or owner changed": [clubs[0], dict(clubs[1], OwnerId=ME)] + clubs[2:],
            "2 owner/creator pairs": [dict(clubs[0], OwnerId=OWNER)] + clubs[1:],
            "not a Club record": [dict(clubs[0], RecordTypeId=sfc.PARTNER_RECORD_TYPE)] + clubs[1:],
        }
        for message, recs in wrong.items():
            with self.subTest(message):
                self.assertIn(message, self.run_tool(sfc.totals, also=None, result=[self.save(recs)])[1])
        everything = [PARENTS[P1], PARENTS[P2]] + clubs[:5]
        self.assertIn("all names ok after the run", self.precheck_all(everything, after=True)[0])
        twin = dict(PARENTS[P2], Id=Z, Name="Sunrise Club")          # a household of a club's name
        self.assertIn("SUNRISEC: the accounts of that name are",
                      self.precheck_all(everything + [twin], after=True)[1])

    def test_totals_accepts_a_later_round_only_from_its_rollback_file(self):
        clubs = self.close_all()
        late = {"Id": Z, "Name": "Late Club", "RecordTypeId": sfc.CLUB_RECORD_TYPE, "ParentId": P2}
        self.assertIn("is not in the write set",
                      self.run_tool(sfc.totals, also=None, result=[self.save(clubs + [late])])[1])
        round2 = os.path.join(self.tmp.name, "created_accounts_round2.csv")
        with open(round2, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=sfc.CREATED_COLS)
            w.writeheader()
            w.writerow(dict.fromkeys(sfc.CREATED_COLS, "") | {
                "action": "create", "club_code": "LATECLUB", "sf_account_id": Z, "sf_account_name": "Late Club",
                "parent_id": P2})
        out, stop = self.run_tool(sfc.totals, also=[round2], result=[self.save(clubs + [late])])
        self.assertIsNone(stop)
        self.assertIn("later rounds: 1", out)
        self.assertIn("differs from its rollback file",
                      self.run_tool(sfc.totals, also=[round2], result=[self.save(clubs + [dict(late, ParentId=P1)])])[1])
        self.assertIn("is not among the Club accounts",
                      self.run_tool(sfc.totals, also=[round2], result=[self.save(clubs)])[1])

    def test_totals_wants_every_batch_closed(self):
        self.close_batch_0()
        self.assertIn("batch 1 is not closed", self.run_tool(sfc.totals, also=None, result=[self.save([self.made(0, A)])])[1])

    # ---- the live pickers (a fake client)
    def test_pickers_compare_names_calc_values_and_unknown_options(self):
        self.build()
        good = {"U.S": ["Alias Club", "Dawn's Club", "Pilot Club"], "Latin America": ["Niñas Club"],
                "Asia": ["Sunrise Club"], "Africa": ["Twin Club"]}

        def run(options=None, calc=None):
            out = io.StringIO()
            try:
                with contextlib.redirect_stdout(out):
                    sfc.pickers(None, self.paths, client=FakeForms(dict(good, **(options or {})), calc))
            except SystemExit as stop:
                return out.getvalue() + str(stop.code)
            return out.getvalue()

        self.assertIn("pickers ok", run())
        self.assertIn("calcValues DIFFER", run(calc={"Asia": "Sunrise Club"}))           # no leading slot
        self.assertIn("case-only 1 ['SUNRISEC']", run({"Asia": ["SUNRISE CLUB"]}))
        self.assertIn("not on the picker 1 ['SUNRISEC']", run({"Asia": []}))
        self.assertIn("options this list does not know 1 ['Brand New Club']",
                      run({"Asia": ["Sunrise Club", "Brand New Club"]}))
        self.assertIn("pickers FAILED", run({"Asia": ["Sunrise Club", "Brand New Club"]}))
        # the held clubs' names, plain or with the partner, are known to the list
        self.assertIn("pickers ok", run({"Africa": ["Twin Club - Example Partner", "Twin Club - Second Partner"]}))


if __name__ == "__main__":
    unittest.main(verbosity=1)
