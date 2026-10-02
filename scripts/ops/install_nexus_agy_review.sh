#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT_DEFAULT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_ROOT="${NEXUS_AGY_REPO_ROOT:-$REPO_ROOT_DEFAULT}"
SOURCE="$REPO_ROOT/scripts/ops/nexus-agy-review"
TARGET="${NEXUS_AGY_REVIEW_TARGET:-$HOME/.local/bin/nexus-agy-review}"
SNAPSHOT="${NEXUS_AGY_SNAPSHOT:-$HOME/.local/share/nexus-agy-direct/Nexus-new}"

if [[ ! -f "$SOURCE" ]]; then
  echo "NEXUS_AGY_REVIEW_SOURCE_MISSING:$SOURCE" >&2
  exit 1
fi
if [[ ! -f "$SNAPSHOT/nexus/services/agy_reviewer_runtime.py" ]]; then
  echo "NEXUS_AGY_REVIEW_SNAPSHOT_INVALID:$SNAPSHOT" >&2
  exit 1
fi

python3 -m py_compile "$SOURCE"
mkdir -p "$(dirname "$TARGET")"
TMP="$TARGET.tmp.$$"
install -m 0755 "$SOURCE" "$TMP"
mv "$TMP" "$TARGET"
cmp -s "$SOURCE" "$TARGET"
echo "NEXUS_AGY_REVIEW_INSTALLED:$TARGET"
shasum -a 256 "$SOURCE" "$TARGET"
