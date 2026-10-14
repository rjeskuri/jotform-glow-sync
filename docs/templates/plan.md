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

<!-- Kept beside the ticket when its change has a live rollout (CLAUDE.md, Conventions); new work
     is a ticket. When it is done: a Result (what ran, with Ryan's go, and how it was verified), the
     status and `done:`, then `make docs-index`. -->

## Rollout (live; each step on Ryan's go)
1. <live step: the backup first, the command, and the read-back that proves it>
2. …

## Rollback
<how each live step is undone, with the backup or command it uses>

## Risks
<what could break, and the mitigation for each; live-system steps named explicitly>

## Proof
<exact commands and the healthy lines expected; `make check` output pasted when done>

## Result
<what ran and when (UTC), with Ryan's go, and how it was verified; filled in when done>
