---
title: Adopt the AI-native SDLC playbook (repo polish, feedback loop, guardrails) and automate the Jotform sync
author: Claude, approved by Ryan Eskuri
status: in-progress
created: 2026-09-01
intent: docs/intent/2026-09-01-auto-sync.md
---

# Plan: AI-native SDLC adoption + automatic Jotform sync

Approved in plan mode on 2026-09-01 (launch day). The first plan committed under `docs/plans/`;
it is also the reason this folder exists.

## Context

Anthropic's "AI-native SDLC playbook" was applied to this repository: committed intent → spec →
plan artifacts as the audit trail, a one-page `CLAUDE.md`, skills and hooks as policy, a single
offline feedback loop (`make check`) as the definition of done, `REVIEW.md` for review, and a
headless loop later. Ryan also asked for the manual export → sync loop to disappear: a roster
change in the sheet should reach Jotform by itself.

Constraint: the forms and the sheet went live the same day. Everything was built repo-local and
offline-verifiable in a git worktree; the only authorized live changes were an additive
`clasp push` (inert until Script Properties are set) and, at Ryan's request, the Club-picker
pilot on the template form.

## Decisions (Ryan)

1. Scope: docs, config, tests **and** the Python de-duplication refactor (the refactor last).
2. A private GitHub repository, pushed after the polish and after the Jotform key is rotated.
3. Live-system gate: hard block unless `GLOW_LIVE_OK=1` was exported before launching Claude Code.
4. Artifacts under `docs/intent`, `docs/specs`, `docs/plans`, templates in `docs/templates`.
5. Automatic sync: event-driven (Apps Script → GitHub Actions → the existing Python sync),
   credentials as GitHub secrets, dry runs until Ryan flips `AUTO_SYNC_APPLY`, a `SyncLog` tab.
6. Per-checkout `.venv` for Python.

## Files that change

- Hygiene: `.gitignore`, `.env.example`, `credentials/README.md` + `config.example.json`,
  `requirements*.txt`, `.nvmrc`, `package.json` (engines, scripts), `appsscript/.claspignore`,
  `.editorconfig`, `ruff.toml`; `.claude/settings.local.json` sanitized and ignored by the repo.
- Feedback loop: `Makefile`, `scripts/check_{py,gs,secrets,docs_links}.*`, `test/load_gs.js`,
  `test/fixtures/make_fixture.py` (+ generated fixture and `expected.json`),
  `test/helpers/py_clubs.py`, `test/parity_test.js`, `test/forms_logic_test.js`,
  `test/dispatch_test.js`, `test/python_test.py`, `tools/build_roster_offline.js`.
- Automatic sync: `tools/auto_sync.py`, `sync_attendance_form.py` (`--summary-json`, warnings
  collector), `appsscript/Dispatch.gs` + call sites in `FormHandlers.gs` / `Roster.gs`, `Config.gs`
  (`TAB.SYNC_LOG`, `PROP.SYNC_DISPATCH_*`), `Menu.gs`, `.github/workflows/{check,auto-sync}.yml`.
- Guardrails: `.claude/settings.json`, `.claude/hooks/{live_gate,protected_paths,secret_scan}.sh`,
  `.claude/skills/*`, `.claude/agents/*`.
- Docs: `CLAUDE.md`, `REVIEW.md`, `docs/{README,RUNBOOK,ARCHITECTURE,DECISIONS}.md`,
  `docs/SHEETS-ACCESS.md` (moved), `docs/archive/2026-08-24-original-plan.md` (moved),
  `docs/LAUNCH.md`, `docs/BACKLOG.md`, `README.md`, `appsscript/INSTALL.md`, templates, intents.
- Refactor (last): `glow/` package (`jotform.py`, `forms.py`, `text.py`, `sync.py`, `cli.py`)
  and the per-script migration — its own intent/spec/plan.

## Order of work

1. Sanitize `.claude/settings.local.json`; worktree `sdlc-adoption`; hygiene files.
2. Feedback loop green on a fresh clone (fixture) and with the real export.
3. Automatic sync through the loop (intent → spec → plan, tests first, then code, workflows).
4. `.claude/` guardrails, stdin-tested.
5. Docs and SDLC artifacts; this plan committed.
6. `git tag pre-refactor`; the `glow/` refactor with byte-equal tests and a GET-only
   before/after capture; may slip to the next day.
7. Multi-agent review against `REVIEW.md`; fast-forward merge into `main` when no tool is
   running; Ryan's setup steps (key rotation, `gh`, secrets, PAT, `clasp push`, Set up tabs,
   Request Jotform sync now, `AUTO_SYNC_APPLY`).

## Risks

- The live `clasp push`: a syntax error breaks every form handler → `make gs` parses all `.gs`;
  the notification is inert until properties are set and wrapped so it cannot fail a
  submission; rollback is a push of the previous commit.
- Re-authorization: `UrlFetchApp` adds an OAuth scope, and until the trigger owner re-authorizes,
  the form-submit trigger fails hard (submissions unprocessed — the notification's try/catch never
  runs). Mitigation (review finding, 2026-09-01): push at a quiet moment; authorize via a GLOW menu
  item immediately; then "Process any missed form responses". The runbook's setup step now says so.
- An unattended writer: bands (≤ 5 creates, ≤ 20 updates, no deletes, no truncated export),
  backup before apply, verify after, `AUTO_SYNC_APPLY` as the kill switch, a dry-run day first.
- Secrets in GitHub: private repo, rotated key only, redacted logs, no roster artifacts.
- The live gate blocking legitimate work: documented override; Ryan can run commands himself.
- The refactor breaking a launch-day tool: isolated in the worktree; pure moves; real-data pins;
  `pre-refactor` tag.

## Proof

```bash
make check                                    # CHECK PASSED (with CSV=<main tree>/data/enrollment_2026-08-24.csv: real data 328/6210)
git check-ignore -v .claude/settings.local.json          # matched by ./.gitignore
git ls-files | grep -E '^(data|backups|credentials)/'     # only README.md and config.example.json
bash <scratchpad>/hook_test.sh                            # every live command exit=2, every read exit=0
grep -c ALLOWED .claude/live_gate.log                     # no unattended live write happened
```

Status log: 2026-09-01 — steps 1–5 done (`916bd1a`); Club picker piloted on the template at
Ryan's request and switched to the searchable mode he verified (`541bbcf`, `0aa1a72`;
`docs/intent/2026-09-01-club-picker.md`); the GET-only capture tool landed (`9ed51f2`).
2026-09-02 — the five-pass adversarial review ran (30 agents); its confirmed findings were fixed
(unverified applies raise ATTENTION, duplicate-name stale check, conditions-only artifacts, live
log redaction, per-match secret allowlists, raw-API and guardrail-file gate patterns, `--synclog`
opt-in, extended constants parity, regex robustness, doc corrections). Step 6 (the `glow/`
refactor) and the merge are pending; no live change beyond the template pilot.
