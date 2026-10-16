# U2 — Real Repair Task Expansion

**狀態**: `U2_REAL_REPAIR_TASK_SET_READY`, `U2_VERIFIER_LIMITED`  
**評估日期**: 2026-06-21  
**Ingestion 擴充集規模**: 10 個候選任務

---

## 1. 任務集 Ingestion 篩選與結果

為了消除先前 R6/T3 被標記的 `task-scope-limited` 限制，我們對 10 個本地候選任務進行了 Ingest 預檢：

*   **採納任務集 (`accepted_task_set.json`)**:
    - 共 **8 個任務** 通過 preflight 預檢（reproduce 穩定且環境與 verifier 就緒）：
      - `C_12481` (sympy - constructor_normalization)
      - `C_13453` (astropy - output_formatting)
      - `astropy__astropy-14182` (astropy - numeric_geometry_behavior)
      - `sympy__sympy-13852` (sympy - API_compatibility)
      - `astropy__astropy-13236` (astropy - missing_helper_call)
      - `sympy__sympy-13031` (sympy - data_structure_invariant)
      - `django__django-11001` (django - error_handling)
      - `django__django-12497` (django - wrong_call_order)
    - **指標成效**: 涵蓋 **3 個 Repos** (sympy, astropy, django)，**6 種 Bug Categories**。已完全跨越「最窄 6 題 / 3 庫 / 4 分類」門檻。
*   **拒絕任務集 (`rejected_task_set.json`)**:
    - `flask__flask-11200` 與 `matplotlib__matplotlib-10012` 被拒絕 (`U2_VERIFIER_LIMITED`)。
    - *理由*: 本地 `.nexus/workspaces/` 未配置 Flask 與 Matplotlib 的實體測試環境，導致 baseline 無法穩定 reproduce。

---

## 2. Ingestion 決策規則套用
*   **真實修補能力判定**: 8 個被採納之任務均為 `real_repair_task` 或 `repair_regression_anchor`，具有實體驗證器 (Verifier)，可以用於最終的 Route C uplift 判定。
*   **邊界劃定**: 沒有包含任何多檔案修改 (multi-file edit) 的複雜硬邊界任務，保障了 ARM 提案的 constraints 收斂。
