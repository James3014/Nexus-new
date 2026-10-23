#!/bin/bash
# Install the Cairnwork worker-account wrapper and the agy copy it runs (#2884, Cairnwork #19 Phase B).
#
# Run as the Owner (no sudo) after Cairnwork's scripts/setup_worker_user.sh has created
# /Users/Shared/cairnwork-worker/bin (Owner-owned, 0755). Copies
#   scripts/ops/agy-worker-exec -> <bin>/agy-worker-exec   (the sudoers rule names this path)
#   the Owner's agy binary      -> <bin>/agy               (the worker cannot enter /Users/<owner>)
# both Owner-owned, mode 0755, replaced atomically. Re-run it whenever the wrapper changes:
# nexus-agy-dispatch --run-as-user refuses a run while the wrapper copy differs from its source.
# A stale agy copy (agy updates itself) is replaced by the dispatcher itself (#2888 follow-up).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="${NEXUS_AGY_WORKER_BIN:-/Users/Shared/cairnwork-worker/bin}"
WRAPPER_SOURCE="$SCRIPT_DIR/agy-worker-exec"
AGY_SOURCE="${NEXUS_AGY_SOURCE_BINARY:-$(command -v agy || true)}"

die() { echo "AGY_WORKER_EXEC_INSTALL_REFUSED:$*" >&2; exit 1; }

[[ -n "$AGY_SOURCE" && -f "$AGY_SOURCE" && -x "$AGY_SOURCE" ]] || die "agy_binary_missing"
[[ -f "$WRAPPER_SOURCE" ]] || die "wrapper_source_missing:$WRAPPER_SOURCE"
[[ -d "$BIN" && ! -L "$BIN" ]] || die "bin_missing:$BIN (run Cairnwork scripts/setup_worker_user.sh first)"
[[ "$(cd -P -- "$BIN" && pwd -P)" == "$BIN" ]] || die "bin_not_canonical:$BIN"
bin_owner=$(stat -c %u "$BIN" 2>/dev/null || stat -f %u "$BIN")
bin_mode=$(stat -c %a "$BIN" 2>/dev/null || stat -f %Lp "$BIN")
[[ "$bin_owner" == "$(id -u)" ]] || die "bin_not_owned_by_$(id -un):$BIN"
[[ "$bin_mode" == "755" ]] || die "bin_mode_$bin_mode:$BIN"
sh -n "$WRAPPER_SOURCE" || die "wrapper_syntax"

install_one() {   # $1 source  $2 destination
  local tmp="$2.tmp.$$"
  rm -f "$tmp"
  cp "$1" "$tmp"
  chmod 0755 "$tmp"
  mv -f "$tmp" "$2"
  [[ ! -L "$2" ]] || die "installed_symlink:$2"
  cmp -s "$1" "$2" || die "installed_copy_differs:$2"
  echo "AGY_WORKER_EXEC_INSTALLED:$2"
}

install_one "$WRAPPER_SOURCE" "$BIN/agy-worker-exec"
install_one "$AGY_SOURCE" "$BIN/agy"
shasum -a 256 "$BIN/agy-worker-exec" "$BIN/agy"
