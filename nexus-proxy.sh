#!/bin/bash
# 🛡️ Nexus 戰甲切換器 v1.1 - [NEXUS v22 ACTIVE]

NEXUS_ROOT="."
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
    echo "[PROTOCOL REMINDER] agent: please read docs/AGENT_MANDATORY_PROTOCOL.md before acting."

# 🚀 執行指令 (版本感知執行)
UV_BIN=$(command -v uv || echo "/Users/jameschen/.local/bin/uv")

# 判斷入口點 (v22 有 engine/nexus_cli.py, v1.5 主要是 scripts/*.py)
if [ -f "scripts/engine/nexus_cli.py" ]; then
    CLI_BIN="scripts/engine/nexus_cli.py"
    CMD_ARGS=("$@")
elif [ -f "scripts/nexus_cli.py" ]; then
    CLI_BIN="scripts/nexus_cli.py"
    CMD_ARGS=("$@")
else
    # 舊版 Baseline 回退到 app.py 或直接說明
    CLI_BIN="scripts/app.py"
    echo "⚠️  注意：舊版戰甲無統一 CLI，嘗試執行 $CLI_BIN 或直接使用 python 腳本。"
    CMD_ARGS=("$@")
fi

if [ "${#CMD_ARGS[@]}" -gt 0 ]; then
    if [ -f "$CLI_BIN" ]; then
        "$UV_BIN" run "$CLI_BIN" "${CMD_ARGS[@]}"
    else
        echo "❌ Error: Entry point $CLI_BIN not found in current armor."
    fi
else
    if [ "$ARMOR" == "v22" ] || [ "$ARMOR" == "rust" ]; then
        "$UV_BIN" run "$CLI_BIN" nexus:status --aos
    else
        echo "ℹ️  Python Baseline 戰甲就緒。可用腳本位於 scripts/ 目錄下。"
    fi
fi

# 🛡️ 身份驗證與驗收回報 (版本感知)
CURRENT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "UNKNOWN")
if [ -f "scripts/ops/ci_gate.py" ]; then
    CI_STATUS=$("$UV_BIN" run scripts/ops/ci_gate.py --dry-run 2>/dev/null | head -1)
else
    CI_STATUS="N/A (Legacy Baseline)"
fi
echo "[NEXUS IDENTITY: $CURRENT_SHA | CI: ${CI_STATUS:-'PENDING'}]"
