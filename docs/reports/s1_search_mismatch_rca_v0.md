# S1 — SEARCH_MISMATCH RCA Freeze Report

**Status**: S1_RCA_FREEZE_COMPLETED
**Track**: Search-Mismatch Capability Recovery Track

---

## 1. Failed Task Evidence Rollup

本階段對 C4 (7B Repair) 階段發生的 `SEARCH_MISMATCH` 進行了根因證據凍結。

### 1.1 C_11618 (sympy__sympy-11618)
- **Task ID**: `C_11618`
- **Source File**: `sympy/geometry/point.py`
- **Target Symbol**: `Point.distance`
- **AST Slice Span**: `Point.distance` (Line 325-360)
- **Exact Source Snippet**:
  ```python
          (s, p) = Point._normalize_dimension(self, Point(p))
          return sqrt(Add(*((a - b) ** 2 for (a, b) in zip(s, p))))
  ```
- **Model-Generated SEARCH**:
  ```python
  <<<<<<< SEARCH
          return sqrt(sum((a - b)**2 for a, b in zip(self.args, other.args)))
  ```
- **Mismatch Class**: `verbatim_mismatch` (7B 使用了 `self.args` 和 `other.args` 以及 `sum(...)`，而實際是 `s`, `p` 和 `Add(*...)`)
- **Parametric/Version Drift**: 是，7B 腦補了其預訓練權重中常見的 Point 距離計算實現，而非當前 SymPy 代碼。
- **Source Slice Contains Text**: 是，AST sliced context 包含正確程式碼，但模型未遵循。
- **Failure Classification**: `SEARCH_VERBATIM_COMPLIANCE_FAILURE` / `PATCH_PROTOCOL_TOO_STRICT_FOR_7B`

### 1.2 C_12481 (sympy__sympy-12481)
- **Task ID**: `C_12481`
- **Source File**: `sympy/combinatorics/permutations.py`
- **Target Symbol**: `Permutation.__new__`
- **AST Slice Span**: `Permutation` (Line 1-253)
- **Exact Source Snippet**:
  在 `l` 為多維列表時，SymPy 的原始代碼使用 `has_dups(l)` 來檢查重複元素：
  ```python
          if has_dups(l):
              raise ValueError('there were repeated elements')
  ```
- **Model-Generated SEARCH**:
  ```python
  <<<<<<< SEARCH
          if len(set(elements)) != len(elements):
              raise ValueError('there were repeated elements')
  ```
  以及第二次嘗試的:
  ```python
  <<<<<<< SEARCH
          if has_dups(l):
              raise ValueError('there were repeated elements')
  ```
  *(但該處已超出 [SOURCE CONTEXT] 給予的 1-253 行範圍，導致 search_mismatch)*
- **Mismatch Class**: `verbatim_mismatch`
- **Parametric/Version Drift**: 是，7B 腦補了 `len(set(elements))` 或猜測了 `has_dups` 的位置。
- **Source Slice Contains Text**: 否（1-253行內未包含實際重複檢查的原始段落）。
- **Failure Classification**: `AST_SLICE_INSUFFICIENT` + `SEARCH_VERBATIM_COMPLIANCE_FAILURE`

### 1.3 C_13453 (astropy__astropy-13453)
- **Task ID**: `C_13453`
- **Source File**: `astropy/io/ascii/html.py`
- **Target Symbol**: `write_ascii_html`
- **AST Slice Span**: `HTML` (Line 1-233)
- **Exact Source Snippet**:
  HTML 寫入的 formats 處理部分，原始代碼在 `HTML` 類別內：
  ```python
  # (原始代碼並不存在 write_ascii_html 的 top-level 函式定義)
  ```
- **Model-Generated SEARCH**:
  ```python
  <<<<<<< SEARCH
  def write_ascii_html(table, file=None, formats=None, **kwargs):
  ```
- **Mismatch Class**: `verbatim_mismatch` / `hallucinated_symbol`
- **Parametric/Version Drift**: 是，模型虛構了 `write_ascii_html` 函數，即使 source context 內只有 `HTML.write` 類別方法。
- **Source Slice Contains Text**: 否（因為該函數純屬模型腦補）。
- **Failure Classification**: `SEARCH_VERBATIM_COMPLIANCE_FAILURE`

---

## 2. Pattern Summary
- **Hallucinated source**: 模型高度傾向於從預訓練記憶中提取「看似正確」的程式碼結構來拼湊 `SEARCH` 區塊。
- **Paraphrased source**: 7B 模型極難做到 100% 逐字匹配，微小的語義/變量命名差異即會觸發 `SEARCH_MISMATCH` 阻斷。
- **Whitespace/Context mismatch**: 由於 7B 缺乏對全局 AST 精確位置的掌控力，極易在縮排與空格上失準。

---

## 3. Root Cause Conclusion
本次分析的 primary root cause 為：
- **SEARCH_VERBATIM_COMPLIANCE_FAILURE** (主要原因)：7B 無法遵循 verbatim 匹配。
- **PATCH_PROTOCOL_TOO_STRICT_FOR_7B** (次要原因)：現有協定要求模型同時負擔「定位(SEARCH)」與「修改(REPLACE)」雙重職責，對 7B 而言定位成本過高。
