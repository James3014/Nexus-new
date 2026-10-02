#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT_DEFAULT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_ROOT="${NEXUS_AGY_REPO_ROOT:-$REPO_ROOT_DEFAULT}"
SOURCE="$REPO_ROOT/scripts/ops/nexus-agy-review-canary"
TARGET="${NEXUS_AGY_REVIEW_CANARY_TARGET:-$HOME/.local/bin/nexus-agy-review-canary}"
HOST_RUNTIME_SNAPSHOT="$HOME/.local/share/nexus-host-runtime/current/snapshot"
if [[ -n "${NEXUS_AGY_SNAPSHOT:-}" ]]; then
  SNAPSHOT="$NEXUS_AGY_SNAPSHOT"
elif [[ -d "$HOST_RUNTIME_SNAPSHOT" ]]; then
  SNAPSHOT="$HOST_RUNTIME_SNAPSHOT"
else
  SNAPSHOT="$HOME/.local/share/nexus-agy-direct/Nexus-new"
fi

if [[ ! -f "$SOURCE" ]]; then
  echo "NEXUS_AGY_REVIEW_CANARY_SOURCE_MISSING:$SOURCE" >&2
  exit 1
fi
if [[ ! -f "$SNAPSHOT/nexus/services/agy_reviewer_canary.py" ]]; then
  echo "NEXUS_AGY_REVIEW_CANARY_SNAPSHOT_INVALID:$SNAPSHOT" >&2
  exit 1
fi
if [[ ! -f "$SNAPSHOT/nexus/services/agy_reviewer_runtime.py" ]]; then
  echo "NEXUS_AGY_REVIEW_CANARY_RUNTIME_MISSING:$SNAPSHOT" >&2
  exit 1
fi

python3 -m py_compile "$SOURCE"
mkdir -p "$(dirname "$TARGET")"
TMP="$TARGET.tmp.$$"
install -m 0755 "$SOURCE" "$TMP"
mv "$TMP" "$TARGET"
cmp -s "$SOURCE" "$TARGET"
echo "NEXUS_AGY_REVIEW_CANARY_INSTALLED:$TARGET"
shasum -a 256 "$SOURCE" "$TARGET"
