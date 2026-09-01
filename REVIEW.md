# REVIEW.md — reviewing a change in this repository

Input: the diff, the `docs/plans/*.md` (or `docs/intent/*.md`) it claims to implement, and the
pasted `make check` output. Do not report anything `make check` already enforces: syntax, the
`--help` smoke, secret/PII/id patterns, absolute paths, fixture freshness, JS parity, Python
unit tests, `.gs` parsing.

## Passes, in order

1. **Bugs** — logic and edge cases in `parse_roster` / `read_sheet` / `read_roster_csv`, qid and
   order arithmetic, the JSON-encoded `terms`/`action` strings, curl argument quoting,
   last-submission-wins identity, case-insensitive matching, the runner's plan parsing and bands.
2. **Live-system safety** — every code path that can POST/PUT/DELETE to Jotform, write the sheet,
   push Apps Script, or run unattended must: be dry-run by default, be `--apply`-gated, back up
   first, verify after (re-read and compare), never `--prune` a form with submissions, and stay
   inside `auto_sync.py`'s bands. Anything a form handler in `appsscript/` calls must be wrapped so
   it cannot fail the submission (`trySyncChoices_` / `tryNotifySync_` pattern).
3. **Privacy and secrets** — nothing in code, docs, tests, fixtures, logs, workflow artifacts or the
   commit message contains a real girl's name or id, a mentor's e-mail, the API key, the sheet or
   script id, a service-account field, or an owner-only edit URL. Fixture names are fictional and
   generated. Logs from unattended runs are redacted.
4. **Python ↔ Apps Script parity** — a change to `parse_roster` / `key` / `name_key`, qids,
   `SESSION_OVERRIDES`, form ids, `ROSTER_COLS`, `RESPONSE_COLS` or `SYNC_LOG_COLS` is mirrored in
   `appsscript/Config.gs` / `Normalize.gs` / `Roster.gs`, and the parity tests changed with it.
5. **Compliance with the plan** — the files touched match "Files that change"; the Proof commands
   were run and their output pasted; anything outside the plan is named and justified; new
   decisions are in `docs/DECISIONS.md`.

## Severity

- **Important** (must fix before merge): every pass-2 and pass-3 finding, correctness bugs, parity
  breaks, a missing or failing Proof.
- **Nit**: style, naming, wording. Report at most five; summarise the rest as a count.

## Skip

`appsscript/Regions.gs` (generated), `package-lock.json`, `test/fixtures/enrollment_sample.csv`
and `expected.json` (generated — review `make_fixture.py` instead), anything `make check` enforces.

## Output

`path:line — finding — why it matters — suggested fix`, grouped by pass, Important first.
End with: `Verified: make check output pasted? yes/no` and `Live systems touched? none / list`.
