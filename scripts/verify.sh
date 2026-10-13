#!/bin/sh
# The whole suite plus lint for jotform-glow-sync: CLAUDE_VERIFY_CMD and the stop hook run this;
# CI (.github/workflows/check.yml) runs `make check` directly.
# Each check on its own line, so `set -e` stops at the first failure.
set -eu
cd "$(dirname "$0")/.."

make check

echo VERIFY OK
