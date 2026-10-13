#!/usr/bin/env bash
set -euo pipefail

# Nexus Core's repo-level completion verifier must not mutate the exact subject
# tree. Materialize the exact current index tree into a disposable shared clone,
# install dependencies there, and run the canonical fast L1 verification there.
SUBJECT_ROOT="$(git rev-parse --show-toplevel)"
SOURCE_HEAD="$(git -C "$SUBJECT_ROOT" rev-parse HEAD^{commit})"
TARGET_TREE="$(git -C "$SUBJECT_ROOT" write-tree)"
VERIFY_PARENT="$(mktemp -d "${TMPDIR:-/tmp}/nexus-core-verify.XXXXXX")"
VERIFY_ROOT="$VERIFY_PARENT/repo"

cleanup() {
  rm -rf "$VERIFY_PARENT"
}
trap cleanup EXIT

git clone --no-checkout --shared --quiet "$SUBJECT_ROOT" "$VERIFY_ROOT"
git -C "$VERIFY_ROOT" checkout --detach --quiet "$SOURCE_HEAD"
git -C "$VERIFY_ROOT" read-tree --reset -u "$TARGET_TREE"
if ORIGIN_URL="$(git -C "$SUBJECT_ROOT" remote get-url origin 2>/dev/null)"; then
  git -C "$VERIFY_ROOT" remote set-url origin "$ORIGIN_URL"
fi
test "$(git -C "$VERIFY_ROOT" write-tree)" = "$TARGET_TREE"

cd "$VERIFY_ROOT"
uv sync --frozen --all-groups --all-extras
uv pip install --python .venv/bin/python --requirement requirements/canonical-learning.txt
uv pip install --python .venv/bin/python --requirement requirements/canonical-runtime.txt

exec "$VERIFY_ROOT/scripts/ops/test_fast.sh"
