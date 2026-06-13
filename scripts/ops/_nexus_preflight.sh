#!/bin/bash
# 🛡️ Nexus Physical Preflight v28.3.0 Eternal (Self-Healing Enabled)
# Identity: Nexus Battlesuit Environment Alignment Protocol

echo "🛡️ [Preflight] Initiating v28.3.0 Environment Alignment..."

# 1. Path Self-Healing (Atomic Symlinking)
# Preserve the caller's PATH precedence because Gemini CLI auth/session
# behavior is sensitive to helper resolution order. Append fallback paths only.
export PATH="$PATH:/opt/homebrew/bin:/Users/jameschen/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

check_binary() {
    if ! command -v "$1" &> /dev/null; then
        echo "⚠️ [Preflight] Binary '$1' not found in PATH. Attempting discovery..."
        # Heuristic discovery for common Mac paths
        FALLBACKS=("/opt/homebrew/bin/$1" "/usr/local/bin/$1" "/Users/jameschen/.npm-global/bin/$1" "/Users/jameschen/.cargo/bin/$1")
        for fb in "${FALLBACKS[@]}"; do
            if [ -f "$fb" ]; then
                echo "✅ [Preflight] Found '$1' at $fb. Aligning..."
                # In a real hardened scenario, we could symlink here, 
                # but for now, we just ensure the current shell session has it.
                export PATH="$(dirname "$fb"):$PATH"
                return 0
            fi
        done
        echo "❌ [Preflight] Fatal: '$1' is missing. Please install it."
        return 1
    fi
    echo "✅ [Preflight] '$1' detected: $(which "$1")"
    return 0
}

check_binary "node" || exit 1
check_binary "gemini" || exit 1
check_binary "uv" || exit 1

# 2. Nexus CLI Surface Check
echo "🛡️ [Preflight] Checking Nexus CLI integrity..."
if [[ -x ".venv/bin/python" ]]; then
    NEXUS_CLI_SMOKE=(".venv/bin/python" "scripts/engine/nexus_cli.py" "--help")
else
    NEXUS_CLI_SMOKE=("uv" "run" "scripts/engine/nexus_cli.py" "--help")
fi
"${NEXUS_CLI_SMOKE[@]}" > /dev/null 2>&1 && echo "✅ Nexus CLI: PASS" || { echo "❌ Nexus CLI: FAIL"; exit 1; }

# 3. Metadata Collection (v28.3.0 Enhanced)
COMMIT_SHA=$(git rev-parse --short HEAD)
SWARM_COUNT=$(ls -d .nexus-swarm-* 2>/dev/null | wc -l | xargs)
TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

echo "[NEXUS v28.3.0 ACTIVE] Preflight complete at $TIMESTAMP."
echo "  Commit SHA: $COMMIT_SHA"
echo "  50 Swarm Status: $SWARM_COUNT directories ready"
echo "  Environment: PRODUCTION-READY"
