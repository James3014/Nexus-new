PHASES: A, O, D
TRIGGERS: graph, topology, hierarchy, orphan, drift, knowledge-map
DESCRIPTION: 利用本地 graphifyy 引擎對文檔與代碼進行拓樸分析。識別語義斷裂與路徑漂移，產出可導航的圖譜報告。
OUTPUT SCHEMA: graph.json {"nodes": list, "edges": list}, GRAPH_REPORT.md {"drift_alerts": list, "god_nodes": list}
NEGATIVE: 禁止在未經 Heuristic 靜態掃描前啟用 Deep Inference。禁止修改 manifest 以外的核心 meta 屬性。
HOOK: Wiki Governance / Decision Integrity Guard.

---
**[NEXUS INTERNAL SKILL: GRAPHIFY v1.0 | GOVERNANCE LEVEL-2]**
