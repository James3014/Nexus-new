#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT_DEFAULT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_ROOT="${NEXUS_HOST_REPO_ROOT:-$REPO_ROOT_DEFAULT}"
SOURCE="$REPO_ROOT/scripts/ops/nexus-host-sync"
TARGET="${NEXUS_HOST_SYNC_TARGET:-$HOME/.local/bin/nexus-host-sync}"

if [[ ! -f "$SOURCE" ]]; then
  echo "NEXUS_HOST_SYNC_SOURCE_MISSING:$SOURCE" >&2
  exit 1
fi

python3 -m py_compile "$SOURCE"
mkdir -p "$(dirname "$TARGET")"
TMP="$TARGET.tmp.$$"
install -m 0755 "$SOURCE" "$TMP"
mv "$TMP" "$TARGET"
cmp -s "$SOURCE" "$TARGET"
echo "NEXUS_HOST_SYNC_INSTALLED:$TARGET"
shasum -a 256 "$SOURCE" "$TARGET"
