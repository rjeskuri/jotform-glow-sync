#!/usr/bin/env python3
"""
The constants that exist in BOTH Python and appsscript/Config.gs / Roster.gs - form ids, qids,
SESSION_OVERRIDES, SF_NAME_SEP, the Roster, Partners and SyncLog columns - so a change on one
side fails here until the other side follows (CLAUDE.md rule 7); and the same-name rule itself,
run on both sides over one fictional Roster (the Apps Script side in Node, through
test/load_gs.js).
"""
import os
import re
import unittest

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import REPO, apps_script_same_name, read
import auto_sync
import form_status
import sync_attendance_form as sync
from glow import sync as glow_sync


CONFIG_GS = os.path.join(REPO, "appsscript", "Config.gs")
ROSTER_GS = os.path.join(REPO, "appsscript", "Roster.gs")


def gs_block(src, name):
    """Body of `const NAME = {...};` or `const NAME = [...];` in a .gs file."""
    m = re.search(r"const %s = [\{\[](.*?)\n?[\}\]];" % re.escape(name), src, re.S)
    assert m, name
    return m.group(1)


class PythonAppsScriptParity(unittest.TestCase):
    def setUp(self):
        self.config = read(CONFIG_GS)

    def test_form_ids(self):
        forms = dict(re.findall(r"^\s+([A-Z_]+): '(\d+)',", gs_block(self.config, "FORMS"), re.M))
        self.assertEqual({"Africa": forms["AFRICA"], "Asia": forms["ASIA"],
                          "Latin America": forms["LATIN_AMERICA"], "U.S": forms["US"]},
                         auto_sync.REGIONAL_FORMS)
        template = [fid for fid, (label, _) in form_status.FORMS.items() if label == "template"]
        self.assertEqual(template, [forms["TEMPLATE"]])
        self.assertEqual({fid for fid, (_, region) in form_status.FORMS.items() if region},
                         set(auto_sync.REGIONAL_FORMS.values()))
        self.assertTrue(all(re.fullmatch(r"\d{15}", f) for f in auto_sync.REGIONAL_FORMS.values()))
        # every other Python copy of the table (docs promise this test catches drift)
        import add_feedback_link
        import add_language
        import add_translations
        import backup_forms
        import clone_regional
        import restore_translations
        live = set(auto_sync.REGIONAL_FORMS.values()) | {forms["TEMPLATE"]}
        defunct = set(form_status.DEFUNCT)
        self.assertEqual(set(backup_forms.FORMS), live | defunct)
        self.assertEqual(set(add_translations.FORMS), live)
        self.assertEqual(set(add_language.FORMS), live)
        self.assertEqual(set(add_feedback_link.FORMS), live)
        self.assertEqual(clone_regional.WORKING_COPY, forms["TEMPLATE"])
        self.assertEqual(restore_translations.TEMPLATE, forms["TEMPLATE"])
        self.assertEqual(set(clone_regional.TITLES), set(auto_sync.REGIONAL_FORMS))

    def test_picker_name_is_shared(self):
        # the sync and form_status find the Club picker with one function, by one name
        self.assertIs(form_status.club_picker, glow_sync.club_picker)
        self.assertIs(sync.club_picker, glow_sync.club_picker)
        self.assertEqual(sync.PICKER_NAME, glow_sync.PICKER_NAME)

    def test_qids(self):
        block = gs_block(self.config, "QID")
        simple = dict(re.findall(r"^\s+([A-Z_]+): '(\d+)',", block, re.M))
        self.assertEqual(simple["CLUB_NAME"], sync.CLUB_NAME)
        self.assertEqual(simple["PARTNER"], sync.PARTNER)
        self.assertEqual(simple["YEAR"], sync.YEAR)
        self.assertEqual((simple["CONTACT_IDS"], simple["MODULE_ID"], simple["WEEK_ID"], simple["YEAR_ID"]),
                         (sync.CONTACT_IDS, sync.MODULE_ID, sync.WEEK_ID, sync.YEAR_ID))
        self.assertEqual(simple["ENABLE_FUZZY"], form_status.ENABLE_FUZZY_QID)
        self.assertEqual((simple["CLUB_NAME"], simple["PARTNER"], simple["CONTACT_IDS"]),
                         (form_status.CLUB_NAME_QID, form_status.PARTNER_QID, form_status.CONTACT_IDS_QID))
        modules = dict(re.findall(r"'(\d)': '(\d+)'", re.search(r"MODULE: \{([^}]*)\}", block).group(1)))
        self.assertEqual(modules, sync.MODULES)
        sessions = {int(k): v for k, v in
                    re.findall(r"(\d+): '(\d+)'", re.search(r"SESSIONS: \{([^}]*)\}", block).group(1))}
        self.assertEqual(sessions, sync.WEEKS)

    def test_session_overrides(self):
        # tolerant of a missing trailing comma and of double-quoted keys, so a
        # GS-side addition can never be invisible to this test
        block = gs_block(self.config, "SESSION_OVERRIDES")
        pairs = {k or k2: int(v) for k, k2, v in
                 re.findall(r"(?:'([^']+)'|\"([^\"]+)\")\s*:\s*(\d+)\s*,?", block)}
        self.assertEqual(pairs, sync.SESSION_OVERRIDES)
        self.assertEqual(len(pairs), block.count(":"))   # every entry was parsed

    def test_the_same_name_separator(self):
        # "<club> - <partner>" is one string on both sides: the forms' Club picker entry and
        # question 5 (Python), the Monday e-mail's Salesforce account name and the intake
        # check (Apps Script). CLAUDE.md rule 7: change both
        found = re.findall(r"^const SF_NAME_SEP = '([^'\n]*)';", self.config, re.M)
        self.assertEqual(found, [glow_sync.SF_NAME_SEP])
        self.assertEqual([ord(c) for c in glow_sync.SF_NAME_SEP], [0x20, 0x2D, 0x20])   # no long dash
        # one definition per side, used by name everywhere else
        self.assertIs(sync.SF_NAME_SEP, glow_sync.SF_NAME_SEP)
        self.assertIs(form_status.SF_NAME_SEP, glow_sync.SF_NAME_SEP)
        for name in sorted(os.listdir(os.path.join(REPO, "appsscript"))):
            if name.endswith(".gs") and name != "Config.gs":
                self.assertNotRegex(read(os.path.join(REPO, "appsscript", name)),
                                    r"(?:const|let|var)\s+SF_NAME_SEP\b", name)

    # One fictional Roster for both sides: (partner, club, full_name, status, region)
    SAME_NAME_ROSTER = [
        ("Partner One", "Stars", "Ann Poe", "active", "Africa"),
        ("Partner One", "Stars", "Kay Loe", "inactive", "Africa"),
        ("Partner Two", "Stars", "Sue Moe", "active", "Asia"),            # another region: one Salesforce org
        ("Partner Four", "STARS", "Liz Noe", " Active ", "U.S"),          # capitals; the status as typed
        ("Partner One", "Alpha Club", "Jane Doe", "active", "Africa"),
        ("partner  one", "Alpha  Club", "Mary Roe", "active", "Africa"),  # one partner written twice
        ("Partner Two", "Beta Club", "Eve Hoe", "active", "Asia"),
        ("Partner Three", "Beta Club", "Ida Toe", "inactive", "U.S"),     # a retired namesake
        ("Partner One", "Comet Club", "Uma Roe", "active", "Africa"),
        ("Partner Two", "Comet Club", "", "active", "Asia"),              # a row with no girl
        ("Partner Two", "Alpha Club - Juniors", "Amy Foe", "active", "Asia"),   # its own " - "
        ("Partner Two", "Étoiles", "Bea Goe", "active", "Asia"),
        ("Fundación Demo", "étoiles", "Cy Joe", "active", "Latin America"),     # accents kept, case not
        ("Partner Three", "Moon", "Dee Koe", "inactive", "U.S"),          # nobody's active club
        ("", "Stars", "Fay Low", "active", "Africa"),                     # no partner: reaches no form
        ("Partner Three", "", "Gia Mow", "active", "U.S"),                # no club
    ]

    def same_name_sides(self, probes=()):
        """(Python's roster_pairs of SAME_NAME_ROSTER, its active clubs, what Apps
        Script makes of the same rows)."""
        import csv
        import tempfile
        cols = ["partner", "club", "full_name", "status", "region"]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "roster.csv")
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["girl_id"] + cols)
                for n, row in enumerate(self.SAME_NAME_ROSTER):
                    w.writerow([f"DEMOCLUB-SAMPLE-{n:03d}", *row])
            pairs = glow_sync.roster_pairs(path)
        active = sorted(pc for pc, is_active in pairs.items() if is_active)
        gs = apps_script_same_name([dict(zip(cols, row)) for row in self.SAME_NAME_ROSTER],
                                   pairs=active, probes=probes)
        if gs is None:
            self.skipTest("node is not installed: the Apps Script side cannot run")
        return pairs, active, gs

    def test_the_switch_rule_agrees_with_apps_script(self):
        # which clubs are "<club> - <partner>": Python decides it for the forms
        # (sync_attendance_form.py --same-name-switch goes by shared_club_names(active_only=True)),
        # Apps Script for the Monday e-mail's Salesforce account names (sharedClubNames_ /
        # sfClubName_). Both run here, on the same rows
        from glow.text import key
        pairs, active, gs = self.same_name_sides()
        shared = glow_sync.shared_club_names(pairs, active_only=True)
        self.assertEqual(gs["sep"], glow_sync.SF_NAME_SEP)
        self.assertEqual(gs["shared"], sorted(shared))
        self.assertEqual(sorted(shared), ["stars", "étoiles"])     # pinned: neither side is empty
        names = [glow_sync.sf_club_name(club, partner, key(club) in shared) for partner, club in active]
        self.assertEqual(gs["names"], names)
        self.assertEqual(dict(zip(active, names)), {
            ("Fundación Demo", "étoiles"): "étoiles - Fundación Demo",
            ("Partner Four", "STARS"): "STARS - Partner Four",             # its own spelling kept
            ("Partner One", "Alpha Club"): "Alpha Club",                   # one partner, written twice
            ("Partner One", "Comet Club"): "Comet Club",                   # its namesake has no girl
            ("Partner One", "Stars"): "Stars - Partner One",
            ("Partner Two", "Alpha Club - Juniors"): "Alpha Club - Juniors",
            ("Partner Two", "Beta Club"): "Beta Club",                     # its namesake is retired
            ("Partner Two", "Stars"): "Stars - Partner Two",
            ("Partner Two", "Étoiles"): "Étoiles - Partner Two"})
        # no two clubs end up with one Salesforce name, on either side
        self.assertEqual(glow_sync.sf_name_clashes(zip(gs["names"], active)), [])

    def test_a_name_in_use_is_the_same_on_both_sides(self):
        # Ryan's decision 2: a NEW club may not take a name another partner's club has - any
        # status, any region, a girl on the row or not. The sync refuses to create it
        # (sync_attendance_form.py: glow.sync.club_partners over roster_pairs); the Club Roster
        # Form handler holds it before it reaches the Roster (newClubHoldReasons_, kind samename)
        from glow.text import key
        clubs = ["Stars", "stars", "Beta Club", "Comet Club", "Moon", "Alpha Club", "Étoiles",
                 "Alpha Club - Juniors", "Brand New Club", "Star"]
        probes = [(partner, club) for club in clubs
                  for partner in ("Partner Nine", "Partner One", "Partner Three")]
        pairs, _, gs = self.same_name_sides(probes)
        holders = glow_sync.club_partners(pairs)
        active = {(key(p), key(c)) for (p, c), is_active in pairs.items() if is_active}
        held = dict(zip(probes, gs["held"]))

        def on_file(partner, club):
            return key(partner) in holders.get(key(club), {})

        def taken(partner, club):
            return any(k != key(partner) for k in holders.get(key(club), {}))

        new = [p for p in probes if not on_file(*p)]
        self.assertEqual(len(new), 24)
        self.assertEqual({p: held[p] for p in new}, {p: taken(*p) for p in new})
        self.assertTrue(held[("Partner Nine", "Stars")])
        self.assertTrue(held[("Partner Nine", "stars")])                # capitals do not make a new name
        self.assertTrue(held[("Partner Nine", "Moon")])                 # a retired club's name is in use
        self.assertTrue(held[("Partner Three", "Comet Club")])          # ...and one a row with no girl holds
        self.assertTrue(held[("Partner One", "Alpha Club - Juniors")])  # a club's own " - " is its name
        self.assertFalse(held[("Partner Nine", "Brand New Club")])
        self.assertFalse(held[("Partner Nine", "Star")])                # a different name
        # a club the partner has on file with an active girl is no new club on either side:
        # the sync matches it to its roster, the handler runs it as that club
        own = [p for p in probes if (key(p[0]), key(p[1])) in active]
        self.assertEqual(sorted(own), [("Partner One", "Alpha Club"), ("Partner One", "Comet Club"),
                                       ("Partner One", "Stars"), ("Partner One", "stars")])
        self.assertEqual([held[p] for p in own], [False] * 4)
        # the documented divergence (docs/ARCHITECTURE.md, Known divergences): a club on file
        # with NO active girl whose name another partner's club has is held at intake; the
        # sync refuses it only when its roster question is gone and it would be created
        self.assertTrue(held[("Partner Three", "Beta Club")])
        self.assertFalse(held[("Partner Three", "Moon")])               # retired, and nobody else's name

    def test_synclog_columns(self):
        m = re.search(r"const SYNC_LOG_COLS = \[(.*?)\];", read(ROSTER_GS), re.S)
        self.assertEqual(re.findall(r"'([a-z0-9_]+)'", m.group(1)), auto_sync.SYNC_LOG_COLS)
        self.assertEqual(m.group(1).count("'") // 2, len(auto_sync.SYNC_LOG_COLS))
        self.assertIn("SYNC_LOG: 'SyncLog'", self.config)
        self.assertEqual(auto_sync.SYNC_LOG_TAB, "SyncLog")

    def test_roster_columns_python_side_is_a_subset(self):
        cols = re.findall(r"'([a-z_]+)'", gs_block(self.config, "ROSTER_COLS"))
        self.assertTrue({"partner", "club", "full_name", "status", "region"} <= set(cols))
        self.assertEqual(cols[0], "girl_id")

    def test_partner_columns(self):
        # the Partners tab's columns: Roster.gs writes them (setUpTabs, seedPartners_) and reads the
        # jotform cell for the mentor e-mails (loadPartnerJotform_), the offline builder keeps its own
        # copy, Python reads the cell for the forms (glow.sync). CLAUDE.md rule 7: change all three
        for path in (ROSTER_GS, os.path.join(REPO, "tools", "build_roster_offline.js")):
            m = re.search(r"const PARTNER_COLS = \[(.*?)\];", read(path), re.S)
            self.assertIsNotNone(m, path)
            self.assertEqual(tuple(re.findall(r"'([a-z_]+)'", m.group(1))), glow_sync.PARTNER_COLS, path)
            self.assertEqual(m.group(1).count("'") // 2, len(glow_sync.PARTNER_COLS), path)
        self.assertIn(glow_sync.JOTFORM_COL, glow_sync.PARTNER_COLS)
        self.assertEqual(glow_sync.PARTNER_COLS[:3], ("partner", "region", "notes"))   # the live tab's header
        # the Apps Script finds the column by the tab's own header row (key_), as Python's
        # read_partners_csv reads the export by header - never by the constant's position
        reader = re.search(r"function loadPartnerJotform_\(\) \{(.*?)\n\}", read(ROSTER_GS), re.S).group(1)
        self.assertIn("getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0].map(key_)", reader)
        self.assertIn(f"header.indexOf('{glow_sync.JOTFORM_COL}')", reader)
        self.assertNotIn("PARTNER_COLS", reader)

    def test_regions_match_glow_forms(self):
        # the Club Roster Form's region picker (Config.gs REGIONS) must offer
        # exactly the regions the Python sync routes on — spelling included
        from glow import forms as glow_forms
        regions = re.findall(r"'([^']+)'", gs_block(self.config, "REGIONS"))
        self.assertEqual(tuple(regions), glow_forms.REGIONS)
        self.assertIn("U.S", regions)                     # one dot, no trailing dot
        self.assertIn("REGION: 'Region where this club meets'", self.config)

    def test_the_architecture_table_lists_every_mirrored_constant(self):
        # docs/ARCHITECTURE.md's "change both" table is the human copy of CLAUDE.md
        # rule 7: one three-cell row per constant (a row with more cells than the
        # header renders without its extra cells, and that constant disappears)
        doc = read(os.path.join(REPO, "docs", "ARCHITECTURE.md"))
        section = doc.split("## Constants that exist on both sides", 1)[1].split("\n## ", 1)[0]
        rows = [ln for ln in section.splitlines() if ln.startswith("|")][2:]   # past header + rule
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row.count("|"), 4, row)
        firsts = [row.split("|")[1] for row in rows]
        for constant in ("Live form ids", "Structural question ids", "SESSION_OVERRIDES",
                         "`SF_NAME_SEP`", "Roster tab columns", "SyncLog columns"):
            self.assertEqual(sum(constant in f for f in firsts), 1, constant)


if __name__ == "__main__":
    unittest.main(verbosity=1)
