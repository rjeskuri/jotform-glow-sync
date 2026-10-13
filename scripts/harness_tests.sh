#!/bin/sh
# HARNESS_TEST_CMD for this repo: run the named test files, one runner per kind.
# Python tests live in test/ without __init__.py, and `python3 -m unittest test/x_test.py` imports
# `test.x_test`, which the standard library's own `test` package shadows; `discover -s test -p` finds the
# module by basename instead. JS tests are plain node scripts that exit non-zero on a failed assertion.
set -u
PYTHON=$(test -x .venv/bin/python3 && echo .venv/bin/python3 || echo python3)
[ $# -gt 0 ] || { echo "usage: scripts/harness_tests.sh test/<name>_test.py|js ..." >&2; exit 2; }
status=0
for f in "$@"; do
  case "$f" in
    *_test.py) echo "$PYTHON -m unittest discover -s test -p $(basename "$f")"
               "$PYTHON" -m unittest discover -s "$(dirname "$f")" -p "$(basename "$f")" || status=1 ;;
    *_test.js) echo "node $f"; node "$f" || status=1 ;;
    *) echo "harness_tests.sh: not a test file: $f" >&2; status=2 ;;
  esac
done
exit $status
