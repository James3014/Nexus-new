# X1 — Harder Real Repair Task Expansion Report

**狀態**: `X1_HARD_REPAIR_TASK_SET_READY`  
**評估日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. 任務 Ingestion 與預檢結構 (Task Expansion Summary)
我們對 20 個候選任務進行了 preflight 預檢：
- **Accepted Tasks**: 共計 **17 個任務**，均屬 sympy, astropy, django 等配置齊備的 workspace。
- **Real Repairs**: 其中包含 **14 個真實修復/回歸任務**（含 C_12481, sympy-14096, django-11505 等中高難度 cross-function 任務）。
- **Rejected Tasks**: 共計 **3 個任務** (flask, matplotlib, numpy)，因本地 workspace 尚未配置而安全排除。
- **指標覆蓋**: 覆蓋 3 個 repos (sympy, astropy, django) 與 7 種 bug categories (constructor normal, output formatting, cross-function 等)。

## 2. Ingest 任務分類詳情

| 任務 ID | 所屬倉庫 | Bug 分類 | 任務屬性 | 預檢狀態 |
| :--- | :---: | :--- | :--- | :---: |
| **C_12481** | `sympy` | constructor_normalization | `repair_regression_anchor` | **ACCEPTED** |
| **C_13453** | `astropy` | output_formatting | `repair_regression_anchor` | **ACCEPTED** |
| **astropy-14182** | `astropy` | numeric_behavior | `real_repair_task` | **ACCEPTED** |
| **sympy-13852** | `sympy` | API_compatibility | `real_repair_task` | **ACCEPTED** |
| **astropy-13236** | `astropy` | missing_helper_call | `real_repair_task` | **ACCEPTED** |
| **sympy-13031** | `sympy` | data_structure_invariant | `real_repair_task` | **ACCEPTED** |
| **django-11001** | `django` | error_handling | `real_repair_task` | **ACCEPTED** |
| **django-12497** | `django` | wrong_call_order | `real_repair_task` | **ACCEPTED** |
| **sympy-14365** | `sympy` | numeric_behavior | `real_repair_task` | **ACCEPTED** |
| **sympy-14096** | `sympy` | medium_semantic_multi-hop | `real_repair_task` | **ACCEPTED** |
| **astropy-14902** | `astropy` | wrong_receiver_argument | `real_repair_task` | **ACCEPTED** |
| **astropy-12907** | `astropy` | error_handling | `real_repair_task` | **ACCEPTED** |
| **django-11505** | `django` | cross_function_dependency | `real_repair_task` | **ACCEPTED** |
| **django-13455** | `django` | data_structure_invariant | `real_repair_task` | **ACCEPTED** |

## 3. 結論
Ingest 任務完全通過 preflight，修復極限與硬任務基準擴充就緒。允許推進至 Milestone X2。
