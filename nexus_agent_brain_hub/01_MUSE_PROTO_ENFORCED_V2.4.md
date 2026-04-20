# 🛡️ MUSE_PROTO v2.4 (Production-Hardened)

## 0) 核心使命
本規約強制 Agent 進入「可驗證、可回溯、可治理」的生產模式。**任何繞過 Gate 的行為均被視為幻覺違規。**

## 1) 強制執行原則 (The Iron Laws)
1. **Behavioral Integrity**: 功能必須經過物理驗證 (tests)。目前的驗證由 **1-bit Core (OneBitGate)** 強制執行，任何未通過測試的節點將被阻斷晉升。
2. **Evidence-Driven**: 任何「完成」宣告必須附帶 `command_artifacts` 與真實輸出。
3. **No-Shadow-Edits**: 禁止在任務邊界外進行無關的代碼重構。
4. **Fail-to-Lesson**: 每次失敗必須回寫至 `Learning Closure Matrix`。

## 2) 必載環境
- **CLI**: `uv run scripts/engine/nexus_cli.py`
- **Preflight**: `bash scripts/ops/_nexus_preflight.sh`
- **GBNF Check**: `LocalBonsaiBrain` 會對所有的 Drone 輸出進行 GBNF 結構化校驗。

## 3) 任務路由決策 (Routing)
- **Baseline**: 標準任務，無回歸風險。
- **Hyper**: 需快速迭代的垂直切片。
- **NightShift**: 跨模組任務，需啟用 `Distributed Lock` 與長循環回歸防護。

## 4) 身份標記
- **開頭**: `[NEXUS v24 ACTIVE]`
- **結尾**: `[NEXUS IDENTITY: <SHA> + v0.7 PRODUCTION-READY]`

---
**[Source: nexus_wiki_vault/01_System/MUSE_PROTO.md]**
