"""The one table of Jotform form ids.

Every Python tool reads it from here; appsscript/Config.gs carries the same
ids for the Apps Script side, and test/gs_parity_test.py fails when they drift.
The regional forms went live 2026-09-01 (cloned from the template 2026-08-27);
the defunct forms are the pre-launch ones, kept as archives.
"""

TEMPLATE = "262352490535154"
TEMPLATE_TITLE = "Attendance Form (Template)"

REGIONALS = {
    "Africa": "262382821971058",
    "Asia": "262383129464057",
    "Latin America": "262383455778067",
    "U.S": "262382706852058",
}

DEFUNCT = {
    "master": "260555608160556",
    "Africa": "260703905772560",
    "Asia": "260704198384564",
    "Latin America": "260704170003542",
    "U.S": "260703912140547",
}

REGIONS = tuple(REGIONALS)

# form id -> region name, "template" for the template
LIVE = {TEMPLATE: "template", **{fid: region for region, fid in REGIONALS.items()}}

# human-readable label per id (what backup_forms.py prints)
LABELS = {
    TEMPLATE: "template (every sync-logic change lands here first)",
    **{fid: f"{region} (live from 2026-09-01)" for region, fid in REGIONALS.items()},
    **{fid: f"{region} (defunct)" for region, fid in DEFUNCT.items()},
}

TITLES = {region: f"{region} Attendance Form" for region in REGIONALS}


def language_of(props):
    """A form's `language` property (GET /form/{id}/properties) as one dict: Jotform serves
    it as a list of one, a dict, or not at all ({})."""
    lang = (props or {}).get("language")
    return lang[0] if isinstance(lang, list) and lang else (lang or {})


def region_of(form_id):
    """The region a live form serves, or None (template / unknown / defunct)."""
    region = LIVE.get(form_id)
    return region if region in REGIONALS else None
