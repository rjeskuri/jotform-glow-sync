---
title: The Jotform client sends a JSON body on standard input
author: Claude (found by an adversarial review of the Contact_IDs design, 2026-09-30)
status: done             # a7eb3a8 on main, 2026-09-30
done: 2026-09-30
created: 2026-09-30
intent: none — docs/intent/2026-09-01-shared-jotform-client.md is the client's
---

# Plan: a request body never travels as a command-line argument

## Problem
`glow/jotform.py` passed a JSON body to curl as one argument (`--data-binary <json>`). Linux
refuses any single argument over 131,072 bytes ("Argument list too long"); macOS only limits
the total. Since the club guard (2026-09-30) a form's rules are larger: read that day, the
conditions write is about 153 KB on Africa and 244 KB on the template (Asia 75 KB, Latin America
40 KB, U.S 23 KB). Every apply since was made by hand from the Mac, or by the runner on Asia, so
nothing has failed yet — but the GitHub runner (Linux) cannot write Africa's rules: a roster
update there would end `APPLY FAILED`, and a new Africa club would get its roster and its
Club-picker entry without its rules (its mentors blocked by the guard).

## Change
- `Client.call(..., body=None)`: the body goes to curl's standard input; `post_json` and
  `put_json` pass `--data-binary @-`. The dry-run gate is unchanged (`is_write` still sees
  `--data-binary`).
- An argument over 120,000 bytes is refused before curl starts (a clear `JotformError`, the
  value never printed), and a curl that cannot be started is a `JotformError` too.
- Tests in `GlowClient`: a body over 200 KB goes on standard input with every argument under the
  limit; the refusal; the clean error.

## Proof
- `make check`: CHECK PASSED (304 tests).
- A local echo server (no Jotform call): a 233,422-byte body sent by `put_json` arrived
  byte-identical with `Content-Type: application/json`.
- After the push, the next runner apply on any region shows the path works on Linux; Africa's
  first one is the real proof (watch it; until then an Africa apply can be made by hand from the
  Mac).

## Rollback
Revert the commit: the client sends bodies as before (and the runner again cannot write
Africa's rules).
