"""Shared library for the GLOW tooling (docs/intent/2026-09-01-shared-jotform-client.md).

- glow.jotform:      the one curl-based Jotform client, dry-run gated; public_page()
- glow.forms:        the one table of form ids (Python-only)
- glow.text:         normalization helpers shared by every tool (key, name_key; the sheet's
                     tidy / cell_key / nfc_key)
- glow.sync:         the enrollment/Roster parsers and the structural question ids
- glow.submissions:  a form's submissions read: the answer to a question, the ticked rosters,
                     the attendance date, the module / session / year
- glow.cli:          tiny main() wrapper turning JotformError into a clean exit; the API key
- glow.backup:       form snapshots before a live write, one stamp, the backup paths
- glow.translations: a form's translation store: read, save before a POST, replace languages
- glow.links:        the link elements above the Submit button
- glow.layout:       where the rosters sit relative to the links and Submit
- glow.usage:        Jotform's account limits against its usage
- glow.translation_lookup: the runtime's names dictionary, emulated
- glow.salesforce:   Salesforce REST through curl, the one client every tool uses
- glow.session_timing: a batch's submission time and delay, its session month and week, and the
                     Salesforce formula texts that compute the same
- glow.private_files: owner-only files and folders (data/ only) for names and record ids; Ledger
- glow/sf_partners.csv: each partner's Salesforce Account (id, name), read by glow.salesforce

Scripts at the repo root import it directly; scripts in tools/ do
`sys.path.insert(0, REPO)` first (the pattern they already used for siblings).
"""
