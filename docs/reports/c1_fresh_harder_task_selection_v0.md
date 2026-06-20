# C1 — Fresh Harder Task Selection Report

**Status**: C1_TASK_SELECTION_READY
**Track**: Capability-First Post-V6 Execution Track

---

## 1. Candidate Task List

為了進行 Nexus 控制平面能力的深度驗證與成長，本階段篩選了 8 個全新（對比 V4-A/V4-B）的任務，涵蓋不同難度與修復屬性。

### 初始執行任務 (Initial Execution Tasks - Priority 1)

1.  **C_13453 (astropy__astropy-13453)**
    *   **任務類型**: Direct Repair (測試 7B 局部修復)
    *   ** issue/bug 摘要**: ascii.html 寫入時，HTML 格式輸出中特殊字符轉義或 class name 的標記有缺陷，需要進行單行/局部修復。
    *   **專案路徑**: `artifacts/external_sources/astropy_13236`
    *   **預期 Base Commit**: `95df21d`
    *   **預期 Verifier 指令**: `pytest astropy/io/ascii/tests/test_html.py`
    *   **預期通道 (Expected Lane)**: `verifier_passed_by_execution`
    *   **預期難度**: LOW
    *   **風險評估**: Model Risk: LOW | Context Risk: LOW | Env Risk: LOW
    *   **選取理由**: 標準小規模局部修復，適合建立 7B 基礎能力基線。
    *   **執行優先級**: HIGH

2.  **C_11618 (sympy__sympy-11618)**
    *   **任務類型**: Direct Repair (測試 7B 局部修復)
    *   ** issue/bug 摘要**: sympy.core.numbers 中 Point 或特定數字結構的精確度轉換或浮點比對失效。
    *   **專案路徑**: `artifacts/external_sources/sympy_13852`
    *   **預期 Base Commit**: `8059df7`
    *   **預期 Verifier 指令**: `pytest sympy/core/tests/test_numbers.py`
    *   **預期通道 (Expected Lane)**: `verifier_passed_by_execution`
    *   **預期難度**: LOW
    *   **風險評估**: Model Risk: LOW | Context Risk: LOW | Env Risk: LOW
    *   **選取理由**: Sympy 核心數學結構修復，驗證 7B 在數學邊界值比對上的直通修復力。
    *   **執行優先級**: HIGH

3.  **C_12481 (sympy__sympy-12481)**
    *   **任務類型**: Canonical/Source-Anchor (測試 AST slicing 與 canonical recovery)
    *   ** issue/bug 摘要**: sympy/combinatorics/permutations.py 中的排列組合運算，涉及 tricky 空白/縮排匹配或 anchor 偏置。
    *   **專案路徑**: `artifacts/external_sources/sympy_13852`
    *   **預期 Base Commit**: `8059df7`
    *   **預期 Verifier 指令**: `pytest sympy/combinatorics/tests/test_permutations.py`
    *   **預期通道 (Expected Lane)**: `canonical_recovery_success`
    *   **預期難度**: MEDIUM
    *   **風險評估**: Model Risk: MEDIUM | Context Risk: HIGH | Env Risk: LOW
    *   **選取理由**: Permutations 元件代碼結構複雜，適合考驗 AST slicing 能否精準截取修復區塊並藉由 canonical recovery 補正空白。
    *   **執行優先級**: HIGH

### 備用與對照任務 (Reserve & Control Tasks - Priority 2)

4.  **C_13877 (sympy__sympy-13877)**
    *   **任務類型**: Canonical/Source-Anchor
    *   ** issue/bug 摘要**: sympy/core/sympify.py 在處理外部字串轉代數表達式時，部分 parse 語意錨點缺失。
    *   **專案路徑**: `artifacts/external_sources/sympy_13852`
    *   **預期 Base Commit**: `e228d7a`
    *   **預期 Verifier 指令**: `pytest sympy/core/tests/test_sympify.py`
    *   **預期通道 (Expected Lane)**: `canonical_recovery_success`
    *   **預期難度**: MEDIUM
    *   **風險評估**: Model Risk: MEDIUM | Context Risk: HIGH | Env Risk: LOW
    *   **選取理由**: Sympify 的代碼依賴繁複，考驗 AST slicing 能否把關上下文膨脹（Context Bloat）。
    *   **執行優先級**: MEDIUM

5.  **C_14365 (astropy__astropy-14365)**
    *   **任務類型**: Semantic Failure (測試 14B 對比)
    *   ** issue/bug 摘要**: ascii.qdp 讀取 QDP 表格時，假設命令必須為全大寫，對大小寫不敏感格式解析報錯。
    *   **專案路徑**: `scratch/tmp_astropy_14182` 或 `artifacts/external_sources/astropy_13236`
    *   **預期 Base Commit**: `95df21d`
    *   **預期 Verifier 指令**: `pytest astropy/io/ascii/tests/test_qdp.py`
    *   **預期通道 (Expected Lane)**: `verifier_passed_by_execution`
    *   **預期難度**: HIGH
    *   **風險評估**: Model Risk: HIGH | Context Risk: MEDIUM | Env Risk: LOW
    *   **選取理由**: 需要進行 QDP 狀態機解析邏輯的小重構，適合在 7B 失敗時，引入 14B strict fallback 進行對比。
    *   **執行優先級**: MEDIUM

6.  **C_14096 (astropy__astropy-14096)**
    *   **任務類型**: Semantic Failure (測試 14B 對比)
    *   ** issue/bug 摘要**: Subclassed SkyCoord 屬性拋出誤導性的 AttributeError，需要在 __getattr__ 中正確處理 descriptor 與 MRO。
    *   **專案路徑**: `artifacts/external_sources/astropy_13236`
    *   **預期 Base Commit**: `95df21d`
    *   **預期 Verifier 指令**: `pytest astropy/coordinates/tests/test_sky_coord.py`
    *   **預期通道 (Expected Lane)**: `verifier_passed_by_execution`
    *   **預期難度**: HIGH
    *   **風險評估**: Model Risk: HIGH | Context Risk: MEDIUM | Env Risk: LOW
    *   **選取理由**: 涉及 Python 進階魔法方法 `__getattr__` 與 MRO 遍歷的修改，極需 14B 深度語義推理能力。
    *   **執行優先級**: MEDIUM

7.  **C_13579 (astropy__astropy-13579)**
    *   **任務類型**: Env-Sensitive (環境敏感分類)
    *   ** issue/bug 摘要**: SlicedWCS 的切片索引映射問題，容易觸及環境缺失或 numpy 相容性阻礙。
    *   **專案路徑**: `artifacts/external_sources/astropy_13236`
    *   **預期 Base Commit**: `95df21d`
    *   **預期 Verifier 指令**: `pytest astropy/wcs/wcsapi/wrappers/tests/test_sliced_wcs.py`
    *   **預期通道 (Expected Lane)**: `env_blocked_but_review_verified`
    *   **預期難度**: MEDIUM
    *   **風險評估**: Model Risk: LOW | Context Risk: LOW | Env Risk: HIGH
    *   **選取理由**: 驗證當依賴環境或 Numpy 架構出現版本不配時，Preflight 與 checker 是否能精準鎖定並隔離。
    *   **執行優先級**: MEDIUM

8.  **C_009_NEG (sympy__sympy-11618_neg)**
    *   **任務類型**: Negative/Control (負控制阻斷)
    *   ** issue/bug 摘要**: 驗證一個不需要進行任何代碼修改的 no-op 或已經被修復的環境狀態。
    *   **專案路徑**: `artifacts/external_sources/sympy_13852`
    *   **預期 Base Commit**: `8059df7`
    *   **預期 Verifier 指令**: `pytest sympy/core/tests/test_numbers.py`
    *   **預期通道 (Expected Lane)**: `no_op_correctly_rejected`
    *   **預期難度**: LOW
    *   **風險評估**: Model Risk: LOW | Context Risk: LOW | Env Risk: LOW
    *   **選取理由**: 檢驗當 patch 不具備修改必要性時，Patch Synthesis 能否正確判定 no-op 並安全 fail-closed。
    *   **執行優先級**: MEDIUM

---

## 2. Global Execution Rules Check

*   **3 Tasks Execution-ready**: `C_13453`, `C_11618`, 與 `C_12481` 已完成環境與源代碼錨定。
*   **Verifier commands known**: 所有 3 個初始任務均有明確的 pytest 單元測試命令與 python 虛擬環境定位。
*   **Governance Check**: `public_claim_allowed=false`, `training_eligible=false`, `runtime/routing=false`。無任何治理衝突。

**結論**: 滿足所有 C1 自動進入 C2 階段之邊界條件。
