# Y1 — Evidence Graph v0 Report

**狀態**: `Y1_EVIDENCE_GRAPH_READY`  
**評估日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. 任務 Evidence Graph 構建摘要 (Evidence Graph Summary)
我們為 17 個 Ingested/Accepted 任務成功構建了 Evidence Graphs。
- **資料結構與 Schema 校驗**: 均嚴格遵循 [evidence_graph_schema.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/y1_evidence_graph_v0/evidence_graph_schema.json) 設計，支援節點與邊的細粒度屬性。
- **Graph Constraints 滿足**:
  - 限制節點與檔案數量（防止 whole-repo dump 導致內容膨脹）。
  - 所有 Node/Edge 均明確標記 `provenance`（如 `ast_analysis`, `verifier_failure`）及 `confidence_score`。
  - 對於有編輯邊界風險或上下文不足之任務，明確標示 `missing_context_risks`（例如 `django-13455` 標記為 `broad_rewrite_risk`）。

---

## 2. 核心任務 Evidence Graph 實例

### Sympy-14096 (Medium Semantic Multi-Hop)
- **根源 Anchor**: `limit` (`sympy/series/limits.py`)
- **因果關係**:
  - `limit` -> depends_on -> `Pow._eval_is_integer` (`sympy/core/power.py`)
  - 完美呈現了多步語義跳轉的因果鏈（causal path）。
- **Example Artifact**: [sympy_14096_graph.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/y1_evidence_graph_v0/graph_examples/sympy_14096_graph.json)

### Django-11505 (Cross-Function Dependency)
- **根源 Anchor**: `add` (`django/contrib/messages/storage/base.py`)
- **因果關係**:
  - `add` -> calls -> `_encode` (`django/contrib/messages/storage/cookie.py`)
  - 呈現了當 proposer 在進行 cookie validation 時，需要關聯底層 cookie storage 的 `_encode` 方法。
- **Example Artifact**: [django_11505_graph.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/y1_evidence_graph_v0/graph_examples/django_11505_graph.json)

### Django-13455 (Hard Boundary Multi-File)
- **根源 Anchor**: `SQLCompiler.get_converters` (`django/db/models/sql/compiler.py`)
- **因果關係**:
  - `QuerySet.values` -> called_by -> `SQLCompiler.get_converters`
  - 此任務需要跨檔案的協同修補。Graph builder 成功偵測到 `broad_rewrite_risk`，為 Y2 multi-file 限制提供了前置判斷。

---

## 3. 結論與下一步
Evidence Graph v0 的構建成功破除了扁平 package 缺乏符號關係的弊端。下一步，我們將利用這些 Graph 所反映的跨符號/跨檔案關係，設計並檢驗安全受控的 Multi-Anchor/Multi-File 行動協議 (Y2)。
