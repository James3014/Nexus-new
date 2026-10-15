#!/usr/bin/env bash
# Enforced Codex launcher (#2195, write-admission model of #1912).
#
# * No blanket bypass: codex runs under its own sandbox
#   (workspace-write, or read-only) with an explicit approval policy.
# * Disposable work copy: codex works in a detached Git worktree under
#   NEXUS_CODEX_WORK_ROOT that may not overlap the canonical checkout.
# * Integrity: the canonical checkout is fingerprinted before and after the
#   run; any change fails the run (it is reported, never reverted).
# * Denied actions (declined / rejected / sandbox-denied) are non-delivery.
set -euo pipefail

NEXUS_ROOT="."
MODEL="${1:-gpt-5.4-mini}"
APPROVAL_MODE="${2:-workspace-write}"
PROMPT_FILE="${3:-/tmp/antigravity_nexus_task.md}"
NEXUS_MACHINE_STATE_DIR="${NEXUS_MACHINE_STATE_DIR:-${NEXUS_STATE_DIR:-${TMPDIR:-/tmp}/nexus-machine-state}}"
NEXUS_STARTUP_REPORT_DIR="${NEXUS_STARTUP_REPORT_DIR:-$NEXUS_MACHINE_STATE_DIR/startup_hardening}"
export NEXUS_MACHINE_STATE_DIR NEXUS_STARTUP_REPORT_DIR
REPORT_FILE="${REPORT_FILE:-$NEXUS_MACHINE_STATE_DIR/antigravity_invoke_report.txt}"
LOCK_FILE="${LOCK_FILE:-/tmp/nexus_antigravity_invoke.lock}"
CODEX_BIN="${CODEX_BIN:-codex}"

# Map the requested mode onto a codex sandbox; anything else is refused.
# "full-auto" is the historical default and now means workspace-write.
case "$APPROVAL_MODE" in
  workspace-write|full-auto) SANDBOX_MODE="workspace-write" ;;
  read-only) SANDBOX_MODE="read-only" ;;
  *)
    echo "[nexus-enforced] approval mode refused: $APPROVAL_MODE (allowed: workspace-write, read-only; no sandbox bypass, #2195)" >&2
    exit 2
    ;;
esac

mkdir -p "$NEXUS_MACHINE_STATE_DIR" "$NEXUS_STARTUP_REPORT_DIR"

if [[ ! -f "$PROMPT_FILE" ]]; then
  cat >&2 <<EOF
[nexus-enforced] prompt file missing: $PROMPT_FILE
Create one first, e.g.:
  cat > /tmp/antigravity_nexus_task.md <<'TASK'
  在 . 內完成指定任務，
  並回報變更檔案、測試摘要與 gate 結果。
  TASK
EOF
  exit 2
fi

if ! command -v "$CODEX_BIN" >/dev/null 2>&1; then
  echo "[nexus-enforced] missing command: $CODEX_BIN" >&2
  exit 2
fi

if [[ -e "$LOCK_FILE" ]]; then
  echo "[nexus-enforced] another antigravity run is active: $LOCK_FILE" >&2
  exit 3
fi

trap 'rm -f "$LOCK_FILE"' EXIT
echo "$$" > "$LOCK_FILE"

cd "$NEXUS_ROOT"
CANONICAL_ROOT="$(cd "$(git rev-parse --show-toplevel)" && pwd -P)"

echo "[nexus-enforced] canonical_root=$CANONICAL_ROOT"
echo "[nexus-enforced] model=$MODEL sandbox=$SANDBOX_MODE approval_policy=never"
echo "[nexus-enforced] prompt_file=$PROMPT_FILE"
echo "[nexus-enforced] report_file=$REPORT_FILE"

BRIEFING_PATH="$(bash scripts/ops/_nexus_enforced_briefing.sh "$NEXUS_MACHINE_STATE_DIR/enforced_agent_briefing.md")"
echo "[nexus-enforced] briefing=$BRIEFING_PATH"

# 🛡️ Nexus Startup Contract Check
export NEXUS_RUNNER="Codex"
python3 scripts/ops/nexus_startup_contract_check.py || {
  echo "❌ [ENFORCEMENT-BLOCK] Startup Contract FAILED. Codex cannot proceed."
  exit 1
}

_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum | cut -d' ' -f1
  else
    shasum -a 256 | cut -d' ' -f1
  fi
}

# HEAD, porcelain status, tracked diff, untracked file bytes and the Git
# common dir's code-bearing metadata (config, hooks/, info/).
canonical_fingerprint() {
  local root="$1" common file
  common="$(git -C "$root" rev-parse --path-format=absolute --git-common-dir)"
  {
    git -C "$root" rev-parse --verify HEAD
    git -C "$root" status --porcelain=v1 -uall -z
    git -C "$root" diff --binary HEAD | _sha256
    while IFS= read -r -d '' file; do
      printf 'untracked:%s:' "$file"
      _sha256 < "$root/$file" || echo unreadable
    done < <(git -C "$root" ls-files -z --others --exclude-standard)
    printf 'config:'
    _sha256 < "$common/config" || echo missing
    for file in $(find "$common/hooks" "$common/info" -type f 2>/dev/null | LC_ALL=C sort); do
      printf '%s:' "${file#"$common"/}"
      _sha256 < "$file" || echo unreadable
    done
  } | _sha256
}

paths_overlap() {
  case "$1/" in "$2/"*) return 0 ;; esac
  case "$2/" in "$1/"*) return 0 ;; esac
  return 1
}

WORK_PARENT="${NEXUS_CODEX_WORK_ROOT:-${TMPDIR:-/tmp}/nexus-codex-runs}"
mkdir -p "$WORK_PARENT"
WORK_PARENT="$(cd "$WORK_PARENT" && pwd -P)"
if paths_overlap "$WORK_PARENT" "$CANONICAL_ROOT"; then
  echo "[nexus-enforced] work root overlaps the canonical checkout: $WORK_PARENT" >&2
  exit 2
fi

BEFORE="$(canonical_fingerprint "$CANONICAL_ROOT")"
WORK_DIR="$(mktemp -d "$WORK_PARENT/run.XXXXXX")"
rmdir "$WORK_DIR"
git -C "$CANONICAL_ROOT" worktree add --quiet --detach "$WORK_DIR" HEAD
WORK_DIR="$(cd "$WORK_DIR" && pwd -P)"
echo "[nexus-enforced] work_copy=$WORK_DIR"

echo "[nexus-enforced] invoke codex-nexus (enforced)"
set +e
"$CODEX_BIN" exec --ephemeral --json -C "$WORK_DIR" -m "$MODEL" \
  --sandbox "$SANDBOX_MODE" -c 'approval_policy="never"' - < "$PROMPT_FILE" | tee "$REPORT_FILE"
CODEX_STATUS=${PIPESTATUS[0]}
set -e

AFTER="$(canonical_fingerprint "$CANONICAL_ROOT" || echo unavailable)"
if [[ "$AFTER" != "$BEFORE" ]]; then
  echo "[nexus-enforced] canonical_checkout_integrity_violation: $CANONICAL_ROOT changed during the run" >&2
  exit 5
fi
if grep -Eqi 'sandbox denied|rejected by user|"status": *"declined"' "$REPORT_FILE"; then
  echo "[nexus-enforced] codex_action_denied: a denied action is non-delivery (work copy kept: $WORK_DIR)" >&2
  exit 4
fi
if [[ "$CODEX_STATUS" -ne 0 ]]; then
  echo "[nexus-enforced] codex exited $CODEX_STATUS (work copy kept: $WORK_DIR)" >&2
  exit "$CODEX_STATUS"
fi
echo "[nexus-enforced] delivered; review the diff in $WORK_DIR, then: git worktree remove $WORK_DIR"
