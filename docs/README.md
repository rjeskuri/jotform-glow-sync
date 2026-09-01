# Docs

| File | What it is for |
|---|---|
| [RUNBOOK.md](RUNBOOK.md) | Every operational procedure with its dry-run and apply form; the form ids; the live gate; the automatic sync's switches |
| [ARCHITECTURE.md](ARCHITECTURE.md) | The flow sheet → Roster → Jotform → Salesforce with file:function pointers; constants that exist on both sides; parity bridges; known divergences; privacy boundaries |
| [DECISIONS.md](DECISIONS.md) | One line per decision that shaped the system, with the why |
| [LAUNCH.md](LAUNCH.md) | The 2026-09-01 launch: links handed to mentors, readiness checklist, post-launch steps |
| [BACKLOG.md](BACKLOG.md) | What remains, in order |
| [SHEETS-ACCESS.md](SHEETS-ACCESS.md) | Giving the tooling (and CI) service-account access to the master enrollment sheet |
| [intent/](intent/) · [specs/](specs/) · [plans/](plans/) | The audit trail of changes: what was wanted → what will exist → how it was built. One file per change, `YYYY-MM-DD-slug.md`, same slug across the three. Templates in [templates/](templates/) |
| [archive/](archive/) | Historical documents kept for the reasoning (the original 2026-08-24 plan) |

How work flows (the AI-native SDLC playbook, adapted): an idea is captured as an **intent**
(problem, outcome, constraints), turned into a **spec** with the policy skills loaded
(`.claude/skills/`), planned in plan mode and committed as a **plan** before any code, built
with `make check` as the definition of done, reviewed against [../REVIEW.md](../REVIEW.md), and
anything the automation finds comes back in as a new intent. `CLAUDE.md` at the root is the
one-page institutional memory for Claude.
