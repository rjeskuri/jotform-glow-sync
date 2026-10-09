---
title: The Global Catalyst logo replaces the Global Girls GLOW header banner
author: Claude (executed with Ryan)
status: blocked          # on Ryan: the logo's upload in the builder (Result: live steps pending Ryan)
created: 2026-09-24
intent: none — requested by Ryan on 2026-09-24
---

# Plan: swap the header logo on every attendance form

Ryan added `Global-Catalyst_Primary-Wordmark-with-Tagline_Full-Color copy.png`
to the repo and asked for it to replace the Global Girls GLOW image on all the
forms, at a similar size.

The logo is the `image` field (q13, unique name `image`) and is identical on
all ten snapshotted forms: `src` a Jotform-hosted PNG, `width` 406,
`height` 103, `align` Center, `alt` empty. Nothing keys on it — q13 is in
`add_translations.py`'s `NEVER_SHOWN`, it is absent from `Config.gs QID`, and
the sync never touches it — so this is a self-contained change.

## Sizing

| | canvas | ink inside it | aspect |
|---|---|---|---|
| old banner (live) | 406×103 | 142×52, 65% whitespace | 3.94 : 1 |
| new logo (supplied) | 2371×1194 | 2282×1140, tightly cropped | 1.99 : 1 |

The two shapes are different, so "similar sizing" cannot mean both dimensions.
**205×103** — the replaced banner's exact height, the width from the new
logo's own proportions. The header band therefore does not move and nothing is
squashed. The alternatives were rejected: keeping the width (406×204) doubles
the header; matching the old *mark* (≈103×52) makes the tagline "IGNITING
GIRL-LED CHANGE." illegible. The logo's mark does end up visually larger than
the old one, because the old file was mostly padding — unavoidable without
padding the new file to the old 3.94:1 box.

## Files that change
- `assets/global-catalyst-wordmark-full.png` — the supplied original, moved out
  of the repo root and renamed (it had a space and "copy" in the name).
- `assets/global-catalyst-header.png` — 410×206, i.e. 2× the display box, so
  phones render it sharp. Derived from the original with PIL/LANCZOS
  (`Image.open(...).resize((410, 206), LANCZOS).save(..., optimize=True)`,
  49 KB); one-off, so no PIL dependency enters the repo.
- `tools/update_static_fields.py` — extended rather than a new tool: it already
  sets properties on static fields by unique name across the live forms, dry
  run by default, re-reading and comparing after each write. Adds
  `IMAGE_PROPS` (the display size, align, alt), `wanted_fields()` (the image
  field appears only when `--image-src` is given, so a re-run for the *other*
  fields can never resize the old banner), `check_src()` (refuses a URL that
  is not https, not reachable, not an image, or smaller than the display box)
  and `png_size()`.
- `test/python_test.py` — `HeaderImage`, including a guard that the committed
  asset stays exactly 2× the display size.
- `docs/RUNBOOK.md` "Header logo", `docs/ARCHITECTURE.md` tool table,
  `docs/DECISIONS.md`, `.claude/skills/jotform-api/SKILL.md` (no asset-upload
  endpoint exists).

## Order of work
1. Assets, tool, tests, docs; `make check`; commit. **Done.**
2. Ryan uploads `assets/global-catalyst-header.png` through the builder on any
   one form and copies the URL it is given. **Jotform's API cannot upload an
   asset** — `src` only points at an already-hosted file (verified against the
   API docs and Jotform's own support answers; `/form/{id}/files` is about
   submission uploads). A data URI would avoid the upload but is untested here
   and Jotform is known to rewrite `http:` inside injected CSS, so it is not
   the path chosen.
3. `python3 backup_forms.py` (snapshots all ten forms).
4. `python3 tools/update_static_fields.py --image-src <URL>` — dry run; expect
   `image (q13)` on five forms showing `src`, `width` 406→205, `height` 103,
   `align` already Center, `alt` ''→'Global Catalyst', `text` → the new
   basename. The two 2026-09-12 fields should report "already as the guide
   wants it".
5. The same with the write flag; every field is re-read and compared.
6. Verify: `tools/form_status.py --form <id> --roster <csv>` CLEAN on each
   regional, and load one public form to see the logo.

## Blocked on Ryan
This session has **no `JOTFORM_API_KEY` and no `GLOW_LIVE_OK=1`** (both were
present earlier today; the environment changed when the CLI was restarted), so
steps 3–6 cannot run here — the live gate blocks the write, as designed. Ryan
either re-launches Claude Code with both exported, or runs the three commands
himself.

## Risks
- The image is one property write per form; the old `src`, `width` and
  `height` are in the snapshot from step 3, so rollback is the same command
  with the old values (or Jotform's Revision History).
- Pointing `src` at a URL that later disappears breaks the header on all five
  forms; `check_src` verifies it is a reachable image before any write, and the
  file lives in the same Jotform account as the form.
- The defunct pre-launch forms keep the old banner. They are archives and
  `glow_forms.LIVE` (what the tool iterates) excludes them.
- The template is included, so future clones inherit the new logo.

## Proof
`make check` tail pasted below when done, plus the dry-run and write output of
step 4–5 and one public-page check.

## Result
`make check` → CHECK PASSED (38 → 45 Python tests). Live steps pending Ryan.
