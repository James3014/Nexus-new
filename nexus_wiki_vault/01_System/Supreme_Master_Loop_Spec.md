---
aliases: '[P-X-D-R-A-C, Master Loop Spec]'
confidence: high
last_compiled: '2026-04-20'
owner: agent
status: production
tags: '[core, architecture, loop]'
title: Supreme Master Loop Specification
---

# 🧬 Supreme Master Loop (P-X-D-R-A-C)

## 🛡️ 核心定義
Supreme Master Loop 已進入 **Production** 階段。它將開發與治理統合成一個具備自律性、強檢核性、且 L4/L3 邊界嚴格定義的「大閉環」。

在架構實體上，它由兩層組成：
1. **L4 Campaign Orchestrator (`campaign_master_loop`)**: 負責 DAG 並行排程、多節點分發與全域里程碑（Milestone）管控。
2. **L3 Task Pipeline (`NexusPipeline`)**: 負責執行單一節點（Node）的 **P-X-D-R-A-C 六階段** 閉環，將開發與治理統合成實體檢核。

## ⚙️ 六大階段 (The 6 Phases)

### Phase 1: Plan (P) - 戰略拆解
- 使用 `CampaignGeneral` 將模糊意圖拆解為任務圖 (DAG)。
- 定義 `StrategicEnvelope` 傳遞戰略封套與全域約束。

### Phase 2: eXecute (X) - 實體執行
- 委派 `TacticalDrone` 在物理沙盒中執行代碼修改。
- 監控 `Sense-Think-Act` 循環，確保符合 `DroneProtocol`。

### Phase 3: Document (D) - 同步紀錄
- 強制更新 `Governance Changelog` 與 `Learning Matrix`。
- 實作 Wiki 與 Git 歷史的物理對位。

### Phase 4: Review (R) - 邏輯審查
- 觸發 `Codex Challenge` (對抗性審查) 或跨模型 A/B 邏輯檢驗。

### Phase 5: Audit (A) - 物理審計
- 執行 `acceptance-check` 並讀取 `hallucination_evidence.json`。
- 計算 `Hallucination Index (HI)` 分數，低於門檻者阻斷。

### Phase 6: Closeout (C) - 晉升結案
- 簽署 `Task Contract Seal`。
- 執行 `Atomic Promotion` 將影子補丁正式晉升至主線。

## ⚙️ 技術實作 (Implementation)
- **Commander**: `nexus/core/campaign_general.py` (L4 指揮官層)。
- **Runner**: `nexus/core/cli_runner_async.py` (非同步執行主循環)。
- **Hardening**: 已實作 `1-bit Core (OneBitGate)` 進行節點晉升判定。
- **Interface**: `scripts/engine/nexus_cli.py nexus run`。

---
**[Source: nexus_wiki_vault/01_System/Supreme_Master_Loop_Spec.md]**
