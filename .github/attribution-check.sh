#!/bin/sh
#
# Fail when text carries tool attribution.
#
# The patterns are the ones .githooks/commit-msg strips. They are repeated here
# rather than shared because the hook rewrites a file in place and this reports
# on one; keeping them literally identical is what matters, so change both.
#
# Usage: attribution-check.sh <file> <what it is>

set -e

file="$1"
what="$2"

matches=$(grep -niE \
  -e '^[[:space:]]*co-authored-by:.*claude' \
  -e '^[[:space:]]*co-authored-by:.*@anthropic\.com' \
  -e '^[[:space:]]*claude-session:' \
  -e 'generated with \[claude code\]' \
  -e '^[[:space:]]*🤖 generated with' \
  -e 'https://claude\.ai/code/session_' \
  "$file" || true)

if [ -z "$matches" ]; then
  exit 0
fi

echo "::error::Tool attribution found in $what."
echo "$matches" | while IFS= read -r line; do
  echo "  $line"
done
cat <<'GUIDANCE'

Commits and pull requests in this repository read as the maintainer's own work.
Remove the lines above.

For commits, enabling the hook strips them automatically before the commit is
written:

    git config core.hooksPath .githooks

A pull request description is not covered by that hook, so it has to be written
without them.
GUIDANCE
exit 1
