# 🧬 Supreme Master Loop (P-X-D-R-A-C)
**[PHYSICAL_STATUS: PRODUCTION | SEAM_HARDENED]**

## 🛡️ 核心定義
Supreme Master Loop 已進入 **Production** 階段。它將開發與治理統合成一個具備自律性、強檢核性、且 L4/L3 邊界由 **Canonical Seam** 嚴格隔離。

## ⚙️ 分層架構與縫合點 (The Seam)
1. **L4 Campaign Orchestrator (`campaign_master_loop`)**: 負責 DAG 排程。
2. **The Seam (`execute_tactical_node`)**: L4 對 L3 的唯一授權接口。
3. **L3 Task Pipeline (`NexusPipeline`)**: 負責執行 **P-X-D-R-A-C**。

## ⚙️ 核心流程對位 (April 22 Update)
- **Hard Seam**: 移除所有 Legacy Fallback，禁止 L4 直接操作檔案。
- **Cold-Start**: 支援 `UNVERIFIED_COLD_START` 狀態，由 `scripts/engine/nexus_cli.py` 進行動態阻斷判定。

## 🛡️ 技術實作
- **Hardening**: `1-bit Core (OneBitGate)` 晉升判定。
- **Acceptance**: `Hallucination Index (HI)` 與冷啟動政策連動。

---
**[Source: nexus/engine/cli_runner_async.py | v24.2-ALIGNED]**
