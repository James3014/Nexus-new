#!/bin/bash
# 🛡️ Nexus-Reflex Universal Installer
# "Give your Agent an Arm."

set -e

# Colors for the glory of Nexus
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}// Nexus-Reflex [SOTA 10/10] Initializing...${NC}"

# Detect OS
OS="$(uname -s)"
ARCH="$(uname -m)"
echo "// Environment: $OS ($ARCH)"

# Installation Targets
OPENCLAW_SKILLS_DIR="$HOME/.openclaw/skills/nexus-reflex"
BIN_DEST="/usr/local/bin/nexus-reflex"

# 1. Create OpenClaw Skill Structure
echo "// Packaging for OpenClaw synergy..."
mkdir -p "$OPENCLAW_SKILLS_DIR/scripts"

# 2. Deployment (In a real public version, this would be a curl to GitHub Releases)
# For now, we sync the current local build to the skill directory
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$REPO_ROOT/target/debug/nexus-reflex-core" ]; then
    cp "$REPO_ROOT/target/debug/nexus-reflex-core" "$OPENCLAW_SKILLS_DIR/scripts/"
    cp "$REPO_ROOT/SKILL.md" "$OPENCLAW_SKILLS_DIR/"
    echo -e "${GREEN}// Nexus-Reflex Binary Deployed to OpenClaw Skills.${NC}"
else
    echo -e "${RED}// Error: Binary not found. Please run 'cargo build' first.${NC}"
    exit 1
fi

# 3. Finalize
echo -e "${BLUE}---${NC}"
echo -e "${GREEN}// Nexus-Reflex: Global Physical Reflexes Engaged.${NC}"
echo "// Use 'nexus-reflex' to command your reality."
