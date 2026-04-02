#!/bin/bash
# 🛡️ Nexus 戰甲切換器 v1.1 - [NEXUS v22 ACTIVE]

NEXUS_ROOT="/Users/jameschen/Workspace/nexus"
ARMOR=${1:-"v22"}

# 預設行為：若無指令則回報 status
if [ "$#" -gt 0 ]; then
    shift
fi

case $ARMOR in
  "python"|"baseline"|"v1.5")
    TARGET_DIR="$NEXUS_ROOT/legacy_baseline"
    ARMOR_LABEL="PYTHON BASELINE ARMOR ACTIVE"
    SHA_REF="84ab129"
    ;;
  "rust"|"v22"|"main")
    TARGET_DIR="$NEXUS_ROOT"
    ARMOR_LABEL="RUST V22 ARMOR ACTIVE"
    SHA_REF="a866b0b"
    ;;
  *)
    echo "Usage: nexus [python|v22] [command]"
    exit 1
    ;;
esac

if [ ! -d "$TARGET_DIR" ]; then
    echo "❌ Error: Target directory $TARGET_DIR not found."
    exit 1
fi

cd "$TARGET_DIR" || exit 1
echo "[$ARMOR_LABEL] @ $SHA_REF"

# 🚀 執行指令 (強制透過 uv run)
UV_BIN=$(command -v uv || echo "/Users/jameschen/.local/bin/uv")

if [ "$#" -gt 0 ]; then
    "$UV_BIN" run scripts/engine/nexus_cli.py "$@"
else
    "$UV_BIN" run scripts/engine/nexus_cli.py nexus:status --aos
fi

# 🛡️ 身份驗證與驗收回報
CURRENT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "UNKNOWN")
CI_STATUS=$("$UV_BIN" run scripts/ops/ci_gate.py --dry-run 2>/dev/null | head -1)
echo "[NEXUS IDENTITY: $CURRENT_SHA | CI: ${CI_STATUS:-'PENDING'}]"
