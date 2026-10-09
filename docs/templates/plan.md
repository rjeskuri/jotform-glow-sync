---
title: <what will exist, in one line>
author: <who wrote it>
status: proposed         # proposed | accepted | in-progress | blocked | done | superseded; a comment after the #
done:                    # YYYY-MM-DD once done (delete the line until then)
backlog:                 # the BACKLOG item(s) it is about, e.g. 41, 42 (delete the line if none)
created: YYYY-MM-DD
intent: <Ryan's ask in his words, with its date> | docs/intent/YYYY-MM-DD-<slug>.md when one exists
---

# Plan: <feature name>

<!-- Required for anything beyond a one-line fix, and committed before the code. Add the plan to
     the index with `make docs-index`. When it is done: a "## Result" section (what ran, with
     Ryan's go, and how it was verified), the status, and `done:`. -->

## Files that change
<paths, one line each, with what changes in them>

## Order of work
1. <step — the repo stays green after each one>
2. …

## Risks
<what could break, and the mitigation for each; live-system steps named explicitly>

## Proof
<exact commands and the healthy lines expected; `make check` output pasted when done>
