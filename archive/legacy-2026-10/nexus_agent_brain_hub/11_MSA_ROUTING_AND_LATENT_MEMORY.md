# 🧬 MSA Routing & Latent Memory Architecture
**[PHYSICAL_STATUS: CORE_WIRED | PRODUCTION_BETA]**

## 1. 核心接線與強制力
MSA Routing 已正式整合至 `nexus/core/router.py -> SkillsRouter` 中，不再是純沙盒 POC。

## ⚙️ 實體化接線細節
- **激活開關**: `NEXUS_MSA_ENABLED=1`。
- **Fail-Closed 門檻**: 0.75。若 `MSARouter` 分數未達標，強制回傳 `UNKNOWN`。
- **雙模檢索 (Dual-Mode Search)**:
    1. **Palace Search (Tier 0)**: 優先搜尋治理規約，保證倫理優先。
    2. **MSA Search (Tier 1)**: 若 Palace 未命中，啟動全量代碼語義路由。
- **動態裝載**: 採 `importlib` 物理隔離實驗模組，核心與實驗區解耦。

## 2. 實體組件
- **Retriever**: `nexus.experiments.msa_routing.msa_indexer.LanceDBRetriever`。
- **Router**: `nexus.experiments.msa_routing.msa_router_contract.MSARouter`。

## 🚧 待完成優化
- **非同步化**: 目前部分檢索路徑仍為同步，需全面遷移至 `httpx.AsyncClient`。

---
**[Source: Truth Realignment Audit Stage 3 - 2026-04-20]**
