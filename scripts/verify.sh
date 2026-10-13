#!/bin/sh
# The whole suite plus lint for jotform-glow-sync: CLAUDE_VERIFY_CMD, the stop hook and CI run this.
# Each check on its own line, so `set -e` stops at the first failure.
set -eu
cd "$(dirname "$0")/.."

make check

echo VERIFY OK
