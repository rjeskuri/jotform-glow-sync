---
name: "Task"
about: "One ticket: request, outline, definition of done, the tests that must pass"
title: ""
labels: ["task", "status:ready"]
---

## Request
<what was asked, in the requester's words, one paragraph>

## Outline
1. <step>

## Definition of done
- [ ] <observable, testable statement>

## Tests that must pass
Broad behavior first, specific cases after. One line each: where, and what it proves.
- `test/<area>_test.py: <Class>.test_<behavior>`: <the contract it pins down>
The existing suite (`make check`) stays green.

## Context
- `<path>`: <why it matters>
- Must not change: <...>
