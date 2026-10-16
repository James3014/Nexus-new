# C6BK: sympy-13852 Lower-Layer Anchor Stability Probe

**Date**: 2026-07-07
**Task**: C6BK-sympy-anchor-stability-probe-autopilot
**Scope**: Confirm that sympy-13852's C6BJ failure was caused by `anchor_too_short_for_body`, not by `problem_statement` generalization failure.

---

## 1. 問題摘要

C6BJ 發現 assertion-grounded `problem_statement` 的泛化被 low-layer instability 阻塞：sympy-13852 在 `REPLACEMENT_SYNTAX_INVALID` 失敗，`problem_statement` 從未到達模型提示詞。C6BK 深入驗證此阻斷層的 root cause taxonomy，確認是否與 pre-C6BD astropy-13236 同類。

---

## 2. 證據清單

| # | 證據 | 來源 | 類型 |
|---|---|---|---|
| E1 | sympy-13852 locked_search = `"if a is S.One:"` — 僅 1 行 | `m1_real_local_solve_benchmark.py#L125` | 靜態分析 |
| E2 | buggy_code 中 if-header 下方有 indented `pass` body (12 空格) | `m1_real_local_solve_benchmark.py#L126-L131` | 靜態分析 |
| E3 | `ast.parse("if a is S.One:")` → `SyntaxError: expected an indented block` | `test_c6bk_sympy_anchor_probe.py` | Unit test |
| E4 | `ast.parse("if a == S.One:")` → 同樣 SyntaxError | `test_c6bk_sympy_anchor_probe.py` | Unit test |
| E5 | Multi-line replacement (`if a == S.One:\n    pass`) → AST 解析通過（wrapped） | `test_c6bk_sympy_anchor_probe.py` | Unit test |
| E6 | C6BJ live rerun: `REPLACEMENT_SYNTAX_INVALID`, `"expected an indented block after 'if' statement on line 2"`, 8.05s | `c6bj_assertion_grounded_generalization_check.md#L21` | Live rerun |
| E7 | `problem_statement` 從未注入 prompt（anchor parse fail 發生在前） | `c6bj_assertion_grounded_generalization_check.md#L22` | Pipeline metadata |
| E8 | astropy-13236 pre-C6BD locked_search 也是 1 行 import（無 body） | 已知歷史 | 對照組 |

---

## 3. sympy-13852 Lower-Layer Taxonomy

### Taxonomy: `anchor_too_short_for_body`

| 維度 | 數值 |
|---|---|
| 分類 | `anchor_too_short_for_body` |
| locked_search 長度 | 1 行 (14 chars) |
| locked_search 語法 | `if a is S.One:` — 不完整 Python（if-header 缺 body） |
| AST 驗證路徑 | `ast.parse(stripped)` → SyntaxError → `ast.parse(def _wrapper():\n    {stripped})` → SyntaxError |
| 與 astropy pre-C6BD 差異 | astropy 的 import 行是完整 statement (AST 可解析)，sympy 的 if-header 連 AST 都無法解析 — **更嚴重** |
| 阻斷位置 | prompt 構建之後，模型輸出 AST 驗證之時 |
| `problem_statement` 可送達性 | **未送達** — AST 驗證在 prompt 送出前就卡住 |

### 排除的 Taxonomy

| Taxonomy | 排除理由 |
|---|---|
| `wrong_nearby_region` | locked_search `if a is S.One:` 在 buggy_code 中唯一匹配，region 正確 |
| `symbol_region_not_reached` | target_symbol `eval` 正確指向 class method，region 可達 |
| `stable_anchor_but_model_syntax_fail` | 不是模型語法錯誤 — 是 locked_search 先天不完整導致任何 replacement 都無效 |
| `unknown_lower_layer_instability` | root cause 完整可追溯 |

---

## 4. Bounded Generalization Blockage 是否成立

**成立。** 證據鏈完整：

```
locked_search "if a is S One:" (1 line, incomplete Python if-header)
  → 模型中看不到 indented body
  → 模型輸出 replacement 也是 1 line incomplete if
  → AST validation: ast.parse("if a == S One:") → SyntaxError
  → REPLACEMENT_SYNTAX_INVALID
  → protocol_parse_failed=True
  → pipeline never reaches verifier or problem_statement evaluation
```

此阻斷與 `problem_statement` 是否存在完全無關 — 即使 sympy 有 `problem_statement`，anchor 層不穩定時模型根本無法產生可 parse 的 patch。

與 pre-C6BD astropy-13236 完全同類，但 sympy 更嚴重：astropy 的 import 行至少是完整 Python statement（AST 可解析），sympy 的 if-header 是語法不完整。

---

## 5. 最小方案

### 候選 Patch: `task-local multi-line locked_search`

將 sympy-13852 的 locked_search 從單行：
```python
"if a is S.One:"
```

改為包含 indented body 的多行版本：
```python
"        if a is S.One:\n"
"            pass\n"
```

**預期效果**：
- 模型可看到完整的 if-block（含 body）
- 輸出 replacement 可包含完整 `if a == S.One:\n            pass`
- 通過 AST validation（`ast.parse` with wrapper fallback）
- `problem_statement` 可送達模型 prompt
- 此為 `C6BL-sympy-task-local-anchor-fix` 的範圍

**不更動處**：
- 不改 `problem_statement`（維持無 problem_statement 狀態）
- 不改 parser / verifier / committee / prompt framework
- 不改 public API

---

## 6. Next Automatic Action

**`C6BL-sympy-task-local-anchor-fix`**

執行步驟：
1. 將 locked_search 改為 multi-line（含 indented pass body）
2. 執行 1 次 live rerun 驗證 `protocol_parse_failed=False`
3. 若通過，加入 `problem_statement`（同 astropy pattern）驗證 generalization
4. 若仍失敗，重新分類 taxonomy 並 freeze

### 受影響檔案

| File | Status | Change |
|---|---|---|
| `tests/unit/local_heal/test_c6bk_sympy_anchor_probe.py` | **NEW (this probe)** | 8 test-only anchor probes |
| `docs/reports/c6bk_sympy_anchor_stability_probe.md` | **NEW (this report)** | Full probe report |
| `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md` | **Update** | Learning closure entry |

**Future (C6BL):**
| `scripts/bench/m1_real_local_solve_benchmark.py` | Modify | sympy locked_search → multi-line |

**No public API modified. No parser/committee/verifier/anchor/prompt framework changes.**
