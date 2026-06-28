# 🛡️ June Unsolved Task Inventory (Phase 56E)

本文件整理並分層管理 6 月歷史未通過任務（Gaps），以便有計劃地進行分批 replay。

---

## 1. 歷史未通過任務清單 (Inventory)

| Task ID | Historical Stage | Historical Status | Historical Failure Class | Historical Blocker | Artifact Path | Has Repro | Has Verifier | Has Oracle | Likely Group | Recommended Replay Order |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **astropy-14182** | `verification` | `fail` | `patch_mismatch` | `local_environment_mismatch` | `artifacts/runtime/.../astropy__astropy-14182.json` | Yes | Yes | Yes | `B_SEMANTIC_UNSOLVED` | **Batch 1 (No. 1)** |
| **sympy-13852** | `verification` | `fail` | `unverified_gap` | `local_environment_mismatch` | `artifacts/runtime/.../sympy__sympy-13852.json` | Yes | Yes | Yes | `B_SEMANTIC_UNSOLVED` | **Batch 1 (No. 2)** |
| **astropy-13579** | `environment` | `fail` | `environment_blocked` | `file_not_found` | `artifacts/runtime/.../astropy__astropy-13579.json` | Yes | Yes | Yes | `C_INFRA_BLOCKED` | **Batch 1 (No. 3)** |
| **astropy-13453** | `localization` | `fail` | `search_mismatch` | `context_exhausted` | `artifacts/runtime/.../astropy__astropy-13453.json` | Yes | Yes | Yes | `E_SEARCH_MISMATCH` | **Batch 2 (No. 4)** |
| **django-11001** | `verification` | `fail` | `retry_exhausted` | `semantic_wrong` | `artifacts/runtime/.../django__django-11001.json` | Yes | Yes | Yes | `B_SEMANTIC_UNSOLVED` | **Batch 2 (No. 5)** |
| **django-12497** | `verification` | `fail` | `retry_exhausted` | `semantic_wrong` | `artifacts/runtime/.../django__django-12497.json` | Yes | Yes | Yes | `B_SEMANTIC_UNSOLVED` | **Batch 2 (No. 6)** |

---

## 2. 第一批 Replay 任務 (Batch 1) 規劃
第一批選擇 5 題以進行精確的主線能力與阻斷驗證：
1. **Group A (防退化 - 舊過現在過)**: `astropy-13236` / `astropy-12907`。
2. **Group B (主線能力恢復 - 舊沒過現在過)**: `astropy-14182` / `sympy-13852`。
3. **Group C (環境/設施故障阻斷 - 舊沒過現在阻斷)**: `astropy-13579`。
