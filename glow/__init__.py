"""Shared library for the GLOW tooling (docs/intent/2026-09-01-shared-jotform-client.md).

- glow.jotform: the one curl-based Jotform client, dry-run gated
- glow.forms:   the one table of form ids (parity-tested against appsscript/Config.gs)
- glow.text:    normalization helpers shared by every tool
- glow.sync:    the enrollment/Roster parsers and the structural question ids
- glow.cli:     tiny main() wrapper turning JotformError into a clean exit

Scripts at the repo root import it directly; scripts in tools/ do
`sys.path.insert(0, REPO)` first (the pattern they already used for siblings).
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
