# C2 — Baseline Reproduction Report

**Status**: C2_REPRODUCTION_COMPLETED
**Track**: Capability-First Post-V6 Execution Track

---

## 1. Reproduction Summary

本階段對 C1 篩選的 3 個初始任務進行了基準重現（Baseline Reproduction）。所有 3 個任務均在對應的 Base Commit 與 Python 虛擬環境中成功觸發預期故障，Exit Code 均為 1。

| 任務 ID | 實例 ID | 專案路徑 | 驗證 Commits | 重現指令 | 預期故障表現 | 實際重現結果 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `C_13453` | `astropy__astropy-13453` | `.nexus/workspaces/astropy` | `95df21d` | `python reproduce_bug.py` | HTML table 寫入時忽視了 formats 參數 | 成功重現，拋出 AssertionError |
| `C_11618` | `sympy__sympy-11618` | `.nexus/workspaces/sympy` | `d4f8832` | `python reproduce_11618.py` | Point.distance 截斷不同維度的座標返回 1 | 成功重現，返回 1 觸發 AssertionError |
| `C_12481` | `sympy__sympy-12481` | `.nexus/workspaces/sympy` | `c807dfe` | `python reproduce_12481.py` | Permutation 傳入 non-disjoint list 拋出 ValueError | 成功重現，拋出預期 ValueError |

---

## 2. Details of Reproduction

### C_13453 (astropy__astropy-13453)
*   **重現指令**: `cd .nexus/workspaces/astropy && /Users/jameschen/Workspace/nexus/.venv_astropy/bin/python reproduce_bug.py`
*   **輸出證據**:
    ```
    HTML Output:
    ...
    FAILURE: formats={'a': '%.2f'} was ignored!
    ```
*   **Exit Code**: 1

### C_11618 (sympy__sympy-11618)
*   **重現指令**: `cd .nexus/workspaces/sympy && git checkout d4f8832c21 && /Users/jameschen/Workspace/nexus/.venv_sympy/bin/python reproduce_11618.py`
*   **輸出證據**:
    ```
    Calculated distance: 1
    FAILURE: Point.distance zipped coordinates without checking dimensions, returned 1.
    ```
*   **Exit Code**: 1

### C_12481 (sympy__sympy-12481)
*   **重現指令**: `cd .nexus/workspaces/sympy && git checkout c807dfe756 && /Users/jameschen/Workspace/nexus/.venv_sympy/bin/python reproduce_12481.py`
*   **輸出證據**:
    ```
    BUG PRESENT: ValueError raised for repeated elements: there were repeated elements; to resolve cycles use Cycle(0, 1)(0, 2).
    ```
*   **Exit Code**: 1

---

## 3. Corrected Verifier Config and Base Commit Adjustments

在重現過程中，我們發現 `task_selection.json` 中對 sympy 任務的說明存在以下偏差，現已進行動態修正：
1.  **C_11618**: 預期 Base Commit 原為 `8059df7` (2023年已修復)，經追蹤 PR 11618 歷史，修正為 `d4f8832c21` (Merge PR 11618 前一刻)。預期 Verifier 指令原為 `test_numbers.py` (不相關)，修正為 `reproduce_11618.py`（核心是 Point 幾何點的 distance 函數）。
2.  **C_12481**: 預期 Base Commit 修正為 `c807dfe756` (PR 12481 merge 前一刻)。預期 Verifier 指令修正為 `reproduce_12481.py`。

這些調整確保了測試環境的精確性與 AST slicing 對準的正確性。滿足所有進入 C3 階段的條件。
