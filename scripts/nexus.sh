#!/bin/bash
# [Nexus Singularity v30.7] Fast-Entry Wrapper
# Usage: ./nexus [HUB_URL]

HUB_URL=${1:-"http://127.0.0.1:5001"}

echo "// Nexus: Connecting to Singularity Hub at $HUB_URL..."

export NEXUS_HUB_URL=$HUB_URL
export PYTHONIOENCODING=utf-8
/Users/jameschen/.local/bin/uv run --with rich --with requests python3 /Users/jameschen/Workspace/nexus/scripts/nexus_chat_cli.py
