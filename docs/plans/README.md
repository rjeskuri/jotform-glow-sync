# Plans and intents

Generated from each file's frontmatter by `make docs-index` (`scripts/docs_index.py`);
`make check` fails when this file is stale, so it is never edited by hand. New work is a ticket
on the board (DECISIONS 2026-10-14); a plan here is kept beside a ticket whose change has a live
rollout (Rollout, Rollback, Result). An intent is optional, to capture Ryan's ask before a
ticket exists ([templates](../templates/)). A status is one of
`proposed`, `accepted`, `in-progress`, `blocked`, `done`, `superseded`,
with an optional comment after a `#`; a done one carries `done: YYYY-MM-DD`, and `backlog:`
names the BACKLOG items a plan is about. Newest first.

## Plans

| Date | Plan | Status | BACKLOG | File |
|---|---|---|---|---|
| 2026-10-25 | The optional session-notes field and its translations on all five attendance forms | done 2026-10-26 |  | [2026-10-25-session-notes.md](2026-10-25-session-notes.md) |
| 2026-10-22 | Roster changes sent as problem reports point their sender to the Club Roster Form, and girls "not on the form" count as one | proposed |  | [2026-10-22-roster-change-reports-to-roster-form.md](2026-10-22-roster-change-reports-to-roster-form.md) |
| 2026-10-21 | Inventory of the Monthly Report (DHIS2) reports, dashboards and interactive dashboard; the two hidden Decommissioned folders; the copy-and-move API proof | done 2026-10-23 |  | [2026-10-21-sf-reporting-inventory.md](2026-10-21-sf-reporting-inventory.md) |
| 2026-10-21 | Duplicate and obsolete flags on Account and Contact, and Account duplicate rules that report only | in-progress |  | [2026-10-21-sf-duplicate-obsolete-flags.md](2026-10-21-sf-duplicate-obsolete-flags.md) |
| 2026-10-21 | A standalone Apps Script moves Jotform's photo subfolders from Ryan's My Drive to the company Shared Drive | accepted |  | [2026-10-21-drive-photo-mover.md](2026-10-21-drive-photo-mover.md) |
| 2026-10-20 | The dashboard's top row becomes two girls-who-attended tiles (Jotform + 3 partners); total attendance no longer tracked | done 2026-10-21 | 72 | [2026-10-20-girls-attended-tiles.md](2026-10-20-girls-attended-tiles.md) |
| 2026-10-19 | The three Salesforce-reporting partners' Monthly Max copied into attendance, one Partner report batch per partner per month | done 2026-10-20 | 72 | [2026-10-19-partner-monthly-max.md](2026-10-19-partner-monthly-max.md) |
| 2026-10-15 | The dashboard's total attendance counts Jotform plus the three Salesforce-reporting partners only, shown beside Jotform only | done 2026-10-15 | 72 | [2026-10-15-attendance-total-three-partners.md](2026-10-15-attendance-total-three-partners.md) |
| 2026-10-14 | Special event "IDG Celebrations" on every attendance form, after "Welcome Session" | done 2026-10-14 |  | [2026-10-14-idg-celebrations.md](2026-10-14-idg-celebrations.md) |
| 2026-10-13 | Special events - ad-hoc sessions as module options, the first "Welcome Session" | done 2026-10-13 |  | [2026-10-13-special-events.md](2026-10-13-special-events.md) |
| 2026-10-12 | The Group Photo sublabel loses its sentence about faces; one photo per submission stays | done |  | [2026-10-12-photo-sublabel.md](2026-10-12-photo-sublabel.md) |
| 2026-10-09 | Repo cleanup: organize, consolidate, lint (no rewrite) | in-progress | 32, 50, 53 | [2026-10-09-repo-cleanup.md](2026-10-09-repo-cleanup.md) |
| 2026-10-09 | Attendance reports and dashboard visible to every internal user - the two folders shared, one permission set, "(test)" dropped | in-progress | 60 | [2026-10-09-attendance-reports-public.md](2026-10-09-attendance-reports-public.md) |
| 2026-10-07 | One Salesforce contact per girl - merge the duplicates the altered names made, then release Queens of Quest | done 2026-10-07 | 61, 76, 77, 78 | [2026-10-07-sf-duplicate-girls.md](2026-10-07-sf-duplicate-girls.md) |
| 2026-10-07 | Attendance processor - a name with extra spaces or invisible characters finds its girl | done 2026-10-07 | 75 | [2026-10-07-processor-name-spacing.md](2026-10-07-processor-name-spacing.md) |
| 2026-10-06 | Salesforce club accounts created automatically for new clubs (BACKLOG 27) | in-progress | 27 | [2026-10-06-sf-new-club-accounts.md](2026-10-06-sf-new-club-accounts.md) |
| 2026-10-06 | The group photo never reaches Salesforce; it is kept where staff can find it, under GLOW's control | in-progress | 68, 69, 70 | [2026-10-06-photos-to-drive.md](2026-10-06-photos-to-drive.md) |
| 2026-10-06 | The module a submission sends is one required dropdown and exact text | done 2026-10-07 | 66, 67 | [2026-10-06-module-selection.md](2026-10-06-module-selection.md) |
| 2026-10-06 | Clubs that do not report through Jotform leave the forms - a Partners-tab marker for the three partners, deactivation of the U.S clubs, the U.S form disabled | in-progress | 71, 74 | [2026-10-06-clubs-off-jotform.md](2026-10-06-clubs-off-jotform.md) |
| 2026-10-06 | One attendance total for leadership that includes the partners who report counts, with the per-girl figures labelled Jotform only, and the clubs that did not submit or sent a blank in plain view | done 2026-10-07 | 72, 73 | [2026-10-06-attendance-totals.md](2026-10-06-attendance-totals.md) |
| 2026-10-02 | The names and the module the forms send are the exact roster and dropdown text | done 2026-10-06 | 62, 63, 64 | [2026-10-02-names-and-modules.md](2026-10-02-names-and-modules.md) |
| 2026-10-02 | Attendance processor - a submission's new girls created in one insert | done 2026-10-02 |  | [2026-10-02-attendance-processor-one-insert.md](2026-10-02-attendance-processor-one-insert.md) |
| 2026-10-02 | Attendance dashboard in Salesforce - charts from the data already there | done 2026-10-02 | 58, 59, 60, 61 | [2026-10-02-attendance-dashboard.md](2026-10-02-attendance-dashboard.md) |
| 2026-09-30 | Rosters above Submit and the club guard, merged together (wf5 integration) | done 2026-09-30 | 47, 48 | [2026-09-30-wf5-integration.md](2026-09-30-wf5-integration.md) |
| 2026-09-30 | Time zones fixed - the work log (billing) and the sheet-facing timestamps | done 2026-09-30 |  | [2026-09-30-time-zones.md](2026-09-30-time-zones.md) |
| 2026-09-30 | September back-fill - the Jotform attendance that never reached Salesforce | done 2026-10-02 |  | [2026-09-30-september-backfill.md](2026-09-30-september-backfill.md) |
| 2026-09-30 | The intake checker for club names two partners share (Part 2 of the same-name plan) | done 2026-09-30 | 49 | [2026-09-30-same-name-intake.md](2026-09-30-same-name-intake.md) |
| 2026-09-30 | Clubs that share a name send "&lt;club&gt; - &lt;partner&gt;" to Salesforce | done 2026-09-30 | 49 | [2026-09-30-same-name-clubs.md](2026-09-30-same-name-clubs.md) |
| 2026-09-30 | Jotform to Salesforce reconnected - the integration restored on the forms | done 2026-09-30 |  | [2026-09-30-salesforce-reconnect.md](2026-09-30-salesforce-reconnect.md) |
| 2026-09-30 | Club accounts in Salesforce, linked to their partners | in-progress | 27 | [2026-09-30-salesforce-clubs.md](2026-09-30-salesforce-clubs.md) |
| 2026-09-30 | Monthly Report in Salesforce - the "attendance submitted electronically" checkbox | done 2026-09-30 | 55 | [2026-09-30-monthly-report-checkbox.md](2026-09-30-monthly-report-checkbox.md) |
| 2026-09-30 | The names list sent to Salesforce is never empty and never another club's | done 2026-10-02 | 35, 56, 57 | [2026-09-30-contact-ids.md](2026-09-30-contact-ids.md) |
| 2026-09-30 | The Jotform client sends a JSON body on standard input | done 2026-09-30 |  | [2026-09-30-body-on-stdin.md](2026-09-30-body-on-stdin.md) |
| 2026-09-30 | September back-fill - the resolver (every attendance submission as clean rows) | done 2026-10-02 |  | [2026-09-30-backfill-resolver.md](2026-09-30-backfill-resolver.md) |
| 2026-09-29 | Every roster renders above the links and the Submit button | done 2026-09-30 | 47 | [2026-09-29-rosters-above-submit.md](2026-09-29-rosters-above-submit.md) |
| 2026-09-29 | One club per attendance submission (the multi-club guard) | done 2026-09-30 | 48 | [2026-09-29-club-guard.md](2026-09-29-club-guard.md) |
| 2026-09-28 | A work log for invoicing (hours per day + what was done) | done 2026-09-28 |  | [2026-09-28-worklog.md](2026-09-28-worklog.md) |
| 2026-09-28 | The attendance forms point mentors to the Club Roster Form when a girl is missing or has left | blocked | 46 | [2026-09-28-roster-form-link.md](2026-09-28-roster-form-link.md) |
| 2026-09-28 | Replay guard — an older form response never puts back girls removed after it was sent | done 2026-09-30 | 41 | [2026-09-28-replay-guard.md](2026-09-28-replay-guard.md) |
| 2026-09-28 | Problem reports that are roster changes reach the ReviewQueue, and Ryan works it weekly | done 2026-09-28 |  | [2026-09-28-problem-report-followup.md](2026-09-28-problem-report-followup.md) |
| 2026-09-28 | Mentors choose their partner from a list when two partners share a club name | superseded | 45, 50 | [2026-09-28-partner-box.md](2026-09-28-partner-box.md) |
| 2026-09-28 | The Google Forms send roster changes to the Club Roster Form, and the problem form asks for a reply address again | blocked | 43 | [2026-09-28-forms-wording.md](2026-09-28-forms-wording.md) |
| 2026-09-28 | Catch "new club" submissions that duplicate a club we already have | done 2026-09-30 | 11b, 44 | [2026-09-28-duplicate-club-guard.md](2026-09-28-duplicate-club-guard.md) |
| 2026-09-27 | Time-zone-proof form-response keys and a safe "Process any missed form responses" | done 2026-09-28 | 41, 42 | [2026-09-27-formlog-key.md](2026-09-27-formlog-key.md) |
| 2026-09-24 | Move a club to its real partner (a mistyped partner), first use 2026-09-24 | done 2026-09-28 | 39 | [2026-09-24-move-club-partner.md](2026-09-24-move-club-partner.md) |
| 2026-09-24 | The Global Catalyst logo replaces the Global Girls GLOW header banner | blocked |  | [2026-09-24-header-logo.md](2026-09-24-header-logo.md) |
| 2026-09-20 | Hindi and Persian on the Asia form; a switcher flag for Odia on every form | done 2026-09-20 | 6b | [2026-09-20-asia-languages-flags.md](2026-09-20-asia-languages-flags.md) |
| 2026-09-14 | Rename a club in place (sheet + forms), first use 2026-09-14 | done 2026-09-14 |  | [2026-09-14-rename-club.md](2026-09-14-rename-club.md) |
| 2026-09-12 | Club picker on every attendance form, with the training guide's wording | done 2026-09-12 | 1c | [2026-09-12-picker-rollout.md](2026-09-12-picker-rollout.md) |
| 2026-09-02 | New partners choose their region on the Club Roster Form | in-progress | 38 | [2026-09-02-region-picker.md](2026-09-02-region-picker.md) |
| 2026-09-01 | A roster change in the sheet reaches the Jotform attendance forms by itself | done 2026-09-12 | 1b | [2026-09-01-auto-sync.md](2026-09-01-auto-sync.md) |
| 2026-09-01 | Adopt the AI-native SDLC playbook (repo polish, feedback loop, guardrails) and automate the Jotform sync | done 2026-09-12 | 1b, 11a | [2026-09-01-ai-native-sdlc-adoption.md](2026-09-01-ai-native-sdlc-adoption.md) |

## Intents

| Date | Intent | Status | Plans | File |
|---|---|---|---|---|
| 2026-10-06 | The group photo never reaches Salesforce; it is kept where staff can find it, under GLOW's control | in-progress | [2026-10-06-photos-to-drive](2026-10-06-photos-to-drive.md) | [2026-10-06-photos-to-drive.md](../intent/2026-10-06-photos-to-drive.md) |
| 2026-10-06 | Clubs that do not report through Jotform leave the attendance forms, without leaving the roster | in-progress | [2026-10-06-clubs-off-jotform](2026-10-06-clubs-off-jotform.md) | [2026-10-06-clubs-off-jotform.md](../intent/2026-10-06-clubs-off-jotform.md) |
| 2026-10-06 | One attendance total for leadership that includes the partners who report counts, with the per-girl figures labelled Jotform only, and the clubs that did not submit or sent a blank in plain view | in-progress | [2026-10-06-attendance-totals](2026-10-06-attendance-totals.md) | [2026-10-06-attendance-totals.md](../intent/2026-10-06-attendance-totals.md) |
| 2026-09-02 | New partners choose their region on the Club Roster Form | in-progress | [2026-09-02-region-picker](2026-09-02-region-picker.md) | [2026-09-02-region-picker.md](../intent/2026-09-02-region-picker.md) |
| 2026-09-01 | One Jotform client, one form table, one set of text helpers | done 2026-09-02 | [2026-09-30-body-on-stdin](2026-09-30-body-on-stdin.md) | [2026-09-01-shared-jotform-client.md](../intent/2026-09-01-shared-jotform-client.md) |
| 2026-09-01 | Python and Apps Script read the enrollment responses identically | proposed |  | [2026-09-01-parity-partnerless-rows.md](../intent/2026-09-01-parity-partnerless-rows.md) |
| 2026-09-01 | Catch "new club" submissions that duplicate a club we already have | in-progress | [2026-09-28-duplicate-club-guard](2026-09-28-duplicate-club-guard.md) | [2026-09-01-duplicate-club-guards.md](../intent/2026-09-01-duplicate-club-guards.md) |
| 2026-09-01 | Switch off the five pre-launch attendance forms | done 2026-09-30 |  | [2026-09-01-disable-defunct-forms.md](../intent/2026-09-01-disable-defunct-forms.md) |
| 2026-09-01 | Mentors pick their club from a list instead of typing its name | done 2026-09-30 | [2026-09-12-picker-rollout](2026-09-12-picker-rollout.md), [2026-09-29-club-guard](2026-09-29-club-guard.md), [2026-09-30-contact-ids](2026-09-30-contact-ids.md), [2026-09-30-same-name-clubs](2026-09-30-same-name-clubs.md), [2026-09-30-same-name-intake](2026-09-30-same-name-intake.md), [2026-10-02-names-and-modules](2026-10-02-names-and-modules.md), [2026-10-06-module-selection](2026-10-06-module-selection.md) | [2026-09-01-club-picker.md](../intent/2026-09-01-club-picker.md) |
| 2026-09-01 | The loop closes by itself — CI, a daily drift check that writes intents, evals for the agent setup | proposed |  | [2026-09-01-ci-and-evals.md](../intent/2026-09-01-ci-and-evals.md) |
| 2026-09-01 | A roster change in the sheet reaches the Jotform attendance forms by itself | done 2026-09-12 | [2026-09-01-ai-native-sdlc-adoption](2026-09-01-ai-native-sdlc-adoption.md), [2026-09-01-auto-sync](2026-09-01-auto-sync.md) | [2026-09-01-auto-sync.md](../intent/2026-09-01-auto-sync.md) |
