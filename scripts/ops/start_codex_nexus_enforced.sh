#!/usr/bin/env bash
# Enforced Codex launcher (#2195, write-admission model of #1912).
#
# * No blanket bypass: codex runs under its own sandbox
#   (workspace-write, or read-only) with an explicit approval policy.
# * Disposable work copy: codex works in a detached Git worktree under
#   NEXUS_CODEX_WORK_ROOT that may not overlap the canonical checkout.
# * TMPDIR and /tmp are excluded from the sandbox's writable roots, and the
#   work copies and the JSONL report default to a state dir outside both, so
#   a sandboxed run cannot rewrite earlier work copies or its own report.
# * Integrity: the canonical checkout is fingerprinted before and after the
#   run; any change fails the run (it is reported, never reverted).
# * Denied actions (declined / rejected / sandbox-denied) are non-delivery;
#   they are read from structured JSONL events, never from free text.
set -euo pipefail

NEXUS_ROOT="."
MODEL="${1:-gpt-5.4-mini}"
APPROVAL_MODE="${2:-workspace-write}"
PROMPT_FILE="${3:-/tmp/antigravity_nexus_task.md}"
NEXUS_MACHINE_STATE_DIR="${NEXUS_MACHINE_STATE_DIR:-${NEXUS_STATE_DIR:-${TMPDIR:-/tmp}/nexus-machine-state}}"
NEXUS_STARTUP_REPORT_DIR="${NEXUS_STARTUP_REPORT_DIR:-$NEXUS_MACHINE_STATE_DIR/startup_hardening}"
export NEXUS_MACHINE_STATE_DIR NEXUS_STARTUP_REPORT_DIR
# Outside TMPDIR and /tmp: workspace-write would otherwise let the run rewrite them.
CODEX_STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/nexus-codex"
REPORT_FILE="${REPORT_FILE:-$CODEX_STATE_DIR/antigravity_invoke_report.txt}"
LOCK_FILE="${LOCK_FILE:-/tmp/nexus_antigravity_invoke.lock}"
CODEX_BIN="${CODEX_BIN:-codex}"

# The model is an argv value (an empty $1 already means the default model):
# refuse anything codex could parse as a flag
# (mirrors agy_model_shape_ok in nexus/executors/agy_write_admission.py).
if [[ -z "$MODEL" || "$MODEL" == -* || "$MODEL" =~ [[:space:]=] ]]; then
  echo "[nexus-enforced] model refused: '$MODEL' (non-empty, no leading '-', no whitespace or '=')" >&2
  exit 2
fi

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

mkdir -p "$NEXUS_MACHINE_STATE_DIR" "$NEXUS_STARTUP_REPORT_DIR" "$(dirname "$REPORT_FILE")"

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

RUN_HOME=""
trap 'rm -f "$LOCK_FILE"; [[ -z "$RUN_HOME" ]] || rm -rf "$RUN_HOME"' EXIT
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

# HEAD, the checked-out branch (name + object), porcelain status, tracked
# diff, untracked file bytes and the Git common dir's code-bearing metadata
# (config, hooks/, info/).  Refs are deliberately limited to HEAD and its
# branch: the common dir is shared with every other worktree, so another
# session's commit, fetch (refs/remotes) or `gc --auto` (packed-refs) during
# a multi-minute run would otherwise be a false integrity violation; codex
# workspace-write already denies writes under .git.  Every step that can fail returns 1 so a snapshot
# that cannot be taken is never mistaken for an unchanged checkout; a missing
# hooks/ or info/ directory is a normal state, not a failure.
_fingerprint_material() {
  local root="$1" common dir file branch rc
  common="$(git -C "$root" rev-parse --path-format=absolute --git-common-dir)" || return 1
  git -C "$root" rev-parse --verify HEAD || return 1
  git -C "$root" status --porcelain=v1 -uall -z || return 1
  git -C "$root" diff --binary HEAD | _sha256 || return 1
  git -C "$root" ls-files -z --others --exclude-standard | while IFS= read -r -d '' file; do
    printf 'untracked:%s:' "$file"
    _sha256 < "$root/$file" || echo unreadable
  done || return 1
  printf 'head-ref:'
  # symbolic-ref -q exits 1 for a detached HEAD (a valid state), >1 on error.
  branch="$(git -C "$root" symbolic-ref -q HEAD)" && rc=0 || rc=$?
  if [[ "$rc" -eq 0 ]]; then
    printf '%s ' "$branch"
    git -C "$root" rev-parse --verify "$branch" || return 1
  elif [[ "$rc" -eq 1 ]]; then
    echo detached
  else
    return 1
  fi
  printf 'config:'
  _sha256 < "$common/config" || echo missing
  for dir in hooks info; do
    [[ -d "$common/$dir" ]] || continue
    find "$common/$dir" -type f -print0 | LC_ALL=C sort -z | while IFS= read -r -d '' file; do
      printf '%s:' "${file#"$common"/}"
      _sha256 < "$file" || echo unreadable
    done || return 1
  done
}

canonical_fingerprint() {
  _fingerprint_material "$1" | _sha256
}

paths_overlap() {
  case "$1/" in "$2/"*) return 0 ;; esac
  case "$2/" in "$1/"*) return 0 ;; esac
  return 1
}

WORK_PARENT="${NEXUS_CODEX_WORK_ROOT:-$CODEX_STATE_DIR/runs}"
mkdir -p "$WORK_PARENT"
WORK_PARENT="$(cd "$WORK_PARENT" && pwd -P)"
if paths_overlap "$WORK_PARENT" "$CANONICAL_ROOT"; then
  echo "[nexus-enforced] work root overlaps the canonical checkout: $WORK_PARENT" >&2
  exit 2
fi

if ! BEFORE="$(canonical_fingerprint "$CANONICAL_ROOT")"; then
  echo "[nexus-enforced] canonical_checkout_snapshot_unavailable: $CANONICAL_ROOT" >&2
  exit 2
fi
WORK_DIR="$(mktemp -d "$WORK_PARENT/run.XXXXXX")"
rmdir "$WORK_DIR"
git -C "$CANONICAL_ROOT" worktree add --quiet --detach "$WORK_DIR" HEAD
WORK_DIR="$(cd "$WORK_DIR" && pwd -P)"
echo "[nexus-enforced] work_copy=$WORK_DIR"

# Disposable HOME (#2254): codex gets a copy of its auth file only (0600), an
# allowlisted environment, and never the host HOME (~/.ssh, ~/.config/gh,
# ~/.gitconfig, ~/.codex history/sessions/memories/MCP config).  The helper
# runs under python3 -I from this script's own checkout.  Deleted on exit.
GUARD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/codex_run_guard.py"
mkdir -p "$CODEX_STATE_DIR"
RUN_HOME="$(mktemp -d "$CODEX_STATE_DIR/home.XXXXXX")"
python3 -I "$GUARD" home "$RUN_HOME" || exit 2
# Symlinks escaping the work copy and the .git pointer, before and after.
# The baseline lives in this shell, not on disk where the run could rewrite it.
TARGET_SNAPSHOT="$(python3 -I "$GUARD" snapshot "$WORK_DIR")" || exit 2

echo "[nexus-enforced] invoke codex-nexus (enforced)"
set +e
python3 -I "$GUARD" exec "$RUN_HOME" -- "$CODEX_BIN" exec --ephemeral --json -C "$WORK_DIR" -m "$MODEL" \
  --sandbox "$SANDBOX_MODE" -c 'approval_policy="never"' \
  -c sandbox_workspace_write.exclude_tmpdir_env_var=true \
  -c sandbox_workspace_write.exclude_slash_tmp=true \
  - < "$PROMPT_FILE" | tee "$REPORT_FILE"
CODEX_STATUS=${PIPESTATUS[0]}
set -e

if ! AFTER="$(canonical_fingerprint "$CANONICAL_ROOT")"; then
  echo "[nexus-enforced] canonical_snapshot_failed: $CANONICAL_ROOT could not be re-fingerprinted" >&2
  exit 5
fi
if [[ "$AFTER" != "$BEFORE" ]]; then
  echo "[nexus-enforced] canonical_checkout_integrity_violation: $CANONICAL_ROOT changed during the run" >&2
  exit 5
fi

if ! printf '%s' "$TARGET_SNAPSHOT" | python3 -I "$GUARD" verify "$WORK_DIR"; then
  echo "[nexus-enforced] codex_target_symlink_or_git_escape: work copy kept: $WORK_DIR" >&2
  exit 6
fi

# Denials are read from the structured `codex exec --json` stream only.
# Assumed event shapes (codex-cli 0.162.1; not confirmable without a model
# run, so the matched key set is kept small and explicit):
#   {"type":"item.*","item":{"type":"command_execution"|"file_change"|
#     "mcp_tool_call"|...,"status":"declined"|"rejected"}}   -> denied
#   {"type":"error","message":"sandbox denied ..."} and
#   {"type":"turn.failed","error":{"message":"sandbox denied ..."}} -> denied
# Free text (agent messages, command output, file contents) is never
# inspected, and a line that is not a JSON object is ignored.
DENIAL_STATUS=0
python3 -I - "$REPORT_FILE" <<'PY' || DENIAL_STATUS=$?
import json
import sys

DENIED_ITEM_STATUSES = {"declined", "rejected"}
ERROR_EVENT_TYPES = {"error", "turn.failed"}


def denied(event):
    item = event.get("item")
    if isinstance(item, dict) and item.get("status") in DENIED_ITEM_STATUSES:
        return True
    if event.get("type") in ERROR_EVENT_TYPES:
        error = event.get("error")
        message = error.get("message") if isinstance(error, dict) else event.get("message")
        if isinstance(message, str) and message.lower().startswith("sandbox denied"):
            return True
    return False


with open(sys.argv[1], encoding="utf-8", errors="replace") as report:
    for line in report:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and denied(event):
            sys.exit(10)
PY
if [[ "$DENIAL_STATUS" -ne 0 ]]; then
  # 10 = a structured denial; anything else means the report could not be
  # classified, which is also non-delivery (fail closed).
  echo "[nexus-enforced] codex_action_denied: a denied action is non-delivery (work copy kept: $WORK_DIR; classifier status $DENIAL_STATUS)" >&2
  exit 4
fi
if [[ "$CODEX_STATUS" -ne 0 ]]; then
  echo "[nexus-enforced] codex exited $CODEX_STATUS (work copy kept: $WORK_DIR)" >&2
  exit "$CODEX_STATUS"
fi
echo "[nexus-enforced] delivered; review the diff in $WORK_DIR, then: git worktree remove $WORK_DIR"
