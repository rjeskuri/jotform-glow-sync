#!/usr/bin/env python3
"""
glow/sf_keep_list.csv, ticket #70 (epic #68): GLOW's keep list for the Monthly Report (`DHIS2__c`)
reports and dashboards, each item mapped to the report or dashboard in the org that it is today.

KeepList: the 19 items and the five dashboards, each with its group and GLOW's measure verbatim (the
GLOW team via Ryan, 2026-10-21; the test carries the list), mapped to the ids Ryan agreed on the
ticket (2026-10-23, "all as proposed"; item 12 had no report until task #80 built it). Ryan's answer
(c), "do NOT change the labels. Kept reports and dashboards keep their current names", replaces the
ticket's first label convention (drop "M&P", a dashboard named after its group): every row's target
label is its label today, except the rows GLOW's review of 2026-11-02 (epic #194) renames: RENAMED, item 17
since ticket #200, whose target is GLOW's name within 40 characters (label_today stays the label #70 recorded).

NewMentorsReport (ticket #80, plan docs/plans/2026-10-26-sf-new-mentors.md, Rollout step 8): item 12
is the report #80 deployed on 2026-10-26, "Partners that recruited new mentors" (GLOW Monthly Reports),
so no row's id reads `new` any more.
The file holds report and dashboard ids and names only, never record data.
"""
import csv
import glob
import os
import re
import unittest

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import REPO, md_part, read

KEEP_LIST = os.path.join(REPO, "glow", "sf_keep_list.csv")
HEADER = ["item", "group", "measure", "kind", "id", "label_today", "label_target"]

GROUPS = ("GLOW Club Attendance", "GLOW Club Implementation", "GLOW Club Observations", "GLOW Club Training",
          "GLOW Club Reporting")
TABLE_GROUP = "Report/Data Table Format"

# item: (group, GLOW's measure verbatim) - the keep list of 2026-10-21 (ticket #70, Context)
ITEMS = {
    "1": ("GLOW Club Attendance", "Whether attendance rosters were collected"),
    "2": ("GLOW Club Attendance", "Attendance rosters uploaded on the Drive"),
    "3": ("GLOW Club Attendance", "Monthly attendance totals"),
    "4": ("GLOW Club Attendance", "Weekly attendance totals"),
    "5": ("GLOW Club Implementation", "GLOW Club activities carried out"),
    "6": ("GLOW Club Implementation", "GLOW Club modules implemented"),
    "7": ("GLOW Club Implementation", "GLOW Club modules adapted to the local context"),
    "8": ("GLOW Club Implementation", "Summits completed"),
    "9": ("GLOW Club Observations", "GLOW Club observation form submitted"),
    "10": ("GLOW Club Observations", "Number of GLOW Club sessions observed"),
    "11": ("GLOW Club Observations", "Whether or not PC has observed sessions"),
    "12": ("GLOW Club Training", "New mentors recruited"),
    "13": ("GLOW Club Training", "Number of mentors who attended training"),
    "14": ("GLOW Club Training", "Number of training sessions led"),
    "15": ("GLOW Club Training", "Whether PC led any training sessions with mentors"),
    "16": ("GLOW Club Training", "Whether PC met with mentors as a group to discuss program implementation"),
    "17": ("GLOW Club Reporting", "Report approved by PO"),
    "18": ("GLOW Club Reporting", "Report submitted on time"),
    "19": (TABLE_GROUP, "GLOW of the Month Stories"),
}
# a dashboard's measure is its group (D1-D5 in the list's order)
ITEMS.update({f"D{i}": (g, g) for i, g in enumerate(GROUPS, 1)})

# item: (kind, id, label today) - Ryan, 2026-10-23, on ticket #70: (a) and (b) all as proposed;
# labels exactly as #69's inventory (SOQL) gives them
AGREED = {
    "1": ("report", "00ORP000004RJYv2AO", "Collection of Attendance Roster by Month"),
    "2": ("report", "00ORP000005rTiX2AU", "Attendance Roster Uploaded on DR by M&P"),
    "3": ("report", "00ORP000005rSbB2AU", "Participation by Month and Partner"),
    "4": ("report", "00ORP000005ufOz2AI", "GLOW Club Each Week"),
    "5": ("report", "00ORP000005rY3t2AE", "Copy of GLOW Club Implementation by M&P"),
    "6": ("report", "00ORP000005rZxd2AE", "Glow Club Modules Implemented by M&P"),
    "7": ("report", "00ORP000005uehR2AQ", "GLOW Club Modules Adapted By Month"),
    "8": ("report", "00ORP000005uekf2AA", "Local and Regional Summits By Month 2"),
    "9": ("report", "00ORP000004RJZC2A4", "Submission of GC observation forms M & P"),
    "10": ("report", "00ORP000004RJZD2A4", "Total Number of Club Observations M&P"),
    "11": ("report", "00ORP000005uf412AA", "Completed Observing Clubs Alteast Once P"),
    "12": ("report", "00ORP000009kXev2AE", "Partners that recruited new mentors"),  # #80, deployed 2026-10-26
    "13": ("report", "00ORP000004RJZE2A4", "Number of mentors trained about module"),
    "14": ("report", "00ORP000004RJZ82AO", "Number of training sessions led"),
    "15": ("report", "00ORP000004RJZ62AO", "Leading training sessions with mentors"),
    "16": ("report", "00ORP000004RJZ72AO", "Meeting with mentors to discuss program"),
    "17": ("report", "00ORP000006XXEf2AO", "Approved Approvals monthly report"),
    "18": ("report", "00ORP0000054DyH2AU", "Reports completed on time"),
    "19": ("table", "00ORP000005p2L32AI", "GLOW of the Month Stories Report"),  # Ryan, 2026-10-23: the org's 10-21 rename
    "D1": ("dashboard", "01ZRP000006iWqL2AU", "Glow Club Attendance"),
    "D2": ("dashboard", "01ZRP000006jU9o2AE", "Implementation Dashboard"),
    "D3": ("dashboard", "01ZRP000006k2D32AI", "GLOW Club Training"),
    "D4": ("dashboard", "01ZRP000006quAj2AI", "Mentors"),
    "D5": ("dashboard", "01ZRP000006oxSr2AI", "Reporting"),
}
# GLOW's review of 2026-11-02 (epic #194) renames some kept reports, superseding (c) for these rows only:
# item: label_target. Ticket #200 (Outline step 3): item 17, GLOW's name within 40 characters.
RENAMED = {
    "17": "Monthly Report Approval Status",
}
# ticket #80: the report it deployed for item 12 (2026-10-26, folder GLOW Monthly Reports)
ITEM_12_ID = "00ORP000009kXev2AE"
ITEM_12_LABEL = "Partners that recruited new mentors"


def case_safe_suffix(id15):
    """The three characters Salesforce appends to a 15-character id to make it case-insensitive: for
    each block of five, the bits of its upper-case letters (first character lowest), as a letter of
    A-Z0-5."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"
    out = ""
    for block in (id15[0:5], id15[5:10], id15[10:15]):
        out += alphabet[sum(1 << i for i, c in enumerate(block) if "A" <= c <= "Z")]
    return out


class KeepList(unittest.TestCase):
    """Ticket #70: GLOW's keep list mapped to the org, as agreed on the ticket (Ryan, 2026-10-23)."""

    longMessage = False         # the messages say what to fix

    def rows(self):
        self.assertTrue(os.path.isfile(KEEP_LIST), "glow/sf_keep_list.csv: missing (ticket #70 creates it, header "
                                                   + ",".join(HEADER) + ")")
        with open(KEEP_LIST, encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            self.assertEqual(header, HEADER, "glow/sf_keep_list.csv: the header is exactly " + ",".join(HEADER)
                                             + " (no BOM, no other column)")
            rows = [r for r in reader if any(c.strip() for c in r)]
        for r in rows:
            self.assertEqual(len(r), len(HEADER), f"glow/sf_keep_list.csv: row {r!r} has {len(r)} cells, not "
                                                  f"{len(HEADER)}")
        return [dict(zip(HEADER, r)) for r in rows]

    def by_item(self):
        rows = self.rows()
        items = [r["item"] for r in rows]
        twice = sorted({i for i in items if items.count(i) > 1})
        self.assertEqual(twice, [], f"glow/sf_keep_list.csv: item(s) {twice} on more than one row")
        return {r["item"]: r for r in rows}

    # --- broad: the list, the mapping, the labels ------------------------------------------------------

    def test_the_keep_list_has_the_nineteen_items_and_five_dashboards(self):
        rows = self.by_item()
        want = [str(i) for i in range(1, 20)] + [f"D{i}" for i in range(1, 6)]
        self.assertEqual(sorted(rows), sorted(want), "glow/sf_keep_list.csv: one row per item 1-19 and D1-D5, "
                                                     f"nothing else (found {sorted(rows)})")
        for item, (group, measure) in ITEMS.items():
            row = rows[item]
            self.assertEqual(row["group"], group, f"glow/sf_keep_list.csv item {item}: group is {group!r}")
            self.assertEqual(row["measure"], measure,
                             f"glow/sf_keep_list.csv item {item}: measure is GLOW's wording {measure!r}"
                             + (" (a dashboard's measure is its group)" if item.startswith("D") else ""))
        dashboards = {r["group"] for r in rows.values() if r["kind"] == "dashboard"}
        self.assertEqual(dashboards, set(GROUPS), "glow/sf_keep_list.csv: the five groups are the five dashboards")
        reports = [i for i, r in rows.items() if r["kind"] == "report"]
        self.assertEqual(len(reports), 18, f"glow/sf_keep_list.csv: items 1-18 are the 18 reports (found {reports})")

    def test_each_item_maps_to_the_agreed_report_or_dashboard(self):
        rows = self.by_item()
        for item, (kind, sf_id, label) in AGREED.items():
            self.assertIn(item, rows, f"glow/sf_keep_list.csv: no row for item {item}")
            row = rows[item]
            got = (row["kind"], row["id"], row["label_today"])
            self.assertEqual(got, (kind, sf_id, label),
                             f"glow/sf_keep_list.csv item {item}: (kind, id, label_today) is {(kind, sf_id, label)!r}, "
                             f"as agreed on ticket #70 (Ryan, 2026-10-23), not {got!r}")

    def test_kept_items_keep_their_current_labels(self):
        # Ryan, 2026-10-23, (c): "do NOT change the labels. Kept reports and dashboards keep their current names."
        # GLOW's review of 2026-11-02 renames the rows of RENAMED (#200: item 17); every other row keeps its label.
        rows = self.by_item()
        for item, row in rows.items():
            where = f"glow/sf_keep_list.csv item {item}"
            target = row["label_target"]
            self.assertTrue(target.strip(), f"{where}: label_target is blank (no row is undecided)")
            self.assertEqual(target, target.strip(), f"{where}: label_target has stray spaces")
            self.assertLessEqual(len(target), 40, f"{where}: label_target {target!r} is over 40 characters "
                                                  "(Salesforce's limit on a report's name)")
            self.assertTrue(row["label_today"].strip(), f"{where}: label_today is blank")
            if item in RENAMED:
                self.assertEqual(target, RENAMED[item],
                                 f"{where}: label_target is GLOW's name {RENAMED[item]!r} (GLOW's review, 2026-11-02; "
                                 f"ticket #200), not {target!r}")
                continue
            self.assertEqual(target, row["label_today"],
                             f"{where}: label_target is the label today, {row['label_today']!r} (Ryan, "
                             "2026-10-23: kept reports and dashboards keep their current names)")

    # --- specific ------------------------------------------------------------------------------------

    def test_item_19_glow_of_the_month_stories_is_a_table_of_its_own_group(self):
        rows = self.by_item()
        self.assertEqual(rows["19"]["kind"], "table", "glow/sf_keep_list.csv item 19: kind is `table` (a tabular "
                                                      "report, not a dashboard component)")
        self.assertEqual(rows["19"]["group"], TABLE_GROUP, f"glow/sf_keep_list.csv item 19: group is {TABLE_GROUP!r}")
        others = [i for i, r in rows.items() if i != "19" and (r["kind"] == "table" or r["group"] == TABLE_GROUP)]
        self.assertEqual(others, [], f"glow/sf_keep_list.csv: only item 19 is a table of {TABLE_GROUP!r} "
                                     f"(also {others})")

    def test_every_item_has_its_id(self):
        rows = self.by_item()
        prefix = {"report": "00O", "table": "00O", "dashboard": "01Z"}
        for item, row in rows.items():
            where = f"glow/sf_keep_list.csv item {item}"
            for col in HEADER:
                self.assertNotIn("?", row[col], f"{where}: `?` left in {col} (no row is undecided)")
            self.assertIn(row["kind"], prefix, f"{where}: kind is report, table or dashboard, not {row['kind']!r}")
            sf_id = row["id"]
            self.assertRegex(sf_id, r"^[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?$",
                             f"{where}: id {sf_id!r} is a 15- or 18-character Salesforce id (no item reads `new` "
                             "since #80 built item 12's report)")
            self.assertTrue(sf_id.startswith(prefix[row["kind"]]),
                            f"{where}: a {row['kind']}'s id starts {prefix[row['kind']]}, not {sf_id[:3]!r}")
            if len(sf_id) == 18:
                self.assertEqual(sf_id[15:], case_safe_suffix(sf_id[:15]),
                                 f"{where}: id {sf_id!r} is mistyped (its last three characters do not match "
                                 "the first fifteen)")

    def test_no_id_is_kept_twice(self):
        rows = self.rows()
        ids = [r["id"] for r in rows]
        # a 15-character id and its 18-character form are the same record
        keys = [i[:15] for i in ids]
        twice = sorted({i for i in ids if keys.count(i[:15]) > 1})
        self.assertEqual(twice, [], f"glow/sf_keep_list.csv: id(s) {twice} on more than one row")
        self.assertEqual(len(ids), 24, f"glow/sf_keep_list.csv: 24 ids (every row, item 12 included since #80), "
                                       f"found {len(ids)}")

    def test_item_12_has_its_new_report(self):
        # ticket #80, plan Rollout step 8: item 12's id is the report #80 deployed, both labels its name
        rows = self.by_item()
        where = "glow/sf_keep_list.csv item 12"
        self.assertIn("12", rows, f"{where}: no row")
        row = rows["12"]
        self.assertEqual((row["group"], row["measure"], row["kind"]),
                         ("GLOW Club Training", "New mentors recruited", "report"),
                         f"{where}: still GLOW Club Training's report for GLOW's measure 'New mentors recruited'")
        sf_id = row["id"]
        self.assertNotEqual(sf_id, "new", f"{where}: id still reads `new`; it is the report #80 deployed, "
                                          f"{ITEM_12_ID} (plan docs/plans/2026-10-26-sf-new-mentors.md, Rollout step 8)")
        self.assertRegex(sf_id, r"^00O[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$",
                         f"{where}: id {sf_id!r} is a report id (00O, 15 or 18 characters)")
        if len(sf_id) == 18:
            self.assertEqual(sf_id[15:], case_safe_suffix(sf_id[:15]),
                             f"{where}: id {sf_id!r} is mistyped (its last three characters do not match the "
                             "first fifteen)")
        self.assertEqual(sf_id[:15], ITEM_12_ID[:15], f"{where}: id is {ITEM_12_ID} (the report #80 deployed), "
                                                      f"not {sf_id!r}")
        for col in ("label_today", "label_target"):
            self.assertEqual(row[col], ITEM_12_LABEL, f"{where}: {col} is the deployed report's name "
                                                      f"{ITEM_12_LABEL!r}, not {row[col]!r}")
        news = [r["item"] for r in rows.values() if r["id"].strip().lower() == "new"]
        self.assertEqual(news, [], f"glow/sf_keep_list.csv: item(s) {news} still read `new` (every item has its report)")

    def test_no_report_from_the_attendance_folders_is_in_it(self):
        # the "Jotform Attendance" dashboard and the two Attendance folders stay untouched (epic #68); their
        # ids are the ones the RUNBOOK's Attendance section and the attendance plans name
        # (not the Monthly Report dashboard plans, `<date>-sf-dash-<name>.md`: "GLOW Club Attendance" is a Monthly
        # Report dashboard, ticket #75, and its ids are the keep list's own)
        text = md_part(os.path.join(REPO, "docs", "RUNBOOK.md"), "## Attendance dashboard in Salesforce")
        plans = [p for p in glob.glob(os.path.join(REPO, "docs", "plans", "*attendance*.md"))
                 if not re.match(r"\d{4}-\d\d-\d\d-sf-dash-", os.path.basename(p))]
        self.assertIn(os.path.join(REPO, "docs", "plans", "2026-10-02-attendance-dashboard.md"), plans,
                      "test: the Jotform Attendance dashboard's plan is among the plans checked against")
        for plan in plans:
            text += "\n" + read(plan)
        attendance = {m[:15] for m in re.findall(r"\b(?:00O|01Z)[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\b", text)}
        self.assertTrue(attendance, "test: found no Attendance report or dashboard id in the docs to check against")
        for r in self.rows():
            self.assertNotIn(r["id"][:15], attendance, f"glow/sf_keep_list.csv item {r['item']}: {r['id']} is an "
                                                       "Attendance report or dashboard, which epic #68 leaves untouched")
            for col in ("label_today", "label_target"):
                self.assertNotRegex(r[col], r"(?i)^(Jotform Attendance|Girls Attended)\b",
                                    f"glow/sf_keep_list.csv item {r['item']}: {col} {r[col]!r} is on the Attendance side")

    def test_the_file_holds_report_and_dashboard_ids_only(self):
        # like glow/sf_partners.csv: report and dashboard ids and names, never record data (an Account, a Contact)
        for r in self.rows():
            for col in HEADER:
                self.assertNotRegex(r[col], r"\b(001|003|005|a0[0-9A-Za-z])[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\b",
                                    f"glow/sf_keep_list.csv item {r['item']}: {col} holds a record id; the file "
                                    "holds report and dashboard ids only")


if __name__ == "__main__":
    unittest.main(verbosity=1)
