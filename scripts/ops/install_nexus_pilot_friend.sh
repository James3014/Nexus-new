#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT_DEFAULT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_ROOT="${NEXUS_PILOT_REPO_ROOT:-$REPO_ROOT_DEFAULT}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${NEXUS_PILOT_VENV:-$HOME/.nexus-pilot/venv}"

if [[ ! -f "$REPO_ROOT/pyproject.toml" && ! -f "$REPO_ROOT/setup.py" ]]; then
  cat <<EOF
[Nexus] Install failed: invalid repo root
  resolved REPO_ROOT = $REPO_ROOT
  expected pyproject.toml or setup.py in that directory

Fix options:
  1) Run installer from a full Nexus repository checkout:
     bash /path/to/nexus/scripts/ops/install_nexus_pilot_friend.sh

  2) Or explicitly set repo root:
     NEXUS_PILOT_REPO_ROOT=/path/to/nexus \\
       bash /path/to/install_nexus_pilot_friend.sh
EOF
  exit 1
fi

echo "[Nexus] Installing Nexus Pilot Friend CLI..."
rm -rf "$VENV_DIR"
"$PYTHON_BIN" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || true
"$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel
"$VENV_DIR/bin/pip" install --no-build-isolation -e "$REPO_ROOT"

mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/nexus-pilot-friend" <<EOF
#!/bin/bash
exec "$VENV_DIR/bin/nexus-pilot-friend" "\$@"
EOF
chmod +x "$HOME/.local/bin/nexus-pilot-friend"

cat > "$HOME/.local/bin/nexus-pilot" <<EOF
#!/bin/bash
exec "$VENV_DIR/bin/nexus-pilot" "\$@"
EOF
chmod +x "$HOME/.local/bin/nexus-pilot"

echo "[Nexus] Installed."
echo "[Nexus] Ensure ~/.local/bin is on PATH."
echo "[Nexus] Start with: nexus-pilot-friend pilot_a"
