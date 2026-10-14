#!/bin/bash
# Install the unattended MCP Gateway auto-deployer (#2153).  The Owner runs this
# once; agents cannot (the auto-mode classifier blocks launchd bootstrap).
#
#   bash scripts/ops/install_nexus_gateway_auto_deploy.sh            # install + load
#   bash scripts/ops/install_nexus_gateway_auto_deploy.sh --dry-run  # print plan only
#
# 1. Fetch main into the existing Gateway bare repository and check it out as a
#    bootstrap worktree (gateway-direct/auto-deploy-bootstrap).
# 2. Point gateway-direct/auto-deploy-current at it.  Every successful deploy
#    moves that link to the new deployment, so the deployer updates itself.
# 3. Write and load the LaunchAgent com.nexus.gateway-auto-deploy, which runs
#    one deploy cycle every INTERVAL seconds.
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
STATE_DIR="${NEXUS_GATEWAY_AUTO_DEPLOY_STATE_DIR:-$HOME/.local/state/nexus-gateway-auto-deploy}"
PYTHON="${NEXUS_GATEWAY_AUTO_DEPLOY_PYTHON:-$(cd / && uv python find --no-project 3.12)}"
INTERVAL="${NEXUS_GATEWAY_AUTO_DEPLOY_INTERVAL:-300}"
GH_BIN="${NEXUS_GATEWAY_AUTO_DEPLOY_GH:-$(command -v gh || echo gh)}"
LOAD="${NEXUS_GATEWAY_AUTO_DEPLOY_LAUNCHD_LOAD:-1}"
DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "NEXUS_GATEWAY_AUTO_DEPLOY_PYTHON_TOO_OLD")'

if [[ "$DRY_RUN" == "1" ]]; then
  echo "would check out main from $BARE at $BOOTSTRAP (unless NEXUS_GATEWAY_AUTO_DEPLOY_TOOL_ROOT is set)"
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
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -c 'import ast, sys; ast.parse(open(sys.argv[1]).read())' "$DEPLOYER"

mkdir -p "$GATEWAY_ROOT" "$(dirname "$PLIST")" "$STATE_DIR"
ln -sfn "$TOOL_ROOT" "$LINK.tmp.$$"
mv -f "$LINK.tmp.$$" "$LINK"

PLIST_TMP="$PLIST.tmp.$$"
"$PYTHON" - "$PLIST_TMP" "$LABEL" "$PYTHON" "$LINK" "$GH_BIN" "$STATE_DIR" "$INTERVAL" <<'PY'
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
        "NEXUS_GATEWAY_PLIST": os.path.expanduser(
            "~/Library/LaunchAgents/com.nexus.mcp.gateway.direct.plist"
        ),
    },
    "StandardOutPath": f"{state_dir}/stdout.log",
    "StandardErrorPath": f"{state_dir}/stderr.log",
}
with open(out, "wb") as fh:
    plistlib.dump(payload, fh, sort_keys=True)
with open(out, "rb") as fh:
    if plistlib.load(fh).get("Label") != label:
        raise SystemExit("NEXUS_GATEWAY_AUTO_DEPLOY_PLIST_LABEL_MISMATCH")
PY
mv "$PLIST_TMP" "$PLIST"

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
