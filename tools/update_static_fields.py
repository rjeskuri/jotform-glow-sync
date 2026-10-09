"""Set the static fields of the live attendance forms - the ones the sync never
touches: wording, the Group Photo limits, and the header logo.

  2026-09-24  image         -> the Global Catalyst logo, displayed 205x103:
                the same height as the Global Girls GLOW banner it replaces,
                the width from the new logo's own 1.99:1 proportions so
                nothing is squashed. Jotform's API CANNOT upload an asset -
                `src` only ever points at an already-hosted file - so the PNG
                (assets/global-catalyst-header.png, 410x206 = 2x, for phones)
                goes into the account through the builder once and its URL is
                passed to --image-src. See docs/RUNBOOK.md, "Header logo".

  2026-09-12  the training guide's wording, and a roomier photo upload:
                mentorEmail   label -> "Partner Coordinator Email" (the
                              sublabel already says a confirmation is sent
                              there and stays)
                photo         sublabel -> "Upload one photo of everyone in
                              attendance today. All girl faces should be
                              visible."; max file size 3MB -> 10MB; HEIC
                              allowed (iPhones shoot it by default); one photo
                              only (allowMultiple off; fileLimit was already 1)

The Club picker's wording lives in sync_attendance_form.py PICKER_PROPS and is
maintained by the sync - this tool covers only fields the sync never touches.
Fields are found by their unique name, never by qid. Dry run by default;
writing needs the flag below (back up first: backup_forms.py --form <id>);
after a write the question is re-read and compared, and any mismatch fails
the run.

    python3 tools/update_static_fields.py            # dry run, all live forms
    python3 tools/update_static_fields.py --form ID  # one form
    python3 tools/update_static_fields.py --image-src https://.../logo.png
"""
import argparse
import os
import re
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from glow import forms as glow_forms
from glow.cli import api_key, run, targets
from glow.jotform import Client

WANTED = {
    "mentorEmail": {
        "text": "Partner Coordinator Email",
    },
    "photo": {
        "subLabel": "Upload one photo of everyone in attendance today. "
                    "All girl faces should be visible.",
        "limitFileSize": "Yes",
        "maxFileSize": "10240",
        "extensions": "jpg, jpeg, png, gif, heic",
        "allowMultiple": "No",
    },
}

# The header logo. Touched ONLY when --image-src names the hosted file: the
# size below belongs to the new logo, and applying it to the wider banner it
# replaces (406x103) would squash that one. `text` follows Jotform's own
# convention - the file's basename - so it is derived from the URL, not fixed.
IMAGE_FIELD = "image"
IMAGE_PROPS = {
    "width": "205",          # same height as the old banner, and the new
    "height": "103",         # logo's own 1.99:1 proportions -> no squashing
    "align": "Center",
    "alt": "Global Catalyst",
}


def png_size(data):
    """(width, height) from a PNG's IHDR, or None if `data` is not a PNG."""
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def wanted_fields(image_src=None):
    """WANTED, plus the header-logo field when a hosted URL was given."""
    if not image_src:
        return dict(WANTED)
    basename = image_src.rsplit("/", 1)[-1].split("?")[0]
    name = re.sub(r"\.(png|jpe?g|gif|webp|svg)$", "", basename, flags=re.I)
    return {**WANTED, IMAGE_FIELD: {**IMAGE_PROPS, "src": image_src, "text": name}}


def check_src(url, fetch=None):
    """Refuse a header URL that a mentor's browser could not load: it must be
    https, come back 200 as an image, and (PNG) be at least the size it is
    displayed at. Returns a line describing what was found."""
    if not url.startswith("https://"):
        sys.exit(f"--image-src must be an https URL (got {url!r})")
    status, content_type, head = (fetch or _fetch_head)(url)
    if not status.startswith("2"):
        sys.exit(f"--image-src is not reachable: HTTP {status or '?'} for {url}")
    if not content_type.startswith("image/"):
        sys.exit(f"--image-src is not an image: content-type {content_type!r} for {url}")
    want_w, want_h = int(IMAGE_PROPS["width"]), int(IMAGE_PROPS["height"])
    size = png_size(head)
    if not size:
        return f"{content_type}, shown at {want_w}x{want_h}"
    if size[0] < want_w or size[1] < want_h:
        sys.exit(f"--image-src is {size[0]}x{size[1]}, smaller than the "
                 f"{want_w}x{want_h} it is displayed at - upload the 2x file "
                 "(assets/global-catalyst-header.png)")
    return (f"{size[0]}x{size[1]} PNG, shown at {want_w}x{want_h} "
            f"({size[0] / want_w:g}x)")


def _fetch_head(url):
    """(status, content-type, first bytes) of a public URL, via curl."""
    out = subprocess.run(["curl", "-sS", "-L", "-m", "30", "-r", "0-2047",
                          "-w", "\n%{http_code} %{content_type}", url],
                         capture_output=True)
    body, _, tail = out.stdout.rpartition(b"\n")
    parts = tail.decode("utf-8", "replace").split()
    return (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else ""), body


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--form", help="one form id (default: template + the four regionals)")
    ap.add_argument("--image-src", metavar="URL",
                    help="hosted header logo for the image field (the API cannot "
                         "upload one - see the module docstring); without it the "
                         "image field is left alone")
    ap.add_argument("--apply", action="store_true", help="write (dry run without it)")
    args = ap.parse_args()

    form_ids = list(targets([args.form] if args.form else None))
    client = Client(api_key(), apply=args.apply)
    fields = wanted_fields(args.image_src)
    if args.image_src:
        print(f"  header image: {args.image_src}\n    {check_src(args.image_src)}\n")
    else:
        print("  (no --image-src: leaving the header image alone)\n")
    mismatches = 0

    for fid in form_ids:
        label = glow_forms.LABELS.get(fid, fid)
        questions = client.get(f"/form/{fid}/questions")
        by_name = {}
        for qid, q in questions.items():
            by_name.setdefault(q.get("name"), []).append((qid, q))

        print(f"== {label}  form {fid}")
        for name, wanted in fields.items():
            found = by_name.get(name, [])
            if len(found) != 1:
                sys.exit(f"form {fid}: expected exactly one question named "
                         f"{name!r}, found {len(found)} - fix the form first")
            qid, q = found[0]
            drift = {k: v for k, v in wanted.items() if str(q.get(k, "")) != v}
            if not drift:
                print(f"    {name} (q{qid}): already as the guide wants it")
                continue
            for k, v in sorted(drift.items()):
                print(f"    {name} (q{qid}): {k}: {str(q.get(k, ''))[:60]!r} -> {v!r}")
            client.post_form(f"/form/{fid}/question/{qid}",
                             {f"question[{k}]": v for k, v in drift.items()},
                             f"update {name} on {fid}")
            if args.apply:
                after = client.get(f"/form/{fid}/question/{qid}")
                bad = {k: after.get(k) for k in drift if str(after.get(k, "")) != drift[k]}
                if bad:
                    mismatches += 1
                    print(f"    ! MISMATCH after write on {name} (q{qid}): {bad}")
                else:
                    print(f"    {name} (q{qid}): written and verified")

    if not args.apply:
        print("\nDRY RUN - re-run with the write flag to apply")
    if mismatches:
        sys.exit(f"{mismatches} field(s) did not verify - re-read before retrying")


if __name__ == "__main__":
    run(main)
