# C15-5H: Valid Unified Diff Conversion Probe — Report

**Sprint**: C15-5H  
**Date**: 2026-07-04  
**Commit**: `72fa1de64`  
**Branch**: `feature/bridge-fastmatcher-20260606`  
**Status**: ✅ ROOT CAUSE FOUND AND FIXED

---

## 1. C15-5G Handoff Summary

C15-5G 確認在 malformed unified diff 下，bridge 正確拒絕轉換。但 mock 注入的有效 unified diff 同樣無法通過 bridge，判定為 `C15_5G_BRIDGE_CONVERSION_FAILED`，`conversion_status = "none"`，`rejection_reason = "unified_diff_malformed"`。

C15-5H 目標：找出為何有效 unified diff 無法通過轉換器。

---

## 2. 診斷路徑

### 初步假設（已排除）

| 假設 | 驗證結果 |
|------|---------|
| `DiffToSSRPConverter.convert()` 本身有 bug | ❌ 排除：單元測試 + 手動 Python 驗證均通過 |
| `source_text` 不是原始 buggy 版本 | ❌ 排除：`apply_failure_target_file_hash_after_restore = 9cdae1b4` 對應正確 buggy_source |
| `target_path.exists()` 返回 False | ❌ 排除：restore 邏輯確認 target_path 存在 |
| mock diff 長度或格式問題 | ❌ 排除：`out_len=261` 對應正確，`classify_format` 返回 `UNIFIED_DIFF` |

### 根因 1：`_dr_localized_files` 型別錯誤

**位置**：`local_model_executor.py` L1780

**問題**：
```python
# 修前（錯誤）
_dr_localized_files = [(request.target_file, _current_content)]  # list[tuple]

# PatchSynthesisPhase.run() L226:
loc_file = input_data.localized_files[0]  # tuple
expected_target = loc_file.path           # AttributeError: 'tuple' object has no attribute 'path'
```

`LocalizationPhase.execute()` L110-111：
```python
if ctx.op.localized_files:  # 非空 → skip
    return PhaseResult(success=True)  # tuple 直接傳到 PatchSynthesisPhase
```

**影響**：`PatchSynthesisPhase.run()` 在 L226 丟 `AttributeError`，被 orchestrator 吞掉，`model_decisions = []`，`_last_patch_decision = None`，`_conversion_status = "none"`。

**修正**：
```python
# 修後（正確）
from nexus.services.local_heal.interface import LocalizedFile as _LocalizedFile
_dr_localized_files = [_LocalizedFile(path=request.target_file, content=_current_content)]
```

### 根因 2：`repair_spec` 生成錯位 `model_decisions[-1]`

**位置**：`patch_synthesis.py` L125

**問題**：
```python
model_decisions.append({"phase": "patch", **patch_decision})   # index 0
# ...
model_decisions.append({"phase": "repair_spec", **spec_decision, "status": "SUCCESS"})  # index 1

# 之後所有 model_decisions[-1] 指向 repair_spec (index 1)
model_decisions[-1]["conversion_status"] = "none"          # 設在 repair_spec 上！
model_decisions[-1]["conversion_status"] = conv_status     # 也設在 repair_spec 上！
```

`local_model_executor.py` L1856-1859 用 `reversed()` 找 `phase in ("patch", "semantic_retry_patch")`，找到的是 **patch decision (index 0)**，它的 `conversion_status` 從未被設定，仍是初始狀態（不存在），`get("conversion_status", "none")` 返回 `"none"`。

**修正**：將 `repair_spec` telemetry 以 inline fields 記錄在 patch decision 中：
```python
# 修前：model_decisions.append({"phase": "repair_spec", ...})
# 修後：
model_decisions[-1]["repair_spec_model"] = spec_decision.get("model", "")
model_decisions[-1]["repair_spec_status"] = "SUCCESS"
```

---

## 3. 修改檔案清單

| 檔案 | 說明 |
|------|------|
| `nexus/services/local_heal/local_model_executor.py` | `_dr_localized_files` 從 tuple 改為 `LocalizedFile` |
| `nexus/services/local_heal/phases/patch_synthesis.py` | `repair_spec` 不再 append 分離 decision，改為 inline fields |
| `tests/unit/local_heal/test_local_model_executor.py` | 新增 `test_c15_5h_dr_localized_files_is_localized_file_not_tuple` 回歸測試 |
| `tests/unit/local_heal/test_diff_to_ssrp.py` | 新增 `test_c15_5h_patch_synthesis_phase_conversion_with_localized_file` 端到端整合測試 |

---

## 4. 紅線審核表

| 紅線項目 | 狀態 |
|---------|------|
| 不新增 route / router / planner | ✅ 無 |
| 不改 verifier 行為 | ✅ 無 |
| 不改 parser contract | ✅ 無 |
| 不 hardcode toy | ✅ 無 |
| 不 fuzzy apply | ✅ 無 |
| 不宣稱 solved | ✅ 未宣稱 |
| 不宣稱 production_ready | ✅ 未宣稱 |

---

## 5. Deterministic Test Evidence

```
tests/unit/local_heal/test_local_model_executor.py::test_c15_5h_dr_localized_files_is_localized_file_not_tuple  PASSED
tests/unit/local_heal/test_diff_to_ssrp.py::test_c15_5h_patch_synthesis_phase_conversion_with_localized_file   PASSED

173 passed in 2.80s (focused test suite)
```

整合測試確認：在 `LocalizedFile` 正確傳入的情況下：
- `PatchSynthesisPhase.run()` 不丟 AttributeError
- `model_decisions` 非空
- `conversion_status == "unified_diff_to_ssrp_converted"`
- `preimage_match_status == "exact_match"`

---

## 6. Decision Gate Result

| Gate | 條件 | 結果 |
|------|------|------|
| **Bug Reproduction** | Integration test 重現 C15-5H 根因 | ✅ PROVEN |
| **Fix Verification** | Integration test 通過（conversion_status=unified_diff_to_ssrp_converted） | ✅ PROVEN |
| **No Regression** | 173 focused tests 全過，pre-existing failures 無新增 | ✅ VERIFIED |

---

## 7. Live Run Summary

本 checkpoint live run 結果（`toy-math-verifier-evidence-gap`，無 mock）：
- `candidate_models=[] len=0`：委員會配置未啟用（execution_topology=localheal_pipeline）
- 主 pipeline 正常跑，verifier_result=fail（模型語義修復不足，非 bridge 問題）
- Bridge 路徑未觸發（無小模型候選），但根因修復已由 unit test 證明

---

## 8. Non-Claims

- **NOT solved**: verifier_result=fail，修的是 bridge 路徑，非 repair 品質
- **NOT armor ready**: 委員會 live bridge path 未在真實 run 中觸發
- **NOT production_ready**
- **NOT public_claim_allowed**

---

## 9. 下一步建議

### C15-5I（建議）：Live Committee Bridge 驗證
在 `toy-math-verifier-evidence-gap` task spec 中加入 `delegated_retry_candidate_models`，設置包含至少一個能生成 unified diff 的小模型，驗證 bridge path 端到端在真實委員會場景下是否能 `conversion_status=unified_diff_to_ssrp_converted` 並進入 `run_isolated_workspace_apply`。

### C15-5J（備選）：Real Repair Task
上游 bridge 已通，可嘗試真實 SWE 任務的委員會 unified diff 修復。
