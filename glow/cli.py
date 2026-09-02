"""Run a tool's main() with the repo's error convention: a JotformError
becomes a clean one-line exit instead of a traceback."""
import sys

from .jotform import JotformError


def run(main):
    try:
        main()
    except JotformError as err:
        sys.exit(str(err))
