# LocalHeal Sprint C15-4D-2: Delegated Retry Prompt Ordering Diagnosis

**Status**: `C15_4D_2_DELEGATED_RETRY_PROMPT_ORDERING_DIAGNOSIS_PASS`

**Date**: 2026-07-04

**Commit**: `7014c128a docs: classify delegated retry output failures`

---

## 1. 問題摘要

Delegated retry 的 plumbing 已驗證完畢：
- delegated retry IS invoked（C15-4C-2 證實 3/3 attempts 均觸發）
- verifier evidence IS available 且 injected（C15-4C-2 證實 `semantic_retry_prompt_has_verifier_evidence=true`）
- C11/C13 SEARCH/REPLACE protocol contract IS fully reused（C15-4D-0 證實 `CONTRACT_REUSED`）
- 但 output quality 仍然失敗（C15-4D-1 證實 2/3 INDENTATION_SYNTAX_ERROR, 1/3 SEARCH_NOT_EXACT_SOURCE）

**delegated_retry solved = NOT_PROVEN**

失敗原因不是 plumbing 或 protocol contract 問題，而是 model output quality 問題。C15-4D-1 提出假設：`build_verification_guided_retry_prompt` 的 section 排列順序可能使 verifier evidence 比 locked SEARCH / output format 更 salient，導致小型 local model 優先處理邏輯修正而忽略格式要求。

本任務為 read-only 診斷，驗證此假設並設計最小修正方案。

---

## 2. 證據清單

### C15-4C-2 Live Probe Evidence

| 欄位 | Attempt 1 | Attempt 2 | Attempt 3 |
|------|-----------|-----------|-----------|
| `pipeline_retry_delegated` | true | true | true |
| `semantic_retry_prompt_has_verifier_evidence` | true | true | true |
| `delegated_retry_status` | REPLACE_SYNTAX_ERROR | REPLACE_SYNTAX_ERROR | SEARCH_MISMATCH |
| `solved` | false | false | false |

Source: `docs/reports/local_model_sprint_c15_4c_2_forced_delegated_retry_live_probe.md:32-37`

### C15-4D-0 Contract Reuse Evidence

| Contract Element | Status |
|-----------------|--------|
| Exact SEARCH/REPLACE format | CONTRACT_REUSED |
| Valid example first | CONTRACT_REUSED |
| Forbidden output types | CONTRACT_REUSED |
| Source anchoring | CONTRACT_REUSED |
| Indentation rules | CONTRACT_REUSED |

Source: `docs/reports/local_model_sprint_c15_4d_0_delegated_retry_protocol_contract_reuse_audit.md:64-76`

### C15-4D-1 Taxonomy Evidence

| Category | Count | Root Cause |
|----------|-------|-----------|
| INDENTATION_SYNTAX_ERROR | 2 | Model produces correct logic but wrong indentation in applied patch |
| SEARCH_NOT_EXACT_SOURCE | 1 | SEARCH block doesn't match current source file |

Source: `docs/reports/local_model_sprint_c15_4d_1_delegated_retry_output_failure_taxonomy.md:62-67`

### Function Evidence

**PromptBuilder.build_patch_system_prompt** (`prompt_builder.py:33-73`):
- 7B model: "HARD OUTPUT CONTRACT: Your response MUST be exactly one SEARCH/REPLACE block."
- Contains valid example, source anchoring rules, forbidden output types
- This is the system prompt — shared by primary and delegated retry paths

**PromptBuilder.build_verification_guided_retry_prompt** (`prompt_builder.py:241-300`):
- Current ordering: `original_user_prompt + header + verifier_section + evidence_section + search_lock + instruction`
- Line 300: `return original_user_prompt + header + verifier_section + evidence_section + search_lock + instruction`
- **Verifier evidence is positioned BEFORE locked SEARCH and output format instruction**

**SelfCorrector.build_retry_prompt** (`corrector.py:8-204`):
- Used by delegated retry in local_model_executor.py:1741
- Adds error-specific instructions (e.g., LOGIC_REGRESSION → "Output a valid SEARCH/REPLACE block")
- Does NOT reorder system prompt; system prompt comes from `build_patch_system_prompt`

**Delegated retry callsite** (`local_model_executor.py:1741-1771`):
- `retry_prompt = SelfCorrector().build_retry_prompt(original_user_prompt=request.problem_statement, ...)`
- `heal_ctx = LegacyHealContext(user_prompt=retry_prompt, ...)`
- `result_ctx = pipeline.run(heal_ctx)` → orchestrator → PatchSynthesisPhase → `build_patch_system_prompt` (system) + retry_prompt (user)
- If first patch fails verification → orchestrator semantic retry → `build_verification_guided_retry_prompt`

### Prompt Flow Map

```
Delegated Retry Path:
  local_model_executor.py
    → SelfCorrector.build_retry_prompt()  ← retry_prompt (user prompt)
    → pipeline.run(heal_ctx)
      → PatchSynthesisPhase
        → build_patch_system_prompt()     ← system prompt (SEARCH/REPLACE contract)
        → retry_prompt as user prompt
      → First patch attempt
      → If verifier fails:
        → orchestrator semantic retry
          → build_verification_guided_retry_prompt()  ← NEW user prompt
            ordering: original + header + verifier + evidence + search_lock + instruction
```

---

## 3. Clean Code / Linus 檢查表

### Responsibility Boundary

`build_verification_guided_retry_prompt` 的唯一職責是組裝 semantic retry 的 user prompt。它不觸碰 system prompt（`build_patch_system_prompt`），不修改 parser，不改變 verifier 行為。這是一個 pure function，輸入→輸出無副作用。

### Data Flow

Verifier evidence 透過 `build_verifier_evidence_section()` 生成，注入到 `evidence_section`。`search_lock` 包含已驗證的 canonical SEARCH span。兩者都是字符串拼接，無控制流影響。

### Coupling Point

`build_verification_guided_retry_prompt` 與 `orchestrator.py:366` 耦合。它是 orchestrator semantic retry 的唯一 prompt 來源。修改此函數直接影響 orchestrator 的 semantic retry 行為。

### Hidden Assumptions

1. 當前假設 verifier evidence 應在 locked SEARCH 之後 — 但實際排列是 verifier evidence 在前
2. 假設小型 local model 會同時處理所有 prompt sections — 但 positional bias 可能使前面的 sections 更 salient
3. 假設 "instruction" section 的 "Keep the SEARCH block above EXACTLY as-is" 足夠強調格式 — 但在 evidence 之後可能被忽略

### Test Gap

目前沒有測試驗證 `build_verification_guided_retry_prompt` 的 section 排列順序。RED tests 應覆蓋：
- search_lock 在 evidence_section 之前
- output format instruction 靠近 locked SEARCH
- verifier evidence 仍然保留

### Smallest Correction Surface

只修改 `build_verification_guided_retry_prompt` 一個函數（prompt_builder.py:300），重新排列 return 語句中的 section 順序。不觸及其他任何文件。

### Blast Radius

| 層面 | 影響 |
|------|------|
| Primary patch prompt | 無影響（不經過此函數） |
| SelfCorrector retry prompt | 無影響（獨立函數） |
| System prompt | 無影響（`build_patch_system_prompt` 不變） |
| Orchestrator semantic retry | 直接影響（唯一 callersite） |
| Parser/verifier | 無影響 |
| Candidate isolation | 無影響 |
| Route/topology | 無影響 |

### 回答 Checklist

- **Is prompt ordering a single-responsibility change?** ✅ 是。只改 section 排列，不改 sections 內容。
- **Is verifier evidence currently before locked SEARCH in user prompt?** ✅ 是。Line 300: `verifier_section + evidence_section + search_lock`。
- **Does retry prompt risk overwhelming SEARCH/REPLACE format instructions?** ⚠️ 可能。verifier evidence 在前可能使小型 model 優先處理邏輯。
- **Would a minimal patch touch only build_verification_guided_retry_prompt?** ✅ 是。只改 prompt_builder.py:300 的 return 語句。
- **Would primary prompt remain unchanged?** ✅ 是。`build_patch_system_prompt` 和 `build_patch_user_prompt` 不受影響。

---

## 4. 論文關聯

### Self-Refine

- **Relevant**: ✅ 直接相關 — iterative feedback/refinement without training
- **Already absorbed**: ✅ Nexus verifier retry 已吸收其核心思想（verifier feedback → retry）
- **Unsuitable direct adoption**: N/A — 已吸收
- **Possible later hypothesis**: 可考慮 Self-Refine 的 "self-feedback" 機制，但 C15-4D 不引入

### Reflexion

- **Relevant**: ⚠️ 部分相關 — language feedback across attempts
- **Already absorbed**: ✅ Nexus semantic retry 已提供跨 attempt feedback
- **Unsuitable direct adoption**: ✅ 不適合 — Reflexion 需要 episodic memory，Nexus 不應在此加入
- **Possible later hypothesis**: 如果 prompt ordering 不夠，可考慮有限的 attempt-level feedback 累積

### Self-Debugging

- **Relevant**: ✅ 直接相關 — use of execution feedback for code repair
- **Already absorbed**: ✅ Nexus verifier evidence injection 已對齊
- **Unsuitable direct adoption**: N/A — 已吸收
- **Possible later hypothesis**: 可考慮更結構化的 execution feedback 格式

### NExT

- **Relevant**: ⚠️ 部分相關 — execution-aware repair
- **Already absorbed**: ❌ 未吸收
- **Unsuitable direct adoption**: ✅ 不適合 — NExT 是 training-oriented，C15-4D 不能加 decoding framework
- **Possible later hypothesis**: 未來若需模型微調可參考

### Structured output / constrained decoding

- **Relevant**: ⚠️ 部分相關 — 可強制模型輸出 SEARCH/REPLACE 格式
- **Already absorbed**: ❌ 未吸收
- **Unsuitable direct adoption**: ✅ 不適合 — C15-4D 不能加新 decoding framework 或 loosening parser
- **Possible later hypothesis**: 未來可考慮 grammar-constrained decoding 作為後備方案

---

## 5. 最小方案

### No-code

保持當前 claim boundary。不宣稱 `delegated_retry solved`。当前狀態：
- delegated_retry solved = NOT_PROVEN
- production_ready = false
- public_claim_allowed = false

### Test-only

RED tests 驗證 prompt 排列順序（不改行為）：

```python
def test_verification_guided_retry_prompt_places_search_lock_before_verifier_evidence():
    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="fix the bug",
        verification_report="test failed",
        canonical_search_span="return x",
        target_file="src/app.py",
    )
    search_lock_pos = prompt.find("CANONICAL SEARCH SPAN")
    evidence_pos = prompt.find("VERIFICATION FAILURE REPORT")
    assert search_lock_pos < evidence_pos, "search_lock should come before verifier evidence"

def test_verification_guided_retry_prompt_keeps_output_format_near_locked_search():
    prompt = PromptBuilder.build_verification_guided_retry_prompt(...)
    search_lock_pos = prompt.find("CANONICAL SEARCH SPAN")
    instruction_pos = prompt.find("### INSTRUCTION")
    assert instruction_pos > search_lock_pos, "instruction should follow search_lock"
    assert instruction_pos - search_lock_pos < 500, "instruction should be near search_lock"

def test_verification_guided_retry_prompt_preserves_verifier_evidence():
    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        verifier_stdout_excerpt="EVIDENCE: normalize_score...",
    )
    assert "VERIFICATION FAILURE REPORT" in prompt
    assert "EVIDENCE: normalize_score" in prompt

def test_primary_patch_system_prompt_unchanged():
    prompt_7b = PromptBuilder.build_patch_system_prompt("qwen-7b")
    assert "HARD OUTPUT CONTRACT" in prompt_7b
    prompt_large = PromptBuilder.build_patch_system_prompt("qwen-14b")
    assert "Output ONLY SEARCH/REPLACE blocks" in prompt_large

def test_no_route_authority_fields_change():
    # Verify no new RouteMode, Router, or topology selector introduced
    import inspect
    from nexus.services.local_heal import prompt_builder
    source = inspect.getsource(prompt_builder)
    assert "RouteMode" not in source
    assert "Router" not in source
    assert "topology" not in source
```

### Minimal patch

**唯一候選**：修改 `build_verification_guided_retry_prompt` 的 return 語句（prompt_builder.py:300）。

**當前**:
```python
return original_user_prompt + header + verifier_section + evidence_section + search_lock + instruction
```

**修正候選**:
```python
return original_user_prompt + header + search_lock + instruction + verifier_section + evidence_section
```

**理由**:
- `search_lock` + `instruction` 在前 → 強調 SEARCH/REPLACE format 和 locked SEARCH
- `verifier_section` + `evidence_section` 在後 → 作為補充資訊
- 輸出格式 instruction 靠近 locked SEARCH → model 更可能遵循格式
- verifier evidence 保留 → 不丟失任何資訊

**不觸及**:
- `build_patch_system_prompt` (primary prompt 不變)
- `build_patch_user_prompt` (primary user prompt 不變)
- `SelfCorrector.build_retry_prompt` (SelfCorrector 路徑不變)
- parser/verifier/candidate isolation

### Refactor candidate

僅供未來參考：若 prompt 持續增長，可考慮 structured prompt sections（header / contract / evidence / instruction 獨立 block）。不在此任務執行。

---

## 6. TDD 計畫

### RED Tests

| Test | 驗證目標 |
|------|---------|
| `test_verification_guided_retry_prompt_places_search_lock_before_verifier_evidence` | search_lock 在 verifier_section 之前 |
| `test_verification_guided_retry_prompt_keeps_output_format_near_locked_search` | instruction 靠近 search_lock |
| `test_verification_guided_retry_prompt_preserves_verifier_evidence` | verifier evidence 未被移除 |
| `test_primary_patch_system_prompt_unchanged` | primary prompt 不受影響 |
| `test_no_route_authority_fields_change` | 無 route/router/planner/topology 變更 |

### Acceptance Criteria

- No runtime behavior changed in this task（只有 prompt 排列順序）
- delegated_retry solved remains NOT_PROVEN
- Minimal patch candidate has bounded blast radius（只改 prompt_builder.py:300）
- public_claim_allowed = false

### Verification Commands

```bash
# Compile check
python3 -m py_compile nexus/services/local_heal/prompt_builder.py

# Unit tests
uv run pytest tests/unit/local_heal/test_prompt_builder.py -q

# Existing tests unaffected
uv run pytest tests/unit/local_heal/ -q
```

---

## 7. 風險與需要批准的項目

| 項目 | 狀態 | 說明 |
|------|------|------|
| Prompt change requires approval | ⚠️ 需要批准 | 修改 `build_verification_guided_retry_prompt` 排列順序 |
| Runtime behavior change requires approval | ⚠️ 需要批准 | Semantic retry prompt 內容不變但順序改變，可能影響 model 行為 |
| Parser/verifier/candidate isolation change forbidden | 🚫 禁止 | 除非另行批准 |
| Route/topology change forbidden | 🚫 禁止 | 不引入新 RouteMode/Router/Planner |
| Public claim forbidden | 🚫 禁止 | delegated_retry solved = NOT_PROVEN |

### 風險評估

| 風險 | 嚴重度 | 緩解 |
|------|--------|------|
| Prompt reordering 可能降低 model 表現 | Medium | 保留所有 sections，只改順序 |
| 某些 model 可能依賴 verifier evidence 在前 | Low | 大型 model 應不受 positional bias 影響 |
| Test failure | Low | RED tests 為 pure assertion，不改 runtime |

---

## Statements

- **No runtime behavior changed**: 本任務為 read-only 診斷，不修改任何 runtime 代碼
- **No benchmark behavior changed**: 未運行 live benchmark
- **No route authority changed**: 無新 RouteMode, Router, Planner, 或 topology selector
- **No parser/verifier/candidate isolation changed**: 未修改這些系統
- **delegated_retry solved NOT_PROVEN**: 本任務不證明 delegated_retry solved
- **production_ready=false**: 本診斷不構成 production-ready
- **public_claim_allowed=false**: 不允許公開宣稱

---

## Required Commands Verification

```bash
test -f docs/reports/local_model_sprint_c15_4d_2_plan_delegated_retry_prompt_ordering_diagnosis.md
# Expected: exit 0

grep -n "問題摘要" docs/reports/local_model_sprint_c15_4d_2_plan_delegated_retry_prompt_ordering_diagnosis.md
# Expected: line with ## 1. 問題摘要

grep -n "證據清單" docs/reports/local_model_sprint_c15_4d_2_plan_delegated_retry_prompt_ordering_diagnosis.md
# Expected: line with ## 2. 證據清單

grep -n "Clean Code" docs/reports/local_model_sprint_c15_4d_2_plan_delegated_retry_prompt_ordering_diagnosis.md
# Expected: line with ## 3. Clean Code

grep -n "論文關聯" docs/reports/local_model_sprint_c15_4d_2_plan_delegated_retry_prompt_ordering_diagnosis.md
# Expected: line with ## 4. 論文關聯

grep -n "最小方案" docs/reports/local_model_sprint_c15_4d_2_plan_delegated_retry_prompt_ordering_diagnosis.md
# Expected: line with ## 5. 最小方案

grep -n "TDD" docs/reports/local_model_sprint_c15_4d_2_plan_delegated_retry_prompt_ordering_diagnosis.md
# Expected: line with ## 6. TDD 計畫

grep -n "需要批准" docs/reports/local_model_sprint_c15_4d_2_plan_delegated_retry_prompt_ordering_diagnosis.md
# Expected: line with ## 7. 風險與需要批准的項目

grep -n "delegated_retry solved NOT_PROVEN" docs/reports/local_model_sprint_c15_4d_2_plan_delegated_retry_prompt_ordering_diagnosis.md
# Expected: multiple lines

grep -n "production_ready=false" docs/reports/local_model_sprint_c15_4d_2_plan_delegated_retry_prompt_ordering_diagnosis.md
# Expected: at least one line

grep -n "public_claim_allowed=false" docs/reports/local_model_sprint_c15_4d_2_plan_delegated_retry_prompt_ordering_diagnosis.md
# Expected: at least one line
```
