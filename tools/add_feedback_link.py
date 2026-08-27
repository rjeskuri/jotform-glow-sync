#!/usr/bin/env python3
"""
Put a "Something not working? Tell us" link at the bottom of the Jotform
attendance forms, just above the Submit button — and take it out again later.

It adds ONE text element per form (no logic, no integration changes) so it is
harmless to the Salesforce mapping and trivial to reverse. Dry run by default.

Usage:
    export JOTFORM_API_KEY=...
    python3 tools/add_feedback_link.py --url https://forms.gle/xxxx            # preview
    python3 tools/add_feedback_link.py --url https://forms.gle/xxxx --apply
    python3 tools/add_feedback_link.py --remove --apply                        # take it out
    python3 tools/add_feedback_link.py --url ... --form 260703905772560 --apply  # one form only
"""
import argparse
import html
import json
import os
import subprocess
import sys

API_BASE = "https://api.jotform.com"
ELEMENT_NAME = "somethingNotWorking"     # unique name = how we find it again

# the live regional forms (cloned 2026-08-27) + the template they came from
FORMS = {
    "262382821971058": "Africa",
    "262383129464057": "Asia",
    "262383455778067": "Latin America",
    "262382706852058": "U.S",
    "262352490535154": "template",
}


def call(args, label, api_key):
    out = subprocess.run(["curl", "-sS"] + args, capture_output=True, text=True)
    try:
        resp = json.loads(out.stdout)
    except json.JSONDecodeError:
        sys.exit(f"{label}: non-JSON response: {out.stdout[:200]}")
    if resp.get("responseCode") != 200:
        sys.exit(f"{label}: {resp.get('responseCode')} {resp.get('message')}")
    return resp["content"]


LINK_TEXT = "Click here to report a problem"   # translated in tools/translations_additions.json


def link_html(url):
    # one plain sentence, so it can be translated as a single string
    u = html.escape(url, quote=True)
    return ('<p style="margin:12px 0;padding:10px 12px;border:1px solid #ddd;'
            'border-radius:6px;background:#f7f7f7;font-size:14px">'
            f'<a href="{u}" target="_blank" rel="noopener">{LINK_TEXT}</a></p>')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--url", help="the feedback Google Form's public URL")
    ap.add_argument("--form", action="append", help="limit to these form IDs")
    ap.add_argument("--remove", action="store_true", help="delete the link element")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.remove and not args.url:
        sys.exit("--url is required (or --remove)")
    api_key = os.environ.get("JOTFORM_API_KEY") or sys.exit("Set JOTFORM_API_KEY")

    targets = {f: FORMS.get(f, "?") for f in args.form} if args.form else FORMS
    print("DRY RUN\n" if not args.apply else "APPLYING\n")

    for form_id, label in targets.items():
        questions = call([f"{API_BASE}/form/{form_id}/questions?apiKey={api_key}"],
                         f"{form_id} questions", api_key)
        ours = [q for q in questions.values() if q.get("name") == ELEMENT_NAME]
        button = [q for q in questions.values() if q.get("type") == "control_button"]
        top_order = max(int(q.get("order", 0)) for q in questions.values())

        if args.remove:
            if not ours:
                print(f"  {form_id} {label:<14} no link element present")
                continue
            for q in ours:
                print(f"  {form_id} {label:<14} DELETE qid {q['qid']}")
                if args.apply:
                    call(["-X", "DELETE", f"{API_BASE}/form/{form_id}/question/{q['qid']}?apiKey={api_key}"],
                         f"{form_id} delete {q['qid']}", api_key)
            continue

        body = link_html(args.url)
        if ours:
            q = ours[0]
            print(f"  {form_id} {label:<14} UPDATE qid {q['qid']} (already present)")
            if args.apply:
                call(["-X", "POST", f"{API_BASE}/form/{form_id}/question/{q['qid']}?apiKey={api_key}",
                      "--data-urlencode", f"question[text]={body}"],
                     f"{form_id} update {q['qid']}", api_key)
            continue

        # place it right before the Submit button: same order as the button,
        # then bump the button by one (adding a question never shifts orders)
        btn = button[0] if button else None
        order = int(btn["order"]) if btn else top_order + 1
        print(f"  {form_id} {label:<14} ADD text element at order {order}"
              + (f", move Submit (qid {btn['qid']}) to {order + 1}" if btn else ""))
        if args.apply:
            created = call(["-X", "POST", f"{API_BASE}/form/{form_id}/questions?apiKey={api_key}",
                            "--data-urlencode", "question[type]=control_text",
                            "--data-urlencode", f"question[name]={ELEMENT_NAME}",
                            "--data-urlencode", f"question[text]={body}",
                            "--data-urlencode", f"question[order]={order}"],
                           f"{form_id} add", api_key)
            new_qid = created.get("qid") if isinstance(created, dict) else None
            if btn:
                call(["-X", "POST", f"{API_BASE}/form/{form_id}/question/{btn['qid']}?apiKey={api_key}",
                      "--data-urlencode", f"question[order]={order + 1}"],
                     f"{form_id} move submit", api_key)
            print(f"      added qid {new_qid}")

    if not args.apply:
        print("\nre-run with --apply to write")


if __name__ == "__main__":
    main()
