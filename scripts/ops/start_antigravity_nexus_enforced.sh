#!/bin/zsh
# ⚠️ COMPATIBILITY LAYER
# This script is deprecated. Please use start_codex_nexus_enforced.sh instead.
# Redirecting to the new unified runner...

echo "⚠️ [DEPRECATION-WARNING] 'start_antigravity_nexus_enforced.sh' is deprecated."
echo "➡️  Redirecting to 'start_codex_nexus_enforced.sh'..."

exec bash scripts/ops/start_codex_nexus_enforced.sh "$@"
