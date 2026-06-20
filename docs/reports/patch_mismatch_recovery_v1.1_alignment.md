# Patch-Mismatch Recovery Sprint v1.1 — T1.1 Hotfix Alignment Report

**[階段]** Patch-Mismatch Recovery Sprint v1.1 — T1.1 Hotfix

**[總體判定]** 🟡 YELLOW (Provisional RED Invalidated)

**[一句話結論]** T1 的 5/5 RED 被判定為**基礎設施回歸 (Infrastructure Regression)**。真正的失敗原因是 T1 新增的 `patch_applier.py` preflight check 漏掉了 `import ast`，導致所有任務在執行真正 patch 診斷前均因 NameError 中斷。這不是 LLM 能力問題，而是測試儀器故障。

---

## 1. 核心判讀：為什麼 T1 的 RED 是暫定的？

在 T1 報告中，root cause 被寫為「LLM 生成了未 import ast 模組的程式碼」。然而，根據 Nexus v26 審查，證據更支持以下解釋：

*   **症狀**: 所有 5 題 rerun 均死在同一個 `NameError: name 'ast' is not defined`。
*   **物理證據**: T1 在 `patch_applier.py` 中新增了 preflight 檢查，該檢查呼叫了 `ast.parse()`。
*   **推論**: 由於錯誤是一致的且與 preflight 邏輯同步出現，這屬於 `infrastructure_regression`。在修復基礎設施前，無法評估 Patcher Hardening 的真實有效性。

---

## 2. T1.1 Hotfix 執行計畫 (Recovery Path)

### A. 根因修正 (Minimal Code Fix)
*   **目標**: 修復 `patch_applier.py` 的 `ast` 匯入問題。
*   **範圍**: 僅限補上 `import ast` 與對應的單元測試。

### B. 基礎設施驗證 (Unit Tests)
1.  驗證 `syntax preflight` 可正常呼叫 `ast.parse`。
2.  驗證 preflight 自身不會拋出 `NameError`。
3.  確保 `malformed SEARCH/REPLACE` 走的是正確的 `contract_preflight` 路徑。

### C. 原 5 題 Focused Rerun
*   **任務集**: `astropy__astropy-12907`, `astropy__astropy-13236`, `astropy__astropy-13579`, `astropy__astropy-14182`, `sympy__sympy-12481`。
*   **配置**: 鎖定 3B shadow + 7B planning + Qwen14B patch authority。
*   **禁止事項**: 不調模型、不換題、不開 sidecar。

---

## 3. 治理與更新後的下一步

*   **T1 狀態更新**: `RED Provisional` (被 infra bug 污染)。
*   **T2 延後**: 在 T1.1 完成並產出乾淨的 5 題 rerun 結果前，嚴禁啟動 T2 或擴大 benchmark。
*   **證據回寫**: 此 Hotfix 完成後，必須更新 `docs/reports/patch_mismatch_failure_corpus_v1.jsonl`，記錄真正的 patch 失敗分類（若仍失敗）。

---
**NEXUS IDENTITY: ea78cea5 + v28.3.0 RUNTIME-ALIGNED**
- **Alignment Source**: NEXUS_PROJECT_REVIEW_REPORT.md (June 16 Audit)
- **Status**: T1.1 HOTFIX IN-PROGRESS
