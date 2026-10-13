#!/bin/sh
# HARNESS_TEST_CMD for this repo: run the named test files, one runner per kind.
# Python tests live in test/ without __init__.py, and `python3 -m unittest test/x_test.py` imports
# `test.x_test`, which the standard library's own `test` package shadows; `discover -s <dir> -p <name>`
# finds the module by basename instead (any .py name: x_test.py or test_x.py). JS tests are plain node
# scripts that exit non-zero on a failed assertion. A path of another kind runs nothing: the script
# says "no tests ran" and exits 5, which harness-red refuses to record as a red run.
set -u
PYTHON=$(test -x .venv/bin/python3 && echo .venv/bin/python3 || echo python3)
[ $# -gt 0 ] || { echo "usage: scripts/harness_tests.sh test/<name>_test.py|.js ..." >&2; echo "no tests ran"; exit 5; }
for f in "$@"; do
  case "$f" in
    *.py|*.js|*.mjs) ;;
    *) echo "harness_tests.sh: cannot run $f (not .py, .js or .mjs); no tests ran" >&2; exit 5 ;;
  esac
done
status=0
for f in "$@"; do
  case "$f" in
    *.py)       echo "$PYTHON -m unittest discover -s $(dirname "$f") -p $(basename "$f")"
                "$PYTHON" -m unittest discover -s "$(dirname "$f")" -p "$(basename "$f")" || status=1 ;;
    *.js|*.mjs) echo "node $f"; node "$f" || status=1 ;;
  esac
done
exit $status
