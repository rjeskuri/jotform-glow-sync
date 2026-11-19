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

## Rollout (live)
<!-- The merge is the rollout for a form change the sync generates: once it lands, the runner
     applies it to every enabled regional form on its next run (DECISIONS 2026-10-14). List the
     hand steps only: the template, from the ticket branch before the land, when the change needs
     browser checks (the runner never syncs it); a disabled form (`--disabled-ok`); writers other
     than the sync (translations, builder edits); and the read-back after the runner's run (each
     region's SyncLog row `applied`, `form_status.py` CLEAN per form). No step sets
     `AUTO_SYNC_APPLY`.
     A step whose backup from today is on record runs automatically through the live gate, logged
     and notified (RUNBOOK "Live gate (Claude Code)", DECISIONS 2026-10-26). A step that deletes,
     and `--prune`, still asks Ryan in the session; so does a step whose backup is missing, or
     whose tool the gate does not list: mark those steps "on Ryan's go". -->
1. <live step: the backup first (`backup_forms.py --form <id>`, `sheets_client.py export`, a
   committed `appsscript/`, the plan's `before/` retrieve), the command, and the read-back that
   proves it>
2. …

## Rollback
<how each live step is undone, with the backup or command it uses; for a generated form change,
the revert or constants-off commit, merged: the runner rolls every enabled regional form back on
its next run. `AUTO_SYNC_APPLY=0` only as the emergency switch, set back to `1` before the
rollback ends>

## Risks
<what could break, and the mitigation for each; live-system steps named explicitly>

## Proof
<exact commands and the healthy lines expected; `make check` output pasted when done>

## Result
<what ran and when (UTC), with Ryan's go, and how it was verified; filled in when done>
