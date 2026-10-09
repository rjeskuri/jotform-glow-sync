#!/usr/bin/env python3
"""
Give the form language switcher a flag for languages Jotform ships none for.

Jotform's "flag-with-nation" switcher renders one nation flag per language
from its own table (Telugu -> India, Urdu -> Pakistan, ...). A language it
has no flag for - Oriya - gets an empty flag slot, in the list and in the
trigger. Two facts make a CSS fix possible: the public page applies the
form's injectCSS property, and the runtime stamps html[lang="<code>"] on
every switch and copies the chosen row's flag into the trigger. So one rule
per language paints the row's slot and, once selected, the trigger's slot
(id-based selectors: the injected CSS precedes the switcher stylesheet).

FLAGS maps a language code to an SVG under tools/switcher_flags/ (or.svg is
Jotform's own India flag, copied from the Telugu row - Odia has no flag of
its own and India is what Jotform's convention gives an Indian language).
The tool builds the block between the two marker comments, GETs each form's
injectCSS, replaces an earlier block or appends, POSTs it back and re-reads
it. Dry run by default; --apply snapshots the form first (glow/backup.py:
properties hold injectCSS). --check-page fetches the PUBLIC form page (no
API) and reports, per language, whether the switcher row carries a flag.

    python3 tools/switcher_flags.py                 # dry run, template + regionals
    python3 tools/switcher_flags.py --form <id>     # one form
    python3 tools/switcher_flags.py --apply
    python3 tools/switcher_flags.py --check-page --form <id>
"""
import argparse
import base64
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from glow import backup                   # noqa: E402  (the snapshot before a write)
from glow import forms as glow_forms      # noqa: E402
from glow.cli import api_key, run, targets                  # noqa: E402
from glow.jotform import Client, public_page   # noqa: E402

FLAGS = {"or": "or.svg"}                  # language code -> file under tools/switcher_flags/
SVG_DIR = os.path.join(REPO, "tools", "switcher_flags")
START, END = "/* GLOW switcher flags v2 */", "/* /GLOW switcher flags */"
ANY_START = "/* GLOW switcher flags v"          # an earlier version's block is replaced too


def data_uri(svg):
    """One-line base64 data: URI. Base64, not percent-encoding: Jotform
    rewrites "http:" to "//" inside injectCSS when it serves the page, which
    turned the SVG's xmlns into //www.w3.org/2000/svg and broke the image
    (found 2026-09-20). Base64 carries no URL for it to touch."""
    svg = re.sub(r"\s+", " ", svg.strip())
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def css_block(flags=FLAGS, svg_dir=SVG_DIR):
    rules = []
    for code, filename in sorted(flags.items()):
        with open(os.path.join(svg_dir, filename), encoding="utf-8") as f:
            uri = data_uri(f.read())
        # id-based selectors: the injected CSS is printed in <head>, BEFORE the
        # switcher stylesheet linked in <body>, so equal specificity would lose;
        # `display` is left alone so the stylesheet's own hiding (.lang-emp
        # before a choice, .only-nation) keeps working (verified 2026-09-20)
        rules.append(
            f'#langList li[data-lang="{code}"] .jfLangDd-flag,\n'
            f'html[lang="{code}"] #langDd .jfLangDd-current:not(.lang-emp) .jfLangDd-flag'
            f'{{background:url("{uri}") center/16px 12px no-repeat}}')
    return START + "\n" + "\n".join(rules) + "\n" + END


def merge(existing, block):
    """existing injectCSS with the marked block replaced, or appended."""
    existing = existing or ""
    i, j = existing.find(ANY_START), existing.find(END)
    if i >= 0 and j > i:
        return existing[:i] + block + existing[j + len(END):]
    return existing.rstrip("\n") + ("\n\n" if existing.strip() else "") + block + "\n"


def page_flags(form_id):
    """(has_block, {code: True/False}) from the public form page - read-only, no API key. A page
    that cannot be fetched stops the run (glow.jotform.public_page), never reads as 0 languages."""
    html = public_page(form_id)
    flags = {}
    for lang, inner in re.findall(r'<li data-lang="([^"]+)"[^>]*>(.*?)</li>', html, re.S):
        flags[lang] = "<svg" in inner
    return START in html, flags


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--form", action="append", metavar="ID",
                    help="form id (repeatable; default: the template and the four live forms)")
    ap.add_argument("--apply", action="store_true", help="write (dry run without it)")
    ap.add_argument("--check-page", action="store_true",
                    help="read the PUBLIC page of each form and report the switcher's flags")
    args = ap.parse_args()
    form_ids = list(targets(args.form))

    if args.check_page:
        for fid in form_ids:
            has_block, flags = page_flags(fid)
            missing = [c for c, ok in flags.items() if not ok]
            print(f"== {glow_forms.LABELS.get(fid, fid)}  form {fid}: GLOW block "
                  f"{'present' if has_block else 'ABSENT'}; {len(flags)} languages, "
                  f"without a built-in flag: {', '.join(missing) or 'none'}")
        return

    client = Client(api_key(), apply=args.apply)
    block = css_block()
    print(f"CSS block: {len(block)} chars, flags for {', '.join(sorted(FLAGS))}\n")
    stamp = backup.stamp()
    problems = 0
    for fid in form_ids:
        label = glow_forms.LABELS.get(fid, fid)
        props = client.get(f"/form/{fid}/properties")
        current = props.get("injectCSS") or ""
        wanted = merge(current, block)
        if wanted == current:
            print(f"== {label}  form {fid}: already has this block")
            continue
        verb = "replace the earlier block in" if ANY_START in current else "append to"
        print(f"== {label}  form {fid}: {verb} injectCSS ({len(current)} -> {len(wanted)} chars)")
        if not args.apply:
            continue
        s = backup.snapshot(fid, client, stamp)
        print(f"   backup_forms: {s['questions']} questions, {s['conditions']} conditions -> backups/{fid}/*-{stamp}.json")
        client.post_form(f"/form/{fid}/properties", {"properties[injectCSS]": wanted},
                         f"{fid} set injectCSS")
        after = client.get(f"/form/{fid}/properties").get("injectCSS") or ""
        if after == wanted:
            print("   written and verified")
        else:
            problems += 1
            print(f"   ! MISMATCH after write: {len(after)} chars read back "
                  f"(block present: {START in after}) - compare with the snapshot before retrying")
    if not args.apply:
        print("\nDRY RUN - re-run with --apply to write")
    if problems:
        sys.exit(f"{problems} form(s) did not verify")


if __name__ == "__main__":
    run(main)
