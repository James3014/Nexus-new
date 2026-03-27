#!/bin/bash
# [Nexus Singularity v30.9] Portable Fast-Entry Wrapper
# Usage: ./nexus.sh [HUB_URL]

# Get the directory where this script is located (Bash/Zsh compatible)
if [ -n "$BASH_SOURCE" ]; then
    SCRIPT_PATH="$BASH_SOURCE"
elif [ -n "$ZSH_VERSION" ]; then
    SCRIPT_PATH="${(%):-%x}"
else
    SCRIPT_PATH="$0"
fi
SCRIPT_DIR="$( cd "$( dirname "$SCRIPT_PATH" )" &> /dev/null && pwd )"
HUB_URL=${1:-"http://127.0.0.1:5001"}

echo "// Nexus: Initializing Singularity Link..."
echo "// Hub: $HUB_URL"

export NEXUS_HUB_URL=$HUB_URL
export PYTHONIOENCODING=utf-8

# Use relative path to find the CLI script
CLI_PATH="$SCRIPT_DIR/nexus_pilot_cli.py"

# Check for 'uv' and use it to run the CLI with dependencies
if command -v uv &> /dev/null; then
    uv run --with rich --with requests python3 "$CLI_PATH"
else
    # Fallback if uv is not on path but maybe in local bin?
    UV_PATH="/Users/jameschen/.local/bin/uv"
    if [ -f "$UV_PATH" ]; then
        "$UV_PATH" run --with rich --with requests python3 "$CLI_PATH"
    else
        echo "// [WARNING] 'uv' not found. Attempting standard python3..."
        echo "// [TIP] For best experience, install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
        python3 "$CLI_PATH"
    fi
fi
