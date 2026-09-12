"""Apply the training guide's 2026-09-12 wording to the static fields of the
live attendance forms, and open up the Group Photo upload:

  mentorEmail   label -> "Partner Coordinator Email" (the sublabel already
                says a confirmation is sent there and stays)
  photo         sublabel -> "Upload one photo of everyone in attendance
                today. All girl faces should be visible."; max file size
                3MB -> 10MB; HEIC allowed (iPhones shoot it by default);
                one photo only (allowMultiple off; fileLimit was already 1)

The Club picker's wording lives in sync_attendance_form.py PICKER_PROPS and is
maintained by the sync - this tool covers only fields the sync never touches.
Fields are found by their unique name, never by qid. Dry run by default;
--apply writes (back up first: backup_forms.py --form <id>); after a write the
question is re-read and compared, and any mismatch fails the run.

    python3 tools/update_static_fields.py            # dry run, all live forms
    python3 tools/update_static_fields.py --form ID  # one form
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from glow import forms as glow_forms      # noqa: E402
from glow.cli import run                  # noqa: E402
from glow.jotform import Client           # noqa: E402

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


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--form", help="one form id (default: template + the four regionals)")
    ap.add_argument("--apply", action="store_true", help="write (dry run without it)")
    args = ap.parse_args()

    api_key = os.environ.get("JOTFORM_API_KEY") or sys.exit("Set JOTFORM_API_KEY")
    form_ids = [args.form] if args.form else list(glow_forms.LIVE)
    client = Client(api_key, apply=args.apply)
    mismatches = 0

    for fid in form_ids:
        label = glow_forms.LABELS.get(fid, fid)
        questions = client.get(f"/form/{fid}/questions")
        by_name = {}
        for qid, q in questions.items():
            by_name.setdefault(q.get("name"), []).append((qid, q))

        print(f"== {label}  form {fid}")
        for name, wanted in WANTED.items():
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
        print("\nDRY RUN - re-run with --apply to write")
    if mismatches:
        sys.exit(f"{mismatches} field(s) did not verify - re-read before retrying")


if __name__ == "__main__":
    run(main)
