# 🛡️ MUSE_PROTO v2.4 (Production-Hardened)
**[PHYSICAL_STATUS: ENFORCED | GBNF_WIRED]**

## 0) 核心使命
本規約強制 Agent 進入「可驗證、可回溯、可治理」的生產模式。任何繞過 Gate 的行為均被視為幻覺違規。

## 1) 強制執行原則 (The Iron Laws)
1. **Behavioral Integrity**: 功能必須經過物理驗證 (tests)。目前驗證由 **1-bit Core (OneBitGate)** 強制執行，未通過測試的節點將被阻斷晉升。
2. **Evidence-Driven**: 任何「完成」宣告必須附帶 `command_artifacts` 與真實輸出。
3. **No-Shadow-Edits**: 禁止在任務邊界外進行無關的代碼重構。
4. **Fail-to-Lesson**: 每次失敗必須回寫至 `Learning Closure Matrix`。
5. **No print()**: 核心代碼禁止使用 `print()`，必須對齊 `logging` 體系。

## 2) 必載環境
- **CLI**: `uv run scripts/engine/nexus_cli.py`
- **Preflight**: `bash scripts/ops/_nexus_preflight.sh`
- **GBNF Check**: 模型輸出必須嚴格遵守 `drone_engine.py` 定義的 GBNF 結構化語法。

## 3) 任務路由決策 (Routing)
- **Baseline**: 標準任務，無回歸風險。
- **Hyper**: 需快速迭代的垂直切片。
- **NightShift**: 跨模組任務，需啟用 `Distributed Lock` 與長循環回歸防護。

---
**[NEXUS IDENTITY: e148a212 + v28.0 PRODUCTION-READY]**
