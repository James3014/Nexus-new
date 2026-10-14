#!/bin/bash
# Install the unattended MCP Gateway auto-deployer (#2153).  The Owner runs this
# once; agents cannot (the auto-mode classifier blocks launchd bootstrap).
#
#   bash scripts/ops/install_nexus_gateway_auto_deploy.sh            # install + load
#   bash scripts/ops/install_nexus_gateway_auto_deploy.sh --dry-run  # print plan only
#
# 1. Fetch main into the existing Gateway bare repository and check it out as a
#    bootstrap worktree (gateway-direct/auto-deploy-bootstrap).
# 2. Verify that commit with the deployer's own `verify-commit` (GitHub main tip
#    or ancestor, all required checks green); stop on any failure.
# 3. Point gateway-direct/auto-deploy-current at it (atomic rename).  Every
#    successful deploy moves that link to the new deployment once the new
#    tree's deployer passes `selftest`, so the deployer updates itself.
# 4. `adopt` the current live Gateway plist on first install: the deployer
#    refuses to switch away from a plist it did not write or adopt
#    (FOREIGN_PLIST -> HOLD).  On a re-run, a live plist the deployer does not
#    know (a manual rebind) is only accepted with `--adopt`.
# 5. Write and load the LaunchAgent com.nexus.gateway-auto-deploy, which runs
#    one deploy cycle every INTERVAL seconds.
# Re-running the installer is safe and idempotent.
#
# Before any manual #526 rebind: `hold`; afterwards `adopt` and `release`.
# It does not touch com.nexus.mcp.gateway.direct; the deployer does that itself,
# only after a candidate passes the spare-port probe.
#
# Pause:   <python> "$LINK/scripts/ops/nexus_gateway_auto_deploy.py" hold --reason "..."
# Resume:  <python> "$LINK/scripts/ops/nexus_gateway_auto_deploy.py" release
# Status:  <python> "$LINK/scripts/ops/nexus_gateway_auto_deploy.py" status
# (or create ~/.local/state/nexus-gateway-auto-deploy/HOLD by hand)
set -euo pipefail

LABEL="com.nexus.gateway-auto-deploy"
GATEWAY_ROOT="${NEXUS_GATEWAY_AUTO_DEPLOY_GATEWAY_ROOT:-$HOME/Library/Application Support/Nexus/gateway-direct}"
BARE="$GATEWAY_ROOT/repository.git"
BOOTSTRAP="$GATEWAY_ROOT/auto-deploy-bootstrap"
LINK="$GATEWAY_ROOT/auto-deploy-current"
# Test/override hook: use this tree instead of a bootstrap worktree.
TOOL_ROOT="${NEXUS_GATEWAY_AUTO_DEPLOY_TOOL_ROOT:-}"
PLIST="${NEXUS_GATEWAY_AUTO_DEPLOY_PLIST:-$HOME/Library/LaunchAgents/$LABEL.plist}"
GATEWAY_PLIST="${NEXUS_GATEWAY_AUTO_DEPLOY_GATEWAY_PLIST:-$HOME/Library/LaunchAgents/com.nexus.mcp.gateway.direct.plist}"
STATE_DIR="${NEXUS_GATEWAY_AUTO_DEPLOY_STATE_DIR:-$HOME/.local/state/nexus-gateway-auto-deploy}"
PYTHON="${NEXUS_GATEWAY_AUTO_DEPLOY_PYTHON:-$(cd / && uv python find --no-project 3.12)}"
INTERVAL="${NEXUS_GATEWAY_AUTO_DEPLOY_INTERVAL:-300}"
GH_BIN="${NEXUS_GATEWAY_AUTO_DEPLOY_GH:-$(command -v gh || echo gh)}"
LOAD="${NEXUS_GATEWAY_AUTO_DEPLOY_LAUNCHD_LOAD:-1}"
DRY_RUN=0
ADOPT=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --adopt) ADOPT=1 ;;
    *) echo "usage: $0 [--dry-run] [--adopt]" >&2; exit 2 ;;
  esac
done

"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "NEXUS_GATEWAY_AUTO_DEPLOY_PYTHON_TOO_OLD")'

if [[ "$DRY_RUN" == "1" ]]; then
  echo "would check out main from $BARE at $BOOTSTRAP (unless NEXUS_GATEWAY_AUTO_DEPLOY_TOOL_ROOT is set)"
  echo "would verify that commit (GitHub main + required checks) and adopt $GATEWAY_PLIST"
  echo "would point $LINK at it"
  echo "would write $PLIST (python=$PYTHON interval=${INTERVAL}s gh=$GH_BIN state=$STATE_DIR)"
  echo "would load gui/$(id -u)/$LABEL"
  exit 0
fi

if [[ -z "$TOOL_ROOT" ]]; then
  git --git-dir "$BARE" fetch --quiet --no-tags origin "+refs/heads/main:refs/nexus-auto-deploy/main"
  COMMIT="$(git --git-dir "$BARE" rev-parse 'refs/nexus-auto-deploy/main^{commit}')"
  if [[ -e "$BOOTSTRAP" ]]; then
    git --git-dir "$BARE" worktree remove --force "$BOOTSTRAP"
  fi
  git --git-dir "$BARE" worktree add --detach "$BOOTSTRAP" "$COMMIT"
  TOOL_ROOT="$BOOTSTRAP"
fi
DEPLOYER="$TOOL_ROOT/scripts/ops/nexus_gateway_auto_deploy.py"
if [[ ! -f "$DEPLOYER" ]]; then
  echo "NEXUS_GATEWAY_AUTO_DEPLOY_SOURCE_MISSING:$DEPLOYER" >&2
  exit 1
fi
if [[ -n "$(git -C "$TOOL_ROOT" status --porcelain)" ]]; then
  echo "NEXUS_GATEWAY_AUTO_DEPLOY_TOOL_TREE_DIRTY:$TOOL_ROOT" >&2
  exit 1
fi
TOOL_COMMIT="$(git -C "$TOOL_ROOT" rev-parse HEAD)"
export PYTHONDONTWRITEBYTECODE=1
if ! "$PYTHON" "$DEPLOYER" verify-commit "$TOOL_COMMIT" --gh "$GH_BIN"; then
  echo "NEXUS_GATEWAY_AUTO_DEPLOY_TOOL_COMMIT_NOT_VERIFIED:$TOOL_COMMIT" >&2
  exit 1
fi
"$PYTHON" "$DEPLOYER" selftest --state-dir "$STATE_DIR"

mkdir -p "$GATEWAY_ROOT" "$(dirname "$PLIST")" "$STATE_DIR"
if [[ -f "$GATEWAY_PLIST" ]]; then
  ADOPT_FLAGS=(--adopt-if-unrecorded)
  if [[ "$ADOPT" == "1" ]]; then
    ADOPT_FLAGS=()
  fi
  if ! "$PYTHON" "$DEPLOYER" adopt "${ADOPT_FLAGS[@]+"${ADOPT_FLAGS[@]}"}" --plist "$GATEWAY_PLIST" --state-dir "$STATE_DIR"; then
    echo "NEXUS_GATEWAY_AUTO_DEPLOY_PLIST_UNKNOWN: the live Gateway plist was not written or adopted by the deployer; re-run with --adopt to accept it" >&2
    exit 1
  fi
else
  echo "NEXUS_GATEWAY_AUTO_DEPLOY_GATEWAY_PLIST_MISSING:$GATEWAY_PLIST (nothing adopted)" >&2
fi
# Atomic, idempotent link replacement (`ln -sfn tmp; mv -f tmp LINK` would move
# the temporary link *into* an existing directory link).
"$PYTHON" - "$TOOL_ROOT" "$LINK" <<'PY'
import os, sys
target, link = sys.argv[1:]
tmp = f"{link}.tmp.{os.getpid()}"
if os.path.lexists(tmp):
    os.unlink(tmp)
os.symlink(target, tmp)
os.replace(tmp, link)
PY


GATEWAY_PLIST="$GATEWAY_PLIST" "$PYTHON" - "$PLIST" "$LABEL" "$PYTHON" "$LINK" "$GH_BIN" "$STATE_DIR" "$INTERVAL" <<'PY'
import os, plistlib, sys
out, label, python, link, gh, state_dir, interval = sys.argv[1:]
payload = {
    "Label": label,
    "ProgramArguments": [
        python, f"{link}/scripts/ops/nexus_gateway_auto_deploy.py",
        "run", "--gh", gh, "--state-dir", state_dir,
    ],
    "RunAtLoad": True,
    "StartInterval": int(interval),
    "ProcessType": "Background",
    "EnvironmentVariables": {
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": os.path.expanduser("~"),
        "PYTHONDONTWRITEBYTECODE": "1",
        # The durable manager derives the Gateway plist from this (out-of-process switch).
        "NEXUS_GATEWAY_PLIST": os.environ["GATEWAY_PLIST"],
    },
    "StandardOutPath": f"{state_dir}/stdout.log",
    "StandardErrorPath": f"{state_dir}/stderr.log",
}
tmp = f"{out}.tmp.{os.getpid()}"
with open(tmp, "wb") as fh:
    plistlib.dump(payload, fh, sort_keys=True)
with open(tmp, "rb") as fh:
    if plistlib.load(fh).get("Label") != label:
        os.unlink(tmp)
        raise SystemExit("NEXUS_GATEWAY_AUTO_DEPLOY_PLIST_LABEL_MISMATCH")
os.replace(tmp, out)
PY

if [[ "$LOAD" == "1" ]]; then
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "NEXUS_GATEWAY_AUTO_DEPLOY_LAUNCHD_REQUIRES_DARWIN" >&2
    exit 1
  fi
  DOMAIN="gui/$(id -u)"
  launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
  launchctl bootstrap "$DOMAIN" "$PLIST"
  launchctl enable "$DOMAIN/$LABEL"
fi

echo "NEXUS_GATEWAY_AUTO_DEPLOY_INSTALLED:$PLIST"
echo "deployer=$LINK -> $TOOL_ROOT python=$PYTHON"
