---
name: deploy-appsscript
description: Push appsscript/ to the live Apps Script bound to the master sheet - what changed since the last deploy, no new Google service, a quiet moment, re-authorization, missed form responses, a deploy tag, and the rollback floors.
disable-model-invocation: true
---

# Deploy the Apps Script (`/deploy-appsscript`)

The script runs the sheet's form-submit trigger (Club Roster Form, problem reports), the Monday
e-mail and the GLOW menu: a bad push stops them. Detail lives in RUNBOOK "Apps Script deploy",
"Rolling back `appsscript/`" and "Missed form responses"; setup in `appsscript/INSTALL.md`.

## Checklist
1. **Green offline**: `make check` ends `CHECK PASSED`; its `gs:` line reads `8 services, 0 unknown
   calls`.
2. **What changes.** The base is the last deployed commit: `git tag -l 'appsscript-deployed-*'`
   (newest by date). If there is no tag, say so to Ryan: the deployed commit is unknown, so diff
   from the newest rollback floor, `986a325`, and say the diff may hold changes already live.
   Then `git log --oneline <base>..HEAD -- appsscript` and `git diff --stat <base> -- appsscript`,
   and summarise per file what a mentor, staff or the triggers will see differently.
3. **No new Google service, no renamed handler.**
   - `make gs` fails on a service beyond the pinned 8 (CLAUDE.md rule 11). A plan that adds one
     means the trigger fails hard from the push until Ryan authorizes (step 7): say so first.
   - The live project calls these by name: `onOpen`, the installed triggers `onAnyFormSubmit` and
     `sendSfPendingDigest`, and every `addItem` function in `Menu.gs`. Check
     `git diff <base> -- appsscript | grep -E '^-function '`: a removed or renamed trigger handler
     needs GLOW → Google Forms → Install triggers right after the push.
4. **The checkout is the code.** clasp pushes the files on disk, not a commit:
   `git status --short -- appsscript` must print nothing; note `git rev-parse --short HEAD`.
5. **A quiet moment.** Ask Ryan: no other rollout running (a sync apply, a Salesforce deploy), no
   Club Roster Form response or problem report expected in the next minutes.
6. **Push.** In Ryan's shell: `nvm use 18` (the script refuses any other Node; clasp 2.4.2), then
   `npm run clasp:push`. Ryan runs it, or Claude does: the hook puts the push to Ryan as an
   approval prompt, and his yes is the go (a session that cannot prompt is refused).
7. **Authorize.** Ryan opens the sheet and runs a GLOW menu item (Show roster summary); if Google
   asks for authorization, he accepts at once.
8. **Missed responses.** GLOW → Google Forms → Process any missed form responses, and read the
   preview: only responses that arrived since the push, plus earlier rows marked `retry after
   ERROR`. Anything else (held rows, responses older than 7 days): stop and follow RUNBOOK
   "Missed form responses".
9. **Tag** (ask Ryan first; `git tag` asks anyway): `git tag appsscript-deployed-YYYY-MM-DD
   <commit from step 4>`, `-2` for a second push the same day. It stays local until Ryan pushes it.
10. **Report**: the commit pushed, what changed, whether authorization was needed, the preview's
    counts, the tag.

## Rollback
- `git checkout <previous appsscript-deployed-* tag> -- appsscript && npm run clasp:push` (Node 18,
  a quiet moment, steps 7-8 again), then `git checkout HEAD -- appsscript` to put the checkout
  back. Without a tag, the target is the commit Ryan knows was live (RUNBOOK "Apps Script
  deploy"), never "the previous commit".
- Never below the floors: `7a175c4`, and `986a325` once the Feedback tab has two reply columns.
- Held new clubs first: a target without the duplicate-club guard (`git grep -q HOLD_PREFIX
  <target> -- appsscript/FormHandlers.gs` finds nothing) reads a held response as done (RUNBOOK
  "Rolling back `appsscript/`").
