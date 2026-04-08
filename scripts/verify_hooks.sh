#!/bin/bash

# --- CONFIG ---
WORKSPACE_ROOT="."
GEMINI_BIN="/Users/jameschen/.npm-global/bin/gemini"
OPENCLAW_BIN="/Users/jameschen/.npm-global/bin/openclaw"
OC_WORKSPACE="/Users/jameschen/.openclaw/workspace"

echo "[*] Nexus Armor Physical Verification Starting..."

# 1. Check Gemini Hook (.gemini/GEMINI.md)
echo -n "[1/4] Checking Gemini Local Hook... "
if [ -f "$WORKSPACE_ROOT/.gemini/GEMINI.md" ]; then
    echo "✅ FOUND"
else
    echo "❌ MISSING"
    mkdir -p "$WORKSPACE_ROOT/.gemini"
    cp "$WORKSPACE_ROOT/GEMINI.md" "$WORKSPACE_ROOT/.gemini/GEMINI.md" 2>/dev/null
    echo "   -> FIXED: Deployed to .gemini/GEMINI.md"
fi

# 2. Check OpenClaw SOUL Anchor
echo -n "[2/4] Checking OpenClaw Global SOUL... "
if [ -f "$OC_WORKSPACE/SOUL.md" ]; then
    echo "✅ FOUND"
else
    echo "❌ MISSING (Copying to global workspace: $OC_WORKSPACE)"
    mkdir -p "$OC_WORKSPACE"
    cp "$WORKSPACE_ROOT/SOUL.md" "$OC_WORKSPACE/SOUL.md"
    cp "$WORKSPACE_ROOT/MEMORY.md" "$OC_WORKSPACE/MEMORY.md"
    echo "   -> FIXED: Deployed to global workspace."
fi

# 3. Check Protocol SSOT Link
echo -n "[3/4] Checking MUSE_PROTO.md Symlink... "
if [ -L "$WORKSPACE_ROOT/MUSE_PROTO.md" ]; then
    echo "✅ VERIFIED (Symlink Live)"
else
    echo "❌ MISSING OR NOT A SYMLINK"
fi

# 4. Check Root Protocol Content
echo -n "[4/4] Checking Felo-First Protocol... "
grep -q "FELO_FIRST = TRUE" "/Users/jameschen/Downloads/obsidian/MUSE_PROTO.md" && echo "✅ VERIFIED (PROTOCOL ACTIVE)"

echo "[*] Verification Complete."
