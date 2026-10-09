"""Shared library for the GLOW tooling (docs/intent/2026-09-01-shared-jotform-client.md).

- glow.jotform:      the one curl-based Jotform client, dry-run gated; public_page()
- glow.forms:        the one table of form ids (parity-tested against appsscript/Config.gs)
- glow.text:         normalization helpers shared by every tool (key, name_key; the sheet's
                     tidy / cell_key / nfc_key)
- glow.sync:         the enrollment/Roster parsers and the structural question ids
- glow.cli:          tiny main() wrapper turning JotformError into a clean exit; the API key
- glow.backup:       form snapshots before a live write, one stamp, the backup paths
- glow.translations: a form's translation store: read, save before a POST, replace languages
- glow.links:        the link elements above the Submit button
- glow.layout:       where the rosters sit relative to the links and Submit
- glow.usage:        Jotform's account limits against its usage
- glow.translation_lookup: the runtime's names dictionary, emulated
- glow.salesforce:   Salesforce REST through curl (sf_partners.csv beside it: each partner's
                     Salesforce Account)

Scripts at the repo root import it directly; scripts in tools/ do
`sys.path.insert(0, REPO)` first (the pattern they already used for siblings).
"""
