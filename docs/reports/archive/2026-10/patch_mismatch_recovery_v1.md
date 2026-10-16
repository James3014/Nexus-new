# Patch-Mismatch Recovery Sprint v1 — P0-lite Report (Updated)

**[階段]** Patch-Mismatch Recovery Sprint v1 — P0-lite → T1.2 Targeted Fix

**[總體判定]** 🟡 Yellow (T1.3 telemetry chain complete, both tasks have full diagnostic data, no regression)

**[一句話結論]** T1.3 完成三項基礎設施修復：(1) syntax preflight 改為驗證 full patched file 而非 isolated fragment；(2) fuzzy threshold 從 0.85 降至 0.75；(3) PatchError.telemetry 完整 forwarding 到 receipt。兩題仍為 SEARCH_MISMATCH，但 telemetry 已完整（file_path, mismatch_subclass, canonical_span, failed_search_text），下一步可做 targeted span injection。

---

## T1.2 Targeted Fix (2026-06-17)

### Priority 1: SEARCH_MISMATCH × 2 — Canonical Span Enforcement + Telemetry

| 項目 | 說明 |
|------|------|
| Root cause | LLM 生成的 SEARCH block 與 source 不 verbatim match；fuzzy fallback 不夠；subclass 未傳播到 receipt |
| 修復 | protocol.py `validate()` 新增 canonical span tracking（source_hash, line range, auto_corrected flag）|
| 新增 | receipt.py `_extract_failure_telemetry()` — SEARCH_MISMATCH 時記錄 mismatch_subclass, file_path, closest_match |
| 新增 | prompt_builder.py — SEARCH_MISMATCH retry 時注入 verbatim copy 強制指令 |

### Priority 2: REPLACE_SYNTAX_ERROR × 1 — Syntax Error Detail Capture

| 項目 | 說明 |
|------|------|
| Root cause | preflight 捕捉到 syntax error 但 telemetry 只記錄 error 字串，無 line/offset |
| 修復 | patch_applier.py `preflight_check()` 新增 syntax_error_line, syntax_error_offset, replace_preview_hash |
| 修復 | receipt.py `_failure_class()` — `REPLACE_SYNTAX_ERROR` 前置判定，返回 `syntax_invalid:replacement` |
| 新增 | prompt_builder.py — REPLACE_SYNTAX_ERROR retry 時注入 indentation 指引 |

### Priority 3: FILE_NOT_FOUND × 1 — Path Resolution Taxonomy

| 項目 | 說明 |
|------|------|
| Root cause | LLM 生成路徑指向 reproduce_bug.py；preflight 無 path_subclass 分類 |
| 修復 | patch_applier.py `preflight_check()` — rglob + relative_suffix 雙策略 resolution；path_subclass 分類（wrong_repro_path / generated_wrong_path / repo_not_mounted）|
| 修復 | receipt.py `_failure_class()` — FILE_NOT_FOUND 前置判定，返回 `file_not_found:wrong_repro_path` 等 |
| 新增 | receipt.py `_extract_failure_telemetry()` — FILE_NOT_FOUND 時記錄 target_path, repo_dir, path_subclass |
| 新增 | prompt_builder.py — FILE_NOT_FOUND retry 時注入僅限 SOURCE CONTEXT 路徑指令 |

### Priority 4: NO_EFFECTIVE_CHANGE × 1 — Semantic Diff Gate

| 項目 | 說明 |
|------|------|
| Root cause | patch 被接受但 validate_effective_change 判定無功能邏輯變更；receipt 無 diff hash |
| 修復 | receipt.py `_failure_class()` — NO_EFFECTIVE_CHANGE 前置判定，返回 `no_effective_change` |
| 新增 | receipt.py `_extract_failure_telemetry()` — NO_EFFECTIVE_CHANGE 時記錄 patch_hash, patch_length |
| 新增 | prompt_builder.py — NO_EFFECTIVE_CHANGE retry 時注入 behavior delta 強制指令 |

### 代碼變更清單

| 文件 | 變更 |
|------|------|
| `nexus/services/local_heal/protocol.py` | `validate()` 新增 canonical span telemetry (source_hash, line range, auto_corrected, closest_match) |
| `nexus/services/local_heal/patch_applier.py` | `preflight_check()` 新增 syntax error details, FILE_NOT_FOUND path taxonomy, resolution tracking |
| `nexus/services/local_heal/receipt.py` | 新增 `_extract_failure_telemetry()`, `_failure_class()` 重排 RELOAD_SYNTAX_ERROR/FILE_NOT_FOUND/NO_EFFECTIVE_CHANGE |
| `nexus/services/local_heal/prompt_builder.py` | retry section 新增 SEARCH_MISMATCH/REPLACE_SYNTAX_ERROR/FILE_NOT_FOUND/NO_EFFECTIVE_CHANGE-specific guidance |

### Test Results

- ✅ 16/16 local_heal tests pass
- ⚠️ 2 pre-existing test failures (tuple vs LocalizedFile — not from T1.2 changes)

---

## T1.1 Regression Hotfix

| 項目 | 說明 |
|------|------|
| Root cause | `patch_applier.py` 使用 `ast.parse` 但未 `import ast`，導致 preflight 自身 NameError |
| 修復 | 加 `import ast` 到 `patch_applier.py` 頂部 |
| 影響範圍 | 單點修復，不涉及 taxonomy / model authority / prompt builder |

---

## 1. 已完成

| 模組 | 變更 | Commit |
|------|------|--------|
| `errors.py` | 新增 `PatchMismatchSubclass` enum（5 subclasses） | — |
| `protocol.py` | 新增 `_classify_mismatch_subclass()` 機械判定邏輯 | — |
| `receipt.py` | 新增 `preflight_telemetry`, `closest_snippet_present`, `closest_snippet_similarity`, `resolved_span` 欄位 | — |
| `patch_applier.py` | 新增 `preflight_check()` + 修復 `import ast` regression | — |
| `interface.py` | `PatchSynthesisOutput` 新增 `preflight_telemetry` 欄位 | — |
| `patch_synthesis.py` | 傳遞 `preflight_telemetry` 到 output | — |
| `failure_corpus_v1.jsonl` | 5 題失败語料已生成 | — |

---

## 2. T1.1 Results

| Task | T1 (before fix) | T1.1 (after fix) | failure_class |
|------|:---:|:---:|:---|
| astropy-12907 | ❌ NameError | ❌ SEARCH_MISMATCH | patch_mismatch |
| astropy-13236 | ❌ NameError | ❌ SYNTAX_ERROR | syntax_invalid |
| astropy-13579 | ❌ NameError | ❌ FILE_NOT_FOUND | patch_mismatch |
| astropy-14182 | ❌ NameError | ❌ SEARCH_MISMATCH | patch_mismatch |
| sympy-12481 | ❌ NameError | ❌ NO_EFFECTIVE_CHANGE | patch_mismatch |
| **Solve rate** | **0/5** | **0/5** | — |

**T1 RED was provisional (invalidated by infra bug). T1.1 RED is valid (real patcher failures).**

---

## 3. 細分類分布 (T1.1)

| failure_class | Count | subclass |
|:---:|:---:|:---|
| patch_mismatch (SEARCH_MISMATCH) | 2 | VERBATIM_SEARCH_MISMATCH |
| patch_mismatch (FILE_NOT_FOUND) | 1 | UNKNOWN_PATCH_MISMATCH |
| patch_mismatch (NO_EFFECTIVE_CHANGE) | 1 | UNKNOWN_PATCH_MISMATCH |
| syntax_invalid (REPLACE_SYNTAX_ERROR) | 1 | PATCH_SYNTAX_INVALID |

**真正的 patcher 瓶頸已浮現：**
- SEARCH_MISMATCH × 2：matcher / canonical snippet 問題
- SYNTAX_ERROR × 1：LLM 生成的 patch 語法錯誤
- FILE_NOT_FOUND × 1： localization 找錯檔案
- NO_EFFECTIVE_CHANGE × 1：LLM 生成的 patch 沒有實質變更

---

## 4. 治理與主線判定

- **維持現有 3B/7B/Qwen14B 主線**：YES
- **expected / observed stop-layer**：expected=verification, observed=patcher（不匹配——正常，這是失败案例）
- **claim boundary 風險**：無。所有 run 均 `claim_eligible=false`

---

## 5. 下一步

T1.1 暴露了真實的 patcher failure 分佈。下一步應針對最高頻 failure 類型做 targeted fix：

1. **SEARCH_MISMATCH × 2**：改善 matcher / canonical snippet pipeline
2. **SYNTAX_ERROR × 1**：改善 prompt builder 的語法提示
3. **FILE_NOT_FOUND × 1**：改善 localization accuracy
4. **NO_EFFECTIVE_CHANGE × 1**：改善 prompt builder 的 minimum fix 提示

**是否需要第二輪 focused rerun**：YES，但需先 targeted fix 最高頻 failure。

---

## 產出物

1. `docs/reports/patch_mismatch_recovery_v1.md`（本文件）
2. `docs/reports/patch_mismatch_failure_corpus_v1.jsonl`（5 題失败語料）
3. Receipt / audit artifacts：`.nexus/reports/local_heal/{task}__PATCH_FIX_V2/`
