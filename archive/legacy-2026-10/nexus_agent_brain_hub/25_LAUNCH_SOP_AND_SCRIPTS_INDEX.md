# 🚀 Launch SOP & Operational Scripts
**[PHYSICAL_STATUS: ENFORCED_ENTRY | SENSORY_ACTIVE]**

## 1. 啟動入口規範 (Entrypoints)
Nexus 嚴禁「裸執行」。所有的 Agent 會話必須經由啟動腳本進入，以載入預檢環境。

## ⚙️ 標準啟動流程 (SOP)
1. **Preflight**: 檢查 `node`, `uv`, `git` 與 `lancedb` 狀態。
2. **Briefing**: 強制顯示任務契約與 `MUSE_PROTO`。
3. **Execution**: 在隔離沙盒執行，紀錄 TraceID。
4. **Audit**: 自動觸發 `acceptance-check` 並計算 HI 分數。
5. **Sync**: 使用 `[wiki:auto-gen]` 同步治理紀錄。

## ⚙️ 核心腳本索引 (Sensory Organs)

| 腳本 | 分類 | 作用 |
|---|---|---|
| `ci_gate.py` | 門禁 | 並行化的發布終極守門員。 |
| `wiki_sync_check.py` | 紀錄 | 具備語義合成能力的紀錄同步器。 |
| `_nexus_preflight.sh` | 環境 | Runtime 環境硬化預檢。 |
| `task_contract_guard.py` | 契約 | 監控變更是否超出合約邊界。 |

---
**[Source: New Dimension Audit Batch E - 2026-04-20]**
