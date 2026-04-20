# 🖥️ CLI Surface & Command Maps
**[PHYSICAL_STATUS: FULLY_OPERATIONAL | SSOT_CONFIGURED]**

## 1. 統一入口與配置歸一
Nexus 的所有操作必須經由 `nexus_cli.py` 進行。全域配置由 `NexusGlobalConfig` 統一管控。

## ⚙️ 實體指令圖譜 (Command Map)

| 指令類別 | 指令示例 (nexus <cmd>) | 實體職能 |
|---|---|---|
| **核心循環** | `run`, `resume` | 啟動或恢復 P-X-D-R-A-C 大閉環。 |
| **治理守門** | `acceptance-check` | 執行 9 分制 HI 審計與證據驗收。 |
| **發布硬化** | `delivery-gate`, `closeout`| 產出交付憑證並封裝任務契約。 |
| **集群監控** | `drone-hud`, `swarm` | 實時監控多 Agent 狀態與 mTLS 機群。 |
| **研究實驗** | `research:run`, `bench` | 啟動沙盒實驗與 A/B 基準測試。 |

## ⚙️ 核心配置 (NexusGlobalConfig)
- **SSoT**: 所有環境變數（如 `NEXUS_OLLAMA_ENDPOINT`, `NEXUS_SSE_PORT`）均在此歸一。
- **Exit Codes**: 對齊 `nexus/core/exit_codes.py` 四態終端語意（0:SUCCESS, 1:FAILED, 2:ESCALATED, 3:HUMAN_REVIEW）。

---
**[Source: Truth Realignment Audit Stage 9 - 2026-04-20]**
