"""What every command-line tool shares: run(main) with the repo's error convention (a
JotformError becomes a clean one-line exit instead of a traceback), the Jotform API key
from the environment, and the forms a --form option selects."""
import os
import sys

from . import forms
from .jotform import JotformError


def run(main):
    try:
        main()
    except JotformError as err:
        sys.exit(str(err))


def api_key(hint="", error=SystemExit):
    """The Jotform API key from the environment (.env), stripped. Without one, raise
    `error` - by default SystemExit, which stops the tool with the message - saying
    "Set JOTFORM_API_KEY in the environment (.env)" + `hint`. Call it in main() after
    parse_args, so --help needs no key (scripts/check_py.py smokes --help without one)."""
    key = (os.environ.get("JOTFORM_API_KEY") or "").strip()
    if not key:
        raise error("Set JOTFORM_API_KEY in the environment (.env)" + hint)
    return key


def targets(form_ids, table=None, unknown="?"):
    """{form id: label} of the forms a tool works on: the --form ids given, each labelled
    from `table` (default glow.forms.LIVE: "template" or the region) or with `unknown`
    when the table lacks it (None: the id itself); with no --form, the whole table, in
    its order."""
    table = forms.LIVE if table is None else table
    if not form_ids:
        return dict(table)
    return {f: table.get(f, f if unknown is None else unknown) for f in form_ids}
