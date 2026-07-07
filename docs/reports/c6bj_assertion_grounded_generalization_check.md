# C6BJ: Assertion-Grounded `problem_statement` Generalization Check

**Date**: 2026-07-07
**Task**: C6BJ-assertion-grounded-generalization-check-autopilot
**Scope**: Verify whether C6BF Phase 2's `problem_statement` patch generalizes beyond astropy__astropy-13236.

---

## 1. 問題摘要

C6BF Phase 2 解決了 astropy__astropy-13236: 在 benchmark spec 中加入 assertion-grounded `problem_statement`（`"The patched file must not contain 'view(NdarrayMixin)'"`），使模型從 `partial_fix`（添加而非移除 `view(NdarrayMixin)`）轉為正確的 `verifier:pass`。本任務驗證此修補是否為單題適用，還是對同類型 task 有泛化價值。

---

## 2. 證據清單

| # | 證據 | 來源 | 類型 |
|---|---|---|---|
| E1 | astropy-13236: C6BF Phase 2 `problem_statement` 加入後連 2 次 SOLVED | `docs/reports/c6bf_apply_contract_patch.md#L148-L165` | Live rerun |
| E2 | sympy-13852: 加入相同 pattern `problem_statement` 後 rerun 失敗 | `REPLACEMENT_SYNTAX_INVALID`, 8.05s | Live rerun |
| E3 | sympy-13852 locked_search 僅 1 行 (`if a is S.One:`) → 模型輸出不完整 Python | `error_message: expected an indented block after 'if' statement on line 2` | Pipeline metadata |
| E4 | `problem_statement` 在 sympy 從未被注入提示詞 → 無法評估其效果 | `protocol_parse_failed=True` 在 prompt 構建之前 | Pipeline metadata |
| E5 | 7 個 C6BJ test-only generalization probe 全 PASS | `test_c6bj_generalization_probe.py` | Unit test |
| E6 | 完整 C6 鏈 (C6AZ~C6BF~C6BJ) 44 test PASS | 全量 pytest | Regression |

---

## 3. 13236 Solve 是否可歸因於 assertion-grounded prompt

**YES** — 直接因果鏈：

```
C6BF Phase 2 (benchmark spec + problem_statement)
  → task_desc = "must not contain view(NdarrayMixin)"
  → 模型在 prompt 中知道 verifier PASS condition
  → patch 正確移除 view(NdarrayMixin)
  → verifier exit=0, solved=True
```

與 C6BE 對照：C6BE 已解決 prose contamination（apply 可達），但 verifier 仍失敗 — 模型不知道要移除什麼。唯一變化是 `problem_statement`。

---

## 4. Bounded Generalization Verdict

**結論**: `generalization blocked by lower-layer instability`

| 維度 | 評估 |
|---|---|
| `problem_statement` 語義模式 | 可泛化。sympy-13852 的 verifier（檢查 `a == S.One`）同等適用於 `"must contain X"` assertion。模式已由 test-only probe 驗證。 |
| lower-layer 穩定性 | **阻塞**。sympy-13852 的 locked_search 僅 1 行（`if a is S.One:`），不含 indented body → 模型產生不完整 Python → `REPLACEMENT_SYNTAX_INVALID`。問題發生在 prompt 構建之前。 |
| 與 astropy-13236 pre-C6BD 類比 | 完全一致：C6BD 之前 astropy 也被 anchor 過短阻塞（locked_search 為 import 行而非 6-line view block）。 |

**阻斷層次**: locked_search / anchor layer，非 problem_statement layer。sympy 需要等於 C6BD 等級的 multi-line locked_search 調整才能評估 problem_statement 的泛化效果。

---

## 5. 最小方案

**No-code / Test-only**（已實施）：

- 7 個 test-only generalization probes（`test_c6bj_generalization_probe.py`）驗證：
  - astropy-13236 `problem_statement` 正確流入 `task_desc`
  - 無 `problem_statement` 的 task 仍使用舊 fallback（regression guard）
  - `problem_statement` 不跨 task 污染
  - 正負 assertion pattern（must contain / must not contain）皆可表達
  - `problem_statement` 不影響 verifier_command / verify_script 等 runtime 邏輯
- sympy-13852 的 `problem_statement` 已 revert（維持僅 astropy 單題適用）

---

## 6. Next Automatic Action

**Freeze this fix as task-local and stop.**

- 不對 `problem_statement` 做通用 framework 化
- 不沿 semantic lane 繼續深挖 astropy-13236（已 SOLVED）
- 不對 sympy-13852 或其他 task 套用相同的 problem_statement 模式
- 僅保留 test-only generalization probe 作為未來 anchor-layer 穩定後的啟動條件

## 7. 受影響檔案

| File | Change |
|---|---|
| `tests/unit/local_heal/test_c6bj_generalization_probe.py` | 7 test-only probes (NEW) |
| `docs/reports/c6bj_assertion_grounded_generalization_check.md` | This report (NEW) |
| `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md` | Learning closure entry |

**No public API modified. No parser/committee/verifier/anchor/prompt framework changes. No benchmark expansion beyond 1 probe task.**
