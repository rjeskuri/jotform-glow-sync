#!/usr/bin/env python3
"""
Switch a regional attendance form off (status DISABLED: Jotform serves its
"form unavailable" page instead of the form) or on again, through the API,
with a snapshot first and a re-read after.

`status` is a property of every form (ENABLED / DISABLED on GET /form/{id}
and GET /form/{id}/properties, read 2026-10-06). Whether the form-encoded
POST /form/{id}/properties with properties[status] CHANGES it is unverified
(docs/plans/2026-10-06-clubs-off-jotform.md, D): the tool re-reads after the
write and, when the status did not move, says so and stops - the form is then
disabled in the builder (Settings -> Form Status) and this tool's dry run
confirms it. The result either way goes into .claude/skills/jotform-api.

Dry run: the form's title, status, submission count and last submission, and
the properties `status` and `messageOfLimitedForm` (the disabled page's text,
Jotform's default "This form is currently unavailable!"; that this property is
what the page shows is unverified too). Refuses the template, any form not in
glow.forms.LIVE (the defunct forms are already off), and - without
--disable-anyway - a form with a submission in the last 30 days.

    python3 tools/disable_form.py --form 262382706852058                     # dry run
    python3 tools/disable_form.py --form 262382706852058 --message "<text>" --apply
    python3 tools/disable_form.py --form 262382706852058 --enable --apply    # the way back

--apply: backup_forms.snapshot first (the properties snapshot records status
and the message to put back), then the POST, then both GETs again. The runner
skips a DISABLED form (SyncLog `skipped`); docs/RUNBOOK.md, "Disabling a
regional form".
"""
import argparse
import os
import sys
from datetime import datetime, timedelta

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import backup_forms                      # noqa: E402
from glow import forms as glow_forms     # noqa: E402
from glow.cli import api_key, run                 # noqa: E402
from glow.jotform import Client          # noqa: E402

RECENT_DAYS = 30
ENABLED, DISABLED = "ENABLED", "DISABLED"
DEFAULT_MESSAGE = "This form is currently unavailable!"     # Jotform's own, read on the defunct forms
STILL_ENABLED = ("the API accepted the write but the status did not change - disable the form in the "
                 "builder (Settings -> Form Status) and run this again without --apply to confirm")


def read_form(client, form_id, after_write=False):
    """(title, status, count, last submission or "", messageOfLimitedForm) from GET /form/{id}
    and GET /form/{id}/properties; the two statuses must agree or the tool refuses to say -
    and says whether the POST has already gone out (`after_write`: the re-read)."""
    form = client.get(f"/form/{form_id}") or {}
    props = client.get(f"/form/{form_id}/properties") or {}
    status, prop_status = str(form.get("status") or ""), str(props.get("status") or "")
    if status != prop_status:
        sys.exit(f"form {form_id}: GET /form says status {status!r}, its properties say "
                 f"{prop_status!r} - not the same form state"
                 + (" after the write - the properties POST was sent; run this again without --apply "
                    "until both GETs agree, then decide" if after_write
                    else "; read again before anything is written"))
    return (str(form.get("title") or ""), status, int(form.get("count") or 0),
            str(form.get("last_submission") or "").strip(), str(props.get("messageOfLimitedForm") or ""))


def describe(form_id, title, status, count, last, message):
    print(f"{title} {form_id}: status {status}, {count} submissions (last {last or 'none'})")
    print(f"  messageOfLimitedForm: {message!r}")


def recent(last, today, days=RECENT_DAYS):
    """Whether `last` (Jotform's "yyyy-mm-dd hh:mm:ss") falls in the last `days` days of `today`."""
    return bool(last) and last[:10] >= (today - timedelta(days=days)).strftime("%Y-%m-%d")


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--form", required=True, metavar="ID", help="the regional form (docs/RUNBOOK.md)")
    ap.add_argument("--enable", action="store_true", help="switch the form on again (default: off)")
    ap.add_argument("--message", metavar="TEXT",
                    help="the disabled page's text (properties[messageOfLimitedForm]); default: leave it")
    ap.add_argument("--disable-anyway", action="store_true",
                    help=f"disable although the form took a submission in the last {RECENT_DAYS} days")
    ap.add_argument("--apply", action="store_true", help="write (dry run without it)")
    args = ap.parse_args()

    form_id = args.form.strip()
    if form_id == glow_forms.TEMPLATE:
        sys.exit("the template is never disabled: every logic change lands there first, and mentors "
                 "never see it")
    if form_id not in glow_forms.LIVE:
        sys.exit(f"form {form_id} is not one of the live regional forms (ids in docs/RUNBOOK.md); the "
                 "defunct forms are already off")
    if args.enable and (args.message or args.disable_anyway):
        sys.exit("--enable takes no --message and no --disable-anyway")
    client = Client(api_key(), apply=args.apply)
    wanted = ENABLED if args.enable else DISABLED

    title, status, count, last, message = read_form(client, form_id)
    describe(form_id, title, status, count, last, message)
    if status not in (ENABLED, DISABLED):
        sys.exit(f"status {status!r} is neither {ENABLED} nor {DISABLED} - a state this tool does not know")
    if status == wanted and (args.message is None or args.message == message):
        print(f"\nalready {wanted} - nothing to do")
        return
    if wanted == DISABLED and recent(last, datetime.now()) and not args.disable_anyway:
        sys.exit(f"form {form_id} took a submission on {last[:10]} (in the last {RECENT_DAYS} days) - "
                 "disabling a form mentors use needs --disable-anyway")

    data = {}
    if status != wanted:
        data["properties[status]"] = wanted
    if args.message is not None and args.message != message:
        data["properties[messageOfLimitedForm]"] = args.message
        print(f"  message -> {args.message!r}")
    if not args.apply:
        what = f"set status {wanted}" if status != wanted else "set the message"
        print(f"\nDRY RUN - re-run with --apply to back up the form, then {what} (then re-read)")
        return

    stamp = datetime.now().strftime("%Y-%m-%dT%H%M")
    s = backup_forms.snapshot(form_id, client, stamp)
    print(f"\n  backup_forms: form {form_id} ({s['questions']} questions, {s['conditions']} conditions, "
          f"status {status}) -> backups/{form_id}/*-{stamp}.json")
    client.post_form(f"/form/{form_id}/properties", data,
                     f"POST properties of {form_id}: " + ", ".join(f"{k}={v!r}" for k, v in data.items()))
    title, after, count, last, message_after = read_form(client, form_id, after_write=True)
    print("  re-read:")
    describe(form_id, title, after, count, last, message_after)
    if after != wanted:
        sys.exit(STILL_ENABLED if wanted == DISABLED else
                 "the API accepted the write but the status did not change - enable the form in the "
                 "builder (Settings -> Form Status) and run this again without --apply to confirm")
    if "properties[messageOfLimitedForm]" in data and message_after != args.message:
        sys.exit(f"status {after} as wanted, but messageOfLimitedForm did not change (still "
                 f"{message_after!r}) - set the disabled page's text in the builder (Settings -> "
                 "Form Status)")
    print(f"  form {form_id} is {after}" + (" - the runner reads it as 'skipped' on its next run"
                                         if after == DISABLED else
                                         " - one runner dry run next (python3 tools/auto_sync.py)"))


if __name__ == "__main__":
    run(main)
