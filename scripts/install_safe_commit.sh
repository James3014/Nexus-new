#!/bin/bash
# One-click Safe-Commit hook setup for Codex-Loop

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
if [ -z "$REPO_ROOT" ]; then
    echo "❌ Error: Not inside a git repository."
    exit 1
fi

HOOK_PATH="$REPO_ROOT/.git/hooks/pre-commit"

echo "Creating hook at: $HOOK_PATH"

cat <<EOF > "$HOOK_PATH"
#!/bin/bash
# Codex-Loop Safe-Commit Guard
codex-loop --mode safe-commit
EOF

chmod +x "$HOOK_PATH"
echo "✅ Safe-Commit hook successfully installed."
echo "💡 Your next commits will be audited by Codex-Loop."
