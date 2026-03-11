#!/bin/bash
# 🛡️ Codex-Loop 2.0 (Lvl 16 Cognitive Loop)
# Muse-Core 的強制跨模型程式碼防護鎖 - 基於 Python Brain 的認知閉環版本
# 支援 Inner Loop 錯誤報告匯出至 /tmp/codex_loop_report.md
# 🛡️ SSoT: Relocatable Public Version
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRAIN_SCRIPT="${SCRIPT_DIR}/codex_loop_brain.py"

python3 "$BRAIN_SCRIPT" "$@"
