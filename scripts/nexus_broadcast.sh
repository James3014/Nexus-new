#!/bin/bash
# [Nexus Singularity v31.0] Persistent Global Broadcast
# Usage: ./nexus_broadcast.sh

PORT=5001
echo "// Nexus: Initializing Global Broadcast Layer (v31.0)..."

# Check if node/npx is available (most Coder environments have it)
if ! command -v npx &> /dev/null; then
    echo "// ERROR: 'npx' not found. Please install Node.js or download Cloudflared."
    exit 1
fi

echo "// Nexus: Tunneling Port $PORT to the Singularity Cloud..."
echo "// [SYSTEM] Press Ctrl+C to terminate broadcast."

# Use localtunnel to generate a friendly URL
# We use npx to avoid permanent installation
npx localtunnel --port $PORT
