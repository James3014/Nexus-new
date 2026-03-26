#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${NEXUS_PILOT_VENV:-$HOME/.nexus-pilot/venv}"

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
