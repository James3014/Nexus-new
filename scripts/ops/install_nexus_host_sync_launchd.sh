#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT_DEFAULT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_ROOT="${NEXUS_HOST_REPO_ROOT:-$REPO_ROOT_DEFAULT}"
MANIFEST="$REPO_ROOT/scripts/ops/nexus-host-runtime-manifest.json"
SYNC_BIN="${NEXUS_HOST_SYNC_BIN:-$HOME/.local/bin/nexus-host-sync}"
SOURCE_REPO="${NEXUS_HOST_SOURCE_REPO:-$HOME/.cache/nexus-host-sync/Nexus-new.git}"
PLIST="${NEXUS_HOST_SYNC_PLIST:-$HOME/Library/LaunchAgents/com.nexus.host-sync.plist}"
STATE_DIR="${NEXUS_HOST_SYNC_STATE_DIR:-$HOME/.local/state/nexus-host-sync}"
LOAD="${NEXUS_HOST_SYNC_LAUNCHD_LOAD:-1}"

if [[ ! -f "$MANIFEST" ]]; then
  echo "NEXUS_HOST_MANIFEST_MISSING:$MANIFEST" >&2
  exit 1
fi

read -r TRACK_REF INTERVAL < <(
  python3 - "$MANIFEST" <<'PY'
import json, sys
data=json.load(open(sys.argv[1], encoding="utf-8"))
print(data.get("track_ref", "main"), int(data.get("sync_interval_seconds", 900)))
PY
)

mkdir -p "$(dirname "$PLIST")" "$STATE_DIR"
TMP="$PLIST.tmp.$$"
python3 - "$TMP" "$SYNC_BIN" "$SOURCE_REPO" "$STATE_DIR" "$TRACK_REF" "$INTERVAL" <<'PY'
import plistlib, sys
out, sync_bin, source_repo, state_dir, track_ref, interval = sys.argv[1:]
payload = {
    "Label": "com.nexus.host-sync",
    "ProgramArguments": [
        sync_bin,
        "sync",
        "--track-ref",
        track_ref,
        "--source-repo",
        source_repo,
    ],
    "RunAtLoad": True,
    "StartInterval": int(interval),
    "ProcessType": "Background",
    "StandardOutPath": f"{state_dir}/stdout.log",
    "StandardErrorPath": f"{state_dir}/stderr.log",
}
with open(out, "wb") as fh:
    plistlib.dump(payload, fh, sort_keys=True)
PY
python3 - "$TMP" <<'PY_VALIDATE'
import plistlib
import sys

with open(sys.argv[1], "rb") as fh:
    payload = plistlib.load(fh)

if payload.get("Label") != "com.nexus.host-sync":
    raise SystemExit("NEXUS_HOST_SYNC_PLIST_LABEL_MISMATCH")
if not isinstance(payload.get("ProgramArguments"), list):
    raise SystemExit("NEXUS_HOST_SYNC_PLIST_PROGRAM_ARGUMENTS_INVALID")
PY_VALIDATE
mv "$TMP" "$PLIST"

if [[ "$LOAD" == "1" ]]; then
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "NEXUS_HOST_SYNC_LAUNCHD_REQUIRES_DARWIN" >&2
    exit 1
  fi
  DOMAIN="gui/$(id -u)"
  launchctl bootout "$DOMAIN" "$PLIST" >/dev/null 2>&1 || true
  launchctl bootstrap "$DOMAIN" "$PLIST"
  launchctl enable "$DOMAIN/com.nexus.host-sync"
  launchctl kickstart -k "$DOMAIN/com.nexus.host-sync"
fi

echo "NEXUS_HOST_SYNC_LAUNCHD_INSTALLED:$PLIST"
echo "track_ref=$TRACK_REF interval_seconds=$INTERVAL"
